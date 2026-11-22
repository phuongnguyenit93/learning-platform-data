# Đăng ký địa chỉ động sau khi tài nguyên sẵn sàng

Trong kiểm thử tích hợp Spring, một tài nguyên phụ trợ thường không có địa chỉ cố định. Database chạy trong container có thể được ánh xạ sang một cổng ngẫu nhiên trên máy host; HTTP stub server có thể chọn cổng trống khi khởi động; một dịch vụ test có thể chỉ biết hostname và port sau khi runtime tạo xong tài nguyên.

Ứng dụng Spring vẫn cần địa chỉ đó để cấu hình `DataSource`, `RestClient`, `RestTemplate` hoặc một client khác. Nếu ghi cứng địa chỉ vào `application-test.properties`, test sẽ phụ thuộc vào cổng hoặc môi trường cụ thể và dễ xung đột khi chạy song song.

Spring Test cung cấp `@DynamicPropertySource` và `DynamicPropertyRegistry` để đăng ký các property có giá trị được lấy từ tài nguyên đang chạy. Kết hợp với supplier được đánh giá lười, cơ chế này giúp Spring nhận đúng địa chỉ động khi property được đọc, miễn là tài nguyên đã khởi động và sẵn sàng ở thời điểm đó.

## 1. Vì sao địa chỉ kiểm thử cần được đăng ký động?

Giả sử một test cần gọi dịch vụ HTTP phụ trợ. Nếu server luôn dùng port 8080, nhiều test hoặc nhiều tiến trình có thể tranh chấp cùng cổng. Nếu server chọn port ngẫu nhiên, địa chỉ chỉ có sau khi server khởi động.

Ví dụ:

~~~text
Trước khi khởi động:
  host = chưa xác định
  port = chưa xác định

Sau khi khởi động:
  host = 127.0.0.1
  port = 49173
  base URL = http://127.0.0.1:49173
~~~

Một client trong Spring có thể cần property:

~~~properties
partner.base-url=http://127.0.0.1:49173
~~~

Không nên tự chọn trước port rồi hy vọng nó còn trống khi server bind. Hãy để tài nguyên chọn endpoint thực tế, đợi tài nguyên sẵn sàng, sau đó cung cấp địa chỉ đó cho Spring.

Các trường hợp thường gặp:

- Testcontainers cấp host port động cho cổng bên trong container.
- WireMock hoặc MockWebServer chạy trên cổng ngẫu nhiên.
- Embedded server được khởi động với port 0.
- Một test fixture khởi động dịch vụ phụ trợ và công bố địa chỉ sau khi bind socket.
- Một tài nguyên cloud hoặc test environment cấp endpoint tại thời điểm tạo.

## 2. Vòng đời đúng: khởi động, chờ sẵn sàng rồi mới dùng địa chỉ

Đăng ký một property chỉ cung cấp giá trị cho Spring. Nó không tự khởi động database, container hoặc HTTP server. Test cần điều phối vòng đời tài nguyên rõ ràng:

~~~text
Tạo test resource
       |
       v
Khởi động resource
       |
       v
Chờ readiness / health check thành công
       |
       v
Đọc host và port thực tế
       |
       v
Đăng ký property động cho Spring
       |
       v
ApplicationContext tạo client / DataSource
       |
       v
Chạy test
       |
       v
Đóng ApplicationContext và resource
~~~

Điểm cần phân biệt:

- **Port được cấp** nghĩa là runtime đã chọn hoặc ánh xạ một port.
- **Resource sẵn sàng** nghĩa là dịch vụ đã khởi động và có thể xử lý loại request mà test cần.
- **Property được đăng ký** nghĩa là Spring có thể tra cứu một giá trị cấu hình.
- **Client được khởi tạo** nghĩa là ứng dụng đã đọc property và có thể giữ địa chỉ đó trong cấu hình của nó.

Một port đã được cấp chưa chắc dịch vụ đã ready. Ví dụ container có thể đã chạy nhưng database còn đang khởi tạo schema hoặc chưa chấp nhận kết nối. Hãy dùng readiness check của công cụ quản lý tài nguyên trước khi cho test sử dụng endpoint.

## 3. @DynamicPropertySource và DynamicPropertyRegistry

`@DynamicPropertySource` là annotation của Spring Test, có từ Spring Framework 5.2.5. Nó đánh dấu một phương thức static dùng để đăng ký property động vào `Environment` của `ApplicationContext` dành cho test.

