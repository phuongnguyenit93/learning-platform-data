# mockJwt để kiểm tra phân quyền bằng JWT giả lập

Một endpoint WebFlux yêu cầu scope `SCOPE_reports:read`. Bạn muốn kiểm tra người có scope được đọc báo cáo, còn người thiếu scope nhận `403 Forbidden`. Để tập trung vào authorization, có thể dùng `mockJwt()` của `spring-security-test` để cấp một `JwtAuthenticationToken` giả lập cho request `WebTestClient`.

`mockJwt()` giúp mô phỏng JWT và authorities trong ngữ cảnh bảo mật của một request Reactive. Nó rất hữu ích khi kiểm tra rule phân quyền, controller, service và method security. Tuy nhiên, mock này không kiểm tra chữ ký JWT, issuer, audience, thời hạn token hoặc quá trình đọc header `Authorization: Bearer` của một server đang chạy thật. Bài học này làm rõ ranh giới đó và hướng dẫn viết cả ca được phép lẫn bị từ chối.

Bài học thuộc chương **OAuth2 Reactive** của module **SPRING_SECURITY_TESTING**. Module tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive; nội dung ở đây tập trung vào JWT giả lập trong WebFlux, `WebTestClient`, `ReactiveSecurityContextHolder` và quyết định authorization theo scope/authority.

## 1. mockJwt() là gì?

`mockJwt()` là một request configurer thuộc `SecurityMockServerConfigurers` trong package:

~~~java
org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers
~~~

Nó được dùng với `WebTestClient` để cấp một JWT giả lập và authentication tương ứng cho request. Sau khi được áp dụng, code xử lý request có thể nhận `JwtAuthenticationToken` trong Reactive Security Context.

Cách dùng cơ bản:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient
        .mutateWith(mockJwt())
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Đoạn trên giả định endpoint `/api/reports` cho phép JWT giả lập mặc định. Trong test thực tế, nên cấu hình claim và authority tường minh để ca kiểm thử thể hiện rõ chính sách mà endpoint yêu cầu.

Một số điểm cần nhớ:

- `mockJwt()` cấp JWT giả lập cho **một request** được cấu hình bằng `mutateWith(...)`.
- Nó tạo ngữ cảnh xác thực phục vụ request test, không đăng nhập vào một Authorization Server.
- Nó không cần một JWT đã ký bằng private key thật để tạo mock authentication.
- Nó không tự chứng minh `JwtDecoder` hoặc validator của ứng dụng hoạt động đúng.
- Mỗi test có thể cấp một JWT với subject, claims và authorities khác nhau.

`mockJwt()` dành cho **OAuth2 Resource Server sử dụng JWT**. Nếu ứng dụng kiểm thử OAuth2 Client Login hoặc OIDC Login, hãy dùng configurer phù hợp với mô hình đăng nhập đó; JWT Resource Server mock không thay thế quy trình OAuth2/OIDC login.

Đừng nhầm configurer Reactive này với request postprocessor `jwt()` của MockMvc:

| Môi trường | API test JWT | Cách gắn vào request |
| --- | --- | --- |
| Servlet + MockMvc | `SecurityMockMvcRequestPostProcessors.jwt()` | `mockMvc.perform(get(...).with(jwt()))` |
| Reactive + WebTestClient | `SecurityMockServerConfigurers.mockJwt()` | `webTestClient.mutateWith(mockJwt()).get()...` |

Cả hai đều có thể tạo JWT authentication giả lập để kiểm tra authorization. Chúng thuộc hai bộ API test khác nhau và không thay thế decoder/validator khi cần xác minh token thật.

## 2. Thiết lập WebTestClient có tích hợp Spring Security

Để `mockJwt()` hoạt động, `WebTestClient` cần được tích hợp với Spring Security WebFlux. Một cách phổ biến là bind client vào `ApplicationContext` và áp dụng `springSecurity()`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

abstract class ReactiveSecurityTestBase {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient webTestClient;

    @BeforeEach
    void setUpWebTestClient() {
        webTestClient = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(SecurityMockServerConfigurers.springSecurity())
                .configureClient()
                .build();
    }
}
~~~

Đây là mẫu thiết lập cho test có Spring WebFlux application context. Trong một dự án Spring Boot, có thể dùng `@SpringBootTest` hoặc `@WebFluxTest` cùng cấu hình test phù hợp; nếu dùng slice test, cần import controller và security configuration cần thiết.

