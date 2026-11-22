# 29.8. Kiểm thử ánh xạ quyền và URL hoặc method authorization

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chương:** 29. Kiểm thử Servlet  
> **Trọng tâm:** Kiểm thử các bước biến dữ liệu từ OAuth2/OIDC Login thành `GrantedAuthority` và sử dụng các quyền ấy ở hai lớp bảo vệ của Spring Security Servlet: luật URL trong `SecurityFilterChain` và luật phương thức như `@PreAuthorize`. Tách rõ kiểm thử mapping, kiểm thử HTTP và kiểm thử service proxy để tránh các phép thử “xanh” nhưng ứng dụng thực tế vẫn cấp quyền sai.

Một ứng dụng OIDC có thể đăng nhập thành công nhưng vẫn xử lý **phân quyền** sai. Ví dụ, Identity Provider (OP) trả claim `groups=["finance-viewers"]`. Ứng dụng phải ánh xạ group đó thành `PERM_REPORT_READ`, không phải `ROLE_ADMIN`. Sau đó endpoint `GET /api/reports/42` được cho phép, còn `POST /api/reports/new` và `GET /api/admin/audit` phải bị từ chối. Nếu một service method xuất báo cáo yêu cầu `PERM_REPORT_EXPORT`, endpoint không được vượt qua yêu cầu này chỉ vì URL đã cho phép đọc báo cáo.

Có ba nơi dễ mắc lỗi:

1. **Ánh xạ sai quyền**: trộn `groups`, `scope`, roles và business permissions; tự cấp `ROLE_ADMIN` từ claim chưa được kiểm tra ngữ cảnh.
2. **Luật URL sai**: thiếu matcher, thứ tự matcher quá rộng, nhầm `hasRole` với `hasAuthority`, hoặc phép thử POST bị CSRF từ chối khiến ta tưởng authorization hoạt động.
3. **Method authorization bị bỏ qua**: không bật `@EnableMethodSecurity`, gọi phương thức nội bộ không đi qua proxy, hoặc test gọi thẳng đối tượng được tạo bằng `new` nên không kiểm tra interceptor thực tế.

Spring Security Test hỗ trợ `MockMvc`, `oidcLogin()`, `oauth2Login()`, `@WithMockUser` và nhiều cơ chế gắn Authentication vào request/test context. Nhưng cần nhớ: **giả lập Authentication khác với kiểm chứng toàn bộ OIDC Login flow**. Một test dùng `oidcLogin().authorities(...)` sẽ kiểm tra việc authorization xử lý authorities đã cung cấp; nó không tự chứng minh mapper được cấu hình trong production đã chuyển claims đúng.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt authentication, authorization, OIDC identity claims, OAuth2 scopes, roles và permissions nghiệp vụ.
2. Hiểu `OAuth2AuthenticationToken`, `OidcUser`, `OidcUserAuthority` và `GrantedAuthority` liên quan thế nào.
3. Phân biệt `ROLE_ADMIN`, `SCOPE_reports.read` và `PERM_REPORT_READ` trong Spring Security.
4. Thiết kế mapper từ nhóm OIDC đã xác minh sang authorities theo allowlist.
5. Viết unit test cho `GrantedAuthoritiesMapper` mà không cần OP thật.
6. Dùng `oidcLogin()` và `oauth2Login()` trong `MockMvc` để kiểm thử các chính sách URL.
7. Hiểu `oidcLogin()` không tự thực thi `OidcUserService`, `GrantedAuthoritiesMapper` hay xác minh ID Token qua OP.
8. Kiểm thử request anonymous, user authenticated nhưng thiếu quyền và user đủ quyền.
9. Kiểm thử luật `requestMatchers(HttpMethod, pattern)` và phát hiện sự khác biệt giữa GET, POST, PUT, DELETE.
10. Phân biệt lỗi HTTP 403 do CSRF với 403 do thiếu `GrantedAuthority`.
11. Kiểm thử `@PreAuthorize` qua Spring-managed service proxy với `@EnableMethodSecurity`.
12. Phát hiện self-invocation, proxy bypass và test không tải method security configuration.
13. Kiểm thử giao nhau của URL authorization và method authorization.
14. Kiểm thử sự cách ly quyền giữa nhiều registration, issuer và tenant.
15. Lập ma trận trường hợp tích cực/tiêu cực, bao gồm missing claims, mixed case, scope mismatch và quyền bị thu hồi.
16. Biết lúc nào cần integration test Authorization Code/OIDC Login thật với OP giả thay vì chỉ mock Authentication.

## 2. Bản đồ các lớp kiểm thử

| Lớp | Đầu vào | Kết quả cần chứng minh | Công cụ phù hợp |
|---|---|---|---|
| Claim interpretation | ID Token hoặc UserInfo claims đã xác minh | Hiểu đúng claim/group của provider | Unit test claim policy, mock OP |
| Authority mapping | `OidcUserAuthority` và những authorities đầu vào | Danh sách `GrantedAuthority` đúng allowlist | Unit test `GrantedAuthoritiesMapper` |
| OAuth2 Login wiring | Login result từ OP và security configuration | Mapper/service thật được gọi trong login pipeline | Integration test mock OP/AS |
| URL authorization | Authentication đã có authorities | Request được phép/bị từ chối theo method và path | `MockMvc` + `oidcLogin()` |
| Method authorization | SecurityContext khi gọi Spring bean | `@PreAuthorize` được enforce qua proxy | `@SpringBootTest`, `@WithMockUser` hoặc test authentication |
| Business tenancy | Principal + tenant/resource owner | Không truy cập tài nguyên tenant khác dù role giống nhau | Service/controller integration tests |
| End-to-end behavior | Browser, authorization code, callback, tokens | Routing, validation, mapping và policy thực sự kết nối | Test OP + ứng dụng + Resource Server giả |

**Không dùng một test đại diện cho tất cả các hàng.** Mỗi lớp có contract riêng; bộ kiểm thử đáng tin phải bao phủ cả đường đi từ claims tới API decision.

## 3. Authentication không đồng nghĩa authorization

**Authentication** trả lời “ai đã được xác thực?”. Với OIDC Login, Spring Security xác minh thông tin từ OP và tạo một Authentication phù hợp.

**Authorization** trả lời “principal này được làm gì với tài nguyên nào?”. Nó có thể dựa vào:

- `GrantedAuthority` trong Authentication;
- role hierarchy;
- annotations như `@PreAuthorize`;
- ownership/tenant membership;
- resource attributes;
- policy database hoặc authorization service.

Ví dụ một OIDC user có subject `employee-734` và đã xác thực hợp lệ, nhưng chỉ có quyền đọc:

```text
OIDC identity:
  issuer = https://login.corporate.test/realm
  sub = employee-734
  groups = ["reports-readers"]

Application authorities:
  PERM_REPORT_READ

Allowed:
  GET /api/reports/42

Denied:
  POST /api/reports/new
  GET /api/admin/audit
  GET /api/reports/42/export  (nếu cần thêm PERM_REPORT_EXPORT)
```

Không cấp quyền dựa trên việc “login thành công” hay “ID Token có chữ ký hợp lệ” mà bỏ kiểm tra claim mapping và business authorization.

## 4. Các authorities thường gặp trong Spring Security

`GrantedAuthority` biểu diễn một quyền dưới dạng chuỗi hoặc một implementation cụ thể. `SimpleGrantedAuthority` là implementation phổ biến.

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority admin =
    new SimpleGrantedAuthority("ROLE_ADMIN");

GrantedAuthority readReports =
    new SimpleGrantedAuthority("PERM_REPORT_READ");

GrantedAuthority oauthScope =
    new SimpleGrantedAuthority("SCOPE_reports.read");
```

Phân biệt:

| Authority string | Cách kiểm tra | Ý nghĩa minh họa |
|---|---|---|
| `ROLE_ADMIN` | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` | Role ứng dụng |
| `ROLE_USER` | `hasRole("USER")` | Role ứng dụng |
| `PERM_REPORT_READ` | `hasAuthority("PERM_REPORT_READ")` | Permission nghiệp vụ |
| `PERM_REPORT_EXPORT` | `hasAuthority("PERM_REPORT_EXPORT")` | Permission xuất dữ liệu |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Scope theo quy ước prefix của Spring Security |
| `OIDC_USER` | Chỉ có nếu ứng dụng tự tạo đúng chuỗi này | Không phải quyền mặc định bắt buộc |

### 4.1. hasRole và hasAuthority khác nhau

Trong cấu hình mặc định thông dụng:

```java
hasRole("ADMIN")
```

kiểm tra authority `ROLE_ADMIN`, còn:

```java
hasAuthority("ADMIN")
```

kiểm tra chuỗi `ADMIN` chính xác.

Vì vậy, user có `SimpleGrantedAuthority("ADMIN")` **không tự thỏa** `hasRole("ADMIN")` với default role prefix. Nếu ứng dụng thay default role prefix, tests phải phản ánh cấu hình thật.

### 4.2. Scope không tự là role

OAuth2 scope `reports.read` được nhiều Spring Security flows chuyển thành `SCOPE_reports.read`. Nhưng `hasRole("REPORTS_READ")` kiểm tra một chuỗi khác; không được tự đồng nhất scope và role.

Với **OAuth2 Client/OIDC Login**, việc scope trở thành authorities nào còn phụ thuộc user service và mapper đã cấu hình. Đừng suy từ hành vi của Resource Server JWT converter rồi áp cho OIDC Login.

## 5. OIDC Login và nguồn authorities

Khi đăng nhập OIDC, Spring Security có thể xây `OidcUser` và những authorities bao gồm một `OidcUserAuthority`, cùng các scope authorities theo implementation/cấu hình.

`OidcUserAuthority` chứa dữ liệu liên quan OIDC ID Token và UserInfo, để ứng dụng ánh xạ những claims thành permissions nội bộ.

