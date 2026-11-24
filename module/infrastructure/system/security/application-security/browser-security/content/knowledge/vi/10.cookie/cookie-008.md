# Thuộc tính SameSite của cookie

> **Chương:** Cookie  
> **Chủ đề:** SameSite attribute  
> **Module:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích thuộc tính `SameSite` điều khiển việc browser gửi cookie trong ngữ cảnh same-site và cross-site như thế nào.
2. Phân biệt `Strict`, `Lax` và `None`, kể cả hành vi mặc định khi không khai báo thuộc tính.
3. Xác định site theo schemeful site và hiểu vì sao same-site không đồng nghĩa same-origin.
4. Phân tích ảnh hưởng của `SameSite` đối với form POST, điều hướng top-level, iframe, subresource và `fetch`.
5. Nhận diện giới hạn của SameSite trong phòng chống CSRF, đặc biệt với sibling subdomain cùng site.
6. Chọn cấu hình cookie phù hợp và kiểm chứng hành vi bằng DevTools cùng bài lab localhost.

## 1. SameSite giải quyết vấn đề gì?

Cookie thường được browser tự động đính vào request khi request khớp phạm vi cookie. Điều này tiện cho session đăng nhập: người dùng không cần gửi lại mật khẩu trong từng request. Nhưng chính hành vi tự động này tạo điều kiện cho **Cross-Site Request Forgery (CSRF)**.

Ví dụ, người dùng đăng nhập tại `https://bank.example.test`. Một trang khác có thể tạo form gửi request đến ngân hàng. Nếu browser tự động đính session cookie và server chỉ kiểm tra cookie hợp lệ, request có thể thay đổi dữ liệu dù người dùng không chủ động thực hiện hành động đó.

Thuộc tính **SameSite** cho phép server hướng dẫn browser khi nào cookie được gửi dựa trên **site của ngữ cảnh khởi tạo request** so với site của đích:

- `Strict`: giới hạn cookie trong ngữ cảnh same-site.
- `Lax`: cho phép same-site và một số điều hướng top-level cross-site an toàn.
- `None`: không áp dụng hạn chế SameSite cho cross-site; browser hiện đại yêu cầu kèm `Secure`.

SameSite là một lớp giảm rủi ro CSRF, không phải cơ chế xác thực hoặc phân quyền. Nó cũng không thay thế CSRF token, kiểm tra `Origin`, Fetch Metadata hay validation phía server.

## 2. Cookie được gửi dựa trên nhiều điều kiện

Ví dụ server tạo session cookie:

```http
Set-Cookie: __Host-session=<gia-tri-ngau-nhien>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Browser chỉ gửi cookie khi request đồng thời thỏa các điều kiện liên quan:

1. **Host/Domain:** host của request khớp cookie host-only hoặc thuộc phạm vi `Domain`.
2. **Path:** đường dẫn request khớp `Path`.
3. **Secure:** nếu cookie có `Secure`, request phải dùng kênh được browser coi là an toàn.
4. **Thời hạn:** cookie chưa hết hạn hoặc bị xóa.
5. **SameSite:** ngữ cảnh request được phép theo `Strict`, `Lax` hoặc `None`.
6. **Chính sách trình duyệt:** browser có thể chặn hoặc phân vùng cookie bên thứ ba theo thiết lập quyền riêng tư.

`SameSite` không thay thế `Domain` hoặc `Path`. Một cookie host-only của `shop.example.test` không tự gửi tới `api.example.test` chỉ vì hai URL cùng site. Ngược lại, cookie của `localhost` không được cô lập theo port; cookie phù hợp host/path có thể được gửi tới cả `localhost:3000` và `localhost:4000`.

### 2.1. Thuộc tính SameSite được đặt ở đâu?

Server đặt SameSite trong header `Set-Cookie`:

```http
Set-Cookie: session_id=abc123; Path=/; HttpOnly; Secure; SameSite=Strict
```

JavaScript không thể đọc thuộc tính `HttpOnly` và cũng không thể xem đầy đủ thuộc tính cookie qua `document.cookie`. Cookie session nên được server phát hành với các thuộc tính phù hợp; `document.cookie` không thể đặt `HttpOnly`.

### 2.2. Một cấu hình session có thể dùng trong production

```http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ý nghĩa:

- `__Host-` yêu cầu cookie có `Secure`, `Path=/` và không có `Domain`; nhờ vậy cookie gắn với host phát hành.
- `Secure` giới hạn việc gửi cookie trên kênh an toàn.
- `HttpOnly` ngăn JavaScript đọc trực tiếp giá trị cookie.
- `SameSite=Lax` giảm việc gửi cookie trong nhiều ngữ cảnh cross-site, nhưng vẫn cho phép một số điều hướng top-level an toàn.

Đây là một điểm khởi đầu thường hợp lý cho session web truyền thống. Ứng dụng cần đánh giá luồng đăng nhập, thanh toán, SSO và iframe để chọn Strict/Lax/None phù hợp.

## 3. Ba giá trị Strict, Lax và None

### 3.1. So sánh hành vi

| Ngữ cảnh request | `SameSite=Strict` | `SameSite=Lax` | `SameSite=None; Secure` |
|---|---:|---:|---:|
| Request same-site thông thường | Gửi nếu cookie scope khớp | Gửi nếu cookie scope khớp | Gửi nếu cookie scope khớp |
| Điều hướng top-level cross-site bằng GET | Không gửi | Thường gửi | Có thể gửi |
| Form POST cross-site | Không gửi | Không gửi | Có thể gửi |
| `fetch`/XHR cross-site | Không gửi | Không gửi | Có thể gửi |
| Ảnh, script hoặc subresource cross-site | Không gửi | Không gửi | Có thể gửi |
| Iframe cross-site | Không gửi | Không gửi | Có thể gửi |

“Có thể gửi” luôn giả định các điều kiện khác đều thỏa: host/domain, path, Secure, credentials mode và chính sách cookie bên thứ ba. `SameSite=None` không bảo đảm browser sẽ cho phép cookie bên thứ ba trong mọi cấu hình.

### 3.2. Strict: chỉ trong ngữ cảnh same-site

`SameSite=Strict` có giới hạn mạnh nhất. Cookie không được gửi trong request cross-site, kể cả khi người dùng nhấp một link GET từ website khác để đi tới ứng dụng.

Ví dụ người dùng đang có cookie session của `https://account.example.test` rồi nhấp link từ `https://news.other.test`:

- Browser điều hướng đến trang tài khoản.
- Request điều hướng có nguồn khởi tạo cross-site.
- Cookie `Strict` không được gửi trong request đó.
- Sau khi trang tài khoản đã tải và người dùng tiếp tục thao tác same-site, cookie có thể được gửi trong các request tiếp theo.

Điều này có thể làm luồng đăng nhập hoặc liên kết từ bên ngoài trông như người dùng chưa đăng nhập ở lần tải đầu. Strict phù hợp với ứng dụng ưu tiên giảm tối đa việc gửi cookie cross-site và có thể chấp nhận tác động UX đó.

### 3.3. Lax: cho phép điều hướng top-level an toàn

`SameSite=Lax` vẫn hạn chế cookie trong các request cross-site như form POST, iframe, ảnh hoặc `fetch`, nhưng cho phép cookie trong **điều hướng top-level cross-site dùng phương thức an toàn**, phổ biến nhất là GET.

Ví dụ người dùng nhấp link từ một website khác đến trang lịch sử đơn hàng:

```html
<a href="https://shop.example.test/orders">Xem đơn hàng</a>
```

Browser có thể gửi cookie Lax trong điều hướng top-level GET. Tuy nhiên, không được thiết kế endpoint GET để thay đổi trạng thái. Đọc dữ liệu hoặc hiển thị trang là phù hợp; hủy đơn, chuyển tiền hay đổi email phải dùng thao tác có bảo vệ thích hợp.

