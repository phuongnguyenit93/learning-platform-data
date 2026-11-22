# Chuyển từ MockMvc sang WebTestClient khi kiểm thử Spring Security WebFlux

> **Chủ đề:** Spring Security - reactive → Chuyển đổi và gỡ lỗi → Chuyển từ MockMvc sang WebTestClient. Bài này hướng dẫn chuyển test HTTP và kiểm thử bảo mật từ mô hình Spring MVC/Servlet sang Spring WebFlux/Reactor, giữ nguyên ý nghĩa của các kiểm thử 401, 403, principal, role/scope và dữ liệu phản hồi.

## 1. Khi nào cần chuyển và chuyển những gì?

**MockMvc** là công cụ kiểm thử HTTP trên stack **Spring MVC/Servlet**: request đi qua **DispatcherServlet**, Servlet Filter và phần bảo mật tương ứng. **WebTestClient** là client kiểm thử dùng được theo hai hướng: gắn trực tiếp vào một ứng dụng **WebFlux** trong bộ nhớ hoặc gọi HTTP đến server đang chạy. Khi chuyển một module thực sự từ Spring MVC sang WebFlux, điều quan trọng là bộ kiểm thử phải chạy qua **WebFilter/Reactive SecurityWebFilterChain**, kiểm tra **Publisher (Mono/Flux)** và truyền security context theo Reactor.

**Chuyển cú pháp test không đồng nghĩa đã chuyển runtime**:

- Một ứng dụng vẫn dùng **spring-boot-starter-web**, **DispatcherServlet**, **HttpSecurity/SecurityFilterChain** có thể được gọi từ WebTestClient qua HTTP, nhưng cách đó không biến ứng dụng thành WebFlux.
- **MockMvcWebTestClient** là adapter giúp viết assertion theo giao diện WebTestClient trên hệ thống MockMvc. Đây là bước chuyển giao diện test khi vẫn còn Servlet, không chứng minh bộ lọc bảo mật reactive hoạt động.
- Với ứng dụng WebFlux thật, dùng **spring-boot-starter-webflux**, **ServerHttpSecurity/SecurityWebFilterChain**, controller có thể trả **Mono/Flux**, và security context sống trong **Reactor Context**.
- Nếu có cả **spring-boot-starter-web** và **spring-boot-starter-webflux**, Spring Boot thường chọn ứng dụng **Servlet/MVC** theo quy tắc tự xác định web application type. Cần kiểm tra dependency và runtime trước khi thay toàn bộ test.

### Mục tiêu sau khi hoàn thành

1. Phân biệt test trên Servlet với test trên WebFlux.
2. Đổi bộ dựng request, phương thức chạy và assertion từ MockMvc sang WebTestClient.
3. Chuyển security test từ **SecurityMockMvcRequestPostProcessors** sang **SecurityMockServerConfigurers**.
4. Viết test 200/401/403 và xác nhận claims/authorities của JWT trong reactive pipeline.
5. Chọn đúng kiểu test: **@WebFluxTest**, **@SpringBootTest + bindToApplicationContext**, hoặc HTTP thật đến server.
6. Gỡ lỗi khi test “xanh” nhưng filter không chạy, JWT không được xác minh, mất Reactor context hoặc request streaming bị treo.

## 2. Bảng đối chiếu MockMvc → WebTestClient

