# Phân biệt tính năng ổn định, tính năng phụ thuộc phiên bản và phần cần tự xây dựng trong Spring Security

> **Phạm vi:** Spring Security cho ứng dụng Java/Spring Boot, ưu tiên **Servlet / Spring MVC**. Bài này hướng dẫn xác định thứ gì đã được framework hỗ trợ, thứ gì phải kiểm tra theo phiên bản và thứ gì là chính sách/nghiệp vụ do ứng dụng chịu trách nhiệm. “Ổn định” ở đây là **mô hình và năng lực nền tảng có thể dựa vào để thiết kế**, không phải lời hứa rằng tên lớp, method, cấu hình mặc định hoặc hành vi chi tiết sẽ không đổi giữa các bản phát hành.

## 1. Vì sao phải phân loại trước khi viết code?

Trong một dự án, câu “Spring Security hỗ trợ đăng nhập, JWT, phân quyền và bảo vệ API” chứa nhiều lớp trách nhiệm khác nhau:

- Spring Security có thành phần chuẩn để **xác thực** yêu cầu, **thực thi** quy tắc phân quyền và **kết nối** một số giao thức xác thực/ủy quyền.
- Cách kích hoạt một thành phần, tên DSL, matcher, phiên bản Java/Spring Boot tương thích hoặc giá trị mặc định có thể **thay đổi theo phiên bản**.
- Quy tắc “chỉ chủ tài liệu mới được xem”, “tài khoản bị khóa sau quy trình điều tra”, “một tổ chức không được xem dữ liệu của tổ chức khác” là **quyết định nghiệp vụ**. Framework chỉ cung cấp điểm gắn để ứng dụng thực thi quyết định đó.

Ba câu hỏi cần tách rõ khi nhận yêu cầu:

1. **Năng lực có sẵn không?** Ví dụ framework đã có `PasswordEncoder`, HTTP Basic, form login, OAuth2 Resource Server, method security.
2. **Năng lực ấy dùng thế nào trên bộ phiên bản đang chạy?** Ví dụ `authorizeRequests` hay `authorizeHttpRequests`, matcher nào được hỗ trợ, có cần module bổ sung không.
3. **Ai định nghĩa dữ liệu/chính sách/quy trình?** Ví dụ quyền sở hữu tài liệu, nơi lưu người dùng, quyết định cấp/hủy quyền, onboarding, kiểm toán.

Nếu trộn ba câu hỏi, nhóm dễ tự viết lại tính năng framework đã có, hoặc ngược lại tưởng rằng chỉ cần bật một starter là đã có toàn bộ quy trình bảo mật của sản phẩm.

## 2. Ba nhóm cần ghi rõ trong thiết kế

| Nhóm | Dấu hiệu | Ví dụ trong Spring Security | Việc cần làm |
| --- | --- | --- | --- |
| **A — Nền tảng tương đối ổn định** | Là khái niệm/điểm mở rộng cốt lõi được tài liệu hóa qua các phiên bản; ứng dụng dựa vào nó ở cấp thiết kế | `Authentication`, `SecurityContext`, xác thực trước phân quyền, Servlet `SecurityFilterChain`, `PasswordEncoder`, rule `authenticated`/`permitAll`/`hasAuthority` | Hiểu cơ chế, chọn đúng module và kiểm thử chính sách, không tự thay một cơ chế đã được hỗ trợ tốt. |
| **B — Phụ thuộc phiên bản / cách tích hợp** | Tên API, mặc định, matcher, dependency, đường dẫn cấu hình hoặc semantic cụ thể thay đổi theo release/stack | `WebSecurityConfigurerAdapter` so với bean `SecurityFilterChain`; `antMatchers` so với `requestMatchers`; matcher Ant/MVC/PathPattern; Lambda DSL; Spring Boot 3 so với 4 | Ghim phiên bản, đối chiếu tài liệu **đúng version**, dùng migration guide và regression test. |
| **C — Phần sản phẩm cần tự xây hoặc tích hợp** | Phụ thuộc user/tenant/dữ liệu/quy trình riêng; framework không thể suy ra chính sách đúng | Đăng ký tài khoản, phê duyệt vai trò, xác định owner của tài liệu, quy tắc tổ chức, mapping quyền từ IdP, thông báo bảo mật, xử lý sự kiện kiểm toán theo yêu cầu | Thiết kế model, use case, lưu trữ, luồng phê duyệt, test nghiệp vụ; gắn vào các điểm mở rộng của framework. |

