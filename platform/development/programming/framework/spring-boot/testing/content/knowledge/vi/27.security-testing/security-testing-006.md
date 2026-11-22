# JWT, opaque token, OAuth2 Login và các công cụ mô phỏng tương ứng

## 1. Bài toán bảo mật cần kiểm thử

Một ứng dụng Spring Boot có thể đồng thời có REST APIs được bảo vệ bởi Bearer access token và giao diện web được bảo vệ bởi OAuth 2.0 Login. Các request nhìn bề ngoài đều có “người dùng đã xác thực”, nhưng **cơ chế, đối tượng Authentication, cách nhận scope và điểm tin cậy** khác nhau đáng kể:

- **JWT Resource Server**: nhận `Authorization: Bearer ...`, giải mã/kiểm tra JWT (chữ ký, thời hạn, issuer, audience nếu cấu hình), chuyển claims/scopes thành `JwtAuthenticationToken` và authorities.
- **Opaque Token Resource Server**: nhận Bearer token dạng chuỗi; gọi `OpaqueTokenIntrospector` để xác minh token và lấy attributes/authorities. Thông thường không tự kiểm tra chữ ký JWT trong nhánh này.
- **OAuth2 Login**: ứng dụng làm OAuth2 client, chuyển hướng browser tới Identity Provider, nhận authorization code, đổi code lấy token và thiết lập phiên đăng nhập (`OAuth2AuthenticationToken`, `OAuth2User`); khi dùng OpenID Connect, có `OidcUser` và ID token.

Viết một test sử dụng `@WithMockUser` cho mọi trường hợp là **sai mức trừu tượng** nếu controller thật cần `Jwt`, `BearerTokenAuthentication`, `OAuth2User` hoặc `OidcUser`. `@WithMockUser` tạo `UsernamePasswordAuthenticationToken` và Spring Security User principal giả, không tự tạo các OAuth2 authentication types.

Bài này thuộc nhóm **Bảo mật** và giải quyết trực tiếp đề mục **“JWT, opaque token, OAuth2 Login và các công cụ mô phỏng tương ứng”**. Ta học hai tầng test khác nhau:

1. **Mock SecurityContext**: dùng `jwt()`, `opaqueToken()`, `oauth2Login()` hoặc `oidcLogin()` từ `spring-security-test` để thử authorization, controller và principal mapping **mà không thực sự xác minh token/code**.
2. **Đi qua authentication filter**: gửi header `Authorization: Bearer ...` tới MockMvc, dùng Mockito `@MockBean JwtDecoder` hoặc `@MockBean OpaqueTokenIntrospector` để kiểm chứng filter gọi decoder/introspection và xử lý thành công/thất bại. Đây vẫn không phải bài test cryptographic validation hoặc gọi Identity Provider thật.

### Mục tiêu

Sau bài học, bạn có thể:

- Chọn đúng công cụ test cho JWT, opaque token, OAuth2 Login và OIDC Login.
- Phân biệt `Authentication`, principal, `GrantedAuthority`, claims, attributes, scopes, roles và các token types.
- Viết tests với `MockMvc`, `jwt()`, `opaqueToken()`, `oauth2Login()` và `oidcLogin()`.
- Phân biệt request không đăng nhập (401/redirect), đăng nhập thiếu scope (403) và request hợp lệ (200).
- Mô phỏng token có `sub`, `scope` và authority `SCOPE_reports.read`.
- Dùng `@MockBean` của Spring Boot 3.3 để thay `JwtDecoder`/`OpaqueTokenIntrospector` trong application context test.
- Giữ thật `SecurityFilterChain`, phân tuyến JWT/opaque/login qua `securityMatcher` và kiểm tra đúng filter.
- Hiểu ranh giới của mock: `jwt()` không kiểm tra chữ ký/`exp`/`iss`/`aud` và `oauth2Login()` không thực hiện OAuth2 authorization-code exchange.
- Chọn test tích hợp WireMock/Testcontainers/IdP sandbox khi cần kiểm tra điều mà mock không thể bảo vệ.

**Phiên bản minh họa:** Java 17+, Spring Boot **3.3.5** và Spring Security **6.3.x** do Boot dependency management quản lý. Các annotation/imports của Boot 4/Spring Security 7 có thể khác; không coi bản minh họa là phiên bản mới nhất.

## 2. Bảng chọn công cụ theo cơ chế

| Kịch bản | Authentication/principal dự kiến | Test tool tương ứng | Giới hạn |
| --- | --- | --- | --- |
| Username/roles chung, không phụ thuộc OAuth2 | `UsernamePasswordAuthenticationToken`, `UserDetails` | `@WithMockUser` hoặc `user()` | Không tạo JWT/OAuth2 principal |
| JWT Resource Server | `JwtAuthenticationToken` / `Jwt` | `jwt()` | Bỏ qua decode/chữ ký/claim validation |
| JWT qua Bearer filter | `JwtAuthenticationToken` | Mock `JwtDecoder` + header Bearer | Test filter wiring, không kiểm tra JWK thật |
| Opaque Resource Server | `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` | `opaqueToken()` | Bỏ qua introspection endpoint |
| Opaque qua Bearer filter | `BearerTokenAuthentication` | Mock `OpaqueTokenIntrospector` + Bearer | Kiểm tra filter/introspection collaboration |
| OAuth2 Login (không OIDC) | `OAuth2AuthenticationToken` / `OAuth2User` | `oauth2Login()` | Không thực hiện redirect/code/token exchange |
| OpenID Connect Login | `OAuth2AuthenticationToken` / `OidcUser` | `oidcLogin()` | Không tự validate chữ ký/nonce/ID token |
| Bất kỳ Authentication dựng thủ công | Phụ thuộc instance | `authentication(authentication)` | Rất linh hoạt nhưng dễ bypass lớp muốn test |
| Thực tế provider discovery, JWKS, introspection, redirects | HTTP/TLS/OAuth2 protocol | Local fake IdP, WireMock, sandbox integration | Chậm hơn, cần lifecycle/secrets |

**Cùng là OAuth 2.0, nhưng OAuth2 Login không đồng nghĩa Resource Server.** `oauth2Login()` mô phỏng user đăng nhập qua browser session; `jwt()` và `opaqueToken()` mô phỏng bearer authentication vào một API. Không dùng `oauth2Login()` thay cho JWT Resource Server test chỉ vì cả hai có thể mang scope.

## 3. Đường đi của JWT request trong ứng dụng

```text
HTTP GET /api/jwt/report
Authorization: Bearer eyJ...
         |
BearerTokenAuthenticationFilter
         |
JwtAuthenticationProvider
         |
JwtDecoder.decode(token)
    - chữ ký/JWK (cấu hình thật)
    - exp, nbf, iss, aud (validator phù hợp)
         |
JwtAuthenticationToken
    principal = Jwt
    authorities = SCOPE_...
         |
AuthorizationFilter kiểm tra hasAuthority(...)
         |
Controller @AuthenticationPrincipal Jwt
```

Trong bài test `.with(jwt())`, ta **chèn kết quả authentication tương đương** vào request context để kiểm tra authorization và controller. `JwtDecoder.decode` **không chạy** khi không gửi Bearer header vào filter. Vì vậy một test `jwt()` PASS không thể chứng minh token do IdP ký đúng, đã hết hạn hay có issuer hợp lệ.

