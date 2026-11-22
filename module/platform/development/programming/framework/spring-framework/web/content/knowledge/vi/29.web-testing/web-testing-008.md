# WebTestClient với controller, RouterFunction, ApplicationContext và máy chủ thật

## Mục tiêu học tập

`WebTestClient` là HTTP test client của Spring Framework. Nó cung cấp API gửi yêu cầu và kiểm tra phản hồi gần giống nhau cho cả hai loại kiểm thử:

- **Mock server**: xử lý request trong bộ nhớ, không cần mở cổng HTTP hoặc khởi động servlet container/network server.
- **Live server**: mở HTTP connection đến máy chủ thực đang chạy, phù hợp kiểm thử tích hợp đầy đủ hơn.

Trong bài này, bạn sẽ biết cách chọn và dùng cả **bốn kiểu thiết lập**:

1. `bindToController(...)`: gắn với một hay một số controller để kiểm thử tập trung.
2. `bindToRouterFunction(...)`: gắn với functional endpoint **WebFlux**.
3. `bindToApplicationContext(...)`: gắn với Spring context đã được cấu hình.
4. `bindToServer()`: gọi HTTP server đang hoạt động, có địa chỉ `baseUrl(...)`.

Ngoài cách tạo client, bài phân tích phạm vi thực sự được kiểm thử, khác biệt WebFlux/Spring MVC, phương thức `exchange()`, assertions cho status/header/body/JSON, xử lý kết quả `Flux` và ví dụ Spring Boot 3.x chạy được với Java 17+ và JUnit 5.

> **Điểm dễ nhầm:** Với **Spring WebFlux**, dùng `WebTestClient.bindToController` và `WebTestClient.bindToApplicationContext`. Với **Spring MVC**, dùng `MockMvcWebTestClient.bindToController` và `MockMvcWebTestClient.bindToApplicationContext`. `WebTestClient.bindToRouterFunction` là đường kiểm thử functional routing WebFlux; không nên suy diễn rằng nó kiểm thử được mọi RouterFunction của Spring MVC.

## 1. WebTestClient kiểm thử những thành phần nào?

`WebTestClient` thuộc package `org.springframework.test.web.reactive.server`. Tuy mang chữ “reactive” trong package, nó có thể được dùng với **Spring MVC lẫn Spring WebFlux**. Phần client dựng request qua API dựa trên `WebClient` và cung cấp fluent assertions, còn lựa chọn `bind...` xác định server được gọi như thế nào.

Một luồng test điển hình:

```text
JUnit test
   |
   v
WebTestClient
   |  .get() / .post() / .put() / .delete()
   |  .uri(), .header(), .contentType(), .bodyValue()
   |  .exchange()  -> thực thi HTTP request theo setup
   v
+---------------------- Mock setup -----------------------+
| Controller riêng | RouterFunction | ApplicationContext |
| Không có real socket, request/response mock            |
+---------------------------------------------------------+
                             HOẶC
+---------------------- Live server ----------------------+
| TCP/HTTP client -> cổng của server -> application       |
+---------------------------------------------------------+
   |
   v
.expectStatus() / .expectHeader() / .expectBody()
hoặc .returnResult(...) -> Flux + StepVerifier
```

Một test đọc JSON ví dụ:

```java
client.get()
        .uri("/books/{id}", 7)
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.title").isEqualTo("Spring");
```

Đoạn này giả định client và endpoint đã được cấu hình. `exchange()` là mốc gửi request; `expect...` tạo assertions; test thất bại khi status, header hoặc body không đúng. `jsonPath("$.id")` tìm trường JSON, không phụ thuộc thứ tự các trường trong JSON object.

### 1.1. Khác WebClient trong ứng dụng

| Tiêu chí | `WebClient` | `WebTestClient` |
| --- | --- | --- |
| Mục đích | Gọi dịch vụ HTTP trong application | Viết kiểm thử HTTP |
| Kết quả thông dụng | `Mono<T>`, `Flux<T>`, `ClientResponse` | Assertion specs, `EntityExchangeResult` hoặc `FluxExchangeResult` |
| Phát request | Publisher được subscribe theo luồng reactive | Test gọi `exchange()` |
| Kiểm tra status/body | Tự viết logic theo yêu cầu ứng dụng | Có sẵn `expectStatus`, `expectHeader`, `expectBody` |
| Có thể dùng mock server không? | Không phải mục đích chính | Có, thông qua `bindTo...` |
| Có thể gọi server thật không? | Có | Có, qua `bindToServer` |

