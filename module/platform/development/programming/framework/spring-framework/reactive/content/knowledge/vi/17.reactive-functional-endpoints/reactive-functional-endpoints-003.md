# Kết hợp predicate đường dẫn, method, header và media type trong Spring WebFlux

## 1. Request predicate trong WebFlux.fn là gì?

Trong mô hình **functional endpoints** của Spring WebFlux, ta định tuyến HTTP request bằng `RouterFunction` thay vì khai báo `@RequestMapping` trên controller. Một `RouterFunction` kiểm tra request và chọn `HandlerFunction` tương ứng. Điều kiện để một route khớp được biểu diễn bằng **`RequestPredicate`**.

Một predicate nhận `ServerRequest` và trả về kết quả đúng/sai. Spring cung cấp các predicate dựng sẵn trong `RequestPredicates`, cho phép kiểm tra:

- **Đường dẫn (path):** request có đi tới `/api/reports/42`, `/users/{id}` hay một pattern phù hợp không?
- **HTTP method:** GET, POST, PUT, PATCH, DELETE, OPTIONS...
- **Header:** request có gửi `X-API-Version: v1`, `X-Client: partner` hoặc giá trị header phù hợp không?
- **Media type:** `Content-Type` của request body có phải JSON không, hoặc `Accept` có chấp nhận JSON không?

Một route thường cần **nhiều điều kiện cùng đúng**. Ví dụ: chỉ nhận `GET /api/reports/{id}` khi client gửi header phiên bản `X-API-Version: v1` và chấp nhận response JSON.

Mô hình tổng quát:

~~~text
HTTP request
    |
    v
RequestPredicate
    |
    +-- path khớp?
    +-- method đúng?
    +-- header đạt điều kiện?
    +-- media type tương thích?
    |
    +-- Tất cả điều kiện đúng --> HandlerFunction
    |
    +-- Không khớp ------------> Router thử route tiếp theo
~~~

`RequestPredicate` chỉ quyết định **route nào được chọn**. Nó không phải handler đọc body, không tự tạo response và không thay thế validation, authorization hoặc xử lý nghiệp vụ.

## 2. Các thành phần trong functional endpoint

Một functional endpoint có ba thành phần chính:

| Thành phần | Trách nhiệm | Kiểu tiêu biểu |
| --- | --- | --- |
| `ServerRequest` | Đại diện HTTP request: method, URI, path variables, headers, query params và body | `ServerRequest` |
| `RequestPredicate` | Kiểm tra request có thỏa điều kiện định tuyến không | `RequestPredicate` |
| `HandlerFunction` | Xử lý request đã được route chọn và tạo response reactive | `HandlerFunction<ServerResponse>` |

Handler function nhận `ServerRequest` và trả `Mono<ServerResponse>`. Request và response có API immutable; body được biểu diễn theo mô hình reactive. Ví dụ đọc JSON body:

~~~java
Mono<CreateReportRequest> body =
    request.bodyToMono(CreateReportRequest.class);
~~~

Một route trực tiếp có thể tạo bằng:

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route(
        RequestPredicates.GET("/api/reports/{id}"),
        handler::getReport
    );
~~~

Đây là đoạn minh họa cần có `handler` và method `getReport` trong ứng dụng. Với nhiều route, thường dùng builder `RouterFunctions.route()` hoặc ghép các `RouterFunction` bằng `and`.

## 3. Predicate đường dẫn: path

`RequestPredicates.path(String)` tạo predicate kiểm tra request path theo pattern. Spring WebFlux dùng cơ chế path pattern để hỗ trợ biến đường dẫn và các pattern phù hợp.

Ví dụ:

~~~java
RequestPredicate reportPath = path("/api/reports/{id}");
RequestPredicate allReports = path("/api/reports/**");
RequestPredicate healthPath = path("/health");
~~~

Các pattern trên là ví dụ về đường dẫn:

- `/api/reports/{id}` khớp một segment động, chẳng hạn `/api/reports/42`.
- `/api/reports/**` dùng để nhóm các đường dẫn con dưới prefix reports.
- `/health` khớp đường dẫn health cụ thể.

Khi route đã khớp, handler lấy biến path bằng:

~~~java
public Mono<ServerResponse> getReport(ServerRequest request) {
    String id = request.pathVariable("id");

    return ServerResponse.ok()
        .bodyValue(Map.of("id", id));
}
~~~

Nếu có nhiều path variables, có thể đọc từng biến bằng tên hoặc lấy map qua `request.pathVariables()`. Path variable là một phần của URI path, khác query parameter như `?page=2`.

Có thể kết hợp path predicate với điều kiện khác:

~~~java
RequestPredicate reportRead =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET));
~~~

Predicate chỉ khớp khi **cả path lẫn method** đúng. Nếu path đúng nhưng method sai, predicate kết hợp vẫn trả false.

## 4. Predicate HTTP method

`RequestPredicates.method(HttpMethod)` kiểm tra một HTTP method. `methods(HttpMethod...)` cho phép chấp nhận một trong nhiều method. Các shortcut như `GET(path)`, `POST(path)`, `PUT(path)` đã kết hợp điều kiện method với path.

Ví dụ:

~~~java
RequestPredicate getOnly = method(HttpMethod.GET);
RequestPredicate writeMethods =
    methods(HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH);
~~~

Một số cách viết tương đương:

~~~java
// Shortcut: method GET + path /reports/{id}.
.GET("/reports/{id}", handler::getReport)

// Cách tường minh:
.route(
    path("/reports/{id}").and(method(HttpMethod.GET)),
    handler::getReport
)
~~~

Shortcut trong router builder giúp code ngắn hơn, còn cách kết hợp predicate tường minh phù hợp khi cần thêm nhiều điều kiện hoặc tái sử dụng predicate.

### Không nhầm route predicate với HTTP authorization

Predicate method chỉ kiểm tra request có dùng GET/POST/... hay không. Nó không xác minh người gọi có quyền thực hiện hành động. Một route POST khớp không có nghĩa người dùng được phép tạo dữ liệu; kiểm tra authentication/authorization phải được thực hiện bằng Spring Security hoặc cơ chế bảo mật phù hợp.

## 5. Predicate header: headers(...)

`RequestPredicates.headers(Predicate<ServerRequest.Headers>)` cho phép viết điều kiện tùy chỉnh trên request headers.

Ví dụ yêu cầu client gửi phiên bản API:

~~~java
RequestPredicate apiV1 =
    headers(headers ->
        "v1".equals(headers.firstHeader("X-API-Version"))
    );
~~~

`firstHeader(name)` trả giá trị header đầu tiên hoặc `null` nếu không có. Viết so sánh theo dạng `"expected".equals(actual)` giúp tránh `NullPointerException` khi client không gửi header.

Một số ví dụ khác:

~~~java
RequestPredicate trustedClient =
    headers(headers ->
        "partner".equals(headers.firstHeader("X-Client"))
    );

RequestPredicate hasTraceId =
    headers(headers ->
        headers.firstHeader("X-Trace-Id") != null
    );

RequestPredicate internalChannel =
    headers(headers ->
        List.of("internal", "batch")
            .contains(headers.firstHeader("X-Channel"))
    );
~~~

Predicate có thể kiểm tra nhiều header trong cùng một lambda:

~~~java
RequestPredicate partnerV1 =
    headers(headers ->
        "partner".equals(headers.firstHeader("X-Client"))
            && "v1".equals(headers.firstHeader("X-API-Version"))
    );
~~~

Tên header HTTP không phân biệt chữ hoa/chữ thường theo quy tắc HTTP. Giá trị header được so sánh theo logic mà ứng dụng định nghĩa; không tự giả định mọi giá trị đều phải chuyển thành chữ thường.

**Cảnh báo bảo mật:** header tùy chỉnh như `X-Client`, `X-Role` hoặc `X-API-Key` có thể được client tự gửi. Dùng predicate header để chọn route hoặc phân loại request, nhưng **không dùng một header do client tự khai báo làm bằng chứng authorization**. Nếu cần xác thực danh tính, hãy dùng Spring Security, token được xác minh hoặc cơ chế tin cậy tương đương.

## 6. Predicate media type: phân biệt Content-Type và Accept

Hai header media type có mục đích khác nhau:

| Header | Ý nghĩa | Predicate tương ứng |
| --- | --- | --- |
| `Content-Type` | Kiểu nội dung mà client đang gửi trong request body | `contentType(MediaType...)` |
| `Accept` | Kiểu response mà client muốn nhận | `accept(MediaType...)` |

### contentType(...)

`contentType(MediaType.APPLICATION_JSON)` kiểm tra media type của request body có phù hợp với một trong các kiểu được khai báo không.

~~~java
RequestPredicate jsonBody =
    contentType(MediaType.APPLICATION_JSON);

RequestPredicate jsonOrNdjson =
    contentType(
        MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_NDJSON
    );
~~~

Dùng predicate này cho route nhận body JSON/NDJSON, ví dụ POST hoặc PUT. Không nên áp dụng `contentType` một cách máy móc cho GET request không có body.

### accept(...)

`accept(MediaType.APPLICATION_JSON)` kiểm tra header `Accept` của client có tương thích với JSON response không.

~~~java
RequestPredicate wantsJson =
    accept(MediaType.APPLICATION_JSON);

RequestPredicate wantsJsonOrText =
    accept(
        MediaType.APPLICATION_JSON,
        MediaType.TEXT_PLAIN
    );
~~~

Ví dụ route chỉ phục vụ JSON:

~~~java
.GET(
    "/reports/{id}",
    accept(MediaType.APPLICATION_JSON),
    handler::getReport
)
~~~

### Ví dụ thực tế: client gửi JSON và muốn nhận JSON

Một request POST có thể mang đồng thời:

~~~http
POST /api/reports
Content-Type: application/json
Accept: application/json
X-Client: partner
~~~

Route có thể yêu cầu cả `contentType(APPLICATION_JSON)`, `accept(APPLICATION_JSON)` và header client phù hợp. Nếu thiếu một điều kiện, route không khớp.

**Không nhầm predicate với codec:** predicate chỉ kiểm tra metadata để chọn handler. Việc thực sự giải mã JSON thành Java object vẫn do `ServerRequest.bodyToMono(...)` và message reader/codec đảm nhiệm trong handler. Một Content-Type được route chấp nhận không bảo đảm body JSON hợp lệ; body sai cú pháp vẫn có thể phát lỗi giải mã.

## 7. Kết hợp điều kiện bằng and, or và negate

`RequestPredicate` hỗ trợ các phép logic:

| Phương thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `and(other)` | Cả predicate hiện tại và predicate kia đều phải đúng | Path AND GET AND header |
| `or(other)` | Ít nhất một trong hai predicate đúng | Header nội bộ OR header đối tác |
| `negate()` | Đảo kết quả predicate | Không thuộc đường dẫn internal |

### Dùng and khi mọi điều kiện đều bắt buộc

~~~java
RequestPredicate readJsonReport =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET))
        .and(headers(h ->
            "v1".equals(h.firstHeader("X-API-Version"))))
        .and(accept(MediaType.APPLICATION_JSON));
~~~

Điều kiện tương đương:

~~~text
path đúng
AND method = GET
AND X-API-Version = v1
AND Accept tương thích application/json
------------------------------------------
                 MATCH
~~~

Chỉ cần một điều kiện sai, route không được chọn.

### Dùng or khi có nhiều lựa chọn hợp lệ

~~~java
RequestPredicate allowedChannel =
    headers(h -> "internal".equals(h.firstHeader("X-Channel")))
        .or(headers(h ->
            "partner".equals(h.firstHeader("X-Channel"))));
~~~

Predicate trên cho phép một trong hai channel. Khi kết hợp với các điều kiện khác, hãy đặt ngoặc hoặc tạo biến trung gian để code thể hiện rõ nhóm OR:

~~~java
RequestPredicate statusRoute =
    path("/api/status")
        .and(method(HttpMethod.GET))
        .and(allowedChannel)
        .and(accept(MediaType.TEXT_PLAIN));
~~~

### Dùng negate để loại trừ

~~~java
RequestPredicate notInternal =
    path("/internal/**").negate();

RequestPredicate publicGet =
    method(HttpMethod.GET).and(notInternal);
~~~

Ví dụ này chỉ là điều kiện routing. Nó không thay thế quy tắc bảo mật; không nên xem “không nằm dưới /internal” là đủ để cấp quyền truy cập.

