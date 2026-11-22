# HTTP Basic và cơ chế gửi username, password qua `Authorization` header

> **Chủ đề:** Spring Security – fundamentals → **Đăng nhập và đăng xuất**. Bài học giải thích HTTP Basic theo RFC 7617, quy trình challenge–response trong HTTP, cách Spring Security đọc username/password từ `Authorization`, cấu hình cho ứng dụng Servlet và WebFlux, kiểm thử, xử lý lỗi và các rủi ro về TLS, lưu thông tin đăng nhập, CSRF và logout. Ví dụ Java dùng JDK 17+, Spring Boot 3.x và Spring Security 6.x.

## 1. HTTP Basic Authentication là gì?

**HTTP Basic Authentication** (viết ngắn là **Basic Auth**) là cơ chế xác thực HTTP trong đó client gửi cặp `username:password` trong header `Authorization` ở các request cần bảo vệ. Cặp thông tin được **mã hóa biểu diễn bằng Base64**, không được mã hóa bí mật bằng Base64.

```http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Basic cmVhZGVyOnNlY3JldA==
```

Trong ví dụ trên, chuỗi Base64 `cmVhZGVyOnNlY3JldA==` chính là biểu diễn byte của `reader:secret`; ai có chuỗi này đều có thể giải mã về tên và mật khẩu gốc. **Không sử dụng HTTP Basic trên kết nối HTTP không mã hóa ở môi trường thực**. HTTPS/TLS là biện pháp cốt yếu để bảo vệ header khỏi bị đọc trên đường truyền.

Cần phân biệt:

- **Authentication:** xác minh cặp thông tin đăng nhập có hợp lệ không. HTTP Basic là **cách truyền credential**, không phải hệ thống lưu tài khoản hoặc hàm kiểm tra mật khẩu.
- **Authorization:** tài khoản đã xác thực được gọi endpoint nào. Spring Security thực hiện bằng `authorizeHttpRequests`, `authorizeExchange`, `hasRole`, `hasAuthority`, v.v.
- **Session:** nơi ứng dụng có thể lưu trạng thái đăng nhập. Giao thức Basic **không yêu cầu** session cookie; thông thường client có thể gửi credential ở mỗi request. Có dùng/không dùng HTTP session còn tùy cấu hình Spring Security và ứng dụng.
- **Logout:** HTTP Basic **không có nghi thức logout chuẩn buộc browser xóa credential đã cache**; không nên áp kỳ vọng của form login/session cookie lên Basic.

### 1.1. Khi nào Basic phù hợp?

Basic Auth có thể hợp lý trong các bối cảnh hạn chế như công cụ quản trị nội bộ, demo, script hoặc API machine-to-machine đơn giản với HTTPS, kiểm soát người dùng, rotation và audit tốt. Với ứng dụng có nhiều client, quyền ủy quyền, thời hạn cấp quyền ngắn, SSO, MFA hoặc logout UX rõ ràng, nên cân nhắc cơ chế khác như form login/session, OAuth2/OIDC hoặc bearer token ngắn hạn tùy kiến trúc.

Không chọn Basic chỉ vì `Authorization` dễ tạo: mỗi request có thể tái gửi mật khẩu thật, nên khi credential bị lộ, hậu quả có thể nghiêm trọng hơn lộ một access token ngắn hạn đã giới hạn phạm vi.

## 2. Cú pháp chính xác của `Authorization: Basic ...`

Theo **RFC 7617**, client tạo `user-pass` theo trình tự:

1. Lấy username và password.
2. Ghép bằng dấu hai chấm đầu tiên: `username + ":" + password`.
3. Chuyển chuỗi thành byte theo một character encoding mà client/server thống nhất.
4. Mã hóa byte bằng **Base64**.
5. Gửi header `Authorization` với authentication scheme `Basic` theo sau là một dấu cách và chuỗi Base64.

Công thức:

```text
username = "reader"
password = "secret"

user-pass = "reader:secret"
UTF-8 bytes = byte sequence of "reader:secret"
Base64 = "cmVhZGVyOnNlY3JldA=="

Authorization: Basic cmVhZGVyOnNlY3JldA==
```

**Dấu hai chấm phân cách:** username **không được chứa dấu `:`** trong Basic theo RFC; server phân tách ở **dấu hai chấm đầu tiên**, còn password vẫn có thể chứa dấu `:` ở phía sau. Ví dụ chuỗi `reader:a:b` có username `reader` và password `a:b`, không phải username `reader:a` và password `b`.