Không dùng `WebTestClient` để thay thế production HTTP client. Nó nằm trong thư viện kiểm thử và được thiết kế để các assertion thất bại đúng cách trong test.

## 2. Chọn hình thức binding

| Thiết lập | Có server HTTP thật? | Thành phần được nạp | Tình huống phù hợp |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(...)` | Không | WebFlux infrastructure và controller được chọn | Test nhanh route, binding, status, JSON, validation của một controller WebFlux |
| `WebTestClient.bindToRouterFunction(...)` | Không | WebFlux `RouterFunction` được chỉ định và xử lý chức năng tương ứng | Test functional routing + handler function WebFlux |
| `WebTestClient.bindToApplicationContext(context)` | Không | WebFlux web configuration/controller/filter được tạo trong context | Test wiring và nhiều thành phần Spring cùng hoạt động |
| `MockMvcWebTestClient.bindToController(...)` | Không | Standalone Spring MVC MockMvc và controller được chỉ định | Test controller annotation Servlet/MVC |
| `MockMvcWebTestClient.bindToApplicationContext(wac)` | Không | `WebApplicationContext` của Spring MVC + MockMvc | Test MVC với cấu hình Spring đang dùng |
| `WebTestClient.bindToServer()` | **Có** | Server/container/network stack theo địa chỉ đích | Kiểm thử tích hợp thật, security/filter/wiring/HTTP transport |

Độ “rộng” của test tăng khi chuyển từ controller độc lập tới application context và server thật. Tuy vậy, nhiều thứ như TLS, proxy, CORS ở lớp gateway, database thực và các dịch vụ ngoài **chỉ** được chứng minh nếu môi trường test thực sự có chúng. Không gọi một mock server test là end-to-end đầy đủ chỉ vì nó dùng API HTTP giống thật.

## 3. Bind trực tiếp vào controller

### 3.1. Controller WebFlux

```java
WebTestClient client = WebTestClient
        .bindToController(new BookController())
        .build();

client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.title").isEqualTo("Spring");
```

Đoạn này **minh họa**, `BookController` sẽ được định nghĩa ở ví dụ chạy được bên dưới. Spring tạo chuỗi xử lý WebFlux cho controller đã truyền vào, đủ để thực hiện mock request/response. Bạn không cần `localhost`, port hoặc Netty.

Có thể truyền nhiều controller trong một setup. Đây là phương án tốt khi muốn phát hiện nhanh lỗi annotation như `@GetMapping`, `@PathVariable`, request body binding, serialization hoặc status mapping.

**Giới hạn:** `bindToController` không tự nạp toàn bộ component scan, security filter, `@ControllerAdvice`, custom codec hoặc service bean của ứng dụng. Nếu controller cần dependencies, tạo instance với mock/stub rõ ràng; cấu hình thêm controller advice/validator tùy setup, hoặc chuyển sang bind-to-context khi mục tiêu là kiểm tra wiring thực.

### 3.2. Controller Spring MVC

Controller MVC chạy trên Servlet infrastructure. Muốn dùng cùng cách viết assertions của `WebTestClient`, cần adapter MockMvc:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = MockMvcWebTestClient
        .bindToController(new MvcBookController())
        .build();
```

`MvcBookController` là class giả định do project MVC khai báo. Đây là **snippet cho một ứng dụng MVC riêng**, không phải một class thuộc demo WebFlux phía sau.

Cơ chế này dùng `StandaloneMockMvcBuilder` và Spring MVC mock request/response; không khởi động Tomcat thật. Không nhầm `WebTestClient.bindToController` (WebFlux) với `MockMvcWebTestClient.bindToController` (MVC) khi test một controller truyền thống.

## 4. Bind trực tiếp vào RouterFunction (WebFlux)

