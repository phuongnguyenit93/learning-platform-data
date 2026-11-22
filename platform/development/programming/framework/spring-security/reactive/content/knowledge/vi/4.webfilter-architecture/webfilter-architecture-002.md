# ServerWebExchange, ServerHttpRequest và ServerHttpResponse trong bảo mật

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt ba đối tượng nền tảng của Spring WebFlux: `ServerWebExchange`, `ServerHttpRequest` và `ServerHttpResponse`.
- Mô tả cách một HTTP request đi qua `WebFilter` và chuỗi lọc Spring Security reactive trước khi đến handler.
- Đọc thông tin request an toàn, thao tác thuộc tính theo vòng đời exchange, lấy principal và hiểu vai trò riêng của Reactor `Context`.
- Bổ sung header phản hồi đúng thời điểm, kết thúc request sớm một cách có kiểm soát và tránh sửa response sau khi đã commit.
- Phân biệt việc trang trí request với việc xác thực người dùng; nhận ra các lỗ hổng phổ biến liên quan đến header giả mạo, body, log, session và response.

> **Ngữ cảnh:** Bài học thuộc kiến trúc WebFilter của Spring Security **reactive** trên Spring WebFlux. Các API dưới đây là loại `org.springframework.http.server.reactive.*` và `org.springframework.web.server.*`; không nhầm với `HttpServletRequest`/`HttpServletResponse` trong Servlet MVC.

## 1. Ba đối tượng tương ứng với điều gì?

| Đối tượng | Vai trò | Những API thường dùng trong bảo mật |
|---|---|---|
| `ServerHttpRequest` | Biểu diễn **HTTP request đến** dưới dạng API của server reactive. | `getMethod()`, `getURI()`, `getPath()`, `getHeaders()`, `getQueryParams()`, `getCookies()`, `getRemoteAddress()`, `getBody()`, `mutate()`. |
| `ServerHttpResponse` | Biểu diễn **HTTP response đi ra**; hỗ trợ ghi status, header, cookie và body qua publisher. | `setStatusCode(...)`, `getHeaders()`, `addCookie(...)`, `beforeCommit(...)`, `isCommitted()`, `writeWith(...)`, `setComplete()`. |
| `ServerWebExchange` | Ngữ cảnh **một lần trao đổi request–response** mà WebFilter và handler cùng xử lý. Bao bọc request, response, thuộc tính, principal và các tiện ích WebFlux. | `getRequest()`, `getResponse()`, `getAttributes()`, `getAttribute(...)`, `getPrincipal()`, `getSession()`, `getFormData()`, `mutate()`. |

Phần mềm tạo `ServerWebExchange` để kết nối request đến với response sẽ được gửi về, cùng dữ liệu phụ trợ của lần xử lý đó. Một `WebFilter` thường nhận **exchange**, bởi nó có thể cần đọc request, ghi response, truy cập principal và truyền exchange đã được bọc cho phần xử lý tiếp theo.

Tương quan:

~~~text
HTTP request đến
  └─ ServerHttpRequest ─┐
                        ├─ ServerWebExchange
  ┌─ ServerHttpResponse ┘        │
  │                              ▼
HTTP response đi              WebFilter.filter(exchange, chain)
                                 │
                                 ▼
                              WebFilter tiếp theo / Handler
                                 │
                                 ▼
                      Mono<Void> biểu diễn quá trình xử lý
~~~

`ServerWebExchange` **không phải một map context toàn cục**. Nó chỉ gắn với một lần HTTP exchange. `ServerHttpRequest` đại diện cho thông điệp request; `ServerHttpResponse` điều khiển thông điệp response. Ba đối tượng có liên quan nhưng không thể dùng thay nhau.

## 2. Chúng xuất hiện ở đâu trong kiến trúc WebFilter?

Khi WebFlux nhận một kết nối/request, lớp HTTP adapter tạo exchange; `FilteringWebHandler` tổ chức các `WebFilter` và chuyển tiếp đến handler. Nếu bật Spring Security WebFlux, một WebFilter proxy của Spring Security chọn `SecurityWebFilterChain` tương ứng và xử lý xác thực, security context, phân quyền, exception handling… theo cấu hình.

