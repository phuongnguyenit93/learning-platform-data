# Cookie không được gửi do Secure, SameSite, Domain hoặc Path

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Một cookie đã xuất hiện trong response nhưng request tiếp theo vẫn là anonymous

Ứng dụng Spring Boot phục vụ giao diện tại `https://app.example.com` và API tại `https://api.example.com`. Sau khi đăng nhập, người dùng thấy:

~~~http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=SESSION_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /dashboard
~~~

Nhưng request tiếp theo tới `/api/profile` lại không có `JSESSIONID`:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Kết quả có thể là HTTP 401, 302 tới login hoặc 403 tùy security chain, phương thức HTTP và filter xử lý. Developer thường nghĩ Spring Security mất authentication, CSRF token sai hoặc thiếu quyền, dù lỗi nằm ở một bước trước: **browser không gửi cookie phiên tới endpoint đó**.

Để điều tra chính xác, phải phân biệt:

1. **Server có phát cookie không?** Response có header `Set-Cookie` thực sự không?
2. **Browser có chấp nhận và lưu cookie không?** Header có thể bị từ chối vì `Secure`, `Domain`, `SameSite=None` thiếu `Secure`, prefix hoặc chính sách browser.
3. **Cookie đã lưu có đủ điều kiện để được gửi trong request cụ thể không?** Browser xét hostname, path, HTTPS, same-site context, thời hạn và loại request.
4. **Request có dùng credentials mode phù hợp không?** `fetch` cross-origin không tự động gửi cookie theo cách lập trình viên mong đợi.
5. **Backend có nhận đúng cookie và phục hồi session không?** Cookie được gửi không chứng minh session còn trong store hoặc security chain đúng.

**Mục tiêu học tập:** đọc đúng `Set-Cookie`/`Cookie`, phân biệt `Secure`, `SameSite`, `Domain`, `Path` và `HttpOnly`, hiểu site so với origin, chẩn đoán CORS/CSRF/SSO và proxy TLS, cấu hình và kiểm thử trên Spring Security **Servlet** lẫn **Reactive/WebFlux**, khắc phục mà không nới cookie hoặc tắt phòng vệ một cách tùy tiện.

## 2. Ba sự thật khác nhau: phát, lưu và gửi cookie

Đây là mô hình quyết định đơn giản:

~~~mermaid
flowchart TD
    A[Server trả HTTP response] --> B{Có Set-Cookie?}
    B -- Không --> C[Kiểm tra session creation, auth, handler, proxy]
    B -- Có --> D{Browser chấp nhận cookie?}
    D -- Không --> E[Kiểm tra Secure, Domain, SameSite, prefix, expiry, policy]
    D -- Có --> F[Cookie được lưu trong cookie jar]
    F --> G{Request tiếp theo có đủ điều kiện gửi?}
    G -- Không --> H[Scheme, host, Path, SameSite, credentials, policy]
    G -- Có --> I[Request có Cookie header]
    I --> J{Backend khôi phục đúng session?}
    J -- Không --> K[Session timeout, store, node, cookie name, chain]
    J -- Có --> L[Authentication, CSRF, authorization, controller]
~~~

Trong DevTools, hãy kiểm tra **cả hai phía**:

| Điểm quan sát | Câu hỏi cần trả lời | Chưa thể kết luận |
|---|---|---|
| Response Headers | `Set-Cookie` có tên và attributes gì? | Browser chắc chắn đã lưu |
| Network → Cookies/Issues | Browser có báo cookie bị loại, chặn, hoặc giới hạn không? | Cookie chắc chắn sẽ được gửi ở mọi request |
| Application/Storage → Cookies | Cookie được lưu cho hostname/path nào? | Cookie đã được gửi ở request đang lỗi |
| Request Headers/Cookies | `Cookie` được gửi thực tế không? | Server đã khôi phục session hợp lệ |
| Spring/server logs | Có session/principal và chain nào xử lý? | Chỉ cần điều chỉnh cookie |

Một dòng `Set-Cookie` trong response **không tương đương** một dòng `Cookie` trong request tiếp theo. Đây là sai lầm phổ biến nhất khi tìm lỗi “tự logout”.

## 3. Cấu trúc một Set-Cookie và ý nghĩa từng phần

Ví dụ một cookie phiên:

~~~http
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thành phần | Vai trò | Điều nên kiểm tra |
|---|---|---|
| `JSESSIONID` | Tên cookie, có thể tùy biến | Backend đang tìm cookie tên nào? |
| `opaque-session-id` | Giá trị nhận diện session, phải được xem là bí mật | Không log hoặc chia sẻ nguyên giá trị |
| `Secure` | Chỉ gửi cookie trên kênh an toàn theo chính sách browser | HTTP/HTTPS và TLS termination |
| `HttpOnly` | Không cho JavaScript đọc cookie qua API như `document.cookie` | Không đồng nghĩa browser không gửi |
| `SameSite=Lax` | Giới hạn gửi cookie theo ngữ cảnh site | Top-level navigation so với cross-site subrequest |
| `Path=/` | Chỉ các request có path phù hợp mới nhận cookie | Reverse proxy prefix, API path |
| `Domain` (nếu có) | Xác định host và các subdomain đủ điều kiện | Host-only hay domain cookie? |
| `Max-Age`/`Expires` (nếu có) | Thời gian sống ở browser | Cookie đã bị xóa/hết hạn? |

Một response có thể có **nhiều header `Set-Cookie`**, không phải một chuỗi duy nhất nối bằng dấu phẩy. Khi tìm trong DevTools hoặc test header, không làm mất các header lặp.

### Host-only là mặc định có ích

Nếu response từ `api.example.com` không có thuộc tính `Domain`, cookie thường là **host-only**, chỉ được gửi tới `api.example.com` chứ không tới `app.example.com`. Điều đó không nhất thiết là lỗi: browser có thể gửi cookie **tới API host** khi frontend khác origin gọi đúng API với credentials mode phù hợp.

Đừng đặt `Domain=example.com` chỉ để JavaScript trên `app.example.com` đọc session cookie của API. Session cookie nên được giữ `HttpOnly` và scope hẹp nhất đủ dùng.

## 4. Secure: HTTP công khai và HTTPS public khác nhau

Cookie có thuộc tính `Secure` về nguyên tắc chỉ được gửi qua HTTPS (trong ngữ cảnh được browser coi là an toàn). Ví dụ:

~~~http
Set-Cookie: SESSION=...; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

| Request | Cookie Secure có được gửi? | Lưu ý |
|---|---|---|
| `https://app.example.com/profile` | Có thể, nếu host/path/site và policy khác cũng phù hợp | `Secure` chỉ là một điều kiện |
| `http://app.example.com/profile` | Thông thường không | Cookie Secure không đi qua HTTP công khai |
| `https://api.example.com/profile` | Chỉ khi Domain/host scope phù hợp | HTTPS không xóa giới hạn host |
| `http://localhost:8080` | Một số browser có ngoại lệ riêng cho localhost | Không lấy local làm bằng chứng production |

**Cẩn trọng với môi trường local:** việc browser xử lý cookie Secure ở `localhost` có ngoại lệ theo triển khai. `localhost`, `127.0.0.1` và hostname tùy chỉnh không nhất thiết có cùng cookie/secure behavior; đừng suy kết quả lab HTTP trực tiếp cho domain HTTPS thực.

### Reverse proxy chấm dứt TLS

Kiến trúc:

~~~mermaid
flowchart LR
    B[Browser HTTPS] --> P[Reverse proxy TLS termination]
    P --> S[Spring Boot HTTP upstream]
~~~

Browser phải nhìn thấy **HTTPS public**, trong khi Spring Boot có thể nhìn upstream HTTP. Nếu application cố suy scheme công khai từ kết nối nội bộ mà không cấu hình forwarded headers/trust proxy đúng, nó có thể tạo redirect hoặc cookie attributes sai.

Sửa tại đúng biên:

1. Xác nhận URL công khai và request scheme browser thực thấy.
2. Kiểm tra `Set-Cookie` sau **proxy**, không chỉ ở Spring origin.
3. Cấu hình cookie `Secure` theo mục tiêu HTTPS production.
4. Nếu cần xử lý `Forwarded`/`X-Forwarded-Proto`, chỉ tin dữ liệu do **reverse proxy được kiểm soát** cung cấp; proxy phải loại bỏ header forwarded giả mạo từ client.
5. Kiểm tra login redirect, session cookie và POST có CSRF token xuyên qua proxy.

**Không sửa bằng cách tắt `Secure` của session cookie trong production HTTPS.** Nếu upstream HTTP trong mạng nội bộ nhưng public là HTTPS, cookie vẫn nên được bảo vệ trên đường browser–edge.

## 5. SameSite: “site” không phải “origin”

`SameSite` giúp browser giới hạn gửi cookie trong các tình huống cross-site. Muốn hiểu chính xác, phải biết:

- **Origin:** bộ ba *scheme + host + port*. `https://app.example.com:443` khác origin với `https://api.example.com:443`.
- **Site** (cách xét hiện đại có tính đến scheme): liên quan đến *scheme* và *registrable domain* của URL. Hai subdomain cùng scheme có thể **same-site nhưng cross-origin**.
- **Top-level navigation:** người dùng điều hướng document chính.
- **Subresource/XHR/fetch/iframe:** request trong ngữ cảnh trang đang mở, không phải top-level navigation.

