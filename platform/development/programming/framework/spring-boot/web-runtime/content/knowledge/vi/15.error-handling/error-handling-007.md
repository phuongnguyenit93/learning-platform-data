# ErrorWebExceptionHandler, DefaultErrorWebExceptionHandler và ErrorAttributes trong Spring WebFlux

Trong ứng dụng **Spring Boot WebFlux**, khi một lỗi không được controller, handler chức năng hoặc cơ chế xử lý lỗi cục bộ giải quyết, Spring Boot có thể chuyển nó qua tầng xử lý lỗi toàn cục để tạo HTTP response. Ba tên gần nhau nhưng khác trách nhiệm:

- **ErrorAttributes**: cung cấp thông tin về lỗi, ví dụ HTTP status, request path, thời điểm, mã lỗi, thông điệp an toàn và dữ liệu phụ trợ.
- **DefaultErrorWebExceptionHandler**: triển khai sẵn của Spring Boot để dựng response lỗi, thường ở dạng JSON cho API client hoặc HTML nếu client yêu cầu HTML và có trang lỗi phù hợp.
- **ErrorWebExceptionHandler**: interface đánh dấu một WebExceptionHandler làm nhiệm vụ **render lỗi**. Có thể thay thế implementation mặc định khi cần kiểm soát cách phản hồi ở mức toàn cục.

Bài sử dụng **Spring Boot 3.5.16, Spring Framework 6.2.x và Java 17+**. Ví dụ chính dùng **spring-boot-starter-webflux** và Reactor Netty, không dùng Spring MVC/Servlet. Package API cần phân biệt rõ:

~~~text
Reactive WebFlux (Spring Boot 3.5.x):
org.springframework.boot.web.reactive.error.ErrorAttributes
org.springframework.boot.web.reactive.error.DefaultErrorAttributes
org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler
org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler
org.springframework.boot.autoconfigure.web.reactive.error.AbstractErrorWebExceptionHandler

Servlet Spring MVC (KHÁC):
org.springframework.boot.web.servlet.error.ErrorAttributes
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

Tên ErrorAttributes có ở cả hai web stacks, nhưng **không cùng interface method signature**. Trong WebFlux, phương thức lấy attributes dùng ServerRequest. Trong Servlet MVC, nó dùng WebRequest. Sao chép nhầm import có thể làm code không biên dịch hoặc không được auto-configuration sử dụng.

## 1. Tổng quan: một lỗi đi từ đâu đến response?

Spring WebFlux cung cấp DispatcherHandler và hệ thống HandlerMapping/HandlerAdapter/HandlerResultHandler cho annotated controllers và WebFlux.fn. Khi pipeline phát ra error signal, nhiều tầng có cơ hội xử lý trước khi lỗi đi tới global WebExceptionHandler.

Sơ đồ tư duy:

~~~text
HTTP request
  |
  v
Reactive HTTP server (thường Reactor Netty)
  |
  v
WebExceptionHandler chain bao quanh WebHandler
  |
  +--> WebFilter / SecurityWebFilterChain
  |          |
  |          v
  |      DispatcherHandler
  |          |
  |          +--> @RestController
  |          |      -> @ExceptionHandler / @RestControllerAdvice
  |          |      -> có thể tự xử lý error và trả response
  |          |
  |          +--> RouterFunction + HandlerFunction
  |                 -> onErrorResume / router filter có thể xử lý
  |
  +--> Lỗi chưa được xử lý và response chưa bị committed
             |
             v
       ErrorWebExceptionHandler
             |
             v
       DefaultErrorWebExceptionHandler (Boot mặc định)
             |
             +--> ErrorAttributes: status, path, error data...
             |
             +--> JSON hoặc error view HTML
             |
             v
       HTTP 4xx/5xx response
~~~

Sơ đồ minh họa **các cơ hội xử lý**, không mô tả chính xác tất cả decorator/callback theo từng implementation. Chú ý:

1. Error handler chỉ xử lý được một lỗi được **truyền tới nó**; nếu controller đã biến lỗi thành một response bình thường, tầng global không thể tự suy ra rằng lỗi vẫn đang chờ xử lý.
2. Khi HTTP response đã bắt đầu ghi headers/body, status và header có thể không còn đổi được. Lỗi giữa chừng của Flux streaming không bảo đảm trở thành một JSON 500 mới.
3. Một số lỗi được framework xử lý ở tầng WebFlux hoặc Security trước khi đến Boot fallback. Vì vậy không nên giả định mọi 400/401/403/404 đều chắc chắn chạy qua cùng custom ErrorAttributes.
4. Reactive error signal khác với việc gọi subscribe() hoặc ném exception ở một thread không liên quan request. Error bị xử lý khi còn nằm trong publisher/chain mà framework quản lý.

## 2. Vai trò của ErrorWebExceptionHandler

Spring Framework có interface:

~~~java
org.springframework.web.server.WebExceptionHandler
~~~

với một phương thức cốt lõi:

~~~java
Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
~~~

Trong Spring Boot, **ErrorWebExceptionHandler** thuộc package org.springframework.boot.web.reactive.error là một marker interface mở rộng WebExceptionHandler để đánh dấu implementation dùng cho **render lỗi WebFlux**.

Một implementation có thể:

- Đọc request, response và exception.
- Quyết định status HTTP phù hợp.
- Chọn media type, headers và nội dung response.
- Ghi response theo reactive publisher và trả Mono<Void>.
- Hoặc không xử lý lỗi và truyền tiếp cho một handler khác trong chain.

**Không phải lúc nào cũng nên tự implement interface thấp nhất.** Việc trực tiếp ghi ServerHttpResponse yêu cầu xử lý nhiều chi tiết: content negotiation, encoding, response committed, log, status, các response headers và cancellation. Nếu chỉ muốn thêm mã lỗi vào JSON, **custom ErrorAttributes thường đơn giản và an toàn hơn**.

### 2.1. Thứ tự trong exception handler chain

Trong Spring Boot 3.5.16, auto-configuration ErrorWebFluxAutoConfiguration đăng ký default ErrorWebExceptionHandler với **@Order(-1)**, nếu chưa có bean ErrorWebExceptionHandler do ứng dụng cung cấp. Các framework WebFlux exception handlers khác thường nằm sau đó trong thứ tự xử lý.

Nếu ứng dụng đăng ký một ErrorWebExceptionHandler riêng, Boot có thể **back off** và không tạo default error renderer nữa. Khi đó ứng dụng sở hữu trách nhiệm tạo response lỗi cho những request mà handler mới xử lý.

Một handler có order nhỏ hơn chạy sớm hơn trong chuỗi có sắp thứ tự, nhưng **thứ tự không phải điều kiện đủ để handler luôn nhận được mọi lỗi**: các exception đã được xử lý cục bộ hoặc không còn trong pipeline sẽ không đi tiếp.

