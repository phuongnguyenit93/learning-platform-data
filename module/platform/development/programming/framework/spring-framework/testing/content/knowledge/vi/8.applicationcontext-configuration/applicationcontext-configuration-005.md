# Lớp cấu hình lồng và phạm vi bean được nạp

Khi kiểm thử Spring, một `ApplicationContext` được tạo từ các lớp cấu hình, component scan, bean import và những nguồn property đã hợp nhất. Cấu hình quyết định **bean nào có mặt trong context**; scope quyết định **mỗi bean được tạo và chia sẻ như thế nào trong context đó**. Hai khái niệm liên quan nhưng không thay thế cho nhau: nạp một bean vào context không có nghĩa mọi test đều nhận một instance mới, và chọn scope `prototype` không làm Spring tự tạo lại toàn bộ context.

Spring Test cho phép khai báo cấu hình ngay bên trong test class bằng static nested configuration class. Spring Boot còn cung cấp `@TestConfiguration` để thêm bean phục vụ test mà vẫn giữ cấu hình ứng dụng chính. Khi hiểu đúng cách phát hiện và import các lớp lồng, ta có thể tạo context gọn, thay collaborator theo từng nhóm test và tránh làm thay đổi cấu hình production. Đồng thời, hiểu bean scope giúp giải thích vì sao một singleton có thể giữ trạng thái qua nhiều test hoặc vì sao request-scoped bean chỉ tồn tại trong một HTTP request.

## 1. Cấu hình quyết định bean nào được nạp

`ApplicationContext` chứa các bean definition và những bean instance được tạo từ các definition đó. Một bean có thể được đưa vào context qua nhiều con đường:

- Khai báo phương thức `@Bean` trong lớp `@Configuration`.
- Quét component bằng `@ComponentScan` hoặc cơ chế component scan của Spring Boot.
- Import lớp cấu hình hoặc component bằng `@Import`.
- Nạp resource XML qua `@ImportResource` hoặc `@ContextConfiguration(locations = ...)`.
- Được đăng ký bởi auto-configuration, `ImportSelector`, registrar hoặc cơ chế mở rộng của Spring.

Trong kiểm thử, các annotation như `@ContextConfiguration`, `@SpringBootTest`, `@WebMvcTest` và `@DataJpaTest` xác định cách tạo context. Cấu hình test có thể bổ sung hoặc thay thế một phần bean graph tùy annotation và cách khai báo.

Ví dụ, một context Spring thuần có thể chỉ nạp các bean được chỉ định:

```java
@Configuration
class BillingConfiguration {
    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}

@Configuration
class BillingTestConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}

@SpringJUnitConfig(classes = {
        BillingConfiguration.class,
        BillingTestConfiguration.class
})
class BillingIntegrationTest {
    @Autowired
    private BillingService billingService;
}
```

Context trên có `BillingService` và implementation `PaymentGateway` được cung cấp bởi cấu hình test. Nó không cần quét toàn bộ package ứng dụng nếu test chỉ cần hai thành phần này.

Một điểm cần nhớ: annotation cấu hình không phải danh sách bean instance đã được tạo ngay lập tức. Spring đăng ký bean definition trước; instance được tạo theo scope và thời điểm khởi tạo của bean. Mặc định, singleton thường được khởi tạo sớm khi context refresh hoàn tất, nhưng bean lazy có thể chỉ được tạo khi lần đầu được yêu cầu.

## 2. Static nested configuration class

Java cho phép khai báo một class bên trong class khác. Với Spring configuration, một static nested class thường được dùng để đặt cấu hình gần test class sử dụng nó:

```java
class CatalogIntegrationTest {
    @Configuration
    static class CatalogTestConfiguration {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }
}
```

Lớp cấu hình lồng nên là `static`. Một inner class không static cần có instance của lớp bao ngoài để được khởi tạo; Spring không tự có một test instance thích hợp để tạo configuration object đó. Static nested class không phụ thuộc instance bên ngoài và có thể được Spring xử lý như một configuration class độc lập.

### 2.1. Cách Spring Test phát hiện cấu hình lồng

