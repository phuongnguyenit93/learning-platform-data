# allowCredentials và giới hạn của origin ký tự đại diện trong CORS

**Phạm vi:** Spring Security trên **Servlet/Spring MVC**, ứng dụng Spring Boot 3.x / Spring Security 6.x; ví dụ Java 17+. Bài học giải thích chính xác khi nào dùng `allowCredentials(true)`, vì sao không thể ghép nó với `allowedOrigins("*")`, cách cấu hình allowlist an toàn và cách quan sát preflight/response từ trình duyệt.

## 1. Nắm đúng ba khái niệm: origin, CORS và credentials

**Origin** gồm ba thành phần: **scheme + host + port**. Chỉ một thành phần khác là **khác origin**.

| URL A | URL B | Cùng origin? | Lý do |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/profile` | Có | Đường dẫn không thuộc origin. |
| `https://app.example.com` | `https://api.example.com` | Không | Host khác nhau. |
| `http://localhost:5173` | `http://localhost:8080` | Không | Port khác nhau. |
| `http://example.com` | `https://example.com` | Không | Scheme khác nhau. |

**CORS (Cross-Origin Resource Sharing)** là cơ chế trình duyệt dùng để quyết định liệu JavaScript ở origin A có được đọc response HTTP từ origin B hay không. Server khai báo chính sách bằng các header `Access-Control-Allow-*`. Same-origin policy vẫn là mặc định; server chỉ nới quyền truy cập cho origin được cấp phép.

**Credentials** trong ngữ cảnh Fetch/CORS có thể gồm cookie, HTTP authentication và chứng chỉ TLS client. Với ứng dụng session-based, cookie xác thực như `JSESSIONID` là trường hợp thường gặp. Chú ý có **hai quyết định khác nhau**:

1. **Client** chọn chế độ gửi/nhận credentials (`fetch(..., { credentials: "include" })` đối với cross-origin).
2. **Server** có chấp nhận công bố response cho một cross-origin request mang credentials hay không (`Access-Control-Allow-Credentials: true` cùng với origin hợp lệ).

Header `Access-Control-Allow-Credentials: true` **không tự buộc trình duyệt gửi cookie**, **không làm cookie vượt quy tắc SameSite/Secure** và **không có nghĩa là cho phép mọi origin**.

## 2. Quy tắc trọng tâm: credentials không đi cùng wildcard origin "*"

Giả sử JavaScript ở `https://app.example.com` gọi `https://api.example.com/api/profile` với `credentials: "include"`. Cấu hình response **sai**:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Với request có credentials, trình duyệt **không chấp nhận** `Access-Control-Allow-Origin: *` để công bố response cho JavaScript. Đây là quy tắc của CORS, không phải đặc thù Spring. Developer Tools có thể báo lỗi tương tự: *The value of the 'Access-Control-Allow-Origin' header must not be '*' when the request's credentials mode is 'include'.*

**Cấu hình đúng** cho một frontend được cho phép:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

`Access-Control-Allow-Origin` chỉ định **một origin cụ thể** được phép (không chứa path); nếu có nhiều origin trong allowlist, server chọn/echo đúng origin của request khi được phép, chứ không trả về danh sách origin ngăn bằng dấu phẩy. `Vary: Origin` giúp cache phân biệt các response có thể khác nhau theo origin; với preflight, Spring còn có thể thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers` vào `Vary`.

Đối với resource **công khai** không cần credentials, cấu hình `Access-Control-Allow-Origin: *` có thể phù hợp. Khi frontend gửi `credentials: "include"`, wildcard vẫn không hợp lệ dù endpoint là public; client có thể cân nhắc `credentials: "omit"` nếu thực sự không cần credentials.

| Tình huống | `Access-Control-Allow-Origin` | `Access-Control-Allow-Credentials` | Kết quả từ trình duyệt |
| --- | --- | --- | --- |
| Request không mang credentials, API public | `*` | Không cần `true` | Có thể đọc response nếu các quy tắc CORS khác cũng đạt. |
| Request `credentials: "include"`, frontend hợp lệ | `https://app.example.com` | `true` | Được công bố response nếu các điều kiện CORS, cookie và xác thực khác đạt. |
| Request `credentials: "include"` | `*` | `true` | **Bị CORS chặn** khi JavaScript đọc response. |
| Request `credentials: "include"`, origin cụ thể | `https://app.example.com` | Thiếu/không phải `true` | **Bị CORS chặn** với credentialed request. |
| Origin lạ không trong allowlist | Không trả origin phù hợp | Không cấp phép | Trình duyệt không cho JavaScript của origin lạ đọc response. |