Lax không có nghĩa mọi request GET cross-site đều được gửi cookie. `fetch` GET, ảnh GET và iframe GET là request tài nguyên/subresource, không phải điều hướng top-level.

### 3.4. None: cho phép cookie trong ngữ cảnh cross-site

Khi một sản phẩm thực sự cần cookie trong iframe hoặc request cross-site, có thể dùng:

```http
Set-Cookie: embed_session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None
```

Browser hiện đại yêu cầu `SameSite=None` đi kèm `Secure`; nếu thiếu Secure, cookie có thể bị từ chối. Kể cả khi cấu hình đúng, chính sách chặn third-party cookie, partitioned storage hoặc thiết lập quyền riêng tư vẫn có thể ngăn cookie được gửi.

Chỉ chọn None khi luồng sản phẩm cần cross-site cookie và đã đánh giá rủi ro. Cân nhắc token ngắn hạn, cơ chế đăng nhập liên kết hoặc cookie partitioned nếu mô hình nhúng phù hợp; không đặt tất cả cookie session thành None theo mặc định.

## 4. Same-site và same-origin là hai ranh giới khác nhau

Với URL HTTP(S), **origin** được xác định bởi scheme, hostname và port. **Schemeful site** thường được xác định bởi scheme và registrable domain (eTLD+1) dựa trên Public Suffix List.

| URL A | URL B | Quan hệ |
|---|---|---|
| `https://app.example.test` | `https://api.example.test` | Same-site, cross-origin |
| `https://app.example.test:443` | `https://app.example.test:8443` | Same-site, cross-origin |
| `https://app.example.test` | `http://app.example.test` | Cross-site, cross-origin do khác scheme |
| `https://app.example.test` | `https://evil.test` | Cross-site, cross-origin |
| `http://localhost:3000` | `http://localhost:4000` | Same-site, cross-origin |
| `http://localhost:3000` | `http://127.0.0.1:4000` | Cross-site, cross-origin |

Điều này giải thích một tình huống quan trọng: trang `https://marketing.example.test` có thể gửi form tới `https://account.example.test`. Hai origin khác nhau, nhưng vẫn cùng site. Cookie Strict/Lax có thể được gửi vì SameSite xét site, trong khi SOP vẫn cấm script marketing đọc DOM tài khoản.

**Không dùng SameSite để thay thế ranh giới origin.** Một subdomain bị chiếm quyền, hosting nội dung không tin cậy hoặc ứng dụng cũ có lỗ hổng vẫn có thể tạo request same-site tới ứng dụng khác.

## 5. Ngữ cảnh request ảnh hưởng SameSite như thế nào?

Browser không chỉ so sánh URL nguồn với URL đích. Nó còn xét **site for cookies** của ngữ cảnh duyệt web, gồm top-level document và các ancestor trong cây frame.

### 5.1. Top-level navigation và subresource

| Hành động | Loại request | Lax cross-site |
|---|---|---|
| Người dùng nhấp link GET sang site khác | Điều hướng top-level | Thường gửi |
| Trang khác gửi form POST sang site khác | Điều hướng top-level bằng POST | Không gửi |
| Trang khác tải ảnh từ site khác | Subresource | Không gửi |
| Trang khác gọi `fetch` tới site khác | Fetch/XHR | Không gửi |
| Trang khác nhúng iframe từ site khác | Nested browsing context | Không gửi |
| Trang same-site gọi endpoint cùng site | Request same-site | Gửi nếu cookie scope khớp |

Với iframe lồng nhau, một ancestor cross-site có thể làm ngữ cảnh được xem là cross-site, ngay cả khi frame hiện tại gọi tài nguyên có hostname cùng site với chính frame. Vì vậy, khi điều tra cookie không được gửi trong widget hoặc luồng thanh toán nhúng, phải xem cả cây frame và top-level site.

### 5.2. Redirect và phương thức

