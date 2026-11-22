# Bài thực hành CSRF, CORS và security headers với kiểm thử trình duyệt

> **Môi trường thực hành:** Spring Boot 3.5.x, Spring Security 6.x (Servlet / Spring MVC), Java 17+, Maven; trình duyệt Chromium và Playwright. Backend chạy tại `http://localhost:8080`; trang frontend độc lập chạy tại `http://localhost:5173`. Ví dụ dành cho máy phát triển **localhost**, không phải cấu hình bảo mật production. Các bước dùng CSRF mặc định, CORS allowlist chính xác và các HTTP security headers do Spring Security phát ra. Mục tiêu không chỉ là làm cho HTTP request “thành công” mà còn **tạo lỗi có chủ đích, quan sát chính xác trình duyệt và chứng minh cơ chế bảo vệ vẫn hoạt động**.

## 1. Kết quả cần đạt

Sau bài này, bạn phải thực hiện được cả bốn phần kiểm thử:

1. **CSRF:** form login/session cookie hoạt động; POST thiếu token bị 403; token từ trước login có thể không còn hợp lệ sau login; token mới dùng được; vai trò USER không thể gọi hành động yêu cầu EDITOR ngay cả khi CSRF hợp lệ.
2. **CORS:** trang ở `http://localhost:5173` gọi API ở `http://localhost:8080` qua `fetch` có `credentials: "include"`, preflight và các response headers phù hợp. Origin `http://127.0.0.1:5173` không nằm trong allowlist và bị browser chặn đọc cross-origin response.
3. **Security headers:** HTTP responses của backend có `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy` và `Referrer-Policy` theo cấu hình; một script inline được chèn vào **tài liệu HTML từ backend** bị CSP chặn, trong khi external script cùng origin vẫn chạy.
4. **Phân tích đúng giới hạn:** giải thích được vì sao một preflight 200 không cấp quyền thao tác, một CORS error không phải bằng chứng API đã được bảo vệ bằng authorization, một HTTP 403 chưa chắc là CSRF và vì sao HSTS không xuất hiện trên response HTTP localhost thông thường.

**Nguyên tắc cốt lõi:** CSRF, CORS và security headers là **ba cơ chế khác nhau**, có thể cùng xuất hiện trong một request nhưng không thay thế nhau.

## 2. Mô hình phòng thủ: đừng nhầm những cơ chế này

| Cơ chế | Mục đích bảo vệ | Ranh giới thực thi | Nó **không** thay thế |
| --- | --- | --- | --- |
| **CSRF token** | Chống request thay đổi trạng thái bị kích hoạt từ nơi khác trong khi browser tự đính kèm credential. | `CsrfFilter` phía server kiểm tra token ở unsafe HTTP request. | Authentication, authorization, chống XSS. |
| **CORS** | Quy định origin nào được **JavaScript trong browser** đọc response cross-origin, và các điều kiện request cross-origin. | Trình duyệt thực thi CORS; server phát các `Access-Control-Allow-*` headers. | Authentication, authorization hoặc giới hạn truy cập bằng curl/server-to-server. |
| **CSP** | Giảm rủi ro thực thi script không mong muốn, chèn nội dung, tải resource sai nguồn. | Browser áp dụng chính sách của **tài liệu HTML nhận CSP**. | Xử lý XSS bằng output escaping, kiểm soát backend permission. |
| **X-Frame-Options / frame-ancestors** | Chống nhúng UI vào frame trái phép / clickjacking. | Browser đối với tài liệu có header đó. | CSRF token/kiểm soát thao tác POST. |
| **X-Content-Type-Options: nosniff** | Hạn chế MIME sniffing cho một số resource. | Browser kiểm tra response MIME và context. | MIME cấu hình đúng hay validation input. |
| **HSTS** | Hướng browser dùng HTTPS cho host sau khi nhận policy qua HTTPS hợp lệ. | Browser theo trạng thái HSTS của host. | TLS/mTLS, reverse proxy và authorization. |
| **Referrer-Policy** | Điều chỉnh thông tin URL trong `Referer` khi điều hướng/tải resource. | Browser. | Ngăn log request nhạy cảm hay data leakage khác. |
| **Authorization** | Chỉ cho user/role/permission được phép gọi backend operation. | `SecurityFilterChain`, method security, domain policy và data layer. | Không có cơ chế nào trong ba cơ chế đầu thay thế được. |

**Vì sao phải test bằng browser thật?** MockMvc có thể kiểm tra response headers, CSRF filter và URL authorization, nhưng không tái tạo đầy đủ browser enforcing CORS, CSP, cookie jar, origin rules, preflight cache hay session transitions qua nhiều tab. Với một số điều kiện cần kiểm tra *chính hành vi browser*, phải dùng Playwright hoặc một công cụ browser tương đương.

## 3. Cấu trúc dự án cho bài thực hành

Tạo thư mục dự án:

~~~text
security-browser-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/securitylab/
│   │   │   ├── SecurityBrowserLabApplication.java
│   │   │   ├── SecurityConfig.java
│   │   │   └── ApiController.java
│   │   └── resources/static/
│   │       ├── index.html
│   │       └── app.js
│   └── test/java/com/example/securitylab/
│       └── HttpSecurityIntegrationTest.java
├── cors-client/
│   ├── index.html
│   └── client.js
└── browser-tests/
    └── tests/
        └── security.spec.js
~~~

**Cấu hình hai origin:**

~~~text
Origin A - Backend:
  http://localhost:8080
  Spring Boot: /, /app.js, /csrf, /api/public,
               /api/profile, /api/notes, /login

Origin B - Frontend:
  http://localhost:5173
  Python static server: /, /client.js

So sánh:
  scheme (http)  : giống
  hostname       : giống localhost
  port           : KHÁC 8080 vs 5173
  -> KHÁC ORIGIN theo browser
  -> cùng-site trong mô hình localhost cùng scheme
~~~

Hai origin khác cổng là **cross-origin**, nên fetch cross-origin bị quy tắc CORS chi phối. Nhưng chúng **cùng-site** theo mô hình schemeful same-site khi hostname/scheme cùng `localhost`; điều này có ý nghĩa với `SameSite` cookie. **Cross-origin không đồng nghĩa cross-site**. Vì vậy demo dùng `localhost` ở cả hai cổng; **đừng tự đổi phía frontend thành `127.0.0.1`** và mong cookie vẫn như cũ. Chúng khác host và không có cùng cookie jar.

## 4. Chuẩn bị Java, Maven, Node và browser

Kiểm tra công cụ:

~~~bash
java -version
mvn -version
node --version
npm --version
~~~

Cần Java 17 hoặc mới hơn trong dải tương thích với Boot 3.x; Maven 3.6.3+ và Node.js phiên bản hiện được Playwright hỗ trợ. Python 3 có thể dùng làm static development server; trên Windows có thể dùng `py` thay `python3`.

