# ServerHttpRequest, ServerHttpResponse và ServerWebExchange

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Luồng xử lý WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt vai trò của `ServerHttpRequest`, `ServerHttpResponse` và `ServerWebExchange` trong một lượt xử lý HTTP của Spring WebFlux.
2. Đọc method, URI, path, query parameters, headers, cookies, remote address và request body bằng các API reactive phù hợp.
3. Thiết lập status, headers, cookies và ghi response body bằng `ServerHttpResponse`; hiểu thời điểm response được commit.
4. Dùng `ServerWebExchange` để truy cập request/response, request attributes, session, principal, form/multipart data và thông tin hỗ trợ xử lý request.
5. Dùng ba abstraction này trong controller và `WebFilter`, biết khi nào nên để message converters/codecs xử lý body thay vì thao tác `DataBuffer` thủ công.
6. Tránh đọc request body nhiều lần, thay đổi header sau commit, chặn event-loop hoặc làm mất quan hệ giữa request và response reactive.

## 1. Ba abstraction trong một HTTP exchange

Trong Spring WebFlux, một request HTTP đi vào server và được chuyển qua các thành phần xử lý reactive. Ở tầng thấp của Spring Web, ba interface thường xuất hiện cùng nhau:

- `ServerHttpRequest` đại diện cho **request phía server nhận được**: method, URI, path, headers, cookies, query parameters, địa chỉ kết nối và body.
- `ServerHttpResponse` đại diện cho **response phía server sẽ gửi**: status, headers, cookies và thao tác ghi body/hoàn tất response.
- `ServerWebExchange` đại diện cho **toàn bộ tương tác request-response**: chứa request và response, đồng thời cung cấp request attributes, session, principal, locale, form/multipart data, log prefix và một số tiện ích HTTP.

```text
                 HTTP client
                     |
              request vào server
                     |
                     v
          +------------------------+
          |    ServerWebExchange   |
          |                        |
          |  +------------------+  |
          |  | ServerHttpRequest|  |
          |  | method, URI      |  |
          |  | headers, cookies |  |
          |  | body             |  |
          |  +------------------+  |
          |                        |
          |  +------------------+  |
          |  |ServerHttpResponse|  |
          |  | status, headers  |  |
          |  | cookies, body    |  |
          |  +------------------+  |
          |                        |
          | attributes, session,   |
          | principal, locale, ... |
          +------------------------+
                     |
              response ra client
```

Có thể hình dung `ServerWebExchange` là “phong bì” của một lượt HTTP; request và response là hai phần bên trong. Một `WebFilter` nhận exchange để can thiệp trước/sau handler. Một annotated controller có thể nhận trực tiếp `ServerHttpRequest`, `ServerHttpResponse` hoặc cả `ServerWebExchange` làm method argument.

Ba interface này thuộc reactive server API. Chúng không phải các lớp Servlet như `HttpServletRequest`/`HttpServletResponse`. Không sử dụng API Servlet trong handler WebFlux thuần reactive.

## 2. ServerHttpRequest: đọc request phía server

Kiểu đầy đủ:

```java
org.springframework.http.server.reactive.ServerHttpRequest
```

`ServerHttpRequest` cung cấp thông tin HTTP và body dưới dạng publisher. Các API hay dùng:

| API | Ý nghĩa |
| --- | --- |
| `getMethod()` / `getMethodValue()` | Method, ví dụ GET, POST, PUT, DELETE. |
| `getURI()` | URI request, có thể gồm query string. |
| `getPath()` | Đường dẫn dạng `RequestPath`, có thông tin context path và path trong ứng dụng. |
| `getHeaders()` | Headers dạng `HttpHeaders`; đọc từ request. |
| `getQueryParams()` | Query parameters đã parse/decode thành `MultiValueMap<String, String>`. |
| `getCookies()` | Cookies nhận từ client. |
| `getBody()` | Body dạng `Flux<DataBuffer>`, tức một luồng byte buffer. |
| `getRemoteAddress()` | Địa chỉ peer kết nối, nếu server cung cấp. |
| `getId()` | ID phục vụ tương quan connection/request nếu có. |
| `mutate()` | Tạo builder để tạo request decorator với thuộc tính đã chỉnh. |

### 2.1. Method, URI, path và query parameters

Ví dụ một request:

```http
GET /api/orders/42?includeItems=true&lang=vi HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Client-Version: 2.1
```

Có thể đọc các trường bằng:

```java
HttpMethod method = request.getMethod();
URI uri = request.getURI();
String path = request.getPath().value();
MultiValueMap<String, String> query = request.getQueryParams();

String includeItems = query.getFirst("includeItems");
String language = query.getFirst("lang");
String clientVersion = request.getHeaders().getFirst("X-Client-Version");
```

