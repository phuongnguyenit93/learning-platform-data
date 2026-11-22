# mockOpaqueToken() và dữ liệu OAuth2AuthenticatedPrincipal

Trong Spring Security WebFlux Resource Server, khi API nhận **opaque access token**, Spring Security gọi một ReactiveOpaqueTokenIntrospector để hỏi Authorization Server về trạng thái và thông tin token. Kết quả introspection được chuyển thành Authentication có principal kiểu OAuth2AuthenticatedPrincipal cùng các GrantedAuthority.

Khi viết test cho WebFlux, không phải lúc nào cũng cần dựng Authorization Server hoặc gửi một token thật. **SecurityMockServerConfigurers.mockOpaqueToken()** tạo sẵn một BearerTokenAuthentication và OAuth2AuthenticatedPrincipal giả lập trong SecurityContext của ServerWebExchange. Nhờ vậy, test có thể tập trung vào controller, dữ liệu principal, scope, authority và authorization.

Bài học giải thích:

- Cách dùng mockOpaqueToken() với WebTestClient.
- Dữ liệu mặc định và cách tùy chỉnh attributes, authorities.
- Cách cung cấp một OAuth2AuthenticatedPrincipal hoàn chỉnh.
- Cách controller và service đọc principal trong reactive request.
- Phân biệt Authentication, principal, token attributes và GrantedAuthority.
- Ranh giới giữa test authorization bằng mock và test introspection thật.
- Cách kiểm thử scope, tenant, subject và những trường hợp thiếu dữ liệu.

## 1. Opaque token authentication trong WebFlux

Opaque access token thường là một chuỗi không chứa claims mà Resource Server có thể tự giải mã. Resource Server gửi token tới introspection endpoint. Authorization Server trả về trạng thái active cùng các attributes liên quan.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server

    C->>R: Authorization: Bearer opaque-token
    R->>I: introspect(token)
    I->>AS: POST /introspect
    AS-->>I: active=true + attributes
    I-->>R: OAuth2AuthenticatedPrincipal
    R->>R: Tạo BearerTokenAuthentication
    R->>R: Kiểm scope và authorization
    R-->>C: Response
~~~

Khi introspection thành công, Authentication thường là **BearerTokenAuthentication**. Principal của nó triển khai **OAuth2AuthenticatedPrincipal**.

Các phần cần phân biệt:

| Thành phần | Ý nghĩa |
|---|---|
| **Access token** | Credential mà client gửi trong Authorization header |
| **ReactiveOpaqueTokenIntrospector** | Gọi hoặc xử lý introspection và trả principal |
| **OAuth2AuthenticatedPrincipal** | Đại diện subject cùng attributes và authorities đã được xác minh |
| **BearerTokenAuthentication** | Authentication chứa principal, token và authorities |
| **GrantedAuthority** | Quyền mà Spring Security dùng trong authorization |
| **SecurityContext** | Lưu Authentication cho request hiện tại trong reactive flow |

Principal không phải raw token. Attributes không phải authorities. Một claim tên role nằm trong attributes không tự động trở thành ROLE_ADMIN nếu không có mapping phù hợp.

## 2. OAuth2AuthenticatedPrincipal là gì?

OAuth2AuthenticatedPrincipal là interface đại diện cho principal được xác thực bằng OAuth 2.0. Những thông tin quan trọng gồm:

- **getName()**: tên principal dùng trong Authentication.
- **getAttributes()**: Map các attributes từ introspection result.
- **getAttribute(name)**: lấy một attribute theo tên.
- **getAuthorities()**: tập GrantedAuthority của principal.

Ví dụ principal có dữ liệu:

~~~json
{
  "sub": "alice",
  "user_id": "u-1001",
  "tenant_id": "tenant-a",
  "client_id": "web-client",
  "scope": "messages:read messages:write",
  "email": "alice@example.com"
}
~~~

Các attributes có thể được đọc trong controller:

~~~java
@GetMapping("/api/profile")
public Mono<Map<String, String>> profile(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String subject = principal.getAttribute("sub");
    String tenant = principal.getAttribute("tenant_id");

    return Mono.just(Map.of(
        "name", principal.getName(),
        "subject", subject,
        "tenant", tenant
    ));
}
~~~

Ví dụ giả định các attributes bắt buộc đều có mặt. Nếu claim có thể thiếu, code production cần xử lý null thay vì đưa trực tiếp vào Map.of.

### 2.1. getName() không phải lúc nào cũng bằng sub

Nhiều Authorization Server dùng claim sub làm principal name, nhưng không nên hard-code giả định này nếu contract có thể khác.

Ví dụ AS gửi:

~~~json
{
  "user_name": "alice",
  "subject_id": "u-1001"
}
~~~

Principal có thể dùng user_name làm tên:

~~~java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        authorities
    );
~~~

Khi cần test đúng principal name, hãy cấu hình toàn bộ principal bằng phương thức principal(...) của mockOpaqueToken(), thay vì chỉ thêm một attribute rồi giả định getName() sẽ tự đổi.

### 2.2. Attributes và authorities là hai tập dữ liệu riêng

