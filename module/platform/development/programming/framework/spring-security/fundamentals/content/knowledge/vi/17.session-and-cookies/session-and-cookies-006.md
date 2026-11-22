# Cookie `Secure`, `HttpOnly` và `SameSite` trong Spring Security

**Chủ đề:** Spring Security – fundamentals → **Phiên và cookie**. Bài học dành cho Java 17+, Spring Boot 3.x/Spring Security 6.x, có thể áp dụng tư duy tương tự cho các phiên bản mới sau khi kiểm tra lại tài liệu API. Mục tiêu là hiểu cookie trình duyệt, ý nghĩa chính xác của ba thuộc tính bảo mật, cấu hình session cookie cho Spring MVC và WebFlux, cũng như giới hạn của chúng trong phòng chống đánh cắp phiên (session hijacking), XSS và CSRF.

## 1. Cookie tham gia vào một phiên đăng nhập như thế nào?

Trong ứng dụng đăng nhập dựa trên **server-side session**, server thường tạo một session ngẫu nhiên, lưu trạng thái xác thực ở phía server (hoặc một session store phân tán), rồi gửi cho trình duyệt một **session identifier** qua response header `Set-Cookie`. Trình duyệt lưu cookie và gửi lại qua request header `Cookie` ở những request phù hợp với domain, path, scheme, SameSite và các chính sách trình duyệt khác.

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/html
```

Ở request sau đến URL hợp lệ:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-random-id
```

**Phân biệt hai header:** `Set-Cookie` là server **thiết lập** cookie; `Cookie` là browser **gửi lại tên và giá trị**, **không gửi ngược các thuộc tính** `Secure`, `HttpOnly` hay `SameSite`. Server phải xác minh session ID theo kho lưu trữ và quyền của người dùng: chỉ nhìn thấy cookie không có nghĩa người gọi đã xác thực.

Ba thuộc tính chính cần đọc trong `Set-Cookie`:

| Thuộc tính | Điều khiển | Tác dụng bảo vệ chính | Điều **không** làm |
|---|---|---|---|
| `Secure` | Trình duyệt chỉ gửi cookie trong yêu cầu qua HTTPS (có ngoại lệ phát triển localhost tùy browser) | Giảm rò cookie trên kết nối HTTP không mã hóa | Không chặn JavaScript đọc cookie, không tự bật HTTPS/TLS |
| `HttpOnly` | Ngăn API JavaScript phía trang như `document.cookie` đọc/ghi cookie đó | Giảm nguy cơ XSS đánh cắp trực tiếp session ID | Không ngăn JavaScript phát request bằng phiên của nạn nhân, không chặn XSS |
| `SameSite` | Điều kiện site của request khi browser gửi cookie | Giảm một số đường tấn công CSRF và cross-site request | Không thay thế CSRF token, Origin validation và phân quyền |

**Cấu hình thường hợp lý với session đăng nhập của ứng dụng web HTTPS:** `Secure; HttpOnly; SameSite=Lax`, điều chỉnh `SameSite=Strict` hoặc `None` khi nghiệp vụ và mô hình đe dọa thực sự cần. Đây là baseline tham khảo, **không có một giá trị SameSite phù hợp mọi sản phẩm**.

## 2. `Secure`: chỉ gửi cookie qua kết nối an toàn

Đặt `Secure` để browser không gửi session cookie qua HTTP thông thường. Điều này đặc biệt quan trọng với ứng dụng có phiên đăng nhập: nếu cookie phiên đi qua kết nối không mã hóa, người nghe lén hoặc kẻ tấn công trên đường truyền có thể lấy ID và chiếm phiên.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong điều kiện thông thường:

- Truy cập `https://app.example.com/account`: cookie thỏa điều kiện scheme HTTPS và có thể được gửi nếu domain/path/SameSite cũng phù hợp.
- Truy cập `http://app.example.com/account`: trình duyệt **không gửi cookie có `Secure`**.
- Trình duyệt hiện đại thường không cho origin HTTP thông thường thiết lập cookie `Secure`; **localhost** có ngoại lệ/khác biệt theo trình duyệt, nên không suy diễn từ môi trường local ra production.
- `Secure` **không mã hóa riêng nội dung cookie**. Nó dựa vào TLS của request; cookie vẫn cần giá trị khó đoán, giới hạn sống và bảo vệ tại server. Nếu không có `HttpOnly`, JavaScript cùng origin vẫn có thể đọc giá trị cookie.

### 2.1. HTTPS và reverse proxy

Một ứng dụng có thể chạy nội bộ qua HTTP sau Nginx, load balancer hoặc Kubernetes ingress nhưng người dùng truy cập **HTTPS** bên ngoài. Đừng tắt `Secure` chỉ vì kết nối từ proxy đến ứng dụng là HTTP. Cấu hình session cookie `Secure=true` để browser chỉ gửi ở đường HTTPS công khai; thiết lập TLS termination và proxy headers đúng cách, chỉ tin proxy được quản trị. Với Spring Boot có thể cần cấu hình xử lý `Forwarded`/`X-Forwarded-*` phù hợp nếu framework phải suy ra scheme, redirect URL hoặc client IP.

**HTTPS thật, HSTS và cookie Secure là các lớp bổ sung nhau**: HTTPS bảo vệ kênh; `Secure` giới hạn nơi browser gửi cookie; HSTS chỉ đạo browser ưu tiên HTTPS cho host đã nhận chính sách. `Secure` không tự phát hành chứng chỉ TLS, không tự redirect HTTP và cũng không ngăn mọi dạng session fixation.

