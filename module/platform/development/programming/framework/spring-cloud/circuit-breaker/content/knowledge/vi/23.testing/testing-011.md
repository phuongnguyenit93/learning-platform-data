# Kiểm thử tích hợp bằng HTTP giả lập và registry được cô lập

## Mục tiêu

Unit test có thể kiểm tra riêng một hàm fallback hoặc cách phân loại exception, nhưng chưa chứng minh toàn bộ luồng Spring hoạt động đúng. Một bài kiểm thử tích hợp cần khởi tạo application context, tạo Circuit Breaker qua factory thật, gửi HTTP tới một upstream giả lập và quan sát trạng thái cùng số request thực tế. Registry Resilience4j nên được tạo riêng cho test context để trạng thái của một bài test không rò sang bài khác.

Sau bài học, bạn có thể:

- Dùng WireMock giả lập phản hồi thành công, lỗi HTTP và độ trễ của dependency.
- Khởi tạo Spring Boot test context với `CircuitBreakerFactory` thật.
- Tạo `CircuitBreakerRegistry` riêng trong test context và kiểm tra trạng thái instance.
- Xác minh fallback, số request upstream và chuyển trạng thái `CLOSED` sang `OPEN`.
- Làm cho test ổn định bằng port động, cấu hình ngưỡng nhỏ và dọn dẹp tài nguyên.
- Phân biệt kiểm thử Circuit Breaker với kiểm thử timeout, retry và Bulkhead.

## Vì sao cần kiểm thử tích hợp?

Một bài unit test gọi trực tiếp fallback có thể chứng minh fallback trả đúng chuỗi hoặc DTO. Tuy nhiên, nó không kiểm tra được:

- Spring có tạo đúng `CircuitBreakerFactory` và bind đúng cấu hình instance hay không.
- HTTP client có thật sự gửi request tới upstream hay không.
- Exception do HTTP client ném ra có được Circuit Breaker ghi nhận hay không.
- Khi mạch `OPEN`, supplier có bị chặn trước khi tạo thêm HTTP request hay không.
- Fallback có được gọi và trả response đúng hợp đồng hay không.
- Registry được test quan sát có phải registry mà integration đang dùng hay không.

Kiểm thử tích hợp dùng một HTTP server giả lập để điều khiển kết quả upstream. Test không cần khởi chạy catalog-service thật hoặc phụ thuộc mạng ngoài. Đồng thời, một registry riêng trong Spring context giúp trạng thái Circuit Breaker có vòng đời gắn với test, dễ quan sát và không bị chia sẻ ngoài ý muốn.

## Dependency kiểm thử

Ví dụ dùng Spring Cloud CircuitBreaker với Resilience4j, Spring Boot Test và Spring Cloud Contract WireMock. Các phiên bản Spring Boot, Spring Cloud và Resilience4j nên được quản lý bằng BOM tương thích của dự án.

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-wiremock</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu dự án dùng Gradle, khai báo các artifact tương đương trong `testImplementation`. Không tự ghép một phiên bản WireMock hoặc Resilience4j khác major với dependency do Spring Cloud BOM quản lý; kiểm tra dependency tree của đúng release train trước khi nâng version.

## Tạo gateway sử dụng factory thật

Gateway cần tạo Circuit Breaker theo ID ổn định và đặt toàn bộ lời gọi HTTP bên trong supplier của `run`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreaker circuitBreaker;

    public CatalogGateway(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl,
            CircuitBreakerFactory<?, ?> factory) {
        this.restClient = builder.baseUrl(baseUrl).build();
        this.circuitBreaker = factory.create("catalog");
    }

    public String findById(String id) {
        return circuitBreaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(String.class),
                error -> "catalog-fallback");
    }
}
```

`RestClient.Builder` được Spring Boot cung cấp khi ứng dụng có cấu hình HTTP client tương ứng. ID `catalog` phải trùng với instance trong cấu hình Resilience4j. Trong ví dụ, `retrieve()` ném exception với phản hồi HTTP 5xx theo error handling mặc định của RestClient; exception được chuyển tới Circuit Breaker và fallback.

Để test tập trung vào Circuit Breaker, không đặt request HTTP bên ngoài supplier. Nếu gọi HTTP trước `run` rồi mới truyền kết quả vào Circuit Breaker, mạch `OPEN` sẽ không ngăn được request.

## Khởi chạy WireMock trên port động

Test cần một HTTP server giả lập. Dùng port động để tránh xung đột khi chạy song song hoặc khi máy phát triển đã có tiến trình chiếm port mặc định.

```java
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

