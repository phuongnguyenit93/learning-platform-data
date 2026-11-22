# Kết hợp giao diện dùng phiên với Resource Server ở hai chuỗi độc lập

> **Thực hành tổng hợp — Spring Security Servlet.** Bài xây dựng một ứng dụng Spring Boot 3.x, Java 17+ có **giao diện web dùng form login và HTTP session** và **REST API dùng OAuth2 Resource Server, Bearer JWT và xử lý stateless**. Hai đường đi sử dụng **hai `SecurityFilterChain` độc lập về matcher, cơ chế xác thực, session, CSRF, entry point và chính sách quyền**, nhưng vẫn nằm trong cùng ứng dụng Servlet. Các ví dụ và kiểm thử chỉ sử dụng tài khoản, token và URL thử nghiệm; không dùng credential hoặc khóa production.

## 1. Mục tiêu và bài toán thực tế

Giả sử cùng một Spring Boot app phục vụ hai nhóm client:

1. **Trình duyệt của nhân viên:** truy cập `/ui/**`, đăng nhập qua trang `/login`, duy trì đăng nhập bằng cookie `JSESSIONID`; trên các form POST cần CSRF token. Người dùng có role `USER` được truy cập trang cá nhân.
2. **Đối tác hoặc client API:** truy cập `/api/**` bằng header `Authorization: Bearer <access-token>`; JWT được xác minh bằng trusted public keys, issuer, audience và thời hạn. Mỗi request phải mang bearer token; API không sử dụng web session để xác thực.

Nếu cấu hình tất cả URL bằng một chuỗi filter chung, những lỗi phổ biến gồm: API trả **302 về trang login** thay vì **401 Bearer**, API vô tình dùng cookie phiên để vượt qua kiểm tra JWT, UI POST không có CSRF vẫn được phép, hoặc token từ client API lại được dùng như session login của nhân viên.

**Kết quả cần đạt:** một ứng dụng chạy được, không trộn hai cơ chế, có kiểm thử chứng minh cả những đường truy cập **phải bị từ chối**.

```text
                   Một Spring Boot Servlet app
                              |
                    FilterChainProxy chọn
                    CHUỖI KHỚP ĐẦU TIÊN
                              |
            +-----------------+------------------+
            |                                    |
     /api/**                                     /** (fallback)
     @Order(1)                                   @Order(2)
            |                                    |
   JWT Bearer token                       Form login / JSESSIONID
   OAuth2 Resource Server                 UserDetailsService
   STATELESS                               IF_REQUIRED session
   Không dùng session UI                   SecurityContext trong session
   CSRF tắt CHỈ tại /api/**                CSRF bật cho form/POST
   API 401/403 theo Bearer                 302 /login hoặc 403
            |                                    |
      /api/me, /api/actions                /ui/me, /ui/change
```

Không có hai application contexts hoặc hai cổng HTTP bắt buộc. Đây là **hai `SecurityFilterChain` trong cùng `FilterChainProxy`**, chọn dựa trên request. Cơ chế trong từng chain chỉ có hiệu lực khi request **khớp chain đó**.

## 2. Tách ranh giới đúng: securityMatcher khác requestMatchers

Đây là phân biệt quan trọng nhất.

- `http.securityMatcher("/api/**")` quyết định **cả chain** có áp dụng cho request hay không.
- `authorizeHttpRequests(...requestMatchers(...))` viết **quy tắc authorization bên trong chain đã được chọn**. Nó không làm chain tự chỉ chạy trên những URL đó.
- `@Order(1)` giúp API chain được xét **trước** chain giao diện.
- `@Order(2)` chạy như fallback `securityMatcher("/**")`, nên các đường không thuộc API vẫn được bảo vệ. Nếu không chain nào khớp, một URL có thể **không được Spring Security bảo vệ**; tránh cấu hình chỉ có hai securityMatcher hẹp mà bỏ sót endpoint mới.

