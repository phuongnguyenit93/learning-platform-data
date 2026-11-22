# Cookie Secure, HttpOnly, SameSite, Domain và Path trong Spring Boot

## 1. Mục tiêu học tập và bức tranh chung

Khi ứng dụng Spring Boot dùng HTTP session hoặc một cookie riêng, **server gửi chỉ thị lưu cookie qua header `Set-Cookie`**, sau đó trình duyệt quyết định khi nào gửi cookie trở lại bằng header `Cookie`. Các thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path` quyết định phần lớn **cách cookie được lưu, gửi và sử dụng**. Cấu hình sai có thể làm lộ session ID, khiến người dùng mất phiên đăng nhập, làm hỏng đăng nhập qua bên thứ ba hoặc tạo điều kiện cho các cuộc tấn công liên quan cookie.

Ví dụ HTTP response:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/plain;charset=UTF-8

visits=1
```

Request tiếp theo có thể gửi:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=abc123
```

**Điểm cốt lõi:** các thuộc tính như `Secure`, `HttpOnly` và `SameSite` nằm trong header **`Set-Cookie` của response**, **không nằm trong header `Cookie`** của request. Browser kiểm tra chính sách rồi quyết định có gửi cặp `name=value` hay không. Phía server không nên kết luận cookie an toàn chỉ vì request có `Cookie: JSESSIONID=...`.

Bài này tập trung vào **Spring Boot web runtime**, đặc biệt HTTP session/JSESSIONID trên Spring MVC (Servlet), và giải thích cách áp dụng tương ứng với WebFlux. Nội dung dùng Java 17+, Spring Boot 3.5.x và ví dụ HTTP có thể kiểm tra bằng `curl`/trình duyệt. Mọi giá trị session ID trong tài liệu là **minh họa**, không phải token thực.

## 2. Cookie là gì và thuộc tính áp dụng ở tầng nào?

Cookie là dữ liệu nhỏ có `name=value` được trình duyệt lưu theo chính sách. Browser áp dụng thuộc tính cookie khi **lưu**, khi **cho phép JavaScript truy cập**, và khi **gửi request**. Spring Boot có thể tạo cookie phiên thông qua servlet container hoặc reactive session manager; ứng dụng cũng có thể tự tạo cookie bằng `ResponseCookie`.

| Thành phần | Nơi xử lý chính | Tác dụng |
| --- | --- | --- |
| `Set-Cookie` | Server gửi, browser nhận | Tạo/cập nhật/xóa cookie và thuộc tính |
| `Cookie` | Browser gửi, server nhận | Chỉ chứa các cặp tên/giá trị được chọn |
| `Secure` | Browser | Hạn chế gửi cookie qua kết nối không an toàn, thường HTTPS |
| `HttpOnly` | Browser | Không cho JavaScript đọc/ghi cookie qua `document.cookie` |
| `SameSite` | Browser | Quyết định gửi cookie trong các ngữ cảnh cùng site/khác site |
| `Domain` | Browser | Xác định hostname nào được nhận cookie |
| `Path` | Browser | Xác định URL path nào được nhận cookie |
| `Expires`, `Max-Age` | Browser | Xác định thời hạn tồn tại phía client |
| `HttpSession` | Server/Servlet container | Giữ trạng thái phiên ở phía server; cookie thường chỉ giữ ID |

**Cookie không đồng nghĩa với session.** Trong mô hình Spring MVC truyền thống, `JSESSIONID` thường chỉ chứa **mã tham chiếu session**; thông tin trong `HttpSession` nằm phía server. Với cookie tự tạo cho theme, giỏ hàng hay token, nội dung cookie có thể khác. Các thuộc tính bảo vệ phải được cân nhắc theo **độ nhạy dữ liệu** và luồng nghiệp vụ.

**Cookie cũng không đồng nghĩa với localStorage.** Trình duyệt có thể tự gửi cookie theo chính sách request, còn dữ liệu trong `localStorage` không tự đi kèm mọi HTTP request. Điều này vừa tiện cho xác thực dựa trên cookie, vừa tạo rủi ro CSRF cần xử lý.

## 3. `Secure`: chỉ gửi trên kết nối an toàn

`Secure` chỉ thị browser chỉ gửi cookie trên những request bảo mật, thông thường là **HTTPS**.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly
```

Với website `https://app.example.com`, cookie trên có thể được gửi trong các request HTTPS phù hợp `Domain`, `Path`, `SameSite`. Browser nhìn chung **không gửi** cookie đó qua `http://app.example.com`. Có ngoại lệ/đặc quyền kiểm thử cho `localhost` ở một số browser; không dùng ngoại lệ ấy làm tiêu chuẩn bảo mật production.

### `Secure` giải quyết gì?

- Giảm nguy cơ session cookie bị gửi dưới dạng rõ văn bản qua HTTP.
- Hạn chế một số cách đánh cắp/chèn cookie qua kết nối không bảo mật.
- Là điều kiện bắt buộc để browser chấp nhận cookie có `SameSite=None`.
- Là điều kiện của các prefix như `__Secure-` và `__Host-` (xem mục 8).

### `Secure` không giải quyết gì?

- **Không tự mã hóa giá trị cookie trong kho lưu trữ của trình duyệt**; mã hóa trên đường truyền do TLS/HTTPS thực hiện.
- Không ngăn JavaScript đọc cookie: việc đó thuộc `HttpOnly`.
- Không tự bảo vệ CSRF: việc đó liên quan `SameSite`, CSRF token và xác minh request.
- Không bảo vệ server khỏi XSS, lỗi phân quyền hay đánh cắp dữ liệu bằng cách gọi API từ chính phiên nạn nhân.
- Không thay thế việc triển khai HTTPS đúng cách, HSTS và cấu hình reverse proxy.

**Thực hành:** session/auth cookie ở production nên có `Secure` và ứng dụng chỉ phục vụ các request xác thực qua HTTPS. Nếu TLS kết thúc ở load balancer rồi proxy về Spring Boot bằng HTTP nội bộ, cần cấu hình TLS/proxy đúng và không để ứng dụng tin các header forwarded từ client chưa được xác thực.

### HTTPS phía trước reverse proxy

Ví dụ luồng triển khai:

```text
Browser --HTTPS--> Reverse proxy/load balancer --HTTP nội bộ--> Spring Boot
```

Nếu cookie được cấu hình dựa trên việc backend tự nhận request là HTTPS hay không, backend có thể thấy `request.isSecure() == false` và bỏ `Secure`. Với session quan trọng, **đặt explicit `server.servlet.session.cookie.secure=true`** trong profile production giúp tránh phụ thuộc vào suy luận không chắc chắn. Nếu cần forwarded headers cho redirect/URL/secure detection, cấu hình `server.forward-headers-strategy` đúng với hệ thống mạng, chỉ tin forwarded headers do proxy đáng tin cậy tạo hoặc ghi đè.