Không dùng @Order một cách ngẫu nhiên để chữa lỗi. Hãy xác định trước handler nào cần xử lý, những lỗi nào cần truyền tiếp và cách kiểm thử toàn cục.

## 3. DefaultErrorWebExceptionHandler làm những gì?

**DefaultErrorWebExceptionHandler** là implementation toàn cục của Spring Boot. Nó kế thừa **AbstractErrorWebExceptionHandler** và sử dụng ErrorAttributes để cung cấp dữ liệu cho response.

Các trách nhiệm chính:

- Xác định dữ liệu lỗi qua ErrorAttributes.
- Sử dụng HTTP status thích hợp từ error attributes.
- Phân biệt request mong muốn HTML với request phù hợp JSON.
- Tìm error view theo quy ước của Boot và fallback sang whitelabel error page cho HTML.
- Tạo JSON response cho machine clients.
- Tham gia hệ thống codecs/message readers-writers của WebFlux.
- Tôn trọng các error properties liên quan đến việc cho phép hiển thị message, stack trace, binding errors và path.

Các method extension thuộc API Boot 3.5 gồm:

| Method | Mục đích |
|---|---|
| getRoutingFunction(ErrorAttributes) | Tạo RouterFunction nội bộ chọn cách render lỗi |
| renderErrorResponse(ServerRequest) | Render JSON error body |
| renderErrorView(ServerRequest) | Render HTML error view |
| acceptsTextHtml() | Predicate kiểm tra client chấp nhận HTML |
| getErrorAttributeOptions(ServerRequest, MediaType) | Xác định dữ liệu được phép đưa vào error attributes |
| getHttpStatus(Map<String,Object>) | Lấy HTTP status từ error map |
| isIncludeMessage / isIncludeStackTrace ... | Quyết định dữ liệu nhạy cảm có được đưa vào response không |

Đây là các điểm mở rộng **có tính phiên bản**, không phải các method application service. Khi nâng Boot, cần xem Javadoc và migration guide trước khi override.

### 3.1. DefaultErrorWebExceptionHandler không phải một @RestController

Mặc dù Boot dùng RouterFunction bên trong error handler, đó không phải một public functional endpoint mà client trực tiếp gọi để tạo lỗi. Nó là một phần của exception handling chain.

Spring MVC có BasicErrorController và error dispatch của Servlet container. **Không chuyển nguyên BasicErrorController hoặc ErrorController kiểu MVC sang reactive WebFlux** rồi kỳ vọng hoạt động giống nhau. Trong reactive stack, các interfaces và lifecycle tương ứng khác.

### 3.2. JSON hay HTML?

Boot mặc định hỗ trợ render HTML khi client **chủ động chấp nhận text/html** và chọn error view thích hợp, còn các API client thường nhận JSON khi request Accept: application/json.

Một request:

~~~http
GET /api/unknown HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

thường nhận JSON error body nếu lỗi chưa bị xử lý nơi khác. Một browser gửi Accept có text/html có thể nhận HTML error page. **Không test một content type duy nhất mà không kiểm soát Accept**, vì cùng status 404 nhưng body có thể khác.

Có thể đặt view lỗi ở:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/4xx.html
src/main/resources/templates/error/5xx.html
~~~

Spring Boot tìm các view theo thứ tự phù hợp với status, series và generic error page. Cần có template engine nếu dùng template tương ứng. Trong WebFlux, fallback template path thường là error/error; cách lookup khác Servlet MVC. Việc có file HTML không bảo đảm mọi request lỗi đều nhận HTML: content negotiation vẫn quan trọng.

## 4. ErrorAttributes chứa thông tin nào?

Interface reactive **org.springframework.boot.web.reactive.error.ErrorAttributes** cung cấp:

~~~java
Throwable getError(ServerRequest request);

Map<String, Object> getErrorAttributes(
        ServerRequest request,
        ErrorAttributeOptions options);

void storeErrorInformation(
        Throwable error,
        ServerWebExchange exchange);
~~~

Đây là **signature rút gọn minh họa API**, không phải một class Java độc lập.

**DefaultErrorAttributes** của Boot có thể cung cấp:

- timestamp: thời điểm lấy error data.
- status: mã HTTP, ví dụ 400, 404, 500.
- error: tên trạng thái hoặc lý do lỗi.
- path: request path, theo option/cấu hình.
- requestId: ID liên quan tới request khi có.
- message: thông điệp lỗi nếu cho phép.
- exception: tên class exception nếu cho phép.
- errors: binding/method validation errors nếu cho phép.
- trace: stack trace nếu cho phép.

**Các key không bảo đảm luôn xuất hiện.** Tập dữ liệu còn tùy lỗi, options, thuộc tính server.error.*, phiên bản Boot và handler đã render response.

### 4.1. ErrorAttributeOptions và nguyên tắc lộ dữ liệu

ErrorAttributeOptions của Spring Boot cho phép bao gồm/loại trừ những dữ liệu như:

~~~text
ErrorAttributeOptions.Include.MESSAGE
ErrorAttributeOptions.Include.STACK_TRACE
ErrorAttributeOptions.Include.BINDING_ERRORS
ErrorAttributeOptions.Include.EXCEPTION
ErrorAttributeOptions.Include.PATH
~~~

Lỗi nội bộ có thể chứa URL upstream, tên bảng database, đoạn SQL, object ID, path hệ thống hoặc thông tin xác thực. Vì vậy **không mở stack trace, exception class hay exception message cho tất cả client production**.

ErrorAttributes có thể nhận dữ liệu gốc từ server, nhưng response public nên có một **contract an toàn**: status, code ổn định, thông điệp đã kiểm duyệt, request ID nếu phù hợp. Chi tiết thật nên nằm trong log/tracing có kiểm soát truy cập.

### 4.2. Tại sao nên kế thừa DefaultErrorAttributes?

Khi override getErrorAttributes từ **DefaultErrorAttributes**, ta giữ được hành vi mặc định để lấy exception, xác định status, lưu error vào ServerWebExchange và cung cấp các trường chuẩn.

Một ErrorAttributes tự implement từ đầu phải thực hiện đầy đủ hợp đồng getError và storeErrorInformation; viết thiếu rất dễ khiến default renderer không tìm được lỗi/status phù hợp.

## 5. Chiến lược chọn mức customization

