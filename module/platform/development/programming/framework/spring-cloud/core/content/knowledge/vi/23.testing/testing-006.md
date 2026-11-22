# Cấp thuộc tính kiểm thử bằng TestPropertySource và DynamicPropertySource

Khi kiểm thử ứng dụng Spring Boot hoặc Spring Cloud, nhiều bean và auto-configuration phụ thuộc vào giá trị trong `Environment`. Ví dụ, service discovery cần URI của mock service, HTTP client cần endpoint và timeout, Config Client cần được cô lập khỏi môi trường bên ngoài, hoặc integration cần host/port do Testcontainers cấp khi khởi động.

Spring Test cung cấp hai cách quan trọng để đưa property vào test context. **`@TestPropertySource`** nạp giá trị cố định từ resource hoặc khai báo trực tiếp trong test. **`@DynamicPropertySource`** đăng ký supplier để cung cấp giá trị tại thời điểm property được đọc. Chọn đúng cách giúp test có cấu hình rõ ràng, tái lập được và không phụ thuộc vào máy chạy.

Bài học thuộc chương **Kiểm thử** của module `SPRING_CLOUD_CORE`. Nội dung giải thích cách sử dụng hai annotation, thứ tự ưu tiên property, kế thừa cấu hình giữa các test class, tích hợp Testcontainers, tương tác với Spring Cloud Config và các vấn đề thường gặp khi Spring Test tái sử dụng ApplicationContext.

## 1. Vì sao cần cấp property riêng cho test?

Ứng dụng thực tế thường lấy cấu hình từ nhiều nguồn: `application.yml`, profile, biến môi trường, system property, command line hoặc Config Server. Khi chạy test, dùng nguyên cấu hình production/development có thể khiến test:

- Kết nối nhầm database, Redis hoặc service discovery thật.
- Phụ thuộc port cố định có thể đã bị process khác sử dụng.
- Không tái lập được khi chạy trên CI.
- Bị ảnh hưởng bởi biến môi trường của máy lập trình.
- Khởi tạo auto-configuration không phù hợp với mục tiêu test.

Thay vì sửa file cấu hình chính cho từng test, Spring Test cho phép thêm property source vào context riêng của test class. Các giá trị này được đưa vào `Environment` trước khi bean được tạo, nên có thể ảnh hưởng đến `@ConfigurationProperties`, `@ConditionalOnProperty`, auto-configuration và cấu hình client.

Ví dụ muốn test client gọi một catalog server giả:

```yaml
catalog:
  client:
    base-url: http://localhost:18081
    connect-timeout: 500ms
    read-timeout: 2s
```

Các giá trị trên chỉ dành cho test. Có thể khai báo bằng `@TestPropertySource` hoặc cung cấp URL động từ server test.

## 2. @TestPropertySource là gì?

`@TestPropertySource` thuộc Spring TestContext Framework, package `org.springframework.test.context`. Annotation này thêm property source vào `Environment` của `ApplicationContext` được tạo cho test.

Có hai cách khai báo chính:

1. `locations`: nạp một hoặc nhiều file properties/XML properties từ classpath hoặc filesystem.
2. `properties`: khai báo inline các cặp key/value ngay trên annotation.

Ví dụ inline:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.base-url=http://localhost:18081",
        "catalog.client.connect-timeout=500ms",
        "catalog.client.read-timeout=2s"
})
class CatalogClientTest {
}
```

Các property có hiệu lực khi Spring tạo test context. Bean đọc `catalog.client.base-url` sẽ nhận URL test thay vì giá trị từ cấu hình ứng dụng có precedence thấp hơn.

### 2.1. Nạp từ file resource

Khi nhiều test dùng chung một bộ cấu hình, có thể đặt property vào file riêng:

```properties
# src/test/resources/catalog-test.properties
catalog.client.base-url=http://localhost:18081
catalog.client.connect-timeout=500ms
catalog.client.read-timeout=2s
spring.cloud.config.enabled=false
```

Sau đó:

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties"
)
class CatalogClientIntegrationTest {
}
```

