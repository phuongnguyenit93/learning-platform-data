# Phân biệt CORS, xác thực, phân quyền và CSRF trong Spring MVC

## 1. Mục tiêu: bốn cơ chế giải quyết bốn câu hỏi khác nhau

Giả sử có một frontend tại `https://app.example.test` gọi API Spring Boot tại `https://api.example.test`. Người dùng đã đăng nhập, trình duyệt muốn tạo tài liệu mới, server chỉ cho role `EDITOR` thao tác, và kẻ tấn công có một website khác cố gửi lệnh thay người dùng.

Trong kịch bản này, có **bốn quyết định bảo mật** cần tách bạch:

1. **CORS (Cross-Origin Resource Sharing):** JavaScript của **origin nào** được trình duyệt cho phép đọc response của API và được browser cho phép thực hiện request CORS theo các quy tắc của Fetch?
2. **Xác thực (authentication):** Request đang đến từ **danh tính nào**, và bằng chứng đăng nhập có hợp lệ không?
3. **Phân quyền (authorization):** Danh tính đó **được phép làm gì** với endpoint, object và dữ liệu cụ thể?
4. **CSRF (Cross-Site Request Forgery):** Làm sao ngăn một website khác **kích hoạt request làm thay đổi trạng thái** bằng những thông tin xác thực mà browser có thể tự đính kèm thay người dùng?

**Chìa khóa:** CORS không phải authentication, không quyết định người dùng có quyền sửa dữ liệu, và **không thay thế CSRF protection**. Authentication không tự động cho phép mọi thao tác; authorization không tự bảo vệ khỏi request giả mạo từ browser đã đăng nhập.

Bài học bao gồm sơ đồ threat model, HTTP headers, request preflight, cookies/credentials, token CSRF, cùng một ứng dụng **Spring Boot 3.3.x / Java 17 / Spring Security 6.x** có cấu hình CORS + authentication + authorization + CSRF và kiểm thử MockMvc. Các đoạn code chạy ở Servlet MVC stack, khác một số API tương ứng của WebFlux.

## 2. Bảng so sánh nhanh

| Cơ chế | Trả lời câu hỏi | Thực thi chủ yếu ở đâu? | Dữ kiện quyết định | Nếu không đạt |
| --- | --- | --- | --- | --- |
| **CORS** | Origin khác có được JavaScript đọc response và gửi CORS request theo browser protocol không? | Browser, với chính sách phản hồi của server | `Origin`, `Access-Control-*`, method, headers, credentials | Browser chặn JS đọc response hoặc không gửi actual request sau preflight thất bại |
| **Authentication** | Bạn là ai? | Server/API/security filter | Session, cookie, HTTP Basic, bearer token, mTLS… | Thường **401** với API cần đăng nhập; có ngoại lệ tùy flow |
| **Authorization** | Bạn được làm việc này với resource này không? | Server/API, method/service/data layer | Principal, role/authority, ownership, tenant, policy | Thường **403** nếu đã xác thực nhưng thiếu quyền; đôi khi **404** có chủ ý để ẩn tồn tại |
| **CSRF protection** | Request thay đổi trạng thái có thật sự xuất phát từ luồng được tin cậy không? | Server và browser client phối hợp | CSRF token, Origin/Referer, SameSite, Fetch Metadata và chính sách session | Thường **403** nếu thiếu/sai token khi bật Spring Security CSRF |

Một request có thể **CORS hợp lệ nhưng authentication thất bại**, hoặc **authentication hợp lệ và đúng role nhưng CSRF thất bại**. Không suy đoán nguyên nhân chỉ từ 403; tìm exception/handler và xem loại kiểm tra nào từ chối.

## 3. Same-Origin Policy và CORS: browser mới là bên cưỡng chế

Một **origin** được xác định bằng tổ hợp **scheme + host + port**.

| URL | Origin so với `https://app.example.test` |
| --- | --- |
| `https://app.example.test/home` | Cùng origin |
| `https://app.example.test/api` | Cùng origin |
| `http://app.example.test/home` | Khác origin: scheme khác |
| `https://app.example.test:8443/home` | Khác origin: port khác |
| `https://api.example.test/home` | Khác origin: host khác |
| `https://evil.example.test/home` | Khác origin: host khác |

**Same-Origin Policy (SOP)** giới hạn khả năng JavaScript từ origin này đọc dữ liệu từ origin khác. CORS là cơ chế cho phép server **chủ động chia sẻ một số response với origin khác** thông qua HTTP headers. Quy tắc được trình duyệt thực thi; cURL, Postman hay script backend **không phải trình duyệt** và thông thường không tự áp cùng CORS restrictions.

### 3.1. Simple CORS request và response

Frontend:

```javascript
fetch("https://api.example.test/api/public", {
  method: "GET"
}).then(r => r.json()).then(console.log);
```

Browser tự thêm, trong các ngữ cảnh phù hợp:

```http
GET /api/public HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
```

Server cho phép frontend này đọc response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json

{"status":"ok"}
```

Nếu response **không** cho phép origin ấy, server vẫn **có thể** đã xử lý request và trả HTTP 200, nhưng browser chặn JavaScript truy cập response. Console thường hiện lỗi CORS. Đây không đồng nghĩa “API trả 403”. CORS error có thể xuất hiện từ **chính browser** mặc dù server đã xử lý request.

Đồng thời:

- Một form HTML từ website khác vẫn có thể gửi những request mà browser cho phép gửi cross-origin.
- Image/script/link/navigation có cơ chế tải tài nguyên riêng, không được hiểu giản đơn là mọi resource phải qua fetch CORS.
- Không dùng `Origin` request header như bằng chứng xác thực danh tính: client ngoài browser có thể giả mạo header.
- CORS không ngăn người dùng trực tiếp gọi API bằng cURL nếu không có authentication/authorization ở server.

### 3.2. Preflight OPTIONS là gì?

Các request CORS không thuộc nhóm browser coi là safelisted thường phải **preflight** trước. Ví dụ frontend gửi JSON cùng Authorization và CSRF header:

```javascript
fetch("https://api.example.test/api/documents", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ title: "Spring MVC" })
});
```

Browser có thể hỏi server trước:

```http
OPTIONS /api/documents HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Preflight hợp lệ có thể nhận:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN,Authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Đây là response **minh họa**, không phải chuỗi header byte-for-byte mặc định. Nếu preflight thành công, browser **mới gửi actual POST**; POST sau đó vẫn phải vượt qua authentication, authorization, CSRF và validation bình thường.

