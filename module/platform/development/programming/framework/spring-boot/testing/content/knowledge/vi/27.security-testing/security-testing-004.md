# CSRF token và phân biệt lỗi CSRF với lỗi phân quyền trong Spring Boot

Trong Spring Boot sử dụng **Spring Security**, hai HTTP request cùng trả **403 Forbidden** có thể thất bại ở **hai cơ chế hoàn toàn khác nhau**:

- **CSRF** (*Cross-Site Request Forgery*): request cần bảo vệ nhưng **thiếu token hoặc gửi token không hợp lệ**, nên `CsrfFilter` từ chối **trước khi** request tới controller hoặc được đánh giá quyền truy cập.
- **Phân quyền (authorization)**: request đã qua kiểm tra CSRF nhưng danh tính đang có **không đủ authority/role** để gọi endpoint, nên `AuthorizationFilter` hoặc method security từ chối.

Vì vậy câu kết luận “POST trả 403 nghĩa là user thiếu quyền ADMIN” thường **không có đủ căn cứ**. Một request của chính ADMIN mà thiếu CSRF token cũng có thể nhận 403. Ngược lại, người dùng có role USER gửi token hợp lệ vẫn có thể nhận 403 khi endpoint đòi ADMIN.

Bài này thuộc nhóm **Bảo mật** của **Spring Boot - testing**. Nội dung bao gồm cơ chế CSRF với session/cookie, cách đọc HTTP 401/403/302 theo cấu hình, kiểm tra các lớp filter, chiến lược test bằng `MockMvc` và `spring-security-test`, token thiếu/sai/hợp lệ, vai trò USER/ADMIN, phương thức GET/POST/PUT/DELETE, cấu hình dành cho API Bearer/SPA, chẩn đoán lỗi thực tế và dự án **Java 17 + Spring Boot 3.5 + Spring Security 6.5 + JUnit Jupiter** có thể chạy bằng Maven.

> **Nguyên tắc:** chỉ nhìn **HTTP status=403** là chưa đủ để xác định nguyên nhân. Hãy dùng một request đối chứng có **token hợp lệ**, quan sát authentication/authority, và kiểm **loại exception/filter đã từ chối** trong môi trường chẩn đoán an toàn.

## 1. CSRF không phải là phân quyền

### 1.1. Tại sao trình duyệt dễ bị CSRF?

Giả sử người dùng đang đăng nhập `https://bank.example` bằng **session cookie**. Khi họ truy cập một website khác có nội dung độc hại, trình duyệt có thể tự động gửi request tới bank và **đính kèm credential theo cơ chế tự động của trình duyệt**, phụ thuộc SameSite/cookie/CORS/browser context. Nếu bank chỉ dựa vào cookie để nhận diện người dùng mà không bảo vệ thao tác thay đổi state, website bên ngoài có thể **kích hoạt hành động ngoài ý muốn**.

```text
Victim browser
   |  (đang có session cookie của bank)
   |
   +--- trang attacker kích hoạt form POST /transfer
   |
   +--- browser gửi cookie bank theo cookie policy
   |
   v
Bank server
   |-- Authentication: cookie/session hợp lệ -> user đã đăng nhập
   |-- Authorization: user được chuyển tiền từ tài khoản của mình
   |-- CSRF validation: thiếu/sai anti-CSRF token -> CHẶN
```

**CSRF protection** nhằm chống một kênh **lạm dụng credential được gửi tự động**. Nó không thay thế việc kiểm ai được thao tác lên đối tượng nào, giới hạn giao dịch, kiểm quyền sở hữu, hay anti-fraud rules.

Một token CSRF thường là **giá trị khó đoán**, được gắn với session hoặc cơ chế lưu state cụ thể. Client hợp lệ đưa token vào hidden form field hoặc header, còn trang ngoài nguồn gốc không thể tùy ý đọc token đó nếu ứng dụng cấu hình và browser security đúng. Spring Security kiểm token từ request so với token đã lưu.

**Không dùng CSRF token làm access token**: token CSRF không chứng minh danh tính, không cấp role, không thay thế session/JWT hay permission. Có token hợp lệ mà không được cấp role ADMIN vẫn phải 403 khi thao tác quản trị.

### 1.2. Phân quyền khác CSRF như thế nào?

| Tiêu chí | CSRF | Authentication | Authorization |
|---|---|---|---|
| Câu hỏi | Request thay đổi state có thật sự đến từ luồng hợp lệ đã có token? | Ai đang gọi? | Người đó được phép làm gì? |
| Dựa vào | Token/cookie/session/repository/handler | Session, Basic, Bearer, form login... | Roles, authorities, ownership, policy |
| Bộ phận điển hình | `CsrfFilter` | Authentication filters / manager | `AuthorizationFilter`, `@PreAuthorize` |
| Request thiếu điều kiện | Thường **403** nếu cần CSRF | Có thể **401** hoặc **302 login**, tùy entry point | Người dùng đã auth nhưng thiếu quyền thường **403** |
| Cách sửa | Truyền token đúng, đồng bộ session/cookie | Đăng nhập hoặc đưa credential hợp lệ | Cấp quyền thích hợp/sửa rule nghiệp vụ, không giả mạo role |
| Không được làm | Vô hiệu toàn bộ CSRF để chữa test | Hardcode giả user vào production | Cho phép role rộng để test hết 403 |