## 3. `HttpOnly`: giảm rủi ro JavaScript đọc session ID

Với `HttpOnly`, JavaScript thông thường ở trang không thể truy cập cookie qua `document.cookie` hoặc các API cookie scripting có liên quan. Session ID vì vậy khó bị đánh cắp trực tiếp chỉ bằng một đoạn script được chèn vào trang.

Ví dụ session cookie:

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Nếu trang có mã:

```javascript
console.log(document.cookie);
```

Chuỗi trả về có thể chứa cookie khác không có `HttpOnly`, nhưng **không bao gồm cookie JSESSIONID đã đánh dấu HttpOnly**. **Đừng in cookie thật vào log/browser console ở ứng dụng production.**

### 3.1. Hiểu đúng giới hạn

- `HttpOnly` **không làm cookie “không được gửi”**. Browser vẫn tự đính kèm nó vào request phù hợp, kể cả request do JavaScript tạo qua `fetch`/`XMLHttpRequest` nếu chính sách credentials, SameSite, CORS và các điều kiện khác cho phép.
- Nếu trang có XSS, mã độc có thể **gửi hành động thay người dùng** bằng browser đã đăng nhập, đọc dữ liệu mà script có quyền đọc hoặc thao tác DOM. `HttpOnly` chỉ hạn chế một kênh lấy **giá trị** cookie, không loại bỏ XSS.
- Đừng đặt `HttpOnly=false` cho **session ID** chỉ để frontend có thể hiển thị trạng thái “đã đăng nhập”. Dùng endpoint như `GET /api/me` trả dữ liệu hồ sơ không nhạy cảm trong phạm vi cho phép.
- Cookie `HttpOnly` không cần chứa JSON profile, mật khẩu hoặc access token dễ bị lộ; session ID nên là một giá trị opaque, ngẫu nhiên và gắn với phiên được quản lý ở server.

### 3.2. Ngoại lệ có chủ đích: cookie chứa CSRF token

Một số ứng dụng SPA đọc CSRF token trong cookie `XSRF-TOKEN` rồi gửi giá trị token trong header `X-XSRF-TOKEN`. Khi **JavaScript thực sự cần đọc cookie CSRF token**, cookie đó có thể **không bật HttpOnly** theo thiết kế. **Đừng nhầm cookie CSRF token với cookie session đăng nhập**: cookie session vẫn nên `HttpOnly=true`.

Spring Security Servlet cung cấp `CookieCsrfTokenRepository.withHttpOnlyFalse()` phục vụ trường hợp JavaScript đọc token. Đây là cấu hình **có điều kiện**, không phải mặc định khuyên dùng cho mọi ứng dụng; SPA với Spring Security 6 còn cần xử lý deferred token/BREACH và luồng tái phát CSRF token theo tài liệu chính thức.

```java
// Trích đoạn trong cấu hình HttpSecurity của ứng dụng Servlet.
// Chỉ dùng khi SPA cần JavaScript đọc cookie XSRF-TOKEN.
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

Đoạn này **không phải một chương trình Java độc lập**; cần import `org.springframework.security.web.csrf.CookieCsrfTokenRepository` và Spring Security tương ứng. Nó cấu hình **cookie CSRF**, **không** có nghĩa session cookie `JSESSIONID` mất `HttpOnly`.

## 4. `SameSite`: “cùng site” khác “cùng origin”

`SameSite` quyết định trình duyệt có gửi cookie khi request được phát sinh trong **ngữ cảnh cross-site** hay không. Để hiểu đúng, phải phân biệt:

- **Origin** gồm `scheme + hostname + port`. Ví dụ `https://app.example.com:443` và `https://api.example.com:443` là **khác origin**.
- **Site** trong cách xác định hiện đại về cookie thường dựa vào `scheme + registrable domain` (schemeful same-site). Ví dụ `https://app.example.com` và `https://api.example.com` thường **cùng site** vì cùng scheme HTTPS và cùng domain đăng ký `example.com`.
- `https://app.example.com` và `https://payments.example.net` là **cross-site**.
- `http://app.example.com` và `https://app.example.com` có **scheme khác nhau**, nên được phân biệt trong cơ chế schemeful same-site.

**Hệ quả:** SameSite không phải cơ chế chặn request **cross-origin** nói chung. Các subdomain cùng site có thể gửi cookie trong ngữ cảnh same-site, dù vẫn là cross-origin và chịu **CORS** nếu JavaScript muốn đọc response. Đừng xem `SameSite=Strict` là tường chống CSRF giữa các subdomain không đáng tin trong cùng site.

## 5. Ba giá trị `Strict`, `Lax` và `None`

| Giá trị | Khi browser gửi cookie | Trường hợp phù hợp | Đổi lại |
|---|---|---|---|
| `SameSite=Strict` | Chỉ trong ngữ cảnh same-site | Phiên chức năng nhạy cảm ít cần đi từ site ngoài | Mở trang qua link từ site ngoài có thể chưa gửi session trong navigation đầu |
| `SameSite=Lax` | Same-site, và một số **top-level navigation** cross-site bằng HTTP method an toàn như GET | Nhiều ứng dụng web thông thường | Cross-site top-level GET vẫn mang cookie; không cho POST cross-site thông thường |
| `SameSite=None` | Cho phép gửi cả same-site và cross-site khi các điều kiện cookie/trình duyệt khác được đáp ứng | Nhúng iframe, tích hợp cross-site thực sự cần credentials | **Bắt buộc kèm Secure**; tăng bề mặt CSRF, có thể bị browser chặn third-party cookies |

