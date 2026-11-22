# Đọc hoặc bổ sung header mà không tiêu thụ mất request body trong Spring Boot WebFlux

## 1. Mục tiêu và tình huống thực tế

Trong một ứng dụng HTTP, bộ lọc thường phải đọc metadata như X-Request-Id, Accept, Content-Type, Authorization hoặc bổ sung một header dùng cho tracing trước khi request tới controller. Vấn đề là **request body chỉ nên được tiêu thụ bởi thành phần được thiết kế để xử lý nó**, chẳng hạn WebFlux HTTP message reader, controller hoặc một bộ xử lý body chuyên dụng.

Một sai lầm hay gặp là viết filter để log request, đọc body bằng subscribe()/block()/DataBufferUtils.join(), rồi vẫn truyền request gốc cho controller. Với body từ kết nối HTTP vốn thường là luồng **không replay tự động**, controller phía sau có thể nhận body rỗng, request bị lỗi hoặc sinh hành vi phụ thuộc timing. Với Netty pooled buffers, việc giữ/release sai còn gây leak và corruption.

Giải pháp đúng cho nhu cầu header thuần túy là **không đọc body**:

- Đọc header qua exchange.getRequest().getHeaders().
- Nếu muốn thay header mà các handler phía sau nhìn thấy, dùng ServerHttpRequest.mutate() và ServerWebExchange.mutate().
- Nếu chỉ muốn thêm response header, ghi qua response.getHeaders() trước commit hoặc đăng ký response.beforeCommit(...).
- Luôn return chain.filter(exchange) hoặc chain.filter(mutatedExchange) như một Mono<Void>; không tự subscribe().
- Không gọi getBody().subscribe(), collectList().block(), DataBuffer.read() hay DataBufferUtils.join() chỉ để làm việc với header.

Bài dùng **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x, Reactor Netty và Spring WebFlux**. Các annotation tương tự có thể có trong Spring MVC, nhưng Servlet Filter/HandlerInterceptor và WebFlux WebFilter là các abstraction khác nhau.

Sau bài học, bạn có thể viết một WebFilter đọc/sửa request header, bổ sung response header, không làm mất JSON body, hiểu trường hợp cần thật sự quan sát body và kiểm thử được hành vi end-to-end.

## 2. Một request HTTP có những gì?

Ví dụ:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Request-Id: req_123
Content-Length: 30

{"message":"Hello from client"}
~~~

Có ba phần cần phân biệt:

1. **Request line và URI**: phương thức POST, đường dẫn /api/echo, query string nếu có.
2. **Headers**: tên/giá trị metadata như Content-Type, Accept, X-Request-Id.
3. **Body**: JSON, text, multipart, file bytes hoặc dữ liệu streaming.

Trong WebFlux, ServerHttpRequest.getHeaders() cung cấp HttpHeaders chứa metadata đã được HTTP server/parser xử lý. Nó **không cần subscribe** vào request body.

Trong khi đó getBody() trả Flux<DataBuffer>. Flux này mô tả luồng dữ liệu body và thông thường chỉ thực sự đọc từ nguồn khi có subscription; đọc/subscribe sai cách có thể tiêu thụ bytes trước khi framework decoder nhìn thấy.

### Đừng nhầm việc lấy Publisher với tiêu thụ Publisher

~~~java
Flux<DataBuffer> publisher = exchange.getRequest().getBody();
~~~

Câu lệnh trên chỉ lấy Publisher. Nhưng:

~~~java
publisher.subscribe();
~~~

đã tạo subscription độc lập. Với request body HTTP, điều này là sai thiết kế nếu mục tiêu chỉ là đọc header.

## 3. WebFilter đứng ở đâu trong WebFlux?

Sơ đồ:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler"]
    B --> C["WebFilter chain"]
    C --> D["ServerWebExchange + ServerHttpRequest"]
    D --> E["DispatcherHandler"]
    E --> F["HandlerMapping / HandlerAdapter"]
    F --> G["HttpMessageReader đọc request body"]
    G --> H["@RequestBody DTO hoặc Mono DTO"]
    H --> I["Controller / Service"]
    I --> J["HttpMessageWriter / ServerHttpResponse"]
    J --> K["HTTP response"]
    C --> L["Đọc/sửa request headers"]
    L --> D
~~~

Filter chạy quanh handler; một WebFilter có thể làm cả logic **trước khi** gọi chain.filter(...) và logic quan sát **sau khi** Publisher hoàn tất/lỗi. Tùy trách nhiệm, WebFilter có thể xử lý access logging, correlation IDs, security metadata hoặc bổ sung response header.

Interface:

~~~java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

Đây là chữ ký minh họa của WebFilter; import Mono tương ứng từ Reactor.

**Không dùng javax.servlet.Filter, jakarta.servlet.Filter hoặc HandlerInterceptor của Spring MVC để thay WebFilter trong reactive web application.** Chúng thuộc Servlet stack, mặc dù đều được gọi là filter/interceptor.

## 4. Đọc headers an toàn mà không đụng body

Một WebFilter chỉ đọc metadata có thể viết:

~~~java
@Component
public final class HeaderObservationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        HttpHeaders headers = exchange.getRequest().getHeaders();
        String contentType = String.valueOf(headers.getContentType());
        String requestId = headers.getFirst("X-Request-Id");

        // Quan sát metadata cần thiết; không log Authorization/Cookie.
        return chain.filter(exchange);
    }
}
~~~

Snippet trên cần imports và có biến contentType/requestId minh họa; không cần một class khác để chuyển body. Quan trọng nhất là filter **không gọi getBody()**.

Các API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| request.getHeaders() | Nhận HttpHeaders |
| headers.getFirst("X-Request-Id") | Đọc một giá trị đầu |
| headers.get("X-Request-Id") | Đọc danh sách các giá trị |
| headers.getContentType() | MediaType request body |
| headers.getAccept() | Danh sách media types client chấp nhận |
| request.getMethod() | HTTP method |
| request.getURI() | URI request |
| request.getId() | ID của ServerHttpRequest theo implementation |

