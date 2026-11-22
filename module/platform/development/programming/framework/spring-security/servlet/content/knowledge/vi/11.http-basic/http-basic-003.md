# Cấu hình httpBasic, realm và phản hồi WWW-Authenticate

> **Ngữ cảnh:** Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC trên **Servlet stack**. Bài này tập trung vào việc bật HTTP Basic bằng `HttpSecurity.httpBasic(...)`, cấu hình **realm** bằng `BasicAuthenticationEntryPoint`, hiểu header **`WWW-Authenticate`**, phân biệt 200/401/403 và xác minh bằng `curl` cùng `MockMvc`. Ví dụ dùng tài khoản trong bộ nhớ cho localhost; không dùng mật khẩu mẫu hoặc HTTP không mã hóa trong production.

## 1. Mục tiêu sau bài học

Bạn có thể:

1. Giải thích cặp header `Authorization: Basic ...` của **request** và `WWW-Authenticate: Basic realm="..."` của **response**.
2. Bật `httpBasic` trong Spring Security 6 bằng DSL lambda (không dùng `WebSecurityConfigurerAdapter` đã lỗi thời).
3. Đặt realm cố định, có ý nghĩa, quan sát HTTP **401 Unauthorized** cùng challenge khi chưa xác thực hoặc credentials sai.
4. Phân biệt **401** (cần credentials hợp lệ) với **403 Forbidden** (đã xác thực nhưng thiếu quyền).
5. Thực hiện bài thử tự động chứng minh header/status và tránh nhầm lỗi cấu hình security với lỗi định tuyến.
6. Nêu được giới hạn bảo mật của Basic: Base64 **không mã hóa dữ liệu**, phải dùng TLS, credentials thường được client gửi lại trên các request sau.

## 2. HTTP Basic là gì?

HTTP Basic là một cơ chế **HTTP authentication scheme**. Khi gửi thông tin xác thực, client tạo chuỗi `username:password`, mã hóa Base64 rồi gắn vào request header:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Authorization: Basic bGVhcm5lcjpkZW1vLXBhc3M=
```

Chuỗi Base64 trên tương ứng với cặp credentials trong ví dụ: `learner:demo-pass`. Đây **không phải mật mã**, không phải chữ ký và cũng không phải access token có thời hạn: bên đọc được header có thể giải mã credentials. Vì vậy **HTTPS là yêu cầu bắt buộc** khi triển khai ngoài máy cá nhân, kể cả trên các mạng nội bộ.

Đối với tài nguyên đòi authentication nhưng chưa có credentials hợp lệ, server trả **401** kèm một **challenge** để client biết kiểu xác thực cần sử dụng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="TrainingAPI"
```

Ý nghĩa của các phần:

- **`HTTP/1.1 401 Unauthorized`:** theo tên lịch sử là “Unauthorized”, nhưng thường có nghĩa là request chưa được **xác thực hợp lệ**.
- **`WWW-Authenticate`:** response header từ server mô tả một hoặc nhiều phương thức client có thể dùng để xác thực. Với Basic, challenge chứa scheme `Basic` và tham số `realm`.
- **`realm="TrainingAPI"`:** tên “vùng bảo vệ” (*protection space*) do server chọn; giúp user agent hiểu phạm vi credentials cho challenge. Nó **không phải password, role, tenant ID đáng tin cậy, hay một kiểm tra authorization**.
- **`Authorization: Basic ...`:** request header mà client gửi khi muốn thử authentication. Nó **không xuất hiện tự động chỉ vì server đã bật httpBasic**; client cần cung cấp credentials hoặc thực hiện phản ứng với challenge.

Cùng một URL có thể có hai vòng request: lần đầu không có `Authorization` → 401 + challenge; client gửi lại với `Authorization` → server kiểm tra username/password rồi cho qua hoặc trả 401 lần nữa.

### Realm không phải tên người dùng hoặc phạm vi Spring Security matcher

