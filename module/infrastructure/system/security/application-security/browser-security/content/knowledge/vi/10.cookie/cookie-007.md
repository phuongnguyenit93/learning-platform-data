# HttpOnly attribute

> **Chương:** Cookie  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Cookie phiên đăng nhập thường chứa một mã định danh mà browser tự gửi tới server khi request phù hợp. Nếu JavaScript đọc được mã này, một lỗ hổng **Cross-Site Scripting (XSS)** có thể giúp kẻ tấn công lấy giá trị cookie và mang sang môi trường khác. Thuộc tính **`HttpOnly`** được thiết kế để giảm rủi ro đó: cookie vẫn được browser quản lý và gửi trong HTTP request, nhưng các API phía script như `document.cookie` không được phép đọc giá trị của cookie.

`HttpOnly` là một lớp bảo vệ hữu ích cho cookie xác thực, nhưng nó không làm cho ứng dụng miễn nhiễm với XSS. Script độc hại vẫn có thể sử dụng phiên của nạn nhân để gửi request, đọc dữ liệu mà trang có quyền đọc và thực hiện thao tác trong ngữ cảnh người dùng. Vì vậy cần kết hợp `HttpOnly` với phòng vệ XSS, CSRF, `Secure`, `SameSite`, quản lý phiên và phân quyền ở server.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `HttpOnly` thay đổi quyền truy cập cookie của JavaScript như thế nào.
2. Tạo cookie HttpOnly bằng response header `Set-Cookie`.
3. Phân biệt việc script **đọc giá trị cookie** với việc browser **tự gửi cookie trong request**.
4. Giải thích vì sao HttpOnly giảm nguy cơ đánh cắp session qua XSS nhưng không ngăn session riding.
5. Phân biệt `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path` và cookie prefix `__Host-`.
6. Thiết kế session cookie an toàn và xác định khi nào cần CSRF token.
7. Kiểm chứng hành vi cookie trong DevTools và request thực tế.

## 2. HttpOnly là gì?

`HttpOnly` là một **cookie attribute** được server khai báo trong header `Set-Cookie`. Khi cookie có thuộc tính này, browser không cho các API không phải HTTP truy cập giá trị cookie. Trong mã JavaScript của trang, cookie đó không xuất hiện trong `document.cookie`.

Ví dụ server trả:

```http
HTTP/1.1 200 OK
Set-Cookie: session_id=opaque-random-value; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"authenticated":true}
```

Browser lưu cookie theo các thuộc tính được khai báo. Khi một request sau đó thỏa điều kiện domain/host, path, thời hạn, `Secure` và `SameSite`, browser có thể tự đính kèm cookie vào request. JavaScript không được đọc giá trị `session_id` bằng `document.cookie`.

**HttpOnly không mã hóa cookie.** Giá trị vẫn được browser lưu và gửi qua HTTP theo quy tắc cookie. Để bảo vệ trên đường truyền, cần HTTPS và `Secure`; để giới hạn ngữ cảnh gửi cookie, cần cân nhắc `SameSite` và các biện pháp chống CSRF.

## 3. Cách hoạt động: JavaScript không đọc được, browser vẫn gửi được

Giả sử server đặt cookie:

```http
Set-Cookie: __Host-session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trang có thể chạy:

```js
console.log(document.cookie);
```

Kết quả sẽ không chứa cookie `__Host-session`. Tuy nhiên, khi JavaScript gọi API cùng origin:

```js
const response = await fetch("/api/profile");
const profile = await response.json();
```

browser vẫn có thể gửi cookie phiên tự động trong request vì đây là request same-origin và Fetch mặc định dùng `credentials: "same-origin"`. Server nhận cookie trong header `Cookie`, xác định phiên và trả response theo quyền của người dùng.

```mermaid
sequenceDiagram
    participant JS as JavaScript của trang
    participant B as Browser
    participant S as Server
    S-->>B: Set-Cookie: session=...; HttpOnly; Secure
    B-->>JS: document.cookie (không có session)
    JS->>B: fetch('/api/profile')
    B->>S: GET /api/profile + Cookie: session=...
    S-->>B: Response theo phiên
    B-->>JS: Response được phép đọc