Đọc header không tương đương xác thực giá trị. Client có thể tự gửi X-Request-Id, X-User, Forwarded hay các header tự đặt. Không nên coi chúng là authority nếu không có hạ tầng kiểm tra tin cậy.

## 5. Đọc headers không làm mất JSON body

Ví dụ controller:

~~~java
@PostMapping("/echo")
public Mono<EchoResponse> echo(@RequestBody Mono<EchoRequest> input) {
    return input.map(dto -> new EchoResponse(dto.message()));
}
~~~

Nếu filter chỉ đọc request.getHeaders(), WebFlux vẫn có thể để Jackson JSON decoder subscribe và giải mã body theo bình thường.

Điểm kiểm chứng là request:

~~~http
POST /echo HTTP/1.1
Content-Type: application/json
X-Request-Id: abc123

{"message":"Xin chào"}
~~~

và controller nhận đúng "Xin chào". Không cần copy raw JSON, không cần tự parse body trong WebFilter.

### Content-Type và body không phải một

getHeaders().getContentType() chỉ đọc metadata. Nó không mở JSON parser. Nếu Content-Type không phù hợp với endpoint @PostMapping(consumes=application/json), request có thể nhận 415 trước khi controller decode. Điều này không chứng tỏ filter làm mất body.

Tương tự, Content-Length chỉ là metadata về độ dài được khai báo/nhận từ HTTP layer; đừng dùng nó như một cơ chế bảo đảm body đã đầy đủ hoặc còn nguyên vẹn.

## 6. Bổ sung request header cho handler phía sau

Trong WebFlux, ServerHttpRequest thường được xem là immutable façade của request; đừng tìm cách set trực tiếp vào một HttpHeaders read-only rồi kỳ vọng framework chấp nhận.

Dùng builder:

~~~java
ServerHttpRequest modifiedRequest = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Request-Id", requestId))
        .build();

ServerWebExchange modifiedExchange = exchange.mutate()
        .request(modifiedRequest)
        .build();

return chain.filter(modifiedExchange);
~~~

Đây là code trong method có exchange, chain và requestId; imports nằm trong ví dụ đầy đủ.

**Điểm mấu chốt**: Request builder tạo request được decorate với headers mới, trong khi body Publisher được kế thừa từ request gốc theo cơ chế mutation thông thường. Không có thao tác đọc, copy, join hoặc subscribe body trong đoạn code này.

### Vì sao chọn headers(...).set(...)?

- set(name, value) cho một giá trị header xác định, giúp **thay** giá trị cũ.
- add(name, value) có thể tạo header nhiều giá trị; đôi lúc đúng nhưng không mong muốn với correlation ID chỉ cần một giá trị.
- Với các metadata chỉ dành cho hệ thống như X-Request-Id, nên có một chính sách chuẩn hóa/tạo mới thay vì tích lũy các bản sao từ mỗi filter.

Không dùng mutation cho những header nhạy cảm như Host, Content-Length, Transfer-Encoding hoặc Authorization mà không hiểu HTTP semantics, security trust và proxy topology. Bài học chỉ minh họa X-Request-Id.

## 7. Bổ sung response header: trước khi ghi và trước commit

Nếu muốn client nhận X-Request-Id trong HTTP response, có thể set sớm:

~~~java
exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);
return chain.filter(exchange);
~~~

Khi filter chạy trước controller/response commit, cách này thường hợp lệ.

Với trường hợp muốn gắn metadata ngay sát lúc response commit, dùng beforeCommit:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);
    return Mono.empty();
});

return chain.filter(exchange);
~~~

beforeCommit là một hook **trước** commit, không phải quyền thay status/header **sau** commit. Nếu response đã commit thì header đã gửi không thể được thay bằng một giá trị mới.

### Request header và response header khác nhau

- Request header mới phải được đặt vào **ServerHttpRequest** mà downstream nhìn thấy.
- Response header phải đặt vào **ServerHttpResponse**.
- Việc thêm X-Request-Id vào request không tự bảo đảm nó xuất hiện trong response.
- Việc thêm X-Request-Id vào response không làm controller tự nhìn thấy nó trong @RequestHeader.
- Nếu cần cả hai, làm cả hai theo đúng phạm vi.

## 8. Tại sao body được coi là one-shot?

Với một HTTP request, body là dữ liệu đi tới từ socket hoặc một pipeline transport. WebFlux biểu diễn nó qua Flux<DataBuffer>. Thông thường, framework controller body reader là **consumer chính**. Nó giải mã JSON, multipart hoặc protobuf theo media type rồi tạo DTO/Publisher phù hợp.

Không được giả định Flux<DataBuffer> gốc là replayable hoặc có thể subscribe nhiều lần như Flux.just(...). Mặc dù cả hai cùng là Flux, **nguồn HTTP network có lifecycle và tài nguyên riêng**, đôi khi chỉ cho phép tiêu thụ một lần.

Những hành vi nguy hiểm:

~~~java
exchange.getRequest().getBody().subscribe(
        buffer -> log.debug("body chunk {}", buffer.readableByteCount())
);

return chain.filter(exchange);
~~~

Filter đã tạo một subscriber riêng. Controller bên dưới có thể không còn nhận body, nhận lỗi hoặc gặp race; chưa kể DataBuffer có thể là bộ nhớ pooled cần được quản lý đúng vòng đời.

Một ví dụ khác:

~~~java
DataBuffer joined = DataBufferUtils.join(
        exchange.getRequest().getBody()).block();
~~~

Đây là code **không nên dùng** trong WebFlux filter: block() có thể nghẽn event loop, join tiêu thụ body, và pooled DataBuffer cần release đúng cách. Đoạn này không phải cách “đọc trước rồi trả body lại” an toàn.

