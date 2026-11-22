# Luồng chuyển hướng từ tài nguyên được bảo vệ đến trang đăng nhập trong Spring Security Servlet

> **Phạm vi:** Spring Security trên Servlet stack, Java 17+, Spring Framework 6 / Spring Security 6. Bài tập trung vào cơ chế **người dùng chưa đăng nhập yêu cầu một URL được bảo vệ → chuyển hướng tới trang đăng nhập → xác thực → quay lại tài nguyên ban đầu**. Ví dụ chạy với Spring Boot 3.3.x để giảm phần khởi tạo máy chủ; luồng filter, request cache và form login vẫn là cơ chế Spring Security Servlet.

## 1. Bài toán: người dùng mở URL cần đăng nhập

Giả sử người dùng chưa có phiên đăng nhập, truy cập trực tiếp:

```text
GET http://localhost:8080/reports?period=2026-11
```

Ứng dụng quy định `/reports` chỉ người đã xác thực mới được đọc. Một trải nghiệm thường mong đợi:

1. Browser yêu cầu `/reports?period=2026-11`.
2. Spring Security nhận ra request **chưa có người dùng được xác thực** và chưa cho controller xử lý.
3. Trước khi đưa browser tới trang login, hệ thống **lưu thông tin request gốc** bằng request cache.
4. Server trả phản hồi chuyển hướng (thường HTTP **302**, header `Location` trỏ tới `/login`).
5. Browser hiển thị form đăng nhập; người dùng nhập username/password, gửi `POST /login` kèm CSRF token.
6. Xác thực thành công, Spring Security lưu `SecurityContext` theo chính sách session và success handler quyết định đích chuyển hướng.
7. Nếu có saved request hợp lệ, browser được chuyển về `/reports?period=2026-11`.
8. Browser gửi **một GET mới** đến URL này, kèm cookie phiên. Spring Security cho phép truy cập sau khi kiểm tra quyền; controller cuối cùng chạy.

**302 không có nghĩa đã đăng nhập.** Chuyển hướng tới `/login` là lời mời xác thực, không phải thao tác xác thực. Và chuyển hướng trở lại URL gốc sau login **không miễn bước phân quyền**: user hợp lệ nhưng thiếu role cần thiết vẫn có thể nhận **403** ở tài nguyên gốc.

Đây là luồng đặc trưng cho **trình duyệt dùng form login và HTTP session**. REST API thường cần 401/403 thay vì redirect sang một trang HTML; không nên đánh đồng hai kiểu client.

## 2. Sơ đồ request và các thành phần tham gia

```text
Browser                          Spring Security Servlet filters
   |                                      |
   | GET /reports?period=2026-11          |
   |------------------------------------->|
   |                                      | AuthorizationFilter kiểm tra rule
   |                                      | -> chưa được xác thực
   |                                      v
   |                              ExceptionTranslationFilter
   |                                      |
   |                                      +-- RequestCache.saveRequest(...)
   |                                      |   (ví dụ HttpSessionRequestCache)
   |                                      |
   |                                      +-- AuthenticationEntryPoint.commence(...)
   |                                      |   (LoginUrlAuthenticationEntryPoint)
   | <------------------------------------|
   | 302 Location: /login                 |
   |                                      |
   | GET /login                           |
   |------------------------------------->| DefaultLoginPageGeneratingFilter
   | <------------------------------------| hoặc custom login controller/view
   | 200 HTML form + CSRF token           |
   |                                      |
   | POST /login (credentials + _csrf)    |
   |------------------------------------->| UsernamePasswordAuthenticationFilter
   |                                      | -> AuthenticationManager
   |                                      | -> AuthenticationProvider
   |                                      | -> SecurityContext/session
   |                                      | -> SavedRequestAwareAuthenticationSuccessHandler
   | <------------------------------------|
   | 302 Location: /reports?period=...    |
   |                                      |
   | GET /reports?period=... + cookie     |
   |------------------------------------->| SecurityContext có Authentication
   |                                      | -> authorization lại
   | <------------------------------------|
   | 200 nội dung báo cáo                 |
```

Trong một ứng dụng servlet, các lớp quan trọng có vai trò riêng:

| Thành phần | Vai trò trong luồng redirect |
| --- | --- |
| `SecurityFilterChain` và `FilterChainProxy` | Quyết định các security filters và quy tắc nào áp dụng cho request |
| `AuthorizationFilter` | Kiểm tra `authenticated()`, `hasRole(...)` và rule truy cập tài nguyên |
| `ExceptionTranslationFilter` | Chuyển `AuthenticationException` / `AccessDeniedException` từ tầng security thành hướng xử lý HTTP thích hợp |
| `AuthenticationEntryPoint` | Quyết định cách **bắt đầu xác thực** khi người dùng chưa được xác thực |
| `LoginUrlAuthenticationEntryPoint` | Entry point cho form login: điều hướng đến login page |
| `RequestCache` / `HttpSessionRequestCache` | Lưu request ban đầu để có thể quay lại sau khi đăng nhập |
| `UsernamePasswordAuthenticationFilter` | Nhận POST form login, gọi `AuthenticationManager` và xử lý thành công/thất bại |
| `SavedRequestAwareAuthenticationSuccessHandler` | Sau login thành công, ưu tiên URL của saved request nếu còn hợp lệ và cấu hình cho phép |
| `SecurityContext` / `SecurityContextRepository` | Lưu/đọc danh tính đã xác thực phù hợp chính sách, thường qua HTTP session |
| `RequestCacheAwareFilter` | Có thể khôi phục request đã lưu trong lượt truy cập phù hợp sau khi chuyển hướng |

Nhớ phân biệt: **entry point đưa bạn đến trang login**, **authentication filter kiểm tra credentials**, còn **success handler chọn đích sau login**. Không phải mọi redirect đều do một filter duy nhất thực hiện.

## 3. Tại sao request ban đầu bị chuyển hướng?

Trong cấu hình form login phổ biến:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .requestMatchers("/reports").authenticated()
        .anyRequest().authenticated()
);
http.formLogin(Customizer.withDefaults());
```

Đây là **fragment Java** cần đặt trong method cấu hình `HttpSecurity`; một ví dụ chạy đầy đủ ở mục 7.

Với `GET /reports` khi chưa có authentication hợp lệ:

1. `AuthorizationFilter` áp dụng `authenticated()` và từ chối request. Ở các phiên bản hiện đại, lỗi từ chối có thể là một subtype của `AccessDeniedException`.
2. `ExceptionTranslationFilter` xử lý tình huống chưa xác thực: nó có thể yêu cầu bắt đầu authentication, thay vì coi đây là user đã đăng nhập nhưng không đủ quyền.
3. Khi bắt đầu authentication, filter kết hợp `RequestCache` để lưu request gốc, sau đó gọi `AuthenticationEntryPoint`.
4. Với form login, entry point là `LoginUrlAuthenticationEntryPoint`, thông thường gửi **302** có `Location` dẫn đến trang login.
5. Browser thực hiện redirect bằng **request mới**. Controller `/reports` chưa được thực thi ở bước này.

Không nên tự viết logic “controller kiểm tra session rồi redirect `/login`” khi Spring Security đã quản lý vòng đời này; dễ bỏ sót quyền truy cập, request cache, security context, CSRF và sự khác biệt giữa anonymous/authenticated.

### Anonymous khác người đã đăng nhập nhưng thiếu quyền

Hai tình huống nhìn bề ngoài đều bị chặn, nhưng có luồng khác nhau:

- **Chưa đăng nhập** + vào `/admin/reports`: tùy entry point (form login) thường được **302 đến `/login`** để xác thực.
- **Đã đăng nhập** với role `USER` + vào `/admin/reports` chỉ cho `ADMIN`: không phải yêu cầu login lại theo mặc định; Spring Security thường trả **403 Access Denied**.

Cơ chế phân biệt này dựa vào trạng thái authentication và các thành phần như `AuthenticationTrustResolver`. Không suy luận chỉ từ `Authentication.isAuthenticated()` vì một số token anonymous có thể có giá trị boolean không như cách ứng dụng tự hiểu.

## 4. RequestCache: làm sao nhớ URL trước khi đăng nhập?

Nếu chỉ có `302 /login`, ứng dụng sẽ biết người dùng đã đăng nhập nhưng **không nhất thiết biết họ muốn tới đâu**. `RequestCache` giải quyết chuyện này.

`HttpSessionRequestCache` (phổ biến với form login) lưu một `SavedRequest` trong HTTP session. Nó có thể ghi nhớ:

- URL gốc cùng query string, chẳng hạn `/reports?period=2026-11`.
- Những chi tiết request cần thiết cho việc nhận diện/khôi phục, tùy implementation.
- Thông tin không đồng nghĩa với lưu toàn bộ HTTP body hay được quyền chạy lại mọi side effect.

Ví dụ:

```text
Lượt 1 (chưa xác thực)
GET /reports?period=2026-11
    -> cache lưu request phù hợp
    -> 302 /login

