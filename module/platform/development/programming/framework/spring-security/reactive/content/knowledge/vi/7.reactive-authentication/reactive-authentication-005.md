# AuthenticationWebFilter và lựa chọn yêu cầu cần xác thực

## 1. Mục tiêu học tập và vấn đề cần giải quyết

Trong Spring Security reactive (Spring WebFlux), **không phải mọi HTTP request đều cần thực hiện một lần xác thực mới**. Request có thể không thuộc phạm vi của cơ chế xác thực đang xét, không mang credentials, mang credentials sai, hoặc đã xác thực được và cần tiếp tục tới bước phân quyền.

`AuthenticationWebFilter` là một `WebFilter` của Spring Security chịu trách nhiệm **thử xác thực một request cụ thể** khi request đó đáp ứng điều kiện kích hoạt. Nó phối hợp với `ServerWebExchangeMatcher`, `ServerAuthenticationConverter` và `ReactiveAuthenticationManager`, sau đó chuyển sang nhánh thành công hoặc thất bại.

Điểm quan trọng nhất: **việc một request có được thử xác thực hay không khác với việc nó có được phép truy cập tài nguyên hay không**. Các quyết định đó nằm ở những tầng khác nhau.

Sau bài này, bạn cần:
- Diễn giải được thứ tự `requiresAuthenticationMatcher` → `ServerAuthenticationConverter` → `ReactiveAuthenticationManager` → success/failure handler.
- Phân biệt `Mono.empty()` nghĩa là *không thử xác thực* ở converter với `Mono.error(AuthenticationException)` nghĩa là *thử xác thực nhưng thất bại*.
- Phân biệt matcher của `SecurityWebFilterChain`, matcher của `AuthenticationWebFilter` và luật `authorizeExchange`.
- Biết cách cấu hình filter cho một tập URL cụ thể, để request không có credentials đi tiếp, đồng thời từ chối credentials sai.
- Hiểu SecurityContext, Reactor Context, session/cookie và trường hợp stateless.
- Xây dựng và kiểm thử một ví dụ Java 17+ chạy được với Spring Boot WebFlux.

## 2. Vị trí của `AuthenticationWebFilter` trong Spring Security WebFlux

Sơ đồ cho một request đi vào ứng dụng:

~~~text
HTTP request
    │
    ▼
WebFlux / Spring Security WebFilterChainProxy
    │
    │ Chọn SecurityWebFilterChain khớp (nếu có nhiều chain)
    ▼
SecurityWebFilterChain đã chọn
    │
    ├─ các security filter khác: context, CSRF, ...
    │
    ▼
AuthenticationWebFilter
    │
    ├─ requiresAuthenticationMatcher khớp?
    │   ├─ Không → bỏ qua xác thực ở filter này, tiếp tục chain
    │   └─ Có
    │       ▼
    │   ServerAuthenticationConverter.convert(exchange)
    │       ├─ Mono.empty() → không có yêu cầu xác thực, tiếp tục chain
    │       └─ phát Authentication chưa xác thực
    │           ▼
    │       ReactiveAuthenticationManager.authenticate(authentication)
    │           ├─ thành công → SecurityContext + success handler
    │           ├─ lỗi AuthenticationException → failure handler
    │           └─ không quyết định / rỗng → phải hiểu rõ hợp đồng manager
    ▼
AuthorizationWebFilter / authorizeExchange
    │
    ├─ permitAll / authenticated / hasRole / hasAuthority / denyAll
    ▼
Handler / RouterFunction / Controller (nếu được phép)
~~~

`AuthenticationWebFilter` không tự xác thực mật khẩu, khóa API hay JWT bằng phép màu. Filter **điều phối**, còn converter đọc dữ liệu request và manager xác minh dữ liệu. Authorization về sau mới quyết định quyền truy cập.

Một số cơ chế có sẵn của Spring Security WebFlux (HTTP Basic, form login, OAuth2 Resource Server) đã đăng ký thành phần xác thực phù hợp thông qua cấu hình `ServerHttpSecurity`. **Không cần tự tạo `AuthenticationWebFilter` cho mọi ứng dụng.** Custom filter thường phù hợp khi triển khai một phương thức credentials riêng có hợp đồng rõ ràng.

## 3. Bốn quyết định độc lập không được nhầm lẫn

| Cấp quyết định | API thường dùng | Câu hỏi được trả lời | Không có nghĩa là |
| --- | --- | --- | --- |
| Chọn chain | `ServerHttpSecurity.securityMatcher(...)` | SecurityWebFilterChain nào áp dụng với request? | Request đã được phép truy cập |
| Chọn yêu cầu cần thử xác thực | `AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)` | Riêng filter xác thực này có xét request không? | Credentials hợp lệ |
| Phát hiện credentials | `ServerAuthenticationConverter.convert(...)` | Có dữ liệu đăng nhập để gửi manager kiểm tra không? | Người dùng đã được xác thực |
| Phân quyền | `authorizeExchange(...).pathMatchers(...).authenticated()/permitAll()/hasRole(...)` | Request được làm gì với danh tính hiện có? | Thay thế việc xác minh credentials |

Ví dụ:
- Chain chung khớp **mọi** URL.
- `AuthenticationWebFilter` riêng cho khóa API chỉ xét `/api/**`.
- Converter chỉ tạo authentication nếu có header `X-API-Key`.
- `/api/public` có thể `permitAll`, còn `/api/me` yêu cầu `authenticated()` và `/api/admin` yêu cầu `ROLE_ADMIN`.

