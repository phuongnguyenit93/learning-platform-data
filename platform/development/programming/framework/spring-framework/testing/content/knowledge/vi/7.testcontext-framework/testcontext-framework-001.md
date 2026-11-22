# Vấn đề nạp cấu hình và quản lý kiểm thử tích hợp

Kiểm thử tích hợp Spring thường cần nhiều thành phần cùng hoạt động: dependency injection, cấu hình ứng dụng, repository, transaction, web layer, message listener và các dịch vụ bên ngoài. Spring TestContext Framework cung cấp cơ chế tạo `ApplicationContext`, tiêm dependency vào test, quản lý transaction và tái sử dụng context giữa các test. Khi cấu hình không rõ ràng hoặc mỗi test yêu cầu một context khác nhau, suite có thể khởi động rất chậm, khó chẩn đoán lỗi hoặc vô tình chia sẻ trạng thái giữa các kịch bản.

Thiết kế kiểm thử tích hợp tốt bắt đầu từ việc chọn đúng phạm vi context, khai báo chính xác cấu hình và nguồn property, rồi quản lý vòng đời context theo nhu cầu thực tế. Một context nên chứa đúng các bean cần kiểm tra; dữ liệu và tài nguyên mutable cần có cách cô lập riêng; context chỉ nên bị đóng và tạo lại khi trạng thái của nó thực sự không còn an toàn để tái sử dụng.

## 1. Spring TestContext Framework quản lý những gì?

TestContext Framework là nền tảng tích hợp kiểm thử của Spring. Nó phối hợp với JUnit Jupiter thông qua `SpringExtension` và cung cấp một `TestContext` chứa thông tin về test class, test method, `ApplicationContext` và các thuộc tính liên quan.

Một số thành phần quan trọng:

| Thành phần | Trách nhiệm |
|---|---|
| `SpringExtension` | Kết nối vòng đời JUnit Jupiter với Spring TestContext Framework |
| `TestContextManager` | Điều phối các callback và listener cho test class/method |
| `TestContext` | Cung cấp context hiện tại, test instance, test method và thuộc tính test |
| `TestExecutionListener` | Thực hiện các hành vi như dependency injection, transaction, xử lý `@DirtiesContext` |
| `TestContextBootstrapper` | Xác định cách xây dựng cấu hình test context |
| `ContextLoader` / `SmartContextLoader` | Tạo `ApplicationContext` từ cấu hình đã hợp nhất |

Với JUnit Jupiter, có thể kích hoạt Spring extension trực tiếp:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = CustomerServiceTestConfig.class)
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void loadsCustomerServiceFromSpringContext() {
        assertThat(customerService).isNotNull();
    }
}
```

Khi dùng Spring Boot, `@SpringBootTest`, `@DataJpaTest`, `@WebMvcTest` và các test slice tương tự đã tích hợp cơ chế extension cần thiết. Không cần thêm `@ExtendWith(SpringExtension.class)` một cách máy móc khi annotation cấp cao đã cung cấp nó.

TestContext Framework không chỉ tạo context một lần cho mỗi test. Nó xây dựng cấu hình đã hợp nhất, tra cache để tìm context tương ứng, tạo mới nếu chưa có và quản lý các listener theo vòng đời test. Hiểu cơ chế này giúp giải thích vì sao hai test class có thể dùng cùng một context hoặc vì sao một thay đổi nhỏ trong annotation lại làm suite khởi động thêm nhiều lần.

## 2. Chọn cách nạp cấu hình phù hợp

Spring có nhiều cách tạo test context. Hãy chọn theo phạm vi cần kiểm tra.

### 2.1. `@ContextConfiguration` cho context Spring có phạm vi xác định

`@ContextConfiguration` khai báo resource locations hoặc class cấu hình để nạp `ApplicationContext`. Nó phù hợp với integration test Spring không cần toàn bộ auto-configuration của Spring Boot.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        CustomerServiceConfig.class,
        CustomerRepositoryTestConfig.class
})
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void createsCustomer() {
        Customer customer = customerService.create("Lan");

        assertThat(customer.name()).isEqualTo("Lan");
    }
}
```

`classes` thường chứa `@Configuration`, component hoặc lớp cấu hình mà loader có thể xử lý. Nếu dùng XML, có thể khai báo `locations`:

```java
@ContextConfiguration(locations = "classpath:/test-context.xml")
class LegacyIntegrationTest {
    // Các dependency được lấy từ context XML.
}
```