Đường dẫn `classpath:` giúp resource được tìm trong test classpath. Có thể khai báo nhiều location nếu test cần ghép nhiều bộ cấu hình. Resource locations hỗ trợ các định dạng properties mà Spring TestContext Framework quy định; không nên giả định mọi định dạng cấu hình của Spring Boot đều là định dạng được `@TestPropertySource` đọc trực tiếp.

### 2.2. Khai báo cả locations và properties

Có thể kết hợp file chung với override riêng cho một test:

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties",
        properties = {
                "catalog.client.read-timeout=100ms",
                "catalog.client.mode=stub"
        }
)
class FastCatalogClientTest {
}
```

Giá trị inline trong `properties` có precedence cao hơn giá trị lấy từ resource location trong cùng nhóm `@TestPropertySource`. Vì vậy, ví dụ trên ghi đè read timeout trong file.

### 2.3. Giá trị mặc định theo tên test class

Nếu không khai báo `locations` hoặc `properties`, Spring Test có thể tìm file properties mặc định tương ứng với tên đầy đủ của test class trong cùng package. Cách này hữu ích cho test có cấu hình riêng, nhưng làm tên resource gắn chặt với tên class. Với cấu hình được chia sẻ giữa nhiều test, khai báo `locations` tường minh thường dễ theo dõi hơn.

## 3. Cách hoạt động của @TestPropertySource

Khi TestContext Framework tạo `ApplicationContext` cho test, property source được đăng ký trước khi bean cần cấu hình được khởi tạo. Vì vậy, điều kiện auto-configuration có thể nhìn thấy các giá trị test.

Ví dụ một configuration có điều kiện:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.client",
        name = "stub",
        havingValue = "true"
)
class CatalogStubConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return new StubCatalogGateway();
    }
}
```

Test bật stub:

```java
@SpringBootTest
@TestPropertySource(properties = "catalog.client.stub=true")
class CatalogStubConfigurationTest {
    // Context được tạo với stub property đã có.
}
```

Điều kiện được đánh giá trong quá trình tạo context. Không cần sửa `Environment` sau khi bean đã được tạo để bật configuration này.

### 3.1. Dùng với Spring Boot test

Có thể kết hợp với `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc test slice khác nếu test đó tạo context Spring và hỗ trợ TestContext Framework.

Ví dụ:

```java
@WebMvcTest(CatalogController.class)
@TestPropertySource(properties = {
        "catalog.client.enabled=false"
})
class CatalogControllerTest {
}
```

Với test slice, chỉ một phần auto-configuration được nạp. Property source vẫn được thêm vào test context, nhưng không có nghĩa toàn bộ application configuration đã được bật.

### 3.2. Property phải có trước khi context refresh

Không nên dùng `@TestPropertySource` như API để thay đổi property sau khi context đã khởi tạo. Annotation mô tả cấu hình đầu vào cho test context; nó không phải cơ chế runtime refresh.

Nếu cần kiểm tra hành vi sau khi cấu hình thay đổi, hãy dùng cơ chế refresh hoặc bean có thể cập nhật trạng thái, rồi kiểm thử lifecycle đó riêng. Không mong đợi việc sửa annotation trong lúc test đang chạy sẽ tạo lại bean.

## 4. Thứ tự ưu tiên property

Khi nhiều nguồn khai báo cùng một key, giá trị được dùng phụ thuộc precedence của property source.

Trong TestContext Framework, các điểm quan trọng cần nhớ:

1. Property động được đăng ký bằng `@DynamicPropertySource` có precedence cao hơn property khai báo bằng `@TestPropertySource`.
2. Inline properties trong `@TestPropertySource(properties=...)` có precedence cao hơn resource locations trong `@TestPropertySource(locations=...)`.
3. Property test có precedence cao hơn các nguồn cấu hình thông thường như system properties, environment variables và application property sources theo quy tắc của test context.
4. Nếu một test còn kết hợp các thuộc tính riêng của Spring Boot như `@SpringBootTest(properties=...)`, hãy xác nhận giá trị hiệu lực bằng `Environment` thay vì suy luận chỉ từ thứ tự annotation.

Ví dụ cùng một key được khai báo ở file và inline:

```properties
# catalog-test.properties
catalog.client.mode=real
catalog.client.read-timeout=2s
```

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties",
        properties = "catalog.client.mode=stub"
)
class CatalogClientTest {
}
```

