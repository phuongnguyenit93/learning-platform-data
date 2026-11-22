# saml2Login() trong kiểm thử và tùy chỉnh principal, thuộc tính, quyền

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot dùng **SAML 2.0 federation** cho phép người dùng đăng nhập qua Identity Provider (IdP), nhận danh tính trong `Saml2Authentication`, đọc thuộc tính SAML như email/phòng ban, rồi phân quyền đọc tài liệu hoặc thao tác quản trị. Khi viết test, nhóm phát triển thường muốn kiểm tra:

- Người dùng Alice đăng nhập SAML và có email/phòng ban mong đợi.
- Alice có role nhân viên, không tự có role quản trị.
- Người dùng Ops có quyền được cấp qua **policy của ứng dụng** chứ không chỉ vì IdP gửi một chuỗi “admin”.
- Controller nhận đúng `Saml2AuthenticatedPrincipal`, không chỉ một username giả bằng `@WithMockUser`.
- Một user thuộc IdP/tenant A không được mặc nhiên xem dữ liệu tenant B.
- Cấu hình `saml2Login()` không làm mất các kiểm tra chữ ký, issuer, audience, InResponseTo hoặc thời hạn khi kiểm thử tích hợp thật.

**Điểm phải phân biệt ngay từ đầu:** `HttpSecurity.saml2Login(...)` là **DSL cấu hình quy trình đăng nhập SAML thực** cho ứng dụng. Trong `spring-security-test` phiên bản **6.5.x**, API `SecurityMockMvcRequestPostProcessors` **không có factory `saml2Login()`** tương đương `oidcLogin()` hoặc `oauth2Login()`. Để chạy MockMvc test ở tầng controller/authorization với principal SAML **giả lập**, hãy tạo `DefaultSaml2AuthenticatedPrincipal` + `Saml2Authentication` rồi dùng `.with(authentication(samlAuthentication))`. Các project hoặc thư viện ngoài có thể tự định nghĩa helper tên `saml2Login()`; khi đó phải xác định helper được import từ đâu và nó có làm cryptographic validation hay không.

Bài học thuộc nhóm **Kiểm thử SAML2** của module Spring Security – federation. Mục tiêu là kiểm thử **principal, attributes và authorities** với Java 17+/Spring Boot 3.x/Spring Security 6.5, sau đó kết nối với integration test kiểm tra SAMLResponse có chữ ký thật. SAML credentials, URLs `example.test` và dữ liệu người dùng trong bài đều là ví dụ.

## 2. Hai loại kiểm thử và những gì chúng có thể chứng minh

| Tầng | Request đầu vào | Có chạy OpenSAML/IdP protocol thật không? | Điều được kiểm chứng |
| --- | --- | --- | --- |
| **Unit test service** | `Saml2AuthenticatedPrincipal`/`Authentication` fixture | Không | Mapping claim, authorization policy, tenant/ACL |
| **MockMvc controller/authorization slice** | `.with(authentication(samlAuth))` | **Không** | URL rules, `@AuthenticationPrincipal`, JSON, HTTP 200/401/403, CSRF |
| **MockMvc chạy application context đầy đủ** | Có thể vẫn dùng fixture `authentication(...)` | Không nếu inject fixture | Kết nối MVC/security filter chain nhưng **bỏ qua SAML XML verification** |
| **Integration ACS với signed SAMLResponse** | POST `SAMLResponse` đến `/login/saml2/sso/{registrationId}` | **Có**, nếu dùng provider/validator thật | IdP key, chữ ký, issuer, audience, time, subject confirmation, InResponseTo |
| **End-to-end với test IdP** | Browser redirect/AuthnRequest/callback/Session | Có | Flow federation và cấu hình proxy/cookie thực tế |
| **Security negative test** | Signed/tampered/expired/cross-audience messages | Có ở tầng integration | Fail closed khi SAML validation sai |

**Không tuyên bố rằng một test `.with(authentication(...))` chứng minh XML signature hợp lệ.** Nó tạo sẵn Spring Security `Authentication`, đúng như mục đích của mock. SAML provider không nhận `SAMLResponse` để kiểm tra lại.

Ngược lại, không cần dựng IdP và X.509 key cho mỗi test Controller chỉ muốn chứng minh “employee không được gọi API admin”. Chọn tầng test đúng giúp bộ test nhanh nhưng không tự đánh đồng unit test với SSO integration.

## 3. Phân biệt hai chữ saml2Login() hay bị gọi nhầm

### 3.1. DSL production: `HttpSecurity.saml2Login`

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
}
```

Đoạn này cấu hình Spring Security làm **SAML 2.0 Relying Party/Service Provider**. Nó cần `RelyingPartyRegistrationRepository` được định nghĩa hoặc auto-configured, IdP metadata/verification certificates, entity ID và ACS endpoint; khi browser login sẽ có redirect/AuthnRequest/Response/Assertion.

### 3.2. MockMvc: không có built-in saml2Login post-processor trong 6.5

Trong Spring Security Test 6.5, những factory quen thuộc gồm:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.*;

user("alice");                 // UsernamePasswordAuthenticationToken
oauth2Login();                 // OAuth2AuthenticationToken / OAuth2User
oidcLogin();                   // OIDC principal
jwt();                         // JwtAuthenticationToken
authentication(myAuthentication); // Authentication tùy biến
securityContext(myContext);       // SecurityContext tùy biến
```

Đây là **mảnh minh họa API**, không phải file Java hoàn chỉnh. Không có factory chuẩn để viết:

```java
// SAI nếu chỉ có spring-security-test 6.5:
mvc.perform(get("/api/me").with(saml2Login()));
```

Điều đúng, không phụ thuộc thư viện helper ngoài:

```java
Saml2Authentication saml = createSamlFixture(...);

mvc.perform(get("/api/me")
        .with(authentication(saml)));
```

Nếu dự án của bạn có helper tự viết tên `saml2Login()`, nó nên **trả một `RequestPostProcessor` dùng `authentication(...)`**, và tên/phạm vi helper phải được ghi rõ. Không import nhầm `oidcLogin()` để giả user SAML.

## 4. Các lớp Spring Security cần nắm

| Class/interface | Package rút gọn | Trách nhiệm |
| --- | --- | --- |
| `Saml2Authentication` | `...saml2.provider.service.authentication` | Authenticated SAML token, principal, response XML, authorities |
| `Saml2AuthenticationToken` | Cùng package | Input token có SAMLResponse **chưa được verify**, dùng trong authentication pipeline |
| `Saml2AuthenticatedPrincipal` | Cùng package | Principal SAML: `getName()`, `getAttributes()`, `getAttribute()`, `getFirstAttribute()`, registration |
| `DefaultSaml2AuthenticatedPrincipal` | Cùng package | Implementation tiện cho **fixture/test** và Spring Security 6.x |
| `SimpleGrantedAuthority` | `org.springframework.security.core.authority` | Một authority như `ROLE_EMPLOYEE` |
| `SecurityMockMvcRequestPostProcessors.authentication` | `org.springframework.security.test.web.servlet.request` | Gắn arbitrary `Authentication` vào MockMvc request |
| `@AuthenticationPrincipal` | `org.springframework.security.core.annotation` | Inject principal của current request vào controller |
| `@WithMockUser` | `spring-security-test` | Giả user thường, **không tự cung cấp attributes SAML** |
| `RelyingPartyRegistration` | `...saml2.provider.service.registration` | Hợp đồng giữa SP và IdP, issuer/keys/ACS/entity IDs |
| `OpenSaml4AuthenticationProvider` hoặc `OpenSaml5AuthenticationProvider` | Theo phiên bản | Xử lý/validate SAML XML của luồng thật |

Ở **Spring Security 6.5**, `DefaultSaml2AuthenticatedPrincipal` có constructor `(String name, Map<String,List<Object>> attributes)` và method `setRelyingPartyRegistrationId(String)`. Khi tạo `Saml2Authentication`, tham số thứ ba là **Collection of GrantedAuthority**, không phải một Map `roles`.

Chú ý nâng cấp: nhánh **Spring Security 7.1.x** đánh dấu `Saml2AuthenticatedPrincipal` và `DefaultSaml2AuthenticatedPrincipal` là deprecated và chuyển hướng tới `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication` cho một số use cases. **Không sao chép code 6.5 sang 7.1 một cách máy móc**; ghim version và xem migration guide.

