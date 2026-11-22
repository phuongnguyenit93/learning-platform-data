# Allowed origins, methods, headers và exposed headers trong CORS

> **Chủ đề:** Spring Security – fundamentals → **CORS** (Cross-Origin Resource Sharing). Bài học dùng Java 17+, Spring Boot 3.x, Spring Framework 6.x và Spring Security 6.x để giải thích **bốn trục cấu hình quan trọng**: allowed origins, allowed methods, allowed headers, exposed headers. Đồng thời trình bày preflight, request có cookie/credentials, cấu hình đúng cho Servlet MVC và WebFlux, cách kiểm thử cũng như ranh giới giữa CORS, CSRF, authentication và authorization.

## 1. CORS giải quyết vấn đề gì?

**Origin** là bộ ba `scheme + host + port`, ví dụ:

- Frontend `https://app.example.com`.
- API `https://api.example.com`.
- Admin frontend `https://console.example.com`.

Ba địa chỉ có thể **cùng site** nhưng **khác origin** vì host khác nhau. Tương tự, `http://localhost:3000` và `http://localhost:8080` khác origin do port khác; `http://app.example.com` và `https://app.example.com` khác origin do scheme khác.

**Same-Origin Policy (SOP)** hạn chế JavaScript của một trang truy cập dữ liệu từ origin khác. **CORS** là cơ chế dựa trên các HTTP headers để **server đích cho phép trình duyệt chia sẻ response với một origin gọi cụ thể**, và với một số request còn kiểm tra qua **preflight** trước khi gửi request thực.

Không nên hiểu CORS là “firewall xác thực API”:

- CORS là cơ chế được **trình duyệt** thực thi; `curl` hoặc một backend khác không nhất thiết áp SOP/CORS.
- Server vẫn phải kiểm tra authentication, role/scope, quyền trên tài nguyên và CSRF khi có browser credentials tự động gửi.
- CORS không cấp thêm quyền database, không làm JWT/secret hợp lệ, không đảm bảo request đến từ ứng dụng frontend thật. `Origin` là tín hiệu do browser đặt, nhưng HTTP client bất kỳ có thể tự tạo header này.
- Một request cross-origin bị browser chặn **đọc response** vẫn có thể đã tới server và gây tác dụng phụ, nhất là với HTML form/simple request. Vì vậy CORS **không thay thế chống CSRF**.

### 1.1. Bốn trục cấu hình

Một policy thường trả lời:

| Câu hỏi | Spring `CorsConfiguration` | Response header chính |
|---|---|---|
| **Origin nào** được đọc response qua browser? | `allowedOrigins` hoặc `allowedOriginPatterns` | `Access-Control-Allow-Origin` |
| **HTTP methods nào** được phép trong preflight? | `allowedMethods` | `Access-Control-Allow-Methods` |
| **Request headers nào** browser được gửi khi preflight? | `allowedHeaders` | `Access-Control-Allow-Headers` |
| **Response headers nào** JS được phép đọc ngoài danh sách safelisted? | `exposedHeaders` | `Access-Control-Expose-Headers` |

Hai thuộc tính thường dùng kèm:

- `allowCredentials` → `Access-Control-Allow-Credentials: true`: cho browser sử dụng credentialed CORS response khi các điều kiện khác thỏa.
- `maxAge` → `Access-Control-Max-Age`: thời gian browser có thể cache kết quả preflight trong giới hạn browser.

**Phân biệt quan trọng nhất:** `allowedHeaders` áp cho **headers của request mà frontend muốn gửi**; `exposedHeaders` áp cho **headers của response mà JavaScript muốn đọc**. Đây là hai chiều hoàn toàn khác nhau.

## 2. Allowed origins: chính xác origin nào được quyền đọc response?

Khi JavaScript chạy ở `https://app.example.com` gọi API ở `https://api.example.com`, browser có thể gửi:

```http
GET /api/items HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
```

Nếu policy cho phép origin này, API trả về:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

[{"id":1,"name":"Notebook"}]
```

Browser dùng `Access-Control-Allow-Origin` để quyết định JavaScript ở origin gửi request có được truy cập response hay không. **Server không nên tự tin rằng người dùng đã có quyền truy cập dữ liệu chỉ vì origin hợp lệ.** Với API cần xác thực, response còn phải đi qua chính sách authentication/authorization.

### 2.1. Origin phải xét scheme, host và port

| Origin gửi request | Policy chỉ cho `https://app.example.com` | Kết quả |
|---|---|---|
| `https://app.example.com` | Khớp hoàn toàn | Cho phép CORS |
| `http://app.example.com` | Sai scheme | Không khớp |
| `https://app.example.com:8443` | Sai port | Không khớp |
| `https://console.example.com` | Sai host | Không khớp trừ khi thêm riêng |
| `https://app.example.com.attacker.net` | Tên giả trông giống | Không khớp |
| `null` | Special Origin value | Không tự cho phép |

Một phép kiểm tra `origin.contains("example.com")` hoặc `origin.endsWith("example.com")` tự viết có thể dễ sai vì domain gần giống, suffix hoặc scheme/port. Hãy dùng CORS framework với **allowlist chính xác** các origin được tin cậy, hoặc một cơ chế pattern được review rõ ràng.

### 2.2. `allowedOrigins` và wildcard `*`

`Access-Control-Allow-Origin: *` cho phép đọc response từ bất kỳ origin khi request **không dùng credentials**. Nó không phải giá trị phù hợp cho API phản hồi riêng tư có cookie hoặc browser authentication được gửi kèm.

**Khi `allowCredentials(true)`, không cấu hình `allowedOrigins(List.of("*"))`.** Browser không chấp nhận combination `Access-Control-Allow-Origin: *` cùng credentialed response; Spring Framework cũng kiểm tra và không cho phép combination wildcard origin này với `allowCredentials=true`. Dùng origin cụ thể.