Trong `pom.xml` tạo Maven project như sau; đây là **POM đầy đủ của demo**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-browser-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
~~~

Phiên bản 3.5.0 trong POM là một **baseline cụ thể cho demo**, không phải tuyên bố về phiên bản Boot mới nhất. Trên dự án thật cần dùng phiên bản Boot/Security đang được hỗ trợ, đã vá bảo mật và kiểm thử lại DSL tương thích. Không trộn dependency Spring Security 5/`javax.servlet` vào Boot 3/`jakarta.servlet`.

## 5. Khởi động ứng dụng Spring Boot

File `src/main/java/com/example/securitylab/SecurityBrowserLabApplication.java`:

~~~java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityBrowserLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityBrowserLabApplication.class, args);
    }
}
~~~

Ứng dụng này sẽ phục vụ backend ở port 8080 khi không đặt `server.port` khác. Với dự án đã có cấu hình port riêng, đặt `server.port=8080` trong profile demo, không sửa cấu hình production.

## 6. SecurityConfig: CSRF còn bật, CORS allowlist, security headers

File `src/main/java/com/example/securitylab/SecurityConfig.java`:

~~~java
package com.example.securitylab;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/", "/index.html", "/app.js",
                    "/csrf", "/api/public", "/error"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/api/profile", true)
                .permitAll()
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "style-src 'self'; " +
                        "connect-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "form-action 'self'; " +
                        "frame-ancestors 'none'"
                    )
                )
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
            );

        return http.build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-test-password"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-test-password"))
                .roles("USER", "EDITOR")
                .build()
        );
    }
}
~~~

### 6.1 Đọc từng nhóm cấu hình, đừng bỏ qua

- `cors(Customizer.withDefaults())` cho phép Spring Security dùng `UrlBasedCorsConfigurationSource` bean. CORS cần được xử lý **trước authorization** để preflight không bị chặn chỉ vì chưa có session cookie.
- `csrf(Customizer.withDefaults())` giữ CSRF protection. `CsrfFilter` sẽ kiểm tra unsafe requests, kể cả POST login và POST nghiệp vụ trong mô hình dựa trên cookie.
- `GET /csrf` được phép cho anonymous để frontend lấy token phục vụ POST login. Token chỉ thuộc ngữ cảnh session hiện tại; response cần tránh bị cache, không để lộ qua CORS cho origin lạ.
- `POST /api/notes` yêu cầu `ROLE_EDITOR`. Có token CSRF đúng mà user chỉ có `ROLE_USER` vẫn bị 403.
- `.formLogin(...permitAll())` cung cấp generated login page, xử lý `POST /login` với CSRF; sau login thành công, trả redirect đến `/api/profile`.
- `anyRequest().denyAll()` là fallback fail-closed cho route chưa khai báo; production phải liệt kê thêm các route thực tế theo chính sách.
- `cors.setAllowedOrigins` liệt kê **đúng** `http://localhost:5173`, không phải `"*"`. Với `allowCredentials(true)`, không dùng `*` làm wildcard tùy ý cho mọi origin.
- `allowedMethods` và `allowedHeaders` xác định preflight được chấp nhận, **không** cấp quyền đối với endpoint. Browser có thể qua preflight nhưng POST thực bị authentication/authorization/CSRF chặn.
- `headers.contentSecurityPolicy(...)` tạo CSP rõ ràng cho document backend: chỉ script cùng origin; không cho inline script (vì không có `'unsafe-inline'`); không cho object, frame ancestors, base URL lạ.
- `referrerPolicy(NO_REFERRER)` giảm dữ liệu URL được gửi làm Referer; vẫn phải tránh đưa secrets vào URL.

### 6.2 Các security headers mặc định còn có gì?

Spring Security Servlet thường viết sẵn một số headers an toàn, ví dụ `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, các cache headers và `Strict-Transport-Security` **khi request sử dụng HTTPS**. Header chính xác còn phụ thuộc phiên bản/config và response.

**Quan trọng:** CSP **không tự có mặc định** cho mọi ứng dụng; bài này thêm tường minh. HSTS **không được kỳ vọng trên HTTP localhost**; production cần HTTPS đúng từ bên ngoài đến reverse proxy/app và HSTS policy phù hợp domain. Không thêm `includeSubDomains` hay `preload` máy móc: mọi subdomain phải thật sự hỗ trợ HTTPS tương ứng.

### 6.3 Vì sao không bật allowCredentials cho mọi origin?

Nếu app dùng session cookie, cho phép một origin độc hại đọc API credentialed responses có thể khiến dữ liệu người dùng bị lộ. Quy tắc:

- Không gửi `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`.
- Không phản chiếu mọi request `Origin` rồi bật credentials.
- Không đưa `null` origin vào allowlist nếu không có nhu cầu và biện pháp riêng; origin `null` xuất hiện trong các ngữ cảnh browser đặc biệt.
- Dùng hostname, scheme, port chính xác; `localhost:5173` khác `127.0.0.1:5173` và khác `https://localhost:5173`.
- Với deployment khác origin và **khác site**, phải thiết kế `SameSite=None; Secure`, HTTPS, CSRF và browser third-party-cookie policy cẩn thận. Demo chọn cùng-site localhost để giảm các biến số này.

## 7. API Controller cấp token, profile và thao tác thay đổi dữ liệu

File `src/main/java/com/example/securitylab/ApiController.java`:

~~~java
package com.example.securitylab;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    public record CsrfInfo(
            String headerName, String parameterName, String token) {
    }

    public record NoteRequest(String text) {
    }

    @GetMapping("/csrf")
    public ResponseEntity<CsrfInfo> csrf(CsrfToken token) {
        CsrfInfo info = new CsrfInfo(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(info);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @PostMapping("/api/notes")
    public ResponseEntity<Map<String, String>> createNote(
            @RequestBody NoteRequest note) {

        if (note == null ||
                note.text() == null ||
                note.text().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "text-required"));
        }

        // Demo: không ghi database, không có side effect thực.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "saved"));
    }
}
~~~

**Điểm bảo mật:**

- `GET /csrf` cung cấp `headerName` và `token` cho request hiện tại. Gọi `getToken()` giúp token trì hoãn được materialize khi cần; trong Spring Security 6 giá trị cung cấp cho client có thể là biểu diễn **XOR-masked**. Client phải gửi nguyên văn giá trị server phát về theo header tương ứng.
- Token endpoint không nhận/trả credential và có `Cache-Control: no-store`; không cache qua CDN hoặc gửi token sang origin không được phép.
- `GET /api/profile` yêu cầu authentication ở `SecurityFilterChain`; method chỉ đọc `Authentication` do Spring Security cung cấp.
- `POST /api/notes` cần **cả role EDITOR và CSRF hợp lệ**. Controller demo không lưu gì; status 201 chỉ dùng để thấy request đã qua security chain.
- Trong production, cần validation, quyền theo owner/tenant, giới hạn request size, error handling và persistence đúng. **Không** dùng thông tin role do client gửi trong JSON để quyết định quyền.
- Token CSRF **không thay thế authentication**. User anonymous có token vẫn không được gọi endpoint `/api/notes`.

