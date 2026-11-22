# @Secured và @RolesAllowed với điều kiện cấu hình tương ứng

Trong **Spring Security cho ứng dụng Servlet**, việc kiểm tra quyền không chỉ diễn ra ở HTTP URL. Một controller, service hoặc thành phần nghiệp vụ có thể được gọi theo nhiều đường: HTTP request, scheduler, message listener, một service khác, hoặc một công cụ nội bộ. **Method security** cho phép khai báo điều kiện phân quyền ngay trên phương thức hoặc lớp Spring-managed. Hai annotation phổ biến là `@Secured` của Spring Security và `@RolesAllowed` theo chuẩn JSR-250/Jakarta.

Cả hai nhìn có vẻ tương tự vì đều dùng để yêu cầu vai trò (role), nhưng có ba điểm bắt buộc phải hiểu trước khi triển khai:

1. **Chúng không mặc nhiên được kích hoạt chỉ bằng `@EnableMethodSecurity`.** Với Spring Security 6, cần bật riêng `securedEnabled = true` cho `@Secured` và `jsr250Enabled = true` cho `@RolesAllowed`.
2. **Cú pháp vai trò thường khác nhau:** mặc định `@Secured("ROLE_ADMIN")` tham chiếu trực tiếp authority có tiền tố `ROLE_`, trong khi `@RolesAllowed("ADMIN")` thường được ánh xạ tới `ROLE_ADMIN` nhờ role prefix mặc định của Spring Security.
3. **Annotation chỉ phát huy hiệu lực khi lời gọi đi qua cơ chế method-security interceptor** (thường là Spring AOP proxy). Gọi một phương thức khác trong cùng đối tượng qua `this`, tạo object bằng `new` hay gọi phương thức private không tự động được chặn như một lời gọi external qua proxy.

Bài học sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet/MVC)**. Nội dung có cơ chế hoạt động, bảng so sánh, cấu hình đúng/sai, chương trình Spring Boot minh họa với `@Secured`/`@RolesAllowed`/`@PermitAll`/`@DenyAll`, kiểm thử MockMvc và method security, chương trình Java 17 thuần mô phỏng quyết định quyền, các lỗi production, bảo mật và checklist. Ví dụ dùng vai trò đơn giản nhằm tập trung vào annotation; khi quyền phụ thuộc ownership, tenant hoặc dữ liệu đối tượng, cần policy nâng cao như `@PreAuthorize` hoặc `AuthorizationManager` tương ứng.

## 1. HTTP security khác method security

HTTP security bảo vệ điểm vào Servlet request; method security bảo vệ **lời gọi method trên bean được Spring quản lý**.

~~~text
HTTP client
    |
    v
Spring Security FilterChainProxy
    |-- Authentication filters -> Authentication + authorities
    |-- AuthorizationFilter  -> URL/method HTTP allowed?
    |
    v
Spring MVC Controller
    |
    v
Spring AOP method-security proxy
    |-- @Secured / @RolesAllowed / @PreAuthorize interceptor
    |-- đọc Authentication từ SecurityContext
    |-- kiểm tra authorities/policy
    |-- grant: gọi method đích
    |-- deny: AccessDeniedException / AuthorizationDeniedException
    |
    v
Service method
    |
    v
Repository / domain logic
~~~

Sơ đồ thể hiện luồng **khi có Spring proxy và security interceptors phù hợp**. Một lời gọi ở trong cùng instance, hoặc một bean không được Spring quản lý, có thể không đi qua proxy dù trong source có annotation.

### Vì sao cần hai lớp?

| Lớp | Điều nó làm tốt | Giới hạn |
| --- | --- | --- |
| `authorizeHttpRequests(...)` | Xác định URL, HTTP method, request matcher, yêu cầu đăng nhập/authority trước controller | Không tự bảo vệ một service nếu service được gọi từ batch/queue hay API khác |
| `@Secured`/`@RolesAllowed` | Đòi vai trò ở điểm gọi method Spring bean được intercept | Không biết sẵn HTTP route hoặc object ownership; phụ thuộc proxy và authentication context |
| `@PreAuthorize` | Diễn đạt biểu thức phức tạp liên quan tham số, principal, bean policy | Cần kiểm soát expression, bean naming và dữ liệu đáng tin; phức tạp hơn |
| Quy tắc trong service/repository | Có thể kiểm tra ownership, tenant, trạng thái dữ liệu và consistency | Phải được gọi nhất quán từ mọi đường sử dụng |

Đối với ứng dụng cần kiểm soát nghiêm ngặt, **HTTP gate và method security là các lớp bổ sung**. Ví dụ, filter yêu cầu `authenticated()` cho toàn API, còn method service quản trị yêu cầu `ROLE_ADMIN`.

### Một câu hỏi quan trọng

Có thể thêm `@Secured("ROLE_ADMIN")` vào một service method rồi bỏ hết HTTP security không? **Không nên suy luận như vậy.** Ngoài method đó còn có controller khác, logic trước lời gọi, resources hoặc route công khai; method security không thay thế request firewall, CSRF, authentication, HTTP headers và mapping policy.

## 2. @Secured là gì?

`@Secured` nằm ở package Spring Security:

~~~java
import org.springframework.security.access.annotation.Secured;
~~~

Annotation dùng các chuỗi authority/role, thường là `ROLE_ADMIN` hoặc `ROLE_USER`:

~~~java
@Secured("ROLE_ADMIN")
public String viewAuditLog() {
    return "audit log";
}
~~~

Nếu bean đã được method-security interceptor bảo vệ và authentication hiện tại không có authority yêu cầu, lời gọi bị từ chối trước khi body phương thức chạy.

### @Secured dùng chuỗi authority

Ví dụ dữ liệu authority của người dùng:

~~~text
admin   -> ["ROLE_ADMIN"]
auditor -> ["ROLE_AUDITOR"]
member  -> ["ROLE_USER"]
~~~

Quy tắc:

~~~java
@Secured("ROLE_ADMIN")
public String adminOnly() {
    return "only admin";
}
~~~

Chỉ `ROLE_ADMIN` được grant trong ví dụ. Nếu username đã xác thực nhưng chỉ có `ROLE_USER`, phương thức phải bị deny.

### Có nhiều role thì OR hay AND?

~~~java
@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
public String reports() {
    return "reports";
}
~~~

Đối với annotation này, nhiều giá trị thể hiện **ít nhất một trong các authority được yêu cầu** — chính sách OR, không phải tất cả đều phải có. Admin hoặc auditor đều có thể gọi. Nếu nghiệp vụ yêu cầu **cả** hai điều kiện, hoặc kết hợp role + tenant + trạng thái tài nguyên, dùng cơ chế diễn đạt phù hợp hơn thay vì giả định mảng sẽ thành AND.

### Class-level và method-level

Có thể đặt `@Secured` trên class để khai báo mặc định cho các method áp dụng:

~~~java
@Secured("ROLE_ADMIN")
@Service
public class AdminTasks {
    public String overview() {
        return "overview";
    }
}
~~~

Đây là fragment: import `@Service` và `@Secured` cần có, không phải một file đầy đủ. Khi khai báo thêm annotation method-level ở cùng lớp hoặc kết hợp nhiều loại annotation, cách resolve metadata và interceptor có thể phụ thuộc framework/version. Hãy chọn quy ước nhất quán và **test mỗi public method**, không xem class-level là một giấy phép bỏ review.

