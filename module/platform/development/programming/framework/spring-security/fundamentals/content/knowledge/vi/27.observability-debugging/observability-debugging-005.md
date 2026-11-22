# Kiểm tra quyền `ROLE_`, authority và scope khi quyết định không như dự kiến

> **Chủ đề:** Quan sát và gỡ lỗi các quyết định **authentication/authorization** trong Spring Security 6.x trên Servlet stack, với Java 17+ và Spring Boot 3.x. Trọng tâm là nhìn **quyền thực tế trong `Authentication`**, so khớp `hasRole`/`hasAuthority`, hiểu tiền tố `ROLE_` và `SCOPE_`, phân tích JWT/OAuth2 scopes, CSRF, filter chain và method security. Ví dụ chạy được dùng HTTP Basic để cô lập vấn đề; phần JWT là hướng dẫn tích hợp riêng, không giả định `UserDetailsService` được gọi cho mọi token.

## 1. Triệu chứng: đã đăng nhập nhưng vẫn 403

Một API có rule:

```java
.requestMatchers("/api/admin").hasRole("ADMIN")
```

Client đăng nhập thành công nhưng nhận **403 Forbidden**. Developer mở database thấy cột `role = ADMIN` và kết luận “Spring Security lỗi”. Thực tế rule mặc định **`hasRole("ADMIN")` tìm authority `ROLE_ADMIN`**, không phải chuỗi `ADMIN`. Nếu mapper tạo `SimpleGrantedAuthority("ADMIN")`, authentication có thể thành công nhưng authorization bị từ chối.

Một trường hợp khác: JWT có `"scope": "reports.read"` nhưng endpoint yêu cầu `hasAuthority("reports.read")`. Spring Security Resource Server thường chuyển scope hợp lệ sang authority **`SCOPE_reports.read`**. Rule so chuỗi không khớp thì request nhận 403 dù token vẫn hợp lệ.

Các vấn đề nên tách thành câu hỏi:

1. **Request có được xác thực không?** Principal có thực sự tồn tại và không phải anonymous? Với HTTP Basic/Bearer, credentials không hợp lệ thường dẫn tới 401; form login có thể redirect.
2. **Request đi qua `SecurityFilterChain` nào?** Một chain khác, `securityMatcher` khác hoặc rule rộng đặt trước có thể quyết định thay cho rule bạn nghĩ.
3. **`Authentication.getAuthorities()` hiện chứa chính xác chuỗi gì?** Không suy từ cột role, claim JSON hay lời kể của frontend.
4. **Authorization kiểm tra chuỗi gì?** `hasRole`, `hasAuthority`, `@PreAuthorize`, scope, role hierarchy, custom `AuthorizationManager` hay điều kiện ownership?
5. **Có cơ chế nào từ chối trước hoặc sau authorization không?** CSRF, account state, method security, ACL, tenant/owner check, exception handling?

**Mục tiêu học:** gỡ lỗi dựa trên bằng chứng theo đúng tầng; không “chữa 403” bằng cách cấp thêm quyền cao hoặc tắt bảo vệ.

## 2. Ba khái niệm dễ nhầm: role, authority và OAuth scope

### 2.1. `GrantedAuthority` là nền tảng chung

Trong Spring Security, `Authentication` chứa tập `GrantedAuthority`. Phần lớn cấu hình phổ thông biểu diễn quyền dưới dạng một chuỗi:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("SCOPE_reports.read");
new SimpleGrantedAuthority("invoice:approve");
```

Đây chỉ là **các giá trị minh họa** thuộc code có import `org.springframework.security.core.authority.SimpleGrantedAuthority`, không phải chương trình Java độc lập. Framework không buộc mọi quyền phải là `ROLE_...`: bạn có thể dùng `"invoice:approve"`, `"SCOPE_reports.read"` hoặc định dạng nghiệp vụ khác, miễn **producer** (nguồn authorities) và **consumer** (authorization rule) dùng cùng quy ước.

**Quy tắc quan trọng:** `hasAuthority("X")` kiểm tra authority có giá trị **đúng chuỗi `"X"`**. Ký tự hoa/thường, dấu chấm, dấu hai chấm và tiền tố đều có ý nghĩa. Một số cấu hình mở rộng (như role hierarchy) có thể thay đổi tập authority hiệu lực, nhưng không thể mặc định coi hai chuỗi khác nhau là tương đương.

### 2.2. `hasRole` thêm tiền tố mặc định

Mặc định, role prefix là `ROLE_`:

| Giá trị trong `Authentication` | Rule | Kết quả thông thường |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | **Cho phép** |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | **Cho phép** |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | **Từ chối** |
| `ADMIN` | `hasRole("ADMIN")` | **Từ chối** |
| `ADMIN` | `hasAuthority("ADMIN")` | **Cho phép** |
| `ROLE_USER` | `hasRole("ADMIN")` | **Từ chối** |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | **Cho phép** |
| `SCOPE_reports.read` | `hasRole("reports.read")` | **Từ chối** |

`hasRole("ADMIN")` là cách ngắn để yêu cầu role theo quy ước, còn `hasAuthority("ROLE_ADMIN")` nói rõ chuỗi cần có. Nếu ứng dụng tùy chỉnh default role prefix (ví dụ qua `GrantedAuthorityDefaults` hoặc API tương ứng ở một số tầng), phải kiểm cấu hình thực: đừng giả định mọi `hasRole` luôn ghép giống nhau ở mọi phiên bản và mọi cách triển khai.

**Không truyền `hasRole("ROLE_ADMIN")` theo thói quen:** trong DSL HTTP, argument của `hasRole` được thiết kế cho **tên role không có tiền tố**; một số API phát hiện và từ chối giá trị đã mang `ROLE_`. Viết `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` để tránh nhầm.

### 2.3. `roles(...)` và `authorities(...)` khi tạo user

`UserDetails` builder của Spring Security có hai cách biểu diễn:

```java
// Ví dụ trong code có UserDetails builder:
User.withUsername("alice")
    .password(storedHash)
    .roles("ADMIN")
    .build();  // cấp authority "ROLE_ADMIN"