Lượt 2 (đăng nhập thành công)
POST /login
    -> success handler lấy URL saved request
    -> 302 /reports?period=2026-11

Lượt 3 (đã có session)
GET /reports?period=2026-11
    -> kiểm tra quyền lại
    -> 200 nếu user có quyền
```

Điểm mấu chốt: **server không tự “tiếp tục thực thi controller đang dở”**. Sau redirect, browser gửi một request mới tới URL được chọn. Với browser, thông thường cần bảo đảm **cookie phiên** được gửi qua các bước để session lưu saved request và authentication vẫn được tìm thấy.

Không mặc định rằng mọi loại request đều có thể được “replay” an toàn: **POST/PUT/PATCH/DELETE** có body và side effects. Cơ chế form login/request cache thông thường phù hợp với việc điều hướng về một trang GET; nếu muốn “gửi lại form đang dở”, ứng dụng phải thiết kế chống trùng lặp, lưu bản nháp dữ liệu và CSRF riêng. Không đặt kỳ vọng Spring Security tự replay body của request ghi dữ liệu.

### Cách RequestCache và RequestCacheAwareFilter liên quan nhau

- `RequestCache.saveRequest(...)` ghi dấu request gốc khi bị yêu cầu login.
- `SavedRequestAwareAuthenticationSuccessHandler` sau xác thực thành công có thể đọc saved request để tạo URL redirect.
- `RequestCacheAwareFilter` hỗ trợ việc lấy request đã lưu khi một request mới khớp điều kiện, theo cách `RequestCache` được cấu hình.

**Nuance ở Spring Security 6:** cách kiểm tra request đã lưu có thể được tối ưu dựa trên tham số request (ví dụ `continue` trong một số cấu hình mặc định). Vì vậy không được viết code với giả định “RequestCacheAwareFilter luôn đọc HTTP session cho mọi request”. Hãy dùng API/cấu hình tương ứng phiên bản ứng dụng và test request/redirect thực tế.

### Khi nào saved request bị mất hoặc không được sử dụng?

- Browser **không giữ cookie phiên** giữa `/reports`, `/login` và `POST /login`.
- Bạn cấu hình `NullRequestCache` hay vô hiệu hóa cơ chế lưu request.
- Session không tồn tại, bị invalidation/timeout, hoặc cấu hình stateless không hỗ trợ lưu thông tin cần thiết.
- Login được mở **chủ động từ menu** thay vì sau khi bị chặn ở URL bảo vệ; lúc này không có saved request tương ứng.
- Success handler được cấu hình **luôn chuyển về URL cố định**, thay vì ưu tiên saved request.
- Có nhiều request trong một session khiến saved request bị thay đổi; không nên coi nó là hàng đợi vô hạn mọi URL trước login.
- Hệ thống reverse proxy/path rewriting, context path hoặc cấu hình redirect URL không đúng, dẫn tới địa chỉ trả về không phù hợp.
- Ứng dụng có nhiều `SecurityFilterChain` dùng request cache/session/entry point khác nhau mà không thiết kế nhất quán.

**Lưu ý an toàn:** URL chuyển hướng có thể chứa dữ liệu nhạy cảm trong query string; không truyền token/mật khẩu qua URL. Khi dùng saved request hoặc success handler tùy chỉnh, cần tránh tạo **open redirect** từ một tham số `next` tùy ý do client đưa lên. Đặt quy tắc chỉ chấp nhận đường dẫn nội bộ an toàn hoặc danh sách domain đáng tin cậy nếu thật sự cần redirect sang domain khác.

## 5. Trang login và form được xử lý ở đâu?

Với:

```java
http.formLogin(Customizer.withDefaults());
```

Spring Security cấu hình form login mặc định. Nếu không khai báo login page riêng, ứng dụng có thể dùng **trang HTML mặc định do Spring Security tạo**.

Các URL mặc định đáng nhớ:

| URL / phương thức | Ý nghĩa |
| --- | --- |
| `GET /login` | Hiển thị trang login mặc định |
| `POST /login` | URL filter xử lý username/password |
| Form field `username` | Giá trị username mặc định |
| Form field `password` | Mật khẩu người dùng nhập |
| Field `_csrf` | CSRF token nếu CSRF protection đang được bật |
| `GET /login?error` | Vị trí form login có thể chuyển tới khi xác thực thất bại |
| `/logout` | Endpoint logout theo policy được cấu hình, với phương thức/CSRF phù hợp |

Trong Spring Security, **`UsernamePasswordAuthenticationFilter`** xử lý `POST /login`; một controller `@PostMapping("/login")` tự viết không bắt buộc và có thể gây xung đột với filter nếu không hiểu cơ chế. Filter tạo `UsernamePasswordAuthenticationToken`, gọi `AuthenticationManager`, sau đó dùng success/failure handler.

Mật khẩu không đúng thường dẫn tới **redirect về login với thông tin lỗi**, không tự động đưa người dùng quay lại tài nguyên cũ như thể đã login. Saved request có thể còn trong session để phục vụ lần login tiếp theo thành công, tùy chính sách và cách ứng dụng quản lý session.

### CSRF không phải lỗi redirect

Vì form login thường sử dụng HTTP session/cookie, CSRF protection phải được xét cẩn thận. Theo cấu hình mặc định, request POST cần token CSRF phù hợp; trang login generated sẽ có cách gửi token đó.

Nếu tự viết `POST /login` bằng `curl` mà chỉ có username/password, **thiếu CSRF token/cookie có thể dẫn đến 403** trước khi xác thực. Đừng kết luận provider kiểm tra password sai hoặc tắt CSRF cho toàn bộ website để “chữa” hiện tượng này.

Nếu dùng trang login tùy chỉnh, phải hiển thị và gửi đúng trường CSRF token, bảo đảm `GET /login` được phép truy cập công khai, và giữ `POST` xử lý login nằm đúng `SecurityFilterChain`.

## 6. Success handler: vì sao đăng nhập xong quay về URL cũ?

Với form login mặc định, `SavedRequestAwareAuthenticationSuccessHandler` thường được dùng để chọn URL sau khi người dùng xác thực thành công. Tư duy đơn giản:

```text
POST /login thành công
    |
    +-- Có SavedRequest hợp lệ, không bị cấu hình override?
    |      +-- Có -> redirect tới URL ban đầu
    |
    +-- Không có / bị override?
           +-- redirect tới target URL mặc định hoặc fallback
