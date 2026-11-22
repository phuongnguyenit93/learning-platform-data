# ServerAuthenticationConverter và chuyển đổi thông tin xác thực từ yêu cầu

## 1. Bài toán và mục tiêu

Trong ứng dụng **Spring Security Reactive** chạy trên Spring WebFlux, một client có thể gửi thông tin đăng nhập qua HTTP Basic, Bearer token, form data, chứng chỉ khách hàng hoặc một giao thức riêng. Tuy nhiên, phần **kiểm tra thông tin đó có hợp lệ không** cần một mô hình chung để không phải viết logic xác thực trong từng controller.

`ServerAuthenticationConverter` giải quyết **bước chuyển đổi đầu vào HTTP thành một ứng viên `Authentication`**. Nó không tự quyết định người dùng đã đăng nhập thành công. Bước kiểm tra thực sự thường thuộc về `ReactiveAuthenticationManager`; `AuthenticationWebFilter` phối hợp các bước và đưa authentication đã xác minh vào ngữ cảnh reactive của request.

Sau bài này, bạn có thể:

- Trình bày chính xác hợp đồng `ServerAuthenticationConverter.convert(ServerWebExchange)` và ba kết quả: có ứng viên, không có ứng viên, hoặc lỗi.
- Phân biệt **trích xuất credentials**, **xác thực credentials**, **lưu/lan truyền SecurityContext** và **phân quyền truy cập**.
- Giải thích `Mono.empty()` là “không thực hiện lần xác thực này”, **không** có nghĩa là request được cấp quyền.
- Nhận diện các converter có sẵn như HTTP Basic, Bearer, form login và trường hợp nào thực sự cần converter tùy chỉnh.
- Tạo một ví dụ Java 17+ gồm converter, `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, security chain, endpoint WebFlux và kiểm thử.
- Phát hiện những sai lầm về `isAuthenticated`, xử lý lỗi, header không đáng tin, `block()`, `subscribe()`, body request, CSRF và thứ tự security filters.

Đây là bài thuộc nhóm **Xác thực reactive**. Ví dụ minh họa một cơ chế nhận credentials do bài học tự định nghĩa; trong hệ thống thật, ưu tiên chuẩn đã được Spring Security hỗ trợ và sử dụng HTTPS, password hashing, quản lý khóa/token và chính sách bảo mật thích hợp.

## 2. Vị trí của converter trong luồng xác thực

Luồng khái quát:

~~~text
Client HTTP request
      |
      v
ServerWebExchange (request headers, cookies, query, body, TLS info...)
      |
      v
SecurityWebFilterChain / AuthenticationWebFilter
      |
      +--> Matcher: có cần thử authentication ở request này không?
      |
      v
ServerAuthenticationConverter.convert(exchange)
      |
      +--> Mono.empty()    : không có credentials phù hợp -> không thử lần này
      +--> Mono.error(...) : request có credentials sai định dạng -> lỗi
      +--> Mono<Authentication> : tạo ứng viên chưa được xác minh
                                       |
                                       v
                         ReactiveAuthenticationManager
                                       |
                          +------------+------------+
                          |                         |
                   Xác thực thất bại         Xác thực thành công
                          |                         |
                    Failure handler        Authentication đã được tin cậy
                                                    |
                                                    v
                                     Reactive SecurityContext / Reactor Context
                                                    |
                                                    v
                                        Authorization của request
                                                    |
                                                    v
                                           WebFlux handler
~~~

**Vai trò tách biệt:**

| Lớp | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `ServerAuthenticationConverter` | Request đang trình bày credentials nào, ở định dạng nào? | Lấy username/password từ Basic header hoặc chuỗi Bearer token |
| `ReactiveAuthenticationManager` | Credentials/token đó có hợp lệ không, và danh tính/quyền nào được cấp? | Kiểm tra mật khẩu, JWT signature/claims, kết quả IdP |
| `AuthenticationWebFilter` | Khi nào gọi converter/manager và xử lý thành công/thất bại ra sao? | Gắn context cho pipeline, gọi success/failure handler |
| `ServerSecurityContextRepository` | Có lưu/tải SecurityContext giữa những request không? | WebSession hoặc no-op |
| `ReactiveSecurityContextHolder` | Downstream đọc SecurityContext của subscription bằng cách nào? | `Mono<SecurityContext>` trong Reactor Context |
| Authorization | Danh tính đã xác thực có được làm thao tác này không? | `authenticated()`, `hasRole("ADMIN")`, quyền sở hữu đơn hàng |

Một converter trả về `Authentication` không đồng nghĩa “đã đăng nhập”. Đây chỉ là **authentication request token** cần được kiểm tra bởi manager. Tên `Authentication` được dùng cho cả token chưa xác minh và token đã xác minh, vì interface này mô tả cả hai trạng thái.

## 3. Hợp đồng chính xác của ServerAuthenticationConverter

Interface nằm trong package:

~~~text
org.springframework.security.web.server.authentication.ServerAuthenticationConverter
~~~

Chữ ký khái niệm:

~~~java
@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

Vì chỉ có một abstract method, có thể triển khai bằng class, lambda hoặc method reference. Đối số `ServerWebExchange` cho phép đọc HTTP request hiện tại. Kiểu trả về `Mono<Authentication>` thể hiện quá trình chuyển đổi là một phần của pipeline Reactor.

### 3.1. Ba kết quả quan trọng

**Kết quả A — `Mono.empty()`: không có ứng viên phù hợp**

Ví dụ converter dành cho header `X-Learn-User` và `X-Learn-Key` nhưng request không mang cả hai header. Converter nên trả `Mono.empty()` để nói **không có lần xác thực nào theo cơ chế đó**. `AuthenticationWebFilter` tiếp tục filter chain; nếu endpoint bảo vệ cần đăng nhập thì tầng authorization/entry point vẫn có thể từ chối với 401.

**Kết quả B — `Mono.just(authentication)`: có credentials để kiểm tra**

Ví dụ request mang hai header hợp lệ về cấu trúc. Converter tạo một `UsernamePasswordAuthenticationToken` với `isAuthenticated() == false`. Manager sẽ kiểm tra giá trị thực tế, rồi mới tạo token đã xác thực có authorities phù hợp.

**Kết quả C — `Mono.error(authenticationException)`: credentials có mặt nhưng sai định dạng**

Ví dụ client gửi `X-Learn-User` nhưng bỏ `X-Learn-Key`, hoặc header thiếu dữ liệu cần thiết. Chọn lỗi kiểu `BadCredentialsException` để mô tả dữ liệu không hợp lệ. Khi được xử lý trong `AuthenticationWebFilter` với failure handler phù hợp, nó dẫn tới phản hồi lỗi xác thực. Không tự biến lỗi parse thành `Mono.empty()` nếu điều đó khiến hệ thống lờ đi credential sai và rẽ sang cơ chế khác ngoài ý muốn.

| Tình huống | Converter nên phát gì? | Ý nghĩa |
| --- | --- | --- |
| Không có dấu hiệu của scheme này | `Mono.empty()` | Không thử authentication theo scheme này |
| Header hợp lệ về cú pháp | `Mono.just(unauthenticatedToken)` | Gửi credentials tới manager |
| Scheme được nhận ra nhưng payload thiếu/sai định dạng | `Mono.error(BadCredentialsException)` | Từ chối đầu vào không hợp lệ |
| Password không đúng | **Manager** phát `AuthenticationException` | Converter không chịu trách nhiệm kiểm tra mật khẩu |
| Request đã xác thực nhưng thiếu role | **Authorization** từ chối | Không phải lỗi chuyển đổi |

Một số converter/framework tích hợp sẵn có quy tắc riêng cho header không phù hợp hoặc token hỏng; khi sử dụng chúng, cần bám vào hợp đồng cụ thể và exception mapping thực tế thay vì áp đặt máy móc mọi trường hợp.

### 3.2. Không bao giờ tự nâng trạng thái xác thực trong converter

Sai:

~~~java
// SAI: đọc username do client gửi rồi tự coi là đã xác thực.
return Mono.just(
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
~~~

Một attacker có thể tự gửi `username=admin`; nếu converter tự cấp `ROLE_ADMIN`, ứng dụng đã **bỏ qua xác thực**.

Mẫu đúng cho yêu cầu username/password:

~~~java
return Mono.just(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword));
~~~

`rawPassword` mới được manager xử lý. Trong production, manager cần so sánh với password hash bằng `PasswordEncoder` phù hợp, kiểm soát đăng nhập thất bại và tránh lưu/log dữ liệu nhạy cảm. Với JWT, converter thường tạo token đại diện cho Bearer credential, còn quá trình xác minh chữ ký/claims và chuyển authorities thuộc thành phần authentication.

### 3.3. `Mono.empty()` khác `Mono.just(null)`

Không dùng `Mono.just(null)`: Reactor không cho phép giá trị null trong `Mono.just`. Trường hợp không có credentials, dùng `Mono.empty()`. Nếu cần báo lỗi xác thực, dùng `Mono.error(...)`.

## 4. Các converter sẵn có và khi nào không nên tự viết

Spring Security Reactive cung cấp converter cho các cơ chế thông dụng, tùy phiên bản và dependency:

| Converter | Loại thông tin nhận từ request | Lưu ý |
| --- | --- | --- |
| `ServerHttpBasicAuthenticationConverter` | `Authorization: Basic ...` | Chuyển cặp username/password theo HTTP Basic |
| `ServerBearerTokenAuthenticationConverter` | Bearer token từ HTTP request | Chuyển token thành authentication request; bản thân converter không chứng minh JWT hợp lệ |
| `ServerFormLoginAuthenticationConverter` | Dữ liệu form đăng nhập | Phù hợp với flow form-login có cơ chế CSRF/session khi cần |
| `ServerX509AuthenticationConverter` | Thông tin chứng chỉ client trong SSL/TLS exchange | Cần cấu hình TLS và xác minh danh tính chứng chỉ đúng cách |
| `DelegatingServerAuthenticationConverter` | Thử nhiều converter theo thứ tự | Tránh xung đột scheme hoặc vô tình bỏ qua lỗi |

Trong OAuth2 Resource Server, thông thường bạn cấu hình `oauth2ResourceServer(...jwt(...))` hoặc opaque token theo mô hình Spring Security, **không** tự parse JWT trong controller hay converter. Thành phần chuyên dụng sẽ đảm nhiệm validation và mapping authorities. Cấu hình Basic/form-login cũng thường đã đăng ký converter phù hợp bên trong security filter chain.

**Khi cần converter tùy chỉnh?** Khi API có một scheme credentials riêng được yêu cầu rõ ràng, hoặc cần chuyển một đầu vào đặc thù thành authentication request token mà manager hiểu được. Trước khi tạo scheme mới trong sản phẩm thật, xem có thể sử dụng HTTP Basic, OAuth2/OIDC, mTLS hoặc chuẩn hỗ trợ sẵn không.

`ServerAuthenticationConverter` trong WebFlux không phải `AuthenticationConverter` của Servlet. Tương ứng:
- WebFlux: `ServerWebExchange`, `Mono<Authentication>`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager`.
- Servlet: `HttpServletRequest` và các thành phần `Filter`/`AuthenticationManager` tương ứng.