Với `@ContextConfiguration`, nếu không khai báo `classes` hoặc `locations`, Spring TestContext Framework có thể dò các static nested class được đánh dấu `@Configuration` trong test class để dùng làm default configuration classes. Điều này cho phép viết:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class CatalogIntegrationTest {
    @Autowired
    private CatalogService catalogService;

    @Configuration
    static class Config {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }

        @Bean
        CatalogService catalogService(CatalogRepository repository) {
            return new CatalogService(repository);
        }
    }
}
```

Khi có nhiều nested configuration class, hãy chỉ định rõ `classes` nếu cần kiểm soát chính xác tập cấu hình hoặc muốn tránh phụ thuộc vào cơ chế dò mặc định. Ví dụ:

```java
@ContextConfiguration(classes = {
        CatalogIntegrationTest.RepositoryConfig.class,
        CatalogIntegrationTest.ServiceConfig.class
})
class CatalogIntegrationTest {
    @Configuration
    static class RepositoryConfig {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }

    @Configuration
    static class ServiceConfig {
        @Bean
        CatalogService catalogService(CatalogRepository repository) {
            return new CatalogService(repository);
        }
    }
}
```

Tách cấu hình theo trách nhiệm có thể hữu ích khi test có nhiều bean. Với một test nhỏ, một nested configuration class thường dễ đọc hơn nhiều lớp cấu hình rời rạc.

### 2.2. `@Configuration` lồng trong `@SpringBootTest`

Trong Spring Boot, nếu test có nested class được đánh dấu `@Configuration`, lớp đó có thể được xem là cấu hình chính cho test thay cho việc tự tìm `@SpringBootConfiguration` của ứng dụng. Điều này có thể vô tình làm test chỉ nạp cấu hình nhỏ trong nested class và bỏ qua auto-configuration hoặc component scan của ứng dụng.

Ví dụ sau có thể khiến người viết nghĩ rằng chỉ thêm một bean giả, nhưng thực tế đã cung cấp một cấu hình thay thế:

```java
@SpringBootTest
class OrderIntegrationTest {
    @Configuration
    static class TestConfig {
        @Bean
        Clock clock() {
            return Clock.systemUTC();
        }
    }
}
```

Nếu mục tiêu là **bổ sung** bean test vào cấu hình Spring Boot chính, dùng `@TestConfiguration`:

```java
@SpringBootTest
class OrderIntegrationTest {
    @Autowired
    private OrderService orderService;

    @TestConfiguration
    static class AdditionalTestConfiguration {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
        }
    }
}
```

`@TestConfiguration` được thiết kế để khai báo cấu hình bổ sung dành cho test. Nó giúp giữ cơ chế tìm cấu hình ứng dụng chính của Spring Boot và thêm bean test vào context. Khi có nhiều bean cùng kiểu, hãy dùng `@Primary` hoặc `@Qualifier` theo ý định injection.

### 2.3. `@TestConfiguration` top-level và `@Import`

Một `@TestConfiguration` top-level thường được import rõ ràng vào test cần dùng:

```java
@TestConfiguration
class FakePaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}