## 9. Không tự subscribe và không block

Trong WebFlux, framework là subscriber của Publisher đại diện cho HTTP request processing. WebFilter cần **return** Mono<Void> của chain:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {
    return chain.filter(exchange);
}
~~~

Không làm:

~~~java
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Với cách sai này, framework không còn điều phối đúng completion, error và cancellation. Điều đó có thể khiến response kết thúc quá sớm, lỗi không tới client và tài nguyên bị rò rỉ.

Dù filter không đụng body, một thao tác block() lấy thông tin từ database hay external HTTP call trong event-loop vẫn có thể gây latency và timeout. Nếu yêu cầu header normalization cần I/O, chọn reactive operator/service thích hợp và return chain trong cùng reactive flow.

## 10. WebFilter, HandlerFilterFunction và MVC HandlerInterceptor

| Công cụ | Web stack | Phạm vi chính |
| --- | --- | --- |
| WebFilter | Spring WebFlux | Chuỗi filter quanh WebHandler |
| HandlerFilterFunction | Spring WebFlux functional endpoints | Bao quanh functional HandlerFunction/RouterFunction |
| WebExceptionHandler | Spring WebFlux | Xử lý lỗi trong WebHandler chain |
| jakarta.servlet.Filter | Servlet/Spring MVC | Servlet filter chain |
| OncePerRequestFilter | Servlet/Spring MVC | Filter hỗ trợ cơ chế once-per-request theo dispatch semantics |
| HandlerInterceptor | Spring MVC | Quanh handler execution của MVC |
| @RestControllerAdvice | Cả MVC/WebFlux có semantics khác nhau | Exception handling của annotated controllers |

Để thêm request/response header trong **WebFlux annotated controllers**, WebFilter là lựa chọn phổ biến. Không dùng HandlerInterceptor Servlet rồi kỳ vọng được gọi trong Netty WebFlux runtime.

Trong WebFlux functional routing, HandlerFilterFunction cũng có thể làm logic header cho nhóm routes cụ thể:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().bodyValue("hello"))
        .filter((request, next) -> next.handle(request));
~~~

Đoạn minh họa này cần imports phù hợp và class có Bean method. Nó không làm gì ngoài pass-through; nếu yêu cầu thay HTTP request headers ở mức toàn server, WebFilter vẫn là extension point rõ ràng.

## 11. Thiết kế correlation ID không tin bừa giá trị client

Trong ví dụ thực hành, chính sách là:

- Chấp nhận X-Request-Id nếu có **đúng một giá trị**, chứa 1–64 ký tự ASCII chữ/số, gạch ngang hoặc gạch dưới.
- Nếu thiếu, trùng nhiều giá trị hoặc sai format, tạo UUID mới.
- Đưa giá trị đã chuẩn hóa vào request header để controller đọc được.
- Gắn cùng giá trị vào response header qua beforeCommit.
- Không dùng header do client đưa làm session identity, authentication hay authorization.
- Không log raw value nếu chưa qua validation; tránh log injection và high-cardinality metrics.

Regex:

~~~text
[A-Za-z0-9_-]{1,64}
~~~

Đây là ví dụ quy tắc correlation ID của ứng dụng, **không phải chuẩn W3C traceparent**. Nếu đang dùng Micrometer Tracing hoặc OpenTelemetry, nên để instrumentation tuân thủ trace context chuẩn thay vì tự chế cách thay traceparent/tracestate.

### Nhiều header cùng tên

HttpHeaders.getFirst chỉ trả một giá trị đầu. Nếu client gửi hai dòng X-Request-Id, một filter nên xác định policy rõ thay vì lấy bừa một giá trị. Ví dụ kiểm tra:

~~~java
List<String> values = headers.get("X-Request-Id");

if (values == null || values.size() != 1) {
    // Sinh correlation ID mới thay vì chấp nhận mơ hồ.
}
~~~

Đây là snippet, không phải method hoàn chỉnh. Cần nhớ proxy có thể coalesce các giá trị theo HTTP behavior riêng; validation của ví dụ từ chối dấu phẩy và những ký tự ngoài whitelist.

## 12. Ví dụ Spring Boot 3.3 WebFlux chạy được

Chúng ta viết project:

1. Một WebFilter đọc X-Request-Id, kiểm tra format, thay header hoặc sinh mới.
2. Filter bổ sung cùng X-Request-Id vào HTTP response trước khi commit.
3. Filter **không gọi getBody()**.
4. Một @RestController nhận JSON body qua @RequestBody Mono<EchoRequest>, đồng thời lấy @RequestHeader đã normalize.
5. HTTP integration test chứng minh body giữ nguyên và request/response headers đồng bộ.
6. Test request thiếu hoặc có header invalid.
7. Test malformed JSON nhận lỗi decode mà không có body-consuming logic trong filter.

### 12.1 Cấu trúc

~~~text
header-preserve-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/header/
    │   ├── HeaderDemoApplication.java
    │   ├── CorrelationHeaderFilter.java
    │   └── EchoController.java
    └── test/java/com/example/header/
        └── HeaderPreservationHttpTests.java
~~~

### 12.2 settings.gradle

~~~groovy
rootProject.name = 'header-preserve-demo'
~~~

### 12.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chỉ dùng starter-webflux; nếu đồng thời có spring-boot-starter-web, Spring Boot thường ưu tiên Servlet MVC. Không ép version Reactor Netty/Jackson khác dependency management của Boot.

### 12.4 HeaderDemoApplication.java

~~~java
package com.example.header;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderDemoApplication.class, args);
    }
}
~~~

### 12.5 CorrelationHeaderFilter.java

~~~java
package com.example.header;