Đây là **đoạn minh họa** trong một controller hoặc WebFilter; cần import các kiểu Spring tương ứng. Query parameters là multi-value map vì cùng một tên có thể xuất hiện nhiều lần, ví dụ `?tag=java&tag=reactive`. Dùng `getFirst` khi chỉ cần giá trị đầu tiên; dùng `get` để lấy toàn bộ danh sách.

`getPath().value()` trả đường dẫn đã được biểu diễn theo `RequestPath`. Nếu cần xử lý path segment, hãy dùng API của `RequestPath` thay vì tự cắt chuỗi URI, đặc biệt khi có encoded character, context path hoặc path parameter.

### 2.2. Headers và cookies

`getHeaders()` cho phép đọc các thông tin như:

```java
String contentType = request.getHeaders().getFirst(HttpHeaders.CONTENT_TYPE);
String authorization = request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
List<String> accepted = request.getHeaders().get(HttpHeaders.ACCEPT);

HttpCookie sessionCookie = request.getCookies()
        .getFirst("SESSION");
```

Đây là đoạn minh họa. Headers/cookies của request là dữ liệu do client gửi; không nên xem chúng là dữ liệu đáng tin chỉ vì chúng có tên quen thuộc. Ví dụ, không cấp quyền chỉ dựa trên `X-User-Id` hoặc `X-Role` do client tự gửi. Hãy dùng Spring Security và `exchange.getPrincipal()` hoặc một cơ chế xác thực đã được xác minh.

### 2.3. Remote address và forwarded headers

`getRemoteAddress()` thường phản ánh peer kết nối trực tiếp tới server. Nếu ứng dụng nằm sau reverse proxy hoặc load balancer, địa chỉ này có thể là proxy, không phải thiết bị người dùng cuối.

Các header `Forwarded` và `X-Forwarded-*` chỉ nên được diễn giải khi proxy tại ranh giới tin cậy được cấu hình để ghi đè/xóa giá trị do client tự gửi và ứng dụng đã bật cơ chế xử lý forwarded headers phù hợp. Không tự lấy `X-Forwarded-For` đầu tiên làm danh tính hay cơ sở phân quyền nếu chưa xác định chuỗi proxy tin cậy.

### 2.4. Request body là Flux<DataBuffer>

`ServerHttpRequest` kế thừa API reactive input message; `getBody()` trả về `Flux<DataBuffer>`. Một body lớn có thể được nhận thành nhiều buffer, không có bảo đảm rằng một `DataBuffer` tương ứng một HTTP packet hoặc toàn bộ body.

```java
Flux<DataBuffer> rawBody = request.getBody();
```

Đoạn trên chỉ lấy publisher mô tả body; dữ liệu được tiêu thụ khi chuỗi có subscriber. **Body là luồng cần quản lý**, không phải một chuỗi có thể gọi `getBody()` nhiều lần để đọc lại từ đầu. Nếu filter tự tiêu thụ body, handler phía sau có thể không còn dữ liệu. Muốn đọc và chuyển tiếp body, cần cơ chế cache/replay và decorator đúng cách; việc này phải quản lý bộ nhớ, backpressure và vòng đời `DataBuffer`.

Trong controller, thông thường nên để Spring WebFlux decode body qua `@RequestBody`:

```java
@PostMapping("/orders")
public Mono<OrderResult> create(@RequestBody Mono<CreateOrderRequest> body) {
    return body.flatMap(orderService::create);
}
```

Đây là **đoạn minh họa**; `CreateOrderRequest`, `OrderResult` và `orderService` do ứng dụng định nghĩa. Cách này dùng message readers/codecs để chuyển body thành kiểu Java. Chỉ thao tác trực tiếp `DataBuffer` khi có yêu cầu ở tầng thấp như proxy, streaming hoặc xử lý byte đặc thù.

### 2.5. Form và multipart

`ServerWebExchange` cung cấp `getFormData()` và `getMultipartData()` ở dạng reactive. Các API này dùng message readers để parse body thành cấu trúc phù hợp. Form URL-encoded được trả về dưới dạng `Mono<MultiValueMap<String, String>>`; multipart data được trả về dưới dạng `Mono<MultiValueMap<String, Part>>`.

Việc parse form/multipart có thể đọc toàn bộ body và kết quả đã parse được cache để gọi các method tương ứng an toàn hơn. Tuy vậy, đừng đồng thời tự tiêu thụ raw body rồi yêu cầu framework parse lại. Với multipart lớn cần streaming, cân nhắc `Flux<PartEvent>` thay vì gom toàn bộ các phần vào map.

