# Quan sát, tái hiện và phân biệt lỗi 401, 403, CSRF và CORS

> **Thực hành tổng hợp — Spring Security fundamentals.** Bài này dùng một REST API Spring Boot Servlet, hai tài khoản với quyền khác nhau và một trang gọi API từ origin khác để tái hiện **401 Unauthorized**, **403 Forbidden do phân quyền**, **403 Forbidden do CSRF**, cùng **lỗi CORS/preflight**. Mục tiêu quan trọng là xác định **filter, request và điều kiện thực sự gây lỗi**, thay vì suy đoán nguyên nhân chỉ bằng status code.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Gửi request có chủ đích để tạo **401** khi chưa xác thực hoặc credentials sai.
2. Tạo **403 do authorization** khi user đã xác thực nhưng thiếu role; chứng minh request đã vượt qua kiểm tra CSRF.
3. Tạo **403 do CSRF** khi user đủ quyền nhưng POST thiếu token; chứng minh user/role không phải nguyên nhân.
4. Tạo **CORS preflight hợp lệ/bị từ chối** bằng `OPTIONS`, `Origin` và `Access-Control-Request-*`; phân biệt lỗi HTTP trên server với lỗi **trình duyệt chặn cho JavaScript đọc response**.
5. Đọc DevTools Network, request/response headers, Spring Security logs và kết quả test để kết luận chính xác.

### Các tình huống sử dụng

API mẫu có `GET /api/tasks` để đọc và `POST /api/tasks` để tạo task. Tài khoản `reader` đọc được; tài khoản `editor` đọc và tạo được. Ta **giữ CSRF protection bật** vì API có thể được ứng dụng trình duyệt gọi và sử dụng `HttpSession` để giữ CSRF token. Ta bật CORS cho duy nhất `http://localhost:5500`, đồng thời có công tắc để tắt cấu hình CORS khi cần tái hiện lỗi.

| Mã/trạng thái quan sát | Yêu cầu tái hiện | Nguyên nhân mục tiêu |
| --- | --- | --- |
| **401** | `GET /api/tasks` không có `Authorization` hoặc sai password | Chưa xác thực |
| **403 — authorization** | `reader` POST với CSRF token **hợp lệ** | Đã xác thực, thiếu `ROLE_EDITOR` |
| **403 — CSRF** | `editor` POST không có CSRF token | Request đổi trạng thái bị CsrfFilter từ chối |
| **403 — CORS preflight** | `OPTIONS` với `Origin` không nằm trong allowlist | CorsFilter không cho origin sử dụng API |
| **Browser CORS error** | Trang ở origin khác gọi API khi CORS bị tắt | Browser không nhận được CORS permission phù hợp |
| **201** | `editor` POST với CSRF token và session khớp | Ca đối chứng thành công |

**Ghi nhớ:** status **403 không ghi rõ “do CSRF” hay “do role”**. Ngay cả CORS preflight cũng có thể bị trả 403. Cần đối chiếu phương thức, URL, token, credentials, origin và filter đã xử lý.

## 2. Mô hình request và thứ tự kiểm tra

Trong Spring Security Servlet, request đi qua chuỗi security filters trước khi đến controller. Với cấu hình CORS tích hợp đúng, luồng được hiểu đơn giản như sau:

```text
Browser / curl
     |
     v
[CORS processing] ---- Origin/preflight không hợp lệ ----> chặn CORS
     |
     v
[CSRF processing] ---- unsafe method thiếu/sai token --> 403
     |
     v
[Authentication] ----- thiếu/sai HTTP Basic -----------> 401 (tùy request/filter)
     |
     v
[Authorization] ------ thiếu role/authority ------------> 403
     |
     v
Controller ---------------------------------------------> 200 / 201
```

Sơ đồ thể hiện **quan hệ chẩn đoán**, không phải toàn bộ filters hay cam kết mọi request đều đi qua đúng bốn bước. Trên request POST thiếu CSRF token, Spring Security có thể từ chối **trước khi** kiểm tra HTTP Basic và quyền. Vì thế, một request POST không credentials cũng có thể thấy **403 do CSRF**, dù GET không credentials trả **401**.

### 401 Unauthorized là gì?

HTTP `401` nghĩa là request thiếu credentials được chấp nhận hoặc credentials không hợp lệ để truy cập tài nguyên được bảo vệ. Với HTTP Basic, phản hồi thường có header:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

