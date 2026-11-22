# Spring WebFlux — Tích hợp RouterFunction bean với DispatcherHandler

## 1. Vấn đề và mục tiêu

Spring WebFlux có hai phong cách khai báo HTTP endpoints:

- **Annotated controller:** `@RestController`, `@GetMapping`, `@RequestBody`.
- **Functional endpoint (WebFlux.fn):** `RouterFunction<ServerResponse>` chọn route, `HandlerFunction<ServerResponse>` xử lý `ServerRequest` và tạo `Mono<ServerResponse>`.

Hai phong cách **có thể chạy cùng một `DispatcherHandler` và một HTTP server**. Trong ứng dụng Spring Boot WebFlux, khai báo `RouterFunction<?>` là Spring bean thường đã đủ; các WebFlux infrastructure beans tự phát hiện và kết hợp routers.

Bài này giải thích:

1. `DispatcherHandler` và ba loại delegates `HandlerMapping`, `HandlerAdapter`, `HandlerResultHandler`.
2. Ba thành phần của functional endpoints: `RouterFunctionMapping`, `HandlerFunctionAdapter`, `ServerResponseResultHandler`.
3. Cách Boot nhận các `RouterFunction` beans; vì sao không cần tự tạo `DispatcherHandler` hoặc gọi `RouterFunctions.toHttpHandler`.
4. Nhiều router beans, composition và **first-match routing order**.
5. Việc functional và annotated endpoints cùng tồn tại, khác biệt giữa router-order và handler-mapping-order.
6. Cách tổ chức handlers/services, dependency injection, filters, security/CORS, error handling.
7. Các lỗi phổ biến khi kết hợp `@EnableWebFlux`, Servlet WebMvc.fn, route prefixes, wildcard routes.
8. Ví dụ Java 17 / Spring Boot 3.5.0 / Spring Framework 6.2, Maven, WebTestClient tests và các câu hỏi luyện tập.

**Ngữ cảnh:** Functional WebFlux. Không nhầm package reactive `org.springframework.web.reactive.function.server` với Servlet `org.springframework.web.servlet.function`.

## 2. RouterFunction và HandlerFunction

### 2.1. HandlerFunction

Functional handler nhận một `ServerRequest`, trả về một `Mono<ServerResponse>`:

~~~java
Mono<ServerResponse> hello(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("Hello WebFlux");
}
~~~

Đây là code fragment, không phải một file Java chạy độc lập. `ServerRequest` có các API như `pathVariable("id")`, `queryParam("q")`, `headers()`, `bodyToMono(BookInput.class)`, `bodyToFlux(...)`, `principal()` và metadata khác.

`ServerResponse` là một mô tả immutable của status, headers, cookies và cách ghi body; framework thực thi việc encode/write, không phải HandlerFunction tự quản lý socket.

### 2.2. RouterFunction

Về bản chất, `RouterFunction<T>` kiểm tra một `ServerRequest` rồi trả `Mono<HandlerFunction<T>>` nếu match hoặc `Mono.empty()` nếu không match.

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().bodyValue("Hello"))
                .build();
~~~

Muốn router này được Spring Boot phát hiện, trả nó từ `@Bean`:

~~~java
@Configuration
class RouterConfiguration {
    @Bean
    RouterFunction<ServerResponse> helloRouter() {
        return RouterFunctions.route()
                .GET("/hello", req ->
                        ServerResponse.ok().bodyValue("Hello"))
                .build();
    }
}
~~~

Khi `RouterConfiguration` nằm trong component scan, Boot đưa bean vào ApplicationContext; không cần viết thêm adapter/mapping.

### 2.3. Functional so với annotated

Annotated:

~~~java
@RestController
class HealthController {
    @GetMapping("/status")
    Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Functional:

~~~java
@Bean
RouterFunction<ServerResponse> statusRouter() {
    return RouterFunctions.route()
            .GET("/status", req ->
                    ServerResponse.ok()
                            .bodyValue(Map.of("status", "ok")))
            .build();
}
~~~

Đây là hai phương án **thay thế**; không nên khai báo cả hai cho cùng GET /status trừ khi có kế hoạch ưu tiên được test. Functional handler chủ động đọc ServerRequest và build ServerResponse; annotated controller dùng argument resolvers/return value handlers của framework.

## 3. DispatcherHandler xử lý request thế nào?

### 3.1. Luồng chung

~~~text
Browser or HTTP client
        |
        v
Reactive HTTP server (thường Reactor Netty)
        |
        v
WebHttpHandlerBuilder-created HttpHandler
        |
        v
WebFilter/WebExceptionHandler chain
        |
        v
DispatcherHandler
        |
        +--> HandlerMapping: tìm handler
        |
        +--> HandlerAdapter: gọi handler
        |
        +--> HandlerResultHandler: ghi response
        |
        v
HTTP status + headers + body
~~~

`DispatcherHandler` là front controller của WebFlux, **không phải DispatcherServlet**. Nó lấy các delegate beans từ ApplicationContext và không tự biết chi tiết về từng RouterFunction hay annotation.

| Component | Mục đích |
| --- | --- |
| `HandlerMapping` | Chọn handler phù hợp theo request |
| `HandlerAdapter` | Gọi handler đã chọn |
| `HandlerResult` | Bao kết quả và context của handler |
| `HandlerResultHandler` | Chọn cách render response và hoàn tất ghi HTTP |

Theo tài liệu Spring Framework 6.2, `DispatcherHandler` hỏi `HandlerMapping` beans theo thứ tự và **sử dụng kết quả match đầu tiên**.

### 3.2. Bộ ba hạ tầng WebFlux.fn

| Class | Vai trò |
| --- | --- |
| `RouterFunctionMapping` | Khám phá, sắp xếp, kết hợp RouterFunction beans và route request |
| `HandlerFunctionAdapter` | Cho phép DispatcherHandler gọi một HandlerFunction |
| `ServerResponseResultHandler` | Ghi Mono<ServerResponse> bằng ServerResponse.writeTo(...) |

Flow:

~~~text
GET /api/fn/books/42
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping
    |
    v
RouterFunction.route(request)
    |
    v
HandlerFunction for GET /api/fn/books/{id}
    |
    v
HandlerFunctionAdapter
    |
    v
Mono<ServerResponse>
    |
    v
ServerResponseResultHandler -> codecs -> HTTP response
~~~

Nếu composite router không match, `RouterFunctionMapping` có thể trả không có handler để DispatcherHandler thử mapping khác.

### 3.3. Annotated components khác

Annotated controllers có `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter`; `@ResponseBody`/`@RestController` được `ResponseBodyResultHandler` xử lý. `ServerResponseResultHandler` xử lý ServerResponse functional. Tất cả làm việc trong cùng một DispatcherHandler nhờ contract delegate chung.

**Không** tự gọi `ServerResponse.writeTo(...)` trong HandlerFunction thông thường; để framework quản lý codecs, write lifecycle và error handling.

## 4. Spring Boot tự cấu hình những gì?

Dùng `spring-boot-starter-webflux` để Spring Boot 3.5 tạo reactive HTTP runtime, WebFlux DispatcherHandler, handler mappings/adapters/result handlers, codecs và các tiện ích Boot.

**Không cần**:

- Tự đăng ký RouterFunctionMapping.
- Tự đăng ký HandlerFunctionAdapter/ServerResponseResultHandler.
- Tự tạo thêm DispatcherHandler.
- Tự biến router bean thành HttpHandler.
- Gắn `@EnableWebFlux` chỉ để chạy functional routing.

Với Boot, nếu muốn thêm CORS/formatters/codecs, dùng `@Configuration implements WebFluxConfigurer` **không gắn @EnableWebFlux**, để giữ các Boot-specific WebFlux auto-config conveniences.

### 4.1. @EnableWebFlux dùng trong trường hợp nào?

Trong Spring Framework non-Boot Java configuration, `@EnableWebFlux` nhập các infrastructure configurations. Nếu dùng nó trong Boot, bạn đang chọn kiểm soát WebFlux config sâu hơn; một số Boot auto-configuration có thể lùi lại và static/codec/error defaults cần được tự kiểm. Không dùng cho bài này.

### 4.2. Cẩn thận starter-web

Nếu classpath có đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường chọn MVC theo mặc định. Khi đó `RouterFunction<ServerResponse>` của WebFlux sẽ không chạy trong một WebFlux DispatcherHandler như mong đợi. Để demo reactive, chỉ dùng WebFlux starter.

### 4.3. Sai import là lỗi thường gặp

WebFlux.fn:

~~~java
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

WebMvc.fn:

~~~java
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;
~~~

Chữ ký và lifecycle khác; hãy kiểm IDE auto-import.

## 5. Nhiều RouterFunction beans

### 5.1. RouterFunctionMapping khám phá và compose

Tài liệu Spring nói rằng RouterFunctionMapping nhận một hoặc nhiều bean `RouterFunction<?>`, **sắp xếp** chúng và kết hợp bằng `RouterFunction.andOther`.

Ví dụ:

~~~text
catalogRoutes  -> GET /api/catalog
orderRoutes    -> GET /api/orders
systemRoutes   -> GET /internal/ping
~~~

Một WebFlux DispatcherHandler đủ để phục vụ tất cả. Khi các paths không trùng, bean ordering ít ảnh hưởng; khi overlaps, thứ tự quyết định outcome.

### 5.2. Specific trước variable

Sai:

~~~java
return RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/latest", handler::latest)
        .build();
~~~

GET /api/books/latest có thể vào byId với id="latest". Đúng:

~~~java
return RouterFunctions.route()
        .GET("/api/books/latest", handler::latest)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

**Functional routes được xét theo thứ tự**, không sử dụng thuật toán “most specific wins” của annotated controller mappings trong cùng router builder.

### 5.3. Thứ tự nhiều beans và @Order

Khi mỗi bean có chồng path hoặc predicate, đừng dựa vào tên file, registration order hoặc giả định @Order áp dụng theo cùng cách trong mọi version. Nếu thực sự cần precedence:

- Đặt các overlapping routes trong **cùng một builder**.
- Hoặc compose rõ bằng `andOther`/`add`.
- Hoặc chọn sorting contract được Framework version hỗ trợ và viết HTTP integration test.
- Tốt nhất thiết kế **một owner cho mỗi method/path**.

### 5.4. Kết hợp tường minh

~~~java
RouterFunction<ServerResponse> first =
        RouterFunctions.route()
                .GET("/api/a", handler::a)
                .build();

RouterFunction<ServerResponse> second =
        RouterFunctions.route()
                .GET("/api/b", handler::b)
                .build();

RouterFunction<ServerResponse> combined =
        first.andOther(second);
~~~

Code fragment cần handler methods. Composite xét router thứ nhất rồi fallback sang router thứ hai nếu không match. Builder cũng hỗ trợ `add(second)` khi cần kết hợp.

### 5.5. Nested router

~~~java
return RouterFunctions.route()
        .path("/api/books", b -> b
                .GET("/latest", handler::latest)
                .GET("/{id}", handler::byId)
                .POST(handler::create))
        .build();
~~~

Nesting giảm lặp path prefix; route order vẫn được giữ.

## 6. Functional và annotated controller có thể chạy cùng nhau

Giả sử:

~~~java
@RestController
class AnnotatedStatus {
    @GetMapping("/api/annotated/status")
    Mono<Map<String, String>> status() {
        return Mono.just(Map.of("mode", "annotated"));
    }
}
~~~

và:

~~~java
@Bean
RouterFunction<ServerResponse> functionalStatus() {
    return RouterFunctions.route()
            .GET("/api/fn/status", request ->
                    ServerResponse.ok()
                            .bodyValue(Map.of("mode", "functional")))
            .build();
}
~~~

Hai routes không xung đột, có cùng WebFlux DispatcherHandler.

**Nếu cùng GET /api/status xuất hiện ở cả hai**, DispatcherHandler chọn HandlerMapping match đầu tiên dựa vào mapping order. Không nên hứa một loại handler luôn thắng. Cần kiểm HandlerMapping order thực tế và có regression test, hoặc loại bỏ overlap.

Ba tầng chọn handler cần phân biệt:

1. **Trong functional router:** first matching request predicate wins.
2. **Giữa các HandlerMapping:** first matching handler mapping wins.
3. **Trong annotated RequestMappingHandlerMapping:** mapping specificity/conditions chọn method theo annotation matching algorithm.

`WebFluxConfigurer#configurePathMatching(...).addPathPrefix` thường dùng với **annotated controller type predicate**; không mặc định thêm prefix cho tất cả functional RouterFunction paths.

## 7. HandlerFilterFunction và WebFilter

Functional route builder có `filter`, `before`, `after`:

~~~java
return RouterFunctions.route()
        .GET("/api/books", handler::list)
        .filter((request, next) ->
                next.handle(request)
                        .doOnError(error -> metrics.increment()))
        .build();
~~~

Đây là fragment, metrics chưa định nghĩa. Filter này áp dụng cho router scope, không tự động áp các @RestController hoặc RouterFunction beans khác.

Một filter có thể short-circuit:

~~~java
.filter((request, next) -> {
    if (maintenance.isActive()) {
        return ServerResponse.status(503)
                .bodyValue(Map.of("code", "MAINTENANCE"));
    }
    return next.handle(request);
})
~~~

Phân biệt:

| Cơ chế | Phạm vi |
| --- | --- |
| `HandlerFilterFunction` | Các HandlerFunction trong router/nested route được filter |
| `WebFilter` | WebHandler chain, có thể bao annotated + functional |
| `SecurityWebFilterChain` | Reactive authentication/authorization |
| `CorsWebFilter` | CORS cho WebFlux functional endpoints theo tài liệu Spring |

Router filter không phải Spring Security policy. Trong ứng dụng có frontend khác origin, CORS preflight cần allowlist origins/methods/headers và thứ tự phù hợp với Security; CORS không thay auth/CSRF.

## 8. Lỗi và HTTP status trong functional handlers

### 8.1. Không dựa hoàn toàn vào @RestControllerAdvice

`@RestControllerAdvice` thuộc annotated controller exception resolution; không mặc định nó xử lý mọi lỗi từ HandlerFunction. Một route filter có thể xử lý domain input error:

~~~java
.filter((request, next) ->
        next.handle(request)
                .onErrorResume(BadInputException.class,
                        ex -> ServerResponse.badRequest()
                                .bodyValue(Map.of(
                                        "code", "INVALID_INPUT"))))
~~~

Với HTTP API public, nên dùng `ProblemDetail` RFC 9457, đặt HTTP status và body status tương thích, không echo exception message hoặc secrets.

### 8.2. No-match vs domain not-found

- `GET /api/fn/books/999` match router nhưng store không có record → domain 404 với `BOOK_NOT_FOUND`.
- `GET /api/fn/unknown` không match bất kỳ handler nào → framework 404, có thể có body khác.

Một HTTP 404 không đủ biết nguồn lỗi; app cần domain code nếu client có logic khác nhau.

### 8.3. Accept và Content-Type predicates

Nếu functional route chứa `RequestPredicates.accept(APPLICATION_JSON)` nhưng client gửi media type khác, router có thể **không match**, khiến response cuối là 404 hoặc error khác tùy mappings. Đừng giả định mọi mismatch luôn 406. Tương tự Content-Type predicate không tự bảo đảm 415 trong mọi topology. Test chính xác method/path/predicates/codecs.

### 8.4. Lỗi khi response đã committed

Khi SSE/stream đã gửi status 200 và body bytes, không thể đổi thành HTTP 500 JSON mới trên cùng response. Nếu channel còn usable, có thể gửi SSE error event theo application protocol; nếu client ngắt transport, cancel/cleanup/log. `DispatcherHandler`/`ServerResponseResultHandler` không thể đảo ngược HTTP headers đã gửi.

## 9. Dự án Maven chạy độc lập

Dự án dùng **Java 17 + Spring Boot 3.5.0 + Spring WebFlux** với:

- Hai bean RouterFunction: `bookRoutes` và `systemRoutes`.
- Một annotated controller `AnnotatedPingController`.
- BookHandler được Spring inject BookStore.
- Route specific `/latest` nằm trước variable `/{id}`.
- POST JSON tạo Book trong in-memory Map, trả 201 + relative Location.
- HandlerFilterFunction map invalid input thành ProblemDetail HTTP 400.
- WebTestClient integration tests xác minh DispatcherHandler/RouterFunctionMapping và endpoints.

### 9.1. Cấu trúc

~~~text
functional-router-demo/
├── pom.xml
└── src/
    ├── main/java/demo/FunctionalRouterApplication.java
    └── test/java/demo/FunctionalRouterTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>functional-router-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
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

### 9.3. FunctionalRouterApplication.java

Đặt toàn bộ Java sau trong `src/main/java/demo/FunctionalRouterApplication.java`. Chỉ một top-level public class; những records/classes khác là package-private.

~~~java
package demo;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FunctionalRouterApplication {
    public static void main(String[] args) {
        SpringApplication.run(FunctionalRouterApplication.class, args);
    }
}

record Book(long id, String title) {
}
record NewBook(String title) {
}
class BadInputException extends RuntimeException {
}

@Service
class BookStore {
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(10);