User.withUsername("bob")
    .password(storedHash)
    .authorities("ROLE_ADMIN", "SCOPE_reports.read")
    .build();  // giữ nguyên các chuỗi đã khai báo
```

`.roles("ADMIN")` **tự thêm `ROLE_`**; `.authorities("ROLE_ADMIN")` giữ nguyên. Không đưa `"ROLE_ADMIN"` vào `.roles(...)` với kỳ vọng framework sẽ “hiểu thông minh” và không lặp tiền tố. Không hash lại `storedHash` trong quá trình tải `UserDetails`; password encoder dùng lúc tạo hash và kiểm tra password ở provider, không quyết định authority.

Nguồn cấp authority có thể là database mapping, LDAP, custom `UserDetailsService`, OAuth2/OIDC authorities, JWT claims converter hoặc service nội bộ. **Mục đầu tiên phải kiểm là output cuối cùng của nguồn đó trong `Authentication`**, không chỉ giá trị thô ở đầu vào.

### 2.4. Scope là quyền được biểu diễn thành authority trong Resource Server

OAuth2 *scope* biểu thị phạm vi token được cấp. Với Spring Security JWT Resource Server và `JwtGrantedAuthoritiesConverter` mặc định, claim quen thuộc `"scope"` hoặc `"scp"` được chuyển thành authority có tiền tố **`SCOPE_`**. Ví dụ:

```json
{
  "sub": "user-123",
  "scope": "reports.read reports.write"
}
```

Trong cấu hình JWT điển hình, kết quả là hai authorities `SCOPE_reports.read` và `SCOPE_reports.write`, **không phải** `reports.read`, `ROLE_reports.read` hoặc một authority duy nhất có chứa cả chuỗi cách nhau bằng dấu cách.

Các lưu ý quan trọng:

- Token phải được **xác minh** (chữ ký hoặc introspection, issuer, expiration, audience theo cấu hình yêu cầu) trước khi tin claim. Đừng decode một JWT chưa xác thực rồi tự cấp quyền từ JSON.
- `"scope"` và `"scp"` thường được dùng như hai tên claim thay thế, không phải quy tắc mọi nhà cung cấp đều tuân theo. Claim `permissions`, `roles`, `realm_access.roles` hoặc `resource_access` **không mặc định** được chuyển thành `ROLE_` hay `SCOPE_`.
- `JwtGrantedAuthoritiesConverter` hỗ trợ cấu hình tên claim và authority prefix khi token provider dùng quy ước khác. Không tự thêm `SCOPE_` lần nữa nếu converter đã thêm.
- Scope mô tả quyền của **token**, không tự chứng minh người dùng sở hữu bản ghi hoặc là member của tenant đang được yêu cầu. Với object/tenant access, vẫn cần chính sách authorization cấp dữ liệu.

## 3. Chẩn đoán HTTP 401, 403, 404 và redirect trước khi xem role

| Quan sát | Tầng nên kiểm đầu tiên | Ví dụ nguyên nhân |
| --- | --- | --- |
| **401** khi gọi GET API Basic | Authentication | Không gửi Basic credentials, mật khẩu sai, user không tồn tại, provider không chấp nhận credentials. |
| **401** khi gọi JWT API | Bearer token validation | Token hết hạn, signature/issuer/audience sai, thiếu Bearer token, decoder/introspector lỗi. |
| **403** trên GET sau login | Authorization | Thiếu `ROLE_...`, `SCOPE_...`, exact authority hoặc owner/tenant permission. |
| **403** trên POST/PATCH/DELETE | **CSRF trước**, sau đó authorization | Thiếu/sai CSRF token; hoặc có token nhưng thiếu quyền. |
| **404** cho ID đã biết | Object-level policy hoặc routing | Query có owner/tenant predicate và cố ý che tài nguyên ngoài scope; hoặc thực sự không có route/item. |
| **302** về login | Authentication entry point của form login | Cấu hình interactive login thay vì Basic/Bearer API. |
| **200** trái mong đợi | Chain/matcher/test setup | Rule quá rộng `permitAll`, request trúng chain khác, test đã tắt filters. |

**Đừng sửa role khi chưa phân biệt authentication với authorization.** Với Spring Security, request chưa xác thực có thể được xử lý qua `AuthenticationEntryPoint` (401 hoặc redirect), còn user được xác thực nhưng không đủ quyền thường được `AccessDeniedHandler` xử lý thành 403. Với CSRF, filter có thể từ chối request trước khi controller/service chạy.

### 3.1. Anonymous không phải tài khoản đăng nhập thật

Spring Security có thể đặt `AnonymousAuthenticationToken` vào `SecurityContext` cho anonymous request. Vì thế kiểm đơn lẻ `authentication != null` hoặc `authentication.isAuthenticated()` **không luôn chứng minh người dùng đã đăng nhập thật**, do anonymous token có thể tự mang trạng thái authenticated. Sử dụng `AuthorizationManager`/`authenticated()` của Spring Security hoặc `AuthenticationTrustResolver` khi cần phân biệt; không tự dùng `getName()` của anonymous làm user ID.

### 3.2. `ROLE_` và `SCOPE_` không tương đương

Một user có `ROLE_ADMIN` **không tự có** `SCOPE_reports.read`. Một JWT có `SCOPE_reports.read` **không tự có** `ROLE_ADMIN`. Nếu ứng dụng có quy tắc “admin được xem mọi báo cáo”, phải **thiết kế chính sách rõ ràng**, ví dụ kết hợp kiểm `hasRole("ADMIN") OR hasAuthority("SCOPE_reports.read")` khi thật sự hợp lệ theo nghiệp vụ; không tự động grant mọi scope chỉ vì tên role có chữ ADMIN.

**Không dùng chính sách “để hết 403”** bằng cách `permitAll()`, `.csrf(disable)` hoặc thêm `ROLE_ADMIN` cho mọi tài khoản. Đó là mở rộng quyền và có thể biến lỗi cấu hình thành lỗ hổng bảo mật.

## 4. Bước đầu tiên khi debug: quan sát authorities hiệu lực

Giá trị quan trọng nhất là `Authentication` **đang dùng trong request bị từ chối**, sau quá trình authentication và authority conversion. Với endpoint đã xác thực, code có thể quan sát:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String username = authentication.getName();
    List<String> authorities = authentication.getAuthorities()
        .stream()
        .map(GrantedAuthority::getAuthority)
        .sorted()
        .toList();
    // Chỉ dùng ở môi trường debug/test được bảo vệ.
}
```