| Từ tài liệu | Đến request | Quan hệ gợi ý |
|---|---|---|
| `https://app.example.com` | `https://api.example.com` | Khác origin, thường same-site |
| `https://app.example.com` | `https://outside.example.net` | Cross-site và cross-origin |
| `http://app.example.com` | `https://app.example.com` | Khác origin và có thể khác site theo schemeful SameSite |
| `https://app.example.com:443` | `https://app.example.com:8443` | Khác origin do port; thường same-site |

Kết luận thiết yếu: **một request có thể cần CORS vì cross-origin dù cookie SameSite không ngăn vì cùng site**.

### Ý nghĩa ba giá trị chính

| SameSite | Tình huống cookie thường được gửi | Tình huống thường bị hạn chế |
|---|---|---|
| `Strict` | Request same-site | Navigation từ site khác và cross-site subrequests |
| `Lax` | Same-site; top-level cross-site navigation dùng method an toàn như GET | Cross-site fetch/XHR, iframe, phần lớn POST cross-site |
| `None` | Có thể được gửi ở cross-site contexts nếu đủ điều kiện khác | Yêu cầu `Secure` theo browser hiện đại, còn chịu third-party cookie restrictions |

Một cookie **không khai báo SameSite** thường được browser hiện đại xử lý gần với `Lax` mặc định; có biến thể tương thích cho cookie mới được cấp trong một số browser. **Không dựa vào ngoại lệ thời gian ngắn hoặc default mơ hồ** để thiết kế luồng POST nhạy cảm.

### Quan trọng: SameSite không tự là CSRF protection đầy đủ

`SameSite=Lax` giúp giảm nhiều request cross-site có cookie, nhưng không thay thế CSRF token cho những ứng dụng còn dùng session/browser credentials. Đặc biệt same-site subdomain có thể không phải cùng origin hoặc cùng trust boundary; XSS và các luồng đăng nhập phức tạp vẫn cần kiểm soát riêng.

## 6. Lax, Strict, None: đối chứng trên request thực

Giả sử người dùng đang ở `https://outside.example.net` và có cookie của `https://app.example.com`:

| Tình huống | Strict | Lax | None + Secure |
|---|---|---|---|
| Browser điều hướng trực tiếp từ site ngoài bằng link GET tới app | Thường không | Thường có | Có thể có |
| Trang site ngoài gọi `fetch("https://app.example.com/api")` | Không | Không | Có thể, nếu credentials/policy phù hợp |
| Site ngoài dùng form POST tới app | Không | Thường không | Có thể theo cookie policy |
| Trang `https://app.example.com` tự gọi cùng site | Có thể | Có thể | Có thể |
| Trang `https://app.example.com` gọi `https://api.example.com` | Không bị loại riêng vì same-site, nếu Domain/host scope đúng | Tương tự | Có thể, nhưng vẫn cần CORS do cross-origin |

Các ô “có thể” còn phụ thuộc `Secure`, `Domain`, `Path`, expiry, partitioning, browser policy, redirect chain và `fetch.credentials`. Đây là **ma trận suy luận**, không phải kết quả test đã đo trên mọi browser.

### Ví dụ bug sau OAuth2/SSO

Một identity provider điều hướng về ứng dụng:

~~~text
IdP (site khác) -> authorization callback của ứng dụng
~~~

Nếu flow sử dụng **top-level GET redirect**, `SameSite=Lax` thường cho cookie trong trường hợp đáp ứng điều kiện. Nhưng nếu callback dùng **form POST cross-site** hoặc được xử lý trong iframe, `Lax`/`Strict` có thể ngăn cookie cần thiết.

Điều này có thể làm session chứa OAuth2 authorization request/`state` không được khôi phục và dẫn tới login thất bại. **Không đổi toàn bộ cookie sang `SameSite=None` theo phản xạ**; trước tiên xác định callback method, site context, cookie scope và rủi ro browser policy, sau đó chọn giải pháp đúng cho flow.

## 7. Domain: host-only, subdomain và trường hợp không được phép đặt Domain

Một server ở `api.example.com` có thể trả:

~~~http
Set-Cookie: SESSION=A; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không có `Domain`: cookie host-only, dành cho `api.example.com`.

Hoặc:

~~~http
Set-Cookie: SESSION=B; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có Domain hợp lệ `example.com` có thể gửi tới `example.com` và subdomain như `api.example.com` hoặc `app.example.com`, miễn các điều kiện khác cũng thỏa.

**Nhưng** cookie rộng domain tăng phạm vi host có thể nhận cookie. Nếu một subdomain yếu bảo mật bị chiếm quyền hoặc vận hành bởi bên không đáng tin, việc chia sẻ session cookie rộng domain có thể gây rủi ro.

### Những tình huống Domain bị browser từ chối hoặc không phù hợp

- Server `api.example.com` cố đặt `Domain=other.example.net`: domain không thuộc phạm vi host được phép.
- Cố đặt `Domain=com` hoặc public suffix: browser từ chối.
- Đặt cookie cho hostname có lỗi chính tả so với request thực.
- Cookie host-only được tạo ở `app.example.com` rồi frontend gọi API `api.example.com` và mong session cookie đi theo.
- Cookie cũ host-only trùng tên với cookie domain-wide mới, tạo hai giá trị cùng tên khi gọi một số path.

Dấu chấm đầu trong `Domain=.example.com` về thực tế được browser hiện đại xử lý như `Domain=example.com`; đừng coi dấu chấm ấy là một cơ chế bảo mật hoặc cách buộc cookie được nhận.

### Không thể chia sẻ cookie giữa các domain tùy ý

`app.example.com` không thể tự đặt session cookie cho `api.another-company.net`. Với frontend và API ở **hai site khác nhau**, cần kiến trúc đăng nhập, cookie/CORS và token bootstrap đúng trust boundary; không thể sửa bằng một `Domain=*` tưởng tượng.

## 8. Path: một dấu / có thể quyết định request có cookie không

Ví dụ:

~~~http
Set-Cookie: SESSION=A; Path=/app; Secure; HttpOnly; SameSite=Lax
~~~

Browser thường gửi cookie cho:

~~~text
/app
/app/
/app/profile
~~~

Nhưng không gửi tới:

~~~text
/api/profile
/application
/logout        (nếu cookie Path chỉ là /app)
~~~

Cookie matching theo Path có quy tắc ranh giới phân đoạn; **không phải mọi đường dẫn bắt đầu bằng cùng vài ký tự đều khớp**.

### Lỗi thường gặp khi dùng reverse proxy prefix

~~~text
Browser:
  GET https://app.example.com/gateway/login
  POST https://app.example.com/gateway/api/profile

Proxy:
  /gateway/... -> /... tại Spring Boot

Spring hoặc container:
  Set-Cookie: JSESSIONID=...; Path=/internal
~~~

Browser không gửi cookie cho `/gateway/api/profile` vì Path không phù hợp, dù backend path sau rewrite có thể đúng. **Browser áp dụng Path theo URL công khai nó gửi**, không theo path upstream mà proxy tạo ra phía sau.

Nếu không khai báo `Path`, browser suy default path từ request URL theo quy tắc cookie. Do đó một cookie được cấp tại route sâu có thể không áp dụng cho endpoint login/logout khác. Với session app dùng nhiều route, chọn Path phù hợp (thường `/` hoặc context path public tương ứng) dựa trên security review.

**Path không phải ranh giới chống truy cập bí mật mạnh.** Cookie Path hỗ trợ scope gửi request, không thay thế phân quyền hay cách cô lập ứng dụng/host.

## 9. HttpOnly, Max-Age, Expires và cookie prefix: được lưu vẫn có thể không dùng được

### HttpOnly không ngăn browser tự gửi cookie

Với:

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

JavaScript:

~~~javascript
console.log(document.cookie);
~~~

có thể **không hiển thị `JSESSIONID`**. Đây là **hành vi bảo vệ đúng** của `HttpOnly`, không phải bằng chứng cookie chưa lưu hay không được gửi. Xem **Network → Request Cookies** hoặc quan sát backend session, không dùng `document.cookie` để kết luận.

Với `CookieCsrfTokenRepository.withHttpOnlyFalse()`, cookie CSRF `XSRF-TOKEN` có thể cần đọc được bằng JS theo chiến lược SPA, nhưng **session cookie** vẫn nên `HttpOnly`.

### Expiration có thể xóa cookie ngay khi vừa nhận

~~~http
Set-Cookie: SESSION=...; Max-Age=0; Path=/; Secure; HttpOnly
~~~

Ví dụ là lệnh **xóa cookie**, không phải phát một phiên mới. Một response login có thể nhận cookie mới ở một bước nhưng một redirect/logout handler sau đó xóa cookie bằng `Max-Age=0` hoặc `Expires` trong quá khứ.

Khi điều tra, kiểm tra **mọi response** trong chuỗi redirect và thứ tự các header `Set-Cookie`. `Max-Age` có ưu tiên so với `Expires` khi cả hai cùng hiện diện theo quy tắc cookie; sai đồng hồ hoặc timezone cũng có thể gây nhầm trong những hệ thống chỉ dùng `Expires`.

Để xóa đúng cookie, thông thường phải khớp tên cùng `Domain` và `Path` tương ứng. Nếu logout xóa cookie với Path khác lúc login, cookie cũ có thể còn lưu, khiến cookie trùng tên hoặc hành vi không nhất quán.

### Prefix là ràng buộc bảo mật, không phải tên trang trí

Browser hỗ trợ cookie prefixes có thể áp dụng quy tắc riêng:

| Prefix | Những điều kiện quan trọng |
|---|---|
| `__Secure-` | Cookie cần `Secure` và được thiết lập từ nguồn bảo mật phù hợp |
| `__Host-` | Cần `Secure`, `Path=/` và **không có `Domain`** (host-only) |

Ví dụ hợp lệ về ý tưởng:

~~~http
Set-Cookie: __Host-SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cố gắng thêm `Domain=example.com` vào cookie `__Host-SESSION`, browser thực thi prefix rules có thể từ chối cookie. **Không bỏ prefix bảo vệ chỉ để khắc phục một lỗi cấu hình**; sửa attributes cho đúng.

### Cookie partitioning và third-party restrictions

Một số browser giới hạn third-party cookies hoặc hỗ trợ cơ chế **partitioned cookies** theo top-level site. Chúng có thể làm cookie không được lưu hoặc không được gửi dù `SameSite=None; Secure` có mặt.

Không nên coi `Partitioned` là công tắc sửa mọi lỗi cross-site. Partition key và hỗ trợ browser thay đổi điều kiện chia sẻ session; cần đánh giá trường hợp thực, security/privacy policy và kiến trúc SSO.

## 10. Fetch credentials: cookie đủ scope vẫn có thể bị bỏ qua

Trang `https://app.example.com` gọi API `https://api.example.com` là **cross-origin**. Với JavaScript:

~~~javascript
await fetch("https://api.example.com/profile");
~~~

`fetch` mặc định dùng credentials mode `same-origin`; đối với request **cross-origin**, browser sẽ không gửi credentials theo cách một request same-origin làm, ngay cả khi cookie có host/Path/SameSite phù hợp.

Nếu kiến trúc đã chủ đích dùng cookie-based authentication cross-origin:

~~~javascript
const response = await fetch("https://api.example.com/profile", {
  method: "GET",
  credentials: "include"
});
~~~

`credentials: "include"` cho phép browser đưa credentials vào request cross-origin **khi cookie policy vẫn cho phép**. Nó không buộc browser bỏ qua `Secure`, `SameSite`, `Domain`, `Path`, chặn third-party cookies hoặc CORS.

| Fetch setting | Ý nghĩa thường gặp |
|---|---|
| `credentials: "omit"` | Không gửi credentials, kể cả same-origin |
| `credentials: "same-origin"` | Gửi credentials cho same-origin request |
| `credentials: "include"` | Cho phép credentials cả cross-origin nếu các chính sách khác chấp nhận |

**Không đổi toàn bộ ứng dụng sang `include`**: chỉ dùng cho API trusted, kết hợp CORS allowlist, CSRF protection và kiểm soát cookie phù hợp.

### Browser không gửi khác với JavaScript không đọc được response

Hai tình huống:

~~~text
Tình huống A:
  Browser không gửi Cookie trong request API
  -> backend có thể coi là anonymous

Tình huống B:
  Browser đã gửi Cookie, server xử lý request
  -> CORS headers sai, JavaScript không được đọc response
~~~

Nếu chỉ xem exception `TypeError: Failed to fetch` ở JavaScript, bạn không biết đang ở A hay B. Cần xem **Network Request Cookies**, response CORS và server logs.

## 11. CORS và SameSite là hai kiểm soát độc lập

Với API credentialed cross-origin, ví dụ:

~~~http
Origin: https://app.example.com
Cookie: SESSION=...
~~~

API có thể cần trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Các giá trị phải phản ánh **origin được phép thật sự**, không được lấy trực tiếp từ input Origin thiếu kiểm soát. `Access-Control-Allow-Origin: *` không tương thích với credentialed CORS responses như mô hình này.

### CORS cho phép không sửa cookie bị SameSite chặn

Nếu frontend ở `https://outside.example.net` gọi API `https://api.example.com`, request là **cross-site**. Cookie `SameSite=Lax` hoặc `Strict` thường không được gửi trong fetch đó, dù API trả CORS allowlist hợp lệ.

Ngược lại, nếu `https://app.example.com` gọi `https://api.example.com` với cookie cùng site và fetch include, SameSite có thể cho phép, nhưng **CORS vẫn phải được cấu hình** vì khác origin.

### Preflight OPTIONS thường không mang cookie

Một request như:

~~~http
OPTIONS /profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

là **CORS preflight**, không phải POST nghiệp vụ. Đừng yêu cầu preflight phải có session cookie mới được chấp nhận. Browser có thể không gửi POST thật nếu preflight bị từ chối.

**Quy trình debug:**

1. Xác nhận OPTIONS có đúng Origin/Method/Headers.
2. Xác nhận CORS configuration của API cho phép chúng.
3. Chỉ khi POST thật được gửi, mới kiểm tra cookie session và CSRF token trên POST.
4. Phân biệt CORS rejection, CSRF rejection và authorization 401/403.

Việc thêm `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` có thể cho authorization đi qua, nhưng **không tự tạo CORS headers phù hợp**. Cần cấu hình CORS processor đúng.

## 12. CSRF: mất session cookie tạo lỗi khác mất CSRF token

Ứng dụng dùng session cookie với form hoặc AJAX:

~~~text
GET /profile:
  Browser gửi JSESSIONID=A
  Server expose CSRF token thuộc phiên A

POST /profile:
  Browser không gửi JSESSIONID
  Client vẫn gửi _csrf hoặc X-CSRF-TOKEN của phiên A
  Server không khôi phục expected token A
  -> thường 403 nếu CsrfFilter từ chối trước các bước khác
~~~

**Đây là lý do quan trọng để xem cả session cookie lẫn CSRF token.** Token được gửi trong POST chưa chứng minh request thuộc đúng session.

### Cookie CSRF khác cookie session

| Cookie | Chức năng | Điều không nên làm |
|---|---|---|
| `JSESSIONID` / `SESSION` | Khôi phục authentication/session | Tắt HttpOnly để JavaScript đọc |
| `XSRF-TOKEN` khi dùng cookie repo | Lưu expected raw CSRF token theo chiến lược phù hợp | Coi tự gửi cookie là đủ thay cho header/parameter |

Với cookie repository dùng raw token, SPA có thể phải đưa giá trị ấy vào `X-XSRF-TOKEN` theo đúng `CsrfTokenRequestHandler`. Khi Spring Security dùng token **XOR-masked** cho HTML nhằm giảm BREACH, raw cookie và masked form có biểu diễn khác. Nếu POST có cả cookie và header mà vẫn 403, cần kiểm tra **handler raw/masked**, không kết luận chắc chắn do `SameSite`.

### Một 403 không chứng minh CSRF

403 cũng có thể xuất phát từ thiếu authority, method security, CORS processor, reverse proxy/WAF hoặc HTTP firewall custom. Nếu cookie không được gửi, GET có thể trả 401 hoặc 302 login, còn POST bị CSRF từ chối sớm thành 403. Cần xác định **filter/handler thực sự trả response**.

## 13. Login, logout và session fixation: chuỗi Set-Cookie thay đổi

Sau login, Spring Security có thể thay session ID để giảm rủi ro **session fixation**. Trong chuỗi redirect, browser có thể nhận:

~~~text
GET /login       -> cookie anonymous session (nếu được tạo)
POST /login      -> authentication success + session ID change
302 /dashboard   -> Set-Cookie session ID mới
GET /dashboard   -> gửi session mới nếu cookie được chấp nhận
POST /profile    -> cùng session mới + CSRF token hiện hành
~~~

Các trường hợp gây lỗi:

- Response login cấp cookie mới với Path khác cookie cũ.
- Cookie mới có `Secure` nhưng browser request tiếp lại dùng HTTP.
- Cookie domain của response mới không đúng host mà request tiếp theo sẽ tới.
- Logout xóa cookie với Domain/Path không khớp cookie lúc login.
- SPA có CSRF token cũ từ trước login; session/cookie mới đã áp dụng.
- Redirect sang host hoặc scheme khác làm `SameSite`/host scope thay đổi.

**Đổi session ID không tự có nghĩa mọi session attribute bị mất.** Session fixation protection và CSRF authentication strategy là hai cơ chế có thể hoạt động đồng thời; CSRF token cũ có thể bị clear sau login, nhưng phải xác minh repository và handler.

### Đừng dán nguyên session ID vào log

Khi chẩn đoán, chỉ ghi có/không cookie, phạm vi, thời điểm và correlation ID. Nếu cần xác minh session đã đổi, có thể dựa vào telemetry nội bộ được bảo vệ, không xuất cookie/session ID vào ticket hoặc ảnh màn hình công khai.

## 14. Session đã được gửi nhưng backend vẫn không khôi phục được

Sau khi nhìn thấy Cookie header trong request, đừng dừng điều tra. Các khả năng:

| Tình huống | Kết quả thường thấy |
|---|---|
| Cookie hết hạn về phía server dù browser chưa xóa | Server không tìm thấy session |
| Session invalidated sau logout | Cookie có thể còn ở browser nhưng không còn state |
| Node A và B có local session store riêng | GET và POST đi khác node, không phục hồi được phiên |
| Session storage TTL/serialization khác nhau | Cookie đúng nhưng session không có hoặc đọc lỗi |
| Backend tìm cookie tên khác | `SESSION` và `JSESSIONID` bị cấu hình lệch |
| Có hai cookie cùng tên, khác Path/Domain | Server có thể đọc giá trị không mong đợi |
| Endpoint đi tới service/security chain khác | Một service không nhận diện phiên của service kia |

