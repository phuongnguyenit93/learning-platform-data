# @WebFluxTest, @SpringBootTest và nạp đúng cấu hình bảo mật

## 1. Mục tiêu và tình huống lỗi thường gặp

Trong Spring Security reactive/WebFlux, một test HTTP có thể trả 200, 401 hoặc 403 mà **không hề nạp đúng `SecurityWebFilterChain` của production**. Trường hợp điển hình là dùng `@WebFluxTest` chỉ nạp controller và web infrastructure, nhưng bỏ sót `@Configuration` tùy chỉnh có bean `SecurityWebFilterChain`. Khi đó Spring Boot có thể áp một default security policy không giống ứng dụng thật; các negative tests vẫn pass, khiến ta nghĩ phân quyền đã được kiểm.

Ví dụ yêu cầu nghiệp vụ:

- `GET /health` công khai.
- `GET /api/reports/{id}` cần `ROLE_READER`.
- `POST /api/reports/{id}/preview` cần `ROLE_EDITOR` **và** CSRF token hợp lệ.
- Routes chưa được công bố bị deny.
- Controller gọi một `ReportService` reactive. Slice test dùng service mock; full test sử dụng implementation thật.
- Khi hệ thống sử dụng JWT, decoder còn phải kiểm chữ ký, issuer, audience, expiration; `mockJwt()` không thay thế bài test này.

**Câu hỏi cốt lõi:** Bộ test đang nạp bean bảo mật nào? Client có thật sự đi qua WebFlux Security filters không? Authentication là kết quả xác minh credentials thật hay chỉ là principal giả do test tự tạo?

Sau bài học, bạn sẽ:
1. Chọn đúng `@WebFluxTest`, `@SpringBootTest(MOCK)` hoặc `@SpringBootTest(RANDOM_PORT)`.
2. Biết khi nào phải `@Import(SecurityConfig.class)` để kiểm custom `SecurityWebFilterChain`.
3. Phân biệt `@MockBean` service với mock security policy.
4. Sử dụng `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
5. Test authentication Basic thật, mockUser/mockJwt, authorization roles và CSRF.
6. Viết full runnable-oriented Java 17+ Gradle project với ba cấp test.
7. Biết giới hạn của controller slice đối với `@PreAuthorize`, tenant/owner ACL, JWT decoder và live HTTP transport.
8. Đọc kết quả 200/401/403/404 có căn cứ, tránh false positives.

## 2. Bản đồ các cấp test HTTP trong WebFlux

~~~text
A. Unit Test:
   new ReportController(fakeService).read("r-1")
   → không Spring context, không security filters, không HTTP.

B. WebTestClient.bindToController(...)
   → controller handler mock; KHÔNG tự có app security chain.

C. @WebFluxTest(ReportController.class)
   + @Import(SecurityConfig.class)
   + @MockBean ReportService
   + WebTestClient + springSecurity()
   → Controller, WebFlux WebFilters, custom SecurityWebFilterChain
   → KHÔNG mở TCP port.

D. @SpringBootTest(MOCK)
   + @AutoConfigureWebTestClient
   → Full Spring application context, services/security thật
   → Mock HTTP runtime, KHÔNG mở TCP port.

E. @SpringBootTest(RANDOM_PORT)
   → Full context + Netty HTTP server thực ở port ngẫu nhiên
   → WebTestClient gửi HTTP thực; KHÔNG dùng mockUser qua socket.
~~~

| Tiêu chí | `@WebFluxTest` | `@SpringBootTest(MOCK)` | `@SpringBootTest(RANDOM_PORT)` |
| --- | --- | --- | --- |
| Component scan | Chỉ web slice | Toàn application | Toàn application |
| `@Service` thông thường | Thường loại khỏi slice | Có | Có |
| Custom security config | **Phải import có chủ đích** | Theo component scan | Theo component scan |
| Dùng Mockito mock service | Phổ biến | Có khi cần cô lập outbound dependency | Có khi cần cô lập outbound dependency |
| `WebTestClient` | Auto-configured | Thường thêm `@AutoConfigureWebTestClient` | Boot hỗ trợ live-bound client |
| Chạy real HTTP listener | Không | Không | **Có** |
| Kiểm security filters | Có nếu nạp đúng chain | Có | Có |
| Kiểm real password/JWT | Có nếu có real auth manager/decoder | Có | Có |
| Tốc độ/giá thành | Thường nhẹ | Trung bình | Nặng hơn |
| Nguy cơ test sai | Thiếu chain/service bean | Sai properties/external dependencies | Port/transport/state và mock-mutator |

**Lưu ý:** `@SpringBootTest` không khai báo `webEnvironment` mặc định dùng `MOCK`. Mock **web environment** không đồng nghĩa mọi service đều là Mockito mock. Với `RANDOM_PORT`, ứng dụng khởi động web server thật.

### 2.1. Phân biệt MVC và WebFlux

- `@WebMvcTest`/`MockMvc`/`HttpSecurity`/`SecurityFilterChain` dành cho **Servlet MVC**.
- `@WebFluxTest`/`WebTestClient`/`ServerHttpSecurity`/`SecurityWebFilterChain` dành cho **reactive WebFlux**.
- Spring Boot thường ưu tiên MVC khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` nằm trên classpath. Với dự án chỉ dùng WebFlux, không vô tình thêm Servlet starter.
- Nếu cần ép kiểu reactive khi cả hai có mặt, cân nhắc `spring.main.web-application-type=reactive` nhưng tốt nhất là sửa dependency graph.

