# Xây dựng ma trận kiểm thử bảo mật, lỗi phụ thuộc và rò rỉ ngữ cảnh trong Spring Security WebFlux

> **Bối cảnh:** thực hành tổng hợp cho Spring Boot 3.x, Spring Security 6.x, Java 17+ và WebFlux/Reactor. Bài học xây một **ma trận kiểm thử có thể chạy và mở rộng**, gồm xác thực, phân quyền, lỗi dịch vụ phụ thuộc và cô lập Security Context giữa các luồng reactive. Ví dụ thực thi dùng HTTP Basic với tài khoản **chỉ dành cho lab** để kiểm tra các nhánh bảo mật mà không phụ thuộc IdP bên ngoài; phần JWT/opaque token có ma trận và kiểm thử contract riêng. HTTP Basic phải chạy sau HTTPS trong môi trường thực tế.

Trong hệ thống reactive, một yêu cầu được trả HTTP 200 chưa chứng minh hệ thống an toàn. Phải chứng minh **người không có quyền bị từ chối**, **sự cố phụ thuộc không biến thành quyền truy cập**, và **danh tính của request A không lẫn vào request B khi Reactor đổi scheduler hoặc hai publisher chạy đồng thời**.

## 1. Mục tiêu và sản phẩm cuối bài

Người học cần thực hiện được:

1. Lập bảng `endpoint × HTTP method × identity × authority × trạng thái dependency → kết quả kỳ vọng`.
2. Biến từng hàng ma trận thành một test thực tế với `WebTestClient`, không chỉ kiểm tra controller bằng unit test thuần.
3. Phân biệt **401** (thiếu/không hợp lệ authentication), **403** (đã xác thực nhưng thiếu quyền, hoặc CSRF từ chối), **2xx** (được cho phép) và **5xx** (dịch vụ phụ thuộc không khả dụng).
4. Mô phỏng dịch vụ nghiệp vụ lỗi, timeout, trả rỗng, IdP lỗi xác minh token, chính sách phân quyền không sẵn sàng; kiểm tra hệ thống **fail closed** cho dữ liệu nhạy cảm.
5. Kiểm thử `ReactiveSecurityContextHolder` theo từng **subscription** và phát hiện cache/biến toàn cục/subscribe thủ công làm lộ danh tính.
6. Đánh giá đúng phạm vi của `mockUser()`, `mockJwt()`, `mockOpaqueToken()` so với kiểm thử HTTP xác thực thật.
7. Tạo kết quả CI có thể truy vết: mỗi lỗi chỉ ra input, kỳ vọng và quan sát; không ghi raw token/password vào log.

**Đầu ra:** một bộ test gồm ma trận quyền, ba nhóm lỗi dependency, test cô lập Reactor Context, và danh sách kiểm tra tích hợp JWT/opaque token. Mục tiêu học tập là có bằng chứng khách quan rằng ứng dụng từ chối đúng và cô lập đúng, không chỉ “có Spring Security trong dependencies”.

## 2. Ba lớp cần kiểm thử riêng

Một HTTP request WebFlux đi qua các lớp sau:

```text
HTTP request
   |
   v
[SecurityWebFilterChain được chọn]
   |
   +-- authentication
   |      - HTTP Basic / OAuth2 Login / JWT / opaque token
   |      - thiếu hoặc token sai: thường HTTP 401 hoặc redirect login
   |
   +-- authorization trong authorizeExchange
   |      - hasRole / hasAuthority / authenticated / permitAll
   |      - đã xác thực nhưng thiếu quyền: thường HTTP 403
   |
   v
[Handler / @PreAuthorize nếu có]
   |
   +-- truy cập danh tính qua ReactiveSecurityContextHolder
   |
   v
[Reactive dependency: R2DBC / WebClient / Redis / IdP / policy service]
   |
   +-- thành công / trả rỗng / 5xx / timeout / không kết nối
   |
   v
[Response HTTP + trace/metric đã che dữ liệu nhạy cảm]
```

Có **hai dạng dependency** cần phân biệt:

- **Phụ thuộc xác thực/phân quyền:** JWK Set, token introspection, external policy decision point (PDP), truy vấn quyền/tenant. Khi không đủ bằng chứng xác minh, không được tự cho phép truy cập. HTTP response chính xác phụ thuộc framework, exception mapping và giao thức; phải đo ở tầng WebFlux.
- **Phụ thuộc nghiệp vụ sau khi đã xác thực:** kho báo cáo, R2DBC, Redis, gRPC, WebClient. Nếu dependency lỗi, API có thể trả 503/504/5xx theo contract, nhưng **không** trả dữ liệu của một người/tenant khác và không dùng dữ liệu không còn hợp lệ làm quyền thay thế.

Một response 503 không có nghĩa Security đã thất bại. Nó có thể chứng minh Security **đã cho đúng principal đi vào handler**, rồi handler xử lý downstream failure có kiểm soát. Vì vậy ma trận phải ghi rõ **lỗi xảy ra ở lớp nào**.

## 3. Thiết kế ma trận bảo mật có thể hành động

### 3.1. Bước đầu: mô tả hợp đồng tài nguyên

Giả sử ứng dụng có các route:

| Endpoint và method | Khách vô danh | User đã đăng nhập | Quyền đặc biệt | Phụ thuộc |
| --- | --- | --- | --- | --- |
| `GET /public` | Cho phép | Cho phép | Không | Không |
| `GET /api/me` | Chặn | Cho phép | `authenticated` | Reactor Security Context |
| `GET /api/report` | Chặn | Chỉ nếu có scope | `SCOPE_reports:read` | Report Gateway |
| `GET /api/admin` | Chặn | Chỉ ADMIN | `ROLE_ADMIN` | Không |
| `GET /api/tenant/{owner}` | Chặn | Chỉ đúng owner | Kiểm tra ownership **sau** authentication | Reactor Context / authorization nghiệp vụ |
| POST ghi dữ liệu nếu thêm về sau | Theo policy | Theo policy | Quyền và CSRF | Database |

Có ba tài khoản **lab**:

| Tài khoản | Authorities |
| --- | --- |
| `alice` | `ROLE_USER`, `SCOPE_reports:read` |
| `bob` | `ROLE_USER` |
| `admin` | `ROLE_ADMIN`, `SCOPE_reports:read` |

`hasRole("ADMIN")` mặc định yêu cầu authority **`ROLE_ADMIN`**, còn `hasAuthority("SCOPE_reports:read")` so khớp chính xác chuỗi scope đã ánh xạ. JWT/opaque token ngoài đời thường cần converter/mapping phù hợp; không giả định mọi token có `role=admin` đều tự động biến thành `ROLE_ADMIN`.

### 3.2. Ma trận yêu cầu tối thiểu

| ID | Method / route | Danh tính | Dependency | Kỳ vọng | Chứng minh |
| --- | --- | --- | --- | --- | --- |
| M01 | `GET /public` | anonymous | N/A | 200 | Public endpoint mở có chủ đích |
| M02 | `GET /api/me` | anonymous | N/A | 401 Basic | Chặn khi thiếu authentication |
| M03 | `GET /api/me` | alice | N/A | 200, body `alice` | Context gắn đúng người |
| M04 | `GET /api/me` | bob | N/A | 200, body `bob` | Không trả lại identity request trước |
| M05 | `GET /api/admin` | alice | N/A | 403 | Không biến `authenticated` thành ADMIN |
| M06 | `GET /api/admin` | admin | N/A | 200 | ADMIN hợp lệ |
| M07 | `GET /api/report` | bob | N/A | 403 | Thiếu scope; không gọi dependency |
| M08 | `GET /api/report` | alice | OK | 200, `report:ready` | Đủ scope và dependency thành công |
| M09 | `GET /api/report` | alice | lỗi runtime từ gateway | 503, không lộ nguyên nhân nhạy cảm | Không fail-open/đưa dữ liệu bừa |
| M10 | `GET /api/report` | alice | không phản hồi vượt timeout | 503 | Hạn chế thời gian chờ |
| M11 | `GET /api/report` | alice | `Mono.empty()` | 503 | Empty không bị hiểu thành thành công |
| M12 | `GET /api/tenant/alice` | alice | N/A | 200, owner `alice` | Chủ sở hữu được xem |
| M13 | `GET /api/tenant/bob` | alice | N/A | 403 | Không được đọc chéo tenant |
| M14 | `GET /api/tenant/alice` | bob | N/A | 403 | Không rò dữ liệu dù đổi request |
| M15 | Reactor publisher A và B | alice, bob đồng thời | scheduler đổi luồng | A=`alice`, B=`bob` | Security Context độc lập từng subscription |
| M16 | Reactor publisher mới | không context | N/A | `anonymous` | Không “nhớ” người dùng của publisher trước |

M01–M14 chạy qua HTTP/WebTestClient; M15–M16 dùng `StepVerifier`. Các kết quả trên là **hợp đồng của ứng dụng mẫu phía dưới**. Với OAuth2 Login người dùng chưa đăng nhập có thể thấy 302 đến IdP thay vì 401; với Spring Security Bearer Resource Server thường thấy 401 và header `WWW-Authenticate`. Không gán một status cố định cho mọi kiểu xác thực.

### 3.3. Vì sao kiểm tra âm tính quan trọng?

Test `ADMIN → 200` vẫn xanh khi lỡ đổi rule từ `hasRole("ADMIN")` sang `authenticated()`. Test `alice → 403` mới phát hiện được lỗ hổng. Tương tự, `report scope hợp lệ → 200` không đủ: cần `bob` thiếu scope → 403, một user chưa đăng nhập → 401 và dependency không được gọi trước khi vượt qua Security.

Một ma trận tốt nên gồm:

- **Positive controls:** principal/authority đúng và dependency khỏe.
- **Negative authorization:** anonymous, sai role/scope, sai owner, phương thức HTTP không được khai báo.
- **Negative protocol:** token hết hạn, chữ ký sai, `iss`/`aud` không hợp lệ, introspection `active=false`.
- **Fault injection:** upstream 5xx, ngắt kết nối, timeout, response sai schema, token/JWK issuer không truy cập được.
- **Isolation:** interleaving, scheduler switch, cache dùng chung, context không tồn tại, đồng thời nhiều request.

## 4. Xây ứng dụng WebFlux demo Java 17+ chạy được

### 4.1. Gradle dependencies

Với dự án Spring Boot 3.3.x có Gradle plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`spring-security-test` hỗ trợ `mockUser`, `mockJwt`, cấu hình test với Spring Security; các HTTP test bên dưới dùng **Basic Auth thật của app**, vì vậy thực sự đi qua `SecurityWebFilterChain`.

### 4.2. Ứng dụng và cấu hình Security

Tạo file `src/main/java/example/securitymatrix/SecurityMatrixApplication.java`:

```java
package example.securitymatrix;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityMatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityMatrixApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/report")
                            .hasAuthority("SCOPE_reports:read")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/tenant/**")
                            .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Dành riêng cho ví dụ học tập, tuyệt đối không đưa {noop}
    // và mật khẩu cố định này vào hệ thống triển khai thực tế.
    @Bean
    MapReactiveUserDetailsService labUsers() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}pass")
                .authorities("ROLE_USER", "SCOPE_reports:read")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password("{noop}pass")
                .authorities("ROLE_USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}pass")
                .authorities("ROLE_ADMIN", "SCOPE_reports:read")
                .build();
        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    // Seam thay thế được ở test để sinh lỗi/timeout mà không cần
    // khởi động database, IdP hoặc HTTP dependency thật.
    interface ReportGateway {
        Mono<String> loadReport();
    }

    @Bean
    ReportGateway reportGateway() {
        return () -> Mono.just("report:ready");
    }

    @RestController
    static class DemoApi {
        private final ReportGateway gateway;

        DemoApi(ReportGateway gateway) {
            this.gateway = gateway;
        }

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public:ok");
        }

        @GetMapping("/api/admin")
        Mono<String> adminEndpoint() {
            return Mono.just("admin:ok");
        }

        @GetMapping("/api/me")
        Mono<String> currentUser() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> ctx.getAuthentication().getName());
        }

        @GetMapping("/api/report")
        Mono<String> report() {
            return gateway.loadReport()
                    .timeout(Duration.ofMillis(250))
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("empty report")))
                    .onErrorMap(ex -> new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Report dependency unavailable"));
        }

        @GetMapping("/api/tenant/{owner}")
        Mono<String> tenantData(@PathVariable String owner) {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> ctx.getAuthentication().getName())
                    .flatMap(requester -> {
                        if (requester.equals(owner)) {
                            return Mono.just("owner:" + owner);
                        }
                        return Mono.error(new ResponseStatusException(
                                HttpStatus.FORBIDDEN,
                                "Tenant access denied"));
                    });
        }
    }
}
```

**Đọc code theo đường bảo mật:**

1. `authorizeExchange` khai báo route **cụ thể trước** `anyExchange().denyAll()`. Cấu hình trên có một chain mặc định match all nên không để rơi request ra ngoài Spring Security.
2. HTTP Basic dùng `MapReactiveUserDetailsService` để tạo `Authentication`/authorities của ba user lab. Không dùng mật khẩu cố định và `{noop}` ở production.
3. `/api/me` đọc `ReactiveSecurityContextHolder` **ngay trong publisher được subscribe cho request**, không truy cập `SecurityContextHolder` ThreadLocal của servlet.
4. `/api/report` chỉ tới handler sau khi Security xác nhận `SCOPE_reports:read`. `ReportGateway` là interface để test điều khiển sự cố. Nếu gateway lỗi/empty/quá 250 ms thì 503; exception gốc không được đưa vào reason response.
5. `/api/tenant/{owner}` minh họa kiểm tra ownership sau authentication; ở sản phẩm thật phải so khớp tenant ID/subject/ACL từ nguồn đáng tin, không dùng username từ URL làm chính sách tenant tổng quát.
6. Tất cả demo endpoints dùng GET để không trộn lỗi CSRF của POST vào bài chính. Không tắt CSRF toàn cục vì thiếu token; khi thêm thao tác ghi phải có ma trận CSRF riêng.

Cấu hình HTTP Basic phục vụ lab; nếu chuyển thành Resource Server Bearer JWT, cấu hình `.oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))`, khai báo issuer/audience/trust phù hợp, rồi test token thật. `mockJwt` hữu ích để thử quyền nhanh, nhưng không thực thi xác minh chữ ký ngoài đời.

## 5. WebTestClient biến ma trận thành regression tests

Tạo file `src/test/java/example/securitymatrix/SecurityMatrixApplicationTest.java`:

```java
package example.securitymatrix;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = SecurityMatrixApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityMatrixApplicationTest {

    @Autowired
    WebTestClient client;

    @MockBean
    SecurityMatrixApplication.ReportGateway gateway;

    @BeforeEach
    void healthyReportByDefault() {
        when(gateway.loadReport()).thenReturn(Mono.just("report:ready"));
    }

    @Test
    void publicRouteAndAnonymousProtection() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public:ok");

        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/report")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void eachAuthenticatedRequestGetsItsOwnIdentity() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");
    }

    @Test
    void adminRequiresAdminRoleEvenForValidUsers() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("admin", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:ok");
    }

    @Test
    void reportNeedsScopeAndThenReturnsGatewayData() {
        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report:ready");
    }

    @Test
    void tenantDataCannotBeReadAcrossUsers() {
        client.get().uri("/api/tenant/alice")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("owner:alice");

        client.get().uri("/api/tenant/bob")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/tenant/alice")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void dependencyExceptionDoesNotProduceDataOrLeakSecret() {
        when(gateway.loadReport()).thenReturn(Mono.error(
                new IllegalStateException("internal-db-secret")));

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .consumeWith(result -> {
                    byte[] response = result.getResponseBody();
                    String body = response == null
                            ? ""
                            : new String(response, StandardCharsets.UTF_8);
                    assertFalse(body.contains("internal-db-secret"));
                });
    }

    @Test
    void dependencyTimeoutAndEmptyMustNotBeSuccessful() {
        when(gateway.loadReport()).thenReturn(Mono.never());

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503);

        when(gateway.loadReport()).thenReturn(Mono.empty());

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503);
    }
}
```

Chạy từ project có Gradle wrapper:

```bash
./gradlew test --tests 'example.securitymatrix.SecurityMatrixApplicationTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests 'example.securitymatrix.SecurityMatrixApplicationTest'
```

**Kết quả kỳ vọng khi chạy đúng dự án mẫu:** bảy test được JUnit báo **PASS**. Không có stdout cố định từ app; các phép thử assert HTTP status và body chính xác. Mã trên là ví dụ hoàn chỉnh cho Spring Boot 3.3.x; annotation `@MockBean` thuộc Spring Boot 3.3, ở các đời Spring Boot mới hơn nó có thể bị deprecated/thay bằng `@MockitoBean` với dependency/test setup tương ứng.

`@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động HTTP server reactive thật trên port ngẫu nhiên; `WebTestClient` gọi request qua Security filters và handler. Việc `@MockBean` thay gateway trong test **không** bỏ qua Security; chỉ phụ thuộc nghiệp vụ được giả lập. Đó là điểm mạnh của integration test này.

**Vì sao một test vừa kiểm tra 503 vừa che exception?** Lỗi upstream có thể chứa hostname, JDBC URL, access token hoặc dữ liệu hạ tầng. API không được trả nguyên stacktrace/messages cho client. Việc log ở server cần redaction và correlation ID; test chống leakage kiểm tra body client, không đủ để chứng minh hệ thống logging an toàn.

## 6. Cô lập Reactive Security Context giữa các subscription

### 6.1. Reactor Context khác ThreadLocal

Trong WebFlux, security context đi qua **Reactor subscriber Context**. `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` dựa vào subscription hiện tại. Nếu pipeline được nối đúng bằng `flatMap`, `map`, `publishOn`, `delayElement`, `contextWrite`, context thường theo subscription khi đi qua các toán tử Reactor; **việc đổi thread trong Reactor không tự động làm mất context**.

Điều dễ sai:

- Dùng `SecurityContextHolder.getContext()` dựa vào `ThreadLocal` ở WebFlux và suy ra danh tính từ worker thread. Một thread có thể xử lý nhiều request khác nhau.
- Lưu `Authentication`/username vào `static`, `ThreadLocal`, singleton field hoặc một `Mono` được cache dùng chung mọi request.
- Tạo `Mono` đọc principal rồi gọi `subscribe()` thủ công ngoài chuỗi của request; subscription mới có thể không thừa hưởng request context.
- Qua `CompletableFuture`, callback SDK ngoài Reactor hoặc reactive bridge tự viết mà không truyền context đúng contract.
- Tạo `Mono.cache()` trên một publisher chứa dữ liệu theo người dùng rồi tái sử dụng cùng cached publisher trên nhiều request.

**Nguyên tắc:** dữ liệu theo user/tenant phải được tính từ context của **subscription hiện tại**, không đưa vào singleton cache chung theo đường dẫn. Nếu cache business data, khóa cache phải bao gồm danh tính/tenant/ACL version phù hợp và quyền phải được kiểm tra trước khi đọc dữ liệu.

### 6.2. Test `StepVerifier` độc lập chứng minh không lẫn context

Tạo file `src/test/java/example/securitymatrix/ReactiveSecurityContextIsolationTest.java`:

```java
package example.securitymatrix;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSecurityContextIsolationTest {

    private static Mono<String> currentIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .defaultIfEmpty("anonymous");
    }

    @Test
    void twoConcurrentSubscriptionsSeeDifferentIdentities() {
        var a = new UsernamePasswordAuthenticationToken(
                "alice", "unused", List.of());
        var b = new UsernamePasswordAuthenticationToken(
                "bob", "unused", List.of());

        Mono<String> alice = currentIdentity()
                .delayElement(Duration.ofMillis(20))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(a));

        Mono<String> bob = currentIdentity()
                .delayElement(Duration.ofMillis(10))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(b));

        StepVerifier.create(Mono.zip(alice, bob))
                .assertNext(pair -> {
                    assertEquals("alice", pair.getT1());
                    assertEquals("bob", pair.getT2());
                })
                .verifyComplete();

        // Subscription mới không chứa context phải độc lập.
        StepVerifier.create(currentIdentity())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test --tests 'example.securitymatrix.ReactiveSecurityContextIsolationTest'
```

**Kỳ vọng:** test PASS, `alice` và `bob` không đổi chỗ dù `delayElement` kích hoạt xử lý bất đồng bộ. Test này chứng minh **Reactor Context được gắn riêng ở mỗi subscription** và được đọc đúng bằng `ReactiveSecurityContextHolder`. Nó **không** một mình chứng minh app HTTP/filters hay cache của ứng dụng không rò dữ liệu; vì vậy phải chạy thêm HTTP tests ở mục 5, rồi thêm concurrency test ở ứng dụng thật khi có shared caches hoặc async bridges.

### 6.3. Anti-pattern: cache Mono chứa danh tính của request

**Sai (đoạn minh họa không phải class độc lập):**

```java
// Singleton service dùng chung mọi request:
private final Mono<String> cachedIdentity =
        ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .cache();
