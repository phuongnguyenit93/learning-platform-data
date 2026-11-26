# Phân biệt bảo mật phương thức Reactive với filter của WebFlux

Một request `GET /api/reports/r-1` có thể đi qua bộ lọc HTTP vì người dùng đã đăng nhập, nhưng vẫn bị từ chối khi gọi một service yêu cầu quyền `SCOPE_reports.read`. Ngược lại, một phương thức service có `@PreAuthorize` hoạt động đúng không chứng minh rằng URL tương ứng đã được bảo vệ khỏi request chưa xác thực. Hai lớp này kiểm tra bảo mật tại **hai ranh giới thực thi khác nhau**.

Bài thuộc chương **Phương thức Reactive** của module **SPRING_SECURITY_TESTING**: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet và Reactive. Trọng tâm là **Spring WebFlux**, `SecurityWebFilterChain`, `@EnableReactiveMethodSecurity`, `@PreAuthorize`, Reactor `SecurityContext`, `WebTestClient` và `StepVerifier`. Công cụ `@WithMockUser`, `mockUser()`, `mockJwt()` và OAuth2/OIDC giả lập sẽ được dùng đúng phạm vi: tạo danh tính thử nghiệm để kiểm tra quyền, không tự xác minh token hay mật khẩu.

## 1. Hai ranh giới bảo mật khác nhau

| Tiêu chí | Bảo mật HTTP WebFlux | Bảo mật phương thức Reactive |
| --- | --- | --- |
| Thành phần chính | `SecurityWebFilterChain` và các `WebFilter` của Spring Security | Interceptor/AOP bảo vệ các phương thức Spring bean |
| Kích hoạt | Cấu hình `ServerHttpSecurity.authorizeExchange(...)` | `@EnableReactiveMethodSecurity` và các annotation như `@PreAuthorize` |
| Điểm kiểm tra | Request đi vào ứng dụng trước khi controller xử lý | Khi một phương thức được bảo vệ được gọi qua bean/proxy |
| Dữ liệu dùng để quyết định | Path, HTTP method, Authentication, authorities, request context | Authentication trong Reactor Context, tên phương thức, tham số, biểu thức hoặc policy |
| Phạm vi | Các request HTTP đi qua security filter chain tương ứng | Các lời gọi tới phương thức được bảo vệ, kể cả không bắt nguồn từ HTTP nếu có security context |
| Test phù hợp | `WebTestClient` gửi GET/POST/DELETE và assert `200`/`401`/`403` | Test gọi Spring service bean rồi dùng `StepVerifier` xác nhận kết quả hoặc `AccessDeniedException` |
| Điều chưa được chứng minh nếu chỉ test lớp này | Không xác nhận một method annotation đã được kích hoạt | Không xác nhận URL, CSRF, HTTP entry point hoặc toàn bộ WebFilterChain |

Không nên coi hai lớp là hai cách thay thế cho nhau. HTTP layer có thể chặn URL không thuộc vùng cho phép, còn method layer bảo vệ nghiệp vụ khi service được gọi qua nhiều nơi: HTTP controller, service khác, tác vụ nội bộ hoặc entry point mới sau này.

~~~mermaid
flowchart TD
    A["HTTP GET /api/reports/r-1"] --> B["SecurityWebFilterChain"]
    B --> C{"Path/HTTP method và Authentication có được phép?"}
    C -->|Không có danh tính| U["401 khi cần đăng nhập"]
    C -->|Thiếu quyền HTTP| F["403 Forbidden"]
    C -->|Qua HTTP policy| D["ReportController"]
    D --> E["ReportService.read(id)"]
    E --> M{"@PreAuthorize thỏa quyền service?"}
    M -->|Không| G["AccessDeniedException -> HTTP 403 thường gặp"]
    M -->|Có| H["Mono/Flux thực thi nghiệp vụ"]
    H --> I["HTTP 200 với kết quả"]
    J["Tác vụ khác gọi ReportService.read(id)"] --> E