~~~text
Client
  │ HTTP
  ▼
Reactive HTTP server / HttpWebHandlerAdapter
  │
  ▼
FilteringWebHandler
  │
  ├─ WebFilter ứng dụng (ví dụ correlation ID)
  │
  ├─ Spring Security WebFilterChainProxy
  │      ├─ chọn SecurityWebFilterChain phù hợp
  │      ├─ cơ chế authentication
  │      ├─ security context / Reactor Context
  │      ├─ cơ chế authorization
  │      └─ xử lý lỗi truy cập theo cấu hình
  │
  └─ DispatcherHandler → Controller / handler
                         │
                         ▼
                ServerHttpResponse → Client
~~~

Đây là **mô hình khái niệm**: thứ tự thực tế của các filter phụ thuộc `@Order`, `Ordered`, các filter được cấu hình và `SecurityWebFiltersOrder`. Không suy luận thứ tự bảo mật chỉ từ vị trí khai báo method trong Java.

Interface cơ bản:

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ExampleFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        // Đọc request hoặc chuẩn bị response tại đây.
        return chain.filter(exchange);
    }
}
~~~

Đoạn trên minh họa interface; để đăng ký thực tế phải tạo bean `WebFilter`, ví dụ `@Component` hoặc `@Bean`. `chain.filter(exchange)` trả `Mono<Void>` đại diện cho phần xử lý còn lại. **Trả về publisher đó** để framework điều phối subscription, lỗi và cancellation. Không tự gọi `subscribe()` trong filter.

Một filter có hai lựa chọn cơ bản:

1. **Tiếp tục**: `return chain.filter(exchange);` (có thể kết hợp thêm toán tử reactive).
2. **Dừng có chủ đích**: thiết lập response rồi trả `response.setComplete()` hoặc publisher ghi body, và **không gọi** `chain.filter(exchange)`.

Trong security, việc dừng vì chưa xác thực/không đủ quyền nên do các thành phần Spring Security tương ứng thực hiện; một filter tự viết không nên tạo lối tắt vô tình bỏ qua authentication/authorization.

## 3. ServerHttpRequest: dữ liệu đầu vào và ranh giới tin cậy

### 3.1. Đọc method, path, query, header và cookie

Ví dụ trong method `filter(...)` hoặc handler có tham số `ServerWebExchange`:

~~~java
ServerHttpRequest request = exchange.getRequest();

String method = request.getMethod().name();
String path = request.getPath().value();
String accept = request.getHeaders().getFirst("Accept");
String tenantQuery = request.getQueryParams().getFirst("tenant");
String rawAuthorization = request.getHeaders().getFirst("Authorization");
~~~

Đây là **đoạn minh họa trong ngữ cảnh đã có biến `exchange`**; không phải chương trình Java độc lập. API đọc trả thông tin *client gửi*, chưa phải bằng chứng client có quyền:

- `getMethod()` và `getPath()` có ích cho điều hướng, policy matching và logging có kiểm soát. Quy tắc bảo mật nên khai báo bằng `authorizeExchange(...).pathMatchers(...)` hoặc matcher của Spring Security, tránh xây bộ kiểm tra URL bằng so khớp chuỗi thủ công.
- `getHeaders()` trả thông tin request; một header do client nhập, kể cả `X-User`, `X-Role` hay `X-Tenant`, **không mặc nhiên đáng tin**. Chỉ dùng làm identity khi kiến trúc có proxy/gateway đáng tin và cơ chế xác minh rõ ràng.
- `Authorization` là dữ liệu credential đầu vào. Không log nguyên token/password, không tự gán `Authentication` từ chuỗi header thô. Để bộ lọc xác thực phù hợp (HTTP Basic, Bearer token, OAuth2…) kiểm tra.
- Query parameter có thể lặp; `getQueryParams()` là multi-value map. Cookie cũng có thể lặp, không tự suy đoán một cookie là phiên đã xác thực.
- `getRemoteAddress()` thường liên quan đến peer kết nối; khi có reverse proxy, IP client thật phụ thuộc cấu hình xử lý `Forwarded`/`X-Forwarded-For` **chỉ từ proxy được tin cậy**. Không lấy địa chỉ do client tự gửi để kết luận quyền truy cập.

