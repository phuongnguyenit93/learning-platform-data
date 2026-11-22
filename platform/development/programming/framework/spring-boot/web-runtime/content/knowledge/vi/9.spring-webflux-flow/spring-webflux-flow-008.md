# WebFilter, WebExceptionHandler và xử lý trước hoặc sau handler trong Spring WebFlux

## 1. Mục tiêu và phạm vi

Trong Spring Boot sử dụng Spring WebFlux, xử lý một yêu cầu HTTP không chỉ gồm controller hay functional handler. Request còn đi qua các bộ lọc, khâu tìm handler, chuyển đổi dữ liệu, xử lý lỗi và quá trình ghi phản hồi. Hai điểm mở rộng ở mức web runtime đặc biệt quan trọng là **`WebFilter`**, dùng để bao quanh quá trình xử lý request, và **`WebExceptionHandler`**, dùng để tiếp nhận lỗi chưa được xử lý trong chuỗi WebFlux.

Sau bài này, người học có thể:

1. Vẽ đúng đường đi của request qua `HttpHandler`, `WebFilter`, `WebHandler` và `WebExceptionHandler`.
2. Viết logic trước handler và sau khi xử lý downstream bằng `WebFilterChain.filter(exchange)`, hiểu khác biệt giữa lúc *xây pipeline* và lúc *publisher được subscribe*.
3. Kiểm soát thứ tự filter bằng `@Order` hoặc `Ordered`, và nhận diện lý do thứ tự chạy trước/sau có thể đảo chiều.
4. Chọn `@ExceptionHandler`/`@RestControllerAdvice`, `WebExceptionHandler` hay cơ chế riêng của Spring Security đúng vị trí.
5. Xử lý lỗi khi response chưa commit, tránh cố thay HTTP status/header sau khi đã gửi dữ liệu.
6. Không gây blocking, double subscription, tiêu thụ body hai lần hoặc làm mất ngữ cảnh request trong pipeline reactive.
7. Tự chạy và kiểm tra chương trình Java 17+ Spring Boot WebFlux có filter, handler, error handler và phản hồi mong đợi.

Ví dụ chính dành cho **Spring Boot 3.x / Spring Framework 6 / Java 17+** với dependency `spring-boot-starter-webflux`. Các tên API và cách đăng ký có thể khác theo thế hệ framework; khi nâng cấp Spring Boot, kiểm tra tài liệu của phiên bản triển khai.

## 2. Tổng quan luồng request WebFlux

Ở mức khái niệm, luồng xử lý của WebFlux với server reactive như Reactor Netty có thể hình dung như sau:

~~~text
HTTP request
   |
Reactor Netty / server adapter
   |
HttpHandler / HttpWebHandlerAdapter
   |
ExceptionHandlingWebHandler -----------------------+
   |                                                |
   v                                                | lỗi chưa xử lý
FilteringWebHandler                                  |
   | WebFilter A (trước)                             |
   |   WebFilter B (trước)                           |
   |     WebFilterChain.filter(exchange)             |
   |       DispatcherHandler / WebHandler            |
   |         HandlerMapping -> handler/controller    |
   |         HandlerAdapter / HandlerResultHandler   |
   |         ghi response hoặc phát sinh lỗi --------+
   |   WebFilter B (tín hiệu hoàn tất/lỗi)
   | WebFilter A (tín hiệu hoàn tất/lỗi)
   v
HTTP response (status, headers, body)
~~~

Sơ đồ biểu diễn tầng xử lý, không cam kết mọi callback đều chạy một lần theo đúng thứ tự thời gian nếu có lỗi, cancellation hoặc xử lý bất đồng bộ. `WebHttpHandlerBuilder` có thể lắp ráp các `WebFilter` và `WebExceptionHandler` lấy từ application context thành web handler chain. Trong WebFlux annotated-controller, `DispatcherHandler` điều phối `HandlerMapping`, `HandlerAdapter` và `HandlerResultHandler`.

Ba interface cần phân biệt:

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| `WebFilter` | Xử lý xung quanh các request đi qua chuỗi WebFlux: chỉnh request/response, logging, correlation, chính sách tiền xử lý | Nằm bên ngoài logic controller/functional route |
| `WebHandler` | Nhận `ServerWebExchange` và trả `Mono<Void>`; phần handler lõi thường do framework điều phối | Xử lý request ở mức web runtime |
| `WebExceptionHandler` | Nhận `ServerWebExchange` và `Throwable` chưa được xử lý để tạo lỗi HTTP hoặc chuyển tiếp lỗi | Bao quanh chuỗi xử lý, có thể thấy lỗi từ filter/handler nếu chưa bị nuốt |