**Quan trọng:** CORS là chính sách của **trình duyệt**, không phải hệ thống xác thực hay phân quyền server. `curl`, Postman và backend khác vẫn có thể gọi API; `Origin` có thể được giả lập bởi non-browser client. Endpoint vẫn phải kiểm tra session/token, quyền truy cập và dữ liệu đầu vào. Một *simple request* có thể đã được gửi tới server trước khi trình duyệt chặn JavaScript đọc response; vì vậy CORS **không thay thế CSRF protection**.

## 3. Spring Framework: allowedOrigins khác allowedOriginPatterns

Trong Spring MVC/Security, `CorsConfiguration` có hai cách cấu hình origin thường gặp:

**Cách A — liệt kê chính xác các origin tin cậy (ưu tiên):**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
    "https://app.example.com",
    "http://localhost:5173"
));
cors.setAllowCredentials(true);
```

Mỗi phần tử `allowedOrigins` là một origin bao gồm scheme, host, port nếu có; không kèm path, query, dấu `*` trong host, hoặc dấu `/` ở cuối. Chỉ đưa `localhost` vào profile môi trường development, không để mở trong production không cần thiết.

**Cách B — dùng pattern khi thật sự có nhiều subdomain hợp lệ:**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.example.com"
));
cors.setAllowCredentials(true);
```

Với origin thực tế được pattern khớp, Spring sẽ ghi **origin cụ thể đã khớp** vào `Access-Control-Allow-Origin`, ví dụ `https://portal.example.com`; header response **không chứa pattern** `https://*.example.com`. Điều này cho phép `allowCredentials(true)` hoạt động về mặt giao thức. Tuy nhiên mọi subdomain khớp pattern đều được tin cậy: một subdomain do bên thứ ba quản lý hoặc bị chiếm quyền có thể tạo rủi ro. Pattern trên cũng không thay thế mặc nhiên origin gốc `https://example.com`; nếu cần, thêm riêng.

**Cách cấu hình cần tránh:**

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true); // Không hợp lệ khi kết hợp "*".
```

Spring kiểm tra sự kết hợp này qua `validateAllowCredentials()` và có thể ném `IllegalArgumentException` khi xử lý CORS: không thể điền `*` vào `Access-Control-Allow-Origin` đối với response hỗ trợ credentials. Tương tự, `@CrossOrigin(origins = "*", allowCredentials = "true")` là cấu hình xung đột.

**Đừng “sửa” bằng `allowedOriginPatterns("*")` một cách máy móc.** Mặc dù Spring có thể echo origin cụ thể và cho phép credentials với pattern toàn cục, hiệu quả của nó là tin cậy **mọi** website để đọc response credentialed (nếu cookie thực sự được gửi và endpoint cho phép). Đó là một chính sách quá rộng đối với API mang dữ liệu riêng tư.

## 4. Cấu hình hoàn chỉnh cho Spring Security Servlet

Ví dụ ứng dụng Spring Boot 3.x có frontend development ở `http://localhost:5173` và frontend production ở `https://app.example.com`. Backend đăng ký CORS cho `/api/**` và giữ Spring Security bảo vệ những endpoint cần đăng nhập.

Các file Java bên dưới cùng package `com.example.corsdemo`, đặt trong `src/main/java/com/example/corsdemo/`. Ví dụ cần các dependency `spring-boot-starter-web` và `spring-boot-starter-security` trên classpath; chúng **không phải** chương trình `javac` thuần độc lập.

**`CorsConfig.java`:**

```java
package com.example.corsdemo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Origin cụ thể, KHÔNG dùng "*" khi bật credentials.
        config.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));
        config.setAllowCredentials(true);

        // Giới hạn hành động và request headers thực sự cần dùng.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
        ));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"
        ));
        config.setExposedHeaders(List.of("X-Request-ID"));
        config.setMaxAge(1800L); // Browser có thể cache preflight.

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
```

**`SecurityConfig.java`:**

```java
package com.example.corsdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource) throws Exception {

        http
            // Áp dụng CORS ở Security filter chain,
            // để preflight OPTIONS đi qua trước authentication.
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Giữ CSRF protection mặc định cho unsafe methods.
        return http.build();
    }
}
```

**`ApiController.java`:**

```java
package com.example.corsdemo;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public ResponseEntity<Map<String, String>> publicData() {
        return ResponseEntity.ok()
            .header("X-Request-ID", "demo-001")
            .body(Map.of("message", "public"));
    }

    @GetMapping("/api/account")
    public Map<String, String> account(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/api/items")
    public Map<String, String> receive(
            @RequestBody Map<String, String> input) {
        // Chỉ echo để minh họa; không lưu database.
        return Map.of("received", input.getOrDefault("name", ""));
    }
}
```

