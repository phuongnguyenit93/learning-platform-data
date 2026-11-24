# Browser và server khác nhau thế nào?

Trong một ứng dụng web, **browser (trình duyệt)** và **server (máy chủ)** cùng tham gia xử lý yêu cầu của người dùng nhưng có **vị trí thực thi, quyền hạn, dữ liệu và trách nhiệm bảo mật khác nhau**. Browser chạy trên thiết bị người dùng, hiển thị giao diện và thực thi mã phía client. Server nhận request, xử lý nghiệp vụ, truy cập dữ liệu và quyết định một thao tác có được phép hay không.

Đây là nội dung nền tảng của chương **Bức tranh tổng thể** trong học phần **Browser Security** (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`). Phân biệt hai môi trường sẽ giúp hiểu vì sao trình duyệt cần **Same-Origin Policy (SOP)** và **CORS**, cookie được gửi theo quy tắc nào, và vì sao các phòng vệ **XSS, CSRF, clickjacking, CSP, Trusted Types, security headers** đòi hỏi sự phối hợp giữa client và server.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả vai trò của browser và server trong một lần tải trang và một lần gọi API.
2. Giải thích vì sao mã JavaScript ở browser không có cùng quyền với mã chạy trên server.
3. Phân biệt **origin**, **site**, cookie và phiên đăng nhập ở hai phía.
4. Giải thích bên nào **cấu hình**, bên nào **thực thi** SOP, CORS, CSP và một số security headers.
5. Đặt đúng biện pháp phòng vệ XSS, CSRF, clickjacking ở browser, server hoặc cả hai.
6. Dùng DevTools để chứng minh request có thể đến server nhưng response bị browser chặn đọc vì CORS.

## 2. Nhìn từ một request thực tế

Khi người dùng mở `https://shop.example.com/orders`, browser thường thực hiện các bước sau:

1. Phân giải tên miền, thiết lập kết nối bảo mật và gửi **HTTP request** đến nơi phục vụ ứng dụng.
2. Server, reverse proxy hoặc CDN trả **HTTP response** gồm status, headers và nội dung HTML/tài nguyên.
3. Browser phân tích HTML/CSS, tải tài nguyên cần thiết, dựng giao diện và chạy JavaScript được phép.
4. Khi người dùng tương tác, JavaScript có thể gọi API để lấy/cập nhật dữ liệu. Server xác thực, kiểm tra quyền, thực hiện nghiệp vụ và trả response.
5. Browser tiếp tục áp dụng quy tắc an toàn trước khi cho mã JavaScript đọc response hoặc thao tác với DOM, cookie và tài nguyên.

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant S as Web server
    participant A as API / nghiệp vụ
    participant D as Cơ sở dữ liệu
    U->>B: Mở /orders
    B->>S: GET /orders
    S-->>B: HTML + security headers
    B->>B: Render HTML; áp dụng CSP và chính sách browser
    U->>B: Chọn xem đơn hàng
    B->>A: GET /api/orders + cookie hợp lệ (nếu có)
    A->>A: Xác thực + kiểm tra quyền
    A->>D: Đọc đơn hàng được phép
    D-->>A: Dữ liệu
    A-->>B: JSON + HTTP headers
    B->>B: Kiểm tra quyền đọc response theo origin/CORS
    B-->>U: Hiển thị kết quả
```

Sơ đồ thể hiện trách nhiệm logic. Trong triển khai thực tế, **web server và API có thể là cùng một chương trình**, nhiều dịch vụ khác nhau hoặc chạy phía sau CDN/reverse proxy. Browser vẫn là môi trường ở phía người dùng, còn quyết định nghiệp vụ cần được bảo vệ tại server.

### So sánh nhanh

| Khía cạnh | Browser (client) | Server (backend) |
| --- | --- | --- |
| Nơi chạy | Thiết bị người dùng, trong môi trường trình duyệt | Máy chủ, container, dịch vụ cloud hoặc runtime backend |
| Mục tiêu chính | Hiển thị UI, nhận tương tác, gọi API | Xử lý nghiệp vụ, lưu/truy xuất dữ liệu, kiểm soát truy cập |
| Mã thường gặp | JavaScript/TypeScript sau khi build, HTML, CSS, Web APIs | Java, Node.js, Go, Python, C#, SQL và các dịch vụ liên quan |
| Dữ liệu có thể tiếp cận | DOM, dữ liệu công khai hoặc dữ liệu đã cấp cho phiên, một số storage/cookie theo chính sách | Dữ liệu được cấp quyền từ database, bộ nhớ dịch vụ, secrets và hạ tầng nội bộ |
| Khả năng người dùng can thiệp | Có thể xem và sửa mã client, sửa DOM, tạo request tùy ý | Người dùng từ xa không mặc nhiên sửa được mã server; server vẫn có thể bị tấn công |
| Quy tắc đọc dữ liệu xuyên origin | Bị browser ràng buộc bởi SOP/CORS và các chính sách liên quan | HTTP client phía server thường không bị browser SOP/CORS; vẫn chịu DNS, mạng, firewall và chính sách nội bộ |
| Xác thực/phân quyền | Có thể hiển thị trạng thái đăng nhập và ẩn/hiện nút theo quyền | **Phải** xác minh danh tính và quyền cho từng thao tác nhạy cảm |
| Xử lý cookie | Lưu và tự gửi cookie khi thỏa thuộc tính/chính sách; giới hạn JavaScript theo `HttpOnly` | Phát `Set-Cookie`, kiểm tra session/token được gửi lên, hủy/đổi phiên khi cần |
| Kiểm soát an toàn | Thực thi SOP, CSP, framing policy, chính sách cookie, cảnh báo HTTPS | Thiết kế authorization, validation, CSRF defense, trả security headers, bảo vệ dữ liệu |

Điều quan trọng nhất: **mã phía browser không phải ranh giới đáng tin cậy để bảo vệ dữ liệu hoặc quyền nghiệp vụ**. Người dùng hoặc công cụ HTTP có thể gửi request mà không dùng chính UI đã lập trình.

## 3. Vì sao browser và server có mức tin cậy khác nhau?

Một giao diện có thể ẩn nút “Xóa tài khoản” với người chưa đăng nhập:

```js
// Client: chỉ điều khiển trải nghiệm giao diện.
if (currentUser?.canDeleteAccount) {
  deleteButton.hidden = false;
}
```

Điều kiện trên hữu ích cho trải nghiệm, nhưng **không chặn được** một người tự tạo request `DELETE /api/account` từ DevTools hoặc công cụ HTTP. Server phải kiểm tra quyền dựa trên **danh tính và dữ liệu đáng tin cậy ở server**, ví dụ:

```js
// Pseudocode phía server: kiểm tra lại quyền ở nơi thực thi hành động.
const user = await authenticate(request);
if (!user || !user.permissions.includes('account:delete')) {
  return respond(403, { error: 'Forbidden' });
}
await deleteAccountOwnedBy(user.id, request.params.accountId);
```

Ví dụ chỉ minh họa nguyên tắc. Một ứng dụng thật phải xử lý cả quyền sở hữu tài nguyên, tính hợp lệ của request, CSRF (nếu xác thực dựa vào cookie), ghi log và các tình huống lỗi.

### Dữ liệu nào không nên đặt ở browser?

Đừng gửi xuống client những bí mật không cần thiết cho chức năng, như mật khẩu database, khóa ký JWT, private API key hoặc thông tin người dùng khác mà phiên hiện tại không có quyền xem. Mã JavaScript, source map, dữ liệu trong HTML, response API và nhiều giá trị storage ở client đều có thể bị người dùng quan sát hoặc sửa.

Ngay cả khi một giá trị không đọc được bằng JavaScript vì `HttpOnly`, người dùng sở hữu trình duyệt vẫn kiểm soát thiết bị và phiên của họ. `HttpOnly` là hàng rào chống một lớp truy cập từ script, **không phải cách giữ bí mật server trước chính người dùng**.

### Browser có nhiệm vụ bảo vệ người dùng khỏi các nguồn web khác nhau

Một browser có thể cùng lúc mở ngân hàng, mạng xã hội và website lạ. Nó cần ngăn script từ website lạ đọc DOM, storage hoặc response riêng của ngân hàng. Đây là mục tiêu của **Same-Origin Policy** và các cơ chế cách ly. Server không vận hành bên trong hộp an toàn của browser; nếu server chủ động gửi HTTP request đến địa chỉ khác, chính ứng dụng server phải kiểm soát đích đến và quyền truy cập đó.

## 4. Origin, site và cookie: ranh giới nằm ở đâu?

### 4.1. Origin là gì?

Một **origin** gồm **scheme + host + port**. Ví dụ:

```text
https://app.example.com:443/profile
  │      │               │
  │      │               └── Port 443 (mặc định của HTTPS)
  │      └────────────────── Host app.example.com
  └───────────────────────── Scheme https

Origin = https://app.example.com
```

Đường dẫn `/profile` không làm đổi origin. Một **site** trong quy tắc *schemeful same-site* thường kết hợp scheme với tên miền có thể đăng ký (*registrable domain*, dựa vào Public Suffix List). Vì vậy **cùng site có thể vẫn khác origin**.

Giả sử trang chính ở `https://app.example.com`:

| Địa chỉ | Cùng origin? | Cùng site? | Giải thích |
| --- | :---: | :---: | --- |
| `https://app.example.com/profile` | Có | Có | Chỉ khác path |
| `https://api.example.com/data` | Không | Có | Khác subdomain, cùng scheme và registrable domain |
| `https://app.example.com:8443` | Không | Có | Khác port |
| `http://app.example.com` | Không | Không | Khác scheme; site hiện đại xét scheme |
| `https://another.example.net` | Không | Không | Khác tên miền đăng ký |

Đây là các URL HTTPS/HTTP thông thường; `file:`, iframe sandbox và tài liệu có *opaque origin* có quy tắc đặc biệt. Trong browser, có thể kiểm tra origin hiện tại bằng `location.origin`.

### 4.2. Browser làm gì với Same-Origin Policy?

**SOP** giới hạn việc JavaScript từ một origin đọc hoặc sửa nội dung riêng của origin khác. Ví dụ, `https://evil.example.net` không được tự do đọc DOM trong iframe của `https://bank.example.com` hay đọc response API của ngân hàng nếu không có cơ chế cho phép phù hợp.

SOP **không chặn tuyệt đối mọi request xuyên origin**. Một trang có thể điều hướng, tải một số loại tài nguyên, nhúng ảnh và gửi nhiều dạng request. Sự phân biệt giữa **gửi request** và **đọc response** giải thích vì sao chỉ có SOP/CORS chưa đủ để chống CSRF.

### 4.3. Cookie thuộc trách nhiệm của ai?

Server có thể trả:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
```

Browser nhận cookie và quyết định khi nào được lưu, gửi lại theo `Domain`/host, `Path`, `Secure`, `SameSite` và các chính sách riêng. Server nhận giá trị cookie trong request, tra phiên và quyết định phiên đó có hợp lệ, còn hạn và được phép làm gì hay không.

| Thuộc tính | Browser áp dụng | Server phải quan tâm |
| --- | --- | --- |
| `Secure` | Giới hạn gửi qua kết nối an toàn | Triển khai HTTPS, cấu hình cookie cho môi trường production |
| `HttpOnly` | Không cho JavaScript truy cập cookie qua `document.cookie` | Vẫn phải phòng XSS vì script độc hại có thể gọi hành động với phiên hiện tại |
| `SameSite=Lax/Strict/None` | Điều chỉnh gửi cookie theo ngữ cảnh same-site/cross-site | Chọn theo luồng sản phẩm; không xem là thay thế đầy đủ cho CSRF defense |
| `Path` và `Domain` | Giới hạn phạm vi gửi cookie | Không coi `Path` là biên giới phân quyền giữa các ứng dụng |
| `__Host-` | Ở browser hỗ trợ, đòi hỏi `Secure`, `Path=/` và không có `Domain` | Tạo host-only cookie với cấu hình giảm rủi ro chia sẻ ngoài ý muốn |

Trong ví dụ trên, `opaque-session-id` phải là giá trị phiên đủ khó đoán; không nên dùng trực tiếp số thứ tự người dùng. Server quản lý phiên an toàn, thu hồi khi đăng xuất và cân nhắc xoay vòng sau các sự kiện xác thực quan trọng.

**Cần tránh hai ngộ nhận:**

- Cookie không hoàn toàn tuân theo origin như DOM hoặc `localStorage`. Hai origin khác nhau có thể cùng nhận một cookie tùy cấu hình domain, path và chính sách trình duyệt.
- `SameSite` so sánh **site**, còn CORS và SOP chủ yếu so sánh **origin**. `https://app.example.com` và `https://api.example.com` có thể cùng site nhưng vẫn cần CORS khi JavaScript ở app muốn đọc response API.

## 5. Browser `fetch()` khác server `fetch()` như thế nào?

Lấy ví dụ frontend ở `https://app.example.com` và API ở `https://api.example.com`.

### 5.1. Gọi API bằng JavaScript trong browser

```js
const response = await fetch('https://api.example.com/orders');
const orders = await response.json();
```

Hai host khác nhau tạo hai origin khác nhau. Browser sẽ áp dụng **CORS** đối với yêu cầu script đọc response. API cần trả header cho phép origin tương ứng, chẳng hạn:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Với request CORS đơn giản, request thực tế có thể đã tới API trước khi browser phát hiện response không có header cho phép và từ chối chuyển body cho JavaScript. Request dùng method/headers không thuộc nhóm được phép gửi trực tiếp thường cần một yêu cầu **preflight `OPTIONS`** trước.

Nếu API cần xác thực bằng cookie ở request xuyên origin, mã client có thể cần:

```js
const response = await fetch('https://api.example.com/me', {
  credentials: 'include',
});
```

Khi dùng credentials, API phải cấu hình `Access-Control-Allow-Credentials: true` và `Access-Control-Allow-Origin` với **origin cụ thể**; không dùng `*` để cho JavaScript đọc response có credentials. Cookie vẫn chỉ được gửi khi thỏa quy tắc cookie và chính sách trình duyệt. Tùy browser và ngữ cảnh, chính sách chặn cookie bên thứ ba cũng có thể ảnh hưởng.

### 5.2. Gọi API từ server

Một backend Node.js có thể gọi:

```js
// Ví dụ chạy ở Node.js 18+ (có fetch).
const response = await fetch('https://api.example.com/orders', {
  headers: { Authorization: `Bearer ${serviceToken}` },
});
const orders = await response.json();
```

HTTP client phía server thông thường **không bị browser SOP/CORS ràng buộc**. Nó có thể đọc response ngay cả khi API không gửi `Access-Control-Allow-Origin`, miễn mạng và server đích cho phép kết nối, và có quyền truy cập hợp lệ.

Tuy nhiên, server cần quản lý **xác thực dịch vụ**, thời hạn timeout, hạn mức, kiểm tra TLS và bảo vệ trước **SSRF** (*Server-Side Request Forgery*). Không nên xây dựng proxy nhận một URL bất kỳ từ client rồi fetch URL đó, vì có thể mở đường truy cập tới metadata service hoặc mạng nội bộ của server.

### 5.3. Bảng phân biệt các trường hợp thường gặp

| Trường hợp | Browser áp dụng SOP/CORS? | Server API vẫn cần kiểm tra quyền? |
| --- | --- | --- |
| `fetch('/api/orders')` cùng origin | Không cần CORS | **Có** |
| Browser `fetch('https://api.example.com/orders')` | Có, khi đọc response xuyên origin | **Có** |
| Browser gửi form HTML sang origin khác | Chính sách trình duyệt có giới hạn khác nhau; không thể coi CORS là hàng rào chặn mọi gửi request | **Có**, kèm CSRF defense khi phù hợp |
| Backend gọi API từ backend | HTTP client không chịu browser SOP/CORS | **Có** |
| `curl` hoặc công cụ HTTP gọi API | Không chịu browser SOP/CORS | **Có** |

**CORS không phải cơ chế authentication/authorization.** Cho phép một origin đọc response không có nghĩa người dùng của origin đó được xem dữ liệu của tất cả tài khoản. Ngược lại, chặn CORS không có nghĩa endpoint đã được bảo vệ khỏi `curl` hoặc các client khác.

## 6. Cơ chế phòng vệ: bên nào làm phần nào?

Browser là nơi **thi hành** nhiều quy tắc bảo vệ nguồn web; server là nơi **trả chính sách và kiểm soát nghiệp vụ**. Một số cơ chế yêu cầu cả hai phối hợp.

| Nguy cơ hoặc cơ chế | Vai trò của browser | Vai trò của server và ứng dụng |
| --- | --- | --- |
| **XSS** — mã độc được đưa vào trang | Thực thi hoặc chặn script tùy DOM sink, CSP, Trusted Types và ngữ cảnh | Escape đầu ra đúng ngữ cảnh, sanitize HTML nếu cần, tránh sinh script từ dữ liệu người dùng, cấu hình CSP |
| **CSRF** — request thay đổi trạng thái ngoài ý muốn | Gửi cookie theo chính sách cookie; có thể hạn chế bằng `SameSite` | Kiểm tra CSRF token hoặc cơ chế tương đương, `Origin`/Fetch Metadata khi phù hợp; cấm tác động trạng thái qua GET |
| **Clickjacking** — UI thật bị lồng trong trang đánh lừa | Chặn nhúng khi chính sách framing không cho phép | Trả CSP `frame-ancestors` hoặc `X-Frame-Options` phù hợp |
| **CORS** | Kiểm tra yêu cầu/response trước khi cho JavaScript đọc | Chỉ định các origin, method, header và chế độ credentials được phép |
| **Trusted Types** | Ở browser hỗ trợ, hạn chế một số DOM sink nhận chuỗi nguy hiểm | Dùng Trusted Types policies được thiết kế và kiểm tra đúng; không thay việc sanitize/escape |
| **HTTPS/HSTS** | Kiểm tra TLS, cảnh báo kết nối và áp dụng HSTS đã nhận | Cung cấp HTTPS đúng cấu hình, gửi HSTS khi phù hợp |
| **Phân quyền tài nguyên** | Có thể ẩn/hiện UI theo quyền mà API công bố | **Bắt buộc** xác minh quyền thực tế trên từng request, từng tài nguyên |

### 6.1. XSS — cả browser và server đều có việc phải làm

Giả sử frontend đưa dữ liệu query chưa tin cậy trực tiếp vào HTML:

```js
const keyword = new URLSearchParams(location.search).get('q') ?? '';

// Không an toàn: chuỗi đầu vào được phân tích như HTML.
document.querySelector('#keyword').innerHTML = keyword;

// Phù hợp nếu chỉ muốn hiển thị văn bản:
document.querySelector('#keyword').textContent = keyword;
```

Browser có thể thực thi nội dung dưới dạng HTML/JavaScript nếu ứng dụng đặt dữ liệu vào sink nguy hiểm. Server có thể đã trả HTML chứa giá trị không được escape, hoặc lỗi xảy ra hoàn toàn trong DOM phía client. Cách sửa phụ thuộc đúng **ngữ cảnh đầu ra**. Khi cần hiển thị HTML do người dùng cung cấp, phải có sanitizer phù hợp và được duy trì an toàn.

Server thường phát header **Content Security Policy (CSP)**, còn browser thực thi chính sách:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Đây là **ví dụ chính sách**, không phải cấu hình sao chép cho mọi ứng dụng: script inline trong trang sẽ bị chính sách `script-src 'self'` ngăn trừ khi dùng cơ chế phù hợp, ví dụ nonce/hash. Với mã thực tế có thể dùng CSP nonce ngẫu nhiên theo mỗi response, kiểm tra tác động lên script/framework và triển khai dần bằng `Content-Security-Policy-Report-Only`.

**Trusted Types** bổ sung lớp kiểm soát cho một số DOM sink như `innerHTML`, khi trình duyệt hỗ trợ và ứng dụng bật thực thi bằng CSP (ví dụ `require-trusted-types-for 'script'`). Trusted Types không tự làm sạch HTML độc hại; ứng dụng vẫn phải tạo chính sách chuyển đổi đầu vào an toàn.

### 6.2. CSRF — browser có thể gửi cookie, server phải xác nhận ý định

Nếu người dùng đang đăng nhập bằng session cookie, một trang khác có thể tìm cách làm trình duyệt gửi request tới ứng dụng. Việc browser không cho trang đó đọc response **không đảm bảo** request thay đổi dữ liệu chưa được xử lý.

Server cần bảo vệ các thao tác nhạy cảm: dùng token chống CSRF hoặc cách bảo vệ tương đương phù hợp kiến trúc; xác minh `Origin` và/hoặc Fetch Metadata khi phù hợp; cấu hình `SameSite` cho cookie; không làm thay đổi trạng thái bằng `GET`. `Origin` hữu ích trong ngữ cảnh browser nhưng không phải bằng chứng định danh đáng tin cậy cho mọi loại client HTTP.

**CORS không thay thế CSRF defense.** Điều này quan trọng cả trong hệ thống nhiều subdomain: hai subdomain có thể cùng *site* nhưng khác *origin*, nên `SameSite` một mình không khẳng định thao tác đến từ đúng ứng dụng được cho phép.

### 6.3. Clickjacking — server nói ai được nhúng, browser thi hành

Nếu trang thanh toán không được nhúng trong iframe, server có thể trả:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Browser tuân theo chính sách và từ chối nhúng tài liệu trong các ngữ cảnh bị cấm. `frame-ancestors` được gửi dưới dạng **HTTP response header**; không hoạt động khi chỉ đặt trong thẻ `<meta>`. Nếu sản phẩm thật cần iframe từ đối tác, hãy thiết kế allowlist cho đúng đối tác thay vì chặn mọi embedding.

### 6.4. Một số security headers khác

| HTTP response header | Ý nghĩa ở phía browser | Điều cần cân nhắc khi server cấu hình |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Hạn chế suy đoán MIME nguy hiểm ở một số ngữ cảnh | Vẫn phải trả `Content-Type` đúng |
| `Strict-Transport-Security` | Ghi nhớ yêu cầu sử dụng HTTPS cho host trong thời hạn chính sách | Chỉ cấu hình trên HTTPS, cân nhắc `includeSubDomains` |
| `Referrer-Policy` | Giới hạn URL/referrer được gửi khi điều hướng hoặc tải tài nguyên | Chọn mức bảo mật phù hợp analytics/liên kết |
| `Permissions-Policy` | Giới hạn tính năng của tài liệu/iframe như camera hoặc micro | Kiểm tra tính năng nào ứng dụng thực sự dùng |
| `Cross-Origin-Opener-Policy` (COOP) | Điều chỉnh quan hệ giữa các browsing context | Kiểm thử popup, đăng nhập liên kết và tích hợp |
| `Cross-Origin-Embedder-Policy` (COEP) | Yêu cầu tài nguyên nhúng đáp ứng chính sách phù hợp | Kiểm thử CDN và tài nguyên bên thứ ba |
| `Cross-Origin-Resource-Policy` (CORP) | Chủ tài nguyên giới hạn việc nhúng tài nguyên trong một số request mode | Không dùng thay CORS khi JavaScript cần đọc dữ liệu |

COOP và COEP có thể phối hợp để tạo **cross-origin isolation** cho những tính năng web cần mức cách ly cao. Server cần hiểu tác động lên các tài nguyên được nhúng; browser là nơi thực thi kiểm soát đó.

## 7. Server-Side Rendering có làm mất ranh giới không?

Không. Cách render giao diện thay đổi nơi tạo HTML, nhưng không xóa ranh giới client/server:

| Kiến trúc | Browser nhận gì? | Server xử lý gì? | Điểm bảo mật cốt lõi |
| --- | --- | --- | --- |
| **SSR** (*Server-Side Rendering*) | HTML đã dựng ở server, có thể thêm JavaScript để tương tác | Tạo HTML, có thể đọc dữ liệu server trước khi trả response | Escape HTML đúng ngữ cảnh; không vô tình nhúng secret vào HTML/initial state |
| **CSR/SPA** (*Client-Side Rendering*) | HTML khởi tạo và bundle JavaScript; client gọi API và dựng UI | API, xác thực, nghiệp vụ, lưu trữ | Phân quyền tại API; chống DOM XSS |
| **Hybrid** | Kết hợp HTML dựng sẵn và phần tương tác động | Render một số phần và phục vụ API | Giữ đúng giới hạn dữ liệu/đặc quyền ở từng phía |

Một component có thể được render ở server rồi *hydrate* ở browser. Đừng suy luận “code chạy ở server trong một bước” nghĩa là mọi giá trị mà component xuất ra đều bí mật: HTML hoặc dữ liệu serialized gửi xuống browser sẽ có thể được quan sát.

## 8. Thực hành: cùng một API, browser bị CORS chặn nhưng server đọc được

Bài thực hành dùng **Node.js 18 trở lên**, không cần thư viện ngoài. Hai chương trình hoạt động trên hai origin:

- `http://localhost:3000`: ứng dụng web, phục vụ HTML và một endpoint server `/proxy`.
- `http://localhost:3001`: API trả JSON, ban đầu **không** trả header CORS.

Vì **port là một phần của origin**, `localhost:3000` và `localhost:3001` khác origin dù cùng máy.

### Bước 1 — Tạo API

Tạo file `api.mjs` trong một thư mục thử nghiệm riêng:

```js
import { createServer } from 'node:http';

const allowCors = false; // Đổi thành true cho lần thử sau.

createServer((req, res) => {
  console.log('[API]', req.method, req.url, 'Origin:', req.headers.origin);
  if (req.url !== '/data') {
    res.writeHead(404).end('Not found');
    return;
  }

  if (allowCors) {
    res.setHeader('Access-Control-Allow-Origin', 'http://localhost:3000');
  }
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify({ source: 'API port 3001', message: 'Đã trả dữ liệu' }));
}).listen(3001, () => console.log('API: http://localhost:3001'));
```

### Bước 2 — Tạo ứng dụng web và đường gọi từ server

Tạo file `app.mjs` cùng thư mục:

```js
import { createServer } from 'node:http';

createServer(async (req, res) => {
  if (req.url === '/proxy') {
    // URL đích cố định chỉ để demo sự khác nhau giữa server và browser.
    try {
      const apiResponse = await fetch('http://localhost:3001/data');
      const payload = await apiResponse.text();
      res.writeHead(apiResponse.status, {
        'Content-Type': 'application/json; charset=utf-8',
      });
      res.end(payload);
    } catch {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'API unavailable' }));
    }
    return;
  }

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(`<!doctype html>
    <html lang="vi">
      <head><meta charset="utf-8"><title>Browser vs Server</title></head>
      <body>
        <h1>Browser và server gọi cùng một API</h1>
        <pre id="results">Đang kiểm tra...</pre>
        <script>
          async function check(label, url) {
            try {
              const response = await fetch(url);
              const data = await response.json();
              return label + ': ' + JSON.stringify(data);
            } catch (error) {
              return label + ': lỗi ' + error.message;
            }
          }
          Promise.all([
            check('Browser → API 3001', 'http://localhost:3001/data'),
            check('Browser → app 3000 → API 3001', '/proxy'),
          ]).then(lines => {
            document.getElementById('results').textContent = lines.join('\\n');
          });
        </script>
      </body>
    </html>`);
}).listen(3000, () => console.log('App: http://localhost:3000'));
```

Mã `app.mjs` dùng template string ở phía Node.js để tạo HTML. Đoạn `<script>` nằm trong HTML **sẽ chạy ở browser sau khi nhận response**, trong khi `fetch()` ở nhánh `/proxy` **chạy tại server Node.js**. Đây chính là khác biệt muốn quan sát.

### Bước 3 — Chạy và xem kết quả

Mở hai terminal trong thư mục vừa tạo:

```bash
node api.mjs
```

```bash
node app.mjs
```

Mở `http://localhost:3000`, sau đó nhấn **F12 → Console và Network**:

| Luồng gọi | Kết quả khi `allowCors = false` | Nguyên nhân |
| --- | --- | --- |
| Browser gọi thẳng `http://localhost:3001/data` | JavaScript nhận lỗi CORS/Failed to fetch | Browser không được đọc response xuyên origin vì API không cho phép |
| Browser gọi `/proxy` ở `localhost:3000`; Node server gọi API `3001` | JavaScript hiển thị JSON | Browser đọc response **cùng origin** từ `3000`; Node server đọc API `3001` mà không chịu browser CORS |

Trong terminal API, bạn sẽ thấy request gửi đến `/data` cho cả hai luồng. Request do browser trực tiếp gửi thường có header `Origin: http://localhost:3000`; request do `fetch()` của Node gửi không nhất thiết có header đó. **Đừng dùng việc thiếu `Origin` làm bằng chứng rằng request là an toàn hoặc đã xác thực.**

### Bước 4 — Bật CORS và thử lại

Đổi `allowCors` trong `api.mjs` thành `true`, khởi động lại API và tải lại trang. Lúc này cả hai luồng đều đọc được JSON. Trong Network, chọn request tới `localhost:3001/data` để xem:

```http
Origin: http://localhost:3000
```

ở **Request Headers** và:

```http
Access-Control-Allow-Origin: http://localhost:3000
```

ở **Response Headers**. Đây là bằng chứng API công bố quyền đọc cho origin cụ thể, và browser thực thi quyền đó.

### Bước 5 — Kiểm tra bằng HTTP client ngoài browser

Giữ `allowCors = false` và thử trực tiếp bằng terminal:

```powershell
Invoke-RestMethod http://localhost:3001/data
```

Nếu dùng hệ điều hành khác có thể dùng `curl http://localhost:3001/data`. Công cụ HTTP đọc được JSON dù API không phát CORS header. Điều này cho thấy **CORS là cơ chế bảo vệ ngữ cảnh browser**, không phải hàng rào bắt buộc của HTTP nói chung.

> **Giới hạn thực hành:** endpoint `/proxy` ở đây chỉ gọi URL API **cố định** để minh họa. Với sản phẩm thật, proxy phải có xác thực, phân quyền, kiểm soát URL đích, timeout, hạn mức và xử lý lỗi. Không biến ví dụ thành một open proxy nhận URL bất kỳ từ người dùng.

## 9. Kiểm tra hiểu biết qua các tình huống

### Tình huống A — “Client đã ẩn nút nên endpoint an toàn”

Một ứng dụng chỉ cho quản trị viên nhìn thấy nút “Khóa tài khoản”. Người thường gửi thủ công request tới endpoint khóa tài khoản.

**Phân tích:** Ẩn nút là UX ở browser. Server phải kiểm tra quyền quản trị của người gọi trên endpoint và tài nguyên đích. Nếu endpoint vẫn xử lý, đó là lỗi phân quyền bất kể UI đã ẩn nút.

### Tình huống B — “API báo lỗi CORS nhưng đã ghi đơn hàng”

Browser hiển thị lỗi CORS sau request `POST`. Server vẫn ghi nhận đơn hàng mới.

**Phân tích:** Tùy loại request và preflight, request chính có thể đã được gửi và xử lý. Browser từ chối cung cấp response không đồng nghĩa server đã hủy thao tác. Thiết kế API cần kiểm tra CSRF, idempotency và xác thực/phân quyền ở server; không dùng lỗi CORS như xác nhận giao dịch chưa xảy ra.

### Tình huống C — “Cùng website thì không cần CORS”

Giao diện ở `https://app.example.com`, API ở `https://api.example.com`.

**Phân tích:** Hai địa chỉ có thể cùng *site* nhưng khác *origin*. Với `fetch()` trong browser cần xét CORS để đọc response, trong khi cookie `SameSite` lại dựa trên quy tắc *site* và các điều kiện cookie khác.

### Tình huống D — “Cookie HttpOnly giải quyết XSS”

Website đặt session cookie `HttpOnly` nhưng vẫn dùng `innerHTML` cho dữ liệu người dùng chưa qua xử lý.

**Phân tích:** `HttpOnly` ngăn script đọc cookie trực tiếp, nhưng script độc hại chạy trong trang vẫn có thể đọc dữ liệu DOM và gửi các request mà browser cho phép. Cần sửa nguồn XSS, dùng API DOM an toàn, escape/sanitize theo ngữ cảnh và bổ sung CSP/Trusted Types phù hợp.

### Tình huống E — “Bật CSP ở server là đủ”

Server phát CSP nhưng nhà phát triển vẫn tạo HTML từ dữ liệu không tin cậy, không kiểm tra quyền API và cho phép mọi origin qua CORS.

**Phân tích:** CSP là chính sách browser thực thi, giúp giảm một số rủi ro mã và tài nguyên, không thay thế validation, authorization hoặc thiết kế CORS. Bảo mật hiệu quả cần đặt biện pháp tại **đúng ranh giới**.

## 10. Checklist trước khi đưa tính năng web vào production

1. **Phân loại dữ liệu:** dữ liệu nào thật sự cần xuống browser, dữ liệu nào chỉ được giữ ở server?
2. **Bảo vệ API:** xác thực, phân quyền trên từng request/tài nguyên, xác minh input, xử lý lỗi và giới hạn tốc độ phù hợp.
3. **Phân tích origin/site:** frontend, API, iframe và CDN có cùng origin hay site không? Có cần CORS, credentialed request hay cookie xuyên site không?
4. **Bảo vệ session:** HTTPS, thuộc tính cookie, CSRF defense, quy trình đăng xuất/hết hạn, không dựa vào ẩn/hiện UI.
5. **Chống injection:** dùng `textContent`/template encoding an toàn; sanitize HTML có chủ đích; kiểm thử CSP và Trusted Types theo browser mục tiêu.
6. **Chặn UI redress:** `frame-ancestors`/framing policy đúng nhu cầu; kiểm tra các trang nhạy cảm có được nhúng trái phép không.
7. **Kiểm chứng hành vi:** trong DevTools quan sát `Origin`, cookies, CORS response headers, CSP violations và request/response thật; ở backend kiểm tra log và các quyết định phân quyền.

## 11. Câu hỏi tự đánh giá

**1.** Browser và server đều có thể dùng JavaScript. Vì sao `fetch()` ở hai môi trường có thể cho kết quả khác nhau khi gọi cùng một API không có CORS header?

**Gợi ý trả lời:** JavaScript trong browser bị SOP/CORS giới hạn khi đọc response xuyên origin. Node.js hoặc HTTP client server thông thường không chịu chính sách bảo mật của browser, dù vẫn phải được mạng và máy chủ đích cho phép.

**2.** Vì sao `https://app.example.com` với `https://api.example.com` có thể cần CORS dù cookie `SameSite` coi chúng cùng site?

**Gợi ý trả lời:** SOP/CORS xét origin (scheme, host, port); `SameSite` xét schemeful site (scheme và registrable domain). Hai khái niệm dùng để giải quyết các bài toán khác nhau.

**3.** Nếu người dùng sửa mã client để bật nút quản trị, biện pháp nào thực sự phải ngăn họ thực hiện quyền quản trị?

**Gợi ý trả lời:** Server phải xác thực người gọi và kiểm tra quyền đối với thao tác/tài nguyên, bất kể client hiển thị thế nào.

**4.** Server gửi `Content-Security-Policy: frame-ancestors 'none'`. Bên nào quyết định giá trị chính sách, bên nào ngăn trang bị nhúng?

**Gợi ý trả lời:** Server lựa chọn và phát chính sách qua HTTP response header; browser kiểm tra và từ chối việc nhúng bị cấm.

**5.** Vì sao API không có `Access-Control-Allow-Origin` vẫn có thể bị CSRF?

**Gợi ý trả lời:** Một số request vẫn có thể tới và được server xử lý. CORS chủ yếu quyết định việc JavaScript ở origin khác được đọc response hay không; CSRF cần phòng vệ phía server và chính sách cookie phù hợp.

## Tài liệu tham khảo

- MDN — [Client-side web APIs](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Client-side_APIs/Introduction), [Overview of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview).
- MDN — [Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy), [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- MDN — [Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies), [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP), [Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API).
- OWASP Cheat Sheet Series — [Cross Site Scripting Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html).
