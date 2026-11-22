# Tiền tố ROLE_ và GrantedAuthorityDefaults trong Spring Security Servlet

> **Chủ đề:** Spring Security - servlet. **Nhóm:** Mô hình phân quyền. **Ví dụ:** Java 17+, Spring Boot 3.x, Spring Security 6.x. Bài trình bày cách `GrantedAuthority` biểu diễn quyền, ý nghĩa mặc định của `ROLE_`, điểm khác biệt giữa HTTP authorization và method security khi dùng `GrantedAuthorityDefaults`, các ví dụ và kiểm thử để tránh lỗi 403 do lệch tiền tố.

## 1. Bài toán điển hình: đã đăng nhập thành công nhưng vẫn bị từ chối

User `alice` đã đăng nhập, nhưng `Authentication.getAuthorities()` chứa:

```text
ADMIN
REPORT_READ
```

Ứng dụng dùng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Trong Spring Security 6 với HTTP authorization manager thông dụng, `hasRole("ADMIN")` yêu cầu authority **`ROLE_ADMIN`**, không phải `ADMIN`. User đã **authenticated**, nhưng **không đủ authority đúng chuỗi**, nên request có thể nhận 403 Forbidden.

Có hai hướng sửa đúng:

- Đổi rule HTTP sang `.hasAuthority("ADMIN")` nếu nguồn danh tính chủ ý cấp chuỗi `ADMIN`.
- Giữ `.hasRole("ADMIN")` nếu dữ liệu authority được chuẩn hóa thành `ROLE_ADMIN`.

`GrantedAuthorityDefaults("")` cho phép thay default role prefix trong **những thành phần có hỗ trợ đọc bean**; nó không sửa tự động tất cả HTTP rules, token, users hay authorities.

**Điểm mấu chốt:** phải biết Spring Security thực sự đang **so chuỗi nào**, chứ không chỉ nhìn từ "role" hoặc "admin" trong tên của database.

## 2. `GrantedAuthority` và role là hai lớp khái niệm

Spring Security dùng `Authentication` để biểu diễn một danh tính đã được xác thực. Thuộc tính `getAuthorities()` chứa các `GrantedAuthority` có thể dùng ở bước authorization.

Contract rút gọn:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Đây là chữ ký API để minh họa, không phải Java source file độc lập. Implementation phổ biến:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("ROLE_EDITOR");
new SimpleGrantedAuthority("REPORT_READ");
new SimpleGrantedAuthority("ORDER_APPROVE");
new SimpleGrantedAuthority("SCOPE_orders.read");
```

Mỗi `SimpleGrantedAuthority` lưu một **chuỗi quyền**. Interface không có enum role hay boolean isPermission. Ý nghĩa của chuỗi được quy định bởi ứng dụng và các authorization managers:

| Ví dụ | Quy ước có thể dùng | Có tự động được hiểu toàn hệ thống không? |
| --- | --- | --- |
| `ROLE_ADMIN` | Vai trò quản trị | `hasRole` thường hiểu `ROLE_`, nhưng hierarchy phải cấu hình riêng |
| `ROLE_SUPPORT` | Vai trò hỗ trợ | Không tự có quyền ADMIN |
| `REPORT_READ` | Quyền đọc báo cáo | Dùng `hasAuthority("REPORT_READ")` |
| `SCOPE_orders.read` | OAuth2 scope được chuyển đổi | Dùng exact authority, không phải `hasRole("orders.read")` |
| `TENANT_42_READ` | Ví dụ quyền theo tenant | Phải có thiết kế mapping/trust boundary rõ |

Authentication thành công không đồng nghĩa được vào mọi endpoint. Authorization có thể cần thêm owner/tenant, loại resource, trạng thái account và thao tác nghiệp vụ.

## 3. `ROLE_` là tiền tố quy ước, không phải permission tự sinh

Spring Security có quy ước lâu đời: tên role logic là `ADMIN`, nhưng khi được biểu diễn như authority thường là `ROLE_ADMIN`.

```text
Role logic:           ADMIN
Authority string:     ROLE_ADMIN

Role logic:           OPS
Authority string:     ROLE_OPS

