# `WebHandler`, `WebFilter` và `WebExceptionHandler` trong Spring WebFlux

## 1. Mục tiêu và bức tranh tổng thể

Spring WebFlux cung cấp một pipeline xử lý HTTP theo mô hình reactive. Ba hợp đồng nền tảng trong bài học này là:

- **`WebHandler`**: thành phần xử lý request ở tầng web cao hơn `HttpHandler`. Trong ứng dụng WebFlux thông thường, `DispatcherHandler` là `WebHandler` trung tâm.
- **`WebFilter`**: thành phần chặn giữa để thực hiện logic trước và sau phần còn lại của chuỗi filter cùng handler, ví dụ request ID, logging, CORS hoặc kiểm tra điều kiện truy cập.
- **`WebExceptionHandler`**: thành phần nhận lỗi thoát ra khỏi chuỗi `WebFilter` hoặc target `WebHandler`, rồi chuyển lỗi thành HTTP response nếu có thể xử lý.

Ba interface này đều làm việc với `Mono<Void>` vì chúng mô tả **quá trình xử lý và ghi response**, không phải một giá trị dữ liệu trả về cho Java caller. `Mono<Void>` hoàn tất khi công việc kết thúc; nó không phát một phần tử `null`.

Sau bài học, bạn cần hiểu cách Spring ghép các thành phần này, đọc đúng thứ tự xử lý request/response, viết filter có thể chạy trước và sau handler, xây exception handler có thể xử lý lỗi hoặc chuyển lỗi tiếp, phân biệt xử lý lỗi toàn cục với `@ControllerAdvice`, và áp dụng các interface này trong một ứng dụng Spring Boot WebFlux chạy được.

### Một request đi qua những lớp nào?

~~~text
HTTP client
    |
    v
HTTP server (Reactor Netty, Tomcat, Jetty, ...)
    |
    v
Server adapter
    |
    v
HttpHandler
    |
    v
WebExceptionHandler chain
    |
    v
WebFilter chain
    |
    v
WebHandler (thường là DispatcherHandler)
    |
    +--> HandlerMapping
    |
    +--> HandlerAdapter
    |
    +--> HandlerResultHandler
    |
    v
HTTP response
~~~

`WebHttpHandlerBuilder` lắp một target `WebHandler`, bao quanh nó bằng các `WebFilter`, rồi đặt các `WebExceptionHandler` bên ngoài để xử lý lỗi thoát ra từ chuỗi. Vì thế filter có thể bao quanh cả xử lý controller/functional endpoint, còn exception handler ở tầng ngoài có thể quan sát lỗi phát sinh trong filter lẫn target handler.

## 2. `HttpHandler`, `WebHandler` và `DispatcherHandler` khác nhau thế nào?

### 2.1. `HttpHandler`: abstraction HTTP thấp nhất của Spring WebFlux

`HttpHandler` là hợp đồng tối giản để xử lý một request và response HTTP. Nó giúp Spring không phụ thuộc trực tiếp vào API riêng của một server. Spring có adapter cho Reactor Netty, Tomcat, Jetty và các Servlet container có hỗ trợ non-blocking I/O.

Vai trò chính của lớp này là kết nối runtime HTTP với mô hình reactive của Spring. Ứng dụng thông thường không cần tự viết `HttpHandler`; Spring Boot cấu hình adapter và server phù hợp từ dependency.

### 2.2. `WebHandler`: xử lý request ở mức web

Hợp đồng:

~~~java
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

`ServerWebExchange` là đối tượng đại diện cho một HTTP request-response exchange. Nó cung cấp:

- `getRequest()`: thông tin request, method, URI, header, body.
- `getResponse()`: thiết lập status, header và ghi body.
- `getAttributes()`: map thuộc tính gắn với exchange hiện tại.
- `getSession()`: truy cập WebSession.
- `getPrincipal()`: thông tin principal khi có tích hợp xác thực.
- `getLocaleContext()`: locale context của request.
- Các API đọc form data và multipart data qua codec, có cơ chế cache cho các API tương ứng.

`WebHandler` không buộc ứng dụng dùng controller annotation. Một ứng dụng có thể triển khai WebHandler trực tiếp hoặc dùng programming model cấp cao hơn như annotated controller và WebFlux.fn.

### 2.3. `DispatcherHandler`: front controller của ứng dụng WebFlux thông thường

Trong cấu hình WebFlux chuẩn, `DispatcherHandler` là `WebHandler` trung tâm, thường được đăng ký dưới bean name `webHandler`. Nó dùng các special bean để tìm và gọi handler thực tế:

1. `HandlerMapping` tìm handler phù hợp với request; ví dụ `RequestMappingHandlerMapping` cho controller annotation hoặc `RouterFunctionMapping` cho functional route.
2. `HandlerAdapter` gọi handler đã tìm được, không phụ thuộc handler được khai báo bằng annotation hay functional endpoint.
3. `HandlerResultHandler` xử lý kết quả, ví dụ serialize object thành JSON hoặc ghi `ServerResponse`.

`DispatcherHandler` là một phần của target WebHandler trong chuỗi ngoài. Bạn thường cấu hình controller, router, filter và exception handler dưới dạng Spring bean, để framework ghép pipeline. Chỉ tự khai báo một WebHandler thay thế khi thật sự muốn tự quản lý programming model ở tầng thấp.

## 3. `WebFilter`: can thiệp trước và sau chuỗi xử lý

### 3.1. Hợp đồng và ý nghĩa

~~~java
public interface WebFilter {
    Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    );
}
~~~

`WebFilterChain` đại diện phần còn lại của chuỗi filter và target `WebHandler`:

~~~java
public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
~~~

Một filter thường làm ba việc:

1. Đọc request hoặc gắn thuộc tính cần cho xử lý phía sau.
2. Gọi `chain.filter(exchange)` để chuyển request sang filter tiếp theo hoặc target handler.
3. Dùng các toán tử Reactor để quan sát kết quả khi chuỗi hoàn tất, phát lỗi hoặc bị hủy.

Ví dụ tổng quát:

~~~java
@Override
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    System.out.println("before");
    return chain.filter(exchange)
        .doOnSuccess(ignored -> System.out.println("success"))
        .doOnError(error -> System.err.println("error=" + error.getMessage()))
        .doFinally(signal -> System.out.println("finished=" + signal));
}
~~~

Đây là ví dụ minh họa về vị trí callback. Vì `Mono<Void>` không phát dữ liệu, đối số của `doOnSuccess` có thể là `null` theo hợp đồng callback của Reactor; không dùng nó làm response body. `doFinally` chạy cho các đường hoàn tất, lỗi hoặc cancel, nên phù hợp với metric kết thúc request.

### 3.2. Filter chạy theo kiểu lồng nhau

Giả sử có hai filter A và B, thứ tự A trước B:

~~~text
A: before
    B: before
        WebHandler
    B: after
A: after
~~~

Filter A bao quanh phần còn lại của chuỗi; B bao quanh target handler. Vì vậy:

- Trên đường request đi vào, filter có order sớm hơn chạy trước.
- Khi response quay ra, callback sau chuỗi chạy theo thứ tự ngược lại.
- Nếu một filter không gọi `chain.filter` và tự hoàn tất response, các filter phía trong và target handler sẽ không được chạy.

Đây là cơ chế phù hợp cho cross-cutting concern. Không nên dùng filter để nhét toàn bộ nghiệp vụ của controller vào một lớp chặn.

### 3.3. Sắp xếp filter bằng `@Order` hoặc `Ordered`

Khi dùng WebFlux Config/Spring Boot, các bean `WebFilter` được phát hiện tự động. Bạn có thể chỉ định thứ tự bằng `@Order` hoặc triển khai `Ordered`.

~~~java
@Component
@Order(10)
public class AuditWebFilter implements WebFilter {
    // ...
}
~~~

Số order nhỏ hơn được ưu tiên trước trong danh sách đã sắp xếp. Thứ tự là một phần của hợp đồng vận hành: filter xác thực, CORS, request ID, logging và rate limit có thể cần vị trí khác nhau. Ví dụ, tài liệu Spring khuyến nghị CORS filter đứng trước chuỗi Spring Security để preflight request được xử lý đúng. Khi thêm Spring Security hoặc filter do Boot tự cấu hình, hãy xác định order thực tế của từng filter thay vì dựa vào thứ tự khai báo bean trong file Java.

### 3.4. Dừng sớm hoặc thay đổi exchange

Filter có thể chặn request trước khi gọi chain:

~~~java
if (exchange.getRequest().getHeaders().getFirst("X-Maintenance") != null) {
    exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
~~~

Nếu muốn thay đổi request, dùng builder của exchange:

~~~java
ServerWebExchange mutated = exchange.mutate()
    .request(builder -> builder.path("/internal"))
    .build();

return chain.filter(mutated);
~~~

Đây là các ví dụ rút gọn; cần bảo đảm thay đổi URL/header không phá routing, security hoặc cache key. Không gọi `chain.filter` hai lần cho cùng một request trừ khi bạn đang triển khai một mô hình retry/dispatch rất cụ thể và hiểu rõ side effect.

### 3.5. Đọc request body trong filter cần thận trọng

Request body thường là stream có thể tiêu thụ một lần. Nếu filter tự đọc body thô rồi vẫn gọi `chain.filter(exchange)`, controller phía sau có thể không còn dữ liệu để đọc. Với form data, ưu tiên API `exchange.getFormData()` vì Spring cung cấp cơ chế parse/cache cho truy cập lặp. Với multipart hoặc streaming body, hãy chọn đúng API và cân nhắc bộ nhớ/backpressure; không gom toàn bộ body vào RAM chỉ để ghi log.

## 4. `WebExceptionHandler`: xử lý lỗi ở tầng WebHandler API

### 4.1. Hợp đồng

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

Hợp đồng của return value rất quan trọng:

- Nếu handler trả về `Mono<Void>` hoàn tất thành công, Spring coi lỗi đã được xử lý.
- Nếu handler trả về `Mono.error(ex)`, lỗi vẫn chưa được xử lý và được chuyển tiếp tới exception handler tiếp theo.
- Nếu không thể ghi response vì response đã committed, handler không thể đổi status/header/body của response đã gửi; cần để lỗi tiếp tục hoặc xử lý theo chính sách đã thiết kế.

Một exception handler có thể chuyển lỗi thành HTTP status, JSON error body, redirect hoặc response rỗng. Nó không cần trả một object JSON qua generic type; nó ghi trực tiếp vào `ServerHttpResponse` rồi trả `Mono<Void>`.

### 4.2. Viết một exception handler có chọn lọc

~~~java
@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
        ServerWebExchange exchange,
        Throwable error
    ) {
        if (!(error instanceof CatalogUnavailableException)) {
            return Mono.error(error);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body =
            "{\"error\":\"CATALOG_UNAVAILABLE\"}".getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

`CatalogUnavailableException` là exception nghiệp vụ do ứng dụng định nghĩa. Handler chỉ xử lý đúng loại lỗi này. Với lỗi khác, nó trả `Mono.error(error)` để handler tiếp theo có cơ hội xử lý. Với lỗi đã commit response, không cố viết một JSON thứ hai lên response đang truyền.

### 4.3. Các handler có sẵn

Spring WebFlux cung cấp:

- `ResponseStatusExceptionHandler`: xử lý `ResponseStatusException` bằng cách đặt HTTP status tương ứng.
- `WebFluxResponseStatusExceptionHandler`: mở rộng hỗ trợ tìm status từ annotation `@ResponseStatus` trên exception; handler này được đăng ký trong WebFlux Config.

Trong Spring Boot, còn có cơ chế xử lý lỗi mặc định để tạo error response phù hợp. Khi bổ sung handler riêng, đặt order có chủ đích để exception handler của ứng dụng chạy đúng vị trí so với fallback của Boot và handler mặc định của WebFlux. Ví dụ ở mục 10 dùng `@Order(-2)` cho handler nghiệp vụ riêng.

### 4.4. Không được xem mọi lỗi là lỗi có thể ghi đè response

Một exception có thể xảy ra khi response chưa bắt đầu ghi hoặc sau khi một phần response đã được gửi. Trường hợp thứ hai thường gặp hơn với response streaming như SSE/NDJSON. Khi response đã committed, không thể đổi status từ 200 thành 500 và thay toàn bộ body bằng JSON mới.

Với streaming response, hãy thiết kế định dạng lỗi trong giao thức stream nếu cần; nếu kết nối đã đóng thì log/metric và cleanup là việc còn lại. Không giả định `WebExceptionHandler` luôn có thể tạo một response lỗi hoàn chỉnh.

## 5. Thứ tự ghép chuỗi và vai trò của `WebHttpHandlerBuilder`

### 5.1. Builder lắp các thành phần như thế nào?

`WebHttpHandlerBuilder` có thể được tạo từ Spring `ApplicationContext` để tự phát hiện:

- Một target `WebHandler` có bean name `webHandler`.
- Không hoặc nhiều bean `WebFilter`; được sắp xếp theo order.
- Không hoặc nhiều bean `WebExceptionHandler`; được sắp xếp theo order.
- Một số thành phần tùy chọn như `WebSessionManager`, `ServerCodecConfigurer`, `LocaleContextResolver` và `ForwardedHeaderTransformer`.

Sơ đồ lắp ghép:

~~~text
WebExceptionHandler (outermost)
    |
    v
WebFilter #1
    |
    v
WebFilter #2
    |
    v
Target WebHandler
    |
    v
DispatcherHandler (thường là target)
~~~

Nhiều `WebExceptionHandler` được ghép thành chuỗi xử lý lỗi. Handler nào hoàn tất thành công thì lỗi được coi là đã xử lý; handler nào trả error thì lỗi được chuyển tiếp.

### 5.2. Tự tạo HttpHandler ở mức thấp

Trong một ứng dụng cần tự dựng chain, có thể dùng builder:

~~~java
WebHandler target = exchange -> {
    exchange.getResponse().setStatusCode(HttpStatus.NO_CONTENT);
    return exchange.getResponse().setComplete();
};

HttpHandler httpHandler = WebHttpHandlerBuilder
    .webHandler(target)
    .filter(myWebFilter)
    .exceptionHandler(myWebExceptionHandler)
    .build();
~~~

Đây là đoạn minh họa sử dụng `WebHttpHandlerBuilder` trực tiếp, không phải cấu hình Spring Boot thông thường. `HttpHandler` trả về có thể được nối với adapter của server như Reactor Netty. Trong ứng dụng Boot, auto-configuration thường dựng phần này từ context; không cần tạo một builder khác chỉ để đăng ký filter.

## 6. Phân biệt `WebExceptionHandler` với `@ControllerAdvice`

Hai cơ chế này có phạm vi và thời điểm xử lý khác nhau:

| Cơ chế | Vị trí | Phạm vi phù hợp |
| --- | --- | --- |
| `@ExceptionHandler` trong `@ControllerAdvice` / `@RestControllerAdvice` | Bên trong cơ chế dispatch của controller | Lỗi từ controller/handler được DispatcherHandler quản lý |
| `WebExceptionHandler` | Bao quanh chuỗi WebFilter và target WebHandler | Lỗi thoát khỏi filter chain hoặc target WebHandler, kể cả lỗi từ filter |
| `ResponseStatusExceptionHandler` | Một WebExceptionHandler của framework | Ánh xạ `ResponseStatusException` thành HTTP status |
| Error handler mặc định của Spring Boot | Trong chuỗi xử lý lỗi của Boot | Error response fallback khi không có handler trước đó xử lý |

Ví dụ: nếu một controller ném exception và có `@ExceptionHandler` phù hợp, lỗi có thể được xử lý ngay trong cơ chế dispatch. Nếu một `WebFilter` phát lỗi trước khi request tới `DispatcherHandler`, `@ControllerAdvice` không phải lớp phù hợp để xử lý lỗi đó; `WebExceptionHandler` ở ngoài chuỗi có thể xử lý.

Không cần chọn một cơ chế duy nhất cho toàn ứng dụng. Dùng `@ControllerAdvice` cho lỗi gắn với controller/API domain, và dùng `WebExceptionHandler` cho xử lý ở tầng web pipeline như filter, status mapping toàn cục hoặc lỗi vượt khỏi dispatch.

## 7. `ServerWebExchange`: đối tượng xuyên suốt request

`ServerWebExchange` nối các thành phần trong một HTTP request-response:

~~~text
WebFilter
  |
  | exchange.getRequest()
  | exchange.getResponse()
  | exchange.getAttributes()
  v
DispatcherHandler / controller
  |
  | cùng exchange
  v
WebExceptionHandler nếu lỗi thoát ra
~~~

Các thuộc tính trong `exchange.getAttributes()` hữu ích khi filter muốn truyền thông tin cho handler phía sau, ví dụ request ID hoặc cờ đã qua bước kiểm tra. Chúng thuộc **exchange hiện tại**, không phải field dùng chung giữa các request.

~~~java
exchange.getAttributes().put("requestId", requestId);

String id = exchange.getAttribute("requestId");
~~~

Không lưu request ID của người dùng trong field mutable của singleton filter hoặc controller. Nhiều request chạy đồng thời; thuộc tính của exchange giúp tách trạng thái theo request.

Khi tạo exchange mới bằng `exchange.mutate().build()`, cần hiểu phần request/response nào được giữ và phần nào được thay. Không sao chép thủ công request/response hoặc tự tạo exchange hoàn toàn mới khi chỉ cần sửa một thuộc tính.

## 8. Viết filter production: request ID, header và log kết thúc

Một filter thường hữu ích cho logging/tracing:

~~~java
@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders().set("X-Request-Id", requestId);

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "requestId=" + requestId + ", signal=" + signal));
    }
}
~~~