Ví dụ:

~~~text
Attributes:
  sub = alice
  tenant_id = tenant-a
  scope = messages:read

Authorities:
  SCOPE_messages:read
~~~

Attributes mô tả token/principal. Authorities là kết quả ánh xạ quyền để Spring Security sử dụng.

Nếu test đặt:

~~~text
attributes.roles = ["ADMIN"]
~~~

thì không có nghĩa principal tự có **ROLE_ADMIN**. Muốn test rule hasRole("ADMIN"), phải cấp authority ROLE_ADMIN hoặc kiểm thử converter/policy thực sự chịu trách nhiệm ánh xạ roles.

## 3. mockOpaqueToken() tạo Authentication giả lập

Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

Dùng với WebTestClient:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

mockOpaqueToken() cấu hình ServerWebExchange để SecurityContext có **BearerTokenAuthentication**, với **OAuth2AuthenticatedPrincipal** làm principal.

Helper này có từ Spring Security **5.3**. Cần thêm dependency spring-security-test và giữ phiên bản tương thích với Spring Security runtime.

### 3.1. Dữ liệu mặc định

Theo test support hiện hành, mockOpaqueToken() tạo principal với dữ liệu mặc định:

~~~text
Attributes:
  sub = user
  scope = read

Authorities:
  SCOPE_read
~~~

Điều này giúp một endpoint yêu cầu SCOPE_read có thể được kiểm thử mà không cần khai báo thêm dữ liệu.

Ví dụ:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ chỉ thành công nếu security configuration và endpoint cho phép authority mặc định đó.

### 3.2. Helper không yêu cầu token hợp lệ

mockOpaqueToken() tạo dữ liệu Authentication theo khai báo của test. Nó không cần một access token thực sự được Authorization Server phát hành.

Điều đó hữu ích khi mục tiêu là:

- Kiểm tra scope/authority.
- Kiểm tra controller đọc principal attributes.
- Kiểm tra method security.
- Kiểm tra tenant/subject authorization.
- Kiểm tra response khi principal có dữ liệu khác nhau.

Nó không xác minh token, không gọi introspection endpoint và không chứng minh client credentials hoặc network connection tới Authorization Server hoạt động.

## 4. Tùy chỉnh attributes bằng attributes(...)

Phương thức attributes nhận một Consumer<Map<String, Object>> để thêm hoặc thay đổi dữ liệu principal.

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("user_id", "u-1001");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("client_id", "web-client");
            attributes.put("scope", "messages:read");
        })
    )
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

Trong implementation test support, attributes mặc định được tạo trước rồi Consumer được áp dụng. Vì vậy nếu chỉ thêm user_id, các giá trị mặc định như sub=user và scope=read vẫn có thể tồn tại.

Nếu muốn test chính xác, hãy ghi rõ các claims có ý nghĩa cho scenario thay vì vô tình dựa vào default values.

### 4.1. Thêm tenant_id

Một API multi-tenant thường cần claim tenant:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("scope", "orders.read");
        })
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Controller hoặc service có thể dùng tenant_id để giới hạn dữ liệu. Test phải xác nhận request tenant-a không đọc được records thuộc tenant-b.

Không lấy tenant từ query parameter do caller tự khai nếu chính sách yêu cầu tenant được ràng buộc với principal.

### 4.2. Thêm client_id

Introspection attributes có thể chứa client_id:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "service-user");
    attributes.put("client_id", "reporting-client");
    attributes.put("scope", "reports.read");
})
~~~

Điều này hữu ích khi authorization phân biệt user và OAuth2 client. Nhưng client_id là dữ liệu của principal, không tự trở thành authority.

Nếu endpoint chỉ cho phép một nhóm client, cần policy kiểm tra client_id và test cả client được phép lẫn client bị từ chối.

### 4.3. Các kiểu dữ liệu phải đúng contract

Attributes là Map<String, Object>, nên giá trị có thể là String, Boolean, Number, List hoặc kiểu dữ liệu khác tùy introspection contract.

Ví dụ:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "alice");
    attributes.put("email_verified", Boolean.TRUE);
    attributes.put("groups", List.of("support", "operations"));
    attributes.put("account_level", 3);
})
~~~

Controller cần đọc đúng kiểu:

~~~java
Boolean verified = principal.getAttribute("email_verified");
List<String> groups = principal.getAttribute("groups");
Integer accountLevel = principal.getAttribute("account_level");
~~~

Không ép mọi attribute thành String. Khi test malformed hoặc thiếu claim, nên xác định rõ behavior mong muốn thay vì để ClassCastException xuất hiện tình cờ.

## 5. Tùy chỉnh authorities bằng authorities(...)

Để kiểm tra authorization, có thể chỉ định authorities trực tiếp:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

OpaqueTokenMutator có hai overload:

- authorities(Collection<GrantedAuthority>)
- authorities(GrantedAuthority...)

Ví dụ nhiều quyền:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read"),
            new SimpleGrantedAuthority("SCOPE_messages:write"),
            new SimpleGrantedAuthority("ROLE_MESSAGE_ADMIN")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange();