```

`cache()` ghi nhớ signal của lần subscribe đầu tiên. Nếu lần đầu chứa `alice`, lần subscribe của `bob` có thể nhận kết quả đã cache là `alice`. Điều này khác việc **mỗi request tạo một Mono mới**; lỗi xuất hiện vì cached publisher chung chứa dữ liệu nhạy cảm theo request.

**Đúng:**

```java
Mono<String> currentIdentity() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
}
```

Nếu có cache kết quả truy vấn, hãy dùng một khóa và lifecycle được thiết kế cho dữ liệu đa tenant, đồng thời kiểm tra lại quyền trước khi trả; không cache nguyên `Authentication` như một singleton cho toàn ứng dụng.

### 6.4. Cơ chế cô lập cần quan sát thêm

Trong hệ thống đa người dùng, test thêm:

| Tình huống | Test kích hoạt | Điều tuyệt đối không xảy ra |
| --- | --- | --- |
| `publishOn(Schedulers.parallel())` | Hai Mono danh tính gắn context khác nhau | Trả chung username do dùng ThreadLocal |
| Nhiều request HTTP đồng thời | A, B gọi cùng route, response bất đồng bộ | A nhận nội dung tenant B hoặc ngược lại |
| Gateway chậm | A timeout trong lúc B thành công | Dữ liệu response B bị hoàn thành vào A |
| Subscriber mới không auth | Subscribe `Mono` bảo mật không có context | Tái dùng context của A |
| Cache dùng chung | A điền cache, B đọc cùng khóa quá rộng | B nhận dữ liệu của A |
| Tự gọi `.subscribe()` | Tạo pipeline tách khỏi web exchange | Logic dựa vào context “trống” rồi tự cho quyền |
| Context bị lỗi | `.onErrorResume` sau lookup danh tính | Không tự chuyển thành principal admin/tenant khác |

Không dùng `contextWrite` gắn một principal cố định trong production để “khắc phục context bị mất”; đó là bypass authentication. Khi cần bridge sang API không reactive, dùng công cụ propagation được framework hỗ trợ hoặc truyền một request-scoped identity immutable một cách tường minh; kiểm thử không lẫn dữ liệu khi chạy song song.

## 7. Ma trận lỗi dịch vụ phụ thuộc

### 7.1. Business dependency: R2DBC, WebClient, Redis

| Failure mode | Cách giả lập trong unit/integration test | Kỳ vọng |
| --- | --- | --- |
| Thành công | `Mono.just("report:ready")` | 200 đúng payload, đúng owner |
| Trả rỗng | `Mono.empty()` | 404/503 tùy contract; ví dụ này là 503 |
| Runtime exception | `Mono.error(new IllegalStateException(...))` | Không trả data, HTTP 503 đã chuẩn hóa |
| Timeout | `Mono.never()` với `.timeout(...)` | Kết thúc trong budget hữu hạn, HTTP 503 |
| HTTP 429/503 từ downstream | HTTP mock server trả status tương ứng | Không dữ liệu nhạy cảm, retry/backoff theo policy |
| Kết nối reset / DNS lỗi | Stub đóng kết nối / sai DNS có kiểm soát | Lỗi được phân loại, không dùng fallback mở quyền |
| Response malformed | Body sai schema hoặc type | Không coi JSON lỗi là kết quả hợp lệ |
| Data của tenant khác | Gateway cố ý trả record có owner khác | Authorization ở service chặn, không phát record |
| Cache cũ khi quyền đã bị thu hồi | Cache cố định identity / stale ACL | Không dùng dữ liệu cũ làm quyết định cho phép |

**Lưu ý:** cache nghiệp vụ không đồng nghĩa cache quyết định quyền. Một dependency lỗi có thể cho phép “read-only degraded mode” với **dữ liệu công khai** nếu hợp đồng cho phép; nhưng quyền truy cập tài nguyên nhạy cảm vẫn phải kiểm tra, không `onErrorReturn(true)` khi PDP/tenant ownership bị lỗi.

Khi mô phỏng timeout, độ trễ của **stub** phải lớn hơn timeout của client/operation. Test không nên dựa vào default timeout dài của JVM hoặc network. Với `WebTestClient` thực tế, dùng `.timeout(Duration.ofMillis(...))` theo yêu cầu; test ở mục 5 đặt 250ms để dễ kiểm chứng. Với logic thuần Reactor có thể dùng virtual time (`StepVerifier.withVirtualTime`) nhưng scheduler thời gian thực của server HTTP không tự chuyển sang virtual time chỉ vì test gọi `withVirtualTime`.

### 7.2. Authentication dependency: IdP/JWK/introspection

Trong Resource Server OAuth2, kiểm thử các trường hợp sau **tách riêng** khỏi demo HTTP Basic:

| Tình huống | Cách thiết lập | Kỳ vọng ở tầng xác thực |
| --- | --- | --- |
| JWT hợp lệ, JWK hợp lệ | JWT ký bằng private key fixture; stub trả JWKS public key | Xác thực thành công rồi mới xét quyền |
| JWT hết hạn / `nbf` chưa đến | Token claim thời gian sai | Từ chối; không có auth hợp lệ |
| Chữ ký sai / `kid` không khớp | Ký bởi key khác / header sai | Từ chối; không tin chữ ký |
| `iss` / `aud` sai | JWT có claim không khớp validator | Từ chối khi validator được cấu hình |
| JWKS 503 khi cần khóa mới | Stub IdP trả 503 | Không chấp nhận token không xác minh được |
| JWKS 503 nhưng key hợp lệ đã cache | Decoder đang có trusted key | JWT có thể vẫn được xác minh; **không** ép test cho rằng mọi request cần gọi IdP |
| Introspection 200 `active=true` | HTTP POST token, Basic client auth; JSON hợp lệ | Principal/authorities đúng |
| Introspection 200 `active=false` | IdP xác định token vô hiệu | Từ chối |
| Introspection 500/503/429 | Mock HTTP server phản hồi lỗi | Không sinh authenticated principal |
| Introspection timeout/connection reset | Stub lỗi network | Không fail-open |
| Client secret sai | Endpoint trả 401/403 | Không coi token “active”, ghi nhận sự cố cấu hình |

**Khác biệt cơ bản:** JWT có thể được xác minh **cục bộ** khi đã có public JWK cache; opaque token thường cần gọi remote introspection mỗi lần nếu ứng dụng chưa cài caching riêng. Do đó số HTTP requests đến IdP không cố định giữa các cơ chế. Tác động lỗi upstream lên **status API** còn tùy exception translation; test HTTP ở ứng dụng thật để chốt hợp đồng 401/5xx thay vì đoán.

`mockJwt()` và `mockOpaqueToken()` tạo authenticated principal giả trong WebTestClient test, không thực thi HTTP JWKS/introspection hay cryptographic signature. Dùng chúng để kiểm quyền; dùng **JWT ký thật + `NimbusReactiveJwtDecoder` thật + JWK mock server** hoặc **`SpringReactiveOpaqueTokenIntrospector` thật + HTTP mock server** khi cần kiểm dependency lỗi.

### 7.3. Một test contract cho introspection 503

Test sau dùng `MockWebServer` và chính `SpringReactiveOpaqueTokenIntrospector` (Spring Security 6.5). Thêm `spring-boot-starter-oauth2-resource-server` vào dependency project cho test này và `mockwebserver` như mục 4.1.

Tạo file `src/test/java/example/securitymatrix/IntrospectionFailureContractTest.java`:

```java
package example.securitymatrix;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class IntrospectionFailureContractTest {

    @Test
    void idp503NeverProducesAnAuthenticatedPrincipal()
            throws IOException, InterruptedException {

        try (MockWebServer idp = new MockWebServer()) {
            idp.start();
            idp.enqueue(new MockResponse()
                    .setResponseCode(503)
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"error\":\"temporarily_unavailable\"}"));

            var introspector = SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(idp.url("/introspect").toString())
                    .clientId("lab-client")
                    .clientSecret("lab-secret")
                    .build();

            StepVerifier.create(introspector.introspect("opaque-lab-token"))
                    .expectError()
                    .verify();

            RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("POST", request.getMethod());
            assertEquals("/introspect", request.getPath());
        }
    }
}
```

Vì `MockWebServer` khởi tạo trên loopback và port động, test không dùng IdP thật và không lưu credentials production. Kết quả dự kiến: introspection `503` gây `onError`, không có principal; test **PASS**. Muốn kiểm đầy đủ, bổ sung test `active=false`, `active=true`, Basic header/form `token` và `WebTestClient` end-to-end với cấu hình `.opaqueToken(...)`. Không tự suy ra rằng một contract test component đã kiểm hết SecurityWebFilterChain.

**Cẩn thận version:** nếu dependency project đang dùng Spring Security API khác 6.5, đối chiếu builder của introspector và JDK trước khi copy. Các bước còn lại của bài dùng Spring Boot 3.3.x; phiên bản 6.5 thuộc nhánh Security 6.x, không nhất thiết là phiên bản do BOM Boot 3.3 tự quản lý. Khi dùng cả code mẫu, giữ dependency versions nhất quán; không cưỡng bức nâng một phần security modules độc lập.

## 8. Phân biệt fail closed và trả status đúng

**Fail closed** nghĩa là khi không thể xác thực hoặc đánh giá quyền, không cung cấp dữ liệu đặc quyền. Nó **không** có nghĩa mọi lỗi dependency phải trả 403:

| Nguồn lỗi | Ý nghĩa | Cách xử lý thường phù hợp |
| --- | --- | --- |
| Không có credential | Chưa xác thực | 401 cho HTTP Basic/Bearer; OAuth2 Login có thể redirect |
| Credential sai/hết hạn | Không xác thực được | 401 Bearer/Basic theo entry point |
| Principal hợp lệ nhưng thiếu scope | Không có quyền | 403 |
| Tenant ownership đã kiểm và sai | Không có quyền sở hữu | 403, hoặc 404 nếu policy cố ý che sự tồn tại |
| PDP không trả verdict vì 503 | **Chưa thể** xác định có quyền | Không cho truy cập; 503/5xx hoặc status policy quy định |
| Introspection không thể kết nối | Không thể xác minh opaque token | Không cho truy cập; status tùy adapter/handler |
| Gateway báo cáo lỗi sau auth | Có quyền, nhưng nghiệp vụ không chạy | 503/504/5xx, không lộ data hoặc secret |
| JWKS key đã cache và chữ ký/claims hợp lệ | Có thể xác minh JWT mà không gọi remote | Tiếp tục auth theo chính sách cache được duyệt |

Cố ý viết một `onErrorReturn(true)` vào authorization predicate hoặc `onErrorResume(e -> Mono.just(Authentication.admin))` là lỗi **fail-open** nghiêm trọng. Đừng tạo fallback lấy tenant default; không tự động dùng principal trước đó, cache kết quả quyền của user khác hoặc cho phép truy cập khi R2DBC truy vấn quyền bị timeout.

Lỗi trả 401 từ **introspection endpoint của IdP** không đồng nghĩa với HTTP 401 trả cho **người gọi API**: hai hop có thể ánh xạ ngoại lệ khác nhau. Bảo đảm test mỗi tầng (decoder/introspector và HTTP filter) riêng biệt.

## 9. Kế hoạch fault injection có kiểm soát

Một suite tốt chạy theo thứ tự logic, không cần nhiều dịch vụ thật:

```text
Unit / StepVerifier
   -> Reactor Context per subscription; timeout/retry/mapError
   -> validate principal + tenant/owner check

