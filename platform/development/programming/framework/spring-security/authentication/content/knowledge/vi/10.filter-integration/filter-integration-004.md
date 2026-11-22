# AuthenticationFilter và AuthenticationConverter trong Spring Security

> **Phạm vi:** Spring Security – authentication, chủ đề **Tích hợp bộ lọc**. Bài học giải thích `AuthenticationConverter` chuyển một HTTP request thành yêu cầu xác thực chưa đáng tin, `AuthenticationFilter` điều phối `AuthenticationManager` và cập nhật `SecurityContext` như thế nào, cách xử lý thành công/thất bại và đặt đúng filter trong chuỗi bảo mật. Ví dụ đầy đủ dùng **Java 17+**, **Spring Boot 4.1.2**, Spring Security Servlet và một HTTP header API key dành riêng cho môi trường học tập.

## 1. Tại sao không nên vừa đọc header vừa tự xác thực trong một filter?

Một ứng dụng có thể nhận credential qua form login, HTTP Basic, Bearer token hoặc header riêng. Định dạng bằng chứng khác nhau nhưng quá trình xử lý thường giống nhau:

```text
HttpServletRequest
       |
       v
Trích xuất bằng chứng (username/password, API key, token...)
       |
       v
Authentication request CHƯA được tin cậy
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       +-- thất bại -> error handler
       |
       +-- thành công -> principal + authorities đáng tin cậy
                                |
                                v
                        SecurityContext
                                |
                                v
                        Authorization
                                |
                                v
                        Controller / Service
```

Nếu một custom filter đọc `X-Role: ADMIN` rồi tự tạo principal với `ROLE_ADMIN`, người dùng có thể tự nâng quyền bằng cách sửa request. Nếu một filter khác tự tạo `UsernamePasswordAuthenticationToken` đã authenticated trước khi so sánh password, toàn bộ quá trình xác thực có thể bị bỏ qua.

Spring Security tách các vai trò để tránh nhầm lẫn:

| Thành phần | Trách nhiệm cốt lõi | Không được ngầm làm |
| --- | --- | --- |
| `AuthenticationConverter` | Biến HTTP request thành authentication request chưa được xác minh | Tự cấp quyền từ input |
| `AuthenticationFilter` | Chọn request, gọi converter/manager, xử lý result và context | Thay provider kiểm chứng credential |
| `AuthenticationManager` | Điều phối các provider | Tin request mà không xác minh |
| `AuthenticationProvider` | Kiểm chứng đúng loại credential, trả principal/authority đáng tin | Chấp nhận role client tự khai |
| `SecurityContextHolder` | Giữ context hiện hành theo strategy | Là kho dữ liệu quyền lâu dài |
| `AuthorizationFilter` | So sánh caller với policy sau authentication | Coi có header là đã có quyền |

**Nguyên tắc:** Converter **đọc**. Manager/provider **kiểm chứng**. AuthenticationFilter **điều phối**. Authorization **quyết định cho phép hành động**.

## 2. AuthenticationConverter: contract và ba kết quả

Interface `org.springframework.security.web.authentication.AuthenticationConverter` có phương thức:

```java
@Nullable
Authentication convert(HttpServletRequest request);
```

Đây là chữ ký API rút gọn; `HttpServletRequest` thuộc `jakarta.servlet.http`, `Authentication` thuộc Spring Security. Method có thể trả:

| Giá trị | Ý nghĩa | Hành vi điển hình của AuthenticationFilter |
| --- | --- | --- |
| `null` | Không có credential thuộc cơ chế converter nhận diện | Bỏ qua authentication attempt, tiếp tục filter chain |
| `Authentication` chưa xác thực | Có bằng chứng để provider kiểm tra | Gọi `AuthenticationManager.authenticate(...)` |
| Ném `AuthenticationException` | Có credential/scheme bị sai định dạng hoặc bị từ chối ngay ở bước parsing | Gọi failure handler |

### Null KHÔNG phải “cho phép”

Ví dụ `GET /api/data` không có header `X-Demo-Key`:

```text
Converter -> null
AuthenticationFilter -> chain tiếp tục, không authenticate
AuthorizationFilter -> yêu cầu authority "data:read"
Caller chưa được xác thực -> entry point trả 401 trong demo
```

Nếu endpoint vô tình có `permitAll()`, nó vẫn có thể được mở. Đây là lỗi của **authorization rule**, không phải tính năng converter tự mở quyền.

### Nên ném exception lúc nào?

Một giao thức nên quy định rõ: *không có credential* có thể trả null; *có credential nhưng sai định dạng* thường ném `BadCredentialsException` hoặc subclass thích hợp. Với API key header:

- Không có header: `null`.
- Một header không rỗng, độ dài hợp lệ: tạo token chưa authenticated.
- Header rỗng, lặp hoặc quá dài: `AuthenticationException`.
- Header đúng định dạng nhưng **giá trị bí mật sai**: converter vẫn tạo token; **provider** mới bác bỏ.

Không để converter tự query nguồn key rồi xây authenticated token; việc kiểm chứng và cấp quyền thuộc tầng authentication provider.

## 3. Authentication token trước và sau xác thực