Điều hướng có thể đi qua nhiều redirect. Việc đánh giá cookie cần xét ngữ cảnh của navigation, phương thức và các site trong chuỗi; không suy luận chỉ từ URL cuối cùng. Ví dụ, một callback đăng nhập dùng POST từ identity provider có thể không nhận cookie Lax như một callback top-level GET.

Nếu thiết kế SSO hoặc payment callback, kiểm tra flow thực tế trên browser mục tiêu. Bảo vệ callback bằng state/nonce, PKCE hoặc cơ chế xác thực giao thức phù hợp; đừng hạ tất cả cookie xuống None chỉ để che một lỗi luồng.

### 5.3. Fetch credentials là điều kiện độc lập

Ngay cả khi hai URL same-site, `fetch` mặc định dùng credentials mode `same-origin`. Nếu trang gọi một **origin khác** và muốn browser xét gửi cookie, phải chỉ định:

```js
const response = await fetch('https://api.example.test/profile', {
  credentials: 'include',
});
```

Cookie chỉ được gửi nếu host/domain, path, Secure, SameSite và chính sách browser đều cho phép. Nếu JavaScript muốn đọc response cross-origin, API còn phải cấu hình CORS chính xác:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

`SameSite` không cấp quyền CORS; CORS cũng không làm cookie vượt qua SameSite hoặc third-party cookie blocking.

## 6. SameSite giúp giảm CSRF nhưng không loại bỏ CSRF

### 6.1. Cross-site POST thường không mang Strict/Lax cookie

Giả sử người dùng đăng nhập tại `https://bank.example.test`. Kẻ tấn công điều khiển `https://evil.test` và tạo form:

```html
<form action="https://bank.example.test/change-email" method="POST">
  <input type="hidden" name="email" value="attacker@example.test">
  <button type="submit">Continue</button>
</form>
```

Khi người dùng gửi form, request là cross-site POST. Cookie Strict và Lax thường không được đính kèm. Đây là lý do SameSite giúp giảm một lớp CSRF.

### 6.2. Same-site sibling subdomain vẫn có thể gây CSRF

Giả sử:

- Ứng dụng tài khoản: `https://account.example.test`.
- Subdomain nội dung: `https://blog.example.test`.
- Hai host cùng schemeful site `https://example.test` nhưng khác origin.

Nếu blog bị chiếm quyền hoặc cho phép nội dung không tin cậy, trang đó có thể gửi form POST tới account. Cookie Strict/Lax của account có thể được gửi vì request là **same-site**. SOP ngăn blog đọc DOM account, nhưng không ngăn mọi form request được gửi.

Vì vậy, backend cần:

1. CSRF token được ràng buộc với phiên hoặc một cơ chế chống CSRF tương đương đã thiết kế đúng.
2. Kiểm tra `Origin` (và `Referer` khi phù hợp) đối với thao tác nhạy cảm.
3. Dùng Fetch Metadata như `Sec-Fetch-Site` để bổ sung quyết định từ chối request cross-site; cân nhắc từ chối `same-site` không đáng tin cho endpoint nhạy cảm.
4. Xác thực và phân quyền độc lập trên mỗi endpoint; không dựa vào cookie hợp lệ như bằng chứng người dùng chủ ý.
5. Không dùng GET để thay đổi trạng thái.

### 6.3. XSS vẫn có thể dùng phiên đăng nhập

SameSite không ngăn script XSS chạy trong origin hợp lệ gửi request cùng site. `HttpOnly` giúp JavaScript không đọc trực tiếp session cookie, nhưng script độc hại vẫn có thể gọi API bằng browser và session hiện có. Kết hợp output encoding, sanitizer khi cần HTML, CSP, Trusted Types và kiểm tra server.

### 6.4. Client ngoài browser không bắt buộc tuân theo SameSite