## 8. Tài liệu HTML từ backend để quan sát CSP thực tế

Tạo file `src/main/resources/static/index.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Security Headers Lab</title>
</head>
<body>
  <h1>Trang backend có CSP</h1>
  <p id="loaded">Chưa chạy script.</p>
  <p>Hãy xem Response Headers và Console trong DevTools.</p>
  <script src="/app.js" defer></script>
</body>
</html>
~~~

Tạo file `src/main/resources/static/app.js`:

~~~javascript
"use strict";

document.getElementById("loaded").textContent =
  "External script cùng origin đã chạy.";
~~~

Đây là HTML **tải từ backend port 8080**, nên nhận `Content-Security-Policy` mà Spring Security ghi lên HTTP response. Script `/app.js` cùng origin được `script-src 'self'` cho phép chạy.

Không viết inline `<script> ... </script>` vào tài liệu này: CSP đã cấu hình **không cho inline script**, nên trình duyệt phải chặn. Để thử policy, ta sẽ **chèn thử** một script inline từ Playwright và xác nhận nó không thực thi. Đừng để header CSP bị reverse proxy bỏ trước khi tới browser production.

**Phân biệt:** việc API trả header CSP không có nghĩa nó kiểm soát script của một trang **được phục vụ từ port 5173**. Browser gắn CSP với **document nhận chính sách**. Vì thế bài thực hành cố ý có **hai trang**: backend HTML để kiểm tra CSP; frontend port 5173 để kiểm tra CORS.

## 9. Frontend cross-origin trên localhost:5173

File `cors-client/index.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>CORS + CSRF Lab</title>
</head>
<body>
  <h1>Frontend khác origin</h1>
  <button id="get-token" type="button">Lấy CSRF token</button>
  <button id="login" type="button">Đăng nhập editor</button>
  <button id="save" type="button">Lưu ghi chú</button>
  <button id="logout" type="button">Đăng xuất</button>
  <p id="status" role="status">Chưa thao tác</p>
  <script src="/client.js" defer></script>
</body>
</html>
~~~

File `cors-client/client.js`:

~~~javascript
"use strict";

const API = "http://localhost:8080";
const statusNode = document.getElementById("status");
let csrfState = null;

function show(text) {
  statusNode.textContent = text;
}

async function request(path, options = {}) {
  return fetch(API + path, {
    ...options,
    credentials: "include",
    cache: "no-store"
  });
}

async function fetchCsrf() {
  const response = await request("/csrf");
  if (!response.ok) {
    throw new Error("Không nhận được CSRF token");
  }

  const data = await response.json();
  if (!data.headerName || !data.token) {
    throw new Error("CSRF JSON không hợp lệ");
  }

  // Giữ token trong memory của tab; không ghi URL hoặc localStorage.
  csrfState = data;
  return data;
}

async function loginEditor() {
  const csrf = await fetchCsrf();

  const response = await request("/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body: new URLSearchParams({
      username: "editor",
      password: "editor-test-password"
    })
  });

  // Browser fetch mặc định theo redirect của formLogin.
  // Đừng suy ra login thành công chỉ từ một 200 HTML login page.
  const profile = await request("/api/profile", {
    headers: { "Accept": "application/json" }
  });

  const type = profile.headers.get("content-type") || "";
  if (!profile.ok || !type.includes("application/json")) {
    throw new Error("Login không tạo authenticated session");
  }

  const body = await profile.json();
  if (body.user !== "editor") {
    throw new Error("Authenticated principal không đúng");
  }

  // Login success xóa CSRF token trước đó theo lifecycle mặc định.
  // Refresh luôn sau khi session/authentication thay đổi.
  await fetchCsrf();
  show("Đã đăng nhập editor");
}

async function saveNote() {
  if (!csrfState) {
    await fetchCsrf();
  }

  const result = await request("/api/notes", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      [csrfState.headerName]: csrfState.token
    },
    body: JSON.stringify({ text: "Browser lab" })
  });

  if (result.status !== 201) {
    throw new Error("POST bị từ chối: HTTP " + result.status);
  }

  const body = await result.json();
  if (body.status !== "saved") {
    throw new Error("Response không đúng");
  }
  show("Đã lưu ghi chú: 201 Created");
}

async function logout() {
  if (!csrfState) {
    await fetchCsrf();
  }

  await request("/logout", {
    method: "POST",
    headers: { [csrfState.headerName]: csrfState.token }
  });

  csrfState = null;
  await fetchCsrf();
  show("Đã đăng xuất và lấy token mới");
}

function bind(id, action) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await action();
    } catch (error) {
      show("Lỗi: " + error.message);
    }
  });
}

bind("get-token", async () => {
  await fetchCsrf();
  show("Đã lấy CSRF token cho phiên hiện tại");
});
bind("login", loginEditor);
bind("save", saveNote);
bind("logout", logout);
~~~

### 9.1 Vì sao mỗi request dùng credentials: include?

Frontend ở `5173`, API ở `8080`. Chúng **khác origin** nên `fetch` mặc định `credentials: "same-origin"` sẽ không tự gửi session cookie tới backend. Với `credentials: "include"`, browser có thể gửi cookie phù hợp với domain/path/SameSite của backend trong các requests cross-origin, nếu cookie policy cho phép.

Ở phía backend, CORS response với `Access-Control-Allow-Origin: http://localhost:5173` và `Access-Control-Allow-Credentials: true` cho browser biết origin này có thể đọc response có credentials. **Cả hai phía cùng cần cấu hình đúng**. Nếu cookie bị SameSite/Secure/third-party policy chặn, bật CORS một mình không tự làm cookie được gửi.

### 9.2 Header CSRF gây preflight

POST trong demo gửi header tùy chỉnh `X-CSRF-TOKEN` và có thể gửi `Content-Type: application/json`. Những thành phần này khiến browser gửi **OPTIONS preflight** trước POST cross-origin. Server trả preflight cho origin/method/headers được phép; sau đó browser mới gửi POST thực nếu các điều kiện CORS đạt.

**Điều rất quan trọng:** preflight được phép **không** có nghĩa user đã login, có role EDITOR hay có CSRF token hợp lệ. Preflight kiểm tra *được phép gửi kiểu request cross-origin này không*; POST thực vẫn qua `CsrfFilter` và authorization.

### 9.3 Demo JavaScript không phải secret store

