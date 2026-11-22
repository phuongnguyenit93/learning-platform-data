# Áp dụng cùng một chuỗi bảo mật cho Controller và RouterFunction

> **Chủ đề:** Kiến trúc `WebFilter` trong Spring Security reactive. Ví dụ dành cho **Spring Boot 3.x, Spring Security 6.x, Spring WebFlux và Java 17+**. Một ứng dụng có thể đồng thời khai báo endpoint bằng `@RestController` và `RouterFunction`, và **cùng một `SecurityWebFilterChain` bảo vệ cả hai** khi HTTP request đi qua hạ tầng Spring WebFlux của ứng dụng.

## Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả đường đi từ HTTP request qua các `WebFilter` của Spring Security, tới `DispatcherHandler` rồi tới annotated controller hoặc functional handler.
2. Phân biệt **`SecurityWebFilterChain` áp dụng cho exchange HTTP** với `HandlerFilterFunction` chỉ áp dụng trong nhóm functional routes.
3. Viết **một bean `SecurityWebFilterChain`** và cùng một chính sách `authorizeExchange` cho các path do hai kiểu handler xử lý.
4. Kiểm tra hành vi **401 / 403 / 200** của cả hai endpoint bằng `WebTestClient` và phát hiện lỗi bỏ sót path matcher.
5. Biết khi nào cần nhiều security chains và vì sao `securityMatcher`, `@Order` và thứ tự authorization rules làm thay đổi kết quả.

## 1. Hai cách khai báo endpoint, một WebFlux runtime

Spring WebFlux có hai mô hình lập trình endpoint:

| Khía cạnh | Annotation-based Controller | Functional RouterFunction |
| --- | --- | --- |
| Tuyên bố route | `@RestController`, `@GetMapping`, `@RequestMapping` | Bean `RouterFunction<ServerResponse>` với `RequestPredicates` |
| Đơn vị xử lý request | Handler method trên controller bean | `HandlerFunction<ServerResponse>` nhận `ServerRequest` |
| Kiểu kết quả phổ biến | `Mono<T>`, `Flux<T>` hoặc đối tượng được framework hỗ trợ | `Mono<ServerResponse>` |
| Handler mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Thành phần xử lý | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` và `ServerResponseResultHandler` |
| Phần chung | `DispatcherHandler` và hạ tầng WebFlux | Cùng `DispatcherHandler` và hạ tầng WebFlux |
| Bảo mật HTTP server | `SecurityWebFilterChain` | **Cùng `SecurityWebFilterChain`** |

Chọn Controller hay RouterFunction là lựa chọn **cách định nghĩa route và handler**. Nó không tạo ra một loại HTTP security mới. Khi cả hai nằm trong **cùng WebFlux application context và server HTTP**, request đến chúng đều chạy qua những `WebFilter` ở mức ứng dụng, trong đó có `WebFilterChainProxy` của Spring Security.

Ví dụ URL:

- `GET /api/annotated/hello` do `@RestController` xử lý.
- `GET /api/functional/hello` do `RouterFunction` xử lý.
- `GET /public/ping` là route công khai để quan sát thứ tự rule.

Ta sẽ dùng cùng quy tắc: GET dưới `/api/**` phải có role `READER`, còn `/public/ping` thì không cần đăng nhập.

## 2. Đường đi request và nơi Spring Security ra quyết định

Luồng tổng quan của **WebFlux server thông thường**:

```text
Client HTTP request
    |
    v
HttpHandler / WebHandler với chuỗi WebFilter của ứng dụng
    |
    v
Spring Security WebFilterChainProxy
    |-- chọn SecurityWebFilterChain phù hợp với ServerWebExchange
    |-- xác thực credential, tạo Authentication khi hợp lệ
    |-- áp dụng authorization rule, CSRF và các filter liên quan
    |-- có thể kết thúc 401/403 trước khi gọi handler
    |
    v
DispatcherHandler (Spring WebFlux)
    |
    +--> RequestMappingHandlerMapping --> @RestController method
    |
    +--> RouterFunctionMapping --> HandlerFunction (WebFlux.fn)
    |
    v
Response được ghi về client
```

Sơ đồ nhấn mạnh **vị trí bảo mật trong request pipeline**, không ràng buộc mọi filter phải chạy theo thứ tự liệt kê. Thứ tự filter thực tế do Spring Security quản lý và còn tùy cơ chế đăng nhập, CSRF, exception handling, v.v.

**Tại sao cùng chain áp dụng cho hai loại handler?**

- `SecurityWebFilterChain` chọn request theo `ServerWebExchange`: URL, HTTP method và các thuộc tính request mà matcher có thể đánh giá.
- Việc phân quyền tại `authorizeExchange` diễn ra trong WebFilter pipeline, trước khi controller/functional handler thực hiện tác vụ.
- Spring Security **không kiểm tra** endpoint đó được viết bằng `@GetMapping` hay `RouterFunctions.route(...)` để quyết định mặc định dùng một chain khác.
- Sau khi qua security, `DispatcherHandler` mới ủy quyền cho handler mapping phù hợp. Annotated và functional endpoint đều có thể được xử lý trong cùng ứng dụng.

**Điều kiện:** Đây phải là **WebFlux server thực sự**. Nếu ứng dụng có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên **Spring MVC/Servlet** theo mặc định; khi đó `SecurityFilterChain`/`HttpSecurity` mới là cơ chế bảo mật Servlet. Để học bài này, dùng `spring-boot-starter-webflux` làm web server và kiểm tra app chọn `REACTIVE`. Có `WebClient` hoặc `Mono` trên classpath chưa đủ chứng minh server chạy WebFlux.

## 3. Chuẩn bị project chạy thử

Tạo dự án Spring Boot 3.x với Java 17+, Gradle Groovy DSL và các dependency cần thiết.

Trong `build.gradle` của dự án đã áp dụng Spring Boot plugin và dependency management phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Không thêm `spring-boot-starter-web` cho bài thực hành này.** `starter-webflux` cung cấp HTTP server WebFlux; `starter-security` cung cấp Spring Security; `starter-test` cung cấp JUnit 5, AssertJ và `WebTestClient` qua các thư viện kiểm thử liên quan.

Cấu trúc mã ví dụ:

```text
src/
  main/java/com/example/webfluxsecurity/
    DemoApplication.java
    GreetingController.java
    FunctionalRoutes.java
    WebSecurityConfig.java
  test/java/com/example/webfluxsecurity/
    SharedSecurityChainTest.java
```

Các đoạn mã dưới đây là **các file riêng trong cùng package**. Không ghép bốn class `public` thành một file Java. Sau khi dự án Spring Boot đã được Gradle cấu hình, dùng `./gradlew bootRun` và `./gradlew test`. Trên Windows PowerShell, dùng `.\gradlew.bat` thay thế.

### 3.1 File khởi động

`src/main/java/com/example/webfluxsecurity/DemoApplication.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` quét các component cùng package và package con. Cả Controller, RouterFunction bean và SecurityConfig ở những file tiếp theo đều được đăng ký vào **cùng một Spring application context**.

### 3.2 Annotated Controller

`src/main/java/com/example/webfluxsecurity/GreetingController.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
        value = "/api/annotated/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> hello() {
        return Mono.just("Hello from Controller");
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

Handler `hello()` trả về `Mono<String>`; Spring WebFlux gửi body text khi publisher hoàn tất. `ping()` dùng để thử route `permitAll`. Cả hai đường dẫn đều được Spring Security nhìn thấy dưới dạng HTTP exchange, không phải loại “controller request” riêng.

### 3.3 Functional RouterFunction

`src/main/java/com/example/webfluxsecurity/FunctionalRoutes.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return RouterFunctions.route(
            RequestPredicates.GET("/api/functional/hello"),
            request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello from RouterFunction")
        );
    }
}
```

`RequestPredicates.GET(...)` định nghĩa URL và HTTP method; `HandlerFunction` nhận `ServerRequest` và tạo `Mono<ServerResponse>`. Handler không tự kiểm tra credential. Nó được bảo vệ **trước khi gọi**, nhờ chuỗi `WebFilter` chung.

**Phân biệt hai lớp lọc:** Builder `RouterFunctions.route().filter(...)` hoặc `RouterFunction.filter(...)` thêm `HandlerFilterFunction` chỉ cho các functional routes được ghép vào router đó. Nó không tự áp dụng cho `@RestController`. Muốn áp dụng authentication, authorization và các chính sách HTTP server cho cả hai, hãy cấu hình **Spring Security `SecurityWebFilterChain`**.

## 4. Một SecurityWebFilterChain dùng chung cho cả hai

`src/main/java/com/example/webfluxsecurity/WebSecurityConfig.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    SecurityWebFilterChain sharedSecurityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**").hasRole("READER")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(reader, viewer);
    }
}
```

**Tại sao cấu hình này dùng đúng một chain?**

1. Chỉ có **một bean `SecurityWebFilterChain`** do ta khai báo là `sharedSecurityChain`. Không đặt `securityMatcher(...)` giới hạn phạm vi chain, nên mặc định chain xét tất cả request HTTP vào ứng dụng.
2. `authorizeExchange` xét URL và method, không xét handler type. Cả `GET /api/annotated/hello` và `GET /api/functional/hello` đều khớp `GET /api/**` và đòi `hasRole("READER")`.
3. `hasRole("READER")` tương đương yêu cầu authority `ROLE_READER`. `User.roles("READER")` tự tạo authority này. `viewer` đăng nhập hợp lệ nhưng chỉ có `ROLE_VIEWER` nên không được vào cả hai endpoint.
4. `httpBasic` xác thực bằng `Authorization: Basic ...` cho demo; `formLogin` bị tắt để tránh redirect sang form làm khó quan sát 401. HTTP Basic **chỉ là lựa chọn minh họa**, không phải khuyến nghị cho mọi ứng dụng WebFlux thực tế.
5. `anyExchange().denyAll()` chặn các request còn lại trong chain. Đặt rule cụ thể trước rule tổng quát để tránh một rule rộng chiếm hết request.
6. Spring Security WebFlux **bật CSRF protection theo mặc định**. Ví dụ chỉ có GET nên không cần CSRF token khi gọi các endpoint mẫu; nếu thêm POST/PUT/DELETE, phải thiết kế xử lý CSRF theo loại client. Đừng tắt CSRF toàn cục chỉ để bài demo dễ chạy.

**Mật khẩu trong mã chỉ phục vụ test nội bộ.** Khi triển khai thật, không hardcode tài khoản hoặc secret trong source; dùng user store/identity provider và cơ chế quản lý secret phù hợp. HTTP Basic phải dùng HTTPS ở môi trường ngoài localhost. Thực tế có thể thay HTTP Basic bằng form session, OAuth2 Login hoặc JWT Resource Server mà không thay nguyên tắc: **security chain hoạt động trước cả hai handler**.

### 4.1 Quy tắc chung dựa vào URL, không dựa vào annotation

Giả sử client gửi:

```http
GET /api/annotated/hello HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

và sau đó gửi:

```http
GET /api/functional/hello HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

Cùng `SecurityWebFilterChain` nhận hai `ServerWebExchange`, cùng `pathMatchers(HttpMethod.GET, "/api/**")`, cùng authentication provider và rule `hasRole("READER")`. Phần khác biệt chỉ bắt đầu khi `DispatcherHandler` tìm handler để trả response.

Nếu muốn một endpoint có quyền khác, thêm rule riêng **trước** rule `/api/**`, ví dụ:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/functional/admin/**")
        .hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/**")
        .hasRole("READER")
    .anyExchange().denyAll()
)
```

Khối trên là **mảnh cấu hình thay thế phần `authorizeExchange`** trong `WebSecurityConfig`, không phải một method Java độc lập. Các endpoint mới thực tế phải được định nghĩa tương ứng. Ngay cả khi một route admin nằm trong RouterFunction, Spring Security vẫn áp dụng rule theo URL/method như thường.

## 5. Xác minh từng đường dẫn bằng HTTP

Sau khi chạy `./gradlew bootRun` với cấu hình mặc định (thường là port 8080), bảng kỳ vọng:

| HTTP request | Authentication | Endpoint | Kỳ vọng |
| --- | --- | --- | --- |
| `GET /public/ping` | Không có | Controller | `200 OK`, body `pong` |
| `GET /api/annotated/hello` | Không có | Controller | `401 Unauthorized` |
| `GET /api/functional/hello` | Không có | RouterFunction | `401 Unauthorized` |
| `GET /api/annotated/hello` | `reader`, password đúng | Controller | `200 OK`, body `Hello from Controller` |
| `GET /api/functional/hello` | `reader`, password đúng | RouterFunction | `200 OK`, body `Hello from RouterFunction` |
| `GET /api/annotated/hello` | `viewer`, password đúng | Controller | `403 Forbidden` |
| `GET /api/functional/hello` | `viewer`, password đúng | RouterFunction | `403 Forbidden` |
| `POST /api/functional/hello` | Bất kỳ | Không có POST route | Không được thực thi như GET route; status phụ thuộc auth/CSRF/handler resolution |

**401 và 403 khác nhau:** 401 là chưa xác thực hợp lệ hoặc không có credential đối với protected resource; 403 là đã xác thực nhưng không có đủ authority (ở ví dụ này là thiếu `ROLE_READER`). Khi route không tồn tại, lỗi HTTP cuối cùng còn phụ thuộc bảo mật và thứ tự xử lý: đừng dùng 404 để suy diễn rằng filter không chạy.

Thử route công khai và request chưa xác thực bằng curl:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/annotated/hello
curl -i http://localhost:8080/api/functional/hello
```

Để thử tài khoản reader, có thể dùng `curl -i -u reader http://localhost:8080/api/functional/hello` rồi nhập mật khẩu demo khi curl hỏi. Cách nhập tương tác giúp tránh đặt mật khẩu trực tiếp vào command line. Với ứng dụng thật, HTTP Basic phải chạy qua HTTPS, không gửi password trên HTTP công khai.

Ví dụ kết quả **cần quan sát** (không phải log giả lập đầy đủ):

```text
GET /public/ping          -> HTTP 200, pong
GET /api/annotated/hello  -> HTTP 401 nếu không có credential
GET /api/functional/hello -> HTTP 401 nếu không có credential
reader + annotated        -> HTTP 200, Hello from Controller
reader + functional       -> HTTP 200, Hello from RouterFunction
viewer + annotated        -> HTTP 403
viewer + functional       -> HTTP 403
```

## 6. Integration test: chứng minh cùng security chain qua hành vi

Các kiểm thử trực tiếp trên HTTP server thực của `@SpringBootTest(webEnvironment = RANDOM_PORT)` đáng tin hơn test riêng một router rồi giả định security của ứng dụng cũng đã chạy. Tệp:

`src/test/java/com/example/webfluxsecurity/SharedSecurityChainTest.java`:

```java
package com.example.webfluxsecurity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class SharedSecurityChainTest {

    private static final List<String> PROTECTED_PATHS = List.of(
        "/api/annotated/hello",
        "/api/functional/hello"
    );

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @Test
    void oneSecurityChainIsRegistered() {
        assertThat(context.getBeansOfType(SecurityWebFilterChain.class))
            .hasSize(1);
    }

    @Test
    void anonymousIsRejectedOnBothEndpoints() {
        for (String path : PROTECTED_PATHS) {
            client.get()
                .uri(path)
                .exchange()
                .expectStatus().isUnauthorized();
        }
    }

    @Test
    void readerCanCallBothEndpoints() {
        client.get()
            .uri("/api/annotated/hello")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from Controller");

        client.get()
            .uri("/api/functional/hello")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from RouterFunction");
    }

    @Test
    void viewerIsForbiddenOnBothEndpoints() {
        for (String path : PROTECTED_PATHS) {
            client.get()
                .uri(path)
                .headers(h -> h.setBasicAuth(
                    "viewer", "viewer-demo-password"))
                .exchange()
                .expectStatus().isForbidden();
        }
    }

    @Test
    void publicControllerIsAccessibleWithoutLogin() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }
}
```

**Kiểm tra mà test này thực sự thực hiện:**

- Context do Spring Boot khởi động có một bean `SecurityWebFilterChain`.
- Một người chưa đăng nhập bị từ chối tại **cả hai** endpoint; không có đường functional “đi tắt” qua bảo mật.
- Một user có `ROLE_READER` vào được cả hai; user hợp lệ nhưng thiếu role bị chặn ở cả hai.
- Endpoint public vẫn hoạt động khi chưa có credential.

Chạy:

```bash
./gradlew test --tests '*SharedSecurityChainTest'
```

Kỳ vọng Gradle báo test thành công khi source, package, dependency và context khớp ví dụ. Test có thể thất bại nếu ứng dụng có thêm `SecurityWebFilterChain` khác, thiếu WebFlux starter, sai password, cấu hình bên ngoài thay đổi port/security, hoặc endpoint không được scan. Trong trường hợp đó hãy xem assertion và exception thực tế; không “chữa” bằng cách tắt security.

**Lưu ý về test slice:** `@WebFluxTest` chỉ tải một phần context, có thể không tự phát hiện các `RouterFunction` bean cũng như `SecurityWebFilterChain` tự khai báo; phải import các thành phần liên quan. `WebTestClient.bindToRouterFunction(...)` đơn thuần có thể chỉ kiểm thử handler mà **bỏ qua security context của ứng dụng**. Dùng `@SpringBootTest` như trên để quan sát cả annotated endpoint và functional endpoint với chính cấu hình bảo mật đã khai báo.

## 7. SecurityWebFilterChain khác HandlerFilterFunction như thế nào?

Hai tên đều có chữ *Filter*, nhưng nơi áp dụng và trách nhiệm khác nhau:

| Tiêu chí | Spring Security `SecurityWebFilterChain` | WebFlux.fn `HandlerFilterFunction` |
| --- | --- | --- |
| Phạm vi | HTTP `ServerWebExchange` đi qua Spring Security `WebFilterChainProxy` | Các `HandlerFunction` thuộc router nơi filter được khai báo |
| Tác động `@RestController` | Có, khi request khớp chain | Không tự áp dụng |
| Tác động `RouterFunction` | Có, khi request khớp chain | Có, trong nhóm functional route chứa filter |
| Thời điểm | Lớp WebFilter của application pipeline trước handler | Xung quanh việc gọi functional handler khi router tương ứng đã được chọn |
| Dùng để | Authentication, authorization, CSRF, security context, security headers | Logging/thay đổi request-response hoặc kiểm tra nghiệp vụ cục bộ trong functional routing |
| Cách cấu hình | `@Bean SecurityWebFilterChain` với `ServerHttpSecurity` | `RouterFunctions.route().filter(...)` hoặc `RouterFunction.filter(...)` |

Ví dụ một filter chức năng:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/functional/hello",
        req -> ServerResponse.ok().bodyValue("Hello from RouterFunction"))
    .filter((request, next) -> {
        // Chỉ áp dụng trong RouterFunction này.
        return next.handle(request);
    })
    .build();
```

Đây là **đoạn minh họa đặt trong method cấu hình**, không phải class hoàn chỉnh. `next.handle(request)` gọi handler tiếp theo. Nếu bỏ lời gọi này và trả response ngay, handler sẽ không chạy. Dù thêm filter ở đây, annotated controller không nhận filter đó. Đối với authentication và authorization dùng chung, vẫn phải dùng Spring Security `WebFilter`.

**Tương tự:** `@ControllerAdvice`, `HandlerInterceptor` của MVC, và Servlet `Filter` không phải cơ chế thay thế `SecurityWebFilterChain` của WebFlux.

## 8. Matcher: nguyên nhân phổ biến khiến một endpoint không được bảo vệ như mong đợi

### 8.1 Security matcher chọn chain, authorization matcher chọn rule

Trong cấu hình **chỉ có một chain** ở mục 4, không có `securityMatcher` giới hạn nên mọi request đều đi vào cùng chain rồi được xét `authorizeExchange`.

Khi chia làm nhiều chain, ví dụ:

```java
.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"))
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated())
```

Đây là **một đoạn nằm trong phần dựng chain**, yêu cầu import `PathPatternParserServerWebExchangeMatcher`. Nó khiến chain **chỉ xét request có path `/api/**`**. Sau khi chain khớp, `anyExchange()` trong chain ấy mới đánh giá request. Hai tầng matcher này khác nhau.

Nếu viết nhầm matcher thành `/api/annotated/**`, functional route `/api/functional/hello` sẽ **không lọt vào chain đó**, dù handler functional vẫn tồn tại. Nếu không có chain khác phù hợp, request có thể không đi qua chính sách Spring Security bạn định áp dụng. **Không dựa vào một `anyExchange().denyAll()` nằm trong chain chỉ match annotated path để bảo vệ functional path ở ngoài chain.**

### 8.2 Nhiều chain được chọn theo thứ tự

Nếu cần bảo mật API Bearer token khác với browser session, có thể có nhiều `SecurityWebFilterChain` bean, thường đặt `@Order` để xác định chain ưu tiên:

```text
@Order(1) apiChain:   securityMatcher("/api/**")
@Order(2) webChain:   securityMatcher(any request)
```

Đây là **sơ đồ khái niệm**, không phải Java có thể biên dịch. Spring Security xét các chain theo thứ tự và chọn **một chain đầu tiên phù hợp** cho request. Chúng không cộng dồn tất cả authorization policies từ mọi chain. Cả Controller lẫn RouterFunction dưới `/api/**` vẫn vào **cùng apiChain**; loại handler không thay đổi thuật toán chọn chain.

**Quan trọng:** Một request khớp path của chain nhưng không khớp rule bên trong có thể nhận kết quả khác dự kiến tùy `anyExchange`. Tốt nhất khai báo đầy đủ quyền, đặt rule đặc thù trước rule rộng và có rule cuối an toàn.

### 8.3 Phương thức HTTP cũng quan trọng

`pathMatchers(HttpMethod.GET, "/api/**")` áp dụng cho GET; POST hoặc DELETE không tự thừa kế role READER từ rule đó. Trong ví dụ, `anyExchange().denyAll()` từ chối các method còn lại theo authorization policy, và với method unsafe thì CSRF filter cũng có thể chặn trước. Việc tồn tại một RouterFunction `GET` không tạo ra một quyền `POST`.

Kiểm tra thêm các yếu tố dễ làm sai matcher: prefix của reverse proxy, `spring.webflux.base-path`, path được chuyển đổi trên gateway, trailing slash, path variables và HTTP method. Xác minh URL thực sự đến server thay vì chỉ nhìn đường dẫn phía client.

## 9. SecurityContext, method security và phân quyền nghiệp vụ chung

Khi HTTP Basic (hoặc JWT/OIDC/session) được xử lý trong WebFilter, danh tính đã xác thực được chuyển trong ngữ cảnh reactive. Controller và HandlerFunction có thể dùng chung bean service xử lý quyền. Trong WebFlux, đọc authentication theo `ReactiveSecurityContextHolder` thay vì giả định ThreadLocal như servlet.

Ví dụ một method reactive trong service bean:

```java
public Mono<String> currentUsername() {
    return org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(context -> context.getAuthentication().getName())
        .defaultIfEmpty("anonymous");
}
```

Đoạn trên là **method minh họa trong một class/service**; không phải ứng dụng độc lập. Nếu được thực thi trong pipeline request đã xác thực, nó trả về tên principal. Không tự `block()` trên event-loop hoặc tự `subscribe()` ngoài pipeline làm mất khả năng gắn context và kiểm soát lifecycle.

Có thể bật `@EnableReactiveMethodSecurity` và dùng `@PreAuthorize` trên **method của Spring bean** để tăng phân quyền ở service dùng chung. Một lambda trong RouterFunction không tự trở thành method được proxy bởi `@PreAuthorize` chỉ vì đặt trong router. Global HTTP authorization vẫn cần kiểm tra request trước khi tới handler; business layer vẫn cần kiểm tra ownership/tenant/record-level permissions của từng tài nguyên. Cùng path rule `hasRole("READER")` chưa bảo đảm user có thể đọc **mọi** record trong hệ thống.

Đối với JWT Resource Server, thay `httpBasic(...)` bằng `oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` và cấu hình issuer/audience hợp lệ; kiểm tra scope bằng `hasAuthority("SCOPE_read")` (nếu JWT scope được map thành authority đó). Điều này thay đổi cách **xác thực**, nhưng nguyên tắc **một HTTP WebFilter chain cho Controller và RouterFunction** giữ nguyên. Không tự gán role cho token nếu claim/authority mapping không hỗ trợ.

## 10. CSRF, CORS và lỗi bảo mật dễ bị bỏ sót

**CSRF:** Trong WebFlux, CSRF protection hoạt động trong security WebFilter chain và có thể tác động tới cả annotated endpoint và functional endpoint. Ví dụ toàn GET không cần gửi token CSRF. Nếu thêm form/cookie session và endpoint thay đổi dữ liệu, cần giữ CSRF protection và truyền CSRF token hợp lệ. Với API Bearer-only không sử dụng cookie tự đính kèm, có thể cân nhắc tắt CSRF cho **phạm vi API phù hợp**, không tắt toàn ứng dụng theo thói quen.

**CORS:** CORS là chính sách browser cross-origin, không thay thế authentication, authorization hay CSRF. Controller có thể dùng `@CrossOrigin`, nhưng cấu hình annotation đó không tự bao phủ RouterFunction. Muốn một CORS policy chung, dùng cấu hình WebFlux/CorsWebFilter hoặc cấu hình tương thích với Spring Security cho các path liên quan. Kiểm tra preflight OPTIONS khi API có client chạy trên origin khác; một rule chỉ cho GET không mặc nhiên đáp ứng preflight được trình duyệt gửi.

**Error handling:** Khi Spring Security chặn request trước handler, controller exception handler hoặc functional error handler không nhất thiết nhận lỗi đó. Dùng security exception handling/entry point/access denied handler đúng lớp khi cần tùy biến 401/403. Không giả định handler logging sẽ luôn được gọi cho request bị security chặn.

**Observability:** Log ở Spring Security và HTTP server phải loại bỏ Authorization header và credential. Dùng trace ID và route/status để theo dõi; test 401/403/200 ở cả hai loại handler quan trọng hơn việc nhìn một dòng log nói “route đã đăng ký”.

## 11. Bài thực hành kiểm tra lỗi cấu hình

Hãy tạo **một thay đổi mỗi lần**, chạy lại `SharedSecurityChainTest` và giải thích vì sao test đúng/sai:

1. **Đổi `/api/**` thành `/api/annotated/**`** trong authorization rule, giữ `anyExchange().denyAll()`: controller đọc được với role READER, functional GET bị từ chối vì không khớp rule GET được phép. Sửa bằng matcher bao phủ cả hai path.
2. **Đổi `hasRole("READER")` thành `hasRole("ADMIN")`**: cả hai endpoint không còn mở cho reader; test 200 cho reader phải thất bại đồng thời. Đây là dấu hiệu chung rule.
3. **Đưa `anyExchange().denyAll()` lên trước `pathMatchers`**: rule rộng thắng trước, các rule chi tiết không được áp dụng như mong muốn; sửa thứ tự.
4. **Thêm `HandlerFilterFunction` vào RouterFunction** nhưng không sửa SecurityConfig: annotated controller không chạy functional filter, còn policy Spring Security của cả hai vẫn không đổi.
5. **Thay đổi HTTP Basic sang JWT** với client/token test hợp lệ: cả hai endpoint vẫn được bảo vệ bằng cùng path matcher; thay đổi chỉ nằm ở authentication và authority mapping.
6. **Dùng `@WebFluxTest(GreetingController.class)` mà không import RouterFunction/SecurityConfig**: test slice không nhất thiết có route functional hoặc custom chain. Dùng full-context test khi cần kiểm tra tính dùng chung.

Đừng coi test failing do sai dependency/context là lỗi quyền business; nếu có MVC starter xuất hiện, trước hết kiểm tra Boot thật sự chạy `REACTIVE`.

## 12. Checklist áp dụng vào dự án thật

- [ ] Server thật sự chạy **Spring WebFlux**, không vô tình chuyển sang MVC vì dependency.
- [ ] Annotated Controller và `RouterFunction` nằm trong cùng HTTP WebFlux application context.
- [ ] Có một `SecurityWebFilterChain` phù hợp với URL của **cả hai** hoặc nếu dùng nhiều chain thì có `securityMatcher` và `@Order` bao phủ đúng.
- [ ] `authorizeExchange` kiểm tra đúng HTTP method, path và authority; rule cuối an toàn.
- [ ] Xác thực (HTTP Basic, OIDC login, JWT, session) được cấu hình ở WebFilter chain thay vì chỉ trong một loại handler.
- [ ] Test **401 khi chưa xác thực**, **403 khi thiếu quyền**, **200 khi đủ quyền** cho từng kiểu endpoint.
- [ ] Functional `HandlerFilterFunction` chỉ dùng cho logic cục bộ phù hợp, không làm thay nhiệm vụ bảo vệ Controller.
- [ ] CSRF, CORS, error handling, security headers và authorization ở cấp tài nguyên được xem xét theo kiểu client/credential thực.
- [ ] Test chạy cùng ứng dụng đầy đủ để tránh bỏ sót bean route hoặc security config ở các test slice.

**Kết luận:** Với Spring Security reactive, lớp quyết định bảo mật HTTP là **`WebFilter` và `SecurityWebFilterChain`**, chứ không phải annotation hay phong cách định nghĩa route. Khi một Controller và một RouterFunction cùng chạy dưới WebFlux HTTP server, một bean `SecurityWebFilterChain` không bị giới hạn sai matcher sẽ áp dụng nhất quán cho cả hai. Hãy chứng minh điều đó bằng kết quả 401/403/200 trên **từng endpoint**.

### Tham khảo chính thức

- [Spring Security — WebFlux Security: cùng WebFilter cho WebFlux và WebFlux.fn, nhiều chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive HTTP requests / authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Framework — WebFlux functional endpoints, RouterFunctionMapping và HandlerFilterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux DispatcherHandler và HandlerMapping](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications, WebTestClient và WebFluxTest](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Security — Reactive test support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