**Không dùng `@Secured` như một String expression language:** `@Secured("hasRole('ADMIN')")` không có nghĩa giống `@PreAuthorize("hasRole('ADMIN')")`. `@Secured` dùng tên authority/role, không tự đánh giá SpEL.

## 3. @RolesAllowed: JSR-250/Jakarta Security annotations

`@RolesAllowed` thuộc họ annotation được chuẩn hóa (trong Spring Boot 3 / Jakarta namespace):

~~~java
import jakarta.annotation.security.RolesAllowed;
~~~

Ví dụ:

~~~java
@RolesAllowed("ADMIN")
public String manageTeams() {
    return "team management";
}
~~~

Trong cấu hình Spring Security 6.x thông thường, `@RolesAllowed("ADMIN")` được đánh giá theo role prefix mặc định `ROLE_`, tức cần authority `ROLE_ADMIN`. **Tiền tố này là một quy ước cấu hình**, không phải kết quả mà Java compiler tự sinh.

### Vai trò trong @RolesAllowed

~~~java
@RolesAllowed({"ADMIN", "AUDITOR"})
public String readReports() {
    return "reports";
}
~~~

Ở đây **một trong hai role** là đủ, tương tự OR. Không hiểu mảng này là AND.

### @PermitAll và @DenyAll đi cùng JSR-250

Họ JSR-250 có thêm:

~~~java
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;

@PermitAll
public String publicMessage() {
    return "public";
}

@DenyAll
public String disabledOperation() {
    return "disabled";
}
~~~

- `@PermitAll` cho phép mọi principal theo method-security JSR-250 rule tương ứng (không tự mở URL nếu HTTP policy vẫn deny).
- `@DenyAll` từ chối lời gọi method qua JSR-250 interceptor, kể cả khi user có ROLE_ADMIN.
- Hai annotation này chỉ có ý nghĩa khi **JSR-250 method security được bật** ở phần cấu hình. Với các method yêu cầu authentication trong HTTP layer, `@PermitAll` không vượt qua điều kiện `authenticated()` của filter.

Không đặt `@PermitAll` và `@DenyAll` cùng một method. Tránh trộn `@PermitAll` với `@Secured` trên một method để “kết hợp” kết quả khi chưa hiểu đầy đủ interceptors/order; xác định một policy rõ và test.

### Jakarta khác javax

Trên Spring Boot 3, Spring Framework 6 và Spring Security 6, dùng:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Code hướng dẫn cũ trên Boot 2 đôi khi dùng `javax.annotation.security.RolesAllowed`. Không copy import `javax.annotation.*` vào dự án Jakarta mà mặc định nó được nhận diện đúng. Việc có dependency `javax.annotation-api` trong classpath không biến annotation `javax` thành tương đương `jakarta` cho các interceptors đã biên dịch với API khác.

## 4. Cấu hình tương ứng: bước quan trọng nhất

Từ Spring Security 6, cấu hình method security hiện đại được bật với `@EnableMethodSecurity`.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
~~~

Đây là file cấu hình Java hoàn chỉnh nếu lưu `MethodSecurityConfig.java` cùng imports (không có package trong fragment để minh họa ngắn). Trong ứng dụng thật, có thể đặt `@EnableMethodSecurity` trên configuration class chứa SecurityFilterChain.

### Default flags của @EnableMethodSecurity

| Tính năng | Flag | Mặc định phổ biến trong Spring Security 6 | Muốn dùng? |
| --- | --- | --- | --- |
| `@PreAuthorize` / `@PostAuthorize` và họ pre/post | `prePostEnabled` | `true` | Không cần bật tường minh nếu giữ mặc định |
| `@Secured` | `securedEnabled` | `false` | **Phải bật true** |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `jsr250Enabled` | `false` | **Phải bật true** |

Điểm đáng nhớ: chỉ viết `@EnableMethodSecurity` **không đồng nghĩa** cả `@Secured` lẫn `@RolesAllowed` đều có enforcement. Đây là nguồn lỗi bảo mật âm thầm: annotation hiển thị đẹp trong code review nhưng không có interceptor được kích hoạt.

### Các cấu hình một chiều

Nếu chỉ dùng Spring Security `@Secured`:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Nếu chỉ dùng Jakarta `@RolesAllowed` và họ JSR-250:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

Nếu dùng cả hai:

~~~java
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
~~~

Tất cả các dòng trên là **fragments** đặt lên class `@Configuration`/bootstrap thích hợp, không phải Java file tự chạy. Không bật `securedEnabled` rồi suy ra JSR-250 được bật; cũng không bật `jsr250Enabled` rồi suy ra Spring `@Secured` được bật.

### Legacy @EnableGlobalMethodSecurity

Các hướng dẫn Spring Security 5 cũ dùng:

~~~java
// API đời cũ; không dùng như cấu hình chính của bài học Spring Security 6.
@EnableGlobalMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Trong Spring Security 6, `@EnableMethodSecurity` là hướng mới được ưu tiên. Nếu chuyển một dự án cũ lên Spring Security 6, cần xem lại các beans/interceptors và integration tests, không chỉ đổi tên annotation rồi kết luận mọi rule vẫn được thi hành.

## 5. ROLE_ prefix và cách ánh xạ roles thành authorities

Spring Security phân biệt **role name** và **GrantedAuthority**. Theo mặc định phổ biến:

~~~text
User.roles("ADMIN")             -> GrantedAuthority: ROLE_ADMIN
@Secured("ROLE_ADMIN")          -> so với authority ROLE_ADMIN
@RolesAllowed("ADMIN")          -> role ADMIN -> authority ROLE_ADMIN
hasRole("ADMIN")                -> authority ROLE_ADMIN
hasAuthority("ROLE_ADMIN")      -> authority ROLE_ADMIN
~~~

Đây là **mặc định thông dụng**, có thể thay đổi nếu ứng dụng cấu hình role prefix/authority mapping riêng. Với identity provider ngoài, authorities có thể là `SCOPE_admin`, `ROLE_ADMIN`, `ADMIN` hoặc một scheme khác.

### Ví dụ đúng khi tạo user bằng Spring Security

~~~java
UserDetails admin = User.withUsername("admin")
    .password(passwordEncoder.encode("demo-password"))
    .roles("ADMIN")
    .build();
~~~

`roles("ADMIN")` thường tự thêm tiền tố `ROLE_`, nên admin có `ROLE_ADMIN`. **Đừng** gọi `roles("ROLE_ADMIN")` rồi nghĩ nó sẽ được giữ nguyên như một authority tùy ý; builder có quy tắc riêng để tránh prefix trùng và có thể từ chối giá trị đã có `ROLE_`.

Nếu muốn khai báo authority đầy đủ:

~~~java
UserDetails admin = User.withUsername("admin")
    .password(passwordEncoder.encode("demo-password"))
    .authorities("ROLE_ADMIN")
    .build();
~~~

Cách dùng `roles` và `authorities` phải nhất quán với contract authentication provider trong ứng dụng.

### Một lỗi phổ biến

~~~java
// Có khả năng sai: người dùng chỉ có ROLE_ADMIN
@Secured("ADMIN")
public void manage() {
    // ...
}
~~~

Spring `@Secured` kiểm tra authority literal theo chính sách được cấu hình. Nếu principal có `ROLE_ADMIN` nhưng annotation yêu cầu `ADMIN`, method có thể bị deny. Ngược lại, với `@RolesAllowed("ADMIN")`, hệ thống JSR-250 Spring Security mặc định thường thêm prefix để khớp `ROLE_ADMIN`.