Ví dụ đúng:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        // Cấu hình riêng cho API ở đây.
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/**")
        // Cấu hình riêng cho giao diện ở đây.
        .build();
}
```

Đoạn trên chỉ minh họa thứ tự/matcher, **chưa phải chương trình an toàn hoàn chỉnh**. Các section tiếp theo cung cấp đầy đủ các authorization rules, authentication, CSRF và session management.

Sai lầm hay gặp là đặt catch-all `securityMatcher("/**")` vào `@Order(1)`. Khi đó mọi request API bị chain giao diện bắt trước; bạn có thể nhận 302 login và không bao giờ đi qua Bearer filter của API. Không sửa bằng cách xóa `securityMatcher` API hoặc tắt security của UI; hãy sửa **matcher/order** và kiểm thử.

Một `SecurityFilterChain` độc lập không có nghĩa các bean bên trong context hoàn toàn cách ly. Chẳng hạn cả hai vẫn có thể sử dụng một `UserDetailsService`, một `AuthenticationManager` hoặc chung logging nếu bạn cấu hình như thế. Sự tách biệt cần được **thể hiện bằng matcher và các security config tương ứng**.

## 3. Chính sách cần viết rõ trước khi code

| Yêu cầu | Giao diện dùng session | API Resource Server |
|---|---|---|
| Đường URL | `/ui/**`, `/login`, `/logout` | `/api/**` |
| Chuỗi ưu tiên | Fallback `@Order(2)` | `@Order(1)` |
| Identity | Form username/password, sau đó `Authentication` lưu qua HTTP session | JWT bearer được kiểm tra trên **từng request** |
| Credential truyền | Cookie session tự động gửi bởi browser | Header `Authorization: Bearer ...` do client đặt |
| Session policy | `SessionCreationPolicy.IF_REQUIRED` | `SessionCreationPolicy.STATELESS` |
| SecurityContext persistence | Session-based context mặc định của web login | Không lấy/lưu context vào HTTP session |
| CSRF | **Bật** cho thay đổi trạng thái qua browser/cookie | Có thể tắt **chỉ trong API thuần bearer** |
| Request cache | Có thể lưu URL trước login | Tắt redirect/saved request của browser |
| Không authenticated | Redirect `/login` (trình duyệt) | 401 với Bearer challenge |
| Authenticated nhưng thiếu quyền | 403 | 403 |
| Logout | POST `/logout` với CSRF, invalidate web session | Không có “logout JWT” tự động; dùng TTL/revocation riêng |
| Quyền | `ROLE_USER` | `SCOPE_api.read`, `SCOPE_api.write` |
| Cơ chế mặc định khi URL không khớp | Deny by default | API chain không áp dụng ngoài `/api/**` |

**Quy tắc biên quan trọng:** Browser có thể vẫn **gửi cookie `JSESSIONID` tới `/api/**`** nếu cookie path/domain bao phủ API. Điều này không có nghĩa API chấp nhận session: API chain phải **bỏ qua session context**. Trong test cần chứng minh “session-only API request → 401”. Tách biệt matcher không tự quyết định cookie path của browser.

### 3.1. Khi nào API được phép tắt CSRF?

CSRF là rủi ro khi browser **tự động đính kèm credential** với một cross-site request (điển hình là cookie session). Với API chỉ xác thực **bearer token được client chủ động đặt trong Authorization header** và không chấp nhận cookie/Basic browser auto credentials, có thể tắt CSRF trong **API chain**. Nhưng nếu API dùng cả cookie session, HTTP Basic tự động hoặc cơ chế credential browser gửi ngầm, **không kết luận CSRF vô hại** chỉ vì URL bắt đầu bằng `/api`.

Trong thiết kế dưới đây, API được cấu hình rõ là **stateless JWT Bearer only**; `csrf.disable()` chỉ được gọi trong API chain. Chain UI giữ CSRF mặc định. Cookie `SameSite` và CORS **không thay thế** CSRF protection cho giao diện.

## 4. Công cụ và cấu trúc dự án thực hành

Sử dụng Java 17, Spring Boot **3.3.5**, Spring Security tương ứng do Spring Boot dependency management lựa chọn, Gradle và JUnit 5. Đây là phiên bản **cụ thể cho dự án mẫu**, không khẳng định bản mới nhất. Dùng Gradle Wrapper cùng dự án.

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cây tệp cần tạo:

```text
src/
  main/
    java/demo/dualchain/
      DualChainApplication.java
      SecurityConfig.java
      ApiOperations.java
      DemoController.java
    resources/
      application.yml
  test/
    java/demo/dualchain/
      DualChainSecurityTest.java
      ApiOperationsTest.java
```

Mẫu cung cấp một web user **in-memory chỉ để học tập** với password được truyền qua cấu hình runtime `DEMO_WEB_PASSWORD`, không hardcode production credential. JWT verifier dùng một JWKS URL cố tình không hoạt động (`.invalid`) để tránh gọi IdP thật; **MockMvc sẽ stub JwtDecoder để kiểm mapping/authorization**, không kiểm signature. Khi triển khai thật phải thay issuer/JWKS/audience bằng giá trị của môi trường và bổ sung signed-token integration tests.

## 5. application.yml và Spring Boot entry point

`src/main/resources/application.yml`:

```yaml
demo:
  jwt:
    issuer: "https://id.example.invalid/"
    audience: "demo-api"
    jwks-uri: "https://id.example.invalid/jwks.json"

server:
  servlet:
    session:
      timeout: 30m
```

`demo.jwt.issuer` và `demo.jwt.jwks-uri` là giá trị **không hoạt động** nhằm học cấu hình. Không tạo một JWT giả rồi kỳ vọng resource server này chấp nhận nó ngoài test. Ứng dụng khởi động được, nhưng với URL JWKS này request Bearer token thực sẽ không xác minh được.

`src/main/java/demo/dualchain/DualChainApplication.java`:

```java
package demo.dualchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualChainApplication.class, args);
    }
}
```

Các chuỗi URL ở ví dụ là HTTP local. Khi đưa web login lên mạng thật, cần HTTPS, session cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, proxy awareness và cơ chế giám sát. Đừng bật cookie `Secure` cho một môi trường chỉ thử HTTP trên localhost rồi cho rằng trình duyệt sẽ gửi cookie bình thường; cấu hình production riêng và kiểm tra thực tế qua TLS.

## 6. Hai SecurityFilterChain: đầy đủ cấu hình, đúng phạm vi

`src/main/java/demo/dualchain/SecurityConfig.java`:

```java
package demo.dualchain;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    // Demo web account ONLY. Production phải dùng user store/IdP riêng.
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService webUsers(
            PasswordEncoder encoder,
            @Value("${DEMO_WEB_PASSWORD}") String password) {
        if (password.isBlank() || password.length() < 12) {
            throw new IllegalStateException(
                "Local web demo credential is missing or invalid");
        }

        UserDetails user = User.withUsername("webuser")
            .password(encoder.encode(password))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(user);
    }

    // Token validation thật của Resource Server khi không mock JwtDecoder.
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${demo.jwt.jwks-uri}") String jwksUri,
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRule = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Required API audience missing", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceRule));
        return decoder;
    }

    // CHAIN 1: API /api/** chỉ nhận Bearer token, không dùng web session.
    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/actions")
                    .authenticated()
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    // CHAIN 2: Fallback web UI; form login + cookie-backed session + CSRF.
    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/ui/**").hasRole("USER")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true))
            .build();
    }
}
```

### 6.1. Tại sao API chain không nhận session?

`SessionCreationPolicy.STATELESS` khiến Spring Security không tạo/không dùng `HttpSession` để lấy `SecurityContext` cho API. `NullSecurityContextRepository` trong demo làm rõ rằng context của bearer request **không được lưu hoặc lấy từ web session**. `requestCache.disable()` tránh cơ chế saved-request/redirect của trình duyệt trong API.

Bearer token được đọc trên mỗi request qua `BearerTokenAuthenticationFilter` rồi chuyển tới `JwtAuthenticationProvider`/`JwtDecoder`. Với JWT tự chứa, token đủ điều kiện sẽ tạo `JwtAuthenticationToken` cho request đó; request tiếp theo **không thừa hưởng authentication từ session UI**.

Lưu ý: **stateless** không có nghĩa “server hoàn toàn không có cache”: decoder/JWKS cache, connection pools, ứng dụng business cache hoặc policy stores vẫn có thể tồn tại. Nó chỉ nói rõ **auth state của request API không dựa vào HTTP session** trong chain này.

### 6.2. Tại sao chain UI giữ session và CSRF?

Giao diện dùng `UsernamePasswordAuthenticationFilter` (form login); sau khi xác thực password bằng `PasswordEncoder`/`UserDetailsService`, context có thể được lưu trong HTTP session. Request sau mang cookie `JSESSIONID` để được nhận là cùng web user.

`SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi cần; `formLogin()` tạo trang login mặc định để demo không cần HTML template. `csrf(Customizer.withDefaults())` giữ chống CSRF cho request thay đổi trạng thái, gồm `POST /ui/change` và `POST /logout`; **GET** không nên thay đổi dữ liệu.

`logout()` chủ yếu xóa đăng nhập của **web session**. Nó **không tự thu hồi access JWT** của client API; JWT tự chứa có thể tiếp tục hợp lệ tới hết hạn hoặc bị thu hồi bởi cơ chế riêng.

### 6.3. Tại sao vẫn cần method security?

`@EnableMethodSecurity` đảm bảo các `@PreAuthorize` trên business service được thực thi khi gọi qua Spring-managed bean. URL chain yêu cầu `authenticated()` cho API, còn service có thể yêu cầu **scope hẹp hơn**. Nếu gọi service bằng `new` hoặc self-invocation bỏ qua proxy, authorization method có thể không được áp dụng. Bài test sẽ dùng bean được Spring inject, không dùng object tự tạo.

Nếu hệ thống có các method dùng chung giữa UI và API, đừng tự đặt `hasRole('USER')` để thỏa mọi client; cần mô hình quyền thống nhất, scope/role mapping chính xác và kiểm tra quyền tài nguyên.

## 7. Tạo business service và controller phân biệt UI/API

`src/main/java/demo/dualchain/ApiOperations.java`:

```java
package demo.dualchain;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ApiOperations {
    @PreAuthorize("hasAuthority('SCOPE_api.read')")
    public String read() {
        return "api-read-ok";
    }

    @PreAuthorize("hasAuthority('SCOPE_api.write')")
    public String write() {
        return "api-write-ok";
    }
}
```

`SCOPE_api.read` và `SCOPE_api.write` được tạo bởi `JwtGrantedAuthoritiesConverter` mặc định khi verified JWT có `scope: "api.read"` hoặc `scope: "api.write"`. UI session chỉ có `ROLE_USER`; không có `SCOPE_api.read` trừ khi bạn cố ý cấp thông qua policy khác.

`src/main/java/demo/dualchain/DemoController.java`:

```java
package demo.dualchain;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final ApiOperations api;

    public DemoController(ApiOperations api) {
        this.api = api;
    }

    @GetMapping("/")
    public String home() {
        return "Two security chains: /ui/** and /api/**";
    }

    @GetMapping("/ui/me")
    public Map<String, String> webMe(Authentication authentication) {
        return Map.of(
            "mode", "session",
            "user", authentication.getName());
    }

    // Bài tập giả lập thay đổi trạng thái; không ghi dữ liệu thật.
    @PostMapping("/ui/change")
    public String changeWebSettings() {
        return "ui-change-ok";
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Authentication authentication) {
        return Map.of(
            "mode", "bearer",
            "subject", authentication.getName(),
            "result", api.read());
    }

    @PostMapping("/api/actions")
    public String writeApi() {
        return api.write();
    }
}
```

Đây là một demo chức năng; sản phẩm thực cần DTO, validation, error responses, audit và object-level authorization. `user`/`subject` có thể là dữ liệu cá nhân; không đưa principal không cần thiết ra response production.

### 7.1. Vì sao endpoint API GET authenticated rồi vẫn có thể trả 403?

Tại URL, API chain chỉ kiểm `authenticated()`. Nhưng `api.read()` được proxy method-security kiểm `SCOPE_api.read`. Token được xác thực thành công nhưng chỉ có `SCOPE_api.write` sẽ bị **403 Forbidden** tại tầng method security khi gọi GET; đó là hành vi mong muốn. Cần tách lỗi **không xác thực được token (401)** với lỗi **đã xác thực nhưng scope không đủ (403)**.

Ngược lại, `/ui/me` yêu cầu `hasRole("USER")` trong web chain, dựa trên `ROLE_USER` do form login phát. Một bearer token có scope API không mặc nhiên được xem là web user.

## 8. Kiểm thử MockMvc: chứng minh hai chain không “mượn” danh tính nhau

Để có kiểm thử đáng tin, cần kiểm tra **allow** và **deny** cho cả hai cơ chế. `@AutoConfigureMockMvc` giữ Spring Security filters hoạt động; không dùng `addFilters=false` hoặc `MockMvcBuilders.standaloneSetup(...)` thiếu `springSecurity()` khi muốn kiểm filter chain.

**Quan trọng về phạm vi:** test dưới đây dùng `@MockBean JwtDecoder` để mô phỏng kết quả decode nhằm tập trung vào **chain selection, Bearer authentication plumbing, authority mapping, UI session và CSRF**. Do decoder bị mock, **chữ ký JWT/JWKS và issuer/audience validators không được thực thi** trong các request test đó. Mục 11 trình bày test thật bằng issuer/JWKS riêng.

`src/test/java/demo/dualchain/DualChainSecurityTest.java`:

```java
package demo.dualchain;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "DEMO_WEB_PASSWORD=local-test-browser-password"
})
@AutoConfigureMockMvc
class DualChainSecurityTest {
    @Autowired MockMvc mvc;

    // Trong lớp này chỉ mock decoder để kiểm định routing + authority mapping.
    @MockBean JwtDecoder jwtDecoder;

    private Jwt fixture(String value, String subject, String scope) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .subject(subject)
            .claim("iss", "https://id.example.invalid/")
            .claim("aud", List.of("demo-api"))
            .claim("scope", scope)
            .issuedAt(Instant.now().minusSeconds(60))
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @BeforeEach
    void stubJwtDecoder() {
        when(jwtDecoder.decode("read-token")).thenReturn(
            fixture("read-token", "api-reader", "api.read"));
        when(jwtDecoder.decode("write-token")).thenReturn(
            fixture("write-token", "api-writer", "api.write"));
        when(jwtDecoder.decode("other-token")).thenReturn(
            fixture("other-token", "api-other", "api.other"));
    }

    private MockHttpSession loggedInWebSession() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "webuser")
                .param("password", "local-test-browser-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void webWithoutSessionRedirectsToLogin() throws Exception {
        mvc.perform(get("/ui/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void formLoginSessionCanAccessUi() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(get("/ui/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("session"))
            .andExpect(jsonPath("$.user").value("webuser"));
    }

    @Test
    void webSessionAloneCannotAuthenticateApi() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithoutBearerReturns401NotLoginRedirect() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerReadTokenCanReadApi() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("bearer"))
            .andExpect(jsonPath("$.subject").value("api-reader"))
            .andExpect(jsonPath("$.result").value("api-read-ok"));
    }

    @Test
    void bearerTokenWithoutReadScopeGets403() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer other-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void bearerTokenAloneCannotOpenSessionUi() throws Exception {
        mvc.perform(get("/ui/me")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void webPostWithoutCsrfIsRejected() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/ui/change").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void webPostWithCsrfIsAllowed() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/ui/change")
                .session(session).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("ui-change-ok"));
    }

    @Test
    void apiPostWithBearerNeedsNoCookieCsrfToken()
            throws Exception {
        mvc.perform(post("/api/actions")
                .header("Authorization", "Bearer write-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-write-ok"));
    }

    @Test
    void bearerWithoutWriteScopeCannotPost() throws Exception {
        mvc.perform(post("/api/actions")
                .header("Authorization", "Bearer read-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void webLogoutIsProtectedByCsrf() throws Exception {
        MockHttpSession session = loggedInWebSession();
        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());
        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Đọc từng nhóm test:**

- `webWithoutSessionRedirectsToLogin` cho thấy UI dùng browser authentication entry point, không trả JSON Bearer 401.
- `formLoginSessionCanAccessUi` chứng minh sau form login, `SecurityContext` được lưu trong web session và request tiếp theo có thể sử dụng session.
- `webSessionAloneCannotAuthenticateApi` là ca rất quan trọng: dù gửi cùng `MockHttpSession` vào `/api/me`, API chain **vẫn yêu cầu JWT** và trả 401.
- `apiWithoutBearerReturns401NotLoginRedirect` phát hiện chain bị bắt nhầm: nếu trả 302, hãy kiểm `@Order` và `securityMatcher`.
- `bearerReadTokenCanReadApi`/`bearerTokenWithoutReadScopeGets403` cho thấy JWT được giải mã bởi stub, scopes trở thành `SCOPE_api.read`, method security kiểm quyền.
- `bearerTokenAloneCannotOpenSessionUi` chứng minh API token không tự tạo browser session ở web chain.
- `webPostWithoutCsrfIsRejected` và `webPostWithCsrfIsAllowed` xác minh CSRF chỉ được bật đúng ở web.
- `apiPostWithBearerNeedsNoCookieCsrfToken` là trường hợp chấp nhận được **chỉ theo giả định API chỉ dùng bearer header**, không chấp nhận browser-cookie authentication.
- `webLogoutIsProtectedByCsrf` bảo đảm POST logout cũng là action có CSRF protection.

Một `403` do thiếu CSRF có thể xuất hiện trước method security. Muốn kiểm scope/role của POST web, test phải có `with(csrf())` hợp lệ trước khi xét quyền; còn POST API thuần bearer không dùng cookie nên demo tắt CSRF ở chain API.

## 9. Test method security riêng để không nhầm với filter hoặc JWT

`src/test/java/demo/dualchain/ApiOperationsTest.java`:

```java
package demo.dualchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = {
    "DEMO_WEB_PASSWORD=local-test-browser-password"
})
class ApiOperationsTest {
    @Autowired ApiOperations api;

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void matchingScopeAllowsRead() {
        assertEquals("api-read-ok", api.read());
    }

    @Test
    @WithMockUser(roles = "USER")
    void webUserRoleDoesNotImplyApiScope() {
        assertThrows(AccessDeniedException.class, api::read);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.write")
    void writeScopeAllowsWrite() {
        assertEquals("api-write-ok", api.write());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void readScopeDoesNotAllowWrite() {
        assertThrows(AccessDeniedException.class, api::write);
    }
}
```

`@WithMockUser` chỉ đặt `Authentication` test vào context, **không** gửi HTTP request, **không** chạy API chain và **không** giải mã/chứng thực JWT. Đây là test riêng cho `@PreAuthorize`. Khi test method pass nhưng test HTTP API fail, nên kiểm bearer filter, decoder, scope converter hoặc chain routing, thay vì vô hiệu hóa method security.

Lệnh chạy trong dự án có Gradle Wrapper:

```bash
./gradlew test
./gradlew test --tests demo.dualchain.DualChainSecurityTest
./gradlew test --tests demo.dualchain.ApiOperationsTest
```

Không áp đặt stdout Gradle cố định vì wrapper, JDK, cache và runner khác nhau. Một test mong đợi 401/403 là **PASS** khi request thực sự bị từ chối đúng nơi.

## 10. Chạy local và hiểu giới hạn của JWT demo

Trong Bash, dùng mật khẩu **chỉ dành cho máy local**:

```bash
export DEMO_WEB_PASSWORD='local-test-browser-password'
./gradlew bootRun
```

Trên PowerShell cần cú pháp biến môi trường tương ứng. Khi chưa cấp `DEMO_WEB_PASSWORD`, ứng dụng phải thất bại startup do thiếu required property; **không có default production password**.

Các request quan sát được **không cần secret**:

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/ui/me
curl -i http://localhost:8080/api/me
```

Kỳ vọng với cấu hình mặc định của demo:

- `GET /` → 200, thông điệp giới thiệu hai chain.
- `GET /ui/me` chưa login → 302 hướng tới trang `/login`.
- `GET /api/me` không Bearer → 401, không phải redirect tới login web.

Để thử form login bằng browser, mở `http://localhost:8080/ui/me`, được chuyển đến trang `/login` mặc định rồi nhập username `webuser` và password local đã cấu hình. Khi đăng nhập, browser nhận cookie session và truy cập UI. Không dùng HTTP thông thường cho credential trên một mạng thật; môi trường triển khai dùng TLS.

Các token `read-token`/`write-token` trong test **không phải JWT thật**. Vì config issuer/JWKS có domain `.invalid`, gửi:

```bash
curl -i -H 'Authorization: Bearer read-token' \
  http://localhost:8080/api/me
```

sẽ **không** được xác thực bằng decoder thật; thông thường không trả 200 (có thể dẫn tới lỗi decode hoặc kết nối JWKS tùy cấu hình). Đây là chủ đích để không nhận nhầm token giả như access token được ký. Chỉ sau khi cấu hình một **test authorization server/JWKS đáng tin** và có signed token thật cho audience `demo-api`, Bearer request mới có thể thành công.

**Không đặt access token thật vào command line**, terminal history, CI log hoặc tài liệu. Dùng cơ chế truyền credential an toàn của môi trường kiểm thử.

## 11. Test chữ ký JWT, issuer, audience và claims ngoài MockMvc stub

Mock `JwtDecoder` có giá trị cho **chain selection + converter + authorization**, nhưng không kiểm tra cryptography. Bổ sung integration test với JWT **được ký bởi test private key**, JWKS test endpoint và **decoder thật** (không dùng `@MockBean JwtDecoder`).

Ma trận nên có:

| Tình huống | Kỳ vọng |
|---|---|
| JWT test ký đúng trusted JWKS, issuer và audience đúng, `scope=api.read` | GET `/api/me` được 200 |
| JWT không có/sai chữ ký | 401 |
| JWT issuer không khớp configured issuer | 401 |
| JWT có audience của API khác | 401 |
| JWT hết hạn hoặc chưa tới `nbf` ngoài clock skew | 401 |
| JWT valid nhưng chỉ có `api.other` | 403 ở `/api/me` |
| JWT valid có `api.read` nhưng không `api.write` | 403 ở `POST /api/actions` |
| JWT valid đúng scope nhưng resource thuộc tenant khác | Từ chối theo business rule bổ sung |
| Browser session có `ROLE_USER` nhưng API không có bearer | 401 bất kể cookie |

Với signed JWT, `JwtDecoder` phải xác minh signature, thuật toán được phép, issuer, time và audience. Trong code `SecurityConfig`, `JwtValidators.createDefaultWithIssuer` và audience validator bảo vệ các claims được yêu cầu; source JWKS vẫn phải thuộc trust configuration. Chỉ nhìn `scope` trên JWT chưa verify là **không an toàn**.

Ngoài ra, JWT tự chứa có thể giữ scopes/roles cũ cho tới hết hạn, dù user bị thu hồi quyền tại IdP. Với quyền nhạy cảm, cần token TTL/revocation/introspection hoặc policy lookup theo security requirement. Session UI và JWT API có **vòng đời thu hồi khác nhau**; invalidate session không tự vô hiệu JWT đã cấp.

## 12. Nếu giao diện muốn dùng OIDC login thay form login

Demo dùng form login để chạy offline không cần IdP. Trong sản phẩm thật, UI thường dùng `oauth2Login()`/OIDC cho browser; **mô hình hai chain vẫn giữ nguyên**:

- API chain `securityMatcher("/api/**")` tiếp tục làm `oauth2ResourceServer().jwt()`, `STATELESS` và không lấy UI session.
- UI chain `securityMatcher("/**")` đổi `formLogin(...)` thành `oauth2Login(...)`, giữ session và CSRF; cấu hình OAuth2 Client Registration, authorization code flow, redirect URI/callback và client secret server-side nếu là confidential client.
- UI tạo `OAuth2AuthenticationToken`/`OidcUser` trong session, API tạo `JwtAuthenticationToken` từ bearer token. Các authorities/claims mappers của hai luồng **khác nhau**, không tự dùng chung `JwtAuthenticationConverter`.
- Callback endpoint như `/login/oauth2/code/{registrationId}` và đường `/oauth2/authorization/{registrationId}` phải rơi vào **UI chain**, không bị API chain bắt trước.
- API không được chấp nhận **OIDC ID token** thay access token dành cho API; validate `aud`/issuer/scope của access token.
- Logout UI session có thể cần thêm OIDC RP-Initiated Logout/back-channel logout theo hợp đồng IdP; không đồng nghĩa revoke bearer access token.

Cấu hình **minh họa** cho client khi có `spring-boot-starter-oauth2-client` và IdP đã đăng ký:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          staff:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Đoạn YAML này là **phần thay thế định hướng cho triển khai có IdP**, không phải một file có thể thả ngay vào demo form-login rồi kỳ vọng mọi test vẫn chạy. Cần đổi dependencies, UI chain, tests và authorities mapping tương ứng. `OIDC_CLIENT_SECRET` không được đưa vào JavaScript/SPA, log hoặc source control. Với public clients, cần Authorization Code + PKCE, không dùng client secret nhúng trong browser.

## 13. CSRF, CORS, cookies và header: không nhầm chức năng

### 13.1. CSRF

CSRF bảo vệ request khi browser tự đính kèm session cookie hoặc credential tương tự. UI chain giữ CSRF, nên `POST /ui/change` phải có token hợp lệ. Với ứng dụng server-rendered, gắn CSRF token vào form theo cơ chế Spring MVC/template engine phù hợp. Một `403` trên POST không có token **không chứng minh** role sai.

API thuần bearer trong header chủ động và stateless có thể disable CSRF trong riêng API chain. Nếu chuyển API sang dùng cookie hay credential browser auto-send, phải **đánh giá lại**; không copy nguyên `csrf.disable()` sang web chain.

### 13.2. CORS

CORS kiểm soát browser JavaScript từ origin nào được đọc response và gửi một số request cross-origin, **không phải authentication hay authorization**. CORS không cho phép một token sai chữ ký trở thành đúng. Nếu một SPA ở origin khác gọi API, cấu hình allowed origins/methods/headers theo client đáng tin và kiểm tra preflight `OPTIONS`; đừng mở `*` bừa bãi khi dùng credentials. Demo không thiết lập CORS vì các request học tập dùng cùng origin/MockMvc.

### 13.3. Cookies và SameSite

`JSESSIONID` là credential của **web session**, cần cấu hình `HttpOnly`, `Secure` khi chạy HTTPS và `SameSite` theo flow login thực tế. Cookie có thể được gửi tới `/api/**` tùy path/domain, nhưng API chain vẫn **không được xác thực từ session**. Nếu đòi cách ly mạnh hơn theo threat model, cân nhắc tách origin/subdomain hoặc deployment, nhưng vẫn phải bảo vệ reverse proxy, path rewrite và cookie scope.

### 13.4. CSP và bảo vệ UI

Giao diện dùng session còn cần XSS protection, output encoding, Content Security Policy phù hợp, chống clickjacking và session fixation. XSS trên cùng origin có thể thực hiện hành động của user ngay cả khi có CSRF token; CSRF không thay XSS protection. API bearer token lưu trong JS cũng chịu rủi ro XSS, nên phải cân nhắc token storage và frontend architecture.

## 14. Những lỗi cấu hình thường gặp

**Lỗi 1 — Catch-all ở @Order(1).** `/**` bắt API trước `/api/**`, dẫn tới redirect login 302 thay vì bearer 401. Đặt API trước và fallback sau.

**Lỗi 2 — Chỉ dùng requestMatchers("/api/**") mà không có securityMatcher.** Rule có thể chỉ kiểm URL trong một chain chứa cả formLogin và resource server; các filter vẫn có cơ hội tham gia request ngoài ý muốn. Tách chain bằng securityMatcher đúng.

**Lỗi 3 — Chỉ tạo chain cho UI và API mà không có fallback.** Endpoint mới không khớp chain nào có thể không được bảo vệ. Dùng `/**` fallback với `denyAll` cho URL không chủ ý.

**Lỗi 4 — Cho API dùng HttpSession.** Cookie UI vô tình có thể làm API nhận identity trái contract. Dùng STATELESS và repository không lưu/tải context trong API; có test “session-only → 401”.

**Lỗi 5 — Tắt CSRF toàn ứng dụng.** UI cookie-authenticated POST mất bảo vệ. Tắt ở API thuần bearer nếu threat model phù hợp, giữ web CSRF.

**Lỗi 6 — Bỏ session trên UI để “tất cả stateless”.** Form login không còn lưu bối cảnh giữa các requests, dẫn tới login loop. UI cần IF_REQUIRED và session context phù hợp.

**Lỗi 7 — Resource Server trả 302 login.** Chain/entry point bị trộn; API nên trả 401 khi không authenticated bằng bearer.

**Lỗi 8 — Dùng JWT scope như role.** `hasRole('api.read')` thường đòi `ROLE_api.read`; converter default tạo `SCOPE_api.read`. Dùng `hasAuthority('SCOPE_api.read')` hoặc contract mapping nhất quán.

**Lỗi 9 — Test API bằng @WithMockUser rồi tin JWT đã được xác minh.** Annotation có thể bỏ qua JWT decoder. Test converter/filter và signed-token validation riêng.

**Lỗi 10 — Dùng ID token OIDC của login UI làm API access token.** Kiểm token type, audience, issuer và scopes đúng Resource Server contract.

**Lỗi 11 — Quên method-security proxy.** Không bật `@EnableMethodSecurity` hoặc gọi service bằng `new` làm `@PreAuthorize` không chạy. Inject bean Spring và test deny case.

**Lỗi 12 — API POST thiếu CSRF nhưng test vẫn 403.** Có thể do thiếu `SCOPE_api.write`, JWT invalid hoặc sai chain. Xem tầng phát 403 trước khi thay CSRF policy.

**Lỗi 13 — Logout UI làm tất cả JWT hết hạn.** `/logout` chỉ quản lý web session theo demo, không revoke tokens stateless. Cần TTL/revocation riêng.

**Lỗi 14 — Đặt JWT private key tại Resource Server.** Resource Server xác minh JWT bất đối xứng qua public JWKS; không cần chia sẻ signing private key của IdP.

**Lỗi 15 — Thiếu audience validator.** Token đúng chữ ký nhưng phát cho API khác có thể bị chấp nhận sai. Kiểm `aud` cho API thực tế.

**Lỗi 16 — Bỏ kiểm tra CORS/preflight khi gọi từ SPA khác origin.** HTTP OPTIONS có thể bị 401 do API chain, nhưng không nên tắt authentication của mọi method để sửa. Cấu hình CORS trong scope phù hợp, giữ bearer authorization cho request thực.

**Lỗi 17 — Không xét request path sau proxy.** Gateway thêm/xóa `/api` prefix có thể khiến chain selection lệch. Test đúng path/servletPath thực nhận trong Spring app.

**Lỗi 18 — Dùng một JWT/SecurityContext cho nhiều request sau logout.** JWT đã phát tự chứa vẫn có thể hợp lệ; session logout và JWT revocation là hai phạm vi khác nhau.

## 15. Ma trận nghiệm thu trước khi triển khai

| Ca thử | Input | Kỳ vọng |
|---|---|---|
| UI anonymous | GET `/ui/me` không session | 302 hướng login |
| UI login | POST `/login` đúng credential + CSRF | 302 rồi session được tạo |
| UI authenticated | GET `/ui/me` với session | 200 |
| UI POST thiếu CSRF | POST `/ui/change` với session, không token | 403 |
| UI POST có CSRF | Session + CSRF hợp lệ | 200 |
| UI logout thiếu CSRF | POST `/logout` với session | 403 |
| API anonymous | GET `/api/me` không bearer | 401, **không** redirect |
| API có session UI, không bearer | GET `/api/me` với JSESSIONID | 401 |
| API đúng bearer + scope read | GET `/api/me` | 200 |
| API bearer thiếu scope read | GET `/api/me` | 403 |
| API bearer + scope write | POST `/api/actions`, không session | 200 trong mô hình API bearer-only |
| API bearer thiếu scope write | POST `/api/actions` | 403 |
| Bearer token gửi vào UI không session | GET `/ui/me` | 302 login |
| JWT wrong issuer/audience | Token có chữ ký hợp lệ nhưng claim sai | 401 trong signed-token test thực |
| JWT bad signature/expired | Bearer token không hợp lệ | 401 |
| URL không được khai báo | GET `/internal/unlisted` | Từ chối theo fallback policy |
| Thay đổi quyền | JWT cũ/session cũ sau revoke | Theo TTL/revocation SLA đã định |
| Hệ thống đa tenant | Token đúng scope nhưng sai resource tenant | 403 theo business authorization |

Các case chỉ MockMvc với `@MockBean JwtDecoder` chứng minh routing/authorization, còn case JWT signature phải có decoder/test keys thật. Không coi một bộ test xanh là bằng chứng SSL, proxy và token revocation ngoài phạm vi đã chạy.

### Checklist cuối cùng

- [ ] API chain có `@Order(1)`, `securityMatcher("/api/**")` và Bearer JWT.
- [ ] UI fallback có `@Order(2)`, `securityMatcher("/**")`, form login/session và CSRF.
- [ ] Không route nào nằm ngoài mọi security chain; fallback deny-by-default.
- [ ] API dùng `STATELESS` và không đọc/ghi `SecurityContext` vào web `HttpSession`.
- [ ] Cùng một cookie web được gửi tới API **không** làm API authenticated.
- [ ] Chỉ disable CSRF cho API nếu API thực sự không nhận browser-auto credentials.
- [ ] UI POST và logout yêu cầu CSRF token hợp lệ.
- [ ] API trả 401 khi thiếu/invalid bearer; UI anonymous chuyển login đúng entry point.
- [ ] `SCOPE_` được kiểm bằng `hasAuthority`; `ROLE_` được dùng nhất quán cho UI role.
- [ ] `@EnableMethodSecurity` hoạt động trên Spring-managed business beans.
- [ ] JWT xác minh chữ ký, issuer, audience, time; tests có ca signature sai khi dùng decoder thực.
- [ ] Client secret, signing keys, session cookies và credentials được quản lý theo environment, không log.
- [ ] Có test allow/deny cho cả UI, API, CSRF, chain order và session isolation.
- [ ] Hiểu rằng logout web session **không tự revoke** access JWT.
- [ ] CORS, headers, cookie flags, TLS, proxy rewrite, IdP và revocation được kiểm thử tại môi trường phù hợp.

## 16. Kết luận

Hai `SecurityFilterChain` giải quyết vấn đề **chọn đúng cơ chế bảo mật theo loại request**. Chain `/api/**` được xét trước, xác thực **Bearer JWT stateless**, không dùng web session và chỉ tắt CSRF khi có lý do về threat model. Chain fallback `/**` xử lý **giao diện form login dùng session**, bảo vệ request thay đổi trạng thái bằng CSRF và tạo trải nghiệm redirect login cho browser.

Bằng chứng quan trọng nhất không chỉ là **UI login được** và **API bearer 200**, mà còn là các ca **không thể dùng phiên UI vào API**, **không thể dùng Bearer JWT làm browser login**, **API thiếu token không bị redirect**, **POST UI thiếu CSRF bị chặn**, và **scope/role không đúng phải bị từ chối**. Khi những điều đó được kiểm chứng bằng cả test MockMvc lẫn signed-token integration tests thích hợp, kiến trúc hỗn hợp session + Resource Server mới có ranh giới rõ ràng và khả năng vận hành an toàn.