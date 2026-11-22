# Chẩn đoán 401 dù đã gửi thông tin xác thực trong Spring Security Reactive

## 1. Mục tiêu: tìm chính xác điểm thất bại thay vì đoán mật khẩu

Một request đến API Spring WebFlux có thể mang `Authorization: Basic ...`, `Authorization: Bearer ...` hoặc cookie phiên mà vẫn nhận `HTTP 401 Unauthorized`. Việc client “đã gửi thông tin xác thực” mới chứng minh **ý định của client**, chưa chứng minh rằng:

1. Credential đã đến đúng ứng dụng sau browser, reverse proxy và gateway.
2. `SecurityWebFilterChain` được chọn thực sự hỗ trợ loại credential ấy.
3. Filter chuyển đổi được dữ liệu request thành đối tượng xác thực.
4. `ReactiveAuthenticationManager`/JWT decoder/user service xác minh thành công.
5. `Authentication` đã được đưa vào đúng Reactor Context trước khi kiểm quyền.
6. Thành phần trả về 401 là Spring Security, hay một gateway/upstream khác.

Bài học thuộc nhóm **Chuyển đổi và gỡ lỗi**: nhấn mạnh chẩn đoán có bằng chứng khi chuyển từ Servlet sang WebFlux hoặc từ Basic/session login sang Bearer JWT. Mục tiêu cuối là chỉ được **vị trí thất bại + nguyên nhân + cách khắc phục + test hồi quy**, không chữa triệu chứng bằng `permitAll()` hoặc tắt cơ chế bảo vệ.

## 2. Đọc đúng mã HTTP trước khi sửa cấu hình

| Mã/biểu hiện | Ý nghĩa thường gặp | Bước kiểm tra kế tiếp |
| --- | --- | --- |
| **401** | Chưa xác thực thành công, thiếu/không hợp lệ credential, hoặc entry point yêu cầu đăng nhập | `WWW-Authenticate`, bộ lọc xác thực, token/password, phiên |
| **403** | Đã xác thực nhưng không đủ quyền, hoặc request bị CSRF/CORS/security policy từ chối | `GrantedAuthority`, `hasRole`/`hasAuthority`, CSRF, CORS |
| **302** tới login/IdP | Flow đăng nhập trên browser đang chuyển hướng | `Location`, session cookie, callback, saved request |
| **404** | Router/path/route không tồn tại hoặc sai prefix | URL qua proxy, controller mapping, gateway |
| **5xx** | Lỗi từ gateway, decoder, IdP/JWK endpoint, ứng dụng hoặc hạ tầng | Server logs, trace ID, dependency và stack trace |

Đây là các quy ước **thường thấy**, không phải định lý: ứng dụng có thể cài `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler` riêng hoặc gateway đổi mã lỗi. Vì thế cần xác định **ai tạo response** trước khi quy kết.

`401` là **Unauthorized** theo tên HTTP, nhưng về ý nghĩa thường là authentication chưa được chấp nhận. Theo giao thức HTTP, response 401 thường mang một hoặc nhiều challenge `WWW-Authenticate` (như `Basic realm="..."` hay `Bearer error="invalid_token"`); header này giúp phân biệt cơ chế bảo vệ. Không suy luận rằng body rỗng đồng nghĩa request chưa qua security filter.

Với Bearer, token hợp lệ mà thiếu scope thường dẫn đến **403** (có thể có `insufficient_scope`), trong khi JWT hết hạn/chữ ký sai thường dẫn đến **401** (có thể có `invalid_token`). CORS preflight xử lý sai có thể thành 401 hoặc lỗi hiển thị như “CORS error” trong browser; CSRF token thiếu ở POST thường thành 403. Cần xem response thật, không chỉ nhìn dòng lỗi trên frontend.

## 3. Đường đi của request qua WebFlux Security

```text
Client/Browser/WebClient
    |
    v
Reverse proxy / API gateway
    |   Header Authorization/Cookie có được giữ nguyên?
    v
WebFlux WebFilter chain
    |
    v
Spring Security WebFilterChainProxy
    |   Chọn đúng SecurityWebFilterChain theo securityMatcher và @Order?
    v
Authentication WebFilter (Basic / Bearer / OAuth2 login / ...)
    |   Đọc được credential? Đúng scheme?
    v
ReactiveAuthenticationManager / ReactiveJwtDecoder / user store
    |   Mật khẩu/chữ ký/issuer/thời gian/validation hợp lệ?
    v
Authentication trong ReactiveSecurityContextHolder (Reactor Context)
    |   Authenticated và authorities đúng?
    v
AuthorizationWebFilter / Reactive method security
    |   Quyền/role/scope/owner đủ?
    v
Handler -> Response
```