## 8. Ghép nhiều predicate và đăng ký route

Có hai cách phổ biến.

### Cách 1: RouterFunctions.route(predicate, handler)

Cách này phù hợp khi đã tạo predicate hoàn chỉnh:

~~~java
RequestPredicate predicate =
    path("/api/reports/{id}")
        .and(method(HttpMethod.GET))
        .and(accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(predicate, handler::getReport);
~~~

### Cách 2: RouterFunctions.route() builder

Builder có shortcut theo HTTP method và path, đồng thời nhận predicate bổ sung:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET(
            "/api/reports/{id}",
            accept(MediaType.APPLICATION_JSON),
            handler::getReport
        )
        .POST(
            "/api/reports",
            contentType(MediaType.APPLICATION_JSON),
            handler::createReport
        )
        .build();
~~~

Ở route GET, builder kết hợp path và method GET với predicate Accept JSON. Ở route POST, builder kết hợp path và method POST với predicate Content-Type JSON.

### Nest các route có điều kiện chung

Nếu nhiều route cùng prefix hoặc cùng điều kiện header, có thể dùng nested route để tránh lặp:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/reports", reports -> reports
            .nest(
                headers(h ->
                    "v1".equals(h.firstHeader("X-API-Version"))),
                versioned -> versioned
                    .GET("/{id}", handler::getReport)
                    .GET("", handler::listReports)
            )
            .POST(
                contentType(MediaType.APPLICATION_JSON),
                handler::createReport
            )
        )
        .build();
~~~

Ở ví dụ trên, path prefix `/api/reports` được chia sẻ. Hai route GET nằm trong nhóm yêu cầu header version v1; POST có predicate Content-Type riêng. Nested route giúp nhóm điều kiện dùng chung, nhưng cần hiểu rõ phạm vi: predicate ở ngoài áp dụng cho tất cả route con; predicate ở một nhánh nested chỉ áp dụng cho nhánh đó.

## 9. Thứ tự khai báo route và xử lý khi không khớp

Các `RouterFunction` được đánh giá **theo thứ tự khai báo/ghép**. Khi một route không khớp, router có thể thử route tiếp theo. Vì vậy, nên đặt route cụ thể trước route tổng quát.

Ví dụ:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/reports/summary", handler::summary)
        .GET("/api/reports/{id}", handler::getReport)
        .GET("/api/reports/**", handler::fallback)
        .build();
~~~

Nếu route tổng quát được đặt trước, nó có thể nhận request trước khi route cụ thể được kiểm tra. Điều này khác với mô hình annotation-based controller, nơi Spring chọn mapping phù hợp theo quy tắc specificity riêng.

Khi một predicate không khớp, route đó không gọi handler. Nếu tất cả router đều không khớp, request tiếp tục qua cơ chế dispatch của ứng dụng; kết quả cuối cùng thường là 404 nếu không có handler/resource khác phù hợp. **Không nên mặc định một predicate mismatch tự động tạo HTTP 405, 406 hoặc 415.** Nếu cần các status cụ thể cho method/media type sai, hãy thiết kế route fallback hoặc exception/handler phù hợp và kiểm thử rõ.

## 10. Predicate routing khác handler filter

Predicate trả lời câu hỏi **request có thuộc route này không?** Filter xử lý request/response trong hoặc quanh handler đã được chọn.

WebFlux.fn cung cấp một số cơ chế:

- `before(...)`: biến đổi request trước khi handler chạy.
- `after(...)`: biến đổi response sau handler.
- `filter(...)`: bọc handler để thực hiện logic trước/sau, ví dụ kiểm tra quyền, logging hoặc đo thời gian.

Ví dụ filter:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/reports/{id}", handler::getReport)
        .filter((request, next) -> {
            if ("allowed".equals(
                    request.headers().firstHeader("X-Demo-Access"))) {
                return next.handle(request);
            }
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        })
        .build();
~~~

Đây là ví dụ minh họa cơ chế filter, không phải giải pháp bảo mật production. Filter có thể kiểm tra thông tin request rồi quyết định có gọi `next.handle(request)` hay trả response khác. Với xác thực/ủy quyền thật, dùng Spring Security thay vì tin một header demo.

