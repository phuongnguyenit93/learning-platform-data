# DynamicPropertyRegistry và giá trị được cung cấp động

Kiểm thử tích hợp thường cần cấu hình chỉ biết được khi tài nguyên test đã khởi động. Một PostgreSQL container có thể được ánh xạ ra cổng ngẫu nhiên; mock HTTP server có thể chọn port còn trống; một broker test có thể tạo địa chỉ kết nối riêng cho từng lần chạy. Nếu ghi cứng những giá trị này vào `application-test.yml`, test sẽ phụ thuộc vào môi trường hoặc dễ xung đột cổng.

Spring Test cung cấp `@DynamicPropertySource` và `DynamicPropertyRegistry` để đăng ký property từ các supplier. Test khai báo tên property cùng một `Supplier`, rồi Spring đưa các giá trị đó vào `Environment` khi tạo `ApplicationContext`. Cách này kết nối cấu hình ứng dụng với tài nguyên có địa chỉ chỉ xuất hiện ở runtime, đồng thời giữ test tự mô tả được nguồn cấu hình của nó.

## 1. Vì sao cần property động?

Property thông thường thường đến từ file cấu hình, biến môi trường, JVM system property hoặc tham số chạy test. Chúng phù hợp với những giá trị ổn định như feature flag, timeout, profile hay tên schema. Nhưng có những giá trị chỉ được biết sau khi một dependency test khởi động:

- JDBC URL và cổng của database container.
- Host/port của mock HTTP server.
- Bootstrap server của Kafka hoặc địa chỉ của một message broker test.
- Endpoint của dịch vụ giả lập được khởi động trên cổng ngẫu nhiên.
- Thư mục tạm, token test hoặc thông tin kết nối được cấp lúc runtime.

Ví dụ, Testcontainers có thể cấp cổng host khác nhau ở mỗi lần chạy. Nếu cấu hình ghi cứng `localhost:5432`, test có thể kết nối nhầm database cục bộ hoặc thất bại khi cổng đó đang được sử dụng.

`@DynamicPropertySource` giải quyết vấn đề bằng cách đăng ký một supplier lấy giá trị từ chính tài nguyên đang chạy:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

Ở đây, `postgres::getJdbcUrl` là method reference phù hợp với `Supplier`. Spring gọi supplier khi property được truy xuất. Vì vậy, phương thức đăng ký có thể được thực hiện trước khi giá trị cuối cùng cần được đọc, miễn là tài nguyên đã sẵn sàng tại thời điểm supplier được gọi.

## 2. `@DynamicPropertySource` và `DynamicPropertyRegistry`

`@DynamicPropertySource` là annotation của Spring TestContext Framework. Nó đánh dấu một phương thức dùng để thêm các property động vào `Environment` của test `ApplicationContext`.

Phương thức được đánh dấu phải:

- Là `static`.
- Nhận đúng một tham số kiểu `DynamicPropertyRegistry`.
- Đăng ký property bằng `registry.add(name, supplier)`.
- Được đặt trong test class hoặc một superclass/enclosing class phù hợp để Spring Test phát hiện.

`DynamicPropertyRegistry` cung cấp phương thức `add(String name, Supplier<Object> valueSupplier)`. Tên property là chuỗi mà ứng dụng đọc qua `@Value`, `Environment` hoặc `@ConfigurationProperties`; supplier trả về giá trị cần cung cấp.

Ví dụ đơn giản:

```java
@SpringBootTest
class FeatureConfigurationTest {
    @DynamicPropertySource
    static void featureProperties(DynamicPropertyRegistry registry) {
        registry.add("feature.checkout.enabled", () -> true);
        registry.add("feature.checkout.max-items", () -> 12);
        registry.add("feature.checkout.label", () -> "integration-test");
    }

    @Autowired
    private Environment environment;

    @Test
    void readsDynamicallyRegisteredProperties() {
        assertThat(environment.getProperty("feature.checkout.enabled", Boolean.class))
                .isTrue();
        assertThat(environment.getProperty("feature.checkout.max-items", Integer.class))
                .isEqualTo(12);
        assertThat(environment.getProperty("feature.checkout.label"))
                .isEqualTo("integration-test");
    }
}
```