## 3. Vì sao @WebFluxTest phải nhập riêng SecurityConfig?

Tài liệu Spring Boot 3.3 nêu rõ `@WebFluxTest` **không tự phát hiện custom security configuration đăng ký bean `SecurityWebFilterChain`**. Slice chủ yếu nạp các thành phần web như controller, controller advice, JSON/converters, `WebFluxConfigurer` và một số infrastructure. Nó không tự nạp mọi `@Configuration`, `@Service` và `@Repository`.

Cấu trúc chuẩn:

~~~java
@WebFluxTest(controllers = ReportController.class)
@Import(SecurityConfig.class)
class ReportSliceTest {
    @MockBean
    ReportService reports;
}
~~~

- `@WebFluxTest` nạp controller và test infrastructure.
- `@Import(SecurityConfig.class)` nạp **security policy thật**.
- `@MockBean ReportService` cung cấp service giả để tránh kéo DB/business graph vào slice.
- `@Import` không tự là bằng chứng filter chain đang thực thi; phải dùng `WebTestClient` gắn security filters và test hành vi.
- Nếu security config phụ thuộc `ReactiveJwtDecoder` hoặc policy service, bổ sung bean đúng phạm vi test; đừng tắt cả chain để làm context start.

**Tại sao test chỉ 401/403 chưa đủ?** Một default `denyAll` hoặc auto-generated “anyRequest authenticated” cũng có thể trả 401/403. Bạn cần **positive tests**: anonymous `GET /health` → 200, reader → 200, editor+CSRF → 200, bên cạnh negative tests. Khi custom config được import, tên bean `securityChain` cũng có thể được assert trong context.

### 3.1. Không nên @Import toàn bộ Application để có security

`@Import(TestingApplication.class)` có thể kích hoạt component scanning sâu và kéo R2DBC, Kafka, Redis hoặc các beans không cần thiết. Tốt hơn:
- Tách `SecurityConfig` thành class nhỏ chỉ cấu hình security/authentication.
- `@Import(SecurityConfig.class)` và mock đúng service dependencies.
- Dùng full `@SpringBootTest` khi thật sự cần kiểm sự phối hợp giữa security, service, repository.

### 3.2. Functional endpoints là ngoại lệ

`@WebFluxTest` không tự scan mọi `RouterFunction` của WebFlux.fn. Nếu app dùng `RouterFunctions.route(...)` cần import router config/bean hoặc dùng `@SpringBootTest`. `bindToController` cũng không tự dựng functional router.

## 4. @SpringBootTest: bốn webEnvironment

| Giá trị | Nghĩa |
| --- | --- |
| `MOCK` (default) | Full context, mock web infrastructure, không HTTP socket |
| `RANDOM_PORT` | Full context, web server thực listen trên random port |
| `DEFINED_PORT` | Full context, server ở cổng xác định (dễ gây xung đột automated tests) |
| `NONE` | Application context không web runtime |

Đối với full WebFlux mock HTTP test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockHttpTest {
    @Autowired WebTestClient client;
}
~~~

Đối với live HTTP test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LivePortHttpTest {
    @Autowired WebTestClient client;
    @LocalServerPort int port;
}
~~~

`@AutoConfigureWebTestClient` giúp tạo client cho mock full context; nó **không** khởi động server socket. Với live-port client đã autowire, request tương đối như `/api/reports/r-1` được gửi tới cổng ngẫu nhiên do Boot quản lý.

Nếu test dùng `@Transactional` và `RANDOM_PORT`, transaction phía HTTP server có thể tách khỏi transaction của test thread; không giả định rollback ở test tự hoàn tác server-side commits. Thiết kế fixtures/cleanup phù hợp.

## 5. WebTestClient và Spring Security test support

Trong mock web environment:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