## 5. Cấu trúc dữ liệu SAML trong principal

Sau khi SAML Response được xác minh, một SAML principal có thể có:

```text
name / NameID      = idp-user-1001
registrationId     = corp
attributes:
  email            = [alice@example.test]
  department       = [engineering]
  groups           = [reports, employees]
  employeeNumber   = [E-1001]
authorities:
  ROLE_EMPLOYEE
  REPORT_READ
```

Ba khái niệm **khác nhau**:

- `principal.getName()`: thường từ **SAML NameID** hoặc tên tùy biến theo provider/policy. Không nhất thiết là email hoặc username nội bộ.
- `principal.getAttributes()`: `Map<String,List<Object>>` từ SAML AttributeStatement; một attribute có thể **nhiều giá trị**.
- `authentication.getAuthorities()`: **Spring Security GrantedAuthority** dùng để quyết định `hasRole`/`hasAuthority`; không tự đồng nhất mọi giá trị nhóm của IdP thành roles của app.

Ví dụ `groups=[admins]` trong một SAML attribute **không tự cấp `ROLE_ADMIN`**. Việc map groups → authorities phải nằm ở converter/policy server-side đã xác minh issuer/registration/tenant và local entitlements.

### Identity của NameID

Một NameID có thể là transient/persistent ID, email format hoặc format do IdP thỏa thuận. Đừng ép `getName()` thành email nếu hệ thống dùng opaque persistent NameID. Nếu app cần local user, tạo mapping đáng tin:

```text
verified IdP issuer + registration + SAML NameID
           |
           v
local identity link / provisioning
           |
           v
local userId + active status + tenant memberships
           |
           v
business roles/permissions/ACL
```

## 6. Dependency cho ví dụ

Với một dự án **Spring Boot 3.x, Java 17+, Spring Security 6.5.x** có Gradle plugin/BOM tương ứng:

```groovy
repositories {
    mavenCentral()
    // Tùy OpenSAML dependency, repository Shibboleth có thể cần thiết.
    maven { url "https://build.shibboleth.net/maven/releases/" }
}

dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-saml2-service-provider"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.security:spring-security-test"
}
```

Đây là **mảnh `build.gradle`**, không gồm plugins/BOM/Java toolchain, nên không phải build file độc lập. Spring Boot dependency management phải chọn tập version tương thích; tránh ép `spring-security-test` bản 7 nếu runtime Spring Security 6.5.

Nếu dùng Maven, thêm các artifact tương đương, để BOM quản lý version. Không đưa IdP private key hoặc production SAMLResponse vào repository test.

Kiểm tra dependency versions:

```bash
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-saml2-service-provider \
  --configuration testRuntimeClasspath
```

## 7. Tạo SAML fixture thủ công cho MockMvc

Đây là **mảnh Java đầy đủ của một helper class** dùng trong `src/test/java/demo/saml/SamlFixtures.java`. Tất cả attributes được khai báo là `Map<String,List<Object>>`; authorities là các `GrantedAuthority` của Spring Security:

```java
package demo.saml;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication
        .DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2Authentication;

public final class SamlFixtures {

    private SamlFixtures() {
    }

    public static Saml2Authentication authenticated(
            String name,
            String registrationId,
            Map<String, List<Object>> attributes,
            String... authorityNames) {

        Map<String, List<Object>> copied = new LinkedHashMap<>();
        attributes.forEach((key, values) ->
                copied.put(key, List.copyOf(values)));

        DefaultSaml2AuthenticatedPrincipal principal =
                new DefaultSaml2AuthenticatedPrincipal(name, copied);
        principal.setRelyingPartyRegistrationId(registrationId);

        Collection<GrantedAuthority> authorities = new ArrayList<>();
        for (String roleOrPermission : authorityNames) {
            authorities.add(new SimpleGrantedAuthority(roleOrPermission));
        }

        // Dữ liệu XML chỉ là dummy string: .with(authentication(...))
        // KHÔNG parse nó, KHÔNG chạy OpenSAML hay verify signature.
        String unverifiedTestXml = "<test-only-not-saml-response/>";
        return new Saml2Authentication(
                principal, unverifiedTestXml, authorities);
    }

    public static Map<String, List<Object>> aliceAttributes() {
        return Map.of(
                "email", List.of((Object) "alice@example.test"),
                "department", List.of((Object) "engineering"),
                "groups", List.of((Object) "reports", "employees"));
    }
}
```

Lưu ý: import Java không thể tách **một qualified class name** thành hai dòng như một Java token. Khi copy vào IDE, hai import `org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal` và `...Saml2Authentication` ở trên phải nằm trọn trên mỗi dòng. Có thể viết lại đúng:

```java
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
```

**Quy tắc fixture:**

1. Tạo principal có **NameID**, attributes và registrationId đúng use case.
2. Tạo authorities riêng; không suy ra chúng từ attributes khi đang viết mock controller test.
3. Dùng XML dummy chỉ vì test không chạy SAML provider; không dùng payload đó gửi vào ACS.
4. Không sao chép production SAMLResponse/NameID/session vào fixture.
5. Nếu app đổi principal type khi nâng lên Security 7.1, fixture phải theo type được app thật sử dụng.

### Một fixture Alice

```java
Saml2Authentication alice = SamlFixtures.authenticated(
        "idp-user-1001",
        "corp",
        SamlFixtures.aliceAttributes(),
        "ROLE_EMPLOYEE",
        "REPORT_READ");
```

`alice.getName()` trả `idp-user-1001`. `getPrincipal()` là SAML principal; `getAuthorities()` chứa `ROLE_EMPLOYEE` và `REPORT_READ`, **không chứa `ROLE_ADMIN`**.

## 8. Controller Spring Boot đọc principal và attributes

Ví dụ API/controller trong `src/main/java/demo/saml/ProfileController.java`:

```java
package demo.saml;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        String email = principal.getFirstAttribute("email");
        List<Object> groups = principal.getAttribute("groups");
        String registrationId = principal.getRelyingPartyRegistrationId();

        return Map.of(
                "name", principal.getName(),
                "email", email == null ? "" : email,
                "registrationId", registrationId == null ? "" : registrationId,
                "groupCount", groups == null ? 0 : groups.size());
    }

    @GetMapping("/api/admin")
    public String admin(Authentication authentication) {
        return "admin=" + authentication.getName();
    }

    @GetMapping("/api/reports/{tenant}")
    public Map<String, String> reports(
            @PathVariable String tenant,
            Authentication authentication) {

        // DEMO: không tin tenant lấy từ request hoặc SAML claims
        // khi chưa map sang local user/tenant membership.
        String localTenant = switch (authentication.getName()) {
            case "idp-user-1001" -> "north";
            case "idp-ops-1002" -> "north";
            default -> "none";
        };

        if (!tenant.equals(localTenant)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return Map.of("tenant", tenant, "status", "visible");
    }
}
```

Tương tự mục 7, import bị xuống dòng trong khối này cần viết thành **một dòng Java**:

```java
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
```

Khi lấy attributes:

- `getFirstAttribute("email")` có thể trả null nếu attribute không tồn tại.
- `getAttribute("groups")` trả danh sách các values, **không phải `String` duy nhất**.
- `getName()` không nhất thiết giống email.
- `getRelyingPartyRegistrationId()` xác định registration nguồn trong phiên bản 6.5.
- `Authentication.getAuthorities()` dùng cho authorization; không map role từ chuỗi raw untrusted trong controller.

Nếu một endpoint cho phép authenticated principal không phải SAML (ví dụ OIDC login), `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` có thể null. Cần tách routes/filter chains hoặc dùng code xử lý đa auth types thay vì để NullPointerException.

## 9. Cấu hình production saml2Login() và HTTP authorization

Một `SecurityFilterChain` Java 17+, chạy cùng project Spring Boot Servlet:

```java
package demo.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain samlWeb(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAuthority("REPORT_READ")
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyRequest().denyAll())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
```

**Cấu hình này cần `RelyingPartyRegistrationRepository` thật** mới đăng nhập được. Ví dụ trong test slice bên dưới **không dựng SAML Login filter**, vì nó chỉ kiểm tra authorization của request đã authenticated; test production config/ACS phải nằm ở tầng integration khác.

`hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`. `hasAuthority("REPORT_READ")` kiểm tra chính xác `REPORT_READ`, **không tự thêm `ROLE_`**. Vì vậy một test fixture dùng `ROLE_EMPLOYEE` không được phép gọi `/api/admin`, còn fixture có `REPORT_READ` sẽ qua URL guard của `/api/reports/**` nhưng còn local tenant checks.

### Cấu hình IdP/RP minh họa

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://sp.example.test/saml2/metadata/corp"
            acs:
              location: "https://sp.example.test/login/saml2/sso/corp"
            assertingparty:
              metadata-uri: "https://idp.example.test/metadata"
```

Metadata URL ở `example.test` là placeholder không tồn tại; để chạy phải dùng test IdP/metadata thật, kiểm tra trust anchors/certificates, issuer/audience, ACS và cookie/SAML request repository. Không thay metadata URI bằng URL bất kỳ do user truyền vào.

## 10. MockMvc: cấu hình test slice không phụ thuộc IdP

Để test `ProfileController` và quyền URL mà không cần gọi IdP, dùng `@WebMvcTest` với **Test-only SecurityFilterChain**. Nó bảo vệ các routes như production nhưng **không cấu hình `saml2Login`/IdP** trong test slice; principal SAML được đưa vào bằng `spring-security-test`. Phân biệt rõ đây là **authorization test**, không phải test wiring của production SAML login.

Lưu `src/test/java/demo/saml/ProfileControllerTest.java`:

```java
package demo.saml;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ProfileController.class)
@Import(ProfileControllerTest.TestAuthorizationSecurity.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestAuthorizationSecurity {
        @Bean
        SecurityFilterChain testsOnly(HttpSecurity http) throws Exception {
            return http
                    .authorizeHttpRequests(auth -> auth
                            .requestMatchers(HttpMethod.GET, "/api/admin")
                                .hasRole("ADMIN")
                            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                                .hasAuthority("REPORT_READ")
                            .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                            .anyRequest().denyAll())
                    .exceptionHandling(ex -> ex
                            .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                    HttpStatus.UNAUTHORIZED)))
                    .build();
        }
    }

    @Test
    void aliceHasSamlNameIdAndMultivaluedAttributes() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/me").with(authentication(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("idp-user-1001"))
                .andExpect(jsonPath("$.email").value("alice@example.test"))
                .andExpect(jsonPath("$.registrationId").value("corp"))
                .andExpect(jsonPath("$.groupCount").value(2));
    }

    @Test
    void employeeCannotCallAdmin() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/admin").with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleIsExplicit() throws Exception {
        var ops = SamlFixtures.authenticated(
                "idp-ops-1002", "corp",
                Map.of("email", List.of((Object) "ops@example.test")),
                "ROLE_EMPLOYEE", "ROLE_ADMIN", "REPORT_READ");

        mvc.perform(get("/api/admin").with(authentication(ops)))
                .andExpect(status().isOk())
                .andExpect(content().string("admin=idp-ops-1002"));
    }

    @Test
    void aliceCannotReadSouthTenant() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/reports/south")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanReadNorthTenant() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/reports/north")
                .with(authentication(alice)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("north"));
    }

    @Test
    void noSamlAuthenticationIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingReportAuthorityIsForbidden() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE");

        mvc.perform(get("/api/reports/north")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }

    @Test
    void forgedHeaderDoesNotGrantAdminRole() throws Exception {
        var alice = SamlFixtures.authenticated(
                "idp-user-1001", "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ");

        mvc.perform(get("/api/admin")
                .header("X-Role", "ROLE_ADMIN")
                .with(authentication(alice)))
                .andExpect(status().isForbidden());
    }
}
```

**Các static imports rút xuống dòng cho dễ trình bày cần được đưa về một dòng khi tạo source thực.** Bốn dòng đúng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
```

Bộ test sử dụng `spring-security-test` với `@WebMvcTest` auto-configured `MockMvc` và filter chain. Nếu dùng `MockMvcBuilders.standaloneSetup` riêng, phải gọi `.apply(springSecurity())` hoặc tích hợp Spring Security FilterChainProxy đúng cách.

### Điều kiện để chạy

- Các class `SamlFixtures` và `ProfileController` phải có package và đường dẫn như trên.
- Test dependencies phải chứa JUnit Jupiter, Spring Boot Test, Spring Security Test và Spring SAML service provider.
- Test slice phải dùng test `SecurityFilterChain` ở trên, **không** tự scan production chain có yêu cầu IdP metadata thật.
- Nếu app có thêm filters/beans qua global imports, cần cô lập test context đúng, không cho test tự tải external IdP.
- Test ở đây **không parse XML dummy**, đúng vì nó test controller/authorization.

Lệnh chạy trong project Gradle đã cấu hình:

```bash
./gradlew test --tests "demo.saml.ProfileControllerTest"
```

Khi dependencies và slice wiring đúng, tám tests bên trên xác nhận 200/401/403, principal/attributes/roles/tenant. Không in stdout cố định của test runner vì nó phụ thuộc Gradle/JUnit version và build output.

## 11. Giải thích getFirstAttribute và getAttribute

Một SAML AttributeStatement có thể chứa:

```xml
<saml:Attribute
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Name="groups">
  <saml:AttributeValue>reports</saml:AttributeValue>
  <saml:AttributeValue>employees</saml:AttributeValue>
</saml:Attribute>
```

Sau khi IdP signature và SAML response được verify, `DefaultSaml2AuthenticatedPrincipal` trong Spring 6.5 có thể expose:

```java
List<Object> groups = principal.getAttribute("groups");
Object first = principal.getFirstAttribute("groups");
Map<String, List<Object>> all = principal.getAttributes();
```

Với fixture ở trên:

```text
groups=[reports, employees]
first=reports
```

**Không ép mọi attribute vào một String**. Với missing attribute, `getFirstAttribute` có thể trả `null`; một attribute multi-valued cần xử lý tất cả values hoặc policy chọn thứ nhất rõ ràng. Nếu attribute là custom XML/SAML value không phải String, cần parse/convert theo contract; không cast liều sang String.

### Trùng key/namespace

SAML attributes có Name và có thể có NameFormat/FriendlyName. Spring mapping có thể dùng `Attribute.Name` làm key; IdP khác có thể phát URL/URN thay tên ngắn `email` hoặc `groups`. Ví dụ:

```text
http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
urn:oid:0.9.2342.19200300.100.1.3
email
mail
```

Chỉ nên normalize những attribute names được **thỏa thuận trong profile của đúng IdP/registration**. Đừng dùng fallback “nếu bất kỳ attribute nào có chữ admin thì cấp ROLE_ADMIN”.

## 12. Tùy chỉnh principal name: NameID, email, employeeId

`DefaultSaml2AuthenticatedPrincipal` trong test nhận `name` trực tiếp. Bạn có thể giả lập:

```java
var principalByNameId = new DefaultSaml2AuthenticatedPrincipal(
        "opaque-nameid-981",
        Map.of("email", List.of((Object) "alice@example.test")));

var principalByLocalId = new DefaultSaml2AuthenticatedPrincipal(
        "local-user-42",
        Map.of("email", List.of((Object) "alice@example.test")));
```

Hai fixtures cho cùng email nhưng **khác principal.getName()**. Tests nên phản ánh đúng converter runtime. Nếu production giữ NameID, không viết unit test giả `getName()==email` chỉ cho thuận tiện: test sẽ che bug mapping.

### Tùy biến ở runtime

Trong Spring Security 6.5/7.x, muốn đổi principal name sau SAML validation, phải sử dụng một **authentication converter/delegating provider** tương ứng release, giữ default signature/issuer/audience/recipient/time checks. Ví dụ về mặt thiết kế:

```text
Verified SAML assertion
  -> verified issuer + stable NameID
  -> local identity linking service
  -> local userId (được phép dùng làm principal name nếu policy)
  -> attributes và authorities đã chuẩn hóa
  -> Saml2Authentication / application-specific Authentication
```