Không có cấu hình nào đảm bảo an toàn tuyệt đối chỉ vì sử dụng exact origins: nếu frontend origin bị XSS/chiếm quyền hoặc người dùng bị attacker dụ làm việc trong ứng dụng hợp lệ, CORS không ngăn tác động từ nguồn đã được tin.

### 2.3. `allowedOriginPatterns` có thể hữu ích nhưng dễ mở quá rộng

Spring Framework có `allowedOriginPatterns` để match một tập origin có cấu trúc, ví dụ nhiều subdomain. Khi pattern khớp, framework có thể trả về **origin cụ thể đã khớp** thay vì `*`, giúp hoạt động với `allowCredentials=true`.

Tuy nhiên, policy như `https://*.example.com` có thể cho cả subdomain chưa kiểm soát, subdomain bị takeover hoặc môi trường test không đáng tin đọc user-specific response. Nếu chỉ có hai frontend xác định, **dùng hai exact origins** vẫn dễ audit và an toàn hơn.

Không dùng giá trị `null` như một wildcard tiện lợi: sandboxed documents, `file:` và một số origin mờ đục có thể phát `Origin: null`.

## 3. Allowed methods: phương thức nào được vượt preflight?

`allowedMethods` kiểm soát HTTP methods mà browser được phép dùng trong **CORS preflight** ở phạm vi resource đã cấu hình. Ví dụ policy có:

```text
GET
POST
PATCH
DELETE
OPTIONS
```

Khi frontend muốn gọi PATCH với JSON, browser gửi preflight `OPTIONS` có:

```http
OPTIONS /api/items/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id
```

Server có thể đáp:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Request-ID
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Browser đối chiếu request method `PATCH` với `Access-Control-Allow-Methods` trước khi gửi actual request. **Header này không tự tạo một endpoint PATCH** và **không thay thế Spring Security authorization**: nếu controller không có `@PatchMapping`, handler có thể trả 405/404; nếu user thiếu quyền, server vẫn có thể trả 403.

### 3.1. CORS-safelisted methods và preflight

Các method `GET`, `HEAD`, `POST` nằm trong tập **CORS-safelisted methods**, nhưng **không phải mọi GET/POST đều tránh preflight**. Một POST với `Content-Type: application/json` hoặc custom header như `X-CSRF-TOKEN` có thể cần preflight vì header/content type không thuộc giới hạn của simple request.

`PATCH`, `PUT` và `DELETE` thường cần preflight cho browser cross-origin. `OPTIONS` là method dùng cho preflight, không phải lời hứa rằng application handler phải xử lý mọi OPTION request theo logic nghiệp vụ.

### 3.2. Sai lầm: cho phép toàn bộ method trong CORS và nghĩ đã bảo vệ bằng method security

Ví dụ `allowedMethods("*")` có thể nới phạm vi preflight. Với request credentialed, Spring có cách xử lý wildcard bằng cách phản ánh method được yêu cầu trong phản hồi; nhưng đó vẫn là chính sách CORS quá rộng. Dùng allowlist `GET`, `POST`, `PATCH`… theo API thật. Dù CORS cho phép PATCH, người dùng vẫn phải có quyền `item:write`/role phù hợp và vượt CSRF guard nếu dùng cookie authentication.

## 4. Allowed headers: frontend được gửi request headers nào?

`allowedHeaders` quy định request header names mà browser được phép dùng trong một preflighted cross-origin request. Ví dụ frontend gửi:

```http
PATCH /api/items/42 HTTP/1.1
Origin: https://app.example.com
Content-Type: application/json
X-Request-ID: req-42
X-CSRF-TOKEN: csrf-from-server
Cookie: JSESSIONID=opaque
```

Trong cấu hình CORS, cần cho phép những header **client được quyền tự đặt**, ví dụ `Content-Type`, `X-Request-ID`, `X-CSRF-TOKEN`, và nếu frontend dùng bearer token thì `Authorization`. Cookie **không** được JavaScript tự đặt bằng `fetch` request header; cookie do browser kiểm soát qua cookie policy và `credentials`, nên **không thêm `Cookie` vào `allowedHeaders` để “bật cookie”**.

Một preflight có:

```http
Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token
```

thì response cần chấp nhận phù hợp:

```http
Access-Control-Allow-Headers: Content-Type, X-Request-ID, X-CSRF-TOKEN
```

Header names so khớp **không phân biệt chữ hoa/chữ thường** theo quy tắc HTTP; thứ tự cũng không phải hợp đồng bất biến. Browser có thể chuyển header names trong preflight thành chữ thường.

### 4.1. Safelisted request headers

Một số request headers cơ bản nằm trong **CORS-safelisted request headers** với các điều kiện cụ thể: `Accept`, `Accept-Language`, `Content-Language`, `Content-Type` ở các MIME types/giá trị cho phép, và một số header như `Range` với ràng buộc. Không phải mọi giá trị/định dạng header cùng tên đều là safelisted.

Với `Content-Type`, các loại thường được chấp nhận cho simple request là:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

`application/json` **không thuộc ba loại safelisted đó**, nên một cross-origin POST JSON thường cần preflight. `Authorization` và custom header như `X-Trace-ID` cũng thường kích hoạt preflight.

### 4.2. Đừng đưa response header vào allowed headers để làm JS đọc được nó

Nếu controller trả:

```http
HTTP/1.1 200 OK
X-Request-ID: req-42
X-Total-Count: 125
```

việc thêm `X-Total-Count` vào `allowedHeaders` **không** giúp browser JavaScript đọc response header này. Phải khai báo `exposedHeaders`; hai chiều khác nhau.

### 4.3. Wildcard `*` trong allowed headers

`allowedHeaders("*")` rộng hơn cần thiết, khiến preflight của nhiều request custom headers được chấp nhận. Với credentials, Spring Framework có xử lý wildcard bằng cách phản ánh headers yêu cầu từ preflight, nhưng nên chọn **finite allowlist** cho các header ứng dụng thật dùng.

