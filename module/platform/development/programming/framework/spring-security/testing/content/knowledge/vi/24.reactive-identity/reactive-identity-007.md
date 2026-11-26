# Phân quyền Reactive theo path, HTTP method và chủ sở hữu tài nguyên

Một request đã xác thực chưa chắc được phép truy cập mọi dữ liệu. Trong API quản lý tài liệu, Alice có thể đọc tài liệu của mình nhưng phải bị từ chối khi đọc tài liệu của Bob. Việc cập nhật còn có thể yêu cầu vai trò biên tập. Để kiểm thử đúng chính sách này, cần kết hợp **path**, **HTTP method**, **authorities** và **thông tin chủ sở hữu lấy từ nguồn dữ liệu đáng tin cậy**.

Bài thuộc chương **Danh tính Reactive** của module **SPRING_SECURITY_TESTING**. Người học sẽ kiểm tra bảo vệ HTTP thực tế bằng `spring-security-test` và `WebTestClient` trên Spring WebFlux, đồng thời phân biệt kiểm thử danh tính giả lập bằng `mockUser()`, `@WithMockUser`, `mockJwt()` với kiểm thử xác thực HTTP Basic hoặc Bearer thật. Bài cũng phân biệt quy tắc HTTP method ở `SecurityWebFilterChain` với method security Java bằng `@PreAuthorize`.

## 1. Xây dựng chính sách phân quyền trước khi viết test

Giả sử API có hai tài liệu được quản lý trên server:

| Tài liệu | Chủ sở hữu | Đường dẫn |
| --- | --- | --- |
| `doc-1` | `alice` | `/api/documents/doc-1` |
| `doc-2` | `bob` | `/api/documents/doc-2` |

Chính sách:

1. `GET /api/documents/{id}`: principal đã xác thực **và** là chủ sở hữu.
2. `PUT /api/documents/{id}`: principal đã xác thực, có `ROLE_EDITOR` **và** là chủ sở hữu.
3. `GET /api/health`: công khai.
4. Các request khác: mặc định từ chối.

Ma trận kỳ vọng ban đầu:

| Yêu cầu | Danh tính / quyền | Kỳ vọng |
| --- | --- | --- |
| GET doc-1 | Alice, USER | `200` |
| GET doc-1 | Bob, USER | `403` |
| GET doc-1 | Không đăng nhập | Thường `401` |
| PUT doc-1 | Alice, USER + EDITOR | `200` |
| PUT doc-1 | Alice, USER | `403` |
| PUT doc-1 | Bob, EDITOR | `403` |
| DELETE doc-1 | Alice, EDITOR | Bị từ chối vì chưa có rule cho DELETE |
| GET health | Anonymous | `200` |

`401 Unauthorized` thường cho biết request chưa được xác thực; `403 Forbidden` thường xảy ra khi principal đã xác thực nhưng thiếu quyền. Kết quả cuối còn tùy `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` của ứng dụng. Ví dụ phía dưới bật HTTP Basic và tắt form login để phản hồi API dễ đối chiếu.

Điều kiện role và ownership giải quyết hai vấn đề khác nhau. `ROLE_EDITOR` cho phép một nhóm thao tác, còn việc tài liệu có `ownerId = alice` cho biết thao tác được phép **trên bản ghi nào**. Không được dùng trường `ownerId` do client tự gửi trong body làm nguồn xác định quyền sở hữu.

## 2. Authentication trong Reactor Context

Spring Security Reactive đặt `SecurityContext` vào **Reactor Context**. Một reactive chain có thể chuyển thread và tiếp tục trên scheduler khác, nên không thể dựa vào một `ThreadLocal` tự chế để lấy danh tính. Có thể đọc authentication hiện tại bằng:

~~~java
Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

`ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`. Trong luồng không có security context, publisher có thể hoàn thành rỗng. Một service thực tế phải xử lý trường hợp không có principal; không nên chuyển mặc định thành một user có quyền.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityWebFilterChain"]
    B --> C{"Matcher path + HTTP method"}
    C -->|GET/PUT tài liệu| D["Authentication từ Reactive Context"]
    C -->|Health| E["permitAll"]
    C -->|Chưa có rule| X["denyAll"]
    D --> F{"Đã xác thực và đủ authority?"}
    F -->|Không| Y["401 hoặc 403"]
    F -->|Có| G["Reactive ownership lookup theo documentId"]
    G --> H{"Principal đúng chủ sở hữu?"}
    H -->|Không| Z["403: không phải owner"]
    H -->|Có| I["Controller và service xử lý"]
~~~

Sơ đồ mô tả logic ví dụ; trên hệ thống thật, security filter có thể áp dụng thêm CSRF, CORS, exception translation và cơ chế authentication khác trước khi gọi controller. Cần kiểm tra riêng các filter có thể ảnh hưởng kết quả.

## 3. Cấu hình SecurityWebFilterChain theo đường dẫn và HTTP method

Với Spring Boot WebFlux, dependency điển hình là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Ví dụ dùng HTTP Basic và user in-memory để tập trung vào cơ chế phân quyền. `{noop}` chỉ dành cho demo/test, không dùng để lưu mật khẩu production.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ReactiveDocumentSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, DocumentOwnership ownership) {

        var readOwn = new DocumentOwnerAuthorizationManager(ownership, null);
        var updateOwn = new DocumentOwnerAuthorizationManager(
            ownership, "ROLE_EDITOR");

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/documents/{id}")
                    .access(readOwn)
                .pathMatchers(HttpMethod.PUT, "/api/documents/{id}")
                    .access(updateOwn)
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}secret")
            .roles("USER", "EDITOR")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}secret")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }
}
~~~

`pathMatchers(HttpMethod.GET, ...)` và `pathMatchers(HttpMethod.PUT, ...)` có thể đưa cùng một URL tới **hai quyết định phân quyền khác nhau**. Đừng đặt matcher rộng `/api/documents/**` với `authenticated()` trước hai rule này; rule đầu tiên khớp có thể kết thúc việc lựa chọn, khiến kiểm tra owner bị bỏ qua. Quy tắc `anyExchange().denyAll()` giúp chặn đường dẫn/method chưa xét tới.

Trong ví dụ, CSRF vẫn bật theo cấu hình mặc định. Khi test PUT/DELETE, cần gửi token CSRF hợp lệ để lỗi `403` do CSRF không che kết quả phân quyền owner. Nếu API production được thiết kế stateless chỉ nhận Bearer token và tắt CSRF có chủ đích, hãy phản ánh đúng cấu hình đó trong bài test.

## 4. Tra quyền sở hữu theo dữ liệu Reactive

Định nghĩa contract với kho tài liệu:

~~~java
import reactor.core.publisher.Mono;

interface DocumentOwnership {
    Mono<Boolean> isOwner(String documentId, String principalName);
}
~~~

Để ví dụ độc lập với database, ta dùng bảng owner cố định:

~~~java
import java.util.Map;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class InMemoryDocumentOwnership implements DocumentOwnership {
    private final Map<String, String> owners = Map.of(
        "doc-1", "alice",
        "doc-2", "bob");

    @Override
    public Mono<Boolean> isOwner(
            String documentId, String principalName) {
        return Mono.just(principalName.equals(owners.get(documentId)));
    }
}
~~~

Trong hệ thống thật, query phải lấy owner từ database đáng tin cậy, ví dụ Reactive MongoDB hoặc R2DBC. Không dùng một HTTP header tùy ý `X-Owner` hoặc payload request làm bằng chứng chủ sở hữu. Việc dùng `Mono<Boolean>` cho phép ghép truy vấn vào đường xử lý authorization không chặn luồng.