Có thể dùng `@SpringJUnitConfig` như một cách viết gọn kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`:

```java
@SpringJUnitConfig(CustomerServiceTestConfig.class)
class CustomerServiceTest {
    // Test sử dụng cấu hình Spring đã chỉ định.
}
```

Khi cấu hình rõ ràng bằng class, người đọc biết context cần những bean nào. Điều này cũng giúp tránh vô tình quét toàn bộ ứng dụng khi test chỉ cần một phần nhỏ.

### 2.2. `@SpringBootTest` để nạp ứng dụng Spring Boot

`@SpringBootTest` tạo test context dựa trên cơ chế khởi động Spring Boot. Nếu không chỉ định `classes`, Spring Boot tìm lớp `@SpringBootConfiguration` phù hợp, thường là lớp có `@SpringBootApplication`, bằng cách dò từ package của test lên các package cha.

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    @Autowired
    private OrderService orderService;

    @Test
    void loadsApplicationServices() {
        assertThat(orderService).isNotNull();
    }
}
```

Nếu có nhiều lớp cấu hình ứng dụng hoặc test nằm ngoài cây package được dò, hãy chỉ định rõ lớp cấu hình:

```java
@SpringBootTest(classes = LearningApplication.class)
class OrderServiceIntegrationTest {
    // Nạp ứng dụng bắt đầu từ LearningApplication.
}
```

Lỗi thường gặp là `Unable to find a @SpringBootConfiguration`. Hãy kiểm tra package của test, vị trí lớp main application và thuộc tính `classes` trước khi thêm một cấu hình ứng dụng giả chỉ để làm test khởi động.

### 2.3. Chọn web environment

`@SpringBootTest` cho phép xác định cách tạo môi trường web bằng `webEnvironment`:

| Giá trị | Hành vi |
|---|---|
| `MOCK` | Tạo web application context mô phỏng nếu ứng dụng có web stack; không khởi động server HTTP thật. Đây là mặc định. |
| `RANDOM_PORT` | Khởi động server thật trên một cổng ngẫu nhiên. |
| `DEFINED_PORT` | Khởi động server thật trên cổng cấu hình, thường là 8080 nếu không đổi. |
| `NONE` | Tạo application context không có môi trường web. |

Ví dụ kiểm tra endpoint bằng `MockMvc` với full application context:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrderFromApplicationContext() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk());
    }
}
```

Khi cần kiểm tra HTTP server, port binding hoặc tương tác qua socket, dùng `RANDOM_PORT`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {
    @LocalServerPort
    private int port;

    @Test
    void startsHttpServerOnAnAvailablePort() {
        assertThat(port).isPositive();
    }
}
```

`RANDOM_PORT` có chi phí khởi động server cao hơn `MOCK`, vì vậy chỉ dùng khi hành vi của server thật là một phần mục tiêu. Một điểm cần nhớ: request HTTP được xử lý ở thread phía server, trong khi transaction của test method chạy ở thread phía test. Transaction test-managed không tự bao bọc transaction của request từ server; dữ liệu do request tạo có thể được commit và cần cleanup riêng.

### 2.4. Test slice cho một phần ứng dụng

Spring Boot cung cấp các annotation slice như `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` và các slice khác. Chúng nạp một tập bean phù hợp với một tầng, thường loại bỏ những phần ứng dụng không liên quan.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;
}
```

`@WebMvcTest` tập trung vào MVC: controller, binding, validation, converter, filter và cấu hình web được chọn. Service thường được thay bằng mock để test tập trung vào HTTP contract.

```java
@DataJpaTest
class OrderRepositoryTest {
    @Autowired
    private OrderRepository orders;
}
```

`@DataJpaTest` tập trung vào entity, repository và cấu hình JPA. Nó thường dùng transaction test được rollback sau mỗi method. Nếu cần thêm bean cấu hình hoặc import một thành phần, hãy làm rõ phần mở rộng thay vì chuyển tất cả repository test sang `@SpringBootTest`.

Một test slice không phải bản sao đầy đủ của ứng dụng. Nếu một bean không được nạp trong slice, đó có thể là hành vi có chủ đích. Hãy thêm đúng cấu hình cần thiết bằng `@Import`, `@TestConfiguration` hoặc annotation mở rộng tương ứng.

## 3. Bổ sung cấu hình dành riêng cho test

Không nên sửa cấu hình production chỉ để tạo một điều kiện kiểm thử. Spring Test cho phép bổ sung cấu hình test bằng class cấu hình, profile và property source.

### 3.1. `@TestConfiguration` và `@Import`

`@TestConfiguration` đánh dấu cấu hình bổ sung chỉ dành cho test. Một lớp nested `@TestConfiguration` trong test có thể thêm bean mà vẫn giữ khả năng phát hiện cấu hình ứng dụng chính của Spring Boot.

```java
@SpringBootTest
@Import(TestClockConfiguration.class)
class SubscriptionIntegrationTest {
    @Autowired
    private SubscriptionService subscriptions;
}

