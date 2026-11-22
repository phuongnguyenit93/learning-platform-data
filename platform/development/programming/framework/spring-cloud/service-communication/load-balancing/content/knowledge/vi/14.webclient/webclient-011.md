# Kiểm thử lời gọi reactive có cân bằng tải

Trong kiến trúc microservices, **WebClient** thường được sử dụng để gọi HTTP theo mô hình reactive. Khi kết hợp **Spring Cloud LoadBalancer**, WebClient có thể gọi một địa chỉ logic như **http://inventory-service/api/stock/BOOK-01**; framework sẽ lấy danh sách **ServiceInstance**, chọn một bản sao và thay tên dịch vụ bằng host/port thật trước khi gửi request.

Một bài kiểm thử chỉ xác nhận JSON trả về đúng **chưa đủ** để khẳng định client-side load balancing hoạt động. Cần chứng minh cả ba điều:

1. **Luồng reactive đúng:** Mono/Flux phát giá trị, lỗi, completion hoặc cancellation theo contract.
2. **Lựa chọn instance đúng:** service ID được phân giải, danh sách ứng viên được dùng và một bản sao hợp lệ được chọn.
3. **HTTP thật đúng:** request được gửi đến host/port đã chọn, giữ đúng method, path, query và headers; lỗi mạng/HTTP được xử lý đúng.

Bài học trình bày chiến lược kiểm thử nhiều tầng, từ **StepVerifier + ExchangeFunction giả** đến **Spring Boot integration test với MockWebServer**. Nội dung cũng đề cập timeout, retry, source discovery rỗng, phản hồi 4xx/5xx, Reactor Context, tránh blocking và tính ổn định của test.

## 1. Hiểu luồng WebClient có Spring Cloud LoadBalancer

~~~mermaid
flowchart TD
    A["OrderService gọi WebClient"] --> B["URI logic: http://inventory-service/..."]
    B --> C["ReactorLoadBalancerExchangeFilterFunction"]
    C --> D["ReactiveLoadBalancer / LoadBalancerClientFactory"]
    D --> E["ServiceInstanceListSupplier"]
    E --> F["Discovery, cache, health, zone, hint"]
    F --> G["Chọn ServiceInstance"]
    G --> H{"Có instance hợp lệ?"}
    H -->|Không| I["Response lỗi / lỗi ở tầng LB"]
    H -->|Có| J["Tái dựng URI vật lý"]
    J --> K["HTTP connector gửi request"]
    K --> L["Backend trả HTTP response hoặc lỗi I/O"]
    L --> M["WebClient decode thành Mono/Flux"]
    M --> N["StepVerifier kiểm tra tín hiệu"]
~~~

Trong Spring Cloud LoadBalancer, **ReactorLoadBalancerExchangeFilterFunction** là bộ lọc tích hợp WebClient với **ReactiveLoadBalancer**. Nó sử dụng host của URI ban đầu như **service ID**, chọn ServiceInstance và tạo request mới trỏ đến địa chỉ thật. **RoundRobinLoadBalancer** là thuật toán thường được dùng mặc định, nhưng ứng dụng có thể cấu hình chính sách khác.

**Phân biệt rõ hai lớp:**

- **WebClient** tạo request, thực thi I/O qua connector và trả Publisher (Mono/Flux).
- **Spring Cloud LoadBalancer** chọn instance. Nó không quyết định business meaning của JSON, HTTP 404 hay việc có retry POST không.

Việc gọi **Mono** không đồng nghĩa request đã được gửi. Với pipeline cold thông thường, các thao tác chỉ chạy **khi có subscription**. Một test tạo Mono nhưng không subscribe/verify có thể vượt qua mà chưa hề gọi LoadBalancer hoặc backend.

## 2. Ma trận: kiểm tra cái gì ở tầng nào?

| Mục tiêu kiểm thử | Công cụ phù hợp | Có chạy HTTP thật? | Có kiểm tra LoadBalancer thật? |
| --- | --- | --- | --- |
| Xây request, path, query, headers | WebClient + ExchangeFunction giả | Không | Không, trừ khi chủ động thêm LB filter |
| Chuyển JSON sang DTO, mapping lỗi | ExchangeFunction hoặc mock connector | Không | Không |
| Mono phát giá trị/lỗi/completion đúng | StepVerifier | Tùy nguồn Publisher | Chỉ khi Publisher đi qua LB |
| Lọc danh sách instance/thuật toán | Supplier/ReactiveLoadBalancer test cô lập | Không | Có, ở tầng chọn instance |
| Service ID thành host/port thật | @LoadBalanced WebClient + MockWebServer | Có | Có |
| Retry chuyển instance sau lỗi | LB integration + mock servers + retry rõ ràng | Có | Có nếu retry được cấu hình |
| Socket timeout/connection reset/TLS | MockWebServer hoặc WireMock | Có | Có nếu dùng client đã gắn LB |
| WebFlux controller phản hồi đúng | WebTestClient | Có thể không | Không mặc nhiên |
| Discovery/registry thực tế | Testcontainers/provider hoặc test environment | Có | Có nếu dùng setup đầy đủ |

**WebTestClient** là công cụ để kiểm thử **HTTP server/controller** theo contract; nó có thể hoạt động không cần server thật. Trong khi đó, để kiểm thử một **WebClient outbound có load balancing**, tài liệu Spring Framework khuyến nghị dùng **mock HTTP server** như OkHttp MockWebServer hoặc WireMock. Hai công cụ có chữ WebClient trong tên không đồng nghĩa cùng mục tiêu.

## 3. Cấu hình WebClient trong ứng dụng thật

Ví dụ cấu hình Spring Cloud:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Client nghiệp vụ có contract đơn giản:

~~~java
record StockResponse(String sku, int available, String instanceId) {
}

@Service
class InventoryClient {

    private final WebClient webClient;

    InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

Khi gọi **getStock("BOOK-01")**, LoadBalancer dùng service ID **inventory-service** để tìm instance. Nếu chọn **10.0.0.42:8082**, URI thực có dạng **http://10.0.0.42:8082/api/stock/BOOK-01**.

Để tích hợp cần:

- Spring WebFlux/WebClient trên classpath, thường qua **spring-boot-starter-webflux** ở các thế hệ Spring Boot tương ứng.
- **spring-cloud-starter-loadbalancer** và BOM Spring Cloud tương thích.
- Nguồn ServiceInstance, ví dụ Eureka, Consul, Kubernetes hoặc SimpleDiscoveryClient.
- Đúng **@LoadBalanced WebClient.Builder** hoặc filter tích hợp được thêm thủ công.

**Không thêm LoadBalancer filter hai lần.** Nếu WebClient.Builder đã được @LoadBalanced và Spring Cloud tự thêm filter, không được lại tự gọi **.filter(lbFunction)** trên cùng builder. Double load balancing có thể khiến host vật lý bị đọc lại như service ID, sinh lỗi khó hiểu.

## 4. Chuẩn bị dependency kiểm thử

Ví dụ Gradle ở mức khai báo dependency (chọn phiên bản theo Spring Boot/Spring Cloud BOM thực tế):

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    // Ví dụ dưới dùng API okhttp3.mockwebserver.* của dòng OkHttp 4.x.
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
~~~

Ví dụ sử dụng **MockWebServer 4.x** với package **okhttp3.mockwebserver**. Nếu dự án dùng OkHttp 5.x, package/API mock server có thể khác; cần cập nhật import và dependency đồng bộ. Không bắt buộc chọn MockWebServer: WireMock cũng có thể mô phỏng endpoint và lỗi HTTP ở tầng mạng.

Trong test, các import quan trọng thường gồm:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.*;
~~~

Đây là **danh sách import minh họa**, không phải class Java hoàn chỉnh. Tùy từng test có thể cần thêm import Mono, Flux, ClientResponse, HttpStatus, ExchangeFunction hoặc Reactor Retry tương ứng.

## 5. Kiểm thử tín hiệu reactive trước khi kiểm thử HTTP

**StepVerifier** thuộc thư viện **reactor-test**. Nó đăng ký subscription và kiểm tra từng tín hiệu Publisher phát ra:

- **onNext:** một giá trị được phát.
- **onComplete:** luồng kết thúc bình thường.
- **onError:** luồng kết thúc với ngoại lệ.
- **cancel:** subscriber ngừng nhận dữ liệu; không nhất thiết có onComplete.

Ví dụ kiểm thử một Mono đơn giản:

~~~java
Mono<StockResponse> response =
        Mono.just(new StockResponse("BOOK-01", 7, "inventory-a"));

StepVerifier.create(response)
        .assertNext(stock -> {
            assertEquals("BOOK-01", stock.sku());
            assertEquals(7, stock.available());
            assertEquals("inventory-a", stock.instanceId());
        })
        .verifyComplete();
~~~

Ví dụ kiểm tra lỗi:

~~~java
Mono<StockResponse> response =
        Mono.error(new IllegalStateException("downstream failed"));

StepVerifier.create(response)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                        && error.getMessage().contains("downstream"))
        .verify();
~~~

**verifyComplete()** khẳng định Mono phát giá trị kỳ vọng rồi hoàn thành; **expectError...verify()** khẳng định luồng kết thúc bằng lỗi. Đây là assertion về **reactive contract**, chưa chứng minh service ID đã được giải qua LoadBalancer.

### 5.1. Không gọi block() để test reactive

Test dạng:

~~~java
StockResponse result = client.getStock("BOOK-01").block();
assertEquals(7, result.available());
~~~

có thể kiểm tra giá trị, nhưng không kiểm tra rõ tín hiệu, cancellation, số sự kiện hay nhánh onError. Nó còn tạo thói quen dùng **block()** trong ứng dụng reactive, vốn nguy hiểm trên WebFlux event-loop.

StepVerifier cũng chờ ở test thread để xác minh luồng, nhưng đây là **công cụ test** chứ không phải một operator blocking được đưa vào production pipeline. Luôn đặt giới hạn thời gian xác minh để tránh test treo vô hạn:

~~~java
StepVerifier.create(client.getStock("BOOK-01"))
        .expectNextMatches(stock -> stock.available() >= 0)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

Đây là **timeout của test**, không tự cấu hình HTTP response timeout hoặc deadline cho WebClient production.

## 6. Test WebClient bằng ExchangeFunction giả: nhanh, nhưng không đủ cho LB

WebClient cho phép thay **ExchangeFunction** bằng một hàm giả. Đây là cách kiểm tra serialization/decoding và request-building mà không mở socket:

~~~java
AtomicReference<URI> seenUrl = new AtomicReference<>();

ExchangeFunction fakeExchange = request -> {
    seenUrl.set(request.url());
    return Mono.just(ClientResponse.create(HttpStatus.OK)
            .header("Content-Type", "application/json")
            .body("""
                    {"sku":"BOOK-01","available":7,"instanceId":"fake"}
                    """)
            .build());
};

WebClient client = WebClient.builder()
        .baseUrl("http://inventory-service")
        .exchangeFunction(fakeExchange)
        .build();