```

Ví dụ ở đầu bài, URL đích sau login thường là `/reports?period=2026-11`. Khi browser quay lại URL này, `AuthorizationFilter` **kiểm tra lại** role và authentication; login thành công không đồng nghĩa tự động `permitAll`.

### `defaultSuccessUrl` có thể thay đổi cách ưu tiên

Trong method cấu hình security, có thể viết:

```java
// Fragment 1: URL mặc định được dùng khi không có saved request.
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", false)
);
```

Khi `alwaysUse` là `false`, saved request (nếu còn phù hợp) thường được ưu tiên; `/dashboard` đóng vai trò mặc định khi không có request trước đó.

```java
// Fragment 2: Luôn redirect tới dashboard, bỏ ưu tiên saved request.
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", true)
);
```

Hai đoạn trên là **các lựa chọn thay thế**, không áp dụng cả hai cùng lúc. `true` có nghĩa không nhất thiết quay lại URL gốc, ngay cả khi có saved request. Nếu bạn tự thay `successHandler`, handler tùy chỉnh cũng có thể làm thay đổi hành vi này.

### Chuyện gì xảy ra nếu login thành công nhưng chưa đủ quyền?

Ví dụ anonymous vào `/admin/reports`, được đưa tới `/login`. Đăng nhập thành công bằng user chỉ có `ROLE_USER`:

```text
GET /admin/reports  -> 302 /login  (chưa xác thực)
POST /login         -> 302 /admin/reports (xác thực thành công)
GET /admin/reports  -> 403 (thiếu ROLE_ADMIN)
```

Đây là **hành vi đúng**: saved request giúp quay về nơi muốn đến, nhưng không bỏ qua phân quyền.

## 7. Ví dụ chạy được: Spring Boot 3 + Java 17 + Servlet form login

Ví dụ sử dụng Spring Boot 3.3.5 (phiên bản minh họa đã phát hành), Java 17+, `spring-boot-starter-web` và `spring-boot-starter-security`.

Ứng dụng có:

- `GET /public`: truy cập công khai.
- `GET /reports?period=2026-11`: cần đăng nhập, hiển thị tên user và giá trị query.
- `GET /admin/reports`: yêu cầu role `ADMIN`.
- Trang `/login`: dùng generated page mặc định của Spring Security.
- Hai user thử: `lan` (`USER`) và `admin` (`ADMIN`), cùng mật khẩu minh họa `demo123`.

Cấu trúc:

```text
form-login-redirect/
├── pom.xml
└── src/main/java/example/redirect/
    ├── RedirectApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 7.1. `pom.xml`

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
    <groupId>example</groupId>
    <artifactId>form-login-redirect</artifactId>
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