`Authentication` là interface có thể đại diện **cả yêu cầu chưa xác thực** lẫn **kết quả đã xác thực**.

Một request token đúng nghĩa thường có:

- `principal`: tên hoặc marker do caller khai, **chưa xác minh**.
- `credentials`: bằng chứng thô đang chờ kiểm tra.
- `authorities`: thường rỗng.
- `isAuthenticated() == false`.

Một kết quả tin cậy sau provider có:

- Principal được tra cứu/được xác nhận từ nguồn server.
- Authorities chỉ do provider/nguồn đã xác minh cấp.
- `isAuthenticated() == true`.
- Credentials được ẩn/xóa khỏi result khi phù hợp.

Trong bài, ta tạo `HeaderKeyAuthentication` riêng để không dùng nhầm `UsernamePasswordAuthenticationToken` của password login. Converter chỉ có thể tạo token `presented(raw)`; provider xác minh rồi tạo kết quả `verified(actor)`.

Tại sao custom type có ích? `AuthenticationProvider.supports(Class<?>)` dùng class type để quyết định provider nào có thể xử lý. Nếu API key bị giả thành token username/password, provider DAO có thể bị chọn nhầm, gây lệch giao thức hoặc bỏ qua một số điều kiện xác thực.

**Không nhất thiết phải tạo custom token cho mọi dự án.** Form login, HTTP Basic, bearer/JWT, SAML hay OAuth2 nên ưu tiên filter/provider tiêu chuẩn của Spring Security.

## 4. AuthenticationFilter hoạt động ra sao?

`org.springframework.security.web.authentication.AuthenticationFilter` là một servlet filter kế thừa `OncePerRequestFilter`, được Spring Security hỗ trợ từ phiên bản 5.2. Hai dạng constructor:

```java
AuthenticationFilter(
        AuthenticationManager manager,
        AuthenticationConverter converter);

AuthenticationFilter(
        AuthenticationManagerResolver<HttpServletRequest> resolver,
        AuthenticationConverter converter);
```

Đây là chữ ký rút gọn, không phải source code độc lập. Dạng thứ nhất dùng một manager. Dạng thứ hai giải quyết bài toán chọn manager dựa trên request (ví dụ nhiều identity realm) **nhưng không tự xác minh issuer hoặc tenant**.

Luồng tổng quát:

```text
AuthenticationFilter
    |
    +-- setRequestMatcher.matches(request) == false
    |       -> chain.doFilter, converter không chạy
    |
    +-- matcher == true
            |
            v
        converter.convert(request)
            |
            +-- null -> chain.doFilter
            |
            +-- AuthenticationException -> failure handler
            |
            +-- unauthenticated Authentication
                        |
                        v
                 manager.authenticate(...)
                        |
                 +------+------+
                 |             |
              success        failure
                 |             |
          SecurityContext   Clear context
          Success handler   Failure handler
                 |
           Handler có thể
           tiếp tục chain,
           ghi response,
           hoặc redirect
```

### RequestMatcher nên hẹp và rõ

`filter.setRequestMatcher(RequestMatcher)` quyết định filter chạy trên URL và method nào. Mặc định một `AuthenticationFilter` được tạo có thể match mọi request; nếu custom converter nhầm lẫn trên endpoint công khai, sẽ phát sinh 401 không mong muốn. Vì vậy trong demo chỉ match chính xác `GET /api/data`.

**Matcher không thay thế authorization.** Dù matcher không khớp, `AuthorizationFilter` vẫn bảo vệ resource theo rule của nó.

### Lựa chọn AuthenticationManagerResolver

Nếu API xử lý nhiều issuer/tenant, có thể cần manager resolver. Resolver chỉ chọn **bộ kiểm chứng thích hợp**; nó không được chọn một manager “dễ hơn” chỉ từ header `X-Tenant-Id` chưa có ràng buộc tin cậy. Việc xác minh tenant/issuer còn phụ thuộc token, routing contract và data source đáng tin.

## 5. Thành công, thất bại và SecurityContextRepository

AuthenticationFilter có các setter quan trọng:

| API | Vai trò |
| --- | --- |
| `setRequestMatcher(...)` | Chỉ ra request nào được filter xử lý |
| `setAuthenticationConverter(...)` | Thay chiến lược chuyển request thành token |
| `setAuthenticationManagerResolver(...)` | Chọn manager theo request |
| `setSuccessHandler(...)` | Xử lý khi xác thực thành công |
| `setFailureHandler(...)` | Xử lý khi xác thực thất bại |
| `setSecurityContextRepository(...)` | Quyết định cách lưu `SecurityContext` sau thành công |

### Success handler có thể dừng hoặc tiếp tục request

`AuthenticationFilter` đặt authentication thành công vào `SecurityContextHolder`, gọi repository để save context, rồi gọi `AuthenticationSuccessHandler`.

`AuthenticationSuccessHandler` có method thông thường nhận request/response/authentication và một method default bổ sung `FilterChain`:

```java
void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);

default void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain,
        Authentication authentication);
```

Đây là API rút gọn, các method có thể khai báo `IOException` và `ServletException`. Handler form login thường redirect. Với một API cần đi **tiếp đến controller trong cùng request**, có thể override dạng bốn tham số và gọi `chain.doFilter(...)`.