Permission string:    REPORT_READ
OAuth scope string:   SCOPE_orders.read
```

Những phép kiểm tra quan trọng:

- `hasAuthority("ADMIN")` tìm đúng `ADMIN`.
- `hasAuthority("ROLE_ADMIN")` tìm đúng `ROLE_ADMIN`.
- `hasRole("ADMIN")` trong HTTP `AuthorityAuthorizationManager` của Spring Security 6 kiểm tra `ROLE_ADMIN`.
- `hasAnyAuthority("REPORT_READ", "REPORT_WRITE")` so exact danh sách được truyền.
- `hasAnyRole("ADMIN", "OPS")` dùng quy ước role, không tương đương `hasAnyAuthority("ADMIN", "OPS")`.

### Bảng đối chiếu mặc định

| Authorities của principal | Rule HTTP | Kết quả kiểm tra chuỗi |
| --- | --- | --- |
| `["ROLE_ADMIN"]` | `hasRole("ADMIN")` | Khớp |
| `["ADMIN"]` | `hasRole("ADMIN")` | Không khớp |
| `["ROLE_ADMIN"]` | `hasAuthority("ROLE_ADMIN")` | Khớp |
| `["ROLE_ADMIN"]` | `hasAuthority("ADMIN")` | Không khớp |
| `["ADMIN"]` | `hasAuthority("ADMIN")` | Khớp |
| `["REPORT_READ"]` | `hasAuthority("REPORT_READ")` | Khớp |
| `["REPORT_READ"]` | `hasRole("REPORT_READ")` | Không khớp khi thiếu `ROLE_REPORT_READ` |
| `["SCOPE_orders.read"]` | `hasAuthority("SCOPE_orders.read")` | Khớp |
| `["SCOPE_orders.read"]` | `hasRole("orders.read")` | Không khớp |

Bảng chỉ nói về so khớp authority của những API nêu trên, chưa tính role hierarchy hoặc authorization manager custom.

### Có nên truyền `hasRole("ROLE_ADMIN")`?

**Không.** API `AuthorityAuthorizationManager.hasRole` theo Spring Security 6 tự áp `ROLE_` và có thể từ chối argument đã bắt đầu bằng tiền tố.

```java
// Dùng tên role logic:
.hasRole("ADMIN")

// Hoặc so khớp chuỗi authority đầy đủ:
.hasAuthority("ROLE_ADMIN")

// Không nên:
.hasRole("ROLE_ADMIN")
```

Đừng đưa một giá trị vào `hasRole` chỉ vì nó trùng literal được lưu trong DB; phải hiểu method có tự gắn tiền tố hay không.

## 4. `roles()` khác `authorities()` khi tạo `UserDetails`

User builder có hai API gần giống nhau:

```java
UserDetails first = User.withUsername("first")
    .password(encodedPassword)
    .roles("ADMIN")
    .build();

UserDetails second = User.withUsername("second")
    .password(encodedPassword)
    .authorities("ADMIN")
    .build();
```

Đây là fragment cần `encodedPassword` hợp lệ, imports và context tương ứng.

- `roles("ADMIN")` thường tạo `SimpleGrantedAuthority("ROLE_ADMIN")`.
- `authorities("ADMIN")` tạo authority đúng chuỗi `ADMIN`.

Kết quả `getAuthorities()` dạng:

```text
first  -> [ROLE_ADMIN]
second -> [ADMIN]
```

**Quan trọng:** kể cả khi thêm `GrantedAuthorityDefaults("")`, `User.UserBuilder.roles("ADMIN")` không tự chuyển thành `authorities("ADMIN")`. Hai API có contract riêng.

Điều tương tự thường xảy ra trong test:

- `@WithMockUser(roles = "ADMIN")` hoặc `user("u").roles("ADMIN")` cấp `ROLE_ADMIN`.
- `@WithMockUser(authorities = "ADMIN")` hoặc `user("u").authorities(...)` cấp `ADMIN`.

Nếu production lưu authority `ADMIN` nhưng test fixture lại tạo `ROLE_ADMIN`, bài test có thể xanh giả hoặc đỏ giả so với dữ liệu thật.

## 5. Bean `GrantedAuthorityDefaults` là gì?

Spring Security cung cấp kiểu `org.springframework.security.config.core.GrantedAuthorityDefaults`. Nó cấu hình **default role prefix cho các thành phần được thiết kế đọc nó**.

Ví dụ prefix rỗng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("");
}
```

