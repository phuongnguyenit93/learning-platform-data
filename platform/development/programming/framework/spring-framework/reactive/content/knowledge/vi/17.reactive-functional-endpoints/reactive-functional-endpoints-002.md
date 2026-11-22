# Khai báo tuyến bằng RouterFunctions.route trong Spring WebFlux

## 1. WebFlux.fn và vai trò của RouterFunctions.route

Spring WebFlux hỗ trợ hai mô hình xây dựng HTTP endpoint:

- **Annotation-based:** dùng `@RestController`, `@GetMapping`, `@PostMapping` và `@RequestBody`.
- **Functional endpoints (WebFlux.fn):** dùng các hàm và object bất biến để mô tả cách khớp request, gọi handler và tạo response.

Một functional endpoint gồm hai thành phần:

- **`RouterFunction<ServerResponse>`** nhận `ServerRequest` và tìm handler phù hợp. Nếu tuyến khớp, router cung cấp handler function; nếu không khớp, router trả publisher rỗng để framework xét router tiếp theo.
- **`HandlerFunction<ServerResponse>`** nhận `ServerRequest` và trả `Mono<ServerResponse>`. Handler đọc path, query, headers hoặc body, gọi service reactive rồi tạo response.

`RouterFunctions.route()` cung cấp builder fluent để khai báo tuyến theo HTTP method, path và predicate. Ví dụ tối giản:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/hello", request ->
            ServerResponse.ok().bodyValue("Hello WebFlux"))
        .build();
~~~

Khi client gọi `GET /hello`, router khớp method và path rồi gọi handler lambda. Handler trả `Mono<ServerResponse>`; WebFlux subscribe và ghi response theo cơ chế reactive.

**Nguyên tắc:** route quyết định request nào đi tới handler nào; handler quyết định cách xử lý request và tạo response. `RouterFunctions.route()` không tự mở socket, không tự subscribe service và không thay thế server runtime.

## 2. Các kiểu và hợp đồng cốt lõi

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `ServerRequest` | Đại diện request đầu vào; cung cấp method, URI, headers, query, path variables và body | `request.pathVariable("id")` |
| `ServerResponse` | Response bất biến chứa status, headers và body publisher | `ServerResponse.ok().bodyValue(user)` |
| `HandlerFunction` | Hàm xử lý một request và trả publisher của response | `request -> ServerResponse.ok().build()` |
| `RouterFunction` | Hàm tìm handler phù hợp cho request | Kết quả từ `RouterFunctions.route().build()` |
| `RequestPredicate` | Điều kiện khớp request | method, path, Accept, Content-Type |
| `HandlerFilterFunction` | Bao quanh handler để xử lý trước/sau hoặc chặn request | log, kiểm tra quyền |
| `RouterFunctions` | Utility và builder để tạo, ghép, nest hoặc chuyển router thành HttpHandler | `RouterFunctions.route()` |

Request và response của WebFlux.fn có contract bất biến. Khi cần biến đổi request trong filter, dùng `ServerRequest.from(request)` để tạo request mới. Khi cần thêm status, header hoặc body, dùng builder của `ServerResponse`.

Handler thường có chữ ký:

~~~java
Mono<ServerResponse> handle(ServerRequest request) {
    return ServerResponse.ok().bodyValue("ready");
}
~~~

`Mono<ServerResponse>` biểu diễn response được tạo bất đồng bộ. Handler có thể chờ repository hoặc WebClient rồi mới quyết định status và body.

## 3. Khai báo tuyến bằng builder

### 3.1. Shortcut theo HTTP method

Builder cung cấp các shortcut thường dùng:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::get)
        .POST("/products", handler::create)
        .PUT("/products/{id}", handler::update)
        .PATCH("/products/{id}", handler::patch)
        .DELETE("/products/{id}", handler::delete)
        .build();
~~~

Các method reference như `handler::get` trỏ tới method nhận `ServerRequest` và trả `Mono<ServerResponse>`. Path có thể chứa biến như `{id}`; handler lấy giá trị bằng `request.pathVariable("id")`.

Các route trong builder được ghép thành một RouterFunction duy nhất khi gọi `build()`. Có thể khai báo router thành Spring bean:

~~~java
@Configuration
class ApiRoutes {
    @Bean
    RouterFunction<ServerResponse> apiRoutes(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::get)
            .POST("/api/products", handler::create)
            .build();
    }
}
~~~

Spring phát hiện bean kiểu `RouterFunction<?>` và đưa nó vào hạ tầng WebFlux để định tuyến request. Không cần tự gọi `subscribe()` trong bean cấu hình.

### 3.2. Tạo route trực tiếp bằng predicate

Ngoài builder shortcut, có thể tạo route từ predicate và handler:

~~~java
RequestPredicate jsonGet =
    RequestPredicates.GET("/api/products")
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(jsonGet, handler::list);
~~~

