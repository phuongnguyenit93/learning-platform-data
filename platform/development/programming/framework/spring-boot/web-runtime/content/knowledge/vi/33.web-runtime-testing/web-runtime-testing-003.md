# @WebFluxTest, WebTestClient và phạm vi kiểm thử reactive trong Spring Boot

## 1. Mục tiêu

Để kiểm thử một ứng dụng **Spring WebFlux**, trước hết phải biết test đang kiểm tra **một publisher `Mono`/`Flux`**, **lát cắt web** hay **toàn ứng dụng và HTTP server thật**. Các cấp kiểm thử có cách thiết lập, độ nhanh và bằng chứng rất khác nhau dù đều có thể dùng API trông giống `client.get().uri(...).exchange()`.

Ba công cụ trọng tâm:

- **`@WebFluxTest`** của Spring Boot: khởi tạo web test slice, auto-configure Spring WebFlux HTTP handler, codecs, web advice và `WebTestClient`, **không tự nạp toàn bộ service/repository/database**.
- **`WebTestClient`** của Spring Framework: gọi HTTP endpoint và assert status, headers, body; có thể bind vào **mock controller/context/router** hoặc **HTTP server thật**.
- **`StepVerifier`** của Reactor Test: xác minh tín hiệu `onNext`, `onComplete`, `onError`, cancellation, demand và virtual time của reactive publisher, **không tự kiểm tra HTTP contract**.

Bài thuộc **Kiểm thử web runtime** của module **Spring Boot - web-runtime**, sử dụng **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit 5/Jupiter, Mockito và reactor-test**. Những import `@WebFluxTest` bên dưới là của **Boot 3.5**; Spring Boot 4.x có mô-đun/package test thay đổi. Với production mới, dùng nhánh Boot còn hỗ trợ và security patches hiện hành; Boot 3.5.16 dùng làm baseline tái lập bài học.

Sau bài học, bạn có thể:

1. Mô tả chính xác phạm vi bean được nạp bởi `@WebFluxTest(controllers=...)`, cách đưa mock vào context bằng `@MockitoBean`.
2. Kiểm tra `GET/POST`, JSON, validation `400`, not-found `404`, unsupported type `415`, `201 Location` và ControllerAdvice.
3. Dùng `FluxExchangeResult` với `StepVerifier` cho SSE/streaming thay vì buffer một stream vô hạn.
4. Phân biệt `bindToController`, `bindToApplicationContext`, `bindToRouterFunction`, `bindToServer`.
5. Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` để chứng minh có **real HTTP connector**.
6. Test signals, error/cancel/virtual time bằng StepVerifier và tránh `block()` trên event loop.
7. Phân biệt test xanh nhờ mock với việc DB, outbound HTTP, security/proxy và resource management **thật sự đã được kiểm chứng**.

## 2. Ma trận phạm vi: unit → slice → full HTTP

```text
Reactive unit test
  service/handler functions + StepVerifier (không Spring context)
      |
      v
@WebFluxTest(CatalogController.class)
  WebFlux codecs, mappings, advice, filters được chọn
  @MockitoBean CatalogService
  WebTestClient trên mock web exchange, KHÔNG mở TCP port
      |
      v
@SpringBootTest + @AutoConfigureWebTestClient
  Full ApplicationContext, webEnvironment=MOCK mặc định
  Có Spring beans thật nhưng vẫn KHÔNG có server port
      |
      v
@SpringBootTest(webEnvironment=RANDOM_PORT)
  Full context + embedded HTTP server; WebTestClient qua loopback
      |
      v