Hoặc nếu tổ chức có naming convention khác:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
```

Hai fragments là **phương án thay thế nhau**; không tạo hai bean cùng loại và giá trị mâu thuẫn trong một cấu hình.

Prefix rỗng có thể làm method-security expression `hasRole('ADMIN')` xem authority `ADMIN` thay vì `ROLE_ADMIN`, **nếu expression handler liên quan sử dụng bean đó**.

### Bean này không làm gì?

Nó **không**:

- Thay đổi các chuỗi trong `Authentication.getAuthorities()` của phiên hiện tại.
- Xóa prefix trên `SimpleGrantedAuthority("ROLE_ADMIN")` đã tồn tại.
- Thay logic của `User.withUsername(...).roles("ADMIN")`.
- Viết lại role/authority trong JWT hoặc database.
- Đổi scope prefix `SCOPE_` của OAuth2 converter.
- Tự tạo role hierarchy hoặc cấp quyền mới cho user.
- Bảo đảm mọi API `hasRole` trong mọi Spring Security version được cấu hình giống nhau.

Sự khác biệt giữa **đổi cách so khớp** và **đổi dữ liệu được cấp** là chìa khóa để tránh mismatch.

### Vì sao khai báo static bean?

Một số thành phần method security có thể được tạo sớm trong quá trình cấu hình. Với Spring Security 6, khai báo `static @Bean GrantedAuthorityDefaults` là cách hữu ích để bean được tìm thấy đúng lúc expression handler cần dùng. Khi có handler custom, cần kiểm tra handler này thực sự nhận default role prefix.

## 6. Method security: `@PreAuthorize` có thể dùng prefix được cấu hình

Ví dụ:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("");
    }
}
```

Fragment cần imports Spring phù hợp. Trong nhiều cấu hình Spring Security 6, method-security expression handler sẽ nhận prefix rỗng. Khi đó:

```java
@PreAuthorize("hasRole('OPS')")
public void runOperations() {
    // Business logic...
}
```

sẽ đòi authority `OPS` thay vì `ROLE_OPS`.

Cần nhớ:

- `@EnableMethodSecurity` phải thực sự bật method interception.
- Annotation phải được thực thi qua một **Spring-managed proxy**; self-invocation của method trong cùng bean có thể bỏ qua interception.
- Một custom `MethodSecurityExpressionHandler` có thể đặt prefix khác; cần kiểm tra application context, không đoán.
- `@PreAuthorize("hasAuthority('OPS')")` so exact authority `OPS`, ít phụ thuộc prefix hơn.
- Method security không thay thế việc kiểm tra tài nguyên thuộc owner/tenant. Một role toàn cục không tự cho quyền với mọi bản ghi.

## 7. Cảnh báo API trong Spring Security 6: HTTP `hasRole` khác method expression

Trong HTTP `authorizeHttpRequests` phổ biến, `hasRole("OPS")` được chuyển tới `AuthorityAuthorizationManager.hasRole("OPS")`, vốn sử dụng quy ước prefix `ROLE_`.

Điều đó có thể xảy ra dù bạn đã khai báo:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("");
}
```

**Không được suy ra** bean này khiến mọi HTTP `hasRole("OPS")` kiểm tra `OPS`. Một HTTP rule không mơ hồ cho authority `OPS` là:

```java
.requestMatchers("/ops/**").hasAuthority("OPS")
```

Khi mục tiêu là convention mặc định, dùng authority `ROLE_OPS` cùng `hasRole("OPS")` cũng đúng.

### Minh họa sự khác biệt

Giả sử principal có authorities `[OPS]`, bean `GrantedAuthorityDefaults("")` được method handler sử dụng:

```text
HTTP authorizeHttpRequests().hasRole("OPS")
  -> thường kiểm tra ROLE_OPS
  -> principal chỉ có OPS -> từ chối

Method @PreAuthorize("hasRole('OPS')")
  -> method expression handler đã dùng prefix rỗng
  -> kiểm tra OPS -> cho phép
```

Đây là hành vi của những engine/configuration nêu rõ trong bài, **không phải lời hứa cho mọi major version hoặc custom manager**.

| API | Authority được kiểm tra |
| --- | --- |
| HTTP `hasAuthority("OPS")` | `OPS` |
| HTTP `hasRole("OPS")` qua `AuthorityAuthorizationManager` ở Security 6 | `ROLE_OPS` |
| Method `hasAuthority('OPS')` | `OPS` |
| Method `hasRole('OPS')` | Theo default prefix của expression handler |
| `User.roles("OPS")` | Cấp `ROLE_OPS` |
| `User.authorities("OPS")` | Cấp `OPS` |
| Test `user("x").roles("OPS")` | Cấp `ROLE_OPS` |
| Test `user("x").authorities(new SimpleGrantedAuthority("OPS"))` | Cấp `OPS` |

Khi dự án dùng `authorizeRequests`/web expressions kiểu cũ hoặc custom authorization manager, cần kiểm chứng lại semantics. Không chuyển hướng dẫn dành cho một engine sang engine khác mà không test.

## 8. Java 17 thuần: mô hình so khớp dễ hiểu

Chương trình sau **độc lập, có thể biên dịch bằng javac** và mô phỏng phép kiểm tra chính xác hoặc ghép prefix. Đây chỉ là mô hình giáo dục, **không phải method thật của Spring Security**.

Tạo file `RolePrefixModel.java`:

```java
import java.util.Set;