**Lưu ý:** Một tính năng có thể nằm ở **nhiều nhóm cùng lúc**. “Dùng JWT cho API” gồm năng lực decode/verify token của resource server (A), cấu hình `issuer-uri`/`JwtDecoder` theo version (B), và quyết định cấp token, nguồn identity, scope/tenant và hủy quyền (C hoặc một IdP bên ngoài). Đừng gắn duy nhất một nhãn cho toàn bộ hệ thống.

### Các nhầm lẫn điển hình

- **“Spring Security có `hasRole`, vậy tự biết ai là chủ hóa đơn.”** Sai: framework so role/authority; nó không biết dữ liệu hóa đơn hoặc quan hệ owner.
- **“Có Resource Server là API tự phát hành access token.”** Sai: resource server **kiểm tra** token; authorization server/IdP mới đóng vai trò phát hành token theo luồng được cấu hình.
- **“Phiên bản mới chỉ thay tên method.”** Sai: một số matcher, filter, persistence hoặc mặc định có thể thay đổi ngữ nghĩa; việc migrate cần test hành vi.
- **“Đã có login nghĩa là có quản lý vòng đời tài khoản.”** Sai: màn hình/luồng login không tự cung cấp đầy đủ đăng ký, xác minh email, hỗ trợ khách hàng, quản lý quyền, chống gian lận.

## 3. Phần nền tảng: các nguyên lý nên học thật chắc

### 3.1. Authentication khác authorization

**Authentication (xác thực)** trả lời: *yêu cầu này đại diện cho ai, và bằng chứng là gì?* Với ứng dụng web, framework có thể tạo `Authentication` sau khi xử lý Basic, form login, OAuth2/OIDC hoặc token Bearer. `Authentication` mang principal, trạng thái authenticated và tập `GrantedAuthority`.

**Authorization (phân quyền)** trả lời: *chủ thể vừa xác thực có được thực hiện hành động này trên tài nguyên này không?* Điều kiện có thể là `hasRole("ADMIN")`, `hasAuthority("invoice:read")`, hoặc kết quả chính sách do ứng dụng tra cứu từ database.

Đăng nhập thành công **không** đồng nghĩa được truy cập mọi dữ liệu. HTTP 401 thường nói thiếu/chưa chấp nhận xác thực; HTTP 403 thường nói yêu cầu bị cấm dù đã có danh tính (còn phụ thuộc entry point, loại luồng và exception mapping cụ thể).

### 3.2. Đường đi Servlet được framework quản lý

```text
HTTP request
   ↓
Servlet container
   ↓
DelegatingFilterProxy → FilterChainProxy
   ↓  chọn SecurityFilterChain đầu tiên khớp request
Các security filter: SecurityContext, CSRF/headers, authentication, authorization...
   ↓  nếu được phép
DispatcherServlet → Controller → Service → Repository
```

`SecurityFilterChain` chọn những filter áp dụng cho một request. Trong chain, `authorizeHttpRequests` định nghĩa quy tắc HTTP. Nếu nhiều chain, chỉ **chain đầu tiên khớp** được chọn; nếu không có chain nào khớp, Spring Security có thể không bảo vệ request đó. Vì vậy cần định nghĩa phạm vi chain rõ ràng và có fallback thích hợp.

Mô hình filter chain là nền tảng, nhưng **cấu trúc/mặc định của filter cụ thể và cách khai báo bean vẫn phải kiểm tra theo phiên bản**. Trong WebFlux, điểm mở rộng tương ứng là `SecurityWebFilterChain`; không bê cấu hình Servlet sang Reactive.

### 3.3. SecurityContext và phạm vi request

`SecurityContextHolder` giúp các thành phần Spring Security truy cập `SecurityContext` hiện tại. Ở ứng dụng Servlet thông thường, chiến lược mặc định sử dụng `ThreadLocal`. Spring Security quản lý việc thiết lập và dọn context ở filter chain.

Điều đó **không bảo đảm** context tự truyền tới mọi thread, `@Async`, queue, scheduler hoặc một request ở service khác. Khi đổi mô hình thực thi, phải thiết kế cách truyền danh tính, kiểm tra tính hợp lệ và làm sạch context thay vì tự sao chép `ThreadLocal` một cách mù quáng.

### 3.4. Framework thực thi rule, ứng dụng quyết định policy

Các rule thường dùng:

- `permitAll()`: mọi request khớp được phép đi tiếp; request vẫn qua security filter chain.
- `authenticated()`: cần danh tính đã được xác thực.
- `hasRole("ADMIN")`: theo quy ước mặc định, cần authority `ROLE_ADMIN`.
- `hasAuthority("invoice:approve")`: so chính xác một authority.
- `denyAll()`: từ chối yêu cầu.
- `access(AuthorizationManager)`: cho phép chính sách tùy biến tại điểm authorization.

`@EnableMethodSecurity` cùng `@PreAuthorize` có thể bảo vệ logic ở phương thức Spring bean. Điều này hữu ích khi một service được gọi từ nhiều controller/entry point, nhưng cũng cần nhớ giới hạn proxy: lời gọi trực tiếp từ một phương thức tới phương thức khác trong cùng bean có thể **không đi qua interceptor**. Kiểm soát tài nguyên nhạy cảm phải được thực thi tại nơi dữ liệu được đọc/sửa, không chỉ dựa vào việc ẩn nút trên frontend.

### 3.5. Các bảo vệ HTTP có sẵn nhưng không phải “tự động an toàn tuyệt đối”

Spring Security có cơ chế hỗ trợ CSRF, security headers, session fixation protection, exception translation và nhiều cách xác thực. Tuy nhiên, việc bật/tắt/cấu hình từng cơ chế cần phù hợp ứng dụng.

Ví dụ: ứng dụng dùng session cookie và form login thường cần bảo vệ CSRF cho các phương thức thay đổi trạng thái. Một API thuần Bearer token có thể có mô hình threat khác; quyết định CSRF phải dựa trên cách trình duyệt gửi credentials, **không** dựa duy nhất vào chữ “REST”. CORS là chính sách trình duyệt; bật CORS không thay thế authorization. HTTPS/TLS, bảo vệ secret, kiểm soát tốc độ và hardening hạ tầng cũng cần trách nhiệm rõ ràng.

## 4. Những thứ phải khóa theo phiên bản trước khi sao chép code

Có hai tầng version cần kiểm tra: **Spring Boot → phiên bản Spring Security/Spring Framework được quản lý**, và các dependency security bổ sung. Đừng trộn snippet tài liệu của Spring Security 7 vào một dự án vẫn chạy Spring Security 6 rồi cho rằng sẽ compile.

| Chủ đề | Dấu mốc phiên bản / rủi ro | Cách xác minh |
| --- | --- | --- |
| Cấu hình Servlet | `WebSecurityConfigurerAdapter` deprecated ở 5.7 và bị loại ở 6.0; bean `SecurityFilterChain` là hướng hiện đại | Xem import và class trên classpath; chạy compile/test. |
| Phân quyền URL | `authorizeRequests`/`antMatchers` cũ được thay bằng `authorizeHttpRequests`/`requestMatchers` | So rule thứ tự, các request thực tế, status 401/403/200. |
| Matcher đường dẫn | 6.x có các lựa chọn Ant/MVC/PathPattern tùy cấu hình; 7.x chuyển sang `PathPatternRequestMatcher` và bỏ matcher Ant/MVC cũ | Test `/**`, servlet path, encoded path, trailing slash và HTTP method. |
| Cấu hình DSL | Lambda DSL đã có từ các bản 5.x, được ưu tiên ở 6.x và bắt buộc ở 7.x; chaining `.and()` cũ không còn là đường đi tương thích | Chuyển sang `http.authorizeHttpRequests(auth -> ...)` và `Customizer.withDefaults()`. |
| Custom DSL | API `HttpSecurity#apply` cũ được thay bằng `.with(...)` để tương thích hướng 7.x | Đối chiếu migration guide trước khi đổi custom configurer. |
| Runtime/framework | Spring Security 6.x gắn với hệ Spring Framework 6 / Boot 3; hướng nâng 7.x đi với Spring Framework 7 / Boot 4 | Kiểm tra BOM/dependency tree, JDK, release notes và hướng dẫn migration. |
| OAuth2/OIDC/SAML, testing, method security | Năng lực có mặt trong framework nhưng cần đúng artifact, provider configuration và API ở phiên bản đang dùng | Xem trang reference version-pinned cho đúng **Servlet hoặc Reactive**. |

### Ví dụ chuyển đổi một rule

**Mã lịch sử — minh họa cú pháp Spring Security 5.x, không dùng nguyên trạng với 6/7:**