Ví dụ:

```http
Set-Cookie: session_strict=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
Set-Cookie: session_lax=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: session_cross=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Đây là **ba cookie minh họa độc lập**, không phải yêu cầu ứng dụng thật phải tạo cùng lúc ba session cookie.

### 5.1. Ma trận hành vi thường gặp

Giả sử người dùng đăng nhập tại `https://app.example.com` và cookie có host/path khớp đích. Bảng dưới mô tả **điều kiện SameSite trong các browser hiện đại**, giả định các chính sách cookie khác không chặn.

| Tình huống request tới app.example.com | Strict | Lax (khai báo tường minh) | None + Secure |
|---|---|---|---|
| Click nội bộ trong app (same-site) | Gửi | Gửi | Gửi |
| `fetch` từ trang same-site phù hợp | Gửi* | Gửi* | Gửi* |
| Người dùng click link từ `other.net` → top-level `GET` app | Không gửi | Gửi | Gửi |
| Form từ `other.net` → top-level `POST` app | Không gửi | Không gửi | Có thể gửi |
| Tải `<img>` hoặc `iframe` app từ trang `other.net` | Không gửi | Không gửi | Có thể gửi |
| `fetch` từ `other.net` đến app | Không gửi | Không gửi | Có thể gửi* |

Dấu `*`: **SameSite chỉ là một điều kiện**. Với JavaScript `fetch`, còn cần xét `credentials` (đặc biệt cross-origin), CORS, phạm vi cookie, third-party cookie blocking và các chính sách trình duyệt. Với `None`, chữ “có thể” phản ánh việc trình duyệt vẫn có thể từ chối cookie bên thứ ba, đặc biệt trong iframe/tracking contexts.

### 5.2. `Lax` và top-level navigation

`Lax` thường **gửi cookie khi người dùng trực tiếp điều hướng bằng GET từ site ngoài**. Điều đó giúp trải nghiệm: người dùng click link từ email hoặc website đối tác đến trang tài khoản mà vẫn có session. `Strict` có thể khiến request đầu này không mang session; sau khi trang mở và điều hướng trong site, cookie lại được gửi nếu điều kiện same-site thỏa.

Chính vì `Lax` vẫn cho cross-site top-level GET, **không được thiết kế GET có tác dụng thay đổi trạng thái** như `GET /transfer?amount=...`, `GET /delete?id=...`. Phương thức an toàn phải thực sự không có tác dụng phụ nghiệp vụ quan trọng; với thao tác thay đổi trạng thái dùng POST/PUT/PATCH/DELETE và CSRF bảo vệ khi cookie là cơ chế xác thực.

### 5.3. Mặc định SameSite khi không khai báo

Nhiều browser hiện đại áp dụng hành vi kiểu `Lax` khi cookie không có thuộc tính SameSite. **Tuy nhiên không nên phụ thuộc vào mặc định trình duyệt**:

- Chính sách khác nhau theo trình duyệt, chế độ, phiên bản hoặc bối cảnh sử dụng.
- Một số browser triển khai mặc định `Lax` với **ngoại lệ POST cross-site trong khoảng ngắn sau khi cookie được tạo**, thường được gọi là `Lax-allowing-unsafe`. Ngoại lệ này **không tương đương với cookie khai báo tường minh `SameSite=Lax`**.
- Vì vậy hãy đặt `SameSite=Lax` hoặc `Strict` rõ ràng theo policy đã kiểm thử.

### 5.4. `None` có nghĩa là không hạn chế theo SameSite, không phải “không có cookie”

`SameSite=None` **không có nghĩa tắt cookie hoặc không có bảo vệ transport**. Nó cho phép trình duyệt gửi cookie trong các ngữ cảnh cross-site khi đủ điều kiện và **phải kèm `Secure`**:

```http
Set-Cookie: embedded_session=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Thiếu Secure:

```http
Set-Cookie: embedded_session=opaque; Path=/; HttpOnly; SameSite=None
```

Nhiều browser hiện đại **từ chối** cookie dạng thứ hai. Ngay cả cookie hợp lệ `None; Secure` cũng có thể **không được gửi** vì chính sách chặn third-party cookie, privacy/tracking protection hoặc partitioning. Khi cần luồng iframe/cross-site SSO, phải kiểm thử trình duyệt thực, CORS, redirect và hành vi phiên; đừng dựa duy nhất vào flag.

## 6. `SameSite`, CSRF, CORS và XSS là những vấn đề khác nhau

### 6.1. Vì sao SameSite giúp giảm CSRF?

Trong tấn công CSRF, người dùng đang đăng nhập vào `bank.example`, rồi truy cập một site độc hại kích hoạt request đến bank. Nếu browser tự gửi session cookie theo request đó, backend có thể hiểu nhầm request là thao tác được chủ tài khoản cho phép.

`SameSite=Lax` hoặc `Strict` làm giảm nhiều tình huống cookie tự đính kèm vào **cross-site unsafe request**. Tuy nhiên:

1. `Lax` vẫn cho top-level GET cross-site; GET tuyệt đối không nên thực thi hành vi nhạy cảm.
2. Request phát từ subdomain **cùng site** có thể không bị SameSite chặn, ngay cả khi subdomain đó bị chiếm quyền.
3. Browser không phải nơi duy nhất API được gọi; API client không phải browser có thể tự gửi header Cookie.
4. Có thêm trường hợp chuyển hướng, state-changing endpoint, browser policy khác nhau và vòng đời đăng nhập cần được xét.
5. `SameSite=None` theo yêu cầu tích hợp làm cookie dễ xuất hiện hơn trong request cross-site; cần chống CSRF chặt chẽ hơn.

**Kết luận:** Với ứng dụng dùng cookie/session để xác thực, tiếp tục áp dụng **CSRF protection** của Spring Security hoặc cơ chế tương đương đã được review theo threat model, không tắt CSRF chỉ vì thêm `SameSite=Lax`. Có thể cần kiểm tra Origin/Referer đáng tin, xác minh CSRF token và từ chối request không hợp lệ.

### 6.2. Vì sao CORS không thay thế CSRF?

**CORS** quyết định JavaScript ở origin khác có được **đọc response** (và với một số request, có được vượt qua preflight) hay không. Nó không phải quy tắc cấm mọi cách browser **gửi** request như form submission. Một response bị JavaScript chặn đọc vẫn có thể đã khiến server thực hiện hành động, nếu backend xử lý request thiếu CSRF guard.

Một ứng dụng frontend `https://app.example.com` và API `https://api.example.com`:

- **Cùng site** nếu cùng HTTPS và cùng registrable domain, nhưng **khác origin**.
- Cookie host-only do `api.example.com` tạo vẫn có thể được gửi **đến api.example.com**; nó không nhất thiết phải có `Domain=.example.com`.
- Khi JavaScript gọi cross-origin bằng `fetch`, thường cần `credentials: "include"` và API phải trả CORS headers cụ thể phù hợp với origin gọi; `Access-Control-Allow-Origin: *` không tương thích với credentialed CORS response.
- CORS hợp lệ **không tự cho phép** request vượt Spring Security authorization hoặc CSRF.

```javascript
// Chạy tại https://app.example.com, gọi API khác origin
fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
}).then(response => {
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
});
```

Đoạn mã chỉ chứng minh cấu hình gửi credentials từ frontend; có cookie nào thật sự được đính kèm còn phụ thuộc vào SameSite, domain/path, Secure, chính sách browser và việc cookie đã tồn tại. Đừng log session ID ra console.

### 6.3. Vì sao HttpOnly không sửa XSS?

Một đoạn XSS có thể không đọc được `JSESSIONID` có HttpOnly, nhưng vẫn **gọi API bằng phiên hiện hữu**, sửa DOM hoặc đọc dữ liệu frontend có quyền xem. Cần bảo vệ đầu vào/đầu ra, output encoding, CSP phù hợp, thư viện an toàn và cập nhật dependency. `HttpOnly` chỉ là một lớp giảm rủi ro đánh cắp trực tiếp session cookie.

## 7. `Domain`, `Path` và thời hạn cookie cũng quan trọng

Ba flag chính không hoạt động độc lập. Các thuộc tính còn lại quyết định **phạm vi** và **tuổi thọ** của cookie:

| Thuộc tính | Ý nghĩa | Lưu ý bảo mật |
|---|---|---|
| Không khai báo `Domain` | Cookie host-only: gắn với host tạo nó | Ưu tiên khi không cần dùng chung subdomain |
| `Domain=example.com` | Cho phép gửi cookie tới domain và subdomain hợp lệ trong phạm vi này | Tăng diện tích ảnh hưởng của subdomain, có rủi ro cookie tossing/fixation |
| `Path=/app` | Chỉ gửi khi request path phù hợp | **Không phải ranh giới quyền bảo mật** giữa các ứng dụng cùng host |
| `Max-Age=1800` | Có hiệu lực theo giây, tính từ lúc thiết lập | Không đồng nghĩa với thời hạn session ở server |
| `Expires=...` | Hạn theo thời điểm tuyệt đối | Nếu có cả `Max-Age` và `Expires`, `Max-Age` được ưu tiên |
| Không có `Expires` và `Max-Age` | Cookie phiên của browser | Browser có thể khôi phục phiên khi restore; không coi đóng tab là đăng xuất chắc chắn |

Với session identifier, nên dùng giá trị ngẫu nhiên khó đoán, thời hạn hợp lý và rotation/migration session ID sau đăng nhập hoặc nâng quyền, kết hợp server-side logout/invalidation. Spring Security có biện pháp chống session fixation trong các cơ chế phù hợp; **các flag cookie không tự thay thế cơ chế này**.

### 7.1. Ưu tiên cookie host-only

`Set-Cookie` không ghi Domain nghĩa là host-only. Nếu API nằm tại `api.example.com` và frontend ở `app.example.com`, cookie session **có thể** vẫn host-only ở API: browser tự gửi nó đến API khi request phù hợp. Cấp `Domain=example.com` để mọi subdomain cùng nhận cookie **không phải lúc nào cũng cần**, và có thể tạo rủi ro từ các subdomain ít được bảo vệ.

### 7.2. Cookie prefixes

Browser hỗ trợ các prefix đặc biệt áp thêm ràng buộc khi tạo cookie:

- `__Secure-<name>`: phải đặt cookie bằng HTTPS và có `Secure`.
- `__Host-<name>`: phải có `Secure`, `Path=/` và **không được có Domain**; hữu ích để giảm tác động của cookie injection từ subdomain.
- `__Http-<name>` và `__Host-Http-<name>`: thêm yêu cầu `HttpOnly` theo hỗ trợ của browser; cần xem compatibility và không dựa vào prefix đơn độc.