public class RolePrefixModel {
    static boolean hasAuthority(Set<String> granted, String exact) {
        return granted.contains(exact);
    }

    static boolean hasRole(
            Set<String> granted, String role, String prefix) {
        return granted.contains(prefix + role);
    }

    public static void main(String[] args) {
        Set<String> prefixed = Set.of("ROLE_ADMIN", "REPORT_READ");
        Set<String> plain = Set.of("ADMIN", "REPORT_READ");

        System.out.println("prefixed.default="
            + hasRole(prefixed, "ADMIN", "ROLE_"));
        System.out.println("plain.default="
            + hasRole(plain, "ADMIN", "ROLE_"));
        System.out.println("plain.custom="
            + hasRole(plain, "ADMIN", ""));
        System.out.println("prefixed.exact="
            + hasAuthority(prefixed, "ROLE_ADMIN"));
        System.out.println("plain.permission="
            + hasAuthority(plain, "REPORT_READ"));
    }
}
```

Chạy với JDK 17+:

```bash
javac RolePrefixModel.java
java RolePrefixModel
```

Stdout chính xác theo code:

```text
prefixed.default=true
plain.default=false
plain.custom=true
prefixed.exact=true
plain.permission=true
```

Trong Spring Security thật, prefix được quyết định bởi authorization manager/expression handler **đang thực thi** và không nhất thiết được truyền dưới dạng parameter như hàm demo.

## 9. Ứng dụng Spring Boot 3 / Security 6 minh họa ba kiểu check

Ta viết một Servlet MVC app có:

- `GET /http/exact`: HTTP `hasAuthority("OPS")`.
- `GET /http/role`: HTTP `hasRole("OPS")`.
- `GET /method/role`: HTTP chỉ cần authenticated, nhưng service method được bảo vệ bằng `@PreAuthorize("hasRole('OPS')")` và method prefix rỗng.

Users minh họa:

| User | Authorities | Kết quả mong đợi |
| --- | --- | --- |
| `ops` | `OPS` | Được vào /http/exact, /method/role; không vào /http/role |
| `legacy` | `ROLE_OPS` | Được vào /http/role; không vào /http/exact, /method/role |
| `viewer` | `REPORT_READ` | Login thành công nhưng thiếu quyền với ba endpoint |

Cố tình có hai naming conventions để **so sánh**, không phải thiết kế production cần giữ mãi.

### Dependencies Gradle

Với một Spring Boot 3.x Gradle project Java17 đã có plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### File Java đầy đủ

Tạo `src/main/java/example/roles/RolePrefixApplication.java`:

```java
package example.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.core.GrantedAuthorityDefaults;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RolePrefixApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolePrefixApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/http/exact").hasAuthority("OPS")
                .requestMatchers("/http/role").hasRole("OPS")
                .requestMatchers("/method/role").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails ops = User.withUsername("ops")
            .password(encoder.encode("ops-pass"))
            .authorities("OPS")
            .build();

        UserDetails legacy = User.withUsername("legacy")
            .password(encoder.encode("legacy-pass"))
            .authorities("ROLE_OPS")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .authorities("REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(ops, legacy, viewer);
    }
}

@Service
class ReportService {

    @PreAuthorize("hasRole('OPS')")
    public String methodReport() {
        return "method allowed";
    }
}

@RestController
class DemoController {
    private final ReportService reportService;

    DemoController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/http/exact")
    String exactPage() {
        return "exact allowed";
    }

    @GetMapping("/http/role")
    String rolePage() {
        return "http role allowed";
    }

    @GetMapping("/method/role")
    String methodPage() {
        return reportService.methodReport();
    }
}
```

Đoạn code dùng một top-level public class trùng tên tệp Java, các class còn lại package-private, hợp lệ trên Java 17. `@SpringBootApplication` quét package `example.roles`; `ReportService` là `@Service` được Spring quản lý nên lời gọi từ controller đi qua method-security proxy.

**Giải thích:**

1. `@EnableMethodSecurity` bật interceptors hỗ trợ `@PreAuthorize`.
2. `static @Bean GrantedAuthorityDefaults("")` cấu hình method expression prefix theo contract của thành phần hỗ trợ.
3. HTTP `hasRole("OPS")` và HTTP `hasAuthority("OPS")` cố tình được đặt ở hai endpoint khác nhau để test.
4. User được tạo bằng `authorities(...)` cho đúng strings, không dùng `roles(...)` vì sẽ sinh `ROLE_`.
5. `.formLogin(Customizer.withDefaults())` bật đăng nhập form và trang login mặc định khi không custom.
6. Password demo được băm bằng delegating encoder; không dùng credential/key demo trong production.

### Chạy ứng dụng

Trong root Gradle project có wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Vào `http://localhost:8080/public`, dự kiến response body:

```text
public
```

Sau khi đăng nhập user `ops` / `ops-pass`:

```text
GET /http/exact  -> HTTP 200, body "exact allowed"
GET /http/role   -> HTTP 403
GET /method/role -> HTTP 200, body "method allowed"
```

Với user `legacy` / `legacy-pass`:

```text
GET /http/exact  -> HTTP 403
GET /http/role   -> HTTP 200, body "http role allowed"
GET /method/role -> HTTP 403
```

Đây là hành vi **dự kiến theo cấu hình**, chưa được kiểm tra bằng việc chạy ứng dụng trong bài viết. Dùng hai browser profiles/cookie jars độc lập để tránh session user trước làm sai kết quả.

## 10. Kiểm thử MockMvc cho cả HTTP và method authorization

Test nên tạo authorities **chính xác như production**, không dùng helper `roles(...)` khi muốn authority không prefix.

Tạo `src/test/java/example/roles/RolePrefixSecurityTest.java`:

```java
package example.roles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RolePrefixSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousProtectedRequestStartsFormLogin() throws Exception {
        mvc.perform(get("/http/exact"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void exactAuthorityOnlyAcceptsOps() throws Exception {
        mvc.perform(get("/http/exact")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("exact allowed"));

        mvc.perform(get("/http/exact")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void httpHasRoleRequiresRoleOpsInSecurity6() throws Exception {
        mvc.perform(get("/http/role")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("http role allowed"));

        mvc.perform(get("/http/role")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodHasRoleUsesConfiguredEmptyPrefix() throws Exception {
        mvc.perform(get("/method/role")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("method allowed"));

        mvc.perform(get("/method/role")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherAuthorityDoesNotGrantOpsRights() throws Exception {
        mvc.perform(get("/http/exact")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isForbidden());

        mvc.perform(get("/method/role")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isForbidden());
    }
}
```

Lệnh chạy:

```bash
./gradlew test
```

Các test là **assertions dự kiến**, chưa được chạy trong lúc soạn bài. `SecurityMockMvcRequestPostProcessors.user` tạo principal đã authenticated để test authorization; nó không kiểm tra credential qua `UserDetailsService`. Để test login end-to-end cần POST `/login` kèm `csrf()`, password đúng/sai và quản lý session.

**Đừng nhầm test principal:** `user("ops").roles("OPS")` sinh `ROLE_OPS` và thay đổi mục tiêu test. Muốn mô phỏng authority `OPS`, dùng `authorities(new SimpleGrantedAuthority("OPS"))`.

### Nếu test method không chạy như kỳ vọng

Xác nhận application version, `@EnableMethodSecurity`, proxy interception, `GrantedAuthorityDefaults` bean được method expression handler sử dụng, không có custom bean đặt prefix khác, service không tự gọi qua self-invocation, và `SecurityContext` trong test có đúng authorities.

## 11. Khi nào nên bỏ việc so prefix và dùng `hasAuthority`?

Một convention mới có thể dùng exact authority ở **cả HTTP lẫn method**:

```java
// HTTP rule:
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")

// Method rule:
@PreAuthorize("hasAuthority('ORDER_READ')")
public Order getOrder(long id) {
    // Vẫn cần kiểm tra ownership/tenant.
    return orderRepository.findById(id).orElseThrow();
}
```

Đây là fragment cần model/repository thực tế, không phải file runnable độc lập. `hasAuthority` làm contract so khớp đơn giản hơn, nhưng ứng dụng vẫn phải quản lý issuer/tenant, account status và quyền trên từng bản ghi.

Một hệ thống khác có thể giữ `ROLE_ADMIN` cho nhóm role và `ORDER_READ` cho permission. Điều đó cũng hợp lý khi mapping và rules nhất quán:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")
```

Không có một lựa chọn prefix bắt buộc cho mọi dự án. Yêu cầu quan trọng là **không mập mờ representation**.

## 12. JWT và `JwtGrantedAuthoritiesConverter`: `SCOPE_` không phải `ROLE_`

Khi Spring Security Resource Server chuyển JWT scope/scp claims thành authorities, quy ước thông dụng là tiền tố `SCOPE_`:

```text
Token đã xác minh:
  scope: "orders.read reports.export"

