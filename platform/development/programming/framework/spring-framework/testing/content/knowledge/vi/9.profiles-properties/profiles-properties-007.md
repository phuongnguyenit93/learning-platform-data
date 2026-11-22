# `DynamicPropertyRegistrar` theo phiên bản Spring hỗ trợ

Trong kiểm thử tích hợp, một số thuộc tính chỉ có giá trị sau khi tài nguyên kiểm thử được khởi chạy. Ví dụ, Testcontainers có thể cấp một cổng ngẫu nhiên cho PostgreSQL; một HTTP server nhúng có thể chọn port khả dụng; hoặc một bean khởi tạo dịch vụ giả lập có thể cung cấp URL sau khi startup. Các giá trị này không thể ghi cố định trong `application-test.properties` vì chúng chỉ được biết ở runtime.

Spring Test cung cấp cơ chế dynamic property để đăng ký các giá trị đó vào `Environment`. Trước Spring Framework 6.2, cách phổ biến là dùng method `@DynamicPropertySource` tĩnh trong test class. Từ **Spring Framework 6.2.0**, có thêm `DynamicPropertyRegistrar`: một bean trong chính test `ApplicationContext` có thể đăng ký dynamic property, kể cả property lấy từ những bean khác trong context.

`DynamicPropertyRegistrar` hữu ích khi tài nguyên hoặc server kiểm thử được quản lý như Spring bean. Nó giúp cấu hình động nằm gần cấu hình tạo tài nguyên, thay vì phải đưa mọi giá trị vào một static method của test class.

## 1. Phiên bản Spring nào hỗ trợ `DynamicPropertyRegistrar`?

`DynamicPropertyRegistrar` được giới thiệu từ **Spring Framework 6.2.0** và thuộc package:

```java
org.springframework.test.context.DynamicPropertyRegistrar
```

Vì vậy:

| Phiên bản Spring Framework | Khả năng |
| --- | --- |
| Trước 5.2.5 | Chưa có `DynamicPropertyRegistry` và `@DynamicPropertySource` |
| 5.2.5 đến 6.1.x | Có `DynamicPropertyRegistry` và `@DynamicPropertySource`; chưa có `DynamicPropertyRegistrar` |
| 6.2.0 trở lên | Có thêm `DynamicPropertyRegistrar` bean và khả năng đăng ký dynamic property từ trong test `ApplicationContext` |

Spring Framework 7.x tiếp tục hỗ trợ API này. Khi dùng Spring Boot, hãy kiểm tra phiên bản Spring Framework thực tế được dependency management kéo vào, thay vì chỉ nhìn version của một thư viện hoặc starter riêng lẻ. Các phiên bản Spring Boot khác nhau quản lý Spring Framework khác nhau.

Với Maven, có thể xem dependency thực tế bằng:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

Nếu `spring-test` đang ở phiên bản thấp hơn 6.2, không thể import `DynamicPropertyRegistrar`. Hãy dùng `@DynamicPropertySource` nếu phù hợp hoặc nâng Spring Framework theo ma trận tương thích của ứng dụng.

Lưu ý rằng `DynamicPropertyRegistry` có từ Spring Framework 5.2.5. API registry và annotation `@DynamicPropertySource` cũ hơn `DynamicPropertyRegistrar`; không nên nhầm mốc phiên bản của chúng.

## 2. `DynamicPropertyRegistrar` là gì?

`DynamicPropertyRegistrar` là một functional interface của Spring TestContext Framework. Nó định nghĩa một phương thức:

```java
void accept(DynamicPropertyRegistry registry);
```

Một bean trong test `ApplicationContext` implement interface này sẽ được Spring Test tự động phát hiện. Spring khởi tạo các registrar bean một cách eager trước giai đoạn pre-instantiation của các singleton thông thường, sau đó gọi `accept()` với một `DynamicPropertyRegistry` để registrar thêm các property.

Ví dụ tối giản:

```java
@TestConfiguration
class ApiTestConfiguration {

    @Bean
    ApiServer apiServer() {
        return new ApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiPropertiesRegistrar(ApiServer apiServer) {
        return registry -> registry.add("api.url", apiServer::getUrl);
    }
}
```