Đừng dùng một converter nhìn vào **XML chưa verify** rồi đặt principal thành `request.getParameter("email")`. Nếu muốn mapping principal name trong Spring Security 7.1, xem `ResponseAuthenticationConverter` và `Saml2ResponseAssertionAccessor`; các API mới thay thế một số phương pháp cũ ở nhánh 6.x.

## 13. RelyingPartyRegistrationId trong fixture

Với nhiều IdP hoặc nhiều tenants, `registrationId` phân biệt cấu hình:

```java
DefaultSaml2AuthenticatedPrincipal principal =
        new DefaultSaml2AuthenticatedPrincipal(
                "nameid-abc",
                Map.of("email", List.of((Object) "alice@example.test")));

principal.setRelyingPartyRegistrationId("partner-a");
```

Test một principal khác với `partner-b`, dù cùng NameID/email, **không mặc định cùng local account/role**. Mapping robust thường dựa trên **verified IdP Entity ID/issuer + NameID + registration context**, không chỉ email.

Trong test fixture, `setRelyingPartyRegistrationId("partner-a")` chỉ đặt **chuỗi**; nó không chứng minh có registration thật hoặc assertion đã ký từ đúng IdP. Assertion verification và registration lookup phải được kiểm tra ở integration tests.

## 14. Custom authorities không tự tương đương SAML attributes

Trong Spring Security:

```text
hasRole("ADMIN")     -> yêu cầu authority ROLE_ADMIN
hasAuthority("ADMIN") -> yêu cầu authority ADMIN
hasAuthority("REPORT_READ") -> yêu cầu đúng REPORT_READ
```

Test:

```java
new Saml2Authentication(
    principal,
    "<dummy/>",
    List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
            new SimpleGrantedAuthority("REPORT_READ")));
```

Không viết:

```java
// SAI: Map attributes không phải GrantedAuthorities.
Map.of("groups", List.of((Object) "admins"));
// rồi coi request được ROLE_ADMIN
```

Mặc định của provider có thể cấp một role cơ bản như `ROLE_USER`/authority đánh dấu yếu tố xác thực tùy release; các quyền business **không nên phụ thuộc đoán defaults**. Khi test business authorization, tạo chính xác bộ authorities mà **production mapper** được thiết kế cấp.

### Authority granularity

Role cấp cao: `ROLE_ADMIN`, `ROLE_EMPLOYEE`. Permission cụ thể: `REPORT_READ`, `REPORT_APPROVE`, `DOCUMENT_EXPORT`. Nếu sản phẩm dùng prefix `SCOPE_` cho OAuth Bearer, đừng tự map một SAML attribute `scope` thành `SCOPE_ADMIN` mà không có AS/local policy tương đương.

## 15. Test mapping role từ IdP groups: đừng mock cả logic cần test

Một lỗi phổ biến:

```java
// Mapper production: groups -> authorities.
// Test lại tự inject cả groups VÀ authority đã map sẵn.
.with(authentication(samlWithGroupAndAuthority("admins", "ROLE_ADMIN")));
```

Test như vậy **không chạy mapper**, nên không phát hiện bug nếu mapper production cấp ADMIN quá rộng.

Đúng là tách hai lớp:

1. **Unit test group-to-authority converter:** truyền identity/attributes **đã verify**, registration/issuer và local policy, assert roles. Ví dụ group `employee` ở partner A được `ROLE_EMPLOYEE`, còn `admin` từ partner chưa được ủy quyền **không** được admin.
2. **MockMvc authorization test:** truyền `Saml2Authentication` với authorities **đã map**, assert controller/endpoint cho phép hay từ chối.
3. **Integration test ACS:** đưa signed SAMLResponse từ IdP sandbox qua converter thật, assert authorities cuối cùng.

Nếu chỉ có MockMvc fixture, cả (1) và (3) còn chưa được kiểm tra.

### Chính sách mapping an toàn

```text
allow ADMIN =
   sourceIssuerApprovedForAdminGroup
   AND registrationMappedToCorrectTenant
   AND stableSubjectLinkedToActiveLocalUser
   AND localEntitlementGrantsAdmin
   AND optional assurance/freshness requirements met
```

Đây là **pseudocode**, không phải SpEL hoặc config Spring tự chạy. Một SAML attribute chứa chuỗi `admin` **không tự cấp quyền**.

## 16. Tùy biến principal trong tests bằng helper có tên rõ

Nếu nhóm muốn cú pháp gần giống `.with(saml2Login())`, có thể tự viết **helper** trả `RequestPostProcessor`. Nhưng để tránh gây hiểu nhầm với `HttpSecurity.saml2Login`, nên gọi `withSamlAuthentication`:

```java
package demo.saml;

import java.util.List;
import java.util.Map;

import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;

public final class CustomSamlMockMvc {

    private CustomSamlMockMvc() {
    }

    public static RequestPostProcessor withSamlAuthentication(
            String name,
            String registrationId,
            Map<String, List<Object>> attributes,
            String... authorities) {
        return authentication(SamlFixtures.authenticated(
                name, registrationId, attributes, authorities));
    }
}
```

**Static import phải ở một dòng Java hoàn chỉnh khi copy:**

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
```

Sử dụng:

```java
mvc.perform(get("/api/me")
        .with(CustomSamlMockMvc.withSamlAuthentication(
                "idp-user-1001",
                "corp",
                SamlFixtures.aliceAttributes(),
                "ROLE_EMPLOYEE", "REPORT_READ")))
        .andExpect(status().isOk());
```

Đây là **helper tự viết**; không phải Spring Security Test built-in. Nó chỉ gắn SAML-shaped authenticated principal vào SecurityContext, **không sinh AuthnRequest và không verify SAMLResponse**. Không đặt tên helper tùy tiện như một API chính thức nếu team mới vào có thể hiểu nhầm.

## 17. Với @WithMockUser: vì sao principal type lại khác?

`@WithMockUser(username="alice", roles="USER")` tạo một `UsernamePasswordAuthenticationToken` với `UserDetails`. Trong khi controller SAML có thể đòi:

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal)
```

Nếu test bằng `@WithMockUser`, principal không phải `Saml2AuthenticatedPrincipal`; Spring có thể inject null hoặc ném lỗi type-specific tùy cấu hình. Vì vậy test SAML attributes **không nên dùng `@WithMockUser` như một vật thay thế hoàn toàn**.

Với endpoint **chỉ kiểm tra hasRole** mà không phụ thuộc principal type, `@WithMockUser(roles="EMPLOYEE")` vẫn hữu ích như test chung. Nhưng khi business code gọi `getFirstAttribute("email")`, `getRelyingPartyRegistrationId()`, `getSessionIndexes()`, hoặc phân biệt IdP, cần fixture SAML đúng type.

## 18. Tạo annotation @WithMockSamlPrincipal cho test suite lớn

Ngoài request-scoped `.with(authentication(...))`, Spring Security Test hỗ trợ `@WithSecurityContext` và `WithSecurityContextFactory` để tạo một fixture dùng lại cho tests ở method/service layers.

Mảnh annotation:

```java
package demo.saml;

import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RUNTIME)
@Target({ METHOD, TYPE })
@WithSecurityContext(factory = MockSamlSecurityContextFactory.class)
public @interface WithMockSamlPrincipal {
    String name() default "idp-user-1001";
    String registrationId() default "corp";
    String[] authorities() default { "ROLE_EMPLOYEE" };
}
```

Mảnh factory:

```java
package demo.saml;

import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support
        .WithSecurityContextFactory;

public final class MockSamlSecurityContextFactory
        implements WithSecurityContextFactory<WithMockSamlPrincipal> {

    @Override
    public SecurityContext createSecurityContext(
            WithMockSamlPrincipal annotation) {

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(SamlFixtures.authenticated(
                annotation.name(),
                annotation.registrationId(),
                SamlFixtures.aliceAttributes(),
                annotation.authorities()));
        return context;
    }
}
```

Lưu ý import đầy đủ trên **một dòng**:

```java
import org.springframework.security.test.context.support.WithSecurityContextFactory;
```

Test:

```java
@Test
@WithMockSamlPrincipal(
        name = "idp-user-1001",
        registrationId = "corp",
        authorities = { "ROLE_EMPLOYEE", "REPORT_READ" })
void myServiceSeesSamlPrincipal() {
    // Service-under-test dùng SecurityContextHolder
    // với principal/authorities SAML giả lập.
}
```

