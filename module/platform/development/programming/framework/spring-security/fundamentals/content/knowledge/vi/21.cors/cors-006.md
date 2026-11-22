# Thứ tự xử lý CORS và yêu cầu xác thực

## 1. Mục tiêu

Bài thuộc nhóm **CORS** của **Spring Security - fundamentals**. Tình huống điển hình là frontend ở `http://localhost:5173` gọi API ở `http://localhost:8080`, trình duyệt gửi request `OPTIONS` rồi báo CORS error, trong khi cùng API hoạt động qua `curl`. Nguyên nhân phổ biến là **preflight bị chặn bởi authentication/authorization trước khi CORS được xử lý**, hoặc origin, method, headers chưa được cho phép.

Sau bài này, bạn có thể:

- Giải thích CORS và nguyên tắc xử lý **preflight trước bước yêu cầu Authentication**.
- Phân biệt preflight `OPTIONS` với **actual GET/POST**; xác định headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
- Phân biệt **CORS, Authentication, Authorization và CSRF**; preflight 200 không cho phép truy cập tài nguyên.
- Cấu hình `http.cors(withDefaults())` cùng `UrlBasedCorsConfigurationSource` trong Spring Security Servlet.
- Hiểu `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age` và `Vary`.
- Kiểm thử 200/401/403, origin cho phép/từ chối, POST preflight và kiểm tra CSRF bằng `MockMvc`.
- Chẩn đoán cấu hình `@CrossOrigin`, `OPTIONS permitAll`, multiple `SecurityFilterChain`, reverse proxy, cookie và browser credentials mode.

**Phạm vi:** Spring Security 6.x Servlet/MVC dùng `HttpSecurity` và `SecurityFilterChain`. Spring WebFlux dùng `ServerHttpSecurity`/`CorsWebFilter`, không áp dụng nguyên mã Servlet.

## 2. CORS là quyền dùng response trên browser, không phải quyền vào API

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **CORS** | Origin browser có được gửi/đọc response cross-origin với method và headers yêu cầu không? | Frontend `http://localhost:5173` gọi `GET /api/me` kèm `Authorization` |
| **Authentication** | Request **thật** có chứng minh danh tính hợp lệ không? | HTTP Basic, session cookie hoặc Bearer token |
| **Authorization** | Danh tính đã xác thực có quyền dùng endpoint hay resource cụ thể không? | `ROLE_ADMIN` cho `GET /api/admin` |
| **CSRF** | Unsafe request có bằng chứng chống giả mạo phù hợp trong mô hình browser tự gửi credentials không? | `POST /api/ping` với CSRF token |

CORS **không** xác thực password, JWT, session, role, scope hay quyền sở hữu. Khi trình duyệt nhận preflight 200, nó mới biết **có thể tiếp tục actual request**; API vẫn có thể trả 401 hoặc 403. Ngược lại, client có password đúng không tự vượt qua CORS của origin không được phép.

**Origin = scheme + host + port.** `http://localhost:5173` và `http://localhost:8080` khác origin vì khác port. `https://app.example.com` và `http://app.example.com` khác scheme. Path `/dashboard` không thuộc origin. **Cross-origin khác cross-site**: cookie `SameSite` dùng khái niệm site, không trùng hoàn toàn với origin.

**CORS không phải firewall.** Một chương trình server-to-server, Postman hoặc `curl` có thể gửi HTTP request mà không chịu ràng buộc trình duyệt đối với CORS. Backend phải bảo vệ mọi tài nguyên bằng Authentication và Authorization độc lập với header `Origin`.

## 3. Nhận diện preflight

Ví dụ một frontend cố gọi API với header `Authorization`:

```javascript
fetch("http://localhost:8080/api/me", {
  method: "GET",
  headers: {
    "Authorization": "Bearer TOKEN_FROM_REAL_LOGIN_FLOW"
  }
});
```