`realm` là thông tin của giao thức HTTP để mô tả protection space cho client. Đổi `"TrainingAPI"` thành `"PrivateArea"` **chỉ đổi challenge mà client nhìn thấy**; không thay `SecurityFilterChain`, không thêm role, không chặn endpoint và không tự quản lý user.

Một realm nên **ổn định, cố định, ngắn và ASCII dễ hiểu**. Không đưa dữ liệu do client kiểm soát trực tiếp vào realm vì đây là một phần của HTTP header; không dùng realm để truyền thông tin nhạy cảm. Browser có thể lưu/tự gửi lại Basic credentials cho vùng bảo vệ nó nhận diện; hành vi cụ thể phụ thuộc user agent và có thể khiến trải nghiệm “logout” khác với form login.

## 3. Luồng Servlet: ai gửi 401 và WWW-Authenticate?

Trong Spring Security Servlet, `BasicAuthenticationFilter` đọc `Authorization` header có scheme `Basic`, tạo `UsernamePasswordAuthenticationToken` chưa xác thực rồi gọi `AuthenticationManager`. Một manager thường dùng là `ProviderManager`, có thể ủy quyền cho `DaoAuthenticationProvider`, `UserDetailsService` và `PasswordEncoder` để kiểm tra mật khẩu.

Khi không có credentials, request vẫn đi qua các filter khác; đến bước HTTP authorization, Spring Security nhận ra endpoint yêu cầu `authenticated()`. `ExceptionTranslationFilter` chuyển trường hợp cần authentication sang `AuthenticationEntryPoint`. Với Basic, `BasicAuthenticationEntryPoint` có nhiệm vụ gửi HTTP **401** cùng `WWW-Authenticate`.

Khi credentials sai, bản thân `BasicAuthenticationFilter` có thể bắt `AuthenticationException` và gọi entry point đã cấu hình. Khi credentials hợp lệ nhưng thiếu role, bước authorization thường đưa về **403** qua `AccessDeniedHandler`; đây **không phải** yêu cầu gửi thêm mật khẩu.

```mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Container]
    B --> C[Spring Security filter chain]
    C --> D{Có Authorization Basic?}
    D -->|Có| E[BasicAuthenticationFilter]
    E --> F[AuthenticationManager / AuthenticationProvider]
    F -->|Credentials sai| J[BasicAuthenticationEntryPoint: 401 + WWW-Authenticate]
    F -->|Hợp lệ| G[Authenticated principal]
    D -->|Không| H[Tiếp tục tới authorization]
    G --> H
    H --> I{Quy tắc authorizeHttpRequests}
    I -->|Public permitAll| K[Spring MVC controller]
    I -->|Chưa xác thực, cần login| J
    I -->|Có login nhưng thiếu quyền| L[403 Forbidden]
    I -->|Đủ quyền| K
    K --> M[200 + response body]
```

**Điểm quan trọng:** `permitAll()` cho phép anonymous ở bước authorization nhưng **không tắt BasicAuthenticationFilter**. Vì vậy client gửi `Authorization: Basic` **sai** đến ngay cả endpoint public có thể nhận **401**, dù cùng endpoint không gửi header nào lại được 200.

## 4. Cấu hình dự án Spring Boot 3.x để thực hành

Tạo project từ Spring Initializr với **Java 17 hoặc 21**, **Spring Boot 3.x**, Gradle (Groovy DSL), dependencies **Spring Web**, **Spring Security**, **Spring Boot Starter Test** và **Spring Security Test**. Các dependency tương ứng bên trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là **block dependencies**, không phải toàn bộ `build.gradle`; plugins, repositories và phiên bản Boot được project Initializr cung cấp. Giữ Gradle wrapper đi cùng dự án.

Cấu trúc file cần tạo:

```text
src/
├── main/java/com/example/basic/
│   ├── BasicDemoApplication.java
│   ├── BasicSecurityConfig.java
│   └── DemoController.java
└── test/java/com/example/basic/
    └── BasicAuthHttpTest.java
```

### 4.1. Lớp khởi động

**`src/main/java/com/example/basic/BasicDemoApplication.java`**