```

Đây là điểm cốt lõi: `HttpOnly` giới hạn **script truy cập cookie**, không tắt cơ chế cookie của browser. Ứng dụng có thể dùng cookie phiên mà không cần JavaScript biết giá trị session ID.

## 4. HttpOnly bảo vệ điều gì trước XSS?

XSS xảy ra khi dữ liệu không đáng tin được đưa vào trang theo cách khiến browser thực thi mã do kẻ tấn công kiểm soát. Nếu session cookie không có HttpOnly, script XSS có thể thử:

```js
// Chỉ minh họa hành vi trên cookie lab không có HttpOnly.
const visibleCookies = document.cookie;
```

Nếu cookie xác thực có thể đọc được, script có thể gửi giá trị đó ra ngoài. Kẻ tấn công sau đó có thể sử dụng cookie trên một client khác để mạo danh phiên, miễn cookie/session còn hiệu lực và server chấp nhận nó.

Khi cookie có HttpOnly, việc đọc trực tiếp qua `document.cookie` không lấy được giá trị session. Điều này **giảm một con đường exfiltration phổ biến** và khiến việc mang session cookie sang thiết bị khác khó hơn qua chính API JavaScript của trang.

Nhưng XSS vẫn là lỗ hổng nghiêm trọng. Script độc hại đang chạy trong origin ứng dụng có thể:

- Gọi API cùng origin; browser tự đính kèm cookie HttpOnly phù hợp.
- Đọc response của API mà trang được phép đọc, ví dụ hồ sơ hoặc nội dung tài khoản.
- Thay đổi nội dung DOM, lấy dữ liệu hiển thị hoặc đọc dữ liệu trong bộ nhớ JavaScript.
- Gửi biểu mẫu, thay đổi thông tin, tạo giao dịch hoặc thực hiện hành động mà người dùng hiện tại có quyền làm.
- Cố gắng gửi dữ liệu lấy được ra ngoài nếu chính sách mạng/CSP và các kiểm soát khác cho phép.

Vì vậy, HttpOnly giúp **giảm nguy cơ đánh cắp giá trị cookie**, nhưng không ngăn kẻ tấn công **sử dụng browser như người dùng đang đăng nhập**. Khả năng này thường được gọi là *session riding* hoặc *authenticated action through XSS*.

## 5. Đọc cookie và sử dụng phiên là hai việc khác nhau

| Hành vi | Cookie có HttpOnly |
| --- | --- |
| Đọc giá trị qua `document.cookie` | Không được phép |
| Đọc giá trị qua Cookie Store API của trang | Không được phép truy cập HttpOnly cookie |
| Tạo cookie HttpOnly bằng `document.cookie` | Không thể; thuộc tính này do HTTP response thiết lập |
| Browser tự gửi cookie trong request phù hợp | Có |
| `fetch` same-origin dùng credentials mặc định | Có thể gửi cookie phù hợp |
| XSS gọi API mà người dùng có quyền gọi | Vẫn có thể |
| XSS đọc response same-origin mà trang được phép đọc | Vẫn có thể |
| JavaScript đọc response header `Set-Cookie` | Không; đây là forbidden response header |

`Set-Cookie` là response header đặc biệt. JavaScript không thể đọc nó qua `fetch` như một header bình thường; việc thêm tên này vào `Access-Control-Expose-Headers` cũng không làm nó trở nên có thể đọc được. Browser xử lý `Set-Cookie` nội bộ để cập nhật cookie store.

Không nên thiết kế frontend dựa trên việc đọc session cookie. Nếu UI cần biết trạng thái đăng nhập, hãy cung cấp endpoint hoặc dữ liệu bootstrap chỉ trả trạng thái cần thiết, ví dụ `GET /api/session`, và bảo đảm server chỉ trả thông tin phù hợp với phiên hiện tại.

## 6. HttpOnly phải được đặt từ server

Thuộc tính HttpOnly được gửi trong `Set-Cookie`:

```http
Set-Cookie: session_id=...; HttpOnly; Path=/; Secure; SameSite=Lax
```

JavaScript không thể nâng một cookie hiện có thành HttpOnly bằng cách gán `document.cookie`. Nếu ứng dụng cần session cookie HttpOnly, backend hoặc thành phần server quản lý session phải phát hành cookie với thuộc tính đó.

Ví dụ cấu hình ở mức khái niệm:

```js
// Pseudocode: tên option cụ thể tùy framework/session library.
setSessionCookie(response, sessionId, {
  httpOnly: true,
  secure: true,
  sameSite: "lax",
  path: "/",
  // Không đặt Domain nếu muốn cookie host-only.
});
```

Tên option và cách viết có thể khác giữa framework. Cần kiểm tra response `Set-Cookie` cuối cùng từ ứng dụng/proxy để xác nhận thuộc tính thực sự được gửi, thay vì chỉ tin cấu hình trong source code.

## 7. HttpOnly không thay thế Secure và SameSite

Ba thuộc tính thường được dùng cùng nhau nhưng bảo vệ các vấn đề khác nhau:

| Attribute | Tác dụng chính | Không giải quyết |
| --- | --- | --- |
| `HttpOnly` | Ngăn API script đọc giá trị cookie | Không ngăn XSS sử dụng phiên, không tự chống CSRF |
| `Secure` | Chỉ gửi cookie qua kết nối bảo mật phù hợp (HTTPS) | Không ngăn JavaScript đọc cookie nếu thiếu HttpOnly; không phân quyền |
| `SameSite` | Hạn chế gửi cookie trong nhiều ngữ cảnh cross-site | Không ngăn mọi CSRF, không cô lập subdomain cùng site |

Ví dụ cookie phiên:

```http
Set-Cookie: __Host-session=...; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ở đây:

- `Secure` yêu cầu browser chỉ gửi cookie qua HTTPS.
- `HttpOnly` chặn script đọc cookie.
- `SameSite=Lax` giảm việc cookie được gửi trong nhiều request cross-site, nhưng vẫn có ngoại lệ như một số top-level navigation an toàn.
- `Path=/` cho cookie áp dụng trên toàn bộ path của host.
- Prefix `__Host-` áp dụng thêm ràng buộc cookie: cần `Secure`, `Path=/` và không được có `Domain` trong các browser hỗ trợ prefix này.

Nếu ứng dụng thật sự cần cookie trong ngữ cảnh cross-site, có thể cần `SameSite=None; Secure`, nhưng khi đó phải thiết kế CSRF protection phù hợp và xét chính sách chặn/partition cookie bên thứ ba của browser.

## 8. Phạm vi cookie: host-only, Domain và Path

HttpOnly không quyết định cookie được gửi tới host nào hoặc path nào. Những thuộc tính phạm vi vẫn có ý nghĩa độc lập.

### 8.1 Host-only cookie

Nếu server bỏ thuộc tính `Domain`, cookie được giới hạn cho host đã phát hành nó:

```http
Set-Cookie: session=...; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie đặt từ `app.example.com` không tự được gửi tới `api.example.com` chỉ vì hai host cùng site.

### 8.2 Cookie có Domain

```http
Set-Cookie: session=...; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie có thể được gửi tới host phù hợp thuộc domain đó và các subdomain theo quy tắc cookie. Điều này mở rộng phạm vi cần bảo vệ: một subdomain bị takeover hoặc có XSS có thể làm tăng rủi ro đối với các luồng cùng site, dù script vẫn không đọc được cookie HttpOnly.

### 8.3 Path

