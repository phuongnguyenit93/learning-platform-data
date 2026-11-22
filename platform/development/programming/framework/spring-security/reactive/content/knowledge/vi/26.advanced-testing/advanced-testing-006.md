# Kiểm thử mockJwt(), mockOpaqueToken() và ánh xạ quyền trong Spring Security Reactive Resource Server

## Mục tiêu và phạm vi

Trong Spring WebFlux, Resource Server thường bảo vệ API bằng JWT hoặc opaque bearer token. Bài học này tập trung vào **kiểm thử xác thực giả lập và quyết định phân quyền** bằng WebTestClient, thay vì yêu cầu một Authorization Server chạy thật cho mọi test.

Sau bài này, bạn có thể:

- Dùng **mockJwt()** để tạo JwtAuthenticationToken cho request và kiểm tra quyền lấy từ claim scope/scp hoặc authorities được chỉ định.
- Dùng **mockOpaqueToken()** để tạo BearerTokenAuthentication có attributes và authorities rõ ràng.
- Phân biệt **claim/attribute** (dữ liệu token) với **GrantedAuthority** (quyền thực tế mà hasAuthority/hasRole kiểm tra).
- Kiểm tra đúng ba trạng thái: chưa xác thực → HTTP 401; đã xác thực nhưng thiếu quyền → HTTP 403; đủ quyền → HTTP 200 hoặc mã thành công của endpoint.
- Biết khi nào phải test **ReactiveJwtDecoder**, **ReactiveOpaqueTokenIntrospector** hoặc converter thật thay vì chỉ dùng mock authentication.

## 1. Resource Server chuyển token thành quyền như thế nào?

Với JWT thật, pipeline khái quát là:

~~~text
Authorization: Bearer <JWT>
    → ServerAuthenticationConverter / AuthenticationWebFilter
    → ReactiveJwtDecoder (kiểm tra chữ ký, issuer, exp, ...)
    → Jwt → Authentication (JWT authentication converter)
    → authorities
    → SecurityWebFilterChain / method security
    → 200 / 403
~~~

Với opaque token, Resource Server gửi giá trị token đến dịch vụ introspection (hoặc triển khai introspector tùy chỉnh); kết quả được chuyển thành principal, attributes và authorities trước khi đánh giá phân quyền.

**Mặc định với JWT**, Spring Security đọc scope hoặc scp và tiền tố hóa từng scope thành **SCOPE_**. Ví dụ:

| Claim/token data | Authority dùng để phân quyền | Biểu thức kiểm tra |
| --- | --- | --- |
| scope = "reports.read reports.write" | SCOPE_reports.read, SCOPE_reports.write | hasAuthority("SCOPE_reports.read") |
| scp = ["reports.read"] | SCOPE_reports.read | hasAuthority("SCOPE_reports.read") |
| roles = ["ADMIN"] | Không tự biến thành ROLE_ADMIN theo cấu hình JWT mặc định | Cần converter riêng hoặc test authorities rõ ràng |
| permissions = ["reports.read"] | Không tự thành quyền theo cấu hình JWT mặc định | Cần converter cho claim permissions |

**hasAuthority("X")** so khớp chuỗi authority X; **hasRole("ADMIN")** thường kiểm tra authority **ROLE_ADMIN**. SCOPE_reports.read, ROLE_ADMIN và reports.read là ba chuỗi khác nhau. Claim JWT chứa chữ “ADMIN” không đồng nghĩa người gọi có ROLE_ADMIN.

Trong một ứng dụng thực, cùng một endpoint có thể kiểm tra quyền ở SecurityWebFilterChain và ở method security (ví dụ @PreAuthorize). Test cần khởi tạo đúng cấu hình được kiểm tra; chạy controller tách biệt hoàn toàn khỏi Spring Security có thể tạo kết quả sai.

## 2. Hai công cụ mock trong WebFlux

| Nội dung | mockJwt() | mockOpaqueToken() |
| --- | --- | --- |
| Vị trí API | SecurityMockServerConfigurers.mockJwt | SecurityMockServerConfigurers.mockOpaqueToken |
| Authentication giả lập | JwtAuthenticationToken | BearerTokenAuthentication |
| Dữ liệu được sửa trong test | .jwt(builder -> ...), .authorities(...) | .attributes(map -> ...), .authorities(...), .principal(...) |
| Mặc định | JWT có sub=user và scope=read; có SCOPE_read | Principal/attributes có sub=user; có SCOPE_read |
| Phù hợp với | Endpoint dùng @AuthenticationPrincipal Jwt, scope JWT, authorization | Endpoint dùng BearerTokenAuthentication/principal của opaque token, authority sau introspection |
| Không tự kiểm tra | Chữ ký, JWK, issuer, hết hạn qua decoder thật | HTTP introspection, client credential, trạng thái active từ nhà cung cấp |

