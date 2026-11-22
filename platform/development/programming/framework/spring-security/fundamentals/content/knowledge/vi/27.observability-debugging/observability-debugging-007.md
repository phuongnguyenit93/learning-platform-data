# Phân biệt lỗi CORS của trình duyệt với lỗi xác thực phía máy chủ

## 1. Tại sao một lỗi hiển thị “CORS” có thể xuất phát từ xác thực?

Giả sử frontend chạy ở `http://localhost:5173`, backend Spring Boot ở `http://localhost:8080`. Người dùng nhấn nút tải thông tin cá nhân và trình duyệt hiển thị:

```text
Access to fetch at 'http://localhost:8080/api/me'
from origin 'http://localhost:5173' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present ...
```

Đội phát triển rất dễ kết luận “thêm `@CrossOrigin("*")` hoặc tắt Spring Security là xong”. Kết luận đó có thể sai và nguy hiểm. Server có thể đã trả **401 Unauthorized** vì chưa đăng nhập hoặc **403 Forbidden** vì không có quyền, nhưng phản hồi lỗi thiếu header CORS nên **JavaScript không được đọc nội dung/status của phản hồi**. Một lỗi xác thực lúc này bị **che bởi biểu hiện CORS** trong trình duyệt.

Ngược lại, request có thể bị **CORS chặn ngay tại preflight** dù người dùng đã có token hợp lệ. Hoặc lỗi hoàn toàn không phải CORS hay xác thực: chứng chỉ TLS sai, DNS không phân giải, backend ngừng chạy, request bị extension chặn hoặc trang HTTPS gọi API HTTP.

Ba câu hỏi phải trả lời **độc lập**:

1. **Trình duyệt có được phép đọc phản hồi cross-origin không?** Đây là kiểm tra CORS/Same-Origin Policy.
2. **Máy chủ có chấp nhận danh tính của request không?** Đây là xác thực: authentication, thường liên quan 401.
3. **Danh tính đó có được phép thực hiện hành động không?** Đây là phân quyền: authorization, thường liên quan 403.

Một request có thể đồng thời thất bại ở nhiều lớp. Vì thế, mục tiêu của bài này là **quan sát và gỡ lỗi** chính xác bằng DevTools, HTTP trace/log, `curl`, Spring Security và kiểm thử MockMvc; không “sửa” bằng cách mở toàn bộ origin hoặc vô hiệu hóa bảo mật.

Phạm vi: **Spring Security Servlet, Spring MVC, Java 17+ và Spring Boot 3.x/Spring Security 6.x**. Cơ chế reactive WebFlux dùng `CorsWebFilter`/`SecurityWebFilterChain` và các API khác; không chép nguyên ví dụ Servlet sang WebFlux.

## 2. CORS thực chất kiểm soát điều gì?

**Same-Origin Policy (SOP)** giới hạn việc mã JavaScript từ một origin đọc dữ liệu của origin khác. Một origin được xác định bởi bộ ba **scheme + host + port**:

| URL | So với `http://localhost:5173` | Vì sao |
| --- | --- | --- |
| `http://localhost:5173/app` | Cùng origin | Scheme, host, port đều giống. |
| `http://localhost:8080/api` | Khác origin | Port 8080 khác 5173. |
| `https://localhost:5173/app` | Khác origin | Scheme HTTPS khác HTTP. |
| `http://127.0.0.1:5173/app` | Khác origin | Host `127.0.0.1` khác `localhost`. |
| `https://api.example.com` | Khác origin với `https://app.example.com` | Subdomain khác; hai origin không giống nhau. |

**Cross-Origin Resource Sharing (CORS)** là cơ chế để **máy chủ nói với trình duyệt** rằng một số origin được phép đọc phản hồi của nó. Ví dụ:

```http
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
```

Điều này **không xác thực người dùng**; nó chỉ cho browser thấy origin nào được chia sẻ phản hồi. Một người chưa đăng nhập vẫn có thể bị 401, dù `Access-Control-Allow-Origin` hoàn toàn đúng. Một người đã đăng nhập nhưng thiếu quyền vẫn có thể bị 403. Và một script ở origin không được phép không được đọc phản hồi theo quy tắc CORS, kể cả endpoint đó công khai.

Những điểm nền tảng:

- **CORS chủ yếu được trình duyệt thực thi.** `curl`, Postman hoặc backend-to-backend HTTP client không tự áp dụng Same-Origin Policy. Họ có thể nhận 200, 401 hoặc 403 dù browser báo CORS.
- **CORS không thay thế xác thực, phân quyền, CSRF hay firewall.** Một endpoint không an toàn không trở nên an toàn chỉ nhờ không có header CORS. Máy khách không phải trình duyệt vẫn có thể gọi API.
- **Có CORS header không đồng nghĩa request được quyền.** Nó chỉ cho phép JavaScript nhìn thấy status/body nếu toàn bộ quy tắc CORS của request được đáp ứng.
- **Không có `Origin` chưa chắc là request giả mạo**, vì nhiều request không phải fetch cross-origin không gửi header này. Không dùng `Origin` một mình làm cơ chế đăng nhập/authorization.
- **Origin và site không giống nhau.** CORS so scheme/host/port, còn `SameSite` cookie dựa vào khái niệm site. Hai origin khác port có thể vẫn thuộc cùng một site; cookie cross-site lại có ràng buộc `SameSite`/`Secure` riêng.

## 3. Preflight: request OPTIONS có thể thất bại trước request thật