```java
package com.example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

Đặt lớp `@SpringBootApplication` ở package gốc `com.example.basic` để Spring tìm được controller và security configuration.

### 4.2. Cấu hình SecurityFilterChain và realm

**`src/main/java/com/example/basic/BasicSecurityConfig.java`**

```java
package com.example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationEntryPoint;

@Configuration
public class BasicSecurityConfig {

    @Bean
    BasicAuthenticationEntryPoint basicEntryPoint() {
        BasicAuthenticationEntryPoint entryPoint =
                new BasicAuthenticationEntryPoint();
        entryPoint.setRealmName("TrainingAPI");
        entryPoint.afterPropertiesSet();
        return entryPoint;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            BasicAuthenticationEntryPoint basicEntryPoint
    ) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest()
                            .authenticated()
                )
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(basicEntryPoint))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(basicEntryPoint))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}
```

**Giải thích từng dòng có tác dụng bảo mật:**

1. **`basicEntryPoint()`** khai báo bean `BasicAuthenticationEntryPoint` với realm `"TrainingAPI"`. `setRealmName(...)` đặt tên vùng bảo vệ, `afterPropertiesSet()` xác nhận cấu hình realm hợp lệ. Khi `commence(...)` được gọi, entry point gửi HTTP **401** và header `WWW-Authenticate: Basic realm="TrainingAPI"`.
2. **`authorizeHttpRequests`** đặt `GET /api/public` là public; `GET /api/admin` cần `ROLE_ADMIN`; mọi request còn lại phải đăng nhập. Thứ tự matcher quan trọng: các rule đặc biệt trước `anyRequest()`.
3. **`httpBasic(basic -> basic.authenticationEntryPoint(...))`** bật HTTP Basic cho chain này và cấp entry point xử lý authentication failure của HTTP Basic.
4. **`exceptionHandling(ex -> ex.authenticationEntryPoint(...))`** dùng cùng entry point để giải quyết trường hợp một endpoint protected được truy cập mà chưa xác thực. Cấu hình rõ hai nơi giúp kết quả challenge cho request không có credentials và request có credentials sai nhất quán trong bài học này.
5. **Không bật form login** trong chain demo, nên endpoint protected không chuyển sang trang `/login`. Đây là lựa chọn có chủ đích cho client `curl`/API.
6. **PasswordEncoder** dùng cơ chế encoding phù hợp với Spring Security; password được mã hóa trước khi đưa vào kho user trong bộ nhớ. Không lưu plaintext password khi triển khai thật.
7. **`roles("ADMIN")`** tạo authority `ROLE_ADMIN`, tương ứng với `hasRole("ADMIN")`. User `learner` không có role này.

Không gọi `csrf.disable()`: mọi phép thử chính của bài đều là `GET`, không cần vô hiệu hóa bảo vệ CSRF. Khi mở rộng sang `POST`/`PUT`/`DELETE`, phải quyết định chính sách CSRF dựa trên session/cookie và cách gửi credentials của client. HTTP Basic **không tự làm cho mọi POST an toàn trước CSRF**.

**Ghi nhớ:** `BasicAuthenticationEntryPoint` được dùng để tạo response challenge; nó **không xác thực password**. Việc kiểm tra password thuộc `AuthenticationManager`/`AuthenticationProvider`. `realm` chỉ phục vụ giao thức/challenge.

### 4.3. Controller công khai, cần đăng nhập và cần quyền ADMIN

**`src/main/java/com/example/basic/DemoController.java`**

```java
package com.example.basic;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/private")
    public String privateEndpoint(Principal principal) {
        return "PRIVATE_OK: " + principal.getName();
    }

    @GetMapping("/api/admin")
    public String adminEndpoint(Principal principal) {
        return "ADMIN_OK: " + principal.getName();
    }
}
```

Controller chỉ quyết định route và body; nó **không tự công khai một URL** bằng tên `publicEndpoint`. Những rule thật sự nằm trong `SecurityFilterChain`. `Principal` cho thấy danh tính của request đã xác thực khi controller được phép chạy.

## 5. Chạy ứng dụng và đọc phản hồi HTTP

Tại thư mục project có Gradle wrapper:

```bash
# Linux / macOS
./gradlew bootRun

