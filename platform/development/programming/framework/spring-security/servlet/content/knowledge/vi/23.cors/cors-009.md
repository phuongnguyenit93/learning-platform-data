# Quan hệ giữa CORS, cookie SameSite, CSRF và HTTPS trong Spring Security Servlet

> **Phạm vi:** Spring Security 6.x trên Servlet stack (Spring MVC/Spring Boot 3.x; Java 17+). Bài học phân biệt bốn cơ chế cùng xuất hiện trong ứng dụng web dùng session cookie: **CORS**, **SameSite**, **CSRF** và **HTTPS**. Chúng giải quyết các câu hỏi bảo mật khác nhau và phải được áp dụng cùng nhau tùy kiến trúc.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài này, bạn có thể giải thích tại sao một frontend `https://app.example.com` gọi API `https://api.example.com` cần cấu hình CORS nhưng vẫn có thể dùng cookie `SameSite=Lax`; vì sao CORS không thay thế CSRF protection; và tại sao HTTPS không tự ngăn trình duyệt gửi yêu cầu giả mạo.

| Cơ chế | Câu hỏi nó trả lời | Nơi thực thi | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **CORS** (Cross-Origin Resource Sharing) | JavaScript từ origin A có được đọc phản hồi của origin B? Với request cần preflight, server có cho phép method/header đó không? | Server công bố chính sách qua HTTP headers; **trình duyệt** kiểm tra và thực thi | CORS không chặn mọi request thay đổi trạng thái; không xác thực người dùng. |
| **Cookie SameSite** | Trình duyệt có đính kèm cookie trong ngữ cảnh same-site/cross-site này không? | Trình duyệt chọn cookie để gửi | SameSite không kiểm tra ý định POST, không bảo vệ khỏi subdomain attacker **cùng site**. |
| **CSRF protection** | Request dùng credential tự động đính kèm có kèm bằng chứng khó giả mạo từ bên ngoài không? | Server, ví dụ `CsrfFilter` trong Spring Security | CSRF token không thay thế authentication/authorization hoặc chống XSS. |
| **HTTPS/TLS** | Kênh truyền có được mã hóa, bảo vệ toàn vẹn và xác thực endpoint TLS không? | Client, server/proxy TLS | HTTPS không chứng minh request đến từ thao tác chủ động của người dùng. |

Không nên kết luận “đã bật một lớp thì không cần ba lớp còn lại”. Ví dụ một POST có cookie phiên qua HTTPS vẫn là mục tiêu CSRF nếu browser bị trang khác điều khiển gửi request và server chỉ kiểm tra cookie.

## 2. Origin khác site như thế nào?

### 2.1 Origin: scheme, host và port

Hai URL được coi là **same-origin** khi có cùng **scheme** (`https`/`http`), **host** và **port** (sau khi quy đổi port mặc định tương ứng).

- `https://app.example.com/home` → `https://app.example.com/api`: **same-origin**, dù path khác.
- `https://app.example.com` → `https://api.example.com`: **cross-origin**, vì host khác.
- `https://app.example.com` → `https://app.example.com:8443`: **cross-origin**, vì port khác.
- `https://app.example.com` → `http://app.example.com`: **cross-origin**, vì scheme khác.

CORS gắn với **origin**. Browser cùng-origin có thể gọi API trong origin đó mà không cần server trả các CORS headers.

### 2.2 Site: scheme và registrable domain

Theo mô hình **schemeful same-site** của trình duyệt hiện đại, “site” được xác định bằng **scheme + registrable domain** (thường là eTLD+1 theo Public Suffix List), không xét port và thường không xét subdomain. Đừng tự tính đơn giản bằng cách lấy hai thành phần cuối của hostname, vì public suffix có thể gồm nhiều cấp.

- `https://app.example.com` và `https://api.example.com`: **cross-origin nhưng same-site**.
- `https://app.example.com` và `https://api.other-example.net`: **cross-origin, cross-site**.
- `https://app.example.com` và `http://api.example.com`: **cross-site** theo schemeful same-site.
- Hai HTTPS URL cùng host nhưng khác port: **cross-origin, same-site**.