Mono<StockResponse> result = client.get()
        .uri("/api/stock/{sku}", "BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);

StepVerifier.create(result)
        .assertNext(stock -> assertEquals(7, stock.available()))
        .verifyComplete();

assertEquals("inventory-service", seenUrl.get().getHost());
assertEquals("/api/stock/BOOK-01", seenUrl.get().getPath());
~~~

Các import bổ sung:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
~~~

**Đây không phải test LoadBalancer.** WebClient trên không được gắn @LoadBalanced hoặc ReactorLoadBalancerExchangeFilterFunction; URI nhìn thấy ở fake exchange vẫn chứa host logic **inventory-service**. Test chỉ chứng minh request được tạo đúng và JSON được decode thành StockResponse.

Nếu fake ExchangeFunction trả về ngay một ClientResponse giả, nó có thể che đi các lỗi transport, TLS, connection pooling hoặc network cancellation. Cần test ở tầng mock HTTP server để kiểm chứng tích hợp thật.

### 6.1. Kiểm tra status và onErrorResume

~~~java
ExchangeFunction fakeError = request -> Mono.just(
        ClientResponse.create(HttpStatus.NOT_FOUND)
                .header("Content-Type", "application/json")
                .body("{\"code\":\"STOCK_NOT_FOUND\"}")
                .build());

WebClient client = WebClient.builder()
        .exchangeFunction(fakeError)
        .build();

Mono<StockResponse> result = client.get()
        .uri("http://inventory-service/api/stock/{sku}", "MISSING")
        .retrieve()
        .bodyToMono(StockResponse.class);

StepVerifier.create(result)
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
~~~

**retrieve()** mặc định biến 4xx/5xx thành **WebClientResponseException**. Một nhánh **onStatus** hoặc **onErrorResume** có thể chuyển ngoại lệ thành domain result, nhưng cần test riêng để tránh vô tình nuốt lỗi hạ tầng.

## 7. Integration test thật: @LoadBalanced WebClient + hai MockWebServer

Đây là bài kiểm thử quan trọng nhất: gọi **http://inventory-service** ở code nghiệp vụ nhưng xác minh request thực sự đến một trong hai **localhost:port** do discovery cung cấp.

### 7.1. Mục tiêu

Thiết lập:

~~~text
Order Service test
    |
    | WebClient GET http://inventory-service/api/stock/BOOK-01
    v
Spring Cloud LoadBalancer
    |-- inventory-a -> localhost:<portA> -> MockWebServer A
    |
    |-- inventory-b -> localhost:<portB> -> MockWebServer B
~~~

Hai server trả JSON với instanceId riêng. Test kiểm tra:

1. Kết quả là StockResponse giải mã từ HTTP response thật.
2. Mỗi request đi tới một server được discovery khai báo.
3. Có thể quan sát phân phối qua nhiều lần gọi nối tiếp.
4. Path, query và header được bảo toàn sau khi tái dựng URI.
5. Không một request nào cố DNS-lookup tên inventory-service như host vật lý.

### 7.2. Một test Spring Boot đầy đủ

Ví dụ minh họa dùng JUnit Jupiter, Spring Boot Test và MockWebServer 4.x:

~~~java
@SpringBootTest(
        classes = WebClientLoadBalancerIT.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class WebClientLoadBalancerIT {

    static final MockWebServer A = new MockWebServer();
    static final MockWebServer B = new MockWebServer();

    static {
        try {
            A.start();
            B.start();
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void discoveryProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
                () -> A.url("/").toString());
        registry.add(
                "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
                () -> B.url("/").toString());

        // Giữ test tập trung vào lựa chọn instance, không retry ngầm.
        registry.add("spring.cloud.loadbalancer.retry.enabled", () -> "false");
    }

    @Autowired
    @LoadBalanced
    WebClient.Builder loadBalancedBuilder;

    @Test
    void sendsRequestsToBothDiscoveredInstances() throws Exception {
        // Đủ response để không phụ thuộc server nào được chọn đầu tiên.
        for (int i = 0; i < 8; i++) {
            A.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {"sku":"BOOK-01","available":7,"instanceId":"a"}
                            """));
            B.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {"sku":"BOOK-01","available":9,"instanceId":"b"}
                            """));
        }

        WebClient client = loadBalancedBuilder
                .baseUrl("http://inventory-service")
                .build();

        Set<String> observed = new HashSet<>();

        // Gọi tuần tự: tránh giả định thứ tự xử lý khi chạy đồng thời.
        for (int i = 0; i < 6; i++) {
            Mono<StockResponse> call = client.get()
                    .uri("/api/stock/{sku}?warehouse={wh}", "BOOK-01", "HCM")
                    .header("X-Correlation-Id", "test-123")
                    .retrieve()
                    .bodyToMono(StockResponse.class);

            StepVerifier.create(call)
                    .assertNext(stock -> {
                        assertEquals("BOOK-01", stock.sku());
                        assertTrue(Set.of("a", "b").contains(stock.instanceId()));
                        observed.add(stock.instanceId());
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }

        assertEquals(Set.of("a", "b"), observed);
        assertEquals(6, A.getRequestCount() + B.getRequestCount());

        RecordedRequest requestA =
                A.takeRequest(1, TimeUnit.SECONDS);
        RecordedRequest requestB =
                B.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(requestA);
        assertNotNull(requestB);
        assertEquals("/api/stock/BOOK-01?warehouse=HCM", requestA.getPath());
        assertEquals("/api/stock/BOOK-01?warehouse=HCM", requestB.getPath());
        assertEquals("test-123", requestA.getHeader("X-Correlation-Id"));
        assertEquals("test-123", requestB.getHeader("X-Correlation-Id"));
    }

    @AfterAll
    static void stopServers() throws IOException {
        A.shutdown();
        B.shutdown();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
        @Bean
        @LoadBalanced
        WebClient.Builder loadBalancedWebClientBuilder() {
            return WebClient.builder();
        }
    }
}
~~~

Import bổ sung cho lớp test:

~~~java
import java.io.IOException;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
~~~

**Phạm vi xác nhận:** ví dụ thiết kế để chạy cùng một Spring Boot/Spring Cloud BOM tương thích, có cả hai bean auto-configuration LoadBalancer và SimpleDiscoveryClient. Do giới hạn bài Knowledge, ví dụ chưa được build/chạy trong repository; khi dùng thật, phải bổ sung imports, kiểm tra phiên bản dependency và chạy test bằng build của dự án.

### 7.3. Vì sao khởi chạy MockWebServer ở static initializer?

**@DynamicPropertySource** được Spring xử lý trong giai đoạn tạo ApplicationContext, trước khi các @BeforeAll thông thường có thể thiết lập tài nguyên theo thứ tự bạn mong đợi. Khởi chạy server trước khi registry đọc URI bảo đảm getPort()/url() đã sẵn có.

Trong suite phức tạp, nên dùng JUnit extension, Testcontainers hoặc cơ chế quản lý lifecycle tương đương. Cần chắc chắn server được dừng sau test và port động không bị dùng lại sai bởi Spring Test context cache.

### 7.4. Vì sao không assert request đầu chắc chắn tới A?

RoundRobinLoadBalancer có bộ đếm vị trí ban đầu; vị trí đầu có thể không bắt đầu từ A. Trong một application có nhiều test hoặc nhiều lần chọn, thứ tự request còn phụ thuộc trạng thái bộ đếm, concurrency và bộ lọc supplier.

Ví dụ trên chỉ yêu cầu:

- Cả hai instance được quan sát sau nhiều request **nối tiếp**.
- Tổng số request phù hợp số lần subscribe.
- Mỗi server thực nhận path và header đúng.

Muốn assert **A → B → A → B**, hãy dùng một LoadBalancer có seed cố định, supplier trả danh sách cố định, không cache/health cập nhật và không có request concurrent. Chỉ nên kiểm tra thứ tự chính xác khi chính thứ tự đó là contract của bài test.

## 8. Test ranh giới Discovery và ServiceInstanceListSupplier

Trong integration test, **SimpleDiscoveryClient** là nguồn dữ liệu tĩnh; nó có thể cung cấp hai ServiceInstance mà không cần Eureka/Consul thật. Nhưng khi điều tra thuật toán chọn, một unit test riêng cho supplier vẫn hữu ích:

~~~java
ServiceInstance a = new DefaultServiceInstance(
        "inventory-a", "inventory-service", "localhost", 8081, false);
ServiceInstance b = new DefaultServiceInstance(
        "inventory-b", "inventory-service", "localhost", 8082, false);

ServiceInstanceListSupplier supplier = new ServiceInstanceListSupplier() {
    @Override
    public String getServiceId() {
        return "inventory-service";
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return Flux.just(List.of(a, b));
    }
};

StepVerifier.create(supplier.get().next())
        .assertNext(instances -> {
            assertEquals(2, instances.size());
            assertEquals("inventory-a", instances.get(0).getInstanceId());
            assertEquals("inventory-b", instances.get(1).getInstanceId());
        })
        .verifyComplete();
~~~

Các import cần thiết:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
~~~

**Điều test này chứng minh:** supplier trả danh sách cố định và thứ tự đã khai báo. Nó **chưa chứng minh** RoundRobinLoadBalancer đã chọn A/B hay ReactorLoadBalancerExchangeFilterFunction đã tái dựng URI. Muốn kiểm tra thuật toán, hãy đưa supplier đó vào một LoadBalancer thực và verify **choose(Request)**; muốn kiểm tra HTTP, tiếp tục dùng MockWebServer.

### 8.1. Khi nào cần custom supplier trong test?

Test với discovery thật có thể bị ảnh hưởng bởi trạng thái đăng ký, TTL cache hoặc health check. Nếu cần tái lập một trường hợp hiếm như chỉ còn một instance, không còn instance, zone không match hoặc retry tránh instance cũ, có thể tạo **supplier giả** trả danh sách do test kiểm soát.

Chú ý nơi đăng ký supplier: Spring Cloud tạo context riêng theo **service ID**. Một cấu hình tùy chỉnh cho inventory-service nên được đăng ký bằng **@LoadBalancerClient(name = "inventory-service", configuration = ...)**, với lớp cấu hình supplier không bị component scan toàn cục.

Ví dụ cấu hình per-service:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class OrderApplication {
}

class InventoryLoadBalancerConfiguration {
    @Bean
    ServiceInstanceListSupplier supplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Ví dụ trên dùng **blocking DiscoveryClient** nhằm tương thích nguồn SimpleDiscoveryClient; việc chọn instance ở WebClient vẫn theo ReactiveLoadBalancer. Nếu provider có **ReactiveDiscoveryClient**, có thể dùng **withDiscoveryClient()** thay vì withBlockingDiscoveryClient(). Đừng suy diễn một nguồn tĩnh sẽ tự hỗ trợ reactive discovery hoặc tự cập nhật health.

## 9. Kiểm tra tình huống không có instance

Nếu request dùng **http://missing-inventory-service/...** nhưng discovery không trả instance cho service ID đó, LoadBalancer không có URI vật lý hợp lệ để kết nối.

Một kịch bản test phải xác nhận:

1. Không có ServiceInstance nào được trả về cho service ID thử nghiệm.
2. Không có request nào tới MockWebServer A/B.
3. Mono kết thúc bằng lỗi hoặc response lỗi đúng với adapter đang sử dụng.
4. Có log/metric đủ để phân biệt lỗi chọn instance với backend trả 503.

Ví dụ test ở **cấu hình mặc định phổ biến của Spring Cloud LoadBalancer**:

~~~java
Mono<String> call = loadBalancedBuilder.build()
        .get()
        .uri("http://service-that-does-not-exist/api/stock")
        .retrieve()
        .bodyToMono(String.class);

StepVerifier.create(call)
        .expectErrorSatisfies(error -> {
            assertInstanceOf(WebClientResponseException.class, error);
            WebClientResponseException httpError =
                    (WebClientResponseException) error;
            assertEquals(503, httpError.getStatusCode().value());
        })
        .verify(Duration.ofSeconds(5));
~~~

**Giới hạn quan trọng:** trong nhiều phiên bản tích hợp reactive, khi không có instance, LoadBalancer filter tạo **HTTP 503 Service Unavailable** nội bộ và retrieve() chuyển thành WebClientResponseException. Tuy nhiên, hành vi có thể được cấu hình để dùng HTTP 404 hoặc khác đi theo adapter/release train. Không đóng đinh 503 trong mọi sản phẩm: kiểm tra contract đúng của phiên bản và cấu hình đang chạy.

Nếu test trên thất bại vì **UnknownHostException** và cố DNS-resolve service-that-does-not-exist, trước tiên cần kiểm tra **@LoadBalanced builder/filter**. Đó không nhất thiết là lỗi discovery rỗng; có thể WebClient chưa được tích hợp LoadBalancer.

Nếu ứng dụng có filter khác chuyển lỗi, assert **domain exception** ở tầng adapter và test riêng trạng thái HTTP tại tầng integration.

## 10. Tách HTTP 4xx/5xx khỏi lỗi transport

WebClient **retrieve()** mặc định chuyển HTTP status 4xx/5xx thành **WebClientResponseException**. Đây là lỗi **có response HTTP**. Lỗi network/connect/read có thể được bọc trong **WebClientRequestException**, ngoài ra còn có lỗi timeout do operator Reactor tự sinh.

| Kịch bản | Dạng tín hiệu thường gặp | Có response HTTP thật? |
| --- | --- | --- |
| Backend trả 200 JSON | onNext(StockResponse), onComplete | Có |
| Backend trả 204 | Mono bodyToMono có thể complete rỗng | Có |
| Backend trả 404 | WebClientResponseException.NotFound | Có |
| Backend trả 503 | WebClientResponseException.ServiceUnavailable | Có |
| DNS/connection refused/TLS | WebClientRequestException, root cause I/O | Không |
| Operator .timeout(...) quá hạn | TimeoutException từ Reactor | Không nhất thiết |
| Response 200 có JSON không giải mã được | DecodingException hoặc codec exception | Có |
| Không còn ServiceInstance | Lỗi/response từ LB filter | Có thể chưa gọi mạng |

Ví dụ với một **MockWebServer dành riêng cho test 404**, enqueue:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"code\":\"STOCK_NOT_FOUND\"}"));
~~~

Sau đó:

~~~java
StepVerifier.create(inventoryClient.getStock("MISSING"))
        .expectErrorMatches(error ->
                error instanceof WebClientResponseException.NotFound)
        .verify(Duration.ofSeconds(5));
~~~

Điều kiện: test fixture đang dùng supplier **chỉ có instance trỏ đến server đó**, không có filter tùy biến ánh xạ 404 sang exception domain, và không có retry tự động che mất response đầu. Mỗi test phải tạo/khôi phục queue response độc lập.

### 10.1. Khi dùng onStatus() hoặc onErrorResume()

Ứng dụng có thể ánh xạ HTTP 404 thành domain error:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.just(new StockNotFoundException(sku)))
        .bodyToMono(StockResponse.class);