Các nguyên tắc:

- Gắn ID trước khi gọi chain để controller và exception handler có thể đọc được.
- Đặt response header trước khi response được commit.
- Dùng `doFinally` để quan sát complete/error/cancel; nếu cần đo thời gian, chụp thời điểm bắt đầu bằng clock monotonic như `System.nanoTime()`.
- Không ghi token, cookie, mật khẩu hoặc toàn bộ body vào log mặc định.
- Trong hệ thống phân tán, có thể nhận trace/correlation ID từ gateway tin cậy, nhưng cần xác thực/chuẩn hóa header đầu vào và tránh log dữ liệu do client tùy ý cung cấp.
- Nếu tích hợp Spring Security, cân nhắc thứ tự filter để request ID có mặt cả trong lỗi bảo mật; thứ tự cụ thể phải được thiết kế cùng security chain.

Đừng gọi `subscribe()` bên trong filter. Trả về Publisher của `chain.filter` để framework quản lý lifecycle, lỗi và cancellation. Nếu tự subscribe, response có thể hoàn tất trước công việc, lỗi bị tách khỏi request và cleanup khó dự đoán.

## 9. Viết exception handler production: phân loại lỗi và trả response an toàn

Một exception handler nên xử lý các lỗi đã biết bằng response có cấu trúc, đồng thời chuyển các lỗi còn lại tiếp tục qua chuỗi.