**`CorsDemoApplication.java`:**

```java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

Nếu cần khởi tạo dự án mới, chọn **Spring Initializr → Gradle, Java 17+, Spring Boot 3.x, Spring Web, Spring Security**, thêm bốn file trên rồi chạy lệnh wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, dùng `.\gradlew.bat bootRun`. URL mặc định khi chưa đổi `server.port` là `http://localhost:8080`; máy frontend dùng `http://localhost:5173`. Mật khẩu demo mặc định của Spring Security (nếu dùng user tự sinh) xuất hiện trong log startup; chỉ phục vụ thử nghiệm, không dùng trong production.

**Điều gì xảy ra?**

- `GET /api/public` được phép khi chưa đăng nhập. Browser từ origin được phép nhận `Access-Control-Allow-Origin` tương ứng và `Access-Control-Allow-Credentials: true`. Header `X-Request-ID` được JavaScript đọc vì có `exposedHeaders`.
- `GET /api/account` cần session đăng nhập. CORS hợp lệ chỉ giúp trình duyệt đọc response **khi xác thực cũng hợp lệ**.
- `POST /api/items` còn chịu CSRF protection. Request cross-origin có cookie phiên và CORS đúng **vẫn có thể bị 403** nếu thiếu CSRF token. Muốn gọi POST thật, phải tích hợp cách phát/đọc CSRF token phù hợp (ví dụ cookie + header `X-XSRF-TOKEN`) và bảo đảm token client truy cập được theo kiến trúc origin/cookie đã chọn. Đừng tắt CSRF để “sửa” lỗi CORS.
- Với một cấu hình source cho `/api/**`, CORS policy không tự áp dụng cho mọi đường dẫn khác (như `/login`). Nếu frontend bắt buộc login bằng XHR cross-origin, cần thiết kế thêm luồng đăng nhập/session/cookie phù hợp; code này chỉ minh họa GET public, GET authenticated và preflight API.

Trong ứng dụng Spring Security, xử lý CORS **trước các bước kiểm tra authentication** rất quan trọng vì request preflight `OPTIONS` thường **không mang cookie phiên**. Việc cấu hình `http.cors(...)` để Spring Security dùng `CorsConfigurationSource` giúp request preflight được xử lý đúng chỗ. Đừng chỉ viết một filter thủ công trả `Access-Control-Allow-Origin` cho tất cả request, dễ sinh header trùng hoặc thiếu chính sách.

## 5. Frontend: credentials phải được bật từ phía Fetch

Ví dụ JavaScript chạy trên frontend `http://localhost:5173` gọi API `http://localhost:8080`:

```javascript
const apiBase = "http://localhost:8080";

async function readPublicData() {
  const response = await fetch(apiBase + "/api/public", {
    method: "GET",
    credentials: "include"
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const data = await response.json();
  const requestId = response.headers.get("X-Request-ID");

  console.log(data, requestId);
}

readPublicData();
```

Khi server chạy đúng và origin nằm trong allowlist, dòng log ví dụ là:

```text
{message: 'public'} 'demo-001'
```

Cách định dạng object trong DevTools có thể thay đổi theo browser, nhưng nội dung JSON là `{"message":"public"}` và header được đọc là `demo-001`.

Các chế độ credentials của Fetch:

- `omit`: không gửi credentials và không xử lý nhận credentials theo chế độ này; thích hợp cho API thực sự công khai.
- `same-origin`: mặc định của Fetch; gửi credentials cho request cùng origin, **không gửi cookie cho cross-origin request**.
- `include`: cho phép gửi/nhận credentials cả khi cross-origin, **tùy giới hạn cookie và chính sách trình duyệt**. Server phải trả CORS headers phù hợp để JavaScript đọc response.

Khác origin **không đồng nghĩa** khác site. Hai port trên `localhost` là khác origin nhưng có thể cùng site; `app.example.com` và `api.example.com` là khác origin nhưng thường cùng site. Ngược lại, từ `other-domain.test` sang `api.example.com` là cross-site. Cookie `SameSite=Lax` hoặc `Strict`, `Secure`, giới hạn third-party cookies và partitioning có thể ngăn cookie trong một số cross-site request **dù CORS đã hợp lệ**. Với cookie cần gửi ở ngữ cảnh cross-site, thường phải cân nhắc `SameSite=None; Secure` và vẫn chịu chính sách chặn cookie của browser. Tuyệt đối không coi việc nới `SameSite` là giải pháp mặc định cho mọi hệ thống.