SameSite là chính sách do user agent/browser thực thi khi gửi cookie. Một HTTP client tự viết có thể gửi header Cookie theo ý nó. Do đó server không được coi SameSite là cơ chế authorization hoặc là bằng chứng request chắc chắn xuất phát từ browser hợp lệ.

## 7. Giá trị mặc định khi không khai báo SameSite

Trong các browser hiện đại, cookie không khai báo `SameSite` thường được xử lý gần với `Lax` mặc định. Tuy nhiên, có một chi tiết tương thích cần biết:

- Một số browser áp dụng chế độ **Lax-allowing-unsafe** cho cookie mà ứng dụng **không khai báo SameSite** và browser gán trạng thái mặc định.
- Chế độ này có thể cho phép một số điều hướng top-level cross-site bằng phương thức không an toàn (ví dụ POST) trong một khoảng ngắn sau khi cookie được tạo; các triển khai phổ biến dùng cửa sổ khoảng hai phút.
- Ngoại lệ này không áp dụng như một quyền chung cho cookie được khai báo tường minh `SameSite=Lax`.

Không dựa vào hành vi mặc định hoặc cửa sổ tương thích để bảo vệ endpoint. Hãy khai báo SameSite tường minh và triển khai CSRF protection độc lập.

## 8. Chọn SameSite cho từng loại ứng dụng

| Tình huống | Lựa chọn khởi đầu | Cần xác minh |
|---|---|---|
| Ứng dụng web truyền thống, session first-party | `Lax` | Link từ site ngoài, form POST, OAuth callback |
| Ứng dụng nội bộ ưu tiên giới hạn cross-site và không phụ thuộc inbound navigation | `Strict` | Luồng mở link từ email, SSO và UX đăng nhập |
| Widget/ứng dụng nhúng cần cookie trong iframe cross-site | `None; Secure` khi thực sự cần | Third-party cookie blocking, partitioning, CSRF và token |
| API được gọi từ frontend khác origin nhưng cùng site | Thường cookie Lax có thể đủ | `credentials: 'include'`, CORS và cookie host/domain scope |
| Dịch vụ được nhúng bởi nhiều website bên ngoài | Tránh dùng cookie session chung nếu có thể | Partitioned cookie, token ngắn hạn hoặc thiết kế xác thực khác |

Một số nguyên tắc:

- Khai báo `SameSite` rõ ràng thay vì phụ thuộc mặc định.
- Dùng `Secure` cho cookie nhạy cảm trong production và phục vụ ứng dụng qua HTTPS.
- Dùng `HttpOnly` cho session cookie để hạn chế truy cập trực tiếp từ JavaScript.
- Hạn chế `Domain` rộng; cân nhắc prefix `__Host-` để gắn session cookie với host.
- Dùng `Strict` khi UX và luồng điều hướng cho phép; `Lax` thường là điểm cân bằng cho ứng dụng first-party.
- Chỉ dùng `None` khi cần cross-site cookie và đã kiểm thử chính sách quyền riêng tư của browser.
- Bảo vệ CSRF ở server ngay cả khi đã dùng Strict.

## 9. Thực hành: kiểm chứng SameSite trên trình duyệt

Bài lab dùng Node.js, không cần thư viện ngoài. Ta tạo:

- Ứng dụng thử nghiệm tại port `3000`.
- Server nhận cookie tại `localhost:4000`.
- `http://localhost:3000` và `http://localhost:4000` là **same-site nhưng cross-origin** vì khác port.
- `http://127.0.0.1:3000` và `http://localhost:4000` là **cross-site và cross-origin**.

Server đặt hai cookie host-only `Strict` và `Lax`. Sau đó ta so sánh POST form same-site/cross-origin, POST form cross-site và điều hướng top-level GET cross-site.

> Lab dùng HTTP loopback và cố ý không đặt `Secure` để quan sát Strict/Lax trong môi trường local. Đây là cấu hình học tập; session cookie production phải dùng HTTPS và `Secure`. Lab không mô phỏng `SameSite=None` vì thuộc tính đó cần Secure và chịu chính sách third-party cookie riêng của browser.