### 7.2. `RedirectApplication.java`

```java
package example.redirect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`: bật form login và phân quyền

```java
package example.redirect;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports").authenticated()
                .anyRequest().authenticated()
        );

        // Form login mặc định: /login, request cache và success handler.
        http.formLogin(Customizer.withDefaults());

        // Không tắt CSRF; browser login POST cần CSRF token hợp lệ.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(lan, admin);
    }
}
```

Giải thích:

1. `/reports` chỉ cần `authenticated()`. `/admin/**` yêu cầu authority `ROLE_ADMIN` vì `hasRole("ADMIN")` dùng prefix mặc định `ROLE_`.
2. `formLogin()` cấu hình entry point vào trang login, `UsernamePasswordAuthenticationFilter`, success/failure handlers và các thành phần liên quan. Không phải tự viết một `LoginController` để demo này chạy.
3. Không cấu hình `SessionCreationPolicy.STATELESS`: form login dùng HTTP session để chia sẻ authentication giữa các lần tải trang và để request cache hoạt động.
4. Không đặt `defaultSuccessUrl(..., true)`, vì muốn quan sát ưu tiên quay về URL được bảo vệ vừa yêu cầu.
5. Password được lưu ở dạng BCrypt hash trong memory. Dùng mật khẩu demo cục bộ; trong sản phẩm thật không hard-code tài khoản và không phục vụ login qua HTTP không mã hóa.
6. `anyRequest().authenticated()` là rule fallback, tránh các URL mới bị mở ngoài ý muốn. Static assets, login page tùy chỉnh và các API công khai cần được thiết kế rõ khi mở rộng ứng dụng.

### 7.4. `DemoController.java`: endpoint để quan sát hành vi redirect

```java
package example.redirect;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String root() {
        return "home:public";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/reports")
    public String reports(
            @RequestParam(defaultValue = "current") String period,
            Authentication authentication) {
        return "reports:" + authentication.getName() + ":" + period;
    }

    @GetMapping("/admin/reports")
    public String adminReports(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

Hai controller method `reports` và `adminReports` chỉ chạy sau khi filter chain đã cho phép request. `@RestController` trả chuỗi văn bản để dễ quan sát thay vì cần template engine; **trang login vẫn là trang HTML do Spring Security tạo**.

## 8. Chạy và kiểm tra chuyển hướng trong browser

### 8.1. Khởi chạy

Trong thư mục có `pom.xml`, dùng Maven 3.9+ và JDK 17+:

```bash
mvn spring-boot:run
```

Với cấu hình mặc định, Tomcat nhúng phục vụ tại `http://localhost:8080`.

### 8.2. Kiểm tra happy path giữ lại query string

1. Mở cửa sổ browser chưa đăng nhập (có thể dùng cửa sổ riêng tư mới) và truy cập `http://localhost:8080/reports?period=2026-11`.
2. Quan sát địa chỉ browser chuyển sang `http://localhost:8080/login`. Đây là bước đưa tới entry point, **chưa phải controller reports chạy**.
3. Đăng nhập bằng username `lan`, password `demo123` trên form được tạo sẵn.
4. Sau login thành công, browser trở lại `/reports?period=2026-11`. Trang hiển thị chính xác:

```text
reports:lan:2026-11
```

Như vậy saved request đã giúp giữ **địa chỉ và query string**, và authentication được đọc lại trên request mới. Trong quá trình này, browser nhận/gửi cookie phiên; khi Spring Security áp dụng session fixation protection, session ID có thể thay đổi trong lúc login, nên không phụ thuộc vào một giá trị `JSESSIONID` cố định.

### 8.3. Kiểm tra public path và rule admin

- Chưa đăng nhập, `GET /public` trả `public:ok`; không redirect.
- Chưa đăng nhập, `GET /admin/reports` thường chuyển sang `/login`.
- Đăng nhập `lan` rồi truy cập `/admin/reports`: server từ chối với HTTP **403** vì `lan` có `ROLE_USER`, không có `ROLE_ADMIN`. Không tự động coi đây là một lần login thất bại.
- Đăng xuất khỏi phiên `lan` theo luồng chuẩn và đăng nhập `admin` với cùng mật khẩu demo; `GET /admin/reports` trả:

```text
admin:admin
```

Để quan sát đúng saved request, nên bắt đầu phiên mới từ **URL cần bảo vệ**, không mở `/login` trực tiếp trước rồi kỳ vọng có sẵn một URL gốc.

### 8.4. Kiểm tra HTTP 302 bằng curl mà không giả lập form login

```bash
# Dùng GET thật để kích hoạt luồng lưu request và 302.
curl -i -c cookies.txt \
  'http://localhost:8080/reports?period=2026-11'

# Lấy trang login, gửi cookie phiên đã lưu.
curl -i -b cookies.txt 'http://localhost:8080/login'
```

Ở request đầu, các header liên quan sẽ có nội dung theo dạng:

```text
HTTP/1.1 302
Location: http://localhost:8080/login
Set-Cookie: JSESSIONID=...; ...
```

Đây là **minh họa dạng header**, không phải transcript byte-for-byte cố định: địa chỉ `Location` có thể là absolute/relative tùy hạ tầng và `Set-Cookie` phụ thuộc cấu hình cookie/session. `curl` mặc định không theo redirect; dùng `-L` nếu muốn theo redirect, nhưng cần hiểu thứ tự request mới.

**Đừng dùng `curl -I` (HEAD) rồi kỳ vọng mô phỏng chính xác việc browser truy cập GET.** Và không POST tới `/login` bằng `curl` chỉ với username/password: form login đang bật CSRF, cần trích token động từ trang, giữ session cookie và gửi lại token. Browser thuận tiện hơn để thử luồng end-to-end này.

### 8.5. Các mã phản hồi phải phân biệt

| Phản hồi | Khi nào trong ví dụ? | Ai có vai trò quyết định? |
| --- | --- | --- |
| **302 → `/login`** | Anonymous yêu cầu tài nguyên được bảo vệ | `ExceptionTranslationFilter` + `LoginUrlAuthenticationEntryPoint` |
| **200 HTML login** | `GET /login` | Trang đăng nhập mặc định hoặc custom login view |
| **302 → saved URL** | `POST /login` với credentials và CSRF hợp lệ | Authentication filter + success handler |
| **302 → `/login?error`** | Form login thất bại do credentials không hợp lệ theo policy mặc định | Failure handler |
| **200 resource** | Browser quay lại URL đã lưu, có authentication và đủ quyền | Authorization + controller |
| **403** | Đã login nhưng thiếu role; hoặc request POST thiếu CSRF token | Access-denied / CSRF mechanisms |
| **401** | Có thể thấy với HTTP Basic/Bearer entry point, không phải luồng browser form login mặc định | Entry point tương ứng |

HTTP status còn phụ thuộc loại request, các custom filter/handler và hạ tầng ứng dụng. Không áp đặt “mọi request chưa đăng nhập đều 302” nếu ứng dụng có nhiều authentication mechanisms.

## 9. Tùy chỉnh trang login: không tạo vòng lặp redirect

Khi thay trang generated bằng trang riêng, cấu hình có thể như sau:

```java
// Fragment trong SecurityFilterChain, thay cho formLogin mặc định.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public", "/signin", "/error").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/perform_login")
        .permitAll()
);
```

Đây là **fragment cấu hình thay thế**, không được ghép trùng vào cấu hình mục 7. Khi dùng:

- Bạn phải tự tạo **`GET /signin`** (controller + HTML template hoặc view) để hiển thị form. Spring Security không tự tạo trang custom `/signin`.
- Form cần `method="post"`, `action="/perform_login"` đúng context path, field username/password đúng tên mặc định hoặc tên đã tùy chỉnh, và **CSRF token hợp lệ**.
- URL login page, login processing và các static assets thiết yếu phải truy cập được khi anonymous; nếu chính `/signin` lại yêu cầu authenticated, server có thể chuyển hướng về chính nó liên tục.
- `loginProcessingUrl` là **endpoint do security filter xử lý**, không nhất thiết cần controller POST cùng URL.
- Khi dùng nhiều `SecurityFilterChain`, phải bảo đảm URL login và login processing thuộc **chain có formLogin**. Nếu login URL bị match vào một chain khác, browser có thể 404, 401 hoặc lặp redirect.

Một trang login custom thường dùng Thymeleaf/JSP hoặc SPA frontend. Nếu frontend khác origin, cần thiết kế CORS, cookie, CSRF và URL callback rõ ràng, không thay đổi ngẫu nhiên security filter order để “thử cho chạy”.

### Tùy chỉnh target sau login