**Không nhầm WebFlux `WebFilter` với Servlet `Filter` hay `HandlerInterceptor` của Spring MVC.** Chúng thuộc các mô hình runtime khác nhau. `WebFilter` hoạt động trên `ServerWebExchange`, trả một reactive publisher; Servlet filter dùng `HttpServletRequest`/`HttpServletResponse` cùng `FilterChain` blocking-style.

## 3. Contract của WebFilter và WebFilterChain

Interface WebFlux có dạng:

~~~java
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}
~~~

Hai tham số quan trọng:

- `ServerWebExchange` chứa request, response, attributes và các thông tin gắn với request. Từ đó có thể đọc method, path, headers, truy cập phản hồi hoặc chia sẻ dữ liệu cho các bước downstream.
- `WebFilterChain` là phần còn lại của chuỗi. `chain.filter(exchange)` trả `Mono<Void>` biểu diễn việc xử lý downstream, **không phải** câu lệnh Java “chặn và đợi đến khi controller chạy xong”.

Một filter thường thực hiện vài thao tác chuẩn bị rồi **trả về** publisher từ downstream, có thể nối thêm các operator để quan sát kết thúc:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    exchange.getResponse().getHeaders().set("X-Trace", "example");

    return chain.filter(exchange)
            .doOnError(error -> logger.warn("Web request failed", error))
            .doFinally(signal -> logger.debug("Request terminated: {}", signal));
}
~~~

