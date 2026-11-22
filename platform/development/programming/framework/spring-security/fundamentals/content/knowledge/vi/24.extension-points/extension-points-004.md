# Chuyển đổi thông tin đầu vào thành Authentication

> **Chủ đề:** Điểm mở rộng trong Spring Security — fundamentals. Bài tập trung vào Spring Security **Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Với WebFlux, những khái niệm tương tự được triển khai bằng các API reactive riêng; không thể dùng trực tiếp `HttpServletRequest` và Servlet filter trong WebFlux.

## 1. Vì sao cần chuyển đổi đầu vào thành Authentication?

Một request có thể mang thông tin nhận dạng theo nhiều dạng:

- Form đăng nhập: `username=alice&password=...`.
- HTTP Basic: `Authorization: Basic ...`.
- Bearer access token: `Authorization: Bearer ...`.
- API key do ứng dụng quy định, ví dụ `X-Api-Key: ...`.
- Client certificate hoặc assertion trong một cơ chế được hỗ trợ.

**Dữ liệu đầu vào chưa phải là danh tính được tin cậy.** Spring Security cần biểu diễn yêu cầu xác thực bằng đối tượng thuộc giao diện `org.springframework.security.core.Authentication`. Sau đó, `AuthenticationManager` cùng `AuthenticationProvider` thích hợp kiểm tra bằng chứng, trả về `Authentication` đã xác thực hoặc ném `AuthenticationException`.

Đây là một **điểm mở rộng** quan trọng: khi ứng dụng có một cách gửi credentials riêng, có thể thay cách **trích xuất và đóng gói đầu vào**, đồng thời vẫn giữ kiến trúc xác thực và phân quyền nhất quán.

Sơ đồ vai trò:

~~~mermaid
flowchart LR
    A["HTTP request<br/>header / form / token"] --> B["AuthenticationConverter<br/>đọc + diễn giải đầu vào"]
    B -->|"Authentication chưa xác thực"| C["AuthenticationManager"]
    C --> D["AuthenticationProvider<br/>kiểm tra bằng chứng"]
    D -->|"Authentication đã xác thực"| E["SecurityContext"]
    E --> F["Authorization<br/>kiểm tra quyền"]
    B -->|"null: không có yêu cầu xác thực phù hợp"| G["Tiếp tục filter chain"]
    B -->|"AuthenticationException"| H["Phản hồi lỗi xác thực"]
    D -->|"AuthenticationException"| H
~~~

**Điểm cốt lõi:** converter trả lời “client đang đưa bằng chứng gì?”, provider/manager trả lời “bằng chứng đó có đáng tin không?”. Không cấp quyền dựa trên chuỗi do client tự khai trong converter.

## 2. Đối tượng Authentication trước và sau khi xác thực

`Authentication` vừa là **đầu vào** cho quá trình xác thực, vừa có thể là **kết quả** đại diện người dùng/ứng dụng sau xác thực.

Các thuộc tính cần hiểu:

| Thuộc tính | Trước xác thực | Sau xác thực thành công |
|---|---|---|
| `principal` | Có thể là username tự khai, ID dự kiến, hoặc chưa biết | Danh tính đã được server xác minh, ví dụ `UserDetails` hoặc client ID |
| `credentials` | Mật khẩu, API key, token… cần kiểm tra | Nên xóa hoặc không giữ dữ liệu nhạy cảm khi không cần |
| `authorities` | Không được tin các role/scope client tự khai | Quyền do phía server xác minh hoặc ánh xạ từ bằng chứng hợp lệ |
| `isAuthenticated()` | `false` | Thông thường `true`, được thiết lập bởi thành phần đáng tin sau khi xác thực |

Ví dụ với username/password:

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "secret-from-request");

// requestToken.isAuthenticated() == false
Authentication result = authenticationManager.authenticate(requestToken);
// Nếu thành công, result thường có principal + authorities đã xác minh.
~~~