@TestConfiguration
class TestClockConfiguration {
    @Bean
    @Primary
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    }
}
```

`@Import` làm rõ cấu hình bổ sung được nạp cùng context. `@Primary` giúp Spring chọn bean test khi có nhiều bean cùng kiểu. Nếu dependency dùng `@Qualifier`, hãy cung cấp đúng tên/qualifier tương ứng.

Có thể khai báo nested test configuration trong test class:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @Autowired
    private PaymentService paymentService;

    @TestConfiguration
    static class PaymentTestConfiguration {
        @Bean
        PaymentGateway paymentGateway() {
            return new InMemoryPaymentGateway();
        }
    }
}
```

Lớp cấu hình nested là static để không cần một instance của test class bên ngoài. Nếu dùng cấu hình top-level, hãy import rõ ràng khi cần thêm nó vào context.

### 3.2. `@ActiveProfiles` để chọn profile

`@ActiveProfiles` kích hoạt profile cho test context. Ví dụ, ứng dụng có `application-integration.yml`:

```java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerIntegrationTest {
    // Nạp cấu hình chung và cấu hình theo profile integration.
}
```

Profile có thể chứa endpoint, tên database, logging hoặc feature flag dành cho môi trường test. Không đặt credential production vào profile test và không dùng profile để che giấu một cấu hình không rõ ràng.

Khi kế thừa test class, `@ActiveProfiles` mặc định kế thừa profile từ superclass. Nếu lớp con cần tự xác định hoàn toàn profile, có thể dùng `inheritProfiles = false`.

```java
@ActiveProfiles(value = "repository-test", inheritProfiles = false)
class IsolatedRepositoryTest extends BaseIntegrationTest {
}
```

Hãy dùng profile có tên theo mục đích và giữ nhất quán giữa IDE, Gradle/Maven và CI. Tránh bật profile bằng một biến môi trường riêng trên máy cá nhân mà không đưa cấu hình tương ứng vào quy trình chạy test.

### 3.3. `@TestPropertySource`

`@TestPropertySource` thêm property source vào `Environment` của test context. Có thể đọc cấu hình từ file:

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/integration-test.properties")
class NotificationIntegrationTest {
}
```

Hoặc khai báo inline properties:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "notification.delivery.enabled=false",
        "notification.retry.max-attempts=2"
})
class NotificationIntegrationTest {
}
```

Inline properties có độ ưu tiên cao hơn các file location được khai báo trong cùng `@TestPropertySource`. Khi cần kiểm tra một giá trị cụ thể, inline property giúp test tự mô tả điều kiện mà không phải tạo thêm file.

Spring Boot cũng hỗ trợ thuộc tính `properties` trên `@SpringBootTest`:

```java
@SpringBootTest(properties = "feature.invoice.enabled=true")
class InvoiceFeatureIntegrationTest {
}
```

Đừng khai báo cùng một key ở quá nhiều nơi mà không biết nguồn nào đang thắng. Khi một property không có giá trị mong đợi, hãy kiểm tra profile đang hoạt động, file được nạp, inline properties và nguồn dynamic trước khi thay đổi bean.

## 4. Property động cho tài nguyên được cấp lúc chạy

Một số dependency test không có URL hoặc cổng cố định trước khi khởi động. Ví dụ, Testcontainers cấp cổng database ngẫu nhiên; mock server cấp port sau khi start; một service test có thể tạo thư mục hoặc endpoint tạm. `@DynamicPropertySource` cho phép đăng ký property từ các giá trị được cung cấp tại runtime.

