# Phân biệt HTTP 401, 403 và chuyển hướng đăng nhập trong Spring Boot web runtime

## 1. Mục tiêu của bài học

Khi một request đến endpoint được bảo vệ trong Spring Boot, hệ thống cần trả lời hai câu hỏi **khác nhau**:

1. **Authentication — xác thực:** Hệ thống đã biết danh tính của người đang gọi chưa? Credential có hợp lệ không?
2. **Authorization — phân quyền:** Với danh tính đó, người gọi có quyền thực hiện hành động trên tài nguyên cụ thể không?

Từ đó phát sinh ba hành vi thường gặp:

- **401 Unauthorized:** client chưa cung cấp bằng chứng xác thực hợp lệ hoặc bằng chứng bị từ chối. Tên mã có chữ “Unauthorized”, nhưng theo ngữ nghĩa HTTP, nó thường báo **cần xác thực hợp lệ**.
- **403 Forbidden:** server hiểu request nhưng **không cho phép** thao tác. Một người có thể đã đăng nhập đúng tài khoản nhưng không có quyền; ngoài ra một số biện pháp bảo vệ khác như **CSRF** cũng có thể tạo 403.
- **302 Found → trang đăng nhập:** trong ứng dụng web dùng **form login và session cookie**, người truy cập chưa đăng nhập thường được **chuyển hướng** tới `/login`. Đây là hành vi bắt đầu xác thực dành cho browser, không đồng nghĩa server trả 401.

Bài này dùng **Spring Boot, Spring Security và Spring MVC (Servlet stack)** để chỉ ra điều kiện nào sinh 401/403/redirect, vai trò `AuthenticationEntryPoint` và `AccessDeniedHandler`, cách thiết kế riêng cho REST API và trang web truyền thống, cũng như kiểm thử bằng Spring Security Test.

Mục tiêu sau khi học: khi gặp status 401, 403, 302 hoặc redirect loop, bạn có thể xác định **lớp nào trả response và vì sao**, không “chữa” mọi lỗi bằng cách tắt Spring Security hoặc thêm `permitAll()`.

## 2. Bảng phân biệt nhanh

| Tình huống | API dùng HTTP Basic/Bearer | Browser dùng form login | Ý nghĩa |
| --- | --- | --- | --- |
| Chưa gửi credential, vào tài nguyên cần xác thực | Thường **401** + challenge phù hợp | Thường **302** tới `/login` | Cần bắt đầu xác thực |
| Gửi mật khẩu sai hoặc token không hợp lệ | Thường **401** | Login POST thất bại, thường **302 /login?error** hoặc render thông báo lỗi | Xác thực không thành công |
| Đăng nhập đúng, thiếu role/authority để xem tài nguyên | **403** | **403** hoặc trang báo từ chối được cấu hình | Đã biết danh tính nhưng không được cấp quyền |
| Request POST dùng cookie, thiếu CSRF token | Có thể **403** nếu chain bật CSRF | Thường **403** | Chống CSRF từ chối; không thể suy luôn “thiếu role” |
| Đã đăng nhập, truy cập endpoint hợp lệ và đủ quyền | **200** hoặc mã nghiệp vụ phù hợp | **200** hoặc redirect theo workflow | Security cho request đi tiếp |
| Truy cập URL không tồn tại, sau khi đã qua bảo vệ | Thường **404** | Thường **404** | Routing/định danh tài nguyên khác với xác thực/phân quyền |

**Cảnh báo:** bảng mô tả **cấu hình phổ biến**, không phải quy tắc bất biến của mọi ứng dụng. `SecurityFilterChain`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, method security, CORS, CSRF, API gateway và controller exception handlers đều có thể thay đổi status. Một status 403 **không tự chứng minh** user đã đăng nhập, và một redirect 302 **không tự chứng minh** login thành công.

### 2.1. HTTP 401 và header `WWW-Authenticate`

Theo HTTP semantics, 401 thông báo request thiếu credential hợp lệ cho target resource và phản hồi phải bao gồm **challenge** `WWW-Authenticate` thích hợp. HTTP Basic ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Tên realm mang tính minh họa, có thể thay đổi theo cấu hình; body có thể rỗng, HTML hoặc JSON tùy stack. Browser có thể hiện hộp thoại nhập user/password khi nhận Basic challenge, trong khi API client dùng challenge để quyết định cách cung cấp credential.

Với OAuth 2.0 Resource Server/Bearer token, challenge điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Trong một số trường hợp, Bearer token không đủ scope có thể trả **403** cùng `WWW-Authenticate: Bearer error="insufficient_scope"` và thông tin scope phù hợp. **Không gộp mọi lỗi OAuth thành Basic**; Spring Security sử dụng entry point và access-denied handler tương ứng với phương thức xác thực đang cấu hình.

Spring Security HTTP Basic còn có hành vi dành cho một số AJAX request: tài liệu chính thức nêu trường hợp request có `X-Requested-By: XMLHttpRequest` thì challenge/body của 401 có thể được giảm/bỏ để tránh hộp thoại Basic của browser. Vì vậy **nếu đang kiểm thử chính challenge Basic**, hãy dùng request thường, không cố áp mọi client header.

### 2.2. HTTP 403 không chỉ dành cho role

403 có thể đến từ:

- User đã authenticated, nhưng thiếu `ROLE_ADMIN`, authority, permission, tenant ownership hoặc điều kiện policy.
- CSRF token không tồn tại, sai hoặc hết hiệu lực ở request thay đổi trạng thái.
- Một gateway/WAF/ingress chặn request trước Spring Boot.
- IP allowlist, rate-limit policy riêng hoặc logic từ chối được ứng dụng thiết kế trả 403.
- Method security, controller/service hoặc chính sách tài nguyên có handler từ chối quyền.

Vì vậy khi gặp 403 phải **xem nguồn phản hồi**: security filter, CSRF, authorization, service, gateway, hay exception handler. Không sửa bằng cách cấp thêm `ADMIN` hoặc tắt CSRF khi chưa xác định được nguyên nhân.

## 3. Cơ chế Spring Security: ai quyết định 401, 403 hay redirect?

Trong ứng dụng Servlet, Spring Security chèn một chuỗi filter vào request pipeline, thông qua `FilterChainProxy` và các `SecurityFilterChain`. Những thành phần chính:

- **Authentication filter** (ví dụ `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, Bearer token filter) kiểm tra credentials và tạo đối tượng `Authentication`.
- **SecurityContext** giữ thông tin authentication của request hiện tại theo cơ chế Spring Security.
- **AuthorizationFilter** và/hoặc method security đánh giá các policy như `authenticated()`, `hasRole("ADMIN")` hoặc authority/scope.
- **ExceptionTranslationFilter** chuyển các lỗi security `AuthenticationException` và `AccessDeniedException` thành hành vi HTTP phù hợp.
- **AuthenticationEntryPoint** bắt đầu xác thực: có thể trả 401/challenge Basic hoặc Bearer, hoặc redirect đến trang login.
- **AccessDeniedHandler** xử lý trường hợp request bị từ chối quyền khi danh tính đã được xác thực theo ngữ nghĩa của security filter.

Luồng khái niệm:

```text
HTTP request
    |
    v
SecurityFilterChain phù hợp request
    |
    +--> Authentication: credential hợp lệ chưa?
    |          |
    |          v
    +--> Authorization: có quyền với endpoint/object?
               |
               +--> Cho phép ---> Controller ---> 2xx/3xx/4xx/5xx nghiệp vụ
               |
               +--> AuthenticationException
               |           |
               |           v
               |      AuthenticationEntryPoint
               |        API Basic: 401 + WWW-Authenticate
               |        Web Form: 302 -> /login
               |
               +--> AccessDeniedException
                           |
                   Anonymous/unauthenticated?
                      /             \
                    Có               Không
                    |                  |
             EntryPoint         AccessDeniedHandler
              401/302               thường 403
```

**Điểm dễ sai:** Khi một user **anonymous** đụng `hasRole("ADMIN")`, `AuthorizationFilter` có thể ném `AccessDeniedException`. Nhưng `ExceptionTranslationFilter` nhận ra caller chưa authenticated và gọi **entry point**, không nhất thiết trả 403. Với API Basic, anonymous thường nhận 401; với form login, anonymous thường nhận redirect login.

Nếu caller đã authenticated nhưng vẫn thiếu quyền, handler từ chối thường trả 403. Đây là lý do “thiếu role” với anonymous và với user đã đăng nhập có **status khác nhau**.

`ExceptionTranslationFilter` không tự tính quyền. Nó chỉ bắt và chuyển security exceptions phù hợp từ phần filter chain phía sau. Một exception đã bị `@ControllerAdvice` hoặc layer khác xử lý thành HTTP body riêng có thể không đi qua đường xử lý này như bạn kỳ vọng. Đặt security rule ở **filter/method security** thay vì tự ném exception ngẫu nhiên và hy vọng kết quả mặc định luôn như nhau.

## 4. Xác thực khác phân quyền trong code

Một số rule thường dùng:

```java
// Snippet bên trong authorizeHttpRequests, không phải class độc lập.
.requestMatchers("/profile").authenticated()
.requestMatchers("/admin").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("REPORT_READ")
.anyRequest().denyAll()
```

- `authenticated()`: caller phải được Spring Security xem là đã xác thực theo policy.
- `hasRole("ADMIN")`: Spring Security mặc định tìm authority `ROLE_ADMIN`; **không** truyền `"ROLE_ADMIN"` cho `hasRole` theo cách thông thường, vì prefix được thêm tự động.
- `hasAuthority("REPORT_READ")`: so khớp tên authority chính xác; không tự thêm `ROLE_`.
- `denyAll()`: từ chối kể cả khi caller authenticated; anonymous có thể được đưa tới entry point.
- `permitAll()`: không yêu cầu đăng nhập cho matcher đó; vẫn có thể chịu các filter bảo vệ khác, ví dụ CSRF trên unsafe method.
- Quyền theo **object** (chỉ owner được xem đơn hàng) không được bảo đảm chỉ vì URL `/orders/{id}` yêu cầu authenticated. Service cần kiểm tra ownership/tenant/ACL, không dựa vào ID khó đoán.

Ví dụ:

```text
GET /orders/123
Authentication: user = alice

Nếu order 123 thuộc alice -> được phép.
Nếu order 123 thuộc bob -> bị từ chối theo policy,
không phải tự động được xem chỉ vì alice đã login.
```

Với object tồn tại nhưng không được phép công bố cả sự tồn tại, một ứng dụng có thể chọn **404 thay vì 403** theo chính sách chống enumeration. Cần áp dụng nhất quán; không đánh đồng “không có quyền” với “không tồn tại” trong internal logs/metrics.

## 5. Hai kiểu web runtime phổ biến

### 5.1. REST API: thường cần status 401/403, không chuyển sang HTML login

Một API phục vụ mobile app, frontend SPA hoặc service-to-service thường cần **machine-readable response**:

```text
GET /api/profile
  Không credentials  -> 401 (+ auth challenge)
  Credentials sai    -> 401
  Credentials hợp lệ -> 200

GET /api/admin
  Chưa xác thực      -> 401
  USER thường        -> 403
  ADMIN              -> 200
```

Nếu API vô tình trả `302 Location: /login`, nhiều HTTP client sẽ **tự đi theo redirect** và nhận trang HTML login với status cuối 200. Frontend có thể cố parse HTML thành JSON, gây lỗi kiểu `Unexpected token '<'`. Log và metrics có thể chỉ nhìn 200 ở request cuối mà bỏ qua 302 ban đầu.

Đừng chỉ thêm header `Accept: application/json` rồi hy vọng framework tự chọn 401 đúng mọi endpoint. Khi cùng ứng dụng có API và browser UI, thiết kế rõ **security matcher và entry point** để hành vi ổn định theo route.

Với JWT/Bearer, dùng Spring Security OAuth 2.0 Resource Server chính thức, không tự giải token bằng string parsing; 401/403 và challenge theo cơ chế Bearer. Ví dụ runnable ở phần 8 dùng **HTTP Basic** chỉ vì dễ minh họa, không phải khuyến nghị dùng Basic với mật khẩu cố định trong production.

### 5.2. Trang web server-rendered: 302 đưa người chưa login tới trang đăng nhập

Đối với UI dùng browser/session cookie:

```text
1. Browser -> GET /app/private
2. Spring Security: chưa đăng nhập
3. Response: HTTP 302, Location: /login
4. Browser -> GET /login
5. Spring Security hiển thị trang login
6. User POST /login với username/password + CSRF token
7. Đăng nhập thành công -> chuyển tiếp theo success handler
8. Browser truy cập trang được phép
```

Chuyển hướng **bắt đầu quá trình đăng nhập**, không phải xác nhận danh tính. Nếu user đã có session hợp lệ nhưng thiếu role vào `/app/admin`, Spring Security thường **trả 403**, không chuyển tới `/login` để user nhập lại cùng tài khoản.

Các yếu tố ảnh hưởng đến redirect:

- `LoginUrlAuthenticationEntryPoint` quyết định nơi bắt đầu authentication cho form login.
- Request cache có thể lưu một **saved request** để đưa user quay lại tài nguyên ban đầu sau khi login. Nếu đặt `defaultSuccessUrl("/app/private", true)`, cấu hình này cố ý bỏ qua saved request và luôn chuyển tới một URL cố định khi thành công.
- Sai `X-Forwarded-Proto`, host, proxy prefix hoặc context path có thể tạo `Location` sai, HTTPS→HTTP, redirect loop hoặc cookie session không được gửi.
- Login page tự tạo của Spring Security chỉ tồn tại khi dùng form login mặc định; nếu cấu hình custom `loginPage("/login")` thì **ứng dụng phải tự render trang đó**.
- Trang `/login` và static assets cần được phép truy cập; nếu login page bị chính security rule chặn, dễ tạo vòng lặp redirect.

## 6. Hiểu phản hồi khi login thất bại và logout

**Sai mật khẩu ở API Basic:** thường 401; challenge cho client biết cần credential hợp lệ. **Sai mật khẩu khi POST HTML form:** thường redirect tới `/login?error`, trong trường hợp cấu hình mặc định, hoặc hiển thị lỗi bằng custom failure handler. Đây là luồng browser, không đồng nhất với API 401.

**Login thành công:** thường redirect 302 tới saved request hoặc default success URL, đồng thời session/security context được quản lý theo policy. 302 ở đây là **kết quả login success**; nó không có cùng ý nghĩa với 302 khi anonymous bị yêu cầu đăng nhập. Cần xem **request gốc** và Location.

**Logout:** với Spring Security CSRF mặc định, logout cần POST có CSRF token; sau logout có thể redirect `/login?logout`. Đừng bật logout qua GET tùy tiện ở ứng dụng browser-authenticated; nếu cần xử lý API token stateless, chiến lược logout/revocation khác session logout.

**Không suy ra từ một mã HTTP duy nhất:** nếu muốn biết user đã xác thực, hãy kiểm tra security context và xử lý kết quả theo auth contract, không dựa vào việc response cuối cùng có `200` hoặc `302`.

## 7. API Basic và form login trong cùng ứng dụng: vì sao cần hai SecurityFilterChain?

Nếu bật đồng thời:

```java
http.httpBasic(Customizer.withDefaults())
    .formLogin(Customizer.withDefaults());
```

trên **một filter chain chung**, Spring Security có thể dùng content negotiation hoặc entry-point selection theo request để chọn Basic challenge hay login redirect. Đây là cấu hình hợp lệ cho nhiều ứng dụng, nhưng dễ gây bất ngờ nếu frontend gửi `Accept` khác, hoặc khi browser tải API bằng fetch.

**Cách minh họa rõ ràng:** tách:

- Chain `/api/**`: chỉ HTTP Basic; stateless; **401** khi thiếu credential, **403** khi authenticated nhưng thiếu role.
- Chain còn lại cho `/app/**` và login: form login; session; **302** với anonymous, **403** khi người đã đăng nhập không có authority.

Với nhiều `SecurityFilterChain`, Spring Security chọn chain phù hợp theo thứ tự `@Order`. Một request chỉ đi qua **chain được chọn**, không phải lấy tất cả rule của mọi chain cộng lại. `securityMatcher(...)` chọn phạm vi **filter chain**, còn `requestMatchers(...)` bên trong `authorizeHttpRequests` đặt luật **authorization của chain ấy**.

Phải có fallback chain để không vô tình bỏ một route không được bảo vệ. Trong ví dụ, chain mặc định có `anyRequest().denyAll()` và vẫn cho trang login cần thiết. Khi dự án thêm endpoint mới, buộc người phát triển xác định chính sách thay vì mặc nhiên public.

## 8. Ví dụ chạy được: Spring Boot 3.5.16 + Java 17 + Spring Security

Ví dụ dùng **Spring MVC** (embedded Tomcat), **HTTP Basic** cho API và **form login mặc định** cho browser. Chọn Spring Boot 3.5.16 để cố định tập API cho bài thực hành; đây là phiên bản đã phát hành, nhưng **Spring Boot 3.5.x đã kết thúc hỗ trợ OSS**. Production mới nên dùng một dòng **Spring Boot còn được hỗ trợ** và bản vá hiện hành; khi chuyển sang Boot 4.x cần đối chiếu starter/test packages và API phù hợp phiên bản.

Tài khoản ví dụ (chỉ cho local demo):

| User | Mật khẩu demo | Quyền |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_ADMIN`, `ROLE_USER` |

**Đây là credential mẫu cố định để học trong môi trường local, không được đưa lên Internet hay dùng trong sản phẩm.** Mật khẩu được encode bằng BCrypt khi tạo `UserDetailsService`, nhưng hardcode password vẫn là anti-pattern cho production.

### 8.1. Cấu trúc dự án

```text
security-status-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  └─ java/com/example/demo/
   │     ├─ SecurityStatusApplication.java
   │     ├─ SecurityConfiguration.java
   │     └─ DemoEndpoints.java
   └─ test/
      └─ java/com/example/demo/
         └─ SecurityStatusApplicationTest.java
```

### 8.2. File `pom.xml`

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-status-demo</artifactId>
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

Maven cần kết nối tới repositories thích hợp để tải dependencies. Nếu đã tạo project bằng Spring Initializr/Maven Wrapper, giữ wrapper và cấu hình build do công ty phê duyệt; khi dùng parent mới được hỗ trợ, cập nhật phiên bản và tương thích API cùng nhau.

### 8.3. Main class

**`src/main/java/com/example/demo/SecurityStatusApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityStatusApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusApplication.class, args);
    }
}
```

### 8.4. Hai filter chains và tài khoản demo

**`src/main/java/com/example/demo/SecurityConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable());

        // Không tắt CSRF trong demo: cả hai API chỉ dùng GET.
        // Với POST/PUT/DELETE, đánh giá CSRF theo cách client gửi credentials.
        return http.build();
    }

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/app/admin").hasRole("ADMIN")
                .requestMatchers("/app/private").authenticated()
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/app/private", true)
            );

        // Spring Security giữ CSRF protection mặc định.
        // Form login mặc định do Spring Security tự render.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN", "USER")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

**Giải thích:**

1. `@Order(1)` + `securityMatcher("/api/**")` đảm bảo mọi request API đi qua chain có `httpBasic` và không bị form-login entry point bắt để chuyển sang HTML.
2. `hasRole("ADMIN")` của `/api/admin` và `/app/admin` so khớp authority `ROLE_ADMIN`. `reader` hợp lệ nhưng chỉ có `ROLE_USER` nên bị 403.
3. `/api/profile` và `/app/private` yêu cầu xác thực, nhưng không yêu cầu role admin.
4. `SessionCreationPolicy.STATELESS` ngăn Spring Security tạo/sử dụng HttpSession để lưu SecurityContext cho API. Client Basic gửi credentials ở mỗi request. Nó **không biến toàn bộ ứng dụng thành stateless**: browser chain vẫn có form login/session.
5. `requestCache(cache -> cache.disable())` tránh lưu saved request cho API, vì client API tự retry sau khi có credential.
6. **CSRF vẫn bật theo mặc định ở cả hai chain**. API ví dụ chỉ có GET, nên không cần nới bảo vệ. Nếu sau này thêm state-changing API, phải quyết định chính xác chính sách CSRF theo cookie, Basic, bearer token và kiểu client; không nên copy `csrf.disable()` bừa bãi.
7. Chain browser mặc định bắt các URL không thuộc `/api/**`, tạo form login mặc định ở `/login`, bảo vệ trang riêng và admin. `defaultSuccessUrl(..., true)` giúp test không phụ thuộc saved request sau login.
8. `anyRequest().denyAll()` để tránh route mới vô tình public. Khi thêm assets, health endpoint, login/logout page tùy chỉnh, phải cấp quyền có chủ đích cho đúng URL.
9. BCrypt được dùng để encode mật khẩu demo; trong production cần user store/identity provider và quản lý credentials, reset, MFA, audit, session fixation, rate limiting, secrets và account lifecycle.
10. Không dùng `@EnableWebSecurity` trong demo vì Spring Boot/Spring Security auto-configuration đã tạo cơ sở phù hợp cho các `SecurityFilterChain` bean này. Không nên đồng thời khai báo thêm filter chain trùng URL vô tình.

**Lưu ý về logout:** ví dụ tập trung GET và form login. Nếu cần logout, bật/cấu hình `logout()` chuẩn của Spring Security, bảo vệ POST logout bằng CSRF và test lại quyền truy cập sau logout; không tự xóa cookie mà bỏ qua invalidate/security context.

### 8.5. Controller để tạo kết quả dễ quan sát

**`src/main/java/com/example/demo/DemoEndpoints.java`**

```java
package com.example.demo;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoEndpoints {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public String index() {
        return "Security status demo\n";
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName(), "area", "api");
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin(Authentication authentication) {
        return Map.of("user", authentication.getName(), "role", "admin");
    }

    @GetMapping(value = "/app/private",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String privatePage(Authentication authentication) {
        return "Private page for " + authentication.getName() + "\n";
    }

    @GetMapping(value = "/app/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String adminPage(Authentication authentication) {
        return "Admin page for " + authentication.getName() + "\n";
    }
}
```

- `Authentication` được lấy từ request đã đi qua security filter, không nhận user identity từ query parameter. Không dùng `?user=admin` để quyết định quyền.
- `@RestController` trả response body; các chuỗi text không phải tên template. Trang login mặc định là HTML được Spring Security tạo riêng; demo không cần Thymeleaf.
- `Map<String,String>` được serialize thành JSON qua Jackson. Thứ tự trường JSON không cố định; test nên kiểm tra field/value, không so sánh một chuỗi JSON theo thứ tự key.
- Controller không chứa `if (isAdmin)` tự chế. Security rules nằm ở filter chain, và production vẫn cần service authorization khi dữ liệu phụ thuộc owner/tenant hoặc object ID.

### 8.6. Chạy ứng dụng

Với JDK 17+, Maven đã được cài:

```bash
java -version
mvn spring-boot:run
```

Nếu đã dùng Maven Wrapper từ Spring Initializr:

```bash
./mvnw spring-boot:run
```

Trên Windows: `mvnw.cmd spring-boot:run`. Mặc định ứng dụng lắng nghe ở `http://localhost:8080` nếu không có cấu hình thay port. Những response mẫu bên dưới giả định không có application.properties hay proxy/security filters khác được thêm vào.

### 8.7. API: thử 401, 403 và 200 với curl

**Không gửi credential:**

```bash
curl -i http://localhost:8080/api/profile
```

Kỳ vọng: **HTTP 401**, header `WWW-Authenticate` bắt đầu bằng `Basic`, không phải redirect `/login`. Body lỗi phụ thuộc Spring Security/Boot, có thể rỗng; không giả định một JSON error body bắt buộc.

**Mật khẩu sai:**

```bash
curl -i -u reader:wrong \
  http://localhost:8080/api/profile
```

Kỳ vọng: **HTTP 401**; không có dữ liệu profile thành công.

**Mật khẩu đúng:**

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/profile
```

Kỳ vọng: HTTP **200** với JSON gồm `"user":"reader"` và `"area":"api"`.

**Đã đăng nhập nhưng thiếu role ADMIN:**

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin
```

Kỳ vọng: **HTTP 403**. Đây là lỗi authorization, không phải lý do để đưa browser tới trang login hoặc đổi thành 401.

**ADMIN hợp lệ:**

```bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
```

Kỳ vọng HTTP **200**, JSON có `"user":"admin"` và `"role":"admin"`.

**Tính bảo mật của Basic:** Header Authorization chứa credential dạng Base64, **không được mã hóa bí mật**. Dùng **HTTPS** bắt buộc trên mạng thực, không log header Authorization, không dùng mật khẩu demo ngoài localhost và đừng đưa credential thực lên shell history của máy dùng chung. Với API production thường cân nhắc bearer token/OAuth2 và credential rotation tùy kiến trúc.

### 8.8. Browser: xem chuyển hướng và 403

Không có session đăng nhập:

```bash
curl -i http://localhost:8080/app/private
```

Kỳ vọng HTTP **302** (hoặc redirect phù hợp theo cấu hình) kèm `Location` trỏ tới `/login`. Giá trị có thể là path tương đối hoặc absolute URL tùy framework/container/proxy; test nên khẳng định route login, không hardcode host nếu không cần.

Nếu dùng browser, mở:

```text
http://localhost:8080/app/private
```

Bạn sẽ được đưa tới trang login mặc định. Đăng nhập bằng `reader` / `reader-pass`; sau khi login thành công, cấu hình demo chuyển về `/app/private` và hiển thị text có tên user.

Sau khi browser đang đăng nhập `reader`, truy cập:

```text
http://localhost:8080/app/admin
```

Kỳ vọng **403**, không tự redirect lại `/login`. Đăng nhập lại bằng tài khoản `admin` (ví dụ trong phiên browser mới) thì `/app/admin` được phép trả 200.

**Vì sao `curl -L` dễ gây nhầm?** Nếu chạy `curl -L` trên request anonymous, client theo `Location` tới trang login rồi hiển thị body của trang cuối. Bạn có thể thấy HTTP 200 ở trang login mà tưởng endpoint `/app/private` đã cho truy cập. Dùng `curl -i` hoặc `curl -v` **không theo redirect** khi cần điều tra status ban đầu.

## 9. Kiểm thử tự động bằng MockMvc + Spring Security Test

Mục tiêu test là bảo đảm chính sách được thực thi ở layer HTTP/security chứ không chỉ controller. Project đã có dependency `spring-security-test`.

Tạo **`src/test/java/com/example/demo/SecurityStatusApplicationTest.java`**:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityStatusApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousApiGets401AndBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Basic")
            ));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordGets200() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("reader"));
    }

    @Test
    void authenticatedApiUserWithoutRoleGets403()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("admin"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/app/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION, endsWith("/login")
            ));
    }

    @Test
    void anonymousAdminPageAlsoStartsLogin() throws Exception {
        mvc.perform(get("/app/admin"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION, endsWith("/login")
            ));
    }

    @Test
    void authenticatedNonAdminGets403InBrowser()
            throws Exception {
        mvc.perform(get("/app/admin")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserCanSeePrivatePage() throws Exception {
        mvc.perform(get("/app/private")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk());
    }

    @Test
    void loginPostWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validLoginPostWithCsrfRedirectsToPrivatePage()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/app/private"));
    }
}
```

Chạy:

```bash
mvn test
```

Trong project đã được tạo với Maven wrapper, có thể dùng `./mvnw test` hoặc `mvnw.cmd test` trên Windows. Với đúng cấu hình và phiên bản trong `pom.xml`, **11 bài test được kỳ vọng pass**. Đây là các kết quả dự kiến để người học tự chạy, **không phải tuyên bố bài này đã được chạy trên một repository cụ thể**.

**Giải thích một số điểm test:**

- `.with(httpBasic(user, password))` dựng header Basic để filter thực sự xác thực tài khoản trong `UserDetailsService`.
- `.with(user("reader").roles("USER"))` là cơ chế **test helper** dựng một user authenticated trong security context, **không kiểm tra quá trình xác thực mật khẩu**. Dùng nó để test authorization, không dùng thay test Basic password hoặc login POST.
- `.with(csrf())` tạo CSRF token hợp lệ cho POST trong MockMvc. Không có `csrf()` thì POST `/login` không phải một request login hợp lệ theo security policy của demo.
- Với anonymous vào trang admin, `AccessDeniedException` kích hoạt **entry point**, vì vậy redirect login thay vì 403.
- `defaultSuccessUrl("/app/private", true)` làm redirect sau login có mục tiêu cố định, giúp test `redirectedUrl` không phụ thuộc vào request cache.
- Test đầu tiên kiểm tra cả `401` lẫn `WWW-Authenticate`; test thứ sáu kiểm tra **Location tới trang login**; các test khác phân biệt rõ “đã xác thực nhưng thiếu quyền” với “chưa xác thực”.

Nên bổ sung integration tests với **HTTP connector thật**, proxy/ingress và browser nếu ứng dụng có cookie, CORS, OAuth redirect và HTTPS termination. MockMvc kiểm tra filter chain/dispatcher logic, nhưng không chứng minh mọi header được proxy/CDN giữ nguyên.

## 10. CSRF: vì sao có thể nhận 403 dù chưa đăng nhập?

Spring Security mặc định bảo vệ các **HTTP method thay đổi trạng thái** như POST/PUT/PATCH/DELETE bằng CSRF khi ứng dụng Servlet dùng chính sách mặc định. CSRF filter có thể từ chối request **trước khi request đến controller và trước khi bạn nhìn thấy kết quả authorization theo role**.

Ví dụ:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=reader&password=reader-pass
```

Nếu thiếu CSRF token hợp lệ, demo trả **403**, không phải 302 tới trang đăng nhập và cũng không phải 401 sai mật khẩu. Đây là **lỗi bảo vệ CSRF**, không phải tín hiệu tài khoản `reader` không có role.

Với form login thực, GET `/login` mặc định tạo HTML form có hidden token theo integration của Spring Security; browser gửi token lại khi POST. Với custom login page, developer phải bảo đảm token được đưa vào form đúng cách. Sau login/logout, token có thể bị thay/clear theo cơ chế Spring Security; frontend SPA phải lấy token mới theo kiến trúc của mình.

**Không tắt CSRF toàn ứng dụng để biến 403 thành 200.** Cần xác định:

1. Endpoint thuộc API stateless Bearer hay browser session/cookie?
2. Request có gửi CSRF token đúng field/header và cookie/session hợp lệ không?
3. Có CORS preflight OPTIONS bị chặn trước authentication do cấu hình filter chain không?
4. CSRF token có hết hạn, session mới, login/logout hoặc thay đổi cookie path/domain không?
5. Có thực sự là lỗi `AccessDeniedException` do thiếu role thay vì `InvalidCsrfTokenException` hoặc `MissingCsrfTokenException`?

**HTTP Basic không mặc nhiên miễn mọi rủi ro CSRF** chỉ vì nó được gọi là “API”: browser có thể tự gửi lại Basic credentials đã lưu trong một số tình huống. Nếu tắt CSRF trên route Basic có thao tác ghi, hãy đánh giá kỹ mô hình client/credential; tốt hơn dùng bearer token do JavaScript/API client gửi có chủ đích cho stateless APIs khi phù hợp.

## 11. Request cache, session và vòng lặp redirect

Form login thường giữ trạng thái giữa nhiều request bằng session cookie. Khi anonymous yêu cầu trang riêng, `RequestCache` có thể lưu original request rồi sau khi login thành công đưa user trở lại. Nếu cookie session không được gửi lại, browser có thể:

```text
GET /app/private -> 302 /login
GET /login -> 200 login page
POST /login -> đăng nhập
GET /app/private -> lại 302 /login
... lặp ...
```

Nguyên nhân cần xem xét:

- Session cookie không được lưu/gửi vì domain, `Path`, `Secure`, `SameSite`, timeout hoặc browser privacy settings.
- Ứng dụng chạy sau reverse proxy kết thúc TLS, nhưng không xử lý `X-Forwarded-Proto/Host/Prefix` đúng → redirect về `http`/host/path khác.
- Cookie được phát cho domain/path khác với public URL, hoặc nhiều replicas không chia sẻ session store/sticky routing.
- Custom login page `/login` cũng bị rule yêu cầu authenticated → tự redirect về chính mình.
- Custom authentication success handler bị tạo redirect sai hoặc stale saved request.
- CORS/cross-site credentials và cookie policy không tương thích với frontend SPA.

**Không sửa redirect loop bằng cách thay mọi rule thành `permitAll()`.** Hãy đo chain nào matched request, status/Location từng hop, `Set-Cookie` và `Cookie`, session persistence rồi sửa đúng ranh giới.

Trong ví dụ, API chain sử dụng `STATELESS` và không có request cache; browser chain dùng form login và session. Không được áp `SessionCreationPolicy.STATELESS` vào browser chain rồi kỳ vọng session login mặc định tồn tại qua các request.

## 12. Tùy chỉnh response 401/403 cho REST API

Một sản phẩm có thể muốn body JSON thống nhất:

```json
{
  "status": 403,
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền với tài nguyên này"
}
```

Với Spring Security, nơi thích hợp là:

- **`AuthenticationEntryPoint`**: xử lý khi cần bắt đầu xác thực — trả 401 (thêm challenge thích hợp theo scheme), không redirect cho route API.
- **`AccessDeniedHandler`**: xử lý lỗi thiếu quyền của caller đã authenticated — trả 403.
- **`@ControllerAdvice`**: xử lý validation, lỗi nghiệp vụ, lỗi server từ controller/service; không xem nó là cơ chế thay thế chắc chắn cho filter-level security exceptions.

Snippet sau minh họa **chỉ cách định tuyến response**, chưa có JSON serialization/security scheme đầy đủ:

```java
// Snippet minh họa bên trong SecurityFilterChain API.
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint((request, response, error) -> {
        response.setStatus(401);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"status\":401,\"code\":\"AUTH_REQUIRED\"}"
        );
    })
    .accessDeniedHandler((request, response, error) -> {
        response.setStatus(403);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"status\":403,\"code\":\"ACCESS_DENIED\"}"
        );
    })
);
```

**Quan trọng:** đoạn này **không được tự copy vào Basic/Bearer chain production** mà không giữ đúng `WWW-Authenticate` challenge. Ví dụ cố tình không phải cấu hình hoàn chỉnh; nếu dùng custom entry point cho Basic, hãy delegate/sinh challenge đúng `Basic realm="..."`, hoặc cấu hình error body quanh entry point phù hợp. Với Bearer, tuân thủ quy tắc challenge/error của OAuth2. Đừng tiết lộ password sai cụ thể, token nội bộ, stack trace hoặc danh sách quyền nhạy cảm vào response.

Tương tự, nếu muốn trang 403 riêng cho browser:

```java
// Snippet trong browser security chain.
http.exceptionHandling(ex -> ex
    .accessDeniedPage("/access-denied")
);
```

Ứng dụng cần tự cung cấp route/view `/access-denied` và policy `permitAll()` hoặc quyền phù hợp để user nhìn thấy trang đó. Không redirect tất cả 403 tới login: user đã xác thực nhưng không có role cần nhận thông báo thiếu quyền, không phải bị buộc login vô hạn.

## 13. CORS, 401/403 và lỗi trình duyệt

Frontend SPA chạy tại `https://ui.example.com`, API tại `https://api.example.com` là **cross-origin**. Browser có thể gửi request `OPTIONS` preflight trước request chính. Nếu security filter yêu cầu authentication trước CORS processing, request preflight thường **không có session cookie/Authorization theo cách bạn mong đợi**, nên bị chặn; console có thể báo CORS error, 401/403 hoặc `Failed to fetch`.

Cần phân biệt:

- **401 từ API:** server đã nhận request chính và yêu cầu authentication; có thể body/headers bị browser không cho đọc do CORS policy.
- **403 từ CSRF:** request thay đổi trạng thái thiếu token (không đồng nghĩa CORS).
- **CORS failure:** browser từ chối cung cấp response cho JavaScript vì headers/preflight không đúng, dù curl gọi URL vẫn thành công.
- **Redirect tới HTML login:** có thể đi sai origin/host và browser chặn; frontend nhận HTML thay JSON nếu redirect được theo.

Chính sách CORS chỉ allowlist những public origins được phép, xử lý preflight **trước authentication** bằng Spring Security CORS integration đúng cách; không dùng `Access-Control-Allow-Origin: *` với credentialed requests. CORS **không thay thế authorization** và không ngăn curl/server-to-server gọi API.

Khi API sử dụng cookie authentication, frontend cần xử lý `credentials`/SameSite/Secure và CSRF policy. Khi API dùng Bearer token, frontend cần gửi `Authorization` đúng cách, bắt 401 để yêu cầu đăng nhập/làm mới token theo policy, bắt 403 để hiển thị thiếu quyền; **không tự retry vô hạn**.

## 14. API client nên xử lý 401, 403 và redirect thế nào?

Pseudo-code ở frontend:

```javascript
async function loadAdminData() {
  const response = await fetch("/api/admin", {
    headers: { "Accept": "application/json" },
    redirect: "manual"
  });

  if (response.status === 401) {
    // Người dùng cần xác thực lại hoặc credential hết hạn.
    // Không tự lặp refresh vô hạn.
    return { action: "AUTHENTICATE" };
  }

  if (response.status === 403) {
    // Không đủ quyền; thông báo và không tự gán role.
    return { action: "SHOW_FORBIDDEN" };
  }

  if (response.status >= 300 && response.status < 400) {
    // API thường không nên gửi HTML login redirect.
    return { action: "UNEXPECTED_REDIRECT" };
  }

  if (!response.ok) {
    return { action: "HANDLE_OTHER_HTTP_ERROR" };
  }

  return await response.json();
}
```

Đây là **ví dụ logic minh họa**, không phải frontend production đầy đủ; endpoint Basic ở bài thực hành yêu cầu Authorization header hoặc browser credentials phù hợp, và cross-origin `redirect: "manual"` có các hạn chế theo Fetch/CORS. Trong SPA, đừng gán mọi 403 thành “đăng nhập lại”, vì user có thể login hợp lệ nhưng không có quyền và việc lặp login không giải quyết được.

Với request sử dụng JSON error body, kiểm tra `Content-Type` trước khi parse; không giả định mọi 401/403 đều có JSON. Xác thực thành công còn phụ thuộc cookie/token refresh, thời hạn và account state. Mặc định xử lý retry phải có số lần/timeout/circuit-breaker phù hợp.

## 15. Bảo mật và các tình huống ngoài lộ trình cơ bản

### 15.1. 404 có thể là chính sách che sự tồn tại

Một người chưa được phép xem `/documents/123` đôi khi được trả **404** để tránh xác nhận tài liệu 123 tồn tại. Điều này **không đồng nghĩa mất phân quyền**; trước khi trả dữ liệu, vẫn phải kiểm tra owner/tenant. Chính sách 403/404 cần thống nhất giữa REST endpoints và logs, và không tạo side channel dễ phân biệt chỉ dựa vào timing/error messages.

### 15.2. Sau đăng nhập, thiếu quyền vì role/authority bị thay đổi

Nếu role thay đổi trong database nhưng user đang có session cũ, security context có thể giữ authorities cũ cho tới khi refresh/login lại hoặc cơ chế đồng bộ được kích hoạt. Trước khi yêu cầu user login lặp lại, kiểm tra quyền hiện tại và cache/session policy. Với token JWT tự chứa scopes, token cũ có thể phản ánh quyền tại thời điểm phát token; server cần thiết kế TTL/revocation/policy phù hợp.

### 15.3. Lỗi 403 nhưng user đã “được gán ADMIN”

Spring Security `hasRole("ADMIN")` mặc định tìm authority `ROLE_ADMIN`. Nếu ứng dụng tự lưu authority `ADMIN` không prefix, check sẽ không khớp. Ngược lại, nếu viết `hasAuthority("ADMIN")` thì phải có đúng authority `ADMIN`. Cần xem chính xác `GrantedAuthority` được xây từ IdP, database và conversion của JWT scopes/roles.

Với method security:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report downloadInternalReport() {
    // ...
}
```

Đây là snippet minh họa, cần `@EnableMethodSecurity` ở cấu hình và `Report` được định nghĩa. Không tự tin rằng rule URL đã đủ bảo vệ thao tác được gọi từ background job, message consumer hoặc service khác; đặt authorization ở tầng phù hợp với threat model.

### 15.4. Sai filter chain vì matcher hoặc thứ tự

Trong nhiều `SecurityFilterChain`, **chain đầu tiên phù hợp** được chọn. Nếu một catch-all chain đứng trước `/api/**`, API có thể bị form login redirect 302 thay vì Basic 401. Nếu không có fallback chain, một route mới có thể không được Spring Security bảo vệ. Kiểm tra thứ tự `@Order`, `securityMatcher` và URL thực sau reverse-proxy rewrite.

### 15.5. User được xác thực nhưng có 403 do CSRF

Đừng quy 403 luôn cho authority. Xác minh:

- Request là GET hay POST/PUT/PATCH/DELETE?
- Có session/cookie và CSRF token không?
- Token còn hợp lệ sau login/logout/session timeout không?
- Custom filter có đọc body, thay token, hoặc request đi qua proxy sửa headers?
- Handler trả `InvalidCsrfTokenException`, `MissingCsrfTokenException` hay `AccessDeniedException` do quyền?

Trong test, tạo **hai case tách biệt**: user có role nhưng POST thiếu CSRF để thấy 403 do CSRF; user có token hợp lệ nhưng thiếu role để thấy 403 do authorization.

### 15.6. Dùng status đúng, không lộ thông tin nhạy cảm

Response 401/403 không nên chứa mật khẩu, token, cookie, stack trace, tên bảng database, role nội bộ cần giữ kín hoặc toàn bộ chuỗi authorization policy. Logging nên ghi request ID, route, auth scheme, status và loại sự kiện, nhưng **không** log raw Authorization header/credential. Đối với 401 Basic, thông điệp nên đủ cho client xử lý nhưng không tiết lộ tài khoản có tồn tại hay không.

### 15.7. HTTPS và reverse proxy

Đối với Basic và form login, HTTPS là bắt buộc ngoài local dev. Nếu TLS kết thúc ở proxy, cấu hình trusted forwarded headers và network isolation để Spring biết public scheme/host; nếu không, `Location` có thể thành HTTP/internal host, cookie Secure/Path sai và browser login loop. **Không tin `X-Forwarded-*` từ Internet trực tiếp**.

## 16. Quy trình chẩn đoán theo tình huống

| Triệu chứng | Câu hỏi đầu tiên | Cách kiểm tra |
| --- | --- | --- |
| `GET /api/profile` trả 302 `/login` | API có đi vào browser filter chain không? | Kiểm tra `@Order`, `securityMatcher("/api/**")`, entry point |
| `GET /api/profile` trả 401 | Có gửi Basic/Bearer credential đúng không? | Xem `WWW-Authenticate`, request headers, auth logs đã loại bí mật |
| `GET /api/admin` với USER trả 403 | User có `ROLE_ADMIN` không? | Kiểm tra authorities và `hasRole`/`hasAuthority` |
| `GET /app/private` anonymous trả 302 | Đây có phải browser form login theo thiết kế không? | Xem `Location: /login` |
| Login POST trả 403 | Có thiếu CSRF token/session không? | Kiểm tra GET login form và POST token/cookie |
| Login thành công mà lại về `/login` | Session cookie có được lưu/gửi? | Xem `Set-Cookie`/`Cookie`, proxy scheme/host/path |
| Role ADMIN trong DB nhưng vẫn 403 | Authority mapping có `ROLE_` prefix? | Review GrantedAuthority, principal, token scopes |
| 401 chỉ khi gọi qua browser JS | Có CORS/preflight/credentials mismatch? | DevTools Network, OPTIONS, Access-Control headers |
| Client API parse JSON thất bại | Có phải nhận trang HTML login do redirect? | Tắt follow redirects, kiểm tra initial HTTP status |
| `403` đến từ Nginx/gateway | Spring có nhận request không? | Edge access logs và backend logs theo request ID |
| Endpoint không tồn tại nhưng trả 401 | Route có bị security chặn trước mapping không? | Authenticated request tới URL tương tự; phân biệt 401/404 |
| Sau logout vẫn truy cập được API Basic | Basic credentials còn được client gửi lại? | Kiểm tra request Authorization; logout session khác Basic |
| Logout POST trả 403 | CSRF có được gửi không? | Kiểm tra token, method và filter chain |

### Checklist release

- [ ] API bảo vệ: anonymous → 401, credential sai → 401, credential đúng thiếu quyền → 403, đúng quyền → 2xx.
- [ ] Form-login web: anonymous vào private → 302 tới login; authenticated thiếu quyền → 403.
- [ ] POST /login và các form state-changing có CSRF token; thiếu/sai token bị từ chối.
- [ ] API không tự chuyển thành HTML login page ngoài ý muốn.
- [ ] `WWW-Authenticate` đúng scheme/realm/scopes theo contract Basic/Bearer.
- [ ] Có fallback SecurityFilterChain; thứ tự `@Order` và `securityMatcher` được test.
- [ ] Đã kiểm tra role prefix, authority và object-level/tenant authorization.
- [ ] CORS/preflight, HTTPS, proxy headers, session cookie và OAuth redirect được kiểm tra ở môi trường production-like.
- [ ] Test logout/session invalidation, token expiry, account disabled và credential rotation.
- [ ] Error body không tiết lộ secrets, và logs có correlation ID nhưng không lộ credentials.
- [ ] Spring Boot/Spring Security dùng dòng còn hỗ trợ và bản vá mới, không copy mật khẩu demo vào production.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** User chưa đăng nhập gọi `GET /api/admin`, endpoint có `hasRole("ADMIN")`. Phải là 403 vì thiếu role?  
**Trả lời:** Không. Spring Security thường nhận diện anonymous và gọi entry point; với Basic là 401, với form login là redirect 302.

**Câu 2.** `reader` đăng nhập thành công rồi gọi `GET /api/admin` nhưng không có `ROLE_ADMIN`. Status thường là gì?  
**Trả lời:** 403 Forbidden; xác thực đã thành công nhưng không đủ quyền.

**Câu 3.** Tại sao `curl -L` có thể khiến bạn tưởng API trả 200?  
**Trả lời:** Client tự theo 302 tới trang login và hiển thị response cuối (200 của login page), không phải status đầu tiên của API.

**Câu 4.** POST /login có đúng username/password nhưng thiếu CSRF token. 403 có chứng minh user không có role không?  
**Trả lời:** Không. CSRF filter có thể từ chối request trước khi quá trình login/authorization được xử lý.

**Câu 5.** 401 API Basic cần header nào?  
**Trả lời:** `WWW-Authenticate` với challenge Basic thích hợp, theo HTTP Basic/HTTP semantics, trừ những ngoại lệ hành vi client/header đã cấu hình.

**Câu 6.** `hasRole("ADMIN")` tìm authority mặc định nào?  
**Trả lời:** `ROLE_ADMIN`. `hasAuthority("ADMIN")` mới so khớp chuỗi `ADMIN` đúng nguyên văn.

**Câu 7.** Nếu API stateless, có thể đặt `SessionCreationPolicy.STATELESS` trên mọi filter chain kể cả browser form login không?  
**Trả lời:** Không nếu browser cần session để lưu trạng thái đăng nhập. Cần phân biệt API chain và browser chain.

**Câu 8.** CORS error và 401 từ API có phải cùng lỗi không?  
**Trả lời:** Không. CORS là cơ chế hạn chế đọc response của browser; 401 là HTTP authentication response. Chúng có thể xuất hiện đồng thời và che lấp nhau.

**Câu 9.** 403 luôn phải trả 403, không bao giờ được trả 404?  
**Trả lời:** Không. Một số API chọn 404 để tránh lộ sự tồn tại của object, nhưng phải giữ authorization thật và áp dụng nhất quán.

**Câu 10.** Khi login thành công rồi redirect sang HTTP/internal host, có nên tắt Secure cookie để hết lỗi?  
**Trả lời:** Không. Sửa HTTPS public URL, trusted proxy headers, Location và cookie policy; giữ cookie Secure trong production.

## 18. Tài liệu chính thức và hướng tự học

- Spring Security 6.5 — *Security Architecture / ExceptionTranslationFilter*: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — *Authentication Architecture*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — *HTTP Basic Authentication*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — *Form Login*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5 — *Multiple HttpSecurity / SecurityFilterChain*: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — *CSRF Protection*: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — *HTTP Bearer Token Authentication*: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security — *Testing Spring MVC*: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — *Spring Security*: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- RFC 9110 — *HTTP Semantics, 401 and 403*: https://www.rfc-editor.org/rfc/rfc9110#section-15.5
- RFC 6750 — *OAuth 2.0 Bearer Token Usage*: https://www.rfc-editor.org/rfc/rfc6750

**Kết luận:** Đừng gộp “chưa đăng nhập” và “đăng nhập nhưng không có quyền”. Trong Spring Security, **AuthenticationEntryPoint** quyết định 401/challenge hoặc 302/login khi cần bắt đầu xác thực; **AccessDeniedHandler** xử lý từ chối quyền, thường là 403. Với CSRF, API gateway, CORS hay proxy, 403/302 có thể có nguyên nhân khác. Hãy dùng những filter chain có phạm vi rõ, bảo toàn CSRF/session policy, kiểm thử **401 + challenge**, **403**, **302 + Location** và các nhánh 2xx để giao diện web và REST API đều có hành vi chính xác.