Nếu chỉ dùng handler mặc định trả redirect, API key đúng có thể **không tới controller**, dù việc xác thực đã thành công. Vì vậy phải test output thực tế chứ không chỉ `Authentication.isAuthenticated()`.

### Failure handler không phải controller advice

Nếu converter hoặc provider ném `AuthenticationException`, `AuthenticationFilter` gọi `AuthenticationFailureHandler` và clear context. Với demo API, ta trả HTTP 401 generic, không gửi nguyên exception message.

`@RestControllerAdvice` thuộc tầng MVC; nhiều security filter chạy **trước** MVC nên controller advice không nhất thiết bắt được lỗi ở đây. `ExceptionTranslationFilter` thường xử lý exception từ authorization/downstream, còn filter authentication có đường failure handler riêng.

### Mặc định không đồng nghĩa session login

`AuthenticationFilter` thường dùng `RequestAttributeSecurityContextRepository` mặc định, **không tự lưu context vào HttpSession**. Một request có `Authentication` hợp lệ không có nghĩa request kế tiếp vẫn authenticated.

Nếu muốn stateful login, cần repository/session strategy phù hợp, session fixation protection, CSRF/remember-me/logout và lifecycle rõ ràng. Nếu muốn stateless API, giữ request-scoped context hoặc tương đương và gửi credential trên mỗi request.

## 6. Đặt AuthenticationFilter vào đúng SecurityFilterChain

Các phần chính trong Servlet Spring Security (thứ tự tổng quát, không liệt kê mọi filter):

```text
SecurityContextHolderFilter
    |
Header/CORS/CSRF protection (theo cấu hình)
    |
LogoutFilter
    |
Custom AuthenticationFilter
    |
AnonymousAuthenticationFilter
    |
ExceptionTranslationFilter
    |
AuthorizationFilter
    |
Controller / Service
```

Spring Security hướng dẫn custom authentication filter thường đặt **sau `LogoutFilter`**. Một ví dụ:

```java
http.addFilterAfter(headerAuthenticationFilter, LogoutFilter.class);
```

Đây là mảnh cấu hình `HttpSecurity`, không phải lớp Java độc lập. Nếu đặt filter **sau `AuthorizationFilter`**, request có thể bị từ chối trước khi có principal. Nếu đặt quá sớm, `SecurityContextHolderFilter` hoặc những lớp bảo vệ request chưa thiết lập đúng.

### Filter bean có thể vô tình chạy hai lần

Spring Boot có thể tự đăng ký bean kiểu `jakarta.servlet.Filter` làm **servlet filter toàn cục**. Nếu đồng thời thêm bean đó vào Spring Security chain, nó có thể chạy hai lần hoặc chạy ngoài chuỗi security.

Trong demo, `AuthenticationFilter` được tạo **trực tiếp trong phương thức xây dựng SecurityFilterChain**, không đặt `@Bean` riêng. Nếu dự án thật cần tạo bean filter, hãy cân nhắc `FilterRegistrationBean#setEnabled(false)` cho đăng ký servlet toàn cục, rồi đưa filter vào chain mong muốn.

### Nhiều filter chain không chia sẻ matcher một cách tự động

Một hệ thống có thể có chain API và chain browser riêng với `@Order`/`securityMatcher`. `FilterChainProxy` chọn **chain đầu tiên khớp request**. Thêm filter vào API chain không làm browser chain cũng có nó. Phải test thứ tự chain, đường public/private, stateless/stateful và error handler theo từng chain.

## 7. Ví dụ đầy đủ: Spring Boot Java 17+ và API key trong header

Mục tiêu ví dụ:

1. Client gửi `X-Demo-Key` trong `GET /api/data`.
2. Converter kiểm tra hình dạng header, trả token `isAuthenticated=false`.
3. Provider dùng key được server cấu hình để kiểm tra bằng chứng rồi cấp principal `service-client` với authority `data:read`.
4. Filter tạo context và **tiếp tục chain** qua success handler bốn tham số.
5. Authorization rule kiểm tra `hasAuthority("data:read")`.
6. Thiếu key hoặc key sai bị từ chối 401; endpoint public không yêu cầu credential.
7. Không tạo HTTP session; mỗi lần gọi endpoint bảo vệ cần header key.

**Lưu ý về an toàn:** key demo không dành cho production. Ứng dụng thật cần key ngẫu nhiên có entropy đủ cao, storage hash/HMAC-at-rest, TLS, audit, rate limiting, rotation, revocation và chính sách theo client/tenant. So sánh SHA-256 digest trong demo **không dùng để lưu password do người dùng chọn**.

### 7.1. Cấu trúc project

```text
header-auth-demo/
├── pom.xml
└── src/main/java/com/example/headerauth/
    └── HeaderAuthApplication.java
```

Demo dùng Spring Boot 4.1.2 và Spring Security do Boot quản lý version. Java 17+ là yêu cầu nền. Spring Security Servlet dùng `jakarta.servlet.http`; đây **không** phải ví dụ WebFlux.

### 7.2. File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>header-auth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

Parent quản lý các dependency tương thích. Nếu tổ chức dùng Spring Boot nhánh khác, kiểm tra version và API Spring Security mà BOM chọn thay vì ghim thủ công một version không tương thích.

