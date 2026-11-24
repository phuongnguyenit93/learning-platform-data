# Browser session

> **Chương:** Session trên browser  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Khi người dùng mở website, đăng nhập, chuyển qua nhiều trang rồi đóng tab, trình duyệt phải quản lý nhiều loại trạng thái: cookie, dữ liệu lưu theo tab, dữ liệu lưu theo origin và trạng thái đăng nhập do server duy trì. Những trạng thái này thường được gọi chung là “session”, nhưng chúng có vòng đời và ranh giới bảo mật khác nhau.

Hiểu **browser session** đòi hỏi phân biệt phiên duyệt web của trình duyệt, phiên đăng nhập của ứng dụng, session cookie và `sessionStorage`. Nếu nhầm chúng với nhau, ứng dụng có thể xóa cookie nhưng vẫn giữ phiên server, cho rằng đóng tab sẽ đăng xuất người dùng, hoặc lưu credential vào nơi JavaScript có thể đọc khi XSS xảy ra.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt browser/browsing session, authentication session, session cookie và `sessionStorage`.
2. Mô tả cách HTTP request mang cookie để server nhận diện phiên đăng nhập.
3. Giải thích vì sao session cookie hết hạn ở browser không đồng nghĩa server session đã bị thu hồi.
4. So sánh cookie, `sessionStorage`, `localStorage` và bộ nhớ JavaScript theo phạm vi, vòng đời và rủi ro.
5. Phân tích tác động của origin, site, tab, profile và chế độ riêng tư tới dữ liệu phiên.
6. Thiết kế vòng đời phiên gồm tạo, xoay, hết hạn, đăng xuất và thu hồi.
7. Liên hệ quản lý phiên với XSS, CSRF, SOP, CORS, HttpOnly, Secure và SameSite.
8. Kiểm chứng hành vi phiên bằng DevTools trong môi trường thử nghiệm.

## 2. “Session” có nhiều nghĩa

Trong phát triển web, từ *session* thường được dùng cho một số khái niệm khác nhau. Cần gọi đúng tên để xác định ai quản lý dữ liệu và khi nào dữ liệu kết thúc.

| Khái niệm | Được quản lý bởi | Phạm vi/vòng đời điển hình |
| --- | --- | --- |
| **Browser session / browsing session** | Trình duyệt và profile | Khoảng thời gian người dùng sử dụng một browser context/profile; có thể gồm nhiều tab và cửa sổ |
| **Top-level browsing context (tab/window)** | Browser | Một tab/cửa sổ có lịch sử điều hướng và `sessionStorage` riêng theo origin |
| **Authentication session / server session** | Ứng dụng server | Trạng thái đăng nhập, danh tính, thời hạn và quyền của một phiên được server xác minh |
| **Session cookie** | Cookie store của browser | Cookie không khai báo `Expires`/`Max-Age`; browser thường coi là cookie theo phiên duyệt |
| **`sessionStorage`** | Browser Storage API | Dữ liệu theo origin và top-level browsing context, thường kết thúc khi tab/window đóng |
| **JavaScript memory state** | JavaScript runtime của trang | Biến, object và state trong document/runtime; thường mất khi document bị thay thế hoặc reload |

Các khái niệm này liên quan nhưng không đồng nhất. Ví dụ, một người dùng có thể mở nhiều tab trong cùng browser session, mỗi tab có `sessionStorage` riêng, trong khi tất cả cùng dùng một authentication session thông qua cookie chung của host.

## 3. Vì sao ứng dụng cần session?

HTTP về cơ bản là giao thức request/response không tự ghi nhớ trạng thái đăng nhập giữa các request. Server cần một cách nhận biết những request sau thuộc cùng một phiên người dùng.

Một mô hình phổ biến là **server-side session**:

1. Người dùng gửi thông tin đăng nhập qua HTTPS.
2. Server xác thực thông tin và tạo session record.
3. Server sinh một session identifier ngẫu nhiên, khó đoán, không chứa thông tin cá nhân hoặc quyền có thể suy ra.
4. Server gửi identifier trong cookie với các thuộc tính bảo mật.
5. Browser lưu cookie và tự gửi nó trong các request phù hợp.
6. Server tra cứu session, kiểm tra trạng thái và xác định người dùng cho request hiện tại.

```mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant S as Web server
    participant DB as Session store
    U->>B: Gửi thông tin đăng nhập
    B->>S: POST /login qua HTTPS
    S->>S: Xác thực thông tin
    S->>DB: Tạo session mới
    DB-->>S: Session ID / record
    S-->>B: Set-Cookie: session=...; HttpOnly; Secure
    B-->>U: Trang đã đăng nhập
    B->>S: GET /account + Cookie
    S->>DB: Tra cứu và kiểm tra session
    DB-->>S: Session còn hiệu lực
    S-->>B: Response theo danh tính phiên
```

Cookie thường chỉ mang **mã định danh phiên**. Dữ liệu như user ID, thời điểm hết hạn, trạng thái thu hồi hoặc quyền hiện tại nên được quản lý và kiểm tra theo thiết kế phía server. Với token tự chứa, server có thể xác minh chữ ký thay vì tra session store ở mọi request, nhưng vẫn cần chiến lược hết hạn, thu hồi và cập nhật quyền phù hợp.

## 4. Session cookie không đồng nghĩa authentication session

Một cookie được gọi là **session cookie** khi nó không có `Expires` hoặc `Max-Age`. Browser thường lưu nó trong cookie store theo phiên duyệt hiện tại và xóa khi browser session kết thúc. Cookie có `Expires` hoặc `Max-Age` thường được gọi là persistent cookie.

Ví dụ session cookie:

```http
Set-Cookie: session_id=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ví dụ persistent cookie:

```http
Set-Cookie: session_id=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

Nhưng có một điểm quan trọng: **session cookie của browser không đặt thời hạn authentication session trên server**. Server có thể hết hạn hoặc thu hồi session sau 15 phút không hoạt động dù cookie vẫn còn trong browser. Ngược lại, cookie session có thể bị browser xóa khi kết thúc phiên duyệt, trong khi session record phía server vẫn còn cho tới khi hết timeout hoặc được dọn dẹp.

Ngoài ra, nhiều browser có tính năng khôi phục phiên duyệt sau khi đóng/mở lại. Một số browser có thể khôi phục session cookie cùng trạng thái tab khi người dùng chọn restore. Vì vậy, không nên dùng việc “không có Max-Age” như một cam kết chắc chắn rằng cookie luôn biến mất ngay khi cửa sổ browser đóng.

| Sự kiện | Cookie trong browser | Authentication session ở server |
| --- | --- | --- |
| Đóng tab | Thường vẫn còn trong cookie store | Thường vẫn còn hiệu lực |
| Đóng browser hoàn toàn | Session cookie thường kết thúc; có thể được khôi phục tùy browser | Không tự động bị thu hồi |
| Cookie hết `Max-Age`/`Expires` | Browser ngừng gửi cookie đã hết hạn | Session server có thể vẫn tồn tại |
| Server thu hồi session | Cookie có thể vẫn còn trong browser | Server từ chối session đó |
| Người dùng logout đúng cách | Server yêu cầu xóa cookie | Server vô hiệu hóa phiên theo thiết kế |

Do đó, hãy thiết kế timeout và logout ở server; đừng phụ thuộc vào vòng đời cookie để bảo vệ phiên.

## 5. Browser lưu cookie và gửi chúng như thế nào?

Browser quản lý cookie trong cookie store. Khi chuẩn bị request, browser xét các điều kiện như:

- Host-only hoặc thuộc tính `Domain`.
- `Path` của cookie.
- Thời hạn `Expires`/`Max-Age`.
- `Secure` và scheme/kết nối của request.
- `SameSite` và ngữ cảnh site của request.
- Chính sách cookie bên thứ ba, partitioning và các thiết lập riêng tư của browser.
- Chế độ credentials của API tạo request, ví dụ Fetch.

Nếu cookie phù hợp, browser thêm nó vào header `Cookie` của request. JavaScript không tự đặt header `Cookie` bằng `fetch`; đây là forbidden request header do browser quản lý. Với cookie `HttpOnly`, JavaScript cũng không đọc được giá trị qua `document.cookie`, nhưng browser vẫn có thể gửi cookie đó.

Cookie không được phân vùng theo port. Hai ứng dụng trên `https://example.com:443` và `https://example.com:8443` khác origin, nhưng cookie không dùng port làm thành phần phạm vi. Đây là một khác biệt cần nhớ khi thiết kế nhiều ứng dụng trên cùng host.