Khi thất bại xác thực, Spring Security chuyển tới cơ chế xử lý authentication failure/entry point phù hợp. Khi thiếu quyền, cơ chế access-denied tham gia. **Một `SecurityWebFilterChain` được chọn cho mỗi request**: cấu hình Bearer ở chain khác không giúp request đang khớp chain Basic. Và `pathMatchers` trong `authorizeExchange` quyết định **quyền truy cập bên trong chain đã chọn**; nó không tự thay `securityMatcher` của chain.

Trong Reactive, `ReactiveSecurityContextHolder` lưu/đọc `SecurityContext` theo **Reactor Context của subscriber**. `SecurityContextHolder.getContext()` kiểu Servlet/`ThreadLocal` không phải nguồn xác thực đáng tin cậy trong WebFlux. Đổi thread bằng `publishOn` trong một chuỗi Reactor hợp lệ không tự động đánh mất Context; làm gãy chuỗi bằng `subscribe()` riêng, callback ngoài Reactor hoặc dùng state toàn cục mới thường gây lỗi context.

## 4. Quy trình chẩn đoán năm chặng

### Chặng 1 — Quan sát response thật và nơi trả lỗi

Dùng request tối giản, **không tự theo redirect** để tránh che mất response ban đầu. Ví dụ endpoint nội bộ đang dùng Basic:

```bash
# Không có credential; dự kiến 401 khi endpoint được bảo vệ bằng Basic.
curl -i http://localhost:8080/api/me

# curl hỏi mật khẩu từ terminal nếu chỉ truyền username.
curl -i --user alice http://localhost:8080/api/me
```

Đối với Bearer token thử nghiệm đã được cấp hợp lệ:

```bash
# ACCESS_TOKEN được cấp vào môi trường test trước đó; không in token ra log.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/me
```

Các lệnh ví dụ trên theo shell Bash. Với PowerShell, tham chiếu biến môi trường là `$env:ACCESS_TOKEN` và có thể gọi `curl.exe` để dùng đúng CLI của curl. Không đưa token, password thật vào command history, URL query, ảnh chụp log hoặc ticket. Không dùng `curl -L` khi cần quan sát redirect đầu tiên; cũng không bật trace thô có thể ghi toàn bộ Authorization.

Ghi lại **timestamp, correlation/request ID, method, public URL, status, `WWW-Authenticate`, `Location`, `Server`/gateway headers và body đã khử thông tin nhạy cảm**. So sánh:

- Request trực tiếp tới app ở mạng test tin cậy (nếu cho phép) với request đi qua public gateway.
- Kết quả cùng credential nhưng khác path (ví dụ `/api/me` và `/web/me`).
- Ứng dụng có nhận được request không (access log, trace ID được gắn xuyên proxy)?

Nếu ở gateway nhận 401 mà ứng dụng **không có request tương ứng**, điều tra cấu hình gateway/auth policy trước; đừng sửa `SecurityWebFilterChain`.

### Chặng 2 — Xác minh credential thực sự đến upstream

Với Bearer, cú pháp mặc định là:

```http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...<token-redacted>
```

Với Basic, request dùng scheme `Basic` kèm Base64 của `username:password`; Base64 **không phải mã hóa**, nên chỉ gửi qua HTTPS. Không nhầm `Proxy-Authorization` với `Authorization` của ứng dụng: một số proxy dùng header khác để xác thực proxy và có thể xóa/đổi header gửi upstream.

Kiểm các lỗi truyền tải thường gặp:

- Frontend chỉ **tạo token** nhưng không gắn `Authorization` vào request API thật, hoặc gắn header vào request A nhưng request B được tạo từ HTTP client khác.
- Có dấu cách/quote/dòng mới sai trong Bearer header; `Bearer undefined`, `Bearer null`, hoặc token được mã hóa Base64 thêm một lần.
- Browser chuyển hướng sang origin khác và không giữ header nhạy cảm như kỳ vọng; so sánh URL cuối cùng của request.
- API gateway, ingress hoặc reverse proxy không forward `Authorization` hay thay bằng credential nội bộ; kiểm chính sách forwarding trên hop đáng tin cậy.
- `WebClient` gọi service B nhưng chỉ xác thực **request vào service A**. Header Bearer không tự “lan truyền” sang mọi outbound `WebClient`.
- Trường hợp browser session login, cookie không được gửi vì `SameSite`, `Secure`, `Path`, `Domain`, `credentials`, phiên hết hạn hoặc sai host.

Khi muốn xác nhận header có tồn tại ở ứng dụng, chỉ ghi **Boolean** như `authorizationPresent=true` hoặc loại scheme sau khi lọc, cộng request ID. Không in nguyên token/Basic value, cookie, header toàn bộ hay authorization code.

### Chặng 3 — Kiểm chain được chọn và kiểu xác thực đã bật

Một endpoint `/api/**` dùng JWT cần chain cấu hình `oauth2ResourceServer(...jwt...)`. Chỉ có `oauth2Login(...)` nghĩa là ứng dụng hỗ trợ login OAuth2 cho browser, **không tự động biến endpoint thành JWT Resource Server**. Chỉ bật `httpBasic()` cũng không khiến `Authorization: Bearer ...` được giải mã.

Trong Spring Boot, tự khai báo `SecurityWebFilterChain` có thể thay thế default filter chain của auto-configuration. Vì vậy việc có dependency hay property `issuer-uri` không chứng minh request đang đi vào chain xử lý JWT; hãy xem bean/`@Order`/`securityMatcher` thực tế.

Ví dụ nhiều chain (đoạn cấu hình để lồng vào một class `@Configuration @EnableWebFluxSecurity`, yêu cầu JWT decoder đã được cấu hình):