Một số hệ thống dùng Bearer token thay vì cookie session. Nếu request không dùng cookie để xác thực, việc thiếu `JSESSIONID` có thể hoàn toàn bình thường; cần xác định **mô hình authentication thực tế** trước khi sửa.

## 15. Cookie của response GET /csrf có thể không giống cookie của login

Trong ứng dụng có CSRF protection:

- GET form/GET `/csrf` có thể tạo session hoặc cookie chứa CSRF token nếu token được materialize.
- Authentication success có thể clear token cũ và phát cookie/session ID mới.
- SPA có thể đọc raw CSRF cookie trước login, sau đó dùng giá trị stale dù session đã đổi.
- `CookieCsrfTokenRepository` khác `HttpSessionCsrfTokenRepository` về nơi expected token được lưu.

Một trình tự kiểm tra tốt:

~~~text
1. GET /login hoặc GET /csrf: session/cookie nào được cấp?
2. POST /login: cookie nào được gửi, cookie nào được set/clear?
3. GET /csrf sau login: materialize token mới chưa?
4. POST /profile: gửi đúng session cookie và CSRF header không?
5. Log: CsrfFilter/WebFilter hay authorization từ chối?
~~~

Không khắc phục một cookie thiếu bằng cách tắt `CsrfFilter`; điều đó có thể che lỗi mà giảm bảo vệ. Cần sửa **cookie delivery và token lifecycle** theo đúng auth flow.

## 16. DevTools: kiểm tra cookie bị chặn ở đâu

DevTools của Chromium/Firefox/WebKit có cách hiển thị khác nhau; tên tab và chuỗi cảnh báo có thể thay đổi. Cách quan sát bền vững:

1. Mở DevTools **trước khi login**, bật Preserve log để giữ chuỗi redirect.
2. Ở **Network**, chọn request đã trả `Set-Cookie`, xem response header và cookie warnings/blocked reasons nếu browser cung cấp.
3. Ở **Application/Storage → Cookies**, xem cookie name, Domain, Path, Expires, Secure, HttpOnly, SameSite và Partitioned nếu có.
4. Chọn **request bị lỗi**, xem **Request Cookies** thật sự đã gửi; đừng suy từ Application/Storage.
5. Kiểm tra URL cuối cùng của request, scheme, host, port và redirect chain.
6. Với cross-origin fetch, đối chiếu `credentials`, CORS preflight, response CORS headers và browser Console.
7. Với POST 403, xem CSRF header/parameter, authentication state và server logs trước khi sửa cookie.

### Bảng ghi nhận không lộ dữ liệu

| Trường | Giá trị minh họa |
|---|---|
| Request ID login | `req-login-17` |
| Response Set-Cookie present | Có |
| Cookie name | `JSESSIONID` |
| Domain scope | Host-only `app.example.com` |
| Path | `/app` |
| Secure / SameSite | `true / Lax` |
| Browser stored? | Có |
| URL request lỗi | `https://api.example.com/profile` |
| Request Cookie present? | Không |
| Fetch credentials mode | `same-origin` |
| Nguyên nhân cần thử | Host-only khác host; cross-origin fetch mặc định không gửi credentials |

Đây là **mẫu suy luận**, không phải log thật. Không dán cookie value, session ID, JWT, Authorization hay CSRF token vào báo cáo.

## 17. Curl cho biết server phát gì, nhưng không mô phỏng SameSite của browser

HTTP client hữu ích để quan sát redirect và cookie headers:

~~~bash
# Lab do nhóm sở hữu: xem response từ đường HTTPS public.
curl -i https://app.example.com/login

# Theo dõi chuỗi redirect, đồng thời dùng cookie jar riêng.
curl -i -L -c cookies.txt -b cookies.txt \
  https://app.example.com/session-lab/start
~~~

Khi dùng `-L`, hãy cẩn trọng với request có authentication, password hoặc secret: redirect có thể dẫn đến hostname khác. Ví dụ trên dùng GET lab; không dùng tuỳ tiện cho request có body hoặc credential nhạy cảm.

Một cookie jar của curl giúp thấy cookie được ghi và có thể được gửi tiếp trong HTTP client. **Nhưng curl không phải browser và không kiểm tra đầy đủ hành vi SameSite/CORS/third-party-cookie restrictions, preflight hoặc CSP**. Do đó:

- Curl gửi cookie thành công không chứng minh browser sẽ gửi trong cross-site fetch.
- Curl nhận `Set-Cookie` không chứng minh browser sẽ lưu cookie có attributes không hợp lệ.
- Curl không tự áp dụng `fetch.credentials` của JavaScript.
- HTTP headers được proxy trả cho curl có thể khác browser nếu Host, TLS hoặc path khác.

Nếu curl thất bại với TLS certificate, điều tra certificate chain/hostname; **không dùng `-k` làm giải pháp triển khai**. Trong lab nội bộ, bảo đảm hostname và certificate phù hợp với môi trường test.

### Tạo hai cookie jars để so sánh

~~~bash
curl -i -c browser-A.cookies -b browser-A.cookies \
  https://app.example.com/session-lab/start

curl -i -c browser-B.cookies -b browser-B.cookies \
  https://app.example.com/session-lab/check
~~~

Jar B không có session của A nên check có thể báo anonymous; đó là phép thử cookie continuity cơ bản. File jar chứa session secret, không commit hoặc gửi qua chat và phải xóa sau khi kiểm thử.

## 18. Spring Boot Servlet: cấu hình session cookie

Với Spring Boot chạy **Servlet** (Spring MVC + servlet container), một cấu hình minh họa cho **production chỉ phục vụ HTTPS công khai**:

~~~properties
# application.properties - ví dụ chính sách session cookie Servlet
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
~~~

Các thuộc tính phù hợp phải được xác nhận theo Spring Boot version, servlet container và việc có dùng Spring Session hay custom cookie serializer không. Nếu một bean hoặc proxy chủ động ghi `Set-Cookie`, **header cuối cùng gửi ra browser** mới là kết quả cần kiểm tra.

**Không đặt Domain rộng mặc định.** Thiếu thuộc tính Domain giúp cookie host-only, thường là lựa chọn an toàn hơn khi chỉ một host phải nhận session cookie. Nếu thật sự cần dùng chung giữa subdomains, hãy review trust boundary rồi cấu hình tường minh, không đặt theo suy đoán.

### Reverse proxy forwarding

Một số deployment dùng:

~~~properties
# Chỉ phù hợp khi app nằm sau reverse proxy đáng tin,
# proxy làm sạch Forwarded/X-Forwarded-* do client giả mạo.
server.forward-headers-strategy=framework
~~~

Hoặc cơ chế native của container/proxy theo kiến trúc đang dùng. **Không coi setting này là cách “bật HTTPS”**: nó chỉ hỗ trợ diễn giải thông tin request qua proxy. Phải có TLS public đúng, tin cậy proxy đúng và test cookie/redirect trên đường public.

### Local development

Một application HTTP local có thể cần cấu hình riêng để kiểm thử chức năng, nhưng việc bỏ Secure ở profile dev **không cho phép bỏ Secure ở production**. Để xác minh cookie Secure thực tế, nên dùng môi trường HTTPS staging với hostname/certificate hợp lệ.

## 19. Servlet: security chain và session lab fixture có kiểm soát

Ví dụ cấu hình bảo vệ cho lab MVC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Các route chỉ tồn tại trong profile test/staging riêng.
            .requestMatchers("/session-lab/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Các route `/session-lab/**` được dùng để chẩn đoán trong môi trường kiểm soát, không nên xuất nguyên trạng trên production.** `permitAll()` ở authorization không có nghĩa tắt `CsrfFilter` cho các unsafe methods; ví dụ lab dùng GET chỉ để khởi tạo/kiểm tra session, không thay đổi nghiệp vụ.

Controller lab chỉ trả trạng thái, không tiết lộ session ID:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletSessionLabController {

    @GetMapping("/session-lab/start")
    Map<String, String> start(HttpSession session) {
        session.setAttribute("lab", "ready");
        return Map.of("session", "started");
    }

    @GetMapping("/session-lab/check")
    ResponseEntity<Map<String, String>> check(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        boolean present = session != null &&
            "ready".equals(session.getAttribute("lab"));
        return present
            ? ResponseEntity.ok(Map.of("session", "present"))
            : ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("session", "absent"));
    }
}
~~~

`start` cố ý tạo session test bằng cách truy cập `HttpSession` và đặt attribute. `check` chỉ đọc session hiện có (không chủ động tạo phiên mới). Endpoint này giúp đo **session continuity**, không phải authentication success và không phải thước đo authorization.

### Phân biệt server-side session với browser cookie

Nếu `GET /session-lab/check` trả 401, có thể:

- Browser không gửi cookie.
- Cookie đã gửi nhưng session không còn hoặc không được khôi phục.
- Request đi tới node/service khác hoặc tên session cookie không đúng.

Đọc server session log, request cookies và đường đi thực tế trước khi kết luận.

## 20. Spring Security Servlet: CORS cho API dùng cookie qua subdomain

Giả sử chỉ frontend `https://app.example.com` được gọi API tại `https://api.example.com` bằng cookie credential. Ví dụ CORS config:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowCredentials(true);
    cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
    ));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Trong Servlet security chain phù hợp:

~~~java
http.cors(Customizer.withDefaults());
~~~