`WWW-Authenticate` là tín hiệu thử thách xác thực. Đừng hiểu 401 theo tên “Unauthorized” của HTTP thành “đã đăng nhập nhưng không được phép”; trường hợp đó thường là 403.

### 403 Forbidden do authorization là gì?

Authentication đã xác định principal, nhưng `AuthorizationManager`/authorization rule không cho thao tác. Ví dụ `reader` có `ROLE_READER` nhưng endpoint POST đòi `ROLE_EDITOR`. Đây là **403 do thiếu quyền**, không phải vì sai mật khẩu.

### 403 Forbidden do CSRF là gì?

`CsrfFilter` kiểm tra CSRF token ở các request đổi trạng thái như POST, PUT, PATCH, DELETE khi bật CSRF. Token không tồn tại, hết hạn, không khớp session hoặc sai giá trị có thể dẫn tới `403`. Một token sai **không tự biến thành 401**. Cần xem đây có phải request trình duyệt dùng cookie/credentials được tự động gắn không để chọn chính sách CSRF phù hợp.

### CORS là gì và vì sao khác CSRF?

**CORS (Cross-Origin Resource Sharing)** là cơ chế browser dùng để quyết định JavaScript tại origin A có được đọc response từ origin B hay không. Origin gồm **scheme, host, port**; do đó `http://localhost:5500` và `http://localhost:8080` khác origin.

- Với request chứa header `Authorization`, browser thường gửi một **preflight `OPTIONS`** trước, kèm `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- Server phải trả các header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` phù hợp. Browser mới tiếp tục request thực tế theo quy tắc Fetch/CORS.
- Một request đơn giản có thể được gửi thật nhưng **JavaScript vẫn bị browser chặn đọc response** khi CORS không cho phép. Vì vậy API có thể trả 200 ở network/backend trong khi script thấy `TypeError: Failed to fetch` hoặc lỗi CORS trong console.
- `curl` không thực thi chính sách CORS của browser. Nó có thể gọi API thành công dù script ở origin khác bị chặn.
- **CORS không phải cơ chế chống CSRF, authentication hay authorization**. Cho phép CORS không mặc định cho phép user thiếu quyền; giữ CSRF vẫn cần khi browser tự mang credentials như cookie hoặc HTTP Basic đã cache.

## 3. Dựng ứng dụng thực hành Spring Boot

Môi trường: **Java 17+**, Spring Boot **3.x** với Spring Security **6.x**, Gradle và một Spring Boot Servlet project. Dùng Spring Initializr tạo dự án với `Spring Web`, `Spring Security`, `Spring Boot Starter Test`, sau đó thêm `spring-security-test`. Ví dụ dưới đây là các file cùng package, có thể biên dịch/chạy trong **project Spring Boot hoàn chỉnh**, không phải các class độc lập chạy trực tiếp với `javac`.

Cấu trúc:

```text
src/main/java/com/example/securitylab/
  SecurityLabApplication.java
  SecurityConfig.java
  TaskController.java
src/test/java/com/example/securitylab/
  SecurityLabTest.java
```

Với Gradle Groovy, dependency cần có:

```groovy
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

Trong một project Spring Boot có sẵn, giữ cấu hình plugin, Java toolchain và BOM/version của project; chỉ bổ sung dependency chưa có. Ứng dụng thực hành lưu dữ liệu trong RAM để không phụ thuộc database.

### `SecurityLabApplication.java`

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

Các file Java khác phải dùng cùng package `com.example.securitylab` để Spring Boot tìm thấy controller và cấu hình qua component scan.

## 4. Cấu hình authentication, authorization, CSRF và CORS

### `SecurityConfig.java`

```java
package com.example.securitylab;