Phương thức được đánh dấu phải nhận một tham số kiểu `DynamicPropertyRegistry`:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> "http://localhost:49173");
}
~~~

API chính:

~~~java
registry.add("property.name", supplier);
~~~

Trong đó:

- `property.name` là tên property mà ứng dụng sẽ đọc.
- `supplier` là `Supplier<?>` cung cấp giá trị khi property được tra cứu.

Có thể đăng ký nhiều property trong cùng một phương thức:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", partnerServer::baseUrl);
    registry.add("partner.api-key", () -> "test-api-key");
    registry.add("feature.remote-check", () -> true);
}
~~~

Supplier được đánh giá lười khi giá trị property được truy xuất. Vì vậy, có thể truyền method reference hoặc lambda để chỉ đọc host/port khi Spring thực sự cần property:

~~~java
registry.add("partner.base-url", partnerServer::baseUrl);
~~~

Không gọi method lấy địa chỉ ngay bên ngoài supplier nếu tài nguyên chưa sẵn sàng:

~~~java
// Không nên: method được gọi ngay trong lúc đăng ký property.
String baseUrl = partnerServer.baseUrl();
registry.add("partner.base-url", () -> baseUrl);
~~~

Nếu `baseUrl()` chỉ có giá trị sau khi server khởi động, cách trên có thể đọc quá sớm. Dùng method reference hoặc lambda gọi method sau khi resource đã được start:

~~~java
registry.add("partner.base-url", partnerServer::baseUrl);
~~~

Supplier không phải callback để khởi động tài nguyên. Nó chỉ cung cấp giá trị. Việc start và readiness vẫn phải được quản lý riêng.

### Property động có độ ưu tiên cao

Các property được đăng ký qua `@DynamicPropertySource` có độ ưu tiên cao hơn những nguồn property thông thường như `@TestPropertySource`, system properties, environment variables và các property source được thêm bằng `@PropertySource` hoặc cách thông thường trong context.

Điều này giúp giá trị endpoint của tài nguyên test ghi đè cấu hình mặc định trong file properties. Tuy nhiên, nên dùng tên property cụ thể và chỉ ghi đè đúng các giá trị cần cho test để tránh cấu hình khó hiểu.

## 4. Ví dụ với WireMock dùng cổng ngẫu nhiên

WireMock có thể khởi động trên một port động. Sau khi gọi `start()`, `baseUrl()` trả về địa chỉ thực tế của server.

Ví dụ sau minh họa việc khởi động tài nguyên trước khi Spring tạo ApplicationContext, rồi đăng ký địa chỉ đó bằng `@DynamicPropertySource`:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import com.github.tomakehurst.wiremock.WireMockServer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PartnerClientIntegrationTests {

    private static final WireMockServer partnerServer =
        new WireMockServer(options().dynamicPort());

    static {
        partnerServer.start();
    }

    @DynamicPropertySource
    static void partnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.base-url", partnerServer::baseUrl);
    }

    @Autowired
    PartnerClient partnerClient;

    @Test
    void callsPartnerAtItsAssignedAddress() {
        partnerServer.stubFor(get(urlEqualTo("/status"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "text/plain")
                .withBody("UP")));

        assertThat(partnerClient.status()).isEqualTo("UP");
    }

    @AfterAll
    static void stopPartnerServer() {
        partnerServer.stop();
    }
}
~~~

Trong ví dụ:

1. Static initializer khởi động WireMock server và để hệ điều hành cấp một port trống.
2. `@DynamicPropertySource` đăng ký supplier trả về `partnerServer.baseUrl()`.
3. Spring đọc `partner.base-url` khi tạo `PartnerClient`.
4. Test cấu hình response giả lập rồi gọi client.
5. Sau khi các test của lớp hoàn tất, server được dừng.

Khởi động trong static initializer là một cách đơn giản để bảo đảm tài nguyên đã được start trước khi Spring cần tạo context. Trong dự án có lifecycle extension riêng, có thể dùng extension đó để quản lý start/stop, miễn là thứ tự bảo đảm resource sẵn sàng trước lần property được đọc.