| Tình huống | MockMvc (Spring MVC) | WebTestClient (WebFlux) |
| --- | --- | --- |
| Test slice controller | **@WebMvcTest**, inject **MockMvc** | **@WebFluxTest**, inject hoặc dựng **WebTestClient** |
| Full application không mở cổng HTTP | **@SpringBootTest + @AutoConfigureMockMvc** | **@SpringBootTest**, **WebTestClient.bindToApplicationContext(context)**, **apply(springSecurity())** |
| Gọi HTTP server thật | **MockMvc** không phải HTTP client thật | **WebTestClient.bindToServer()** hoặc client được auto-configure ở RANDOM_PORT |
| Tạo GET | **mockMvc.perform(get("/api/me"))** | **client.get().uri("/api/me").exchange()** |
| Tạo POST JSON | **post(...).contentType(...).content(...)** | **post().uri(...).contentType(...).bodyValue(...)** |
| Kiểm HTTP status | **andExpect(status().isOk())** | **expectStatus().isOk()** |
| Kiểm JSONPath | **andExpect(jsonPath("$.subject").value("alice"))** | **expectBody().jsonPath("$.subject").isEqualTo("alice")** |
| Kiểm header | **andExpect(header().string(...))** | **expectHeader().valueEquals(...)** |
| Principal giả lập | **.with(user("alice"))** | **client.mutateWith(mockUser("alice"))** |
| JWT giả lập | **.with(jwt())** | **client.mutateWith(mockJwt())** |
| CSRF giả lập | **.with(csrf())** | **client.mutateWith(csrf())** |
| Security test support | **SecurityMockMvcRequestPostProcessors** | **SecurityMockServerConfigurers** |
| Kết quả async | **asyncDispatch(...)** trong một số kịch bản MVC | **exchange()**, **returnResult(...)**, **StepVerifier** cho Flux/Mono |
| Reactive method security | Không thuộc MockMvc thuần Servlet | Thực thi trên Reactor Context với **@EnableReactiveMethodSecurity** khi sử dụng |

Điểm dễ nhầm nhất là **.with(jwt())** và **.mutateWith(mockJwt())**. Cả hai dùng thư viện **spring-security-test**, nhưng thuộc hai nhánh cấu hình khác nhau, không phải API hoán đổi trực tiếp.

## 3. Trước khi sửa test: kiểm tra hợp đồng runtime và behavior

Lập một bảng kiểm cho từng endpoint hiện hữu:

- **Route và HTTP method:** giữ nguyên đường dẫn, query params, status code, media type và cấu trúc response nếu yêu cầu chuyển đổi không đổi API contract.
- **Quyền:** phân biệt anonymous, authenticated nhưng thiếu authority, JWT có scope cần thiết, principal và tenant khác nhau.
- **Lỗi:** xác định status/body phù hợp cho 401 (chưa xác thực), 403 (thiếu quyền), 400 (payload sai), 404 (không tồn tại/không thấy đối tượng).
- **CSRF/session:** API Bearer token stateless khác ứng dụng đăng nhập bằng cookie; không tắt CSRF chỉ để test “xanh”.
- **Phản ứng bất đồng bộ:** controller trả **Mono/Flux** phải được subscribe bởi WebFlux test runtime; không gọi **block()** trong handler để bắt chước Servlet.
- **Dependency của controller:** ở test slice có thể cần mock service; ở integration test dùng bean thực để chứng minh WebFilter → controller/service đi đúng.
- **Nguồn JWT:** mock JWT chỉ cung cấp **Authentication** để kiểm behavior nội bộ, không thay cho kiểm tra chữ ký/issuer/audience/expiry ở HTTP thật.

Sau khi hiểu những hợp đồng trên, thực hiện migration theo hai vòng: kiểm behavior HTTP/security trong WebFlux application context, rồi kiểm kịch bản cấu hình token thật với server và IdP/decoder đáng tin cậy.

## 4. Ví dụ hoàn chỉnh: Spring Boot 3.3.x, Java 17+, Spring Security WebFlux

Ví dụ bên dưới chạy **WebFlux application context trong bộ nhớ**, dùng SecurityWebFilterChain bảo vệ hai endpoint và test security bằng **mockJwt()**. Các tên class/đường dẫn nhất quán; chỉ cần tạo các tệp theo cấu trúc:

~~~text
settings.gradle
build.gradle
src/main/java/example/migration/WebfluxMigrationApplication.java
src/test/java/example/migration/WebfluxMigrationSecurityTest.java
~~~