| Tình huống frontend → API | CORS? | SameSite? | CSRF khi dùng cookie? |
| --- | --- | --- | --- |
| `https://app.example.com` → `https://app.example.com/api` | Không cần CORS cho same-origin fetch. | Cookie đủ điều kiện same-site. | Vẫn cần cho POST/PUT/PATCH/DELETE. |
| `https://app.example.com` → `https://api.example.com` | Cần nếu JS đọc cross-origin response. | Cùng site; `Lax` có thể vẫn gửi. | Vẫn cần, vì cookie tự đính kèm. |
| `https://app.example.com` → `https://api.other-example.net` | Cần. | Cross-site; `Lax/Strict` thường không gửi cookie trong fetch. | Nếu API dùng cross-site cookie, vẫn cần CSRF và đánh giá chính sách cookie bên thứ ba. |
| `https://app.example.com` → `http://api.example.com` | Khác origin, song mixed content còn là vấn đề. | Schemeful cross-site. | HTTPS/Secure/mixed-content phải được giải quyết trước. |

**Cùng site không đồng nghĩa cookie chung.** Cookie còn có `Domain` hoặc thuộc tính host-only, `Path`, `Secure`, `HttpOnly`, hạn sử dụng. Ví dụ API ở `api.example.com` có thể tự cấp host-only session cookie cho API; cookie đó được gửi tới API khi điều kiện phù hợp, dù frontend ở subdomain khác. Cookie của `app.example.com` không tự động được gửi tới `api.example.com`.

## 3. Trình tự xử lý một request có cookie

Giả sử người dùng đăng nhập vào API bằng session cookie; frontend JavaScript ở một origin khác gọi API.

~~~text
JavaScript tại https://app.example.com
    |
    +-- Browser xác định cross-origin và same-site/cross-site
    |     +-- Xác định cookie phù hợp: Domain/Path/Secure/SameSite
    |     +-- Xét chế độ fetch credentials
    |
    +-- Nếu cần preflight, gửi OPTIONS tới API
    |     +-- CORS trên server kiểm tra Origin, method, headers
    |     +-- OPTIONS thông thường không mang session cookie
    |
    +-- Request thật (GET/POST/...)
          |
          +-- CORS integration trên server
          +-- CsrfFilter: kiểm tra token với unsafe methods
          +-- Authentication + Authorization
          +-- Controller (nếu được phép)
          |
          +-- Response có các CORS headers khi origin được phép
                   |
                   +-- Browser quyết định JS có được đọc response
~~~

Không phải request nào cũng có preflight, và browser có thể chặn ngay từ trước bước request thật (ví dụ mixed content). Nhưng khi request đã tới controller và thay đổi dữ liệu, việc JS bị **chặn đọc response bởi CORS không hoàn tác thay đổi đó**. Đây là lý do không được dùng CORS làm biện pháp chống CSRF duy nhất.

## 4. CORS kiểm soát những gì?

### 4.1 Origin và các HTTP header chính

Client cross-origin có thể gửi `Origin: https://app.example.com`. API được phép trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Với request cần preflight, browser gửi `OPTIONS` trước khi gửi request thật:

~~~http
OPTIONS /api/preferences HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nếu được chấp nhận, phản hồi preflight có thể gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Ví dụ minh họa; status và thứ tự/casing headers có thể khác theo Spring Framework/proxy. `Content-Type: application/json` và custom header `X-CSRF-TOKEN` thường kích hoạt preflight với cross-origin fetch.

### 4.2 Credentialed requests có điều kiện riêng

Muốn JS gửi cookie cho API **khác origin**, client thường phải đặt `credentials: "include"`; mặc định `fetch` là `"same-origin"` nên không gửi cookie tới API khác origin dù chúng cùng site. Với response dùng credential, server phải trả origin **cụ thể**, không được dùng `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`.

CORS cho phép JavaScript sử dụng response nhưng **không thể ép cookie được gửi** nếu `Secure`, `SameSite`, `Domain`, `Path` hay trình duyệt đã loại cookie. Ngược lại, không được cấp `Access-Control-Allow-Credentials: true` cho mọi Origin bằng cách phản chiếu tùy tiện giá trị Origin nhận từ client.