**Phân biệt phân tích cú pháp và xác thực:** Biết request mang header `Authorization` chỉ chứng minh có *dữ liệu header*, không chứng minh credential hợp lệ. Spring Security nhận trách nhiệm phân tích, xác thực và tạo `Authentication`.

### 3.2. Request không được sửa tùy ý

Thông thường không thể chỉnh trực tiếp method/URI/header của request gốc bằng cách tự sửa các collection đọc ra. Nếu cần tạo góc nhìn request mới cho phần xử lý **downstream**, dùng builder/decorator:

~~~java
ServerHttpRequest decoratedRequest = exchange.getRequest()
    .mutate()
    .headers(headers -> headers.set("X-Verified-Tenant", verifiedTenant))
    .build();

ServerWebExchange decoratedExchange = exchange.mutate()
    .request(decoratedRequest)
    .build();

return chain.filter(decoratedExchange);
~~~

Đây là **đoạn đặt trong `WebFilter.filter(...)`**; `verifiedTenant` phải là dữ liệu đã được hệ thống xác minh trong logic tin cậy (không phải giá trị lấy thẳng từ header gửi đến). `headers.set(...)` thay thế giá trị cùng tên, thay vì vô tình giữ thêm một header client giả mạo. Việc tạo decorated exchange chỉ thay đổi góc nhìn cho handler/filter sau đó, không sửa gói HTTP đã đi trên mạng.

Cách bọc request **không tự làm header trở thành authentication**. Với định danh/quyền truy cập, dùng `Authentication` và authorization của Spring Security.

### 3.3. Body là luồng reactive và có ràng buộc tiêu thụ

`request.getBody()` có kiểu `Flux<DataBuffer>`: các mảnh byte được cung cấp theo tín hiệu reactive, không phải `String` đã nằm sẵn trong RAM. Filter cố “đọc trước” body có thể khiến handler phía sau không còn dữ liệu để đọc; buffering không giới hạn có thể gây quá tải bộ nhớ; quản lý `DataBuffer` sai có thể rò rỉ tài nguyên.

- Ưu tiên cơ chế sẵn có của WebFlux/Spring Security để xử lý form, authentication credential, multipart và body decoding.
- Nếu thật sự phải đọc/chỉnh body trong filter, cần giới hạn kích thước, xử lý lỗi và cancellation, tuân thủ release/retain của `DataBuffer`, và cung cấp lại body qua `ServerHttpRequestDecorator` cho downstream. Đây là một bài toán riêng, không thể giải bằng gọi `block()` hoặc `subscribe()` tùy ý.
- Không log body chứa password, bearer token, cookie hoặc dữ liệu cá nhân. Tránh biến một request stream thành dữ liệu dùng chung của nhiều request.

## 4. ServerHttpResponse: ai được ghi gì và khi nào?

Với `ServerHttpResponse response = exchange.getResponse()`, một filter có thể:

- Đặt HTTP status trước khi response commit: `response.setStatusCode(HttpStatus.BAD_REQUEST)`.
- Bổ sung/chỉnh header trước khi commit: `response.getHeaders().set("X-Correlation-Id", id)`.
- Bổ sung cookie theo chính sách tương ứng: `response.addCookie(...)`.
- Đăng ký tác vụ thực hiện **trước khi commit**: `response.beforeCommit(Supplier<? extends Mono<Void>>)`.
- Trả một publisher hoàn tất response không có body: `return response.setComplete();`.
- Trả một publisher ghi dữ liệu body (cần mã hóa và quản lý buffer đúng cách): `response.writeWith(...)`.

### 4.1. Thời điểm commit

Khi response bắt đầu được commit (ví dụ ghi body hoặc hoàn thành response), status và header phải được cố định để gửi cho client. Sau khi response đã commit, việc đổi status/header có thể không còn hiệu lực hoặc gây lỗi. Vì vậy:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.beforeCommit(() -> {
    response.getHeaders().set("X-Correlation-Id", correlationId);
    return Mono.empty();
});
return chain.filter(exchange);
~~~