| Nhu cầu | Điểm mở rộng nên ưu tiên | Vì sao |
|---|---|---|
| Chỉ muốn đổi nội dung JSON, thêm code/correlation ID | Bean ErrorAttributes kế thừa DefaultErrorAttributes | Giữ default renderer và content negotiation |
| Chỉ muốn thay cách include message/trace | server.error.* properties | Ít code và dễ điều chỉnh theo môi trường |
| Muốn response chuẩn RFC 9457 Problem Details cho built-in exceptions | spring.webflux.problemdetails.enabled và WebFlux exception handling | Dùng chuẩn framework trước khi tự quản lý |
| Muốn xử lý exception của một annotated controller hoặc nhóm controller | @ExceptionHandler, @RestControllerAdvice | Rõ phạm vi, gần API contract |
| Muốn xử lý lỗi của một functional route riêng | onErrorResume hoặc WebFlux.fn handler/filter | Rõ phạm vi router, không ảnh hưởng toàn ứng dụng |
| Muốn thay logic chọn JSON/HTML hoặc error routing global | Kế thừa DefaultErrorWebExceptionHandler hoặc AbstractErrorWebExceptionHandler | Có hạ tầng builder/codecs sẵn |
| Muốn tự viết output bytes/headers, tự quyết toàn lifecycle | ErrorWebExceptionHandler thấp nhất | Linh hoạt nhưng phức tạp, dễ lỗi |
| Muốn render HTML 404/5xx riêng | Static/templates error pages | Không cần viết global low-level handler |

**Quy tắc:** thay dữ liệu trước khi thay luồng xử lý; thay luồng xử lý chỉ khi có requirement cụ thể và test bảo đảm hành vi mặc định quan trọng vẫn còn.

## 6. Dự án Java 17+ chạy được: custom ErrorAttributes, giữ Boot handler

Ta sẽ tạo một WebFlux application có:

1. GET /api/demo/ok trả 200.
2. GET /api/demo/bad-request chủ động phát ResponseStatusException(400).
3. GET /api/demo/failure phát IllegalStateException để mô phỏng lỗi server.
4. URL không có handler, ví dụ /api/no-such-resource, thường trả 404.
5. Custom **SanitizedErrorAttributes** thêm field code/message an toàn và loại bỏ những thuộc tính lỗi không muốn public.
6. DefaultErrorWebExceptionHandler vẫn được Spring Boot tự cấu hình; **không** tự tạo một ErrorWebExceptionHandler nữa.
7. Integration test qua HTTP thực bằng WebTestClient và RANDOM_PORT.

**Phạm vi ví dụ:** không dùng database, messaging hoặc external HTTP calls. Đây là bài học về error boundary, không phải nền tảng error catalog hoàn chỉnh.

### 6.1. Cấu trúc thư mục

~~~text
webflux-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/errors/
    │   │   ├── ErrorsApplication.java
    │   │   ├── DemoController.java
    │   │   └── SanitizedErrorAttributes.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/errors/
            └── ErrorContractTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-error-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-error-demo</name>

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

Không thêm spring-boot-starter-web, vì mục tiêu là reactive server của Spring WebFlux thay vì Spring MVC. Parent quản lý các versions phù hợp. Maven cần có Internet/cache/mirror dependency khi build.

### 6.3. application.yml

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never

spring:
  application:
    name: webflux-error-demo
~~~

Những property server.error.* là lớp phòng vệ thứ nhất, tránh vô tình đưa chi tiết exception vào response. Ví dụ còn có custom ErrorAttributes để chuẩn hóa output an toàn.

Không bật spring.webflux.problemdetails.enabled trong **demo này**, nhằm quan sát trực tiếp DefaultErrorWebExceptionHandler và JSON error map theo cơ chế Boot. Một ứng dụng khác có thể chọn bật Problem Details, nhưng cần test sự tương tác và định dạng thực tế.

### 6.4. ErrorsApplication.java

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
~~~

Class nằm trong package gốc com.example.errors để quét DemoController và SanitizedErrorAttributes. Không cần @EnableWebFlux, vì Boot đã tự cấu hình reactive web stack.

### 6.5. DemoController.java

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok() {
        return Mono.just(Map.of("result", "ok"));
    }

    @GetMapping("/bad-request")
    public Mono<Map<String, String>> badRequest() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Internal diagnostic details must stay private"));
    }

    @GetMapping("/failure")
    public Mono<Map<String, String>> failure() {
        return Mono.error(new IllegalStateException(
                "Internal failure details must stay private"));
    }
}
~~~

Đoạn mã trả Mono.error để lỗi **nằm trong reactive pipeline**, thay vì tự subscribe bên ngoài request lifecycle. Trong dự án thật, lỗi có thể đến từ R2DBC, WebClient hoặc service; yêu cầu bảo mật/logging không thay đổi.

ResponseStatusException biểu diễn lỗi HTTP chủ động có status. IllegalStateException không tự chứa status HTTP, nên global handler thường xem là lỗi server 500 khi không có custom mapping.

### 6.6. SanitizedErrorAttributes.java: điểm mở rộng chính

~~~java
package com.example.errors;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.reactive.error.DefaultErrorAttributes;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;

@Component
public class SanitizedErrorAttributes extends DefaultErrorAttributes {

    @Override
    public Map<String, Object> getErrorAttributes(
            ServerRequest request,
            ErrorAttributeOptions options) {

        Map<String, Object> attributes = new LinkedHashMap<>(
                super.getErrorAttributes(request, options));

        int status = ((Number) attributes
                .getOrDefault("status", 500)).intValue();

        attributes.remove("trace");
        attributes.remove("exception");
        attributes.remove("errors");
        attributes.remove("message");

        String code = switch (status) {
            case 400 -> "BAD_REQUEST";
            case 404 -> "NOT_FOUND";
            default -> status >= 500
                    ? "INTERNAL_ERROR" : "HTTP_ERROR";
        };

        String message = switch (status) {
            case 400 -> "Invalid request";
            case 404 -> "Resource not found";
            default -> status >= 500
                    ? "Unexpected server error" : "Request failed";
        };

        attributes.put("code", code);
        attributes.put("message", message);
        return attributes;
    }
}
~~~

Đây là lớp Java hoàn chỉnh, có thể copy vào project như cấu trúc đã nêu.

**Tại sao làm vậy?**

- @Component tạo một bean thuộc kiểu ErrorAttributes, làm ErrorWebFluxAutoConfiguration không cần tạo DefaultErrorAttributes bean thứ hai.
- Kế thừa DefaultErrorAttributes để giữ cơ chế lấy status và error details cần thiết cho default renderer.
- LinkedHashMap tạo bản sao có thể sửa được, không thay trực tiếp map từ superclass.
- Không xóa status: **DefaultErrorWebExceptionHandler dùng status để dựng response status**.
- Loại bỏ trace/exception/errors/message cũ để tránh phụ thuộc vào thông điệp thô.
- Thêm code là mã máy đọc ổn định; message là câu public an toàn.
- Không dùng exception.getMessage() để tạo client-facing message cho 500, vì exception có thể mang thông tin nhạy cảm.

**Giới hạn của demo:** mọi 4xx không thuộc 400/404 sẽ có code HTTP_ERROR và message Request failed. API production nên có bảng mã lỗi ổn định theo status/loại nghiệp vụ, thiết kế i18n và test thêm 401/403/405/409/422. Không coi cùng status 400 là một loại lỗi nghiệp vụ duy nhất.