Trong test này, `catalog.client.mode` có giá trị `stub` do inline test property có precedence cao hơn resource location.

### 4.1. Kiểm tra giá trị thực tế

Khi cần chẩn đoán, inject `Environment`:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.mode=stub"
})
class CatalogPropertyTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestProperty() {
        assertThat(environment.getProperty("catalog.client.mode"))
                .isEqualTo("stub");
    }
}
```

Đây là cách kiểm tra giá trị đã resolve. Nếu test có nhiều nguồn cấu hình, có thể kiểm tra thêm property sources trong `ConfigurableEnvironment` để xác định nguồn nào đang thắng. Tránh dump toàn bộ environment ra log vì có thể chứa password hoặc token.

## 5. Kế thừa cấu hình @TestPropertySource

Các test class có thể kế thừa cấu hình từ superclass. Mặc định, resource locations và inline properties được kế thừa.

Hai thuộc tính điều khiển việc kế thừa:

| Thuộc tính | Mặc định | Tác động khi đặt false |
| --- | --- | --- |
| `inheritLocations` | `true` | Không kế thừa locations từ superclass |
| `inheritProperties` | `true` | Không kế thừa inline properties từ superclass |

Ví dụ superclass cung cấp cấu hình chung:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.mode=stub",
        "catalog.client.connect-timeout=500ms"
})
abstract class BaseCatalogTest {
}
```

Test con kế thừa và ghi đè:

```java
@TestPropertySource(properties = {
        "catalog.client.read-timeout=100ms"
})
class FastCatalogTest extends BaseCatalogTest {
}
```

Test con có cả cấu hình từ superclass và property bổ sung của chính nó. Khi cùng key được khai báo ở cấp con và cấp cha, cấu hình cấp con được dùng theo quy tắc kế thừa của TestContext Framework.

### 5.1. Tắt kế thừa có chủ đích

```java
@TestPropertySource(
        properties = "catalog.client.mode=real",
        inheritProperties = false
)
class RealCatalogTest extends BaseCatalogTest {
}
```

Khi `inheritProperties=false`, test con không nhận inline properties từ superclass. Điều này hữu ích khi test cần một bộ cấu hình độc lập, nhưng có thể làm mất các property nền mà test khác đang dựa vào.

Tương tự, `inheritLocations=false` chỉ ngăn kế thừa resource locations. Hai thuộc tính điều khiển hai nhóm riêng biệt; đặt một thuộc tính không tự tắt nhóm còn lại.

### 5.2. Nhiều annotation và composition

`@TestPropertySource` có thể được dùng lặp lại hoặc qua annotation tổng hợp/meta-annotation theo khả năng của Spring Test phiên bản đang dùng. Khi cấu hình phức tạp, nên gom các property dùng chung thành annotation test riêng có tên thể hiện mục đích, nhưng cần kiểm tra thứ tự và inheritance để tránh test nhận property ngoài dự kiến.

## 6. @DynamicPropertySource là gì?

`@DynamicPropertySource` là annotation của Spring TestContext Framework, được bổ sung từ Spring Framework 5.2.5. Nó đánh dấu một static method nhận `DynamicPropertyRegistry` và đăng ký property bằng supplier.

Khác với inline property cố định, supplier có thể lấy giá trị chỉ có sau khi resource test được khởi động. Ví dụ, Testcontainers cấp port ngẫu nhiên khi map cổng container ra host; test không thể biết port đó trước khi container chạy.

