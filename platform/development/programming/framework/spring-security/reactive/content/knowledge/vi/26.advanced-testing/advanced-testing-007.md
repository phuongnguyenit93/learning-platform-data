# Kiểm thử `mockOAuth2Login()`, `mockOidcLogin()` và principal sau đăng nhập trong Spring Security WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) tạo một request đã xác thực bằng OAuth 2.0 Login hoặc OpenID Connect (OIDC) Login trong `WebTestClient` mà không cần Identity Provider (IdP) thật; (2) kiểm tra `OAuth2User`, `OidcUser`, `Authentication` và tên principal sau đăng nhập; (3) thiết lập attributes, ID Token claims, authorities và tên principal tùy biến; (4) viết cả kịch bản được phép, bị từ chối và chưa đăng nhập; (5) phân biệt giới hạn của kiểm thử giả lập với kiểm thử toàn bộ luồng đăng nhập.

## 1. Những gì thực sự được giả lập

Trong ứng dụng WebFlux, bộ lọc Spring Security lưu thông tin xác thực trong reactive security context để controller và tầng nghiệp vụ truy cập được trong luồng Reactor. Hai helper của thư viện `spring-security-test` tạo ngữ cảnh xác thực cho **request kiểm thử**, bỏ qua việc chuyển hướng đến IdP, nhận authorization code, đổi code lấy token hoặc kiểm tra chữ ký token:

- `mockOAuth2Login()`: tạo `OAuth2AuthenticationToken` có principal kiểu `OAuth2User`. Phù hợp ứng dụng dùng OAuth 2.0 Login và các attributes của người dùng.
- `mockOidcLogin()`: cũng tạo `OAuth2AuthenticationToken`, nhưng principal là `OidcUser` với `OidcIdToken` và `OidcUserInfo`. Phù hợp ứng dụng cần danh tính/claims của OIDC.

Sơ đồ luồng kiểm thử:

~~~text
WebTestClient.mutateWith(mockOAuth2Login() hoặc mockOidcLogin())
    -> request giả lập có Authentication trong SecurityContext
    -> SecurityWebFilterChain (quy tắc xác thực/phân quyền)
    -> Handler/Controller (@AuthenticationPrincipal, Principal)
    -> response được assert bằng WebTestClient
~~~

Cả hai helper đều có thể cung cấp `OAuth2AuthorizedClient` giả qua repository dùng trong test, hữu ích với `@RegisteredOAuth2AuthorizedClient`. Chúng **không xác minh** rằng cấu hình authorization endpoint, redirect URI, client secret, PKCE, token exchange hoặc IdP bên ngoài hoạt động đúng.

### Mặc định cần nhớ

| Đặc điểm | `mockOAuth2Login()` | `mockOidcLogin()` |
| --- | --- | --- |
| Authentication | `OAuth2AuthenticationToken` | `OAuth2AuthenticationToken` |
| Principal | `OAuth2User` | `OidcUser` (cũng là `OAuth2User`) |
| Danh tính mặc định | attribute `sub = "user"` | ID Token claim `sub = "user"` |
| Authority mặc định | `SCOPE_read` | `SCOPE_read` |
| Dữ liệu chỉnh sửa trực tiếp | `attributes(...)` | `idToken(...)`, `userInfo(...)` |
| Principal hoàn toàn tùy biến | `oauth2User(...)` | `oidcUser(...)` |

`getName()` của principal mặc định trả `user`. Trong trường hợp tùy biến, `getName()` có thể lấy từ thuộc tính khác như `user_name` hoặc `preferred_username`; nó không nhất thiết bằng claim `sub`. `Authentication.getPrincipal()` là đối tượng người dùng, còn `Authentication.getName()` là tên do đối tượng đó quyết định.

## 2. Chuẩn bị môi trường kiểm thử reactive

Ví dụ sử dụng Java 17+, Spring Boot 3.x / Spring Security 6.x và JUnit Jupiter. Trên dự án Gradle Spring Boot **đã có plugins và quản lý phiên bản**, thêm các dependency dưới đây vào `build.gradle` (không khai báo phiên bản riêng để dùng BOM của Boot):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dùng WebFlux, `WebTestClient` và import helper từ `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers`. API dành cho Spring MVC như `SecurityMockMvcRequestPostProcessors.oauth2Login()` hoặc `MockMvc` **không** phải helper dùng trong bài này. Các bài test bên dưới bind vào application context giả lập (`MOCK`), không khởi động server thật.