**Giới hạn của helper annotation này:** nó dùng `aliceAttributes()` cố định cho mọi subject. Trong dự án thực hãy cho phép cấu hình email/groups/tenant hoặc sử dụng nhiều fixture builders; không dùng Alice email cho principal Bob rồi kết luận account linking đúng. `WithSecurityContextFactory` tạo context test, **không xác thực XML hoặc IdP**.

## 19. Khi nào dùng authentication(...) và khi nào dùng securityContext(...)

Hai cách:

```java
mvc.perform(get("/api/me")
        .with(authentication(mySamlAuthentication)));
```

và:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(mySamlAuthentication);

mvc.perform(get("/api/me")
        .with(securityContext(context)));
```

`authentication(...)` gọn khi chỉ muốn gắn principal/authorities cho một request. `securityContext(...)` linh hoạt hơn khi cần kiểm tra custom details, custom Authentication hoặc context đặc thù.

**Phải cấu hình MockMvc với Spring Security integration**. Với `@WebMvcTest` + `@AutoConfigureMockMvc`/Spring Boot auto-config, filter chain thường được kết nối. Khi tự tạo MockMvc bằng `MockMvcBuilders`, tài liệu chính thức chỉ rõ:

```java
mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Nếu bỏ integration này, `authentication(...)` có thể không được chuyển vào `SecurityContextHolder` theo cách controller/service mong đợi. Không đặt `SecurityContextHolder.setContext(...)` trong test method rồi quên clear sau test; dễ rò user sang các tests khác. Dùng request post-processor hoặc `@WithSecurityContext`.

## 20. @AuthenticationPrincipal so với Authentication.getPrincipal()

Ở controller:

```java
@GetMapping("/api/whoami")
public String whoami(
        Authentication authentication,
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    return authentication.getName() + "|" + principal.getName();
}
```

`Authentication` expose name, authorities, details và token type. `@AuthenticationPrincipal` lấy **principal object**. Với `Saml2Authentication` trong Spring Security 6.5, principal thường là `Saml2AuthenticatedPrincipal`; name có thể khớp `Saml2Authentication.getName()`.

Nhưng không phải mọi authentication provider đều giữ cùng principal type sau custom conversion; có hệ thống wrap principal thành local `UserDetails` hoặc domain-specific object. Vì vậy trước khi viết controller, quyết định contract:

- Controller SAML-specific: nhận `Saml2AuthenticatedPrincipal`, chỉ gọi ở SAML-protected routes.
- Controller đa giao thức: nhận `Authentication` hoặc local domain principal đã chuẩn hóa.
- Business services: nên nhận **local user ID + permissions**, tránh phụ thuộc trực tiếp XML/IdP NameID.

### Những lỗi null và generic type thường gặp

```java
String email = principal.getFirstAttribute("email");
List<Object> groups = principal.getAttribute("groups");
```

`getFirstAttribute` có thể null; nếu group attribute chứa giá trị kiểu khác String, đừng cast trực tiếp `(String) groups.get(0)` mà chưa kiểm tra type. Nếu muốn debug, log **tên các attributes**, không dump nguyên assertion hoặc PII.

## 21. Kiểm thử multiple attributes và multi-valued groups

Đừng chỉ test đúng một value. Một IdP có thể trả:

```text
groups = [engineering, reports, beta-testers]
department = [platform]
email = [alice@example.test]
employeeId = []
```

Nên kiểm tra:

1. Attribute có một value.
2. Attribute có nhiều values và đúng thứ tự/định dạng nếu business contract cần.
3. Attribute thiếu hẳn → xử lý null/empty đúng.
4. Attribute tồn tại nhưng empty list.
5. Attribute không phải String → parser/mapper không throw ClassCastException.
6. Có hai attribute keys cùng FriendlyName nhưng Name khác → chỉ dùng attribute name được contract cho phép.
7. Đặc thù IdP A dùng URI attribute name, IdP B dùng `email` → tránh mapping nhầm.
8. Business group-to-authority mapper không cấp quyền quá rộng nếu giá trị là `admins` từ issuer chưa được phê duyệt.

**Fixture đúng dữ liệu** không làm các nhóm đó trở nên tin cậy. Chỉ khi integration SAML đã verify IdP signature/issuer, mapper runtime mới có thể dùng claims theo policy.

## 22. Method security và @PreAuthorize

Trong ứng dụng production:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Service:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_APPROVE')")
    public void approve(String reportId) {
        // Business validation, tenant/ownership và transaction cần bổ sung.
    }
}
```

Để test `@PreAuthorize` thực sự, service phải là **Spring-managed proxy** và `@EnableMethodSecurity` hoạt động trong test context. Nếu bạn gọi `new ReportService().approve(...)`, method authorization aspect **không chạy**.

Một unit test with `@WithMockSamlPrincipal`/`@WithSecurityContext` có thể tạo authorities phù hợp, nhưng test phải boot context đủ để gọi bean thật đã proxy. Hoặc dùng `MockMvc` gọi controller được bảo vệ bằng service method. Không đánh đồng route `hasAuthority` với business object ACL: muốn chống BOLA/IDOR cần kiểm tra quyền trên reportId/tenant.

### Kiểm thử quyền deny

- Employee chỉ có `REPORT_READ` gọi `approve` → AccessDeniedException/403 theo tầng test.
- Approver có `REPORT_APPROVE` nhưng report thuộc tenant khác → vẫn deny bởi local tenant/resource check.
- IdP group `approvers` nhưng local account disabled → fail-closed.
- Machine token/Bearer API không tự được coi như SAML user.

## 23. MockMvc kiểm tra HTTP 401, 403 và redirect

Với **test-only chain** ở mục 10, `HttpStatusEntryPoint(UNAUTHORIZED)` tạo HTTP 401 cho anonymous test; user authenticated nhưng thiếu authority trả 403.

Ở **production SAML chain**, request anonymous vào protected URL thường có thể:

1. Trả redirect tới trang chọn IdP/login.
2. Tiếp tục redirect tới `/saml2/authenticate/{registrationId}` và IdP.
3. Sau successful SSO tạo application session.

Vì vậy **không khẳng định mọi anonymous request production phải 401**. HTTP status phụ thuộc entry point/configuration; test controller authorization slice có entry point 401 chỉ để tạo assertion ổn định.

### Kiểm tra contract theo tầng

| Kịch bản | Authorization slice | Real SAML login |
| --- | --- | --- |
| Không có Authentication | 401 theo test entrypoint | Redirect login/IdP theo config |
| Authenticated thiếu role | 403 | 403 nếu SAML valid nhưng thiếu role |
| Mock SAML principal đủ role | 200 | Không tương đương signed SAMLResponse |
| Signed Response sai audience | Chưa kiểm tra | Provider phải reject |
| Signed Response sai issuer/key | Chưa kiểm tra | Provider phải reject |
| CSRF thiếu ở business POST | Nếu CSRF bật, 403 | Web CSRF policy phải hoạt động |

## 24. CSRF trong kiểm thử SAML2 và business POST

SAML ACS thường là `POST /login/saml2/sso/{registrationId}` mang `SAMLResponse` từ browser/IdP. Spring Security SAML login DSL có cơ chế để xử lý callback mà **không cần CSRF token ứng dụng thông thường** tại endpoint protocol, còn chữ ký/issuer/recipient/InResponseTo/OneTimeUse là phòng tuyến riêng.

**Không tắt CSRF toàn ứng dụng** chỉ để cho SAML POST chạy được. Business endpoints dùng session cookie vẫn có nguy cơ CSRF.

Ví dụ test một POST nghiệp vụ:

```java
mvc.perform(post("/api/reports/approve")
        .with(authentication(approver))
        .with(csrf()))
    .andExpect(status().isOk());