`ApiServer` là bean được quản lý trong test context. Registrar nhận bean đó làm dependency rồi đăng ký property `api.url` bằng method reference `apiServer::getUrl`.

Các bean khác trong context có thể đọc property:

```java
@Component
class ApiClientConfiguration {

    ApiClientConfiguration(@Value("${api.url}") URI apiUrl) {
        // Dùng apiUrl để cấu hình client
    }
}
```

Đây là điểm khác biệt quan trọng so với `@DynamicPropertySource`: registrar là một bean, nên nó có thể tương tác trực tiếp với các bean khác trong `ApplicationContext`.

## 3. DynamicPropertyRegistry và Supplier

`DynamicPropertyRegistry` cung cấp phương thức `add()`:

```java
void add(String name, Supplier<Object> valueSupplier);
```

Tham số thứ hai là `Supplier`, vì vậy giá trị được cung cấp khi property được resolve, thay vì bắt buộc phải tính tại đúng thời điểm gọi `add()`.

Ví dụ:

```java
registry.add("service.port", server::getPort);
registry.add("service.url", () -> "http://localhost:" + server.getPort());
```

Method reference hoặc lambda có thể đọc giá trị runtime. Điều này hữu ích khi port hoặc URL được cấp động sau khi server khởi động.

Không nên nhầm `Supplier` với một tác vụ được thực thi liên tục. Supplier được gọi khi Spring cần resolve property; nếu giá trị nguồn thay đổi giữa các lần resolve, kết quả có thể thay đổi theo. Với cấu hình ứng dụng như URL database, nên bảo đảm tài nguyên đã khởi động và giá trị ổn định trước khi các bean tiêu thụ property được khởi tạo.

## 4. Registrar được phát hiện và gọi ở thời điểm nào?

Spring Test tự phát hiện các bean có kiểu `DynamicPropertyRegistrar` trong test `ApplicationContext`. Các registrar bean được eager initialize trước singleton pre-instantiation phase. Sau khi registrar được khởi tạo, Spring gọi `accept(registry)` để đăng ký các property.

Luồng khái quát:

```text
Tạo test ApplicationContext
          |
          v
Đăng ký bean definitions từ test config
          |
          v
Khởi tạo DynamicPropertyRegistrar beans (eager)
          |
          v
Gọi accept(DynamicPropertyRegistry)
          |
          v
Đăng ký property suppliers vào Environment
          |
          v
Khởi tạo các singleton bean thông thường
          |
          v
Các bean resolve property khi cần
```

Trình tự này giúp property được đăng ký trước khi phần lớn singleton thông thường cần resolve cấu hình của chúng.

### Cảnh báo về eager initialization

Nếu registrar tương tác với một bean khác, bean đó và dependency của nó cũng được khởi tạo eager. Đây là hành vi được thiết kế để registrar có thể lấy giá trị từ bean nguồn, nhưng có thể làm thay đổi thời điểm khởi tạo so với một context chỉ dùng lazy bean.

Ví dụ, registrar cần `ApiServer` để lấy port. Khi Spring tạo registrar, `ApiServer` cũng phải được tạo trước. Nếu constructor hoặc init method của `ApiServer` khởi động server, server có thể được khởi động sớm trong quá trình bootstrap context.

Hãy tránh vòng phụ thuộc kiểu:

```text
DynamicPropertyRegistrar
       |
       v
ApiClient bean
       |
       v
api.url property
       ^
       |
Registrar đang cố đăng ký api.url từ ApiClient
```

Registrar nên phụ thuộc vào bean cung cấp giá trị gốc, không phụ thuộc vào consumer đang cần property mà chính registrar đăng ký. Ví dụ, registrar lấy URL từ `ApiServer`; `ApiClient` mới là consumer của `api.url`.

## 5. Ví dụ đầy đủ với server có port ngẫu nhiên

Giả sử test cần một HTTP server nội bộ. Server chọn port khả dụng khi khởi động và cung cấp URL cho `RestClient` hoặc một client khác trong ứng dụng.