Đây là fragment của class có logger và imports tương ứng, không phải chương trình Java độc lập. `doFinally` có thể nhận tín hiệu `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Nó phù hợp ghi metrics/cleanup nhẹ; **không** phải vị trí an toàn để thêm header bắt buộc sau khi response đã hoàn tất.

### 3.1. Đăng ký filter

Có thể khai báo bằng `@Component` trên class `implements WebFilter`, hoặc tạo bean `@Bean WebFilter` trong `@Configuration`. Spring WebFlux sẽ thu thập các filter khi lắp ráp web handler. Một filter phù hợp có thể áp dụng cho cả annotated controllers và functional endpoints trong cùng WebFlux application.

Đừng dùng `FilterRegistrationBean` kiểu Servlet để đăng ký `WebFilter` trong Reactor Netty application. Nếu dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên Servlet MVC trừ khi bạn chọn rõ web application type; cần xác nhận runtime trước khi debug filter “không chạy”.

## 4. Trước handler, sau handler và reactive subscription

Điểm dễ sai nhất là hiểu “chạy sau” như đoạn lệnh Java đặt sau `chain.filter(exchange)`. Ví dụ:

~~~java
Mono<Void> downstream = chain.filter(exchange);
log.info("After calling chain.filter");
return downstream;
~~~

Dòng log trên thực thi khi phương thức filter xây dựng publisher, **không đảm bảo handler đã xử lý xong**. Muốn thực hiện tác vụ sau khi downstream hoàn tất, phải gắn operator vào tín hiệu của publisher.

### 4.1. Tiền xử lý trước downstream

Các việc phù hợp:

- Kiểm tra request method, path, headers, correlation ID.
- Đưa dữ liệu đơn giản vào `exchange.getAttributes()` để downstream sử dụng.
- Chuẩn bị response headers trước khi ghi body.
- Từ chối một request theo chính sách đơn giản nếu đã có thông tin xác định trước handler.
- Tạo timer hoặc metric context, tránh IO blocking trong filter.

Ví dụ minh họa:

~~~java
exchange.getAttributes().put("requestStartNanos", System.nanoTime());
exchange.getResponse().getHeaders().set("X-Request-Category", "api");
return chain.filter(exchange);
~~~

Đặt thông tin vào exchange attributes thích hợp cho dữ liệu thuộc *một request*. Đừng đặt request-scoped mutable state vào field singleton của filter.

### 4.2. Hậu xử lý khi downstream hoàn tất

Khi chỉ muốn thực hiện tác vụ sau khi downstream hoàn thành thành công:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                metrics.recordCompleted(exchange.getRequest().getPath().value())));
~~~

Fragment này giả định có `metrics` trong bean. `then` chỉ chạy hành động khi downstream **hoàn tất bình thường**; nếu phát sinh lỗi, publisher lỗi được truyền tiếp và hành động sau `then` không chạy. Nếu cần ghi nhận thành công, lỗi và cancellation, cân nhắc `doFinally`, nhưng callback phải ngắn, không blocking.

Để tạo publisher *mỗi lần được subscribe*, có thể dùng `Mono.defer(() -> { ... })` cho các bước mang side effect cần gắn vào subscription. Thông thường request được WebFlux subscribe một lần; tránh tự gọi `subscribe()` từ filter vì sẽ tạo luồng xử lý riêng và khiến error, cancellation hoặc backpressure không còn đi theo response pipeline chính.

### 4.3. Thứ tự chạy trước và sau

Giả sử chuỗi có filter A bọc filter B, cả hai đều dùng `chain.filter` và `doFinally`:

~~~text
A - phần trước
  B - phần trước
    handler / ghi response
  B - tín hiệu kết thúc
A - tín hiệu kết thúc
~~~

Đó là mô hình bao lồng nhau. Khi có lỗi hoặc cancel, những operator đã đăng ký có thể nhận các tín hiệu khác nhau. Không nên mặc định đoạn `then` hậu xử lý sẽ chạy với mọi kết quả.

## 5. Thứ tự WebFilter bằng @Order và Ordered

Các bean `WebFilter` được sắp xếp theo order. Quy tắc Spring thông thường là **giá trị order thấp hơn chạy trước ở nhánh đi vào**:

~~~java
@Component
@Order(-100)
class FirstFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
~~~

Đây là fragment và cần các import `@Component`, `@Order`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, `Mono`. Nếu filter X có `@Order(-100)` và filter Y `@Order(100)`, X thường nhận request trước Y. Với các nhánh hậu xử lý bao lồng, Y có thể thấy completion trước X.

Có thể triển khai interface `Ordered` và trả order từ `getOrder()` thay cho `@Order`. **Không dựa vào thứ tự bean được viết trong source** hoặc hai filter cùng order khi cần chuỗi chính xác; hãy định nghĩa rõ thứ tự và viết test.

### 5.1. Filter có thể chặn downstream

Nếu filter trả `Mono<Void>` tự xử lý request mà không gọi `chain.filter(exchange)`, handler phía sau sẽ không chạy:

~~~java
if ("/maintenance".equals(exchange.getRequest().getPath().value())) {
    exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
~~~

Đây là cách có chủ đích chặn request. Phải đảm bảo filter tạo response hợp lệ và không vô tình chặn những route khác. Đừng gọi `chain.filter` sau khi đã chọn phản hồi kết thúc riêng.

## 6. WebExceptionHandler và cách lỗi được truyền qua pipeline

Interface:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

Khi chuỗi bên trong phát ra tín hiệu lỗi và lỗi chưa được xử lý, tầng exception handling có thể lần lượt thử các `WebExceptionHandler` theo thứ tự. Một handler có hai khả năng chính:

- **Đã xử lý:** đặt status/header, ghi body nếu thích hợp rồi trả publisher **hoàn tất thành công**.
- **Không xử lý được:** trả `Mono.error(ex)` để chuyển lỗi cho handler tiếp theo hoặc cho runtime.

Ví dụ tối giản:

~~~java
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    if (!(ex instanceof MissingApiKeyException)) {
        return Mono.error(ex);
    }

    ServerHttpResponse response = exchange.getResponse();
    if (response.isCommitted()) {
        return Mono.error(ex);
    }

    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    return response.setComplete();
}
~~~

Đây là fragment cần exception class và imports tương ứng. Nó cho thấy cần kiểm tra cả **loại lỗi** lẫn **trạng thái response** trước khi đổi status. Trong API có xác thực, 401 còn có quy tắc challenge phù hợp; không dùng fragment này làm thay thế trực tiếp cho Spring Security.

### 6.1. Lỗi đến từ đâu?

`WebExceptionHandler` có thể nhận:

- Lỗi được trả bằng `Mono.error` từ một `WebFilter` trước khi handler chạy.
- Lỗi từ phân giải handler, request mapping hoặc những phần bên trong WebFlux không được giải quyết tại tầng cụ thể.
- Lỗi từ controller/functional handler và các bước reactive downstream nếu chưa bị `@ExceptionHandler` hoặc operator khác xử lý.
- Lỗi khi xử lý response, nhưng **không đồng nghĩa** còn có thể đổi status/body nếu response đã commit.

Nếu filter dùng `onErrorResume` để chuyển lỗi downstream thành phản hồi bình thường, lỗi ấy có thể **không đến** `WebExceptionHandler` nữa. Tương tự, lỗi trong annotated controller được `@ExceptionHandler` xử lý thành công thường không cần đi tới tầng global exception handler.

### 6.2. Thứ tự WebExceptionHandler

Các `WebExceptionHandler` được sắp xếp theo order. Một handler ứng dụng cần chạy trước cơ chế lỗi mặc định của Spring Boot nên có order sớm hơn handler mặc định, và chỉ xử lý **những exception mình sở hữu**.

Trong Spring Boot 3.x, `DefaultErrorWebExceptionHandler` mặc định thường đăng ký với order `-1`. Vì vậy ví dụ custom `WebExceptionHandler` có `@Order(-2)` thường được thử trước. Đây là ví dụ theo Boot 3.x; khi thay version, kiểm tra thứ tự của các handler được đăng ký thực tế.

Không tạo một `WebExceptionHandler` bắt tất cả `Throwable` rồi luôn trả 200 hoặc 400. Làm vậy che dấu lỗi lập trình, lỗi hạ tầng và có thể phá hợp đồng HTTP. Những exception ngoài phạm vi nên được propagate.

## 7. So sánh WebExceptionHandler, @ExceptionHandler và onErrorResume

| Cách xử lý | Phạm vi phù hợp | Hạn chế quan trọng |
|---|---|---|
| `@ExceptionHandler` trong controller | Lỗi của controller và xử lý handler được framework hỗ trợ | Không phải cơ chế toàn cục cho lỗi trước routing ở filter |
| `@RestControllerAdvice` | Chuẩn hóa lỗi của annotated controllers ở nhiều class | Không thay thế WebExceptionHandler cho mọi lỗi ngoài controller |
| `WebExceptionHandler` | Lỗi chưa được xử lý từ chain WebFlux, bao gồm filter và handler | Không thể ghi lại status/header khi response đã commit |
| `onErrorResume` trong reactive pipeline | Khôi phục lỗi cụ thể ở nơi biết ngữ cảnh nghiệp vụ | Có thể bắt lỗi quá rộng hoặc che lỗi của downstream |
| `WebFilter` trả response sớm | Trả lời request trước handler, ví dụ chặn theo điều kiện đơn giản | Phải bảo đảm không gọi tiếp chain hoặc ghi response hai lần |
| Spring Security reactive entry point/denied handler | 401/403 liên quan authentication và authorization | Nên tuân theo contract của security chain |

### 7.1. Cẩn thận với onErrorResume trong WebFilter

Ví dụ:

~~~java
return chain.filter(exchange)
        .onErrorResume(MyDomainException.class, error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(HttpStatus.CONFLICT);
            return exchange.getResponse().setComplete();
        });
~~~

Đây là fragment hợp lệ về ý tưởng, nhưng phải hiểu rằng filter vừa nhận trách nhiệm xử lý lỗi của **cả downstream**. Nếu mọi filter tự `onErrorResume(Throwable.class, ...)`, handler lỗi chính thức sẽ khó quan sát lỗi và có thể bị thay bởi response không nhất quán. Với lỗi nghiệp vụ của annotated controller, thường đặt `@ExceptionHandler` gần controller hoặc dùng advice có chủ đích.

### 7.2. Errors từ WebFilter có vào @RestControllerAdvice?

Thông thường **không**. Một lỗi phát sinh trước khi request vào annotated controller, chẳng hạn trong `WebFilter`, không nằm trong cơ chế xử lý exception của controller. Dùng `WebExceptionHandler` hoặc xử lý lỗi ngay tại filter/security layer phù hợp.

Ngược lại, lỗi được ném trong controller hoặc publisher mà controller trả về có thể được Spring WebFlux xử lý bằng `@ExceptionHandler` nếu còn ở giai đoạn có thể tạo response. Các lỗi phát sinh rất muộn sau khi đã ghi response cần phương án khác.

## 8. Điểm commit của ServerHttpResponse và beforeCommit

`ServerHttpResponse` trong WebFlux có trạng thái commit. Sau khi headers và status đã được phát xuống tầng HTTP, không thể đảo ngược những dữ liệu ấy.

Những phương thức thường gặp:

- `response.setStatusCode(HttpStatus.BAD_REQUEST)`: yêu cầu đặt mã phản hồi, thành công nếu response chưa commit.
- `response.getHeaders().set(...)`: chuẩn bị header cho response chưa commit.
- `response.writeWith(Publisher<DataBuffer>)`: ghi body bất đồng bộ và có thể kích hoạt commit.
- `response.setComplete()`: tín hiệu hoàn tất response, có thể kích hoạt quá trình commit nếu chưa xảy ra.
- `response.isCommitted()`: trả về trạng thái đã commit; hữu ích khi xử lý exception.
- `response.beforeCommit(Supplier<? extends Mono<Void>> action)`: đăng ký tác vụ bất đồng bộ được thực thi trước thời điểm commit.

Ví dụ ở một filter:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders().set("X-Response-Ready", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
~~~

`beforeCommit` hữu ích khi muốn đặt header dựa trên trạng thái cuối được biết ngay trước commit. **Đăng ký callback sớm** và giữ callback trả một `Mono<Void>` thực sự phản ánh công việc; không gọi `subscribe()` thủ công trong callback.

Đừng cố thêm header ở `doFinally` hoặc `then` sau khi body đã ghi. `then` sau `chain.filter(exchange)` không phải cơ chế “sửa response trước commit”. Nếu cần thay status khi lỗi xuất hiện, xử lý trước khi response được gửi; khi `isCommitted()` là true, propagating/logging và hoàn tất kết nối thường là các lựa chọn còn lại.

### 8.1. Lỗi giữa streaming

Một response SSE hoặc file lớn có thể đã gửi `200 OK` cùng các chunk đầu tiên khi một publisher gặp lỗi. Lúc ấy không thể chuyển thành `500` và gửi một Problem Details JSON mới. Có thể gửi một tín hiệu lỗi ở cấp giao thức ứng dụng **nếu stream còn gửi được và giao thức hỗ trợ**, hoặc ngừng stream, log và giải phóng tài nguyên.

Việc `response.isCommitted()` false tại thời điểm A không đảm bảo đến thời điểm B vẫn chưa commit. Không giải quyết concurrency/race chỉ bằng cách kiểm tra trước rồi đợi một async operation lâu; phải thiết kế luồng xử lý lỗi trước khi bắt đầu viết body.

## 9. Ví dụ Java 17+ chạy được trên Spring Boot WebFlux

Ví dụ này thể hiện ba request:

1. `GET /ok`: filter chuẩn bị header, handler trả nội dung bình thường.
2. `GET /blocked`: filter tạo lỗi trước handler, `WebExceptionHandler` chuyển thành status 403.
3. `GET /handler-error`: controller phát lỗi, `@RestControllerAdvice` trả status 422.

### 9.1. Tạo project

Sử dụng Java 17+ và Maven. Tạo file `pom.xml` tại thư mục project:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-chain-demo</artifactId>
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

Không thêm `spring-boot-starter-web` vào ví dụ vì mục tiêu là chạy với WebFlux reactive server.

Đặt file `src/main/java/example/webflux/WebFluxChainDemoApplication.java`:

~~~java
package example.webflux;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxChainDemoApplication.class, args);
    }
}

class FilterDeniedException extends RuntimeException {
    FilterDeniedException() {
        super("blocked at filter");
    }
}

class HandlerRuleException extends RuntimeException {
    HandlerRuleException() {
        super("handler rule");
    }
}

@Component
@Order(-100)
class TraceAndGateFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        exchange.getResponse().getHeaders().set("X-Filter", "entered");
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set("X-Commit", "ready");
            return Mono.empty();
        });

        String path = exchange.getRequest().getPath().pathWithinApplication().value();
        if ("/blocked".equals(path)) {
            return Mono.error(new FilterDeniedException());
        }

        return chain.filter(exchange);
    }
}

@Component
@Order(-2)
class FilterExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (!(ex instanceof FilterDeniedException)) {
            return Mono.error(ex);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(ex);
        }

        response.setStatusCode(HttpStatus.FORBIDDEN);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
        byte[] bytes = "blocked at filter\n".getBytes(StandardCharsets.UTF_8);
        DataBuffer body = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(body));
    }
}

@RestController
class ApiController {

    @GetMapping(path = "/ok", produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> ok() {
        return Mono.just("ok");
    }

    @GetMapping("/handler-error")
    Mono<String> fail() {
        return Mono.error(new HandlerRuleException());
    }
}

@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(HandlerRuleException.class)
    ResponseEntity<Map<String, String>> handle(HandlerRuleException ex) {
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

Code đặt trong cùng một file có đúng một public class trùng tên file; các class còn lại có package visibility và đều nằm trong phạm vi component scan của `@SpringBootApplication`.

### 9.2. Chạy và kiểm tra

Yêu cầu JDK 17+, Maven và cổng 8080 còn trống:

~~~bash
mvn spring-boot:run
~~~

Tại terminal khác:

~~~bash
curl -i http://localhost:8080/ok
curl -i http://localhost:8080/blocked
curl -i http://localhost:8080/handler-error
~~~

Các kết quả quan trọng (thứ tự headers, `Date`, `Content-Length`, `Transfer-Encoding` tùy runtime):

| Request | Status dự kiến | Header quan trọng | Body |
|---|---:|---|---|
| `GET /ok` | 200 | `X-Filter: entered`, `X-Commit: ready` | `ok` |
| `GET /blocked` | 403 | `X-Filter: entered`, `X-Commit: ready` | `blocked at filter` kèm newline |
| `GET /handler-error` | 422 | `X-Filter: entered`, `X-Commit: ready` | JSON `{"error":"handler rule"}` |

Từ ví dụ quan sát được:

- `TraceAndGateFilter` chạy trước handler và đăng ký callback `beforeCommit`.
- Với `/blocked`, filter trả `Mono.error` **không gọi** `chain.filter`; controller không được chạy. Custom `FilterExceptionHandler` bắt lỗi và ghi 403/plain text.
- Với `/handler-error`, lỗi phát ra từ publisher do controller trả về. `@RestControllerAdvice` tạo response 422/JSON; custom `WebExceptionHandler` chỉ nhận những lỗi còn propagate tới tầng của nó và không tự đổi 422.
- `X-Commit` được thiết lập tại callback trước commit, không đặt muộn sau khi response đã xong.
- Nếu bỏ `@Order(-2)` hoặc đăng ký một error handler bắt mọi lỗi với thứ tự muộn, có thể bị default error handler xử lý trước; cần kiểm tra thứ tự thực tế.

Ví dụ này cố ý chỉ xét lỗi cụ thể `FilterDeniedException`. Trong hệ thống có xác thực, xử lý 401/403 nên dùng các hook phù hợp của Spring Security như `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`.

## 10. Kiểm thử bằng WebTestClient

Bài kiểm tra API không chỉ xác nhận status mà còn phân biệt lỗi do filter và controller advice.

Với project ví dụ, thêm vào `pom.xml` dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đoạn sau là ví dụ **trong lớp test có `WebTestClient client` được inject và cấu hình bằng Spring Boot test**; không phải class test độc lập:

~~~java
client.get().uri("/ok").exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Filter", "entered")
        .expectHeader().valueEquals("X-Commit", "ready")
        .expectBody(String.class).isEqualTo("ok");

client.get().uri("/blocked").exchange()
        .expectStatus().isForbidden()
        .expectHeader().valueEquals("X-Filter", "entered")
        .expectBody(String.class).isEqualTo("blocked at filter\n");

client.get().uri("/handler-error").exchange()
        .expectStatus().isEqualTo(422)
        .expectBody()
        .jsonPath("$.error").isEqualTo("handler rule");
~~~

Có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` kết hợp `@AutoConfigureWebTestClient` theo cấu hình test Spring Boot đang dùng để chạy against application. Dùng WebTestClient giúp kiểm tra API reactive mà không tự subscribe vào publisher.

