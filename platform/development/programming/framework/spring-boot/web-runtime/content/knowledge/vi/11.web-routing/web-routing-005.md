# RouterFunction, HandlerFunction và ServerResponse trong WebFlux.fn

## 1. WebFlux.fn là gì?

Spring WebFlux cung cấp hai phong cách xây dựng HTTP API: annotated controllers (@RestController, @GetMapping, ...) và **functional endpoints**, gọi là **WebFlux.fn**. Functional endpoints đặt định tuyến, logic xử lý và hợp đồng phản hồi trong các hàm/đối tượng Java thay vì gắn annotation HTTP lên từng controller method. Cả hai cùng sử dụng runtime Spring WebFlux, HTTP codecs, WebFilter và cơ chế reactive của Project Reactor.

Ba trụ cột của WebFlux.fn:

- **RouterFunction<ServerResponse>**: nhận ServerRequest, kiểm tra các điều kiện khớp HTTP request và chọn một HandlerFunction; nếu không khớp, kết quả routing trống.
- **HandlerFunction<ServerResponse>**: nhận ServerRequest và trả **Mono<ServerResponse>**, thường gọi service/repository rồi tạo HTTP response.
- **ServerResponse**: mô tả status, header, cookie, media type và body mà Spring WebFlux sẽ gửi về client.

**ServerRequest** là đối tượng đầu vào của handler, cung cấp method, path, header, query parameter, path variable, request body và ngữ cảnh request.

Mục tiêu sau bài học: hiểu hợp đồng của ba thành phần; thiết kế GET/POST REST endpoints; dùng RequestPredicate, nesting và filter; phân biệt JSON body/Publisher; xử lý 400/404/201; biết thứ tự route và lỗi trùng route; chạy Java 17+ / Spring Boot 3.3.x; kiểm thử bằng WebTestClient; nhận biết các phản mẫu block() và subscribe() trong HTTP handler.

**Phạm vi:** đây là WebFlux.fn ở package org.springframework.web.reactive.function.server. Spring MVC có một bộ functional API khác ở org.springframework.web.servlet.function; không dùng nhầm import hoặc giả định MVC.fn có Mono<ServerResponse>. Ví dụ hướng đến Spring Boot 3.3.x, Java 17+; đối chiếu tài liệu đúng nhánh Spring Boot khi áp dụng lên Boot mới hơn.

## 2. Tư duy tách route, handler và response

Với một HTTP request:

~~~http
GET /api/books/12 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Các bước khái quát:

~~~text
HTTP client
   |
   v
HTTP server (thường Reactor Netty)
   |
   v
HttpHandler / WebFilter
   |
   v
DispatcherHandler
   |
   v
RouterFunctionMapping: chọn HandlerFunction
   |
   v
HandlerFunctionAdapter: gọi handle(ServerRequest)
   |
   v
Mono<ServerResponse>
   |
   v
ServerResponseResultHandler + HTTP codec
   |
   v
HTTP response
~~~

RouterFunctionMapping nhận các RouterFunction beans, sắp xếp/kết hợp và tìm route khớp. HandlerFunctionAdapter gọi handler function. ServerResponseResultHandler ghi ServerResponse ra HTTP response. Khi ứng dụng sử dụng spring-boot-starter-webflux, Spring Boot thiết lập hạ tầng này; lập trình viên chỉ cần đăng ký router và handler thích hợp.

Phân tách trách nhiệm tốt: RouterFunction biết **đường đi**; HandlerFunction biết **cách xử lý**; ServerResponse biết **gói kết quả HTTP**. Data access, transaction, caching và nghiệp vụ nên nằm trong service/repository riêng, không dồn toàn bộ vào một lambda route.

## 3. Hợp đồng RouterFunction

Về ý nghĩa, RouterFunction<ServerResponse> có một method route nhận ServerRequest và trả publisher chứa HandlerFunction khi match:

~~~java
Mono<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

Đoạn trên chỉ mô tả chữ ký khái quát, không phải source file biên dịch độc lập. Thực tế Spring Framework thường được sử dụng qua RouterFunctions.route():

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/books", bookHandler::list)
        .GET("/api/books/{id}", bookHandler::get)
        .POST("/api/books", bookHandler::create)
        .build();
~~~

bookHandler là một Bean được khai báo ở project hoàn chỉnh phía dưới. GET /api/books chọn list; GET /api/books/12 chọn get; POST /api/books chọn create.

Để Spring Boot sử dụng router, thường đăng ký @Bean:

~~~java
@Bean
RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
    return RouterFunctions.route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
~~~

