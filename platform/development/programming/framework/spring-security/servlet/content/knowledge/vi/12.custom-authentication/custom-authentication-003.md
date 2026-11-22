# Đọc JSON đăng nhập bằng AuthenticationConverter

Trong **Spring Security cho ứng dụng Servlet**, nhiều frontend gửi thông tin đăng nhập bằng một HTTP request có body JSON, chẳng hạn `POST /api/login` với `{"username":"alice","password":"..."}`, thay vì biểu mẫu HTML có các field `username` và `password`. Muốn tích hợp kiểu request này mà vẫn tận dụng hệ thống xác thực của Spring Security, ta cần phân biệt hai nhiệm vụ:

- **Đọc request và chuyển thành đối tượng Authentication chưa được xác thực**: việc của `AuthenticationConverter`.
- **Xác minh username/password và quyết định xác thực**: việc của `AuthenticationManager` và `AuthenticationProvider`, không phải converter.

Spring Security cung cấp `AuthenticationFilter` để kết nối `AuthenticationConverter` với `AuthenticationManager`, một `RequestMatcher` xác định request đăng nhập, cùng handler cho kết quả thành công/thất bại. Từ đó, ứng dụng có thể xử lý JSON an toàn mà **không cần tự kiểm tra password trong controller hoặc cấp role theo JSON do client khai báo**.

Bài học xây dựng một luồng JSON login cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC**: giải thích hợp đồng converter, code class Java đầy đủ, lựa chọn session hay stateless, CSRF, giới hạn payload, lỗi dữ liệu, kiểm thử MockMvc và những nguy cơ bảo mật thường gặp. Các đoạn mã Spring cần dependencies phù hợp; chương trình JDK độc lập ở cuối dùng để minh họa riêng logic phân tuyến, không giả làm JSON parser hay password verifier.

## 1. Kiến trúc: từ request JSON đến Authentication

### 1.1. Luồng xử lý được khuyến nghị

~~~text
Client
  |
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"secret"}
  v
Servlet Filter Chain
  |
  v
FilterChainProxy / SecurityFilterChain đã khớp
  |
  v
CsrfFilter (nếu dùng cookie/session: phải có CSRF token hợp lệ)
  |
  v
AuthenticationFilter
  |-- RequestMatcher: đây có phải POST /api/login không?
  |
  |-- AuthenticationConverter.convert(request)
  |       |
  |       +-- parse JSON có giới hạn
  |       +-- kiểm tra cú pháp/trường cần thiết
  |       +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
  |               (CHƯA được tin cậy)
  |
  |-- AuthenticationManager.authenticate(token)
  |       |
  |       +-- DaoAuthenticationProvider
  |               |-- UserDetailsService tải tài khoản
  |               |-- PasswordEncoder.matches(...) xác minh password
  |               +-- trả Authentication đã xác thực
  |
  |-- nếu thành công:
  |       |-- thiết lập SecurityContext
  |       |-- lưu context theo SecurityContextRepository nếu cấu hình
  |       +-- AuthenticationSuccessHandler: HTTP response
  |
  +-- nếu thất bại:
          +-- AuthenticationFailureHandler: HTTP response
~~~

Tất cả các bước diễn ra trong hệ sinh thái **Servlet filters**. Một custom converter không có trách nhiệm tự quản lý SecurityContext, không ghi session, không quyết định redirect và không đảm nhiệm kiểm tra mật khẩu.

### 1.2. Vì sao không dùng converter như một controller?

Ví dụ controller tự xử lý `POST /api/login` rồi gọi repository để so sánh password thường dẫn tới việc tự xây lại logic mà Spring Security đã có: encoder, account status, user cache, provider, authentication events, session fixation, security context, success/failure handler và cơ chế kiểm tra quyền. Nếu bắt buộc dùng controller, vẫn cần tổ chức các bước bằng AuthenticationManager và xử lý đầy đủ vòng đời security; còn với JSON login trong Servlet filter, `AuthenticationFilter + AuthenticationConverter` thường là cách gọn và dễ mở rộng hơn.

### 1.3. So sánh các thành phần

| Thành phần | Đầu vào | Đầu ra/trách nhiệm | Không làm |
| --- | --- | --- | --- |
| `RequestMatcher` | HTTP request | Có/không khớp login endpoint | Parse JSON, xác thực mật khẩu |
| `AuthenticationConverter` | `HttpServletRequest` | Một `Authentication` **chưa tin cậy**, hoặc `null` nếu không áp dụng | Không cấp quyền đã xác thực |
| `AuthenticationFilter` | Matcher, converter và manager | Điều phối xác thực trong filter chain, gọi handlers | Không thay provider tự xác minh password |
| `AuthenticationManager` | Authentication request | Authentication kết quả hoặc lỗi | Không đọc body JSON |
| `DaoAuthenticationProvider` | Username/password token | Kiểm tra UserDetails, PasswordEncoder và account flags | Không định nghĩa HTTP JSON schema |
| `AuthenticationSuccessHandler` | Authentication thành công, request, response | Chọn HTTP status/JSON/redirect | Không cấp authorities theo ý client |
| `AuthenticationFailureHandler` | AuthenticationException, request, response | Trả lỗi HTTP nhất quán, không lộ secrets | Không cho qua khi password sai |
| `SecurityContextRepository` | SecurityContext/request/response | Lưu/nạp context theo chiến lược stateful/request-scoped | Không tự quyết định client có được login |

## 2. Hợp đồng của AuthenticationConverter

Interface trong Spring Security Servlet:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

// Hình dạng API, không phải file Java độc lập:
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request)
            throws AuthenticationException;
}
~~~

### Trả về đối tượng gì?

Với username/password, kết quả phù hợp trước bước xác thực là:

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);
~~~

Đây là factory method của Spring Security 6.x; import `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`. Token lúc này chứa **credentials chưa được xác minh**. Không tự đặt `isAuthenticated=true`, không gán `ROLE_ADMIN` từ field JSON của client và không dùng factory tạo token trusted chỉ vì username tồn tại.

Sau đó filter chuyển token tới `AuthenticationManager.authenticate(...)`. Nếu thành công, provider trả về một Authentication với principal, authorities và trạng thái xác thực hợp lệ. Converter **không phải bằng chứng danh tính**.