Đây là **đoạn trong một `WebFilter.filter(...)`**, nơi `correlationId` đã được tạo. Callback `beforeCommit` cần nhanh, không blocking, và thích hợp để thêm metadata cuối trước commit. Việc gọi `response.isCommitted()` giúp quan sát trạng thái, nhưng **không thay thế** quản lý đúng thời điểm ghi. Không chờ đến `doFinally` của một pipeline đã hoàn tất để mới cố thêm header.

### 4.2. Kết thúc sớm có kiểm soát

Ví dụ một filter kiểm tra *điều kiện đầu vào phi xác thực* đã được định nghĩa rõ:

~~~java
if (invalidRequestShape) {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.BAD_REQUEST);
    return response.setComplete();
}
return chain.filter(exchange);
~~~

Đây là **nhánh minh họa trong filter**, với `invalidRequestShape` là kết quả kiểm tra cú pháp request; đoạn này không bao gồm các khai báo khác của class. Khi đã dừng, **không** gọi `chain.filter(exchange)` nữa. Để phản hồi `401 Unauthorized` hoặc `403 Forbidden` cho bài toán authentication/authorization, ưu tiên cấu hình `ServerHttpSecurity`, `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` theo đúng ngữ nghĩa, bao gồm challenge header khi cần.

Đối với response body, bộ ghi response sẽ chịu trách nhiệm serialized data và buffer; không tự thao tác `OutputStream` hay giả định ghi đồng bộ kiểu Servlet.

## 5. ServerWebExchange: request-scoped dữ liệu, principal và session

### 5.1. Thuộc tính trong exchange

`exchange.getAttributes()` là một `Map<String,Object>` dùng để chia sẻ metadata trong **một lần trao đổi HTTP**:

~~~java
private static final String AUDIT_TRACE_KEY =
    "com.example.security.auditTraceId";

// Trong WebFilter:
exchange.getAttributes().put(AUDIT_TRACE_KEY, "req-123");

// Trong handler/filter downstream dùng cùng key:
String traceId = exchange.getAttribute(AUDIT_TRACE_KEY);
~~~

Đây là các đoạn minh họa ở những vị trí riêng biệt, không phải chương trình độc lập. Nên dùng key có namespace tránh trùng tên với thư viện/framework. Attribute hữu ích cho dữ liệu gắn với quá trình xử lý request, ví dụ request ID đã được tạo ở server, thời điểm nhận request, hoặc kết quả phân tích đã xác minh.

Đừng nhầm exchange attributes với bộ nhớ chia sẻ toàn ứng dụng, và đừng đưa state mutable này vào singleton dùng chung cho nhiều request.

### 5.2. Principal và SecurityContext

`exchange.getPrincipal()` trả `Mono<Principal>`. Trong một exchange đi qua Spring Security reactive, principal có thể phản ánh `Authentication` đã được xác thực, tùy cách filter chain được thiết lập. Khi không có principal, publisher có thể rỗng.

~~~java
Mono<String> username = exchange.getPrincipal()
    .map(java.security.Principal::getName)
    .defaultIfEmpty("anonymous");
~~~

Ví dụ dùng cho **hiển thị tên hoặc log an toàn**. Không dùng giá trị fallback `"anonymous"` để cấp quyền hoặc suy ra cơ chế xác thực thành công. Có trường hợp Spring Security từ chối trước khi handler chạy.

Dữ liệu xác thực reactive cốt lõi được Spring Security quản lý thông qua `ReactiveSecurityContextHolder` và **Reactor Context theo subscription**, ví dụ:

~~~java
Mono<String> authenticatedName =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext -> securityContext.getAuthentication())
        .map(authentication -> authentication.getName());
~~~