### 7.3. File HeaderAuthApplication.java

```java
package com.example.headerauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderAuthApplication.class, args);
    }
}

final class HeaderKeyAuthentication extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private HeaderKeyAuthentication(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    static HeaderKeyAuthentication presented(String rawKey) {
        return new HeaderKeyAuthentication(
                "unverified", rawKey, List.of(), false);
    }

    static HeaderKeyAuthentication verified(String actor) {
        return new HeaderKeyAuthentication(
                actor, null,
                List.of(new SimpleGrantedAuthority("data:read")),
                true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Only provider may verify credentials");
        }
        super.setAuthenticated(false);
    }
}

// Converter chỉ chuyển request thành token chưa xác thực.
final class HeaderKeyConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        Enumeration<String> headers =
                request.getHeaders("X-Demo-Key");

        if (!headers.hasMoreElements()) {
            return null;
        }

        String rawKey = headers.nextElement();

        if (headers.hasMoreElements()
                || rawKey == null
                || rawKey.isBlank()
                || rawKey.length() > 256) {
            throw new BadCredentialsException("Invalid key format");
        }

        return HeaderKeyAuthentication.presented(rawKey);
    }
}

// Provider duy nhất cấp principal và quyền sau xác minh.
final class HeaderKeyProvider implements AuthenticationProvider {

    private final byte[] expectedHash;

    HeaderKeyProvider(String expectedKey) {
        this.expectedHash = sha256(expectedKey);
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request instanceof HeaderKeyAuthentication keyToken)
                || keyToken.isAuthenticated()) {
            throw new BadCredentialsException(
                    "Invalid authentication request");
        }

        Object presented = keyToken.getCredentials();

        if (!(presented instanceof String raw)
                || !MessageDigest.isEqual(
                        expectedHash, sha256(raw))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return HeaderKeyAuthentication.verified("service-client");
    }

    @Override
    public boolean supports(Class<?> type) {
        return HeaderKeyAuthentication.class.isAssignableFrom(type);
    }

    private static byte[] sha256(String input) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        String expectedKey = System.getenv("DEMO_API_KEY");
        if (expectedKey == null || expectedKey.length() < 16) {
            throw new IllegalStateException(
                    "Set DEMO_API_KEY to at least 16 chars");
        }

        AuthenticationManager manager =
                new ProviderManager(new HeaderKeyProvider(expectedKey));

        AuthenticationFilter filter = new AuthenticationFilter(
                manager, new HeaderKeyConverter());

        filter.setRequestMatcher(request ->
                "GET".equals(request.getMethod())
                        && "/api/data".equals(request.getServletPath()));

        filter.setSecurityContextRepository(
                new RequestAttributeSecurityContextRepository());

        // Dạng bốn tham số tiếp tục chain tới authorization/controller.
        filter.setSuccessHandler(new AuthenticationSuccessHandler() {

            @Override
            public void onAuthenticationSuccess(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Authentication authentication) throws IOException {
                response.setStatus(HttpServletResponse.SC_OK);
            }

            @Override
            public void onAuthenticationSuccess(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain,
                    Authentication authentication)
                    throws IOException, ServletException {
                chain.doFilter(request, response);
            }
        });

        filter.setFailureHandler((request, response, ex) ->
                response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED));

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(
                                new RequestAttributeSecurityContextRepository()))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                        HttpStatus.UNAUTHORIZED)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/data")
                                .hasAuthority("data:read")
                        .anyRequest().denyAll())
                // Không khai báo filter là @Bean servlet toàn cục.
                .addFilterAfter(filter, LogoutFilter.class)
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/data")
    String data(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

### Diễn giải code theo vai trò

**Token riêng:** `presented(rawKey)` có `isAuthenticated=false` và không có authority. `verified("service-client")` chỉ do provider gọi trong trường hợp key được xác minh, gán `data:read` từ **server**. Override `setAuthenticated(true)` ngăn caller tùy tiện đánh dấu token presented là trusted. Không đưa entity JPA hoặc secret vào principal.

**Converter:** Trả null nếu không có header, ném exception nếu header sai dạng và trả token chưa xác thực nếu có một header hợp lệ. Nó không so khớp key và không tin bất kỳ `X-Role` nào.

**Provider:** Dùng `MessageDigest.isEqual` để so sánh digest; đây chỉ là minh họa so sánh một API key, không phải password hashing thích hợp với password có entropy thấp. Key production phải được sinh ngẫu nhiên mạnh, lưu dưới dạng digest/HMAC kiểm soát, có cơ chế revoke/rotate và giới hạn thử sai.

**Manager:** `ProviderManager` biết loại `HeaderKeyAuthentication` vì provider khai báo `supports(...)`. Không tự tạo một authenticated `UsernamePasswordAuthenticationToken` chỉ vì header có dữ liệu.

**Filter:** Matcher giới hạn GET `/api/data`. Không có header -> converter null -> filter tiếp tục, nhưng authorization vẫn từ chối. Có key sai -> provider ném `BadCredentialsException` -> failure handler 401.

**Success handler:** Dạng bốn tham số gọi `chain.doFilter`. Nếu không có bước này, một handler mặc định có thể trả redirect thay vì cho controller xử lý request. Context được filter đặt vào holder trước khi chain tiếp tục.

**Context/repository:** Dùng request-attribute repository và `STATELESS` để không duy trì login bằng session. Client phải trình credential lại ở mỗi GET `/api/data`.

**Authorization:** Rule `hasAuthority("data:read")` mới cho phép truy cập. `anyRequest().denyAll()` giúp không mở các URL khác ngoài dự kiến. Cấu hình không tùy tiện tắt CSRF; demo chỉ dùng GET.

## 8. Chạy ứng dụng và kiểm chứng HTTP

Để chạy với Maven:

```bash
export DEMO_API_KEY='local-demo-key-not-for-production'
mvn spring-boot:run
```

Nếu có Maven wrapper từ Spring Initializr:

```bash
export DEMO_API_KEY='local-demo-key-not-for-production'
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
$env:DEMO_API_KEY = 'local-demo-key-not-for-production'
./mvnw.cmd spring-boot:run
```

Key này **chỉ dùng trên localhost**, không triển khai ngoài Internet. Sau khi server chạy ở cổng 8080, mở terminal khác:

```bash
curl -i http://localhost:8080/public/ping