Cả hai là **WebTestClientConfigurer**. Cú pháp chủ đạo:

~~~java
client.mutateWith(mockJwt())
      .get().uri("/reports")
      .exchange();

client.mutateWith(mockOpaqueToken())
      .get().uri("/reports")
      .exchange();
~~~

Các lời gọi này đặt authentication kiểm thử vào ngữ cảnh request WebFlux. Chúng **không tạo một bearer token đã ký hợp lệ** và không bảo đảm luồng xác minh token thật đã chạy. Đặc biệt, trong test opaque, việc thêm một attribute bằng .attributes(...) **không đồng nghĩa authorities đã tự được tính lại**; đặt .authorities(...) khi bạn muốn kiểm soát quyền đã được introspection cấp.

## 3. Phụ thuộc và cách gắn WebTestClient với Spring Security

Với Spring Boot 3.x và Java 17+, một dự án dùng WebFlux Resource Server có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

test {
    useJUnitPlatform()
}
~~~

Đoạn Gradle trên đặt trong build.gradle của dự án đã cấu hình plugin Spring Boot/Dependency Management tương ứng. Đây là phần **dependencies và test task**, không phải toàn bộ build.gradle độc lập.

Khi tạo client bằng tay, hãy gắn security vào ApplicationContext:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Import tĩnh:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

Nếu sử dụng test slice, test annotation hoặc auto-configured WebTestClient, vẫn phải bảo đảm security filters/method security thực sự nằm trong test context. **WebTestClient.bindToController(...)** không mặc nhiên mang toàn bộ SecurityWebFilterChain thật của ứng dụng.

## 4. Ví dụ hoàn chỉnh: 401, 403, 200 với cả hai mock

Ví dụ độc lập dưới đây kiểm tra **authorization trong WebFlux** trên cùng hai endpoint. TestConfig tạo SecurityWebFilterChain thật nhưng cố ý không thiết lập JWT decoder hay opaque introspector: mục tiêu là chứng minh điều kiện phân quyền khi mock authentication đã được cung cấp. Phần 7 sẽ chỉ ra cách nâng lên integration test đi qua bộ xử lý bearer token thật.