**Preflight không phải login và không mang CSRF token của actual request.** Preflight theo Fetch không gửi credentials như session cookie; vì vậy Spring Security cần xử lý CORS trước cơ chế kiểm tra đăng nhập để không từ chối OPTIONS vì vắng session. Preflight cũng không chứng minh người dùng có role `EDITOR`.

### 3.3. Vì sao POST dạng form vẫn nguy hiểm khi CORS bị từ chối?

Một trang độc hại có thể chứa:

```html
<form action="https://bank.example.test/transfer" method="post">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="100">
  <button type="submit">Submit</button>
</form>
```

Đây là ví dụ **tư duy mối đe dọa**, không phải API được khuyến khích triển khai. Nếu người dùng đã đăng nhập ở `bank.example.test` và browser tự gửi cookie hợp lệ trong bối cảnh ấy, server thiếu CSRF protection có thể nhận và xử lý POST. Kẻ tấn công **không cần đọc response** để gây ra chuyển tiền.

Nhiều simple requests (trong cách gọi truyền thống) **không cần preflight**. CORS hạn chế **đọc response** của script ngoài origin, chứ không phải một hàng rào tổng quát chặn mọi yêu cầu có side effect. Cookie `SameSite` có thể chặn cookie trong một số tình huống cross-site, nhưng không phải lý do để bỏ mọi kiểm tra CSRF.

## 4. CORS credentialed requests: origin cụ thể, không dùng wildcard

Credentials có thể gồm cookie và HTTP authentication. Đối với một frontend cross-origin muốn browser gửi cookie, tùy ngữ cảnh cần:

```javascript
fetch("https://api.example.test/api/documents/1", {
  method: "GET",
  credentials: "include"
});
```

Server cho phép origin đó đọc response có credentials:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

**Không kết hợp `Access-Control-Allow-Origin: *` với credentialed request.** Browser sẽ từ chối cho JavaScript đọc response. Khi có nhiều origin tin cậy, server phải kiểm tra allowlist và trả **một origin cụ thể khớp request**, không phản chiếu bất kỳ `Origin` nào không kiểm tra.

Các lưu ý quan trọng:

1. `credentials: "include"` là lựa chọn phía frontend; nó **không thay** xác thực server và không tạo cookie tự động nếu browser/session chưa có.
2. `Access-Control-Allow-Credentials: true` chỉ cho phép JavaScript nhận credentialed response khi origin cũng hợp lệ. Nó **không cấp role**.
3. Cookie cross-site còn chịu chính sách `SameSite`, `Secure`, domain/path, HTTPS và các giới hạn third-party cookies của trình duyệt. CORS thành công **không bảo đảm cookie được gửi**.
4. `Access-Control-Allow-Origin: null` không phải wildcard an toàn; origin `null` có thể phát sinh từ sandbox, file/data URL và các môi trường khó tin cậy.
5. Nếu cache lưu response thay đổi theo origin, cần `Vary: Origin`. Nếu response còn khác nhau theo cookie/login, phải áp dụng `Cache-Control` phù hợp để tránh lộ dữ liệu cá nhân qua shared cache.
6. Tránh `allowedOriginPatterns("*")` cộng `allowCredentials=true` cho nội dung riêng tư: tuy có thể phản chiếu origin theo cấu hình framework, đây thường là **allow-all** không an toàn về mặt chính sách.

**Phân biệt origin và site:** `https://app.example.com` và `https://api.example.com` là **khác origin**, nhưng có thể cùng “site” theo chính sách cookie. `SameSite` và SOP/CORS không đo cùng một ranh giới; một subdomain không đáng tin cậy có thể làm thay đổi phân tích rủi ro CSRF.

## 5. Authentication: ai đang gửi request?

Authentication kiểm chứng danh tính của client/người dùng dựa trên một cơ chế cụ thể, ví dụ:

- Session cookie: browser gửi ID session; server tra session tới principal.
- HTTP Basic: header `Authorization: Basic ...` mang thông tin tài khoản qua encoding Base64 (không phải encryption). **Chỉ dùng với HTTPS thực tế.**
- Bearer token: header `Authorization: Bearer <token>`; server xác thực chữ ký, thời hạn, issuer, audience hoặc introspection theo thiết kế.
- OAuth2/OIDC login: các protocol có token/flow và các bước kiểm chứng; không tự suy ra đó là authorization.
- mTLS/client certificates: xác thực danh tính client ở TLS layer.

Sau khi xác thực, Spring Security có một `Authentication` chứa `principal` và tập `GrantedAuthority`. Controller có thể đọc:

```java
@GetMapping("/api/me")
Map<String, String> me(Authentication authentication) {
    return Map.of("username", authentication.getName());
}
```

*Đây là đoạn minh họa trong controller bảo vệ bởi Spring Security, cần import phù hợp.*

Nếu request thiếu/không hợp lệ credentials khi cần xác thực, API dùng HTTP Basic/Bearer thường phản hồi **401 Unauthorized** cùng cơ chế challenge tương ứng. Với form login, server có thể **redirect tới trang đăng nhập** thay vì 401 JSON. Không suy đoán 401/302 chỉ từ việc thiếu cookie; phụ thuộc `AuthenticationEntryPoint` và request context.

**Không đồng nhất HTTP 401 với CORS:** một frontend có thể thấy lỗi CORS nếu API gửi 401 mà không kèm header cho phép đọc cross-origin; sửa riêng cách tích hợp CORS và authentication. Không mở `/**` thành permitAll chỉ để “hết lỗi CORS”.

### 5.1. Authentication thành công chưa có quyền gì?

Người dùng được xác thực là `reader` nhưng chỉ có role `READER`. Họ được xem tài liệu nhưng **không** được tạo hoặc xóa nếu policy đòi `EDITOR`. Authentication chỉ trả lời “bạn là ai”; hành động còn phải qua authorization.

## 6. Authorization: ai được phép làm gì?