Không coi `allowedHeaders` là lớp kiểm soát dữ liệu tin cậy: một client không phải browser vẫn có thể gửi bất kỳ header nào; backend phải validate giá trị, authentication, business constraints và không tin `X-User-ID`/`X-Tenant-ID` do client tự thêm.

## 5. Exposed headers: frontend JavaScript được đọc response headers nào?

Browser không cho JavaScript đọc tất cả response headers của cross-origin fetch chỉ vì CORS cho phép response body. Một số response headers là **CORS-safelisted response headers** và được phép truy cập mặc định:

```text
Cache-Control
Content-Language
Content-Length
Content-Type
Expires
Last-Modified
Pragma
```

Nếu frontend cần đọc những response headers khác như `X-Request-ID`, `X-Total-Count`, `ETag` hoặc `Content-Disposition`, server nên liệt kê chúng trong:

```http
Access-Control-Expose-Headers: X-Request-ID, X-Total-Count
```

Ví dụ fetch trong frontend:

```javascript
const response = await fetch("https://api.example.com/api/items", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

console.log(response.headers.get("Content-Type"));   // safelisted
console.log(response.headers.get("X-Request-ID"));   // cần exposed
console.log(response.headers.get("X-Total-Count"));  // cần exposed
```

Code chỉ minh họa cách đọc, không khẳng định response nào đó đã có header. `credentials: "include"` không tự đảm bảo cookie được gửi; còn phụ thuộc cookie scope, SameSite, Secure, browser policy và CORS.

### 5.1. `exposedHeaders` KHÔNG quyết định frontend gửi header

Ngược lại với `allowedHeaders`:

- `allowedHeaders("X-Request-ID")`: browser **được gửi** `X-Request-ID` trong request sau preflight.
- `exposedHeaders("X-Request-ID")`: JavaScript **được đọc** `X-Request-ID` trong response CORS.
- Nếu API vừa nhận request-id của client vừa trả request-id của server, có thể cần **cả hai**.
- Nếu response có header `X-Total-Count` nhưng frontend không gửi header đó, chỉ cần cấu hình `exposedHeaders` cho nó, không nhất thiết thêm vào allowed headers.

### 5.2. `Set-Cookie` là trường hợp đặc biệt

`Set-Cookie` là **forbidden response header name** đối với Fetch API. JavaScript không thể đọc giá trị `Set-Cookie` từ `response.headers.get("Set-Cookie")`, **kể cả** nếu thêm `Set-Cookie` vào `Access-Control-Expose-Headers`. Browser quản lý cookie riêng. Không dùng exposedHeaders để tìm cách lấy session ID.

### 5.3. Wildcard `Access-Control-Expose-Headers: *` với credentials

Theo mô hình CORS chuẩn, wildcard `*` cho exposed headers có ý nghĩa đặc biệt cho request **không có credentials**. Với credentialed requests, `*` không được coi là wildcard phổ quát. Tài liệu Spring Framework lưu ý một số browser hỗ trợ hành vi rộng hơn khi Spring phát wildcard dù allowCredentials bật, nhưng **không nên dựa vào ngoại lệ triển khai và khả năng tương thích**.

**Khuyến nghị:** khai báo chính xác `exposedHeaders(List.of("X-Request-ID","X-Total-Count"))`. Không dùng `"*"` để khỏi phải quản lý các response headers nhạy cảm.

## 6. Ma trận bốn trục — xem nhanh không nhầm hướng

| Dòng hoạt động | Header browser/client | Header response server | Cấu hình Spring |
|---|---|---|---|
| Frontend muốn gọi API | `Origin` | `Access-Control-Allow-Origin` | `allowedOrigins` |
| Frontend muốn gọi PATCH | `Access-Control-Request-Method: PATCH` trong preflight | `Access-Control-Allow-Methods` | `allowedMethods` |
| Frontend muốn gửi `X-CSRF-TOKEN` | `Access-Control-Request-Headers` trong preflight | `Access-Control-Allow-Headers` | `allowedHeaders` |
| Frontend muốn đọc `X-Total-Count` | JavaScript gọi `response.headers.get(...)` | `Access-Control-Expose-Headers` | `exposedHeaders` |
| Frontend dùng cookie/auth credentials | `credentials: "include"` + browser cookie policy | `Access-Control-Allow-Credentials: true` và origin cụ thể | `allowCredentials(true)` |
| Browser cache preflight | Browser tự quản lý cache | `Access-Control-Max-Age` | `maxAge` |

Ví dụ policy nghiệp vụ:

```text
Origins:
  https://app.example.com
  https://console.example.com

Methods:
  GET, POST, PATCH, DELETE, OPTIONS

Request headers:
  Authorization, Content-Type, X-CSRF-TOKEN, X-Request-ID

Exposed response headers:
  X-Request-ID, X-Total-Count

Credentials: true
Preflight max age: 1800 seconds
Scope: /api/**
```

Chú ý `allowCredentials(true)` chỉ nên bật khi frontend thật sự cần browser credentials. Nếu API là bearer-only cho một SPA chủ động gắn Authorization header, cần phân tích xem có cần credential mode và các cookie nào hiện diện. `Authorization` là một request header thường cần `allowedHeaders` trong preflight, nhưng không phải cứ có `Authorization` là phải bật credentialed CORS trong mọi tình huống.

## 7. Preflight và actual request: đầy đủ hai giai đoạn

### 7.1. Frontend muốn PATCH JSON

JavaScript tại `https://app.example.com` gọi API `https://api.example.com`:

```javascript
// csrfToken do ứng dụng cấp từ nguồn tin cậy, gắn với phiên hiện tại.
const response = await fetch("https://api.example.com/api/items/42", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "req-42",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ label: "Updated" })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
console.log(response.headers.get("X-Request-ID"));
```

