# MockServerHttpRequest, MockServerHttpResponse và MockServerWebExchange

Khi kiểm thử ứng dụng Spring WebFlux, nhiều thành phần xử lý request và response theo mô hình reactive mà không cần chạy một HTTP server thật. Để kiểm tra các thành phần này ở mức unit test, Spring Test cung cấp ba đối tượng mô phỏng quan trọng: `MockServerHttpRequest`, `MockServerHttpResponse` và `MockServerWebExchange`.

Ba lớp này cho phép tạo một request HTTP trong bộ nhớ, quan sát response được ghi ra và đặt cả hai vào một exchange giống với đối tượng mà WebFlux chuyển qua các `WebFilter` và `WebHandler`. Nhờ vậy, ta có thể kiểm tra logic xử lý ở tầng WebFlux trực tiếp bằng JUnit mà không cần mở port, gửi request qua mạng hoặc khởi động toàn bộ ứng dụng.

## 1. Vai trò của ba đối tượng mock

Trong WebFlux, `ServerHttpRequest` đại diện cho request phía server, `ServerHttpResponse` đại diện cho response phía server và `ServerWebExchange` gom request, response cùng ngữ cảnh của một lần trao đổi HTTP.

| Lớp mock | Package | Mô phỏng | Khi nào dùng |
|---|---|---|---|
| `MockServerHttpRequest` | `org.springframework.mock.http.server.reactive` | Một request server reactive | Tạo method, URI, header, cookie và body đầu vào |
| `MockServerHttpResponse` | `org.springframework.mock.http.server.reactive` | Một response server reactive | Đặt status, header, cookie và kiểm tra body được ghi |
| `MockServerWebExchange` | `org.springframework.mock.web.server` | Một HTTP exchange hoàn chỉnh | Kiểm thử `WebFilter`, `WebHandler` và thành phần nhận `ServerWebExchange` |

Các lớp này thuộc module `spring-test`. Chúng triển khai các contract của Spring WebFlux, do đó mã production có thể nhận interface `ServerHttpRequest`, `ServerHttpResponse` hoặc `ServerWebExchange`; test truyền implementation mock vào mà không phải thay đổi mã production.

Luồng xử lý có thể hình dung như sau:

```text
MockServerHttpRequest
          |
          v
   MockServerWebExchange
       /          \
      v            v
 request        response
                  |
                  v
        MockServerHttpResponse
                  ^
                  |
       WebFilter / WebHandler
```

`MockServerWebExchange` chứa request và response. Trong phần lớn test, ta chỉ cần tạo request rồi gọi `MockServerWebExchange.from(request)` để nhận exchange có response mock đi kèm.

## 2. Chuẩn bị dependency kiểm thử

Nếu ứng dụng đã dùng Spring WebFlux, các interface reactive và Reactor đã có trong dependency chính. Các lớp mock nằm trong `spring-test`, vì vậy cần dependency test tương ứng.

Ví dụ với Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webflux")
    testImplementation("io.projectreactor:reactor-test")
}
```

Trong ứng dụng thực tế, `spring-webflux` thường đã được khai báo ở cấu hình `implementation`; không cần khai báo lại trong `testImplementation` nếu test đã nhận được nó qua test runtime classpath. `reactor-test` chỉ cần khi dùng `StepVerifier` hoặc tiện ích kiểm thử Reactor khác. Hãy để Spring BOM hoặc dependency management hiện có quản lý phiên bản Spring đồng bộ.

Nếu dự án dùng Spring Boot, `spring-boot-starter-test` thường đã cung cấp `spring-test` và JUnit Jupiter. Ứng dụng vẫn cần dependency WebFlux nếu đang kiểm thử các contract reactive của WebFlux.

Các import thường gặp:

```java
import org.springframework.http.HttpCookie;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
```

## 3. Tạo request bằng MockServerHttpRequest

`MockServerHttpRequest` cung cấp các factory method để tạo request với HTTP method thường dùng. Sau khi cấu hình các thuộc tính, gọi `build()` để tạo đối tượng request.

### 3.1. Tạo request GET đơn giản

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/orders/42")
        .build();
```

