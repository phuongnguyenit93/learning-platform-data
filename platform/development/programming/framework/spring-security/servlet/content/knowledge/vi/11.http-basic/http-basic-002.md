# BasicAuthenticationFilter và AuthenticationEntryPoint trong Spring Security Servlet

> **Bối cảnh:** Spring Security 6 trên Servlet stack, Java 17+; ví dụ Spring Boot 3.3.5 giúp chạy ứng dụng Tomcat nhúng. Chủ đề chính là cách `BasicAuthenticationFilter` chuyển HTTP Basic credentials thành yêu cầu xác thực và cách `AuthenticationEntryPoint` trả lời client bằng **HTTP 401 / WWW-Authenticate**. Phân biệt rõ với form login, authorization, CSRF và cơ chế phiên.

## 1. HTTP Basic: đường đi của username và mật khẩu

Với HTTP Basic, client gửi header `Authorization` có scheme `Basic` cùng một chuỗi Base64 biểu diễn `username:password`:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic dXNlcjpwYXNz
```

Trong ví dụ cú pháp trên, `dXNlcjpwYXNz` là Base64 của `user:pass`. Base64 **không phải mã hóa bảo mật**: bất kỳ ai đọc được header đều có thể khôi phục mật khẩu. **HTTPS/TLS là bắt buộc** trong môi trường triển khai thực tế; không lưu header hoặc decoded password vào log.

HTTP Basic có hai vai trò tách biệt:

1. **`BasicAuthenticationFilter`**: bộ lọc xác thực. Nó nhận diện Basic header, đọc username/password, tạo `Authentication` chưa xác thực, gọi `AuthenticationManager`. Thành công thì thiết lập `SecurityContext` của request; thất bại thì dùng authentication entry point phù hợp.
2. **`AuthenticationEntryPoint`**: hợp đồng **bắt đầu yêu cầu xác thực** bằng HTTP response. Implementation `BasicAuthenticationEntryPoint` thường trả **401 Unauthorized** và `WWW-Authenticate: Basic realm="..."`, giúp client biết phải gửi Basic credentials.

Bên cạnh đó, `AuthorizationFilter`/authorization policy xác định người đã xác thực **được truy cập tài nguyên nào**. Đúng mật khẩu nhưng thiếu role có thể dẫn tới **403 Forbidden**; đó không phải lỗi của `PasswordEncoder` hay dấu hiệu Basic filter chưa chạy.

### So sánh nhanh với đăng nhập biểu mẫu

| Nội dung | HTTP Basic | Form login |
| --- | --- | --- |
| Credentials đi qua | `Authorization: Basic ...` | `POST /login` với username/password |
| Filter tiêu biểu | `BasicAuthenticationFilter` | `UsernamePasswordAuthenticationFilter` |
| Cần xác thực khi truy cập tài nguyên | Thường 401 + Basic challenge | Thường 302 redirect tới trang `/login` |
| Cách client duy trì danh tính | Gửi credentials mỗi request hoặc theo behavior của client/cấu hình | HTTP session/cookie phổ biến |
| Trải nghiệm | CLI, API đơn giản, hệ thống legacy | Trình duyệt và form HTML |
| Truyền password qua HTTP thuần | **Không an toàn** | **Không an toàn** |

Đừng chọn entry point form login cho REST client chỉ vì hệ thống đã có trang `/login`: API sẽ nhận redirect/HTML thay vì challenge đúng loại.

## 2. Sơ đồ Spring Security Servlet khi có Basic header

```text
HTTP request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy -> SecurityFilterChain
                                                |
                                                v
                                       BasicAuthenticationFilter
                                                |
                          +---------------------+-------------------+
                          |                                         |
                 Có Basic Authorization?                       Không có
                          |                                         |
                          v                                         v
               Đọc username/password                     Bỏ qua authenticate,
                          |                                tiếp tục filters
                          v                                         |
           UsernamePasswordAuthenticationToken                      v
                (chưa authenticated)                          AuthorizationFilter
                          |                                         |
                          v                              Endpoint yêu cầu login?
             AuthenticationManager                                 |
                          |                                         v
             ProviderManager/providers                    ExceptionTranslationFilter
                          |                                         |
             +------------+--------------+                          v
             |                           |                  AuthenticationEntryPoint
       Thành công                     Thất bại              (thường 401 challenge)
             |                           |
             v                           v
      Authentication đã        AuthenticationException
        xác thực                         |
             |                           v
             v                    BasicAuthenticationFilter
      SecurityContext                 xử lý failure
             |                           |
             v                           v
       AuthorizationFilter        AuthenticationEntryPoint
             |                    (thường 401 challenge)
      +------+-------+
      |              |
    Đủ quyền       Thiếu quyền
      |              |
   Controller      HTTP 403