Ví dụ host-only session cookie:

```http
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ví dụ **không hợp lệ** cho prefix `__Host-` vì có Domain:

```http
Set-Cookie: __Host-session=opaque; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Nếu đổi tên session cookie thành `__Host-session`, server hoặc session infrastructure phải **đọc đúng tên mới**. Prefix chỉ là quy ước được browser hỗ trợ và kiểm tra theo khả năng tương thích; nó không thay thế xác thực server-side.

## 8. Cấu hình Spring Boot Servlet / Spring MVC

Với ứng dụng **Spring Boot 3.5** và servlet container auto-configured tương ứng, có thể đặt session cookie bằng `application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /
```

Tương đương trong `application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

**Giải thích:**

1. `secure=true` yêu cầu cookie phiên có `Secure`; production phải có HTTPS ở phía browser. Với môi trường local chỉ chạy `http://127.0.0.1`, cookie Secure có thể hoạt động khác nhau tùy browser; nên test bằng HTTPS gần production.
2. `http-only=true` yêu cầu cookie phiên có `HttpOnly`, giảm nguy cơ lấy session ID qua JavaScript.
3. `same-site=lax` yêu cầu cookie có `SameSite=Lax`. Nếu cần `strict` hoặc `none`, thay bằng giá trị đó **chỉ sau khi review luồng điều hướng và CSRF**; `none` phải đi cùng `secure=true`.
4. `timeout=30m` là thời hạn phía server của phiên Servlet theo cấu hình; nó **không tự đảm bảo** thuộc tính `Max-Age=1800` trên cookie.
5. `path=/` khiến cookie áp dụng trong phạm vi đường dẫn gốc của host; cần cân nhắc đường dẫn ứng dụng thực tế nếu host phục vụ nhiều ứng dụng.

Các property trên là cho **Servlet session cookie**, không tự áp cho mọi cookie khác như custom token, `remember-me`, OAuth2 redirect state hoặc CSRF cookie tùy repository/cơ chế sử dụng. Mỗi cookie phát ra từ các thành phần khác vẫn phải được audit độc lập.

**Lưu ý:** ứng dụng sử dụng Spring Session hoặc container/proxy riêng có thể có thêm cách cấu hình `CookieSerializer`, filter hoặc header rewrite. Kiểm tra `Set-Cookie` **thật** trên response sau deploy, không suy luận hoàn toàn từ file YAML.

### 8.1. Bean Spring Security và cấu hình phiên

`SecurityFilterChain` xử lý xác thực, phân quyền, CSRF, session fixation, logout, headers bảo mật và các bước liên quan. Việc bật cookie flags **không yêu cầu** tắt CSRF hoặc đổi cách phân quyền. Ví dụ lớp cấu hình cơ bản `WebSecurityConfig.java` cho một ứng dụng Spring MVC có form login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
```

Đây là class cấu hình dùng Spring Security 6.x, Java 17+, cần đặt trong ứng dụng Spring Boot MVC có `spring-boot-starter-web` và `spring-boot-starter-security`. Các giá trị Secure/HttpOnly/SameSite thuộc cấu hình session cookie bên trên, không nằm trong `formLogin()`. Mặc định CSRF trong cấu hình dạng này **không bị tắt**. Cần xử lý user/password storage và trang đăng nhập theo ứng dụng thật.

Không hiểu `formLogin` đồng nghĩa tự tạo cookie tại mọi request: session cookie được phát sinh khi framework tạo/dùng session và theo cấu hình session strategy. Để kiểm tra, thực hiện luồng đăng nhập/session thực trong test.

### 8.2. Phân biệt cookie chính của session và cookie do API tự phát

Nếu code tự gửi `Set-Cookie` cho cookie riêng, các property `server.servlet.session.cookie.*` **không đảm bảo** nó có đầy đủ flag. Nên dùng builder chuẩn như Spring `ResponseCookie` và chỉ gửi với logic đã kiểm soát.

Ví dụ dưới đây tạo **một cookie minh họa không phải authentication cookie**. Nó là một controller Java 17+ dùng trong Spring Boot web app, không phải tệp `.java` có thể chạy riêng bằng `javac` khi chưa có dependency Spring.

```java
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SampleCookieController {

    @GetMapping("/public/example-cookie")
    public ResponseEntity<String> issueExampleCookie() {
        ResponseCookie cookie = ResponseCookie
            .from("__Host-example", "sample-value")
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax")
            .path("/")
            .maxAge(Duration.ofMinutes(5))
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .body("Cookie example");
    }
}
```

Do cookie tên `__Host-example` có `Secure`, `Path=/` và **không có Domain**, nó thỏa quy tắc prefix `__Host-` trong browser hỗ trợ. Chuỗi `sample-value` chỉ để học, **không được dùng làm session ID/token thật**. Session cookie chuẩn nên do Spring/container/session store quản lý, không tự chế từ một giá trị đoán được hoặc hardcode.

## 9. Cấu hình Spring Boot WebFlux

Trong Spring Boot 3.5, session cookie ở mô hình **reactive WebFlux** dùng nhóm property riêng `server.reactive.session.cookie.*`:

```yaml
server:
  reactive:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /
```

Cần phân biệt:

| Mô hình | Namespace cấu hình cookie |
|---|---|
| Servlet / Spring MVC | `server.servlet.session.cookie.*` |
| Reactive / Spring WebFlux | `server.reactive.session.cookie.*` |

Không cấu hình cả hai namespace rồi mặc định mong cả hai đều áp dụng. Xác định ứng dụng thực chạy Servlet hay Reactive. Spring Boot có thể chọn Servlet nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, vì vậy nên kiểm tra runtime/app type thực.

Ở WebFlux, lớp bảo mật HTTP được cấu hình qua `ServerHttpSecurity`/`SecurityWebFilterChain` thay vì `HttpSecurity`/`SecurityFilterChain`. Cookie flags và chính sách SameSite là chuyện browser, còn việc lấy session/reactive security context phải giữ đúng luồng Reactor. Ví dụ tối giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveWebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
    }
}
```

**Lưu ý cho ví dụ:** `httpBasic` không mặc nhiên mô tả phiên đăng nhập dùng cookie: Basic có thể xác thực trên từng request qua header `Authorization`. Nếu ứng dụng thực sự cần login bằng session, cần chọn cơ chế authentication/session phù hợp, không kết luận rằng có `SecurityWebFilterChain` thì chắc chắn đang dùng session cookie. YAML bên trên cấu hình **khi WebSession cookie được tạo**, không khiến mọi request tạo session.

## 10. Trường hợp đặc biệt: đăng nhập cross-site, iframe và SPA

### 10.1. Frontend khác origin nhưng vẫn cùng site

Ví dụ:

- Frontend: `https://app.example.com`.
- Backend: `https://api.example.com`.

Hai host là **khác origin**, nhưng thường **cùng site** (đều HTTPS, cùng registrable domain). Trường hợp này có thể dùng `SameSite=Lax` cho cookie host-only của API, kết hợp `fetch(..., { credentials: "include" })` và CORS cấu hình cho frontend cụ thể. **Không tự chọn `SameSite=None` chỉ vì hai origin khác nhau**.

### 10.2. Frontend thật sự cross-site

Ví dụ:

- Frontend: `https://portal.partner.net`.
- Backend: `https://auth.example.com`.

Đây là **cross-site**. Nếu thực sự cần cookie tham gia cross-site request, có thể cần `SameSite=None; Secure`, nhưng vẫn phải xét browser third-party cookie blocking, consent, CORS, CSRF và kiến trúc authentication. Khi third-party cookies bị chặn, đổi flag thành `None` không phải bảo đảm luồng đăng nhập sẽ chạy. Có thể cân nhắc cách tích hợp dựa trên top-level redirect/OIDC flow, same-site frontend/backend, hoặc kiến trúc phù hợp khác đã review bảo mật.

### 10.3. OAuth2/OIDC login redirect không đồng nghĩa mọi cookie phải None

Một luồng authorization code có điều hướng qua identity provider bên ngoài. Sau redirect về callback, request có thể là **top-level GET** và cookie `SameSite=Lax` có thể được gửi. Nhưng các biến thể dùng POST response mode, iframe, silent login hoặc domain khác có yêu cầu khác. Phải kiểm tra chi tiết cách lưu session/state/nonce, phương thức callback và browser được hỗ trợ; không nới `SameSite=None` cho toàn bộ session chỉ từ phán đoán “SSO cần cross-site”.

## 11. Kiểm chứng `Set-Cookie` trên response thật

Đừng chỉ đọc application.yml rồi kết luận cấu hình đã đúng. Kiểm tra browser và response trên **HTTPS** của môi trường gần production:

1. Mở DevTools → **Network** → response tạo phiên (đăng nhập hoặc request khởi tạo session); xem response header `Set-Cookie`, không nhầm với request header `Cookie`.
2. Mở DevTools → **Application/Storage → Cookies**; kiểm tra `Secure`, `HttpOnly`, `SameSite`, Domain, Path, Expires.
3. Reload trang sau đăng nhập; xác nhận session cookie được gửi cho đúng host/path và **không** được gửi đến host/path không phù hợp.
4. Dùng test ngoài site thực để thử top-level GET, POST và iframe/fetch; nhận biết cookie có thể bị chặn bởi CORS/credentials hoặc third-party policy chứ không chỉ SameSite.
5. Kiểm tra cookie sau deploy đằng sau reverse proxy/load balancer; tránh tình huống local đúng nhưng production phát cookie thiếu `Secure` vì scheme forwarding sai.
6. Kiểm tra logout, session invalidation, session fixation defense, CSRF token lifecycle và thời hạn server session.

Lệnh xem response header (chỉ ví dụ; URL cần thuộc môi trường test của bạn):

```bash
curl -i https://app.example.com/public/example-cookie
```

Trong response test từ controller ví dụ, phần `Set-Cookie` phải có các thuộc tính tương tự:

```http
Set-Cookie: __Host-example=sample-value; Path=/; Max-Age=300; Secure; HttpOnly; SameSite=Lax
```

**Thứ tự các thuộc tính có thể khác**; test nên kiểm tra sự có mặt của từng flag, không so khớp tuyệt đối toàn bộ dòng trừ khi API yêu cầu. `curl` **không mô phỏng đầy đủ** quyết định của browser đối với SameSite, CORS hoặc third-party cookies. Không đưa session ID thật vào log hoặc bản chụp chia sẻ công khai.

### 11.1. Trích đoạn test MockMvc cho cookie do controller tạo

Với `spring-boot-starter-test` hoặc tương đương, `MockMvc` và Spring test context đã cấu hình:

```java
MvcResult result = mockMvc
    .perform(get("/public/example-cookie"))
    .andExpect(status().isOk())
    .andReturn();

List<String> cookieHeaders = result.getResponse()
    .getHeaders(HttpHeaders.SET_COOKIE);

assertThat(cookieHeaders).anySatisfy(value -> {
    assertThat(value).contains("__Host-example=");
    assertThat(value).contains("Secure");
    assertThat(value).contains("HttpOnly");
    assertThat(value).contains("SameSite=Lax");
    assertThat(value).contains("Path=/");
});
```

Đây là **trích đoạn** test, không phải lớp test độc lập. Cần import `MvcResult`, `HttpHeaders`, `List`, `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status` và `Assertions.assertThat` của AssertJ; cần inject `MockMvc` và tạo Spring test context. Trích đoạn trên kiểm tra cookie **của endpoint mẫu**, **không tự chứng minh** session cookie `JSESSIONID` được Spring Boot phát đúng: phải tạo session thật trong integration test tương ứng.

### 11.2. Bộ ca kiểm thử theo nguy cơ

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Tạo phiên qua HTTPS | Session cookie có `Secure`, `HttpOnly`, `SameSite` mong muốn |
| Request tới cùng host/path bằng HTTP | Browser không gửi cookie Secure (trừ khác biệt localhost) |
| Chạy `document.cookie` | Không đọc được cookie HttpOnly |
| JavaScript gọi API khi đã đăng nhập | Cookie HttpOnly vẫn có thể được gửi theo cookie policy; API vẫn kiểm tra quyền |
| Cross-site top-level GET | Lax có thể gửi, Strict không gửi |
| Cross-site POST từ site ngoài | Lax khai báo tường minh không gửi session, None có thể gửi nếu browser cho phép |
| Iframe từ site khác | Lax/Strict thông thường không gửi, None + Secure có thể gửi |
| `SameSite=None` thiếu Secure | Browser hiện đại thường từ chối cookie |
| Cookie có prefix `__Host-` nhưng có Domain | Browser hỗ trợ prefix sẽ từ chối |
| CSRF POST không có token | Phải bị từ chối nếu CSRF guard áp dụng, bất kể cookie Lax đã có |
| Logout | Session ở server vô hiệu, cookie phía browser bị hết hạn/xóa theo đúng tên/path/domain |
| Subdomain không tin cậy | SameSite không tự ngăn request cùng site; quyền/CSRF vẫn được kiểm tra |
| Expired session | Server từ chối session ID cũ dù browser còn giữ cookie |
| App qua proxy HTTPS | `Set-Cookie` vẫn giữ `Secure` và domain/path mong muốn |

**Phân biệt browser behavior với header serialization:** Một unit test thấy `SameSite=Lax` trong header chỉ kiểm tra server **phát đúng flag**; muốn biết browser **gửi/không gửi** ở từng trường hợp thực, cần browser integration test.

## 12. Ví dụ Java 17 độc lập: mô hình tư duy SameSite đơn giản

Để củng cố ma trận, có thể viết một **mô hình học tập** bằng Java thuần, không cần Spring. Nó **không mô phỏng đầy đủ trình duyệt**: bỏ qua default-Lax grace, CORS/credentials, third-party blocking, iframe policy, Domain/Path/Secure và redirect chain. Dùng nó để nhớ quy tắc cơ bản chứ **không dùng thay test browser hoặc quyết định security phía server**.

Tệp `SameSitePolicyDemo.java`:

```java
public class SameSitePolicyDemo {

    enum Mode { STRICT, LAX, NONE }

    record Scenario(boolean sameSite,
                    boolean topLevelNavigation,
                    boolean safeMethod) {}

    static boolean allowedBySameSite(Mode mode, Scenario request) {
        if (request.sameSite()) {
            return true;
        }
        return switch (mode) {
            case STRICT -> false;
            case LAX ->
                request.topLevelNavigation() && request.safeMethod();
            case NONE -> true;
        };
    }

    public static void main(String[] args) {
        Scenario externalLinkGet = new Scenario(false, true, true);
        Scenario externalFormPost = new Scenario(false, true, false);

        System.out.println("Strict link GET: "
            + allowedBySameSite(Mode.STRICT, externalLinkGet));
        System.out.println("Lax link GET: "
            + allowedBySameSite(Mode.LAX, externalLinkGet));
        System.out.println("Lax form POST: "
            + allowedBySameSite(Mode.LAX, externalFormPost));
        System.out.println("None form POST: "
            + allowedBySameSite(Mode.NONE, externalFormPost));
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac SameSitePolicyDemo.java
java SameSitePolicyDemo
```

Stdout chính xác theo mô hình trên:

```text
Strict link GET: false
Lax link GET: true
Lax form POST: false
None form POST: true
```

Những giá trị boolean trên chỉ mô tả **cửa SameSite lý tưởng hóa**. Ví dụ `None form POST: true` **không khẳng định** browser sẽ thực sự gửi cookie: còn phải có `Secure`, HTTPS, cookie đúng scope, browser không chặn third-party cookie và request đáp ứng chính sách riêng. Cũng cần phân biệt `safeMethod` (GET/HEAD/OPTIONS/TRACE theo ngữ nghĩa HTTP) với “request không thể gây tác dụng phụ”: phía ứng dụng phải **tự đảm bảo** safe method không thay đổi trạng thái.

## 13. Các lỗi thường gặp và cách sửa