Trong đoạn này cần import `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Publisher này chỉ phát giá trị khi security context phù hợp đã được đưa vào subscription; không nên gọi `block()` để đọc trong WebFlux service.

Ba phạm vi này khác nhau:

| Kênh | Lưu gì | Vòng đời/phạm vi |
|---|---|---|
| Request headers/cookies | Dữ liệu do HTTP client/proxy gửi | Thông điệp HTTP, chưa đáng tin cho đến khi xác minh |
| `exchange.getAttributes()` | Metadata nội bộ của một HTTP exchange | Exchange được chuyển qua filter/handler |
| Reactor `Context` / `ReactiveSecurityContextHolder` | Metadata theo subscriber, bao gồm security context reactive | Chuỗi reactive và subscription tương ứng |

**Không tự chép `Authorization` header vào exchange attribute rồi coi đó là principal đã xác thực.** Một security filter đúng phải tạo hoặc khôi phục `Authentication` từ thông tin đã kiểm chứng; các authorization rule hoạt động dựa trên nó.

### 5.3. Session và body convenience API

`exchange.getSession()` trả `Mono<WebSession>`, liên quan đến session WebFlux nếu ứng dụng có sử dụng. Việc gọi API session không đồng nghĩa user đã xác thực hoặc security context nhất thiết nằm trong session. Vị trí lưu security context phụ thuộc `ServerSecurityContextRepository` và cấu hình (ví dụ ứng dụng stateless với bearer token khác ứng dụng có web session).

`exchange.getFormData()` và `getMultipartData()` hỗ trợ đọc dữ liệu form/multipart đã được phân tích cú pháp qua cơ chế WebFlux. Dùng chúng khi thật sự cần và xét giới hạn kích thước, nội dung nhạy cảm; không làm bước “đọc form cho mọi request” ở một filter global.

## 6. Bài thực hành: WebFlux + Spring Security có kiểm soát

Ví dụ sử dụng **Java 17**, **Spring Boot 3.3.5**, WebFlux và Spring Security reactive. Nó minh họa đồng thời:

1. WebFilter tạo correlation ID ở server và lưu ở **exchange attributes**.
2. Filter đặt ID vào **Reactor Context** cho pipeline downstream.
3. Filter đưa ID vào response header bằng `beforeCommit`.
4. Controller đọc **request** từ exchange; route công khai dùng ID; route riêng yêu cầu **Basic authentication** của Spring Security.
5. `exchange.getPrincipal()` ở route riêng phản ánh principal qua security filter chain.

Đây là một ứng dụng chạy độc lập cho mục đích học tập, không phụ thuộc code của module hiện tại.

### 6.1. Cấu trúc thư mục

~~~text
exchange-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ExchangeSecurityDemo.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'exchange-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Tệp `src/main/java/example/ExchangeSecurityDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;
import reactor.util.context.Context;

@SpringBootApplication
public class ExchangeSecurityDemo {

    private static final String TRACE_ATTRIBUTE =
        "example.ExchangeSecurityDemo.traceId";
    private static final String TRACE_CONTEXT = "traceId";

    public static void main(String[] args) {
        SpringApplication.run(ExchangeSecurityDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Credential đơn giản chỉ dành cho demo local.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Order(Ordered.HIGHEST_PRECEDENCE)
    @org.springframework.stereotype.Component
    static final class CorrelationFilter implements WebFilter {
        @Override
        public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

            String traceId = UUID.randomUUID().toString();

            // Metadata chỉ dành cho exchange hiện tại.
            exchange.getAttributes().put(TRACE_ATTRIBUTE, traceId);

            ServerHttpResponse response = exchange.getResponse();
            response.beforeCommit(() -> {
                response.getHeaders().set("X-Correlation-Id", traceId);
                return Mono.empty();
            });

            // Reactor Context truyền theo subscriber, kể cả đổi thread.
            return chain.filter(exchange)
                .contextWrite(Context.of(TRACE_CONTEXT, traceId));
        }
    }

    @RestController
    static final class ApiController {

        @GetMapping("/public")
        public Mono<Map<String, String>> publicRoute(
            ServerWebExchange exchange) {

            ServerHttpRequest request = exchange.getRequest();

            return Mono.deferContextual(ctx ->
                Mono.just(Map.of(
                    "method", request.getMethod().name(),
                    "path", request.getPath().value(),
                    "traceId", ctx.<String>getOrDefault(
                        TRACE_CONTEXT, "missing")
                )));
        }

        @GetMapping("/private")
        public Mono<Map<String, String>> privateRoute(
            ServerWebExchange exchange) {

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "principal", principal.getName(),
                    "path", exchange.getRequest().getPath().value()
                ));
        }
    }
}
~~~