## 5. Xử lý HTTP request đúng cách

Một converter thường đọc `exchange.getRequest().getHeaders()`, `getCookies()`, query parameters hoặc metadata TLS. Các nguyên tắc quan trọng:

1. **Xác định đúng nguồn tin cậy.** Header `X-User` do client tự đặt không chứng minh danh tính; nếu hạ tầng reverse proxy đã xác thực và đưa thông tin người dùng vào header, phải bảo đảm proxy xóa/ghi đè header từ bên ngoài và ràng buộc trust boundary. Không tin header người dùng tự khai là authentication.
2. **Kiểm tra dấu hiệu scheme trước.** Không có credential dành cho converter hiện tại nên trả `Mono.empty()` để những cơ chế khác hoặc authorization tiếp tục xử lý.
3. **Nếu scheme được nhận ra nhưng hỏng, từ chối rõ ràng.** Không dùng fallback cho phép request đi tiếp như anonymous khi nó đang cố đăng nhập với credential sai.
4. **Kiểm tra định dạng và giới hạn kích thước.** Tránh split chuỗi thiếu kiểm tra, header quá lớn, ký tự không hợp lệ hoặc dữ liệu lặp nhiều lần.
5. **Không log secrets.** Dù chỉ đang parse, token/password là dữ liệu nhạy cảm; không đưa vào log, metrics labels hoặc exception message trả về client.
6. **Không chặn event-loop.** Converter cần trả `Mono`; nếu có thao tác I/O, dùng API reactive. Không gọi `block()` hoặc `subscribe()` trong converter.
7. **Không tự cấp authorities.** Có `Authentication` để gửi sang manager là đủ; kết quả đã xác thực phải do bước tin cậy tạo ra.
8. **Đọc request body cẩn trọng.** Request body của WebFlux là dòng dữ liệu; việc tự tiêu thụ `getBody()` có thể khiến downstream không đọc lại được. Ưu tiên converter/codec đã được hỗ trợ cho form hoặc dùng phương án đảm bảo chỉ đọc body một lần, giới hạn kích thước và xử lý bộ nhớ.