Để có ví dụ chạy được và chủ động quan sát principal, tạo ba file cùng package `com.example.securitydemo`.

### File 1: `src/main/java/com/example/securitydemo/ReactiveLoginDemoApplication.java`

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveLoginDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/admin").hasAuthority("ROLE_ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Chuỗi filter yêu cầu xác thực đối với mọi endpoint, riêng `/admin` đòi authority `ROLE_ADMIN`. `httpBasic` chỉ cho ví dụ xác định rõ phản hồi 401 khi truy cập ẩn danh; helper OAuth2/OIDC trong test vẫn đưa ngữ cảnh xác thực giả trực tiếp vào request. **Đây là cấu hình tối giản để kiểm tra principal**, không phải cấu hình đăng nhập OAuth2/OIDC production. Ứng dụng thật cần thiết lập `oauth2Login`, client registration và provider tương ứng.

### File 2: `src/main/java/com/example/securitydemo/ProfileController.java`

~~~java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping("/me/oauth2")
    public Mono<Map<String, String>> oauth2(
            @AuthenticationPrincipal OAuth2User user) {
        return Mono.just(Map.of(
                "name", user.getName(),
                "userId", user.getAttribute("user_id")));
    }

    @GetMapping("/me/oidc")
    public Mono<Map<String, String>> oidc(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of(
                "name", user.getName(),
                "subject", user.getIdToken().getSubject(),
                "userId", user.getIdToken().getClaimAsString("user_id")));
    }

    @GetMapping("/me/principal")
    public Mono<String> principal(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @GetMapping("/me/context")
    public Mono<String> contextName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
~~~

`@AuthenticationPrincipal` trích ra `Authentication.getPrincipal()`, sau đó chuyển sang kiểu khai báo. Khi endpoint cần OIDC-specific ID Token, hãy dùng `OidcUser` và `getIdToken()`. Nếu chỉ cần tên đã xác thực, có thể nhận `Mono<Principal>` hoặc đọc `ReactiveSecurityContextHolder`. Không lấy Authentication của request WebFlux từ `SecurityContextHolder` ThreadLocal như trong cách viết servlet đồng bộ. Hai endpoint `/me/oauth2` và `/me/oidc` cố ý yêu cầu `user_id`; test phải cung cấp thuộc tính đó vì mặc định chỉ có `sub`, tránh xây dựng `Map.of(...)` với giá trị null.

### File 3: `src/test/java/com/example/securitydemo/ProfileControllerTest.java`

~~~java
package com.example.securitydemo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProfileControllerTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void oauth2AttributesAndDefaultPrincipalName() {
        client.mutateWith(mockOAuth2Login()
                        .attributes(attrs -> attrs.put("user_id", "u-42")))
                .get().uri("/me/oauth2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("user")
                .jsonPath("$.userId").isEqualTo("u-42");
    }

    @Test
    void oidcIdTokenClaimAndDefaultPrincipalName() {
        client.mutateWith(mockOidcLogin()
                        .idToken(token -> token.claim("user_id", "u-77")))
                .get().uri("/me/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("user")
                .jsonPath("$.subject").isEqualTo("user")
                .jsonPath("$.userId").isEqualTo("u-77");
    }

    @Test
    void principalAfterOAuth2Login() {
        client.mutateWith(mockOAuth2Login())
                .get().uri("/me/principal")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user");
    }

    @Test
    void authenticationFlowsThroughReactiveContext() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/me/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user");
    }

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/me/principal")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutAdminAuthorityIsForbidden() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminAuthorityAllowsRequest() {
        client.mutateWith(mockOidcLogin()
                        .authorities(new SimpleGrantedAuthority("ROLE_ADMIN")))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void customOAuth2UserControlsPrincipalName() {
        OAuth2User user = new DefaultOAuth2User(
                AuthorityUtils.createAuthorityList("SCOPE_read"),
                Map.of("user_name", "linh", "user_id", "u-42"),
                "user_name");

        client.mutateWith(mockOAuth2Login().oauth2User(user))
                .get().uri("/me/oauth2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("linh")
                .jsonPath("$.userId").isEqualTo("u-42");
    }

    @Test
    void customOidcUserCanUsePreferredUsername() {
        OidcIdToken idToken = OidcIdToken.withTokenValue("fake-id-token")
                .claim("sub", "subject-101")
                .claim("preferred_username", "minh")
                .claim("user_id", "u-99")
                .build();

        OidcUser user = new DefaultOidcUser(
                AuthorityUtils.createAuthorityList("SCOPE_read"),
                idToken,
                "preferred_username");

        client.mutateWith(mockOidcLogin().oidcUser(user))
                .get().uri("/me/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("minh")
                .jsonPath("$.subject").isEqualTo("subject-101")
                .jsonPath("$.userId").isEqualTo("u-99");
    }
}
~~~

Chạy một class test trong dự án Gradle đã được cấu hình Spring Boot (không cần IdP và không cần server thực):

~~~bash
./gradlew test --tests 'com.example.securitydemo.ProfileControllerTest'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.securitydemo.ProfileControllerTest
~~~

Kết quả cần quan sát là **9 bài test thành công**. Các kiểm tra trên đọc HTTP status, response JSON hoặc plain text; chúng không phụ thuộc vào stdout của controller.

## 3. Đọc principal sau khi mock đăng nhập

Có ba góc nhìn cần phân biệt:

1. `@AuthenticationPrincipal OAuth2User`: nhận đối tượng chứa attributes (ví dụ `user.getAttribute("user_id")`) và `getName()`; dùng cho profile OAuth2.
2. `@AuthenticationPrincipal OidcUser`: nhận đối tượng có `getIdToken()`, `getUserInfo()`, `getClaims()`; đọc `sub` từ ID Token khi cần mã định danh từ IdP. `OidcUser` mở rộng `OAuth2User`.
3. `Principal` / `Authentication`: thể hiện danh tính ở lớp security; `OAuth2AuthenticationToken.getPrincipal()` là `OAuth2User` hoặc `OidcUser` tùy request. `getName()` dùng name attribute được cấu hình, nên **không mặc định coi là ID bất biến**.

Ở luồng bất đồng bộ/reactive, `ReactiveSecurityContextHolder.getContext()` lấy SecurityContext gắn với Reactor context. Điều này quan trọng khi xử lý chuyển luồng, gọi service reactive, hoặc thao tác không chạy trên cùng thread với nơi bắt đầu request. `Mono<Principal>` trong controller cũng phản ánh danh tính của request hiện tại.

Ví dụ từ bộ test:

| Request được giả lập | Cách đọc | Giá trị mong đợi |
| --- | --- | --- |
| `mockOAuth2Login()` | `Principal.getName()` | `user` |
| `mockOAuth2Login().attributes(...)` | `OAuth2User.getAttribute("user_id")` | `u-42` |
| `mockOidcLogin().idToken(...)` | `OidcUser.getIdToken().getSubject()` | `user` |
| `mockOidcLogin().idToken(...)` | `OidcUser.getIdToken().getClaimAsString("user_id")` | `u-77` |
| `mockOAuth2Login().oauth2User(...)` | `OAuth2User.getName()` | `linh` |
| `mockOidcLogin().oidcUser(...)` | `OidcUser.getName()` so với `getIdToken().getSubject()` | `minh` so với `subject-101` |

Trong nghiệp vụ, thường dùng cặp `issuer + sub` làm khóa định danh OIDC ổn định trong phạm vi issuer; `preferred_username`, `name`, `email` có thể thay đổi, thiếu hoặc không duy nhất. Test nên khẳng định đúng trường mà nghiệp vụ thật sử dụng.

## 4. Tùy biến cho các kịch bản kiểm thử chuyên sâu

**Authorities / phân quyền.** Các helper cấp mặc định `SCOPE_read`. Muốn test `hasAuthority("ROLE_ADMIN")`, dùng `authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` như ví dụ. `SCOPE_read` khác `ROLE_ADMIN`; nếu policy dùng `hasRole("ADMIN")`, Spring Security tra `ROLE_ADMIN` theo quy ước tiền tố. Thử cả phản hồi 403 khi đã login nhưng thiếu quyền và phản hồi 200 khi có quyền.

**OAuth2 attributes.** `mockOAuth2Login().attributes(attrs -> attrs.put("user_id", "u-42"))` tác động vào thuộc tính của `OAuth2User`. Nếu muốn thay tên chính từ `sub` sang `user_name` hoặc dùng principal tùy chỉnh, tạo `DefaultOAuth2User` với `nameAttributeKey` rồi truyền cho `oauth2User(...)`.

**OIDC claims.** `mockOidcLogin().idToken(token -> token.claim("user_id", "u-77"))` tác động ID Token; `userInfo(...)` tác động UserInfo. Chỉ đọc claim từ đúng nguồn mà code nghiệp vụ thực sự đọc. Trường hợp principal tự định nghĩa hoặc name attribute khác mặc định, tạo `DefaultOidcUser` rồi truyền cho `oidcUser(...)`.

**Client registration / authorized client.** Nếu controller dùng `@RegisteredOAuth2AuthorizedClient`, helper login cung cấp authorized client giả; có thể thay `clientRegistration(ClientRegistration)` để phù hợp registration ID và metadata mà code cần. Nếu đang kiểm thử OAuth2 client chạy độc lập với login của người dùng (như client credentials), dùng `mockOAuth2Client("registration-id")` thay vì coi `mockOAuth2Login()` là tương đương.

**Kiểm thử thật sự theo từng request.** Gắn `mutateWith(...)` đúng vào từng `WebTestClient` request và assert cả response lẫn trạng thái 401/403. Cách này khiến dữ liệu xác thực của từng case rõ ràng, dễ tránh việc test sau vô tình hưởng principal của test trước.

## 5. Các lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` nhận null hoặc không đúng kiểu | Dùng `mockOAuth2Login()` nhưng endpoint yêu cầu OIDC | Dùng `mockOidcLogin()` hoặc điều chỉnh kiểu principal theo logic thật |
| `user_id` null, truy cập attribute không ra dữ liệu | Default helper chỉ đặt `sub` | Thêm `attributes(...)` hoặc `idToken(...)` ở đúng helper |
| Test trả 401 dù đã gọi helper | WebTestClient không tích hợp security filter support hoặc cấu hình request sai | Khi bind thủ công: `.apply(springSecurity())`; kiểm tra dùng đúng API reactive |
| Test trả 403 | Principal đã được xác thực nhưng thiếu authority theo policy | Cấp đúng `SCOPE_*` / `ROLE_*` và assert cả ca thiếu quyền |
| `getName()` khác `sub` | Principal có `nameAttributeKey` tùy biến | Assert riêng name và subject; đừng đồng nhất hai trường |
| `@WithMockUser` không cung cấp `OidcUser` | `@WithMockUser` tạo kiểu Authentication/principal khác | Với controller phụ thuộc OAuth2/OIDC, dùng helper OAuth2/OIDC |
| Đọc context bằng ThreadLocal khi chạy Reactor | SecurityContext của WebFlux được truyền trong Reactor context | Dùng `ReactiveSecurityContextHolder` hoặc tham số principal reactive |
| Test pass nhưng login thật lỗi | Helper không thực hiện redirect, token exchange hoặc validate IdP | Bổ sung integration test riêng với IdP thử nghiệm / mock HTTP provider |

Đừng suy ra `mockOidcLogin()` kiểm tra ID Token hợp lệ về chữ ký, audience, issuer, nonce hoặc expiration. Claims và authorities ở đây là **fixture do bài test quyết định**, không phải kết quả xác minh token thật. Với API resource server nhận Bearer JWT, dùng `mockJwt()` hoặc `mockOpaqueToken()`: đó là mô hình bảo vệ endpoint bằng access token, khác với người dùng đăng nhập qua OAuth2/OIDC Login.

## 6. Checklist thiết kế bài test

- Test endpoint chỉ đọc `Principal.getName()` nếu cần tên đơn giản; test `OAuth2User`/`OidcUser` khi code nghiệp vụ phụ thuộc thuộc tính/claims cụ thể.
- Dựng fixture khớp dữ liệu thật: `sub`, `user_id`, authority, registration và name attribute; có ca thiếu claim, thiếu quyền và anonymous khi nghiệp vụ cần.
- Kiểm tra đúng vị trí claim: `OAuth2User.getAttributes()`, OIDC ID Token hay UserInfo, và phân biệt `name` với `subject`.
- Kiểm tra cả authorization (401/403/200) lẫn nội dung trả về; assert rõ chủ thể mà request nhìn thấy trong Reactor context.
- Chạy thêm kiểm thử tích hợp authorization flow với IdP/thành phần HTTP giả lập nếu mục tiêu là xác nhận cấu hình redirect, token exchange, xác thực ID Token hoặc các hành vi provider.

## Tài liệu chính thức

- [Spring Security — Testing OAuth 2.0 trong ứng dụng reactive](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOAuth2Login()`, `mockOidcLogin()`, claims, authorities và principal tùy chỉnh.
- [SecurityMockServerConfigurers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): các mutator và hợp đồng `SecurityContext` của WebTestClient.

Kết quả cốt lõi: hãy chọn helper dựa trên **kiểu principal mà code thực sự cần**, dựng đúng dữ liệu để kiểm thử quyền và thuộc tính, và xác minh danh tính được truyền qua WebFlux/Reactor từ request đến controller.