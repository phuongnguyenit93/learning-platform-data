# Credentials, cookie và ràng buộc khi cho phép origin

## 1. Bài toán: CORS cho phép đọc response có phiên đăng nhập

Trong hệ thống Spring Security, một giao diện tại `https://app.example.com` có thể cần gọi API tại `https://api.example.com` để hiển thị thông tin người dùng đã đăng nhập. Hai địa chỉ này **khác origin**, vì hostname khác nhau. Nếu API dùng session cookie, frontend có thể cần gửi cookie trong request cross-origin và đọc dữ liệu cá nhân từ response.

Vấn đề không được giải quyết chỉ bằng một header. Ít nhất có **ba quyết định độc lập**:

1. **JavaScript có yêu cầu trình duyệt gửi credentials không?** Fetch sử dụng tùy chọn `credentials`.
2. **Trình duyệt có thực sự được phép gửi cookie đến API không?** Cookie phải thỏa Domain/Path, `Secure`, `SameSite` và chính sách cookie của trình duyệt.
3. **Trình duyệt có cho phép JavaScript đọc response đã trả về không?** CORS phải cấp quyền cho origin và đáp ứng yêu cầu credentials mode, thường qua `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials`.

Trong mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, sự kết hợp này phải đi cùng authentication, authorization, CSRF protection, security headers, CSP, HSTS, HTTP firewall và quản lý session trên cả **Servlet** lẫn **Reactive**. CORS chỉ quyết định việc chia sẻ response cross-origin cho JavaScript; nó không xác thực người dùng hoặc thay thế những lớp bảo vệ đó.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt `credentials: "omit"`, `"same-origin"` và `"include"`, đặc biệt với frontend và API nằm ở hai subdomain.
- Giải thích khi nào phải dùng `Access-Control-Allow-Credentials: true`, tại sao không được ghép với `Access-Control-Allow-Origin: *` trong request dùng credentials mode `include`.
- Phân biệt **cross-origin** với **cross-site**, và hiểu `SameSite`, `Secure`, `HttpOnly`, Domain/Path, chính sách cookie bên thứ ba.
- Cấu hình CORS với danh sách origin tin cậy cho Spring Security Servlet và Reactive, kiểm tra cả preflight lẫn actual response.
- Chẩn đoán các trường hợp cookie không được gửi, browser chặn response, hoặc request thất bại vì CSRF/xác thực nhưng bị hiểu nhầm thành CORS.

## 2. Credentials gồm những gì?

Trong ngữ cảnh Fetch, *credentials* có thể liên quan tới cookie, thông tin xác thực HTTP và chứng thư TLS phía client. Các hệ thống web phổ biến thường quan tâm nhất đến **session cookie**. Bên cạnh đó, JavaScript có thể chủ động đặt header `Authorization: Bearer ...`, nhưng việc đặt header này cần phân biệt với tùy chọn `credentials` của Fetch.

Ví dụ:

~~~javascript
// API dùng session cookie do browser quản lý.
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Khác với:

~~~javascript
// API dùng bearer token được ứng dụng chủ động đặt trong header.
const response = await fetch("https://api.example.com/api/me", {
  credentials: "omit",
  headers: {
    Authorization: "Bearer <access-token>"
  }
});
~~~

Ở ví dụ bearer token, `Authorization` là header do chương trình đặt và thường khiến cross-origin request cần **preflight**. Nó không có nghĩa browser tự tìm session cookie để gửi. Cần bảo vệ token theo mô hình xác thực của ứng dụng; cấu hình CORS không quyết định token đó hợp lệ hay không.

### 2.1. Ba giá trị của Fetch credentials

| Giá trị | Hành vi chính | Khi gọi `https://api.example.com` từ `https://app.example.com` |
| --- | --- | --- |
| `omit` | Không tự gửi credentials thuộc quản lý Fetch; không nhận `Set-Cookie` theo cơ chế credentials của Fetch | Không gửi session cookie chỉ vì browser đang lưu cookie |
| `same-origin` | Gửi/nhận credentials theo mặc định cho request **cùng origin** | **Không** gửi cookie trong request này vì API khác origin |
| `include` | Cho phép browser gửi/nhận credentials với cả request cross-origin theo chính sách cookie và trình duyệt | Có thể gửi cookie phù hợp tới API |

Giá trị mặc định của `fetch()` là **`"same-origin"`**. Nếu không khai báo `credentials`, request từ `app.example.com` sang `api.example.com` không tự động gửi session cookie của API, mặc dù hai địa chỉ có thể cùng site.

~~~javascript
// Mặc định là credentials: "same-origin".
await fetch("https://api.example.com/api/me");

// Chủ động yêu cầu dùng credentials trong request khác origin.
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

**Điểm quan trọng:** `credentials: "include"` là yêu cầu về **chế độ credentials**, không phải lệnh ép browser gửi cookie. Cookie có thể vẫn không được đính kèm vì thuộc tính cookie, domain, chính sách chống tracking hoặc quyền riêng tư. Đồng thời, CORS với credentials mode `include` có các điều kiện chặt chẽ ngay cả khi không có cookie nào thực sự được gửi.

## 3. Hai header CORS bắt buộc hiểu cùng nhau