**Charset không tự động cố định UTF-8 cho mọi server/client:** RFC 7617 để encoding mặc định cho trường hợp không có khai báo ở trạng thái chưa xác định nhằm tương thích hệ thống cũ. Server có thể đưa tham số `charset="UTF-8"` trong header **challenge** `WWW-Authenticate` để chỉ định UTF-8 theo RFC; không gắn tham số `charset` vào chính header `Authorization: Basic ...`. Với username/password có dấu tiếng Việt hoặc ký tự Unicode, cần kiểm tra client, server và normalization tương thích. Ví dụ ASCII `reader:secret` tránh vấn đề này.

**`Authorization` khác `Proxy-Authorization`:** cái đầu dùng để xác thực với **origin server**; cái sau phục vụ HTTP proxy yêu cầu xác thực và có luồng `407 Proxy Authentication Required` riêng. Đừng nhầm challenge `WWW-Authenticate` từ server với `Proxy-Authenticate` từ proxy.

## 3. Luồng 401 challenge–response trên HTTP

HTTP Basic dựa trên **HTTP authentication framework**. Một request không có credential tới tài nguyên được bảo vệ thường đi theo chuỗi:

```text
┌──────────────────────┐              ┌──────────────────────────┐
│ Client / browser     │              │ Server + Spring Security │
└──────────┬───────────┘              └─────────────┬────────────┘
           │ GET /api/me                           │
           │ (không có Authorization)              │
           ├───────────────────────────────────────►│
           │                                       │
           │ 401 Unauthorized                      │
           │ WWW-Authenticate: Basic realm="API"  │
           │◄───────────────────────────────────────┤
           │                                       │
           │ GET /api/me                           │
           │ Authorization: Basic <base64>         │
           ├───────────────────────────────────────►│
           │                                       │
           │ xác thực credential → kiểm tra quyền  │
           │◄───────────────────────────────────────┤
           │ 200 OK, hoặc 401/403 tùy kết quả      │
```

Sơ đồ là **luồng điển hình**, không bắt buộc client phải đợi 401 rồi mới gửi credential. `curl -u` và nhiều HTTP client có thể **gửi trước** `Authorization: Basic ...` ngay trong request đầu tiên. Một số client/browser cache credential theo protection space/realm và tự tái gửi ở request sau.

### 3.1. `WWW-Authenticate` và realm

Response cho client chưa xác thực có thể có:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Demo API"
Cache-Control: no-store
```

- `401` nói rằng request chưa cung cấp authentication hợp lệ cho tài nguyên, thường kèm challenge.
- `WWW-Authenticate` cho biết server chấp nhận cơ chế `Basic` và có thể xác định vùng bảo vệ (**realm**).
- `realm="Demo API"` là nhãn/không gian bảo vệ phục vụ xác thực theo HTTP; **không phải** role, tenant hoặc permission của Spring Security.
- Browser có thể hiển thị hộp thoại username/password dựa vào challenge; fetch/XHR và client tự động có thể xử lý khác. Spring Security có hành vi đặc thù để tránh bật prompt trình duyệt trong một số request AJAX.
- Có thể quảng bá UTF-8 bằng `WWW-Authenticate: Basic realm="Demo API", charset="UTF-8"` với client hỗ trợ; không nên cho rằng mọi client cũ tuân theo charset.

### 3.2. Phân biệt 401, 403 và thành công

| Bối cảnh | Kết quả thường gặp | Giải thích |
|---|---|---|
| Không gửi `Authorization` tới endpoint protected | **401** và challenge Basic | Chưa có credential hợp lệ |
| `Authorization: Basic ...` với password sai | **401** | Xác thực thất bại; có thể challenge lại |
| Header Basic bị hỏng hoặc không giải mã hợp lệ | **401** hoặc xử lý lỗi khác tùy filter/config | Không tạo authentication hợp lệ |
| Credential đúng, role không đủ | **403 Forbidden** | Đã xác thực nhưng authorization từ chối |
| Credential đúng, có quyền và handler thành công | **2xx** | Được đi tiếp; mã cụ thể phụ thuộc endpoint |
| Endpoint công khai với `permitAll()` | Thường không cần login | Vẫn chịu các filter/biện pháp bảo mật khác |

**Không suy ra mọi response 401/403 đều do Basic filter:** CSRF protection, entry point, custom exception handler, reverse proxy, resource server hoặc logic ứng dụng cũng có thể ảnh hưởng status. Ví dụ với POST, một request dùng Basic hợp lệ vẫn có thể bị **403 vì thiếu CSRF token** nếu CSRF guard đang bật.

## 4. Cơ chế trong Spring Security Servlet

Trong ứng dụng Spring MVC/Servlet sử dụng Spring Security 6.x, các thành phần chính:

- `SecurityFilterChain`: danh sách các Servlet filter bảo vệ request theo cấu hình `HttpSecurity`.
- `BasicAuthenticationFilter`: tìm credential Basic trong request, decode username/password, xây dựng một `Authentication` chưa xác thực và gửi cho cơ chế xác thực.
- `AuthenticationManager`: điều phối việc xác thực, thường thông qua `ProviderManager` với provider hỗ trợ username/password.
- `DaoAuthenticationProvider`: có thể dùng `UserDetailsService` tìm user và `PasswordEncoder` kiểm tra password do client cung cấp với **hash** đang lưu.
- `SecurityContextHolder`: cung cấp authentication đã xác minh trong quá trình xử lý Servlet request.
- `AuthorizationFilter` hoặc các thành phần authorization tương ứng: áp rule `authenticated()`, `hasRole(...)`, `hasAuthority(...)` trước khi request đi tới controller.
- `ExceptionTranslationFilter` và `BasicAuthenticationEntryPoint`: phối hợp khởi tạo challenge khi thiếu authentication hợp lệ, xử lý phản hồi từ chối theo cấu hình.

Luồng rút gọn:

```text
HTTP request
  │
  ▼