## 3. ServerHttpResponse: xây dựng response

Kiểu đầy đủ:

```java
org.springframework.http.server.reactive.ServerHttpResponse
```

`ServerHttpResponse` cho phép ứng dụng thiết lập trạng thái và metadata của response, rồi ghi body dưới dạng publisher. Các API thường gặp:

| API | Ý nghĩa |
| --- | --- |
| `setStatusCode(HttpStatusCode)` | Đặt HTTP status, ví dụ 201, 204, 404 hoặc 503. |
| `getStatusCode()` | Đọc status hiện tại; có thể chưa được thiết lập tường minh. |
| `getHeaders()` | Headers response. |
| `getCookies()` | Cookie sẽ gửi cho client. |
| `isCommitted()` | Kiểm tra response đã commit chưa. |
| `beforeCommit(Supplier<Mono<Void>>)` | Đăng ký hành động reactive chạy ngay trước khi commit. |
| `writeWith(Publisher<DataBuffer>)` | Ghi body từ publisher DataBuffer. |
| `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` | Ghi các nhóm buffer và flush sau từng nhóm publisher. |
| `setComplete()` | Hoàn tất response không cần body do ứng dụng ghi. |

### 3.1. Đặt status và headers trước khi response commit

Ví dụ:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().set("X-Request-Source", "webflux");
```

Đây là **đoạn minh họa**. Headers và status cần được đặt trước khi response được commit (thường là khi bắt đầu ghi body hoặc khi server hoàn tất response). Sau commit, không thể tùy ý đổi status hoặc headers đã gửi cho client; các thay đổi muộn có thể bị bỏ qua hoặc không còn hiệu lực.

`beforeCommit` dành cho thao tác cần chạy đúng trước thời điểm commit:

```java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Processed", "true")));
```

Đây là **đoạn minh họa**. Supplier phải trả publisher để hành động được thực hiện đúng trong chuỗi commit; không gọi `subscribe()` bên trong callback. `beforeCommit` không phải nơi chạy tác vụ blocking hoặc công việc dài.

### 3.2. Ghi body bằng writeWith

Một response nhỏ có thể được ghi trực tiếp:

```java
byte[] bytes = "Hello from WebFlux".getBytes(StandardCharsets.UTF_8);
DataBuffer buffer = response.bufferFactory().wrap(bytes);

response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
return response.writeWith(Mono.just(buffer));
```

Đây là **đoạn minh họa trong handler trả `Mono<Void>`**, cần import `DataBuffer`, `Mono` và `StandardCharsets`. `writeWith` nhận publisher các buffer và trả `Mono<Void>` biểu thị quá trình ghi hoàn tất hoặc lỗi. Phải **return publisher này** để WebFlux/server theo dõi vòng đời ghi response.

Không vừa gọi `writeWith` thủ công vừa trả một body khác để framework tiếp tục ghi lần nữa. Nếu muốn dùng cách ghi thủ công, method thường trả `Mono<Void>` và chuỗi đó là kết quả xử lý response.

Khi làm việc với `DataBuffer`, cần hiểu ownership và release trong các đường error/cancel/discard. Các codec của Spring thường quản lý buffer do chúng tạo; khi tự tạo hoặc giữ pooled buffer, hãy dùng `DataBufferUtils` và hướng dẫn của API để giải phóng đúng lúc, tránh leak hoặc double release.

### 3.3. writeAndFlushWith cho streaming

`writeAndFlushWith` nhận một publisher lồng nhau: mỗi publisher con chứa một nhóm `DataBuffer`. Server flush sau mỗi nhóm. Điều này hữu ích cho nội dung cần gửi theo đợt, nhưng không phải cách mặc định để ghi mọi JSON response.

Ví dụ minh họa về cấu trúc:

```java
Publisher<Publisher<DataBuffer>> chunks = ...;
return response.writeAndFlushWith(chunks);
```

Đây là **đoạn minh họa**, cần xây dựng publisher buffer phù hợp với giao thức response. Với SSE, thường dùng `Flux<T>` và `MediaType.TEXT_EVENT_STREAM` để Spring codec encode từng event; không cần tự tạo buffer/flush nếu không có lý do tầng thấp cụ thể.

### 3.4. setComplete khi không có body

```java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
```

Đây là đoạn minh họa trong handler. `204 No Content` là response thành công không có body. `setComplete()` trả `Mono<Void>`, nên vẫn phải return/compose publisher đó để quá trình hoàn tất được quản lý.

### 3.5. Cookies

`getCookies()` trên response trả về map cookie có thể thêm hoặc cấu hình cookie response. Trong code thực tế, ưu tiên `ResponseCookie` để đặt các thuộc tính như `Path`, `Max-Age`, `Secure`, `HttpOnly` và `SameSite` phù hợp với chính sách bảo mật.

```java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