`bindToApplicationContext(...)` dùng WebFlux controllers/filters của context; `apply(springSecurity())` cài hỗ trợ Spring Security Test như `mockUser()`/`csrf()`. Không dùng mỗi `bindToController(...)` rồi tin nó tự thêm production security chain.

### 5.1. Ba loại credentials trong test

| Cách | Thực hiện kiểm mật khẩu/chữ ký? | Dùng để |
| --- | --- | --- |
| `client.mutateWith(mockUser("alice").roles("READER"))` | **Không** | Kiểm route/authorization với principal giả |
| `@WithMockUser` | **Không** | Kiểm method/HTTP authorization trong mock context |
| `client.mutateWith(mockJwt())` | **Không** | Kiểm JWT principal/authority giả, không kiểm decoder |
| `headers(h -> h.setBasicAuth("reader","reader-pass"))` | **Có** khi chain/manager thật được nạp | Kiểm HTTP Basic authentication |
| `headers(h -> h.setBearerAuth(signedJwt))` | **Có** khi decoder JWT thật được nạp | Kiểm signature/claims/route authorization |
| Live HTTP + Basic/Bearer headers | **Có** | Kiểm network transport và authentication |

`mockUser()` và `mockJwt()` không có lỗi về bản chất: chúng chủ động loại bỏ phần khó để test logic authorization. Sai lầm là mô tả kết quả này như một kiểm chứng signing key/password/issuer/audience đã đúng.

### 5.2. CSRF trong WebFlux tests

Với unsafe methods như POST/PUT/DELETE và CSRF enabled, cần token hợp lệ:

~~~java
client.mutateWith(csrf())
    .post().uri("/api/reports/r-1/preview")
    .headers(h -> h.setBasicAuth("editor","editor-pass"))
    .bodyValue(new PreviewRequest("Draft"))
    .exchange()
    .expectStatus().isOk();
~~~

Đây là `SecurityMockServerConfigurers.csrf()` dành cho WebTestClient, **không** phải `MockMvcRequestPostProcessors.csrf()` dành cho Servlet. Trong ví dụ sử dụng HTTP Basic, CSRF được giữ vì browser có thể tự gửi Basic credentials theo cơ chế ambient auth. Với API thuần Bearer header, quyết định CSRF cần dựa threat model; không disable vô điều kiện chỉ để test pass.

## 6. Project Java 17+ để đối chiếu ba kiểu test

Mục tiêu project:
- Spring Boot **3.3.13**, Gradle 8.x, Java 17+.
- WebFlux + Spring Security reactive.
- Hai users **chỉ dùng cho lab**: reader có `ROLE_READER`, editor có `ROLE_READER` và `ROLE_EDITOR`.
- `/health` công khai, GET report cần reader, POST preview cần editor + CSRF.
- Service stateless để kết quả deterministic.
- 3 test classes: slice, full MOCK, live-port.

**An toàn:** Dùng `{noop}` password để minh họa HTTP Basic, **không dùng trong production**. Production cần password hashing/IdP, HTTPS, quyền owner/tenant và audit.

~~~text
webflux-security-testing/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/testing/
    │   ├── TestingApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportService.java
    │   ├── DefaultReportService.java
    │   └── ReportController.java
    └── test/java/demo/testing/
        ├── ReportSliceTest.java
        ├── FullContextMockHttpTest.java
        └── LivePortHttpTest.java
~~~

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-security-testing'
~~~

### 6.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong Boot 3.3, dùng `org.springframework.boot.test.mock.mockito.MockBean`; ở các phiên bản mới, Spring Framework `@MockitoBean` đã thay thế dần cách cũ. Đừng trộn imports từ hướng dẫn Boot mới với project 3.3 mà không kiểm API.

### 6.3. TestingApplication.java

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

### 6.4. SecurityConfig.java

~~~java
package demo.testing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasRole("EDITOR")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // CSRF mặc định vẫn enabled; không csrf.disable().
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .roles("READER")
            .build();
        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor-pass")
            .roles("READER", "EDITOR")
            .build();
        return new MapReactiveUserDetailsService(
            reader, editor);
    }
}
~~~

**Đọc config:**
- `@EnableWebFluxSecurity` và `SecurityWebFilterChain` sử dụng `ServerHttpSecurity`, không phải `HttpSecurity` Servlet.
- `GET /health` là sentinel 200 khi policy thật được nạp.
- `hasRole("READER")` và `hasRole("EDITOR")` kiểm authorities tương ứng `ROLE_READER`/`ROLE_EDITOR`; không nhầm `SCOPE_` của OAuth2 JWT.
- `anyExchange().denyAll()` bảo vệ routes/methods khác.
- `httpBasic` yêu cầu đúng username/password của reactive user details service.
- `formLogin` bị tắt để tránh HTML login trong API demo; CSRF vẫn bật.
- Role được khai trong source chỉ để lab; ứng dụng thật không hardcode passwords.