Authorization kiểm tra policy trên **endpoint**, **method**, **resource** và đôi khi **field**:

```text
Principal: reader
Authorities: ROLE_READER
GET /api/documents/1        → allowed
POST /api/documents         → denied

Principal: editor
Authorities: ROLE_EDITOR
GET /api/documents/1        → allowed
POST /api/documents         → allowed nếu CSRF và các điều kiện khác đạt
```

Spring Security cung cấp `authorizeHttpRequests`:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAnyRole("READER", "EDITOR")
    .requestMatchers(HttpMethod.POST, "/api/documents")
        .hasRole("EDITOR")
    .anyRequest().denyAll()
);
```

*Đoạn minh họa cho SecurityFilterChain; ví dụ hoàn chỉnh ở mục 10.*

`hasRole("EDITOR")` mặc định tương ứng authority `ROLE_EDITOR`, không phải string `EDITOR` nếu chưa chỉnh role prefix. `requestMatchers` chỉ bảo vệ theo HTTP path/method phù hợp; controller riêng vẫn cần check ownership và tenant.

### 6.1. Endpoint authorization chưa đủ cho object authorization

Giả sử hai người cùng có role `READER`. API:

```text
GET /api/invoices/101
GET /api/invoices/202
```

Nếu invoice 202 thuộc người khác, policy chỉ `hasRole("READER")` **không đủ**. Cần tra invoice trong phạm vi user/tenant và kiểm tra quyền trên object cụ thể. Đây là rủi ro **Broken Object Level Authorization (BOLA/IDOR)**.

Một mẫu ở service/repository:

```java
// Ý tưởng; không phải chương trình standalone.
Invoice invoice = repository.findById(invoiceId)
        .orElseThrow(NotFoundException::new);
authorizationService.assertCanRead(currentUser, invoice);
return invoice;
```

Với hệ thống multi-tenant, nhiều trường hợp nên query data **đã lọc theo tenant/user** ngay từ DB thay vì fetch object của người khác rồi mới kiểm tra, để giảm lộ metadata. Trả 404 thay vì 403 khi muốn không tiết lộ sự tồn tại là quyết định security/product; đừng dùng 404 như cách thay thế việc kiểm tra quyền thật sự.

### 6.2. 403 không có nghĩa chỉ một lỗi

Cả authorization failure **và CSRF token failure** thường có thể đưa đến HTTP 403. Log/metrics cần tách `AccessDeniedException` do thiếu authority khỏi `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException`. Đừng kết luận người dùng thiếu role chỉ từ status 403.

Nếu CSRF filter nằm trước logic authorization và POST thiếu token, có thể nhận 403 **ngay cả khi người dùng chưa đăng nhập**. Để kiểm tra authentication riêng, thử GET bảo vệ hoặc request state-changing có token hợp lệ.

## 7. CSRF: giả mạo request nhờ credentials tự gắn của browser

CSRF là hành vi website/app khác khiến browser của người dùng đang đăng nhập gửi **request thay đổi trạng thái** tới ứng dụng đích, lợi dụng việc browser có thể tự gửi cookie, HTTP authentication hoặc một số loại credential khác.

Chuỗi tấn công kiểu form:

```text
Nạn nhân đăng nhập https://bank.example
    │
    ├─ Browser lưu session cookie hợp lệ
    │
    ▼
Nạn nhân mở website độc hại https://evil.example
    │
    ├─ Trang độc hại tạo form POST tới bank.example
    ├─ Browser có thể đính session credential theo cookie rules
    ▼
Server bank.example nhận POST
    ├─ Authentication: nạn nhân hợp lệ
    ├─ Authorization: nạn nhân có quyền chuyển tiền
    ├─ Nếu thiếu CSRF protection:
    │     → thực hiện transfer mà người dùng không chủ động thao tác
    └─ Nếu CSRF token sai/thiếu:
          → từ chối trước khi đổi trạng thái
```

**CSRF không đòi attacker đọc response của ngân hàng.** Kẻ tấn công chỉ cần kích hoạt request thành công. Bởi vậy CORS không ngăn được toàn bộ CSRF. Đây là lý do nên yêu cầu token hoặc áp dụng chính sách bảo vệ tương đương cho các phương thức tạo, sửa, xóa khi xác thực dựa vào credentials tự đính kèm.

### 7.1. CSRF token hoạt động thế nào?

Trong mô hình synchronizer token:

1. Server tạo/giữ một token khó đoán gắn với session hoặc ngữ cảnh bảo mật.
2. Frontend **hợp lệ** nhận token qua form HTML/meta/API endpoint được bảo vệ bởi SOP/CORS chính sách chặt chẽ.
3. Khi gửi POST/PUT/PATCH/DELETE, frontend gửi token trong hidden field hoặc header như `X-CSRF-TOKEN`.
4. Server so sánh/verify token với token kỳ vọng. Sai hoặc thiếu → request bị từ chối.

Ví dụ request:

```http
POST /api/documents HTTP/1.1
Cookie: JSESSIONID=<session-cookie>
X-CSRF-TOKEN: <token-đã-được-cấp>
Content-Type: application/json