Đối với JavaScript từ `https://app.example.com` thực hiện `fetch` với `credentials: "include"`, API muốn browser cho đọc response cần trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Trong đó:

- `Access-Control-Allow-Origin` chỉ định **origin cụ thể được phép đọc response**, phải phù hợp với `Origin` của request.
- `Access-Control-Allow-Credentials: true` cho biết server chấp thuận chia sẻ response cho request ở credentials mode cần điều kiện này. Giá trị có hiệu lực là `true`, phân biệt hoa thường theo cú pháp CORS; không dùng `True` hoặc `1`.
- `Vary: Origin` giúp cache HTTP phân biệt response theo origin khi server chọn `Access-Control-Allow-Origin` dựa trên `Origin` nhận được.

### 3.1. Vì sao wildcard origin bị từ chối?

Response sau **không hợp lệ** để JavaScript đọc dưới `credentials: "include"`:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Dấu `*` không thể cấp quyền CORS đọc response trong credentials mode `include`. Browser từ chối chia sẻ response cho JavaScript, kể cả khi server đã xử lý request và trả HTTP 200.

Tương tự, chỉ trả origin cụ thể nhưng thiếu `Access-Control-Allow-Credentials: true` cũng không đủ:

~~~http
Access-Control-Allow-Origin: https://app.example.com
# Thiếu Access-Control-Allow-Credentials: true
~~~

| `Access-Control-Allow-Origin` | `Access-Control-Allow-Credentials` | Fetch `credentials: "include"` được đọc response? |
| --- | --- | --- |
| `https://app.example.com` | `true` | Có, nếu các điều kiện CORS khác đạt |
| `https://app.example.com` | Thiếu | Không |
| `https://evil.example.com` | `true` | Không, vì origin không khớp |
| `*` | `true` | Không, wildcard bị cấm với chế độ này |
| Thiếu | `true` | Không |
| `https://app.example.com` | `false` hoặc giá trị sai cú pháp | Không |

Cột cuối chỉ nói về **quyền đọc response**. Việc API trả 401/403, cookie không được gửi hoặc CSRF thất bại là những vấn đề khác cần điều tra riêng.

### 3.2. Allow-Credentials không tự tạo cookie

`Access-Control-Allow-Credentials: true` là một **response header của server**, không phải chỉ thị browser tự gửi session ID. Browser quyết định gửi cookie theo Fetch credentials mode và luật cookie. JavaScript cũng không thể tự đọc session cookie đặt `HttpOnly` để gắn vào request.

Trong ứng dụng dùng bearer token thủ công, không mặc nhiên bật `allowCredentials(true)` chỉ vì request có `Authorization`. Việc có cần `Access-Control-Allow-Credentials` phụ thuộc vào **credentials mode của Fetch và yêu cầu CORS**, còn `Authorization` là header phải được cho phép ở preflight khi cần. Server luôn phải xác thực token.

## 4. Hai khái niệm khác nhau: cross-origin và cross-site

Đây là nguyên nhân thường gặp khiến cấu hình CORS trông đúng nhưng cookie vẫn không hoạt động.

- **Origin** được xác định bằng *scheme + host + port*.
- **Site** trong chính sách cookie hiện đại thường dựa trên *scheme + registrable domain* (ví dụ `example.com` trong tên miền minh họa); port không tham gia xác định site.

| Trang frontend | API đích | Cross-origin? | Thường là cross-site? |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/api` | Không | Không |
| `https://app.example.com` | `https://api.example.com` | Có | Không, thường same-site |
| `https://app.example.com:443` | `https://app.example.com:8443` | Có | Không, port khác |
| `https://app.example.com` | `http://api.example.com` | Có | Có, do khác scheme trong schemeful same-site |
| `https://app.example.com` | `https://login.partner.test` | Có | Có, khác site |

Bảng mô tả các ngữ cảnh HTTPS và HTTP thông dụng. *Public Suffix List* và cách xác định registrable domain là phần quan trọng khi xét site thực tế; không thể chỉ cắt chuỗi hostname ở dấu chấm cuối. Đặc biệt, `localhost` và địa chỉ IP cần được đánh giá theo quy tắc trình duyệt, không suy luận rằng chúng là các subdomain production.

### 4.1. Tại sao `SameSite=Lax` có thể dùng giữa hai subdomain?

Giả sử:

- Frontend: `https://app.example.com`.
- API: `https://api.example.com`.
- Cookie phiên được API đặt cho host `api.example.com` với `SameSite=Lax`.

Hai host **khác origin** nhưng thường **same-site**. Nếu frontend dùng `credentials: "include"` và cookie đáp ứng các ràng buộc khác, cookie `SameSite=Lax` có thể được gửi trong request tới API. Không bắt buộc đổi sang `SameSite=None` chỉ vì API khác subdomain.

CORS vẫn phải cho phép origin frontend cụ thể và hỗ trợ credentials mode nếu JavaScript cần đọc response. Cookie `SameSite` và CORS giải quyết **hai câu hỏi khác nhau**.

### 4.2. Khi nào cần `SameSite=None; Secure`?

Nếu trang ở `https://portal.example.com` thực hiện request tới `https://api.partner.test` và xác thực bằng cookie của `api.partner.test`, đây là **cross-site request**.