## 7. Kiểm thử integration bằng WebTestClient

File **src/test/java/com/example/errors/ErrorContractTest.java**:

~~~java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorContractTest {

    @Autowired
    private WebTestClient client;

    @Test
    void successfulRequestIsNotRewritten() {
        client.get()
                .uri("/api/demo/ok")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.result").isEqualTo("ok");
    }

    @Test
    void badRequestHasSafePublicError() {
        client.get()
                .uri("/api/demo/bad-request")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo("BAD_REQUEST")
                .jsonPath("$.message").isEqualTo("Invalid request");
    }

    @Test
    void serverErrorDoesNotLeakInternalReason() {
        client.get()
                .uri("/api/demo/failure")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody(String.class)
                .value(body -> {
                    assertThat(body)
                            .contains("INTERNAL_ERROR")
                            .contains("Unexpected server error")
                            .doesNotContain(
                                    "Internal failure details must stay private");
                    assertThat(body).doesNotContain("stackTrace");
                });
    }

    @Test
    void unknownRouteProduces404() {
        client.get()
                .uri("/api/no-such-resource")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("NOT_FOUND");
    }
}
~~~

Đây là **HTTP integration test**: application chạy trên random port, nên kiểm thử cả WebFlux codecs, error handler auto-configuration và dữ liệu response trên wire. Không chỉ đơn thuần kiểm tra bean SanitizedErrorAttributes có tồn tại.

Cần ghi nhớ: tùy custom security/filter hoặc error handlers khác, một 404 có thể được dựng trước khi tới Boot fallback. Demo không đăng ký security/advice bổ sung nên trường hợp chưa có route được kỳ vọng đi qua cơ chế lỗi mặc định.

### 7.1. Chạy và diễn giải

~~~bash
mvn test
mvn spring-boot:run
~~~

Lệnh đầu chạy JUnit tests. Khi kiểm thử thành công, Maven trả exit code 0. Lệnh thứ hai mở embedded server theo cấu hình application.yml; không chạy cùng lúc hai Maven processes trên cổng cố định nếu không cần.

Sau khi server chạy, thử:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/ok

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/bad-request

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/demo/failure

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/no-such-resource
~~~

Kết quả chính:

| Request | HTTP status | Điều cần xác minh |
|---|---|---|
| GET /api/demo/ok | 200 | JSON có result=ok |
| GET /api/demo/bad-request | 400 | status=400, code=BAD_REQUEST, message=Invalid request |
| GET /api/demo/failure | 500 | code=INTERNAL_ERROR, không có exception message nội bộ |
| GET /api/no-such-resource | 404 | code=NOT_FOUND khi Boot fallback xử lý |

Ví dụ **minh họa về nội dung**, không cố định thứ tự JSON key:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "code": "INTERNAL_ERROR",
  "message": "Unexpected server error"
}
~~~

DefaultErrorAttributes có thể bổ sung timestamp, path và requestId. Không nên assert thứ tự key, timestamp cụ thể hoặc request ID trong test. Header và error body thực tế có thể khác khi thêm Spring Security, custom response handlers hoặc đổi version.

## 8. Vì sao giữ DefaultErrorWebExceptionHandler lại tốt?

Trong ví dụ, ta chỉ thay **dữ liệu** error, không thay **cách dựng response**. Điều này giúp Boot vẫn quyết định:

- Status từ error map.
- Cơ chế JSON writing với codecs được cấu hình.
- Content negotiation JSON/HTML.
- Quy ước error views của WebFlux.
- Xử lý include-message, include-stacktrace, include-binding-errors theo properties.
- Tích hợp với auto-configuration của ứng dụng.

Dù vậy, một custom ErrorAttributes trả map sai (ví dụ xóa key status, đặt status thành String không hợp lệ, hoặc chứa object không serialize được) vẫn có thể phá default renderer.

**Quy tắc tốt:** giữ các key nền tảng cần thiết; thêm mã riêng rõ ràng; không trả Throwable, StackTraceElement[], hoặc object domain không an toàn vào attributes. Custom ErrorAttributes là nơi chuẩn hóa **response metadata**, không phải nơi làm database query.

## 9. DefaultErrorWebExceptionHandler và content negotiation

Với browser, Accept có thể bao gồm text/html. Boot ưu tiên render error view HTML trong những trường hợp phù hợp.

Với API clients, nên gửi:

~~~http
Accept: application/json
~~~

và kiểm tra Content-Type phản hồi. Nếu client nhận HTML whitelabel page thay vì JSON, hãy kiểm tra **request Accept thực tế**, proxy và error handler selection trước khi cho rằng ObjectMapper lỗi.

### 9.1. Lỗi 404 có thể được hiển thị bằng static HTML

Tạo file:

~~~text
src/main/resources/public/error/404.html
~~~

với nội dung minh họa:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Không tìm thấy</title></head>
<body>
  <h1>404 - Không tìm thấy trang</h1>
</body>
</html>
~~~

Khi browser yêu cầu HTML và Boot chọn view theo quy ước, nội dung có thể được dùng cho 404. Không thêm file này vào demo API nếu mục tiêu test máy đọc là JSON thuần; nó thuộc tình huống tùy chỉnh giao diện website.

Nếu static page chứa thông tin người dùng hoặc lỗi nội bộ, phải xem lại chính sách bảo mật. Error page nên cung cấp hướng dẫn đơn giản, không dump stack trace.

## 10. Tùy chỉnh DefaultErrorWebExceptionHandler ở mức nâng cao

Khi cần **đổi lựa chọn render**, ví dụ API gateway yêu cầu response lỗi luôn là JSON kể cả request Accept có text/html, bạn có thể **kế thừa DefaultErrorWebExceptionHandler** và override getRoutingFunction.

**Lưu ý phạm vi:** đoạn dưới là **một phương án thay thế cho cơ chế render mặc định**, không được đưa vào demo chính như một class thông thường mà không thay cấu hình bean tương ứng. Nó thay lựa chọn HTML/JSON của Boot, nên phải cân nhắc hợp đồng với browser và template views.

Ví dụ subclass, dùng đúng constructor của **Spring Boot 3.5.16**:

~~~java
package com.example.errors;

import org.springframework.boot.autoconfigure.web.ErrorProperties;
import org.springframework.boot.autoconfigure.web.WebProperties;
import org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler;
import org.springframework.boot.web.reactive.error.ErrorAttributes;
import org.springframework.context.ApplicationContext;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

public class JsonOnlyErrorHandler extends DefaultErrorWebExceptionHandler {

    public JsonOnlyErrorHandler(
            ErrorAttributes errorAttributes,
            WebProperties.Resources resources,
            ErrorProperties errorProperties,
            ApplicationContext applicationContext) {

        super(errorAttributes, resources, errorProperties,
                applicationContext);
    }