Đây là **một** cách tích hợp CORS cho Spring Security MVC; ở dự án có MVC CORS config sẵn, nhiều security chains hoặc gateway xử lý CORS, phải xem nguồn cấu hình thực tế và tránh phát header mâu thuẫn.

Ở frontend:

~~~javascript
const result = await fetch("https://api.example.com/api/profile", {
  credentials: "include"
});
~~~

**Ba điều kiện cùng phải đúng** để session cookie được gửi và JS đọc response: host/path/scheme/SameSite policy cho phép cookie; fetch credentials mode thích hợp; CORS response được phép cho origin cụ thể. Nếu request thay đổi trạng thái, phải đáp ứng CSRF token và authorization riêng.

Không thiết lập CORS wildcard để làm API “hết lỗi” và không trả `Access-Control-Allow-Credentials: true` cho mọi website.

## 21. Reactive/WebFlux: session cookie đi qua WebSessionIdResolver

Ở WebFlux, session thường dựa trên `WebSession` và thành phần `WebSessionIdResolver`, không phải Servlet `HttpSession`. Spring Framework cung cấp `CookieWebSessionIdResolver` để quyết định cookie nào chứa WebSession ID.

Một cấu hình minh họa cho deployment HTTPS:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
public class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");

        resolver.addCookieInitializer(builder -> builder
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
        );
        return resolver;
    }
}
~~~

Đây là API của Spring Framework trong môi trường WebFlux phù hợp. Khi dùng Spring Session Reactive, gateway hoặc custom session resolver, phải kiểm tra bean nào thật sự quản lý cookie và **header `Set-Cookie` cuối cùng**. Không dùng bean Servlet cookie configuration rồi giả định nó tự điều khiển WebFlux.

### WebFlux security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/session-lab/**").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Controller WebFlux tương ứng:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
class ReactiveSessionLabController {

    @GetMapping("/session-lab/start")
    Mono<Map<String, String>> start(WebSession session) {
        session.getAttributes().put("lab", "ready");
        return Mono.just(Map.of("session", "started"));
    }

    @GetMapping("/session-lab/check")
    Mono<ResponseEntity<Map<String, String>>> check(WebSession session) {
        boolean present = "ready".equals(
            session.getAttribute("lab")
        );
        return Mono.just(present
            ? ResponseEntity.ok(Map.of("session", "present"))
            : ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("session", "absent")));
    }
}
~~~

Không gửi session ID trong response lab. `start` thêm attribute để session có trạng thái; `check` chỉ đọc attribute. Khi WebSession chưa từng được bắt đầu, request check có thể có một WebSession object rỗng mà không đồng nghĩa đã gửi cookie; vì vậy test theo **attribute** chứ không chỉ kiểm tra object khác null.

### Khác biệt cần nhớ

| Servlet | Reactive/WebFlux |
|---|---|
| `HttpSession` | `WebSession` |
| `JSESSIONID` phổ biến | `SESSION` phổ biến trong resolver mặc định; có thể tùy biến |
| Servlet container/session cookie config | `WebSessionIdResolver`/Spring Session Reactive |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `MockMvc` | `WebTestClient` |
| `CsrfFilter` | `CsrfWebFilter` |

**Không mang nguyên cấu hình servlet cookie sang WebFlux**. Tên cookie mặc định, cơ chế resolver và HTTP server có thể khác; phải xác nhận stack thực tế.

## 22. MockMvc: kiểm tra server session, không giả lập browser cookie policy

Với Servlet session lab ở mục 19:

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Tạo session giả lập trong MockMvc.
MvcResult start = mockMvc.perform(get("/session-lab/start"))
    .andExpect(status().isOk())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) start.getRequest().getSession(false);
assertNotNull(session);

// Truyền chính session đó: backend nhìn thấy dữ liệu lab.
mockMvc.perform(get("/session-lab/check")
        .session(session))
    .andExpect(status().isOk());

// Không truyền session: đối chứng về server-side session state.
mockMvc.perform(get("/session-lab/check"))
    .andExpect(status().isUnauthorized());
~~~

Test này đòi hỏi MockMvc gắn application context/security filters và controller lab. Nó chứng minh **server xử lý cùng session khác với không có session**, không chứng minh browser lưu cookie đúng `SameSite`, `Domain`, `Path` hay `Secure`.

### Vì sao không nên assert Set-Cookie bằng MockMvc như browser?

MockMvc dùng mock servlet request/response, không chạy qua full browser cookie jar và có thể không tái hiện toàn bộ hành vi **servlet container cấp cookie session** của HTTP server thật. Muốn kiểm tra header `Set-Cookie` cuối cùng, hãy test qua actual embedded container hoặc staging HTTPS. Muốn kiểm tra cookie được **browser gửi**, dùng browser E2E.

### CSRF trong MockMvc vẫn là phép thử khác

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER")))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Hai phép thử trên giả định controller trả 204 khi hợp lệ và CSRF protection đang áp dụng. `with(user(...))` và `with(csrf())` là **test helpers**, không kiểm tra cookie phiên trong browser. Chỉ khi test auth/cookie end-to-end mới biết 403 thực tế liên quan cookie hay token.

## 23. WebTestClient: xác nhận Set-Cookie của Reactive server và continuity

Với WebFlux, dùng **WebTestClient kết nối HTTP server thật** trong test integration. Ví dụ đã có client kết nối tới **HTTPS base URL** đúng của lab:

~~~java
import java.util.List;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

import static org.junit.jupiter.api.Assertions.*;

EntityExchangeResult<byte[]> start = webTestClient.get()
    .uri("/session-lab/start")
    .exchange()
    .expectStatus().isOk()
    .expectBody().returnResult();

List<ResponseCookie> values =
    start.getResponseCookies().get("SESSION");
assertNotNull(values);
assertFalse(values.isEmpty());

ResponseCookie sessionCookie = values.get(0);
assertTrue(sessionCookie.isSecure());
assertTrue(sessionCookie.isHttpOnly());
assertEquals("/", sessionCookie.getPath());
assertEquals("Lax", sessionCookie.getSameSite());

webTestClient.get()
    .uri("/session-lab/check")
    .cookie("SESSION", sessionCookie.getValue())
    .exchange()
    .expectStatus().isOk();

webTestClient.get()
    .uri("/session-lab/check")
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Ví dụ áp dụng khi resolver và controller WebFlux từ mục 21 đã được cấu hình và session state được lưu. **Không dùng session ID thật trong output hoặc test report.** Test này còn **chủ động gắn cookie** bằng client API; nó kiểm tra server đọc cookie đúng nhưng không bắt browser tuân theo SameSite/Secure/third-party-cookie rules.

Nếu kết quả Set-Cookie khác dự kiến, trước khi kết luận “WebFlux không hỗ trợ attribute”, hãy kiểm tra Spring Session/custom resolver, cookie initializer, app profile và proxy. Để kiểm tra header thực tế qua CDN, test phải dùng **đường public** tương ứng.

## 24. Playwright: browser thật có lưu và gửi cookie không?

Giả định lab có HTTPS với hostname do đội kiểm thử kiểm soát, certificate hợp lệ, server phục vụ `/session-lab/start` và `/session-lab/check`. Ví dụ:

~~~javascript
import { test, expect } from "@playwright/test";

test("session cookie được lưu và gửi trên HTTPS đúng host/path",
  async ({ browser }) => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const origin = "https://app.example.test";

      const start = await page.goto(origin + "/session-lab/start");
      expect(start.status()).toBe(200);

      const cookies = await context.cookies(origin);
      const session = cookies.find(c => c.name === "SESSION");
      expect(session).toBeDefined();
      expect(session.secure).toBe(true);
      expect(session.httpOnly).toBe(true);
      expect(session.sameSite).toBe("Lax");
      expect(session.path).toBe("/");

      // Chỉ có ý nghĩa khi /session-lab/check trả 200
      // nếu đã khôi phục session "ready".
      const check = await page.goto(origin + "/session-lab/check");
      expect(check.status()).toBe(200);
    } finally {
      await context.close();
    }
});
~~~

**Lưu ý:** những hostname `*.example.test` là ví dụ lab, phải cấu hình DNS/hosts và HTTPS certificate trước. Nếu lab dùng cookie `JSESSIONID` Servlet thay vì `SESSION` WebFlux, đổi assertion tên cho đúng. Trên production không nên expose các route lab này.

Test này mạnh hơn việc xem mỗi `Set-Cookie`, vì nó buộc browser **lưu cookie rồi gửi lại** để server khôi phục session. Tuy nhiên, vẫn cần test riêng cross-origin/cross-site và reverse proxy.

### Đo request cookies thay vì chỉ xem cookie store

Có thể quan sát request headers từ Playwright mà **không in giá trị bí mật**:

~~~javascript
const requestPromise = page.waitForRequest(request =>
  request.url().endsWith("/session-lab/check")
);

const navigation = page.goto(origin + "/session-lab/check");
const request = await requestPromise;
const response = await navigation;

const headers = await request.allHeaders();
const cookieWasSent = Object.hasOwn(headers, "cookie");
expect(cookieWasSent).toBe(true);
expect(response.status()).toBe(200);
~~~

Đoạn này minh họa phần bổ sung bên trong một test đã có `page`/`origin`; không phải test độc lập. **Không in `headers.cookie`** vào console, report hoặc artifact. Nếu có nhiều requests tới cùng URL, cần điều chỉnh predicate/đồng bộ để đo đúng request.

### Chỉ thấy cookie trong Application tab không đủ