Để cookie có khả năng được gửi trong bối cảnh cross-site, cookie thường cần:

~~~http
Set-Cookie: SESSION=opaque-value; Path=/; HttpOnly; Secure; SameSite=None
~~~

Điều này **chưa bảo đảm** browser sẽ gửi cookie: nhiều trình duyệt hạn chế cookie bên thứ ba, sử dụng chính sách tracking prevention, cookie partitioning hoặc cài đặt người dùng. `SameSite=None; Secure` là điều kiện cần trong nhiều tình huống, không phải biện pháp vượt qua mọi giới hạn quyền riêng tư.

Đối với ứng dụng vừa và nhỏ, việc tổ chức frontend và backend dưới những site được kiểm soát phù hợp hoặc dùng backend-for-frontend có thể đơn giản hơn so với phụ thuộc hoàn toàn vào cookie bên thứ ba. Việc thay đổi kiến trúc vẫn phải cân nhắc CSRF, phiên đăng nhập và quyền dữ liệu.

## 5. Cookie được gửi đến host nào?

Một cookie HTTP không thuộc quyền sở hữu của mọi website cùng tên công ty. Browser đánh giá cookie đối với **đích request** theo ít nhất các thuộc tính:

| Thuộc tính | Tác dụng |
| --- | --- |
| `Domain` | Giới hạn host hoặc nhóm subdomain được phép nhận cookie |
| `Path` | Giới hạn đường dẫn request gửi cookie |
| `Secure` | Chỉ gửi cookie qua kết nối bảo mật theo chính sách browser |
| `HttpOnly` | Không cho JavaScript truy cập cookie qua `document.cookie` |
| `SameSite` | Điều khiển cookie được gửi trong ngữ cảnh same-site/cross-site |
| `Expires` hoặc `Max-Age` | Giới hạn thời gian tồn tại |
| `Partitioned` (nếu hỗ trợ) | Yêu cầu cookie được phân vùng theo site cấp trên, phục vụ một số trường hợp nhúng/cross-site |

### 5.1. Host-only cookie

Response từ `https://api.example.com`:

~~~http
Set-Cookie: SESSION=server-generated-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu **không** có `Domain`, cookie thường là *host-only*, chỉ được gửi tới `api.example.com` khi các điều kiện khác phù hợp. Trang `https://app.example.com` không cần đọc cookie đó trực tiếp để có thể yêu cầu browser gửi nó tới `api.example.com` bằng Fetch `credentials: "include"`.

Điều này thường phù hợp với session cookie: giữ cookie ở hostname API thay vì cố mở rộng quyền nhận cookie tới toàn bộ các subdomain.

### 5.2. Cookie khai báo Domain

Một response từ subdomain phù hợp có thể đặt:

~~~http
Set-Cookie: SESSION=server-generated-id; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có phạm vi host rộng hơn. Cấu hình Domain phải tuân thủ quy tắc DNS/public suffix của browser; không phải server nào cũng có thể đặt cookie cho domain bất kỳ. Mở rộng Domain làm tăng số host có thể nhận cookie, vì vậy không nên dùng chỉ để sửa lỗi CORS. Với hệ thống có nhiều subdomain khác mức độ tin cậy, host-only thường giảm phạm vi ảnh hưởng khi một subdomain bị xâm nhập.

### 5.3. HttpOnly và Set-Cookie

`HttpOnly` ngăn JavaScript đọc cookie qua `document.cookie`. Nó **không ngăn browser tự gửi cookie** trong request HTTP được phép.

Đồng thời, `Set-Cookie` là **forbidden response-header name** với Fetch. Ngay cả khi API cấu hình:

~~~http
Access-Control-Expose-Headers: Set-Cookie
~~~

JavaScript vẫn không đọc được `Set-Cookie` bằng `response.headers.get("Set-Cookie")`. Browser có thể lưu cookie nếu request và chính sách cookie đáp ứng điều kiện tương ứng; việc lưu cookie không đòi hỏi JavaScript đọc được header.

### 5.4. Cookie có thể bị từ chối dù CORS thành công

Giả sử API trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nhưng request thực tế là cross-site, hoặc dùng `credentials: "omit"`, hoặc cookie bị chính sách trình duyệt chặn. Khi đó frontend **có thể** được đọc body theo CORS nhưng phiên đăng nhập vẫn không được thiết lập hoặc duy trì như mong đợi.

Sự kiện gửi/lưu cookie và kiểm tra CORS có thể dẫn tới kết quả khác nhau. Phải xem tab **Cookies** của DevTools và mục nguyên nhân cookie bị loại bỏ, thay vì suy luận chỉ từ header `Access-Control-Allow-Credentials`.

## 6. Luồng đầy đủ: đăng nhập bằng cookie và gọi API

Xét một kiến trúc **same-site nhưng cross-origin**:

- Frontend: `https://app.example.com`.
- API: `https://api.example.com`.
- Browser lưu session cookie dành cho `api.example.com`.
- Frontend cần gọi `GET /api/me`.

### 6.1. Yêu cầu JavaScript