Đoạn trên là **minh họa cần một `authenticationManager` được cấu hình**; nó không phải chương trình Java độc lập và không có stdout. Đừng gọi `UsernamePasswordAuthenticationToken.authenticated(...)` ngay khi chỉ mới đọc username/password từ request. Factory đó dành cho mã nguồn **đã có cơ sở tin cậy** để tạo kết quả xác thực.

Một `Authentication` chưa xác thực thường chỉ là **lời yêu cầu kiểm tra**. Dù nó có trường `principal="admin"` hoặc `authorities=["ROLE_ADMIN"]` từ payload, những giá trị này không thể mặc nhiên trở thành quyền thật.

## 3. Điểm mở rộng AuthenticationConverter

Với Servlet stack, Spring Security cung cấp giao diện:

~~~java
package org.springframework.security.web.authentication;

public interface AuthenticationConverter {
    Authentication convert(jakarta.servlet.http.HttpServletRequest request);
}
~~~

Đây là chữ ký rút gọn để học khái niệm; chú thích `@Nullable` và các metadata khác không được thể hiện. `convert(...)` làm việc với request HTTP và trả một trong ba kết quả:

1. **Trả một `Authentication` chưa xác thực:** có đủ dữ liệu theo scheme mà converter chịu trách nhiệm, ví dụ lấy username và password rồi tạo `UsernamePasswordAuthenticationToken.unauthenticated(...)`.
2. **Trả `null`:** không tìm thấy yêu cầu xác thực mà converter nhận diện; filter sử dụng converter có thể bỏ qua lượt xác thực này và cho request đi tiếp. `null` **không có nghĩa là đã đăng nhập thành công**.
3. **Ném `AuthenticationException`:** request chủ động dùng scheme đó nhưng dữ liệu sai cấu trúc, trùng header, credentials trống hoặc không parse được theo hợp đồng. Thường dùng `BadCredentialsException`, không ném tùy tiện `RuntimeException` làm server trả 500.

Ví dụ một converter từ header riêng:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;

final class ExampleHeaderConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String username = request.getHeader("X-Demo-User");
        String password = request.getHeader("X-Demo-Password");

        if (username == null && password == null) {
            return null;
        }
        if (username == null || username.isBlank()
                || password == null || password.isBlank()) {
            throw new BadCredentialsException("Incomplete credentials");
        }
        return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
    }
}
~~~

Đây là ví dụ **chỉ để nhìn rõ hợp đồng converter**, chưa được gắn vào filter/manager và không phải phương án truyền mật khẩu tùy biến nên dùng trong sản phẩm. Ứng dụng thực tế nên dùng cơ chế chuẩn như Basic qua HTTPS, form login được bảo vệ, hoặc OAuth2/OIDC khi phù hợp.

### Phân biệt ba việc dễ trộn lẫn

- **Parsing/normalization:** xác định header hoặc field, kiểm tra định dạng và tạo token đầu vào → converter.
- **Verification:** tra cứu user, kiểm tra password hash/chữ ký token/revocation/issuer/audience, tìm principal thật → provider/manager hoặc thành phần xác thực chuyên trách.
- **Authorization:** đối chiếu `GrantedAuthority`, role, scope và chính sách của endpoint → `AuthorizationManager`/method security.

Converter không nên tự quyết định `ROLE_ADMIN`, không tự tạo trusted token và không tự viết `SecurityContextHolder`. Cách phân tách này giúp kiểm thử và thay thế input format mà không phá chính sách bảo mật.

## 4. Converter được sử dụng ở đâu trong filter chain?

Một converter **không tự được chạy** chỉ vì có bean `@Component`. Phải có filter/chức năng gọi nó và xử lý kết quả. Một mô hình phổ biến:

~~~text
Request -> SecurityFilterChain
    -> Authentication filter nhận request phù hợp
        -> AuthenticationConverter.convert(request)
           - null: không xác thực theo scheme này
           - Authentication chưa xác thực:
                -> AuthenticationManager.authenticate(...)
                    -> AuthenticationProvider.authenticate(...)
                       -> success: Authentication đã xác thực
                       -> failure: AuthenticationException
           - exception: phản hồi lỗi theo cơ chế của filter
        -> success: SecurityContext hoặc success handler
    -> AuthorizationFilter
    -> Controller
~~~

`AuthenticationFilter` là filter tổng quát có thể nhận `AuthenticationConverter` và `AuthenticationManager`, thường cấu hình cùng **request matcher**, **success handler** và **failure handler** cho một yêu cầu xác thực chuyên biệt như endpoint đăng nhập. Sau thành công, loại filter này thường giao quyền xử lý phản hồi cho success handler; không nên tự giả định nó luôn tiếp tục chạy controller ban đầu.

Trong các cơ chế có sẵn, Spring Security thường đã cung cấp bước đọc/chuyển đổi credentials phù hợp: HTTP Basic dùng `BasicAuthenticationConverter`; một resource server nhận Bearer token bằng các thành phần riêng của OAuth2. **Ưu tiên cơ chế có sẵn** nếu giao thức đã chuẩn hóa.

Nếu muốn **xác thực mỗi request** bằng API key rồi tiếp tục xử lý API endpoint, có thể xây dựng một `OncePerRequestFilter` gọi converter và manager, đặt kết quả vào một `SecurityContext` mới, rồi gọi `filterChain.doFilter(...)`. Ví dụ dưới đây minh họa cách này. Đây là lựa chọn có chủ đích vì nó cho thấy đầy đủ “request → converter → manager/provider → context → authorization”.

## 5. Ví dụ hoàn chỉnh: chuyển X-Api-Key thành Authentication

**Mục tiêu:** `GET /api/data` yêu cầu header `X-Api-Key`. Converter chỉ đọc header và tạo một token **chưa xác thực**. Provider so sánh API key với giá trị demo phía server, trả lại token **đã xác thực** mang `ROLE_READER`. Filter đặt token vào `SecurityContext` của **request hiện tại**. Chỉ sau đó controller mới được chạy.

Dùng **Java 17+**, **Spring Boot 3.5.0 / Spring Security 6.x**, Maven. Giá trị key trong ví dụ công khai để phục vụ học tập; tuyệt đối không dùng nó như secret production.

Cấu trúc:

~~~text
api-key-demo/
├── pom.xml
└── src/main/java/com/example/apikey/
    ├── ApiKeyDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

### 5.1. pom.xml

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
    <groupId>com.example</groupId>
    <artifactId>api-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

### 5.2. ApiKeyDemoApplication.java

~~~java
package com.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

Toàn bộ các thành phần demo được gom vào một tệp cho dễ chạy. Trong dự án thật, converter, token, provider và filter có thể nằm ở các class/tệp riêng. **Không đăng ký filter tùy biến dưới dạng `@Component`** ở ví dụ này để tránh Spring Boot tự đăng ký nó thêm lần nữa tại servlet container.