```

Đoạn trên yêu cầu đã có controller/URL rule cho route này và imports `post`/`csrf`; nó **không khởi tạo SAML login**. Nếu gọi cùng POST không `csrf()` với CSRF mặc định bật, test kỳ vọng bị từ chối (thường 403) trước authorization/business logic.

`with(csrf())` chỉ tạo CSRF token test; nó **không ký SAML Response**, không có quan hệ với `SAMLRequest`/`RelayState`.

## 25. Tầng Integration: POST SAMLResponse có chữ ký qua ACS

Để chứng minh SAML federation end-to-end, phải dùng **real SAML response payload được ký bởi test IdP key** với `RelyingPartyRegistration` tin test certificate. Các bước:

1. Cấu hình một test IdP riêng và RP metadata/IdP signing certificate ở application test profile.
2. Bắt đầu SP-initiated flow để `Saml2AuthenticationRequestRepository` lưu pending AuthnRequest.
3. IdP sandbox tạo Response có `Response.ID`, `Assertion.ID`, `Issuer`, `Destination`, `AudienceRestriction`, `SubjectConfirmationData.InResponseTo` và timing hợp lệ.
4. Ký Response/Assertion theo trust contract, mã hóa Base64 khi gửi HTTP-POST.
5. Gửi POST về ACS trong **browser/session phù hợp** cùng RelayState khi có.
6. Kiểm tra HTTP login outcome, SecurityContext, principal name, attributes, authorities và session cookie.
7. Gửi phản hồi chữ ký sai/expired/replayed/wrong audience, khẳng định fail closed.

Mảnh MockMvc request **chỉ minh họa** cách gửi response thật, không tự tạo chữ ký:

```java
mvc.perform(post("/login/saml2/sso/corp")
        .param("SAMLResponse", signedFixtureBase64)
        .param("RelayState", pendingRelayState)
        .session(initiatingBrowserSession))
    .andExpect(status().is3xxRedirection());
```

`signedFixtureBase64`, `pendingRelayState` và `initiatingBrowserSession` phải đến từ **test harness** được thiết lập đúng, không phải các chuỗi random. Không tạo XML unsigned, Base64 encode rồi kỳ vọng Spring Security accept. Trong integration, có thể thấy redirect đến error page ngay cả khi status 302; cần assert **authentication success handler/state thật**, không chỉ kiểm tra 3xx.

### Những negative fixtures quan trọng

- Response không có chữ ký theo policy.
- Chữ ký dùng khóa không nằm trong trusted IdP certs.
- Signed XML được sửa sau khi ký.
- Issuer không khớp registration.
- Audience không khớp SP Entity ID.
- Recipient/Destination khác ACS.
- Assertion expired/NotBefore tương lai.
- InResponseTo sai hoặc AuthnRequest đã consumed.
- Replay Response.ID/Assertion.ID.
- XML Signature Wrapping hoặc duplicate XML IDs.
- Multi-tenant/IdP registration mismatch.
- Account disabled dù SAML assertion hợp lệ.

MockMvc `authentication(...)` **không thể phát hiện** các lỗi này vì đã bypass SAML provider. Phải có signed integration tests riêng.

## 26. Không dùng Saml2AuthenticationToken thay Saml2Authentication fixture

Hai lớp không tương đương:

```java
Saml2AuthenticationToken tokenBeforeValidation = ...; // chưa verify
Saml2Authentication afterValidation = ...;             // authenticated
```

`Saml2AuthenticationToken` đại diện SAMLResponse inbound chưa xác minh, `isAuthenticated()` là false. `Saml2Authentication` đại diện kết quả đã verified trong production, còn ở test có thể **được tạo bằng fixture**.

Không dùng `Saml2AuthenticationToken` trong MockMvc `.with(authentication(...))` rồi mong `authenticated()`/`hasRole` hoạt động như authenticated principal SAML; và càng không gọi `setAuthenticated(true)` trên token chưa verify để “làm test qua”.

Ở application thật, chỉ OpenSAML provider/AuthenticationManager sau khi kiểm tra signature, conditions, audience, issuer và subject confirmation mới nên phát authenticated token. Test fixture là ngoại lệ **chỉ tồn tại trong test scope**.

## 27. @WithSecurityContextFactory và lifecycle của SecurityContext

Một custom annotation test có thể đặt `SecurityContext` ở đầu một method:

```text
@BeforeTestExecution:
  TestSecurityContextHolder chứa Saml2Authentication fixture

Test:
  Controller/Service nhìn thấy fixture khi Spring Security Test tích hợp đúng

After test:
  SecurityContext được cleanup bởi test infrastructure
```

Nếu tự gọi `SecurityContextHolder.setAuthentication(...)` mà không dùng Spring Security Test, context `ThreadLocal` có nguy cơ rò sang test sau, đặc biệt khi test runner reuse threads.

**Tốt nhất** cho MockMvc từng request là `.with(authentication(saml))`. Với method-security tests có nhiều lời gọi trong một test, `@WithMockSamlPrincipal`/factory riêng tiện hơn. Khi chuyển sang Security 7.1, interface principal có deprecation, nên cô lập fixture factory tại một file để nâng cấp tập trung.

## 28. Tách SAML registration và multi-tenant tests

Hệ thống có:

```text
registrationId=corp, issuer=https://idp.corp.example.test
registrationId=partner, issuer=https://idp.partner.example.test
```

Một principal có email trùng nhau ở hai IdPs không tự là cùng local user:

```text
(corp,   NameID=A123, email=alice@example.test)
(partner,NameID=B777, email=alice@example.test)
```

Test cases:

1. Assert đúng `registrationId` của principal sau SAML login.
2. Assert mapping user local theo issuer + stable NameID, không chỉ email.
3. Assert partner group `admin` không cấp `ROLE_ADMIN` ở tenant corp.
4. Assert `/api/reports/north` deny user chỉ thuộc South.
5. Assert disabled local account fail closed dù IdP có signed assertion mới.
6. Assert SAMLResponse Issuer B gửi vào ACS corp bị từ chối trong integration.
7. Assert request repository/RelayState không nối sai browser/tenant.

Mock fixture có thể đặt registrationId tùy ý, nên **không dùng MockMvc auth fixture để chứng minh issuer-to-registration signature validation**.

## 29. Production mapping authorities từ verified SAML assertions

Trong Spring Security 6.x, tùy release/provider, có các extension points để customize **response authentication converter**, hoặc bọc/delegate kết quả từ provider sau validation:

```text
OpenSAML validates Response/Assertion:
  signature + trusted issuer + destination/recipient
  + audience + subject confirmation + time + InResponseTo

Default response authentication conversion:
  verified NameID + SAML Attributes + base authorities

Application enrichment:
  verify local account link and tenant membership
  map approved attributes/groups to local permissions
  preserve trusted principal and avoid privilege escalation

Result:
  Saml2Authentication (or approved custom Authentication)
```

**Không tắt default validation để thêm claims hoặc authorities.** Nếu cần tạo `Saml2Authentication` mới sau conversion trong Security 6.x, vẫn phải dùng validated principal/response và local policy. Tránh giữ raw SAMLResponse trong logs để debug converter.

Các API chính xác khác nhau giữa `OpenSaml4AuthenticationProvider` của một số release 6.x, `OpenSaml5AuthenticationProvider` của 6.5/7.x và `ResponseAuthenticationConverter` của nhánh 7.1. Hãy dùng Javadoc của BOM đang chạy thay vì copy lẫn lambda types `ResponseToken`/`AssertionToken`/`Saml2ResponseAssertionAccessor`.

### Bảo vệ multi-valued group mapping

Map nhóm IdP sang role không được hoạt động bằng substring:

```text
groups contains "admin" -> ROLE_ADMIN  // nguy hiểm
```

Thay bằng phép khớp chính xác với allowlist issuer + group ID:

```text
if verifiedIssuer == approvedCorpIdp
   AND groups contains exact configured group identifier
   AND localUser.active == true
   AND localUser.hasEntitlement("admin"):
       grant ROLE_ADMIN