import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${lab.cors.enabled:true}") boolean corsEnabled
    ) throws Exception {

        if (corsEnabled) {
            // Tích hợp CORS trước các bước authentication/authorization.
            http.cors(Customizer.withDefaults());
        } else {
            // Chỉ tắt để tái hiện lỗi CORS trong phòng lab.
            http.cors(AbstractHttpConfigurer::disable);
        }

        return http
            // Bật CSRF mặc định; token được lưu trong HttpSession khi cần.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/csrf", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/tasks")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(HttpMethod.POST, "/api/tasks")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5500"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/csrf", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Tài khoản demo chỉ dùng cho bài học trên localhost.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-pass"))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-pass"))
            .roles("READER", "EDITOR")
            .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }
}
```

**Những quyết định cần hiểu:**

1. **HTTP Basic** buộc request truy cập `/api/tasks` có credentials hợp lệ. Trong thực tế phải dùng **HTTPS**: Base64 không mã hóa bí mật username/password. Mật khẩu trong bài chỉ dùng để học, không đưa credentials thật vào URL, log, mã frontend hoặc Git.
2. `reader` có `ROLE_READER`; `editor` có cả `ROLE_READER` và `ROLE_EDITOR`. `hasRole("EDITOR")` sẽ kiểm tra authority `ROLE_EDITOR`. Authentication thành công không làm mọi endpoint tự động được cấp phép.
3. **CSRF được bật có chủ đích**. Với `HttpSessionCsrfTokenRepository` mặc định, token gắn với session và chỉ hợp lệ khi gửi lại đúng token cùng cookie session. Không bật `SessionCreationPolicy.STATELESS` ở phòng lab này vì cần mô phỏng luồng browser/session.
4. `GET /csrf` là endpoint lấy CSRF token cho lab. `GET` là safe method nên không bắt CSRF token; truy cập endpoint này không tự cấp quyền đọc hay sửa tasks.
5. CORS chỉ cho `http://localhost:5500`, không dùng `*`; `allowCredentials(true)` cho phép origin đã chỉ định sử dụng credentialed cross-origin requests theo trình duyệt. Cấu hình này **không thay thế** Basic auth, role hay CSRF token.
6. Biến `lab.cors.enabled` mặc định `true`. Khi đặt `false`, ta tắt integration CORS của Spring Security để quan sát sự khác biệt; đây chỉ là thí nghiệm, không phải phương pháp khắc phục lỗi.
7. `dispatcherTypeMatchers(ERROR).permitAll()` cho phép dispatch lỗi của Spring Boot đi đến handler; `anyRequest().denyAll()` vẫn chặn các endpoint ngoài phạm vi API mô tả.

**Giới hạn bảo mật:** Đừng đưa mật khẩu demo hoặc cấu hình client origin cố định sang production. Nếu ứng dụng có kiến trúc khác, cần xây dựng lại CORS/CSRF theo origin, loại credential, session và dữ liệu được bảo vệ.

## 5. Controller dùng chung để đối chứng cả bốn loại lỗi

### `TaskController.java`

```java
package com.example.securitylab;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TaskController {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Task> tasks = new ConcurrentHashMap<>();

    // Ép materialize token: GET trả token tương ứng session hiện tại.
    @GetMapping("/csrf")
    public CsrfView csrf(CsrfToken csrfToken) {
        return new CsrfView(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken()
        );
    }

    @GetMapping("/api/tasks")
    public List<Task> list() {
        return tasks.values().stream()
            .sorted(Comparator.comparingLong(Task::id))
            .toList();
    }

    @PostMapping("/api/tasks")
    public ResponseEntity<Task> create(@RequestBody NewTask body) {
        if (body.text() == null || body.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank"
            );
        }

        Task saved = new Task(nextId.incrementAndGet(), body.text().trim());
        tasks.put(saved.id(), saved);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    public record CsrfView(
        String headerName, String parameterName, String token
    ) {}
    public record NewTask(String text) {}
    public record Task(long id, String text) {}
}
```

Không có logic role/CSRF nào trong controller: **SecurityFilterChain xử lý chúng trước khi thực thi controller**. Nếu bị chặn 401/403, danh sách tasks không đổi. Endpoint `GET /csrf` đọc `CsrfToken` thực tế (khi bật CSRF mặc định) và trả thông tin token cho client thử nghiệm. Token có thể khác giữa các lần đọc, nhất là với cơ chế che token mặc định của Spring Security 6; phải dùng token mới trả về cùng session đúng.

**Quan trọng:** `HttpSession` ở đây hỗ trợ lưu CSRF token. HTTP Basic xác thực request qua credentials mà client gửi; có một session chứa CSRF token **không đồng nghĩa** người dùng được cấp quyền ghi. Khi POST vẫn phải gửi credentials đúng và có `ROLE_EDITOR`.

## 6. Chạy lab và ghi nhận response