Functional endpoint WebFlux có router và handler function, không bắt buộc có `@RestController`. Một ví dụ:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
        RequestPredicates.GET("/hello/{name}"),
        request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "message", "Hello " + request.pathVariable("name"))));

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/hello/Lan")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello Lan");
```

Imports bổ sung trong snippet: `java.util.Map`, `org.springframework.http.MediaType`, `org.springframework.web.reactive.function.server.RouterFunction`, `RouterFunctions`, `RequestPredicates`, `ServerResponse`.

`WebTestClient.bindToRouterFunction(routes)` dùng `RouterFunctions.toWebHandler` để dựng mock WebFlux `WebHandler`. Nó kiểm tra route predicate, trích xuất path variables, handler response và serialization mà **không mở server port**.

Một vài tình huống đáng test:

- Request khớp predicate `GET("/hello/{name}")` trả HTTP 200 và body đúng.
- Method hoặc path không khớp route dự kiến thì không được xử lý như route đó.
- Query param/header predicate có được phân nhánh đúng không.
- Body/codec và lỗi phát sinh trong handler function có được biến thành response như mong đợi không.

**Giới hạn quan trọng:** Spring Framework 6.2 không cung cấp đường binding `WebTestClient.bindToRouterFunction` tương đương cho **functional endpoint Spring MVC**. Nếu đang dùng `org.springframework.web.servlet.function.RouterFunction`, hãy dùng công cụ test MVC phù hợp (ví dụ MockMvc với Spring MVC context) hoặc test trên server thật. Đừng truyền kiểu WebMvc RouterFunction vào method WebFlux chỉ vì cùng tên.

## 5. Bind vào ApplicationContext

Một controller test chạy độc lập đôi khi “xanh” dù Spring application thật bị thiếu bean, sai route mapping hoặc filter không được cài. `bindToApplicationContext` mở rộng phạm vi tới những thành phần Spring đã có trong context.

### 5.1. Spring WebFlux ApplicationContext

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ContextTest {
    @Autowired
    ApplicationContext context;

    @Test
    void readsFromConfiguredApplication() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .build();

        client.get()
                .uri("/books/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7);
    }
}
```

Đây là snippet Spring Boot WebFlux, giả định ứng dụng có `/books/7`. `ApplicationContext` cần thực sự mang WebFlux web configuration. Spring dùng context để dựng `WebHandler` pipeline gồm các thành phần áp dụng trong môi trường test.

Ví dụ `@SpringBootTest(webEnvironment=MOCK)` **không mở HTTP port**. Nếu dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, server thật vẫn khởi động do annotation, nhưng client được tạo bằng `bindToApplicationContext` vẫn xử lý request **in-memory**; nó không đột nhiên chuyển sang network mode chỉ vì context đang có server.

Dùng dạng này khi cần xác minh controller, router, codec, filters, exception handlers, dependency injection và các cấu hình đang được import. Mức độ test phụ thuộc thực tế context chứa gì: test slice hoặc test configuration rút gọn sẽ không tự động chứng minh toàn bộ ứng dụng production.

### 5.2. Spring MVC WebApplicationContext

```java
@Autowired
WebApplicationContext wac;

WebTestClient mvcClient = MockMvcWebTestClient
        .bindToApplicationContext(wac)
        .build();
```

Imports thêm: `org.springframework.web.context.WebApplicationContext` và `org.springframework.test.web.servlet.client.MockMvcWebTestClient`. Đây là snippet ở trong class test có MVC web context, không phải mã chạy độc lập.

Cơ chế này xây MockMvc từ context; mặc dù interface kiểm tra response vẫn là `WebTestClient`, HTTP request/response là mock Servlet. Nếu cần assertion dành riêng cho Servlet MVC như model attribute, forwarded URL hoặc resolved exception, có thể chuyển kết quả phù hợp sang MockMvc result actions thông qua tiện ích tương ứng của `MockMvcWebTestClient`.

### 5.3. Những gì context test có thể và không thể khẳng định

Đây là **integration test của web layer trong Spring context**, không tự động là end-to-end network test.

Test có thể kiểm chứng routing/codec/filter/security được nạp trong context. Nhưng còn những câu hỏi như “reverse proxy có chuyển tiếp header không”, “TLS certificate có đúng không”, “server nén response ra sao”, “database thật có hoạt động không” phụ thuộc môi trường tương ứng. Khi các yếu tố mạng hoặc deployment là đối tượng cần chứng minh, dùng `bindToServer` trên hạ tầng phù hợp.

## 6. Bind vào máy chủ HTTP thật

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();

client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(7);
```

Khác với mock binding, setup này gửi HTTP đến process/server thực đang lắng nghe port. Nó có thể test ứng dụng chạy ở localhost, test container, môi trường integration hoặc một staging environment đã được chuẩn bị.

Trong JUnit của Spring Boot, dùng **random port** để tránh đụng cổng giữa các test/process:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpTest {
    @LocalServerPort
    int port;

    @Test
    void checksLiveEndpoint() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get().uri("/books/7")
                .exchange()
                .expectStatus().isOk();
    }
}
```

`@LocalServerPort` thuộc `org.springframework.boot.test.web.server.LocalServerPort`. Đây là snippet đầy đủ về ý tưởng; project demo phía dưới có cấu trúc test chạy được.

**Những điểm cần nhớ:**