Staging/E2E qua ingress, TLS, remote dependencies
```

| Test | Context | Mở HTTP server thật? | Cái kiểm tra được |
| --- | --- | --- | --- |
| `StepVerifier` unit | Không bắt buộc | Không | Mono/Flux values, errors, completion/cancel |
| `WebTestClient.bindToController` | Test handler setup tối thiểu | Không | WebFlux controller và HTTP decoding/encoding |
| `@WebFluxTest` | Web slice | Không | Controller mapping, codec, validation, advice và mock collaborator |
| `@SpringBootTest(MOCK)` + client | Full app | Không | Bean wiring với mock web exchange |
| `@SpringBootTest(RANDOM_PORT)` | Full app | **Có** | Embedded server + HTTP networking + real beans hiện có |
| E2E | Deployed system | **Có** | Gateway/proxy/TLS/auth/data theo topology |

**Không thể lấy `@WebFluxTest` pass để kết luận Reactor Netty socket, TLS, database, reverse proxy hoặc client disconnect đã hoạt động đúng**, vì slice không chạy những thành phần đó.

### 2.1. Cẩn thận Spring MVC vs Spring WebFlux

- `@WebMvcTest` dành cho Spring MVC/Servlet; thường dùng `MockMvc`.
- `@WebFluxTest` dành cho WebFlux; auto-configures `WebTestClient`.
- Nếu classpath có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường **ưu tiên MVC**; muốn reactive phải chủ động chọn stack hoặc đặt `spring.main.web-application-type=reactive` theo kiến trúc.
- `WebTestClient` cũng có adapter `MockMvcWebTestClient` cho MVC. Tên WebTestClient **không** tự chứng minh runtime đang reactive.

## 3. Bên trong `@WebFluxTest`

Với Spring Boot 3.5:

```java
@WebFluxTest(controllers = CatalogController.class)
class CatalogControllerSliceTest {
    @Autowired WebTestClient client;
    @MockitoBean CatalogService service;
}
```

Đây là **snippet**, không phải test class độc lập; mã đầy đủ ở phần 6.

`@WebFluxTest` tự xây Spring WebFlux infrastructure và chọn các thành phần web thích hợp: annotated `@Controller`/`@RestController`, `@ControllerAdvice`/`@RestControllerAdvice`, `@JsonComponent`, `Converter`/`GenericConverter`, `WebFluxConfigurer`, cùng `WebFilter`/`WebExceptionHandler` và modules liên quan theo Javadoc/auto-configuration version.

Slice **không** auto-scan `@Service`, `@Repository`, Spring Data repositories, R2DBC connections, thông thường `@ConfigurationProperties` hoặc arbitrary application beans. Nếu controller cần service, test phải cung cấp mock/bean:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
CatalogService service;
```

Trong Spring Framework 6.2, `@MockitoBean` đăng ký hoặc override **Spring bean** trong test ApplicationContext. Mockito `@Mock` đơn lẻ chỉ tạo object ngoài Spring BeanFactory, không tự giải quyết constructor injection của controller. `@MockBean` Boot cũ đã deprecated từ Boot 3.4 để thay bằng `@MockitoBean`.

**Không import cả application config chỉ để slice khởi động.** Nếu cần một custom converter/serializer/error handler, dùng `@Import(SpecificWebConfig.class)`. Nếu cần configuration properties, dùng `@EnableConfigurationProperties(...)` theo đúng scope. Một `@ComponentScan` tùy chỉnh quá rộng trên main application class có thể phá test slice filters và kéo cả service/repository vào.

### 3.1. Hai giới hạn dễ bỏ sót

1. `@WebFluxTest` **không tự tìm functional `RouterFunction<?>` routes** như cách tìm annotated controllers. Dùng `WebTestClient.bindToRouterFunction(...)` hoặc `@Import` route configuration hoặc `@SpringBootTest`.
2. `@WebFluxTest` **không tự phát hiện một custom `SecurityWebFilterChain` bean** của production. Nếu ứng dụng có reactive security, có thể nạp default security auto-config theo classpath nhưng không phải custom policy. Muốn test authorization đúng phải import security config hoặc dùng full integration, không tắt bảo mật chỉ để qua HTTP 200.

## 4. `WebTestClient` và bốn cách bind

`WebTestClient` thuộc `org.springframework.test.web.reactive.server`. Một request:

```java
client.get().uri("/api/items/a1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.name").isEqualTo("Book");
```

`get/post/delete` xác định method; `uri` URL/template; `contentType` là request body type; `accept` là response format muốn nhận; `exchange` thực hiện qua binding đã chọn; `expectStatus/expectHeader/expectBody/expectBodyList/returnResult` assert kết quả.

### 4.1. Bind tới controller

```java
CatalogService mockService = Mockito.mock(CatalogService.class);
CatalogController controller = new CatalogController(mockService);

WebTestClient client =
    WebTestClient.bindToController(controller).build();
```

Snippet cần imports và domain classes ở ví dụ. Nó dựng mock WebFlux HTTP handler setup **không cần Spring Boot context**. Không tự bao gồm tất cả security filters/config ở production.

### 4.2. Bind tới context

```java
WebTestClient client =
    WebTestClient.bindToApplicationContext(applicationContext).build();
```

Spring Framework dùng WebFlux WebHandler chain từ context, vẫn không mở port. `@WebFluxTest` thường tạo client được cấu hình ở phạm vi tương tự.

### 4.3. Bind tới functional router

```java
RouterFunction<ServerResponse> route =
    RouterFunctions.route(
        RequestPredicates.GET("/fn/ping"),
        request -> ServerResponse.ok().bodyValue("pong")
    );
WebTestClient client =
    WebTestClient.bindToRouterFunction(route).build();

client.get().uri("/fn/ping").exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("pong");
```

Snippet cần các imports `org.springframework.web.reactive.function.server.*`. Không dùng `@WebFluxTest(MyHandler.class)` rồi mong mọi `RouterFunction` tự đăng ký; nếu thấy 404 trong slice có thể chỉ là thiếu route test config.

### 4.4. Bind tới server thật