### Ý nghĩa của null và exception

| Kết quả `convert(...)` | Khi phù hợp | Hành vi của AuthenticationFilter |
| --- | --- | --- |
| Trả một Authentication chưa xác thực | Request thuộc endpoint và payload dùng được | Gửi tới AuthenticationManager |
| Trả `null` | Converter không thấy credential áp dụng; với request không thuộc login scope | Không thực hiện authentication attempt ở bước đó |
| Ném `AuthenticationException` | Request login có payload sai/thiếu hoặc converter không thể hoàn tất theo hợp đồng | Đi vào luồng failure handling nếu exception xảy ra trong phần xử lý của filter |

Một lời khuyên quan trọng: **đừng trả `null` cho mọi JSON không hợp lệ**. Nếu request đã được xác định là `POST /api/login`, dữ liệu thiếu username/password là lỗi đầu vào cần phản hồi minh bạch theo chính sách API. Trả null có thể làm request đi tiếp tới filter khác và cho kết quả khó hiểu, không nhất thiết kích hoạt failure handler.

### Converter có cần tự kiểm tra URL không?

`AuthenticationFilter` có thể nhận `RequestMatcher` để chỉ gọi converter ở endpoint phù hợp. Vì vậy, URL/path/method nên được xác định rõ tại cấu hình filter; kiểm tra dự phòng trong converter có thể hữu ích khi tái sử dụng component, nhưng **không thay matcher của filter**. Nếu filter dùng matcher quá rộng, request ngoài login scope có thể bị đọc body hoặc chặn bất ngờ.

## 3. Thiết kế API login JSON trước khi viết code

Hợp đồng tối thiểu của ví dụ:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json
Cookie: JSESSIONID=...               (nếu session đã tồn tại)
X-CSRF-TOKEN: <csrf-token-hợp-lệ>   (khi CSRF được bật)

{"username":"alice","password":"demo-only-password"}
~~~

Dòng CSRF token trong ví dụ là **placeholder giải thích giao thức**, không phải token có thể dùng thực tế. Với Spring Security 6, việc gửi token qua request attribute/header và cách xử lý token (có thể gồm XOR masking) cần phù hợp cấu hình `CsrfTokenRequestHandler` của ứng dụng; không hardcode token. Một frontend dùng cookie-based login phải có cơ chế lấy/truyền token tin cậy.

Cơ chế demo trả:

| Trường hợp | HTTP | Nội dung phản hồi ví dụ |
| --- | --- | --- |
| Username/password đúng | 200 | `{"status":"ok","username":"alice"}` |
| Username/password sai | 401 | `{"error":"invalid_credentials"}` |
| JSON sai cú pháp hoặc thiếu trường | 400 | `{"error":"invalid_request"}` |
| Content-Type không phải JSON | 415 | `{"error":"unsupported_media_type"}` |
| Body vượt giới hạn | 413 | `{"error":"payload_too_large"}` |
| Lỗi nội bộ của luồng authentication | 503 trong demo | `{"error":"login_unavailable"}` |
| Thiếu CSRF token khi session/cookie login | 403 | Có thể do CsrfFilter trả trước converter |

Đây là **quy ước API do ứng dụng định nghĩa**, không phải status mặc định cứng của `AuthenticationConverter`. Ứng dụng có thể chọn phản hồi khác, miễn nhất quán và không tạo khả năng dò tài khoản. Trong mọi trường hợp, không phản chiếu password, password hash hoặc stack trace về frontend.

### Vì sao cần giới hạn body?

Đọc toàn bộ body JSON không giới hạn làm tăng nguy cơ tốn bộ nhớ/CPU, nhất là endpoint login dễ bị tấn công. Ví dụ dùng giới hạn **8 KiB** (8 × 1024 byte) cho một payload username/password; ứng dụng thật chọn con số theo yêu cầu và các tầng proxy/gateway. Đọc tối đa `limit + 1` byte cho phép phát hiện payload quá lớn **kể cả khi Content-Length không được gửi** hoặc sử dụng chunked encoding. Proxy/server vẫn nên có request limits riêng.

Các yêu cầu đầu vào khác:

- Chỉ chấp nhận `application/json` và tham số charset tương thích nếu client gửi.
- Username phải là chuỗi không rỗng, có giới hạn độ dài rõ.
- Password phải là chuỗi, không được tự `trim()` vì khoảng trắng có thể là một phần của password.
- Chỉ nhận các field API cho phép; không lấy role, authorities, enabled hay authenticated từ client để tạo token.
- Xác định cách xử lý JSON chứa field lạ, duplicate keys, trailing tokens và kiểu sai.
- Không giữ password trong request attributes, cache chung hoặc log.
- Đọc body trong converter **một lần**; Servlet input stream không mặc định có khả năng đọc lại.

## 4. Ví dụ converter đầy đủ với Jackson

Spring Boot Web thường tự cung cấp bean `ObjectMapper` của Jackson. Ví dụ sau dùng Jackson để deserialize record Java 17, kiểm tra Content-Type, giới hạn body, yêu cầu field và tạo token **chưa xác thực**.

Tạo file `src/main/java/com/example/jsonlogin/JsonLoginAuthenticationConverter.java`:

~~~java
package com.example.jsonlogin;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import org.springframework.http.InvalidMediaTypeException;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class JsonLoginAuthenticationConverter
        implements AuthenticationConverter {

    private static final int MAX_JSON_BYTES = 8 * 1024;
    private final ObjectMapper mapper;

    public JsonLoginAuthenticationConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    // Record mô tả JSON đầu vào, không có field roles/authenticated.
    public record LoginPayload(String username, String password) {}

    // Lỗi input để failure handler chọn HTTP status phù hợp.
    public static final class LoginInputException
            extends AuthenticationException {

        private final int status;

        public LoginInputException(int status, String reason) {
            super(reason);
            this.status = status;
        }

        public LoginInputException(int status, String reason, Throwable cause) {
            super(reason, cause);
            this.status = status;
        }

        public int status() {
            return status;
        }
    }

    @Override
    public Authentication convert(HttpServletRequest request) {
        // Matcher của AuthenticationFilter mới là ranh giới chính.
        if (!"POST".equals(request.getMethod())) {
            return null;
        }

        String contentType = request.getContentType();
        try {
            if (contentType == null ||
                    !MediaType.APPLICATION_JSON.isCompatibleWith(
                            MediaType.parseMediaType(contentType))) {
                throw new LoginInputException(
                    415, "Unsupported login content type");
            }
        } catch (InvalidMediaTypeException ex) {
            throw new LoginInputException(
                415, "Unsupported login content type", ex);
        }

        byte[] body;
        try {
            // Không đọc vô hạn ngay cả với request thiếu Content-Length.
            body = request.getInputStream().readNBytes(MAX_JSON_BYTES + 1);
        } catch (IOException ex) {
            // Lỗi I/O thuộc vận hành, không giả làm password sai.
            throw new AuthenticationServiceException(
                "Could not read login request", ex);
        }

        if (body.length > MAX_JSON_BYTES) {
            throw new LoginInputException(413, "Login body too large");
        }
        if (body.length == 0) {
            throw new LoginInputException(400, "Login body missing");
        }

        LoginPayload credentials;
        try {
            credentials = mapper.readerFor(LoginPayload.class)
                .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .readValue(body);
        } catch (JsonProcessingException ex) {
            throw new LoginInputException(400, "Invalid login JSON", ex);
        } catch (IOException ex) {
            throw new AuthenticationServiceException(
                "Could not parse login request", ex);
        }

        if (credentials == null ||
                credentials.username() == null ||
                credentials.username().isBlank() ||
                credentials.username().length() > 128 ||
                credentials.password() == null ||
                credentials.password().isEmpty() ||
                credentials.password().length() > 1024) {
            throw new LoginInputException(
                400, "Invalid login fields");
        }

        // Không biến username/password chưa kiểm chứng thành trusted token.
        return UsernamePasswordAuthenticationToken.unauthenticated(
            credentials.username(), credentials.password());
    }
}
~~~

### Đọc chi tiết các quyết định trong code

1. `AuthenticationFilter` sẽ được cấu hình matcher POST /api/login. Check `POST` trong converter chỉ là phòng vệ bổ sung. Với đường dẫn khác, matcher giúp converter không phải đọc body.
2. `MediaType.APPLICATION_JSON.isCompatibleWith(...)` kiểm tra Content-Type mà không yêu cầu so sánh chuỗi cứng `"application/json"`, nên tham số như `charset=UTF-8` không tự khiến request bị từ chối.
3. `readNBytes(MAX_JSON_BYTES + 1)` giới hạn dữ liệu được đọc và giúp phát hiện body vượt hạn mức. Nó không thay thế giới hạn request ở container, reverse proxy và rate limiting.
4. `ObjectReader` bật `FAIL_ON_UNKNOWN_PROPERTIES` và `FAIL_ON_TRAILING_TOKENS` để từ chối các field dư hoặc token JSON theo sau object. Việc từ chối **duplicate JSON keys** cần cấu hình parser strict duplicate detection riêng nếu API yêu cầu, không tự coi hai tùy chọn này là đủ.
5. Username và password lấy đúng hai field. Client không được quyết định `isAuthenticated` hay `GrantedAuthority`.
6. Không `trim` password; khoảng trắng đầu/cuối có thể là dữ liệu hợp lệ.
7. `LoginInputException` là `AuthenticationException` để filter chuyển tới failure handler; status lưu trong exception chỉ là chính sách demo. Lỗi I/O được biểu diễn bằng `AuthenticationServiceException` riêng, tránh ngụy trang lỗi hệ thống thành credential sai.
8. Dùng `UsernamePasswordAuthenticationToken.unauthenticated(...)` để provider xác minh, không tự đặt context hay trả authenticated token trong converter.

**Chú ý:** record `LoginPayload` tồn tại ngắn hạn nhưng chứa mật khẩu rõ trong bộ nhớ lúc xác thực. Điều này là tự nhiên khi xác thực password; cần giảm vòng đời, không log/serialize object và không đưa nó vào queue/cache. Java String không thể chủ động xóa nội dung bộ nhớ tức thì; không tuyên bố việc `eraseCredentials` bảo đảm xóa tất cả bản sao String đã từng tồn tại.

### Nếu muốn dùng DTO khác

Một ứng dụng có thể đặt tên field `email` thay vì `username`, hoặc chấp nhận identifier phức tạp; khi đó thay record và logic mapping. Nhưng **converter không được tự cấp quyền** dựa trên field `role` do client gửi. Nếu authentication type khác username/password, hãy tạo token yêu cầu tương ứng và dùng provider tương thích.

## 5. Cấu hình Spring Boot, AuthenticationFilter và provider

Ví dụ chạy dạng **session-based login bằng JSON**: POST /api/login trả JSON và lưu SecurityContext trong session; GET /api/me sau đó dùng cookie session đã được cấp. **CSRF vẫn bật** vì cookie tự được browser gửi và có nguy cơ cross-site request. Để dễ tập trung, tài khoản dùng `InMemoryUserDetailsManager`; production nên thay bằng kho tài khoản thực và cơ chế xác thực/kiểm soát truy cập phù hợp.

### 5.1. Dependencies Maven

Trong một project Spring Boot 3.x có parent/BOM tương thích và plugin run/test, thêm các dependency sau. Version các Spring artifact nên để Boot BOM quản lý.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-web` thường đã có Jackson ở những cấu hình Spring Boot 3.x thông dụng. Nếu dự án chủ động loại Jackson, phải bổ sung dependency tương ứng hoặc đổi JSON library và cấu hình bean parser. Với những phiên bản Boot tương lai, đối chiếu classpath thực tế.

### 5.2. Application entry point

Tạo `src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig hoàn chỉnh

Tạo `src/main/java/com/example/jsonlogin/SecurityConfig.java`:

~~~java
package com.example.jsonlogin;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

