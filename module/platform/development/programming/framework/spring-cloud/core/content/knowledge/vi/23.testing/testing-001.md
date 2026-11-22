# Phân tầng kiểm thử thuộc tính, context và tích hợp

Ứng dụng Spring Cloud nhận cấu hình từ nhiều nguồn và phối hợp nhiều thành phần như Spring Cloud Context, Config Client, service discovery và LoadBalancer. Một lỗi có thể bắt đầu từ property chưa được bind, profile được chọn sai, bean không được tạo, refresh không dựng lại target, hoặc registry trả về instance mà consumer không gọi được.

Không nên kiểm tra mọi tình huống bằng một bài **@SpringBootTest** lớn. Hãy chọn tầng kiểm thử theo hành vi cần chứng minh: kiểm tra property và auto-configuration bằng context nhỏ; kiểm tra vòng đời bean trong Spring context; kiểm tra Config Server, registry và HTTP qua integration test có kiểm soát.

Bài học thuộc chương **Kiểm thử** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào cách tổ chức test cho cấu hình ngoài, Spring Cloud Context, Config Client/Server, service discovery và load balancing; cách chọn test fixture; và cách tránh test chậm, phụ thuộc môi trường hoặc tạo kết quả không ổn định.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt unit test, property binding test, context test và integration test.
- Kiểm tra **@ConfigurationProperties**, validation, profile và property precedence.
- Dùng **ApplicationContextRunner** để kiểm tra bean và auto-configuration trong context nhỏ.
- Chọn đúng giữa **@SpringBootTest**, test slice và **@TestConfiguration**.
- Kiểm tra **@RefreshScope** và quá trình làm mới target bean.
- Kiểm thử Config Client với Config Server giả lập hoặc thật.
- Kiểm thử service discovery và Spring Cloud LoadBalancer mà không phụ thuộc registry production.
- Dùng **@DynamicPropertySource** để truyền địa chỉ/port động của tài nguyên test.
- Thiết kế test cho trường hợp lỗi, timeout, thiếu instance và cấu hình không hợp lệ.
- Giữ test độc lập, có thể lặp lại và phù hợp chạy trong CI.

## 2. Chọn tầng kiểm thử theo câu hỏi cần trả lời

Mỗi tầng trả lời một loại câu hỏi khác nhau:

| Tầng | Câu hỏi chính | Công cụ thường dùng | Phạm vi |
| --- | --- | --- | --- |
| Unit test | Logic thuần có đúng không? | JUnit, Mockito, AssertJ | Một class hoặc hàm, không khởi tạo Spring |
| Property test | Giá trị có bind/validate đúng không? | Binder, ApplicationContextRunner | Environment, ConfigurationProperties |
| Context test | Bean, condition và scope có hoạt động không? | ApplicationContextRunner, SpringBootTest | Một phần hoặc toàn bộ ApplicationContext |
| Integration test | Các thành phần có giao tiếp đúng qua ranh giới thật không? | SpringBootTest, WireMock, Testcontainers | HTTP, Config Server, registry, database |
| Contract test | Hai dịch vụ có giữ đúng hợp đồng API không? | Spring Cloud Contract hoặc test hợp đồng tương đương | Provider và consumer |

Hãy bắt đầu từ tầng nhỏ nhất có thể chứng minh hành vi:

- Kiểm tra timeout được bind thành Duration không cần khởi động Config Server.
- Kiểm tra ConditionalOnProperty tạo bean hay không không cần mở cổng HTTP.
- Kiểm tra RefreshScope tạo lại target có thể thực hiện trong một context test.
- Kiểm tra Config Client gửi đúng application/profile đến Config Server cần một HTTP server giả lập hoặc Config Server thật.
- Kiểm tra instance đã đăng ký có truy cập được từ consumer cần kiểm thử qua network/registry tương ứng.

Một test chỉ chứng minh được phần mà nó thực sự chạy qua. ApplicationContextRunner không chứng minh Config Server hoạt động; mock DiscoveryClient không chứng minh registry production đăng ký đúng địa chỉ.

## 3. Kiểm thử ConfigurationProperties và validation

Các lớp cấu hình nên được kiểm thử độc lập với hạ tầng ngoài. Ví dụ một client nội bộ cần base URL và timeout:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "catalog.client")
@Validated
public record CatalogClientProperties(
        @NotBlank String baseUrl,
        @Min(1) @Max(5000) int timeoutMs) {
}
```

Đăng ký lớp properties trong context kiểm thử:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
class CatalogPropertiesTestConfiguration {
}
```

