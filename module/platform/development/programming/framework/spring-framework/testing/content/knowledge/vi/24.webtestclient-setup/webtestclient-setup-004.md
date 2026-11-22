# `bindToApplicationContext` với cấu hình WebFlux

`WebTestClient.bindToApplicationContext(...)` tạo một HTTP test client gắn trực tiếp với Spring `ApplicationContext`. Với ứng dụng WebFlux, cách này cho phép gửi request mô phỏng qua hạ tầng reactive web mà context đã cấu hình: `DispatcherHandler`, handler mapping, controller hoặc functional route, `WebFilter`, exception handler và các bộ chuyển đổi dữ liệu.

Đây là lựa chọn phù hợp khi muốn kiểm thử nhiều thành phần WebFlux cùng phối hợp trong một context nhưng chưa cần khởi động Netty hoặc một HTTP server thật. Khác với việc chỉ bind vào một controller, `bindToApplicationContext` sử dụng cấu hình web được đăng ký trong context, vì vậy bài test có thể kiểm tra cả các thành phần dùng chung của ứng dụng.

## 1. WebTestClient và các cách bind

`WebTestClient` có API gần giống `WebClient`: mô tả method, URI, header, body của request, gọi `exchange()` rồi kiểm tra status, response header và body. Điểm khác biệt là nó bổ sung các assertion dành cho kiểm thử.

Có nhiều cách tạo `WebTestClient`, mỗi cách phù hợp với một phạm vi:

| Cách bind | Phạm vi được dựng | Khi nên dùng |
|---|---|---|
| `bindToController(...)` | Controller được chỉ định và hạ tầng tối thiểu cần thiết | Kiểm tra riêng controller hoặc một nhóm controller nhỏ. |
| `bindToRouterFunction(...)` | Functional endpoint được chỉ định | Kiểm tra một `RouterFunction` và handler tương ứng. |
| `bindToApplicationContext(context)` | WebFlux infrastructure và các bean web được phát hiện trong Spring context | Kiểm tra cấu hình WebFlux tổng thể, filter, advice, codec và nhiều endpoint. |
| `bindToServer()` | Kết nối tới HTTP server đang chạy | Kiểm tra request qua server, connector và HTTP transport thật. |

`bindToApplicationContext` nằm giữa test thành phần và test qua server thật. Nó giữ được cấu hình Spring WebFlux rộng hơn so với bind trực tiếp controller, nhưng vẫn chạy trong môi trường mock ở bộ nhớ.

## 2. Context cần có cấu hình WebFlux

`bindToApplicationContext` nhận một Spring `ApplicationContext` đã được refresh. Context phải cung cấp `WebHandler` và các bean WebFlux cần thiết. Với cấu hình Java thuần, `@EnableWebFlux` đăng ký hạ tầng Spring WebFlux, bao gồm `DispatcherHandler` cùng các thành phần mapping và adapter.

Ví dụ một cấu hình tối giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
class WebFluxTestConfiguration {

    @Bean
    GreetingController greetingController() {
        return new GreetingController();
    }
}
```

Controller trả về kiểu reactive:

```java
import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
class GreetingController {

    @GetMapping("/{name}")
    Mono<Greeting> greet(@PathVariable String name) {
        return Mono.just(new Greeting("Hello, " + name));
    }
}