~~~java
package com.example.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class SecurityConfig {

    private static final String HEADER = "X-Api-Key";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint entryPoint = (request, response, failure) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"error\":\"authentication_required\"}");
        };

        AuthenticationConverter converter = new HeaderApiKeyConverter();
        AuthenticationManager manager =
                new ProviderManager(new DemoApiKeyProvider());

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .addFilterAfter(
                new ApiKeyFilter(converter, manager, entryPoint),
                LogoutFilter.class);

        return http.build();
    }

    // Token do converter tạo: untrusted; do provider tạo: trusted.
    private static final class ApiKeyToken extends AbstractAuthenticationToken {
        private final Object principal;
        private final Object credentials;

        private ApiKeyToken(
                Object principal,
                Object credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean trusted) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(trusted);
        }

        static ApiKeyToken unauthenticated(String suppliedKey) {
            return new ApiKeyToken(null, suppliedKey, List.of(), false);
        }

        static ApiKeyToken verified(
                String trustedPrincipal,
                Collection<? extends GrantedAuthority> authorities) {
            return new ApiKeyToken(trustedPrincipal, null, authorities, true);
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
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                        "Only the verified factory can create trusted tokens");
            }
            super.setAuthenticated(false);
        }
    }

    // 1. Chỉ diễn giải HTTP input và tạo Authentication chưa xác thực.
    private static final class HeaderApiKeyConverter
            implements AuthenticationConverter {

        @Override
        public Authentication convert(HttpServletRequest request) {
            Enumeration<String> values = request.getHeaders(HEADER);
            if (values == null || !values.hasMoreElements()) {
                return null;
            }

            String suppliedKey = values.nextElement();
            if (values.hasMoreElements()
                    || suppliedKey == null
                    || suppliedKey.isBlank()) {
                throw new BadCredentialsException("Malformed API key header");
            }

            return ApiKeyToken.unauthenticated(suppliedKey);
        }
    }

    // 2. Kiểm tra bằng chứng; quyền và principal do server cấp.
    private static final class DemoApiKeyProvider
            implements AuthenticationProvider {

        private static final byte[] EXPECTED =
                "demo-key-123".getBytes(StandardCharsets.UTF_8);

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyToken token)) {
                return null;
            }

            Object raw = token.getCredentials();
            if (!(raw instanceof String suppliedKey)) {
                throw new BadCredentialsException("Missing API key");
            }
            if (!MessageDigest.isEqual(
                    EXPECTED,
                    suppliedKey.getBytes(StandardCharsets.UTF_8))) {
                throw new BadCredentialsException("Invalid API key");
            }

            return ApiKeyToken.verified(
                    "demo-client",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyToken.class.isAssignableFrom(type);
        }
    }

    // 3. Dùng converter + manager cho mỗi request /api/... .
    private static final class ApiKeyFilter extends OncePerRequestFilter {

        private final AuthenticationConverter converter;
        private final AuthenticationManager manager;
        private final AuthenticationEntryPoint entryPoint;

        ApiKeyFilter(
                AuthenticationConverter converter,
                AuthenticationManager manager,
                AuthenticationEntryPoint entryPoint) {
            this.converter = converter;
            this.manager = manager;
            this.entryPoint = entryPoint;
        }

        @Override
        protected boolean shouldNotFilter(HttpServletRequest request) {
            return !request.getServletPath().startsWith("/api/");
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            Authentication verified = null;
            try {
                Authentication candidate = converter.convert(request);
                if (candidate != null) {
                    verified = manager.authenticate(candidate);
                }
            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                entryPoint.commence(request, response, ex);
                return;
            }

            if (verified != null) {
                SecurityContext context =
                        SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
            }

            chain.doFilter(request, response);
        }
    }
}
~~~

**Cách các thành phần hợp tác:**

