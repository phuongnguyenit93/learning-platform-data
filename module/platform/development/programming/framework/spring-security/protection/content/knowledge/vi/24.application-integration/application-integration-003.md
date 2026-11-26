# SPA khác origin với CORS và cookie

## Mục tiêu học tập

Sau bài học thuộc chương **Tích hợp ứng dụng**, người học có thể:

- Phân biệt **cross-origin**, **cross-site** và **same-site nhưng cross-origin** khi SPA và Spring Security API chạy ở các hostname, scheme hoặc port khác nhau.
- Giải thích vì sao trình duyệt cần **CORS** để frontend JavaScript đọc response từ API khác origin, nhưng CORS **không thay thế** CSRF token hay authorization.
- Hiểu cách `fetch(..., { credentials: "include" })` phối hợp với cookie `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path`; xác định khi nào browser **thực sự gửi cookie**.
- Phân tích **preflight OPTIONS** và các header `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
- Thiết kế endpoint cấp **CSRF token qua JSON** cho một frontend origin được phép, sử dụng session cookie `HttpOnly` tại API host và gửi token qua HTTP header khi thực hiện POST/PUT/PATCH/DELETE.
- Cấu hình CORS **trước cơ chế xác thực** trong Spring Security **Servlet** và **Reactive/WebFlux** mà không vô tình cho phép mọi website đọc response mang credential.
- Xử lý form login, logout, token hết hiệu lực sau xác thực, phiên hết hạn và trường hợp cookie bên thứ ba bị browser chặn.
- Viết kiểm thử `MockMvc`/`WebTestClient` cho CORS + CSRF và kiểm thử browser end-to-end để phân biệt lỗi preflight, cookie, token, authentication, authorization, CSP và reverse proxy.
- Đánh giá khi nào nên chuyển sang **SPA cùng origin qua reverse proxy** hoặc **Backend for Frontend (BFF)** thay vì cố dùng cookie cross-site trên nhiều browser.

## 1. Tình huống: SPA và API không cùng origin

Giả sử một SPA được phục vụ tại:

~~~text
Frontend: https://spa.example.com
Backend:  https://api.example.com
~~~

Sau khi tải JavaScript, frontend thực hiện:

~~~javascript
const response = await fetch("https://api.example.com/api/me");
~~~

Trình duyệt so sánh **origin của trang hiện tại** với **origin của URL request**:

~~~text
origin = scheme + hostname + port
~~~

Hai URL trên **khác origin** vì hostname khác nhau. Khi frontend muốn đọc response API, **CORS (Cross-Origin Resource Sharing)** là một chính sách browser cần được cấu hình phù hợp ở phía backend. Việc chúng cùng thuộc doanh nghiệp, dùng HTTPS và cùng đăng nhập **không khiến chúng thành same-origin**.

Nếu backend dùng session cookie để xác thực, còn phải xét một chính sách độc lập: browser có **gửi cookie của API** cùng request cross-origin hay không? Và nếu gửi cookie, server có **kiểm tra CSRF token** trên request thay đổi trạng thái hay không?

Ba câu hỏi tách biệt:

1. **Cookie / credential:** Browser có đính kèm cookie phù hợp tới `api.example.com` không?
2. **CORS / đọc response:** JavaScript tại `spa.example.com` có được browser cho phép đọc response do `api.example.com` trả về không?
3. **CSRF / thay đổi trạng thái:** Server có chỉ chấp nhận thao tác ghi nếu request mang token được cấp và kiểm chứng theo đúng phiên/ngữ cảnh không?

> **Nguyên tắc:** CORS là cơ chế kiểm soát tương tác *giữa các origin* do trình duyệt thực thi; SameSite áp dụng cho *cookie* theo quan hệ site; CSRF token là kiểm tra *phía server* khi nhận request có credential. Không một cơ chế nào mặc nhiên thay thế hai cơ chế kia.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, cách phối hợp này là phần của phòng vệ HTTP và browser cùng với CSP, HSTS, security headers, HTTP firewall và bảo vệ session; các nguyên tắc áp dụng cho cả Spring Security **Servlet** và **Reactive**.

### 1.1. Sơ đồ kiến trúc

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser tại spa.example.com
    participant A as Spring API tại api.example.com
    participant S as Session store / Service

    U->>B: Mở SPA qua HTTPS
    B->>A: GET /api/csrf, Origin: spa.example.com
    A->>A: Kiểm tra origin theo CORS allowlist
    A->>S: Tạo hoặc tải session và CSRF token
    A-->>B: JSON token + Set-Cookie + CORS headers
    Note over B: JS đọc JSON nếu CORS cho phép, không đọc cookie HttpOnly
    U->>B: Lưu hồ sơ
    B->>A: OPTIONS /api/profile (CORS preflight)
    A-->>B: Cho phép origin, method, headers
    B->>A: POST + Cookie phiên + X-CSRF-TOKEN
    A->>A: CSRF + Authentication + Authorization
    A->>S: Cập nhật nếu hợp lệ
    A-->>B: 204 No Content + CORS headers
~~~

Sơ đồ mô tả **trường hợp browser thực sự cho phép cookie**. Với SPA và API ở **hai site khác nhau**, việc chặn third-party cookie có thể khiến request không có session cookie dù CORS được cấu hình đúng.

## 2. Phân biệt origin và site trước khi đặt SameSite

### 2.1. Origin: scheme, hostname và port

Ví dụ các cặp URL:

| SPA origin | API URL | Quan hệ origin |
|---|---|---|
| `https://spa.example.com` | `https://api.example.com` | **Cross-origin** do hostname khác |
| `https://app.example.com:443` | `https://app.example.com:8443` | **Cross-origin** do port khác |
| `http://localhost:5173` | `http://localhost:8080` | **Cross-origin** do port khác |
| `https://app.example.com` | `http://app.example.com` | **Cross-origin** do scheme khác |
| `https://app.example.com` | `https://app.example.com/api/profile` | **Same-origin** |

CORS chủ yếu phục vụ kịch bản **JavaScript gọi và đọc response từ origin khác**. Browser tự đặt `Origin` cho những request liên quan; mã JavaScript không được tự tùy ý thay đổi header này như một header ứng dụng thông thường.

### 2.2. Site: scheme và registrable domain

Trong các browser hiện đại sử dụng **schemeful same-site**, một site thường dựa trên:

~~~text
site = scheme + registrable domain
~~~

Registrable domain dựa trên **Public Suffix List**; không nên tự xác định site bằng cách luôn lấy hai nhãn cuối hostname. Port thường **không** làm hai URL trở thành cross-site, còn scheme HTTP/HTTPS có thể làm khác site.

| SPA | API | Origin | Site |
|---|---|---|---|
| `https://spa.example.com` | `https://api.example.com` | Khác | **Cùng site** |
| `https://app.example.com:8443` | `https://api.example.com` | Khác | **Cùng site** |
| `http://spa.example.com` | `https://api.example.com` | Khác | **Khác site** theo schemeful same-site |
| `https://frontend.other.test` | `https://api.example.com` | Khác | **Khác site** |
| `http://localhost:5173` | `http://localhost:8080` | Khác | Thường được browser coi cùng site ở ngữ cảnh localhost tương ứng |

**Phân biệt rất quan trọng:**

- `https://spa.example.com` → `https://api.example.com` **cần CORS**, vì cross-origin.
- Hai host trên có thể là **same-site**, nên cookie `SameSite=Lax` của `api.example.com` **không bị chặn chỉ vì request đến từ SPA khác hostname**.
- `https://frontend.other.test` → `https://api.example.com` vừa **cross-origin vừa cross-site**; cookie `Lax`/`Strict` thông thường **không đi kèm** fetch cross-site. `SameSite=None; Secure` có thể cần thiết nhưng vẫn chịu chính sách chặn cookie bên thứ ba.

### 2.3. Cross-origin không đồng nghĩa third-party cookie

Cookie thuộc `api.example.com` được gửi **đến chính host api.example.com` theo phạm vi cookie. Ở trường hợp SPA cùng site `spa.example.com`, nhiều browser coi request này là first-party/same-site cho chính sách SameSite mặc dù nó cross-origin. Khi SPA ở `frontend.other.test`, cookie API có thể chịu chính sách **third-party cookie**.

Thuật ngữ “first-party/third-party” và chính sách storage/partitioning khác nhau giữa browser; không nên khẳng định mọi browser sẽ xử lý giống nhau. Hãy kiểm thử trên browser mà sản phẩm hỗ trợ.

### 2.4. Một subdomain cùng site không mặc nhiên đáng tin

Nếu `blog.example.com` cho phép nội dung không tin cậy hoặc bị chiếm quyền, nó vẫn có thể **same-site** với `api.example.com`. Cookie `SameSite=Lax` hoặc `Strict` có thể được gửi tới API trong một request được blog kích hoạt.

Tuy nhiên **Same-Origin Policy** thường ngăn blog đọc JSON CSRF token của API nếu CORS **không** cho phép origin blog. Vì vậy CORS allowlist chặt chẽ và CSRF token gắn ngữ cảnh là các lớp quan trọng. **Không dùng `allowedOriginPatterns("*")` hoặc phản chiếu tùy tiện Origin** để tất cả subdomain đều đọc được response kèm cookie.

## 3. CORS thực sự làm những gì?

### 3.1. Browser kiểm tra header của response API

SPA gửi request:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Cookie: JSESSIONID=SESSION_A
~~~

Backend có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://spa.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"username":"alice"}
~~~

Browser chỉ cho JavaScript phía SPA **đọc response** nếu các điều kiện CORS và credential mode tương ứng được đáp ứng. Header `Vary: Origin` giúp cache trung gian phân biệt response tùy theo Origin, nhất là khi server chọn origin được phép theo request.

**CORS không phải cơ chế xác thực user.** Một website được allowlist CORS không tự có quyền đọc tài nguyên mà không có session/token và authorization phù hợp. Ngược lại, nếu CORS cấu hình quá rộng với credential, một website ngoài có thể được phép đọc dữ liệu riêng tư khi browser gửi cookie của API.

### 3.2. Request đơn giản và preflight khác nhau

Một số request **được browser cho phép gửi mà không cần preflight**, ví dụ HTML form truyền thống dùng phương thức/body phù hợp.

Với JavaScript gọi cross-origin có **custom header** như `X-CSRF-TOKEN` hoặc `Content-Type: application/json`, browser thường phát một request **CORS preflight** bằng `OPTIONS` trước:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight trả chính sách cho phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://spa.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Nếu preflight hợp lệ, browser mới gửi request thực:

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: TOKEN_CUA_PHIEN_A

{"displayName":"Alice New"}
~~~

**Không xem OPTIONS là một thao tác nghiệp vụ cần user đã đăng nhập.** CORS preflight thường **không mang cookie/session credential** của request thực, nên nếu Spring Security yêu cầu authentication trước khi xử lý CORS, preflight có thể trả `401`/redirect và browser không gửi POST.

Spring Security cần tích hợp **CORS trước bước kiểm tra security session/authorization** cho request preflight tương ứng.

### 3.3. Preflight thành công không chứng minh CSRF token hợp lệ

CORS preflight chỉ hỏi: *Origin này có được phép gửi một request POST với những header này không?*

Nó **không** gửi giá trị CSRF token thực tế và không kiểm tra token. Sau khi preflight được phép, request POST vẫn phải qua `CsrfFilter`/`CsrfWebFilter`; token thiếu/sai sẽ bị từ chối.

### 3.4. CORS không ngăn mọi request gây tác động

Một trang khác origin có thể tạo form:

~~~html
<!-- Ví dụ mô hình rủi ro trong môi trường thử nghiệm. -->
<form method="post" action="https://api.example.com/api/profile">
  <input type="hidden" name="displayName" value="Unwanted">
</form>
~~~

Form POST có thể được browser **gửi** không cần CORS cho phép trang nguồn đọc response. Nếu cookie auth được gửi và backend chấp nhận body/method, server có thể đã cập nhật dữ liệu trước khi browser hạn chế response.

**Do đó:** Không sử dụng “CORS chỉ cho phép SPA của chúng ta” làm lý do tắt CSRF ở API sử dụng cookie tự gửi.

### 3.5. Cookie có được gửi không còn phụ thuộc fetch credentials

Mặc định thông dụng của `fetch` là `credentials: "same-origin"`. Khi gọi **cross-origin**, browser không tự gửi cookie theo chế độ mặc định này dù cookie có `SameSite=Lax` và là same-site.

SPA phải chủ động dùng:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

`credentials: "include"` chỉ **cho phép browser cân nhắc gửi cookie** và xử lý credentials trên response, chứ không vượt `SameSite`, `Secure`, `Domain`, `Path`, third-party cookie blocking hoặc các chính sách storage khác.

**Không** dùng `mode: "no-cors"` như “cách chữa CORS”. Nó khiến response thường **opaque** đối với JavaScript và không cấp quyền đọc JSON/API; nó cũng không tạo cơ chế bảo vệ CSRF.

## 4. Quy tắc CORS khi dùng cookie

### 4.1. Chỉ allowlist origin được kiểm soát

Đối với frontend `https://spa.example.com`, API chỉ nên cho phép những origin **thực sự cần và tin cậy**, ví dụ chính SPA này:

~~~http
Access-Control-Allow-Origin: https://spa.example.com
Access-Control-Allow-Credentials: true
~~~

**Không dùng**:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser không chấp nhận wildcard `*` là allowed origin cho **credentialed CORS response**. Và dù framework cố ghép header này, đó cũng không phải một thiết kế bảo mật tốt.

**Cũng không làm:**

~~~text
Origin request: https://random-attacker.test
Access-Control-Allow-Origin: https://random-attacker.test
Access-Control-Allow-Credentials: true
~~~

nếu server đang **phản chiếu mọi Origin mà không xác minh allowlist**. Khi browser gửi cookie được phép, attacker origin có thể đọc dữ liệu của user từ API qua CORS cấu hình sai.

### 4.2. Chỉ cho phép phương thức và header cần dùng

Một SPA dùng REST JSON và CSRF header có thể cần:

~~~text
Allowed origins:  https://spa.example.com
Allowed methods:  GET, POST, PUT, PATCH, DELETE, OPTIONS
Allowed headers:  Content-Type, X-CSRF-TOKEN
Allow credentials: true
Max age:          1800 giây (ví dụ)
~~~

Nếu frontend gửi header `X-XSRF-TOKEN` với cookie CSRF repository, cấu hình phải cho phép header tương ứng. Nếu có `Authorization`, cần đánh giá luồng Bearer và chỉ thêm nó khi API thực sự sử dụng.

**Giới hạn:** CORS allowed methods/headers không phải một rule authorization nghiệp vụ. Backend vẫn phải kiểm tra method, quyền, CSRF token và input.

### 4.3. Vary: Origin để tránh lỗi cache

Khi API phục vụ nhiều origin được phép và response CORS thay đổi theo Origin, hãy bảo đảm response có `Vary: Origin`. Preflight có thể cần phân biệt thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers`.

Đối với response có dữ liệu cá nhân hoặc CSRF token, nên đặt `Cache-Control: no-store` hoặc policy không cho cache chia sẻ tùy ứng dụng; **Vary một mình không làm response riêng tư an toàn để cache công khai**.

### 4.4. Origin phải khớp chính xác scheme, host và port

Một allowlist `https://spa.example.com` không tự cho phép:

- `http://spa.example.com` (khác scheme);
- `https://spa.example.com:8443` (khác port);
- `https://preview.spa.example.com` (khác host);
- `https://evilspa.example.com` (không phải subdomain hợp lệ được tin cậy);
- `https://another.example.com` (dù cùng site).

Có thể dùng danh sách nhiều origin **cụ thể** nếu sản phẩm có các frontend khác nhau. Với preview deployments động, `allowedOriginPatterns` chỉ nên được dùng khi pattern **chặt chẽ và có kiểm soát sở hữu domain**; đừng cho phép mọi origin/cổng để tránh lỗi dev tạm thời.

## 5. Cookie API trong SPA khác origin

### 5.1. Cookie phiên HttpOnly nên thuộc API host

Ví dụ API phát:

~~~http
Set-Cookie: JSESSIONID=random-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không khai báo `Domain` giúp cookie **host-only** cho `api.example.com`, nếu response được gửi từ API host đó. Khi SPA tại `spa.example.com` gọi `https://api.example.com/api/me` với `credentials: "include"`, browser có thể gửi cookie **đến api.example.com** nếu cookie policy cho phép.

SPA **không cần** đọc `JSESSIONID` bằng `document.cookie`. Cũng không nên mở `HttpOnly=false` cho session cookie chỉ vì frontend ở hostname khác. Backend dựa trên cookie browser tự gửi, còn JavaScript dựa trên endpoint `/api/me` để biết trạng thái xác thực.

### 5.2. Vì sao frontend không đọc được cookie host-only của API?

JavaScript chạy tại `spa.example.com` không thể đọc một cookie **host-only** của `api.example.com` bằng `document.cookie`. Đây là ranh giới bình thường, không phải lỗi cấu hình.

Browser vẫn có thể gửi cookie của API **đến API host** khi request có `credentials: "include"` và đủ các điều kiện cookie policy. Cần phân biệt:

- **Đọc cookie bằng JS trên SPA origin:** Thường không thể với API host-only cookie.
- **Browser đính kèm cookie khi request tới API origin:** Có thể, tùy credentials mode và cookie policy.
- **Đọc JSON response từ API:** Cần API trả CORS headers cho đúng Origin và credentials.
- **CSRF token:** Có thể cấp riêng bằng JSON response qua CORS cho frontend tin cậy; không cần đọc session ID.

### 5.3. Cookie SameSite cho hai kiến trúc

| Mô hình | Ví dụ | SameSite cho cookie API | Lưu ý |
|---|---|---|---|
| **Cross-origin, same-site** | `https://spa.example.com` → `https://api.example.com` | `Lax` hoặc `Strict` có thể cho cookie trong request same-site | Vẫn cần `credentials: "include"` và credentialed CORS |
| **Cross-origin, cross-site** | `https://frontend.other.test` → `https://api.example.com` | `Lax`/`Strict` thường không gửi cho cross-site fetch; `None; Secure` có thể cần | Third-party cookie restrictions có thể ngăn dù dùng None |
| **Same-origin qua proxy** | `https://app.example.com` → `https://app.example.com/api` | `Lax` phù hợp với nhiều web flows | Thường không cần CORS trong fetch cùng origin |
| **Local dev khác port** | `http://localhost:5173` → `http://localhost:8080` | Thường same-site về hostname/scheme, nhưng khác origin | Cookie Secure/localhost exceptions có khác biệt browser; không thay test HTTPS production |

Cookie `SameSite=None` trong browser hiện đại cần `Secure`, nhưng **không bảo đảm** third-party cookies luôn được chấp nhận. Phải kiểm tra browser support và mục tiêu sản phẩm.

### 5.4. Cookie Domain rộng có thể làm tăng rủi ro

Không tự đặt `Domain=example.com` chỉ để SPA đọc một cookie của API. Việc mở rộng domain cho phép cookie được gửi tới nhiều subdomain và có thể tăng khả năng **cookie injection**, cookie trùng tên hoặc pha trộn ranh giới tin cậy.

Với session cookie, ưu tiên host-only khi kiến trúc cho phép; cân nhắc tiền tố `__Host-` (đòi `Secure`, `Path=/`, không `Domain` trong browser hỗ trợ). Nếu SPA cần CSRF token, hãy cấp qua **API JSON CORS được kiểm soát** thay vì nới rộng quyền đọc session cookie.

### 5.5. Third-party cookie blocking và các cơ chế mới

Khi SPA và API **khác site**, các browser có thể chặn hoặc phân vùng third-party cookies, thay đổi hành vi theo phiên bản, chính sách người dùng và môi trường enterprise.

Một số công nghệ như **partitioned cookies (CHIPS)** hoặc **Storage Access API** có thể hỗ trợ những ngữ cảnh cụ thể, nhưng không phải cách thay thế phổ quát cho session cross-site truyền thống. Cookie phân vùng theo top-level site có **ngữ nghĩa phiên khác** cookie không phân vùng; cần thiết kế và kiểm thử riêng.

Nếu ứng dụng cần hỗ trợ rộng trên nhiều browser, có thể cân nhắc **reverse proxy cùng origin** hoặc **BFF** để tránh phụ thuộc vào việc browser chấp nhận cookie third-party. Đừng “khắc phục” bằng cách tắt CSRF hoặc mở credentialed CORS cho tất cả origin.

## 6. Tích hợp CSRF khi SPA đọc API ở origin khác

### 6.1. Vì sao ứng dụng có cookie phiên cần CSRF?

Giả sử backend xác thực user dựa trên cookie `JSESSIONID` được browser tự gửi. Ngay cả khi API chỉ cho phép `https://spa.example.com` đọc response bằng CORS, một website ngoài có thể kích hoạt một số request qua form/điều hướng mà không đọc response.

**CSRF token** buộc request ghi mang một giá trị được ứng dụng hợp lệ lấy từ nguồn mà attacker khác origin **thường không đọc được**, rồi chủ động gửi qua form field hoặc header. Trong luồng SPA khác origin:

1. Browser gửi `GET https://api.example.com/api/csrf` với `credentials: "include"`.
2. API trả JSON có tên header và token được phát cho **phiên hiện tại**, kèm CORS headers chỉ cho `https://spa.example.com`.
3. SPA đọc JSON sau khi browser xác minh CORS và giữ token trong memory.
4. Với POST/PUT/PATCH/DELETE, SPA gửi **CSRF header** cùng request và cho browser tự gửi cookie phiên.
5. `CsrfFilter` hoặc `CsrfWebFilter` đối chiếu submitted token với expected token theo repository/request handler.
6. Nếu token thiếu/sai, server từ chối **trước khi thao tác nghiệp vụ được commit**.