Một client minh họa:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class PartnerClient {

    private final RestClient restClient;

    PartnerClient(@Value("${partner.base-url}") String baseUrl) {
        this.restClient = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    String status() {
        return restClient.get()
            .uri("/status")
            .retrieve()
            .body(String.class);
    }
}
~~~

Ví dụ dùng `RestClient`, có từ Spring Framework 6.1. Với ứng dụng dùng `RestTemplate`, WebClient hoặc một client khác, nguyên tắc đăng ký property vẫn tương tự.

## 5. Ví dụ với Testcontainers và port được ánh xạ động

Container thường khai báo port bên trong image, nhưng Testcontainers có thể ánh xạ port đó sang một port ngẫu nhiên trên host. Không nên giả định host port bằng container port.

Ví dụ PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void applicationCanUseDatabase() {
        // Thực hiện kiểm thử repository hoặc service.
    }
}
~~~

Testcontainers quản lý vòng đời static container qua JUnit Jupiter extension. Container được khởi động trước khi test sử dụng, và các supplier lấy JDBC URL, username, password từ chính container đó.

`getJdbcUrl()` chứa thông tin host và port được ánh xạ thực tế. Không tự ghép `localhost:5432`, vì port 5432 trong container có thể được ánh xạ sang một port khác trên máy chạy test.

Với container cung cấp HTTP service, nguyên tắc lấy endpoint tương tự:

~~~java
registry.add("partner.base-url", () ->
    "http://" + service.getHost() + ":" + service.getMappedPort(8080)
);
~~~

Trong ví dụ này, `8080` là port bên trong container đã được expose. `getMappedPort(8080)` trả về port phía host sau khi container khởi động. Supplier chỉ nên được gọi sau khi container đã start.

### Chờ container sẵn sàng

Testcontainers có startup check và wait strategy. Với dịch vụ HTTP, có thể cấu hình chờ HTTP health endpoint:

~~~java
static final GenericContainer<?> partner =
    new GenericContainer<>(DockerImageName.parse("example/partner:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
            Wait.forHttp("/health")
                .forPort(8080)
                .forStatusCode(200)
        );
~~~

Khi dùng wait strategy, `start()` chỉ hoàn tất sau khi điều kiện chờ thành công hoặc startup timeout xảy ra. Điều này giúp tránh trường hợp Spring tạo client với endpoint đã có port nhưng service chưa nhận request được.

Các kiểu wait thường gặp:

| Wait strategy | Dùng khi |
|---|---|
| `Wait.forListeningPort()` | Chỉ cần xác nhận port bắt đầu lắng nghe. |
| `Wait.forHttp(path)` | Cần endpoint HTTP health trả status mong đợi. |
| `Wait.forLogMessage(regex, count)` | Tài nguyên phát log báo sẵn sàng. |
| `Wait.forHealthcheck()` | Image có health check mà container runtime báo trạng thái healthy. |

Chọn điều kiện readiness phản ánh khả năng mà test thực sự cần. Một port lắng nghe có thể chưa đồng nghĩa database đã nhận truy vấn hoặc HTTP API đã sẵn sàng xử lý request nghiệp vụ.

## 6. Không đọc host/port quá sớm

Nhiều API chỉ trả endpoint sau khi tài nguyên được start:

| API | Khi nào có thể đọc |
|---|---|
| `WireMockServer.baseUrl()` | Sau khi WireMock start. |
| `GenericContainer.getHost()` | Sau khi container start. |
| `GenericContainer.getMappedPort(port)` | Sau khi container start và port được ánh xạ. |
| `PostgreSQLContainer.getJdbcUrl()` | Sau khi container start. |
| `WebServer.getPort()` với port 0 | Sau khi embedded server bind port thực tế. |

Đây là lý do supplier quan trọng:

~~~java
registry.add("partner.base-url", () ->
    "http://" + container.getHost() + ":" + container.getMappedPort(8080)
);
~~~

Không tính địa chỉ ở thời điểm khai báo field nếu resource chưa start:

~~~java
// Có thể thất bại nếu container chưa được start.
static final String PARTNER_URL =
    "http://" + container.getHost() + ":" + container.getMappedPort(8080);
~~~

Giữ việc đọc endpoint bên trong supplier, hoặc chỉ tạo giá trị sau một bước start/readiness rõ ràng.

Supplier có thể được Spring gọi khi property được truy xuất; không nên dựa vào giả định nó chỉ được gọi đúng một lần. Supplier nên trả về cùng một địa chỉ hợp lệ trong suốt vòng đời của ApplicationContext và không thực hiện side effect như start/stop container.

## 7. Property được đọc khi nào?

`@DynamicPropertySource` được Spring Test sử dụng khi chuẩn bị `ApplicationContext`. Property source động được thêm vào `Environment`, sau đó các bean có thể đọc property trong lúc binding cấu hình hoặc khởi tạo.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "partner")
public record PartnerProperties(URI baseUrl) {}
~~~