~~~javascript
async function loadProfile() {
  const res = await fetch("https://api.example.com/api/me", {
    method: "GET",
    credentials: "include"
  });

  if (!res.ok) {
    throw new Error("Không lấy được hồ sơ: HTTP " + res.status);
  }

  return await res.json();
}
~~~

`GET` thông thường này có thể **không cần preflight**. `credentials: "include"` tự nó không làm browser phải gửi `OPTIONS`.

### 6.2. Actual request

Nếu cookie hợp lệ và trình duyệt cho phép:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=opaque-session-id
~~~

Header `Cookie` được browser tạo; JavaScript thông thường không được trực tiếp gán `Cookie` trong Fetch.

### 6.3. Actual response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: private, no-store

{"userId":42,"displayName":"Lan"}
~~~

Nếu session hợp lệ, API trả dữ liệu phù hợp với **quyền của user**. Nếu CORS cũng hợp lệ, browser mới trao response cho JavaScript.

`Cache-Control: private, no-store` trong ví dụ thể hiện biện pháp giảm rủi ro lưu cache cho dữ liệu nhạy cảm; cần thiết kế cache theo tính chất dữ liệu thật, tách biệt với quy tắc CORS.

~~~mermaid
sequenceDiagram
    participant UI as JavaScript tại app.example.com
    participant Browser as Trình duyệt
    participant API as Spring Security API tại api.example.com
    UI->>Browser: fetch(/api/me, credentials include)
    Browser->>Browser: Kiểm tra Domain/Path/Secure/SameSite/chính sách cookie
    Browser->>API: GET /api/me + Origin + Cookie (nếu được phép)
    API->>API: Xác thực session và phân quyền
    API-->>Browser: 200 hoặc 401/403 + Allow-Origin + Allow-Credentials
    Browser->>Browser: Kiểm tra quyền CORS với credentials mode
    alt Hợp lệ
        Browser-->>UI: Response và JSON có thể đọc
    else Thiếu hoặc sai quyền CORS
        Browser-->>UI: Lỗi CORS, không đọc được response
    end
~~~

**Hai tình huống lỗi độc lập:**

- Cookie không được gửi → API trả `401 Unauthorized`. Nếu response 401 có header CORS hợp lệ, frontend **đọc được status 401** và hiển thị yêu cầu đăng nhập.
- API trả 200 nhưng thiếu `Access-Control-Allow-Credentials: true` → frontend **không đọc được response**, dù API đã xác thực và xử lý request thành công.

Không nên “sửa” lỗi thứ hai bằng cách cho phép mọi origin, vì response có thể chứa dữ liệu cá nhân.

## 7. Khi request cần preflight, credentials hoạt động thế nào?

Frontend thực hiện request thay đổi trạng thái với session cookie và CSRF token:

~~~javascript
async function changeDisplayName(csrfToken) {
  const res = await fetch("https://api.example.com/api/profile", {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ displayName: "Lan Nguyen" })
  });

  if (!res.ok) {
    throw new Error("Cập nhật thất bại: HTTP " + res.status);
  }
}
~~~

`PUT`, `Content-Type: application/json` và `X-CSRF-TOKEN` khiến request này cần preflight. Trình duyệt thường **không gửi cookie phiên hoặc token xác thực của actual request trong preflight CORS**:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type, x-csrf-token
~~~

Preflight response hợp lệ cho actual request có credentials mode `include`:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, PUT
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Nếu preflight qua được, browser mới gửi actual request:

~~~http
PUT /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: <valid-csrf-token>
Cookie: SESSION=opaque-session-id

{"displayName":"Lan Nguyen"}
~~~

Response thực tế **cũng phải** mang quyền CORS hợp lệ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Spring Security vẫn cần xác thực session, phân quyền user và kiểm tra CSRF token trên **actual PUT**. Preflight không phải request cập nhật hồ sơ và không nên bị chặn vì thiếu cookie phiên.

### 7.1. Preflight không gửi cookie không có nghĩa actual request không dùng cookie

Đây là nhầm lẫn phổ biến: request `OPTIONS` thiếu `Cookie` là **bình thường**. Cấu hình buộc OPTIONS preflight phải authenticated bằng session thường gây lỗi 401/403 và khiến browser **không gửi actual PUT**.

Hãy để CORS xử lý preflight trước phần xác thực của Spring Security. Chỉ thêm rule cho `OPTIONS` mà không có các response header CORS vẫn chưa đủ.

### 7.2. Preflight không phải cơ chế CSRF

Một `POST` dạng form có thể không cần preflight. Nếu có cookie phiên và ứng dụng không chống CSRF, request gây thay đổi trạng thái có thể được server xử lý dù JavaScript trên trang lạ **không đọc được response**. Vì vậy, bảo vệ CSRF vẫn cần dựa trên mô hình cookie/session và nguy cơ thay đổi trạng thái, không dựa vào việc preflight có xuất hiện hay không.

## 8. Cấu hình Spring Security Servlet

Với Spring MVC + Spring Security, có thể khai báo một chính sách CORS cụ thể và tích hợp sớm qua `HttpSecurity.cors`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chỉ các giao diện có quyền đọc response đã xác thực.
        cors.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Content-Type",
            "X-CSRF-TOKEN",
            "Authorization"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Cách đọc cấu hình:**