**401 không được bảo đảm cho mọi request chưa đăng nhập**: với form login, Spring Security có thể **302 Redirect** tới trang đăng nhập; với Basic/Bearer, thường là 401. Với POST **không có token**, `CsrfFilter` có thể từ chối bằng 403 **trước khi** luồng authentication entry point quyết định 401/302.

## 2. CSRF filter xử lý request như thế nào?

Spring Security Servlet sử dụng `CsrfFilter` cùng `CsrfTokenRepository` và `CsrfTokenRequestHandler`.

```text
HTTP request
   |
   v
SecurityFilterChain
   |
   v
CsrfFilter
   |
   +-- HTTP method cần CSRF protection?
   |      |-- Không (GET, HEAD, OPTIONS, TRACE mặc định)
   |      |          |
   |      |          +--> tiếp tục filter chain
   |      |
   |      +-- Có (POST, PUT, PATCH, DELETE ... mặc định)
   |                 |
   |                 v
   |       Load expected token theo repository
   |                 |
   |       Resolve submitted token từ request
   |                 |
   |       Compare token?
   |         |-- Thiếu/sai -> CsrfException
   |         |                -> AccessDeniedHandler
   |         |                -> 403
   |         |
   |         +-- Hợp lệ -> tiếp tục filter chain
   |
   v
Authentication / Authorization
   |
   +-- Chưa đăng nhập -> AuthenticationEntryPoint -> 401/302 tùy cấu hình
   |
   +-- Có auth nhưng thiếu role/authority -> AccessDeniedException -> 403
   |
   +-- Đủ quyền -> Controller / business service
```

### 2.1. Phương thức HTTP nào mặc định cần token?

Spring Security Servlet mặc định **bỏ qua CSRF với GET, HEAD, TRACE, OPTIONS** và kiểm với các phương thức khác; trong ứng dụng REST thường là POST, PUT, PATCH, DELETE.

| Method | Mặc định cần CSRF? | Lý do |
|---|---|---|
| `GET /api/admin/summary` | Không | GET nên là thao tác an toàn/read-only |
| `HEAD /api/admin/summary` | Không | Safe HTTP method |
| `OPTIONS /api/admin/tasks` | Không | Thường liên quan preflight; authorization/CORS vẫn riêng |
| `POST /api/admin/tasks` | **Có** | Tạo dữ liệu |
| `PUT /api/admin/tasks/1` | **Có** | Cập nhật |
| `PATCH /api/admin/tasks/1` | **Có** | Cập nhật một phần |
| `DELETE /api/admin/tasks/1` | **Có** | Xóa |
| `GET /api/delete?id=1` | Không mặc định | **Thiết kế sai** nếu GET thực sự xóa state |

**Không dựa vào “GET không cần CSRF” để cho phép GET gây side effect.** HTTP method semantics là một phần quan trọng của thiết kế bảo mật. Nếu ứng dụng có matcher tùy biến, hành vi có thể khác bảng mặc định; test phải theo `SecurityFilterChain` thực tế.

### 2.2. Token nằm ở đâu?

Với form HTML, token có thể nằm trong hidden input tên `_csrf`; với JavaScript client, thường gửi header `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` theo cơ chế handler/repository.

```http
POST /api/admin/tasks HTTP/1.1
Cookie: JSESSIONID=session-example
X-CSRF-TOKEN: csrf-token-example
Content-Type: application/json

{"name":"create-report"}
```

Đây là **HTTP request minh họa**, không phải token thật và không thể copy chạy nếu token không khớp server session. **Cookie session và token phải thuộc cùng security context**, nếu session timeout/rotated thì token cũ có thể invalid.

### 2.3. Hai ngoại lệ CSRF quan trọng

Spring Security cung cấp:

- `org.springframework.security.web.csrf.CsrfException`: lớp gốc cho lỗi CSRF, thuộc nhánh `AccessDeniedException`.
- `MissingCsrfTokenException`: có tình huống không tìm được **expected token** cần thiết trong repository.
- `InvalidCsrfTokenException`: token dự kiến không khớp token client cung cấp.

**Không khẳng định “thiếu header luôn là MissingCsrfTokenException”**: Spring Security có thể đã tạo/lưu expected token và khi client không gửi token, loại thực tế là `InvalidCsrfTokenException`. Ở mức phân loại nguyên nhân, dùng `instanceof CsrfException` đáng tin hơn suy từ message hoặc một subtype cụ thể.

Khi lỗi phân quyền, có thể thấy `AccessDeniedException` hoặc loại như `AuthorizationDeniedException` (tùy Spring Security version/path). Vì `CsrfException` cũng là một dạng `AccessDeniedException`, mọi đoạn code kiểu `if (ex instanceof AccessDeniedException) { authorization }` sẽ **phân loại nhầm CSRF**. Phải kiểm `CsrfException` **trước**, rồi mới xếp các `AccessDeniedException` còn lại vào nhóm phân quyền/chính sách truy cập.

## 3. 403 là triệu chứng, không phải nguyên nhân