import com.github.tomakehurst.wiremock.WireMockServer;

class WireMockSupport {
    static final WireMockServer UPSTREAM = startServer();

    private static WireMockServer startServer() {
        WireMockServer server = new WireMockServer(wireMockConfig().dynamicPort());
        server.start();
        return server;
    }
}
```

`UPSTREAM.baseUrl()` trả về địa chỉ có port thực tế sau khi server khởi động. Dùng `@DynamicPropertySource` để đưa địa chỉ đó vào Spring context:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.base-url", WireMockSupport.UPSTREAM::baseUrl);
}
```

Trong test class thực tế, có thể khai báo server là static field và dừng nó trong `@AfterAll`. Điều quan trọng là server phải được khởi động trước khi Spring đọc dynamic property, và phải được dừng sau khi test context không còn sử dụng nó.

## Cô lập CircuitBreakerRegistry cho test context

Resilience4j lưu các instance Circuit Breaker trong `CircuitBreakerRegistry`. Nếu nhiều test cùng dùng một registry tồn tại lâu, một test có thể để instance ở `OPEN`; test sau tiếp tục nhận `CallNotPermittedException` dù nó chưa gửi đủ request lỗi.

Có thể cung cấp một registry riêng trong test context:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class IsolatedCircuitBreakerConfiguration {
    @Bean
    @Primary
    CircuitBreakerRegistry testCircuitBreakerRegistry() {
        CircuitBreakerConfig testDefaults = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();
        return CircuitBreakerRegistry.of(testDefaults);
    }
}
```

Đưa cấu hình này vào test bằng `@Import(IsolatedCircuitBreakerConfiguration.class)`. Khi Resilience4j integration lấy registry qua Spring bean, bean `@Primary` này được dùng và registry có vòng đời thuộc test context. Nếu phiên bản integration hoặc cấu hình dự án tự tạo registry theo một cơ chế riêng, cần xác nhận factory thật đang dùng đúng bean test; không chỉ autowire một registry khác rồi giả định nó chứa instance mà factory tạo.

Trong test, có thể inject `CircuitBreakerRegistry` và đọc instance `catalog` bằng `registry.find("catalog")`. Đây cũng là một cách kiểm tra rằng instance được factory sử dụng đã được đăng ký vào registry test.

`CircuitBreakerRegistry.of(testDefaults)` tạo registry độc lập với registry mặc định toàn cục và đặt ngưỡng cơ sở nhỏ cho test. `@TestPropertySource` đồng thời khai báo cấu hình instance mà Spring Cloud CircuitBreaker integration có thể bind theo phiên bản đang dùng. Giữ hai bộ giá trị nhất quán; nếu integration của dự án cấu hình instance trực tiếp qua factory, hãy xác nhận factory sử dụng registry test và cấu hình `catalog` mong muốn thay vì chỉ dựa vào việc autowire registry.

## Cấu hình ngưỡng nhỏ cho test

Production thường cần sliding window và thời gian chờ đủ lớn để tránh phản ứng quá mức với vài request ngẫu nhiên. Test tích hợp nên dùng cửa sổ nhỏ để chuyển trạng thái xác định với ít request:

```java
@SpringBootTest
@Import(IsolatedCircuitBreakerConfiguration.class)
@TestPropertySource(properties = {
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-type=COUNT_BASED",
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-size=4",
        "resilience4j.circuitbreaker.instances.catalog.minimum-number-of-calls=4",
        "resilience4j.circuitbreaker.instances.catalog.failure-rate-threshold=50",
        "resilience4j.circuitbreaker.instances.catalog.wait-duration-in-open-state=30s"
})
class CatalogGatewayIntegrationTest {
    // Test implementation follows.
}
```

Với bốn mẫu và ngưỡng lỗi 50%, bốn phản hồi lỗi liên tiếp đủ làm Circuit Breaker chuyển `OPEN`. Thời gian `OPEN` 30 giây giúp test có đủ thời gian xác nhận lời gọi tiếp theo bị từ chối mà không tự chuyển sang `HALF_OPEN` giữa các assertion. Đây là cấu hình test; không sao chép nguyên các giá trị này sang production.

## Bài test tích hợp hoàn chỉnh

Ví dụ dưới đây kiểm tra một request thành công, ba lỗi HTTP 500, trạng thái `OPEN` và request thứ năm bị từ chối trước khi tới WireMock:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.getRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.okJson;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.tomakehurst.wiremock.WireMockServer;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(IsolatedCircuitBreakerConfiguration.class)
@TestPropertySource(properties = {
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-type=COUNT_BASED",
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-size=4",
        "resilience4j.circuitbreaker.instances.catalog.minimum-number-of-calls=4",
        "resilience4j.circuitbreaker.instances.catalog.failure-rate-threshold=50",
        "resilience4j.circuitbreaker.instances.catalog.wait-duration-in-open-state=30s"
})
class CatalogGatewayIntegrationTest {
    private static final WireMockServer UPSTREAM = WireMockSupport.UPSTREAM;

    @Autowired
    private CatalogGateway gateway;

    @Autowired
    private CircuitBreakerRegistry registry;

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry properties) {
        properties.add("catalog.base-url", UPSTREAM::baseUrl);
    }

    @BeforeEach
    void resetUpstream() {
        UPSTREAM.resetAll();
    }

    @AfterAll
    static void stopUpstream() {
        UPSTREAM.stop();
    }

    @Test
    void opensCircuitAfterFailuresAndRejectsNextRequest() {
        UPSTREAM.stubFor(get(urlPathEqualTo("/products/ok"))
                .willReturn(okJson("{\"id\":\"ok\"}")));
        UPSTREAM.stubFor(get(urlPathEqualTo("/products/42"))
                .willReturn(aResponse().withStatus(500)));

        assertThat(gateway.findById("ok")).contains("ok");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");

        CircuitBreaker breaker = registry.find("catalog").orElseThrow();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // Lời gọi này bị Circuit Breaker từ chối; upstream không nhận request thứ năm.
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");

        UPSTREAM.verify(1, getRequestedFor(urlPathEqualTo("/products/ok")));
        UPSTREAM.verify(3, getRequestedFor(urlPathEqualTo("/products/42")));
    }
}
```