response.addCookie(cookie);
```

Đây là **đoạn minh họa**; cần import `ResponseCookie`. `Secure` chỉ gửi cookie qua HTTPS. `HttpOnly` ngăn JavaScript phía trình duyệt đọc cookie, nhưng không tự ngăn CSRF; cần chính sách SameSite, CSRF protection và cấu hình domain/path thích hợp.

## 4. ServerWebExchange: ngữ cảnh của toàn bộ request

Kiểu đầy đủ:

```java
org.springframework.web.server.ServerWebExchange
```

Một exchange bao bọc request-response hiện tại và những dữ liệu phục vụ xử lý server-side. Các method quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getRequest()` | Lấy `ServerHttpRequest` hiện tại. |
| `getResponse()` | Lấy `ServerHttpResponse` hiện tại. |
| `getAttributes()` | Map mutable chứa thuộc tính riêng của exchange/request. |
| `getAttribute(name)` / `getAttributeOrDefault` | Đọc một request attribute. |
| `getRequiredAttribute(name)` | Lấy attribute bắt buộc; thiếu thì báo lỗi. |
| `getSession()` | Lấy `Mono<WebSession>` của request. |
| `getPrincipal()` | Lấy `Mono<Principal>` nếu request đã xác thực. |
| `getLocaleContext()` | Lấy locale context được cấu hình. |
| `getFormData()` | Parse form URL-encoded theo reactive API. |
| `getMultipartData()` | Parse multipart body theo reactive API. |
| `checkNotModified(...)` | Hỗ trợ điều kiện ETag/Last-Modified và response 304. |
| `getLogPrefix()` | Prefix để tương quan log theo request. |
| `mutate()` | Tạo builder để bọc exchange với request/response/principal đã điều chỉnh. |

### 4.1. Request attributes chỉ dành cho exchange hiện tại

Attributes phù hợp để truyền dữ liệu giữa WebFilter và handler trong **cùng một request**, ví dụ correlation ID, thời điểm bắt đầu, kết quả kiểm tra nội bộ hoặc dữ liệu đã xác minh.

```java
exchange.getAttributes().put("traceId", traceId);

String value = exchange.getAttributeOrDefault(
        "traceId", "missing");
```

Đây là **đoạn minh họa**. Attributes không phải global application cache, không phải session và không tự được lưu sang request tiếp theo. Không dùng static map hoặc field mutable trong singleton thay thế request attributes vì nhiều request có thể chạy đồng thời.

### 4.2. Session và principal là reactive

`getSession()` trả `Mono<WebSession>`, còn `getPrincipal()` trả một publisher chứa principal nếu có. Không gọi `block()` để lấy chúng trong WebFlux handler.

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

Đây là đoạn minh họa trả `Mono<String>`. Kết quả có thể rỗng khi không có principal; `defaultIfEmpty` chỉ xử lý trường hợp rỗng, không phải lỗi xác thực. Việc xác thực/ủy quyền thực tế nên được thực hiện qua Spring Security và các chính sách tương ứng.

### 4.3. checkNotModified cho ETag và Last-Modified

Khi có representation cacheable, server có thể dùng `ETag` hoặc thời điểm sửa đổi để tránh gửi lại body không thay đổi. `exchange.checkNotModified(etag)` hoặc overload có thêm `Instant lastModified` có thể chuẩn bị status/header thích hợp cho conditional request và trả `true` khi không cần xử lý tiếp.

Đây là tiện ích HTTP có semantics cụ thể, không phải phép so sánh chuỗi tùy ý. ETag phải đại diện cho phiên bản nội dung thực tế; nếu dữ liệu đã thay đổi mà vẫn dùng ETag cũ, client có thể giữ cache sai.

### 4.4. Mutate exchange và request

Các request/response/exchange API chủ yếu là abstraction có thể được wrap/decorate. Khi cần sửa thuộc tính request cho các filter/handler phía sau, dùng builder thay vì cố sửa object gốc:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder ->
                builder.headers(headers ->
                        headers.set("X-Internal-Check", "passed")))
        .build();