| Case | Authentication | CSRF | Authority | Kết quả thường thấy |
|---|---|---|---|---|
| GET public | Anonymous | Không yêu cầu | Public | **200** |
| GET admin | Anonymous | Không yêu cầu | Thiếu authentication | **401** (trong cấu hình demo) |
| GET admin | USER | Không yêu cầu | Thiếu ADMIN | **403 authorization** |
| GET admin | ADMIN | Không yêu cầu | Đủ ADMIN | **200** |
| POST admin | Anonymous | **Thiếu** | Chưa đánh giá role | **403 CSRF** |
| POST admin | USER | **Thiếu** | Chưa đánh giá role | **403 CSRF** |
| POST admin | USER | **Sai token** | Chưa đánh giá role | **403 CSRF** |
| POST admin | USER | **Đúng token** | Thiếu ADMIN | **403 authorization** |
| POST admin | ADMIN | **Thiếu token** | Chưa đánh giá role | **403 CSRF** |
| POST admin | ADMIN | **Đúng token** | Đủ ADMIN | **201** |
| POST admin | Anonymous | **Đúng token** | Không có authentication | **401** (trong cấu hình demo) |

Các status **401** phía trên là do ví dụ cấu hình `AuthenticationEntryPoint` trả 401 có chủ đích. Một website dùng form login có thể redirect 302. Trên một ứng dụng có nhiều filter chains, rule matching cũng quyết định kết quả. **Không chẩn đoán bằng status một mình**, kể cả khi cùng là 403.

### Bài test đối chứng phân biệt hai 403

Muốn biết vì sao USER POST admin bị 403:

1. Gửi POST với USER, **không** CSRF → 403. Đây là bằng chứng *có thể* bị CSRF, chưa chứng minh authorization.
2. Gửi **cùng POST** với USER, **token hợp lệ** → vẫn 403. CSRF đã qua, vì vậy nguyên nhân lúc này phải tìm ở **role/authorization hoặc policy khác**.
3. Gửi cùng POST với ADMIN, token hợp lệ → 201. Điều này chứng minh endpoint và token test hợp lệ, rule role có hiệu lực.
4. Gửi POST với ADMIN, **bỏ token** → 403. Điều này chứng minh **role ADMIN không thay thế CSRF**.

Đừng “sửa” một test authorization bị 403 bằng cách **tắt CSRF toàn ứng dụng**. Hãy đưa token hợp lệ vào request để **cô lập lớp authorization**, rồi kiểm quyền một cách độc lập.

## 4. Spring Security 6.5 và CSRF token repository

Mặc định, Spring Security dùng `HttpSessionCsrfTokenRepository` lưu token với session, deferred loading và cơ chế request attribute handler. Kết quả thực còn tùy code cấu hình:

- **Server-rendered forms**: template có thể đọc token từ request attributes hoặc hỗ trợ của form tag.
- **REST AJAX dùng session cookie**: JavaScript phải lấy token bằng cơ chế an toàn rồi gửi header khi thay đổi state.
- **`CookieCsrfTokenRepository`**: server có thể lưu CSRF token trong cookie `XSRF-TOKEN`, browser frontend đọc khi được cho phép và gửi `X-XSRF-TOKEN`. Cấu hình `withHttpOnlyFalse()` chỉ dùng nếu JavaScript thực sự cần đọc cookie và chấp nhận tradeoff, không bật vì mọi cookie đều cần JS.
- **Spring Security 6.x XOR/BREACH protection**: `XorCsrfTokenRequestAttributeHandler` có thể che/mask token khi render. Token thô trong cookie không tự có cùng representation với token đã mask. Với SPA phải dùng request handler đúng theo hướng dẫn chính thức, không chỉ thêm cookie repository rồi kỳ vọng mọi header tự hoạt động.
- **Login/logout/session rotation**: Spring Security có thể xóa CSRF token cũ sau authentication success hoặc logout success; SPA cần **lấy lại token mới** trước POST kế tiếp.
- **Session timeout**: token gắn session cũ có thể hết hiệu lực. 403 lúc này không đồng nghĩa role bị thu hồi.

Một lỗi thường gặp: frontend nhận cookie `XSRF-TOKEN` nhưng quên gửi header `X-XSRF-TOKEN`, gửi token thuộc **session khác**, hoặc browser không gửi cookie vì `SameSite`/domain/path/Secure/credentials policy. Triệu chứng thường là 403 trên POST dù GET thành công.

### CORS và SameSite không thay thế CSRF

- **CORS** kiểm soát việc JavaScript từ origin khác được đọc response hoặc gửi một số request cross-origin; **không phải cơ chế chống mọi CSRF**. Một HTML form có thể tạo request mà không cần đọc response.
- **SameSite** cookie là một lớp giảm rủi ro, nhưng không nên thay thế toàn bộ thiết kế CSRF đối với ứng dụng dùng credentials tự động.
- **Authorization** trả lời ai được làm gì; **CSRF** trả lời request thay đổi state có đủ bằng chứng chống cross-site forgery hay không.

Không cần token CSRF cho mọi API như một quy tắc bất biến: quyết định dựa trên **kiểu client và cơ chế credential**, không chỉ HTTP status hay JSON format.