import jakarta.servlet.http.HttpServletResponse;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // CHỈ phục vụ học tập. Không hardcode password production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Chọn persistence qua HTTP session cho ví dụ này.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            ObjectMapper mapper,
            SecurityContextRepository repository) throws Exception {

        JsonLoginAuthenticationConverter converter =
                new JsonLoginAuthenticationConverter(mapper);
        AuthenticationFilter jsonFilter =
                new AuthenticationFilter(manager, converter);

        jsonFilter.setRequestMatcher(
            new AntPathRequestMatcher("/api/login", "POST"));

        // AuthenticationFilter custom cần repository phù hợp để login
        // được lưu qua các HTTP request, không chỉ vào thread hiện tại.
        jsonFilter.setSecurityContextRepository(repository);

        // Đổi session ID khi một session đã tồn tại trước login,
        // giảm nguy cơ session fixation trong mô hình dùng cookie.
        jsonFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        jsonFilter.setSuccessHandler((request, response, authentication) -> {
            response.setStatus(HttpServletResponse.SC_OK);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            mapper.writeValue(response.getWriter(), Map.of(
                "status", "ok",
                "username", authentication.getName()));
        });

        jsonFilter.setFailureHandler((request, response, exception) -> {
            int status;
            String error;

            if (exception instanceof
                    JsonLoginAuthenticationConverter.LoginInputException input) {
                status = input.status();
                error = switch (status) {
                    case 400 -> "invalid_request";
                    case 413 -> "payload_too_large";
                    case 415 -> "unsupported_media_type";
                    default -> "invalid_request";
                };
            } else if (exception instanceof AuthenticationServiceException) {
                status = HttpServletResponse.SC_SERVICE_UNAVAILABLE;
                error = "login_unavailable";
            } else {
                status = HttpServletResponse.SC_UNAUTHORIZED;
                error = "invalid_credentials";
            }

            response.setStatus(status);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            mapper.writeValue(response.getWriter(), Map.of("error", error));
        });

        http.securityContext(context -> context
                .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .addFilterAt(jsonFilter, UsernamePasswordAuthenticationFilter.class);

        // Không gọi csrf.disable(): cookie-based session cần bảo vệ CSRF.
        // Không bật formLogin(): ứng dụng demo chỉ dùng custom JSON login.
        return http.build();
    }
}
~~~

Cấu hình trên minh họa các API Spring Security 6.x; constructor/setter của `DaoAuthenticationProvider` có thể được đánh dấu deprecated ở những bản 6.x mới, và các bản khác có thể cung cấp constructor nhận `UserDetailsService`. Chọn cú pháp khởi tạo phù hợp version đã khóa trong dự án; **hợp đồng chính** vẫn là provider dùng encoder, manager kiểm tra credentials và filter dùng converter.

Một số điểm quan trọng:

1. `new AuthenticationFilter(manager, converter)` gắn converter với AuthenticationManager **thật**; không có đoạn nào tự so sánh password trong converter.
2. `setRequestMatcher(...)` giới hạn **chính xác POST /api/login**. Request GET /api/login không được coi là nỗ lực xác thực JSON.
3. `addFilterAt(jsonFilter, UsernamePasswordAuthenticationFilter.class)` đặt filter custom ở vị trí quy ước của username/password filter. Ví dụ này không bật thêm `formLogin()` để tránh hai filter xử lý cùng cơ chế. Nếu dự án có form login hoặc các chain khác, phải thiết kế rõ matcher và thứ tự, không thay thế các filter khác một cách vô ý.
4. `SecurityContextRepository` được cấu hình **cả cho AuthenticationFilter và HttpSecurity**, để luồng lưu/ngữ cảnh giữa request nhất quán. Chỉ gọi `SecurityContextHolder.setContext(...)` trong code custom không đủ để login session sống qua request tiếp theo.
5. Chọn `ChangeSessionIdAuthenticationStrategy` cho ví dụ dùng session; ứng dụng thật cần đối chiếu session fixation protection, concurrent session controls và chiến lược session authentication của hệ thống.
6. Success handler chỉ phản hồi JSON và username được xác thực; **không trả password, hash, cookie/session ID hay toàn bộ principal**.
7. Failure handler phân biệt **lỗi request** (400/413/415), **sai credentials** (401) và một số lỗi dịch vụ (503), nhưng không tiết lộ user có tồn tại hay không.
8. `CsrfFilter` vẫn bảo vệ POST login. Nếu frontend không gửi CSRF token hợp lệ, request có thể bị từ chối trước cả khi converter chạy.
9. `AuthenticationFilter` trong ví dụ là đường login riêng; API không tự trở thành stateless chỉ vì sử dụng JSON thay HTML.

**Giới hạn đáng chú ý:** Với ứng dụng dùng remember-me, OAuth2 login, nhiều security chain hoặc session concurrency, một custom AuthenticationFilter cần tích hợp đúng các chiến lược/handler bổ sung. Không suy luận rằng thay `UsernamePasswordAuthenticationFilter` bằng filter khác tự động giữ nguyên mọi tính năng form login truyền thống.

### 5.4. Endpoint kiểm tra session sau login

Tạo `src/main/java/com/example/jsonlogin/CurrentUserController.java`:

~~~java
package com.example.jsonlogin;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

Endpoint được bảo vệ bằng `authenticated()` nên trong luồng request đúng cấu hình, `principal` là principal hợp lệ. Response dự kiến khi Alice đã login:

~~~json
{"username":"alice"}
~~~

Đây là nội dung JSON, không cam kết vị trí whitespace/serialization cụ thể nếu mapper bị tùy chỉnh. Khi chưa đăng nhập, entry point của demo trả 401.

## 6. Thử request và hiểu vòng đời session/CSRF

Sau khi chạy project với Maven wrapper phù hợp:

~~~bash
./mvnw spring-boot:run
~~~

Client gửi body:

~~~json
{
  "username": "alice",
  "password": "demo-only-password"
}
~~~

**Đừng thử một POST curl thuần rồi kết luận converter hỏng vì thấy 403.** Mô hình demo dùng session cookie và **giữ CSRF bật**. Frontend cần có cơ chế lấy CSRF token hợp lệ, giữ cùng session/cookie và gửi token theo quy ước của CSRF repository/handler đã cấu hình. Mã ví dụ không tạo endpoint phát CSRF token cho browser vì trọng tâm ở converter; có thể dùng MockMvc với `csrf()` ở phần 8 để kiểm tra xác thực độc lập với UI.

Nếu bạn có CSRF token hợp lệ do ứng dụng cung cấp và cookie đúng session, request dạng minh họa có thể là:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: REPLACE_WITH_VALID_TOKEN' \
  -d '{"username":"alice","password":"demo-only-password"}' \
  http://localhost:8080/api/login