```

Hai nhánh 401 có bản chất khác nhau:

- **Không gửi Basic header**: filter có thể không gọi manager. Về sau một request anonymous bị rule `authenticated()` từ chối; `ExceptionTranslationFilter` quyết định gọi `AuthenticationEntryPoint`.
- **Đã gửi username/password sai**: Basic filter gọi manager, nhận `AuthenticationException`, rồi trực tiếp dùng entry point hoặc cơ chế xử lý failure đã cấu hình.

Điều này giúp debug chính xác: không có header thì không nên sửa logic so mật khẩu; header có nhưng password sai thì xem authentication provider; password đúng nhưng 403 thì xem authorities/rule/CSRF.

## 3. BasicAuthenticationFilter thực hiện những bước nào?

### 3.1. Nhận diện và đọc Authorization

Filter tìm một header `Authorization` phù hợp với HTTP Basic. Chuỗi phía sau `Basic ` được giải mã Base64 để có username/password ngăn bởi dấu hai chấm đầu tiên:

```text
username:password
         |
         v
    Base64 encode
         |
         v
Authorization: Basic <encoded-value>
```

Nếu username là `linh` và password là `demo123`, `curl --user linh:demo123` có thể tạo Basic header giúp thử luồng. **Không viết literal Base64 thực tế** vào tài liệu vận hành hoặc log production.

Một số lưu ý chuẩn HTTP Basic:

- Username không nên chứa dấu hai chấm `:` vì dấu hai chấm đầu tiên phân tách username/password; password về mặt cú pháp có thể chứa `:`.
- Base64 hợp lệ về cú pháp **chưa** chứng minh credentials đúng; provider vẫn phải kiểm tra username và mật khẩu.
- Encoding của ký tự không ASCII cần sự tương thích giữa client/server (xem quy ước charset của HTTP Basic, RFC 7617); không giả định mọi client xử lý Unicode giống nhau.
- Header dùng scheme khác, chẳng hạn `Bearer`, không được `BasicAuthenticationFilter` tự kiểm chứng như JWT. Nếu ứng dụng cần Bearer, phải dùng filter/provider/decoder đúng cơ chế.
- Header Basic malformed hoặc sai credentials có thể đưa đến lỗi xác thực và challenge; hành vi cụ thể tùy converter và cấu hình.

**Đặc biệt:** endpoint được đánh dấu `permitAll()` không làm cho mọi authentication filter biến mất. Nếu client cố gửi **Basic header sai** tới một URL công khai, Basic filter vẫn có thể thử authenticate trước khi đến rule `permitAll()`, dẫn đến 401.

### 3.2. Tạo Authentication chưa được tin

Minh họa tương đương:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                usernameFromHeader, passwordFromHeader);
Authentication result = authenticationManager.authenticate(request);
```

Đây là **fragment giải thích** (biến `usernameFromHeader`, `passwordFromHeader`, `authenticationManager` phải được cung cấp), không phải mã nguồn nội bộ từng dòng của filter. `Authentication` request thường có `isAuthenticated()==false`, principal là username ban đầu, credentials là mật khẩu và authorities chưa được cấp.

`AuthenticationManager` (thường là `ProviderManager`) chọn `AuthenticationProvider` hỗ trợ `UsernamePasswordAuthenticationToken`. Với tài khoản lưu theo username/password, `DaoAuthenticationProvider` sử dụng `UserDetailsService` và `PasswordEncoder.matches(raw, storedHash)` để kiểm chứng. Role/authority của result phải đến từ **nguồn tin cậy**, không từ JSON hay header do client tự khai.

