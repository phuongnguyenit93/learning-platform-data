# GrantedAuthorityDefaults và phạm vi áp dụng tiền tố theo thành phần

> **Phạm vi:** Spring Security Servlet, Spring Boot với Java 17+, tập trung vào quan hệ giữa `GrantedAuthority`, quy ước `ROLE_`, cách đổi tiền tố bằng `GrantedAuthorityDefaults` và giới hạn hiệu lực của nó ở từng API. Mã minh họa dùng các API có trong Spring Security 6.5.x; khi nâng major/minor version, cần chạy kiểm thử lại.

## 1. Tại sao đổi tiền tố role lại sinh lỗi 403?

Trong Spring Security, quyền được gán cho một danh tính qua danh sách `GrantedAuthority` của `Authentication`. Với kiểu thông dụng `SimpleGrantedAuthority`, giá trị authority là một **chuỗi chính xác**. Ví dụ `"ROLE_ADMIN"`, `"APP_ADMIN"` và `"ADMIN"` là ba giá trị khác nhau.

- `hasAuthority("APP_ADMIN")` yêu cầu authority **đúng chuỗi** `APP_ADMIN`.
- `hasRole("ADMIN")` là cách viết dựa trên **quy ước role prefix**; với tiền tố mặc định `ROLE_`, phần lớn các cơ chế kiểm tra role sẽ tìm `ROLE_ADMIN`.
- `GrantedAuthorityDefaults("APP_")` cho phép các thành phần **có hỗ trợ cấu hình này** hiểu role `ADMIN` tương ứng với authority `APP_ADMIN`.

Giả sử Alice được authentication cấp `ROLE_ADMIN`. Ứng dụng thêm `GrantedAuthorityDefaults("APP_")` và dùng `@PreAuthorize("hasRole('ADMIN')")`. Nếu method expression handler tiếp nhận prefix mới, phép kiểm tra sẽ tìm `APP_ADMIN` và **từ chối Alice**, dù Alice đã xác thực thành công. Cách sửa là đồng bộ dữ liệu authority, cấu hình policy và cách test; riêng việc có bean không tự đổi `ROLE_ADMIN` thành `APP_ADMIN`.

**Phân biệt:** authentication xác minh danh tính; authorization quyết định danh tính đó có quyền với action/resource đang xét. 403 ở đây thường là **thiếu authority mong đợi**, còn thiếu/không hợp lệ thông tin đăng nhập thường kích hoạt authentication entry point (HTTP Basic có thể trả 401).

## 2. `GrantedAuthorityDefaults` làm gì?

Lớp `org.springframework.security.config.core.GrantedAuthorityDefaults` nhận một tham số `rolePrefix`; `getRolePrefix()` trả về giá trị đó. Mục đích là định nghĩa prefix mặc định cho **quy tắc phân quyền theo role** ở những thành phần tích hợp với bean.

Cấu hình tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Configuration
class RolePrefixConfig {
    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }
}
~~~

Đây là **class cấu hình trong ứng dụng Spring** (cần dependency Spring Security), không phải một `main` chạy độc lập bằng `java RolePrefixConfig`.

Tài liệu chính thức khuyến nghị `static @Bean` để Spring đăng ký cấu hình tiền tố **sớm**, trước khi cấu hình method security được khởi tạo. Có thể đánh dấu bean thuộc hạ tầng bằng `@Role(BeanDefinition.ROLE_INFRASTRUCTURE)` nếu dự án muốn làm rõ vai trò của bean.

**Bean này không tự:**

1. Đổi tên chuỗi trong `Authentication#getAuthorities()`, session, JWT hoặc database.
2. Viết lại mọi `hasAuthority("ROLE_ADMIN")` thành `hasAuthority("APP_ADMIN")`.
3. Thay đổi cách `User.UserBuilder.roles(...)` hoặc `@WithMockUser(roles = ...)` tạo authority.
4. Thay đổi các static factory tự áp `ROLE_` như `AuthorityAuthorizationManager.hasRole(...)`.
5. Đổi tiền tố `SCOPE_` được JWT converter gán cho scope OAuth2.
6. Sửa literal trong `@Secured`, role hierarchy hoặc custom authorization manager mà bạn đã tự cấu hình.