Có thể đọc các thông tin cơ bản qua contract `ServerHttpRequest`:

```java
assertEquals(HttpMethod.GET, request.getMethod());
assertEquals("/api/orders/42", request.getURI().getPath());
```

Request mock không gửi dữ liệu qua socket. URI chỉ là thông tin request mà thành phần được kiểm thử nhìn thấy.

### 3.2. Cấu hình method, URI và query parameter

Có thể tạo request bằng method tường minh khi cần kiểm thử một HTTP method ít dùng:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .method(HttpMethod.PATCH, "/api/orders/42?notify=false")
        .build();
```

Query string được phân tích thành `MultiValueMap`:

```java
assertEquals("false", request.getQueryParams().getFirst("notify"));
```

Khi có nhiều giá trị cùng tên, ví dụ `?tag=java&tag=spring`, `getQueryParams()` giữ các giá trị trong danh sách. Test nên xác minh đúng quy tắc mà controller hoặc filter cần dùng: lấy giá trị đầu tiên, xử lý tất cả giá trị hay từ chối tham số lặp.

### 3.3. Thêm header và cookie

Header có thể được thêm qua builder:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/profile")
        .header("X-Request-Id", "req-100")
        .header("X-Feature", "preview")
        .build();

assertEquals("req-100", request.getHeaders().getFirst("X-Request-Id"));
```

Để thêm cookie, dùng `HttpCookie`:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/profile")
        .cookie(new HttpCookie("SESSION", "session-value"))
        .build();

assertEquals("session-value", request.getCookies()
        .getFirst("SESSION").getValue());
```

Header và cookie là hai cơ chế riêng. Cookie của request được gửi trong header `Cookie`, nhưng Spring cung cấp API cookie để test và mã ứng dụng thao tác theo tên/value mà không phải tự phân tích chuỗi header.

### 3.4. Tạo request có body

Với POST, PUT hoặc PATCH, có thể đặt content type và body ngay trên builder:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-101")
        .body("""
                {
                  "productId": 42,
                  "quantity": 2
                }
                """);
```

`body(String)` tạo body dạng text cho request mock. Nếu cần kiểm tra nội dung nhị phân hoặc encoding đặc biệt, hãy dựng `DataBuffer` theo đúng kiểu dữ liệu và content type cần mô phỏng.

Thông tin request có thể được xác minh như sau:

```java
assertEquals(HttpMethod.POST, request.getMethod());
assertEquals(MediaType.APPLICATION_JSON, request.getHeaders().getContentType());
assertEquals("req-101", request.getHeaders().getFirst("X-Request-Id"));
```

Body được cung cấp qua `getBody()` dưới dạng `Flux<DataBuffer>`, không phải `String` đồng bộ. Khi test cần đọc body trực tiếp, phải subscribe hoặc thu thập publisher và giải phóng `DataBuffer` sau khi đọc.

### 3.5. Đọc body của request một cách an toàn

Ví dụ sau gom body thành một `DataBuffer`, đọc bytes rồi giải phóng buffer:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.server.reactive.ServerHttpRequest;

private String readBody(ServerHttpRequest request) {
    DataBuffer buffer = DataBufferUtils.join(request.getBody()).block();
    if (buffer == null) {
        return "";
    }

    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    } finally {
        DataBufferUtils.release(buffer);
    }
}
```

Trong test:

```java
assertTrue(readBody(request).contains("\"productId\": 42"));
```

`DataBufferUtils.join` gom các buffer trong publisher thành một buffer tổng hợp. Phải giải phóng buffer sau khi đọc để tránh rò rỉ tài nguyên, đặc biệt khi implementation sử dụng pooled buffer. Với request body được xử lý bởi một handler thật, thường nên để handler đọc body thay vì test tự tiêu thụ trước, vì body là một luồng có thể không replay được.

### 3.6. Các thuộc tính request khác

Tùy test case, request builder có thể mô phỏng thêm thông tin như địa chỉ remote/local, SSL metadata và context path. Các thuộc tính này hữu ích khi kiểm thử logic phụ thuộc địa chỉ client, giao thức bảo mật hoặc đường dẫn ứng dụng.

Không nên đặt mọi header, cookie hoặc địa chỉ vào mọi test. Chỉ cấu hình dữ liệu có ảnh hưởng đến hành vi đang kiểm thử; fixture càng nhỏ thì nguyên nhân thất bại càng dễ nhận biết.

## 4. Dùng MockServerHttpResponse để quan sát response

`MockServerHttpResponse` là implementation mock của `ServerHttpResponse`. Thông thường, ta lấy response từ exchange để bảo đảm request và response thuộc cùng một lần trao đổi.

```java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders").build());