Cách này hữu ích khi điều kiện khớp phức tạp hoặc cần tạo predicate riêng trước khi ghép router. Builder cũng có overload nhận predicate:

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route()
        .GET("/api/products",
            RequestPredicates.accept(MediaType.APPLICATION_JSON),
            handler::list)
        .build();
~~~

Predicate có thể yêu cầu thêm header, Content-Type, query parameter hoặc điều kiện tùy chỉnh bên cạnh method và path.

## 4. RequestPredicate: điều kiện để route khớp

`RequestPredicate` biểu diễn một điều kiện trên request. `RequestPredicates` cung cấp factory cho các điều kiện phổ biến.

| Predicate | Điều kiện |
| --- | --- |
| `GET("/path")` | HTTP GET và path phù hợp |
| `POST("/path")` | HTTP POST và path phù hợp |
| `method(HttpMethod.PUT)` | HTTP method cụ thể |
| `path("/api/**")` | Path phù hợp mẫu |
| `pathExtension("json")` | Phần mở rộng path |
| `accept(MediaType.APPLICATION_JSON)` | Client chấp nhận JSON |
| `contentType(MediaType.APPLICATION_JSON)` | Request body có Content-Type JSON |
| `queryParam("mode", predicate)` | Query parameter thỏa predicate |
| `headers(predicate)` | Các header thỏa điều kiện |
| `header(name, predicate)` | Header cụ thể thỏa điều kiện |
| `cookie(name, predicate)` | Cookie cụ thể thỏa điều kiện |

Ví dụ chỉ nhận POST có Content-Type JSON và client chấp nhận JSON:

~~~java
RequestPredicate jsonPost =
    RequestPredicates.POST("/api/products")
        .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON))
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(jsonPost, handler::create);
~~~

Khi predicate không khớp, handler của route đó không được gọi. RouterFunction có thể tiếp tục xét route tiếp theo; nếu không route nào khớp, request được chuyển cho cơ chế xử lý không tìm thấy handler của WebFlux.

### 4.1. Kết hợp and, or và negate

- `and(other)`: cả hai điều kiện phải đúng.
- `or(other)`: ít nhất một điều kiện đúng.
- `negate()`: đảo kết quả điều kiện.

~~~java
RequestPredicate jsonOrText =
    RequestPredicates.accept(MediaType.APPLICATION_JSON)
        .or(RequestPredicates.accept(MediaType.TEXT_PLAIN));

RequestPredicate apiPath =
    RequestPredicates.path("/api/**");

RequestPredicate publicPath = apiPath.negate();
~~~

Dùng `and` để siết điều kiện route, `or` khi một handler hỗ trợ nhiều kiểu request và `negate` cho các vùng path loại trừ. Predicate nên mô tả điều kiện định tuyến, không nên chứa toàn bộ nghiệp vụ.

### 4.2. Query parameter

Ví dụ chỉ khớp khi `view=compact`:

~~~java
RequestPredicate compactView =
    RequestPredicates.GET("/api/products")
        .and(RequestPredicates.queryParam(
            "view",
            value -> value.equals("compact")
        ));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(compactView, handler::compactList);
~~~

Nếu tham số tùy chọn hoặc có nhiều giá trị, có thể để route chỉ khớp path/method rồi đọc query bằng `request.queryParam("view")` trong handler.

### 4.3. Path variable

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route()
        .GET("/api/products/{id}", handler::get)
        .build();
~~~

Handler đọc biến:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String rawId = request.pathVariable("id");
    return ServerResponse.ok().bodyValue("id=" + rawId);
}
~~~

`pathVariable` trả chuỗi. Nếu cần số hoặc UUID, handler phải parse và xử lý dữ liệu không hợp lệ; không giả định path variable đã được chuyển thành kiểu domain.

## 5. Thứ tự route và cách tránh tuyến bị che

Router functions được đánh giá theo thứ tự. Route đầu tiên khớp sẽ cung cấp handler được sử dụng. Điều này khác annotation-based mapping, nơi Spring có quy tắc chọn mapping cụ thể nhất.

Ví dụ dễ gặp lỗi:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/users/{id}", handler::get)
        .GET("/api/users/search", handler::search)
        .build();
~~~

Route biến `{id}` có thể khớp chuỗi `search`, khiến route tìm kiếm phía sau không được gọi. Khai báo tuyến cụ thể trước:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/users/search", handler::search)
        .GET("/api/users/{id}", handler::get)
        .build();
~~~

Nguyên tắc sắp xếp:

1. Route tĩnh và cụ thể trước.
2. Route có predicate bổ sung trước route tổng quát.
3. Route biến path tổng quát sau.
4. Route fallback cuối cùng.

Khi có nhiều RouterFunction bean, WebFlux dùng thứ tự bean và ghép chúng trong RouterFunctionMapping. Nếu nhiều bean cùng khớp, thứ tự cấu hình có thể ảnh hưởng handler được chọn. Hãy kiểm tra path collision và chỉ định ordering khi thực sự cần.