~~~java
@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {
        if (error instanceof CatalogUnavailableException) {
            return writeError(
                exchange,
                HttpStatus.SERVICE_UNAVAILABLE,
                "{\"error\":\"CATALOG_UNAVAILABLE\"}"
            );
        }

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        return Mono.error(error);
    }

    private Mono<Void> writeError(
        ServerWebExchange exchange,
        HttpStatus status,
        String json
    ) {
        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            return Mono.error(
                new IllegalStateException("Response already committed"));
        }

        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Đây là ví dụ rút gọn để minh họa hợp đồng. Trong hệ thống thật:

- Ánh xạ exception sang status và error code theo hợp đồng API, không dựa vào tên class một cách tùy tiện.
- Không trả stack trace, SQL, hostname nội bộ, token hoặc thông tin triển khai cho client.
- Log chi tiết ở server với request ID, nhưng tránh log cùng một exception nhiều lần ở mọi tầng.
- Nếu response đã committed, không cố ghi thêm JSON; ghi log/metric và để kết nối kết thúc theo trạng thái thực tế.
- Không bắt mọi `Throwable` rồi trả 200 OK. Lỗi không nhận diện được phải tiếp tục được báo cho fallback/error infrastructure.

Nếu chỉ cần ánh xạ `ResponseStatusException`, hãy cân nhắc handler có sẵn của Spring thay vì tự viết lại logic status. Với lỗi controller, `@RestControllerAdvice` có thể dễ đọc hơn và cung cấp các cơ chế xử lý exception theo domain.

## 10. Ví dụ Spring Boot 3 + Java 17 hoàn chỉnh

Ví dụ sau minh họa ba thành phần trong một ứng dụng thực:

- `DispatcherHandler` là target `WebHandler` do Spring Boot cấu hình.
- `RequestIdWebFilter` gắn request ID và response header.
- `CatalogWebExceptionHandler` xử lý exception nghiệp vụ ở tầng WebExceptionHandler.
- Controller trả Publisher và tạo cả response thành công lẫn lỗi.

Dùng Spring Boot **3.5.7**, Java 17 và Maven. Đây là một project độc lập; không trộn `spring-boot-starter-web` vào dependencies để tránh Boot chọn Spring MVC thay cho WebFlux.

### 10.1. Cấu trúc project

~~~text
webflux-handler-chain/
├── pom.xml
└── src/main/java/example/webflux/
    ├── WebFluxHandlerChainApplication.java
    ├── DemoController.java
    ├── RequestIdWebFilter.java
    ├── CatalogWebExceptionHandler.java
    └── CatalogUnavailableException.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-handler-chain</artifactId>
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
~~~

### 10.3. `WebFluxHandlerChainApplication.java`

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxHandlerChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxHandlerChainApplication.class, args);
    }
}
~~~

### 10.4. `RequestIdWebFilter.java`

~~~java
package example.webflux;

import java.util.UUID;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders().set("X-Request-Id", requestId);

        System.out.println("before requestId=" + requestId);

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "after requestId=" + requestId + ", signal=" + signal));
    }
}
~~~

Import `Ordered` không cần thiết trong class vì ta dùng annotation `@Order`; có thể xóa import đó trong IDE nếu compiler/linter báo unused import. Nội dung chính của ví dụ là filter tự đăng ký như bean và được order bằng annotation.

### 10.5. `CatalogUnavailableException.java`

~~~java
package example.webflux;

public class CatalogUnavailableException extends RuntimeException {

    public CatalogUnavailableException(String message) {
        super(message);
    }
}
~~~

### 10.6. `CatalogWebExceptionHandler.java`