Nên bổ sung những kiểm thử thực tế:

1. Lỗi trong filter *trước* handler, xác nhận controller không được gọi và đúng error handler xử lý.
2. Lỗi bên trong controller, xác nhận `@RestControllerAdvice` xử lý đúng và không bị lỗi global che.
3. Hai filter có order khác nhau, xác nhận header/attribute/callback theo thứ tự mong muốn.
4. Filter trả `setComplete()` để chặn request, xác nhận không có response body ngoài ý muốn.
5. Lỗi sau khi streaming đã phát một phần body, xác nhận code không cố đặt status mới.
6. Cancellation/timeout và cleanup, đo không có lời gọi blocking giữ event loop.
7. Filter đọc body có tương thích với controller downstream hoặc không nếu có nhu cầu thực sự.

## 11. Đặt logic tại đúng lớp: một bảng quyết định

| Yêu cầu | Nên bắt đầu ở | Giải thích |
|---|---|---|
| Gắn correlation ID, một header chung | `WebFilter` + `beforeCommit` khi cần | Chạy trước handler; đăng ký header trước lúc commit |
| Kiểm tra request header chung cho mọi route | `WebFilter` | Có thể từ chối sớm; trả publisher phù hợp |
| Xử lý lỗi thuộc một annotated controller | `@ExceptionHandler` | Gần ngữ cảnh nghiệp vụ, dễ ánh xạ lỗi |
| Chuẩn hóa lỗi controller trên nhiều controller | `@RestControllerAdvice` | Tái sử dụng chính sách lỗi annotation-based |
| Lỗi từ filter/routing chưa được xử lý | `WebExceptionHandler` | Bao phủ tầng WebFlux bên ngoài handler |
| 401/403 từ cơ chế authentication/authorization | Spring Security reactive entry point/denied handler | Giữ contract và thứ tự của security chain |
| Một yêu cầu cụ thể trên functional route | `HandlerFilterFunction` | Chỉ tác động đến nhóm router functions được bọc |
| Lỗi một API outbound cụ thể | `onErrorResume` gần client/service | Có ngữ cảnh để phân biệt timeout, 404 và fallback |
| Chỉnh status/header sau khi body stream | Thiết kế lại điểm phát dữ liệu | Sau commit không thể thay status/header đã gửi |