```java
@Bean
@Order(0)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(1)
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Các import bổ sung chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

**Cảnh báo cấu hình:** đây là minh họa **hai chain khác cơ chế**, không phải thay thế tùy tiện cho cấu hình production đang dùng. Cần dependency `spring-boot-starter-oauth2-resource-server`, cấu hình `ReactiveJwtDecoder` từ issuer/JWK phù hợp, và kiểm các endpoint ngoài `/api/**`. Nếu có public prefix proxy, kiểm URL/path mà ứng dụng thực sự nhận khi khớp matcher. Không đặt một catch-all chain có thứ tự ưu tiên cao hơn khiến chain dành cho `/api/**` không bao giờ được chọn.

### Chặng 4 — Phân tích xác minh credential và tạo Authentication

Kiểm đúng theo loại credential, **không suy đoán vì header nhìn có vẻ hợp lệ**.

#### HTTP Basic / username-password

- Server phải bật `httpBasic(...)` ở chain khớp request.
- Spring Security phải có `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` thích hợp, user đang enabled/unlocked và mật khẩu khớp `PasswordEncoder`.
- Với `DelegatingPasswordEncoder`, password lưu trữ thường có prefix như `{bcrypt}...`. Giá trị không có prefix/encoder không tương thích gây xác thực thất bại hoặc lỗi cấu hình; đừng chuyển sang plaintext ở production.
- Nếu dùng login form, verify POST đăng nhập, session cookie và CSRF riêng; gửi credential HTTP Basic vào ứng dụng chỉ hỗ trợ form login có thể không hoạt động.

#### JWT Bearer Resource Server

- Header mặc định là `Authorization: Bearer <access-token>`. Các custom header hoặc query param không tự được dùng nếu chưa cấu hình `ServerBearerTokenAuthenticationConverter`; nên ưu tiên header chuẩn.
- JWT phải đúng định dạng, chữ ký/alg/kid phù hợp khóa public từ JWK Set, `iss` đúng issuer kỳ vọng, `exp`/`nbf` hợp lệ và đồng hồ server chính xác.
- `aud` là một điều kiện bảo mật đáng kiểm cho API của bạn, **nhưng không mặc định được xác minh bởi mọi cấu hình Resource Server**; phải cấu hình validator audience theo hợp đồng hệ thống.
- Token của môi trường staging, ID token của OIDC, hoặc refresh token **không mặc nhiên là access token** được API chấp nhận.
- JWK endpoint không truy cập được có thể khiến decoder thất bại theo nhiều cách, thậm chí thành 5xx tùy loại lỗi; kiểm exception/log thật trước khi gắn nhãn “token sai”.
- JWT hợp lệ nhưng thiếu scope/role chủ yếu là **vấn đề authorization**, thường trả 403, không phải phải sửa chữ ký/issuer.
- Với opaque token, dùng introspection (`ReactiveOpaqueTokenIntrospector`) thay vì JWT decoder; kiểm URI, xác thực client, trạng thái active/expiry và lỗi mạng.

Ví dụ resource server dùng JWT với Spring Boot (đoạn `application.yml` minh họa; issuer phải là giá trị đúng của môi trường):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/api
```

Với `issuer-uri`, Spring có thể dùng metadata để tìm JWK Set và kiểm `iss`. Nếu server không công bố discovery tương thích, cấu hình `jwk-set-uri` và validator issuer theo tài liệu; không “chữa 401” bằng cách vô hiệu hóa signature/expiry/issuer validation.

#### WebSession/cookie sau login OAuth2/OIDC

- Đã redirect từ IdP về callback **không có nghĩa** request gọi API tiếp theo đang có authenticated WebSession.
- Mở DevTools → Network; xác nhận `Set-Cookie` từ ứng dụng được browser chấp nhận và cookie được gửi trong request API cần xác thực.
- Với cross-origin `fetch` có cookie, cấu hình `credentials: 'include'` ở client khi phù hợp và CORS credentials + origin allowlist ở server; same-origin fetch thường có default credentials riêng.
- Nếu sau callback 401, kiểm `SameSite`, `Secure`, `Path`, domain, session TTL, cache/store và nhiều replica; `invalid_state`/redirect loop thường là dấu hiệu mất session.
- Phân biệt cookie **session** với cookie **CSRF**. Có cookie CSRF không đảm bảo đã đăng nhập; có session cookie cũng không đảm bảo session chưa hết hạn.

### Chặng 5 — Xác định lỗi quyền hay mất Reactor Context

Khi authentication đã thành công:

- Với JWT, Spring thường ánh xạ `scope`/`scp` sang authority dạng `SCOPE_orders.read`. `hasRole("ADMIN")` tìm `ROLE_ADMIN`, khác `hasAuthority("ADMIN")`. Thiếu scope/role là lý do của **403**, không chứng minh token không hợp lệ.
- Với endpoint có `@PreAuthorize`, kiểm reactive method security đã bật và method được proxy xử lý theo cơ chế Reactive. Kiểm cả URL rule và method rule.
- Với WebFlux, để đọc principal trong pipeline, sử dụng `ReactiveSecurityContextHolder.getContext()` hoặc các tham số principal của WebFlux. Không đọc `SecurityContextHolder` dựa vào thread để kết luận user anonymous.
- Nếu controller bắt đầu với `Authentication` hợp lệ nhưng service tiếp theo không có context, tìm `subscribe()` lồng nhau, callback ngoài chuỗi Reactor hoặc publisher được tạo và subscribe độc lập. `publishOn` tự nó không phải bằng chứng mất context.
- Nếu response 401 xảy ra **trước khi controller được gọi**, ưu tiên kiểm converter/manager/chain/gateway hơn là phỏng đoán context mất bên trong nghiệp vụ.

## 5. Ví dụ Java 17+ chạy được: phân biệt thiếu credential, sai credential và thiếu quyền

Fixture sau là một ứng dụng WebFlux tối giản chạy trong JUnit 5, có Basic authentication và endpoint `/api/me`. Để tái hiện 401/403 **không cần JWT issuer thật**, test tách rõ từng trạng thái:

- Không header Basic → **401**.
- Basic với mật khẩu sai → **401**.
- Bearer string gửi vào chain chỉ hỗ trợ Basic → **401**.
- Basic đúng vào `/api/me` → **200** và body là principal.
- Basic đúng nhưng không có role ADMIN vào `/api/admin` → **403**.

Tệp `src/test/java/example/security/Reactive401DiagnosticTest.java`:

```java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = Reactive401DiagnosticTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class Reactive401DiagnosticTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicPasswordReturns401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void bearerIsNotAcceptedByBasicOnlyChain() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("not-a-jwt"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctBasicCredentialsReturnPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "correct"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void validUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "correct"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, ProbeController.class})
    static class TestApplication {}

    @Configuration(proxyBeanMethods = false)
    @EnableWebFluxSecurity
    static class SecurityConfig {

        @Bean
        SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(ex -> ex
                            .pathMatchers("/api/admin").hasRole("ADMIN")
                            .pathMatchers("/api/**").authenticated()
                            .anyExchange().denyAll())
                    .httpBasic(Customizer.withDefaults())
                    .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                    .build();
        }

        @Bean
        MapReactiveUserDetailsService users() {
            return new MapReactiveUserDetailsService(
                    User.withUsername("alice")
                            .password("{noop}correct")
                            .roles("USER")
                            .build());
        }
    }

    @RestController
    static class ProbeController {

        @GetMapping("/api/me")
        Mono<String> currentPrincipal() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(context -> context.getAuthentication().getName());
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin");
        }
    }
}
```

**Giải thích kỹ fixture:** `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` chạy WebFlux WebFilter chain của context thật; `setBasicAuth` tạo đúng header Basic; `MapReactiveUserDetailsService` cung cấp user test cố định; `ReactiveSecurityContextHolder` chứng minh controller nhìn thấy authentication theo Reactor Context. `{noop}` chỉ chấp nhận được với **credential giả trong bài test**, tuyệt đối không chọn cách lưu mật khẩu này ở production.

Hai test 401 trả lời hai câu hỏi khác nhau: “có header hay không” và “header có được manager chấp nhận không”. Test Bearer trên Basic-only chain cho thấy **header Authorization có tồn tại mà không có Authentication hợp lệ**. Test 403 chứng minh credential hợp lệ nhưng thiếu quyền là lỗi khác với authentication.

### Dependency và lệnh chạy

Ghép các dependency vào `build.gradle` của Spring Boot 3.x đang dùng BOM của Boot; không cần khai báo version riêng nếu project đã quản lý:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Chạy ở project có wrapper và các dependency tương thích:

```bash
./gradlew test --tests 'example.security.Reactive401DiagnosticTest'
```

Trên Windows dùng `gradlew.bat test --tests "example.security.Reactive401DiagnosticTest"`. Kỳ vọng **5 test PASS** (không có dòng stdout nghiệp vụ bắt buộc); nếu bất kỳ status khác dự kiến, kiểm classpath/filter chain hoặc bản build thực tế. Đây là fixture test không kết nối gateway thật, không kiểm signature JWT và không kiểm browser cookie policy.

## 6. Kiểm tra riêng trường hợp Bearer JWT

### 6.1. Mẫu WebFlux Resource Server

Cấu hình mẫu Java 17+ cho API chấp nhận JWT; đây là class cấu hình đầy đủ nhưng **vẫn cần issuer/JWK endpoint có thật** trong runtime:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class JwtApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Thêm `spring-boot-starter-oauth2-resource-server` và `issuer-uri` như mục 4. Nếu dùng các chain khác nhau, thêm `securityMatcher`/`@Order` như ví dụ nhiều chain; việc cấp quyền cho `/api/public/**` không tự cho phép những endpoint ngoài matcher ở chain khác.

**Khi JWT thật trả 401**, kiểm theo thứ tự:

1. Đúng `Bearer` scheme, không có tiền tố lặp, không bị gateway sửa.
2. Header JWT `alg`/`kid` có tương thích key set/trust policy, không chấp nhận `alg=none`.
3. `iss` khớp issuer cấu hình đúng từng ký tự; `exp`/`nbf` và thời gian hệ thống không lệch bất thường.
4. Token thuộc đúng môi trường và đúng loại access token; đối chiếu `aud` với audience API yêu cầu, và cấu hình audience validator nếu cần.
5. Có thể truy cập IdP discovery/JWKS từ server, đúng HTTPS/certificate, cache và key rotation.
6. Log exception đã khử dữ liệu nhạy cảm chỉ ra `JwtValidationException`/decoder/HTTP 401 hay vấn đề hạ tầng khác. Không kết luận root cause chỉ từ mã 401.

**JWT nhìn thấy bằng cách decode Base64URL không chứng minh chữ ký hợp lệ**. Không copy token của người dùng lên trang JWT decoder không được tin cậy. Nếu cần xem claims, dùng công cụ local được tổ chức cho phép và không tiết lộ token; chữ ký/issuer/time/audience phải được hệ thống kiểm trên server.

### 6.2. Mock JWT và token thật kiểm những thứ khác nhau

`spring-security-test` có `mockJwt()` để kiểm rule authorization ở WebFlux khi đã có resource-server setup:

```java
// Đoạn test minh họa trong class đã có client + chain Resource Server.
// Không kiểm tra chữ ký/issuer/expiry của token thật.
client.mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("scope", "orders.read")))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
```

Import static:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
```

Giả lập authentication chỉ chứng minh endpoint và security rule hoạt động **khi đã có một Authentication phù hợp**. Muốn chẩn đoán 401 do xác minh token, bổ sung integration test với JWT thật đã ký bởi khóa test và decoder configured đúng, gồm token hợp lệ, hết hạn, issuer sai, signature sai, aud sai khi API kiểm aud. Không tuyên bố “JWT xác thực chuẩn” chỉ vì `mockJwt()` PASS.

## 7. Những điểm dễ bỏ sót khi chuyển Servlet → Reactive

| Cách làm quen thuộc trong Servlet | Cách kiểm ở WebFlux Reactive | Nếu bỏ sót |
| --- | --- | --- |
| `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` | Cấu hình cũ không bảo vệ WebFlux theo mong đợi |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Security chain Reactive không được cấu hình đúng |
| `UserDetailsService` | `ReactiveUserDetailsService` | Manager không dùng được nguồn user Reactive như mong đợi |
| `JwtDecoder` | `ReactiveJwtDecoder` | Resource Server Reactive thiếu decoder phù hợp |
| `SecurityContextHolder` qua `ThreadLocal` | `ReactiveSecurityContextHolder` qua Reactor Context | Đọc nhầm anonymous/không tìm được Authentication |
| Servlet `Filter`/`OncePerRequestFilter` | WebFlux `WebFilter`/Security WebFilter | Custom xác thực không chạy trên reactive request |
| MVC `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` khi dùng reactive method authorization | Kiểm quyền ở method không áp dụng đúng |
| `HttpSession`, `JSESSIONID` | `WebSession` và cookie/session manager theo WebFlux | Browser gửi cookie nhưng server không tìm được phiên |

**Không thể sửa 401 chỉ bằng đổi import**. Khi chuyển mã nguồn, cần kiểm toàn bộ đường đi: filter chain chọn đúng → converter → reactive manager/decoder → context → authorization. Một ứng dụng có cả MVC và WebFlux dependency có thể chọn web application type không như kỳ vọng; kiểm startup logs, dependency tree và framework thực sự xử lý HTTP inbound.

## 8. CORS, CSRF và browser: đừng nhầm các lớp lỗi

### 8.1. CORS preflight

Một SPA ở `https://ui.example.com` gọi API `https://api.example.com` với header Authorization có thể khiến browser tự gửi **OPTIONS preflight** trước GET/POST:

```http
OPTIONS /api/me HTTP/1.1
Origin: https://ui.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight này **không mang Bearer token hoặc cookie session** như request API thực. Nếu security xử lý trước CORS và bắt authentication cho OPTIONS, browser có thể báo CORS và không gửi request chính. Spring Security hướng dẫn cho WebFlux là xử lý CORS **trước** security, thường thông qua cấu hình CORS/`CorsWebFilter` đúng. Đừng giải pháp hóa bằng cách tắt toàn bộ authentication hoặc cho phép mọi origin có credential.

Kiểm preflight độc lập:

```bash
curl -i -X OPTIONS https://api.example.com/api/me \
  -H "Origin: https://ui.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Kỳ vọng status/`Access-Control-Allow-Origin`/`Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` phù hợp với chính sách của ứng dụng. Preflight qua cổng public có thể bị gateway chặn trước Spring; đối chiếu trace.

### 8.2. CSRF

Nếu `POST`/`PUT`/`DELETE` với cookie/session thành 403 nhưng `GET` 200, kiểm CSRF token, header/form field và session trước. Spring Security WebFlux có bảo vệ CSRF; đừng tắt cho toàn ứng dụng để biến 403 thành 200. Với API Bearer stateless, cân nhắc policy CSRF dựa trên cách browser tự gửi credential và threat model, chứ không dựa duy nhất vào chữ “REST”.

### 8.3. Browser session khác Bearer JWT

Với browser login, sau khi callback OAuth2 thành công, API nhận cookie phiên hợp lệ mới có authenticated session. Nếu UI dùng fetch tới API host khác, `credentials`/CORS/SameSite và cookie scope quyết định cookie có đi theo hay không. Nếu SPA lưu token trong bộ nhớ và tự gắn Bearer header, cookie session lại không liên quan đến request đó. Phải xác định app đang dùng **mô hình nào** trước khi chữa lỗi.

## 9. WebClient gọi service khác: 401 xuất hiện ở downstream

Ví dụ request vào **service A** được xác thực, nhưng bên trong A dùng `WebClient` gọi **service B** và B trả 401. 401 đó không nhất thiết đến từ A; token của request đầu vào không tự gắn lên outbound WebClient.

Nếu A là JWT Resource Server và policy cho phép chuyển access token đến B, Spring Security cung cấp `ServerBearerExchangeFilterFunction`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamClientConfig {

    @Bean
    WebClient downstreamClient(WebClient.Builder builder) {
        return builder
                .filter(new ServerBearerExchangeFilterFunction())
                .build();
    }
}
```

Chỉ dùng propagation này khi B là **audience/recipient hợp lệ** của token và chính sách bảo mật cho phép. Với service-to-service hoặc token exchange, có thể cần credential/token riêng từ `ReactiveOAuth2AuthorizedClientManager` thay vì chuyển token của người dùng. Filter function chỉ có thể lấy Bearer token khi ngữ cảnh xác thực hiện tại chứa token phù hợp; callback ngoài Reactor hoặc mất context có thể khiến outbound request thiếu token.

Để chẩn đoán: ghi correlation ID giữa A→B, status do B trả, header **có/không** ở phía B và đúng authorization policy, tuyệt đối không log raw token. Test cần phân biệt: A trả 401 tại inbound, hay A trả body lỗi sau khi B trả 401.

## 10. Bảng tra nguyên nhân từ dấu hiệu thực tế

| Dấu hiệu | Giả thuyết ưu tiên | Bằng chứng và hướng xử lý |
| --- | --- | --- |
| Browser gửi header, Spring không thấy | Gateway/proxy strip hoặc request khác origin | Đối chiếu trace ID và sự hiện diện header ở từng hop tin cậy |
| Basic đúng trên `/web`, 401 trên `/api` | Hai chain chọn cơ chế khác nhau | Xem `@Order` và `securityMatcher`, không mặc định cả app dùng Basic |
| Bearer nào cũng 401 | Không bật Resource Server, header converter sai hoặc decoder sai | Kiểm chain và `ReactiveJwtDecoder` trước khi đổi token |
| JWT chỉ lỗi sau khi đổi môi trường | `iss`/`aud`/JWK/clock không khớp | Đối chiếu token metadata với issuer và validator của môi trường |
| JWT đã xác minh, endpoint vẫn từ chối | Thiếu scope/role hoặc method security | Xem `Authentication.getAuthorities()` sau khử dữ liệu; thường là 403 |
| Login web thành công nhưng API 401 | Cookie không gửi hoặc session hết hạn | DevTools cookie, `SameSite`/`Secure`/`Path`/`Domain`/TTL |
| Postman/curl được, browser lỗi CORS | OPTIONS preflight bị chặn hoặc CORS không cho origin/header | Kiểm preflight riêng; CORS trước security |
| GET 200, POST 403 | CSRF token thiếu/sai, hoặc rule riêng cho method | Kiểm CSRF và HTTP method rule, không vội đổ cho authentication |
| Sau proxy có 401, gọi trực tiếp app 200 | Gateway authorization hoặc mất header | Xác định hop tạo response và policy forwarding |
| Service A authentication OK, gọi service B 401 | WebClient không gửi token hoặc token không dành cho B | Phân biệt inbound/outbound auth, audience và client config |
| Trên Reactor thread khác principal trống | Dùng ThreadLocal Servlet hoặc tách subscription | Dùng `ReactiveSecurityContextHolder` và giữ một reactive chain |
| Lỗi chỉ xảy ra ở vài pod | Config/keys/clock/session store khác replica | So sánh deployment config, clock, session persistence từng replica |

## 11. Logging và kiểm thử hồi quy an toàn

Bật mức debug trong **test/staging được kiểm soát** khi cần, ví dụ:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Nếu cần TRACE, chỉ dùng trong khoảng chẩn đoán ngắn với lưu trữ truy cập hạn chế; một số thư viện/gateway/HTTP client có thể ghi headers hoặc dữ liệu nhạy cảm ở mức trace. Khôi phục cấu hình logging sau khi tìm được lỗi. Không in token, password, cookie/session ID, client secret, authorization code, chữ ký hoặc Authorization header đầy đủ.

Mỗi lần tái hiện nên ghi:

1. **Request ID**, HTTP method, public path, auth scheme (không nội dung credential), status và nguồn response.
2. Chain phù hợp, filter/manager/decoder thực sự chạy, có tìm thấy user/token hay không.
3. Authentication result: authenticated/anonymous, authority names chỉ khi phù hợp chính sách bảo mật, error class đã loại dữ liệu nhạy cảm.
4. Kiểm URL/headers qua proxy và session/browser nếu nguồn xác thực liên quan.
5. Test sau sửa: missing → 401; malformed/wrong credential → 401; valid credential → 200; valid but insufficient privilege → 403; CORS preflight hoạt động; credential không rò sang service không được phép.

Không thay `AuthenticationEntryPoint` sang 200/302/403 chỉ để “hết 401”; entry point tùy biến chỉ được dùng khi thiết kế response chính thức yêu cầu và tests xác nhận giao thức không sai lệch. Không bỏ issuer/expiry/signature validation, CSRF, hoặc quyền của endpoint.

## 12. Quy trình quyết định nhanh

```text
START: client nói đã gửi credential nhưng nhận 401
 |
 +-- Có response/trace ở Spring WebFlux không?
 |      +-- KHÔNG: kiểm gateway, proxy, ingress, route, hop tạo 401
 |      +-- CÓ:
 |           |
 |           +-- Upstream nhận đúng Authorization/Cookie không?
 |           |      +-- KHÔNG: kiểm browser/client, redirect, WebClient, proxy
 |           |      +-- CÓ:
 |           |           |
 |           |           +-- Request khớp chain có đúng auth scheme không?
 |           |           |      +-- KHÔNG: sửa @Order/securityMatcher và Basic/Bearer/login
 |           |           |      +-- CÓ:
 |           |           |           |
 |           |           |           +-- Converter/manager/decoder xác thực OK?
 |           |           |           |      +-- KHÔNG: password/issuer/exp/nbf/JWK/token type
 |           |           |           |      +-- CÓ: kiểm Authentication/authorities,
 |           |           |           |                rule URL/method, custom entry point,
 |           |           |           |                và response có phải 403 không
 |
 +-- Chỉ browser bị lỗi? kiểm CORS preflight/cookie/CSRF
 +-- Chỉ downstream bị lỗi? kiểm credential propagation và audience
 +-- Sau sửa: chạy test 401/200/403 và request qua đường public
```

## 13. Checklist trước khi chốt một lỗi 401

- [ ] Có bằng chứng về **nơi trả 401**, response headers và request ID; không đoán từ màn hình frontend.
- [ ] Xác nhận credential đến đúng hop, đúng path, đúng `Authorization` scheme hoặc cookie scope.
- [ ] Xác nhận `SecurityWebFilterChain` **thực sự khớp** và hỗ trợ đúng phương thức auth.
- [ ] Với Basic: kiểm reactive user store, password encoder, account state, không chuyển plaintext vào production.
- [ ] Với JWT: kiểm decoder/issuer/exp/nbf/key/JWK và audience policy; phân biệt access token với ID token.
- [ ] Với browser: kiểm preflight CORS, session cookie, CSRF riêng; không đồng nhất 401 với 403.
- [ ] Với WebClient: phân biệt auth inbound/outbound và nguyên tắc token audience.
- [ ] Dùng `ReactiveSecurityContextHolder` đúng chuỗi Reactor; không trông cậy Servlet ThreadLocal.
- [ ] Có test tự động cho 401 thiếu/sai credential, 200 credential hợp lệ, 403 thiếu quyền và integration qua proxy/IdP nếu phù hợp.
- [ ] Thông tin nhạy cảm được che trên log và ticket; bản sửa không giảm hiệu lực bảo vệ.

## Tài liệu tham khảo

- [Spring Security — WebFlux Security Configuration, nhiều SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest và thứ tự rule](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — Testing Authentication qua WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html).
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- [Spring Security — Testing OAuth2/JWT bằng mockJwt](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html).
- [Spring Security — CORS trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [Spring Security — CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Reactor — Context and Context-Propagation](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