Giả định browser cho phép cookie cho `api.example.com`, endpoint xác thực bằng session và Spring Security có CSRF protection. Token trong code phải lấy từ luồng bootstrap/form đáng tin; không hardcode hay lấy từ attacker origin.

### 7.2. Browser gửi preflight `OPTIONS`

```http
OPTIONS /api/items/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token
```

**Preflight thường không mang cookie phiên.** Nếu tầng authentication/authorization chạy trước CORS và yêu cầu user đã đăng nhập cho `OPTIONS`, server có thể trả 401/403 trước khi CORS được xử lý, khiến browser không gửi actual request. Spring Security khuyến nghị **xử lý CORS trước** các filter bảo mật cần credential.

### 7.3. Server trả policy cho preflight

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Request-ID, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Status có thể là `200` hoặc `204` tùy implementation; browser quan tâm chính sách CORS và tính hợp lệ của response. **Không cần cookie/session trong preflight**. Access-Control-Max-Age chỉ là cache preflight với browser-specific limit; không kéo dài session hay CSRF token.

### 7.4. Browser gửi actual request

Nếu preflight thành công, browser mới gửi actual request với method/body/header do frontend yêu cầu. Response có thể là:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID, X-Total-Count
Content-Type: application/json
X-Request-ID: req-42
X-Total-Count: 1

{"id":42,"label":"Updated"}
```

Nếu user không đủ quyền hoặc CSRF token sai, server vẫn có thể từ chối actual request. **Preflight 200 không có nghĩa actual request sẽ 200**. Nếu actual response bị chặn về CORS, browser có thể báo lỗi mạng/CORS ở JavaScript ngay cả khi server xử lý request và trả một HTTP status thật; DevTools network giúp phân biệt.

## 8. Credentials: cookie, HTTP authentication và wildcard

Với `fetch(..., {credentials: "include"})`, trình duyệt có thể gửi cookie/HTTP authentication cho cross-origin API theo cookie policy và authentication state. Để JavaScript nhận credentialed CORS response, server thường cần:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

**Sai:**

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browser không chấp nhận credentialed CORS response có wildcard origin. Spring cũng không cho dùng `allowedOrigins("*")` cùng `allowCredentials(true)`. Chọn exact origin/allowlist.

**Cũng phải phân biệt origin và site**: `https://app.example.com` và `https://api.example.com` khác origin (cần CORS cho browser fetch) nhưng thường same-site theo SameSite cookie. Không tự dùng `SameSite=None` chỉ vì hai subdomain khác origin. Nếu frontend và API thực sự ở hai registrable domains khác nhau, third-party cookie blocking có thể khiến session cookie không đi qua dù cấu hình `SameSite=None; Secure`.

### 8.1. CORS không thay thế CSRF

Browser có thể gửi request cross-origin đơn giản dù frontend không được đọc response. Nếu cookie/session tự gắn với request, backend vẫn cần CSRF token hoặc cơ chế đã review. Khi Spring Security default CSRF bật, POST/PATCH/DELETE thường cần token đúng; CORS allowlist không chứng minh người dùng chủ động thực hiện action.

### 8.2. CORS không thay thế xác thực hoặc phân quyền

`curl` hoặc service khác không phải browser có thể gửi Origin giả và header tùy ý. API phải kiểm tra JWT/session/password, role, scope, owner, tenant và action. Không sử dụng giá trị `Origin` làm bằng chứng đăng nhập hoặc làm tenant ID.

### 8.3. Cookie không phải một allowed request header do frontend tùy ý đặt

Trong browser `fetch`, `Cookie` là forbidden request header và được browser quản lý. Cấu hình `allowedHeaders("Cookie")` không có tác dụng “bật cookie” cho JS; phải xét `credentials`, server `allowCredentials`, cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` và các quy tắc browser.

## 9. Spring Boot MVC/Security: cấu hình policy cụ thể

Ví dụ một Spring Boot MVC app, Java 17+, dùng **Spring Framework `CorsConfiguration`**, `UrlBasedCorsConfigurationSource`, kết hợp Spring Security 6.x. Class `CorsSecurityConfig.java`:

```java
package com.example.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Allowed origins: exact frontend origins.
        config.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://console.example.com"
        ));

        // Allowed methods for CORS preflight.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH", "DELETE", "OPTIONS"
        ));

        // Request headers the browser is allowed to send.
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-CSRF-TOKEN",
            "X-Request-ID"
        ));

        // Non-safelisted response headers visible to JavaScript.
        config.setExposedHeaders(List.of(
            "X-Request-ID", "X-Total-Count"
        ));

        // Only enable when browser credentials are necessary.
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // CORS integration is placed before authentication.
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .authenticated()
                .requestMatchers(HttpMethod.PATCH, "/api/items/**")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích từng dòng chính:**

- `setAllowedOrigins` liệt kê đúng hai frontend. Browser từ `https://evil.example.net` không nhận quyền đọc response CORS.
- `setAllowedMethods` cho phép GET/POST/PATCH/DELETE/OPTIONS ở tầng CORS; **không** bảo đảm controller/API đã cung cấp từng method hay cho user permission.
- `setAllowedHeaders` cho phép những request header mà frontend cần. Không thêm `Cookie` chỉ để hỗ trợ credentials.
- `setExposedHeaders` cho JavaScript đọc các response header `X-Request-ID` và `X-Total-Count`; không cần cho tất cả headers.
- `setAllowCredentials(true)` khiến policy phù hợp với frontend dùng cookie/session đã được browser chấp nhận; tăng mức độ tin cậy của các origins được allow.
- `setMaxAge(1800L)` giới hạn cache preflight theo giây ở cấp policy; browser có thể giới hạn thấp hơn.
- `registerCorsConfiguration("/api/**", ...)` giới hạn policy cho API; không tự mở mọi path. Cấu hình mapping cụ thể cần khớp đường dẫn thật và filter chain bao phủ request.
- `.cors(Customizer.withDefaults())` tích hợp CORS với Spring Security để preflight xử lý đúng thứ tự. Với `UrlBasedCorsConfigurationSource` bean trên, Spring Security có nguồn policy rõ ràng.
- `formLogin` mô tả một mô hình session/cookie. `.csrf(Customizer.withDefaults())` giữ lớp CSRF; một request PATCH thật cần CSRF token hợp lệ và role EDITOR.
- `anyRequest().denyAll()` ngăn endpoint/method chưa được bảo vệ bằng rule rõ ràng tự mở; không nhầm CORS preflight với actual authorization.