Spring Security cần cho CORS xử lý preflight trước các filter kiểm tra xác thực có thể từ chối `OPTIONS`: preflight thông thường **không kèm cookie session**. Khi có bean `CorsConfigurationSource`, `http.cors(...)` là cách tích hợp đúng trong Servlet filter chain.

### 4.3 Vì sao chặn đọc response không đủ để chặn CSRF?

Một trang attacker có thể tạo HTML form thông thường:

~~~html
<form action="https://api.example.com/account/email" method="post">
  <input type="hidden" name="email" value="attacker@example.net">
  <button type="submit">Gửi</button>
</form>
~~~

Loại form POST này **không cần CORS preflight**. Trình duyệt có thể gửi request và, tùy SameSite/bối cảnh cookie, kèm credential. Attacker có thể **không đọc được** response, nhưng nếu server chỉ kiểm cookie mà không kiểm CSRF/Origin, thay đổi trạng thái có thể đã xảy ra. Đây là ví dụ khái niệm; endpoint chỉ minh họa, không phải hệ thống tồn tại.

CORS đôi khi cản được request chứa custom header hoặc JSON nhờ preflight, nhưng form có thể dùng các dạng content type được trình duyệt cho gửi trực tiếp. Vì vậy không dùng CORS để thay `CsrfFilter`.

## 5. Cookie SameSite: Lax, Strict, None

| Giá trị | Hành vi điển hình | Giới hạn |
| --- | --- | --- |
| `SameSite=Strict` | Chỉ gửi cookie trong ngữ cảnh same-site. | Chuyển từ website bên ngoài vào app có thể mất cookie ở điều hướng đầu; sibling subdomains vẫn có thể same-site. |
| `SameSite=Lax` | Gửi trong ngữ cảnh same-site và một số điều hướng top-level **cross-site với phương thức an toàn**, chủ yếu GET. | Cross-site top-level GET vẫn có thể mang cookie; tuyệt đối không thiết kế GET thay đổi trạng thái. |
| `SameSite=None; Secure` | Cho phép cookie trong ngữ cảnh cross-site khi browser và chính sách cookie cho phép. | `Secure` bắt buộc trong các trình duyệt hiện đại; chặn cookie bên thứ ba vẫn có thể khiến cookie không được gửi. |

**Trường hợp dễ nhầm:** frontend `https://app.example.com` và API `https://api.example.com` **cùng site**; session cookie của host API với `SameSite=Lax` vẫn đủ điều kiện được gửi khi frontend fetch tới API, miễn là cookie đúng host/path, HTTPS và `credentials: "include"`. **Không cần `SameSite=None` chỉ vì hai host là hai subdomain khác nhau.**

Ngược lại, frontend `https://app.example.com` gọi `https://api.other-example.net` là cross-site; `SameSite=Lax/Strict` thường chặn cookie ở fetch cross-site. Nếu phải dựa vào cookie cross-site, cần `SameSite=None; Secure` và phải kiểm tra giới hạn third-party cookies. Không nên đổi SameSite một cách mù quáng để “sửa CORS”.

### Rủi ro từ sibling subdomain

Nếu `https://evil.example.com` bị attacker kiểm soát, nó và `https://api.example.com` **khác origin nhưng cùng site**. SameSite=Lax/Strict **không mặc nhiên ngăn** request từ subdomain đó mang cookie tới API. CORS có thể chặn JS đọc response nhưng không loại bỏ mọi request gây tác động. CSRF token, kiểm soát Origin/Fetch Metadata phù hợp và authorization vẫn có vai trò riêng.

Giữ session cookie **host-only** khi không cần chia sẻ giữa subdomain. Đặt `Domain=.example.com` quá rộng khiến nhiều subdomain cùng nhận cookie, tăng bề mặt tấn công; host-only giảm rủi ro này nhưng cũng không thay thế CSRF.

## 6. CSRF: bằng chứng cho request thay đổi trạng thái