`HandlerFilterFunction` là bộ lọc cho functional routing, khác với `WebFilter` áp dụng ở mức web application. Đừng sử dụng một `WebExceptionHandler` toàn cục cho mọi lỗi nghiệp vụ nếu một advice/handler cụ thể có thể diễn đạt hợp đồng rõ hơn.

## 12. Các rủi ro của WebFilter trong ứng dụng thực

### 12.1. Blocking trên event loop

Không gọi JDBC/JPA đồng bộ, `Thread.sleep`, `Future.get` hoặc `WebClient.block()` trực tiếp trong filter. Filter thường nằm trên đường nóng của mọi request; một lời gọi blocking sẽ làm tăng độ trễ và có thể nghẽn event-loop trên Reactor Netty.

Nếu bắt buộc dùng thư viện đồng bộ legacy, cần cô lập có kiểm soát:

~~~java
return Mono.fromCallable(() -> legacyVerifier.verify(exchange))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(allowed -> allowed
                ? chain.filter(exchange)
                : exchange.getResponse().setComplete());
~~~

Đây là fragment cần bean `legacyVerifier` và chính sách status phù hợp khi bị từ chối. `boundedElastic` chỉ chuyển nơi blocking diễn ra sang scheduler có giới hạn; nó không biến thư viện thành non-blocking và vẫn cần timeout, concurrency limit và kiểm soát thread/connection pool.