```java
@SpringBootTest
@Testcontainers
class CustomerDatabaseIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Phương thức được đánh dấu `@DynamicPropertySource` phải là `static` và nhận `DynamicPropertyRegistry`. Mỗi `registry.add` đăng ký một supplier; giá trị được lấy khi property được truy cập. Cách này hữu ích cho endpoint, cổng và credential do tài nguyên test cung cấp.

Các dynamic properties có độ ưu tiên cao hơn những property source thông thường như `@TestPropertySource`, system properties, environment variables và property source khai báo trong ứng dụng. Điều này giúp thông tin runtime của container được dùng khi tạo datasource.

Nếu dùng `@DynamicPropertySource` trong superclass, các lớp con có thể kế thừa cùng phương thức. Khi supplier trả giá trị khác nhau giữa các subclass nhưng cấu hình được cache dùng chung, hãy bảo đảm context không bị tái sử dụng với endpoint cũ. Trong trường hợp đó, `@DirtiesContext` trên base class hoặc cấu trúc test tách context rõ ràng có thể cần thiết.

Đừng dùng dynamic property cho giá trị thực ra đã biết và ổn định. Với một feature flag hoặc timeout cố định, inline property thường dễ đọc hơn. Dùng dynamic property khi giá trị chỉ có sau khi khởi tạo tài nguyên.

## 5. Cấu hình kế thừa và context hierarchy

Spring cho phép chia sẻ cấu hình test qua superclass hoặc tổ chức context thành nhiều cấp.

### 5.1. Kế thừa `@ContextConfiguration`

Các cấu hình test có thể được kế thừa từ lớp cha. Mặc định, locations và classes được kết hợp theo quy tắc kế thừa của annotation. Nếu lớp con cần thay thế cấu hình của lớp cha, có thể đặt `inheritLocations = false`.

```java
@SpringJUnitConfig(classes = SharedIntegrationConfig.class)
abstract class BaseIntegrationTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
class CustomerRepositoryTest extends BaseIntegrationTest {
}
```

Khi cần kiểm soát hoàn toàn cấu hình lớp con:

```java
@ContextConfiguration(
        classes = CustomerTestConfig.class,
        inheritLocations = false)
class IsolatedCustomerTest extends BaseIntegrationTest {
}
```

`@ActiveProfiles` và `@TestPropertySource` cũng có quy tắc kế thừa riêng, mặc định cho phép kế thừa. Các thuộc tính `inheritProfiles`, `inheritLocations` và `inheritProperties` giúp thay đổi cách kết hợp. Hãy đọc rõ ý nghĩa của từng annotation vì `inheritLocations` không điều khiển profile hoặc property source.

Base test class nên chứa những cấu hình thật sự chung và ổn định. Nếu mỗi lớp con phải tắt phần lớn cấu hình của lớp cha, cấu trúc kế thừa có thể đang làm context khó hiểu và khó tái sử dụng.

### 5.2. `@ContextHierarchy` cho context cha và con

Trong một số ứng dụng, đặc biệt ứng dụng web theo kiến trúc Spring MVC truyền thống, có thể cần một root context chứa service/repository và một child context chứa controller hoặc web configuration. `@ContextHierarchy` mô tả cấu trúc đó:

```java
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class LegacyWebIntegrationTest {
    @Autowired
    private WebApplicationContext webContext;
}
```

Child context có thể truy cập bean từ parent context, trong khi parent không phụ thuộc child. Tách cấp giúp mô phỏng cách ứng dụng web truyền thống khởi tạo root và servlet context.

Không cần dùng hierarchy cho mọi ứng dụng Spring Boot. Nếu chỉ cần một application context, `@SpringBootTest` hoặc một slice test thường đơn giản hơn. Hierarchy phù hợp khi cấu trúc nhiều context là một phần kiến trúc cần kiểm tra.

## 6. Spring cache `ApplicationContext` như thế nào?

Khởi tạo `ApplicationContext` có thể tốn thời gian vì Spring phải quét component, tạo bean, cấu hình datasource, khởi động server hoặc kết nối các tài nguyên. TestContext Framework duy trì một cache context dùng chung trong cùng JVM để các test có cấu hình tương đương không phải khởi động lại.

Cache key được tạo từ cấu hình đã hợp nhất. Những thành phần chính tham gia key gồm:

- Resource locations và configuration classes.
- Context initializer classes.
- Context customizers, bao gồm các cấu hình do test cung cấp và dynamic properties.
- Context loader.
- Parent context nếu dùng hierarchy.
- Active profiles.
- Property source descriptors và inline property values.
- Resource base path của web context.

Hai test class có cùng cấu hình đã hợp nhất có thể nhận cùng một context từ cache. Chỉ khác một profile, property, class cấu hình hoặc customizer cũng có thể tạo cache key khác và dẫn đến một context mới.

Cache được dùng trong cùng process/JVM của test suite. Nó không tự chia sẻ context giữa hai tiến trình Gradle fork khác nhau hoặc giữa hai lần chạy CI độc lập.

### 6.1. Vì sao suite có quá nhiều context?

Giả sử mười test class đều dùng `@SpringBootTest`, nhưng mỗi class khai báo một inline property khác nhau:

```java
@SpringBootTest(properties = "feature.a.enabled=true")
class FeatureATest {
}