Dùng ApplicationContextRunner để tạo context nhỏ với các giá trị cụ thể:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientPropertiesTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(CatalogPropertiesTestConfiguration.class);

    @Test
    void bindsValidProperties() {
        contextRunner
            .withPropertyValues(
                "catalog.client.base-url=https://catalog.internal",
                "catalog.client.timeout-ms=800"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClientProperties properties =
                    context.getBean(CatalogClientProperties.class);

                assertThat(properties.baseUrl())
                    .isEqualTo("https://catalog.internal");
                assertThat(properties.timeoutMs()).isEqualTo(800);
            });
    }

    @Test
    void rejectsInvalidTimeout() {
        contextRunner
            .withPropertyValues(
                "catalog.client.base-url=https://catalog.internal",
                "catalog.client.timeout-ms=0"
            )
            .run(context -> assertThat(context).hasFailed());
    }
}
```

Để các annotation Jakarta Validation có hiệu lực, dự án cần Bean Validation implementation, thường được đưa vào qua **spring-boot-starter-validation**. Nếu thiếu implementation, test binding có thể chạy nhưng không kiểm tra constraint như mong muốn.

### 3.1. Kiểm tra giá trị mặc định và giá trị thiếu

Không chỉ kiểm tra trường hợp cấu hình đầy đủ. Nên có test cho:

- Property bị thiếu và trường có default.
- Property bị thiếu nhưng là bắt buộc.
- Chuỗi rỗng hoặc chỉ có khoảng trắng.
- Giá trị số nằm ngoài giới hạn.
- Enum không hợp lệ.
- Duration hoặc URI sai định dạng.
- Nested properties bị thiếu một phần.

Nếu constructor-bound record không có default, hãy xác nhận context thất bại với nguyên nhân dễ hiểu. Điều này giúp lỗi cấu hình được phát hiện lúc khởi động thay vì xuất hiện ở lần gọi dịch vụ đầu tiên.

### 3.2. Kiểm tra Binder trực tiếp

Khi chỉ cần xác nhận phép chuyển đổi và binding, có thể dùng Binder mà không tạo ApplicationContext:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

Map<String, Object> values = new HashMap<>();
values.put("catalog.client.base-url", "https://catalog.internal");
values.put("catalog.client.timeout-ms", "800");

ConfigurationPropertySource source =
    new MapConfigurationPropertySource(values);

CatalogClientProperties properties = new Binder(source)
    .bind("catalog.client", CatalogClientProperties.class)
    .orElseThrow();

assertThat(properties.timeoutMs()).isEqualTo(800);
```

Cách này nhanh và cô lập. Tuy nhiên, nó không kiểm tra EnableConfigurationProperties, Bean Validation trong context, component scan hoặc auto-configuration. Khi cần chứng minh những phần đó, dùng ApplicationContextRunner.

## 4. Kiểm thử property source, profile và precedence

Ứng dụng Spring Boot có thể nhận cấu hình từ nhiều nơi: Config Data, profile-specific file, environment variable, JVM system property, command-line argument, PropertySource và property source do test đăng ký.

Trong test, hãy đặt giá trị tường minh để kết quả không phụ thuộc máy developer hoặc runner CI.

### 4.1. Chọn profile kiểm thử

Dùng ActiveProfiles để xác định profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class CatalogConfigurationTests {
    // Test sử dụng application-test.yml và các test properties được khai báo.
}
```

File application-test.yml nên chứa giá trị dành riêng cho test, chẳng hạn URL của mock service, timeout ngắn và feature flag. Không đưa credential production vào test resource.

### 4.2. Ghi đè property trong test

@SpringBootTest(properties = ...) phù hợp khi cần vài giá trị inline:

```java
@SpringBootTest(properties = {
    "catalog.client.base-url=http://localhost:18081",
    "catalog.client.timeout-ms=300"
})
class CatalogClientContextTests {
}
```

TestPropertySource phù hợp khi muốn quản lý một file test riêng:

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/catalog-client-test.properties")
class CatalogClientPropertySourceTests {
}
```

Khi cần giá trị được cấp động từ Testcontainers, WireMock hoặc server có port ngẫu nhiên, dùng DynamicPropertySource:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class CatalogDatabaseIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("catalog")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