### Bước 1 — Tạo file `samesite-lab.cjs`

```js
const http = require('node:http');

const homePage = `<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>SameSite lab</title></head>
<body>
  <h1>SameSite attribute lab</h1>
  <p>Đầu tiên mở trang setup trên localhost để tạo cookie Strict và Lax.</p>
  <p><a href="http://localhost:4000/setup">Mở cookie setup</a></p>
  <p>Sau đó thử hai trang khởi tạo:</p>
  <ul>
    <li><a href="http://localhost:3000/attack">localhost:3000 (same-site với victim)</a></li>
    <li><a href="http://127.0.0.1:3000/attack">127.0.0.1:3000 (cross-site với victim)</a></li>
  </ul>
</body>
</html>`;

const attackPage = `<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>SameSite request test</title></head>
<body>
  <h1>Gửi request tới localhost:4000</h1>
  <p id="source"></p>
  <p>
    Trang hiện tại và victim có thể same-site hoặc cross-site.
    Xem kết quả cookie tại trang đích và log server.
  </p>
  <form action="http://localhost:4000/action-post" method="POST">
    <input type="hidden" name="action" value="demo">
    <button type="submit">Gửi form POST tới victim</button>
  </form>
  <p>
    <a href="http://localhost:4000/action-get">
      Điều hướng top-level GET tới victim
    </a>
  </p>
  <script>
    document.querySelector('#source').textContent =
      'Origin nguồn: ' + location.origin;
  </script>
</body>
</html>`;

function sendHtml(res, body, extraHeaders = {}) {
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    ...extraHeaders,
  });
  res.end(body);
}

http.createServer((req, res) => {
  if (req.url === '/') return sendHtml(res, homePage);
  if (req.url === '/attack') return sendHtml(res, attackPage);
  res.writeHead(404);
  res.end('Not found');
}).listen(3000, '0.0.0.0', () => {
  console.log('App: http://localhost:3000');
  console.log('App: http://127.0.0.1:3000');
});

function cookieReport(req) {
  const cookieNames = new Set(
    (req.headers.cookie || '').split(';').map((part) => part.trim())
  );
  return {
    strictCookieSent: cookieNames.has('strict_demo=1'),
    laxCookieSent: cookieNames.has('lax_demo=1'),
    secFetchSite: req.headers['sec-fetch-site'] || '(browser không gửi)',
    origin: req.headers.origin || '(không có Origin header)',
  };
}

function sendReport(res, report) {
  res.writeHead(200, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(report, null, 2));
}

http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/setup') {
    return sendHtml(res, `<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>Cookie setup</title></head>
<body>
  <h1>Đã tạo cookie thử nghiệm</h1>
  <p>strict_demo và lax_demo là cookie host-only của localhost.</p>
  <p><a href="http://localhost:3000/attack">Thử same-site từ localhost</a></p>
  <p><a href="http://127.0.0.1:3000/attack">Thử cross-site từ 127.0.0.1</a></p>
</body></html>`, {
      'Set-Cookie': [
        'strict_demo=1; Path=/; HttpOnly; SameSite=Strict',
        'lax_demo=1; Path=/; HttpOnly; SameSite=Lax',
      ],
    });
  }

  if (req.method === 'GET' && req.url === '/action-get') {
    const report = cookieReport(req);
    console.log('GET /action-get', report);
    return sendReport(res, report);
  }

  if (req.method === 'POST' && req.url === '/action-post') {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      const report = { ...cookieReport(req), body };
      console.log('POST /action-post', report);
      return sendReport(res, report);
    });
    return;
  }

  res.writeHead(404);
  res.end('Not found');
}).listen(4000, '0.0.0.0', () => {
  console.log('Victim: http://localhost:4000/setup');
});
```

Chạy:

```sh
node samesite-lab.cjs
```

Mở `http://localhost:4000/setup` trước để browser lưu hai cookie. Cookie được tạo trong ngữ cảnh top-level first-party của host `localhost`.