Ví dụ một cấu hình Resource Server Reactive bảo vệ endpoint theo scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
class ReactiveResourceServerConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/reports")
                            .hasAuthority("SCOPE_reports:read")
                        .anyExchange().authenticated()
                )
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        jwt -> { }
                ))
                .build();
    }
}
~~~

Cấu hình trên giả định ứng dụng đã có cấu hình `ReactiveJwtDecoder` phù hợp, ví dụ từ issuer URI, JWK Set URI hoặc một bean decoder do ứng dụng cung cấp. Trong test dùng `mockJwt()`, request configurer cấp authentication giả lập; server không cần giải mã một bearer token thật cho request đó. Khi kiểm thử xác thực JWT thực, phải dùng request có bearer token đi qua decoder.

Trong các ví dụ tiếp theo, giả định `WebTestClient` đã được dựng như trên và security filter chain đã bật.

## 3. Tạo JWT với subject và claims tùy chỉnh

Có thể tùy chỉnh JWT bằng hàm `jwt(...)` nhận một consumer của builder:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("lan")
                .claim("scope", "reports:read")
                .claim("tenant", "north")))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Các claim thường dùng trong test:

| Claim | Ý nghĩa kiểm thử |
| --- | --- |
| `sub` | Chủ thể của token, thường được dùng làm tên principal |
| `scope` | Scope OAuth2, thường được ánh xạ thành authority có tiền tố `SCOPE_` |
| `scp` | Một dạng claim scope khác mà converter có thể hỗ trợ tùy cấu hình |
| `iss` | Issuer, hữu ích khi kiểm thử logic đọc claim; mock không tự xác minh issuer |
| `aud` | Audience, hữu ích khi kiểm thử logic đọc claim; mock không tự xác minh audience |
| `tenant` | Claim tùy chỉnh cho tenant của ứng dụng |
| `roles` | Claim role tùy chỉnh, cần converter hoặc mapping riêng nếu muốn biến thành authority |

Khi dùng `mockJwt().jwt(...)`, bạn đang cấu hình nội dung JWT giả lập. Việc có claim `iss` hoặc `aud` trong mock không chứng minh validator đã kiểm tra chúng. Test này chủ yếu kiểm tra các thành phần phía sau authentication có xử lý principal/claim như mong muốn không.

Đối với scope, converter mặc định của Resource Server thường đọc `scope` hoặc `scp` và tạo authority có tiền tố `SCOPE_`. Ví dụ `scope = "reports:read reports:export"` có thể ánh xạ thành `SCOPE_reports:read` và `SCOPE_reports:export`. Nếu ứng dụng đã cấu hình converter tùy chỉnh, hãy xác minh mapping theo cấu hình thật và dùng authority tương ứng trong test.

## 4. Scope được ánh xạ thành GrantedAuthority như thế nào?

Một JWT Resource Server không trực tiếp so sánh chuỗi claim với rule authorization. Sau bước xác thực, JWT được chuyển thành authentication có danh sách `GrantedAuthority`. Với converter mặc định, scope thường có tiền tố `SCOPE_`.

Ví dụ:

~~~json
{
  "sub": "lan",
  "scope": "reports:read reports:export"
}
~~~

Các authority mong đợi:

~~~text
SCOPE_reports:read
SCOPE_reports:export
~~~

Do đó, rule sau:

~~~java
.hasAuthority("SCOPE_reports:read")
~~~

khác với:

~~~java
.hasAuthority("reports:read")
~~~

Nếu ứng dụng dùng `hasAuthority("reports:read")`, phải cấu hình converter để tạo authority không có tiền tố `SCOPE_` hoặc dùng một mapping khác. Đừng nhầm scope claim với authority đã được ánh xạ.

Có thể viết assertion trong controller hoặc service để quan sát authority:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
~~~

Trong code Reactive, kiểu dữ liệu đúng là `Mono<Authentication>` vì `ReactiveSecurityContextHolder.getContext()` trả về `Mono<SecurityContext>`. Publisher cần được compose trong pipeline; không đọc `SecurityContextHolder.getContext()` theo cách Servlet từ thread bất kỳ rồi giả định đó là context của Reactor.

## 5. Kiểm thử endpoint: scope hợp lệ được phép

Giả sử endpoint `GET /api/reports` yêu cầu `SCOPE_reports:read`. Test với JWT có scope này:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
class ReportResourceServerTest extends ReactiveSecurityTestBase {