Các phiên bản được cố định cho ví dụ Java 17; dự án thật cần thống nhất version với build và dependency management của dự án.

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-security-migration'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong demo chỉ dùng **starter-webflux**, không thêm **starter-web**. Bộ kiểm thử sử dụng Spring Test, JUnit Jupiter và Spring Security Test. **@MockBean** trong đoạn test tương thích Spring Boot 3.3.x đã cố định ở đây; với các bản mới hơn, cần đọc API thay thế của version dự án.

**src/main/java/example/migration/WebfluxMigrationApplication.java**

~~~java
package example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebfluxMigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxMigrationApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class WebSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Chỉ phù hợp với demo API Bearer JWT không dùng cookie.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/me")
                        .hasAuthority("SCOPE_profile.read")
                        .pathMatchers(HttpMethod.POST, "/api/notes")
                        .hasAuthority("SCOPE_notes.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}

record PublicView(String message) {}
record ProfileView(String subject, String tenant) {}
record NoteRequest(String text) {}
record NoteReceipt(String createdBy, String tenant, String text) {}

@RestController
@RequestMapping("/api")
class DemoApiController {
    @GetMapping("/public")
    Mono<PublicView> publicEndpoint() {
        return Mono.just(new PublicView("public-ok"));
    }

    @GetMapping("/me")
    Mono<ProfileView> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(new ProfileView(
                jwt.getSubject(),
                jwt.getClaimAsString("tenant_id")));
    }

    @PostMapping("/notes")
    Mono<NoteReceipt> addNote(
            @RequestBody Mono<NoteRequest> body,
            @AuthenticationPrincipal Jwt jwt) {
        return body.map(request ->
                new NoteReceipt(
                        jwt.getSubject(),
                        jwt.getClaimAsString("tenant_id"),
                        request.text()));
    }
}
~~~

Ứng dụng minh họa cách sử dụng **@AuthenticationPrincipal Jwt** trong controller reactive. **/api/public** cho phép anonymous; **/api/me** cần **SCOPE_profile.read**; **POST /api/notes** cần **SCOPE_notes.write**. Endpoint POST trả thông tin giả lập, **không lưu DB**; ví dụ tập trung chứng minh migration của HTTP security test, không đại diện cho kiểm thử transaction/persistence.

**Lưu ý bảo mật:** ở một hệ thống đa tenant thật, phải kiểm chứng **tenant_id** từ JWT đã được xác thực và áp dụng vào truy vấn/service; đọc claim trong ví dụ này chỉ để chứng minh test principal. Nếu dùng browser cookie/session thì đánh giá lại CSRF, logout và session management; không sao chép dòng **csrf(...disable)** vô điều kiện.

### 4.1 Test sau khi chuyển: WebTestClient + mockJwt()

**src/test/java/example/migration/WebfluxMigrationSecurityTest.java**