- `baseUrl(...)` là địa chỉ tuyệt đối (scheme, host, port), nên không cần port khi gọi `uri("/books/7")`.
- `RANDOM_PORT` chỉ dành cho **embedded server được khởi chạy bởi test**; không dùng một cổng đoán trước.
- Timeout giới hạn thời gian chờ phản hồi trong test để tránh treo CI.
- Để kiểm tra TLS, reverse proxy hoặc networking thực, kết nối tới chính tầng mạng mà bạn muốn kiểm chứng. Live localhost chỉ xác minh stack trên host local.
- Nếu chạy test song song, tránh state dùng chung không cô lập; nếu cần database/external services, dùng fixtures/test containers riêng.

## 7. Viết assertion với WebTestClient

### 7.1. Request: path, query, header, body

```java
client.post()
        .uri(builder -> builder.path("/books")
                .queryParam("source", "test")
                .build())
        .header("X-Correlation-Id", "test-123")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("title", "HTTP Tests"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueEquals("Location", "/books/9")
        .expectBody()
        .jsonPath("$.title").isEqualTo("HTTP Tests");
```

Request body có thể là DTO, record, map hoặc publisher có codec hỗ trợ. Kiểu HTTP body và expected response phải khớp API. Trong test, `Content-Type` mô tả request gửi lên, còn `Accept` mô tả response mong muốn. Đối với endpoint GET không có body, `contentType(...)` thường không cần thiết.

### 7.2. Kiểm tra status và header

Các phương thức thường dùng:

```java
client.get().uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

Tùy endpoint, có thể dùng `isCreated()`, `isNoContent()`, `isNotFound()`, `is4xxClientError()` hoặc kiểm tra status cụ thể bằng `isEqualTo(422)`. `expectHeader().valueEquals(...)` kiểm tra chính xác giá trị header; `valueMatches(...)` cho regex khi hợp đồng cần dạng mẫu.

Với lỗi, đừng kiểm tra một JSON error body “mặc định” chưa chắc cố định giữa các phiên bản Spring Boot. Nếu hợp đồng API chỉ cam kết 404, test status 404; chỉ test body lỗi khi ứng dụng thực sự định nghĩa schema.

### 7.3. Kiểm tra JSON theo cấu trúc

```java
client.get().uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.title").isEqualTo("Spring");
```

`jsonPath` hữu ích vì thứ tự keys, khoảng trắng và định dạng JSON thường không quan trọng về ngữ nghĩa. Có thể dùng `expectBody(Book.class)` để decode thành DTO và assert record/object. Muốn kiểm tra cả danh sách, `expectBodyList(Book.class)` hỗ trợ assertions về size và phần tử.

### 7.4. Nhận toàn bộ kết quả để assert sâu hơn

```java
EntityExchangeResult<Book> response = client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Book.class)
        .returnResult();