    @Test
    void readerScopeCanAccessReports() {
        webTestClient
                .mutateWith(mockJwt().jwt(jwt -> jwt
                        .subject("lan")
                        .claim("scope", "reports:read")))
                .get()
                .uri("/api/reports")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Đây là ví dụ cấu trúc; việc inject `WebTestClient` tùy cách dự án cấu hình Boot/WebFlux test. Nếu client chưa được tích hợp security configurer, hãy dựng nó bằng `bindToApplicationContext(...).apply(springSecurity())` như phần trước.

Test này chứng minh authorization cho request có authority được ánh xạ từ scope. Nó không chứng minh JWT có chữ ký hợp lệ hoặc bearer header đã được giải mã.

## 6. Kiểm thử endpoint: thiếu scope bị từ chối

Dùng JWT vẫn hợp lệ về mặt mock nhưng thiếu scope mà endpoint yêu cầu:

~~~java
@Test
void tokenWithoutReadScopeIsForbidden() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("mai")
                    .claim("scope", "reports:export")))
            .get()
            .uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Trong test này, request đã có authentication giả lập. Việc bị từ chối là do authority không đáp ứng `hasAuthority("SCOPE_reports:read")`. Với authorization rule ở WebFlux, trường hợp đã xác thực nhưng thiếu quyền thường trả `403 Forbidden`.

Cần phân biệt với request không có JWT:

~~~java
@Test
void requestWithoutJwtIsUnauthorized() {
    webTestClient
            .get()
            .uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
}
~~~

Kỳ vọng `401` giả định ứng dụng cấu hình Resource Server bearer authentication và entry point tương ứng. Với cấu hình khác, response có thể khác. Hai test có ý nghĩa riêng:

| Request | Authentication | Authorization | Kết quả điển hình |
| --- | --- | --- | --- |
| Không dùng `mockJwt()` | Chưa có JWT authentication | Không thể đáp ứng rule yêu cầu đăng nhập | `401` |
| JWT mock có `reports:export` | Có authentication | Thiếu `SCOPE_reports:read` | `403` |
| JWT mock có `reports:read` | Có authentication | Đủ scope | `200` |

## 7. Cấp authorities trực tiếp

Khi mục tiêu là kiểm tra authorization downstream, có thể cấp authorities trực tiếp thay vì kiểm tra việc ánh xạ từ claim:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
        .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports:read"),
                new SimpleGrantedAuthority("SCOPE_reports:export")))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Cách này hữu ích khi muốn cô lập rule authorization khỏi logic chuyển claim thành authority. Nhưng nó có một giới hạn: test không chứng minh converter của ứng dụng đã ánh xạ `scope`/`scp`/claim tùy chỉnh đúng.

Nên có hai nhóm test riêng nếu mapping là phần quan trọng của ứng dụng:

1. **Authorization test:** cấp authorities trực tiếp để kiểm tra endpoint/service cho phép hoặc từ chối.
2. **Converter/integration test:** dùng claim JWT và xác minh converter tạo đúng authorities; nếu cần kiểm tra decoder, gửi token qua cơ chế xác thực thật.

Không nên chỉ dùng authority trực tiếp rồi kết luận scope claim của JWT production được ánh xạ đúng.

## 8. Kiểm thử claim tùy chỉnh và tenant

Ứng dụng có thể dùng claim tùy chỉnh như `tenant`, `department` hoặc `account_id`. Có thể đưa chúng vào JWT mock:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("lan")
                .claim("scope", "reports:read")
                .claim("tenant", "north")
                .claim("department", "finance")))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Nếu controller lấy claim qua `@AuthenticationPrincipal Jwt jwt`, có thể trả subject/tenant để kiểm tra:

~~~java
@GetMapping("/api/whoami")
Mono<Map<String, String>> whoami(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "tenant", jwt.getClaimAsString("tenant")));
}
~~~

Test:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("lan")
                .claim("tenant", "north")))
        .get()
        .uri("/api/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.subject").isEqualTo("lan")
        .jsonPath("$.tenant").isEqualTo("north");
~~~

Đây là test đọc claim từ principal JWT đã được mock. Nó không kiểm tra token validator có chấp nhận issuer hoặc tenant đó hay không. Nếu tenant là ranh giới bảo mật, cần test riêng policy kiểm tra tenant, bao gồm cả tenant đúng và tenant không khớp.

Ví dụ method security:

~~~java
@PreAuthorize("@tenantPolicy.canRead(authentication, #tenantId)")
public Mono<List<Report>> readTenantReports(String tenantId) {
    return reportRepository.findByTenantId(tenantId).collectList();
}
~~~

Khi test method này, hãy tạo JWT mock có claim tenant và authority phù hợp, sau đó xác minh policy cho phép tenant đúng và từ chối tenant khác. Bảo đảm `@EnableReactiveMethodSecurity` đã bật trong cấu hình. Nếu policy đọc principal/claim qua authentication, mockJwt có thể giúp kiểm tra nhánh authorization mà không cần ký token thật.