Một abstraction đơn giản:

```java
public class ApiServer {

    private final HttpServer server;

    public ApiServer() throws IOException {
        this.server = HttpServer.create();
    }

    public void start() throws IOException {
        server.bind(new InetSocketAddress("localhost", 0), 0);
        server.start();
    }

    public int getPort() {
        return server.getAddress().getPort();
    }

    public String getUrl() {
        return "http://localhost:" + getPort();
    }

    public void stop() {
        server.stop(0);
    }
}
```

Test configuration:

```java
@TestConfiguration
class ApiServerTestConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    ApiServer apiServer() throws IOException {
        return new ApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiServerProperties(ApiServer apiServer) {
        return registry -> registry.add("test.api.base-url", apiServer::getUrl);
    }
}
```

Consumer có thể inject URL:

```java
@Component
class ExternalApiClient {

    private final RestClient restClient;

    ExternalApiClient(@Value("${test.api.base-url}") String baseUrl) {
        this.restClient = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }
}
```

Test nạp cấu hình:

```java
@SpringBootTest
@Import(ApiServerTestConfiguration.class)
class ExternalApiClientIntegrationTest {

    @Autowired
    Environment environment;

    @Autowired
    ExternalApiClient client;

    @Test
    void exposesTheStartedServerUrlAsADynamicProperty() {
        String baseUrl = environment.getRequiredProperty("test.api.base-url");

        assertTrue(baseUrl.startsWith("http://localhost:"));
    }
}
```

Ví dụ này minh họa cách resource do context quản lý cung cấp property động. Trong dự án thực tế, `ApiServer` có thể là một server test chuyên dụng hoặc một bean do thư viện tạo ra. Nếu server cần được khởi động bằng lifecycle riêng, hãy cấu hình `initMethod`/`destroyMethod` hoặc lifecycle interface phù hợp và bảo đảm URL có sẵn khi consumer khởi tạo.

## 6. Ví dụ với Testcontainers và PostgreSQL

Một use case phổ biến là dùng Testcontainers khởi chạy database trên port ngẫu nhiên. Nếu container được quản lý như Spring bean trong test context, `DynamicPropertyRegistrar` có thể lấy JDBC URL, username và password từ bean container.

Ví dụ với Testcontainers:

```java
@TestConfiguration
class PostgreSqlTestConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }

    @Bean
    DynamicPropertyRegistrar postgresProperties(
            PostgreSQLContainer<?> postgresContainer) {

        return registry -> {
            registry.add("spring.datasource.url", postgresContainer::getJdbcUrl);
            registry.add("spring.datasource.username", postgresContainer::getUsername);
            registry.add("spring.datasource.password", postgresContainer::getPassword);
        };
    }
}
```

Test sử dụng cấu hình đó:

```java
@SpringBootTest
@Import(PostgreSqlTestConfiguration.class)
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInTheContainerDatabase() {
        // Ghi và đọc dữ liệu qua repository thật
    }
}
```

Khi Spring khởi tạo registrar, dependency `postgresContainer` được khởi tạo và gọi init method `start()`. Registrar đăng ký các supplier lấy thông tin kết nối từ container. Sau đó các singleton như datasource có thể resolve `spring.datasource.url`, username và password.

Trong ví dụ, container là bean nên lifecycle của nó gắn với context. Spring gọi `stop()` khi bean bị destroy. Hãy cân nhắc context cache: nếu nhiều test class dùng chung context, container có thể sống lâu hơn một method test. Đó thường là điều mong muốn để tái sử dụng context, nhưng cần hiểu rõ khi nào context bị đóng hoặc loại khỏi cache.

Một lựa chọn khác là dùng Testcontainers JUnit extension với static `@Container` field và `@DynamicPropertySource`. Khi container được quản lý ngoài Spring context, cách static đó thường tự nhiên hơn.

## 7. So sánh `DynamicPropertyRegistrar` và `@DynamicPropertySource`

Hai cơ chế cùng đăng ký dynamic property nhưng khác nhau về vị trí và nguồn giá trị.