Chạy project trong terminal, với CORS mặc định bật:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ví dụ dùng `http://localhost:8080` chỉ cho localhost. Khi dùng `curl` trong PowerShell, nên gọi `curl.exe` (để tránh alias của Windows PowerShell). Các lệnh có ký tự `\` nối dòng trong khối Bash dành cho Bash; trong PowerShell, viết **một dòng** hoặc dùng cú pháp nối dòng PowerShell. Mọi ví dụ dưới đây giả định server chạy ở 8080, không bị ứng dụng khác chiếm cổng.

### Ca A — 401 do thiếu authentication

```bash
curl -i http://localhost:8080/api/tasks
```

Kỳ vọng status **401 Unauthorized** và header challenge `WWW-Authenticate: Basic ...`. Request không có `Authorization`, nên Spring Security không thể xác thực principal để vào endpoint GET yêu cầu role.

Thử password sai:

```bash
curl -i -u reader:wrong-password http://localhost:8080/api/tasks
```

Kỳ vọng **401**, khác với trường hợp đã đăng nhập đúng nhưng không đủ quyền.

Đối chứng credentials đúng:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/tasks
```

Kỳ vọng **200 OK**. Với server mới chạy và chưa tạo task, body:

```json
[]
```

### Ca B — 403 do CSRF, dù user đủ quyền

`editor` có quyền POST, nhưng thử gửi request **không có CSRF token**:

```bash
curl -i -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"Created without CSRF token"}' \
  http://localhost:8080/api/tasks
```

Kỳ vọng **403 Forbidden**. Đây là trường hợp CSRF filter từ chối request unsafe trước khi controller chạy. Không kết luận thiếu role chỉ vì thấy 403; user `editor` được cấu hình `ROLE_EDITOR`.

Nếu thử POST **không có credentials và cũng không có CSRF token**, thứ tự filters có thể làm 403 CSRF xuất hiện trước 401 authentication. Muốn tái hiện 401 sạch, dùng GET không credentials như Ca A.

### Ca C — Lấy CSRF token đúng session

Dùng cookie jar để giữ `JSESSIONID` từ phiên trả token:

```bash
curl -i -c cookies.txt http://localhost:8080/csrf
```

Ví dụ body có cấu trúc (token thực tế là chuỗi ngẫu nhiên dài):

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<token-thuc-te-tu-server>"
}
```

Sao chép **giá trị `token` thật** từ response; không dùng nguyên chuỗi ví dụ. `-c cookies.txt` lưu cookie server trả về. Với các request POST tiếp theo, dùng **`-b cookies.txt` để gửi lại đúng cookie**, đồng thời gửi header `X-CSRF-TOKEN` tương ứng.

**Không được nhầm:**
- Chỉ có CSRF token nhưng thiếu cookie session gắn với token → thường **403**.
- Chỉ có cookie session nhưng thiếu token → **403**.
- Header token sai hoặc token thuộc session khác → **403**.
- Token đúng **không thay thế** HTTP Basic credentials hay quyền truy cập.

### Ca D — 403 do thiếu role (đã vượt qua CSRF)

`reader` có credentials đúng nhưng **không có role EDITOR**. Gửi cả CSRF token và session hợp lệ:

```bash
curl -i -b cookies.txt -u reader:reader-demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <token-thuc-te-tu-server>' \
  -d '{"text":"Reader cannot create"}' \
  http://localhost:8080/api/tasks
```

Kỳ vọng **403 Forbidden**. Lần này CSRF token đã hợp lệ nên lý do từ chối là `hasRole("EDITOR")`, khác hoàn toàn Ca B. Nếu cả hai đều có status 403, hãy so request headers, username/role và CSRF token/session để phân biệt.

### Ca E — Đối chứng editor tạo thành công

Dùng **cùng cookie jar và token hợp lệ** như trên, nhưng credentials `editor`:

```bash
curl -i -b cookies.txt -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <token-thuc-te-tu-server>' \
  -d '{"text":"Authorized task"}' \
  http://localhost:8080/api/tasks
```

Kỳ vọng **201 Created**. Nếu là task đầu tiên sau khi khởi động:

```json
{"id":1,"text":"Authorized task"}
```

Gọi lại `GET` bằng reader để quan sát bản ghi mới:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/tasks
```

Kỳ vọng **200 OK**, danh sách có task vừa tạo. ID có thể khác nếu đã thử tạo thành công trước đó. Đây là đối chứng xác nhận controller hoạt động, tránh hiểu nhầm mọi lỗi 403 do API hỏng.

### So sánh nhanh