## 9. Kiểm thử Reactive method security

Trong WebFlux, security context được truyền qua Reactor Context. Khi một request dùng `mockJwt()` đi qua WebFlux security chain, authentication có thể được đọc bởi reactive method security trong cùng pipeline.

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@Service
class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports:read')")
    public Mono<String> readReport() {
        return Mono.just("report-content");
    }
}
~~~

Cấu hình bật method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

Test thông qua endpoint gọi service:

~~~java
@Test
void jwtScopeAuthorizesReactiveService() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("lan")
                    .claim("scope", "reports:read")))
            .get()
            .uri("/api/reports/service")
            .exchange()
            .expectStatus().isOk();
}

@Test
void missingScopeCannotInvokeReactiveService() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("mai")
                    .claim("scope", "reports:export")))
            .get()
            .uri("/api/reports/service")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Các test cần endpoint thực sự gọi `ReportService.readReport()`. `@EnableReactiveMethodSecurity` bật kiểm tra ở method layer; `mockJwt()` cung cấp authentication để method security đánh giá. Nếu chỉ test route authorization, method security không tự được bật chỉ vì có `SecurityWebFilterChain`.

## 10. Dùng mockJwt với custom authority converter

Resource Server có thể cấu hình converter để chuyển claim tùy chỉnh thành authority. Ví dụ ứng dụng dùng claim `permissions` thay vì `scope`:

~~~json
{
  "sub": "lan",
  "permissions": ["report:read", "report:export"]
}
~~~

Converter của ứng dụng có thể ánh xạ các giá trị thành `REPORT_READ` và `REPORT_EXPORT`. Trong test muốn kiểm tra rule downstream, cấp authority trực tiếp:

~~~java
webTestClient
        .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("REPORT_READ")))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Đây là test authorization sau khi authentication đã có authority. Nó không kiểm tra custom converter đọc `permissions`. Để kiểm tra converter, gọi converter trực tiếp với một `Jwt` có claim tương ứng, hoặc chạy request qua decoder/authentication converter thực tế rồi xác minh authority được tạo.

Một test converter đơn vị có thể tạo Jwt bằng builder:

~~~java
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .subject("lan")
        .claim("permissions", List.of("report:read", "report:export"))
        .build();
~~~

Sau đó gọi converter và assert danh sách `GrantedAuthority`. Nếu converter trả `Mono<AbstractAuthenticationToken>` hoặc một dạng reactive converter, dùng Reactor Test để subscribe và kiểm tra kết quả. Việc test converter tách riêng giúp xác định lỗi nằm ở mapping claim hay ở authorization rule.

## 11. Thiết lập WebTestClient trong các kiểu test khác nhau

### Bind vào ApplicationContext

Đây là cách phù hợp cho test cần mock server configurer như `mockJwt()`:

~~~java
webTestClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

Request được dispatch trong test application context và đi qua WebFlux filter chain đã cấu hình. `mockJwt()` có thể gắn authentication giả lập cho request.

### Bind vào controller

`bindToController(...)` phù hợp với test controller cô lập, nhưng nếu controller phụ thuộc security filter chain hoặc method security, cần cấu hình WebFlux security đầy đủ. Nếu thiếu security infrastructure, test có thể gọi thẳng controller mà không kiểm tra authorization.

### Bind tới server thật

`bindToServer()` kết nối HTTP qua socket. Khi muốn kiểm tra bearer token thật, gửi header:

~~~java
webTestClient.get()
        .uri("/api/reports")
        .headers(headers -> headers.setBearerAuth(signedAccessToken))
        .exchange()
        .expectStatus().isOk();
~~~

Đây là đường kiểm thử khác với `mockJwt()`. Token phải được ký/được phát hành theo cấu hình mà `ReactiveJwtDecoder` tin cậy. `mockJwt()` không tự vượt qua ranh giới mạng và không thay thế header bearer của một client tới server đang chạy.

## 12. Những gì mockJwt không kiểm tra

`mockJwt()` tập trung vào authorization và xử lý request sau khi đã có JWT authentication giả lập. Nó không thay thế các bài test xác thực JWT.