Phạm vi filter cũng quan trọng: filter gắn vào builder áp dụng cho các route được builder đó tạo; filter trong nested builder không tự động áp dụng cho các route top-level khác.

## 11. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây tạo ba endpoint functional:

- `GET /api/reports/{id}`: path + method GET + header phiên bản + Accept JSON.
- `POST /api/reports`: path + method POST + header client + Content-Type JSON.
- `GET /api/status`: path + method GET + một trong hai header channel + Accept text/plain.

Tạo cấu trúc:

~~~text
predicate-routing-demo/
├── pom.xml
└── src/main/java/com/example/routing/
    ├── RoutingApplication.java
    ├── ReportHandler.java
    └── ReportRoutes.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>predicate-routing-demo</artifactId>
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

File `src/main/java/com/example/routing/RoutingApplication.java`:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/routing/ReportHandler.java`:

~~~java
package com.example.routing;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class ReportHandler {

    public record ReportView(String id, String status) {}
    public record CreateReportRequest(String title) {}
    public record CreateReportResponse(boolean accepted, String title) {}

    public Mono<ServerResponse> getReport(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ReportView(id, "ready"));
    }

    public Mono<ServerResponse> createReport(ServerRequest request) {
        return request.bodyToMono(CreateReportRequest.class)
            .flatMap(body ->
                ServerResponse.accepted()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(
                        new CreateReportResponse(true, body.title())
                    )
            );
    }

    public Mono<ServerResponse> status(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("ready");
    }
}
~~~

File `src/main/java/com/example/routing/ReportRoutes.java`:

~~~java
package com.example.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicate;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;
import static org.springframework.web.reactive.function.server.RequestPredicates.headers;
import static org.springframework.web.reactive.function.server.RequestPredicates.method;
import static org.springframework.web.reactive.function.server.RequestPredicates.path;

@Configuration(proxyBeanMethods = false)
public class ReportRoutes {

    @Bean
    RouterFunction<ServerResponse> reportRoutes(ReportHandler handler) {

        RequestPredicate readReport =
            path("/api/reports/{id}")
                .and(method(HttpMethod.GET))
                .and(headers(h ->
                    "v1".equals(h.firstHeader("X-API-Version"))))
                .and(accept(MediaType.APPLICATION_JSON));

        RequestPredicate createReport =
            path("/api/reports")
                .and(method(HttpMethod.POST))
                .and(headers(h ->
                    "trusted".equals(h.firstHeader("X-Client"))))
                .and(contentType(MediaType.APPLICATION_JSON));

        RequestPredicate allowedChannel =
            headers(h ->
                "internal".equals(h.firstHeader("X-Channel")))
            .or(headers(h ->
                "partner".equals(h.firstHeader("X-Channel"))));

        RequestPredicate status =
            path("/api/status")
                .and(method(HttpMethod.GET))
                .and(allowedChannel)
                .and(accept(MediaType.TEXT_PLAIN));

        return RouterFunctions.route(readReport, handler::getReport)
            .and(RouterFunctions.route(createReport, handler::createReport))
            .and(RouterFunctions.route(status, handler::status));
    }
}
~~~

Chạy trong thư mục `predicate-routing-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Thử GET: path + method + header + Accept

~~~bash
curl -i "http://localhost:8080/api/reports/42" ^
  -H "Accept: application/json" ^
  -H "X-API-Version: v1"
~~~

Response JSON dự kiến:

~~~json
{"id":"42","status":"ready"}
~~~

Nếu thiếu `X-API-Version: v1`, hoặc Accept không phù hợp, predicate không khớp và handler `getReport` không được gọi.

### Thử POST: path + method + header + Content-Type

~~~bash
curl -i -X POST "http://localhost:8080/api/reports" ^
  -H "Content-Type: application/json" ^
  -H "X-Client: trusted" ^
  -d "{"title":"Q2 report"}"
~~~

Response dự kiến là HTTP 202 với JSON:

~~~json
{"accepted":true,"title":"Q2 report"}
~~~

Nếu Content-Type không phù hợp hoặc header client không đúng, route không khớp. Khi route đã khớp nhưng JSON body sai cú pháp, handler/codec mới xử lý và có thể phát lỗi decode; hai trường hợp này khác nhau.