### 6.5. ReportService.java

~~~java
package demo.testing;

import reactor.core.publisher.Mono;

interface ReportService {
    Mono<ReportView> read(String id);
    Mono<ReportView> preview(String id, String title);
}

record ReportView(String id, String title) {}

record PreviewRequest(String title) {}
~~~

Các Java records chỉ chứa dữ liệu JSON cho HTTP. `preview` không ghi database; mục đích là kiểm authz/CSRF với POST.

### 6.6. DefaultReportService.java

~~~java
package demo.testing;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class DefaultReportService implements ReportService {

    @Override
    public Mono<ReportView> read(String id) {
        return Mono.defer(() -> {
            if (!"r-1".equals(id)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }
            return Mono.just(new ReportView(
                id, "Report " + id));
        });
    }

    @Override
    public Mono<ReportView> preview(String id, String title) {
        return Mono.defer(() -> {
            if (!"r-1".equals(id)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }
            return Mono.just(new ReportView(id, title));
        });
    }
}
~~~

Trong full context, service implementation này là `@Service` thật. Trong `@WebFluxTest`, nó không được component-scanned; test cung cấp `@MockBean ReportService`. Chính sự khác biệt này minh họa ranh giới giữa slice và full integration.

### 6.7. ReportController.java

~~~java
package demo.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ReportController {

    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/reports/{id}")
    Mono<ReportView> read(@PathVariable String id) {
        return reports.read(id);
    }

    @PostMapping("/api/reports/{id}/preview")
    Mono<ReportView> preview(
            @PathVariable String id,
            @RequestBody Mono<PreviewRequest> body) {
        return body.flatMap(request ->
            reports.preview(id, request.title()));
    }
}
~~~

Controller không tự đọc user ID/role từ header request. Trong production, service/repository phải kiểm thêm tenant, ownership và ACL của report, không coi `ROLE_READER` là quyền xem mọi tài liệu.

## 7. Kiểm thử @WebFluxTest với security config thật