`context.cookies(origin)` cho biết cookie jar lưu gì ở URL cụ thể; nó không tự chứng minh cookie sẽ đi trong một cross-site fetch hoặc iframe. Phải quan sát request thực hoặc hành vi server trên **đúng loại request cần điều tra**.

## 25. Test SameSite đúng: dùng hai site, không chỉ hai port của localhost

Sai lầm thường gặp:

~~~text
Frontend: http://localhost:3000
Backend:  http://localhost:8080
~~~

Đây là hai origin khác nhau do port, nhưng không phải hai **registrable sites** khác nhau theo cùng scheme/host. Vì vậy test từ port 3000 sang 8080 có thể phát hiện **CORS/fetch credentials**, nhưng không đủ để tái hiện lỗi **cross-site SameSite**.

### Ma trận test nên có

| Cặp nguồn/đích | Mục tiêu |
|---|---|
| `https://app.example.test` → `https://app.example.test` | Same-origin, cookie baseline |
| `https://app.example.test` → `https://api.example.test` | Cross-origin nhưng same-site |
| `https://front.other.test` → `https://api.example.test` | Cross-site fetch |
| `http://app.example.test` → `https://app.example.test` | Kiểm tra ảnh hưởng schemeful site và Secure |
| Public domain → backend qua TLS proxy | Phân biệt public Path/Domain với upstream |

Trong môi trường thực hành, cần map hostname về server test và cấp certificate phù hợp. Không tùy tiện gọi endpoint của bên thứ ba.

### Ví dụ kiểm thử hành vi cross-site fetch

Giả định cookie `SESSION` được cấp **host-only** bởi `https://api.example.test` với `SameSite=Lax` và backend test có CORS policy tạm cho nguồn `https://front.other.test`:

~~~javascript
import { test, expect } from "@playwright/test";

test("Lax session cookie không đi theo cross-site fetch", async ({ browser }) => {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    const api = "https://api.example.test";

    // Tạo cookie của API trong top-level navigation.
    await page.goto(api + "/session-lab/start");
    const stored = await context.cookies(api);
    expect(stored.find(c => c.name === "SESSION")?.sameSite)
      .toBe("Lax");

    // Một site khác, không phải chỉ khác port.
    await page.goto("https://front.other.test/test-page");

    const requestPromise = page.waitForRequest(req =>
      req.url() === api + "/session-lab/check"
    );

    await page.evaluate(async url => {
      // Response có thể bị chặn bởi CORS; chỉ cần quan sát request
      // thực tế đã gửi. Không truyền secrets vào mã JavaScript.
      try {
        await fetch(url, { credentials: "include" });
      } catch (_) { /* Chẩn đoán Network/CORS riêng. */ }
    }, api + "/session-lab/check");

    const request = await requestPromise;
    const headers = await request.allHeaders();
    expect(Object.hasOwn(headers, "cookie")).toBe(false);
  } finally {
    await context.close();
  }
});
~~~

**Giới hạn quan trọng:** kết quả cookie không được gửi có thể còn bị tác động bởi **third-party cookie restrictions**, `Domain`, `Path`, `Secure` hoặc chính sách browser. Để quy nguyên nhân chính xác cho SameSite, phải kiểm tra blocked reason trong browser, và chạy đối chứng với cookie/test configuration chỉ khác thuộc tính cần đo. Không thiết lập `SameSite=None` cho production chỉ để test xanh.

### Top-level GET khác fetch

Trong một test riêng, hãy thử click liên kết GET từ `front.other.test` tới `api.example.test`. Cookie `SameSite=Lax` có thể được gửi trong top-level navigation đó dù **không** được gửi trong cross-site fetch. Sự khác nhau này là nội dung bài học, không phải browser bug.

## 26. Kịch bản A — Login HTTPS thành công, request HTTP tiếp theo mất session

**Hiện tượng:** trong staging, form login qua `https://app.example.com` thành công và server gửi session cookie `Secure`. Một đoạn JavaScript hoặc cấu hình redirect sau đó gọi:

~~~text
http://app.example.com/api/profile
~~~

Request không có session cookie, nhận 401/302 login.

**Bằng chứng cần tìm:**

1. Response login có `Set-Cookie: ... Secure` không?
2. Request tiếp theo thật sự dùng scheme `http:` hay `https:`?
3. Có HSTS hoặc `upgrade-insecure-requests` khiến browser nâng cấp URL trước khi gửi không? Xem URL thực tế trong Network.
4. Proxy có tạo redirect absolute URL HTTP vì hiểu sai scheme công khai?
5. Console có báo mixed content không? Browser có thể chặn request trước khi gửi.

**Cách sửa:** chuẩn hóa URL công khai HTTPS, TLS termination, forwarded headers đáng tin và application redirect. Giữ cookie `Secure`; không chuyển nó sang cookie không Secure để làm HTTP request hoạt động.

**Đối chứng:** cùng session, request `https://app.example.com/api/profile` phải có cơ hội gửi cookie nếu Domain/Path/SameSite hợp lệ. Nếu cookie vẫn thiếu trên HTTPS, tiếp tục xem các ràng buộc khác.

## 27. Kịch bản B — SPA subdomain gọi API nhưng cookie host-only ở frontend

**Hiện tượng:**

~~~text
User đăng nhập trên https://app.example.com
  -> Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax

SPA gọi https://api.example.com/api/orders
  -> không có SESSION cookie
  -> API coi anonymous
~~~

Cookie không có `Domain` nên host-only cho `app.example.com`. Thêm `credentials: "include"` **không thể** làm cookie host-only đi tới `api.example.com`; browser vẫn thực thi Domain scope.

**Hướng điều tra:**

1. Session của API có được thiết kế dùng chung với web frontend không, hay hai service có authentication riêng?
2. Host nào thực sự phát cookie? Ở DevTools, Domain có phải host-only?
3. Cookie được gửi đến endpoint nào khi gọi top-level hoặc fetch đúng host?
4. Có gateway trên **cùng origin** có thể route `/api/**` tới backend, thay vì chia sẻ cookie giữa subdomains không?
5. Nếu cần cookie domain-wide thật, mọi subdomain được cấp quyền nhận cookie có đáng tin cậy không?

**Cách sửa** phụ thuộc kiến trúc: dùng BFF/same-origin gateway, authentication API riêng hoặc cookie domain được review chặt chẽ. Không tùy tiện đặt `Domain=example.com` cho session cookie trên một hệ thống có subdomain không đáng tin.

## 28. Kịch bản C — API nhận credentialed CORS nhưng cookie bị SameSite chặn

**Hiện tượng:** SPA tại `https://front.other.test` gọi `https://api.example.test` bằng:

~~~javascript
fetch("https://api.example.test/api/orders", {
  credentials: "include"
});
~~~

API đã trả CORS headers đúng origin và `Access-Control-Allow-Credentials: true`, nhưng session không có.

**Lý do có thể:** cookie `SESSION` là `SameSite=Lax`, không được gửi trong **cross-site fetch**. Kết quả không tự chứng minh API thiếu CORS hay Spring Security không lưu session.

**Đối chứng cần thực hiện:**

1. Tạo session cookie bằng top-level GET trên API site trong môi trường lab.
2. Xem browser đã lưu cookie, có Secure/Path/Domain đúng.
3. Từ cross-site frontend, phát fetch với `include` và quan sát request cookies.
4. Từ **same-site** frontend khác subdomain, thử request tương ứng với CORS allowlist phù hợp.
5. Kiểm tra blocked reason của browser; third-party policy có thể tác động đồng thời.

Nếu hệ thống thực sự cần cross-site cookie, phải đánh giá toàn bộ auth/CSRF/third-party-cookie policy trước khi cân nhắc `SameSite=None; Secure` hoặc kiến trúc thay thế. **Không coi None là một mẹo sửa mặc định.**

## 29. Kịch bản D — Path sai vì proxy đổi prefix

**Hiện tượng:** phiên login được cấp khi truy cập:

~~~http
Set-Cookie: SESSION=...; Path=/backend; Secure; HttpOnly
~~~

Nhưng ứng dụng công khai:

~~~text
https://app.example.com/portal/home
https://app.example.com/portal/api/profile
~~~

Browser không gửi cookie cho `/portal/api/profile` vì cookie chỉ có Path `/backend`.

**Phân tích:** reverse proxy có thể đổi `/portal/*` thành `/backend/*` cho upstream. Browser không biết upstream path. Nó chỉ xét Path theo request công khai.

**Cách sửa đúng:** nhất quán URL public, session cookie Path và rewrite rules. Kiểm thử login → redirect → API trên URL công khai. Nếu Path được set rộng hơn, review các app khác cùng host để tránh vô tình chia sẻ cookie.

**Tránh khắc phục sai:** không dùng JavaScript copy session cookie sang `document.cookie` vì cookie HttpOnly không nên bị phơi bày; không tự xây cookie mới chứa session ID.

## 30. Kịch bản E — Logout xóa cookie sai Path, tạo hai session cookies

**Hiện tượng:** sau logout, browser vẫn giữ `SESSION` hoặc đôi lúc backend nhận sai giá trị session.

Một sequence:

~~~http
# Cookie được cấp ban đầu:
Set-Cookie: SESSION=OLD; Path=/app; Secure; HttpOnly; SameSite=Lax

# Logout chỉ xóa phiên bản Path=/:
Set-Cookie: SESSION=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Lệnh xóa sau **không nhất thiết xóa** cookie `SESSION` có Path `/app`. Khi login mới tạo cookie cùng tên Path khác, browser có thể giữ nhiều cookie `SESSION`.

