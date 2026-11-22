# Chuyển hướng tới trang đăng nhập khác với trả HTTP 401 cho API

## 1. Bài toán: một ứng dụng, hai cách trả lời khi chưa đăng nhập

Một ứng dụng Spring Security có thể đồng thời phục vụ **trang HTML cho người dùng** và **REST API cho frontend/ứng dụng di động/service**. Cả hai đều có tài nguyên cần xác thực, nhưng khi credential thiếu hoặc không hợp lệ, phản hồi hợp lý có thể rất khác nhau:

- Trình duyệt mở `GET /web/profile` chưa có phiên: thường cần **HTTP 302 Found**, header `Location: /login`. Browser tự mở trang đăng nhập; sau khi login, ứng dụng có thể tiếp tục truy cập tài nguyên ban đầu.
- API client gọi `GET /api/profile` không có bearer access token: thường cần **HTTP 401 Unauthorized** cùng challenge `WWW-Authenticate: Bearer`; không gửi trang HTML login và không chuyển hướng tới web form.
- Một client đã xác thực nhưng thiếu scope/role để vào API: thông thường **HTTP 403 Forbidden**, không phải login redirect và không phải 401 chỉ vì không đủ quyền.

Bài này thuộc phần **Phản hồi xác thực** của module **Spring Security - authentication**. Mục tiêu là nắm được ý nghĩa HTTP, đường đi trong Spring Security Servlet, cấu hình đúng cho web/API, tránh redirect sai ngữ cảnh và kiểm thử đủ các tình huống.

**Thông điệp chính:** phản hồi `302` hay `401` là **quyết định của giao thức tương tác và chính sách của tài nguyên** khi cần xác thực. Nó không thay thế quá trình kiểm mật khẩu/token; càng không có nghĩa ứng dụng được phép giảm bảo mật vì phát hiện request “trông giống API”.

## 2. Bảng so sánh HTTP 302, 401 và 403

| Mã HTTP | Tên chuẩn | Ý nghĩa trong ứng dụng | Header tiêu biểu | Client xử lý |
| --- | --- | --- | --- | --- |
| **302** | Found | Resource web yêu cầu login, hướng browser tới trang đăng nhập | `Location: /login` | Trình duyệt điều hướng tới trang login |
| **303** | See Other | Chuyển client bằng GET sang URL khác, thường sau POST thành công | `Location: /somewhere` | Theo URI mới bằng GET |
| **401** | Unauthorized | Request chưa có credentials hợp lệ cho tài nguyên | `WWW-Authenticate: Bearer` hoặc `Basic ...` | Client lấy/đổi credential, yêu cầu lại nếu phù hợp |
| **403** | Forbidden | Request đã xác thực nhưng không được cấp quyền, hoặc bị policy khác từ chối | Thường không có `Location` | Không tự thử login lặp lại; xử lý thiếu quyền |
| **429** | Too Many Requests | Vượt quota/rate limit, ví dụ login throttling | Có thể `Retry-After` | Backoff theo policy, không spam lại |
| **500/503** | Server/Service Unavailable | Hệ thống xác thực hoặc phụ thuộc đang lỗi | Tùy lỗi | Không nhầm thành “mật khẩu sai” hoặc “đăng nhập lại” |

**Chi tiết:** tên chuẩn của HTTP 401 là “Unauthorized”, nhưng về thực tế nó thường được dùng cho **chưa xác thực**; 403 thường dùng cho đã xác thực nhưng **không được phép**. HTTP cũng cho phép 403 cho một số lý do policy khác; status thực tế của Spring Security còn phụ thuộc entry point, CSRF, access denied handler và loại credential.

**Không dùng status 302/401 thay nhau theo sở thích.** API client có thể tự động follow 302, nhận HTML trang login với status 200 và tưởng API thành công. Ngược lại, một browser vào trang web mà chỉ nhận JSON 401 thường không có trải nghiệm đăng nhập phù hợp.

## 3. Hai HTTP exchange minh họa

### 3.1. Web browser: redirect tới trang login

Request khi chưa có phiên:

```http
GET /web/profile HTTP/1.1
Host: app.example.test
Accept: text/html
```

Phản hồi thường gặp khi form login được cấu hình:

```http
HTTP/1.1 302 Found
Location: /login
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

Browser sẽ thực hiện một request **khác** tới `GET /login`. Đây không phải 401, và trang login không phải response của endpoint `/web/profile`. Header `Location` có thể chứa absolute URL trong một số triển khai/proxy, vì vậy test nên kiểm cùng đích được dự kiến thay vì giả định luôn đúng một chuỗi.

Sau khi đăng nhập thành công, Spring Security có thể sử dụng saved request để quay về tài nguyên ban đầu. Đây là UX cho **điều hướng trình duyệt**; không nên sao chép nguyên vào JSON API.

### 3.2. REST API: trả challenge 401

```http
GET /api/profile HTTP/1.1
Host: app.example.test
Accept: application/json
```

Phản hồi điển hình khi sử dụng OAuth2 Resource Server:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
```

Thư viện Spring Security có thể bổ sung các tham số phù hợp vào `WWW-Authenticate`; ví dụ bearer token bị từ chối do hết hạn/chữ ký sai có thể nhận `error="invalid_token"` theo RFC 6750. **Không** bắt buộc mọi response 401 phải có JSON body. Client HTTP phải dựa trên status và challenge theo contract; body là dữ liệu hỗ trợ, không phải credential.

### 3.3. Token đúng nhưng thiếu quyền: 403