`Path` giới hạn những đường dẫn mà browser gửi cookie. Tuy nhiên, Path không phải ranh giới bảo mật đáng tin cậy giữa các ứng dụng trên cùng host. Không dùng `Path=/admin` như biện pháp thay thế origin riêng, phân quyền hoặc cô lập ứng dụng.

### 8.4 Prefix `__Host-`

Với cookie xác thực nhạy cảm, prefix `__Host-` giúp buộc cookie vào host phát hành:

```http
Set-Cookie: __Host-session=...; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie `__Host-` phải được đặt trong ngữ cảnh bảo mật, có `Secure`, có `Path=/` và không có `Domain` theo quy tắc prefix của browser hỗ trợ. Nó giúp ngăn chia sẻ cookie qua thuộc tính Domain và giảm một số rủi ro ghi đè cookie giữa subdomain. Nó không ngăn XSS trên chính host dùng phiên, cũng không thay thế authorization/CSRF.

## 9. HttpOnly và CSRF

CSRF xảy ra khi browser của người dùng gửi request tới ứng dụng đã đăng nhập theo cách khiến server nhầm request đó là hành động hợp lệ của người dùng. Cookie được browser tự động đính kèm là một lý do cookie-based session cần chống CSRF.

`HttpOnly` không ngăn CSRF. Trên thực tế, cookie HttpOnly vẫn được browser gửi tự động trong request phù hợp; đó chính là cách ứng dụng dùng nó để duy trì phiên mà JavaScript không cần biết giá trị.

Ví dụ, một trang bên ngoài có thể cố gắng gửi form tới endpoint thay đổi trạng thái. Nếu cookie được gửi và server không kiểm tra CSRF, hành động có thể xảy ra dù script của trang ngoài không đọc được cookie hay response.

Biện pháp phòng vệ nên kết hợp theo kiến trúc:

- Cookie `SameSite` phù hợp với luồng ứng dụng.
- CSRF token được server xác minh cho các thao tác thay đổi trạng thái.
- Kiểm tra `Origin`/`Referer` hoặc Fetch Metadata như tín hiệu bổ sung.
- Không dùng GET cho thao tác thay đổi dữ liệu.
- Xác thực, phân quyền và kiểm tra trạng thái nghiệp vụ ở server.

Nếu dùng double-submit cookie, cần thiết kế token chống giả mạo và ràng buộc phù hợp; không giả định chỉ cần một cookie đọc được bằng JavaScript là đủ. Một số thiết kế cần token được cung cấp qua HTML hoặc response body/header riêng, trong khi session cookie vẫn HttpOnly.

## 10. HttpOnly và XSS: biện pháp giảm thiểu, không phải sửa gốc

HttpOnly là một lớp giảm thiểu tác động sau khi script độc hại đã chạy. Nó không loại bỏ nguồn XSS. Cần xử lý lỗ hổng tại điểm dữ liệu đi vào và điểm dữ liệu được hiển thị:

- Dùng output encoding đúng ngữ cảnh HTML, attribute, URL, CSS và JavaScript.
- Ưu tiên DOM API an toàn như `textContent` khi chỉ cần hiển thị văn bản.
- Tránh sink nguy hiểm như `innerHTML`, `outerHTML`, `document.write` với dữ liệu không tin cậy.
- Khi cần render HTML do người dùng cung cấp, dùng sanitizer đã được kiểm chứng và cấu hình phù hợp.
- Triển khai CSP với nonce/hash và hạn chế script source; tránh `'unsafe-inline'` nếu không có lý do đã đánh giá.
- Cân nhắc Trusted Types để giảm việc đưa chuỗi tùy ý vào DOM sink nguy hiểm trên browser hỗ trợ.
- Kiểm soát dependency và script bên thứ ba chạy trong origin có quyền truy cập dữ liệu nhạy cảm.

Một ví dụ DOM an toàn hơn:

```js
const message = new URLSearchParams(location.search).get("message") ?? "";
document.querySelector("#message").textContent = message;
```

Nếu XSS vẫn xảy ra, HttpOnly giúp hạn chế việc đọc session ID, nhưng không ngăn script đọc nội dung trang hoặc gọi API trong quyền của người dùng. Vì vậy, phòng vệ XSS vẫn là ưu tiên chính.

## 11. Session riding và giảm tác động khi XSS xảy ra

Khi cookie HttpOnly không thể bị đọc trực tiếp, kẻ tấn công vẫn có thể lợi dụng browser đang có phiên. Server nhìn thấy request hợp lệ về mặt cookie và có thể thực hiện hành động nếu thiếu lớp bảo vệ khác.

Các biện pháp giảm tác động:

1. **Phân quyền tối thiểu:** mỗi tài khoản và session chỉ có quyền cần thiết.
2. **Xác minh bổ sung cho thao tác nhạy cảm:** đổi email, thay mật khẩu, thanh toán, xuất dữ liệu hoặc thay đổi MFA có thể cần xác nhận lại mật khẩu, WebAuthn hoặc bước xác minh phù hợp.
3. **CSRF protection:** ngăn website khác lợi dụng browser gửi request có cookie.
4. **Giới hạn thời gian và vòng đời session:** idle timeout, absolute timeout, thu hồi session, rotation sau đăng nhập hoặc thay đổi đặc quyền.
5. **Giám sát hành vi:** phát hiện bất thường về tốc độ, thiết bị, địa điểm hoặc chuỗi thao tác theo chính sách riêng tư và rủi ro.
6. **Giảm dữ liệu trả về:** API chỉ trả trường cần thiết; tránh để một request có thể đọc toàn bộ dữ liệu tài khoản.
7. **Kiểm soát script:** CSP, Trusted Types và quản lý dependency giúp giảm khả năng XSS hoặc script không mong muốn.

Không nên yêu cầu xác nhận lại cho mọi request vì sẽ làm hỏng trải nghiệm. Hãy xác định thao tác có hậu quả cao và áp dụng step-up authentication phù hợp.

## 12. Thiết kế session cookie an toàn

Một cookie phiên cho ứng dụng HTTPS có thể có dạng:

```http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

