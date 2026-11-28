# Kiểm thử Config Client với máy chủ thật hoặc HTTP giả lập

Config Client thường tải cấu hình trong giai đoạn khởi động Spring Boot. Vì vậy, một bài kiểm thử chỉ gọi method của service sau khi context đã chạy chưa đủ để chứng minh ứng dụng có thể kết nối Config Server, yêu cầu đúng application/profile/label và bind được các property từ xa. Cần kiểm thử cả giao thức HTTP mà Config Client sử dụng lẫn kết quả cuối cùng trong Spring Environment và bean cấu hình.

Có hai cách kiểm thử bổ sung cho nhau:

- **HTTP giả lập:** dùng WireMock hoặc MockWebServer trả response theo giao thức Config Server. Cách này nhanh, xác định và phù hợp kiểm tra request path, response, lỗi mạng và các trường hợp biên.
- **Config Server thật:** chạy một Config Server test cùng repository fixture. Cách này xác minh tích hợp end-to-end với backend và hành vi thực tế của EnvironmentRepository.

Nên kiểm thử theo nhiều lớp: property binding, Config Data import, HTTP contract, server/repository integration và smoke test sau triển khai. Dù dùng server thật hay giả lập, tiêu chí cuối cùng là ứng dụng nhận đúng cấu hình cho context đã yêu cầu và xử lý lỗi theo chính sách đã định.

## 1. Kiến trúc kiểm thử

Khi ứng dụng khởi động với Config Data API, Config Client đọc location `configserver:...`, gửi HTTP request đến Config Server và chuyển các property source trong response thành Spring Environment.

~~~mermaid
flowchart TD
    T[Test] --> A[Start Config Client]
    A --> B[spring.config.import]
    B --> C{Config Server target}
    C -->|Mock HTTP| W[WireMock / MockWebServer]
    C -->|Real integration| S[Config Server test instance]
    S --> R[Test repository]
    W --> J[Environment JSON]
    R --> J
    J --> E[Spring Environment]
    E --> P[ConfigurationProperties binding]
    P --> V[Assertions]
~~~

Các lớp cần xác minh:

| Lớp | Nội dung cần kiểm tra |
|---|---|
| Config Data | Import location được xử lý đúng khi bootstrap |
| HTTP request | URL, application, profile, label, headers và authentication |
| Environment response | JSON có metadata và propertySources đúng cấu trúc |
| Property source | Key từ xa xuất hiện và có thứ tự ưu tiên mong muốn |
| Binding | ConfigurationProperties/Value nhận đúng kiểu và giá trị |
| Error handling | 404, 401/403, 5xx, timeout và response không hợp lệ |
| Refresh | Client đọc lại cấu hình và bean hỗ trợ refresh nhận giá trị mới |

## 2. Chuẩn bị dependency kiểm thử

Một Config Client dùng Maven thường có các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.wiremock</groupId>
        <artifactId>wiremock</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Quản lý phiên bản Spring Boot và Spring Cloud bằng BOM tương thích. Chọn phiên bản WireMock phù hợp với Java version của project và quy định của build. Nếu dùng OkHttp MockWebServer thay cho WireMock, thêm dependency test tương ứng; không cần cài cả hai thư viện nếu không có nhu cầu.

Đối với kiểm thử Config Server thật, test module còn cần Config Server starter và backend fixture phù hợp. Ví dụ có thể chạy server trên cổng ngẫu nhiên với native test repository hoặc một Git repository tạm được tạo trong thư mục test.

## 3. Tạo property class để kiểm tra kết quả