JWT có thể chứa các claims như `sub` (chủ thể), `iss` (issuer), `aud` (audience), `exp` (expiry), `nbf` và `scope`/`scp`. Spring Security mặc định chuyển scope thành authorities có tiền tố `SCOPE_`, ví dụ claim `scope: "reports.read"` tương ứng `SCOPE_reports.read`. Mapping có thể được tùy biến bằng converter; nếu sản phẩm có custom converter, phải test theo converter thật ở tầng phù hợp.

### Đừng lẫn JWT payload với authority

Một test có:

```java
.with(jwt().jwt(jwt ->
    jwt.subject("alice")
       .claim("scope", "reports.read")))
```

mô phỏng JWT có `sub` và `scope`; test utility có thể suy ra `SCOPE_reports.read`. Một test khác:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_reports.read")))
```

chỉ định authorities **trực tiếp**, hữu ích khi tập trung vào authorization nhưng có thể bypass custom claims-to-authorities converter. Khi test chính xác converter claim-to-scope, không nên chỉ hardcode authorities rồi tuyên bố converter đã được kiểm tra.

## 4. Đường đi của opaque token

```text
HTTP GET /api/opaque/report
Authorization: Bearer opaque-string
         |
BearerTokenAuthenticationFilter
         |
OpaqueTokenAuthenticationProvider
         |
OpaqueTokenIntrospector.introspect(token)
    -> OAuth2AuthenticatedPrincipal
    -> attributes (sub, scope, ...)
    -> granted authorities
         |
BearerTokenAuthentication
         |
AuthorizationFilter
         |
Controller @AuthenticationPrincipal OAuth2AuthenticatedPrincipal
```

Opaque token không cần có định dạng JWT, không tự mang claims có thể tin được ở phía resource server. Resource server thường phải hỏi **introspection endpoint** của authorization server (RFC 7662), kiểm tra phản hồi active và lấy thông tin bổ sung. Bài test `opaqueToken()` đặt sẵn `BearerTokenAuthentication` trong SecurityContext, không mở HTTP đến introspection server và không xác minh `active=false` hoặc revoke.

Ngay cả khi chuỗi opaque token tình cờ trông giống JWT, **cơ chế xác minh được cấu hình mới là điều quyết định**. Resource server có thể introspect cả một token mang cấu trúc JWT; đừng phân loại nhánh chỉ dựa vào chuỗi token có dấu chấm.

## 5. OAuth2 Login và OIDC Login khác Bearer Resource Server

Đối với browser login:

```text
Browser GET /web/profile
       |
Spring Security chưa có user
       |
Redirect /oauth2/authorization/test-idp
       |
Authorization Server login/consent
       |
Redirect /login/oauth2/code/test-idp?code=...&state=...
       |
Ứng dụng đổi code và lấy user information / ID token
       |
Session SecurityContext chứa OAuth2AuthenticationToken
       |