@SpringBootTest
@Import(FakePaymentConfiguration.class)
class PaymentIntegrationTest {
    @Autowired
    private PaymentService paymentService;
}
```

`@TestConfiguration` được đánh dấu như một test component và thường được loại khỏi component scan thông thường. Đây là chủ đích: một fake hoặc test bean không nên vô tình xuất hiện trong context production chỉ vì nằm trong package được scan. `@Import` cho biết test nào chủ động sử dụng cấu hình đó.

Có thể đặt nested `@TestConfiguration` trực tiếp trong test class để phạm vi sử dụng được nhìn thấy ngay tại nơi khai báo. Nếu nhiều test class dùng chung cấu hình, top-level configuration kết hợp `@Import` giúp tránh lặp lại và thể hiện dependency rõ ràng.

## 3. Phân biệt các cách đưa bean vào context

Các annotation có vẻ tương tự nhưng ý nghĩa khác nhau:

| Cơ chế | Tác dụng | Trường hợp phù hợp |
|---|---|---|
| `@ContextConfiguration(classes = ...)` | Chỉ định cấu hình dùng để xây dựng context Spring Test | Spring integration test cần tập cấu hình cụ thể |
| `@SpringBootTest(classes = ...)` | Chỉ định nguồn cấu hình ứng dụng Spring Boot | Cần nạp ứng dụng từ một main configuration cụ thể |
| `@Import(...)` | Đưa thêm configuration hoặc component vào cấu hình hiện tại | Bổ sung bean test hoặc module cấu hình |
| `@TestConfiguration` | Đánh dấu cấu hình bổ sung dành cho test | Fake, clock cố định, adapter in-memory |
| `@ComponentScan` | Quét package để tìm component | Nạp một nhóm component theo package và filter |
| `@ImportResource` | Nạp cấu hình XML | Ứng dụng còn dùng XML hoặc cần kiểm tra cấu hình XML |

Đừng nhầm `@Import` với `@ComponentScan`. Import thêm một kiểu cấu hình đã biết; component scan tìm nhiều component trong một vùng package theo filter. Với test, import rõ ràng thường giúp context nhỏ và dễ giải thích hơn.

### 3.1. Component scan có thể nạp nhiều bean hơn dự kiến

Một cấu hình test có `@ComponentScan` rộng có thể kéo theo các adapter, client hoặc cấu hình production mà test không cần:

```java
@Configuration
@ComponentScan("com.example")
class BroadTestConfiguration {
}
```

Nếu package gốc chứa nhiều module, context có thể cần datasource, HTTP client hoặc property mà test không định dùng. Hãy giới hạn package hoặc dùng filter:

```java
@Configuration
@ComponentScan(
        basePackages = "com.example.catalog",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = RemoteCatalogClient.class))
class CatalogTestConfiguration {
}
```

Trong nhiều trường hợp, khai báo `@Bean` hoặc `@Import` cho một vài thành phần cụ thể dễ hiểu hơn scan package lớn rồi loại bỏ từng bean.

### 3.2. Điều kiện tạo bean

Bean có thể chỉ được đăng ký khi điều kiện thỏa mãn, ví dụ `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnClass` hoặc custom condition. Vì vậy, việc một class nằm trong component scan không đảm bảo bean luôn xuất hiện.

```java
@Configuration
@Profile("integration")
class IntegrationGatewayConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Nếu bean bị thiếu, hãy kiểm tra profile và điều kiện trước khi thêm một bean trùng kiểu vào test. Hai bean cùng tồn tại có thể gây `NoUniqueBeanDefinitionException` hoặc khiến Spring chọn nhầm implementation.

## 4. Lớp cấu hình lồng trong JUnit `@Nested` test

Một nested configuration class và một JUnit `@Nested` test class là hai khái niệm khác nhau:

- Nested configuration class là class Java bên trong một class khác, thường `static`, được Spring dùng để đăng ký bean.
- JUnit `@Nested` class là nhóm test lồng bên trong test class khác, thường không static và có vòng đời test riêng theo JUnit.

Spring Test có annotation `@NestedTestConfiguration` để điều khiển việc các nested test class kế thừa cấu hình từ enclosing test class như thế nào. Mặc định là `INHERIT`, nghĩa là cấu hình Spring từ class bao ngoài được kế thừa vào nested test class theo quy tắc tương ứng.

Ví dụ:

```java
@SpringBootTest
class CustomerIntegrationTest {
    @Autowired
    CustomerService customers;

    @Nested
    class WhenCustomerExists {
        @Test
        void loadsCustomer() {
            assertThat(customers).isNotNull();
        }
    }

    @Nested
    class WhenCustomerIsMissing {
        @Test
        void handlesMissingCustomer() {
            assertThat(customers).isNotNull();
        }
    }
}
```

Hai nhóm test dùng chung cấu hình Spring từ class bao ngoài. Chúng không tự động nhận một `ApplicationContext` riêng chỉ vì được đặt trong hai nested class.

Nếu muốn nested test class không kế thừa cấu hình từ enclosing class, có thể dùng:

```java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class CustomerIntegrationTest {
    @Nested
    @SpringBootTest(classes = CustomerOnlyTestApplication.class)
    class IsolatedCustomerConfigurationTest {
        // Cấu hình của nested test class được dùng độc lập.
    }
}
```