- `allowedOrigins` là origin **của frontend tin cậy**, không phải URL API. Không chứa path.
- `allowCredentials(true)` khiến Spring có thể trả `Access-Control-Allow-Credentials: true` cho request CORS hợp lệ; **không tự gửi cookie** và không tự cấp session.
- `allowedMethods`, `allowedHeaders` cho preflight; `exposedHeaders` cho phép frontend đọc thêm các response header được chỉ rõ.
- `http.cors(Customizer.withDefaults())` tích hợp xử lý CORS vào security filter chain, để preflight được xử lý thích hợp trước khi bộ lọc xác thực gây lỗi vì thiếu cookie.
- `anyRequest().authenticated()` vẫn buộc actual request xác thực; nhưng ví dụ này **chưa cấu hình một cơ chế đăng nhập cụ thể**. Cần kết hợp session login, authorization và CSRF theo ứng dụng thật.

### 8.1. Không dùng `allowedOrigins("*")` khi bật credentials

Ví dụ sai:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true); // Không hợp lệ với wildcard allowedOrigins.
~~~

Spring có cơ chế kiểm tra tổ hợp này và có thể từ chối cấu hình trong lúc xử lý. Không sửa bằng cách phản chiếu `Origin` từ request một cách vô điều kiện. Cách phù hợp là allowlist origin cụ thể.

`allowedOriginPatterns` cho phép đặt pattern rồi trả origin đã khớp dưới dạng cụ thể, nhưng việc hỗ trợ `allowCredentials(true)` **không có nghĩa pattern rộng là an toàn**:

~~~java
// Chỉ dùng nếu tổ chức thật sự kiểm soát mọi subdomain có thể khớp.
cors.setAllowedOriginPatterns(List.of(
    "https://*.trusted-frontends.example.com"
));
~~~

Một subdomain bị chiếm hoặc do người dùng tạo có thể khiến pattern quá rộng cấp quyền đọc dữ liệu đã xác thực cho JavaScript không đáng tin cậy. Chỉ dùng sau khi đánh giá quyền sở hữu subdomain.

### 8.2. Cookie được tạo ở đâu?

CORS **không tạo session cookie**. Với ứng dụng Servlet dùng session, cookie thường được servlet container hoặc cơ chế đăng nhập tạo và gửi trong response `Set-Cookie`. Phải cấu hình riêng thuộc tính `Secure`, `HttpOnly`, `SameSite`, Domain/Path, timeout phiên, session fixation protection và bảo vệ CSRF phù hợp.

Không giả định rằng bật `cors.setAllowCredentials(true)` tự thêm `SameSite=None`, tự tạo cookie hoặc tự bật HTTPS/HSTS. Đây là các thiết lập độc lập trong hệ thống.

## 9. Cấu hình Spring Security Reactive / WebFlux

Với WebFlux, sử dụng `ServerHttpSecurity`, `SecurityWebFilterChain` và `UrlBasedCorsConfigurationSource` ở package reactive:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "Authorization"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }
}
~~~

Ý nghĩa `allowedOrigins`, `allowCredentials` và header CORS không khác Servlet. Điểm cần chú ý là **thứ tự xử lý trong pipeline reactive**: preflight phải có cơ hội được CORS xử lý trước khi authentication chặn vì không có cookie/token. Nếu dùng `CorsWebFilter` riêng, hãy phối hợp thứ tự filter và tránh đồng thời khai báo nhiều cơ chế chèn CORS header mâu thuẫn.

Session trong WebFlux có cơ chế quản lý riêng, có thể đi qua `WebSession` và cookie phiên của ứng dụng. Đừng sao chép nguyên cấu hình servlet container để giả định thuộc tính cookie reactive luôn giống hệt nhau. Chính sách `SameSite`, `Secure`, session và CSRF cần được cấu hình tại thành phần quản lý phiên/cookie tương ứng với stack đang chạy.

## 10. Origin được phép là quyết định tin cậy dữ liệu

Một hệ thống chỉ nên cấp quyền CORS với credentials mode cho những frontend **đáng tin cậy đọc dữ liệu thay mặt user**.

Giả sử user đã đăng nhập vào `api.example.com`. Nếu API trả:

~~~http
Access-Control-Allow-Origin: https://evil.example.com
Access-Control-Allow-Credentials: true
~~~

và browser gửi cookie hợp lệ khi JavaScript ở `evil.example.com` gọi API, trang lạ có thể **đọc dữ liệu riêng tư** mà API trả cho user đó. Điều này xảy ra vì server đã cấp quyền đọc response cho origin không tin cậy.

Các sai lầm nguy hiểm:

~~~java
// SAI: phản chiếu mọi Origin do client tự khai báo.
String origin = request.getHeader("Origin");
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
~~~

~~~java
// SAI: wildcard rộng cho thông tin có phiên đăng nhập.
cors.setAllowedOriginPatterns(List.of("*"));
cors.setAllowCredentials(true);
~~~

Một pattern không giới hạn hay phản chiếu không kiểm tra làm mất ý nghĩa allowlist. Thay vào đó, chỉ liệt kê frontend có thực sự được vận hành và bảo vệ. Origin từ request **không chứng minh người gọi là user hợp lệ**; các HTTP client ngoài browser có thể đặt `Origin` giả.