~~~java
package example.webflux;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class CatalogWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {
        if (!(error instanceof CatalogUnavailableException)) {
            return Mono.error(error);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes =
            "{\"error\":\"CATALOG_UNAVAILABLE\"}".getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

`@Order(-2)` đặt handler nghiệp vụ trước fallback error handler của Spring Boot trong ví dụ này. Nếu ứng dụng có nhiều handler khác, hãy kiểm tra thứ tự thực tế và tránh tạo hai handler cùng nhận rồi cùng ghi một response.

### 10.7. `DemoController.java`

~~~java
package example.webflux;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok(ServerWebExchange exchange) {
        String requestId = exchange.getAttribute(
            RequestIdWebFilter.REQUEST_ID_ATTRIBUTE);

        return Mono.just(Map.of(
            "message", "ok",
            "requestId", requestId
        ));
    }

    @GetMapping("/fail")
    public Mono<String> fail() {
        return Mono.error(
            new CatalogUnavailableException("catalog is temporarily unavailable"));
    }

    @GetMapping("/missing")
    public Mono<String> missing() {
        return Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "not found"));
    }
}
~~~

### 10.8. Chạy ứng dụng

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

Thử endpoint thành công:

~~~bash
curl -i http://localhost:8080/demo/ok
~~~

Kết quả chính:

~~~text
HTTP/1.1 200 OK
X-Request-Id: <UUID được tạo cho request>
Content-Type: application/json

{"message":"ok","requestId":"<cùng UUID>"}
~~~

Thử lỗi nghiệp vụ:

~~~bash
curl -i http://localhost:8080/demo/fail
~~~

Kết quả chính:

~~~text
HTTP/1.1 503 Service Unavailable
X-Request-Id: <UUID được tạo cho request>
Content-Type: application/json

{"error":"CATALOG_UNAVAILABLE"}
~~~

Thử lỗi status của framework:

~~~bash
curl -i http://localhost:8080/demo/missing
~~~

Kết quả chính là HTTP 404. Body lỗi chi tiết phụ thuộc error attributes và cấu hình Spring Boot; không nên dựa vào toàn bộ JSON mặc định như một hợp đồng API cố định.

Log ứng dụng có dạng:

~~~text
before requestId=<UUID>
after requestId=<cùng UUID>, signal=onComplete
~~~

Với request lỗi, filter vẫn có thể quan sát lỗi hoặc signal kết thúc theo đường xử lý thực tế. `CatalogWebExceptionHandler` chỉ xử lý `CatalogUnavailableException`; lỗi `ResponseStatusException` được chuyển tiếp để handler status của framework xử lý.

### 10.9. Vì sao ví dụ này minh họa đúng ba hợp đồng?

- `DispatcherHandler` là target WebHandler; nó route `/demo/ok`, `/demo/fail` và `/demo/missing` tới controller.
- `RequestIdWebFilter` chạy trước target handler, gắn request ID vào exchange và header. Controller đọc lại giá trị từ đúng exchange.
- `CatalogWebExceptionHandler` nằm ở lớp exception chain ngoài filter/handler. Nó xử lý lỗi nghiệp vụ bằng cách ghi HTTP 503 và JSON body.
- Khi handler không nhận diện lỗi, nó trả `Mono.error(error)`; handler tiếp theo có thể xử lý, ví dụ handler status của WebFlux cho `ResponseStatusException`.
- Controller trả về `Mono`; không tự `subscribe()`, vì Spring quản lý subscription và response lifecycle.

## 11. Kiểm thử filter và exception handler

Có thể dùng `WebTestClient` để kiểm thử tích hợp mà không cần viết HTTP client thủ công. Ví dụ test trong ứng dụng đã cấu hình WebFlux:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebPipelineIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdIsAddedToSuccessfulResponse() {
        client.get()
            .uri("/demo/ok")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.message").isEqualTo("ok")
            .jsonPath("$.requestId").exists();
    }

    @Test
    void customExceptionIsMappedTo503() {
        client.get()
            .uri("/demo/fail")
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.error").isEqualTo("CATALOG_UNAVAILABLE");
    }
}
~~~

Đây là đoạn test minh họa; project cần thêm dependency `spring-boot-starter-test` và các import JUnit/Spring Boot tương ứng. Các assertion tập trung vào hợp đồng HTTP: status, header và error code. Không nên test thứ tự thread bằng cách so sánh tên thread hoặc dựa vào thời gian ngủ.

Các trường hợp kiểm thử đáng có:

- Filter gọi chain đúng một lần khi request hợp lệ.
- Filter short-circuit trả status dự kiến và không gọi handler phía trong.
- Request ID được gắn vào cả response thành công và lỗi.
- Exception handler xử lý đúng exception đã chọn.
- Exception không nhận diện được được chuyển tiếp, không bị biến thành 200.
- Khi response đã committed, handler không cố ghi body lỗi lần thứ hai.
- Hai request đồng thời không chia sẻ thuộc tính exchange của nhau.