Ví dụ dùng `WireMockSupport` để giữ phần khởi tạo server tách riêng. Trong dự án, có thể đặt helper và test configuration ở các file test riêng để dễ tái sử dụng.

Test này chứng minh nhiều lớp cùng hoạt động:

1. Spring khởi tạo `CatalogGateway` và inject `CircuitBreakerFactory`.
2. Gateway gửi HTTP request tới WireMock thay vì catalog-service thật.
3. Một request thành công và ba request HTTP 500 được Circuit Breaker ghi nhận.
4. Sau bốn mẫu, tỷ lệ lỗi là 75%, vượt ngưỡng 50%, nên mạch chuyển `OPEN`.
5. Request tiếp theo nhận fallback do Circuit Breaker từ chối; WireMock chỉ nhận ba request lỗi và một request thành công.

Nếu test quan sát thấy request thứ năm vẫn tới upstream, cần kiểm tra registry mà factory đang dùng, tên instance, cấu hình được bind và vị trí lời gọi HTTP trong supplier.

## Kiểm tra HTTP giả lập theo từng kịch bản

WireMock có thể tạo nhiều phản hồi để kiểm tra các tình huống khác nhau:

| Kịch bản | Stub HTTP | Điều cần xác nhận |
|---|---|---|
| Upstream khỏe | 200 với JSON hợp lệ. | Gateway trả dữ liệu thật; Circuit Breaker ghi nhận success. |
| Upstream lỗi server | 500 hoặc 503. | Client ném exception; Circuit Breaker ghi nhận failure và fallback được gọi. |
| Upstream chậm | Delay lớn hơn timeout đã cấu hình. | TimeLimiter hoặc HTTP client timeout kết thúc lời gọi theo chính sách. |
| Upstream không kết nối được | Dừng server hoặc dùng port không có listener. | Lỗi kết nối được phân loại và xử lý như dự kiến. |
| Mạch `OPEN` | Không cần stub mới. | Supplier không chạy; số request tới WireMock không tăng. |
| Phục hồi | Trả 200 sau thời gian `OPEN`. | Probe `HALF_OPEN` thành công và mạch có thể về `CLOSED`. |