Dù filter **được phép xét** `/api/public`, request không có khóa API vẫn có thể qua `permitAll`. Nhưng request **chủ động đưa khóa API sai** có thể bị filter từ chối trước khi tới authorization. Từ “public” chỉ nói về quyền truy cập; không cam kết rằng mọi thông tin xác thực sai gửi tới URL ấy sẽ bị bỏ qua.

## 4. `setRequiresAuthenticationMatcher`: lọc request trước khi đọc credentials

Khai báo với `AuthenticationWebFilter`:

~~~java
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);

filter.setRequiresAuthenticationMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

`setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)` định nghĩa **điều kiện phải thỏa để filter bắt đầu thử chuyển request thành Authentication**.

Với matcher trên:
- GET `/api/me`: khớp; converter được xem xét.
- GET `/api/admin`: khớp; converter được xem xét.
- GET `/api/public`: cũng khớp; có cần đăng nhập hay không là luật authorization riêng.
- GET `/public`: không khớp; custom filter đi tiếp mà không cố đọc credentials.

Khi bạn **không cấu hình matcher**, mặc định của `AuthenticationWebFilter` là khớp mọi request. Điều này **không** có nghĩa mỗi request đều chạy manager, vì converter vẫn có quyền trả `Mono.empty()` khi không thấy credentials.

`PathPatternParserServerWebExchangeMatcher` là matcher của WebFlux, nhận mẫu đường dẫn. Có thể thiết lập matcher theo phương thức HTTP hoặc kết hợp nhiều điều kiện, nhưng mọi matcher cần có mục tiêu rõ ràng: URL, HTTP method, loại request, v.v. Không chỉ khớp dựa vào một header thiếu kiểm soát nếu sự hiện diện của header đó có thể làm bỏ qua bước bảo vệ mong muốn.

### 4.1. `securityMatcher` của chain khác gì `requiresAuthenticationMatcher`?

Trong ứng dụng nhiều chain:

~~~java
@Bean
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .build();
}
~~~

`securityMatcher` quyết định **cả chain** có được chọn hay không. Một filter nằm trong chain không được chọn sẽ không được gọi, bất kể matcher riêng của filter là gì. Sau khi chọn chain, `requiresAuthenticationMatcher` chỉ quyết định liệu **một AuthenticationWebFilter trong chain đó** có thử chuyển credentials hay không.

Có thể chỉ dùng một chain toàn cục và giới hạn custom filter bằng `requiresAuthenticationMatcher`, như ví dụ đầy đủ ở dưới. Như thế `/public` vẫn nằm trong chuỗi bảo mật nhưng không kích hoạt xác thực bằng API key.

## 5. `ServerAuthenticationConverter`: có hay không có thông tin đăng nhập?

`org.springframework.security.web.server.authentication.ServerAuthenticationConverter` là chiến lược:

~~~java
Mono<Authentication> convert(ServerWebExchange exchange);
~~~

Nó đọc `ServerWebExchange` (request, headers, cookies, parameters...) rồi tạo một **Authentication yêu cầu xác thực** hoặc phát rỗng.

Ví dụ converter chỉ chấp nhận khóa API trong header:

~~~java
ServerAuthenticationConverter converter = exchange ->
    Mono.justOrEmpty(
            exchange.getRequest().getHeaders().getFirst("X-API-Key"))
        .map(key -> (Authentication)
            UsernamePasswordAuthenticationToken.unauthenticated(
                "api-key", key));
~~~

Trong đoạn trên, `"api-key"` chỉ là nhãn demo. Giá trị raw từ header được giữ làm `credentials` để **manager kiểm tra**. Token được tạo bằng `unauthenticated(...)` vì chưa xác minh gì cả; không bao giờ dùng factory `authenticated(...)` dựa trực tiếp vào dữ liệu do client gửi.

Converter có ba trường hợp khác nhau:

1. **Không có header** → `Mono.empty()`. Filter hiểu là **không có yêu cầu xác thực** để thử và tiếp tục chain. Authorization sau đó có thể cho phép `/api/public` hoặc từ chối `/api/me`.
2. **Có header** → phát một `Authentication` chưa xác thực. Manager phải kiểm tra khóa. Ngay cả chuỗi rỗng hoặc sai vẫn có thể được chuyển cho manager để phát lỗi tường minh.
3. **Dữ liệu bị lỗi cú pháp** → tùy giao thức, converter có thể phát một `AuthenticationException` (ví dụ `BadCredentialsException`) để báo lần thử xác thực không hợp lệ; không dùng `Mono.empty()` như cách che giấu lỗi đăng nhập cần từ chối.

Phân biệt `Mono.empty()` và `Mono.error(...)` là cốt lõi của xử lý authentication reactive:

| Tín hiệu từ converter | Filter sẽ hiểu | Ví dụ |
| --- | --- | --- |
| `Mono.empty()` | Không thử xác thực bằng cơ chế này | Không có `X-API-Key` |
| `Mono.just(unauthenticatedToken)` | Có credentials, gửi manager | Có header `X-API-Key` |
| `Mono.error(AuthenticationException)` | Có lỗi xác thực cần xử lý | Token/header không đúng định dạng theo hợp đồng converter |