~~~mermaid
flowchart TD
    A[SPA tải trên spa.example.com] --> B[GET api.example.com/api/csrf, credentials include]
    B --> C{Browser có gửi/nhận session cookie?}
    C -->|Có và CORS hợp lệ| D[SPA đọc JSON token được cấp]
    C -->|Cookie bị chặn| E[Xử lý cookie/session policy hoặc đổi kiến trúc]
    D --> F[POST /api/profile có X-CSRF-TOKEN]
    F --> G{CORS preflight cho phép?}
    G -->|Không| H[Browser không gửi actual request]
    G -->|Có| I[POST đến Spring API với cookie theo policy]
    I --> J{Cookie/auth và CSRF token đúng?}
    J -->|Không| K[401, 403 hoặc policy khác; không ghi dữ liệu]
    J -->|Có| L[Authorization + validation nghiệp vụ]
    L --> M[Thực hiện cập nhật và trả response]
~~~

Sơ đồ lý tưởng hóa cookie/preflight; **CORS, authentication, authorization và CSRF có nguyên nhân lỗi riêng**, không nên tự đồng nhất mọi status `403` với CSRF.

### 6.2. API cấp token không được mở credentialed CORS cho mọi website

Một endpoint `GET /api/csrf` có thể cần truy cập trước login để lấy token cho `POST /api/login`. Việc endpoint **permitAll** không đồng nghĩa cho mọi origin đọc token của phiên.

Một thiết kế an toàn hơn:

- Chỉ cho **SPA origin đáng tin** đọc token qua CORS.
- Gửi `Cache-Control: no-store`; không để CDN cache token theo user.
- Không ghi token/session ID vào URL, log hay analytics.
- Token phải được repository/request handler thật của Spring Security phát, **không hardcode**.
- Khi user login/logout hoặc session timeout, frontend cập nhật token phù hợp với phiên mới.
- Bảo vệ chống **XSS tại SPA origin**: nếu attacker chạy JavaScript trong origin được CORS allowlist, họ có thể đọc token hợp lệ và gọi API như script frontend.

### 6.3. Vì sao nên cấp token qua JSON thay vì cố đọc cookie của API?

Khi SPA ở `spa.example.com` và API ở `api.example.com`:

- Cookie session **host-only của API** nên là `HttpOnly` và **không đọc được từ JS của SPA**.
- Nếu dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` và cookie `XSRF-TOKEN` chỉ thuộc host API, **JS tại SPA không tự đọc được cookie đó**.
- Có thể cố chia sẻ cookie CSRF qua `Domain=example.com` để JS đọc nhưng điều này mở rộng phạm vi cookie và nguy cơ cookie injection/tấn công từ sibling subdomain.
- Endpoint **JSON token qua CORS allowlist chặt chẽ** giúp SPA nhận token mà không cần nới rộng phạm vi session cookie hay cookie CSRF.

Vì vậy luồng chính của bài sử dụng **synchronizer token trong HttpSession/WebSession**, công bố token qua JSON cho origin được phép. Mô hình cookie CSRF vẫn hữu ích trong kiến trúc khác nhưng cần đánh giá riêng.

### 6.4. Token masked, deferred và raw token

Spring Security Servlet hiện đại có thể dùng `XorCsrfTokenRequestAttributeHandler`, trả biểu diễn token **XOR-masked** khi render/truy xuất cho response để giảm một số rủi ro nén như BREACH.

~~~text
Raw expected token theo session A: R
GET /api/csrf lần 1 -> submitted token M1 = mask(R, random1)
GET /api/csrf lần 2 -> submitted token M2 = mask(R, random2)

M1 có thể khác M2.
Handler giải mã submitted M1/M2 và so với R.
~~~

Bài test nên dùng **giá trị endpoint thực sự trả** và headerName tương ứng, không đòi token JSON phải giống raw token trong session.

Với deferred token, chỉ tải SPA tĩnh không nhất thiết tạo token; endpoint `GET /api/csrf` cần **truy cập token** để khởi tạo/lấy token khi cần. Với WebFlux, publisher `Mono<CsrfToken>` phải được subscribe qua reactive pipeline.

Khi chọn cookie CSRF + SPA đọc **raw token** và gửi header `X-XSRF-TOKEN`, một handler chỉ giải mã token XOR có thể không tương thích. Hãy chọn request handler phù hợp với luồng raw/masked của phiên bản đang dùng thay vì tắt CSRF.

## 7. Servlet: cấu hình Spring Security CORS và session đúng thứ tự

### 7.1. CORS configuration source có allowlist rõ ràng

Ví dụ dưới đây dùng **Spring MVC/Servlet**, không phải các class `org.springframework.web.cors.reactive.*` của WebFlux.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chính xác scheme + hostname + port của SPA production.
        cors.setAllowedOrigins(List.of("https://spa.example.com"));

        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));

        // Chỉ các header mà SPA thực sự cần gửi.
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));

        // Cho browser dùng cookie trong cross-origin fetch.
        cors.setAllowCredentials(true);

        // Browser cache kết quả preflight theo chính sách của nó.
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Kết hợp `CorsConfigurationSource` với Spring Security bảo đảm CORS được xét trước các bước bảo vệ đòi credential khi đúng chain được chọn.

**Không** cấu hình CORS `allowedOrigins("*")` khi `allowCredentials(true)`, hoặc dùng `allowedOriginPatterns("*")` để “giải quyết lỗi” mà không kiểm soát origin. `setMaxAge` chỉ là thời gian cache **preflight permission**, không phải thời gian sống session cookie hay CSRF token.

Nếu production có nhiều SPA origins do chính tổ chức quản lý, liệt kê rõ từng origin. Origin preview động chỉ được cho phép nếu **mẫu domain đảm bảo quyền sở hữu/tin cậy** và đã phân tích XSS/rò rỉ token qua CORS.

### 7.2. Cấu hình SecurityFilterChain giữ CSRF cho POST

Đây là ví dụ cho API **dùng HttpSession cookie**, form login do Spring Security xử lý và frontend mong đợi JSON/status thay vì redirect HTML.

~~~java
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class ServletApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            // Xử lý CORS cả ở preflight không kèm session cookie.
            .cors(Customizer.withDefaults())

            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )

            .formLogin(form -> form
                .loginProcessingUrl("/api/login")
                .successHandler((request, response, authentication) ->
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT))
                .failureHandler((request, response, exception) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
            )

            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT))
            )

            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
            )

            // Giữ CSRF cho POST/PUT/PATCH/DELETE có cookie session.
            .csrf(csrf -> csrf.csrfTokenRepository(
                new HttpSessionCsrfTokenRepository()
            ))

            .build();
    }
}
~~~

**Điều kiện của ví dụ:**

- Class `ServletCorsConfig` ở mục 7.1 và class `ServletApiSecurityConfig` cùng thuộc **một cấu hình Servlet**, không tạo ra hai `SecurityFilterChain` vô ý cạnh tranh.
- Project cần Spring Security Web/Servlet, cấu hình authentication provider/user store thực tế và controller nghiệp vụ.
- `.cors(Customizer.withDefaults())` tìm `CorsConfigurationSource` phù hợp. Với nhiều CORS sources hoặc cấu hình tùy chỉnh, **chỉ rõ source cho chain** thay vì dựa vào tự động chọn.
- `/api/login` **permitAll không miễn CSRF**. Spring Security form-login filter nhận **form-urlencoded** `username`/`password` theo mặc định; JSON login đòi converter/filter tùy chỉnh.
- Khi logout được bảo vệ bởi CSRF, request POST `/api/logout` phải có token.
- `204 No Content` được dùng làm response contract cho frontend. Một triển khai OAuth2/OIDC hoặc flow redirect khác cần hợp đồng riêng, không tự áp response 204.
- `HttpStatusEntryPoint(401)` làm API thiếu authentication có response dễ xử lý hơn redirect login; còn `403` có thể do CSRF hoặc thiếu quyền. Nếu hệ thống vừa phục vụ HTML MVC vừa API, cần matcher/entrypoint phân biệt thay vì đặt chung cho toàn bộ web.
- Không dùng `csrf.disable()` chỉ vì ứng dụng gọi API bằng JSON, hoặc vì CORS đã cấu hình.

### 7.3. Cookie Spring Boot ở phía Servlet API

Một ứng dụng production được browser gọi trực tiếp qua HTTPS public API hostname:

~~~yaml
# application.yml (Servlet)
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Cấu hình `same-site: lax` phù hợp cho ví dụ **same-site cross-origin** `spa.example.com` → `api.example.com` với HTTPS, nếu cookie policy cho phép. Khi frontend/API khác cả site, `lax` thường không được gửi trong cross-site fetch; `none` đi kèm `secure: true` có thể cần:

~~~yaml
# Chỉ xét trong kiến trúc thật sự cần cross-site cookie.
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: none
~~~

**Không coi đây là một giải pháp chắc chắn** khi browser chặn third-party cookie. Trong hệ thống dùng Spring Session hoặc custom cookie serializer, cookie thực có thể được phát bởi cơ chế riêng; kiểm tra response `Set-Cookie` trong Network thay vì chỉ đọc YAML.

Tại đây **không đặt `Domain=example.com`**: session cookie host-only của API là đủ để browser gửi đến API host. Nếu dùng HTTPS reverse proxy, cần cấu hình trusted forwarded headers/host ở biên phù hợp; không mặc định chấp nhận header `X-Forwarded-*` từ Internet.

### 7.4. Servlet GET /api/csrf trả JSON, không cache

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletCsrfApi {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken csrfToken) {
        // Truy cập token để xử lý deferred loading.
        String submittedToken = csrfToken.getToken();

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrfToken.getHeaderName(),
                "parameterName", csrfToken.getParameterName(),
                "token", submittedToken
            ));
    }
}
~~~

GET này có thể được gọi **trước login**. Khi đó token được phát trong ngữ cảnh phiên ẩn danh dùng để bảo vệ `POST /api/login`. Sau authentication thành công, token có thể bị invalidated; frontend cần tải lại token.

Phản hồi mẫu khi browser cho phép cookie:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://spa.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax

{"headerName":"X-CSRF-TOKEN","parameterName":"_csrf","token":"SUBMITTED_VALUE"}
~~~

`Set-Cookie` chỉ xuất hiện khi một cookie được tạo/đổi; browser không đòi mỗi response đều phải có nó. `SUBMITTED_VALUE` là ví dụ biểu diễn token từ handler, **không phải bí mật để hardcode**. Không bật cache công khai cho endpoint này.

### 7.5. Servlet API /api/me và POST /api/profile

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class ServletProfileApi {

    private final ProfileService profiles;

    ServletProfileApi(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/me")
    Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }

    record UpdateProfile(String displayName) {}

    @PostMapping("/api/profile")
    ResponseEntity<Void> update(
            Principal principal,
            @RequestBody UpdateProfile input) {

        String name = input.displayName();

        if (name == null || name.isBlank() || name.length() > 80) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Tên không hợp lệ");
        }

        // Service phải kiểm tra quyền theo user/tài nguyên.
        profiles.renameIfAuthorized(principal.getName(), name);
        return ResponseEntity.noContent().build();
    }
}
~~~

`ProfileService` là **service giả định cần tự triển khai**, không phải API có sẵn của Spring. Trong ứng dụng thật phải bổ sung persistence/transaction, input validation, authorization theo tài nguyên và audit. Request POST phải qua CSRF filter **trước khi** tới controller.

### 7.6. Đừng dùng JWT-in-cookie để miễn CSRF

Nếu đội ngũ chuyển từ `JSESSIONID` sang JWT access token trong cookie:

~~~http
Set-Cookie: ACCESS_TOKEN=jwt; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

browser vẫn **tự đính kèm cookie** trong những request phù hợp. JWT có chữ ký và backend không lưu phiên **không làm biến mất nguy cơ CSRF**. Cần đánh giá cơ chế token/defense cho những request ghi theo đường xác thực cookie.

Khác với trường hợp API **chỉ nhận Bearer header do JS chủ động gắn** và không có bất kỳ cookie/HTTP Basic/BFF session fallback. Không được suy diễn “đang dùng SPA và JWT” là đủ để tắt CSRF.

## 8. SPA JavaScript: credentials include và CSRF header

### 8.1. Một helper cross-origin có kiểm tra origin đích

Đối với các ví dụ cùng site cross-origin:

~~~javascript
// api-client.js — SPA đang chạy tại https://spa.example.com.
const API_ORIGIN = "https://api.example.com";

// Token do API cấp cho phiên hiện hành; không đưa vào URL hoặc log.
let csrfState = null;

function apiUrl(path) {
  if (typeof path !== "string" || !path.startsWith("/api/")) {
    throw new Error("API path phải bắt đầu bằng /api/");
  }

  const url = new URL(path, API_ORIGIN);

  // Tránh vô tình đưa cookie/token tới URL ngoài API đã chọn.
  if (url.origin !== API_ORIGIN
      || !url.pathname.startsWith("/api/")) {
    throw new Error("API URL không được phép");
  }

  return url.toString();
}

async function loadCsrfToken() {
  const response = await fetch(apiUrl("/api/csrf"), {
    method: "GET",
    mode: "cors",
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("GET CSRF token thất bại: " + response.status);
  }

  const result = await response.json();

  if (!result.token || result.headerName !== "X-CSRF-TOKEN") {
    throw new Error("CSRF response không phù hợp cấu hình SPA");
  }

  csrfState = {
    token: result.token,
    headerName: result.headerName
  };

  return csrfState;
}

async function apiFetch(path, options = {}) {
  const method = (options.method ?? "GET").toUpperCase();
  const safeMethods = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
  const headers = new Headers(options.headers ?? {});

  if (!safeMethods.has(method)) {
    if (!csrfState) {
      await loadCsrfToken();
    }

    headers.set(csrfState.headerName, csrfState.token);
  }

  return fetch(apiUrl(path), {
    ...options,
    method,
    mode: "cors",
    credentials: "include",
    headers
  });
}

function clearCsrfState() {
  csrfState = null;
}
~~~

**Giới hạn của helper:**

- Nó mô tả API session-cookie. Với Bearer-only API, credential flow khác.
- Khi gọi POST với `X-CSRF-TOKEN`, browser sẽ preflight vì đây là header không thuộc safelist; server phải cho đúng method/header/origin.
- Không lưu session ID vào JS; cookie `HttpOnly` do browser quản lý.
- Không dùng `mode: "no-cors"` để né lỗi; client cần đọc JSON và status.
- Không tự retry POST bất kỳ khi `403`, nhất là giao dịch không idempotent; có thể là lỗi CSRF hoặc authorization.
- Đường dẫn được giới hạn đến đúng API origin; không dùng URL do người dùng cung cấp mà chưa kiểm soát.
- Một script XSS chạy tại **SPA origin được CORS cho phép** có thể đọc token và gọi API. Phải kết hợp chống XSS, CSP và kiểm soát script.

### 8.2. Login qua form POST nhưng UI là SPA

Nếu server dùng Spring Security `formLogin` như mục 7.2, browser gửi body dạng form-urlencoded:

~~~javascript
async function login(username, password) {
  // Token được cấp cho ngữ cảnh trước login.
  await loadCsrfToken();

  const form = new URLSearchParams({ username, password });

  const response = await apiFetch("/api/login", {
    method: "POST",
    body: form
  });

  if (response.status !== 204) {
    throw new Error("Login thất bại: HTTP " + response.status);
  }

  // Authentication có thể invalidated token trước login.
  clearCsrfState();
  await loadCsrfToken();

  return readCurrentUser();
}

async function readCurrentUser() {
  const response = await apiFetch("/api/me", { method: "GET" });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Không đọc được user: HTTP " + response.status);
  }

  return response.json();
}
~~~

`URLSearchParams` dùng làm `fetch` body thường được browser gắn `Content-Type: application/x-www-form-urlencoded;charset=UTF-8` phù hợp form login.

Cần lưu ý một điểm đặc thù **cross-origin**: form POST có **custom CSRF header**, nên browser có thể gửi **OPTIONS preflight trước POST**, dù content type form-urlencoded là đơn giản. Preflight **không kèm cookie phiên**, nhưng CORS phải cho header và method.

Nếu login trả `204` mà `GET /api/me` sau đó vẫn `401`, phải xác định cookie login có được browser nhận và gửi lại hay không, session store có hoạt động và frontend/backend thực sự cùng site hay không. Đừng tắt CSRF chỉ để chữa `401`.

### 8.3. POST JSON cập nhật hồ sơ

~~~javascript
async function renameProfile(displayName) {
  const response = await apiFetch("/api/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName })
  });

  if (response.status === 401) {
    throw new Error("Chưa đăng nhập hoặc phiên đã hết hạn");
  }

  if (response.status === 403) {
    throw new Error("Bị từ chối: kiểm tra CSRF token và quyền");
  }

  if (!response.ok) {
    throw new Error("Không cập nhật được: HTTP " + response.status);
  }
}
~~~

JSON body và `X-CSRF-TOKEN` cần preflight trong ngữ cảnh cross-origin. Trong một phiên đã xác thực, server phải trả `403` khi POST không có hoặc có CSRF token sai **nếu request thuộc phạm vi bảo vệ**, dù CORS trả header hợp lệ.

### 8.4. Logout qua POST có CSRF token

~~~javascript
async function logout() {
  const response = await apiFetch("/api/logout", {
    method: "POST"
  });

  if (!response.ok) {
    throw new Error("Logout thất bại: HTTP " + response.status);
  }

  clearCsrfState();

  // Lấy token mới nếu SPA tiếp tục ở trang login cần POST sau logout.
  await loadCsrfToken();
}
~~~

Không thiết kế `GET /api/logout` để thực hiện logout ngay: một top-level GET cross-site có thể mang cookie `SameSite=Lax`, khiến ứng dụng chịu logout CSRF.

### 8.5. Vòng đời SPA: loading, 401, 403 và expired session

Trình tự startup điển hình:

~~~text
SPA load
  -> GET /api/csrf (credentials include, CORS)
  -> GET /api/me
      -> 200: hiển thị user
      -> 401: hiển thị form login
  -> POST /api/login với CSRF trước login
      -> success: tải CSRF token mới rồi GET /api/me
  -> POST /api/profile với CSRF hiện hành
  -> POST /api/logout với CSRF hiện hành
      -> success: xóa state UI và lấy token ẩn danh nếu cần
~~~

Trong browser có thể xuất hiện **CORS error** trước khi JavaScript thấy HTTP status; đó thường là dấu hiệu preflight/headers/policy, khác với một response HTTP `401`/`403` đã được browser cho phép JS đọc.

### 8.6. Không giả định cookie có vì fetch thành công

`fetch(..., {credentials:"include"})` và CORS được cấu hình đúng **không bảo đảm cookie được gửi**. Với cross-site cookie, browser có thể chặn third-party cookie:

- `GET /api/csrf` có thể tạo session A nhưng cookie không được giữ;
- `POST /api/login` đến như một phiên khác hoặc không mang pre-auth session cookie;
- CSRF token theo session A bị từ chối vì server nhận phiên B/không có phiên;
- `GET /api/me` tiếp tục trả 401 dù frontend thấy status login hợp lý ở một bước.

**Cách xử lý đúng:** Chẩn đoán Cookie/Set-Cookie và chính sách browser, rồi đánh giá lại kiến trúc. Không chỉ tăng CORS permission hoặc tắt CSRF.

## 9. Login, logout và session lifecycle trong kiến trúc cross-origin

### 9.1. Cần bảo vệ POST login trước authentication

Login CSRF có thể ép browser đăng nhập vào tài khoản attacker hoặc thay trạng thái phiên theo cách không mong muốn. Vì vậy `POST /api/login` **không nên được miễn CSRF chỉ vì user chưa xác thực**.

Khi frontend cần token trước login, `GET /api/csrf` có thể tạo pre-authentication session. Browser cần giữ cookie đó giữa GET và POST, nên CORS credentials và cookie policy phải hoạt động **trước khi người dùng đăng nhập**.

### 9.2. Session fixation và đổi token sau login

Sau authentication thành công, Spring Security có cơ chế chống session fixation phù hợp; session ID có thể thay đổi. Một số cơ chế xóa/refresh expected CSRF token ở ranh giới login/logout.

Vì vậy token trước login **có thể không còn hợp lệ** sau login. SPA nên gọi lại endpoint cấp token và cập nhật state cho session mới.

Không gửi session ID trong URL, hidden field hoặc localStorage để “đồng bộ” với frontend. Browser tự gửi cookie; server quản lý phiên và token theo repository.

### 9.3. Post-logout và những tab còn mở

Một tab logout có thể làm session cookie/token cũ không còn hợp lệ, còn tab khác vẫn giữ UI trước logout. Request tiếp theo từ tab cũ có thể trả `401`/`403`.

Cách xử lý UX là xóa state, thông báo phiên đã kết thúc và yêu cầu login lại, không bỏ qua token cũ hoặc tắt CSRF cho tab còn mở.

### 9.4. OAuth2/OIDC, SSO và callback

Một SPA có thể đăng nhập qua Identity Provider ngoài site. Khi đó cần phân biệt:

- **CORS** cho các API gọi bằng JavaScript;
- **Cookie SameSite** của phiên dùng lưu authorization request/state trong browser redirect;
- **OAuth `state`, PKCE và nonce** (tùy flow) bảo vệ luồng đăng nhập;
- **CSRF token** cho các POST nghiệp vụ dùng cookie phiên sau login.

Nếu sử dụng callback **form_post** cross-site, cookie `SameSite=Lax` có thể không được gửi trong POST callback. Không mở tất cả cookie thành `None` hoặc tắt CSRF mà không phân tích kỹ luồng. Có thể cần cơ chế lưu trạng thái đăng nhập khác hoặc architecture cụ thể.

## 10. Lưu ý khi dùng CookieCsrfTokenRepository ở SPA khác origin

Một số SPA framework quen mô hình:

~~~http
Set-Cookie: XSRF-TOKEN=raw-token; Path=/; Secure; SameSite=Lax
~~~

Client đọc `XSRF-TOKEN` qua `document.cookie` rồi gửi `X-XSRF-TOKEN`. Cách này **không tự hoạt động** với hai hostname host-only khác nhau:

~~~text
SPA JavaScript ở spa.example.com
Cookie XSRF-TOKEN host-only tại api.example.com
=> JS ở spa.example.com không đọc được cookie của api.example.com
~~~

Các lựa chọn:

1. **Ưu tiên luồng JSON**: GET `https://api.example.com/api/csrf` qua CORS credentials, nhận token trong JSON và gửi header; session cookie vẫn host-only/HttpOnly.
2. **Có chủ đích chia sẻ cookie CSRF qua registrable domain**: cần phân tích nguy cơ sibling subdomain, cookie injection, duplicate cookie và request handler raw/masked; **không chia sẻ session ID** cho frontend JS.
3. **Chuyển thành same-origin qua proxy**: frontend và API xuất hiện trên một host, cookie/token transport đơn giản hơn.
4. **BFF**: browser giao tiếp với BFF theo cookie session cùng origin; BFF gọi resource API bằng credential ở server, bảo vệ CSRF trên browser→BFF.