| Ca | Credentials | CSRF token/session | Quyền theo endpoint | HTTP kỳ vọng |
| --- | --- | --- | --- | --- |
| A: GET không auth | Thiếu | GET không cần | Chưa xét | 401 |
| A: GET sai password | Sai | GET không cần | Chưa xét | 401 |
| A: GET reader | Đúng | GET không cần | Đủ | 200 |
| B: POST editor | Đúng | **Thiếu** | Đủ | 403 do CSRF |
| D: POST reader | Đúng | **Đúng** | **Thiếu** | 403 do authorization |
| E: POST editor | Đúng | **Đúng** | Đủ | 201 |

## 7. Tái hiện CORS preflight riêng biệt

Khi web page tại `http://localhost:5500` gọi API tại `http://localhost:8080` và tự gửi header `Authorization`, browser phát sinh preflight vì `Authorization` không nằm trong danh sách request headers được safelist. Preflight thường có hình thức:

```http
OPTIONS /api/tasks HTTP/1.1
Origin: http://localhost:5500
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

### Ca F — Preflight origin được cho phép

Quan sát raw response bằng `curl` (ở đây tự mô phỏng preflight để xem header, không thay browser):

```bash
curl -i -X OPTIONS http://localhost:8080/api/tasks \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Với CORS đang bật, preflight hợp lệ thường trả **200 OK**, có `Access-Control-Allow-Origin: http://localhost:5500` và thông tin phương thức/header được cho phép. Không cần Basic credentials trong preflight. Một preflight thành công **không có nghĩa** GET/POST thật đã vượt authentication, authorization hoặc CSRF.

### Ca G — Preflight origin bị từ chối

Đổi origin thành địa chỉ **không nằm trong allowlist**:

```bash
curl -i -X OPTIONS http://localhost:8080/api/tasks \
  -H 'Origin: http://localhost:5501' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
```

Với `CorsFilter` của cấu hình lab, phản hồi thường là **403** với dấu hiệu như `Invalid CORS request`. Đây là 403 **do CORS**, không cần user đăng nhập và không có ý nghĩa rằng tài khoản thiếu role. Để xác nhận, đổi lại origin `5500` với các headers/methods cho phép: preflight sẽ qua.

### Ca H — Tắt CORS rồi quan sát browser bị chặn

Dừng server và khởi động lại với property **chỉ dùng trong bài lab**:

```bash
./gradlew bootRun --args='--lab.cors.enabled=false'
```

Chạy lại preflight Ca F. Không còn CorsFilter tích hợp chấp thuận origin; `OPTIONS` có thể gặp security và trả 401/403, hoặc server không cung cấp headers CORS cần thiết. **Không dựa vào một status cố định** ở chế độ này. Dấu hiệu quyết định là response không chứng minh origin/header/method được cho phép, nên browser không thể tiếp tục/đọc kết quả theo chính sách CORS.

Để so sánh, request **cùng endpoint nhưng dùng `curl`** vẫn có thể trả 200 với Basic credentials:

```bash
curl -i -u reader:reader-demo-pass \
  -H 'Origin: http://localhost:5500' \
  http://localhost:8080/api/tasks
```

`curl` không cưỡng chế CORS. Vì vậy việc “curl được 200 nhưng browser lỗi CORS” là hoàn toàn có thể và không chứng minh authorization đã sai. Khởi động lại không có property hoặc với `--lab.cors.enabled=true` để bật lại CORS cho các bài test tiếp theo.

## 8. Xem lỗi CORS bằng trình duyệt và DevTools

Để quan sát trực tiếp, phục vụ một trang HTML từ **origin khác** như `http://localhost:5500`. Có thể dùng VS Code Live Server hoặc, nếu có Python 3, chạy trong một thư mục chứa file HTML:

```bash
python -m http.server 5500
```

Tạo file `cors-lab.html` bên trong thư mục phục vụ, với nội dung demo (chỉ dùng tài khoản học tập trên localhost):

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>CORS Lab</title></head>
<body>
  <button id="load">Gọi GET /api/tasks</button>
  <pre id="result"></pre>
  <script>
    document.getElementById("load").addEventListener("click", async () => {
      const output = document.getElementById("result");
      try {
        const response = await fetch("http://localhost:8080/api/tasks", {
          method: "GET",
          // Demo only: không nhúng credentials thật vào frontend.
          headers: {
            Authorization: "Basic " + btoa("reader:reader-demo-pass")
          },
          credentials: "include"
        });
        output.textContent =
          "HTTP " + response.status + "\n" + await response.text();
      } catch (error) {
        output.textContent = error.name + ": " + error.message;
      }
    });
  </script>