MockServerHttpResponse response = exchange.getResponse();
```

### 4.1. Kiểm tra status và header

Response có thể được cấu hình bằng các API của `ServerHttpResponse`:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().set("X-Request-Id", "req-101");

assertEquals(HttpStatus.CREATED, response.getStatusCode());
assertEquals(MediaType.APPLICATION_JSON, response.getHeaders().getContentType());
assertEquals("req-101", response.getHeaders().getFirst("X-Request-Id"));
```

Trong các phiên bản Spring mới, kiểu trả về của `getStatusCode()` là `HttpStatusCode`; `HttpStatus` là một implementation cụ thể. Có thể so sánh trực tiếp với hằng `HttpStatus` tương ứng.

### 4.2. Ghi body reactive

Response body được ghi bằng publisher của `DataBuffer`. Ví dụ:

```java
import java.nio.charset.StandardCharsets;

import reactor.core.publisher.Mono;

response.setStatusCode(HttpStatus.OK);
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

byte[] bytes = "order accepted".getBytes(StandardCharsets.UTF_8);
Mono<Void> writeResult = response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes)));

writeResult.block();
```

Trong unit test, gọi `block()` tại ranh giới test giúp chờ thao tác reactive hoàn tất trước khi assertion. Không nên chuyển cách làm này sang mã production của WebFlux; trong ứng dụng, hãy tiếp tục trả về và kết hợp `Mono`/`Flux` để giữ luồng không blocking.

### 4.3. Đọc body đã ghi

`MockServerHttpResponse` cung cấp tiện ích `getBodyAsString()` để lấy nội dung body dưới dạng `Mono<String>`:

```java
String body = response.getBodyAsString().block();

assertEquals("order accepted", body);
```

Đặt content type/charset phù hợp nếu body không dùng UTF-8 mặc định. Với JSON, có thể kiểm tra chuỗi JSON, parse thành DTO hoặc dùng JSON assertion phù hợp với dự án. Tránh kiểm tra toàn bộ chuỗi nếu thứ tự field hoặc khoảng trắng không thuộc hợp đồng response.

### 4.4. Kiểm tra cookie trong response

Response cookie được biểu diễn bằng `ResponseCookie`:

```java
import org.springframework.http.ResponseCookie;

response.addCookie(ResponseCookie.from("SESSION", "new-session")
        .httpOnly(true)
        .secure(true)
        .path("/")
        .build());

ResponseCookie cookie = response.getCookies().getFirst("SESSION");
assertNotNull(cookie);
assertTrue(cookie.isHttpOnly());
assertTrue(cookie.isSecure());
assertEquals("/", cookie.getPath());
```

Cookie có thể mang thông tin bảo mật như `HttpOnly`, `Secure`, `SameSite`, `Path` và `Max-Age`. Khi kiểm thử session hoặc authentication, hãy xác minh những thuộc tính bắt buộc theo chính sách ứng dụng. Không nên chỉ kiểm tra cookie có tồn tại mà bỏ qua cờ bảo mật.

### 4.5. Hoàn tất response không có body

Với response rỗng, có thể gọi `setComplete()`:

```java
response.setStatusCode(HttpStatus.NO_CONTENT);
response.setComplete().block();

assertEquals(HttpStatus.NO_CONTENT, response.getStatusCode());
```

Đây là cách mô phỏng endpoint trả `204 No Content` hoặc filter hoàn tất response mà không ghi body. Nếu hợp đồng yêu cầu body rỗng, có thể kiểm tra body sau khi hoàn tất theo API của mock response.

