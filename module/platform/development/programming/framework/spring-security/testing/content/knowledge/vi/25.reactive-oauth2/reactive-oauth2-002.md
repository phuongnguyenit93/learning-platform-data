# Tùy chỉnh claims và authorities trong mockJwt

Một JWT có thể chứa nhiều claim: `sub`, `scope`, `aud`, `tenant`, `permissions` hoặc `roles`. Khi kiểm thử một endpoint WebFlux, bạn cần xác minh principal đọc đúng claim, authority phản ánh quyền cần thiết và policy cho phép hoặc từ chối đúng trường hợp. `mockJwt()` cho phép dựng JWT giả lập để kiểm tra các hành vi đó mà không cần phát hành token thật cho mỗi test.

Bài học thuộc chương **OAuth2 Reactive** của module **SPRING_SECURITY_TESTING**. Module hướng dẫn kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Nội dung tập trung vào việc tùy chỉnh claim bằng `mockJwt().jwt(...)`, cấp authority trực tiếp, kiểm tra principal/claim tùy chỉnh và xác minh converter ánh xạ claim thành authority. Bạn cũng sẽ phân biệt test authorization dùng JWT giả lập với test xác thực token thật qua `ReactiveJwtDecoder`.

## 1. Claims và authorities có vai trò khác nhau

JWT là tập hợp các claim được đóng gói trong token. Claim mô tả chủ thể hoặc thuộc tính của token; authority là quyền mà Spring Security dùng khi đánh giá authorization.

Ví dụ payload minh họa:

~~~json
{
  "sub": "lan",
  "preferred_username": "lan.nguyen",
  "scope": "reports:read reports:export",
  "tenant": "north",
  "permissions": ["report:approve", "report:archive"]
}
~~~

Một số claim thường gặp:

| Claim | Ý nghĩa | Cách thường được dùng |
| --- | --- | --- |
| `sub` | Subject, định danh chủ thể token | Principal name mặc định |
| `preferred_username` | Username thân thiện do issuer cung cấp | Principal name nếu converter được cấu hình |
| `scope` | OAuth2 scopes, thường là chuỗi phân tách bằng khoảng trắng | Converter mặc định tạo `SCOPE_...` authorities |
| `scp` | Claim scope dạng khác mà converter mặc định có thể hỗ trợ | Mapping scope tùy phiên bản/cấu hình |
| `roles` | Role do issuer hoặc hệ thống phát hành quy ước | Cần mapping nếu muốn biến thành authority |
| `permissions` | Permission chi tiết của ứng dụng | Thường cần converter tùy chỉnh |
| `tenant` | Tenant hoặc tổ chức của chủ thể | Dùng trong policy kiểm tra phạm vi dữ liệu |
| `aud` | Audience mà token hướng tới | Validator xác minh token thật; code có thể đọc claim |
| `iss` | Issuer phát hành token | Validator xác minh issuer của token thật |

Ví dụ `scope = "reports:read"` không đồng nghĩa trong JWT đã có một authority tên `SCOPE_reports:read`. Resource Server chuyển claim thành `GrantedAuthority` thông qua converter. Với converter mặc định, scope thường được thêm tiền tố `SCOPE_`.

Authorization rule thường kiểm tra authority:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/reports")
            .hasAuthority("SCOPE_reports:read")
        .anyExchange().authenticated()
)
~~~

Vì vậy, khi viết test, hãy xác định rõ bạn đang kiểm tra **claim có trong JWT**, **authority được tạo ra từ claim**, hay **quyết định authorization dựa trên authority**. Đây là ba lớp liên quan nhưng không phải một.

## 2. Tùy chỉnh claim với mockJwt().jwt(...)

`mockJwt()` là configurer cho `WebTestClient` trong package:

~~~java
org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers
~~~

Dùng `.jwt(...)` để thay đổi JWT giả lập bằng builder:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("lan")
                .claim("preferred_username", "lan.nguyen")
                .claim("tenant", "north")
                .claim("scope", "reports:read reports:export")
                .claim("permissions", List.of("report:approve", "report:archive"))))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Các import cần thiết cho đoạn trên:

~~~java
import java.util.List;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
~~~

`jwt(...)` nhận một consumer của `Jwt.Builder`. Bạn có thể thiết lập subject, header và claim tùy chỉnh. Các kiểu dữ liệu claim nên phản ánh cấu trúc mà ứng dụng thật nhận từ issuer:

Builder do `mockJwt()` tạo sẵn một số giá trị mặc định cho header `alg` và các claim `sub`, `scope`. Nếu test cần khẳng định danh sách authority chính xác, hãy ghi đè scope hoặc cấp authorities tường minh để không vô tình phụ thuộc các giá trị mặc định đó.

- Chuỗi cho `tenant`, `preferred_username` hoặc một claim định danh.
- Danh sách chuỗi cho `permissions` dạng mảng.
- Chuỗi phân tách bằng khoảng trắng cho `scope` theo quy ước OAuth2 phổ biến.
- Danh sách chuỗi cho `aud` nếu cần mô phỏng audience dạng mảng.
- Số hoặc thời điểm cho claim số như `iat`, `exp`, `nbf` nếu code ứng dụng đọc chúng.

Claim tùy chỉnh chỉ có ý nghĩa khi code ứng dụng thực sự đọc hoặc converter/policy sử dụng nó. Thêm `tenant` vào JWT mock không tự động tạo tenant context hoặc áp dụng tenant isolation.

## 3. Dùng claim để kiểm tra principal và dữ liệu của controller

Với Resource Server Reactive, principal thường là `Jwt`. Controller có thể nhận JWT qua `@AuthenticationPrincipal`:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "username", jwt.getClaimAsString("preferred_username"),
                "tenant", jwt.getClaimAsString("tenant")));
    }
}
~~~

Test có thể cung cấp claim và xác minh response:

~~~java
@Test
void controllerReadsCustomClaims() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("user-42")
                    .claim("preferred_username", "lan.nguyen")
                    .claim("tenant", "north")))
            .get()
            .uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("user-42")
            .jsonPath("$.username").isEqualTo("lan.nguyen")
            .jsonPath("$.tenant").isEqualTo("north");
}
~~~

Test này kiểm tra controller đọc claim từ principal JWT giả lập. Nó không chứng minh `JwtDecoder` đã kiểm tra chữ ký, issuer hoặc audience. Nếu claim `tenant` quyết định quyền truy cập dữ liệu, cần thêm ca tenant đúng và tenant sai ở policy/service thay vì chỉ kiểm tra JSON response.

## 4. Authorities mặc định từ scope

Resource Server mặc định thường dùng `JwtGrantedAuthoritiesConverter` để chuyển `scope` hoặc `scp` thành authorities. Mỗi scope được gắn tiền tố `SCOPE_`.

JWT mock:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("lan")
                .claim("scope", "reports:read reports:export")))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Authorities mong đợi với mapping mặc định:

~~~text
SCOPE_reports:read
SCOPE_reports:export
~~~

Rule tương ứng:

~~~java
.hasAuthority("SCOPE_reports:read")
~~~

Nếu ứng dụng kiểm tra `hasAuthority("reports:read")`, rule sẽ không khớp với authority mặc định có tiền tố. Có thể thay đổi prefix hoặc dùng custom converter, nhưng cần đảm bảo cấu hình ứng dụng và test thống nhất.

Có thể viết assertion trong reactive pipeline để quan sát authority:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
~~~

Kiểu dữ liệu là `Mono<Authentication>` vì `ReactiveSecurityContextHolder.getContext()` trả về `Mono<SecurityContext>`. Publisher cần được compose trong pipeline; không đọc `SecurityContextHolder` theo mô hình ThreadLocal của Servlet để suy ra context Reactive.

## 5. Cấp authorities trực tiếp trong mockJwt

Khi muốn kiểm tra authorization mà không phụ thuộc vào claim converter, có thể cấp authority trực tiếp cho JWT mock:

~~~java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
        .mutateWith(mockJwt()
                .jwt(jwt -> jwt
                        .subject("lan")
                        .claim("permissions", List.of("report:read")))
                .authorities(List.of(
                        new SimpleGrantedAuthority("PERM_report:read"))))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Trong ví dụ, claim `permissions` được thêm vào JWT để test có thể kiểm tra dữ liệu claim, còn authority `PERM_report:read` được cấp trực tiếp cho authentication. Rule authorization phải yêu cầu đúng authority đó, ví dụ:

~~~java
.hasAuthority("PERM_report:read")
~~~

Cách cấp authority trực tiếp giúp cô lập test authorization. Nó không chứng minh converter production đã đọc claim `permissions` và tạo ra `PERM_report:read`. Nếu mapping claim là yêu cầu của ứng dụng, hãy test converter riêng hoặc chạy request qua luồng xác thực JWT thật.

Có thể dùng cách này để kiểm tra ma trận quyền:

~~~java
@Test
void readPermissionIsAllowed() {
    webTestClient.mutateWith(mockJwt().authorities(List.of(
                    new SimpleGrantedAuthority("PERM_report:read"))))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
}

@Test
void exportOnlyPermissionCannotRead() {
    webTestClient.mutateWith(mockJwt().authorities(List.of(
                    new SimpleGrantedAuthority("PERM_report:export"))))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Hai test trên giả định route yêu cầu `PERM_report:read` và JWT mock tạo authentication cho request. Request có authentication nhưng thiếu authority sẽ thường nhận `403 Forbidden`.

### Derive authorities từ chính JWT mock

Ngoài danh sách authority cố định, `JwtMutator` còn có overload nhận `Converter<Jwt, Collection<GrantedAuthority>>`. Overload này nhận JWT đã được dựng bằng `.jwt(...)` rồi tính authorities từ claim của chính JWT đó:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

webTestClient
        .mutateWith(mockJwt()
                .jwt(jwt -> jwt
                        .subject("lan")
                        .claim("permissions", List.of("report:read")))
                .authorities(jwt -> jwt.getClaimAsStringList("permissions")
                        .stream()
                        .map(permission -> (GrantedAuthority)
                                new SimpleGrantedAuthority("PERM_" + permission))
                        .collect(Collectors.toList())))
        .get()
        .uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Đây là converter được truyền riêng cho **test configurer**. Nó hữu ích khi muốn chứng minh cách một JWT mock cụ thể được biến thành authorities trong request test. Tuy nhiên, nó không tự gọi `ReactiveJwtAuthenticationConverter` đã cấu hình trong `SecurityWebFilterChain` của ứng dụng. Nếu muốn xác minh converter production, hãy test bean converter riêng hoặc gửi bearer token qua decoder/filter chain thật.

Ba cách cấp authority trong `JwtMutator` phục vụ các mục tiêu khác nhau:

| Cách cấu hình | Ý nghĩa |
| --- | --- |
| `.authorities(Collection<GrantedAuthority>)` | Gắn một danh sách authority cố định vào authentication mock |
| `.authorities(GrantedAuthority...)` | Cách truyền danh sách cố định bằng varargs |
| `.authorities(Converter<Jwt, Collection<GrantedAuthority>>)` | Tính authority từ JWT mock, ví dụ đọc claim `permissions` |

## 6. Tùy chỉnh converter cho claim permissions

Nhiều issuer phát hành claim ứng dụng như:

~~~json
{
  "sub": "lan",
  "permissions": ["report:read", "report:export"],
  "tenant": "north"
}
~~~

Bạn có thể cấu hình Reactive JWT authentication converter để biến mỗi permission thành authority có tiền tố `PERM_`. Ví dụ:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Flux;

@Configuration
class ReactiveJwtClaimsConfig {

    @Bean
    ReactiveJwtAuthenticationConverter jwtAuthenticationConverter() {
        ReactiveJwtAuthenticationConverter converter =
                new ReactiveJwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<String> permissions =
                    jwt.getClaimAsStringList("permissions");

            if (permissions == null) {
                return Flux.empty();
            }

            return Flux.fromIterable(permissions)
                    .map(permission ->
                            (GrantedAuthority) new SimpleGrantedAuthority(
                                    "PERM_" + permission));
        });

        converter.setPrincipalClaimName("preferred_username");
        return converter;
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveJwtAuthenticationConverter jwtAuthenticationConverter) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/reports")
                            .hasAuthority("PERM_report:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(
                                jwtAuthenticationConverter)))
                .build();
    }
}
~~~