import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public final class CorrelationHeaderFilter implements WebFilter {

    private static final String HEADER = "X-Request-Id";
    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = chooseId(
                exchange.getRequest().getHeaders());

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set(HEADER, requestId))
                .build();

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .build();

        updated.getResponse().beforeCommit(() -> {
            updated.getResponse().getHeaders()
                    .set(HEADER, requestId);
            return Mono.empty();
        });

        return chain.filter(updated);
    }

    private static String chooseId(HttpHeaders headers) {
        List<String> values = headers.get(HEADER);

        if (values != null && values.size() == 1
                && values.get(0) != null
                && VALID_ID.matcher(values.get(0)).matches()) {
            return values.get(0);
        }

        return UUID.randomUUID().toString();
    }
}
~~~

**Giải thích từng bước:**

1. getHeaders đọc metadata trực tiếp và không tiêu thụ body.
2. chooseId kiểm tra danh sách values, tránh chọn một giá trị mơ hồ.
3. ServerHttpRequest.mutate().headers(...).build() tạo request decorator mang header đã normalize.
4. ServerWebExchange.mutate().request(request).build() tạo exchange để downstream nhìn thấy request mới.
5. Response.beforeCommit gắn header lúc response chuẩn bị commit.
6. return chain.filter(updated) giữ nguyên reactive lifecycle.
7. Không có getBody(), subscribe(), block(), DataBufferUtils.join hay bản sao raw payload ở filter này.

Header do client gửi là metadata cho correlation; UUID được dùng làm fallback, không phải một cơ chế sinh credential bảo mật theo policy session.

### 12.6 EchoController.java

~~~java
package com.example.header;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class EchoController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoResponse>> echo(
            @RequestBody Mono<EchoRequest> input,
            @RequestHeader("X-Request-Id") String requestId) {

        return input.map(dto -> ResponseEntity.ok(
                new EchoResponse(
                        requestId,
                        dto.message(),
                        dto.message() == null
                                ? 0
                                : dto.message().length())));
    }

    @GetMapping(path = "/id", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<HeaderResponse> id(
            @RequestHeader("X-Request-Id") String requestId) {

        return Mono.just(new HeaderResponse(requestId));
    }
}

record EchoRequest(String message) {
}

record EchoResponse(String requestId, String message, int length) {
}

record HeaderResponse(String requestId) {
}
~~~

Cùng một package có một public class EchoController và các package-private records. Jackson trong Boot 3.3 hỗ trợ Java 17 records.

- @RequestHeader đọc **header từ request đã mutate**.
- @RequestBody Mono<EchoRequest> để framework HTTP codec tự decode JSON từ body Publisher gốc.
- EchoResponse trả lại message và độ dài String tính bằng Java UTF-16 code units; đừng nhầm với số bytes UTF-8 hay số grapheme clusters.
- Nếu requestId thiếu/không hợp lệ, filter tạo một giá trị mới trước khi controller argument resolution.
- Nếu message=null, demo trả length=0; API production thường cần validation riêng nếu yêu cầu message bắt buộc.
- Filter không thực hiện authorization; không dùng requestId làm user ID.

## 13. Integration test bằng WebTestClient trên HTTP thật

File HeaderPreservationHttpTests.java:

~~~java
package com.example.header;

import java.util.Map;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HeaderPreservationHttpTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void validHeaderAndJsonBodyArePreserved() {
        client().post()
                .uri("/api/echo")
                .header("X-Request-Id", "req_123")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "  Hello  "))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Request-Id", "req_123")
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req_123")
                .jsonPath("$.message").isEqualTo("  Hello  ")
                .jsonPath("$.length").isEqualTo(9);
    }

    @Test
    void missingHeaderIsGeneratedButBodySurvives() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "payload"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.message").isEqualTo("payload")
                .jsonPath("$.length").isEqualTo(7)
                .jsonPath("$.requestId").isNotEmpty();
    }

    @Test
    void invalidHeaderIsReplaced() {
        client().post()
                .uri("/api/echo")
                .header("X-Request-Id", "bad id !")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "still intact"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().value("X-Request-Id", value -> {
                    assertThat(value).matches(
                            "[A-Za-z0-9_-]{1,64}");
                    assertThat(value).isNotEqualTo("bad id !");
                })
                .expectBody()
                .jsonPath("$.message").isEqualTo("still intact");
    }

    @Test
    void getWithoutBodyAlsoSeesNormalizedHeader() {
        client().get()
                .uri("/api/id")
                .header("X-Request-Id", "hello_42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("hello_42");
    }

    @Test
    void malformedJsonIsRejectedByCodecNotFilter() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().exists("X-Request-Id");
    }

    @Test
    void unsupportedContentTypeDoesNotBecomeBodyLoss() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not JSON")
                .exchange()
                .expectStatus().isUnsupportedMediaType();
    }
}
~~~

File test có hai imports (Pattern và AssertJ) chỉ một được dùng ở test; unused import có thể xóa mà không ảnh hưởng biên dịch. Java compiler không xem unused import hợp lệ thành lỗi mặc định. Test cố tình không so sánh toàn bộ JSON string vì thứ tự JSON fields không phải contract.

Test RANDOM_PORT sử dụng embedded HTTP server thật, đi qua WebFilter, Jackson decoder, controller và response writer. Đó là cách kiểm chứng có giá trị hơn chỉ gọi new CorrelationHeaderFilter().filter(...) trong unit test.

Các kết quả trong code là **kỳ vọng từ thiết kế**, không phải bằng chứng đã chạy Gradle trên workspace hiện tại.

## 14. Chạy project và kiểm tra bằng cURL

### 14.1 Build và test

Trong thư mục header-preserve-demo:

~~~bash
gradle clean test
~~~

Nếu dự án có Gradle wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

### 14.2 Khởi động

~~~bash
gradle bootRun
~~~

Theo cấu hình thông thường, server dùng port 8080 nếu không bị chiếm hoặc ghi đè.