1. `HeaderApiKeyConverter` chỉ kiểm tra sự có mặt, tính duy nhất và dạng cơ bản của header; nó trả `ApiKeyToken.unauthenticated(...)`. Chỉ có converter thì **chưa xác thực được ai**.
2. `DemoApiKeyProvider` xác thực key; khi hợp lệ, nó tự cấp principal `demo-client`, authority `ROLE_READER` và không đưa API key vào token kết quả. Client không được khai role qua header.
3. `ProviderManager` điều phối provider theo loại token. `supports(...)` xác định provider có thể xử lý loại `Authentication` này; nếu không provider nào phù hợp, quá trình xác thực không thành công.
4. `ApiKeyFilter` đặt `Authentication` **đã xác minh** vào một `SecurityContext` mới rồi mới cho filter chain chạy tiếp. Nếu không có header, converter trả `null`: request tiếp tục và quy tắc `authenticated()` sẽ từ chối endpoint bảo vệ; `ExceptionTranslationFilter` khởi động entry point cho anonymous caller.
5. Nếu header không hợp lệ hoặc key sai, converter/provider ném `AuthenticationException`; filter bắt ngoại lệ ở **chính đoạn chuyển đổi/xác thực** và gọi entry point để trả 401. Đoạn `chain.doFilter(...)` ở **ngoài** `try/catch` này để không vô tình nuốt các lỗi của filter/controller phía sau.
6. `SessionCreationPolicy.STATELESS` nghĩa là ví dụ không ghi nhớ `SecurityContext` vào HTTP session cho lần gọi sau. Client phải gửi key hợp lệ trên mỗi request cần bảo vệ.
7. Không cấu hình Basic/form login để hai cơ chế đó không cạnh tranh với header tùy biến. Đặt custom filter **sau `LogoutFilter`** giúp thực hiện xác thực trước authorization.
8. CSRF protection **vẫn giữ mặc định**. Ví dụ chỉ dùng `GET`; nếu thêm API thay đổi trạng thái, thiết kế CSRF phải dựa trên kiểu client và cơ chế gửi credentials, không mặc định tắt cho mọi ứng dụng.

**Lưu ý về API key demo:** Giá trị `demo-key-123` được hard-code và trình bày rõ ràng để người học tái hiện kết quả. Bản production cần secret manager/config an toàn, key đủ entropy, xoay vòng, thu hồi, giới hạn quyền, HTTPS, rate limiting và ánh xạ identity/authorities từ hệ thống đáng tin. Phép so sánh `MessageDigest.isEqual` chỉ minh họa việc tránh so sánh chuỗi đơn giản; nó không thay thế toàn bộ thiết kế API key an toàn.

### 5.4. DemoController.java