## 6. Nested routes: gom tuyến có chung path hoặc predicate

Nếu nhiều route cùng có prefix `/api/users`, có thể dùng `path` để tránh lặp:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/users", users -> users
            .GET(accept(MediaType.APPLICATION_JSON), handler::list)
            .GET("/{id}", accept(MediaType.APPLICATION_JSON), handler::get)
            .POST(handler::create))
        .build();
~~~

Các path bên trong được ghép với prefix chung:

| Khai báo bên trong | Path thực tế |
| --- | --- |
| `GET(accept(JSON), handler::list)` | GET /api/users |
| `GET("/{id}", accept(JSON), handler::get)` | GET /api/users/{id} |
| `POST(handler::create)` | POST /api/users |

Có thể nest theo predicate khác ngoài path, ví dụ yêu cầu Accept JSON cho một nhóm route:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/users", users -> users
            .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/{id}", handler::get)
                .GET(handler::list))
            .POST(handler::create))
        .build();
~~~

Nested route hữu ích khi một nhóm endpoint chia sẻ path, header hoặc điều kiện. Tránh nest quá sâu khiến việc tìm route khó khăn; một hoặc hai tầng có ý nghĩa thường đủ.

## 7. Ghép nhiều RouterFunction

Có thể chia route theo domain hoặc module rồi ghép chúng:

~~~java
RouterFunction<ServerResponse> userRoutes = userRoutes(userHandler);
RouterFunction<ServerResponse> orderRoutes = orderRoutes(orderHandler);

RouterFunction<ServerResponse> api =
    userRoutes.and(orderRoutes);
~~~

Các API chính:

- `RouterFunction.and(other)` ghép router hiện tại với router khác.
- `RouterFunction.andRoute(predicate, handler)` thêm route từ predicate và handler.
- Builder `add(otherRouter)` đưa router đã tạo vào builder.
- `build()` hoàn tất builder và trả RouterFunction.

Ví dụ thêm route health:

~~~java
RouterFunction<ServerResponse> routes =
    userRoutes
        .and(orderRoutes)
        .andRoute(RequestPredicates.GET("/health"),
            request -> ServerResponse.ok().bodyValue("UP"));
~~~

Thứ tự ghép vẫn có ý nghĩa. Nếu router đầu đã khớp, router sau không được xét cho request đó. Tổ chức route theo module giúp bảo trì, nhưng vẫn cần kiểm tra collision giữa các path.

## 8. HandlerFunction: đọc request và tạo ServerResponse

Handler nhận `ServerRequest` và trả `Mono<ServerResponse>`. Có thể viết lambda nhỏ:

~~~java
HandlerFunction<ServerResponse> hello =
    request -> ServerResponse.ok().bodyValue("Hello");
~~~

Với ứng dụng thực tế, nên nhóm handler liên quan vào class để tách route declaration khỏi logic xử lý.

### 8.1. Đọc thông tin request

`ServerRequest` cung cấp method, URI, path, path variable, query parameter, headers, cookies, form data, multipart data và body.

~~~java
Mono<ServerResponse> describe(ServerRequest request) {
    String id = request.pathVariable("id");
    String agent = request.headers().firstHeader("User-Agent");
    String query = request.queryParam("q").orElse("");

    return ServerResponse.ok().bodyValue(
        "id=" + id + ", q=" + query + ", agent=" + agent
    );
}
~~~

Trong code production, tránh đưa toàn bộ header/cookie nhạy cảm vào log hoặc response. Chỉ lấy trường cần thiết.

### 8.2. Đọc request body thành Mono

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateUserRequest.class)
        .flatMap(input -> service.create(input.name())
            .flatMap(user -> ServerResponse
                .created(URI.create("/api/users/" + user.id()))
                .bodyValue(user)));
}
~~~

`bodyToMono` decode một body thành object. Việc đọc và decode diễn ra reactive; handler compose publisher bằng `flatMap` để chờ service mà không gọi `block()`.

Nếu body có thể vắng mặt, cần quyết định semantics:

~~~java
return request.bodyToMono(CreateUserRequest.class)
    .flatMap(this::save)
    .switchIfEmpty(
        ServerResponse.badRequest().bodyValue("Request body is required")
    );
~~~

Nếu body bắt buộc mà không có, trả 400 hoặc status phù hợp với API. Nếu body malformed hoặc không thể decode, WebFlux có thể phát lỗi như `ServerWebInputException`; hãy xử lý tập trung hoặc chuyển thành response có chủ đích.

### 8.3. Đọc stream body thành Flux

~~~java
Mono<ServerResponse> importEvents(ServerRequest request) {
    Flux<EventInput> events =
        request.bodyToFlux(EventInput.class);

    return service.importEvents(events)
        .then(ServerResponse.accepted().build());
}
~~~