```java
// Fragment trong configure(HttpSecurity http) của WebSecurityConfigurerAdapter cũ
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
    .and()
    .httpBasic();
```

**Mã hiện đại cho Spring Security 6.x — fragment đặt trong `SecurityFilterChain` bean:**

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
return http.build();
```

Đổi cú pháp **chưa đủ** để chứng minh di chuyển đúng: phải giữ chính sách, test thứ tự matcher, xác thực, quyền và các hành vi phụ như CSRF, login redirect. Ở 7.x, kiểm tra lại mọi pattern theo ngữ nghĩa `PathPattern`. Quy tắc "cụ thể trước, tổng quát sau" vẫn có giá trị học tập; **cú pháp matcher cụ thể** nằm trong nhóm B.

### Cách xem dependency thực đang chạy

```bash
# Maven: xem phiên bản dependency sau dependency management và transitive resolution
mvn dependency:tree -Dincludes=org.springframework.security

# Gradle (chạy trong project/module tương ứng)
./gradlew dependencies --configuration runtimeClasspath
```

Với Gradle đa module, chỉ kiểm tra configuration của module đang chạy; không lấy version từ một snippet trên web làm nguồn chân lý. Đọc thêm release notes của Spring Boot, Spring Security và các integration liên quan trước khi nâng.

## 5. Cái gì Spring Security hỗ trợ, và cái gì vẫn là việc của sản phẩm?

| Yêu cầu sản phẩm | Framework/chuẩn có thể cung cấp | Phần ứng dụng/đơn vị khác phải quyết định |
| --- | --- | --- |
| Đăng nhập username/password | Authentication filters, `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, form login | Người dùng lưu ở đâu; đăng ký, xác minh email, khôi phục mật khẩu, trạng thái khóa tài khoản và quy trình hỗ trợ. |
| Bảo vệ API bằng Bearer JWT | Resource Server, `JwtDecoder`, xác minh chữ ký và claim theo cấu hình, chuyển scope thành authority | Ai phát hành token, issuer/audience hợp lệ, keys, rotation, thời hạn, thu hồi, mapping user/tenant và phân quyền dữ liệu. |
| Đăng nhập qua OIDC/OAuth2 | OAuth2 Client/`oauth2Login`, redirect và trao đổi code theo cấu hình provider | Đăng ký app ở IdP, mapping người dùng nội bộ, quy tắc liên kết account, offboarding và xử lý tài khoản trùng. |
| Phân quyền theo role/scope | `hasRole`, `hasAuthority`, `AuthorizationManager`, method security | Danh sách vai trò/permission, ai có quyền cấp chúng, phạm vi dự án/tenant và quan hệ role với nghiệp vụ. |
| “Chỉ owner xem được tài liệu” | Điểm mở rộng `@PreAuthorize`/custom `AuthorizationManager` | Schema lưu owner, logic ownership, chuyển quyền, ngoại lệ quản trị, bảo vệ dữ liệu khỏi truy cập chéo. |
| MFA/OTP/passkeys | Có những thành phần và luồng hỗ trợ tùy release/module; có thể tích hợp IdP cung cấp MFA | Chính sách enrollment/recovery, cách áp dụng cho đối tượng nào, rủi ro mất thiết bị, truyền thông và hỗ trợ người dùng. |
| Rate limiting/chống bot | Có thể kết hợp filter/gateway/IdP/WAF hoặc thư viện khác | Giới hạn theo IP/user/tenant, thuật toán, phân tán, phản hồi 429, dashboard và vận hành. |
| Audit và cảnh báo | Sự kiện security, logging/integration hooks | Trường dữ liệu sự kiện, retention, cảnh báo, bảo mật log, phân tích gian lận, quy trình xử lý sự cố. |
| Phân quyền nhiều tổ chức | Ngữ cảnh principal/authority và điểm extension | Tenant isolation xuyên repository, DB, cache, message, query, file storage, test truy cập chéo. |

Không phải mọi tính năng nhóm C đều cần **tự viết từ đầu**. Nên ưu tiên **tích hợp** một Identity Provider, gateway hoặc thư viện đáng tin cậy khi phù hợp. Nhưng trách nhiệm kiểm tra chính sách nghiệp vụ, cấu hình và hành vi đầu cuối vẫn thuộc hệ thống.

### Ba vai trò OAuth2 dễ lẫn