Authorities qua converter thông dụng:
  SCOPE_orders.read
  SCOPE_reports.export
```

Nếu API cần scope đọc đơn:

```java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

`GrantedAuthorityDefaults("")` **không tự thay đổi** converter của JWT. Nếu điều chỉnh `JwtGrantedAuthoritiesConverter.setAuthorityPrefix(...)` để dùng prefix khác, các rule cần đổi tương ứng; không trộn một role name `ADMIN` với quyền `SCOPE_admin` tùy tiện.

Ngoài ra, các role từ Identity Provider (ví dụ groups/realm roles) có thể cần custom converter để tạo `ROLE_ADMIN` hoặc `ADMIN`. Chỉ làm vậy từ claims **đã xác minh chữ ký, issuer/audience, expiration, tenant mapping** và nguồn cấp quyền đáng tin cậy. Không bao giờ nhận một request body tự khai role rồi cho phép nó trở thành `GrantedAuthority`.

## 13. Role hierarchy và các method-security annotation khác

`RoleHierarchy` cho phép mô tả một quan hệ role/authority theo chính sách, ví dụ:

```text
ROLE_ADMIN
  |
  +--> ROLE_MANAGER
          |
          +--> ROLE_VIEWER
```

Nhưng một hierarchy chỉ có tác dụng khi được cấu hình và tích hợp vào authorization manager/expression handler cần dùng. `GrantedAuthorityDefaults("")` **không** tự tạo quan hệ kế thừa. Nếu hierarchy khai `ROLE_ADMIN` mà user thực được cấp `ADMIN`, quan hệ có thể không khớp.

Method security còn có `@Secured` và JSR-250 `@RolesAllowed` khi được kích hoạt bằng những tùy chọn phù hợp, ví dụ `securedEnabled=true` hoặc `jsr250Enabled=true` trong `@EnableMethodSecurity`. Chúng có semantics/manager riêng; không suy ra một cấu hình prefix cho `@PreAuthorize` sẽ mặc nhiên áp giống hệt ở mọi annotation hoặc version.

Với ứng dụng có nhiều cơ chế authorization, kiểm thử từng kiểu annotation và HTTP filter chain là bắt buộc. Nhớ phân biệt `AuthenticationManager` (xác minh danh tính), `AuthorizationManager` (ra quyết định truy cập), `GrantedAuthoritiesMapper` (chuẩn hóa quyền) và `GrantedAuthorityDefaults` (một default role prefix setting).

## 14. Di chuyển từ `ROLE_ADMIN` sang `ADMIN` cần migration đầy đủ

Việc đặt `new GrantedAuthorityDefaults("")` không phải một cuộc migration. Cần rà soát ít nhất:

1. Data store: các cột role/permission, `UserDetailsService`, external groups và `GrantedAuthoritiesMapper`.
2. HTTP rules: `hasRole`, `hasAnyRole`, `hasAuthority`, multiple `SecurityFilterChain` và custom managers.
3. Method rules: `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@RolesAllowed`, expression handlers và Spring proxies.
4. Test fixtures: `@WithMockUser(roles=...)`, `user().roles(...)`, mocked JWT/JWT converters.
5. RoleHierarchy: tên quyền trong các quan hệ và nơi hierarchy được áp dụng.
6. Sessions/JWT: authentication đã phát hành có snapshot authorities cũ; cần TTL/revoke/invalidation policy phù hợp.
7. Rollout/cluster: tránh node A đang yêu cầu `ROLE_ADMIN` trong khi node B yêu cầu `ADMIN`, gây hành vi phân quyền không ổn định.
8. Giám sát: theo dõi denies nhưng không log password, JWT, session ID hoặc bí mật.

| Trước | Sau | Cần kiểm tra |
| --- | --- | --- |
| User authority `ROLE_MANAGER` | `MANAGER` | Mapping DB/SSO/JWT |
| HTTP `hasRole("MANAGER")` | HTTP `hasAuthority("MANAGER")` | Exact authority contract |
| Method `hasRole('MANAGER')` | Method `hasAuthority('MANAGER')` hoặc handler prefix rỗng | Method proxy/handler |
| `User.roles("MANAGER")` | `User.authorities("MANAGER")` | User builder |
| `@WithMockUser(roles="MANAGER")` | `@WithMockUser(authorities="MANAGER")` | Test setup |
| `ROLE_MANAGER > ROLE_USER` | Hierarchy theo convention mới | Integration với authorization engines |

**Đừng "fix" bằng cách cấp cả `MANAGER` và `ROLE_MANAGER` cho tất cả users không phân biệt.** Nó có thể mở rộng quyền ngoài ý định và che đi policy không nhất quán.