Hãy hiểu đó là **cấu hình dành cho người tiêu thụ (consumer)**, không phải một phép tìm và thay chuỗi trên toàn bộ Spring Security.

## 3. Bảng phạm vi áp dụng theo thành phần

Ví dụ mong muốn tiền tố mới là `APP_`; role nghiệp vụ được đặt tên `ADMIN`.

| Thành phần / API | Cơ chế có ý nghĩa | Lưu ý |
| --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Method security expression handler dùng role prefix; cấu hình chuẩn có thể đọc `GrantedAuthorityDefaults` | Khi đã áp `APP_`, cần `APP_ADMIN` |
| `@PostAuthorize("hasRole('ADMIN')")` | Cũng là biểu thức method security | Có thể kiểm tra sau khi method chạy; chỉ dùng nếu thực sự cần |
| `@PreAuthorize("hasAuthority('APP_ADMIN')")` | So khớp literal `APP_ADMIN` | Không tự thêm/đổi prefix |
| `authorizeHttpRequests().hasRole("ADMIN")` | DSL HTTP tạo `AuthorizationManager`; cách lấy prefix phụ thuộc đường cấu hình và phiên bản | Kiểm chứng bằng HTTP integration test sau khi đổi prefix |
| `authorizeHttpRequests().hasAuthority("APP_ADMIN")` | So khớp literal | Cách viết minh bạch khi muốn authority riêng |
| `AuthorityAuthorizationManager.hasRole("ADMIN")` | Static factory của API này tự thêm `ROLE_` | Không mặc nhiên tiêu thụ bean `GrantedAuthorityDefaults` |
| `AuthorityAuthorizationManager.hasAuthority("APP_ADMIN")` | So khớp literal | Phù hợp khi tự tạo manager |
| `User.withUsername(...).roles("ADMIN")` | Builder **tạo `ROLE_ADMIN`** | Không bị bean `APP_` tự thay đổi |
| `User.withUsername(...).authorities("APP_ADMIN")` | Tạo authority `APP_ADMIN` | Dùng khi cần prefix tùy biến |
| `new SimpleGrantedAuthority("APP_ADMIN")` | Lưu chính chuỗi được truyền | Không có prefix tự động |
| `@WithMockUser(roles = "ADMIN")` | Test annotation thường tạo `ROLE_ADMIN` | Test prefix mới nên dùng `authorities = "APP_ADMIN"` |
| `@Secured("APP_ADMIN")` | Annotation sử dụng tên authority được khai báo | Không coi chuỗi là biểu thức `hasRole`; bật `securedEnabled` |
| `@RolesAllowed("ADMIN")` | JSR-250 authorization manager có cơ chế tiền tố role riêng, mặc định `ROLE_` | Bật `jsr250Enabled` và kiểm chứng config/phiên bản |
| `RoleHierarchyImpl.fromHierarchy("APP_ADMIN > APP_USER")` | Chuỗi hierarchy chứa tên authorities thực tế | Bean prefix không viết lại chuỗi hierarchy |
| `JwtGrantedAuthoritiesConverter` | Scope mặc định ánh xạ theo `SCOPE_` | Cấu hình converter riêng nếu đổi quy ước |
| `RoleVoter` và cơ chế legacy | Có cấu hình tiền tố riêng | Không áp logic method security đời mới cho mọi component |

**Điểm học quan trọng:** tên `hasRole` có thể xuất hiện trong nhiều lớp API, nhưng **không phải mọi implementation đều lấy prefix từ cùng một nguồn**. Khi chọn một custom prefix, luôn đối chiếu contract của từng thành phần thực thi quyền.

### Ba bước cần phân biệt

~~~text
(1) XÁC THỰC VÀ CẤP AUTHORITY
    UserDetailsService / JWT converter / AuthenticationProvider
        -> Authentication.authorities = ["APP_ADMIN"]

(2) DỊCH ROLE THÀNH YÊU CẦU AUTHORITY
    @PreAuthorize("hasRole('ADMIN')")
    + role prefix "APP_" trong method expression handler
        -> yêu cầu "APP_ADMIN"

(3) SO KHỚP QUYỀN
    So sánh yêu cầu "APP_ADMIN" với danh sách authorities
        -> có "APP_ADMIN" => allow
        -> chỉ có "ROLE_ADMIN" => deny
~~~