curl -i -H 'X-Demo-Key: local-demo-key-not-for-production' \
  http://localhost:8080/api/data

curl -i http://localhost:8080/api/data

curl -i -H 'X-Demo-Key: wrong-key' \
  http://localhost:8080/api/data
```

| Request | Kết quả dự kiến | Giải thích |
| --- | --- | --- |
| `GET /public/ping` không key | HTTP 200, body `pong` | Endpoint permitAll |
| `GET /api/data` key đúng | HTTP 200, body `hello service-client` | Provider xác minh, cấp `data:read` |
| `GET /api/data` không key | HTTP 401 | Converter null, authorization/entry point từ chối |
| `GET /api/data` key sai | HTTP 401 | Provider từ chối qua failure handler |
| `GET /api/data` key rỗng | HTTP 401 | Converter từ chối format |
| `POST /api/data` | Không được mở | Filter chỉ match GET; denyAll/CSRF áp dụng |

Header/body lỗi phụ thuộc cấu hình/framework, nên không kỳ vọng một JSON error cố định. Key trong ví dụ có thể xuất hiện trong terminal history; ở sản phẩm thật cần quy trình secret handling thích hợp và HTTPS.

### Dòng chảy của GET hợp lệ

```text
GET /api/data + X-Demo-Key hợp lệ
            |
            v
Matcher true
            |
            v
Converter -> HeaderKeyAuthentication chưa authenticated
            |
            v
ProviderManager -> HeaderKeyProvider
            |
            v
Digest khớp -> HeaderKeyAuthentication verified
            |
            v
AuthenticationFilter đặt SecurityContext
            |
            v
SuccessHandler -> chain.doFilter
            |
            v
AuthorizationFilter kiểm tra data:read
            |
            v