@SpringBootTest(properties = "feature.b.enabled=true")
class FeatureBTest {
}
```

Các cấu hình khác nhau có thể tạo các cache key khác nhau. Nếu mỗi class còn dùng profile hoặc mock bean khác, số context tăng thêm. Việc tạo context mới nhiều lần thường là nguyên nhân khiến integration suite chậm.

Hãy gom những cấu hình thực sự giống nhau vào một cấu hình dùng chung. Nếu hai nhóm test cần giá trị khác nhau, hãy xác định chúng có thực sự cần context riêng hay có thể thay đổi dữ liệu đầu vào ở cấp test method. Không gom cấu hình chỉ để đạt cache hit nếu điều đó làm test mất tính độc lập.

### 6.2. Giới hạn cache và chính sách LRU

Context cache có giới hạn kích thước. Mặc định, cache giữ tối đa 32 context; khi vượt giới hạn, context ít được sử dụng gần đây nhất có thể bị loại theo chính sách least-recently-used (LRU) và được đóng.

Có thể điều chỉnh kích thước bằng system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Hãy cân nhắc tăng giới hạn sau khi đã hiểu vì sao suite cần nhiều context. Tăng cache có thể giảm số lần khởi động lại nhưng cũng giữ nhiều bean, connection pool và tài nguyên trong bộ nhớ hơn. Nếu cache miss đến từ cấu hình vô tình khác nhau, sửa cấu hình thường hiệu quả hơn tăng giới hạn.

### 6.3. Xem thống kê cache

Để tìm nguyên nhân suite tạo nhiều context, bật log DEBUG cho cache:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Log thống kê có thể cho biết số lần hit, miss và số context đang nằm trong cache. Nếu miss tăng gần như theo số test class, hãy so sánh các annotation cấu hình, profile, property, import và mock bean của các class đó.

Một context được tái sử dụng không có nghĩa mọi trạng thái bên trong nó được reset. Spring singleton bean vẫn tồn tại trong suốt vòng đời context. Cache chỉ quản lý việc tái sử dụng context, không phải cơ chế cô lập dữ liệu test.

## 7. Quản lý context bằng `@DirtiesContext`

`@DirtiesContext` đánh dấu context hiện tại là không còn an toàn để tái sử dụng. Spring loại context tương ứng khỏi cache và đóng nó; lần test sau cần cấu hình đó sẽ tạo context mới.

Ví dụ dùng sau khi test thay đổi trạng thái singleton bean hoặc cấu hình context theo cách không thể khôi phục:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutableApplicationConfigurationTest {
    // Test thay đổi trạng thái cấp ApplicationContext.
}
```

Các chế độ thường dùng ở cấp class:

| `ClassMode` | Thời điểm đánh dấu context |
|---|---|
| `BEFORE_CLASS` | Trước khi chạy các test method trong class |
| `AFTER_CLASS` | Sau khi hoàn tất class; đây là mặc định |

Ở cấp method, có thể chọn:

| `MethodMode` | Thời điểm đánh dấu context |
|---|---|
| `BEFORE_METHOD` | Trước test method |
| `AFTER_METHOD` | Sau test method; đây là mặc định |

Ngoài ra, `@DirtiesContext` có thể áp dụng cho hierarchy với các chế độ `HierarchyMode`, xác định việc loại bỏ context hiện tại hoặc cả những context liên quan trong hierarchy.

### 7.1. Khi nào cần `@DirtiesContext`?

Annotation này phù hợp khi test làm thay đổi trạng thái của chính context và không thể khôi phục đáng tin cậy, chẳng hạn:

- Thay đổi bean singleton hoặc registry cấp context mà test khác không thể reset.
- Thay đổi cấu hình runtime của context theo cách ảnh hưởng đến bean khác.
- Test một tình huống đặc biệt làm context không còn sử dụng được sau khi chạy.