# Windows PowerShell
.\gradlew.bat bootRun
```

Khi thành công, embedded Servlet Container thường lắng nghe `http://localhost:8080` nếu chưa đổi `server.port`. Mở terminal thứ hai và giữ ứng dụng chạy trong terminal thứ nhất.

Trong PowerShell, nên dùng `curl.exe` để tránh alias `curl` của một số phiên bản Windows PowerShell. Tất cả lệnh dưới đây sử dụng credentials **giả lập, chỉ chạy trên localhost**.

### Thử 1 — Public, không gửi Authorization

```bash
curl -i http://localhost:8080/api/public

# Windows PowerShell:
curl.exe -i http://localhost:8080/api/public
```

**Kỳ vọng:** HTTP **200 OK**, body chính xác:

```text
PUBLIC_OK
```

Request vẫn đi qua security filters, nhưng `permitAll()` cho phép controller xử lý. Không có `WWW-Authenticate` ở response 200 của endpoint này trong cấu hình minh họa.

### Thử 2 — Protected, không có credentials

```bash
curl -i http://localhost:8080/api/private
```

**Kỳ vọng:** HTTP **401** với header quan trọng:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="TrainingAPI"
```

Không cần suy đoán body lỗi vì Spring Boot/container có thể tạo trang lỗi JSON/HTML hoặc body rỗng tùy environment. Header challenge và status là phần phải kiểm tra. Method `privateEndpoint` chưa được gọi.

### Thử 3 — Có username nhưng sai password

```bash
curl -i -u learner:wrong-pass http://localhost:8080/api/private
```

**Kỳ vọng:** **401**, vẫn có `WWW-Authenticate: Basic realm="TrainingAPI"`. Dù client đã gửi `Authorization`, xác thực thất bại khiến entry point phát challenge lần nữa. Không phân biệt “mật khẩu sai” với “username không tồn tại” bằng thông điệp quá chi tiết để tránh user enumeration.

### Thử 4 — Username/password đúng

```bash
curl -i -u learner:demo-pass http://localhost:8080/api/private
```

**Kỳ vọng:** HTTP **200** và body:

```text
PRIVATE_OK: learner
```

Ở đây `curl -u` tạo `Authorization: Basic ...`. `BasicAuthenticationFilter` xác thực rồi Spring Security tiếp tục request tới Spring MVC. `Principal.getName()` là `learner`.

### Thử 5 — Đã đăng nhập nhưng không có role ADMIN

```bash
curl -i -u learner:demo-pass http://localhost:8080/api/admin
```

**Kỳ vọng:** HTTP **403 Forbidden**, vì `learner` chỉ có `ROLE_USER`. Trường hợp này đã xác thực rồi, nên **không phải một Basic challenge mới** trong luồng mặc định của demo. Cố gửi lại cùng password không tạo thêm role.

### Thử 6 — Đăng nhập ADMIN

```bash
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

**Kỳ vọng:** HTTP **200** và body:

```text
ADMIN_OK: admin
```

Cùng endpoint `/api/admin` nhưng kết quả thay đổi theo authorities của caller. `realm` vẫn là `TrainingAPI` và không quyết định ai là admin.

### Thử 7 — Public nhưng cố tình gửi Basic credentials sai

```bash
curl -i -u learner:wrong-pass http://localhost:8080/api/public
```

**Kỳ vọng:** **401** trong cấu hình này, bởi `BasicAuthenticationFilter` xử lý header Basic có mặt và thất bại **trước** bước authorization `permitAll()`. So sánh với Thử 1 (không gửi header → 200) để không nhầm rằng một endpoint public luôn cho qua mọi `Authorization` header sai.

## 6. Bảng kết quả cần nhớ