## 6. Cookie, sessionStorage, localStorage và memory

Các nơi lưu trạng thái phía browser có đặc tính khác nhau:

| Nơi lưu | Phạm vi chính | Tự gửi trong HTTP request? | JavaScript đọc được? | Vòng đời |
| --- | --- | --- | --- | --- |
| Cookie | Host/domain, path và các chính sách cookie | Có, khi phù hợp | Có, trừ cookie HttpOnly | Session cookie hoặc persistent cookie |
| `sessionStorage` | Origin + top-level browsing context | Không | Có | Theo page session/tab; thường mất khi tab/window đóng |
| `localStorage` | Origin trong storage partition tương ứng | Không | Có | Tồn tại qua reload và browser restart, trừ khi bị xóa/chính sách storage thay đổi |
| JavaScript memory | Runtime/context của trang | Không | Có trong context | Thường mất khi document/runtime bị thay thế |
| IndexedDB | Origin/storage partition tương ứng | Không | Có | Lưu bền cho tới khi bị xóa, eviction hoặc storage partition kết thúc |

Không nên lưu session ID nhạy cảm trong `localStorage` chỉ vì muốn giữ đăng nhập lâu hơn: mọi script chạy cùng origin có thể đọc dữ liệu đó, bao gồm script XSS. `sessionStorage` cũng có thể bị XSS đọc; tên gọi “session” không tạo ra ranh giới bảo mật chống script độc hại.

### 6.1 `sessionStorage` theo tab

`sessionStorage` được phân vùng theo origin và top-level browsing context. Hai tab cùng mở `https://app.example.com` thường có hai vùng `sessionStorage` độc lập:

```js
sessionStorage.setItem("wizard-step", "2");
```

Reload trang trong cùng tab không nhất thiết xóa dữ liệu. Khi một tab mới được mở với `window.open` và có opener, browser có thể khởi tạo `sessionStorage` của tab mới bằng bản sao trạng thái ban đầu của opener; sau đó hai vùng lưu trữ độc lập. Nếu mở bằng `noopener`, quan hệ opener bị loại bỏ và không có việc sao chép theo cách đó.

`sessionStorage` hữu ích cho trạng thái tạm theo tab như tiến trình wizard, bộ lọc hoặc dữ liệu form chưa gửi. Không dùng nó làm cơ chế xác thực server-side: server không tự nhận được dữ liệu này trong request, và JavaScript cùng origin có thể đọc/sửa nó.

### 6.2 Cookie chia sẻ giữa tab

Cookie phù hợp được lưu ở cookie store của profile và có thể được dùng bởi nhiều tab cùng host/path, không bị giới hạn theo tab. Vì thế, người dùng đăng xuất ở một tab có thể làm những tab khác mất phiên khi server thu hồi session và cookie được xóa. Nhưng giao diện ở tab còn mở có thể vẫn hiển thị dữ liệu đã tải trước đó; ứng dụng nên xử lý `401`/`403`, cập nhật trạng thái đăng nhập và tránh coi dữ liệu trong memory là còn hợp lệ mãi.

## 7. Origin, site, tab và browser profile

Các cơ chế browser dùng những ranh giới khác nhau:

- **Origin** là `scheme + host + port`; SOP và CORS chủ yếu dựa trên origin.
- **Site** trong mô hình schemeful thường dựa trên scheme và registrable domain; SameSite cookie dùng ngữ cảnh site.
- **Cookie scope** dựa trên host/domain, path và thuộc tính cookie; port không tạo cookie boundary.
- **`sessionStorage`** dựa trên origin và top-level browsing context.
- **`localStorage`** dựa trên origin trong storage partition tương ứng.
- **Browser profile/private context** có thể có cookie store và storage riêng.

Ví dụ, `https://app.example.com` và `https://api.example.com` có thể same-site nhưng cross-origin. Hai tab ở hai host có thể chia sẻ một cookie `Domain=example.com` nếu các điều kiện cookie phù hợp, nhưng JavaScript ở app vẫn không mặc nhiên đọc response API do SOP/CORS. Ngược lại, hai tab cùng origin có thể chia sẻ localStorage nhưng mỗi tab có sessionStorage riêng.