Browser tự đính kèm session cookie hợp lệ với URL; đó là “ambient credential”. Kẻ tấn công có thể tìm cách làm browser gửi POST với cookie có thật của nạn nhân. CSRF token là giá trị khó đoán mà ứng dụng hợp lệ gửi thêm bằng hidden form field hoặc header; server đối chiếu với token tương ứng session/nguồn lưu hợp lệ.

Trong Spring Security Servlet, `CsrfFilter` bảo vệ các phương thức không an toàn theo mặc định: thường POST/PUT/PATCH/DELETE. Các phương thức GET/HEAD/OPTIONS/TRACE không bị yêu cầu token theo matcher mặc định vì được giả định là safe. **Không dùng GET để chuyển tiền, đổi cấu hình, xóa tài nguyên hoặc thực hiện side effect.**

- **CORS không thay CSRF**: chỉ chặn quyền đọc response cũng không ngăn hết form POST.
- **SameSite không thay CSRF**: đặc biệt nguy hiểm với subdomain cùng site bị kiểm soát và các endpoint GET có side effect.
- **HTTPS không thay CSRF**: một request giả mạo vẫn có thể dùng kênh HTTPS được mã hóa hoàn hảo.
- **CSRF không thay authorization**: token đúng nhưng người dùng không được quyền sửa tài nguyên vẫn phải bị từ chối.
- **CSRF không thay chống XSS**: script độc hại trên cùng origin có thể lấy token rồi gửi request hợp lệ.
- **JSON không tự bảo vệ khỏi CSRF**: cơ chế credential và server validation mới quyết định rủi ro, không phải tên “REST API”.

Nếu API chỉ dùng `Authorization: Bearer ...` do JS tự chủ động gắn, hoàn toàn không nhận credential nào browser tự gửi, mô hình CSRF khác với session cookie. Nhưng nếu còn session cookie, HTTP Basic được browser tự gắn, refresh cookie hoặc các luồng credential tự gửi, vẫn phải đánh giá CSRF theo từng endpoint. Đừng tự động tắt CSRF cho toàn bộ ứng dụng chỉ vì nó là SPA.

### Token với SPA và Spring Security 6

Spring Security 6 dùng cơ chế **deferred CSRF token** và mặc định có **XOR masking** cho giá trị token phản chiếu nhằm giảm rủi ro BREACH. SPA có thể gọi endpoint `GET /api/csrf` để lấy token đúng định dạng, rồi gửi header `csrf.headerName` với giá trị `csrf.token` khi POST. Khi frontend cố ý đọc token, supplier được hiện thực hóa; còn những request không cần token có thể không buộc tải/tạo token.

Nếu thay bằng `CookieCsrfTokenRepository` để JavaScript đọc cookie `XSRF-TOKEN` thô, phải bảo đảm server có request handler tương thích cách client gửi token. Token thô từ cookie không phải lúc nào cũng giống biểu diễn XOR mặc định trên request attribute.

## 7. HTTPS, Secure cookie, HSTS và proxy

HTTPS mã hóa và bảo vệ toàn vẹn dữ liệu khi truyền; máy khách kiểm tra danh tính server qua TLS certificate. Nó giúp bảo vệ session cookie và CSRF token khỏi bị đọc/sửa trên đường truyền, nhưng **không ngăn yêu cầu giả mạo** đã được browser tự gửi tới HTTPS API.

Điểm quan trọng trong hệ thống dùng session:

1. Bật HTTPS nhất quán cho frontend, API và các endpoint login/refresh/logout; tránh mixed content (trang HTTPS gọi API HTTP có thể bị browser chặn).
2. Đánh dấu session cookie `Secure` để chỉ gửi qua kết nối được xem là bảo mật; dùng `HttpOnly` để JS không đọc trực tiếp session cookie. `HttpOnly` không ngăn trình duyệt tự gửi cookie.
3. Dùng **HSTS** trên HTTPS endpoint/edge nếu phù hợp để browser ưu tiên HTTPS sau khi ghi nhớ chính sách; cân nhắc kỹ `includeSubDomains`.
4. Với TLS termination tại reverse proxy, chỉ tin các forwarded headers được proxy đáng tin cậy thiết lập; bảo vệ đường proxy → application theo threat model. Không tin vô điều kiện `X-Forwarded-Proto` do client bên ngoài gửi.
5. Nếu ứng dụng dùng cookie CSRF riêng, phải cấu hình thuộc tính cookie đó riêng. Các thuộc tính **session cookie** không chứng minh cookie khác cùng `SameSite/Secure/HttpOnly`.