RouterFunctions.route() trả builder, hỗ trợ GET/POST/PUT/PATCH/DELETE và các predicate khác. Không nhất thiết tự viết class implements RouterFunction; builder đơn giản và dễ kiểm thử hơn.

## 4. Hợp đồng HandlerFunction

HandlerFunction<T extends ServerResponse> đại diện cho một hàm nhận ServerRequest và trả Mono<T>:

~~~java
Mono<ServerResponse> handle(ServerRequest request);
~~~

Một handler nhỏ có thể là lambda:

~~~java
request -> ServerResponse.ok().bodyValue("Hello WebFlux.fn")
~~~

Ví dụ Bean độc lập:

~~~java
@Bean
RouterFunction<ServerResponse> helloRoutes() {
    return RouterFunctions.route()
            .GET("/hello", request -> ServerResponse.ok()
                    .bodyValue("Hello WebFlux.fn"))
            .build();
}
~~~

Khi gọi GET /hello, handler tạo HTTP 200 và body text. Với API lớn, nhóm logic vào một @Component có các method list, get, create, update, delete thay vì viết một lambda dài hàng trăm dòng.

**Quan trọng:** Mono<ServerResponse> không có nghĩa Spring tự tạo một thread riêng cho mỗi request. Nó biểu diễn một quá trình xử lý reactive có thể hoàn tất bất đồng bộ. Không tự gọi subscribe() trong handler để xử lý công việc nền rồi trả HTTP 200 ngay, vì như vậy việc xử lý, lỗi và cancellation thoát khỏi vòng đời HTTP request.

## 5. ServerRequest và dữ liệu đầu vào

Các API thường dùng:

| Dữ liệu | WebFlux.fn API | Lưu ý |
| --- | --- | --- |
| Path variable | request.pathVariable("id") | String, cần parse/validate |
| Query | request.queryParam("page") | Optional<String> |
| Header | request.headers().firstHeader("X-Request-ID") | Có thể null |
| HTTP method | request.method() | HttpMethod |
| URI | request.uri() | URI chứa path và query |
| JSON body một object | request.bodyToMono(CreateBookRequest.class) | Cần JSON codec, Content-Type |
| Nhiều object/body stream | request.bodyToFlux(Event.class) | Kiểm soát buffer/backpressure |
| Session | request.session() | Mono<WebSession> |
| Principal | request.principal() | Mono<Principal> |
| Exchange thấp hơn | request.exchange() | ServerWebExchange |

Ví dụ đọc path variable:

~~~java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue(Map.of("error", "id must be numeric"));
}
~~~

Snippet được đặt trong handler trả Mono<ServerResponse>. Nó cần import Map và biến request kiểu ServerRequest. Nếu id phải dương, cần kiểm tra id > 0. Không mặc định rằng URL có placeholder {id} là id đã hợp lệ.

Khi request có body, dùng bodyToMono/bodToFlux phù hợp. Không dùng bodyToMono(...).block() trong request handler; dùng flatMap để nối bước bất đồng bộ.

## 6. ServerResponse: status, header và body

Một số factory thông dụng:

~~~java
ServerResponse.ok().bodyValue(Map.of("status", "ok"));

ServerResponse.created(URI.create("/api/books/13"))
        .bodyValue(new Book(13, "WebFlux"));

ServerResponse.noContent().build();

ServerResponse.notFound().build();

ServerResponse.badRequest()
        .bodyValue(Map.of("error", "invalid input"));

ServerResponse.status(HttpStatus.CONFLICT)
        .bodyValue(Map.of("error", "duplicate"));
~~~

Đây là các expression minh họa độc lập, không phải một main method đầy đủ. Cần các import tương ứng. bodyValue(...) và build() trả Mono<ServerResponse>; khi handler trả lại Publisher này, framework quản lý lúc viết HTTP response.

Với JSON:

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("message", "hello"));
~~~

Với một Publisher:

~~~java
Flux<Book> books = store.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(books, Book.class);
~~~

Dùng **bodyValue** cho object đã có sẵn. Dùng **body(Publisher, element type)** khi response body được phát từ Flux/Mono; tránh truyền một Publisher vào bodyValue và mong framework tự coi nó là reactive source trong mọi trường hợp.

HTTP 201 nên có Location nếu tài nguyên mới có URL. HTTP 204 không có response body. 404 dùng khi resource hợp lệ nhưng không tồn tại; 400 dùng khi đầu vào sai định dạng. Nên thể hiện status có chủ đích thay vì luôn trả 200.

## 7. RequestPredicates: khớp method, path, header và media type