Không chỉ xác nhận Config Client nhận HTTP 200. Hãy bind property vào bean giống cách ứng dụng thật sử dụng:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public class OrderProperties {

    private Duration timeout;
    private int maxItems;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
~~~

Đăng ký properties trong ứng dụng:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(OrderProperties.class)
public class OrdersClientApplication {
}
~~~

Trong test, assert trực tiếp bean đã bind:

~~~java
assertThat(properties.getTimeout()).isEqualTo(Duration.ofSeconds(3));
assertThat(properties.getMaxItems()).isEqualTo(100);
~~~

Kiểm tra binding giúp phát hiện sai kiểu dữ liệu, sai tên key và thiếu property bắt buộc. Nếu ứng dụng dùng validation, test cả giá trị hợp lệ lẫn giá trị ngoài miền.

## 4. Mô phỏng Config Server bằng WireMock

Config Server trả Environment dưới dạng JSON. Response thường có metadata và danh sách propertySources; mỗi property source chứa tên nguồn và map key/value.

Ví dụ response rút gọn:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "version": "test-commit-001",
  "state": null,
  "propertySources": [
    {
      "name": "mock:orders-service-prod",
      "source": {
        "orders.timeout": "3s",
        "orders.max-items": 100
      }
    }
  ]
}
~~~

Config Client yêu cầu endpoint theo dạng:

~~~text
/{application}/{profile}/{label}
~~~

Ví dụ với application orders-service, profile prod và label release-2026.11:

~~~text
/orders-service/prod/release-2026.11
~~~

Đường dẫn và các chi tiết request cần được xác nhận với release train đang dùng, đặc biệt nếu có context path, prefix, discovery-first lookup hoặc cấu hình nhiều label.

### 4.1. Ví dụ kiểm thử bằng WireMock

Ví dụ dưới đây khởi động client bằng SpringApplicationBuilder sau khi WireMock đã sẵn sàng. Cách này giúp đặt spring.config.import trước khi Config Data được nạp:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

class ConfigClientWireMockTest {

    private static WireMockServer configServer;