return chain.filter(updated);
```

Đây là **đoạn minh họa trong WebFilter**. `mutate()` tạo exchange decorator; `request(builder -> ...)` tạo request decorator với header đã thay đổi. Các thành phần downstream nhận exchange mới qua `chain.filter(updated)`. Request ban đầu không được sửa tại chỗ.

Chỉ thêm header nội bộ do server kiểm soát; đừng dùng cách này để tin tưởng một header xác thực do client tự gửi. Nếu muốn thay đổi response behavior ở tầng thấp, có thể dùng `ServerHttpResponseDecorator` và đặt nó vào exchange mới, nhưng cần hiểu kỹ cách write/commit và ownership của DataBuffer.

## 5. Dùng ba abstraction trong WebFilter

`WebFilter` là điểm phù hợp để xử lý concern xuyên suốt nhiều endpoint: trace ID, audit metadata, kiểm tra header, thời gian xử lý hoặc chính sách request chung. Chữ ký:

```java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)
```

`WebFilterChain.filter(exchange)` chuyển request tới filter tiếp theo và handler cuối cùng. Filter nên **compose và return** publisher của chain; không tự `subscribe()` vào nó. Có thể gắn operator để quan sát trước/sau:

```java
return chain.filter(exchange)
        .doOnError(error -> logFailure(exchange, error))
        .doFinally(signal -> recordCompletion(exchange, signal));
```

Đây là **đoạn minh họa**. `doFinally` có thể nhận `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; cancellation upstream không nhất thiết có nghĩa client đã đóng kết nối, vì một operator khác cũng có thể hủy. Đặt hook gần đúng boundary và dùng request correlation ID để đọc log.

### 5.1. Filter hoàn chỉnh: gắn trace ID và đo thời gian

Ví dụ này tạo một trace ID, lưu vào exchange attributes, thêm response header và ghi kết quả khi request kết thúc:

```java
@Component
public class RequestTraceFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.traceId", traceId);

        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();
        response.getHeaders().set("X-Trace-Id", traceId);

        long started = System.nanoTime();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    System.out.printf(
                            "%s %s -> %s [%s] %dms%n",
                            request.getMethodValue(),
                            request.getURI().getPath(),
                            response.getStatusCode(),
                            signal,
                            elapsedMs);
                });
    }
}
```

Đây là **một class minh họa** cần các import `UUID`, `TimeUnit`, `Component`, `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse`, `WebFilter`, `WebFilterChain` và `Mono`. Header được đặt trước khi chain ghi response nên vẫn có thể được gửi. Attribute giúp controller đọc cùng trace ID mà không phải parse lại header.

`doFinally` chạy cho complete/error/cancel của publisher ở vị trí đó. Thời gian đo bao gồm thời gian chain xử lý tới tín hiệu kết thúc mà filter quan sát được; đây không nhất thiết là thời gian client nhận hết byte trên mạng ở mọi server/transport.

### 5.2. Khi filter không gọi chain

Một filter có thể chủ động kết thúc sớm, ví dụ từ chối request không đạt điều kiện. Khi đó filter phải thiết lập response thích hợp và return publisher hoàn tất:

```java
if (!allowed) {
    response.setStatusCode(HttpStatus.FORBIDDEN);
    return response.setComplete();
}
return chain.filter(exchange);
```

Đây là **đoạn minh họa** trong `WebFilter`; biến `allowed` là kết quả kiểm tra đã được xác minh. Nếu response cần body lỗi, có thể dùng codec hoặc ghi publisher DataBuffer. Không gọi chain rồi đồng thời tự ghi response khác trong cùng nhánh nếu không có thiết kế rõ ràng.

## 6. Ví dụ Spring Boot 3.3.5 chạy được

Ví dụ đầy đủ sau dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và dependency `spring-boot-starter-webflux`. Phiên bản được cố định để dễ tái lập; trong dự án thực tế nên theo version/BOM đang được dự án quản lý.

Cấu trúc:

```text
webflux-exchange-demo/
├── pom.xml
└── src/main/java/demo/
    ├── WebFluxExchangeApplication.java
    ├── RequestTraceFilter.java
    └── ExchangeController.java
```

### 6.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-exchange-demo</artifactId>
    <version>1.0.0</version>

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
```

### 6.2. WebFluxExchangeApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxExchangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxExchangeApplication.class, args);
    }
}
```

### 6.3. RequestTraceFilter.java

```java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestTraceFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.traceId", traceId);

        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();
        response.getHeaders().set("X-Trace-Id", traceId);

        long started = System.nanoTime();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started);

                    System.out.printf(
                            "%s %s -> %s [%s] %dms%n",
                            request.getMethodValue(),
                            request.getURI().getPath(),
                            response.getStatusCode(),
                            signal,
                            elapsedMs);
                });
    }
}
```