`OVERRIDE` làm nested test class tự khai báo cấu hình của nó thay vì kế thừa cấu hình enclosing. Cơ chế này hữu ích khi một nhóm test lồng cần context khác hẳn. Không dùng nó chỉ để chia nhóm theo tên hoặc trạng thái nghiệp vụ nếu các test vẫn cần cùng bean graph.

Có thể cấu hình mặc định cho toàn dự án qua thuộc tính `spring.test.enclosing.configuration` trong `junit-platform.properties`, hoặc khai báo annotation tại vị trí phù hợp. Nếu thay đổi mặc định, hãy đảm bảo IDE và CI cùng nạp cấu hình đó.

## 5. Bean scope là gì?

Scope xác định vòng đời và phạm vi chia sẻ của một bean instance. Trong Spring, scope mặc định là `singleton`. Một bean singleton được tạo một lần cho mỗi bean definition trong một `ApplicationContext` và được chia sẻ khi các thành phần yêu cầu bean đó.

Các scope phổ biến:

| Scope | Ý nghĩa | Nơi thường sử dụng |
|---|---|---|
| `singleton` | Một instance cho mỗi bean definition trong một container | Service stateless, repository, cấu hình |
| `prototype` | Tạo instance mới mỗi lần container resolve bean | Đối tượng có trạng thái ngắn hạn do caller quản lý |
| `request` | Một instance trong vòng đời một HTTP request | Dữ liệu gắn với một request |
| `session` | Một instance trong vòng đời HTTP session | Trạng thái theo phiên người dùng |
| `application` | Một instance trong phạm vi `ServletContext` | Trạng thái web application |
| `websocket` | Một instance trong vòng đời WebSocket session | Trạng thái theo kết nối WebSocket |
| custom scope | Vòng đời do ứng dụng hoặc extension định nghĩa | Nhu cầu đặc thù của ứng dụng |

`singleton` không có nghĩa là một instance duy nhất cho toàn bộ JVM. Hai `ApplicationContext` khác nhau có thể tạo hai singleton instance khác nhau cho cùng một class/bean name. Tương tự, test dùng context cache có thể nhìn thấy cùng singleton instance qua nhiều test class nếu chúng dùng chung context.

## 6. Singleton scope và ảnh hưởng đến test

Nếu không khai báo scope, bean mặc định là singleton:

```java
@Component
class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    int next() {
        return count.incrementAndGet();
    }
}
```

```java
@Configuration
class CounterConfiguration {
    @Bean
    RequestCounter requestCounter() {
        return new RequestCounter();
    }
}
```

Trong cùng context, những nơi inject `RequestCounter` sẽ nhận cùng một instance. Điều này phù hợp với service stateless hoặc bean quản lý tài nguyên dùng chung, nhưng có thể gây rò rỉ trạng thái nếu bean giữ dữ liệu mutable theo từng test hoặc từng request.

Test minh họa identity của singleton:

```java
@SpringJUnitConfig(CounterConfiguration.class)
class SingletonScopeTest {
    @Autowired
    private RequestCounter firstReference;

    @Autowired
    private RequestCounter secondReference;

    @Test
    void injectsTheSameSingletonInstance() {
        assertThat(firstReference).isSameAs(secondReference);
    }
}
```

Trong test suite, Spring có thể cache context và tái sử dụng giữa các class có cấu hình tương đương. Nếu một test tăng counter lên 5, test tiếp theo có thể nhìn thấy giá trị đó nếu cùng context và bean không được reset.

Giải pháp tốt thường là giữ singleton bean stateless, chuyển state theo lần gọi vào tham số hoặc object cục bộ, hoặc cung cấp cơ chế reset rõ ràng cho fixture test. `@DirtiesContext` chỉ nên dùng khi chính context bị thay đổi và không thể khôi phục; nó không phải cách dọn mọi dữ liệu.

## 7. Prototype scope