Cấu trúc:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", () -> "http://localhost:18081");
}
```

Phương thức phải là `static` và nhận `DynamicPropertyRegistry`. Với mỗi key, gọi `registry.add(name, supplier)` để đăng ký nguồn cung cấp giá trị.

### 6.1. Supplier được đánh giá khi property được resolve

`DynamicPropertyRegistry` nhận supplier thay vì bắt buộc nhận giá trị đã tính ngay. Supplier được gọi khi property được resolve. Điều này phù hợp với giá trị runtime như host, mapped port hoặc URL do test server cấp.

Ví dụ:

```java
registry.add("catalog.client.base-url", mockServer::baseUrl);
```

Nếu gọi `mockServer.baseUrl()` trước khi server khởi động và truyền giá trị tĩnh, test có thể nhận port chưa được cấp. Dùng method reference giúp lấy giá trị khi Spring cần resolve property.

Tính lazy không có nghĩa Spring tự refresh mọi bean khi supplier đổi giá trị. Nó chỉ mô tả cách property source lấy giá trị; bean đã khởi tạo không tự được tạo lại chỉ vì giá trị supplier thay đổi.

### 6.2. Có thể đăng ký nhiều property

```java
@DynamicPropertySource
static void catalogProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.host", mockServer::getHostName);
    registry.add("catalog.client.port", mockServer::getPort);
    registry.add("catalog.client.base-url", mockServer::baseUrl);
}
```

Mỗi supplier nên trả kiểu giá trị phù hợp với property consumer. Có thể đăng ký String, Integer, Boolean hoặc kiểu có thể chuyển đổi theo cơ chế conversion của Spring. Hãy giữ supplier đơn giản, ổn định và không tạo side effect.

## 7. Dùng DynamicPropertySource với Testcontainers

Testcontainers thường cấp port động để tránh xung đột giữa các test hoặc process CI. `@DynamicPropertySource` là cách tiêu chuẩn để đưa địa chỉ container vào Spring test context.

Ví dụ Redis:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RedisIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                redis::getFirstMappedPort
        );
    }

    @Test
    void applicationCanUseRedis() {
        // Test tương tác với bean Redis của ứng dụng.
    }
}
```

Testcontainers khởi động container theo lifecycle của JUnit extension. Supplier lấy host và mapped port mà container được cấp, sau đó Spring Boot bind các property Redis trước khi tạo bean cần kết nối.

Tên property Redis tùy Spring Boot version và Redis client configuration. Với ứng dụng dùng property prefix khác, hãy đăng ký đúng key mà bean configuration thực tế đọc.

### 7.1. Không giả định port cố định

Không viết `localhost:6379` khi Testcontainers đang map cổng động. Port bên trong container là 6379, nhưng host port có thể là một số khác. Dùng `getHost()` và `getFirstMappedPort()` để lấy endpoint thực tế.

### 7.2. Container phải sẵn sàng khi supplier được resolve

Supplier không tự khởi động container. Testcontainers lifecycle phải bảo đảm container đang chạy trước khi ứng dụng dùng property để tạo connection. Nếu tự quản lý container thủ công, hãy start container trước khi Spring context cần resolve property và stop nó sau test.

### 7.3. Có thể dùng cho database, broker và mock server

Cùng mẫu này áp dụng cho PostgreSQL, Kafka, RabbitMQ, WireMock hoặc một service giả khác:

```java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", mockServer::baseUrl);
    registry.add("catalog.client.connect-timeout", () -> "300ms");
}
```

Điểm quan trọng là supplier lấy endpoint thực tế sau khi resource được cấp. Không đưa credential hoặc token nhạy cảm vào log khi debug các property này.

## 8. So sánh TestPropertySource và DynamicPropertySource