**Bảo mật bổ sung:** Với server-rendered form login, hãy có user store đáng tin, password hashing, cookie `Secure`/`HttpOnly`/`SameSite`, HTTPS và session management. Code trên **chỉ tập trung cấu hình CORS/security policy**; nó chưa cung cấp user store/controller, không phải ứng dụng Spring Boot độc lập.

### 9.1. Vì sao cần CORS trước Spring Security?

Preflight không mang cookie phiên theo luồng thông thường. Nếu authentication filter buộc OPTIONS phải xác thực trước khi xử lý CORS, browser có thể thấy 401/403 và không gửi PATCH/POST thật.

Spring Security tích hợp CORS với Spring MVC hoặc `CorsConfigurationSource`/`CorsFilter`. Với nhiều security chains, nhiều `CorsConfigurationSource` hoặc custom filters, cần xác minh chain nào có policy và thứ tự filters. Đừng tự thêm nhiều `CorsFilter` khác nhau khiến response lặp headers; prefer một nguồn cấu hình được quản lý rõ ràng.

### 9.2. Policy không nên nới rộng theo phản hồi lỗi frontend

Không đổi từ `allowedOrigins(List.of("https://app.example.com"))` thành `allowedOrigins("*")` trong production chỉ vì frontend gặp CORS error. Hãy xem Origin của request thực, preflight method/headers, credentials, proxy, security chain và route mapping, rồi bổ sung đúng origin/header/method có nhu cầu.

## 10. Demo Spring Boot MVC + MockMvc tích hợp CORS

Dưới đây là ví dụ project nhỏ để kiểm tra bốn trục **allowed origins/methods/headers/exposed headers** bằng test. Dùng **JDK 17+**, Maven, Spring Boot **3.5.7**, Spring Security 6.x do Spring Boot quản lý. Các domain `example.com` chỉ là địa chỉ minh họa, không cần hoạt động thật khi test với MockMvc. Không dùng credentials demo ở production.

Cấu trúc:

```text
cors-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cors/
    │   ├── CorsApplication.java
    │   ├── CorsSecurityConfig.java
    │   └── ItemController.java
    └── test/java/com/example/cors/
        └── CorsSecurityTests.java
```

### 10.1. `pom.xml`

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
    <artifactId>cors-demo</artifactId>
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

### 10.2. `CorsApplication.java`

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

### 10.3. `ItemController.java`

```java
package com.example.cors;

import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping
    public ResponseEntity<List<Map<String, Object>>> list() {
        return ResponseEntity.ok()
            .header("X-Request-ID", "req-demo")
            .header("X-Total-Count", "1")
            .body(List.of(Map.of("id", 42, "label", "Notebook")));
    }

    @PatchMapping("/{id}")
    public ResponseEntity<Map<String, Object>> patch(
            @PathVariable long id,
            @RequestBody Map<String, String> body) {
        String label = body.getOrDefault("label", "Unchanged");

        // Demo: only returns a response; does not persist changes.
        return ResponseEntity.ok()
            .header("X-Request-ID", "req-patch")
            .body(Map.of("id", id, "label", label));
    }
}
```

`GET /api/items` trả hai response headers `X-Request-ID` và `X-Total-Count` để test exposed headers. `PATCH /api/items/{id}` minh họa request JSON/CSRF, **không cập nhật database thật**. CORS policy không tạo authentication/authorization; controller chỉ chạy sau khi Spring Security đã cho phép.

### 10.4. `CorsSecurityTests.java`

```java
package com.example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedOriginMethodAndHeadersPassPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-request-id,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void unknownOriginFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://evil.example.net")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH"))
            .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenMethodFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRequestHeaderFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-admin-override"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualGetHasCorsAndExposedHeaders() throws Exception {
        mvc.perform(get("/api/items")
                .with(user("alice"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Request-ID, X-Total-Count"))
            .andExpect(header().string("X-Request-ID", "req-demo"))
            .andExpect(header().string("X-Total-Count", "1"));
    }

    @Test
    void patchWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(patch("/api/items/42")
                .with(user("alice").roles("EDITOR"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType("application/json")
                .content("{\"label\":\"Updated\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void patchWithEditorAndCsrfSucceeds() throws Exception {
        mvc.perform(patch("/api/items/42")
                .with(user("alice").roles("EDITOR"))
                .with(csrf())
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType("application/json")
                .content("{\"label\":\"Updated\"}"))
            .andExpect(status().isOk())
            .andExpect(content().json(
                "{\"id\":42,\"label\":\"Updated\"}"));
    }
}
```

**Đọc kết quả test:**

- Preflight PATCH được chấp nhận dù không có `Cookie` hoặc `@WithMockUser`, vì CORS được xử lý đúng thứ tự.
- Origin lạ, method PUT chưa allow, hoặc header `X-Admin-Override` chưa allow làm preflight bị từ chối.
- GET có authentication mock nhận CORS headers và `Access-Control-Expose-Headers` để browser có thể đọc `X-Request-ID`/`X-Total-Count`.
- PATCH có role EDITOR nhưng thiếu CSRF token vẫn bị 403; role không thay CSRF guard.
- PATCH có role EDITOR và CSRF token mock hợp lệ đi qua HTTP gate, controller trả JSON demo.

