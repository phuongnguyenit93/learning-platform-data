# Nhóm tuyến với nest và quản lý thứ tự so khớp trong Spring WebFlux.fn

## 1. Vì sao cần nested routes?

Trong Spring WebFlux.fn, **RouterFunction** ánh xạ request tới **HandlerFunction**. Nhiều endpoint thường chia sẻ điều kiện như path prefix \`/api/v1/users\`, header \`Accept: application/json\`, kiểu body \`Content-Type: application/json\`, tenant hoặc phiên bản API. Nếu lặp lại các điều kiện đó trên từng route, cấu hình sẽ dài và dễ lệch.

**Nested route** gom các route vào một nhóm, đặt predicate chung ở bên ngoài rồi khai báo route con ở bên trong:

~~~text
/api/v1
   |
   +-- Accept: application/json
   |      +-- GET /users/search
   |      +-- GET /users/{id}
   |      +-- POST /users
   |
   +-- GET /health
~~~

Prefix \`/api/v1\` áp dụng cho mọi route trong nhóm. Predicate Accept JSON chỉ áp dụng cho nhóm users. Route health vẫn thuộc prefix API nhưng không bị ràng buộc bởi predicate JSON.

Cần hiểu hai việc cùng lúc: **nest** giúp gom route có predicate chung; **route order** quyết định route nào được chọn trước khi nhiều pattern có thể khớp cùng request.

## 2. RouterFunction và RequestPredicate

### 2.1. RouterFunction là gì?

Trong WebFlux.fn:

- **ServerRequest** đại diện request HTTP ở tầng functional.
- **HandlerFunction<T extends ServerResponse>** nhận ServerRequest và trả Mono của ServerResponse.
- **RouterFunction<T>** nhận ServerRequest và trả Mono chứa HandlerFunction nếu route khớp; nếu không khớp, nó hoàn tất rỗng.

~~~text
ServerRequest
     |
     v
RouterFunction
     |
     +-- khớp ------> Mono<HandlerFunction>
     |
     +-- không khớp -> Mono.empty()
~~~

RouterFunction chọn handler; HandlerFunction thực hiện nghiệp vụ và tạo ServerResponse. RouterFunction không nên truy vấn database hoặc thực hiện I/O.

### 2.2. RequestPredicate

**RequestPredicate** là điều kiện kiểm tra request có phù hợp với route hay không. Các predicate phổ biến trong \`RequestPredicates\`:

| Predicate | Ý nghĩa |
| --- | --- |
| \`GET(path)\`, \`POST(path)\`, \`PUT(path)\`, \`DELETE(path)\` | Kiểm tra HTTP method và path |
| \`method(HttpMethod)\` | Kiểm tra HTTP method |
| \`path(pattern)\` | Kiểm tra path theo pattern |
| \`accept(mediaType)\` | Kiểm tra header Accept của client |
| \`contentType(mediaType)\` | Kiểm tra Content-Type của request |
| \`queryParam(name, predicate)\` | Kiểm tra query parameter |
| \`headers(predicate)\` | Kiểm tra điều kiện trên headers |

Ví dụ:

~~~java
RouterFunctions.route()
        .GET("/products/{id}",
                RequestPredicates.accept(MediaType.APPLICATION_JSON),
                handler::find)
        .build();
~~~

Route cần thỏa method GET, path phù hợp và predicate Accept JSON. Overload GET của builder tự kết hợp method/path với predicate bổ sung.

### 2.3. Kết hợp predicate

RequestPredicate hỗ trợ:

- **\`RequestPredicate.and(RequestPredicate)\`**: cả hai predicate phải đúng.
- **\`RequestPredicate.or(RequestPredicate)\`**: ít nhất một predicate đúng.
- **\`RequestPredicate.negate()\`**: đảo kết quả predicate.

~~~java
RequestPredicate apiJson =
        RequestPredicates.path("/api/**")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RequestPredicate notHealth =
        RequestPredicates.path("/health").negate();
~~~

Khi dùng \`nest(apiJson, ...)\`, route con chỉ được xét nếu cả path API và Accept JSON đều phù hợp.

Phân biệt hai header: **Accept** cho biết media type client muốn nhận; **Content-Type** cho biết media type của body request đang gửi. Với POST JSON, có thể cần kiểm tra cả hai.

## 3. path(...) — nhóm theo path prefix

### 3.1. Ví dụ cơ bản

~~~java
RouterFunction<ServerResponse> userRoutes = RouterFunctions.route()
        .path("/users", users -> users
                .GET("/{id}", handler::find)
                .GET("", handler::list)
                .POST(handler::create))
        .build();
~~~

Đây là đoạn minh họa với handler đã có sẵn. Các route con được ghép vào prefix chung:

| Route bên trong | URL thực tế |
| --- | --- |
| \`GET("/{id}")\` | \`GET /users/{id}\` |
| \`GET("")\` | \`GET /users\` |
| \`POST(handler::create)\` | \`POST /users\` |

**\`path(String, Consumer<RouterFunctions.Builder>)\`** là cách tiện dụng để tạo nhóm route dùng chung prefix. Consumer nhận builder để khai báo route con.

### 3.2. Prefix nhiều cấp

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api", api -> api
                .path("/v1", v1 -> v1
                        .path("/users", users -> users
                                .GET("/{id}", handler::find)
                                .GET("", handler::list))))
        .build();
~~~

Các URL cuối cùng là \`GET /api/v1/users\` và \`GET /api/v1/users/{id}\`. Nesting nên phản ánh cấu trúc domain; tránh lồng quá nhiều cấp nếu chỉ làm code khó đọc.

### 3.3. path là dạng chuyên biệt của nest

\`path("/users", builder -> ...)\` là cú pháp tiện lợi cho nhóm route có path predicate chung. Khi cần nhóm theo điều kiện khác path, dùng \`nest(RequestPredicate, Consumer<RouterFunctions.Builder>)\`.

## 4. nest(...) — nhóm theo bất kỳ predicate nào

### 4.1. Nhóm theo Accept header

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/users", handler::list)
                .GET("/users/{id}", handler::find)
                .POST("/users", handler::create))
        .build();
~~~

Các route trong nhóm chỉ được xét khi predicate Accept JSON khớp. Cách này tránh lặp predicate trên từng route.

### 4.2. Kết hợp path và header

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/v1", api -> api
                .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/users", handler::list)
                        .GET("/users/{id}", handler::find)))
        .build();
~~~

Để route con được chọn, request phải thỏa prefix \`/api/v1\`, Accept JSON, method và path con. Về logic, các predicate được kết hợp theo quan hệ AND.

### 4.3. Nhóm theo predicate tùy chỉnh

~~~java
RequestPredicate internalClient = request ->
        request.headers().header("X-Client-Type").contains("internal");

RouterFunction<ServerResponse> internalRoutes =
        RouterFunctions.route()
                .nest(internalClient, internal -> internal
                        .GET("/reports", handler::listInternal))
                .build();
~~~

Đây là đoạn minh họa với handler đã có. Predicate tùy chỉnh nên **nhanh, xác định và không có side effect**. Không truy vấn database hoặc gọi HTTP blocking trong giai đoạn so khớp route.

Có thể dùng static \`RouterFunctions.nest(predicate, routerFunction)\` để lồng một router đã tạo; hoặc dùng builder \`nest(predicate, consumer)\` để xây router con tại chỗ. Cách builder thường dễ đọc khi khai báo route ứng dụng.

## 5. Quản lý thứ tự so khớp: first match

### 5.1. Route được đánh giá theo thứ tự composition

Trong WebFlux.fn:

1. Kiểm tra route đầu tiên.
2. Nếu route không khớp, chuyển sang route tiếp theo.
3. Dừng tại route đầu tiên tìm được HandlerFunction.
4. Nếu không route nào khớp, RouterFunction không cung cấp handler.

Vì vậy, khai báo **route cụ thể trước route tổng quát**.

Điều này khác với annotated controller. Với annotation-based mapping, Spring chọn mapping phù hợp nhất theo điều kiện so khớp và độ cụ thể. Với WebFlux.fn, không dựa vào cơ chế tự chọn route cụ thể nhất; thứ tự composition là điều cần quản lý.

### 5.2. Route tĩnh và route có path variable

Ví dụ sai:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/users/{id}", handler::find)
        .GET("/users/search", handler::search)
        .build();
~~~

Request \`GET /users/search\` cũng có thể khớp pattern \`/users/{id}\` với \`id = "search"\`. Vì route biến được khai báo trước, handler find có thể được chọn và route search phía sau không được xét.

Cách đúng:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/users/search", handler::search)
        .GET("/users/{id}", handler::find)
        .build();
~~~

Route tĩnh \`/users/search\` được xét trước; route có biến nhận các path còn lại phù hợp.

### 5.3. Route cụ thể và wildcard

Giả sử có \`GET /files/latest\`, \`GET /files/{name}\` và \`GET /files/**\`. Nên khai báo:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/files/latest", handler::latest)
        .GET("/files/{name}", handler::byName)
        .GET("/files/**", handler::underDirectory)
        .build();
~~~

Route cụ thể nhất đứng trước, route rộng nhất đứng cuối. Nếu wildcard đứng đầu, nó có thể nhận request mà handler chuyên biệt cần xử lý.

### 5.4. Kết hợp nhiều RouterFunction

~~~java
RouterFunction<ServerResponse> publicRoutes = RouterFunctions.route()
        .GET("/public/status", handler::status)
        .build();

RouterFunction<ServerResponse> adminRoutes = RouterFunctions.route()
        .GET("/admin/status", handler::adminStatus)
        .build();

RouterFunction<ServerResponse> allRoutes =
        publicRoutes.and(adminRoutes);
~~~

Nếu publicRoutes không tìm được handler, router tiếp theo được xét. Nếu publicRoutes đã khớp, adminRoutes không thay thế handler đó. Builder cũng hỗ trợ \`add\` và \`andRoute\`. Trong nội bộ Spring, RouterFunctionMapping kết hợp router bean theo thứ tự qua **\`RouterFunction.andOther(...)\`**.

## 6. Thứ tự trong nested routes

### 6.1. Route con vẫn giữ thứ tự khai báo

~~~java
.path("/api/v1", api -> api
        .path("/users", users -> users
                .GET("/search", handler::search)
                .GET("/{id}", handler::find)
                .GET("/**", handler::fallback)))
~~~

Thứ tự trong nhóm users là \`/search\`, \`/{id}\`, rồi \`/**\`. Prefix chỉ thêm điều kiện chung; nó không tự sắp xếp route con theo độ cụ thể.

### 6.2. Route ngoài nhóm và route trong nhóm

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/v1", api -> api
                .GET("/health", handler::health)
                .path("/users", users -> users
                        .GET("/search", handler::search)
                        .GET("/{id}", handler::find)))
        .GET("/health", handler::rootHealth)
        .build();
~~~

Route \`/api/v1/health\` và \`/health\` khác path nên không xung đột. Nếu các nhóm có predicate chồng lấn, hãy đọc thứ tự composition và kiểm thử request đại diện. Đừng giả định nested route luôn được ưu tiên hơn top-level route hoặc ngược lại trong mọi cấu trúc.

### 6.3. Predicate nhóm không khớp

Nếu outer predicate của nest không khớp, các route con không được xét. Ví dụ nhóm Accept JSON không được chọn khi header Accept không đáp ứng predicate. Nếu ứng dụng cần response rõ ràng cho media type không hỗ trợ, hãy thiết kế route fallback hoặc cơ chế xử lý lỗi phù hợp; không mặc định mọi predicate mismatch tự động tạo HTTP 406.

## 7. Thứ tự giữa nhiều RouterFunction bean

Trong cấu hình Spring WebFlux, **RouterFunctionMapping** phát hiện các bean RouterFunction, sắp xếp chúng và kết hợp thành một RouterFunction tổng hợp. Khi chia route thành nhiều bean, thứ tự giữa các bean cũng có thể ảnh hưởng route nào được chọn trước.

~~~java
@Configuration
class RouteConfiguration {

    @Bean
    @Order(0)
    RouterFunction<ServerResponse> specificRoutes(SpecificHandler handler) {
        return RouterFunctions.route()
                .GET("/reports/latest", handler::latest)
                .build();
    }

    @Bean
    @Order(10)
    RouterFunction<ServerResponse> generalRoutes(GeneralHandler handler) {
        return RouterFunctions.route()
                .GET("/reports/{id}", handler::find)
                .build();
    }
}
~~~

Đây là đoạn cấu hình minh họa. \`@Order(0)\` được sắp trước \`@Order(10)\`; route cụ thể được ghép trước route tổng quát.

Khuyến nghị:

- Route có liên quan và dễ chồng lấn nên nằm trong một builder để thứ tự hiển thị ngay tại một nơi.
- Nếu chia nhiều bean theo module, đặt \`@Order\` rõ ràng khi thứ tự có ý nghĩa.
- Không dựa vào thứ tự khởi tạo bean hoặc tên method để suy ra precedence.
- Tránh để hai bean cùng order chứa route chồng lấn nếu thứ tự giữa chúng không được thiết kế rõ.
- Dùng integration test cho route có thể chồng lấn.

## 8. Nested routes và filter: phạm vi áp dụng

Router builder cung cấp ba cách xử lý xuyên suốt route:

| API | Vai trò |
| --- | --- |
| \`before(...)\` | Biến đổi ServerRequest trước khi gọi handler |
| \`after(...)\` | Biến đổi hoặc quan sát ServerResponse sau khi handler tạo response |
| \`filter(...)\` | Bọc HandlerFunction tiếp theo; có thể cho phép hoặc chặn việc gọi handler |

### 8.1. before: xử lý request trước handler

ServerRequest có contract bất biến. Nếu muốn bổ sung header cho request chuyển tới handler, tạo request mới:

~~~java
.before(request -> ServerRequest.from(request)
        .header("X-Route-Scope", "users")
        .build())
~~~

Đây là đoạn minh họa. Khi đặt \`before\` trong builder của nested route, nó chỉ áp dụng cho các route được tạo trong builder đó. Route sibling hoặc top-level khác không tự động nhận biến đổi này.

### 8.2. after: xử lý response sau handler

~~~java
.after((request, response) -> {
    logResponse(request.path(), response.statusCode());
    return response;
})
~~~

Đây là đoạn minh họa với hàm logResponse của ứng dụng. \`after\` nhận request và response, sau đó trả response đã xử lý. Khi đặt trên builder ngoài cùng, filter áp dụng cho tất cả route được tạo bởi builder đó, kể cả route nested bên trong.

### 8.3. filter và HandlerFilterFunction

API \`filter(...)\` nhận một **HandlerFilterFunction**. Filter function nhận ServerRequest và HandlerFunction tiếp theo, rồi trả Publisher của ServerResponse:

~~~java
.filter((request, next) -> {
    if (accessPolicy.allow(request)) {
        return next.handle(request);
    }
    return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
})
~~~

Đây là đoạn minh họa với accessPolicy do ứng dụng cung cấp. Nếu điều kiện không đạt, filter trả response mà không gọi \`next.handle(request)\`. Nếu điều kiện đạt, nó chuyển request tới filter/handler tiếp theo.

Filter route-level hữu ích cho logic chỉ áp dụng một nhóm functional routes. Với bảo mật ứng dụng tổng thể, cân nhắc Spring Security và WebFilter chain; không dùng một header demo làm giải pháp bảo mật production.

### 8.4. Filter ở nested builder và builder ngoài

~~~java
RouterFunctions.route()
        .path("/api/v1", api -> api
                .path("/users", users -> users
                        .GET("/{id}", handler::find)
                        .before(this::addUserHeader))
                .GET("/health", handler::health))
        .after(this::logAllResponses)
        .build();
~~~

- \`before(addUserHeader)\` đặt trong nhóm users nên chỉ áp dụng cho route được tạo trong nhóm users.
- \`after(logAllResponses)\` đặt ở builder ngoài nên áp dụng cho tất cả route được tạo bởi builder, gồm users và health.

Phạm vi filter được quyết định bởi vị trí đặt nó trong builder. Khi di chuyển filter vào hoặc ra khỏi nested group, hãy kiểm tra lại route nào bị ảnh hưởng.

## 9. Predicate mismatch, 404 và lỗi nội dung

Predicate không khớp có nghĩa route đó không được chọn. Nó không có nghĩa handler đã chạy và trả response lỗi.

| Tình huống | Ý nghĩa |
| --- | --- |
| Path không khớp prefix nest | Nhóm route không được xét |
| Method không khớp | Route không được chọn |
| Accept predicate không khớp | Route yêu cầu media type đó không được chọn |
| Content-Type predicate không khớp | Route yêu cầu loại body đó không được chọn |
| Handler được gọi nhưng trả ServerResponse.notFound() | Handler chủ động tạo HTTP 404 |
| Không route nào khớp sau khi xét toàn bộ RouterFunction | Không có handler functional phù hợp; xử lý not-found của framework/application quyết định response cuối |

Nếu API cần phân biệt **404 Not Found** với **405 Method Not Allowed**, hoặc **406 Not Acceptable** với **415 Unsupported Media Type**, hãy thiết kế fallback/error handling rõ ràng và kiểm thử theo HTTP contract. Không dựa vào việc chỉ thêm predicate là framework chắc chắn trả đúng status theo ý nghiệp vụ trong mọi cấu hình.

## 10. Ví dụ Java 17+ chạy được: nested routes và route order

Ví dụ xây dựng Spring Boot WebFlux app có prefix chung \`/api/v1\`, nhóm users chỉ nhận Accept JSON, route tĩnh search đứng trước route động id, và route health nằm ngoài nested Accept predicate.

### 10.1. Cấu trúc dự án

~~~text
webflux-nested-routes/
├── pom.xml
└── src/
    ├── main/java/example/routes/
    │   ├── DemoApplication.java
    │   └── ApiRoutes.java
    └── test/java/example/routes/
        └── ApiRoutesTest.java
~~~

### 10.2. pom.xml

Ví dụ dùng Spring Boot **3.5.5** và Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-nested-routes</artifactId>
    <version>1.0.0</version>

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

### 10.3. DemoApplication.java

~~~java
package example.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. ApiRoutes.java

~~~java
package example.routes;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.function.server.RequestPredicates;

import reactor.core.publisher.Mono;

@Configuration
public class ApiRoutes {

    @Bean
    RouterFunction<ServerResponse> apiRoutes() {
        return RouterFunctions.route()
                .path("/api/v1", api -> api
                        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/users/search", this::searchUsers)
                                        .GET("/users/{id}", this::findUser))
                        .GET("/health", this::health))
                .build();
    }

    private Mono<ServerResponse> searchUsers(ServerRequest request) {
        String query = request.queryParam("q").orElse("");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("route", "search", "query", query));
    }

    private Mono<ServerResponse> findUser(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("route", "user", "id", id));
    }

    private Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("UP");
    }
}
~~~

Điểm cần quan sát:

- \`path("/api/v1", ...)\` tạo prefix dùng chung.
- \`nest(accept(APPLICATION_JSON), ...)\` áp dụng Accept JSON cho route users.
- \`GET("/users/search")\` đứng trước \`GET("/users/{id}")\`, nên từ khóa search không bị hiểu thành id.
- \`GET("/health")\` nằm ngoài nested Accept predicate nhưng vẫn trong prefix /api/v1.
- Handler trả Mono<ServerResponse>; không gọi subscribe() hoặc block() trong route.

### 10.5. Chạy ứng dụng

Tại thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Tìm kiếm users:

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/v1/users/search?q=reactor"
~~~

Response có status **200 OK** và JSON chứa:

~~~json
{
  "route": "search",
  "query": "reactor"
}
~~~

Lấy user theo id:

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/v1/users/42"
~~~

Response có status **200 OK** và JSON chứa:

~~~json
{
  "route": "user",
  "id": "42"
}
~~~

Health endpoint:

~~~bash
curl -i http://localhost:8080/api/v1/health
~~~

Body:

~~~text
UP
~~~

Thứ tự key trong JSON không phải contract routing.

### 10.6. Kiểm thử route order bằng WebTestClient

Tệp **ApiRoutesTest.java**:

~~~java
package example.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiRoutesTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void staticSearchRouteWinsBeforePathVariableRoute() {
        webTestClient.get()
                .uri("/api/v1/users/search?q=reactor")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.route").isEqualTo("search")
                .jsonPath("$.query").isEqualTo("reactor");
    }

    @Test
    void pathVariableRouteReceivesUserId() {
        webTestClient.get()
                .uri("/api/v1/users/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.route").isEqualTo("user")
                .jsonPath("$.id").isEqualTo("42");
    }

    @Test
    void healthRouteIsOutsideJsonNestedPredicate() {
        webTestClient.get()
                .uri("/api/v1/health")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("UP");
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Ba test xác nhận route static search được chọn thay vì route biến id, route biến xử lý URL user bình thường, và health chia sẻ prefix nhưng không bị ràng buộc bởi nested Accept JSON.

## 11. Ví dụ lỗi thường gặp và cách sửa

### 11.1. Route tổng quát đặt trước route cụ thể

**Sai:**

~~~java
RouterFunctions.route()
        .GET("/orders/{id}", handler::find)
        .GET("/orders/search", handler::search)
        .build();
~~~

**Đúng:**

~~~java
RouterFunctions.route()
        .GET("/orders/search", handler::search)
        .GET("/orders/{id}", handler::find)
        .build();
~~~

Nếu không sửa thứ tự, từ khóa search có thể bị xem như một id.

### 11.2. Lặp prefix và predicate

**Khó bảo trì:**

~~~java
RouterFunctions.route()
        .GET("/api/v1/users", acceptJson, handler::list)
        .GET("/api/v1/users/{id}", acceptJson, handler::find)
        .POST("/api/v1/users", acceptJson, handler::create)
        .build();
~~~

**Dễ đọc hơn:**

~~~java
RouterFunctions.route()
        .path("/api/v1", api -> api
                .nest(acceptJson, json -> json
                        .GET("/users", handler::list)
                        .GET("/users/{id}", handler::find)
                        .POST("/users", handler::create)))
        .build();
~~~

Nesting giảm duplication và giúp thay đổi prefix/predicate tại một điểm.

### 11.3. Đặt predicate ở sai cấp

Nếu đặt Accept JSON ở builder ngoài cùng, mọi route được tạo trong builder đó có thể bị áp dụng điều kiện JSON, kể cả health hoặc route trả text/plain. Đặt predicate đúng phạm vi: nhóm JSON bên trong nest, health text ở route sibling bên ngoài nhóm JSON, nhóm upload theo Content-Type phù hợp.

### 11.4. Dùng nhầm Accept và Content-Type

POST body JSON thường cần kiểm tra Content-Type của request; response JSON cần xét Accept mà client gửi. Hai predicate có thể được kết hợp, nhưng không thay thế nhau.

### 11.5. Nhiều RouterFunction bean nhưng không đặt order

Nếu hai bean có route chồng lấn, RouterFunctionMapping kết hợp chúng theo thứ tự bean. Dùng \`@Order\` hoặc gom route có liên quan vào một builder và kiểm thử precedence; không dựa vào thứ tự khởi tạo không rõ ràng.

### 11.6. Predicate tùy chỉnh làm I/O hoặc có side effect

Predicate được dùng trong giai đoạn tìm route. Không gọi database, remote service hoặc thao tác blocking trong predicate. Hãy để handler thực hiện nghiệp vụ sau khi route được chọn.

## 12. Checklist debug và thiết kế route order

Một thứ tự route dễ đọc thường là:

1. Route tĩnh đặc biệt: \`/search\`, \`/summary\`, \`/latest\`, \`/health\`.
2. Route có path variable: \`/{id}\`, \`/{id}/history\`.
3. Route wildcard/catch-all: \`/**\` hoặc resource fallback.
4. Fallback route nếu ứng dụng chủ động cần response tùy chỉnh.

Khi route sai, kiểm tra:

- Path, context path, prefix, dấu slash và path variable.
- HTTP method.
- Outer nest và inner predicate.
- Accept, Content-Type, query parameter và custom condition.
- Route biến/wildcard có đứng trước route tĩnh không.
- RouterFunction composition và thứ tự add/and.
- @Order khi có nhiều RouterFunction bean.
- Filter scope: before/filter/after đang đặt ở builder cấp nào.
- Response status, content type, body và lỗi deferred.
- Test request ranh giới: static, variable, unmatched path, wrong method và header không phù hợp.

Có thể bật log có chọn lọc cho package WebFlux trong môi trường development. Không bật DEBUG rộng trong production nếu log có thể chứa thông tin request nhạy cảm.

## 13. So sánh nhanh với annotated controller

| Chủ đề | WebFlux.fn | Annotated controller |
| --- | --- | --- |
| Khai báo route | RouterFunction builder | @RequestMapping, @GetMapping... |
| Nhóm prefix | path(...) hoặc nest(path(...)) | @RequestMapping ở class |
| Nhóm predicate | nest(RequestPredicate, ...) | Mapping conditions/annotation |
| Handler | HandlerFunction | Controller method |
| Thứ tự | Route composition first-match | Spring chọn mapping phù hợp nhất theo điều kiện |
| Filter theo route | before/after/filter trên builder | WebFilter, ControllerAdvice và cơ chế tương ứng |
| Phong cách | Functional, route và handler tách rõ | Annotation-driven |

Cả hai đều thuộc Spring WebFlux và có thể cùng tồn tại. Không nên chuyển toàn bộ controller sang functional chỉ để dùng nest; annotated controller đã có cách nhóm prefix bằng class-level @RequestMapping.

## 14. Ghi nhớ

- **path(prefix, builder)** gom route dùng chung path prefix.
- **nest(predicate, builder)** gom route dùng chung bất kỳ RequestPredicate nào, không chỉ path.
- **RequestPredicate.and/or/negate** giúp kết hợp điều kiện route.
- Nested route chỉ được xét khi predicate nhóm khớp; route con vẫn giữ thứ tự khai báo.
- **RouterFunction routes được đánh giá theo thứ tự composition**. Đặt route tĩnh/cụ thể trước route path variable và wildcard.
- Nhiều RouterFunction bean được RouterFunctionMapping sắp xếp và kết hợp bằng RouterFunction.andOther; đặt @Order khi thứ tự giữa bean có ý nghĩa.
- Filter đặt trong nested builder chỉ áp dụng cho phạm vi route tương ứng; filter ở builder ngoài có thể áp dụng cả route nested.
- Không làm I/O hoặc business logic trong RequestPredicate.
- Kiểm thử route precedence bằng WebTestClient để tránh regression khi thêm endpoint.

**Tài liệu chính thức:**
- [Spring Framework — Functional Endpoints (WebFlux.fn): predicates, route order, nested routes và filters](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework Javadoc — RouterFunctions.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html)
- [Spring Framework Javadoc — RouterFunctionMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/support/RouterFunctionMapping.html)
- [Spring Framework Javadoc — RequestPredicates](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html)
- [Spring Framework Reference — DispatcherHandler and WebFlux infrastructure](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