Đây là **fragment frontend** để giải thích CORS, không phải ứng dụng phát token hoàn chỉnh. Không hard-code access token hoặc password thật vào JavaScript. Header `Authorization` không thuộc nhóm CORS-safelisted request headers nên browser thường phải preflight.

**Request OPTIONS preflight**:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight **thường không mang `JSESSIONID` hoặc HTTP `Authorization` credentials của request thật**. `Access-Control-Request-Headers: authorization` chỉ nêu **tên** header được đề nghị; nó **không chứa giá trị token**. Preflight không gọi controller để đọc profile, không sửa dữ liệu, không có danh tính Alice/Bob cần phân quyền.

Không phải mọi `OPTIONS` đều là preflight; một CORS preflight thông thường cần `Origin` và `Access-Control-Request-Method`. Đừng coi một request OPTIONS tùy ý là được phép không cần xử lý.

**Phản hồi hợp lệ có dạng:**

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Giá trị và thứ tự headers thay đổi theo CORS config/framework; đây là mẫu minh họa, không phải bytes cố định.

- `Access-Control-Allow-Origin`: origin được phép nhận response theo chính sách browser.
- `Access-Control-Allow-Methods`: method được phép trong CORS.
- `Access-Control-Allow-Headers`: request headers cho phép.
- `Access-Control-Allow-Credentials`: phối hợp với credentials mode khi frontend cần cookies/auth credentials; nếu true thì origin phải được chỉ rõ, không dùng `*`.
- `Access-Control-Max-Age`: thời gian browser có thể cache **preflight**, không phải session timeout hoặc thời hạn token.
- `Vary`: giúp cache phân biệt origin, requested method/headers.

**Sau preflight:** browser gửi GET/POST thật, lúc này mới có header `Authorization` hoặc cookie session (tùy browser/credential policy), và backend mới xác thực và phân quyền. Nếu origin/method/header không hợp lệ, CORS processor có thể trả **403**, chặn bước tiếp theo.

## 4. Thứ tự sai và thứ tự đúng

### Sai: auth xử lý trước CORS

```text
Browser OPTIONS /api/me
  Origin: http://localhost:5173
  Access-Control-Request-Method: GET
  Access-Control-Request-Headers: authorization
                │
                ▼
Authentication / authorization yêu cầu authenticated()
                │
         Không có cookie hoặc Authorization credentials
                │
                ▼
          401 Unauthorized / 302 /login
                │
                ▼
Browser báo preflight/CORS error
GET thật có thể chưa được gửi
```

Đây là vấn đề **thứ tự**, không phải bằng chứng API GET phải công khai. Thêm credentials vào OPTIONS không phải lời giải: browser không dùng preflight để gửi token của request thật.

### Đúng: CORS trước filter đòi Authentication

```text
Servlet request
      │
      ▼
FilterChainProxy chọn SecurityFilterChain đúng path
      │
      ▼
CorsFilter được http.cors(...) tích hợp
      │
      ├─ Preflight hợp lệ → 200 + CORS allow headers, dừng
      ├─ Preflight sai policy → 403, dừng
      └─ Actual request hợp lệ về origin → tiếp tục
                   │
                   ▼
               CsrfFilter
                   │
                   ▼
          Authentication filters
                   │
                   ▼
           AuthorizationFilter
                   │
                   ▼
               Controller
```

Sơ đồ là mô hình rút gọn. Trong Spring Security Servlet, **`CorsFilter` được tích hợp ở vị trí phù hợp trước các security filters đòi credentials**; thứ tự đầy đủ còn nhiều filters. Vì vậy câu “CORS phải được xử lý trước Spring Security” trong tài liệu có ý nghĩa **trước những bước đòi Authentication/Authorization**. `CorsFilter` vẫn có thể nằm **bên trong** `SecurityFilterChain` khi được cấu hình bằng `http.cors(...)`, không bắt buộc là filter global đứng ngoài toàn bộ Spring Security.