Không dùng `@DirtiesContext` như cách dọn mọi dữ liệu test. Nếu test chỉ tạo record trong database, hãy dùng transaction rollback hoặc cleanup dữ liệu. Nếu test tạo file, hãy xóa file. Nếu test gửi message, hãy dùng queue/topic riêng hoặc dọn message. Đóng cả context để giải quyết những trạng thái có phạm vi nhỏ thường làm suite chậm và khó mở rộng.

`@DirtiesContext` cũng không đảm bảo xóa dữ liệu ở hệ thống bên ngoài context. Database, container, file và broker có thể vẫn giữ dữ liệu sau khi context bị đóng.

### 7.2. Cẩn thận khi dùng với test chạy song song

Nếu một test đánh dấu context dirty trong khi test khác đang sử dụng cùng context, việc đóng context có thể gây lỗi khó dự đoán. Với parallel execution, tránh để các test đồng thời chia sẻ context mà một test có thể loại bỏ. Có thể nhóm chúng chạy cùng thread, dùng resource lock phù hợp hoặc thiết kế context riêng cho test thay đổi trạng thái.

## 8. Cô lập dữ liệu và trạng thái trong integration test

Context cache và test instance lifecycle không tự làm sạch mọi thứ. Một `ApplicationContext` được cache có thể chứa singleton bean được nhiều test dùng chung. Vì vậy, cần quản lý dữ liệu theo đúng phạm vi.

### 8.1. Transaction test với database

Spring Test hỗ trợ transaction test-managed qua `@Transactional`:

```java
@SpringBootTest
@Transactional
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customers;

    @Autowired
    private CustomerRepository repository;

    @Test
    void createsCustomerInsideTestTransaction() {
        customers.create("Lan");

        assertThat(repository.findByName("Lan")).isPresent();
    }
}
```

Theo cấu hình mặc định, transaction của test được rollback sau mỗi method. Điều này giúp dữ liệu database không tồn tại qua các test method trong cùng transaction manager.

Tuy nhiên, rollback không áp dụng cho mọi side effect. Email đã gửi, message đã được broker nhận, file đã ghi hoặc request HTTP đã xử lý có thể không được rollback cùng transaction database. Với những tác dụng phụ đó, cần fake, test container, queue riêng hoặc cleanup tương ứng.

### 8.2. Request qua server thật có transaction riêng

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, test method và request HTTP chạy trên các thread khác nhau. Transaction `@Transactional` của test không tự bao quanh transaction trong request server. Nếu endpoint ghi dữ liệu, hãy xóa dữ liệu sau test hoặc dùng fixture có định danh duy nhất và cleanup tường minh.

### 8.3. Không lưu mutable state trong singleton bean nếu không cần

Spring bean mặc định thường có scope singleton. Một bean giữ list, counter hoặc dữ liệu request trong field có thể làm test tác động lẫn nhau khi context được cache. Nếu state thuộc một lần gọi, hãy giữ nó trong biến cục bộ hoặc mô hình hóa scope phù hợp. Nếu state là một phần của ứng dụng, cung cấp API quản lý và reset có ý nghĩa thay vì phụ thuộc vào việc tạo context mới.

## 9. Lỗi nạp context thường gặp và cách xử lý

Khi context không khởi động, stack trace thường có nhiều lớp `BeanCreationException` hoặc `ApplicationContext` failure. Hãy tìm nguyên nhân gốc ở các `Caused by` sâu nhất và đối chiếu với cấu hình test.

### 9.1. Không tìm thấy cấu hình Spring Boot

Thông báo thường gặp:

```text
Unable to find a @SpringBootConfiguration
```

Nguyên nhân có thể là test nằm ngoài package tree của lớp `@SpringBootApplication`, có nhiều cấu hình ứng dụng hoặc module test không phụ thuộc đúng module chứa lớp main.

Cách xử lý:

- Chỉ định `@SpringBootTest(classes = MainApplication.class)` khi cần nạp ứng dụng cụ thể.
- Kiểm tra package và dependency của test module.
- Với test Spring thuần, dùng `@ContextConfiguration(classes = ...)` thay vì yêu cầu Boot tìm main application.

### 9.2. Không tạo được bean hoặc thiếu dependency

Lỗi `NoSuchBeanDefinitionException` thường cho biết context không chứa bean mà test hoặc bean khác yêu cầu. Trong test slice, một service không được nạp có thể là hành vi bình thường.

Hãy xác định test đang dùng full context hay slice. Với slice, import cấu hình cần thiết hoặc mock collaborator của controller/service. Với full context, kiểm tra component scan, điều kiện `@ConditionalOn...`, profile và cấu hình bean.