StepVerifier.create(call)
        .expectError(StockNotFoundException.class)
        .verify(Duration.ofSeconds(5));
~~~

StockNotFoundException là exception do ứng dụng định nghĩa. Nếu dùng:

~~~java
Mono<Optional<StockResponse>> result = webClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .map(Optional::of)
        .onErrorResume(WebClientResponseException.NotFound.class,
                ex -> Mono.just(Optional.empty()));
~~~

thì StepVerifier cần **expectNext(Optional.empty())** rồi verifyComplete(), không còn expectError(NotFound). Chỉ áp dụng chuyển 404 thành empty khi contract endpoint thực sự cho phép; không được nuốt lỗi 404 do sai path hoặc gateway.

## 11. Kiểm thử HTTP timeout theo hai cách khác nhau

**HTTP timeout** và **Reactor timeout operator** đều có thể làm Mono lỗi nhưng **không cùng cơ chế**:

1. **response timeout của connector:** ví dụ Reactor Netty cấu hình HttpClient.responseTimeout(); bộ lọc/connector có thể báo WebClientRequestException và cause thuộc Netty/network.
2. **Mono.timeout(Duration):** nếu publisher không phát tín hiệu đúng hạn, Reactor sinh TimeoutException theo operator, bất kể TCP đã kết nối hay chưa.