Scheme thay đổi từ HTTPS sang HTTP cũng có thể thay đổi kết quả schemeful same-site và kích hoạt chặn cookie `Secure`; không “sửa” bằng cách tắt Secure hoặc nới SameSite.

## 8. Cấu hình Spring Security Servlet cho SPA và API cùng site, khác origin

Giả sử:

- Frontend: `https://app.example.com`.
- API: `https://api.example.com`.
- Authentication: session cookie của API.
- Frontend được phép gọi `/api/**` bằng fetch có cookie; các request ghi vẫn cần CSRF token.

### 8.1 SecurityFilterChain và chính sách CORS

Đây là một lớp `WebSecurityConfig.java` trong dự án Spring Boot có dependency `spring-boot-starter-web` và `spring-boot-starter-security`. Đoạn Java yêu cầu Spring runtime/dependencies, **không phải** chương trình Java SE độc lập chạy trực tiếp bằng `javac`.

~~~java
package com.example.demo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Ý nghĩa:

- `.cors(Customizer.withDefaults())` tích hợp CORS vào Spring Security để xử lý preflight trước khi authentication yêu cầu session. `CorsConfigurationSource` giới hạn origin/method/header theo whitelist.
- `setAllowedOrigins` nhận **origin đầy đủ**, ví dụ có `https://` nhưng không có path. Không dùng wildcard hay phản chiếu Origin lạ khi `allowCredentials=true`.
- `setAllowedHeaders` phải khớp các custom headers mà client gửi. Ví dụ dùng header token mặc định `X-CSRF-TOKEN`; nếu hệ thống dùng tên khác thì cập nhật có chủ đích.
- `csrf(Customizer.withDefaults())` giữ bảo vệ CSRF. Đừng gọi `csrf.disable()` chỉ vì SPA giao tiếp qua JSON.
- `formLogin(...)` minh họa một ứng dụng có session authentication. Luồng login của hệ thống thực cần cấu hình để phù hợp SPA, bao gồm redirect, response, session lifecycle và lấy lại CSRF token sau thay đổi xác thực.
- Policy đang gắn `/api/**`; các endpoint ngoài phạm vi này không tự được cấp CORS chỉ vì cùng host. Chỉ mở thêm đường dẫn thật sự cần frontend truy cập.

### 8.2 Session cookie qua HTTPS

Ví dụ `application.properties` dành cho môi trường triển khai HTTPS:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Chúng áp dụng cho Servlet session cookie do Spring Boot quản lý. `SameSite=Lax` là lựa chọn có thể phù hợp cho `app.example.com` và `api.example.com` **cùng site HTTPS**; không cần chuyển `None` chỉ để gọi API khác subdomain. Kiểm tra response `Set-Cookie`, Domain/Path và reverse proxy thực tế.

### 8.3 Cấp CSRF token khi frontend cần

File `CsrfEndpoint.java` trong ứng dụng Spring MVC:

~~~java
package com.example.demo;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CsrfEndpoint {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

Endpoint GET đọc token theo nhu cầu, kích hoạt deferred loading. Spring Security 6 cung cấp biểu diễn phù hợp handler hiện tại, và JSON thường chứa `headerName`, `parameterName`, `token`. Với token gắn với session, không cache chung giữa người dùng; cấu hình `Cache-Control: no-store` phù hợp cho phản hồi token. Sau login/logout hoặc khi session thay đổi, cần lấy lại token mới.

### 8.4 JavaScript gọi API có cookie và CSRF token

Đoạn JavaScript sau chạy tại frontend `https://app.example.com`. Nó giả định API có một endpoint nghiệp vụ POST `/api/preferences` và session authentication đã được thiết lập hợp lệ. Đây là đoạn **tích hợp**, không chạy độc lập nếu thiếu backend/đăng nhập.

~~~javascript
const tokenResponse = await fetch(
  "https://api.example.com/api/csrf",
  { credentials: "include", cache: "no-store" }
);
if (!tokenResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}
const csrf = await tokenResponse.json();

const updateResponse = await fetch(
  "https://api.example.com/api/preferences",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ theme: "dark" })
  }
);
if (!updateResponse.ok) {
  throw new Error("Update failed");
}
~~~