Giả sử token đã được Resource Server xác minh về chữ ký, issuer, audience và thời hạn, nhưng chỉ có `SCOPE_profile.read` trong khi endpoint `/api/admin` cần `SCOPE_admin.read`.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Đây là **ví dụ hình thức header có thể gặp**, không phải cam kết byte-for-byte cho mọi phiên bản và custom handler. Điểm cần nhớ: token hợp lệ không có nghĩa đủ quyền. Không biến thiếu scope thành 302 tới web login; login lại bằng cùng quyền chưa chắc giải quyết được.

## 4. Ai quyết định phản hồi trong Spring Security?

Trong Servlet stack, một request đi qua `FilterChainProxy` và các filter của `SecurityFilterChain` khớp với request. Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `AuthorizationFilter` / method security | Áp chính sách quyền; có thể tạo `AccessDeniedException` |
| `ExceptionTranslationFilter` | Chuyển security exceptions thành phản hồi HTTP/khởi động authentication |
| `AuthenticationEntryPoint` | Chọn **cách bắt đầu xác thực**: redirect, 401 + challenge, HTTP status… |
| `LoginUrlAuthenticationEntryPoint` | Chuyển tới URL form login cho browser |
| `BearerTokenAuthenticationEntryPoint` | Trả status/challenge OAuth2 Bearer theo Resource Server |
| `BasicAuthenticationEntryPoint` | Gửi 401 cùng challenge `WWW-Authenticate: Basic ...` |
| `HttpStatusEntryPoint` | Chỉ trả status được cấu hình, ví dụ 401; không tự phát Bearer challenge |
| `AccessDeniedHandler` | Xử lý quyền bị từ chối sau khi đã xác thực, thường 403 |
| `RequestCache` | Có thể lưu request web trước khi redirect để tiếp tục sau login |
| `AuthenticationFailureHandler` | Xử lý **POST login thất bại**; khác với entry point khi vào tài nguyên protected |

### 4.1. ExceptionTranslationFilter không xác minh mật khẩu

Một trường hợp thường gặp:

```text
GET /web/profile (anonymous)
    |
    v
AuthorizationFilter: yêu cầu authenticated → denied
    |
    v
ExceptionTranslationFilter:
    request chưa authenticated → AuthenticationEntryPoint
    |
    v
LoginUrlAuthenticationEntryPoint
    |
    v
302 Location: /login
```

Đối với `GET /api/profile`, chain Resource Server chọn Bearer entry point rồi trả 401. Nếu một user đã authenticated nhưng thiếu role, `ExceptionTranslationFilter` thường chuyển `AccessDeniedException` cho `AccessDeniedHandler`, thường là 403.

Cần phân biệt **ngoại lệ phát sinh trong luồng authentication filter** (ví dụ malformed bearer token được xử lý bởi bearer filter/entry point) với ngoại lệ phát sinh khi authorization đánh giá quyền. Không phải mọi failure đều đi theo cùng call stack nội bộ, dù chúng có thể tạo mã HTTP giống nhau. Hãy cấu hình và test **kết quả cuối** thay vì dựa hoàn toàn vào thứ tự filter tự suy đoán.

### 4.2. Entry point không phải success/failure handler

- Request chưa đăng nhập vào `/web/profile` → entry point quyết định redirect 302.
- User submit `POST /login` sai password → `AuthenticationFailureHandler` thường redirect `/login?error` (hoặc response khác nếu tùy biến).
- User submit login đúng → `AuthenticationSuccessHandler` tiếp tục saved request/default URL.
- User đã xác thực vào resource thiếu quyền → `AccessDeniedHandler` quyết định 403 hoặc policy khác.

Nếu bạn chỉ tùy chỉnh `AuthenticationEntryPoint` mà mong thay đổi response của việc **POST form login sai password**, có thể sẽ không đạt yêu cầu: đó là trách nhiệm của failure handler. Ngược lại, đổi failure handler cũng không tự biến API chưa token thành 401.

## 5. Trình duyệt và API cần contract khác nhau

Với **trang HTML dùng server-side session**:

1. Browser gửi cookie phiên nếu có.
2. Tài nguyên protected cần user đăng nhập.
3. Nếu chưa đăng nhập, server thường redirect 302 tới trang form/OIDC login.
4. Browser hiển thị login; sau login hợp lệ có thể quay lại request trước đó.

Với **REST API token-based**:

1. Client gửi `Authorization: Bearer <access_token>` qua TLS.
2. Resource Server xác minh access token theo issuer/chữ ký hoặc introspection, audience, thời gian và policy.
3. Nếu thiếu/sai token, trả 401 với challenge phù hợp; nếu token hợp lệ nhưng thiếu scope, thường 403.
4. Client quyết định xin token mới, yêu cầu user tương tác theo flow hợp lệ hoặc hiển thị lỗi. Server không chuyển API request tới form HTML.

Một SPA sử dụng browser **vẫn là API client** khi gọi `fetch("/api/...")`. Việc request được tạo bởi browser không làm JSON endpoint trở thành navigation web. Cần phân biệt **top-level navigation** với **AJAX/fetch** và policy của **đường dẫn**, không đoán chỉ qua user-agent.

## 6. Vì sao chỉ nhìn Accept hoặc X-Requested-With chưa đủ?

Có thể dùng `Accept: text/html` để nhận diện mục tiêu hiển thị, nhưng:

- JavaScript fetch có thể gửi `Accept: */*`.
- Browser navigation có thể chấp nhận nhiều media types.
- Một mobile client có thể gửi `Accept: text/html` do cấu hình mặc định sai.
- Header `X-Requested-With: XMLHttpRequest` không còn được mọi client tự động gửi và có thể bị giả.
- User-Agent, Referer, Origin, Sec-Fetch-* hỗ trợ phân tích nhưng **không phải bằng chứng xác thực**.