Ví dụ WireMock cho response chậm:

```java
UPSTREAM.stubFor(get(urlPathEqualTo("/products/slow"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(1_500)
                .withBody("{\"id\":\"slow\"}")
                .withHeader("Content-Type", "application/json")));
```

Nếu timeout của HTTP client là 500 ms, request có thể thất bại trước khi WireMock trả response. Không chỉ dựa vào TimeLimiter: kiểm tra cả timeout ở tầng HTTP client và khả năng hủy request. Khi timeout xảy ra, server giả lập có thể vẫn hoàn tất việc ghi response dù client đã ngắt kết nối.

## Cô lập registry giữa nhiều test

Có ba nguyên tắc giúp test không phụ thuộc thứ tự chạy:

- Tạo `CircuitBreakerRegistry` mới trong test application context thay vì dùng một static registry dùng chung cho cả suite.
- Dùng `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)` khi cần đóng context sau class và bảo đảm bean/registry được tạo lại ở lần chạy sau.
- Nếu test nhiều trạng thái trong cùng context, dùng ID riêng cho từng kịch bản hoặc chủ động reset trạng thái bằng API phù hợp; không dựa vào thứ tự test ngầm định.

Ví dụ:

```java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CatalogGatewayIntegrationTest {
    // Test context và registry được đóng sau class.
}
```

Nếu dùng `@TestInstance(PER_CLASS)` hoặc giữ WireMock server tĩnh, vẫn phải quản lý lifecycle server riêng. Đóng Spring context không tự động dừng một `WireMockServer` do test tự tạo nếu không đăng ký cơ chế cleanup.

Không tạo registry mới trong từng assertion hoặc trong mỗi lần gọi gateway. Mục đích là cô lập registry theo test context, còn các lời gọi trong cùng một scenario phải đi qua cùng instance để có thể tích lũy mẫu và chuyển trạng thái.

## Kiểm thử HALF_OPEN mà không phụ thuộc sleep dài

Sau khi Circuit Breaker `OPEN`, hết `waitDurationInOpenState` thì mạch có thể chuyển sang `HALF_OPEN`. Test nên kiểm soát thời gian chờ để tránh chậm và flaky:

- Dùng `waitDurationInOpenState` ngắn trong profile test, nhưng đủ để assertion `OPEN` hoàn tất.
- Dùng Awaitility hoặc polling có timeout để chờ điều kiện trạng thái thay vì `Thread.sleep` cố định dài.
- Đặt `permittedNumberOfCallsInHalfOpenState` nhỏ để xác minh số probe.
- Sau khi mạch chuyển `HALF_OPEN`, stub một số response thành công và kiểm tra mạch về `CLOSED` khi đủ kết quả.
- Tạo một scenario khác với probe thất bại để xác nhận mạch quay lại `OPEN`.

Không dùng `waitDurationInOpenState: 0` nếu mục tiêu là quan sát trạng thái `OPEN` ổn định: mạch có thể chuyển tiếp quá nhanh khi có request mới. Với test cần kiểm soát thời gian tuyệt đối, có thể dùng clock được hỗ trợ bởi phiên bản Resilience4j đang dùng hoặc kiểm thử state transition riêng ở tầng registry; đừng giả định mọi integration cho phép inject clock qua factory.

## Kiểm tra fallback và response contract

Fallback cần được xác minh như một phần của hợp đồng API, không chỉ kiểm tra rằng một giá trị bất kỳ đã được trả về:

- Với dữ liệu cache, xác nhận trường metadata cho biết dữ liệu cũ hoặc suy giảm.
- Với dependency không khả dụng, xác nhận status và error code phù hợp.
- Với lỗi nghiệp vụ như 404, xác nhận không bị biến thành fallback hạ tầng nếu chính sách không xem đó là lỗi Circuit Breaker.
- Với thao tác ghi, xác nhận timeout không tạo kết quả thành công giả và retry dùng idempotency key nếu được hỗ trợ.
- Xác nhận fallback không gọi lại chính upstream đang lỗi.