## 5. Ví dụ runnable Java 17 / Spring Boot 3.5: phân biệt nguyên nhân 403 bằng MockMvc

Ta tạo một Spring MVC ứng dụng rất nhỏ:

- `GET /api/public/ping`: không cần login.
- `GET /api/admin/summary`: cần role ADMIN, **không cần CSRF**.
- `POST /api/admin/tasks`: cần role ADMIN **và** CSRF token.
- `PUT /api/admin/tasks/7`, `DELETE /api/admin/tasks/7`: cũng là unsafe methods.
- Test dùng `.with(user("...").roles(...))` để giả lập authentication cho **từng request**; không phải gọi login API thật.
- Test dùng `.with(csrf())`, `.with(csrf().asHeader())` và `.with(csrf().useInvalidToken())` của `spring-security-test` để kiểm token.
- Cấu hình demo có **header chẩn đoán `X-Demo-Denial`** phân biệt `CsrfException` với denial còn lại. Header này **chỉ để học/test**, **không nên đưa chi tiết chính sách bảo mật vào response production**. Production có thể log nội bộ category/correlation ID và trả body 403 thống nhất.

Ví dụ dùng `@SpringBootTest(webEnvironment=MOCK)` kết hợp `@AutoConfigureMockMvc`, nạp **SecurityFilterChain thật của ứng dụng demo** vào MockMvc. Không cần network server bên ngoài, Docker hoặc database.

### 5.1. Cây thư mục

```text
csrf-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── DemoSecurityConfig.java
    │   └── DemoAdminController.java
    └── test/java/com/example/csrf/
        └── CsrfAuthorizationTest.java
```

### 5.2. POM Maven

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>csrf-authorization-demo</artifactId>
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

**Lý do tách dependencies:** `spring-boot-starter-security` cung cấp filter chain và authorization, còn **`spring-security-test`** cung cấp `csrf()`, `user()`, `@WithMockUser` và hỗ trợ MockMvc. Thiếu dependency test chuyên biệt này, ví dụ static import `SecurityMockMvcRequestPostProcessors.csrf` không biên dịch được. Parent Boot quản lý phiên bản tương thích; không pin ngẫu nhiên Spring Security 7 với Boot 3.5.

### 5.3. Application

File **`src/main/java/com/example/csrf/CsrfDemoApplication.java`**:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

Application có embedded servlet stack và tự scan controller/config bên dưới cùng package. Các JUnit tests chỉ khởi tạo MockMvc thông qua Spring test context, không mở TCP port thật.

### 5.4. SecurityFilterChain thật cho demo

File **`src/main/java/com/example/csrf/DemoSecurityConfig.java`**:

```java
package com.example.csrf;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfException;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class DemoSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Bật CSRF theo mặc định của Spring Security.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                // Cố định 401 cho anonymous trong ví dụ.
                // Form login ở ứng dụng khác có thể redirect 302.
                .authenticationEntryPoint((request, response, cause) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
                .accessDeniedHandler((request, response, denied) -> {
                    // Header CHỈ ĐỂ CHẨN ĐOÁN TRONG DEMO/TEST.
                    // Không expose loại failure chi tiết trong prod.
                    String category = denied instanceof CsrfException
                            ? "csrf" : "authorization";
                    response.setHeader("X-Demo-Denial", category);
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN);
                }));

        return http.build();
    }
}
```

**Tại sao handler phân biệt đúng hai loại?** `CsrfConfigurer` của Spring Security 6.5 lấy `AccessDeniedHandler` được cấu hình qua `ExceptionHandlingConfigurer` cho `CsrfFilter`; còn authorization failure đi qua `ExceptionTranslationFilter` với cùng handler. Ở đây ta kiểm `denied instanceof CsrfException` **trước**, sau đó phân loại denial khác. Handler **không thay đổi quyền**; nó chỉ báo trạng thái.

**Đừng đưa header `X-Demo-Denial` từ ví dụ vào production như một thông lệ**: phản hồi công khai có thể làm lộ chi tiết cơ chế kiểm soát. Trong hệ thật, ghi log/metric **server-side** theo category/correlation ID và giữ response message trung tính. Bài dùng header chỉ để có assertion trực tiếp và dễ học.

**Về role:** `hasRole("ADMIN")` mong authority `ROLE_ADMIN`, không mong chuỗi trần `ADMIN`. `user("...").roles("ADMIN")` trong test tạo authority đúng tiền tố. Nếu domain sử dụng authorities khác, dùng `hasAuthority("...")` và mô phỏng đúng token/claims.

**Về authentication:** bài không cung cấp login form/API. Test `user()` đưa mock authenticated principal vào security context để kiểm role, không phải mô phỏng quá trình kiểm mật khẩu/JWT thật. Production cần cấu hình authentication mechanism theo nhu cầu riêng.

### 5.5. Controller công khai và quản trị

File **`src/main/java/com/example/csrf/DemoAdminController.java`**:

```java
package com.example.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoAdminController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @PostMapping("/admin/tasks")
    public ResponseEntity<String> createTask() {
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body("task-created");
    }

    @PutMapping("/admin/tasks/7")
    public String updateTask() {
        return "task-updated";
    }

    @DeleteMapping("/admin/tasks/7")
    public ResponseEntity<Void> deleteTask() {
        return ResponseEntity.noContent().build();
    }
}
```

