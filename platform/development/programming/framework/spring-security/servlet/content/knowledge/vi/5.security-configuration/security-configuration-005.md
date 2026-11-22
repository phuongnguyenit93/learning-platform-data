# Tách cấu hình cho giao diện web, REST API và khu vực quản trị

> **Chủ đề:** Spring Security trong ứng dụng **Servlet**, với Java 17+ và cấu hình Java của Spring Security 6. Bài sử dụng Spring Boot 3 để minh họa ứng dụng chạy được; nguyên tắc phân tách các `SecurityFilterChain` vẫn áp dụng trong dự án Servlet tự khởi tạo Spring Security không dùng Boot.

## 1. Bài toán: ba vùng HTTP có nhu cầu bảo mật khác nhau

Một ứng dụng thường có đồng thời:

- **Giao diện web** như `/home`, `/dashboard` và `/login`: người dùng tương tác bằng browser, đăng nhập qua HTML form, giữ `SecurityContext` trong HTTP session và cần CSRF protection cho các thao tác thay đổi trạng thái.
- **REST API** như `/api/public`, `/api/orders`: client có thể là ứng dụng di động, backend khác hoặc CLI, thường tự gửi `Authorization` trong từng request; API cần trả **401/403** thay vì redirect đến trang HTML. API dùng token thường được thiết kế stateless.
- **Khu vực quản trị** như `/admin/reports`: chỉ tài khoản có quyền quản trị được vào, kể cả khi người dùng bình thường đã đăng nhập hợp lệ. Tùy rủi ro, có thể cần MFA, xác thực lại, audit hoặc session policy nghiêm ngặt hơn.

Nếu dùng cùng một policy cho mọi URL, lỗi dễ gặp là API chuyển hướng đến `/login`, route admin bị mở bởi `authenticated()`, hoặc CSRF của cả website bị tắt để một REST client gửi được POST.

Spring Security Servlet giải quyết bằng **nhiều `SecurityFilterChain`**, mỗi chain xác định phạm vi request và bộ filter, cơ chế xác thực, phân quyền, session/CSRF/entry point thích hợp.

```text
HTTP Request
    |
    v
Servlet container -> DelegatingFilterProxy -> FilterChainProxy
                                               |
                              Thử lần lượt các SecurityFilterChain
                                               |
                        +----------------------+--------------------+
                        |                      |                    |
                   /admin/**                /api/**           Còn lại (/login,
                        |                      |                /dashboard...)
                   ADMIN chain              API chain             WEB chain
                   role ADMIN               HTTP Basic demo       form login
                   dùng session             stateless             dùng session
                   redirect /login          401 / 403             redirect /login
                        |                      |                    |
                        +----------------------+--------------------+
                                               |
                                         Controller
```

**Một request được `FilterChainProxy` đưa vào chain đầu tiên có matcher phù hợp**. Nó không chạy qua cả ba chain rồi cộng dồn các rule. Nếu không chain nào match, request có nguy cơ không đi qua các security filter cần thiết. Vì thế ví dụ sẽ có WEB chain cuối làm **fallback**.

## 2. Hiểu đúng `securityMatcher`, `requestMatchers` và `@Order`

| Thành phần | Trả lời câu hỏi | Tác dụng |
| --- | --- | --- |
| `@Order(1)` trên bean `SecurityFilterChain` | Chain nào được xem trước? | Chọn độ ưu tiên giữa các chain |
| `http.securityMatcher("/api/**")` | Request có thuộc **chain API** không? | Giới hạn phạm vi nguyên chain, gồm cả authentication và authorization filters |
| `authorizeHttpRequests(...).requestMatchers("/api/orders")` | Request đã vào chain có được phép không? | Chọn luật phân quyền bên trong chain |
| `anyRequest()` trong một chain | Các URL còn lại thuộc chain xử lý thế nào? | Luật fallback bên trong chain đã chọn |
| Chain không đặt `securityMatcher` riêng | Những URL chưa match chain trước đi đâu? | Trở thành fallback bao phủ mọi request còn lại |