```text
OP ID Token / UserInfo
        |
        v
OIDC validation + OidcUserService
        |
        v
OidcUserAuthority / scope authorities
        |
        v
GrantedAuthoritiesMapper hoặc custom OidcUserService
        |
        v
OAuth2AuthenticationToken.authorities
        |
        +--> URL AuthorizationManager
        |
        +--> @PreAuthorize / method security
```

**Điểm quan trọng:** claims từ OP là đầu vào định danh và có thể là đầu vào permission mapping đã được phê duyệt. Nhưng việc người dùng thuộc group `admins` ở OP không tự có nghĩa họ là `ROLE_ADMIN` của mọi tenant trong ứng dụng.

## 6. Quyết định nguồn quyền đáng tin

Trước khi viết mapper, phải xác định:

1. Claim `groups` lấy từ ID Token hay UserInfo?
2. Issuer nào được phép phát claim đó?
3. Claim có dạng list, string hay nested JSON theo hợp đồng OP?
4. Group nào được phép ánh xạ sang authority nội bộ nào?
5. Cùng tên group ở hai issuers có nghĩa giống nhau không?
6. Có cần kiểm tra tenant membership từ database không?
7. Permission nào thuộc ứng dụng, permission nào thuộc Resource Server?
8. Khi group bị thu hồi, authorities đang lưu trong session được làm mới như thế nào?

Ví dụ chính sách cho một OP:

| Claim group đã xác minh | Authority ứng dụng | Cho phép |
|---|---|---|
| `acme-reports-readers` | `PERM_REPORT_READ` | Đọc báo cáo Acme |
| `acme-reports-writers` | `PERM_REPORT_WRITE` | Tạo/sửa báo cáo Acme theo policy |
| `acme-report-exporters` | `PERM_REPORT_EXPORT` | Xuất báo cáo Acme |
| `acme-portal-admins` | `ROLE_ADMIN` | Chức năng quản trị Acme theo policy |
| Group không nằm trong allowlist | Không cấp quyền mới | Fail closed |

Một quy tắc như “group nào chứa `admin` thì gán `ROLE_ADMIN`” là nguy hiểm; chuỗi group phải được ánh xạ theo hợp đồng, issuer và tenant scope đã kiểm tra.

## 7. Tạo GrantedAuthoritiesMapper có allowlist

Ví dụ Java dùng các groups từ ID Token của một issuer đã được tin cậy:

```java
package example.security;

import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

public final class AcmeAuthoritiesMapper
        implements GrantedAuthoritiesMapper {

    private static final String TRUSTED_ISSUER =
        "https://login.acme.test/realms/employees";

    private static final Map<String, String> GROUP_TO_AUTHORITY =
        Map.of(
            "acme-reports-readers", "PERM_REPORT_READ",
            "acme-reports-writers", "PERM_REPORT_WRITE",
            "acme-report-exporters", "PERM_REPORT_EXPORT",
            "acme-portal-admins", "ROLE_ADMIN"
        );

    @Override
    public Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> input) {

        Set<GrantedAuthority> mapped = new HashSet<>();

        for (GrantedAuthority authority : input) {
            if (authority instanceof OidcUserAuthority oidc) {
                String issuer = oidc.getIdToken()
                    .getIssuer().toString();

                if (!TRUSTED_ISSUER.equals(issuer)) {
                    continue;
                }

                List<String> groups = oidc.getIdToken()
                    .getClaimAsStringList("groups");

                if (groups == null) {
                    continue;
                }

                for (String group : groups) {
                    String appAuthority =
                        GROUP_TO_AUTHORITY.get(group);

                    if (appAuthority != null) {
                        mapped.add(
                            new SimpleGrantedAuthority(appAuthority)
                        );
                    }
                }
            }

            // Ví dụ chỉ giữ scope authorities đã được tạo
            // bởi framework/provider, không tự nâng scope thành role.
            String value = authority.getAuthority();

            if (value != null && value.startsWith("SCOPE_")) {
                mapped.add(authority);
            }
        }

        return mapped;
    }
}
```

### 7.1. Giới hạn chủ ý của ví dụ

- Chỉ map group từ ID Token theo hợp đồng của một OP.
- Không đọc claims từ một URL/user input tùy ý.
- Không grant quyền cho groups lạ.
- Không biến mọi `SCOPE_*` thành `ROLE_ADMIN`.
- Không mặc định group cho tenant khác mang cùng ý nghĩa.
- Với ứng dụng nhiều tenants/registrations, cần mapping theo registration/issuer + tenant membership; một mapper chỉ nhìn issuer có thể chưa đủ.
- Nếu dữ liệu groups thực sự nằm trong UserInfo, ví dụ phải được điều chỉnh theo nguồn claim đã phê duyệt, không tự coi ID Token luôn có groups.

### 7.2. Vì sao mapper này có thể chưa đủ cho multi-tenant?

`GrantedAuthoritiesMapper` nhận một collection authorities, không có sẵn tham số `clientRegistrationId` trong method signature. Nếu policy phụ thuộc registration/tenant, một custom `OidcUserService` sử dụng `OidcUserRequest.getClientRegistration()` kết hợp membership service có thể phù hợp hơn. Không suy tenant chỉ từ phần cuối email hoặc tên group.

## 8. Wiring mapper vào OAuth2 Login

Ví dụ Spring Security Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class LoginAuthoritiesConfiguration {

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return new AcmeAuthoritiesMapper();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            GrantedAuthoritiesMapper mapper)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo ->
                    userInfo.userAuthoritiesMapper(mapper)
                )
            )
            .build();
    }
}
```

Đây là ví dụ cho việc wiring mapper, chưa phải toàn bộ luật URL của ứng dụng. Ở các phần sau, ta thay `authorizeHttpRequests` bằng policy đầy đủ.

**Bước kiểm thử riêng rất quan trọng:** `oidcLogin()` của Spring Security Test tạo Authentication giả lập trực tiếp. Việc nó tạo được `ROLE_ADMIN` trong MockMvc không có nghĩa bean `userAuthoritiesMapper()` ở trên đã chạy.

## 9. Khi nào dùng custom OidcUserService?

`userAuthoritiesMapper` tiện để chuyển đổi authorities sau khi user đã được load. Nhưng nếu cần:

- Đọc thêm thông tin membership từ service nội bộ.
- Dùng registration ID, issuer và tenant đồng thời.
- Dựa vào dữ liệu UserInfo/ID Token theo policy từng provider.
- Từ chối login nếu user bị khóa hoặc không thuộc tenant.
- Ánh xạ claims đa issuer/đa tenant với context rõ ràng.

thì custom `OidcUserService` hoặc một lớp service dùng trong userInfoEndpoint có thể phù hợp hơn.

Ví dụ khái niệm:

```java
OidcUserService delegate = new OidcUserService();

return request -> {
    OidcUser user = delegate.loadUser(request);
    String registrationId =
        request.getClientRegistration().getRegistrationId();

    // Xác minh issuer/sub và membership theo registration
    // trước khi tạo authorities/cho đăng nhập.
    return applyTrustedTenantPolicy(user, registrationId);
};
```

`applyTrustedTenantPolicy` là **hàm do ứng dụng tự xây**, không phải API Spring Security. Test phải inject/mock membership service và kiểm tra cả quyền bị từ chối. Nếu custom user service tạo `DefaultOidcUser`, hãy bảo toàn ID Token/UserInfo và name attribute theo contract của ứng dụng.

## 10. Dependency kiểm thử

Gradle ví dụ:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Với Maven, tương ứng thêm `spring-security-test` scope `test` và Spring Boot test starter.

Các ví dụ dưới dùng Spring Boot 3.x/Spring Security 6.x theo phong cách Servlet/Jakarta. API/cấu hình có thể khác nếu dự án chạy bản khác. Cần có một `SecurityFilterChain` và các controller/service beans tương ứng trong test application context.

## 11. Tư duy ba nhóm test thay vì một test “admin thành công”

Một test:

```java
mockMvc.perform(get("/api/admin/audit")
    .with(oidcLogin().authorities(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    )))
    .andExpect(status().isOk());
```

chỉ chứng minh: **khi Authentication có ROLE_ADMIN, endpoint trả 200** trong test context đang dùng.

Nó **chưa chứng minh**:

- User thường bị từ chối.
- `ROLE_ADMIN` thực sự được map từ OIDC claims.
- Session token đã được OIDC xác minh.
- Role của tenant A không có hiệu lực ở tenant B.
- Method authorization đã chạy.
- Một request không có CSRF không thể ghi dữ liệu.
- API không bị lộ qua matcher rộng hơn.

Vì vậy mỗi rule cần ít nhất ba trường hợp: **anonymous**, **authenticated thiếu quyền** và **authenticated đủ quyền**; thêm edge cases tùy mức rủi ro.

## 12. Thiết kế endpoint/authority matrix cho bài lab

Giả sử sản phẩm có:

| Method | URL | URL authorization | Method authorization bổ sung |
|---|---|---|---|
| GET | `/api/reports/{id}` | `PERM_REPORT_READ` | Business ownership nếu cần |
| POST | `/api/reports/new` | `PERM_REPORT_WRITE` | Business validation |
| GET | `/api/reports/{id}/export` | `PERM_REPORT_READ` | `PERM_REPORT_EXPORT` |
| GET | `/api/admin/audit` | `ROLE_ADMIN` | Audit domain policy |
| GET | `/public/status` | Public | Không |
| GET | `/api/profile` | Authenticated | Không |

Đây là hợp đồng của **ứng dụng minh họa**, không phải luật mặc định của Spring Security.

### 12.1. Vì sao URL export cần cả READ và EXPORT?

Một user có `PERM_REPORT_EXPORT` nhưng không có quyền đọc báo cáo không nên xuất nội dung. Chúng ta cấu hình GET reports yêu cầu READ và method export yêu cầu EXPORT. Khi cả hai lớp được áp, user cần **hai authorities**.

Nếu một rule chỉ ở controller mà service có thể được gọi từ scheduler, GraphQL hoặc endpoint khác, cần xem method security như một lớp bảo vệ bổ sung.

## 13. SecurityFilterChain với luật URL rõ ràng

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApplicationSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/public/status", "/error"
                ).permitAll()

                .requestMatchers(
                    "/api/admin/**"
                ).hasRole("ADMIN")

                .requestMatchers(
                    HttpMethod.POST, "/api/reports/**"
                ).hasAuthority("PERM_REPORT_WRITE")

                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("PERM_REPORT_READ")

                .anyRequest().authenticated()
            )
            .oauth2Login(login -> {})
            .build();
    }
}
```