Không có một converter nào phải thực hiện đầy đủ mọi việc trên. Converter tốt thường **nhỏ, dễ kiểm thử và chỉ chịu trách nhiệm chuyển đổi định dạng**.

## 6. Ví dụ chạy được: converter đọc hai header học tập

Ví dụ này dùng Java 17, Spring Boot 3.3.13 (dòng Spring Security 6.x) và Gradle. Ta định nghĩa scheme **chỉ để học**:

~~~text
X-Learn-User: learner
X-Learn-Key: local-pass
~~~

Dấu hiệu hợp lệ về cấu trúc là **có đúng một giá trị không rỗng cho mỗi header**. Converter chỉ chuyển chúng thành unauthenticated token. Manager demo có hai tài khoản hard-code để bạn phân biệt authentication với authorization:

- `learner / local-pass` → `ROLE_USER`.
- `admin / admin-pass` → `ROLE_ADMIN`.

**Tuyệt đối không áp dụng scheme này trực tiếp vào production.** Nó không tuân theo một giao thức authentication chuẩn, credentials đơn giản và hard-code, chưa có password hashing, rotation, rate limiting, TLS termination, account lockout hoặc audit bảo mật. Không dùng các tên/giá trị này làm secrets thật.

Cấu trúc:

~~~text
converter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── DemoHeaderAuthenticationConverter.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── DemoHeaderAuthenticationConverterTest.java
~~~

### 6.1. Cấu hình Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'converter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản thư viện Spring WebFlux/Spring Security/Reactor tương thích với phiên bản Boot đã chọn. Nếu làm dự án thật, chọn nhánh được hỗ trợ và có bản vá bảo mật mới nhất của tổ chức; không xem version minh họa là khuyến nghị vận hành lâu dài.