### 3.3. Khi xác thực thành công

`AuthenticationManager.authenticate(...)` trả về `Authentication` đáng tin cậy, thường có `isAuthenticated()==true`, principal và các authorities. Filter tạo/cập nhật `SecurityContext` cho request, để các filter sau và controller nhìn thấy identity.

Cần lưu ý:

- `BasicAuthenticationFilter` không quyết định tài nguyên nào cho `ROLE_ADMIN`; rule `authorizeHttpRequests` kiểm tra quyền.
- `ProviderManager` thường cố xóa credential trong result khi object hỗ trợ `CredentialsContainer`. Không dựa vào `getCredentials()` để đọc lại password sau authenticate, và không log raw credentials kể cả trước lúc xóa.
- Trong một số cấu hình, Basic filter có thể kiểm tra authentication đã có ở context để tránh xác thực lại vô ích; nhưng đừng suy ra Basic **tự động tạo login session** hoặc bảo đảm stateless chỉ từ `httpBasic()`.
- `SecurityContextHolder` đại diện cho context hiện tại. Việc context được lưu qua các requests hay không là vấn đề của `SecurityContextRepository` và session policy, không phải tự động do interface `AuthenticationManager`.

### 3.4. Khi xác thực thất bại

Nếu provider ném `BadCredentialsException`, `DisabledException`, `LockedException` hoặc một `AuthenticationException` khác, filter không được gắn result như user đã được xác thực. Trong flow Basic thông thường, entry point tạo 401 challenge.

Một custom instance của `BasicAuthenticationFilter` có thể được cấu hình khác, chẳng hạn cơ chế xử lý `ignoreFailure`; vì vậy chỉ nên kết luận từ response/filter chain thực tế, không giả định mọi cách tạo filter đều giống nhau.

## 4. AuthenticationEntryPoint và BasicAuthenticationEntryPoint

Hợp đồng Servlet có dạng:

```java
public interface AuthenticationEntryPoint {
    void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException;
}
```

Đây là **chữ ký rút gọn** để giải thích; interface đã tồn tại trong `org.springframework.security.web`. Ở Spring Security 6, Servlet APIs dùng **`jakarta.servlet.*`**, không còn `javax.servlet.*`.

`commence()` không trả `Authentication`; nó dùng `HttpServletResponse` để phát tín hiệu HTTP bắt đầu xác thực, ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

Trong HTTP Basic:

- **401** nghĩa chưa có authentication hợp lệ đáp ứng yêu cầu. Mã này có thể xuất hiện khi **không gửi credentials** hoặc **credentials sai**.
- **`WWW-Authenticate`** báo challenge/scheme cho client, giúp công cụ HTTP hoặc browser biết phải gửi loại credentials nào.
- **`realm`** là tên phạm vi bảo vệ trong challenge, **không phải role**. Realm `Learning API` không cấp quyền `ROLE_ADMIN` và không thay thế `UserDetailsService`.
- `BasicAuthenticationEntryPoint` là một implementation thích hợp cho Basic; `LoginUrlAuthenticationEntryPoint` lại dành cho hướng chuyển tới trang login form.

Có thể định cấu hình realm qua Java DSL:

```java
http.httpBasic(basic -> basic.realmName("Learning API"));
```

Đoạn này nằm trong method `SecurityFilterChain`, không tạo “realm database”. Nó thay tên realm cho Basic challenge mặc định trong cấu hình tương ứng.

### 4.1. 401 khác 403 và 302

| Response | Trường hợp điển hình | Nguyên nhân |
| --- | --- | --- |
| **200** | Credentials đúng và đủ quyền; hoặc endpoint công khai | Request được xử lý |
| **401** | Anonymous vào `/api/me` | `ExceptionTranslationFilter` gọi entry point khi rule yêu cầu authentication |
| **401** | Đã gửi Basic header nhưng password sai | Basic filter/manager/provider thất bại, entry point tạo challenge |
| **403** | Password đúng nhưng thiếu `ROLE_ADMIN` | `AuthorizationFilter` và access-denied handling |
| **403** | POST thiếu CSRF token khi CSRF bật | `CsrfFilter` |
| **302** | Form login chuyển tới `/login` | Login URL entry point, không phải Basic response chuẩn |