**Không giả định** `CookieCsrfTokenRepository` mặc định đã thực hiện biến thể signed double-submit HMAC gắn phiên. Nếu yêu cầu signed double-submit, cần thiết kế/kiểm chứng chữ ký, ngữ cảnh phiên và cookie scope đúng.

## 11. CSP, HSTS và bảo mật hai origin

### 11.1. CSP cần khai báo connect-src cho API origin

CSP được gửi trên **HTML của SPA** ở `https://spa.example.com`, ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

`connect-src` giúp browser giới hạn các đích kết nối mà JavaScript của SPA được phép gọi. Nhưng **CSP không thay CORS**: API vẫn phải cho phép đúng SPA origin qua CORS nếu frontend cần đọc response.

Một số frontend dùng analytics, WebSocket, font, CDN hoặc inline script; CSP production phải được thiết kế theo các tài nguyên thực tế. Chính sách minh họa không phải cấu hình tối ưu cho mọi build. Xem xét nonce/hash, Trusted Types và loại bỏ DOM sinks nguy hiểm để giảm nguy cơ XSS.

### 11.2. HSTS và HTTPS trên cả SPA lẫn API

SPA và API có **hai host**; cần đảm bảo HTTPS/chứng chỉ hợp lệ cho cả hai. HSTS được browser nhận theo từng host và chính sách; cân nhắc `includeSubDomains`/preload rất thận trọng.

Nếu SPA dùng HTTPS nhưng API là HTTP, browser có thể chặn mixed content và cookie `Secure` không hoạt động như dự kiến. Không “sửa” bằng cách tắt Secure cho production.

### 11.3. Reverse proxy, forwarding headers và cookie scope

Nếu API chạy phía sau gateway HTTPS:

~~~text
Browser --HTTPS--> api.example.com (proxy)
                            |
                            +--HTTP nội bộ--> Spring API
~~~

Backend có thể cần trusted `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host` để tạo redirect và cookie đúng public scheme/host. Không cho client Internet truy cập trực tiếp upstream hoặc giả mạo forwarded headers.

Khi CORS allowlist dùng `https://spa.example.com`, hãy xác minh API nhận đúng `Origin` từ browser và trả `Access-Control-Allow-Origin` trên **response cuối cùng** qua proxy. Một proxy gỡ CORS headers hay header CSRF có thể khiến tích hợp thất bại.

### 11.4. Header phản hồi phải tương ứng với nguồn tạo response

| Response | Header/policy cần chú ý |
|---|---|
| SPA HTML từ `spa.example.com` | CSP (bao gồm `connect-src`), frame-ancestors, cache index.html, HSTS |
| SPA JS/CSS assets | MIME/nosniff, cache fingerprint, không trả HTML cho asset thiếu |
| API `/api/csrf` | CORS trusted origin + credentials, `Cache-Control: no-store`, token/session riêng |
| API `/api/me` | CORS, authentication/authorization, private/no-store cache policy |
| API POST login/logout/profile | CORS preflight và actual response, CSRF filter, session cookie, no-store |
| Redirect/error của API | Không trả HTML login ngoài dự kiến; CORS headers phù hợp để frontend thấy lỗi |
| Error page từ proxy | Đúng status và không lộ cấu trúc hạ tầng |

**Một CSP mạnh trên API JSON không tự bảo vệ HTML SPA ở origin khác**. Và CORS headers trên HTML SPA không thay CORS của resource API.

## 12. Reactive/WebFlux: CORS, WebSession và CSRF token

### 12.1. Điểm giống và khác với Servlet

Mô hình browser **không thay đổi** khi backend chuyển từ Spring MVC sang Spring WebFlux: trang ở `spa.example.com` vẫn gửi request cross-origin đến `api.example.com`; JavaScript phải dùng `credentials: "include"`, API phải cho đúng CORS Origin và session cookie phải đáp ứng policy browser.

Các class backend khác nhau:

| Vai trò | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Session-based CSRF repository | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Session | `HttpSession` | `WebSession` |
| CORS configuration source | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| CORS integration | `http.cors(...)` | `http.cors(...)` với Reactive source |
| Request context | Servlet request/response | `ServerWebExchange` |
| Token publisher | `CsrfToken` request attribute/argument | Thường `Mono<CsrfToken>` trên exchange attribute |
| Test | `MockMvc` | `WebTestClient` |

Đừng import **Servlet CORS source** vào ứng dụng WebFlux hoặc ngược lại; có các class tên gần giống nhưng thuộc package khác nhau.

### 12.2. CORS source dành cho Reactive

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfig {

    @Bean
    CorsConfigurationSource reactiveCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://spa.example.com"));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

CORS source trên chỉ có ý nghĩa khi được tích hợp với WebFlux handler/security chain. Đừng khai báo lặp một `CorsWebFilter` không cần thiết **và** Spring Security CORS integration mà không kiểm tra thứ tự/duplicate headers. Bên dưới dùng **Spring Security CORS integration trực tiếp** với source đã tạo.

### 12.3. SecurityWebFilterChain: preflight trước authentication

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        return http
            // Reactive CORS xử lý preflight trước yêu cầu phiên auth.
            .cors(cors -> cors.configurationSource(corsSource))

            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyExchange().authenticated()
            )

            .formLogin(form -> form
                .requiresAuthenticationMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                        "/api/login", HttpMethod.POST))
                .authenticationSuccessHandler(
                    (exchange, authentication) -> {
                        exchange.getExchange().getResponse()
                            .setStatusCode(HttpStatus.NO_CONTENT);
                        return Mono.empty();
                    })
                .authenticationFailureHandler(
                    (exchange, exception) -> {
                        exchange.getExchange().getResponse()
                            .setStatusCode(HttpStatus.UNAUTHORIZED);
                        return Mono.empty();
                    })
            )

            .logout(logout -> logout
                .requiresLogout(
                    new PathPatternParserServerWebExchangeMatcher(
                        "/api/logout", HttpMethod.POST))
                .logoutSuccessHandler((exchange, authentication) -> {
                    exchange.getExchange().getResponse()
                        .setStatusCode(HttpStatus.NO_CONTENT);
                    return Mono.empty();
                })
            )

            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((exchange, exception) -> {
                    exchange.getResponse()
                        .setStatusCode(HttpStatus.UNAUTHORIZED);
                    return exchange.getResponse().setComplete();
                })
            )

            // Cookie WebSession là credential tự gửi: không disable CSRF.
            .csrf(csrf -> csrf.csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()
            ))

            .build();
    }
}
~~~

**Điều kiện và giới hạn:**

- Đoạn trên là **ví dụ Reactive**, không được đưa vào ứng dụng Servlet cạnh tranh với `HttpSecurity`.
- Có thể cần điều chỉnh chi tiết handler/matcher theo phiên bản Spring Security đang sử dụng; xác minh API của version thực tế khi triển khai.
- Authentication user store/service và reactive dependencies phải được ứng dụng cấu hình.
- Form login truyền thống nhận `application/x-www-form-urlencoded`; JSON login cần authentication converter tùy chỉnh.
- Preflight `OPTIONS` không có cookie vẫn phải được xử lý CORS theo policy; actual POST sau đó chịu CSRF và authorization.
- Phản hồi `401`/`204` là contract ví dụ cho SPA; nếu ứng dụng dùng default redirect hoặc OAuth2 flow, cần thiết kế lại theo luồng thực tế.
- Với logout Reactive, việc dọn SecurityContext và **hủy toàn bộ WebSession** có thể khác chính sách Servlet. Nếu yêu cầu invalidate toàn WebSession, cần thêm handler phù hợp (ví dụ `WebSessionServerLogoutHandler`) và xác minh trạng thái sau logout.
- Không để matcher `/api/**` vô tình bỏ qua một nhóm endpoint cookie-based khi sau này thêm nhiều security chains.

### 12.4. Endpoint CSRF Reactive có subscribe publisher

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfApi {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> csrf =
            exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()
            )));
    }
}
~~~

Ví dụ này giả định `CsrfWebFilter` đã đưa `Mono<CsrfToken>` vào `ServerWebExchange`. Với deferred token, việc trả publisher trong pipeline giúp token được resolve; không gọi `block()` trong controller.

Nếu application dùng custom request handler/token provider, phải kiểm tra cách token được cấp trên exchange. Response JSON chỉ nên đọc được từ những frontend origins đáng tin cậy qua CORS và phải có no-store cache policy.

### 12.5. Reactive API đọc user và cập nhật hồ sơ

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
class ReactiveProfileApi {

    private final ReactiveProfileService profiles;

    ReactiveProfileApi(ReactiveProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .map(p -> Map.of("username", p.getName()));
    }

    record UpdateProfile(String displayName) {}

    @PostMapping("/api/profile")
    Mono<ResponseEntity<Void>> update(
            ServerWebExchange exchange,
            @RequestBody Mono<UpdateProfile> input) {

        return Mono.zip(exchange.getPrincipal(), input)
            .flatMap(pair -> {
                String displayName = pair.getT2().displayName();

                if (displayName == null || displayName.isBlank()
                        || displayName.length() > 80) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Tên không hợp lệ"));
                }

                return profiles.renameIfAuthorized(
                        pair.getT1().getName(), displayName)
                    .thenReturn(ResponseEntity.noContent().build());
            });
    }
}
~~~

`ReactiveProfileService` là **service giả định** có method trả `Mono<Void>`; ứng dụng thật phải triển khai phân quyền, validation và ghi dữ liệu qua non-blocking storage hoặc cô lập thao tác blocking đúng cách.

### 12.6. Cookie WebSession qua HTTPS