Controller -> "hello service-client"
```

Nếu key sai, controller không được gọi. Nếu key thiếu, converter không thử authenticate, nhưng policy không cho phép truy cập.

## 9. Converter khác Provider và Authorization ở đâu?

Một số yêu cầu tưởng giống nhau nhưng thuộc trách nhiệm khác:

| Câu hỏi | Thành phần |
| --- | --- |
| Header có tồn tại không? | Converter |
| Có nhiều header mập mờ không? | Converter |
| Key còn hiệu lực, chưa bị revoke không? | Provider/identity service |
| Key thuộc client nào? | Provider/nguồn tin cậy |
| Client được cấp permission nào? | Provider/authority mapping |
| Request có quyền gọi `GET /api/data` không? | AuthorizationManager |
| Client được đọc record thuộc tenant nào? | Domain authorization |
| Khi đăng nhập thành công có lưu session không? | Filter và SecurityContextRepository |
| Khi key sai trả 401/redirect/JSON nào? | Failure handler/entry point |

Một raw key không chứng minh user ID hay tenant được khai trong query. Nguồn key phải ánh xạ sang client/actor/tenant bền vững, rồi authorization kiểm tra phạm vi bản ghi. `Authentication.getName()` của demo trả `service-client`, nhưng tên principal không tự là khóa dữ liệu ổn định.

**Cấm nâng quyền từ input:** Không đọc `X-Role: ADMIN` và chuyển thành `SimpleGrantedAuthority("ROLE_ADMIN")` ở converter. Authorities chỉ có hiệu lực khi được gán bởi nguồn có thẩm quyền sau kiểm chứng.

## 10. So sánh với AbstractAuthenticationProcessingFilter và OncePerRequestFilter

`AbstractAuthenticationProcessingFilter` là lớp cơ sở cho nhiều cơ chế login, đặc biệt tương tác browser/form. Nó có hook `attemptAuthentication`, success/failure handlers, session authentication strategy, remember-me integration và các lifecycle khác. `AuthenticationFilter` là cách tổ hợp các thành phần: converter + manager + handlers, tránh subclass filter chỉ để thay cách đọc credential.

Hai lớp **không hoàn toàn tương đương**. Khi di trú từ subclass của `AbstractAuthenticationProcessingFilter` sang `AuthenticationFilter`, phải xem lại session fixation protection, saved request, event publishing, remember-me, security context persistence và behavior sau thành công, không chỉ đổi tên class.

Custom `OncePerRequestFilter` có thể phù hợp với logging, metrics hoặc policy đặc thù không phải authentication. Nhưng nếu tự implement authentication, bạn phải tự quản lý:

- Khi nào kiểm tra matcher và credential?
- Tạo untrusted token bằng gì?
- Gọi manager/provider nào?
- Xóa context khi failure?
- Save context vào repository nào?
- Có tiếp tục filter chain sau success?
- Lỗi authentication/authorization được dịch ra response ở đâu?
- Có chạy hai lần do servlet registration không?

Nếu các câu hỏi trên đều thuộc authentication, dùng `AuthenticationFilter` thường rõ ràng hơn.

## 11. Ưu tiên cơ chế chuẩn khi không có yêu cầu đặc biệt

Spring Security có cơ chế tiêu chuẩn như:

- `httpBasic` và `BasicAuthenticationFilter`.
- `formLogin`, `UsernamePasswordAuthenticationFilter`.
- `oauth2ResourceServer().jwt(...)`, `BearerTokenAuthenticationFilter` và JWT validation/converter.
- OAuth2 Login, SAML và những authentication flow được hỗ trợ khác.

**Không cần tự viết converter cho Basic hoặc tự verify JWT signature bằng vài dòng code** khi framework đã xử lý protocol: header parsing, challenge, issuer, audience, expiry, signature, key rotation, error handling và nhiều trường hợp cạnh.

Custom `AuthenticationFilter` hữu ích khi bạn có một cơ chế credential riêng cần tích hợp vào Spring Security manager/provider. Ví dụ bài học dùng header `X-Demo-Key`, nhưng với production cần đánh giá xem dùng một identity standard hay gateway đã có hỗ trợ API key có an toàn và dễ vận hành hơn không.

### Không nhầm Bearer token với API key

Một bearer access token có thể chứa signature/issuer/audience/scope; một API key thường là secret opaque do hệ thống tự quản lý. Hai loại có vòng đời, lưu trữ và thu hồi khác. Đừng thay `BearerTokenAuthenticationFilter` bằng custom converter chỉ lấy header rồi coi token đúng nếu không rỗng.

## 12. Stateful, stateless và lưu SecurityContext

Một request authenticated không đồng nghĩa mọi request sau đó cũng authenticated. Trong demo:

```text
Request 1: GET /api/data + key đúng -> 200
Request 2: GET /api/data không key -> 401
```

Vì `SessionCreationPolicy.STATELESS` và `RequestAttributeSecurityContextRepository`, kết quả chỉ dùng trong request hiện tại. **Không tự tạo session login**.

Nếu là ứng dụng browser dùng cookie:

- Dùng repository lưu HTTP session khi phù hợp.
- Thiết kế login success handler redirect/response phù hợp.
- Giữ CSRF protection cho thao tác thay đổi trạng thái.
- Xem session fixation, concurrent session, logout và remember-me.
- Không lưu raw credential vào session.
- Xác định khi nào SecurityContext được save; trong Spring Security mới, việc save explicit có thể quan trọng.

Nếu là API token/JWT:

- Mỗi request phải verify token hoặc tham khảo token introspection đã tin cậy.
- Context có thể request-scoped; token TTL/revocation là cơ chế khác.
- Phải kiểm tra quyền theo request và resource; auth success không cấp tất cả quyền.
- Không dùng cookie session như một fallback không được thiết kế.

## 13. Xử lý lỗi: filter failure handler và entry point khác nhau

Hai trường hợp cùng có thể trả HTTP 401 nhưng đường xử lý khác nhau:

```text
Header có nhưng sai
    Converter -> token
    Provider -> AuthenticationException
    AuthenticationFilter.failureHandler -> HTTP 401

Không có header
    Converter -> null
    Filter -> chain tiếp tục
    AuthorizationFilter từ chối anonymous
    ExceptionTranslationFilter -> AuthenticationEntryPoint -> HTTP 401