Đoạn này là **mẫu minh họa** cần imports `Authentication`, `SecurityContextHolder`, `GrantedAuthority`, `java.util.List` và môi trường có `SecurityContext`. Đừng trả ra `authentication.getCredentials()`, password hash, raw JWT, session cookie hoặc toàn bộ principal tùy tiện. Hạn chế log principal và authorities tại production theo chính sách bảo vệ dữ liệu.

### 4.1. Quan sát an toàn trong bài thực hành

Trong ví dụ runnable ở phần 5 có một endpoint `/api/me` yêu cầu đăng nhập, chỉ trả `username` và chuỗi authorities, đã sắp xếp để test ổn định. **Đây là endpoint demo**, không khuyến nghị bật vô điều kiện ở production. Nếu cần diagnostics thật, dùng quyền admin/support, redaction, audit và tắt sau khi khắc phục.

Giả sử response như sau:

```json
{
  "username": "analyst",
  "authorities": [
    "ROLE_ANALYST",
    "SCOPE_reports.read",
    "SCOPE_reports.write"
  ]
}
```

Đối chiếu từng ký tự với rule:

- `hasRole("ADMIN")` cần `ROLE_ADMIN` → không có → 403.
- `hasAuthority("SCOPE_reports.read")` → có → cho phép.
- `hasAuthority("reports.read")` → **không có** → 403.
- `hasAuthority("ROLE_ANALYST")` → có → cho phép.
- `hasRole("ANALYST")` → có → cho phép theo default prefix.

**Chú ý:** UI có thể hiển thị “Analyst” hay “Admin” nhưng không quyết định authority phía backend. Đừng dựa vào tên menu, cookie tự đặt hoặc role trong JSON không xác minh.

## 5. Ví dụ Java 17+ chạy được: tìm lỗi role và scope bằng HTTP Basic

Ví dụ dùng Spring Boot 3.x với hai account và role/scope-like authorities được gán trực tiếp:

- `analyst` / `analyst123`: `ROLE_ANALYST`, `SCOPE_reports.read`, `SCOPE_reports.write`.
- `admin` / `admin123`: `ROLE_ADMIN`, **không có scope reports**.

Mục đích là **minh họa chuỗi authority**, không giả lập JWT verification. Trong ứng dụng thật, `SCOPE_...` thường xuất phát từ Bearer token converter, nhưng `hasAuthority` vẫn có thể kiểm chính xác cùng chuỗi được cấp bởi một nguồn authentication khác.

### 5.1. Cấu trúc Gradle

`settings.gradle`:

```groovy
rootProject.name = 'authority-diagnostics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Phiên bản Spring Boot **3.3.5** là phiên bản **ghim minh họa**, không phải bản mới nhất. Spring Boot quản lý các artifact Spring Security và test cùng họ phiên bản. Có thể sử dụng `gradle test` với Gradle tương thích hoặc Gradle Wrapper. JDK 17+ và quyền tải dependency từ các kho đã cấu hình là điều kiện để chạy demo.

### 5.2. Mã ứng dụng đầy đủ

Tạo tệp `src/main/java/demo/diagnostics/AuthorityDiagnosticsApplication.java`:

```java
package demo.diagnostics;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDiagnosticsApplication.class, args);
    }
}

record IdentityView(String username, List<String> authorities) {}

@RestController
class DemoEndpoints {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    IdentityView me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new IdentityView(authentication.getName(), authorities);
    }

    @GetMapping("/api/admin")
    String roleAdmin() {
        return "admin-role-ok";
    }

    @GetMapping("/api/admin/exact")
    String exactAdmin() {
        return "admin-authority-ok";
    }

    @GetMapping("/api/admin/strict")
    String strictAdmin() {
        return "plain-admin-ok";
    }

    @GetMapping("/api/reports")
    String reports() {
        return "reports-read";
    }

    @PostMapping("/api/reports/export")
    @ResponseStatus(HttpStatus.ACCEPTED)
    String exportReports() {
        return "export-request-accepted";
    }
}