| Request | Authorization header | Status kỳ vọng | `WWW-Authenticate` | Diễn giải |
|---|---|---:|---|---|
| `GET /api/public` | Không | **200** | Không | Endpoint được phép anonymous |
| `GET /api/private` | Không | **401** | `Basic realm="TrainingAPI"` | Chưa xác thực, phát challenge |
| `GET /api/private` | Basic sai | **401** | `Basic realm="TrainingAPI"` | Authentication thất bại |
| `GET /api/private` | `learner:demo-pass` | **200** | Không | Đã xác thực và được phép |
| `GET /api/admin` | `learner:demo-pass` | **403** | Thường không | Đã xác thực nhưng thiếu `ROLE_ADMIN` |
| `GET /api/admin` | `admin:admin-pass` | **200** | Không | Có `ROLE_ADMIN` |
| `GET /api/public` | Basic sai | **401** | `Basic realm="TrainingAPI"` | Filter kiểm tra header trước permitAll |

**Không kiểm thử bằng việc so sánh toàn bộ response body của 401/403:** server có thể định dạng khác nhau theo Spring Boot version, content negotiation và error handling. Điều cần khẳng định là **status + `WWW-Authenticate` ở 401**, và **200 + body controller** khi được phép.

### Khi nào 302 xuất hiện thay vì 401?

Với cấu hình form login, browser có thể nhận `302 Found`, header `Location: /login` và được dẫn tới trang đăng nhập. Đó là cơ chế khác HTTP Basic. Trong demo ta **chỉ bật HTTP Basic và đặt entry point rõ ràng** để kết quả 401/challenge nhất quán. Nếu một ứng dụng đồng thời dùng form login và Basic, phải kiểm tra request matcher, content negotiation và entry point được chọn trong từng ngữ cảnh.

## 7. Kiểm thử tự động bằng MockMvc

Bên cạnh thử `curl`, có thể khởi tạo Spring Boot test context và gửi request qua Spring MVC + Security filters bằng `MockMvc`. Dependencies test đã thêm ở mục 4. Đừng chỉ gọi trực tiếp Java method của controller: cách đó không kiểm tra `SecurityFilterChain` hoặc `WWW-Authenticate`.

**`src/test/java/com/example/basic/BasicAuthHttpTest.java`**

```java
package com.example.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void protectedEndpointSendsBasicChallenge() throws Exception {
        mvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }

    @Test
    void invalidPasswordSendsBasicChallengeAgain() throws Exception {
        mvc.perform(get("/api/private")
                    .with(httpBasic("learner", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }

    @Test
    void validBasicCredentialsAllowProtectedEndpoint() throws Exception {
        mvc.perform(get("/api/private")
                    .with(httpBasic("learner", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE_OK: learner"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("learner", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("ADMIN_OK: admin"));
    }

    @Test
    void invalidBasicHeaderCanBlockPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public")
                    .with(httpBasic("learner", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }
}
```

Chạy test:

```bash
# Linux / macOS
./gradlew test

# Windows PowerShell
.\gradlew.bat test
```

**Kỳ vọng:** Gradle báo `BUILD SUCCESSFUL` và bảy test pass khi project đúng như các file minh họa. Đây là **kết quả dự kiến khi chạy project**, không phải lời khẳng định đã chạy bài này trong môi trường tài liệu.

Test `httpBasic(...)` tạo header Basic thật cho `MockMvc`. Assertion `header().string(HttpHeaders.WWW_AUTHENTICATE, ...)` xác minh realm chính xác, không chỉ kiểm tra status 401. Điều này hữu ích khi refactor security config và vô tình làm mất Basic challenge.

## 8. Các cách cấu hình realm khác và điểm cần lưu ý

### 8.1. Khi chỉ cần Basic mặc định

Cấu hình tối thiểu:

```java
http.httpBasic(Customizer.withDefaults());
```

Đây là **snippet bên trong cấu hình HttpSecurity**, không phải file Java độc lập. Nó bật HTTP Basic với thiết lập mặc định, bao gồm entry point phù hợp do framework cấu hình. Nếu không khai báo realm riêng, tên realm mặc định của Spring Security có thể xuất hiện trong challenge. Không nên hard-code vào test một tên realm “tự đoán”; dùng realm được cấu hình rõ khi cần contract ổn định.