### Điểm điều tra

- Ở browser cookie store, có mấy cookie cùng tên, khác Domain/Path?
- Mỗi `Set-Cookie` login/logout có đúng Domain/Path của cookie cần xóa không?
- Header `Cookie` ở request lỗi chứa một hay nhiều giá trị cùng tên?
- Framework/server session resolver chọn cookie nào khi gặp trùng tên?
- Cookie cũ có còn gắn với session hợp lệ không hay chỉ là state lỗi thời?

**Cách sửa:** đồng bộ cookie name/scope và deletion rules ở các thành phần chịu trách nhiệm. Không tự thiết kế quy tắc phân tích Cookie header mơ hồ; giảm tình trạng cookie trùng tên ngay từ lúc phát và xóa.

## 31. Kịch bản F — Cookie vẫn được gửi, nhưng request trả 403 sau login

Một ticket nói “cookie không được gửi” nhưng DevTools lại cho thấy:

~~~text
POST /profile
  Cookie: JSESSIONID=...
  X-CSRF-TOKEN: token trước khi login
  Response: 403
~~~

Nếu server khôi phục authentication/session thành công, nguyên nhân **không còn là cookie bị browser bỏ qua**. Có thể:

- CSRF token cũ bị invalidate sau login.
- Session mới có expected CSRF token khác token trong form/SPA.
- Raw cookie CSRF được gửi bằng header nhưng CSRF handler đang giải masked token.
- Authorization hoặc method security từ chối.
- Request đi vào chain khác hoặc gateway phát 403.

**Hướng xử lý:** tìm `CsrfFilter`/`CsrfWebFilter`, `InvalidCsrfTokenException`, auth/authorization event và CSRF repository. Bootstrap CSRF token mới sau auth transition nếu cần. Không đổi cookie SameSite/Domain vô cớ chỉ vì cùng HTTP status.

## 32. Bảng phân loại lỗi: nguyên nhân nào phù hợp với quan sát?

| Triệu chứng | Nghi vấn trước tiên | Cách loại trừ |
|---|---|---|
| Response không có `Set-Cookie` | Session không được tạo/ghi hoặc proxy loại header | Dùng session lab và kiểm tra origin/public |
| Response có `Set-Cookie`, browser từ chối lưu | Secure, SameSite=None thiếu Secure, Domain/prefix, expiry/policy | DevTools blocked reason |
| Cookie đã lưu, request HTTPS đúng host nhưng không gửi | Path, SameSite context, credentials, expiry | So cookie scope và loại request |
| Cookie chỉ không gửi trên HTTP | Secure | Thử đường HTTPS public |
| Cookie app host không đi tới API subdomain | Host-only Domain | Kiểm tra host phát cookie |
| Cookie không gửi khi cross-site fetch | SameSite, third-party policies, credentials | So same-site control và DevTools reason |
| Cookie không gửi trên cross-origin fetch cùng site | Fetch default credentials hoặc host/path scope | Thử `include` trong lab, kiểm tra Cookie header |
| Cookie chỉ không gửi tới route `/api/**` | Path | So Path với URL browser gửi |
| Cookie có tên `__Host-...` không được lưu | Prefix requirements bị vi phạm | Secure + Path=/ + không Domain |
| Browser thấy cookie nhưng JS không đọc được | HttpOnly | Xem Request Cookies; không tắt HttpOnly tùy tiện |
| Cookie đã gửi nhưng backend anonymous | Session timeout/store, cookie name, node hoặc auth chain | Server trace và session lab |
| POST có cookie nhưng 403 | CSRF/authorization/CORS/WAF | Lớp từ chối + exception |
| OPTIONS không có cookie | Preflight thường không có credentials | Kiểm tra CORS config, không ép cookie |
| Login redirect loop | Cookie missing hoặc auth/redirect configuration | Network redirect + auth state |
| Chỉ lỗi production qua proxy | Secure, host/path rewrite, forwarded header, edge | So origin/public response |
| Chỉ lỗi vài node | Session store/affinity/canary | Gắn request ID và node |
| Form từ bfcache dùng token cũ | Token/session transition | GET token và POST hợp lệ sau reload |

Đừng tự động nới cookie dựa vào một hàng trong bảng. Có thể cùng lúc sai `Path` và `fetch.credentials`; hoặc cookie gửi đúng nhưng CSRF token stale. **Ưu tiên phép thử có đối chứng chỉ thay một yếu tố.**

## 33. Quy trình chẩn đoán bảy bước, từ browser đến Spring Security

~~~mermaid
flowchart TD
    A[API 401/302/403, nghi session cookie mất] --> B{Có HTTP request thực?}
    B -- Không --> C[Browser CSP, mixed content, CORS preflight, network]
    B -- Có --> D{Response trước đó có Set-Cookie?}
    D -- Không --> E[Login/session creation, app, proxy, cookie writer]
    D -- Có --> F{Browser đã lưu cookie?}
    F -- Không --> G[Secure, SameSite=None, Domain, prefix, expiry, policy]
    F -- Có --> H{Request bị lỗi có Cookie header?}
    H -- Không --> I[Scheme, host, Path, SameSite, fetch credentials]
    H -- Có --> J{Server tìm được session?}
    J -- Không --> K[Cookie name, session store, TTL, node, proxy]
    J -- Có --> L[Authentication, CSRF, authorization, controller]
    G --> M[Đối chứng một biến đổi, kiểm thử browser]
    I --> M
    K --> M
    L --> M
    M --> N[Kiểm thử lại đường public và nhiều browser]
~~~

### Bước 1 — Xác định đúng request

Ghi method, URL công khai (scheme, hostname, port, path), initiator, Origin, request ID và status. Trong browser, phân biệt một `OPTIONS` preflight với GET/POST thật. Nếu browser không gửi request vì CSP/mixed content, không thể kết luận cookie không đi kèm một request chưa hề tồn tại.

### Bước 2 — Tìm response phát cookie

Quan sát `Set-Cookie` trong response **cuối cùng qua proxy**, gồm cả redirect và logout. So sánh với header ở Spring origin nếu cần. Hãy xem có cookie nào được xóa bởi `Max-Age=0` hoặc `Expires` trong một response sau đó hay không.

### Bước 3 — Xác nhận lưu cookie

Xem Application/Storage và blocked reasons. Kiểm tra `Secure`, `SameSite=None`/Secure, Domain hợp lệ, Path, prefix, thời hạn và third-party browser policy. Không suy từ response header rằng browser đã chấp nhận.

### Bước 4 — Xác nhận gửi cookie

Ở request lỗi, xem **Request Cookies thực tế**. Đối chiếu với scheme, target hostname, Path và site context của browser. Nếu JavaScript gọi cross-origin, kiểm tra `credentials`. Không dùng `document.cookie` làm tiêu chuẩn cho HttpOnly cookies.

### Bước 5 — Xác nhận khôi phục session

Nếu cookie đã được gửi, đối chiếu session resolver/container, tên cookie, state store, login/logout events, session timeout và load balancer. Một cookie string đến backend nhưng session đã invalidated vẫn có thể dẫn đến anonymous.

### Bước 6 — Chỉ sau đó kiểm tra bảo mật khác

Nếu session hoạt động, tìm CSRF filter/token, authorization rule, method security và security chain. CORS response sai có thể khiến JavaScript không đọc được kết quả dù server đã xử lý POST. Không gộp các lỗi này thành “cookie browser hỏng”.

### Bước 7 — Lập test hồi quy

Kiểm thử lại GET → login → redirect → GET API → POST có CSRF → logout trên **đường HTTPS public**, nhiều browser mục tiêu, các subdomain và flow cross-origin thực có trong sản phẩm. Dùng các test route lab cô lập để tránh ảnh hưởng dữ liệu nghiệp vụ.

## 34. Sửa đúng lỗi mà vẫn giữ biên bảo mật

| “Cách chữa nhanh” không nên dùng | Rủi ro | Hướng sửa phù hợp |
|---|---|---|
| Bỏ `Secure` để cookie đi qua HTTP | Session credential có nguy cơ lộ qua đường không bảo mật | Sửa HTTPS, redirect, TLS proxy |
| Đổi mọi cookie sang `SameSite=None` | Mở rộng khả năng gửi cookie trong cross-site requests, vẫn bị privacy policy | Phân tích flow SSO/iframe thật; dùng thiết kế có mục đích |
| Đặt `Domain=example.com` cho mọi session cookie | Tăng phạm vi subdomains nhận credential | Ưu tiên host-only hoặc BFF/same-origin gateway |
| Đặt `Path=/` cho mọi cookie không review | Có thể chia sẻ cookie ngoài phạm vi ứng dụng | Chọn Path theo public route có trust boundary rõ |
| Tắt HttpOnly để JS đọc session ID | Tăng tác động khi có XSS | Giữ HttpOnly; dùng CSRF token endpoint/cookie riêng |
| Cố gửi cookie qua fetch mà không xét CORS | Có thể gửi credentials đến API không tin cậy | Chỉ `include` cho trusted API và CORS allowlist |
| Cho mọi Origin và credentials trong CORS | Mở truy cập cross-origin ngoài thiết kế | Explicit allowlist; kiểm tra origin/method/headers |
| Tắt CSRF để POST “hết 403” | Mất phòng vệ state-changing browser requests | Sửa session continuity và token flow |
| Tắt HTTP firewall vì URL lạ không vào controller | Che lỗi URL/proxy normalization | Sửa URI canonical hoặc review firewall với regression |
| Bỏ HSTS hoặc CSP để “cookie ổn hơn” | Suy yếu TLS và lớp bảo vệ browser | Tách nguyên nhân; giữ policy đúng |
| Chép session ID sang localStorage | JavaScript có thể truy cập secret; lệch mô hình cookie | Cookie session HttpOnly/Secure phù hợp |
| Sửa cookie scope nhưng bỏ qua logout | Cookie cũ còn lại, session không được xóa đúng | Test cấp và xóa cookie cùng Domain/Path |
| Dựa riêng vào curl để kết luận browser đúng | Curl không thực thi SameSite/CORS như browser | Browser E2E và DevTools |
| In cookie headers vào ticket/CI log | Rò session, CSRF token hoặc thông tin cá nhân | Chỉ log flags/attributes/request IDs |