### 6.2. Chạy và quan sát

Cần JDK 17+ và Gradle hoặc Gradle Wrapper tương thích (nếu dự án chưa có wrapper thì dùng lệnh `gradle`). Từ thư mục `exchange-security-demo`:

~~~bash
gradle bootRun
~~~

Nếu đã tạo Gradle Wrapper, tương đương `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:demo-pass http://localhost:8080/private
~~~

Kỳ vọng cho **cấu hình demo đang chạy**:

| Lời gọi | HTTP status kỳ vọng | Nội dung cần đối chiếu |
|---|---|---|
| `GET /public` không credential | 200 | JSON có `method=GET`, `path=/public`, `traceId` là UUID; response header `X-Correlation-Id` bằng giá trị `traceId`. |
| `GET /private` không credential | 401 | Spring Security chặn trước khi controller trả dữ liệu riêng; HTTP Basic challenge phụ thuộc cấu hình entry point. |
| `GET /private` với Basic `learner:demo-pass` | 200 | JSON có `principal=learner`, `path=/private`. |

Các UUID thay đổi mỗi request và thứ tự field trong JSON không có bảo đảm; vì vậy không đưa một chuỗi JSON/status+header cứng làm “stdout chính xác”. Đây là HTTP response, không phải stdout của lệnh `java`. Khi dùng PowerShell, nếu `curl` là alias khác, hãy gọi `curl.exe`.

**Lưu ý bảo mật:** `{noop}` cho phép password chưa mã hóa và tài khoản demo được hardcode. Chỉ dùng trong môi trường thử nghiệm local; môi trường thật cần encoder an toàn, quản lý secret và luồng xác thực thích hợp. Không dùng Basic authentication qua HTTP không mã hóa ở môi trường thật; cần HTTPS. Bài demo dùng các route GET nên không vô hiệu hóa CSRF để “cho chạy được”.

### 6.3. Vì sao ví dụ có hai nơi lưu trace ID?

`exchange.getAttributes()` giúp các filter/handler đang nhận cùng exchange truy cập metadata nội bộ. `contextWrite` đưa thông tin cho những operator reactive đọc bằng `Mono.deferContextual(...)`. Hai phạm vi có thể cùng mang **một giá trị**, nhưng chúng là hai cơ chế khác nhau. Dấu `.contextWrite(Context.of(...))` được đặt ở phía downstream của `chain.filter(exchange)` để các publisher upstream của chain có thể đọc context khi được subscribe.

`@Order(Ordered.HIGHEST_PRECEDENCE)` ở filter demo giúp đăng ký callback response sớm và đặt context bao quanh chuỗi downstream. Không dùng ví dụ này làm căn cứ tự ý đảo thứ tự các filter bảo mật nội bộ do Spring Security quản lý.

## 7. Nơi nên đặt logic bảo mật

**Không phải mọi việc cần nhìn request đều phải là WebFilter do ứng dụng tự viết.** Dựa vào trách nhiệm, chọn cơ chế thích hợp:

| Nhu cầu | Cơ chế ưu tiên | Vì sao |
|---|---|---|
| Xác thực Basic, Bearer JWT, OAuth2 Login | Spring Security `SecurityWebFilterChain` và các thành phần authentication phù hợp | Quản lý credential, authentication, context và lỗi chuẩn |
| Phân quyền URL/method | `authorizeExchange(...)`, method security khi phù hợp | Policy rõ ràng, đồng nhất; tránh tự so sánh string URL |
| Đọc danh tính trong service reactive | `ReactiveSecurityContextHolder.getContext()` hoặc API principal đã được framework cấp | Không dựa vào `ThreadLocal` hay header do client tự chọn |
| Correlation ID, đo thời gian, header kỹ thuật | `WebFilter` ứng dụng | Gắn logic request/response chung cho toàn pipeline |
| Cần diễn giải thông tin gửi đến thành Authentication | `ServerAuthenticationConverter` với `ReactiveAuthenticationManager` và filter authentication phù hợp | Tách bước trích xuất credential khỏi bước kiểm chứng |
| Cần trả response tùy biến khi bị từ chối | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` | Giữ ngữ nghĩa 401/403 và thứ tự security |
| Cấu hình security context dựa trên session/repository | `ServerSecurityContextRepository` | Tránh lưu/khôi phục security context tùy tiện vào attribute |