</body>
</html>
```

Mở `http://localhost:5500/cors-lab.html`, sau đó nhấn nút:

1. **Khi CORS bật:** tab **Network** thường hiển thị preflight `OPTIONS` (nếu không dùng kết quả preflight cache) rồi `GET` trả `200`; trang có thể đọc JSON. Response preflight/actual có các header CORS phù hợp.
2. **Khi CORS tắt:** tab **Console** báo lỗi chính sách CORS; script có thể thấy lỗi `TypeError` hoặc `Failed to fetch`. Tab **Network** cho thấy preflight hoặc response thiếu headers cần thiết. Response không nhất thiết mang một status “CORS error” đặc biệt.
3. **Khi origin không được phép:** nếu chuyển trang sang `http://localhost:5501`, preflight bị từ chối ngay vì chỉ origin `5500` được phép. Đừng sửa allowlist bằng `*` chỉ để lỗi biến mất.
4. **Nếu gọi POST bằng browser:** CORS được cho phép chỉ mở đường cho request; vẫn cần user đủ role và CSRF token đúng session. Đừng tắt CSRF để xử lý lỗi CORS.

> **Cảnh báo về demo:** JavaScript chứa credentials chỉ để tái hiện trên localhost; trong ứng dụng thật không đưa Basic username/password hoặc secret vào mã nguồn frontend. Browser có thể quản lý credential/cookie theo chính sách riêng; chọn authentication architecture phù hợp trước khi triển khai.

### Phân biệt trên DevTools

Tại **Network**, chọn request và đọc theo thứ tự:

- **Request URL, Method, Origin:** request thật `GET`/`POST` hay preflight `OPTIONS`? Có đúng host, port và protocol không?
- **Status và response headers:** `401` kèm `WWW-Authenticate` gợi ý authentication; `403` cần thêm bằng chứng; preflight cần `Access-Control-Allow-*` tương ứng.
- **Request headers:** `Authorization` có được gửi không? `X-CSRF-TOKEN` có đúng không? Cookie session có được gửi không? Preflight có `Access-Control-Request-Headers` nào?
- **Console:** thông báo browser chặn CORS mô tả quyền truy cập từ origin; JavaScript có thể không đọc được body/status thực tế.
- **Server logs/tests:** dùng để xác nhận filter nào từ chối. Một console message đơn lẻ không đủ phân biệt CSRF và authorization.

## 9. Kiểm thử tự động với MockMvc

`spring-security-test` cung cấp `httpBasic(...)` và `csrf()` để kiểm thử filter chain mà không cần tự sao chép token. `csrf()` tạo **CSRF token hợp lệ cho request test**; chỉ dùng trong test, không thay việc lấy token thật của client production.