    BookStore() {
        books.put(1L, new Book(1L, "Spring WebFlux"));
    }

    Mono<Book> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    Mono<Book> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = ids.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}

@Component
class BookHandler {
    private final BookStore store;

    BookHandler(BookStore store) {
        this.store = store;
    }

    Mono<ServerResponse> latest(ServerRequest request) {
        return store.find(1L)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book));
    }

    Mono<ServerResponse> byId(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException exception) {
            return Mono.error(new BadInputException());
        }

        if (id <= 0) {
            return Mono.error(new BadInputException());
        }

        return store.find(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(problem(HttpStatus.NOT_FOUND,
                        "BOOK_NOT_FOUND", "Không tìm thấy sách"));
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(NewBook.class)
                .switchIfEmpty(Mono.error(new BadInputException()))
                .flatMap(input -> {
                    if (input.title() == null
                            || input.title().isBlank()) {
                        return Mono.error(new BadInputException());
                    }
                    return store.create(input.title())
                            .flatMap(book -> ServerResponse
                                    .created(URI.create(
                                            "/api/fn/books/" + book.id()))
                                    .contentType(
                                            MediaType.APPLICATION_JSON)
                                    .bodyValue(book));
                });
    }

    Mono<ServerResponse> badInput() {
        return problem(HttpStatus.BAD_REQUEST,
                "INVALID_INPUT", "Dữ liệu đầu vào không hợp lệ");
    }

    private Mono<ServerResponse> problem(
            HttpStatus status, String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                status, detail);
        p.setProperty("code", code);
        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(p);
    }
}