| Tiêu chí | `@DynamicPropertySource` | `DynamicPropertyRegistrar` |
| --- | --- | --- |
| Có từ phiên bản | Spring Framework 5.2.5 | Spring Framework 6.2.0 |
| Nơi khai báo | Method `static` trong test class hoặc superclass phù hợp | Bean trong test `ApplicationContext` |
| Đầu vào | `DynamicPropertyRegistry` được truyền vào method | `DynamicPropertyRegistry` được truyền vào `accept()` |
| Truy cập bean Spring khác | Không trực tiếp qua test method static | Có thể inject và tương tác với bean context |
| Trường hợp phù hợp | Tài nguyên static hoặc được quản lý bởi JUnit/Testcontainers extension | Tài nguyên/server được quản lý như Spring bean |
| Thời điểm | Đăng ký dynamic property trong quá trình chuẩn bị context test | Registrar bean được eager initialize trước singleton pre-instantiation |

### Cách cũ: `@DynamicPropertySource`

```java
@SpringBootTest
@Testcontainers
class OrderRepositoryTest {

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

Method phải là `static` và nhận một tham số `DynamicPropertyRegistry`. Cách này phù hợp khi container được quản lý bởi JUnit Testcontainers extension và không cần truy cập bean trong Spring context để tạo property.

### Cách mới: registrar bean

```java
@TestConfiguration
class DatabaseTestConfiguration {

    @Bean
    DynamicPropertyRegistrar databaseProperties(DatabaseServer databaseServer) {
        return registry -> {
            registry.add("spring.datasource.url", databaseServer::jdbcUrl);
            registry.add("spring.datasource.username", databaseServer::username);
        };
    }
}
```

Registrar phù hợp khi `DatabaseServer` là bean trong context hoặc được cung cấp bởi một test configuration khác. Không cần static method trên test class.

Hai cách không loại trừ nhau. Một test có thể có nhiều nguồn dynamic property, nhưng nên tránh đăng ký cùng một key ở nhiều nơi vì sẽ khó hiểu nguồn nào đang quyết định giá trị cuối cùng. Hãy chọn một cơ chế chính cho mỗi nhóm tài nguyên.

## 8. Độ ưu tiên của dynamic property

Dynamic property có độ ưu tiên cao hơn các nguồn sau:

- `@TestPropertySource`.
- Environment variables của hệ điều hành.
- Java system properties.
- Property source được thêm bằng `@PropertySource`.
- Property source ứng dụng được thêm theo cách khai báo hoặc lập trình thông thường.

Điều này cho phép test ghi đè chọn lọc cấu hình môi trường. Ví dụ, `spring.datasource.url` do registrar đăng ký sẽ được ưu tiên khi Spring resolve property so với URL được đặt trong `application-test.properties` hoặc system property tương ứng.

Độ ưu tiên cao rất hữu ích khi cần bảo đảm test dùng đúng container hoặc server test. Tuy nhiên, nó cũng có thể che giấu cấu hình sai nếu registrar đăng ký nhầm key hoặc giá trị. Hãy kiểm tra property quan trọng qua `Environment` khi chẩn đoán context.

Ví dụ:

```java
@Autowired
Environment environment;