### Role prefix được tùy chỉnh thì sao?

Ứng dụng có thể cấu hình role prefix hoặc authority mapping khác mặc định qua `GrantedAuthorityDefaults` hoặc các thành phần method authorization tương ứng. Khi đó cần xác minh **cả**:

- Những authorities thực tế nằm trong `Authentication.getAuthorities()`.
- Cách `@Secured`, `@RolesAllowed` và HTTP `hasRole(...)` diễn giải role.
- Sự nhất quán giữa role hierarchy, claim mapping, database roles và test fixtures.

Không khẳng định chỉ thay một bean sẽ đồng bộ ngay mọi cơ chế method/HTTP trong mọi phiên bản. Viết test dựa trên authority string thực tế mà provider trả về.

## 6. Spring AOP proxy: khi nào annotation thực sự chạy?

Method security thông thường được triển khai bằng **Spring AOP interception**. Lời gọi phải đi qua proxy được Spring tạo cho bean có method cần bảo vệ.

~~~text
Controller bean
      |
      | service.adminOperation()
      v
Spring proxy  ------------> Method security advisor/interceptor
                                   |
                                   +-- check authorities
                                   |
                              ALLOW / DENY
                                   |
                                   v
                              Target service method
~~~

Nếu code dùng `new AdminService()` thay vì một bean từ ApplicationContext, object đó không có proxy method-security của Spring.

### Self-invocation là bẫy lớn

~~~java
@Service
public class UnsafeWorkflow {

    public String outer() {
        // Lời gọi từ bên trong cùng instance thường KHÔNG qua proxy.
        return this.restricted();
    }

    @Secured("ROLE_ADMIN")
    public String restricted() {
        return "sensitive";
    }
}
~~~

Đây là **ví dụ nguy cơ**, không phải cách triển khai được khuyến nghị. Nếu một controller gọi `outer()` của bean mà `outer()` không có rule, lời gọi `this.restricted()` thường bỏ qua method interceptor dù `restricted()` có `@Secured`. Hậu quả: nguồn gọi qua proxy trực tiếp tới restricted() bị chặn, nhưng đường đi từ outer() có thể không bị kiểm tra cùng cách.

**Cách xử lý tốt hơn:** tách restricted operation sang **một bean khác**, rồi inject bean đó; lời gọi qua bean proxy thực thi method security. Hoặc đặt policy ở entry point bên ngoài và trong business service theo thiết kế. Không dùng thủ thuật tự inject proxy, `AopContext.currentProxy()` hay chuyển quyền kiểm soát lung tung chỉ để né self-invocation nếu kiến trúc có thể được tách rõ.

### Những hạn chế thường gặp

- **Private method** không nên được xem là điểm chặn an toàn bằng proxy method security, vì proxy thường không intercept lời gọi private.
- **Final class/final method** có thể gây hạn chế với class-based proxy; kết quả còn phụ thuộc proxy type và interfaces.
- **Methods trên interface** có thể được proxy theo cách khác class methods; chọn nơi đặt annotation nhất quán và test trong project thật.
- **Non-public methods** có khác biệt giữa JDK dynamic proxy và CGLIB; để ví dụ dễ dự đoán, sử dụng public methods trên Spring beans bình thường.
- **Method nội bộ gọi trực tiếp** bằng `this`, constructor invocation, static methods, objects tạo bằng `new` không được bảo vệ như external proxy calls.
- **@Async/threads** có thể không có SecurityContext giống request gốc; muốn bảo vệ method trong async flow cần thiết kế context propagation hoặc service identity, không dựa vào ThreadLocal tình cờ.

Một test chỉ kiểm tra rằng annotation có mặt trong source hoặc bytecode **không đủ**. Cần test lời gọi qua Spring bean thực và kỳ vọng AccessDeniedException/403 đúng khi không đủ quyền.

## 7. Ví dụ hoàn chỉnh: Spring Boot, @Secured và @RolesAllowed

Ta xây ứng dụng với ba tài khoản demo:

| User | Authorities từ UserDetailsService | Mục đích |
| --- | --- | --- |
| `admin` | ROLE_ADMIN | Được gọi các method admin |
| `auditor` | ROLE_AUDITOR | Được xem method dành cho admin/auditor |
| `member` | ROLE_USER | Chỉ dùng public/user route phù hợp |

Các endpoint:

| Endpoint | Service method annotation | Kỳ vọng |
| --- | --- | --- |
| GET /api/secured/admin | `@Secured("ROLE_ADMIN")` | Chỉ admin |
| GET /api/jsr250/admin | `@RolesAllowed("ADMIN")` | Chỉ admin |
| GET /api/secured/report | `@Secured({"ROLE_ADMIN","ROLE_AUDITOR"})` | Admin hoặc auditor |
| GET /api/jsr250/report | `@RolesAllowed({"ADMIN","AUDITOR"})` | Admin hoặc auditor |
| GET /api/jsr250/locked | `@DenyAll` | Không ai |
| GET /api/public/info | `@PermitAll` + HTTP permitAll | Anonymous cũng có thể vào |

Cấu hình HTTP cho phép request đi đến controller nếu đã authenticated (ngoại trừ public/info). **Method security** tiếp tục kiểm tra role tại service. Đây là cách tách trách nhiệm rõ để test được sự khác biệt giữa HTTP và method security.

### 7.1. Dependencies Maven

Trong một project Spring Boot 3.x đã có parent/BOM và plugin build tương thích, `pom.xml` khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>jakarta.annotation</groupId>
        <artifactId>jakarta.annotation-api</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Không chép các dependency cũ `javax.annotation-api` để dùng cho `jakarta.annotation.security.RolesAllowed`. Boot BOM quản lý các version phù hợp. Nếu dự án đang dùng bản Spring Boot khác, kiểm tra API và Java toolchain thực tế.

### 7.2. Main class

Tạo `src/main/java/com/example/methodroles/MethodRolesApplication.java`:

~~~java
package com.example.methodroles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodRolesApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: bật cả hai cơ chế

Tạo `src/main/java/com/example/methodroles/SecurityConfig.java`:

~~~java
package com.example.methodroles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // MẬT KHẨU DEMO. KHÔNG hardcode credentials production.
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password(encoder.encode("admin-demo-password"))
                .roles("ADMIN").build(),
            User.withUsername("auditor")
                .password(encoder.encode("auditor-demo-password"))
                .roles("AUDITOR").build(),
            User.withUsername("member")
                .password(encoder.encode("member-demo-password"))
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/info").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF: ví dụ chỉ dùng GET.
        // Đường method protected sẽ còn được method security kiểm tra.
        return http.build();
    }
}
~~~

Những điểm không được bỏ qua:

1. `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` là **điều kiện kích hoạt** hai loại annotation; không chỉ đặt `@EnableMethodSecurity` không tham số.
2. `User.withUsername(...).roles("ADMIN")` tạo authority `ROLE_ADMIN` theo role-prefix thông thường.
3. HTTP rule yêu cầu authenticated cho phần còn lại, **không tự cho admin quyền toàn bộ**; service annotations quyết định việc gọi method nào.
4. `httpBasic()` chỉ để dễ kiểm thử bằng HTTP client; production cần HTTPS, strong password policy, MFA/identity tùy threat model, rate limiting và không dùng credentials test.
5. `csrf` vẫn bật cho phương thức thay đổi trạng thái. Chỉ có GET trong demo; điều này không phải lý do để disable CSRF toàn ứng dụng.
6. Không dùng các route public quá rộng như `/api/**.permitAll()`. Public được giới hạn ở GET /api/public/info qua route cụ thể; để ràng buộc method chính xác hơn, nên khai báo `requestMatchers(HttpMethod.GET, "/api/public/info")` theo policy, đặc biệt khi endpoint có thêm POST sau này.