`bodyToFlux` phù hợp khi request chứa nhiều phần tử hoặc dữ liệu streaming. Không gom toàn bộ stream vào list nếu kích thước lớn hoặc cần xử lý từng phần tử. Hãy lưu ý backpressure và đảm bảo lỗi ở bất kỳ phần tử nào được xử lý đúng.

### 8.4. Tạo ServerResponse

| API | Ý nghĩa |
| --- | --- |
| `ServerResponse.ok()` | 200 OK |
| `ServerResponse.created(uri)` | 201 Created kèm Location |
| `ServerResponse.accepted()` | 202 Accepted |
| `ServerResponse.noContent()` | 204 No Content |
| `ServerResponse.badRequest()` | 400 Bad Request |
| `ServerResponse.notFound()` | 404 Not Found |
| `ServerResponse.status(code)` | Status tùy chỉnh |

Dùng `bodyValue(value)` cho một giá trị đã có; dùng `body(publisher, elementClass)` cho publisher; dùng `build()` khi không có body.

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
        .flatMap(user -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(user))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Đoạn này biến kết quả empty thành 404. Nếu lỗi xảy ra, nó vẫn là onError; cần mapping lỗi riêng theo nghiệp vụ.

## 9. Validation và xử lý lỗi trong functional handler

Functional endpoint vẫn dùng được validation của Spring. Có thể inject Validator hoặc dùng Bean Validation theo cấu hình ứng dụng.

Ví dụ validation đơn giản:

~~~java
private Mono<ServerResponse> validateAndCreate(
        CreateUserRequest input) {
    if (input.name() == null || input.name().isBlank()) {
        return ServerResponse.badRequest()
            .bodyValue("name is required");
    }

    return service.create(input.name())
        .flatMap(user -> ServerResponse
            .created(URI.create("/api/users/" + user.id()))
            .bodyValue(user));
}
~~~

Handler gọi:

~~~java
return request.bodyToMono(CreateUserRequest.class)
    .flatMap(this::validateAndCreate)
    .switchIfEmpty(ServerResponse.badRequest().build());
~~~

Với validation phức tạp, dùng Spring Validator hoặc Jakarta Bean Validation. Khi phát hiện lỗi, có thể ném `ServerWebInputException` để WebFlux xử lý theo error handling đã cấu hình, hoặc map sang ServerResponse cụ thể.

### 9.1. onErrorResume trong handler

~~~java
Mono<ServerResponse> response = service.findById(id)
    .flatMap(user -> ServerResponse.ok().bodyValue(user))
    .switchIfEmpty(ServerResponse.notFound().build())
    .onErrorResume(IllegalArgumentException.class,
        error -> ServerResponse.badRequest()
            .bodyValue("Invalid identifier"));
~~~

Chỉ map loại lỗi mà handler hiểu rõ. Đừng biến mọi lỗi thành 400: lỗi database, lỗi mạng và bug lập trình có thể cần response 5xx hoặc error handler chung.

## 10. Filter: before, after và HandlerFilterFunction

Filter thêm hành vi bao quanh handler mà không lặp code ở từng route.

- `before(Function<ServerRequest, ServerRequest>)`: biến đổi request trước handler, ví dụ thêm header nội bộ.
- `after(BiFunction<ServerRequest, ServerResponse, ServerResponse>)`: quan sát hoặc biến đổi response sau handler.
- `filter(HandlerFilterFunction)`: nhận request và handler tiếp theo, có thể gọi tiếp hoặc trả response sớm.

Ví dụ log response:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .filter((request, next) ->
            next.handle(request)
                .doOnNext(response ->
                    System.getLogger("routes").log(
                        System.Logger.Level.INFO,
                        request.methodName() + " " + request.path()
                            + " -> " + response.statusCode()
                    )))
        .build();
~~~

Filter có thể chặn request trước handler:

~~~java
.filter((request, next) -> {
    String token = request.headers().firstHeader("X-Internal-Token");
    if (!"expected-value".equals(token)) {
        return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
    }
    return next.handle(request);
})
~~~

Đây chỉ là minh họa cơ chế. Trong ứng dụng thật, không hard-code token; dùng Spring Security hoặc cơ chế xác thực có quản lý secret, expiry và phân quyền. Router filter không thay thế security chain.

**Phạm vi filter trong nested route:** filter gắn vào builder áp dụng cho các route builder đó tạo. Filter đặt trong nested builder có thể chỉ áp dụng cho nhóm nested; filter cấp ngoài có thể áp dụng cho cả route nested. Đọc vị trí filter trong cây builder để tránh bỏ sót route.

## 11. Tổ chức route theo module trong Spring Boot

Một cấu trúc dễ duy trì:

~~~text
src/main/java/demo/
  DemoApplication.java
  user/
    User.java
    CreateUserRequest.java
    UserService.java
    UserHandler.java
    UserRoutes.java
  order/
    OrderHandler.java
    OrderRoutes.java
~~~

Vai trò:

- `UserRoutes` chỉ khai báo method/path/predicate và nối tới handler.
- `UserHandler` đọc request, gọi service và tạo response.
- `UserService` chứa nghiệp vụ và truy cập dữ liệu.
- DTO/domain model mô tả dữ liệu vào/ra.
- `DemoApplication` khởi động Spring Boot.

Ví dụ cấu hình bean:

~~~java
@Configuration
class UserRoutes {
    @Bean
    RouterFunction<ServerResponse> userRouter(UserHandler handler) {
        return RouterFunctions.route()
            .path("/api/users", users -> users
                .GET(handler::list)
                .GET("/{id}", handler::get)
                .POST(handler::create))
            .build();
    }
}
~~~

Spring Boot WebFlux starter tự cấu hình các thành phần cần thiết để chạy RouterFunction bean trong DispatcherHandler. Hạ tầng gồm RouterFunctionMapping để tìm router, HandlerFunctionAdapter để gọi handler và ServerResponseResultHandler để ghi response.

Có thể dùng functional endpoints cùng annotation-based controllers trong một ứng dụng. Quy hoạch path và thứ tự router rõ ràng để không có hai endpoint cùng nhận một request ngoài ý muốn.

## 12. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Ví dụ sau xây dựng API user bằng WebFlux.fn. Nó minh họa GET danh sách, GET theo ID, POST tạo user, predicate JSON, router builder, handler class và kiểm thử WebTestClient.

### 12.1. Cấu trúc thư mục

~~~text
functional-router-demo/
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    User.java
    CreateUserRequest.java
    UserService.java
    UserHandler.java
    UserRoutes.java
  src/test/java/demo/
    UserRoutesTest.java
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

Spring Boot quản lý phiên bản Spring Framework, Reactor và dependency tương thích qua dependency management. Không tự ghim phiên bản Spring Framework hoặc Reactor riêng nếu chưa có lý do tương thích.

### 12.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.4. User.java và CreateUserRequest.java

~~~java
package demo;

public record User(long id, String name) {
}
~~~

~~~java
package demo;

public record CreateUserRequest(String name) {
}
~~~

### 12.5. UserService.java

~~~java
package demo;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class UserService {
    private final ConcurrentMap<Long, User> users =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    public UserService() {
        users.put(1L, new User(1L, "Mai"));
    }

    public Flux<User> findAll() {
        return Flux.defer(() -> Flux.fromIterable(
            users.values().stream()
                .sorted(Comparator.comparingLong(User::id))
                .toList()
        ));
    }

    public Mono<User> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(users.get(id)));
    }

    public Mono<User> create(String name) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            User user = new User(id, name);
            users.put(id, user);
            return user;
        });
    }
}
~~~

Service dùng ConcurrentHashMap để demo lưu dữ liệu trong bộ nhớ. Trong ứng dụng thật, thay bằng repository reactive hoặc nguồn dữ liệu phù hợp. `defer` và `fromSupplier` khiến thao tác đọc/ghi được thực hiện khi subscription chạy.

### 12.6. UserHandler.java

~~~java
package demo;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@Component
public class UserHandler {
    private final UserService service;

    public UserHandler(UserService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.findAll(), User.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException error) {
            return ServerResponse.badRequest().build();
        }

        return service.findById(id)
            .flatMap(user -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(user))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateUserRequest.class)
            .flatMap(input -> {
                if (input.name() == null || input.name().isBlank()) {
                    return ServerResponse.badRequest()
                        .bodyValue("name is required");
                }

                return service.create(input.name())
                    .flatMap(user -> ServerResponse
                        .created(URI.create("/api/users/" + user.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(user));
            })
            .switchIfEmpty(ServerResponse.badRequest()
                .bodyValue("request body is required"))
            .onErrorResume(ServerWebInputException.class, error ->
                ServerResponse.badRequest()
                    .bodyValue("invalid request body"));
    }
}
~~~

Handler trả `Mono<ServerResponse>` cho mọi nhánh. GET parse ID và trả 404 khi service empty. POST đọc body JSON, kiểm tra name, tạo user rồi trả 201 với Location. Lỗi decode request được map thành 400. Ứng dụng thật nên dùng validator và error body chuẩn hóa.

### 12.7. UserRoutes.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class UserRoutes {
    @Bean
    RouterFunction<ServerResponse> userRoutes(UserHandler handler) {
        return RouterFunctions.route()
            .GET("/api/users", handler::list)
            .GET("/api/users/{id}", handler::get)
            .POST("/api/users",
                RequestPredicates.contentType(MediaType.APPLICATION_JSON),
                handler::create)
            .build();
    }
}
~~~