Trong ứng dụng production, phần `oauth2Login(login -> {})` có thể được thay bằng cấu hình mapper/registration/logout/error handling phù hợp. Snippet nhấn mạnh cách định nghĩa luật URL; kết hợp với mapper ở mục 8 nếu dùng cùng test application.

### 13.1. Matcher cụ thể trước matcher rộng

Nếu viết:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

matcher rộng phía trước có thể xử lý `/api/admin/**` trước, khiến kiểm tra role phía sau không có hiệu lực cho những requests đó.

Trong DSL `authorizeHttpRequests`, thứ tự các matchers đóng vai trò quan trọng: **đặt những rule cụ thể hơn trước những rule rộng hơn** và thêm negative tests cho endpoint nhạy cảm.

### 13.2. GET khác POST

Hai matcher:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
.requestMatchers(HttpMethod.POST, "/api/reports/**")
```

không đồng nghĩa. Khi test, phải truyền đúng HTTP method và gửi CSRF token cho request thay đổi trạng thái nếu cấu hình CSRF bảo vệ.

### 13.3. anyRequest().authenticated() vs denyAll()

`authenticated()` chỉ yêu cầu đã đăng nhập, không đòi role cụ thể. `denyAll()` khóa những routes không được khai báo trước, phù hợp với một số ứng dụng API rất chặt. Nếu dùng `denyAll()`, phải cân nhắc endpoints OIDC login/callback và các routes cần cho sản phẩm.

Chọn fallback có chủ đích, không coi `authenticated()` là quyền truy cập mọi dữ liệu.

## 14. Controller mẫu để kiểm thử URL

```java
package example.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportExportService exporter;

    public ReportController(ReportExportService exporter) {
        this.exporter = exporter;
    }

    @GetMapping("/api/reports/{id}")
    public String view(@PathVariable long id) {
        return "report-" + id;
    }

    @PostMapping("/api/reports/new")
    public ResponseEntity<Void> create() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @GetMapping("/api/reports/{id}/export")
    public String export(@PathVariable long id) {
        return exporter.exportReport(id);
    }

    @GetMapping("/api/admin/audit")
    public String audit() {
        return "audit";
    }

    @GetMapping("/public/status")
    public String publicStatus() {
        return "ok";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile";
    }
}
```

Đây là controller tối giản dùng trong test; chưa có database, tenant ownership, validation hay trả file thực tế. Chúng ta cố ý đặt export logic trong service bean để kiểm thử cả URL layer và method layer.

## 15. Service method có @PreAuthorize

```java
package example.web;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    @PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")
    public String exportReport(long reportId) {
        return "export-" + reportId;
    }
}
```

Với `@EnableMethodSecurity`, Spring tạo method-security interceptors/proxies phù hợp. Khi controller gọi Spring-managed `ReportExportService` bean, annotation được áp.

### 15.1. Method security không phải một if trong source code

Test gọi:

```java
new ReportExportService().exportReport(42L);
```

sẽ không tự đi qua Spring proxy; annotation có thể **không được enforce**. Kiểm thử method authorization phải lấy service từ Spring context hoặc cấu hình interceptor đúng.

### 15.2. Self-invocation

Nếu một method trong cùng object gọi:

```java
this.exportReport(42L);
```

có thể bypass Spring proxy trong mô hình proxy-based method security. Không dùng test controller thành công để kết luận mọi self-invocation đều được bảo vệ. Thiết kế service boundaries để các phương thức có security contract được gọi qua proxy hoặc dùng chiến lược thực thi được hỗ trợ.

## 16. @EnableMethodSecurity không được quên

Spring Security 6 dùng:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

để bật method security theo cấu hình. Nếu annotation không được bật trong test context hoặc production context, `@PreAuthorize` không có hiệu lực chỉ vì nó xuất hiện trong source code.

### 16.1. Test context phải tương ứng production

Nếu bạn dùng `@WebMvcTest(ReportController.class)` mà không import method security config hoặc chỉ mock `ReportExportService`, test có thể kiểm tra controller response nhưng **không kiểm tra method proxy thực tế**.

Để test method security, dùng `@SpringBootTest`/Spring-managed bean hoặc slice context đã cấu hình đầy đủ interceptor và service. Tách một test nhóm `MockMvc` cho URL và một test nhóm service cho `@PreAuthorize` cũng là cách tốt.

## 17. MockMvc tích hợp Spring Security

Có hai cách setup thông dụng:

**A. Spring Boot test context:**

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportUrlSecurityTest {
    @Autowired MockMvc mockMvc;
}
```

Trong setup phù hợp, Spring Boot tích hợp filter chain với MockMvc.

**B. Standalone/manual MockMvc setup:**

```java
MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Nếu quên `springSecurity()` trong setup thủ công, `MockMvc` có thể gọi controller mà không chạy SecurityFilterChain, tạo test “200” giả.

### 17.1. Test context phải có ClientRegistrationRepository?

Tùy auto-configuration và security config, `oauth2Login()` có thể cần `ClientRegistrationRepository`. Trong test, có thể:

- Dùng một Client registration test với placeholder endpoints/Client ID.
- Import configuration bean cần thiết.
- Mock những integrations không liên quan.
- Dùng `@WebMvcTest` có security config đúng và dependencies tối thiểu.

Không cần OP thật chỉ để test URL authorization bằng `oidcLogin()`.

## 18. SecurityMockMvcRequestPostProcessors.oidcLogin()

Import:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
```

Ví dụ:

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin())
)
.andExpect(status().isForbidden());
```

**Lưu ý quan trọng:** `oidcLogin()` mặc định có những authorities của fixture mà Spring Security Test cung cấp; chúng không nhất thiết chứa `PERM_REPORT_READ`. Test này minh họa user authenticated nhưng thiếu permission đọc báo cáo trong policy của bài.

### 18.1. Gán authorities tường minh

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin().authorities(
            new SimpleGrantedAuthority("PERM_REPORT_READ")
        ))
)
.andExpect(status().isOk());
```

Dữ liệu mà test postprocessor gắn vào request được dùng để **kiểm tra authorization rule**. Không có OIDC browser redirect, authorization code hay token signature validation nào được thực hiện bởi snippet này.

### 18.2. oidcLogin() có phải là mockJwt() không?

Không. `oidcLogin()` mô phỏng OAuth2/OIDC Login của một web application (Client/RP); `jwt()` trong Spring Security Test mô phỏng bearer JWT authentication của Resource Server.

Nếu bài toán là test API nhận Bearer JWT như Resource Server, nên dùng `jwt()`/`opaqueToken()` và Resource Server rules phù hợp. Đừng dùng `jwt()` để kiểm tra những endpoint vốn dựa vào OIDC web session, hoặc ngược lại, chỉ vì cả hai có claims.

## 19. Unit test mapper trực tiếp

Cách đầu tiên để chứng minh claim mapping đúng là kiểm thử chính `AcmeAuthoritiesMapper`.

Ví dụ JUnit 5:

```java
package example.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

class AcmeAuthoritiesMapperTest {

    private final AcmeAuthoritiesMapper mapper =
        new AcmeAuthoritiesMapper();

    private OidcIdToken idToken(
            String issuer,
            List<String> groups) {

        return new OidcIdToken(
            "synthetic-token",
            Instant.now(),
            Instant.now().plusSeconds(300),
            Map.of(
                "iss", issuer,
                "sub", "synthetic-user",
                "aud", List.of("acme-client"),
                "groups", groups
            )
        );
    }

    @Test
    void trustedReaderGroupBecomesReadPermission() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.acme.test/realms/employees",
                List.of("acme-reports-readers")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .contains("PERM_REPORT_READ")
            .doesNotContain(
                "PERM_REPORT_WRITE",
                "PERM_REPORT_EXPORT",
                "ROLE_ADMIN"
            );
    }

    @Test
    void unknownGroupDoesNotBecomeAdmin() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.acme.test/realms/employees",
                List.of("admins", "random-super-admin")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .doesNotContain("ROLE_ADMIN");
    }

    @Test
    void sameGroupFromDifferentIssuerDoesNotGrantPermission() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.other.test/realms/employees",
                List.of("acme-portal-admins")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .doesNotContain("ROLE_ADMIN");
    }
}
```

### 19.1. Điều gì đã được kiểm tra?

- Group allowlist đúng cho OP tin cậy.
- Group tùy ý không thể tự biến thành `ROLE_ADMIN`.
- Cùng tên group ở issuer khác không được cấp quyền.
- Mapper không mặc định cấp toàn bộ permissions.

### 19.2. Điều gì chưa được kiểm tra?

Fixtures tự tạo `OidcIdToken` không xác minh chữ ký hoặc nonce. Unit test này **chỉ kiểm tra mapper**; nó không chứng minh OP thật đã phát token hợp lệ hay bean mapper được gắn vào OAuth2 Login pipeline.

## 20. Test khi thiếu group claim hoặc group rỗng

Một hệ thống phải xử lý:

```json
{"sub": "user-1"}
```

hoặc:

```json
{"sub": "user-1", "groups": []}
```

mà không tự cấp quyền mặc định cao.

Ví dụ helper test cần cho phép tạo ID Token **không có** claim `groups`. Kết quả kỳ vọng:

- Không throw NullPointerException.
- Không cấp `ROLE_ADMIN`.
- Không tự fallback từ thiếu group sang role mạnh.
- Chỉ giữ các authorities được policy cho phép (ví dụ scope riêng).
- Quyết định có cho login nhưng từ chối endpoints hay từ chối login hoàn toàn là **policy ứng dụng**.