Một `ReactiveAuthorizationManager<AuthorizationContext>` nhận reactive authentication và biến path `id` từ matcher:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

final class DocumentOwnerAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final DocumentOwnership ownership;
    private final String requiredAuthority;

    DocumentOwnerAuthorizationManager(
            DocumentOwnership ownership, String requiredAuthority) {
        this.ownership = ownership;
        this.requiredAuthority = requiredAuthority;
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object rawId = context.getVariables().get("id");
        if (!(rawId instanceof String id) || id.isBlank()) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .filter(auth -> auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken))
            .filter(this::hasAuthority)
            .flatMap(auth -> ownership.isOwner(id, auth.getName()))
            .map(allowed -> (AuthorizationResult)
                new AuthorizationDecision(allowed))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private boolean hasAuthority(Authentication auth) {
        if (requiredAuthority == null) {
            return true;
        }
        return auth.getAuthorities().stream()
            .anyMatch(a -> requiredAuthority.equals(a.getAuthority()));
    }
}
~~~

`AuthorizationContext.getVariables()` lấy biến `id` từ path matcher có khai báo `{id}`; map này chứa các giá trị kiểu `Object` nên cần xác minh kiểu trước khi dùng. Nếu matcher không tạo ra biến này, manager từ chối mặc định. Nếu `ownership.isOwner(...)` trả `Mono.empty()`, `defaultIfEmpty(false)` cũng từ chối. Nếu database trả lỗi, không được biến lỗi ấy thành `true`: exception sẽ phải được xử lý theo chính sách an toàn của ứng dụng. Ví dụ sử dụng API `authorize(...)` của Spring Security **6.4 trở lên**, gồm dòng 7.x; ở một số bản 6.x cũ hơn, `ReactiveAuthorizationManager` chỉ cung cấp `check(...)` với `Mono<AuthorizationDecision>`.

Lưu ý `AnonymousAuthenticationToken` có thể báo `isAuthenticated() == true` về mặt kỹ thuật; vì vậy không được chỉ dựa vào một phép gọi `isAuthenticated()` để nhận diện người dùng thật. Trong ví dụ có kiểm tra thêm kiểu anonymous token.

Một owner check thuần `hasRole("EDITOR")` sẽ cho phép Bob sửa tài liệu của Alice nếu Bob cũng là editor. Một owner check thuần không kiểm tra role sẽ cho phép Alice sửa dữ liệu dù chỉ được đọc. Manager trên hợp nhất hai điều kiện cho `PUT` và chỉ áp dụng ownership với `GET`.

### Ranh giới quyền theo tenant

Khi ứng dụng có multi-tenancy, so sánh chuỗi `username` có thể không đủ. Hai tenant khác nhau có thể cùng tên Alice; nên xét đồng thời **tenant ID**, **immutable principal ID** và **document ID** do server quản lý. Các giá trị `tenantId` hoặc `ownerId` do client gửi chỉ được coi là input định vị sau khi được xác thực, không thể tự cấp quyền truy cập.

## 5. Controller và phân quyền trên phương thức Java

Controller ví dụ giữ logic xử lý đơn giản; quyền truy cập HTTP đã được giới hạn ở `SecurityWebFilterChain`. Với thao tác ghi, controller gọi một service Spring riêng:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class DocumentController {
    private final DocumentWriteService writeService;

    DocumentController(DocumentWriteService writeService) {
        this.writeService = writeService;
    }

    @GetMapping("/health")
    Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/documents/{id}")
    Mono<Map<String, String>> read(@PathVariable String id) {
        return Mono.just(Map.of("id", id, "action", "read"));
    }

    @PutMapping("/documents/{id}")
    Mono<Map<String, String>> update(@PathVariable String id) {
        return writeService.update(id)
            .map(result -> Map.of("id", id, "result", result));
    }
}
~~~