~~~

`REPLACE_WITH_VALID_TOKEN` là placeholder. Token không thể được tự tạo bằng cách gõ chuỗi tùy ý. Với Spring Security 6 và cơ chế XOR-CSRF mặc định, cách frontend nhận/gửi token phải theo cấu hình handler thực tế. Khi request login thành công, client giữ session cookie; request GET /api/me với cookie đó thường trả username Alice.

Nếu muốn xây frontend chạy browser thực, cần quyết định thêm: SameSite, Secure, HttpOnly cookies; CSRF token exposure; CORS allowlist nếu khác origin; cache policy cho response đăng nhập; thời hạn session; logout; session fixation; rate limiting/MFA. Không chọn `csrf().disable()` chỉ để demo POST chạy dễ hơn khi vẫn xác thực bằng cookie.

### Phân biệt JSON login và JWT login

| Mô hình | Sau POST /api/login | Request sau lấy danh tính từ đâu? |
| --- | --- | --- |
| Ví dụ session trong bài | Handler trả JSON, context được lưu qua HttpSession repository | Session cookie hợp lệ và SecurityContextRepository |
| Stateless Bearer/JWT API | Cơ chế login có thể trả token được phát hành hợp lệ qua một thành phần chuyên trách | Client gửi Bearer token ở từng request; resource server xác minh token |
| JSON login không save context/token | Response 200 không tự tạo trạng thái đăng nhập bền vững | Request sau có thể lại anonymous |

**`AuthenticationConverter` không tự cấp JWT, không ký token và không biến endpoint thành stateless.** Nếu hệ thống muốn OAuth2/OIDC hoặc bearer tokens, cần chọn kiến trúc phù hợp thay vì tự tạo chuỗi token không có xác minh/thu hồi.

## 7. Lỗi JSON đi vào filter như thế nào?

### 7.1. JSON sai cú pháp

~~~http
POST /api/login
Content-Type: application/json