Ví dụ minh họa cách cấp endpoint động; cấu hình database thực tế còn cần database name, username và password tương ứng với container đã khởi tạo.

Dynamic properties có precedence cao hơn TestPropertySource, environment của hệ điều hành, system properties và property sources được khai báo qua PropertySource hoặc thêm bằng ứng dụng. Vì vậy, nếu một giá trị trong test không như dự kiến, hãy kiểm tra cả nguồn và thứ tự ưu tiên của nó.

### 4.3. Kiểm tra origin khi giá trị bị ghi đè

Khi test chỉ assert giá trị cuối cùng, bạn có thể bỏ sót việc nó đến từ nguồn không mong muốn. Với lỗi precedence, hãy kiểm tra Environment và origin/property source tương ứng, hoặc dùng Actuator env trong môi trường test được bảo vệ.

Ví dụ cần phân biệt:

- catalog.client.base-url đến từ application-test.yml.
- Cùng key được ghi đè bởi DynamicPropertySource.
- Một environment variable trên máy CI vô tình làm thay đổi kết quả.

Không dùng DynamicPropertySource cho mọi property chỉ vì tiện. Hãy dùng nó cho tài nguyên có địa chỉ/port chỉ biết được sau khi khởi động test fixture.

## 5. Dùng ApplicationContextRunner kiểm tra bean và auto-configuration

ApplicationContextRunner khởi tạo một context nhỏ, thực hiện callback kiểm tra rồi tự đóng context. Đây là công cụ phù hợp để kiểm tra:

- ConditionalOnProperty.
- ConditionalOnClass.
- Bean được tạo khi dependency có mặt.
- Bean mặc định bị lùi lại khi ứng dụng cung cấp bean riêng.
- Properties được bind vào auto-configuration.
- Context khởi động thất bại khi thiếu dependency hoặc cấu hình bắt buộc.

Ví dụ auto-configuration chỉ tạo bean khi feature được bật:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "catalog.cache",
    name = "enabled",
    havingValue = "true"
)
class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Test hai nhánh:

```java
class CatalogCacheConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(CatalogCacheConfiguration.class);

    @Test
    void createsCacheWhenEnabled() {
        runner.withPropertyValues("catalog.cache.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogCache.class);
            });
    }

    @Test
    void doesNotCreateCacheWhenDisabled() {
        runner.withPropertyValues("catalog.cache.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogCache.class);
            });
    }
}
```

Nếu kiểm tra auto-configuration của Spring Cloud, đưa đúng configuration cần kiểm tra vào runner và chỉ thêm những dependency/auto-configuration liên quan. Tránh nạp toàn bộ ứng dụng khi câu hỏi chỉ là một điều kiện tạo bean.

## 6. Chọn SpringBootTest hay test slice?

@SpringBootTest tạo ApplicationContext của ứng dụng hoặc cấu hình test được chỉ định. Dùng nó khi cần kiểm tra sự phối hợp của nhiều bean, Config Client, refresh scope hoặc HTTP server thực.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogApplicationIntegrationTests {
    // Kiểm tra ứng dụng đã khởi động và endpoint có thể được gọi qua HTTP.
}
```

Test slice chỉ nạp một phần ứng dụng:

| Annotation | Phạm vi |
| --- | --- |
| @WebMvcTest | Controller, MVC configuration, converter và filter thuộc lát cắt MVC |
| @DataJpaTest | Entity, repository và cấu hình JPA |
| @RestClientTest | Thành phần HTTP client theo hỗ trợ của Spring Boot version đang dùng |
| @JsonTest | Serialization/deserialization |
| @SpringBootTest | Toàn bộ ApplicationContext của ứng dụng |

Ví dụ @WebMvcTest phù hợp để kiểm tra controller trả đúng status và JSON. Nó không chứng minh Config Server, Eureka hoặc LoadBalancer được cấu hình đúng, vì các thành phần đó thường không nằm trong slice MVC.

### 6.1. Bổ sung cấu hình chỉ dành cho test

Dùng TestConfiguration để thêm bean giả hoặc fixture vào context test:

```java
@TestConfiguration(proxyBeanMethods = false)
class CatalogTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Import cấu hình này vào test bằng Import(CatalogTestConfiguration.class). Nested TestConfiguration được bổ sung vào cấu hình ứng dụng; nó không thay thế cấu hình chính như một nested Configuration thông thường có thể làm.

### 6.2. Hiểu context cache và DirtiesContext