@Configuration(proxyBeanMethods = false)
class FunctionalRoutes {
    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler books) {
        return RouterFunctions.route()
                .GET("/api/fn/books/latest", books::latest)
                .GET("/api/fn/books/{id}", books::byId)
                .POST("/api/fn/books", books::create)
                .filter((request, next) ->
                        next.handle(request)
                                .onErrorResume(
                                        BadInputException.class,
                                        error -> books.badInput()))
                .build();
    }

    @Bean
    RouterFunction<ServerResponse> systemRoutes() {
        return RouterFunctions.route()
                .GET("/api/fn/ping", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(Map.of(
                                        "style", "functional",
                                        "ok", true)))
                .build();
    }
}

@RestController
class AnnotatedPingController {
    @GetMapping(path = "/api/annotated/ping",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Map<String, Object>> ping() {
        return Mono.just(Map.of(
                "style", "annotated", "ok", true));
    }
}
~~~

### 9.4. Giải thích code

- Hai RouterFunction beans có disjoint paths, không phụ thuộc bean-order.
- RouterFunctionMapping khám phá hai beans; HandlerFunctionAdapter gọi functional handlers; ServerResponseResultHandler encode/write.
- `AnnotatedPingController` chạy trong cùng DispatcherHandler qua RequestMappingHandlerMapping/Adapter.
- `/latest` trước `/{id}` để không parse chữ "latest" thành long.
- `BookHandler` là @Component singleton nhưng không giữ mutable ServerRequest trong field.
- `BookStore` dùng AtomicLong + ConcurrentHashMap minh họa, không có database/transactions.
- `Mono.defer` và `Mono.fromSupplier` giúp tác vụ được thực hiện khi có subscription.
- Router-specific filter chỉ bắt `BadInputException` của book routes; không tự bắt lỗi annotated/security.
- `ProblemDetail` và HTTP status được xây an toàn, không trả exception message.
- `ServerResponse.created(URI.create(...))` trả 201 Location relative URL, tránh hardcode internal backend origin.
- Không thêm @EnableWebFlux hoặc tự tạo infrastructure beans.
- Demo không có authentication, CORS hay persistence; production phải thiết kế riêng.

### 9.5. Chạy

~~~bash
mvn spring-boot:run
~~~

Functional:

~~~bash
curl -i http://localhost:8080/api/fn/ping
curl -i http://localhost:8080/api/fn/books/latest
curl -i http://localhost:8080/api/fn/books/1
~~~

Ví dụ body:

~~~json
{"id":1,"title":"Spring WebFlux"}
~~~

Annotated:

~~~bash
curl -i http://localhost:8080/api/annotated/ping
~~~

Body:

~~~json
{"style":"annotated","ok":true}
~~~

Lỗi:

~~~bash
curl -i http://localhost:8080/api/fn/books/999
curl -i http://localhost:8080/api/fn/books/not-a-number
~~~

Kỳ vọng 404/BOOK_NOT_FOUND và 400/INVALID_INPUT tương ứng.

POST:

~~~bash
curl -i -X POST http://localhost:8080/api/fn/books \
  -H 'Content-Type: application/json' \
  --data '{"title":"Reactive Book"}'
~~~

Lần tạo đầu có thể trả:

~~~http
HTTP/1.1 201 Created
Location: /api/fn/books/11
Content-Type: application/json

{"id":11,"title":"Reactive Book"}
~~~

ID tăng qua requests; đừng hardcode 11 trong tests.

## 10. WebTestClient integration tests

Tạo `src/test/java/demo/FunctionalRouterTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.DispatcherHandler;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.support.HandlerFunctionAdapter;
import org.springframework.web.reactive.function.server.support.RouterFunctionMapping;
import org.springframework.web.reactive.function.server.support.ServerResponseResultHandler;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FunctionalRouterTest {
    @Autowired WebTestClient http;
    @Autowired ApplicationContext context;

    @Test
    void webfluxInfrastructureIsManagedBySpring() {
        assertNotNull(context.getBean(DispatcherHandler.class));
        assertNotNull(context.getBean(RouterFunctionMapping.class));
        assertNotNull(context.getBean(HandlerFunctionAdapter.class));
        assertNotNull(context.getBean(ServerResponseResultHandler.class));
        assertTrue(context.getBeansOfType(RouterFunction.class)
                .size() >= 2);
    }

    @Test
    void functionalAndAnnotatedBothRespond() {
        http.get().uri("/api/fn/ping").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.style").isEqualTo("functional");

        http.get().uri("/api/annotated/ping").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.style").isEqualTo("annotated");
    }

    @Test
    void exactRouteWinsOverVariableRoute() {
        http.get().uri("/api/fn/books/latest").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Spring WebFlux");
    }

    @Test
    void variableRouteWorks() {
        http.get().uri("/api/fn/books/1").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void missingBookReturnsDomain404() {
        http.get().uri("/api/fn/books/999999").exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.code").isEqualTo("BOOK_NOT_FOUND");
    }

    @Test
    void invalidBookIdReturns400() {
        http.get().uri("/api/fn/books/abc").exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void createReturns201WithLocation() {
        http.post().uri("/api/fn/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewBook("Test"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueMatches(
                        HttpHeaders.LOCATION,
                        "/api/fn/books/[0-9]+")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test");
    }

    @Test
    void invalidPostReturns400() {
        http.post().uri("/api/fn/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewBook(" "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void unmatchedPathReturns404() {
        http.get().uri("/api/fn/no-such-route").exchange()
                .expectStatus().isNotFound();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Đây là Spring Boot HTTP integration test: kiểm exact beans trong ApplicationContext và routing thật qua server, không chỉ gọi phương thức controller trực tiếp.

### 10.1. Vì sao không chỉ bindToRouterFunction?

WebTestClient có:

~~~java
WebTestClient client =
        WebTestClient.bindToRouterFunction(router).build();
~~~

Cách này thích hợp **isolated route tests** và chạy nhanh, nhưng không tự chứng minh RouterFunction bean được Spring Boot phát hiện, nhiều beans được RouterFunctionMapping compose đúng hay annotated controller cùng DispatcherHandler. Vì bài học nhắm bean-integration, `@SpringBootTest(RANDOM_PORT)` là một kiểm thử quan trọng.

## 11. Tình huống gỡ lỗi

| Triệu chứng | Kiểm tra |
| --- | --- |
| Router bean có nhưng 404 | Component scan, package, exact route/predicates |
| Không thấy RouterFunctionMapping | App type MVC, sai WebFlux dependency |
| Import RouterFunction sai | `web.servlet.function` vs `web.reactive.function.server` |
| `/latest` bị parse long | Variable route trước static route |
| Router A chiếm Router B | Predicate overlap và bean composition ordering |
| Annotated thắng functional trên same path | HandlerMapping order; nên tránh overlap |
| JSON body fail | Jackson/codec configuration/media type |
| Handler filter không chạy ở annotated route | Phạm vi HandlerFilterFunction chỉ theo router |
| @RestControllerAdvice không bắt functional error | Dùng route filter/WebExceptionHandler đúng tầng |
| CORS preflight sai | CorsWebFilter/Security OPTIONS policy |
| Static resources biến mất sau @EnableWebFlux | Boot auto-configuration đã thay đổi |
| Blocking DB kéo chậm toàn app | Netty event-loop bị block |
| bindToRouterFunction pass nhưng Boot app 404 | Test isolated không xác minh bean discovery |
| SSE lỗi sau 200 nhưng không thể gửi 500 | Response đã committed |

## 12. Bài tập

**Bài 1.** Mô tả ba bước RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler và trách nhiệm DispatcherHandler.

**Bài 2.** Đăng ký hai bean RouterFunction ở hai module khác nhau với paths không trùng; kiểm cả hai bằng WebTestClient.

**Bài 3.** Thêm @RestController trong cùng ứng dụng, chứng minh cả hai phong cách dùng một server/DispatcherHandler.

**Bài 4.** Đặt variable route trước static route, quan sát GET /books/latest, sau đó sửa và viết test.

**Bài 5.** Tạo hai RouterFunction beans có method/path overlap và đo precedence thực tế; refactor thành một owner.

**Bài 6.** Compose router qua andOther/builder.add thay vì tạo duplicate broad routes.

**Bài 7.** Dùng HandlerFilterFunction để map BadInputException thành 400 ProblemDetail; kiểm filter không áp vào annotated controller.

**Bài 8.** So sánh WebFilter và HandlerFilterFunction về phạm vi, cross-cutting logging và Security.

**Bài 9.** Tạo một functional POST JSON handler, kiểm request Content-Type, body decode và lỗi.

**Bài 10.** Thêm CORS preflight qua CorsWebFilter, allowlist SPA origin; giải thích vì sao không thay authorization.

**Bài 11.** So sánh bindToRouterFunction với SpringBootTest RANDOM_PORT. Điều gì chỉ integration test mới xác minh được?

**Bài 12.** Thử gọi RouterFunctions.toHttpHandler trực tiếp trong custom adapter; nêu các config/filters/codecs cần quản lý.

**Bài 13.** Tạo một wildcard route rồi test nó không chiếm annotated/static endpoints.

**Bài 14.** Chuyển blocking legacy call sang Mono.fromCallable + boundedElastic, kiểm event-loop không bị block.

## 13. Checklist production

- [ ] Spring Boot dùng reactive WebFlux đúng package và dependencies.
- [ ] RouterFunction beans thực sự xuất hiện trong ApplicationContext.
- [ ] DispatcherHandler, RouterFunctionMapping, HandlerFunctionAdapter, ServerResponseResultHandler do Framework quản lý.
- [ ] Functional và annotated routes có path ownership rõ, không overlap tùy tiện.
- [ ] Trong functional builder, static/specific routes được xét trước variable/wildcard.
- [ ] Mọi route methods/predicates/Accept/Content-Type có integration tests.
- [ ] Handler có DI, không lưu request-specific mutable state trong singleton.
- [ ] Handler trả Publisher, không gọi subscribe() fire-and-forget cho request work.
- [ ] HTTP status/ErrorResponse/ProblemDetail an toàn, không leak stacktraces/secrets.
- [ ] SecurityWebFilterChain và CorsWebFilter có scope/order phù hợp.
- [ ] Reactive I/O không bị blocking, có timeout/backpressure/cancellation policy.
- [ ] Stream sau commit không cố thay HTTP status/headers.
- [ ] Static resources và actuator/health mappings không bị wildcard chiếm.
- [ ] WebTestClient qua HTTP server/Boot context xác minh bean discovery và annotated coexistence.
- [ ] Metrics dùng low-cardinality route templates, logs có safe correlation IDs.

## 14. Ghi nhớ

- `RouterFunctionMapping` nhận Spring-managed RouterFunction beans, order/compose chúng và tìm handler.
- `HandlerFunctionAdapter` gọi functional handler; `ServerResponseResultHandler` ghi ServerResponse.
- Functional và annotated controllers dùng **cùng DispatcherHandler**, nhưng HandlerMappings/Adapters khác nhau.
- Functional builder dùng **first match**, DispatcherHandler dùng **first matching HandlerMapping**; annotated selection dùng specificity.
- Không cần `@EnableWebFlux` hay custom HttpHandler để chạy RouterFunction bean với Boot.
- Không dựa vào incidental bean order khi có overlapping routes; tránh overlap hoặc compose có test.
- HandlerFilterFunction khác WebFilter/SecurityWebFilterChain về scope.
- Isolated router test không chứng minh Spring Boot bean discovery; dùng HTTP WebTestClient integration test.
- Thiết kế reactive publisher/error/cancellation và bảo vệ thông tin nhạy cảm ngay từ đầu.

## 15. Tài liệu tham khảo

- [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html).
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html).
- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html).
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).
- [RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/RouterFunctionMapping.html).
- [HandlerFunctionAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/HandlerFunctionAdapter.html).
- [ServerResponseResultHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/ServerResponseResultHandler.html).
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/).