Với `CookieWebSessionIdResolver` và Spring Framework phiên bản hỗ trợ `addCookieInitializer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));

        return resolver;
    }
}
~~~

Trong ví dụ **same-site cross-origin**, cookie `SameSite=Lax` có thể được browser gửi nếu `credentials: "include"`, HTTPS và các chính sách khác cho phép. Khi SPA/API khác site, cần đánh giá lại None/Secure và third-party cookie blocking.

Nếu dùng **Spring Session**, cookie serializer hoặc một WebSessionIdResolver riêng, nó có thể thay đổi nơi phát cookie. Kiểm tra `Set-Cookie` thật thay vì cho rằng config này luôn là nguồn quyết định cuối.

## 13. Test CORS/CSRF trên Servlet với MockMvc

### 13.1. Một bộ test cần tách hai nhóm câu hỏi

**Nhóm A — CORS:** Origin `https://spa.example.com` được phép preflight và đọc actual response theo policy; Origin không tin cậy không được nhận credentialed CORS permission.

**Nhóm B — CSRF:** Với cùng principal, cùng payload và session phù hợp, request ghi **đúng token** đi qua lớp CSRF, còn **thiếu/sai token** bị chặn và không có side effect.

Test CORS thành công không chứng minh token CSRF hợp lệ; test `with(csrf())` không mô phỏng browser áp dụng cookie SameSite hoặc CORS response.

### 13.2. MockMvc: preflight được phép, preflight bị chặn