Spring TestContext Framework cache ApplicationContext giữa các test có cấu hình tương đương. Điều này giúp giảm thời gian khởi động.

DirtiesContext đánh dấu context đã bị thay đổi và cần loại khỏi cache để tạo context mới cho lần dùng tiếp theo. Chỉ dùng khi test thật sự làm thay đổi trạng thái context không thể khôi phục an toàn, ví dụ thay đổi singleton bean hoặc cấu hình scope toàn cục.

Không thêm DirtiesContext vào mọi test để “chắc chắn sạch”. Nó làm suite chậm và có thể che giấu việc test đang chia sẻ mutable state.

## 7. Kiểm thử RefreshScope và việc tạo lại bean

RefreshScope tạo proxy cho bean và quản lý target đã khởi tạo. Khi target bị invalidate, lần gọi tiếp theo sẽ tạo target mới và chạy lại lifecycle của bean.

Có thể kiểm tra vòng đời này bằng cách cấp property động, thay giá trị rồi gọi RefreshScope.refresh(beanName):

```java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = RefreshScopeTestApplication.class)
class RefreshScopeTests {

    private static final AtomicReference<String> MESSAGE =
        new AtomicReference<>("before");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("catalog.message", MESSAGE::get);
    }

    @Autowired
    MessageProvider messageProvider;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void recreatesRefreshScopedTarget() {
        assertThat(messageProvider.message()).isEqualTo("before");

        MESSAGE.set("after");

        assertThat(refreshScope.refresh("messageProvider")).isTrue();
        assertThat(messageProvider.message()).isEqualTo("after");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class RefreshScopeTestApplication {

        @Bean
        @RefreshScope
        MessageProvider messageProvider(
                @Value("${catalog.message}") String message) {
            return () -> message;
        }
    }

    interface MessageProvider {
        String message();
    }
}
```

Test này chứng minh target của bean được tạo lại và nhận giá trị mới từ Environment. Nó chưa chứng minh Config Client đã gọi Config Server để tải property source mới.

### 7.1. Phân biệt refresh target và refresh Environment

Có hai phần cần kiểm tra riêng:

1. **Refresh scope:** target bean bị xóa khỏi cache và được tạo lại ở lần truy cập tiếp theo.
2. **Environment refresh:** property source được cập nhật, các property được rebind và sự kiện thay đổi được phát ra theo cơ chế refresh đang dùng.

Nếu chỉ gọi refreshScope.refresh("messageProvider"), bạn đang kiểm tra phần thứ nhất. Muốn kiểm tra toàn bộ đường đi từ cấu hình ngoài đến bean, cần một integration test thay đổi nguồn cấu hình, gọi cơ chế refresh phù hợp và xác nhận giá trị mới.

Một số điểm cần đưa vào test:

- Bean có thật sự nằm trong RefreshScope không?
- Tên bean truyền vào refresh(String) có đúng không?
- Bean có giữ giá trị đã bind trong một dependency không được refresh không?
- Bean có khởi tạo lại thành công không?
- Có property source nào ưu tiên cao hơn vẫn che giá trị mới không?

Spring Cloud không cập nhật sự hiện diện của một property chỉ vì khóa đó bị xóa khỏi nguồn rồi gọi refresh. Nếu nghiệp vụ cần trạng thái bật/tắt, hãy kiểm tra hành vi khi giá trị được đổi rõ ràng, thay vì chỉ dựa vào việc xóa khóa.

## 8. Kiểm thử Spring Cloud Config Client

Config Client nạp cấu hình từ Config Server qua Config Data import. Một integration test cần chứng minh ít nhất:

- spring.application.name được gửi đúng.
- Profile và label được chọn đúng.
- Property từ remote source xuất hiện trong Environment.
- Giá trị được bind vào bean như mong đợi.
- Hành vi khi Config Server không truy cập được phù hợp với optional: hoặc chế độ fail-fast.

Ví dụ cấu hình client trong test:

```properties
spring.application.name=orders
spring.profiles.active=integration
spring.config.import=configserver:http://localhost:18888
```

Có thể chạy một HTTP mock server như WireMock trên port test cố định hoặc khởi động trước khi Spring test context được tạo. Mock server trả về response Environment của Config Server cho các path tương ứng:

- /orders/default
- /orders/integration