Khi frontend gửi request cross-origin có phương thức/header/content type cần kiểm tra trước, browser tự gửi một **CORS preflight request** bằng phương thức `OPTIONS`. Ví dụ JavaScript muốn gửi header `Authorization`:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Điểm quan trọng: đây là request **hỏi xem có được gửi GET với header Authorization không**, chứ **không phải** GET thật. Trong luồng thông thường, preflight không gửi session cookie `JSESSIONID` hoặc bearer token để xác thực người dùng. Nó mang thông tin cần kiểm tra **origin + phương thức + tên header**, không mang giá trị token.

Nếu CORS được phép, server trả một phản hồi dạng:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Các giá trị, thứ tự và việc có `Vary`/`Access-Control-Max-Age` cụ thể tùy cấu hình/framework. Browser kiểm tra các header và có thể gửi tiếp request GET thật. **Phản hồi preflight thành công không chứng minh GET sẽ thành công hoặc được xác thực.**

Nếu preflight bị trả 401 do Spring Security đòi đăng nhập trước khi CORS xử lý, hoặc bị trả 403 vì origin/method/header không được cho phép, trình duyệt có thể **không gửi GET thật**. Đây là lỗi lớp CORS/preflight; không nên bảo người dùng “đăng nhập lại” nếu vấn đề nằm ở thứ tự filter hoặc danh sách origin.

### 3.1. Request nào có thể không cần preflight?

Các request có phương thức đơn giản (`GET`, `HEAD` hoặc `POST`) với nhóm header được CORS safelist và `Content-Type` phù hợp có thể được gửi **trực tiếp**, không preflight. Ví dụ `GET` cross-origin chỉ với `Accept: application/json` thường không kích hoạt preflight. Khi đó máy chủ nhận **request thật** và có thể trả 401 hoặc 403 ngay.

Ngược lại, `Authorization`, header tùy chỉnh `X-...`, `PUT`, `DELETE` hoặc `Content-Type: application/json` trong nhiều tình huống khiến browser gửi preflight. Những chi tiết khác như browser và policy mạng cũng ảnh hưởng. **Không cố ý bỏ xác thực/header an toàn chỉ để tránh preflight.**

### 3.2. Tại sao Spring Security phải xử lý CORS trước kiểm tra đăng nhập?

Preflight thông thường không có credentials. Nếu một filter yêu cầu `Authentication` chạy trước CORS, nó có thể chặn `OPTIONS` bằng 401/403. Spring Security hỗ trợ tích hợp `CorsFilter` qua DSL `http.cors(...)` và `CorsConfigurationSource` để CORS được xử lý đúng thứ tự.

Đừng hiểu nhầm rằng chỉ cần thêm:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

là đủ cho mọi lỗi CORS. Câu lệnh đó chỉ ảnh hưởng **quy tắc phân quyền**; nó không tự sinh header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` hoặc cho phép browser đọc response. Nếu cần hỗ trợ OPTIONS, hãy xử lý CORS bằng cấu hình đúng, sau đó chỉ bổ sung rule phân quyền khi thật sự cần.

## 4. Ba mẫu lỗi nhìn giống nhau nhưng khác nguyên nhân

### Trường hợp A — preflight thất bại, request thực tế chưa được gửi

```text
Browser frontend (5173)
  -> OPTIONS /api/me [Origin, Request-Method, Request-Headers]
  <- 403 / 401 / thiếu header CORS
  -> KHÔNG gửi GET /api/me
  -> Console báo preflight/CORS; fetch không có response HTTP đọc được
```

Cách xử lý: xem request OPTIONS trong tab Network, Origin, phương thức/header yêu cầu, thứ tự CORS filter và policy server. Nếu 401 từ cơ chế xác thực do preflight chưa được CORS xử lý, sửa integration/thứ tự filter. Nếu origin thực sự không được phép, **không nới quyền bừa bãi**.

### Trường hợp B — request GET nhận 401/403 và có CORS header hợp lệ

```http
GET /api/me HTTP/1.1
Origin: http://localhost:5173
```

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
WWW-Authenticate: Basic realm="demo-api"
```

Browser có thể cho JavaScript truy cập `Response.status === 401`. Client lúc này phải xử lý **thiếu xác thực**, chẳng hạn chuyển sang luồng login đúng cơ chế. Đừng sửa bằng `allowedOrigins("*")` vì CORS **đã hoạt động**.

Với request đã xác thực nhưng thiếu quyền, server có thể trả `403 Forbidden` và CORS header hợp lệ. JavaScript đọc được 403; đó là **authorization**, không nhất thiết lỗi CORS.