Test sử dụng `.with(user(...))` để giả lập authentication, **không test mật khẩu/form login**. `.with(csrf())` giả lập CSRF token, **không mô phỏng browser SameSite hoặc cookie thật**. Status CORS rejection có thể khác nếu custom CORS processor/exception handler được thay đổi; test ở đây dành cho cấu hình Spring Boot/Security điển hình.

Lệnh chạy:

```bash
mvn test
mvn spring-boot:run
```

Maven example có thể khởi tạo context dù chưa có user store do test dùng mocked user và các phép thử tập trung vào CORS; khi chạy một luồng login thật, bạn phải bổ sung `UserDetailsService`/authentication provider và user/password storage đúng chính sách. Domain HTTPS minh họa trong header không cần tồn tại thật đối với MockMvc.

## 11. `@CrossOrigin` và cấu hình MVC: lựa chọn khác

Spring MVC có thể khai báo CORS ở controller:

```java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET, RequestMethod.HEAD},
    allowedHeaders = {"Authorization", "Content-Type"},
    exposedHeaders = {"X-Request-ID", "X-Total-Count"},
    allowCredentials = "true",
    maxAge = 1800
)
public class ExampleCrossOriginController {

    @GetMapping("/api/example")
    public String example() {
        return "ok";
    }
}
```

**Lưu ý phạm vi:** annotation trên controller áp cho handler được annotate, trong khi `CorsConfigurationSource` có thể định nghĩa policy global theo path. Nếu dùng cả `@CrossOrigin`, `WebMvcConfigurer.addCorsMappings` và `CorsConfigurationSource`, cần hiểu cách framework kết hợp hoặc ưu tiên cấu hình, tránh policy ngoài ý muốn. Với Spring Security, hãy bật `.cors(...)` đúng để preflight qua security filter. Một nguồn policy trung tâm thường dễ audit khi API lớn.

Cấu hình `@CrossOrigin` giải thích được cả bốn trục, nhưng không nên rải annotation qua nhiều controller nếu chúng có thể lệch origin/method/header allowlists. Không dùng `@CrossOrigin("*")` với credentialed endpoints.

## 12. WebFlux: cùng CORS semantics, khác API filter chain

Ứng dụng Reactive WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Cấu hình **không hoán đổi** với Servlet MVC.