~~~java
package com.example.apikey;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/data")
    public String data(Authentication authentication) {
        return "data:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
~~~

### 5.5. Chạy và quan sát kết quả

Yêu cầu JDK 17+ và Maven đã cài. Tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Terminal thứ hai:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/data
curl -i -H "X-Api-Key: wrong" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" http://localhost:8080/api/admin
~~~

Với Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần. Chỉ các dòng request trên được coi là bước thử; status và body có thể xem ngay trong kết quả `-i`.

| Trường hợp | Status mong đợi | Điều quan sát được |
|---|---|---|
| `GET /public` | `200` | Body `public` |
| `GET /api/data` không có `X-Api-Key` | `401` | Body JSON `{"error":"authentication_required"}` |
| `GET /api/data` key `wrong` | `401` | Cùng JSON lỗi, không lộ nguyên nhân chi tiết |
| `GET /api/data` key `demo-key-123` | `200` | Body chính xác `data:demo-client` |
| `GET /api/admin` key hợp lệ | `403` | Đã xác thực nhưng chỉ có `ROLE_READER`, thiếu `ROLE_ADMIN` |

Lưu ý: với `403`, ví dụ chỉ cam kết **status**; body do handler mặc định/servlet container quyết định. Các header phụ như `Date`, `Content-Length`, `Cache-Control` cũng có thể thay đổi theo môi trường. Một request thành công **không đăng nhập cho request sau** vì đây là cấu hình stateless.

Thử thêm hai trường hợp:

~~~bash
curl -i -H "X-Api-Key:" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" -H "X-Api-Key: another" http://localhost:8080/api/data
~~~

Dòng thứ hai kiểm tra chính sách từ chối **hai giá trị header**. Dòng đầu với header rỗng có thể bị client/proxy chuẩn hóa thành “không có header”, nhưng cả hai cách đều phải dẫn đến `401` cho endpoint bảo vệ.

## 6. Vì sao conversion chưa phải authentication?

Dòng lệnh sau cho thấy thông điệp quan trọng:

~~~text
X-Api-Key: demo-key-123
    |
    v
HeaderApiKeyConverter.convert(request)
    -> ApiKeyToken(credentials="demo-key-123", authenticated=false)
    |
    v
ProviderManager.authenticate(token)
    -> DemoApiKeyProvider xác minh secret
    -> ApiKeyToken(principal="demo-client",
                   authorities=["ROLE_READER"],
                   credentials=null,
                   authenticated=true)
    |
    v
SecurityContextHolder: Authentication đã xác minh
    |
    v
AuthorizationFilter: /api/data -> allow; /api/admin -> deny
~~~

Nếu `AuthenticationConverter` tự gọi `setAuthenticated(true)` hoặc tạo trusted token bằng những role client gửi tới, attacker có thể bỏ qua bước chứng minh danh tính. Đối tượng token đầu vào không phải bằng chứng đã kiểm chứng. Vì vậy ví dụ tạo hai factory riêng, cấm chuyển token chưa tin cậy thành `authenticated=true` bằng setter công khai và chỉ để provider tạo token đã xác thực.

Việc chọn **loại `Authentication`** cũng quan trọng. `ProviderManager` chọn `AuthenticationProvider` thông qua `supports(Class<?> type)`. Nếu converter trả `ApiKeyToken` mà hệ thống chỉ có `DaoAuthenticationProvider` hỗ trợ username/password, sẽ không có provider phù hợp. Thêm converter không tự sinh provider tương ứng.

## 7. Các cách chuyển đổi đầu vào thường gặp

| Nguồn đầu vào | Token/đầu vào điển hình | Việc cần xác minh tiếp theo |
|---|---|---|
| Form login username/password | `UsernamePasswordAuthenticationToken` chưa xác thực | Account, password hash, trạng thái tài khoản |
| HTTP Basic | Username/password trích từ header Basic | Username/password qua provider phù hợp |
| Bearer token | Biểu diễn credential Bearer (tùy cơ chế) | Chữ ký, thời gian, issuer, audience, quyền và các chính sách token |
| API key riêng | Custom `Authentication` chưa xác thực | Key có tồn tại/hợp lệ/còn hiệu lực, gắn với principal nào |
| Client certificate | Thông tin chứng chỉ do TLS/container cung cấp | Chuỗi tin cậy, hiệu lực, ánh xạ danh tính, chính sách liên quan |

**Không suy ra từ `Authorization: Bearer ...` rằng token đã hợp lệ.** Phần đọc header chỉ giải quyết cú pháp/định dạng; đánh giá tính hợp lệ phải dựa trên cơ chế OAuth2 Resource Server hoặc provider chuyên dụng.

**Đừng nhầm `JwtAuthenticationConverter` với `AuthenticationConverter` ở Servlet:** `JwtAuthenticationConverter` nhận `Jwt` đã qua bước giải mã/xác minh từ resource server, sau đó ánh xạ thành `AbstractAuthenticationToken` (đặc biệt principal/authorities). Trong khi `AuthenticationConverter` đang học nhận trực tiếp `HttpServletRequest`. Cả hai đều chuyển đổi dữ liệu nhưng nhận đầu vào ở **hai giai đoạn khác nhau**.

Nếu ứng dụng hỗ trợ nhiều scheme, có thể dùng `DelegatingAuthenticationConverter` (có trong các phiên bản Spring Security 6.3+) để thử nhiều converter theo thứ tự và lấy kết quả **khác `null` đầu tiên**. Cần thiết kế rõ request matcher và thứ tự: không để converter dành cho scheme A nuốt lỗi của scheme B hoặc chấp nhận một header không được dự kiến.

## 8. Quy tắc thiết kế converter an toàn

### 8.1. Phân biệt vắng mặt và sai định dạng

- **Không có credentials của scheme**: trả `null` để filter quyết định có thể đi tiếp hay không.
- **Có credentials thuộc scheme nhưng dữ liệu lỗi**: ném `AuthenticationException` phù hợp để trả lỗi xác thực.
- **Có credentials có vẻ đúng định dạng**: tạo **token chưa xác thực**, chuyển sang manager/provider.

Nếu converter trả `null` cả khi header đã được gửi nhưng bị sai cú pháp, một filter khác có thể coi request như anonymous và bỏ lỡ ý định xác thực. Điều này làm hành vi xử lý lỗi thiếu nhất quán, nhất là khi có nhiều scheme.

### 8.2. Không tin dữ liệu client tự gắn

Tránh gán authorities từ `X-Role`, `isAdmin=true`, username trong request hoặc JWT chưa được xác minh. Chỉ server hoặc issuer đáng tin sau bước kiểm tra mới là nguồn của principal và quyền. Khi hỗ trợ multi-tenant, phải ràng buộc key/token với tenant và quyền thực của danh tính, không chỉ parse một tenant ID rồi cấp quyền.

### 8.3. Xử lý input chắc chắn

Giới hạn độ dài header/body, kiểm tra giá trị lặp lại, blank, encoding và cú pháp. Nếu có JSON credentials, dùng parser chuẩn, tránh tự tách chuỗi và tránh cho request body bị đọc hai lần bởi các component không biết nhau. Đừng gọi `getParameter(...)` rồi giả định nó đọc JSON; `getParameter` chủ yếu dành cho query/form params.

### 8.4. Không rò rỉ secrets

Sử dụng TLS; không đưa password/API key/token vào query string; không log `Authorization`, `Cookie` hoặc custom credential header; không trả nguyên văn `AuthenticationException.getMessage()` ra client. Khi lưu `Authentication` vào context/session, hạn chế giữ `credentials`. Nếu token có cache hoặc nằm trong log, việc thực hiện `toString()` cũng cần được đánh giá.

### 8.5. Đúng thứ tự filter, đúng vòng đời SecurityContext

Authentication filter phải chạy trước quyết định authorization cho request; Spring Security nạp và dọn `SecurityContextHolder` theo vòng đời request. Với custom filter, **tạo `SecurityContext` mới** để đặt kết quả tin cậy; không đơn giản tự đặt một token chưa xác thực vào context. Nếu ứng dụng dùng login dựa trên session, phải cấu hình lưu `SecurityContext` bằng `SecurityContextRepository` thích hợp; `setContext(...)` đơn lẻ không bảo đảm lưu cho request tiếp theo.

`AuthenticationFilter`, các built-in filter và một `OncePerRequestFilter` tùy chỉnh có **chính sách xử lý thành công/thất bại khác nhau**. Chọn hook phù hợp với hành vi mong muốn, đặc biệt khi cần redirect, JSON response hay tiếp tục controller.

### 8.6. Tách request matcher và giao thức phản hồi

`/api/login`, `/api/**`, browser page hoặc webhook có thể cần converter/filter khác nhau. Chỉ bật converter trên phạm vi có chủ đích. Với HTTP Basic/Bearer, `401` thường cần header `WWW-Authenticate` theo giao thức; không dùng challenge `Basic` cho API key riêng nếu server không hỗ trợ Basic. `403` thường dùng cho người dùng đã xác thực nhưng thiếu quyền. Các trường hợp bị CSRF filter chặn là đường bảo vệ khác và có thể trả `403` trước khi converter tùy biến chạy.

## 9. Những lỗi hay gặp khi mở rộng

1. **Converter trả token `authenticated=true`:** lỗi ranh giới tin cậy. Đổi sang token chưa xác thực và để provider trả trusted token.
2. **Converter tạo `ROLE_ADMIN` từ header/query:** lỗi leo thang đặc quyền. Chỉ lấy quyền từ dữ liệu đã được kiểm tra phía server.
3. **`ProviderNotFoundException` khi gọi manager:** loại token converter trả về không có `AuthenticationProvider.supports(...)` phù hợp; kiểm tra class token, manager được gắn với filter và provider list.
4. **Converter trả `null` cho credentials sai cú pháp:** sai semantic, có thể khiến lỗi bị diễn giải là anonymous. Phân biệt “không gửi” và “gửi sai”.
5. **Key hợp lệ nhưng endpoint vẫn trả `401`:** xem filter có nằm trong đúng `SecurityFilterChain`, `shouldNotFilter` và request matcher có khớp, provider có trả authenticated token, context có được đặt trước authorization hay không.
6. **Key hợp lệ nhưng endpoint trả `403`:** Authentication thành công nhưng role/scope thiếu. `hasRole("ADMIN")` đòi authority `ROLE_ADMIN`; converter không có nhiệm vụ sửa quyền.
7. **Custom filter chạy hai lần:** nếu filter vừa là Spring bean được Boot auto-register vào servlet container, vừa được thêm trong `HttpSecurity`, nó có thể được gọi ngoài chain đúng thứ tự. Tránh auto-register hoặc tắt registration ngoài Spring Security.
8. **Tự catch mọi `Exception` thành 401:** như vậy lỗi lập trình, lỗi database hoặc lỗi authorization bị che giấu. Chỉ xử lý `AuthenticationException` tại bước xác thực; để các lỗi khác đến handler phù hợp.
9. **Không thấy authentication còn hiệu lực ở request tiếp theo:** xem chính sách stateless/session và `SecurityContextRepository`. Demo hiện tại cố ý yêu cầu API key mỗi lần.
10. **Dùng class Servlet trong ứng dụng reactive:** WebFlux dùng `ServerWebExchange`, `ServerAuthenticationConverter`, `AuthenticationWebFilter` và reactive security context; đây là một pipeline khác.

Khi debug môi trường phát triển, bật có chọn lọc:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Dùng logs để kiểm tra SecurityFilterChain và thứ tự filter; **không bật ghi log credentials**. Test những nhánh có/không header, key sai, key đúng và thiếu quyền thay vì chỉ test case thành công.

## 10. Tự kiểm tra và bài tập thực hành

1. Vì sao `convert(request)` không nên truy vấn database rồi tự trả `authenticated=true`? Hai giai đoạn tách nhau giúp ích gì cho kiểm thử?
2. Nếu `X-Api-Key` không có trong request, `HeaderApiKeyConverter` trả giá trị gì? Vì sao endpoint `/api/data` vẫn không thể được truy cập?
3. Tại sao `/api/admin` trả `403` khi API key chính xác, dù provider đã xác thực thành công?
4. Nếu API key bị gửi hai lần trong hai header, nhánh nào xử lý lỗi? Dùng `AuthenticationException` có lợi gì?
5. Chuyện gì xảy ra nếu `ApiKeyFilter` bị đặt **sau** `AuthorizationFilter`? Vì sao kết quả có thể sai?
6. Hãy đổi `DemoApiKeyProvider` để kiểm tra nhiều key lưu ngoài code, có ngày hết hạn, principal/role riêng. Giữ converter **không đổi**; đây chính là lợi ích của điểm mở rộng.
7. Thêm một API key có `ROLE_ADMIN` do server cấp và chứng minh `/api/admin` chỉ thành công với key đó. Tuyệt đối không nhận role từ request để quyết định quyền.
8. Thiết kế test cho: header vắng mặt, header rỗng, header trùng, key sai, key đúng, thiếu authority, converter trả `null`, provider không hỗ trợ token.

**Hoàn thành bài học khi bạn có thể chỉ rõ:** dữ liệu HTTP được chuyển thành token ở đâu; ai kiểm tra bằng chứng; ai đưa `Authentication` đã xác thực vào context; ai quyết định 401/403; vì sao converter không phải chỗ “tin” client; và làm thế nào thay đổi kiểu đầu vào mà vẫn giữ provider/authorization nhất quán.

## Tài liệu tham khảo chính thức

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html)
- [Spring Security — AuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html)
- [Spring Security — Servlet filter chain, adding filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