```java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://127.0.0.1:8080")
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

Đây là **HTTP network client thật**; không có server lắng nghe thì sẽ fail connect. Với `@SpringBootTest(RANDOM_PORT)`, Spring Boot có thể inject client đúng random port, không hardcode 8080. Không dùng test client để gọi production có dữ liệu thật khi chưa được phép.

## 5. Dự án hoàn chỉnh: Catalog WebFlux và ba cấp test

Ứng dụng có:

- `GET /api/items/{id}` → `Mono<ItemDto>`; resource thiếu được map thành HTTP 404.
- `GET /api/items` → `Flux<ItemDto>` hữu hạn serialize thành JSON array.
- `POST /api/items` → validate JSON, trả HTTP 201 + `Location`.
- `GET /api/heartbeats` → ba Server-Sent Events (SSE) rồi complete.
- `InMemoryCatalogService` → implementation thật trong RAM, không cần database.
- `CatalogControllerSliceTest` → Mockito mock service, không mở HTTP port.
- `CatalogIntegrationTest` → server random port, gọi real service.
- `CatalogReactiveUnitTest` → StepVerifier trực tiếp.

### 5.1. Cây file

```text
webflux-testing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webfluxdemo/
    │   │   ├── WebFluxTestingApplication.java
    │   │   ├── ItemDto.java
    │   │   ├── CreateItemRequest.java
    │   │   ├── CatalogService.java
    │   │   ├── InMemoryCatalogService.java
    │   │   ├── ItemNotFoundException.java
    │   │   ├── ApiErrorAdvice.java
    │   │   └── CatalogController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/webfluxdemo/
            ├── CatalogControllerSliceTest.java
            ├── CatalogIntegrationTest.java
            └── CatalogReactiveUnitTest.java
```

Mỗi `public class` hoặc `public record` top-level ở file cùng tên, package nhất quán.

### 5.2. `pom.xml` Maven (Spring Boot 3.5.16, Java 17)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-testing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

`spring-boot-starter-webflux` sử dụng WebFlux và Reactor Netty mặc định; `spring-boot-starter-validation` cung cấp Jakarta Validation; `spring-boot-starter-test` mang JUnit/Mockito/Spring Test; `reactor-test` cung cấp StepVerifier/TestPublisher.

**Không** thêm `spring-boot-starter-web` vào bài thực hành, tránh Boot chọn MVC do classpath. Spring Boot BOM quản lý versions tương thích. Với Boot 4.x phải kiểm tra thay đổi dependency và import test annotations riêng.

### 5.3. Application properties

**`src/main/resources/application.properties`**

```properties
spring.application.name=webflux-testing-demo
server.port=8080
spring.main.web-application-type=reactive
```

Với project chỉ có WebFlux, property reactive thường không cần; nó nhấn mạnh mục tiêu. Không biến blocking I/O code thành non-blocking nhờ một property.

### 5.4. Spring Boot main

**`src/main/java/com/example/webfluxdemo/WebFluxTestingApplication.java`**

```java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxTestingApplication.class, args);
    }
}
```

### 5.5. Domain records

**`src/main/java/com/example/webfluxdemo/ItemDto.java`**

```java
package com.example.webfluxdemo;

public record ItemDto(String id, String name, int quantity) {}
```

**`src/main/java/com/example/webfluxdemo/CreateItemRequest.java`**

```java
package com.example.webfluxdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String name,
        @Min(1) int quantity
) {}
```

`@NotBlank` chặn tên null/empty/whitespace; `@Min(1)` chặn số lượng dưới 1. Record là Java 17 value type; Jackson của WebFlux deserialize từ JSON qua codecs.

### 5.6. Service contract và implementation

**`src/main/java/com/example/webfluxdemo/CatalogService.java`**

```java
package com.example.webfluxdemo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogService {
    Mono<ItemDto> findById(String id);
    Flux<ItemDto> findAll();
    Mono<ItemDto> create(CreateItemRequest request);
}
```

**`src/main/java/com/example/webfluxdemo/InMemoryCatalogService.java`**

```java
package com.example.webfluxdemo;

import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryCatalogService implements CatalogService {

    private final Map<String, ItemDto> items =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(2);

    public InMemoryCatalogService() {
        items.put("a1", new ItemDto("a1", "Book", 10));
        items.put("b2", new ItemDto("b2", "Pen", 20));
    }

    @Override
    public Mono<ItemDto> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)));
    }

    @Override
    public Flux<ItemDto> findAll() {
        return Flux.defer(() -> Flux.fromIterable(items.values()))
            .sort(Comparator.comparing(ItemDto::id));
    }

    @Override
    public Mono<ItemDto> create(CreateItemRequest request) {
        return Mono.fromSupplier(() -> {
            String id = "n" + sequence.incrementAndGet();
            ItemDto item =
                new ItemDto(id, request.name(), request.quantity());
            items.put(id, item);
            return item;
        });
    }
}
```

`@Service` **có mặt** trong full app/`@SpringBootTest`, **không tự được scan** trong `@WebFluxTest`. `Mono.defer` và `Mono.fromSupplier` giữ việc đọc/ghi in-memory diễn ra khi subscription, không thực hiện side effect ngay ở controller invocation. `ConcurrentHashMap` dùng cho demo concurrency cơ bản, không thay persistence/transaction/authorization production. `findAll` sort để output/test ổn định; database thật cần pagination và order rõ.

### 5.7. Exception và WebFlux advice

**`src/main/java/com/example/webfluxdemo/ItemNotFoundException.java`**

```java
package com.example.webfluxdemo;

