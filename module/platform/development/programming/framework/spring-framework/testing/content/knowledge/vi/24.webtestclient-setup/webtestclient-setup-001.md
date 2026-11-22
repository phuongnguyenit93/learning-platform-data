# Vai trò WebTestClient và quan hệ với WebClient

`WebTestClient` là công cụ gửi request và kiểm tra response trong Spring testing. Nó cho phép kiểm thử endpoint theo phong cách HTTP mà không nhất thiết phải mở cổng mạng hoặc khởi động server thật. Tùy cách cấu hình, request có thể chạy qua WebFlux infrastructure trong bộ nhớ, qua adapter của Spring MVC hoặc tới một server đang chạy thật.

`WebClient` cũng là HTTP client của Spring và có API request dạng fluent tương tự. Tuy nhiên, hai lớp phục vụ hai mục đích khác nhau: ứng dụng thường dùng `WebClient` để gọi dịch vụ bên ngoài; test dùng `WebTestClient` để gửi request tới endpoint cần kiểm thử và viết assertion trực tiếp trên response.

## 1. WebTestClient là gì?

`WebTestClient` nằm trong package `org.springframework.test.web.reactive.server` của module `spring-test`. API này được giới thiệu từ Spring Framework 5.0 và được thiết kế để kiểm thử ứng dụng WebFlux. Từ Spring Framework 5.3, adapter `MockMvcWebTestClient` còn cho phép dùng cùng phong cách kiểm thử với Spring MVC.

WebTestClient cung cấp ba phần chính:

- Request builder: chọn HTTP method, URI, header, cookie, query parameter và body.
- Exchange: thực thi request thông qua cấu hình test hoặc gửi tới server thật.
- Response assertions: kiểm tra status, header, cookie, body và các thuộc tính của response.

Ví dụ tối giản:

```java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello, World");
```

Request GET được dựng bằng `.get()` và `.uri(...)`. `.exchange()` gửi request qua test server. Sau đó test có thể xác nhận status và body bằng các API `expect...`.

## 2. WebClient là gì?

`WebClient` nằm trong package `org.springframework.web.reactive.function.client` của Spring WebFlux. Đây là HTTP client không đồng bộ, hỗ trợ reactive types như `Mono` và `Flux`. Ứng dụng sử dụng nó để gọi HTTP API khác, ví dụ một service đơn hàng gọi service thanh toán.

Ví dụ một thành phần ứng dụng dùng WebClient:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;

class PaymentClient {

    private final WebClient webClient;

    PaymentClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://payments.example.test")
                .build();
    }

    Mono<PaymentResponse> findPayment(String paymentId) {
        return webClient.get()
                .uri("/payments/{id}", paymentId)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
```

`retrieve()` bắt đầu xử lý response theo luồng của WebClient; `bodyToMono(...)` chuyển body thành một reactive publisher. Đoạn code này là logic chạy trong ứng dụng, không phải assertion của một test endpoint.

## 3. Quan hệ giữa WebTestClient và WebClient

WebTestClient được xây dựng dựa trên WebClient và sử dụng phong cách request builder tương tự. Cách viết request vì thế khá quen thuộc nếu đã dùng WebClient: `.get()`, `.post()`, `.uri(...)`, `.header(...)`, `.cookie(...)`, `.bodyValue(...)` và các thao tác tương tự.

Điểm khác biệt nằm ở cách thực thi và cách xử lý response:

| Nội dung | WebClient | WebTestClient |
|---|---|---|
| Mục đích | Gọi HTTP API từ code ứng dụng | Kiểm thử HTTP endpoint |
| Request API | Fluent request builder | Fluent request builder tương tự |
| Thực thi | Gửi request qua HTTP connector tới server | Có thể chạy trong bộ nhớ hoặc gửi tới server thật |
| Sau khi gửi | Đọc body thành `Mono`/`Flux`, xử lý status và lỗi trong application code | Dùng `expectStatus()`, `expectHeader()`, `expectBody()` để assertion |
| Nơi thường dùng | Service, gateway, adapter tích hợp | JUnit tests cho WebFlux hoặc MVC endpoint |

Ví dụ so sánh luồng response:

```java
// Trong application code: WebClient
Mono<PaymentResponse> payment = webClient.get()
        .uri("/payments/{id}", paymentId)
        .retrieve()
        .bodyToMono(PaymentResponse.class);

// Trong test: WebTestClient
client.get()
        .uri("/payments/{id}", paymentId)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("PAID");
```

WebTestClient không phải lớp con của WebClient và cũng không nên thay thế WebClient trong logic nghiệp vụ. Có thể hiểu WebTestClient là một test client có request API tương tự WebClient, đồng thời bổ sung các assertion dành cho kiểm thử.

## 4. Các chế độ kết nối của WebTestClient

Điểm quan trọng khi thiết lập WebTestClient là chọn đúng nơi request sẽ đi tới. Các factory method xác định test chạy với controller, application context, router function hay server đang hoạt động.

### 4.1. bindToController(...)

Dùng khi muốn kiểm thử một hoặc một vài annotated controller với cấu hình WebFlux tối thiểu:

```java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();
```

Đây là kiểu test standalone. Không cần khởi động toàn bộ application context. Nếu controller có dependency, hãy tạo instance với dependency cần thiết rồi truyền vào. Nếu test phụ thuộc vào controller advice, filter, codec hoặc cấu hình WebFlux tùy chỉnh, cần bổ sung chúng qua cấu hình builder hoặc dùng context-based setup.

### 4.2. bindToApplicationContext(...)

Khi cần sử dụng cấu hình WebFlux và bean đã đăng ký trong application context, bind tester vào context:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
```

`applicationContext` ở đây là context của ứng dụng reactive đã được khởi tạo, thường có cấu hình WebFlux và các controller hoặc handler bean. Cách này phù hợp khi test cần xác nhận cấu hình web thật của ứng dụng, chẳng hạn codec, controller advice, filter hoặc các thành phần được đăng ký trong context.

### 4.3. bindToRouterFunction(...)

Với WebFlux functional endpoints, có thể bind trực tiếp vào `RouterFunction`:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
        GET("/hello"),
        request -> ServerResponse.ok().bodyValue("Hello"));

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/hello")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello");
```

Cách này phù hợp với ứng dụng dùng WebFlux functional routing thay vì `@RestController`.

### 4.4. bindToServer()

Khi server đã chạy và test muốn gửi request HTTP thật, dùng `bindToServer()`:

```java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/health")
        .exchange()
        .expectStatus().isOk();