Chế độ riêng tư/incognito thường dùng vùng lưu trữ tách biệt và xóa dữ liệu tạm khi phiên riêng tư kết thúc theo chính sách browser. Browser cũng ngày càng áp dụng partitioning cho một số storage/cookie bên thứ ba. Không nên giả định mọi browser/profile đều dùng chung một cookie jar hoặc có cùng chính sách lưu trữ.

## 8. Authentication session và vòng đời đăng nhập

Một authentication session cần có vòng đời rõ ràng, không chỉ là cookie tồn tại trong browser.

### 8.1 Tạo phiên

Sau khi xác thực thành công, server nên tạo session ID mới bằng nguồn ngẫu nhiên an toàn, đủ entropy và không thể dự đoán. Không dùng username, timestamp, số tăng dần hoặc dữ liệu do client tự chọn làm session ID.

Ví dụ response:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Prefix `__Host-` yêu cầu cookie có `Secure`, `Path=/` và không có `Domain` trong browser hỗ trợ prefix. Đây là cách giới hạn cookie vào host phát hành, không phải thay thế kiểm tra session.

### 8.2 Xoay session ID

Server nên tạo ID mới sau những sự kiện làm thay đổi mức độ tin cậy, chẳng hạn:

- Người dùng đăng nhập thành công.
- Người dùng nâng quyền hoặc hoàn tất xác thực đa yếu tố.
- Người dùng thay đổi mật khẩu hoặc khôi phục tài khoản.
- Phiên chuyển từ trạng thái anonymous sang authenticated.

Xoay ID giúp giảm **session fixation**, trong đó kẻ tấn công tìm cách khiến nạn nhân dùng một session ID mà kẻ tấn công đã biết hoặc kiểm soát. Khi xoay, server cần vô hiệu hóa ID cũ theo chính sách và cập nhật cookie mới.

### 8.3 Kiểm tra session ở mỗi request

Server cần kiểm tra session còn tồn tại, chưa hết hạn, chưa bị thu hồi và gắn với danh tính phù hợp. Quyền truy cập tài nguyên vẫn phải được kiểm tra riêng; có session hợp lệ không đồng nghĩa user được phép đọc mọi dữ liệu.

### 8.4 Hết hạn và thu hồi

Thường cần phân biệt:

- **Idle timeout:** phiên hết hạn sau một khoảng thời gian không có hoạt động hợp lệ.
- **Absolute timeout:** phiên hết hạn sau tổng thời gian tối đa kể từ khi tạo, kể cả có hoạt động liên tục.
- **Revocation:** server chủ động vô hiệu hóa phiên, ví dụ logout, đổi mật khẩu, phát hiện xâm nhập hoặc quản trị viên thu hồi.

Timeout phải được thực thi ở server. Cookie browser còn tồn tại không thể kéo dài một session đã hết hạn; ngược lại, xóa cookie phía client mà không thu hồi session server không đảm bảo session ID bị đánh cắp đã mất giá trị.

## 9. Đăng xuất đúng cách

Logout nên thực hiện theo thứ tự logic:

1. Xác minh request logout hợp lệ, có CSRF protection nếu dùng cookie tự gửi.
2. Vô hiệu hóa session/token ở server hoặc đưa nó vào danh sách thu hồi theo kiến trúc.
3. Trả response xóa cookie với cùng tên và phạm vi phù hợp (`Path`, `Domain`/host-only).
4. Frontend xóa dữ liệu UI tạm và chuyển về trạng thái chưa đăng nhập.
5. Các tab khác xử lý response `401`/`403` ở request tiếp theo và đồng bộ trạng thái giao diện nếu cần.

Ví dụ xóa cookie host-only:

```http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
```

Nếu cookie ban đầu có `Domain` hoặc `Path` khác, response xóa phải khớp phạm vi đó để browser loại đúng cookie. Nếu chỉ xóa một cookie ở browser mà session server vẫn hoạt động, bản sao session ID ở nơi khác có thể tiếp tục được sử dụng cho tới khi server hết hạn/thu hồi.

Logout nên là thao tác thay đổi trạng thái, không dùng GET đơn thuần. Bảo vệ CSRF cho logout cũng cần được cân nhắc vì kẻ tấn công có thể khiến người dùng bị đăng xuất ngoài ý muốn.