Method security được kích hoạt bởi `@EnableReactiveMethodSecurity` trong cấu hình mục 3:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class DocumentWriteService {
    @PreAuthorize("hasRole('EDITOR')")
    public Mono<String> update(String documentId) {
        return Mono.just("updated:" + documentId);
    }
}
~~~

| Thành phần | Điều kiện được kiểm tra |
| --- | --- |
| HTTP GET + path matcher | Authentication và ownership của tài liệu |
| HTTP PUT + path matcher | Authentication, `ROLE_EDITOR` và ownership |
| `@PreAuthorize` trên Java method | `ROLE_EDITOR` tại thời điểm gọi service qua Spring proxy |

**HTTP method** như GET/PUT là thuộc tính request, còn **Java method security** áp dụng trên lời gọi bean. Một lời gọi từ service khác có thể bỏ qua HTTP matcher, nên không được cho rằng `@PreAuthorize("hasRole('EDITOR')")` đủ để bảo vệ ownership. Nếu service có nhiều entry point, hãy kiểm tra owner ngay tại service hoặc câu lệnh cập nhật database.

Chỉ phương thức được gọi qua bean/proxy có gắn security interceptor mới được kiểm tra annotation. Ví dụ `new DocumentWriteService()` hoặc lời gọi nội bộ trong cùng object có thể bỏ qua kiểm tra từ proxy. `Mono`/`Flux` cũng cần giữ đúng Reactor Context trong lúc subscription để method security đọc được authentication.

Một đoạn kiểm tra owner trong service có thể viết theo hướng reactive:

~~~java
Mono<String> checkOwned(
        String documentId, Authentication authentication,
        DocumentOwnership ownership) {
    return ownership.isOwner(documentId, authentication.getName())
        .flatMap(allowed -> allowed
            ? Mono.just("allowed:" + documentId)
            : Mono.error(new AccessDeniedException("Not document owner")));
}
~~~

Đoạn này minh họa quyết định quyền, chưa thực hiện ghi thật. Khi ghi database, cân nhắc điều kiện update cùng owner hoặc transaction phù hợp để tránh ownership bị đổi sau bước kiểm tra nhưng trước bước ghi.

## 6. WebTestClient: các ca được phép và bị từ chối

Với `WebTestClient` có Spring Security test support, `mockUser()` thiết lập authentication giả lập trong request test. Ví dụ sau sử dụng ứng dụng WebFlux đã có các bean mục 3–5:

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
class DocumentAuthorizationWebTestClientTest {

    @Autowired
    WebTestClient client;

    @Test
    void healthAllowsAnonymous() {
        client.get().uri("/api/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void aliceCanReadHerDocument() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-1");
    }