## 4. `HttpOnly`: ngăn JavaScript truy cập cookie

`HttpOnly` ngăn JavaScript trên trang đọc hoặc đặt cookie đó qua `document.cookie`.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ví dụ:

```javascript
console.log(document.cookie);
```

Đây là code chạy trong trình duyệt, **không phải Java**. Nếu `JSESSIONID` có `HttpOnly`, nó không xuất hiện trong chuỗi trả về bởi `document.cookie`. Tuy nhiên browser **vẫn gửi** cookie đó trong request phù hợp chính sách, kể cả request khởi tạo bằng `fetch` hoặc `XMLHttpRequest` khi chế độ credentials và các giới hạn web platform cho phép.

### Tại sao nên đặt cho session cookie?

Nếu XSS làm chạy một script độc hại, script có thể thử đọc `document.cookie` và gửi session ID ra ngoài. `HttpOnly` làm giảm khả năng đánh cắp **cookie value** qua con đường này.

Nhưng **HttpOnly không chữa XSS**: script độc hại vẫn có thể thực hiện các hành động trong phiên hiện tại, đọc phần nội dung trang mà script truy cập được hoặc gửi request được browser đính kèm cookie. Vì thế vẫn cần escaping output, Content Security Policy thích hợp, kiểm soát đầu vào, kiểm tra phân quyền phía server và CSRF protection.

### Cookie nào không nên có `HttpOnly`?

Chỉ cookie thật sự cần JavaScript trực tiếp đọc/sửa, ví dụ một số preference không nhạy cảm, mới có thể cân nhắc `HttpOnly=false`. Nếu JavaScript không cần biết giá trị, kể cả cookie tùy chọn giao diện cũng có thể đặt `HttpOnly=true`.

Đối với **session ID, refresh token hoặc token đăng nhập nhạy cảm lưu trong cookie**, ưu tiên `HttpOnly=true`. Một số thiết kế CSRF double-submit dùng cookie token để JavaScript đọc; đó là trường hợp có chủ đích, cần hiểu rõ cách Spring Security xử lý CSRF và không nhầm cookie CSRF token với session authentication cookie.

## 5. `SameSite`: cùng site, khác site và ba chế độ

`SameSite` chỉ thị browser có gửi cookie trong request phát sinh từ **một site khác** hay không. Nó là một hàng rào giảm rủi ro CSRF, **không phải cơ chế phân quyền**.

Khái niệm **site** trong các browser hiện đại thường xét **scheme và registrable domain** (schemeful same-site). Cần phân biệt nó với **origin**, vốn gồm scheme, host và port.

Ví dụ:

| Hai URL | Same-site? | Same-origin? | Giải thích |
| --- | --- | --- | --- |
| `https://app.example.com` và `https://api.example.com` | Thường **có** | **Không** | Cùng scheme và registrable domain, host khác |
| `https://app.example.com:443` và `https://app.example.com:8443` | **Có** | **Không** | Port ảnh hưởng origin, thường không thay site |
| `http://app.example.com` và `https://app.example.com` | **Không** theo schemeful site | **Không** | Khác scheme |
| `https://app.example.com` và `https://other.example.net` | **Không** | **Không** | Khác registrable domain |

Các domain trong bảng là ví dụ giả định; quy tắc thực tế còn liên quan Public Suffix List. Vì vậy **cross-origin không nhất thiết cross-site**: một SPA trên `app.example.com` gọi API trên `api.example.com` khác origin nhưng có thể vẫn cùng site. CORS và SameSite là hai cơ chế khác nhau.

### `SameSite=Strict`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=Strict
```

Browser chỉ gửi cookie trong ngữ cảnh **same-site**. Khi người dùng nhấn liên kết từ site ngoài đến trang ứng dụng, cookie Strict có thể không đi kèm request đầu tiên, khiến phiên đang đăng nhập tạm thời có vẻ như chưa đăng nhập. Strict phù hợp một số cookie thao tác đặc biệt nhạy cảm, nhưng cần kiểm thử UX chuyển trang và đăng nhập.

### `SameSite=Lax`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=Lax
```

Lax gửi cookie ở những request same-site và **một số điều hướng top-level từ site khác với HTTP method an toàn**, điển hình người dùng nhấn liên kết đến trang `GET`. Nó thường **không gửi** cookie cho cross-site `POST`/iframe/subresource/fetch trong các trường hợp bị giới hạn.

Đây thường là lựa chọn cân bằng cho **session cookie web truyền thống**. Tuy nhiên, một hành động làm thay đổi dữ liệu qua `GET` vẫn là lỗi thiết kế; cùng-site subdomain cũng có thể không đáng tin cậy. **Lax không thay thế CSRF token**.

Một số browser áp dụng chính sách giống Lax khi `SameSite` bị bỏ trống, đôi khi có ngoại lệ chuyển tiếp cho cookie mới tạo. Do đó **khai báo rõ `SameSite=Lax`** giúp hành vi dễ dự đoán hơn việc trông chờ browser default.

### `SameSite=None`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=None
```

`None` cho phép gửi cookie cả trong các ngữ cảnh cross-site, **nếu các chính sách browser khác vẫn cho phép**. Browser hiện đại yêu cầu `Secure` khi dùng `SameSite=None`; cookie thiếu Secure có thể bị từ chối.

Chỉ chọn `None` khi luồng nghiệp vụ thật sự cần cookies trong iframe bên thứ ba, integration khác site hoặc một số luồng đăng nhập liên hệ nhiều site. Ngay cả với `None; Secure`, cookie của bên thứ ba có thể bị browser chặn hoặc phân vùng bởi chính sách tracking privacy; **None không bảo đảm cookie luôn được chấp nhận**.

### Tình huống tham khảo

| Tình huống | Strict | Lax | None + Secure |
| --- | --- | --- | --- |
| Điều hướng thông thường trong cùng site | Gửi nếu Domain/Path hợp lệ | Gửi nếu hợp lệ | Gửi nếu hợp lệ |
| Nhấn liên kết từ site khác đến trang bằng GET top-level | Thường không | Thường có | Có thể có |
| POST form từ site khác | Không | Thường không | Có thể có |
| Trang site khác nhúng iframe hoặc subresource về ứng dụng | Không | Thường không | Có thể có, còn phụ thuộc chính sách third-party |
| Fetch khác **origin** nhưng vẫn same-site | Có thể gửi nếu credentials/CORS và Domain/Path hợp lệ | Tương tự | Tương tự |

Bảng là khái quát các điều kiện SameSite, **chưa xét** quyền truy cập phía server, CSP, CORS, third-party cookie blocking hoặc chính sách browser. Đối với OAuth/OIDC/SAML, cần xét cụ thể redirect qua top-level GET, `form_post`, iframe hoặc callback và cả cookie state/correlation; đổi tất cả session cookies sang `None` mà không phân tích là một lỗi thường gặp.

## 6. `Domain`: host-only và chia sẻ cookie giữa subdomain

Khi `Set-Cookie` **không có thuộc tính Domain**, cookie là **host-only**: chỉ gửi cho hostname chính xác đã đặt cookie (nếu các điều kiện khác thỏa mãn).

Ví dụ response từ `https://app.example.com`:

```http
Set-Cookie: SID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie đó gửi tới `app.example.com`; nó **không tự gửi tới** `api.example.com` vì hostname khác.

Nếu server có quyền đặt cookie cho một domain cha hợp lệ:

```http
Set-Cookie: SID=abc123; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie có thể được gửi tới `example.com` và các subdomain như `app.example.com`, `api.example.com`, nếu đồng thời thỏa Secure/SameSite/Path. Thuộc tính `Domain` cho phép mở rộng phạm vi tới domain cha hợp lệ, **không cho phép** app.example.com đặt cookie cho `other-company.com` hoặc một public suffix như `com`.

### Quy tắc quan trọng

- **Mặc định nên bỏ Domain** để cookie host-only, giảm việc chia sẻ session giữa các subdomain.
- Chỉ dùng `Domain=example.com` khi có kiến trúc thật sự cần các subdomain **chia sẻ đúng cookie ấy**; ngay cả khi cookie được chia sẻ, các service vẫn cần dùng chung cách xác thực/session repository nếu muốn session ID có ý nghĩa ở mọi nơi.
- Cú pháp cũ `Domain=.example.com`: dấu chấm đầu giờ được browser hiện đại **bỏ qua**; `.example.com` không có nghĩa “chỉ các subdomain, trừ root”.
- Cookie `Domain=example.com` mở rộng bề mặt rủi ro: subdomain ít tin cậy/bị chiếm quyền có thể liên quan đến tấn công cookie tossing, cookie fixation hoặc xung đột cookie.
- Domain **không chứa** scheme hoặc port. Không ghi `Domain=https://example.com` hay `Domain=example.com:8443`.
- Một server ở `localhost` hoặc trên địa chỉ IP có hành vi xử lý `Domain` khác domain Internet thông thường; khi phát triển local, ưu tiên bỏ Domain.

### Domain không phải “same-site”

Hai subdomain có thể **same-site** nhưng cookie host-only của `app.example.com` vẫn **không gửi** sang `api.example.com`. `SameSite=Lax` không làm rộng phạm vi Domain. Để request kèm cookie, phải đồng thời thỏa **Domain/host, Path, Secure, SameSite và các chính sách browser khác**.

## 7. `Path`: lọc URL được gửi cookie

`Path` chỉ định prefix path mà cookie được browser gửi theo quy tắc so khớp path của cookie.

```http
Set-Cookie: SID=abc123; Path=/admin; Secure; HttpOnly; SameSite=Lax
```

Cookie trên thường được gửi tới:

- `/admin`, `/admin/`, `/admin/orders`;
- nhưng **không gửi** tới `/`, `/api` hoặc `/administrator`.

Dấu `/` là dấu phân tách path: `Path=/admin` không đơn thuần khớp chuỗi `/administrator`. Nếu không khai báo Path, browser chọn **default-path dựa trên URL tạo cookie**, không phải lúc nào cũng là `/`. Đối với session cookie, Spring Boot/servlet container thường áp dụng path theo context ứng dụng; bạn có thể cấu hình rõ `server.servlet.session.cookie.path`.

### Path là phạm vi gửi, không phải ranh giới bảo mật

**Không dùng Path để phân quyền**: script hoặc ứng dụng trên cùng origin có thể tìm cách tương tác với các path khác; server vẫn phải kiểm tra authentication/authorization. `Path=/admin` không bảo đảm người dùng thường không xem được tài nguyên `/admin`.

Cookie có cùng tên nhưng khác Path có thể cùng tồn tại, ví dụ:

```http
Set-Cookie: SID=aaa; Path=/; Secure
Set-Cookie: SID=bbb; Path=/admin; Secure
```

Request `/admin` có thể mang cả hai cặp tên `SID`. Server/framework không nên dựa vào thứ tự cặp cookie trùng tên để chọn một giá trị nhạy cảm. Hãy dùng **tên cookie riêng** cho từng ứng dụng hoặc thiết kế path nhất quán. Tránh để các ứng dụng ở nhiều context paths tự tạo nhiều `JSESSIONID` khó phân biệt.

### Path và ứng dụng dưới context path

Khi chạy Spring Boot Servlet tại `/shop` (ví dụ `server.servlet.context-path=/shop`), cookie session có thể được giới hạn cho `/shop` thay vì toàn host. Nếu override `Path=/`, cookie sẽ được gửi rộng hơn tới các ứng dụng khác cùng host. Việc mở rộng này có thể hữu ích cho một số kiến trúc nhưng tăng phạm vi phơi lộ.

Cookie `Path=/shop` của ứng dụng không tự trở thành `Path=/` khi Spring Boot đổi reverse proxy prefix; cần xem URI **mà browser thực nhận**, proxy rewrite, context path và cookie path. Proxy có thể rewrite `Set-Cookie` nhưng phải được kiểm thử và quản lý nhất quán.

## 8. Kết hợp thuộc tính và cookie prefix

Một cấu hình phù hợp với session của ứng dụng web HTTPS trên **một host** thường là:

```http
Set-Cookie: __Host-SESSION=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Lợi ích của prefix `__Host-`: browser hỗ trợ prefix chỉ chấp nhận cookie khi có **`Secure`**, **`Path=/`** và **không có `Domain`**, đồng thời được đặt từ ngữ cảnh HTTPS bảo mật. Điều này giúp giảm một số kiểu ghi đè từ subdomain hoặc đường dẫn không mong muốn.

| Prefix | Yêu cầu cơ bản trên browser hỗ trợ | Hợp với |
| --- | --- | --- |
| `__Secure-` | `Secure`; đặt từ HTTPS | Cookie an toàn nhưng có thể cần Domain hoặc Path tùy chọn |
| `__Host-` | `Secure`, `Path=/`, **không có Domain**, đặt từ HTTPS | Session cookie host-only trên một hostname |
| `__Http-` | `Secure` và `HttpOnly`, được đặt bằng Set-Cookie | Hướng tới cookie chỉ server có thể tạo; cần xem hỗ trợ browser |
| `__Host-Http-` | Kết hợp yêu cầu `__Host-` và `HttpOnly` | Mô hình nghiêm ngặt hơn ở browser hỗ trợ |

Prefix là **kiểm tra quy ước phía browser**, không phải xác thực/ủy quyền của server. Một số prefix mới không được hỗ trợ đồng nhất trên mọi browser; cần kiểm tra mục tiêu triển khai.

**Lưu ý rất dễ sai:** `__Host-SESSION` và `Domain=example.com` **không tương thích**. Nếu phải chia sẻ cookie giữa subdomain bằng Domain, không dùng prefix `__Host-`. Khi đặt cookie `__Host-`, phải dùng `Path=/` (không được `Path=/shop`).

### Chọn cấu hình theo tình huống

| Mục đích | Secure | HttpOnly | SameSite | Domain | Path |
| --- | --- | --- | --- | --- | --- |
| Session đăng nhập web HTTPS thông thường | `true` | `true` | `Lax` (đánh giá luồng) | Bỏ trống (host-only) | `/` hoặc context path phù hợp |
| Session cực nhạy, không cần điều hướng cross-site | `true` | `true` | `Strict` sau khi test UX | Bỏ trống | Giới hạn theo ứng dụng |
| Cookie cần hoạt động trong iframe third-party | `true` | `true` nếu JS không cần đọc | `None`; còn tùy third-party policy | Tối thiểu cần thiết | Tối thiểu cần thiết |
| Theme/locale preference không nhạy cảm và JS cần đọc | `true` trên HTTPS | Có thể `false` | Thường `Lax` | Bỏ trống | Theo UI |
| CSRF token theo mẫu JS đọc cookie | `true` trên HTTPS | Có thể `false` nếu framework yêu cầu JS đọc | Theo luồng và hướng dẫn CSRF | Tối thiểu | Theo cấu hình |

Không có một bộ thuộc tính áp dụng tốt cho mọi ứng dụng. **Session auth** cần bảo vệ nghiêm ngặt hơn preference không nhạy cảm; ứng dụng iframe/cross-site có yêu cầu khác web truyền thống.

## 9. Cấu hình cookie HTTP session trên Spring Boot MVC

Trong Spring Boot MVC chạy trên Servlet container như Tomcat, các thuộc tính cookie session được cấu hình qua `server.servlet.session.cookie.*`. Boot áp dụng cấu hình lên session cookie do container tạo, **không tự động áp dụng mọi property này cho cookie tùy chỉnh của controller hoặc thư viện ngoài**.

Ví dụ cho môi trường production có HTTPS:

```properties
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
# Không đặt server.servlet.session.cookie.domain
server.servlet.session.timeout=20m
```

Đây là **đoạn cấu hình production** cho ứng dụng tại host riêng, context path tương thích `/`. Đặt `secure=true` yêu cầu trình duyệt dùng HTTPS để trao đổi session; không nên test toàn bộ chính sách này bằng một trang HTTP thường. Nếu ứng dụng dùng `server.servlet.context-path=/shop`, cân nhắc cookie path và prefix trước khi giữ nguyên `__Host-SESSION`.

### Ý nghĩa các property

| Property | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `server.servlet.session.cookie.name` | Tên cookie session | Mặc định thường là `JSESSIONID` |
| `server.servlet.session.cookie.secure` | Luôn gắn `Secure` | Đặt `true` ở production HTTPS |
| `server.servlet.session.cookie.http-only` | Gắn `HttpOnly` | Đặt `true` cho session ID |
| `server.servlet.session.cookie.same-site` | `Lax`/`Strict`/`None` | Kiểm thử các luồng login, cross-site |
| `server.servlet.session.cookie.domain` | Thuộc tính Domain | Bỏ trống cho host-only |
| `server.servlet.session.cookie.path` | Thuộc tính Path | Dựa vào context path hoặc đặt cụ thể |
| `server.servlet.session.cookie.max-age` | Tuổi cookie phía client | Không phải server-side session idle timeout |
| `server.servlet.session.timeout` | Idle timeout của session trên server | Phải xem cùng cookie lifetime |

**Vòng đời cookie và vòng đời session khác nhau:** đặt `cookie.max-age=7d` không có nghĩa session tồn tại bảy ngày; nếu server hết hạn session sau 20 phút không hoạt động, một cookie cũ vẫn có thể được browser gửi nhưng ID đó không còn trỏ đến session đang hợp lệ. Ngược lại, browser xóa cookie không nhất thiết tự xóa ngay toàn bộ state phía server; cần logic logout/invalidate phù hợp.

### Khi dùng Spring Session

Nếu ứng dụng dùng Spring Session (ví dụ session trong Redis), framework có cơ chế quản lý cookie như `DefaultCookieSerializer`. Không giả định cấu hình mặc định của Servlet container/`server.servlet.session.cookie.*` luôn là nguồn quyết định cuối cùng khi có session repository hoặc cookie serializer tùy chỉnh. Hãy xác minh bean/session integration thực tế và **response `Set-Cookie`** trong môi trường chạy. Các thuộc tính tương đương có thể cần cấu hình tại serializer thích hợp, với cùng nguyên tắc Secure, HttpOnly, SameSite, Domain và Path.

### Khi dùng WebFlux

Spring Boot WebFlux có nhóm property **`server.reactive.session.cookie.*`** tương ứng, ví dụ:

```properties
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=Lax
server.reactive.session.cookie.path=/
# Bỏ Domain để giữ host-only nếu không có nhu cầu chia sẻ
```

Đây là **cấu hình riêng cho ứng dụng WebFlux**; không dùng nhóm `server.servlet.*` rồi kỳ vọng thay đổi cookie reactive session. Spring Security và Spring Session vẫn có thể có cơ chế/session cookie serializer riêng; kiểm tra header khi kết hợp chúng.

## 10. Ví dụ chạy được: Spring Boot MVC và cookie phiên

Ví dụ sử dụng **JDK 17+**, **Maven** và **Spring Boot 3.5.0** cho một project độc lập. Đây là phiên bản cụ thể của dòng 3.5, không đại diện phiên bản mới nhất của Spring Boot. Trong dự án thực, chọn bản vá đang được hỗ trợ theo chính sách vận hành.

Ví dụ có một endpoint đếm lượt truy cập trong `HttpSession`, một endpoint tạo cookie preference riêng và một endpoint xóa cookie preference. Không có đăng nhập thật; dữ liệu dùng để quan sát cách browser lưu/gửi cookie.

### 10.1. Cấu trúc

```text
cookie-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiedemo/
    │   └── CookieDemoApplication.java
    └── resources/
        ├── application.properties
        └── application-prod.properties