HTTP status không tự cho biết chính xác exception nào. Cần xem filter, AuthenticationManager, authorization rule, handler, request headers và context.

### 4.2. Hai cách đi đến Basic challenge

**Không có Authorization:**

```text
GET /api/me, không có Basic header
  -> BasicAuthenticationFilter bỏ qua authenticate
  -> AuthorizationFilter chặn anonymous
  -> ExceptionTranslationFilter gọi AuthenticationEntryPoint
  -> 401 + WWW-Authenticate: Basic realm="Learning API"
```

**Basic header có mật khẩu sai:**

```text
GET /api/me + Basic credentials không hợp lệ
  -> BasicAuthenticationFilter thử authenticate
  -> AuthenticationManager/DaoAuthenticationProvider
  -> BadCredentialsException
  -> BasicAuthenticationFilter xử lý failure
  -> AuthenticationEntryPoint
  -> 401 + WWW-Authenticate: Basic realm="Learning API"
```

**Đã xác thực nhưng thiếu role:** authentication thành công, `AuthorizationFilter` từ chối và **403**, không phải “bắt nhập password lần nữa”.

## 5. Ví dụ runnable: ứng dụng Servlet với HTTP Basic

Ta xây một ứng dụng Spring Boot 3.3.5 + Java 17+, dùng Spring MVC (Servlet), Spring Security và HTTP Basic. Ba endpoints:

| Endpoint | Yêu cầu | Kết quả khi đúng |
| --- | --- | --- |
| `GET /api/public` | Công khai | `public:ok` |
| `GET /api/me` | `authenticated()` | `me:<username>` |
| `GET /api/admin` | `hasRole("ADMIN")` | `admin:<username>` |

Dùng hai account **chỉ để thực hành local**:

| Username | Mật khẩu | Role |
| --- | --- | --- |
| `linh` | `demo123` | `ROLE_USER` |
| `admin` | `demo123` | `ROLE_ADMIN` |

Cấu trúc file:

```text
spring-basic-demo/
├── pom.xml
└── src/main/java/example/basic/
    ├── BasicDemoApplication.java
    ├── SecurityConfig.java
    └── ApiController.java
```

### 5.1. Tạo pom.xml

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
    <artifactId>spring-basic-demo</artifactId>
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

### 5.2. BasicDemoApplication.java