Đừng xây security boundary kiểu:

```java
// PSEUDOCODE PHẢN VÍ DỤ: không dùng để quyết định giảm xác thực
if (request.getHeader("Accept").contains("text/html")) {
    redirectToLogin();
} else {
    permitOrReturn401();
}
```

Nếu có thể, **tách các URL theo namespace** và bảo đảm mỗi namespace có entry point, authentication mechanism và session policy rõ ràng: `/api/**` dùng Bearer, `/web/**` dùng form/session. Content negotiation có thể điều chỉnh **presentation** sau khi policy đã rõ, không dùng để cho phép một cơ chế yếu hơn vượt qua quy tắc truy cập.

Nếu một URL bắt buộc hỗ trợ cả HTML navigation và API, cần `DelegatingAuthenticationEntryPoint` với `RequestMatcher` được thiết kế/test kỹ, nhưng phải giữ nguyên **yêu cầu xác thực** bất kể cách trả lời. Chỉ đổi 302/401 không được làm thay đổi authenticated principal/authorities.

## 7. Cấu hình nhiều SecurityFilterChain: mô hình đáng tin

Một ứng dụng Spring Security Servlet có thể khai báo nhiều bean `SecurityFilterChain`. Spring Security duyệt theo `@Order` và dùng **chain đầu tiên** có `securityMatcher` khớp request.

```text
@Order(1): http.securityMatcher("/api/**")
  oauth2ResourceServer(jwt)
  stateless API, bearer challenge
  /api/private: SCOPE_api.read
  /api/admin:   SCOPE_admin.read
  others: denyAll

@Order(2): chain không có securityMatcher
  formLogin
  /, /error: permitAll
  other web URLs: authenticated
  anonymous protected web request → 302 /login
```

**Khác biệt cần nhớ:**

- `securityMatcher("/api/**")` quyết định **chain** nào xử lý request.
- `requestMatchers("/api/private")` quyết định **quy tắc quyền** bên trong chain API.
- `anyRequest()` chỉ bao phủ request thuộc chain hiện tại.
- Nếu không có catch-all chain, URL ngoài mọi matcher có thể không được Spring Security bảo vệ.
- Endpoint do filter tạo, ví dụ `GET /login` và `POST /login`, cũng chỉ khả dụng trong chain mà URL của chúng thuộc phạm vi. Vì vậy đừng đặt form login duy nhất trong chain `/api/**` rồi chờ `/login` hoạt động bên ngoài matcher.
- Không bật `formLogin()` trong chain API thuần Bearer nếu định dạng API yêu cầu 401 và không có web session.

Sự tách biệt này còn giúp **CSRF/session** được cấu hình đúng theo loại client: browser form thường có session/cookie và CSRF protection; API chỉ dùng bearer header thường không cần CSRF cho cùng mô hình credential. Không áp dụng `csrf.disable()` toàn ứng dụng chỉ để sửa 403 trong API.

## 8. Ví dụ Spring Boot 3.x, Java 17+: web redirect và API 401

Ví dụ chạy trên Spring MVC/Servlet với Spring Boot 3.x + Spring Security 6.x, Java 17+. Có một local user mẫu để thử web form và một OAuth2 Resource Server cho API. **Tài khoản mẫu chỉ dùng local development**; token JWT dành cho API cần do Authorization Server bên ngoài phát hành.

### 8.1. Dependencies