assertEquals(7L, response.getResponseBody().id());
```

Imports: `org.springframework.test.web.reactive.server.EntityExchangeResult`, `org.junit.jupiter.api.Assertions.assertEquals`. Đây là đoạn để đặt trong test, giả định `Book` đã khai báo trong project. `returnResult()` hữu ích khi muốn assert những điều mà JSONPath không tiện diễn đạt; đừng mặc định DTO luôn khác null nếu endpoint có thể trả HTTP 204.

### 7.5. Reactive stream và dữ liệu vô hạn

Nếu endpoint trả stream nhiều phần tử (SSE/NDJSON), đừng dùng `expectBodyList(...)` với luồng vô hạn: nó có thể chờ tới timeout hoặc tích lũy quá nhiều phần tử. Thay vào đó:

```java
FluxExchangeResult<Book> response = client.get()
        .uri("/books/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(Book.class);

StepVerifier.create(response.getResponseBody())
        .expectNext(new Book(7, "Spring"))
        .expectNext(new Book(8, "Reactor"))
        .verifyComplete();
```

Đoạn trên giả định server phát **đúng hai phần tử** và hoàn tất. `StepVerifier` thuộc `reactor-test`; `FluxExchangeResult` thuộc `org.springframework.test.web.reactive.server`. Nếu server phát vô hạn, áp dụng `take(n)` hoặc hủy subscription có chủ đích với timeout. Streaming semantics phải được cả server, media type và decoder hỗ trợ.

## 8. Ví dụ hoàn chỉnh: bốn kiểu binding trên Spring Boot WebFlux

Dự án sau có:

- Một `@RestController` với GET, POST và endpoint sự kiện.
- Một `RouterFunction<ServerResponse>`.
- Một test class dùng **cả bốn mode**: controller, router function, application context và live server.
- Kiểm thử JSON body, Location header, 404 và `Flux` streaming.

Cấu hình dựa trên **Spring Boot 3.3.6** (Spring Framework 6.1.x), Java 17. Những API dùng trong demo cũng phù hợp về ý tưởng với Spring Framework 6.2. Không cần database hoặc external HTTP service.

### 8.1. Cấu trúc

```text
webtestclient-demo/
├── build.gradle
└── src/
    ├── main/java/demo/webtest/
    │   ├── WebTestDemoApplication.java
    │   └── BookController.java
    └── test/java/demo/webtest/
        └── WebTestClientModesTest.java
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` mang WebFlux server và WebClient runtime; `spring-boot-starter-test` cung cấp JUnit 5, Spring Test, WebTestClient test support và thư viện assertions; `reactor-test` cho `StepVerifier`. Gradle plugin và dependency management đồng bộ phiên bản từ Spring Boot.

**Không thêm đồng thời `spring-boot-starter-web` vào demo này**, vì Spring Boot có quy tắc tự chọn web stack khi cả Spring MVC và WebFlux cùng trên classpath. Ví dụ muốn minh họa thuần WebFlux để những binding cụ thể đúng context.

### 8.3. WebTestDemoApplication.java

```java
package demo.webtest;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;

@SpringBootApplication
public class WebTestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTestDemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> helloRouter() {
        return RouterFunctions.route(
                GET("/hello/{name}"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                                "message",
                                "Hello " + request.pathVariable("name"))));
    }
}
```

`helloRouter()` tạo endpoint functional `GET /hello/{name}`. Handler đọc biến `name` và tạo JSON response, ví dụ gọi `/hello/Lan` trả `{"message":"Hello Lan"}`. Nó là bean của ApplicationContext nên vừa được phép kiểm thử tách riêng bằng `bindToRouterFunction`, vừa được load chung khi bind context hoặc gọi server thật.

### 8.4. BookController.java

```java
package demo.webtest;

import java.net.URI;
import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/books")
public class BookController {

    public record Book(long id, String title) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public Mono<Book> one(@PathVariable long id) {
        if (id != 7) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found"));
        }
        return Mono.just(new Book(7, "Spring"));
    }

    @GetMapping
    public Flux<Book> all(@RequestParam(defaultValue = "2") int limit) {
        return Flux.just(
                new Book(7, "Spring"),
                new Book(8, "Reactor"))
                .take(Math.max(0, Math.min(limit, 2)));
    }

    @PostMapping
    public Mono<ResponseEntity<Book>> create(
            @RequestBody Mono<CreateBook> input) {
        return input.map(dto -> ResponseEntity
                .created(URI.create("/books/9"))
                .body(new Book(9, dto.title())));
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Book> events() {
        return Flux.just(
                new Book(7, "Spring"),
                new Book(8, "Reactor"))
                .delayElements(Duration.ofMillis(10));
    }
}
```

Controller này không giữ state mutable: mỗi test có input và kết quả xác định. `Mono.error(ResponseStatusException)` trở thành HTTP 404 qua tầng WebFlux. `create()` đọc JSON request thành `CreateBook` và trả status 201 với `Location: /books/9`. `events()` phát hai object theo định dạng SSE rồi kết thúc, để `StepVerifier` có thể xác nhận `verifyComplete()`.

Lưu ý `all()` không phụ thuộc database: demo ưu tiên cơ chế test, không mô phỏng persistence. Cần kiểm thử business logic, persistence hay transaction thật thì thêm các thành phần đó trong bài test chuyên biệt.

### 8.5. WebTestClientModesTest.java

```java
package demo.webtest;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.test.StepVerifier;