**Nếu JS cần POST với CSRF token:** CORS phải cho phép request header `X-XSRF-TOKEN` và preflight thích hợp. Việc đặt token trong header là vấn đề **CSRF**, tách biệt với `allowCredentials`. Một frontend ở `app.example.com` không thể đọc cookie **host-only** của `api.example.com` bằng `document.cookie`; cần một cơ chế bootstrap/token/BFF thiết kế riêng, thay vì giả định `credentials: "include"` tự làm cookie xuất hiện trong `document.cookie` của frontend.

## 6. Preflight: trình duyệt hỏi phép trước request có điều kiện

Khi thực hiện request cross-origin có method hoặc header không thuộc nhóm safelisted (ví dụ POST JSON với `Content-Type: application/json` hoặc header `X-XSRF-TOKEN`), trình duyệt thường gửi `OPTIONS` **preflight**:

```http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
```

Response hợp lệ từ Spring có thể có dạng:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: content-type,x-xsrf-token
Access-Control-Max-Age: 1800
Vary: Origin
```

Các header/định dạng cụ thể có thể khác theo phiên bản và request, miễn đáp ứng chính sách CORS. Preflight thành công chỉ cho phép trình duyệt **thử gửi request thật**; request `POST` có thể tiếp tục bị chặn bởi authentication, CSRF hay validation. Không dùng status của preflight làm bằng chứng POST nghiệp vụ đã thành công.

Theo chuẩn CORS, **preflight thông thường không gửi credentials** như cookie phiên; vì vậy nếu Security filter chain ép `OPTIONS` phải authenticated, preflight có thể bị trả 401/302 trước khi CORS được đánh giá. Một số implementation có hành vi TLS client certificate riêng; đừng phụ thuộc vào chúng để xác thực preflight.

**Không dùng `*` tràn lan với credentialed preflight:** ngoài origin, các wildcard trong `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` hoặc `Access-Control-Expose-Headers` cũng có ngữ nghĩa đặc biệt khi request mang credentials; an toàn, dễ kiểm chứng nhất là liệt kê method/header cần thiết như cấu hình trên.

## 7. Thử thực tế với curl và DevTools

Giả sử backend đang ở `http://localhost:8080`.

**A. Kiểm tra preflight cho origin được cho phép:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-xsrf-token"
```

Trên Windows PowerShell, có thể dùng `curl.exe` để gọi curl thật. Phản hồi hợp lệ cần có `Access-Control-Allow-Origin: http://localhost:5173` và `Access-Control-Allow-Credentials: true`, cùng methods/headers cho preflight.

**B. Kiểm tra origin không có trong allowlist:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"
```

Không được nhận một phản hồi CORS cấp phép `https://untrusted.example`. Spring có thể trả 403 cho preflight bị từ chối. Không dùng `curl` để kết luận trình duyệt cho phép đọc response, vì `curl` không thực thi same-origin policy.

**C. Kiểm tra GET từ frontend JavaScript:**

Trong Chrome/Edge DevTools → **Network**, mở request tới `/api/public`:

1. **Request Headers** phải có `Origin: http://localhost:5173`.
2. **Response Headers** phải có `Access-Control-Allow-Origin: http://localhost:5173` và `Access-Control-Allow-Credentials: true` nếu dùng `credentials: "include"`.
3. Tab **Console** nhận JSON và `X-Request-ID` như đoạn JS. Nếu đổi frontend sang origin không được phép, browser sẽ báo lỗi CORS.
4. Nếu nhìn thấy response từ server trong Network nhưng `fetch` bị từ chối do CORS, điều đó không mâu thuẫn: server có thể đã xử lý request, còn **browser không công bố response cho JS**.
5. Nếu GET authenticated trả 302/401, xác minh đăng nhập/session và quy tắc cookie. Nếu POST trả 403, kiểm tra thêm CSRF. Không gom tất cả thành lỗi CORS.

**D. Thử sai cấu hình trong môi trường dev (không deploy):**

Nếu thay thành `setAllowedOrigins(List.of("*"))` đồng thời giữ `setAllowCredentials(true)`, Spring không chấp nhận cấu hình đó khi xác thực CORS config; thường thấy `IllegalArgumentException` liên quan tới `allowCredentials` và wildcard. Khôi phục allowlist origin cụ thể để sửa.