### 11.1. Test Mono.timeout bằng server chậm

MockWebServer 4.x có thể trì hoãn body:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"sku\":\"BOOK-01\",\"available\":7}")
        .setBodyDelay(2, TimeUnit.SECONDS));
~~~

WebClient dùng supplier chỉ trỏ đến **server**. Test:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .timeout(Duration.ofMillis(250));

StepVerifier.create(call)
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify(Duration.ofSeconds(3));
~~~

Giả định server đã nhận request nhưng chưa phát xong body trong 250 ms. Đây là bài kiểm thử **deadline ở tầng Reactor**, không phải bằng chứng connect timeout của HTTP engine.

Đặt timeout đủ xa khỏi dao động thời gian khởi tạo Spring context và TCP handshake; nếu đặt 1 ms, test có thể rớt trước khi request thật sự đến server, mất giá trị kiểm chứng.

### 11.2. Test response timeout của Reactor Netty

Ví dụ cấu hình connector:

~~~java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofMillis(300));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
~~~

Trong fixture HTTP server chậm tương tự, test nên xác nhận:

- Có request gửi tới server.
- Connector chấm dứt trong ngân sách cấu hình.
- Ngoại lệ thuộc loại request/transport và giữ cause thích hợp.

Không assert cứng một subclass Netty duy nhất giữa các phiên bản Reactor Netty/HTTP engine. Các API test nên phân biệt **có HTTP response** với **lỗi I/O/timeout trước khi response hoàn tất**.

Các import: **reactor.netty.http.client.HttpClient** và **org.springframework.http.client.reactive.ReactorClientHttpConnector**. Trong production nên cấu hình thời gian cho connect, response, pool acquisition và deadline tổng một cách nhất quán.

## 12. Retry reactive: phải kiểm tra số lần gọi thực tế

Spring Cloud LoadBalancer có cơ chế retry theo service instance, còn Reactor cung cấp **retryWhen(Retry...)** để retry Publisher. Hai cơ chế có thể cộng dồn và tạo nhiều request hơn dự kiến.

Với một test chỉ tập trung vào retry ở tầng **Reactor**, tắt retry tự động của Spring Cloud LoadBalancer:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
~~~

Sau đó giả lập một server trả 503, rồi 200 ở lần gọi tiếp theo:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(503)
        .setBody("temporarily unavailable"));

server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody("""
                {"sku":"BOOK-01","available":7,"instanceId":"a"}
                """));
~~~

Client:

~~~java
Mono<StockResponse> result = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .retryWhen(Retry.max(1)
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));

StepVerifier.create(result)
        .assertNext(stock -> assertEquals(7, stock.available()))
        .verifyComplete();

assertEquals(2, server.getRequestCount());
~~~

Điều kiện: supplier của test trỏ tới **một** MockWebServer; test không bật retry ở proxy/server, không có interceptor khác gửi lại request. Nếu có hai instance, **Reactor retry có thể kích hoạt lựa chọn instance lần nữa**, nhưng để assert instance đổi từ A sang B phải cố định seed/chính sách chọn và kiểm soát danh sách ứng viên.

### 12.1. Không thử lại mọi lỗi

Ví dụ điều kiện lọc retry chỉ nhận HTTP 503. Không nên retry:

- HTTP 400/422 do request sai.
- HTTP 401/403 do auth.
- 404 khi resource thật sự không tồn tại.
- JSON decode lỗi do contract không tương thích.

Lỗi 429 có thể retry khi có cơ chế tôn trọng Retry-After. Timeout và 503 có thể retry với request **safe/idempotent** và giới hạn budget; đối với POST tạo tài nguyên hoặc thanh toán, phải có idempotency key được backend thực thi.

### 12.2. Khi retry thuộc Spring Cloud LoadBalancer

Nếu yêu cầu là **kiểm thử chính sách retry chọn instance khác**, không nên chỉ test operator retryWhen. Hãy dùng integration fixture có hai server và chính sách retry LoadBalancer phù hợp:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
~~~

Các thuộc tính có thể thay đổi giữa release train; Spring Cloud LoadBalancer hiện hành có cả cấu hình avoid-previous-instance và backoff. Kiểm tra dependency retry thực tế trên classpath, loại filter được auto-configure và phương thức HTTP được áp dụng. Không suy luận rằng thêm YAML trên sẽ bảo đảm một lần 503 luôn được gửi lại sang B.

Test phải xác nhận trực tiếp **RecordedRequest** ở từng server. Nếu thấy cả A và B nhận request, đồng thời tổng attempts đúng 2, mới có chứng cứ retry đã đổi instance. Nếu chỉ thấy hai response tại cùng A, test chỉ chứng minh có retry, chưa chứng minh **load-balancer retry-to-next-instance**.

## 13. Virtual time cho retry/delay: không giả lập TCP bằng đồng hồ ảo

Reactor **StepVerifier.withVirtualTime** rất hữu ích cho unit test các operator như delayElements(), timeout(), Retry.fixedDelay() hoặc Retry.backoff() khi chúng dùng scheduler do Reactor quản lý.

Ví dụ sau **không dùng mạng**; nó kiểm tra retry với khoảng cách một giây bằng đồng hồ ảo:

~~~java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
                    int n = attempts.incrementAndGet();
                    return n < 3
                            ? Mono.<String>error(
                                    new IllegalStateException("temporary"))
                            : Mono.just("ok");
                })
                .retryWhen(Retry.fixedDelay(
                                2, Duration.ofSeconds(1))
                        .filter(ex ->
                                ex instanceof IllegalStateException)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("ok")
        .verifyComplete();

assertEquals(3, attempts.get());
~~~

**withVirtualTime nhận Supplier để tạo Publisher sau khi scheduler ảo đã được cài đặt.** Nếu tạo Mono có timer từ trước và chỉ truyền một tham chiếu có sẵn, timer có thể gắn scheduler thật khiến test bị treo hoặc chạy chậm.

Giới hạn quan trọng:

- Virtual time chỉ điều khiển các scheduler Reactor tham gia cơ chế thay thế.
- Không làm **MockWebServer**, TCP socket, DNS hoặc Reactor Netty response timeout tự chạy nhanh hơn.
- Với pipeline nhiều scheduler tùy chỉnh hoặc mô hình phát liên tục, test cần kiểm soát kỹ để tránh deadlock.
- Nếu mục tiêu là HTTP transport, dùng mock server thật với timeout thực tế và chấp nhận một ngân sách thời gian test nhỏ nhưng đủ ổn định.

## 14. Cancellation và cleanup trong pipeline reactive

Khi người dùng đóng kết nối inbound, upstream timeout hoặc một subscriber hủy đăng ký, WebClient có thể nhận cancellation. Test cần xác nhận pipeline ngừng chờ và giải phóng tài nguyên theo khả năng connector.

Một unit test cô lập dùng ExchangeFunction giả:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

ExchangeFunction neverResponding = request ->
        Mono.<ClientResponse>never()
                .doOnCancel(() -> cancelled.set(true));

WebClient client = WebClient.builder()
        .exchangeFunction(neverResponding)
        .build();

Mono<String> call = client.get()
        .uri("http://inventory-service/slow")
        .retrieve()
        .bodyToMono(String.class);

StepVerifier.create(call)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

Đây là test **truyền cancellation trong Publisher giả**. Nó không chứng minh socket thật đã đóng ngay, Netty pool đã release hay backend ngừng xử lý công việc. Muốn kiểm tra I/O thực, đặt MockWebServer phản hồi chậm, quan sát client connector, số kết nối và việc giải phóng tài nguyên.

**Không dùng block() để mô phỏng cancellation của HTTP client reactive.** Hãy dùng StepVerifier và các hook doOnCancel/doFinally ở tầng Publisher phù hợp; tránh biến hook test thành logic dùng chung trong production.

## 15. Context propagation và header theo từng request

**Reactor Context** là ngữ cảnh gắn với subscription, khác với ThreadLocal. Với WebClient, có thể dùng Context để mang trace/tenant ID đến một filter và chuyển thành HTTP header nếu contract yêu cầu.

Ví dụ một filter:

~~~java
ExchangeFilterFunction traceFilter = (request, next) ->
        Mono.deferContextual(context -> {
            String traceId =
                    context.getOrDefault("traceId", "unknown");

            ClientRequest withTrace = ClientRequest.from(request)
                    .header("X-Trace-Id", traceId)
                    .build();

            return next.exchange(withTrace);
        });
~~~

Ở nơi gọi:

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class)
        .contextWrite(Context.of("traceId", "trace-123"));
~~~

**Context.of** nằm trong reactor.util.context.Context. Khi dùng MockWebServer, assert header **X-Trace-Id: trace-123** bằng RecordedRequest. Kiểm tra thêm hai subscription độc lập có traceId khác nhau để tránh cross-request leakage.

Lưu ý:

- Reactor Context **không tự động biến thành HTTP header**. Filter hoặc framework observability phải thực hiện propagation.
- Đừng dùng ThreadLocal đơn giản để mang tenant/trace ID qua scheduler reactive; giá trị có thể bị mất khi đổi thread.
- Đừng tự đưa Authorization hoặc token nhạy cảm vào header chỉ vì chúng có trong Context; tuân theo chính sách bảo mật.
- Với load balancing dựa trên header hint/sticky, cần kiểm tra **filter order** và khả năng Spring Cloud chuyển Request context cho các ServiceInstanceListSupplier liên quan.

Nếu ứng dụng đã có Micrometer Tracing, nên ưu tiên cơ chế context propagation chuẩn thay vì tự tạo trace header tùy biến cho production. Đoạn code ở trên nhằm minh họa điểm kiểm thử.

## 16. Kiểm thử song song: assert tính đúng đắn, không cứng vị trí Round Robin

WebClient hỗ trợ nhiều lời gọi đang chờ đồng thời. Một pattern đơn giản:

~~~java
Flux<StockResponse> calls = Flux.range(0, 40)
        .flatMap(index ->
                webClient.get()
                        .uri("http://inventory-service/api/stock/{sku}",
                                "BOOK-01")
                        .retrieve()
                        .bodyToMono(StockResponse.class),
                8);

StepVerifier.create(calls.collectList())
        .assertNext(responses -> {
            assertEquals(40, responses.size());
            assertTrue(responses.stream().allMatch(
                    r -> Set.of("a", "b").contains(r.instanceId())));
        })
        .verifyComplete();
~~~

Để test này chạy, **mỗi MockWebServer cần có đủ response queued** hoặc có dispatcher trả response theo request; nếu queue cạn, test có thể treo hoặc nhận phản hồi không như mong đợi. Đặt deadline test và đảm bảo fixture reset trạng thái giữa các test.

Với **flatMap**, thứ tự phần tử đầu ra **không bảo đảm bằng thứ tự index**. Không nên assert kết quả đúng A, B, A, B khi có nhiều request đồng thời. Thay vào đó:

- Xác nhận tổng số kết quả và request đúng.
- Xác nhận mỗi response đến từ một instance hợp lệ.
- Đảm bảo không mất, trùng hoặc trả sai dữ liệu theo request ID.
- Nếu kiểm tra phân phối, dùng nhiều request và các ngưỡng thống kê hợp lý; không yêu cầu tỷ lệ 50/50 tuyệt đối.

Nếu contract yêu cầu **thứ tự phản hồi giống thứ tự đầu vào**, dùng concatMap hoặc flatMapSequential theo nhu cầu, rồi kiểm tra tác động lên concurrency/latency. Đó là thuộc tính operator Reactor, không phải chức năng do LoadBalancer đảm bảo.

## 17. Kiểm thử streaming bằng bodyToFlux()

Không phải downstream nào cũng trả một JSON object rồi đóng response. Với NDJSON hoặc Server-Sent Events, WebClient có thể trả **Flux<T>** và phát từng phần tử khi dữ liệu đến.

Ví dụ nghiệp vụ:

~~~java
Flux<InventoryEvent> events = webClient.get()
        .uri("http://inventory-service/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(InventoryEvent.class);
~~~

Trong test, thay vì ép toàn bộ thành List, có thể kiểm tra hai phần tử rồi hủy:

~~~java
StepVerifier.create(events)
        .assertNext(event ->
                assertEquals("RESERVED", event.type()))
        .assertNext(event ->
                assertEquals("RELEASED", event.type()))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Phải mô phỏng đúng **Content-Type** và framing của giao thức stream. Với SSE, mock server gửi dạng:

~~~text
data: {"type":"RESERVED"}

data: {"type":"RELEASED"}

~~~

Mỗi event kết thúc bằng một dòng trống; HTTP response có Content-Type **text/event-stream**. Đối với NDJSON, dùng Content-Type phù hợp và một JSON object trên mỗi dòng.

Đây là kiểm thử **decode stream và cancellation**. Nếu cần kiểm tra **backpressure**, nên thiết kế unit test với TestPublisher hoặc nguồn Flux có kiểm soát yêu cầu demand; TCP streaming và HTTP connector có cơ chế buffering nên không thể suy ra hoàn toàn backpressure chỉ từ số phần tử đã nhận.

## 18. Kiểm thử zone, hint, health và retry trong supplier chain

Spring Cloud LoadBalancer có thể dùng **ZonePreferenceServiceInstanceListSupplier**, **HintBasedServiceInstanceListSupplier**, **HealthCheckServiceInstanceListSupplier** hoặc retry-aware decorator. Khi WebClient đã được tích hợp đúng, danh sách cuối cùng quyết định tập instance mà HTTP request có thể đến.

Ví dụ metadata:

| Instance | zone | hint | Health giả lập |
| --- | --- | --- | --- |
| A | zone-a | stable | UP |
| B | zone-b | canary | UP |
| C | zone-a | canary | DOWN |

Một số kịch bản cần kiểm chứng:

| Tình huống | Thiết lập | Assertion cốt lõi |
| --- | --- | --- |
| Local zone | Client zone-a, A/C còn trong danh sách | Chỉ instance cùng zone còn được xem xét nếu có match |
| Không match zone | Caller zone-c | ZonePreference fallback về danh sách delegate |
| Hint canary | Header X-SC-LB-Hint=canary | Đúng tập ứng viên theo metadata hint và thứ tự decorator |
| Health C DOWN | Health supplier loại C | Request không đi C sau khi trạng thái health đã cập nhật |
| Không còn instance cùng zone healthy | Health trước Zone | Zone có thể fallback sang B |
| Retry A lỗi | Retry-aware bật và B là ứng viên | Nếu cấu hình cho phép, thử instance khác |
| Cache chưa hết TTL | Instance bị xóa khỏi registry nhưng cache cũ | Có thể vẫn chọn instance cũ trong một khoảng thời gian |

**Không dùng dữ liệu discovery thay đổi ngẫu nhiên** để assert các kịch bản này. Unit test nên cung cấp snapshot cố định để biết chính xác danh sách đầu vào của từng decorator. Integration test sau đó xác minh liệu chính sách đã tác động đến URI được gửi xuống server không.

Đặc biệt, **HealthCheckServiceInstanceListSupplier** có scheduler và kết quả cập nhật bất đồng bộ. Khi test health, chờ tới lúc danh sách ổn định hoặc có điều kiện đồng bộ rõ ràng, thay vì sleep(100) rồi giả định health đã cập nhật.

## 19. Các lỗi làm test reactive có LoadBalancer trở nên flaky

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Test chỉ tạo Mono rồi kết thúc | Không có subscription | Dùng StepVerifier.verify/verifyComplete |
| WebClient cố phân giải DNS service ID | Không dùng @LoadBalanced builder | Kiểm tra bean, starter và filter |
| Host thật bị xem như service ID | Double load-balancing filter | Chỉ chọn một cách tích hợp LB |
| Test không thấy server nào nhận request | Supplier trống, context cấu hình sai, Mono chưa subscribe | Kiểm tra fixture discovery và tín hiệu StepVerifier |
| Luôn đến instance A | Chỉ có một instance sau filter, cache/zone/hint hoặc test khác đã đổi cấu hình | In danh sách đầu ra và metadata |
| Thứ tự A/B thay đổi giữa các lần chạy | Seed Round Robin, concurrency hoặc context dùng chung | Assert membership/count, không hardcode lượt đầu |
| Timeout xuất hiện trước khi server nhận request | Operator timeout quá ngắn | Tách startup time khỏi request deadline; tăng ngân sách test |
| Test chờ mãi | MockWebServer queue hết response hoặc StepVerifier thiếu verify | Đủ response + thời hạn verify |
| Response 503 bất ngờ | LB không có instance hoặc server thật trả 503 | Kiểm tra request count và trace/lifecycle |
| onErrorResume nuốt cả 5xx | Filter ngoại lệ quá rộng | Chỉ chuyển loại lỗi đúng contract |
| Retry phát sinh nhiều lần không dự kiến | Spring LB retry và Reactor retry cùng bật | Kiểm kê cả hai tầng, đếm RecordedRequest |
| Virtual time không chạy nhanh | Timer dựng trước withVirtualTime hoặc là timeout TCP thật | Tạo publisher lazy và tách test network |
| Test context rò rỉ giữa các case | Cùng MockWebServer queue/counter hoặc Spring context cache | Reset fixture, cô lập property/service ID |
| Server DOWN nhưng vẫn được chọn | SimpleDiscoveryClient tĩnh hoặc cache/health chưa refresh | Test riêng discovery/health; không nhầm lỗi WebClient |
| Không thấy header từ Reactor Context | Chưa viết filter propagation, sai filter order | Assert RecordedRequest và contextWrite |

### 19.1. Bảo đảm test cô lập

Nên có quy tắc:

1. **Không dùng port cố định** như 8081/8082 trong test chạy song song; dùng MockWebServer port động.
2. Mỗi test có response queue rõ ràng, không phụ thuộc thứ tự chạy JUnit.
3. Không dùng chung LoadBalancer Round Robin state giữa các test kỳ vọng lượt đầu cố định.
4. Cô lập cấu hình service ID/metadata khi test zone, hint hoặc retry.
5. Tránh Thread.sleep để chờ scheduler; dùng StepVerifier/await condition/virtual time đúng ngữ cảnh.
6. Giới hạn thời gian verify() và network request.
7. Đếm request tại server thật, không chỉ đọc response body.
8. Khi cần debug, tạm thu log service ID, instance ID, status và trace ID; không log token hoặc raw payload nhạy cảm.

## 20. Quy trình chẩn đoán một bài test đang thất bại

Khi client không trả kết quả kỳ vọng, hãy đi từ ngoài vào trong:

~~~text
1. Publisher có được subscribe chưa?
   |
2. WebClient.Builder có @LoadBalanced/filter phù hợp chưa?
   |
3. URI logic có host đúng service ID không?
   |
4. ServiceInstanceListSupplier trả những instance nào?
   |
5. LoadBalancer chọn instanceId/host/port nào?
   |
6. MockWebServer nào thực sự nhận request?
   |
7. Path, query, headers, method ở server có đúng?
   |
8. Server trả HTTP status/body gì?
   |
9. WebClient phát onNext/onError/onComplete ra sao?
   |
10. Retry/timeout/filter có sửa kết quả hay gửi request lần nữa?
~~~

Ở từng tầng, nên ghi thông tin an toàn:

~~~text
testId=lb-reactive-01
serviceId=inventory-service
instanceId=inventory-b
method=GET
pathTemplate=/api/stock/{sku}
status=200
attempt=1
durationMs=23
~~~

Đây là **mẫu log mong muốn**, không phải tên metric mặc định của Spring Cloud. Nếu muốn quan sát được instanceId, có thể dùng LoadBalancerLifecycle, log phía server hoặc công cụ tracing/observability có hook thích hợp. Không suy đoán instanceId từ response nếu đó không phải dữ liệu đáng tin cậy của test.

## 21. Bộ test tối thiểu trước khi đưa vào CI

| Mã test | Mục tiêu | Công cụ | Pass khi |
| --- | --- | --- | --- |
| WC-01 | JSON -> DTO | Fake ExchangeFunction | Mono phát DTO đúng rồi complete |
| WC-02 | HTTP 404 | Mock exchange/server | onError(NotFound) hoặc domain result theo contract |
| WC-03 | Service ID -> instance thật | @LoadBalanced + 2 MockWebServer | Có request tới các port được discovery khai báo |
| WC-04 | Path, query, header | MockWebServer RecordedRequest | Các thành phần request giữ nguyên |
| WC-05 | Không có instance | Spring Cloud context với supplier rỗng | Lỗi từ LB, không có request gửi đến backend |
| WC-06 | Backend trả 503 | Server một instance | Phân biệt HTTP error với lỗi không có instance |
| WC-07 | Transport timeout | MockWebServer chậm + connector timeout | Phát request/transport error đúng loại |
| WC-08 | Deadline timeout | Mono.timeout | Phát TimeoutException trong ngân sách |
| WC-09 | Retry đúng số lần | 503 rồi 200 | Tổng RecordedRequest đúng attempts |
| WC-10 | Retry chọn instance khác | Hai server + policy chọn xác định | Request của từng lần thử đến đúng instance |
| WC-11 | Cancellation | Fake ExchangeFunction + StepVerifier | Hook cancel được gọi |
| WC-12 | Context propagation | Reactor Context + filter + MockWebServer | Header đúng mỗi subscription |
| WC-13 | Concurrent requests | flatMap có concurrency giới hạn | Không mất/nhân request, response hợp lệ |
| WC-14 | Streaming | SSE/NDJSON mock response | bodyToFlux nhận event và hỗ trợ cancellation |

**Phân tầng trong CI:** chạy unit test nhanh, không mở socket, ở mỗi commit; chạy integration test MockWebServer ở build thường; chạy test discovery provider thực hoặc chaos/network fault trong pipeline chuyên biệt khi hạ tầng cho phép.

Không đánh giá hiệu năng production dựa trên thời gian của unit test fake ExchangeFunction. Nếu cần đo latency/throughput, dùng benchmark và môi trường gần production, tách tác động JVM warm-up, network, connection pool, zone routing và retry.

## 22. Checklist trước khi hoàn thành

- [ ] WebClient đang dùng **@LoadBalanced WebClient.Builder** hoặc filter tích hợp đúng một lần.
- [ ] URI logic có host là service ID và không hardcode port backend.
- [ ] Test Mono/Flux luôn được subscribe bằng StepVerifier hoặc subscriber phù hợp.
- [ ] Test unit dùng fake ExchangeFunction chỉ kiểm tra request/response mapping, không kết luận LB đã chạy.
- [ ] Test tích hợp dùng hai MockWebServer hoặc backend mock khác với port động.
- [ ] Dữ liệu discovery hoặc ServiceInstanceListSupplier được kiểm soát và có thể tái lập.
- [ ] Xác minh request thực nhận qua RecordedRequest: method, path, query, headers.
- [ ] Không assert thứ tự Round Robin đầu tiên nếu không cố định seed/trạng thái.
- [ ] Có test no-instance, HTTP 404/503, transport failure và JSON decode failure.
- [ ] Tách deadline của Reactor khỏi HTTP connector response timeout.
- [ ] Virtual time chỉ dùng cho scheduler Reactor, không dùng để giả lập socket thật.
- [ ] Retry ở Reactor và Spring Cloud LoadBalancer được cấu hình, đếm attempts rõ ràng.
- [ ] Request có side effect chỉ retry khi có hợp đồng idempotency.
- [ ] Có test cancellation, Context propagation và concurrent access khi phù hợp.
- [ ] Mock server queues, timers và Spring context được cô lập giữa các test.
- [ ] Test có timeout; không dựa vào sleep ngẫu nhiên.
- [ ] Log/metric không tiết lộ token, cookie hoặc payload nhạy cảm.

## 23. Kết luận

**Kiểm thử WebClient reactive có cân bằng tải cần xác minh cả Publisher lẫn lựa chọn ServiceInstance và I/O HTTP thực tế.** StepVerifier rất phù hợp để kiểm tra onNext, onError, onComplete và cancellation; ExchangeFunction giả giúp test nhanh phần dựng request và deserialize; nhưng **chỉ integration test với @LoadBalanced WebClient và mock HTTP server thật mới chứng minh được service ID đã được chuyển thành host/port của instance được chọn**.

Với Spring Cloud LoadBalancer, hãy kiểm soát dữ liệu ServiceInstanceListSupplier, tránh filter LoadBalancer bị gắn hai lần, phân biệt lỗi không có instance với lỗi HTTP hoặc transport và đếm số request khi retry. Sử dụng **mock servers, timeout rõ ràng, virtual time đúng mục đích và assertions không phụ thuộc thứ tự xử lý ngẫu nhiên** sẽ giúp test chính xác, nhanh và ít flaky.

## 24. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ReactiveLoadBalancer, RoundRobinLoadBalancer, ServiceInstanceListSupplier, retry, health, hint và WebClient integration.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): cách dùng @LoadBalanced WebClient.Builder và ReactorLoadBalancerExchangeFilterFunction.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): khuyến nghị mock web server như OkHttp MockWebServer/WireMock để kiểm thử client HTTP.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): bodyToMono, bodyToFlux, mặc định ánh xạ HTTP 4xx/5xx và onStatus.
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP server/controller và phân biệt với kiểm thử WebClient outbound.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher, PublisherProbe và virtual time.
- [Reactor Test – StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): expectNext, expectError, thenCancel, verify(Duration) và withVirtualTime.
- [Reactor – retryWhen / Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): nguyên lý retry và thao tác trên Publisher.
- [Spring Cloud Commons source – RoundRobinLoadBalancer.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/RoundRobinLoadBalancer.java): logic chọn instance, seed/counter và trường hợp danh sách rỗng.
- [Spring Cloud Commons source – ReactorLoadBalancerExchangeFilterFunction.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/reactive/ReactorLoadBalancerExchangeFilterFunction.java): filter tích hợp WebClient và chọn instance reactive.