@Configuration
class DemoSecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("analyst")
                .password(encoder.encode("analyst123"))
                .authorities(
                    "ROLE_ANALYST",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write"
                )
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/reports/export")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/admin/exact")
                    .hasAuthority("ROLE_ADMIN")
                .requestMatchers("/api/admin/strict")
                    .hasAuthority("ADMIN")
                .requestMatchers("/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

**Quan sát:** `DemoSecurityConfiguration` cấp `ROLE_ADMIN` cho admin qua `.roles("ADMIN")`; endpoint `/api/admin/strict` cố tình yêu cầu **`hasAuthority("ADMIN")`** để minh họa một rule sai nếu người viết định kiểm role `ADMIN`. Admin thật vẫn nhận 403 ở endpoint strict vì **không tồn tại authority `ADMIN` trần**. Ngược lại, `/api/admin` dùng `hasRole("ADMIN")` và `/api/admin/exact` dùng `hasAuthority("ROLE_ADMIN")` đều cho admin đi qua.

Endpoint `/api/reports` dùng `SCOPE_reports.read` và POST export dùng `SCOPE_reports.write`: analyst được phép; admin không tự có scope. Rule POST xếp trước rule GET. Chính sách CSRF Servlet vẫn bật mặc định; HTTP Basic được dùng để minh họa 401/403, không bật form login redirect.

`@RestController` và `DemoSecurityConfiguration` là package-private classes trong cùng tệp với public class ứng dụng, nên code hợp lệ theo Java. Trong production không để các account demo hard-coded và không mở endpoint chẩn đoán authorities vô hạn chế.

### 5.3. Kết quả cụ thể khi chạy bằng curl

Khởi động ở thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`; nếu chưa có Gradle Wrapper, dùng `gradle bootRun` với một bản Gradle 8.x tương thích. Mặc định demo lắng nghe tại `localhost:8080`.

Các lệnh Bash sau hiển thị **chỉ HTTP status**, để không phụ thuộc body:

```bash
# 1. Public
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/public

# 2. Protected không credentials
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me

# 3. Mật khẩu sai
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:wrong http://localhost:8080/api/me

# 4. Đúng role ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin

# 5. Exact authority ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/exact

# 6. Cố ý so sai "ADMIN" với "ROLE_ADMIN"
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/strict

# 7. Analyst thiếu ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:analyst123 http://localhost:8080/api/admin

# 8. Analyst có scope-like authority đọc reports
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:analyst123 http://localhost:8080/api/reports

# 9. Admin có role nhưng thiếu scope reports.read
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/reports
```

Mỗi lệnh in một dòng trạng thái, kết quả dự kiến theo thứ tự:

```text
200
401
401
200
200
403
403
200
403
```

Để xem authorities thực của analyst trong demo:

```bash
curl -s -u analyst:analyst123 \
  http://localhost:8080/api/me
```

Response JSON dự kiến (Spring MVC/Jackson có thể không chèn khoảng trắng):

```json
{"username":"analyst","authorities":["ROLE_ANALYST","SCOPE_reports.read","SCOPE_reports.write"]}
```

Đây là **giá trị sau authentication**, đủ để giải thích các rule đã kiểm mà không phải suy đoán từ bảng roles. Với admin, list authorities chỉ có `ROLE_ADMIN`.

**Lưu ý:** `curl` với HTTP Basic qua HTTP thường chỉ được dùng trên localhost để học. Production phải dùng TLS/HTTPS và cơ chế quản lý credentials phù hợp. Với POST và CSRF mặc định, không thể chỉ gửi `-u` rồi mong nhận 202; dùng MockMvc test ở phần tiếp theo để tạo token hợp lệ hoặc thiết kế luồng CSRF client đầy đủ.

## 6. Kiểm thử chính xác bằng `spring-security-test`

Tạo `src/test/java/demo/diagnostics/AuthorityDiagnosticsTest.java`. Test dùng app context đầy đủ, filter chain thật và in-memory user service; không mock authentication provider trong các ca cần xác thực password.

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorityDiagnosticsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousOnProtectedEndpointGets401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("analyst", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualAuthoritiesAppearInAuthenticatedPrincipal()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username")
                .value("analyst"))
            .andExpect(jsonPath("$.authorities",
                hasItems(
                    "ROLE_ANALYST",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write"
                )));
    }

    @Test
    void hasRoleAdminPassesWhenUserHasRoleAdmin()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-role-ok"));
    }

    @Test
    void exactRoleAuthorityAlsoPasses() throws Exception {
        mvc.perform(get("/api/admin/exact")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }

    @Test
    void exactPlainAdminIsDifferentFromRoleAdmin()
            throws Exception {
        mvc.perform(get("/api/admin/strict")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystWithoutRoleAdminIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystWithReadScopeAuthorityIsAllowed()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-read"));
    }

    @Test
    void adminRoleDoesNotGrantMissingReportScope()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfRejectsWriteEvenWithScope()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndWriteAuthorityPermitExport()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("analyst", "analyst123"))
                .with(csrf()))
            .andExpect(status().isAccepted())
            .andExpect(content().string("export-request-accepted"));
    }

    @Test
    void validCsrfDoesNotGrantMissingWriteScope()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void withMockUserRoleCreatesRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void withMockUserExactAuthorityDoesNotSatisfyHasRole()
            throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void exactScopeAuthoritySatisfiesReportRule() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "reports.read")
    void missingScopePrefixFailsExactAuthorityCheck()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }
}
```

Đối với `@WithMockUser`, Spring Security Test **tạo principal giả** trong `SecurityContext`, không kiểm password. Vì thế test `WithMockUser` chỉ chứng minh behavior theo authorities được **giả lập**; các ca `httpBasic(...)` mới dùng filter/provider/encoder để kiểm credentials thật. Đừng dùng `@WithMockUser` làm bằng chứng JWT đã được verify hay account tồn tại trong database.

**Về POST:** Test đầu nhận 403 vì không có CSRF token theo cấu hình demo. Test thứ hai thêm `.with(csrf())` và analyst có `SCOPE_reports.write`, nên trả 202. Test thứ ba **có CSRF hợp lệ nhưng không có scope**, vì vậy 403 là lỗi authorization, không phải CSRF. Chính sự đối chiếu này giúp tìm đúng nguyên nhân.

### 6.1. Chạy test

Dùng Gradle Wrapper trong thư mục dự án:

```bash
./gradlew test
```

Windows:

```bat
gradlew.bat test
```

Chỉ chạy suite:

```bash
./gradlew test --tests demo.diagnostics.AuthorityDiagnosticsTest
```

Test thành công khi các assertion khớp; không dự đoán nguyên văn stdout Gradle vì còn phụ thuộc phiên bản Gradle, môi trường và log. Có thể thử **cố tình** đổi rule `/api/reports` sang `hasAuthority("reports.read")` trong bản sao dev rồi chạy lại test: các ca mô tả `SCOPE_reports.read` phải thất bại, chứng tỏ suite nhạy với bug về prefix.

## 7. Chẩn đoán riêng cho JWT/OAuth2 Resource Server

Ví dụ phần 5 dùng Basic authentication để dễ cô lập role/authority. Với JWT Resource Server, đường đi khác:

```text
Authorization: Bearer <JWT>
       |
       v
BearerTokenAuthenticationFilter
       |
       v
JwtAuthenticationProvider / JwtDecoder
       |  chữ ký, issuer, expiry, audience theo cấu hình
       v
JwtAuthenticationToken
       |  claim scope/scp -> JwtGrantedAuthoritiesConverter
       v
Authentication.getAuthorities() (ví dụ SCOPE_reports.read)
       |
       v
AuthorizationFilter / method security -> 200 hoặc 403
```

Đừng mong `UserDetailsService.loadUserByUsername` tự được gọi trên mọi JWT request; Resource Server thường xác thực token qua decoder/provider. Cũng đừng đọc trực tiếp `jwt.getClaimAsString("role")` trong controller để tự vượt qua authorization rules mà không kiểm claim và policy.

### 7.1. Từ claims đến chuỗi authority

Ví dụ JWT đã được xác minh:

```json
{
  "sub": "user-123",
  "scope": "reports.read reports.write",
  "roles": ["ADMIN"],
  "permissions": ["invoice:approve"]
}
```

Với converter scopes mặc định, Spring Security Resource Server thường cấp:

```text
SCOPE_reports.read
SCOPE_reports.write
```

`roles: ["ADMIN"]` và `permissions: ["invoice:approve"]` **không tự nhiên trở thành** `ROLE_ADMIN` hay authority `invoice:approve` nếu chưa cấu hình converter phù hợp. Nếu endpoint yêu cầu `hasRole("ADMIN")`, token chỉ có scope reports vẫn bị 403, và đó có thể là **đúng thiết kế**, không phải lỗi login.

### 7.2. Tùy chỉnh converter khi provider dùng claim khác

Một provider có thể dùng claim `"permissions"` chứa các chuỗi như `"reports.read"` thay cho `"scope"`. Khi dùng Spring Security Resource Server với dependency `spring-boot-starter-oauth2-resource-server`, có thể ánh xạ như sau:

```java
// Đoạn minh họa tích hợp cho cấu hình JWT Resource Server;
// KHÔNG thêm nguyên xi vào demo HTTP Basic phía trên.

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();

    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(permissions);
    return converter;
}

@Bean
SecurityFilterChain jwtChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/jwt-api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/jwt-api/reports")
                .hasAuthority("PERM_reports.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter())
            )
        );
    return http.build();
}
```

Cần imports cho `@Bean`, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `HttpSecurity`, `SecurityFilterChain` và cấu hình decoder hợp lệ (ví dụ trusted issuer/JWK set và kiểm audience nếu cần). Đây là **đoạn code định hướng**, không phải bản chạy độc lập: không kèm cấu hình issuer/decoder, routing các chain khác hay token thật. Nếu tích hợp vào ứng dụng có chain Basic hiện hữu, phải thiết kế `@Order`/`securityMatcher` để tránh chain không mong muốn bắt request.

Nếu muốn authorities `"ROLE_ADMIN"` từ một claim roles, cần converter chuyên dụng kiểm soát prefix `ROLE_`, xử lý format claim và hợp nhất với scope authorities một cách có chủ đích. Không tự gộp mọi role/scope/permission chưa được nhà cung cấp danh tính xác minh.

**Đặc biệt:** `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("permissions")` chỉ định một claim; nó **không mặc nhiên hợp nhất** cả scope và permissions. Nếu muốn hai nguồn, hãy tự xây converter kết hợp có kiểm thử hoặc dùng delegation APIs thích hợp.

### 7.3. `jwt()` trong MockMvc test không phải kiểm thử chữ ký

Spring Security Test có `.with(jwt())` để giả lập một JWT principal/authorities cho các bài test authorization. Nó **không tự chứng minh** token production được decode đúng, ký hợp lệ hay claims được ánh xạ đúng từ issuer thật. Muốn kiểm `JwtDecoder`, issuer/audience, expiry và converter thực, cần bài test riêng với decoder/config tương ứng hoặc integration test qua HTTP Bearer token đã được tạo/kiểm soát phù hợp.

Ví dụ fragment (chỉ dành cho test có module Resource Server và imports tương ứng):

```java
mvc.perform(get("/jwt-api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("PERM_reports.read")
        )))
    .andExpect(status().isOk());
```

Trong fragment này, `jwt()` đặt authorities trực tiếp nên **bỏ qua câu hỏi claim `permissions` có được converter tạo ra authority đúng hay không**. Để test converter, phải đưa JWT fixture qua chính converter hoặc chạy đường token thật và kiểm `Authentication.getAuthorities()`. Không chọn fake authorities để test mà vô tình giấu lỗi mapping.

### 7.4. Chẩn đoán token thiếu scope

Checklist riêng:

1. Response 401 hay 403? **401** thường là token bị từ chối ở authentication; **403** sau authentication là thiếu authority/policy.
2. Token đã có chữ ký, issuer, audience, expiry được validate chưa?
3. Kiểm tên và kiểu claim thực (`scope` string, `scp` array, `permissions` list, nested roles).
4. Converter nào được gắn vào JWT authentication? Nó có dùng đúng claim name và prefix không?
5. `Authentication.getAuthorities()` cuối cùng là gì? Có `SCOPE_reports.read` hay `PERM_reports.read` không?
6. Rule kiểm `hasAuthority("SCOPE_reports.read")`, `hasRole("ADMIN")` hay permission khác?
7. Có nhiều filter chains hoặc resource servers cho các routes khác nhau không?
8. Scope tồn tại chưa đủ quyền theo **owner/tenant**, ACL hoặc method security? Nếu chưa đủ, 403/404 vẫn có thể là đúng.

Không đăng nguyên JWT/cookie/password lên chat/log để debug. Có thể xác minh claims trong môi trường an toàn với dữ liệu đã redacted, nhưng tuyệt đối không tin payload chưa verify.

## 8. Khi log cho biết “access denied” nhưng không rõ rule nào

### 8.1. Bật security logging tạm thời ở môi trường dev/test

Có thể thêm cấu hình **chỉ trong profile debug/test**:

```properties
logging.level.org.springframework.security=TRACE
```

Đối với ứng dụng lớn, nên chọn logger cụ thể và giảm xuống DEBUG khi đủ thông tin. Log TRACE giúp quan sát filter chain, authentication và authorization decisions, nhưng **nội dung tùy phiên bản**, và log bảo mật có thể chứa thông tin nhạy cảm. Không bật vô thời hạn trong production; giới hạn quyền đọc log, thời gian lưu và không ghi token/password/raw HTTP Authorization header. Không khẳng định mọi TRACE entry sẽ hiển thị đúng `GrantedAuthority` hoặc biểu thức bị từ chối; dùng kết hợp test diagnostics.

### 8.2. Theo dõi đúng chuỗi kiểm tra

Khi nhận 403, đi từ ngoài vào trong:

```text
Request URL + HTTP method
  |
  v
SecurityFilterChain matching?
  |  - securityMatcher, @Order, filter chain khác
  v
Authentication type and principal?
  |  - anonymous, Basic, session, JWT, oauth2Login
  v
Authentication.getAuthorities()?
  |  - ROLE_..., SCOPE_..., exact business permissions
  v
Authorization rules?
  |  - requestMatchers, hasRole, hasAuthority, order
  v
Other checks?
  |  - CSRF filter, @PreAuthorize, @PostAuthorize
  |  - owner / tenant / ACL in service or repository
  v
Controller response / exception handler
```

**Về matcher order:** trong `authorizeHttpRequests`, các quy tắc được xét theo thứ tự khai báo, nên rule rộng đứng trước rule cụ thể có thể bắt request. Ví dụ sai về chủ đích:

```java
// Sai nếu muốn /api/admin/** có policy chặt hơn:
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Khi `/api/**` được xét trước và match, policy admin phía sau có thể không được thực thi. Đặt rule cụ thể trước rule chung. Với nhiều chain, `securityMatcher` quyết định chain nào áp dụng **trước khi** các `requestMatchers` của chain đó hoạt động. Chỉ chỉnh một rule mà request chưa từng đi qua chain đó sẽ không cải thiện kết quả.

### 8.3. Method security có thể từ chối sau HTTP rule

Một endpoint có `.anyRequest().authenticated()` nhưng service thực được gọi có:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(Long invoiceId) {
    // Business logic
}
```

Khi `@EnableMethodSecurity` được bật và lời gọi đi qua Spring proxy, method có thể từ chối user thiếu authority **ngay cả khi HTTP rule cho qua**. Đoạn trên là minh họa phương thức thuộc Spring bean có import `@PreAuthorize`, **không phải chương trình Java độc lập**.

Khi debug, xem:

- App có `@EnableMethodSecurity` và gọi đúng bean proxy không?
- Principal authorities có `invoice:approve` chính xác không?
- Có custom `PermissionEvaluator`, role hierarchy, `@PostAuthorize` hay các annotation kết hợp không?
- Một `@WebMvcTest` đang mock service có thể bỏ qua method security thật; cần integration test với service bean thực.
- Self-invocation trong cùng object có thể không đi qua proxy; điều này có thể làm policy **không áp dụng**, nguy hiểm hơn cả 403. Đảm bảo kiến trúc lời gọi qua bean proxy phù hợp.

### 8.4. Custom role prefix và role hierarchy

`GrantedAuthorityDefaults` có thể thay đổi role prefix cho những điểm dùng role expression/handler tương ứng. Nếu hệ thống đã tùy biến, cần xác nhận **cấu hình hiệu lực thực tế** của request authorization và method authorization, đặc biệt khi đã nâng phiên bản Spring Security. Không suy từ một bean duy nhất rằng mọi API đều thống nhất prefix.

Role hierarchy (ví dụ admin bao hàm một số quyền của user) có thể cho phép rule dựa trên **reachable authorities**, ngay cả khi bạn chỉ nhìn thấy authorities gốc trong `Authentication`. Vì vậy khi câu trả lời không khớp bảng ở mục 2, kiểm có custom `RoleHierarchy`, `AuthorizationManager`, method interceptor hoặc trust resolver nào được đăng ký. Viết test các vai trò kế thừa, không tự giả định “ROLE_ADMIN có tất cả scope”.

## 9. Những sai lầm dễ tạo 403 hoặc làm mất an toàn

### 9.1. Gán role từ request client để hết lỗi

**Không được** nhận `"role": "ADMIN"` hoặc `"scope": "reports.write"` trong body login/request rồi chuyển thẳng thành `GrantedAuthority`. Quyền phải đến từ một nguồn phía server hoặc claims đã được xác minh và policy chấp nhận. Nếu không, attacker tự cấp quyền.

### 9.2. So sánh sai tiền tố

Rule `hasAuthority("SCOPE_read")` không khớp `SCOPE_reports.read`. Rule `hasRole("ADMIN")` không khớp `ADMIN` trần theo default convention. Tạo bảng producer/consumer rõ ràng:

| Nguồn cấp | Giá trị thực | Rule thích hợp |
| --- | --- | --- |
| `.roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`. |
| `.authorities("ADMIN")` | `ADMIN` | `hasAuthority("ADMIN")` khi chủ đích dùng quyền trần. |
| JWT scope `"reports.read"` với converter mặc định | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")`. |
| Custom permission `"invoice:approve"` | `invoice:approve` | `hasAuthority("invoice:approve")`. |
| Custom JWT prefix `"PERM_"` | `PERM_reports.read` | `hasAuthority("PERM_reports.read")`. |

Chỉ đổi rule nếu đúng nghiệp vụ; đôi khi cần sửa mapper vì account được **cấp authority sai**. Đổi tất cả endpoints sang `permitAll()` là cách che lỗi nguy hiểm.

### 9.3. Chỉ test với `@WithMockUser`

`@WithMockUser(roles="ADMIN")` tự tạo `ROLE_ADMIN` trong test. Nếu database production mapper chỉ tạo `ADMIN`, test vẫn có thể pass nhưng API thật 403. Phải có integration test với **nguồn user/token converter thực**, và kiểm `Authentication.getAuthorities()` trong request đó.

### 9.4. JWT converter bị thay mà không biết

Khi thay converter để đọc `"permissions"`, scope từ `"scope"` có thể không còn được tạo nếu converter mới chỉ xử lý một claim. Một endpoint từng có `SCOPE_reports.read` có thể bắt đầu 403. Test cả mapping `permissions` lẫn scope nếu cả hai cần dùng; không chỉ test list claims thô.

### 9.5. `hasRole` và `hasAuthority` bị lẫn trong method security

`@PreAuthorize("hasRole('ADMIN')")` và `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` thường cùng kiểm default role, trong khi `@PreAuthorize("hasAuthority('ADMIN')")` thì khác. Cẩn trọng giữa request-level DSL và method expressions khi có custom role prefix.

### 9.6. 403 vì CSRF nhưng lại thêm quyền

Với POST trong ví dụ, dù analyst có `SCOPE_reports.write`, thiếu CSRF token vẫn 403. Test thêm `.with(csrf())` rồi phân biệt. Với app chỉ dùng Bearer token không nhận cookie tự động, chính sách CSRF có thể khác; quyết định bật/tắt phải dựa vào mô hình đe dọa thực tế, không chỉ vì “POST bị 403”.

### 9.7. API trả 200 nhưng dữ liệu ngoài scope

Có `SCOPE_reports.read` không có nghĩa user được đọc mọi báo cáo của mọi tổ chức. Role/scope kiểm quyền **chức năng**, còn owner/tenant/ACL kiểm quyền **bản ghi**. Nếu service dùng `findById(id)` không scope, user vẫn có thể xem dữ liệu người khác dù mọi test `hasAuthority` đều đúng. Dùng repository query theo `ownerUserId`/`authorizedTenantId` và test đổi ID chéo user.

### 9.8. Debug sai `SecurityContext` trong async/job

`SecurityContextHolder` thường dùng ngữ cảnh gắn thread; code `@Async`, scheduled job, message consumer không tự có principal HTTP hợp lệ. Không fallback thành admin hoặc bỏ check khi không có context. Với job nền, truyền scope/identity đã được xác minh bằng cơ chế phù hợp, không tái sử dụng tùy tiện credentials từ request.

### 9.9. Caching authorities không cập nhật

User vừa bị thu hồi quyền nhưng session/token hoặc cache còn giữ authorities cũ; endpoint tiếp tục cho phép. Ngược lại, user vừa được cấp quyền mà JWT cũ chưa chứa scope mới sẽ bị 403. Quy hoạch token TTL, invalidation/session refresh và chính sách thu hồi quyền theo độ nhạy. Không coi một thay đổi trong bảng roles là tác động tức thì lên mọi token đang lưu hành.

## 10. Quy trình điều tra nhanh một trường hợp 403

Giả sử báo lỗi: “Admin mở `/api/reports` nhận 403, nhưng báo cáo vẫn hiện ở giao diện”.

**Bước 1 — tái hiện request:** ghi lại HTTP method, URL, status, request ID, cơ chế auth. Không sao chép token/password vào ticket.

**Bước 2 — xác nhận authentication:** thử endpoint đã xác thực tương đương; xem request hiện có principal thật hay không, password/token đã qua validation chưa. Nếu 401 thì phải xử lý authentication trước.

**Bước 3 — đọc authorities hiệu lực:** trong test/safe diagnostics, admin có `ROLE_ADMIN` nhưng không có `SCOPE_reports.read`.

**Bước 4 — đối chiếu rule:** `/api/reports` yêu cầu `hasAuthority("SCOPE_reports.read")`. Theo policy hiện tại, 403 là **kết quả đúng**. Nếu nghiệp vụ muốn admin xem reports, hãy duyệt và thực thi một policy rõ ràng, thay vì đổi không kiểm soát.

**Bước 5 — kiểm tầng khác:** nếu đã có scope mà vẫn 403, kiểm CSRF (với method unsafe), filter chain, `@PreAuthorize`, quyền dữ liệu/tenant, custom access decision và exception mapper.

**Bước 6 — viết hồi quy:** một test positive (principal có quyền thì 200), một test negative (thiếu quyền thì 403); với POST có thêm case CSRF có/không; với dữ liệu có case owner/tenant. Chỉ kết luận fix khi test thực sự chạy qua đúng chain/provider.

### 10.1. Ma trận xác minh tối thiểu

| Case | Nhóm kiểm thử | Kỳ vọng demo |
| --- | --- | --- |
| Không credentials đến `/api/me` | Authentication | 401 |
| Sai mật khẩu analyst | Authentication | 401 |
| Admin vào `/api/admin` | Role | 200 |
| Analyst vào `/api/admin` | Role | 403 |
| Admin vào `/api/admin/exact` | Exact `ROLE_ADMIN` | 200 |
| Admin vào `/api/admin/strict` | Exact `ADMIN` sai | 403 |
| Analyst vào `/api/reports` | Scope-like authority | 200 |
| Admin vào `/api/reports` | Không có scope | 403 |
| Analyst POST export không CSRF | CSRF | 403 |
| Analyst POST export + CSRF | CSRF + authority | 202 |
| Admin POST export + CSRF | Thiếu scope (không phải thiếu CSRF) | 403 |
| `@WithMockUser(authorities="reports.read")` | Sai prefix scope | 403 |

Tất cả test này đều có mặt trong suite ở phần 6; chúng cố ý kiểm **khả năng được phép và bị từ chối**, không chỉ “đăng nhập thành công”.

## 11. Tự kiểm tra kiến thức

**Tình huống 1:** `getAuthorities()` chỉ có `ROLE_SUPPORT`, nhưng method dùng `hasAuthority('SUPPORT')`. Vì sao 403?  
**Đáp án:** `hasAuthority` so chuỗi chính xác; `SUPPORT` khác `ROLE_SUPPORT`. Chọn `hasRole('SUPPORT')` theo mặc định hoặc `hasAuthority('ROLE_SUPPORT')` nếu đúng policy.

**Tình huống 2:** JWT `"scope": "orders.read orders.write"`, resource server converter mặc định, rule `hasAuthority('orders.read')`. Có khớp không?  
**Đáp án:** Không; converter thường tạo `SCOPE_orders.read` và `SCOPE_orders.write`. Cần rule phù hợp hoặc converter theo thiết kế.

**Tình huống 3:** `@WithMockUser(roles="ADMIN")` pass, nhưng HTTP Basic với user `admin` thật nhận 403. Có mâu thuẫn không?  
**Đáp án:** Không; mock user tự có `ROLE_ADMIN`. Cần xem authorities của user thật sau `UserDetailsService`/provider, chain và mapping role.

**Tình huống 4:** User có `SCOPE_reports.write`, POST report trả 403 và chưa gửi CSRF. Có chắc thiếu scope không?  
**Đáp án:** Chưa. Thử POST với CSRF token hợp lệ; nếu thành công, nguyên nhân là CSRF. Nếu vẫn 403, mới tiếp tục điều tra quyền/các policy khác.

**Tình huống 5:** Admin có `ROLE_ADMIN`, API cần `SCOPE_reports.read`, không có role hierarchy/override. Có cần tự động cho phép không?  
**Đáp án:** Không. Role và scope là các authority khác nhau; chỉ cho phép nếu có policy rõ ràng.

**Tình huống 6:** Token có claim `"roles":["ADMIN"]` nhưng `Authentication` chỉ có `SCOPE_read`. Tại sao?  
**Đáp án:** JWT converter mặc định tập trung vào scopes; claim roles tùy nhà cung cấp không tự chuyển thành `ROLE_ADMIN`. Phải thiết kế/test custom converter nếu cần.

**Tình huống 7:** Principal có đúng authority, GET vẫn trả 404. Có phải authorization sai?  
**Đáp án:** Không nhất thiết. Endpoint có thể giới hạn truy vấn theo chủ sở hữu/tổ chức và cố tình trả 404 cho record ngoài scope, hoặc ID không tồn tại.

**Tình huống 8:** Request đi qua chain số 2 nhưng developer sửa rule của chain số 1. Kết quả?  
**Đáp án:** Thay đổi không ảnh hưởng request. Phải xác định `securityMatcher`, `@Order` và filter chain thực được chọn.

**Tình huống 9:** User đã bị thu hồi scope trong identity provider nhưng JWT cũ vẫn còn scope. Lỗi ở đâu?  
**Đáp án:** Token thường là snapshot quyền tại thời điểm cấp. Cần chính sách TTL, revocation, kiểm quyền hiện tại hoặc tái phát hành token phù hợp; sửa DB không tự xóa mọi token đang dùng.

**Tình huống 10:** Quan sát `authentication.isAuthenticated()==true` với anonymous token. Có thể coi là login hợp lệ?  
**Đáp án:** Không. Anonymous authentication có thể báo `true`; dùng cơ chế trust resolver/`authenticated()` đã được framework hỗ trợ để phân biệt.

## 12. Checklist thực hành

- [ ] Xác nhận request đúng HTTP method, URL và có status thực 401/403/404/302.
- [ ] Xác định authentication mechanism: Basic, form, session, JWT, OAuth2/OIDC.
- [ ] Kiểm đúng `SecurityFilterChain`, thứ tự chain và matcher.
- [ ] Quan sát **`Authentication.getAuthorities()` thực**, không đoán từ role/scope thô ở DB/JWT.
- [ ] So chính xác `ROLE_`, `SCOPE_`, chữ hoa/thường, dấu chấm và quyền custom.
- [ ] Với `hasRole`, hiểu tiền tố mặc định; với `hasAuthority`, hiểu exact string.
- [ ] Kiểm JWT converter, claim names, authority prefix; xác minh token đầy đủ.
- [ ] Kiểm role hierarchy, method security và custom permission evaluator nếu dùng.
- [ ] Với POST/PUT/PATCH/DELETE, phân biệt 403 do CSRF với 403 do thiếu authority.
- [ ] Với tài nguyên riêng/đa tenant, kiểm owner/organization scope sau quyền chức năng.
- [ ] Viết test positive **và** negative bằng auth flow phù hợp; không chỉ dùng mock principal.
- [ ] Không log raw token, password, credentials hoặc cấp thêm quyền để “sửa nhanh”.
- [ ] Không dùng `permitAll()`/tắt CSRF để che lỗi mà chưa có thiết kế và đánh giá rủi ro.
- [ ] Xác định hiệu lực cache/session/token khi thay đổi quyền.
- [ ] Chỉ bật security TRACE trong môi trường kiểm soát, tắt sau khi điều tra.

## 13. Kết luận và tài liệu đối chiếu

**Chuỗi suy luận đúng:** request → xác thực → `Authentication.getAuthorities()` → chain/rule thực tế → các bước CSRF, method security và owner/tenant → quyết định. Với Spring Security mặc định, `hasRole("ADMIN")` tìm `ROLE_ADMIN`, `hasAuthority("ROLE_ADMIN")` kiểm đúng chuỗi đó, còn scope JWT `"reports.read"` thường được ánh xạ thành `SCOPE_reports.read`. Khi 403 xảy ra, hãy xác minh từng mắt xích và viết một test đối chứng, không phỏng đoán từ nhãn vai trò trong UI.

Tài liệu chính thức và tiêu chuẩn:

- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet filter architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