Spring có thể chuyển đổi kiểu dữ liệu khi đọc property qua `Environment` hoặc bind vào `@ConfigurationProperties`. Supplier trả về `Object`, do đó có thể cung cấp chuỗi, số, boolean hoặc kiểu giá trị phù hợp với property consumer.

### 2.1. Supplier được đánh giá khi cần

Khác với việc tự gọi `getJdbcUrl()` rồi lưu chuỗi vào một biến ngay trong phương thức cấu hình, đăng ký method reference giữ lại hành động lấy giá trị:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
```

Supplier giúp property lấy được giá trị sau khi tài nguyên đã khởi động và sẵn sàng cung cấp endpoint. Đây là lý do dynamic property phù hợp với cổng được cấp ngẫu nhiên.

Có thể đăng ký bằng lambda:

```java
registry.add("catalog.api.base-url", () -> mockServer.url("/").toString());
```

Hoặc method reference:

```java
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
```

Chọn cách viết làm rõ thời điểm lấy giá trị và nguồn dữ liệu. Không tính sẵn URL từ một port chưa được cấp hoặc từ một container chưa khởi động.

### 2.2. Đăng ký nhiều property liên quan

Một tài nguyên thường cung cấp nhiều property. Ví dụ, database container cung cấp URL, username và password. Hãy đăng ký chúng cùng một nơi để người đọc thấy chúng cùng thuộc một dependency:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Với một mock service, có thể đăng ký URL và một số cờ điều khiển:

```java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", catalogServer::baseUrl);
    registry.add("catalog.client.connect-timeout", () -> "2s");
    registry.add("catalog.client.enabled", () -> true);
}
```

Các tên property phải trùng với key mà ứng dụng đang đọc. Nếu service dùng `catalog.client.url` nhưng test đăng ký `catalog.client.base-url`, property sẽ không được áp dụng dù phương thức đăng ký chạy thành công.

## 3. Kết hợp với Testcontainers

Testcontainers khởi động các dependency thật trong container để integration test kiểm tra driver, SQL, migration và giao thức thực tế. Địa chỉ kết nối thường được biết sau khi container chạy, nên `@DynamicPropertySource` là cách phổ biến để truyền các giá trị đó vào Spring.

Ví dụ với PostgreSQL:

```java
@SpringBootTest
@Testcontainers
class CustomerRepositoryIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("customers")
                    .withUsername("test-user")
                    .withPassword("test-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private CustomerRepository customers;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = customers.save(new Customer("Lan"));

        assertThat(customers.findById(saved.id()))
                .get()
                .extracting(Customer::name)
                .isEqualTo("Lan");
    }
}
```

`@Container` đánh dấu container được quản lý bởi Testcontainers JUnit Jupiter extension. Vì field là `static`, container có vòng đời cấp class theo quy ước của extension. `@DynamicPropertySource` đăng ký supplier lấy JDBC URL và credential từ container đó. Khi Spring tạo datasource, các property được đọc từ container đã khởi động.

Ví dụ giả định dự án đã khai báo dependency Testcontainers phù hợp, gồm module PostgreSQL và integration JUnit Jupiter. Phiên bản dependency cần tương thích với Spring Boot, JUnit và Testcontainers mà dự án đang sử dụng.

### 3.1. Container cấp class và container cấp method

Testcontainers JUnit Jupiter hỗ trợ container static và instance:

- Container `static` được khởi động một lần cho class và dừng sau class.
- Container instance được khởi động cho từng test method và dừng sau method tương ứng.

Dynamic property method phải là `static`, vì vậy mô hình thông dụng là static container dùng chung cho test class. Nếu mỗi method cần một container riêng, hãy cân nhắc một cách quản lý tài nguyên khác hoặc thiết kế test sao cho property/context có vòng đời tương thích. Một Spring `ApplicationContext` không tự được tạo lại cho từng test method chỉ vì container instance thay đổi.

Không nên thay đổi endpoint của container trong khi context đang dùng datasource đã được tạo từ endpoint cũ. Context và dependency của nó cần có vòng đời tương thích.

### 3.2. Spring Boot `@ServiceConnection` là lựa chọn khác

Trong các phiên bản Spring Boot hỗ trợ Testcontainers service connections, `@ServiceConnection` có thể tự cấu hình một số loại connection factory phổ biến mà không cần tự đăng ký từng property datasource. Cơ chế này tiện lợi khi dùng loại container được Spring Boot nhận diện.

`@DynamicPropertySource` vẫn hữu ích khi:

- Ứng dụng cần property có tên riêng không thuộc service connection chuẩn.
- Dependency không được `@ServiceConnection` hỗ trợ.
- Test cần cung cấp nhiều giá trị runtime tùy biến.
- Muốn kiểm soát rõ ràng cách property được ánh xạ vào `Environment`.

Không cần dùng đồng thời hai cơ chế cho cùng một property nếu chúng tạo ra cấu hình trùng hoặc khó xác định nguồn thắng. Chọn cơ chế phù hợp với loại dependency và phiên bản Spring Boot của dự án.

## 4. Kết nối mock HTTP server

Một service client thường nhận base URL từ property:

```java
@ConfigurationProperties(prefix = "catalog.client")
record CatalogClientProperties(URI baseUrl) {
}