Builder cung cấp shortcut GET/POST, còn RequestPredicates cung cấp điều kiện bổ sung như accept, contentType, queryParam, headers và path. Có thể kết hợp predicate bằng and/or/negate.

Ví dụ chỉ match GET khi client chấp nhận text/plain:

~~~java
RouterFunctions.route()
        .GET("/hello",
                RequestPredicates.accept(MediaType.TEXT_PLAIN),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello"))
        .build();
~~~

**Phân biệt Accept và Content-Type:**

- Accept: client muốn nhận định dạng response nào.
- Content-Type: định dạng body mà client đang gửi trong request.

Nếu RequestPredicate không match, router có thể không chọn handler và request trả 404 khi không có route khác. Do đó, thêm accept(...) hoặc contentType(...) vào route có thể đổi kết quả từ 406/415 thành 404 trong một số tổ hợp. Muốn API có mã lỗi 406/415 đúng hợp đồng, cần kiểm thử media negotiation và thiết kế error handling, không chỉ suy luận từ predicate.

Không gắn thêm predicate theo thói quen. GET không có body không cần predicate Content-Type. Với POST JSON, có thể để router match theo method/path rồi để body reader/codec xử lý supported media type.

## 8. Thứ tự route và route trùng nhau

WebFlux.fn thử các RouterFunction theo thứ tự; route đầu tiên phù hợp được chọn. Khác annotation controller, nơi HandlerMapping có thuật toán độ đặc hiệu của mapping.

Ví dụ nguy cơ:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::get)
        .GET("/api/books/search", handler::search)
        .build();
~~~

GET /api/books/search có thể bị /{id} nhận trước, khiến handler get cố parse "search" thành số và trả 400. Đúng hơn:

~~~java
RouterFunctions.route()
        .GET("/api/books/search", handler::search)
        .GET("/api/books/{id}", handler::get)
        .build();
~~~

Đây là hai snippet minh họa route với handler::search giả định có trong module mở rộng. Project mẫu phía dưới không đăng ký route /search. Nguyên tắc là đặt route cụ thể/trùng prefix trước route tổng quát hoặc catch-all.

Khi có nhiều RouterFunction bean, Spring tìm, sắp xếp và ghép chúng. Tổ chức rõ thứ tự với @Order/Ordered nếu thực sự cần, và tránh chồng chéo để không phụ thuộc một thứ tự dễ thay đổi khi refactor. Kiểm thử toàn bộ route đặc biệt, route ID và route fallback.

## 9. Ghép và lồng routes

Có thể ghép RouterFunction bằng and(...) hoặc dùng Builder.add(otherRouter). Ví dụ:

~~~java
RouterFunction<ServerResponse> routes =
        booksRoutes.and(healthRoutes);
~~~

booksRoutes, healthRoutes là hai router đã tạo ở nơi khác. Router bên trái được xét trước theo cơ chế composition.

Để chia sẻ prefix:

~~~java
@Bean
RouterFunction<ServerResponse> nestedBookRouter(
        BookHandler handler) {
    return RouterFunctions.route()
            .path("/api/books", nested -> nested
                    .GET("/{id}", handler::get)
                    .GET(handler::list)
                    .POST(handler::create))
            .build();
}
~~~

Đây là **cách thay thế** BookRoutes trong project hoàn chỉnh; không khai báo cả hai router cùng path/method trong một app. Builder.path giúp gom các tuyến dưới prefix chung. Có thể dùng Builder.nest để áp dụng predicate chung như Accept cho một nhóm GET mà không ảnh hưởng POST hoặc routes ngoài nhóm.

Nested routes dễ đọc khi nhóm API lớn. Tuy nhiên, lồng quá nhiều tầng làm scope của predicate/filter khó nhìn và dễ tạo 404 ngoài ý muốn. Nên giữ cấu trúc đủ đơn giản và test các trường hợp header khác nhau.

## 10. Đọc JSON với bodyToMono và flatMap

Với request:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"title":"Reactive Java"}
~~~

Handler có thể đọc body rồi tạo sách:

~~~java
return request.bodyToMono(CreateBookRequest.class)
        .flatMap(input -> store.insert(input.title())
                .flatMap(book -> ServerResponse
                        .created(URI.create(
                                "/api/books/" + book.id()))
                        .bodyValue(book)));
~~~

Đoạn minh họa này cần request/store/DTO và chưa có validation. Bản hoàn chỉnh trong phần 12 xử lý title null/trống và body rỗng.