## 15. Chẩn đoán 401, 403 và các lỗi prefix

Một user thiếu quyền thông thường nhận **403**, nhưng status không nói hết nguyên nhân:

| Kết quả | Nguyên nhân có thể |
| --- | --- |
| 302 redirect `/login` | Anonymous được form-login entry point yêu cầu đăng nhập |
| 401 Unauthorized | Thiếu/không hợp lệ authentication với Basic/Bearer |
| 403 với user đã login | Không đủ authority, role mismatch, deny policy, resource-level check |
| 403 khi POST | Có thể thiếu CSRF token, không nhất thiết do role |
| 404 | Không có handler, endpoint chưa expose, hoặc policy cố ý ẩn resource |

Khi gặp 403, đi theo các bước:

1. Xác nhận request vào đúng `SecurityFilterChain` và rule match URL/method.
2. Xác nhận principal đã authenticated và `SecurityContext` đang chứa loại Authentication gì.
3. Quan sát **exact authorities** của principal tại request trong môi trường debug đã kiểm soát.
4. Phân biệt API `hasRole`, `hasAuthority`, SpEL expression hay custom manager.
5. Xác định prefix thực sự của manager/handler; không suy từ tên bean.
6. Nếu là method security, kiểm tra `@EnableMethodSecurity` và lời gọi qua Spring proxy.
7. Xem role hierarchy, scopes, object ownership và tenant boundary.
8. Xem session/JWT cũ có authorities bị cache/stale không.
9. Viết test cho user có `ADMIN`, `ROLE_ADMIN`, không có authority và các roles khác.
10. Chỉ sau đó mới sửa mapping, rule hoặc expression handler.

Bật debug log chỉ khi cần trong development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Không ghi token, cookie, password, security headers hay private data vào log/metrics. Ở production dùng audit/correlation ID với thông tin tối thiểu, có quyền truy cập phù hợp.

## 16. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| User có `ADMIN`, HTTP rule `hasRole("ADMIN")` | 403 | `hasAuthority("ADMIN")` hoặc cấp `ROLE_ADMIN` |
| User có `ROLE_ADMIN`, rule `hasAuthority("ADMIN")` | 403 | Exact `ROLE_ADMIN` |
| Truyền `hasRole("ROLE_ADMIN")` | Có thể lỗi config | `hasRole("ADMIN")` |
| Tin `GrantedAuthorityDefaults` đổi mọi HTTP matcher | Method/HTTP khác kết quả | Test từng manager, dùng exact authority |
| Đổi prefix nhưng dùng `User.roles()` | Vẫn cấp `ROLE_...` | Dùng `authorities()` nếu muốn không prefix |
| Dùng `@WithMockUser(roles=...)` cho dữ liệu không prefix | Fixture sai | Dùng `authorities=...` |
| Dùng `hasRole` cho JWT scope `SCOPE_...` | Không match | `hasAuthority("SCOPE_...")` |
| Quên `@EnableMethodSecurity` hoặc proxy | Annotation bị bỏ qua | Bật interception và test |
| Tự tạo authorities từ user input | Privilege escalation | Chỉ map từ identity source đáng tin |
| Giả định ADMIN tự có tất cả permissions | Có thể thiếu hoặc lạm quyền | RoleHierarchy và policy nghiệp vụ rõ |
| Bỏ qua ownership/tenant khi đã có role | IDOR, cross-tenant access | Kiểm tra resource-level permission |
| Thêm cùng lúc role prefix và không prefix để "chữa" lỗi | Quyền thừa | Chọn naming convention thống nhất |
| Đổi config nhưng giữ session/JWT cũ | Authorization stale | Revoke/refresh theo SLA |
| Tắt CSRF để xử lý 403 | Gây rủi ro bảo mật | Phân biệt lỗi CSRF/role và sửa đúng tầng |

## 17. Câu hỏi ôn tập

**Câu 1.** User có authority `ADMIN`, HTTP `hasRole("ADMIN")` theo Spring Security 6 mặc định có cho phép không?

**Đáp án:** Không, manager thường kiểm tra `ROLE_ADMIN`. Cần exact `hasAuthority("ADMIN")` hoặc cấp `ROLE_ADMIN`.

**Câu 2.** `hasAuthority("ADMIN")` có tự ghép `ROLE_` không?

**Đáp án:** Không. Nó kiểm tra exact `ADMIN`.

**Câu 3.** `GrantedAuthorityDefaults("")` có sửa authorities trong `Authentication` không?