## 12. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Nghĩ `WebHandler` chính là controller.** Trong ứng dụng chuẩn, `DispatcherHandler` là target WebHandler và controller là handler được dispatch tới. Hãy phân biệt tầng tổng thể với endpoint cụ thể.

**Lỗi 2 — Viết filter nhưng quên gọi `chain.filter(exchange)`.** Request bị chặn tại filter. Chỉ short-circuit khi bạn thực sự muốn tự tạo response.

**Lỗi 3 — Gọi `chain.filter(exchange)` hai lần.** Có thể làm cùng request được xử lý nhiều lần, tạo side effect hoặc response đã committed. Trả về một chuỗi Publisher duy nhất.

**Lỗi 4 — Gọi `subscribe()` bên trong filter.** Framework không còn quản lý công việc đó trong cùng response lifecycle; lỗi và cancellation dễ bị tách. Trả về `chain.filter`.

**Lỗi 5 — Dùng `@ControllerAdvice` để xử lý lỗi phát sinh trước DispatcherHandler.** Filter nằm ngoài dispatch; dùng `WebExceptionHandler` ở tầng WebHandler API cho lỗi filter/global.

**Lỗi 6 — Exception handler trả `Mono.empty()` nhưng không ghi hoặc hoàn tất response.** Framework có thể coi lỗi đã xử lý trong khi response không có status/body như mong muốn. Ghi response hoặc gọi `setComplete` trước khi hoàn tất.

**Lỗi 7 — Trả `Mono.error(error)` cho exception đã xử lý.** Điều đó báo rằng lỗi chưa được xử lý và cho phép handler tiếp theo chạy. Khi đã ghi response thành công, trả Publisher ghi response để nó hoàn tất bình thường.

**Lỗi 8 — Ghi body lỗi sau khi response committed.** Status/header không thể thay đổi và body thứ hai có thể làm hỏng giao thức. Kiểm tra `response.isCommitted()`.

**Lỗi 9 — Bắt mọi lỗi rồi trả 200.** Client không thể phân biệt thành công và thất bại. Map lỗi đã biết sang status đúng, lỗi còn lại tiếp tục tới fallback.

**Lỗi 10 — Không cấu hình order.** Nhiều filter/exception handler có thể chạy theo thứ tự không như dự định. Dùng `@Order`/`Ordered` và kiểm tra cả bean do framework/security/Boot tạo.

**Lỗi 11 — Đọc request body trong filter rồi đọc lại ở controller.** Body thường là stream một lần; filter có thể đã tiêu thụ dữ liệu. Dùng API cache phù hợp hoặc thiết kế body caching rõ ràng.

**Lỗi 12 — Lưu request state trong field của singleton filter.** Nhiều request chạy đồng thời và có thể ghi đè dữ liệu. Dùng `ServerWebExchange.getAttributes()` hoặc Reactor Context theo đúng nhu cầu.

**Lỗi 13 — Nghĩ WebExceptionHandler luôn có thể đổi HTTP status.** Nếu response đã commit, không thể thay status hoặc gửi một body mới. Với stream, hãy thiết kế error event hoặc chấp nhận kết thúc kết nối.

**Lỗi 14 — Ghi exception message nội bộ trực tiếp vào response.** Có thể lộ thông tin nhạy cảm. Dùng error code và message an toàn; log chi tiết có correlation ID ở server.

**Lỗi 15 — Dùng `block()` hoặc I/O blocking trong filter.** Filter nằm trên request path; blocking có thể chiếm event-loop. Dùng API reactive hoặc cô lập thư viện blocking bằng chiến lược phù hợp như boundedElastic khi thật sự cần.

**Lỗi 16 — Nhầm `WebFilter` với `HandlerInterceptor`.** WebFilter bao quanh toàn bộ chuỗi WebHandler; interceptor thuộc cơ chế handler cụ thể. Chọn theo phạm vi cần áp dụng.

**Lỗi 17 — Tự tạo một WebHandler bean trong ứng dụng Boot mà không hiểu DispatcherHandler.** Có thể thay thế hoặc xung đột với target handler mặc định. Thông thường hãy dùng controller/RouterFunction và đăng ký filter/exception handler bean.

**Lỗi 18 — Cho rằng `WebExceptionHandler` thay thế mọi `@ExceptionHandler`.** Exception trong controller có thể được xử lý bên trong dispatch; WebExceptionHandler là lớp ngoài cho lỗi còn thoát ra khỏi chain.

## 13. Bài tập tự kiểm tra