Không giải quyết mọi lỗi bằng cách chuyển sang `@SpringBootTest`. Nếu test đang kiểm tra controller, bổ sung đúng dependency mock vào `@WebMvcTest` thường giữ phạm vi phù hợp hơn.

### 9.3. Property placeholder không được resolve

Ví dụ lỗi:

```text
Could not resolve placeholder 'external.api.url'
```

Hãy kiểm tra key có trong file cấu hình đang được nạp hay không, profile có được kích hoạt không và test có cần cung cấp inline property hoặc dynamic property không.

```java
@SpringBootTest(properties = "external.api.url=http://localhost:8089")
class ExternalClientIntegrationTest {
}
```

Nếu URL được cấp bởi mock server, đăng ký qua `@DynamicPropertySource` để lấy port sau khi server khởi động.

### 9.4. Nhiều bean cùng kiểu hoặc chọn sai implementation

Khi có nhiều bean cùng kiểu, Spring có thể báo `NoUniqueBeanDefinitionException` hoặc chọn implementation khác với ý định. Dùng `@Qualifier`, `@Primary` hoặc cấu hình test bean rõ ràng. Kiểm tra cả profile và điều kiện tạo bean để biết vì sao implementation đó xuất hiện.

### 9.5. Database connection hoặc migration thất bại

Context có thể không khởi động vì datasource URL sai, container chưa sẵn sàng, credential không đúng hoặc migration lỗi. Hãy kiểm tra property datasource thực tế, trạng thái container và log migration. Nếu test cần database thật, dùng Testcontainers hoặc dịch vụ test được quản lý thay vì dựa vào database cục bộ không được khai báo trong build.

### 9.6. Context đã thất bại trước đó

Trong Spring Framework 6.1 trở lên, TestContext Framework có cơ chế failure threshold cho cùng một context cache key. Mặc định, sau một lần load context thất bại, những lần thử tiếp theo với cùng key có thể bị bỏ qua và báo lỗi cho biết ngưỡng thất bại đã bị vượt qua. Có thể điều chỉnh bằng system property `spring.test.context.failure.threshold`.

Khi thấy thông báo threshold, hãy tìm lỗi load đầu tiên trong log. Những lỗi skip tiếp theo thường là hệ quả của lần thất bại ban đầu, không phải nguyên nhân độc lập. Đừng tăng threshold để che lỗi cấu hình gốc.

## 10. Giữ context cache hiệu quả

Một số lựa chọn giúp giảm số lần khởi động context:

- Dùng chung cấu hình cho các test thực sự có cùng profile, property và bean graph.
- Tránh tạo inline properties khác nhau giữa các class nếu giá trị có thể được điều khiển ở cấp test method.
- Không import một cấu hình mới cho từng class nếu không có nhu cầu riêng.
- Hạn chế thay bean bằng các tập mock khác nhau nếu test có thể kiểm tra collaborator qua unit test hoặc slice riêng.
- Chỉ dùng `@DirtiesContext` khi context cần bị loại khỏi cache.
- Bật log cache khi suite chậm để quan sát hit/miss thay vì đoán.

Không cố ép tất cả test dùng chung một context. Các test cần profile, property, server hoặc bean graph khác nhau có thể cần context riêng. Mục tiêu là tái sử dụng những context tương đương và giữ phạm vi mỗi test rõ ràng.

## 11. Tổ chức base integration test

Một base class có thể gom cấu hình thật sự chung:

```java
@SpringBootTest
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
    @Autowired
    protected TestEntityManager entityManager;
}
```

Các lớp con dùng lại cấu hình:

```java
class CustomerServiceIT extends BaseIntegrationTest {
    @Autowired
    private CustomerService customers;
}

class OrderServiceIT extends BaseIntegrationTest {
    @Autowired
    private OrderService orders;
}
```

Nếu các lớp con có cùng cấu hình đã hợp nhất, Spring có thể tái sử dụng context. Hãy giữ base class tập trung vào cấu hình và tiện ích dùng chung. Tránh đặt quá nhiều setup dữ liệu vào `@BeforeEach` của base class vì mọi subclass sẽ nhận fixture không cần thiết.

Nếu một nhóm test cần profile hoặc property khác, hãy khai báo rõ ở nhóm đó và chấp nhận context key khác khi hành vi thực sự khác. Dùng kế thừa chỉ khi quan hệ cấu hình có ý nghĩa; composition qua `@Import` hoặc test configuration có thể rõ hơn nếu các test chỉ chia sẻ một vài bean.