```

Đây là pseudocode, không phải SpEL runnable. Tests cho role mapper phải include `groups=["administered-project"]` và bảo đảm **không** cấp admin do substring.

## 30. Java 17 độc lập: chính sách principal, attributes và authorities

Để có một ví dụ **chạy được không cần Spring/IdP**, chương trình mô phỏng sau tạo principal đã được xác minh và áp chính sách trên email, registration, roles và tenant. Nó **không verify SAML XML**, không thay code Spring Security; chỉ giúp hiểu cách danh tính và quyền có tác dụng khác nhau.

Lưu `SamlPrincipalPolicyDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class SamlPrincipalPolicyDemo {

    record Principal(
            String nameId,
            String registrationId,
            Map<String, List<String>> attributes,
            Set<String> authorities,
            String localTenant) {
    }

    static String firstAttribute(Principal principal, String key) {
        List<String> values = principal.attributes().get(key);
        return (values == null || values.isEmpty()) ? "" : values.get(0);
    }

    static boolean canRead(Principal principal, String tenant) {
        return principal != null
                && "corp".equals(principal.registrationId())
                && principal.authorities().contains("REPORT_READ")
                && principal.localTenant().equals(tenant);
    }

    static boolean canAdmin(Principal principal) {
        return principal != null
                && "corp".equals(principal.registrationId())
                && principal.authorities().contains("ROLE_ADMIN");
    }

    public static void main(String[] args) {
        Principal alice = new Principal(
                "idp-user-1001", "corp",
                Map.of(
                        "email", List.of("alice@example.test"),
                        "groups", List.of("reports", "employees")),
                Set.of("ROLE_EMPLOYEE", "REPORT_READ"),
                "north");

        Principal partner = new Principal(
                "partner-999", "partner",
                Map.of(
                        "email", List.of("alice@example.test"),
                        "groups", List.of("admins")),
                Set.of("ROLE_EMPLOYEE"), "south");

        System.out.println("nameId=" + alice.nameId());
        System.out.println("email=" + firstAttribute(alice, "email"));
        System.out.println("groupCount="
                + alice.attributes().get("groups").size());
        System.out.println("missingAttribute="
                + firstAttribute(alice, "employeeNumber").isEmpty());
        System.out.println("aliceCanReadNorth=" + canRead(alice, "north"));
        System.out.println("aliceCanReadSouth=" + canRead(alice, "south"));
        System.out.println("aliceIsAdmin=" + canAdmin(alice));
        System.out.println("partnerIsAdmin=" + canAdmin(partner));
        System.out.println("sameEmailDifferentIdentity="
                + !alice.nameId().equals(partner.nameId()));
    }
}
```

Chạy Java 17+:

```bash
javac SamlPrincipalPolicyDemo.java
java SamlPrincipalPolicyDemo
```

Stdout **chính xác**:

```text
nameId=idp-user-1001
email=alice@example.test
groupCount=2
missingAttribute=true
aliceCanReadNorth=true
aliceCanReadSouth=false
aliceIsAdmin=false
partnerIsAdmin=false
sameEmailDifferentIdentity=true
```

Đây là Java SE demo có output xác định, tách hoàn toàn khỏi SAML provider. `SamlFixtures` trong mục 7 là Spring-specific fixture có semantics tương tự, nhưng test nó qua MockMvc đòi Spring Boot/Security dependencies.

## 31. Kiểm thử account linking, role và tenant trên nhiều thuộc tính

Một tập case hữu ích:

| Case | NameID | Registration | Attributes | GrantedAuthority | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| Alice employee | A123 | corp | email, groups reports | ROLE_EMPLOYEE/REPORT_READ | Me=200, reports north=200, admin=403 |
| Alice thiếu email | A123 | corp | groups reports | ROLE_EMPLOYEE | Me xử lý empty/email missing, không NPE |
| Alice có 3 groups | A123 | corp | groups có 3 values | REPORT_READ | groupCount=3 |
| Ops admin | OPS7 | corp | verified ops identity | ROLE_ADMIN | admin=200 nếu local policy cấp |
| Partner cùng email Alice | B999 | partner | email giống Alice | ROLE_EMPLOYEE | Không auto-link Alice corp |
| “admins” attribute nhưng no local admin | C555 | partner | groups=[admins] | ROLE_EMPLOYEE | admin=403 |
| User bị disabled | DIS9 | corp | signed attributes vẫn đúng | Không cấp Authentication sau local policy | Deny |
| Tenant South request north | S001 | corp | tenant south | REPORT_READ | 403 local ACL |
| Anonymous | — | — | — | — | 401/redirect theo entrypoint |
| UsernamePassword fixture | alice | — | Không có SAML attrs | ROLE_USER | Không test được SAML attributes contract |

Lưu ý phương pháp: các test cases 401/403 trong MockMvc chỉ kiểm tra URL/controller policy. Các test “SAML signed nhưng account disabled” cần chạy converter/user directory đúng tầng; fixture có sẵn authenticated token sẽ bỏ qua bước disabled-account validation.

## 32. Những lỗi phổ biến khi dùng saml2Login() trong tests

| Lỗi | Vì sao | Sửa thế nào |
| --- | --- | --- |
| `Cannot resolve method saml2Login()` trong `SecurityMockMvcRequestPostProcessors` | API 6.5 không có test post-processor này | Tạo `Saml2Authentication` và dùng `authentication(...)` |
| Import `oidcLogin()` để fake SAML | Principal type thành OIDC, không phải SAML | Dùng SAML fixture đúng |
| `@WithMockUser` rồi `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` null | Principal type không khớp | `authentication(new Saml2Authentication(...))` |
| Test group attribute là `String` | SAML attribute có nhiều values | `Map<String,List<Object>>` và `getAttribute()` |
| Expect name bằng email nhưng fixture NameID opaque | Sai contract principal name | Test mapping đúng NameID/local ID |
| Missing `ROLE_` prefix khi dùng `hasRole` | `hasRole("ADMIN")` tìm `ROLE_ADMIN` | Tạo authority đúng |
| Tạo group=[admins] và tự expect admin | Attribute khác authority | Test mapper/local policy riêng |
| Tạo fixture XML dummy rồi POST tới ACS | Provider sẽ reject vì không signed/valid | Dùng signed IdP fixture |
| Coi `authentication(...)` test verify signature | Nó đã dựng SecurityContext | Integration test qua SAML provider |
| Test 3xx tới ACS và gọi success | Có thể redirect tới login error | Assert authenticated SecurityContext/handler outcome |
| Dùng `Saml2AuthenticationToken` chưa verify như authenticated token | Token isAuthenticated=false | Dùng `Saml2Authentication` fixture |
| Test không chạy Spring Security filter chain | SecurityContext không được inject đúng | `@WebMvcTest` security config hoặc `springSecurity()` |
| Test slice tự tải IdP metadata ngoài Internet | Production configuration bị import ngoài ý muốn | Isolate test config/fixtures |
| Không test missing attributes | NPE/cast failures | Test missing/multi-valued cases |
| Không test cross tenant | BOLA/IDOR | Local ACL/tenant tests |
| Test dùng live production SAMLResponse | Lộ credential/PII và replay risk | Dùng sandbox IdP/signed fixtures riêng |
| Spring 7.1 deprecation warnings | API principal/accessor đổi theo release | Theo migration docs, cô lập fixture builders |

## 33. Ma trận kiểm thử đầy đủ theo tầng

### Unit và MockMvc authorization

| Test | Trường đầu vào | Mong đợi |
| --- | --- | --- |
| U1 | NameID cố định | `Authentication.getName()` đúng |
| U2 | Email attribute một value | `getFirstAttribute("email")` trả email |
| U3 | groups multi-valued | `getAttribute("groups")` giữ list |
| U4 | Thiếu email | Không NPE/role escalation |
| U5 | registrationId=corp | Response trả đúng registration |
| U6 | Same email registrationId=partner | Không auto-link corp user |
| U7 | Employee thiếu ROLE_ADMIN | 403 admin |
| U8 | Admin ROLE_ADMIN hợp lệ | 200 admin |
| U9 | REPORT_READ | 200 report đúng tenant |
| U10 | Thiếu REPORT_READ | 403 report |
| U11 | REPORT_READ nhưng tenant sai | 403 local ACL |
| U12 | Anonymous | 401 theo test entrypoint |
| U13 | Browser giả X-Role=ADMIN | Không đổi GrantedAuthority |
| U14 | @WithMockUser thay SAML fixture | Phát hiện không kiểm thử đúng principal |
| U15 | Role mapper group từ issuer khác | Không cấp admin |
| U16 | Local account disabled | Deny ở tầng user linking/mapper |

### Integration và federation

| Test | SAML input | Mong đợi |
| --- | --- | --- |
| I1 | Valid signed Response từ test IdP | Login thành công |
| I2 | Response unsigned | Reject theo profile |
| I3 | Signature tampered | Reject |
| I4 | Unknown IdP signing certificate | Reject |
| I5 | Wrong Issuer | Reject |
| I6 | Wrong Audience | Reject |
| I7 | Wrong Recipient/Destination | Reject |
| I8 | Assertion expired | Reject |
| I9 | NotBefore tương lai | Reject |
| I10 | InResponseTo không khớp AuthnRequest | Reject |
| I11 | Session/RelayState không thuộc browser | Reject |
| I12 | Replay Response/Assertion | Reject theo anti-replay policy |
| I13 | XML Signature Wrapping | Không nhận unsigned/attacker-controlled node |
| I14 | IdP returns two values of groups | Attributes mapped đúng contract |
| I15 | IdP sends privilege-like group từ issuer lạ | Không cấp role local quá rộng |
| I16 | Browser callback với SameSite/cookie policy | AuthnRequest correlation còn hợp lệ |
| I17 | Two IdP registrations cùng email | Không cross-tenant account linking |
| I18 | Key rotation được phê duyệt | Accept đúng new trusted key |
| I19 | Key revoked/unknown | Reject |
| I20 | SP session logout và login lại | Không tái sử dụng SecurityContext sai |

**Test fixture injection qua `authentication(...)` chỉ thuộc cột Unit/MockMvc**. Tất cả integration tests phải có SAML XML được ký hợp lệ hoặc bị cố ý làm sai bằng test keys.

## 34. Viết test ổn định, không phụ thuộc thứ tự

Một số nguyên tắc:

- Mỗi request test tạo mới `Saml2Authentication`, không dùng chung mutable principal với `setRelyingPartyRegistrationId` giữa các threads.
- Không lưu `SecurityContextHolder` static/global giữa tests; để framework cleanup.
- Với `@WebMvcTest`, import đúng test security config; nếu có nhiều `SecurityFilterChain` hãy kiểm tra matcher order.
- Với `@SpringBootTest`, cấu hình test RP/IdP metadata ổn định, không gọi URL external không kiểm soát lúc startup.
- Không assert session `JSESSIONID` cụ thể hoặc XML signature bytes là bất biến qua runs.
- Không assert chỉ status code 302 mà bỏ qua redirect target và SecurityContext.
- Không dùng `MockMvcRequestBuilders.post` tạo unsigned XML và gọi đó là “successful SAML login”.
- Nếu thay attributes converter hoặc role mapper, viết unit test converter **trước** MockMvc fixture.
- Dùng Java 17 toolchain và BOM để khớp Spring Security Test với runtime.
- Test browser/proxy HTTPS có thể khác MockMvc `http://localhost`; kiểm tra `{baseUrl}`, forwarded headers và ACS URLs tại integration.