~~~

Mã HTTP trong sơ đồ là kết quả điển hình với một API dùng HTTP Basic/Bearer và exception handling thông thường. Tùy cấu hình, lỗi thiếu authentication có thể chuyển hướng đăng nhập hoặc có phản hồi khác. Một lời gọi service trực tiếp không có khái niệm status HTTP: nó trả publisher hoặc phát ra lỗi Reactive.

## 2. Reactor SecurityContext: danh tính đi theo subscriber

WebFlux xử lý bất đồng bộ, có thể chuyển thread trong quá trình thực hiện. `SecurityContextHolder` dạng thread-local của môi trường Servlet không phải nơi ứng dụng Reactive nên đọc Authentication. Spring Security lưu thông tin bảo mật trong **Reactor Context**; `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` để truy cập theo kiểu non-blocking.

~~~java
Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

Trong môi trường không có security context, publisher có thể hoàn thành rỗng. Một ứng dụng an toàn không nên coi trường hợp này là một principal mặc định có quyền. Khi viết kiểm thử method security, điều quan trọng là **Reactor Context phải hiện diện tại thời điểm publisher được subscribe**, không chỉ khi phương thức tạo ra `Mono` được gọi.

Ví dụ một test nhỏ tự cung cấp Authentication vào Reactor Context:

~~~java
Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
    "alice",
    "N/A",
    List.of(new SimpleGrantedAuthority("SCOPE_reports.read")));

Mono<String> observedName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(observedName)
    .expectNext("alice")
    .verifyComplete();
~~~

Đoạn này sử dụng `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.core.authority.SimpleGrantedAuthority` và `reactor.test.StepVerifier`. Nó minh họa truyền context, **chưa kiểm tra HTTP hoặc annotation**.

## 3. Ứng dụng mẫu: một HTTP policy và hai method policy

Ta xây dựng API báo cáo để thấy khác biệt rõ ràng:

- `GET /api/health` công khai.
- `GET /api/reports/{id}` yêu cầu **đã xác thực** ở WebFilterChain, rồi `ReportService.read` yêu cầu thêm `SCOPE_reports.read`.
- `DELETE /api/reports/{id}` yêu cầu `ROLE_ADMIN` ở WebFilterChain, rồi `ReportService.delete` yêu cầu thêm `ROLE_SUPERVISOR` ở method security.
- Các đường dẫn khác bị từ chối.

Với Spring Boot WebFlux, dependencies minh họa:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Cấu hình dùng Basic authentication và dữ liệu người dùng riêng cho bài học. Điều này giúp kiểm thử ranh giới WebFilter/method mà không cần authorization server ngoài:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ReportSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/{id}")
                    .authenticated()
                .pathMatchers(HttpMethod.DELETE, "/api/reports/{id}")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
            User.withUsername("reader")
                .password("{noop}secret")
                .authorities("ROLE_USER", "SCOPE_reports.read")
                .build(),
            User.withUsername("viewer")
                .password("{noop}secret")
                .authorities("ROLE_USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}secret")
                .authorities("ROLE_ADMIN")
                .build(),
            User.withUsername("superadmin")
                .password("{noop}secret")
                .authorities("ROLE_ADMIN", "ROLE_SUPERVISOR")
                .build()
        );
    }
}
~~~

`{noop}` chỉ dùng với mật khẩu giả trong test/demo; không lưu mật khẩu production như vậy. Với test request HTTP, chính `MapReactiveUserDetailsService` này xác minh username/password. Còn `mockUser()` cung cấp Authentication giả lập để tập trung vào phân quyền.

Ở các rule trên, `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`. `hasAuthority("SCOPE_reports.read")` trong service sẽ kiểm tra đúng chuỗi authority được cung cấp. Scope OAuth2 và role không tự động tương đương.

### Controller chỉ định tuyến và gọi service