@Test
void usesTheContainerJdbcUrl() {
    String jdbcUrl = environment.getRequiredProperty("spring.datasource.url");

    assertTrue(jdbcUrl.startsWith("jdbc:postgresql://"));
}
```

Không ghi password hoặc secret ra log để chẩn đoán. Nếu cần kiểm tra, hãy xác nhận nguồn hoặc đặc tính an toàn của cấu hình thay vì in giá trị bí mật.

## 9. Dùng registrar khi property được lấy từ bean khác

Đây là trường hợp `DynamicPropertyRegistrar` giải quyết thuận tiện hơn static method. Giả sử một bean test khởi chạy WireMock hoặc một mock server và cung cấp base URL.

```java
@TestConfiguration
class MockServerConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    MockWebServer mockWebServer() {
        return new MockWebServer();
    }

    @Bean
    DynamicPropertyRegistrar mockServerProperties(MockWebServer mockWebServer) {
        return registry -> registry.add(
            "catalog.api.base-url",
            () -> mockWebServer.url("/").toString()
        );
    }
}
```

Consumer có thể inject `${catalog.api.base-url}` hoặc đọc qua `Environment`. Registrar lấy giá trị từ bean server thay vì phải truy cập một static field.

Điểm cần quan tâm là server phải được khởi động trước khi URL được sử dụng. Nếu `MockWebServer` được start trong init method, Spring hoàn tất khởi tạo dependency trước khi registrar đăng ký property. Supplier sẽ lấy URL khi property được resolve.

## 10. Eager initialization và vòng đời bean

Việc registrar được eager initialize có một số hệ quả cần hiểu:

1. Registrar không phải một bean lazy thông thường; Spring cần tạo nó để đăng ký property.
2. Bean được inject vào constructor hoặc factory method của registrar cũng bị khởi tạo sớm.
3. Các dependency của những bean đó có thể được khởi tạo theo dây chuyền.
4. Nếu một bean nguồn khởi động server hoặc container, tài nguyên có thể được khởi động sớm hơn dự kiến.
5. Nếu registrar phụ thuộc vào consumer của chính property nó đăng ký, có thể tạo vòng phụ thuộc hoặc khiến consumer được khởi tạo trước khi property sẵn sàng.

Thiết kế nên tách rõ:

```text
Resource bean (starts server/container)
          |
          v
DynamicPropertyRegistrar
          |
          v
Environment property
          |
          v
Consumer bean (HTTP client / DataSource)
```

Registrar phụ thuộc vào resource bean; consumer phụ thuộc vào property. Không tạo dependency ngược từ registrar tới consumer.

Nếu khởi tạo tài nguyên tốn kém, hãy xem xét phạm vi test context và khả năng tái sử dụng context. Không nên tạo nhiều container giống nhau chỉ vì mỗi test method có một registrar riêng; Spring Test thường cache context theo cấu hình tương đương.

## 11. Registrar và `@DynamicPropertySource` trên `@Bean` method

Spring Framework 6.2 còn hỗ trợ áp dụng `@DynamicPropertySource` lên một method `@Bean` trong configuration class. Trong một số trường hợp, điều đó được dùng để yêu cầu bean tương ứng được eager initialized nhằm bảo đảm property mà bean đăng ký có sẵn cho các singleton khác.

Ví dụ khái quát:

```java
@TestConfiguration
class EmbeddedServerConfiguration {