Converter ở đây thực hiện hai việc:

1. Đọc danh sách claim `permissions` và tạo các `GrantedAuthority` có tiền tố `PERM_`.
2. Dùng claim `preferred_username` làm principal name thay vì mặc định `sub`.

Nếu ứng dụng cần giữ cả scope mặc định và permission tùy chỉnh, converter phải kết hợp cả hai nguồn authority. Đoạn ví dụ chỉ ánh xạ `permissions` để làm rõ cơ chế. Trong dự án thật, tránh vô tình bỏ các scope authority đang được policy khác sử dụng.

## 7. Kiểm thử converter riêng biệt

`mockJwt()` dựng authentication cho request test; nó không phải bằng chứng rằng converter cấu hình trong `SecurityWebFilterChain` đã được gọi. Vì vậy, hãy kiểm tra converter bằng một test riêng.

Ví dụ gọi converter trực tiếp:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.core.Authentication;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveJwtAuthenticationConverterTest {

    private final ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtClaimsConfig().jwtAuthenticationConverter();

    @Test
    void mapsPermissionsAndPrincipalClaim() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("preferred_username", "lan.nguyen")
                .claim("permissions", List.of(
                        "report:read", "report:export"))
                .build();

        StepVerifier.create(converter.convert(jwt))
                .assertNext(authentication -> {
                    assertThat(authentication.getName())
                            .isEqualTo("lan.nguyen");
                    assertThat(authentication.getAuthorities())
                            .extracting("authority")
                            .containsExactlyInAnyOrder(
                                    "PERM_report:read",
                                    "PERM_report:export");
                })
                .verifyComplete();
    }
}
~~~

Test này kiểm tra converter tạo principal name và authorities đúng từ claim. JWT được tạo trực tiếp bằng builder, không được ký hoặc giải mã. Đây là unit test mapping, không phải test chữ ký JWT.

Trong test thực tế, nên inject converter bean thay vì tự gọi constructor cấu hình nếu class config có dependency khác. Có thể tách converter thành một bean độc lập để unit test dễ dàng.

## 8. Kiểm thử allowed/denied với custom claims

Giả sử endpoint yêu cầu `PERM_report:read` và converter production đọc claim `permissions`. Dùng `mockJwt()` với authority trực tiếp để kiểm tra policy:

~~~java
@Test
void userWithReadPermissionCanAccess() {
    webTestClient
            .mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .subject("lan")
                            .claim("permissions", List.of("report:read"))
                            .claim("tenant", "north"))
                    .authorities(List.of(
                            new SimpleGrantedAuthority("PERM_report:read"))))
            .get()
            .uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
}

@Test
void userWithoutReadPermissionIsForbidden() {
    webTestClient
            .mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .subject("mai")
                            .claim("permissions", List.of("report:export"))
                            .claim("tenant", "north"))
                    .authorities(List.of(
                            new SimpleGrantedAuthority("PERM_report:export"))))
            .get()
            .uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Hai test trên xác minh authorization khi authentication đã được cung cấp. Nếu muốn xác minh mapping production, hãy bổ sung test converter hoặc test tích hợp gửi bearer token thật. Không suy luận rằng việc `mockJwt().authorities(...)` thành công có nghĩa claim converter đang hoạt động.

Một ma trận test hữu ích:

| JWT mock | Authority được cấp | Rule | Kết quả |
| --- | --- | --- | --- |
| Có `permissions = [report:read]` | `PERM_report:read` | `hasAuthority("PERM_report:read")` | Cho phép |
| Có `permissions = [report:export]` | `PERM_report:export` | `hasAuthority("PERM_report:read")` | Từ chối |
| Có `tenant = north` | Authority hợp lệ | Policy yêu cầu tenant `south` | Từ chối nếu policy kiểm tra tenant |
| Không có JWT mock | Không có JWT authentication | Route yêu cầu xác thực | Thường `401` |
| JWT mock có authority trực tiếp nhưng claim thiếu | Có authority | Rule chỉ kiểm tra authority | Có thể được phép; test này không chứng minh claim mapping |

## 9. Kết hợp claim tenant với authorization policy

Một claim tùy chỉnh có thể được dùng để giới hạn dữ liệu theo tenant. Tuy nhiên, việc claim tồn tại trong JWT không tự bảo vệ dữ liệu; ứng dụng cần policy thực sự kiểm tra claim và tài nguyên.

Ví dụ service:

~~~java
@Service
class TenantReportService {

    @PreAuthorize("@tenantPolicy.canRead(authentication, #tenantId)")
    public Mono<List<Report>> readReports(String tenantId) {
        return reportRepository.findByTenantId(tenantId).collectList();
    }
}
~~~

Nếu dùng `@PreAuthorize` trên reactive method, hãy bật Reactive Method Security trong cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

Policy có thể đọc principal và claim từ `JwtAuthenticationToken`:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

@Component("tenantPolicy")
class TenantPolicy {

    public boolean canRead(Authentication authentication, String tenantId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuthentication)) {
            return false;
        }

        String tokenTenant =
                jwtAuthentication.getToken().getClaimAsString("tenant");

        return tenantId.equals(tokenTenant);
    }
}
~~~

Test cho tenant phù hợp và không phù hợp:

~~~java
@Test
void sameTenantCanRead() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("lan")
                    .claim("tenant", "north"))
                    .authorities(List.of(
                            new SimpleGrantedAuthority("PERM_report:read"))))
            .get()
            .uri("/api/tenants/north/reports")
            .exchange()
            .expectStatus().isOk();
}

@Test
void differentTenantIsForbidden() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("lan")
                    .claim("tenant", "north"))
                    .authorities(List.of(
                            new SimpleGrantedAuthority("PERM_report:read"))))
            .get()
            .uri("/api/tenants/south/reports")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Các test giả định endpoint gọi method được bảo vệ, Reactive Method Security đã bật nếu dùng method security, và URL tenant được truyền vào service. Nếu authorization chỉ cấu hình ở route, hãy đặt rule tương ứng ở `authorizeExchange` hoặc kiểm tra policy trong controller/service. Đừng để test pass chỉ vì endpoint không thực sự sử dụng claim tenant.

## 10. Phân biệt claim mapping với xác thực JWT thật

`mockJwt()` giúp kiểm tra phần ứng dụng sau khi authentication đã có. Nó không kiểm tra các bước xác thực token:

| Điều cần xác minh | Dùng mockJwt? | Test phù hợp |
| --- | --- | --- |
| Controller đọc `tenant` hoặc `preferred_username` | Có | Dựng claim bằng `.jwt(...)` |
| Rule cho phép/từ chối theo authority | Có | Dựng authority bằng `.authorities(...)` hoặc claim với mapping mặc định |
| Custom converter tạo authority từ `permissions` | Không chỉ dựa vào mockJwt | Unit test converter hoặc integration test qua decoder |
| `JwtDecoder` đọc bearer token | Không | Gửi `Authorization: Bearer ...` qua filter chain/server |
| Chữ ký token hợp lệ | Không | Token ký bằng test key và decoder xác minh |
| Issuer/audience đúng | Không | Test validator với giá trị đúng và sai |
| Token hết hạn hoặc chưa có hiệu lực | Không | Test `exp`/`nbf` với clock/validator |
| JWK Set endpoint hoặc issuer discovery | Không | Integration test với issuer/JWK endpoint test |
| OAuth2 Authorization Code/OIDC login | Không | Dùng test support cho OAuth2/OIDC login phù hợp |