Spring Boot Config Data có thể tải cấu hình theo hai lượt: lượt đầu với profile default, sau đó tải thêm các profile được kích hoạt. Vì vậy, mock server cần phục vụ các request mà client thực sự gửi, không chỉ giả định sẽ có đúng một request cho profile cuối cùng.

Response Environment có cấu trúc chứa tên ứng dụng, profile, label và danh sách propertySources. Ví dụ rút gọn:

```json
{
  "name": "orders",
  "profiles": ["integration"],
  "label": null,
  "version": "test-revision",
  "propertySources": [
    {
      "name": "orders-integration.yml",
      "source": {
        "catalog.page-size": 40
      }
    }
  ]
}
```

Sau khi context khởi động, kiểm tra property catalog.page-size trong Environment và bean ConfigurationProperties tương ứng. Đồng thời xác nhận request đã đến đúng path, application name và profile.

### 8.1. Kiểm tra Config Server không khả dụng

Chạy hai tình huống riêng:

| Cấu hình import | Kết quả mong đợi khi Config Server không khả dụng |
| --- | --- |
| spring.config.import=optional:configserver:http://localhost:18888 | Ứng dụng có thể tiếp tục khởi động mà không có remote properties |
| spring.config.import=configserver:http://localhost:18888 | Khởi động thất bại nếu không lấy được cấu hình bắt buộc |

Đừng dùng optional: trong mọi test. Nếu cấu hình production yêu cầu Config Server để có credential hoặc endpoint bắt buộc, test cần chứng minh ứng dụng fail khi nguồn cấu hình đó không sẵn sàng.

### 8.2. Kiểm thử Config Server riêng

Có thể kiểm tra Config Server với native/file-system backend trong test. Đặt profile native, trỏ spring.cloud.config.server.native.searchLocations tới thư mục fixture, khởi động server trên random port rồi gọi endpoint /{application}/{profile}/{label}.

Test phía server xác nhận:

- Repository fixture được đọc đúng.
- Application/profile/label chọn đúng file.
- Property source và precedence đúng.
- Giá trị mã hóa/giải mã được xử lý theo cấu hình test nếu có dùng encryption.

Test phía client xác nhận Config Client tiêu thụ response đó. Giữ hai bài test tách nhau giúp phân biệt lỗi repository/server với lỗi client import.

## 9. Kiểm thử Service Discovery và LoadBalancer

Một test discovery cần kiểm tra hai tầng:

1. Discovery trả về đúng danh sách ServiceInstance.
2. HTTP client dùng service ID để chọn và gọi một instance.

Khi không cần kiểm tra registry thật, có thể dùng SimpleDiscoveryClient với instance khai báo bằng test properties:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
```

Cấu hình này phù hợp cho test LoadBalancer mà không phải dựng Eureka hoặc Consul. SimpleDiscoveryClient được dùng khi không có discovery client dựa trên service registry trong classpath. Nếu test có Eureka/Consul client thật, hãy cấu hình hoặc mock đúng discovery implementation thay vì mặc định cho rằng simple client sẽ được chọn.

### 9.1. Kiểm tra request đi qua LoadBalancer

Với Spring Boot 3.2+ và Spring Framework 6.1+, có thể dùng @LoadBalanced RestClient.Builder. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class TestHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder(
            RestClientBuilderConfigurer configurer) {
        return configurer.configure(RestClient.builder());
    }
}
```

Client trong test phải gọi bằng service ID:

```java
String response = restClient.get()
    .uri("http://catalog-service/api/items")
    .retrieve()
    .body(String.class);
```

Hai HTTP server giả lập lắng nghe trên hai port. Cấu hình SimpleDiscoveryClient trỏ tới các port đó, rồi xác nhận request được nhận ở một instance thuộc danh sách.

Nếu dự án dùng Spring Boot cũ hơn 3.2, chọn RestTemplate hoặc WebClient theo API tích hợp load balancer của release train đó; không ép thêm Spring Framework 6.1 vào dự án Boot cũ chỉ để dùng RestClient.

### 9.2. Không kiểm tra round-robin bằng giả định thứ tự cứng

Một test không nên mặc định request đầu tiên luôn đến instance A, request thứ hai luôn đến B, trừ khi đã kiểm soát supplier, cache và trạng thái của load balancer.

Thay vào đó:

- Xác nhận host được chọn nằm trong danh sách instance hợp lệ.
- Xác nhận request path/header/body được giữ nguyên.
- Xác nhận không có instance thì nhận lỗi no-instance phù hợp.
- Nếu cần kiểm tra thuật toán round-robin, cấu hình supplier test có thứ tự xác định và cô lập context theo service ID.

