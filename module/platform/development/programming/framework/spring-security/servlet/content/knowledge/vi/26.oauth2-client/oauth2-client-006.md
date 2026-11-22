# GrantedAuthoritiesMapper và chuyển đổi claims thành quyền ứng dụng

**Module:** Spring Security – Servlet  
**Chủ đề cha:** OAuth2 Client

## 1. Vấn đề: đăng nhập OAuth2/OIDC không đồng nghĩa có quyền ứng dụng

Một ứng dụng Spring Security Servlet có thể đăng nhập bằng **OAuth 2.0 Login / OpenID Connect (OIDC)**. Sau khi người dùng đăng nhập qua Identity Provider (IdP), ứng dụng có một đối tượng `Authentication` chứa principal và tập `GrantedAuthority`. Tuy vậy, các thông tin IdP cung cấp như `sub`, `email`, `groups`, `roles`, `scope` hay claim tự định nghĩa **không tự động trở thành quyền nghiệp vụ** `ROLE_ADMIN`, `ROLE_EDITOR` hoặc `ORDER_APPROVE`.

**GrantedAuthoritiesMapper** là điểm mở rộng cho phép ứng dụng **ánh xạ các authority có được sau khi OAuth2/OIDC login** thành những `GrantedAuthority` mà cơ chế authorization của Spring Security hiểu.

Ví dụ chính sách nội bộ:

| Claim đáng tin từ IdP | Authority trong ứng dụng | Quyền được sử dụng |
| --- | --- | --- |
| `app_roles: ["viewer"]` | `ROLE_VIEWER` | Xem trang dành cho viewer |
| `app_roles: ["editor"]` | `ROLE_EDITOR` | Chỉnh sửa theo chính sách ứng dụng |
| `app_roles: ["admin"]` | `ROLE_ADMIN` | Truy cập endpoint quản trị |
| `app_roles: ["unknown"]` | Không tự cấp role mới | Từ chối vai trò chưa định nghĩa |
| Không có `app_roles` | Không thêm vai trò nghiệp vụ | Chỉ có khả năng đăng nhập, không được nâng quyền |

Dù user có `ROLE_ADMIN`, endpoint làm việc với một đối tượng cụ thể vẫn có thể cần kiểm tra quyền với **tenant, dự án, chủ sở hữu, trạng thái và tài nguyên**. Role là một yếu tố authorization, không thay kiểm tra đầy đủ.

## 2. Phân biệt OAuth2 Client, OIDC, access token và quyền ứng dụng

Spring Security hỗ trợ nhiều trường hợp có OAuth 2.0, nhưng cách chuyển claims thành quyền khác nhau:

- **`oauth2Login()` (Servlet OAuth2 Client):** ứng dụng web chuyển hướng browser sang IdP, nhận kết quả đăng nhập, tạo `OAuth2AuthenticationToken` / principal, rồi thường lưu authentication trong HTTP session. `GrantedAuthoritiesMapper` phù hợp cho **authority của người dùng sau login**.
- **OIDC login:** dùng `openid` scope và ID Token để xác nhận danh tính. `OidcUserAuthority` có thể chứa `OidcIdToken` và `OidcUserInfo` (nếu có).
- **OAuth2 login không OIDC:** thông tin người dùng thường đến từ UserInfo endpoint; `OAuth2UserAuthority` mang attributes trả về từ provider.
- **OAuth2 Resource Server nhận JWT bearer token:** đường đi thường là `JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter`, **không phải `GrantedAuthoritiesMapper` của `oauth2Login`**.
- **Ứng dụng OAuth2 Client gọi API khác:** `OAuth2AuthorizedClient`/access token dùng để gọi downstream resource server; authority của người dùng đang đăng nhập không tự quyết định được quyền ở API downstream.
- **Client credentials (machine-to-machine):** không có luồng đăng nhập người dùng tương ứng để dùng mapper theo ví dụ này.

**Claim** là trường thông tin trong ID token hoặc response UserInfo, chẳng hạn:

~~~json
{
  "sub": "user-123",
  "preferred_username": "an",
  "app_roles": ["viewer", "editor"]
}
~~~