Route POST chỉ khớp khi request có Content-Type JSON. Predicate thuộc phần định tuyến; handler chịu trách nhiệm decode và xử lý body. Nếu cần kiểm tra Accept header, kết hợp thêm `RequestPredicates.accept(MediaType.APPLICATION_JSON)`.

### 12.8. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc khi đã cài Gradle:

~~~bash
gradle bootRun
~~~

Gọi API:

~~~bash
curl -i http://localhost:8080/api/users
curl -i http://localhost:8080/api/users/1
curl -i http://localhost:8080/api/users/99
curl -i -X POST http://localhost:8080/api/users -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"An"}'
~~~

Các kết quả chính:

| Request | Status dự kiến | Nội dung |
| --- | --- | --- |
| GET /api/users | 200 | JSON array có user Mai |
| GET /api/users/1 | 200 | JSON user Mai |
| GET /api/users/99 | 404 | Không có user |
| POST /api/users với name An | 201 | JSON user mới, Location /api/users/2 |
| POST không có body | 400 | Thông báo request body required |
| POST với name rỗng | 400 | Thông báo name is required |

Dữ liệu trong demo chỉ lưu trong RAM và được khởi tạo lại khi ứng dụng restart.

## 13. Kiểm thử route bằng WebTestClient

Có thể test functional router trực tiếp hoặc test cả ứng dụng. Với Spring Boot, dùng `@SpringBootTest` và `@AutoConfigureWebTestClient` để gửi HTTP request qua server test.