`src/test/java/demo/testing/ReportSliceTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(controllers = ReportController.class)
@Import(SecurityConfig.class)
class ReportSliceTest {

    @Autowired
    ApplicationContext context;

    @MockBean
    ReportService reports;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void loadsCustomChain() {
        assertThat(context.containsBean("securityChain"))
            .isTrue();
    }

    @Test
    void publicHealthReturns200() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void anonymousGetReturns401() {
        client.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
        verifyNoInteractions(reports);
    }

    @Test
    void incorrectBasicPasswordReturns401() {
        client.get().uri("/api/reports/r-1")
            .headers(h -> h.setBasicAuth("reader","invalid"))
            .exchange()
            .expectStatus().isUnauthorized();
        verifyNoInteractions(reports);
    }

    @Test
    void correctReaderGetsMockServiceResult() {
        given(reports.read("r-1")).willReturn(
            Mono.just(new ReportView("r-1","From mock")));

        client.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("r-1")
            .jsonPath("$.title").isEqualTo("From mock");

        verify(reports).read("r-1");
    }

    @Test
    void mockUserOnlyTestsAuthorizationRule() {
        given(reports.read("r-1")).willReturn(
            Mono.just(new ReportView("r-1","From mock")));

        client.mutateWith(
                mockUser("fake-reader").roles("READER"))
            .get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isOk();
        // Không chứng minh mật khẩu user "fake-reader".
    }

    @Test
    void readerWithCsrfStillCannotPost() {
        client.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }

    @Test
    void editorWithoutCsrfCannotPost() {
        client.post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }

    @Test
    void editorWithCsrfGets200() {
        given(reports.preview("r-1","Draft")).willReturn(
            Mono.just(new ReportView("r-1","Draft")));

        client.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Draft");

        verify(reports).preview("r-1","Draft");
    }

    @Test
    void deleteMethodIsNotAllowedByPolicy() {
        client.delete().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }
}
~~~

### 7.1. Mười test method kiểm những ranh giới nào?

| Nhóm | Các assertions | Lớp được kiểm |
| --- | --- | --- |
| Bean hiện diện | `securityChain` tồn tại | Wiring của `@Import` |
| Public route | health 200 | Custom `permitAll` |
| Anonymous/invalid password | GET 401 | HTTP Basic authentication/filter |
| Reader hợp lệ | GET 200, mock gọi đúng | Authn/authz + controller |
| MockUser | GET 200 | **Chỉ** authorization with fake Authentication |
| Role thiếu | Reader POST có CSRF → 403 | `hasRole("EDITOR")` |
| CSRF thiếu | Editor POST → 403 | CSRF filter |
| Role+CSRF đúng | Editor POST → 200 | Positive HTTP/security path |
| Method chưa cấp | DELETE → 403 | `denyAll` |

Một `@WebFluxTest` nạp sai security có thể trả 401/403 ở nhiều negative cases; **positive 200 tests** và bean assertion giúp phát hiện sai wiring.

### 7.2. Vì sao không mock SecurityWebFilterChain?

Nếu mục tiêu là kiểm authorization thật, mock chain hoặc cấu hình `permitAll` trong test làm test vô nghĩa. Hãy mock collaborator `ReportService`, còn chain phải là bean đúng production policy.

### 7.3. Slice không chứng minh quyền ở data layer

`@MockBean ReportService` thay thế business implementation. Vì vậy test 200 chỉ chứng minh HTTP/serialization/controller/role rule, **không** chứng minh:
- `@PreAuthorize` trên real service đã chạy.
- Tenant A bị chặn đọc dữ liệu tenant B.
- R2DBC query có owner/tenant predicate.
- Database row-level security/transactions đúng.
- User vừa bị khóa vẫn bị từ chối.

Những nội dung đó cần service/repository tests hoặc full integration với real beans và test DB.

## 8. Kiểm thử @SpringBootTest(MOCK) + @AutoConfigureWebTestClient

`src/test/java/demo/testing/FullContextMockHttpTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockHttpTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebTestClient bootClient;

    @Autowired
    ReportService reports;

    @Test
    void usesRealServiceAndCorrectSecurityConfig() {
        assertThat(reports)
            .isInstanceOf(DefaultReportService.class);
        assertThat(context.containsBean("securityChain"))
            .isTrue();
    }

    @Test
    void anonymousIs401InFullContext() {
        bootClient.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void actualServiceReturnsExpectedContent() {
        bootClient.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("r-1")
            .jsonPath("$.title").isEqualTo("Report r-1");
    }

    @Test
    void unknownReportIs404AfterAuthentication() {
        bootClient.get().uri("/api/reports/other")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void fullContextStillRequiresCsrfForPost() {
        WebTestClient secureClient = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        secureClient.post()
            .uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();

        secureClient.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Draft");
    }
}
~~~

**Năm methods** minh họa full application context với **real service** nhưng mock web runtime. `bootClient` được Boot tạo nhờ `@AutoConfigureWebTestClient`; `secureClient` được bind rõ vào ApplicationContext và apply `springSecurity()` để dùng CSRF mutator.

**Lưu ý:** Full context của ứng dụng thật có thể nạp R2DBC/Kafka/Redis/OAuth2 clients. Dùng `@ActiveProfiles("test")`, test-specific configurations, Testcontainers hoặc mock **đúng outbound dependencies**, không tắt security chain để khởi động thành công.

## 9. Kiểm thử @SpringBootTest(RANDOM_PORT) — HTTP thật

`src/test/java/demo/testing/LivePortHttpTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LivePortHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void webServerHasRealRandomPort() {
        assertThat(port).isPositive();
    }

    @Test
    void noAuthenticationReturns401OverHttp() {
        client.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicReaderGets200OverHttp() {
        client.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Report r-1");
    }
}
~~~

**Ba methods** đi qua Netty/HTTP socket thật. `@LocalServerPort` dùng để kiểm port; Boot có thể tự cấu hình WebTestClient để gửi tới live server. Không dùng `mockUser()` hoặc `mockJwt()` mutator làm credential cho server thực; mutator tác động mock server context, **không** đi trên dây TCP.

### 9.1. Kết quả tổng

Ba test classes có **18 phương thức test**: 10 slice + 5 full MOCK + 3 RANDOM_PORT. Chúng được thiết kế để pass trên Java 17/Spring Boot 3.3.13 với dependency tương thích, nhưng **chưa có log biên dịch/chạy thật trong bài viết**. Phải chạy Gradle trước khi khẳng định `BUILD SUCCESSFUL`.

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Khởi động app:

~~~bash
gradle bootRun
~~~

Thử:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/reports/r-1
curl -i -u reader:reader-pass http://localhost:8080/api/reports/r-1
~~~

Kỳ vọng:
- GET `/health` → HTTP 200, body `ok`.
- GET report không credentials → HTTP 401.
- GET report với reader hợp lệ → HTTP 200, JSON `{"id":"r-1","title":"Report r-1"}`.
- POST preview với editor nhưng không có CSRF token → 403. Test mock web client dùng `csrf()` để minh họa successful POST; demo chưa cung cấp endpoint cấp CSRF token cho curl/browser.

**Chỉ dùng demo passwords trên localhost.** HTTP Basic qua Internet cần HTTPS và thiết kế authentication phù hợp.

## 10. Khi dùng OAuth2 Resource Server JWT thay HTTP Basic

Các bài kiểm thử vẫn cần bảo đảm nạp đúng `SecurityWebFilterChain`.

### 10.1. JWT chain minh họa (không thuộc runnable Basic project)

~~~java
@Configuration
@EnableWebFluxSecurity
class JwtSecurityConfig {
    @Bean
    SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Cần `spring-boot-starter-oauth2-resource-server` và một `ReactiveJwtDecoder` cấu hình đúng issuer/JWKS/audience. Với JWT, scopes mặc định thường thành `SCOPE_*`; đừng nhầm với `ROLE_*` trong ví dụ Basic.

### 10.2. JWT slice test và decoder dependency

~~~java
@WebFluxTest(ProtectedReportController.class)
@Import(JwtSecurityConfig.class)
class JwtSliceTest {

    @MockBean
    ReactiveJwtDecoder decoder;

    // Client mock context + apply(springSecurity())
    // client.mutateWith(mockJwt().authorities(
    //    new SimpleGrantedAuthority("SCOPE_reports.read")))
    //    .get().uri("/api/reports/r-1") ...
}
~~~

Đây là **snippet không độc lập**; `ProtectedReportController` là ví dụ tên controller trong ứng dụng JWT khác, không phải một file thuộc runnable Basic project. `@MockBean ReactiveJwtDecoder` có thể thỏa dependency của chain trong slice, còn `mockJwt()` tạo Authentication giả để test authorization. **Kết quả này KHÔNG kiểm chữ ký, issuer, audience hay JwtAuthenticationConverter thật**.

### 10.3. Muốn kiểm cryptographic validation, làm sao?

Dùng full-context mock/live tests với `Authorization: Bearer <signed-JWT>` thực:
- Test-only RSA private key ký JWT.
- `NimbusReactiveJwtDecoder` chỉ tin public key test.
- `JwtValidators.createDefaultWithIssuer(issuer)` + audience validator.
- JWT đúng chữ ký/issuer/audience/expiry + quyền → 200.
- JWT hợp lệ nhưng thiếu `SCOPE_reports.read` → 403.
- JWT bị sửa, sai chữ ký/issuer/audience/exp → 401.
- `@TestConfiguration` decoder được inject chỉ vào tests, **không** đóng gói private signing key vào production.
- Test riêng JWKS metadata discovery, caching/rotation và TLS nếu đó là scope hệ thống.
- Với `RANDOM_PORT`, truyền **real Bearer header** chứ không dùng `mockJwt()`.

Một test `mockJwt().authorities(ROLE_ADMIN)` trả 200 không chứng minh attacker không thể giả chữ ký. Nó chỉ chứng minh rule dùng authority.

## 11. Method security và quyền dữ liệu không nằm trong controller mock

Giả sử service thật có:

~~~java
@Service
class ReportWriteService {
    @PreAuthorize("hasAuthority('SCOPE_reports.write')")
    Mono<Void> update(String reportId) {
        return Mono.empty();
    }
}
~~~

Nếu slice dùng `@MockBean ReportWriteService`, method thật **không chạy**, vì vậy `@PreAuthorize` ở method đó cũng không được kiểm như bạn tưởng. Phải có `@EnableReactiveMethodSecurity` trong config thích hợp, gọi qua Spring proxy và test service real hoặc full context.

Cần kiểm riêng:
1. Unauthorized user bị deny trước side effects.
2. User có scope nhưng sai tenant vẫn bị deny.
3. Repository query/update có tenant/owner predicates, tránh IDOR/BOLA.
4. Permission thay đổi/revoke khi token còn hạn được xử lý theo policy.
5. Reactor SecurityContext được propagate qua các Mono/Flux, không dựa ThreadLocal Servlet.
6. Self-invocation hoặc `new ReportWriteService()` có thể bỏ qua proxy method security.

**Đừng** dùng controller slice pass để tuyên bố repository/object authorization đã được kiểm.

## 12. Nhiều SecurityWebFilterChain và chọn chain đúng

Khi có nhiều chains:
- `securityMatcher` chọn **chain** áp dụng theo request.
- `authorizeExchange` quy định **quyền** trong chain được chọn.
- `@Order` ảnh hưởng thứ tự ưu tiên.
- Một test import thiếu chain JWT có thể khiến request đi vào fallback Basic/default chain và trả response sai.

Ví dụ thiết kế:

~~~text
@Order(1) /api/**  → JWT chain, SCOPE_api.read
@Order(2) fallback → Basic/login chain, ROLE_USER
~~~

Các test nên có:
- `/api/reports` không token 401, JWT valid đúng scope 200, thiếu scope 403.
- `/web/**` theo login policy của chain thứ hai.
- Route không khớp → deny.
- Method POST khác GET; CSRF policy khác theo chain.
- Positive và negative assertions cho **mỗi** ranh giới, không chỉ có `getBean(SecurityWebFilterChain.class)`.

Nếu mục tiêu slice chỉ một chain, hãy ghi rõ và import đúng config; integration full context phải xác nhận thứ tự và tương tác của mọi chains.

## 13. Troubleshooting khi test bảo mật WebFlux bị sai

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `@WebFluxTest` health 401 thay vì 200 | Không nạp custom `SecurityWebFilterChain` | `@Import(SecurityConfig.class)` |
| Controller slice thiếu bean ReportService | `@Service` bị loại khỏi slice | `@MockBean ReportService` |
| Context thiếu ReactiveJwtDecoder | Đã import JWT chain nhưng thiếu decoder | Mock decoder/test config hoặc full test |
| `bindToController` test 200 nhưng production 401 | Không có security filters | Bind ApplicationContext + apply(springSecurity()) |
| `mockUser` pass dù password sai | Mock bypass password manager | Test HTTP Basic thật |
| JWT mock pass nhưng signed JWT 401 | Mock bypass signature/issuer/audience | Test Bearer signed JWT và decoder |
| POST đúng editor nhưng 403 | Thiếu CSRF hoặc role sai | Hai test role+CSRF riêng |
| DELETE 403 | `denyAll` hoặc CSRF | Test path/method matcher, không mở tùy tiện |
| `@SpringBootTest(MOCK)` không autowire WebTestClient | Thiếu auto-config | `@AutoConfigureWebTestClient` |
| Random-port test không có server | Web environment hoặc startup lỗi | Kiểm starter webflux, logs, config |
| Security config bean có nhưng route sai | Multiple chain order hoặc matcher sai | Positive/negative tests từng chain |
| `@PreAuthorize` không chặn trong slice | Service bị mock/thiếu method security | Full tests với proxied real service |
| Slice nạp DB ngoài ý muốn | Explicit @ComponentScan gây mở scope | Tách configs/import nhỏ |
| Context không tìm thấy app class | Test nằm sai package | Đặt test trong package tree hoặc specify classes |
| 403 với user có role | `SCOPE_` khác `ROLE_`/CSRF/tenant ACL | Kiểm authority, policy và data |
| Toàn negative tests pass | Chain deny-all cũng có thể pass | Thêm health/authorized 200 |
| @MockBean API lỗi trên Boot mới | Phiên bản framework thay đổi | Dùng @MockitoBean tương ứng version |
| Test live DB side effects không rollback | HTTP server transaction khác test thread | Setup/cleanup dữ liệu riêng |
| Browser có CORS lỗi nhưng WebTestClient pass | Test không gửi Origin/preflight | Test CORS riêng, không coi CORS là auth |

### 13.1. Những cách “sửa” sai

- **Sai:** vô hiệu hóa CSRF khi test POST 403 mà không hiểu nguyên nhân.
- **Sai:** thay toàn bộ SecurityConfig thành `permitAll` trong test đang được mô tả là “kiểm security”.
- **Sai:** `@Import(TestingApplication.class)` để kéo cả app vào web slice.
- **Sai:** dùng `mockJwt()` rồi kết luận JWT crypto đáng tin.
- **Sai:** chỉ kiểm status 401/403 mà không có test 200.
- **Sai:** đặt `@WithMockUser` trong live TCP test rồi tin request thực mang principal đó.
- **Đúng:** xác định test scope, nạp config thật cho security, dùng mock chỉ ở boundary ngoài scope và kiểm hành vi đầy đủ.

## 14. Các bài tập tự kiểm

**Câu 1.** `@WebFluxTest` có tự nạp custom `SecurityWebFilterChain` không?

**Đáp án:** Không được bảo đảm; Boot 3.3 nêu rõ không tự detect. Dùng `@Import(SecurityConfig.class)` hoặc full context.

**Câu 2.** `@SpringBootTest` mặc định mở port thực không?

**Đáp án:** Không. `MOCK` là default; dùng `RANDOM_PORT` cho HTTP server thực.

**Câu 3.** `@AutoConfigureWebTestClient` có tự mở Netty socket không?

**Đáp án:** Không. Nó là auto-config client trong context.

**Câu 4.** Vì sao health 200 là sentinel tốt nhưng chưa đủ?

**Đáp án:** Thiếu import có thể khiến default chain từ chối health. Nhưng một chain permitAll toàn app cũng cho 200; cần protected positives/negatives.

**Câu 5.** `mockUser("reader")` có kiểm password reader-pass không?

**Đáp án:** Không. Dùng HTTP Basic request thật để kiểm password path.

**Câu 6.** `mockJwt()` có kiểm signature và JWKS không?

**Đáp án:** Không. Dùng signed JWT Bearer qua ReactiveJwtDecoder.

**Câu 7.** Editor có quyền nhưng POST không CSRF nhận gì trong demo?

**Đáp án:** 403.

**Câu 8.** Reader có CSRF nhưng thiếu ROLE_EDITOR?

**Đáp án:** 403.

**Câu 9.** Editor có CSRF và service trả report?

**Đáp án:** 200.

**Câu 10.** Dùng @MockBean service có kiểm @PreAuthorize trên service thật không?

**Đáp án:** Không. Cần test method security với real proxied service.

**Câu 11.** @WebFluxTest không tự load functional RouterFunction, làm gì?

**Đáp án:** @Import router configuration hoặc @SpringBootTest.

**Câu 12.** Trong RANDOM_PORT, nên dùng mockUser() thay Basic credentials qua TCP không?

**Đáp án:** Không; mockUser không phải HTTP credential trên wire.

**Câu 13.** Một JWT có SCOPE_reports.read nhưng service check hasRole("READER"), có khớp không?

**Đáp án:** Không mặc định; `SCOPE_` và `ROLE_` khác nhau.

**Câu 14.** Tại sao test @Transactional không tự rollback server commit qua RANDOM_PORT?

**Đáp án:** Client/server HTTP thực ở execution/transaction contexts khác nhau; cần cleanup test data.

**Câu 15.** Controller slice đã test 200, có đủ chứng minh tenant B bị từ chối không?

**Đáp án:** Không khi service/repository bị mock. Cần object/tenant data-layer integration tests.

## 15. Checklist trước khi merge các bài test bảo mật

- [ ] Project thực sự là WebFlux; không nhầm MVC annotations.
- [ ] Dùng `@WebFluxTest` cho controller slice, import đúng `SecurityConfig`.
- [ ] Mock service/dependency ngoài scope, không mock SecurityWebFilterChain đang kiểm.
- [ ] Có sentinel public route 200 và protected positive 200.
- [ ] Có anonymous 401, wrong credential 401, missing role 403.
- [ ] Có CSRF allowed/denied tests cho unsafe methods.
- [ ] WebTestClient mock context được apply `springSecurity()` khi dùng mutators.
- [ ] `@SpringBootTest(MOCK)` có `@AutoConfigureWebTestClient` hoặc bind context rõ.
- [ ] `RANDOM_PORT` test dùng Basic/Bearer credentials thật, không mock principal qua TCP.
- [ ] Multiple chains được kiểm path/order/method đúng.
- [ ] Method security được kiểm trên real service/proxy khi thuộc phạm vi.
- [ ] JWT resource server tests có bài ký thật để kiểm signature/issuer/audience/expiry.
- [ ] Tenant/owner/resource policy được test ở data boundary.
- [ ] Test không dùng production passwords, tokens, databases hoặc IdP.
- [ ] Build với framework version chính xác, update imports khi nâng Boot.
- [ ] Tách các case 401/403/404 và nguyên nhân theo response contract.
- [ ] Không disable CSRF hoặc thêm permitAll để “làm đẹp” kết quả tests.
- [ ] Test fixtures deterministic, có cleanup khi live-port writes.
- [ ] Không claim đã verify security production chỉ từ một controller slice.

## 16. Nguồn tham khảo chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, @WebFluxTest, @SpringBootTest, RANDOM_PORT, auto-config WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — WebFluxTest API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Security — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive Authentication Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Reactive CSRF Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — Testing OAuth2 and mockJwt: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot — How-to Testing: https://docs.spring.io/spring-boot/how-to/testing.html

**Ghi nhớ:** `@WebFluxTest` cần `@Import(SecurityConfig.class)` nếu phải kiểm custom `SecurityWebFilterChain`; `@SpringBootTest(MOCK)` dùng full context không mở HTTP server, còn `RANDOM_PORT` mở server thật. `WebTestClient` phải đi qua đúng filter chain, không chỉ bind vào controller. Hãy dùng mockUser/mockJwt cho authorization tests, real Basic/JWT credentials cho authentication tests, và kiểm **cả cases được cho phép lẫn bị từ chối** để tránh false confidence do security policy không được nạp đúng.
