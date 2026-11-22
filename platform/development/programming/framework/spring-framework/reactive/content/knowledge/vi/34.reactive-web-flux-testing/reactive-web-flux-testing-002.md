# Phân biệt kiểm thử WebFlux không máy chủ với kết nối HTTP tới máy chủ thật

## 1. Mục tiêu

Trong Spring WebFlux, cùng một đoạn test có thể được chạy với request/response mô phỏng hoặc qua một HTTP server thực:

~~~java
client.get()
    .uri("/api/hello/Lan")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Xin chào Lan");
~~~

Dù các assertion giống hệt nhau, **cách tạo WebTestClient quyết định phạm vi của phép kiểm thử**:

- **Mock-server setup:** không mở HTTP port. WebTestClient truyền request tới WebFlux handler chain bằng mock HTTP exchange.
- **Live-server setup:** WebTestClient kết nối bằng HTTP qua socket đến một server đang chạy, có thể là embedded Reactor Netty của Spring Boot hoặc server bên ngoài.

“Không máy chủ” trong bài này chỉ nghĩa là **không khởi động HTTP server cho test**; không phải serverless cloud. Nó cũng không đồng nghĩa “mock tất cả”: một bài test không mở socket vẫn có thể gọi service, database hoặc WebClient downstream thật.

Mục tiêu thực hành: chọn đúng chế độ cho từng rủi ro, viết test Java 17 với Spring Boot 3.5, hiểu những phần nào được kiểm tra và những phần không được kiểm tra.

## 2. Hai đường thực thi khác nhau

### 2.1. Không có HTTP server

~~~text
JUnit
 |
 v
WebTestClient
 |
 v
MockServerHttpRequest / MockServerHttpResponse
 |
 v
WebHandler chain
 +-- WebFilter (nếu được đăng ký)
 +-- HandlerMapping
 +-- HandlerAdapter
 +-- Message readers/writers
 |
 v
Controller / RouterFunction
 |
 v
Service / Repository (thật hoặc mock tùy test)
 |
 v
Mock response -> assertions
~~~

Các mock classes của `spring-test` mô phỏng giao diện request/response phía WebFlux. WebHandler chain vẫn có thể thực thi routing, binding, validation, codecs và reactive operators. Nhưng không có TCP listener, HTTP parser của server, TLS handshake hay network connection thật.

### 2.2. Có HTTP server

~~~text
JUnit
 |
 v
WebTestClient.bindToServer()
 |
 v
Reactor Netty HTTP client
 |
 +------- TCP localhost:randomPort ---------+
                                            |
                                            v
                                  Embedded Netty HTTP server
                                            |
                                            v
                                      WebFlux filters
                                            |
                                            v
                                  Controller / RouterFunction
                                            |
                                            v
                                  Service / Repository
                                            |
                                            v
                                     HTTP response
                                            |
                                            v
                                    WebTestClient
                                            |
                                            v
                                         Assertions
~~~

Ngay cả khi test và server chạy trong cùng một JVM, HTTP request vẫn qua socket thật. Điều này đủ để kiểm tra embedded connector và HTTP transport ở localhost, nhưng **chưa kiểm tra production ingress, CDN hay TLS production** nếu request không đi qua chúng.

## 3. Các chế độ WebTestClient và Spring Boot