    @BeforeAll
    static void startConfigServer() {
        configServer = new WireMockServer(wireMockConfig().dynamicPort());
        configServer.start();

        configServer.stubFor(get(urlPathEqualTo(
                "/orders-service/prod/release-2026.11"))
            .willReturn(aResponse()
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "name": "orders-service",
                      "profiles": ["prod"],
                      "label": "release-2026.11",
                      "version": "test-commit-001",
                      "state": null,
                      "propertySources": [{
                        "name": "mock:orders-service-prod",
                        "source": {
                          "orders.timeout": "3s",
                          "orders.max-items": 100
                        }
                      }]
                    }
                    """)));
    }

    @AfterAll
    static void stopConfigServer() {
        if (configServer != null) {
            configServer.stop();
        }
    }

    @Test
    void loadsRemotePropertiesIntoSpringEnvironment() {
        String importLocation =
                "configserver:http://localhost:" + configServer.port();

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(OrdersClientApplication.class)
                    .web(WebApplicationType.NONE)
                    .properties(
                        "spring.config.import=" + importLocation,
                        "spring.application.name=orders-service",
                        "spring.profiles.active=prod",
                        "spring.cloud.config.label=release-2026.11")
                    .run()) {

            OrderProperties properties =
                    context.getBean(OrderProperties.class);

            assertThat(properties.getTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(properties.getMaxItems()).isEqualTo(100);
        }

        configServer.verify(getRequestedFor(urlPathEqualTo(
                "/orders-service/prod/release-2026.11")));
    }
}
~~~

Ví dụ minh họa cách dựng test context theo chương trình; hãy bổ sung các import, cấu hình logging và dependency phù hợp với project. Một số phiên bản Config Client có thể thêm query parameter hoặc gọi endpoint phụ trợ; khi đó xác minh request bằng path matcher và kiểm tra request thực tế từ WireMock.

Điểm quan trọng là WireMock phải chạy trước khi SpringApplication khởi động, vì Config Data import được xử lý trong quá trình chuẩn bị Environment. Nếu dùng một port cố định, bảo đảm port không xung đột và server được khởi động trước khi test context được tạo.

## 5. Dùng MockWebServer thay WireMock

MockWebServer phù hợp nếu project đã sử dụng OkHttp hoặc muốn API đơn giản để enqueue response:

~~~java
MockWebServer server = new MockWebServer();
server.start();

server.enqueue(new MockResponse()
        .addHeader("Content-Type", "application/json")
        .setBody(environmentJson));

String importLocation =
        "configserver:" + server.url("/");

try (ConfigurableApplicationContext context =
        new SpringApplicationBuilder(OrdersClientApplication.class)
            .web(WebApplicationType.NONE)
            .properties(
                "spring.config.import=" + importLocation,
                "spring.application.name=orders-service",
                "spring.profiles.active=prod",
                "spring.cloud.config.label=release-2026.11")
            .run()) {

    OrderProperties properties = context.getBean(OrderProperties.class);
    assertThat(properties.getMaxItems()).isEqualTo(100);

    RecordedRequest request = server.takeRequest();
    assertThat(request.getPath())
            .contains("/orders-service/prod/release-2026.11");
} finally {
    server.shutdown();
}
~~~

Đây là đoạn mã minh họa; cần khai báo `environmentJson`, import các lớp MockWebServer và bảo đảm server được khởi động trước client. Với request retry hoặc nhiều request, enqueue đủ response theo thứ tự và đọc từng RecordedRequest để tránh test phụ thuộc vào thứ tự không xác định.

Không nên dùng mock HTTP để kiểm tra thuật toán nội bộ của Config Server. Mock chỉ xác nhận client xử lý đúng contract HTTP; việc Config Server đọc Git/JDBC/Vault phải được kiểm tra bằng integration test riêng.

## 6. Kiểm tra application, profile và label

Một lỗi phổ biến là client khởi động được nhưng yêu cầu sai context. Tạo test cases riêng cho:

| Thuộc tính | Giá trị test | Điều cần xác minh |
|---|---|---|
| spring.application.name | orders-service | Request dùng đúng application |
| spring.profiles.active | prod | Request gửi profile đúng |
| spring.cloud.config.label | release-2026.11 | Request chọn đúng label |
| spring.config.import | configserver URL | Client kết nối đúng base URL |
| search path hoặc application config name | Theo deployment | Server trả đúng property sources |

Với nhiều profile, xác minh chuỗi profile mà client gửi và response server trả về. Với label có dấu slash, branch hoặc ký tự đặc biệt, kiểm tra URL encoding và cách reverse proxy chuyển tiếp path.

Có thể tạo WireMock stub cho mỗi context:

~~~java
configServer.stubFor(get(urlPathEqualTo(
        "/orders-service/staging/release-2026.11"))
    .willReturn(okJson(stagingEnvironmentJson)));

configServer.stubFor(get(urlPathEqualTo(
        "/orders-service/prod/release-2026.11"))
    .willReturn(okJson(productionEnvironmentJson)));
~~~

Sau đó khởi động hai client context với profile khác nhau và assert giá trị bind. Đảm bảo mỗi test có cấu hình độc lập, không để system property hoặc Spring context cache làm rò rỉ profile từ test trước.

## 7. Kiểm tra property source và thứ tự ưu tiên

Config Client có thể nhận property từ nhiều nguồn: local application.yml, Config Server, profile-specific files, environment variables và command-line arguments. Một test tốt cần xác định nguồn nào được kỳ vọng thắng.

Ví dụ giả lập Config Server trả:

~~~json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "version": "test-commit-002",
  "propertySources": [{
    "name": "mock:remote",
    "source": {
      "orders.max-items": 100,
      "orders.timeout": "3s"
    }
  }]
}
~~~

Trong test, có thể đặt local default:

~~~yaml
orders:
  max-items: 50
~~~

Sau đó khởi động với Config Data import và kiểm tra giá trị thực tế:

~~~java
assertThat(context.getEnvironment()
        .getProperty("orders.max-items", Integer.class))
        .isEqualTo(100);
~~~

Giá trị mong đợi phụ thuộc thứ tự property source của Config Data imports và nguồn local trong phiên bản Spring Boot/Spring Cloud đang dùng. Hãy xác nhận bằng test thay vì giả định remote luôn thắng local trong mọi cách khai báo import.

Nếu cần chẩn đoán, kiểm tra tên property source và origin mà không in secret:

~~~java
import org.springframework.core.env.PropertySource;

assertThat(context.getEnvironment().getPropertySources())
        .anySatisfy(source ->
                assertThat(source.getName()).contains("configserver"));
~~~

Ví dụ dùng AssertJ để duyệt các PropertySource. Không dump toàn bộ property source vào test report vì response có thể chứa credential đã được giải mã.

## 8. Kiểm tra cấu hình bắt buộc và validation

Test client nên xác nhận ứng dụng từ chối khởi động khi thiếu property bắt buộc hoặc giá trị ngoài miền:

~~~java
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "orders")
@Validated
public class OrderProperties {

    @NotNull
    private Duration timeout;

    @Min(1)
    private int maxItems;

    // getters và setters
}
~~~

Ví dụ dùng Jakarta Bean Validation cho Spring Boot 3; với ứng dụng Spring Boot 2, dùng package javax.validation tương ứng.

Các trường hợp nên kiểm thử:

- Key bắt buộc không có trong response.
- Giá trị Duration sai định dạng.
- Số lượng bằng 0 hoặc âm.
- Giá trị vượt giới hạn nghiệp vụ.
- Hai key cũ/mới cùng tồn tại nhưng không đồng nhất.
- Property từ local file vô tình che giá trị remote.

Validation nên chạy ở startup để lỗi cấu hình được phát hiện trước khi nhận traffic. Test cần xác nhận loại exception hoặc failure condition phù hợp, nhưng tránh phụ thuộc vào toàn bộ nội dung stack trace.

## 9. Kiểm tra Config Server thật

HTTP giả lập không kiểm tra Git clone, JDBC query, search paths hay cách Config Server hợp nhất property source. Để kiểm tra end-to-end, chạy một Config Server thật trong test với repository fixture có thể tái lập.

Một mô hình kiểm thử:

1. Tạo repository cấu hình tạm với application.yml, orders-service.yml và orders-service-prod.yml.
2. Ghi các property không nhạy cảm có giá trị dễ phân biệt vào từng file.
3. Khởi động Config Server trên cổng ngẫu nhiên với Git URI trỏ tới repository fixture.
4. Chờ server sẵn sàng và xác nhận endpoint health.
5. Khởi động Config Client với spring.config.import trỏ tới server thật.
6. Assert Environment, property source, binding và giá trị ưu tiên.
7. Thay đổi repository fixture, fetch/refresh theo cơ chế backend và xác minh label/commit mới.
8. Đóng client/server và xóa tài nguyên tạm trong finally/cleanup.

Với Git backend, có thể tạo local Git repository trong thư mục test bằng JGit hoặc script fixture được quản lý bởi test harness. Không phụ thuộc repository internet công khai trong test thường xuyên; network ngoài làm test chậm và không ổn định.

Ví dụ khởi chạy server và client theo chương trình:

~~~java
try (ConfigurableApplicationContext server =
        new SpringApplicationBuilder(ConfigServerTestApplication.class)
            .web(WebApplicationType.SERVLET)
            .properties(
                "server.port=0",
                "spring.cloud.config.server.git.uri=" + repositoryUri,
                "spring.cloud.config.server.git.clone-on-start=true")
            .run()) {

    int port = server.getEnvironment()
            .getProperty("local.server.port", Integer.class);

    try (ConfigurableApplicationContext client =
            new SpringApplicationBuilder(OrdersClientApplication.class)
                .web(WebApplicationType.NONE)
                .properties(
                    "spring.config.import=configserver:http://localhost:" + port,
                    "spring.application.name=orders-service",
                    "spring.profiles.active=prod",
                    "spring.cloud.config.label=test-ref")
                .run()) {

        OrderProperties properties =
                client.getBean(OrderProperties.class);
        assertThat(properties.getMaxItems()).isEqualTo(100);
    }
}
~~~

Đây là skeleton cần ghép với Config Server test application có @EnableConfigServer, Git fixture đã được tạo/commit và dependency tương ứng. Cổng ngẫu nhiên giúp tránh xung đột giữa các test chạy song song. Đảm bảo lấy đúng port do web server công bố sau khi startup; nếu phiên bản hoặc web server không đưa port vào Environment theo key trên, lấy từ WebServerApplicationContext.

## 10. Kiểm tra mandatory và optional Config Data import

Với import bắt buộc:

~~~yaml
spring:
  config:
    import: "configserver:http://localhost:8888"
~~~

Nếu Config Server không truy cập được hoặc không thể nạp cấu hình bắt buộc, ứng dụng thường thất bại khi startup. Test nên xác nhận lỗi startup trong trường hợp server tắt hoặc trả lỗi.

Với import tùy chọn:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Ứng dụng có thể tiếp tục khởi động khi Config Server không khả dụng, miễn là các property bắt buộc vẫn có giá trị an toàn từ nguồn khác. Test optional cần xác nhận:

- Context khởi động được khi server vắng mặt.
- Property fallback có giá trị đúng.
- Không có secret hoặc endpoint production bị thay bằng default yếu.
- Log/metrics ghi nhận Config Server không truy cập được.

Không dùng optional để che giấu việc mất database password, signing key hoặc cấu hình bảo mật bắt buộc. Test phải phản ánh chính sách startup thật của ứng dụng.

## 11. Kiểm tra lỗi HTTP và lỗi kết nối

Tạo stub cho các lỗi phổ biến:

| Tình huống | Mock response | Kỳ vọng cần kiểm tra |
|---|---|---|
| Application/profile không tồn tại | 404 hoặc Environment rỗng theo contract server | Client xử lý theo chính sách cấu hình |
| Authentication thiếu/sai | 401 | Startup/refresh thất bại có kiểm soát |
| Không đủ quyền | 403 | Không retry vô hạn, log rõ lỗi quyền |
| Backend lỗi | 500/503 | Retry/timeout/fail-fast theo cấu hình |
| Network timeout | Không trả response | Client dừng hoặc fallback theo import policy |
| JSON sai định dạng | Body không hợp lệ | Client báo lỗi parse rõ ràng |
| Thiếu property bắt buộc | 200 nhưng source thiếu key | Binding/validation thất bại |
| Label không tồn tại | 404 hoặc response theo backend | Client không âm thầm dùng label sai |

Ví dụ WireMock trả 503:

~~~java
configServer.stubFor(get(urlPathEqualTo(
        "/orders-service/prod/release-2026.11"))
    .willReturn(aResponse().withStatus(503)));
~~~

Với timeout, dùng delayed response hoặc dừng mock server sau khi client được tạo. Đặt timeout ngắn trong test để không làm suite kéo dài. Nếu test retry, verify số request và khoảng retry theo cấu hình thay vì dùng sleep dài không xác định.

## 12. Kiểm tra authentication và TLS

Nếu Config Server được bảo vệ bằng Basic Authentication hoặc OAuth2, test HTTP mock có thể xác nhận client gửi header đúng:

~~~java
configServer.verify(getRequestedFor(urlPathEqualTo(
        "/orders-service/prod/release-2026.11"))
    .withHeader("Authorization", matching("Basic .+")));
~~~

Không ghi giá trị Authorization thật vào test output. Dùng credential giả lập chỉ dành cho test và không tái sử dụng secret production.

Với TLS, nên có ít nhất một integration test xác nhận truststore/certificate được cấu hình đúng. Không tắt certificate validation trong test rồi coi như đã kiểm thử TLS. Có thể dùng test certificate riêng và truststore fixture, đồng thời kiểm tra hostname/SAN.

Nếu dùng mutual TLS, kiểm tra cả client certificate và server trust chain. Quản lý fixture certificate riêng, có thời hạn rõ ràng và không dùng private key production.

## 13. Kiểm thử refresh sau khi cấu hình thay đổi

Config Client có thể làm mới Environment qua cơ chế refresh của Spring Cloud Context. Nếu ứng dụng expose Actuator refresh, chỉ expose trong mạng quản trị và kiểm thử endpoint bằng POST.

Ví dụ bean cần cập nhật được đánh dấu refresh scope:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class OrderPolicy {

    private final OrderProperties properties;

    public OrderPolicy(OrderProperties properties) {
        this.properties = properties;
    }

    public int maxItems() {
        return properties.getMaxItems();
    }
}
~~~

Một bài kiểm thử refresh nên:

1. Mock hoặc Config Server thật trả max-items = 100.
2. Khởi động Config Client và xác nhận bean đọc 100.
3. Thay response server để trả max-items = 150.
4. Gửi refresh request hoặc gọi ContextRefresher theo cách ứng dụng vận hành.
5. Xác nhận Environment và refresh-scoped bean đọc 150.
6. Xác nhận các bean singleton đã sao chép giá trị cũ không tự đổi.

Endpoint refresh không tự bảo đảm mọi bean đều được tạo lại. Test cần kiểm tra đúng loại bean và consumer thực tế; với nhiều instance, kiểm thử Bus refresh là một bài integration khác.

Trong ví dụ này, OrderProperties phải là bean được Spring Cloud Context rebind khi Environment thay đổi, hoặc bản thân nó phải thuộc refresh scope. Nếu OrderProperties là một object thường không được rebind, chỉ tạo lại OrderPolicy vẫn có thể giữ tham chiếu tới dữ liệu cũ. Hãy kiểm tra lifecycle của cả bean cấu hình lẫn bean tiêu thụ.

## 14. Kiểm thử retry và timeout

Config Server có thể tạm thời không khả dụng khi client khởi động hoặc refresh. Nếu hệ thống cấu hình retry, test các thuộc tính retry đang dùng trong phiên bản Spring Cloud cụ thể, chẳng hạn số lần thử tối đa, khoảng chờ ban đầu và hệ số nhân.

Không nên kiểm thử bằng cách chờ vài chục giây thật nếu có thể dùng clock hoặc test harness phù hợp. Đặt timeout nhỏ, response có kiểm soát và verify số lần request. Cũng cần kiểm tra tình huống server phục hồi trước khi hết retry và tình huống hết retry mà server vẫn lỗi.

Retry không sửa được lỗi 401/403 do policy sai hoặc 404 do label không tồn tại. Phân loại lỗi trước khi cấu hình retry để tránh tạo tải không cần thiết lên Config Server.

## 15. Kiểm thử nhiều nguồn cấu hình

Khi Config Client kết hợp local files, Config Server và Vault, test riêng từng nguồn và test hợp nhất:

- Config Server trả key không nhạy cảm theo application/profile/label.
- Vault trả secret qua Config Data location riêng.
- Local file cung cấp default phù hợp cho developer.
- Environment variable hoặc command line override theo chính sách triển khai.

Không đưa secret thật vào WireMock fixture, Git fixture hoặc test report. Dùng giá trị giả và xác nhận nguồn property bằng metadata thay vì in plaintext.

Nếu cùng key tồn tại trong nhiều nguồn, viết test thể hiện rõ nguồn có thẩm quyền. Một thay đổi thứ tự imports có thể làm giá trị thắng thay đổi dù mọi server đều trả HTTP 200.

## 16. Test isolation và độ ổn định của suite

Config Client test dễ bị ảnh hưởng bởi state dùng chung:

- WireMock server hoặc MockWebServer chưa dừng sau test.
- System properties còn sót lại từ lần chạy trước.
- Spring TestContext cache tái sử dụng context với Config Server URL cũ.
- Port cố định bị test khác chiếm.
- Nhiều test dùng chung stub và request journal.
- Repository fixture bị sửa bởi test chạy song song.

Để giữ suite ổn định:

1. Dùng port ngẫu nhiên và khởi động server trước khi client context được tạo.
2. Đóng Spring context và mock server trong finally hoặc lifecycle callback.
3. Không dùng system property toàn cục nếu test có thể chạy song song; nếu buộc dùng, lưu và khôi phục giá trị cũ.
4. Tách stub theo path hoặc scenario của từng test.
5. Dùng repository fixture riêng hoặc khóa truy cập nếu test thay đổi chung.
6. Không phụ thuộc Internet hoặc Git remote công khai trong test thường xuyên.
7. Đặt timeout hữu hạn để suite không treo khi mock/server mất.

## 17. Phân tầng test trong CI/CD

| Loại test | Phụ thuộc | Mục tiêu | Thời điểm chạy |
|---|---|---|---|
| Property binding unit test | Không cần server | Kiểu dữ liệu, validation và default | Mọi build |
| Config Client + mock HTTP | WireMock/MockWebServer | URL, payload, lỗi HTTP và bootstrap | Mọi pull request |
| Config Server integration | Config Server và repository fixture | Git/JDBC/backend, profile, label và precedence | Pull request hoặc pipeline integration |
| Refresh integration | Config Client, mock/server và Actuator/ContextRefresher | Environment/bean cập nhật sau thay đổi | Pipeline integration |
| Deployment smoke test | Config Server môi trường triển khai | TLS, auth, network và config release thực tế | Sau deploy |

Test thường xuyên nên deterministic và không cần tài nguyên hạ tầng dùng chung. Test môi trường thật cần có dữ liệu không nhạy cảm, timeout rõ ràng và cleanup để tránh để lại repository hoặc secret fixture.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Mock server không nhận request | Import location chưa có trước Config Data bootstrap hoặc sai base URL | Khởi động mock trước client và cung cấp import khi tạo SpringApplication |
| Client gọi sai application | spring.application.name hoặc config name khác dự kiến | Assert request path và cấu hình tên tường minh |
| Profile không đúng | Active profiles bị test context khác ghi đè | Đặt profile trong test properties và kiểm tra request |
| Label không đúng | Thiếu spring.cloud.config.label hoặc URL path encoding sai | Verify path và response metadata |
| Response 200 nhưng property null | JSON sai cấu trúc hoặc key nằm ngoài propertySources.source | Dùng Environment JSON đúng schema |
| Test pass nhưng production fail | Mock không kiểm tra TLS, auth, backend hoặc server repository | Bổ sung integration và deployment smoke test |
| Test suite chập chờn | Port cố định, context cache hoặc shared stub | Dùng dynamic port và cleanup rõ ràng |
| Refresh trả giá trị cũ | Bean không refresh scope hoặc client chưa nạp lại source | Kiểm tra Environment, refresh mechanism và proxy |
| Test retry chạy quá lâu | Timeout/retry production quá lớn trong test | Dùng test-specific timeout và verify request count |

## 19. Checklist kiểm thử Config Client

- [ ] Config Data import được cung cấp trước khi Spring context khởi động.
- [ ] Đã kiểm tra đúng application, profile và label trong request.
- [ ] Mock response tuân theo Environment JSON contract.
- [ ] Property source được nạp vào Spring Environment.
- [ ] ConfigurationProperties bind đúng kiểu và giá trị.
- [ ] Đã kiểm tra thứ tự ưu tiên giữa local và remote source.
- [ ] Đã kiểm tra thiếu key và validation failure.
- [ ] Đã kiểm tra mandatory và optional import.
- [ ] Đã kiểm tra 401, 403, 404, 5xx, timeout và JSON lỗi.
- [ ] Authentication header và TLS được kiểm thử khi có sử dụng.
- [ ] Đã kiểm tra refresh và bean lifecycle nếu ứng dụng hỗ trợ refresh.
- [ ] Có integration test với Config Server thật và repository fixture.
- [ ] Mock server, context và repository fixture được cleanup.
- [ ] Test không dùng secret production hoặc phụ thuộc Internet.
- [ ] Có deployment smoke test sau khi phát hành.

Kiểm thử Config Client cần xác minh toàn bộ đường đi từ Config Data import đến property được bind trong ứng dụng. HTTP giả lập giúp kiểm tra nhanh contract, request context và lỗi; Config Server thật xác minh backend cùng cách tạo Environment. Kết hợp hai loại test với kiểm tra validation, precedence, refresh và smoke test sau deploy giúp phát hiện sai lệch cấu hình trước khi chúng ảnh hưởng đến dịch vụ đang chạy.