### 6.2. Ứng dụng khởi động

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.3. Converter: chỉ trích xuất và tạo token chưa xác thực

`src/main/java/demo/DemoHeaderAuthenticationConverter.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class DemoHeaderAuthenticationConverter
        implements ServerAuthenticationConverter {

    private static final String USER_HEADER = "X-Learn-User";
    private static final String KEY_HEADER = "X-Learn-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> users = exchange.getRequest()
                .getHeaders().getOrEmpty(USER_HEADER);
        List<String> keys = exchange.getRequest()
                .getHeaders().getOrEmpty(KEY_HEADER);

        // Hai header đều vắng: cơ chế này không thực hiện xác thực.
        if (users.isEmpty() && keys.isEmpty()) {
            return Mono.empty();
        }

        // Có dấu hiệu đăng nhập nhưng thiếu, lặp hoặc rỗng dữ liệu.
        if (users.size() != 1 || keys.size() != 1
                || users.get(0).isBlank() || keys.get(0).isBlank()) {
            return Mono.error(
                    new BadCredentialsException("Invalid demo headers"));
        }

        String username = users.get(0);
        String password = keys.get(0);

        // Chỉ là ứng viên; manager sẽ xác minh ở bước tiếp theo.
        Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);
        return Mono.just(candidate);
    }
}
~~~

**Phân tích dòng quan trọng:**
- `getOrEmpty` cho phép xử lý trường hợp header hoàn toàn không có mà không gặp `NullPointerException`.
- Nếu cả hai header vắng, `Mono.empty()` báo **không có authentication attempt** từ converter.
- Nếu chỉ một header xuất hiện, hoặc có nhiều giá trị, hoặc chuỗi rỗng/trắng, `BadCredentialsException` báo payload sai định dạng.
- Nếu có cặp header hợp lệ về hình thức, converter tạo `UsernamePasswordAuthenticationToken.unauthenticated`, **không** tự gọi database hay quyết định mật khẩu đúng.
- Đây là ví dụ xử lý header ở mức nhập môn; một sản phẩm thật phải có chiến lược giới hạn kích thước, chống header smuggling, proxy trust và xác thực theo chuẩn được thiết kế riêng.

### 6.4. ReactiveAuthenticationManager + AuthenticationWebFilter

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveAuthenticationManager demoAuthenticationManager() {
        return authentication -> Mono.defer(() -> {
            String user = authentication.getName();
            String password = String.valueOf(authentication.getCredentials());

            if ("learner".equals(user) && "local-pass".equals(password)) {
                return Mono.just(
                        UsernamePasswordAuthenticationToken.authenticated(
                                user, null,
                                List.of(new SimpleGrantedAuthority("ROLE_USER"))));
            }

            if ("admin".equals(user) && "admin-pass".equals(password)) {
                return Mono.just(
                        UsernamePasswordAuthenticationToken.authenticated(
                                user, null,
                                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
            }

            return Mono.error(
                    new BadCredentialsException("Invalid demo credentials"));
        });
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager demoAuthenticationManager) {

        AuthenticationWebFilter demoFilter =
                new AuthenticationWebFilter(demoAuthenticationManager);

        demoFilter.setServerAuthenticationConverter(
                new DemoHeaderAuthenticationConverter());

        demoFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        demoFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());

        HttpStatusServerEntryPoint unauthorized =
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

        demoFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(unauthorized));

        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(unauthorized))
                .addFilterAt(demoFilter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Vì sao từng phần cần thiết:**

1. **Manager** nhận credentials từ candidate, đối chiếu demo account và tạo token đã xác thực với `ROLE_USER` hoặc `ROLE_ADMIN`; trường hợp sai phát `BadCredentialsException`.
2. **`AuthenticationWebFilter`** là filter điều phối, không phải converter. Nó gọi converter trước, gọi manager khi có candidate, xử lý kết quả và cung cấp authentication thành công cho downstream pipeline.
3. **`setRequiresAuthenticationMatcher("/api/**")`** giới hạn request mà filter này xem xét. Matcher không cấp quyền: các rule trong `authorizeExchange` mới quyết định truy cập.
4. **`setAuthenticationFailureHandler`** trả HTTP 401 khi converter/manager phát lỗi authentication phù hợp. Không trả thông tin chi tiết credentials cho client.
5. **`exceptionHandling(...authenticationEntryPoint(...))`** định nghĩa response 401 khi authorization yêu cầu authentication nhưng không tìm thấy người dùng hợp lệ.
6. **`addFilterAt(..., AUTHENTICATION)`** đặt custom `AuthenticationWebFilter` vào vị trí xác thực của reactive security chain; đây là API dành cho `WebFilter`, không phải Servlet `Filter`.
7. **No-op SecurityContextRepository** không giữ authentication giữa các request. Tuy vậy, authentication đã xác minh vẫn được gắn với Reactor Context của **request hiện tại**.
8. **`httpBasic`/`formLogin` bị tắt** để luồng demo chỉ dùng converter mới. Nếu cần đồng thời nhiều scheme, phải thiết kế thứ tự matcher/filter và thử nghiệm xung đột.
9. **`hasRole("ADMIN")`** theo quy ước kiểm tra authority `ROLE_ADMIN`; manager demo cấp authority đó cho tài khoản admin.

Cấu hình chủ ý chỉ có các endpoint GET, vì vậy ví dụ không tắt CSRF. Nếu thêm POST/PUT/DELETE hoặc browser credential tự động gửi, phải thiết kế CSRF theo threat model thực tế. Scheme demo này cũng **không phải một giải pháp xác thực production**.

### 6.5. WebFlux controller

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "user:"
                        + context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("admin-only");
    }
}
~~~

`/api/me` đọc `Authentication` đã được xác minh từ `ReactiveSecurityContextHolder`. Nếu converter tự tạo token nhưng manager thất bại, handler không được trả `user:...`. Không dùng `SecurityContextHolder` kiểu thread-local của Servlet và không gọi `block()` trong controller.

### 6.6. Chạy và kiểm tra bằng curl

Đứng trong thư mục dự án, cần JDK 17 và Gradle phù hợp. Chạy:

~~~bash
gradle bootRun
~~~

Nếu đã có Gradle Wrapper, có thể chạy `./gradlew bootRun`. Ở terminal khác:

~~~bash
# Không cần credentials trên endpoint công khai.
curl -i http://localhost:8080/api/public

# Không có bất kỳ header xác thực nào.
curl -i http://localhost:8080/api/me

# Cặp header hợp lệ: tài khoản người học.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: local-pass'   http://localhost:8080/api/me

# Có username nhưng thiếu secret.
curl -i -H 'X-Learn-User: learner'   http://localhost:8080/api/me

# Có đủ header nhưng secret sai.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: wrong'   http://localhost:8080/api/me

# Đã xác thực nhưng không đủ role.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: local-pass'   http://localhost:8080/api/admin

# Đủ role ADMIN.
curl -i   -H 'X-Learn-User: admin'   -H 'X-Learn-Key: admin-pass'   http://localhost:8080/api/admin
~~~

**Kết quả mong đợi:**

| Request | Converter | Manager / Authorization | HTTP |
| --- | --- | --- | --- |
| `/api/public`, không headers | `Mono.empty()` | Route cho phép anonymous | **200**, body `public` |
| `/api/me`, không headers | `Mono.empty()` | Authorization yêu cầu login | **401** |
| `/api/me`, `learner/local-pass` | Candidate chưa xác thực | Manager xác minh USER | **200**, body `user:learner` |
| `/api/me`, thiếu key | `BadCredentialsException` | Failure handler | **401** |
| `/api/me`, key sai | Candidate hợp lệ cú pháp | Manager từ chối | **401** |
| `/api/admin`, `learner/local-pass` | Candidate | USER thiếu `ROLE_ADMIN` | **403** |
| `/api/admin`, `admin/admin-pass` | Candidate | ADMIN đủ quyền | **200**, body `admin-only` |

Các response lỗi có thể có body/header khác nhau theo cấu hình/version; bảng chốt **status và body của trường hợp thành công**. Với API thật, tránh truyền demo secrets trong terminal dùng chung hoặc lưu chúng trong shell history.

### 6.7. Vì sao ví dụ có cả 401 và 403?

- **401 Unauthorized:** chưa có credentials phù hợp hoặc quá trình xác thực thất bại. Ở đây API entry point/failure handler chủ động dùng HTTP 401.
- **403 Forbidden:** manager đã xác minh danh tính, nhưng authorization không cho phép quyền `ADMIN`.

Nếu đổi converter thành một hàm luôn trả token có `ROLE_ADMIN` và `isAuthenticated=true`, bạn đã vô tình bỏ qua bước xác minh; đó là lỗi bảo mật, không phải cách viết converter nhanh hơn.

## 7. Unit test độc lập cho converter

Một converter nên được kiểm thử **riêng với manager**. Điều này cho phép chứng minh nó chỉ parse request và trả một authentication candidate, trong khi manager mới kiểm tra password. Thử nghiệm dưới đây dùng `MockServerWebExchange`, JUnit 5 và Reactor `StepVerifier`.

`src/test/java/demo/DemoHeaderAuthenticationConverterTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class DemoHeaderAuthenticationConverterTest {

    private final DemoHeaderAuthenticationConverter converter =
            new DemoHeaderAuthenticationConverter();

    @Test
    void missingHeadersMeanNoAuthenticationAttempt() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me"));

        StepVerifier.create(converter.convert(exchange))
                .verifyComplete();
    }

    @Test
    void validShapeProducesUnauthenticatedCandidate() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me")
                        .header("X-Learn-User", "learner")
                        .header("X-Learn-Key", "local-pass"));

        StepVerifier.create(converter.convert(exchange))
                .assertNext(authentication -> {
                    assertEquals("learner", authentication.getName());
                    assertEquals("local-pass",
                            authentication.getCredentials());
                    assertFalse(authentication.isAuthenticated());
                })
                .verifyComplete();
    }

    @Test
    void partialHeadersAreRejected() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me")
                        .header("X-Learn-User", "learner"));

        StepVerifier.create(converter.convert(exchange))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** ba test hoàn thành thành công nếu file, class, dependencies được tạo đúng như ví dụ. Đây là dự đoán theo mã nguồn, không phải khẳng định đã chạy trên máy bạn.