**Không có một bộ attributes phù hợp cho mọi mô hình.** Cookie phiên của web UI cùng origin, cookie SSO, cookie phục vụ embedded app và cookie dành cho SPA có trust boundary khác nhau. Thay đổi attributes phải được cân nhắc cùng authentication, CSRF, CORS, session và browser privacy.

## 35. Bài thực hành tổng hợp: điều tra sáu lỗi cookie

**Bối cảnh:** tạo một Spring Boot lab chỉ dùng dữ liệu giả, có HTTPS hostname do nhóm kiểm thử kiểm soát. Triển khai một phiên bản Servlet và một phiên bản WebFlux với route `GET /session-lab/start`, `GET /session-lab/check`, một form login và endpoint POST được CSRF bảo vệ. Có một reverse proxy để thử rewrite prefix.

### Nhiệm vụ

1. **Baseline:** cấp cookie `Secure; HttpOnly; SameSite=Lax; Path=/` trên HTTPS. Xác nhận browser lưu cookie và `/session-lab/check` khôi phục session.
2. **Secure:** gọi URL HTTP công khai bằng cùng browser. Quan sát cookie Secure có được gửi không, request có bị HSTS/mixed content ngăn trước không. Kết luận theo request thực, không suy từ local HTTP.
3. **Domain:** phát host-only cookie từ `api.example.test` rồi thử gọi `app.example.test`. Xác nhận host khác không nhận cookie dù hai host có thể same-site.
4. **Path:** đặt Path `/app`, so `/app/check` với `/api/check`; chú ý khác biệt giữa `/app` và `/application`.
5. **SameSite:** dùng trang `front.other.test` và `api.example.test` qua HTTPS, so cross-site fetch với top-level GET navigation. Dùng browser blocked reasons và đối chứng phù hợp.
6. **Fetch credentials:** từ `app.example.test` gọi `api.example.test` trong lab qua CORS allowlist; so `same-origin` và `include` khi cookie host/path phù hợp.
7. **CORS preflight:** gửi custom header `X-CSRF-TOKEN`; xem OPTIONS có được chấp nhận và browser có gửi POST thật không.
8. **CSRF:** gửi POST với và không có CSRF token tương ứng session. Phân biệt việc cookie session không đi cùng request với việc CSRF handler từ chối token.
9. **Logout:** cấp cookie Path `/app`, thử xóa bằng Path sai rồi sửa; xác nhận cookie store và trạng thái session sau logout.
10. **Servlet:** kiểm tra Spring Boot cookie properties và `SecurityFilterChain`, dùng MockMvc test session state. Gọi actual embedded servlet server để đo header cookie.
11. **Reactive:** cấu hình `CookieWebSessionIdResolver` và `SecurityWebFilterChain`; dùng WebTestClient kiểm tra response cookie attributes và continuity, sau đó browser test.
12. **Proxy:** thực hiện login trên public prefix `/portal` nhưng upstream `/backend`; sửa cookie Path/rewrites để browser gửi đúng.
13. **Multi-node:** mô phỏng session storage không được chia sẻ. Quan sát Cookie header có thể vẫn có trong request nhưng session server không còn.
14. **Báo cáo:** lập bảng gồm request URL, initiator/site context, Set-Cookie, stored?, sent?, session restored?, security chain, lỗi thực và cách sửa nhỏ nhất.

### Mẫu kết quả kỳ vọng

| Ca test | Cookie đã lưu? | Cookie có thể gửi? | Lý do |
|---|---|---|---|
| HTTPS same-origin GET đúng Path | Có | Có thể | Đáp ứng Secure, host/path, site và policy |
| HTTP non-local với cookie Secure | Có thể còn trong store | Không | Scheme không đáp ứng Secure |
| API khác hostname với host-only cookie | Có | Không | Domain scope |
| Path `/app`, request `/api` | Có | Không | Path không match |
| Cross-site fetch, cookie Lax | Có | Thường không | SameSite và/hoặc browser third-party policy |
| Cross-origin cùng site, fetch mặc định | Có | Thường không | Credentials mode `same-origin` |
| Cross-origin cùng site, fetch include + CORS hợp lệ | Có | Có thể | Vẫn chịu host/path/scheme và cookie policy |
| Cookie gửi nhưng server session đã hết hạn | Có | Có | Backend không khôi phục được session |

Các kết quả “có thể” phải được chứng minh bằng browser cụ thể và môi trường lab. Đừng coi bảng là tuyên bố áp dụng cho mọi trình duyệt và mọi phiên bản.

### Câu hỏi tự đánh giá

1. Vì sao có `Set-Cookie` trong response chưa chứng minh browser đã lưu cookie?
2. Browser có lưu cookie rồi nhưng không gửi ở request là do những loại điều kiện nào?
3. `Secure` và `HttpOnly` bảo vệ hai khía cạnh khác nhau như thế nào?
4. Tại sao `document.cookie` không hiển thị `JSESSIONID` chưa chắc là lỗi?
5. Vì sao ngoại lệ `localhost` về cookie Secure không đủ để kiểm chứng production?
6. `Origin` khác `site` ở điểm nào? Hai subdomain có thể same-site nhưng cross-origin không?
7. `SameSite=Lax` có thể gửi cookie với cross-site top-level GET nhưng không gửi với cross-site fetch trong những trường hợp nào?
8. CORS allowlist hợp lệ có tự làm browser bỏ qua SameSite không?
9. `credentials: "include"` có làm cookie host-only đi tới hostname khác không?
10. Vì sao preflight OPTIONS thường không có cookie và không nên bị yêu cầu authentication?
11. Cookie không khai báo Domain khác Domain được khai báo tường minh thế nào?
12. Vì sao `Domain=example.com` không phải cách sửa mặc định cho nhiều microservices?
13. Cookie `Path=/app` có được gửi tới `/application` không? Vì sao?
14. Khi reverse proxy rewrite `/portal` thành `/backend`, browser xét cookie Path nào?
15. `SameSite=None` cần điều kiện gì và còn chịu giới hạn browser nào?
16. Cookie `__Host-SESSION` phải thỏa những ràng buộc gì?
17. Cookie `Max-Age=0` có ý nghĩa gì? Vì sao xóa cookie sai Path gây lỗi?
18. GET form có CSRF token nhưng POST thiếu JSESSIONID sẽ gây lỗi gì?
19. Một POST 403 có thể do authorization chứ không phải cookie không gửi không?
20. Tại sao MockMvc và WebTestClient không thay thế hoàn toàn kiểm thử SameSite bằng browser?
21. Servlet `HttpSession` và Reactive `WebSession` khác nhau ảnh hưởng việc cấu hình cookie ra sao?
22. Khi cookie đã được gửi nhưng node B không tìm được session, nên sửa browser hay session store?
23. Vì sao một cookie có thể được chấp nhận trong top-level navigation nhưng không trong iframe?
24. Khi nào nên đổi `fetch.credentials` và khi nào không nên?
25. Vì sao không tắt `Secure`, HttpOnly hoặc CSRF chỉ để làm request thành công?

## 36. Ghi nhớ

**Cookie được phát, được browser lưu và được browser gửi là ba bước riêng biệt.** Với `Secure`, hãy kiểm tra scheme HTTPS public và TLS proxy; với `SameSite`, hãy phân biệt **same-origin với same-site** và đối chiếu top-level navigation, fetch, iframe; với `Domain`, hãy phân biệt cookie host-only với domain cookie; với `Path`, hãy đối chiếu URL **công khai của browser**, không chỉ path upstream sau rewrite. `HttpOnly` ngăn JavaScript đọc cookie nhưng **không ngăn browser gửi** khi request đủ điều kiện.

Nếu cookie đã được gửi, tiếp tục kiểm tra **session timeout, logout, session store, cookie name, security chain và authentication**. POST 403 còn có thể đến từ CSRF token stale, CORS, authorization hoặc firewall. Servlet và Reactive/WebFlux có cấu hình session riêng: `HttpSession`/servlet container so với `WebSession`/`CookieWebSessionIdResolver`. Dùng MockMvc/WebTestClient để kiểm tra hành vi server, kết hợp DevTools và Playwright để chứng minh chính sách browser trên đường HTTPS public.

Trong `SPRING_SECURITY_HTTP_PROTECTION`, mục tiêu là sửa đúng lớp trong khi giữ **cookie session Secure/HttpOnly**, CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và các cơ chế bảo vệ phiên. Không nới cookie hoặc tắt phòng vệ khi chưa xác định được vì sao **request cụ thể** không mang đúng session.