{"title":"Tài liệu mới"}
```

Một website tấn công có thể khiến browser gửi session cookie trong một số bối cảnh, nhưng thông thường **không đọc được token bí mật từ origin đích** nếu SOP, CORS, XSS protections và cách cấp token được giữ đúng. Token không phải authentication: nắm token mà không có danh tính hợp lệ cũng chưa có quyền làm nghiệp vụ.

### 7.2. Spring Security bảo vệ method nào theo mặc định?

Với Spring Security Servlet mặc định, CSRF protection được bật cho **unsafe HTTP methods**, thường là mọi method trừ:

- `GET`
- `HEAD`
- `OPTIONS`
- `TRACE`

Tức `POST`, `PUT`, `PATCH` và `DELETE` thường yêu cầu CSRF token khi bật CSRF filter. Các phương thức an toàn **không được dùng để thay đổi trạng thái nghiệp vụ**: nếu server dùng GET để xóa data, attacker có thể kích hoạt URL ảnh/link ngay cả khi CSRF configuration xem GET là safe.

“Preflight OPTIONS không cần CSRF” **không** có nghĩa “actual POST không cần CSRF”. Hai request khác nhau về mục đích và credentials.

### 7.3. CSRF có cần cho stateless JWT/Bearer API?

Phụ thuộc **cách credential được gửi**, không chỉ phụ thuộc chữ “JWT”, “REST” hay “stateless”:

| Thiết kế | Browser tự gửi credential qua cross-site request? | Đánh giá CSRF |
| --- | --- | --- |
| Session cookie dùng cho login | Có thể, theo cookie policy | **Cần bảo vệ CSRF** cho state changes |
| HTTP Basic mà browser lưu credentials và gửi tự động | Có thể | **Không mặc định được tắt CSRF** |
| JWT nằm trong cookie tự đính kèm | Có thể | **Vẫn có nguy cơ CSRF** |
| Access token chỉ được JS chủ động gắn trong `Authorization: Bearer ...`, không có ambient cookie/basic auth | Attacker site thường không có token để đính header hợp lệ | CSRF theo kiểu classic thường giảm mạnh; có thể cân nhắc tắt CSRF **cho API đáp ứng thật sự giả định này** |
| Mixed-mode: Bearer header + session cookie ở endpoint khác | Có đường gửi credential tự động | Cần phân loại từng security chain/endpoint; đừng tắt toàn cục |

Nếu token được JS cất trong `localStorage` hoặc memory, nguy cơ **XSS/token theft** là một vấn đề khác; không nói “không cần CSRF” đồng nghĩa “đã an toàn mọi mặt”. Refresh token trong cookie cũng có thể tạo CSRF surface dù access token nằm trong memory.

### 7.4. SameSite và các lớp bổ sung

Cookie `SameSite=Lax`/`Strict` giảm nhiều trường hợp gửi cookie cross-site, nhưng:

- SameSite và **same-origin** khác nhau; các subdomain cùng site không mặc nhiên đáng tin.
- Một số flow cần cookie cross-site, thường yêu cầu `SameSite=None; Secure` và HTTPS, đồng thời bị third-party-cookie policies của browser chi phối.
- Các hành vi navigation/redirect, legacy browser và đường đăng nhập có tính chất riêng.
- Với request có credentials nhạy cảm, nên kết hợp token, strict origin policy, secure cookies và các biện pháp phù hợp.

Ngoài token, có thể kiểm tra `Origin`/`Referer`, Fetch Metadata headers như `Sec-Fetch-Site` và áp dụng custom request protections; đừng dùng một header tùy ý do non-browser client dễ giả để thay authentication.

### 7.5. Double-submit cookie vs session token

Một số SPA dùng cookie chứa CSRF token và JavaScript đọc giá trị ấy để gửi lại trong một header. Cách này phải được thiết kế đúng (binding/HMAC hoặc framework strategy phù hợp) để tránh cookie injection/subdomain attacks. Trong Spring Security, `CookieCsrfTokenRepository` phục vụ một số mô hình này. Tuy nhiên Spring Security 6 có **deferred token** và **XOR masking** để bảo vệ against BREACH trong rendering; việc đưa token ra SPA cần hiểu `CsrfTokenRequestHandler`, không đơn giản là “copy cookie XSRF-TOKEN vào header” với mọi configuration.

Bài demo ở mục 10 cố ý dùng **mặc định session-based CSRF token** và endpoint GET cấp token cho frontend tin cậy, tránh khẳng định các cấu hình SPA/cookie chuyên biệt luôn hoạt động cùng nhau mà không chỉnh handler.

## 8. Ma trận kết quả: cùng request, nhiều cổng kiểm soát

Xét endpoint:

```text
POST /api/documents
Origin: https://app.example.test
Role cần: EDITOR
CSRF protection: enabled
CORS allowlist: https://app.example.test
```

| Tình huống | CORS | Authentication | Authorization | CSRF | Kết quả phổ biến |
| --- | --- | --- | --- | --- | --- |
| Frontend origin được phép, editor đã login, CSRF token đúng | Pass | Pass | Pass | Pass | 201 Created |
| Origin được phép, không có credential, GET endpoint được bảo vệ | Pass | Fail | — | Không áp dụng GET | 401 / login flow |
| Origin được phép, reader có CSRF token hợp lệ, cố POST | Pass | Pass | Fail | Pass | 403 |
| Origin được phép, editor cố POST nhưng thiếu CSRF token | Pass | Pass | Pass theo role | Fail | 403, không tạo dữ liệu |
| Origin lạ, CORS preflight POST không được phép | Fail | Không đánh giá identity ở preflight | — | — | Browser không gửi actual POST; preflight server có thể 403 |
| Origin lạ, simple form POST và credentials tự gửi được | Browser không đọc response | Có thể pass | Có thể pass | Fail nếu CSRF bảo vệ đúng | Server chặn request làm thay đổi trạng thái |
| CORS allow-all public endpoint, không cần login | Pass | N/A | Public | N/A nếu chỉ đọc | Client có thể đọc public response |

**Không thể xác định chính xác một status duy nhất** cho toàn ma trận nếu chưa biết entry point, filter order, preflight type, CSRF policy, resource rules và browser cookie behavior. Ma trận là mô hình giải thích cho ứng dụng điển hình, không phải quy tắc bắt buộc mọi Spring Security app.

### 8.1. 401, 403 và lỗi CORS khác nhau ở đâu?

**401** nghĩa server cần credentials hợp lệ cho resource. Thường có `WWW-Authenticate` khi dùng Basic/Bearer.

**403** nghĩa server hiểu request nhưng từ chối; có thể vì thiếu authority, CSRF token sai hoặc filter khác. Authentication chưa thành công cũng có thể nhận 403 ở một số luồng, nhất là CSRF kiểm tra unsafe method.

**CORS failure** là browser chặn truy cập response hoặc bỏ actual request vì preflight không đạt. Không nhất thiết có HTTP 403: server có thể trả 200 nhưng thiếu header CORS; JavaScript vẫn thấy lỗi. Network tab/backend logs giúp phân biệt.

## 9. SecurityFilterChain: thứ tự xử lý quan trọng

Spring Security Servlet triển khai bằng filter chain (`FilterChainProxy`). MVC controller được gọi **sau** các kiểm tra trong security filters khi request đi qua chain.

Luồng khái niệm:

```text
Browser
  → Servlet container
    → Spring Security FilterChainProxy
       → CORS xử lý trước auth (khi tích hợp đúng)
       → Authentication filters / SecurityContext
       → CSRF token validation cho unsafe methods
       → Authorization decisions
       → DispatcherServlet
          → Spring MVC controller
          → HTTP response