~~~

### 5.1. Authorities tường minh thay thế authorities suy ra từ scope

Mặc định helper đọc claim scope để tạo authorities với prefix **SCOPE_**. Ví dụ scope=read tạo SCOPE_read.

Khi gọi authorities(...), test đang cung cấp trực tiếp danh sách authorities dùng cho principal. Hãy xem đó là dữ liệu đầu vào của authorization test, không phải kiểm thử scope-to-authority converter của introspector.

### 5.2. Scope string không tự là authority

Ví dụ:

~~~text
scope = messages:read
~~~

authority thường dùng trong Spring Security:

~~~text
SCOPE_messages:read
~~~

Rule:

~~~java
.hasAuthority("SCOPE_messages:read")
~~~

Nếu test truyền:

~~~java
new SimpleGrantedAuthority("messages:read")
~~~

thì authority không khớp với rule có prefix SCOPE_.

### 5.3. Role cần ROLE_ prefix

Nếu authorization dùng:

~~~java
.hasRole("ADMIN")
~~~

authority cần có thường là:

~~~text
ROLE_ADMIN
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))
    )
    .delete()
    .uri("/api/admin/messages/42")
    .exchange()
    .expectStatus().isNoContent();
~~~

Role này được cấp trực tiếp cho mock principal. Nó không chứng minh Authorization Server thật có claim role tương ứng hoặc converter production ánh xạ role đó đúng.

## 6. Cung cấp một OAuth2AuthenticatedPrincipal hoàn chỉnh bằng principal(...)

Khi test cần thay đổi principal name, dùng custom principal implementation hoặc kiểm tra dữ liệu phức tạp, có thể tạo **DefaultOAuth2AuthenticatedPrincipal** rồi truyền qua principal(...).

~~~java
import java.util.Map;

import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

Map<String, Object> attributes = Map.of(
    "user_name", "alice",
    "subject_id", "u-1001",
    "tenant_id", "tenant-a"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        AuthorityUtils.createAuthorityList("SCOPE_messages:read")
    );

webTestClient
    .mutateWith(mockOpaqueToken().principal(principal))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

Cách này cấu hình toàn bộ principal, gồm:

- Name.
- Attributes.
- Authorities.

Dùng nó khi principal name không lấy từ sub, khi ứng dụng có custom OAuth2AuthenticatedPrincipal hoặc khi muốn test đúng cấu trúc principal mà một introspector tùy chỉnh trả về.

### 6.1. Khi nào dùng attributes() và khi nào dùng principal()?

| Nhu cầu | Cách phù hợp |
|---|---|
| Chỉ thêm sub, tenant_id hoặc user_id | attributes(...) |
| Đổi scope/claims để test | attributes(...) |
| Cấp một authority cụ thể | authorities(...) |
| Cấp nhiều authorities | authorities(...) |
| Đổi principal name theo user_name | principal(...) |
| Dùng custom OAuth2AuthenticatedPrincipal | principal(...) |
| Kiểm implementation principal của ứng dụng | principal(...) |

Không cần tự tạo principal hoàn chỉnh cho những test đơn giản. attributes() và authorities() dễ đọc hơn khi chỉ thay đổi một vài giá trị.

### 6.2. Principal name và attribute name là hai điều khác nhau

Ví dụ principal:

~~~java
new DefaultOAuth2AuthenticatedPrincipal(
    "alice@example.com",
    Map.of(
        "user_name", "alice",
        "sub", "u-1001"
    ),
    authorities
);
~~~

Khi đó:

~~~text
principal.getName() = alice@example.com
principal.getAttribute("user_name") = alice
principal.getAttribute("sub") = u-1001
~~~

Không mặc định getName() bằng sub hoặc email. Hãy dùng principal(...) khi test phụ thuộc vào tên đã được xác định theo contract.

## 7. Đọc principal trong WebFlux controller

Có hai cách thường dùng.

### 7.1. Inject OAuth2AuthenticatedPrincipal

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    Mono<String> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        return Mono.just(principal.getName());
    }
}
~~~

Đây là lựa chọn phù hợp khi controller cần đọc principal name hoặc attributes.

### 7.2. Inject BearerTokenAuthentication

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

@RestController
class TokenInfoController {

    @GetMapping("/api/token-info")
    Mono<String> tokenInfo(BearerTokenAuthentication authentication) {
        String subject =
            (String) authentication.getTokenAttributes().get("sub");

        return Mono.just(subject);
    }
}
~~~

BearerTokenAuthentication cung cấp thông tin về authentication của opaque token, trong đó getTokenAttributes() trả các token attributes.

Cách này hữu ích khi controller cần làm việc trực tiếp với BearerTokenAuthentication.

### 7.3. Đọc Authentication trong reactive service

Nếu cần truy cập SecurityContext trong reactive pipeline, dùng ReactiveSecurityContextHolder:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

Trong WebFlux, SecurityContext được truyền qua **Reactor Context**, không nên giả định nó luôn có trong ThreadLocal như cách dùng SecurityContextHolder của Servlet.