| Tiêu chí | `@TestPropertySource` | `@DynamicPropertySource` |
| --- | --- | --- |
| Cách cấp giá trị | Inline hoặc resource location | Supplier đăng ký trong static method |
| Giá trị | Thường cố định theo test | Có thể phụ thuộc resource runtime |
| Thời điểm lấy | Nạp như test property source khi tạo context | Supplier được gọi khi property được resolve |
| Dùng với Testcontainers | Có thể dùng nếu endpoint biết trước | Phù hợp khi host/port được cấp động |
| Kế thừa | Có `inheritLocations`, `inheritProperties` | Static method có thể được kế thừa từ superclass |
| Precedence | Cao hơn property sources ứng dụng; inline cao hơn resource | Cao hơn `@TestPropertySource` |
| Mục tiêu thường gặp | Feature flag, timeout, profile test, endpoint cố định | Container port, mock server URL, endpoint cấp runtime |

Quy tắc chọn:

- Dùng `@TestPropertySource` khi biết trước giá trị và muốn cấu hình test rõ ràng, dễ đọc.
- Dùng `@DynamicPropertySource` khi giá trị phụ thuộc resource được tạo lúc chạy test.
- Có thể kết hợp cả hai: file chứa cấu hình chung, dynamic property ghi đè endpoint động.
- Tránh dùng supplier cho một giá trị cố định nếu inline property đã đủ rõ.

## 9. Kết hợp hai nguồn và kiểm tra precedence

Ví dụ file test đặt endpoint mặc định, còn container cung cấp endpoint thật:

```properties
# catalog-integration.properties
catalog.client.base-url=http://localhost:18081
catalog.client.connect-timeout=500ms
catalog.client.read-timeout=2s
```

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-integration.properties"
)
@Testcontainers
class CatalogIntegrationTest {

    @Container
    static final GenericContainer<?> catalog =
            new GenericContainer<>("example/catalog-test:latest")
                    .withExposedPorts(8080);

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.client.base-url",
                () -> "http://" + catalog.getHost()
                        + ":" + catalog.getFirstMappedPort()
        );
    }
}
```

`catalog.client.base-url` được cung cấp từ dynamic source và có precedence cao hơn giá trị trong file. Các property timeout vẫn đến từ resource.

Cách kết hợp này hữu ích khi phần lớn test configuration dùng chung, chỉ một vài endpoint được cấp động. Không cần sao chép toàn bộ property file vào từng test class.

## 10. Tương tác với Spring Cloud Config

Ứng dụng Spring Cloud có thể nạp remote property từ Config Server. Test tích hợp thường cần kiểm soát việc này để không phụ thuộc server cấu hình bên ngoài.

Có thể override các feature flag hoặc endpoint liên quan trong test:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "spring.cloud.config.enabled=false",
        "catalog.client.mode=stub",
        "catalog.client.base-url=http://localhost:18081"
})
class IsolatedCatalogTest {
}
```

Việc vô hiệu hóa Config Client cần phù hợp với cách ứng dụng đang nạp cấu hình và phiên bản Spring Cloud Config. Nếu ứng dụng dùng Config Data import, hãy kiểm tra log khởi động và cơ chế import thực tế; chỉ đặt một property không bảo đảm mọi cấu hình từ xa đã bị loại trong mọi setup.

Trong test cần kiểm tra chính Config Client hoặc Config Server, không nên tắt integration. Thay vào đó, dùng mock server hoặc Config Server test riêng và cấp endpoint qua test property source.

### 10.1. Test property có thể ảnh hưởng auto-configuration

Property như `spring.cloud.discovery.enabled`, `spring.cloud.config.enabled` hoặc feature flag riêng có thể làm condition match/unmatch trước khi bean được tạo. Vì vậy, test phải đặt đúng property trước khi context refresh.

### 10.2. Không dùng property test để che lỗi cấu hình production

Test cô lập dependency ngoài để kiểm tra logic riêng là hợp lý. Nhưng nếu mục tiêu là xác minh cấu hình production, phải có integration test kiểm tra property thật hoặc profile triển khai tương ứng. Nếu mọi test đều override endpoint và tắt integration, lỗi cấu hình ở môi trường thật có thể không được phát hiện.

## 11. Context cache và dynamic property inheritance