| Yêu cầu cần kiểm tra | `mockJwt()` có phù hợp không? | Cách kiểm thử phù hợp |
| --- | --- | --- |
| Rule yêu cầu scope/authority | Có | Cấp claim hoặc authorities bằng `mockJwt()` |
| Controller đọc `sub`/custom claim | Có | Tạo JWT mock với claim mong muốn |
| Method security theo authority | Có | Gửi request mock tới method được bảo vệ |
| Chuyển claim `scope` thành `SCOPE_...` của converter thực | Không nên chỉ dựa vào mock | Test converter hoặc authentication flow thực |
| Đọc `Authorization: Bearer` header | Không | Gửi header bearer qua filter chain/server |
| Xác minh chữ ký JWT | Không | Dùng token ký bằng test key và decoder |
| Kiểm tra issuer/audience | Không | Test validator/decoder với claim hợp lệ và không hợp lệ |
| Kiểm tra `exp`/`nbf` | Không | Test JWT validation với clock và token phù hợp |
| Kết nối JWK Set/issuer thật | Không | Integration test với issuer/JWK endpoint test |
| Kiểm tra OAuth2 Authorization Code/OIDC login | Không | Dùng test support cho OAuth2/OIDC login hoặc provider test |

Một JWT mock có claim `iss = "https://issuer.example"` không chứng minh ứng dụng đã gọi issuer discovery hoặc kiểm tra issuer. Tương tự, claim `exp` trong mock không chứng minh validator từ chối token hết hạn. Hãy viết test ở đúng lớp cần xác minh.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mockJwt()` không được áp dụng | `WebTestClient` chưa được tích hợp Spring Security | Bind vào ApplicationContext và áp dụng `springSecurity()` |
| Test trả `401` dù có `mockJwt()` | Request không đi qua test configurer/filter chain mong muốn hoặc test dùng client live server | Kiểm tra cách bind client; live server cần bearer header thật |
| Test trả `403` dù đã có JWT mock | Scope/authority không khớp rule | Assert authority thực tế; dùng đúng tiền tố `SCOPE_` |
| Claim `scope` có giá trị nhưng không tạo authority mong muốn | Converter tùy chỉnh hoặc format claim khác mặc định | Test converter riêng; cấp authority trực tiếp để cô lập authorization |
| Dùng `roles("READER")` nhưng rule cần scope | Role và scope là authority khác nhau | Dùng `SCOPE_reports:read` hoặc cấu hình mapping phù hợp |
| Test JWT mock pass nhưng token production bị từ chối | Mock bỏ qua decoder/validator | Kiểm thử token ký thật qua bearer authentication |
| `@PreAuthorize` không từ chối | Chưa bật reactive method security hoặc endpoint không gọi method được bảo vệ | Bật `@EnableReactiveMethodSecurity` và xác minh call path |
| Đọc context bằng `SecurityContextHolder` trả null | Reactive context không dựa trên ThreadLocal mặc định | Dùng `ReactiveSecurityContextHolder` trong pipeline |
| Test POST nhận `403` | CSRF đang bật và request thiếu token | Dùng reactive CSRF test configurer cho ca hợp lệ; giữ ca thiếu token |

## 14. Bài thực hành

Tạo một WebFlux Resource Server có endpoint `GET /api/reports` yêu cầu authority `SCOPE_reports:read`. Hoàn thành các bài sau:

1. Dựng `WebTestClient` bằng `bindToApplicationContext(...)` và `springSecurity()`.
2. Dùng `mockJwt()` với subject `lan` và claim `scope = "reports:read"`; xác minh endpoint được phép.
3. Dùng JWT mock có scope `reports:export`; xác minh request bị từ chối với `403`.
4. Gửi request không có JWT mock; xác minh entry point trả `401` theo cấu hình.
5. Cấp authorities trực tiếp bằng `mockJwt().authorities(...)` và so sánh với cách để converter ánh xạ từ claim.
6. Tạo claim `tenant`, đọc claim qua `@AuthenticationPrincipal Jwt` và kiểm tra tenant policy.
7. Bật `@EnableReactiveMethodSecurity`, bảo vệ service bằng `@PreAuthorize` và kiểm thử cả allowed/denied.
8. Viết test riêng cho custom JWT authorities converter nếu ứng dụng dùng claim `permissions`.
9. Tạo token ký bằng test key, gửi `Authorization: Bearer` tới server test và kiểm tra decoder/issuer/audience/expiry. So sánh kết quả với `mockJwt()`.
10. Viết một ca POST có CSRF hợp lệ và một ca thiếu CSRF nếu endpoint bật bảo vệ CSRF.

Sau khi hoàn thành, hãy giải thích được: **mockJwt tạo authentication ở đâu, scope được chuyển thành authority như thế nào, rule nào quyết định request được phép, và phần nào vẫn cần token thật để kiểm tra?**

## Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