Security integration / WebTestClient
   -> anonymous/role/scope/owner
   -> dependency mock: OK / error / empty / never
   -> HTTP status, body, no data leakage

Adapter contract / HTTP stub
   -> JWKS, introspection, WebClient dependency protocol
   -> 200/401/403/429/503/malformed/slow/TLS errors

End-to-end staging
   -> real proxy, IdP, TLS, R2DBC/Redis where applicable
   -> access controls and correlation across components
```

### 9.1. Các bất biến cần đo

- **Authorization first:** request thiếu quyền không gọi report gateway. Kiểm tra `Mockito.verify(gateway, never()).loadReport()` trong một test **chỉ** gửi request thiếu quyền; không dùng chung fixture làm phép đo khi test khác đã gọi gateway.
- **Không trả fallback nhạy cảm:** các response lỗi không chứa record, bearer token, password, connection string hay stacktrace.
- **Timeout hữu hạn:** một dependency `Mono.never()` không giữ request vô hạn; test có budget.
- **Isolation:** user A không nhận `sub`, `tenantId` hoặc payload của user B.
- **Đúng tầng:** lỗi token phải bị chặn trước handler; lỗi nghiệp vụ xảy ra sau khi auth thành công; logs thể hiện loại lỗi khác nhau.
- **Retry đúng giới hạn:** không retry token introspection/POST vô điều kiện; nếu retry idempotent read dependency, giới hạn lần và thời gian. Một retry có thể nhân số request; test số lần theo chính sách thực, không mặc định bằng một.
- **Cache đúng scope:** cache authorization không dùng chung user/tenant; policy revoke và TTL cần test.
- **Không chặn event loop:** không gọi `.block()` hoặc blocking JDBC trong reactive handler; nếu bắt buộc bridge blocking, cô lập scheduler và vẫn phải bảo toàn context/traces đúng cách.

### 9.2. Một negative test cực quan trọng

Với `/api/admin`, chỉ test `admin → 200` **không đủ**: nếu developer thay `.hasRole("ADMIN")` bằng `.authenticated()`, test vẫn xanh. Thêm `alice → 403` phát hiện lỗi. Với `/api/report`, test `bob → 403` ngăn quyền scope bị nới. Với tenant, luôn kiểm tra **owner A đọc tenant B → bị chặn**.

### 9.3. Đặt test data cố định nhưng không dùng data thật

Dùng test usernames/tenant IDs ổn định, token ký bằng fixture key riêng, endpoint giả trên port ngẫu nhiên, clock cố định khi kiểm tra `exp`/`nbf`. Tạo cleanup cho mock HTTP server, database container, session và caches theo từng test. Không chạy test phụ thuộc IdP internet làm điều kiện bắt buộc cho unit suite.

## 10. Kiểm tra rò rỉ context dưới tải đồng thời

Một test `Mono.zip` chứng minh cơ chế Reactor Context cơ bản, nhưng chưa phát hiện mọi lỗi **shared state của ứng dụng**. Khi ứng dụng có cache/static fields/custom WebFilter, bổ sung kiểm thử HTTP đồng thời:

1. Khởi động ứng dụng bằng `RANDOM_PORT`, dùng hai principal có quyền và tenant khác nhau.
2. Gửi nhiều request A/B đồng thời qua `WebTestClient` hoặc async HTTP client; mỗi request có credential riêng và correlation ID riêng. Không dùng global default Authorization header thay đổi giữa các thread.
3. Trong service giả lập, delay khác nhau giữa A và B (`Mono.delay`), có thể chuyển scheduler bằng `publishOn` và cố ý interleave.
4. Assert từng response chứa **đúng** user/tenant/record tương ứng; không lấy `lastLoggedInUser` hay `currentTenant` từ singleton fields.
5. Lặp lại với một request timeout, một request thành công và một request bị 403. Request bị từ chối không được chạm resource của người khác.
6. Kiểm tra log/traces có correlation ID riêng, nhưng không in credentials. Test phải đủ lặp lại để tìm race mà vẫn có thời gian chạy hữu hạn.

**Sai lầm tinh vi:** gán `currentUser` vào field của `@Service` singleton. Hai request interleave có thể ghi đè field trước khi Mono sử dụng nó. Giải pháp là giữ identity trong Reactor Context hoặc tham số immutable của mỗi pipeline, và đưa dữ liệu cần dùng vào lambda theo subscription, không dùng singleton mutable state.

### Ví dụ sai và đúng với `flatMap`

**Sai – pseudocode logic, không chạy độc lập:**

```java
// Field dùng chung của singleton:
private String currentTenant;