import demo.webtest.BookController.Book;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class WebTestClientModesTest {

    @LocalServerPort
    int port;

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    RouterFunction<ServerResponse> helloRouter;

    @Test
    void bindToController_usesMockWebFluxRequest() {
        WebTestClient client = WebTestClient
                .bindToController(new BookController())
                .build();

        client.get()
                .uri("/books/{id}", 7)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.id").isEqualTo(7)
                    .jsonPath("$.title").isEqualTo("Spring");
    }

    @Test
    void bindToRouterFunction_testsFunctionalEndpoint() {
        WebTestClient client = WebTestClient
                .bindToRouterFunction(helloRouter)
                .build();

        client.get()
                .uri("/hello/Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.message").isEqualTo("Hello Lan");
    }

    @Test
    void bindToApplicationContext_usesConfiguredWebFluxPipeline() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.post()
                .uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "HTTP Tests"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals("Location", "/books/9")
                .expectBody()
                    .jsonPath("$.id").isEqualTo(9)
                    .jsonPath("$.title").isEqualTo("HTTP Tests");
    }

    @Test
    void bindToServer_sendsHttpToRandomPort() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.get()
                .uri("/books/404")
                .exchange()
                .expectStatus().isNotFound();

        client.get()
                .uri("/books?limit=2")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(Book.class)
                .hasSize(2);
    }

    @Test
    void streamResultCanBeCheckedWithStepVerifier() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        FluxExchangeResult<Book> response = client.get()
                .uri("/books/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Book.class);

        StepVerifier.create(response.getResponseBody())
                .expectNext(new Book(7, "Spring"))
                .expectNext(new Book(8, "Reactor"))
                .verifyComplete();
    }
}
```

**Chú ý về cú pháp import:** Trong Java, cách đúng để import nested record là `import demo.webtest.BookController.Book;`, **không phải static import type**. Hãy dùng dòng sau thay cho dòng `import static demo.webtest.BookController.Book;` trong phần imports nếu IDE/compiler không chấp nhận:

```java
import demo.webtest.BookController.Book;
```

Mỗi test ở trên kiểm tra một đường khác nhau. Vì dùng `@SpringBootTest(RANDOM_PORT)` trên cả lớp, embedded server được tạo chung cho test class, **ngay cả ba test mock**. Điều này là lựa chọn minh họa tiện gom đủ bốn chế độ trong một file. Trong test suite thực tế, nên đặt các test mock controller/router vào class **không có `@SpringBootTest`** để tăng tốc và chứng minh chúng không cần khởi động server.

### 8.6. Chạy dự án

Tại thư mục có `build.gradle`, cài JDK 17+ và Gradle tương thích, chạy:

```bash
gradle test
```

Hoặc `./gradlew test` (Unix/macOS) / `gradlew.bat test` (Windows) nếu đã có Gradle Wrapper. Spring Boot 3.3.6 tương thích Java 17; nếu dùng JDK 21 cũng ổn.

Các kết quả mong đợi theo **hợp đồng HTTP trong demo**:

| Request/test | HTTP status | Đặc điểm body/header |
| --- | --- | --- |
| Controller `GET /books/7` | 200 | JSON có `id=7`, `title=Spring` |
| Router `GET /hello/Lan` | 200 | JSON có `message=Hello Lan` |
| Context `POST /books` | 201 | `Location: /books/9`, JSON `id=9` |
| Server `GET /books/404` | 404 | Không giả định schema lỗi cụ thể |
| Server `GET /books?limit=2` | 200 | JSON array 2 cuốn sách |
| Server `GET /books/events` | 200 | SSE gồm hai `Book`, sau đó kết thúc |

Không cam kết một stdout cố định của Gradle: logs và kết quả build phụ thuộc phiên bản Gradle, JDK và môi trường. Bài kiểm thử đạt khi JUnit 5 assertions đều pass. Để xem một request thật trong trình duyệt, chạy `gradle bootRun` và mở `http://localhost:8080/books/7`.

## 9. Tổ chức test suite hợp lý trong dự án thật

Một thiết kế thực tế thường chia:

```text
src/test/java/...
├── BookControllerMockTest.java       // bindToController
├── HelloRouterTest.java              // bindToRouterFunction
├── WebContextIntegrationTest.java    // bindToApplicationContext
└── LiveServerIntegrationTest.java    // bindToServer + RANDOM_PORT
```

Tại sao?

- **Controller test** chạy nhanh, ít dependency, tập trung status, binding, serialization của một controller.
- **RouterFunction test** xác minh route predicate và handler function; không cần Spring context nếu tự tạo router.
- **ApplicationContext test** xác minh component scan, filters, `@ControllerAdvice`, converters và cấu hình thực sự được nạp.
- **Live server test** xác minh thêm HTTP transport, server configuration và các vấn đề có thể chỉ xuất hiện khi request đi qua real socket.

Đừng dùng test quá nặng cho lỗi rất đơn giản. Ngược lại, test mock một controller độc lập không đủ làm bằng chứng rằng production web security, proxy và kết nối bên ngoài hoạt động.

### 9.1. Test slice và Spring Boot annotations

Trong Boot WebFlux, `@WebFluxTest` có thể tạo context rút gọn chỉ cho web slice; `@AutoConfigureWebTestClient` có thể cấu hình client để injection tùy kiểu test. Nếu dùng injection `@Autowired WebTestClient` thì phải bảo đảm test annotation/configuration hỗ trợ nó, thay vì tưởng mọi `@SpringBootTest` đều tự tạo WebTestClient ở mọi cấu hình.