```java
// Fragment: chỉ khi không có saved request sẽ dùng /dashboard.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", false));
```

```java
// Fragment khác: luôn về /dashboard, bỏ ưu tiên saved request.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", true));
```

Hai đoạn là **hai phương án thay thế**, không phải cấu hình đồng thời. Nếu chính sách UX yêu cầu luôn landing page sau login, bạn có thể chọn dạng thứ hai; nếu mục tiêu là người dùng quay lại nơi họ đang truy cập, giữ handler ưu tiên saved request.

### Tùy chỉnh request cache

```java
// Fragment cho trường hợp CHỦ ĐỘNG không muốn lưu request ban đầu.
http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
```

Cần import `org.springframework.security.web.savedrequest.NullRequestCache`. Khi dùng cách này, không kỳ vọng ứng dụng quay lại URL bảo vệ ban đầu qua cơ chế saved request mặc định. Với REST API stateless, thường chọn entry point trả 401/403, không lưu request để redirect sang form login.

## 10. REST API và nhiều SecurityFilterChain

Ứng dụng có cả web UI và API nên cân nhắc tách chain:

- WEB: form login, session, request cache và redirect về trang HTML.
- API: Bearer token hoặc Basic theo thiết kế; thường cần **HTTP 401** khi chưa xác thực và **403** khi thiếu permission; không cần trình duyệt đi tới `/login`.

Ví dụ **fragment minh họa riêng**, không ghép nguyên vào ứng dụng mục 7:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đoạn này cần `@Configuration`, `@EnableWebSecurity` và các import phù hợp `Order`, `SecurityFilterChain`, `HttpSecurity`, `SessionCreationPolicy`, `NullRequestCache`; nó chỉ trình bày **phân chia chính sách**, không phải một ứng dụng runnable độc lập. Đặt API chain **trước** WEB fallback để `/api/**` không bị web chain nhận và redirect tới form login.

Không suy luận “stateless thì CSRF luôn được tắt an toàn”; nếu API dùng credentials mà browser tự động gửi như cookie hoặc một số trường hợp Basic, cần đánh giá CSRF theo mô hình client/threat model. Nếu API chỉ chấp nhận Bearer token gửi chủ động trong header, có thể đưa ra policy CSRF khác riêng cho API chain sau khi xác minh điều kiện.

## 11. Lỗi thường gặp và cách tìm đúng nguyên nhân

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `GET /reports` trả 200 khi chưa login | Rule quá rộng `permitAll` hoặc request không đi qua chain bảo vệ | Kiểm tra matcher, filter registration và cấu hình authorize |
| Chuyển hướng nhiều lần giữa `/login` và `/login` | Trang login bị rule bảo vệ, login page URL sai | Cho anonymous truy cập login page và resources cần thiết |
| Login xong luôn về `/` chứ không về reports | Không có saved request, mất session cookie, custom handler hoặc `defaultSuccessUrl(..., true)` | Kiểm tra RequestCache, session, handler và flow truy cập |
| Login xong quay về reports nhưng bị 403 | User không có authority cần thiết | Đây là authorization, không phải lỗi request cache |
| `POST /login` trả 403 | Thiếu/sai CSRF token hoặc session cookie | Kiểm tra form action, CSRF hidden field và cookie |
| `POST /login` trả 404 | Sai `loginProcessingUrl`, request vào sai security chain hoặc không có filter xử lý | Xác minh login processing URL và matcher |
| `GET /login` 404 khi dùng custom login page | Chỉ đặt `loginPage` mà chưa tạo controller/view | Tạo endpoint hiển thị login |
| API bị redirect HTML thay vì trả 401 | Web chain xử lý API hoặc entry point không phù hợp | Tách API chain/entry point, kiểm tra `@Order` |
| Saved request trở lại URL sai host/scheme | Reverse proxy headers, context path hoặc redirect config sai | Kiểm tra trusted forwarded headers và URL generation |
| Đăng nhập thành công nhưng browser vẫn anonymous | Cookie không được gửi, policy stateless, context không lưu hoặc session lỗi | Kiểm tra `SecurityContextRepository`, cookie, session |
| Sau logout browser còn thấy trang cache | Browser/proxy caching hoặc logout chưa invalidation đúng | Xem cache headers, logout handler, session invalidation |

### Cách debug theo từng request