## 10. Browser session và quản lý nhiều tab

Nhiều tab có thể dùng chung một authentication session thông qua cookie, nhưng mỗi tab giữ state giao diện và `sessionStorage` riêng. Điều này tạo ra các trường hợp cần xử lý:

- Người dùng logout ở tab A; tab B vẫn hiển thị dữ liệu cũ cho tới khi gọi API hoặc nhận tín hiệu đồng bộ.
- Người dùng đổi mật khẩu hoặc bị thu hồi session; request tiếp theo từ tab đang mở cần nhận `401`/`403` và chuyển về trạng thái phù hợp.
- Một tab hết session trong khi tab khác còn form chưa gửi; ứng dụng cần bảo toàn nội dung người dùng theo cách an toàn và không gửi lại thao tác nhạy cảm một cách mù quáng.
- Hai tab cùng cập nhật session/token; thiết kế rotation cần tránh race condition khiến tab hợp lệ vô tình dùng ID đã bị thu hồi.

Có thể đồng bộ trạng thái UI giữa các tab bằng `BroadcastChannel`, `storage` event hoặc cơ chế server push. Nhưng thông báo từ tab khác chỉ là tín hiệu giao diện; **server vẫn là nguồn quyết định phiên có hợp lệ hay không**. Không tin một message client-side để cấp lại quyền.

## 11. Browser session và CORS

Khi frontend và API khác origin, cookie phiên có thể cần được gửi qua Fetch với:

```js
const response = await fetch("https://api.example.com/session", {
  credentials: "include",
});
```

API cần trả CORS response header phù hợp nếu JavaScript frontend phải đọc response:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Đồng thời cookie phải phù hợp với domain/path, `Secure`, `SameSite` và chính sách cookie của browser. CORS không tự gửi cookie và không tự tạo session. `credentials: "include"` cũng không bỏ qua quy tắc cookie.

Với credentialed response, không dùng `Access-Control-Allow-Origin: *`. Hãy allowlist origin cụ thể. Preflight thường không mang cookie session; server cần xử lý `OPTIONS` mà không yêu cầu phiên đăng nhập. Request thực tế vẫn phải được xác thực và phân quyền.

**Không nhầm cross-origin với cross-site:** `https://app.example.com` gọi `https://api.example.com` là cross-origin nhưng thường same-site. SOP/CORS vẫn áp dụng vì host khác nhau; SameSite cookie có thể phân loại request là same-site. Cấu hình cookie và CORS phải được kiểm tra độc lập.

## 12. XSS, CSRF và session security

Session là mục tiêu có giá trị cao vì nó đại diện cho danh tính người dùng. Các lỗi ở browser có thể tác động tới session theo những cách khác nhau.

| Mối đe dọa | Tác động tới session | Lớp phòng vệ liên quan |
| --- | --- | --- |
| XSS | Script cùng origin có thể dùng phiên để gọi API; nếu cookie không HttpOnly có thể đọc giá trị | Output encoding, DOM API an toàn, CSP, Trusted Types, HttpOnly |
| CSRF | Trang ngoài khiến browser gửi request có cookie phiên | SameSite, CSRF token, kiểm tra Origin/Referer, Fetch Metadata |
| Session fixation | Nạn nhân đăng nhập với ID mà kẻ tấn công biết | Tạo ID mới và rotate sau authentication/privilege change |
| Session hijacking | Kẻ tấn công sử dụng session ID bị lộ | HTTPS, Secure, HttpOnly, giảm lộ credential, rotation/revocation |
| Clickjacking | Người dùng bị lừa thao tác trong ứng dụng đã đăng nhập | CSP `frame-ancestors`, xác nhận thao tác nhạy cảm, CSRF protection |
| Token theft từ storage | XSS đọc token trong localStorage/sessionStorage | Tránh lưu credential có thể đọc khi không cần; giảm XSS; quản lý token ngắn hạn |

### 12.1 HttpOnly giảm lộ ID nhưng không ngăn hành động

Cookie `HttpOnly` không xuất hiện trong `document.cookie`, nhưng XSS vẫn có thể gọi endpoint cùng origin và browser gửi cookie. Vì vậy, không coi HttpOnly là biện pháp khắc phục XSS; nó chỉ giảm một đường đánh cắp credential.