    @Override
    protected RouterFunction<ServerResponse> getRoutingFunction(
            ErrorAttributes errorAttributes) {

        return RouterFunctions.route(
                request -> true,
                this::renderErrorResponse);
    }
}
~~~

Ở đây RequestPredicate dạng lambda luôn match request lỗi, rồi gọi renderErrorResponse của superclass. Vì vậy HTML error view mặc định không còn được chọn trong phạm vi handler này.

**Quan trọng:** subclass cần được **đăng ký là ErrorWebExceptionHandler bean**. Chỉ định nghĩa class mà không tạo bean thì Spring Boot không tự dùng class đó. Ngoài ra, khi tự đăng ký handler, cần cấu hình message readers/writers và view resolvers phù hợp.

Một configuration riêng cho phương án nâng cao:

~~~java
package com.example.errors;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.web.ServerProperties;
import org.springframework.boot.autoconfigure.web.WebProperties;
import org.springframework.boot.web.reactive.error.ErrorAttributes;
import org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.result.view.ViewResolver;

@Configuration(proxyBeanMethods = false)
public class JsonOnlyErrorConfiguration {

    @Bean
    @Order(-2)
    ErrorWebExceptionHandler jsonOnlyErrorHandler(
            ErrorAttributes attributes,
            WebProperties webProperties,
            ServerProperties serverProperties,
            ApplicationContext applicationContext,
            ServerCodecConfigurer codecs,
            ObjectProvider<ViewResolver> viewResolvers) {

        JsonOnlyErrorHandler handler = new JsonOnlyErrorHandler(
                attributes,
                webProperties.getResources(),
                serverProperties.getError(),
                applicationContext);

        handler.setMessageReaders(codecs.getReaders());
        handler.setMessageWriters(codecs.getWriters());
        handler.setViewResolvers(
                viewResolvers.orderedStream().toList());

        return handler;
    }
}
~~~

Nếu quyết định thử cách này, thêm **cả hai** class JsonOnlyErrorHandler và JsonOnlyErrorConfiguration vào project, rồi kiểm thử lại mọi status. Chúng **không thuộc phiên bản runnable mặc định** ở mục 6–7. Vì bean custom ErrorWebExceptionHandler đã xuất hiện, Boot có thể không đăng ký DefaultErrorWebExceptionHandler tự động nữa. Order -2 là lựa chọn cụ thể cho ví dụ, không phải một hằng số cần áp dụng cho mọi project.

Vì configuration này thay cách render HTML/JSON, phải test:

- API clients với Accept: application/json.
- Browser clients với Accept: text/html.
- 404, 400 và 500 từ những nguồn khác nhau.
- Có trường hợp body response hoặc headers đã committed hay không.
- Codec cho định dạng response mong muốn đã sẵn sàng chưa.
- Mọi error attributes còn hợp lệ và có status đúng chưa.

**Khi chỉ cần thêm code/message an toàn, KHÔNG cần những lớp nâng cao này; dùng SanitizedErrorAttributes như mục 6 là đủ.**

## 11. AbstractErrorWebExceptionHandler: ở giữa thấp và cao

Spring Boot cung cấp **AbstractErrorWebExceptionHandler** để xây error response bằng phong cách functional WebFlux. Nó nằm giữa hai lựa chọn:

- ErrorWebExceptionHandler thấp nhất: bạn tự xử lý ServerWebExchange và Mono<Void>.
- DefaultErrorWebExceptionHandler: Boot đã triển khai gần đủ cho JSON/HTML, bạn override một phần.
- AbstractErrorWebExceptionHandler: Boot cung cấp hạ tầng ErrorAttributes, routing, message writers/readers, view resolvers; bạn tự định nghĩa getRoutingFunction và cách dựng response.

Khi kế thừa AbstractErrorWebExceptionHandler, bạn phải cung cấp RouterFunction phù hợp; nếu router không match request lỗi, exception gốc có thể được truyền tiếp cho những WebExceptionHandler khác.

Đây là tính chất quan trọng: **RouterFunction nội bộ của error handler có thể chọn không xử lý lỗi**, không nên giả định nó luôn trả một ServerResponse.

Nếu muốn thay toàn bộ body format nhưng vẫn dựa trên ServerRequest/ServerResponse, AbstractErrorWebExceptionHandler thường đơn giản hơn implement WebExceptionHandler từ đầu. Nếu chỉ đổi một status/message, vẫn ưu tiên ErrorAttributes hoặc xử lý cục bộ.

## 12. Điều gì xảy ra nếu tự implement ErrorWebExceptionHandler?

Một implementation thấp nhất có signature:

~~~java
public interface ErrorWebExceptionHandler
        extends WebExceptionHandler {
}
~~~

Đây là mô tả interface về mặt cấu trúc, không phải source file cần thêm; class framework đã định nghĩa sẵn.

Một handler tự viết phải quan tâm:

1. Kiểm tra response.isCommitted() trước khi cố đổi status/headers.
2. Đặt HTTP status thích hợp cho exception, không trả 500 cho mọi 4xx.
3. Chọn Content-Type, charset và codec.
4. Tạo body an toàn và reactive Mono<Void>.
5. Không chặn event-loop bằng block(), Thread.sleep hoặc database/JDBC đồng bộ.
6. Không gọi subscribe() thủ công rồi trả Mono.empty() trước khi ghi xong response.
7. Không bỏ qua cancellation và lỗi trong lúc encode/write body.
8. Bảo toàn các header quan trọng như Allow cho 405 hoặc những header security/caching có liên quan.
9. Theo dõi tracing/metrics mà không double-log hoặc nuốt lỗi.
10. Viết integration tests với đúng thứ tự exception handlers.

Một handler trả Mono.empty() sau khi đã xử lý và hoàn tất response khác với handler trả Mono.error(original) để chuyển lỗi sang handler tiếp theo. Không tự thay đổi cơ chế propagation khi chưa hiểu WebExceptionHandler contract.

Khi response đã được commit, toàn bộ việc dựng một JSON lỗi mới có thể bất khả thi. Đặc biệt với Server-Sent Events hoặc Flux streaming, status thường đã gửi trước khi một publisher phát lỗi muộn.

## 13. @RestControllerAdvice và @ExceptionHandler đứng ở đâu?

Một ứng dụng **annotated WebFlux controller** có thể dùng @ExceptionHandler hoặc @RestControllerAdvice:

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handle(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest().body(
                Map.of("code", "BAD_INPUT"));
    }
}
~~~

Đoạn này minh họa riêng; cần import org.springframework.web.bind.annotation.RestControllerAdvice, ExceptionHandler, org.springframework.http.ResponseEntity và java.util.Map.