Đây là **claim ví dụ do IdP/ứng dụng thống nhất**. Không có yêu cầu chuẩn OIDC rằng mọi IdP phải phát hành `app_roles`; có IdP dùng `roles`, `groups`, claim có namespace, `realm_access.roles` hoặc một API phân quyền riêng. Phải xác nhận **claim thực tế nằm ở ID Token, UserInfo hay chỉ ở Access Token** trước khi viết mapper.

### 2.1. Scope không phải role ứng dụng

Spring Security có thể tạo authority dạng `SCOPE_email`, `SCOPE_profile` hoặc `SCOPE_xxx` từ scopes liên quan. Scope mô tả phạm vi được cấp trong quan hệ OAuth2, không tự nói rằng người dùng là quản trị viên ứng dụng.

- `hasRole("ADMIN")` mặc định kiểm tra authority **`ROLE_ADMIN`**.
- `hasAuthority("ROLE_ADMIN")` kiểm tra chính xác chuỗi `ROLE_ADMIN`.
- `hasAuthority("SCOPE_orders.read")` kiểm tra authority scope đúng chuỗi đó, nếu authentication thực sự có.
- Claim `app_roles: ["admin"]` chỉ trở thành `ROLE_ADMIN` **sau khi** mapper được viết và chạy thành công.

Không nên dùng quy tắc “cứ có `SCOPE_profile` là `ROLE_ADMIN`” hoặc coi mọi string từ claim là quyền hệ thống.

## 3. Mapper được gọi ở đâu trong luồng Servlet OAuth2 Login?

~~~text
Browser
  |
  | GET /admin (chưa có session)
  v
Spring Security -> Redirect sang Authorization Server/IdP
  |
  | Người dùng đăng nhập và cho phép ứng dụng
  v
GET /login/oauth2/code/company?code=...&state=...
  |
  v
OAuth2/OIDC authentication provider
  |-- xác thực state, code flow, OIDC ID Token theo cơ chế framework
  |-- lấy OidcUser / OAuth2User và authorities
  v
GrantedAuthoritiesMapper
  |-- đọc claim đã chọn từ ID Token hoặc UserInfo
  |-- áp allowlist và chuyển app_roles => ROLE_*
  v
Authentication chứa mapped authorities
  |
  v
SecurityContext / session
  |
  v
Authorization: hasRole("ADMIN"), @PreAuthorize(...), ...
~~~

**Thời điểm:** mapper thường được gọi **trong quá trình authentication**, không gọi lại cho mọi HTTP request. Nếu role ở IdP thay đổi trong khi người dùng vẫn giữ session, authorities đã gắn với authentication có thể **chưa cập nhật**. Cần chính sách re-login, tái xác thực, thu hồi session hoặc đồng bộ quyền nếu yêu cầu thay đổi ngay.

**Đầu vào mapper:** `Collection<? extends GrantedAuthority>`, không phải một JWT string và **không có sẵn OAuth2AccessToken**. Dữ liệu truy xuất được tùy loại authority:

| Loại authority | Đọc dữ liệu | Ghi chú |
| --- | --- | --- |
| `OidcUserAuthority` | `getIdToken().getClaims()`; có thể thêm `getUserInfo().getClaims()` | ID Token thuộc luồng OIDC, UserInfo có thể không tồn tại. |
| `OAuth2UserAuthority` | `getAttributes()` | Thuộc OAuth2 login không OIDC hoặc thuộc dịch vụ user tùy biến. |
| `SimpleGrantedAuthority` | `getAuthority()` | Có thể chứa `SCOPE_...` hay authority khác từ nguồn đã được ứng dụng cấu hình. |

**Nguồn đáng tin:** với OIDC, Spring Security xác thực token theo issuer, audience, chữ ký và các quy tắc liên quan trong luồng chuẩn. Mapper chỉ **dịch dữ liệu đã được luồng xác thực chấp nhận**. Không lấy claim từ query parameter, header tự do do client gửi hoặc JSON không có xác thực rồi chuyển thẳng thành quyền.

## 4. Thiết kế chính sách map an toàn

Trước khi code, định nghĩa một **hợp đồng claim** với IdP:

1. Tên claim dùng làm căn cứ cấp role: ví dụ `app_roles`.
2. Nguồn ưu tiên: **ID Token** nếu claim có mặt; chỉ dùng **UserInfo** khi hợp đồng cho phép và ID Token không có claim. Đừng tùy ý hợp nhất hai nguồn với quy tắc có thể nâng quyền.
3. Kiểu dữ liệu: danh sách chuỗi như `["viewer","editor"]`; chuỗi tự do hoặc map lồng không được tự biến thành danh sách nếu chưa có đặc tả.
4. Tập vai trò cho phép: `viewer`, `editor`, `admin`; các giá trị khác bị bỏ qua hoặc từ chối đăng nhập theo chính sách.
5. Quy tắc normalizing: chỉ trim và so khớp không phân biệt hoa thường khi hợp đồng cho phép; không làm phép so khớp gần đúng kiểu chứa substring `"admin"`.
6. Quy tắc mặc định: **không có claim/không hợp lệ => không cấp role nghiệp vụ**.
7. Quy tắc đặc quyền: role quan trọng có thể cần kiểm tra thêm tenant, đăng ký nội bộ, người phê duyệt hoặc cơ chế authorization riêng.

**Không** dùng trực tiếp:

~~~java
// Ví dụ nguy hiểm: claim bất kỳ đều có thể trở thành ROLE_*.
new SimpleGrantedAuthority("ROLE_" + roleFromClaim);
~~~

Nếu ID Token/UserInfo chứa `"super_admin"` ngoài chính sách, cách trên tự tạo `ROLE_SUPER_ADMIN`. Hãy dùng **allowlist** chuyển những giá trị biết trước sang authority biết trước.

Không cấp quyền chỉ vì `email` có hậu tố công ty, `preferred_username` giống tên admin, hoặc `email_verified=true`. Đây là thông tin danh tính/thuộc tính, không thay thế quyết định cấp quyền của tổ chức.

## 5. Ví dụ Java 17+ và Spring Security 6: OIDC login + mapper

Ví dụ sau chạy trên **Spring Boot 3.3.5** và **Java 17**. Bản cố định được chọn để dễ tái hiện cú pháp; môi trường vận hành nên dùng phiên bản được hỗ trợ và cập nhật bản vá. Ứng dụng cần một OIDC Provider thật để hoàn thành login; **unit tests của mapper không cần kết nối provider**.

Cấu trúc:

~~~text
oauth-role-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── Application.java
    │   │   ├── AppAuthoritiesMapper.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/demo/AppAuthoritiesMapperTest.java
~~~

### 5.1. Maven dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>oauth-role-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 5.2. Mapper: chỉ ánh xạ claim `app_roles` qua allowlist

**src/main/java/demo/AppAuthoritiesMapper.java**

~~~java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;
import org.springframework.stereotype.Component;

@Component
public final class AppAuthoritiesMapper implements GrantedAuthoritiesMapper {

    @Override
    public Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> incoming) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                // Giữ OIDC_USER và dữ liệu nhận dạng gốc.
                result.add(oidc);

                Map<String, Object> claims = oidc.getIdToken().getClaims();

                // Chỉ fallback sang UserInfo nếu ID Token KHÔNG có claim.
                if (!claims.containsKey("app_roles")
                        && oidc.getUserInfo() != null) {
                    claims = oidc.getUserInfo().getClaims();
                }

                addApplicationRoles(claims, result);

            } else if (authority instanceof OAuth2UserAuthority oauth2) {
                result.add(oauth2); // Giữ OAUTH2_USER.
                addApplicationRoles(oauth2.getAttributes(), result);

            } else if (authority.getAuthority() != null
                    && authority.getAuthority().startsWith("SCOPE_")) {
                // Giữ scope authorities theo chính sách demo,
                // KHÔNG tự nâng scope thành ROLE_ADMIN.
                result.add(authority);
            }
        }

        return result;
    }

    private static void addApplicationRoles(
            Map<String, Object> claims,
            Set<GrantedAuthority> result) {
        Object raw = claims.get("app_roles");

        // Fail closed nếu IdP không phát danh sách chuỗi.
        if (!(raw instanceof Collection<?> roles)) {
            return;
        }

        for (Object item : roles) {
            if (!(item instanceof String role)) {
                continue;
            }

            String key = role.trim().toLowerCase(Locale.ROOT);

            switch (key) {
                case "viewer" ->
                    result.add(new SimpleGrantedAuthority("ROLE_VIEWER"));
                case "editor" ->
                    result.add(new SimpleGrantedAuthority("ROLE_EDITOR"));
                case "admin" ->
                    result.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                default -> {
                    // Không tự tạo role cho giá trị lạ.
                }
            }
        }
    }
}
~~~