### 12.2 SameSite không phải CSRF protection duy nhất

`SameSite=Lax` hoặc `Strict` có thể giảm việc gửi cookie trong ngữ cảnh cross-site. Tuy nhiên, subdomain khác origin nhưng cùng site có thể tạo request same-site. Nếu subdomain bị takeover hoặc chứa nội dung không tin cậy, cần CSRF token và kiểm tra nguồn request phù hợp.

### 12.3 Clickjacking có thể lợi dụng session đang hoạt động

Nếu ứng dụng cho phép nhúng trang nhạy cảm trong iframe, người dùng có thể bị dụ click lên giao diện đã đăng nhập. Dùng CSP `frame-ancestors` để giới hạn nơi được nhúng; có thể bổ sung `X-Frame-Options` cho tương thích cũ. Những thao tác quan trọng vẫn cần xác nhận và kiểm tra quyền ở server.

## 13. Các security header và cookie attribute hỗ trợ session

| Cơ chế | Vai trò trong bảo vệ phiên | Giới hạn |
| --- | --- | --- |
| `Set-Cookie: ...; HttpOnly` | Chặn script đọc cookie | Không ngăn session riding qua XSS |
| `Secure` | Chỉ gửi cookie qua HTTPS | Không tự bật HTTPS toàn site hoặc sửa TLS sai cấu hình |
| `SameSite` | Giảm gửi cookie trong nhiều request cross-site | Không ngăn mọi CSRF và không cô lập subdomain same-site |
| `__Host-` prefix | Buộc cookie host-only, Secure, Path=/ trong browser hỗ trợ | Không ngăn XSS trên chính host |
| HSTS | Yêu cầu browser dùng HTTPS theo chính sách đã lưu | Không thay `Secure` trên cookie; lần truy cập đầu cần cân nhắc preload/HTTPS |
| CSP | Hạn chế nguồn script và hành vi tải/thực thi nội dung | Không tự sửa mọi XSS; policy lỏng có thể mất tác dụng |
| Trusted Types | Giảm chuỗi không tin cậy đi vào một số DOM sink | Không tự sanitize dữ liệu; hỗ trợ tùy browser |
| CSP `frame-ancestors` | Giới hạn site được nhúng ứng dụng | Không ngăn phishing ngoài iframe hoặc thao tác được người dùng tự xác nhận |
| `Cache-Control: no-store` | Giảm lưu cache cho response nhạy cảm | Không xóa dữ liệu đã nằm trong memory/DOM hoặc ảnh chụp của người dùng |