`editor-test-password` trong frontend là **chỉ dành cho local lab**. Trong production tuyệt đối không embed mật khẩu thật trong JavaScript; user phải nhập credential qua một login flow an toàn, hoặc dùng SSO/OIDC phù hợp. Khi ứng dụng triển khai, mọi dữ liệu người dùng đều cần bảo vệ tránh XSS và lưu trữ phù hợp. CSRF token giữ trong memory nhằm hạn chế tồn tại lâu, nhưng **XSS cùng origin vẫn có thể đọc token**: cần CSP, encoding và chống XSS.

## 10. Chạy ứng dụng ở hai terminal

Từ thư mục `security-browser-lab`, terminal 1 chạy backend:

~~~bash
mvn spring-boot:run
~~~

Khi khởi chạy thành công, kiểm tra từ trình duyệt:

~~~text
http://localhost:8080/
http://localhost:8080/api/public
http://localhost:8080/csrf
~~~

Terminal 2 khởi động static site frontend; với Python 3:

~~~bash
python3 -m http.server 5173 --directory cors-client
~~~

Trên Windows, nếu `python3` không tồn tại, thử:

~~~powershell
py -m http.server 5173 --directory cors-client
~~~

Mở:

~~~text
http://localhost:5173/
~~~

**Không dùng `file:///.../cors-client/index.html` để test CORS**. Trang `file:` có thể có opaque/null origin, không khớp `http://localhost:5173` được cấu hình. Phải dùng một HTTP server thực để origin trong browser đúng.

### 10.1 Thao tác bằng tay

1. Mở `http://localhost:5173/` trong Chromium; bật DevTools → Network.
2. Bấm **Lấy CSRF token**; xem request `GET http://localhost:8080/csrf` và response JSON. Tránh copy raw token/cookie vào ticket.
3. Bấm **Đăng nhập editor**; quan sát một OPTIONS preflight nếu browser gửi, POST `/login` và redirect/profile. Session cookie của `localhost` có thể thay sau login (session fixation protection).
4. Bấm **Lưu ghi chú**; POST `/api/notes` phải trả **201 Created** và body `{"status":"saved"}`.
5. Thử bỏ header CSRF qua JavaScript DevTools (phần 12): POST sẽ bị 403.
6. Thử gửi token cũ sau login: bị từ chối theo lifecycle của cấu hình.
7. Mở `http://localhost:8080/` và kiểm tra security response headers; thử chèn inline script bằng Playwright để quan sát CSP enforcement.
8. Đăng xuất ở frontend, rồi dùng token/session mới thử lại; request POST yêu cầu role EDITOR phải tiếp tục bị chặn khi anonymous.

Đừng coi “Network hiển thị OPTIONS 200” là kết luận test thành công. Hãy quan sát **POST thật** và status cuối.

## 11. HTTP CORS preflight: mong đợi chính xác

Một preflight mẫu do browser phát cho POST JSON có header CSRF:

~~~http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Phần response quan trọng về mặt ngữ nghĩa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin
~~~

**Đây là response minh họa**, không khẳng định thứ tự/chính tả hoặc toàn bộ headers luôn xuất hiện y hệt trong mọi Spring Boot/Servlet implementation. `Vary` có thể gồm thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Điều cần test là **giá trị cho phép origin, credentials, method và headers** tương ứng request.

Với origin không được cho phép, không được phát header `Access-Control-Allow-Origin` chấp nhận origin đó. `CorsFilter` của Spring có thể trả 403 cho CORS request không hợp lệ; browser có thể hiển thị một **CORS error** và JavaScript nhận rejected Promise/TypeError thay vì đọc được body/status bị chặn.

### 11.1 CORS không ngăn curl gửi request

Có thể gửi request từ command-line dù browser không cho JavaScript origin lạ đọc response. Ví dụ:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Command-line HTTP client **không áp dụng browser same-origin policy**. Vì thế CORS **không phải firewall**, không phải authorization mechanism và không bảo vệ API khỏi kẻ tấn công có thể gửi HTTP trực tiếp. Endpoints nhạy cảm vẫn cần authentication/authorization/CSRF phù hợp threat model.

### 11.2 Không dùng CORS để sửa mọi lỗi 401/403

Nếu browser Network thấy POST 403 với CORS headers cho phép origin, khả năng cao request đã qua CORS nhưng bị CSRF hoặc authorization từ chối. Đừng mở `allowedOrigins("*")` chỉ để làm lỗi 403 biến mất. Hãy nhìn:

- Browser có gửi session cookie không?
- Token CSRF ở đúng header chưa, token còn thuộc phiên hiện tại không?
- User có role EDITOR không?
- Request thực có bị 401/302 tới login rồi browser gặp redirect/CORS error không?
- Frontend có dùng đúng scheme/hostname/port, không trộn localhost và 127.0.0.1?

## 12. Thử CSRF lỗi và role lỗi từ browser DevTools

Sau khi đăng nhập editor và nhận token mới, ở Console của trang `http://localhost:5173`, chạy đoạn **không mang CSRF header**:

~~~javascript
const missingCsrf = await fetch(
  "http://localhost:8080/api/notes",
  {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: "missing token" })
  }
);
console.log(missingCsrf.status);
~~~

Khi cùng session đã đăng nhập, CORS origin hợp lệ và POST có JSON body, kỳ vọng status **403** vì token thiếu. Console có thể hiển thị thêm một OPTIONS preflight; request OPTIONS có thể thành công, nhưng POST sau đó vẫn 403.

Muốn thử **token không hợp lệ**:

~~~javascript
const invalidCsrf = await fetch(
  "http://localhost:8080/api/notes",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": "deliberately-invalid-token"
    },
    body: JSON.stringify({ text: "bad token" })
  }
);
console.log(invalidCsrf.status);
~~~

Kỳ vọng 403. Đoạn code **không vô hiệu hóa CSRF** và không hề lấy token bí mật của người khác. Thử nghiệm chỉ trên demo local do bạn kiểm soát.

### 12.1 Role USER có CSRF đúng vẫn bị từ chối

Có thể đăng nhập bằng user `reader` và `reader-test-password` trong phiên riêng (ví dụ browser context mới hoặc logout trước). Khi POST `/api/notes` mang token hợp lệ, `CsrfFilter` sẽ cho qua nhưng `hasRole("EDITOR")` vẫn trả 403.

Nếu chỉ xem status 403, chưa phân biệt được hai nguyên nhân. Để chứng minh **authorization**, luôn chuẩn bị **CSRF hợp lệ** trong test. Để chứng minh **CSRF**, dùng principal có quyền **EDITOR**. Các test độc lập ở phần sau được thiết kế đúng như vậy.

### 12.2 Token cũ sau login

Lấy token trước login từ `GET /csrf`, đăng nhập thành công, rồi thử gửi **token cũ** tới `POST /api/notes` dưới session mới. Trong Spring Security form login mặc định, CSRF token cũ thường bị xóa tại authentication success, do đó POST với token cũ bị 403. Lấy token mới sau login và thử lại sẽ thành công.