Trong project có Spring Boot Gradle plugin và dependency management, thêm khối `dependencies` sau vào `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Resource Server JWT dùng thư viện JOSE được starter cung cấp. Chỉ cấu hình `spring-boot-starter-oauth2-client` nếu ứng dụng cũng cần chủ động login bằng OAuth2/OIDC hoặc gọi API bên ngoài; điều đó **khác** với việc Resource Server nhận Bearer token.

### 8.2. JWT issuer, JWKS và audience

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

Từ Spring Boot 3.x/Spring Security 6.5 có hỗ trợ cấu hình resource server JWT và audience validation theo property `audiences`. Với phiên bản cụ thể, đối chiếu tài liệu/BOM đang chạy. `issuer-uri` phải khớp claim `iss`, `audiences` phải chứa tài nguyên API hiện tại, còn `jwk-set-uri` phải được công bố bởi issuer **được tin cậy**. Không lấy JWKS URI từ HTTP request hoặc từ token chưa kiểm chứng.

Các biến môi trường minh họa:

```bash
export JWT_ISSUER='https://issuer.example.test'
export JWT_JWK_SET_URI='https://issuer.example.test/jwks'
export JWT_AUDIENCE='demo-api'
```

URL `example.test` không phải IdP đang chạy; thay bằng cấu hình thật từ môi trường lab. Việc khai báo `jwk-set-uri` giúp tránh phải thực hiện issuer discovery lúc khởi động ở một số cách cấu hình; khi xác minh token thật vẫn cần JWKS có thể truy cập và token hợp lệ. Không đưa private signing key của AS vào resource server.

### 8.3. Main application

Tất cả Java file trong `src/main/java/com/example/responses/` với package `com.example.responses`.

**`ResponseApplication.java`**

```java
package com.example.responses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseApplication.class, args);
    }
}
```

### 8.4. SecurityConfig.java: tách hai chain

**`SecurityConfig.java`**

```java
package com.example.responses;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/private")
                        .hasAuthority("SCOPE_api.read")
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasAuthority("SCOPE_admin.read")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService localDemoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("LocalOnly-ChangeMe!"))
                        .roles("USER")
                        .build());
    }
}
```

**Giải thích chính xác vai trò từng dòng:**

1. Chain API có `@Order(1)` và `securityMatcher("/api/**")`, nên request `/api/private` không rơi vào chain form login ngay cả khi `Accept: text/html`. Chỉ Resource Server JWT được bật trong chain này.
2. `oauth2ResourceServer(...jwt(...))` xác thực bearer access token; theo cấu hình mặc định, thiếu/sai token khi truy cập protected API dẫn tới **401 với Bearer challenge**, không phải HTML login redirect.
3. `SCOPE_api.read`/`SCOPE_admin.read` là authorities từ scope JWT theo convention của Spring Security; chỉ khi token được xác minh và đủ authority mới được truy cập các endpoint.
4. `SessionCreationPolicy.STATELESS` làm rõ API không dùng web login session cho auth. `csrf(...disable)` chỉ an toàn trong phạm vi **API header-based thuần Bearer không dùng cookie authentication**; không dùng cho endpoint yêu cầu cookie.
5. Chain web không có `securityMatcher` riêng nên bao phủ URL còn lại; `formLogin(...)` bật default generated login page và xử lý form. Anonymous GET `/web/private` thường được 302 tới `/login`.
6. `UserDetailsService` dùng một tài khoản/mật khẩu **cố định để demo local**, đã hash với BCrypt. Trong production phải dùng user store phù hợp, secret management, MFA/rate limiting và không commit một mật khẩu dùng được vào repo.
7. Không gộp `formLogin()` và `oauth2ResourceServer()` vào một chain toàn cục rồi hy vọng Spring tự đoán đúng mọi request; nếu không khai báo entry point/chính sách rõ, kết quả có thể phụ thuộc matcher, handler và content negotiation.
8. `permitAll()` của `/api/public` cho phép request không có token, nhưng nếu client gửi một bearer token **sai**, bearer authentication filter vẫn có thể từ chối request trước authorization. Không đồng nghĩa endpoint phải phớt lờ mọi token sai.

### 8.5. Controller minh họa

**`DemoController.java`**

```java
package com.example.responses;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/web/private")
    public String webPrivate() {
        return "Web: signed in";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "API: public";
    }

    @GetMapping("/api/private")
    public String apiPrivate() {
        return "API: read permitted";
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "API: admin permitted";
    }
}
```

Ví dụ dùng text đơn giản để dễ quan sát, nhưng với production cần JSON contract cho API, HTML/template phù hợp cho web và domain authorization ở service. Không trả raw access token, password hoặc thông tin nội bộ security context trong response.

### 8.6. Kết quả kỳ vọng

Chạy `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`) sau khi cấu hình biến môi trường và Gradle wrapper phù hợp.

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/web/private
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -H 'Accept: text/html' http://localhost:8080/api/private
```

Kết quả **kỳ vọng theo cấu hình**, không phải output đã chạy qua một AS thật:

| Request | Kỳ vọng |
| --- | --- |
| `GET /` | 200, nội dung public |
| `GET /web/private` anonymous | 302 redirect đến `/login` |
| `GET /login` anonymous | 200, form login do Spring Security tạo |
| `GET /api/public` không token | 200 |
| `GET /api/private` không token | 401 + `WWW-Authenticate: Bearer` |
| `GET /api/private` với `Accept: text/html` nhưng không token | Vẫn 401, không chuyển HTML login |
| `GET /api/private` token hợp lệ có scope `api.read` | 200 |
| `GET /api/admin` token hợp lệ chỉ có `api.read` | 403 |
| `GET /api/admin` token hợp lệ có `admin.read` | 200 |

Không dùng `curl -L` khi muốn kiểm trực tiếp response 302; `-L` sẽ theo redirect và có thể khiến bạn chỉ thấy response của `/login`. Không đưa token thật vào history, logs, ticket; nên dùng terminal an toàn và token test ngắn hạn.

## 9. MockMvc: test đúng 302, 401 và 403

Với `spring-security-test` và `spring-boot-starter-test`, tạo file `src/test/java/com/example/responses/ResponseSecurityTest.java`.

**`ResponseSecurityTest.java`**

```java
package com.example.responses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "spring.security.oauth2.resourceserver.jwt.issuer-uri=https://issuer.example.test",
        "spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://issuer.example.test/jwks",
        "spring.security.oauth2.resourceserver.jwt.audiences=demo-api"
})
@AutoConfigureMockMvc
class ResponseSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebNavigationRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, endsWith("/login")));
    }

    @Test
    void anonymousApiReturnsBearer401EvenWithHtmlAccept() throws Exception {
        mvc.perform(get("/api/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Bearer")));
    }

    @Test
    void publicApiWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("API: public"));
    }

    @Test
    void jwtWithReadScopeIsAccepted() throws Exception {
        mvc.perform(get("/api/private").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_api.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("API: read permitted"));
    }

    @Test
    void authenticatedJwtWithoutAdminScopeGets403() throws Exception {
        mvc.perform(get("/api/admin").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_api.read"))))
                .andExpect(status().isForbidden());
    }
}
```

Chạy `./gradlew test` hoặc `.\gradlew.bat test`. Kết quả mong đợi: năm test pass khi được đặt trong project Boot 3.x theo ví dụ, với dependencies và security config phù hợp. Đây là **test mô phỏng** ở mức Spring MVC/security authorization; không khẳng định đã chạy trong một project thực ở bài này.