Controller không truy cập database và không làm side effect thật. Ta cố ý tách security filter behavior ra khỏi JPA/service logic để một lỗi 403 không bị nhầm với unique constraint hay transaction rollback. Đường dẫn cố định `/7` chỉ phục vụ demonstration, không phải API design production.

### 5.6. MockMvc integration tests: 14 ca độc lập

File **`src/test/java/com/example/csrf/CsrfAuthorizationTest.java`**:

```java
package com.example.csrf;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class CsrfAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicGetDoesNotNeedAuthenticationOrCsrf() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousAdminGetGets401NotCsrf403() throws Exception {
        mvc.perform(get("/api/admin/summary"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserAdminGetFailsAuthorization() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "authorization"));
    }

    @Test
    void adminGetSucceedsWithoutCsrf() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-summary"));
    }

    @Test
    void anonymousPostWithoutCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks"))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserPostWithoutCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserWithInvalidCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER"))
                .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserWithValidCsrfStillGetsAuthorization403()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER"))
                .with(csrf()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "authorization"));
    }

    @Test
    void adminPostWithValidCsrfParameterCreatesTask()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("task-created"));
    }

    @Test
    void adminPostWithValidCsrfHeaderCreatesTask()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf().asHeader()))
                .andExpect(status().isCreated())
                .andExpect(content().string("task-created"));
    }

    @Test
    void adminPostWithoutCsrfStillGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void adminPostWithInvalidCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void anonymousWithValidCsrfStillNeedsAuthentication()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(put("/api/admin/tasks/7")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }
}
```

**Đây là 14 phương thức `@Test` độc lập.** Test có cả anonymous, USER và ADMIN; CSRF token hợp lệ, thiếu và sai; method GET, POST, PUT. `DELETE` cũng mặc định cần CSRF, có thể bổ sung test tương tự `PUT` cho endpoint xóa (không cần dùng DELETE để chứng minh tất cả các test hiện tại).

### 5.7. Diễn giải 14 ca test và kết quả

| Nhóm | Case | Điều được chứng minh |
|---|---|---|
| Method safe | GET public anonymous | Không cần auth/CSRF ở public endpoint |
| Authentication | GET admin anonymous | 401 do `AuthenticationEntryPoint` demo, không phải CSRF |
| Authorization | GET admin USER | 403 **authorization**, GET không cần token |
| Authorization pass | GET admin ADMIN | 200, rule role đúng |
| CSRF ưu tiên | POST anonymous không token | 403 **csrf** trước authorization |
| CSRF ưu tiên | POST USER không token | 403 **csrf** dù user còn thiếu role |
| CSRF invalid | POST USER token sai | 403 **csrf**, không đánh đồng role |
| Authz riêng | POST USER token đúng | 403 **authorization** sau khi qua CSRF |
| Success | POST ADMIN token trong parameter | 201 Created |
| Success | POST ADMIN token qua header | 201 Created |
| CSRF không được role thay thế | POST ADMIN không token | 403 **csrf** |
| CSRF invalid ở ADMIN | POST ADMIN token sai | 403 **csrf** |
| Authentication riêng | POST anonymous token đúng | 401 theo cấu hình entry point |
| Method unsafe | PUT ADMIN không token | 403 **csrf**, ngay cả khi role đủ |

**Không chỉ kiểm status:** Bài đưa header diagnostic từ exception class để test xác định nhánh, đồng thời giữ **bài test đối chứng với token hợp lệ**. Khi đưa logic vào sản phẩm, hãy bỏ header công khai và thay bằng logs/metrics **server-side**, vẫn giữ các test kiểm role/token một cách tương đương.

**Không dùng `csrf()` như một phép giả lập login:** `csrf()` tạo request token hợp lệ trong MockMvc security test. Nó không chứng minh một trình duyệt thực đã nhận cookie/token và gửi trở lại đúng session. `user()` tạo principal giả cũng không kiểm password/SSO/JWT parsing. Các luồng đó cần thêm integration/end-to-end tests qua HTTP client/browser.

### 5.8. Cách chạy

Cần **JDK 17+**, Maven, không cần Docker:

```bash
mvn test
mvn -Dtest=CsrfAuthorizationTest test
```

Nếu dự án có Maven Wrapper, dùng `./mvnw test` hoặc `mvnw.cmd test` trên Windows. Với cấu hình hoàn chỉnh trên, kỳ vọng **Tests run: 14, Failures: 0, Errors: 0**. Không có stdout nghiệp vụ cố định; Surefire/JUnit/Spring Boot có thể log việc khởi tạo context.

Ví dụ là **mã được rà soát theo API Spring Boot 3.5 / Spring Security 6.5**, không phải tuyên bố đã thực thi Maven trong lúc biên soạn nội dung. Khi áp dụng thực tế, hãy chạy Maven trên project và xác minh behavior với configuration/filters của chính ứng dụng.

## 6. Khi không cần CSRF hoặc cần cấu hình riêng cho API?

### 6.1. Browser session + cookies