### Trường hợp C — server trả 401/403 nhưng browser hiển thị CORS

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/json
// Không có Access-Control-Allow-Origin
```

Request có thể đã đến server và server đã xử lý xác thực, nhưng vì thiếu CORS header hợp lệ, browser không cho JavaScript thấy response. Trong JS, `fetch` thường reject bằng `TypeError` thay vì tạo một `Response` có status 401.

**Hai vấn đề cùng tồn tại**: thông tin xác thực không hợp lệ (401) *và* lỗi chia sẻ response (CORS). Cần sửa cấu hình để error response ở origin hợp lệ cũng có CORS header; **không** biến 401 thành 200 và **không** bỏ rule xác thực.

### Trường hợp D — lỗi mạng bị hiểu là CORS

```text
net::ERR_CONNECTION_REFUSED
TLS/certificate error
DNS resolution error
Mixed content: HTTPS page -> HTTP API
Browser extension/Ad blocker blocked request
```

Lỗi này không giải quyết bằng `@CrossOrigin`. Cần kiểm tra API có chạy, host/port đúng, certificate, mixed content và thiết bị mạng. MDN cũng phân biệt “CORS request did not succeed” khi kết nối/network/protocol thất bại, không phải do policy origin cụ thể.

## 5. Ma trận nhận diện nhanh trong DevTools

| Dấu hiệu | Suy luận ban đầu | Việc kiểm tra tiếp |
| --- | --- | --- |
| Có OPTIONS, bị 401; GET không xuất hiện | Preflight bị lớp xác thực chặn trước CORS hoặc quy tắc OPTIONS sai | Kiểm tra `http.cors()`, filter order, security matcher và log của OPTIONS. |
| OPTIONS trả 403 “Invalid CORS request” | Origin/method/header không được cho phép | Đối chiếu `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` với cấu hình. |
| OPTIONS 200 nhưng thiếu ACAO/allow-method/allow-header thích hợp | Preflight chưa được browser chấp nhận | Kiểm tra đủ các header CORS, proxy có xóa/chỉnh header không. |
| OPTIONS thành công, GET trả 401 **có ACAO** | CORS ổn, xác thực thất bại | Kiểm tra cookie/token/Authorization, thời hạn và entry point. |
| OPTIONS thành công, GET trả 403 **có ACAO** | CORS ổn, quyền không đủ hoặc filter khác trả 403 | Phân biệt AccessDenied, CSRF và rule ứng dụng trong log. |
| GET trả 401/403 **không có ACAO** | Xác thực/phân quyền thất bại và browser không đọc được lỗi | Thêm CORS handling cho cả response lỗi, giữ nguyên status bảo mật. |
| Không có status HTTP, “connection refused” hoặc TLS error | Lỗi hạ tầng/kết nối | Xem server startup, DNS, network, TLS, mixed content. |
| `curl` trả JSON 200 nhưng browser báo CORS | `curl` không thực thi SOP; chưa chứng minh CORS đúng | Dùng DevTools và request mang `Origin` đúng frontend. |
| Chỉ lỗi khi `credentials: "include"` | Cookie/credentialed CORS/third-party cookie policy có vấn đề | ACAO cụ thể, ACAC=true, cookie SameSite/Secure, CSRF. |
| 302 redirect đến trang login/IdP rồi báo CORS | Luồng login tương tác không phù hợp fetch/XHR hoặc redirect cross-origin | Xem chuỗi redirect và thiết kế OIDC/login đúng luồng. |

Bảng này là **gợi ý điều tra**, không phải chẩn đoán tự động. Ví dụ 403 có thể do CSRF, CORS filter, phân quyền hoặc một gateway/WAF; cần xem URL nào trả 403, status ở Network, phản hồi và log để kết luận.

## 6. Quy trình gỡ lỗi có thứ tự: Browser → HTTP → Spring Security → Gateway

### 6.1. Trong trình duyệt

1. Mở **Developer Tools → Network**, bật **Preserve log** khi cần quan sát redirect và filter **Fetch/XHR** (hoặc All để thấy OPTIONS).
2. Gây lại lỗi từ đúng frontend và kiểm tra **Request URL**, **Request Method**, **Origin**, status, redirect chain và error trong Console.
3. Nếu có `OPTIONS`, xem ba header request: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`; sau đó xem `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và status response.
4. Nếu OPTIONS được chấp nhận, tìm **request thật** `GET`/`POST`. Xem status 401, 403, 404, 500; response headers có ACAO và (nếu cần) ACAC không.
5. Kiểm tra request thật **có đúng Authorization/cookie không**. Một số trường hợp cookie không được gửi vì `credentials` mặc định hoặc `SameSite`/`Secure`/third-party cookie policy, không phải vì password sai.
6. Dùng tab **Console** để đọc lý do CORS mà browser cung cấp. JavaScript thường **không được biết chi tiết** lỗi CORS vì lý do bảo mật, nên cần DevTools Network và log server.
7. Nếu status là `(blocked)` hoặc request không kết nối, kiểm tra CSP, mixed content, DNS, TLS, extension và proxy. Không mặc định mọi `TypeError: Failed to fetch` đều là CORS.

**Không chia sẻ ảnh DevTools còn chứa Authorization, Cookie, access/refresh token, session ID hoặc thông tin cá nhân.** Khi viết ticket hoặc log, chỉ gửi status, route đã làm sạch và correlation ID được cấp an toàn.

### 6.2. Dùng `curl` đúng mục đích

Một lời gọi `curl` **không có Origin** kiểm tra endpoint và xác thực nhưng **không kiểm tra đầy đủ CORS browser**:

```bash
curl -i http://localhost:8080/api/me
```

Nếu API dùng HTTP Basic và chưa xác thực, phản hồi 401 là điều bình thường. Thêm `Origin` của frontend để xem server có trả ACAO hay không:

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/me
```

Mô phỏng preflight (lệnh hữu ích, không thay thế browser thật):

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Thử lại với origin không được cho phép:

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Kết quả cần phân biệt:

- Một response có status `401` và `Access-Control-Allow-Origin: http://localhost:5173` cho biết **CORS xử lý được request thật**, nhưng request chưa được xác thực.
- Một preflight `OPTIONS` được chấp nhận với ACAO, allowed methods và allowed headers cho biết browser có thể thử request thật; **không** chứng minh danh tính hợp lệ.
- Một preflight không được phép có thể trả 403 và không có ACAO. Đây là **CORS rejection**, không nhất thiết là thiếu vai trò của tài khoản.
- `curl` vẫn in response dù ACAO không có; chỉ **browser** mới thực thi việc chặn JavaScript đọc dữ liệu theo CORS.

### 6.3. Trong Spring Security

Xem cấu hình `SecurityFilterChain`:

- Có `http.cors(...)` không? Nó có dùng đúng `CorsConfigurationSource` hoặc hỗ trợ CORS của Spring MVC không?
- `securityMatcher` có khiến request `OPTIONS` hoặc URL thực tế rơi vào chain khác, thiếu CORS filter không?
- Có custom filter/WAF trong ứng dụng trả 401/403 **trước** khi CORS xử lý không?
- Có rule `anyRequest().authenticated()` khiến OPTIONS bị chặn vì chưa có cookie không?
- Status 401 đến từ `AuthenticationEntryPoint` nào? 403 từ `AccessDeniedHandler`, CSRF hay CORS?
- Response lỗi do controller/`@RestControllerAdvice` hoặc proxy trả có đi qua cùng CORS handling không?
- Khi bật DEBUG an toàn trên môi trường thử nghiệm, filter order và request matcher nào đã áp dụng?

**Không chỉ chỉnh `@CrossOrigin` trên controller** rồi cho rằng mọi phản hồi từ security filters đều được xử lý, vì một request có thể bị chặn trước khi vào MVC. Tích hợp CORS vào Spring Security chain là cách chủ động kiểm soát preflight.

### 6.4. Trong proxy/load balancer/API gateway

Có trường hợp ứng dụng trả header CORS đúng nhưng gateway xóa, nhân đôi hoặc thay đổi nó. Cũng có trường hợp gateway tự trả 401/403/502 mà **không chuyển request tới JVM**. Cần đối chiếu:

- Request ID, thời điểm, host và đường dẫn trong log proxy và backend.
- Response được tạo bởi ingress/gateway hay Spring Security/Servlet.
- `Access-Control-Allow-Origin` có bị ghi hai lần không; CORS không cho phép response có nhiều giá trị ACAO không phù hợp.
- `Vary: Origin` và cache khi server trả origin động; tránh cache response với ACAO của origin A rồi phát sai cho origin B.
- Chính sách preflight ở gateway và trong ứng dụng có bị xung đột không.

## 7. Ví dụ Java 17+ / Spring Boot 3.x: cấu hình để CORS đúng nhưng 401/403 vẫn được giữ nguyên

Thiết kế demo:

- Frontend được cho phép: `http://localhost:5173`.
- Backend: `http://localhost:8080`, dùng HTTP Basic **chỉ để minh họa**.
- `GET /api/public/ping` công khai; `GET /api/me` yêu cầu đăng nhập; `GET /api/admin/report` yêu cầu vai trò ADMIN.
- User demo `reader` có vai trò READER, **không** có ADMIN.
- Chỉ cho CORS với origin đã nêu, method GET/OPTIONS, header Authorization/Content-Type.
- Preflight được CORS xử lý trước xác thực; 401/403 của API vẫn mang ACAO cho origin được phép. Origin khác bị từ chối.
- Không vô hiệu hóa CSRF, không mở tất cả origin, không bỏ phân quyền.

**Giới hạn:** HTTP Basic gửi credentials trên mỗi request, vì vậy hệ thống thật phải dùng **HTTPS** và quản lý mật khẩu đúng cách. Tài khoản và mật khẩu demo trong bài chỉ là dữ liệu thử nghiệm; không nhúng mật khẩu thật vào source/frontend.

### 7.1. Dependency

Tạo dự án Spring Boot 3.x có Gradle plugin, Java toolchain 17+ và thêm các dependency trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **trích đoạn dependencies**, không phải một file build hoàn chỉnh. Các lớp Java dùng cùng package `demo.corsdiagnosis`.

### 7.2. Ứng dụng khởi động

Tệp `src/main/java/demo/corsdiagnosis/CorsDiagnosisApplication.java`:

```java
package demo.corsdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}
```

### 7.3. `CorsConfigurationSource` và `SecurityFilterChain`

Tệp `src/main/java/demo/corsdiagnosis/SecurityConfig.java`:

```java
package demo.corsdiagnosis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
public class SecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chỉ frontend đã được phê duyệt; không dùng "*" cho credentials.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false); // Demo không sử dụng cookie cross-origin.
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource
    ) throws Exception {

        http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF. Ví dụ chỉ có các endpoint GET.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("READER")
                .build()
        );
    }
}
```

**Giải thích chính xác trách nhiệm:**