### 9.1. Vì sao jwt() không test chữ ký?

`jwt()` của Spring Security Test đặt một `JwtAuthenticationToken` giả lập vào request. Nó có thể kiểm security chain selection và authorization policy, **không xác thực** JWT signature, issuer, audience, expiration, `kid` hoặc key rotation.

Integration test cần tạo JWT thực được ký bằng khóa test và JWKS endpoint thử nghiệm, gọi API qua `Authorization: Bearer ...` để `BearerTokenAuthenticationFilter`/`JwtDecoder` xử lý. Các case cần thử: token giả, sai chữ ký, sai issuer/audience, hết hạn, chưa tới `nbf`, thiếu scope, JWT đúng nhưng dành cho API khác.

### 9.2. Test web login thật và request cache

Để kiểm phần redirect và session:

- Anonymous GET `/web/private` → 302 `/login`; `GET /login` sinh trang HTML.
- POST form login đúng bằng MockMvc `formLogin()` (có CSRF test support) → authenticated session; dùng cùng `MockHttpSession` khi GET `/web/private`.
- POST login sai → handler trả URL lỗi theo cấu hình, không nhầm với anonymous entry point.
- Gửi POST thay đổi trạng thái qua browser **không có CSRF token** → thường 403; không phải do bearer JWT sai.
- Đăng nhập xong kiểm saved request/back-navigation, cookie session và logout.

Request cache chỉ nên lưu các request web hợp lệ. Với API, không cần tạo `SavedRequest` hay chuyển request POST nhạy cảm sang trang login rồi replay ngoài ý định. Đặc biệt cần test sau login: HTTP method, body và CSRF của thao tác trước login **không được** phát lại một cách không an toàn.

## 10. Tùy chỉnh AuthenticationEntryPoint cho API

Nếu một API **không dùng Bearer** (ví dụ một integration có hợp đồng trả JSON 401 riêng), có thể khai báo `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` hoặc entry point trả JSON. Nhưng nếu API dùng OAuth2 Bearer, việc thay toàn bộ entry point bằng status-only 401 có thể **làm mất `WWW-Authenticate`**, khiến client không nhận được challenge chuẩn.

Trong Spring Security Servlet, mã sau chỉ là **snippet cấu hình cho một chain API không phụ thuộc Bearer**, không phải class chạy riêng:

```java
.exceptionHandling(errors -> errors
        .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
```

Imports:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
```

Không thêm đoạn này vào resource server JWT của mục 8 rồi khẳng định vẫn có Bearer challenge. Với Bearer token, tốt nhất giữ `BearerTokenAuthenticationEntryPoint` theo mặc định hoặc delegate tới nó khi định dạng thêm body JSON.

### 10.1. Mẫu trả JSON và giữ Bearer challenge

Nếu API yêu cầu một JSON body nhất quán khi thiếu/sai Bearer token, hãy thiết kế entry point **gọi BearerTokenAuthenticationEntryPoint trước**, rồi bổ sung body **chỉ khi response chưa committed**. Đoạn sau minh họa trong `SecurityConfig` của API chain:

```java
var bearerEntryPoint = new BearerTokenAuthenticationEntryPoint();

http.exceptionHandling(errors -> errors
        .authenticationEntryPoint((request, response, exception) -> {
            bearerEntryPoint.commence(request, response, exception);
            if (!response.isCommitted()) {
                response.setHeader("Cache-Control", "no-store");
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write(
                        "{\"error\":\"authentication_required\"}");
            }
        }));
```

Imports tương ứng: `org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint`. Đây là **snippet đặt bên trong cấu hình HttpSecurity**, và cần test trường hợp không token, token sai, token expired cùng `WWW-Authenticate`. Một số lỗi có thể được filter Resource Server tự đưa đến entry point của nó tùy cách cấu hình, nên với yêu cầu chính xác đầu-cuối hãy kiểm thử filter chain, không chỉ nhìn snippet.

Đừng đưa exception message có chứa token, issuer URL nội bộ, stack trace hay thông tin người dùng vào JSON error. Nếu ứng dụng theo RFC 9457 Problem Details, có thể chọn response `application/problem+json` với schema ổn định nhưng vẫn giữ status/challenge thích hợp.

### 10.2. Mã lỗi có nên trả cùng body không?

Có thể chuẩn hóa:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Valid access credentials are required"
}
```

Đối với 403:

```json
{
  "code": "ACCESS_DENIED",
  "message": "You are not allowed to access this resource"
}
```

Đây là **body minh họa do ứng dụng tự định nghĩa**, không phải mặc định của Spring Security. Client nên phân biệt bằng HTTP status, không chỉ dựa trên chuỗi `code`. Không trả thông tin cho biết account tồn tại, mật khẩu sai bao nhiêu lần, role nội bộ của người dùng khác hoặc token validation secret.

## 11. RequestCache và nguy cơ redirect loop

Khi người dùng chưa đăng nhập vào trang web, `ExceptionTranslationFilter` có thể lưu request qua `RequestCache`. Sau login, handler có thể redirect người dùng trở lại URL đã yêu cầu.

Ví dụ:

```text
GET /web/private  ──────> chưa login
      │
      ├─ lưu SavedRequest (session)
      └─ 302 /login
                 │
                 ├─ GET /login: hiển thị form
                 └─ POST /login: kiểm password, CSRF, tạo session
                          │
                          └─ 302 /web/private
```

Điểm cần bảo vệ:

- `GET /login` phải public trong **web chain**, nếu không browser có thể bị redirect vòng tròn tới chính login page.
- Nếu dùng custom `loginPage("/signin")`, **ứng dụng phải tự tạo GET /signin** và cho phép truy cập; nếu không có controller/template sẽ gặp 404 hoặc loop.
- Không đưa API authentication failure vào web `RequestCache` và không thực hiện redirect qua login URL của UI cho `/api/**`.
- Tránh open redirect: chỉ cho phép return URL/saved target từ nguồn/đích đã được kiểm soát. Không lấy `returnTo` tùy ý của attacker rồi redirect sang domain lạ.
- Với browser session, kiểm session fixation, Secure/HttpOnly/SameSite cookies, CSRF token và logout. Nếu hệ thống dùng reverse proxy, cấu hình public scheme/host an toàn để `Location` đúng.
- Có thể cần điều chỉnh `RequestCache` cho các trạng thái đặc biệt như SPA navigation, nhưng không biến một API POST không idempotent thành thao tác tự phát lại sau login.

## 12. Custom login page và chuyển hướng sang OIDC Provider

Nếu dùng form login tùy chỉnh:

```java
.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .permitAll())
```

Đây là đoạn DSL đặt trong **web SecurityFilterChain**; phải tự tạo trang `GET /signin` và form `POST /signin` có CSRF token. Nếu dùng trang login mặc định như ví dụ mục 8, **không cần tự tạo controller cho `/login`**.

Với OIDC/OAuth2 Login, browser có thể được redirect đến:

```text
/oauth2/authorization/<registrationId>
   → Authorization Server / Identity Provider
   → callback /login/oauth2/code/<registrationId>
   → ứng dụng tạo authenticated web session
```

Luồng này có state/PKCE và OIDC token validation theo provider, không chỉ là một HTTP redirect tùy ý. Mặc dù login chuyển qua website IdP, **API Bearer Resource Server vẫn phải trả 401** với client thiếu token, không redirect request API sang IdP rồi mong API client hoàn thành tương tác trình duyệt.

Nếu front-end SPA muốn khởi tạo OIDC login, đó là **quyết định ở client/application workflow** sau khi API trả 401, không phải sự chuyển hướng ngầm từ API backend. Phải bảo đảm Authorization Code with PKCE/nonce/state theo kiến trúc, redirect URI hợp lệ và không gửi access token qua URL tùy ý.

## 13. CORS và CSRF: hai loại lỗi hay bị nhầm với 401

### 13.1. CORS preflight

Browser có thể gửi `OPTIONS /api/...` trước request có Authorization header. Nếu API bảo vệ mọi OPTIONS bằng Bearer mà không cấu hình CORS phù hợp, preflight có thể bị trả 401 và trình duyệt chặn request thật.

Cần cấu hình `CorsConfigurationSource`/`http.cors(...)` hợp lệ cho các origins, methods và headers được phép, xử lý preflight trước security checks theo thiết kế. CORS **không phải cơ chế authentication**; việc cho preflight qua không cho phép đọc tài nguyên protected mà thiếu Bearer token.

Không tùy tiện đặt `Access-Control-Allow-Origin: *` cùng credential cookie hoặc cho mọi origin điều khiển session. Cần dùng chính sách phù hợp browser API và kiểm thử từ origin thực tế.

### 13.2. CSRF và HTTP 403

Một trang web dùng cookie/session có thể cần CSRF token cho POST/PUT/DELETE. Nếu POST form hoặc thao tác UI thiếu CSRF, Spring Security có thể trả **403 Forbidden**, dù user đã đăng nhập. Đây không nhất thiết là “user thiếu role”. Không tắt CSRF để biến phản hồi thành 302.

Ví dụ trong cấu hình mục 8: CSRF bị disable **chỉ trong API chain** vì mô hình API thuần Bearer header, không dựa vào cookie auto-submitted. Web chain giữ CSRF protection. Nếu API dùng session cookie/bearer đồng thời, phải đánh giá lại; không mặc định disable.

### 13.3. HTTP Basic challenge trong browser

Nếu bật `httpBasic()` trên một web chain, browser có thể bật hộp thoại nhập username/password dựa trên challenge Basic thay vì redirect trang login, tùy negotiation và entry point. Vì vậy mẫu web trong bài **chỉ bật formLogin**, còn mẫu API **chỉ bật Resource Server JWT**. Đừng bật nhiều entry points rồi không xác định client nào thuộc tuyến nào.

## 14. Trả 401 khi nào và 403 khi nào?

Bảng quyết định theo trạng thái xác thực và quyền:

| Trạng thái request | Web navigation | API Bearer |
| --- | --- | --- |
| Chưa có credential cho protected resource | Thường 302 tới login | 401, Bearer challenge |
| Credential cung cấp không hợp lệ | Web login failure handler hoặc entry point | 401, có thể `invalid_token` |
| Credential hợp lệ, thiếu authority | Thường 403 hoặc custom access denied UI | Thường 403, có thể `insufficient_scope` |
| Credential hợp lệ, đủ scope nhưng sai tenant/ownership | Phải từ chối theo domain policy | Phải từ chối; status do policy/ẩn tài nguyên quyết định |
| Form POST thiếu CSRF | Thường 403 do CSRF | Không áp dụng nếu API thuần Bearer header và được cấu hình đúng |
| Truy cập endpoint public | 200/3xx theo nghiệp vụ | 2xx nếu endpoint hợp lệ; token sai vẫn có thể bị auth filter từ chối |

Với một API không muốn tiết lộ tài nguyên có tồn tại, một số chính sách có thể chọn 404 thay vì 403 khi phù hợp. Điều này là quyết định **hợp đồng API**, không phải lý do bỏ authn/authz.