Spring TestContext Framework cache `ApplicationContext` để giảm thời gian chạy test. Các test có cùng cấu hình context có thể dùng chung context đã tạo.

Điều này đặc biệt quan trọng khi dùng `@DynamicPropertySource` trong superclass:

```java
abstract class BaseCatalogIntegrationTest {

    static MockWebServer server;

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url", () ->
                server.url("/").toString());
    }
}
```

Nếu nhiều subclass dùng chung method nhưng mỗi subclass khởi tạo server hoặc endpoint khác nhau, context cache có thể tái sử dụng context được tạo với dynamic property từ test trước. Khi đó test sau có thể gọi nhầm server hoặc port cũ.

### 11.1. Dùng @DirtiesContext khi cấu hình động thực sự khác nhau

Nếu các subclass cần giá trị dynamic khác nhau và không thể dùng chung context, có thể đánh dấu context cần loại khỏi cache bằng `@DirtiesContext` ở vị trí phù hợp, thường là base test class hoặc class có cấu hình thay đổi.

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class IsolatedCatalogEndpointTest extends BaseCatalogIntegrationTest {
}
```

`@DirtiesContext` làm context bị đóng và loại khỏi cache theo mode được chọn; việc tạo context mới có chi phí. Không nên thêm annotation này cho mọi test một cách máy móc. Tốt hơn là nhóm test có cùng endpoint vào cùng context hoặc tạo cấu hình test tách biệt có chủ đích.

### 11.2. Supplier không làm cache tự phân biệt mọi giá trị runtime

Spring dùng metadata cấu hình test để xác định context có thể tái sử dụng. Không nên dựa vào giả định rằng hai supplier có cùng method nhưng trả giá trị khác nhau sẽ luôn khiến Spring tạo context mới. Nếu endpoint thay đổi theo subclass, hãy thiết kế cache boundary rõ ràng và kiểm thử việc tái sử dụng.

## 12. Kế thừa DynamicPropertySource

Một static method `@DynamicPropertySource` trong superclass có thể được kế thừa bởi các test class con. Điều này hữu ích khi một nhóm test dùng chung container hoặc mock service.

Ví dụ:

```java
abstract class BaseRedisIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                redis::getFirstMappedPort
        );
    }
}
```

Các subclass có thể dùng chung endpoint Redis. Khi tất cả subclass dùng cùng một container lifecycle và cùng cấu hình, chia sẻ context có thể giảm thời gian test.

Nếu mỗi subclass cần container khác nhau hoặc giá trị khác nhau, không nên để inheritance và context cache tạo ra sự phụ thuộc khó thấy. Tách test class/configuration hoặc dùng `@DirtiesContext` khi cần.

## 13. Kiểm thử property và bean được cấu hình

Không chỉ xác nhận property đã được đọc; nên xác nhận bean sử dụng giá trị đó đúng cách.

Ví dụ properties class:

```java
@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(1);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
```

Test:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.base-url=http://localhost:18081",
        "catalog.client.connect-timeout=250ms"
})
class CatalogClientPropertiesTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsTestValues() {
        assertThat(properties.getBaseUrl())
                .isEqualTo(URI.create("http://localhost:18081"));
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofMillis(250));
    }
}
```