### 14.3 Request có header hợp lệ

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req_123' \
  -d '{"message":"Hello from client"}'
~~~

Kỳ vọng HTTP 200; response header X-Request-Id: req_123; JSON body tương đương:

~~~json
{
  "requestId": "req_123",
  "message": "Hello from client",
  "length": 17
}
~~~

Độ dài Java String của "Hello from client" là 17 ký tự UTF-16; JSON response có thể đổi thứ tự fields mà không thay semantics.

### 14.4 Request không có header

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":"payload"}'
~~~

Kỳ vọng HTTP 200, response/header body có X-Request-Id được sinh từ UUID. Message "payload" vẫn nguyên, length=7. Giá trị UUID cụ thể sẽ khác mỗi lần nên không được viết assert một giá trị cố định.

### 14.5 Request header không hợp lệ

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: bad id !' \
  -d '{"message":"still intact"}'
~~~

Filter từ chối header có space và !, thay bằng UUID mới. Cả request header downstream và response header đều dùng giá trị đã chuẩn hóa.

### 14.6 JSON malformed

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":'
~~~

HTTP 400 là kết quả thông thường do JSON parser không thể decode body. Không đổ lỗi cho WebFilter chỉ đọc header; cần xem codec exception và request syntax.

## 15. Điều gì xảy ra nếu filter muốn đọc cả body?

Khi chỉ cần header, **không đọc body** là thiết kế tốt nhất. Nhưng có những use case thật sự cần body, như HMAC signature verification, request payload audit theo chính sách, security scanning hoặc custom protocol parsing.

Đây là một bài toán khác, phải giải quyết có ý thức vì Flux<DataBuffer> từ HTTP request không mặc định replayable.

Các hướng triển khai:

1. Di chuyển xử lý tới controller/request DTO hoặc service nếu đủ.
2. Dùng schema-aware HTTP message reader/decoder nếu mục tiêu là validate payload.
3. Dùng API security/framework chuẩn thay vì tự parse Authorization + body.
4. Nếu buộc phải audit/verify raw body trước controller, xây một ServerHttpRequestDecorator có **body replay** và bảo đảm semantics của pooled DataBuffer, bounded memory và cancellation.
5. Nếu chỉ muốn **quan sát số bytes đi qua** mà không cần đọc raw content, có thể decorate getBody() và dùng doOnNext trên cùng Publisher được downstream subscribe, không tạo subscriber thứ hai.

**Không** dùng DataBufferUtils.join(...) rồi gọi chain.filter(exchange) với request gốc: body đã bị tiêu thụ mà không được cấp lại cho downstream.

## 16. Quan sát byte count mà không tiêu thụ body riêng

Trong tình huống nâng cao, muốn đếm kích thước những DataBuffer mà downstream đã request, có thể bọc request Publisher bằng decorator:

~~~java
AtomicLong bytesSeen = new AtomicLong();

ServerHttpRequest counted =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public Flux<DataBuffer> getBody() {
                return super.getBody()
                        .doOnNext(buffer ->
                                bytesSeen.addAndGet(
                                        buffer.readableByteCount()));
            }
        };

ServerWebExchange updated =
        exchange.mutate().request(counted).build();

return chain.filter(updated)
        .doFinally(signal -> log.debug(
                "Observed request bytes={}, signal={}",
                bytesSeen.get(),
                signal));
~~~

Đây là snippet trong WebFilter với imports cho AtomicLong, ServerHttpRequestDecorator, DataBuffer, Flux và log.

Tại sao ví dụ này không đọc mất body?

- Decorator **trả lại cùng dữ liệu Flux<DataBuffer> cho downstream** sau doOnNext.
- Nó không subscribe độc lập.
- Nó chỉ gọi readableByteCount(), không gọi buffer.read(...) để làm thay đổi read position.
- Nó không release DataBuffer sớm.
- Decoder vẫn là subscriber của Publisher được trả về.

Các giới hạn:

- Số bytes quan sát được không nhất thiết bằng số bytes truyền trên wire vì HTTP framing, content encoding và implementation.
- Nếu downstream không đọc body, counter có thể bằng 0.
- Nếu downstream subscribe nhiều lần hoặc pipeline thay đổi, counter có thể đếm lặp.
- doFinally của chain không chứng minh client đã nhận HTTP response.
- Không dùng pattern này để sao chép/log payload nhạy cảm mà không có policy.
- Đừng tạo decorator chỉ để đọc header; trường hợp header thuần đã được giải quyết bằng getHeaders()/mutate() đơn giản hơn.

## 17. Body caching/replay: khi nào cần và những điều bắt buộc

Đối với chữ ký HMAC trên raw request body, một giải pháp có thể phải đọc bytes một lần rồi cấp lại cho decoder. Nhưng làm an toàn cần nhiều điều kiện:

### 17.1 Giới hạn memory trước khi aggregate

DataBufferUtils.join(body, maxByteCount) trong Spring Framework 6.x có thể dùng cho **body hữu hạn, có giới hạn**. Nếu body vượt giới hạn, cần phát lỗi rõ, không cố giữ vô hạn trong heap. Body upload/multipart lớn có thể không phù hợp để buffer.

### 17.2 Ownership và release pooled DataBuffer

Reactor Netty có thể dùng pooled buffers. Khi join/copy/transform DataBuffer, phải quản lý retain/release đúng và không giữ tham chiếu đến buffer đã release. Cần test cancellation, lỗi decode, request empty và payload lớn.

### 17.3 Replay phải cấp lại đúng bytes

Sau khi kiểm tra body, downstream cần nhận **một Publisher mới chứa toàn bộ bytes nguyên vẹn** với các lifecycle semantics thích hợp. Không chỉ gắn attribute rawBody rồi tiếp tục chain vì @RequestBody vẫn sẽ đọc Publisher của request. Không tự gọi subscribe vào nguồn request từ filter.