Sai ở bước nào cũng có thể làm tài khoản đăng nhập thành công nhưng bị từ chối khi thực thi policy.

## 4. Ví dụ Java 17+ và Spring Boot: kiểm chứng prefix tại method và HTTP

Ví dụ sau sử dụng ba user:

- Alice được cấp bằng `authorities("APP_ADMIN")`, authority thực tế là `APP_ADMIN`.
- Bob được cấp bằng `roles("ADMIN")`, authority thực tế vẫn là `ROLE_ADMIN`.
- Charlie được cấp bằng `authorities("APP_USER")`, authority thực tế là `APP_USER`.

Cách kiểm tra HTTP bằng `hasAuthority(...)` giữ rõ **chuỗi chính xác**. Cách kiểm tra method bằng `hasRole(...)` minh họa hiệu lực của `GrantedAuthorityDefaults("APP_")` trên method security chuẩn.

Tạo Spring Boot Maven project dùng **Java 17+**, starter **Spring Web** và **Spring Security**. Đặt lớp sau trong tệp `src/main/java/com/example/prefix/PrefixApplication.java`.

~~~java
package com.example.prefix;

import java.util.stream.Collectors;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.core.GrantedAuthorityDefaults;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class PrefixApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrefixApplication.class, args);
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/http/admin").hasAuthority("APP_ADMIN")
            .requestMatchers("/method/admin", "/method/user",
                "/literal/admin", "/whoami").authenticated()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("APP_ADMIN")
            .build();

        // roles("ADMIN") van tao "ROLE_ADMIN".
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        UserDetails charlie = User.withUsername("charlie")
            .password(encoder.encode("demo789"))
            .authorities("APP_USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, charlie);
    }

    @RestController
    static class Api {
        private final ProtectedService service;

        Api(ProtectedService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/http/admin")
        String httpAdmin() {
            return "http admin";
        }

        @GetMapping("/method/admin")
        String methodAdmin() {
            return service.admin();
        }

        @GetMapping("/method/user")
        String methodUser() {
            return service.user();
        }

        @GetMapping("/literal/admin")
        String literalAdmin() {
            return service.literalAdmin();
        }

        @GetMapping("/whoami")
        String whoami(Authentication authentication) {
            String authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + authorities;
        }
    }

    @Service
    static class ProtectedService {

        @PreAuthorize("hasRole('ADMIN')")
        public String admin() {
            return "method admin";
        }

        @PreAuthorize("hasRole('USER')")
        public String user() {
            return "method user";
        }

        @PreAuthorize("hasAuthority('ROLE_ADMIN')")
        public String literalAdmin() {
            return "literal admin";
        }
    }
}
~~~

Chú ý: `Api` gọi sang Spring-managed `ProtectedService` nên proxy method-security có cơ hội chặn `@PreAuthorize`. Nếu trong cùng service gọi `this.admin()` thì theo proxy-based AOP thông thường có thể bỏ qua advice; không dùng self-invocation làm ví dụ kiểm thử authorization.

### Lệnh chạy