Ví dụ test converter hoặc `mockJwt()` có thể đưa claim `iss` và `aud` vào JWT mock, nhưng điều đó không chứng minh validator đã kiểm tra chúng. Khi cần xác minh chữ ký và metadata issuer, hãy tạo token ký bằng test key và gửi qua `ReactiveJwtDecoder` trong filter chain.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Controller đọc claim trả `null` | Claim chưa được thêm hoặc sai kiểu dữ liệu | Dùng `.claim(...)` với kiểu phù hợp và kiểm tra tên claim |
| Rule không khớp dù JWT có scope | Authority có tiền tố khác | Kiểm tra converter và dùng đúng `SCOPE_` hoặc prefix đã cấu hình |
| Có `permissions` nhưng không tạo authority | Converter mặc định không ánh xạ claim tùy chỉnh đó | Cấu hình converter hoặc cấp authority trực tiếp chỉ cho test authorization |
| Test `mockJwt().authorities(...)` pass nhưng production fail | Mock bỏ qua converter/decoder thật | Test converter riêng và gửi bearer token thật qua server |
| Principal name không phải username mong muốn | Mặc định dùng `sub` hoặc converter chưa đổi principal claim | Cấu hình `setPrincipalClaimName(...)` và kiểm tra |
| Tenant claim đúng nhưng vẫn đọc dữ liệu tenant khác | Policy không kiểm tra claim hoặc endpoint bỏ qua policy | Kiểm tra call path và viết ca tenant đúng/sai |
| Test trả `401` dù đã dùng mockJwt | Client/filter chain chưa được tích hợp hoặc test đang gửi tới live server | Dùng WebTestClient bind ApplicationContext + `springSecurity()`; live server cần bearer header |
| Test trả `403` dù claim có scope | Converter tạo authority khác rule hoặc mock authority không đúng | Assert danh sách authorities thực tế |
| `ReactiveSecurityContextHolder` không có context | Đọc ngoài Reactor pipeline hoặc filter chain chưa chạy | Compose `Mono` trong pipeline và kiểm tra WebTestClient setup |

## 12. Bài thực hành

Tạo một WebFlux Resource Server với endpoint `GET /api/reports` yêu cầu `PERM_report:read` và endpoint `GET /api/tenants/{tenant}/reports` kiểm tra tenant. Hoàn thành các nhiệm vụ:

1. Dựng `WebTestClient` bằng `bindToApplicationContext(...)` và `springSecurity()`.
2. Dùng `mockJwt().jwt(...)` để thêm `sub`, `preferred_username`, `tenant` và `permissions`.
3. Xác minh controller đọc đúng claim qua `@AuthenticationPrincipal Jwt`.
4. Cấp authority trực tiếp `PERM_report:read` và kiểm tra request được phép.
5. Cấp `PERM_report:export` và xác minh request đọc báo cáo bị từ chối.
6. Viết `ReactiveJwtAuthenticationConverter` để chuyển claim `permissions` thành authority `PERM_...`.
7. Test converter độc lập với `StepVerifier` để xác minh cả principal name và danh sách authority.
8. Kiểm tra tenant đúng và tenant sai bằng policy thực sự được gọi bởi endpoint/service.
9. So sánh test dùng authority trực tiếp với test converter: nêu rõ mỗi test chứng minh điều gì.
10. Tạo token ký bằng test key, gửi bearer token tới server test và xác minh decoder/issuer/audience/expiry; so sánh với `mockJwt()`.

Sau khi hoàn thành, hãy trả lời bốn câu hỏi: **JWT mock chứa claim nào? Authority được cấp trực tiếp hay được converter tạo? Authorization rule yêu cầu quyền gì? Test có đi qua decoder để xác minh token thật không?** Trả lời rõ bốn câu hỏi này giúp bạn thiết kế test có phạm vi chính xác và tránh nhầm dữ liệu claim với quyền đã được cấp.

## Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — JwtMutator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.JwtMutator.html)
- [Spring Security API — ReactiveJwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