public class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException() {
        super("Item not found");
    }
}
```

**`src/main/java/com/example/webfluxdemo/ApiErrorAdvice.java`**

```java
package com.example.webfluxdemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ErrorPayload(String code, String message) {}

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ErrorPayload> notFound(
            ItemNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ErrorPayload(
                "ITEM_NOT_FOUND", "Item not found"));
    }
}
```

HTTP 404 domain contract được kiểm bởi slice test. Không gửi raw internal exception/token/stack trace trong response. Có thể dùng `ProblemDetail` nếu API yêu cầu RFC 9457; chọn một schema ổn định và test contract rõ.

### 5.8. Reactive controller và SSE

**`src/main/java/com/example/webfluxdemo/CatalogController.java`**

```java
package com.example.webfluxdemo;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
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
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/items/{id}")
    public Mono<ItemDto> findById(@PathVariable String id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ItemNotFoundException()));
    }

    @GetMapping("/items")
    public Flux<ItemDto> findAll() {
        return service.findAll();
    }

    @PostMapping(
        path = "/items",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<ItemDto>> create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request)
            .map(item -> ResponseEntity
                .created(URI.create("/api/items/" + item.id()))
                .body(item));
    }

    @GetMapping(
        path = "/heartbeats",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> heartbeats() {
        return Flux.range(1, 3)
            .map(i -> ServerSentEvent.<String>builder()
                .id(Integer.toString(i))
                .event("heartbeat")
                .data("beat-" + i)
                .build());
    }
}
```

Cần hiểu:

- `Mono.empty()` từ service là **một completion rỗng**, không tự là HTTP 404. Controller `switchIfEmpty` chuyển thành `ItemNotFoundException`, được `ApiErrorAdvice` xử lý.
- `Flux<ItemDto>` hữu hạn được JSON codec trả dưới dạng array; SSE với `MediaType.TEXT_EVENT_STREAM_VALUE` là streaming HTTP, **không phải WebSocket**.
- `@Valid @RequestBody` đi qua WebFlux argument resolvers và Bean Validation; input sai trả 400 trước khi service được gọi.
- `ResponseEntity.created(...)` trả HTTP 201 + `Location`. ID in-memory được server sinh; với ID có ký tự không an toàn cần URL encode path segment.
- Không gọi `subscribe()`/`block()` trong handler; để Spring WebFlux quản lý subscription/propagation lỗi.
- `Flux.range(1,3)` chỉ giả lập ba event hữu hạn để test deterministic; SSE production có long-lived connections, heartbeat, cancellation và quotas.

## 6. Slice test hoàn chỉnh: `@WebFluxTest` + Mockito + WebTestClient

**`src/test/java/com/example/webfluxdemo/CatalogControllerSliceTest.java`**

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@WebFluxTest(controllers = CatalogController.class)
class CatalogControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;

    @Test
    void getItemReturnsExpectedJson() {
        given(service.findById("a1")).willReturn(
            Mono.just(new ItemDto("a1", "Book", 10))
        );

        client.get().uri("/api/items/a1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("a1")
            .jsonPath("$.name").isEqualTo("Book")
            .jsonPath("$.quantity").isEqualTo(10);

        verify(service).findById("a1");
    }

    @Test
    void missingItemReturnsAdvice404() {
        given(service.findById("missing"))
            .willReturn(Mono.empty());

        client.get().uri("/api/items/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND")
            .jsonPath("$.message").isEqualTo("Item not found");
    }

    @Test
    void finiteFluxProducesJsonArray() {
        given(service.findAll()).willReturn(Flux.just(
            new ItemDto("a1", "Book", 10),
            new ItemDto("b2", "Pen", 20)
        ));

        client.get().uri("/api/items")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ItemDto.class)
            .hasSize(2)
            .contains(
                new ItemDto("a1", "Book", 10),
                new ItemDto("b2", "Pen", 20)
            );
    }

    @Test
    void validPostReturns201AndLocation() {
        given(service.create(any(CreateItemRequest.class)))
            .willReturn(Mono.just(
                new ItemDto("n3", "Pencil", 3)
            ));

        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest("Pencil", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueEquals(HttpHeaders.LOCATION, "/api/items/n3")
            .expectBody()
            .jsonPath("$.name").isEqualTo("Pencil");

        verify(service).create(any(CreateItemRequest.class));
    }

    @Test
    void beanValidationRejectsBadBodyBeforeService() {
        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest(" ", 0))
            .exchange()
            .expectStatus().isBadRequest();

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void malformedJsonReturns400() {
        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{ bad-json ")
            .exchange()
            .expectStatus().isBadRequest();

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void unsupportedMediaTypeReturns415() {
        client.post().uri("/api/items")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("name=Pencil&quantity=3")
            .exchange()
            .expectStatus().isEqualTo(415);

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void sseStreamEmitsThreeEventsAndCompletes() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/heartbeats")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> assertEquals("beat-1", e.data()))
            .expectNextCount(1)
            .assertNext(e -> assertEquals("beat-3", e.data()))
            .verifyComplete();
    }
}
```