### 8.2. Khi cần thay realm

Trong demo, thay `entryPoint.setRealmName("TrainingAPI")` bằng `"OperationsAPI"`, khởi động lại, rồi gọi `GET /api/private` không có credentials. Status vẫn **401**, nhưng header đổi thành:

```http
WWW-Authenticate: Basic realm="OperationsAPI"
```

Tên realm không làm thay đổi `hasRole`, `permitAll`, endpoint hay danh sách user. Browser có thể xử lý credentials cache theo protection space mới; đừng xem việc đổi realm là cơ chế thu hồi password hoặc phiên.

### 8.3. Tại sao khai báo cùng entry point ở httpBasic và exceptionHandling?

Trong HTTP Basic có ít nhất hai nguyên nhân cần challenge:

- **Sai credentials trong BasicAuthenticationFilter:** filter đã đọc `Authorization` và authentication thất bại.
- **Không có credentials nhưng endpoint protected:** filter có thể không xác thực ai, và yêu cầu đăng nhập được phát hiện khi authorization xử lý anonymous request.

Cấu hình cùng `BasicAuthenticationEntryPoint` cho cả hai trường hợp giúp ta kiểm soát challenge thống nhất. Khi xây app phức tạp (có form login, Bearer tokens, nhiều security chains), **đừng tùy tiện gán một entry point toàn cục** cho mọi loại request; thay vào đó cấu hình theo `SecurityFilterChain` hoặc request matcher phù hợp.

### 8.4. Nhiều SecurityFilterChain và realm khác nhau

Ứng dụng có thể có chain API riêng và chain web riêng. Khi đó:

- Dùng `http.securityMatcher("/api/**")` để giới hạn chain API; một chain fallback khác bảo vệ những URL ngoài API.
- Chỉ chain **khớp đầu tiên** được `FilterChainProxy` chọn. Thứ tự chain/`@Order` ảnh hưởng kết quả.
- Các chain có thể dùng entry point hoặc scheme khác nhau, nhưng **realm không tự chọn chain**. Nếu một URL rơi nhầm chain web có form login, response có thể là 302 chứ không phải 401.
- Đừng tạo chain chỉ cho `/api/**` rồi vô tình bỏ mọi URL khác khỏi Spring Security. Mọi route nhạy cảm phải được bảo vệ bởi một chain phù hợp.

Trong demo đơn chain, tất cả endpoints thuộc cùng một `SecurityFilterChain`; vì thế kết quả thử nghiệm có thể đối chiếu trực tiếp.

## 9. Giải thích những lỗi hay gặp

### 9.1. `401` nhưng thiếu `WWW-Authenticate`

Kiểm tra xem 401 được tạo bởi `BasicAuthenticationEntryPoint` hay bởi controller/proxy/error handler khác. Nếu code tự viết `response.setStatus(401)` mà không thiết lập challenge, một Basic client sẽ không nhận được thông tin yêu cầu xác thực. Trong app dùng nhiều entry points, xác minh `exceptionHandling` và `httpBasic` có trỏ đúng entry point của chain đang chạy.

Ngoài ra, proxy/gateway có thể tạo 401 trước ứng dụng hoặc bỏ header khi chuyển tiếp. So sánh kết quả khi gọi trực tiếp service với kết quả qua gateway, chỉ bật logging HTTP an toàn, tuyệt đối không log raw Authorization header ở production.

### 9.2. Có Basic header nhưng vẫn 401

Xác nhận đúng hostname/port/path, user/password, cơ chế mã hóa password và rằng client thực sự gửi header. `Authorization: Basic ...` dùng cặp username/password, **khác** `Authorization: Bearer ...`. Nếu dùng `curl -u`, hãy dùng credentials demo chính xác.

Nếu password được lưu dưới dạng BCrypt nhưng `PasswordEncoder` kiểm tra kiểu khác, việc xác thực có thể thất bại. Trong ứng dụng thực, đặt chuẩn encoding rõ ràng, migration có kiểm soát và không log password để debug.