Đặc biệt, một custom WebFilter không được “cho qua” một request nhạy cảm chỉ vì tìm thấy `X-User: admin` hoặc cookie có tên quen thuộc. Dấu hiệu do client tạo không thay thế bước authentication.

## 8. Những hiểu nhầm và lỗi triển khai phổ biến

### Lỗi 1: Coi ServerWebExchange là SecurityContext

`exchange.getAttributes().put("user", "...")` chỉ đặt metadata. Spring Security không tự coi key tự đặt đó là Authentication. Nếu muốn truy xuất identity đã xác thực, dùng principal/security context đúng luồng.

### Lỗi 2: Cố đổi status sau khi controller đã ghi body

Response có thể đã commit. Ghi header quá muộn dẫn đến header không có trên mạng hoặc lỗi. Đăng ký `beforeCommit` trước khi gọi downstream, hoặc thiết lập response trước khi ghi.

### Lỗi 3: Gọi `chain.filter(exchange)` mà không trả publisher

~~~java
// SAI: publisher có thể không được subscribe đúng cách.
chain.filter(exchange);
return Mono.empty();

// ĐÚNG: trả publisher của downstream.
return chain.filter(exchange);
~~~

Hai đoạn chỉ minh họa phần thân method `filter`. Reactive pipeline là mô tả tác vụ; việc tạo `Mono` không đồng nghĩa tác vụ đã chạy.

### Lỗi 4: Tự gọi `subscribe()`/`block()` trong WebFilter

Việc subscribe tay có thể tạo subscription tách rời, mất Reactor Context/SecurityContext, làm lỗi lan truyền sai và phá vòng đời request; `block()` có thể chặn event-loop thread. Kết hợp bằng `flatMap`, `then`, `onErrorResume` phù hợp và trả một publisher cho framework.

### Lỗi 5: Đọc request body rồi truyền request gốc

Body reactive không phải dữ liệu có thể đọc tùy ý nhiều lần. Nếu filter cần xem body, giải pháp đúng phải tính đến buffering giới hạn, decorator cho request downstream, backpressure và quản lý DataBuffer. Tránh tự chặn/collect toàn bộ body để “đọc cho nhanh”.

### Lỗi 6: Tin vào header IP, role, tenant không được xác minh

`X-Forwarded-For`, `X-Role`, `X-Tenant` hoặc `Authorization` đều là đầu vào. Chỉ tin khi đã qua cơ chế xác minh thích hợp; reverse proxy phải được cấu hình rõ, chặn hoặc ghi đè các header mà client không được quyền tự khai báo.

### Lỗi 7: Để lộ dữ liệu nhạy cảm qua log/response

Không log raw bearer token, password, cookie phiên; không trả stack trace, security context hoặc thuộc tính nội bộ về client. Correlation ID nên là định danh vô nghĩa, không chứa thông tin cá nhân.

### Lỗi 8: Dùng cùng một state mutable cho mọi request

Đặt `ServerWebExchange`, response hoặc danh tính người dùng vào field của bean singleton dẫn đến truy cập đồng thời và lộ thông tin chéo request. Giữ exchange theo từng invocation; metadata request trong exchange attributes hoặc Reactor Context theo scope đúng.

### Lỗi 9: Tưởng `getSession()` luôn có nghĩa đã đăng nhập

Session hiện diện không chứng minh có Authentication. Ứng dụng bearer JWT stateless có thể xác thực mà không duy trì session phía server. Quyết định authorization dựa trên Authentication/security context và policy.