### Thử OR: một trong hai channel được phép

~~~bash
curl -i "http://localhost:8080/api/status" ^
  -H "Accept: text/plain" ^
  -H "X-Channel: partner"
~~~

Response dự kiến:

~~~text
ready
~~~

Có thể thay `partner` bằng `internal`. Predicate `allowedChannel` dùng `or`, nên một trong hai giá trị header là đủ; các điều kiện path, method và Accept vẫn phải đúng.

Các lệnh cURL trên dùng ký tự nối dòng `^` của Windows CMD. Trong PowerShell hoặc Bash, có thể viết lệnh trên một dòng hoặc dùng ký tự nối dòng tương ứng.

## 12. Kiểm thử route bằng WebTestClient

Có thể kiểm thử functional route mà không cần khởi động server thật bằng `WebTestClient.bindToRouterFunction(...)`. Cách này hữu ích để kiểm tra cả trường hợp khớp và không khớp predicate.

Ví dụ đoạn test minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ReportRoutesTest {

    private final ReportHandler handler = new ReportHandler();

    private final RouterFunction<ServerResponse> routes =
        new ReportRoutes().reportRoutes(handler);

    private final WebTestClient client =
        WebTestClient.bindToRouterFunction(routes).build();

    @Test
    void matchesGetWhenAllPredicatesPass() {
        client.get()
            .uri("/api/reports/42")
            .header("X-API-Version", "v1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{"id":"42","status":"ready"}");
    }

    @Test
    void doesNotMatchWhenVersionHeaderIsMissing() {
        client.get()
            .uri("/api/reports/42")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

Đây là đoạn test cần dependency `spring-boot-starter-test` hoặc các dependency test tương ứng, và các import `RouterFunction`, `ServerResponse`. Nếu chạy trong ứng dụng có route/controller khác, kết quả của một request không khớp có thể khác do router khác tiếp tục xử lý; test bind trực tiếp vào router này cô lập đúng hành vi của route được kiểm tra.

Nên có test cho:

- Đúng path, method, header và media type → handler được gọi.
- Đúng path nhưng sai method → route không khớp.
- Thiếu header bắt buộc → route không khớp.
- Content-Type không phù hợp → handler không được chọn.
- Accept không tương thích → route không khớp.
- OR: từng nhánh hợp lệ riêng lẻ đều khớp.
- Nhiều route có path overlap → route cụ thể được khai báo trước.
- Body sai định dạng sau khi route khớp → lỗi decode được xử lý riêng với lỗi routing.

## 13. Những lỗi thường gặp và cách tránh

1. **Nhầm Content-Type với Accept:** Content-Type là kiểu body request; Accept là kiểu response client muốn. Dùng `contentType(...)` cho body gửi lên và `accept(...)` cho response.
2. **Dùng header predicate nhưng quên header có thể vắng mặt:** `firstHeader` có thể trả `null`. So sánh theo cách null-safe như `"v1".equals(value)`.
3. **Dùng `and` khi thực tế muốn một trong nhiều lựa chọn:** tất cả điều kiện phải đúng nên route có thể không bao giờ khớp. Dùng `or` và nhóm predicate rõ ràng.
4. **Dùng `or` không có nhóm điều kiện:** biểu thức logic khó đọc hoặc vô tình nới lỏng điều kiện bắt buộc. Tạo biến predicate cho nhóm OR rồi kết hợp AND ở ngoài.
5. **Tưởng path predicate kiểm tra query parameter:** path chỉ kiểm tra URI path. Nếu cần query param, dùng predicate query tương ứng hoặc kiểm tra `ServerRequest.queryParam(...)` trong handler.
6. **Dùng Content-Type predicate cho GET không có body:** header có thể không tồn tại. Chỉ kiểm tra Content-Type ở route thực sự nhận body.
7. **Đọc body trong predicate:** predicate dùng để chọn route dựa trên metadata; body là stream có lifecycle riêng. Đọc body trong handler sau khi route được chọn.
8. **Cho rằng predicate mismatch tự trả 405/406/415:** predicate chỉ làm route không khớp. Muốn status cụ thể cần fallback/exception handling và test.
9. **Đặt route tổng quát trước route cụ thể:** route tổng quát có thể nhận request trước. Khai báo route cụ thể trước.
10. **Dùng header tùy chỉnh làm xác thực:** client có thể tự gửi header. Dùng Spring Security hoặc xác minh token/credential thật.
11. **Nhầm predicate với filter:** predicate quyết định route; filter bọc handler đã chọn. Dùng đúng abstraction cho mục đích.
12. **Dùng path prefix lặp ở nhiều route:** nested route bằng `path(...)` giúp gom prefix và điều kiện chung.
13. **Không kiểm thử route mismatch:** route đúng trong happy path chưa đủ. Test thiếu từng header, sai method và media type.
14. **Nhầm media type tương thích với chuỗi bằng nhau tuyệt đối:** `accept`/ `contentType` thực hiện matching theo quy tắc MediaType của Spring, không đơn giản là so sánh chuỗi header.
15. **Dùng predicate header để kiểm tra body JSON hợp lệ:** predicate chỉ kiểm tra header. JSON sai cú pháp được phát hiện ở bước decode trong handler.
16. **Không để ý thứ tự ghép RouterFunction:** `and(...)` nối route theo thứ tự; route đầu tiên khớp sẽ được chọn.

## 14. Checklist thiết kế route

Trước khi đăng ký một route, hãy xác định:

- Path pattern chính xác là gì? Có path variable hay prefix chung không?
- HTTP method nào được phép?
- Có cần header bắt buộc không? Nếu thiếu thì route có nên không khớp?
- Request body có media type nào? Có cần `contentType` không?
- Client phải chấp nhận response media type nào? Có cần `accept` không?
- Điều kiện là AND hay OR? Nhóm predicate đã rõ ràng chưa?
- Có route tổng quát nào có thể bắt request trước route cụ thể không?
- Nếu không có route khớp, ứng dụng cần 404, 405, 406 hay 415 theo hợp đồng nào?
- Có đang nhầm route selection với authentication/authorization không?
- Body có được đọc đúng một lần trong handler không?
- Có test cho cả route match và mismatch không?

## 15. Câu hỏi tự kiểm tra

**1.** `RequestPredicate` làm nhiệm vụ gì? Kiểm tra request có thỏa điều kiện để chọn một route hay không.

**2.** `path("/reports/{id}")` kiểm tra phần nào của request? URI path, không phải query string.

**3.** `method(HttpMethod.GET)` có kiểm tra header không? Không; nó chỉ kiểm tra HTTP method.

**4.** `headers(h -> ...)` cho phép làm gì? Viết predicate tùy chỉnh trên các request headers.

**5.** `contentType(APPLICATION_JSON)` kiểm tra header nào? Content-Type của request body.

**6.** `accept(APPLICATION_JSON)` kiểm tra header nào? Accept, tức media type client chấp nhận ở response.

**7.** `and` khác `or` thế nào? AND yêu cầu cả hai predicate đúng; OR yêu cầu ít nhất một predicate đúng.

**8.** `negate()` dùng để làm gì? Đảo kết quả của predicate.

**9.** Vì sao nên đặt route cụ thể trước route tổng quát? RouterFunction được đánh giá theo thứ tự; route tổng quát có thể khớp trước.

**10.** Predicate header có thay thế Spring Security không? Không; nó chỉ chọn route, không xác thực danh tính hay quyền.

**11.** Khi predicate không khớp, handler có được gọi không? Không; router thử route khác hoặc để cơ chế dispatch xử lý request không có handler phù hợp.

**12.** Có nên đọc request body trong predicate không? Không; body nên được đọc trong handler qua `bodyToMono` hoặc `bodyToFlux`.

**Ghi nhớ:** Trong WebFlux.fn, `RequestPredicate` cho phép ghép điều kiện **path + HTTP method + headers + media type** để chọn đúng `HandlerFunction`. Dùng `and` khi mọi điều kiện đều bắt buộc, `or` khi có lựa chọn thay thế, `negate` khi cần loại trừ. `contentType` kiểm tra body client gửi; `accept` kiểm tra response client chấp nhận. Đặt route cụ thể trước route tổng quát, xử lý body trong handler và dùng Spring Security cho authorization.

**Tài liệu chính thức:** [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html); [RequestPredicates Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html); [RequestPredicate Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicate.html).