## 5. Kết hợp request và response bằng MockServerWebExchange

`MockServerWebExchange` triển khai `ServerWebExchange`, là đối tượng trung tâm được truyền qua WebFlux. Nó giữ request, response và một số ngữ cảnh bổ sung như attributes, session và principal.

### 5.1. Tạo exchange từ request

Cách đơn giản nhất:

```java
MockServerHttpRequest request = MockServerHttpRequest
        .get("/api/orders/42")
        .header("X-Request-Id", "req-102")
        .build();

MockServerWebExchange exchange = MockServerWebExchange.from(request);
```

Sau đó có thể truy cập cả hai phía:

```java
assertEquals("/api/orders/42", exchange.getRequest().getURI().getPath());
assertNotNull(exchange.getResponse());
```

`from(request)` tạo exchange mock với response và các thành phần hỗ trợ mặc định cần thiết cho nhiều test đơn giản. Nếu test cần session manager, principal hoặc locale context đặc biệt, có thể dùng builder của `MockServerWebExchange` để cung cấp cấu hình phù hợp với phiên bản Spring đang sử dụng.

### 5.2. Exchange attributes

`ServerWebExchange` có map attributes để các filter và handler chia sẻ dữ liệu trong phạm vi một request. Test có thể đặt hoặc kiểm tra attribute:

```java
exchange.getAttributes().put("tenantId", "tenant-42");

assertEquals("tenant-42", exchange.getAttribute("tenantId"));
```

Một `WebFilter` có thể đặt correlation id, tenant, thông tin tracing hoặc kết quả phân giải locale vào attributes. Khi kiểm thử, nên xác minh key và giá trị thực sự được downstream handler sử dụng, tránh phụ thuộc vào một attribute nội bộ không thuộc hợp đồng của thành phần.

### 5.3. WebSession

Exchange cung cấp session qua `getSession()`, trả về `Mono<WebSession>`. Test có thể chờ session được tạo và kiểm tra attributes:

```java
WebSession session = exchange.getSession().block();
assertNotNull(session);

session.getAttributes().put("userId", "user-42");

WebSession sameSession = exchange.getSession().block();
assertEquals("user-42", sameSession.getAttribute("userId"));
```

Session là reactive nên không được lấy trực tiếp như một object đồng bộ từ exchange. Khi test cần xác minh việc lưu session hoặc phát hành session id, cần xét thêm session manager/store và response cookie theo cấu hình cụ thể.

### 5.4. Principal và locale context

`ServerWebExchange` cung cấp principal qua `getPrincipal()` dưới dạng `Mono`. Trong test có thể dùng exchange builder để cấu hình principal phù hợp hoặc kiểm thử filter với một exchange đã được thiết lập principal.

Locale context được truy cập qua `getLocaleContext()`. Nếu logic phụ thuộc locale, hãy cố định locale trong test và khôi phục mọi trạng thái theo thread sau khi hoàn tất. Không nên để test phụ thuộc locale mặc định của máy chạy.

### 5.5. Form data và multipart data

Exchange cũng cung cấp API reactive để truy cập form data và multipart data:

- `getFormData()` trả về `Mono<MultiValueMap<String, String>>`.
- `getMultipartData()` trả về `Mono<MultiValueMap<String, Part>>`.

Những API này có thể cần body reader/codec tương ứng. Khi mục tiêu là kiểm tra parser hoặc controller binding, hãy bảo đảm test dùng cấu hình codec giống phạm vi cần xác minh. `MockServerWebExchange` tạo môi trường trao đổi HTTP trong bộ nhớ, nhưng không tự động chứng minh mọi codec hay cấu hình của ứng dụng thật đã được đăng ký.

## 6. Kiểm thử WebFilter bằng mock exchange

`WebFilter` nhận `ServerWebExchange` và `WebFilterChain`. Nó có thể đọc request, thêm attribute/header, chặn request hoặc chuyển tiếp tới filter tiếp theo.

Ví dụ một filter sao chép correlation id từ request sang response:

```java
import org.springframework.http.HttpStatus;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public class CorrelationIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String correlationId = exchange.getRequest()
                .getHeaders().getFirst("X-Correlation-Id");

        if (!StringUtils.hasText(correlationId)) {
            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        exchange.getAttributes().put("correlationId", correlationId);
        exchange.getResponse().getHeaders()
                .set("X-Correlation-Id", correlationId);

        return chain.filter(exchange);
    }
}
```

Unit test có thể cung cấp một `WebFilterChain` giả dưới dạng lambda. Chain chỉ cần trả về một `Mono<Void>` và có thể ghi nhận rằng nó được gọi:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.WebFilterChain;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class CorrelationIdWebFilterTest {

    private final CorrelationIdWebFilter filter = new CorrelationIdWebFilter();

    @Test
    void copiesCorrelationIdAndContinuesChain() {
        var request = MockServerHttpRequest.get("/api/orders")
                .header("X-Correlation-Id", "trace-42")
                .build();
        var exchange = MockServerWebExchange.from(request);
        var chainCalled = new AtomicBoolean(false);

        WebFilterChain chain = nextExchange -> {
            chainCalled.set(true);
            nextExchange.getResponse().setStatusCode(HttpStatus.OK);
            return nextExchange.getResponse().setComplete();
        };

        filter.filter(exchange, chain).block();

        assertTrue(chainCalled.get());
        assertEquals("trace-42", exchange.getAttribute("correlationId"));
        assertEquals("trace-42", exchange.getResponse()
                .getHeaders().getFirst("X-Correlation-Id"));
        assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
    }

    @Test
    void rejectsRequestWithoutCorrelationId() {
        var request = MockServerHttpRequest.get("/api/orders").build();
        var exchange = MockServerWebExchange.from(request);
        var chainCalled = new AtomicBoolean(false);
        WebFilterChain chain = nextExchange -> {
            chainCalled.set(true);
            return nextExchange.getResponse().setComplete();
        };

        filter.filter(exchange, chain).block();

        assertFalse(chainCalled.get());
        assertEquals(HttpStatus.BAD_REQUEST, exchange.getResponse().getStatusCode());
    }
}
```

Test thứ nhất kiểm tra filter đọc đúng header, đặt attribute, ghi response header và chuyển tiếp chain. Test thứ hai xác minh request thiếu dữ liệu bị chặn trước khi chain được gọi. Hai trường hợp đại diện cho hai nhánh hành vi quan trọng của filter.

Nếu muốn kiểm tra publisher mà không gọi `block()`, có thể dùng `StepVerifier`:

```java
StepVerifier.create(filter.filter(exchange, chain))
        .verifyComplete();
```

`StepVerifier` phù hợp để kiểm tra hoàn tất, lỗi hoặc thứ tự tín hiệu của `Mono`/`Flux`. Với một filter chỉ trả về `Mono<Void>`, `verifyComplete()` xác nhận luồng kết thúc bình thường.

## 7. Kiểm thử WebHandler

`WebHandler` là contract xử lý exchange ở tầng thấp của WebFlux. Nó nhận một `ServerWebExchange` và trả về `Mono<Void>` khi xử lý hoàn tất.

Ví dụ handler trả về văn bản:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebHandler;

import reactor.core.publisher.Mono;

public class HealthWebHandler implements WebHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.OK);
        exchange.getResponse().getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] body = "healthy".getBytes(StandardCharsets.UTF_8);
        return exchange.getResponse().writeWith(
                Mono.just(exchange.getResponse().bufferFactory().wrap(body)));
    }
}
```

Test handler:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HealthWebHandlerTest {

    @Test
    void writesHealthResponse() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/health").build());

        new HealthWebHandler().handle(exchange).block();

        assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
        assertEquals("healthy", exchange.getResponse().getBodyAsString().block());
    }
}
```

Ở đây, handler được gọi trực tiếp nên test tập trung vào logic xử lý exchange. Nếu cần xác minh routing, filter chain, codec, exception handler hoặc cấu hình WebFlux của ứng dụng, cần một integration test rộng hơn.

## 8. Kiểm thử component phụ thuộc vào ServerWebExchange

Không chỉ `WebFilter` và `WebHandler` mới dùng exchange. Các resolver, security component, locale handler và logic tiện ích có thể nhận `ServerWebExchange` để truy cập request, session, principal hoặc attributes.

Một ví dụ component đọc tenant id từ header và đặt vào exchange:

```java
public class TenantResolver {