Chạy từ thư mục dự án Maven:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell hoac Command Prompt
mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng chạy trên `localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/method/admin
curl -i -u alice:demo123 http://localhost:8080/whoami
curl -i -u bob:demo456 http://localhost:8080/whoami
curl -i -u alice:demo123 http://localhost:8080/method/admin
curl -i -u bob:demo456 http://localhost:8080/method/admin
curl -i -u charlie:demo789 http://localhost:8080/method/user
curl -i -u alice:demo123 http://localhost:8080/http/admin
curl -i -u bob:demo456 http://localhost:8080/http/admin
curl -i -u bob:demo456 http://localhost:8080/literal/admin
curl -i -u alice:demo123 http://localhost:8080/literal/admin
~~~

| Request | HTTP kỳ vọng | Lý do |
| --- | --- | --- |
| `/public/ping`, anonymous | 200, `pong` | `permitAll()` |
| `/method/admin`, anonymous | 401 | Route cần authentication; HTTP Basic yêu cầu credential |
| `/whoami`, Alice | 200, `alice:APP_ADMIN` | Authority thực tế của Alice |
| `/whoami`, Bob | 200, `bob:ROLE_ADMIN` | `roles("ADMIN")` vẫn sinh `ROLE_ADMIN` |
| `/method/admin`, Alice | 200, `method admin` | Method `hasRole('ADMIN')` tìm `APP_ADMIN` |
| `/method/admin`, Bob | 403 | Bob chỉ có `ROLE_ADMIN` |
| `/method/user`, Charlie | 200, `method user` | Có `APP_USER` |
| `/http/admin`, Alice | 200, `http admin` | HTTP so khớp literal `APP_ADMIN` |
| `/http/admin`, Bob | 403 | Bob thiếu `APP_ADMIN` |
| `/literal/admin`, Bob | 200, `literal admin` | `hasAuthority('ROLE_ADMIN')` là so khớp nguyên văn |
| `/literal/admin`, Alice | 403 | Alice thiếu `ROLE_ADMIN` |

Trong ví dụ, mất credential với tài nguyên được bảo vệ dẫn đến **401** qua HTTP Basic; đã đăng nhập nhưng thiếu quyền dẫn đến **403**. Nếu dự án dùng form login, request chưa xác thực có thể chuyển hướng đến trang đăng nhập. Password chỉ phục vụ demo; HTTP Basic phải dùng qua HTTPS khi triển khai thực tế.

## 5. Các API trông giống nhau nhưng không tương đương

### 5.1. HTTP DSL `hasRole` và static `AuthorityAuthorizationManager.hasRole`

Hai đoạn sau có thể trông tương tự:

~~~java
// Fragment đặt bên trong authorizeHttpRequests:
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

~~~java
// Fragment Java dùng trực tiếp manager:
var manager = AuthorityAuthorizationManager.hasRole("ADMIN");
~~~

Nhưng thành phần thứ nhất đi qua cấu hình DSL HTTP; thành phần thứ hai dùng **static factory có contract tự thêm `ROLE_`**. Với cấu hình custom prefix, không được coi chúng là tương đương nếu chưa kiểm tra phiên bản và cơ chế tạo manager.

Nếu muốn kiểm tra chính xác `APP_ADMIN`, có thể dùng:

~~~java
// Fragment trong HTTP DSL:
.requestMatchers("/admin/**").hasAuthority("APP_ADMIN")

// Hoac khi tu tao manager:
var manager = AuthorityAuthorizationManager.hasAuthority("APP_ADMIN");
~~~

Các đoạn ở trên là **fragment**, không biên dịch độc lập. Import lớp manager là `org.springframework.security.authorization.AuthorityAuthorizationManager`.

### 5.2. `@PreAuthorize` và `@Secured`

`@PreAuthorize("hasRole('ADMIN')")` đi qua **SpEL expression** và default role prefix. Trái lại, `@Secured("APP_ADMIN")` diễn đạt **authority literal** trong annotation được `SecuredAuthorizationManager` xử lý; không nên giả định đó là lời gọi `hasRole` bên trong SpEL.

Cần bật tùy chọn tương ứng:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Nếu dùng cả JSR-250:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

JSR-250 dùng `jakarta.annotation.security.RolesAllowed` với cách xử lý tiền tố role do `Jsr250AuthorizationManager` đảm nhiệm; API có `setRolePrefix(...)`. Vì vậy, trong migration cần kiểm tra manager này có được tích hợp đúng với custom prefix hay không. Cần dependency chứa Jakarta annotation API trong dự án nếu runtime không cung cấp sẵn.

### 5.3. `RoleHierarchy` là chuỗi quyền thực tế

Ví dụ:

~~~java
RoleHierarchy hierarchy =
    RoleHierarchyImpl.fromHierarchy("APP_ADMIN > APP_USER");
~~~

Đây là **fragment**; import `org.springframework.security.access.hierarchicalroles.RoleHierarchy` và `RoleHierarchyImpl`. Chuỗi hierarchy chứa **authority name thực tế**, không tự được viết lại bằng `GrantedAuthorityDefaults`. Cũng phải bảo đảm tầng authorization đang sử dụng hierarchy phù hợp, không chỉ tạo bean rồi cho rằng mọi custom manager đều biết nó.

### 5.4. UserDetails, OAuth2 và test

- `User.withUsername("bob").roles("ADMIN")` tạo `ROLE_ADMIN`.
- `User.withUsername("bob").authorities("APP_ADMIN")` tạo `APP_ADMIN`.
- `new SimpleGrantedAuthority("APP_ADMIN")` giữ nguyên chuỗi `APP_ADMIN`.
- `@WithMockUser(roles = "ADMIN")` thường tạo `ROLE_ADMIN`; để thử prefix mới, dùng `@WithMockUser(authorities = "APP_ADMIN")` và test cả denied path.
- `JwtGrantedAuthoritiesConverter` thông thường tạo `SCOPE_...` từ scope của JWT (đã được xác minh). Bean role-prefix không chuyển `SCOPE_report.read` thành `APP_report.read`. Nếu IdP đưa vai trò trong claim khác, cần converter/mapper tường minh và nguồn token đáng tin.
- Nếu role/authority được lưu trong session/JWT/cache, đổi bean hay database **không chắc** làm các credential/phiên đang hoạt động đổi ngay. Cần chiến lược refresh/revocation.

### 5.5. Component legacy và phiên bản khác

`RoleVoter`, cấu hình XML legacy, reactive security, custom expression handlers và custom `AuthorizationManager` có thể dùng cơ chế prefix khác. Khi đổi từ Spring Security 6.x sang 7.x, kiểm tra lại API mới liên quan đến `AuthorizationManagerFactory` và cách nó nhận `rolePrefix`; đừng suy đoán từ behavior của một phiên bản cũ. Cấu hình **phải được chứng minh bằng integration test**, nhất là khi kết hợp URL security, method security và token converter.

## 6. Chẩn đoán lỗi prefix theo trình tự

Khi tài khoản đã đăng nhập nhưng bị 403:

1. Xác định request bị chặn ở **HTTP authorization** hay **method authorization**; check cả hai nếu có.
2. Đọc **authority thực tế** của `Authentication`: ví dụ in `authentication.getAuthorities()` trong môi trường test. Không log mật khẩu hoặc token.
3. Ghi lại **quy tắc yêu cầu**: `hasRole('ADMIN')`, `hasAuthority('APP_ADMIN')`, `@Secured` hay một custom manager.
4. Tìm **prefix nguồn** mà consumer dùng: default method expression prefix, prefix của HTTP DSL, static factory, converter hoặc role hierarchy.
5. Xác nhận bean `GrantedAuthorityDefaults` tồn tại và được tạo sớm (với method security: `static @Bean`).
6. Nếu project có tự tạo `MethodSecurityExpressionHandler`, `AuthorizationManager` hoặc `RoleHierarchy`, kiểm tra các thành phần đó có cấu hình riêng nào ghi đè/hạn chế default.
7. Kiểm tra dữ liệu cũ từ JWT, SSO, session, cache hoặc database.
8. Viết test xác nhận **allow và deny**, tránh sửa lỗi 403 bằng cách mở `permitAll()`.

Ví dụ ma trận mong muốn đối với policy đòi `APP_ADMIN`:

| Authority đầu vào | `hasAuthority('APP_ADMIN')` | Method `hasRole('ADMIN')` đã áp `APP_` |
| --- | --- | --- |
| `APP_ADMIN` | ALLOW | ALLOW |
| `ROLE_ADMIN` | DENY | DENY |
| `ADMIN` | DENY | DENY |
| `APP_USER` | DENY | DENY |
| Không có authority phù hợp | DENY | DENY |

Đây là **ma trận kỳ vọng khi thành phần method thực sự nhận prefix `APP_`**. Nếu test thực tế khác, phải tìm nguyên nhân ở nguồn authority hoặc config consumer; không thay đổi test chỉ để bỏ qua lỗi.

## 7. Migration từ `ROLE_` sang `APP_`

1. **Chốt hợp đồng dữ liệu:** xác định role logic `ADMIN` được lưu thành authority `APP_ADMIN` ở nơi nào; tách role khỏi permission như `invoice:read`.
2. **Kiểm kê điểm cấp authority:** in-memory users, database, LDAP/OIDC, JWT converter, SSO mapping, test fixture.
3. **Kiểm kê điểm kiểm tra:** HTTP DSL, method SpEL, `@Secured`, `@RolesAllowed`, custom `AuthorizationManager`, role hierarchy, legacy voter.
4. **Đặt `GrantedAuthorityDefaults` kịp thời:** dùng `static @Bean`; trong custom handler/manager, cấu hình trực tiếp nếu cần.
5. **Sửa đúng nguồn cấp authority:** không dùng `roles("ADMIN")` khi chủ ý cấp `APP_ADMIN`; dùng `authorities("APP_ADMIN")` hoặc mapper có kiểm soát.
6. **Kiểm tra literal:** `hasAuthority("ROLE_ADMIN")`, `@Secured("ROLE_ADMIN")` và hierarchy `ROLE_...` sẽ không tự đổi.
7. **Test đa tầng:** user có `APP_ADMIN`, chỉ có `ROLE_ADMIN`, không có quyền, anonymous; kiểm thử request HTTP và lời gọi method qua proxy.
8. **Quản lý giai đoạn chuyển tiếp:** session/JWT cũ còn sống; chọn refresh/revocation hoặc migration có thời hạn để vừa không khóa nhầm user vừa không chấp nhận quyền rộng quá lâu.
9. **Giám sát sau đổi:** tỷ lệ 401/403, hành vi 403 mới xuất hiện, audit mapping role và các lần từ chối khác tenant/resource.

## 8. Nhầm lẫn phổ biến và câu hỏi tự kiểm tra

**Nhầm lẫn 1 — “`GrantedAuthorityDefaults("APP_")` đổi mọi `ROLE_ADMIN` đã cấp.”** Sai. Bean chỉ cung cấp cấu hình prefix cho các consumer tương thích; authority thực tế vẫn như nguồn cấp ban đầu.

**Nhầm lẫn 2 — “`hasRole("ADMIN")` tương đương mọi nơi với `hasAuthority("APP_ADMIN")`.”** Không thể khẳng định khi chưa xét component/phiên bản; static `AuthorityAuthorizationManager.hasRole` vẫn dùng `ROLE_`.

**Nhầm lẫn 3 — “`User.withUsername(...).roles("ADMIN")` sẽ sinh `APP_ADMIN`.”** Sai. Builder tự gắn `ROLE_`.

**Nhầm lẫn 4 — “Scope OAuth2 tự đổi tiền tố theo role prefix.”** Sai. Converter JWT có prefix riêng, thông thường `SCOPE_`.

**Nhầm lẫn 5 — “Test `@WithMockUser(roles="ADMIN")` chứng minh custom prefix hoạt động.”** Sai nếu fixture cấp `ROLE_ADMIN` trong khi runtime policy đòi `APP_ADMIN`.

**Tự kiểm tra:**

1. `@PreAuthorize("hasRole('ADMIN')")` có prefix `APP_` thực sự có hiệu lực ở method. Cần authority nào? **`APP_ADMIN`**.
2. Account chỉ có `ROLE_ADMIN` có qua được rule method nêu trên không? **Không**, khi không có rule phụ cấp quyền.
3. `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` có bị đổi thành `APP_ADMIN` không? **Không**, vì literal.
4. `AuthorityAuthorizationManager.hasRole("ADMIN")` tạo check cho authority nào? **`ROLE_ADMIN`** theo contract static factory.
5. User builder `roles("ADMIN")` có chịu ảnh hưởng của bean custom không? **Không**.
6. Muốn kiểm thử rule method prefix mới với `@WithMockUser` nên truyền gì? **`authorities = "APP_ADMIN"`**.
7. Tại sao HTTP cho phép nhưng method vẫn 403? Có thể HTTP rule kiểm `APP_ADMIN`, còn method-security handler tìm authority khác hoặc tài khoản chỉ có authority không tương thích. Cần kiểm tra **cả hai consumer**.
8. Có nên bỏ prefix bằng chuỗi rỗng không? Chỉ khi đã kiểm chứng toàn bộ policy, nguồn cấp authority và nguy cơ va chạm giữa tên role/permission. Prefix rỗng có thể làm mô hình khó phân biệt hơn.

**Ghi nhớ:** `GrantedAuthorityDefaults` thay đổi **quy ước diễn giải role tại các thành phần có hỗ trợ**. Luôn xác minh ba thứ: **authority thật trong `Authentication`**, **chính xác API đang kiểm tra**, và **prefix/literal mà API đó đang sử dụng**.

## Tài liệu chính thức

- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- `GrantedAuthorityDefaults` API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/core/GrantedAuthorityDefaults.html
- `AuthorityAuthorizationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- `User.UserBuilder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- `Jsr250AuthorizationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