### 6.4. ExchangeController.java

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangeController {
    @GetMapping("/inspect")
    public Map<String, Object> inspect(
            ServerHttpRequest request,
            ServerWebExchange exchange) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethodValue());
        result.put("path", request.getPath().value());
        result.put("query", request.getQueryParams());
        result.put("traceId",
                exchange.getAttributeOrDefault("demo.traceId", "missing"));
        return result;
    }

    @PostMapping(
            value = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
            ServerHttpRequest request,
            @RequestBody Mono<String> body) {

        return body.map(value ->
                request.getHeaders().getContentType() + " | " + value);
    }

    @GetMapping("/direct")
    public Mono<Void> direct(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "written by ServerHttpResponse\n"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);

        return response.writeWith(Mono.just(buffer));
    }
}
```

### 6.5. Chạy và gửi request

Tại thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Trên Windows PowerShell, dùng `curl.exe` để tránh alias `curl`; trên Linux/macOS có thể dùng `curl`:

```powershell
curl.exe -i "http://localhost:8080/inspect?source=demo"
curl.exe -i -X POST -H "Content-Type: text/plain" --data "hello" http://localhost:8080/echo
curl.exe -i http://localhost:8080/direct
```

**Kết quả quan sát chính:**

1. `GET /inspect?source=demo` trả HTTP 200 và JSON chứa method `GET`, path `/inspect`, query `source=demo` cùng `traceId` do filter tạo. Response có header `X-Trace-Id` cùng giá trị với attribute controller đọc được.
2. `POST /echo` với body `hello` trả body `text/plain | hello`. Controller đọc header từ `ServerHttpRequest` và để `@RequestBody Mono<String>` cùng message reader decode body.
3. `GET /direct` trả HTTP 202 Accepted, Content-Type `text/plain` và body `written by ServerHttpResponse`. Controller đã tự ghi body nên method trả `Mono<Void>`.

Ví dụ log filter có dạng (thời gian và trace ID thay đổi theo lần chạy):

```text
GET /inspect -> 200 OK [onComplete] 18ms
POST /echo -> 200 OK [onComplete] 4ms
GET /direct -> 202 ACCEPTED [onComplete] 2ms
```

Đây là output minh họa theo hình dạng log; số mili-giây phụ thuộc máy và môi trường. `doFinally` có thể in `onError` hoặc `cancel` nếu request kết thúc theo cách tương ứng.

## 7. Khi nào dùng request, response hay exchange?

| Nhu cầu | API nên dùng | Vì sao |
| --- | --- | --- |
| Chỉ cần method, path, header hoặc query | `ServerHttpRequest` | Đọc đúng phần request cần thiết. |
| Cần decode body thành DTO | `@RequestBody Mono<T>`/`Flux<T>` | Để codec quản lý decode và backpressure. |
| Cần raw byte stream hoặc proxy body | `ServerHttpRequest.getBody()` | Tầng thấp, cần tự quản lý DataBuffer và ownership. |
| Cần đặt status/header/cookie hoặc ghi response thủ công | `ServerHttpResponse` | API trực tiếp của response reactive. |
| Cần trace ID, session, principal, attributes hoặc cả request và response | `ServerWebExchange` | Một context thống nhất của request hiện tại. |
| Cần logic xuyên suốt nhiều endpoint | `WebFilter` với `ServerWebExchange` | Can thiệp trước/sau handler mà vẫn giữ reactive chain. |
| Chỉ trả JSON/text thông thường | Return DTO, `Mono<T>` hoặc `Flux<T>` từ controller | Spring codec tự encode; code ít và an toàn hơn. |

Không phải cứ có thể dùng `ServerWebExchange` là nên dùng ở mọi controller. Nếu một method chỉ cần một query parameter, `@RequestParam` rõ ràng hơn. Nếu chỉ cần một header, `@RequestHeader` dễ đọc hơn. Dùng exchange khi thực sự cần ngữ cảnh HTTP rộng hơn.

## 8. Những ranh giới cần phân biệt

### 8.1. ServerHttpRequest khác ServerRequest

Trong functional endpoints, Spring cung cấp `org.springframework.web.reactive.function.server.ServerRequest`. Đây là abstraction cấp cao cho `HandlerFunction`, có API riêng như `headers()`, `bodyToMono`/`body` và `exchange()`. Nó không phải `org.springframework.http.server.reactive.ServerHttpRequest`.

Tương tự, `ServerResponse` của functional endpoint là builder abstraction để mô tả response, còn `ServerHttpResponse` là API HTTP server tầng thấp để ghi trực tiếp response. Không nhầm hai cặp tên gần giống nhau.

### 8.2. Response đã commit không thể đổi status tùy ý

Nếu body đã bắt đầu được ghi, headers/status thường đã commit. Khi lỗi xảy ra giữa một response streaming, server không thể quay lại thay HTTP 200 thành 500 nếu header đã gửi. Hãy quyết định response contract và error strategy trước khi stream; nếu client cần biết lỗi giữa stream, giao thức body/SSE phải có cách biểu diễn lỗi phù hợp.

### 8.3. Không tự subscribe vào request body hoặc response

Không viết:

```java
request.getBody().subscribe(buffer -> process(buffer));
return chain.filter(exchange);
```

Đây là **anti-pattern minh họa**: body bị tiêu thụ trong subscription riêng, có thể cạnh tranh với decoder/handler phía sau; lỗi và cancellation không còn được compose vào HTTP lifecycle. Hãy dùng `flatMap`/`map` trên publisher và return kết quả, hoặc dùng controller argument/codec.

Tương tự, không gọi `response.writeWith(...).subscribe()` rồi return `Mono.empty()`. Phải return `writeWith(...)` để server theo dõi việc ghi và lỗi.

### 8.4. DataBuffer không phải byte[] thông thường

Một `DataBuffer` có thể dùng pooled/native memory. Đọc buffer rồi giữ lại hoặc loại bỏ nó đòi hỏi ownership rõ ràng. Khi dùng API tầng thấp:

- Không giữ DataBuffer sau khi đã release.
- Không release hai lần.
- Khi copy bytes ra cấu trúc riêng, bảo đảm giải phóng buffer theo đúng API.
- Xử lý đường cancel/error/discard, đặc biệt với buffer chưa tới downstream.
- Ưu tiên codec của Spring nếu không cần can thiệp byte stream.

### 8.5. Attributes không phải security context

Request attribute chỉ là map dữ liệu trong exchange hiện tại. Không tự biến một giá trị attribute do client kiểm soát thành quyền truy cập. Dữ liệu xác thực cần được tạo bởi thành phần đáng tin cậy; dùng `Principal` và Spring Security để kiểm tra danh tính/authority.

### 8.6. Không tin forwarded headers từ mọi client

`Forwarded` và `X-Forwarded-*` có thể bị giả mạo nếu proxy không xóa và ghi lại giá trị đầu vào. Cấu hình forwarded-header handling phải khớp topology và trust boundary. Không dùng các header này làm cơ sở cấp quyền hoặc rate limit theo IP nếu chưa kiểm soát proxy.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Nhầm `ServerWebExchange` là request body | Dùng sai abstraction | Exchange chứa request và response cùng metadata server-side. |
| Nhầm `ServerHttpRequest` với functional `ServerRequest` | Gọi nhầm API/package | Kiểm tra package và programming model. |
| Đọc `getBody()` trong filter rồi để handler đọc lại | Handler có thể nhận body rỗng hoặc stream đã bị tiêu thụ | Compose body vào pipeline hoặc xây dựng request decorator có replay đúng cách. |
| Gom body lớn vào memory không giới hạn | Tăng bộ nhớ, giảm khả năng streaming | Dùng streaming publisher, giới hạn kích thước và codec phù hợp. |
| Tự sửa request headers trực tiếp | Headers request thường là view read-only | Dùng `request.mutate()` hoặc `exchange.mutate()` tạo decorator. |
| Đổi status/header sau khi response commit | Thay đổi không còn được gửi | Đặt metadata trước khi ghi body hoặc dùng `beforeCommit` đúng cách. |
| Gọi `writeWith` nhưng không return publisher | Server không theo dõi đúng vòng đời ghi | Return/compose `Mono<Void>` từ writeWith. |
| Vừa ghi response thủ công vừa return DTO | Có thể ghi response hai lần hoặc commit conflict | Chọn một cách sở hữu body cho mỗi handler. |
| Gọi `subscribe()` trong WebFilter | Tạo nhánh tách rời khỏi request | Return `chain.filter(exchange)` đã compose. |
| Dùng `block()` để lấy principal/session/body | Chặn event-loop hoặc làm sai reactive lifecycle | Compose publisher bằng map/flatMap. |
| Dùng request attribute như session | Dữ liệu mất sau exchange hiện tại | Dùng WebSession hoặc persistence phù hợp nếu cần qua nhiều request. |
| Tin `X-Forwarded-For` từ Internet | Có thể giả mạo IP client | Chỉ xử lý forwarded header sau trusted proxy. |
| Không release pooled DataBuffer | Memory leak | Quản lý ownership/release theo DataBuffer API. |
| Gọi getStatusCode rồi giả định luôn khác null | Status có thể chưa được thiết lập tường minh | Xử lý trạng thái chưa đặt hoặc dùng default theo ngữ cảnh. |
| Coi cancel luôn là client disconnect | Metric/log sai nguyên nhân | Operator upstream cũng có thể cancel; đặt hook đúng boundary và correlation ID. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `ServerHttpRequest` và `ServerHttpResponse` khác nhau ở đâu?  
**Đáp án:** Request đại diện thông tin và body client gửi tới server; response đại diện status, headers, cookies và body server gửi lại.

**Câu 2.** `ServerWebExchange` bổ sung điều gì ngoài request/response?  
**Đáp án:** Nó cung cấp context cho lượt HTTP như request attributes, session, principal, locale, form/multipart data, log prefix và các tiện ích HTTP như conditional request.

**Câu 3.** Vì sao không nên gọi `request.getBody().subscribe(...)` trong WebFilter rồi gọi `chain.filter(exchange)`?  
**Đáp án:** Đó là subscription tách rời có thể tiêu thụ body trước decoder/handler, đồng thời lỗi/cancel không được quản lý chung. Hãy compose body vào publisher được return.

**Câu 4.** Khi nào không thể đổi status HTTP nữa?  
**Đáp án:** Sau khi response đã commit, thường là khi headers/body bắt đầu được ghi. Status và headers cần được quyết định trước commit.

**Câu 5.** `response.writeWith(...)` trả kiểu gì và cần làm gì với nó?  
**Đáp án:** Trả `Mono<Void>` biểu thị ghi body hoàn tất hoặc lỗi; phải return/compose publisher này.

**Câu 6.** Dữ liệu nào phù hợp với `exchange.getAttributes()`?  
**Đáp án:** Metadata riêng của request hiện tại như trace ID hoặc kết quả xử lý nội bộ. Không dùng làm global cache hay session giữa nhiều request.

**Câu 7.** Tại sao `getRemoteAddress()` có thể không phải IP thật của người dùng?  
**Đáp án:** Kết nối trực tiếp có thể đến từ reverse proxy/load balancer. Forwarded headers chỉ đáng tin khi proxy ở trust boundary ghi lại và cấu hình xử lý đúng.

**Câu 8.** Có nên dùng `ServerHttpResponse` để tự ghi mọi JSON response không?  
**Đáp án:** Không cần. Thường return DTO/Mono/Flux và để Spring codecs encode. Ghi trực tiếp hữu ích cho trường hợp tầng thấp, streaming byte hoặc kiểm soát response đặc biệt.

**Câu 9.** `ServerRequest` trong functional endpoint có phải `ServerHttpRequest` không?  
**Đáp án:** Không. Chúng thuộc package và mức abstraction khác nhau. `ServerRequest` cung cấp API cấp cao cho `HandlerFunction`; `ServerHttpRequest` là HTTP server message tầng thấp.

## Ghi nhớ

- **`ServerHttpRequest`:** đọc method, URI/path, headers, cookies, query params và raw body dạng `Flux<DataBuffer>`.
- **`ServerHttpResponse`:** thiết lập status/headers/cookies, theo dõi commit và ghi body qua `writeWith`/`writeAndFlushWith` hoặc hoàn tất bằng `setComplete`.
- **`ServerWebExchange`:** gom request, response và context của một request; dùng attributes, session, principal, locale, form/multipart, log prefix và builder mutate.
- Trong controller, ưu tiên argument resolver và codecs như `@RequestBody Mono<T>`; dùng raw DataBuffer khi thực sự cần tầng thấp.
- Body request là stream có ownership/lifecycle; response chỉ có thể đổi status/headers trước commit. Luôn compose và return publisher, không tự subscribe/block.
- Với proxy, forwarded headers và security metadata, chỉ tin dữ liệu sau khi xác minh trust boundary.

### Tài liệu tham khảo

1. [Spring Framework – Reactive Core / WebHandler API](https://docs.spring.io/spring-framework/reference/7.1/web/webflux/reactive-spring.html): `ServerWebExchange`, `WebFilter`, session, attributes, form và multipart.
2. [Spring Framework – Annotated Controller Method Arguments](https://docs.spring.io/spring-framework/reference/7.1/web/webflux/controller/ann-methods/arguments.html): inject `ServerWebExchange`, `ServerHttpRequest` và `ServerHttpResponse`.
3. [ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response, attributes, principal, session, mutate và conditional request.
4. [ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request metadata, body và builder.
5. [ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): response status, headers, cookies và ghi body.
6. [ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): `beforeCommit`, `writeWith`, `writeAndFlushWith` và `setComplete`.
7. [Spring Framework – WebFlux Testing](https://docs.spring.io/spring-framework/reference/7.1/testing/webtestclient.html): kiểm thử reactive HTTP với `WebTestClient`.