```java
package example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig.java

```java
package example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        // Bật BasicAuthenticationFilter và entry point tương ứng.
        http.httpBasic(basic -> basic.realmName("Learning API"));

        // Không dựa vào HTTP session để giữ SecurityContext giữa các request.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        // API không cần lưu saved request để redirect về trang login HTML.
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache())
        );

        // Giữ CSRF mặc định; bài demo chỉ dùng GET.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(linh, admin);
    }
}
```

Phân tích các lựa chọn:

1. `httpBasic` bật filter xác thực từ header và Basic entry point. `realmName("Learning API")` đặt tên challenge.
2. `UserDetailsService` trả user có mật khẩu đã hash qua BCrypt. Spring Security cấu hình provider username/password thích hợp; filter gọi manager, không tự so mật khẩu.
3. `SessionCreationPolicy.STATELESS` có nghĩa Spring Security không tạo/dùng HTTP session để lấy/lưu `SecurityContext` **cho cơ chế này**; nó không chứng minh toàn hệ thống không component nào từng tạo session.
4. `NullRequestCache` tránh lưu URL cần đăng nhập để đưa qua form login rồi quay về. Basic dành cho HTTP client nhận 401 và tự gửi credentials, không cần saved request HTML.
5. `anyRequest().denyAll()` tránh mở ngoài dự kiến các URL không được liệt kê. `requestMatchers` theo method giúp hiểu rõ phạm vi GET.
6. CSRF được giữ mặc định. Các GET endpoints phù hợp thử nghiệm Basic; nếu thêm POST/PUT/PATCH/DELETE, cần quyết định CSRF theo cách clients gửi credentials, không tắt mù.
7. Ví dụ chỉ có một `SecurityFilterChain` bao phủ mọi URL; trong ứng dụng trộn API/web thật có thể tách chains ở mục 9.

**Lưu ý:** Không cần tự tạo `AuthenticationManager` ở ví dụ đơn giản vì Spring Security có thể xây manager từ `UserDetailsService`/`PasswordEncoder` phù hợp. Khi ứng dụng có nhiều providers hoặc tự cấu hình managers, phải kiểm tra đúng wiring giữa Basic filter → manager → provider.

### 5.4. ApiController.java

```java
package example.basic;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicData() {
        return "public:ok";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

`Authentication` trong controller đến từ `SecurityContext` của request sau khi filter xác thực; `hasRole("ADMIN")` được kiểm tra **trước khi controller chạy**. `@RestController` trả chuỗi để dễ so stdout, không cần frontend/template.

### 5.5. Chạy

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Với cấu hình mặc định, Tomcat phục vụ tại `http://localhost:8080`. Trong thực tế chỉ triển khai HTTP Basic qua **HTTPS**; địa chỉ HTTP ở đây là local học tập.

## 6. Thử cả ba trạng thái 200, 401, 403 bằng curl

### 6.1. Public không cần Authorization: 200

```bash
curl -s http://localhost:8080/api/public
```

Kết quả body kỳ vọng:

```text
public:ok
```

`BasicAuthenticationFilter` bỏ qua xác thực khi không có Basic header và rule `permitAll()` cho phép request.

### 6.2. Tài nguyên cần login nhưng không gửi header: 401

```bash
curl -i http://localhost:8080/api/me
```

Kỳ vọng HTTP **401**. Response thường có challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

Đó là hai dòng liên quan, **không phải toàn bộ header byte-for-byte**. Filter Basic không có dữ liệu để authenticate; sau đó authorization từ chối anonymous và `ExceptionTranslationFilter` gọi Basic entry point.

### 6.3. Có Basic nhưng mật khẩu sai: 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user linh:wrong-password http://localhost:8080/api/me
```

Kết quả kỳ vọng:

```text
401
```

`curl --user` tạo Basic header. Lần này `BasicAuthenticationFilter` thực sự đưa `UsernamePasswordAuthenticationToken` đến `AuthenticationManager`; provider phát hiện password không hợp lệ; filter/entry point tạo 401.

### 6.4. Username/password hợp lệ: 200

```bash
curl -s --user linh:demo123 http://localhost:8080/api/me
```

Kết quả:

```text
me:linh
```

Client phải cung cấp credentials ở request mới; `STATELESS` không làm request tiếp theo tự authenticated chỉ vì request trước đã 200.

### 6.5. Đã authenticated nhưng thiếu ROLE_ADMIN: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user linh:demo123 http://localhost:8080/api/admin
```

Kết quả:

```text
403
```

`linh` được provider xác thực, nhưng chỉ có `ROLE_USER`, không đạt `hasRole("ADMIN")`. Đây là **authorization failure**, không phải authentication failure.

### 6.6. ADMIN hợp lệ: 200

```bash
curl -s --user admin:demo123 http://localhost:8080/api/admin
```

Kết quả:

```text
admin:admin
```

Không cần lưu form session cho Basic demo; `curl` gửi Basic header trong mỗi lần gọi.

### 6.7. Bảng kiểm tra kỳ vọng

| Request | Basic filter | Phân quyền | Status/body |
| --- | --- | --- | --- |
| `GET /api/public` không header | Không authenticate | `permitAll` | 200 `public:ok` |
| `GET /api/me` không header | Không authenticate | Chặn anonymous | 401 + challenge |
| `GET /api/me` với `linh:wrong-password` | Authenticate thất bại | Không cấp authenticated context | 401 + challenge |
| `GET /api/me` với `linh:demo123` | Thành công | `authenticated()` | 200 `me:linh` |
| `GET /api/admin` với `linh:demo123` | Thành công | Thiếu `ROLE_ADMIN` | 403 |
| `GET /api/admin` với `admin:demo123` | Thành công | Đủ `ROLE_ADMIN` | 200 `admin:admin` |
| `GET /api/public` nhưng chủ động gửi Basic sai | Có thể thử xác thực rồi fail | `permitAll` không tắt auth filter | Có thể 401 |
| POST API mà không có CSRF token | Phụ thuộc credentials | CSRF filter | Thường 403 |

Không suy từ `permitAll()` rằng client có thể gửi một Basic Authorization header sai mà vẫn luôn nhận 200: authentication filter có thể quyết định thất bại **trước** khi authorization rule được áp dụng.

## 7. Session, SecurityContext và browser cache: đừng nhầm

HTTP Basic thường gửi credentials lặp lại thay vì tạo một phiên đăng nhập form. Nhưng **`httpBasic()` không tự bảo đảm tất cả ứng dụng stateless**. Một hệ thống có thể còn session login, request cache, remember-me hoặc custom filters.

Ví dụ đã chủ động cấu hình:

```java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
http.requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
```

`STATELESS` nghĩa Spring Security không dùng `HttpSession` để giữ `SecurityContext` giữa các requests ở chain được cấu hình; **trong một request**, `SecurityContextHolder` vẫn có thể chứa authentication để phục vụ authorization/controller. `NullRequestCache` cũng tránh ý tưởng redirect về một saved request dùng cho form login.

Một số browser **cache Basic credentials ở phía client** và có thể tự gửi lại header khi gặp vùng bảo vệ tương ứng. Cảm giác “đã login” từ browser không chứng minh server đã lưu session. Điều này cũng khiến logout khó hơn: server không thể luôn ép browser xóa Basic credentials cache chỉ bằng endpoint logout. Nếu cần logout/revocation/MFA tốt, hãy xem xét form/session hoặc token có vòng đời rõ ràng.

## 8. Bảo mật HTTP Basic: các vấn đề dễ bỏ sót

### HTTPS, password hashing và brute-force

- Base64 **không bảo mật**; password phải được bảo vệ bằng HTTPS/TLS. Nên áp dụng HSTS, cấu hình proxy và TLS theo mô hình triển khai.
- Server lưu **hash mật khẩu** bằng `PasswordEncoder` phù hợp (BCrypt, Argon2 hoặc scheme được kiểm soát), không lưu plaintext và không so chuỗi Base64 với hash.
- Giới hạn số lần thử, giám sát credential stuffing, lockout/step-up theo rủi ro. `BasicAuthenticationFilter` không tự cung cấp toàn bộ biện pháp chống brute force.
- Không ghi raw `Authorization` header, decoded username/password, Basic token hoặc các thông tin có thể tái sử dụng để xác thực vào log/telemetry.

### CSRF khi browser tự gửi credentials

**Đừng mặc định “HTTP Basic = stateless = không cần CSRF”.** Browser có thể tự gửi lại credentials được cache. Nếu client browser tự đính kèm credentials vào request, các yêu cầu ghi dữ liệu có thể cần CSRF protection, tùy kiến trúc và threat model.

Trong demo, giữ CSRF mặc định vì các endpoints chỉ dùng GET. Khi xây POST/PUT/DELETE, hãy xác định client (browser, SPA, mobile, backend), cách gửi credentials tự động/chủ động, CORS và các lớp bảo vệ cần thiết. API **chỉ chấp nhận Bearer token chủ động gửi qua header** có thể có chính sách CSRF khác với browser sử dụng cookie hoặc Basic cache; không tắt CSRF cho toàn bộ website chỉ để một lệnh curl POST chạy được.

### Realm và quyền truy cập

`realm="Learning API"` thuộc challenge HTTP, **không phải `ROLE_ADMIN`**. Cấu hình realm không xác định user nào được xem resource; quyền vẫn do `authorizeHttpRequests`/method security và authorities từ nguồn tin cậy quản lý.

## 9. Tùy chỉnh AuthenticationEntryPoint theo nhu cầu API

Nếu cần response JSON 401 nhưng vẫn dùng HTTP Basic, có thể tùy chỉnh entry point. Fragment thay thế dưới đây dành cho method cấu hình `HttpSecurity`:

```java
http.httpBasic(basic -> basic.authenticationEntryPoint(
        (request, response, exception) -> {
            response.setStatus(401);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("WWW-Authenticate",
                    "Basic realm=\"Learning API\"");
            response.getWriter().write("{\"error\":\"unauthorized\"}");
        }
));
```

Đây là **fragment thay thế cho `http.httpBasic(basic -> basic.realmName(...))`** trong ví dụ chạy, không áp dụng đồng thời cả hai. Phần header `WWW-Authenticate` giúp giữ Basic challenge cho client. Không trả `AuthenticationException` message chi tiết, stack trace, username status hay password trong JSON.

Nếu response HTTP cần có JSON body và behavior chính xác cho cả đường lỗi của filter lẫn đường anonymous của `ExceptionTranslationFilter`, hãy kiểm thử **cả không gửi header và gửi credentials sai**. Khi tích hợp nhiều chains/entry points, content negotiation hoặc client headers có thể ảnh hưởng entry point thực sự được chọn.

Một số client/browser có thể hiện prompt nhập mật khẩu khi nhận Basic challenge; đây là hành vi **client**, không phải HTML form do server tạo. Nếu không muốn browser prompt hoặc cần login UX, xem xét cơ chế khác phù hợp thay vì chỉ đổi status code.

## 10. Khi có cả web form và REST API

Nếu một ứng dụng Servlet có web UI và API, một chính sách phù hợp thường là:

- API `/api/**`: Basic hoặc Bearer, entry point trả 401/403, stateless/request cache riêng.
- Web UI: form login, session và entry point redirect HTML.

Ví dụ **fragment thay thế** (không ghép với code runnable mục 5):

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(basic -> basic.realmName("Learning API"));
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(cache -> cache
            .requestCache(new NullRequestCache()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Fragment cần `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, `NullRequestCache`, `Customizer` và các imports tương ứng. Đây là minh họa cách chia chain, **không phải class Java độc lập để paste trực tiếp**. Đặt chain API cụ thể ở `@Order(1)`, WEB fallback ở `@Order(2)` để web form không “cướp” URL API rồi redirect tới login HTML. Đồng thời phải bảo đảm route login nằm trong chain web có `formLogin`.

Nhớ phân biệt `http.securityMatcher("/api/**")` chọn **chain nào áp dụng**, còn `authorizeHttpRequests().requestMatchers(...)` chọn **policy trong chain**. Một request chỉ vào chain phù hợp đầu tiên, không lần lượt qua cả hai.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| API trả 302 tới `/login` thay vì 401 | Web chain/form entry point được chọn | Chain order, matcher, loại entry point |
| 401 dù đã gửi Basic | Header sai Base64, password sai, user disabled/locked hoặc thiếu provider | Converter, manager/provider, encoder, account status |
| 401 không có `WWW-Authenticate` | Custom entry point không đặt header hoặc có cơ chế khác | Filter/entry point được chọn, response headers |
| Browser bật hộp thoại username/password | Browser phản ứng với Basic challenge | Đây là behavior client, không phải `UsernamePasswordAuthenticationFilter` |
| URL công khai nhận 401 khi gửi Basic sai | Filter thử xác thực trước authorization `permitAll` | Không gửi header sai; kiểm tra filter behavior |
| 403 với password đúng | Thiếu role/authority hoặc CSRF | Authorization rules, access-denied handler, CSRF |
| Request đầu 200, request sau 401 | API stateless, request sau không có credentials | Client gửi Authorization mỗi request |
| GET `/api/me` chạy khi không gửi credentials | Route mở sai hoặc context/session đang có Authentication | Rule, security chain và session/context |
| POST API trả 403 | CSRF bật cho unsafe methods | Thiết kế CSRF theo loại client, không disable mù |
| Basic không giải mã đúng Unicode | Client/server dùng charset khác nhau | Quy ước RFC 7617, client behavior |
| “Logout” nhưng browser vẫn đăng nhập Basic | Browser cache credentials riêng | Chọn cơ chế phiên/token có thu hồi phù hợp |
| JWT bị Basic filter từ chối | Basic không tự xác minh Bearer | Chuyển sang Resource Server JWT thích hợp |

### Debug theo thứ tự hợp lý

1. Xem request thực (method, URL, `Accept`, loại Authorization scheme), **không in secret**.
2. Xác minh `SecurityFilterChain` được chọn và xem có `BasicAuthenticationFilter` hay không.
3. Nếu thiếu Basic header, kiểm tra authorization và entry point khi anonymous.
4. Nếu có Basic header, xem converter có tạo đúng token, manager/provider có hỗ trợ không, password/flags có hợp lệ không.
5. Nếu xác thực thành công, kiểm tra `getAuthorities()`, `hasRole()`/`hasAuthority()` và policy.
6. Nếu 401, xem `WWW-Authenticate`, entry point và cấu hình realm; nếu 403, xem rule hoặc `CsrfFilter`.
7. Với browser/cross-origin requests, kiểm tra CORS preflight, cookie, Basic credential cache và proxy headers.
8. Kiểm tra stateless session policy và cách context được lưu; không suy luận từ `httpBasic()` đơn lẻ.

Có thể bật log ở development:

```properties
logging.level.org.springframework.security=DEBUG
```

Chỉ log thông tin an toàn; không bật log/trace làm lộ Basic credentials hoặc `Authorization` header ở production.

## 12. Câu hỏi tự ôn và checklist

1. **BasicAuthenticationFilter nhận dữ liệu gì?** `Authorization: Basic <base64(username:password)>`; nó đưa yêu cầu tới `AuthenticationManager`.
2. **AuthenticationEntryPoint có kiểm tra mật khẩu không?** Không; nó dùng `HttpServletResponse` để khởi phát authentication, thường 401 Basic challenge.
3. **Vì sao thiếu header nhưng vẫn 401?** `AuthorizationFilter` chặn anonymous, `ExceptionTranslationFilter` gọi entry point.
4. **Vì sao mật khẩu sai vẫn 401 dù đã gửi Authorization?** Filter gọi manager/provider, xác thực thất bại và entry point trả challenge.
5. **Đúng mật khẩu nhưng 403 vì sao?** Đã xác thực nhưng thiếu quyền hoặc bị chính sách khác như CSRF từ chối.
6. **Realm `Learning API` có phải một role?** Không, chỉ là tên phạm vi Basic challenge.
7. **Base64 có mã hóa bảo mật password không?** Không; phải dùng HTTPS.
8. **HTTP Basic có tự động tạo session không?** Không thể kết luận chỉ từ tên scheme; cần kiểm tra session/context policy.
9. **POST bằng HTTP Basic luôn miễn CSRF?** Không; browser có thể tự gửi credentials, phải đánh giá threat model.
10. **`permitAll` có vô hiệu hóa BasicAuthenticationFilter trên URL công khai?** Không; một header Basic sai chủ động gửi có thể vẫn gây 401.

Checklist triển khai:

- [ ] Sử dụng `BasicAuthenticationFilter` đúng chain và manager/provider có khả năng xác thực username/password.
- [ ] Kiểm tra entry point, 401 và header `WWW-Authenticate` khi client cần Basic challenge.
- [ ] Tách 401 authentication failure với 403 authorization/CSRF.
- [ ] Bảo vệ credentials bằng HTTPS, encoder phù hợp, rate limiting và chính sách logging an toàn.
- [ ] Nếu cần stateless, cấu hình và kiểm tra `SessionCreationPolicy.STATELESS` cùng context/request cache.
- [ ] Đánh giá CSRF khi browser có thể tự gắn credentials; không tắt toàn bộ mà thiếu phân tích.
- [ ] Với web + API, tách chain/entry point để API không redirect sang HTML login.
- [ ] Kiểm thử đủ public, anonymous, credentials sai, credentials đúng, thiếu role, custom entry point và request tiếp theo.
- [ ] Nếu cần logout, MFA hoặc thu hồi access, cân nhắc cơ chế phù hợp hơn Basic credentials dài hạn.

**Kết luận:** `BasicAuthenticationFilter` xử lý **Basic Authorization header và xác thực danh tính**, `AuthenticationEntryPoint` xử lý **tín hiệu HTTP yêu cầu đăng nhập** (thường **401 + `WWW-Authenticate`**), còn `AuthorizationFilter` quyết định **danh tính đã xác thực có được truy cập tài nguyên không**. Hiểu rõ ba trách nhiệm này giúp phân tích đúng 200/401/403 và thiết kế API an toàn hơn.