Tại sao 8 tests này hữu ích?

| Test | Phần web được kiểm | Không được tự kết luận |
| --- | --- | --- |
| GET existing | Mapping, status 200, JSON codec, field values | DB thật có item |
| GET missing | `Mono.empty` thành 404 qua advice | Remote API behavior |
| GET list | Flux hữu hạn được encode thành JSON array | Infinite streaming/backpressure |
| POST valid | JSON binding, 201, Location | Persistence commit |
| Bad body | Bean Validation 400, service không bị gọi | Mọi business input checks |
| Malformed JSON | Decoder 400 | External proxy response |
| Wrong Content-Type | `consumes`/415 | CORS/edge rewriting |
| SSE | Media type và reactive events/complete | Netty TCP/TLS và disconnect |

`@MockitoBean` trong slice tạo mock service; `given(...).willReturn(Mono.just/empty(...))` là controlled test behavior. **Nếu service mock không stub và trả null publisher, controller có thể NPE**. Không dùng mock 200 thành công để chứng minh real service trả đúng dữ liệu hoặc authorization.

### 6.1. Streaming khác body thông thường

- JSON array hữu hạn: `expectBodyList(ItemDto.class)` hợp lý vì Flux sẽ complete.
- SSE/infinite Flux: không nên dùng `expectBodyList` vì có thể chờ vô hạn. Dùng `returnResult(...)` để lấy `FluxExchangeResult<T>` và StepVerifier consume/cancel.
- Khi streaming đã gửi headers/commit HTTP 200 rồi publisher phát error, server có thể **không đổi status thành 500**; error có thể thể hiện ở stream termination/connection. Test cả signal và HTTP lifecycle.

## 7. Integration test: full context và HTTP server thật

**`src/test/java/com/example/webfluxdemo/CatalogIntegrationTest.java`**

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CatalogIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void realHttpReadsSeedItem() {
        assertTrue(port > 0);

        client.get().uri("/api/items/a1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemDto.class)
            .isEqualTo(new ItemDto("a1", "Book", 10));
    }

    @Test
    void realHttpCreatesAndReadsBackItem() {
        EntityExchangeResult<ItemDto> result =
            client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("Marker", 5))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(ItemDto.class)
                .returnResult();

        ItemDto created = result.getResponseBody();
        assertNotNull(created);
        assertEquals("Marker", created.name());
        assertEquals(5, created.quantity());

        String url = "/api/items/" + created.id();
        assertEquals(url,
            result.getResponseHeaders().getFirst("Location"));

        client.get().uri(url)
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemDto.class)
            .isEqualTo(created);
    }

    @Test
    void realHttpMapsNotFoundError() {
        client.get().uri("/api/items/not-existent")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }
}
```

`RANDOM_PORT` khởi động embedded web server thật, `@LocalServerPort` nhận port được cấp, WebTestClient thực hiện HTTP loopback. `InMemoryCatalogService` là **bean thật** vì full context scan `@Service`. Test POST→GET chứng minh state thay đổi trong service; không có database thật, vì demo không dùng DB.

`@SpringBootTest` **mặc định webEnvironment=MOCK**, vì thế `@AutoConfigureWebTestClient` + `@SpringBootTest` đơn thuần chỉ nạp full ApplicationContext rồi test qua mock web exchange. Dùng `RANDOM_PORT` khi cần HTTP connector/netty socket thực.

Đừng dùng `@Transactional` trên random-port test rồi kỳ vọng mọi DB writes trong server đều rollback, bởi test thread và server execution/transaction boundaries khác nhau. Dùng data cleanup/test fixtures đúng.

## 8. Unit test Mono/Flux bằng StepVerifier

**`src/test/java/com/example/webfluxdemo/CatalogReactiveUnitTest.java`**

```java
package com.example.webfluxdemo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogReactiveUnitTest {

    private final InMemoryCatalogService service =
        new InMemoryCatalogService();

    @Test
    void monoEmitsItemAndCompletes() {
        StepVerifier.create(service.findById("a1"))
            .assertNext(item -> {
                assertEquals("a1", item.id());
                assertEquals("Book", item.name());
            })
            .verifyComplete();
    }

    @Test
    void missingMonoCompletesEmpty() {
        StepVerifier.create(service.findById("missing"))
            .verifyComplete();
    }

    @Test
    void fluxEmitsItemsInOrder() {
        StepVerifier.create(service.findAll())
            .expectNext(
                new ItemDto("a1", "Book", 10),
                new ItemDto("b2", "Pen", 20)
            )
            .verifyComplete();
    }

    @Test
    void createEmitsNewValue() {
        StepVerifier.create(service.create(
                new CreateItemRequest("Ruler", 2)))
            .assertNext(item -> {
                assertEquals("Ruler", item.name());
                assertEquals(2, item.quantity());
            })
            .verifyComplete();
    }

    @Test
    void virtualTimeAvoidsWaitingTwoHours() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofHours(1)).take(2))
            .expectSubscription()
            .thenAwait(Duration.ofHours(2))
            .expectNext(0L, 1L)
            .verifyComplete();
    }
}
```

`StepVerifier` xác minh **Reactive Streams signals**; nó không biết HTTP 201/404, URL hay JSON codec. Unit test `Mono.empty()` và web slice test 404 bổ sung nhau: mã trong controller/advice mới quyết định empty publisher được chuyển thành status HTTP nào.

### 8.1. Virtual time phải tạo publisher trong supplier

`StepVerifier.withVirtualTime(() -> Flux.interval(...))` giúp test Reactor time-based operators mà không chờ giờ thật. Tạo `Flux.interval` **trong** supplier, để virtual scheduler được cài trước khi publisher được dựng. Virtual time không làm nhanh network TCP, database, `Thread.sleep` hoặc event loop của remote service.

### 8.2. Thêm lỗi, demand và cancel

```java
Flux<Integer> failing = Flux.just(1, 2)
    .concatWith(Mono.error(
        new IllegalStateException("boom")));