Prototype tạo một instance mới mỗi lần bean được yêu cầu từ container:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class ReportDraft {
    private final List<String> lines = new ArrayList<>();

    void addLine(String line) {
        lines.add(line);
    }

    List<String> lines() {
        return List.copyOf(lines);
    }
}
```

Mỗi lần gọi `applicationContext.getBean(ReportDraft.class)` sẽ nhận một instance mới:

```java
@Test
void createsANewPrototypeInstanceForEachLookup() {
    ReportDraft first = context.getBean(ReportDraft.class);
    ReportDraft second = context.getBean(ReportDraft.class);

    assertThat(first).isNotSameAs(second);
}
```

Prototype phù hợp khi cần object có trạng thái riêng và caller chịu trách nhiệm vòng đời sau khi nhận. Spring tạo và cấu hình bean nhưng không quản lý đầy đủ destruction callback cho prototype như singleton; caller cần giải phóng tài nguyên mà prototype sở hữu.

### 7.1. Prototype được inject vào singleton

Một lỗi thường gặp là inject prototype trực tiếp vào singleton:

```java
@Component
class ReportService {
    private final ReportDraft draft;

    ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
```

`ReportService` là singleton. Khi singleton được tạo, Spring resolve dependency `ReportDraft` một lần và giữ instance đó trong field. Việc `ReportDraft` có scope prototype không khiến Spring tự thay field bằng instance mới mỗi lần gọi method.

Nếu cần prototype mới theo từng thao tác, hãy dùng `ObjectProvider`:

```java
@Component
class ReportService {
    private final ObjectProvider<ReportDraft> drafts;

    ReportService(ObjectProvider<ReportDraft> drafts) {
        this.drafts = drafts;
    }

    ReportDraft newDraft() {
        return drafts.getObject();
    }
}
```

Mỗi lần gọi `getObject()` sẽ resolve bean theo scope, nên với prototype sẽ nhận instance mới. Có thể dùng `ObjectFactory`, `Provider` hoặc scoped proxy tùy nhu cầu, nhưng `ObjectProvider` thường thuận tiện trong Spring vì hỗ trợ các thao tác resolve bổ sung.

## 8. Request và session scope

Web scope cần một web-aware `ApplicationContext` và ngữ cảnh HTTP phù hợp. `request` tạo một bean instance cho mỗi HTTP request; `session` tạo một instance cho mỗi HTTP session.

```java
@Component
@RequestScope
class RequestMetadata {
    private String correlationId;

    void setCorrelationId(String value) {
        this.correlationId = value;
    }

    String correlationId() {
        return correlationId;
    }
}
```

`@RequestScope` là cách viết gọn cho bean có scope request và mặc định dùng scoped proxy phù hợp để bean request-scoped có thể được inject vào singleton. Proxy sẽ resolve target instance theo request hiện tại.

Một ví dụ session scope:

```java
@Component
@SessionScope
class ShoppingSession {
    private final List<String> itemIds = new ArrayList<>();

    void add(String itemId) {
        itemIds.add(itemId);
    }