**Đáp án:** Không. Nó là config default prefix cho các thành phần hỗ trợ; không rewrite data.

**Câu 4.** `User.roles("OPS")` và `User.authorities("OPS")` có giống nhau không?

**Đáp án:** Không. `roles` thường tạo `ROLE_OPS`, `authorities` tạo `OPS`.

**Câu 5.** Tại sao test `@WithMockUser(roles="OPS")` có thể khác production user `OPS`?

**Đáp án:** Test fixture tạo `ROLE_OPS` nên authority string khác.

**Câu 6.** HTTP `hasRole("OPS")` và method `@PreAuthorize("hasRole('OPS')")` luôn dùng prefix giống nhau không?

**Đáp án:** Không bảo đảm. Trong Security 6 HTTP builder dùng manager có `ROLE_`, còn method expression handler có thể nhận `GrantedAuthorityDefaults("")`. Test từng tầng.

**Câu 7.** Muốn giữ authority `OPS` nhưng không muốn phụ thuộc prefix, nên dùng gì?

**Đáp án:** `hasAuthority("OPS")` và `@PreAuthorize("hasAuthority('OPS')")`.

**Câu 8.** JWT converter tạo `SCOPE_orders.read`, rule phù hợp là gì?

**Đáp án:** `hasAuthority("SCOPE_orders.read")` nếu converter đang dùng naming đó.

**Câu 9.** User `ROLE_ADMIN` tự có `ROLE_VIEWER` không?

**Đáp án:** Không; role hierarchy cần được cấu hình và áp dụng.

**Câu 10.** Tại sao đổi bean role prefix vẫn có thể khiến người dùng còn quyền cũ?

**Đáp án:** Sessions, JWT và caches có thể giữ snapshot authorities. Migration phải giải quyết các vòng đời ấy.

**Câu 11.** Một method có `@PreAuthorize` nhưng không chặn người thiếu quyền, cần kiểm tra gì?

**Đáp án:** `@EnableMethodSecurity`, Spring proxy, self-invocation, handler và test configuration, không chỉ prefix.

**Câu 12.** Role ADMIN có cho phép đọc dữ liệu tenant khác không?

**Đáp án:** Không tự động; cần tenant/ownership authorization riêng.

## 18. Checklist trước khi phát hành

- [ ] Định nghĩa convention canonical cho role, permission, scope.
- [ ] Kiểm tra `GrantedAuthority.getAuthority()` thực tế, không chỉ nhãn role trong DB.
- [ ] Biết API nào thêm `ROLE_` và API nào so exact string.
- [ ] Dùng `GrantedAuthorityDefaults` chỉ khi các thành phần cần dùng được cấu hình tương thích.
- [ ] Kiểm thử `authorizeHttpRequests().hasRole` độc lập với method `@PreAuthorize.hasRole`.
- [ ] Không dùng `User.roles()` hoặc `@WithMockUser(roles=...)` để cấp unprefixed authority.
- [ ] Dùng exact `hasAuthority` cho permissions để tránh nhập nhằng.
- [ ] Kiểm tra proxy/`@EnableMethodSecurity` để method annotations thực sự hoạt động.
- [ ] Kiểm soát JWT/SSO converters, RoleHierarchy và các authority mappers.
- [ ] Test principals có `ADMIN`, `ROLE_ADMIN` và không có quyền.
- [ ] Test HTTP/method, roles/scopes, ownership/tenant và CSRF ở đúng lớp.
- [ ] Xử lý dữ liệu session/JWT/cache cũ khi đổi convention.
- [ ] Không mở rộng quyền tạm thời chỉ để test pass.
- [ ] Có regression tests khi nâng phiên bản Spring Security.
- [ ] Không log password, token hoặc dữ liệu người dùng nhạy cảm trong debug.

## Kết luận

`ROLE_` là **quy ước tiền tố role** trong nhiều API Spring Security. `GrantedAuthority` mới là các chuỗi quyền thực sự được gắn vào `Authentication`. `hasAuthority` so khớp chuỗi chính xác, trong khi `hasRole` có thể thêm prefix theo implementation đang thực thi.

`GrantedAuthorityDefaults` hữu ích để đổi default role prefix cho các component hỗ trợ, đặc biệt method-security expressions, nhưng **không tự chuyển đổi authorities hoặc đảm bảo mọi HTTP `hasRole` theo cùng một bean**. Để tránh lỗi 403, hãy chọn convention nhất quán, chuẩn hóa quyền từ nguồn danh tính đáng tin, dùng exact `hasAuthority` khi thích hợp và kiểm thử cả HTTP lẫn method authorization theo đúng Spring Security version.