record Greeting(String message) {
}
```

`@EnableWebFlux` tạo cấu hình WebFlux nền tảng; bean controller được phát hiện và đăng ký trong cùng context. Khi context được refresh, `WebTestClient` có thể dựng mock server handler từ context đó.

## 3. Tạo client bằng `bindToApplicationContext`

Với context Java thuần, có thể tạo context trong test và bind client trực tiếp:

```java
import static org.springframework.test.web.reactive.server.WebTestClient.bindToApplicationContext;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingWebFluxTest {

    @Test
    void returnsGreetingFromTheConfiguredWebFluxContext() {
        try (var context = new AnnotationConfigApplicationContext(
                WebFluxTestConfiguration.class)) {

            WebTestClient client = bindToApplicationContext(context)
                    .configureClient()
                    .baseUrl("http://localhost")
                    .build();

            client.get()
                    .uri("/api/greetings/{name}", "Lan")
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                    .expectBody(Greeting.class)
                    .isEqualTo(new Greeting("Hello, Lan"));
        }
    }
}
```

`bindToApplicationContext(context)` đọc cấu hình web từ context và dựng `HttpHandler` cho mock server. `configureClient()` chuyển sang phần cấu hình client, ví dụ base URL, default header hoặc filter phía client. `build()` hoàn tất `WebTestClient`.

Trong ví dụ, `AnnotationConfigApplicationContext` tự refresh sau khi nhận cấu hình class. Nếu tự tạo context bằng constructor rỗng và đăng ký bean thủ công, cần gọi `refresh()` trước khi bind client. Context đã đóng thì client không còn môi trường web để xử lý request.

Các import thường dùng cho đoạn test trên:

```java
import org.springframework.http.MediaType;
```

## 4. Dùng Spring Boot test context

Trong ứng dụng Spring Boot WebFlux, context thường đã được cấu hình bởi `@SpringBootApplication` và các auto-configuration. Có thể lấy context đó rồi tạo client:

```java
import static org.springframework.test.web.reactive.server.WebTestClient.bindToApplicationContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ApplicationWebFluxContextTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = bindToApplicationContext(applicationContext)
                .configureClient()
                .baseUrl("http://localhost")
                .build();
    }

    @Test
    void returnsApplicationResponse() {
        client.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

`webEnvironment = MOCK` không khởi động embedded HTTP server. Test gửi request qua mock WebFlux handler được dựng từ context. Đây là cách phù hợp để nạp toàn bộ bean, cấu hình, filter và exception handler của ứng dụng trong khi vẫn tránh chi phí mở cổng mạng.

Spring Boot cũng có thể tự cấu hình `WebTestClient` để inject vào test khi dùng `@AutoConfigureWebTestClient` cùng web environment phù hợp. Nếu dùng client được auto-configure, không cần tự gọi `bindToApplicationContext` lần nữa. Khi mục tiêu là hiểu rõ cách bind context hoặc cần tùy chỉnh client riêng, cách tạo thủ công như ví dụ trên cho thấy rõ nguồn cấu hình.

## 5. Các thành phần WebFlux được kiểm tra

Khác với `bindToController`, bind vào application context cho phép request đi qua các thành phần web được context cung cấp. Những thành phần thường có mặt gồm:

- `DispatcherHandler` và các `HandlerMapping` chọn endpoint phù hợp.
- `HandlerAdapter` gọi annotated controller hoặc functional handler.
- `WebFilter` áp dụng cross-cutting logic trước và sau handler.
- `WebExceptionHandler` xử lý exception phát sinh trong WebFlux pipeline.
- `ServerCodecConfigurer` và `HttpMessageReader`/`HttpMessageWriter` xử lý request/response body.
- `WebSessionManager`, `LocaleContextResolver` và các thành phần web infrastructure khác nếu được cấu hình.

Các bean này phải thực sự có trong context. Nếu test chỉ đăng ký một controller nhưng không có cấu hình WebFlux, `WebTestClient` không thể tự suy ra toàn bộ ứng dụng cần chạy như thế nào.

### Kiểm tra `WebFilter`

Ví dụ một filter thêm header vào response:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.WebFilter;

@Configuration
class TraceFilterConfiguration {

    @Bean
    WebFilter traceHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .add("X-Trace-Source", "webflux-filter");
            return chain.filter(exchange);
        };
    }
}
```

Vì filter là bean trong application context, client bind vào context có thể kiểm tra header do filter tạo:

```java
client.get()
        .uri("/api/greetings/Lan")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Trace-Source", "webflux-filter");
```

Filter đặt header trước khi gọi `chain.filter(exchange)`, nhờ đó header có mặt trước khi handler ghi body và response được commit. Nếu cần thay đổi response sau khi downstream hoàn tất, phải tính đến việc response có thể đã được commit và không còn cho phép sửa header.

### Kiểm tra exception handler toàn cục

WebFlux có thể đăng ký `WebExceptionHandler` hoặc dùng `@RestControllerAdvice` với `@ExceptionHandler`. Khi bind application context, test có thể xác nhận exception được chuyển thành response theo cấu hình chung.

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> handleInvalidArgument(IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_ARGUMENT", exception.getMessage()));
    }
}

record ApiError(String code, String message) {
}
```

Nếu một controller ném `IllegalArgumentException`, bài test có thể xác nhận status và body:

```java
client.get()
        .uri("/api/items/invalid")
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody(ApiError.class)
        .value(error -> assertThat(error.code()).isEqualTo("INVALID_ARGUMENT"));
```

`assertThat` trong ví dụ đến từ AssertJ. Kiểm thử này có ý nghĩa khi advice được đăng ký trong application context; nếu chỉ bind trực tiếp controller mà không đưa advice vào cấu hình, kết quả có thể khác.

## 6. Functional endpoints cũng thuộc application context