    List<String> items() {
        return List.copyOf(itemIds);
    }
}
```

Không inject trực tiếp một request/session object không có proxy vào singleton theo cách làm target được resolve quá sớm. Dùng `@RequestScope`/`@SessionScope` với scoped proxy mặc định hoặc một provider phù hợp để target được lấy khi request/session đang hoạt động.

### 8.1. Kiểm tra request scope

Khi test request-scoped bean, phải có request context. `MockMvc` hoặc web test environment có thể thiết lập request lifecycle phù hợp cho luồng MVC. Nếu gọi service trực tiếp trong một unit test không có request, truy cập request-scoped bean có thể gây `ScopeNotActiveException` hoặc lỗi tương đương.

Với Spring MVC, có thể kiểm tra qua hai request riêng để chứng minh mỗi request nhận target riêng. Ví dụ minh họa:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RequestMetadataIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void createsRequestScopedMetadataForEachRequest() throws Exception {
        mockMvc.perform(get("/test/request-id"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/test/request-id"))
                .andExpect(status().isOk());
    }
}
```

Để xác nhận hai target khác nhau, endpoint test có thể trả một correlation ID được tạo trong request hoặc một định danh instance chỉ dành cho test. Không so sánh proxy object bằng `isNotSameAs`, vì proxy có thể là cùng một object Java trong khi target phía sau thay đổi theo request.

### 8.2. Kiểm tra session scope

Session scope tồn tại qua nhiều request thuộc cùng session. Khi kiểm thử, phải gửi lại cùng session cookie hoặc dùng cơ chế giữ session của MockMvc. Hai request không có chung session sẽ nhận hai session-scoped target khác nhau; hai request có cùng session sẽ dùng cùng target trong vòng đời session.

Không giả định mỗi request đều tạo session mới hoặc session tự bị xóa khi test kết thúc. Hãy quản lý session/cookie rõ ràng và dọn state theo test.

## 9. Application scope và WebSocket scope

Application scope gắn với `ServletContext` của web application. Nó có vòng đời rộng hơn một request hoặc session nhưng vẫn khác singleton scope: singleton thuộc một bean definition trong một `ApplicationContext`, còn application scope thuộc `ServletContext`.

Trong ứng dụng có nhiều web application context hoặc nhiều servlet context, sự khác biệt này có thể quan trọng. Không dùng application scope chỉ vì muốn chia sẻ dữ liệu toàn JVM; nếu mục tiêu là một bean dùng chung trong một Spring context, singleton thường phù hợp.

WebSocket scope gắn với một WebSocket session. Bean được tạo trong session và có thể được dùng trong các message xử lý thuộc cùng kết nối. Test scope này cần thiết lập lifecycle WebSocket session thực hoặc môi trường test hỗ trợ; khởi tạo service trực tiếp không tạo ra WebSocket context.

Các web scope chỉ hoạt động khi scope tương ứng đã được đăng ký và context đang có request/session/WebSocket context hoạt động. Nếu test không có môi trường đó, lỗi scope không active thường là dấu hiệu test đang chạy sai loại context hoặc chưa thiết lập lifecycle cần thiết.

## 10. Khai báo scope trên `@Bean`

Scope có thể được khai báo trên component bằng `@Scope`, hoặc trên phương thức `@Bean`:

```java
@Configuration
class DraftConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ReportDraft reportDraft() {
        return new ReportDraft();
    }
}
```

Mặc định, bean khai báo bằng `@Bean` cũng là singleton. Nếu cần request hoặc session scope, có thể dùng annotation scope tương ứng:

```java
@Bean
@RequestScope
RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

### 10.1. `proxyMode` và scoped proxy

Khi bean có scope ngắn hơn bean phụ thuộc vào nó, chẳng hạn request-scoped bean được inject vào singleton, scoped proxy cho phép singleton giữ một proxy ổn định và proxy resolve target theo scope đang hoạt động.

Có thể khai báo proxy mode tường minh:

```java
@Bean
@Scope(value = WebApplicationContext.SCOPE_REQUEST,
       proxyMode = ScopedProxyMode.TARGET_CLASS)
RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

`TARGET_CLASS` dùng proxy dựa trên class; `INTERFACES` dùng proxy dựa trên interface và yêu cầu bean có interface phù hợp. Các annotation `@RequestScope` và `@SessionScope` mặc định đã cấu hình scoped proxy theo cách thông dụng. Không cần thêm proxy mode nếu mặc định đáp ứng nhu cầu.

Scoped proxy không làm scope target biến thành singleton. Proxy là đối tượng được inject; target thật vẫn được resolve theo request/session hiện tại. Vì vậy, hai field có thể cùng giữ một proxy reference nhưng nhận target khác nhau ở các scope khác nhau.

## 11. `@Configuration` full mode và `proxyBeanMethods`

`@Configuration` mặc định dùng cơ chế proxy cho các phương thức `@Bean` để một lời gọi giữa các phương thức bean trong cùng configuration class được điều phối qua container. Điều này giúp duy trì singleton semantics:

```java
@Configuration
class ServiceConfiguration {
    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

Với cấu hình proxy mặc định, lời gọi `repository()` trong `service()` được xử lý bởi Spring và trả về bean singleton đã đăng ký, thay vì tạo một repository độc lập ngoài container.

Nếu đặt `proxyBeanMethods = false`, configuration dùng chế độ không proxy (lite behavior): lời gọi trực tiếp giữa các phương thức Java là lời gọi thông thường. Khi đó, `service()` gọi `repository()` có thể tạo một instance mới thay vì lấy bean do container quản lý. Để tránh nhầm lẫn, dùng method parameter injection:

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfiguration {
    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }
}
```

Spring resolve tham số `Repository` từ context. Cách viết này hoạt động rõ ràng với cả cấu hình proxy và không proxy, đồng thời thể hiện dependency giữa các bean.

Khi test một nested configuration class, hãy lưu ý `proxyBeanMethods` nếu các phương thức `@Bean` gọi lẫn nhau. Một test có thể thấy hai instance khác nhau dù bean definition mặc định là singleton nếu code tự gọi method trong cấu hình lite mode.

## 12. Bean scope và context cache trong Spring Test

Context cache tái sử dụng `ApplicationContext` giữa các test có cấu hình tương đương trong cùng JVM. Vì singleton scope gắn với bean definition trong context, singleton instance cũng được chia sẻ trong suốt thời gian context được tái sử dụng.

Điều đó có nghĩa:

- `PER_METHOD` của JUnit tạo test instance mới cho từng method, nhưng không tạo Spring context mới.
- `PER_CLASS` giữ một test instance cho class, nhưng không tự thay đổi scope của bean Spring.
- Singleton bean trong context cache có thể được nhiều test class cùng sử dụng.
- Prototype bean được resolve lại mỗi lần yêu cầu từ container, nhưng prototype đã inject trực tiếp vào singleton vẫn có thể bị giữ lại trong field singleton.
- Request/session bean cần đúng web scope đang hoạt động; context cache không tạo request hoặc session cho test.

Nếu test làm thay đổi singleton state và không thể reset, `@DirtiesContext` có thể đánh dấu context cần loại khỏi cache. Tuy nhiên, nếu chỉ cần xóa dữ liệu database hoặc message, hãy dùng transaction/cleanup tương ứng. Đóng context không tự xóa dữ liệu ở hệ thống ngoài.

## 13. Kiểm tra bean scope bằng `ApplicationContext`

Với singleton và prototype, có thể viết test tập trung vào hành vi scope:

```java
@SpringJUnitConfig(ScopeTestConfiguration.class)
class BeanScopeTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void singletonReturnsTheSameInstance() {
        Object first = context.getBean("sharedComponent");
        Object second = context.getBean("sharedComponent");

        assertThat(first).isSameAs(second);
    }

    @Test
    void prototypeReturnsDifferentInstances() {
        Object first = context.getBean("draftComponent");
        Object second = context.getBean("draftComponent");

        assertThat(first).isNotSameAs(second);
    }
}

@Configuration
class ScopeTestConfiguration {
    @Bean("sharedComponent")
    Object sharedComponent() {
        return new Object();
    }

    @Bean("draftComponent")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Object draftComponent() {
        return new Object();
    }
}
```

Test trên kiểm tra scope qua container lookup trực tiếp. Với request/session scope, cần web context và request/session lifecycle; không thể thay bằng cách gọi `getBean()` trong một context không có web scope đang hoạt động.

Nếu cần xác nhận bean có được nạp hay không, có thể dùng `containsBean`, `getBeanNamesForType` hoặc autowire dependency. Tuy nhiên, test nên ưu tiên hành vi của thành phần sử dụng bean thay vì kiểm tra danh sách mọi bean nội bộ của context, trừ khi chính cấu hình là đối tượng cần kiểm thử.

## 14. Những lỗi thường gặp

### Dùng nested `@Configuration` khi chỉ muốn bổ sung bean

Trong `@SpringBootTest`, nested `@Configuration` có thể thay thế nguồn cấu hình chính được tìm tự động. Nếu muốn thêm bean test vào ứng dụng, dùng nested `@TestConfiguration` hoặc import một test configuration rõ ràng.

### Khai báo nested configuration không static

Inner class không static cần instance của lớp bao ngoài. Dùng static nested class để Spring có thể khởi tạo configuration độc lập.

### Quét package quá rộng

`@ComponentScan` có thể kéo vào client, datasource hoặc cấu hình production không liên quan. Giới hạn package/filter hoặc import bean cần thiết.

### Nghĩ rằng `singleton` là một instance cho toàn JVM

Singleton được định nghĩa theo bean definition trong một container. Hai context riêng có thể có hai instance; context cache có thể làm nhiều test cùng nhìn thấy một instance.

### Inject prototype vào singleton và mong mỗi lần gọi có instance mới

Dependency được resolve khi singleton được tạo. Dùng `ObjectProvider<T>` hoặc provider tương ứng để yêu cầu prototype mới tại thời điểm cần.

### Truy cập request scope khi không có request

Unit test gọi service trực tiếp có thể không có request context. Dùng web test phù hợp hoặc thiết kế abstraction để logic nghiệp vụ không phụ thuộc trực tiếp vào request-scoped state.

### Dùng `@DirtiesContext` để dọn database

Context bị đóng không đồng nghĩa dữ liệu database, file hoặc broker bị xóa. Dùng transaction rollback hoặc cleanup đúng tài nguyên.

### Gọi trực tiếp phương thức `@Bean` trong lite configuration

Khi `proxyBeanMethods = false`, lời gọi Java trực tiếp có thể tạo instance mới. Dùng method parameter injection để Spring cung cấp bean dependency.

## 15. Quy trình chọn cấu hình và scope

Khi thiết kế test context, hãy trả lời các câu hỏi theo thứ tự:

1. Test cần toàn bộ ứng dụng, một slice hay chỉ một tập bean cụ thể?
2. Cấu hình chính đến từ `@SpringBootTest`, `@ContextConfiguration` hay một test configuration được import?
3. Nested class đang dùng là configuration class hay JUnit `@Nested` test class?
4. Nếu dùng Spring Boot, nested class có cần thay thế cấu hình chính hay chỉ bổ sung bean? Chọn `@Configuration` hoặc `@TestConfiguration` đúng mục đích.
5. Bean nào được tạo qua `@Bean`, component scan, import, profile hoặc condition?
6. Scope của mỗi bean có phù hợp với vòng đời dữ liệu mà nó giữ không?
7. Có singleton mutable nào bị chia sẻ qua context cache không?
8. Có prototype được inject vào singleton và cần provider để resolve nhiều lần không?
9. Web-scoped bean có được truy cập trong request/session context hợp lệ không?
10. Test cần cleanup state ở cấp method, request, session, context hay hệ thống bên ngoài?

Một context test tốt chỉ nạp những bean cần thiết cho hành vi đang kiểm tra. Configuration class làm rõ nguồn bean definition; scope làm rõ vòng đời instance; cleanup bảo đảm dữ liệu không rò rỉ sang kịch bản khác. Khi ba phần này được thiết kế tường minh, test tích hợp sẽ dễ đọc và dễ dự đoán hơn.

## 16. Nguyên tắc cần nhớ

- Cấu hình quyết định bean definition nào được nạp; scope quyết định instance được tạo và chia sẻ ra sao.
- Static nested `@Configuration` có thể được Spring Test phát hiện làm cấu hình mặc định khi không chỉ định nguồn cấu hình rõ ràng.
- Trong Spring Boot, dùng `@TestConfiguration` khi muốn bổ sung bean test mà vẫn giữ cấu hình ứng dụng chính.
- Dùng `@Import` để đưa test configuration top-level vào đúng test; tránh component scan quá rộng.
- `@Nested` của JUnit khác nested configuration class; `@NestedTestConfiguration` điều khiển việc kế thừa cấu hình từ enclosing test class.
- Singleton là một instance theo bean definition trong một `ApplicationContext`, không phải một instance toàn JVM.
- Prototype tạo instance mới khi container resolve bean; inject trực tiếp vào singleton không làm dependency tự thay đổi mỗi lần gọi.
- Request/session/application/WebSocket scope cần đúng web context và vòng đời tương ứng.
- Context cache có thể khiến singleton bean được chia sẻ giữa nhiều test; JUnit tạo test instance mới không đồng nghĩa Spring tạo context mới.
- Dùng `@DirtiesContext` khi context thực sự không thể tái sử dụng; cleanup database, file và broker bằng cơ chế riêng.

Lớp cấu hình lồng giúp đặt cấu hình test gần nơi sử dụng, còn bean scope giúp xác định rõ thời gian sống và phạm vi chia sẻ của từng dependency. Kết hợp hai cơ chế đúng cách sẽ tạo được `ApplicationContext` vừa đủ, tránh nạp nhầm bean production và giữ cho trạng thái giữa các test được kiểm soát.