Giải thích những quyết định bảo mật:

- Chỉ lấy `app_roles` từ authority được framework cung cấp sau login. Code không tin role do browser tự khai báo.
- Với OIDC, ưu tiên claim trong ID Token; chỉ chuyển sang UserInfo khi **thiếu hẳn** claim ở ID Token. Nếu ID Token có claim nhưng sai kiểu hoặc giá trị lạ, code không chuyển sang nguồn khác để “cứu” bằng cách nâng quyền.
- Với OAuth2 login không OIDC, dùng `OAuth2UserAuthority.getAttributes()`, phù hợp nếu provider cung cấp `app_roles` qua dữ liệu user đã lấy.
- Bỏ qua claim sai kiểu và vai trò không nằm trong allowlist.
- Dùng `LinkedHashSet` để tránh authority trùng.
- Giữ authority nhận dạng `OIDC_USER`/`OAUTH2_USER` và các `SCOPE_` mà Spring Security đã đưa vào; **không** copy tùy ý mọi `ROLE_*` có sẵn từ nguồn chưa được audit. Nếu ứng dụng có authority gốc hợp lệ khác, hãy mở rộng chính sách giữ authority một cách rõ ràng.
- Mapper chỉ ánh xạ role. Chính sách nghiệp vụ quan trọng vẫn cần authorization theo resource.

**Lưu ý:** `List` được import trong ví dụ để dễ dùng khi phát triển thêm nhưng không được sử dụng trực tiếp trong class mapper; có thể bỏ import đó mà không ảnh hưởng biên dịch.

### 5.3. Đăng ký mapper trong Spring Security Servlet

**src/main/java/demo/SecurityConfiguration.java**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AppAuthoritiesMapper mapper) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/edit").hasAnyRole("EDITOR", "ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info ->
                    info.userAuthoritiesMapper(mapper)
                )
            );

        // Giữ CSRF mặc định cho session/cookie.
        return http.build();
    }
}
~~~

`.userAuthoritiesMapper(mapper)` là điểm tích hợp quan trọng cho `oauth2Login()`. Sau khi quá trình OAuth2/OIDC login thành công, tập authority được mapper trả về được dùng trong `Authentication`, từ đó Spring Security áp dụng `hasRole` / `hasAuthority`.

`hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` theo default role prefix. **Không** viết `hasRole("ROLE_ADMIN")` nếu vẫn dùng prefix mặc định, vì dễ tạo nhầm cấu hình prefix. Với quyền không phải role, như `INVOICE_APPROVE`, dùng `hasAuthority("INVOICE_APPROVE")` hoặc một AuthorizationManager phù hợp.

**src/main/java/demo/DemoController.java**

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "Open /me, /edit or /admin");
    }

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", names
        );
    }

    @GetMapping("/edit")
    Map<String, String> edit() {
        return Map.of("status", "editor-or-admin");
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("status", "admin");
    }
}
~~~

Chỉ trả **tên authority** ở endpoint `/me` để quan sát kết quả học tập; **không xuất ID Token, access token, refresh token hoặc claim nhạy cảm** ra response hay log. Production thường chỉ trả những thông tin thực sự cần cho UI.

### 5.4. Kết nối OIDC Provider

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**Trong file YAML thực tế**, cú pháp Spring environment placeholder phải là `client-id: ${OIDC_CLIENT_ID}`, `client-secret: ${OIDC_CLIENT_SECRET}` và `issuer-uri: ${OIDC_ISSUER_URI}`; ba giá trị này đọc từ biến môi trường. Không hard-code client secret thật vào repository.