    @Bean
    @DynamicPropertySource
    ApiServer apiServer(DynamicPropertyRegistry registry) {
        ApiServer server = new ApiServer();
        server.start();
        registry.add("api.url", server::getUrl);
        return server;
    }
}
```

Đây là một cách khác để gắn việc tạo bean với việc đăng ký dynamic property. Nếu mục tiêu là đăng ký property từ bean khác trong context, `DynamicPropertyRegistrar` thường thể hiện ý định rõ hơn. Không nên dùng cả hai cơ chế cho cùng key nếu không cần thiết.

Hãy kiểm tra API của phiên bản Spring đang dùng và lifecycle của bean. Với tài nguyên cần cleanup, cần bảo đảm có `destroyMethod` hoặc lifecycle phù hợp để giải phóng tài nguyên sau khi context đóng.

## 12. Đăng ký nhiều property trong một registrar

Một registrar có thể đăng ký nhiều property liên quan tới cùng tài nguyên:

```java
@Bean
DynamicPropertyRegistrar redisProperties(RedisTestServer redis) {
    return registry -> {
        registry.add("spring.data.redis.host", redis::host);
        registry.add("spring.data.redis.port", redis::port);
        registry.add("spring.data.redis.username", redis::username);
        registry.add("spring.data.redis.password", redis::password);
    };
}
```

Nhóm property liên quan tới một resource trong cùng registrar giúp cấu hình có tính kết dính. Nếu nhiều tài nguyên độc lập như database, message broker và mock HTTP server, có thể tạo registrar riêng cho mỗi resource để dependency và lifecycle rõ ràng.

Đặt tên property theo convention mà ứng dụng đang sử dụng. Với Spring Boot, thường dùng relaxed binding và tên dạng kebab-case trong file cấu hình; trong registry, hãy đăng ký đúng key mà consumer đang resolve.

## 13. Registrar không thay thế việc quản lý lifecycle tài nguyên

`DynamicPropertyRegistrar` chỉ đăng ký property. Nó không tự tạo, start, stop hoặc cleanup container/server nếu những hành động đó không được cấu hình trong bean lifecycle.

Ví dụ registrar đăng ký `server.getPort()` nhưng server chưa được start thì giá trị port có thể không hợp lệ hoặc chưa sẵn sàng. Cần quản lý tài nguyên qua:

- `@Bean(initMethod = "start", destroyMethod = "stop")` khi phù hợp.
- `InitializingBean` và `DisposableBean` nếu muốn dùng lifecycle interface.
- `SmartLifecycle` cho tài nguyên cần tham gia phase start/stop của context.
- Testcontainers JUnit extension nếu container được quản lý bên ngoài Spring context.
- Một extension hoặc fixture riêng nếu vòng đời tài nguyên thuộc test framework khác.

Chọn một chủ sở hữu lifecycle rõ ràng. Tránh để JUnit extension và Spring bean cùng start/stop một container vì có thể dẫn đến dừng tài nguyên khi context vẫn còn sử dụng hoặc start nhiều lần.

## 14. Xử lý khi property không resolve được

Nếu một bean inject `@Value("${api.url}")` nhưng registrar không đăng ký property, context có thể thất bại khi tạo bean. Một số nguyên nhân thường gặp:

- Test configuration chứa registrar chưa được import hoặc scan.
- Test context đang chạy Spring Framework thấp hơn 6.2 nên không có API registrar.
- Bean nguồn không được tạo hoặc init method thất bại.
- Tên property trong registrar khác tên consumer.
- Registrar phụ thuộc vào bean consumer tạo vòng khởi tạo.
- Supplier chỉ được gọi khi property resolve và tại thời điểm đó tài nguyên chưa sẵn sàng.
- Một property source khác hoặc profile làm người đọc nhầm giá trị đang được dùng.

Để chẩn đoán:

```java
String apiUrl = environment.getProperty("api.url");
assertNotNull(apiUrl, "api.url must be registered by the test context");
```

Hãy kiểm tra `Environment` sau khi context đã được khởi tạo. Khi giá trị bị thiếu, xem lại registrar bean có nằm trong context hay không và liệu `accept()` đã được gọi. Không nên đưa default production URL vào test chỉ để context khởi động, vì như vậy có thể khiến test vô tình gọi dịch vụ thật.

## 15. Dùng registrar trong test slice hay full context?

`DynamicPropertyRegistrar` được phát hiện trong test `ApplicationContext`, vì vậy nó có thể được dùng trong test context được tạo bởi các annotation Spring Test tương ứng. Tuy nhiên, cấu hình test phải thực sự được nạp vào slice/context đó.

Với `@SpringBootTest`, có thể import test configuration:

```java
@SpringBootTest
@Import(ApiServerTestConfiguration.class)
class ApiIntegrationTest {
}
```

Với một slice như `@DataJpaTest`, hãy xác nhận cấu hình cần thiết được đưa vào slice và không vô tình kéo toàn bộ ứng dụng vào. Nếu registrar cung cấp datasource property, cấu hình slice và auto-configuration datasource cần được sắp xếp phù hợp.

Đối với `@WebMvcTest`, nếu dynamic property chỉ phục vụ một client được mock hoặc bean bị loại khỏi slice, registrar có thể không cần thiết. Hãy chọn test slice theo hành vi cần kiểm tra, không thêm tài nguyên ngoài phạm vi chỉ để sử dụng API này.

## 16. Kết hợp registrar với `@ActiveProfiles` và property file

Dynamic property thường bổ sung hoặc ghi đè cấu hình từ profile. Ví dụ, `application-test.yml` có thể chứa các thiết lập chung:

```yaml
feature:
  audit-enabled: false