### 9.3. `GET /api/public` bị 401 bất ngờ

Đầu tiên thử **không gửi header**. Nếu request không có credentials trả 200 nhưng gửi Basic sai trả 401, đó là hành vi hợp lý theo ví dụ vì Basic filter xử lý credentials có mặt trước khi `permitAll`.

Nếu **không có credentials vẫn 401**, kiểm tra matcher có đúng HTTP method và path không, `SecurityFilterChain` bean có được load không, có `server.servlet.context-path`/gateway prefix không và có chain khác bắt request trước không.

### 9.4. `403` thay vì `401`

Đã xác thực nhưng thiếu role thường là **403**. Với `learner` truy cập `/api/admin`, gửi lại cùng credentials không thêm `ROLE_ADMIN`. Mặt khác, `403` trên `POST` có thể do CSRF, không phải quyền. Không vô hiệu hóa CSRF mù quáng chỉ để đổi status; kiểm tra phương thức, cookie/session và CSRF token.

### 9.5. Browser hiện popup hoặc tiếp tục gửi credentials

Browser có thể hiện hộp thoại Basic challenge và nhớ credentials cho protection space. HTTP Basic **không có chuẩn “logout” riêng tương đương vô hiệu hóa session**. Việc gọi endpoint logout không đảm bảo browser xóa credentials đã cache; cần thiết kế auth phù hợp (thường form login/OIDC) nếu sản phẩm cần logout có thể dự đoán.

Khi debug, dùng `curl` hoặc một browser profile sạch để tránh credentials cũ. Đừng đưa ví dụ password thật vào command line trong môi trường nhiều người vì shell history/process inspection có thể tiết lộ.

### 9.6. `WWW-Authenticate` khác chính tả/kiểu chữ

Tên HTTP header không phân biệt hoa-thường theo giao thức; giá trị header có thể có tham số khác tùy server và cơ chế. Trong demo dùng `BasicAuthenticationEntryPoint` với realm tĩnh để test chính xác. Trong môi trường khác, hãy ưu tiên kiểm tra ý nghĩa giao thức và các tham số được cấu hình, không dựa vào thứ tự toàn bộ headers.

### 9.7. 404 bị che bởi 401

Với `anyRequest().authenticated()`, `GET /api/does-not-exist` không có Basic credentials có thể nhận 401 **trước khi MVC kiểm tra có controller hay không**. Hãy thử credentials hợp lệ rồi mới kết luận route tồn tại. Một URL không tồn tại không nhất thiết lập tức trả 404 nếu Security filter chặn trước.

## 10. Bảo mật khi sử dụng HTTP Basic trong hệ thống thật

1. **Luôn dùng HTTPS/TLS:** Base64 không che giấu password; mọi intermediary thấy request header sau khi giải mã TLS tại điểm kết thúc TLS cần được bảo vệ phù hợp.
2. **Không hard-code password:** user/role trong bộ nhớ và `demo-pass` chỉ để luyện tập. Dùng identity store, secrets management, password encoder phù hợp và MFA nếu threat model yêu cầu.
3. **Không ghi Authorization vào log:** cẩn thận với reverse proxy, observability/tracing, error reports và `curl -v`. Không dán ảnh chụp có credentials lên ticket công khai.
4. **Không nhầm realm với quyền:** Authorization phải ở `authorizeHttpRequests` và/hoặc method security. Realm không kiểm soát role, account, JWT hay tenant.
5. **Không coi Basic tự đảm bảo stateless:** Basic thường gửi credentials cho mỗi request, nhưng session persistence phụ thuộc security/session configuration. Với API muốn stateless, cần cấu hình session policy rõ và kiểm thử.
6. **Có rate limiting và brute-force protection:** một endpoint Basic công khai ra Internet có thể bị thử password liên tục. Cần monitoring, throttling, lockout policy có kiểm soát và bảo vệ account enumeration.
7. **CSRF tùy mô hình client:** trình duyệt có thể tự đính Basic credentials trong một số ngữ cảnh; cần đánh giá CSRF khi có hành động thay đổi trạng thái. Không tự động tắt `csrf` chỉ vì đang dùng HTTP Basic.
8. **Cân nhắc client UX:** Basic phù hợp một số client script/diagnostic/internal API qua TLS, nhưng không lý tưởng cho browser app cần login/logout UX và MFA. Với ứng dụng hiện đại, cân nhắc form login có session an toàn, OIDC hoặc OAuth2 resource server tùy kiến trúc.
9. **Phân biệt `Authorization` với `WWW-Authenticate`:** header thứ nhất do client gửi credentials; header thứ hai do server gửi challenge. Không copy credentials vào response.
10. **Đổi password/thu hồi:** khi Basic credentials bị lộ, phải đổi/khóa tài khoản và kiểm soát phiên/token song song nếu hệ thống hỗ trợ nhiều phương thức xác thực; đổi realm không thu hồi bí mật bị lộ.