```

Không phải mọi lỗi filter authentication đều được `ExceptionTranslationFilter` xử lý. Tương tự, `@RestControllerAdvice` không được đảm bảo bắt exception từ security filter trước controller.

HTTP 403 thường biểu thị caller đã được xác thực nhưng thiếu authority. Một rate limiter có thể trả 429; lỗi nguồn IDP/DB có thể cần 5xx/503 theo policy. Không suy luận từ HTTP 401 rằng mật khẩu sai hay user tồn tại.

Phản hồi công khai nên trung lập, không xuất raw `ex.getMessage()`, header credential hoặc nội dung database. Logging nội bộ có thể ghi loại lỗi và correlation ID nhưng không ghi secret. Định nghĩa recovery theo giao thức thay vì im lặng cấp quyền thấp khi auth backend lỗi.

## 14. Security hardening cho custom converter/filter

Những điểm phải đánh giá nếu mang thiết kế API key vào production:

1. **TLS:** credential đi qua header vẫn có thể bị lộ nếu dùng HTTP.
2. **Nguồn key:** tạo secret ngẫu nhiên entropy cao, key ID riêng, kiểm tra key còn hạn và bị revoke không.
3. **Lưu trữ:** hash/HMAC key ở nguồn có kiểm soát; không lưu plaintext key trong code, config commit hay log.
4. **So sánh:** tránh so sánh credential bằng string equals khi cần hạn rò timing; một phép so sánh digest constant-time là một lớp bảo vệ, không thay rate limiting.
5. **Giới hạn request:** độ dài header, số header trùng, encoding và normalization phải có policy.
6. **Rate limiting:** chống key brute force và DoS hashing/backing store.
7. **Principal stable ID:** gắn key với account/client ID và tenant từ nguồn server.
8. **Quyền tối thiểu:** chỉ cấp permission đã định nghĩa; endpoint có owner/resource authorization.
9. **Rotation/revocation:** key cũ bị từ chối theo yêu cầu SLA, cache invalidation có thời hạn.
10. **Không log secret:** raw header, password, bearer token và session cookie không được xuất ra tracing.
11. **Không permitAll ngoài ý muốn:** converter null không được biến thành anonymous access tới protected path.
12. **Filter order:** xác định chain và vị trí sau authentication/CSRF support phù hợp.
13. **Nhiều provider:** chỉ accept loại token đúng contract; đừng để provider fallback không rõ.
14. **Session policy:** stateless/stateful phải tường minh, không trộn auth bằng header với session dài hạn ngoài policy.
15. **Error response:** generic cho client, đầy đủ telemetry cho vận hành, không leak account/key.
16. **Version updates:** kiểm tra dependency Spring Security hiện hành và advisory định kỳ.

### Đừng gọi SHA-256 của key là password hashing

Demo dùng SHA-256 digest để minh họa so sánh một **API key được kỳ vọng có entropy cao**. Với password do con người chọn, phải dùng `PasswordEncoder` kiểu BCrypt, Argon2 hay tương đương có work factor; SHA-256 trực tiếp quá nhanh cho mục đích đó. Hai bài toán không được hoán đổi.

## 15. Ma trận kiểm thử converter, provider, filter và authorization

| Tầng | Trường hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| Converter | Không có header | `convert(req) == null` |
| Converter | Một header đúng format | Token chưa authenticated, authorities rỗng |
| Converter | Header rỗng | `BadCredentialsException` |
| Converter | Hai header hoặc quá dài | Bị từ chối |
| Converter | Có `X-Role: ADMIN` | Không cấp role theo input |
| Provider | API key đúng | Principal server cấp, authority `data:read` |
| Provider | API key sai | Không authenticated |
| Provider | Token type không hỗ trợ | `supports(...) == false` |
| Provider | Cố truyền trusted token từ client | Không bỏ qua kiểm chứng |
| Filter | Matcher không khớp | Converter không được gọi |
| Filter | Thành công có continue handler | Controller được gọi đúng một lần |
| Filter | Failure | SecurityContext không có trusted result |
| HTTP | Public endpoint anonymous | 200 |
| HTTP | Protected endpoint key đúng | 200, body chính xác |
| HTTP | Protected endpoint thiếu/sai key | 401 |
| HTTP | Authenticated nhưng thiếu quyền | 403 |
| HTTP | Sai method/path | Không mở tự động |
| Context | Request tiếp theo không key | Không giữ authenticated session từ request trước |
| Chain | Hai SecurityFilterChain | Chọn đúng chain theo matcher/order |
| Registration | Filter bean vừa auto-register vừa addFilter | Không bị double invocation |
| Safety | Log/error | Không lộ raw key, password, token |
| Tenant | Key của tenant A gọi tài nguyên B | Domain policy từ chối |
| Revocation | Key bị thu hồi | Request mới không được chấp nhận |

### Lưu ý khi viết test tích hợp

Với Spring Security Test và MockMvc, phải khởi động đúng `SecurityFilterChain` chứ không chỉ gọi controller trực tiếp. Test riêng cả **header không có** (converter trả null) và **header sai** (provider ném exception) vì chúng đi qua hai handler khác nhau.

Test default success handler: nếu bỏ override dạng bốn tham số, filter có thể không đưa request tới controller. Kiểm tra body `hello service-client`, không chỉ một status thành công mơ hồ.

Test multi-chain: nếu ứng dụng thật có hai chain, request nào match chain đầu tiên sẽ không tự chạy chain thứ hai. Phải kiểm tra filter không được gắn sai vào browser login hoặc các endpoint public.

## 16. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Converter tự tạo authenticated token | Bypass kiểm chứng | Token presented chưa tin, verified từ provider |
| Converter tạo role từ request | Privilege escalation | Provider nạp quyền tin cậy |
| Converter trả null nhưng endpoint permitAll | Mở dữ liệu | Authorization rule đúng |
| Quên `setRequestMatcher` | Filter xử lý quá nhiều URL | Match path/method cụ thể |
| Dùng token type username/password cho API key | Có thể chọn provider sai | Custom type hoặc DSL chuẩn |
| Bỏ qua `AuthenticationManager` | Tự viết lại authentication | Gọi manager/provider |
| Đặt filter sau AuthorizationFilter | Từ chối trước khi có principal | Kiểm tra thứ tự filter |
| Default success handler cho REST data | Redirect hoặc không tới controller | Handler tiếp tục chain |
| Filter được auto-register hai lần | Request chạy lặp | Tránh @Bean servlet filter cùng addFilter |
| Không chọn repository phù hợp | State thất lạc hoặc bị lưu ngoài ý định | Context/session policy rõ |
| Tưởng 401 nào cũng từ converter | Sai cách debug | Phân biệt failure/entry point |
| Dùng `@RestControllerAdvice` cho mọi security failure | Filter error bị bỏ sót | Dùng security handlers |
| Tự disable CSRF vô điều kiện | Browser cookie bị CSRF | Giữ policy cho request thay đổi dữ liệu |
| Gửi key qua query string | Lộ ở URL/history/log | Credential qua header + TLS |
| SHA-256 key có entropy thấp | Dễ bị đoán | Key random mạnh và rotation |
| Không test duplicate header | Proxy/app parse lệch | Giới hạn format |
| Tin `getName()` làm account ID | Dễ nhầm khi rename/tenant | Dùng stable ID |
| Không test stateless | Session xuất hiện ngoài ý muốn | Request 2 không key phải bị từ chối |
| Tự sửa SecurityContextHolder trong converter | Context leakage | Filter chịu trách nhiệm |
| Không test actual chain | Pass unit, fail production | MockMvc/integration filter tests |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `AuthenticationConverter.convert` trả null nghĩa là gì?  
**Đáp án:** Không tạo authentication attempt từ request ấy; filter tiếp tục, authorization vẫn áp dụng.

**Câu 2.** Converter thấy `X-Role: ADMIN` có nên gán `ROLE_ADMIN` không?  
**Đáp án:** Không. Role từ client chưa đáng tin; provider/nguồn quyền xác minh mới quyết định.

**Câu 3.** Cần `AuthenticationManager` để làm gì sau converter?  
**Đáp án:** Xác minh credential bằng provider phù hợp rồi tạo authenticated result.

**Câu 4.** `setRequestMatcher` có đồng nghĩa cấp quyền cho URL không?  
**Đáp án:** Không. Nó chỉ quyết định filter có xử lý request đó hay không; quyền thuộc authorization.

**Câu 5.** Vì sao handler thành công dạng bốn tham số hữu ích cho API?  
**Đáp án:** Có thể gọi `chain.doFilter` để request đi tiếp vào authorization/controller.

**Câu 6.** Tại sao request key đúng lần 1 không làm request không key lần 2 hợp lệ?  
**Đáp án:** Vì demo stateless và dùng request-attribute context, không lưu session.

**Câu 7.** Dùng `@Bean` filter và `http.addFilterAfter` cùng lúc có thể gây gì?  
**Đáp án:** Filter bị đăng ký chạy hai lần hoặc ngoài Spring Security chain.

**Câu 8.** Header sai và thiếu header có đi cùng một handler không?  
**Đáp án:** Không nhất thiết. Sai key qua failure handler của filter; thiếu key có thể qua authorization/entry point.

**Câu 9.** Khi nào nên chọn manager resolver?  
**Đáp án:** Khi cần chọn manager theo context tin cậy, chẳng hạn nhiều realm/issuer; không cho phép bypass bằng header tenant tự khai.

**Câu 10.** Custom AuthenticationFilter có nên tự kiểm tra JWT signature từ một chuỗi tùy ý không?  
**Đáp án:** Không nên khi Spring Security OAuth2 Resource Server đã cung cấp decoder/validation chuẩn.

**Câu 11.** Một caller authenticated có `data:read` có tự được đọc mọi tenant không?  
**Đáp án:** Không. Cần kiểm tra owner/tenant trong domain policy.

**Câu 12.** Có phải `@RestControllerAdvice` bắt mọi authentication failure từ filter?  
**Đáp án:** Không. Security filter chạy trước MVC và có failure handler/entry point riêng.

## Kết luận

`AuthenticationConverter` chuyển HTTP request thành **Authentication chưa xác minh**. `AuthenticationFilter` dùng matcher để quyết định khi nào chuyển đổi, gọi `AuthenticationManager`/`AuthenticationProvider`, cập nhật `SecurityContext` và giao kết quả cho success/failure handler. Sau đó `AuthorizationFilter` và domain policy mới quyết định caller được làm gì.

Một tích hợp bảo mật tốt cần **request matcher hẹp, provider đúng loại credential, handler phù hợp với REST hay browser, filter order chính xác, context repository khớp mô hình phiên, và kiểm thử cả request thiếu credential lẫn credential sai**.

**Ghi nhớ:** *Converter đọc bằng chứng. Provider kiểm chứng. Filter quản lý kết quả. Authorization thực thi quyền.*

### Tài liệu chính thức

- [Spring Security — AuthenticationConverter API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html)
- [Spring Security — AuthenticationFilter API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html)
- [Spring Security — AuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html)
- [Spring Security — Servlet Architecture / Adding Filters](https://docs.spring.io/spring-security/reference/7.0/servlet/architecture.html)
- [Spring Security — SecurityContext persistence](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/persistence.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html)
- [Spring Boot 4.1.2 – release](https://github.com/spring-projects/spring-boot/releases/tag/v4.1.2)