### Bước 2 — Thử same-site nhưng cross-origin

1. Mở `http://localhost:3000/attack`.
2. Trang này và victim `http://localhost:4000` khác port nên **cross-origin**, nhưng cùng scheme và hostname nên **same-site**.
3. Nhấn **Gửi form POST tới victim**.
4. Quan sát trang response và terminal: browser thường gửi cả `strict_demo` và `lax_demo`. Header `Sec-Fetch-Site` thường là `same-site`.

Đây là điểm quan trọng: SameSite không chặn request từ một origin khác nếu origin đó cùng site. Trong thực tế, sibling subdomain có thể tạo rủi ro tương tự.

### Bước 3 — Thử cross-site POST

1. Mở `http://127.0.0.1:3000/attack`.
2. Nguồn là hostname `127.0.0.1`, đích là `localhost`. Đây là cross-site.
3. Nhấn **Gửi form POST tới victim**.
4. Quan sát response và log: trong browser hỗ trợ Fetch Metadata, `Sec-Fetch-Site` thường là `cross-site`; cookie Strict và Lax không được gửi trong POST cross-site.

### Bước 4 — Thử điều hướng top-level GET

Vẫn ở trang `http://127.0.0.1:3000/attack`, nhấn link **Điều hướng top-level GET tới victim**. Browser điều hướng tab tới `localhost:4000/action-get`:

- Cookie Strict không được gửi.
- Cookie Lax thường được gửi vì đây là điều hướng top-level cross-site dùng GET.

So sánh với POST ở bước trước để thấy Lax cho phép một trường hợp điều hướng an toàn, không phải mọi request cross-site.

### Bước 5 — Xem cookie trong DevTools

Mở **Application/Storage → Cookies → http://localhost** và kiểm tra cột SameSite, HttpOnly, Path, Domain. Trong **Network**, chọn request tới `localhost:4000` và xem Request Headers/Cookies hoặc tab Cookies để quan sát cookie được gửi và lý do cookie bị chặn nếu browser cung cấp thông tin đó.

Cookie có `HttpOnly` không xuất hiện trong `document.cookie`; điều này không ngăn browser tự động đính cookie vào request. Thử xóa cookie hoặc đổi giá trị SameSite trong server rồi chạy lại setup để lặp thí nghiệm.

## 10. Chẩn đoán lỗi SameSite

Khi cookie không được gửi trong luồng đăng nhập, iframe hoặc API request:

1. **Xác định site nguồn và đích:** schemeful site có giống nhau không? Có khác scheme, subdomain hoặc public suffix không?
2. **Xem top-level site và ancestor:** request được tạo từ trang chính, iframe lồng nhau hay redirect? Có ancestor cross-site không?
3. **Xác định loại request:** top-level navigation GET, POST, form, image, iframe hay `fetch`? Lax chỉ có ngoại lệ cho một số top-level safe navigation.
4. **Kiểm tra thuộc tính cookie:** SameSite có được khai báo rõ không? None có Secure không? Cookie còn hạn và khớp Domain/Path/Secure không?
5. **Kiểm tra credentials mode:** `fetch` tới origin khác có đặt `credentials: 'include'` chưa?
6. **Kiểm tra chính sách privacy:** browser có chặn third-party cookie hoặc phân vùng storage không?
7. **Kiểm tra DevTools và server log:** cookie có bị browser block không? Request có thực sự tới server? `Sec-Fetch-Site` là giá trị nào?
8. **Đánh giá server-side CSRF:** token, Origin/Referer, Fetch Metadata, authentication và authorization có được kiểm tra không?

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Người dùng nhấp link ngoài nhưng trang chưa nhận session | Cookie Strict bị bỏ qua trên navigation cross-site | Thử Lax và kiểm tra UX callback |
| Form POST từ site khác không có cookie | SameSite Strict/Lax đang hoạt động | Kiểm tra cookie block reason và site nguồn |
| Cookie Lax có trong điều hướng GET nhưng không có trong fetch GET | Fetch không phải top-level navigation | So sánh loại request trong Network |
| Cookie Strict vẫn có trong request từ subdomain | Hai host cùng site | Kiểm tra schemeful site và Sec-Fetch-Site |
| Cookie None không xuất hiện trong iframe | Thiếu Secure hoặc third-party cookie bị chặn | Kiểm tra Set-Cookie, HTTPS và privacy settings |
| Fetch khác origin không gửi cookie dù same-site | Credentials mode mặc định là same-origin | Dùng `credentials: 'include'` nếu cần và cấu hình CORS |
| Cookie có trong request nhưng thao tác trái phép vẫn xảy ra | Backend thiếu CSRF protection/authorization | Kiểm tra token, Origin, Fetch Metadata và quyền |