Tệp: src/test/java/example/security/ReactiveAuthorizationTest.java

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.EnableWebFlux;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReactiveAuthorizationTest.TestConfig.class)
class ReactiveAuthorizationTest {

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
    void missingAuthenticationReturns401() {
        client.get().uri("/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void jwtScopeClaimGrantsRead() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("sub", "alice")
                               .claim("scope", "reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void jwtWrongAuthorityReturns403() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.write")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void opaqueWithExplicitReadAuthorityReturns200() {
        client.mutateWith(mockOpaqueToken()
                .attributes(attrs -> attrs.put("sub", "bob"))
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void opaqueAttributeAloneDoesNotGrantReadAuthority() {
        client.mutateWith(mockOpaqueToken()
                .attributes(attrs -> attrs.put("scope", "reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postRequiresWriteAuthority() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
                .post().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.write")))
                .post().uri("/reports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Configuration
    @EnableWebFlux
    @EnableWebFluxSecurity
    static class TestConfig {
        @Bean
        SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
            return http
                    .csrf(ServerHttpSecurity.CsrfSpec::disable)
                    .authorizeExchange(exchanges -> exchanges
                            .pathMatchers(HttpMethod.GET, "/reports")
                                .hasAuthority("SCOPE_reports.read")
                            .pathMatchers(HttpMethod.POST, "/reports")
                                .hasAuthority("SCOPE_reports.write")
                            .anyExchange().denyAll())
                    .build();
        }

        @Bean
        ReportsController reportsController() {
            return new ReportsController();
        }
    }

    @RestController
    static class ReportsController {
        @GetMapping("/reports")
        public Mono<String> read() {
            return Mono.just("report");
        }

        @PostMapping("/reports")
        public Mono<String> write() {
            return Mono.just("created");
        }
    }
}
~~~

Chạy test trong dự án Gradle đã khai báo các dependency ở phần 3:

~~~bash
./gradlew test --tests example.security.ReactiveAuthorizationTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.ReactiveAuthorizationTest
~~~

Kết quả mong đợi: **6 test PASS**; không có stdout cố định nào được chương trình in ra, nên không giả định một dòng console cụ thể. Trạng thái HTTP được assert ngay trong mỗi test.

Lý do cấu hình **CSRF disabled** ở ví dụ: chúng ta muốn POST thất bại/thành công do authority, không do thiếu CSRF token. Trong ứng dụng sử dụng session/cookie, hãy xem xét CSRF theo mô hình bảo mật thật; không sao chép thay đổi cấu hình đó một cách máy móc.

Điểm then chốt: mặc dù hai mock hoạt động trong security test context này, nó **không chứng minh ứng dụng đã bật cả hai chế độ JWT và opaque Resource Server**. Production thường chọn loại token theo hợp đồng với Authorization Server; kiểm thử mỗi chế độ trên cấu hình thực tương ứng.

## 5. Ánh xạ quyền JWT từ scope/scp và custom claims

### 5.1. Kiểm tra scope mặc định

Đối với JWT, **mockJwt().jwt(...)** nhận trình tùy biến Jwt.Builder. Với claim scope="reports.read" như ví dụ trên, mockJWT mặc định áp dụng quy tắc tạo SCOPE_reports.read. Có thể kiểm tra trường hợp quyền rỗng bằng cách xóa scope mặc định:

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claims(claims -> claims.remove("scope"))))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isForbidden();
~~~

Hoặc đặt quyền theo ý đồ kiểm thử một cách trực tiếp:

~~~java
client.mutateWith(mockJwt()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("ROLE_AUDITOR")))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

**.authorities(...)** là kết quả quyền đã ánh xạ, không phải claim. Nếu test gán SCOPE_reports.read trực tiếp thì test chỉ xác nhận rule; nó **không kiểm tra code chuyển claim tùy chỉnh thành authority**.

### 5.2. Custom claim permissions: dùng converter chung với production

Giả sử Identity Provider gửi JWT với:

~~~json
{
  "sub": "alice",
  "permissions": ["reports.read", "reports.write"]
}
~~~

Cấu hình JWT thông thường không đọc trường permissions. Dùng JwtGrantedAuthoritiesConverter để chỉ định tên claim và tiền tố:

~~~java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("SCOPE_");
~~~

Để **test converter**, truyền chính converter đó vào mockJwt() thay vì hard-code authorities:

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .claim("permissions", java.util.List.of("reports.read"))
            .claims(claims -> claims.remove("scope")))
        .authorities(permissions))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Trong production reactive Resource Server, cùng converter phải được gắn vào JwtAuthenticationConverter và được thích nghi thành reactive converter. **Đoạn sau là phần cấu hình minh họa**, đặt trong class cấu hình có các import phù hợp:

~~~java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter delegate = new JwtAuthenticationConverter();
delegate.setJwtGrantedAuthoritiesConverter(permissions);

ReactiveJwtAuthenticationConverterAdapter reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(delegate);

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(reactiveConverter)));
~~~

Các lớp trên thuộc package org.springframework.security.oauth2.server.resource.authentication; ReactiveJwtAuthenticationConverterAdapter là adapter từ converter đồng bộ sang kiểu reactive. Trong code ứng dụng thực, đưa converter về một bean/hàm dùng chung để test không vô tình dùng cấu hình khác production.

Nếu muốn giữ **cả scope mặc định lẫn permissions riêng**, cần ghép các converter (chẳng hạn DelegatingJwtGrantedAuthoritiesConverter) thay vì thay thế converter cũ bằng converter chỉ đọc permissions. Khi chuyển sang ROLE_ cho trường roles, security rule phải khớp ROLE_ADMIN; đừng gọi hasRole("ROLE_ADMIN"), vì hasRole tự thêm tiền tố ROLE_ theo quy ước.

Một test tốt phải có **cả test được phép và test bị từ chối**: ví dụ permissions=["reports.read"] cho GET 200, chỉ permissions=["reports.write"] cho GET 403.

## 6. Ánh xạ quyền opaque token và introspection

Opaque token thường không chứa claim để ứng dụng tự giải mã. Ứng dụng gọi **ReactiveOpaqueTokenIntrospector** để nhận danh tính, attributes và authorities. Với mockOpaqueToken():

~~~java
client.mutateWith(mockOpaqueToken()
        .attributes(attrs -> {
            attrs.put("sub", "alice");
            attrs.put("tenant_id", "tenant-a");
            attrs.put("scope", "reports.read");
        })
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Ở đây ba attributes mô phỏng dữ liệu principal; **chỉ .authorities(...)** quyết định quyền mô phỏng. Giá trị "scope" trong attributes **không được coi là bằng chứng** rằng custom introspector của ứng dụng đã map đúng scope. Để kiểm tra principal cụ thể, có thể dùng .principal(OAuth2AuthenticatedPrincipal) và test controller/handler đọc từ BearerTokenAuthentication.

Với token thật, cấu hình Resource Server opaque tương ứng có dạng:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(org.springframework.security.config.Customizer.withDefaults()));
~~~

JWT mode dùng:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(org.springframework.security.config.Customizer.withDefaults()));
~~~

