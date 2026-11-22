# WebExceptionHandler cho lỗi ngoài controller trong Spring WebFlux

## 1. Vì sao cần một tầng xử lý lỗi ngoài controller?

Spring WebFlux có nhiều tầng tham gia xử lý một HTTP request: server adapter, chuỗi \`WebFilter\`, \`WebHandler\` (thường là \`DispatcherHandler\`), handler mapping, controller hoặc functional endpoint, rồi đến việc ghi response. Exception có thể phát sinh ở bất kỳ tầng nào.

Ví dụ:

- Một \`WebFilter\` kiểm tra token và gặp lỗi khi gọi dịch vụ xác thực.
- Một filter ghi log hoặc đọc metadata bị lỗi trước khi request được chuyển vào controller.
- Một thành phần hạ tầng lấy tenant, session hoặc thông tin định tuyến gặp exception.
- Một handler mapping hoặc functional endpoint phát sinh lỗi.
- Một controller trả về \`Mono\` mà publisher phát \`onError\` sau khi method đã trả về.
- Một thao tác ghi response gặp lỗi trong quá trình encode hoặc gửi dữ liệu.

\`@ExceptionHandler\` và \`@ControllerAdvice\` rất hữu ích cho exception trong mô hình annotated controller. Tuy nhiên, chúng hoạt động qua cơ chế xử lý handler của controller. Một exception phát sinh trong \`WebFilter\` trước khi request tới controller không thuộc phạm vi xử lý của controller advice đó.

**\`WebExceptionHandler\` là abstraction ở tầng WebHandler API**, nằm bên ngoài chuỗi filter và WebHandler đích. Nó cung cấp một nơi tập trung để xử lý exception lan ra từ những thành phần này, kể cả lỗi không xuất phát từ controller.

Mục tiêu thường là ánh xạ exception đã biết thành HTTP status và response body an toàn, ghi log có correlation, đồng thời để những exception không thuộc phạm vi tiếp tục đi tới handler kế tiếp.

## 2. Vị trí của WebExceptionHandler trong request lifecycle

Spring Framework xây dựng chuỗi xử lý cấp thấp bằng \`WebHttpHandlerBuilder\`. Builder có thể tự phát hiện các bean trong \`ApplicationContext\`, bao gồm nhiều \`WebExceptionHandler\`, nhiều \`WebFilter\` và một \`WebHandler\` đích.

Mô hình khái quát:

~~~text
HTTP server adapter
        |
        v
WebExceptionHandler chain
        |
        v
WebFilter chain
        |
        v
Target WebHandler
        |
        +-- DispatcherHandler
        |      |
        |      +-- annotated controller
        |      +-- functional endpoint
        |
        v
HTTP response
~~~

Exception phát sinh trong filter hoặc target WebHandler được lan ra ngoài. Chuỗi \`WebExceptionHandler\` nhận exception và thử xử lý theo thứ tự.

Một handler có thể:

- Xử lý thành công: đặt status/header, ghi response rồi hoàn tất publisher.
- Không nhận trách nhiệm xử lý exception: trả một publisher phát lỗi để handler tiếp theo thử xử lý.
- Không thể ghi response vì response đã commit: không được ghi một response thứ hai; cần log và để lỗi tiếp tục được quan sát ở tầng runtime.

Đây là tầng bao quanh xử lý request. Nó không thay thế controller, filter, service hay security; nó chỉ quyết định cách xử lý exception đã thoát khỏi các tầng đó.

## 3. Hợp đồng quan trọng của WebExceptionHandler

Interface của Spring Framework:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

Phương thức nhận:

- \`ServerWebExchange\`: request/response hiện tại cùng attributes, session, principal và các thông tin liên quan.
- \`Throwable\`: exception đang được lan truyền.

Giá trị trả về \`Mono<Void>\` thể hiện **kết quả xử lý exception**, không phải một body dữ liệu:

| Giá trị trả về | Ý nghĩa với exception chain |
| --- | --- |
| \`Mono.empty()\` hoặc publisher hoàn tất bình thường sau khi response đã được xử lý | Handler đã nhận trách nhiệm; exception được xem là đã xử lý |
| \`Mono.error(ex)\` | Handler này không xử lý exception; exception tiếp tục tới handler kế tiếp |
| Publisher phát lỗi khác | Việc xử lý của handler thất bại; lỗi mới tiếp tục được lan truyền |

Đây là điểm dễ viết sai nhất. Nếu exception không thuộc phạm vi của handler, **đừng trả \`Mono.empty()\`** chỉ để bỏ qua nó. Làm vậy khiến framework tưởng exception đã được xử lý dù chưa có response thích hợp.

Ví dụ đúng về nguyên tắc:

~~~java
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    if (ex instanceof KnownApplicationException) {
        // Tạo response cho exception này.
        return writeErrorResponse(exchange);
    }

    // Không thuộc phạm vi: để handler kế tiếp xử lý.
    return Mono.error(ex);
}
~~~

\`writeErrorResponse\` ở đây là method minh họa. Trong code thật, nó phải hoàn tất sau khi status/header/body đã được ghi thành công.

## 4. WebExceptionHandler khác @ExceptionHandler và @ControllerAdvice

Ba cơ chế có phạm vi và mức trừu tượng khác nhau:

| Cơ chế | Vị trí | Trường hợp phù hợp |
| --- | --- | --- |
| \`@ExceptionHandler\` trong controller | Bên trong cơ chế xử lý annotated controller | Lỗi riêng của controller hoặc nhóm endpoint |
| \`@RestControllerAdvice\` | Áp dụng toàn cục cho annotated controllers | Chuẩn hóa lỗi validation, domain và HTTP của controller |
| \`WebExceptionHandler\` | Bên ngoài WebFilter chain và target WebHandler | Lỗi filter, lỗi tầng WebHandler hoặc exception chưa được tầng trong xử lý |

Ví dụ controller advice:

~~~java
@RestControllerAdvice
public class ApiControllerAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> handleBadInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(
            new ApiError("BAD_INPUT", "The request is invalid.")
        );
    }

    public record ApiError(String code, String message) {}
}
~~~

Cơ chế này phù hợp với exception phát sinh trong annotated controller. Nhưng nếu \`AuthenticationWebFilter\` hoặc một \`WebFilter\` tùy biến phát lỗi trước khi \`DispatcherHandler\` gọi controller, controller advice không phải tầng xử lý thích hợp.

Ví dụ filter:

~~~java
@Component
public class TokenFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        if (tokenIsInvalid(exchange)) {
            return Mono.error(new InvalidTokenException());
        }

        return chain.filter(exchange);
    }
}
~~~

\`InvalidTokenException\` phát sinh ở filter. Một \`WebExceptionHandler\` có thể ánh xạ lỗi này thành 401 hoặc 403 theo hợp đồng bảo mật. Với xác thực thực tế, nên ưu tiên cơ chế entry point/access-denied handler của Spring Security; không tự viết bộ xác thực token bằng một filter demo.

**Không phải mọi exception trong controller đều đi thẳng tới WebExceptionHandler.** WebFlux có cơ chế xử lý exception bên trong HandlerAdapter và controller advice. Chỉ exception chưa được xử lý ở tầng trong mới tiếp tục lan tới tầng ngoài.

## 5. Khi nào exception được chuyển tới WebExceptionHandler?

Có thể phân loại theo nơi phát sinh:

| Nơi phát sinh | Cơ chế thường xử lý trước | Vai trò của WebExceptionHandler |
| --- | --- | --- |
| \`WebFilter\` trước khi gọi chain | Không có controller handler ở thời điểm đó | Tầng chính để xử lý exception thoát khỏi filter |
| \`WebFilter\` sau khi gọi chain và publisher downstream lỗi | Filter có thể tự xử lý bằng operator nếu thiết kế như vậy | Nhận lỗi nếu filter không xử lý và lỗi lan ra ngoài |
| Handler mapping hoặc dispatch | Cơ chế dispatch/exception handling nội bộ nếu có | Xử lý exception còn lan ra khỏi WebHandler |
| Annotated controller | \`@ExceptionHandler\`, \`@ControllerAdvice\`, HandlerAdapter | Fallback cho lỗi chưa được xử lý |
| Functional endpoint | Handler/router có thể xử lý lỗi trong pipeline | Nhận exception còn lan ra khỏi target WebHandler |
| Ghi response sau khi headers/body đã commit | Không thể tạo response HTTP mới | Không thể đổi status/body; chỉ log/quan sát và kết thúc stream theo khả năng runtime |

Lỗi phát sinh trong một reactive publisher có thể xuất hiện **sau khi method đã trả về**. Ví dụ:

~~~java
@GetMapping("/data")
public Mono<Data> data() {
    return service.fetch()
        .map(this::transform);
}
~~~

Nếu \`service.fetch()\` phát \`onError\` khi subscription chạy, lỗi vẫn thuộc pipeline xử lý request. Nếu không được operator hoặc handler nội bộ xử lý, nó có thể lan tới WebExceptionHandler.

Ngược lại, exception trong một thread nền đã tách khỏi request lifecycle bằng một \`subscribe()\` độc lập không tự động quay lại exception chain của request ban đầu. Đây là một lý do không nên tự subscribe trong controller hoặc filter.

## 6. Thứ tự xử lý và cách nhường lỗi cho handler kế tiếp

WebFlux cho phép đăng ký nhiều bean \`WebExceptionHandler\`. Thứ tự có thể điều khiển bằng \`@Order\` hoặc interface \`Ordered\`.

Một handler nên xử lý **phạm vi exception cụ thể**:

~~~java
if (ex instanceof InvalidTokenException) {
    return writeUnauthorized(exchange);
}
return Mono.error(ex);
~~~

Không nên bắt mọi \`Throwable\` rồi luôn trả 500, bởi điều đó có thể:

- Che mất status đã được xác định bởi \`ResponseStatusException\`.
- Làm mất xử lý mặc định của Spring hoặc Spring Boot.
- Biến lỗi hủy, lỗi ghi response hoặc lỗi hạ tầng thành một response chung không phù hợp.
- Khiến lỗi lập trình khó phát hiện.

### Handler chain hoạt động thế nào?

Giả sử có ba handler theo thứ tự:

~~~text
CustomApiExceptionHandler
          |
          | không nhận exception -> Mono.error(ex)
          v
BootErrorWebExceptionHandler
          |
          | không xử lý được -> Mono.error(ex)
          v
Framework response-status handler
~~~

Đây là mô hình minh họa về việc exception được thử lần lượt; thứ tự cụ thể còn phụ thuộc bean và cấu hình của ứng dụng. Mỗi handler cần tuân thủ hợp đồng complete/error để chuỗi biết exception đã được xử lý hay chưa.

Không dùng \`onErrorResume(ex -> Mono.empty())\` như một cách “bỏ qua lỗi” trong handler. Nó có thể nuốt exception mà không thiết lập response status/body.

## 7. Các handler có sẵn của Spring Framework

Spring WebFlux có những implementation tích hợp:

### ResponseStatusExceptionHandler

\`ResponseStatusExceptionHandler\` xử lý exception kiểu \`ResponseStatusException\` bằng cách đặt HTTP status tương ứng trên response. Nó phù hợp khi ứng dụng chỉ cần ánh xạ exception sang status code.

Ví dụ:

~~~java
return Mono.error(
    new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Resource not found"
    )
);
~~~

Handler tương ứng có thể đặt status 404. Việc có body lỗi hay không phụ thuộc tầng error rendering khác.

### WebFluxResponseStatusExceptionHandler

\`WebFluxResponseStatusExceptionHandler\` mở rộng cơ chế trên và có thể xác định status từ annotation \`@ResponseStatus\` trên exception class. Spring WebFlux Config đăng ký implementation này.

Ví dụ:

~~~java
@ResponseStatus(HttpStatus.CONFLICT)
public class DuplicateOrderException extends RuntimeException {
}
~~~

Khi exception này thoát ra và được status handler xử lý, response có status 409.

Hai handler trên không giống một bộ renderer JSON đầy đủ. Nếu cần response body thống nhất, có thể dùng controller advice, Boot error handler hoặc custom WebExceptionHandler tùy phạm vi.

## 8. Xử lý response: status, header và body

Một custom \`WebExceptionHandler\` làm việc trực tiếp với \`ServerWebExchange\` và \`ServerHttpResponse\`. Một response JSON cơ bản cần:

1. Kiểm tra response chưa commit.
2. Chọn status theo loại exception.
3. Đặt \`Content-Type\`.
4. Serialize error payload.
5. Ghi \`DataBuffer\` vào response và trả publisher từ \`writeWith\`.

Ví dụ khung:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

byte[] json = objectMapper.writeValueAsBytes(errorBody);

return response.writeWith(
    Mono.just(response.bufferFactory().wrap(json))
);
~~~

Đây là đoạn minh họa cần \`ObjectMapper\`, \`Mono\`, \`ServerHttpResponse\` và error DTO. Không cần gọi \`subscribe()\`: publisher của \`writeWith\` được framework compose vào response lifecycle.

Nếu response không có body, có thể đặt status/header rồi trả \`response.setComplete()\`. Không ghi JSON \`null\` khi hợp đồng muốn response rỗng.

### Dùng Problem Details

Spring Framework hỗ trợ RFC 9457 Problem Details qua \`ProblemDetail\` và \`ErrorResponse\`. Ví dụ payload:

~~~json
{
  "type": "https://example.org/problems/upstream-unavailable",
  "title": "Upstream unavailable",
  "status": 503,
  "detail": "A required upstream service is temporarily unavailable."
}
~~~

Với annotated controller, có thể trả \`ProblemDetail\` từ \`@ExceptionHandler\` hoặc dùng \`ResponseEntityExceptionHandler\`. Ở tầng thấp hơn, custom handler có thể tự tạo body theo cùng schema và đặt \`Content-Type: application/problem+json\`.

Không đưa stack trace, SQL, hostname nội bộ, token hoặc thông tin nhạy cảm vào response công khai. Error detail cho client nên ổn định, có thể hành động và không tiết lộ cấu trúc nội bộ.

## 9. Response đã commit: giới hạn không thể đảo ngược

Một HTTP response có thể được commit khi status/header đã được gửi hoặc body bắt đầu được ghi. Sau thời điểm đó, server không thể gửi một response HTTP thứ hai để đổi 200 thành 500 hay thay body đã gửi.

Custom handler nên kiểm tra:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}
~~~

Nếu response đã commit:

- Không cố đặt status mới.
- Không cố ghi thêm JSON error document vào body hiện tại.
- Không gọi \`setComplete()\` với kỳ vọng nó sẽ thay thế body đã gửi.
- Ghi log/metric với request correlation ID.
- Để lỗi được lan truyền hoặc stream kết thúc theo khả năng server.

Đặc biệt với SSE, NDJSON, file download hoặc response stream dài, lỗi xảy ra sau khi một phần body đã tới client không thể đổi HTTP status ban đầu. Nếu protocol cho phép, ứng dụng có thể gửi một **event lỗi ở cấp ứng dụng** trước khi stream kết thúc; đây là thiết kế riêng của stream, không phải một HTTP response mới.

## 10. Spring Boot: ErrorWebExceptionHandler và DefaultErrorWebExceptionHandler

Spring Boot bổ sung abstraction và cấu hình error rendering trên WebFlux:

- \`ErrorWebExceptionHandler\` là marker interface của Boot, mở rộng Framework \`WebExceptionHandler\`, dùng cho thành phần render error response.
- \`AbstractErrorWebExceptionHandler\` là base class tiện lợi để xây dựng error handler theo phong cách functional endpoint.
- \`DefaultErrorWebExceptionHandler\` là implementation mặc định của Boot.
- \`ErrorWebFluxAutoConfiguration\` tạo \`ErrorAttributes\` và error handler mặc định khi ứng dụng reactive phù hợp và chưa có bean thay thế.

Boot mặc định đặt error handler của mình ở order \`-1\`. Handler tùy biến có thể chạy trước nó bằng order ưu tiên cao hơn (số nhỏ hơn), xử lý một số lỗi cụ thể, rồi trả \`Mono.error(ex)\` cho lỗi khác để Boot tiếp tục xử lý.

### Chỉ thêm WebExceptionHandler hay thay thế error renderer của Boot?

Đây là hai ý định khác nhau:

| Cách triển khai | Hệ quả |
| --- | --- |
| Bean chỉ implement Framework \`WebExceptionHandler\` | Có thể xử lý một số exception ở tầng ngoài; Boot vẫn có thể đăng ký error renderer mặc định |
| Bean implement Boot \`ErrorWebExceptionHandler\` | Được đánh dấu là error renderer; auto-configuration mặc định có thể lùi theo điều kiện thiếu bean |
| Kế thừa \`AbstractErrorWebExceptionHandler\` | Có helper để định tuyến error bằng \`RouterFunction\` và tạo JSON/HTML response |
| Tùy biến \`ErrorAttributes\` | Thay đổi dữ liệu error được dùng bởi Boot renderer hiện có mà không nhất thiết viết lại toàn bộ handler |

Nếu chỉ cần bắt một lỗi hạ tầng cụ thể từ filter, thường chỉ cần thêm một bean Framework \`WebExceptionHandler\` có phạm vi hẹp. Không cần thay toàn bộ Boot error renderer.

Nếu thay thế Boot renderer bằng \`ErrorWebExceptionHandler\`, ứng dụng phải chịu trách nhiệm đầy đủ hơn về status mapping, content negotiation, body, logging, view và fallback.

### Problem Details trong Spring Boot

Có thể bật hỗ trợ Problem Details của WebFlux bằng property:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Với exception chuẩn được hỗ trợ, Spring có thể render response theo \`application/problem+json\`. Trước khi viết custom Boot error handler, hãy xem có thể dùng \`ProblemDetail\`, \`ErrorResponse\`, \`ResponseEntityExceptionHandler\` hoặc tùy biến \`ErrorAttributes\` để đạt mục tiêu hay không.

## 11. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này minh họa đúng ranh giới ngoài controller:

- Một \`WebFilter\` phát \`EdgeFailureException\` trước khi request tới controller.
- Một custom \`WebExceptionHandler\` ở order \`-2\` ánh xạ exception đó thành HTTP 503 JSON.
- Exception khác được chuyển tiếp bằng \`Mono.error(ex)\`.
- Controller có \`@ExceptionHandler\` riêng để xử lý lỗi phát sinh trong controller, trả HTTP 400.

Cấu trúc:

~~~text
web-exception-handler-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/errorhandling/
    │   ├── ErrorHandlingApplication.java
    │   ├── EdgeFailureException.java
    │   ├── EdgeFailureFilter.java
    │   ├── ApiWebExceptionHandler.java
    │   └── DemoController.java
    └── test/java/com/example/errorhandling/
        └── ErrorHandlingTest.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>web-exception-handler-demo</artifactId>
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

File \`src/main/java/com/example/errorhandling/ErrorHandlingApplication.java\`:

~~~java
package com.example.errorhandling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/errorhandling/EdgeFailureException.java\`:

~~~java
package com.example.errorhandling;

public final class EdgeFailureException extends RuntimeException {
    public EdgeFailureException() {
        super("A required upstream dependency is unavailable");
    }
}
~~~

File \`src/main/java/com/example/errorhandling/EdgeFailureFilter.java\`:

~~~java
package com.example.errorhandling;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class EdgeFailureFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();

        if ("/api/edge-failure".equals(path)) {
            return Mono.error(new EdgeFailureException());
        }

        return chain.filter(exchange);
    }
}
~~~

File \`src/main/java/com/example/errorhandling/ApiWebExceptionHandler.java\`:

~~~java
package com.example.errorhandling;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    private static final Logger log =
        LoggerFactory.getLogger(ApiWebExceptionHandler.class);

    private final ObjectMapper objectMapper;

    public ApiWebExceptionHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (!(ex instanceof EdgeFailureException)) {
            return Mono.error(ex);
        }

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            log.error("Cannot render edge error because response is committed: {}",
                exchange.getLogPrefix(), ex);
            return Mono.error(ex);
        }

        ApiError body = new ApiError(
            "UPSTREAM_UNAVAILABLE",
            "A required upstream service is temporarily unavailable."
        );

        final byte[] json;
        try {
            json = objectMapper.writeValueAsBytes(body);
        } catch (JsonProcessingException serializationError) {
            return Mono.error(serializationError);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        log.warn("Mapped edge failure for {}", exchange.getLogPrefix(), ex);

        return response.writeWith(
            Mono.just(response.bufferFactory().wrap(json))
        );
    }

    public record ApiError(String code, String message) {}
}
~~~

File \`src/main/java/com/example/errorhandling/DemoController.java\`:

~~~java
package com.example.errorhandling;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    public record ControllerError(String code, String message) {}

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/controller-failure")
    public Mono<String> controllerFailure() {
        return Mono.error(new IllegalArgumentException("invalid input"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ControllerError> handleBadInput(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest().body(
            new ControllerError(
                "BAD_INPUT",
                "The controller request is invalid."
            )
        );
    }
}
~~~

Chạy từ thư mục \`web-exception-handler-demo\` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Thử lỗi phát sinh ngoài controller

~~~bash
curl -i http://localhost:8080/api/edge-failure
~~~

Response dự kiến:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
~~~

Body JSON:

~~~json
{
  "code": "UPSTREAM_UNAVAILABLE",
  "message": "A required upstream service is temporarily unavailable."
}
~~~

Request bị filter chặn trước khi tới controller. \`ApiWebExceptionHandler\` nhận \`EdgeFailureException\`, đặt status 503 và ghi JSON response.

### Thử lỗi được xử lý trong controller

~~~bash
curl -i http://localhost:8080/api/controller-failure
~~~

Response dự kiến:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

Body JSON:

~~~json
{
  "code": "BAD_INPUT",
  "message": "The controller request is invalid."
}
~~~

Lỗi này được \`@ExceptionHandler\` trong controller xử lý. Nó minh họa phạm vi khác nhau giữa controller-level exception handling và WebExceptionHandler.

### Thử endpoint bình thường

~~~bash
curl -i http://localhost:8080/api/ok
~~~

Body JSON:

~~~json
{"status":"ok"}
~~~

### Vì sao ví dụ vẫn giữ Boot default error handler?

Custom class chỉ implement Framework \`WebExceptionHandler\`, không implement marker \`ErrorWebExceptionHandler\` của Boot. Vì vậy Boot vẫn có thể tạo default error renderer. Custom handler có order \`-2\`, chạy trước Boot default handler order \`-1\`; nó chỉ xử lý \`EdgeFailureException\`, còn exception khác được chuyển tiếp.

## 12. Kiểm thử bằng WebTestClient

Có thể kiểm tra cả hai đường lỗi bằng test tích hợp. File \`src/test/java/com/example/errorhandling/ErrorHandlingTest.java\`:

~~~java
package com.example.errorhandling;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ErrorHandlingTest {

    @Autowired
    WebTestClient client;

    @Test
    void filterFailureIsHandledByWebExceptionHandler() {
        client.get()
            .uri("/api/edge-failure")
            .exchange()
            .expectStatus().isEqualTo(503)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("UPSTREAM_UNAVAILABLE");
    }

    @Test
    void controllerFailureIsHandledByExceptionHandler() {
        client.get()
            .uri("/api/controller-failure")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("BAD_INPUT");
    }

    @Test
    void normalRequestStillWorks() {
        client.get()
            .uri("/api/ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Các test xác nhận:

1. Exception do filter phát ra được custom WebExceptionHandler ánh xạ thành 503.
2. Exception từ controller được local \`@ExceptionHandler\` ánh xạ thành 400.
3. Request bình thường vẫn hoạt động.

Đây là test tích hợp phụ thuộc Spring Boot test và server reactive nhúng. Nếu test handler riêng lẻ, có thể dùng \`MockServerWebExchange\` và kiểm tra \`Mono<Void>\`/response; nhưng test tích hợp hữu ích hơn để xác nhận thứ tự thực tế giữa filter, controller, custom handler và Boot default handler.

## 13. Tùy biến Boot error rendering sâu hơn

Nếu yêu cầu là chuẩn hóa **mọi lỗi chưa xử lý** thành một schema riêng, có thể cân nhắc Boot \`AbstractErrorWebExceptionHandler\`. Base class này cung cấp cơ chế functional routing cho error response và truy cập \`ErrorAttributes\`, message readers/writers cùng view resolvers.

Một triển khai theo hướng này thường:

1. Kế thừa \`AbstractErrorWebExceptionHandler\`.
2. Inject \`ErrorAttributes\`, resource properties và \`ApplicationContext\`.
3. Cấu hình message readers/writers từ \`ServerCodecConfigurer\`.
4. Override \`getRoutingFunction(...)\` để chọn JSON/HTML error route.
5. Trả \`ServerResponse\` với status và body phù hợp.

Boot cũng có \`DefaultErrorWebExceptionHandler\`, có thể subclass để override một số hành vi cụ thể. Các class và constructor có thể thay đổi giữa major version Boot; luôn dùng API đúng version dự án.

Khi chỉ cần sửa nội dung lỗi mặc định, xem xét bean \`ErrorAttributes\` trước. Khi muốn RFC 9457, xem xét \`ProblemDetail\` và property \`spring.webflux.problemdetails.enabled\`. Chỉ thay error renderer khi cần kiểm soát thực sự toàn bộ response.

## 14. Logging, correlation và bảo mật

Error handler là nơi thích hợp để ghi nhận lỗi chưa được xử lý ở tầng trong. Tuy nhiên, log phải đủ thông tin cho vận hành mà không biến thành nơi lưu bí mật.

Nên:

- Ghi loại exception, request path, status và correlation/request ID.
- Dùng \`exchange.getLogPrefix()\` để gắn log với request trong WebFlux.
- Ghi stack trace ở server log theo severity phù hợp.
- Trả error code ổn định cho client.
- Không trả trực tiếp \`ex.getMessage()\` nếu thông tin có thể chứa SQL, hostname, token hoặc dữ liệu cá nhân.
- Không log authorization header, cookie, session ID hay request body nhạy cảm.
- Dùng metrics để phân biệt lỗi đã được map với lỗi chưa xử lý.

Không phải mọi exception đều là 500. Hãy ánh xạ theo nguyên nhân và hợp đồng:

| Nhóm lỗi | Status thường gặp |
| --- | --- |
| Request không hợp lệ | 400 |
| Chưa xác thực | 401 |
| Đã xác thực nhưng không đủ quyền | 403 |
| Không tìm thấy resource | 404 |
| Conflict nghiệp vụ | 409 |
| Payload quá lớn | 413 |
| Media type không hỗ trợ | 415 |
| Lỗi phụ thuộc upstream tạm thời | 502 hoặc 503 theo ngữ cảnh |
| Lỗi không dự kiến phía server | 500 |

Không dùng 401/403 thay thế nhau và không biến mọi exception thành 500. Nếu dùng Spring Security, hãy để authentication entry point và access-denied handler xử lý các lỗi bảo mật đúng tầng.

## 15. Những lỗi thường gặp

1. **Dùng \`@ControllerAdvice\` để bắt lỗi từ WebFilter:** filter nằm ngoài controller dispatch. Dùng WebExceptionHandler hoặc cơ chế Security tương ứng.
2. **Trả \`Mono.empty()\` cho exception chưa xử lý:** framework hiểu là đã handled dù response có thể chưa được tạo. Trả \`Mono.error(ex)\` để chuyển tiếp.
3. **Bắt mọi Throwable rồi trả 500:** che giấu lỗi đã có status, lỗi hủy và lỗi lập trình. Chỉ map các exception thuộc phạm vi.
4. **Không khai báo order:** handler tùy biến có thể chạy sau Boot default hoặc không theo thứ tự mong muốn. Xác định rõ thứ tự với \`@Order\`/Ordered.
5. **Đặt custom handler trước Boot nhưng không nhường lỗi:** Boot default không còn cơ hội xử lý exception khác. Với lỗi không nhận diện, trả \`Mono.error(ex)\`.
6. **Nhầm WebExceptionHandler với ErrorWebExceptionHandler:** interface thứ hai là marker của Boot. Đăng ký nó có thể làm Boot default renderer lùi theo điều kiện.
7. **Tưởng WebExceptionHandler chỉ xử lý controller:** nó bao quanh WebFilter chain và target WebHandler; lỗi filter cũng thuộc phạm vi.
8. **Cố đổi status sau response commit:** HTTP headers/body đã gửi không thể thu hồi. Kiểm tra \`response.isCommitted()\`.
9. **Ghi body hai lần:** có thể làm response lỗi hoặc connection bị đóng. Một handler chỉ nên ghi một response.
10. **Gọi \`block()\` hoặc \`subscribe()\` trong handler:** chặn event loop hoặc tách response write khỏi lifecycle. Trả publisher từ \`writeWith\`.
11. **Trả exception message nguyên văn:** có thể lộ thông tin nội bộ. Dùng error code/message an toàn và log chi tiết phía server.
12. **Không xử lý lỗi serialize error body:** chính error renderer có thể thất bại. Có fallback tối thiểu hoặc propagate lỗi serialize.
13. **Cho rằng lỗi sau commit có thể thành JSON 500:** với stream đã bắt đầu, không thể thay HTTP status; thiết kế in-band error nếu protocol hỗ trợ.
14. **Dùng handler chung thay Spring Security:** lỗi xác thực/ủy quyền cần entry point/access-denied handler đúng ngữ cảnh.
15. **Không test exception từ filter:** test controller advice không chứng minh filter errors được xử lý.
16. **Không kiểm tra cancellation:** client disconnect thường là cancel, không nhất thiết là exception mà WebExceptionHandler xử lý.
17. **Tạo custom ErrorWebExceptionHandler quá sớm:** có thể vô tình thay thế toàn bộ Boot error rendering. Trước tiên xem ErrorAttributes/ProblemDetail hoặc thêm một Framework handler có phạm vi hẹp.
18. **Không phân biệt lỗi được xử lý và lỗi được log:** ghi log không tự xử lý exception; handler phải hoàn tất response hoặc nhường lỗi.

## 16. Checklist thiết kế WebExceptionHandler

Trước khi đưa handler vào production, kiểm tra:

- Exception nào thuộc trách nhiệm của handler?
- Exception nào phải được chuyển tiếp?
- Handler chạy trước hay sau Boot default?
- Handler có xử lý đúng \`Mono<Void>\` contract không?
- Response đã commit chưa?
- Status và content type có khớp error contract không?
- Error body có tránh lộ thông tin nội bộ không?
- Có correlation ID và log server-side không?
- Có phân biệt lỗi controller, filter, security và functional endpoint không?
- Có xử lý lỗi serialize/write response không?
- Có giữ nguyên behavior của Boot default cho exception khác không?
- Có test WebFilter error, controller error, unknown error và committed response không?
- Có tránh \`block()\`, \`subscribe()\` và ghi response nhiều lần không?

## 17. Câu hỏi tự kiểm tra

**1.** \`WebExceptionHandler\` thuộc tầng nào? WebHandler API, bao quanh chuỗi WebFilter và target WebHandler.

**2.** Phương thức \`handle\` nhận gì? \`ServerWebExchange\` và \`Throwable\`, trả \`Mono<Void>\`.

**3.** \`Mono<Void>\` complete có nghĩa gì? Exception đã được handler xử lý.

**4.** \`Mono.error(ex)\` có ý nghĩa gì? Handler hiện tại không xử lý; exception được chuyển tới handler kế tiếp.

**5.** Vì sao \`@ControllerAdvice\` không bắt exception do WebFilter ném trước controller? Vì controller advice hoạt động qua HandlerAdapter/annotated controller, còn filter nằm bên ngoài dispatch.

**6.** WebExceptionHandler có thể bắt lỗi từ functional endpoint không? Có, nếu lỗi thoát khỏi handler/router và lan ra target WebHandler.

**7.** \`@Order\` dùng để làm gì? Quy định thứ tự các WebExceptionHandler/WebFilter trong chain tương ứng.

**8.** \`ResponseStatusExceptionHandler\` làm gì? Ánh xạ \`ResponseStatusException\` sang HTTP status; WebFlux có extension hỗ trợ \`@ResponseStatus\`.

**9.** \`ErrorWebExceptionHandler\` thuộc Framework hay Boot? Đây là marker interface của Spring Boot, mở rộng Framework WebExceptionHandler.

**10.** Vì sao custom handler nên trả \`Mono.error(ex)\` cho lỗi không biết? Để handler kế tiếp, chẳng hạn Boot default, tiếp tục xử lý.

**11.** Có thể đổi status sau khi response commit không? Không. Headers/body đã gửi không thể thay thế bằng một response mới.

**12.** Vì sao không trả \`ex.getMessage()\` cho client? Message có thể tiết lộ SQL, hostname, token hoặc chi tiết nội bộ.

**13.** Khi nào nên dùng AbstractErrorWebExceptionHandler? Khi cần tùy biến Boot error rendering bằng functional RouterFunction và ErrorAttributes.

**14.** Nếu chỉ muốn xử lý một exception từ filter trong Boot thì có cần thay DefaultErrorWebExceptionHandler không? Thường không; thêm Framework WebExceptionHandler có phạm vi hẹp và để Boot xử lý lỗi còn lại.

**Ghi nhớ:** \`WebExceptionHandler\` là tầng xử lý exception bên ngoài WebFilter chain và target WebHandler. \`Mono<Void>\` complete nghĩa là đã xử lý; \`Mono.error(ex)\` nghĩa là nhường lỗi cho handler kế tiếp. \`@ControllerAdvice\` dành cho lỗi trong annotated controller; WebExceptionHandler phù hợp với lỗi filter và lỗi hạ tầng ngoài controller. Trong Boot, hiểu rõ thứ tự với default error renderer, chỉ bắt lỗi thuộc phạm vi, không ghi response sau commit và không để lộ chi tiết nội bộ.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — Reactive Core, WebHandler API and Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.2 — Controller Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html)
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-advice.html)
- [Spring Boot 3.5 — Reactive Web Applications and Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5 — ErrorWebFluxAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/ErrorWebFluxAutoConfiguration.html).