Một exception được advice xử lý **không nhất thiết đến DefaultErrorWebExceptionHandler**, vì WebFlux có thể đã tạo một response thành công ở tầng handler result. Do đó:

- Nếu error contract phải thống nhất, chọn rõ nơi sở hữu từng loại lỗi.
- Không trông đợi ErrorAttributes luôn bổ sung code cho response do @ExceptionHandler tự dựng.
- Viết test cho cả lỗi được advice xử lý và lỗi không được xử lý.
- Với functional WebFlux.fn, dùng onErrorResume hoặc HandlerFilterFunction; đừng giả định mọi exception được functional handler phát đều đi vào @RestControllerAdvice như annotated controller.
- Với Spring Security, authentication/authorization failures có cơ chế response riêng; các lỗi 401/403 không phải lúc nào cũng qua Boot error renderer.

Trong demo chính, không tạo advice để các lỗi mô phỏng đi qua fallback toàn cục.

## 14. WebFlux.fn: xử lý lỗi cục bộ

Functional handler nhận ServerRequest và trả Mono<ServerResponse>. Có thể map lỗi tại chỗ:

~~~java
public Mono<ServerResponse> find(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
            .flatMap(value ->
                    ServerResponse.ok().bodyValue(value))
            .switchIfEmpty(
                    ServerResponse.notFound().build())
            .onErrorResume(
                    IllegalArgumentException.class,
                    error -> ServerResponse.badRequest().build());
}
~~~

Đây là đoạn minh họa riêng, giả định service đã được inject và trả Mono của một object phù hợp. Nó không thuộc demo runnable mục 6. Lưu ý:

- switchIfEmpty trả 404 là một response bình thường, không phải lỗi đang lan truyền. DefaultErrorWebExceptionHandler **không cần chạy** để tạo response đó.
- onErrorResume đổi error signal thành response 400; cũng không còn error để global handler xử lý.
- Nếu muốn central global handler xử lý một lỗi chưa được map, giữ nguyên error signal bằng Mono.error và không tự subscribe.
- Nếu error đến sau khi response streaming đã bắt đầu, handler có thể không đổi được status/body nữa.

Nên thống nhất cách mã hóa lỗi giữa annotated/functional endpoints, nhưng không buộc tất cả lỗi phải đi qua duy nhất một global handler nếu điều đó làm thiết kế phức tạp không cần thiết.

## 15. Problem Details theo RFC 9457

Trước khi tự viết toàn bộ lỗi JSON, xem xét **ProblemDetail** của Spring Framework và cơ chế Spring Boot:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Tùy chọn này cho phép Boot tự cấu hình hỗ trợ Problem Details cho các built-in WebFlux exceptions theo tài liệu. Response chuẩn thường dùng:

~~~http
Content-Type: application/problem+json
~~~

với những field chính:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "A requested resource does not exist",
  "instance": "/api/items/999"
}
~~~

Đây là **ví dụ hợp đồng**, không phải bảo đảm rằng lỗi mặc định Spring Boot sẽ luôn xuất đúng câu detail này.

**Quan trọng:** bật property không có nghĩa tất cả Throwable trong mọi lớp, bao gồm lỗi bảo mật và lỗi do functional handlers tự xử lý, sẽ đồng nhất thành ProblemDetail. Một số exceptions được xử lý qua ResponseEntityExceptionHandler/ControllerAdvice, một số đi qua global fallback, một số là response trực tiếp.

Nếu chọn Problem Details, hãy quyết định nó là format chính của API và **test toàn bộ các nhóm lỗi**. Không đồng thời duy trì hai schema JSON khác nhau mà không tài liệu hóa.

### 15.1. ErrorAttributes và ProblemDetail có thể cùng tồn tại không?

Có thể có cả hai cơ chế trong application, nhưng không nên giả định chúng hợp nhất field tự động. Tùy nguồn lỗi, handler nào nhận error trước có thể quyết định format response. Khi muốn chuẩn hóa, thiết kế một lớp mapping lỗi dùng chung ở những điểm thích hợp và tránh duplicating logic.

## 16. Error properties thường cần xem

Với Spring Boot WebFlux 3.5, các property thuộc nhóm **server.error.*** điều khiển phần dữ liệu lỗi hiển thị. Ví dụ:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Một số môi trường có thể hỗ trợ lựa chọn include theo tham số request (on_param), nhưng không nên bật ở production nếu client bất kỳ có thể thêm tham số để lấy stack trace hoặc thông tin nội bộ.

Phân biệt:

- **server.error.include-message**: có cho phép message exception trong error attributes/response theo renderer hiện tại không.
- **server.error.include-stacktrace**: có cho phép trace hay không.
- **server.error.include-binding-errors**: có cho phép chi tiết binding/validation errors hay không.
- **server.error.path**: cấu hình liên quan tới đường dẫn error mặc định; không biến một global WebExceptionHandler thành một controller REST của ứng dụng.
- **spring.webflux.problemdetails.enabled**: bật hỗ trợ Problem Details cho built-in WebFlux exception handling trong Boot.

Không xem các thuộc tính này là một **bộ lọc toàn cục có thể bảo vệ mọi custom error handler**. Nếu chính bạn tự viết code gọi response.writeWith và đưa exception.getMessage() vào JSON, Boot không thể tự loại bí mật khỏi chuỗi đó.

## 17. Truyền đúng HTTP status và headers

ErrorAttributes thường mang status. DefaultErrorWebExceptionHandler lấy status để dựng response. Khi custom map, **không xóa hoặc thay status thành một kiểu dữ liệu sai**.

Một số trạng thái cần chú ý:

| HTTP status | Tình huống | Lưu ý |
|---|---|---|
| 400 | Request input không hợp lệ | Không trả 500 cho lỗi client rõ ràng |
| 401 | Chưa xác thực | Có thể do security entry point xử lý, cần giữ WWW-Authenticate khi thích hợp |
| 403 | Không có quyền hoặc CSRF fail | Security filter có thể sở hữu response |
| 404 | Route/tài nguyên không tồn tại | Phân biệt routing 404 và business 404 |
| 405 | Method không được hỗ trợ | Allow header có ý nghĩa HTTP và không được làm mất |
| 409 | Xung đột trạng thái nghiệp vụ | API layer/service mapping phải rõ |
| 415 | Unsupported Media Type | Do consumes/codec của request body |
| 422 | Semantic input error theo API contract | Không tự áp dụng cho mọi validation |
| 500 | Lỗi không dự kiến từ server | Phải ẩn thông tin nội bộ |
| 503 | Upstream unavailable / overload theo chính sách | Có thể có Retry-After phù hợp |

**Lưu ý:** chỉ nhìn một Throwable chưa đủ để định status của toàn bộ hệ thống. Spring Framework có ResponseStatusException, ErrorResponse và exception handling riêng; Spring Security/Gateway cũng có cơ chế của chúng. Custom global handler cần tôn trọng semantics HTTP và bảo toàn những headers cần thiết.