Đừng trông chờ việc đổi vị trí `.cors(...)` và `.authorizeHttpRequests(...)` trong source Java sẽ tự đổi thứ tự filters; Spring Security quản lý thứ tự filter theo cơ chế framework.

**Thứ tự đúng giữ nguyên an toàn:** preflight 200 **không** có quyền; actual request cần Authn/Authz và có thể bị CSRF chặn nếu là unsafe method.

## 5. Tại sao chỉ permitAll OPTIONS chưa đủ?

Cấu hình này thường được dùng để sửa nhanh:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
    .anyRequest().authenticated()
)
```

Đây là **fragment**, **không phải cấu hình CORS hoàn chỉnh**. `permitAll()` chỉ mở một bước **authorization** nhưng không tạo `Access-Control-Allow-Origin/Methods/Headers`, không áp dụng danh sách origin được tin cậy và không bảo đảm custom authentication filter trước đó không chặn OPTIONS.

`web.ignoring().requestMatchers(HttpMethod.OPTIONS, "/**")` cũng không tự tạo CORS response và có thể bỏ qua nhiều security filters không cần thiết. Thực hành tốt là **cho CORS processor nhận diện/giải quyết preflight**, còn actual methods vẫn chịu policy bảo mật.

## 6. Cấu hình Spring Security Servlet

Tạo `UrlBasedCorsConfigurationSource` với allowlist hẹp:

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("http://localhost:5173"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-CSRF-TOKEN")
    );
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Đây là fragment, phần code runnable mục 8 có đủ imports/class. Bật CORS trong `HttpSecurity`:

```java
http.cors(withDefaults());
```

Spring Security có thể dùng bean `UrlBasedCorsConfigurationSource` để cấu hình xử lý CORS trước authentication. Khi có Spring MVC trên classpath nhưng **không có `CorsConfigurationSource` riêng**, Spring Security có thể dùng CORS config của Spring MVC. `@CrossOrigin` ở controller **không giải quyết được** preflight nếu một security filter đã chặn trước khi MVC nhận request.

Các tham số cần kiểm tra:

| Cấu hình | Tác dụng | Cảnh báo |
| --- | --- | --- |
| `allowedOrigins` | Origin allowlist, gồm scheme/host/port | Không dùng wildcard với credentials true |
| `allowedMethods` | Methods được browser phép gọi | Không mở rộng DELETE/PUT nếu chưa cần |
| `allowedHeaders` | Request headers được browser phép gửi | Có `Authorization` cho bearer/Basic, `Content-Type` cho JSON |
| `allowCredentials` | Response hỗ trợ credentialed cross-origin mode hay không | Không thay login; true cần origin cụ thể |
| `maxAge` | Preflight cache duration | Không phải session/token expiry |
| `registerCorsConfiguration` | Path mapping cho CORS | `/api/**` không tự bảo vệ/cấp CORS cho `/login` |

### Cookie và CORS credentials

Nếu frontend `https://app.example.com` dùng session cookie của backend `https://api.example.com`, request thật có thể gửi cookie theo `credentials:"include"` và cookie policy. CORS preflight vẫn không thể bị bắt chứng minh danh tính.

**Fragment cấu hình cho cookie-based frontend:**

```java
CorsConfiguration cfg = new CorsConfiguration();
cfg.setAllowedOrigins(List.of("https://app.example.com"));
cfg.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cfg.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cfg.setAllowCredentials(true);
```

**Frontend fragment:**

```javascript
fetch("https://api.example.com/account", {
  credentials: "include",
  method: "GET"
});
```

Với credentials mode `include`, browser cần `Access-Control-Allow-Credentials: true` và `Access-Control-Allow-Origin` cụ thể được phép để frontend đọc response. `Access-Control-Allow-Origin: *` **không hợp lệ** cho credentialed response; Spring Framework không cho `allowedOrigins("*")` kết hợp `allowCredentials(true)`. Cookie còn phụ thuộc `Secure`, `SameSite`, Domain/Path và chính sách browser. Cross-origin không nhất thiết cross-site, đừng đặt `SameSite=None` bừa bãi.

**CORS không thay CSRF.** Browser có thể tự gửi cookie session vào một request không mong muốn. Với POST/PUT/PATCH/DELETE của app dùng session/cookie, cần CSRF protection hoặc biện pháp tương đương, ngay cả khi CORS đã cho phép origin.

## 7. Phân biệt 200, 401 và 403

| Tình huống | Response điển hình trong lab | Nhóm nguyên nhân |
| --- | --- | --- |
| Preflight hợp lệ, không có credentials | **200** | CORS chấp nhận origin/method/headers |
| Preflight từ origin không được phép | **403** | CORS |
| Preflight xin method/header chưa cho | **403** | CORS |
| Actual GET origin hợp lệ nhưng không credentials | **401** | HTTP Basic authentication |
| Actual GET origin hợp lệ nhưng password sai | **401** | Authentication |
| Actual GET user có quyền | **200** | Qua authn/authz |
| Actual GET user không đủ `ROLE_ADMIN` | **403** | Authorization |
| Actual POST origin hợp lệ, credentials đúng, thiếu CSRF | **403** | `CsrfFilter` |
| Actual GET origin không được phép dù Basic đúng | **403** | CORS actual request |
| Request không có `Origin`, Basic đúng | Có thể **200** | Không áp CORS browser, vẫn phải xác thực |

HTTP Basic thường trả 401 với `WWW-Authenticate`. Nếu app dùng form login thay vì Basic, request thiếu credentials có thể nhận 302 về `/login`. **403 không có nghĩa luôn sai role**: có thể do CORS processor hoặc `CsrfFilter`. Muốn chẩn đoán phải xem method, Origin, preflight headers và nơi sinh response.

## 8. Demo runnable Java 17, Spring Boot 3.5.12

Ta xây một backend với hai user cục bộ:

- `alice / alice123` có `ROLE_USER`.
- `admin / admin123` có `ROLE_ADMIN`.

API có:

| Path | Method | Quyền |
| --- | --- | --- |
| `/public` | GET | Công khai, không dùng để thử cross-origin |
| `/api/me` | GET | Authentication hợp lệ |
| `/api/admin` | GET | `ROLE_ADMIN` |
| `/api/ping` | POST | Authentication và CSRF token; POST chỉ minh họa, không lưu dữ liệu |

Lab dùng **HTTP Basic chỉ trên localhost**, không phát JWT. Frontend `http://localhost:5173` chỉ là allowlisted origin để thử. Production phải dùng HTTPS, identity management, session/token flows an toàn; **không gửi password trong JavaScript frontend**.

### 8.1. Các file

```text
cors-auth-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/corsauth/
    │   ├── CorsAuthApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/corsauth/
        └── CorsAuthTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'cors-auth-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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

Cần JDK 17+ và Gradle 8.4+ tương thích. Vì ứng dụng phụ thuộc Spring libraries, dùng Gradle/Wrapper dựng classpath; không thể chạy chỉ bằng `javac`/`java` trần không có dependencies.

### 8.2. Main

**`src/main/java/com/example/corsauth/CorsAuthApplication.java`**

```java
package com.example.corsauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsAuthApplication.class, args);
    }
}
```

### 8.3. CORS + Authentication + Authorization

**`src/main/java/com/example/corsauth/SecurityConfiguration.java`**

```java
package com.example.corsauth;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        cfg.setAllowedOrigins(List.of("http://localhost:5173"));
        cfg.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cfg.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cfg.setAllowCredentials(false);
        cfg.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cfg);
        return source;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .cors(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .csrf(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

**Đọc cấu hình theo chức năng:**

1. `UrlBasedCorsConfigurationSource` chứa CORS policy cho `/api/**` với một frontend origin cụ thể; không cho `https://evil.example`.
2. `.cors(withDefaults())` tích hợp xử lý preflight trước bước đòi HTTP Basic authentication.
3. `Authorization` nằm trong allowed request headers, nhưng **không có credentials nào được gửi trong preflight**.
4. `.requestMatchers("/api/admin").hasRole("ADMIN")` đứng trước rule rộng `/api/**.authenticated()`, tránh điều kiện rộng che rule role.
5. `.httpBasic(withDefaults())` xác thực request thật; `formLogin(...disable())` tránh redirect HTML login trong demo API.
6. `.csrf(withDefaults())` giữ kiểm tra CSRF. Với `POST /api/ping`, `CsrfFilter` vẫn đòi token; preflight 200 không qua mặt CSRF.
7. `setAllowCredentials(false)` cho lab không dùng cookie login cross-origin. Muốn browser `credentials:"include"` với session thì phải thiết kế lại policy.
8. BCrypt hash password trong user store demo; mật khẩu trong tài liệu chỉ để học local.

### 8.4. Controller

**`src/main/java/com/example/corsauth/DemoController.java`**

```java
package com.example.corsauth;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin(Authentication auth) {
        return Map.of("admin", auth.getName());
    }

    @PostMapping("/api/ping")
    public Map<String, String> ping(Authentication auth) {
        return Map.of("status", "POST accepted", "user", auth.getName());
    }
}
```

Route `/api/ping` chỉ tạo response trong lab, không lưu dữ liệu thật. Nó là ví dụ method POST để quan sát CSRF. Ứng dụng thật cần authorization theo resource, transaction và input validation.

### 8.5. Chạy

```bash
gradle test
gradle bootRun
```

Với Gradle Wrapper đúng version, dùng `./gradlew test`/`./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat test`/`gradlew.bat bootRun` trên Windows. Ứng dụng chạy ở `http://localhost:8080` nếu cổng chưa bị chiếm và không có cấu hình khác.

### 8.6. Curl: so sánh preflight và actual request

**Preflight hợp lệ, không có Basic credentials:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Kỳ vọng **200** và `Access-Control-Allow-Origin: http://localhost:5173`, allowed methods/headers phù hợp. Không thêm `-u` vào preflight.

**Preflight sai origin:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: GET'
```

Kỳ vọng **403** từ CORS.

**Preflight xin DELETE chưa được phép:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
```

Kỳ vọng **403**.

**Actual GET origin được phép nhưng thiếu credentials:**

```bash
curl -i 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173'
```

Kỳ vọng **401 Unauthorized** do HTTP Basic. Nếu Spring Security tích hợp CORS đúng, browser origin được cho phép có thể nhìn thấy CORS headers trên response 401.

**Actual GET có credentials hợp lệ:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/me'
```

Kỳ vọng **200** với JSON chứa `"user":"alice"`.

**Actual GET role sai:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/admin'
```

Kỳ vọng **403** do `hasRole("ADMIN")`. Với `-u admin:admin123`, endpoint `/api/admin` trả **200** và `"admin":"admin"`.

**CORS từ chối origin dù credentials đúng:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: https://evil.example' \
  'http://localhost:8080/api/me'
```

Kỳ vọng **403** từ CORS. Nếu bỏ `Origin` mà vẫn có Basic credentials hợp lệ, `curl` có thể nhận **200**; CORS không là server firewall.

**POST có Basic đúng nhưng thiếu CSRF token:**

```bash
curl -i -X POST -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/ping'
```

Kỳ vọng **403** do `CsrfFilter`. Nếu preflight POST trước đó là 200, điều này vẫn đúng: **CORS và CSRF là hai quyết định độc lập**.

`curl` không tự thực thi browser preflight cache hay CORS blocking; nó chỉ cho bạn xem HTTP response từ server. Test browser thật vẫn cần thiết để xác minh frontend có đọc được response hay không.

### 8.7. MockMvc tests: preflight, Authentication, Authorization, CSRF

**`src/test/java/com/example/corsauth/CorsAuthTests.java`**

```java
package com.example.corsauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAuthTests {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightNeedsNoCredentials() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", FRONTEND))
            .andExpect(header().exists("Access-Control-Allow-Methods"))
            .andExpect(header().exists("Access-Control-Allow-Headers"))
            .andExpect(header().doesNotExist("WWW-Authenticate"));
    }

    @Test
    void preflightForPostDoesNotNeedCredentials() throws Exception {
        mvc.perform(options("/api/ping")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization, content-type"))
            .andExpect(status().isOk());
    }

    @Test
    void preflightRejectsUnknownOrigin() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void preflightRejectsUnlistedMethod() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsUnlistedHeader() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "X-Secret-Internal"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualWithoutAuthenticationIs401() throws Exception {
        mvc.perform(get("/api/me").header("Origin", FRONTEND))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", FRONTEND));
    }

    @Test
    void actualWithWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualWithCorrectAuthenticationIs200() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void allowedOriginDoesNotGiveAdminRole() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Origin", FRONTEND)
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void actualWithForbiddenOriginIs403() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", "https://evil.example")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void noOriginDoesNotRemoveAuthenticationRequirement()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preflightSuccessDoesNotBypassCsrf() throws Exception {
        mvc.perform(options("/api/ping")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isOk());

        mvc.perform(post("/api/ping")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/ping")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("POST accepted"));
    }
}
```

`httpBasic()` từ Spring Security Test dựng HTTP Basic credentials cho request thật; `csrf()` thêm một CSRF token hợp lệ **trong test**, không phải một giá trị cố định dành cho browser.

Các test chứng minh:
- Preflight **200 không có credentials**.
- Origin hợp lệ nhưng thiếu/sai credentials → actual **401**.
- User hợp lệ nhưng thiếu role → actual **403**.
- Origin lạ → CORS **403**.
- POST preflight **200** nhưng actual POST thiếu CSRF **403**; có auth và CSRF hợp lệ **200**.
- Không gửi Origin không khiến backend bỏ qua Authentication.

**Giới hạn:** `MockMvc` chưa chứng minh cookie behavior, CORS browser preflight cache, reverse proxy, TLS hay CDN đúng. Các bước đó cần kiểm thử trong browser và môi trường triển khai thật. Ví dụ code được rà soát tĩnh; kết quả `gradle test` là mục tiêu kỳ vọng, không được tuyên bố đã chạy trong bài này.

## 9. Multiple SecurityFilterChain: chọn chain trước, CORS trước auth trong chain

Có **hai thứ tự** cần kiểm tra:

1. `FilterChainProxy` chọn **SecurityFilterChain đầu tiên** matching request dựa trên `@Order` và `securityMatcher`.
2. Trong chain đã chọn, `CorsFilter` cần xử lý preflight **trước** các filter đòi authentication.

Một chain tổng quát đặt trước `/api/**` có thể che API chain, khiến CORS source intended cho API không được sử dụng. OPTIONS `/api/orders` có cùng path `/api/orders`, nên chain matcher chỉ cho GET mà không cho OPTIONS cũng có thể gây lỗi.

**Fragment multiple-chain:**

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(cors -> cors.configurationSource(apiCorsSource))
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(withDefaults())
        .build();
}
```

Đây **không phải file runnable độc lập**: cần imports và bean `apiCorsSource`, cùng fallback chain cho routes còn lại. Nếu có **nhiều `CorsConfigurationSource` beans**, Spring Security có thể không biết tự chọn nguồn nào; khi ấy chỉ định nguồn tường minh cho từng chain qua `configurationSource(...)`.

`securityMatcher` chọn chain, còn `requestMatchers` bên trong chain chọn authorization rule; đó không phải hai công cụ thay nhau.

## 10. Troubleshooting trong browser và proxy

Một hệ thống thật có thể có:

```text
Browser → CDN/ingress → API gateway → Servlet filters → Spring Security → MVC
```

Nếu gateway đòi login trước khi chuyển OPTIONS vào Spring Boot, thay đổi `http.cors(...)` ở backend chưa chắc sửa được.

**Trình tự điều tra:**

1. Mở **DevTools → Network** tìm OPTIONS và actual request riêng.
2. Với OPTIONS, xem `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, status và `Access-Control-Allow-Origin/Methods/Headers`.
3. OPTIONS **401/302**: có thể bị authentication/login entry point chặn trước CORS ở gateway hoặc filter chain.
4. OPTIONS **403**: kiểm tra origin/method/request headers allowlist; không mặc định do role.
5. OPTIONS **200**, GET **401**: CORS đã thành công; kiểm tra credentials trong request thật.
6. OPTIONS **200**, GET/POST **403**: xem role/scope/CSRF/CORS actual; xác định filter sinh lỗi.
7. Actual response server **200** nhưng JS vẫn báo CORS: kiểm tra header ACAO/ACAC trên **actual response**, duplicate ACAO, wildcard, redirects, cache và credentials mode.
8. Chỉ lỗi ở một số URL: xem CORS mapping `/api/**`, multiple chains, MVC `@CrossOrigin`, proxy path rewrite.
9. Chỉ lỗi sau deploy: xem scheme/host/port frontend thật, TLS redirect, gateway auth trên OPTIONS, `Vary` trên cache.
10. Không ghi Authorization header, access token, cookie session hoặc password thật vào logs/bug report.

| Quan sát | Khả năng chính |
| --- | --- |
| OPTIONS 401 + WWW-Authenticate | Authentication trước CORS |
| OPTIONS 302 về /login | Form login xử lý preflight |
| OPTIONS 403 | Origin/method/header bị CORS từ chối |
| OPTIONS 200, actual GET 401 | Lỗi authentication request thật |
| OPTIONS 200, actual GET 403 thiếu role | Authorization |
| OPTIONS 200, actual POST 403 thiếu CSRF | `CsrfFilter` |
| `curl` 200, browser không gửi GET | Browser preflight fail |
| Response 200 nhưng JS không đọc được | Actual CORS headers/credentials policy không đúng |
| Lỗi chỉ ở proxy | Gateway/ingress/cache/path rewrite |

## 11. Sai lầm thường gặp

| Sai | Đúng |
| --- | --- |
| “OPTIONS phải đăng nhập như GET” | Preflight được CORS xử lý **không phụ thuộc Authentication** |
| “OPTIONS permitAll là đủ” | Cần CORS processor trả allow headers chính xác |
| “200 preflight là API đã mở” | Request thật vẫn authn/authz/CSRF |
| “`Access-Control-Request-Headers: authorization` là token” | Nó chỉ ghi **tên** header |
| “CORS chặn mọi client không có origin” | CORS chủ yếu là **browser policy**, backend vẫn cần auth |
| “CORS error thì tắt CSRF” | CORS và CSRF khác nhau |
| “`@CrossOrigin` chắc chắn xử lý OPTIONS” | Security/gateway có thể chặn trước MVC |
| “`allowedOrigins("*")` với credentials=true vẫn ổn” | Không, cần origin cụ thể |
| “Khác origin nghĩa luôn khác site” | Hai khái niệm khác nhau |
| “Spring Security chỉ có một chain” | Có thể nhiều chains; kiểm tra `@Order`/`securityMatcher` |
| “Postman chạy tốt nghĩa CORS đúng” | Postman không tự chặn theo browser CORS |
| “403 luôn là thiếu ROLE_ADMIN” | CORS/CSRF cũng có thể 403 |

### Kiểm tra production trước release

Hãy xác nhận origin allowlist theo từng environment, CORS policy có trên đúng paths/chains, preflight không bị authentication ở gateway, actual vẫn bảo vệ bằng role/scope/object authorization, response 401/403 có headers phù hợp cho trusted origin, cookies/CSRF được kiểm tra với browser thật, CDN cache xét `Vary` và logs không làm lộ credentials.

## 12. Câu hỏi tự kiểm tra

**1.** Tại sao preflight thường không có `JSESSIONID` hay `Authorization` của actual request? — Vì preflight chỉ hỏi origin/method/headers có được phép không; browser không dùng nó như một request đã xác thực.

**2.** OPTIONS 200 có chứng minh Alice được vào `/api/admin` không? — Không. Actual GET vẫn có thể 403 nếu thiếu ROLE_ADMIN.

**3.** Hai URL `http://localhost:5173` và `http://localhost:8080` có cùng origin không? — Không, khác port.

**4.** `OPTIONS /** permitAll` vì sao không đủ? — Không tạo `Access-Control-Allow-*` và không xử lý policy CORS.

**5.** `Access-Control-Request-Headers: authorization` có chứa bearer token không? — Không, chỉ là tên header.

**6.** OPTIONS 200, GET 401 nghĩa là gì? — Browser được phép tiếp tục nhưng actual request thiếu/sai credentials.

**7.** OPTIONS 200, POST 403 có thể là lỗi gì? — CSRF hoặc authorization/CORS actual tùy request; phải kiểm tra filter gây lỗi.

**8.** Vì sao có thể GET 200 bằng curl dù CORS sai? — Curl không áp dụng browser CORS restrictions; Authn/Authz vẫn bảo vệ server.

**9.** Có thể dùng ACAO `*` với `Access-Control-Allow-Credentials: true` không? — Không; dùng origin cụ thể được phép.

**10.** Multiple chains cần kiểm tra hai thứ tự nào? — `@Order`/`securityMatcher` chọn chain, và CorsFilter trước bước đòi Authentication trong chain đó.

**11.** Cookie `SameSite=None; Secure` có tự cho phép cross-origin response không? — Không. Cookie policy và CORS response policy khác nhau.

**12.** Access token hợp lệ có thay thế CORS allowlist không? — Không; token xác thực request thật, CORS quyết định browser dùng cross-origin response.

**13.** CORS có thay CSRF token cho POST dùng cookie không? — Không. CORS và CSRF bảo vệ hai khía cạnh khác nhau.

**14.** API trả 401 ở preflight trong Spring Security thì kiểm tra gì trước? — CORS integration với chain/gateway và filter order, vì preflight không có credentials.

**15.** `Access-Control-Max-Age: 600` có phải token sống 600 giây không? — Không; đây là preflight cache duration.

## 13. Ghi nhớ

- **CORS phải được xử lý trước bước yêu cầu xác thực** đối với preflight.
- **Preflight không xác thực user**, không mang `Authorization` hoặc cookie login của actual request.
- Với Spring Security Servlet, bật `http.cors(withDefaults())` và cấu hình `UrlBasedCorsConfigurationSource` hoặc MVC source tích hợp hợp lệ.
- **200 preflight không mở endpoint**: actual request vẫn có thể 401/403/200.
- `OPTIONS permitAll` và tắt CSRF không phải giải pháp thay thế CORS.
- **CORS không phải authorization hay firewall**; curl/non-browser callers vẫn phải được bảo vệ bằng authn/authz.
- Credentials true phải dùng origin allowlist cụ thể, không `*`; browser cookie có những ràng buộc SameSite/Secure/CSRF riêng.
- Với nhiều chains/proxies, xác minh cả **thứ tự chọn chain**, **CorsFilter**, và nơi tạo response.
- Debug **OPTIONS và actual** riêng, không dựa vào một dòng “CORS error” của console.

### Tài liệu tham khảo

- Spring Security 6.5 — CORS: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html
- Spring Security — Java Configuration / Multiple Chains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework — Spring MVC CORS: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — MockMvc testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- MDN — CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Request.credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