    public String resolve(ServerWebExchange exchange) {
        String tenantId = exchange.getRequest()
                .getHeaders().getFirst("X-Tenant-Id");

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant id is required");
        }

        return tenantId.trim();
    }
}
```

Test có thể tạo exchange với các header khác nhau:

```java
@Test
void trimsTenantId() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/resource")
                    .header("X-Tenant-Id", " tenant-a ")
                    .build());

    assertEquals("tenant-a", new TenantResolver().resolve(exchange));
}

@Test
void rejectsMissingTenantId() {
    var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/resource").build());

    assertThrows(IllegalArgumentException.class,
            () -> new TenantResolver().resolve(exchange));
}
```

Đối với component chỉ đọc dữ liệu từ exchange, cách này thường đủ. Nếu component còn phụ thuộc bean, security context hoặc các filter trước đó, test nên dựng đúng dependency hoặc dùng một context nhỏ để mô phỏng chuỗi tích hợp.

## 9. Phân biệt mock exchange với MockMvc và WebTestClient

Spring có nhiều công cụ kiểm thử web. Chúng phục vụ các tầng khác nhau và không thay thế hoàn toàn cho nhau.

| Công cụ | Nền tảng | Phạm vi phù hợp |
|---|---|---|
| `MockServerHttpRequest` / `MockServerHttpResponse` / `MockServerWebExchange` | WebFlux reactive | Unit test filter, handler hoặc component làm việc trực tiếp với contract server reactive |
| `MockMvc` | Spring MVC / Servlet | Kiểm thử controller MVC qua `DispatcherServlet` trong môi trường mock Servlet |
| `WebTestClient` | WebFlux và có thể dùng với MVC | Kiểm thử HTTP ở mức client; có thể bind tới controller, application context hoặc server thật |

Không dùng `MockServerWebExchange` để thay thế `MockHttpServletRequest` của Spring MVC. Hai bộ API phản ánh hai contract server khác nhau: Servlet là mô hình request/response đồng bộ dựa trên Servlet API; WebFlux dùng `ServerHttpRequest`, `ServerHttpResponse` và reactive streams.

`WebTestClient` phù hợp khi muốn gửi request theo cách gần với client HTTP và kiểm tra response theo chuỗi fluent API. Nó có thể bind tới controller hoặc context mà không cần server thật, hoặc kết nối server chạy thực tế. Mock exchange phù hợp hơn khi muốn gọi trực tiếp một filter/handler và kiểm tra cách component thao tác trên exchange.

Ví dụ quyết định lựa chọn:

- Kiểm tra một filter thêm header: dùng `MockServerWebExchange`.
- Kiểm tra một `WebHandler` ghi status/body: dùng `MockServerWebExchange`.
- Kiểm tra mapping route, serialization và exception handling của WebFlux: cân nhắc `WebTestClient`.
- Kiểm tra controller Spring MVC: dùng `MockMvc`.
- Kiểm tra hành vi qua socket, server connector và môi trường mạng thật: dùng test khởi chạy server phù hợp.

## 10. Những giới hạn cần hiểu khi dùng mock exchange

Mock exchange mô phỏng contract của WebFlux trong bộ nhớ. Nó không tái tạo toàn bộ hành vi của server connector hoặc hạ tầng mạng.

Các điểm cần lưu ý:

- Không có socket thực, TLS handshake thực hoặc kết nối client thật.
- Không tự xác minh cấu hình Netty, Reactor Netty, server timeout hay connection pool.
- Không tự chứng minh toàn bộ route mapping, codec và filter chain của ứng dụng đã được đăng ký đúng.
- Request body là reactive stream; việc test tiêu thụ body trước handler có thể làm thay đổi hành vi mà handler nhìn thấy.
- DataBuffer có thể cần được giải phóng đúng cách khi test tự đọc hoặc tạo buffer.
- Session, principal, locale và attributes cần được thiết lập rõ ràng nếu logic phụ thuộc vào chúng.
- Mock exchange mặc định có thể khác cấu hình production về codec, session store hoặc security context.

Vì vậy, nên dùng mock exchange cho unit test và bổ sung integration test ở đúng nơi cần bảo vệ cấu hình hoặc hạ tầng thật. Không cần biến mọi test thành kiểm thử server đầu cuối; hãy chọn phạm vi dựa trên hành vi cần xác minh.

## 11. Các lỗi thường gặp

**Dùng nhầm mock Servlet cho WebFlux.** `MockHttpServletRequest` thuộc Spring MVC/Servlet. Component nhận `ServerWebExchange` cần mock reactive tương ứng.

**Quên gọi `build()` cho request builder.** Các factory method của `MockServerHttpRequest` trả về builder; phải hoàn tất cấu hình và build trước khi truyền request vào exchange.

**Không chờ publisher hoàn tất.** `writeWith`, `setComplete`, `getSession` và nhiều API khác trả về `Mono`. Nếu assertion chạy trước khi publisher hoàn tất, response hoặc session có thể chưa ở trạng thái mong đợi. Dùng `StepVerifier` hoặc chờ publisher trong test.

**Gọi `block()` trong mã production.** `block()` chỉ nên được dùng ở ranh giới test đồng bộ hoặc trong công cụ phù hợp. Trong pipeline WebFlux production, hãy trả về publisher và compose các bước reactive.

**Đọc DataBuffer nhưng không release.** Khi test tự đọc body, cần quản lý vòng đời buffer. Bỏ qua việc release có thể gây rò rỉ bộ nhớ trong implementation dùng pooled buffer.

**Đọc request body nhiều lần.** Body là stream. Nếu một bước test đã consume body, handler phía sau có thể không còn dữ liệu. Hãy để component được kiểm thử đọc body hoặc chủ động cache/replay theo đúng yêu cầu production.

**Chỉ kiểm tra response status.** Một filter hoặc handler có thể trả đúng status nhưng sai header, cookie hoặc body. Hãy kiểm tra các thành phần thuộc hợp đồng.

**Cho rằng mock exchange xác minh được cấu hình server.** Unit test gọi trực tiếp filter không chứng minh filter đã được đăng ký vào chain. Nếu registration là mục tiêu, cần test cấu hình hoặc WebTestClient.

**Dựng exchange quá phức tạp.** Chỉ thêm session, principal, locale, multipart hoặc attribute khi hành vi đang kiểm thử cần chúng. Fixture tối giản giúp test dễ hiểu và ít phụ thuộc.

## 12. Quy trình xây dựng test với ba lớp mock

Khi kiểm thử một thành phần WebFlux, có thể làm theo trình tự sau:

1. Xác định component nhận `ServerHttpRequest`, `ServerHttpResponse` hay `ServerWebExchange`.
2. Nếu chỉ cần request, tạo `MockServerHttpRequest` với method, URI, header, cookie và body cần thiết.
3. Nếu cần cả request và response, tạo `MockServerWebExchange.from(request)`.
4. Gọi filter, handler hoặc component trực tiếp bằng interface production đang sử dụng.
5. Chờ `Mono`/`Flux` hoàn tất bằng `StepVerifier` hoặc `block()` trong ranh giới test.
6. Kiểm tra status, header, cookie, body, attributes, session hoặc principal theo hợp đồng.
7. Nếu test tự tiêu thụ `DataBuffer`, giải phóng buffer và không làm cạn body trước component cần kiểm tra.
8. Bổ sung WebTestClient hoặc integration test khi cần xác minh routing, codec, filter registration hay server connector.

Khi dùng đúng phạm vi, `MockServerHttpRequest`, `MockServerHttpResponse` và `MockServerWebExchange` giúp kiểm thử logic WebFlux nhanh và tập trung. Chúng cho phép dựng chính xác điều kiện HTTP cần thiết, quan sát response reactive và xác minh cách filter/handler thao tác với exchange mà không cần khởi động server cho từng unit test.