### 12.2. Đọc body hai lần

Request body trong WebFlux thường là stream `Flux<DataBuffer>` có đặc tính tiêu thụ một lần. Nếu filter subscribe và đọc hết body trước, controller downstream có thể không còn dữ liệu hoặc gặp lỗi. Việc cache/replay body cần xử lý `DataBuffer`, reference counting và release đúng cách; sai có thể gây memory leak hoặc tràn bộ nhớ.

Nếu yêu cầu chỉ là xác thực metadata, ưu tiên headers/path/query parameters. Khi buộc phải kiểm tra/chuyển đổi body, sử dụng decorator/cache phù hợp đã kiểm thử, giới hạn kích thước và tránh subscribe độc lập. Không giữ toàn bộ body vào field của singleton filter.

### 12.3. Context và tracing

Reactive chain có thể chuyển thread. `ThreadLocal` hoặc MDC truyền thống không tự theo một logical request qua mọi scheduler. Dùng `exchange.getAttributes()` cho dữ liệu request-scoped đơn giản và Reactor Context / cơ chế context propagation tương thích cho tracing hoặc security context theo đúng thư viện của ứng dụng.

Không ghi token, cookie, Authorization header hoặc nội dung nhạy cảm vào logs. Đối với tracing, log request ID, method, route, duration và status sau khi xử lý đủ để chẩn đoán nhiều sự cố.