~~~java
package example.migration;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class WebfluxMigrationSecurityTest {

    @Autowired
    ApplicationContext context;

    // Chỉ để khởi tạo filter chain OAuth2 Resource Server trong test.
    // mockJwt() cung cấp SecurityContext trong bộ nhớ cho từng request.
    @MockBean
    ReactiveJwtDecoder jwtDecoder;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    private WebTestClient asJwt(
            String subject, String tenant, String scope) {
        return client.mutateWith(mockJwt()
                .jwt(jwt -> jwt
                        .subject(subject)
                        .claim("tenant_id", tenant))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_" + scope)));
    }

    @Test
    void publicEndpointWorksWithoutToken() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("public-ok");
    }

    @Test
    void anonymousRequestGets401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutScopeGets403() {
        asJwt("alice", "tenant-a", "other.read")
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctJwtScopeReachesController() {
        asJwt("alice", "tenant-a", "profile.read")
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a");
    }

    @Test
    void writeRequiresWriteScope() {
        asJwt("alice", "tenant-a", "profile.read")
                .post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteRequest("first note"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedWriteUsesAuthenticatedPrincipal() {
        asJwt("alice", "tenant-a", "notes.write")
                .post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteRequest("first note"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.createdBy").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a")
                .jsonPath("$.text").isEqualTo("first note");
    }

    @Test
    void ClientTenantHeaderCannotOverrideJwtClaim() {
        asJwt("alice", "tenant-a", "profile.read")
                .get()
                .uri("/api/me")
                .header("X-Tenant-Id", "tenant-b")
                .header("X-User-Id", "bob")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a");
    }
}
~~~

**Chạy:**

~~~bash
gradle test
~~~

Nếu dự án đã có Gradle Wrapper tương thích với phiên bản Boot:

~~~bash
./gradlew test
~~~

Trên PowerShell Windows có thể dùng **gradlew.bat test**. Kỳ vọng **7 trường hợp** pass nếu fixture được tạo đúng và môi trường có các dependency/JDK phù hợp. Để xem test failures, kiểm tra báo cáo Gradle tại **build/reports/tests/test/index.html**. Đây là **kỳ vọng của fixture**, không phải tuyên bố đã chạy test trên máy của người học.

### 4.2 Vì sao cấu hình test hoạt động?

- **@SpringBootTest** tải filter chain, controller và context thực của demo; **WebEnvironment.MOCK** không mở cổng HTTP ngoài.
- **bindToApplicationContext(context)** ghép WebTestClient với handler chain trong bộ nhớ; request được dispatch bởi Spring WebFlux.
- **apply(springSecurity())** gắn Spring Security test support cho WebFlux request binding; các mutation **mockJwt()** được filter đúng cách áp dụng.
- **@MockBean ReactiveJwtDecoder** đáp ứng bean dependency của OAuth2 Resource Server khi bootstrap; test không thực hiện verify chữ ký JWT.
- **mockJwt().jwt(...)** tạo principal có subject và tenant claim; **authorities(...)** gán quyền thật mà rule **hasAuthority** đang kiểm tra.
- **exchange()** thực hiện request/subscribe pipeline; **expectStatus/expectBody** kiểm cả security outcome lẫn controller response.
- Mỗi test dùng một biến thể client **mutateWith(...)** cho request phù hợp, không phải ghi Authorization toàn cục rồi để principal test trước rò sang test sau.

MockJwt **không chứng minh** decoder chấp nhận token hợp lệ hay từ chối token sai chữ ký, sai issuer, sai audience, expired, kid không tồn tại. Muốn kiểm những điều đó phải chạy kiểm thử decoder và request có Bearer token ký thật trong môi trường tích hợp.

## 5. So sánh cùng một ca trước và sau

Giả sử test cũ dùng Servlet Spring Security Test:

~~~java
// Ví dụ cú pháp của Spring MVC + MockMvc (không đưa vào dự án WebFlux demo).
mockMvc.perform(get("/api/me")
        .with(jwt()
                .jwt(jwt -> jwt.subject("alice")
                        .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice"));
~~~

Sau khi đổi sang WebFlux, cùng ý định kiểm thử:

~~~java
// Đặt trong test đã cấu hình WebTestClient và springSecurity().
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice")
                .claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_profile.read")))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.subject").isEqualTo("alice");
~~~

**Nhận xét:** cả hai kiểm logic scope/claim với Authentication giả lập. Bản WebFlux kiểm **SecurityWebFilterChain** và reactive handler khi dùng đúng ứng dụng WebFlux. Chỉ thay những dòng syntax mà không chuyển/test lại **runtime SecurityFilterChain → SecurityWebFilterChain** có thể khiến ta test nhầm stack.

## 6. Chọn scope của test: slice, full context và real HTTP

### 6.1 @WebFluxTest: nhanh, tập trung controller

Dùng **@WebFluxTest(controllers = DemoApiController.class)** để tải slice WebFlux. Khi test security của controller, import **WebSecurityConfig** nếu slice không tự nạp cấu hình tùy biến; cung cấp **ReactiveJwtDecoder** mock và **@MockBean** các collaborator của controller. Ví dụ skeleton có chủ đích, sử dụng các class ở mục 4:

~~~java
@WebFluxTest(controllers = DemoApiController.class)
@Import(WebSecurityConfig.class)
class ApiControllerSliceTest {
    @Autowired ApplicationContext context;
    @MockBean ReactiveJwtDecoder jwtDecoder;

    @Test
    void authorizedProfile() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient().build();

        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice")
                        .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read")))
                .get().uri("/api/me").exchange()
                .expectStatus().isOk();
    }
}
~~~

Đoạn này là **skeleton bổ sung**, cần các import JUnit/Spring cùng các lớp demo đã cung cấp; không dùng như file Java độc lập. Không phải mọi **@Configuration** hoặc bean của ứng dụng đều được nạp vào slice. Với controller thực gọi service, mock service bằng **@MockBean** hoặc import bean đúng scope, rồi quyết định rõ test bảo vệ HTTP hay test nghiệp vụ.

### 6.2 @SpringBootTest + bindToApplicationContext: test WebFlux trong bộ nhớ

Dùng khi cần thật sự kết nối các bean/filter/controller/service trong một context, có thể mock các dependency ngoại vi như database hoặc IdP. Đây là đường được trình bày đầy đủ ở mục 4, thích hợp test **SecurityWebFilterChain**, reactive principal và endpoint contract mà không phụ thuộc network.

**Thực thi ở context bộ nhớ khác thực thi ở mạng thật:** test có thể bypass decoder bằng mockJwt để tập trung kiểm authorization. Không dùng kết quả này để chứng nhận cấu hình issuer/audience và TLS ngoài đời.

### 6.3 @SpringBootTest(RANDOM_PORT): kiểm HTTP thật

Dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** với **@AutoConfigureWebTestClient**, hoặc tạo **WebTestClient.bindToServer().baseUrl(...)**, để gửi request qua HTTP tới server thật. Trong trường hợp này, mockJwt của WebFlux security test là mutation cục bộ của application-context-bound client, **không truyền Authentication qua wire** và không thể thay Bearer token. Phải gửi **Authorization: Bearer ...** với JWT đã được ký bởi test IdP/key hoặc opaque token hợp lệ đối với IdP thử nghiệm, rồi cho decoder/introspection của Resource Server chạy thật.

Đây là khác biệt cốt lõi:

~~~text
A. Context-bound:
   WebTestClient → test WebFilter(mockJwt) → SecurityWebFilterChain → Controller
   Authentication được gắn trong test; không có JWT thực để verify.

B. Real HTTP:
   WebTestClient → TCP/HTTP → Reactor Netty server
                 → SecurityWebFilterChain → JwtDecoder/Introspector
                 → Controller
   Authorization header phải chứa credential thật theo fixture.
~~~

Không lấy HTTP 200 từ client context-bound rồi kết luận đã xác minh chữ ký JWT production. Cũng không thêm fake principal bằng cách đặt **X-User-Id** hay **X-Tenant-Id** mà không có contract tin cậy giữa gateway và backend.

## 7. Chuyển các kiểu authorization test phổ biến

### 7.1 User/role và JWT/scope khác nhau

WebFlux cho phép cả:

~~~java
// Khi endpoint chỉ yêu cầu authenticated hoặc ROLE_USER.
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/user").exchange()
        .expectStatus().isOk();
~~~

~~~java
// Khi endpoint kiểm SCOPE_profile.read từ JWT.
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice"))
        .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get().uri("/api/me").exchange()
        .expectStatus().isOk();
~~~

Đây là **snippet minh họa** và yêu cầu endpoint/cấu hình tương ứng; **/api/user** không tồn tại trong demo mục 4. **mockUser()** tạo Authentication kiểu user/password với principal tương ứng, nên controller khai báo **@AuthenticationPrincipal Jwt** không nên được kiểm bằng mockUser(). Ngược lại, **mockJwt()** phù hợp endpoint Resource Server kỳ vọng Jwt principal. Nếu dùng **@WithMockUser** trong test reactive, phải bảo đảm cơ chế Spring Security Test cung cấp Reactor Context đúng cho setup đó; explicit **mutateWith(mockUser())** dễ đọc và cho phép biến thể mỗi request.

**ROLE_** và **SCOPE_** là convention khác nhau. **roles("ADMIN")** thường sinh **ROLE_ADMIN**; **hasAuthority("SCOPE_notes.write")** phải được cấp đúng authority, không suy ra từ roles("ADMIN").

### 7.2 CSRF: chỉ áp dụng cho cơ chế sử dụng session/cookie phù hợp

Với form login hoặc cookie-based session, kiểm lỗi POST không có CSRF và POST có CSRF hợp lệ; trong WebTestClient dùng **SecurityMockServerConfigurers.csrf()**, ví dụ:

~~~java
// Ví dụ riêng cho ứng dụng bật CSRF và sử dụng auth cookie/session.
// Không dùng status 200 nếu endpoint/service/policy thực tế quy định khác.
client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/api/form")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"value\":\"demo\"}")
        .exchange()
        .expectStatus().isOk();
~~~

Đoạn này không thuộc demo stateless JWT đã tắt CSRF và không phải test chạy độc lập. Khi một ứng dụng chuyển từ session sang Bearer, quyết định dùng CSRF cần dựa vào cách browser gửi credential, không phải chỉ theo framework.

### 7.3 Method security sử dụng Reactor Context

Khi chuyển **@PreAuthorize**, **@PostAuthorize** hoặc các cơ chế method-security tùy biến:

- Trên WebFlux, bật **@EnableReactiveMethodSecurity** khi dự án dùng reactive method security.
- Gọi qua **Spring proxy/bean thực**, không trực tiếp tạo service bằng **new** trong integration test vì có thể bỏ qua proxy.
- Đặt **Authentication** vào **Reactor Context** để service xử lý đúng sau khi đổi thread/scheduler; không dùng **SecurityContextHolder** ThreadLocal như nguồn mặc định cho pipeline reactive.
- Với unit test publisher có thể dùng **StepVerifier** và **ReactiveSecurityContextHolder.withAuthentication(auth)**; với WebTestClient context-bound, **mockJwt()/mockUser()** gắn Authentication qua WebFilter.
- Luôn có cả ca được phép và bị từ chối; nếu mock service trả sẵn 403 cho mọi request thì test có thể “xanh giả”.

### 7.4 JSON, headers, query và body

MockMvc thường truyền body qua chuỗi JSON; WebTestClient có **bodyValue(Object)** để dùng Jackson hoặc **BodyInserters** khi cần. Test nên assert cả status, Content-Type và dữ liệu quan trọng; kiểm tra response lỗi không làm rò secret. Với request có query params, dùng **uri(uriBuilder -> uriBuilder.path(...).queryParam(...).build())** thay cho việc nối chuỗi thủ công nhiều tham số.

Khi migration API contract, giữ nguyên case dữ liệu lỗi: body rỗng, invalid JSON, field thiếu, validation, header sai định dạng, unicode, quyền không đủ. Không chỉ test happy path 200.

## 8. Flux/SSE/streaming: không đem cách test asyncDispatch của Servlet sang nguyên trạng

Spring MVC có thể trả **DeferredResult/Callable** và cần **asyncDispatch()** trong một số MockMvc test. Với WebFlux, handler phát **Mono** hoặc **Flux**; WebTestClient subscribe pipeline. Đối với response hữu hạn dùng **expectBody()**, còn streaming dài hoặc vô hạn không nên gọi **expectBody()** để chờ toàn bộ stream.

Ví dụ minh họa khi endpoint đã trả **Flux<String>** và streaming theo giao thức thích hợp:

~~~java
// Đoạn ghép vào test có endpoint GET /api/events trả streaming body.
Flux<String> events = client
        .get().uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class)
        .getResponseBody();

StepVerifier.create(events.take(3))
        .expectNextCount(3)
        .verifyComplete();
~~~

Đây là snippet phụ, yêu cầu import **Flux**, **StepVerifier**, **MediaType** và endpoint streaming thực; không tồn tại trong fixture mục 4. Nếu body là **ServerSentEvent<T>** cần dùng ParameterizedTypeReference phù hợp và assert event/data theo format. Với stream không kết thúc, xác định rõ số phần tử, timeout, cancel/backpressure và dữ liệu kỳ vọng. Không biến **Flux** thành **blockLast()** trong Netty handler chỉ để test giống Servlet.

Test publisher ở service có thể dùng **StepVerifier** để assert **onNext/onError/onComplete**, đặc biệt khi kiểm việc phân quyền xảy ra trong lambda/operator lúc subscribe. HTTP test kiểm **WebFilter và status**, StepVerifier kiểm **semantics** của pipeline; hai loại bổ sung cho nhau.

## 9. Kế hoạch migration theo từng bước

1. **Chốt runtime:** xác nhận module thực sự là WebFlux, loại bỏ phụ thuộc MVC ngoài ý muốn hoặc ghi rõ trường hợp chạy chung có chủ đích. Quan sát log/startup và loại **SecurityFilterChain** đang được sử dụng.
2. **Phân loại test cũ:** test controller thuần, test security, service unit, integration với DB/IdP, streaming. Giữ test service hiện có nếu vẫn đúng; tập trung thay test phụ thuộc MockMvc/Servlet.
3. **Chọn setup mới:** **@WebFluxTest** cho slice, **@SpringBootTest + bindToApplicationContext** cho HTTP security trong bộ nhớ, **RANDOM_PORT + Bearer token thật** cho decoder/remote integration.
4. **Đổi API:** **perform(...) → ...exchange()**, **andExpect → expectStatus/expectBody**, **.with(jwt()/user()/csrf()) → .mutateWith(mockJwt()/mockUser()/csrf())**.
5. **Giữ security contract:** với từng route, có ít nhất request anonymous 401, authenticated thiếu quyền 403, đủ quyền 2xx và response mapping; bổ sung tenant/owner test nếu endpoint có ownership.
6. **Kiểm reactor context:** authorization ở method layer, scheduler hops, publisher lazy; không chuyển blocking logic sang event loop chỉ vì sửa test.
7. **Thử URL thật:** kiểm issuer/audience/signature/expiry, HTTP 401 với token sai, HTTPS/JWK/introspection và cấu hình hệ thống; mockJwt không bao phủ phần này.
8. **Chạy test và rà kết quả:** test report, mutation/authorization, race/timeout, không có false-positive do route không được nạp hoặc security filter bị loại trong slice.

Không xóa test cũ chỉ vì cách viết khác: sau khi test mới chứng minh cùng hành vi và runtime đã chuyển thật, mới loại đường MockMvc không còn giá trị. Nếu ứng dụng vẫn Servlet, WebTestClient qua HTTP có thể là công cụ test hợp lệ nhưng cần ghi đúng mục tiêu đo.

## 10. Gỡ lỗi các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| Tên test là WebFlux nhưng runtime lại MVC | Có cả starter-web và starter-webflux; WebApplicationType là SERVLET | Xem dependency graph/startup; điều chỉnh stack theo mục tiêu thực |
| Test nhận 401 dù đã dùng mockJwt() | WebTestClient không được gắn Spring Security test support đúng, hoặc gọi real HTTP | Dùng **bindToApplicationContext(...).apply(springSecurity())**; với real HTTP gửi JWT hợp lệ |
| JWT test nhận 403 | Rule yêu cầu **SCOPE_...** nhưng test cấp **ROLE_...** hoặc scope khác | Kiểm authority chính xác theo **hasAuthority** |
| Context lỗi thiếu ReactiveJwtDecoder | Bật Resource Server JWT nhưng không cấu hình decoder/JWKS và test không cung cấp bean | @MockBean ReactiveJwtDecoder trong test context, hoặc cấu hình decoder thật ở integration |
| Dùng mockUser() nhưng @AuthenticationPrincipal Jwt là null | Principal không phải Jwt | Đổi sang **mockJwt()** nếu test endpoint JWT, không cast tùy tiện |
| Test 200 dù filter không chạy | BindToController trực tiếp mà thiếu WebFilter/Security chain; permitAll sai rộng | Assert thêm 401/403, bind full context hoặc import security/filter vào slice |
| Test đăng nhập qua cookie bị 403 khi POST | CSRF bật và request chưa có token | Dùng **mutateWith(csrf())** trong test CSRF hợp lệ và ca thiếu CSRF |
| StepVerifier không thấy security context | Service tạo bằng **new**, context không truyền vào Reactor, subscribe ở nơi khác | Gọi Spring proxy, truyền Authentication bằng Reactor Context, không subscribe thủ công |
| Test request treo khi response Flux vô hạn | **expectBody()** chờ body kết thúc | Dùng **returnResult(...).getResponseBody()** + StepVerifier, take/cancel và timeout |
| MockMvc assertions bị lỗi import | Vẫn import **MockMvcRequestBuilders**, **SecurityMockMvcRequestPostProcessors** | Thay sang **WebTestClient** và **SecurityMockServerConfigurers** |
| Test JWT xanh nhưng production bị 401 | mockJwt() không gọi decoder/JWKS/issuer/audience validation | Thêm integration test token ký thật và validator tương ứng |
| Test thay đổi behavior khi đổi scheduler | Dùng ThreadLocal hoặc block/subscribe không đúng nơi | Giữ luồng Reactor, StepVerifier, quan sát event-loop và propagation |

**Cách khoanh vùng 401/403:** trước tiên xác định request đang đi qua context-bound WebFlux hay HTTP thật; tiếp theo xác định Authentication có được tạo không; cuối cùng so **authorities/claims** với rule cụ thể và service policy. Đừng tắt toàn bộ security để làm test pass, vì như vậy chính đường cần kiểm thử bị bỏ qua.

## 11. Tiêu chí nghiệm thu

Hoàn thành bài khi:

- Test WebFlux dùng **WebTestClient** và chạy qua đúng **SecurityWebFilterChain**.
- Có test kiểm **public, anonymous 401, thiếu scope 403, đủ scope 2xx**, đồng thời assert principal/claims đúng.
- Controller reactive vẫn trả **Mono/Flux** theo contract, không chèn **block()/subscribe()** thủ công để tương thích bài test cũ.
- Các ca body, headers, validation, CSRF (nếu có), method security và stream được chuyển theo đúng semantics.
- Tài liệu/test phân biệt rõ **mockJwt()** trong application context với **Bearer JWT thật** đi qua HTTP và decoder.
- Có bằng chứng chạy test với framework/dependency đúng stack, và có test tích hợp JWT signature/issuer/audience/expiry nếu dự án dùng Resource Server thật.

**Ghi nhớ:** mục đích chuyển từ MockMvc sang WebTestClient là kiểm thử đúng request pipeline của hệ thống reactive và giữ được các ranh giới bảo mật. Việc đổi tên API test chỉ là một phần; nguồn Authentication, WebFilter, Reactor Context và mức tích hợp của test mới quyết định kết quả có đáng tin hay không.