Cũng không đủ để nói “các trang cùng công ty đều an toàn”. Nếu một subdomain cho phép upload HTML/JS của người dùng, bị chiếm DNS, bị XSS, hoặc do bên thứ ba vận hành, việc cấp CORS với credentials cho toàn bộ subdomain đó có thể làm tăng mức độ thiệt hại.

## 11. CORS, CSRF và các header bảo vệ khác

| Cơ chế | Vấn đề được giải quyết |
| --- | --- |
| Fetch `credentials` | Browser được yêu cầu gửi/nhận credentials theo chế độ nào? |
| Cookie `SameSite` / `Secure` / `HttpOnly` | Cookie được gửi trong ngữ cảnh nào, qua kết nối nào, có cho JavaScript đọc trực tiếp không? |
| CORS `Allow-Origin` / `Allow-Credentials` | JavaScript cross-origin có được đọc response trong credentials mode này không? |
| Authentication | Request đại diện cho user/client nào? |
| Authorization | User/client có được phép dùng tài nguyên, dữ liệu hoặc thao tác không? |
| CSRF protection | Request thay đổi trạng thái dùng phiên có được bảo vệ khỏi việc kích hoạt trái ý muốn không? |
| CSP `connect-src` | JavaScript tại frontend được kết nối tới những đích nào? |
| HSTS, TLS và session security | Bảo vệ đường truyền HTTPS, cookie phiên, vòng đời session và nguy cơ chiếm phiên |

### 11.1. CORS có chặn CSRF không?

**Không.** CORS thường hạn chế JavaScript đọc response chứ không chặn mọi request cross-site đi đến server. Một form HTML cross-site có thể thực hiện request thuộc loại không cần preflight; browser vẫn có thể mang cookie nếu chính sách cookie cho phép. Nếu server xử lý thao tác thay đổi trạng thái mà thiếu chống CSRF, việc browser chặn đọc response không ngăn hậu quả.

Với Spring Security dùng session cookie, hãy giữ cơ chế kiểm tra CSRF token phù hợp. API dựa trên bearer token mà browser không tự gắn token có mô hình CSRF khác, nhưng vẫn cần đánh giá các đường xác thực khác có tồn tại không; không tắt CSRF một cách máy móc.

### 11.2. Tránh xung đột giữa CORS và xử lý lỗi bảo mật

API có thể trả `401` khi chưa đăng nhập, `403` khi thiếu quyền hoặc CSRF token. Nếu response lỗi không mang header CORS hợp lệ, JavaScript chỉ thấy lỗi CORS và không đọc được status thực tế. Khi chẩn đoán, kiểm tra cả **actual response của lỗi** ở Servlet filter, Reactive filter, gateway và exception handler.

### 11.3. Cẩn trọng với dữ liệu nhạy cảm và cache

Với response cá nhân hóa theo cookie, cần thiết kế cache tránh chia sẻ nhầm dữ liệu user qua CDN/proxy. `Vary: Origin` chỉ giúp phân biệt theo origin khi header phản hồi phụ thuộc origin; nó **không tự giải quyết** việc cache dữ liệu theo từng user. Đối với dữ liệu riêng tư, xem xét `Cache-Control: private` hoặc `no-store` và cấu hình cache phù hợp.

## 12. Kiểm thử từng lớp thay vì chỉ tìm “CORS error”

### 12.1. Ma trận kỳ vọng

Giả sử API cấp CORS credentials cho duy nhất `https://app.example.com` và sử dụng session cookie.

| Tình huống | Browser có thể gửi cookie? | JavaScript có thể đọc response? |
| --- | --- | --- |
| `Origin: https://app.example.com`, `credentials: "include"`, cookie hợp lệ, CORS đầy đủ | Có | Có, nếu response đạt CORS |
| `Origin: https://app.example.com`, `credentials: "same-origin"` tới API khác origin | Không theo chế độ Fetch này | Có thể đọc nếu CORS không-credentialed hợp lệ |
| `Origin: https://evil.example.com`, `credentials: "include"` | Tùy cookie/third-party policy | Không, nếu allowlist từ chối origin |
| `credentials: "include"`, response `Allow-Origin: *` | Tùy cookie policy | Không, wildcard không hợp lệ |
| `credentials: "include"`, response thiếu `Allow-Credentials` | Tùy cookie policy | Không |
| `credentials: "include"`, cookie bị chặn bởi `SameSite` | Không | Có thể đọc HTTP 401 nếu response có CORS hợp lệ |
| `credentials: "include"`, preflight bị 401 | Chưa tới actual request | Không; actual request không được gửi |
| Actual response 403 vì CSRF, CORS hợp lệ | Nếu request có cookie thì có thể đã gửi | Có, đọc được 403 để xử lý |

Trong cột “có thể gửi cookie”, câu trả lời còn phụ thuộc cookie thực sự có tồn tại, Domain/Path/`Secure`/`SameSite` và chính sách browser. Không có header CORS nào có thể **ép** browser đính kèm cookie bị chặn.

### 12.2. Dùng DevTools

Từ **frontend thực** đang chạy tại origin được cấu hình:

1. Mở **Network** và chọn request `/api/me`.
2. Xem **Request Headers**: có `Origin: https://app.example.com` không? Có `Cookie` không? Nếu cookie vắng mặt, kiểm tra tab Cookies và lý do cookie bị chặn.
3. Xem **Response Headers**: có `Access-Control-Allow-Origin` đúng origin và `Access-Control-Allow-Credentials: true` không?
4. Với request `PUT` hoặc `POST` JSON, kiểm tra **OPTIONS preflight**: có bị 401/403, không cho method hoặc không cho `X-CSRF-TOKEN` không?
5. Nếu OPTIONS thành công, kiểm tra **actual request** có xuất hiện và response lỗi 401/403/500 có header CORS hay không.
6. Nếu cookie không được gửi dù `credentials: "include"`, kiểm tra `SameSite`, `Secure`, Domain/Path, HTTP/HTTPS và chính sách cookie bên thứ ba.
7. Đối chiếu **Console** với Network: lỗi CORS ở Console thường không cho biết toàn bộ lý do xác thực hoặc cookie ở tầng server.

Không sửa bằng `mode: "no-cors"`: chế độ này làm response bị giới hạn đọc (*opaque*), không cấp quyền đọc JSON hay session.

### 12.3. Xem header API bằng curl

Kiểm tra actual response:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com"
~~~

Có thể mô phỏng request mang cookie thử nghiệm:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com" \
  -H "Cookie: SESSION=<test-session-id>"
~~~

Và preflight cho request cập nhật:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type, x-csrf-token"
~~~

**Không dùng session ID thật trong lệnh được ghi vào shell history, log hoặc công cụ chia sẻ.** Ví dụ chỉ dùng placeholder/test session. Tên miền `.example` cần thay bằng API kiểm thử thực tế.

`curl` không thực thi SOP/CORS và không tự áp dụng cookie policy của trình duyệt như Fetch. Vì thế curl thấy response thành công **không chứng minh** JavaScript ở origin nào cũng đọc được hoặc cookie sẽ được browser gửi. Trong PowerShell cũ, gọi `curl.exe` nếu `curl` bị ánh xạ tới `Invoke-WebRequest`.

### 12.4. Ví dụ kiểm thử preflight Servlet bằng MockMvc

Một test tích hợp có Spring Security và cấu hình như mục 8:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialCorsPreflightTest {

    @Autowired
    MockMvc mvc;

    @Test
    void permitsTrustedOriginWithoutPreflightCookie() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void rejectsUntrustedOrigin() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }
}
~~~

Bộ test minh họa kiểm tra **preflight không mang cookie**. Để kiểm thử end-to-end với actual request, cần bổ sung ứng dụng có endpoint, cơ chế đăng nhập/session và CSRF token, thực hiện các request tích hợp phù hợp và quan sát hành vi browser thật. Trong WebFlux có thể viết test tương ứng với `WebTestClient`.

Đây là ví dụ có chủ đích để học, **chưa phải test đã được chạy** trên dự án thực.

## 13. Bảng chẩn đoán lỗi credentials và cookie

| Hiện tượng | Nguyên nhân có thể | Kiểm tra hoặc hướng xử lý |
| --- | --- | --- |
| `fetch` trả lỗi CORS dù HTTP 200 | Thiếu `Allow-Credentials: true` hoặc `Allow-Origin` sai | Kiểm tra actual response và Fetch credentials mode |
| Console báo wildcard không được dùng với credentials | `Allow-Origin: *` và `credentials: "include"` | Chỉ trả origin tin cậy cụ thể |
| `GET /api/me` nhận 401 nhưng không thấy cookie | Fetch đang dùng mặc định `same-origin` | Dùng `credentials: "include"` nếu chủ động cho phép gọi cross-origin bằng cookie |
| Đã dùng `include` nhưng vẫn không thấy cookie | Cookie Domain/Path/`Secure`/`SameSite` hoặc third-party policy | Kiểm tra tab Cookies, site/origin, HTTPS và chính sách browser |
| Cross-origin same-site hoạt động, cross-site thất bại | `SameSite=Lax`/`Strict` hoặc cookie bên thứ ba bị chặn | Xác định site; với cross-site kiểm tra `SameSite=None; Secure` và giới hạn browser |
| `OPTIONS` 401 vì không có cookie | Security filter/gateway yêu cầu xác thực preflight | Xử lý CORS trước authentication; xem route OPTIONS |
| OPTIONS 200 nhưng browser không gửi PUT | Thiếu `Allow-Methods`, `Allow-Headers` hoặc `Allow-Credentials` phù hợp | Đối chiếu request preflight và response preflight |
| PUT có cookie nhưng trả 403 | CSRF token thiếu/sai hoặc thiếu quyền | Kiểm tra server log, authorization và CSRF riêng |
| POST/PUT 401 hoặc 403 nhưng JS chỉ thấy lỗi CORS | Actual error response không có CORS header | Bổ sung CORS nhất quán cho response lỗi |
| API trả Set-Cookie nhưng browser không lưu | Fetch credentials mode/cookie policy không cho lưu | Xem lý do cookie bị chặn trong DevTools |
| `response.headers.get("Set-Cookie")` là null | `Set-Cookie` bị cấm đọc từ Fetch | Kiểm tra cookie ở DevTools; không expose `Set-Cookie` để né chính sách |
| Lúc đúng lúc sai sau CDN | Cache không phân biệt origin/user | Kiểm tra `Vary: Origin`, `Cache-Control`, cache cá nhân hóa |
| Chỉ gateway deployment bị lỗi | Gateway chặn OPTIONS hoặc sửa/nhân đôi CORS header | So sánh response tại gateway và ứng dụng |
| `http://app.example.com` không được phép | Allowlist chỉ có `https://app.example.com` | Scheme thuộc origin; kiểm tra origin browser thật |