Với MVC, `@WebMvcTest` và `MockMvc` là con đường phổ biến cho controller slice. Nếu muốn giao diện assertion của WebTestClient, có thể dùng `MockMvcWebTestClient` trên MockMvc hoặc MVC context phù hợp. Chọn test annotation theo **stack phía server**.

### 9.2. Dữ liệu test, isolation và concurrency

Nếu có database thật, dùng fixture có thể tái lập, cleanup/transaction rõ ràng và test containers khi cần. Với server chạy ở random port, mỗi test process có thể chọn một cổng tự do nhưng các test vẫn có thể chia sẻ database/cache. Không dựa vào thứ tự chạy của JUnit; tránh phụ thuộc state tạo bởi test khác. Khi kiểm tra streaming, đặt timeout và hủy subscription để test không bị treo.

## 10. Cấu hình client và khả năng chẩn đoán

### 10.1. configureClient() và bindToServer()

Mock server binding trả một `MockServerSpec`. Sau khi chỉnh setup mock server, dùng `configureClient()` để chuyển sang phần cấu hình HTTP client:

```java
WebTestClient client = WebTestClient
        .bindToController(new BookController())
        .configureClient()
        .baseUrl("/api")
        .defaultHeader("X-Test-Source", "junit")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Nếu controller mapping thực là `/books/...` và đặt `baseUrl("/api")`, request `client.get().uri("/books/7")` mang path có tiền tố `/api`: controller ví dụ sẽ không khớp nếu không có route tương ứng. Đoạn cấu hình là ví dụ API **không dùng trực tiếp để chạy test trong demo**. Hãy chỉ định base URL thật sự đúng với server setup.

Với live server, các client options thường được cấu hình trực tiếp từ `bindToServer()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .defaultHeader("X-Test-Source", "junit")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Không log Authorization hoặc cookie thật. Test dùng HTTP headers khi cần kiểm tra hợp đồng; riêng việc có header trong request không chứng minh server đã xác thực user. Nếu kiểm thử Spring Security, dùng security test utilities và assertion 401/403/200 theo từng user/role cụ thể.

### 10.2. Assertion thông báo lỗi dễ hiểu

Giảm độ khó chẩn đoán khi test fail bằng cách chia expectations rõ ràng và thêm mô tả hoặc dùng `consumeWith(...)` cho assertions tùy chỉnh. Khi dữ liệu là JSON, thường chọn `jsonPath` hoặc `json(...)` theo nội dung hợp đồng, thay vì so sánh chuỗi JSON chứa thứ tự keys/whitespace không quan trọng.

Với body lớn hoặc streaming, chỉ log lượng dữ liệu vừa đủ và đã loại thông tin nhạy cảm. Mọi mock/live test nên đặt timeout hợp lý; không dùng `Thread.sleep(...)` để “đợi server”.

### 10.3. Request và response có cấu trúc

Sau `exchange()` bạn có thể kiểm tra:

- `expectStatus()`: HTTP status.
- `expectHeader()`: Content-Type, Location, ETag hoặc custom headers.
- `expectCookie()`: HTTP response cookies khi hợp đồng có cookie.
- `expectBody()`: body bytes, JSONPath hoặc JSON assertion.
- `expectBody(T.class)`, `expectBodyList(T.class)`: giải mã body thành DTO/collection.
- `returnResult(T.class)`: kiểm tra publisher response, nhất là stream nhiều phần tử.

Đặt assertion đúng hợp đồng: nếu chỉ cam kết 204 No Content, không cố đọc một DTO; nếu phản hồi là SSE vô hạn, tránh API buộc đọc toàn bộ body.

## 11. Những lỗi thường gặp