Ví dụ response đăng nhập:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
```

Header CSP và các header khác cần được điều chỉnh theo tài nguyên và luồng nhúng thật. Không copy chính sách mẫu vào production mà chưa kiểm tra script, style, iframe, popup đăng nhập và tài nguyên bên thứ ba.

## 14. Những lỗi quản lý browser session thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đồng nhất session cookie với login session | Nghĩ đóng browser là server tự logout | Quản lý idle/absolute timeout và revocation phía server |
| Nghĩ đóng tab sẽ xóa cookie | Tab khác vẫn dùng chung cookie store | Hiểu cookie scope và quản lý logout tập trung |
| Chỉ xóa cookie khi logout | Session ID đã sao chép có thể còn hiệu lực | Thu hồi session phía server rồi xóa cookie |
| Dùng `sessionStorage` làm authentication | XSS có thể đọc; server không tự nhận dữ liệu storage | Dùng cơ chế xác thực server-side phù hợp |
| Lưu session ID trong localStorage | Script cùng origin có thể đọc/exfiltrate | Cân nhắc HttpOnly cookie và thiết kế CSRF phù hợp |
| Không rotate session sau login | Tăng rủi ro session fixation | Phát hành ID mới sau xác thực/nâng quyền |
| Cho rằng HttpOnly ngăn XSS sử dụng phiên | XSS vẫn gọi API với cookie tự gửi | Phòng vệ XSS và giảm quyền/session lifetime |
| Dựa vào SameSite để chống mọi CSRF | Subdomain cùng site vẫn có thể gửi request same-site | CSRF token và kiểm tra nguồn request |
| Chỉ dựa vào cookie expiry | Server session có thể còn sống hoặc đã bị thu hồi trước đó | Đồng bộ timeout và trạng thái ở server |
| Không xử lý nhiều tab sau logout | Tab khác vẫn hiển thị dữ liệu cũ | Xử lý 401/403, đồng bộ UI và kiểm tra server |

## 15. Thực hành kiểm chứng trong môi trường lab

Thực hiện trên ứng dụng local hoặc domain thử nghiệm mà bạn quản lý. Dùng tài khoản và dữ liệu giả; không đọc hoặc xuất cookie/session của người dùng thật.

### Bài thử A — Session cookie và persistent cookie

Tạo hai cookie lab từ server:

```http
Set-Cookie: browser_session=lab-a; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: persistent_lab=lab-b; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600
```

Trong DevTools → Application/Storage → Cookies, quan sát thuộc tính Expires/Max-Age. Đóng một tab rồi mở lại cùng website; tiếp tục kiểm tra cookie. Nếu muốn thử kết thúc browser session, hãy dùng profile lab và ghi nhận hành vi restore session của browser.

**Kỳ vọng:** Đóng tab đơn lẻ không đồng nghĩa xóa session cookie. Hành vi sau khi đóng browser phụ thuộc cách browser kết thúc/khôi phục session. Persistent cookie có thời hạn được khai báo rõ.

### Bài thử B — `sessionStorage` giữa hai tab

Trong Console của tab A:

```js
sessionStorage.setItem("lab-step", "A");
localStorage.setItem("lab-shared", "shared");
```

Mở tab B cùng origin bằng thao tác mở tab độc lập. Đọc hai storage trong tab B, sau đó sửa từng giá trị và quay lại tab A.

**Kỳ vọng:** `sessionStorage` của hai top-level browsing context độc lập; `localStorage` cùng origin được chia sẻ trong storage partition tương ứng. Nếu tab B được mở bằng `window.open` có opener, kiểm tra hành vi khởi tạo/copy sessionStorage riêng theo browser; sau đó các vùng lưu trữ không đồng bộ thay đổi với nhau.

### Bài thử C — HttpOnly cookie vẫn được gửi

Đăng nhập tài khoản lab và để server cấp cookie HttpOnly. Chạy:

```js
console.log(document.cookie);
const response = await fetch("/api/session-info");
console.log(response.status, await response.json());
```

Quan sát Network và log server. Không ghi giá trị cookie thô vào log.

**Kỳ vọng:** Cookie không xuất hiện trong `document.cookie`, nhưng browser gửi nó tới endpoint phù hợp và server nhận diện session.

### Bài thử D — Logout và thu hồi session

1. Đăng nhập trên hai tab cùng profile.
2. Logout ở tab A qua endpoint được bảo vệ CSRF.
3. Gọi endpoint yêu cầu đăng nhập ở tab B.
4. Kiểm tra cookie đã được xóa đúng scope và server session đã bị thu hồi.

**Kỳ vọng:** Request tiếp theo từ tab B không còn được chấp nhận với session đã thu hồi, dù tab B vẫn còn dữ liệu giao diện cũ. Ứng dụng cần xử lý `401` và chuyển UI về trạng thái chưa đăng nhập.

### Bài thử E — Timeout phía server

Trong môi trường lab, đặt idle timeout ngắn và absolute timeout dài hơn. Đăng nhập, gửi request để làm mới hoạt động hợp lệ, rồi để phiên không hoạt động. Sau đó thử gọi API trước và sau thời điểm hết hạn.

**Kỳ vọng:** Server từ chối phiên sau idle timeout dù cookie còn trong browser. Kiểm tra riêng absolute timeout để xác nhận hoạt động liên tục không kéo dài phiên vượt giới hạn tối đa.

## 16. Quy trình kiểm tra session bằng DevTools

Khi debug phiên đăng nhập, nên kiểm tra theo trình tự:

1. **Network → response đăng nhập:** xác nhận `Set-Cookie` có đúng tên, `HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain`/host-only và thời hạn.
2. **Application/Storage → Cookies:** kiểm tra cookie được browser lưu hay bị từ chối; xem cảnh báo về SameSite, Secure hoặc third-party cookie.
3. **Network → request tiếp theo:** xác minh cookie có được gửi tới đúng host/path và request có đúng credentials mode.
4. **Server log/session store:** xác minh session record còn hoạt động, chưa bị thu hồi và gắn đúng user; tránh log session ID thô.
5. **Response status:** phân biệt `401` (chưa xác thực/phiên không hợp lệ) và `403` (đã xác thực nhưng không được phép theo policy), tùy quy ước API.
6. **Nhiều tab:** thử logout, hết hạn hoặc đổi quyền ở một tab rồi gọi API từ tab khác.
7. **CORS:** nếu frontend/API khác origin, kiểm tra `credentials`, cookie policy và CORS response header riêng biệt.

Không chia sẻ ảnh chụp DevTools chứa cookie, Authorization header hoặc dữ liệu cá nhân. Khi cần báo lỗi, che các giá trị credential trước khi gửi log.

## 17. Checklist thiết kế browser session

- [ ] Phân biệt rõ browser session, session cookie, authentication session và `sessionStorage` trong tài liệu/thiết kế.
- [ ] Session ID đủ ngẫu nhiên, opaque, không chứa thông tin cá nhân hoặc quyền có thể đoán.
- [ ] Cookie xác thực dùng `HttpOnly`, `Secure`, `SameSite` phù hợp.
- [ ] Giới hạn cookie theo host/path; cân nhắc host-only và `__Host-`.
- [ ] Không lưu credential nhạy cảm vào `localStorage`/`sessionStorage` nếu không có lý do và phân tích rủi ro.
- [ ] Rotate session ID sau login, nâng quyền và sự kiện xác thực quan trọng.
- [ ] Server thực thi idle timeout, absolute timeout và revocation.
- [ ] Logout vô hiệu hóa server session và xóa cookie đúng scope.
- [ ] Endpoint thay đổi trạng thái có CSRF protection; không dựa riêng vào HttpOnly/SameSite.
- [ ] Phòng vệ XSS bằng encoding, DOM API an toàn, CSP và Trusted Types khi phù hợp.
- [ ] API kiểm tra authorization trên từng tài nguyên và hành động.
- [ ] Response chứa dữ liệu nhạy cảm có cache policy phù hợp.
- [ ] Xử lý nhiều tab và response 401/403 sau logout/timeout.
- [ ] Kiểm thử browser thực tế, bao gồm profile riêng tư và chính sách cookie bên thứ ba nếu ứng dụng phụ thuộc chúng.

## 18. Câu hỏi tự kiểm tra

1. Browser session, session cookie và authentication session khác nhau thế nào?
2. Vì sao đóng một tab không đồng nghĩa người dùng đã logout?
3. Nếu cookie hết hạn ở browser nhưng session record còn ở server, điều gì xảy ra? Ngược lại thì sao?
4. `sessionStorage` được phân vùng theo những yếu tố nào? Vì sao nó không phù hợp để làm session xác thực server-side?
5. Cookie HttpOnly không đọc được bằng JavaScript nhưng vẫn được gửi tới API như thế nào?
6. Vì sao cần rotate session ID sau đăng nhập để giảm session fixation?
7. Logout đúng cách cần làm gì ở server và browser?
8. CORS, SameSite, HttpOnly và Secure bảo vệ những ranh giới khác nhau nào?
9. XSS vẫn có thể làm gì khi session cookie đã có HttpOnly?
10. Làm thế nào để một tab khác nhận biết session đã bị thu hồi mà không tự cấp quyền dựa trên thông điệp client-side?

## 19. Ghi nhớ

**Browser session, session cookie và authentication session là ba khái niệm khác nhau.** Browser quản lý cookie và storage theo những ranh giới riêng; server quản lý danh tính, thời hạn và quyền của phiên đăng nhập. Session cookie không có `Expires`/`Max-Age` thường gắn với phiên duyệt, nhưng hành vi khôi phục browser có thể ảnh hưởng việc lưu lại cookie. Nó không thay thế idle timeout, absolute timeout hoặc thu hồi session ở server.

Với ứng dụng web, hãy dùng cookie xác thực có `HttpOnly`, `Secure`, `SameSite` phù hợp; giới hạn phạm vi cookie; rotate và thu hồi session đúng lúc; bảo vệ CSRF; phòng vệ XSS; và xác minh quyền trên mỗi request. **Browser lưu và gửi credential; server quyết định phiên còn hợp lệ và người dùng được phép làm gì.**