## 8. Các lỗi cấu hình và cách xác định đúng nguyên nhân

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Console báo không được dùng wildcard với credentials | Response có `Access-Control-Allow-Origin: *`, Fetch dùng `include`. | Dùng allowlist origin cụ thể + `allowCredentials(true)`; hoặc bỏ credentials nếu API thực sự public. |
| Spring báo `IllegalArgumentException` về `allowCredentials` | `allowedOrigins` chứa `*` cùng `allowCredentials=true`. | Đổi thành `allowedOrigins` cụ thể; chỉ dùng `allowedOriginPatterns` khi đã đánh giá đủ phạm vi tin cậy. |
| Có `Access-Control-Allow-Origin` đúng nhưng JS vẫn bị CORS | Thiếu `Access-Control-Allow-Credentials: true` với request `include`; preflight thiếu method/header. | Xem **cả request và response** trong Network, kiểm tra credentials mode và headers. |
| Preflight trả 401/302 | `OPTIONS` bị security filter/đăng nhập xử lý trước CORS. | Kết nối `CorsConfigurationSource` với `http.cors(...)`, xác minh CORS filter chạy trước authentication. |
| CORS đúng nhưng không có cookie | `credentials` của Fetch sai; SameSite/Secure/domain/path/third-party cookie policy chặn. | Kiểm tra Cookies tab, Network → Request Cookies, origin/site và thuộc tính cookie. |
| GET profile trả 401/302 | Không có session hợp lệ. | Xác thực session/login; CORS đúng không cấp quyền đăng nhập. |
| POST trả 403 dù preflight xanh | Thiếu/sai CSRF token hoặc không đủ quyền. | Kiểm tra `CsrfFilter` và `X-XSRF-TOKEN`, không tắt CSRF chỉ để thử CORS. |
| Chạy được ở localhost nhưng fail production | Scheme, host, port không trùng allowlist; HTTPS/cookie policy khác. | Cho phép chính xác production origin và rà domain/path/SameSite/Secure. |
| Response đôi lúc dùng origin sai từ cache | Proxy/CDN không phân biệt `Origin`. | Đảm bảo `Vary: Origin` được tôn trọng và cache không phát tán response riêng tư. |
| Có hai header `Access-Control-Allow-Origin` | Vừa cấu hình Spring CORS vừa tự thêm header qua proxy/filter/controller. | Chọn một chủ thể cấu hình, tránh phát trùng/giá trị trái nhau. |

**Lưu ý bảo mật:**

- **Không phản chiếu mọi `Origin`** mà không kiểm tra allowlist; đặt `allowedOriginPatterns("*")` khi bật credentials cũng tạo hiệu ứng tương tự.
- **Không sử dụng `Access-Control-Allow-Origin: null` làm đường tắt.** Origin `null` có thể phát sinh từ sandbox iframe hoặc `file:`; không mặc nhiên đáng tin.
- CORS không giảm nhu cầu **CSRF token** khi xác thực qua cookie. Origin/Referer checking và SameSite có thể hỗ trợ phòng vệ, nhưng không tự thay thế toàn bộ CSRF protection.
- Chỉ cho phép những frontend thật sự cần đọc response mang credentials; giới hạn methods/headers và exposed headers. Tách cấu hình development và production.
- Kiểm tra **quyền truy cập dữ liệu** ở backend: một request có CORS hợp lệ vẫn phải chịu authentication, authorization và kiểm tra đối tượng (IDOR/BOLA).

## 9. Checklist tự đánh giá

Tự trả lời bốn câu sau trước khi bật `allowCredentials`:

1. Frontend nào cần đọc response mang cookie hoặc HTTP credentials? Có thể liệt kê **chính xác** scheme/host/port không?
2. Frontend đã dùng `credentials: "include"` cho cross-origin chưa, và cookie thực sự có được gửi theo SameSite/Secure/domain/path không?
3. Response trả **một origin cụ thể** cùng `Access-Control-Allow-Credentials: true`, các method/header cần thiết và `Vary: Origin` chưa?
4. Preflight, authentication, authorization và CSRF đã được kiểm tra **riêng biệt** chưa?

**Ghi nhớ:** `allowCredentials(true)` cho phép browser công bố response của một request có credentials **chỉ đối với origin được phép**, nhưng không tự gửi cookie hoặc vượt cơ chế xác thực. Với Spring Security Servlet, **`allowedOrigins("*")` + `allowCredentials(true)` là xung đột**. Dùng allowlist origin cụ thể; nếu dùng `allowedOriginPatterns`, Spring echo origin thật nhưng bạn vẫn phải kiểm soát chặt pattern. Kiểm tra CORS cùng với preflight, chính sách cookie, authentication và CSRF để tránh nhầm lỗi và mở quyền truy cập quá rộng.