Hai đoạn trên là **hai cấu hình lựa chọn**; mỗi cấu hình cần decoder/introspector và thông số nhà cung cấp phù hợp. Không ghép chúng một cách tùy tiện để kết luận rằng ứng dụng hỗ trợ đồng thời hai cơ chế.

Khi custom introspector biến attribute "roles" thành ROLE_ADMIN, hãy test trực tiếp logic đó (hoặc gọi HTTP với introspector giả lập) và kiểm tra tập authorities được trả về. Chỉ viết mockOpaqueToken().authorities(ROLE_ADMIN) sẽ bỏ qua lỗi ánh xạ thực tế.

## 7. Ranh giới unit/security test và integration test

**Mock authentication** kiểm tra tốt rule, controller nhận principal và method security, nhưng **bỏ qua quá trình giải mã/xác minh bearer token**. Để test đường đi thực qua AuthenticationWebFilter:

1. Khởi tạo đúng SecurityWebFilterChain với .oauth2ResourceServer(...jwt(...)) **hoặc** .opaqueToken(...).
2. Cung cấp ReactiveJwtDecoder/ReactiveOpaqueTokenIntrospector test double trong ApplicationContext; với Spring Boot 3.3 có thể dùng @MockBean, còn các phiên bản Boot mới hơn có cơ chế @MockitoBean tương ứng.
3. Gửi **Authorization: Bearer <giá trị token>** qua WebTestClient thay vì dùng mutateWith(mockJwt()) hoặc mutateWith(mockOpaqueToken()).
4. Kiểm tra decoder/introspector được gọi, authorities từ converter đang dùng trong ứng dụng, và kết quả 200/401/403. Dùng WireMock/Testcontainers hoặc Authorization Server thật khi cần kiểm tra endpoint introspection, JWK rotation hay giao thức đầy đủ.

Ví dụ mảnh mã cho **JWT pipeline test** (giả định client đang dùng cấu hình JWT Resource Server và jwtDecoder là mock bean):

~~~java
Jwt decoded = Jwt.withTokenValue("test-jwt")
        .header("alg", "RS256")
        .claim("sub", "alice")
        .claim("scope", "reports.read")
        .build();

when(jwtDecoder.decode("test-jwt")).thenReturn(Mono.just(decoded));

client.get().uri("/reports")
      .headers(headers -> headers.setBearerAuth("test-jwt"))
      .exchange()
      .expectStatus().isOk();
~~~

Ở đây việc mock decoder cho phép test **converter và authorization sau decode**; nó vẫn không xác nhận chữ ký/issuer/expiration bằng thuật toán thật. Cần đặt stubbing trong một test class có Mockito và cấu hình phù hợp; mảnh mã này **không phải chương trình Java độc lập**.

Ví dụ mảnh mã cho **opaque pipeline test** (cấu hình opaque mode, introspector là mock bean):

~~~java
OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
                java.util.Map.of("sub", "alice", "scope", "reports.read"),
                java.util.List.of(
                    new SimpleGrantedAuthority("SCOPE_reports.read")));

when(introspector.introspect("opaque-ok")).thenReturn(Mono.just(principal));

client.get().uri("/reports")
      .headers(headers -> headers.setBearerAuth("opaque-ok"))
      .exchange()
      .expectStatus().isOk();
~~~

Các class thường dùng: ReactiveJwtDecoder, ReactiveOpaqueTokenIntrospector, OAuth2AuthenticatedPrincipal và DefaultOAuth2AuthenticatedPrincipal. Kết quả phụ thuộc converter/introspector thật được cấu hình; nếu muốn chứng minh quy tắc ánh xạ custom, tránh stub trực tiếp kết quả đã “đúng sẵn” và gọi chính phần mapping được dùng ở production.

Ngoài ra, lỗi **401 do token không hợp lệ** chỉ có ý nghĩa khi bộ lọc xác thực thực sự chạy với token/header hoặc decoder/introspector trả lỗi; tạo mockJwt() rồi đổi claim exp thành quá khứ **không đủ để chứng minh validator thời gian chạy**.

## 8. Ma trận ca kiểm thử cần có