Với website đăng nhập bằng session cookie, CSRF **thường nên bật** cho unsafe methods. Thao tác POST từ browser sẽ kèm cookie theo cookie policy, nên anti-CSRF token là tuyến phòng thủ quan trọng. Không bỏ toàn bộ CSRF để chữa những test thiếu `.with(csrf())`.

### 6.2. API dùng Bearer token trong Authorization header

Một API chỉ phục vụ non-browser clients hoặc frontend gửi Bearer token **tự đặt vào header `Authorization`** và **không sử dụng credential được browser tự gắn** có mô hình CSRF khác. Có thể cấu hình `csrf.disable()` cho đúng chain/endpoint sau khi threat modeling chứng minh CSRF không còn là rủi ro dựa trên ambient credentials.

**“Stateless” không đủ để tự động tắt CSRF.** HTTP Basic credentials và một số cookie/authentication schemes có thể được trình duyệt gửi tự động, ngay cả khi backend không tạo server session. Nếu Bearer token được để **trong cookie** rồi trình duyệt tự gửi, rủi ro CSRF vẫn đáng xem xét. Không chỉ dựa vào `SessionCreationPolicy.STATELESS` hay endpoint trả JSON để quyết định bỏ CSRF.

Ví dụ scope CSRF cho một nhóm endpoint **thực sự không dùng browser credentials**:

```java
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/api/machine/**"));
```

Đây chỉ là snippet bên trong cấu hình `HttpSecurity`, không phải class hoàn chỉnh. Chỉ ignore đường dẫn đã được threat model và có authentication phù hợp; **không bao trùm `/api/**` tùy tiện** khi browser session còn dùng chung. Với nhiều `SecurityFilterChain`, cần kiểm chain nào match trước, tránh vô ý bỏ CSRF trên session endpoints.

### 6.3. SPA lấy token bằng cookie

Spring Security có `CookieCsrfTokenRepository.withHttpOnlyFalse()` cho trường hợp JavaScript thực sự cần đọc token cookie. Với Spring Security 6.x, cần cấu hình **request handler phù hợp XOR/BREACH** và cơ chế **refresh token sau login/logout**. Cấu hình cookie repository đơn thuần không chứng minh SPA có thể gửi token hợp lệ: token server render có thể masked trong request attribute, token cookie là raw, và client phải gửi đúng header.

**Checklist SPA:** SameSite/Secure/HttpOnly đúng policy, cookie domain/path chính xác, credentials mode và CORS phù hợp, lấy token mới sau authentication/logout, không log token, session chưa hết hạn, và test **hai requests thực** (lấy token rồi gửi unsafe request) trên cùng cookie jar.

## 7. Các lỗi thường gặp khi phân biệt 401/403

| Triệu chứng | Khả năng cao | Cách xác minh |
|---|---|---|
| GET public 200, POST authenticated 403 | Thiếu/sai CSRF token | Gửi token hợp lệ với cùng session; kiểm `CsrfException` |
| ADMIN POST 403 nhưng ADMIN GET 200 | CSRF áp dụng cho POST, GET bỏ qua | POST thêm `csrf()`, role giữ nguyên |
| USER POST 403 cả khi có CSRF | Thiếu authority hoặc access policy khác | So với ADMIN + token hợp lệ; xem `AuthorizationFilter`/method security |
| USER GET admin 403 | Authorization, vì GET mặc định không cần CSRF | Kiểm `ROLE_ADMIN`/`hasRole("ADMIN")` |
| Anonymous GET admin 302 | Form login entry point | Không coi 302 là CSRF; login/credential đúng |
| Anonymous POST admin 403 | Có thể CSRF filter chặn trước auth entry point | Kiểm token; thử anonymous + valid token đối chứng |
| MockMvc request thiếu `csrf()` | Test setup thiếu token chứ không phải production bug | Thêm `.with(csrf())` khi test authorization trên unsafe method |
| `csrf().useInvalidToken()` trả 403 | Đúng cơ chế CSRF | Assert CSRF branch, không kết luận user thiếu quyền |
| API đã gửi cookie nhưng vẫn 403 | Không có CSRF header hoặc sai cookie/session | Kiểm cookie jar/header, session rotation, mask/raw token |
| Sau login/logout POST đầu bị 403 | CSRF token cũ bị clear/rotate, SPA chưa refresh | Lấy token mới sau authentication/logout |
| PUT/PATCH/DELETE 403, GET 200 | Unsafe HTTP methods cần CSRF | Test token theo mỗi method |
| HTTP 401 từ JWT API | Chưa auth, token expired/signature sai | Kiểm authentication entry point/JWT, không gọi là CSRF |
| HTTP 403 từ JWT API | Thiếu scope/role, hoặc CSRF nếu chain đang bật | Kiểm security chain, exception root cause |
| CORS preflight fail | Browser cross-origin policy/filter order | Kiểm OPTIONS/CORS config, không “tắt CSRF” theo suy đoán |
| JSON POST 403 | CSRF không chỉ áp dụng form encoding | Kiểm session/cookie/CSRF policy, content type không tự tắt CSRF |
| Client 403 sau session timeout | Expected token không còn thuộc session | Reauthenticate/refresh token và retry có kiểm soát |
| Controller/`@PreAuthorize` 403 | Method security denial | CSRF hợp lệ rồi inspect method authorization |
| Test dùng `roles("ADMIN")` nhưng config `hasAuthority("ADMIN")` | Role tạo `ROLE_ADMIN`, không khớp chuỗi `ADMIN` | Đồng bộ role/authority conventions |
| Gọi `csrf.disable()` để mọi test xanh | Che mất lỗ hổng cho browser session | Giữ CSRF, sửa test token và config đúng scope |