```

Chế độ này thực hiện network I/O tới server. Nó phù hợp với integration test hoặc test chạy cùng server được khởi động bởi test framework. Khi dùng Spring Boot, có thể để Boot khởi động server trên cổng ngẫu nhiên và inject WebTestClient đã được cấu hình:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiIntegrationTests {

    @Autowired
    private WebTestClient client;

    @Test
    void healthEndpointIsAvailable() {
        client.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Trong ví dụ này, request đi tới server thật đang chạy ở cổng ngẫu nhiên. Test bao phủ nhiều thành phần hơn so với bind trực tiếp vào controller, nhưng chi phí khởi tạo và thời gian chạy thường cao hơn.

## 5. WebTestClient dùng với Spring MVC

WebTestClient ban đầu hướng tới WebFlux. Với ứng dụng Spring MVC, có thể dùng `MockMvcWebTestClient` để cung cấp API kiểm thử tương tự nhưng thực thi qua MockMvc:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

WebTestClient client = MockMvcWebTestClient
        .bindToController(new GreetingMvcController())
        .build();
```

`MockMvcWebTestClient` là adapter ở package `org.springframework.test.web.servlet.client`. Nó cho phép dùng request/response assertion của WebTestClient trên nền MockMvc. Đây là lựa chọn hữu ích khi muốn có API kiểm thử theo phong cách WebTestClient nhưng ứng dụng đang dùng Servlet stack của Spring MVC.

Có thể bind vào `WebApplicationContext` của Spring MVC:

```java
WebTestClient client = MockMvcWebTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

Không nhầm `MockMvcWebTestClient` với `WebTestClient.bindToApplicationContext(...)`: cái đầu dùng adapter MockMvc cho Spring MVC; cái sau dựng pipeline reactive WebFlux từ application context.

## 6. Viết assertion với WebTestClient

### Kiểm tra status và header

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectHeader().exists("X-Request-Id");
```

Có thể kiểm tra status cụ thể như `isCreated()`, `isNotFound()`, `isBadRequest()` hoặc dùng `isEqualTo(...)` với status mong muốn.

### Kiểm tra JSON body

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("42")
        .jsonPath("$.status").isEqualTo("PAID");
```

### Deserialize body thành object

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .value(order -> {
            assertThat(order.getId()).isEqualTo("42");
            assertThat(order.getStatus()).isEqualTo("PAID");
        });
```

### Kiểm tra body rỗng

```java
client.delete()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

Các assertion này chạy sau `.exchange()`. Không dùng `retrieve()` như WebClient trong test flow, vì WebTestClient cần `ResponseSpec` để gọi `expectStatus()`, `expectHeader()` và `expectBody()`.

## 7. Ví dụ kiểm thử controller WebFlux hoàn chỉnh

Controller reactive đơn giản:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<GreetingResponse> greeting(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just(new GreetingResponse("Hello, " + name));
    }
}

record GreetingResponse(String message) {}
```