```

Trên thực tế Spring Security có nhiều filters và thứ tự chính xác phụ thuộc version/security chains; sơ đồ **không** cam kết mọi ứng dụng dùng đúng bốn filters với thứ tự minh họa trên. Hãy dùng cấu hình Spring Security thay vì tự tạo nhiều Servlet Filter cạnh tranh thứ tự.

### 9.1. Tại sao CORS phải được xử lý trước authentication?

Preflight không gửi cookie xác thực. Nếu ứng dụng bắt preflight phải có login/session, browser không thể thực hiện cross-origin POST hợp lệ. Spring Security hướng dẫn tích hợp CORS bằng `CorsConfigurationSource` (ví dụ `UrlBasedCorsConfigurationSource`) và `http.cors(...)`, để preflight được xử lý đúng trước authentication.

**Chú ý:** Đừng giải quyết bằng cách tắt authentication cho tất cả endpoints. Chỉ xử lý CORS preflight độc lập; actual requests vẫn yêu cầu credentials/roles/CSRF theo policy.

### 9.2. Spring MVC @CrossOrigin và cấu hình Security

`@CrossOrigin` có thể khai báo CORS cho controller/method MVC. `WebMvcConfigurer#addCorsMappings` khai báo CORS chung ở Spring MVC layer. Nhưng khi dùng Spring Security, đặc biệt với preflight, cần tích hợp CORS đúng vào Security filter chain. Một `CorsConfigurationSource` tường minh giúp thống nhất policy ở filter layer.

Ví dụ:

```java
@CrossOrigin(origins = "https://app.example.test")
@GetMapping("/api/public")
String example() { return "public"; }
```

Đây là đoạn minh họa; **nó không tự cấp quyền truy cập** cho endpoint được bảo vệ. Nếu SecurityFilterChain từ chối vì chưa auth, thêm `@CrossOrigin` không làm user trở thành authenticated. Nếu đồng thời khai báo nhiều nguồn CORS, cần kiểm tra có bị xung đột/override policy hay không.

## 10. Ứng dụng Spring Boot 3 + Java 17: tích hợp đủ bốn lớp

Demo sử dụng:

- HTTP Basic để tạo danh tính `reader` và `editor` dễ quan sát. Password dạng `{noop}` **chỉ dành cho demo**, không dùng production.
- URL authorization: GET document cho READER hoặc EDITOR; POST tạo document chỉ cho EDITOR.
- CORS allowlist một origin `https://app.example.test`; credentialed responses có explicit origin.
- CSRF **bật mặc định** trên unsafe methods; demo tạo CSRF token qua GET trong cùng session.
- `MockMvc` để chứng minh 401, 403 do role, 403 do CSRF, 201 thành công, preflight cho phép/từ chối và allowed-origin response.
- Repository tạm dùng ConcurrentHashMap để tránh setup database; chỉ minh họa security behavior.

### 10.1. Cấu trúc dự án