| Cấu hình | Chạy server thật? | Được tạo/nạp | Phù hợp nhất |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(controller)` | Không | Controller do test đưa vào, WebFlux infrastructure cơ bản | Controller-focused test |
| `WebTestClient.bindToRouterFunction(route)` | Không | Functional router được chỉ định | Router predicate và handler |
| `WebTestClient.bindToApplicationContext(context)` | Không | WebHandler chain từ các bean trong context | Tích hợp Spring context nhưng không socket |
| `@WebFluxTest(Controller.class)` | Không | WebFlux test slice với client mock | Test web layer và mock service |
| `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient` | Không | Full Boot ApplicationContext qua mock exchange | Wiring filter, service, codec |
| `@SpringBootTest(RANDOM_PORT)` | Có | Full Boot ApplicationContext + embedded server | HTTP integration qua socket |
| `@SpringBootTest(DEFINED_PORT)` | Có | Server trên port được cấu hình | Test tích hợp có kiểm soát port |
| `WebTestClient.bindToServer().baseUrl(url)` | Kết nối server đang chạy | Client HTTP thật | End-to-end tới URL |

Phân biệt hai trục riêng: **phạm vi bean** (chỉ controller, slice hay full context) và **phương tiện vận chuyển HTTP** (mock exchange hay network socket). Một test full-context vẫn có thể hoàn toàn không sử dụng network.

## 4. bindToController: mock WebFlux request không cần Boot context

~~~java
GreetingController controller =
    new GreetingController(new GreetingService());

WebTestClient client = WebTestClient
    .bindToController(controller)
    .build();
~~~

Spring dựng một WebHandler chain và đăng ký controller được truyền vào. Đây không phải lời gọi Java method trực tiếp: các thành phần routing, URI variables, request body decoding và response encoding vẫn tham gia.

### Có thể kiểm thử

- `@GetMapping`, `@PostMapping`, `@RequestParam`, `@PathVariable`.
- JSON body và HTTP status.
- Controller trả Mono hoặc Flux.
- Validation/advice khi đã được cấu hình.
- Handler có gọi đúng dependency giả lập không.

### Không tự động có

- Tất cả `@Service` hoặc `@Repository` bean từ component scan.
- Custom `WebFilter` do Spring Boot tự tìm.
- Full configuration properties.
- Spring Security chain hoặc exception handling ngoài test setup.
- Embedded Reactor Netty server, TCP, TLS, port, HTTP/2.

Muốn thêm một filter hoặc advice:

~~~java
WebTestClient client = WebTestClient
    .bindToController(controller)
    .controllerAdvice(new AppExceptionHandler())
    .webFilter(new AuditWebFilter())
    .build();
~~~

Hai class `AppExceptionHandler` và `AuditWebFilter` là lớp minh họa do ứng dụng tự định nghĩa; nếu test không cung cấp chúng, chúng không tự xuất hiện. Không dùng controller-only test để kết luận auto-configuration production hoạt động.

## 5. bindToRouterFunction: dành cho functional endpoints

Với functional routing:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route(
    RequestPredicates.GET("/ping"),
    request -> ServerResponse.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("pong")
);

WebTestClient client = WebTestClient
    .bindToRouterFunction(route)
    .build();

client.get()
    .uri("/ping")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("pong");
~~~

`bindToRouterFunction` dùng mock request/response để kiểm tra functional route và handler. Nó không tự chứng minh rằng bean route được Spring Boot auto-discover trong full context. Nếu cần đánh giá toàn bộ routing bean registration, hãy dùng bindToApplicationContext hoặc SpringBootTest.

## 6. bindToApplicationContext: sử dụng Spring beans thật nhưng không mở port

~~~java
@Autowired
ApplicationContext context;

WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

Spring dùng `WebHttpHandlerBuilder` tạo WebHandler chain từ context: những controllers, RouterFunction, WebFilter, WebExceptionHandler, codecs và configuration hiện diện trong context có thể được kiểm tra.

**Điểm cần nhớ:** bindToApplicationContext không thay đổi tập bean đã nạp. Nếu context là WebFlux slice, bạn chỉ kiểm tra slice; nếu context là SpringBootTest(MOCK), bạn kiểm tra cấu hình tương ứng của full application. Cả hai vẫn không có server socket.

Khác biệt theo cấu hình:

~~~text
@WebFluxTest -> context hạn chế -> bindToApplicationContext -> mock exchange
@SpringBootTest(MOCK) -> context đầy đủ -> bindToApplicationContext -> mock exchange
@SpringBootTest(RANDOM_PORT) -> context đầy đủ + live server
                          -> bindToServer -> TCP socket
~~~

Đừng suy ra “có ApplicationContext” thì chắc chắn “có HTTP server”. Đó là hai đặc tính riêng.

## 7. @WebFluxTest: controller slice và mock dependency

Spring Boot 3.5 cung cấp `@WebFluxTest`, tự cấu hình WebFlux test infrastructure và WebTestClient, đồng thời hạn chế bean scan. Các bean như `@Controller`, `@ControllerAdvice`, `@JsonComponent`, converters, `WebFluxConfigurer` thường nằm trong slice; `@Service`/`@Repository` thông thường không được nạp tự động.

~~~java
@WebFluxTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void greetingUsesService() {
        when(service.greet("Lan"))
            .thenReturn(Mono.just("Xin chào Lan"));

        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }
}
~~~

Đây là snippet minh họa; bộ mã đầy đủ có import ở mục 13. `@MockitoBean` thuộc Spring Framework 6.2 và được dùng với Spring Boot 3.5; nó thay thế cách dùng `@MockBean` đã deprecated.

Ưu điểm:

- Test web layer nhanh và cô lập hơn full context.
- Dễ mô phỏng service trả giá trị, empty hoặc error.
- Không cần mở port hay kết nối database.
- Kiểm tra status, binding và JSON serialization.

Giới hạn:

- Service thật không được kiểm thử khi đã mock.
- Custom `SecurityWebFilterChain` đăng ký như bean không nhất thiết được phát hiện trong slice; cần import cấu hình security khi cần.
- Custom filters/config nằm ngoài slice có thể không xuất hiện.
- Không kiểm tra Netty HTTP server.

Dùng `@WebFluxTest` cho nhiều trường hợp mapping/validation, nhưng bổ sung integration test cho bean wiring, security và các đường request quan trọng.

## 8. @SpringBootTest: MOCK là mặc định

~~~java
@SpringBootTest
class ApplicationTest {
}
~~~

Nếu không đặt `webEnvironment`, Boot mặc định dùng `SpringBootTest.WebEnvironment.MOCK` và **không** khởi động embedded HTTP server.

| WebEnvironment | Embedded server? | Mục đích |
| --- | --- | --- |
| `MOCK` | Không | Full context + mock web environment |
| `RANDOM_PORT` | Có | Live HTTP server trên port ngẫu nhiên |
| `DEFINED_PORT` | Có | Live server trên port trong config hoặc 8080 |
| `NONE` | Không | ApplicationContext thường, không web environment |

Dùng WebTestClient với MOCK:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ApplicationMockTest {

    @Autowired
    WebTestClient client;

    @Test
    void fullContextWorksWithoutHttpSocket() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`@AutoConfigureWebTestClient` cài đặt client mock cho test khi ứng dụng dùng WebFlux. Boot có thể nạp service và repository thật trong mode này, dù không mở port.

Vì vậy **MOCK server không đồng nghĩa mock database**. Nếu repository thật kết nối DB hoặc service gọi WebClient downstream thật, test vẫn có thể phụ thuộc tài nguyên ngoài. Test isolation phải được thiết kế ở tầng dependency.

## 9. RANDOM_PORT: embedded HTTP server thật

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveServerTest {

    @LocalServerPort
    int port;

    @Test
    void makesRealNetworkRequest() {
        WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();

        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Boot sẽ start embedded web server, chọn port còn trống và inject vào `@LocalServerPort`. Nếu chỉ sử dụng Spring WebFlux starter, server mặc định là Reactor Netty.

`WebTestClient.bindToServer()` là một HTTP client thật. Nó gửi request tới server được đặt tại baseUrl. Nếu không có server lắng nghe, kết nối sẽ lỗi.

### RANDOM_PORT so với DEFINED_PORT

- RANDOM_PORT thích hợp CI: tránh trùng cổng và giảm xung đột với ứng dụng khác.
- DEFINED_PORT phù hợp một số integration environment được kiểm soát nhưng dễ trùng port nếu nhiều test chạy song song.
- Đừng hard-code `localhost:8080` cho RANDOM_PORT.
- Dùng `@LocalServerPort` hoặc WebTestClient do Boot cấu hình phù hợp.

Nếu test muốn kết nối staging hay một server bên ngoài, không cần `@SpringBootTest(RANDOM_PORT)`; có thể `bindToServer().baseUrl("https://test.example.com")` nhưng phải quản lý credentials, dữ liệu và độ ổn định của môi trường. Không chạy test có side-effect vô tình trên production.

## 10. Độ bao phủ: cái gì được kiểm tra, cái gì không?

| Thuộc tính | Bind to controller | Full-context mock | Live server |
| --- | --- | --- | --- |
| WebFlux route matching | Có | Có | Có |
| Request body decoding | Có | Có | Có |
| Response JSON encoding | Có | Có | Có |
| Filter trong handler chain | Khi đăng ký | Khi có trong context | Khi có trong context |
| Spring service/repository | Theo object cung cấp | Theo context | Theo context |
| Application startup/wiring | Không đầy đủ | Có | Có |
| Netty HTTP connector | Không | Không | Có |
| TCP socket/port | Không | Không | Có |
| TLS/HTTP2 thật | Không | Không | Nếu cấu hình tương ứng |
| Header/parser limits của server | Không | Không | Có |
| Proxy/ingress bên ngoài | Không | Không | Chỉ khi request đi qua |
| Backpressure trong Publisher | Có thể kiểm | Có thể kiểm | Có thể kiểm thêm transport |
| Speed/isolation | Thường tốt nhất | Phụ thuộc context | Thường tốn thêm chi phí |

Cùng nhận HTTP 200 trong ba mode **không** có nghĩa đã kiểm chứng cùng những thành phần. Mock controller test hữu ích để xác nhận API contract ở tầng web; live-server test kiểm tra thêm đường giao tiếp qua network, nhưng không tự kiểm tra mọi hệ thống bên ngoài.

## 11. Lựa chọn mức test theo nhu cầu

- **Controller behavior:** bindToController hoặc @WebFluxTest.
- **Functional route:** bindToRouterFunction.
- **Custom WebFilter/exception handler/config trong ApplicationContext:** bindToApplicationContext hoặc @SpringBootTest(MOCK).
- **Spring Boot dependency injection thật:** full-context mock test.
- **Ứng dụng có khởi động embedded server?** @SpringBootTest(RANDOM_PORT).
- **Kết nối HTTP, compression, keep-alive, timeout socket, HTTP parser limits:** live server.
- **Kết nối qua proxy/ingress/TLS thật:** gửi test qua chính hạ tầng đó, không chỉ localhost.
- **Reactive service operator:** StepVerifier thường nhẹ hơn HTTP test.
- **Repository/R2DBC:** integration test với DB tương ứng; không bắt buộc test mọi query qua HTTP.

Chiến lược thường hợp lý: nhiều test nhẹ cho mapping/validation, một số full-context tests cho wiring/filter/security, và một tập nhỏ live-server tests cho critical paths/streaming/transport.

## 12. Những khác biệt dễ bỏ sót

### WebFilter

Một `@Component WebFilter` có trong Spring context sẽ được thực thi ở full-context mock và live server. Nhưng bindToController không tự scan nó. Test không đăng ký filter có thể pass dù production filter sửa path hoặc chặn request.

### Spring Security

Một `@WebFluxTest` không tự phát hiện mọi custom `SecurityWebFilterChain` do ứng dụng đăng ký bằng @Bean. Cần import cấu hình phù hợp hoặc dùng full-context test.

Mock authentication (ví dụ `mutateWith(mockUser())`) có thể giúp test security trong mock reactive exchange. Nhưng thông tin đó **không phải HTTP credentials trên dây**. Live test phải gửi Basic/Bearer headers, cookies hoặc token phù hợp để thật sự đi qua authentication protocol.

### Database và transaction

Live-server test có HTTP client và server trong hai execution contexts. Đặt `@Transactional` trên JUnit test method **không đảm bảo** transaction khởi tạo bên server được rollback cùng test; điều tương tự cần thận trọng với Reactor Context của R2DBC.

Dữ liệu test nên tách biệt theo test ID, database riêng hoặc reset fixtures có kiểm soát. Mock-server test cũng không tự động rollback mọi side effect của repository.

### Streaming và cancellation

Mock exchange có thể kiểm tra Flux, NDJSON và SSE semantics. Nhưng vấn đề flush qua network, client disconnect và connection close yêu cầu live transport test. Ngay cả live localhost không chứng minh proxy/CDN production flush đúng.

### Spring MVC không phải WebFlux mock setup

`WebTestClient` có thể dùng để test MVC qua `MockMvcWebTestClient`, nhưng đó là MVC setup khác. Với ứng dụng chứa cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn MVC làm web type mặc định; hãy xác định rõ hệ thống đang test.

## 13. Dự án Spring Boot 3.5 / Java 17 chạy được

Dự án minh họa bốn kiểu test cùng một REST API:

- `bindToController` không nạp Spring context.
- `@WebFluxTest` nạp web slice, mock service.
- `@SpringBootTest(MOCK)` nạp full context, không khởi động HTTP server.
- `@SpringBootTest(RANDOM_PORT)` start Netty thật, kết nối qua `bindToServer`.
- Test bổ sung `bindToRouterFunction`.
- Một filter `@Component` thêm header, giúp nhìn thấy sự khác biệt giữa standalone và full context.
- Một endpoint NDJSON để kiểm tra streaming bằng StepVerifier qua HTTP thật.

### 13.1. Cấu trúc

~~~text
webflux-test-modes/
├── pom.xml
└── src/
    ├── main/java/com/example/testmodes/
    │   ├── ModesApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   └── TraceHeaderFilter.java
    └── test/java/com/example/testmodes/
        ├── StandaloneControllerTest.java
        ├── WebFluxSliceTest.java
        ├── FullMockContextTest.java
        ├── RealServerTest.java
        └── FunctionalRouterTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-test-modes</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. ModesApplication.java

~~~java
package com.example.testmodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ModesApplication.class, args);
    }
}
~~~

### 13.4. GreetingService.java

~~~java
package com.example.testmodes;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<String> greet(String name) {
        return Mono.just("Xin chào " + name);
    }
}
~~~

### 13.5. GreetingController.java

~~~java
package com.example.testmodes;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    public record Greeting(String message) {}
    public record EchoRequest(String text) {}
    public record EchoResponse(String text) {}
    public record Notice(int id, String label) {}

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        return service.greet(name).map(Greeting::new);
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<EchoResponse> echo(
            @RequestBody Mono<EchoRequest> request) {
        return request.map(value -> new EchoResponse(value.text()));
    }

    @GetMapping(
        path = "/notices",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<Notice> notices() {
        return Flux.just(
            new Notice(1, "ready"),
            new Notice(2, "done")
        );
    }
}
~~~

Các Java record ở đây là nested public record types, Jackson hỗ trợ serialization và deserialization. Stream trả Flux hữu hạn hai bản ghi, nên live test có thể dùng verifyComplete.

### 13.6. TraceHeaderFilter.java

~~~java
package com.example.testmodes;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class TraceHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
            .add("X-App-Filter", "active");

        return chain.filter(exchange);
    }
}
~~~

Filter có mặt trong full application context. Standalone bindToController không tự load filter, nhờ đó ta có thể kiểm tra header vắng mặt so với xuất hiện ở hai full-context modes.

### 13.7. StandaloneControllerTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class StandaloneControllerTest {

    private final WebTestClient client = WebTestClient
        .bindToController(
            new GreetingController(new GreetingService())
        )
        .build();

    @Test
    void controllerWorksWithoutServer() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("X-App-Filter")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void jsonBodyCanBeDecodedWithoutNetwork() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new GreetingController.EchoRequest("hello"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }
}
~~~

Test có WebFlux route matching, HTTP body codecs và JSON assertions; nhưng không có server socket hoặc App WebFilter.

### 13.8. WebFluxSliceTest.java

~~~java
package com.example.testmodes;

import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@WebFluxTest(GreetingController.class)
class WebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void controllerUsesMockService() {
        when(service.greet("Mai"))
            .thenReturn(Mono.just("Xin chào Mai"));

        client.get()
            .uri("/api/hello/Mai")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Mai");
    }
}
~~~

Spring Boot tạo WebFlux slice và WebTestClient, nhưng chưa chạy GreetingService thật vì nó được thay bằng Mockito mock.

### 13.9. FullMockContextTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FullMockContextTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @Test
    void fullContextFilterWorksWithoutHttpServer() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void explicitBindToContextAlsoUsesMockExchange() {
        WebTestClient localClient = WebTestClient
            .bindToApplicationContext(context)
            .build();

        localClient.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }
}
~~~

Ở đây Spring context chứa controller, service và filter thật. Tuy nhiên cả hai test vẫn đi bằng mock exchange, không có inbound TCP connection.

### 13.10. RealServerTest.java

~~~java
package com.example.testmodes;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealServerTest {

    @LocalServerPort
    int port;

    private WebTestClient liveClient() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void httpGoesThroughRealLocalServerSocket() {
        assertTrue(port > 0);

        liveClient().get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void clientReadsRealHttpNdjsonStream() {
        FluxExchangeResult<GreetingController.Notice> result =
            liveClient().get()
                .uri("/api/notices")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
                .returnResult(GreetingController.Notice.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new GreetingController.Notice(1, "ready"),
                new GreetingController.Notice(2, "done")
            )
            .verifyComplete();
    }
}
~~~

`bindToServer` kết nối qua HTTP đến port do Spring Boot thực sự lắng nghe. Test stream dùng `FluxExchangeResult` và `StepVerifier` theo cách Spring Framework hướng dẫn cho streaming responses.

### 13.11. FunctionalRouterTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

class FunctionalRouterTest {

    @Test
    void routerFunctionRunsWithoutLiveServer() {
        RouterFunction<ServerResponse> routes =
            RouterFunctions.route(
                RequestPredicates.GET("/ping"),
                request -> ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("pong")
            );

        WebTestClient client = WebTestClient
            .bindToRouterFunction(routes)
            .build();

        client.get()
            .uri("/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

### 13.12. Lệnh chạy và kết quả dự kiến

Yêu cầu Java 17+ và Maven. Trong thư mục `webflux-test-modes`:

~~~bash
mvn test
~~~

Có tổng cộng **8 phương thức @Test** trong năm test classes: hai standalone, một slice, hai full-context mock, hai live-server và một functional router. Nếu tất cả pass, Maven trả exit code 0 và hiển thị `BUILD SUCCESS`. Không khẳng định thời gian chạy hoặc dòng stdout cụ thể vì chúng phụ thuộc môi trường.

Khởi động ứng dụng ngoài test:

~~~bash
mvn spring-boot:run
~~~

Thử bằng curl:

~~~bash
curl -i http://localhost:8080/api/hello/Lan
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -d "{\"text\":\"hello\"}"
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/notices
~~~

GET hello dự kiến HTTP 200 với body:

~~~json
{"message":"Xin chào Lan"}
~~~

Full server response có header:

~~~http
X-App-Filter: active
~~~

POST echo dự kiến:

~~~json
{"text":"hello"}
~~~

NDJSON body gồm hai dòng:

~~~text
{"id":1,"label":"ready"}
{"id":2,"label":"done"}
~~~

Hai dòng có thể flush hoặc được nhận theo các chunk khác nhau; không coi mỗi dòng NDJSON tương ứng đúng một TCP packet. Test thực thi với localhost, không cần external HTTP service.

## 14. Cách viết assertions dùng chung cho cả mock và live

API WebTestClient gần như giống nhau bất kể binding mode:

~~~java
client.post()
    .uri("/api/echo")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new GreetingController.EchoRequest("sample"))
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("sample");
~~~

Các nhóm assertion:

| Nhóm | API ví dụ | Kiểm tra |
| --- | --- | --- |
| Status | `expectStatus().isOk()` | HTTP 200 |
| Status | `expectStatus().isNotFound()` | HTTP 404 |
| Header | `expectHeader().valueEquals("X-App-Filter","active")` | Header cụ thể |
| Media type | `contentTypeCompatibleWith(APPLICATION_JSON)` | Content-Type tương thích |
| JSON | `expectBody().jsonPath("$.text").isEqualTo(...)` | Trường trong body |
| DTO | `expectBody(MyDto.class)` | Deserialize rồi assert object |
| Empty body | `expectBody().isEmpty()` | Không có body |
| Stream | `returnResult(MyEvent.class)` | Nhận FluxExchangeResult |

Với một stream có thể vô hạn, dùng:

~~~java
FluxExchangeResult<Event> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(Event.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

Đây là snippet minh họa dùng kiểu `Event` của một ứng dụng khác, không thuộc project ở mục 13. `thenCancel` dùng khi không mong stream hoàn tất. Hãy thực sự consume/cancel response body sau `returnResult` để tránh giữ subscription và resources lâu ngoài ý muốn.

## 15. Security: mock principal không giống HTTP credentials thật

Trong mock WebFlux test có Spring Security test support, có thể sử dụng `mutateWith(mockUser(...))` để đặt authentication vào mock reactive exchange. Đây là cách hiệu quả để kiểm tra authorization nhiều role mà không cần phát hành JWT thật.

Nhưng trong live-server test, `bindToServer()` mở HTTP socket. Server chỉ thấy những credentials được gửi theo giao thức: `Authorization` header, cookies, token hoặc mTLS certificate. Một mock authentication trong JVM của test không tự động “đi qua dây”.

Ví dụ request shape với HTTP Basic:

~~~java
liveClient().get()
    .uri("/admin")
    .headers(headers ->
        headers.setBasicAuth("test-admin", "test-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Đây chỉ là snippet minh họa với user test giả định và **không** thuộc project mục 13. Khi xây project có Spring Security, tạo test users hoặc token fixtures thích hợp.

Bài test @WebFluxTest cũng không tự kiểm tra custom `SecurityWebFilterChain` chỉ vì production có cấu hình đó; hãy `@Import` đúng config hoặc dùng full-context test.

## 16. Transaction, database và nguồn dữ liệu ngoài

Mock HTTP transport không đồng nghĩa mock database:

- `bindToController` có thể được dựng với một service/repository thật.
- `@WebFluxTest` thường thay service bằng mock nên chưa chạy DB.
- `@SpringBootTest(MOCK)` có thể chạy R2DBC/JDBC/database thật nếu context cấu hình như vậy.
- `@SpringBootTest(RANDOM_PORT)` có thể dùng H2, Testcontainers hoặc DB thật; lựa chọn DB không được quyết định bởi port mode.

Với live-server tests, request chạy phía server riêng khỏi JUnit test method. `@Transactional` trên test method **không đảm bảo** thao tác ghi được tạo ở server sẽ tự rollback theo transaction của test. Đối với reactive data access, Reactor Context và transaction manager cũng phải được hiểu theo phạm vi subscription.

Chiến lược isolation:

1. Dữ liệu test có ID riêng, không phụ thuộc thứ tự.
2. Clean up bằng test fixture hoặc schema/database riêng.
3. Dùng Testcontainers khi cần kiểm tra behavior của database engine thật.
4. Không truy cập production data chỉ để chạy một controller test.
5. Không để test endpoint ghi dữ liệu vượt ngoài phạm vi test.

## 17. Những lỗi phổ biến

1. **Nghĩ WebTestClient luôn gửi HTTP thật:** bindToController, bindToRouterFunction và bindToApplicationContext đều dùng mock exchange.
2. **Nghĩ @SpringBootTest mặc định mở port:** thực tế WebEnvironment.MOCK.
3. **Nghĩ @WebFluxTest nạp mọi @Service:** web slice loại phần lớn service/repository.
4. **Dùng bindToServer khi chưa có server lắng nghe:** sẽ lỗi kết nối.
5. **Hard-code port 8080 với RANDOM_PORT:** cần @LocalServerPort.
6. **Dùng DEFINED_PORT trong CI chạy song song:** dễ xung đột.
7. **Nghĩ mock server nghĩa mock downstream:** dependency thật vẫn có thể được gọi.
8. **Bind controller nhưng mong custom WebFilter tự chạy:** phải đăng ký hoặc dùng full context.
9. **Quên import custom security trong slice:** test không đại diện authorization production.
10. **Dùng mockUser rồi nghĩ credentials được gửi qua HTTP socket:** không phải; phải gửi auth qua HTTP.
11. **Không test body JSON hoặc status lỗi:** thiếu coverage API contract.
12. **Không consume streaming response:** giữ subscription và bỏ sót event/error.
13. **Không tách test data:** flakiness khi nhiều test tương tác DB.
14. **Dùng @Transactional tại JUnit và tin server-side write rollback:** không đúng cho live-server request.
15. **Test localhost nhưng tuyên bố đã test proxy:** request không đi qua proxy thì không thể xác nhận.
16. **Chỉ dựa vào mock test để xác nhận TLS/HTTP2/Netty:** cần live transport.
17. **Chỉ dùng live test để kiểm tra mapping đơn giản:** chậm hơn không cần thiết và khó cô lập lỗi.
18. **Đặt @SpringBootTest và @WebFluxTest cùng một test class:** test slices không được kết hợp theo cách đó.
19. **Không phân biệt MVC và WebFlux:** MockMvcWebTestClient dành cho MVC setup, WebTestClient WebFlux mock setup là một đường riêng.
20. **Gọi external service thật vô tình:** làm CI flaky, tăng rủi ro side effects.
21. **Không đặt response timeout cho test stream dài:** test có thể treo khi server không phản hồi như mong đợi.
22. **Kiểm tra mỗi HTTP 200:** bỏ sót headers, content type và mapping của error.
23. **Tin rằng live server localhost kiểm tra production certificate:** không nếu cấu hình TLS/endpoint khác.
24. **Không đọc nguyên nhân lỗi:** phân biệt context startup failure, connection refused, status mismatch, timeout và JSON assertion failure.

## 18. Hướng gỡ lỗi theo triệu chứng

| Triệu chứng | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| NoSuchBeanDefinition khi @WebFluxTest | Service bị loại khỏi slice | @MockitoBean hoặc @Import đúng bean |
| bindToServer báo connection refused | Không có server/cổng sai | RANDOM_PORT, @LocalServerPort, địa chỉ |
| Test mock pass, live fail | Lỗi connector, HTTP parser hoặc config runtime | Log Netty, port, headers, codecs |
| Header filter không xuất hiện ở standalone | Filter không được đăng ký | .webFilter(...) hoặc full-context |
| Filter có ở full mock nhưng thiếu ở live | Config/đường request khác nhau | Kiểm tra app type, proxy, filter order |
| 401 trong slice nhưng mong 200 | Security test configuration | Mock user/test credentials và chain |
| 403 chỉ ở slash variant | Path normalization/security mismatch | Test cả /path và /path/, filter order |
| Real test không rollback dữ liệu | Transaction test không bao server | Cleanup per test / database isolation |
| NDJSON test không hoàn tất | Stream vô hạn hoặc không consume | returnResult + StepVerifier + thenCancel |
| Live request chậm | Server startup, I/O, network, DB | Profiles, dependencies, timeout hợp lý |
| Test chạy MVC thay vì WebFlux | Có cả web và webflux starters | Xác định spring.main.web-application-type |

Khi chẩn đoán, hãy xác định chính xác mode đang dùng **trước** khi sửa timeout hoặc tăng số thread. Một test không có socket không thể có lỗi TCP connect tới inbound server; còn test real server có thể gặp những vấn đề ngoài phạm vi mock chain.

## 19. Checklist lựa chọn chế độ

- [ ] Mục tiêu là controller logic, bean wiring hay network transport?
- [ ] Đã chọn mock binding hoặc bindToServer đúng với mục tiêu chưa?
- [ ] Có biết @SpringBootTest mặc định MOCK không?
- [ ] Nếu dùng @WebFluxTest, các collaborator đã được mock/import đúng chưa?
- [ ] Nếu cần WebFilter, nó có trong chain đang test không?
- [ ] Nếu cần security, test có cùng matcher/chain như production không?
- [ ] Nếu dùng RANDOM_PORT, có lấy port động không?
- [ ] Có tránh phụ thuộc port 8080 cố định trong CI không?
- [ ] Có đặt responseTimeout phù hợp cho client thật không?
- [ ] Có kiểm tra cả HTTP status, headers, body và streaming khi cần không?
- [ ] Có consume/cancel response body cho stream vô hạn không?
- [ ] Database/downstream dependencies được cô lập hoặc quản lý rõ không?
- [ ] Có tránh giả định test @Transactional rollback server writes không?
- [ ] Nếu mục tiêu là proxy/TLS, request có thật sự đi qua hạ tầng đó không?
- [ ] Test chạy được trên CI không cần credentials production không?
- [ ] Có giữ test nhẹ cho nhiều edge cases và một số live smoke tests không?

## 20. Câu hỏi tự kiểm tra

**1.** WebTestClient có luôn dùng socket không? Không. Nó có mock-server binding và live-server binding.

**2.** bindToController dùng cho gì? Dựng WebFlux handler chain cho controller cụ thể, không khởi động server.

**3.** bindToRouterFunction có mở HTTP port không? Không.

**4.** bindToApplicationContext có mở port không? Không, nó tạo mock handler chain từ context.

**5.** @WebFluxTest có nạp tất cả service không? Không, web slice thường mock service dependency bằng @MockitoBean.

**6.** @SpringBootTest không ghi webEnvironment chạy mode nào? MOCK.

**7.** @SpringBootTest(RANDOM_PORT) có server thật không? Có, embedded server trên cổng ngẫu nhiên.

**8.** @LocalServerPort dùng khi nào? Khi cần lấy cổng mà embedded server đã được cấp.

**9.** bindToServer() có start server không? Không, chỉ kết nối tới server sẵn có.

**10.** Full-context MOCK có dùng service/repository thật không? Có thể, theo context đã nạp.

**11.** Test controller-only có tự scan @Component WebFilter không? Không.

**12.** Cùng nhận JSON 200 ở mock và live có đồng nghĩa test cùng phạm vi? Không, live còn kiểm tra HTTP transport.

**13.** Server thật trên localhost có kiểm chứng CDN production không? Không.

**14.** Security mockUser() có tạo HTTP header Basic/Bearer qua socket không? Không.

**15.** Streaming WebTestClient dùng API nào? returnResult(T.class) để lấy FluxExchangeResult<T>, rồi StepVerifier.

**16.** @Transactional test method có rollback mọi server write trong RANDOM_PORT không? Không bảo đảm; cần test data isolation.

**17.** Vì sao chọn RANDOM_PORT thay DEFINED_PORT cho CI? Giảm xung đột và tránh cần dự đoán port.

**18.** Khi nào nên ưu tiên bindToController? Khi chỉ cần kiểm tra mapping, binding, status và DTO serialization của controller.

**19.** Khi nào nên dùng full-context mock? Khi cần bean wiring/filter/security trong Spring context nhưng không cần socket.

**20.** Khi nào nhất thiết cần live-server? Khi muốn kiểm tra server connector và HTTP transport thật.

## 21. Kết luận

Đừng đánh giá WebFlux test chỉ bằng việc thấy chữ `WebTestClient`. Câu hỏi quan trọng là **request đã đi qua đường nào**:

~~~text
WebTestClient.bindToController / bindToRouterFunction
    -> mock exchange, controller/route scope

WebTestClient.bindToApplicationContext
    -> mock exchange, bean scope do context quyết định

@WebFluxTest / @SpringBootTest(MOCK) + WebTestClient
    -> Spring TestContext, không mở HTTP server

@SpringBootTest(RANDOM_PORT) + WebTestClient.bindToServer
    -> embedded HTTP server thật, TCP socket thật
~~~

Mock mode giúp test nhanh, cô lập và dễ xác định lỗi controller/web layer. Full-context mock giúp kiểm chứng Spring wiring và filter chain mà không cần network. Live mode giúp xác nhận ứng dụng mở port, trao đổi HTTP thật và giải mã streaming response qua socket. Kết hợp các mức kiểm thử theo rủi ro sẽ đáng tin cậy hơn việc dùng một mode cho tất cả.

**Tài liệu chính thức:**

- [Spring Framework 6.2 — WebTestClient setup, assertions, streaming](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Framework 6.2 — Testing WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-test.html)
- [Spring Framework 6.2 — WebTestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Framework 6.2 — MockitoBean và bean override](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).