Test dùng bindToController:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class GreetingWebFluxTests {

    private final WebTestClient client = bindToController(
            new GreetingController()).build();

    @Test
    void returnsGreetingAsJson() {
        client.get()
                .uri(uriBuilder -> uriBuilder.path("/greeting")
                        .queryParam("name", "Ada")
                        .build())
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Ada");
    }
}
```

Test này chạy controller qua WebFlux test infrastructure mà không cần khởi động HTTP server. Nó vẫn kiểm tra request mapping, argument binding, message conversion và response được tạo ra trong pipeline đã cấu hình cho test.

## 8. WebTestClient không phải công cụ thay thế để test WebClient

Vì API request builder giống nhau, đôi khi dễ nhầm rằng WebTestClient có thể kiểm tra trực tiếp code ứng dụng đang dùng WebClient. Hai mục tiêu test thực tế khác nhau:

- **Kiểm thử server endpoint:** gửi request tới controller hoặc server bằng WebTestClient và kiểm tra response mà server trả về.
- **Kiểm thử HTTP client của ứng dụng:** xác nhận một service dùng WebClient gửi đúng request tới dịch vụ ngoài, xử lý status và deserialize response như mong đợi.

Khi kiểm thử code dùng WebClient, thường cấu hình base URL trỏ tới mock HTTP server như MockWebServer hoặc WireMock, hoặc cung cấp `ExchangeFunction` giả để kiểm tra request và trả response mô phỏng. Ví dụ dùng `ExchangeFunction`:

```java
ExchangeFunction exchangeFunction = request -> {
    assertThat(request.url().getPath()).isEqualTo("/payments/p-42");
    ClientResponse response = ClientResponse.create(HttpStatus.OK)
            .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .body("{\"id\":\"p-42\",\"status\":\"PAID\"}")
            .build();
    return Mono.just(response);
};

WebClient webClient = WebClient.builder()
        .exchangeFunction(exchangeFunction)
        .build();
```

Đoạn trên minh họa cách cô lập HTTP client của ứng dụng. Test thực tế có thể dùng mock server để kiểm tra cả request được gửi ra và response được nhận về qua HTTP protocol. Không dùng `WebTestClient.bindToController(...)` để thay thế việc kiểm thử một `WebClient` gọi hệ thống bên ngoài.

## 9. Chọn chế độ phù hợp

| Mục tiêu | Cách khởi tạo | Có server thật? |
|---|---|---|
| Kiểm thử một WebFlux annotated controller | `WebTestClient.bindToController(...)` | Không |
| Kiểm thử cấu hình WebFlux trong context | `WebTestClient.bindToApplicationContext(...)` | Không |
| Kiểm thử WebFlux functional route | `WebTestClient.bindToRouterFunction(...)` | Không |
| Kiểm thử server đang chạy | `WebTestClient.bindToServer()` | Có |
| Kiểm thử Spring MVC bằng API WebTestClient | `MockMvcWebTestClient.bindToController(...)` hoặc `bindToApplicationContext(...)` | Không, chạy qua MockMvc |

Chọn test theo phạm vi cần xác nhận. Standalone binding nhanh và tập trung; application context binding bao phủ cấu hình Spring; server binding kiểm tra thêm HTTP connector, server và cấu hình triển khai thực tế.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `WebTestClient` | Thiếu `spring-test` hoặc Spring Framework quá cũ | Thêm dependency test phù hợp và dùng Spring Framework có API này |
| Không resolve được kiểu WebFlux | Thiếu `spring-webflux` hoặc reactive dependencies cần thiết | Bổ sung dependency WebFlux tương thích với Spring Framework |
| Controller không có dependency | Dùng `bindToController(...)` nhưng không tạo dependency cho controller | Truyền controller instance đã được khởi tạo đầy đủ hoặc dùng application context |
| Filter hoặc codec tùy chỉnh không chạy | Dùng standalone binding mà chưa đăng ký cấu hình cần thiết | Dùng builder customization hoặc bind vào application context |
| Request tới server thất bại do connection refused | Dùng `bindToServer()` khi server chưa chạy hoặc sai base URL | Khởi động server trước và cấu hình đúng địa chỉ, cổng |
| Dùng WebTestClient để kiểm tra outbound WebClient | Nhầm test client với HTTP client của application code | Dùng mock HTTP server hoặc ExchangeFunction để kiểm thử WebClient |
| MVC controller không được xử lý như mong đợi | Dùng WebFlux binding cho ứng dụng Servlet MVC | Dùng `MockMvcWebTestClient` để adapter qua MockMvc |

## 11. Ghi nhớ

`WebClient` là HTTP client dành cho code ứng dụng; `WebTestClient` là công cụ kiểm thử endpoint có request API tương tự và bổ sung response assertions. WebTestClient có thể chạy với WebFlux controller, router function, application context hoặc server thật. Với Spring MVC, dùng `MockMvcWebTestClient` để thực thi qua MockMvc. Khi kiểm thử code outbound đang dùng WebClient, hãy mô phỏng HTTP service mà WebClient gọi bằng mock server hoặc ExchangeFunction. Chọn đúng client theo hướng request cần kiểm thử sẽ giúp test phản ánh đúng ranh giới giữa server endpoint và HTTP integration.