### 12.4. Error handler ghi response hai lần

Nếu một filter đã gọi `response.writeWith(...)` hoặc `response.setComplete()`, rồi tiếp tục propagate lỗi, một error handler khác có thể cố ghi thêm body hoặc đổi status. Hãy đảm bảo mỗi request có một nguồn quyết định phản hồi, chỉ propagate khi không xử lý được và kiểm tra `isCommitted()`.

Không tạo `DataBuffer` rồi bỏ quên, đặc biệt với Netty pooled buffers. Khi dùng body Flux, việc phát hành và giải phóng buffer phải theo cơ chế framework hoặc API tương ứng.

### 12.5. Lỗi nằm ngoài reactive publisher

Nếu filter tự gọi `subscribe()` để khởi chạy một tác vụ phụ và không liên kết publisher đó vào `Mono<Void>` trả về, error của tác vụ phụ có thể không tới `WebExceptionHandler` của request. Tương tự, công việc nền được tách ra sau khi response đã hoàn tất không còn là phần của request-response pipeline; cần xử lý lỗi, retry, observability và lifecycle riêng.

## 13. Cách gỡ lỗi theo vị trí phát sinh

Khi thấy phản hồi bất thường, phân loại theo câu hỏi:

1. **Filter có chạy không?** Xác nhận runtime là WebFlux, bean đã được đăng ký, order và path condition. Có thể dùng WebTestClient để kiểm tra header do filter đặt.
2. **Handler có chạy không?** Kiểm tra filter có trả response sớm hoặc `Mono.error` mà không gọi `chain.filter`. Kiểm tra HandlerMapping và route.
3. **Code “sau chain.filter” chạy quá sớm?** Kiểm tra operator; câu lệnh Java chạy khi xây publisher không tương đương tín hiệu completion.
4. **Lỗi từ filter không vào @RestControllerAdvice?** Đó là sự khác biệt phạm vi; xem `WebExceptionHandler` hoặc handling ngay tại filter.
5. **WebExceptionHandler không được gọi?** Có thể lỗi đã được `onErrorResume` hoặc `@ExceptionHandler` xử lý trước; hoặc exception handler mặc định có order ưu tiên hơn.
6. **Lỗi handler không đổi status?** Response có thể đã commit. Xác định lần ghi/flush đầu của body hoặc SSE.
7. **Xuất hiện 200 nhưng body rỗng?** Kiểm tra publisher bị nuốt lỗi thành `Mono.empty()`, filter kết thúc sớm hoặc body converter.
8. **Client nhận 500 chung dù có handler riêng?** Kiểm tra loại exception, order, handler có trả `Mono.error` lại và có cấu hình Boot error response mặc định.
9. **Lỗi chỉ xảy ra khi tải cao?** Kiểm tra blocking code, connection pool, scheduler queue, cancellation và handler có subscribe thủ công.
10. **Body bị mất sau filter?** Kiểm tra việc tiêu thụ request body một lần và cơ chế caching/decorating.