{"username":"alice","password":
~~~

Jackson ném lỗi parse, converter chuyển sang `LoginInputException(400, ...)`. Nếu qua CSRF filter hợp lệ, AuthenticationFilter gọi failure handler và trả body công khai như `{"error":"invalid_request"}`. Không log toàn bộ body đã lỗi vì nó có thể chứa password.

### 7.2. JSON hợp lệ nhưng password sai

~~~json
{"username":"alice","password":"not-the-password"}
~~~

Converter vẫn tạo token **chưa xác thực**. `DaoAuthenticationProvider` đối chiếu password và ném `AuthenticationException` phù hợp; failure handler trả 401 chung. Đây là **lỗi authentication**, khác với lỗi cấu trúc JSON.

### 7.3. Client gửi role hoặc authenticated

~~~json
{
  "username": "alice",
  "password": "demo-only-password",
  "authorities": ["ROLE_ADMIN"],
  "authenticated": true
}
~~~

Vì converter demo bật `FAIL_ON_UNKNOWN_PROPERTIES`, body này bị từ chối 400. Ngay cả nếu một API lựa chọn bỏ qua field lạ, **không bao giờ chuyển các field quyền đó thành token đã xác thực**; authorities phải đến từ provider/nguồn đã tin cậy.

### 7.4. Content-Type không khớp

Nếu gửi `text/plain` hay `application/x-www-form-urlencoded` đến endpoint chỉ nhận JSON, converter báo 415 qua exception được cấu hình. Spring MVC controller có thể dùng `@RequestBody` và `consumes=...`, nhưng **AuthenticationFilter chạy ở filter chain trước controller**, nên việc kiểm tra media type trong converter không phụ thuộc vào validation của `@RequestBody`.

### 7.5. Body vượt kích thước

Với limit 8192 bytes, payload có hơn 8192 bytes sẽ bị converter từ chối 413 trước khi deserialization. Giá trị giới hạn được đo trên **bytes**, không phải số ký tự Java hay số code point Unicode.

### 7.6. Exception không phải AuthenticationException

`AuthenticationConverter.convert(...)` chỉ khai báo `AuthenticationException` unchecked trong API. Nếu code để `IOException` hay `RuntimeException` không được chuyển đổi hợp lý, hệ thống có thể không đi qua failure handler dự kiến và có response khác hoặc lộ chi tiết nếu error handling bị cấu hình kém. Ví dụ bắt lỗi Jackson/IO và chuyển sang exception phù hợp, nhưng **không che mọi lỗi vận hành thành 401 sai password**.

### 7.7. Body đã bị đọc bởi filter khác

Servlet input stream không mặc định cho phép nhiều thành phần cùng đọc hết body. Nếu logging filter đọc JSON trước AuthenticationFilter rồi không cung cấp wrapper có khả năng phát lại thực sự, converter có thể thấy input rỗng. Chỉ dùng `ContentCachingRequestWrapper` không tự động đảm bảo các downstream component đọc lại từ cache; cần hiểu hợp đồng wrapper cụ thể, hạn chế ghi log body nhạy cảm và test thứ tự filter.

## 8. Kiểm thử bằng MockMvc: phải qua filter thật

Một test `@WithMockUser` tạo Authentication sẵn **không chứng minh converter đã đọc JSON, provider kiểm tra password hay context đã lưu**. Test đúng trọng tâm cần gửi `POST /api/login` với JSON và CSRF token hợp lệ, rồi quan sát response, session và `GET /api/me`.

Tạo `src/test/java/com/example/jsonlogin/JsonLoginIntegrationTest.java`:

~~~java
package com.example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void correctJsonLoginPersistsAuthenticationInSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"demo-only-password"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.username").value("alice"))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void wrongPasswordIs401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"wrong"}
                    """))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void invalidJsonIs400() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not valid json"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_request"));
    }

    @Test
    void unknownFieldCannotGrantRole() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username":"alice",
                      "password":"demo-only-password",
                      "authorities":["ROLE_ADMIN"]
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void tooLargeJsonIs413() throws Exception {
        String body = "{\"username\":\"alice\",\"password\":\""
                + "x".repeat(8200) + "\"}";

        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isPayloadTooLarge());
    }

    @Test
    void missingCsrfIsRejectedBeforeConverterSuccess()
            throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"demo-only-password"}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedGetMeIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Lưu ý về status matcher:** `status().isPayloadTooLarge()` có trong các phiên bản Spring Test cung cấp mã 413. Nếu bản Spring Test cụ thể không có matcher này, kiểm tra status code 413 bằng `status().is(413)`. Để tránh phụ thuộc, có thể dùng trực tiếp `status().is(413)` trong test. Các assert chỉ đúng nếu project dùng đúng chain, converter, provider, repo và failure handler ở ví dụ.

### Kỳ vọng test thể hiện điều gì?

| Test | Điều chứng minh |
| --- | --- |
| JSON đúng + session | Converter tạo token phù hợp; provider xác thực; AuthenticationFilter lưu context; GET sau đọc được principal |
| Password sai | Converter đọc JSON được, **provider** bác bỏ credentials |
| JSON sai | Converter trả lỗi đầu vào 400 qua failure handler |
| Field authorities từ client | Schema request không cho client tự thêm quyền |
| Body quá lớn | Giới hạn byte được kiểm tra trước deserialization |
| POST thiếu CSRF | CsrfFilter bảo vệ cookie-based login |
| GET /api/me không đăng nhập | Authorization từ chối, entry point trả 401 |

Để kiểm tra thứ tự filter và các lỗi khó hơn, bổ sung test cho `Content-Type: text/plain`, request không có password, username quá dài, session cookie sai, session fixation và nhiều request nối tiếp. Với converter có mock `AuthenticationManager`, có thể assert token đầu vào có `isAuthenticated=false` và không mang authorities trusted.

### Kiểm tra có thật sự chọn đúng SecurityFilterChain không

Trong ứng dụng nhiều chain, `securityMatcher("/api/**")` và `@Order` có thể khiến request login đi vào một chain khác. Khi test trả 404/403 dù JSON đúng, hãy xác minh filter được đăng ký vào chain khớp `POST /api/login`, không bị một filter/entrypoint khác xử lý trước. Đừng chỉnh `permitAll()` bừa bãi để che việc matcher sai.

## 9. Java 17 độc lập: mô phỏng quyết định parse hoặc bỏ qua

Chương trình sau chạy **chỉ bằng JDK 17**, minh họa phân biệt ba nhánh: bỏ qua request không khớp login, từ chối media type/body size sai, hoặc chuyển một request hợp lệ sang bước xác thực. Nó **không parse JSON, không kiểm tra password và không thay thế Spring Security**; những chức năng ấy đã được thực hiện trong code framework ở trên.

Lưu file `JsonLoginRoutingDemo.java`:

~~~java
public class JsonLoginRoutingDemo {
    private static final int MAX_BYTES = 8 * 1024;

    static String route(String method, String path,
                        String contentType, int byteCount) {
        if (!"POST".equals(method) || !"/api/login".equals(path)) {
            return "SKIP";
        }
        if (contentType == null ||
                !contentType.startsWith("application/json")) {
            return "REJECT 415";
        }
        if (byteCount > MAX_BYTES) {
            return "REJECT 413";
        }
        if (byteCount == 0) {
            return "REJECT 400";
        }
        return "CONVERT -> AUTHENTICATE";
    }

    public static void main(String[] args) {
        System.out.println(route("GET", "/api/login",
                "application/json", 80));
        System.out.println(route("POST", "/api/login",
                "text/plain", 80));
        System.out.println(route("POST", "/api/login",
                "application/json", 9000));
        System.out.println(route("POST", "/api/login",
                "application/json", 0));
        System.out.println(route("POST", "/api/login",
                "application/json", 80));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac JsonLoginRoutingDemo.java
java JsonLoginRoutingDemo
~~~

Stdout chính xác:

~~~text
SKIP
REJECT 415
REJECT 413
REJECT 400
CONVERT -> AUTHENTICATE
~~~

Hàm `route` dùng `startsWith("application/json")` **chỉ để mô phỏng đơn giản**, không nên sao chép vào converter production: một Content-Type không hợp lệ nhưng có tiền tố này vẫn có thể được chấp nhận. Trong Spring code thật, dùng `MediaType.parseMediaType(...)` và kiểm tra compatibility.

## 10. Những vấn đề bảo mật liên quan đến JSON login

### 10.1. CSRF trong cookie-based authentication

JSON không tự bảo vệ khỏi CSRF. Nếu trình duyệt tự gửi cookie xác thực và API có side effects, phải có chính sách CSRF phù hợp. Browser cross-origin restrictions, CORS và SameSite cookies có ích nhưng **không thay thế việc đánh giá CSRF**. Với login cũng có rủi ro login-CSRF, nơi attacker ép browser nạn nhân đăng nhập vào tài khoản do attacker kiểm soát. Vì vậy ví dụ giữ `CsrfFilter` và test thiếu CSRF trả 403.

Không cấu hình `csrf().disable()` toàn cục chỉ vì frontend gửi `application/json`. Nếu xây API stateless sử dụng Bearer token trong header, CSRF có thể được đánh giá khác; phải gắn quyết định với **cơ chế credential thực tế**, không với định dạng body.

### 10.2. Không tự tạo authenticated token trong converter

**Sai:**

~~~java
// KHÔNG dùng: client chưa được xác thực nhưng lại tạo trusted token.
return UsernamePasswordAuthenticationToken.authenticated(
    username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

`authenticated(...)` yêu cầu phía gọi đã có cơ sở tin cậy để xác thực và cấp authorities. Trong converter đọc input từ Internet, dữ liệu còn chưa được provider kiểm tra. Dùng `unauthenticated(...)` để có chuỗi kiểm tra mật khẩu/khóa tài khoản/encoder đúng.

### 10.3. Không so sánh password trực tiếp hoặc lưu plaintext

AuthenticationProvider phải dùng `PasswordEncoder.matches(...)` với hash an toàn từ kho user, không dùng `raw.equals(storedHash)`, không tự hash bằng `MessageDigest.getInstance("SHA-256")` cho password mà không có KDF/salt/cost phù hợp. `BCryptPasswordEncoder` trong demo chỉ thể hiện một lựa chọn; sản phẩm thật phải chọn cost và migration theo chính sách bảo mật.

### 10.4. Không đưa credentials vào log

Những cách log sau đều rủi ro:

- Log nguyên body login JSON.
- Log Authentication request token có credentials.
- Log error message kèm password.
- Ghi payload login vào tracing/APM, request replay, access log hoặc crash report không được kiểm soát.

Chỉ log metadata cần thiết và đã được hạn chế, ví dụ request ID, mã lỗi tổng quát, thời gian xử lý; không dùng username/password làm khóa duy nhất để correlation trên môi trường không được bảo vệ.

### 10.5. Rate limiting, MFA và brute force

Converter chỉ giới hạn schema/size, **không giải quyết credential stuffing**. Endpoint login production cần rate limiting, theo dõi abuse, account lockout hợp lý, MFA/passkeys khi phù hợp, phát hiện bất thường và kiểm soát dò username. Cố gắng giữ phản hồi sai username và sai password giống nhau; không trả thông tin cho phép attacker biết tài khoản nào tồn tại.

### 10.6. Session fixation và cookie policy

Với cookie-based session, sau xác thực cần chính sách session fixation phù hợp. Ví dụ đặt `ChangeSessionIdAuthenticationStrategy` cho filter custom để xử lý session có từ trước. Cũng cần chính sách timeout, logout, cookie `Secure`/`HttpOnly`/`SameSite`, HTTPS và bảo vệ session store. Nếu ứng dụng đã có session management strategy phức tạp, dùng **chính strategy được hệ thống cấu hình**, tránh tạo một bản riêng làm mất concurrency/session registry behavior.

### 10.7. Không tin trường JSON chứa tenant hoặc role

Nếu login cần tenant/organization, tenant mà client chọn là **đầu vào yêu cầu**, không phải bằng chứng đã có quyền vào tenant đó. Provider/identity service phải xác minh user thuộc tenant được chọn; không tự thêm `ROLE_ADMIN` từ payload. Với multi-tenant, kho user và SecurityContext phải giữ rõ identity/tenant đáng tin cậy.

### 10.8. Body size và JSON parser

Giới hạn 8 KiB ở converter giảm nguy cơ memory exhaustion nhưng không thay thế proxy/container max request size, giới hạn nesting, duplicate-key policy, timeout, request concurrency và WAF nếu cần. Jackson parsing từ input body có thể gây tốn CPU với JSON đặc biệt; cân nhắc thiết lập parser constraints theo yêu cầu bảo mật thực tế. Không xây JSON parser thủ công bằng split/regex cho credentials.

## 11. Các lỗi hay gặp và cách xử lý

| Hiện tượng | Khả năng nguyên nhân | Cách xác minh |
| --- | --- | --- |
| POST /api/login trả 403 dù JSON đúng | CsrfFilter từ chối trước authentication | Gửi CSRF token hợp lệ, kiểm tra repository và session |
| Converter không chạy | Filter matcher sai URL/method, sai chain, filter chưa được add | Xem SecurityFilterChain được chọn và vị trí AuthenticationFilter |
| Converter nhận body rỗng | Filter khác đã đọc stream, client không gửi body | Kiểm tra input stream, thứ tự filters, logging |
| Login trả 400 | JSON sai cú pháp/schema, password field null, dữ liệu vượt field limits | Xem validation, JSON client thật, Content-Type |
| Login trả 415 | Content-Type không phải application/json hoặc lỗi cú pháp media type | Gửi đúng Content-Type, kiểm tra charset |
| Login trả 413 | Body quá 8 KiB | Giới hạn payload và kiểm tra client gửi dư dữ liệu gì |
| Login trả 401 với password đúng | Provider/encoder/UserDetailsService sai cấu hình, user disabled | Test AuthenticationManager, BCrypt hash, status account |
| Login trả 200 nhưng GET /api/me 401 | Context không được save, session cookie bị mất, stateless policy | Kiểm tra SecurityContextRepository ở filter và chain, Set-Cookie và cookie request sau |
| Login trả 200 nhưng trình duyệt lại không thấy user | Client bỏ cookie, khác origin, SameSite/Secure/CORS, session timeout | Theo dõi request cookies và chính sách browser |
| Converter trả null cho JSON lỗi | Trả null thay vì ném AuthenticationException | Phân biệt request không áp dụng và payload sai |
| Thêm roles từ payload mà API “vẫn chạy” | Đã tạo trusted token trước xác minh | Chỉ dùng unauthenticated token và trusted provider |
| Có hai lần login/filter chạy | Đăng ký filter trùng container + security chain, bật formLogin đồng thời | Kiểm tra cách đăng ký filter và matcher |
| Custom filter chạy với Basic/Bearer sai | Matcher quá rộng hoặc các chain chồng lấn | Cấu hình securityMatcher/requestMatcher chính xác |
| HTTP error lộ stack trace | Ngoại lệ chưa được bao/tầng lỗi trả chi tiết | Quy định failure handler trả lỗi tổng quát và log an toàn |
| Test WithMockUser PASS nhưng login thật FAIL | Test không đi qua converter/provider | Dùng MockMvc post JSON + csrf, session assertions |
| Mật khẩu có khoảng trắng bị từ chối | Converter tự trim/normalize password | Giữ nguyên password input, chỉ kiểm tra null/empty phù hợp |

### AuthenticationFilter khác UsernamePasswordAuthenticationFilter thế nào?

`UsernamePasswordAuthenticationFilter` truyền thống đọc username/password qua **request parameters** (phù hợp form-urlencoded) và có xử lý riêng cho cấu hình form login. Nó không mặc định đọc JSON body bằng Jackson. `AuthenticationFilter` mang abstraction `AuthenticationConverter` để tách trích xuất dữ liệu từ request khỏi việc authentication. Khi xây JSON login, đặt custom converter vào AuthenticationFilter thường rõ ràng hơn việc đọc body trực tiếp rồi tự set SecurityContext trong controller.

### Vì sao không dùng @RequestBody và @Valid trong converter?

`@RequestBody` và nhiều tính năng của `@Valid` là cơ chế argument resolution/validation của **Spring MVC controller**. AuthenticationFilter xử lý ở lớp Servlet Filter **trước khi request tới DispatcherServlet**, nên không thể giả định annotation của controller tự parse/validate JSON cho converter. Muốn dùng Bean Validation có thể tự gọi validator hoặc tách phần validation thành service, nhưng cần kiểm soát đầu vào/ngoại lệ trong filter. Trong ví dụ, record và điều kiện validation được viết rõ ngay trong converter.

## 12. Câu hỏi và bài tập tự kiểm tra

**Bài 1.** Vì sao `AuthenticationConverter` không nên tạo `UsernamePasswordAuthenticationToken.authenticated(...)` trực tiếp từ JSON?

**Đáp án:** Vì JSON là dữ liệu chưa tin cậy; converter chỉ chuyển đổi credential, còn provider phải kiểm tra bằng UserDetailsService/PasswordEncoder. Tạo trusted token trực tiếp bỏ qua xác minh và có thể cấp quyền sai.

**Bài 2.** Khách gửi body JSON sai cú pháp tới POST /api/login. Converter nên trả null hay ném AuthenticationException?

**Đáp án:** Với request đã khớp login endpoint, nên ném AuthenticationException phù hợp để failure handler tạo phản hồi lỗi có chủ đích. `null` chỉ thích hợp khi không có authentication attempt áp dụng theo hợp đồng đã thiết kế.

**Bài 3.** Một developer dùng `@PostMapping("/api/login")` với `@RequestBody` và kỳ vọng AuthenticationFilter tự nhận object DTO. Điều đó có đúng không?

**Đáp án:** Không. AuthenticationFilter chạy trước Spring MVC controller. Converter phải tự đọc, parse và validate HttpServletRequest (hoặc ủy quyền vào một component dành cho filter), không dựa vào @RequestBody của controller.

**Bài 4.** Converter nhận `{"username":"alice","password":"good","roles":["ADMIN"]}`. Tại sao phải từ chối hoặc bỏ qua roles từ client?

**Đáp án:** Client không có quyền tự khai báo authority đã được xác minh. Roles và permissions phải do nguồn trusted/provid­​er cấp sau khi xác thực. Trong ví dụ strict JSON schema, field lạ bị từ chối 400.

**Bài 5.** Login POST với JSON hợp lệ và password đúng nhưng thiếu CSRF token; hệ thống dùng cookie/session. Có thể thấy 403 không?

**Đáp án:** Có. CsrfFilter có thể từ chối POST trước khi converter chạy. JSON không tự miễn CSRF; cần token hợp lệ theo cơ chế csrf repository/handler của ứng dụng.

**Bài 6.** `AuthenticationManager` trả success, success handler viết 200 JSON, nhưng GET /api/me sau đó luôn bị từ chối. Điều gì cần xem?

**Đáp án:** Kiểm tra context có được save vào SecurityContextRepository phù hợp không, chain có cùng repository không, cookie session có được gửi/nhận không và có chính sách stateless nào làm mất persistence không.

**Bài 7.** Vì sao hạn mức body dùng `readNBytes(limit + 1)` thay vì chỉ nhìn Content-Length?

**Đáp án:** Content-Length có thể vắng mặt hoặc request dùng chunked transfer; đọc tối đa limit+1 byte giúp phát hiện payload quá lớn mà không giữ cả body trong RAM.

**Bài 8.** Một custom filter log request body trước AuthenticationFilter làm converter luôn nhận input rỗng. Vấn đề nằm ở AuthenticationManager không?

**Đáp án:** Không. Servlet body stream đã bị tiêu thụ trước khi converter đọc. Cần thiết kế logging không ghi credentials và kiểm soát wrapper/thứ tự filter; không sửa PasswordEncoder để xử lý lỗi stream.

**Bài 9.** Một người dùng login JSON rồi ứng dụng muốn cung cấp Bearer token cho SPA. AuthenticationConverter có nhiệm vụ phát hành/ký JWT không?

**Đáp án:** Không. Converter chỉ đọc request thành Authentication request. Token issuance, expiry, revocation, bảo vệ key và validation của resource server là các thành phần/quy trình riêng.

**Bài 10.** Tại sao `@WithMockUser` không đủ kiểm thử converter?

**Đáp án:** Annotation này đưa Authentication có sẵn vào test, bỏ qua body parsing và quá trình provider kiểm tra credentials. Cần gửi POST JSON thật qua MockMvc và xác minh status, lỗi, SecurityContext/session.

## 13. Checklist trước khi đưa JSON login vào production

- [ ] Xác nhận **đúng SecurityFilterChain** và `RequestMatcher` cho POST login, không chặn/bắt nhầm endpoint khác.
- [ ] Converter chỉ parse request, trả **Authentication chưa xác thực**, không lấy roles/authorities từ client.
- [ ] Giới hạn Content-Type, body size, username/password lengths; kiểm tra JSON schema, xử lý input stream một lần.
- [ ] Dùng `AuthenticationManager`/provider đáng tin và `PasswordEncoder` phù hợp, không tự so sánh password.
- [ ] Thiết kế phản hồi 400/401/413/415/503 và messages không dò được username/credentials.
- [ ] Nếu dùng **session cookie**, giữ CSRF protection, session fixation controls, logout, cookie flags và repository persistence nhất quán.
- [ ] Nếu chọn **stateless token**, xác định riêng token issuance, key rotation, TTL, validation và revocation; không nghĩ JSON đồng nghĩa stateless.
- [ ] Không log request body, password, hash, session ID hoặc Authentication chứa credentials.
- [ ] Rate limiting, abuse monitoring, MFA và security audit thuộc tầng chính sách rộng hơn converter.
- [ ] Test JSON đúng, password sai, JSON sai, unknown fields, body lớn, CSRF, session request sau và multiple security chains.
- [ ] Cân nhắc sai khác về API/constructor giữa các phiên bản Spring Security 6.x; khóa và kiểm thử trên version thực tế.

**Ghi nhớ:** `AuthenticationConverter` là **cửa chuyển đổi từ HTTP JSON sang Authentication request chưa được tin cậy**; `AuthenticationFilter` phối hợp matcher, AuthenticationManager và handlers để hoàn thành luồng login. Giữ ranh giới này rõ ràng giúp hệ thống vừa hỗ trợ frontend JSON, vừa tái sử dụng cơ chế mật khẩu, phân quyền và vòng đời SecurityContext của Spring Security.