```text
cors-auth-csrf-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── WebSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DocumentController.java
    └── test/java/example/
        └── SecurityBoundaryTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cors-auth-csrf-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 10.3. WebSecurityDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSecurityDemoApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java

```java
package example;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .cors(Customizer.withDefaults())
                // CSRF đang bật theo mặc định; ghi tường minh
                // để không hiểu nhầm REST API luôn tắt CSRF.
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                            HttpMethod.GET, "/api/csrf")
                        .authenticated()
                    .requestMatchers(
                            HttpMethod.GET, "/api/documents/**")
                        .hasAnyRole("READER", "EDITOR")
                    .requestMatchers(
                            HttpMethod.POST, "/api/documents")
                        .hasRole("EDITOR")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(
                "https://app.example.test"));
        config.setAllowedMethods(List.of(
                "GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password("{noop}editor-pass")
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }
}
```

**Phân tích các phần:**

- `http.cors(Customizer.withDefaults())` tích hợp CORS vào Spring Security. Bean kiểu `UrlBasedCorsConfigurationSource` xác định mapping dưới `/api/**`.
- `setAllowedOrigins(...)` chỉ nhận origin đã khai báo; không dùng wildcard khi `allowCredentials=true`.
- `setAllowedMethods(...)` nêu các method được CORS chấp nhận, nhưng **không phải** HTTP method authorization; muốn POST cần role EDITOR.
- `setAllowedHeaders(...)` cho phép browser preflight các header thực sự cần gửi.
- `setMaxAge(3600L)` là thời gian browser có thể cache kết quả preflight, không phải thời gian login hoặc CSRF token hết hạn.
- `requestMatchers(GET,...).hasAnyRole(...)` và `requestMatchers(POST,...).hasRole(...)` tạo **authorization policy**, độc lập với CORS.
- `.csrf(...)` giữ default CSRF protection; POST của EDITOR vẫn có thể bị 403 khi thiếu token.
- `httpBasic(...)` tạo phương pháp authentication đơn giản. Browser có thể tự gửi cached Basic credentials, nên không dựa vào chữ “Basic” để bỏ CSRF.
- `{noop}` chứa password rõ là **bài học**, tuyệt đối không dùng ngoài demo. Production dùng password encoder phù hợp, secret handling, TLS, rate limiting và cơ chế quản lý danh tính thật.

### 10.5. DocumentController.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record CreateDocumentRequest(@NotBlank String title) {}

record DocumentResponse(long id, String title) {}

@RestController
public class DocumentController {

    private final AtomicLong nextId = new AtomicLong(2);
    private final Map<Long, DocumentResponse> documents =
            new ConcurrentHashMap<>();

    public DocumentController() {
        documents.put(1L, new DocumentResponse(1L, "Public sample"));
    }

    @GetMapping("/api/documents/{id}")
    ResponseEntity<DocumentResponse> read(@PathVariable long id) {
        DocumentResponse found = documents.get(id);
        return found == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(found);
    }

    @PostMapping("/api/documents")
    ResponseEntity<DocumentResponse> create(
            @Valid @RequestBody CreateDocumentRequest request) {

        long id = nextId.getAndIncrement();
        DocumentResponse doc =
                new DocumentResponse(id, request.title());

        documents.put(id, doc);
        return ResponseEntity.status(HttpStatus.CREATED).body(doc);
    }

    @GetMapping("/api/csrf")
    Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

        // Chạm vào getToken() để deferred token được sinh/lưu.
        return Map.of(
                "token", token.getToken(),
                "headerName", token.getHeaderName());
    }
}
```

Endpoint `GET /api/csrf` **yêu cầu login** theo URL policy rồi trả token cho frontend tin cậy. Token được server tạo trong session khi accessed, browser cần lưu session cookie để gửi cùng POST. Ở Spring Security 6, cơ chế token mặc định có thể dùng **deferred loading và XOR masking**; frontend nên gửi **giá trị token nhận từ endpoint** trong header mà endpoint trả tên, không suy diễn giá trị của cookie độc lập.

**Lưu ý:** endpoint này có thể được đọc bằng JavaScript từ **origin đã allowlist** khi có credentials hợp lệ và CORS headers đúng. Không cache token qua CDN, không ghi token vào analytics/logs/URL. Đây là mô hình minh họa backend+frontend, chưa phải production account/session lifecycle, cookie setup hay persistence.

### 10.6. Chạy bằng Maven và kiểm tra bằng cURL

Dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

GET không có authentication:

```bash
curl -i http://localhost:8080/api/documents/1
```

Kỳ vọng **401 Unauthorized** theo demo HTTP Basic. GET với tài khoản reader:

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/documents/1
```

Kỳ vọng 200, body:

```json
{"id":1,"title":"Public sample"}
```

POST với editor **không có CSRF token**:

```bash
curl -i -u editor:editor-pass \
  -H "Content-Type: application/json" \
  -d '{"title":"Tài liệu mới"}' \
  http://localhost:8080/api/documents
```

Kỳ vọng **403 Forbidden** vì CSRF; editor đã đúng role nhưng điều đó không loại bỏ yêu cầu token.

Lấy token gắn với session và dùng lại. Ví dụ trên shell POSIX có Python 3:

```bash
curl -sS -u editor:editor-pass -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

TOKEN=$(python3 -c \
  'import json; print(json.load(open("csrf.json"))["token"])')

curl -i -u editor:editor-pass -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Tài liệu mới"}' \
  http://localhost:8080/api/documents
```

Kỳ vọng **201 Created** với body có `id` được cấp và title vừa gửi. ID có thể thay đổi giữa các lần chạy/test nên không hardcode một số cho mọi request. Với Windows PowerShell, dùng `curl.exe`, cú pháp biến và đọc JSON của PowerShell thay cho lệnh shell POSIX ở trên.

**Quan trọng:** cURL **không cưỡng chế CORS như browser**. Nếu bạn tự gửi header `Origin: https://evil.example.test` bằng cURL mà vẫn thấy response/status nào đó, nó không chứng minh browser được phép đọc. Muốn test CORS, cần xác nhận các response headers với preflight và thử trong browser origin tương ứng.

### 10.7. Frontend fetch minh họa

Giả sử website tin cậy đã có phương thức authentication phù hợp và browser giữ credentials cần thiết. Logic client có thể:

```javascript
const api = "https://api.example.test";

const csrfResponse = await fetch(api + "/api/csrf", {
  credentials: "include"
});
if (!csrfResponse.ok) throw new Error("Cannot read CSRF token");

const csrf = await csrfResponse.json();

const saveResponse = await fetch(api + "/api/documents", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ title: "New document" })
});
if (!saveResponse.ok) throw new Error("Cannot create document");
```

**Đây là pseudocode luồng frontend**, không phải một demo browser đăng nhập Basic tự động hoàn chỉnh. Browser cần được xác thực trước; môi trường cross-site cookies phải đáp ứng SameSite/Secure policies; khi dùng HTTP Basic, có thể cần login/challenge/Authorization thích hợp. Không dùng ví dụ để kết luận chỉ thêm `credentials: "include"` là tạo được session hay tự đăng nhập.

Trong trang chạy cùng origin với API, thường **không cần CORS**. CORS chỉ liên quan khi scheme/host/port khác nhau. Không bật CORS rộng chỉ vì dùng fetch.

## 11. MockMvc: kiểm thử tách riêng bốn cổng bảo vệ

File `src/test/java/example/SecurityBoundaryTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void protectedGetWithoutAuthenticationIs401() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.title").value("Public sample"));
    }

    @Test
    void readerCannotPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("reader", "reader-pass"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden document\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("editor", "editor-pass"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Missing CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("editor", "editor-pass"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Allowed document\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Allowed document"));
    }

    @Test
    void allowedPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/documents")
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "POST")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "authorization,content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.test"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                    "true"));
    }

    @Test
    void deniedOriginFailsPreflight() throws Exception {
        mvc.perform(options("/api/documents")
                    .header(HttpHeaders.ORIGIN,
                            "https://evil.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void allowedOriginCanReadAuthenticatedResponse() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("reader", "reader-pass"))
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.test"));
    }

    @Test
    void csrfEndpointNeedsLoginAndReturnsToken() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/csrf")
                    .with(httpBasic("editor", "editor-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }
}
```

**Điểm học tập của từng test:**

- `protectedGetWithoutAuthenticationIs401`: lỗi **authentication**, không phải CORS.
- `readerCannotPostEvenWithValidCsrf`: role không đủ → lỗi **authorization**; token không cấp quyền.
- `editorCannotPostWithoutCsrf`: danh tính/role đúng nhưng thiếu **CSRF token** → 403.
- `editorCanPostWithCsrf`: đủ các điều kiện liên quan → 201.
- `allowedPreflightDoesNotRequireLogin`: **CORS OPTIONS** có thể đạt dù không có session/login.
- `deniedOriginFailsPreflight`: policy CORS từ chối origin; không suy ra authentication của request thực.
- `allowedOriginStillNeedsAuthentication`: allowlist origin không làm user authenticated.
- `csrfEndpointNeedsLoginAndReturnsToken`: token issuance qua endpoint được bảo vệ.
- Các GET với `Origin` xác minh header CORS mà vẫn giữ policy authentication/authorization.

**Giới hạn:** MockMvc không chạy browser SOP/CORS enforcement. Nó kiểm tra **server response headers và Spring Security decisions**, chứ không thể mô phỏng hoàn toàn browser sẽ chặn JavaScript đọc response thế nào. Với integration test end-to-end, dùng browser thật ở hai origins, proxy/HTTPS và cookie settings như production.

## 12. Tắt CSRF chỉ khi có cơ sở rõ ràng

Đôi khi người phát triển chép:

```java
http.csrf(csrf -> csrf.disable());
```

vì “REST dùng JSON nên CSRF không cần”. **Đây là kết luận sai:** một endpoint dùng JSON vẫn có thể dùng session cookie, browser HTTP Basic hoặc JWT trong cookie. Media type JSON không quyết định có CSRF risk hay không; một số attack đường qua simple requests, content-type coercion, upload/form route, login/logout endpoint hoặc cấu hình sai vẫn có thể tạo side effect.

Chỉ cân nhắc tắt CSRF ở **một security chain/endpoint thực sự stateless** khi xác định rằng credentials **không bao giờ được browser tự đính kèm** và các cross-site requests không thể thừa hưởng quyền của user. Khi đó vẫn phải giữ authentication/authorization, HTTPS, token validation, CORS allowlist hợp lý và XSS protection.

Ví dụ cấu hình **minh họa riêng** cho API OAuth2 Resource Server:

```java
// Chỉ phù hợp nếu request không chấp nhận ambient credentials
// và auth bắt buộc là Bearer header được cấp hợp lệ.
http.securityMatcher("/stateless/**")
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

*Không chèn đoạn này vào dự án Boot chạy ở mục 10. Để chạy cần OAuth2 Resource Server dependency, JwtDecoder/issuer configuration và authorization policy đầy đủ.* Dùng nhiều SecurityFilterChain cần hiểu matcher/order của từng chain, không vô tình tạo endpoint chưa được bảo vệ.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xem CORS là cơ chế xác thực | Origin được phép nhưng anonymous có thể gọi nếu API permitAll | Bảo vệ endpoint bằng authentication |
| Xem CORS allowlist là authorization | User role không đủ vẫn mong được sửa | Kiểm tra role/authority/ownership ở server |
| Xem CORS là CSRF prevention | Form/simple request có thể gây side effect dù script không đọc response | Bật CSRF protection nếu có ambient credentials |
| Chặn OPTIONS preflight bằng login | Browser không gửi actual POST dù user đã login | Tích hợp CORS trước Security auth |
| Mở `Access-Control-Allow-Origin: *` + credentials | Browser từ chối credentialed response | Origin cụ thể từ allowlist; policy đúng |
| Phản chiếu mọi Origin cùng `Access-Control-Allow-Credentials: true` | Bất kỳ origin nào có thể đọc credentialed data | Allowlist nghiêm ngặt, không phản chiếu tùy ý |
| Thấy 403 thì chắc thiếu role | CSRF failure cũng thường 403 | Tách Missing/InvalidCsrfToken khỏi authorization denial |
| Thấy lỗi CORS thì API chắc trả 403 | Server có thể trả 200 nhưng JS không được đọc | Xem Network tab, OPTIONS/actual response headers |
| Chỉ bảo vệ `/api/**` bằng role | IDOR/BOLA với dữ liệu của user khác | Kiểm tra permission từng object/tenant |
| Dùng JWT trong cookie rồi tắt CSRF | Browser có thể tự gửi JWT cookie | Bảo vệ CSRF như session cookie |
| Dùng HTTP Basic mà coi luôn stateless an toàn CSRF | Browser có thể cache/gửi credential tự động | Phân tích browser credential behavior; giữ CSRF khi cần |
| Dùng `{noop}` cho mật khẩu thật | Lộ password khi config/DB bị đọc | Hash bằng encoder mạnh, TLS, secret policy |
| Client gửi `credentials:"include"` nhưng không thấy cookie | SameSite/Secure/third-party-cookie policy | Kiểm tra cookies, HTTPS và domain/path |
| Cho GET thực hiện cập nhật state | GET thường không CSRF-check, dễ bị trigger | Chuyển side effect sang unsafe methods |
| Tin `Origin` request header như danh tính | Non-browser có thể giả header | Authentication riêng bằng credentials |
| Chỉ dựa vào SameSite khi có subdomain không tin cậy | Same-site khác same-origin; có thể bị khai thác | Token, origin policy, trust boundaries |
| Token CSRF lộ qua log, URL, CDN | Attacker có thể tái sử dụng token | Không log/cache/shared expose; kiểm soát nơi cấp |
| Vô hiệu hóa toàn bộ CSRF để test 201 | Bỏ lớp bảo vệ production | Dùng test `with(csrf())` và sửa client token flow |
| Phát CORS headers cho lỗi nhưng quên auth | Frontend đọc 401/403 được nhưng data chưa an toàn | CORS, auth, authorization là các lớp tách biệt |
| Dùng browser localStorage cho bearer rồi khẳng định không có rủi ro | XSS có thể lấy access token | Hardening XSS, CSP, token rotation, hạn chế scope |
| Cho mọi method/header/origin tùy ý | Cross-origin attack surface quá rộng | Chỉ allowlist origins/methods/headers cần dùng |

## 14. Checklist triển khai thực tế

1. **Threat model**: app browser hay machine-to-machine? Credentials có tự được đính kèm không?
2. **Phân loại endpoint**: public GET, authenticated read, write, admin, object ownership, upload, login/logout.
3. **Chọn authentication**: session+form login, OIDC, HTTP Basic nội bộ, Bearer JWT/OAuth2, mTLS…; không trộn không kiểm soát.
4. **Authorization**: URL policy deny-by-default và checks ở service cho tenant/ownership; kiểm soát method/object/field.
5. **CORS**: chỉ cho origins tin cậy, methods/headers cần thiết; credentialed origins không dùng `*`; preflight đi trước auth.
6. **CSRF**: giữ protection cho browser dùng cookie/ambient credentials; client nhận và gửi token an toàn.
7. **HTTP semantics**: GET/HEAD không tạo state; unsafe methods có validation, transaction, audit.
8. **Cookies và sessions**: `HttpOnly`, `Secure`, `SameSite`, session fixation/logout, cookie scope, third-party cookie policies.
9. **Headers và caching**: `Vary: Origin`, private/no-store cho dữ liệu cá nhân/CSRF token; HTTPS và HSTS phù hợp.
10. **XSS**: CSRF token không chống được XSS; escape HTML, tránh unsafe eval/inline scripts, CSP.
11. **Test**: 401 anonymous, 403 reader write, 403 missing CSRF, 201 editor+token, preflight allowed/denied, origin vs role, object-level ownership.
12. **Quan sát lỗi**: log request ID, endpoint, authenticated principal/authority theo chính sách privacy và loại policy failure; không log token, password, session cookie.
13. **Deploy**: HTTPS trên reverse proxy và chính xác scheme/origin; cấu hình forwarded headers đúng để CORS/redirect/cookies không lệch.
14. **Browser thực**: test credentialed fetch, OPTIONS, SameSite cookies trên domains thật; MockMvc chưa đủ để kết luận browser behavior.

## 15. Tự kiểm tra kiến thức

**1.** Frontend tại `https://app.example.test` gọi `https://api.example.test` có phải cross-origin không?  
**Đáp án:** Có, host khác; dù có thể same-site ở một số chính sách cookie.

**2.** Server trả HTTP 200 nhưng thiếu `Access-Control-Allow-Origin`, browser JS đọc body được không?  
**Đáp án:** Không theo CORS nếu cross-origin. Server có thể đã xử lý request.

**3.** Cho phép CORS với origin X có làm user từ X tự đăng nhập không?  
**Đáp án:** Không. Authentication cần credentials hợp lệ.

**4.** User đã xác thực nhưng thiếu role EDITOR, CORS và CSRF đều hợp lệ; POST tạo document được không?  
**Đáp án:** Không. Authorization phải từ chối.

**5.** Editor đã login và có quyền tạo document nhưng thiếu CSRF token, kết quả trong demo?  
**Đáp án:** HTTP 403, không tạo document.

**6.** Preflight OPTIONS có cần session cookie không?  
**Đáp án:** Thông thường không có credentials theo browser CORS preflight, nên CORS phải được xử lý trước auth.

**7.** Vì sao CORS không thay thế CSRF?  
**Đáp án:** Browser có thể gửi một số cross-origin requests gây side effect dù attacker không đọc được response.

**8.** `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` cho credentialed fetch có hợp lệ không?  
**Đáp án:** Không, browser không chấp nhận wildcard origin cho credentialed response.

**9.** Browser gửi cookie tự động còn API dùng JWT trong cookie. CSRF có thể tồn tại không?  
**Đáp án:** Có, vì JWT trong cookie vẫn có ambient credential behavior.

**10.** Bearer header do JS tự đính và server tuyệt đối không dùng cookie/basic credentials có cần CSRF kiểu session không?  
**Đáp án:** Có thể giảm/không cần classic CSRF trong threat model đó, nhưng vẫn cần các bảo vệ authentication, authorization, CORS, XSS và token security.

**11.** CORS preflight POST thành công có chứng minh user đủ quyền POST không?  
**Đáp án:** Không. Actual POST vẫn cần login/role/token.

**12.** HTTP 403 có luôn là lỗi authorization không?  
**Đáp án:** Không. CSRF failure và nhiều policy violations khác cũng có thể gây 403.

**13.** GET yêu cầu authentication sai thường trả gì trong HTTP Basic API?  
**Đáp án:** 401, thường có `WWW-Authenticate`.

**14.** URL authorize rule `hasRole("READER")` đủ để ngăn người đọc invoice của user khác không?  
**Đáp án:** Không; cần object-level/tenant ownership authorization.

**15.** Cookie `SameSite=Lax` có tự biến mọi cross-origin request thành an toàn không?  
**Đáp án:** Không, SameSite khác SOP/CORS, policy phụ thuộc điều hướng/context và còn rủi ro khác.

**16.** Vì sao không dùng cURL để “chứng minh browser không gặp CORS”?  
**Đáp án:** cURL không tự enforce browser SOP và CORS.

**17.** Với Spring Security test, vì sao dùng `with(csrf())` trong POST?  
**Đáp án:** Giả lập CSRF token hợp lệ để test tiếp authorization/controller thay vì bị filter từ chối trước.

**18.** Login bằng HTTP Basic mà request vẫn bị 403 khi tạo document, nên kiểm tra gì?  
**Đáp án:** CSRF token và role/policy, sau đó validation và exception logs; không chỉ CORS.

**19.** `X-CSRF-TOKEN` có phải là bearer access token không?  
**Đáp án:** Không. CSRF token chứng minh request hợp lệ theo policy chống giả mạo; nó không thay authentication.

**20.** CORS allowlist chỉ có `https://app.example.test`, request từ website độc hại có thể gọi API qua backend script không?  
**Đáp án:** Có thể gửi HTTP request ở ngoài browser; server phải dùng authentication/authorization để bảo vệ, không dựa vào CORS.

## 16. Tài liệu gốc nên đọc

- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS trước Spring Security, integration với `UrlBasedCorsConfigurationSource`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token repository, deferred token, request handler và kiểm thử.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, rules theo URL/method và authorities.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, principal, authorities và SecurityContext.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `SecurityMockMvcRequestPostProcessors.csrf()`.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS trong Spring MVC.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): origin, preflight, credentials và browser enforcement.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): ranh giới scheme/host/port.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer/double-submit tokens, SameSite, origin checks.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default và object-level permissions.

**Quy tắc cuối cùng:** **CORS** quyết định browser JS origin nào được chia sẻ response; **authentication** xác định danh tính; **authorization** kiểm tra quyền cụ thể; **CSRF protection** kiểm tra request làm thay đổi trạng thái có bị website khác giả mạo nhờ credentials tự gửi hay không. Bảo mật web đúng là **sự phối hợp của cả bốn**, không phải bật một header rồi coi các lớp khác đã xong.