Test thứ hai đặc biệt quan trọng: `assertFalse(authentication.isAuthenticated())` ngăn nguy cơ converter tự xác minh người dùng. Test thứ nhất chứng minh no credentials phát **completion không có item**. Test thứ ba chứng minh một yêu cầu có dấu hiệu xác thực nhưng thiếu thông tin không bị lặng lẽ bỏ qua.

Để kiểm tra **integration của SecurityWebFilterChain**, cần thêm kiểm thử WebFlux qua `WebTestClient` với các trường hợp 200, 401, 403 ở phần trên. Unit test chỉ kiểm tra converter, không chứng minh filter đã được đăng ký đúng order hoặc manager có đúng logic.

## 8. AuthenticationWebFilter điều phối những gì?

Với request khớp `setRequiresAuthenticationMatcher`, `AuthenticationWebFilter` về khái niệm:

1. Gọi converter để lấy ứng viên `Authentication`.
2. Nếu converter trả `Mono.empty()`, không thử xác thực theo filter này; cho request đi tiếp trong chain.
3. Nếu converter phát candidate, gọi `ReactiveAuthenticationManager.authenticate(authentication)`.
4. Nếu manager xác thực thành công, Spring Security đưa Authentication/Context vào luồng reactive của request, xử lý success handler và tiếp tục chain.
5. Nếu converter hoặc manager phát `AuthenticationException` được xử lý theo hợp đồng, gọi failure handler. Kết quả chính xác phụ thuộc cấu hình, entry point và loại exception; lỗi hệ thống không nhất thiết là lỗi credentials của client.
6. Authorization diễn ra ở phần thích hợp của chain, quyết định có được truy cập resource hay không.