### 7.1. Quy trình chẩn đoán một 403 thật

1. **Đọc method và URL**: GET hay POST/PUT/PATCH/DELETE? Đường dẫn có thuộc `SecurityFilterChain` mong đợi không?
2. **Kiểm authentication**: session có hợp lệ không, principal/roles/authorities nào có trong `SecurityContext`? Không log credential hoặc token raw.
3. **Kiểm CSRF**: token có được gửi trong header/parameter mong đợi không, có cùng session/cookie và chưa rotate/expire không?
4. **Chạy request đối chứng**: cùng principal, cùng endpoint, thêm **token hợp lệ**. Nếu chuyển từ CSRF 403 sang authorization 403, cả hai điều kiện đều có vấn đề nhưng ở thứ tự khác.
5. **Kiểm denial exception**: có `CsrfException`, `InvalidCsrfTokenException` hoặc `MissingCsrfTokenException` không; nếu không, xem authorization rule, method security, resource ownership.
6. **Xem log/filter chain có kiểm soát**: bật Spring Security DEBUG/TRACE trong môi trường test, không bật logging headers/tokens nhạy cảm vào production.
7. **Cố định bằng test regression**: thêm cả negative token test và positive token + role test; đừng dừng ở một assertion `isForbidden()`.

### 7.2. Lưu ý khi inspect log

Có thể bật logger test:

```properties
logging.level.org.springframework.security=DEBUG
```

Trong môi trường chẩn đoán có thể tăng một số logger có chọn lọc lên TRACE, nhưng phải kiểm nguy cơ log dữ liệu nhạy cảm. Dùng **correlation ID, request method/path đã sanitize, user ID đã pseudonymize, loại lỗi, tên security rule hoặc tên filter**, không ghi raw session cookie, Bearer token, CSRF token hoặc PII vào CI artifact.

Nếu cài custom `AccessDeniedHandler`, phải phân loại theo **`CsrfException` trước `AccessDeniedException`** như trong ví dụ. Một 403 do handler business tự trả không nhất thiết tới từ Spring Security; cần kiểm response writer/controller advice cả ngoài security chain.

## 8. Kiểm thử sâu hơn bằng browser, MockMvc và WebFlux

### 8.1. MockMvc kiểm SecurityFilterChain nhưng không mô phỏng trình duyệt

`MockMvc` + `spring-security-test` mạnh cho **filter behavior**, request matchers, CSRF token validation, role checks và controller mapping mà không cần TCP. Nhưng `with(csrf())` và `user()` **cung cấp trực tiếp trạng thái test**; chúng không chứng minh:

- HTML form thật có hidden field token.
- Browser tự lưu cookie/session, không leak token sang origin khác.
- SPA đọc cookie đúng và gửi header sau login/logout.
- Authentication provider kiểm password/SSO/JWT signature.
- Reverse proxy/CORS/SameSite và HTTPS hoạt động theo production.

Với website session, nên có thêm một test **HTTP/browser roundtrip**: mở GET nhận session và CSRF token, giữ cookie jar, POST không token → 403; POST với token + session → success nếu role đủ; logout/login đổi token, thử token cũ thất bại. Với API có OAuth2, cần test authentication/claims riêng.

### 8.2. Với WebFlux

Spring Security WebFlux sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và `CsrfWebFilter`, không dùng `HttpSecurity` Servlet filter. Test phù hợp là `WebTestClient` cùng Spring Security reactive test configurers:

```java
webTestClient.mutateWith(
        SecurityMockServerConfigurers.mockUser("alice")
                .roles("ADMIN"))
        .mutateWith(SecurityMockServerConfigurers.csrf())
        .post()
        .uri("/api/admin/tasks")
        .exchange()
        .expectStatus().isCreated();
```

Đây là **snippet**, không phải file chạy độc lập: cần `WebTestClient`, `spring-security-test`, WebFlux endpoint/config và import `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers`. Không copy `MockMvc.with(csrf())` của Servlet trực tiếp vào WebTestClient. Reactive CSRF repository mặc định thường gắn với WebSession, nhưng cookie/token handler semantics phải kiểm theo phiên bản.

### 8.3. Test slice so với full context