Các chain có matcher **chồng lấn** không tạo thành nhiều lớp bảo vệ liên tiếp. Ví dụ nếu chain WEB không giới hạn URL được đặt `@Order(1)`, nó có thể match `/api/**` và `/admin/**` trước, khiến API/ADMIN chain không được chọn.

Hai nguyên tắc quan trọng: **chain cụ thể đặt trước, chain tổng quát đặt sau**; bên trong `authorizeHttpRequests`, matcher cụ thể đặt trước `anyRequest()` cuối cùng.

Với khu vực quản trị, cần tính cả `/admin` lẫn `/admin/**`. Với API, hãy xem có endpoint gốc `/api` hay chỉ các URL dưới `/api/`; đừng giả định mọi pattern đều bao phủ mọi biến thể đường dẫn. Nếu dùng `contextPath` hoặc `servletPath` đặc biệt, kiểm tra cách matcher của phiên bản Spring Security được cấu hình diễn giải path.

## 3. Thiết kế policy trước khi viết code

Ta sẽ dùng ba tài khoản minh họa, cùng một `UserDetailsService`:

| Username | Authorities | Mục đích |
| --- | --- | --- |
| `guest` | `ROLE_USER` | Đăng nhập được vào dashboard, không được đọc orders hay vào admin |
| `alice` | `ROLE_USER`, `orders:read` | Xem dashboard và gọi API orders |
| `boss` | `ROLE_ADMIN`, `orders:read` | Đọc orders và vào khu quản trị |

Các endpoint:

| URL | Chain | Authorization | Chưa đăng nhập |
| --- | --- | --- | --- |
| `GET /home` | WEB | `permitAll()` | HTTP 200 |
| `GET /dashboard` | WEB | `authenticated()` | HTTP 302 → `/login` |
| `GET /login`, `POST /login` | WEB | Form login | Hiển thị/nhận form |
| `GET /api/public` | API | `permitAll()` | HTTP 200 |
| `GET /api/orders` | API | `hasAuthority("orders:read")` | HTTP 401 |
| `GET /admin/reports` | ADMIN | `hasRole("ADMIN")` | HTTP 302 → `/login` |
| URL khác dưới `/api/**` | API | `denyAll()` | Bị từ chối |
| URL khác dưới `/admin/**` | ADMIN | `hasRole("ADMIN")` | Theo login và quyền |

`ROLE_ADMIN` là authority Spring Security dùng theo convention khi kiểm tra `hasRole("ADMIN")`. `orders:read` là authority nghiệp vụ do ứng dụng định nghĩa. **Có role ADMIN không mặc nhiên có mọi permission**; trong bài `boss` được cấp cả hai authority.

WEB và ADMIN có thể **dùng chung login form và HTTP session**, sau đó ADMIN kiểm tra role thêm lần nữa. API dùng cơ chế xác thực trên từng request và không sử dụng phiên đăng nhập web.

## 4. Ví dụ chạy với Spring Boot 3, Java 17+

Tạo Maven project với **Spring Boot 3.3.5** (phiên bản ổn định đã phát hành dùng để minh họa), Java 17+, dependencies `spring-boot-starter-web` và `spring-boot-starter-security`. Không cần cơ sở dữ liệu trong bài: các tài khoản nằm trong `InMemoryUserDetailsManager`.