**Các điểm mở rộng:** `setServerAuthenticationConverter`, `setRequiresAuthenticationMatcher`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler`, `setSecurityContextRepository`. Có thể dùng manager resolver nếu mỗi request cần chọn cơ chế manager khác nhau theo chính sách, nhưng không tự tạo lẫn lộn nhiều filter/manager khi framework đã hỗ trợ scheme sẵn.

Sự khác nhau giữa các tín hiệu:

| Tín hiệu | Ý nghĩa với filter |
| --- | --- |
| Converter `Mono.empty()` | Bỏ qua authentication attempt của filter này |
| Converter `Mono.just(candidate)` | Thử xác thực bằng manager |
| Converter `Mono.error(BadCredentialsException)` | Xử lý như một lỗi authentication phù hợp |
| Manager `Mono.just(verified)` | Authentication thành công, có thể tiếp tục authorization |
| Manager `Mono.error(BadCredentialsException)` | Credential không hợp lệ |
| Manager `Mono.empty()` | Manager không cung cấp kết quả xác thực; ý nghĩa cụ thể tùy manager/filter |
| Authorization từ chối | Người gọi không được truy cập, dù quá trình chuyển đổi có thể đã đúng |

Trong production, không dựa vào converter để thực thi những quy tắc quyền nghiệp vụ như “đơn hàng có thuộc người này không”; những kiểm tra đó thuộc authorization/service sau khi danh tính đã được xác minh.

## 9. Mono.empty(), lỗi cú pháp và nhiều authentication schemes

Giả sử API hỗ trợ cả Basic và Bearer. Khi request mang `Authorization: Bearer ...`, một converter dành cho Basic cần nhận ra **không thuộc cơ chế của nó** và có thể trả `Mono.empty()`. Một converter chuyên về Bearer nhận request đó, chuyển sang token phù hợp. Nếu scheme Bearer hiện diện nhưng token bị lỗi, converter/manager tương ứng phải từ chối đúng cách; đừng chủ động coi nó như “không có credentials” chỉ để cho phép một fallback kém an toàn.

Một converter phối hợp như `DelegatingServerAuthenticationConverter` có thể thử nhiều delegate, nhưng phải hiểu cách nó dừng khi có kết quả, tiếp tục khi empty và xử lý lỗi. Thứ tự converter có thể ảnh hưởng kết quả. Với nhiều `AuthenticationWebFilter`, cần kiểm soát matcher, authentication order và failure handling cho từng filter.

**Đặc biệt chú ý fallback nguy hiểm:**

~~~java
// SAI về mặt bảo mật nếu mọi token hỏng bị biến thành "không có thông tin".
return parseBearer(exchange)
        .onErrorResume(error -> Mono.empty());
~~~

Cách này nuốt cả lỗi bất thường. Một token hỏng có thể bị bỏ qua, rồi một cơ chế khác hoặc rule public xử lý request ngoài dự kiến. Hãy phân biệt `Mono.empty()` khi scheme không có, `AuthenticationException` khi scheme đã nhận diện mà credential sai, và lỗi hạ tầng khi việc xác thực không thể thực hiện.

## 10. Request body, login form và nguồn dữ liệu bất đồng bộ

Nhiều API login nhận JSON body như:

~~~json
{
  "username": "learner",
  "password": "local-pass"
}
~~~

Về mặt kỹ thuật, converter có thể đọc request body bất đồng bộ và tạo authentication candidate. Nhưng trong WebFlux, body là một `Flux<DataBuffer>` có vòng đời tiêu thụ riêng; không được gọi `block()` để lấy JSON, không tùy tiện subscribe thêm lần nữa và không giả định body sẽ tự có lại cho downstream.

Nếu dùng form login, ưu tiên các cơ chế đã được Spring Security cung cấp. Với login JSON thực sự cần tùy chỉnh, nên:
- Giới hạn request method/path/content type/size trước khi parse.
- Dùng codec/decoder reactive phù hợp và validate payload.
- Tránh giữ password trong log hoặc state sống quá lâu.
- Thiết kế chuyện body được đọc **một lần**, và nếu downstream cần đọc lại thì phải có cơ chế caching/decorating an toàn, có giới hạn.
- Cấu hình CSRF/CORS và cookie handling dựa theo loại client và cách credentials được gửi.

**Bẫy phổ biến:** converter đọc hết body trong một subscription, còn controller cố đọc lại body lần nữa; kết quả có thể rỗng hoặc gặp lỗi do body đã được consume. Việc “đổi từ `block()` sang `flatMap`” chưa tự sửa sai lầm tiêu thụ body hai lần.

## 11. Reactor Context, session và khả năng đọc principal

Trong WebFlux, sau khi authentication thành công, downstream thường đọc context bằng:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

Nó phụ thuộc vào Reactor Context của subscription đang chạy, không phải `ThreadLocal` mặc định của Servlet. Việc chuyển scheduler bằng `publishOn` hoặc `subscribeOn` trong **cùng pipeline** không mặc nhiên làm mất Reactor Context.

Nhưng converter/service tự gọi `subscribe()` có thể tạo subscription độc lập, không được bảo đảm có context request và không còn error/cancellation flow đúng. Ví dụ sai:

~~~java
converter.convert(exchange).subscribe(candidate -> {
    // SAI: tự làm authentication ngoài security filter chain.
    audit(candidate);
});
return Mono.empty();
~~~

Đây là đoạn minh họa anti-pattern, không phải chương trình độc lập; `audit` là hàm giả định. Hãy để `AuthenticationWebFilter` quản lý subscription và kết quả authentication, hoặc compose các thao tác cần thiết vào publisher của chuỗi chính.

**Lưu `SecurityContext` khác với convert:** `ServerSecurityContextRepository` quyết định cách tải/lưu authentication giữa các request. Demo dùng `NoOpServerSecurityContextRepository` vì mỗi request phải gửi lại header. Điều đó không ngăn `ReactiveSecurityContextHolder` thấy authentication của request hiện tại. Nếu triển khai phiên đăng nhập (WebSession) hoặc OAuth2 login tương tác, thiết kế persistence riêng và không tùy tiện dùng no-op.

## 12. Thứ tự, matcher và lỗi HTTP

Ở Spring Security Reactive, `SecurityWebFilterChain` có thể chứa nhiều filter. `SecurityWebFiltersOrder.AUTHENTICATION` xác định vị trí dành cho authentication. Một ứng dụng có nhiều chain thì `securityMatcher` và `@Order` của các chain quyết định chain nào áp dụng cho request.

Phân biệt:
- **Filter matcher:** filter authentication cụ thể có thử convert request này hay không?
- **Security chain matcher:** security chain nào được chọn cho request?
- **Authorization rule:** sau authentication, route yêu cầu quyền gì?
- **Failure handler:** một lần xác thực thất bại được diễn đạt thành HTTP response thế nào?
- **Authentication entry point:** khi cần xác thực nhưng chưa có danh tính phù hợp, phản hồi ra sao?

Nếu `/api/me` trả 401 dù gửi đúng headers, cần kiểm tra không chỉ converter, mà cả manager, filter registration, chain matcher, path matcher, thứ tự filter, exception handling và context propagation.

Nếu `/api/admin` trả 403 cho tài khoản learner, đó là **đúng kỳ vọng** khi manager cấp `ROLE_USER`, còn URL yêu cầu `ROLE_ADMIN`. Đừng nới `permitAll()` hoặc tự thêm `ROLE_ADMIN` vào converter để “sửa” 403.

## 13. Các lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Converter tự đặt `isAuthenticated=true` | Tin thông tin tự khai của client, bỏ qua bước kiểm tra | Tạo token chưa xác thực, manager xác minh |
| Trả `Mono.empty()` cho mọi lỗi parse | Credential sai bị bỏ qua lặng lẽ | Chỉ empty khi scheme không hiện diện; dùng AuthenticationException nếu đã nhận diện nhưng không hợp lệ |
| Manager làm cả HTTP parsing | Gắn chặt xác thực với WebFlux request, khó tái sử dụng | Converter parse request, manager xác minh token |
| Converter gọi DB blocking trên event-loop | Giảm thông lượng hoặc lỗi blocking | I/O reactive; cô lập legacy blocking đúng cách nếu không thể thay |
| Converter tự `block()`/`subscribe()` | Subscription/context/cancellation không còn được điều phối | Trả `Mono` cho framework |
| Tự tin tưởng `X-User` do client gửi | Dễ giả mạo người dùng | Dùng credentials có thể kiểm tra hoặc cơ chế trusted proxy được khóa chặt |
| Đọc body hai lần | Body rỗng hoặc lỗi, leak memory khi caching sai | Decoder reactive và quản lý một lần tiêu thụ |
| Lẫn authorization với authentication | Kiểm tra role chưa đủ, hoặc cấp role trong converter | Chỉ cấp authorities sau verification; kiểm tra quyền trong authorization |
| Dùng `AuthenticationConverter` Servlet trong WebFlux | API kiểu request/filter không phù hợp | Dùng `ServerAuthenticationConverter` và `AuthenticationWebFilter` |
| Hiểu 401/403 như nhau | Debug sai tầng | 401 thường do authentication; 403 thường do đã login nhưng thiếu quyền |
| Chỉ thử `/api/me` đúng credentials | Bỏ sót bypass và trường hợp hỏng payload | Thử anonymous, missing/duplicate/malformed, wrong password, wrong role |
| Cho secret vào log/exception | Rò rỉ credentials | Log mã lỗi và correlation ID, không log raw credential |

## 14. Câu hỏi tự kiểm tra

1. `ServerAuthenticationConverter.convert(exchange)` nhận đối tượng nào và trả kiểu Publisher nào?
2. `Mono.empty()` có nghĩa request đã được xác thực và cho phép hay không? Ai xử lý quyết định truy cập sau đó?
3. Khi gửi `X-Learn-User` nhưng thiếu `X-Learn-Key`, demo trả gì? Khi đủ hai header nhưng key sai, bước nào phát hiện?
4. Vì sao `UsernamePasswordAuthenticationToken.unauthenticated` thích hợp hơn token đã `authenticated` khi converter chỉ đọc header?
5. `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và `ReactiveSecurityContextHolder` có trách nhiệm khác nhau như thế nào?
6. Nếu endpoint public có header đăng nhập sai và filter vẫn được thử trên route đó, bạn có nên mặc định kết quả là 200 vì rule `permitAll()` không? Vì sao?
7. Khi nào cần `DelegatingServerAuthenticationConverter`? Làm sao tránh scheme này nuốt lỗi scheme khác?
8. Vì sao dùng converter sẵn có của Resource Server cho JWT thường an toàn và dễ bảo trì hơn tự parse token trong controller?
9. Trường hợp nào bạn nên dùng `Mono.error(BadCredentialsException)` thay vì `Mono.empty()`?
10. Vì sao converter đọc JSON body phải quản lý việc tiêu thụ body và kích thước dữ liệu?