Tạo `src/test/java/demo/UserRoutesTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UserRoutesTest {
    @Autowired
    WebTestClient client;

    @Test
    void listUsersReturnsJson() {
        client.get()
            .uri("/api/users")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(1)
            .jsonPath("$[0].name").isEqualTo("Mai");
    }

    @Test
    void existingUserReturns200() {
        client.get()
            .uri("/api/users/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(User.class)
            .isEqualTo(new User(1L, "Mai"));
    }

    @Test
    void missingUserReturns404() {
        client.get()
            .uri("/api/users/999")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .isEmpty();
    }

    @Test
    void createUserReturns201AndLocation() {
        client.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateUserRequest("An"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals("Location", "/api/users/2")
            .expectBody(User.class)
            .isEqualTo(new User(2L, "An"));
    }

    @Test
    void emptyCreateBodyReturns400() {
        client.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Chạy `./gradlew test`. Năm test kiểm tra route được đăng ký, handler được gọi, status/header/body và nhánh body rỗng. Với service lưu RAM, nếu chạy test song song hoặc dùng cùng context lâu dài, cần cô lập dữ liệu test hoặc reset repository giữa test.

Có thể test router độc lập bằng `WebTestClient.bindToRouterFunction(router).build()` khi muốn kiểm tra route mà không khởi động Spring Boot server. Cách đó hữu ích cho unit test nhanh; integration test xác minh thêm việc Spring phát hiện RouterFunction bean và kết nối với WebFlux runtime.

## 14. Kết hợp functional endpoints với annotation-based controllers

WebFlux.fn và controller annotation cùng chạy trên reactive core. Một ứng dụng có thể có controller annotation cho endpoint CRUD thông thường, functional router cho nhóm endpoint cần khai báo tập trung và handler class để tái sử dụng logic xử lý request.

Hạ tầng WebFlux dùng RouterFunctionMapping để phát hiện router beans, HandlerFunctionAdapter để gọi handler và ServerResponseResultHandler để ghi response. Không cần tự gọi router từ controller hoặc tự ghi body vào server response.

Nếu hai cơ chế cùng khai báo một path/method, việc xử lý phụ thuộc mapping order và cấu hình. Tránh khai báo trùng hoặc kiểm tra thứ tự mapping có chủ đích. Khi route thuộc module riêng, đặt prefix rõ ràng như `/api/internal` hoặc `/api/events` giúp giảm xung đột.

## 15. Serving resources và các tính năng route nâng cao

Functional router cũng có thể phục vụ resource tĩnh. Ví dụ map `/resources/**` tới thư mục resource:

~~~java
Resource location = new FileUrlResource("public-resources/");
RouterFunction<ServerResponse> resources =
    RouterFunctions.resources("/resources/**", location);
~~~

Có thể dùng `RouterFunctions.route().resource(predicate, resource).build()` để redirect một nhóm path về resource, ví dụ index của Single Page Application. Cần cấu hình đường dẫn và quyền truy cập file cẩn thận; không expose tùy tiện thư mục nhạy cảm.

Một số tính năng khác:

- **API version predicate:** route có thể khớp version khi đã bật API versioning trong WebFlux configuration.
- **CORS:** functional endpoints hỗ trợ CORS thông qua `CorsWebFilter`.
- **Custom predicate:** tạo RequestPredicate riêng khi điều kiện route không nằm trong factory có sẵn.
- **Nested predicate:** gom route theo path, Accept header hoặc điều kiện chung.
- **Router composition:** ghép router của các module bằng `and`, `add` hoặc `andRoute`.

Không nên đưa điều kiện nghiệp vụ phức tạp vào RequestPredicate. Route nên quyết định request thuộc endpoint nào; handler/service quyết định request hợp lệ và thực hiện nghiệp vụ ra sao.

## 16. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khai báo route tổng quát trước route cụ thể | Route cụ thể có thể bị route trước che | Đặt route tĩnh/cụ thể trước |
| Quên gọi `build()` | Chưa hoàn tất RouterFunction builder | Kết thúc builder bằng `build()` |
| Handler trả kiểu không phải `Mono<ServerResponse>` | Không đúng hợp đồng WebFlux.fn reactive | Trả publisher của ServerResponse |
| Gọi `subscribe()` trong handler | Tách side effect khỏi lifecycle HTTP request | Compose Mono/Flux và return publisher |
| Gọi `block()` trong handler | Chặn event-loop | Dùng map/flatMap và reactive service |
| Dùng path variable mà không parse/validate | Lỗi parse có thể thành 500 ngoài ý muốn | Parse có kiểm soát và trả 400 |
| Không xử lý empty từ repository | Không có response nghiệp vụ rõ ràng | Dùng switchIfEmpty để trả 404 hoặc kết quả rỗng phù hợp |
| Nhầm predicate với validation nghiệp vụ | Request bị định tuyến sai hoặc logic bị giấu trong route | Predicate chỉ kiểm tra điều kiện định tuyến |
| Quên kiểm tra Content-Type | Handler có thể decode body không đúng format | Thêm contentType predicate và xử lý decode error |
| Ghép nhiều router không xét thứ tự | Route đầu tiên có thể nhận request của module khác | Kiểm tra path collision và order |
| Đặt filter sai phạm vi nested route | Một số endpoint không đi qua filter dự kiến | Xem builder nào tạo route và vị trí filter |
| Dùng router filter làm thay thế bảo mật | Có thể bỏ sót authentication/authorization chuẩn | Dùng Spring Security; filter route chỉ bổ sung logic cục bộ |
| Gom body Flux lớn vào List | Tốn RAM và mất streaming | Xử lý publisher trực tiếp |
| Bỏ qua lỗi decode JSON | Client nhận response không nhất quán | Map ServerWebInputException/validation errors |
| Dùng cùng một path ở controller và functional route | Mapping phụ thuộc order, khó debug | Tránh trùng path hoặc cấu hình order có chủ đích |
| Tạo route bean nhưng không nằm trong component scan | Spring không phát hiện router | Đặt @Configuration trong package scan hoặc import cấu hình |
| Nghĩ route không khớp luôn tự tạo 404 từ handler | Handler chưa được gọi; request đi qua mapping khác hoặc fallback | Kiểm tra toàn bộ router/handler mapping |
| Trả body publisher mà không chọn media type phù hợp | Codec hoặc client có thể không xử lý đúng | Chọn Content-Type/Accept và codec phù hợp |

## 17. Checklist thiết kế RouterFunction

Trước khi đưa route vào ứng dụng, kiểm tra:

1. Method và path có mô tả đúng endpoint không?
2. Có predicate cho Accept/Content-Type/header/query cần thiết không?
3. Route có bị một route tổng quát khai báo trước che không?
4. Các route cùng prefix có thể gom bằng nested route không?
5. Handler có đúng chữ ký `Mono<ServerResponse>` không?
6. Body request được decode thành kiểu dữ liệu phù hợp không?
7. Body rỗng, JSON lỗi và validation failure được xử lý thế nào?
8. Empty service result có semantics 404, list rỗng hay fallback?
9. Handler có compose reactive publisher, tránh block/subscribe thủ công không?
10. Filter có đúng phạm vi và không thay thế security chain không?
11. Các RouterFunction bean có path collision với nhau hoặc controller annotation không?
12. Đã test status, header, body và route không khớp bằng WebTestClient chưa?

| Nhu cầu | Cách khai báo |
| --- | --- |
| Route GET đơn giản | `GET("/path", handler)` |
| Route POST có predicate | `POST("/path", predicate, handler)` |
| Điều kiện kết hợp | `predicate.and(other)` / `or(other)` |
| Prefix chung | `path("/prefix", builder -> ...)` |
| Ghép router module | `routerA.and(routerB)` |
| Thêm route vào router đã có | `andRoute(predicate, handler)` |
| Thêm log/chặn request | `filter((request, next) -> ...)` |
| Thay đổi request trước handler | `before(request -> ...)` |
| Quan sát response sau handler | `after((request, response) -> ...)` |
| Phục vụ static resource | `RouterFunctions.resources(...)` |
| Kiểm thử functional route | `WebTestClient.bindToRouterFunction(router)` |

## 18. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `RouterFunction` và `HandlerFunction` khác nhau thế nào?

**Đáp án:** RouterFunction tìm handler phù hợp với request. HandlerFunction xử lý request và trả `Mono<ServerResponse>`.

**Câu 2.** Vì sao handler WebFlux.fn trả `Mono<ServerResponse>`?

**Đáp án:** Việc đọc dữ liệu, gọi service và tạo response có thể bất đồng bộ. Mono biểu diễn response được phát sau khi chuỗi reactive hoàn tất.

**Câu 3.** `GET("/users/{id}")` có tự chuyển id thành long không?

**Đáp án:** Không. `request.pathVariable("id")` trả String; handler phải parse và xử lý dữ liệu không hợp lệ.

**Câu 4.** `accept(APPLICATION_JSON)` và `contentType(APPLICATION_JSON)` khác nhau thế nào?

**Đáp án:** Accept mô tả định dạng response client chấp nhận; Content-Type mô tả định dạng body của request gửi lên.

**Câu 5.** Vì sao route `/users/search` nên đứng trước `/users/{id}`?

**Đáp án:** RouterFunction xét tuyến theo thứ tự. Route biến có thể khớp chuỗi search, khiến route tìm kiếm phía sau không được gọi.

**Câu 6.** Khi nào nên dùng nested route?

**Đáp án:** Khi nhiều route cùng path prefix hoặc cùng predicate. Nested route giảm lặp và làm nhóm endpoint rõ hơn.

**Câu 7.** Filter khác handler thế nào?

**Đáp án:** Handler thực hiện logic endpoint. Filter bao quanh handler để thêm hành vi chung, có thể gọi handler tiếp theo hoặc trả response sớm.

**Câu 8.** Có thể dùng RouterFunction bean cùng @RestController không?

**Đáp án:** Có. Spring WebFlux hỗ trợ cả functional endpoints và annotated controllers trong cùng ứng dụng; cần tránh route collision và kiểm tra mapping order.

**Câu 9.** Nếu service trả Mono.empty() khi GET resource theo ID, handler nên làm gì?

**Đáp án:** Nếu contract quy định resource không tồn tại là 404, dùng `switchIfEmpty(ServerResponse.notFound().build())`. Với collection search, list rỗng có thể là 200.

**Câu 10.** Có nên gọi `subscribe()` trong handler để lưu dữ liệu rồi trả response ngay không?

**Đáp án:** Không. Side effect tách khỏi request lifecycle có thể làm response trả trước khi lưu hoàn tất và lỗi không còn được truyền đúng. Hãy compose publisher và chỉ tạo response sau khi thao tác cần thiết hoàn tất.

**Câu 11.** Khi route không khớp, handler của route đó có được gọi không?

**Đáp án:** Không. RouterFunction không cung cấp handler cho request đó; framework tiếp tục xét router khác hoặc xử lý request không được định tuyến.

**Câu 12.** Cần kiểm thử functional route mà không khởi động server thật thì dùng gì?

**Đáp án:** `WebTestClient.bindToRouterFunction(router).build()` có thể bind trực tiếp RouterFunction để kiểm tra request/response.

## 19. Ghi nhớ và tài liệu chính thức

- `RouterFunctions.route()` tạo builder để khai báo tuyến HTTP bằng method, path và predicate.
- `RouterFunction` tìm handler; `HandlerFunction` xử lý request và trả `Mono<ServerResponse>`.
- `RequestPredicate` mô tả điều kiện khớp; dùng `and`, `or` và `negate` để kết hợp điều kiện.
- Router được đánh giá theo thứ tự; đặt route cụ thể trước route tổng quát.
- Dùng nested routes để gom path/predicate chung; dùng `and` hoặc `add` để ghép router theo module.
- `ServerRequest` đọc path/query/headers/body; `ServerResponse` tạo status, headers và body reactive.
- `before`, `after` và `filter` thêm hành vi chung; bảo đảm filter ở đúng phạm vi.
- Spring Boot WebFlux tự phát hiện RouterFunction bean và tích hợp nó vào DispatcherHandler.
- Kiểm thử route bằng WebTestClient; không gọi `block()` hoặc `subscribe()` thủ công trong handler.

Tài liệu chính thức:

1. [Spring Framework Reference — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): tổng quan, RouterFunction, HandlerFunction, RequestPredicate, nested routes, filter và cách chạy.
2. [Spring Framework Javadoc — RouterFunctions](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.html): builder, route composition, resources và utility.
3. [Spring Framework Javadoc — RequestPredicates](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): factory cho method, path, headers, query và media type.
4. [Spring Framework Javadoc — ServerRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): API đọc HTTP request và body.
5. [Spring Framework Javadoc — ServerResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): builder response, status, headers và body.
6. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử WebFlux endpoint và router.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): tự cấu hình Spring Boot WebFlux runtime.