### `SecurityLabTest.java`

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest(properties = "lab.cors.enabled=true")
@AutoConfigureMockMvc
class SecurityLabTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithoutCredentialsIs401() throws Exception {
        mvc.perform(get("/api/tasks"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void getWithWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/tasks")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanGetTasks() throws Exception {
        mvc.perform(get("/api/tasks")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void editorPostWithoutCsrfIs403() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("editor", "editor-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"No token\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerPostWithCsrfStill403() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("reader", "reader-demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Missing role\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorPostWithCsrfIs201() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("editor", "editor-demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Allowed\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.text").value("Allowed"));
    }

    @Test
    void allowedOriginPreflightPasses() throws Exception {
        mvc.perform(options("/api/tasks")
                .header(HttpHeaders.ORIGIN, "http://localhost:5500")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5500"));
    }

    @Test
    void otherOriginPreflightIsForbidden() throws Exception {
        mvc.perform(options("/api/tasks")
                .header(HttpHeaders.ORIGIN, "http://localhost:5501")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test
```

PowerShell: `.\gradlew.bat test`. Bộ test kiểm tra **8 tình huống**. Kết quả pass khi môi trường Spring Boot/Java/dependencies khớp và ứng dụng dùng đúng các lớp trên; Gradle thường in `BUILD SUCCESSFUL` khi chạy thành công. Không có stdout ứng dụng cố định phải khớp ngoài các status và JSON assertions đã ghi.

**Điểm mạnh của test tách biệt:** Hai test `editorPostWithoutCsrfIs403` và `readerPostWithCsrfStill403` đều đợi **403**, nhưng nguyên nhân khác nhau đã được cô lập bằng thông tin đầu vào. Test preflight 403 cố ý không gửi credentials cũng giúp chứng minh một 403 có thể xuất hiện **trước cả authentication**.

## 10. Bật log để xác định filter và root cause

Để quan sát filter chain trong môi trường học, có thể thêm vào `src/main/resources/application.yml`:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Khi cần chi tiết hơn và **chỉ trên local**, tạm dùng `TRACE` cho namespace thích hợp. Logger, phiên bản Spring Security và cấu hình filter chain ảnh hưởng nội dung thông báo; **không dựa vào một log line cụ thể** như một API contract.

Quy trình xác minh khi gặp 403:

1. Ghi lại **method, path, Origin, user/role, CSRF token và cookie session** của ca lỗi (không ghi giá trị secret/token thật vào log chia sẻ).
2. Thử GET không credentials để tạo 401 chuẩn và xác nhận HTTP Basic entry point.
3. Thử POST của editor **không token** để tạo 403 CSRF; đối chứng bằng token hợp lệ + cùng session để được 201.
4. Thử POST reader **có token hợp lệ** để tạo 403 authorization; đổi sang editor giữ token/session để được 201.
5. Với request browser từ origin khác, xem `OPTIONS` có xảy ra trước request thật không. Kiểm tra CORS headers ở response; thử `curl` cùng request và so sánh.
6. Nếu lỗi ở trước controller, đừng debug business logic trước khi biết filter nào từ chối.

**Tránh log dữ liệu nhạy cảm:** không bật TRACE trên production chỉ để tìm lỗi đơn giản; nếu phải điều tra, giới hạn thời gian/môi trường và che `Authorization`, `Cookie`, CSRF token và PII.

## 11. Bảng chẩn đoán: cùng status nhưng cách sửa khác nhau

| Dấu hiệu | Kiểm chứng độc lập | Hướng xử lý |
| --- | --- | --- |
| GET trả **401**, có `WWW-Authenticate` | Thử credentials đúng và sai | Kiểm tra Basic header, password encoder, user store, authentication config |
| POST trả **403**, token/cookie CSRF thiếu | Editor có role vẫn 403; thêm token đúng session thì 201 | Cấp/đính kèm token ở unsafe method; giữ CSRF khi có browser dùng ambient credentials |
| POST trả **403**, CSRF đã hợp lệ | Reader bị 403, editor được 201 | Sửa role/authority/matcher/policy nếu yêu cầu nghiệp vụ đòi thay đổi |
| OPTIONS preflight trả **403** | Đổi giữa Origin 5500 và 5501 | Cấu hình allowlist cho origin, method, headers cần thiết; đặt CORS trước auth |
| Browser báo **CORS**, `curl` cùng API trả 200 | Xem tab Network, preflight, `Access-Control-Allow-Origin` | Sửa CORS policy trên server; đừng tắt authentication hoặc CSRF |
| Browser không đọc được 401/403 thật | Response không có headers CORS hoặc preflight fail | Sửa CORS trước để browser có thể thấy response, sau đó xử lý 401/403 thực tế |
| POST bất ngờ trả 403 dù không gửi Basic | CSRF filter có thể chặn trước Basic auth | Tách GET unauthenticated để đo 401; bổ sung token để quan sát lớp xác thực |
| POST token đúng vẫn 403 | Token có cùng session không? User có role không? | Tách thứ tự: verify session/token, sau đó verify principal/authority |

### Quy tắc thực hành quan trọng

- **401:** trước hết hỏi “authentication đã thành công chưa?”.
- **403:** hỏi “CSRF token đã hợp lệ chưa?”, rồi mới hỏi “principal có đủ quyền không?”; đồng thời xem request có phải preflight từ origin bị từ chối không.
- **CORS:** hỏi “đây là lỗi bị browser chặn theo origin hay HTTP response mà JavaScript đọc được?”.
- **CSRF:** hỏi “browser có tự động gắn credentials vào request không?”; đừng chỉ hỏi “API có stateless hay không?”.
- **Preflight:** một request `OPTIONS` có thể bị browser gửi **không kèm credentials**; phải cấu hình CORS đúng để không biến nó thành lỗi authentication ngoài ý muốn.
- **Không xử lý lỗi bằng cách tắt bảo mật:** `permitAll()` không sửa CSRF, `csrf.disable()` không sửa CORS, `allowedOrigins("*")` không sửa authentication hay authorization.

## 12. Bài tập mở rộng có tiêu chí rõ ràng

### Bài A — Điều tra “cả hai đều 403”

Thực hiện lần lượt (1) editor POST thiếu token, (2) reader POST có token đúng, (3) editor POST có token đúng. Thu thập request headers và status; viết một câu giải thích cho **mỗi lần 403** mà không dùng câu mơ hồ “Spring Security chặn”.

**Đạt** nếu có bằng chứng case (3) trả 201 và phân biệt được CsrfFilter với authorization decision.

### Bài B — Điều tra “curl được, browser không”

Chạy lab với CORS bật và tắt. Từ origin `5500`, quan sát preflight/actual request trong Network; chạy `curl` trực tiếp đến API cùng credentials; so sánh.

**Đạt** nếu giải thích được tại sao `curl` không có chính sách CORS của browser, nhận ra request `OPTIONS`, và chỉ ra header `Access-Control-Allow-Origin` bị thiếu hoặc không khớp.

### Bài C — Phân biệt origin và cookie/session

Đổi riêng port nguồn trang HTML từ `5500` sang `5501`; đừng đổi API. Quan sát preflight bị chặn và khôi phục bằng cách trở về `5500`. Sau đó lấy CSRF token ở một session, thử POST bằng **session khác** để quan sát 403 CSRF.

**Đạt** nếu không nhầm sự khác nhau giữa **origin trong CORS** và **phiên lưu CSRF token**. Origin được cho phép không làm token của session A hợp lệ trong session B.

### Bài D — Viết báo cáo lỗi có thể tái hiện

Với mỗi loại lỗi, ghi lại: URL, method, Origin (nếu có), credentials được gửi hay không, role, CSRF token/cookie có hợp lệ không, expected status, actual status, bằng chứng từ Network/log và giải pháp. Che password/token thật. Một báo cáo tốt cho phép người khác tái hiện chính xác mà không cần đoán.

## 13. Các lỗi tư duy phổ biến

- **“403 = sai role.”** Sai: 403 còn có thể do CSRF hoặc CORS preflight và một số cơ chế từ chối khác.
- **“CORS báo lỗi tức server không nhận request.”** Không luôn đúng: preflight có thể ngăn request thật, nhưng với request không preflight, server có thể đã xử lý và browser chỉ chặn JS đọc response.
- **“Tắt CSRF thì hết lỗi CORS.”** Sai: hai chính sách giải quyết hai vấn đề khác nhau.
- **“Bật CORS thì browser gọi API được dù chưa đăng nhập.”** Sai: CORS không cấp credentials hay quyền.
- **“HTTP Basic là stateless nên không thể có CSRF.”** Sai: browser có thể tự gửi Basic credentials đã cache; cần đánh giá request có ambient credentials hay không.
- **“401 và 403 có thể đổi tùy ý.”** Không nên: mỗi status có semantics khác nhau và ảnh hưởng hành vi client; quan sát filter chain để trả đúng lỗi.
- **“Test bằng curl đã xác nhận CORS hoạt động.”** Không đủ: curl không cưỡng chế CORS; cần kiểm tra preflight/response headers và hành vi browser.
- **“Copy CSRF token là đủ.”** Sai: token thường gắn với đúng session; giữ cookie, tránh token cũ hoặc token lấy từ session khác.

## 14. Tài liệu nền tảng

Chọn tài liệu phù hợp **phiên bản Spring Security** đang dùng:

- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): vai trò các filters, thứ tự xử lý security và exception translation.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): BasicAuthenticationFilter và authentication entry point.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): authorization matchers, roles, authorities và denyAll.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CsrfFilter, CSRF token và các lưu ý với browser.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước Spring Security và tích hợp CORS.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): SOP, Origin, preflight và Access-Control-Allow-*.

**Tiêu chí hoàn thành toàn bài:** Có ứng dụng chạy tại localhost, test tái hiện được 401, 403 authorization, 403 CSRF, CORS preflight hợp lệ/bị chặn, nhìn được CORS error trong browser khi tắt CORS và giải thích được vì sao **cùng một status 403 có thể đến từ các lớp xử lý khác nhau**.