Spring Cloud LoadBalancer tạo context riêng theo service ID và có thể cache danh sách instance. Vì thế, test phân phối instance cần kiểm soát cache hoặc tạo context mới giữa các kịch bản.

### 9.3. Kiểm tra registry thật khi cần

Nếu mục tiêu là chứng minh Eureka/Consul đăng ký đúng, cần integration test với registry tương ứng. Dùng Testcontainers hoặc fixture tương đương để khởi động registry, cấp địa chỉ động bằng DynamicPropertySource, khởi động service, rồi kiểm tra:

- Service ID và instance ID.
- Host, port, secure flag và metadata.
- Trạng thái đăng ký/heartbeat.
- Deregistration khi instance dừng.
- Consumer lấy instance từ registry và gọi được endpoint.

Mock DiscoveryClient chỉ kiểm tra logic phía ứng dụng. Nó không chứng minh registry thật nhận heartbeat, cập nhật trạng thái hoặc xóa instance đã dừng.

## 10. Kiểm thử HTTP client và lỗi gọi dịch vụ

Với client nội bộ, tách kiểm thử client khỏi kiểm thử discovery:

- Test request path, query parameter, header và body bằng mock HTTP server.
- Test mapping response thành DTO.
- Test xử lý 4xx/5xx.
- Test timeout và connection failure.
- Test LoadBalancer chọn host dựa trên service ID.
- Test retry/circuit breaker ở tầng cấu hình tương ứng nếu ứng dụng có sử dụng.

Không để một test duy nhất vừa kiểm tra JSON mapping, vừa khởi động Config Server, registry, database và toàn bộ ứng dụng. Khi test thất bại, rất khó xác định ranh giới nào gây lỗi.

Đối với request ghi dữ liệu như tạo đơn hàng hoặc thanh toán, hãy kiểm tra retry riêng. Chỉ retry khi API có idempotency key hoặc hợp đồng nghiệp vụ bảo đảm thao tác không bị thực hiện trùng.

## 11. Kiểm thử sự kiện và thay đổi cấu hình

Spring Cloud Context có các sự kiện như EnvironmentChangeEvent và cơ chế refresh scope. Nếu ứng dụng có listener cập nhật cache, feature flag hoặc log level khi cấu hình đổi, cần test cả listener và đường phát sự kiện.

Ví dụ listener:

```java
@Component
class FeatureFlagListener {

    private volatile boolean enabled;

    @EventListener
    void onEnvironmentChange(EnvironmentChangeEvent event) {
        if (event.getKeys().contains("feature.catalog.enabled")) {
            // Đọc lại property hoặc cập nhật state theo chính sách ứng dụng.
        }
    }
}
```

Trong unit test, có thể phát EnvironmentChangeEvent với tập key cụ thể để kiểm tra logic listener. Trong integration test, thay đổi property source và kích hoạt refresh theo đúng cơ chế ứng dụng đang dùng, sau đó xác nhận listener nhận sự kiện và trạng thái được cập nhật.

Không dùng test event giả để kết luận Config Client đã tải dữ liệu mới từ Config Server. Hai test chứng minh hai ranh giới khác nhau.

## 12. Quản lý fixture và trạng thái giữa các test

Các thành phần Spring Cloud có thể giữ cache hoặc state theo context/process:

- ApplicationContext được Spring TestContext cache giữa các test.
- LoadBalancer có child context theo service ID và có thể cache danh sách instance.
- RefreshScope giữ target bean cho đến khi cache entry bị invalidate.
- Mock HTTP server giữ request journal và stub.
- Testcontainers có thể được chia sẻ theo vòng đời class hoặc suite.
- Static mutable state có thể tồn tại giữa các test trong cùng JVM.

Để tránh test phụ thuộc thứ tự:

1. Khởi tạo fixture trước khi ApplicationContext cần đọc cấu hình.
2. Dùng port động và đăng ký bằng DynamicPropertySource.
3. Xóa request journal hoặc reset stub trước mỗi test khi cần.
4. Tạo cache key/service ID riêng cho kịch bản hoặc chủ động làm mới cache.
5. Không thay đổi static state dùng chung nếu test chạy song song.
6. Đóng server/container và context theo lifecycle của test framework.
7. Không dùng Thread.sleep() để đợi registry; chờ điều kiện có timeout hoặc poll trạng thái có kiểm soát.