1. `WebHandler.handle` nhận tham số gì và trả kiểu gì? **`ServerWebExchange` và `Mono<Void>`.**
2. `WebFilter` cần gọi phương thức nào để chuyển request cho phần còn lại? **`chain.filter(exchange)`.**
3. Nếu filter không gọi chain và trả `exchange.getResponse().setComplete()`, controller có chạy không? **Không**, filter đã short-circuit.
4. Khi `WebExceptionHandler` hoàn tất thành công, điều đó có nghĩa gì? **Lỗi đã được xử lý.**
5. Khi handler trả `Mono.error(ex)`, điều gì xảy ra? **Lỗi tiếp tục tới handler tiếp theo trong chuỗi.**
6. Trong WebFlux chuẩn, target `WebHandler` thường là class nào? **`DispatcherHandler`.**
7. `DispatcherHandler` tìm endpoint bằng loại special bean nào? **`HandlerMapping`.**
8. Bean `WebFilter` có thể được đăng ký như thế nào trong Spring Boot? **Khai báo bean/`@Component`; Spring phát hiện tự động.**
9. Làm sao quy định thứ tự filter? **`@Order` hoặc `Ordered`.**
10. Exception phát sinh trong filter có được `@ControllerAdvice` xử lý theo cơ chế controller thông thường không? **Filter ở ngoài DispatcherHandler; dùng WebExceptionHandler cho phạm vi này.**
11. Khi response đã committed, exception handler có thể đổi status từ 200 sang 500 không? **Không.**
12. Vì sao không nên gọi `subscribe()` trong filter? **Nó tách công việc khỏi lifecycle request-response do framework quản lý.**
13. Vì sao request body không nên được đọc tùy tiện trong filter? **Body thường chỉ tiêu thụ được một lần; controller có thể không còn dữ liệu.**
14. `ServerWebExchange.getAttributes()` phù hợp để lưu gì? **Metadata theo request như request ID; không phải trạng thái global.**
15. Nếu có `ResponseStatusException`, handler framework nào có thể ánh xạ status? **`ResponseStatusExceptionHandler`/`WebFluxResponseStatusExceptionHandler`.**
16. Trong ứng dụng Boot, vì sao custom WebExceptionHandler cần order rõ ràng? **Để nó chạy đúng vị trí so với error fallback của Boot và handler mặc định WebFlux.**
17. `WebFilter` có áp dụng cho functional endpoint không? **Có**, vì filter bao quanh target WebHandler, trong đó DispatcherHandler có thể dispatch functional routes.
18. Nếu custom WebExceptionHandler không nhận loại exception, nên trả gì? **`Mono.error(error)` để chuyển tiếp.**

## 14. Ghi nhớ và tài liệu tham khảo

- **`WebHandler`** là hợp đồng xử lý một `ServerWebExchange` và trả `Mono<Void>`.
- **`DispatcherHandler`** thường là target WebHandler trong ứng dụng WebFlux chuẩn; nó điều phối `HandlerMapping`, `HandlerAdapter` và `HandlerResultHandler`.
- **`WebFilter`** bao quanh phần còn lại của chuỗi filter và target handler; dùng cho logic xuyên suốt request.
- **`WebExceptionHandler`** nằm ngoài filter/handler chain; hoàn tất nghĩa là đã xử lý lỗi, trả error nghĩa là chuyển tiếp.
- **`@ControllerAdvice`** xử lý lỗi trong phạm vi dispatch controller; `WebExceptionHandler` bao phủ lỗi thoát ra từ tầng web pipeline.
- Dùng `ServerWebExchange` để truy cập request, response và thuộc tính theo request; tránh state mutable dùng chung.
- Trả Publisher để framework quản lý lifecycle; không tự subscribe/block trong filter hoặc handler.

Tài liệu chính thức để đối chiếu:

1. [Spring Framework Reference — Reactive Core / WebHandler API, Filters và Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, `WebHandler`, bean discovery, `WebFilter` và `WebExceptionHandler`.
2. [Spring Framework Reference — DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): front controller, `HandlerMapping`, `HandlerAdapter` và `HandlerResultHandler`.
3. [Spring Framework Javadoc — WebHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebHandler.html): hợp đồng `handle(ServerWebExchange)`.
4. [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html) và [WebFilterChain](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html): filter contract và chuyển tiếp chain.
5. [Spring Framework Javadoc — WebExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): hợp đồng xử lý lỗi và ý nghĩa Mono<Void>.
6. [Spring Framework Javadoc — WebHttpHandlerBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html): ghép WebHandler, filters, exception handlers và server adapter.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): auto-configuration WebFlux, WebFilter bean, error handling và cấu hình ứng dụng reactive.