### Lỗi 10: Tự gắn response 401/403 mà bỏ qua cơ chế Spring Security

Status không phải toàn bộ quy trình xử lý lỗi bảo mật. Spring Security còn quản lý authentication entry point, HTTP Basic challenge, access-denied logic và security context. Custom response cần đặt vào extension point phù hợp.

## 9. Checklist review một WebFilter liên quan bảo mật

Trước khi chấp nhận code, kiểm tra:

1. **Scope:** Filter chạy cho request nào? Có thực sự cần global WebFilter hay nên đặt trong `SecurityWebFilterChain`?
2. **Nguồn dữ liệu:** Method/path/header/body lấy từ `ServerHttpRequest` có được coi là untrusted và xác minh trước khi dùng làm quyền không?
3. **Chuyển tiếp:** Mọi nhánh tiếp tục có trả `chain.filter(exchange)`; nhánh dừng có hoàn tất response và không gọi chain tiếp?
4. **Context:** Metadata exchange và Reactor Context có được dùng đúng phạm vi; principal có đến từ authentication thật không?
5. **Response:** Header/status được thiết lập trước commit; callback `beforeCommit` không blocking; không cố sửa sau commit?
6. **Body và tài nguyên:** Không đọc body lặp, không giữ buffer vô hạn, không rò DataBuffer và không gọi `block()` trong event loop?
7. **Bảo vệ dữ liệu:** Không ghi credential vào log, không phản hồi thông tin nhạy cảm, không tin header giả mạo?
8. **Kiểm thử:** Có case anonymous/authenticated/denied, lỗi và cancellation, correlation ID trên cả success và failure, các request đồng thời không dùng nhầm metadata?

Những kịch bản kiểm thử thực tế nên có:

- `GET /public` trả 200 và một correlation ID tương ứng giữa body và header.
- `GET /private` không credential bị từ chối; có credential hợp lệ trả đúng principal.
- Một request có `X-User: admin` không tự được xác thực.
- Hai request đồng thời nhận correlation ID riêng; response không mang ID của request khác.
- Khi controller thất bại trước hoặc trong khi ghi body, filter không cố ghi header sau commit và lỗi vẫn được xử lý đúng.
- Khi có gateway/reverse proxy, dữ liệu `Forwarded` chỉ được dùng theo cấu hình trust đã kiểm chứng.

## 10. Câu hỏi tự đánh giá

**1. Muốn đọc path của request hiện tại trong WebFilter, lấy ở đâu?**

Từ `exchange.getRequest().getPath()`. Nó cung cấp dữ liệu request; luật phân quyền nên được định nghĩa bằng matcher của Spring Security.

**2. Sau khi một handler đã bắt đầu gửi response, có thể chắc chắn thay HTTP status không?**

Không. Khi response đã commit, status/header không còn tự do thay đổi. Đặt trước thời điểm commit; cân nhắc `beforeCommit` cho header cần thêm.

**3. `exchange.getAttributes()` và `ReactiveSecurityContextHolder` có phải cùng một kho lưu không?**

Không. Attributes thuộc về exchange; `ReactiveSecurityContextHolder` dựa vào Reactor Context của subscription.

**4. Nếu client gửi `X-Role: ADMIN`, endpoint có thể tự cấp quyền admin không?**

Không. Header do client khai báo là untrusted. Spring Security phải xác thực danh tính và đánh giá policy dựa trên Authentication/authorities được tạo từ dữ liệu đã kiểm chứng.

**5. Khi muốn trả 400 và dừng xử lý trong filter, có bắt buộc gọi chain không?**

Không. Có thể đặt status rồi `return response.setComplete()`, nhưng chỉ ở nhánh có chủ đích. Đừng dùng nó thay cơ chế xử lý lỗi authentication/authorization của Spring Security.

## Tài liệu chính thức

- Spring Framework WebFlux — `WebFilter` và Web Handler API: https://docs.spring.io/spring-framework/reference/web/webflux-webhandler-api.html
- Spring Framework Javadoc — `ServerWebExchange`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework Javadoc — `ServerHttpRequest`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework Javadoc — `ServerHttpResponse`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