### 20.1. Claim có kiểu dữ liệu sai

OP có thể gửi `groups="admins"` dạng string thay vì list, hoặc nested JSON không đúng contract. Mapper nên từ chối/gracefully fail theo policy, không dùng `String.contains("admin")` để đoán. Viết test malformed claims để tránh escalation qua dữ liệu lạ.

## 21. Test trùng group, thứ tự và casing

Các trường hợp:

```text
groups = ["acme-reports-readers", "acme-reports-readers"]
groups = ["ACME-REPORTS-READERS"]
groups = ["acme-reports-readers ", "acme-portal-admins"]
groups = []
```

Một mapper dùng `Set` có thể bỏ trùng authority. Nhưng **không nên tự lowercase/trim mọi group** nếu OP contract định nghĩa identifier case-sensitive. Nếu normalization là yêu cầu nghiệp vụ, phải thiết kế rõ và test rằng nó không biến group gần giống thành quyền cao hơn.

### 21.1. Test nhóm chứa ký tự đáng ngờ

Không cấp quyền từ:

```text
"xx-acme-portal-admins-xx"
"acme-portal-admins,other"
"../../admin"
"ROLE_ADMIN"
```

nếu policy chỉ cho phép literal `acme-portal-admins`. Chính sách allowlist chính xác tránh substring escalation.

## 22. Viết test URL authorization bằng @SpringBootTest

Ví dụ với Spring Boot/JUnit 5:

```java
package example.security;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportUrlSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerCanReadReport() throws Exception {
        mockMvc.perform(
            get("/api/reports/42")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_READ")
                ))
        )
        .andExpect(status().isOk());
    }

    @Test
    void readerCannotCreateReportEvenWithCsrf() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_READ")
                ))
                .with(csrf())
        )
        .andExpect(status().isForbidden());
    }

    @Test
    void writerCanCreateReportWithCsrf() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_WRITE")
                ))
                .with(csrf())
        )
        .andExpect(status().isCreated());
    }

    @Test
    void writerWithoutCsrfIsDeniedByCsrfFilter() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_WRITE")
                ))
        )
        .andExpect(status().isForbidden());
    }
}
```

### 22.1. Vì sao phải tách hai bài test POST?

Test `readerCannotCreateReportEvenWithCsrf` chứng minh **authorization** chặn reader. Vì đã cung cấp CSRF token hợp lệ, 403 không còn được giải thích đơn giản bởi thiếu CSRF.

Test `writerWithoutCsrfIsDeniedByCsrfFilter` chứng minh CSRF protection hoạt động, **không** chứng minh writer thiếu quyền.

Một bộ test chỉ gửi POST mà quên `with(csrf())` có thể báo 403 cho mọi role, đánh lừa người viết rằng luật POST authorization đúng.

## 23. Test anonymous và authenticated thiếu quyền

Đối với ứng dụng OAuth2 Login dùng browser redirect, anonymous request tới protected URL thường được đưa vào authentication entry point hoặc redirect tới login. Nó **không nhất thiết** trả 401 như một Bearer API.

Ví dụ:

```java
@Test
void anonymousUserIsAskedToAuthenticate() throws Exception {
    mockMvc.perform(get("/api/reports/42"))
        .andExpect(status().is3xxRedirection());
}

@Test
void authenticatedWithoutReadPermissionGets403()
        throws Exception {

    mockMvc.perform(
        get("/api/reports/42")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_USER")
            ))
    )
    .andExpect(status().isForbidden());
}
```

Điều kiện cho test anonymous redirect: ứng dụng đang dùng OAuth2 Login/browser authentication entry point và security config thực sự trả 3xx. Nếu app đã định nghĩa API-specific entry point trả 401, thì đó là expected contract. Đừng hardcode 302 cho mọi ứng dụng.

### 23.1. Anonymous và 403 khác ý nghĩa

- Anonymous: authentication chưa có, thường challenge/redirect tới login.
- Authenticated nhưng thiếu permission: authorization bị từ chối, thường 403.
- Có Authentication nhưng CSRF thiếu: cũng có thể 403, nhưng **nguyên nhân khác**.
- Resource Server Bearer token invalid: thường 401 theo challenge contract, khác với OIDC browser session.

Một test assertion cần phản ánh **cause và contract**, không chỉ “status không phải 200”.

## 24. Test quyền admin và ROLE_ prefix

Với rule:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

test:

```java
@Test
void adminCanReadAudit() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")
            ))
    )
    .andExpect(status().isOk());
}

@Test
void authorityNamedAdminWithoutRolePrefixIsNotEnough()
        throws Exception {

    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ADMIN")
            ))
    )
    .andExpect(status().isForbidden());
}

@Test
void ordinaryReaderCannotReadAudit() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

Ở cấu hình role prefix mặc định, các test minh họa chính xác khác biệt giữa `hasRole` và `hasAuthority`. Nếu team tự đổi prefix, thay expected values theo config và test cả hai đường.

## 25. Test thứ tự requestMatchers

Một lỗi cấu hình dễ bỏ qua:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
)
```

Khi matcher rộng trước, endpoint admin có thể chỉ yêu cầu authenticated. Test positive với admin vẫn xanh. Cần **test negative với user thường**:

```java
@Test
void authenticatedReaderCannotBypassAdminRoute() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

Nếu test này trả 200, đó là dấu hiệu matcher order/routing policy sai.

### 25.1. Thêm đường thay thế và fallback

Ngoài exact URL, test:

- `/api/admin/audit`;
- `/api/admin/audit/` nếu controller/router chấp nhận;
- URL có path variables;
- GET, POST, PATCH, DELETE tương ứng;
- những routes cũ/aliases;
- các endpoint được thêm mới;
- path normalization theo servlet/firewall configuration.

Không tự tắt `StrictHttpFirewall` hoặc nới path matching để test “dễ đi qua”; hãy xác định contract chấp nhận/khước từ những đường đó.

## 26. Test method security trực tiếp qua Spring bean

Với `ReportExportService.exportReport(...)` yêu cầu `PERM_REPORT_EXPORT`:

```java
package example.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import example.web.ReportExportService;

@SpringBootTest
class ReportExportMethodSecurityTest {

    @Autowired
    ReportExportService exporter;

    @Test
    @WithMockUser(authorities = "PERM_REPORT_EXPORT")
    void exporterCanInvokeMethod() {
        assertThat(exporter.exportReport(42L))
            .isEqualTo("export-42");
    }

    @Test
    @WithMockUser(authorities = "PERM_REPORT_READ")
    void readerCannotInvokeMethod() {
        assertThatThrownBy(
            () -> exporter.exportReport(42L)
        )
        .isInstanceOf(AccessDeniedException.class);
    }
}
```

Test này dùng service bean do Spring cung cấp, vì vậy method-security proxy/interceptors có cơ hội hoạt động. Với Spring Security version cụ thể, exception có thể là subtype của `AccessDeniedException`.

### 26.1. Điều gì chưa được kiểm tra?

`@WithMockUser` đặt Authentication giả vào test SecurityContext. Nó **không** đi qua OIDC Login và không kiểm tra claim mapper. Đây là test **method policy**: có `PERM_REPORT_EXPORT` thì được, thiếu thì bị chặn.

### 26.2. Tại sao không test với new ReportExportService()?

Bởi vì Spring method security được áp qua proxy/interceptor, không phải compiler chèn điều kiện vào thân method. Một đối tượng tạo bằng `new` không được quản lý bởi Spring có thể gọi method mà không gặp AccessDeniedException.

## 27. Test method-level role và SpEL

Ngoài `hasAuthority`, có thể gặp:

```java
@PreAuthorize("hasRole('ADMIN')")
public void manageUsers() { ... }

@PreAuthorize("hasAnyAuthority('PERM_REPORT_READ', 'ROLE_ADMIN')")
public Report getReport(long id) { ... }