Nếu một test chỉ pass khi chạy riêng nhưng fail khi chạy cả suite, hãy tìm state bị chia sẻ, context cache, static field hoặc port cố định trước khi tăng timeout.

## 13. Các lỗi thường gặp khi viết test Spring Cloud

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Property trong test không ghi đè giá trị cũ | Nguồn test có precedence thấp hơn hoặc context đã được cache | Kiểm tra property source và dùng đúng DynamicPropertySource/test property |
| ConfigurationProperties không được bind | Chưa đăng ký properties class | Dùng EnableConfigurationProperties hoặc configuration scan |
| Validation không chạy | Thiếu Bean Validation implementation | Thêm spring-boot-starter-validation và Validated |
| Context test không tạo bean | Condition hoặc dependency trên classpath không thỏa | Dùng ApplicationContextRunner để kiểm tra từng điều kiện |
| RefreshScope vẫn trả giá trị cũ | Bean không nằm trong refresh scope hoặc target chưa bị invalidate | Kiểm tra scope, bean name và RefreshScope.refresh |
| Xóa property rồi refresh nhưng bean vẫn có giá trị | Refresh không tự cập nhật sự hiện diện của property đã bị xóa | Kiểm tra logic absence/default; dùng giá trị trạng thái tường minh |
| Config Client gọi nhiều endpoint | Config Data tải default profile rồi profile được kích hoạt | Stub các request thực tế; không giả định chỉ có một lượt |
| Config Client khởi động dù Config Server tắt | Dùng optional: | Bỏ optional: khi remote config là bắt buộc |
| LoadBalancer báo không có instance | Sai service ID hoặc discovery không trả instance | Kiểm tra DiscoveryClient/SimpleDiscoveryClient và record |
| LoadBalancer gọi sai instance trong test | Cache/supplier hoặc context theo service ID còn state | Cô lập context, reset fixture và kiểm tra tập instance |
| Test registry lúc được lúc không | Chờ bằng sleep hoặc heartbeat chưa hoàn tất | Chờ điều kiện registry có timeout |
| Test pass riêng nhưng fail cả suite | Context cache hoặc static state dùng chung | Reset state, bỏ phụ thuộc thứ tự, kiểm soát chạy song song |
| Test integration phụ thuộc máy developer | Port cố định, profile hoặc env variable cục bộ | Dùng port động, profile test và dynamic properties |

## 14. Ma trận test đề xuất cho module Spring Cloud Core

Một module có Config Client, refresh scope, discovery và HTTP client có thể tổ chức suite như sau:

| Nhóm test | Ví dụ kịch bản | Tầng |
| --- | --- | --- |
| Configuration binding | Bind URI, timeout, retry, validation | Property test |
| Property precedence | Profile test ghi đè application default | Property/context test |
| Conditional beans | Bật/tắt feature hoặc discovery client | Context test |
| Refresh scope | Đổi property và tạo lại target bean | Context test |
| Config Client | Import remote property, fail-fast, optional source | Integration test |
| Config Server | Native repository, application/profile/label | Integration test |
| Service discovery | Lấy instance theo service ID | Context/integration test |
| LoadBalancer | Gọi nhiều instance, no-instance, host selection | Integration test |
| HTTP client | Mapping DTO, headers, status, timeout | Client test |
| Registry lifecycle | Register, heartbeat, deregister | Integration test |
| Config event | Listener nhận key thay đổi và cập nhật state | Unit/context test |
| Resilience | Retry, timeout và lỗi instance | Integration test |

Không phải mọi dự án đều cần mọi dòng. Chọn các nhóm phù hợp với dependency và hành vi thực sự có trong module.

## 15. Tổ chức chạy test trong CI

Một pipeline hợp lý có thể chia thành ba nhóm:

- **Fast tests:** unit test, Binder/property test và ApplicationContextRunner; chạy thường xuyên trong mỗi commit.
- **Application tests:** SpringBootTest, MVC/client slices và refresh scope test; chạy trong pull request.
- **Infrastructure integration tests:** Config Server, registry, database và Testcontainers; chạy khi thay đổi liên quan hoặc trong pipeline CI đầy đủ.

Giữ dependency version đồng bộ bằng Spring Cloud BOM và Spring Boot dependency management. Khi test thất bại sau nâng cấp, ghi lại Boot version, Cloud release train, JDK và dependency tree liên quan. Không giải quyết lỗi test bằng cách ép riêng một module Spring Cloud sang version khác mà chưa kiểm tra compatibility matrix.