| Tình huống | Đầu vào đề xuất | Kỳ vọng |
| --- | --- | --- |
| Không có authentication | GET /reports, không mutateWith | 401 |
| JWT đủ scope đọc | mockJwt().jwt(scope=reports.read) | 200 |
| JWT thiếu quyền đọc | mockJwt().authorities(SCOPE_reports.write) | 403 |
| JWT không có scope | mockJwt() sau khi bỏ claim scope | 403 |
| Opaque đủ quyền | mockOpaqueToken().authorities(SCOPE_reports.read) | 200 |
| Opaque chỉ có scope attribute, thiếu authority tương ứng | mockOpaqueToken().attributes(...) | 403 |
| POST có quyền đọc nhưng thiếu ghi | SCOPE_reports.read | 403 |
| POST có quyền ghi | SCOPE_reports.write | 200 |
| Custom JWT permissions | converter từ permissions → SCOPE_... | 200/403 theo quyền cụ thể |
| Token thật sai/hết hạn | Bearer header + decoder/introspector hoặc server stub | 401, kiểm tra handler lỗi thực |

Ma trận có thể được triển khai bằng test tham số hóa, nhưng mỗi case cần lý do thất bại rõ ràng. Nếu endpoint thực có @PreAuthorize, hãy giữ cấu hình method security và kiểm tra thêm trường hợp HTTP rule cho qua nhưng method rule từ chối.

## 9. Lỗi phổ biến và cách xử lý

- **Nhầm claim với authority.** JWT permissions=["ADMIN"] không tự cho ROLE_ADMIN; opaque .attributes("scope", ...) không thay thế .authorities(...). Sửa converter hoặc mock quyền sau ánh xạ, tùy tầng đang test.
- **Sai tiền tố hoặc dấu phân cách.** scope "reports.read" cho SCOPE_reports.read, không tự cho reports.read, ROLE_reports.read hay SCOPE_reports:read.
- **Test vô tình pass vì mockJwt mặc định có SCOPE_read.** Với test thiếu quyền, xóa scope hoặc đặt authorities không có quyền cần thiết.
- **Test converter bằng cách gán authorities cố định.** Cách đó bỏ qua converter; truyền cùng JwtGrantedAuthoritiesConverter qua .authorities(converter) hoặc gọi thực pipeline có decoder stub.
- **Quên springSecurity() khi tự bind WebTestClient.** SecurityMockServerConfigurers cần được gắn vào client/context đúng cách.
- **Nhầm 401 và 403.** 401 là chưa/chưa thể xác thực; 403 là đã được xác thực nhưng bị chính sách phân quyền từ chối. Có thể có ngoại lệ do entry point/handler tùy chỉnh, cần test theo cấu hình thực.
- **Bị CSRF che lỗi phân quyền trên POST.** Nếu API sử dụng CSRF, thêm mockCsrf hoặc token đúng; nếu là stateless bearer API, xét cấu hình CSRF phù hợp. Không kết luận thiếu authority khi nguyên nhân là CSRF.
- **Dùng mock JWT để test chữ ký hoặc hết hạn.** Mock inject authentication đã được chấp nhận; phải kiểm thử decoder/validator qua bearer header hoặc test decoder riêng.
- **Dùng WebMvc MockMvc cho WebFlux.** Phần này áp dụng WebTestClient cùng SecurityMockServerConfigurers (reactive), không dùng SecurityMockMvcRequestPostProcessors của Servlet.
- **Bỏ qua negative test.** Một test HTTP 200 không chứng minh endpoint cấm tài khoản thiếu quyền; luôn có case 403 và 401 thích hợp.

## 10. Tự kiểm tra kiến thức

1. Một JWT có scope="reports.read" sẽ tạo authority nào theo mặc định? **SCOPE_reports.read.**
2. Vì sao mockOpaqueToken().attributes(attrs -> attrs.put("scope", "reports.read")) vẫn có thể bị 403? **Attributes không thay thế authorities của Authentication giả lập; endpoint kiểm tra authority.**
3. Khi dùng hasRole("ADMIN"), cần quyền nào? **ROLE_ADMIN.**
4. Test với mockJwt().authorities(SCOPE_reports.read) có xác minh custom claim converter không? **Không; đã chỉ định authority sau ánh xạ.**
5. Muốn kiểm tra luồng bearer → decoder → converter → authorization, nên làm gì? **Gửi bearer header qua cấu hình Resource Server thật, stub decoder/introspector phù hợp và assert quyền; dùng integration test đầy đủ nếu cần kiểm tra cryptography/introspection HTTP.**

## Tài liệu chính thức

- Spring Security — Testing OAuth 2.0 with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html

Các ví dụ sử dụng mô hình Spring Security 6.x / Spring Boot 3.x với WebFlux và Java 17+; khi nâng phiên bản lớn, kiểm tra lại API và dependency tương ứng.