## 18. Observability, logging và correlation ID

Một lỗi server thường cần hai góc nhìn:

**Client-facing:** status, error code ổn định, message an toàn, request ID/correlation ID có thể dùng khi báo sự cố.

**Server-side:** exception type, stack trace, tracing span, request ID, upstream latency, thông tin hệ thống phù hợp với logging policy.

Không nên đưa toàn bộ server-side error data vào public JSON. Ví dụ, thay vì message "Database socket timeout to internal-host:5432", trả "Unexpected server error" và ghi chi tiết ở log/tracing an toàn.

### 18.1. requestId khác business correlation ID

DefaultErrorAttributes WebFlux có thể có requestId liên quan HTTP exchange. Một hệ thống nhiều service có thể dùng traceId của distributed tracing hoặc một correlation ID được tạo/kiểm soát ở gateway. Chúng không nhất thiết giống nhau.

Nếu thêm request identifier vào error response:

- Xác định nguồn tạo và nơi xác minh ID.
- Tránh tin mù quáng header do client tùy ý gửi.
- Tránh log payload, Authorization header, cookie và PII.
- Kiểm thử rằng ID trong JSON tương ứng ID mà support/logs có thể tra cứu.
- Với Reactor Context, không phụ thuộc vô điều kiện vào ThreadLocal xuyên scheduler boundaries.

### 18.2. Lỗi đã được xử lý có thể không hiện trong metrics như mong đợi

Khi controller/advice bắt exception và trả response 4xx/5xx, framework observation có thể không tự nhận được exception gốc trong mọi trường hợp. Tùy công cụ quan sát và phiên bản Spring, cần ghi nhận handled exception trên observation context hoặc bổ sung metrics phù hợp.

Không dùng "đếm số lần ErrorWebExceptionHandler chạy" làm chỉ số tổng số lỗi của hệ thống. Nó không bao phủ mọi lỗi được xử lý cục bộ.

## 19. Reactive safety và streaming responses

Trong WebFlux, Mono và Flux đại diện cho những công việc có thể được subscribe/cancel theo vòng đời request. Một global error handler chỉ có thể phản hồi khi error signal còn trong chain và response có thể ghi được.

### 19.1. Không dùng block() trong error handler

Sai:

~~~java
String detail = webClient.get()
        .uri("/diagnostics")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

Đây là anti-pattern minh họa. Nó có thể chặn event loop, thậm chí làm một lỗi ban đầu kéo theo lỗi mới trong global error handler.

Một error handler nên làm ít công việc, ưu tiên dữ liệu đã có ở ServerWebExchange hoặc exception object. Nếu phải gọi I/O để enrich error response, cần thiết kế timeout, fallback và reactive composition rất cẩn thận; thông thường không nên gọi network từ global error renderer.

### 19.2. Không tự gọi subscribe() và kết thúc request

Sai:

~~~java
Mono<Void> writing = response.writeWith(bodyPublisher);
writing.subscribe();
return Mono.empty();
~~~

Code trên tách công việc ghi ra khỏi publisher trả cho framework. Nó có thể gây response sớm, mất backpressure/cancellation và lỗi không được quan sát.

Thay vì vậy, nếu tự implement WebExceptionHandler, **trả chính publisher viết response**:

~~~java
return response.writeWith(bodyPublisher);
~~~

Các đoạn này là minh họa về reactive semantics, không phải một class ErrorWebExceptionHandler hoàn chỉnh.

### 19.3. Khi response đã committed

Ví dụ endpoint stream text/event-stream đã gửi một số sự kiện rồi Flux.error được phát ra. Không thể đảm bảo đổi response thành HTTP 500 JSON vì client có thể đã nhận HTTP 200 và một phần body.

Chiến lược đúng có thể là:

- Kết thúc stream và để client retry theo hợp đồng.
- Phát một event lỗi có schema riêng nếu protocol hỗ trợ.
- Log/tracing lỗi và giải phóng tài nguyên.
- Đặt timeout/retry policy ở đúng tầng.
- Kiểm thử ngắt kết nối và cancellation.

Global error renderer không thay thế protocol error handling cho streams.

## 20. Kiểm thử các trường hợp dễ bị bỏ sót

Ngoài bốn test ở mục 7, nên mở rộng:

1. **Accept: application/json** nhận JSON error schema.
2. **Accept: text/html** nhận error page nếu còn giữ default HTML rendering.
3. Lỗi 400 từ ResponseStatusException.
4. Lỗi 404 do không có route.
5. Lỗi nghiệp vụ được map thành một ResponseEntity 404 trực tiếp; xác nhận global ErrorAttributes không bị kỳ vọng áp dụng sai.
6. Lỗi 500 không tiết lộ internal message/stack trace.
7. Spring Security 401/403 với rule thực tế.
8. Lỗi validation @Valid trong annotated controller.
9. Lỗi WebFlux.fn được xử lý bởi onErrorResume và lỗi không được xử lý.
10. Request từ gateway/proxy có forwarded prefix và request ID.
11. Request body media type sai, JSON sai, method sai để bảo đảm status không đổi thành 500.
12. Streaming publisher phát lỗi sau khi response đã committed.
13. Custom handler có order, message readers/writers và error attributes phù hợp.
14. Các response với error path chứa ký tự lạ/PII được kiểm soát theo policy.

WebTestClient phù hợp với WebFlux. Khi test handler toàn cục và auto-configuration, ưu tiên @SpringBootTest RANDOM_PORT hoặc test ứng dụng đủ context; một test bindToController riêng có thể không kích hoạt cùng Boot global error handler.

Không assert exception class nội bộ hoặc thứ tự JSON fields trừ khi đó thật sự là hợp đồng công khai của ứng dụng.

## 21. Những lỗi phổ biến và hướng điều tra