- **`@WebMvcTest`**: kiểm controller và Spring MVC slice; phải bảo đảm **SecurityFilterChain thật hoặc một config được import có chủ đích**. Nếu thay security bằng mock/fake không đại diện production, test pass không chứng minh policy thật.
- **`@SpringBootTest` + `@AutoConfigureMockMvc`**: nạp cấu hình Spring Security thật trong context, kiểm filter + controller mà không mở TCP. Đây là cách của ví dụ.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)`**: test HTTP socket thật, cookie jar/session/redirect và browser semantics khi cần end-to-end.
- **Unit test method security**: kiểm `@PreAuthorize` hoặc ownership policy với security context phù hợp, **không nhầm với CSRF**.

## 9. Bài thực hành tự kiểm

Trước khi xem đáp án, dự đoán response theo cấu hình demo (401 entry point, 403 denied):

| Request | Dự đoán |
|---|---|
| GET `/api/admin/summary` anonymous | **401** |
| GET `/api/admin/summary` USER | **403 authorization** |
| GET `/api/admin/summary` ADMIN | **200** |
| POST `/api/admin/tasks` ADMIN, thiếu CSRF | **403 csrf** |
| POST `/api/admin/tasks` USER, đúng CSRF | **403 authorization** |
| POST `/api/admin/tasks` ADMIN, đúng CSRF | **201** |
| POST `/api/admin/tasks` anonymous, đúng CSRF | **401** |
| POST `/api/admin/tasks` USER, sai CSRF | **403 csrf** |
| PUT `/api/admin/tasks/7` ADMIN, thiếu CSRF | **403 csrf** |

Lý giải: request unsafe phải qua `CsrfFilter` trước; chỉ khi token hợp lệ mới tới authentication/authorization. Role ADMIN không chứng minh token hợp lệ. Token hợp lệ không chứng minh principal đã đăng nhập. GET safe không bị CSRF chặn mặc định, nhưng vẫn chịu authorization.

### Những lỗi “sửa nhanh” không nên áp dụng

- **Tắt CSRF toàn cục** chỉ để POST test trả 201.
- **Bỏ `hasRole`** để user không còn nhận 403.
- **Cho mọi role là ADMIN** trong test để khỏi viết trường hợp denial.
- **Đưa `csrf()` vào tất cả requests** kể cả test âm tính muốn chứng minh thiếu token.
- **Bắt mọi `AccessDeniedException` và ghi nhận “permission denied”** mà không tách `CsrfException`.
- **Nhìn thấy 401 trong một hệ thống rồi mặc định hệ khác cũng 401**, dù form login redirect 302.
- **Lưu token CSRF vào log/copy paste từ test sang production**.
- **Chuyển sang Bearer token nhưng giữ token trong cookie tự gửi** rồi kết luận “stateless nên không có CSRF”.
- **Thêm `CookieCsrfTokenRepository.withHttpOnlyFalse()` mà không xét XOR handler, session rotation, cookie attributes và SPA token refresh**.

## 10. Checklist trước khi kết luận bài test bảo mật PASS

- [ ] Tôi xác định được cơ chế browser credential (session cookie, Basic, Bearer header/cookie) và nhu cầu CSRF.
- [ ] Tôi phân biệt được **authentication**, **authorization** và **CSRF**.
- [ ] GET/HEAD/OPTIONS/TRACE được xử lý theo chính sách, không dùng GET để thay đổi state.
- [ ] POST/PUT/PATCH/DELETE có negative tests thiếu/sai token khi chain bật CSRF.
- [ ] Với unsafe method, test quyền luôn có **CSRF token hợp lệ** để không bị CSRF che lỗi phân quyền.
- [ ] Cùng endpoint có đối chứng ADMIN/USER và token hợp lệ/thiếu/sai.
- [ ] Tôi không kết luận 403 là lỗi role chỉ từ status code.
- [ ] Phân loại exception theo `CsrfException` trước các denial khác.
- [ ] Với anonymous request, tôi biết 401 hay 302 tùy authentication entry point; CSRF vẫn có thể trả 403 trước.
- [ ] Tôi kiểm đúng `ROLE_ADMIN` vs `ADMIN` và không nhầm `hasRole` với `hasAuthority`.
- [ ] `spring-security-test` có trong test dependencies, không dùng mock user làm chứng cứ login/JWT thật.
- [ ] MockMvc có security filters, dùng cấu hình chain sát production.
- [ ] Nếu SPA, token được gửi từ cùng session/cookie, handler mask/raw đúng và refresh sau login/logout.
- [ ] Tôi không tắt CSRF cho browser app chỉ để làm test xanh.
- [ ] Nếu API không cần CSRF, tôi có threat model chứng minh không có ambient credentials, không chỉ dựa vào “stateless/JSON”.
- [ ] Tôi không log CSRF, session cookie, Bearer token hoặc thông tin nhạy cảm.
- [ ] Với nhiều filter chains hoặc @PreAuthorize, tôi đã xác định denial xuất phát ở đâu.
- [ ] Tôi biết giới hạn của MockMvc so với HTTP/browser end-to-end.
- [ ] Tôi chạy `mvn test` trên đúng version Spring Security/Boot của dự án và không chỉ nhìn PASS một test 403.

**Kết luận:** CSRF và phân quyền có thể cùng trả **403** nhưng khác **điều kiện, filter, cách sửa và cách test**. Hãy luôn dựng test **“cùng user, token thiếu/sai/đúng”** và **“cùng token đúng, USER/ADMIN”** để thấy rõ thứ tự. **Role đúng không thay thế token; token đúng không thay thế role.** Chỉ bỏ CSRF ở những API đã được đánh giá mô hình credential phù hợp.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Servlet Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 — CsrfConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