```

### 10.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cookie-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

POM không thêm Spring Security vì demo chỉ minh họa **cookie và session**; không dùng ứng dụng demo này như hệ thống xác thực production. Nếu thêm Security, các quy tắc CSRF và login/logout cần được xử lý trong security filter chain.

### 10.3. Java đầy đủ, chỉ một tệp

Tệp `src/main/java/com/example/cookiedemo/CookieDemoApplication.java`:

```java
package com.example.cookiedemo;

import java.time.Duration;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieDemoApplication.class, args);
    }
}

@RestController
class CookieDemoController {

    @GetMapping(value = "/demo/visit",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String visit(HttpSession session) {
        Integer oldCount = (Integer) session.getAttribute("visits");
        int count = oldCount == null ? 1 : oldCount + 1;
        session.setAttribute("visits", count);
        return "visits=" + count;
    }

    @GetMapping(value = "/demo/choice",
            produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> setChoice(HttpServletRequest request) {
        ResponseCookie cookie = ResponseCookie
                .from("demo_choice", "compact")
                .path("/demo")
                .sameSite("Lax")
                .httpOnly(true)
                .secure(request.isSecure())
                .maxAge(Duration.ofMinutes(10))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("choice=compact");
    }

    @PostMapping(value = "/demo/choice/clear",
            produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> clearChoice(HttpServletRequest request) {
        ResponseCookie deleted = ResponseCookie
                .from("demo_choice", "")
                .path("/demo")
                .sameSite("Lax")
                .httpOnly(true)
                .secure(request.isSecure())
                .maxAge(Duration.ZERO)
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, deleted.toString())
                .body("choice cleared");
    }
}
```

Toàn bộ mã nằm **trong một tệp**. `CookieDemoApplication` là class `public`; `CookieDemoController` là class package-private, được Spring quét cùng package. Không cần tự ghi `Set-Cookie: JSESSIONID=...`: khi endpoint `/demo/visit` tạo/ghi state trong `HttpSession`, servlet container quản lý cookie session.

**Chủ ý của `.secure(request.isSecure())` trong cookie preference demo:** cho phép quan sát cả local HTTP (không có Secure) và HTTPS (có Secure) mà không cần chứng chỉ TLS local. Đây không phải cấu hình bảo mật khuyến nghị cho cookie xác thực; **ở production cookie auth phải bắt buộc `Secure=true`**, không dựa vào việc ứng dụng nhìn thấy HTTP hay HTTPS mà bỏ cờ.

### 10.4. Cấu hình local và production

`src/main/resources/application.properties` để chạy local HTTP:

```properties
server.port=8080
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m
```

File này **không ép `Secure=false`**; chính sách cookie khi local phụ thuộc request/server. Ứng dụng thực phải có profile production riêng cho HTTPS, ví dụ `src/main/resources/application-prod.properties`:

```properties
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
# Cố ý KHÔNG đặt Domain: __Host- yêu cầu host-only
```

File `application-prod.properties` chỉ có ý nghĩa khi chạy với profile `prod`. Ở production, phải có HTTPS hợp lệ tại browser và đúng cấu hình proxy. **Đừng bật profile prod khi thử HTTP thường qua hostname ngoài `localhost`** rồi kết luận cookie bị lỗi, bởi browser có thể cố ý từ chối gửi hoặc lưu cookie `Secure`.

Khi chạy trực tiếp `java -jar` với HTTPS phía trước proxy:

```bash
java -jar target/cookie-demo-1.0.0.jar --spring.profiles.active=prod
```

Lệnh trên chỉ bật chính sách cookie production; **không tự tạo chứng chỉ TLS**. Việc cấu hình TLS/proxy nằm ở tầng triển khai.

### 10.5. Chạy và kiểm tra local

Từ thư mục `cookie-demo`:

```bash
mvn spring-boot:run
```

Trong terminal khác dùng `curl`:

```bash
curl -i -c cookies.txt http://localhost:8080/demo/visit
```

Phần HTTP body sau header là:

```text
visits=1
```

Response đầu tiên tạo session thường có header `Set-Cookie: JSESSIONID=...` với các thuộc tính được cấu hình. Giá trị session ID là **ngẫu nhiên**, không dự đoán trước. Tệp `cookies.txt` sẽ lưu cookie theo định dạng Netscape cookie jar của curl.

Gửi request thứ hai **cùng cookie jar**:

```bash
curl -s -b cookies.txt http://localhost:8080/demo/visit
```

Body chính xác:

```text
visits=2
```

Nếu không dùng `-b cookies.txt` và không gửi session cookie, request mới tạo session khác và thường trả `visits=1`. Đây là minh chứng session state nằm phía server, còn cookie là khóa giúp tra cứu lại session.

Tạo cookie preference:

```bash
curl -i -c cookies.txt http://localhost:8080/demo/choice
```

Body là `choice=compact`. Header sẽ có dạng:

```http
Set-Cookie: demo_choice=compact; Path=/demo; Max-Age=600; HttpOnly; SameSite=Lax
```

Đây là **dạng minh họa** của các thuộc tính chính; thứ tự, `Expires` và chi tiết header có thể khác theo phiên bản. Trên HTTP local, cookie được tạo bởi code không gắn Secure vì `request.isSecure()` là `false`. Nếu request thực sự là HTTPS, có `Secure`.

Xóa preference cookie:

```bash
curl -i -b cookies.txt -c cookies.txt -X POST \
  http://localhost:8080/demo/choice/clear
```

Body chính xác:

```text
choice cleared
```

Server gửi `Set-Cookie` với **cùng tên và Path=/demo**, kèm `Max-Age=0`. Browser/curl xử lý việc xóa cookie scope đó. Đây là ví dụ xóa preference, **không phải logout authentication** và không hủy `HttpSession`.

Trên Windows PowerShell nên dùng `curl.exe` nếu `curl` bị ánh xạ thành lệnh khác; đặt lệnh trên một dòng hoặc nối dòng theo cú pháp PowerShell. Lệnh ví dụ `-X POST` chỉ dùng vì endpoint được khai báo `@PostMapping`.

### 10.6. Tại sao không lưu cờ cookie bằng `document.cookie`?

`document.cookie` chỉ viết được một số thuộc tính của cookie phía client và **không thể đặt `HttpOnly`**. Vì thế session/auth cookie phải được tạo bởi server qua `Set-Cookie`. `ResponseCookie` trong Java cho phép khai báo các thuộc tính có thể kiểm soát rõ hơn so với tự nối chuỗi HTTP header.

Để viết nhiều cookie trong một response, gửi **nhiều header `Set-Cookie` riêng**, không gộp thành một header phân tách bằng dấu phẩy. Một `Set-Cookie` chỉ tạo/cập nhật một cookie.

## 11. Cấu hình cookie ứng dụng bằng `ResponseCookie`

`server.servlet.session.cookie.*` chủ yếu điều chỉnh **session cookie**; còn cookie riêng như `theme`, `locale`, `remember_me` hoặc CSRF cookie có thể do application/Spring Security/thư viện tạo và **phải có policy riêng**.

Đoạn minh họa sau dùng API của Spring Framework:

```java
ResponseCookie cookie = ResponseCookie.from("ui_mode", "dark")
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofDays(30))
        .build();

response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
```

Đây là **snippet**, không phải chương trình độc lập: cần `HttpServletResponse response`, imports `ResponseCookie`, `HttpHeaders`, `Duration` và chạy trên HTTPS. Nếu JavaScript cần đọc `ui_mode`, cân nhắc `httpOnly(false)` **chỉ vì có lý do chức năng cụ thể** và đảm bảo giá trị không nhạy cảm.

### Cookie `SameSite=None` khi phải sử dụng cross-site

```java
ResponseCookie thirdPartyCookie = ResponseCookie.from(
                "embedded_widget_session", "opaque-value")
        .secure(true)
        .httpOnly(true)
        .sameSite("None")
        .path("/")
        .build();
```

Đây là **minh họa cách thiết lập thuộc tính**; không bảo đảm browser cho phép third-party cookie, không tạo cơ chế đăng nhập an toàn và không phải khuyến nghị lưu secret trực tiếp trong cookie. Bên cạnh CORS/credentials (nếu khác origin), cần phân tích CSRF, chống clickjacking, cookie blocking và giới hạn iframe.

### Có thể thêm `Partitioned` không?

Một số browser hỗ trợ **partitioned cookies (CHIPS)**: cookie được lưu phân vùng theo top-level site để giảm theo dõi giữa nhiều site. Cookie Partitioned cần `Secure`, và phạm vi hỗ trợ tùy browser. Spring Boot 3.5.x có cấu hình `server.servlet.session.cookie.partitioned`/`server.reactive.session.cookie.partitioned` cho các runtime tương ứng; nếu không sử dụng, không cần bật.

`Partitioned` không phải tên thay thế cho `SameSite`, không phải giải pháp mặc định cho mọi ứng dụng nhúng và không làm mất yêu cầu xác thực/CSRF. Kiểm tra Browser DevTools và thử trên browser hỗ trợ trước khi triển khai.

## 12. `Expires`, `Max-Age`, xóa cookie và xung đột scope

Các cookie attributes về thời gian:

- `Max-Age=600`: cookie hết hạn sau 600 giây tính từ khi được đặt, theo quy tắc browser.
- `Expires=Wed, 01 Jan 2031 00:00:00 GMT`: thời điểm hết hạn tuyệt đối ở phía client.
- Khi có cả hai, **`Max-Age` được ưu tiên** theo chuẩn.
- `Max-Age=0` hoặc âm thường làm browser hết hạn cookie; `Max-Age=0` là cách xóa phổ biến.
- Không có `Expires`/`Max-Age` thường là **session cookie** phía browser; cách browser khôi phục phiên sau restart có thể khiến nó tồn tại lâu hơn ý niệm “đóng cửa sổ là xóa”.

Ví dụ xóa:

```http
Set-Cookie: demo_choice=; Path=/demo; Max-Age=0; SameSite=Lax
```

Điểm khó: browser định danh cookie chủ yếu bằng **name + domain/host scope + path** (và có thêm partition key đối với partitioned cookie). Muốn xóa đúng cookie, thường phải dùng **cùng tên, Domain nếu trước đó có và Path**, đồng thời expiry về 0. Nếu ban đầu tạo `Path=/admin` nhưng lúc xóa dùng `Path=/`, bạn có thể xóa một cookie khác hoặc chẳng xóa được cookie cần xóa.

`Secure`, `HttpOnly` và `SameSite` nên tiếp tục được đặt nhất quán khi phát cookie xóa, dù các cờ đó không thay thế việc khớp name/domain/path. Với `__Host-` phải giữ quy tắc prefix cả lúc phát lệnh xóa.

**Xóa session cookie không phải tất cả logout:** server cũng phải hủy/rotate session, Spring Security phải thực hiện logout flow phù hợp; những hệ thống dùng remember-me/refresh-token phải thu hồi token cần thiết. Xóa cookie ở browser chỉ giải quyết một phần trạng thái client.

## 13. Cookie và CSRF, XSS, CORS: các ranh giới khác nhau

### 13.1. CSRF

Cookie xác thực được browser tự đính vào request. Một site độc hại có thể cố gắng khiến browser gửi yêu cầu làm thay đổi dữ liệu tới ứng dụng mà người dùng đang đăng nhập. `SameSite=Lax`/`Strict` giúp giảm một số trường hợp CSRF, nhưng **không thay thế** việc thiết kế endpoint đúng HTTP methods, kiểm tra CSRF token khi cần và các biện pháp xác minh nguồn request.

Trong ứng dụng Spring Security dựa trên session, thường nên giữ **CSRF protection được cấu hình phù hợp**, đặc biệt cho form POST/PUT/PATCH/DELETE. Không tắt CSRF toàn cục chỉ vì đã đặt `SameSite=Lax`. Same-site subdomain không nhất thiết đáng tin: nếu một subdomain bị chiếm quyền, tấn công có thể vượt qua sự bảo vệ chỉ dựa vào SameSite.

### 13.2. XSS

`HttpOnly` làm script không đọc được **giá trị cookie** qua API JavaScript thông thường. Nó không ngăn script độc hại hành động bằng session đang có. Phòng chống XSS cần escaping output, template an toàn, kiểm soát HTML động, CSP thích hợp và review dependency phía frontend.

### 13.3. CORS

Một trang `https://app.example.com` gọi API `https://api.example.com` là **cross-origin**; browser kiểm tra CORS, kể cả khi hai host cùng site. Để gửi cookie với `fetch` cross-origin, client thường cần:

```javascript
fetch("https://api.example.com/me", {
  credentials: "include"
});
```

Đây là code browser, không phải Java. Phía API cần CORS đúng cho origin cụ thể, khi cho phép credentials: ví dụ `Access-Control-Allow-Credentials: true` và `Access-Control-Allow-Origin` là origin được phép (không dùng wildcard `*` cùng credentials). Dù cấu hình CORS hợp lệ, cookie vẫn phải thỏa Domain/Path/Secure/SameSite và browser privacy policy.

**CORS không phải CSRF protection.** Việc browser không cho JavaScript đọc response vì CORS không nhất thiết ngăn request gây side effect được gửi. Cấu hình CORS rộng và cookie `SameSite=None` còn cần đánh giá cẩn thận hơn.

### 13.4. Không đưa secrets vào cookie “vì có HttpOnly”

`HttpOnly` không mã hóa dữ liệu cookie trong trình duyệt. Tránh lưu mật khẩu, API key hoặc dữ liệu cá nhân nhạy cảm dạng rõ trong cookie. Nếu kiến trúc dùng token trong cookie, cần cân nhắc chữ ký/mã hóa, hạn dùng, rotation, revoke/logout, kích thước và các thuộc tính browser. Với server-side session, lưu **ID khó đoán** trong cookie và session state phía server là phương án thường dễ kiểm soát hơn.

## 14. Debug thực tế: vì sao cookie không được gửi?

Khi một người dùng “đăng nhập xong nhưng tải trang tiếp theo lại mất phiên”, hãy theo một thứ tự quan sát rõ:

1. **Request tạo phiên có thực sự trả `Set-Cookie` không?** Mở Browser DevTools → Network → response headers, tìm dòng `Set-Cookie`.
2. **Browser có chấp nhận cookie không?** Kiểm tra DevTools Application/Storage → Cookies và lý do blocked/rejected (nếu trình duyệt hiển thị).
3. **URL đang truy cập đúng scheme/host/path không?** Kiểm tra HTTPS, port/proxy, Domain, host-only, Path.
4. **Request phát sinh từ same-site hay cross-site?** Xem trang tạo request, phương thức GET/POST, top-level navigation/iframe và `SameSite`.
5. **Nếu JS fetch cross-origin, credentials/CORS đúng chưa?** `credentials: "include"`, origin và response CORS, nhưng vẫn tuân theo cookie policy.
6. **Cookie có hết hạn hoặc bị xóa không?** Xem Max-Age/Expires, session timeout server, logout, rotation và các Set-Cookie tiếp theo.
7. **Có nhiều cookie trùng tên không?** Kiểm tra `JSESSIONID`/`SESSION` theo Path/Domain, cookie cũ từ context khác.
8. **Có Spring Session/Spring Security hay reverse proxy sửa cookie không?** Kiểm tra actual response headers tại browser và từng tầng proxy.
9. **Server có session ID nhưng không tìm được state không?** Kiểm tra session store, sticky session, Redis availability, session timeout và logic auth.

Dùng `curl -i` để quan sát header:

```bash
curl -i https://app.example.com/login
```

Đây chỉ là **mẫu lệnh kiểm tra header**; không giả định `/login` là GET public ở mọi ứng dụng. Muốn quan sát cookie qua nhiều request:

```bash
curl -c cookies.txt -i https://app.example.com/
curl -b cookies.txt -i https://app.example.com/profile
```

`curl` có cookie jar riêng, **không mô phỏng đầy đủ mọi chính sách browser** như SameSite và browser third-party restrictions. Dùng browser DevTools để xác minh hành vi sản phẩm thực. JavaScript `fetch` không thể đọc trực tiếp `Set-Cookie` response header vì đó là forbidden response-header name, kể cả khi server có trả cookie.

### Bảng triệu chứng nhanh

| Triệu chứng | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| Cookie không gửi trên `http://example.com` | `Secure`, site yêu cầu HTTPS | Test/deploy HTTPS; không bỏ Secure ở production |
| Cookie `SameSite=None` không được lưu | Thiếu `Secure` hoặc third-party restrictions | Thêm Secure/HTTPS; kiểm tra browser blocked reason |
| `document.cookie` không thấy session ID | `HttpOnly` đang hoạt động | Đây là hành vi đúng; kiểm tra Network/Cookies |
| Chỉ `app.example.com` có cookie, `api.example.com` không có | Host-only; Domain bị bỏ trống | Thiết kế đúng hostname/Domain nếu thực sự cần chia sẻ |
| `/shop` có session nhưng `/admin` không có | Cookie `Path=/shop` | Xem context path và thiết kế cookie scope |
| Khi redirect sang HTTPS rồi quay HTTP mất session | Secure + HTTP callback | Giữ HTTPS xuyên luồng, sửa reverse proxy |
| OAuth callback POST từ site bên ngoài không có cookie state | SameSite=Lax/Strict chặn cross-site POST | Phân tích callback flow, dùng state/correlation và thuộc tính phù hợp |
| Cookie được gửi nhưng server coi chưa đăng nhập | Session expired/server-side state mất | Kiểm tra session store, auth handler và timeout |
| Sau logout vẫn có cookie cũ | Delete cookie sai Path/Domain hoặc thiếu invalidate | Xóa đúng scope, hủy server session và token |
| JS fetch đến API không kèm cookie | Credentials mode, CORS, Domain, SameSite | Kiểm tra cả 4 tầng và browser policy |
| Cookie có `Domain=.example.com` nhưng điều kiện lạ | Dấu chấm đầu không còn mang ý nghĩa cũ | Dùng `Domain=example.com` rõ ràng hoặc bỏ Domain |
| Có hai `JSESSIONID` và server chọn sai | Tên trùng với Path/Domain khác nhau | Dùng tên riêng và scope rõ ràng |

## 15. Thiết kế theo từng kiến trúc Spring Boot

### 15.1. Ứng dụng MVC render HTML trên một host

- Có thể dùng session server-side với cookie host-only.
- Bắt buộc HTTPS trong production, `Secure=true`, `HttpOnly=true`.
- `SameSite=Lax` thường phù hợp nếu không có flow đặc biệt; bảo vệ CSRF với Spring Security.
- Giữ `Domain` trống; `Path` theo ứng dụng.
- Có thể dùng prefix `__Host-` khi `Path=/` và không có Domain.

### 15.2. SPA trên subdomain gọi API trên subdomain khác

- Hai hostname có thể same-site nhưng cross-origin.
- CORS + `fetch credentials` cần đúng; cookie phải khớp hostname mà request thực tế gửi tới.
- Có thể để API tự đặt cookie **host-only của api.example.com** và browser đính nó khi gọi API; không nhất thiết đặt `Domain=example.com` chỉ để SPA gọi được API. JavaScript của SPA không cần đọc HttpOnly session cookie.
- Nếu API cần chia sẻ cookie trên nhiều subdomain, mở rộng Domain có đánh đổi bảo mật và cần thiết kế xác thực nhất quán.
- Dù cùng site, vẫn xem xét CSRF và các subdomain không tin cậy.

### 15.3. Ứng dụng nhúng trong iframe thuộc site khác

- Khả năng cần `SameSite=None; Secure` cho cookie phiên nhúng.
- Browser có thể chặn third-party cookies; cần xét policy mới, cookie partitioning, flow đăng nhập top-level hoặc cơ chế thay thế tùy yêu cầu.
- Kiểm tra CSP `frame-ancestors` và `X-Frame-Options` để chỉ cho phép nhúng ở nơi hợp lệ.
- Không mở rộng `Domain` hoặc CORS một cách tùy tiện để chữa lỗi iframe.

### 15.4. Nhiều ứng dụng Spring Boot phía sau cùng reverse proxy

- Xác định host, context path và Set-Cookie **sau khi đi qua proxy**.
- Dùng tên cookie riêng nếu nhiều ứng dụng trên cùng hostname, hoặc Path hợp lý.
- Nếu nhiều instance cùng một ứng dụng chia sẻ session, cần session store thích hợp (ví dụ Spring Session Redis) hoặc cấu hình session affinity rõ, chứ không thể chỉ chia sẻ tên cookie.
- Header `X-Forwarded-Proto`/`Forwarded` cần được proxy đáng tin điều khiển; backend không được tự tin dữ liệu spoofed từ Internet.
- Bảo vệ session fixation bằng cơ chế rotate session ID sau đăng nhập; Spring Security có hỗ trợ chiến lược phù hợp.

## 16. Bài tập và câu hỏi tự kiểm tra

1. **`Secure` và `HttpOnly` có giống nhau không?** Không. Secure hạn chế gửi cookie trên kết nối không an toàn; HttpOnly hạn chế JavaScript truy cập giá trị cookie.
2. **`SameSite=None` có thể không có `Secure` không?** Browser hiện đại thường từ chối; yêu cầu `Secure` và HTTPS (trừ ngoại lệ localhost trong một số môi trường).
3. **Cookie không có `Domain` được gửi đến host nào?** Host chính xác đã đặt cookie, không mặc nhiên đến các subdomain khác.
4. **`Domain=example.com` chỉ tới các subdomain, không tới root domain?** Sai. Nó có thể áp dụng cho root và các subdomain phù hợp.
5. **`Path=/admin` có bảo vệ endpoint `/admin` khỏi người dùng không đủ quyền không?** Không. Đó chỉ là phạm vi browser gửi cookie; phải phân quyền ở server.
6. **`SameSite=Lax` có thay thế CSRF token không?** Không. Nó giảm một số tình huống cross-site request nhưng không giải quyết tất cả.
7. **`HttpOnly` có ngăn XSS thực hiện giao dịch bằng session của nạn nhân không?** Không; cookie vẫn được browser gửi trong request được phép.
8. **Phản hồi `Set-Cookie` có `Secure` thì request gửi lên có chuỗi `Secure` trong `Cookie` không?** Không. `Cookie` chỉ chứa tên và giá trị.
9. **Session timeout 20 phút và cookie Max-Age 7 ngày có nghĩa vẫn đăng nhập được 7 ngày không?** Không. Nếu server-side session hết hạn, cookie cũ không phục hồi trạng thái đã hết hạn.
10. **Tại sao cookie `__Host-SESSION` đặt `Domain=example.com` bị từ chối?** Prefix `__Host-` yêu cầu không có Domain, `Path=/` và Secure qua HTTPS.
11. **`app.example.com` gọi `api.example.com`, đây là cross-site chắc chắn?** Không; thường là same-site nhưng cross-origin. Còn Domain, CORS/credentials và cookie policy phải xét riêng.
12. **Xóa `Path=/admin` cookie bằng `Path=/` có đúng không?** Không bảo đảm; cần khớp name/Domain/Path theo cookie gốc.

## 17. Checklist trước khi triển khai production

- [ ] Xác định từng cookie chứa gì: session ID, auth token, CSRF token hay preference.
- [ ] Session/auth cookie có `Secure=true`, `HttpOnly=true` và chỉ dùng HTTPS.
- [ ] Chọn `SameSite=Lax` hoặc `Strict` phù hợp; `None; Secure` chỉ khi flow yêu cầu, đã đánh giá CSRF/third-party restrictions.
- [ ] Bỏ `Domain` trừ khi thật sự cần chia sẻ cookie; không mở rộng cookie đến mọi subdomain theo thói quen.
- [ ] Đặt `Path` rõ theo context ứng dụng; cân nhắc `__Host-` nếu đúng ràng buộc.
- [ ] Đặt thời hạn cookie phù hợp, phân biệt client Max-Age và server session timeout.
- [ ] Kiểm tra logout, invalidate session, session ID rotation và xóa cookie đúng scope.
- [ ] Xác nhận Spring MVC dùng `server.servlet.session.cookie.*`, WebFlux dùng `server.reactive.session.cookie.*` và Spring Session/security integration không override bất ngờ.
- [ ] Kiểm tra HTTPS termination, reverse proxy forwarded headers và chính sách trust.
- [ ] Không thay thế CSRF/XSS protection bằng SameSite/HttpOnly.
- [ ] Kiểm tra thực tế bằng DevTools trên các trình duyệt/thiết bị mục tiêu, với cả cross-site redirects/iframes khi có.
- [ ] Không ghi log session ID/token thật, không đặt dữ liệu nhạy cảm dạng rõ trong cookie.
- [ ] Giám sát số trường hợp session invalid, login loop, redirect lỗi và browser cookie rejection sau release.

## 18. Tài liệu tham khảo đáng tin cậy

- Spring Boot 3.5 — [Common Application Properties: Servlet Session Cookie và Reactive Session Cookie](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- Spring Boot — [Embedded Servlet Container và session cookie configuration](https://docs.spring.io/spring-boot/how-to/webserver.html)
- Spring Framework — [ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html)
- Spring Security — [Protection Against Exploits: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- Spring Session — [Spring Session with Servlet](https://docs.spring.io/spring-session/reference/http-session.html)
- MDN — [Set-Cookie header: Secure, HttpOnly, SameSite, Domain, Path và cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- MDN — [Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- MDN — [Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- MDN — [Fetch: credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)

**Ghi nhớ:** `Secure` quyết định **gửi qua kết nối bảo mật**, `HttpOnly` quyết định **JavaScript có đọc được cookie không**, `SameSite` quyết định **ngữ cảnh site nào được gửi**, `Domain` giới hạn **host**, và `Path` giới hạn **URL path**. Các điều kiện này được browser xét **đồng thời**; còn phân quyền, CSRF protection, quản lý phiên và TLS là trách nhiệm bổ sung của ứng dụng/hạ tầng.