Spring bind property:

~~~properties
partner.base-url=http://...
~~~

Hoặc bean đọc trực tiếp:

~~~java
PartnerClient(@Value("${partner.base-url}") String baseUrl) {
    // Tạo client từ baseUrl.
}
~~~

Khi bean đã được tạo và client đã lưu base URL, thay đổi giá trị trả về của supplier sau đó không tự động cấu hình lại client hiện có. Vì vậy, endpoint cần ổn định trong suốt vòng đời context. Nếu tài nguyên được restart và nhận port mới, thường phải tạo lại context/client tương ứng hoặc dùng một cơ chế cập nhật cấu hình có chủ đích.

### Độ ưu tiên không thay thế lifecycle

Property động có thể ghi đè property tĩnh, nhưng độ ưu tiên không làm resource tự sẵn sàng. Nếu supplier được gọi khi container chưa start, `getMappedPort()` vẫn có thể ném exception. Cần giải quyết thứ tự start/readiness độc lập với thứ tự ưu tiên property.

## 8. Quản lý resource bằng JUnit và Spring Test

Tài nguyên phụ trợ và ApplicationContext có vòng đời riêng. Cần bảo đảm:

- Resource khởi động trước khi Spring đọc endpoint.
- Resource không bị dừng trong khi test hoặc bean vẫn cần gọi nó.
- Test không chia sẻ nhầm một tài nguyên mutable giữa nhiều lớp chạy song song.
- Resource được dừng ngay cả khi test thất bại.

### Static resource dùng chung trong một test class

Với WireMock hoặc một server Java chạy trong cùng JVM, có thể dùng static field và `@AfterAll` như ví dụ trước. Nếu khởi động resource trong static initializer, cần bảo đảm lệnh start hoàn tất trước khi Spring extension chuẩn bị context.

### Dùng JUnit extension

Nếu thư viện quản lý tài nguyên cung cấp JUnit extension, ưu tiên dùng extension chính thức để có lifecycle nhất quán. Ví dụ Testcontainers:

~~~java
@Testcontainers
class DatabaseTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Static container được dùng chung cho các test method trong lớp. Instance container có thể được khởi động và dừng theo từng test method. Chọn phạm vi theo chi phí khởi động và mức độ cô lập cần thiết.

### Không dừng resource quá sớm

Nếu `ApplicationContext` được cache và tái sử dụng giữa nhiều test class, một static resource chỉ thuộc về một class có thể bị dừng trong khi context vẫn còn bean trỏ tới địa chỉ cũ. Điều này tạo ra lỗi khó hiểu ở test chạy sau.

Các cách xử lý:

- Đặt resource ở phạm vi sống đủ lâu so với mọi context sử dụng nó.
- Dùng cùng một base test class để quản lý resource và cấu hình context.
- Tách context nếu các lớp cần resource có lifecycle hoặc endpoint khác nhau.
- Đóng context trước khi dừng resource nếu test fixture tự quản lý cả hai vòng đời.

## 9. Kế thừa @DynamicPropertySource và context cache

Phương thức `@DynamicPropertySource` có thể được khai báo trong superclass và được kế thừa bởi các lớp test con. Cách này hữu ích khi nhiều integration test dùng chung một database hoặc một dịch vụ test.

Ví dụ:

~~~java
abstract class AbstractDatabaseIntegrationTest {

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
class OrderRepositoryTests extends AbstractDatabaseIntegrationTest {
    // Test repository.
}

@SpringBootTest
class CustomerRepositoryTests extends AbstractDatabaseIntegrationTest {
    // Test repository.
}
~~~

Khi các lớp con dùng cùng resource và cùng cấu hình, kế thừa giúp tránh lặp lại phần đăng ký property.

Tuy nhiên, Spring Test cache `ApplicationContext` để tái sử dụng giữa các test có cấu hình tương đương. Nếu các lớp con kế thừa cùng một phương thức nhưng resource hoặc giá trị property động thực tế thay đổi giữa các lớp, context được cache có thể vẫn giữ cấu hình cũ. Trong trường hợp đó, cân nhắc `@DirtiesContext` ở superclass hoặc tách cấu hình/context để mỗi resource có context phù hợp.

Không cần dùng `@DirtiesContext` một cách máy móc. Nếu resource tĩnh và endpoint giữ nguyên suốt vòng đời context, cache context thường là lợi ích về thời gian chạy test.

## 10. Đăng ký nhiều địa chỉ động

Một test có thể phụ thuộc nhiều tài nguyên:

- Database.
- Message broker.
- HTTP stub server.
- Cache.

Đăng ký tất cả property trong cùng một phương thức:

~~~java
@DynamicPropertySource
static void registerInfrastructure(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);

    registry.add("partner.base-url", partnerServer::baseUrl);

    registry.add("cache.host", redis::getHost);
    registry.add("cache.port", () -> redis.getMappedPort(6379));
}
~~~

Mỗi supplier phải lấy giá trị từ đúng resource. Tránh tái sử dụng một host hoặc port cho nhiều dịch vụ chỉ vì chúng tình cờ cùng chạy trên máy local.

Nếu một resource phụ thuộc resource khác, phải khởi động theo thứ tự dependency. Ví dụ, ứng dụng cần database trước khi khởi tạo schema; nếu HTTP stub không phụ thuộc database thì có thể start song song, nhưng tất cả phải ready trước khi bean tương ứng bắt đầu sử dụng.

## 11. Đăng ký property động bằng ApplicationContextInitializer

Trước khi có `@DynamicPropertySource`, một cách thường dùng là `ApplicationContextInitializer`. Cách này vẫn hữu ích trong một số cấu hình đặc biệt hoặc codebase cũ:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.support.TestPropertyValues;

class PartnerContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String baseUrl = PartnerTestResource.baseUrl();
        TestPropertyValues.of(
            "partner.base-url=" + baseUrl
        ).applyTo(context.getEnvironment());
    }
}
~~~

Đăng ký initializer trên test:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = PartnerContextInitializer.class)
class PartnerIntegrationTests {
}
~~~

Initializer chạy trong quá trình chuẩn bị context. Resource phải được start và ready trước khi initializer đọc địa chỉ. Khác với `DynamicPropertyRegistry`, ví dụ trên tạo chuỗi property ngay trong initializer.

Với Spring Framework 5.2.5 trở lên, `@DynamicPropertySource` thường ngắn gọn và thể hiện rõ ý định đăng ký giá trị động bằng supplier. Không cần chuyển sang initializer nếu annotation đáp ứng được lifecycle của test.

## 12. Spring Boot @ServiceConnection và khi nào dùng

Với Spring Boot 3.1 trở lên, `@ServiceConnection` có thể tự tạo connection details cho một số loại Testcontainers phổ biến như PostgreSQL, Redis, Kafka và nhiều dịch vụ được hỗ trợ.

Ví dụ:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Spring Boot nhận diện loại container và tạo connection details cho auto-configuration phù hợp. Với trường hợp chuẩn được hỗ trợ, không cần tự đăng ký `spring.datasource.url`, username và password.

Chọn `@ServiceConnection` khi:

- Dùng Spring Boot.
- Loại container được Spring Boot hỗ trợ.
- Muốn để Boot tự cấu hình kết nối theo loại service.

Chọn `@DynamicPropertySource` khi:

- Dùng Spring Framework Test trực tiếp hoặc không muốn phụ thuộc cơ chế riêng của Boot.
- Tài nguyên là WireMock, MockWebServer hoặc một dịch vụ tùy chỉnh.
- Ứng dụng cần một property riêng như `partner.base-url`.
- Cần đăng ký giá trị không có connection details auto-configuration tương ứng.

Hai cơ chế có thể cùng xuất hiện trong một test suite, nhưng nên tránh đăng ký hai nguồn cạnh tranh cho cùng một cấu hình kết nối nếu không có lý do rõ ràng.

## 13. Trường hợp ứng dụng tự chạy trên port ngẫu nhiên

Nếu chính ứng dụng Spring Boot là tài nguyên cần được kiểm thử, có thể khởi động embedded server trên port ngẫu nhiên:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationHttpIntegrationTests {

    @LocalServerPort
    int port;

    @Test
    void respondsOnAssignedPort() {
        // Dùng port được inject để gọi server đang chạy.
    }
}
~~~