Test này xác nhận property binding. Nếu mục tiêu là kiểm tra HTTP client thật, cần thêm mock server và xác nhận request được gửi tới endpoint động. Nếu mục tiêu là condition, kiểm tra bean có/không có trong context.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Bean nhận giá trị từ application.yml thay vì test value | Annotation đặt sai test class, context không dùng annotation hoặc key không đúng | Kiểm tra test context, key đầy đủ và Environment |
| Inline property không ghi đè file | Nhầm property key hoặc source khác có precedence cao hơn | Kiểm tra giá trị resolve và property sources |
| Dynamic property trả port 0 hoặc port cũ | Supplier được gọi khi resource chưa sẵn sàng hoặc context cache giữ endpoint cũ | Kiểm tra lifecycle container và context reuse |
| `@DynamicPropertySource` không được phát hiện | Method không static hoặc signature sai | Dùng static method nhận `DynamicPropertyRegistry` |
| Testcontainers kết nối localhost sai | Dùng container port thay host mapped port hoặc host không đúng | Dùng `getHost()` và `getFirstMappedPort()` |
| Test con thiếu property từ superclass | Đặt `inheritProperties=false` hoặc `inheritLocations=false` | Kiểm tra inheritance flags |
| Test bị ảnh hưởng bởi test trước | Dùng system property/global state hoặc context cache không phù hợp | Dùng test property source và quản lý context lifecycle |
| Config Server vẫn được gọi trong test | Config Data import hoặc setup Config Client chưa được vô hiệu hóa đúng | Kiểm tra log import và version-specific Config Client behavior |
| Bean condition không match | Property được thêm sau khi context đã refresh | Cấp property trước startup và kiểm tra condition report |
| Hai subclass dùng nhầm endpoint | Dynamic property method kế thừa nhưng context được cache dùng chung | Tách context hoặc dùng `@DirtiesContext` phù hợp |
| Test chạy local nhưng fail trên CI | Port cố định, phụ thuộc service cài sẵn hoặc env khác | Dùng port động, container và property supplier |

Trình tự điều tra:

1. Xác định test class nào đang tạo context và annotation nào có hiệu lực.
2. Kiểm tra property key chính xác và giá trị trong `Environment`.
3. Xem property đến từ `@DynamicPropertySource`, inline test property hay resource.
4. Kiểm tra precedence giữa dynamic source và test property source.
5. Kiểm tra supplier có trả giá trị đúng tại thời điểm được resolve.
6. Xác nhận container/mock server đã start và port mapping đã hoàn tất.
7. Kiểm tra context cache và inheritance giữa superclass/subclass.
8. Xem condition evaluation report nếu bean không được tạo.
9. Đảm bảo test không sửa global system property hoặc dùng chung mutable state.

## 15. Thực hành: test Spring Cloud client với endpoint động

Giả sử `order-service` gọi `catalog-service` qua một HTTP client. Test muốn chạy một mock server trên port ngẫu nhiên và cấp URL cho Spring context.

### Bước 1 — Tạo mock server

Dùng WireMock, MockWebServer hoặc một HTTP server test phù hợp. Server cần được start trước khi Spring resolve property `catalog.client.base-url`.

### Bước 2 — Đăng ký property động

```java
@SpringBootTest
class CatalogClientIntegrationTest {

    static final MockWebServer server = startServer();

    private static MockWebServer startServer() {
        try {
            MockWebServer value = new MockWebServer();
            value.start();
            return value;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @AfterAll
    static void stopServer() throws IOException {
        server.shutdown();
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.client.base-url",
                () -> server.url("/").toString()
        );
    }
}
```

Đây là skeleton minh họa với MockWebServer; cần dependency test phù hợp và bảo đảm server start trước khi Spring cần resolve supplier. Với Testcontainers, có thể dùng static `@Container` để quản lý lifecycle.