### 17.4 Không dùng body caching cho mọi request

- Chi phí memory, latency và CPU tăng.
- Streaming/multipart upload có thể mất lợi ích non-blocking.
- JSON chứa dữ liệu nhạy cảm có thể bị giữ lại trong RAM hoặc logs.
- Request body có thể rất lớn, vô hạn hoặc bị client ngắt giữa chừng.
- Một codec cần bảo toàn Content-Type, charset và transfer semantics.
- Đối với HMAC, cần xác định chính xác canonicalization, content encoding, signing scope và thời điểm verify.

Một custom ServerHttpRequestDecorator dùng để replay body phải được kiểm thử bằng HTTP integration, body lớn, early cancellation, concurrent requests và memory leak diagnostics. Bài này **không đưa một body cache giả an toàn**: khi nhiệm vụ chỉ là đọc/thêm header, không cần làm bất kỳ bước nào trong số đó.

## 18. Một kiểu bug phổ biến: log body rồi controller nhận rỗng

Mẫu sai:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    exchange.getRequest().getBody().subscribe(buffer -> {
        // Đã subscribe request body ngoài pipeline chính.
        log.debug("bytes={}", buffer.readableByteCount());
    });

    return chain.filter(exchange);
}
~~~

Vì có hai subscriptions tranh cùng body source, controller có thể nhận lỗi hoặc request body không đúng. Không thể sửa chỉ bằng thêm cache() một cách tùy tiện: cached buffers có thể bị release, giữ vô hạn, hoặc đổi ownership. Đừng nghĩ Flux.cache() tự tạo một HTTP request replayable an toàn với pooled memory.

Cách sửa khi yêu cầu chỉ là metadata:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String contentType =
            String.valueOf(exchange.getRequest()
                    .getHeaders()
                    .getContentType());

    return chain.filter(exchange);
}
~~~

Body sẽ tiếp tục được downstream đọc đúng chỗ.

## 19. Quy tắc với Content-Length, Transfer-Encoding và Content-Type

Header manipulation có thể gây lỗi dù không đụng body nếu bạn sửa những header có ý nghĩa nội dung:

- **Content-Length** phải phù hợp với bytes body thực; đừng tự set số bất kỳ.
- **Transfer-Encoding** thuộc transport/framing, không đặt bừa ở filter ứng dụng.
- **Content-Type** quyết định HTTP codec có thể decode hay không; đừng chuyển application/json sang text/plain chỉ để “sửa” một lỗi khác.
- **Content-Encoding** cho biết compression/encoding; nếu body được decompress/recompress thì metadata phải nhất quán.
- **Host** có ý nghĩa authority/routing/security, không tự thay từ client-controlled header.
- **Authorization/Cookie** là dữ liệu nhạy cảm; không ghi logs hoặc reflect vào response.
- **Forwarded/X-Forwarded-*** chỉ đáng tin khi proxy chain được cấu hình đúng.

X-Request-Id là header metadata có phạm vi nhỏ hơn, nhưng vẫn phải validate và giới hạn độ dài.

## 20. Header security và reverse proxy

Một số tình huống bảo mật:

### 20.1 Client có thể giả X-User và X-Role

Đọc X-User hoặc X-Role không chứng minh ai đã đăng nhập. Nếu gateway xác thực và gắn header nội bộ, gateway phải xóa header người dùng tự gửi rồi chèn giá trị đáng tin. Ứng dụng backend cần giới hạn truy cập trực tiếp vào backend, định nghĩa trust boundary và xác thực mối quan hệ gateway/backend.

### 20.2 X-Forwarded-For có thể không đáng tin

Client có thể gửi header X-Forwarded-For giả. Không lấy getFirst("X-Forwarded-For") rồi coi đó chắc chắn là IP gốc. Với Boot, cấu hình forwarded headers strategy phù hợp topology và chỉ tin những reverse proxy được quản lý.

### 20.3 Correlation ID có thể thành vector log injection

Đừng log nguyên chuỗi không giới hạn do client gửi. Ví dụ whitelist ký tự đơn giản và giới hạn 64 ký tự trong filter giảm rủi ro ký tự xuống dòng/điều khiển. Không gắn raw requestId vào metric labels có cardinality vô hạn.

### 20.4 Header response và CORS

Browser JavaScript đọc custom response header có thể phụ thuộc **Access-Control-Expose-Headers** với CORS. Việc server trả X-Request-Id không bảo đảm JavaScript cross-origin đọc được nó nếu CORS chưa được cấu hình. Tránh tự đặt Access-Control-Allow-Origin: * cùng credential policy không hợp lệ. Dùng CORS configuration phù hợp ở Spring Security hoặc WebFlux config.

## 21. Filter order và phạm vi áp dụng

WebFilter có thể được sắp thứ tự bằng @Order hoặc Ordered. Một số WebFilter thuộc Spring Security hoặc tracing có order riêng, và trách nhiệm của bạn có thể phụ thuộc thứ tự chạy.

Trong project mẫu:

~~~java
@Component
@Order(0)
public final class CorrelationHeaderFilter implements WebFilter {
    // ...
}
~~~

Nếu filter sau cần nhìn thấy request header đã normalize, filter chuẩn hóa phải nằm **trước** filter đó trong chain. Nhưng đừng đoán thứ tự chỉ từ annotation của một filter; hãy xem Spring application context, security chain và integration test trong ứng dụng thực.

Lưu ý:

- Không sửa Authorization theo ý muốn để lừa security context.
- Header chuẩn hóa cho tracing nên phối hợp với Micrometer Tracing/OpenTelemetry.
- Filter registration chỉ nên áp dụng với ứng dụng WebFlux; OncePerRequestFilter dành cho MVC.
- Một WebFilter sẽ bao quanh cả những endpoint thuộc DispatcherHandler hoặc functional route khi nằm trong cùng WebHandler chain.
- Nếu chỉ cần xử lý một số routes, có thể dùng route filters/HandlerFilterFunction thích hợp hoặc kiểm tra path hợp lệ một cách có chủ đích, tránh regex matching tùy tiện.