Đừng dùng map() khi lambda tự trả Mono<ServerResponse>, vì có thể tạo Mono<Mono<ServerResponse>>. Dùng flatMap để flatten Publisher. Nếu bodyToMono trả Mono.empty() vì không có body, dùng switchIfEmpty(...) tạo response 400. Nếu body parsing phát lỗi, xử lý lỗi theo loại hợp lý; không biến mọi exception từ database thành 400.

**Không gọi subscribe() thủ công** để lưu bản ghi, vì HTTP response có thể hoàn tất trước thao tác thực, mất kiểm soát cancellation và error propagation.

## 11. Bố cục dự án Spring Boot Java 17+

Ví dụ sau dùng **Spring Boot 3.3.0 + Java 17+**, Gradle Groovy DSL, starter WebFlux và embedded Reactor Netty mặc định. Nó là API quản lý sách đơn giản không cần database. Dữ liệu chỉ nằm trong ConcurrentHashMap nên mất khi restart.

Cấu trúc:

~~~text
webflux-fn-books/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/fn/
        BookApiApplication.java
        Book.java
        CreateBookRequest.java
        BookStore.java
        BookHandler.java
        BookRoutes.java
      resources/
        application.yml
    test/
      java/example/fn/
        BookApiApplicationTests.java
~~~

Mỗi public class/record phải nằm trong file trùng tên. Cần JDK 17+, Gradle Wrapper tương thích Spring Boot 3.3 và môi trường tải được Maven Central.

### 11.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-fn-books'
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

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
~~~

Không thêm spring-boot-starter-web vì Spring Boot thường ưu tiên MVC khi cả MVC/WebFlux starter cùng tồn tại. Nếu dự án thực đã có dependency management, giữ theo bộ version của dự án thay vì sao chép plugin versions từ một bài mẫu.

### 11.3. application.yml

~~~yaml
spring:
  application:
    name: webflux-fn-books

server:
  port: 8080
~~~

Để chạy trên port khác: java -jar ... --server.port=9090 hoặc truyền SERVER_PORT theo cấu hình môi trường.

### 11.4. BookApiApplication.java

~~~java
package example.fn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
~~~

### 11.5. Book.java

~~~java
package example.fn;

public record Book(long id, String title) {
}
~~~

### 11.6. CreateBookRequest.java

~~~java
package example.fn;

public record CreateBookRequest(String title) {
}
~~~

Jackson thông thường trong starter WebFlux có thể chuyển JSON thành record CreateBookRequest và serialize Book record về JSON.

### 11.7. BookStore.java

~~~java
package example.fn;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class BookStore {

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public Flux<Book> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(books.values())
                        .sort(Comparator.comparingLong(Book::id)));
    }

    public Mono<Book> findById(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(books.get(id)));
    }

    public Mono<Book> insert(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}
~~~

AtomicLong cấp id đồng thời trong một JVM. ConcurrentHashMap an toàn hơn HashMap khi có concurrent requests nhưng không có transaction/durability. Flux.defer/Mono.defer trì hoãn thao tác đến lúc subscribe. sort thu thập dữ liệu trước khi phát nên **không phù hợp dataset lớn**. Demo in-memory này không chứng minh JDBC trở thành non-blocking khi bọc bằng Mono.

### 11.8. BookHandler.java

~~~java
package example.fn;

import java.net.URI;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.findAll(), Book.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        long id;

        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException exception) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of(
                            "error", "id must be an integer"));
        }

        if (id <= 0) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of(
                            "error", "id must be positive"));
        }

        return store.findById(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBookRequest.class)
                .flatMap(input -> {
                    String title = input.title();

                    if (title == null || title.isBlank()) {
                        return ServerResponse.badRequest()
                                .contentType(
                                        MediaType.APPLICATION_JSON)
                                .bodyValue(Map.of(
                                        "error", "title is required"));
                    }

                    return store.insert(title.trim())
                            .flatMap(book -> ServerResponse
                                    .created(URI.create(
                                            "/api/books/" + book.id()))
                                    .contentType(
                                            MediaType.APPLICATION_JSON)
                                    .bodyValue(book));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                                "error", "JSON body is required")));
    }
}
~~~

Giải thích: list trả Publisher của sách; get phân biệt 400 do id sai và 404 do không tồn tại; create giải mã JSON, kiểm tra title, lưu bằng Publisher và trả 201 với Location. Khi có JSON sai cú pháp, codec WebFlux có thể phát exception; cần error handler nhất quán trong ứng dụng production.

### 11.9. BookRoutes.java

~~~java
package example.fn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class BookRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
        return RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .build();
    }
}
~~~