FilterChainProxy / SecurityFilterChain
  │
  ▼
BasicAuthenticationFilter
  ├─ Không có Basic header: để pipeline quyết định tiếp
  └─ Có Basic header: decode username/password
             │
             ▼
         AuthenticationManager
             │
             ▼
        UserDetailsService
        + PasswordEncoder
             │
       ┌─────┴───────┐
       │ hợp lệ      │ sai
       ▼             ▼
 Authentication   Authentication failure
 đã xác thực       → 401/challenge
       │
       ▼
  Authorization rule
       │
   ┌───┴────────┐
   │ đủ quyền   │ thiếu quyền
   ▼            ▼
 Controller      403 (thường gặp)
```

**Quan trọng:** Basic gửi **mật khẩu gốc trong credential được Base64 hóa** qua HTTPS, nhưng server **không nên lưu mật khẩu gốc**. `PasswordEncoder` kiểm tra mật khẩu từ request với hash được lưu (ví dụ BCrypt hoặc thuật toán password hashing được khuyến nghị). Base64 **không phải** `PasswordEncoder` và không thay thế BCrypt/Argon2/PBKDF2.

Trong Spring Security, việc đọc username/password không buộc ứng dụng tạo form login. Có thể bật Basic độc lập:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
```

Đây là **trích đoạn**, không phải toàn bộ class chạy được. Cần import `org.springframework.security.config.Customizer`, `HttpSecurity`, định nghĩa `SecurityFilterChain` và cung cấp cơ chế kiểm tra user/password.

## 5. Ví dụ Spring Boot MVC có thể chạy: hai user, ba endpoint

Ví dụ dùng **Java 17**, **Maven**, Spring Boot **3.5.7** (một version 3.x cố định để tái lập bài học) và Spring Security 6.x do Spring Boot quản lý dependency. Trong triển khai production, phải nâng lên phiên bản đang được hỗ trợ và đã vá bảo mật; mật khẩu dưới đây **chỉ là dữ liệu demo**.

Cấu trúc:

```text
basic-auth-demo/
├── pom.xml
└── src/main/java/com/example/basicauth/
    ├── BasicAuthApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>basic-auth-demo</artifactId>
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

### 5.2. `BasicAuthApplication.java`

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }
}
```

### 5.3. `SecurityConfig.java`