## 22. Chẩn đoán khi controller không còn đọc được body

### Bước 1: xác định stack

Ứng dụng chạy Servlet MVC hay reactive WebFlux? Nếu có cả starter-web và starter-webflux, Boot thường ưu tiên MVC; WebFilter bạn viết có thể không nằm trong server stack thực tế.

### Bước 2: xem filter có subscribe vào getBody() không

Tìm trong code các pattern:

~~~text
getBody().subscribe(...)
getBody().blockFirst()
getBody().collectList().block()
DataBufferUtils.join(request.getBody())
buffer.read(...)
DataBufferUtils.release(buffer)
~~~

Một số API là hợp lệ trong **đúng ngữ cảnh có ownership**, nhưng nếu chúng xuất hiện trong header-only WebFilter cần điều tra ngay.

### Bước 3: xem body đã được decorate đúng chưa

Nếu một filter thực sự đọc và cache body, downstream có nhận một ServerHttpRequestDecorator với getBody() được triển khai đúng không? Có memory limit, release và cancellation handling chưa?

### Bước 4: phân biệt lỗi HTTP codec

HTTP 400 do JSON malformed, 415 do Content-Type sai, 413/size limit, 401/403 do security, 404 route không match và 500 server error có nguyên nhân khác. Không kết luận body mất chỉ từ mã status.

### Bước 5: kiểm tra Content-Length/Content-Encoding

Một filter hoặc proxy sửa metadata không nhất quán có thể làm codec đọc sai dù raw body tồn tại. Hãy kiểm tra request thực tế trước và sau gateway.

### Bước 6: kiểm thử bằng HTTP thật

Gửi JSON có một chuỗi đặc trưng, assert response echo giữ nguyên. Thử header hợp lệ, thiếu, không hợp lệ, body lớn vừa phải, Unicode và malformed JSON; với multipart upload cần test riêng.

### Bước 7: dùng logging có kiểm soát

Không bật Netty wiretap rộng cho production nếu payload chứa token/PII. Có thể bật debug cho handler mapping và codec theo phạm vi cần thiết mà không dump toàn bộ body.

## 23. Spring MVC/Servlet tương ứng

Nếu hệ thống dùng spring-boot-starter-web và DispatcherServlet, filter phổ biến là OncePerRequestFilter:

~~~java
@Component
public class RequestIdServletFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String id = request.getHeader("X-Request-Id");
        response.setHeader(
                "X-Request-Id",
                id == null ? "server-generated" : id);

        filterChain.doFilter(request, response);
    }
}
~~~

Đây là snippet cần imports: org.springframework.stereotype.Component, org.springframework.web.filter.OncePerRequestFilter, jakarta.servlet.FilterChain, jakarta.servlet.ServletException, jakarta.servlet.http.HttpServletRequest/HttpServletResponse và java.io.IOException.

Trong Servlet, request.getHeader không đọc ServletInputStream. Nhưng nếu muốn **bổ sung request header** để downstream getHeader thấy giá trị mới, HttpServletRequest bản gốc không có setHeader thông thường; cần HttpServletRequestWrapper đúng cách. Thêm response.setHeader không đồng nghĩa chỉnh được request.getHeader.

**ContentCachingRequestWrapper** cache dữ liệu khi body được đọc, nhưng không mặc nhiên biến getInputStream() thành nguồn đọc lại từ đầu nhiều lần. Nếu bạn thật sự cần replay input stream, cần wrapper triển khai lại đúng contract. Đừng port code Servlet body wrappers thẳng sang WebFlux; hai hệ có resource/cancellation/async semantics khác.

## 24. Kiểm thử các tình huống cạnh

Bên cạnh test chính, một hệ thống sản xuất nên kiểm tra:

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Không có X-Request-Id | Server tạo ID hợp lệ và trả về |
| Hai header cùng tên | Policy từ chối hoặc xử lý rõ |
| X-Request-Id rất dài | Bị từ chối/tạo ID mới, không lộ vào log |
| Header chứa ký tự điều khiển | HTTP server có thể từ chối request trước filter; không log raw |
| JSON có Unicode | Body/charset không bị đổi |
| JSON nested và arrays | Jackson vẫn parse bình thường |
| Empty body với @RequestBody required | Error contract rõ, không do filter tiêu thụ |
| Multipart/file upload | Streaming hoạt động và không buffer vô hạn |
| SSE response | Header được gắn trước commit, không can thiệp output stream |
| Client disconnect giữa upload | Không rò rỉ subscription/buffers |
| CORS cross-origin | Browser được phép đọc custom response header nếu cần |
| Spring Security | Header không bị dùng như nguồn authority chưa xác thực |
| Reverse proxy | Forwarded headers/correlation policy phối hợp đúng |
| Concurrent requests | Không giữ requestId trong field mutable singleton |
| Content-Encoding/compression | Không sửa body metadata bất nhất |

Đặc biệt, filter là singleton bean theo ứng dụng, vì vậy **không** lưu requestId vào một field mutable dùng chung. Hãy giữ nó trong biến local per request hoặc exchange attributes/Reactor Context khi có mục đích rõ.

## 25. Những lỗi thiết kế phổ biến và cách sửa

**Lỗi 1 — getBody().subscribe() để log:** tạo subscriber thứ hai, body có thể không còn cho controller. Sửa: chỉ getHeaders() nếu nhu cầu là metadata.

**Lỗi 2 — block() trong WebFilter:** gây nghẽn event loop và tiêu thụ request body nếu block trên body Publisher. Sửa: return chain reactive, tránh synchronous I/O.