```text
segmented-security/
├── pom.xml
└── src/main/java/demo/segments/
    ├── SegmentedSecurityApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>segmented-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 4.2. `SegmentedSecurityApplication.java`

```java
package demo.segments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SegmentedSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SegmentedSecurityApplication.class, args);
    }
}
```

### 4.3. `SecurityConfig.java`: ba chain rõ phạm vi

```java
package demo.segments;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        // ADMIN: bao phủ cả /admin và /admin/**.
        http.securityMatcher("/admin", "/admin/**");
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
        );
        // /login được xử lý bởi WEB chain; dùng phiên web đã đăng nhập.
        http.exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                        new LoginUrlAuthenticationEntryPoint("/login")
                )
        );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("orders:read")
                .anyRequest().denyAll()
        );
        // HTTP Basic phục vụ ví dụ CLI; API không dùng session để xác thực.
        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );
        // Giữ CSRF mặc định; các request API trong ví dụ đều dùng GET.
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        // Không thu hẹp securityMatcher: chain cuối bao phủ URL còn lại.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/home", "/error").permitAll()
                .anyRequest().authenticated()
        );
        http.formLogin(form -> form.permitAll());
        http.logout(logout -> logout.permitAll());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails guest = User.withUsername("guest")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER")
                .build();

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER", "orders:read")
                .build();

        UserDetails boss = User.withUsername("boss")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "orders:read")
                .build();

        return new InMemoryUserDetailsManager(guest, alice, boss);
    }
}
```

Cấu hình trên có các đặc điểm cần hiểu rõ:

1. **ADMIN `@Order(1)`** là chain ưu tiên cao nhất, chỉ match URL admin. `hasRole("ADMIN")` tương đương kiểm tra `ROLE_ADMIN` theo tiền tố mặc định. Đăng nhập không tự động cho phép truy cập admin nếu thiếu role.
2. **ADMIN dùng trang login thuộc WEB chain**: `LoginUrlAuthenticationEntryPoint("/login")` redirect khách chưa xác thực đến `/login`; URL này không khớp `/admin/**`, nên WEB chain hiển thị form và nhận POST `/login`. Sau khi xác thực qua WEB, session có thể mang authentication sang ADMIN. ADMIN vẫn quyết định quyền độc lập.
3. **API `@Order(2)`** nhận `/api/**`, dùng `httpBasic()` và `SessionCreationPolicy.STATELESS`. HTTP Basic ở đây là cách thử đơn giản bằng `curl`; triển khai API thực tế thường dùng Bearer token/JWT và kiểm chứng mỗi request.
4. **WEB `@Order(3)`** không gọi `securityMatcher`, do đó là fallback cho `/login`, `/dashboard` và các đường dẫn khác. `formLogin()` cung cấp trang đăng nhập mặc định; `logout()` xử lý đăng xuất cùng các yêu cầu CSRF phù hợp.
5. **`UserDetailsService` chung** cung cấp tài khoản cho các provider xác thực, nhưng không ép từng chain dùng chung cách lấy credentials. Ở ADMIN/WEB, authentication được lưu/đọc qua cơ chế session; API được cấu hình không dùng session để xác thực.
6. **CSRF của WEB/ADMIN được giữ**. Ví dụ API chỉ dùng GET nên chưa cần quyết định xử lý CSRF cho method thay đổi trạng thái. Không tắt CSRF toàn ứng dụng chỉ vì muốn gọi REST POST.

`SessionCreationPolicy.STATELESS` có nghĩa Spring Security không tạo/dùng HTTP session để lưu hoặc lấy `SecurityContext` cho API chain; nó không có nghĩa mọi thành phần trong ứng dụng bị cấm tuyệt đối tạo một HTTP session.

### 4.4. `DemoController.java`

```java
package demo.segments;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/home")
    public String home() {
        return "home:public";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard:" + authentication.getName();
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api:public";
    }

    @GetMapping("/api/orders")
    public String apiOrders(Authentication authentication) {
        return "orders:" + authentication.getName();
    }

    @GetMapping("/admin/reports")
    public String adminReports(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

Đây là `@RestController` trả văn bản thay cho giao diện HTML, giúp kiểm tra các chain bằng HTTP. Spring Security tự cung cấp login page mặc định `GET /login`; sau khi login, browser có thể dùng session khi gọi `/dashboard` hoặc `/admin/reports`. Đối với UI thật, có thể thay controller bằng trang MVC, template engine hoặc frontend tương ứng.

## 5. Chạy và xác minh behavior

Từ thư mục có `pom.xml`, chạy:

```bash
mvn spring-boot:run
```

Trên shell hỗ trợ `curl`, chạy các request. Output phía dưới là **kỳ vọng** với cấu hình mẫu nếu ứng dụng được khởi động trên cổng 8080 mặc định.

```bash
curl -s http://localhost:8080/home
# home:public

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/dashboard
# 302

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/admin/reports
# 302

curl -s http://localhost:8080/api/public
# api:public

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/orders
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u guest:demo123 http://localhost:8080/api/orders
# 403

curl -s -u alice:demo123 http://localhost:8080/api/orders
# orders:alice

curl -s -u boss:demo123 http://localhost:8080/api/orders
# orders:boss
```

**WEB/ADMIN kiểm tra bằng browser:** mở `http://localhost:8080/admin/reports`. Khi chưa đăng nhập, browser được chuyển đến `/login`. Đăng nhập với `guest/demo123` rồi trở lại `/admin/reports` sẽ bị từ chối (403) vì thiếu `ROLE_ADMIN`. Đăng xuất đúng flow rồi đăng nhập bằng `boss/demo123`, endpoint sẽ trả `admin:boss`. Login với `alice/demo123` cho phép vào `/dashboard`, nhưng không được vào admin.

Không dùng riêng `curl -u boss:demo123` để kiểm chứng login của ADMIN: trong cấu hình này **chỉ API chain có HTTP Basic**; WEB/ADMIN dùng form/session. Với `POST /login`, browser đưa kèm CSRF token và cookie; tự gửi POST bằng `curl` không có token có thể bị 403.

### 5.1. HTTP 302 khác 401 và 403

| Mã | Trường hợp | Ý nghĩa |
| --- | --- | --- |
| **302** | Khách truy cập `/dashboard` hoặc `/admin/reports` | Luồng browser được redirect đến trang đăng nhập |
| **401** | `/api/orders` không có credentials hợp lệ | API challenge xác thực, không chuyển sang form |
| **403** | `guest` có credentials hợp lệ nhưng thiếu `orders:read`; user thường vào admin | Authentication có thể đã có, authorization không cho phép; 403 cũng có thể do CSRF trên request thay đổi trạng thái |

Nếu API bất ngờ redirect đến `/login`, hãy kiểm tra `@Order`, `securityMatcher("/api/**")` và loại authentication entry point thực sự được chọn. Nếu người dùng thường vào được admin, cần kiểm tra request có vào ADMIN chain hay không trước khi sửa role.

## 6. Phân tách session, entry point và CSRF

### WEB: form login và session

Khi `POST /login` thành công, Spring Security tạo hoặc cập nhật `Authentication` trong `SecurityContext`; cơ chế của WEB chain lưu context vào session để browser có thể dùng lại trong request sau. Browser gửi cookie phiên đến `/dashboard` và `/admin/reports`. Spring Security còn có những cơ chế bảo vệ session như session fixation protection theo cấu hình; production cần thiết lập HTTPS, `Secure`/`HttpOnly`/`SameSite`, timeout và chính sách đăng xuất.

### ADMIN: cùng phiên, quyền chặt hơn

ADMIN và WEB có thể nhận cùng authentication từ session nhưng ADMIN vẫn cần `ROLE_ADMIN`. Chain riêng giúp thêm những quy tắc riêng ở vùng admin. Tuy nhiên **tách chain không tự bật MFA, xác thực lại hoặc session timeout riêng**. Những yêu cầu này cần thiết kế và tích hợp thêm (chẳng hạn xác thực đa yếu tố, step-up authentication, logging/audit và ràng buộc session).

### API: authentication theo mỗi request

API `STATELESS` tránh phụ thuộc vào session web khi kiểm tra một request API. Ở ví dụ, Basic credentials có thể được xác thực theo mỗi request. Đây là phương án học tập và phải dùng HTTPS. API production thường dùng OAuth2 Resource Server với Bearer JWT hoặc opaque token.

**CSRF không chỉ phụ thuộc có session hay không.** Browser có thể tự gửi cookie và đôi khi cả credentials HTTP Basic; vì vậy không thể suy ra “REST API = tắt CSRF an toàn”. Nếu chỉ các client chủ động gửi Bearer token trong header và server không chấp nhận credentials browser tự gửi, có thể cấu hình CSRF riêng cho API chain theo kiến trúc đó. WEB/ADMIN dùng cookie thì cần bảo vệ thao tác state-changing.

Một fragment **thay thế**, khi API chuyển hẳn sang Bearer JWT, là:

```java
// Fragment trong apiChain(), thay httpBasic() hiện có.
// Chỉ phù hợp khi API không nhận cookie hoặc credentials tự gửi từ browser.
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
);
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
http.csrf(csrf -> csrf.disable());
```

Đoạn này **không chạy độc lập**: cần `spring-boot-starter-oauth2-resource-server`, cấu hình trusted issuer/JWK hoặc `JwtDecoder` và token hợp lệ. Scope JWT theo mặc định thường được chuyển thành authority `SCOPE_<scope>`; nếu giữ rule `hasAuthority("orders:read")`, cần bảo đảm converter/token cung cấp đúng authority hoặc đổi rule phù hợp. Không coi role/permission trong payload client chưa xác thực là quyền tin cậy.

## 7. Phân quyền URL khác với phân quyền method

`authorizeHttpRequests` bảo vệ URL ở filter chain trước khi controller chạy. Khi nghiệp vụ cũng được gọi qua job hoặc service khác, có thể cân nhắc method security (`@EnableMethodSecurity` và `@PreAuthorize`), nhưng cần biết cơ chế Spring AOP/proxy và các hạn chế như self-invocation.

```java
// Fragment trong class @Configuration:
@EnableMethodSecurity

// Fragment trên method của Spring-managed bean:
@PreAuthorize("hasAuthority('orders:read')")
public OrderSummary readOrders() {
    // logic nghiệp vụ
}
```

Đây là **hai fragment ở vị trí khác nhau**, không phải một class Java hoàn chỉnh; `OrderSummary` chỉ là kiểu minh họa. Không nên nghĩ rằng tách SecurityFilterChain đã thay thế được chính sách ở tầng service khi nghiệp vụ cần bảo vệ độc lập với HTTP URL.

## 8. Khi nào nhiều chain là cần thiết?

**Nên dùng nhiều chain** khi nhóm URL khác nhau đáng kể về authentication mechanism, entry point (HTML redirect so với HTTP 401), session policy, CSRF hoặc custom security filters.

**Một chain có thể đủ** khi tất cả URL dùng chung một form login/session/các filter và chỉ khác role/permission. Khi đó viết nhiều `requestMatchers` trong cùng một `authorizeHttpRequests` thường dễ hiểu hơn:

```java
// Fragment thay thế minh họa một chain duy nhất, không ghép vào cấu hình mục 4.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/reports/**").hasAuthority("reports:read")
        .anyRequest().authenticated()
);
http.formLogin(Customizer.withDefaults());
```

Không nên tạo một `SecurityFilterChain` cho mỗi endpoint chỉ vì mỗi endpoint đòi role khác nhau. Độ phức tạp của nhiều chain nằm ở matcher, thứ tự, filter shared/state và cách bảo đảm URL không lọt khỏi policy.

## 9. Lỗi thường gặp và quy trình chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| API redirect HTML login thay vì 401 | WEB chain match trước API hoặc sai entry point | Kiểm tra `@Order`, `securityMatcher`, cơ chế Basic/Bearer |
| User thường vào được admin | ADMIN chain không được chọn hoặc thiếu `hasRole("ADMIN")` | Đọc URL thực, matcher, rule và authority hiện có |
| POST API trả 403 | CSRF đang bật hoặc authorization từ chối | Xem filter gây từ chối; chọn CSRF theo credentials và client |
| POST `/login` bị 403 | Thiếu CSRF token/cookie khi tự gửi request | Dùng browser flow hoặc test gửi token đúng |
| API request dùng được cookie WEB không có Authorization | API vẫn đọc session hoặc URL bị match sai chain | Kiểm tra `STATELESS`, chain order và security context repository |
| `ROLE_USER` không qua `hasRole("ADMIN")` | Đây là từ chối có chủ ý | Kiểm tra ánh xạ role, không thêm bypass |
| Có `ADMIN` nhưng `hasRole("ADMIN")` báo 403 | Authority mặc định phải là `ROLE_ADMIN` | Cấp role/authority thống nhất hoặc cấu hình tiền tố |
| URL nhạy cảm không được Spring Security bảo vệ | Không security chain nào match, thiếu fallback | Bổ sung fallback; test mọi path kể cả `/admin` gốc |
| Form admin redirect đến `/login` nhưng trang không hiện | `/login` bị bắt bởi chain khác hoặc web chain không có form login | Giữ `/login` và POST `/login` trong WEB chain |
| Custom filter chạy hai lần | Đăng ký trùng ở Servlet container và Spring Security chain | Xác minh vị trí đăng ký filter và quy trình khởi tạo |

Khi debug, theo thứ tự: **(1) URL thực và servlet path → (2) security chain được chọn → (3) authentication/session/token → (4) authorities → (5) rule và CSRF → (6) HTTP entry point/response**.

Trong môi trường development có thể dùng:

```properties
logging.level.org.springframework.security=DEBUG
```

Đây là fragment cấu hình `application.properties` để quan sát log của Spring Security, không phải chương trình Java. Không ghi password, Bearer token hoặc session cookie vào log, đặc biệt ở production.

## 10. Tự kiểm tra kiến thức

1. **Vì sao `@Order(3)` của WEB là fallback?** Vì WEB chain không thu hẹp `securityMatcher`, nên có thể match các URL còn lại sau ADMIN/API.
2. **`http.securityMatcher("/api/**")` và `requestMatchers("/api/orders")` có giống nhau?** Không: cái đầu chọn *chain*, cái sau chọn *quy tắc* trong chain.
3. **`guest` gọi API orders bằng Basic credentials hợp lệ nhận gì?** 403 do thiếu `orders:read`.
4. **`boss` gửi Basic tới `/admin/reports` có được nhận tự động không?** Không trong ví dụ: ADMIN không bật HTTP Basic, mà dùng redirect tới form login của WEB.
5. **`guest` login qua WEB rồi vào ADMIN được không?** Không, session chỉ xác nhận danh tính; ADMIN vẫn cần `ROLE_ADMIN`.
6. **Tắt CSRF ở WEB để API POST hoạt động có đúng?** Không. Xử lý CSRF theo nhóm client, loại credentials và chain liên quan.
7. **Thêm `GET /api/unknown` nhưng chưa khai báo thì sao?** API chain được chọn, `denyAll()` từ chối.
8. **Vì sao role ADMIN chưa chắc đọc được orders?** Role và permission là các authority riêng; ví dụ cấp `orders:read` tường minh.

## 11. Checklist trước khi triển khai

- [ ] Lập bản đồ prefix và endpoint thực tế, gồm login/logout, error, static resources, context path và root path.
- [ ] Đặt chain cụ thể trước chain fallback, kiểm tra overlap và route chưa khớp.
- [ ] Xác định cơ chế xác thực, entry point và session policy riêng cho browser, API và admin.
- [ ] Kiểm tra quyền bằng chính authorities thực tế, kể cả user đã đăng nhập nhưng thiếu permission.
- [ ] Giữ CSRF cho giao diện dùng cookie; đánh giá CSRF cho API dựa trên cách client gửi credentials.
- [ ] Đảm bảo login page và login processing URL thực sự thuộc chain có form login.
- [ ] Thêm test cho 200/302/401/403 và cả route `/admin`, `/api` nếu ứng dụng có xử lý hai đường dẫn này.
- [ ] Với admin nhạy cảm, triển khai thêm MFA, re-authentication, logging và kiểm soát phiên theo nhu cầu thực tế.
- [ ] Kiểm tra lần nữa khi dùng reverse proxy, path rewriting, CORS hoặc custom filter.

**Ghi nhớ:** `@Order` quyết định **thứ tự thử chain**; `securityMatcher` xác định **chain nào nhận request**; `requestMatchers` xác định **quy tắc quyền trong chain**. Phân tách ba mức này là nền tảng để ứng dụng Servlet bảo vệ đúng giao diện web, REST API và khu vực quản trị.