**Quan trọng:** đoạn code trên sử dụng `requestMatchers("/api/public/info")` không ràng buộc HTTP method, nhưng controller chỉ có GET và `anyRequest().authenticated()` cho các URL khác. Trong production, nếu cần policy allowlist chặt theo method, thay bằng version có `HttpMethod.GET` để tránh một POST cùng path được permit ở HTTP layer trước khi MVC xử lý. Bảo mật method vẫn phải được xét riêng; route method khác có thể được bổ sung sau này.

### 7.4. MethodProtectedService: annotation đặt trên service

Tạo `src/main/java/com/example/methodroles/MethodProtectedService.java`:

~~~java
package com.example.methodroles;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.stereotype.Service;

@Service
public class MethodProtectedService {

    @Secured("ROLE_ADMIN")
    public String securedAdmin() {
        return "secured-admin-ok";
    }

    @RolesAllowed("ADMIN")
    public String rolesAllowedAdmin() {
        return "roles-allowed-admin-ok";
    }

    @Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
    public String securedReport() {
        return "secured-report-ok";
    }

    @RolesAllowed({"ADMIN", "AUDITOR"})
    public String rolesAllowedReport() {
        return "roles-allowed-report-ok";
    }

    @DenyAll
    public String locked() {
        return "locked-should-not-run";
    }

    @PermitAll
    public String publicInfo() {
        return "public-ok";
    }
}
~~~

Các phương thức đều là **public**, class không final, do Spring tạo bean, controller sẽ inject bean. Trong cấu hình bật cả hai loại, Spring method-security interceptor kiểm tra role trước khi gọi body method. `locked()` không nên được thực thi qua proxy ngay cả với admin.

Bài cố ý **không đặt nhiều loại annotation mâu thuẫn lên cùng method**. Mỗi endpoint thể hiện một contract rõ. Khi migrate một codebase lớn, nếu method có `@Secured` và `@PreAuthorize` hoặc annotation method/class chồng lấn, cần review semantics kết hợp interceptors, order và test; không giả định một annotation “ghi đè” annotation khác trong mọi cấu hình.

### 7.5. Controller gọi service qua bean proxy

Tạo `src/main/java/com/example/methodroles/MethodRolesController.java`:

~~~java
package com.example.methodroles;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MethodRolesController {

    private final MethodProtectedService service;

    public MethodRolesController(MethodProtectedService service) {
        this.service = service;
    }

    @GetMapping("/api/secured/admin")
    public String securedAdmin() {
        return service.securedAdmin();
    }

    @GetMapping("/api/jsr250/admin")
    public String rolesAllowedAdmin() {
        return service.rolesAllowedAdmin();
    }

    @GetMapping("/api/secured/report")
    public String securedReport() {
        return service.securedReport();
    }

    @GetMapping("/api/jsr250/report")
    public String rolesAllowedReport() {
        return service.rolesAllowedReport();
    }

    @GetMapping("/api/jsr250/locked")
    public String locked() {
        return service.locked();
    }

    @GetMapping("/api/public/info")
    public String publicInfo() {
        return service.publicInfo();
    }
}
~~~

Do controller inject Spring-managed `MethodProtectedService`, lời gọi `service.securedAdmin()` đi qua interceptor method security khi được bật. Nếu controller tự `new MethodProtectedService()` hoặc gọi method không qua proxy, điều kiện annotation có thể không được thi hành.

### 7.6. Chạy và thử hành vi dự kiến

Chạy ứng dụng với Maven wrapper trong project Boot 3.x đã cấu hình:

~~~bash
./mvnw spring-boot:run
~~~

Một số HTTP request **chỉ trên localhost/demo**:

~~~bash
# curl -u sẽ hỏi mật khẩu nếu không ghi password sau dấu :
curl -i -u admin http://localhost:8080/api/secured/admin
curl -i -u member http://localhost:8080/api/secured/admin
curl -i -u admin http://localhost:8080/api/jsr250/admin
curl -i -u auditor http://localhost:8080/api/jsr250/report
curl -i -u admin http://localhost:8080/api/jsr250/locked
curl -i http://localhost:8080/api/public/info
~~~

Kỳ vọng (khi nhập đúng mật khẩu demo tương ứng):

| Request | Kết quả thường gặp | Ý nghĩa |
| --- | --- | --- |
| Admin GET /api/secured/admin | 200, `secured-admin-ok` | `@Secured` nhận ROLE_ADMIN |
| Member GET /api/secured/admin | 403 | Authenticated nhưng thiếu ROLE_ADMIN |
| Admin GET /api/jsr250/admin | 200, `roles-allowed-admin-ok` | `@RolesAllowed("ADMIN")` nhận ROLE_ADMIN |
| Auditor GET /api/jsr250/report | 200, `roles-allowed-report-ok` | Mảng role là OR |
| Admin GET /api/jsr250/locked | 403 | `@DenyAll` chặn |
| Anonymous GET /api/public/info | 200, `public-ok` | HTTP permitAll + JSR-250 PermitAll |
| Anonymous GET /api/secured/admin | 401 (HTTP Basic) | Không có authentication, bị HTTP entry point chặn |

Status phụ thuộc AuthenticationEntryPoint/AccessDeniedHandler của ứng dụng; ví dụ dùng HTTP Basic mặc định. Thứ quan trọng là **quyết định allow/deny** phải đúng, không phải ghi nhớ rằng mọi denied luôn có cùng status.

## 8. Kiểm thử Spring Boot/MockMvc: không chỉ đọc annotation

Khi method security bị cấu hình thiếu flag, source vẫn có annotation nhưng request có thể thành công ngoài ý muốn. Vì vậy test cần xác minh **lời gọi thật qua bean proxy**, kể cả khi HTTP layer đã cho qua vì authenticated.

Tạo `src/test/java/com/example/methodroles/MethodRolesIntegrationTest.java`:

~~~java
package com.example.methodroles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodRolesIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void securedAllowsAdminAndDeniesMember() throws Exception {
        mvc.perform(get("/api/secured/admin")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-admin-ok"));

        mvc.perform(get("/api/secured/admin")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void rolesAllowedUsesJakartaAndAdminRole() throws Exception {
        mvc.perform(get("/api/jsr250/admin")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("roles-allowed-admin-ok"));

        mvc.perform(get("/api/jsr250/admin")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anyListedRoleIsEnough() throws Exception {
        mvc.perform(get("/api/secured/report")
                .with(httpBasic("auditor", "auditor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-report-ok"));

        mvc.perform(get("/api/jsr250/report")
                .with(httpBasic("auditor", "auditor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("roles-allowed-report-ok"));

        mvc.perform(get("/api/jsr250/report")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void denyAllRejectsEvenAdmin() throws Exception {
        mvc.perform(get("/api/jsr250/locked")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicMethodIsAnonymousAccessible() throws Exception {
        mvc.perform(get("/api/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void anonymousCannotReachProtectedMethod() throws Exception {
        mvc.perform(get("/api/secured/admin"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### Vì sao bộ test này phát hiện thiếu flag?

- Nếu quên `securedEnabled = true` nhưng vẫn bật `jsr250Enabled = true`, member GET /api/secured/admin có thể vượt qua HTTP `authenticated()` rồi gọi service **không có check @Secured**, trả 200; test đòi 403 sẽ fail.
- Nếu quên `jsr250Enabled = true` nhưng vẫn bật `securedEnabled = true`, member GET /api/jsr250/admin và admin GET /api/jsr250/locked có thể không bị JSR-250 interceptor kiểm tra; test sẽ phát hiện.
- Nếu cả hai tắt, các test positive vẫn có thể pass vì method body chạy, nhưng **negative tests** fail — đây là lý do chỉ kiểm thử admin được phép chưa đủ.
- Test HTTP Basic còn kiểm tra user/password được provider xác thực; nhưng để kiểm thử thuần method security, có thể dùng `@WithMockUser` đúng phạm vi.

Những nhận định trên áp dụng khi không có **một cơ chế authorization khác** đồng thời chặn các endpoints; nếu HTTP rule đã yêu cầu ROLE_ADMIN, test member bị 403 ở filter sẽ không chứng minh method security đang bật. Bài cố ý đặt HTTP rule chung là `authenticated()` để kiểm tra role ở method.

### Một test bean trực tiếp với @WithMockUser

Tạo `src/test/java/com/example/methodroles/MethodSecurityBeanTest.java`:

~~~java
package com.example.methodroles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodSecurityBeanTest {

    @Autowired MethodProtectedService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminMayCallSecured() {
        assertEquals("secured-admin-ok", service.securedAdmin());
        assertEquals("roles-allowed-admin-ok",
                     service.rolesAllowedAdmin());
    }

    @Test
    @WithMockUser(roles = "USER")
    void memberCannotCallSecuredOrJsr250() {
        assertThrows(AccessDeniedException.class,
                     () -> service.securedAdmin());
        assertThrows(AccessDeniedException.class,
                     () -> service.rolesAllowedAdmin());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void denyAllBlocksAdmin() {
        assertThrows(AccessDeniedException.class,
                     () -> service.locked());
    }
}
~~~

`@WithMockUser(roles = "ADMIN")` tạo một test Authentication có authority `ROLE_ADMIN` theo convention của Spring Security Test. Nó **không** chứng minh HTTP Basic/password verification đã chạy. Test bean trực tiếp rất hữu ích để kiểm tra method proxy, nhưng không thay thế MockMvc integration khi cần xác minh authentication/HTTP mapping.

**Test này gọi bean do Spring inject, không gọi `new MethodProtectedService()`.** Điều đó quan trọng: object tạo bằng `new` sẽ bỏ qua Spring proxy và có thể cho kết quả khác.

### Một negative test dành cho self-invocation

Nếu service có method `outer()` gọi `this.securedAdmin()`, cần test riêng đường đó. Đừng nghĩ test `service.securedAdmin()` qua proxy đã chứng minh mọi code path nội bộ được bảo vệ. Cách tối ưu thường là tách phương thức nhạy cảm sang bean khác hoặc thêm check ở business boundary phù hợp, sau đó test entry point thực.

## 9. Các quyết định 401, 403 và lỗi AOP

Trong ứng dụng HTTP Basic demo:

| Tình huống | Kết quả điển hình | Vì sao |
| --- | --- | --- |
| Anonymous GET /api/secured/admin | 401 | HTTP rule `authenticated()` dùng Basic entry point |
| Member được HTTP cho qua nhưng method yêu cầu ADMIN | 403 | Method-security interceptor từ chối role |
| Admin có ROLE_ADMIN gọi @Secured admin | 200 | Manager grant |
| Admin gọi @DenyAll | 403 | JSR-250 interceptor deny |
| Public method @PermitAll nhưng HTTP URL đòi authentication | Có thể 401 với anonymous | HTTP filter chặn trước method |
| Method interceptor không được bật | Có thể 200 ngoài ý muốn | Annotation có trong source nhưng không thực thi |
| Method code tự ném runtime exception | Phụ thuộc error handler | Không phải mọi exception đều là authorization denial |

Trong nhiều bản Spring Security, khi method security từ chối sẽ ném một exception thuộc họ `AccessDeniedException` (ví dụ `AuthorizationDeniedException`). `ExceptionTranslationFilter` thường chuyển exception khi phát sinh trong Servlet filter chain sang `AccessDeniedHandler`/AuthenticationEntryPoint phù hợp. Gọi method trực tiếp trong một service test có thể nhận exception thay vì HTTP status.

**Không catch AccessDeniedException rồi trả dữ liệu nhạy cảm** vì tưởng đó là cách xử lý UI lỗi. Nếu muốn response 403/JSON, xử lý bằng error response layer thích hợp nhưng vẫn giữ authorization deny.

### HTTP checks và method checks có thể cùng chạy

Một request có thể được HTTP filter cho qua vì role hợp lệ nhưng bị method-security chặn do quyền khác. Điều này không mâu thuẫn; đó là defense in depth. Tuy nhiên, nếu hai nơi chứa policy lệch nhau, người dùng có thể gặp các lỗi khó hiểu. Giữ một model role rõ ràng, test cả HTTP và method, đừng cấp `permitAll()` cho toàn API chỉ để bảo vệ bằng method-level.

## 10. So sánh @Secured, @RolesAllowed và @PreAuthorize

| Tiêu chí | @Secured | @RolesAllowed | @PreAuthorize |
| --- | --- | --- | --- |
| Nguồn annotation | Spring Security | Jakarta JSR-250 | Spring Security |
| Import | `org.springframework.security.access.annotation.Secured` | `jakarta.annotation.security.RolesAllowed` | `org.springframework.security.access.prepost.PreAuthorize` |
| Flag bật riêng | `securedEnabled=true` | `jsr250Enabled=true` | `prePostEnabled=true` (mặc định thường bật) |
| Giá trị phổ biến | `"ROLE_ADMIN"` | `"ADMIN"` | `"hasRole('ADMIN')"` |
| Nhiều role | OR | OR | Có thể dùng AND/OR tùy expression |
| Object ownership/tenant | Không diễn đạt trực tiếp bằng biểu thức | Không diễn đạt trực tiếp bằng biểu thức | Có thể gọi policy bean/so sánh tham số theo dữ liệu tin cậy |
| Có @PermitAll/@DenyAll cùng họ? | Không | Có | Có các biểu thức/annotation pre/post khác, không đồng nhất |
| Dùng tốt nhất | Legacy/simple fixed authorities | Standard role-based declarations | Quy tắc linh hoạt, object-level, kết hợp điều kiện |

Ví dụ một rule đòi cả role và điều kiện nghiệp vụ:

~~~java
// Fragment ví dụ trong Spring bean với method security enabled.
@PreAuthorize("hasRole('ADMIN') and @tenantPolicy.canEdit(authentication, #projectId)")
public void editProject(long projectId) {
    // ...
}
~~~

Đây **không** phải file runnable: cần bean `tenantPolicy` đã được Spring quản lý, method `canEdit(...)` đúng contract, phương thức service thực, parameter name metadata đáng tin, cấu hình `@EnableMethodSecurity` và kiểm thử policy với DB. Không cho phép `projectId` do client tự khai báo là bằng chứng ownership; dữ liệu tenant/owner phải đến từ store tin cậy.

Với điều kiện phức tạp hơn, đôi khi một custom `AuthorizationManager<MethodInvocation>` hoặc policy service chung dễ kiểm thử/duy trì hơn một SpEL dài.

### Khi nào giữ @Secured hoặc @RolesAllowed?

- Codebase sẵn có role-based checks đơn giản, muốn giữ cách diễn đạt gọn.
- Yêu cầu phải dùng Jakarta JSR-250 để nhất quán các module.
- Chính sách chỉ là “có ít nhất một role được liệt kê” và không cần truy cập tham số/record.

Không nên ép tất cả quy tắc owner/tenant theo các role tĩnh; quyền `ROLE_USER` không chứng minh một người được sửa **bất kỳ** project nào.

## 11. Java 17 độc lập: mô phỏng ánh xạ roles

Để thấy sự khác biệt giữa `@Secured("ROLE_ADMIN")` và `@RolesAllowed("ADMIN")`, chương trình sau mô phỏng cách kiểm tra authorities với prefix mặc định. Nó **không sử dụng Spring Security**, không chạy annotation interceptor và không chứng minh phương thức có được Spring proxy bảo vệ. Mục đích chỉ là tách logic **role name → authority** và OR semantics.

Lưu file `RoleAnnotationPolicyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Set;

public class RoleAnnotationPolicyDemo {

    record DemoUser(String name, Set<String> authorities) {}

    static boolean secured(DemoUser user, String... authorityNames) {
        if (user == null) {
            return false;
        }
        return Arrays.stream(authorityNames)
                .anyMatch(user.authorities()::contains);
    }

    static boolean rolesAllowed(DemoUser user, String... roleNames) {
        if (user == null) {
            return false;
        }
        return Arrays.stream(roleNames)
                .map(role -> role.startsWith("ROLE_")
                        ? role : "ROLE_" + role)
                .anyMatch(user.authorities()::contains);
    }

    static String label(boolean granted) {
        return granted ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        DemoUser admin = new DemoUser(
                "admin", Set.of("ROLE_ADMIN"));
        DemoUser auditor = new DemoUser(
                "auditor", Set.of("ROLE_AUDITOR"));
        DemoUser member = new DemoUser(
                "member", Set.of("ROLE_USER"));

        System.out.println("admin @Secured: " +
                label(secured(admin, "ROLE_ADMIN")));
        System.out.println("admin @RolesAllowed: " +
                label(rolesAllowed(admin, "ADMIN")));
        System.out.println("auditor any role: " +
                label(rolesAllowed(auditor, "ADMIN", "AUDITOR")));
        System.out.println("member any role: " +
                label(rolesAllowed(member, "ADMIN", "AUDITOR")));
        System.out.println("member @Secured ADMIN: " +
                label(secured(member, "ROLE_ADMIN")));
        System.out.println("unknown principal: " +
                label(rolesAllowed(null, "ADMIN")));
        System.out.println("raw authority mismatch: " +
                label(secured(admin, "ADMIN")));
    }
}
~~~

Biên dịch/chạy với JDK 17:

~~~bash
javac RoleAnnotationPolicyDemo.java
java RoleAnnotationPolicyDemo
~~~

Stdout **chính xác**:

~~~text
admin @Secured: ALLOW
admin @RolesAllowed: ALLOW
auditor any role: ALLOW
member any role: DENY
member @Secured ADMIN: DENY
unknown principal: DENY
raw authority mismatch: DENY
~~~

Nhận xét:

- `@Secured` mô hình dùng tên authority đúng như khai báo; `ADMIN` không tự thành `ROLE_ADMIN`.
- `@RolesAllowed` mô hình thêm prefix theo convention nếu cần.
- Có **ít nhất một** role trong danh sách là đủ.
- Một principal vắng mặt hoặc không có authority cần thiết bị deny.
- Đây là mô hình **giải thích**, không phải bản sao đầy đủ Jsr250AuthorizationManager hay SecuredAuthorizationManager; thực tế có cấu hình role prefix, role hierarchy, authentication trust và proxy semantics riêng.

## 12. Những cạm bẫy cấu hình và nâng cấp

### 12.1. Thiếu flag securedEnabled

~~~java
// CHƯA ĐỦ nếu ứng dụng cần @Secured:
@EnableMethodSecurity
~~~

Mặc định pre/post authorization được bật theo cấu hình thông dụng, nhưng secured annotation không tự được bật. Một method `@Secured("ROLE_ADMIN")` có thể chạy cho member nếu không có một cơ chế bảo vệ khác. Cách sửa:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Cần chạy negative tests: member gọi service admin phải bị deny.

### 12.2. Thiếu flag jsr250Enabled

~~~java
// CHƯA ĐỦ nếu ứng dụng cần @RolesAllowed/@DenyAll/@PermitAll:
@EnableMethodSecurity(securedEnabled = true)
~~~

Cách sửa:

~~~java
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
~~~

Nếu một method `@DenyAll` vẫn được gọi bởi admin, đó là tín hiệu mạnh rằng JSR-250 interceptor chưa hoạt động hoặc lời gọi bypass proxy.

### 12.3. Dùng sai import

Trong Boot 3, dùng `jakarta.annotation.security.RolesAllowed`, không sao chép máy móc `javax.annotation.security.RolesAllowed` từ bài cũ. Nếu import vẫn compile nhờ dependency Java EE cũ, không có nghĩa cấu hình Jakarta JSR-250 của Spring Security mới sẽ nhận diện annotation đó.

### 12.4. Viết nhầm ROLE_ prefix

`@Secured("ADMIN")` với principal `ROLE_ADMIN` có thể deny. `@RolesAllowed("ADMIN")` với principal `ROLE_ADMIN` thường allow dưới default prefix. Ngược lại, nếu identity system cung cấp authority `ADMIN` không có prefix, cần cấu hình role mapping đồng nhất; đừng sửa từng annotation tùy hứng.

### 12.5. Dùng @Secured như SpEL

~~~java
// SAI VỀ Ý NGHĨA: @Secured không parse biểu thức hasRole(...).
@Secured("hasRole('ADMIN')")
public void operation() {}
~~~

Nếu cần SpEL, dùng `@PreAuthorize("hasRole('ADMIN')")` với method-security pre/post enabled. Đây là fragment minh họa lỗi, không phải logic được khuyến nghị.

### 12.6. Cho rằng danh sách vai trò là AND

`@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})` và `@RolesAllowed({"ADMIN", "AUDITOR"})` biểu diễn **OR**. Để yêu cầu đồng thời nhiều điều kiện, dùng policy rõ ràng; hãy unit test member chỉ có một role không được grant nếu business thật sự yêu cầu hai roles.

### 12.7. Bỏ qua self-invocation

Một method không annotated gọi `this.securedMethod()` có thể bypass interceptor. Phân tách trách nhiệm bean, inject proxy đúng cách hoặc đặt enforce ở business boundary. Test đường gọi thực chứ không chỉ gọi securedMethod() trực tiếp qua proxy.

### 12.8. Đặt annotation trên private/final method

Proxy-based method security có những giới hạn với private/final và phương thức không được proxy. Dùng public non-final methods cho điểm chặn chính, đặt trên Spring-managed bean và kiểm tra kiểu proxy thực khi có interface/AspectJ/annotation trên interface.

### 12.9. Tự tạo service bằng new

~~~java
// NGUY HIỂM nếu nghĩ annotation sẽ tự chạy:
MethodProtectedService service = new MethodProtectedService();
service.securedAdmin();
~~~

Object tự tạo không phải Spring proxy. Trong test, inject `@Autowired MethodProtectedService`. Trong ứng dụng, dùng constructor injection thay vì `new` để bypass container.

### 12.10. HTTP layer chặn trước, làm test “xanh giả”

Nếu HTTP rule đã `hasRole("ADMIN")` cho `/api/secured/admin`, member bị 403 ở filter dù `@Secured` đang tắt. Kiểm thử riêng service bean với `@WithMockUser` hoặc đặt HTTP gate chỉ `authenticated()` như demo, để chắc chắn method security thật sự đưa ra quyết định.

### 12.11. Hợp nhất nhiều annotation không có chủ đích

Đặt đồng thời `@Secured` và `@PreAuthorize` hay `@RolesAllowed` trên cùng method có thể kích hoạt nhiều interceptors/policies; kết quả không nhất thiết là “annotation cuối cùng thắng”. Cần một contract rõ ràng và test với role matrix. Tốt nhất tránh annotation mâu thuẫn trên một method.

### 12.12. Quên @Async và SecurityContext

SecurityContext theo request thường gắn với thread. Khi một method protected được gọi trong một executor thread, nó không mặc nhiên có cùng Authentication. Spring Security có các giải pháp context propagation thích hợp, nhưng phải dùng có chủ đích và tránh kéo context người dùng vào background job lâu dài ngoài policy. Khi không có identity đáng tin, không được tự grant.

### 12.13. Dựa vào role USER cho object-level access

Role chỉ là thuộc tính chung; không chứng minh một order/project thuộc user. Nếu method `getInvoice(long id)` chỉ có `@RolesAllowed("USER")`, người dùng có thể cố truy cập invoice của người khác. Cần object-level checks từ dữ liệu server đáng tin, ví dụ tenant/owner, ở service hoặc policy layer.

### 12.14. Thay đổi authority mapping không sửa test

Một migration identity provider có thể đổi authorities từ `ROLE_ADMIN` sang `admin` hoặc scopes. Annotation cũ sẽ deny hoặc hành xử khác. Trong test cần assert authorities thực tế và behavior của `@Secured`/`@RolesAllowed`, không chỉ kiểm tra Authentication.isAuthenticated().

## 13. Nâng cao: kế thừa, proxy order và transaction

### Class-level security trong hierarchy

Annotation có thể được khai báo ở class hoặc method tùy Target và thư viện; Spring Security sẽ resolve security metadata qua các method/class khi proxy thực thi. Với interface inheritance, method override, bridge methods, overloaded methods và bean có nhiều interfaces, cách nhận annotation có thể phức tạp. Nên đặt quy tắc ở **concrete service methods** hoặc quy ước được test, và tạo test cho từng trường hợp inheritance thực sự dùng; không cho rằng annotation đặt ở một interface bất kỳ sẽ được framework tìm thấy theo mọi cấu hình.

### Self invocation và transactional proxy

Cả `@Transactional` và method security có thể sử dụng AOP interception. Việc gọi qua `this` thường bypass proxy-related behavior của cả hai. Nếu một method transactional gọi method restricted trong cùng instance, không được suy đoán interceptor của restricted method sẽ tự chạy. Tách bean hoặc điều chỉnh kiến trúc.

### Thứ tự AOP advisors

Method security và transaction advice có order; tùy cấu hình, authorization có thể diễn ra trước hoặc trong transaction. Với policy đọc dữ liệu, cần tính đến race condition và database consistency. Không cố tối ưu advisor order trước khi có chính sách nghiệp vụ/test rõ ràng.

### Exceptions và phản hồi API

Trong ứng dụng API, một method bị deny thường dẫn đến AccessDeniedException, rồi qua Servlet exception translation có thể thành 403/JSON. Nếu service được gọi từ message consumer, exception có thể làm message retry hoặc chuyển DLQ theo cơ chế riêng; không có HTTP status ở bối cảnh đó. Cần quyết định cách xử lý fail closed cho từng entry point mà không nuốt exception rồi vẫn thực hiện nghiệp vụ.

## 14. Hướng dẫn kiểm thử production-grade

### 14.1. Test matrix hai annotation

| Identity | @Secured ROLE_ADMIN | @RolesAllowed ADMIN | Multi-role ADMIN/AUDITOR | @DenyAll |
| --- | --- | --- | --- | --- |
| Admin | Allow | Allow | Allow | Deny |
| Auditor | Deny | Deny | Allow | Deny |
| Member | Deny | Deny | Deny | Deny |
| Anonymous | Deny | Deny | Deny | Deny |

Test nên có ít nhất một **positive** và một **negative** cho **mỗi loại annotation**. Ngoài HTTP tests, test service bean trực tiếp để phát hiện thiếu flag nhưng HTTP gate tình cờ che mất lỗi.

### 14.2. Test thiếu cấu hình một cách có kiểm soát

Trong môi trường test/laboratory, có thể tạo một application context riêng chỉ bật `@EnableMethodSecurity` mặc định, inject bean có `@Secured`/`@RolesAllowed` và quan sát sự khác biệt. Đây là **thí nghiệm chứng minh cơ chế**, không phải cấu hình deploy. Không cố ý bỏ flags ở production để so sánh.

### 14.3. Test trực tiếp từ controller và từ service caller khác

Một service có thể được gọi từ controller, scheduler hoặc message handler. Những caller đó có authentication context không giống nhau. Với caller ngoài HTTP, cần xác định principal/service identity hợp pháp, không dùng một arbitrary admin Authentication để khiến mọi test xanh. Nếu business logic cần identity của user gốc, cần truyền qua tầng tin cậy và kiểm soát lifecycle.

### 14.4. Test thay đổi role và revoke quyền

Authorities thường được nạp khi authentication. Khi quyền một user bị thu hồi trong DB/IdP, Authentication/session đang hoạt động có thể còn authority cũ cho tới khi được refresh/reauthenticated theo policy. Method annotation không tự làm role revocation realtime. Cần thiết kế lifecycle của authorities, token/session expiry hoặc truy vấn policy động khi cần thu hồi nhanh.

### 14.5. Test API version và non-HTTP paths

Nếu một service method được gọi từ nhiều controllers hoặc interface API, method security sẽ tăng độ phủ; nhưng chỉ khi các đường gọi đi qua proxy. Test routes/versions mới và gọi trực tiếp từ một Spring-managed bean khác để tránh bypass. Đừng để controller tự tạo service hoặc gọi internal methods vượt rule.

### 14.6. Log/audit an toàn

Có thể log sự kiện quyền bị từ chối (method name, request ID, policy key, result) với lượng thông tin tối thiểu. Không log password, bearer token, session ID, Authentication chứa credentials, method arguments nhạy cảm hoặc thông tin user chưa được cho phép đọc. Một AccessDeniedException không chứng minh người dùng có ý tấn công; phản hồi người dùng nên trung tính.

## 15. Câu hỏi và bài tập thực hành

**Bài 1.** Dự án đã dùng `@EnableMethodSecurity` không tham số và có method `@Secured("ROLE_ADMIN")`. Test member vẫn gọi được method. Sai ở đâu?

**Đáp án:** `securedEnabled` mặc định không bật trong cấu hình thông dụng Spring Security 6. Cần `@EnableMethodSecurity(securedEnabled=true)`, bảo đảm bean/proxy được dùng và viết negative test trực tiếp.

**Bài 2.** Một service dùng `@RolesAllowed("ADMIN")` nhưng chỉ bật `securedEnabled=true`. Có đủ chưa?

**Đáp án:** Chưa. `@RolesAllowed` thuộc JSR-250, cần `jsr250Enabled=true`. Hai flags độc lập.

**Bài 3.** `User.withUsername("admin").roles("ADMIN")` tạo authority gì theo default Spring Security?

**Đáp án:** `ROLE_ADMIN`. Vì vậy `@Secured("ROLE_ADMIN")` và `@RolesAllowed("ADMIN")` có thể cùng grant khi các cơ chế đã bật và prefix theo mặc định.

**Bài 4.** Vì sao `@Secured("ADMIN")` có thể deny một principal có `ROLE_ADMIN`?

**Đáp án:** `@Secured` nhận authority name literal; `ADMIN` khác `ROLE_ADMIN`. Phải đồng bộ role/authority mapping.

**Bài 5.** Với `@RolesAllowed({"ADMIN","AUDITOR"})`, user chỉ có ROLE_AUDITOR có được phép không?

**Đáp án:** Có, vì mảng roles ở đây mang semantics OR (một trong các roles), không phải AND.

**Bài 6.** `@DenyAll` đã được đặt trên method nhưng admin vẫn gọi được. Hai nguyên nhân đầu tiên cần kiểm tra là gì?

**Đáp án:** `jsr250Enabled=true` đã bật chưa, và lời gọi có qua Spring proxy không. Ngoài ra cần kiểm tra import `jakarta.annotation.security.DenyAll`, target method public và class được Spring quản lý.

**Bài 7.** `@PermitAll` đặt trên service method. Anonymous request GET /private vẫn nhận 401, vì sao?

**Đáp án:** HTTP SecurityFilterChain có thể yêu cầu `authenticated()` trước khi controller gọi method. `@PermitAll` chỉ cho phép ở lớp JSR-250 method security, không vượt qua HTTP authorization.

**Bài 8.** Controller dùng `new MethodProtectedService()` rồi gọi `securedAdmin()`. Có an toàn không?

**Đáp án:** Không thể coi là an toàn vì object không phải Spring AOP proxy; annotation có thể không được kiểm tra. Inject bean từ ApplicationContext và kiểm thử.

**Bài 9.** Bean có `outer()` gọi `this.securedAdmin()`, trong khi `outer()` không annotated. Test trực tiếp `bean.securedAdmin()` bị deny nhưng `bean.outer()` lại chạy thành công. Vì sao?

**Đáp án:** Self-invocation trong cùng instance thường bypass proxy interception. Tách protected method sang bean khác hoặc enforce ở boundary phù hợp.

**Bài 10.** `@Secured("hasRole('ADMIN')")` có tương đương `@PreAuthorize("hasRole('ADMIN')")` không?

**Đáp án:** Không. `@Secured` không parse SpEL `hasRole(...)`, còn `@PreAuthorize` sử dụng biểu thức authorization. Chọn API phù hợp và bật tương ứng.

**Bài 11.** Một test chỉ xác nhận admin GET /api/secured/admin trả 200. Nó chứng minh securedEnabled đã bật chưa?

**Đáp án:** Chưa. Nếu flag tắt, method vẫn có thể chạy và trả 200. Cần test member bị deny khi HTTP chỉ đòi authenticated, hoặc test bean qua @WithMockUser để trực tiếp chứng minh interceptor.

**Bài 12.** Một service có `@RolesAllowed("USER")` và method `getInvoice(id)`. Alice có ROLE_USER nhưng đọc được hóa đơn của Bob. Sai ở đâu?

**Đáp án:** Role USER không xác định object ownership. Cần policy owner/tenant từ dữ liệu server (ở service/AuthorizationManager/PreAuthorize thích hợp), đồng thời test negative-object cases.

**Bài 13.** Sau khi một user bị thu hồi ROLE_ADMIN trong DB, một phiên đăng nhập cũ vẫn gọi được method @Secured admin. Có phải annotation bị lỗi?

**Đáp án:** Không nhất thiết. Authentication có thể giữ authorities được nạp khi login; phải có cơ chế refresh/revocation/session invalidation hoặc policy động phù hợp. Annotation không tự truy vấn lại DB mỗi lần trong mọi kiến trúc.

**Bài 14.** Vì sao một method trong scheduled job có `@RolesAllowed("ADMIN")` có thể bị deny dù HTTP test admin chạy?

**Đáp án:** Background thread có thể không có Authentication của HTTP user. Cần định nghĩa service identity/context propagation đáng tin; không tự biến job thành admin để né policy.

## 16. Checklist triển khai và vận hành

- [ ] Dùng Spring Boot 3/Spring Security 6 với import `jakarta.annotation.security.*`, không nhầm namespace `javax.annotation.*` của hướng dẫn cũ.
- [ ] Nếu dùng `@Secured`, bật `@EnableMethodSecurity(securedEnabled=true)`.
- [ ] Nếu dùng `@RolesAllowed`/`@PermitAll`/`@DenyAll`, bật `@EnableMethodSecurity(jsr250Enabled=true)`.
- [ ] Nếu dùng cả hai, bật **cả hai flags** và có negative tests cho từng cơ chế.
- [ ] Đối chiếu `ROLE_` prefix, `roles(...)`, `authorities(...)` và identity provider mapping.
- [ ] Xem nhiều giá trị annotation là **OR**, không phải AND.
- [ ] Không dùng `@Secured` như SpEL; rule phức tạp dùng `@PreAuthorize`/policy service thích hợp.
- [ ] Đặt điểm chặn ở public methods của Spring-managed beans, lời gọi đi qua proxy.
- [ ] Không dựa vào private/final/self-invoked methods hoặc objects tạo bằng `new` để bảo vệ quyền.
- [ ] Tách các method nhạy cảm sang bean phù hợp để tránh self-invocation bypass.
- [ ] Test trực tiếp Spring-injected service bean và HTTP MockMvc, có cả allow và deny cases.
- [ ] Không để HTTP hasRole rule che mất lỗi method-security trong test chứng minh annotation.
- [ ] Phân biệt HTTP authentication/authorization với method security và tránh blanket permitAll.
- [ ] Không tin user-supplied role/tenant headers; authorities phải đến từ authentication provider đáng tin.
- [ ] Khi policy phụ thuộc tài nguyên, kiểm tra owner/tenant và consistency tại service/data boundary.
- [ ] Với @Async/scheduler/queue, thiết kế identity/context propagation và test từng entry point.
- [ ] Review khi upgrade Spring Security 6 minor, AOP proxy mode, role hierarchy và authority revocation.
- [ ] Giữ audit tối thiểu, không log credentials hoặc sensitive method arguments.

**Kết luận:** `@Secured` và `@RolesAllowed` đều giúp bảo vệ **lời gọi phương thức** bằng role/authority, nhưng thuộc **hai cơ chế được bật độc lập**. Trong Spring Security 6, hãy dùng `@EnableMethodSecurity(securedEnabled=true, jsr250Enabled=true)` nếu dùng cả hai, thống nhất role prefix `ROLE_`, kiểm thử **negative cases** để chứng minh annotation thật sự đang chạy, và không quên giới hạn proxy/self-invocation cũng như những quy tắc object-level vượt quá khả năng role checks đơn giản.