**Lưu ý:** mặc định của `AuthenticationWebFilter`, khi bạn không thay converter, là `ServerHttpBasicAuthenticationConverter`. Vì thế với cơ chế custom API key, cần cấu hình `setServerAuthenticationConverter(...)`, nếu không filter sẽ đọc dữ liệu theo HTTP Basic thay vì header khóa API.

## 6. `ReactiveAuthenticationManager`: nơi quyết định credentials có hợp lệ không

`ReactiveAuthenticationManager` nhận `Authentication` từ converter và trả `Mono<Authentication>`. Theo hợp đồng framework:
- Phát `Authentication` đã xác thực: thành công.
- Phát lỗi `AuthenticationException`: thông tin đăng nhập được xử lý nhưng không hợp lệ.
- Phát rỗng: manager **không thể quyết định** với loại yêu cầu đó (thường vì không hỗ trợ dạng token), không đồng nghĩa thành công.

Logic minh họa:

~~~java
ReactiveAuthenticationManager manager = incoming -> {
    if (!(incoming instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty(); // Manager không xử lý kiểu này.
    }

    if (!"expected-key".equals(incoming.getCredentials())) {
        return Mono.error(new BadCredentialsException("Invalid API key"));
    }

    Authentication trusted = UsernamePasswordAuthenticationToken.authenticated(
        "reader",
        null,
        List.of(new SimpleGrantedAuthority("ROLE_READER"))
    );
    return Mono.just(trusted);
};
~~~

Đây là **đoạn minh họa**, chưa phải chương trình Java độc lập. Chỉ sau khi manager xác minh khóa mới tạo token bằng `authenticated(...)` và gán authorities. Credentials của token kết quả có thể là `null` để không lưu lại bí mật.

Manager không nên:
- Gọi `block()` trong pipeline để tra cứu database khi có reactive repository/client.
- Gán `ROLE_ADMIN` từ một trường role do client gửi chưa kiểm chứng.
- Biến khóa sai thành `Mono.empty()` chỉ vì muốn tránh trả lỗi; hãy phát `AuthenticationException` theo hợp đồng.
- Tự log raw password/API key/JWT. Nội dung lỗi bên ngoài nên chung chung để hạn chế tiết lộ thông tin xác thực.

Với I/O async thật, manager có thể trả `Mono` từ reactive repository, kiểm tra kết quả bằng `flatMap` hoặc các toán tử phù hợp rồi phát authentication đã xác thực. Không coi `Mono.defer` bao quanh code blocking là tự động biến nó thành non-blocking.

## 7. Thành công, thất bại và vòng đời `SecurityContext`

`AuthenticationWebFilter` có các hook:

~~~java
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
filter.setSecurityContextRepository(securityContextRepository);
~~~

**Khi xác thực thành công**, filter nhận `Authentication` đã xác thực, xây `SecurityContext` thích hợp, lưu qua `ServerSecurityContextRepository` đã cấu hình và gắn security context vào Reactor Context của nhánh tiếp theo. Success handler quyết định xử lý tiếp: ví dụ tiếp tục chuỗi filter cho API, hoặc chuyển hướng sau form login.

- Success handler mặc định là `WebFilterChainServerAuthenticationSuccessHandler`: tiếp tục chuỗi xử lý.
- Context repository mặc định của `AuthenticationWebFilter` là `NoOpServerSecurityContextRepository`: không chủ động lưu security context giữa các request.
- Nếu dùng session login, cơ chế cấu hình/repository tương ứng có thể lưu và tải SecurityContext qua session cho các request sau. Việc chọn repository phải nhất quán với mô hình xác thực.

**Khi xác thực thất bại**, ví dụ manager phát `BadCredentialsException`, failure handler được gọi. Filter mặc định có hành vi mời xác thực HTTP Basic; với API custom, nên đặt failure handler trả status phù hợp và không để lộ credential. Lỗi kỹ thuật như timeout của kho dữ liệu không nên mặc định bị “bỏ qua để cho đăng nhập”.

**Khi converter trả rỗng**, filter **không dựng một Authentication thành công**: request đi tiếp; authorization vẫn chịu trách nhiệm chặn vùng yêu cầu đăng nhập.

### 7.1. `ReactiveSecurityContextHolder` và các toán tử Reactor

Trong Spring WebFlux, ngữ cảnh bảo mật gắn với chuỗi reactive qua Reactor Context; có thể truy cập:

~~~java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

`ReactiveSecurityContextHolder.getContext()` trả publisher, không trả trực tiếp `SecurityContext` đồng bộ. Không đọc `SecurityContextHolder` theo giả định ThreadLocal của Servlet trong handler WebFlux, và không `block()`/`subscribe()` thủ công trong handler để lấy username.

### 7.2. Không nhầm xác thực và phân quyền

Ngay cả khi manager xác thực thành công, request có thể bị từ chối 403 do thiếu quyền ở `authorizeExchange`. Ví dụ API key hợp lệ của `reader` chỉ có `ROLE_READER`; `/api/admin` cần `ROLE_ADMIN`. Ngược lại, một endpoint `permitAll` có thể trả 200 mà không hề tạo `Authentication` cho client.

Trong custom filter, *authentication thất bại* thường trả 401 theo policy API, còn *authorization từ chối người đã đăng nhập* thường trả 403. Kết quả HTTP thực tế còn phụ thuộc authentication entry point, failure handler và access-denied handler đã cấu hình.

## 8. Ví dụ chạy được: API key chỉ được xử lý ở `/api/**`

Ví dụ sử dụng **Spring Boot 3.3.13, Java 17+ và Gradle 8.x**. Đây là cơ chế **API key mô phỏng dành cho học tập**; dữ liệu khóa hard-code trong code không phù hợp production. Trong hệ thống thật, cần kho bí mật, quy trình rotate/revoke, TLS, kiểm soát log và cách kiểm tra khóa an toàn. Với JWT/OAuth2, ưu tiên Spring Security OAuth2 Resource Server thay vì tự viết filter.

Điểm cần quan sát:
- `/public` nằm ngoài `/api/**`: custom authentication filter bỏ qua.
- `/api/public` nằm trong phạm vi filter nhưng không yêu cầu đăng nhập theo authorization; không có header vẫn được 200.
- `/api/me` yêu cầu authentication: không có header → 401; khóa đúng → 200.
- `/api/admin` yêu cầu role ADMIN: khóa reader → 403, khóa admin → 200.
- Một header API key **sai** trên `/api/public` vẫn có thể tạo lần thử xác thực thất bại → 401, dù rule của endpoint là `permitAll`.

### 8.1. Khởi tạo dự án

Cấu trúc:

~~~text
reactive-auth-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveAuthFilterApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── AuthenticationFilterTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-auth-filter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý phiên bản Spring Security và Reactor tương thích qua dependency management; không gắn phiên bản của các thư viện con một cách tùy ý. Trong ứng dụng khác, dùng phiên bản Boot đang được hỗ trợ và đã kiểm thử bởi dự án.

### 8.2. Lớp khởi động

`src/main/java/demo/ReactiveAuthFilterApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthFilterApplication.class, args);
    }
}
~~~

### 8.3. Cấu hình `AuthenticationWebFilter` có phạm vi rõ ràng

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
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    ReactiveAuthenticationManager apiKeyManager() {
        return incoming -> {
            if (!(incoming instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty(); // Không nhận diện loại token khác.
            }

            if (!(incoming.getCredentials() instanceof String key)) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            if ("reader-demo-key".equals(key)) {
                return Mono.just(trusted("reader", "ROLE_READER"));
            }

            if ("admin-demo-key".equals(key)) {
                return Mono.just(trusted("admin", "ROLE_ADMIN"));
            }

            return Mono.error(
                new BadCredentialsException("Invalid API key"));
        };
    }

    private static Authentication trusted(String name, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                   ReactiveAuthenticationManager apiKeyManager) {

        AuthenticationWebFilter apiKeyFilter =
            new AuthenticationWebFilter(apiKeyManager);

        // Chỉ các request /api/** kích hoạt converter của filter.
        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        );

        // Không có header => Mono.empty() => không thử xác thực.
        // Có header => Authentication CHƯA xác thực để manager kiểm tra.
        ServerAuthenticationConverter converter = exchange ->
            Mono.justOrEmpty(
                    exchange.getRequest().getHeaders()
                        .getFirst("X-API-Key"))
                .map(key -> (Authentication)
                    UsernamePasswordAuthenticationToken.unauthenticated(
                        "api-key", key));

        apiKeyFilter.setServerAuthenticationConverter(converter);

        // Mỗi request cung cấp khóa riêng; không lưu SecurityContext
        // qua session hoặc giữa các request ở custom filter.
        apiKeyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        // Lỗi xác thực: trả 401, không tiết lộ khóa API.
        apiKeyFilter.setAuthenticationFailureHandler((web, exception) -> {
            var response = web.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        // Dùng success handler mặc định: tiếp tục WebFilterChain.
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            // Không dùng Basic / form login trong ví dụ khóa API.
            .httpBasic(spec -> spec.disable())
            .formLogin(spec -> spec.disable())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint((exchange, cause) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    return response.setComplete();
                })
            )
            .addFilterAt(apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }
}
~~~

**Các điểm cần hiểu trong code:**

1. `@EnableWebFluxSecurity` và `SecurityWebFilterChain` thiết lập hạ tầng/luật web security. Spring Boot với security starter cũng có auto-configuration tương ứng; annotation được đặt ở đây để thể hiện cấu hình rõ ràng.
2. Chúng ta chỉ tạo **một chain mặc định khớp mọi request**. `setRequiresAuthenticationMatcher("/api/**")` giới hạn **riêng filter xác thực khóa API**, không giới hạn phạm vi bảo vệ của chain.
3. `converter` trả `Mono.empty()` khi không có `X-API-Key`. Đây là tình huống **không có nỗ lực xác thực**, khác với header có giá trị sai. Khóa sai làm `apiKeyManager` phát `BadCredentialsException`.
4. `UsernamePasswordAuthenticationToken.unauthenticated` đóng vai trò *vỏ mang credentials tạm thời* vì ví dụ muốn tránh tự viết một loại token mới. Trong hệ thống phức tạp, có thể dùng custom `Authentication` riêng để manager dễ nhận biết rõ loại credentials.
5. `apiKeyManager` kiểm tra key rồi tạo Authentication đã xác thực với `credentials = null` và quyền đã xác định bởi server. Không dùng roles do client tự gửi. Các so sánh khóa chuỗi cứng chỉ để học, không áp dụng nguyên xi cho production.
6. `NoOpServerSecurityContextRepository` giữ cơ chế API key stateless: client phải cung cấp khóa ở mỗi request cần xác thực. Context vẫn có trong **subscription hiện tại** sau thành công để controller/authorization đọc được.
7. Failure handler xử lý lỗi xác thực của filter và trả 401. `exceptionHandling.authenticationEntryPoint` xử lý yêu cầu đến tài nguyên cần authentication nhưng chưa có authentication hợp lệ, cũng trả 401.
8. `SecurityWebFiltersOrder.AUTHENTICATION` là vị trí đặt custom filter trong security chain. Nó bảo đảm bước xác thực diễn ra trước khi authorization đánh giá rule đã khai báo.
9. `/api/admin` cần authority `ROLE_ADMIN` vì `hasRole("ADMIN")` áp dụng tiền tố theo quy ước. Khóa reader chỉ có `ROLE_READER`.
10. Không disable CSRF: ví dụ dùng **chỉ HTTP GET**. Khi triển khai POST/PUT/DELETE cần hiểu cơ chế CSRF và nguồn credentials trước khi cấu hình chính sách riêng.

### 8.4. Các endpoint để quan sát hành vi

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record Identity(String name, List<String> authorities) {}

    @GetMapping("/public")
    Mono<String> rootPublic() {
        return Mono.just("root-public");
    }

    @GetMapping("/api/public")
    Mono<String> apiPublic() {
        return Mono.just("api-public");
    }

    @GetMapping("/api/me")
    Mono<Identity> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(this::toIdentity);
    }

    @GetMapping("/api/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-area");
    }

    private Identity toIdentity(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList();
        return new Identity(auth.getName(), authorities);
    }
}
~~~

`ReactiveSecurityContextHolder` đọc authentication đã xác minh trong Reactor Context. Endpoint `/api/me` chỉ hiển thị tên và authorities; không hiển thị `getCredentials()` hoặc raw `X-API-Key`. Nếu chưa đăng nhập, rule `authenticated()` chặn request ở security chain trước khi handler này trả nội dung.

Dự án không có controller cho một số route khác, nhưng `anyExchange().denyAll()` bảo đảm policy không tự cho phép các URL không được nêu tên. Một ứng dụng thật cần cấu hình thêm health checks, static resources hoặc các endpoint cần thiết một cách tường minh.

## 9. Kết quả các request: matcher, converter, manager và rule

| HTTP request | `requiresAuthenticationMatcher` | Converter | Manager | Authorization | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| GET `/public`, không key | Không khớp | Không chạy | Không chạy | `permitAll` | 200 |
| GET `/api/public`, không key | Khớp | `Mono.empty()` | Không chạy | `permitAll` | 200 |
| GET `/api/me`, không key | Khớp | `Mono.empty()` | Không chạy | `authenticated()` | 401 |
| GET `/api/me`, `reader-demo-key` | Khớp | Tạo token chưa xác thực | Trả `ROLE_READER` | `authenticated()` | 200 |
| GET `/api/me`, key sai | Khớp | Tạo token chưa xác thực | `BadCredentialsException` | Không tới handler | 401 |
| GET `/api/admin`, `reader-demo-key` | Khớp | Tạo token chưa xác thực | Trả `ROLE_READER` | `hasRole("ADMIN")` từ chối | 403 |
| GET `/api/admin`, `admin-demo-key` | Khớp | Tạo token chưa xác thực | Trả `ROLE_ADMIN` | `hasRole("ADMIN")` cho phép | 200 |
| GET `/api/public`, key sai | Khớp | Tạo token chưa xác thực | `BadCredentialsException` | Request đã thất bại trước phân quyền | 401 |

Hàng cuối cực kỳ quan trọng: **`permitAll` không có nghĩa “bỏ qua AuthenticationWebFilter”**. Vì filter chạy trước authorization, một credential có mặt nhưng không hợp lệ vẫn có thể kích hoạt failure handler. Nếu yêu cầu sản phẩm là mọi request ở `/api/public` phải bỏ qua filter, cần **loại URL đó khỏi `requiresAuthenticationMatcher` một cách tường minh**, thay vì hy vọng rule `permitAll` thay thế điều kiện match của filter.

## 10. Chạy bằng curl

Mở server từ thư mục `reactive-auth-filter-demo`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Unix/macOS hoặc `gradlew.bat bootRun` trên Windows. Ứng dụng mặc định lắng nghe `http://localhost:8080` nếu không thay cổng.

Trong bash/Git Bash:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -H 'X-API-Key: reader-demo-key' http://localhost:8080/api/me
curl -s -H 'X-API-Key: wrong' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -H 'X-API-Key: reader-demo-key' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -H 'X-API-Key: admin-demo-key' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -H 'X-API-Key: wrong' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
~~~

Các mã HTTP của lệnh 1, 2, 3, 5, 6, 7, 8 theo thứ tự:

~~~text
200
200
401
401
403
200
401
~~~

Lệnh 4 trả JSON đại diện danh tính đã xác thực, dạng:

~~~json
{
  "name": "reader",
  "authorities": ["ROLE_READER"]
}
~~~

Dấu cách/thứ tự thuộc tính JSON có thể khác, nhưng tên và authority phải khớp. Không có API key nào được trả lại trong body. Với Windows PowerShell, dùng `curl.exe`; tùy máy có thể cần thay `/dev/null` bằng `NUL`. Các API keys mẫu không được dùng làm secrets thật hoặc gửi trên HTTP ngoài môi trường local.

## 11. Kiểm thử thực tế bằng `WebTestClient`

Tạo `src/test/java/demo/AuthenticationFilterTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationFilterTests {

    @Autowired
    WebTestClient client;

    @Test
    void outsideApiIsNotAnAuthenticationAttemptForCustomFilter() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("root-public");
    }

    @Test
    void anonymousPublicApiIsAllowedButProtectedApiIsNot() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-public");

        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyProducesTrustedPrincipalInReactorContext() {
        client.get().uri("/api/me")
            .header("X-API-Key", "reader-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("reader")
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void incorrectKeyReturnsAuthenticationFailure() {
        client.get().uri("/api/me")
            .header("X-API-Key", "wrong")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authorizationHappensAfterSuccessfulAuthentication() {
        client.get().uri("/api/admin")
            .header("X-API-Key", "reader-demo-key")
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin")
            .header("X-API-Key", "admin-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-area");
    }

    @Test
    void publicAuthorizationDoesNotIgnoreBadCredentials() {
        client.get().uri("/api/public")
            .header("X-API-Key", "wrong")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc dùng wrapper nếu dự án có. Sáu phương thức test cần PASS để xác nhận hành vi của cấu hình mẫu. Gradle trả exit code 0 khi thành công; log cụ thể phụ thuộc môi trường, vì vậy không khẳng định một chuỗi log cố định.

**Vì sao bài test cuối quan trọng?** Nếu lập trình viên nhầm `permitAll` là bỏ qua filter, test có thể bắt lỗi đó. Đây là kiểm thử đặc biệt hữu ích khi bổ sung endpoint public vào API vốn có bộ lọc xác thực custom.

## 12. Muốn bỏ qua xác thực trên một endpoint public thì làm thế nào?

Nếu yêu cầu nghiệp vụ là `/api/public` **không bao giờ thử xác thực API key**, kể cả khi client vô tình gửi key sai, cần thay matcher của filter thành một `ServerWebExchangeMatcher` chỉ khớp các path thật sự cần thử xác thực.

Ví dụ chọn hai nhóm protected path, minh họa thay cho matcher `/api/**` trong cấu hình đầy đủ:

~~~java
import org.springframework.security.web.server.util.matcher.OrServerWebExchangeMatcher;

// Chỉ /api/me và /api/admin kích hoạt filter API key.
// Các endpoint khác, kể cả /api/public, bỏ qua filter này.
apiKeyFilter.setRequiresAuthenticationMatcher(
    new OrServerWebExchangeMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/me"),
        new PathPatternParserServerWebExchangeMatcher("/api/admin")
    )
);
~~~

Đây là **đoạn sửa minh họa, không độc lập**: cần dùng trong `SecurityConfig` tại mục 8 và thêm import. Với API có nhiều route bảo vệ, cách liệt kê tất cả path có thể khó bảo trì. Nên chọn cách phù hợp với mô hình sản phẩm; nếu filter phải hỗ trợ các endpoint mới, đừng để việc quên cập nhật matcher làm endpoint đó chỉ còn authorization nhưng không có phương thức xác thực.

Đừng sửa bằng cách đặt `.pathMatchers("/api/public").permitAll()` và kỳ vọng filter tự bỏ qua: đó vẫn là **điều kiện phân quyền**, không thay matcher của filter.

## 13. Matcher theo HTTP method và điều kiện khác

Không phải mọi endpoint đều cần cùng cơ chế. Một số ứng dụng muốn kiểm tra credentials chỉ cho những method nhất định. `PathPatternParserServerWebExchangeMatcher` có overload nhận HTTP method và path. Ví dụ minh họa:

~~~java
new PathPatternParserServerWebExchangeMatcher(
    "/api/data/**",
    org.springframework.http.HttpMethod.POST
);
~~~

Khi dùng overload, kiểm tra chữ ký phù hợp với phiên bản Spring Security đã chọn; API của matcher có overload nhận path/method và có thể khác theo phiên bản. Với bất kỳ rule chỉ theo method nào, cần kiểm thử GET, POST, PUT, DELETE và OPTIONS để tránh vô tình để một method nhạy cảm không được xác thực. Authorization vẫn phải được áp dụng độc lập với phạm vi filter.

Matcher cũng có thể được kết hợp bằng `AndServerWebExchangeMatcher` / `OrServerWebExchangeMatcher` hoặc implementation riêng. Nếu API cho phép một filter bắt request dựa vào header, cần nhớ **header có thể do client kiểm soát**. Không thể xem “có header xác thực” là tiêu chí duy nhất để quyết định request **có phải bảo vệ hay không**: request thiếu header phải bị chặn bởi authorization nếu endpoint yêu cầu đăng nhập.

**Cảnh báo kỹ thuật:** Ví dụ trên thể hiện ý định match theo HTTP method; trước khi sao chép, hãy đối chiếu constructor của `PathPatternParserServerWebExchangeMatcher` trong phiên bản đang dùng và kiểm tra compile. Nếu API chọn method đầu tiên, dùng chữ ký đó; mục tiêu học là hiểu rằng cần đối chiếu path + method đúng phiên bản, không phụ thuộc vị trí tham số theo suy đoán.

## 14. Những hiểu nhầm và lỗi phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nhầm `securityMatcher` của chain với `requiresAuthenticationMatcher` của filter | Cấu hình phạm vi bảo vệ/đăng nhập không như mong muốn | Phân biệt chain được chọn và filter trong chain |
| Nghĩ `permitAll` khiến `AuthenticationWebFilter` không chạy | Gửi key sai vào endpoint public vẫn bị từ chối | Thiết kế matcher loại trừ public khi cần, kiểm thử riêng |
| Converter trả `Mono.empty()` khi key có mặt nhưng sai | Không có lỗi xác thực rõ ràng; có thể tạo kết quả khó dự đoán | Trả token chưa xác thực cho manager và phát `BadCredentialsException` |
| Converter tự tạo token `authenticated(...)` | Bỏ qua xác minh credentials, có thể leo thang quyền | Converter chỉ tạo token chưa xác thực |
| Manager cấp `ROLE_ADMIN` từ payload client | Lỗ hổng phân quyền | Chỉ cấp authority từ nguồn đã kiểm tra |
| Dùng `block()` để đọc database trong manager | Chặn event loop WebFlux | Dùng repository/client reactive, kết hợp `flatMap` |
| Dùng `HttpSecurity`, `OncePerRequestFilter` hoặc `RequestMatcher` của Servlet | Không khớp kiến trúc WebFlux | Dùng `ServerHttpSecurity`, `WebFilter` và `ServerWebExchangeMatcher` |
| Tự `subscribe()` bên trong filter | Request lifecycle/context và lỗi không còn được quản lý đúng | Trả lại `Mono<Void>` để framework subscribe |
| Không hiểu `NoOpServerSecurityContextRepository` | Tưởng authentication được lưu để tái sử dụng tự động | Cung cấp credentials mỗi request hoặc cấu hình lưu session có chủ đích |
| Không cấu hình failure/entry point cho API | 401/redirect/WWW-Authenticate không như mong muốn | Cấu hình lỗi HTTP phù hợp và test |
| Đặt filter sai `SecurityWebFiltersOrder` | Authorization có thể chạy trước khi xác thực custom | Chọn `AUTHENTICATION` khi đó là bước authentication |
| Tưởng converter mặc định đọc API key | Mặc định converter đọc HTTP Basic | Đặt `setServerAuthenticationConverter` riêng |
| Chỉ test trường hợp key đúng | Bỏ sót anonymous, key sai, public route, role thiếu | Dùng ma trận request và WebTestClient |
| Ghi header raw hoặc token vào logs | Rò rỉ thông tin bí mật | Chỉ log mã lỗi/trace ID và thông tin đã lọc |
| Dùng key chuỗi hard-code làm cơ chế production | Secret khó rotate, nguy cơ lộ trong source | Vault/secret manager, TLS, hash, rotation, revoke, rate limit |

### 14.1. “Không có credentials” khác “credentials sai”

Bài toán thường gặp ở API public: client không đưa `X-API-Key` thì converter trả rỗng, authorization `permitAll` nên request thành công. Client đưa giá trị `wrong` thì converter phát token, manager phát lỗi, failure handler trả 401. Đây **không phải** mâu thuẫn: một request không yêu cầu danh tính vẫn có thể bị từ chối nếu nó **chủ động thử xác thực bằng credentials sai**.

Đối với API protected, cả “không có header” và “header sai” có thể cùng biểu hiện 401 từ hai đường đi khác nhau. Bổ sung trace/metric đã lọc giúp phân biệt:
- thiếu credentials: authorization/entry point;
- credentials sai: authentication failure handler.
Không đưa giá trị khóa vào log hoặc metric label.

### 14.2. HTTP 401, 403 và lỗi kỹ thuật

- `401 Unauthorized`: không có authentication phù hợp hoặc không xác thực được theo cơ chế hiện tại; trả theo entry point/failure handler.
- `403 Forbidden`: authentication hợp lệ nhưng thiếu quyền, hoặc một security filter khác như CSRF từ chối request.
- `5xx` có thể phản ánh sự cố hệ thống; không chuyển mọi timeout của kho khóa thành `Mono.empty()` hay đăng nhập thành công.

Response cụ thể phụ thuộc cấu hình error handling, filter order, format/content negotiation, reverse proxy. Kiểm thử API nên xác nhận status và body an toàn theo hợp đồng của ứng dụng.

### 14.3. Với JWT, HTTP Basic và form login thì sao?

Spring Security có các DSL được hỗ trợ:
- `http.httpBasic(...)`: lọc request mang HTTP Basic và dùng cơ chế xác thực phù hợp.
- `http.formLogin(...)`: xử lý request login theo form.
- `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`: cơ chế Resource Server kiểm tra Bearer JWT với các thành phần có sẵn.

Hãy ưu tiên cơ chế sẵn có nếu bài toán thuộc giao thức chuẩn. Custom `AuthenticationWebFilter` phù hợp hơn cho định dạng credentials riêng, và khi đó phải tự làm rõ matcher, converter, manager, success/failure và chính sách SecurityContext. Không nên tự viết JWT parser hoặc cơ chế chữ ký.

## 15. Chẩn đoán theo từng bước khi xác thực không chạy

Nếu một request có `X-API-Key` nhưng controller vẫn nhận anonymous hoặc 401, hãy xét theo thứ tự:

1. **Ứng dụng chạy Spring WebFlux?** Kiểm tra dependency, tránh vô tình dùng Servlet MVC.
2. **Chain nào được chọn?** Nếu nhiều `SecurityWebFilterChain`, kiểm tra `securityMatcher` và `@Order`.
3. **Filter đã được thêm vào chain được chọn chưa?** Kiểm tra `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`.
4. **Matcher của filter có khớp không?** Xét path, method, trailing slash, context path, reverse proxy.
5. **Converter có thấy header?** Đối chiếu tên header, case-insensitive theo HTTP, proxy có chuyển tiếp header không. Đừng log giá trị secret.
6. **Converter có trả `Mono.empty()` không?** Nếu rỗng, manager không có token để xử lý.
7. **Manager trả gì?** Authentication đã xác minh, `AuthenticationException` hay một publisher rỗng vì không hỗ trợ?
8. **Sau thành công, authorization có chấp nhận authorities?** `hasRole("ADMIN")` thường cần `ROLE_ADMIN`.
9. **Failure handler và entry point có trả mã mong muốn không?** Kiểm tra test 401 và 403 riêng biệt.
10. **SecurityContext có ở cùng Reactor pipeline không?** Đừng detach request bằng `subscribe()` hoặc dùng ThreadLocal Servlet trong WebFlux.

Để debug, có thể bật mức log Spring Security thích hợp ở môi trường phát triển nhưng luôn lọc raw credentials, Authorization header và cookie. Đối với ứng dụng cần quan sát sâu, có thể thêm instrumentation cho **quyết định match và loại kết quả** mà không thu thập bí mật.

## 16. Bài tập vận dụng

**Bài 1.** Với cấu hình mục 8, GET `/api/public` không có `X-API-Key` có gọi manager không?  
**Đáp án:** Không. Matcher khớp nhưng converter trả `Mono.empty()`; authorization `permitAll` cho request qua.

**Bài 2.** Nếu gửi `X-API-Key: wrong` tới `/api/public` thì kết quả gì?  
**Đáp án:** Converter tạo authentication chưa xác thực, manager phát `BadCredentialsException`, failure handler trả 401 dù URL được `permitAll`.

**Bài 3.** Nếu gửi key reader tới `/api/admin` thì filter thành công hay thất bại?  
**Đáp án:** **Xác thực thành công** (có danh tính reader), nhưng **phân quyền thất bại** vì thiếu `ROLE_ADMIN`; kỳ vọng 403.

**Bài 4.** Khi dùng chain catch-all và filter matcher `/api/**`, endpoint `/public` có được bảo vệ bởi security chain không?  
**Đáp án:** Có, vì chain khớp mọi request; chỉ custom API-key filter không thử xác thực trên URL đó. Quy tắc `permitAll` xác định nó là public.

**Bài 5.** Khi client không gửi khóa cho `/api/me`, có nên converter tự tạo `ROLE_READER` mặc định không?  
**Đáp án:** Không. Converter trả rỗng; rule `authenticated()` phải từ chối request chưa đăng nhập.

**Bài 6.** Vì sao không dùng `Mono.empty()` cho một khóa sai?  
**Đáp án:** Vì đó là nỗ lực xác thực có credentials không hợp lệ; phải biểu diễn bằng lỗi xác thực. Trả rỗng có thể khiến nhánh xử lý hiểu sai là không có nỗ lực xác thực.

**Bài 7.** Muốn bỏ qua filter custom cho `/api/public`, sửa `authorizeExchange` hay `setRequiresAuthenticationMatcher`?  
**Đáp án:** Sửa matcher **của filter**; `authorizeExchange` chỉ quyết định quyền, không tắt authentication filter.

**Bài 8.** Trong một app dùng JWT chuẩn, nên tự tạo `AuthenticationWebFilter` để parse token không?  
**Đáp án:** Thông thường không. Dùng OAuth2 Resource Server của Spring Security để xử lý Bearer JWT, cấu hình decoder và validators chuẩn.

**Bài 9.** Manager trả `Mono<Authentication>` từ repository nhưng bạn dùng `.block()` trong manager để lấy user, có phù hợp WebFlux không?  
**Đáp án:** Không. Hãy duy trì publisher reactive và dùng `flatMap`/`map` để quyết định authentication.

**Bài 10.** Trường hợp nào khiến filter không được gọi dù matcher của filter là “match all”?  
**Đáp án:** Request được chọn vào một `SecurityWebFilterChain` **khác** không chứa filter đó, hoặc không có chain nào khớp; điều kiện của filter chỉ có ý nghĩa khi nó nằm trong chain đang thực thi.

## 17. Tài liệu chính thức

- Spring Security API `AuthenticationWebFilter` (mô tả thuật toán, matcher, converter, success/failure): https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security WebFlux configuration (nhiều chain, matcher, `ServerHttpSecurity`): https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security reactive authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security API `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security API `ServerAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html

**Ghi nhớ:** `AuthenticationWebFilter` xác định **có thử xác thực request này hay không** nhờ matcher và converter; manager xác minh credentials; success/failure handler quyết định nhánh tiếp theo; `authorizeExchange` quyết định **request đã có danh tính tương ứng có được phép truy cập tài nguyên hay không**. Đặt đúng ranh giới bốn trách nhiệm này là chìa khóa để xây cơ chế xác thực reactive an toàn.