~~~java
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class ReportController {

    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/reports/{id}")
    Mono<String> read(@PathVariable String id) {
        return reports.read(id);
    }

    @DeleteMapping("/reports/{id}")
    Mono<String> delete(@PathVariable String id) {
        return reports.delete(id);
    }
}
~~~

### Service kiểm tra quyền ở ranh giới phương thức

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> read(String id) {
        return Mono.just("report:" + id);
    }

    @PreAuthorize("hasRole('SUPERVISOR')")
    public Mono<String> delete(String id) {
        return Mono.just("deleted:" + id);
    }
}
~~~

Hai phương thức trên là minh họa hành vi; `delete` chỉ trả chuỗi và không thực sự xóa database. Khi áp dụng vào hệ thống có dữ liệu thật, cần thêm quy tắc chủ sở hữu/tenant nếu nghiệp vụ đòi hỏi và kiểm soát thao tác ghi an toàn.

`@EnableReactiveMethodSecurity` đăng ký method-security interceptor. `@PreAuthorize` được đánh giá khi method được gọi qua **Spring-managed bean/proxy** trong security context thích hợp. Nó vẫn có thể bảo vệ service khi service được gọi từ một nơi không phải controller. Việc có annotation trong source **chưa đủ** nếu bean không được Spring quản lý hoặc cấu hình chưa bật method security.

## 4. Ma trận tách lỗi HTTP layer và method layer

| Request | Danh tính/authority | WebFilterChain | Method security | Kết quả HTTP thường gặp |
| --- | --- | --- | --- | --- |
| GET /api/health | Anonymous | `permitAll` | Không có annotation | `200` |
| GET /api/reports/r-1 | Anonymous | Chặn vì chưa đăng nhập | Không tới service | `401` |
| GET /api/reports/r-1 | viewer: `ROLE_USER` | Cho qua vì đã xác thực | Từ chối vì thiếu `SCOPE_reports.read` | `403` |
| GET /api/reports/r-1 | reader: `ROLE_USER`, `SCOPE_reports.read` | Cho qua | Cho qua | `200` |
| DELETE /api/reports/r-1 | reader: `ROLE_USER`, `SCOPE_reports.read` | Từ chối vì thiếu `ROLE_ADMIN` | Không tới service | `403` |
| DELETE /api/reports/r-1 | admin: `ROLE_ADMIN` | Cho qua | Từ chối vì thiếu `ROLE_SUPERVISOR` | `403` |
| DELETE /api/reports/r-1 | superadmin: `ROLE_ADMIN`, `ROLE_SUPERVISOR` | Cho qua | Cho qua | `200` |

Hai dòng `DELETE` đều trả `403` nhưng do **hai nguyên nhân khác nhau**. Chỉ nhìn status code không chỉ ra lớp nào đã chặn. Để chứng minh chính sách đúng, cần các đối chứng dương và các test gọi trực tiếp service trong phần sau.

Một request không có authentication ở endpoint chỉ cần `authenticated()` thường nhận `401` với HTTP Basic hoặc Bearer API. Trong form login, có thể nhận redirect thay vì `401`. Một service method bị từ chối trực tiếp sẽ phát lỗi `AccessDeniedException` trong Reactive publisher, không tự tạo status HTTP.

## 5. WebTestClient: kiểm tra cả filter và annotation qua HTTP