Đừng hiểu rằng cứ mỗi GET sẽ tạo token raw mới: Spring Security 6 có thể **XOR-mask** token khi xuất ra, khiến token string khác nhau mà expected token gốc vẫn là một. Lỗi sau login liên quan tới **thay đổi authentication/lifecycle**, không phải đơn giản vì hai tab hiển thị token khác string.

## 13. Kiểm thử backend bằng MockMvc: CSRF, CORS, headers, role

Test đầu tiên chạy Spring Security filter chain trong Spring Boot context mà **không cần trình duyệt**. Nó rất tốt để cô lập backend logic trước khi dùng Playwright.

File `src/test/java/com/example/securitylab/HttpSecurityIntegrationTest.java`:

~~~java
package com.example.securitylab;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanFetchCsrfAndItMustNotBeCached()
            throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty())
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "editor", roles = "EDITOR")
    void editorWithValidCsrfCreatesNote() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("saved"));
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerIsDeniedEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"x\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginPreflightReturnsCredentialHeaders()
            throws Exception {
        mvc.perform(options("/api/notes")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void deniedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header("Origin", "http://127.0.0.1:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "content-type,x-csrf-token"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void appDocumentHasCspAndDefaultSecurityHeaders()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                    "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                    "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                    "Content-Security-Policy",
                    org.hamcrest.Matchers.containsString(
                        "script-src 'self'")));
    }

    @Test
    void publicApiWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }
}
~~~

**Tại sao dùng `@WithMockUser` ở test này?** Ở đây muốn cô lập **CSRF vs authorization**, không cố chứng minh login password thực. Test reader có CSRF hợp lệ vẫn bị 403 vì thiếu role; test editor thiếu CSRF bị 403 dù role đúng. Đó là những phép thử độc lập và chính xác hơn một test “POST trả 403” không phân loại.

### 13.1 Giới hạn cần ghi trong báo cáo test

- `@WithMockUser` đặt Authentication giả trong TestContext. Nó **không xác minh password** hay cookie từ browser.
- `csrf()` của Spring Security Test tạo token hợp lệ trong request test. Nó **không kiểm thử** browser đã lấy token qua GET, lưu/refresh đúng sau login, hay gửi credentials include.
- MockMvc chạy Spring MVC + security filters trong context nhưng **không tái hiện browser thực thi CORS/CSP**.
- Test header CSP chỉ chứng minh **server phát đúng chuỗi policy**, chưa chứng minh browser sẽ chặn inline script. Phần Playwright phía sau bổ sung bằng chứng đó.
- Trên HTTP MockMvc, không assert HSTS luôn có mặt vì Spring Security chỉ gửi HSTS trên request HTTPS phù hợp. Đó là một kỳ vọng cần test riêng ở deployment HTTPS.
- Kết quả test còn phụ thuộc phiên bản Boot/Security và context đang thực thi. Không biến test profile `permitAll` hoặc `@AutoConfigureMockMvc(addFilters=false)` thành “cách sửa” cho bài thực hành bảo mật.

Chạy:

~~~bash
mvn test
~~~

Với code demo đúng, chín test trong `HttpSecurityIntegrationTest` có kỳ vọng như đã viết. Không có stdout Maven cố định; nếu test fail phải kiểm tra từng nguyên nhân, không sửa code để luôn trả 200.

## 14. Kiểm thử trình duyệt bằng Playwright

### 14.1 Cài đặt Playwright

Từ thư mục `browser-tests` (là một thư mục riêng, cạnh `pom.xml`):

~~~bash
npm init -y
npm install --save-dev @playwright/test
npx playwright install chromium
~~~

**Trước khi chạy Playwright**, giữ hai terminal server đang hoạt động:

~~~text
backend  http://localhost:8080
frontend http://localhost:5173
~~~

Nếu dùng Windows/CI, cài đặt Chromium dependencies theo hướng dẫn Playwright dành cho hệ điều hành tương ứng. Browser automation sẽ sử dụng **Chromium thật**, không phải HTTP client của Playwright APIRequestContext để kiểm tra enforcement CORS/CSP.

### 14.2 Test file security.spec.js

Tạo `browser-tests/tests/security.spec.js`:

~~~javascript
import { test, expect } from "@playwright/test";

const FRONTEND = "http://localhost:5173";
const BACKEND = "http://localhost:8080";

test("frontend được CORS cho phép và có CSRF hợp lệ",
    async ({ page }) => {

  await page.goto(FRONTEND);

  await page.getByRole("button", { name: "Lấy CSRF token" })
    .click();

  await expect(page.locator("#status"))
    .toHaveText("Đã lấy CSRF token cho phiên hiện tại");

  // Fetch chạy trong browser origin 5173 (không dùng Node HTTP).
  const body = await page.evaluate(async () => {
    const response = await fetch(
      "http://localhost:8080/api/public",
      { credentials: "include" }
    );
    return response.json();
  });

  expect(body.message).toBe("public");
});

test("sau login, token cũ bị từ chối nhưng token mới gửi được",
    async ({ page }) => {

  await page.goto(FRONTEND);

  const oldCsrf = await page.evaluate(async () => {
    const res = await fetch("http://localhost:8080/csrf", {
      credentials: "include",
      cache: "no-store"
    });
    return res.json();
  });

  await page.getByRole("button", { name: "Đăng nhập editor" })
    .click();
  await expect(page.locator("#status"))
    .toHaveText("Đã đăng nhập editor");

  // Form login làm thay đổi authentication và CSRF lifecycle.
  const oldStatus = await page.evaluate(async old => {
    const res = await fetch(
      "http://localhost:8080/api/notes",
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          [old.headerName]: old.token
        },
        body: JSON.stringify({ text: "stale token" })
      }
    );
    return res.status;
  }, oldCsrf);

  expect(oldStatus).toBe(403);

  // Frontend đã tự fetch token mới sau login.
  await page.getByRole("button", { name: "Lưu ghi chú" })
    .click();
  await expect(page.locator("#status"))
    .toHaveText("Đã lưu ghi chú: 201 Created");

  // Có quyền EDITOR nhưng thiếu CSRF vẫn bị từ chối.
  const missingStatus = await page.evaluate(async () => {
    const res = await fetch(
      "http://localhost:8080/api/notes",
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "without csrf" })
      }
    );
    return res.status;
  });

  expect(missingStatus).toBe(403);
});

test("origin khác allowlist bị browser chặn đọc CORS response",
    async ({ page }) => {

  // Python http.server mặc định có thể phục vụ localhost và 127.0.0.1.
  await page.goto("http://127.0.0.1:5173/");

  const blocked = await page.evaluate(async () => {
    try {
      await fetch("http://localhost:8080/api/public", {
        mode: "cors",
        credentials: "include"
      });
      return false;
    } catch {
      return true;
    }
  });

  expect(blocked).toBe(true);
});