```text
Người dùng ─► Client (web/mobile/app) ─► Authorization Server / IdP
                                           │ phát hành access token
                                           ▼
Client ─────── Bearer access token ───────► Resource Server (API)
                                           │ kiểm tra token/claims
                                           ▼
                                         Business service
                                           │ kiểm tra owner/tenant/policy
                                           ▼
                                          Dữ liệu
```

- **OAuth2 Client/OIDC login**: hỗ trợ tương tác đăng nhập và lấy token theo cấu hình; có thể cần hệ thống identity bên ngoài.
- **OAuth2 Resource Server**: xác minh bearer token JWT/opaque để bảo vệ API. Nó không tự nhiên trở thành nơi phát hành token chỉ vì thêm starter.
- **Authorization Server**: thành phần phát hành token, có thể là dịch vụ IdP bên ngoài hoặc hệ thống được triển khai bằng tính năng authorization server phù hợp. Thiết kế token issuance, client registration và lifecycle vẫn cần quyết định riêng.

Dù resource server xác thực JWT đúng chữ ký, API vẫn phải xét **audience, issuer, scope/authority, tenant và quyền với từng bản ghi** phù hợp threat model. Một JWT hợp lệ không mặc nhiên trao quyền đọc dữ liệu của bất kỳ khách hàng nào.

## 6. Ví dụ chạy được: framework kiểm tra danh tính, ứng dụng kiểm tra owner

Dự án nhỏ dưới đây dùng **Java 17+, Maven và Spring Boot 3.3.0 (Spring Security 6.x)** để minh họa cả ba nhóm. Đây là phiên bản **cố định cho ví dụ học tập**; khi làm sản phẩm thật, chọn nhánh được hỗ trợ và bản vá hiện hành. Mã demo cố ý dùng HTTP Basic và user trong bộ nhớ để tập trung vào ranh giới trách nhiệm; không dùng thông tin tài khoản demo cho production.

Chính sách:

1. `GET /public/health` được phép truy cập công khai (**năng lực A, cấu hình B**).
2. `GET /api/docs/{id}` yêu cầu đã đăng nhập (**A/B**), sau đó chỉ người sở hữu bản ghi được xem (**C**).
3. `GET /api/admin/stats` yêu cầu role ADMIN (**A/B**); dữ liệu thống kê trả về chỉ là demo.
4. Người dùng demo `alice` sở hữu tài liệu 1, `bob` sở hữu tài liệu 2; `admin` có role ADMIN nhưng không tự động được xem tài liệu của người khác vì policy owner chưa cho phép.

### 6.1. Cấu trúc

```text
spring-security-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/example/boundary/
    │   ├── BoundaryDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── ApiController.java
    └── test/java/example/boundary/
        └── SecurityBoundaryTest.java
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>spring-security-boundary-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/boundary/BoundaryDemoApplication.java`:

```java
package example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
```

`src/main/java/example/boundary/SecurityConfig.java`:

```java
package example.boundary;

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
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Phân loại:** `SecurityFilterChain`, `UserDetailsService`, `PasswordEncoder`, HTTP Basic, `@EnableMethodSecurity` là những năng lực framework hỗ trợ. Cú pháp Lambda DSL, `requestMatchers` và cách tạo bean đang được minh họa **theo Spring Security 6.x**. Danh sách user, role và password là **dữ liệu demo do ứng dụng cung cấp**, không phải user mà framework tự sinh ra cho mỗi sản phẩm.

`src/main/java/example/boundary/DocumentPolicy.java`:

```java
package example.boundary;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Dữ liệu demo: ứng dụng sở hữu quy tắc owner, không phải Spring Security.
    private final Map<Long, String> owners = Map.of(
        1L, "alice",
        2L, "bob"
    );

    public boolean canRead(String username, Long documentId) {
        return username != null && username.equals(owners.get(documentId));
    }
}
```

Ở sản phẩm thật, `owners` thường đến từ database và phải bị giới hạn theo tenant, tình trạng dữ liệu, quyền ủy quyền và các transaction liên quan. Hàm policy phải dựa trên **identity đáng tin từ `Authentication`**, không dựa vào tham số `userId` mà client có thể tùy ý gửi.

`src/main/java/example/boundary/DocumentService.java`:

```java
package example.boundary;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    // #p0 là tham số thứ nhất (documentId), không phụ thuộc tên tham số Java.
    @PreAuthorize("@documentPolicy.canRead(authentication.name, #p0)")
    public String read(Long documentId) {
        return "doc-" + documentId;
    }
}
```

`@PreAuthorize` là điểm thực thi do framework cung cấp; `documentPolicy.canRead` là **logic riêng của ứng dụng**. `DocumentService` được Controller khác gọi qua Spring proxy để interceptor method security áp dụng. Không chuyển điều kiện này thành chỉ một kiểm tra ở UI hoặc tin vào client gửi “owner=true”.

`src/main/java/example/boundary/ApiController.java`:

```java
package example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final DocumentService documents;

    public ApiController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/docs/{id}")
    public String readDocument(@PathVariable Long id) {
        return documents.read(id);
    }

    @GetMapping("/api/admin/stats")
    public String stats() {
        return "stats";
    }
}
```

### 6.2. Kiểm thử tự động đúng ranh giới

`src/test/java/example/boundary/SecurityBoundaryTest.java`:

```java
package example.boundary;

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
class SecurityBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void documentRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/docs/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/1").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc-1"));
    }

    @Test
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/docs/2").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/2").with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc-2"));
    }

    @Test
    void aliceCannotReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("stats"));
    }

    @Test
    void adminStillCannotReadSomeoneElsesDocument() throws Exception {
        mvc.perform(get("/api/docs/1").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
java -version
mvn test
mvn spring-boot:run
```

Với đúng mã và dependencies nêu trên, **kết quả mong đợi** của `mvn test` là **8 test qua**. Đây là expected outcome của ví dụ, không phải log build đã được chạy ở môi trường này.

Chạy ứng dụng rồi gửi request trong terminal khác:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/docs/1
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/docs/1
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/docs/2
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/api/admin/stats
```

Kết quả dự kiến khi server dùng cổng mặc định 8080:

```text
200
401
200
403
200
```

Trên Windows PowerShell, dùng `curl.exe` và thay `/dev/null` bằng `NUL`. Các lệnh chỉ minh họa GET nên CSRF mặc định không cản chúng. Với POST/PUT/DELETE, cần xét CSRF token trong trường hợp session/cookie có thể được trình duyệt tự gửi.

### 6.3. Rút ra bài học từ ví dụ

| Điều quan sát | Ai chịu trách nhiệm? | Bằng chứng kiểm thử |
| --- | --- | --- |
| Anonymous vào public endpoint được | Framework thực thi `permitAll` theo cấu hình phiên bản | `healthIsPublic`: 200 |
| Anonymous bị chặn ở API riêng | Framework xử lý xác thực và entry point | `documentRequiresAuthentication`: 401 |
| User role thấp không vào admin | Framework so authority `ROLE_ADMIN` | `aliceCannotReadAdminStats`: 403 |
| Alice đọc tài liệu của Alice | Policy của ứng dụng và method security phối hợp | `aliceCanReadOwnDocument`: 200 |
| Alice không đọc tài liệu của Bob | **Ứng dụng** định nghĩa ownership; framework chặn khi policy trả false | `aliceCannotReadBobsDocument`: 403 |
| Admin không mặc nhiên bỏ qua owner | Quy tắc sản phẩm quyết định, không suy ra từ tên role | `adminStillCannotReadSomeoneElsesDocument`: 403 |

Nếu sau này nghiệp vụ cho phép ADMIN xem tài liệu bất kỳ, thay đổi đúng nơi là **policy** (và thêm test), không thay `authenticated()` thành `permitAll()` hoặc tự viết một filter xác thực mới.

## 7. Phân loại ở cấp dự án bằng năm câu hỏi

Giả sử yêu cầu là: **“Chỉ người dùng thuộc cùng tổ chức mới tải được hợp đồng, trừ nhân viên kiểm toán nội bộ có quyền đặc biệt.”**

**Câu 1 — Ai là principal và bằng chứng xác thực đến từ đâu?** Session, OAuth2 login, bearer JWT hay mTLS? Framework có module tích hợp nào? Nếu dùng IdP, ai vận hành và quản lý danh tính? Đây là **A + lựa chọn integration**.

**Câu 2 — Hệ đang chạy bộ phiên bản nào?** Spring Boot/Security/Java, Servlet hay Reactive, module nào đã thêm, API nào còn hỗ trợ? Đây là **B**. Ghi câu trả lời bằng `dependency:tree` hoặc `dependencies`, không viết “bản mới nhất” vào thiết kế mà không xác định version.

**Câu 3 — Chính sách phụ thuộc dữ liệu nào?** Bảng `contract`, `tenant_id`, quan hệ `membership`, role kiểm toán, trạng thái hợp đồng, thời hạn truy cập. Đây là **C**; Spring Security không biết dữ liệu của sản phẩm.

**Câu 4 — Điểm thực thi ở đâu?** HTTP matcher để bắt buộc login, method security để chặn thao tác dịch vụ, repository query gắn tenant để tránh rò rỉ dữ liệu; với download cần kiểm tra quyền **trước khi** phát sinh presigned URL, stream hoặc cache. Đây là **A + C**, với cú pháp theo **B**.

**Câu 5 — Bằng chứng nào đủ chấp nhận?** Test anonymous, người cùng tenant, người khác tenant, kiểm toán viên, revoked membership, URL bị đổi ID, batch download và background job. Cần cả test **cho phép** và test **từ chối**; chạy lại khi nâng version hoặc sửa policy.

### Kỹ thuật ghi quyết định trong tài liệu thiết kế

Với mỗi năng lực, ghi rõ:

```text
Yêu cầu: xem hợp đồng
Năng lực framework: HTTP authentication + method authorization
Phiên bản/stack: Spring Boot 3.3.x, Spring Security 6.3.x, Servlet
Nguồn identity: IdP hoặc local UserDetailsService đã chọn
Quyền nghiệp vụ: cùng tenant và membership còn hiệu lực,
                 hoặc role kiểm toán đã được phê duyệt
Nguồn dữ liệu policy: database ứng dụng (contract, membership, tenant)
Điểm thực thi: Service trước khi truy xuất/trả file
Bằng chứng: test 401, 403, 200 và test truy cập chéo tenant
Owner vận hành: nhóm chịu trách nhiệm Identity + nhóm sở hữu Contract
```

Các giá trị phiên bản/nguồn identity trong ví dụ khung này chỉ là **mẫu điền**, cần thay bằng sự thật của dự án đang làm. Nếu một dòng chưa được xác định, đó là quyết định còn thiếu cần làm rõ trong thiết kế; đừng mặc định framework tự đáp ứng.

## 8. Ranh giới nâng cấp: giữ nguyên nguyên tắc, kiểm lại hành vi

Trước khi nâng Spring Security, chia backlog thành hai phần:

**Phần không đổi về ý định nghiệp vụ:**

- API quản trị chỉ cho role ADMIN.
- Người dùng chỉ xem bản ghi được quyền xem.
- API chưa đăng nhập không được trả dữ liệu riêng.
- Tài khoản bị thu hồi quyền không được tiếp tục thao tác theo chính sách đã công bố.

**Phần phải kiểm thử vì version có thể làm thay đổi cách thực thi:**

- Matcher có còn nhận dạng đúng URL, path encoding, servlet prefix và HTTP method?
- DSL và extension API có còn compile, custom filter còn nằm đúng thứ tự?
- Authentication exception chuyển thành 401, 403 hay redirect đúng như client mong đợi?
- Session, CSRF, cookies, CORS và logout có giữ semantics cần thiết?
- JWT validation, claim/authority mapping, OIDC redirect URI và cấu hình provider có còn tương thích?
- Test method security có chạy qua proxy và tất cả luồng gọi service hay không?

### Ba tình huống migration thường làm lộ lỗ hổng

1. **Chuyển `antMatchers` sang `requestMatchers` mà không xem wildcard.** Một pattern cũ có thể không có cùng ngữ nghĩa trong PathPattern; request lọt khỏi rule hoặc bị block ngoài ý muốn.
2. **Đổi `web.ignoring` sang `permitAll` hoặc ngược lại chỉ để hết 403.** `web.ignoring` loại request khỏi Spring Security filter chain; `permitAll` vẫn giữ filter bảo vệ. Phải đánh giá hiệu ứng với security headers, authentication, CSRF và monitoring.
3. **Thêm multi-chain nhưng quên fallback.** `securityMatcher("/api/**")` chỉ chọn một chain cho API. Các URL bên ngoài mẫu đó có thể không còn chain bảo vệ nếu không có cấu hình khác.

Đối với nâng 6.x lên 7.x, đối chiếu chính xác migration guide về Lambda DSL, `PathPatternRequestMatcher`, API extension và các thay đổi mặc định; đừng viết một script thay thế tên method hàng loạt rồi coi là hoàn tất.

## 9. Những điểm hay bị gán sai trách nhiệm

1. **PasswordEncoder vs password policy:** BCrypt/Argon2 và việc so mật khẩu là năng lực kỹ thuật. Chính sách độ dài, mật khẩu bị lộ, reset, thông báo và vòng đời account thuộc sản phẩm/IdP.
2. **JWT validation vs quyền dữ liệu:** chữ ký và thời hạn token hợp lệ không có nghĩa principal có quyền trên tài liệu `id=99`. Cần xác minh audience, issuer và policy theo dữ liệu thực.
3. **Role vs tenant:** `ROLE_ADMIN` có thể là quản trị của một tenant, không phải admin toàn hệ thống. Cần biểu diễn scope của role và chặn truy cập chéo tenant tại backend.
4. **CORS vs authorization:** cho phép origin chỉ kiểm soát hành vi trình duyệt theo CORS; không phải bằng chứng người gọi được phép xem dữ liệu.
5. **CSRF vs authentication:** login thành công không làm POST tự hợp lệ khi CSRF bảo vệ đang bật; và tắt CSRF không biến API thành an toàn.
6. **Logging vs audit trail:** log exception hoặc access denied của framework không tự đáp ứng yêu cầu lưu nhật ký thay đổi quyền, truy xuất dữ liệu nhạy cảm hoặc retention.
7. **MFA feature vs MFA program:** một bước xác thực mạnh chỉ là một phần của onboarding, recovery, enrollment, hỗ trợ người dùng và phản ứng sự cố.
8. **Bảo vệ controller vs bảo vệ service:** nếu service được gọi từ batch, queue hoặc job, kiểm tra HTTP tại controller không bảo vệ tất cả entry point. Có thể cần kiểm soát ở tầng dịch vụ và các adapter tương ứng.
9. **Framework feature vs Spring Boot auto-configuration:** thêm dependency có thể kích hoạt hành vi mặc định, nhưng khi khai báo bean bảo mật riêng, ứng dụng cần định nghĩa rõ các rule và kiểm tra kết quả; không suy ra cấu hình auto còn nguyên.
10. **“Ổn định” vs “không cần cập nhật”:** nguyên lý Authentication/Authorization có thể ổn định, nhưng một dependency cũ không có bản vá vẫn có rủi ro. Cần tiếp tục theo dõi security advisories và release support.

## 10. Checklist áp dụng trước khi đóng một yêu cầu bảo mật

- [ ] Có định nghĩa **đầu vào, principal, tài nguyên, hành động, kết quả cho phép/từ chối**.
- [ ] Xác định chính xác phiên bản Spring Boot, Spring Security, Java, Servlet/Reactive và các dependency liên quan.
- [ ] Chỉ ra năng lực nào do framework có sẵn, năng lực nào phải tích hợp IdP/gateway và phần nghiệp vụ nào phải xây dựng.
- [ ] Không nhầm Resource Server với Authorization Server; không nhầm authentication với authorization.
- [ ] Policy owner/tenant/role/scope được kiểm tra **server-side** bằng dữ liệu đáng tin.
- [ ] Có cấu hình filter chain phù hợp, fallback, thứ tự matcher và chính sách default deny khi cần.
- [ ] Đánh giá CSRF/session/CORS/HTTPS theo cách ứng dụng thực sự dùng credentials.
- [ ] Có test 200/401/403, truy cập chéo tài nguyên và các case biên.
- [ ] Có kế hoạch test lại khi nâng phiên bản, đặc biệt matchers, custom extensions và flow đăng nhập.
- [ ] Có ghi rõ owner của dữ liệu identity, policy, key/token, audit và vận hành bảo mật.

## 11. Tài liệu chính thức để tự đối chiếu

- Spring Security — *Servlet Architecture*: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — *Servlet Authentication Architecture*: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 — *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — *OAuth2 roles: Resource Server, Client, Authorization Server*: https://docs.spring.io/spring-security/reference/servlet/oauth2/
- Spring Security — *OAuth2 Login*: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security — *CSRF*: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — *MockMvc testing*: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security 6.5 — *Migration to 7, Configuration*: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security 6.5 — *Migration to 7, Web*: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security — *Migration index*: https://docs.spring.io/spring-security/reference/migration/

**Kết quả học tập cần đạt:** với một yêu cầu bảo mật cụ thể, có thể trình bày rõ **framework thực thi cơ chế gì**, **cú pháp/hành vi phải khóa theo release nào** và **chính sách/dữ liệu nào cần đội sản phẩm tự quyết định**; sau đó chứng minh thiết kế bằng kiểm thử cho cả đường đi được phép lẫn đường đi bị chặn.