WebFlux hỗ trợ functional routing bằng `RouterFunction` và `HandlerFunction`. Khi các route được đăng ký thành bean trong context có cấu hình WebFlux, `bindToApplicationContext` có thể kiểm tra chúng cùng với controller và filter khác.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class GreetingRoutes {

    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return route(GET("/functional/greeting"), request ->
                ServerResponse.ok().bodyValue(new Greeting("Hello from route")));
    }
}
```

Test gọi route qua cùng client:

```java
client.get()
        .uri("/functional/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Greeting.class)
        .isEqualTo(new Greeting("Hello from route"));
```

Các endpoint được cấu hình ở nhiều phong cách có thể được kiểm tra trong cùng một WebFlux pipeline.

## 7. Kiểm tra codec và content negotiation

WebFlux dùng codec để đọc request body và ghi response body. Khi bind vào application context, test sử dụng codec được cấu hình trong context thay vì chỉ dựa vào cấu hình mặc định của một controller riêng lẻ.

Ví dụ controller nhận JSON:

```java
@PostMapping("/api/messages")
Mono<MessageView> create(@RequestBody Mono<CreateMessage> request) {
    return request.map(value -> new MessageView(value.text(), "ACCEPTED"));
}

record CreateMessage(String text) {
}

record MessageView(String text, String status) {
}
```

Test xác nhận request JSON được đọc và response JSON được ghi:

```java
client.post()
        .uri("/api/messages")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateMessage("Reactive testing"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(MessageView.class)
        .isEqualTo(new MessageView("Reactive testing", "ACCEPTED"));
```

Nếu ứng dụng đăng ký custom codec, cấu hình `maxInMemorySize`, JSON mapper hoặc reader/writer riêng, bind vào context giúp test dùng đúng cấu hình đó. Đây là một lý do nên dùng application context thay vì chỉ tạo client quanh một handler độc lập khi cần xác nhận cấu hình serialization của toàn ứng dụng.

## 8. Cấu hình client sau khi bind

`configureClient()` cho phép thiết lập các tùy chọn phía client sau khi server side đã được dựng. Một số tùy chọn thường dùng:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .baseUrl("http://localhost")
        .defaultHeader("X-Test-Client", "webflux-context-test")
        .build();
```

Có thể dùng default header để truyền dữ liệu chung cho mọi request, chẳng hạn tenant hoặc correlation id test. Không nên đưa credential nhạy cảm hoặc token dùng chung vào cấu hình test nếu không cần thiết; mỗi test nên kiểm soát rõ danh tính và quyền của request.

Client cũng hỗ trợ filter theo phong cách `WebClient`:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .filter((request, next) -> next.exchange(request))
        .build();
```

Client filter nằm ở phía gửi request của test. Nó khác `WebFilter`, vốn chạy bên trong ứng dụng WebFlux. Khi debug, cần xác định assertion hoặc log đang quan sát tầng client hay tầng server.

## 9. Kiểm thử body reactive và stream

WebTestClient có thể kiểm tra body đơn, danh sách, JSON path hoặc stream. Với response hữu hạn, `expectBody(...)` thường đủ:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ItemView.class)
        .hasSize(2);
```

Với endpoint streaming như Server-Sent Events, có thể lấy `FluxExchangeResult` rồi dùng Reactor Test để xác nhận các phần tử theo thời gian:

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event -> "ready".equals(event.data()))
        .thenCancel()
        .verify();
```

Để kiểm tra stream, cần bảo đảm publisher phát dữ liệu theo cách test có thể quan sát. Với stream vô hạn, `thenCancel()` kết thúc subscription sau các event cần xác nhận. Không nên dùng `expectBody()` cho stream không bao giờ hoàn tất vì test sẽ phải chờ body kết thúc.

## 10. Phân biệt mock WebFlux context với server thật

`bindToApplicationContext` tạo mock server handler trong bộ nhớ. Request không đi qua TCP socket, Netty channel hoặc connector HTTP thật. Vì vậy, test có thể xác nhận pipeline WebFlux nhưng không xác nhận các hành vi thuộc server/network.

| Hành vi | `bindToApplicationContext` | Server thật (`bindToServer` hoặc Boot `RANDOM_PORT`) |
|---|---|---|
| Controller và functional route mapping | Có | Có |
| `WebFilter`, advice và codec trong context | Có | Có |
| Binding, validation, content negotiation | Có | Có |
| Reactive publisher và response body | Có, trong mock exchange | Có, qua transport thật |
| Netty channel, TCP, TLS, HTTP connector | Không | Có |
| Giới hạn request/response của server và network timeout | Không đầy đủ | Có thể kiểm tra |
| Client disconnect và backpressure ở transport | Không mô phỏng đầy đủ | Có thể kiểm tra |

Khi cần kiểm tra server nhúng thật, có thể khởi động ứng dụng với `RANDOM_PORT` rồi kết nối WebTestClient đến server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxServerIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void servesRequestThroughTheRunningServer() {
        webTestClient.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Trong cấu hình này, Spring Boot có thể auto-configure `WebTestClient` để gửi request đến cổng server thực đang chạy. Đây là test tích hợp qua HTTP transport, khác với việc tự gọi `bindToApplicationContext`.

## 11. Các lỗi thường gặp khi dùng `bindToApplicationContext`

### Context chưa được refresh

`WebTestClient` cần context đã hoàn tất khởi tạo bean. Nếu tự tạo context bằng constructor rỗng, hãy đăng ký cấu hình và gọi `refresh()` trước khi bind. Đừng tạo client trước khi web infrastructure được đăng ký.

### Context không phải cấu hình WebFlux

Nếu context không có bean `WebHandler` hoặc không được cấu hình bằng `@EnableWebFlux`/Spring Boot WebFlux auto-configuration, `bindToApplicationContext` không có đủ hạ tầng để xử lý request. Kiểm tra ứng dụng đang chạy WebFlux hay Spring MVC. Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot có thể chọn MVC làm application type theo điều kiện classpath; khi muốn ứng dụng reactive, cần cấu hình dependency và application type phù hợp.

### Nhầm lẫn giữa WebFilter và Servlet Filter

WebFlux dùng `org.springframework.web.server.WebFilter`; Spring MVC/Servlet dùng `jakarta.servlet.Filter`. Một Servlet Filter không tự trở thành `WebFilter` chỉ vì nó là bean. Hãy kiểm tra đúng loại filter cho stack đang chạy.

### Mong đợi bind context sẽ khởi động Netty

`bindToApplicationContext` không khởi động server Netty. Nếu test cần connector, port, TLS hoặc transport, dùng server thật và kết nối bằng HTTP client.

### Chỉ đăng ký controller mà bỏ sót cấu hình chung

Nếu test cần global filter, advice, custom codec hoặc router bean, chúng phải có trong application context. Bind trực tiếp controller không tự đưa các bean còn thiếu vào pipeline.

### Dùng client sau khi context đã đóng

Client được dựng từ context phụ thuộc vào các thành phần trong context đó. Hãy giữ context sống trong toàn bộ test sử dụng client và đóng context sau khi test hoàn tất.

### Test stream không có điều kiện kết thúc

`expectBody()` chờ body hoàn tất. Với publisher vô hạn hoặc SSE, dùng `returnResult()` và Reactor Test để kiểm tra một số event rồi hủy subscription.

## 12. Khi nào chọn từng cách bind?

| Nhu cầu | Lựa chọn |
|---|---|
| Kiểm tra một controller độc lập với ít cấu hình | `bindToController(...)`. |
| Kiểm tra một functional route riêng | `bindToRouterFunction(...)`. |
| Kiểm tra nhiều controller, router, filter, advice và codec cùng phối hợp | `bindToApplicationContext(...)`. |
| Kiểm tra cấu hình WebFlux đầy đủ trong ứng dụng Spring Boot nhưng không mở port | `@SpringBootTest(MOCK)` và bind application context, hoặc auto-configure WebTestClient cho mock environment. |
| Kiểm tra Netty, TCP, TLS, timeout và request qua HTTP thật | `RANDOM_PORT` với WebTestClient đã được cấu hình, hoặc `bindToServer()` đến server đang chạy. |

Khi chọn cách bind, hãy bắt đầu từ phạm vi cần xác nhận. Nếu test chỉ cần kiểm tra logic của một controller, dựng toàn bộ application context có thể làm test nặng và khó khoanh vùng. Nếu test cần xác nhận global `WebFilter`, custom codec hoặc nhiều route phối hợp, bind vào context cung cấp đúng cấu hình cần kiểm tra.

## 13. Checklist cho bài test WebFlux context

- [ ] Application context đã được refresh trước khi bind client.
- [ ] Context có cấu hình WebFlux và bean `WebHandler` phù hợp.
- [ ] Test đang dùng `WebFilter` thay vì nhầm với Servlet `Filter`.
- [ ] Controller, functional route, advice và filter cần kiểm tra đều có trong context.
- [ ] Client được tạo bằng `WebTestClient.bindToApplicationContext(context)`.
- [ ] Assertion kiểm tra status, header và body theo hợp đồng endpoint.
- [ ] Nếu cần custom codec hoặc content negotiation, test dùng context có đúng cấu hình codec.
- [ ] Với stream không kết thúc, test dùng `returnResult()` và kiểm soát subscription.
- [ ] Không xem mock context test là bằng chứng cho Netty, TCP, TLS hoặc connector.
- [ ] Nếu cần HTTP transport thật, có bài test server riêng dùng `RANDOM_PORT` hoặc `bindToServer()`.

`bindToApplicationContext` giúp kiểm thử WebFlux ở phạm vi application context: request đi qua các route, controller, filter, exception handler và codec đã được cấu hình cùng nhau. Nó là lựa chọn hữu ích cho integration test reactive web nhanh và có phạm vi rõ ràng; khi cần xác nhận hành vi của Netty hoặc mạng, hãy bổ sung test kết nối tới server thật.