1. Ghi lại **URL đầu tiên** người dùng mở, method, query string và HTTP status.
2. Kiểm tra security chain đã được chọn, rule `authenticated()`/`hasRole()` áp dụng, trạng thái anonymous.
3. Kiểm tra redirect đầu tiên: `Location` có trỏ đúng URL login không? Có session cookie khi cần lưu request không?
4. Kiểm tra GET login page: response có form đúng action, CSRF token và CSS/JS cần thiết không?
5. Kiểm tra POST login: filter có xử lý? Authentication thành công hay failure? Có session fixation protection/chuyển session ID phù hợp không?
6. Kiểm tra `SavedRequestAwareAuthenticationSuccessHandler`: có saved request hay bị `defaultSuccessUrl(..., true)` hoặc custom handler ghi đè?
7. Kiểm tra GET trở về URL gốc: browser có cookie phiên mới? User có authority cần thiết? Nếu 403, đây là điều kiện truy cập sau login.

Có thể bật log ở môi trường development để quan sát filter và xử lý xác thực:

```properties
logging.level.org.springframework.security=DEBUG
```

Không ghi password, CSRF token, raw session cookie hoặc full `Authorization` header vào log. Khi điều tra trên production, che thông tin cá nhân và secrets theo chính sách quản trị log.

## 12. Các trường hợp cần tự kiểm chứng

| Thử nghiệm | Kết quả hợp lý |
| --- | --- |
| Anonymous vào `/public` | 200, không redirect |
| Anonymous vào `/reports?period=2026-11` | 302 tới login |
| Đăng nhập `lan` sau khi vào reports | 302 về saved URL, rồi 200 với body `reports:lan:2026-11` |
| Mở `/login` trực tiếp rồi đăng nhập, trước đó không truy cập URL bảo vệ | Chuyển tới target URL mặc định/fallback, không có saved reports URL |
| Đăng nhập với mật khẩu sai | Không cấp session xác thực; failure handler đưa về trang login với lỗi |
| Anonymous vào `/admin/reports` | 302 tới login |
| Sau login bằng `lan` vào admin | 403 vì không có `ROLE_ADMIN` |
| Sau login bằng `admin` vào admin | 200 với body `admin:admin` |
| Tự POST login không có CSRF token đúng | Thường bị từ chối với 403 |
| Bật `defaultSuccessUrl("/dashboard", true)` | Thành công về dashboard thay vì ưu tiên saved request |
| Tắt request cache qua `NullRequestCache` | Không còn hành vi quay về URL gốc dựa trên saved request mặc định |

Ở kiểm thử tích hợp, nên xác minh **hai request tách biệt**: request đầu trả redirect đến login; sau login, browser hoặc test client giữ session/cookies và request lại URL gốc. Đừng chỉ test `/login` rồi suy luận cơ chế lưu request gốc chắc chắn hoạt động.

## 13. Checklist triển khai thực tế

- [ ] Định nghĩa tài nguyên cần bảo vệ bằng `authorizeHttpRequests`, không dựa vào controller tự redirect.
- [ ] Dùng entry point đúng loại client: form login cho browser, 401/403 cho API.
- [ ] Bảo đảm login page/login processing URL và static resources thiết yếu không bị security rule tạo vòng lặp.
- [ ] Kiểm tra `RequestCache` và session cookie khi cần quay lại URL đã truy cập; không lưu secrets trong query string.
- [ ] Giữ CSRF protection cho form login và những thao tác thay đổi trạng thái dùng cookie/session.
- [ ] Hiểu rằng saved request không replay request body hay side effects của POST/PUT.
- [ ] Kiểm tra success handler: ưu tiên saved request hay luôn redirect target cố định; cấu hình có chủ đích.
- [ ] Sau login luôn kiểm tra authorization lại, đặc biệt với URL cần role cao hơn.
- [ ] Bảo vệ cookie phiên bằng HTTPS, `Secure`, `HttpOnly`, `SameSite` hợp lý và session fixation protection.
- [ ] Với reverse proxy hoặc nhiều security chain, test redirect host/scheme/context path và quyền thực tế.
- [ ] Thêm test happy path và failure path, xử lý các trường hợp session timeout, cookie bị chặn và login sai.

**Ghi nhớ:** Khi anonymous mở tài nguyên được bảo vệ, Spring Security Servlet có thể **chặn request → lưu SavedRequest → dùng AuthenticationEntryPoint chuyển tới /login → xác thực bằng form → success handler chuyển về SavedRequest → kiểm tra quyền lại trên request mới**. Phần redirect không thay thế authentication hay authorization; nó chỉ nối liền trải nghiệm người dùng giữa tài nguyên gốc và trang đăng nhập.