StepVerifier.create(failing)
    .expectNext(1, 2)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "boom".equals(ex.getMessage()))
    .verify();
```

Snippet trên cần import `Mono`, `Flux`, `StepVerifier`. Không thể dùng HTTP status một mình để kiểm tín hiệu `onError` sau khi stream đã phát một số phần tử.

Demand:

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Cancel stream vô hạn:

```java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify();
```

Các tests trên chỉ kiểm operators được chỉ định; chúng không chứng minh toàn bộ HTTP streaming network tôn trọng backpressure/cleanup dưới tải. Test cancellation thật qua HTTP client/proxy và metrics nếu nghiệp vụ có streaming dài.

## 9. Chạy ứng dụng và 16 tests

Khởi chạy manual:

```bash
java -version
mvn spring-boot:run
```

Thử:

```bash
curl -i "http://localhost:8080/api/items/a1"
curl -i "http://localhost:8080/api/items/missing"
curl -i "http://localhost:8080/api/items"
curl -i -H "Content-Type: application/json" \
  -d '{"name":"Pencil","quantity":3}' \
  "http://localhost:8080/api/items"
curl -i -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/heartbeats"
```

GET `/api/items/a1` có response body kỳ vọng:

```json
{"id":"a1","name":"Book","quantity":10}
```

GET missing trả 404 với `ITEM_NOT_FOUND`, POST valid trả 201/Location đến ID mới, SSE phát `beat-1`, `beat-2`, `beat-3` và complete. Timestamp/headers/ID mới thay đổi theo runtime; không assert byte-for-byte một response chứa giá trị động.

Chạy suite:

```bash
mvn test
```

Hoặc `./mvnw test`/`mvnw.cmd test` nếu project có Maven Wrapper. Có thể chọn riêng:

```bash
mvn -Dtest=CatalogControllerSliceTest test
mvn -Dtest=CatalogIntegrationTest test
mvn -Dtest=CatalogReactiveUnitTest test
```

Theo các file ví dụ có **8 slice tests + 3 full HTTP integration tests + 5 reactive unit tests = 16 test methods**. Các phương thức được thiết kế để pass với đúng dependencies và runtime, **không phải lời tuyên bố đã chạy Maven trong một project người dùng**. Test xanh cũng không chứng minh p99 latency, CPU utilization, TLS hay DB production.

## 10. Security và test phạm vi reactive

Spring WebFlux security sử dụng `SecurityWebFilterChain` (khác Servlet `SecurityFilterChain`). `@WebFluxTest` không tự nạp custom security config tạo bean này, vì vậy test có thể đi qua default security khi có `spring-boot-starter-security` hoặc không có chính sách production như bạn tưởng.

Mô hình minh họa cho app có reactive security (không phải code thuộc demo catalog):

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là snippet cần Spring Security dependencies/imports như `Configuration`, `Bean`, `EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`. Để test đúng trong slice:

```java
@WebFluxTest(controllers = AdminController.class)
@Import(ReactiveSecurityConfig.class)
class AdminSecurityTest {
    // @MockitoBean AdminService
    // WebTestClient + reactive Spring Security Test
}
```

Có thể bổ sung test dependency `org.springframework.security:spring-security-test` và dùng `SecurityMockServerConfigurers.mockUser(...)`, `mockJwt(...)`, `csrf(...)`. Khi tự build WebTestClient bằng `bindToApplicationContext`, cần apply `SecurityMockServerConfigurers.springSecurity()` nếu muốn Spring Security test support hoạt động đúng. Cũng phải bảo đảm real reactive security filters đang nằm trong chain.

Không bật `csrf().disable()`/`permitAll()` chỉ để tests xanh. Nếu API dùng Bearer stateless và cookie sessions khác nhau, threat model CSRF cũng khác; test theo production contract. Nếu authorization thực thi bên trong service bị mock, cần **test service/integration với quyền thật** để kiểm tenant/object ownership.

Về dữ liệu bảo mật: chỉ dùng account/token giả trong tests; không log `Authorization`, cookies, session IDs, production API keys hoặc payload chứa PII. Không gửi request đến production endpoint ngoài phạm vi cho phép chỉ vì code test có `bindToServer`.

## 11. Functional routes và routing lỗi

Annotated controllers là mục tiêu chính của `@WebFluxTest`. Functional WebFlux routes được khai báo qua `RouterFunction<ServerResponse>`, không tự nhận bằng `@WebFluxTest(MyHandler.class)`.

Chọn một trong ba cách:

1. `WebTestClient.bindToRouterFunction(route)` để kiểm một functional route thuần.
2. `@Import(RouterConfig.class)` trong web test context nếu route/handler cần Spring beans.
3. `@SpringBootTest` khi cần toàn routing/security/filter configuration.

Một 404 trong slice chưa chắc production endpoint 404; kiểm route thực sự đã được đăng ký vào test context.

## 12. Khi nào cần integration với R2DBC, WebClient và proxy?

Một controller reactive trong production có thể gọi:

```text
Controller -> CatalogService -> R2DBC Repository
                           -> WebClient -> Remote HTTP service
                           -> Cache / message broker