Quy trình: GET token được CORS cho phép → cookie của API được lưu/gửi theo chính sách browser → POST JSON có custom header CSRF thường được preflight → POST thật kèm cookie và CSRF header → `CsrfFilter` kiểm tra trước nghiệp vụ → các bước authentication/authorization và controller xử lý nếu hợp lệ.

Browser cần `credentials: "include"` cho API cross-origin **ngay cả khi cùng site**. Header token không phải session credential; không ghi token vào URL hoặc log. Nếu server trả redirect tới trang đăng nhập khác origin hoặc response lỗi thiếu CORS headers, browser có thể hiển thị CORS error: cần kiểm tra redirect và authentication, không chỉ sửa CORS whitelist.

## 9. Kiểm chứng cơ chế bằng các tình huống thực tế

### 9.1 Kiểm tra preflight (chỉ kiểm tra phía server)

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/preferences" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Một cấu hình hợp lệ dự kiến có origin cụ thể `https://app.example.com`, phương thức `POST`, các header phù hợp và `Access-Control-Allow-Credentials: true`. Thay Origin thành `https://untrusted.example.net` để xác nhận server không cấp quyền CORS tùy tiện. Tùy cấu hình, origin không hợp lệ có thể dẫn tới 403 hoặc không có headers cho phép.

**curl không thực thi SameSite, CORS hay mixed-content policy như browser.** Dùng DevTools của trình duyệt với frontend thật để xác nhận request có gửi cookie không, preflight có thành công không, POST có đến server không và JS có được đọc response không.

### 9.2 Các case cần thử trong browser / kiểm thử tích hợp

| Case | Điều cần quan sát |
| --- | --- |
| Frontend cùng origin gọi POST bằng session | Không cần CORS; CSRF vẫn chặn POST thiếu token. |
| Frontend `app.example.com` gọi `api.example.com` | CORS trả đúng origin; `credentials: include`; cookie API hợp lệ có thể gửi với SameSite=Lax; POST hợp lệ kèm token. |
| Bỏ `credentials: "include"` ở cross-origin fetch | Không gửi cookie phiên như dự kiến dù CORS cho phép; thường bị coi là chưa đăng nhập. |
| Gửi POST thiếu/sai token nhưng cookie đúng | `CsrfFilter` chặn, thường trả HTTP 403; không thực hiện thay đổi trạng thái. |
| POST với token đúng nhưng user thiếu quyền | Vẫn phải bị authorization từ chối; CSRF thành công không cho thêm quyền. |
| Cross-site form POST từ origin lạ | Không phụ thuộc CORS để ngăn gửi; SameSite có thể loại cookie, còn CSRF phải bảo vệ nếu credential tới server. |
| Subdomain same-site bị attacker kiểm soát | SameSite không đủ phân biệt subdomain; CORS ngăn đọc khi origin không cho phép, CSRF/authorization bảo vệ tác vụ. |
| Trang HTTPS gọi API HTTP | Browser có thể chặn mixed content, cookie Secure không gửi; sửa HTTPS, không tắt Secure. |
| Session đổi sau login/logout | Token cũ có thể không hợp lệ; frontend phải nạp lại token. |

Quan sát trong DevTools: `Origin`, request URL/method, `Access-Control-Request-*`, `Access-Control-Allow-*`, `Cookie`/`Set-Cookie` (và lý do cookie bị chặn), status, redirects, `Content-Type` và header CSRF. Phân biệt lỗi preflight với lỗi 401/403 do auth/CSRF.

### 9.3 Phân biệt bốn lớp khi sự cố