Đây là ví dụ cấu hình, thời hạn và SameSite cần điều chỉnh theo luồng sản phẩm. Các điểm thiết kế:

- Session ID nên là giá trị ngẫu nhiên đủ mạnh, không chứa thông tin cá nhân hoặc quyền hạn có thể giải mã từ phía client.
- Server lưu trạng thái phiên hoặc dùng cơ chế token có thiết kế vòng đời và thu hồi phù hợp.
- Xoay session ID sau đăng nhập, nâng quyền hoặc sự kiện xác thực quan trọng để giảm session fixation.
- Thu hồi session khi logout, đổi mật khẩu hoặc phát hiện sự cố theo chính sách.
- Đặt `HttpOnly`, `Secure`, `SameSite` và phạm vi host/path phù hợp.
- Ưu tiên host-only cookie hoặc `__Host-` nếu không cần chia sẻ cookie giữa subdomain.
- Dùng HTTPS toàn bộ luồng; cân nhắc HSTS để giảm nguy cơ truy cập HTTP.
- Tránh lưu session ID trong `localStorage` hoặc `sessionStorage` nếu mục tiêu là không cho JavaScript đọc credential.

`Max-Age` và `Expires` quyết định thời hạn cookie ở browser; chúng không tự bảo đảm session phía server đã hết hiệu lực. Server phải thực thi timeout và thu hồi session độc lập. Nếu cookie hết hạn nhưng session server còn sống, cookie cũ không còn được browser gửi tự động; nếu session server bị thu hồi, cookie còn lưu cũng không được chấp nhận.

## 13. HttpOnly và token trong localStorage

Một số ứng dụng lưu access token trong `localStorage` để JavaScript đọc và gắn vào `Authorization` header. Cách này khác với session cookie HttpOnly:

| Vị trí credential | JavaScript đọc được? | Tự gửi theo cookie rules? | Tác động XSS thường gặp |
| --- | --- | --- | --- |
| HttpOnly cookie | Không qua API script | Có, nếu request thỏa điều kiện cookie/credentials | Không dễ lấy trực tiếp giá trị; vẫn có thể dùng phiên để gọi API |
| Cookie không HttpOnly | Có qua `document.cookie` nếu cookie phù hợp | Có | Có thể đọc và exfiltrate giá trị cookie |
| `localStorage` | Có | Không; ứng dụng thường tự gắn vào header | Có thể đọc và exfiltrate token |
| Biến trong memory | Có với script cùng context | Không tự động | Có thể bị đọc/khai thác khi XSS chạy trong context đó |

Không có nơi lưu credential nào loại bỏ được XSS. HttpOnly giảm khả năng script lấy trực tiếp session cookie; token trong localStorage thường dễ bị đọc hơn khi XSS xảy ra. Ngược lại, cookie tự gửi có thể tạo rủi ro CSRF nên cần SameSite và CSRF protection. Lựa chọn phụ thuộc kiến trúc SPA, backend, OAuth/OIDC, thời hạn token, khả năng thu hồi và mô hình đe dọa.

## 14. Kiểm chứng HttpOnly trong DevTools

Thực hiện trong môi trường local/lab có tài khoản thử nghiệm. Không lấy cookie phiên thật để chia sẻ hoặc ghi vào log.

### Bài thử A — So sánh cookie có và không có HttpOnly

Tạo hai cookie lab qua response:

```http
Set-Cookie: visible_lab=visible-value; Path=/; Secure; SameSite=Lax
Set-Cookie: protected_lab=protected-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong Console:

```js
console.log(document.cookie);
```

**Kỳ vọng:** `visible_lab` có thể xuất hiện nếu các điều kiện cookie phù hợp; `protected_lab` không xuất hiện.

### Bài thử B — Xác minh browser vẫn gửi HttpOnly cookie

Từ cùng origin, gọi endpoint lab:

```js
const response = await fetch("/api/whoami");
console.log(await response.json());
```

Trong DevTools → Network, chọn request và xem phần Request Headers/Cookies (cách hiển thị tùy browser). Kiểm tra server log cho biết cookie lab có được gửi và phiên thử nghiệm có được nhận diện hay không. Không ghi giá trị cookie thô vào log.

**Kỳ vọng:** Cookie HttpOnly phù hợp được browser đính kèm dù `document.cookie` không đọc được nó.

### Bài thử C — HttpOnly không ngăn session riding

Trong ứng dụng lab có endpoint chỉ trả dữ liệu giả, mô phỏng một script chạy trong origin bằng cách gọi API:

```js
const response = await fetch("/api/lab-profile");
const profile = await response.json();
console.log("Dữ liệu lab đọc được:", profile);
```

Không thực hiện hành động phá hủy hoặc gửi dữ liệu ra ngoài. Quan sát server nhận phiên lab và trả dữ liệu.

**Kỳ vọng:** Script không biết session ID nhưng browser vẫn dùng phiên khi gửi request. Đây là lý do HttpOnly không thay thế phòng vệ XSS.

### Bài thử D — Kiểm tra `Set-Cookie` và phạm vi cookie

Trong Network, chọn response đăng nhập và kiểm tra header `Set-Cookie`. Xác nhận `HttpOnly`, `Secure`, `SameSite`, `Path` và việc có/không có `Domain`. So sánh với tab Application/Storage → Cookies. Cookie HttpOnly thường vẫn được hiển thị trong DevTools của người dùng, nhưng không xuất hiện trong `document.cookie`.

**Kỳ vọng:** Cấu hình thực tế từ response khớp với chính sách thiết kế. Việc DevTools hiển thị cookie không có nghĩa JavaScript của trang được phép đọc nó.

### Bài thử E — Kiểm tra CSRF độc lập

Trong lab, tạo endpoint POST thay đổi một giá trị giả và dùng session cookie HttpOnly. Gửi request từ trang lab khác; thử khi bật/tắt CSRF token và thay đổi SameSite theo các cấu hình thử nghiệm.

**Kỳ vọng:** HttpOnly không tự chặn request; server cần CSRF protection và kiểm tra quyền. Ghi nhận cookie có được gửi hay không, request có đến server hay không và server có chấp nhận thao tác hay không.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng HttpOnly chặn XSS | XSS vẫn có thể đọc dữ liệu trang và gọi API bằng phiên hiện tại | Sửa XSS tại nguồn; dùng CSP/Trusted Types và HttpOnly như lớp bổ sung |
| Cho rằng HttpOnly chặn CSRF | Browser vẫn gửi cookie phù hợp trong request cross-site/same-site | SameSite, CSRF token, Origin/Fetch Metadata và kiểm tra server |
| Chỉ đặt HttpOnly mà bỏ Secure | Cookie vẫn có thể bị gửi qua HTTP nếu các điều kiện khác cho phép | Dùng HTTPS và `Secure`; cân nhắc HSTS |
| Dùng `Domain=example.com` không cần thiết | Mở rộng phạm vi cookie tới subdomain | Dùng host-only hoặc `__Host-` khi phù hợp |
| Lưu session ID trong localStorage rồi nghĩ đã có HttpOnly | JavaScript vẫn đọc được token | Dùng server-issued HttpOnly cookie nếu kiến trúc phù hợp |
| Dùng cookie HttpOnly cho dữ liệu frontend cần tự đọc | Frontend không thể đọc trực tiếp, dẫn đến workaround yếu | Cung cấp endpoint trạng thái/dữ liệu tối thiểu từ server |
| Không xoay hoặc thu hồi session | Cookie bị lộ từ nguồn khác có thể dùng lâu | Rotation, timeout và server-side revocation |
| Chỉ kiểm tra cấu hình source code | Proxy/framework có thể bỏ hoặc ghi đè Set-Cookie | Kiểm tra response header thực tế trong Network và integration test |

## 16. Câu hỏi tự kiểm tra

1. Vì sao cookie HttpOnly không xuất hiện trong `document.cookie` nhưng vẫn có thể xuất hiện trong request `Cookie` tới server?
2. Nếu XSS không đọc được session ID, script độc hại còn có thể làm gì trong origin ứng dụng?
3. HttpOnly khác `Secure` và `SameSite` ở điểm nào?
4. Vì sao HttpOnly không phải biện pháp chống CSRF?
5. Cookie host-only khác cookie có `Domain` ra sao? `__Host-` giúp củng cố điều gì?
6. Tại sao `Set-Cookie` không thể được frontend đọc như response header thông thường?
7. Nếu UI cần biết trạng thái đăng nhập nhưng không cần biết session ID, nên thiết kế API thế nào?
8. Những lớp phòng vệ nào giảm tác động của session riding sau khi XSS xảy ra?

## 17. Ghi nhớ

`HttpOnly` yêu cầu browser **không cung cấp giá trị cookie cho các API script**, giúp giảm nguy cơ XSS đọc và đánh cắp session cookie trực tiếp. Browser vẫn có thể tự gửi cookie trong request phù hợp, nên script XSS vẫn có thể sử dụng phiên của nạn nhân để gọi API và thực hiện hành động trong phạm vi quyền của họ.

Với cookie xác thực, hãy cân nhắc `HttpOnly; Secure; SameSite`, giới hạn phạm vi bằng host-only hoặc `__Host-` khi phù hợp, quản lý vòng đời session và chống CSRF. Đồng thời sửa XSS tại nguồn bằng output encoding, DOM API an toàn, CSP và Trusted Types. **HttpOnly giảm khả năng lấy credential; nó không biến một trang có XSS thành trang an toàn.**