**Lỗi 3 — join body rồi bỏ request gốc:** downstream @RequestBody không còn bytes để decode. Sửa: chỉ dùng body replay decorator có giới hạn và lifecycle rõ nếu thật sự cần.

**Lỗi 4 — tự release pooled DataBuffer:** có thể gây downstream đọc buffer đã release. Sửa: giữ ownership semantics, không release buffer bạn chỉ pass-through.

**Lỗi 5 — buffer.read(...) để “ngó” bytes:** thao tác read có thể thay đổi read position, làm downstream thiếu dữ liệu. Sửa: tránh đọc, hoặc dùng phương pháp quan sát đúng API mà không đổi position và không giữ buffer sau lifecycle.

**Lỗi 6 — sửa HttpHeaders trực tiếp trên request read-only:** có thể ném UnsupportedOperationException hoặc không có hiệu lực. Sửa: ServerHttpRequest.mutate().headers(...), chain.filter(exchange mới).

**Lỗi 7 — thêm header vào response và mong controller đọc được:** hai hướng request/response khác nhau. Sửa: mutate request để handler nhìn thấy, beforeCommit để client nhìn thấy.

**Lỗi 8 — sửa response header sau commit:** status/headers đã được gửi, thay map Java không thay wire response. Sửa: set sớm hoặc beforeCommit.

**Lỗi 9 — append nhiều X-Request-Id không kiểm soát:** tạo ambiguity và khác biệt proxy. Sửa: chính sách một giá trị dùng headers.set.

**Lỗi 10 — tin X-User/X-Forwarded-For do client gửi:** có thể gây authorization spoofing. Sửa: xác định trusted gateway/proxy và security context.

**Lỗi 11 — gọi chain.filter(...).subscribe rồi return Mono.empty:** framework mất lifecycle và error propagation. Sửa: return chain.filter(...).

**Lỗi 12 — test chỉ gọi controller method trực tiếp:** không xác minh filter hoặc Jackson decoder. Sửa: WebTestClient HTTP trên RANDOM_PORT.

**Lỗi 13 — nghĩ malformed JSON là body bị mất:** request parser có thể tự fail. Sửa: kiểm tra Content-Type, status và codec exception.

**Lỗi 14 — cố cache mọi upload:** memory và latency tăng, dễ leak và phá streaming. Sửa: chỉ cache bounded payload thật sự cần; tách policy cho multipart/large streams.

**Lỗi 15 — coi X-Request-Id là authentication:** correlation ID không chứng minh danh tính. Sửa: dùng Spring Security, authn/authz riêng.

## 26. Checklist triển khai

- [ ] Xác nhận server thực sự chạy WebFlux.
- [ ] Dùng WebFilter thay Servlet Filter/HandlerInterceptor nếu ở reactive stack.
- [ ] Header-only filter chỉ gọi getHeaders(), không consume getBody().
- [ ] Đăng ký request header qua ServerHttpRequest.mutate nếu downstream cần nhìn thấy.
- [ ] Dùng ServerWebExchange.mutate().request(...) để truyền đúng request.
- [ ] Dùng headers.set cho single-value metadata có policy rõ.
- [ ] Đăng ký response.beforeCommit trước chain khi cần response header.
- [ ] Return chain.filter(...), không tự subscribe/block.
- [ ] Header client được validate/giới hạn chiều dài và không dùng làm auth.
- [ ] Không sửa Content-Length, Host, Transfer-Encoding tùy tiện.
- [ ] Không giữ request data trong singleton mutable field.
- [ ] Không log Authorization/Cookie/raw body tràn lan.
- [ ] Nếu cần body, có bounded caching/replay và DataBuffer ownership đúng.
- [ ] Test giữ nguyên JSON body qua WebTestClient HTTP thật.
- [ ] Test missing/invalid/duplicate request headers.
- [ ] Kiểm tra multipart/stream/cancel nếu ứng dụng có dùng.
- [ ] Đảm bảo CORS expose custom response header nếu browser cần đọc.
- [ ] Xác nhận Spring Security/tracing filters phối hợp đúng thứ tự.

## 27. Tóm tắt

Trong Spring Boot WebFlux, **đọc headers và tiêu thụ body là hai việc độc lập**. WebFilter có thể lấy request.getHeaders(), chuẩn hóa một header bằng ServerHttpRequest.mutate(), đưa request mới vào ServerWebExchange.mutate(), rồi thêm response header trong beforeCommit mà **không hề subscribe request.getBody()**. Khi đó HTTP message reader của WebFlux vẫn nhận và giải mã body theo cơ chế bình thường.

Body là Flux<DataBuffer> gắn với network lifecycle, không phải một mảng byte replayable mặc định. Việc subscribe, block, join hoặc đọc/release DataBuffer sớm có thể làm controller mất body, hỏng decoding hoặc rò rỉ tài nguyên. Chỉ triển khai body caching/replay khi nghiệp vụ thực sự yêu cầu, với giới hạn bộ nhớ, quản lý pooled buffer và kiểm thử lỗi/cancellation.

Ví dụ CorrelationHeaderFilter và EchoController minh họa đúng điểm mở rộng: **header được đọc/sửa nhưng JSON body giữ nguyên**, request và response dùng cùng X-Request-Id, còn WebTestClient kiểm chứng điều đó trên HTTP thật.

## 28. Tài liệu tham khảo

- Spring Framework — WebFlux Web Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework 6.1 — WebFilter API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework 6.1 — ServerHttpRequest API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework 6.1 — ServerHttpRequestDecorator API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html
- Spring Framework 6.1 — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.1 — ServerHttpResponse API / beforeCommit: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Security — Reactive Web Applications: https://docs.spring.io/spring-security/reference/reactive/index.html
- Reactor Core — Reference Guide: https://projectreactor.io/docs/core/release/reference/
- HTTP Semantics — RFC 9110: https://www.rfc-editor.org/rfc/rfc9110