IdP phải được cấu hình redirect URI hợp lệ cho registration `company`, thông thường:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Đăng nhập thử bằng `/oauth2/authorization/company`; browser chuyển qua provider và trở lại callback sau authorization-code flow. Để nhận `ROLE_EDITOR` trong ví dụ, IdP cần thực sự phát claim `app_roles: ["editor"]` ở **ID Token**, hoặc **UserInfo** khi ID Token không chứa claim; claim không tự xuất hiện khi chỉ khai báo `scope: openid, profile, email`.

**Chạy dự án với OIDC Provider hợp lệ đã cấu hình:**

~~~bash
mvn spring-boot:run
~~~

Kết quả mong đợi sau login với `app_roles: ["editor"]`:

| Request | Kỳ vọng |
| --- | --- |
| `GET /` | 200, public. |
| `GET /me` khi chưa login | Điều hướng đến trang login theo flow mặc định. |
| `GET /me` đã login | 200, authorities có `ROLE_EDITOR`; có thể có `OIDC_USER`, `SCOPE_...`. |
| `GET /edit` đã login editor | 200. |
| `GET /admin` đã login editor nhưng không có `ROLE_ADMIN` | 403 Forbidden. |
| `GET /admin` đã login admin | 200 nếu mapper thực sự tạo `ROLE_ADMIN`. |

**Cảnh báo phạm vi:** không nên triển khai endpoint thay đổi dữ liệu bằng GET như `/edit`; ví dụ trả trạng thái chỉ để quan sát authorization. Các thao tác ghi thực tế phải dùng HTTP method thích hợp, được bảo vệ CSRF khi xác thực bằng session cookie, đồng thời kiểm tra quyền và nghiệp vụ.

## 6. Unit test mapper: không cần một IdP đang chạy

**src/test/java/demo/AppAuthoritiesMapperTest.java**

~~~java
package demo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;

import static org.assertj.core.api.Assertions.assertThat;

class AppAuthoritiesMapperTest {

    private final AppAuthoritiesMapper mapper = new AppAuthoritiesMapper();