test("CSP backend cho external script nhưng chặn inline script",
    async ({ page }) => {

  await page.goto(BACKEND + "/");

  await expect(page.locator("#loaded"))
    .toHaveText("External script cùng origin đã chạy.");

  const inlineExecuted = await page.evaluate(() => {
    window.__labInlineExecuted = false;

    const script = document.createElement("script");
    script.textContent = "window.__labInlineExecuted = true";
    document.body.appendChild(script);

    return window.__labInlineExecuted;
  });

  expect(inlineExecuted).toBe(false);

  const headers = await page.evaluate(async () => {
    // Header inspection ở server đã được kiểm tra thêm bằng MockMvc.
    return document.location.origin;
  });
  expect(headers).toBe(BACKEND);
});
~~~

Đây là test dùng **JavaScript chạy trong browser context** thông qua `page.evaluate`. Khi test CORS disallowed origin, browser phải không cho script đọc response; browser có thể ghi lỗi CORS vào Console. Không dựa vào việc JavaScript bắt được status code 403 từ disallowed response: policy browser thường khiến `fetch` reject với network-style error.

**Về stale token sau login:** test lấy token từ anonymous session **trước** khi login; sau login, default authentication strategy làm token cũ không còn hợp lệ. Nó kiểm tra chính tình huống UX thường gặp sau login. Nếu bạn thay CSRF repository/handler hoặc authentication filter trong dự án thật, hãy điều chỉnh kịch bản theo lifecycle thực tế và kiểm chứng nguyên nhân thay vì hard-code suy đoán.

### 14.3 Chạy browser tests

Trong `browser-tests`:

~~~bash
npx playwright test tests/security.spec.js
~~~

Để xem trình duyệt thật trong quá trình chạy:

~~~bash
npx playwright test tests/security.spec.js --headed
~~~

Để điều tra test fail:

~~~bash
npx playwright test tests/security.spec.js --debug
~~~

Playwright mặc định có thể chạy tests song song trong **browser contexts tách biệt**. Điều này tốt cho isolation vì mỗi test có cookies/CSRF state riêng; nhưng nếu dùng shared database/user state trong ứng dụng thật, phải thiết kế fixtures tránh cạnh tranh tài nguyên.

**Không bịa kết quả:** output test, thời gian chạy và số failed/passed chỉ có thể kết luận khi thực sự chạy project và Playwright trong môi trường có Java, Node, browser, ports và dependencies đầy đủ. File ở đây là **mẫu bài thực hành**, chưa phải log thực thi được ghi nhận.

## 15. Quan sát thêm trong DevTools để hiểu đúng nguyên nhân

Khi chạy browser tests hoặc thao tác tay, hãy mở Chromium DevTools → **Network**, lọc theo `Fetch/XHR` và xem:

### Với GET /csrf

- Request origin `http://localhost:5173`.
- Response `Access-Control-Allow-Origin: http://localhost:5173` và `Access-Control-Allow-Credentials: true` khi có Origin header.
- Response JSON chứa header name và token cho session hiện tại.
- Cache-Control không cho lưu trữ token trong cache.
- Cookie session nếu được set: kiểm tra Path, Domain, SameSite, Secure, nhưng **không copy giá trị raw** vào báo cáo.

### Với OPTIONS /api/notes

- `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` được browser tạo tự động.
- Response cho phép origin/method/headers phù hợp.
- OPTIONS không cần CSRF token giống POST nghiệp vụ; nó là phép thăm dò CORS, không phải thao tác thay đổi trạng thái.

### Với POST /api/notes

- Có credential/session cookie phù hợp.
- Header CSRF mang giá trị lấy từ **phiên hiện tại**, không phải token trước login.
- Response 201 khi có EDITOR + CSRF hợp lệ; 403 nếu thiếu token hoặc thiếu role.
- Không log raw token/cookie trong CI, ticket hoặc screenshots chia sẻ công khai.

### Với GET / (backend HTML)

- `Content-Security-Policy` chứa `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY`.
- `Referrer-Policy: no-referrer`.
- External script `/app.js` tải và chạy.
- Inline script được chèn bởi Playwright bị chặn; browser Console có thể báo CSP violation.
- HTTP localhost không có HSTS header như HTTPS hợp lệ. Đây không phải bằng chứng HSTS production bị tắt.

## 16. Security headers: những gì thử nghiệm này chứng minh và chưa chứng minh

### 16.1 CSP đúng không phải lời giải mọi XSS

Một CSP hạn chế `script-src` giúp chặn nhiều dạng script injection, nhưng không thay thế:

- Output encoding theo context HTML/attribute/URL/JavaScript.
- Không dùng `innerHTML` với dữ liệu không tin cậy.
- Sanitization hợp lệ cho rich HTML.
- Server-side validation và authorization.
- Subresource Integrity (SRI) nếu tải third-party scripts, và supply-chain review.
- Nonce/hash policy khi cần inline bootstrap script an toàn; không bật `unsafe-inline` bừa để “làm website chạy”.

CSP có thể triển khai trước bằng `Content-Security-Policy-Report-Only` để đo vi phạm khi di trú, nhưng **Report-Only không chặn** như enforcement header. Trong bài này dùng header enforcing để browser test có thể chứng minh script inline bị ngăn.

### 16.2 Header ở API response không bảo vệ tài liệu frontend khác origin

Giả sử backend trả CSP cho `GET /api/public`, còn frontend HTML đến từ Python static server 5173. CSP của JSON response **không quyết định** script nào được chạy trong document 5173. Nếu frontend thật ở CDN/reverse proxy, chính CDN/proxy/frontend server phải phát CSP phù hợp cho **tài liệu HTML** đó.

Do đó Playwright test CSP trên `http://localhost:8080/` chứ không dùng frontend 5173. Đây là điểm dễ sai khi triển khai backend và SPA riêng origin.

### 16.3 X-Frame-Options và frame-ancestors

Spring Security mặc định thường phát `X-Frame-Options: DENY`, chặn các trình duyệt tương thích nhúng trang trong frame. CSP `frame-ancestors 'none'` là cơ chế hiện đại tương đương ở phạm vi document, có độ linh hoạt cao hơn.

Khi cần iframe hợp lệ giữa các origin do doanh nghiệp quản lý, thiết kế allowlist rõ ràng và test browser trên chính domain triển khai. Đừng tắt toàn bộ frame protection để một trang nhúng tạm thời hoạt động.

### 16.4 X-Content-Type-Options, cache, referrer