Đừng gọi subscribe() thủ công chỉ để lấy Authentication rồi lưu vào biến toàn cục. Hãy compose publisher để context tiếp tục được truyền theo request.

### 7.4. Không log access token

BearerTokenAuthentication có credential/token value. Khi debug principal, chỉ log những attributes đã được phép và cần thiết; không ghi raw token hoặc Authorization header vào log.

Principal attributes cũng có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm. Chỉ đưa những trường cần thiết vào response, log và trace.

## 8. Thiết lập WebTestClient với Spring Security

Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
~~~

Một cách tạo WebTestClient gắn với application context:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient =
    WebTestClient.bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

springSecurity() thiết lập test support cho Spring Security trong WebTestClient. Application context cần chứa SecurityWebFilterChain mà ứng dụng thực sự sử dụng.

### 8.1. Dùng Spring Boot integration test

Ví dụ skeleton:

~~~java
@SpringBootTest
class OpaqueTokenWebFluxTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient webTestClient;

    @BeforeEach
    void setUp() {
        this.webTestClient =
            WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }
}
~~~

Ví dụ giả định project dùng JUnit 5 và đã có WebFlux/Spring Security dependencies.

### 8.2. Dùng WebFlux slice test

Với @WebFluxTest, cần đưa controller và cấu hình security cần thiết vào test slice. Nếu SecurityWebFilterChain yêu cầu ReactiveOpaqueTokenIntrospector bean, test context vẫn phải có bean phù hợp để khởi tạo cấu hình.

mockOpaqueToken() bỏ qua introspection trong request test, nhưng **không tự tạo mọi bean mà application context cần để khởi động**.

Có thể dùng test configuration hoặc mock bean cho những dependency ngoài phạm vi test.

### 8.3. Dependency cần thiết

Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Giữ phiên bản spring-security-test đồng bộ với Spring Security runtime, thường thông qua Spring Boot dependency management hoặc Spring Security BOM.

Nếu thiếu test module, các static imports của SecurityMockServerConfigurers sẽ không được tìm thấy.

## 9. Test controller đọc attributes

Giả sử endpoint trả subject:

~~~java
@GetMapping("/api/profile")
Mono<String> profile(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getAttribute("sub"));
}
~~~

Test:

~~~java
@Test
void profileReturnsSubjectFromPrincipalAttributes() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("scope", "profile.read");
            })
        )
        .get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("alice");
}
~~~

Test này chứng minh controller đọc sub từ OAuth2AuthenticatedPrincipal được đưa vào request. Nó không chứng minh Authorization Server thật đã phát claim đó.

### 9.1. Test tenant attribute

~~~java
@GetMapping("/api/tenant")
Mono<String> tenant(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Mono.just(principal.getAttribute("tenant_id"));
}
~~~

Test:

~~~java
@Test
void tenantIsReadFromAuthenticatedPrincipal() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
            })
        )
        .get()
        .uri("/api/tenant")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-a");
}
~~~

Không lấy tenant từ query parameter nếu tenant phải được xác định bởi token/principal.

## 10. Test scope và authorities