**Đừng dùng 401 cho mọi thứ**: khiến client tự refresh/re-login vô hạn, che mất lỗi scope/tenant. **Đừng trả 200 kèm JSON `{error:401}`**: phá HTTP semantics, cache/metrics/monitoring và khiến SDK khó xử lý.

## 15. Frontend xử lý 401 thế nào cho đúng?

Một SPA gọi API bằng JavaScript có thể:

```javascript
async function fetchProfile() {
  const response = await fetch("/api/private", {
    headers: {
      Accept: "application/json",
      Authorization: "Bearer " + getAccessTokenSafely()
    }
  });

  if (response.status === 401) {
    // Không lặp vô hạn. Dùng flow renewal/login đã thiết kế.
    showAuthenticationRequired();
    return;
  }
  if (response.status === 403) {
    showInsufficientPermissions();
    return;
  }
  if (!response.ok) {
    showGenericError();
    return;
  }
  const text = await response.text();
  showProfile(text);
}
```

Hàm `getAccessTokenSafely()`/`show...()` là **hàm của ứng dụng, không có sẵn trong JavaScript**; đây là snippet minh họa cách xử lý HTTP status, không phải file JS chạy độc lập. Ứng dụng cần chọn storage/flow token an toàn; tránh lưu access token dài hạn ở vị trí dễ bị XSS lấy.

**Lưu ý trải nghiệm:**

- Khi 401, chỉ kích hoạt đúng **một** lần refresh/login flow (single-flight), không refresh vô hạn.
- Khi 403, giải thích thiếu quyền và tránh tự logout user nếu token vẫn hợp lệ.
- Không follow redirect HTML ngoài ý muốn rồi parse trang login như JSON.
- Nếu backend trả 429/503, dùng backoff và thông báo phù hợp, không coi đó là “token hết hạn”.
- Không chuyển hướng browser tới URL từ response không đáng tin; tránh open redirect và lộ token qua query/referrer.

## 16. Failure modes phổ biến và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `fetch("/api/...")` nhận HTML login thay vì JSON/401 | API rơi vào chain formLogin hoặc bị redirect 302 | Tách `/api/**` thành Resource Server chain và kiểm 401 |
| API gọi qua curl trả 302 | `LoginUrlAuthenticationEntryPoint` áp cho API | Chọn entry point đúng contract API |
| Browser mở trang web chỉ thấy 401 JSON | Web chain dùng HttpStatusEntryPoint/Bearer | Bật formLogin/OIDC redirect cho web navigation |
| API thiếu bearer header trả 403 | Custom AccessDeniedHandler hoặc CSRF/matcher sai | Kiểm exception type, entry point, CSRF và chain |
| Token đúng nhưng thiếu quyền trả 401 | Catch-all auth failure/handler nhầm authz | Giữ authentication riêng, trả 403/insufficient_scope |
| 401 không có `WWW-Authenticate` | Thay Bearer entry point bằng HttpStatusEntryPoint | Giữ Bearer challenge qua delegate |
| POST form sai mật khẩu không theo custom entry point | `AuthenticationFailureHandler` xử lý form login failure | Tùy chỉnh failure handler đúng vị trí |
| `GET /login` trả 404 | Form login nằm trong chain không khớp `/login` hoặc custom page chưa có | Đảm bảo chain/matcher và controller/template |
| Login page redirect loop | `/login` không public hoặc bị rule khác bắt | Cho phép login endpoints, xem chain order |
| API hết hạn token rồi liên tục 302 đến IdP | Dùng `oauth2Login()` thay Resource Server | API trả 401; client tự điều phối login khi phù hợp |
| CORS preflight bị 401 | OPTIONS không được CORS xử lý đúng | Cấu hình CORS preflight trước auth |
| 403 trên web POST mặc dù authenticated | CSRF token thiếu hoặc policy deny | Bổ sung CSRF đúng, không tắt bừa |
| Dùng `Accept` để cho phép một flow yếu hơn | Header do client chọn, sai trust boundary | Security policy theo route/credential |
| URL ngoài mọi `SecurityFilterChain` | Không có catch-all | Thêm chain bao phủ tất cả request dự kiến |
| API “public” gửi token sai bị từ chối | Bearer filter xử lý token sai trước `permitAll()` | Client đừng gửi token sai, hoặc thiết kế route/chain rõ |
| Proxy tạo redirect HTTP thay vì HTTPS | Host/scheme forwarding không tin cậy/chưa đúng | Cấu hình trusted proxy, public URL/forward headers |
| Test MockMvc `jwt()` pass nhưng JWT giả cũng được chấp nhận | Test bypass decoder thật | Integration test JWT/JWKS có chữ ký |

Không sửa tất cả các lỗi bằng `permitAll()` hoặc `csrf.disable()` toàn cục. Việc “API trả 200” khi thiếu xác thực không phải giải quyết vấn đề response mà là tạo lỗ hổng.

## 17. Kiểm thử hồi quy theo ma trận

Ngoài năm test mẫu, một suite hợp lý cần bao phủ:

1. Anonymous web `GET /web/private` → `302 Location /login`; anonymous `GET /login` → form 200.
2. Anonymous API `GET /api/private` → 401 + `WWW-Authenticate: Bearer` với `Accept: application/json` **và** `Accept: text/html`.
3. API bearer token sai signature/issuer/audience/exp → 401; không được chuyển sang chain web.
4. API token đúng nhưng thiếu `SCOPE_admin.read` → 403; không bị logout vô cớ.
5. API token đúng với scope → 200; browser session cookie **không** tự cấp access token cho resource server.
6. Browser login thành công với CSRF và session → vào được `/web/private`; form login failure đi qua failure handler.
7. Web POST thiếu CSRF → 403; API Bearer POST theo policy riêng, không tắt CSRF ở web.
8. Browser truy cập API với `Accept: text/html` → vẫn 401 (route quan trọng hơn header).
9. CORS OPTIONS hợp lệ → preflight xử lý phù hợp, nhưng business GET/POST vẫn yêu cầu token.
10. URI ngoài `/api/**` thuộc web catch-all, không trôi ra ngoài Spring Security; login/logout endpoints nằm đúng chain.
11. Redirect qua reverse proxy HTTPS, saved request và URL return target không gây open redirect/loop.
12. Client theo redirect/SPA SDK nhận đúng HTTP status, không báo 200 sau khi vô tình tải HTML login.

Khi kiểm thử bằng `curl`, dùng `-i` để xem status và headers; tránh `-L` nếu muốn quan sát 302 gốc. Với MockMvc, kiểm riêng status, Location và WWW-Authenticate; đừng assert một HTML body thay cho header semantics.

## 18. Vận hành và an toàn

- **Định nghĩa rõ hợp đồng:** tài nguyên nào HTML redirect, tài nguyên nào JSON/Bearer 401, URL public nào, lối login nào và scope nào.
- **Giữ response đúng status:** logging/metrics phân loại 302, 401, 403, 429 và 5xx; phát hiện vòng lặp login hoặc đột biến token invalid.
- **Không rò token/session:** dùng HTTPS, không đưa Bearer token vào URL, query string, logs hoặc Location header. Kiểm CORS, referrer policy và cookie flags.
- **Không tiết lộ chi tiết thất bại:** body authentication failure không chứa password, token, account existence, stack trace, signing keys hoặc thông tin role nhạy cảm.
- **Không dùng HTML redirect cho API:** client không tương tác được với form login từ request JSON, dễ xảy ra 302→200 HTML khiến parser/SDK sai.
- **Không dùng 401 như toàn bộ quyền:** authenticated nhưng thiếu scope/tenant là lớp authorization khác; kiểm policy và 403 theo contract.
- **Không bỏ CSRF trên web session:** phân vùng chain theo credential đúng và test cả POST, không chỉ GET.
- **Giữ độ tin cậy của forwarded headers:** reverse proxy phải sanitize header từ client, backend chỉ tin proxy đã định nghĩa.
- **Thực thi authn/authz ở backend:** response chọn 302/401 là phần giao tiếp, không tự bảo vệ dữ liệu nếu endpoint bỏ qua filter hoặc chỉ kiểm ở frontend.

## 19. Câu hỏi tự kiểm tra

1. Vì sao HTTP 302 phù hợp cho top-level browser navigation nhưng có thể gây lỗi khi client `fetch` chờ JSON? Cho ví dụ 302 được follow đến HTML 200.
2. Tại sao tài nguyên API thiếu bearer token phải dùng 401 và `WWW-Authenticate: Bearer` thay vì chỉ trả 302 `Location: /login`?
3. Khi một JWT hợp lệ nhưng thiếu scope, vì sao phản hồi thường là 403 chứ không phải 401? Điều gì khác nếu JWT hết hạn?
4. `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và `AuthenticationFailureHandler` giải quyết những tình huống nào khác nhau?
5. Tại sao `securityMatcher("/api/**")` khác với `requestMatchers("/api/private")`? Điều gì xảy ra nếu không có chain bao phủ URL còn lại?
6. Một SPA gửi `Accept: text/html` tới `/api/profile`. Có nên redirect tới login không? Vì sao không chọn chính sách auth chỉ theo `Accept`?
7. Nếu custom entry point API trả JSON 401 nhưng xóa `WWW-Authenticate`, điều gì có thể sai với OAuth2 Bearer client?
8. Thiết kế test bảo đảm CSRF 403 của web POST không bị nhầm với 401 thiếu Bearer ở API.
9. Với login OIDC, vì sao browser có thể redirect tới IdP nhưng API Resource Server vẫn nên trả 401?
10. Khi app chạy sau reverse proxy, có những nguy cơ gì từ Location header, Host forwarding và saved request?

## 20. Tổng kết và tài liệu tham khảo

- **302 + Location**: thường dùng để hướng **browser navigation** chưa đăng nhập tới trang login. Đây là UX của ứng dụng web dùng form/session hoặc OIDC login.
- **401 + WWW-Authenticate**: phù hợp để yêu cầu **API client** cung cấp credentials theo scheme của API, ví dụ `Bearer`. Không trả HTML login thay vì challenge.
- **403**: thường dùng khi đã xác thực nhưng không được cấp quyền; không nên kích hoạt login loop.
- **AuthenticationEntryPoint** quyết định cách bắt đầu authentication; **AccessDeniedHandler** xử lý quyền bị từ chối; **AuthenticationFailureHandler** xử lý thất bại khi submit login.
- Tách `/api/**` và các trang web thành các `SecurityFilterChain` có matcher/order rõ, session/CSRF policy đúng, catch-all bảo vệ URL còn lại.
- Header `Accept`, `User-Agent` hoặc `X-Requested-With` không phải nguồn xác thực; đừng dùng chúng để đổi điều kiện bảo vệ.
- Test status **và headers** (Location, WWW-Authenticate) với cả browser, API client, token hợp lệ/không hợp lệ và trường hợp thiếu quyền.

**Tài liệu tham khảo chính thức:**

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 – Java Configuration và Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 – ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 – OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)