- `X-Content-Type-Options: nosniff` có ích khi browser phân loại tài nguyên; phải trả Content-Type đúng cho JS/CSS/JSON.
- Cache headers Spring Security giúp tránh cache một số responses nhạy cảm, nhưng **không** thể thay thiết kế cache của CDN/API. Endpoint `/csrf` trong demo đặt `no-store` riêng.
- `Referrer-Policy: no-referrer` giảm việc gửi URL trong Referer; nếu business cần analytics, chọn policy phù hợp nhưng không đặt credentials/token vào URL.
- Các headers như `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy` và `Cross-Origin-Resource-Policy` có thể hữu ích cho mô hình browser isolation riêng, nhưng **không bật tùy tiện**: COEP/CORP có thể khiến resources cross-origin không tải được. Bài này không gộp chúng thành một preset không phân tích.

### 16.5 HSTS chỉ kiểm tra trên HTTPS đúng

`Strict-Transport-Security` do Spring Security phát khi request được đánh dấu là HTTPS theo cấu hình thích hợp. Trên localhost HTTP, đừng đánh giá “HSTS pass” bằng cách nhìn header không tồn tại.

Trong production, test:
1. Client truy cập hostname production qua **HTTPS** thực.
2. Response trả HSTS với `max-age` phù hợp, không nhầm HTTP vs HTTPS.
3. Reverse proxy/ingress chuyển đúng scheme, không tin `X-Forwarded-Proto` từ client tùy ý.
4. HTTPS certificates và redirect chính xác, không có mixed content.
5. Chỉ dùng `includeSubDomains`/preload sau khi kiểm tra tất cả subdomains và quy trình rollback.

**Không tự bật HSTS preload cho localhost hoặc domain demo**; preload tác động lâu dài tới domain thật.

## 17. Cookie, SameSite và CSRF trong mô hình hai cổng

Một request `fetch("http://localhost:8080/api/notes", {credentials:"include"})` từ trang `http://localhost:5173` là **cross-origin**, nhưng hai URL có cùng scheme và hostname, nên thuộc mô hình **same-site**. Cookie session với `SameSite=Lax` có thể được gửi ở các request same-site nếu Path/Domain và policy khác đều phù hợp.

Vì sao bài không dùng `https://evil.example` làm frontend demo? Mục tiêu là cô lập **CORS origin check** trước, tránh trộn thêm hành vi cross-site cookies. Nếu frontend thực được phục vụ từ một registrable domain khác:

- Browser có thể không gửi cookie khi `SameSite=Lax/Strict`.
- `SameSite=None; Secure` thường cần thiết cho cross-site cookie phù hợp, đồng thời dùng HTTPS.
- Browser privacy controls có thể chặn third-party cookies ngay cả khi server bật CORS đúng.
- CSRF protection vẫn cần khi browser có thể tự gửi cookie trong cross-site scenario.
- CORS allowCredentials không thay đổi SameSite/third-party-cookie policy.
- Quản lý refresh/logout/CSRF token và CSRF handler đúng với mô hình credential.

**Quy tắc:** CORS, Cookie SameSite và CSRF bảo vệ những ranh giới khác nhau. Đừng cho rằng cùng một cấu hình khắc phục được tất cả.

## 18. Khi nào 401, 302, 403, 201 là hành vi mong đợi?

| Tình huống | Trong cấu hình demo | Cách đọc |
| --- | --- | --- |
| GET public, anonymous | 200 | Không cần authentication. |
| GET profile, anonymous | Thường 302 tới login page vì formLogin. | Đây là authentication entry point, không phải CORS tự quyết định. |
| POST notes, editor, CSRF đúng | 201 | Authentication/authorization/CSRF đã qua, controller xử lý. |
| POST notes, editor, thiếu CSRF | 403 | CsrfFilter chặn request. |
| POST notes, editor, token CSRF sai | 403 | Token invalid, không phải role sai. |
| POST notes, reader, CSRF đúng | 403 | Thiếu `ROLE_EDITOR`. |
| OPTIONS từ origin 5173 hợp lệ | 200 hoặc preflight response thành công theo config. | CORS cho phép kiểu cross-origin request, không chứng minh user có quyền. |
| OPTIONS từ origin 127.0.0.1:5173 | Bị CorsFilter từ chối; browser không cho JS đọc response. | Origin không thuộc allowlist. |
| CSP chặn inline script | Không thực thi script, browser ghi vi phạm. | Chứng minh browser enforcement trên HTML từ backend. |

**Không thể dùng duy nhất một status để phân loại nguyên nhân.** Để chẩn đoán, xem request method, Origin, cookies, CSRF header, principal, authorities, chain và log filter trong môi trường dev/test phù hợp.

## 19. Lỗi thường gặp trong phòng lab

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| GET /csrf trả 200 nhưng POST 403 | Token không được gửi, token stale sau login, hoặc session cookie bị thiếu. | Sau login lấy token mới; kiểm tra headerName, credentials, cookie. |
| OPTIONS 200 nhưng POST 403 | CORS cho phép preflight, nhưng CSRF hoặc quyền không đạt. | Kiểm tra POST thật; tách kiểm thử CSRF khỏi role. |
| Trang frontend gặp TypeError: Failed to fetch | CORS bị browser chặn, server không chạy, HTTP/HTTPS mismatch, browser cookie/privacy policy hoặc network lỗi. | Kiểm tra DevTools Network/Console, Origin và Response Headers; không đoán chỉ từ TypeError. |
| Origin 127.0.0.1 không được phép | Allowlist chỉ có localhost. | Giữ hai hostname khác nhau để làm negative test; production allowlist theo nhu cầu thật. |
| CORS fail khi allowCredentials=true và "*" | Wildcard không phù hợp credentialed CORS, hoặc framework từ chối config. | Chỉ định allowedOrigins chính xác. |
| Cookie không gửi dù ACAO đúng | `fetch` thiếu credentials include; SameSite/Secure/Path/Domain hoặc third-party policy. | Kiểm tra cookie và site/origin trước khi mở rộng CORS. |
| POST login redirect nhưng frontend vẫn báo chưa login | Credential sai, login failure redirect tới HTML, session cookie không lưu hoặc CSRF sai. | GET /api/profile sau login và kiểm tra JSON principal; đừng chỉ tin status 200 của redirect. |
| User editor POST không CSRF vẫn 403 | CSRF hoạt động đúng. | Fetch token và gửi đúng header; không disable CsrfFilter. |
| User reader POST CSRF đúng vẫn 403 | Server yêu cầu ROLE_EDITOR. | Đây là authorization; không cấp role bừa, không biến endpoint thành permitAll. |
| CSP làm inline script từ HTML không chạy | Policy cố ý không có unsafe-inline. | Chuyển JS sang external script, hoặc cân nhắc nonce/hash nếu thực sự cần inline. |
| CSP test trên frontend 5173 không thấy block | HTML 5173 do Python server trả, **không nhận CSP của backend**. | Test document từ backend hoặc cấu hình CSP cho frontend server. |
| Playwright test lỗi nhưng MockMvc pass | Browser CORS/CSP/cookie behavior khác mock HTTP. | Phân biệt test server headers và browser enforcement; xem trace/Console. |
| HSTS không có trên localhost HTTP | HSTS chỉ có ý nghĩa trên HTTPS và thường chỉ được phát khi request secure. | Test HTTPS deployment; không giả lập HSTS kết luận trên HTTP. |
| Browser test bị timeout | Backend/frontend chưa chạy hoặc port bị chiếm. | Kiểm tra 8080/5173, test origin, logs. |
| CORS preflight không hiện lần thứ hai | Browser có thể cache preflight theo `Access-Control-Max-Age`. | Xóa cache/context mới, thay request hoặc kiểm tra ở Network phù hợp. |
| Code frontend hoạt động nhưng không ở production | Credentials hard-coded, session/cookie topology khác, CSP/proxy khác. | Thiết kế auth production, TLS, secrets, allowed origins và browser policy phù hợp. |