Mono<String> load(String tenant) {
    currentTenant = tenant;
    return gateway.loadFor(currentTenant);
}
```

Nếu `gateway.loadFor(...)` đọc/đánh giá giá trị vào thời điểm khác hoặc có callback dùng field, request B có thể thay field của A. Code trên cũng không tự kiểm tra tenant có thuộc principal hiện tại hay không.

**Đúng – giữ tenant thành biến local và kiểm quyền trong pipeline:**

```java
Mono<String> loadAuthorized(String requestedTenant) {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(requester -> {
                if (!requester.equals(requestedTenant)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.FORBIDDEN, "Tenant access denied"));
                }
                return gateway.loadFor(requestedTenant);
            });
}
```

Đoạn đúng là **mảnh code minh họa** cho service có `gateway.loadFor(...)` và imports tương ứng, chưa phải class chạy độc lập. Sản phẩm thật kiểm tra membership/ownership bằng ID và policy đáng tin cậy; so tên trong demo chỉ để thấy pipeline không chia sẻ field.

## 11. Các lỗi thường gặp khi tổng hợp ma trận

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ test status 200 của user admin | Không phát hiện rule bị nới quyền | Thêm test user thường → 403 và anonymous → 401 |
| Dùng `mockJwt()` rồi tuyên bố đã kiểm JWK | Bỏ qua chữ ký và HTTP JWKS | Test thêm decoder thật với JWT ký fixture và IdP stub |
| Test opaque token chỉ `200` | `active=false` cũng có HTTP 200 | Assert introspector phát lỗi khi `active=false` |
| Coi 503 từ IdP là token invalid | Trộn lỗi hạ tầng và kết luận xác thực | Tách lỗi và log; vẫn không cấp quyền |
| Dùng `.onErrorReturn(true)` trong policy | Fail-open | Trả lỗi/deny, không tự công nhận quyền |
| Cache principal dưới singleton | User B đọc principal của A | Đọc Reactor Context mỗi subscription, cache theo scope |
| Dùng `SecurityContextHolder` ThreadLocal trên reactive flow | Thấy null/sai principal trên event loop | Dùng `ReactiveSecurityContextHolder` |
| Gọi `.subscribe()` trong service | Detached subscription có thể mất request context | Compose publisher và để WebFlux subscribe |
| Dùng `Thread.sleep` trong reactive handler | Chặn event loop và tăng timeout giả | Dùng `Mono.delay`, async I/O, boundedElastic khi bắt buộc bridge blocking |
| Tắt CSRF vì POST test nhận 403 | Có thể mở lỗ hổng browser session | Test CSRF riêng, cấu hình theo kiến trúc |
| Chỉ assert status, không assert body | Có thể rò secret/dữ liệu tenant dù status lỗi | Assert body và response headers nhạy cảm |
| Test phụ thuộc IdP hoặc DB production | Không ổn định, nguy cơ lộ thông tin | Mock server/test DB/certificate fixture |
| Mock gateway và bỏ qua chain security | Test nghiệp vụ không chứng minh 401/403 | `@SpringBootTest` + `WebTestClient` đi qua filters |
| Không test timeout | Request treo vô hạn khi dependency không trả lời | Timeout + fault injection `Mono.never()` |
| Thấy 403 rồi đổ lỗi role | CSRF hoặc method security có thể tạo 403 | Phân loại tầng lỗi và method/route trước |

## 12. Bộ chỉ số, tài liệu QA và CI

Một báo cáo test cần ghi:

```text
Scenario: M09
Route: GET /api/report
Identity fixture: alice
Authorities: ROLE_USER, SCOPE_reports:read
Injected dependency state: Mono.error(IllegalStateException)
Expected HTTP status: 503
Expected sensitive body exposure: none
Observed status: [test reports result]
Outcome: PASS / FAIL
```

Mọi scenario phải có ID cố định, route/method, role/scope, dependency state, expected HTTP response, quan sát thực tế và assertion; không chỉ một dòng “security tests pass”. Với CI, tách suite nhanh (authorization, Reactor Context) và suite HTTP contract (IdP stub, integration), chỉ chạy staging E2E khi môi trường ổn định.

Thêm một **sentinel negative test** khi sửa policy mới: cố ý làm rule admin bớt chặt trên một nhánh test và xác nhận test `alice → 403` fail; đó là cách biết test thực sự bắt regression. Giới hạn fault injection ở môi trường test/staging. Không công bố token, password, private signing key, secret/host nội bộ trong report hoặc logs. Với `MockWebServer` có thể assert header Basic bằng giá trị fixture, nhưng không in header ra stdout.

### Checklist để đánh giá hoàn thành bài thực hành

- [ ] Có bảng route × identity × scope/role × dependency state × expected status/body.
- [ ] Có ít nhất ba class test: WebTestClient authorization/dependency, Reactor Context isolation và adapter contract IdP (hoặc lớp tương đương).
- [ ] Anonymous, user thiếu quyền và user đúng quyền đều có test trên tài nguyên nhạy cảm.
- [ ] `GET /api/me` trả đúng identity cho hai user; hai subscriber đồng thời không lẫn context.
- [ ] Có tenant-crossing negative test và chống cache/field toàn cục mang dữ liệu user.
- [ ] Có dependency success, exception, empty, timeout; timeout hữu hạn và lỗi không trả dữ liệu nhạy cảm.
- [ ] JWT/opaque test phân biệt auth mock với kiểm chứng chữ ký/remote introspection thật.
- [ ] Không dùng fallback cho phép quyền khi IdP/PDP/R2DBC lỗi.
- [ ] Mỗi test có kết quả có thể tái hiện và nằm trong CI phù hợp.
- [ ] Kiểm tra các status 401/403/503 theo đúng loại authentication; không suy diễn chung cho mọi kiến trúc.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — WebFlux Security configuration và nhiều chain](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html).
- [Spring Security 6.5 — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html).
- [Spring Security 6.5 — Reactive Web Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html).
- [Spring Security 6.5 — OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html).
- [Spring Security 6.5 — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Framework — Testing WebFlux với WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).

**Kết quả học tập đạt yêu cầu** khi bạn có thể chỉ ra bằng test: *ai được xem tài nguyên nào*, *dependency lỗi thì API xử lý ra sao*, và *hai request reactive không thể vô tình dùng principal/tenant/data của nhau*.