1. **Bỏ `Secure` vì ứng dụng chạy HTTP sau proxy:** đặt cookie Secure theo HTTPS bên ngoài; sửa trust chain/forwarded headers và cấu hình TLS/proxy.
2. **Nghĩ `Secure` tự chặn XSS hoặc mã hóa giá trị trong RAM:** không đúng. Dùng HttpOnly, chống XSS, session hardening và phân quyền.
3. **Tắt `HttpOnly` trên session cookie vì SPA cần biết user nào:** giữ HttpOnly, dùng endpoint `/api/me`; chỉ cân nhắc readable CSRF token cookie khi thật sự cần.
4. **Dùng `SameSite=None` nhưng thiếu `Secure`:** browser thường không chấp nhận cookie; thêm Secure và HTTPS hoặc thiết kế lại tích hợp.
5. **Coi Lax là bảo vệ CSRF hoàn chỉnh:** cross-site top-level GET vẫn mang cookie; same-site subdomain có thể vượt lớp này; luôn bảo vệ unsafe method bằng CSRF control phù hợp.
6. **Coi cross-origin luôn là cross-site:** hai subdomain HTTPS của cùng registrable domain có thể same-site nhưng khác origin; phân biệt CORS và SameSite.
7. **Nghĩ CORS cấm tất cả cross-site POST:** form POST có thể đến server dù frontend JavaScript không đọc được response. Backend phải kiểm soát CSRF.
8. **Dựa vào browser default Lax:** thiếu thuộc tính explicit có thể có hành vi khác nhau, gồm ngoại lệ POST ngắn sau khi tạo cookie.
9. **Gán Domain quá rộng:** `Domain=example.com` khiến nhiều subdomain chia sẻ phạm vi cookie; ưu tiên host-only và prefix `__Host-` nếu phù hợp.
10. **Nhầm Path với biên giới bảo mật:** `Path` là điều kiện gửi cookie, không phải authorization giữa ứng dụng/tenant.
11. **Đặt `Max-Age` vô hạn cho session quan trọng:** tăng thời gian lộ ID hữu dụng nếu bị lấy cắp; cần thời hạn và rotation/invalidation phía server.
12. **Lưu mật khẩu, PII hoặc bearer token nhạy cảm dạng dễ đọc trong cookie:** tốt nhất dùng session ID opaque và giảm dữ liệu phía client.
13. **Tắt CSRF để form/login “hết 403” mà không điều tra:** cần phân biệt sai token, CSRF token chưa được phát, session hết hạn, cookie bị browser chặn, thiếu quyền.
14. **Tưởng every `Set-Cookie` là session:** remember-me, CSRF, tracking/preferences và cookie tự tạo có chính sách khác nhau; phải kiểm tra từng loại.
15. **Test bằng curl rồi suy ra browser hỗ trợ SameSite:** curl chỉ đọc header, không đại diện browser/iframe/credentials/third-party policy.
16. **Dùng HTTP local rồi kết luận cookie Secure “hỏng”:** thử HTTPS hoặc cấu hình môi trường test phù hợp; localhost có ngoại lệ phụ thuộc trình duyệt.

## 14. Checklist triển khai trước production

- [ ] Mọi trang đăng nhập và request mang session cookie đều phục vụ qua HTTPS với cấu hình TLS chuẩn.
- [ ] Session cookie được phát có `Secure=true` và `HttpOnly=true`, xác nhận trên response thật sau proxy.
- [ ] `SameSite` được đặt tường minh: chọn `Lax`/`Strict` theo UX, `None` chỉ khi cần cross-site thực sự và có `Secure`.
- [ ] Xác định **site vs origin** cho frontend/API/identity provider; test login redirect và iframe/cross-site flows nếu có.
- [ ] Giữ CSRF protection hoặc cơ chế tương đương phù hợp với cookie authentication; GET không có tác dụng thay đổi trạng thái.
- [ ] Cookie session ưu tiên host-only; Domain, Path, `__Host-` prefix được kiểm tra có chủ đích.
- [ ] Session ID khó đoán, rotate sau đăng nhập/nâng quyền, invalidation khi logout, giới hạn tuổi thọ hợp lý.
- [ ] Không chứa mật khẩu, dữ liệu cá nhân nhạy cảm hoặc secret không cần thiết trong cookie.
- [ ] Kiểm tra session cookie, CSRF token cookie và các custom cookie **riêng biệt**.
- [ ] Test thực bằng browser trên HTTPS, bao gồm cross-site GET/POST, subdomain, iframe, credentials và third-party cookie restrictions.
- [ ] Xác minh cấu hình đúng web stack: `server.servlet.session.cookie.*` cho MVC, `server.reactive.session.cookie.*` cho WebFlux.
- [ ] Hạn chế XSS, bảo vệ endpoint và dữ liệu ở server; **không coi một cookie flag là bằng chứng authorization**.

## 15. Nguồn tham khảo chính thức

- [MDN — Set-Cookie: Secure, HttpOnly, SameSite, Prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies).
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).

**Ghi nhớ:** `Secure` quyết định **kênh HTTPS**, `HttpOnly` quyết định **JavaScript có thể đọc cookie hay không**, `SameSite` quyết định **khi nào browser gửi cookie trong ngữ cảnh cùng site/khác site**. Ba thuộc tính bổ sung nhau nhưng **không thay thế** TLS, chống XSS, CSRF token, session management, phân quyền ở server hoặc kiểm thử trình duyệt thực.