### Bước 3 — Cấp property cố định bằng TestPropertySource

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.connect-timeout=300ms",
        "catalog.client.read-timeout=1s",
        "catalog.client.retry.enabled=false"
})
class CatalogClientIntegrationTest {
    // Có thể kết hợp với DynamicPropertySource trong cùng test class.
}
```

Endpoint được cấp động; timeout và retry flag được khai báo cố định. Hai annotation giải quyết hai loại dữ liệu khác nhau.

### Bước 4 — Xác nhận request

Đăng ký response giả cho path catalog, gọi service client và xác nhận request đi tới mock server. Test nên kiểm tra method, path, query và payload cần thiết, không chỉ kiểm tra bean đã khởi tạo.

### Bước 5 — Kiểm tra tính cô lập

Chạy test độc lập và chạy cả suite. Xác nhận:

- Không kết nối service catalog thật.
- Port được cấp động, không xung đột.
- Test không phụ thuộc thứ tự chạy.
- Context cache không khiến test dùng endpoint của class khác.
- Server được đóng sau test.
- Giá trị test không rò sang JVM hoặc test class khác.

### Câu hỏi tự kiểm tra

1. `@TestPropertySource` thuộc framework nào và thêm property vào đâu?
2. Hai cách khai báo chính của `@TestPropertySource` là gì?
3. Inline properties và resource locations có thứ tự ưu tiên thế nào?
4. `inheritLocations` và `inheritProperties` điều khiển điều gì?
5. Vì sao `@DynamicPropertySource` dùng static method?
6. `DynamicPropertyRegistry.add` nhận supplier để giải quyết vấn đề gì?
7. Vì sao Testcontainers phù hợp với `@DynamicPropertySource`?
8. Property động có tự làm bean được tạo lại khi supplier trả giá trị mới không?
9. Dynamic property và `@TestPropertySource` có precedence thế nào?
10. Vì sao context cache có thể khiến subclass dùng nhầm endpoint?
11. Khi nào nên dùng `@DirtiesContext`?
12. Vì sao cần kiểm tra giá trị trong `Environment` thay vì chỉ nhìn annotation?

**Gợi ý đáp án:** (1) Spring TestContext Framework; nó thêm property source vào Environment của test context; (2) `locations` và `properties`; (3) Inline properties có precedence cao hơn resource locations; (4) Kế thừa file cấu hình và inline property từ superclass; (5) Spring cần đăng ký supplier trước khi context được tạo, theo contract static của annotation; (6) Để lấy giá trị chỉ có lúc runtime như host/port; (7) Container cấp mapped port khi khởi động; (8) Không, supplier lazy không đồng nghĩa bean tự refresh; (9) Dynamic property có precedence cao hơn; (10) Context đã tạo có thể được tái sử dụng với cấu hình endpoint cũ; (11) Khi test cần context mới do dynamic configuration khác nhau; (12) Để biết property source và giá trị thực sự được resolve.

## 16. Những nguyên tắc cần nhớ

- `@TestPropertySource` cấp property cố định qua resource location hoặc inline properties cho Spring test context.
- Inline `properties` có precedence cao hơn resource `locations` trong cùng cấu hình.
- Property test có thể điều khiển `@ConfigurationProperties`, `@ConditionalOnProperty` và auto-configuration trước khi bean được tạo.
- `inheritLocations` và `inheritProperties` mặc định cho phép kế thừa cấu hình từ superclass.
- `@DynamicPropertySource` dùng static method nhận `DynamicPropertyRegistry` để đăng ký supplier.
- Supplier phù hợp với host, port và endpoint được cấp khi test resource khởi động.
- Dynamic property có precedence cao hơn `@TestPropertySource`.
- Supplier được resolve lazy nhưng không tự làm bean đã tạo được refresh.
- Testcontainers cần cung cấp host và mapped port thực tế; không giả định port host cố định.
- Spring Test context cache có thể giữ cấu hình dynamic cũ nếu nhiều subclass dùng chung context nhưng cần endpoint khác nhau.
- Dùng `@DirtiesContext` có chủ đích khi cần loại context khỏi cache; ưu tiên thiết kế test dùng chung context khi cấu hình thực sự giống nhau.
- Kiểm tra giá trị hiệu lực trong `Environment`, test cả property binding, bean condition và request thực tế.

Dùng `@TestPropertySource` cho cấu hình cố định và `@DynamicPropertySource` cho endpoint runtime giúp Spring Cloud test không phụ thuộc hạ tầng đang chạy trên máy phát triển. Khi kiểm soát precedence, lifecycle resource và context cache, test có thể chạy ổn định trên local lẫn CI và xác minh đúng hành vi của cấu hình trước khi phát hành.

## Tài liệu tham khảo

- [Spring Framework Reference — Context Configuration with TestPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework API — TestPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestPropertySource.html)
- [Spring Framework API — DynamicPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertySource.html)
- [Testcontainers for Java](https://java.testcontainers.org/)