Giả sử SecurityWebFilterChain yêu cầu:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/messages/**")
        .hasAuthority("SCOPE_messages:read")
    .anyExchange().authenticated()
)
~~~

### 10.1. Token có scope cần thiết

~~~java
@Test
void readScopeCanAccessMessages() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:read")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isOk();
}
~~~

### 10.2. Token thiếu scope

~~~java
@Test
void writeScopeCannotReadMessages() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:write")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Đây là authorization test. Authority được cấp trực tiếp cho principal mock; nó không kiểm tra scope trong introspection response được converter ánh xạ ra sao.

### 10.3. Test authority được suy ra từ scope attribute

Nếu muốn dùng logic mặc định của mutator, có thể cấu hình scope attribute:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes ->
            attributes.put("scope", "messages:read messages:write")
        )
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk();
~~~

Theo mặc định, mutator chuyển từng scope thành authority với prefix SCOPE_. Khi test cần authority đặc biệt, dùng authorities(...) trực tiếp.

### 10.4. Test role

~~~java
@Test
void adminRoleCanAccessAdminEndpoint() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))
        )
        .delete()
        .uri("/api/admin/messages/42")
        .exchange()
        .expectStatus().isNoContent();
}
~~~

Test role này chỉ xác minh authorization rule với authority ROLE_ADMIN. Nếu production lấy role từ một claim như roles, cần kiểm thử mapper/introspector thực tế riêng.

## 11. Test principal name khác sub

Giả sử Authorization Server dùng user_name làm tên hiển thị:

~~~java
Map<String, Object> attributes = Map.of(
    "user_name", "alice",
    "sub", "u-1001"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        attributes,
        AuthorityUtils.createAuthorityList("SCOPE_profile.read")
    );
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken().principal(principal))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("alice");
~~~

Nếu controller trả sub, kết quả sẽ là u-1001. Nếu controller trả principal.getName(), kết quả là alice.

Test này giúp phân biệt **principal name** và **subject claim**.

## 12. Test thiếu attributes và dữ liệu không hợp lệ

Một principal có thể thiếu claim vì Authorization Server thay đổi contract, scope bị lược bỏ hoặc token thuộc client khác.

Ví dụ:

~~~java
.attributes(attributes -> {
    attributes.put("sub", "alice");
    attributes.remove("tenant_id");
})
~~~

Nếu controller yêu cầu tenant_id, cần quyết định rõ:

- Trả 400 nếu dữ liệu request thiếu.
- Từ chối authentication/authorization nếu token thiếu claim bắt buộc.
- Trả 403 nếu principal không có quyền.
- Trả lỗi nội bộ có kiểm soát nếu contract bị vi phạm ở tầng mapping.

Không để null pointer hoặc ClassCastException trở thành response ngẫu nhiên.

### 12.1. Attributes thiếu không giống token inactive

mockOpaqueToken() vẫn tạo Authentication giả lập ngay cả khi attributes do test cấu hình thiếu một trường. Nó không chạy quy tắc active của introspection.

Trong hệ thống thật, token inactive thường không tạo principal được xác thực. Test inactive token cần kiểm tra introspector/Resource Server authentication flow thật.

### 12.2. Test type mismatch

Nếu production mong tenant_id là String nhưng introspection response trả Number hoặc List, test nên mô phỏng dữ liệu sai kiểu để xác định behavior.

Không ép kiểu bừa bãi trong controller. Tốt hơn nên có một lớp mapper/adapter chuyển OAuth2AuthenticatedPrincipal thành domain identity với validation rõ ràng.

## 13. Principal data và method security

WebFlux có thể dùng reactive method security để kiểm scope/authority ở service layer.

Bật:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Ví dụ:

~~~java
@Service
class MessageService {

    @PreAuthorize("hasAuthority('SCOPE_messages:read')")
    Mono<List<Message>> findMessages() {
        return repository.findAll().collectList();
    }
}
~~~

Test qua WebTestClient:

~~~java
@Test
void principalWithReadScopeCanInvokeService() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_messages:read")
            )
        )
        .get()
        .uri("/api/messages")
        .exchange()
        .expectStatus().isOk();
}
~~~

Method security kiểm authorities trong Authentication. Nếu policy cần tenant_id hoặc subject, service có thể nhận principal/Authentication hoặc dùng một authorization component đọc reactive SecurityContext.

### 13.1. Kiểm owner và tenant trong service

Ví dụ logic:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<Order> getOrder(UUID orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getPrincipal())
        .cast(OAuth2AuthenticatedPrincipal.class)
        .flatMap(principal -> {
            String subject = principal.getAttribute("sub");
            String tenantId = principal.getAttribute("tenant_id");

            return repository.findByIdAndTenantIdAndOwnerSubject(
                orderId, tenantId, subject
            );
        });
}
~~~

Test cần tạo principal có sub và tenant_id đúng, sau đó kiểm cả owner, non-owner và cross-tenant cases.

Không chỉ kiểm hasAuthority nếu endpoint trả dữ liệu theo tenant. Scope messages.read không tự cho phép đọc mọi message của mọi tenant.

### 13.2. Giữ dữ liệu principal trong reactive flow

SecurityContext trong WebFlux được lưu trong Reactor Context. Khi compose Mono/Flux, Spring Security có thể cung cấp context theo subscription.

Không đọc Authentication ở một thread tùy ý rồi giữ trong static variable. Không dùng ThreadLocal để truyền principal qua các async boundaries. Test cần đi qua WebFlux filter chain và reactive service path thực tế.

## 14. Phân biệt mockOpaqueToken(), mockJwt(), mockUser() và mockOAuth2Login()

Các helper tạo những loại Authentication khác nhau:

| Helper | Authentication | Principal |
|---|---|---|
| **mockOpaqueToken()** | BearerTokenAuthentication | OAuth2AuthenticatedPrincipal |
| **mockJwt()** | JwtAuthenticationToken | Jwt |
| **mockUser()** | UsernamePasswordAuthenticationToken | UserDetails |
| **mockOAuth2Login()** | OAuth2AuthenticationToken | OAuth2User |
| **mockOidcLogin()** | OAuth2AuthenticationToken | OidcUser |

Chọn helper theo principal mà controller/service thực sự nhận.

### 14.1. Khi controller nhận OAuth2AuthenticatedPrincipal

Dùng:

~~~java
@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal
~~~

Test phù hợp:

~~~java
.mutateWith(mockOpaqueToken())
~~~

### 14.2. Khi controller nhận Jwt

Dùng:

~~~java
@AuthenticationPrincipal Jwt jwt
~~~

Test phù hợp:

~~~java
.mutateWith(mockJwt())
~~~

Không dùng mockOpaqueToken() cho controller mong Jwt, vì principal của nó là OAuth2AuthenticatedPrincipal chứ không phải Jwt.

### 14.3. Khi controller nhận OidcUser

Dùng:

~~~java
@AuthenticationPrincipal OidcUser user
~~~

Test phù hợp:

~~~java
.mutateWith(mockOidcLogin())
~~~

OIDC login principal khác Resource Server opaque-token principal.

### 14.4. Khi chỉ cần test role đơn giản

mockUser() có thể đủ cho một rule role-based không phụ thuộc OAuth2 principal. Nhưng nếu code truy cập token attributes hoặc BearerTokenAuthentication, mockUser() tạo sai Authentication type cho mục tiêu test.

## 15. mockOpaqueToken() không gọi ReactiveOpaqueTokenIntrospector

Đây là ranh giới quan trọng nhất khi sử dụng helper.

mockOpaqueToken() đưa một Authentication giả lập vào SecurityContext. Nó **không gửi HTTP request tới Authorization Server**, không gọi ReactiveOpaqueTokenIntrospector và không kiểm token value.

Vì vậy, test dùng helper không chứng minh:

- Authorization header được trích xuất đúng.
- Introspection URI đúng.
- Client ID/client secret đúng.
- HTTP Basic/client authentication đúng.
- TLS certificate/hostname đúng.
- AS trả active=true hay active=false.
- Introspection response được parse đúng.
- Timeout, network failure hoặc AS 5xx được xử lý đúng.
- Scope/attributes thật được ánh xạ đúng từ response.

### 15.1. Khi nào nên mockOpaqueToken()?

Dùng nó khi trọng tâm là:

- SecurityWebFilterChain authorization.
- Controller principal binding.
- OAuth2AuthenticatedPrincipal attributes.
- Authorities và method security.
- Tenant/subject ownership policy.
- Response contract sau khi authentication đã thành công.

### 15.2. Khi nào phải kiểm introspection thật?

Dùng một test khác khi cần xác nhận:

- BearerTokenAuthenticationWebFilter trích token từ HTTP request.
- ReactiveOpaqueTokenIntrospector được gọi.
- Response active=false bị từ chối.
- Attributes và scopes từ AS được map đúng.
- Lỗi HTTP, timeout, TLS hoặc client credentials không fail-open.
- Authentication entry point trả status/challenge phù hợp.

Có thể dùng test HTTP server/stub cho introspection endpoint hoặc mock bean ReactiveOpaqueTokenIntrospector trong một integration test của filter chain.

## 16. Kiểm thử qua ReactiveOpaqueTokenIntrospector stub

Nếu muốn kiểm tra Resource Server thực sự gọi introspector nhưng không cần Authorization Server ngoài, có thể cung cấp một ReactiveOpaqueTokenIntrospector test.

Mô hình:

~~~java
ReactiveOpaqueTokenIntrospector introspector = token -> {
    if (!"test-access-token".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Invalid token"));
    }

    Map<String, Object> attributes = Map.of(
        "sub", "alice",
        "tenant_id", "tenant-a",
        "scope", "messages:read"
    );

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            attributes,
            AuthorityUtils.createAuthorityList("SCOPE_messages:read")
        );

    return Mono.just(principal);
};
~~~

Sau đó cấu hình introspector này vào Resource Server test context và gửi request có Authorization header thật:

~~~java
webTestClient
    .get()
    .uri("/api/messages")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ trên mô phỏng contract introspector, không kiểm HTTP client hoặc Authorization Server thật. Nó vẫn đi qua Bearer authentication filter và ReactiveOpaqueTokenIntrospector bean đã cấu hình.

### 16.1. So sánh ba mức test

| Cách test | Có SecurityContext? | Có chạy Bearer filter? | Có gọi introspector? |
|---|---|---|---|
| mockOpaqueToken() | Có, được tạo sẵn | Không cần trích token thật | Không |
| HTTP Bearer + introspector stub | Được tạo sau authentication | Có | Có, tới stub |
| HTTP Bearer + test AS/introspection server | Được tạo sau authentication | Có | Có, qua HTTP test server |

Chọn mức test theo câu hỏi cần trả lời. Không cần dựng AS cho mọi authorization test, nhưng không dùng mockOpaqueToken() để kết luận integration introspection hoạt động.

## 17. Test active=false và lỗi introspection

Một introspector thực tế không nên trả principal cho token inactive. Test với stub có thể:

- Trả BadOpaqueTokenException cho token không hợp lệ.
- Trả principal cho token active.
- Trả lỗi transport cho timeout/AS failure.
- Trả principal thiếu claim bắt buộc để kiểm validation/policy.

Các kết quả thường mong đợi:

| Tình huống | Kết quả |
|---|---|
| Token active và đủ scope | Request được phép |
| Token active nhưng thiếu scope | 403 |
| Token inactive/invalid | 401 |
| Introspection timeout | Không tạo Authentication thành công |
| AS 5xx | Không fail-open |
| Principal thiếu tenant bắt buộc | Từ chối theo policy |
| Principal có scope nhưng sai tenant | Từ chối resource authorization |

Không map mọi lỗi introspection thành một principal rỗng hoặc user mặc định. Khi chưa có kết quả xác minh tin cậy, authentication phải thất bại.

## 18. Kiểm tra response và lỗi khi dùng WebTestClient

WebTestClient cho phép kiểm tra status, headers và body:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages:read"))
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.count").isEqualTo(3);
~~~

Nếu request thiếu quyền:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_messages:write"))
    )
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isForbidden();
~~~

Nếu request không có Authentication:

~~~java
webTestClient
    .get()
    .uri("/api/messages")
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Status thực tế còn phụ thuộc SecurityWebFilterChain, entry point, authorization rule và controller. Hãy test đúng contract mà API công bố.

## 19. Một ma trận kiểm thử cho OAuth2AuthenticatedPrincipal

Giả sử API yêu cầu:

~~~text
GET /api/messages
  authority: SCOPE_messages:read

GET /api/tenant/messages
  authority: SCOPE_messages:read
  tenant: tenant-a

GET /api/admin/messages
  authority: ROLE_ADMIN
~~~

Ma trận:

| Principal | Authorities | Tenant | Kết quả mong đợi |
|---|---|---|---|
| Alice | SCOPE_messages:read | tenant-a | Đọc messages |
| Alice | SCOPE_messages:write | tenant-a | Bị từ chối đọc |
| Bob | SCOPE_messages:read | tenant-b | Bị từ chối ở tenant-a |
| Admin | ROLE_ADMIN | tenant-a | Qua admin policy |
| Anonymous | Không có | Không có | 401 |
| Active principal | Scope đúng nhưng thiếu tenant | Không có | Từ chối theo policy |

Test phải chứng minh cả nhánh cho phép và nhánh từ chối.

### 19.1. Test cùng scope, khác tenant

~~~java
@Test
void principalFromOtherTenantCannotReadTenantA() {
    webTestClient
        .mutateWith(mockOpaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "bob");
                attributes.put("tenant_id", "tenant-b");
                attributes.put("scope", "messages:read");
            })
        )
        .get()
        .uri("/api/tenant-a/messages")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test này giữ scope giống nhau nhưng thay tenant. Nếu vẫn được phép, policy tenant có thể đang bị bỏ qua.

### 19.2. Test scope đúng nhưng subject không phải owner

Tạo principal có scope đọc và subject khác owner của resource. Kiểm service/repository từ chối. **Scope cho phép loại hành động; subject/tenant quyết định dữ liệu nào được truy cập.**

## 20. Reactive SecurityContext và test isolation

WebFlux dùng Reactor Context để mang SecurityContext qua các publisher. Mỗi request test cần có principal riêng.

Không giữ principal vào static field hoặc singleton mutable state. Nếu test chạy song song, hai requests có thể bị lẫn dữ liệu nếu ứng dụng tự quản lý Authentication sai cách.

Ví dụ:

~~~text
Request A:
  sub=alice
  tenant=tenant-a

Request B:
  sub=bob
  tenant=tenant-b
~~~

Mỗi request phải đọc đúng principal của mình. Dùng WebTestClient mutator riêng cho từng request và tránh biến toàn cục lưu thông tin người dùng.

### 20.1. Không gọi subscribe() thủ công trong controller

Sai:

~~~java
@GetMapping("/api/profile")
Mono<String> profile() {
    ReactiveSecurityContextHolder.getContext()
        .subscribe(context -> saveUser(context.getAuthentication().getName()));

    return Mono.just("ok");
}
~~~

Cách này tạo subscription tách khỏi response lifecycle, khiến error/cancellation/context khó kiểm soát.

Đúng hơn là compose publisher:

~~~java
@GetMapping("/api/profile")
Mono<String> profile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

## 21. Những lỗi thường gặp

**Dùng mockOpaqueToken() để kiểm HTTP introspection.** Helper bỏ qua introspector và inject Authentication giả lập.

**Nhầm OAuth2AuthenticatedPrincipal với Jwt.** Opaque token principal không phải Jwt object.

**Dùng mockUser() cho controller nhận BearerTokenAuthentication.** Authentication type không phù hợp.

**Chỉ thêm tenant_id vào attributes nhưng không kiểm tenant.** Claim có mặt không có nghĩa authorization tự xảy ra.

**Nghĩ claim roles tự tạo ROLE_ADMIN.** Attributes và authorities là hai tập dữ liệu riêng.

**Nhầm scope với authority.** Scope messages:read thường trở thành SCOPE_messages:read.

**Nhầm principal.getName() với sub.** Principal name có thể được cấu hình theo attribute khác.

**Dựa vào default values mà không khai báo scenario.** Mặc định sub=user, scope=read có thể làm test xanh ngoài ý muốn.

**Không cấu hình spring-security-test.** Static imports và mutator không có trong test classpath.

**Không gắn Spring Security vào WebTestClient.** Test có thể không đi qua filters/authorization thật.

**Tạo SecurityFilterChain yêu cầu introspector nhưng test context thiếu bean.** mockOpaqueToken() không tự cấu hình application dependencies.

**Đọc attributes bằng kiểu sai.** Có thể gây ClassCastException hoặc NullPointerException.

**Log token hoặc toàn bộ attributes.** Có thể làm lộ credential hoặc dữ liệu nhạy cảm.

**Dùng một principal mutable cho nhiều requests.** Có nguy cơ rò rỉ dữ liệu giữa test cases.

**Nhầm mockOpaqueToken() với mockOAuth2Login().** Resource Server Bearer authentication và OIDC login là hai Authentication flows khác nhau.

## 22. Quy trình viết test

**Bước 1 — Xác định code cần kiểm.** Controller nhận OAuth2AuthenticatedPrincipal, BearerTokenAuthentication hay Authentication tổng quát?

**Bước 2 — Chọn helper đúng.** Với opaque Resource Server principal, dùng mockOpaqueToken().

**Bước 3 — Khai báo attributes rõ ràng.** Đặt sub, tenant_id, client_id và các claims cần thiết cho test.

**Bước 4 — Khai báo authorities rõ ràng.** Dùng authorities(...) khi kiểm scope/role; nếu kiểm default scope mapping của mutator, cấu hình scope attribute.

**Bước 5 — Kiểm principal name.** Nếu ứng dụng phụ thuộc getName(), tạo custom principal khi contract không dùng sub làm name.

**Bước 6 — Thiết lập WebTestClient có Spring Security.** Dùng application context và springSecurity() để test đúng filter chain.

**Bước 7 — Test positive và negative.** Đủ scope, thiếu scope, sai tenant, non-owner, thiếu attributes và anonymous.

**Bước 8 — Kiểm reactive method security.** Bật @EnableReactiveMethodSecurity nếu service dùng @PreAuthorize.

**Bước 9 — Tách test authentication integration.** Dùng Bearer header và ReactiveOpaqueTokenIntrospector stub/HTTP test server khi cần kiểm introspection.

**Bước 10 — Giữ request isolation.** Không lưu Authentication vào static/singleton mutable fields và không tự subscribe tách khỏi pipeline.

## 23. Câu hỏi tự kiểm tra

**1. mockOpaqueToken() tạo loại Authentication nào?**

BearerTokenAuthentication.

**2. Principal của nó triển khai interface nào?**

OAuth2AuthenticatedPrincipal.

**3. Dữ liệu mặc định của helper gồm gì?**

sub=user, scope=read và authority SCOPE_read.

**4. Làm sao thêm tenant_id?**

Dùng attributes(attributes -> attributes.put("tenant_id", "tenant-a")).

**5. Làm sao cấp authority SCOPE_messages:read?**

Dùng authorities(new SimpleGrantedAuthority("SCOPE_messages:read")).

**6. Nếu attributes có roles=["ADMIN"], principal có tự có ROLE_ADMIN không?**

Không. Cần mapping hoặc cấp authority rõ ràng.

**7. Khi nào dùng principal(...) thay attributes(...)?**

Khi cần cung cấp toàn bộ OAuth2AuthenticatedPrincipal, custom implementation hoặc principal name riêng.

**8. mockOpaqueToken() có gọi ReactiveOpaqueTokenIntrospector không?**

Không. Nó tạo Authentication giả lập trong test exchange.

**9. Có thể dùng mockJwt() thay mockOpaqueToken() cho controller nhận OAuth2AuthenticatedPrincipal không?**

Không nên. mockJwt() tạo JwtAuthenticationToken với Jwt principal.

**10. Vì sao WebFlux không nên dùng ThreadLocal để giữ Authentication?**

SecurityContext được truyền qua Reactor Context; ThreadLocal không đảm bảo context theo reactive execution.

**11. Test scope thành công có chứng minh introspection response được parse đúng không?**

Không nếu dùng mockOpaqueToken(). Cần introspector stub hoặc HTTP integration test.

**12. Token active nhưng thiếu scope nên trả kết quả gì?**

Authentication có thể thành công, nhưng authorization từ chối, thường là 403.

## Kết luận

**mockOpaqueToken()** là công cụ Spring Security Test dành cho WebFlux Resource Server khi cần tạo một **BearerTokenAuthentication** có principal kiểu **OAuth2AuthenticatedPrincipal** mà không cần Authorization Server thật.

Dùng:

- **attributes(...)** để thiết lập subject, tenant, client và các token attributes.
- **authorities(...)** để cấp scope/role authorities cho authorization tests.
- **principal(...)** để cung cấp một OAuth2AuthenticatedPrincipal hoàn chỉnh và kiểm principal name riêng.
- **WebTestClient.mutateWith(mockOpaqueToken())** để kiểm controller, filter authorization và reactive method security.

Điều cần giữ rõ là helper chỉ mô phỏng trạng thái đã authenticated. Nó không gọi introspection endpoint, không kiểm active, không xác minh client credentials và không test network failure. Khi cần chứng minh những phần đó, hãy gửi Bearer header thật qua Resource Server filter chain và dùng ReactiveOpaqueTokenIntrospector stub hoặc test Authorization Server.

**Một test WebFlux tốt phải mô phỏng đúng principal mà code đang dùng, kiểm attributes và authorities riêng biệt, rồi xác nhận cả những trường hợp scope/tenant/subject không đủ quyền đều bị từ chối.**

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Testing: Opaque Token Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — OpaqueTokenMutator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.OpaqueTokenMutator.html)
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html)
- [Spring Security API — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