```java
package com.example.basicauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-pass-123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("ops")
            .password(encoder.encode("demo-admin-123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

Phân tích cấu hình:

1. `.httpBasic(Customizer.withDefaults())` đăng ký Basic authentication trong Servlet security chain.
2. `/public/ping` được `permitAll()`; không đòi Basic header.
3. `GET /api/me` yêu cầu `authenticated()`; cả `reader` và `ops` đều đạt nếu nhập đúng mật khẩu.
4. `GET /api/admin/**` yêu cầu `hasRole("ADMIN")`, tương ứng `ROLE_ADMIN` theo prefix mặc định. `reader` chỉ có `ROLE_READER` nên bị từ chối.
5. `.anyRequest().denyAll()` không tự cấp quyền cho endpoint khác hoặc method chưa mô tả. Đây là lựa chọn **deny by default**.
6. `formLogin(...disable())` bỏ form login trong demo để thể hiện rõ Basic. Nó không có nghĩa ứng dụng trở nên stateless hay CSRF được tắt.
7. `InMemoryUserDetailsManager` dùng cho demo, unit test hoặc tình huống nhỏ. Hai password ở đây được **hash bằng BCrypt khi khởi động**, nhưng giá trị plaintext viết trong source chỉ để học. Production phải lấy credential từ kho an toàn và quản lý user/role/rotation thích hợp.
8. Không có `.csrf(csrf -> csrf.disable())`: demo **giữ CSRF mặc định**. Các route được thử chỉ dùng GET, tránh hiểu sai rằng bật Basic là có thể bỏ CSRF.

### 5.4. `DemoController.java`

```java
package com.example.basicauth;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "admin-report";
    }
}
```

Controller chỉ đọc tên user từ `Authentication` do Spring Security cung cấp; **không tin username lấy từ header tự chế hoặc request body**. Nó không trực tiếp decode header Basic, bởi việc này thuộc filter đã cấu hình.

### 5.5. Chạy với Maven

Trong thư mục `basic-auth-demo`:

```bash
mvn spring-boot:run
```

Yêu cầu đã cài **JDK 17+** và Maven. Ứng dụng mặc định chạy ở `http://localhost:8080` khi chưa đổi `server.port`. Dùng HTTP ở đây **chỉ cho môi trường localhost để học**; production phải phục vụ qua HTTPS/TLS và kiểm tra proxy/security headers.

Kiểm tra các tình huống:

```bash
# 1. Public endpoint, không cần credentials
curl -i http://localhost:8080/public/ping

# 2. Protected endpoint nhưng không gửi Authorization
curl -i http://localhost:8080/api/me

# 3. reader có mật khẩu đúng (CHỈ DỮ LIỆU DEMO)
curl -i --user reader:demo-pass-123 http://localhost:8080/api/me

# 4. reader không có ROLE_ADMIN
curl -i --user reader:demo-pass-123 http://localhost:8080/api/admin/report

# 5. ops có ROLE_ADMIN
curl -i --user ops:demo-admin-123 http://localhost:8080/api/admin/report

# 6. Sai mật khẩu
curl -i --user reader:wrong-password http://localhost:8080/api/me
```

Ma trận kết quả kỳ vọng, giả sử không có custom middleware hoặc proxy nào sửa response:

| Request | Credential | Status kỳ vọng | Kết quả chính |
|---|---|---|---|
| `GET /public/ping` | không có | 200 | Body `pong` |
| `GET /api/me` | không có | 401 | Challenge Basic |
| `GET /api/me` | reader / demo-pass-123 | 200 | JSON chứa `"username":"reader"` |
| `GET /api/admin/report` | reader / demo-pass-123 | 403 | Reader thiếu `ROLE_ADMIN` |
| `GET /api/admin/report` | ops / demo-admin-123 | 200 | Body `admin-report` |
| `GET /api/me` | reader / wrong-password | 401 | Authentication thất bại |
| `POST /api/me` | reader / demo-pass-123 | bị từ chối | Không có rule POST, CSRF cũng có thể từ chối trước |

**Lưu ý:** Đừng hardcode password thật trong lệnh shell, script được commit, CI log hoặc process arguments. `curl --user reader` có thể yêu cầu nhập password tương tác; ví dụ `--user name:password` bên trên chỉ để dễ quan sát với **tài khoản demo không dùng ngoài localhost**. Tùy cài đặt browser/client, có thể thấy challenge/response headers hoặc nội dung lỗi khác nhau; không assert toàn bộ message lỗi khi bài kiểm tra chỉ cần status.

## 6. Java 17 độc lập: tự tạo và đọc chuỗi Basic

Để hiểu rõ Base64, chương trình dưới đây **không dùng Spring** và có thể biên dịch trực tiếp bằng `javac`. Tệp `BasicHeaderDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {

    public static void main(String[] args) {
        String username = "reader";
        String password = "secret"; // Chỉ là giá trị học tập.

        String userPass = username + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8)
        );

        System.out.println("Authorization: Basic " + token);

        byte[] decoded = Base64.getDecoder().decode(token);
        System.out.println("Decoded: "
            + new String(decoded, StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy:

```bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
```

Đầu ra chuẩn chính xác:

```text
Authorization: Basic cmVhZGVyOnNlY3JldA==
Decoded: reader:secret
```

Chỉ hai dòng Java đã chứng minh Base64 **dễ đảo ngược**, không có confidentiality. Không viết chương trình production để in dòng `Decoded` hoặc lưu password plaintext: đây là cách minh họa nguy cơ. Việc cấp password an toàn cần password hashing, TLS, hạn chế logging và quản lý secret theo quy trình riêng.

### 6.1. Nếu client gửi Unicode

Ví dụ người dùng `nguyễn` và password có Unicode: `getBytes(StandardCharsets.UTF_8)` tạo byte UTF-8, nhưng server nhận đúng hay không phải dựa trên quy ước charset đã thống nhất. RFC 7617 không mặc định mọi phía dùng UTF-8 khi không có charset challenge. Nếu hỗ trợ tên tiếng Việt, test các trường hợp ký tự có dấu, normalization và quyền truy cập bằng client khác nhau; tránh tự decode bằng charset không khớp.

### 6.2. Không tự viết Basic parser trong controller

Thực tế **không cần** gọi `Base64.getDecoder()` trong controller khi Spring Security đã có Basic authentication filter. Viết parser riêng dễ mắc các lỗi: so sánh mật khẩu không an toàn, quên xử lý byte/charset, bỏ qua locking/rate limiting, lưu plaintext, tự xử lý challenge và vô tình lộ credential qua log. Hãy để Spring Security xử lý Basic và giữ code nghiệp vụ chỉ làm việc với `Authentication` đã được xác minh.

## 7. Kiểm thử thật bằng `spring-security-test`

Các request `curl` cho thấy hành vi end-to-end. Để kiểm tra tự động trên Servlet, dùng `MockMvc` và helper `httpBasic(...)` từ `spring-security-test`. Lớp test đầy đủ bên dưới khớp với ba class của demo và dependency `spring-security-test` trong `pom.xml`.

Tệp `src/test/java/com/example/basicauth/BasicSecurityTests.java`:

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class BasicSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void protectedEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAuthenticateReader() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("reader", "demo-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("ops", "demo-admin-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }
}
```

Chạy:

```bash
mvn test
```

**Ý nghĩa kiểm thử:** `httpBasic(username,password)` tạo một request với **header `Authorization: Basic ...` thật cho Spring Security filter của test**. Trong khi đó, `with(user("reader"))` hoặc `@WithMockUser` gắn sẵn một authentication mock vào test context; các cách đó hữu ích để kiểm tra quyền, nhưng **không đủ** để chứng minh quá trình decode header + kiểm tra password của Basic hoạt động. Hãy dùng loại fixture phù hợp với câu hỏi test đang kiểm.

Trước khi dùng trong sản phẩm thực, bổ sung test:

- Header Basic không đúng cú pháp hoặc Base64 sai.
- Tài khoản disabled/locked/expired và password rotation.
- Role/authority mapping và các endpoint chỉ cho ADMIN.
- HTTPS/proxy bảo toàn authentication nhưng không đưa header vào log.
- CSRF token trên unsafe methods khi request xuất phát từ browser.
- Không có `Authorization` nhưng có cookie/session khác: đảm bảo đúng authentication policy, tránh bất ngờ khi tồn tại nhiều cơ chế.
- Kiểm thử client Unicode khi hệ thống chấp nhận username/password không ASCII.

## 8. HTTP Basic trên WebFlux: cùng chuẩn header, khác filter chain

Với Spring WebFlux, **chuẩn `Authorization: Basic ...` không đổi**, nhưng API cấu hình khác:

| Servlet / MVC | Reactive / WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` |
| `SecurityContextHolder` ở Servlet | Reactor `Context` / `ReactiveSecurityContextHolder` |

Ví dụ lớp cấu hình dùng **Spring Security WebFlux**, không đặt cùng với demo Spring MVC trong một ứng dụng chạy Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveBasicConfig {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-pass-123"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
```

Lớp trên là **cấu hình Spring** cần nằm trong một ứng dụng WebFlux có `spring-boot-starter-webflux` và `spring-boot-starter-security`, không thể `javac` độc lập khi chưa có dependencies. Spring WebFlux xử lý xác thực trong **reactive WebFilter pipeline** thay vì Servlet `BasicAuthenticationFilter`; đọc authentication hiện hành bằng cơ chế reactive phù hợp. Nếu tùy biến truy vấn user từ database, không `block()` hoặc `subscribe()` thủ công trong authentication manager/reactive filter.

Đừng đổi tên `httpBasic` khi chuyển sang WebFlux — cả hai DSL đều có tên `httpBasic(...)`, nhưng builder, chain và implementation khác nhau.

## 9. HTTP Basic, HTTPS và bảo vệ credential

**Tại sao không nên dùng Basic qua HTTP?**

Header:

```http
Authorization: Basic cmVhZGVyOnNlY3JldA==
```

không che giấu username/password. Nếu gửi qua HTTP, bất kỳ bên có thể đọc traffic trên đường truyền đều có thể lấy credential và tái sử dụng. Kể cả khi truyền qua HTTPS, các vấn đề như log sai, client nhiễm mã độc, TLS termination không đáng tin hoặc secret hardcode vẫn là rủi ro riêng.

Các biện pháp tối thiểu:

1. **HTTPS end-to-end theo mô hình hạ tầng:** dùng TLS từ client đến origin/reverse proxy đáng tin; giới hạn luồng HTTP nội bộ, kiểm tra policy của ingress/load balancer. HSTS phù hợp giúp trình duyệt ưu tiên HTTPS, nhưng không thay thế TLS.
2. **Không log `Authorization`:** cấu hình reverse proxy, application server, APM, tracing, exception handler, HTTP debug log và hỗ trợ khách hàng để mask/redact credential; tuyệt đối không ghi nguyên token Basic vào log.
3. **Dùng password hashing ở server:** BCrypt/Argon2/PBKDF2 theo chính sách và chi phí phù hợp, không lưu plaintext hoặc Base64 như là hash.
4. **Giới hạn thử mật khẩu:** rate limit, backoff, phát hiện brute force, account lockout hợp lý; tránh response tiết lộ “username tồn tại nhưng password sai”.
5. **Dùng credential riêng theo client và quyền tối thiểu:** không dùng chung một admin password cho nhiều service; có quy trình cấp, thu hồi, rotate, phát hiện lộ lọt.
6. **Từ chối endpoint ngoài quyền:** có Basic credential hợp lệ không có nghĩa được gọi admin API. Dùng `hasRole`/`hasAuthority` và kiểm tra quyền cấp bản ghi nếu cần.
7. **Kiểm soát HTTP client:** không để credential trong URL `https://user:pass@example.com`, query string, file code được commit, shell history, log hoặc JavaScript frontend không kiểm soát.
8. **Không forward credential đến domain khác:** redirect, proxy hay hệ thống trung gian phải tránh chuyển tiếp header `Authorization` ra ngoài phạm vi trust.
9. **Theo dõi và vô hiệu tài khoản:** khi mật khẩu lộ, thay đổi mật khẩu, tắt user và kiểm tra mọi client cũ; Basic không có token expiration riêng.
10. **Ưu tiên biện pháp mạnh hơn khi cần:** MFA, mTLS, OAuth2 client credentials, short-lived access tokens, scoped service accounts có thể tốt hơn Basic tùy threat model.

### 9.1. Base64 không phải bảo mật, kể cả khi chuỗi dài

Một token Basic thường dài, có dấu `=` ở cuối, trông giống chuỗi khó hiểu, nhưng chỉ là mã hóa dữ liệu. Dùng cùng `username:password` sẽ cho **cùng một token** (giả sử cùng encoding). Không thêm entropy, không ký điện tử, không cấp hạn dùng, không xác minh tính toàn vẹn. Lớp bảo mật chính là TLS trong quá trình truyền và chính sách xác thực/phân quyền ở server.

### 9.2. Không nhầm với `Bearer`

`Authorization: Bearer <token>` truyền access token theo một **authentication scheme khác**; token có thể là JWT hoặc opaque token với thời hạn và phạm vi ủy quyền riêng. Không decode Bearer bằng cách chia username/password ở dấu hai chấm; không cấu hình `httpBasic()` rồi kỳ vọng nó tự xác minh Bearer token. Với OAuth2 Resource Server của Spring Security, sử dụng cấu hình resource server/decoder phù hợp.

## 10. HTTP Basic và session: điều gì là stateless?

Basic không cần session cookie để client chứng minh danh tính: mỗi request có thể mang cặp username/password. Nhưng điều đó **không tự bảo đảm ứng dụng Spring stateless ở mọi khía cạnh**.

Phân biệt ba quyết định:

- **Giao thức Basic:** cách truyền credential trong header và phản hồi challenge.
- **Session management của Spring Security:** có tạo/đọc `HttpSession` để lưu security context hoặc dữ liệu liên quan hay không.
- **Trạng thái ứng dụng:** controller/service có dùng session, giỏ hàng, workflow state hoặc dữ liệu tương tác khác hay không.

Với API chỉ phục vụ script/client không dùng trình duyệt, muốn Spring Security không dùng HTTP session để lưu authentication, có thể cấu hình thêm:

```java
// Trích đoạn trong securityFilterChain(HttpSecurity http).
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

Nhớ import `org.springframework.security.config.http.SessionCreationPolicy`. Cấu hình này nói với Spring Security cách quản lý security context/session; nó **không làm password của Basic ngừng được gửi lại**, không vô hiệu hóa mọi phiên do thành phần ứng dụng khác tự tạo, và **không phải là lập luận đủ để tắt CSRF**.

### 10.1. Vì sao Basic có thể cần CSRF protection trong browser?

CSRF xuất hiện khi trình duyệt **tự gắn credential** vào request gửi đến server theo một ngữ cảnh khác site. Với Basic, sau khi người dùng nhập credential qua browser challenge, trình duyệt **có thể nhớ và tự tái gửi** Basic credential tới protection space tương ứng. Vì vậy theo hướng dẫn Spring Security, **browser dùng Basic cũng có thể bị CSRF** ngay cả khi không dựa vào `JSESSIONID`.

Ví dụ:

1. Browser đã xác thực Basic với `https://bank.example` và cache credential.
2. Người dùng mở một site độc hại.
3. Site đó cố khởi tạo một request thay đổi trạng thái đến bank.
4. Nếu browser tự gửi Basic credential và server thiếu CSRF guard, thao tác có thể bị thực thi thay người dùng.

**Đừng viết `.csrf(csrf -> csrf.disable())` chỉ vì ứng dụng dùng Basic hoặc vì bạn đã chọn `SessionCreationPolicy.STATELESS`.** Đánh giá môi trường client, việc browser có thể tự gửi credential, content type và đường vào cross-site. Với service-to-service thuần không dùng browser, chính sách CSRF có thể khác sau khi phân tích threat model; cần giải thích rõ và test trước khi thay đổi. Với demo MVC ở trên, giữ CSRF và chỉ kiểm tra GET/HEAD an toàn.

## 11. Login, logout và việc browser cache credential

Basic không giống form login sử dụng trang đăng nhập và session cookie.

| Khía cạnh | HTTP Basic | Form login + session |
|---|---|---|
| Điểm cung cấp credential | Header `Authorization: Basic ...` | Thường POST form login |
| Khi gọi request sau | Client/browser có thể gửi lại cùng credential | Browser gửi session cookie |
| Server cần session để kiểm tra user? | Không bắt buộc | Thông thường có session |
| Có challenge `WWW-Authenticate`? | Có, trong luồng 401 điển hình | Thường redirect tới login hoặc response tùy app |
| Logout chuẩn khiến browser quên credential? | **Không có bảo đảm chuẩn** | Có thể invalidate server session và xóa cookie phù hợp |
| Phù hợp với UX “Đăng xuất” rõ ràng? | Khó hơn | Thường phù hợp hơn |
| Rủi ro nếu credential được client lưu lâu dài | Có, vì thường là password gốc | Có, nhưng session ID có thể bị thu hồi/đổi riêng |

**Sai lầm:** gọi `/logout` xong nghĩ Basic credential không còn được gửi. Nếu browser hoặc client vẫn cache cặp username/password, request kế tiếp có thể lập tức xác thực lại. Invalidating `HttpSession` không xóa được credential mà browser đã lưu. Có thể thay đổi realm, password hoặc xử lý client-specific, nhưng đó không phải cơ chế logout phổ quát, đáng tin hoặc thân thiện với UX.

Nếu yêu cầu có đăng nhập/đăng xuất thật sự trong UI, bảo mật đa thiết bị, MFA/SSO và phiên có thời hạn, nên chọn cơ chế thiết kế riêng cho phiên hoặc token có lifecycle thu hồi phù hợp.

## 12. Nhận diện lỗi thường gặp

1. **Nghĩ Base64 là mã hóa an toàn:** dễ decode; dùng HTTPS và không lộ header.
2. **Chỉ mã hóa password rồi bỏ username khỏi token:** Basic chuẩn cần `username:password` trước Base64.
3. **Gửi header sai cú pháp:** `Authorization: Basic token` có một dấu cách sau scheme; không gửi `Basic username:password` thô.
4. **Nhầm `Authorization` với `WWW-Authenticate`:** client gửi cái đầu, server challenge bằng cái sau.
5. **Nhầm 401 và 403:** 401 thường yêu cầu credential hợp lệ; 403 thường là đã xác thực nhưng thiếu quyền hoặc bị lớp CSRF/policy khác từ chối.
6. **Không dùng `PasswordEncoder`:** không lưu plaintext/Base64 password trong database hoặc source. `User.withDefaultPasswordEncoder()` không phù hợp cho sản phẩm thật.
7. **Đồng nhất Basic với stateless tuyệt đối:** session và application state là quyết định cấu hình riêng.
8. **Tắt CSRF mặc định trong browser Basic:** trình duyệt có thể tự gửi lại credential, nên nguy cơ CSRF có thể vẫn còn.
9. **Quên quyền endpoint:** `authenticated()` chỉ cần đăng nhập; `/api/admin/**` vẫn phải có `hasRole("ADMIN")` hoặc policy tương đương.
10. **Quên negative tests:** test user đúng chưa chứng minh password sai bị từ chối hoặc user thường không truy cập được admin.
11. **Tin rằng Basic có logout chuẩn:** browser/client có thể tiếp tục cache và gửi credential.
12. **Đặt credential trong URL/curl CLI/log:** nguy cơ lộ qua history, process list, monitoring, access logs hoặc trace.
13. **Tự decode Basic trong controller:** dễ bỏ qua flow xác thực, password hashing, rate limit, challenge và audit của Spring Security.
14. **Bỏ qua charset/Unicode:** client/server dùng khác charset có thể khiến login lỗi với username có dấu.
15. **Nhầm Basic với Bearer:** không dùng Basic filter để xác minh OAuth2 JWT.
16. **Tưởng `permitAll()` nghĩa là filter không hoạt động:** Basic filter vẫn có thể xử lý Authorization header đã gửi; quy tắc permitAll chỉ nói request không cần permission để đi qua authorization gate.
17. **Dựa vào default user/password của framework khi deploy:** demo có user in-memory cố định; production cần danh tính, nguồn user, password rotation và giám sát thật.
18. **Chuyển từ MVC sang WebFlux bằng copy cấu hình:** cùng header nhưng lớp bảo mật, security context và repository API khác.
19. **Bỏ qua reverse proxy:** một thiết bị trung gian có thể log, xóa hoặc forward header không đúng; kiểm tra end-to-end trên HTTPS.
20. **Đưa header Basic vào report/ticket:** bất kỳ ai nhìn thấy đều có thể decode về mật khẩu; phải redact trước khi chia sẻ.

## 13. Checklist triển khai API có Basic

- [ ] Xác định ai là client: browser, script, mobile app hay service-to-service; Basic thực sự phù hợp hơn token/session không?
- [ ] HTTPS/TLS bắt buộc trên đường từ client tới hệ thống tin cậy; không truyền credential qua HTTP production.
- [ ] Không xuất `Authorization` vào log, trace, metrics labels, error response hoặc tài liệu hỗ trợ có thể truy cập công khai.
- [ ] Username/password được kiểm tra bằng `AuthenticationManager` và provider phù hợp; password ở storage là hash đủ mạnh.
- [ ] Account, role, authority và quyền trên tài nguyên được kiểm soát độc lập với thành công của Basic authentication.
- [ ] Chỉ mở endpoint có chủ đích, matcher đặc thù trước; có `anyRequest().denyAll()` hoặc fallback được review rõ.
- [ ] 401/WWW-Authenticate và 403 được test đúng cơ chế và quyền; không lộ thông tin tài khoản trong lỗi.
- [ ] Có rate limit, giám sát brute force, rotation/thu hồi credential, xử lý tài khoản bị khóa.
- [ ] Nếu browser có thể tự gửi credential, đánh giá CSRF; không tắt vì cho rằng Basic mặc nhiên an toàn.
- [ ] Không coi Basic có logout chuẩn; UX đăng xuất cần cơ chế khác hoặc chính sách client quản lý credential.
- [ ] Với server stateless, cấu hình session management rõ, nhưng vẫn xét application state/CSRF riêng.
- [ ] Kiểm thử Java/MockMvc bằng Basic header thật, không chỉ mock user; kiểm tra cả case sai password và thiếu role.
- [ ] Nếu dùng Unicode, chốt và test charset/normalization theo RFC và browser/client thực tế.
- [ ] Nếu dùng WebFlux, dùng `ServerHttpSecurity` và reactive user store, không block reactive pipeline.

## 14. Tài liệu tham khảo

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): định dạng `username:password`, Base64, realm, charset và hạn chế bảo mật của Basic.
- [Spring Security 6.5 — Basic Authentication (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationFilter`, `WWW-Authenticate`, xử lý challenge, `AuthenticationManager`.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): `httpBasic`, `UserDetailsService` và cơ chế xác minh password.
- [Spring Security — CSRF and stateless browser applications](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): browser có thể tự gửi HTTP Basic credentials nên có thể bị CSRF.
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): cấu hình `SecurityWebFilterChain`, `ServerHttpSecurity` và `httpBasic`.

**Ghi nhớ:** HTTP Basic truyền `username:password` được **Base64 hóa** trong `Authorization` header, thường lặp lại theo request; **Base64 không che giấu mật khẩu**. Spring Security dùng filter, authentication manager/provider, password encoder và authorization rules để xử lý. Chỉ dùng Basic trên **HTTPS**, không log header, kiểm tra role/quyền ở server và hiểu rõ rằng browser cache, CSRF, session và logout là các vấn đề phải giải quyết thêm — không được Basic tự xử lý.