## 35. Câu hỏi tự đánh giá

**1. `HttpSecurity.saml2Login()` có tạo mock user cho MockMvc không?**  
Không. Nó cấu hình luồng đăng nhập thật của Service Provider.

**2. Trong spring-security-test 6.5 có `.with(saml2Login())` chuẩn giống `oidcLogin()` không?**  
Không trong API `SecurityMockMvcRequestPostProcessors` chính thức đã kiểm tra. Dùng `authentication(Saml2Authentication)` hoặc helper tự viết.

**3. Tại sao test `@WithMockUser` chưa đủ?**  
Nó tạo UsernamePassword principal; không chứa SAML attributes/registrationId theo kiểu `Saml2AuthenticatedPrincipal`.

**4. Principal name có luôn là email không?**  
Không. Nó có thể là NameID opaque hoặc local ID qua converter, tùy contract.

**5. Vì sao attributes phải là `Map<String,List<Object>>`?**  
SAML Attribute có thể có nhiều AttributeValue; provider giữ danh sách.

**6. Một SAML attribute groups=[admins] có tự thành ROLE_ADMIN không?**  
Không. Authorities do mapper/local IAM cấp theo issuer, registration và policy.

**7. `hasRole("ADMIN")` yêu cầu authority gì?**  
Thông thường là `ROLE_ADMIN`. `hasAuthority("ADMIN")` đòi đúng chuỗi `ADMIN`.

**8. Test `authentication(new Saml2Authentication(...))` có verify chữ ký IdP không?**  
Không; đó là mock authenticated token cho authorization/controller tests.

**9. Muốn test signature/audience/InResponseTo phải làm gì?**  
Gửi signed SAMLResponse qua ACS với test IdP/keys, pending AuthnRequest và validator thật.

**10. Vì sao test tenant authorization vẫn cần khi đã SAML login?**  
SAML xác thực identity, không chứng minh user được xem mọi report/tài nguyên của tenant khác.

**11. Có cần gọi `springSecurity()` khi tự dựng MockMvc không?**  
Có khi dùng `MockMvcBuilders` theo tài liệu, để SecurityContext và filter chain hoạt động chính xác.

**12. Với Spring Security 7.1 cần xem lại gì?**  
Các deprecation của `Saml2AuthenticatedPrincipal`/`DefaultSaml2AuthenticatedPrincipal`, API assertions/accessor và migration guide.

## 36. Checklist áp dụng vào dự án

- [ ] Hiểu rõ `HttpSecurity.saml2Login` khác MockMvc `authentication(...)`.
- [ ] Đã kiểm tra version `spring-security-test` tương thích runtime Security/BOM.
- [ ] Test principal type là SAML, không dùng `@WithMockUser` để giả SAML attributes.
- [ ] Fixture chứa NameID đúng contract, attributes `Map<String,List<Object>>`, registrationId và GrantedAuthorities.
- [ ] Tests cover missing/single/multi-valued attributes và custom NameID.
- [ ] Roles được cấp explicit từ policy, không dựa vào nhóm tùy ý.
- [ ] `hasRole`/`hasAuthority` được test đúng tiền tố và tên permissions.
- [ ] Controller `@AuthenticationPrincipal` nhận đúng type hoặc handle đa giao thức.
- [ ] MockMvc chạy trong test SecurityFilterChain có deny-by-default.
- [ ] Test anonymous 401/redirect theo đúng entrypoint thực tế của từng tầng.
- [ ] Test employee 403 admin và approver 200 đúng quyền.
- [ ] Test local tenant/ACL ngay cả khi user đã authenticated.
- [ ] Auth group/role mapper có unit tests riêng thay vì fixture cấp quyền sẵn.
- [ ] `@PreAuthorize` tests gọi Spring-managed proxied service, không `new`.
- [ ] CSRF trên business POST không bị tắt vì SAML ACS.
- [ ] Có integration tests với signed SAMLResponse/IdP sandbox và cả negative signatures/issuer/audience/time/InResponseTo/replay.
- [ ] Không dùng production SAMLResponse hoặc private signing keys làm test fixtures.
- [ ] Multi-IdP/tenant mapping giữ issuer/registration/NameID scope.
- [ ] Không nhầm `Saml2AuthenticationToken` trước validate với `Saml2Authentication` sau validate.
- [ ] Khi nâng lên Spring Security 7.1, cập nhật fixture principal types theo migration guide.

## 37. Tài liệu tham khảo

- [Spring Security 6.5 — SecurityMockMvcRequestPostProcessors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): danh sách builders `user`, `oauth2Login`, `oidcLogin`, `jwt`, `authentication`, **không có `saml2Login`**.
- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `authentication(authentication)` và `securityContext(context)`.
- [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` và FilterChainProxy integration.
- [Spring Security — MockMvc Request Post-processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): standard test request processors.
- [Spring Security 6.5 — Saml2Authentication API](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html): constructor principal/XML/authorities.
- [Spring Security 6.5 — DefaultSaml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/site/docs/6.5.6-SNAPSHOT/api/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): name, attributes, registrationId setter.
- [Spring Security 6.5 — Saml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getAttribute`, `getFirstAttribute`, registrationId.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): provider, SAML authentication pipeline và URL patterns.
- [Spring Security — SAML Authentication Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): customizing principal, attributes, granted authorities và OpenSAML provider.
- [Spring Security 6.5 — SAML 2.0 Migrations to 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): migration của response authentication converter.
- [Spring Security 7.1 — DefaultSaml2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): deprecation và `Saml2ResponseAssertionAccessor`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`/`@WithSecurityContext`/factory.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF cho business POST và web session.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): chữ ký, validation, replay, XML Signature Wrapping, trust boundary.