    private static Set<String> names(
            Collection<? extends GrantedAuthority> authorities) {
        return authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void mapsOidcIdTokenRolesAndKeepsScope() {
        var token = new OidcIdToken(
            "id-token-used-only-in-this-unit-test",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2026-01-01T01:00:00Z"),
            Map.of(
                "sub", "user-1",
                "app_roles", List.of("editor", "viewer", "unknown")
            )
        );

        var mapped = mapper.mapAuthorities(List.of(
            new OidcUserAuthority(token),
            new SimpleGrantedAuthority("SCOPE_email")
        ));

        assertThat(names(mapped))
            .contains("OIDC_USER", "SCOPE_email",
                      "ROLE_EDITOR", "ROLE_VIEWER")
            .doesNotContain("ROLE_ADMIN", "ROLE_UNKNOWN");
    }

    @Test
    void mapsNonOidcUserAttributesWithAllowlist() {
        var oauth2 = new OAuth2UserAuthority(Map.of(
            "id", "user-2",
            "app_roles", List.of(" admin ", "admin", "other")
        ));

        var mapped = mapper.mapAuthorities(List.of(oauth2));

        assertThat(names(mapped))
            .contains("OAUTH2_USER", "ROLE_ADMIN")
            .doesNotContain("ROLE_OTHER");
    }

    @Test
    void missingOrMalformedRolesDoNotElevateUser() {
        var noClaim = new OAuth2UserAuthority(Map.of(
            "id", "user-3",
            "email", "admin@example.test"
        ));
        var wrongType = new OAuth2UserAuthority(Map.of(
            "id", "user-4",
            "app_roles", "admin"
        ));
        var nonStrings = new OAuth2UserAuthority(Map.of(
            "id", "user-5",
            "app_roles", List.of(42, true)
        ));

        for (var authority : List.of(noClaim, wrongType, nonStrings)) {
            assertThat(names(mapper.mapAuthorities(List.of(authority))))
                .contains("OAUTH2_USER")
                .doesNotContain("ROLE_ADMIN", "ROLE_EDITOR", "ROLE_VIEWER");
        }
    }

    @Test
    void unsupportedRoleCannotCreateArbitraryAuthority() {
        var oauth2 = new OAuth2UserAuthority(Map.of(
            "id", "user-6",
            "app_roles", List.of("super_admin", "ROLE_ADMIN")
        ));

        assertThat(names(mapper.mapAuthorities(List.of(oauth2))))
            .doesNotContain("ROLE_SUPER_ADMIN", "ROLE_ADMIN");
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

**Kỳ vọng:** cả 4 test pass. Đây là kết quả dự kiến khi chạy đúng source trên, không phải log được ghi nhận từ một môi trường thực thi đã kiểm chứng.

Lưu ý test tự tạo `OidcIdToken` **chỉ để kiểm thử mapper**, không xác minh chữ ký JWT hoặc luồng OIDC thật. Phần xác thực token/issuer/audience thuộc integration tests và cấu hình OAuth2 Login với IdP tin cậy. Tránh dùng các đối tượng token tự tạo đó trong production.

## 7. Khi claims không có ở ID Token hoặc UserInfo

Với một số IdP, role chỉ có trong **Access Token** (ví dụ `realm_access.roles`) hoặc trong API quản lý nhóm/quyền riêng. `GrantedAuthoritiesMapper` không được cung cấp `OAuth2AccessToken` trực tiếp, vì nó chỉ nhận collection authority.

Có ba hướng thiết kế:

1. **Ưu tiên cấu hình IdP phát hành claim dùng cho ứng dụng vào ID Token/UserInfo**, nếu chính sách IdP cho phép và claim đúng audience/ngữ cảnh.
2. **Tùy biến `OAuth2UserService` / `OidcUserService`**, nơi `OAuth2UserRequest`/`OidcUserRequest` có thông tin access token. Service có thể gọi endpoint role đáng tin bằng token phù hợp rồi tạo principal chứa authority được kiểm tra. Cần timeout, kiểm tra lỗi, giới hạn quyền token và chính sách fail closed.
3. **Tra quyền nội bộ từ database** theo định danh ổn định `issuer + sub` hoặc khóa người dùng đã liên kết; phù hợp nếu quyền là quyết định của chính ứng dụng, không phải của IdP.

**Không nên** tự decode Access Token như một JWT rồi coi nội dung là quyền ứng dụng mà bỏ qua xác thực issuer, audience, chữ ký và đúng mục đích sử dụng. Access token có thể opaque; có thể được phát hành cho một resource server khác; chưa chắc có cấu trúc JWT hoặc claims như đã đoán.

Nếu IdP dùng claim lồng như `realm_access.roles`, cần viết extractor đúng schema, xác thực kiểu dữ liệu từng mức và chỉ cấp quyền theo allowlist. Mapper ở mục 5 **cố ý chỉ hiểu một schema `app_roles`**, không tự nhận tất cả tên claim của mọi IdP.

## 8. `GrantedAuthoritiesMapper` khác `JwtAuthenticationConverter`

Đây là nhầm lẫn phổ biến trong Spring Security:

| Trường hợp | Authentication | Điểm chuyển đổi quyền phù hợp |
| --- | --- | --- |
| Servlet web app dùng `oauth2Login()` | `OAuth2AuthenticationToken` và `OAuth2User` / `OidcUser` | `GrantedAuthoritiesMapper` trong `oauth2Login().userInfoEndpoint()`; hoặc custom user service. |
| REST API dùng `oauth2ResourceServer().jwt()` | `JwtAuthenticationToken` | `JwtAuthenticationConverter` và `JwtGrantedAuthoritiesConverter` / custom converter. |
| API xác thực bằng opaque token introspection | Bearer token authentication với principal từ introspection | Custom introspector/authority conversion tùy cấu hình. |
| OAuth2 Client gọi downstream API | `OAuth2AuthorizedClient` / access token | Quyền được kiểm tra ở resource server đích; không tự chuyển role của UI thành quyền API. |

Vì vậy nếu mapper hoạt động ở web app nhưng request tới resource server vẫn 403, không nhất thiết mapper sai: resource server có cơ chế xác thực bearer token và quyết định quyền **riêng**. Đừng truyền role từ `/me` hoặc từ browser như nguồn chứng minh quyền của API.

## 9. `ROLE_`, `SCOPE_` và `@PreAuthorize`

Role/authority là **chuỗi** Spring Security sử dụng trong quyết định truy cập; `SimpleGrantedAuthority` chỉ là wrapper mang chuỗi đó.

Ví dụ:

~~~java
// Nếu Authentication có ROLE_EDITOR:
.requestMatchers("/edit").hasRole("EDITOR")

// Kiểm tra đúng authority, không thêm ROLE_:
.requestMatchers("/audit").hasAuthority("AUDIT_READ")
~~~

Đây là **đoạn cấu hình minh họa trong DSL**, không phải một file Java độc lập. `hasRole("EDITOR")` khớp `ROLE_EDITOR` với prefix mặc định. Còn `hasAuthority("AUDIT_READ")` khớp đúng `AUDIT_READ`.

Nếu đã bật `@EnableMethodSecurity`, service có thể kiểm tra:

~~~java
@PreAuthorize("hasRole('EDITOR') or hasRole('ADMIN')")
public void updateArticle(long articleId, String text) {
    // Kiểm tra thêm quyền với articleId ở lớp nghiệp vụ.
}
~~~

Đoạn này cũng là **minh họa phương thức bên trong service có import `PreAuthorize`**, không phải class chạy độc lập. Với hệ thống nhiều tenant, phải đánh giá cả `articleId` thuộc tenant nào và người gọi được sửa bài đó không; role đơn thuần chưa đủ.

Tránh tạo role có cùng tên với scope rồi suy luận ngầm. Một chính sách có thể dùng `ROLE_EDITOR` cho quyền UI, `ARTICLE_WRITE` cho thao tác nghiệp vụ, `SCOPE_articles.write` cho quyền gọi API của client; không bắt buộc ba thứ phải đồng nghĩa.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Login thành công, `/admin` trả 403 | Mapper không tạo `ROLE_ADMIN`; claim vắng/sai nguồn/sai kiểu; user thực sự không có role. | Xem schema claim đã được xác thực, mapper output và policy `hasRole`. |
| Có `SCOPE_profile` nhưng không qua `hasRole("ADMIN")` | Scope khác role. | Map role theo chính sách rõ ràng; không nâng scope thành admin. |
| Token có `realm_access.roles` nhưng mapper không thấy | Claim nằm **chỉ trong Access Token**, không nằm ở ID Token/UserInfo mà mapper đọc. | Cấu hình IdP bổ sung claim phù hợp hoặc custom user service/role lookup. |
| Có claim `"ADMIN"` nhưng không qua | Tên claim khác `app_roles`, dữ liệu không phải array, hoặc mapping bị bỏ qua. | Xác định hợp đồng claim chính xác rồi kiểm tra test case. |
| UserInfo thiếu role nhưng ID Token có role | Chính sách mapper ưu tiên ID Token. | Quan sát nguồn đúng; tránh ghi đè bằng nguồn ít tin cậy hơn. |
| `hasRole("ROLE_ADMIN")` không khớp | Prefix `ROLE_` bị áp thêm tùy matcher mặc định. | Viết `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`. |
| User đổi role ở IdP nhưng web app vẫn giữ role cũ | Authority được map lúc login và có thể được lưu trong session. | Đặt chính sách refresh/re-login/revoke session. |
| Roles mapper đúng nhưng API bearer token vẫn bị 403 | Resource Server dùng converter riêng. | Kiểm tra JWT converter/audience/scopes và policy bên API. |
| User thuộc tenant khác vẫn có role admin | Role toàn cục không gắn tài nguyên/tenant. | Thêm authorization theo resource/tenant, không dựa mỗi `ROLE_ADMIN`. |
| Mở `/oauth2/authorization/company` không vào IdP | Client registration, issuer metadata, redirect URI hoặc môi trường chưa đúng. | Kiểm tra cấu hình provider, client ID, secret và callback URL. |

Khi debug nên ghi **tên authority và số lượng role** ở môi trường kiểm thử có kiểm soát; không log raw ID Token, access token, refresh token, client secret hoặc đầy đủ thông tin cá nhân. 403 từ authorization khác với thất bại authentication/OIDC validation; xem exception và security filter logs với mức phù hợp.

## 11. Quy trình triển khai an toàn trong dự án thật

1. **Xác định chủ thể và yêu cầu quyền:** role nào được quyền làm gì, scope nào có ý nghĩa gì, quyền nào phải kiểm tra per-resource/tenant.
2. **Xác định issuer, audience, loại login:** OIDC/OAuth2 web login, JWT resource server hay service-to-service.
3. **Thống nhất schema claim** với IdP hoặc nguồn phân quyền nội bộ: tên, kiểu, nơi phát hành, thời điểm hiệu lực, trách nhiệm thu hồi.
4. **Map bằng allowlist và fail closed:** không tạo authority không được định nghĩa; xử lý null, claim thiếu/sai kiểu, role không biết, trùng.
5. **Tích hợp đúng filter chain** và xác nhận endpoint nào dùng `hasRole`, `hasAuthority`, `@PreAuthorize` hoặc kiểm tra quyền theo đối tượng.
6. **Kiểm thử cả nhánh tốt/xấu:** OIDC, OAuth2 không OIDC, viewer/editor/admin, unknown role, claim thiếu, claim sai cấu trúc, role thay đổi, tenant khác.
7. **Xác minh với provider thật** sau khi unit test pass: claim có đúng trong ID Token/UserInfo và mapper được gọi trong luồng login đúng.
8. **Kiểm soát vòng đời authorities:** đăng xuất, session timeout, role revocation, đồng bộ nội bộ và reauthentication khi quyền thay đổi.
9. **Không bỏ những bảo vệ khác:** CSRF của web app dùng session/cookie, HTTPS, session fixation protection, kiểm soát secret, log an toàn và authorization ở service.

## 12. Tự kiểm tra

**1.** `email_verified: true` có tự tạo `ROLE_USER` không?  
**Trả lời:** Không. Đó là claim về trạng thái xác minh email; chỉ map thành authority nếu có chính sách ứng dụng rõ ràng, thường không dùng làm bằng chứng cấp quyền.

**2.** `app_roles: ["admin"]` ở ID Token có làm user thành admin ở mọi resource server không?  
**Trả lời:** Không. Mapper tạo authority cho **authentication của web app**. Resource server kiểm tra bearer token, audience và converter của chính nó.

**3.** Tại sao code dùng allowlist thay vì nối `"ROLE_" + role`?  
**Trả lời:** Để chỉ cấp các quyền ứng dụng đã định nghĩa, tránh tạo authority ngoài dự kiến từ claim không hợp lệ hoặc thay đổi schema.

**4.** Mapper có thể gọi API với access token ngay từ `mapAuthorities` không?  
**Trả lời:** Signature không có access token. Nếu cần token và network lookup, sử dụng custom OAuth2UserService/OidcUserService hoặc kiến trúc tra quyền khác phù hợp.

**5.** Có `ROLE_EDITOR` có nghĩa được sửa mọi tài liệu không?  
**Trả lời:** Không. Với tài liệu cụ thể còn cần kiểm tra chủ sở hữu, tenant, trạng thái và chính sách per-resource.

**6.** Nếu IdP cập nhật role ngay lúc user đang đăng nhập, quyền trong session có đổi ngay không?  
**Trả lời:** Thường không tự đổi nếu authentication chưa được xây dựng lại; cần chính sách refresh/re-login/thu hồi hoặc kiểm tra quyền động.

---

**Ghi nhớ:** `GrantedAuthoritiesMapper` là cầu nối giữa **claims/authorities sau OAuth2–OIDC login** và **`GrantedAuthority` của ứng dụng Spring Security Servlet**. Hãy xác định rõ nguồn claims, chỉ map từ allowlist, phân biệt `ROLE_` với `SCOPE_`, mặc định không nâng quyền khi claim thiếu hoặc sai, và luôn thực thi authorization theo ngữ cảnh tài nguyên.