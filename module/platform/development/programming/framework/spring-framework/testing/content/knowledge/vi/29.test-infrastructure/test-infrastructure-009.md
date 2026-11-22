# Không phụ thuộc dịch vụ sản xuất hoặc Internet công khai

## 1. Vì sao kiểm thử cần độc lập với hệ thống bên ngoài?

Một bài kiểm thử tự động nên chạy được trong máy lập trình viên, CI và môi trường phát triển mà không cần gọi đến dịch vụ sản xuất hoặc một API công khai trên Internet. Nếu test gửi request trực tiếp đến hệ thống thật, kết quả có thể phụ thuộc vào trạng thái mạng, dữ liệu của người dùng, giới hạn tốc độ, thời gian hoạt động của nhà cung cấp hoặc cấu hình tài khoản bên ngoài.

Những phụ thuộc này làm test khó lặp lại và có thể gây ra tác động ngoài ý muốn:

- Một API bên ngoài ngừng hoạt động khiến build thất bại dù code của ứng dụng không thay đổi.
- Dữ liệu thực thay đổi theo thời gian, làm assertion hôm nay khác với ngày mai.
- Test gửi email, tạo đơn hàng, thanh toán hoặc ghi dữ liệu vào tài khoản thật.
- Nhiều lượt chạy dùng chung một tài nguyên, dẫn đến xung đột khi chạy song song.
- Token, credential hoặc endpoint sản xuất bị đưa vào log, cấu hình hay môi trường CI.
- Test mất nhiều thời gian chờ network timeout hoặc retry.

Mục tiêu là làm cho test kiểm soát được các hệ thống mà nó tương tác. Trong phần lớn test, các dịch vụ bên ngoài được thay bằng fake, stub hoặc mock. Với những hạ tầng cần kiểm thử hành vi thật như database, broker hoặc cache, có thể chạy một instance cô lập trên máy hoặc trong container. Cả hai cách đều giúp test không dựa vào dịch vụ sản xuất.

## 2. Xác định ranh giới cần cô lập

Trước khi chọn công cụ, hãy xác định test đang kiểm tra phần nào và hệ thống bên ngoài nào nằm ngoài phạm vi đó.

Ví dụ, một ứng dụng đặt hàng có thể gọi:

| Phụ thuộc | Tác động nếu gọi dịch vụ thật | Cách cô lập thường dùng |
|---|---|---|
| Payment gateway | Có thể phát sinh giao dịch thật hoặc giữ tiền | Fake `PaymentGateway`, WireMock hoặc sandbox riêng do nhà cung cấp cung cấp cho contract test được kiểm soát. |
| Inventory API | Dữ liệu kho thay đổi, API có thể giới hạn request | Stub HTTP response hoặc chạy service giả lập cục bộ. |
| Email/SMS provider | Có thể gửi thông báo đến người dùng thật | Fake notification port hoặc SMTP server giả như GreenMail/Mailpit. |
| Database | Chia sẻ dữ liệu, schema hoặc trạng thái giữa các test | Database riêng, schema riêng hoặc Testcontainers. |
| Message broker | Consumer/producer có thể dùng chung topic và làm mất tính xác định | Broker container, topic/consumer group riêng cho test. |
| Object storage | Có thể ghi/xóa file trong bucket thật | Fake storage adapter, MinIO hoặc LocalStack trong môi trường test. |
| Public API | Phụ thuộc DNS, mạng Internet, quota và dữ liệu thay đổi | Fixture, stub server hoặc dữ liệu snapshot đã kiểm soát. |

Không phải test nào cũng cần dựng toàn bộ hệ thống. Unit test nên tập trung vào logic và thay dependency bằng fake đơn giản. Integration test có thể dùng database hoặc broker thật trong container để kiểm tra mapping, transaction và giao thức. Contract test có thể kiểm tra sự tương thích giữa consumer và provider bằng contract đã lưu hoặc môi trường sandbox riêng. End-to-end test nên ít hơn và chỉ chạy trong môi trường được kiểm soát.

## 3. Đưa dịch vụ bên ngoài sau một interface

Một cách hiệu quả để cô lập ứng dụng là đặt mỗi dịch vụ bên ngoài sau một interface thuộc miền nghiệp vụ hoặc application layer. Code nghiệp vụ gọi interface; adapter production thực hiện HTTP, còn test cung cấp implementation giả.

Ví dụ với cổng thanh toán:

```java
public interface PaymentGateway {
    PaymentResult charge(ChargeCommand command);
}

public record ChargeCommand(String orderId, long amountInCents) {
}

public record PaymentResult(String transactionId, boolean approved) {
}
```

Adapter production sử dụng `RestClient` để gọi nhà cung cấp:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class HttpPaymentGateway implements PaymentGateway {

    private final RestClient client;

    HttpPaymentGateway(
            RestClient.Builder builder,
            @Value("${payment.api-base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        return client.post()
                .uri("/charges")
                .body(command)
                .retrieve()
                .body(PaymentResult.class);
    }
}
```

Service nghiệp vụ chỉ phụ thuộc interface:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public PaymentResult checkout(String orderId, long amountInCents) {
        return paymentGateway.charge(
                new ChargeCommand(orderId, amountInCents));
    }
}
```

Trong test service, cung cấp fake implementation để kiểm soát kết quả:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(CheckoutServiceTests.FakePaymentConfiguration.class)
class CheckoutServiceTests {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    FakePaymentGateway fakePaymentGateway;

    @Test
    void returnsTheConfiguredPaymentResult() {
        fakePaymentGateway.nextResult = new PaymentResult("test-tx-42", true);

        PaymentResult result = checkoutService.checkout("order-42", 2500);

        assertThat(result.transactionId()).isEqualTo("test-tx-42");
        assertThat(fakePaymentGateway.lastCommand)
                .isEqualTo(new ChargeCommand("order-42", 2500));
    }

    @TestConfiguration
    static class FakePaymentConfiguration {

        @Bean
        FakePaymentGateway fakePaymentGateway() {
            return new FakePaymentGateway();
        }

        @Bean
        @Primary
        PaymentGateway paymentGateway(FakePaymentGateway fake) {
            return fake;
        }
    }
}

class FakePaymentGateway implements PaymentGateway {

    PaymentResult nextResult = new PaymentResult("test-approved", true);
    ChargeCommand lastCommand;

    @Override
    public PaymentResult charge(ChargeCommand command) {
        lastCommand = command;
        return nextResult;
    }
}
```

Trong test context, bean `PaymentGateway` được inject là fake có `@Primary`. HTTP adapter production không được chọn để phục vụ service này, do đó test không cần credential hay endpoint thanh toán thật. Fake cũng cho phép kiểm tra chính xác command mà service gửi sang cổng thanh toán.

Nếu test cần kiểm tra riêng cách `HttpPaymentGateway` tạo HTTP request, hãy kiểm thử adapter đó bằng `MockRestServiceServer` hoặc một stub HTTP server cục bộ. Không cần gọi dịch vụ thanh toán thật để xác nhận URI, header, JSON body hay cách xử lý response.

## 4. Dùng MockRestServiceServer để giả lập outbound HTTP

`MockRestServiceServer` thuộc Spring Test và có thể kết nối với `RestClient.Builder` hoặc `RestTemplate`. Nó ghi nhận request mà client gửi và trả response do test khai báo, không tạo kết nối mạng đến host trong URI.

Ví dụ kiểm thử adapter `RestClient`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class HttpPaymentGatewayTests {

    @Test
    void sendsChargeRequestAndReadsTheResponse() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://payments.example.invalid");

        MockRestServiceServer server = MockRestServiceServer
                .bindTo(builder)
                .build();

        PaymentGateway gateway = new HttpPaymentGateway(builder,
                "https://payments.example.invalid");

        server.expect(requestTo("https://payments.example.invalid/charges"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withSuccess(
                        """
                        {"transactionId":"test-tx-42","approved":true}
                        """,
                        MediaType.APPLICATION_JSON));

        PaymentResult result = gateway.charge(
                new ChargeCommand("order-42", 2500));

        assertThat(result).isEqualTo(new PaymentResult("test-tx-42", true));
        server.verify();
    }
}
```

Tên miền `.invalid` được dành riêng cho mục đích minh họa và không trỏ đến dịch vụ thật. Quan trọng hơn, `MockRestServiceServer` được bind vào builder mà adapter sử dụng trước khi builder tạo client. Vì vậy, request được xử lý bởi mock server thay vì network request factory thông thường.

Test có thể thêm matcher để kiểm tra header, query parameter và body. `server.verify()` xác nhận mọi expectation đã được thực hiện. Nếu adapter tạo request sai method hoặc URL, expectation sẽ thất bại.

Với `RestTemplate`, cách sử dụng tương tự nhưng bind trực tiếp vào instance:

```java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

`MockRestServiceServer` thích hợp cho test outbound HTTP của adapter. Nó không chạy controller của ứng dụng. Nếu muốn kiểm thử một HTTP client gọi vào chính controller Spring MVC trong cùng tiến trình, `MockMvcClientHttpRequestFactory` là lựa chọn khác; nếu muốn kiểm thử HTTP transport qua socket, dùng mock server như WireMock hoặc MockWebServer.

## 5. Dùng WireMock hoặc MockWebServer cho HTTP integration test cục bộ

Đôi khi cần một HTTP server thật trên loopback để kiểm tra nhiều chi tiết của client hoặc tích hợp với thư viện HTTP không hỗ trợ `MockRestServiceServer`. WireMock và MockWebServer có thể khởi động một server cục bộ trên port ngẫu nhiên, nhận request qua socket và trả response theo stub.

Ví dụ với WireMock:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

@SpringBootTest
class InventoryClientIntegrationTests {

    private static final WireMockServer inventoryServer =
            new WireMockServer(options().dynamicPort());

    static {
        inventoryServer.start();
    }

    @DynamicPropertySource
    static void inventoryProperties(DynamicPropertyRegistry registry) {
        registry.add("inventory.api-base-url", inventoryServer::baseUrl);
    }

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void readsInventoryFromTheLocalStubServer() {
        inventoryServer.stubFor(get(urlEqualTo("/items/42"))
                .willReturn(aResponse()
                        .withHeader("Content-Type", "application/json")
                        .withBody("""
                                {"id":42,"available":true}
                                """)));

        InventoryItem item = inventoryClient.findById(42);

        assertThat(item.available()).isTrue();
    }

    @AfterAll
    static void stopServer() {
        inventoryServer.stop();
    }
}
```

Ví dụ giả định `InventoryClient` đọc property `inventory.api-base-url` khi được tạo và gọi `GET /items/{id}`. `@DynamicPropertySource` đăng ký base URL được WireMock cấp bằng port ngẫu nhiên, do đó Spring context không cần biết port trước khi server khởi động. Không có request nào đi đến API inventory công khai.

Khi test chạy song song, nên dùng port ngẫu nhiên và trạng thái stub riêng cho mỗi test class hoặc test instance. Nếu một server được dùng chung, phải reset mappings và request journal trước mỗi test để không rò rỉ stub hoặc request history. Cũng cần cân nhắc vòng đời của server khi Spring Test cache application context: server phải còn hoạt động trong toàn bộ thời gian context sử dụng property đó.

WireMock có thể kiểm tra header, query, JSON body, thứ tự request và mô phỏng timeout hoặc lỗi HTTP. MockWebServer cung cấp cách tiếp cận tương tự với request queue và recorded request. Chọn một công cụ phù hợp với stack hiện tại thay vì dựng nhiều mock server cho cùng một mục tiêu.

## 6. Dùng Testcontainers cho hạ tầng cần hành vi thật

Không phải mọi phụ thuộc đều nên thay bằng mock. Khi test cần xác nhận SQL, transaction, constraint, migration, broker protocol hoặc cache behavior, một dịch vụ thật trong container thường cho kết quả đáng tin cậy hơn database giả lập hoặc in-memory substitute.

Testcontainers tạo container dùng riêng cho test và ánh xạ port động về máy chạy test. Ví dụ với PostgreSQL:

Với Spring Boot 3.1 trở lên, ví dụ dùng `@ServiceConnection` cần các module test tương ứng. Nếu dự án dùng Spring Boot dependency management, có thể khai báo:

```groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

Để dùng WireMock, thêm thư viện WireMock 3.x vào test dependencies và để dependency management của dự án quản lý phiên bản hoặc khai báo phiên bản tương thích một cách tường minh.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository orderRepository;

    @Test
    void persistsAnOrderInAnIsolatedDatabase() {
        Order saved = orderRepository.save(new Order("order-test-1"));

        assertThat(orderRepository.findById(saved.getId())).isPresent();
    }
}
```

`@ServiceConnection` được Spring Boot hỗ trợ từ 3.1 và tự cung cấp connection details cho service container tương thích. Nếu dùng phiên bản Boot cũ hơn hoặc không dùng Boot service connection, có thể đăng ký JDBC URL, username và password qua `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Testcontainers cần Docker hoặc một runtime container tương thích. Image có thể phải được tải từ registry ở lần đầu tiên; để chạy CI hoàn toàn không phụ thuộc Internet, hãy cache hoặc mirror image trong registry nội bộ trước, rồi cấu hình runner dùng image đó. Sau khi image đã có sẵn, container test có thể chạy cục bộ mà không cần gọi dịch vụ database sản xuất.

Có thể áp dụng cùng mô hình cho Redis, Kafka, RabbitMQ, Elasticsearch hoặc các hạ tầng khác có module Testcontainers. Dùng tên topic, database, schema hoặc bucket riêng cho test và xóa tài nguyên sau khi test kết thúc.

## 7. Cấu hình Spring test để không trỏ đến production

Spring Boot hỗ trợ profile và property source để tách cấu hình test khỏi cấu hình chạy thật. Một file `application-test.yml` có thể chứa các giá trị mặc định an toàn cho môi trường test:

```yaml
payment:
  api-base-url: http://127.0.0.1:9091
inventory:
  api-base-url: http://127.0.0.1:9092
notifications:
  enabled: false
```

Kích hoạt profile trong test:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ApplicationIntegrationTests {
}
```

Các địa chỉ loopback trên chỉ là ví dụ. Test nên thay bằng port động từ WireMock, MockWebServer hoặc Testcontainers khi cần. Việc tắt notification giúp ngăn gửi email/SMS trong test, nhưng vẫn cần fake hoặc stub cho code phụ thuộc notification để test không gọi dịch vụ thật.

Profile chỉ là cách chọn cấu hình, không phải ranh giới bảo mật. Biến môi trường, system property hoặc cấu hình ngoài có thể ghi đè property trong `application-test.yml`. Do đó:

- Không đưa credential production vào môi trường chạy test.
- Không dùng URL production làm fallback khi property test bị thiếu.
- Với cấu hình endpoint bắt buộc, fail fast khi thiếu giá trị hoặc khi host không thuộc danh sách cho phép trong test.
- Dùng port ngẫu nhiên và loopback cho dịch vụ giả lập.
- Tách cấu hình và secret của CI test khỏi secret của production.

Có thể thêm kiểm tra cấu hình để từ chối endpoint không an toàn khi test profile được bật. Ví dụ sau minh họa kiểm tra hostname của một URI trước khi khởi tạo HTTP client:

```java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
class TestEndpointGuard {

    TestEndpointGuard(@Value("${payment.api-base-url}") String baseUrl) {
        URI uri = URI.create(baseUrl);
        String host = uri.getHost();

        if (host == null || !(host.equals("localhost")
                || host.equals("127.0.0.1")
                || host.equals("::1"))) {
            throw new IllegalStateException(
                    "Payment endpoint must be local while the test profile is active");
        }
    }
}
```

Đây là guard đơn giản cho một cấu hình test. Với hệ thống phức tạp, nên quản lý danh sách endpoint được phép theo từng adapter và áp dụng chính sách egress ở CI hoặc network namespace. Kiểm tra chuỗi URL đơn thuần không thay thế được kiểm soát mạng vì DNS, redirect và proxy cũng có thể ảnh hưởng đích kết nối.

## 8. Ngăn test tạo side effect thật

Ngoài HTTP client, các side effect có thể xuất hiện từ scheduler, listener, message consumer, email sender, file storage hoặc tác vụ khởi chạy khi application context được tạo.

Một số cách kiểm soát phổ biến:

| Thành phần | Cách kiểm soát trong test |
|---|---|
| Email/SMS | Thay adapter bằng fake; kiểm tra message được tạo thay vì gửi ra ngoài. |
| Thanh toán | Fake gateway hoặc stub response; dùng sandbox riêng chỉ trong contract test có kiểm soát. |
| Scheduler | Tắt scheduling trong test hoặc cấu hình scheduler không thực thi job tự động. |
| Message consumer | Dùng broker container và topic riêng; hoặc thay consumer bằng fake trong test service. |
| Cloud storage | Dùng local emulator/container hoặc fake storage port; không dùng bucket production. |
| Webhook | Gửi đến WireMock cục bộ và xác nhận payload, retry, signature. |
| Analytics/telemetry | Dùng exporter test hoặc tắt exporter outbound trong test context. |
| File system | Dùng thư mục tạm riêng cho test và dọn sau khi hoàn tất. |

Không nên chỉ tắt exception hoặc nuốt lỗi network để test tiếp tục. Điều đó có thể che giấu việc code vô tình gọi endpoint thật. Hãy làm cho dependency được thay thế rõ ràng và để test thất bại nếu một đường đi ra ngoài ranh giới dự kiến.

## 9. Cô lập dữ liệu và chạy test song song

Ngay cả khi không gọi dịch vụ production, test vẫn có thể không ổn định nếu nhiều test chia sẻ cùng một tài nguyên cục bộ. Ví dụ, hai test cùng dùng một database, topic hoặc WireMock server có thể ghi đè dữ liệu và expectation của nhau.

Các kỹ thuật giúp giảm xung đột:

- Tạo database/schema/topic/bucket riêng cho mỗi test class hoặc test suite.
- Dùng UUID hoặc namespace riêng cho dữ liệu test, tránh ID cố định dùng chung.
- Dùng port ngẫu nhiên để tránh xung đột khi nhiều server giả chạy cùng lúc.
- Reset stub, request journal và trạng thái fake trước mỗi test.
- Không dùng static mutable state cho kết quả fake nếu test có thể chạy song song.
- Dọn container, file tạm, listener và executor sau khi test hoàn tất.
- Với Spring context cache, đảm bảo tài nguyên mà context giữ tham chiếu không bị dừng quá sớm.

Một test nên tự tạo dữ liệu cần thiết và không phụ thuộc vào thứ tự chạy. Nếu cần seed data lớn, dùng fixture versioned hoặc script test được quản lý cùng mã nguồn.

## 10. Phân biệt test isolation với offline build

Hai khái niệm này liên quan nhưng không giống nhau:

| Khía cạnh | Ý nghĩa | Cách xử lý |
|---|---|---|
| Test không gọi dịch vụ production | Ứng dụng và test không gửi request hoặc side effect đến hệ thống thật. | Fake, stub, local server, container riêng, cấu hình test an toàn và chặn egress. |
| Test không cần Internet khi chạy | Test runtime chỉ dùng tài nguyên cục bộ hoặc nội bộ đã chuẩn bị. | Cache/mirror image và fixture; không gọi API công khai trong test. |
| Build không cần Internet | Gradle/Maven không phải tải plugin hoặc dependency từ repository bên ngoài trong lần build đó. | Chuẩn bị dependency cache hoặc repository mirror; dùng chế độ offline khi phù hợp. |

Ví dụ `./gradlew test --offline` yêu cầu Gradle dùng các dependency đã có trong cache và không truy cập repository để tải dependency mới. Tùy chọn này không chặn một đoạn code test gọi `https://api.example.com` bằng HTTP client. Ngược lại, test không gọi Internet vẫn có thể cần Internet ở bước dependency resolution nếu thư viện chưa được cache.

Để CI thật sự độc lập với Internet, cần chuẩn bị dependency và container image trước, sau đó chạy test trong runner không có outbound network hoặc chỉ cho phép kết nối đến dịch vụ nội bộ được chỉ định. Đây là chính sách môi trường chạy, không phải điều mà `@ActiveProfiles("test")` tự đảm bảo.

## 11. Kiểm soát egress ở CI

Một lớp bảo vệ mạnh là cấu hình runner hoặc network policy chỉ cho phép kết nối đến các dịch vụ test cần thiết. Ví dụ, CI có thể:

1. Tải dependency từ artifact repository nội bộ.
2. Lấy container image từ registry nội bộ đã mirror.
3. Khởi động database, broker và HTTP stub trên network riêng của job.
4. Chạy test với biến môi trường chỉ chứa endpoint nội bộ.
5. Chặn outbound Internet và các dải mạng production trong giai đoạn test.
6. Thu thập log, report và dọn tài nguyên sau job.

Không nên dựa vào `/etc/hosts`, DNS giả hoặc thay URL bằng một chuỗi không tồn tại như biện pháp bảo vệ duy nhất. Những cách đó không chặn được mọi đường kết nối, redirect hoặc proxy. Network egress policy ở runner/container là ranh giới phù hợp để ngăn test vô tình gọi ra ngoài.

Nếu một số test bắt buộc phải gọi sandbox bên thứ ba để xác nhận hợp đồng, hãy tách chúng thành nhóm riêng, dùng credential sandbox có quyền hạn thấp, giới hạn lịch chạy và chỉ allowlist đúng host cần thiết. Nhóm test thông thường vẫn phải chạy mà không cần Internet công khai.

## 12. Contract test để tránh stub lệch khỏi API thật

Fake và stub làm test nhanh, ổn định, nhưng có nguy cơ mô phỏng sai hành vi của provider. Ví dụ, stub luôn trả HTTP 200 trong khi API thật có thể trả 409 cho trạng thái xung đột hoặc thay đổi tên field trong JSON.

Có thể giảm rủi ro bằng contract test:

- Lưu contract hoặc schema API trong repository và kiểm tra request/response của consumer với contract đó.
- Dùng provider verification để xác nhận service provider thực hiện đúng contract.
- Chỉ chạy test với sandbox thật khi cần thiết và không dùng dữ liệu production.
- Version hóa fixture, schema và stub mapping để thay đổi API được review cùng code.
- Giữ một số integration test với local server/container để xác nhận serialization, HTTP status và protocol behavior.

Contract test không yêu cầu mọi lần chạy unit test phải gọi provider thật. Consumer có thể xác minh hành vi của mình bằng contract được version hóa; provider xác minh contract trong pipeline của chính provider. Khi cần test end-to-end qua network, dùng môi trường staging/sandbox riêng biệt và dữ liệu có thể hủy.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test thỉnh thoảng thất bại dù code không đổi | Phụ thuộc API công khai, mạng hoặc dữ liệu thay đổi. | Thay bằng fake/stub hoặc local service có dữ liệu xác định. |
| CI gửi email hoặc tạo giao dịch thật | Application context nạp adapter production hoặc scheduler tự chạy. | Import test configuration, thay adapter bằng fake và tắt side effect tự động. |
| Test profile vẫn gọi production | Environment variable hoặc system property ghi đè URL test; thiếu property rơi về default production. | Không dùng fallback production, validate endpoint và tách secret môi trường. |
| WireMock test dùng nhầm port hoặc không kết nối được | Server chưa start khi Spring context đọc property hoặc port bị cố định và xung đột. | Khởi động server trước khi context load, dùng port động và `@DynamicPropertySource`. |
| Testcontainers không khởi động khi offline | Docker image chưa có trong cache hoặc runner không truy cập registry. | Mirror/cache image trước job và cấu hình image nội bộ. |
| Test song song bị lẫn dữ liệu | Chia sẻ database, topic, stub mapping hoặc static mutable fake. | Tạo namespace/tài nguyên riêng, reset trạng thái và dùng port ngẫu nhiên. |
| Stub pass nhưng production integration lỗi | Stub không phản ánh contract provider hiện tại. | Version hóa contract, bổ sung provider verification hoặc sandbox test có kiểm soát. |
| `--offline` nhưng test vẫn gọi Internet | Gradle offline chỉ điều khiển dependency resolution, không chặn network của code test. | Dùng network egress policy để chặn outbound ở runtime. |

## 14. Quy trình thiết kế test độc lập

Khi thêm một phụ thuộc bên ngoài vào ứng dụng hoặc test, có thể áp dụng trình tự sau:

1. Xác định interface/adapter đại diện cho dịch vụ bên ngoài và phần code cần được kiểm thử.
2. Với unit/service test, thay adapter bằng fake hoặc mock có kết quả xác định.
3. Với outbound HTTP adapter, dùng `MockRestServiceServer` để kiểm tra request/response mà không có network.
4. Khi cần kiểm tra HTTP stack thật của client, dùng WireMock hoặc MockWebServer trên loopback với port động.
5. Với database, broker hoặc cache cần hành vi thật, dùng Testcontainers hoặc dịch vụ cục bộ cô lập.
6. Cấu hình test profile và dynamic properties để mọi endpoint trỏ đến fake/local resource; không dùng credential production.
7. Cô lập dữ liệu và reset tài nguyên để test có thể chạy song song, lặp lại.
8. Chuẩn bị dependency và container image trong cache/mirror nếu cần chạy không Internet.
9. Chặn egress ở CI để phát hiện ngay khi code vô tình gọi dịch vụ công khai hoặc production.
10. Dùng contract test riêng để bảo đảm fake/stub vẫn phản ánh hợp đồng API mà ứng dụng cần tuân thủ.

## 15. Kết luận

Test đáng tin cậy phải kiểm soát được các dịch vụ mà nó phụ thuộc. Hãy đặt dịch vụ ngoài sau interface, dùng fake hoặc `MockRestServiceServer` cho test tập trung, dùng WireMock/MockWebServer khi cần HTTP server cục bộ và dùng Testcontainers khi cần database hoặc broker thật trong môi trường cô lập. Profile và dynamic properties giúp chọn đúng endpoint, còn CI egress policy ngăn kết nối ngoài ý muốn. Cuối cùng, contract test giúp stub không lệch khỏi API provider. Nhờ đó, test có thể chạy lặp lại trong CI mà không chạm vào dữ liệu, credential hoặc dịch vụ sản xuất.