**Đáp án gợi ý ngắn:** (1) `ServerWebExchange` → `Mono<Authentication>`; (2) không, chỉ bỏ qua lần thử của converter, authorization/entry point vẫn có thể từ chối; (3) converter báo lỗi thiếu key, manager từ chối key sai; (4) converter chưa kiểm chứng danh tính; (5) filter điều phối, manager xác minh, holder cung cấp context trong Reactor; (6) không, credential sai có thể kích hoạt failure handler dù endpoint có rule public; (7) nhiều schemes phải có thứ tự và chính sách lỗi rõ ràng; (8) thư viện chuẩn xử lý validation/claims/key rotation theo cấu hình; (9) có dấu hiệu scheme nhưng payload hỏng; (10) body là stream reactive được consume và có nguy cơ memory leak nếu cache tùy tiện.

## 15. Ghi nhớ

**`ServerAuthenticationConverter` chỉ biến dữ liệu của HTTP request thành một yêu cầu xác thực; nó không chứng minh danh tính.** Một pipeline Spring Security Reactive có ranh giới rõ ràng:

~~~text
ServerWebExchange
     -> ServerAuthenticationConverter
     -> unauthenticated Authentication
     -> ReactiveAuthenticationManager
     -> verified Authentication
     -> Reactor SecurityContext
     -> Authorization
     -> WebFlux handler
~~~

Hãy dùng `Mono.empty()` khi scheme không xuất hiện; `AuthenticationException` khi credential đã nhận diện nhưng sai; để manager xác minh và cấp authorities; để `AuthenticationWebFilter` quản lý subscription/success/failure; và kiểm thử cả 200, 401, 403. Đây là nền tảng để mở rộng sang Basic, JWT Bearer, form login hoặc tích hợp cơ chế khác một cách an toàn trong WebFlux.

### Tài liệu chính thức

- Spring Security — `ServerAuthenticationConverter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security — `AuthenticationWebFilter` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — `ServerHttpSecurity` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `ServerWebExchangeMatchers` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html