## 14. Bài tập vận dụng

**Tình huống 1.** Trang `https://app.example.com` gọi `https://api.example.com/api/me`. Cookie của API có `Secure; HttpOnly; SameSite=Lax`. Fetch không ghi `credentials`. Hai host same-site và cookie đang tồn tại; trình duyệt có tự gửi cookie không?

**Đáp án:** Không theo mặc định Fetch của request **khác origin**. Mặc định là `credentials: "same-origin"`. Nếu muốn browser cân nhắc cookie trong request cross-origin, cần `credentials: "include"`; cookie thực tế còn phải qua các điều kiện cookie.

**Tình huống 2.** API trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. Frontend dùng `credentials: "include"`, nhưng cookie bị chặn nên request không có header Cookie. Frontend có đọc được response không?

**Đáp án:** Không. Quy tắc wildcard được đánh giá theo **credentials mode `include`**, không dựa vào việc request thực tế có cookie hay không.

**Tình huống 3.** Frontend và API là hai subdomain HTTPS cùng site. Cookie `SameSite=Lax` có bắt buộc đổi sang `SameSite=None` để call API bằng Fetch không?

**Đáp án:** Không nhất thiết. Cùng site dù khác origin, cookie `SameSite=Lax` có thể được gửi khi các điều kiện khác hợp lệ; Fetch vẫn cần `credentials: "include"` cho request cross-origin.

**Tình huống 4.** API trả `Set-Cookie: SESSION=...; HttpOnly; Secure; SameSite=None`, CORS đúng. Browser vẫn chặn cookie trong một trang bên thứ ba. Có thể khắc phục bằng cách thêm `Access-Control-Allow-Credentials` lần nữa không?

**Đáp án:** Không. Cookie có thể bị chặn bởi third-party-cookie policy/partitioning hoặc thuộc tính cookie/đường dẫn. CORS không vượt qua chính sách quyền riêng tư của browser.

**Tình huống 5.** Preflight OPTIONS của `PUT` được gửi mà không có session cookie; Spring Security trả 401. Có nên đưa cookie vào OPTIONS bằng JavaScript không?

**Đáp án:** Không. Trình duyệt quản lý preflight và thường không gửi credentials của actual request trong preflight. Cần cấu hình xử lý CORS đủ sớm, để preflight được kiểm tra bằng origin/method/header. Authentication/authorization/CSRF dành cho actual PUT.

**Tình huống 6.** CORS credentials hoạt động, nhưng một POST bằng form cross-site vẫn làm đổi dữ liệu trên server. Đây có phải lỗi của `Access-Control-Allow-Origin` không?

**Đáp án:** Không nhất thiết. CORS không phải cơ chế chặn tất cả request cross-site. Cần bảo vệ CSRF và thiết kế session/cookie để request thay đổi trạng thái chỉ được xử lý khi hợp lệ.

**Tình huống 7.** Có thể đặt `Access-Control-Expose-Headers: Set-Cookie` để JavaScript đọc session cookie không?

**Đáp án:** Không. `Set-Cookie` bị browser lọc khỏi các response header mà Fetch cho JavaScript đọc, kể cả khi có Expose-Headers. Session cookie nên được quản lý bởi browser và server, sử dụng `HttpOnly` khi phù hợp.

**Tình huống 8.** Nhóm phát triển thêm `https://*.example` vào `allowedOriginPatterns` và bật `allowCredentials(true)`, vì mọi subdomain đều do công ty sở hữu. Cấu hình đã đủ an toàn chưa?

**Đáp án:** Chưa thể kết luận. Cần xác minh toàn bộ subdomain khớp pattern có thực sự tin cậy hay không, kể cả hosting bên thứ ba, subdomain do user tạo, XSS và DNS bị bỏ quên. Với dữ liệu phiên nhạy cảm, ưu tiên allowlist origin cụ thể.

---

**Ghi nhớ:** Để đọc response cross-origin bằng session cookie, cần đồng thời có **Fetch credentials mode phù hợp**, **cookie được browser cho phép gửi theo chính sách cookie**, và **CORS response chấp nhận origin cụ thể cùng credentials mode**. `Access-Control-Allow-Credentials: true` không tạo cookie; `SameSite=None` không thay thế CORS; wildcard `Access-Control-Allow-Origin: *` không hợp lệ với `credentials: "include"`. Trong Spring Security, hãy cấu hình allowlist tin cậy cho Servlet/Reactive, cho preflight đi qua đúng luồng, và giữ riêng authentication, authorization, CSRF cùng phòng vệ session.