Test cần có timeout hợp lý và cleanup rõ ràng. Một integration test không nên phụ thuộc Config Server public, registry dùng chung của nhóm hoặc dữ liệu production. Dùng fixture riêng cho từng run để tránh test này làm thay đổi kết quả của test khác.

## 16. Bài tập vận dụng

Một order-service sử dụng:

- ConfigurationProperties để đọc URL và timeout của catalog-service.
- Spring Cloud Config Client để nạp cấu hình theo profile.
- RefreshScope cho một bean giữ feature flag.
- Eureka để đăng ký và tìm instance.
- LoadBalanced RestClient.Builder để gọi catalog-service.

Hãy thiết kế và triển khai các test sau:

1. Property test kiểm tra URL, timeout hợp lệ và timeout ngoài giới hạn.
2. Profile test chứng minh application-test.yml được chọn.
3. Precedence test chứng minh DynamicPropertySource ghi đè property file.
4. Context test kiểm tra bean chỉ được tạo khi feature flag bật.
5. Refresh test thay đổi feature flag và xác nhận target RefreshScope được tạo lại.
6. Config Client integration test giả lập Config Server, kiểm tra application name và profile.
7. Fail-fast test xác nhận ứng dụng dừng khi Config Server bắt buộc không khả dụng.
8. Discovery test xác nhận catalog-service trả về danh sách instance mong đợi.
9. LoadBalancer integration test gọi qua service ID và xác nhận request đến một instance hợp lệ.
10. Registry integration test kiểm tra đăng ký, heartbeat và deregistration.
11. HTTP client test kiểm tra response DTO, lỗi 5xx và timeout.
12. Chạy toàn bộ suite nhiều lần và xác nhận kết quả không phụ thuộc thứ tự test.

**Tiêu chí hoàn thành:** mỗi test xác định rõ tầng và ranh giới cần chứng minh; không khởi động hạ tầng ngoài trong property/context test; integration test có fixture riêng, port động và cleanup; test lỗi cấu hình và không có instance được kiểm tra rõ ràng.

## 17. Ghi nhớ

- Unit test kiểm tra logic; property test kiểm tra binding/validation; context test kiểm tra bean/condition/scope; integration test kiểm tra giao tiếp giữa các thành phần.
- ApplicationContextRunner phù hợp cho properties và auto-configuration vì context nhỏ, đóng sau mỗi lần chạy.
- Dùng ActiveProfiles, TestPropertySource và DynamicPropertySource để kiểm soát cấu hình test.
- DynamicPropertySource phù hợp để cấp port/URL của Testcontainers hoặc mock server và có precedence cao hơn nhiều nguồn test khác.
- SpringBootTest kiểm tra context ứng dụng; test slice chỉ nạp một phần hệ thống.
- DirtiesContext loại context khỏi cache; chỉ dùng khi test thật sự làm bẩn trạng thái context.
- Test RefreshScope target recreation riêng với test tải cấu hình mới từ Config Server.
- Config Data import có thể yêu cầu Config Client gọi Config Server cho default rồi profile đang hoạt động.
- SimpleDiscoveryClient hữu ích cho LoadBalancer test không cần registry; registry lifecycle cần integration test riêng.
- Không giả định thứ tự round-robin cứng nếu chưa kiểm soát supplier/cache.
- Dùng port động, fixture riêng, cleanup và kiểm soát static state để test chạy ổn định trong CI.

## 18. Tài liệu tham khảo

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): SpringBootTest, test configuration và context caching.
- [Spring Boot — ApplicationContextRunner và Auto-configuration Testing](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): kiểm thử điều kiện tạo bean và auto-configuration trong context nhỏ.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): DynamicPropertySource, DynamicPropertyRegistry và precedence.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): TestPropertySource và property source trong test context.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): RefreshScope, RefreshScope.refreshAll() và refresh bean theo tên.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, profile loading, optional import và fail-fast.
- [Spring Cloud Config Server — File System Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/file-system-backend.html): native profile và searchLocations cho test server.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): discovery supplier, cache, health check và chọn instance.
- [Spring Cloud — Centralized Configuration Guide](https://spring.io/guides/gs/centralized-configuration): ví dụ Config Client và refresh endpoint theo luồng end-to-end.