`WebTestClient` cùng `spring-security-test` có thể tạo principal và authorities giả lập bằng `mockUser()`, nhờ đó từng test tập trung vào một điều kiện phân quyền. Trong Spring Boot WebFlux, cấu hình test minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
@AutoConfigureWebTestClient
class ReportHttpSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicHealthDoesNotRequireAuthentication() {
        client.get().uri("/api/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void anonymousRequestIsStoppedByHttpSecurity() {
        client.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedViewerIsStoppedByMethodSecurity() {
        client.mutateWith(mockUser("viewer").roles("USER"))
            .get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerWithScopePassesBothLayers() {
        client.mutateWith(mockUser("reader")
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:r-1");
    }

    @Test
    void readerCannotDeleteBecauseHttpLayerRequiresAdmin() {
        client.mutateWith(mockUser("reader")
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
            .mutateWith(csrf())
            .delete().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminPassesHttpRuleButFailsServiceRule() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .mutateWith(csrf())
            .delete().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void superadminPassesBothDeleteRules() {
        client.mutateWith(mockUser("superadmin")
                .roles("ADMIN", "SUPERVISOR"))
            .mutateWith(csrf())
            .delete().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("deleted:r-1");
    }
}
~~~

Thêm import `org.springframework.security.core.authority.SimpleGrantedAuthority` cho lớp test trên. Test `readerWithScopePassesBothLayers` chứng minh filter và method đều cho phép request; hai test `readerCannotDelete...` và `adminPassesHttpRuleButFailsServiceRule` tách lần lượt điều kiện WebFilterChain và annotation. Cả hai có thể trả `403`, nên lý do thất bại được suy ra từ chính sách đã dựng và từ các đối chứng thành công, không đơn giản từ status.

`csrf()` được gắn vào các request DELETE vì cấu hình WebFlux mẫu vẫn bật CSRF. Nếu bỏ CSRF token, request có thể bị chặn `403` trước khi tới rule `hasRole("ADMIN")` hay `@PreAuthorize`. Một bài test âm tính khi đó có thể xanh do sai lý do. Khi kiểm thử stateless Bearer API đã chủ động tắt CSRF theo thiết kế, hãy dùng đúng security chain của API đó.

`mockUser()` **không xác minh password** qua `MapReactiveUserDetailsService`. Nó đặt principal đã authenticated vào request test để cô lập điều kiện authorization. Muốn kiểm tra authentication và phân quyền qua HTTP thật, dùng header Basic hoặc Bearer theo cơ chế của ứng dụng.

## 6. StepVerifier: kiểm tra riêng method security không cần HTTP

Khi gọi service trực tiếp, không có `SecurityWebFilterChain` xử lý path. Vì thế ta có thể chứng minh annotation vẫn thực hiện công việc của nó độc lập với HTTP:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import reactor.test.StepVerifier;

@SpringBootTest(
    properties = "spring.main.web-application-type=reactive"
)
class ReportReactiveMethodSecurityTest {

    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(username = "reader",
                  authorities = "SCOPE_reports.read")
    void methodAllowsReaderWithExpectedScope() {
        StepVerifier.create(reports.read("r-1"))
            .expectNext("report:r-1")
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "viewer", roles = "USER")
    void methodRejectsAuthenticatedUserWithoutScope() {
        StepVerifier.create(reports.read("r-1"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "supervisor", roles = "SUPERVISOR")
    void methodAllowsDeleteWithoutCheckingHttpAdminRole() {
        StepVerifier.create(reports.delete("r-1"))
            .expectNext("deleted:r-1")
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void methodRejectsAdminWithoutSupervisorRole() {
        StepVerifier.create(reports.delete("r-1"))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Ví dụ này sử dụng **bean `ReportService` được inject từ Spring**, có bật `@EnableReactiveMethodSecurity`. `@WithMockUser` của Spring Security Test giúp cung cấp security context cho publisher trong test; `StepVerifier` thực hiện subscription và xác nhận giá trị hoặc lỗi thực sự được phát ra.

Ca `methodAllowsDeleteWithoutCheckingHttpAdminRole` là bằng chứng quan trọng: user chỉ có `ROLE_SUPERVISOR` gọi `reports.delete(...)` trực tiếp **thành công** vì method annotation yêu cầu đúng role ấy; nếu cùng user gọi HTTP DELETE thì WebFilterChain cần thêm `ROLE_ADMIN` và sẽ từ chối. Hai chính sách không tự động hợp nhất ở mọi nơi.

Không nên kiểm tra method security bằng việc chỉ gọi `reports.read("r-1")` rồi dừng; một publisher Reactive phải được subscribe mới thực thi toàn bộ chain. `StepVerifier` giúp làm rõ cả trường hợp thành công, phát lỗi và hoàn thành rỗng.

Nếu muốn bảo vệ mọi lời gọi service bằng cả điều kiện ADMIN và SUPERVISOR, hãy đặt **cả hai điều kiện trong method policy** (hoặc một policy chung), thay vì giả định nó luôn được gọi từ URL đã bảo vệ. Điều này quan trọng khi service được tái sử dụng bởi scheduled job, consumer hoặc service khác.

### Không có HTTP thì không có mã 401/403

`AccessDeniedException` từ một method test là exception trong luồng Reactive. `401`/`403` chỉ xuất hiện khi exception đó được xử lý trong bối cảnh web qua Spring Security exception translation hoặc handler của ứng dụng. Nếu gọi service trực tiếp từ mã ngoài HTTP, chính caller phải quyết định xử lý lỗi thế nào.

## 7. Gửi HTTP Basic thật để kiểm tra đường xác thực

Với `MapReactiveUserDetailsService` ở mục 3, dùng header `Authorization: Basic ...` sẽ đi qua bộ lọc xác thực HTTP thay vì chỉ giả lập danh tính:

~~~java
@Test
void basicCredentialsForReaderPassBothLayers() {
    client.get().uri("/api/reports/r-1")
        .headers(h -> h.setBasicAuth("reader", "secret"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("report:r-1");
}

@Test
void wrongPasswordFailsBeforeMethodAuthorization() {
    client.get().uri("/api/reports/r-1")
        .headers(h -> h.setBasicAuth("reader", "wrong-secret"))
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void correctViewerPasswordStillLacksServiceScope() {
    client.get().uri("/api/reports/r-1")
        .headers(h -> h.setBasicAuth("viewer", "secret"))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Đưa các phương thức trên vào lớp `ReportHttpSecurityTest`. Trường hợp mật khẩu sai giúp phân biệt lỗi **authentication** từ provider với lỗi **authorization** ở method. Ca viewer có mật khẩu đúng mà thiếu scope cho thấy authentication thành công không tự động cấp quyền nghiệp vụ.

Ví dụ vẫn chỉ kiểm tra user store in-memory. Một hệ thống LDAP, OAuth2 Login hoặc JWT Resource Server cần kiểm thử thêm connector/decoder thật khi mục tiêu là chứng minh toàn bộ quá trình xác thực.

## 8. JWT, OAuth2 và OIDC giả lập không thay thế security flow

Trong WebFlux Resource Server, `mockJwt()` tạo `JwtAuthenticationToken` phục vụ test:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

// Đặt đoạn này trong test context bật JWT Resource Server.
WebTestClient jwtReaderClient = client.mutateWith(
    mockJwt()
        .jwt(jwt -> jwt.subject("reader"))
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")));

jwtReaderClient.get().uri("/api/reports/r-1")
    .exchange()
    .expectStatus().isOk();
~~~

Vì `mockJwt()` đặt sẵn authentication, kết quả có thể chứng minh hai chính sách WebFilter/method xét đúng authorities, nhưng **không chứng minh** một JWT đã ký thật được decode. Không ghép snippet này vào test context chỉ bật HTTP Basic rồi kết luận Resource Server hoạt động. Để kiểm chứng chữ ký, issuer, audience và `exp`, phải gửi JWT thật qua `Authorization: Bearer ...` và cho `ReactiveJwtDecoder` chạy.

Spring Security Test cũng có `mockOAuth2Login()` và `mockOidcLogin()` dành cho request với danh tính OAuth2/OIDC đã giả lập. Chúng giúp tập trung vào phân quyền method và HTTP, nhưng không chạy authorization code, PKCE, xác minh ID token hay trao đổi token với nhà cung cấp danh tính. Khi muốn kiểm tra OAuth2 Client hoặc OIDC Login thực, cần test tích hợp riêng với provider được kiểm soát.

Scope OAuth2 theo convention thường được ánh xạ thành authority `SCOPE_reports.read`. Nó **không tự trở thành `ROLE_ADMIN` hoặc `ROLE_SUPERVISOR`**. Để chuyển từ JWT/opaque token claims sang role nghiệp vụ, cần một converter rõ ràng và test đúng converter ấy.

## 9. Những trường hợp method security không được áp dụng như mong đợi

### Chưa bật @EnableReactiveMethodSecurity

Một phương thức có `@PreAuthorize` trong source không đủ để kích hoạt bảo vệ; cần cấu hình `@EnableReactiveMethodSecurity` trong application/test context. Nếu annotation chưa được áp dụng, phép kiểm tra role không chạy và service có thể trả kết quả bình thường dù principal không đủ quyền.

Việc có test WebFilterChain trả `401` ở một endpoint không chứng minh method interceptor đã được bật. Nên có ít nhất một test gọi trực tiếp service bằng `@WithMockUser` không đủ quyền và kỳ vọng `AccessDeniedException`.

### Gọi object bằng new thay vì Spring bean

~~~java
// Đây chỉ là object Java thông thường, không đi qua method-security proxy.
ReportService direct = new ReportService();

// Lời gọi này không tự kiểm tra @PreAuthorize.
Mono<String> result = direct.read("r-1");
~~~

Đối tượng trên không được Spring quản lý, nên annotation không được thực thi. Muốn test method security, inject `ReportService` từ Spring context hoặc lấy đúng bean đã được Spring tạo proxy. Đừng để một test trực tiếp `new` service rồi kết luận annotation bảo vệ thành công.

### Self-invocation trong cùng bean

Giả sử service có phương thức `getInternalReport()` gọi một phương thức `securedRead()` được annotate ngay trong cùng class. Với cơ chế proxy, lời gọi `this.securedRead()` có thể không đi qua interceptor, nên không thực hiện `@PreAuthorize` như một caller từ bên ngoài. Đây là lỗi kiến trúc thường gặp khi dùng AOP security.

Nếu cần bảo vệ ranh giới đó, cân nhắc tách phương thức cần bảo vệ sang một Spring bean riêng, gọi qua bean/proxy, hoặc đưa phép kiểm tra chính sách vào logic service một cách rõ ràng.

### Reactor Context bị mất hoặc subscription khác

Publisher Reactive chỉ thực thi khi có subscription. Việc tự tạo callback, kết thúc pipeline bằng `subscribe()` ở một nơi khác, hoặc phối hợp cơ chế bất đồng bộ bên ngoài Reactor có thể khiến security context không được truyền như dự kiến. Với các operator Reactor tiêu chuẩn, context được truyền theo cơ chế Reactor, không nhất thiết mất khi đơn thuần đổi scheduler.

Khi viết test, dùng `StepVerifier` subscribe ngay trên publisher và thiết lập đúng identity. Nếu không dùng `@WithMockUser`, có thể dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))` trong một test được kiểm soát như ở mục 2.

### Phương thức không trả Publisher

Reactive method security được thiết kế để làm việc với Reactive streams và Reactor Context. Với một ứng dụng WebFlux có các phương thức imperative hoặc blocking, cần hiểu rõ phiên bản/cách cấu hình hỗ trợ method-security tương ứng. Đừng chuyển một method Reactive sang trả giá trị đồng bộ rồi mặc định interceptor vẫn thực thi với cùng ngữ nghĩa context.

### Không đi qua Spring Security filter chain trong HTTP test

Nếu dựng `WebTestClient` chỉ gắn trực tiếp vào controller hoặc handler mà không tích hợp Spring Security, request có thể không chạy `SecurityWebFilterChain`. Khi cần kiểm thử filter, dùng `@SpringBootTest` với `@AutoConfigureWebTestClient` để tải đúng ứng dụng, hoặc dùng `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).build()` trên WebFlux application context có cấu hình bảo mật.

Test chỉ chạy controller có thể vẫn gọi một service có `@PreAuthorize` và trả `403`. Kết quả đó chứng minh method security ở service, nhưng không đủ để kết luận HTTP matcher, CSRF hoặc authentication filter đã được áp dụng.

## 10. Khi cả hai lớp có điều kiện khác nhau, chọn nơi đặt quy tắc

Một quy tắc API thường phù hợp với WebFilterChain khi nó gắn chặt với HTTP, ví dụ:

- Endpoint công khai hay yêu cầu đăng nhập.
- Giới hạn `GET`, `POST`, `DELETE` trên từng path.
- Cơ chế Bearer/Basic, CSRF, CORS, session và authentication entry point.

Một quy tắc thường phù hợp với method security hoặc domain policy khi nó cần bảo vệ **nghiệp vụ được gọi từ nhiều nơi**, ví dụ:

- Chỉ nhân viên có quyền phê duyệt mới được gọi `approveInvoice(...)`.
- Chỉ một số scopes mới được xuất dữ liệu nhạy cảm.
- Một phương thức service chỉ được phép thực hiện trên tài nguyên của tenant hoặc chủ sở hữu hiện tại.

Hai lớp có thể bổ sung nhau. Nhưng khi một yêu cầu nghiệp vụ phải giữ đúng dù không còn HTTP controller, **không được chỉ dựa vào WebFilterChain**. Đối với logic chủ sở hữu phức tạp, một policy/domain service kiểm tra principal và dữ liệu từ database đáng tin cậy có thể dễ bảo trì hơn việc nhồi mọi điều kiện vào expression.

Một điểm khác biệt nữa là **thứ tự đánh giá**. Request thường phải vượt qua WebFilterChain mới tới controller/service; nếu bị chặn ở HTTP layer thì method security không có cơ hội chạy. Ngược lại, một lời gọi service trực tiếp không có HTTP request sẽ chỉ đi qua các cơ chế ở ranh giới method và business layer.

## 11. Ma trận kiểm thử để tránh các test "xanh sai lý do"

| Câu hỏi kiểm chứng | Thiết lập tốt nhất | Bằng chứng nên thu |
| --- | --- | --- |
| URL có yêu cầu đăng nhập không? | Gửi request không credentials bằng WebTestClient | `401`/redirect đúng hợp đồng |
| Path GET có được phép nhưng DELETE bị chặn không? | Dùng cùng principal, thay HTTP method | Kết quả từng method theo policy |
| WebFilterChain có yêu cầu ADMIN không? | DELETE với user chỉ có SUPERVISOR và CSRF hợp lệ | `403` trước khi vào service |
| Method có yêu cầu SUPERVISOR không? | Gọi service bean bằng `@WithMockUser(roles="ADMIN")` | `AccessDeniedException` |
| Hai lớp cùng cho phép không? | DELETE với ADMIN + SUPERVISOR và CSRF hợp lệ | `200`, body thành công |
| Method security có thực sự bật không? | Gọi service bean trực tiếp với scope thiếu | Publisher phát `AccessDeniedException` |
| HTTP Basic có xác thực mật khẩu không? | Gửi header Basic đúng/sai | `200`/`401` theo dữ liệu user store |
| JWT có được decode, xác minh chữ ký không? | Bearer JWT ký thật qua decoder trong một test riêng | Token hợp lệ thành công, token sai chữ ký nhận `401` |
| Service có hoạt động khi không bắt nguồn từ HTTP không? | Test direct bean + Reactor Context | Chính sách method vẫn được thực thi |
| CSRF có làm sai kết quả test phân quyền không? | Gửi CSRF hợp lệ với request thay đổi dữ liệu | `403` xuất phát từ chính sách cần test |

**Đối chứng dương quan trọng ngang test âm tính.** Nếu tất cả GET đều `403` do security context lỗi, test “viewer bị cấm” vẫn xanh dù WebFilter hoặc method policy đang cấu hình sai. Luôn có test reader được `200` với `SCOPE_reports.read` và superadmin được `200` với đủ hai role.

## 12. Bài tập thực hành

1. **Tắt method security trong một test context riêng.** Giữ rule GET chỉ `authenticated()` ở WebFilterChain. Gửi viewer đã đăng nhập và quan sát method `@PreAuthorize` không còn chặn khi interceptor không được kích hoạt. Khôi phục cấu hình và chứng minh test bắt đầu trả `403`.
2. **Tắt rule HTTP trong một test context riêng.** Cho phép HTTP DELETE nhưng giữ `@PreAuthorize("hasRole('SUPERVISOR')")`. Gửi admin không có SUPERVISOR và xác minh vẫn bị chặn bởi service.
3. **Đảo hai role.** Dùng user chỉ có SUPERVISOR gọi HTTP DELETE (bị WebFilterChain chặn), rồi gọi trực tiếp `ReportService.delete` bằng `StepVerifier` (được method cho qua). Giải thích vì sao kết quả khác nhau.
4. **Thử dùng `new ReportService()`.** So sánh với bean inject từ Spring và giải thích vai trò của method interceptor/proxy; không xem thử nghiệm `new` là bằng chứng bảo mật production.
5. **Kiểm tra CSRF.** Bỏ `csrf()` khỏi test DELETE và quan sát kết quả. Thêm lại CSRF rồi so sánh test âm tính/dương tính để xác nhận đang kiểm tra đúng lớp.
6. **So sánh mock và Basic thật.** Kiểm tra một reader bằng `mockUser().authorities(...)` và một reader qua Basic header, sau đó thử mật khẩu sai. Giải thích vì sao mock không phát hiện lỗi xác thực.
7. **Chuyển sang JWT Resource Server.** Dùng `mockJwt()` để kiểm tra authorities tại HTTP và method, rồi dùng JWT ký thật qua `ReactiveJwtDecoder` trong test khác để kiểm tra `401` do chữ ký sai/hết hạn.
8. **Thêm owner vào business policy.** Cho `read(id)` chỉ trả báo cáo thuộc principal hiện tại; dùng `Mono<Boolean>` của reactive repository và kiểm tra cả `Mono.empty()`, `Mono.error(...)` lẫn owner sai.
9. **Kiểm tra self-invocation.** Thêm một method gọi method có `@PreAuthorize` trong cùng bean; so sánh kết quả với lời gọi qua bean riêng, rồi điều chỉnh thiết kế để policy luôn được thực thi.
10. **Tách lớp test theo trách nhiệm.** Viết một suite WebTestClient cho filter + HTTP behavior và một suite StepVerifier cho method boundary. Ghi rõ mỗi suite chứng minh điều gì và còn giới hạn gì.

### Kết quả cần đạt

Sau bài học, người học cần giải thích được: **WebFilterChain bảo vệ request HTTP**, còn **Reactive method security bảo vệ lời gọi Spring bean trong Reactor security context**. Hai lớp có thể cùng chặn một request nhưng vì các điều kiện khác nhau. Kiểm thử có chất lượng phải phân biệt `401` do xác thực thất bại, `403` do thiếu quyền HTTP hoặc method, và `AccessDeniedException` trong một publisher được kiểm thử trực tiếp. `mockUser()`, `@WithMockUser` và `mockJwt()` hỗ trợ kiểm thử phân quyền; khi yêu cầu xác minh authentication thực tế, phải bổ sung request HTTP Basic/Bearer qua filter/provider/decoder tương ứng.

### Tài liệu tham khảo

- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security — Reactive Testing with Method Security](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