- `corsConfigurationSource()` chỉ cho `http://localhost:5173`. `localhost` khác `127.0.0.1`; `http` khác `https`; port cũng là một phần origin.
- `registerCorsConfiguration("/api/**", cors)` gắn policy cho API. Một route khác không có cấu hình CORS tương ứng không mặc nhiên được chia sẻ cross-origin.
- `.cors(cors -> cors.configurationSource(corsSource))` tích hợp xử lý CORS vào Spring Security và cho preflight đúng đường xử lý. Khi request thật được phép theo CORS, bước xác thực/phân quyền vẫn diễn ra.
- `.setAllowedHeaders(List.of("Authorization", "Content-Type"))` cho phép browser xin dùng các header đó trong preflight; nó **không xác nhận giá trị** header Authorization là hợp lệ.
- `setAllowCredentials(false)` phù hợp cho ví dụ không dùng cookie CORS; với cookie cross-origin cần cấu hình khác có giới hạn.
- `requestMatchers("/api/admin/**").hasRole("ADMIN")` khiến user demo READER bị 403. `/api/me` yêu cầu xác thực nên request không có credentials trả 401 theo cơ chế Basic.
- `anyRequest().denyAll()` ngăn endpoint ngoài phạm vi demo vô tình mở công khai.
- `httpBasic(...)` dùng Spring Security tích hợp; không tự viết filter đọc header Basic. Khi chuyển sang Bearer/JWT, thay cơ chế xác thực nhưng vẫn giữ **tách biệt** giữa policy CORS và quyền.
- Không có `csrf.disable()`: yêu cầu thay đổi trạng thái dùng session/cookie vẫn phải đánh giá CSRF riêng, không liên quan việc cấu hình CORS cho GET.

**Quan trọng về bean:** Code chủ động truyền `CorsConfigurationSource` vào DSL để không phụ thuộc việc Spring Security chọn nguồn cấu hình nào nếu hệ thống có nhiều nguồn CORS. Trong ứng dụng lớn có nhiều `SecurityFilterChain`, cần quyết định policy của **từng chain** và vị trí matcher tương ứng.

### 7.4. Controller

Tệp `src/main/java/demo/corsdiagnosis/DemoController.java`:

```java
package demo.corsdiagnosis;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin/report")
    public Map<String, Boolean> adminReport() {
        return Map.of("ok", true);
    }
}
```

Các endpoint GET này chỉ để minh họa kiểm tra. Không tạo thao tác thay đổi trạng thái bằng GET trong ứng dụng thật. Với người chưa xác thực, controller `/api/me` **không được chạy**; Security chặn trước. Với user READER, `/api/admin/report` bị từ chối trước controller. CORS có thể vẫn thêm header cho response lỗi.

### 7.5. JavaScript quan sát lỗi từ trình duyệt

Đặt frontend ở origin `http://localhost:5173` rồi chạy trong DevTools Console:

```javascript
async function checkApi() {
  try {
    const response = await fetch("http://localhost:8080/api/me", {
      mode: "cors"
    });

    console.log("HTTP status:", response.status);
    console.log("Readable by JS:", true);

    if (response.status === 401) {
      console.log("Request needs authentication");
    } else if (response.status === 403) {
      console.log("Authenticated account lacks access, or request was denied");
    }
  } catch (error) {
    console.log("No readable HTTP response");
    // Đây chưa phải bằng chứng chắc chắn lỗi CORS:
    // có thể là TLS, DNS, connection failure, mixed content...
    console.error(error);
  }
}
checkApi();
```

Với server ví dụ và đúng origin, request không có Authorization thường tạo **401 đọc được bởi JavaScript**, không phải exception CORS. Một `fetch` resolved với status 401 vẫn là kết quả HTTP bình thường; `fetch` **không tự reject** chỉ vì response có HTTP 401 hoặc 403.

Nếu chạy cùng mã từ origin không được phép, có thể xảy ra lỗi CORS và `catch` chạy, dù server tạo response khác. Không suy luận rằng catch luôn đồng nghĩa sai password.

Không để mật khẩu demo trong mã JavaScript sản phẩm để thử authentication; các ca xác thực thành công và phân quyền dưới đây được kiểm tra bằng MockMvc hoặc HTTP client thử nghiệm.

## 8. Kiểm thử MockMvc: preflight và xác thực là hai nhóm assertion riêng

Tệp `src/test/java/demo/corsdiagnosis/CorsAndAuthenticationTests.java`:

```java
package demo.corsdiagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndAuthenticationTests {

    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String REJECTED_ORIGIN = "https://untrusted.example";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightFromAllowedOriginIsAcceptedWithoutLogin()
            throws Exception {
        mvc.perform(options("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(header().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS
            ))
            .andExpect(header().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS
            ));

        // Không có Authorization/cookie nhưng OPTIONS vẫn được CORS xử lý.
    }

    @Test
    void preflightFromRejectedOriginDoesNotGrantCors() throws Exception {
        mvc.perform(options("/api/me")
                .header(HttpHeaders.ORIGIN, REJECTED_ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"
                ))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }

    @Test
    void actualGetWithoutCredentialsIs401ButCorsSucceeds()
            throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void invalidPasswordIsStill401WithCorsHeaders() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void authenticatedReaderCanReadMeWithCors() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(jsonPath("$.user").value("reader"));
    }

    @Test
    void readerCannotAccessAdminBut403IsReadableByBrowser()
            throws Exception {
        mvc.perform(get("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "demo-password")))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void requestWithoutOriginStillUsesServerAuthentication()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }

    @Test
    void publicEndpointFromAllowedOriginWorks() throws Exception {
        mvc.perform(get("/api/public/ping")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(jsonPath("$.result").value("pong"));
    }
}
```

Chạy trong dự án Spring Boot có Gradle wrapper:

```bash
./gradlew test --tests demo.corsdiagnosis.CorsAndAuthenticationTests
```

Đây là **8 test được thiết kế để kiểm tra hành vi mong đợi**; bài viết không khẳng định đã chạy lệnh trong môi trường người đọc. Nếu ứng dụng đúng cấu hình, 8 ca cần PASS. Chúng kiểm tra:

| Ca | HTTP status kỳ vọng | CORS header | Điều chứng minh |
| --- | --- | --- | --- |
| Preflight origin cho phép, thiếu login | 200 | ACAO chính xác, allow-method/header | Không cần xác thực để hỏi quyền cross-origin. |
| Preflight origin cấm | 403 | Không có ACAO | CORS từ chối origin, không mở bừa API. |
| GET thực không credentials, origin hợp lệ | 401 | ACAO hợp lệ | Lỗi xác thực vẫn đọc được trong browser. |
| GET với mật khẩu sai, origin hợp lệ | 401 | ACAO hợp lệ | CORS không “sửa” authentication. |
| GET với tài khoản hợp lệ | 200 | ACAO hợp lệ | Chia sẻ response và xác thực đều hoạt động. |
| GET admin với user READER | 403 | ACAO hợp lệ | Thiếu quyền khác với CORS failure. |
| GET không có Origin | 401 | Không cần ACAO | Server vẫn thực hiện authentication dù không có CORS. |
| GET public, origin hợp lệ | 200 | ACAO hợp lệ | Endpoint công khai đúng chính sách. |

**Giới hạn kiểm thử:** MockMvc giả lập request và filter chain trong ứng dụng; nó **không thực thi chính sách CORS của browser** và không kiểm tra nginx/ingress/CDN. Với production cần thêm kiểm thử end-to-end dùng trình duyệt thật, hạ tầng proxy thật, cookie thực và đúng origin frontend. Tuy nhiên MockMvc là cách hiệu quả để kiểm chứng riêng **status của server** và **header CORS** trước khi gỡ lỗi giao diện.

## 9. Khác biệt khi dùng cookie session và `credentials: "include"`

Ví dụ phía trên không gửi cookie cross-origin. Ứng dụng dùng session cookie cần hiểu **ba lớp riêng**:

1. Browser có gửi cookie không, xét `fetch(credentials)`, `SameSite`, `Secure`, domain/path và third-party cookie restrictions?
2. CORS có cho JavaScript đọc **credentialed response** không, xét ACAO và ACAC?
3. Spring Security có nhận session đó, cho phép thao tác và kiểm tra CSRF không?

Một frontend session-cookie có thể gọi:

```javascript
const result = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
console.log(result.status);
```