Tệp `ReactiveCorsSecurityConfig.java` dùng trong một ứng dụng WebFlux riêng:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class ReactiveCorsSecurityConfig {

    @Bean
    CorsConfigurationSource reactiveCorsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "PATCH", "OPTIONS"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        config.setExposedHeaders(List.of("X-Request-ID"));
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {
        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Đây là class Spring, cần Spring Boot WebFlux và Spring Security reactive dependencies. `HttpBasic` ở ví dụ chỉ minh họa authentication pipeline; browser có thể tự gửi Basic credentials đã cache, nên CSRF vẫn là vấn đề cần đánh giá. Khi tích hợp session login/SPA, cấu hình WebSession và token repository đúng với kiến trúc.

Lưu ý:

- Chọn đúng import **reactive** cho `CorsConfigurationSource` và `UrlBasedCorsConfigurationSource`.
- `CorsConfiguration` chung thuộc `org.springframework.web.cors`.
- `CorsWebFilter` hoặc tích hợp `.cors(...)` phải xử lý preflight **trước authentication**.
- Không gọi `block()` hay `subscribe()` thủ công trong security pipeline để “lấy origin”; CORS processing không cần làm vậy.
- Kiểm tra test bằng `WebTestClient` ở runtime reactive; `MockMvc` chỉ kiểm tra Servlet.
- Nếu project chứa cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, hãy xác định web runtime Boot thật đang dùng; không cấu hình cả hai chain và mong cả hai bảo vệ một request.

## 13. Java 17 độc lập: mô hình hóa ba điều kiện của preflight

Ví dụ sau là **Java thuần**, không cần Spring. Nó mô hình hóa cách một policy chỉ chấp nhận origin, method và request headers nằm trong các allowlists. `exposedHeaders` **không ảnh hưởng việc cho phép preflight**, bởi nó chỉ quy định những response headers mà JavaScript có thể đọc.

Tệp `CorsPolicyDemo.java`:

```java
import java.util.Locale;
import java.util.Set;

public class CorsPolicyDemo {

    private static final Set<String> ORIGINS =
        Set.of("https://app.example.com", "https://console.example.com");

    private static final Set<String> METHODS =
        Set.of("GET", "POST", "PATCH", "DELETE", "OPTIONS");

    private static final Set<String> HEADERS =
        Set.of("content-type", "authorization",
               "x-csrf-token", "x-request-id");

    record Request(String origin, String method, Set<String> headers) {}

    static boolean allowedByCors(Request request) {
        return ORIGINS.contains(request.origin())
            && METHODS.contains(request.method())
            && request.headers().stream().allMatch(header ->
                HEADERS.contains(header.toLowerCase(Locale.ROOT)));
    }

    static void check(String name, Request request) {
        System.out.println(name + ": " + allowedByCors(request));
    }

    public static void main(String[] args) {
        check("Allowed GET",
            new Request("https://app.example.com", "GET", Set.of()));
        check("Allowed PATCH",
            new Request("https://app.example.com", "PATCH",
                Set.of("Content-Type", "X-Request-ID")));
        check("Unknown header",
            new Request("https://app.example.com", "PATCH",
                Set.of("X-Admin-Override")));
        check("Unknown origin",
            new Request("https://evil.example.net", "GET", Set.of()));
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac CorsPolicyDemo.java
java CorsPolicyDemo
```

Stdout chuẩn chính xác:

```text
Allowed GET: true
Allowed PATCH: true
Unknown header: false
Unknown origin: false
```

Lớp này **không triển khai CORS chuẩn**: nó bỏ qua safelisted headers/methods, cookie/credentials, preflight cache, `Vary`, CORS response serialization, browser-specific policy và Spring routing. Nó chỉ giúp nhận diện **ba chiều đầu vào**. `exposedHeaders` không xuất hiện trong hàm `allowedByCors` vì đó là chính sách **quyền đọc response headers**, không phải input gate.

## 14. Dùng DevTools và curl để xác minh

### 14.1. Kiểm tra preflight bằng curl

```bash
curl -i -X OPTIONS https://api.example.com/api/items/42 \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token'
```

Đây là lệnh test hình dạng response; URL minh họa cần thay bằng môi trường thật. Xác minh:

- `Access-Control-Allow-Origin` khớp exact origin được allow.
- `Access-Control-Allow-Methods` có PATCH (không nhất thiết chỉ có PATCH).
- `Access-Control-Allow-Headers` chấp nhận các header mà frontend yêu cầu.
- `Access-Control-Allow-Credentials: true` nếu dùng credentials và policy cho phép.
- `Access-Control-Max-Age` và `Vary` hợp lý; không cache response theo origin sai.
- Không cần session cookie trên preflight; đừng chấp nhận 401 vì thiếu cookie như trạng thái bình thường của một policy cần CORS.

**curl không thực thi SOP/CORS**: curl có thể đọc body ngay cả khi server thiếu `Access-Control-Allow-Origin`. Nó phù hợp để xem response HTTP của backend, **không thay thế test bằng browser**.

### 14.2. Kiểm tra actual response

Trong DevTools → Network:

1. Xác định request có `Origin` thực tế nào (scheme/host/port).
2. Kiểm tra có OPTIONS preflight không; các request simple có thể không có preflight.
3. Kiểm tra `Access-Control-Request-Method` và `Access-Control-Request-Headers` trên OPTIONS.
4. Đọc response preflight: ACAO, ACAM, ACAH, ACAC, Max-Age.
5. Đọc response actual: ACAO, ACAC, `Access-Control-Expose-Headers` và các response headers muốn đọc.
6. Kiểm tra cookie thực sự có được gửi không (credentials/include + cookie policy), không nhầm CORS với SameSite.
7. Kiểm tra status security (401/403), CSRF token, role/permission và route có tồn tại.
8. Kiểm tra reverse proxy/gateway có xóa/ghi đè CORS headers không; test production-like HTTPS.

**CORS error ở console không luôn là root cause.** Một preflight trả 401 do security ordering, một redirect login, lỗi 500 không có CORS headers, cookie bị browser chặn hoặc proxy sai có thể đều xuất hiện dưới dạng CORS/network failure từ frontend.

## 15. Các lỗi cấu hình điển hình và cách sửa

| Lỗi | Triệu chứng | Hướng sửa |
|---|---|---|
| Dùng `allowedOrigins("*")` với `allowCredentials(true)` | Browser chặn credentialed response, Spring có thể từ chối config | Exact allowlist origins |
| Chỉ thêm `allowedHeaders` để JS đọc response header | `response.headers.get("X-Total-Count")` trả null | Thêm `exposedHeaders` tương ứng |
| Chỉ thêm `exposedHeaders` để gửi custom header | PATCH/JSON preflight thất bại | Thêm `allowedHeaders` theo request |
| Không cho PATCH trong `allowedMethods` | Preflight báo method không được phép | Thêm đúng method nếu API hợp lệ |
| Origin thiếu/sai port/scheme | ACAO không khớp hoặc vắng | Cấu hình exact origin thực tế |
| Preflight OPTIONS bị yêu cầu đăng nhập | 401/403 trước actual request | Tích hợp CORS trước security |
| Gửi cookie nhưng chỉ cấu hình allowedOrigins | JavaScript không truy cập credentialed response | allowCredentials và origin cụ thể, cùng cookie policy |
| Thêm `Cookie` vào allowedHeaders để “bật cookie” | Không thay đổi behavior | `credentials`/SameSite/Secure/Domain/Path |
| CORS mở quá rộng, kể cả wildcard patterns | Origin không tin cậy có thể đọc response | Giới hạn origin, review subdomains |
| Sai `Vary` qua CDN/cache | Response ACAO của origin này trả cho origin khác | Cache-aware headers, Spring CORS processor/proxy |
| Tin CORS chặn mọi attacker | Non-browser client vẫn gọi được API | Authentication, authorization, CSRF |
| Response có `Set-Cookie` nhưng JS không đọc được | `response.headers.get("Set-Cookie")` là null | Browser quản lý; không expose cookie |
| Thiếu allowed Request Header `Authorization` | Preflight bearer fetch bị từ chối | Khai báo allowedHeaders Authorization |
| `exposedHeaders("*")` cho requests có credentials | Browser khác nhau, không đáng tin | Liệt kê finite exposed headers |
| CORS policy cho POST nhưng CSRF bảo vệ POST | Preflight pass, POST 403 | Gửi CSRF token hợp lệ; không tắt guard |
| `@CrossOrigin` trộn config global làm lệch rule | Kết quả CORS không như dự kiến | Một policy có chủ đích, test paths/chains |

### 15.1. Chẩn đoán theo thứ tự

1. Có thật là cross-origin không (scheme, host, port)?
2. Browser có gửi preflight không? Method và request headers nào kích hoạt?
3. Origin có trong allowlist? Path có match CORS config không?
4. Allowed methods và allowed headers đáp ứng preflight không?
5. Nếu credentials, có exact ACAO + ACAC và browser cookie policy phù hợp không?
6. Actual response có CORS headers không, kể cả response lỗi?
7. Nếu cần đọc response headers, `exposedHeaders` đã khai báo chưa?
8. Authentication/authorization/CSRF và controller mapping có chặn actual không?
9. Gateway, CDN hoặc proxy có chèn, cache hoặc xóa CORS headers không?
10. Test bằng browser thật song song với curl/MockMvc; không kết luận từ một thông báo console duy nhất.

## 16. CORS và các lớp bảo vệ khác

### 16.1. CORS so với CSRF

CORS quyết định một origin JavaScript có được truy cập response và có được vượt qua preflight khi cần hay không. CSRF xảy ra khi browser tự gửi credential làm server tin request ngoài ý muốn. **Một request có thể bị JS chặn đọc response nhưng vẫn gây thay đổi dữ liệu phía server**, nên cần CSRF protection với cookie/session apps.

### 16.2. CORS so với authentication và authorization

- CORS allowlist không chứng minh user là Alice, không chứng minh token hợp lệ.
- `hasRole("ADMIN")` và `hasAuthority("item:read")` không thay CORS policy.
- Cần tenant/owner/state checks trong service nếu API thao tác tài nguyên có nhiều chủ sở hữu.
- Nếu đã xác thực nhưng thiếu scope, browser có thể thấy 403 khi CORS response được trình bày đúng.
- API client không phải browser không chịu sự thực thi CORS của browser; bảo mật backend phải đứng vững độc lập.

### 16.3. CORS so với CSP/SOP

SOP là chính sách cô lập origin ở browser. CORS là một cơ chế **nới** một số hạn chế đọc response cross-origin theo quyền do server cấp. CSP (đặc biệt `connect-src`) có thể giới hạn những đích mà chính frontend được phép kết nối; CSP trên trang frontend không thay thế CORS từ API.

### 16.4. CORS so với SameSite

CORS dựa trên **origin**; SameSite cookie dựa trên **site** (schemeful registrable domain). Hai subdomain có thể same-site và khác-origin, nên frontend có thể cần CORS nhưng cookie `SameSite=Lax` vẫn được gửi theo điều kiện same-site. Ngược lại, frontend cross-site có `SameSite=None; Secure` vẫn có thể bị third-party cookie blocking.

## 17. Checklist dùng trước production

- [ ] Ghi rõ origin frontend thực tế bằng scheme/host/port; không dùng chuỗi domain chưa xác thực.
- [ ] Dùng allowlist exact cho `allowedOrigins`; nếu dùng patterns phải audit subdomains, tenant và takeover risk.
- [ ] `allowedMethods` chỉ gồm methods thực sự cần; không mở wildcard theo thói quen.
- [ ] `allowedHeaders` chỉ gồm request headers frontend cần (Content-Type, Authorization, CSRF, request-id...).
- [ ] `exposedHeaders` chỉ gồm response headers JavaScript phải đọc (X-Request-ID, X-Total-Count...).
- [ ] Với credentials, origin phải cụ thể, `allowCredentials(true)` được bật có lý do, cookie policy được kiểm tra.
- [ ] Preflight xử lý trước authentication; không yêu cầu cookie/session trên OPTIONS.
- [ ] API vẫn xác thực JWT/session/password, kiểm tra role/authority và tài nguyên.
- [ ] Unsafe requests có CSRF defense phù hợp nếu browser tự gửi credential.
- [ ] `Set-Cookie` không được coi là response header JS có thể đọc dù exposed.
- [ ] `Vary: Origin` và cache headers được giữ qua gateway/CDN, kể cả các preflight conditions.
- [ ] Có test positive/negative cho origin, method, header, exposed response headers và credentials.
- [ ] Thử cả local development ports và HTTPS production; không tự nới policy khi gặp CORS error.
- [ ] Phân biệt MockMvc/WebTestClient/curl với **behavior thật của browser**.
- [ ] Mọi ngoại lệ rộng được tài liệu hóa, review và có chủ sở hữu.

## 18. Tự kiểm tra

**Câu 1:** Frontend muốn đọc `X-Total-Count` trong response. Thêm `X-Total-Count` vào `allowedHeaders` có đủ không?

**Trả lời:** Không. `allowedHeaders` chỉ áp cho headers client gửi. Phải thêm `X-Total-Count` vào `exposedHeaders` và đảm bảo API thật sự trả header đó.

**Câu 2:** API cho `https://app.example.com` nhưng trình duyệt gửi `Origin: http://app.example.com`. Hai origin có khớp không?

**Trả lời:** Không; scheme khác (`http` với `https`).

**Câu 3:** Preflight trả 200 và có `Access-Control-Allow-Methods: PATCH`. PATCH thật có chắc chạy thành công không?

**Trả lời:** Không. Handler có thể thiếu, user có thể không đủ quyền, CSRF token sai hoặc dữ liệu không hợp lệ. CORS không cấp permission.

**Câu 4:** Frontend dùng cookie authentication. Có thể trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` không?

**Trả lời:** Không. Credentialed response cần origin cụ thể được allow; wildcard origin không được browser chấp nhận.

**Câu 5:** Preflight OPTIONS không có `JSESSIONID` và bị Spring Security trả 401. Cần cho user đăng nhập lại trên preflight không?

**Trả lời:** Không. Phải xử lý CORS trước authentication, cấu hình `CorsConfigurationSource` và `.cors(...)` đúng; preflight không phải request nghiệp vụ xác thực.

**Câu 6:** Có cách dùng `exposedHeaders` để JavaScript đọc `Set-Cookie` không?

**Trả lời:** Không. `Set-Cookie` là forbidden response header đối với Fetch; browser quản lý cookie riêng.

## 19. Tài liệu chính thức

- [Spring Framework – CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- [Spring Framework – CORS trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html).
- [Spring Security – Servlet CORS integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security – Reactive CORS integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- [MDN – Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers).
- [MDN – Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers).
- [MDN – Access-Control-Allow-Methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Methods).

**Ghi nhớ:** `allowedOrigins` = **frontend origin nào** được đọc response; `allowedMethods` = **HTTP method nào** được chấp nhận trong CORS preflight; `allowedHeaders` = **request headers nào frontend có thể gửi**; `exposedHeaders` = **response headers nào frontend có thể đọc**. Khi có cookie/auth credentials, cần origin cụ thể và policy thích hợp. CORS phải xử lý trước Spring Security authentication trong luồng preflight, nhưng **không bao giờ thay thế authentication, authorization, CSRF, TLS hay quyền theo đối tượng tại server**.