1. **Gọi `WebTestClient.bindToController` cho controller MVC rồi mong test Servlet stack.** Với MVC, dùng `MockMvcWebTestClient.bindToController` hoặc MockMvc; với WebFlux mới dùng trực tiếp.
2. **Dùng `bindToRouterFunction` với `org.springframework.web.servlet.function.RouterFunction`.** Method này dành cho WebFlux functional router; đây là hai kiểu khác package.
3. **Nghĩ mock binding tự chạy HTTP server.** `bindToController`, `bindToRouterFunction` và `bindToApplicationContext` chạy mock request/response, không mở network connection.
4. **Nghĩ test có `RANDOM_PORT` nghĩa client luôn dùng server thật.** Chỉ `bindToServer()` với URL/port thật mới đi qua socket; `bindToApplicationContext` vẫn là mock mode.
5. **Quên cấu hình route/baseUrl và nhận 404 giả.** Soát đường dẫn được tạo từ base URL, controller mapping và URI template.
6. **Đặt `@SpringBootTest` cho mọi controller unit test.** Khi không cần context, `bindToController` có thể chạy nhanh hơn và cô lập hơn.
7. **Dùng `expectBodyList` cho stream vô hạn.** Dùng `returnResult`, Reactor `StepVerifier`, timeout và giới hạn phần tử phù hợp.
8. **Assert toàn bộ body lỗi Spring mặc định.** Schema lỗi có thể thay đổi theo cấu hình/phiên bản; test hợp đồng nghiệp vụ đã được xác định.
9. **Gọi service thật ngoài Internet từ test mock.** Nếu controller tự gọi service ngoài qua HTTP, bind controller không tự chặn những calls đó. Stub/mock dependency hoặc tạo test integration riêng.
10. **Test security bằng một controller độc lập nhưng quên filters/security chain.** Chọn context/security configuration hoặc live server mode để đánh giá bảo vệ end-to-end.
11. **Quên dependency reactor-test khi dùng StepVerifier.** `reactor-test` là thư viện kiểm thử Reactor, cần nằm trong test classpath.
12. **So sánh JSON theo thứ tự thuộc tính hoặc timing chính xác.** Kiểm tra nội dung theo contract, dùng timeout hợp lý và tránh giả định scheduling.

## 12. Bài tập thực hành

**Bài 1 — Controller mock:** Viết test GET `/books/7` trả 200, `id=7`; GET `/books/8` trả 404. Dùng `WebTestClient.bindToController(new BookController())`. Nêu những thành phần Spring application chưa được xác minh.

**Bài 2 — Functional router:** Đổi router thành `GET /hello/{name}?lang=vi`, response JSON là `{"message":"Xin chào Lan"}`. Test một URL đúng và một URL sai với `bindToRouterFunction`.

**Bài 3 — Context wiring:** Thêm một `WebFilter` vào application context để gắn header response `X-Env: test`. Tại sao test `bindToApplicationContext` thích hợp để xác nhận filter này hơn test một controller standalone không bổ sung filter?

**Bài 4 — Live server:** Chạy test với `RANDOM_PORT`, gửi GET qua `bindToServer` tới `http://127.0.0.1:<port>/books/7`. Thay port thành một cổng không có server, phân biệt lỗi kết nối với một HTTP status 404.

**Bài 5 — POST và Location:** Dùng client từ context test để POST `{"title":"New Book"}` tới `/books`. Assert HTTP 201, `Location: /books/9` và JSON title đúng. Giải thích khác biệt giữa `contentType` và `accept`.

**Bài 6 — SSE:** Giả sử endpoint `/books/events` phát vô hạn. Viết test chỉ nhận hai phần tử đầu rồi hủy subscription. Vì sao `verifyComplete()` không đúng nếu stream không bao giờ hoàn tất?

**Bài 7 — Chọn mức kiểm thử:** Với một bug mapping path variable, một bug thiếu WebFilter bean, một bug TLS certificate và một bug reverse proxy strip header, hãy chọn mode ít tốn chi phí nhất mà vẫn kiểm chứng được từng lỗi. Phân biệt cái nào đòi môi trường live thật.

## Tóm tắt kiến thức

- `WebTestClient` thống nhất cú pháp request và assertions cho mock và live HTTP test.
- `bindToController`: tập trung một hoặc nhiều controller, thường nhanh và cô lập.
- `bindToRouterFunction`: kiểm thử **functional endpoints WebFlux** trong bộ nhớ.
- `bindToApplicationContext`: kiểm thử web infrastructure đã được load từ Spring context, vẫn là mock HTTP.
- `bindToServer`: gửi HTTP qua mạng đến server đang chạy, phù hợp integration/e2e hơn.
- Trong **Spring MVC**, dùng `MockMvcWebTestClient` cho controller/context mock, còn live server vẫn dùng `WebTestClient.bindToServer`.
- `exchange()` kích hoạt request; sau đó dùng `expectStatus`, `expectHeader`, `expectBody` hoặc `returnResult` và `StepVerifier`.
- Chọn mode dựa vào bug cần bắt, thời gian chạy và các hạ tầng thật sự được đưa vào phạm vi test.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — WebTestClient và bốn chế độ setup: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Spring Framework 6.2 — Spring MVC test framework: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — WebFlux functional endpoints: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework — WebTestClient Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