Sử dụng logs theo correlation ID, trace spans, metrics và các kịch bản WebTestClient nhỏ để xác minh giả thuyết; không suy luận chỉ từ thứ tự log ở các thread khác nhau.

## 14. Các lỗi thiết kế thường gặp

1. **Nhầm WebFilter với Servlet Filter:** API, cấu hình và runtime khác nhau.
2. **Cho rằng viết code sau `chain.filter(exchange)` nghĩa là chạy sau handler:** không đúng với publisher lazy.
3. **Đặt header bắt buộc trong `doFinally`:** có thể quá muộn vì response đã commit.
4. **Dùng cùng `@Order` và tin vào thứ tự ngẫu nhiên:** không ổn định khi thay đổi bean/runtime.
5. **Nuốt mọi lỗi trong `onErrorResume(Throwable.class, ...)`:** che giấu sự cố và phá hợp đồng HTTP.
6. **Dùng WebExceptionHandler để xử lý mọi lỗi controller:** làm mất ngữ cảnh và bỏ qua advice nghiệp vụ.
7. **Gọi `subscribe()` trong filter:** tách work khỏi request pipeline, mất error/cancellation propagation.
8. **Chặn event loop bằng JDBC hoặc `block()`:** hại throughput của các request khác.
9. **Đọc body rồi không phát lại cho handler:** khiến downstream nhận body rỗng hoặc báo lỗi.
10. **Đổi status sau streaming bắt đầu:** không thể đảo ngược status/header đã commit.
11. **Đưa state mutable của request vào singleton filter:** có nguy cơ lẫn dữ liệu giữa các requests.
12. **Tự xử lý 401/403 không tuân theo Spring Security:** có thể thiếu challenge hoặc sai quy tắc phân quyền.
13. **Quên khác biệt giữa errors pre-handler và controller errors:** chọn sai tầng xử lý, test không phản ánh luồng thực.
14. **Không xử lý tín hiệu CANCEL:** resource cleanup và metrics có thể sai khi client ngắt kết nối.

## 15. Checklist trước khi triển khai

- [ ] Đã xác định ứng dụng chạy WebFlux reactive runtime và có đúng bean `WebFilter`.
- [ ] Các filter quan trọng có order rõ và được kiểm thử theo thứ tự.
- [ ] Logic trước handler đặt trước `chain.filter` hoặc trong đoạn defer phù hợp.
- [ ] Hậu xử lý dựa trên tín hiệu publisher như `then`, `doOnError`, `doFinally`; không dựa vào thứ tự câu lệnh Java.
- [ ] Không gọi `subscribe()` hoặc `block()` thủ công trong filter.
- [ ] Không tiêu thụ request body mà thiếu cache/replay/release được kiểm thử.
- [ ] Lỗi controller xử lý bằng `@ExceptionHandler`/`@RestControllerAdvice` khi có ngữ cảnh phù hợp.
- [ ] Lỗi pre-handler chưa xử lý được có `WebExceptionHandler` phù hợp và order trước handler lỗi mặc định nếu cần.
- [ ] Error handler chỉ xử lý loại lỗi được chỉ định, propagate lỗi khác.
- [ ] Không cố sửa status/headers sau khi response commit; đã kiểm tra `isCommitted()` và thiết kế callback `beforeCommit` khi cần.
- [ ] Spring Security giữ trách nhiệm về authentication/authorization và 401/403.
- [ ] Kiểm thử `/ok`, `/blocked`, lỗi controller, streaming lỗi, cancel và request concurrency.
- [ ] Logging/tracing có correlation ID, không tiết lộ token và không blocking event loop.

## 16. Ghi nhớ

**WebFilter bao quanh handler và chuyển xử lý qua `WebFilterChain`; WebExceptionHandler tiếp nhận lỗi chưa được xử lý ở tầng WebFlux.** Muốn làm việc *trước* handler, thiết lập dữ liệu khi filter nhận request. Muốn làm việc *sau* handler, phải dùng tín hiệu reactive từ publisher mà chain trả về. Controller advice xử lý lỗi trong phạm vi controller, còn lỗi từ filter hoặc routing có thể cần WebExceptionHandler. Mọi nhánh phải tôn trọng thời điểm commit của HTTP response, tránh blocking và giữ lỗi/cancellation nằm trong cùng reactive chain.

## Tài liệu tham khảo

- Spring Framework, WebFlux Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework, WebFlux Exceptions: https://docs.spring.io/spring-framework/reference/web/webflux/ann-controller/ann-exceptions.html
- Spring Framework, WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework API, WebExceptionHandler: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework API, ServerHttpResponse: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Boot, Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