    @Test
    void bobCannotReadAlicesDocument() {
        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousCannotReadProtectedDocument() {
        client.get().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ownerWithEditorRoleCanUpdate() {
        client.mutateWith(mockUser("alice").roles("USER", "EDITOR"))
            .mutateWith(csrf())
            .put().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.result").isEqualTo("updated:doc-1");
    }

    @Test
    void ownerWithoutEditorRoleCannotUpdate() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .put().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorCannotUpdateSomeoneElsesDocument() {
        client.mutateWith(mockUser("bob").roles("USER", "EDITOR"))
            .mutateWith(csrf())
            .put().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void deletionDoesNotInheritPutPermission() {
        client.mutateWith(mockUser("alice").roles("USER", "EDITOR"))
            .mutateWith(csrf())
            .delete().uri("/api/documents/doc-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`mockUser("alice")` và `mockUser("bob")` giúp kiểm tra authorization **mà không xác thực mật khẩu thật**. Ca Alice đọc doc-1 là đối chứng dương; ca Bob đọc doc-1 là đối chứng âm về ownership. Các ca PUT tách riêng owner và `ROLE_EDITOR`.

`csrf()` có mặt vì cấu hình mẫu không tắt CSRF. Nếu thiếu CSRF token, một request PUT có thể nhận `403` trước khi ownership được kiểm tra. Một test thiếu CSRF có thể vô tình thành công dù logic owner bị lỗi. API chỉ dùng JWT Bearer stateless có thể chọn cấu hình CSRF khác; khi đó các test phải phù hợp với SecurityWebFilterChain thật.

| User | HTTP method | Tài liệu | Quyền | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Alice | GET | doc-1 | USER | `200` |
| Alice | GET | doc-2 | USER | `403` |
| Bob | GET | doc-2 | USER | `200` |
| Anonymous | GET | doc-1 | — | `401` |
| Alice | PUT | doc-1 | USER + EDITOR | `200` |
| Alice | PUT | doc-1 | USER | `403` |
| Bob | PUT | doc-1 | USER + EDITOR | `403` |
| Bob | PUT | doc-2 | USER + EDITOR | `200` |
| Alice | DELETE | doc-1 | USER + EDITOR | `403` nếu security chặn trước routing |

Một route không có controller handler có thể trả `405 Method Not Allowed` nếu request đến được routing layer; `denyAll` trong security chain có thể trả `403` trước đó. Vì vậy kỳ vọng phải dựa vào thứ tự filter và mapping của ứng dụng đang test.

## 7. Dùng Basic header để kiểm tra xác thực thật

Các test với `mockUser()` không đi qua kiểm tra username/password. Để quan sát authentication filter và authorization cùng vận hành, có thể gửi header Basic thật tới WebFlux:

~~~java
@Test
void validBasicAuthenticationThenOwnerCheckSucceeds() {
    client.get()
        .uri("/api/documents/doc-1")
        .headers(h -> h.setBasicAuth("alice", "secret"))
        .exchange()
        .expectStatus().isOk();
}

@Test
void aCorrectPasswordDoesNotGrantAnotherUsersDocument() {
    client.get()
        .uri("/api/documents/doc-1")
        .headers(h -> h.setBasicAuth("bob", "secret"))
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void incorrectPasswordIsRejectedBeforeOwnerCheck() {
    client.get()
        .uri("/api/documents/doc-1")
        .headers(h -> h.setBasicAuth("alice", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Ba phương thức này được đặt trong lớp test WebTestClient mục 6. `setBasicAuth` tạo header `Authorization: Basic ...`; `MapReactiveUserDetailsService` trong cấu hình mục 3 cung cấp user để Spring Security kiểm tra mật khẩu. Các test cho biết:

- Mật khẩu đúng + chủ sở hữu đúng có thể trả `200`.
- Mật khẩu đúng + chủ sở hữu sai bị từ chối quyền, thường `403`.
- Mật khẩu sai bị từ chối **trước khi** phép kiểm tra chủ sở hữu có một principal hợp lệ.

Như vậy `401` do authentication khác với `403` do authorization. Nếu ứng dụng dùng JWT Bearer hoặc opaque token, cần thay HTTP Basic bằng Bearer Resource Server tương ứng và kiểm thử decoder/introspector bằng token thực khi mục tiêu là kiểm chứng xác thực.

## 8. JWT/OAuth2/OIDC giả lập có vai trò gì?

`spring-security-test` có `mockJwt()` cho WebFlux Resource Server, phù hợp để kiểm tra authorization với một subject và authorities xác định:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

// Đoạn ví dụ dành cho test context đã bật JWT Resource Server.
WebTestClient aliceJwtClient = client.mutateWith(
    mockJwt()
        .jwt(jwt -> jwt.subject("alice"))
        .authorities(new SimpleGrantedAuthority("ROLE_EDITOR")));

aliceJwtClient.mutateWith(csrf())
    .put().uri("/api/documents/doc-1")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ JWT này cần một ứng dụng **có cấu hình Resource Server JWT** và rule owner tương ứng. Không ghép trực tiếp vào ứng dụng chỉ cấu hình HTTP Basic ở mục 3 rồi kết luận JWT đã được decode. `mockJwt()` đặt một `JwtAuthenticationToken` giả lập vào test, **không gửi chuỗi JWT đã ký qua Bearer header** và không xác minh chữ ký bằng `ReactiveJwtDecoder`.

Theo convention của Resource Server, `scope=documents.write` thường trở thành authority `SCOPE_documents.write`, chứ **không tự biến thành `ROLE_EDITOR`**. Nếu yêu cầu nghiệp vụ dùng role, cần có converter phù hợp hoặc chỉnh rule theo authority thực tế. Test mock phải dùng cùng quy tắc ánh xạ mà ứng dụng vận hành.

Tương tự, `mockOAuth2Login()` hoặc `mockOidcLogin()` cung cấp authentication cho test khi người dùng đã được đăng nhập OAuth2/OIDC. Chúng không kiểm tra authorization code, PKCE, ID token signature, redirect hay IdP thật. Với test authentication flow thực, cần dùng HTTP request qua luồng bảo mật tương ứng, độc lập với test owner/role.

## 9. Test method security với @WithMockUser và StepVerifier

Khi kiểm thử `@PreAuthorize` ở `DocumentWriteService`, dùng Spring bean thật và subscription Reactive:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class DocumentMethodSecurityTest {

    @Autowired
    DocumentWriteService writeService;

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void editorCanInvokeSecuredMethod() {
        StepVerifier.create(writeService.update("doc-1"))
            .expectNext("updated:doc-1")
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCannotInvokeEditorMethod() {
        StepVerifier.create(writeService.update("doc-1"))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Đoạn test này kiểm tra **Java method security**, không kiểm tra URL. `@WithMockUser` tạo security context phục vụ test; Spring Security Test hỗ trợ Reactor Context cho phép `@EnableReactiveMethodSecurity` đọc được identity khi publisher được subscribe. Nếu pipeline được chuyển sang một subscription bên ngoài context hoặc tự tách khỏi reactive chain, phải kiểm tra việc truyền Reactor Context.

Một user EDITOR trong test trên vẫn có thể gọi `update("doc-2")` vì service mẫu mới kiểm tra role. Điều này nhấn mạnh nhu cầu có quyền sở hữu **ngay ở service hoặc tầng dữ liệu** nếu method được dùng bởi nhiều entry point.

## 10. Những lỗi dễ làm kiểm thử phân quyền cho kết quả sai

**Matcher quá rộng hoặc đặt trước rule cụ thể.** `/api/documents/**` chỉ yêu cầu authenticated có thể bỏ qua owner check nếu được đặt trước rule `GET /api/documents/{id}`. Thêm test Bob đọc doc-1 giúp phát hiện.

**Tin owner do client gửi.** Trường `owner` trong body hoặc header `X-User` có thể bị giả mạo. Hãy đọc owner từ kho dữ liệu do server kiểm soát và đối chiếu với principal đáng tin cậy.

**Chỉ kiểm tra role.** Bob có EDITOR không có nghĩa được sửa tài liệu của Alice. Test phải có trường hợp role đúng nhưng owner sai.

**Chỉ kiểm tra owner.** Alice sở hữu doc-1 nhưng vẫn có thể thiếu EDITOR để sửa nó. Test phải có trường hợp owner đúng nhưng role sai.

**Dùng blocking I/O trong ReactiveAuthorizationManager.** `.block()` hoặc JDBC đồng bộ chạy trên event-loop có thể làm nghẽn pipeline. Nên dùng kho dữ liệu hỗ trợ Reactive hoặc bố trí riêng blocking work theo thiết kế.

**Không kiểm tra CSRF trong request thay đổi dữ liệu.** PUT/DELETE có thể bị `403` vì thiếu token CSRF trước khi manager owner chạy. Hãy có đối chứng dương với CSRF hợp lệ trong cấu hình có CSRF.

**Dùng `@WithMockUser` hoặc `mockJwt()` để chứng minh JWT/mật khẩu hợp lệ.** Đây là công cụ giả lập identity; để kiểm thử xác thực thật phải gửi Basic/Bearer header và chạy provider/decoder/introspector.

**Chỉ kiểm tra `auth.isAuthenticated()`.** Anonymous token vẫn có thể mang cờ này; cần cơ chế loại trừ anonymous hoặc dùng các manager authenticated tiêu chuẩn.

**Đọc owner xong rồi ghi mà không xét thay đổi đồng thời.** Nếu chủ sở hữu bị đổi giữa bước kiểm tra và bước update, request cũ có thể ghi dữ liệu sai. Với dữ liệu quan trọng, dùng update có điều kiện owner hoặc transaction phù hợp.

**Không xét tenant.** Username giống nhau ở hai tenant không đủ chứng minh cùng principal. Cần nguồn định danh ổn định và điều kiện tenant.

**Bỏ qua `Mono.empty()`/`Mono.error(...)` của owner lookup.** Khi chưa kiểm chứng được owner, không được cho request đi tiếp. Mã HTTP tương ứng với lỗi repository cần được test theo error policy.

**Chỉ có test bị từ chối.** Một security chain sai khiến mọi request `403` cũng làm nhiều ca âm tính qua. Phải có đối chứng dương: owner đọc được và owner có EDITOR cập nhật được.

**Không có quy tắc về sự tồn tại của tài nguyên.** Có API trả `403` cho bản ghi của người khác; có API chủ động trả `404` để giảm tiết lộ sự tồn tại. Chọn một policy nhất quán và kiểm tra đúng policy đó.

## 11. Bài tập thực hành

1. Thêm `doc-3` thuộc Alice. Viết test Alice đọc `doc-3` thành công, Bob bị từ chối; thử ID không tồn tại và xác định policy trả `403` hay `404`.
2. Cho Bob thêm `ROLE_EDITOR`. Kiểm tra Bob vẫn không thể cập nhật `doc-1` nhưng cập nhật được `doc-2`.
3. Thử đưa matcher `/api/documents/**` lên trước rule ownership. Chạy lại test Bob đọc doc-1, xác định vì sao bị lọt quyền, rồi sửa thứ tự.
4. Dùng `@WithMockUser` và `StepVerifier` để kiểm tra method security của `DocumentWriteService.update` với USER và EDITOR.
5. Thay owner map bằng repository Reactive; mô phỏng `Mono.empty()` và lỗi kết nối, bảo đảm không cho phép truy cập khi chưa chứng minh được owner.
6. Gửi HTTP Basic đúng/sai mật khẩu bằng `WebTestClient`, phân biệt `401` do xác thực với `403` do owner không khớp.
7. Chuyển sang JWT Resource Server, test quyền bằng `mockJwt()`; tiếp tục gửi JWT ký thật qua `ReactiveJwtDecoder` để kiểm tra chữ ký sai, issuer sai hoặc token hết hạn trả `401`.
8. Thêm tenant ID và immutable user ID vào ownership, tạo hai principal có cùng username hiển thị ở tenant khác nhau và kiểm tra không truy cập chéo.
9. Thêm câu lệnh update database có điều kiện owner; mô phỏng việc chuyển owner trước khi cập nhật và chứng minh request cũ không thể sửa bản ghi.

### Kết quả cần đạt

Người học cần phân biệt rõ **authentication nằm trong Reactor Context**, **quy tắc theo path và HTTP method**, **method security trên Spring bean** và **phân quyền theo dữ liệu chủ sở hữu của từng tài nguyên**. Kết hợp test `200`, `401` và `403` với nguyên nhân rõ ràng sẽ phát hiện được cả lỗi xác thực, lỗi phân quyền và lỗi bỏ qua ranh giới đối tượng.

### Tài liệu tham khảo

- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