```

Với `@WebFluxTest`, `CatalogService` thường bị mock, nên **không** kiểm connection pool, HTTP retry/timeout, remote JSON schema, SQL transaction hay Redis/Kafka serialization.

Cần các tầng bổ sung:

- **Unit/service StepVerifier:** transform, error classification, retry/cancel; mock reactive collaborators.
- **Repository/data integration:** R2DBC Testcontainers/test DB để kiểm query/transaction; không chạy SQL thật trong slice giả lập.
- **Outbound WebClient HTTP stub:** mock HTTP server cục bộ, inject base URL bằng cấu hình test/`@DynamicPropertySource` và kiểm actual requests/responses.
- **SpringBootTest RANDOM_PORT:** kiểm WebFlux HTTP server + full bean wiring; có thể thêm DB container/stub remote nếu thực sự yêu cầu.
- **E2E qua gateway:** TLS, proxy, WAF, auth provider, idle timeout, HTTP/2, SSE disconnect; chỉ ở môi trường được phê duyệt.

Nếu server test được mở trên random port và test class có `@Transactional`, transaction của test thread không đảm bảo rollback server-thread DB writes. Dùng setup/cleanup test data đúng boundary.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Lý do | Cách sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: CatalogService` | Service không thuộc web slice | `@MockitoBean` hoặc `@Import` đúng bean |
| Mockito `@Mock` có nhưng vẫn thiếu bean | @Mock không đăng ký Spring bean | Dùng @MockitoBean |
| `@WebFluxTest` import không tìm thấy sau Boot 4 | Test modules/package đổi | Dùng import/version docs tương ứng |
| Có MVC và WebFlux cùng classpath | Boot có thể chọn MVC | Kiểm starter + web-application-type |
| Controller test 401/403 bất ngờ | Security default/custom chain khác nhau | Import đúng SecurityWebFilterChain, test policy |
| Test functional route luôn 404 | `RouterFunction` chưa đăng ký | bindToRouterFunction hoặc import router |
| Stub mock trả null Publisher | `Mono/Flux` method chưa stub | `Mono.just/empty/error` đúng case |
| Test HTTP 200 nhưng JSON sai | Chỉ assert status | Assert content type/body/jsonPath |
| Validation test không trả 400 | Thiếu validator/`@Valid`/binding | Thêm starter-validation và correct annotations |
| JSON POST trả 415 | Sai Content-Type | Gửi `application/json` |
| `expectBodyList` treo | Stream không hoàn tất | returnResult + StepVerifier + cancel |
| HTTP 200 nhưng stream error | Headers đã commit, Flux lỗi sau đó | Test stream error signals/cancel |
| `@SpringBootTest` không chạy real HTTP | Default MOCK | Chọn RANDOM_PORT |
| Tests leak state/context | Cached Spring context, singleton mutable | Isolate data/reset fixtures |
| Test transaction không rollback real HTTP writes | Test/server thread khác transaction | Cleanup database fixtures |
| Test pass nhưng Netty block dưới tải | Mock exchange không đo event loop | Instrument real server, không block reactive pipeline |
| 16 functional tests xanh được gọi “10.000 RPS” | Không có benchmark | Load test có phép + metrics tail latency |