Khi cho phép credentials cross-origin, response cần chính sách phù hợp, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Trong Java config, cấu hình **chỉ cho danh sách origin tin cậy**:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cors.setAllowCredentials(true);
```

Đây là **trích đoạn cấu hình thay thế** cho API dùng cookie; cần đặt trong một `CorsConfigurationSource` phù hợp, không gắn chồng lên ví dụ HTTP Basic nếu chưa thay mô hình xác thực.

Những điểm dễ nhầm:

- Khi request dùng credentials, **không** trả `Access-Control-Allow-Origin: *`; browser không chấp nhận wildcard cho credentialed CORS.
- `Access-Control-Allow-Credentials: true` **không khiến cookie tự được gửi** nếu `SameSite`, `Secure`, domain/path, third-party cookie policy hoặc `fetch` không cho phép.
- Cookie được gửi đến API **không chứng minh người dùng có quyền**; phiên có thể hết hạn hoặc thiếu quyền.
- `SameSite=None; Secure` có thể cần cho cookie dùng trong ngữ cảnh **cross-site**, nhưng **cross-origin** và **cross-site** không giống nhau.
- CORS không thay thế **CSRF protection**. Một trang được cho phép đọc response không có nghĩa mọi request thay đổi trạng thái đều được miễn CSRF.
- Khi dùng `Origin` động hoặc origin patterns, phải bảo đảm policy có chủ đích và cache được phân biệt đúng bằng `Vary: Origin`.

Ví dụ này cũng giúp phân biệt hai tình huống browser thường hiển thị gần giống nhau: **cookie không được gửi nên server trả 401 hợp lệ**, và **CORS credentialed headers không hợp lệ khiến JavaScript không đọc được cả 401**.

## 10. 401, 403, redirect và login: những nhầm lẫn trong ứng dụng thực tế

### 10.1. API JSON khác website dùng form login

Ứng dụng web dùng `formLogin` mặc định có thể đáp lại request chưa đăng nhập bằng:

```http
HTTP/1.1 302 Found
Location: /login
```

Browser fetch tự đi theo redirect theo cấu hình mặc định. Nếu redirect dẫn tới một origin khác, như Identity Provider, kết quả có thể trông như lỗi CORS ở bước redirect hoặc trang login; không phải vì tài khoản API đã “mất quyền”.

Đối với API JSON, thường nên có hợp đồng status-based 401 và hướng dẫn frontend khởi động luồng đăng nhập đúng cách. Với OIDC/OAuth, chuyển hướng người dùng qua **navigation/top-level redirect** theo thiết kế, không dùng fetch để coi HTML login ở IdP như JSON API. Đừng chỉ mở CORS mọi origin của IdP để làm mất thông báo.

### 10.2. 403 không chỉ có nghĩa “thiếu role”

Spring Security hoặc các thành phần trước controller có thể trả 403 khi:

- Người dùng đã xác thực nhưng không có authority/role cần thiết.
- CSRF token thiếu/sai ở request thay đổi trạng thái với CSRF bật.
- CORS filter từ chối origin/method/header, thường trả “Invalid CORS request”.
- Gateway/WAF chặn request theo quy tắc riêng.
- Ứng dụng chủ đích trả 403 vì chính sách nghiệp vụ.

Vì vậy, hãy xác định **filter/handler nào trả 403**, request `OPTIONS` hay request thật, log và response header. Không nên tự động kết luận “role thiếu” mỗi khi thấy 403.

### 10.3. HTTP 401 cần challenge phù hợp

Với HTTP Basic hoặc Bearer, `WWW-Authenticate` là phần quan trọng của giao thức. Nếu tùy chỉnh `AuthenticationEntryPoint` để trả JSON, vẫn phải giữ challenge tương thích với cơ chế được sử dụng. Không vô hiệu hóa Spring Security hay xóa `WWW-Authenticate` chỉ vì muốn 401 nhìn giống một response khác.

Nếu browser bị CORS chặn, JavaScript **không đọc được** body/header 401; giải pháp là CORS policy đúng đối với origin có quyền xem phản hồi, **không phải** trả token/challenge cho mọi origin tùy ý.

## 11. Những cách “sửa CORS” không nên làm

### 11.1. Dùng `mode: "no-cors"`

```javascript
// Không phải giải pháp để đọc JSON API.
fetch("http://localhost:8080/api/me", { mode: "no-cors" });
```

Chế độ `no-cors` làm phản hồi trở nên **opaque** trong nhiều trường hợp: JavaScript không đọc được status/body/header như JSON API thông thường; `response.status` thường là 0. Nó không “bỏ qua bảo mật browser” theo cách giúp bạn dùng response.

### 11.2. Mở CORS cho tất cả origin

```java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
```

Đây là cấu hình không hợp lệ cho credentialed CORS trong Spring Framework hiện đại và là dấu hiệu thiết kế nguy hiểm. Đừng phản ứng trước lỗi CORS bằng cách cho phép mọi origin. Thay vào đó, xác định origin frontend thực sự, method, header và nhu cầu credentials. Nếu dùng allowed-origin patterns, hãy đánh giá origin được match thật, tránh pattern quá rộng cho API nhạy cảm.

### 11.3. Tắt `http.cors()` hoặc tắt toàn bộ Spring Security

`http.cors(cors -> cors.disable())` vô hiệu hóa tích hợp CORS của Spring Security; **nó không tắt Same-Origin Policy của trình duyệt**. Việc tắt authorization/CSRF để browser không còn báo 401/403 có thể mở lỗ hổng bảo mật nghiêm trọng mà vẫn không tạo các header CORS cần thiết.

### 11.4. Chỉ thêm `@CrossOrigin`

`@CrossOrigin` trong Spring MVC có ích cho endpoint/controller và có thể được Spring Security sử dụng **khi tích hợp CORS đúng cách**. Nhưng các phản hồi do security filter, gateway hoặc chuỗi khác tạo ra trước controller cần được kiểm thử; một annotation controller không bảo đảm bao phủ mọi preflight/401/403.

### 11.5. Chỉ trả HTTP 200 để browser không báo lỗi

HTTP 200 cho request chưa đăng nhập phá hợp đồng API và giám sát. Nếu CORS được phép mà user chưa xác thực, **401 có ACAO** là kết quả hợp lý. Với user đã xác thực thiếu quyền, **403 có ACAO** cũng có thể là kết quả đúng.

### 11.6. Tin rằng `curl` thành công đồng nghĩa browser được phép đọc

`curl` chỉ kiểm tra HTTP response. Browser còn áp dụng SOP, CORS credentials, preflight, redirects và cookie policies. Cần kiểm thử cả hai phía.

### 11.7. Thêm CORS header ở nhiều tầng không kiểm soát

Nếu Spring Boot và gateway cùng chèn ACAO, response có thể có **hai giá trị** hoặc wildcard lẫn origin cụ thể khiến browser từ chối. Phân định nơi chịu trách nhiệm CORS, kiểm tra final response tại điểm trình duyệt nhận được.

## 12. Kiểm tra riêng error path, nhiều chain và tình huống biên

### 12.1. Lỗi từ custom filter trước CORS

Một filter do ứng dụng tự đăng ký ở Servlet container có thể trả lỗi **trước** `springSecurityFilterChain`. Khi đó cấu hình `http.cors()` trong Spring Security không thể “quay ngược thời gian” để thêm header cho response đã được commit. Cần chuyển trách nhiệm, điều chỉnh thứ tự hoặc bảo đảm response do filter đó tạo có hợp đồng CORS phù hợp với chính sách.

Tương tự, response từ reverse proxy hoặc API gateway cần cấu hình tương ứng tại tầng tạo ra lỗi.

### 12.2. Nhiều `SecurityFilterChain`

Ví dụ có chain `/api/admin/**` với `@Order(1)` và chain `/api/**` với `@Order(2)`. `FilterChainProxy` chọn **chain đầu tiên khớp**. Nếu chỉ bật CORS trong chain thứ hai, request admin có thể không đi qua cùng CorsFilter, dẫn đến 401/403 admin bị browser báo CORS. Hãy kiểm tra matcher, thứ tự và CORS config của **từng chain**.

### 12.3. Preflight cache, error caching và `Vary`

Preflight có thể được browser cache theo `Access-Control-Max-Age` trong giới hạn riêng của trình duyệt. Khi sửa cấu hình CORS, có thể cần thử profile mới hoặc điều kiện cache khác để tránh nhìn kết quả cũ. Tuy nhiên không nên nhầm preflight cache với HTTP cache của response dữ liệu.

Nếu trả ACAO theo origin từ allowlist động, header `Vary: Origin` giúp cache trung gian phân biệt biến thể. Đối với preflight, `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers` cũng có thể quan trọng.

### 12.4. Redirect, OPTIONS và lỗi vượt ra ngoài ứng dụng

Không giả định mọi `302`/`307` trên preflight sẽ hoạt động đồng nhất ở mọi trình duyệt. Tránh redirect không cần thiết trước khi CORS xử lý, ví dụ HTTP → HTTPS ở sai tầng hoặc redirect OPTIONS tới login. Cấu hình frontend gọi trực tiếp origin HTTPS chính xác, kiểm tra redirect chain trong DevTools.

Nếu browser báo **mixed content**, chứng chỉ không tin cậy, DNS, firewall hay connection refused, ưu tiên giải quyết kết nối: CORS headers chỉ tồn tại khi có HTTP response phù hợp.

### 12.5. WebSocket, SSE và private network

- WebSocket có handshake và quy tắc bảo mật origin riêng; **không** lấy kiểm thử Fetch CORS làm bằng chứng bảo vệ WebSocket.
- Server-Sent Events/EventSource chịu một số quy tắc cross-origin/credentials; kiểm thử đúng client được dùng.
- Một số phiên bản trình duyệt có kiểm tra liên quan truy cập mạng riêng (Private Network Access). Đây là vấn đề bổ sung theo browser/environment, không đồng nghĩa với 401/403 của Spring Security.

## 13. Checklist chẩn đoán theo trình tự ưu tiên

Khi nhận ticket “frontend lỗi CORS”:

1. **Ghi đúng nguồn:** frontend origin (scheme/host/port), API URL, method, status trong Network, có OPTIONS không. Không ghi token/cookie thật.
2. **Kiểm tra mạng:** backend có chạy, DNS/TLS/mixed content có ổn, browser extension có can thiệp không.
3. **Kiểm tra preflight:** nếu có OPTIONS, xem response status và ACAO/allowed methods/headers; xác minh xử lý trước authentication.
4. **Kiểm tra request thật:** có được gửi không; status 200/401/403/500; CORS header có trên cả error path không.
5. **Tách authn/authz:** 401 do thiếu/sai credentials, 403 do thiếu quyền hay CSRF/CORS/gateway; kiểm tra security chain/entry point/handler.
6. **Kiểm tra credentialed CORS:** `fetch.credentials`, cookie attributes, ACAO cụ thể và ACAC; không dùng wildcard, không mặc định mở CSRF.
7. **Đối chiếu với `curl`:** gọi có và không có Origin, mô phỏng OPTIONS; nhớ `curl` không thực thi SOP.
8. **Kiểm tra Spring:** `CorsConfigurationSource`, `http.cors`, custom filters, nhiều `SecurityFilterChain` và error handler.
9. **Kiểm tra gateway:** header có bị ghi đè/nhân đôi; lỗi 401/403 có xuất hiện trước backend; cache có trộn origin không.
10. **Viết regression tests:** allowed preflight 200, blocked preflight không có ACAO, request thật 401/403 kèm ACAO cho origin hợp lệ, request thành công 200 và test browser từ origin thực.

### Ma trận nghiệm thu cuối cùng

| Tình huống | Chẩn đoán đúng | Tiêu chí đạt |
| --- | --- | --- |
| Origin hợp lệ + OPTIONS không có credentials | CORS preflight | CORS xử lý không đòi login; method/header được cho phép chính xác. |
| Origin không hợp lệ + OPTIONS | CORS rejection | Không cho origin bị cấm đọc response; không nới wildcard. |
| Origin hợp lệ + GET chưa đăng nhập | Authentication | 401, browser có thể đọc response lỗi qua ACAO. |
| Origin hợp lệ + GET đã login nhưng thiếu quyền | Authorization | 403, browser đọc được status theo policy. |
| Origin hợp lệ + GET credentials hợp lệ | Happy path | 200, JSON đúng, có ACAO phù hợp. |
| Cookie cross-origin | CORS + cookie policy + session/CSRF | ACAO không dùng `*`, ACAC/cookie đúng, quyền vẫn được kiểm tra. |
| Network/TLS lỗi | Hạ tầng | Kết nối được sửa; không “sửa” bằng mở CORS. |
| CORS đúng ở backend nhưng sai tại browser | Gateway/cache/redirect | Final response trong DevTools đúng policy và không có header trùng. |

**Nguyên tắc kết luận:** Đừng hỏi “CORS hay Security?” như thể chỉ được chọn một. Hãy hỏi **request nào**, **đã đến server chưa**, **status nào được tạo ở đâu**, **browser có quyền đọc response đó không**, và **người gọi có được xác thực/phân quyền không**. Chỉ sau khi phân biệt các câu trả lời đó mới nên sửa cấu hình.

## 14. Tài liệu tham khảo

- Spring Security 6.5 — [CORS trong Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html).
- Spring Security 6.5 — [SecurityFilterChain và Servlet architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
- Spring Security 6.5 — [Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html).
- Spring Framework — [CORS và MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- MDN — [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- MDN — [Thông báo lỗi CORS và cách chẩn đoán](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors).
- MDN — [Reason: CORS request did not succeed](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSDidNotSucceed).
- MDN — [Fetch API, request credentials và xử lý HTTP error](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).