| Hiện tượng | Nguyên nhân hay gặp | Cách sửa |
|---|---|---|
| Custom ErrorAttributes không được gọi | Bean chưa được scan, lỗi đã được @ExceptionHandler xử lý hoặc application chạy MVC | Kiểm tra context, stack MVC/WebFlux và vị trí lỗi |
| Import ErrorAttributes xong lỗi method signature | Nhầm package Servlet với Reactive | Dùng org.springframework.boot.web.reactive.error.ErrorAttributes |
| Browser thấy HTML, test chờ JSON | Accept của browser có text/html | Test với Accept JSON hoặc tùy chỉnh renderer theo contract |
| JSON error có message/trace nội bộ | server.error.* mở hoặc custom handler tự trả exception text | Tắt include, sanitize attributes, test dữ liệu nhạy cảm |
| Mọi lỗi thành 500 | Custom handler ghi status cố định | Giữ status mapping và xem ResponseStatusException |
| Lỗi @RestControllerAdvice xử lý không có custom code từ ErrorAttributes | Advice đã tạo response trước global fallback | Chuẩn hóa error contract tại advice hoặc có shared mapping |
| Custom DefaultErrorWebExceptionHandler không chạy | Chưa đăng ký bean hoặc Boot có handler khác | Đăng ký ErrorWebExceptionHandler bean, kiểm tra order và auto-configuration |
| Tự đăng ký handler thì JSON serialize lỗi | Thiếu message writers/readers hoặc codec không phù hợp | Cấu hình ServerCodecConfigurer như mục 10 |
| Error handler bị khởi tạo lỗi | Không cung cấp resources/context hoặc chưa set infrastructure | Dùng constructor đúng phiên bản và kiểm tra dependency beans |
| Response body trống sau lỗi giữa stream | Response đã committed | Thiết kế stream error contract riêng; không cố ghi JSON mới |
| Service trả Mono.empty nhưng client muốn 404 | Mono.empty không tự đồng nghĩa 404 | Chủ động map empty thành status/exception phù hợp |
| Exception trong reactive pipeline biến mất | Code tự subscribe hoặc swallow bằng onErrorComplete | Trả publisher cho framework; xử lý có chủ đích |
| Health check bị HTML 404 khi đổi base path | Sai URL qua proxy hoặc server stack | Đối chiếu path bên ngoài và internal mappings |
| ProblemDetail và error map xuất hai format khác nhau | Một số lỗi đi qua advice, số khác qua Boot fallback | Chuẩn hóa schema và test từng nguồn lỗi |
| 405 không có Allow đúng sau customization | Handler tự tạo response và bỏ header gốc | Bảo toàn HTTP semantics hoặc để framework xử lý |
| Không thấy lỗi trong metrics dù client nhận 500 | Error được xử lý trước observation ghi nhận exception | Điều chỉnh observation/tracing cho handled errors |

## 22. Quy trình điều tra thực tế

Khi một hệ thống WebFlux trả lỗi bất thường:

1. Ghi **request thật**: method, URL sau proxy, Accept, Content-Type, request ID, status và response headers.
2. Kiểm tra đang chạy **Spring WebFlux reactive** hay Spring MVC có WebClient; đừng chọn package theo tên dependency một cách máy móc.
3. Xác định exception xuất phát ở controller annotation, functional handler, filter/security, router hay codec.
4. Kiểm tra xem @ExceptionHandler, @RestControllerAdvice, onErrorResume hoặc security đã biến lỗi thành response chưa.
5. Nếu lỗi vẫn vào global chain, xác nhận ErrorWebExceptionHandler bean nào được dùng và thứ tự của nó.
6. Kiểm tra ErrorAttributes getErrorAttributes tạo map nào, status có hợp lệ và dữ liệu có an toàn không.
7. Kiểm tra DefaultErrorWebExceptionHandler chọn JSON hay HTML và codec nào đang ghi response.
8. Test không có custom handler để so sánh với Boot defaults trong môi trường thử nghiệm riêng; không thay production không kiểm soát.
9. Kiểm tra trường hợp response already committed hoặc streaming.
10. Xác nhận Problem Details/security/gateway behavior nếu có.
11. Viết integration regression test cho status, headers, error code, safe message và không lộ stack trace.
12. Sau khi sửa, theo dõi error rate/latency và tracing thay vì chỉ xem một curl response.

Bắt đầu từ bằng chứng HTTP, không đoán từ một dòng log duy nhất. Đừng tự sửa global status mapping cho mọi exception chỉ để chữa một endpoint.

## 23. Checklist trước khi merge

- [ ] Xác nhận ứng dụng chạy Spring WebFlux, không import nhầm Servlet ErrorAttributes.
- [ ] Hiểu vai trò của ErrorWebExceptionHandler, DefaultErrorWebExceptionHandler và ErrorAttributes.
- [ ] Dùng ErrorAttributes nếu chỉ thay dữ liệu error response.
- [ ] Không xóa trường status hoặc đưa object không serialize được vào error map.
- [ ] Không để lộ exception message, trace, validation rejectedValue hoặc secret qua public response.
- [ ] Xác định rõ schema JSON, status HTTP, code nghiệp vụ và các header cần bảo toàn.
- [ ] Có test 400/404/500 và test success path.
- [ ] Phân biệt error đã được advice/onErrorResume xử lý và error còn tới global fallback.
- [ ] Nếu custom handler thay Boot default: có registration, order, readers, writers và view resolvers.
- [ ] Kiểm tra JSON/HTML theo Accept thực tế.
- [ ] Có chiến lược ProblemDetail riêng nếu dự án bật spring.webflux.problemdetails.enabled.
- [ ] Không block() hay subscribe() trong reactive error handling.
- [ ] Không cố sửa status/body sau khi response committed.
- [ ] Test qua gateway, Spring Security và actuator nếu ứng dụng sử dụng.
- [ ] Tracing/logging giữ dữ liệu nhạy cảm an toàn và hỗ trợ correlation ID.
- [ ] Đã đối chiếu API với đúng phiên bản Spring Boot khi nâng major version.

## 24. Kết luận

**ErrorAttributes cung cấp dữ liệu lỗi; DefaultErrorWebExceptionHandler dựng response JSON/HTML; ErrorWebExceptionHandler là hợp đồng mở rộng để thay cách render lỗi ở tầng WebFlux toàn cục.**

Trong đa số ứng dụng Spring Boot, hãy **giữ default handler và thêm một ErrorAttributes bean** khi chỉ cần mã lỗi, message an toàn hoặc metadata. Sử dụng @RestControllerAdvice hoặc xử lý tại WebFlux.fn cho những lỗi thuộc rõ một API/route. Chỉ kế thừa DefaultErrorWebExceptionHandler, AbstractErrorWebExceptionHandler hoặc tự implement ErrorWebExceptionHandler khi cần thay đổi cơ chế render/status/format toàn cục và đã kiểm thử đầy đủ.

Bảo toàn semantics HTTP, không để lộ nội dung exception, không block event loop và không nhầm lỗi đã xử lý với lỗi chờ global fallback. Đó là những nguyên tắc quan trọng nhất khi xây error contract đáng tin cậy trên reactive stack.

## Tài liệu chính thức

- [Spring Boot 3.5 — Reactive Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5.16 — DefaultErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html)
- [Spring Boot 3.5.16 — AbstractErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/AbstractErrorWebExceptionHandler.html)
- [Spring Boot 3.5.16 — Reactive DefaultErrorAttributes API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/error/DefaultErrorAttributes.html)
- [Spring Boot 3.5.16 — Reactive ErrorAttributes API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/reactive/error/ErrorAttributes.html)
- [Spring Boot 3.5.16 — ErrorWebFluxAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/ErrorWebFluxAutoConfiguration.html)
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