## 14. Checklist trước khi chấp nhận test suite

- [ ] Đúng stack Spring WebFlux, dependency tree không vô tình chọn MVC.
- [ ] Đúng Spring Boot version/package cho `@WebFluxTest`, `@MockitoBean`, `@AutoConfigureWebTestClient`.
- [ ] Biết test dùng mock exchange hay real network; không gọi slice test là E2E.
- [ ] Services/repositories được mock/import đúng scope; tránh broad component scan.
- [ ] Có HTTP method/URI, JSON media type, status/body/header assertions.
- [ ] Có validation 400, 404 domain advice, 201 Location, 415 content type.
- [ ] Có StepVerifier tests cho Mono/Flux signals, error/cancel/virtual time khi cần.
- [ ] Với SSE/NDJSON, dùng returnResult và cancellation, không buffer infinite stream.
- [ ] Có security tests dùng real reactive policy, không disable auth/CSRF để test xanh.
- [ ] Có full HTTP random-port tests cho connector/real beans và integration khi cần.
- [ ] Functional RouterFunction được đăng ký đúng trong test.
- [ ] Có tests riêng cho database/outbound HTTP/caching nếu business phụ thuộc vào chúng.
- [ ] Tests không phụ thuộc cổng 8080 cố định, method order hoặc state chia sẻ giữa classes.
- [ ] HTTP server real transaction được cleanup đúng; không giả định test @Transactional rollback được.
- [ ] Không gọi block/subscribe thủ công trong WebFlux controller.
- [ ] Không sử dụng production secrets, data thật hoặc load test không được phép.
- [ ] Kết luận QA phản ánh **điều đã thực sự kiểm chứng**, không suy ra performance capacity.

## 15. Câu hỏi tự kiểm tra

**1. `@WebFluxTest` có mở Netty TCP port thật không?**  
Không. Nó test mock WebFlux exchange; dùng RANDOM_PORT nếu cần real HTTP.

**2. Vì sao `CatalogService` không tự có trong test slice?**  
Vì `@Service` không được scan trong web slice. Dùng `@MockitoBean`.

**3. `WebTestClient.bindToServer` và `bindToController` khác nhau?**  
Cái đầu gọi server qua HTTP thật; cái sau dựng mock web handler.

**4. Một test `Mono.empty()` pass có chứng minh HTTP 404 không?**  
Không. HTTP status do controller/advice quyết định; cần WebTestClient test.

**5. Khi nào dùng `StepVerifier`?**  
Khi kiểm onNext/onComplete/onError, cancel/demand/time-based publisher.

**6. Infinite SSE có nên dùng `expectBodyList`?**  
Không. Dùng `returnResult` và StepVerifier, kết thúc bằng `thenCancel()`.

**7. `@SpringBootTest` mặc định có HTTP server thật không?**  
Không, MOCK là mặc định; RANDOM_PORT khởi động server.

**8. Vì sao `@WebFluxTest` không tự kiểm custom security chain?**  
Custom `SecurityWebFilterChain` bean có thể không được slice nạp; import đúng hoặc full context.

**9. Có test được RouterFunction qua `WebTestClient` không?**  
Có, dùng `bindToRouterFunction` hoặc import route config trong context.

**10. Virtual time có làm một remote HTTP 1 giờ chạy tức thì không?**  
Không. Nó chỉ điều khiển Reactor scheduler cho time operators phù hợp.

**11. Spring MVC + WebFlux dependencies, Boot thường chọn cái nào?**  
MVC ưu tiên mặc định; phải kiểm stack thực đang chạy.

**12. 16 tests pass có chứng minh API đạt p99 100 ms không?**  
Không; cần benchmark đo hiệu năng riêng, cùng environment/load và SLO.

## 16. Tài liệu chính thức

- Spring Boot 3.5 — **Testing Spring Boot Applications**, WebFluxTest/SpringBootTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 Javadoc — **WebFluxTest**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework 6.2 — **MockitoBean**: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — **WebFlux @RequestBody**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — **Functional WebFlux routing**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Project Reactor — **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Security — **Reactive Security testing**: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Boot 3.5.16 release and OSS support note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** `@WebFluxTest` là **web-layer slice** có mock request/response và các collaborators được mock, không phải full application test. `WebTestClient` là test client có nhiều cách bind, từ mock controller/context/router đến server HTTP thật. `StepVerifier` kiểm Publisher signals và streaming lifecycle. Với một reactive endpoint quan trọng, hãy kết hợp **unit StepVerifier + @WebFluxTest HTTP contract + @SpringBootTest(RANDOM_PORT) integration**, và tách riêng security/database/outbound API/proxy tests theo phạm vi rủi ro.