Trong trường hợp này, `@LocalServerPort` là cách phù hợp để lấy port của embedded server sau khi server đã khởi động. Không nên cố đọc port đó trong `@DynamicPropertySource` của cùng context, vì dynamic property source tham gia vào quá trình chuẩn bị context trước khi embedded server của context hoàn tất khởi động.

Nếu một service bean khác trong ứng dụng cần biết địa chỉ của chính embedded server, hãy xem xét thiết kế lifecycle và cấu hình riêng. Đừng tạo vòng phụ thuộc khi context cần property để khởi động server nhưng property lại chỉ có sau khi server khởi động.

## 14. Những lỗi thường gặp

### Đọc getMappedPort trước khi container start

Testcontainers chỉ biết port mapping sau khi container được khởi động. Đưa lời gọi vào supplier hoặc đọc sau bước start.

### Nghĩ rằng đăng ký property sẽ tự khởi động resource

`registry.add` chỉ đăng ký supplier. Test vẫn phải start container/server và chờ readiness.

### Chỉ kiểm tra port đã mở

Port lắng nghe không bảo đảm dịch vụ đã sẵn sàng về nghiệp vụ. Dùng health check hoặc wait strategy phù hợp.

### Dùng port cố định

Port cố định có thể xung đột giữa các tiến trình hoặc máy chạy CI. Ưu tiên dynamic port và đọc địa chỉ do resource cung cấp.

### Eagerly evaluate supplier

Gọi `getMappedPort()` hoặc `baseUrl()` trước khi start có thể gây lỗi. Dùng lambda hoặc method reference để lấy giá trị ở thời điểm property được truy xuất.

### Dừng resource trước khi context hoàn tất

Bean có thể giữ endpoint cũ và tiếp tục gọi resource đã bị dừng. Đồng bộ lifecycle resource với context sử dụng nó.

### Tái sử dụng context nhưng thay endpoint

Context cache có thể tái sử dụng bean đã cấu hình bằng endpoint cũ. Nếu endpoint thay đổi giữa các lớp test, cân nhắc tách context hoặc `@DirtiesContext`.

### Nhầm container port với host port

`getMappedPort(8080)` trả port phía host được ánh xạ từ port 8080 trong container. Client chạy ngoài container thường cần host và mapped port, không phải cặp `localhost:8080`.

### Đăng ký sai tên property

Property phải khớp chính xác với tên mà `@Value`, `@ConfigurationProperties` hoặc auto-configuration đang đọc. Kiểm tra prefix và cấu trúc tên property.

### Dùng @DynamicPropertySource cho port của chính embedded server

Property source được xử lý khi context đang được chuẩn bị, trước khi embedded server có port cuối cùng. Dùng `@LocalServerPort` sau khi server khởi động hoặc một lifecycle hook phù hợp.

## 15. Checklist triển khai trong test

Khi test cần địa chỉ của tài nguyên động, hãy lần lượt:

1. Xác định ai quản lý tài nguyên: JUnit extension, Testcontainers, WireMock hay fixture tự viết.
2. Chọn port động hoặc để runtime cấp mapping; tránh hard-code port.
3. Khởi động resource trước khi Spring cần cấu hình client.
4. Chờ readiness bằng health check, wait strategy hoặc tín hiệu start hoàn tất.
5. Đăng ký property qua `@DynamicPropertySource` và `DynamicPropertyRegistry`.
6. Đưa lời gọi lấy host/port vào supplier nếu địa chỉ chỉ có sau khi start.
7. Để Spring tạo `ApplicationContext` và bind property vào bean.
8. Giữ resource sống trong toàn bộ thời gian context và test cần sử dụng nó.
9. Đóng context/resource theo lifecycle rõ ràng.
10. Nếu endpoint thay đổi giữa các lớp nhưng context được cache, xem xét tách context hoặc `@DirtiesContext`.

Đăng ký địa chỉ động hiệu quả khi property được đọc đúng thời điểm và resource có lifecycle rõ ràng. `@DynamicPropertySource` cung cấp cầu nối từ endpoint do runtime cấp sang `Environment` của Spring; supplier giúp trì hoãn việc lấy giá trị, còn bước start và readiness bảo đảm địa chỉ đó thực sự có thể sử dụng khi ứng dụng khởi tạo.