spring:
  datasource:
    hikari:
      maximum-pool-size: 3
```

Trong khi registrar cung cấp URL, username và password của database container:

```java
@Bean
DynamicPropertyRegistrar databaseProperties(PostgreSQLContainer<?> postgres) {
    return registry -> {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    };
}
```

Profile vẫn cung cấp cấu hình tĩnh dùng chung; registrar cung cấp những giá trị chỉ có thể biết sau khi resource khởi chạy. Vì dynamic property có độ ưu tiên cao, các key được đăng ký sẽ ghi đè nguồn cấu hình thấp hơn khi resolve.

## 17. Những sai lầm thường gặp

- **Dùng registrar trên Spring Framework 6.1 hoặc thấp hơn:** class/interface không tồn tại trong `spring-test` của phiên bản đó.
- **Nhầm mốc phiên bản:** `DynamicPropertyRegistry` và `@DynamicPropertySource` có từ 5.2.5, còn `DynamicPropertyRegistrar` có từ 6.2.0.
- **Đưa registrar vào sai context:** bean không được phát hiện nếu test configuration không được nạp.
- **Cho rằng registrar tự khởi chạy resource:** registrar chỉ đăng ký property; resource cần lifecycle riêng.
- **Bỏ qua eager initialization:** dependency của registrar có thể được tạo sớm, làm server/container khởi động trong bootstrap context.
- **Tạo dependency vòng:** registrar inject consumer đang cần property mà registrar đăng ký.
- **Đăng ký cùng key ở nhiều nơi:** nguồn giá trị trở nên khó hiểu và khó chẩn đoán.
- **Đăng ký URL trước khi server sẵn sàng:** supplier được gọi khi resolve nhưng resource chưa được start đúng cách.
- **Để test rơi về URL production:** property thiếu có thể khiến client gọi nhầm hệ thống thật nếu có default nguy hiểm.
- **Không tính đến context cache:** container hoặc server có thể sống cùng context lâu hơn một test method.
- **Dùng registrar khi static `@DynamicPropertySource` đã phù hợp:** thêm bean và dependency không cần thiết cho một resource được quản lý ngoài context.

## 18. Quy trình chọn cơ chế dynamic property

Khi một test cần property runtime, hãy xác định nguồn giá trị trước:

1. **Giá trị cố định cho test:** dùng `@TestPropertySource`, `properties` trên annotation test hoặc file cấu hình test.
2. **Giá trị từ tài nguyên static/ngoài Spring context:** dùng `@DynamicPropertySource` với method `static`, chẳng hạn container được quản lý bởi JUnit Testcontainers extension.
3. **Giá trị từ bean trong test ApplicationContext:** dùng `DynamicPropertyRegistrar` trên Spring Framework 6.2 trở lên.
4. **Resource cần start/stop:** quản lý lifecycle bằng Spring bean hoặc test extension; registrar chỉ đọc giá trị của resource.
5. **Consumer cần property lúc khởi tạo:** bảo đảm registrar đăng ký property trước singleton consumer và không tạo vòng phụ thuộc.
6. **Ứng dụng dùng phiên bản cũ hơn 6.2:** tiếp tục dùng `@DynamicPropertySource` hoặc nâng Spring Framework theo dependency management tương thích.

`DynamicPropertyRegistrar` mở rộng dynamic property testing bằng cách đưa việc đăng ký property vào trong `ApplicationContext`. Từ Spring Framework 6.2.0, registrar bean có thể lấy giá trị từ các bean khác, đăng ký supplier vào `Environment` và cung cấp cấu hình runtime cho những singleton được khởi tạo sau đó. Hãy chú ý eager initialization, lifecycle của resource, thứ tự resolve và độ ưu tiên property để test tích hợp dùng đúng tài nguyên mà nó quản lý.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Context Configuration with Dynamic Property Sources (6.2)](https://www.springframework.org/spring/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [DynamicPropertyRegistrar Javadoc (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/test/context/DynamicPropertyRegistrar.html)
- [Spring Framework 6.2 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