- **Preflight bị từ chối:** xem allowlist Origin/method/headers và việc CORS có chạy trước auth; không mở `*` kèm credentials.
- **Response bị CORS chặn dù server trả 200/401/403:** kiểm tra response/error/redirect chain có CORS headers đúng; bản thân server có thể đã xử lý request.
- **Cookie không gửi:** xem fetch credentials, Domain/Path, Secure, SameSite, third-party cookie restriction và scheme HTTPS. SameSite là site-based, không phải origin-based.
- **POST có cookie nhưng bị 403:** xem CSRF token, định dạng raw/masked, session/token mới sau login, rồi kiểm tra authorization. Không tắt CSRF để né lỗi.
- **Mixed content / TLS / proxy:** sửa đường truyền và cấu hình proxy đáng tin cậy; không vô hiệu HTTPS/Secure/HSTS để làm request chạy tạm.

## 10. Những nhầm lẫn phải tránh

**“CORS = chống CSRF.”** Sai: CORS chặn quyền đọc response hoặc một số luồng preflight; form POST đơn giản không cần preflight. CSRF token kiểm tra yêu cầu thực sự có quyền thực hiện thao tác gắn với session.

**“SameSite=Lax là đủ cho tất cả CSRF.”** Sai: cùng-site attacker (ví dụ sibling subdomain) có thể gây request mang cookie; và top-level cross-site GET vẫn có thể mang cookie Lax. Các endpoint GET phải an toàn theo HTTP semantics.

**“Bật HTTPS là hết CSRF.”** Sai: request giả mạo vẫn có thể gửi qua HTTPS. HTTPS bảo vệ bí mật trong transit, không xác minh ý định người dùng.

**“Khác origin nghĩa là khác site.”** Sai: `app.example.com` và `api.example.com` cùng scheme HTTPS là cross-origin nhưng same-site; đừng vội dùng SameSite=None.

**“SameSite=None làm CORS thành công.”** Sai: cookie policy và CORS độc lập. `None; Secure` còn có thể bị trình duyệt chặn third-party cookies, và không tự cấp quyền CORS.

**“Dùng JSON/SPA có thể tắt CSRF.”** Sai nếu API vẫn sử dụng cookie credential tự động gửi. Phải dựa vào mô hình credential thật.

**“CORS error luôn có nghĩa whitelist sai.”** Không đủ: lỗi redirect/login, preflight bị auth chặn, cookie bị loại, HTTPS/proxy hoặc response lỗi thiếu CORS headers đều có thể khiến browser báo CORS error.

**“CORS bảo vệ API khỏi curl/Postman.”** Sai: công cụ không phải browser không tự thi hành CORS, SameSite như trình duyệt. API luôn phải tự kiểm tra xác thực và quyền truy cập.

## 11. Chọn phương án theo kiến trúc

- **Server-rendered web cùng origin:** HTTPS + session cookie Secure/HttpOnly + SameSite phù hợp + Spring Security CSRF. Không cần bật CORS rộng khi frontend không cross-origin.
- **SPA khác origin nhưng cùng site:** giới hạn CORS theo origin tin cậy, frontend dùng `credentials: "include"`, cookie API đúng host/path và SameSite phù hợp (thường Lax), CSRF token cho unsafe methods và HTTPS cho cả hai host.
- **SPA khác site:** CORS vẫn cần cho JS đọc API; cookie cross-site gặp yêu cầu SameSite=None; Secure và chính sách third-party cookies. Đánh giá chuyển về same-site/cùng origin qua proxy/backend-for-frontend nếu kiến trúc phụ thuộc session cookie.
- **API chỉ có Bearer token do client chủ động gửi:** CORS vẫn là chính sách quyền đọc cross-origin; HTTPS vẫn bảo vệ token. Đánh giá nhu cầu CSRF dựa trên việc còn credential nào browser tự đính kèm hay không; authorization là bắt buộc.

**Ghi nhớ:** **CORS kiểm soát truy cập cross-origin của JavaScript; SameSite kiểm soát gửi cookie theo site; CSRF kiểm tra request thay đổi trạng thái khi có credential tự động; HTTPS bảo vệ đường truyền.** Thiết kế an toàn đòi hỏi xét cả origin, site, cookie scope, phương thức HTTP, token CSRF, xác thực/ủy quyền và TLS.