## 20. Checklist nghiệm thu bài thực hành

Đánh dấu từng mục **chỉ sau khi đã kiểm chứng** bằng test/Network:

- [ ] Backend khởi chạy trên `localhost:8080`, frontend trên `localhost:5173` bằng HTTP server.
- [ ] CORS allowlist không dùng wildcard credentialed; request từ 5173 được phép, từ 127.0.0.1:5173 bị chặn.
- [ ] OPTIONS preflight có các `Access-Control-Allow-*` headers phù hợp; POST thật vẫn qua authorization/CSRF.
- [ ] `GET /csrf` trả token của phiên hiện tại với `Cache-Control: no-store`.
- [ ] Login editor thành công qua form login filter và browser giữ session cookie phù hợp.
- [ ] Token trước login bị từ chối sau authentication change; token mới có thể POST.
- [ ] Editor POST thiếu CSRF / CSRF sai bị 403.
- [ ] User thiếu role EDITOR nhưng có CSRF hợp lệ vẫn bị 403.
- [ ] Editor có CSRF hợp lệ POST thành công và nhận 201/JSON phù hợp.
- [ ] GET backend HTML mang CSP đúng, external script cùng origin chạy, inline script bị chặn trong browser.
- [ ] Backend response có `X-Content-Type-Options`, `X-Frame-Options` và `Referrer-Policy` như cấu hình.
- [ ] Không báo HSTS fail chỉ vì HTTP local; có kế hoạch kiểm tra HTTPS deployment riêng.
- [ ] Không dùng `@WithMockUser` để tự khẳng định cookie/session/login lifecycle của trình duyệt.
- [ ] Không dùng CORS làm authorization; mọi endpoint nhạy cảm vẫn có server-side permission check.
- [ ] Không đăng nhập bằng user/password hard-coded hoặc log raw CSRF token/cookie ở production.
- [ ] Khi mở DevTools/CI traces, đã lọc/mask cookie, Authorization headers, CSRF token và PII.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Browser gửi OPTIONS `/api/notes` và nhận 200. Người chưa đăng nhập có gửi POST hợp lệ được không?

**Đáp:** Preflight được phép chỉ cho biết origin/method/headers hợp lệ về CORS. POST thật vẫn phải có authentication, role EDITOR và CSRF token hợp lệ. OPTIONS 200 **không** cấp quyền.

**Câu 2.** Một CORS error có nghĩa attacker không thể dùng curl gọi endpoint?

**Đáp:** Không. CORS là chính sách JavaScript/browser. Server-to-server và command-line clients không bị browser same-origin policy chi phối; backend phải tự authorization.

**Câu 3.** Vì sao frontend 5173 gọi API 8080 cần CORS dù hai địa chỉ đều localhost?

**Đáp:** Origin gồm **scheme + hostname + port**. Port khác nhau là khác origin. Hai địa chỉ có thể cùng-site nhưng vẫn cross-origin.

**Câu 4.** Sau login, token trước login bị 403 nhưng token mới thành công. Có nên tắt CSRF cho POST login?

**Đáp:** Không. Spring Security có thể xóa token khi authentication success; frontend cần lấy lại token cho session mới. Login CSRF là lớp bảo vệ quan trọng trong mô hình cookie/session.

**Câu 5.** CSP header của JSON API có tự bảo vệ trang React/HTML do CDN khác origin phát không?

**Đáp:** Không. Browser thực thi CSP của **document** nhận header CSP. CDN/front-end server phải phát policy cho document frontend nếu muốn áp dụng nó tại đó.

**Câu 6.** Tại sao Spring Security không gửi HSTS trên `http://localhost:8080`?

**Đáp:** HSTS phải được browser học qua HTTPS hợp lệ; HTTP demo không thể chứng minh HSTS deployment. Hãy kiểm tra chính HTTPS endpoint production.

**Câu 7.** Test `@WithMockUser` với `.with(csrf())` trả 201 đã chứng minh browser gửi cookies và token đúng chưa?

**Đáp:** Chưa. Đó là test server rule với Authentication/token do test tạo. Cần Playwright/browser flow để chứng minh CORS, cookies, login rotation và fetch request thực.

## 22. Tổng kết

Bài thực hành kết nối **ba lớp phòng thủ trình duyệt** với authorization phía server:

~~~text
Trang frontend 5173
  -> browser kiểm tra origin + preflight CORS
  -> fetch có credentials include (cookie phù hợp)
  -> request sang backend 8080
       -> CorsFilter: origin/method/headers có hợp lệ?
       -> CsrfFilter: token có đúng phiên hiện tại?
       -> Authentication/Authorization: user có ROLE_EDITOR?
       -> Controller: xử lý thao tác và trả response
  <- browser nhận response đã có CORS headers
  <- browser quyết định JS frontend có được đọc response

Trang HTML backend 8080
  <- backend gửi security headers (CSP, nosniff, frame, referrer...)
  -> browser thực thi CSP trên chính document đó
~~~

**CSRF bảo vệ khỏi thao tác bị giả mạo trong ngữ cảnh credential tự động gửi; CORS kiểm soát khả năng JavaScript cross-origin truy cập response; security headers giảm một số lớp tấn công tại browser.** Chúng chỉ hiệu quả khi phối hợp với authentication, authorization, đúng cookie/session policy và HTTPS production.

**Quy tắc kết thúc:** *Kiểm thử security phải gồm cả ca được phép và bị từ chối, cả backend assertion và browser enforcement. Không “sửa” bài thực hành bằng cách tắt CSRF, mở CORS cho mọi origin hoặc bỏ CSP để làm test xanh.*

## Tài liệu tham khảo

- Spring Security Reference — Servlet CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security Reference — Servlet CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security Reference — Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security Reference — Spring MVC MockMvc testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security Reference — MockMvc CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- MDN — SameSite cookie attribute: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
- Playwright Test — Getting Started: https://playwright.dev/docs/intro