## 11. Bài tập tự kiểm chứng

**Bài 1.** Đổi realm từ `TrainingAPI` sang `InternalAPI`. Giữ nguyên các user/roles. So sánh HTTP status, `WWW-Authenticate` và kết quả truy cập `/api/admin`.  
**Kết quả:** header challenge đổi realm; permission vẫn theo `hasRole("ADMIN")`.

**Bài 2.** Gọi `/api/private` ba lần: không credentials, sai password, đúng password. Với mỗi lần, ghi lại status, sự tồn tại của `WWW-Authenticate` và response body.  
**Kết quả:** 401 + challenge; 401 + challenge; 200 + `PRIVATE_OK: learner`.

**Bài 3.** Gọi `/api/public` không header và với Basic password sai. Vì sao có thể nhận hai status khác nhau?  
**Kết quả:** `permitAll()` không bỏ qua `BasicAuthenticationFilter`; header không hợp lệ vẫn có thể kích hoạt authentication failure.

**Bài 4.** Truy cập `/api/admin` bằng `learner` rồi `admin`.  
**Kết quả:** 403 và 200; realm không phải cơ chế phân quyền.

**Bài 5.** Bỏ cấu hình `exceptionHandling(ex -> ex.authenticationEntryPoint(...))` và thử lại client browser lẫn `curl`. Quan sát challenge nào thực sự được chọn trên phiên bản Spring Security đang dùng, rồi khôi phục cấu hình rõ ràng.  
**Mục tiêu:** hiểu rằng entry point có thể bị ảnh hưởng bởi nhiều authentication mechanisms và request matchers.

**Bài 6.** Thêm `GET /api/unknown` không có controller. Gọi không credentials và có credentials hợp lệ.  
**Mục tiêu:** phân biệt 401 từ security filter với 404 từ Spring MVC, tránh chẩn đoán sai một route.

## 12. Ghi nhớ

- Bật **HTTP Basic** trong Servlet Spring Security 6 bằng `http.httpBasic(...)`.
- **`BasicAuthenticationEntryPoint`** cấu hình `realm` và gửi **401 + `WWW-Authenticate: Basic realm="..."`** khi client cần xác thực.
- **`Authorization: Basic ...`** do client gửi; Base64 không bảo mật password. **Dùng HTTPS.**
- **401**: thiếu hoặc sai credentials, thường cần Basic challenge. **403**: đã xác thực nhưng không đủ quyền; thường không yêu cầu challenge Basic mới.
- **`permitAll()`** không loại Security filter; một Basic header sai vẫn có thể làm public endpoint trả 401.
- Realm **không thay thế** `authorizeHttpRequests`, roles, password encoder hoặc session security.
- Test tốt cần kiểm tra cả **HTTP status, `WWW-Authenticate`, body controller** và hành vi theo quyền; không chỉ một status 200.

**Nguyên tắc cuối:** `httpBasic` bật giao thức, `BasicAuthenticationEntryPoint` mô tả challenge bằng realm, `AuthenticationManager` xác minh danh tính, và authorization rules quyết định tài nguyên được truy cập. Các trách nhiệm này khác nhau nhưng phối hợp trên cùng một HTTP request.