## 12. Quy trình chẩn đoán một integration test chậm hoặc không khởi động

Khi test gặp vấn đề về context, hãy đi theo thứ tự:

1. Xác định loại test: full application context, context Spring thuần hay test slice.
2. Tìm cấu hình gốc: `classes`, `locations`, main application, profile và initializer.
3. Kiểm tra property: file được nạp, inline properties, dynamic properties và nguồn runtime.
4. Đọc nguyên nhân gốc trong stack trace, đặc biệt bean creation, placeholder, datasource và migration.
5. Nếu context load thành công nhưng suite chậm, bật log `org.springframework.test.context.cache` ở DEBUG để xem cache hit/miss.
6. Tìm `@DirtiesContext`, cấu hình khác nhau giữa test class và các customizer làm cache key thay đổi.
7. Kiểm tra trạng thái singleton, transaction, database và tài nguyên ngoài context có đang bị chia sẻ hay không.
8. Chỉ tăng cache size hoặc tách context khi đã xác định rõ nhu cầu và chi phí.

Quy trình này giúp phân biệt lỗi cấu hình, lỗi dependency, lỗi tài nguyên ngoài và vấn đề tái sử dụng context. Những nguyên nhân này có cách sửa khác nhau; xử lý đúng phạm vi giúp suite ổn định mà không phải mở rộng mọi test thành full application context.

## 13. Bảng chọn annotation theo mục tiêu

| Mục tiêu | Annotation/cơ chế thường phù hợp | Phạm vi được nạp |
|---|---|---|
| Nạp một tập bean Spring cụ thể | `@ContextConfiguration`, `@SpringJUnitConfig` | Các class hoặc resource được chỉ định |
| Nạp ứng dụng Spring Boot | `@SpringBootTest` | Application context theo cấu hình Boot |
| Kiểm tra MVC với mock service | `@WebMvcTest` | Web slice |
| Kiểm tra JPA repository | `@DataJpaTest` | Persistence slice |
| Bổ sung bean dành riêng cho test | `@TestConfiguration`, `@Import` | Cấu hình test bổ sung |
| Chọn cấu hình theo môi trường | `@ActiveProfiles` | Profile tương ứng |
| Nạp property từ file hoặc inline | `@TestPropertySource`, `@SpringBootTest(properties = ...)` | Property source của test |
| Dùng URL/port cấp lúc chạy | `@DynamicPropertySource` | Property lấy từ supplier runtime |
| Xây dựng root/child context | `@ContextHierarchy` | Nhiều cấp `ApplicationContext` |
| Loại context khỏi cache | `@DirtiesContext` | Context bị đánh dấu không thể tái sử dụng |

## 14. Nguyên tắc cần nhớ

- Chọn `@ContextConfiguration`, `@SpringBootTest` hoặc test slice theo đúng phạm vi cần kiểm tra.
- Chỉ định `classes` khi Spring Boot không thể tìm đúng cấu hình ứng dụng hoặc khi test cần một cấu hình cụ thể.
- Dùng profile và property source có chủ đích; dùng `@DynamicPropertySource` cho giá trị chỉ có sau khi tài nguyên test được khởi tạo.
- Context cache tái sử dụng context có cùng cấu hình đã hợp nhất trong cùng JVM; thay đổi profile, property, initializer hoặc customizer có thể tạo cache key mới.
- Dùng `@DirtiesContext` khi trạng thái của chính context không thể khôi phục; quản lý database, file và broker theo cơ chế riêng.
- Test instance mới không đồng nghĩa với Spring context mới; singleton bean trong context được cache có thể được nhiều test cùng sử dụng.
- Transaction rollback giúp cô lập dữ liệu database trong đúng transaction, nhưng không hoàn tác email, message hoặc request đã gửi ra ngoài.
- Khi context load thất bại, tìm nguyên nhân gốc đầu tiên; khi suite chậm, quan sát cache hit/miss và số context thực sự được tạo.

Nắm được cách nạp cấu hình và quản lý vòng đời `ApplicationContext` giúp integration test vừa kiểm tra đúng các thành phần Spring cần thiết, vừa tái sử dụng tài nguyên hiệu quả. Mỗi test class nên thể hiện rõ cấu hình, profile và property mà nó cần; dữ liệu và tác dụng phụ cần được cô lập theo đúng ranh giới; context chỉ nên bị tạo lại khi có lý do cụ thể.