@PreAuthorize("#ownerId == authentication.name")
public void updateOwnProfile(String ownerId) { ... }
```

Mỗi biểu thức cần test:

- User đủ role/authority.
- User thiếu role/authority.
- Null/missing argument nếu policy cần.
- Đúng/sai owner.
- Admin exception policy nếu có.
- Input giả mạo `ownerId` từ request.

### 27.1. authentication.name có thể không phải business user ID

Với OIDC, `authentication.name` có thể là `sub` hoặc principal name do mapper/user service cấu hình. Nếu domain có internal user ID khác, so sánh trực tiếp `ownerId == authentication.name` có thể sai.

Thay bằng policy service kiểm tra identity mapping đã xác minh, ví dụ `@PreAuthorize("@reportPolicy.canEdit(authentication, #reportId)")`. Đây là bean/method do ứng dụng định nghĩa và phải được test với tenants/ownership thực tế.

## 28. Test giao nhau giữa URL và method security

Endpoint:

```text
GET /api/reports/42/export
```

phải qua:

1. URL rule GET `/api/reports/**` yêu cầu `PERM_REPORT_READ`.
2. Method `ReportExportService.exportReport` yêu cầu `PERM_REPORT_EXPORT`.

Ma trận:

| Authorities | URL READ | Method EXPORT | Kết quả |
|---|---|---|---|
| Không có | Không | Không được gọi | 403 |
| Chỉ `PERM_REPORT_READ` | Có | Không | 403 |
| Chỉ `PERM_REPORT_EXPORT` | Không | Không được gọi | 403 |
| READ + EXPORT | Có | Có | 200 |
| `ROLE_ADMIN` | Tùy role hierarchy/policy | Tùy policy | Không mặc định bypass |
| Authenticated nhưng không roles | Không | Không được gọi | 403 |

Test tích cực:

```java
@Test
void readAndExportAuthoritiesAreBothRequired() throws Exception {
    mockMvc.perform(
        get("/api/reports/42/export")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ"),
                new SimpleGrantedAuthority("PERM_REPORT_EXPORT")
            ))
    )
    .andExpect(status().isOk());
}
```

Test tiêu cực:

```java
@Test
void readerWithoutExportAuthorityGets403() throws Exception {
    mockMvc.perform(
        get("/api/reports/42/export")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

### 28.1. Test phải chạy service proxy thật

Nếu controller được test với một mocked `ReportExportService`, test có thể không đi qua `@PreAuthorize` của real service; lúc đó test chỉ kiểm tra URL policy. Dùng Spring-managed service thật hoặc integration test phù hợp cho giao nhau hai layers.

## 29. Không để @WithMockUser che lỗi claim mapping

Test:

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminAccessIsAllowed() { ... }
```

kiểm tra role-based authorization. Nó không chứng minh OP group `acme-portal-admins` sẽ được mapper đổi thành `ROLE_ADMIN`.

Cần ít nhất:

1. **Mapper test:** `groups=["acme-portal-admins"]` từ trusted issuer → `ROLE_ADMIN`.
2. **URL test:** `ROLE_ADMIN` → `/api/admin/audit` 200.
3. **Integration wiring test:** OIDC login thực với mock OP → authorities trong Authentication được tạo như dự kiến.

Nếu chỉ có 1 và 2, code có thể vẫn quên:

```java
.userInfoEndpoint(userInfo -> userInfo.userAuthoritiesMapper(mapper))
```

làm production không bao giờ tạo ROLE_ADMIN dù các unit tests đều xanh.

## 30. Kết hợp mapper output với oidcLogin() trong test

Để kiểm thử **hợp đồng nối hai lớp** mà không cần OP thật, ta có thể lấy authorities từ mapper rồi cung cấp chúng cho `oidcLogin()`:

```java
OidcIdToken idToken = // synthetic token fixture
GrantedAuthoritiesMapper mapper = new AcmeAuthoritiesMapper();

var mapped = mapper.mapAuthorities(
    List.of(new OidcUserAuthority(idToken))
);

GrantedAuthority[] authorities =
    mapped.toArray(new GrantedAuthority[0]);

mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin().authorities(authorities))
)
.andExpect(status().isOk());
```

Test này chứng minh **mapper output khi được đưa vào policy thì được hiểu đúng**.

**Tuy nhiên:** nó vẫn không chứng minh Spring Security OAuth2 Login trong application context đã gọi mapper. Để bảo đảm wiring, dùng một integration test với OP giả và login callback thực, hoặc test bean configuration phù hợp.

## 31. Test claims với oidcLogin().idToken(...)

`oidcLogin()` cho phép chỉnh fixture ID Token:

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin()
            .idToken(token -> token
                .claim("groups", List.of("acme-reports-readers"))
            )
        )
);
```

Đoạn này đưa `groups` vào synthetic ID Token của test principal.

**Cảnh báo quan trọng:** chỉ thêm claim groups không tự chạy `AcmeAuthoritiesMapper` hay tự cấp `PERM_REPORT_READ`. Muốn test URL rule, dùng `.authorities(...)`. Muốn test mapper, gọi mapper trực tiếp. Muốn test wiring, chạy full login path với OP test.

Đây là một trong những điểm phân biệt quan trọng nhất trong bài học.

## 32. oauth2Login() và oidcLogin() khác nhau

Spring Security Test hỗ trợ hai hướng:

**`oauth2Login()`**

- Mô phỏng OAuth2 Login principal.
- Phù hợp khi provider dùng OAuth2 login không có ID Token.
- Có thể cấu hình authorities và OAuth2 user attributes.

**`oidcLogin()`**

- Mô phỏng OpenID Connect Login principal.
- Có OIDC ID Token/UserInfo fixture.
- Có thể cấu hình authorities cho Authentication.

Trong cả hai trường hợp, test postprocessor tạo context giả lập; không tự gọi OP, Authorization Endpoint, Token Endpoint hay UserInfo endpoint.

### 32.1. Không suy claims của OAuth2User giống OidcUser

Một OAuth2 provider không OIDC có thể cung cấp `OAuth2UserAuthority` với attributes khác `OidcUserAuthority`. Mapper chỉ nhận `OidcUserAuthority` sẽ không tự map roles cho OAuth2 Login thường.

Nếu sản phẩm hỗ trợ cả hai, phải có policy mapping riêng theo provider/registration và test cả hai đường.

## 33. Resource Server JWT tests không thay OIDC Client tests

Một backend có thể đồng thời là:

- OIDC Client/RP cho browser login.
- OAuth2 Resource Server nhận JWT Bearer cho API.

Hai Authentication types khác nhau:

| Flow | Authentication thường gặp | Test postprocessor phù hợp |
|---|---|---|
| OIDC Login browser | `OAuth2AuthenticationToken` với `OidcUser` | `oidcLogin()` |
| OAuth2 Login không OIDC | `OAuth2AuthenticationToken` với `OAuth2User` | `oauth2Login()` |
| Resource Server JWT | `JwtAuthenticationToken` | `jwt()` |
| Resource Server opaque token | Bearer authentication với token introspection | `opaqueToken()` |
| Form login/username/password | Authentication với UserDetails | `user()` hoặc `@WithMockUser` |

Một test `jwt().authorities(...)` có thể hợp lệ cho REST Resource Server, nhưng **không tự chứng minh** authorities của `OidcUser` được tạo từ OIDC Login theo policy.

Nếu cùng URL hỗ trợ browser session và Bearer token, cần thử cả hai authentication entry points/filter chains theo contract.

## 34. Role hierarchy: ADMIN có tự nhận REPORT_READ không?

Không phải mặc định mọi role admin được cấp toàn bộ permissions. Nếu ứng dụng có `RoleHierarchy`, ví dụ ADMIN kế thừa VIEWER, thì policy/test cần thể hiện hierarchy đó.

Nguyên tắc:

- Phân quyền dựa trên cấu hình hierarchy thật, không suy từ tên chuỗi `ROLE_ADMIN`.
- Nếu `ROLE_ADMIN` cần được phép xuất báo cáo, phải có policy rõ.
- Role hierarchy và permissions `PERM_*` có thể có semantics khác nhau.
- Test user có admin role **không** có export permission để xác định contract thực tế.
- Đừng hardcode mọi test admin đều 200 mà không xem authorities/roles ở từng lớp.

### 34.1. Prefix mismatch trong hierarchy

Nếu hierarchy dùng `ROLE_ADMIN > ROLE_VIEWER` nhưng test đặt `ADMIN`, kết quả có thể khác. Kiểm thử string chính xác sau mapping và các policy methods dùng hasRole/hasAuthority.

## 35. Multi-tenant: đúng role nhưng sai tenant

Kịch bản:

```text
Tenant A (Acme):
  issuer = https://login.acme.test/realms/employees
  group = acme-portal-admins
  user = alice

Tenant B (Globex):
  issuer = https://identity.globex.test/oidc
  group = globex-portal-admins
  user = bob
```

Alice có `ROLE_ADMIN` **của Acme**, không tự có quyền quản trị Globex.

Một URL rule như:

```java
.requestMatchers("/t/*/admin/**").hasRole("ADMIN")
```

có thể quá rộng nếu `ROLE_ADMIN` không mang tenant context. Cần thêm policy bảo đảm principal là member/admin của **tenant đang được truy cập**, ví dụ custom authorization manager hoặc service check.

### 35.1. URL variable không phải bằng chứng tenant membership

```text
GET /t/globex/admin/users
```

là một request mà caller tự chọn. Không lấy `globex` từ URL rồi tự cấp quyền chỉ vì token chứa `ROLE_ADMIN` ở tenant khác.

### 35.2. Test cross-tenant denial

Tạo cases:

| Identity | Authorities | Request tenant | Kỳ vọng |
|---|---|---|---|
| Alice của Acme | Acme admin | Acme | Allow nếu policy thỏa |
| Alice của Acme | Acme admin | Globex | Deny |
| Bob của Globex | Globex admin | Globex | Allow |
| Bob của Globex | Globex admin | Acme | Deny |
| User không membership | Role string từ claim khác | Acme/Globex | Deny |
| Cùng `sub` ở hai issuers | Bất kỳ | Tenant không tương ứng | Không account-link sai |

Đây là test authorization ứng dụng, không chỉ test `hasRole("ADMIN")`.

## 36. Thiết kế method authorization theo tài nguyên

Một permission tĩnh không phải lúc nào cũng đủ. Ví dụ `PERM_REPORT_READ` chỉ có giá trị cho các report thuộc tenant của user.

Có thể xây policy bean:

```java
@Service("reportPolicy")
public class ReportPolicy {

    private final ReportRepository reports;
    private final TenantMembershipService membership;

    public boolean canRead(
            Authentication authentication,
            long reportId) {

        // Tìm report tenant từ nguồn dữ liệu đáng tin.
        // Ánh xạ Authentication -> internal user theo issuer+sub.
        // Kiểm tra membership/permission trong tenant của report.
        // Đây là pseudocode minh họa:
        return verifiedCanRead(authentication, reportId);
    }
}
```

Và:

```java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report getReport(long reportId) {
    // ...
}
```

`verifiedCanRead` là logic nghiệp vụ do ứng dụng tự triển khai, không phải Spring Security API. Trong production, method phải fail closed khi identity mapping, tenant lookup hoặc nguồn quyền không xác minh được.

### 36.1. Test URL và business policy riêng

- Test URL: anonymous/user không có global read authority bị chặn.
- Test method: user có global read authority nhưng không có tenant membership vẫn bị chặn.
- Test repository: report ID thuộc tenant khác không bị lộ.
- Test race: quyền bị thu hồi trong phiên hiện hữu được revalidated theo độ trễ mà sản phẩm cam kết.

## 37. Test lỗi claim mapping để ngăn privilege escalation

Ma trận âm tính nên bao gồm:

| Đầu vào giả lập | Kỳ vọng |
|---|---|
| `groups=[]` | Không phát sinh role từ nhóm |
| Không có `groups` | Không tự grant role mạnh |
| `groups="acme-portal-admins"` không đúng schema list | Theo policy: reject/không map, không elevate |
| `groups=["admins"]` | Không khớp allowlist |
| `groups=["acme-portal-admins-extra"]` | Không khớp exact group |
| Group đúng nhưng issuer khác | Không map Acme role |
| Cùng sub từ issuer khác | Không coi là cùng user |
| Email `@acme.test` nhưng không membership | Không tự grant |
| Claim group trùng hai lần | Không có quyền trùng gây side effect |
| Null/missing principal | Không cho phép action nhạy cảm |
| OP UserInfo thay đổi cấu trúc | Không silently fallback sang admin |
| Claim tự do tên `role=ADMIN` | Không dùng nếu không thuộc trusted policy |

Test cả những dữ liệu **gần đúng** vì chúng có thể làm lộ lỗi substring/case-insensitive mapping.

## 38. Method security có thể bị bypass khi test dùng mock service

Giả sử `ReportController` gọi:

```java
reportExportService.exportReport(id);
```

Nếu trong `@WebMvcTest` ta dùng một mock bean trả sẵn `"export-42"`, annotation `@PreAuthorize` trên implementation thật không nhất thiết được chạy. Test controller có thể trả 200 dù service production sẽ từ chối.

Cách chia hợp lý:

1. MockMvc controller slice test để kiểm tra HTTP routing/serialization/URL authorization.
2. Service bean integration test để kiểm tra method authorization.
3. Một full context test có cả controller và Spring-managed service thật để kiểm tra giao nhau hai lớp.

### 38.1. Không cần một test thay thế cả ba

Một test rộng có thể phát hiện nhiều vấn đề nhưng chậm/khó debug. Nên dùng test riêng theo contract và một số integration cases đại diện rủi ro lớn.

## 39. Test Spring Security configuration thực tế

Có thể có nhiều `SecurityFilterChain`:

```text
Chain 1: /api/**      -> Bearer Resource Server
Chain 2: /**          -> OAuth2 Login browser session
```

Hoặc một chain có nhiều authentication methods. Nếu `@WebMvcTest` chỉ import một phần, MockMvc có thể không dùng cùng chain matchers như production.

### 39.1. Các câu hỏi cần kiểm tra

- Chain order có đúng không?
- Request matcher của chain có bắt endpoint không?
- URL rule có nằm trong chain đó không?
- CSRF đã bật/tắt theo đúng endpoint contract chưa?
- Authentication entry point xử lý anonymous như thế nào?
- OIDC Login có thể bắt đầu/callback trong chain không?
- Method security beans có được kích hoạt không?
- Có test URL mới không được match bởi rule rộng không?

Đừng dùng `addFilters=false` khi mục tiêu của test là kiểm tra URL authorization; cờ đó có thể loại bỏ chính SecurityFilterChain cần kiểm tra.

## 40. Test service authorization khi có @Async, @Transactional hoặc scheduler

Method security thường dựa vào proxy và SecurityContext. Khi method chạy async/scheduler:

- SecurityContext có thể không được propagate sang thread mới.
- `@PreAuthorize` có thể chạy trước hoặc trong async invocation tùy proxy/config.
- Service tự gọi method có annotation có thể bypass proxy.
- Background job có thể không có Authentication của user.
- Authorization dựa trên method arguments cần source of truth độc lập session khi chạy offline.

Tests nên kiểm tra execution context thật. Không suy một test đồng bộ `@WithMockUser` sẽ bảo đảm behavior trong executor/scheduler.

### 40.1. Đừng “sửa test” bằng cách bỏ @PreAuthorize

Nếu permission check thất bại trong background job, cần thiết kế service account/delegated authorization đúng; không xóa annotation chỉ để batch chạy.

## 41. Quyền đã thu hồi và Authentication cũ

Khi user login, authorities có thể được tính rồi lưu trong `SecurityContext`/session. Nếu admin thu hồi `ROLE_ADMIN`, Authentication hiện hữu không tự sửa.

Do đó:

- Test mapper đúng tại thời điểm login **không chứng minh** quyền bị thu hồi được chặn ngay sau đó.
- Nếu yêu cầu quyền freshness, cần invalidate session, reload permissions hoặc authorization check động.
- Test session cũ sau role change để xác nhận SLA.
- Với API dùng JWT, test expiry/introspection/denylist riêng.
- Không nhầm OIDC Login principal trong session với access token của Resource Server.

### 41.1. Test stale role

Kịch bản:

1. User login và được `ROLE_ADMIN`.
2. Admin gỡ group/membership.
3. Session cookie vẫn còn.
4. User gọi endpoint admin.
5. Ứng dụng phải tuân policy: deny ngay, deny sau TTL hoặc yêu cầu re-login theo SLA.

Một test chỉ login lại sau khi role bị xóa sẽ bỏ qua bug authorities stale trong session cũ.

## 42. Kiểm thử trường hợp không có CSRF token

Trên Servlet stack, CSRF thường được bật cho các state-changing methods trong session-based web app.

Bảng:

| Request | Authentication | CSRF | Permission | Kỳ vọng |
|---|---|---|---|---|
| GET báo cáo | Reader | Không cần cho GET theo default | READ | 200 |
| POST tạo report | Writer | Hợp lệ | WRITE | 201 |
| POST tạo report | Writer | Thiếu | WRITE | 403 do CSRF |
| POST tạo report | Reader | Hợp lệ | Thiếu WRITE | 403 do authorization |
| POST tạo report | Anonymous | Hợp lệ | Không có | Challenge/deny theo entry point |
| DELETE một resource | Có quyền | Thiếu | Có | Thường bị CSRF từ chối nếu CSRF áp dụng |

Không chỉ assert 403 rồi kết luận permission policy đúng. Tách test CSRF và role bằng cách chuẩn bị token hợp lệ khi kiểm tra authorization.

### 42.1. Với stateless Bearer API

Một số Resource Server APIs stateless không dùng browser session/cookie và được thiết kế bỏ CSRF cho những endpoints phù hợp. Trong trường hợp đó test matrix khác. Đừng tự tắt CSRF toàn hệ thống OIDC web login chỉ vì các API Bearer đã được cấu hình stateless.

## 43. Dùng @WithMockUser hay oidcLogin() khi nào?

| Công cụ | Thích hợp nhất | Không kiểm tra |
|---|---|---|
| `@WithMockUser` | Unit/integration test Spring method security, policy theo authority | OIDC claim mapping/remote login |
| `with(user(...))` | MockMvc request với username/authorities rõ | OP token validation |
| `with(oidcLogin())` | OIDC Client URL rules, principal shape, authorities | Authorization code flow, mapper wiring mặc định |
| `with(oauth2Login())` | OAuth2 non-OIDC Login rules | OIDC ID Token processing |
| `with(jwt())` | Resource Server JWT authorization rules | OIDC browser login |
| Mock OP + login callback | End-to-end OIDC config, mapper wiring, validation | Một số external provider behaviors ngoài mock |

Chọn tool theo câu hỏi test muốn chứng minh. Không cần mock OP cho mọi `hasAuthority` rule, nhưng cũng không thể chỉ dùng `oidcLogin()` nếu mục tiêu là chứng minh group mapping của production.

## 44. Tích hợp với authorization rules ở HTTP method khác nhau

Không chỉ test GET và POST. Một hệ thống thực tế có thể có:

```text
GET    /api/reports/{id}            -> READ
POST   /api/reports/new             -> WRITE
PUT    /api/reports/{id}            -> WRITE
PATCH  /api/reports/{id}/status     -> APPROVE
DELETE /api/reports/{id}            -> DELETE
GET    /api/reports/{id}/export     -> READ + EXPORT
```

Mỗi HTTP method cần luật rõ. Nếu fallback `.anyRequest().authenticated()`, một DELETE endpoint mới có thể chỉ yêu cầu login nếu developer quên khai báo quyền DELETE.

### 44.1. Negative test cho operation mới

Thêm test:

```java
mockMvc.perform(
    delete("/api/reports/42")
        .with(oidcLogin().authorities(
            new SimpleGrantedAuthority("PERM_REPORT_READ")
        ))
        .with(csrf())
)
.andExpect(status().isForbidden());
```

Expected 403 chỉ đúng nếu security policy **thực sự** từ chối reader cho DELETE. Nếu không có matcher DELETE và fallback `authenticated()`, test có thể phát hiện lỗ hổng.

## 45. Return status không đủ để chứng minh method được bảo vệ

Giả sử export endpoint trả 403 vì controller tự kiểm tra business condition, trong khi `@PreAuthorize` thực tế không chạy. Test assert 403 có thể vẫn xanh nhưng không chỉ ra security interceptor đã hoạt động.

Để test method authorization:

- Gọi trực tiếp Spring bean qua proxy với Authentication thiếu permission.
- Assert AccessDeniedException theo contract.
- Với positive case, assert kết quả nghiệp vụ.
- Có thể dùng mock dependency phía sau để xác nhận logic nhạy cảm không được gọi khi bị từ chối.
- Test self-invocation/alternate callers nếu kiến trúc có.

Không dùng body response ngẫu nhiên làm bằng chứng duy nhất của authorization mechanism.

## 46. Logging kết quả test không làm lộ token

Ngay cả test fixtures cũng nên tuân kỷ luật:

- Dùng synthetic ID Token/access tokens.
- Không copy production tokens vào test source.
- Không in `Authorization`, `Cookie` hoặc `OAuth2AuthorizedClient` trong logs.
- Không ghi toàn bộ OIDC claims nếu chứa PII.
- Không đưa `code`/`state` trong URL vào CI artifacts trừ trường hợp fixtures giả đã được phê duyệt.
- Gắn test failure với route template, registration ID và policy identifier thay vì raw token.

Với MockMvc, `andDo(print())` có thể in request/response details trong test output. Trong môi trường có credential thật hoặc test secrets, cân nhắc giới hạn hoặc sanitization trước khi sử dụng.

## 47. Lab A — Kiểm thử GrantedAuthoritiesMapper

**Mục tiêu:** biến group OIDC thành permissions theo allowlist.

1. Tạo `AcmeAuthoritiesMapper` với bốn group mappings.
2. Tạo synthetic OIDC ID Token issuer Acme.
3. Kiểm tra group reader tạo `PERM_REPORT_READ`.
4. Kiểm tra group writer không tự tạo `ROLE_ADMIN`.
5. Kiểm tra group admin tạo `ROLE_ADMIN` chính xác.
6. Kiểm tra group lạ/missing không tạo quyền.
7. Kiểm tra same group từ issuer khác bị bỏ qua.
8. Kiểm tra duplicate groups không tạo duplicate authorities.

**Kết quả mong đợi:** mapper không cấp thêm quyền từ dữ liệu chưa được phê duyệt.

## 48. Lab B — MockMvc với oidcLogin()

**Mục tiêu:** kiểm tra URL policy cho authenticated users.

1. Cấu hình URL rules GET READ, POST WRITE, admin role.
2. Dùng `oidcLogin().authorities(PERM_REPORT_READ)`.
3. GET report → 200.
4. POST report với CSRF hợp lệ → 403.
5. Dùng `oidcLogin().authorities(PERM_REPORT_WRITE)`.
6. POST report với CSRF → 201.
7. POST report không CSRF → 403 nhưng nguyên nhân là CSRF.
8. Dùng `ROLE_ADMIN` để truy cập admin → 200.

**Kết quả mong đợi:** test phân biệt authentication, authorization và CSRF.

## 49. Lab C — @PreAuthorize qua proxy

**Mục tiêu:** không để method authorization bị bỏ qua.

1. Tạo Spring-managed `ReportExportService`.
2. Bật `@EnableMethodSecurity`.
3. Gắn `@PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")`.
4. Test với `@WithMockUser(authorities = "PERM_REPORT_EXPORT")` → thành công.
5. Test với READ only → AccessDeniedException.
6. So sánh khi gọi đối tượng tạo bằng `new` để hiểu proxy boundary.
7. Tạo controller gọi service bean thật.
8. Kiểm tra GET export cần READ + EXPORT trong HTTP integration test.

**Kết quả mong đợi:** annotations được enforce tại Spring proxy và hai lớp URL/method đều hoạt động.

## 50. Lab D — Matcher order và endpoint bypass

**Mục tiêu:** phát hiện luật quá rộng.

1. Viết rule `/api/admin/**` yêu cầu `ROLE_ADMIN`.
2. Test reader vào admin → 403.
3. Cố ý đổi thứ tự, đặt `/api/**.authenticated()` lên trước trong test branch.
4. Chạy lại reader test và quan sát lỗ hổng.
5. Khôi phục thứ tự an toàn.
6. Thêm test POST/DELETE endpoints.
7. Thử fallback `authenticated()` và `denyAll()` theo product contract.
8. Ghi lại rule precedence và test regression.

**Kết quả mong đợi:** negative tests phát hiện matcher order sai mà admin positive test không thể phát hiện.

## 51. Lab E — Claim group không tự map khi dùng oidcLogin()

**Mục tiêu:** hiểu giới hạn của Spring Security Test postprocessors.

1. Trong MockMvc, dùng `oidcLogin().idToken(token -> token.claim("groups", ...))`.
2. Không cung cấp `.authorities(...)`.
3. Quan sát authorization rule yêu cầu `PERM_REPORT_READ` không tự được thỏa trong bài lab.
4. Gọi mapper trực tiếp với `OidcUserAuthority` chứa claim group.
5. Xác minh mapper tạo PERM_REPORT_READ.
6. Cung cấp mapper output qua `.authorities(...)`.
7. GET report → 200.
8. Ghi lại rằng cần full login integration test để xác nhận wiring bean mapper.

**Kết quả mong đợi:** claims fixture và GrantedAuthority fixture là hai phần khác nhau.

## 52. Lab F — Multi-tenant role isolation

**Mục tiêu:** ngăn quyền của một tenant được dùng ở tenant khác.

1. Tạo issuer Acme và Globex khác nhau.
2. Tạo user Acme có group admin.
3. Mapper chỉ chấp nhận Acme group khi issuer phù hợp.
4. Test mapper với cùng group nhưng issuer Globex.
5. Xây policy kiểm tra internal account tenant membership.
6. User admin Acme gọi API admin Acme → allow.
7. Cùng user gọi admin Globex → deny.
8. Test email/sub trùng từ issuers khác không auto-link.

**Kết quả mong đợi:** `ROLE_ADMIN` không trở thành “admin toàn bộ SaaS” ngoài scope.

## 53. Lab G — Spring Security Test và mock OP

**Mục tiêu:** phân biệt authorization policy tests và login-wiring integration tests.

1. Chạy MockMvc test với `oidcLogin()` cho URL rules.
2. Chạy unit test `GrantedAuthoritiesMapper`.
3. Tạo OP giả với Issuer/JWKS/Authorization/Token endpoints.
4. Bắt đầu Authorization Code/OIDC Login của RP theo registration test.
5. Trả ID Token hợp lệ với group Acme reader.
6. Quan sát Authentication sau login có authority tương ứng.
7. Trả ID Token group admin từ issuer sai/audience sai và xác nhận bị từ chối.
8. Đảm bảo mapper được cấu hình trong `oauth2Login().userInfoEndpoint()` thực sự được gọi.

**Kết quả mong đợi:** toàn bộ đường claims → Authentication → HTTP policy hoạt động, không chỉ mô phỏng authorities bằng tay.

## 54. Lab H — Test quyền bị thu hồi khi session còn sống

**Mục tiêu:** phát hiện stale authorities.

1. User OIDC login và có `ROLE_ADMIN`.
2. Lưu Authentication trong RP HTTP session.
3. Gỡ group/membership trên source of truth.
4. Giữ session cũ và gọi endpoint admin.
5. Quan sát hiện trạng theo design: session có thể vẫn giữ authorities cũ.
6. Thêm permission freshness check hoặc session invalidation theo policy.
7. Test lại thời điểm sau khi revoke; phải đáp ứng SLA.
8. Không suy rằng re-login mới đã bị từ chối nghĩa session cũ tự bị thu hồi.

**Kết quả mong đợi:** authorization freshness được kiểm chứng độc lập với mapper correctness.

## 55. Ma trận kiểm thử tổng hợp

| Test | Dữ liệu vào | Kỳ vọng |
|---|---|---|
| Trusted reader group | ID Token group hợp lệ | READ authority |
| Trusted writer group | ID Token group hợp lệ | WRITE authority |
| Trusted exporter group | ID Token group hợp lệ | EXPORT authority |
| Trusted admin group | ID Token group hợp lệ | ROLE_ADMIN |
| Missing groups | Không có claim groups | Không tự cấp quyền |
| Unknown groups | Group không allowlist | Không cấp quyền |
| Wrong issuer | Cùng group từ issuer khác | Không cấp Acme rights |
| Duplicate groups | Hai nhóm giống nhau | Authorities không bị nhân bản |
| Malformed claim | String thay vì list | Không elevate |
| Same sub other issuer | Chủ thể trùng sub | Không auto-link |
| Anonymous GET | Không Authentication | Redirect/challenge theo entry point |
| Reader GET report | READ | 200 |
| Reader POST report + CSRF | READ | 403 |
| Writer POST report + CSRF | WRITE | 201 |
| Writer POST report thiếu CSRF | WRITE | 403 do CSRF |
| Reader admin endpoint | READ | 403 |
| Admin admin endpoint | ROLE_ADMIN | 200 |
| Authority ADMIN thiếu prefix | ADMIN | 403 nếu default hasRole |
| Export chỉ READ | READ | 403 method |
| Export chỉ EXPORT | EXPORT | 403 URL |
| Export READ + EXPORT | Cả hai | 200 |
| Service method với EXPORT | @WithMockUser EXPORT | Thành công |
| Service method chỉ READ | @WithMockUser READ | AccessDeniedException |
| @EnableMethodSecurity thiếu | Test context không bật proxy | Test phải phát hiện cấu hình sai |
| Mocked service bypass | @WebMvcTest mock service | Không dùng làm bằng chứng method policy |
| Matcher order lỗi | Broad rule trước admin rule | Negative test phải thất bại |
| Alternative HTTP method | DELETE/PATCH | Luật đúng operation |
| Cross-tenant admin | Role Acme, request Globex | Deny |
| Role revoked | Session cũ còn | Deny theo SLA policy |
| oidcLogin claims only | Group claim nhưng không authorities | Không tự coi mapper chạy |
| Full OP login | ID Token group test | Mapper wiring thật được áp |
| Resource Server JWT | jwt() fixture | Test riêng JWT policy |

## 56. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test `oidcLogin()` trả 403 dù token có groups | Claims fixture không tự map authorities | Gọi mapper riêng hoặc dùng `.authorities(...)` |
| Unit mapper pass nhưng login thật không có role | Chưa wiring `userAuthoritiesMapper`/custom user service | Test login pipeline thực |
| `hasRole("ADMIN")` luôn 403 | Authority là `ADMIN` thay vì `ROLE_ADMIN` | Kiểm tra prefix/config |
| POST luôn 403 dù writer | Thiếu CSRF token | Dùng `with(csrf())` khi test authorization |
| GET admin 200 cho user thường | Broad request matcher trước admin matcher | Sửa thứ tự và negative tests |
| @PreAuthorize không có tác dụng | Chưa bật `@EnableMethodSecurity` | Bật đúng config/test context |
| @PreAuthorize hoạt động trong test service nhưng controller bypass | Mock service hoặc gọi self-invocation | Kiểm tra proxy/integration |
| Gọi service qua `new` không bị deny | Bỏ qua Spring proxy | Inject bean từ Spring context |
| User khác tenant vẫn có role ADMIN | Mapping không gắn issuer/tenant | Bổ sung membership/authorization |
| `jwt()` test pass, OIDC session test fail | Nhầm Resource Server và OIDC Client Authentication | Test đúng loại principal |
| `@WithMockUser` pass nhưng ID Token thật fail | Bypass protocol/mapping validation | Mock OP integration test |
| Anonymous trả 302 thay vì 401 | OAuth2 Login browser entry point | Assert theo security contract |
| Method export chỉ có EXPORT bị 403 | URL layer còn yêu cầu READ | Kiểm tra hai lớp |
| Method test trả 403 do business check | Chưa kiểm tra interceptor thật | Gọi Spring bean trực tiếp/verify AccessDeniedException |
| Authority rút ở OP nhưng session vẫn admin | Stale Authentication | Invalidate session hoặc revalidate |
| Same group ở issuer khác vẫn grant | Mapper chỉ nhìn tên group | Thêm issuer/registration context |
| Route DELETE mới mở cho mọi user đã login | Fallback `authenticated()` quá rộng | Khai báo operation-specific matcher |
| Test path bypass trên MockMvc khác production | Context/filter/firewall không giống | Dùng production-like configuration |

## 57. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “ID Token hợp lệ thì user có quyền truy cập mọi endpoint.” | OIDC xác thực danh tính; authorization do policy quyết định. |
| “Group `admins` luôn là ROLE_ADMIN.” | Phải dựa trên trusted issuer/tenant allowlist. |
| “Scope và role là một.” | `SCOPE_*` và `ROLE_*` là các authorities khác nhau. |
| “hasRole('ADMIN') kiểm tra authority ADMIN.” | Theo default prefix, kiểm tra `ROLE_ADMIN`. |
| “oidcLogin().idToken(groups) sẽ tự chạy mapper.” | Postprocessor giả lập Authentication, không chạy mapper wiring. |
| “oidcLogin() test chứng minh ID Token signature hợp lệ.” | Nó bypass remote protocol validation. |
| “@WithMockUser test được OIDC claims.” | Nó chỉ đặt mock Authentication. |
| “Một test 200 của admin đủ chứng minh API an toàn.” | Cần negative tests cho user thiếu quyền, anonymous và bypass routes. |
| “POST 403 nghĩa permission policy đã đúng.” | 403 có thể đến từ CSRF filter. |
| “@PreAuthorize luôn hoạt động chỉ vì có annotation.” | Cần method security enabled và Spring proxy invocation. |
| “Method call bằng new giống call qua Spring bean.” | Thường bypass interceptor/proxy. |
| “Mocking service trong MVC test chứng minh @PreAuthorize.” | Mock có thể bỏ method security implementation. |
| “ROLE_ADMIN từ tenant A là admin tenant B.” | Cần tenant-scoped authorization. |
| “UserInfo/ID Token group mapping giống nhau mọi provider.” | Claim shape/source phụ thuộc OP contract. |
| “Đổi quyền ở OP sửa ngay SecurityContext hiện tại.” | Session có thể giữ authorities cũ. |
| “Resource Server jwt() tương đương OIDC Client oidcLogin().” | Hai authentication flows khác nhau. |
| “Matcher order không quan trọng.” | Rule rộng có thể bỏ qua rule cụ thể phía sau. |
| “Không cần kiểm thử HTTP method khác GET.” | POST/PUT/PATCH/DELETE có permissions và CSRF semantics riêng. |

## 58. Câu hỏi tự kiểm tra

**Câu 1.** `GrantedAuthority` khác OIDC group claim như thế nào?

*Gợi ý:* group là dữ liệu từ OP; authority là quyền mà ứng dụng sử dụng trong authorization decisions.

**Câu 2.** `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` có giống nhau ở default prefix không?

*Gợi ý:* thường có, nhưng cấu hình prefix có thể thay đổi.

**Câu 3.** Vì sao unit test mapper và MockMvc test URL cần tách?

*Gợi ý:* một test mapping, test kia kiểm tra enforcement của authorities đã có.

**Câu 4.** Dùng `oidcLogin().idToken(token -> token.claim("groups", ...))` có tự gọi mapper không?

*Gợi ý:* không.

**Câu 5.** Vì sao test reader POST phải gửi `with(csrf())`?

*Gợi ý:* muốn 403 do thiếu WRITE, không phải thiếu CSRF token.

**Câu 6.** Vì sao anonymous request trong OIDC browser app có thể trả 302 thay vì 401?

*Gợi ý:* authentication entry point dẫn browser tới login.

**Câu 7.** Vì sao code `new ReportExportService().exportReport(...)` không phải cách test `@PreAuthorize` tốt?

*Gợi ý:* bypass Spring-managed method-security proxy.

**Câu 8.** Có `@EnableMethodSecurity` trong production nhưng không import vào test context thì sao?

*Gợi ý:* method authorization test có thể không phản ánh production behavior.

**Câu 9.** Vì sao user có EXPORT mà không có READ vẫn bị GET export từ chối?

*Gợi ý:* URL authorization yêu cầu READ trước khi service method kiểm tra EXPORT.

**Câu 10.** Nếu cùng `sub=123` xuất hiện ở hai issuers, ta có thể coi là cùng user không?

*Gợi ý:* không; sub có phạm vi issuer.

**Câu 11.** Nếu role là ADMIN cho tenant Acme, user có tự làm admin Globex không?

*Gợi ý:* không; tenant membership/permissions cần enforce riêng.

**Câu 12.** Một `@WebMvcTest` dùng mock export service có chứng minh method security không?

*Gợi ý:* không nhất thiết.

**Câu 13.** Vì sao một test `jwt()` không chứng minh OIDC Login authority mapper hoạt động?

*Gợi ý:* Resource Server JWT authentication là flow khác.

**Câu 14.** Khi admin gỡ group nhưng HTTP session còn, test gì cần chạy?

*Gợi ý:* stale authorities/authorization freshness trong session.

**Câu 15.** Matcher `/api/**.authenticated()` đặt trước `/api/admin/**.hasRole("ADMIN")` gây rủi ro gì?

*Gợi ý:* rule rộng có thể short-circuit admin rule.

## 59. Checklist trước khi coi authorization tests hoàn thành

1. **Policy documented:** Mỗi endpoint/method có permissions và expected statuses?
2. **Source trust:** Claim mapping chỉ tin provider/issuer/tenant được cho phép?
3. **Allowlist groups:** Không substring mapping hoặc fallback thành admin?
4. **Authority names:** `ROLE_*`, `SCOPE_*`, `PERM_*` nhất quán?
5. **Mapper tests:** Có cases group đúng, sai, thiếu, trùng, sai issuer?
6. **Wiring tests:** Có chứng minh mapper/custom OidcUserService được gọi trong login thật?
7. **MockMvc security:** Filter chain có chạy trong test context?
8. **Positive/negative:** Có authenticated đủ quyền và thiếu quyền cho mỗi route?
9. **Anonymous:** Có kiểm tra entry point behavior 302/401 theo contract?
10. **CSRF:** Tests phân biệt 403 do CSRF và 403 do authorization?
11. **Matcher order:** Có test user thường truy cập admin bị chặn?
12. **HTTP methods:** GET/POST/PUT/PATCH/DELETE theo policy đã khai báo?
13. **Method security:** `@EnableMethodSecurity` thật sự bật, gọi Spring proxy?
14. **Proxy boundaries:** Không bị self-invocation hoặc test `new` đánh lừa?
15. **Intersection:** URL READ + method EXPORT được test cả four combinations?
16. **Tenancy:** Role tenant A không cấp quyền trên tenant B?
17. **Session freshness:** Role revoked có hiệu lực trong thời hạn đã cam kết?
18. **Wrong auth type:** Không dùng `jwt()` thay `oidcLogin()` ngoài ngữ cảnh Resource Server?
19. **Sensitive logs:** Tests không in real tokens/ID Token claims/CSRF/session cookies?
20. **Regression:** Mọi endpoint mới có allow/deny policy test thích hợp?

## 60. Tài liệu tham khảo

- [Spring Security Reference — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): tích hợp Spring Security với Servlet tests.
- [Spring Security Reference — MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): cấu hình MockMvc và Spring Security filters.
- [Spring Security Reference — MockMvc OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `oidcLogin()` và test authentication fixtures.
- [Spring Security Reference — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): dùng CSRF request postprocessor.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): URL authorization, request matchers và thứ tự rule.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interceptors.
- [Spring Security Reference — OAuth 2.0 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): user authorities mapper và OidcUserService customization.
- [Spring Security API — GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html): authority mapping contract.
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html): ID Token/UserInfo và OIDC authority.
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html): Authentication cho OAuth2/OIDC Login.
- [Spring Security API — OidcIdToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/OidcIdToken.html): synthetic ID Token fixtures.
- [Spring Security Test API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): `oidcLogin()`, `oauth2Login()`, `jwt()` và `csrf()`.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): SpringBootTest và AutoConfigureMockMvc.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, issuer, subject và authentication.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): OAuth2 authorization grants và scopes.
- [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ authorization, token và Client integrations.

**Kết luận:** Kiểm thử authorization trong ứng dụng Spring Security OIDC Client cần chứng minh **cả chuỗi từ claims tới quyền và từ quyền tới hành vi được phép**. Kiểm thử `GrantedAuthoritiesMapper` để chắc rằng chỉ các groups được tin cậy mới trở thành `ROLE_*` hoặc `PERM_*`; dùng `MockMvc + oidcLogin().authorities(...)` để kiểm tra URL rules, HTTP methods, matcher order, anonymous và CSRF; dùng Spring-managed service với `@EnableMethodSecurity` để kiểm tra `@PreAuthorize` thực sự được enforce qua proxy. Đừng xem `oidcLogin()` là bằng chứng mapper được production gọi, đừng xem 403 do CSRF là bằng chứng thiếu quyền, và đừng bỏ qua tenant membership hoặc session authorities đã lỗi thời. Một bộ test vững phải có **allow và deny cases** ở từng lớp, nhất là các tình huống có thể gây privilege escalation hoặc rò dữ liệu giữa tenants.