Giả định `CorsConfigurationSource` ở mục 7.1 đã được Spring Security tích hợp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsServletPreflightTests {

    @Autowired MockMvc mvc;

    @Test
    void allowedSpaPreflightDoesNotRequireLoginCookie()
            throws Exception {

        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://spa.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://spa.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void untrustedOriginIsNotAllowed() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://attacker.other.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }
}
~~~

Kết quả `403` ở preflight không được phép là hành vi thường gặp của Spring CORS processor theo cấu hình này; nếu custom handler trả status khác, assertion phải theo policy thực tế. Điểm cần xác minh là **Origin không tin cậy không được nhận CORS permission để đọc credentialed response**.

**Vì sao không có `with(user("alice"))` trong preflight?** Preflight không được dựa vào session đã xác thực: browser thường không gửi cookie của actual request trong preflight. Nếu Spring Security chặn OPTIONS vì chưa login, cấu hình CORS trước security đang có vấn đề.

### 13.3. MockMvc: POST đúng/thiếu/sai token, cùng trusted Origin

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndCsrfServletTests {

    @Autowired MockMvc mvc;

    @Test
    void validCsrfHeaderPasses() throws Exception {
        mvc.perform(post("/api/profile")
                .header("Origin", "https://spa.example.com")
                .with(user("alice"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice New\"}"))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://spa.example.com"));
    }

    @Test
    void missingCsrfHeaderIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .header("Origin", "https://spa.example.com")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Do Not Save\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfHeaderIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .header("Origin", "https://spa.example.com")
                .with(user("alice"))
                .with(csrf().asHeader().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Do Not Save\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đoạn test giả định endpoint POST trả `204` khi hợp lệ, service test cho phép Alice chỉnh sửa và không có validation failure. `with(user("alice"))` tạo mock authentication; `with(csrf())` dùng test token, **không chứng minh** session cookie thật, browser credentials mode hoặc request handler raw/masked của SPA.

Với các negative cases, thêm assertion database/service: **không có dữ liệu nào được cập nhật**. CSRF header không phải giấy phép vượt authorization.

### 13.4. Test GET CSRF token thật theo session

Mức tích hợp cao hơn:

1. GET `/api/csrf` với `Origin: https://spa.example.com`.
2. Lấy JSON `headerName`, `token` và `MockHttpSession` do repository cấp.
3. POST `/api/profile` với **cùng session** và token đúng trong header đã được công bố.
4. POST với cùng session nhưng **thiếu token**; phải `403`.
5. Tạo session B riêng, lấy token B; POST với session A + token B phải bị từ chối nếu repository theo `HttpSession`.
6. Sau negative cases, kiểm tra database không đổi.

Ví dụ code phần cốt lõi:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfRoundTripServletTests {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    @Test
    void clientUsesIssuedTokenWithSameSession() throws Exception {
        MvcResult issue = mvc.perform(get("/api/csrf")
                .header("Origin", "https://spa.example.com")
                .with(user("alice")))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode data = json.readTree(
            issue.getResponse().getContentAsString());
        String token = data.get("token").asText();
        String headerName = data.get("headerName").asText();

        MockHttpSession session = (MockHttpSession)
            issue.getRequest().getSession(false);

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .header("Origin", "https://spa.example.com")
                .header(headerName, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice New\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .header("Origin", "https://spa.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Must Not Change\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là test token/HttpSession trong MockMvc. `MockMvc` **không chạy trình duyệt thật**, nên không áp dụng thuật toán SameSite, chặn third-party cookie hay `fetch(credentials)`. Kiểm thử E2E browser là tầng bổ sung bắt buộc với kiến trúc cross-origin.

## 14. Test CORS/CSRF trên Reactive với WebTestClient

### 14.1. Tạo test client có Spring Security WebFlux filters

Giả định project WebFlux đã có `ReactiveCorsConfig`, `ReactiveApiSecurityConfig` và endpoint API phù hợp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsAndCsrfReactiveTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void allowedPreflightDoesNotNeedCookie() {
        client().options().uri("/api/profile")
            .header("Origin", "https://spa.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "Access-Control-Allow-Origin",
                "https://spa.example.com")
            .expectHeader().valueEquals(
                "Access-Control-Allow-Credentials", "true");
    }

    @Test
    void wrongOriginPreflightIsRejected() {
        client().options().uri("/api/profile")
            .header("Origin", "https://attacker.other.test")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers", "x-csrf-token")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfTokenPasses() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/api/profile")
            .header("Origin", "https://spa.example.com")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Alice New\"}")
            .exchange()
            .expectStatus().isNoContent();
    }

    @Test
    void missingCsrfTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/api/profile")
            .header("Origin", "https://spa.example.com")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Must Not Save\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongCsrfTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/api/profile")
            .header("Origin", "https://spa.example.com")
            .header("X-CSRF-TOKEN", "invalid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Must Not Save\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Giới hạn:**

- `mockUser()` tạo principal giả để tránh lỗi thiếu đăng nhập làm nhiễu kiểm tra CSRF.
- `csrf()` là test helper; nó không chứng minh frontend đã nhận token qua CORS, gửi cookie thật hay handler token có round-trip đúng.
- `WebTestClient` không tự chạy thuật toán browser SameSite/CORS; nó gọi ứng dụng test qua web filter chain.
- Status preflight cụ thể phụ thuộc CORS processor/policy nhưng nguyên tắc cần assert là **trusted origin được phép, untrusted origin không được phép**.
- Test `POST /api/profile` giả định endpoint thực sự chấp nhận JSON hợp lệ và trả `204`. Bổ sung kiểm chứng trạng thái dữ liệu sau negative tests.

### 14.2. HTTP integration cho Reactive/WebSession

Test nhiều request liên tiếp với **hai cookie jars tách biệt**:

~~~text
Client A:
    GET /api/csrf + Origin của SPA
       -> lấy Set-Cookie: SESSION=A, token A
    POST /api/profile + Cookie: SESSION=A + header token A
       -> qua CSRF nếu đã xác thực và đủ quyền
    POST /api/profile + Cookie: SESSION=A, không token
       -> bị từ chối, không có side effect

Client B:
    GET /api/csrf
       -> Set-Cookie: SESSION=B, token B

Client A:
    POST /api/profile + Cookie: SESSION=A + header token B
       -> bị từ chối với WebSession-backed token
~~~

Với reactive stack, `CsrfWebFilter` đặt token publisher ở exchange khi cần; endpoint `/api/csrf` phải subscribe và trả giá trị thực. Nếu test dùng `WebTestClient.bindToApplicationContext`, cần chủ động giữ và gửi cookie giữa các request hoặc dùng client chạy qua server thật có cookie jar; không mặc định test client mô phỏng mọi hành vi browser.

## 15. Browser E2E: bằng chứng quyết định của tích hợp khác origin

Các test server ở trên chỉ cho biết Spring CORS/CSRF filters phản ứng thế nào khi nhận request. Chúng **không chứng minh browser đã gửi cookie và cho phép JavaScript đọc response**. Với kiến trúc SPA khác origin, kiểm thử trong browser thật là cần thiết.

### 15.1. Hai môi trường test riêng: same-site và cross-site

Dùng những tên miền thử nghiệm đã được cấu hình DNS/hosts và HTTPS:

~~~text
Môi trường A — Cross-origin nhưng same-site:
  SPA: https://spa.example.test
  API: https://api.example.test

Môi trường B — Cross-origin và cross-site:
  SPA: https://frontend.other.test
  API: https://api.example.test
~~~

Những tên miền trên là **mô hình**, không mặc định tự hoạt động trên Internet; cần certificate hợp lệ và policy môi trường phù hợp.

Tại môi trường A, cookie `SameSite=Lax` của API thường có thể được gửi trong request same-site khi `credentials: "include"`. Tại môi trường B, cookie `Lax` thường **không** đi cùng cross-site fetch. Cookie `None; Secure` chỉ có thể hoạt động nếu browser cho third-party cookie trong ngữ cảnh đó.

**Không trộn kết quả hai môi trường.** Một cấu hình pass tại `spa.example.com`/`api.example.com` không chứng minh nó sẽ hoạt động với frontend nằm ở site khác.

### 15.2. Kịch bản E2E được đề xuất

1. **Mở trang SPA:** Truy cập origin frontend qua HTTPS, kiểm tra bundle tải được và CSP `connect-src` cho API origin.
2. **Gọi GET pre-login:** `fetch("https://api.../api/csrf", {credentials: "include"})`. Quan sát `Origin`, CORS headers và `Set-Cookie` trên response.
3. **Xác nhận cookie nhận được:** Trong DevTools Storage/Cookies và Network, xem cookie của **API host** có tồn tại và thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path` đúng không. Cookie HttpOnly **không hiện trong `document.cookie`**, không phải lỗi.
4. **Thực hiện login:** POST `/api/login` có form-urlencoded body và `X-CSRF-TOKEN`. Quan sát request `OPTIONS` trước POST; preflight không cần session cookie, nhưng phải có `Access-Control-Allow-Origin`/methods/headers hợp lệ.
5. **Kiểm tra session sau login:** Gọi `GET /api/me`. API phải trả user hiện tại nếu browser đã lưu/gửi cookie. Không dựa vào một biến `isLoggedIn` trong frontend để kết luận server đã xác thực.
6. **Lấy token sau login:** Gọi `GET /api/csrf` lần nữa nếu login đã thay đổi phiên/token.
7. **POST hợp lệ:** Gửi JSON cùng header CSRF, kiểm tra `204` và xác nhận dữ liệu được cập nhật.
8. **POST thiếu token:** Với cùng session cookie, bỏ CSRF header và gửi POST test có payload hợp lệ. Server phải từ chối và **không ghi dữ liệu**.
9. **POST token sai:** Đổi token hoặc dùng token của session B độc lập. Server phải từ chối nếu repository yêu cầu ràng buộc phiên.
10. **Origin không được phép:** Từ trang ở `https://untrusted.other.test`, thử fetch API. Browser không được đọc response có credential; nếu request thực vẫn đến server qua đường khác, CSRF vẫn phải bảo vệ thao tác ghi.
11. **Logout có token:** POST `/api/logout` hợp lệ; GET `/api/me` sau đó phải không còn authenticated session.
12. **Kiểm tra phiên đã hết hạn:** Giữ trang SPA mở, logout ở tab khác hoặc để session timeout rồi gửi POST; UI phải xử lý 401/403 hợp lý, không tự bỏ CSRF.
13. **Thử browser khác:** Kiểm tra các browser mục tiêu của sản phẩm, bao gồm thiết lập chặn third-party cookies nếu hỗ trợ frontend/API cross-site.
14. **Qua reverse proxy thật:** Bật route production-like; kiểm tra forwarded headers, Cookie, Location, caching, CORS headers trên response thành công **và response lỗi**.

### 15.3. Hai browser contexts cho session A/B

~~~text
Context A:
  GET API /api/csrf      -> cookie/session A, token A
  POST API /api/login    -> session xác thực A'
  GET API /api/csrf      -> token A' hiện hành
  POST API /api/profile  -> cookie A' + token A' hợp lệ

Context B:
  GET API /api/csrf      -> cookie/session B, token B

Context A:
  POST API /api/profile  -> cookie A' + token B
  => từ chối với synchronizer token theo session
~~~

Mỗi context phải có **cookie jar riêng**. Hai tab trong cùng browser profile có thể chia sẻ cookie, nên **không tương đương hai session**.

Trong test này, còn phải xác minh attacker origin **không được CORS cấp quyền đọc token của context A**, kể cả khi attacker có thể tạo request tới API.

### 15.4. Có cần dùng Playwright/Cypress không?

Browser automation có ích để bắt lỗi môi trường thật. Khi viết test:

- Sử dụng **hai origin thật**, không mock `Origin` rồi coi như browser policy đã được thử.
- Gắn network instrumentation chỉ ghi metadata, **không lưu session ID hoặc CSRF token đầy đủ**.
- Xác nhận **actual request có/không xảy ra** sau preflight, tránh coi browser CORS error tương đương server CSRF rejection.
- Dùng test user và dữ liệu có thể reset; kiểm tra data/event trước/sau các negative cases.
- Với cross-site cookie, chọn browser versions/settings tương ứng môi trường hỗ trợ, không chỉ một bản Chrome ở chế độ mặc định.
- Sau login/logout, kiểm tra cả CORS headers trên response `204`, `401` và `403` để frontend nhìn thấy lỗi thực.

## 16. Các lỗi triển khai thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
|---|---|---|
| `TypeError: Failed to fetch` và console báo CORS | API không cấp ACAO, sai allowed origin, preflight không được phép hoặc lỗi mạng | Mở Network: request OPTIONS, actual request, status và response headers |
| Preflight `OPTIONS` trả `401`/redirect login | Security authentication chạy trước xử lý CORS | Đặt CORS vào Spring Security chain trước auth; preflight không đòi cookie |
| Preflight `OPTIONS` trả `403` | Origin, method hoặc header không nằm trong allowlist | Kiểm tra `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` |
| Response có `Access-Control-Allow-Origin: *` và `Allow-Credentials: true` | Wildcard không hợp lệ cho credentialed CORS | Trả chính xác trusted SPA origin và `Vary: Origin` |
| Browser không cho JS đọc response dù API trả `200` | Thiếu `Access-Control-Allow-Credentials: true` hoặc ACAO sai | Kiểm tra response **actual**; preflight pass chưa đủ |
| GET `/api/csrf` trả token nhưng POST `403` | Cookie pre-auth/session không đi cùng POST, token cũ hoặc header sai | So Cookie trên GET/POST, request handler, raw/masked, login lifecycle |
| Login trả `204` nhưng GET `/api/me` vẫn `401` | Browser không lưu/gửi cookie, session persistence sai, third-party cookie blocked | DevTools Storage/Network, cookie Path/Domain/SameSite và Set-Cookie warnings |
| SPA ở `spa.example.com` không đọc được `XSRF-TOKEN` của `api.example.com` | Cookie API host-only, JS ở sibling hostname không đọc được | Cấp CSRF qua JSON hoặc thiết kế transport khác có kiểm soát |
| Browser gửi cookie trong same-site cross-origin dù `SameSite=Strict` | SameSite dựa theo site, không theo origin | Kiểm tra schemeful same-site và giữ CSRF |
| Cookie `SameSite=Lax` không gửi ở frontend site khác | Cross-site fetch không được Lax cho cookie | Kiểm tra nhu cầu None/Secure, browser blocking và xem lại kiến trúc |
| Cookie `None; Secure` vẫn không gửi | Chính sách chặn third-party cookie hoặc hạn chế storage | Test browser support, cân nhắc proxy cùng origin/BFF |
| Cookie `Secure` không lưu trong môi trường HTTP dev | Scheme không phù hợp, browser policy/localhost exception khác | Dùng local HTTPS hoặc dev proxy, đừng giảm bảo mật production |
| CORS pass nhưng POST giả mạo vẫn thực hiện | Server không kiểm CSRF hoặc endpoint chấp nhận simple form body | Bật token/filter đúng chain và test no-side-effects |
| Request POST sai token được frontend hiển thị như “CORS error” | Error response 403 thiếu CORS headers do custom handler/proxy | Kiểm tra ACAO/credentials trên **response lỗi** |
| Status `403` dù CSRF token đúng | User thiếu quyền, token hết hạn, wrong session hoặc handler sai dạng | Phân biệt `AccessDeniedException`, CSRF exception, principal, authorities |
| CORS cho `https://spa.example.com` nhưng dev ở `http://localhost:5173` bị chặn | Dev origin không có trong production allowlist | Dùng dev profile có allowlist riêng, không mở wildcard production |
| Header CORS có ở Spring nhưng không tới browser | Reverse proxy/WAF thay/loại headers hoặc cache response | So response ở upstream và browser, kiểm tra cache/Vary |
| Browser OPTIONS pass rồi POST `404` | Proxy rewrite path hoặc backend route sai | So public `/api/...` và path backend nhận |
| SPA chạy HTTPS nhưng API URL là HTTP | Mixed content bị chặn, `Secure` cookie không hoạt động | Dùng HTTPS API và CSP `connect-src` phù hợp |
| Login OAuth callback mất state | Cookie Strict/Lax không phù hợp cross-site callback POST hoặc session store sai | Kiểm tra response mode/state storage và SameSite, không bỏ CSRF nghiệp vụ |
| Sau logout, tab cũ POST `403` | Token/phiên đã invalidated | Reload token và xác thực lại, không tắt CSRF |
| Token sau login không giống token trước login | Login/session rotation và CSRF token invalidation | Hành vi có thể đúng; GET token mới trước POST tiếp |
| Chỉ lỗi khi scale nhiều node | Session/token chỉ ở node A, request sau đến node B | Shared session store/affinity, TTL, cookie và node mapping |
| CSRF token bị lộ trong CDN/log | Cache GET token hoặc logging body/header quá rộng | `Cache-Control: no-store`, khử token/cookie khỏi logs, kiểm tra edge |

### 16.1. Phân biệt browser block với server reject

~~~text
Trường hợp A — Preflight bị chặn:
  Browser → OPTIONS
  API/proxy → không cho CORS
  Browser KHÔNG gửi POST thật
  JS thường thấy lỗi CORS/network

Trường hợp B — Browser cho POST, server chặn CSRF:
  Browser → OPTIONS (nếu cần)
  API → preflight cho phép
  Browser → POST có cookie nhưng thiếu/sai token
  Spring Security → 403
  JS thấy HTTP 403 NẾU response cũng có CORS headers phù hợp

Trường hợp C — POST không có cookie:
  Browser → POST, credentials include nhưng cookie bị policy loại
  Spring Security → xem như anonymous hoặc thiếu session
  JS thấy 401/403/redirect theo authentication entry point
~~~

Ba trường hợp có cách khắc phục khác nhau. Đừng dùng `csrf.disable()` để chữa lỗi preflight, hoặc mở `Access-Control-Allow-Origin` cho mọi website để chữa lỗi session cookie.

### 16.2. Đọc Network theo thứ tự

Trong DevTools, kiểm tra:

1. **Request URL:** Đúng public API scheme, host và port không?
2. **Request Origin:** Đúng origin frontend đang tải không?
3. **OPTIONS preflight:** Có được gửi không, status bao nhiêu, request method/headers có khớp allowlist?
4. **Preflight response:** `Access-Control-Allow-Origin` và `Allow-Credentials` hợp lệ không?
5. **Actual request:** Có thực sự được gửi sau preflight không?
6. **Cookie header:** Browser có đính kèm session cookie không? Không lấy `document.cookie` làm bằng chứng nếu cookie HttpOnly.
7. **CSRF header:** Tên/value có được gửi không (không cần ghi giá trị token ra log)?
8. **Actual response:** CORS headers có trên 2xx/401/403 không, redirect có làm đổi origin không?
9. **Server side:** Filter chain nào được chọn, exception thuộc CSRF/auth/authorization?
10. **Dữ liệu:** Với negative case, thao tác nghiệp vụ có bị thực hiện ngoài ý muốn không?

## 17. Multi-node, cache và reverse proxy

### 17.1. Session store phải nhất quán

~~~mermaid
flowchart LR
    SPA[Browser SPA] --> API[api.example.com TLS Gateway]
    API --> A[Spring node A]
    API --> B[Spring node B]
    A --> STORE[(Shared Session Store)]
    B --> STORE
~~~

Nếu `GET /api/csrf` được xử lý ở node A, còn POST ở node B, hai node phải có thể truy cập **cùng expected token** theo session. Có thể dùng sticky session hoặc shared session store (ví dụ Spring Session với store được hỗ trợ), kèm TTL/serializer phù hợp.

Không giải quyết `403` ngẫu nhiên giữa node bằng cách tắt CSRF hoặc cho phép token bất kỳ.

### 17.2. CORS headers và proxy cache

Khi trả credentialed CORS response, cache trung gian cần tôn trọng `Vary: Origin`; nhưng response cá nhân/CSRF token thường cần **no-store** vì Vary không tự ngăn cache chia sẻ dữ liệu nhạy cảm giữa users.

Với proxy:

- Không cache `/api/csrf`, login, logout và response riêng tư.
- Không loại `Set-Cookie` trên response API nếu application session cần cookie.
- Không bỏ `Origin`/`X-CSRF-TOKEN`/`Cookie` trên request actual; nhưng phải bảo vệ credential và khử thông tin nhạy cảm khi log.
- Đảm bảo response `401`/`403` có CORS headers chính xác cho trusted SPA để frontend báo lỗi đúng.
- Chỉ tin forwarded headers từ proxy được quản lý; tránh host/scheme spoofing khi tạo redirect hoặc absolute URL.
- Đừng trộn cache của preflight và response dữ liệu của user.

### 17.3. Cookie scope khi backend triển khai dưới context path

Nếu API public URL có prefix `/api/**` nhưng backend servlet context path khác, cookie `Path` có thể chỉ phù hợp với prefix nội bộ thay vì public path. Khi đó browser không gửi cookie ở request tiếp theo dù cookie đã được phát.

Kiểm tra `Set-Cookie: Path=...` trong **browser public URL**, không chỉ config nội bộ. Sửa ở tầng session cookie resolver hoặc proxy cookie path rewrite một cách có kiểm soát, tránh cùng tên cookie nhiều Path gây hành vi khó đoán.

## 18. Quyết định kiến trúc: CORS+cookie, proxy cùng origin hay BFF?

| Phương án | Khi nào hợp lý | Điểm mạnh | Thách thức cần giải |
|---|---|---|---|
| **SPA cross-origin cùng site** | Frontend/API trên hai subdomain cùng HTTPS, cùng registrable domain | Tách triển khai, cookie Lax có thể hoạt động, API độc lập | CORS allowlist, `credentials: include`, CSRF header, cookie host-only |
| **SPA cross-site + cookie** | Tích hợp nhiều site thật sự cần browser cookie API | Có thể giữ session cookie ở API | `SameSite=None; Secure`, third-party cookie blocking, browser compatibility, CSRF/CORS |
| **SPA + reverse proxy cùng origin** | Có quyền kiểm soát một public host cho UI/API | Đơn giản hóa fetch/CORS, thường giảm phụ thuộc cross-site cookie | Proxy routing, TLS, cache, session, CSRF vẫn cần |
| **BFF cùng origin với SPA** | Cần giữ access/refresh token khỏi JS, frontend gọi API gián tiếp | Browser→BFF dùng session cookie, BFF→API dùng bearer server-side | CSRF tại BFF, session store, backend authorization, logout |
| **Bearer-only API với client chủ động gửi header** | API thực sự không nhận cookie/HTTP auth fallback | CSRF kiểu cookie ít trọng tâm hơn | XSS/token theft, token lifecycle, CORS và quyền |

**Khuyến nghị thiết kế:** Nếu không có yêu cầu mạnh bắt buộc cross-site cookies và mục tiêu là hỗ trợ nhiều browser, **same-origin proxy hoặc BFF** thường giảm độ phức tạp hơn việc phụ thuộc `SameSite=None` và third-party cookie exceptions. Tuy nhiên kiến trúc nào cũng phải giữ phân quyền và các lớp chống XSS/CSRF tương ứng.

## 19. Checklist kiểm thử và triển khai

| Kiểm tra | Tiêu chí cần đạt |
|---|---|
| Origin | Scheme/hostname/port frontend và API đã được ghi rõ |
| Phân loại site | Same-site cross-origin hay cross-site, không nhầm hai khái niệm |
| CORS allowlist | Chỉ origin thực sự được tin cậy; không phản chiếu mọi origin |
| Credentialed CORS | ACAO là origin cụ thể, `Access-Control-Allow-Credentials: true` |
| Preflight | OPTIONS hoạt động **không cần session cookie**, kiểm tra method/header |
| Actual response | CORS headers có trên success và error responses theo policy |
| Fetch | `credentials: "include"` ở tất cả request cần cookie |
| Cookie xác thực | Host-only khi có thể, `HttpOnly; Secure` và SameSite phù hợp |
| Third-party cookies | Có kiểm thử browser đích nếu frontend/API cross-site |
| API token | `GET /api/csrf` được trusted SPA đọc, `Cache-Control: no-store` |
| CSRF POST | HeaderName/token đúng, missing/wrong bị 403, không có side effect |
| Session lifecycle | Token mới sau login/logout/timeout khi cần, không dùng token cũ |
| Authorization | Mỗi route/tài nguyên đều kiểm tra quyền phía server |
| XSS/CSP | SPA chặn XSS, có CSP `connect-src` cho API origin |
| HTTPS/HSTS | Cả frontend và API chạy HTTPS, HSTS theo chính sách |
| Proxy | Giữ Origin, Cookie, CSRF headers, public path và redirect |
| Cache/Vary | Response riêng tư không cache công khai; Vary theo Origin khi cần |
| Test Servlet | MockMvc kiểm tra CORS preflight và token đúng/thiếu/sai |
| Test Reactive | WebTestClient kiểm tra preflight + CsrfWebFilter |
| Browser E2E | Cookie thật, network preflight, 401/403, hai session, cross-site policy |
| Observability | Không log session ID, CSRF token hay nội dung PII nhạy cảm |

## 20. Câu hỏi tự đánh giá

**Câu 1.** SPA ở `https://spa.example.com` gọi API `https://api.example.com`. Hai địa chỉ cùng registrable domain; có cần CORS không?

**Đáp án:** Có. Hai hostname khác nhau nên **cross-origin**; CORS được đánh giá theo origin, không theo site. Hai địa chỉ có thể **same-site**, giúp cookie Lax đủ điều kiện được gửi khi `credentials: "include"` và cookie policy cho phép.

**Câu 2.** Frontend gọi `fetch("https://api.example.com/api/me")` không truyền options, server có trả ACAO/credentials đúng. Vì sao backend vẫn không thấy session cookie?

**Đáp án:** `fetch` mặc định thường dùng `credentials: "same-origin"`, nên cookie không được gửi trong cross-origin request. Frontend cần `credentials: "include"`; browser vẫn áp dụng SameSite, Secure và cookie policy.

**Câu 3.** Một SPA cross-origin dùng `X-CSRF-TOKEN`. Browser phát OPTIONS không có cookie; server đòi authenticated session cho OPTIONS và trả 401. Sửa gì?

**Đáp án:** Tích hợp CORS trước Spring Security authentication cho preflight; browser không gửi cookie của actual request trong preflight. Không vô hiệu hóa CSRF trên POST; POST thực vẫn kiểm tra token.

**Câu 4.** API trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. Có đúng cho SPA dùng cookie không?

**Đáp án:** Không. Credentialed CORS response không được dùng wildcard origin. Phải allowlist và trả origin cụ thể, kết hợp `Vary: Origin` khi phản hồi khác nhau theo Origin.

**Câu 5.** Cookie `JSESSIONID` của API có `HttpOnly` nên SPA không thấy trong `document.cookie`. Có phải đổi `HttpOnly=false` không?

**Đáp án:** Không. Browser có thể tự gửi cookie cho API khi `credentials: "include"` và cookie policy cho phép. SPA chỉ cần đọc endpoint `/api/me` và CSRF token được cấp qua kênh riêng; session ID không nên cho JS đọc.

**Câu 6.** SPA ở `https://frontend.other.test` gọi API `https://api.example.com`. Cookie `SameSite=Lax` không được gửi, nên có người đề nghị `None; Secure`. Đề nghị này đã giải quyết xong chưa?

**Đáp án:** Chưa. `None; Secure` chỉ cho phép cookie cross-site trong những ngữ cảnh browser hỗ trợ; third-party cookie blocking/partitioning vẫn có thể ngăn. CORS và CSRF cũng cần cấu hình đúng, hoặc cân nhắc kiến trúc proxy/BFF.

**Câu 7.** CORS chỉ cho `spa.example.com` đọc response. Có thể tắt CSRF vì trang ngoài không đọc được response không?

**Đáp án:** Không. Một form cross-origin có thể gửi POST mà không đọc response; nếu cookie được gửi và server chấp nhận body, thao tác có thể xảy ra. CSRF token vẫn bảo vệ request có tác động.

**Câu 8.** SPA tại `spa.example.com` đọc cookie `XSRF-TOKEN` host-only do `api.example.com` phát nhưng nhận `undefined`. Đâu là nguyên nhân?

**Đáp án:** JS thuộc hostname SPA không đọc được cookie host-only của API. Nên cấp CSRF token qua JSON response có credentialed CORS cho trusted SPA hoặc thiết kế một cơ chế cookie-scope khác có phân tích rủi ro; **không mở session cookie HttpOnly**.

**Câu 9.** Một POST với token sai trả HTTP 403 từ server, nhưng JavaScript chỉ hiện CORS error. Tại sao?

**Đáp án:** Response 403 có thể thiếu CORS headers nên browser không cho JS đọc status/body. Cần điều tra CORS trên error path và nguyên nhân CSRF riêng; không thay việc server từ chối token sai.

**Câu 10.** Các test `MockMvc.with(csrf())` và `WebTestClient.mutateWith(csrf())` đều pass. Có chứng minh third-party cookie hoạt động trên Safari/Firefox/Chrome không?

**Đáp án:** Không. Test helper kiểm tra logic security phía server, không chạy thuật toán cookie policy browser. Cần E2E browser thật với frontend/API cross-site và xác minh Cookie/Set-Cookie trên Network.

## Kết luận

**SPA khác origin với CORS và cookie** yêu cầu phối hợp đúng **ba ranh giới bảo mật độc lập**: browser kiểm soát việc gửi **cookie credential** qua `Secure`, `SameSite`, scope và third-party cookie policy; **CORS** quyết định JavaScript ở origin SPA có được gửi/đọc response cross-origin theo policy hay không; **CSRF token** được Spring Security kiểm chứng trước khi thao tác ghi dùng credential tự gửi được chấp nhận.

Với hai subdomain cùng scheme và registrable domain, SPA/API có thể **cross-origin nhưng same-site**: vẫn cần CORS và `credentials: "include"`, song cookie `SameSite=Lax` có thể được gửi. Với frontend/API **khác site**, `SameSite=None; Secure` có thể cần nhưng không thắng được các chính sách chặn third-party cookie, nên cần kiểm thử browser và cân nhắc reverse proxy/BFF.

Trên **Spring Security Servlet**, sử dụng `HttpSecurity.cors(...)` cùng `UrlBasedCorsConfigurationSource` và giữ `CsrfFilter`/`HttpSessionCsrfTokenRepository` cho session-cookie POST. Trên **Reactive/WebFlux**, dùng `ServerHttpSecurity.cors(...)` với Reactive CORS source và giữ `CsrfWebFilter`/`WebSessionServerCsrfTokenRepository`. Frontend lấy token qua `GET /api/csrf` được CORS allowlist, gửi header trên unsafe request và làm mới token khi vòng đời xác thực thay đổi.

Kiểm thử phải bao trùm **OPTIONS preflight**, response CORS cho cả thành công và lỗi, cookie thực trong browser, token đúng/thiếu/sai, login/logout, two-session binding và **không có tác động nghiệp vụ khi request bị từ chối**. Các lớp CSP, HSTS, security headers, HTTP firewall và bảo vệ session trong **SPRING_SECURITY_HTTP_PROTECTION** bổ sung đúng mục đích, chứ không thay nhau.

## Tài liệu tham khảo

- [Spring Security — CORS với Servlet](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): tích hợp CORS trước authentication, cấu hình CORS source.
- [Spring Security — CORS với Reactive](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): tích hợp CORS trong WebFlux/Spring Security.
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): session token, request handler, masking và SPA.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` và token repository.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser CORS, simple requests, preflight, credentials và response headers.
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `same-origin` và `include`.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): ranh giới origin của browser.
- [web.dev — SameSite cookies explained](https://web.dev/articles/samesite-cookies-explained): same-site, cross-site và những lựa chọn cookie.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token và defense in depth.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): chống XSS tại origin SPA được CORS allowlist.