@Component
class CatalogClient {
    private final WebClient webClient;

    CatalogClient(CatalogClientProperties properties,
                  WebClient.Builder builder) {
        this.webClient = builder.baseUrl(properties.baseUrl().toString()).build();
    }
}
```

Trong integration test, một mock server có thể khởi động trên cổng ngẫu nhiên. Test đăng ký URL thực tế qua dynamic property để Spring bind vào `CatalogClientProperties`.

```java
@SpringBootTest
class CatalogClientIntegrationTest {
    static final MockWebServer server = new MockWebServer();

    static {
        try {
            server.start();
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url",
                () -> URI.create(server.url("/").toString()));
    }

    @AfterAll
    static void stopServer() throws IOException {
        server.shutdown();
    }

    @Autowired
    private CatalogClient client;

    @Test
    void callsConfiguredCatalogEndpoint() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""{"id":"item-42","name":"Keyboard"}"""));

        CatalogItem item = client.findById("item-42");

        assertThat(item.name()).isEqualTo("Keyboard");
        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getPath()).isEqualTo("/items/item-42");
    }
}
```

Ví dụ dùng static initializer để server sẵn sàng trước khi Spring cần đọc property. Trong dự án thật, có thể dùng một JUnit extension hoặc fixture quản lý vòng đời server; điều quan trọng là server phải được khởi động trước khi supplier được đánh giá và phải dừng sau khi test class hoàn tất.

Tên property `catalog.client.base-url` cần tương ứng với cách bind của `CatalogClientProperties`. Nếu record dùng `URI baseUrl`, Spring Boot Configuration Properties sẽ bind key `base-url` vào component `baseUrl` theo relaxed binding.

Không dùng một URL giả định như `http://localhost:8080` khi mock server có thể cấp port ngẫu nhiên. URL động giúp tránh xung đột với tiến trình khác và làm test độc lập hơn với cấu hình máy.

## 5. Thứ tự ưu tiên của dynamic property

Dynamic property source có độ ưu tiên cao trong `Environment`. Các property được đăng ký bằng `@DynamicPropertySource` được ưu tiên hơn các nguồn thông thường như:

- `@TestPropertySource`.
- JVM system properties.
- Environment variables của hệ điều hành.
- Property source khai báo trong ứng dụng, ví dụ `application.properties` hoặc `application.yml`.

Điều này cho phép test ghi đè endpoint production mặc định bằng địa chỉ của container hoặc mock server. Ví dụ, file `application.yml` có thể chứa:

```yaml
catalog:
  client:
    base-url: https://catalog.example.test
```

Test có thể cung cấp endpoint runtime:

```java
@DynamicPropertySource
static void catalogProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", mockServer::baseUrl);
}
```

Khi ứng dụng đọc property này trong test context, giá trị dynamic sẽ được ưu tiên. Tuy vậy, nên đăng ký đúng key và chỉ ghi đè những giá trị cần thiết. Một property dynamic không tự động thay mọi property có cùng prefix.

### 5.1. Kiểm tra giá trị thực tế trong `Environment`

Khi không chắc property nào đang thắng, có thể inject `Environment` và đọc trực tiếp key:

```java
@Autowired
private Environment environment;

@Test
void usesContainerJdbcUrl() {
    String url = environment.getRequiredProperty("spring.datasource.url");

    assertThat(url).isEqualTo(postgres.getJdbcUrl());
}
```

Trong một test cấu hình, assertion này xác nhận giá trị property đã đăng ký. Nếu mục tiêu là kiểm tra datasource thật, hãy thực hiện một truy vấn hoặc lưu/đọc dữ liệu qua repository để xác nhận kết nối hoạt động.

Không log credential hoặc token trong test output. Khi debug, ưu tiên in host, port hoặc tên property đã được resolve, và che thông tin xác thực.

## 6. Dynamic property và `@ConfigurationProperties`

Dynamic property hoạt động với các cơ chế đọc property thông thường của Spring. Ví dụ, một bean `@ConfigurationProperties` có thể bind giá trị URL do registry cung cấp:

```java
@ConfigurationProperties(prefix = "payment.gateway")
record PaymentGatewayProperties(URI baseUrl, Duration timeout) {
}
```

Test đăng ký property:

```java
@DynamicPropertySource
static void paymentProperties(DynamicPropertyRegistry registry) {
    registry.add("payment.gateway.base-url", paymentServer::baseUrl);
    registry.add("payment.gateway.timeout", () -> "1500ms");
}
```

Spring Boot bind các giá trị này vào record khi tạo bean cấu hình. `Duration` hỗ trợ định dạng mà Spring Boot nhận biết, ví dụ `1500ms`, `2s` hoặc `1m`.

Nếu property không được bind, kiểm tra:

1. Prefix trên `@ConfigurationProperties` có đúng không.
2. Tên property được đăng ký có đúng theo relaxed binding không.
3. Configuration properties class đã được scan hoặc enable chưa.
4. Có bean khác hoặc property source có độ ưu tiên cao hơn không.
5. Supplier có trả về giá trị phù hợp với kiểu đích không.

Không nhầm việc đăng ký property với việc tự động tạo bean cấu hình. `@DynamicPropertySource` chỉ thêm giá trị vào `Environment`; ứng dụng vẫn cần cơ chế đăng ký và bind `@ConfigurationProperties` như bình thường.

## 7. Kế thừa phương thức `@DynamicPropertySource`

Các phương thức `@DynamicPropertySource` có thể được đặt trong superclass để nhiều integration test dùng chung một tài nguyên hoặc cùng cách đăng ký property:

```java
abstract class BaseDatabaseIntegrationTest {
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

@SpringBootTest
class CustomerRepositoryTest extends BaseDatabaseIntegrationTest {
    @Autowired
    private CustomerRepository customers;
}

@SpringBootTest
class OrderRepositoryTest extends BaseDatabaseIntegrationTest {
    @Autowired
    private OrderRepository orders;
}
```

Các lớp con kế thừa phương thức đăng ký property. Đây là cách gom boilerplate cho nhóm test dùng cùng database configuration.

### 7.1. Khi subclass dùng tài nguyên khác nhau

Một tình huống tinh tế xuất hiện khi superclass có `@DynamicPropertySource`, nhưng supplier trả giá trị khác nhau tùy subclass. Spring dùng các phương thức dynamic property source như một phần cấu hình test context và cache context dựa trên cấu hình đã hợp nhất. Giá trị runtime do supplier trả về không nhất thiết tạo ra cache key riêng cho mỗi giá trị.

Ví dụ, hai subclass kế thừa cùng một phương thức nhưng mỗi lớp thay đổi container hoặc endpoint theo cách riêng. Nếu Spring tái sử dụng context đã tạo cho lớp trước, bean có thể vẫn giữ connection được tạo từ endpoint cũ.

Khi dynamic property thực sự thay đổi giữa các subclass và làm thay đổi context cần dùng, hãy đánh dấu context dirty ở base class hoặc tổ chức test để mỗi nhóm tài nguyên có context riêng:

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseExternalServiceIntegrationTest {
    // Dynamic property source và tài nguyên dùng theo từng nhóm test.
}
```

`@DirtiesContext` làm context được loại khỏi cache sau class. Chỉ dùng khi giá trị động khác nhau thực sự đòi hỏi context khác. Nếu mọi subclass dùng chung một container và endpoint, giữ context cache thường hiệu quả hơn.

## 8. Dynamic property và vòng đời tài nguyên

Supplier chỉ cung cấp giá trị; nó không tự khởi động hoặc dừng container, server hay broker. Test phải quản lý vòng đời tài nguyên bằng Testcontainers, JUnit extension, `@BeforeAll`/`@AfterAll` hoặc cơ chế cleanup phù hợp.

Một thứ tự khái quát:

```text
Khởi động tài nguyên test
        |
        v
Spring đọc cấu hình test
        |
        v
@DynamicPropertySource đăng ký supplier
        |
        v
Environment truy xuất property
        |
        v
Spring tạo bean dùng endpoint/credential
        |
        v
Test thực hiện request hoặc truy vấn
        |
        v
Đóng context và giải phóng tài nguyên
```

Chi tiết thứ tự phụ thuộc vào cách extension hoặc fixture khởi động tài nguyên. Quy tắc thực tế là supplier phải đọc được giá trị hợp lệ khi Spring cần resolve property và tài nguyên phải còn sống trong suốt thời gian bean sử dụng nó.

### 8.1. Không trả endpoint đã lỗi thời

Tránh lưu URL/port trước khi server khởi động hoặc trả về một giá trị đã thay đổi sau khi context tạo client. Nếu tài nguyên có thể restart và nhận port mới, context cũ không tự cập nhật datasource hoặc HTTP client đã được tạo từ property cũ.

Khi restart tài nguyên, hãy xác định liệu cần tạo context mới hay có thể giữ endpoint ổn định. Nếu context cần tạo lại, quản lý bằng lifecycle test và `@DirtiesContext` ở phạm vi phù hợp.

### 8.2. Supplier không phải nơi thực hiện side effect

Supplier nên đọc giá trị từ tài nguyên đã được khởi tạo. Không nên dùng supplier để khởi động container, tạo database, gửi request hoặc thay đổi trạng thái toàn cục. Property có thể được truy cập nhiều lần; side effect trong supplier có thể bị lặp và khiến kết quả khó dự đoán.

Hãy tách trách nhiệm:

- Extension/fixture khởi động và dừng tài nguyên.
- `@DynamicPropertySource` đăng ký các giá trị kết nối.
- Spring tạo bean dựa trên property.
- Test thực hiện hành vi và cleanup dữ liệu cần thiết.

## 9. So sánh với `@TestPropertySource` và profile

Ba cơ chế thường được dùng cùng nhau nhưng phục vụ những loại cấu hình khác nhau:

| Cơ chế | Nguồn giá trị | Khi phù hợp |
|---|---|---|
| `@ActiveProfiles` | Chọn nhóm cấu hình theo profile | Muốn bật `application-integration.yml` hoặc cấu hình môi trường test |
| `@TestPropertySource` | File hoặc inline property tĩnh | Timeout, feature flag, tên queue hoặc giá trị đã biết trước |
| `@DynamicPropertySource` | Supplier lấy giá trị lúc runtime | URL/port/credential của container hoặc server test |

Ví dụ kết hợp:

```java
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = {
        "catalog.client.retry.max-attempts=2",
        "catalog.client.connect-timeout=1s"
})
class CatalogIntegrationTest {
    @DynamicPropertySource
    static void dynamicCatalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url", catalogServer::baseUrl);
    }
}
```

Profile chọn nhóm cấu hình chung; `@TestPropertySource` cung cấp các giá trị cố định cho test; dynamic registry cung cấp endpoint chỉ biết được sau khi server khởi động. Phân chia như vậy giúp nguồn của mỗi property rõ ràng.

## 10. Chẩn đoán lỗi với dynamic property

### 10.1. Property không được tìm thấy

Nếu ứng dụng báo `Could not resolve placeholder`, hãy kiểm tra tên key trong `registry.add` và tên key mà `@Value` hoặc `@ConfigurationProperties` đang đọc. Kiểm tra phương thức được đánh dấu `@DynamicPropertySource`, có đúng `static` và nhận `DynamicPropertyRegistry` hay không.

Ví dụ, nếu ứng dụng đọc:

```java
@Value("${catalog.client.base-url}")
private URI baseUrl;
```

thì registry phải đăng ký `catalog.client.base-url`, không phải một key gần giống như `catalog.base-url`.

### 10.2. Supplier được gọi khi tài nguyên chưa sẵn sàng

Nếu supplier gọi `getJdbcUrl()` trước khi container chạy, kiểm tra cách quản lý lifecycle của Testcontainers. Với JUnit Jupiter, dùng container static được extension quản lý hoặc đảm bảo fixture khởi động trước thời điểm Spring resolve property.

Không tự gọi `start()` lặp lại bên trong supplier. Điều đó trộn vòng đời tài nguyên với việc đọc cấu hình và có thể tạo nhiều container ngoài ý muốn.

### 10.3. Kết nối đến sai port hoặc endpoint cũ

In ra host/port không nhạy cảm mà supplier trả về, kiểm tra container đang chạy và kiểm tra context có được cache từ một test khác hay không. Nếu endpoint thay đổi theo subclass nhưng context được tái sử dụng, xem lại cấu hình kế thừa và phạm vi `@DirtiesContext`.

### 10.4. Giá trị property không được bind vào bean

Kiểm tra prefix, tên key, kiểu dữ liệu và việc đăng ký `@ConfigurationProperties`. Một property có trong `Environment` nhưng không xuất hiện trong bean cấu hình thường là vấn đề binding hoặc bean registration, không phải vấn đề supplier.

### 10.5. Property bị ghi đè

Dynamic property source có ưu tiên cao hơn các property source thông thường, nhưng nếu test đọc một key khác hoặc có logic ứng dụng tự ghi đè giá trị sau khi bind, kết quả có thể không như mong đợi. Đọc trực tiếp key trong `Environment`, rồi kiểm tra bean đã bind để xác định lỗi nằm ở property source hay ở bước cấu hình bean.

### 10.6. Context cache che giấu thay đổi endpoint

Nếu supplier thay đổi giá trị theo subclass nhưng phương thức dynamic source vẫn là cùng một phương thức được kế thừa, context key có thể không phản ánh thay đổi runtime đó. Tách context hoặc đánh dấu dirty khi endpoint khác nhau thật sự cần context mới.

## 11. Ví dụ tổng hợp: database và service endpoint

Một ứng dụng có thể cần cả database container và mock HTTP service. Mỗi dependency cung cấp endpoint động:

```java
@SpringBootTest
@Testcontainers
class OrderIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static final GenericContainer<?> catalog =
            new GenericContainer<>("wiremock/wiremock:3.9.1")
                    .withExposedPorts(8080);

    @DynamicPropertySource
    static void runtimeProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);

        registry.add("catalog.client.base-url", () ->
                "http://" + catalog.getHost() + ":" +
                        catalog.getMappedPort(8080));
    }

    @Autowired
    private OrderService orders;

    @Test
    void createsOrderUsingRuntimeDependencies() {
        Order order = orders.create(new CreateOrderCommand("customer-42"));

        assertThat(order.id()).isNotBlank();
    }
}
```

Ví dụ minh họa cách đăng ký nhiều dependency runtime trong một registry. Để test có ý nghĩa thực tế, container catalog cần được cấu hình stub/response mong đợi và test nên xác nhận hành vi ứng dụng sử dụng response đó. `GenericContainer` ở đây chỉ minh họa một service có port được expose; trong dự án thật, có thể dùng module Testcontainers chuyên biệt hoặc mock server phù hợp.

Không nên để test chỉ xác nhận ứng dụng khởi động thành công nếu mục tiêu là tích hợp. Hãy thực hiện một thao tác nghiệp vụ đi qua database và service endpoint, sau đó xác nhận kết quả ở ranh giới phù hợp.

## 12. Các lỗi thiết kế thường gặp

### Ghi cứng port của tài nguyên test

Port cố định có thể bị chiếm hoặc trỏ đến dịch vụ khác. Dùng port ngẫu nhiên và đăng ký endpoint runtime.

### Dùng `@DynamicPropertySource` cho property tĩnh

Timeout hoặc feature flag đã biết trước thường phù hợp với inline property hoặc `@TestPropertySource`. Dynamic registry nên dành cho giá trị thực sự chỉ có khi runtime.

### Quên quản lý vòng đời tài nguyên

Registry không khởi động hoặc dừng container. Dùng extension hoặc fixture để quản lý start/stop và bảo đảm tài nguyên sống trong suốt thời gian context sử dụng nó.

### Đăng ký sai tên property

Supplier vẫn được đăng ký nhưng ứng dụng đọc key khác. So khớp chính xác tên property và kiểm tra `Environment` khi cần.

### Tạo side effect trong supplier

Supplier có thể được gọi khi property được resolve. Chỉ đọc giá trị; khởi động tài nguyên ở lifecycle hook hoặc extension.

### Dùng chung context khi endpoint thay đổi

Context cache có thể tái sử dụng bean đã bind endpoint cũ. Tổ chức context theo vòng đời tài nguyên hoặc dùng `@DirtiesContext` khi cần.

### Cho rằng dynamic property tự tạo bean cấu hình

Registry chỉ thêm giá trị vào `Environment`. Bean `@ConfigurationProperties` vẫn phải được scan/enable, còn client vẫn cần được đăng ký như bình thường.

## 13. Quy trình áp dụng `DynamicPropertyRegistry`

Khi một integration test cần giá trị chỉ có ở runtime, hãy thực hiện theo trình tự:

1. Xác định property ứng dụng cần đọc, ví dụ JDBC URL hoặc base URL của HTTP client.
2. Chọn tài nguyên test cung cấp giá trị đó: Testcontainers, mock server hoặc fixture tương ứng.
3. Xác định lifecycle của tài nguyên và bảo đảm nó sẵn sàng khi Spring resolve property.
4. Khai báo phương thức `static` có `@DynamicPropertySource` và tham số `DynamicPropertyRegistry`.
5. Đăng ký từng key với supplier hoặc method reference lấy giá trị từ tài nguyên.
6. Kiểm tra property đã được resolve và bean đã bind đúng giá trị.
7. Thực hiện hành vi tích hợp thực tế; không chỉ kiểm tra context có thể khởi động.
8. Nếu endpoint thay đổi giữa các test class, xem xét context cache và tách context khi cần.
9. Dừng tài nguyên sau khi test hoàn tất và cleanup dữ liệu ngoài transaction.

Một dynamic property nên có nguồn duy nhất, tên rõ ràng và vòng đời tương thích với bean sử dụng nó. Khi endpoint thay đổi, cần hiểu cả supplier lẫn context cache; chỉ đăng ký một lambda không tự làm client hoặc datasource đã tạo được cấu hình lại.

## 14. Nguyên tắc cần nhớ

- `@DynamicPropertySource` đánh dấu phương thức static đăng ký property cho test context.
- `DynamicPropertyRegistry.add(name, supplier)` liên kết một key với giá trị được cung cấp qua supplier.
- Supplier phù hợp với port, URL và credential chỉ biết được sau khi tài nguyên test khởi động.
- Registry thêm giá trị vào `Environment`; nó không tự khởi động container, tạo bean hoặc quản lý cleanup.
- Dynamic properties có độ ưu tiên cao hơn `@TestPropertySource`, JVM system properties, environment variables và property source thông thường của ứng dụng.
- Dùng `@ConfigurationProperties` hoặc `@Value` như bình thường để tiêu thụ property đã đăng ký.
- Có thể kế thừa phương thức dynamic property source, nhưng phải chú ý context cache nếu giá trị runtime thay đổi giữa các subclass.
- Chỉ dùng `@DirtiesContext` khi endpoint thay đổi đòi hỏi context mới; không dùng nó thay cho cleanup database hoặc broker.
- Giữ supplier thuần đọc dữ liệu và để extension/fixture quản lý vòng đời tài nguyên.

`DynamicPropertyRegistry` nối cấu hình Spring với các dependency được cấp lúc runtime. Khi property name, supplier và vòng đời tài nguyên được khai báo rõ, integration test có thể dùng cổng ngẫu nhiên và endpoint riêng mà vẫn khởi tạo `ApplicationContext` một cách nhất quán.