Controller @AuthenticationPrincipal OAuth2User hoặc OidcUser
```

`oauth2Login()` của `SecurityMockMvcRequestPostProcessors` **bỏ qua flow chuyển hướng/code exchange** và thiết lập một OAuth2 user đã xác thực cho MockMvc request. Nó phù hợp kiểm tra controller hiển thị thuộc tính người dùng và kiểm soát quyền khi **đã đăng nhập**.

`oidcLogin()` làm tương tự nhưng principal là `OidcUser` có `OidcIdToken`; phù hợp khi code dùng `user.getIdToken()` hoặc `user.getSubject()`.

**Access token** dùng để gọi Resource Server, còn **ID token** trong OIDC nhằm chứng minh sự kiện đăng nhập cho client. Không thay ID token bằng JWT access token trong unit tests hoặc production just because cả hai có thể ở định dạng JWT.

## 6. HTTP status mong đợi

| Request | REST JWT/opaque | Web OAuth2 Login |
| --- | --- | --- |
| Chưa xác thực | Thường 401 với Bearer challenge | Thường 302 redirect đến login/authorization endpoint |
| Có principal nhưng thiếu quyền | 403 Forbidden | 403 nếu authorization rule yêu cầu quyền cụ thể |
| Principal hợp lệ và đủ authority | 200 (tùy controller) | 200 (tùy controller) |
| Bearer token lỗi chữ ký/introspection | 401 trong filter-authentication path | Không phải login-code flow |
| Token mock `jwt()` có claim giả hết hạn | Có thể 200 nếu có authority phù hợp | Không liên quan |

**Không ép mọi request anonymous trả 401.** Với web chain có OAuth2 login, unauthenticated browser thường nhận redirect. Với stateless Resource Server, unauthenticated request thường là 401; authenticated nhưng thiếu `SCOPE_...` là 403. Status có thể khác nếu cấu hình custom `AuthenticationEntryPoint`, `AccessDeniedHandler` hoặc gateway.

## 7. Project minh họa: ba security chains và một bộ MockMvc tests

Để kiểm tra công cụ tương ứng, ta dùng một Spring Boot MVC app có ba nhánh độc lập. Mỗi chain chỉ áp dụng cho path của chính nó:

- `/api/jwt/**`: JWT Resource Server, cần `SCOPE_reports.read`.
- `/api/opaque/**`: Opaque Resource Server, cũng cần `SCOPE_reports.read`.
- `/web/**`: OAuth2 Login/OIDC Login, cần user authenticated.
- Các path khác bị deny theo fallback chain; không để “ngoài matcher” trở thành route công khai không mong đợi.

Cây thư mục:

```text
security-auth-modes/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/security/
│   ├── SecurityModesApplication.java
│   ├── SecurityModesController.java
│   └── SecurityModesConfiguration.java
└── src/test/java/com/example/security/
    └── SecurityModesMvcTest.java
```

Trong tests, `JwtDecoder` và `OpaqueTokenIntrospector` là Mockito mocks, còn một `ClientRegistrationRepository` fake chỉ có URL/credentials giả phục vụ tạo OAuth2 Login filter. **Không kết nối Identity Provider thật.** App chỉ được kỳ vọng chạy các tests với test beans; để chạy `bootRun` ngoài test, bạn phải cấu hình decoder/introspector/client registration thật theo môi trường.

## 8. Gradle dependencies

### settings.gradle

```groovy
rootProject.name = 'security-auth-modes'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

### Vai trò của dependencies

- `spring-boot-starter-security`: `SecurityFilterChain`, filters, authorization.
- `spring-boot-starter-oauth2-resource-server`: JWT/opaque resource server support; JWT verification cũng cần JOSE module được starter cung cấp.
- `spring-boot-starter-oauth2-client`: OAuth2 Login và ClientRegistration.
- `spring-security-test`: `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()`, `@WithMockUser`, integration với MockMvc.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, MockMvc test support.
- `junit-platform-launcher`: chạy JUnit Platform trong Gradle khi cần.

Đừng trộn `spring-security-test` version mới hơn nhiều với `spring-security-*` runtime của Boot 3.3. Dùng dependency management của Boot để tránh class/method version mismatches.

## 9. Application root

`src/main/java/com/example/security/SecurityModesApplication.java`:

```java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityModesApplication.class, args);
    }
}
```

Không có `@EnableMethodSecurity` trong demo vì authorization policy nằm ngay trong filter chains. Nếu dự án thật dùng `@PreAuthorize`, cần bật method security và test cả method invocation ở tầng thích hợp.

## 10. Controller minh họa bốn kiểu principal

`src/main/java/com/example/security/SecurityModesController.java`:

```java
package com.example.security;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecurityModesController {

    @GetMapping("/api/jwt/report")
    public Map<String, String> jwt(
            @AuthenticationPrincipal Jwt principal) {
        return Map.of(
                "mode", "jwt",
                "subject", principal.getSubject());
    }

    @GetMapping("/api/opaque/report")
    public Map<String, String> opaque(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
                "mode", "opaque",
                "subject",
                String.valueOf(principal.getAttribute("sub")));
    }

    @GetMapping("/web/profile")
    public Map<String, String> oauth2(
            @AuthenticationPrincipal OAuth2User user) {
        return Map.of(
                "mode", "login",
                "subject", String.valueOf(user.getAttribute("sub")));
    }

    @GetMapping("/web/oidc")
    public Map<String, String> oidc(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "mode", "oidc",
                "subject", user.getSubject());
    }
}
```

Bốn endpoints cố ý yêu cầu **đúng type principal**. Nếu đưa `@WithMockUser` vào `/api/jwt/report`, Spring không tạo `Jwt` từ `UserDetails`; method có thể không nhận đúng principal. Đó là lý do không thể dùng một annotation cho mọi flow.

Các responses chỉ trả field phi nhạy cảm `subject` và `mode`. Trong ứng dụng thật, không trả toàn bộ JWT claims/ID token/access token hoặc secrets trong API responses để “debug”.

## 11. SecurityFilterChain tách riêng JWT, opaque và login

`src/main/java/com/example/security/SecurityModesConfiguration.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityModesConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain jwtApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/jwt/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/jwt/report")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(withDefaults()))
                .sessionManagement(sessions ->
                        sessions.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain opaqueApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/opaque/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/opaque/report")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.opaqueToken(withDefaults()))
                .sessionManagement(sessions ->
                        sessions.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain browserLogin(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(
                        "/web/**", "/login/**", "/oauth2/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/web/**")
                        .authenticated()
                        .anyRequest().permitAll())
                .oauth2Login(withDefaults())
                .build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain otherRequests(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().denyAll())
                .build();
    }
}
```

### Phân tích cấu hình

1. `@Order` quy định thứ tự chọn chain; Spring Security dùng **chain đầu tiên có matcher khớp**, không chạy tuần tự mọi chain cho một request.
2. `jwtApi` chỉ áp dụng cho `/api/jwt/**`, tạo JWT authentication filter và yêu cầu `SCOPE_reports.read`.
3. `opaqueApi` chỉ áp dụng cho `/api/opaque/**`, tạo opaque-token filter và yêu cầu cùng scope.
4. `browserLogin` chỉ áp dụng cho path liên quan web/login/authorization; bật `oauth2Login` và giữ session/CSRF mặc định của login flow.
5. `otherRequests` chặn các path còn lại. Không có ý định mở mọi endpoint trong demo.
6. `csrf(AbstractHttpConfigurer::disable)` chỉ được áp dụng cho hai **stateless bearer API chains**. Không tắt CSRF toàn hệ thống chỉ vì muốn test GET dễ hơn.

**Lưu ý:** việc dùng JWT và opaque cùng lúc trong một ứng dụng không nên cấu hình chồng tùy tiện trong cùng một chain; demo tách qua path matchers để người học thấy rõ filter nào chạy. Một hệ thống thật có thể phân biệt qua host, tenant hoặc service boundary khác, nhưng cần explicit security design và tests cho mọi matcher.

### Tại sao cần mock decoder/introspector dù dùng jwt()/opaqueToken()?

Khi khởi tạo `SecurityFilterChain` có `oauth2ResourceServer().jwt()`, filter cần một `JwtDecoder` hợp lệ để xây provider. Tương tự opaque cần `OpaqueTokenIntrospector`. Bài test tạo hai mocks làm beans để Spring context khởi tạo được **mà không phải truy cập IdP**. Các test với `jwt()` và `opaqueToken()` không cần gọi mocks này, nhưng các test gửi Bearer header thật sẽ stub và kiểm tra tương tác.

### @SpringBootTest thay vì @WebMvcTest?

Bộ ví dụ dùng `@SpringBootTest + @AutoConfigureMockMvc` để giữ toàn bộ **production SecurityFilterChain** và bốn endpoints thực trong một context. `@WebMvcTest` phù hợp khi test một controller slice nhỏ, nhưng cần import chain/decoder/introspector/ClientRegistrationRepository có chủ đích. Dùng full context ở đây để giúp ba luồng auth hoạt động song song, không phải vì mọi security test đều nên chạy full context.

## 12. Bộ test MockMvc hoàn chỉnh

`src/test/java/com/example/security/SecurityModesMvcTest.java`:

```java
package com.example.security;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityModesMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ClientRegistrationRepository registrations;

    @MockBean
    JwtDecoder jwtDecoder;

    @MockBean
    OpaqueTokenIntrospector introspector;

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeIdentityProvider {

        @Bean
        ClientRegistrationRepository fakeRegistrations() {
            ClientRegistration fake = ClientRegistration
                    .withRegistrationId("test-idp")
                    .clientId("fake-client")
                    .clientSecret("not-a-real-secret")
                    .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                    .redirectUri(
                            "{baseUrl}/login/oauth2/code/{registrationId}")
                    .authorizationUri(
                            "https://idp.example.invalid/authorize")
                    .tokenUri(
                            "https://idp.example.invalid/token")
                    .userInfoUri(
                            "https://idp.example.invalid/userinfo")
                    .userNameAttributeName("sub")
                    .scope("profile")
                    .clientName("Fake IdP")
                    .build();
            return new InMemoryClientRegistrationRepository(fake);
        }
    }

    @Test
    void jwtPostProcessorProvidesJwtPrincipalAndScope()
            throws Exception {
        mvc.perform(get("/api/jwt/report")
                .with(jwt().jwt(builder -> builder
                        .subject("alice")
                        .claim("scope", "reports.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("jwt"))
                .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void jwtPrincipalWithoutRequiredScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/jwt/report")
                .with(jwt().jwt(builder -> builder
                        .subject("alice")
                        .claim("scope", "profile"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingJwtAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/jwt/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void opaquePostProcessorProvidesPrincipalAndAuthorities()
            throws Exception {
        mvc.perform(get("/api/opaque/report")
                .with(opaqueToken()
                        .attributes(attributes ->
                                attributes.put("sub", "bob"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("opaque"))
                .andExpect(jsonPath("$.subject").value("bob"));
    }

    @Test
    void opaquePrincipalWithoutScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/opaque/report")
                .with(opaqueToken()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_profile"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingOpaqueAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(get("/api/opaque/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void oauth2LoginProvidesOAuth2UserAttributes()
            throws Exception {
        ClientRegistration registration = registrations
                .findByRegistrationId("test-idp");

        mvc.perform(get("/web/profile")
                .with(oauth2Login()
                        .clientRegistration(registration)
                        .attributes(attributes ->
                                attributes.put("sub", "carol"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("login"))
                .andExpect(jsonPath("$.subject").value("carol"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/web/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void oidcLoginProvidesIdTokenPrincipal()
            throws Exception {
        mvc.perform(get("/web/oidc")
                .with(oidcLogin()
                        .idToken(token -> token.subject("dana"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("oidc"))
                .andExpect(jsonPath("$.subject").value("dana"));
    }

    @Test
    void realBearerJwtHeaderCallsJwtDecoder()
            throws Exception {
        Jwt decoded = Jwt.withTokenValue("valid-test-jwt")
                .header("alg", "RS256")
                .subject("decoded-alice")
                .claim("scope", "reports.read")
                .build();

        given(jwtDecoder.decode("valid-test-jwt"))
                .willReturn(decoded);

        mvc.perform(get("/api/jwt/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer valid-test-jwt"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("decoded-alice"));

        verify(jwtDecoder).decode("valid-test-jwt");
    }

    @Test
    void badJwtHeaderIsRejectedByAuthenticationFilter()
            throws Exception {
        given(jwtDecoder.decode("bad-jwt"))
                .willThrow(
                        new BadJwtException("invalid test JWT"));

        mvc.perform(get("/api/jwt/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer bad-jwt"))
                .andExpect(status().isUnauthorized());

        verify(jwtDecoder).decode("bad-jwt");
    }

    @Test
    void realOpaqueBearerHeaderCallsIntrospector()
            throws Exception {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "introspected-bob",
                        Map.of("sub", "introspected-bob"),
                        AuthorityUtils.createAuthorityList(
                                "SCOPE_reports.read"));

        given(introspector.introspect("valid-opaque"))
                .willReturn(principal);

        mvc.perform(get("/api/opaque/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer valid-opaque"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject")
                        .value("introspected-bob"));

        verify(introspector).introspect("valid-opaque");
    }

    @Test
    void introspectedOpaqueTokenWithoutScopeIsForbidden()
            throws Exception {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "limited-bob",
                        Map.of("sub", "limited-bob"),
                        AuthorityUtils.createAuthorityList(
                                "SCOPE_profile"));

        given(introspector.introspect("limited-opaque"))
                .willReturn(principal);

        mvc.perform(get("/api/opaque/report")
                .header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer limited-opaque"))
                .andExpect(status().isForbidden());

        verify(introspector).introspect("limited-opaque");
    }
}
```

**Có 13 phương thức `@Test`** trong `SecurityModesMvcTest`, được chia thành 4 JWT cases (3 injected + 1 decoder valid + 1 decoder invalid: thực tế 5), 4 opaque cases (3 injected + 2 introspection: thực tế 4? xem bảng nhóm bên dưới), 3 login/OIDC cases và 1 anonymous redirect. Không cần một Identity Provider thật để chạy các requests vì chỉ sử dụng fake registration và mocks.

**Quan trọng khi đọc source:** bài test sử dụng cả hai con đường rất khác nhau:

- `get(...).with(jwt())`/`with(opaqueToken())`/`with(oauth2Login())` tạo authentication context trước khi filter authorization hoạt động. **Không** có header Bearer phải decode.
- `get(...).header(AUTHORIZATION, "Bearer ...")` đi qua resource-server filter; `JwtDecoder`/`OpaqueTokenIntrospector` mock được gọi. Đây là test wiring của actual filter chain, nhưng vẫn không dùng cryptographic verification/introspection HTTP.

### Test-only registration và mock infrastructure

`@TestConfiguration` nested class cung cấp một `ClientRegistrationRepository` với URL không hoạt động (`example.invalid`) và credentials giả. Nó cho `oauth2Login()` có cấu hình OAuth2 client phù hợp **mà không liên hệ IdP**. Trong production, ClientRegistration phải được load từ provider configuration và secrets đúng môi trường.

`@MockBean` của Spring Boot 3.3 thay các decoder/introspector beans trong test context bằng Mockito mocks. Nó tránh application startup phụ thuộc JWKS hoặc introspection endpoint. Không đưa mock beans này vào `src/main/java` hoặc production profile. Những phiên bản Boot mới có thể dùng annotation khác cho Mockito test beans, vì vậy luôn đối chiếu phiên bản đang dùng.

## 13. Đối chiếu số test và hành vi

| Nhóm | Test methods | Kết quả kỳ vọng |
| --- | --- | --- |
| JWT postprocessor | `jwtPostProcessorProvidesJwtPrincipalAndScope` | 200 + subject alice |
| JWT scope âm | `jwtPrincipalWithoutRequiredScopeIsForbidden` | 403 |
| JWT anonymous | `missingJwtAuthenticationIsUnauthorized` | 401 |
| Opaque postprocessor | `opaquePostProcessorProvidesPrincipalAndAuthorities` | 200 + subject bob |
| Opaque scope âm | `opaquePrincipalWithoutScopeIsForbidden` | 403 |
| Opaque anonymous | `missingOpaqueAuthenticationIsUnauthorized` | 401 |
| OAuth2 Login | `oauth2LoginProvidesOAuth2UserAttributes` | 200 + subject carol |
| Browser anonymous | `anonymousBrowserRequestRedirectsToLogin` | 3xx redirect |
| OIDC Login | `oidcLoginProvidesIdTokenPrincipal` | 200 + subject dana |
| Bearer JWT decoder mock | `realBearerJwtHeaderCallsJwtDecoder` | 200, decoder được gọi |
| Bearer JWT lỗi | `badJwtHeaderIsRejectedByAuthenticationFilter` | 401 |
| Bearer opaque introspector mock | `realOpaqueBearerHeaderCallsIntrospector` | 200, introspector được gọi |
| Bearer opaque thiếu quyền | `introspectedOpaqueTokenWithoutScopeIsForbidden` | 403 |

Tổng là **13** methods (5 JWT, 5 opaque, 3 login/OIDC nếu tính anonymous browser case). Đây là **kết quả dự kiến từ source**, không phải xác nhận Gradle đã chạy PASS.

### Giải thích 401 và 403

Ở REST chains, absence hoặc invalid credentials không tạo authenticated principal nên `AuthenticationEntryPoint` thường trả **401**. Nếu có principal đã xác thực nhưng thiếu `SCOPE_reports.read`, `AuthorizationFilter` từ chối bằng **403**.

Điều này quan trọng cho security regression: một API trả 200 cho principal thiếu scope là rủi ro authorization; một API trả 403 cho unauthenticated request có thể không theo convention mong đợi, nhưng status exact phải dựa vào security policy của chính ứng dụng.

### Giải thích redirect của OAuth2 Login

Với `/web/profile`, chain bật `oauth2Login` thay vì JWT bearer authentication. Request anonymous thường dẫn tới redirect đến trang login/authorization flow. Vì route của demo có thể chọn login page theo client registration, test assert chung `is3xxRedirection()` thay vì hardcode một redirect URI khi không cần bảo vệ path cụ thể.

## 14. jwt(): điều gì được kiểm tra và điều gì bị bỏ qua?

`jwt()` từ Spring Security test tạo một mock `Jwt` và gắn nó vào test request dưới `JwtAuthenticationToken`. Nếu chỉ muốn thử scope authorization:

```java
mvc.perform(get("/api/jwt/report")
        .with(jwt().authorities(
                new SimpleGrantedAuthority(
                        "SCOPE_reports.read"))))
        .andExpect(status().isOk());
```

Snippet này không độc lập vì cần `MockMvc mvc` và config từ project. Nó phù hợp bảo vệ hasAuthority rule, nhưng **không gọi `JwtGrantedAuthoritiesConverter` theo cách tương đương một JWT thực** nếu bạn override authorities trực tiếp.

Nếu muốn kiểm tra claim mapping ở mức mock:

```java
mvc.perform(get("/api/jwt/report")
        .with(jwt().jwt(builder -> builder
                .subject("scope-user")
                .claim("scope", "reports.read"))))
        .andExpect(status().isOk());
```

Spring Security test hỗ trợ việc suy scope thành `SCOPE_...`. Tuy vậy, đây vẫn là test authentication postprocessor; nó **không** chứng minh `NimbusJwtDecoder` thực tế chấp nhận token có signature/issuer/audience đúng.

### Claim exp/iss/aud có được validate không?

Không nên suy như vậy. Bạn có thể tạo một mock JWT chứa `exp` quá khứ, `iss` sai hoặc `aud` thiếu và vẫn chèn principal thành công với `jwt()`, vì bước validate JWT đã bị bypass. Hãy tách:

- **Authorization tests**: `jwt()` với claims/authorities giả để kiểm tra controller/rules.
- **Decoder validator tests**: kiểm tra `JwtDecoder` thực cùng signed test token/JWKS và issuer/audience/timestamps, có clock/skew policy rõ ràng.
- **Integration với IdP**: khi cần provider key rotation, metadata discovery, redirect flow, token issuance và revocation.

**Không dùng `alg=none` từ test JWT builder làm bằng chứng một production JWT hợp lệ.** Thông tin mặc định trên mock là convenience, không đại diện production signing policy.

## 15. Mock JwtDecoder: khi nào quan trọng?

Với header thật:

```java
given(jwtDecoder.decode("valid-test-jwt"))
        .willReturn(Jwt.withTokenValue("valid-test-jwt")
                .header("alg", "RS256")
                .subject("decoded-alice")
                .claim("scope", "reports.read")
                .build());

mvc.perform(get("/api/jwt/report")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer valid-test-jwt"))
        .andExpect(status().isOk());

verify(jwtDecoder).decode("valid-test-jwt");
```

Đoạn này cho biết:

1. `BearerTokenAuthenticationFilter` nhận đúng Bearer header.
2. JWT authentication provider gọi `JwtDecoder.decode`.
3. Spring chuyển `Jwt` do decoder trả thành `Authentication`.
4. Authority mapping thông thường cho phép đi qua scope rule.
5. Controller nhận principal JWT tương ứng.

Nhưng decoder là **Mockito stub**; không có kiểm tra chữ ký/`kid`/JWKS ở đây. Nếu muốn test converter tùy biến, có thể trả một Jwt có scopes/claims đặc biệt và assert security rule, nhưng vẫn phải có bài kiểm tra riêng cho các validators thật.

### Lỗi JWT phải dùng exception phù hợp

`BadJwtException` mô phỏng JWT không hợp lệ trong decoder. Khi nó được ném từ decode, provider chuyển thành lỗi authentication và filter thường trả 401. Không nên dùng một `RuntimeException` bất kỳ để “giả token invalid”: nó có thể bị xử lý như lỗi nội bộ thay vì invalid credentials.

## 16. opaqueToken(): principal và authorities

`opaqueToken()` tạo một `BearerTokenAuthentication` đã xác thực. Nó có thể nhận attributes:

```java
.with(opaqueToken()
    .attributes(attributes -> {
        attributes.put("sub", "bob");
        attributes.put("department", "operations");
    })
    .authorities(new SimpleGrantedAuthority(
            "SCOPE_reports.read")))
```

Tại controller, `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` có thể truy cập các attributes; `Authentication#getAuthorities` quyết định authorization. Với opaque introspection thật, scopes thường được trả về từ authorization server và được chuyển thành authorities có prefix `SCOPE_` theo converter. Khi tạo authorities thủ công trong postprocessor, bạn đang **bỏ qua bước convert scope từ introspection response**.

**Không suy rằng `opaqueToken()` kiểm tra active=true, expiry, revocation hoặc introspection client credentials.** Nó chỉ làm một request có BearerTokenAuthentication hợp lệ để test application logic phía sau authentication.

## 17. Mock OpaqueTokenIntrospector: mô phỏng response từ IdP

Với Bearer header thật:

```java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "introspected-bob",
        Map.of("sub", "introspected-bob"),
        AuthorityUtils.createAuthorityList(
            "SCOPE_reports.read"));

given(introspector.introspect("valid-opaque"))
    .willReturn(principal);

mvc.perform(get("/api/opaque/report")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer valid-opaque"))
    .andExpect(status().isOk());

verify(introspector).introspect("valid-opaque");
```

Điều này kiểm tra resource-server filter **gọi đúng introspector bean** và dùng `OAuth2AuthenticatedPrincipal` trả về. Nó không HTTP POST tới introspection endpoint vì đó là mock. Khi IdP trả “inactive” trong production, introspector thật phải từ chối; để kiểm tra chính logic inactive, cần test introspection client bằng HTTP response giả có `active:false` hoặc sử dụng test library hỗ trợ OAuth2 server stubbing.

### Rủi ro mock introspector quá rộng

Một Mockito stub kiểu `when(introspect(anyString())).thenReturn(principalAdmin)` có thể biến mọi chuỗi, kể cả token sai, thành user đủ quyền. Với integration tests nên stub **exact token** và test invalid branch riêng. Tránh mock trả một principal có admin authority cho mọi request rồi cho rằng security đã được bảo vệ.

Nếu introspection exception có semantics khác nhau (inactive vs endpoint unavailable), cần test mapping theo policy; đừng cho mọi lỗi introspection trở thành 200 hoặc silently grant access.

## 18. oauth2Login() và oidcLogin(): khi nào dùng loại nào?

Khi controller cần `OAuth2User` và các attributes từ user-info endpoint, dùng:

```java
mvc.perform(get("/web/profile")
        .with(oauth2Login()
                .attributes(attrs ->
                        attrs.put("sub", "carol"))))
        .andExpect(status().isOk());
```

Khi controller dùng OpenID Connect `OidcUser`/`OidcIdToken`:

```java
mvc.perform(get("/web/oidc")
        .with(oidcLogin()
                .idToken(id -> id.subject("dana"))))
        .andExpect(status().isOk());
```

Các snippets cần `MockMvc` và project security chains tương ứng. Tại MockMvc request, test utility đưa principal vào đúng security context để `@AuthenticationPrincipal` nhận được. Không có sự kiện browser thực tế được redirect đến IdP hoặc trao đổi authorization code.

### OAuth2 Login test cần test registration thật hay giả?

Nếu code dùng `@RegisteredOAuth2AuthorizedClient` hoặc ClientRegistration/authorized client, test postprocessor có thể nhận `clientRegistration(...)`, còn application context có thể cung cấp `ClientRegistrationRepository`. Trong bộ ví dụ, nested `@TestConfiguration` tạo fake ClientRegistration và test truyền nó vào `oauth2Login()`. Các test không sử dụng production client secret.

### OIDC ID token khác JWT Resource Server access token

`oidcLogin()` thiết lập `OidcUser` với ID token phục vụ login identity. `jwt()` thiết lập `JwtAuthenticationToken` với access token claims theo resource-server semantics. Một controller nhận `@AuthenticationPrincipal OidcUser` không nên được test bằng `jwt()` và ngược lại. Có thể tất cả đều có claim `sub`, nhưng authentication type và trust boundary khác nhau.

### OAuth2 Login không tự tạo session across MockMvc requests

`oauth2Login()` giúp **một request** có user đăng nhập. Nếu muốn test session persistence/redirect cookie/CSRF giữa nhiều requests, phải giữ `MockHttpSession`/cookies đúng cách hoặc dùng browser integration. Đừng cho rằng hai `mvc.perform(...)` độc lập tự chia sẻ session chỉ vì request trước dùng `oauth2Login()`.

## 19. @WithMockUser: dùng đúng nhưng không lạm dụng

`@WithMockUser(username="alice", roles="ADMIN")` rất hữu ích cho controller/service tests mà code chỉ quan tâm tên, roles hoặc chung `Authentication`. Nó tạo `UsernamePasswordAuthenticationToken` với `UserDetails` principal và authorities như `ROLE_ADMIN`.

Nhưng với code dựa trên:

- `@AuthenticationPrincipal Jwt`;
- `BearerTokenAuthentication.getTokenAttributes()`;
- `@AuthenticationPrincipal OAuth2User`;
- `@AuthenticationPrincipal OidcUser`;

...thì `@WithMockUser` không tạo đúng object. Với `@PreAuthorize("hasAuthority('SCOPE_reports.read')")`, có thể dùng `@WithMockUser(authorities="SCOPE_reports.read")` để test **chính expression authorization**. Tuy nhiên test này vẫn không xác nhận resource-server JWT/opaque authentication.

Phân biệt:

| Annotation/postprocessor | Principal/Auth | Hợp lý nhất khi |
| --- | --- | --- |
| `@WithMockUser` | Spring User, UsernamePasswordAuthenticationToken | Test role/username độc lập token |
| `user("alice")` | UserDetails | Cần username/roles trong một MockMvc request |
| `jwt()` | Jwt, JwtAuthenticationToken | API JWT và scope rules |
| `opaqueToken()` | OAuth2AuthenticatedPrincipal, BearerTokenAuthentication | API introspection và attributes |
| `oauth2Login()` | OAuth2User, OAuth2AuthenticationToken | OAuth2 browser-login controller |
| `oidcLogin()` | OidcUser, OAuth2AuthenticationToken | OpenID Connect user/id token |
| `authentication(token)` | Type tùy ý | Custom Authentication hoặc manual setup |

**Không khai báo `@WithMockUser` toàn class** rồi quên những request cần phải anonymous. Nó có thể khiến negative authentication test giả định thiếu token lại được xem như user đã xác thực. Khi cần unauthenticated test, không thêm user postprocessor và không đặt class-level authentication annotation.

## 20. Permission mapping: SCOPE_ và ROLE_ không giống nhau

Spring Security quản lý authorities dưới dạng strings; convention là:

- `hasRole("ADMIN")` thường tìm `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` tìm chính string `ROLE_ADMIN`.
- `hasAuthority("SCOPE_reports.read")` tìm OAuth2 authority có prefix `SCOPE_`.
- JWT/opaque scopes thường được chuyển từ dữ liệu token sang authorities `SCOPE_*`, nhưng converter có thể được cấu hình lại.

**Không biến mọi scope thành role admin.** Scope như `reports.read` là quyền hạn do authorization server cấp; vai trò nội bộ như ADMIN có thể đến từ policy/claims/DB riêng. Khi map từ external claims sang internal roles, cần kiểm tra issuer/tenant, allowlist và authority converter thật để tránh privilege escalation.

Test âm `jwtPrincipalWithoutRequiredScopeIsForbidden` và `opaquePrincipalWithoutScopeIsForbidden` có giá trị cao vì chúng chứng minh **đã xác thực nhưng thiếu permission thì không truy cập được**.

## 21. Request matching và default-deny

Khi có nhiều filter chains, những lỗi khó tìm thường nằm ở matcher:

```text
/api/jwt/report      -> jwtApi chain
/api/opaque/report   -> opaqueApi chain
/web/profile         -> browserLogin chain
/web/oidc            -> browserLogin chain
/unknown             -> fallback denyAll chain
```

Nếu một security matcher vô tình viết `/api/jwt/*` thay vì `/api/jwt/**`, nested API route có thể không được bảo vệ bởi đúng filter. Nếu không có fallback chain, request có thể rơi ra ngoài mọi chain hoặc được một chain mặc định khác xử lý; do đó **test path mismatches và deny-by-default** là phần quan trọng khi triển khai thật.

**Không cấu hình cùng lúc JWT và opaque provider cho cùng một path mà không có quy tắc phân giải rõ ràng.** Đối với bearer tokens, filter không thể an toàn chọn provider chỉ bằng cách nhìn token có ba phần cách bởi dấu chấm nếu hệ thống có chính sách tin cậy khác nhau.

## 22. Các tình huống lỗi đáng viết thêm test

### JWT

- Không có `Authorization` header → 401.
- Bearer header malformed → 401 theo entry point và resolver.
- Decoder phát hiện invalid signature/expired/issuer/audience → 401.
- Decoder trả valid Jwt thiếu scope → 403.
- Có scope nhưng tenant ID không khớp resource ownership → 403 theo business policy.
- Có claim dạng list/string khác nhau với `scope`/`scp` → converter test.
- Token hết hạn sát thời điểm hiện tại → validator test với clock/skew.
- JWKS rotation/`kid` thay đổi → integration với fake JWKS server.

### Opaque token

- Không có Bearer → 401.
- Introspector trả principal có scope phù hợp → 200.
- Introspector trả principal thiếu scope → 403.
- IdP trả `active:false` → 401 khi introspector thật từ chối.
- Introspection endpoint timeout/5xx → xử lý theo policy, **không tự cho phép** truy cập.
- Token bị revoke sau khi cache introspection → kiểm tra TTL/revocation window.
- Introspection client dùng secret sai → authentication thất bại, không log secret.

### OAuth2 Login/OIDC

- Anonymous tới protected page → redirect.
- Sau login thành công với user attributes → controller trả đúng profile.
- Missing email/subject/roles → mapping behavior hợp lệ.
- OIDC ID token có nonce/issuer/audience sai → integration validation test.
- Callback state mismatch/CSRF → reject.
- Session fixation/session expiry/logout → đúng policy.
- Nhiều client registrations → chọn đúng provider/redirect URI.
- User có external role nhưng không được app tin cậy → 403.

Test những trường hợp quan trọng với sản phẩm thực; không cần mở một IdP thật cho mọi unit/controller test.

## 23. Bảo mật của chính test fixtures

- Dùng token giả như `valid-test-jwt` hoặc `valid-opaque`, **không** copy access token production vào mã nguồn.
- Dùng domain reserved như `idp.example.invalid` cho fake ClientRegistration; không vô tình gọi domain ngoài.
- Không đưa production client secrets, refresh tokens, cookies/Authorization headers vào log hoặc snapshots.
- Nếu cần test actual JWKS signature, dùng keys/certificates sinh cho test với private key được bảo vệ, không commit production secrets.
- Với test expired/nbf, dùng thời gian cố định hoặc clock hỗ trợ skew; tránh assertions sát giây hết hạn gây flaky.
- Với OAuth2 login redirect, kiểm tra state/nonce/PKCE bằng test protocol ở tầng thích hợp; không tắt chúng để test dễ hơn.
- Tránh custom `JwtDecoder` chấp nhận `alg=none` trong production; mock JWT mặc định không tương đương production token.
- Không cho `OpaqueTokenIntrospector` mặc định grant admin authority khi token không introspect được.
- Nếu dùng multi-tenant issuer, kiểm tra tenant identity và requested resource, không chỉ xem có `SCOPE_read`.
- Bảo vệ test endpoints và profiles: không export fake-idp registration hoặc mocked decoder vào production.

## 24. Chạy project và đọc kết quả thật

Giả sử bạn đã tạo Gradle Wrapper tương thích, chạy:

```bash
./gradlew test --tests 'com.example.security.SecurityModesMvcTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu project chưa có Wrapper nhưng đã cài Gradle tương thích:

```bash
gradle test
```

Bộ source mẫu có **13 methods mang `@Test`**. Không có stdout nghiệp vụ cố định: log phụ thuộc Spring/Gradle version và môi trường. Đọc báo cáo sau khi chạy:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Các kết quả 200/401/403/3xx trong bảng là kỳ vọng theo test source. Chưa có Gradle execution report trong quá trình biên soạn bài này, nên không được tuyên bố “13 tests đã PASS”.** Nếu test fail do Spring context startup, xác định thiếu JwtDecoder, introspector hoặc ClientRegistrationRepository trước khi sửa assertions.

### Thứ tự chẩn đoán khi context fail

1. Xác nhận Spring Boot 3.3.5, Java 17, dependencies và import classes.
2. Kiểm tra bốn SecurityFilterChain beans được tạo, matchers và `@Order`.
3. Kiểm tra `@MockBean JwtDecoder` và `@MockBean OpaqueTokenIntrospector` được đăng ký trong test context.
4. Kiểm tra nested `@TestConfiguration` tạo fake ClientRegistrationRepository.
5. Kiểm tra anonymous status và request matcher đầu tiên.
6. Kiểm tra `jwt()`/`opaqueToken()` đưa đúng authorities.
7. Với Bearer header, kiểm tra Mockito stub có đúng token string và `verify(decoder).decode(...)` hoặc `verify(introspector).introspect(...)`.
8. Đọc full root cause và `MockMvc` actual response, không tắt security filter chỉ để suite xanh.

## 25. Các lỗi sai phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` mà `@AuthenticationPrincipal Jwt` null | Sai principal type | Dùng `jwt()` hoặc real Bearer + decoder |
| Opaque controller không có token attributes | Dùng `jwt()` hoặc `@WithMockUser` | Dùng `opaqueToken()` |
| OIDC controller không nhận OidcUser | Dùng `oauth2Login()` thường | Dùng `oidcLogin()` |
| JWT test 200 dù token có exp quá khứ | `jwt()` bypass validator | Test JwtDecoder thật |
| Introspection bị revoke mà test vẫn 200 | `opaqueToken()` bypass IdP | Mock introspection HTTP thật/validator |
| Test 403 trong khi tưởng 401 | Đã authenticated nhưng thiếu scope | Phân biệt authn và authz |
| Browser anonymous nhận redirect, không 401 | OAuth2 Login entry point | Assert 3xx theo chain |
| Authority `reports.read` không khớp | Security rule cần `SCOPE_reports.read` | Map authorities đúng prefix |
| Method bảo vệ bởi `@PreAuthorize` không chạy trong test | Chưa bật method security | Thêm `@EnableMethodSecurity` và test đúng context |
| JWT bearer header không gọi decoder | Đã dùng `with(jwt())` thay header | Dùng header Bearer và mock decoder |
| JWT bearer token fail thành internal error | Mock ném RuntimeException tùy ý | Dùng exception authentication/BadJwt phù hợp |
| Opaque bearer mock vẫn gọi mạng IdP | Mock bean chưa thay đúng introspector | Kiểm tra bean type và chain |
| OAuth2 login thiếu ClientRegistrationRepository | OAuth2 client config chưa được cung cấp | Dùng test-only registration |
| Login mock có user nhưng session test fail | Mock chỉ tạo context cho một request | Giữ session/cookie hoặc test login flow riêng |
| CSRF error trên POST browser test | Chưa có CSRF token | Dùng `csrf()` cho state-changing request |
| Có path không được bảo vệ | `securityMatcher` sai hoặc thiếu fallback | Test route matrix/denyAll |
| Unit tests PASS nhưng JWKS rotation production fail | Mock decoder không dùng JWKs | Integration test fake JWKS server |
| Mockito scope mock cho tất cả bearer | Stub quá rộng | Dùng exact token + negative tests |

## 26. JWT signing, issuer, audience và clock skew

### Những yêu cầu của JWT Resource Server thật

Theo policy của ứng dụng, JWT Resource Server cần kiểm tra:
- Chữ ký hợp lệ bằng key đáng tin cậy/JWKS.
- Thuật toán được chấp nhận (không vô tình tin `alg=none`).
- `exp` và `nbf` với clock skew phù hợp.
- `iss` trùng authorization server/tenant được cấu hình.
- `aud` chứa API recipient đúng, nếu hệ thống yêu cầu.
- Scope/role claims được map và validate đúng.
- Token không bị dùng sai purpose (ID token thay access token).

`jwt()` trong MockMvc bypass các bước này. Để kiểm chứng validator, tạo signed test JWT bằng test key và một local JWK set endpoint, cấu hình `NimbusJwtDecoder` thật/validators thật, rồi thử invalid issuer/audience/expired/signature scenarios. Việc đó là **một test suite khác**, không phải mở rộng giả lập principal.

### Ranh giới của JwtDecoder Mockito

Test với `given(jwtDecoder.decode("valid-test-jwt")).willReturn(jwt)` xác minh filter→provider→converter→controller, nhưng **Mockito quyết định token hợp lệ**. Nó không tự phát hiện policy đổi JWK endpoint hoặc key rotation. Đừng báo cáo “JWT signature verified” từ test chỉ có mock decoder.

## 27. Opaque introspection và tính thu hồi token

Một opaque token có thể bị revoke nhanh vì Resource Server tham vấn IdP, nhưng độ trễ và cache policy có thể làm một token cũ còn hiệu lực trong khoảng thời gian nhất định. Các test policy cần xác định:

- Introspection endpoint auth bằng client ID/secret đúng.
- Response `active` true/false được hiểu đúng.
- `exp`, `scope`, `sub` và custom attributes có semantics rõ.
- Cache introspection, nếu có, có TTL và invalidation/revocation SLA.
- Khi IdP timeout, hệ thống fail closed hay áp dụng fallback nào theo policy (không âm thầm grant access).
- Logs không phát tán access token hoặc introspection client secret.

`opaqueToken()` cung cấp principal giả đã authenticated; `@MockBean OpaqueTokenIntrospector` cung cấp principal giả từ filter; cả hai không gọi HTTP endpoint. Để kiểm tra parser response `active:false` và credentials, cần mock endpoint HTTP hoặc dùng sandbox IdP riêng, không chỉ tạo `DefaultOAuth2AuthenticatedPrincipal` thủ công.

## 28. Test OAuth2 browser login ở mức nào?

Có ít nhất ba tầng:

1. **Controller đã đăng nhập:** `oauth2Login()`/`oidcLogin()`, không redirect/code exchange.
2. **Spring Security flow:** MockMvc/HTTP server test cho redirect, state, session, callback, login success handler; có thể mock token/user-info endpoints.
3. **End-to-end IdP:** browser hoặc protocol test qua provider sandbox, kiểm tra PKCE/nonce, cookies, TLS và cross-origin behavior theo cấu hình thật.

Dùng tầng nhẹ nhất có thể bảo vệ behavior bạn quan tâm. Nếu controller chỉ hiển thị tên user, `oauth2Login()` đủ; nếu kiểm tra callback URL được cấu hình đúng, cần tầng hai; nếu cần chứng minh IdP production hỗ trợ PKCE/token mapping, tầng ba.

### CSRF trong browser flow

CSRF vẫn có ý nghĩa với session-authenticated browser requests. Nếu mở rộng project với POST `/web/settings`, MockMvc test gửi POST bằng OAuth2 login cần CSRF token khi Spring Security bật CSRF:

```java
mvc.perform(post("/web/settings")
        .with(oauth2Login())
        .with(csrf()))
        .andExpect(status().isOk());
```

Đây là **snippet**, không runnable độc lập vì project chưa có `/web/settings` POST endpoint. Cần static imports `post` và `csrf`, và controller/state tương ứng. Không tắt CSRF trên browser chain để tránh phải viết một `.with(csrf())`.

## 29. Test method security

Nếu ứng dụng bảo vệ service method bằng:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report readReport(String id) {
    // ...
}
```

thì đây là **snippet**, không thuộc project runnable. Cần bật `@EnableMethodSecurity` và giữ proxy/bean thật. Một `@WithMockUser(authorities="SCOPE_reports.read")` có thể kiểm tra quyền của method nhưng không tạo JWT claims; test dùng `jwt()`/`opaqueToken()` có thể kết hợp với MockMvc để đưa đúng principal vào HTTP request rồi kiểm tra method security đi qua service.

Nếu service bị mock toàn bộ bằng `@MockBean`, `@PreAuthorize` trên service thật cũng có thể không được exercise. Hãy phân biệt test authorization expression với test filter authentication.

## 30. WebFlux/reactive không dùng cùng MockMvc postprocessors

Project dùng servlet MVC. Với ứng dụng WebFlux, dùng `WebTestClient` và các postprocessors riêng như `SecurityMockServerConfigurers.mockJwt()`, `mockOpaqueToken()`, `mockOAuth2Login()` hoặc `mockOidcLogin()` tùy Spring Security version. Không copy trực tiếp `SecurityMockMvcRequestPostProcessors.jwt()` vào WebFlux rồi nghĩ là cùng một abstraction.

**Các hướng đều phải đảm bảo security filter integration thực sự được gắn vào test client.** Với `MockMvcBuilders.standaloneSetup(...)`, nếu không gọi `.apply(springSecurity())` hoặc gắn SecurityFilterChain đúng, các postprocessors có thể không hoạt động như một test an ninh thực. `@SpringBootTest + @AutoConfigureMockMvc` của project mẫu tự đưa security filter chains vào MockMvc.

## 31. Bài tập luyện tập

1. Chạy ba request không có auth vào /api/jwt/report, /api/opaque/report, /web/profile; giải thích 401 vs redirect.
2. Thay `.with(jwt())` bằng `@WithMockUser` ở JWT endpoint, quan sát principal type mismatch.
3. Bỏ scope reports.read của JWT, xác minh status 403.
4. Thử `jwt().authorities(...)` thay cho claim mapping, nói rõ phần converter nào bị bypass.
5. Tạo mock JWT với `iss` sai hoặc expired; giải thích tại sao `jwt()` vẫn không tự reject.
6. Viết test `JwtDecoder` thật có signed test JWT và audience validator.
7. Cho `jwtDecoder.decode(...)` ném `BadJwtException`, kiểm tra 401.
8. Dùng opaqueToken() custom attributes `department` và assert ở controller mới.
9. Cho introspector trả principal có `SCOPE_profile` và assert opaque endpoint 403.
10. Tạo một stub introspection endpoint trả `active:false` để test HTTP introspector thật.
11. Với OAuth2 Login, thay attr `sub` thành một user khác và kiểm tra profile response.
12. Dùng oidcLogin() với ID token `sub` riêng, xác minh `OidcUser`.
13. Test OAuth2 callback state mismatch bằng MockMvc/IdP stub tầng giao thức.
14. Thêm POST /web/settings được bảo vệ CSRF, thử thiếu và có `csrf()`.
15. Thử thêm custom JwtGrantedAuthoritiesConverter map claim riêng và kiểm tra behavior không bị postprocessor override.
16. Kiểm tra fail-closed khi introspection endpoint timeout.
17. Thêm matcher deny-by-default cho endpoint mới và bảo đảm không rò public API.
18. Tạo test method security `@PreAuthorize` với principal phù hợp và verify service thật.
19. Chạy một test riêng và toàn class, đọc báo cáo Gradle thực tế.
20. Đặt token/secrets giả trong fixtures và kiểm tra không có token production trong Git/CI logs.

## 32. Checklist QA

- [ ] Đã phân biệt JWT Resource Server, opaque Resource Server và OAuth2/OIDC Login?
- [ ] Dùng đúng `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()` theo principal type?
- [ ] Không dùng `@WithMockUser` như một JWT/opaque replacement nếu code cần token type?
- [ ] `@MockBean JwtDecoder` và `@MockBean OpaqueTokenIntrospector` chỉ có trong test context?
- [ ] Đã tách mock SecurityContext tests khỏi Bearer filter tests?
- [ ] Có assert cả 200, 401 và 403 theo đúng route/policy?
- [ ] Browser anonymous có redirect expectation theo OAuth2 Login?
- [ ] `SCOPE_` và `ROLE_` được phân biệt và kiểm tra đúng?
- [ ] JWT claims quan trọng được map thành authorities theo converter thực?
- [ ] Không tuyên bố `jwt()` đã validate chữ ký/exp/iss/aud?
- [ ] Không tuyên bố `opaqueToken()` đã gọi introspection/kiểm tra revoke?
- [ ] OAuth2 login test có user attrs và client registration phù hợp?
- [ ] OIDC test có `OidcUser`/ID token, không lẫn access token?
- [ ] SecurityFilterChain matchers và order được bảo vệ bằng tests?
- [ ] Stateless API CSRF policy được tách khỏi browser CSRF policy?
- [ ] Không có trust-all JwtDecoder/introspector trong production?
- [ ] API bearer token và OAuth2 login session không bị nhầm lẫn?
- [ ] Token/credentials demo đều giả, không có secret thật trong logs?
- [ ] Với multi-tenant, issuer/audience/tenant ownership có test riêng?
- [ ] Với revoke/ID token validation, có integration/IdP tests phù hợp?
- [ ] Nếu dùng reactive WebFlux, đã chọn WebTestClient APIs tương ứng?
- [ ] Đã đọc Gradle/CI report thật trước khi khẳng định tests PASS?

## 33. Tài liệu chính thức

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/oauth2.html): `jwt()`, `opaqueToken()`, `oauth2Login()`, `oidcLogin()`, mocking decoder/introspector.
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/authentication.html): `user()` và `@WithMockUser`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/setup.html): `springSecurity()` MockMvc configurer.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/resource-server/jwt.html): JwtDecoder, issuer/audience, scope authority mapping.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/resource-server/opaque-token.html): introspection và BearerTokenAuthentication.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.3/servlet/oauth2/login/core.html): ClientRegistration, SecurityFilterChain, OAuth2AuthenticationToken.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): Spring Boot auto-configuration và custom security chains.
- [Spring Boot 3.3 — OAuth2](https://docs.spring.io/spring-boot/3.3/reference/security/oauth2.html): resource server/client registrations và configuration properties.
- [Spring Boot 3.3 — @MockBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): test-only bean replacement.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter test methods.

## 34. Kết luận

**JWT**, **opaque token** và **OAuth2 Login** đều dùng Spring Security nhưng không thể gom vào một mock user type. Với JWT Resource Server, dùng **`jwt()`** để test principal/scope/authorization, hoặc mock **`JwtDecoder`** rồi gửi Bearer header để test authentication filter. Với opaque Resource Server, dùng **`opaqueToken()`** hoặc mock **`OpaqueTokenIntrospector`** tương ứng. Với browser OAuth2/OIDC Login, dùng **`oauth2Login()`** hoặc **`oidcLogin()`** để mô phỏng người dùng đã đăng nhập; muốn test full redirect/code/JWKS/nonce/PKCE cần integration tests ở tầng sâu hơn.

Một suite bảo mật hữu ích cần kiểm tra cả access allowed/forbidden/unauthorized, authority mapping và principal type, đồng thời **không tuyên bố chữ ký JWT, revocation hay OAuth2 redirect flow đã được kiểm chứng chỉ vì MockMvc postprocessor PASS**. Bài mẫu Java17+/Spring Boot3.3.5 dùng ba filter chains, controllers và 13 phương thức test để phân biệt rõ các ranh giới này.