## 11. Câu hỏi tự kiểm tra

**1.** Cookie `SameSite=Strict` có được gửi khi người dùng nhấp link từ `https://news.other.test` sang `https://account.example.test` không?  
**Trả lời:** Không trong request điều hướng cross-site ban đầu; cookie Strict chỉ được gửi trong ngữ cảnh same-site.

**2.** Cookie `SameSite=Lax` có được gửi trong form POST cross-site không?  
**Trả lời:** Thông thường không. Lax cho phép một số điều hướng top-level cross-site bằng phương thức an toàn như GET.

**3.** `SameSite=None` cần thuộc tính nào đi kèm trong browser hiện đại?  
**Trả lời:** `Secure`; cookie vẫn có thể chịu third-party cookie blocking hoặc partitioning.

**4.** `https://app.example.test` và `https://api.example.test` khác origin nhưng same-site. Cookie Strict có thể được gửi trong request phù hợp không?  
**Trả lời:** Có, nếu cookie scope khớp và ngữ cảnh request được browser xem là same-site. Nếu dùng fetch cross-origin, credentials mode vẫn phải cho phép gửi cookie.

**5.** Vì sao SameSite Strict không ngăn được mọi CSRF từ sibling subdomain?  
**Trả lời:** Sibling subdomain cùng schemeful site nên request có thể là same-site dù khác origin; server vẫn cần CSRF token và kiểm tra nguồn.

**6.** `HttpOnly` có ngăn XSS gửi request bằng session cookie không?  
**Trả lời:** Không. Nó ngăn script đọc trực tiếp giá trị cookie, nhưng browser vẫn có thể tự đính cookie vào request mà script tạo.

**7.** Cookie không khai báo SameSite có hành vi gì trong browser hiện đại?  
**Trả lời:** Thường gần với Lax mặc định. Một số browser có chế độ tương thích Lax-allowing-unsafe ngắn hạn cho cookie không khai báo thuộc tính; không dựa vào ngoại lệ này.

**8.** Vì sao phải kiểm tra `Sec-Fetch-Site` và CSRF token ở server dù cookie đã có SameSite?  
**Trả lời:** SameSite chỉ là một lớp do browser thực thi và không chặn mọi request same-site, XSS hoặc client ngoài browser. Token và kiểm tra server xác minh request theo ngữ cảnh nghiệp vụ.

## Tổng kết

`SameSite` hướng dẫn browser gửi cookie theo quan hệ giữa site của ngữ cảnh khởi tạo và site đích: `Strict` giới hạn mạnh nhất, `Lax` cho phép thêm một số điều hướng top-level an toàn, còn `None; Secure` cho phép cookie trong ngữ cảnh cross-site khi chính sách browser chấp nhận. Same-site khác same-origin, nên sibling subdomain vẫn có thể tạo request same-site và gây CSRF. Hãy khai báo thuộc tính rõ ràng, kết hợp Secure/HttpOnly và cookie scope hợp lý, kiểm thử iframe/redirect/fetch thực tế, đồng thời luôn thực thi **CSRF protection, authentication và authorization ở server**.