Đây là toàn bộ cấu hình route, không cần @RestController cho endpoints trong ví dụ. Spring Boot sẽ quét package example.fn, tạo BookHandler/BookStore và đăng ký RouterFunction bean.

## 12. Chạy ứng dụng và quan sát HTTP response

Trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau khi server startup thành công trên port 8080, chạy ở terminal khác:

~~~bash
curl -i http://localhost:8080/api/books
~~~

Kỳ vọng HTTP 200 và JSON rỗng lúc ứng dụng vừa start:

~~~json
[]
~~~

Tạo sách:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d '{"title":"Reactive Java"}'
~~~

Nếu đây là request tạo sách đầu tiên, kỳ vọng HTTP 201 Created, Location=/api/books/1, body JSON:

~~~json
{"id":1,"title":"Reactive Java"}
~~~

Sau khi có sách id=1:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Kỳ vọng HTTP 200 và JSON của sách id=1. Với id chưa tồn tại:

~~~bash
curl -i http://localhost:8080/api/books/999999
~~~

Kỳ vọng HTTP 404. Với id không thể parse:

~~~bash
curl -i http://localhost:8080/api/books/not-an-id
~~~

Kỳ vọng HTTP 400 với error tương ứng. Với tên trống:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d '{"title":" "}'
~~~

Kỳ vọng HTTP 400 với error title is required.

Các ví dụ response nói tới **trạng thái mong đợi sau khi chạy thành công**, không phải kết quả đã thực thi tại máy của người học. Số id có thể khác nếu nhiều request tạo sách đã chạy.

## 13. WebTestClient: kiểm thử route và response

Tệp src/test/java/example/fn/BookApiApplicationTests.java:

~~~java
package example.fn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookApiApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void createAndRead() {
        Book created = client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest("  Reactive Java  "))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody(Book.class)
                .returnResult()
                .getResponseBody();

        assertNotNull(created);
        assertEquals("Reactive Java", created.title());

        client.get()
                .uri("/api/books/" + created.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive Java");
    }

    @Test
    void invalidIdIsBadRequest() {
        client.get()
                .uri("/api/books/no-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unknownBookIsNotFound() {
        client.get()
                .uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void blankTitleIsBadRequest() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest(" "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error")
                .isEqualTo("title is required");
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

@SpringBootTest(RANDOM_PORT) tạo HTTP server thực trên port ngẫu nhiên; @AutoConfigureWebTestClient tạo client có thể gửi request đến server trong cấu hình tích hợp của Spring Boot 3.3. Test trực tiếp route/handler khác với integration test network. Nếu trong cùng project có nhiều tests với BookStore in-memory singleton, không dựa vào việc id bắt đầu bằng 1 ở mọi test; dùng id trả về từ response như ví dụ.

### Các chế độ dùng WebTestClient

- bindToRouterFunction(router): test RouterFunction và handler trên test infrastructure mà không mở TCP port.
- bindToApplicationContext(context): test WebFlux ApplicationContext không nhất thiết mở port.
- bindToServer().baseUrl(...): gửi request tới HTTP server đang chạy.
- @SpringBootTest(RANDOM_PORT) + WebTestClient: tích hợp server thật trong test Spring Boot.

Chọn mức phù hợp với rủi ro: unit/contract tests chạy nhanh, integration test xác minh cả HTTP adapter và codec. Test gọi trực tiếp BookHandler.get với một ServerRequest mock không đủ chứng minh router matching và HTTP mapping.

## 14. Functional filters và WebFilter

Một HandlerFilterFunction nhận ServerRequest, HandlerFunction kế tiếp và trả Mono<ServerResponse>. Có thể dùng builder.filter(...) để xử lý quy tắc chung cho **những functional routes thuộc builder đó**.

Ví dụ kiểm tra một header của môi trường lab:

~~~java
RouterFunction<ServerResponse> demo =
        RouterFunctions.route()
                .GET("/internal-demo", request ->
                        ServerResponse.ok().bodyValue("ok"))
                .filter((request, next) -> {
                    String mode = request.headers()
                            .firstHeader("X-Lab-Mode");
                    if (!"on".equals(mode)) {
                        return ServerResponse.badRequest()
                                .bodyValue(Map.of(
                                        "error", "X-Lab-Mode must be on"));
                    }
                    return next.handle(request);
                })
                .build();
~~~

Đây là snippet riêng, không nằm trong project mẫu chính. Nó cần import Map và classes WebFlux.fn. Filter có thể ngăn gọi handler nếu điều kiện không thỏa.

**Phân biệt phạm vi:**

- HandlerFilterFunction: functional route hoặc nhóm routes được ghép với filter đó.
- WebFilter: cross-cutting cho WebFlux request chain, có thể áp dụng cả functional và annotated endpoints.
- Servlet Filter: API Servlet, không phải lựa chọn middleware mặc định của WebFlux.
- SecurityWebFilterChain: chính sách authentication/authorization reactive của Spring Security.

Không dùng X-Lab-Mode hay một header tự gửi làm authentication thực sự. Với hệ thống multi-tenant hoặc API có dữ liệu nhạy cảm, dùng principal/claims đã xác thực và các security rules phù hợp.

### before, after và filter

Builder hỗ trợ before(request -> newRequest), after((request,response) -> newResponse) và filter((request,next) -> Mono<ServerResponse>) ở phạm vi route liên quan. Vì ServerRequest/ServerResponse có hợp đồng bất biến, hãy dùng builder/copy API để tạo biến thể mới thay vì giả định có thể sửa object đã tạo theo cách mutable.

Filter trong nhóm nested routes không nhất thiết áp dụng cho routes ngoài nhóm. Test cả những request nằm ngoài phạm vi để tránh vô tình áp dụng quá rộng.

## 15. Error handling và validation

HTTP contract tốt phải phân biệt:

| Tình huống | Status thường dùng | Điểm xử lý |
| --- | --- | --- |
| id sai định dạng | 400 | Handler parse/validation |
| JSON sai cú pháp | 400 | Request body decoder/error handler |
| Field bắt buộc trống | 400 | Validator hoặc handler |
| Resource không tồn tại | 404 | switchIfEmpty(notFound) |
| Resource bị trùng | 409 | Business validation |
| Không xác thực | 401 | Spring Security reactive |
| Không đủ quyền | 403 | Authorization |
| Content-Type không hỗ trợ | 415 | Codec/media type |
| Không tạo được representation theo Accept | 406 | Content negotiation |
| Lỗi backend thật | 5xx | Error handler và logging |

Với functional handler, nếu chỉ dùng bodyToMono mà chưa gọi Validator thì không được tự suy ra mọi annotation @Valid trên DTO đều đã được áp dụng. Có thể dùng Spring Validator/Bean Validation được inject, hoặc validate rõ trước khi gọi repository. Khi lỗi validation, trả error response có cấu trúc ổn định; không để stack trace, SQL, credential hoặc giá trị secret lọt về client.

Không dùng onErrorResume(error -> badRequest()) để che mọi lỗi backend thành 400. Hãy phân biệt exception do input và exception do hệ thống; những lỗi không mong đợi cần được log/tracing đúng và trả 5xx không lộ thông tin nhạy cảm.

## 16. Reactive request lifecycle và phản mẫu

Code đúng thường **trả reactive pipeline**:

~~~java
return store.findById(id)
        .flatMap(book -> ServerResponse.ok().bodyValue(book))
        .switchIfEmpty(ServerResponse.notFound().build());
~~~

Code sai về cách quản lý lifecycle:

~~~java
store.insert(title).subscribe(); // xử lý tách khỏi HTTP response
Book book = store.findById(id).block(); // chặn request thread
~~~

Hai dòng chỉ minh họa phản mẫu, không phải source độc lập. subscribe thủ công có thể khiến response gửi trước khi insert hoàn tất, lỗi không được chuyển thành HTTP status và cancellation không được xử lý. block() trên non-blocking thread có thể bị cấm hoặc làm nghẽn event loop.

Nếu buộc phải gọi một API blocking, có thể offload công việc một cách có giới hạn:

~~~java
Mono<Book> result = Mono.fromCallable(
        () -> blockingGateway.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Snippet có dependency giả định blockingGateway và cần import Reactor Mono/Schedulers. boundedElastic có tài nguyên hữu hạn; offload không biến JDBC hay SDK đồng bộ thành non-blocking. Khi nhiều phần nghiệp vụ chủ yếu blocking, Spring MVC có thể đơn giản hơn WebFlux.

## 17. Streaming, codec và backpressure

ServerResponse.body(Flux, Class) cho phép HTTP writer encode phần tử từ Publisher, nhưng **không phải Flux nào cũng streaming constant memory**. Ví dụ BookStore.findAll dùng sort, tức là cần gom dữ liệu để sắp xếp. Nhiều codec có thể buffer hoặc encode thành JSON array; proxy cũng có thể buffer response trước khi client thấy.

Ví dụ SSE trong handler:

~~~java
Flux<ServerSentEvent<String>> events =
        Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder()
                        .data("tick-" + index)
                        .build());

return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events,
                new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {});
~~~

Snippet này cần import Duration, Flux, ServerSentEvent, MediaType và ParameterizedTypeReference; nó không nằm trong project CRUD hoàn chỉnh. Kỳ vọng client hỗ trợ SSE nhận ba data event tick-0, tick-1, tick-2 rồi stream kết thúc.

Khi triển khai thực, cần test cancellation, client chậm, memory, backpressure, proxy buffering, timeout và giới hạn body. Không coi Publisher là bảo chứng rằng mọi tầng database, HTTP server và reverse proxy đều non-blocking.

## 18. WebFlux.fn và annotated WebFlux có thể cùng tồn tại

Có. Spring WebFlux hỗ trợ cả RouterFunction beans và @RestController annotated handlers trên cùng reactive runtime. Tuy nhiên nên tránh cùng method/path xuất hiện ở cả hai phong cách mà không có chủ ý; routing conflict khó bảo trì.

Không nhầm với tình huống **starter-web + starter-webflux**: khi cả hai starter xuất hiện, Spring Boot thường chọn web application type MVC; thêm Mono trong một controller MVC không đủ chứng minh HTTP app đang chạy WebFlux. Muốn triển khai functional WebFlux, giữ classpath đúng và kiểm tra reactive ApplicationContext.

Một WebFlux.fn route-level filter không tự phủ lên @RestController; nếu cần xử lý xuyên mọi request WebFlux, cân nhắc WebFilter hoặc Spring Security reactive. Endpoint ownership nên được định nghĩa rõ để tránh route bị che bởi catch-all.

## 19. WebFlux.fn khác Spring MVC.fn

Tên class tương tự nhưng **package khác**:

| Đặc điểm | WebFlux.fn | Spring MVC.fn |
| --- | --- | --- |
| RouterFunction package | org.springframework.web.reactive.function.server | org.springframework.web.servlet.function |
| HandlerFunction return | Mono<ServerResponse> | ServerResponse |
| Request model | ServerRequest reactive | ServerRequest Servlet |
| Response handling | Reactive HTTP codecs | Servlet message conversion |
| Server mặc định thường dùng | Reactor Netty | Tomcat |
| Cross-cutting web API | WebFilter | Servlet Filter |

Nếu IDE import nhầm ServerResponse từ org.springframework.web.servlet.function, generic RouterFunction và body handling sẽ không tương thích với WebFlux.fn. Kiểm tra cả RouterFunction, ServerRequest, HandlerFunction, ServerResponse đều ở package web.reactive.function.server.

## 20. Khi nào dùng WebFlux.fn thay annotations?

WebFlux.fn phù hợp khi team muốn:

- Khai báo tuyến cùng predicate rõ ràng tại một nơi.
- Dùng modular router cho từng domain/module.
- Dễ ghép/nest routes và áp dụng route-level filters theo nhóm.
- Tách HandlerFunction dạng class khỏi cấu hình tuyến.
- Sử dụng Java functions/lambdas cho những endpoint gọn.

Annotated controllers có ưu thế về sự quen thuộc, method-level annotations, binding và validation phổ biến. Không có kết luận chung rằng functional routes nhanh hơn hoặc an toàn hơn trong mọi workload. Cả hai vẫn phụ thuộc cùng reactive HTTP runtime, codec, data layer và security.

Chọn cách theo tiêu chuẩn maintainability và testability của project; tránh thay đổi kiến trúc chỉ vì cú pháp ngắn hơn vài dòng.

## 21. Troubleshooting checklist

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Router không hoạt động | @Bean/@Configuration chưa được scan, sai package |
| GET /search bị 400 | /{id} bắt trước /search |
| POST body khác media type trả 404 | contentType predicate không match |
| POST trả 415 | Codec không đọc được Content-Type |
| Response trả 406 | Không có representation theo Accept |
| Không đọc được pathVariable | Tên {id} trong path khác tên được đọc |
| Handler trả Mono<Mono<ServerResponse>> | Dùng map thay vì flatMap |
| API response trước khi lưu | subscribe thủ công thay vì trả chain |
| Response body rỗng bất ngờ | Mono.empty chưa được switchIfEmpty |
| 500 với input sai | Exception parse chưa xử lý/validation thiếu |
| Route filter không áp dụng toàn app | Filter gắn chỉ với RouterFunction |
| Sau khi thêm starter MVC, WebFlux route không chạy | Spring Boot chọn Servlet MVC |
| Mất performance | blocking on event loop, data access bottleneck |
| Unit test pass nhưng deploy lỗi | Chưa có test port/HTTP thật |
| JSON serialization khác | Codec/Jackson config hoặc schema thay đổi |

Quy trình điều tra: xác định đúng runtime stack; kiểm tra dependency và RouterFunction beans; so path/method/predicate; kiểm tra route precedence; xem HTTP status và error log; tái hiện bằng WebTestClient; xác minh serializer và security; cuối cùng mới điều chỉnh server tuning.

## 22. Bài thực hành nâng cao

1. **Route cụ thể:** thêm GET /api/books/search, đặt trước /api/books/{id}, dùng queryParam("q") lọc title. Kiểm thử route precedence.
2. **Nesting:** chuyển BookRoutes sang builder.path("/api/books", ...); không đăng ký duplicate router. Kiểm tra GET/POST vẫn đúng.
3. **Validation:** thêm author hoặc price vào CreateBookRequest, dùng Validator phù hợp, trả error 400 có cấu trúc.
4. **Route filter:** thêm filter cho nhóm /internal-demo, kiểm tra ngoài nhóm không bị ảnh hưởng; không dùng lab header cho authentication.
5. **Lỗi JSON:** gửi body sai cú pháp, sai media type, body rỗng; kiểm tra status và không lộ stack trace.
6. **Streaming:** thêm route SSE gửi ba event; test stream bị hủy, proxy buffering và memory.
7. **Database:** thay BookStore bằng repository reactive phù hợp, giữ contract Mono/Flux; đánh giá các request chậm và backpressure.
8. **Security:** dùng Spring Security reactive cho POST, test 401/403; bảo vệ cả functional và annotated routes.
9. **Deployment:** chạy JAR trên port khác, kiểm tra graceful shutdown và health/readiness.

Bằng chứng đạt: source code, Gradle test pass, curl request/response, ghi rõ route matching và tình huống lỗi. Không tự bịa con số latency hoặc throughput; nếu benchmark thì cố định JDK, CPU, memory, dữ liệu, mức tải và đo nhiều lần.

## 23. Câu hỏi tự kiểm tra

1. RouterFunction và HandlerFunction đảm nhận hai nhiệm vụ gì khác nhau?
2. Vì sao HandlerFunction trả Mono<ServerResponse>?
3. ServerRequest khác HttpServletRequest như thế nào?
4. RouterFunctionMapping, HandlerFunctionAdapter và ServerResponseResultHandler làm gì?
5. Vì sao route static nên được đặt trước /{id}?
6. Dùng RequestPredicates.accept khác RequestPredicates.contentType như thế nào?
7. Vì sao một predicate không match có thể gây 404?
8. Khi nào dùng ServerResponse.bodyValue và khi nào dùng body(Publisher, Class)?
9. Mono.empty() của repository nên dẫn tới response gì khi tìm theo ID?
10. Vì sao không dùng block() hoặc subscribe() trong handler?
11. HandlerFilterFunction có phủ toàn bộ annotated WebFlux controllers không?
12. WebFilter khác Servlet Filter và route filter như thế nào?
13. Khi nào @Valid trên DTO cần explicit validation trong functional handlers?
14. Spring WebFlux.fn và Spring MVC.fn khác nhau ở package và return type ra sao?
15. WebTestClient.bindToRouterFunction có mở TCP port thật không?
16. Làm sao kiểm thử embedded server thật bằng RANDOM_PORT?
17. Có nên dùng Spring MVC và WebFlux starter cùng lúc chỉ để nhận WebClient không?
18. Vì sao Flux chưa bảo đảm không buffer toàn bộ dữ liệu?
19. Trường hợp nào nên trả 400, 404, 409, 415 hoặc 500?
20. Khi nào nested route hoặc ghép RouterFunction giúp code dễ bảo trì hơn?

## 24. Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): route, handler, ServerRequest, ServerResponse, predicates, nesting, filters.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): RouterFunctionMapping, handler invocation và result handling.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux integration.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): WebTestClient, @SpringBootTest và test slices.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToRouterFunction/bindToServer.
- [Project Reactor](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, flatMap, error handling và scheduler.

**Kết luận:** RouterFunction chọn đúng HTTP handler theo predicate và thứ tự; HandlerFunction xây dựng một reactive chain từ ServerRequest; ServerResponse xác định HTTP status, headers và body. Khi giữ rõ ba ranh giới đó, WebFlux.fn vừa dễ tổ chức tuyến lớn vừa kiểm thử được bằng WebTestClient, nhưng vẫn phải đảm bảo validation, security, codecs và xử lý non-blocking đúng cách.