Nếu gateway trả DTO, nên deserialize response và assert các trường quan trọng thay vì so sánh toàn bộ JSON string. Nếu gateway trả status HTTP, dùng WebTestClient hoặc MockMvc phù hợp với loại ứng dụng để kiểm tra status, header và body ở ranh giới controller.

## Các giới hạn của test registry và HTTP giả lập

Registry cô lập chứng minh state machine trong một JVM và một Spring context. Nó không mô phỏng việc đồng bộ trạng thái giữa nhiều pod; Resilience4j Circuit Breaker thường giữ trạng thái cục bộ theo instance ứng dụng.

WireMock mô phỏng giao thức HTTP và các phản hồi đã cấu hình. Nó không mô phỏng đầy đủ TLS, DNS, load balancer, network partition, connection reuse, giới hạn file descriptor hoặc tải của một upstream thật. Các bài kiểm thử tải và môi trường staging vẫn cần thiết để xác nhận pool sizing, latency phân vị và khả năng phục hồi.

Một HTTP server giả lập trả 500 giúp kiểm tra phân loại exception của client. Nếu ứng dụng dùng WebClient reactive, cần viết test theo reactive pipeline và xác nhận subscription; không dùng một test đồng bộ để suy luận toàn bộ semantics reactive.

## Lỗi thường gặp

- **Mock CircuitBreakerFactory thay vì dùng factory thật:** test không còn xác minh integration, registry và cấu hình instance.
- **Dùng registry tĩnh chung cho mọi test:** trạng thái `OPEN` từ test trước có thể làm test sau thất bại.
- **Autowire registry khác với registry của factory:** assertion nhìn thấy state không phản ánh lời gọi thật.
- **Dùng port cố định:** test có thể xung đột với tiến trình khác hoặc chạy song song.
- **Không reset WireMock:** mapping và request journal từ test trước có thể ảnh hưởng assertion.
- **Không đặt lời gọi HTTP trong supplier:** Circuit Breaker không chặn được request khi `OPEN`.
- **Chỉ assert fallback:** không biết upstream có bị gọi thêm hay không; hãy verify số request.
- **Dùng ngưỡng production quá lớn:** test cần quá nhiều request hoặc chạy quá lâu mới chuyển trạng thái.
- **Dùng sleep dài cố định:** làm test chậm và dễ flaky trên CI.
- **Quên dừng WireMock:** port và thread server có thể còn tồn tại sau test.
- **Cho rằng test WireMock chứng minh network production:** cần thêm kiểm thử môi trường và tải cho các vấn đề connection/pool thực tế.

## Thực hành hoàn chỉnh

Hãy tạo một test class với Spring Boot context, `CircuitBreakerFactory` thật, registry riêng và WireMock server port động. Chạy lần lượt các kịch bản sau:

1. Request thành công: xác nhận body thật được trả về và registry ghi nhận success.
2. Request lỗi 500: xác nhận fallback, failure count và số request upstream.
3. Nhiều lỗi liên tiếp: xác nhận Circuit Breaker chuyển `OPEN` khi đạt `minimumNumberOfCalls` và failure threshold.
4. Request khi `OPEN`: xác nhận fallback được gọi nhưng WireMock không nhận thêm request.
5. Upstream chậm: xác nhận timeout của HTTP client hoặc TimeLimiter kết thúc lời gọi theo cấu hình.
6. Upstream phục hồi: xác nhận probe `HALF_OPEN` được giới hạn và mạch về `CLOSED` khi đủ kết quả thành công.
7. Chạy lại class hoặc test suite theo thứ tự khác: xác nhận registry được tạo mới và không phụ thuộc trạng thái của lần chạy trước.

Ghi lại trạng thái Circuit Breaker, số lần gọi thật tới WireMock, số lần fallback, thời gian xử lý và loại exception. Một bài test tích hợp tốt phải chứng minh cả hành vi của ứng dụng lẫn việc dependency không bị gọi thêm sau khi Circuit Breaker đã mở.
