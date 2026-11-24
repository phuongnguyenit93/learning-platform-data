# Cookie Path attribute

Thuộc tính **Path** của cookie xác định những đường dẫn URL mà browser có thể đính kèm cookie vào request gửi tới host phù hợp. Ví dụ cookie có `Path=/app` thường được gửi tới `/app`, `/app/profile` và `/app/orders`, nhưng không được gửi tới `/application` hoặc `/admin`.

Path giúp giới hạn phạm vi gửi cookie theo đường dẫn, giảm việc gửi cookie tới các endpoint không cần dùng nó. Tuy nhiên, **Path không phải ranh giới bảo mật để cách ly các ứng dụng cùng origin**. Các ứng dụng cùng scheme, host và port vẫn thuộc cùng origin; mã cùng origin có thể tương tác với nhau theo SOP, và server có thể thiết lập cookie cho path khác. Muốn cách ly ứng dụng có mức tin cậy khác nhau, cần thiết kế origin/host riêng và kiểm soát quyền ở server.

Bài học thuộc chương **Cookie** trong module **Browser Security** (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; liên hệ Path với Domain, Secure, HttpOnly, SameSite, SOP, CORS và phòng vệ CSRF/XSS.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Path điều khiển việc browser gửi cookie theo URL path như thế nào.
2. Áp dụng quy tắc **path-match** và xác định cookie có được gửi cho một request cụ thể không.
3. Tính **default-path** khi server không khai báo Path hoặc khai báo giá trị không hợp lệ.
4. Phân biệt Path với Domain, host-only cookie, Secure, HttpOnly và SameSite.
5. Giải thích vì sao Path không phải ranh giới bảo mật giữa các ứng dụng cùng origin.
6. Xử lý cookie trùng tên ở nhiều Path và xóa cookie đúng phạm vi.
7. Dùng Node.js và DevTools để quan sát cookie được gửi ở các đường dẫn khác nhau.

## 2. Path làm gì trong mô hình cookie?

Server tạo cookie qua response header **Set-Cookie**. Browser lưu cookie cùng các thuộc tính như host/domain, path, thời hạn và chính sách bảo mật. Khi gửi một HTTP request, browser tự quyết định cookie nào phù hợp với URL và ngữ cảnh request.

Ví dụ:

```http
Set-Cookie: app_session=opaque-value; Path=/app; Secure; HttpOnly; SameSite=Lax
```

Cookie trên có:

- Tên: `app_session`.
- Giá trị: `opaque-value` (ví dụ minh họa; session thực tế phải khó đoán và được quản lý phía server).
- Path: `/app`.
- Secure: chỉ gửi trên kết nối an toàn theo quy tắc browser.
- HttpOnly: JavaScript không đọc trực tiếp cookie bằng `document.cookie`.
- SameSite=Lax: áp dụng quy tắc gửi cookie theo ngữ cảnh site.

Khi request tới URL có path khớp `/app`, browser có thể đính kèm cookie nếu các điều kiện khác cũng thỏa mãn. Request tới path không khớp sẽ không nhận cookie này.

### Path chỉ là một trong nhiều điều kiện gửi cookie

| Thuộc tính | Browser dùng để quyết định | Ví dụ |
| --- | --- | --- |
| **Domain / host-only** | Host nào được nhận cookie | Cookie host-only của `api.example.com` không gửi tới `app.example.com` |
| **Path** | Đường dẫn request nào khớp cookie | `Path=/app` khớp `/app/orders` |
| **Secure** | Kết nối có đủ điều kiện an toàn không | Cookie Secure chỉ gửi qua HTTPS, với ngoại lệ phát triển localhost theo quy tắc browser |
| **HttpOnly** | Script có được truy cập cookie qua API như `document.cookie` không | HttpOnly ngăn JavaScript đọc trực tiếp |
| **SameSite** | Ngữ cảnh request có same-site/cross-site phù hợp không | Lax, Strict, None |
| **Expires / Max-Age** | Cookie còn hạn hay đã hết hạn | Max-Age=3600 tồn tại tối đa khoảng một giờ |

Các thuộc tính kết hợp với nhau. `Path=/app` không buộc browser gửi cookie nếu host không khớp, cookie hết hạn, request không có credentials phù hợp hoặc chính sách SameSite/third-party cookie không cho phép.

## 3. Quy tắc Path matching

Browser so sánh **cookie-path** với **request-path** theo quy tắc path-match. Cookie Path khớp request path khi một trong ba điều kiện sau đúng:

1. Cookie path và request path giống hệt nhau.
2. Cookie path là tiền tố của request path và cookie path kết thúc bằng dấu gạch chéo `/`.
3. Cookie path là tiền tố của request path và ký tự ngay sau tiền tố trong request path là dấu `/`.

Ví dụ cookie có `Path=/app`:

| Request path | Khớp? | Lý do |
| --- | :---: | --- |
| `/app` | Có | Trùng chính xác |
| `/app/` | Có | Ký tự tiếp theo sau `/app` là `/` |
| `/app/profile` | Có | `/app` là tiền tố, ký tự tiếp theo là `/` |
| `/app/orders/42` | Có | Nằm dưới nhánh `/app` |
| `/application` | Không | Ký tự tiếp theo là `l`, không phải `/` |
| `/app-old` | Không | Ký tự tiếp theo là `-` |
| `/APP/profile` | Không | Path matching phân biệt chữ hoa/chữ thường |
| `/admin` | Không | Không có tiền tố `/app` |

### 3.1. Dấu gạch chéo cuối có ý nghĩa

Hai cookie Path sau không hoàn toàn giống nhau:

```http
Set-Cookie: a=1; Path=/app
Set-Cookie: b=1; Path=/app/
```

- `Path=/app` khớp cả request path `/app` và các nhánh con như `/app/profile`.
- `Path=/app/` khớp `/app/` và các nhánh con, nhưng không khớp đường dẫn chính xác `/app`.
- Cả hai đều không khớp `/application`.

Nên chọn một quy ước path nhất quán cho ứng dụng, đặc biệt khi route có hoặc không có dấu gạch chéo cuối.

### 3.2. Query string và fragment không quyết định Path

Path matching xét **đường dẫn của URL request**, không xét query string hoặc fragment:

| URL | Request path | Cookie `Path=/app` |
| --- | --- | :---: |
| `https://example.com/app?tab=orders` | `/app` | Có |
| `https://example.com/app/orders?id=42` | `/app/orders` | Có |
| `https://example.com/admin?next=/app` | `/admin` | Không |
| `https://example.com/app#profile` | `/app` | Có |

Fragment (phần sau `#`) không được gửi trong HTTP request. Chuỗi `/app` nằm trong query hoặc fragment không làm một request tới `/admin` trở thành path khớp.

### 3.3. Path không phụ thuộc HTTP method

Nếu URL path khớp, Path không phân biệt GET, POST, PATCH hay DELETE. Browser vẫn xét các điều kiện khác, nhưng không có thuộc tính Path riêng cho từng method.

Ví dụ cookie `Path=/api` có thể được gửi tới cả:

```text
GET    /api/profile
POST   /api/orders
PATCH  /api/profile
DELETE /api/sessions/current
```

Nếu ứng dụng chỉ muốn cookie xuất hiện ở một số hành động hoặc API nhất định, cần thiết kế host/endpoint/session phù hợp và kiểm tra quyền ở server; Path không thay thế authorization.

## 4. Default Path: khi không khai báo Path

Nếu response Set-Cookie không có Path, hoặc thuộc tính Path có giá trị rỗng/không bắt đầu bằng `/`, browser sử dụng **default-path** được suy ra từ request path đã nhận cookie.

Quy tắc khái quát:

1. Nếu request path rỗng hoặc không bắt đầu bằng `/`, default path là `/`.
2. Nếu request path chỉ có một dấu `/`, default path là `/`.
3. Nếu dấu `/` cuối cùng là dấu đầu tiên của request path, default path là `/`.
4. Trường hợp còn lại, default path là phần từ đầu request path đến ngay trước dấu `/` cuối cùng.

Ví dụ:

| URL tạo response Set-Cookie | Request path | Default Path |
| --- | --- | --- |
| `https://example.com/` | `/` | `/` |
| `https://example.com/login` | `/login` | `/` |
| `https://example.com/app/login` | `/app/login` | `/app` |
| `https://example.com/app/orders/new` | `/app/orders/new` | `/app/orders` |
| `https://example.com/app/` | `/app/` | `/app` |

Ví dụ response từ `/app/login`:

```http
HTTP/1.1 200 OK
Set-Cookie: login_hint=1; HttpOnly; SameSite=Lax
```

Cookie sẽ có default Path là `/app`, không phải mặc định luôn là `/`. Nếu muốn phạm vi rõ ràng, hãy khai báo Path tường minh.

### Giá trị Path không hợp lệ

Nếu giá trị Path rỗng hoặc không bắt đầu bằng `/`, browser bỏ qua giá trị đó và dùng default-path:

```http
Set-Cookie: example=1; Path=app
```

Ở đây `Path=app` không phải path hợp lệ theo quy tắc cookie; browser không tự hiểu thành `/app`. Hãy viết:

```http
Set-Cookie: example=1; Path=/app
```

## 5. Browser gửi Path cookie trong request như thế nào?

Giả sử server đã đặt:

```http
Set-Cookie: app_session=abc123; Path=/app; HttpOnly; SameSite=Lax
```

Khi browser gửi request tới `/app/orders`, request có thể chứa:

```http
GET /app/orders HTTP/1.1
Host: example.com
Cookie: app_session=abc123
```

Khi request tới `/admin`, cookie này không được đính kèm:

```http
GET /admin HTTP/1.1
Host: example.com
```

**Path không được gửi lại trong Cookie request header.** Server chỉ nhận các cặp tên/giá trị cookie; nó không thể nhìn vào header Cookie rồi biết mỗi cookie được tạo với Path hay Domain nào. Thuộc tính Path được browser dùng để lọc cookie trước khi gửi.

Browser áp dụng path matching cho request tài nguyên cùng host, không chỉ điều hướng trang chính. Ví dụ request fetch, ảnh, script hoặc stylesheet tới một URL có path khớp có thể nhận cookie, nếu credentials và các chính sách khác cho phép.

### Path và fetch credentials

Đối với Fetch API, chế độ credentials quyết định browser có đưa credential phù hợp vào request hay không; Path tiếp tục là một điều kiện lọc cookie:

```js
// Nếu cookie Path=/app, request này có thể nhận cookie.
await fetch('/app/profile');

// Cùng origin nhưng path không khớp, cookie Path=/app không được gửi.
await fetch('/admin/profile');
```

Hai request trên cùng origin. Path không thay thế SOP, CORS hay SameSite; nó chỉ tác động đến cookie được đính kèm cho từng URL.

## 6. Path khác Domain, host-only và origin

Cookie không được phân vùng giống hệt các Web API theo origin. Đặc biệt, cookie **không được phân tách theo port**.

| Thành phần URL / ranh giới | Có ảnh hưởng đến cookie? | Giải thích |
| --- | :---: | --- |
| Host | Có | Host-only cookie chỉ gửi tới host tạo nó |
| Domain attribute | Có | Có thể mở rộng cookie tới subdomain phù hợp |
| Path | Có | Lọc theo request path |
| Port | Không | Hai port trên cùng hostname có thể nhận cùng cookie nếu các điều kiện khác phù hợp |
| Scheme | Có điều kiện | Secure cookie chỉ gửi qua kết nối an toàn theo quy tắc browser |
| Origin | Không phải thuộc tính cookie trực tiếp | Origin gồm scheme/host/port; cookie scope không tương đương origin |
| Site | Có qua SameSite | Cookie policy phân loại request theo ngữ cảnh site |

Ví dụ:

```http
Set-Cookie: session=abc; Path=/app; HttpOnly; SameSite=Lax
```

Nếu không có Domain, cookie là host-only. Cookie có thể được gửi tới các request path khớp trên cùng hostname, bất kể request dùng port nào. Nếu server muốn giới hạn theo subdomain, cần hiểu Domain/host-only; Path không thể thay thế.

### Path=/ không có nghĩa cookie gửi tới mọi website

`Path=/` chỉ có nghĩa cookie khớp mọi path **trên host/domain phù hợp**. Nó không mở rộng cookie sang domain bất kỳ. Domain, Secure, SameSite, thời hạn và credentials vẫn được xét.

## 7. Path không phải ranh giới bảo mật

Path hữu ích để giảm việc gửi cookie tới những route không cần dùng, nhưng không nên dùng nó để cách ly hai ứng dụng có mức tin cậy khác nhau trên cùng origin.

### 7.1. SOP không coi Path là origin

Hai URL:

```text
https://example.com/app/
https://example.com/admin/
```

có cùng scheme, host và port nên **cùng origin**. JavaScript chạy trong `/app/` và `/admin/` không bị SOP cách ly chỉ vì path khác nhau. Các cơ chế same-origin cho DOM và storage không tạo biên giới mới theo Path.

### 7.2. Script cùng origin có thể tương tác với cookie Path khác

Path không phải cơ chế bảo mật vì các ứng dụng cùng host có thể thiết lập cookie cho path khác thông qua response Set-Cookie hoặc script không bị HttpOnly. Một trang cùng origin cũng có thể tạo iframe tới URL có path khớp cookie rồi tương tác với tài liệu đó theo quyền same-origin; Path không ngăn việc đọc dữ liệu qua ranh giới tài liệu cùng origin.

Ví dụ, nếu `/app/` và `/admin/` cùng origin, không nên giả định cookie `Path=/admin` là bí mật trước mã JavaScript độc hại chạy trong `/app/`. Nếu cookie là HttpOnly, JavaScript không thể đọc trực tiếp giá trị đó, nhưng vẫn có thể gửi request trong phiên mà browser cho phép; server phải kiểm tra quyền.

### 7.3. Path không thay thế phân quyền endpoint

Một server không nên cho phép hành động chỉ vì request có cookie với một Path cụ thể. Cookie chứng minh browser đã gửi một giá trị phiên; server cần xác thực phiên, kiểm tra người dùng có quyền với route và tài nguyên, kiểm tra CSRF nếu phù hợp.

Nếu cần cách ly mạnh giữa app người dùng, admin và nội dung không tin cậy:

- Dùng hostname/origin riêng theo ranh giới tin cậy.
- Dùng cookie host-only, tránh Domain cookie rộng nếu không cần.
- Giữ session riêng và xác thực/phân quyền ở server.
- Cấu hình CSP, frame-ancestors, Trusted Types và security headers theo từng ứng dụng.
- Không phục vụ HTML/JavaScript tùy ý do người dùng tải lên từ origin đang giữ session nhạy cảm.

## 8. Cookie trùng tên ở nhiều Path

Browser có thể lưu nhiều cookie cùng tên nếu Path khác nhau (hoặc Domain khác nhau). Ví dụ:

```http
Set-Cookie: session=app-value; Path=/app; HttpOnly
Set-Cookie: session=root-value; Path=/; HttpOnly
```

Khi request tới `/app/profile`, cả hai cookie đều có thể khớp. Request header có thể chứa:

```http
Cookie: session=app-value; session=root-value
```

**Cookie request header không mang thuộc tính Path**, nên server không thể xác định trực tiếp giá trị nào thuộc `/app` hay `/`. User agent thường sắp xếp cookie có Path dài hơn trước, nhưng server không nên dựa vào thứ tự này để quyết định danh tính hoặc quyền truy cập.

Rủi ro:

- Framework hoặc middleware có thể chọn cookie đầu tiên, cookie cuối cùng hoặc từ chối cookie trùng tên theo cách khác nhau.
- Reverse proxy và backend có thể phân tích header khác nhau, gây sai lệch session hoặc cookie tossing.
- Việc đổi Path của cookie trong một lần deploy có thể khiến cookie cũ và mới cùng tồn tại.

**Khuyến nghị:** dùng tên cookie duy nhất cho mỗi mục đích và host, tránh cùng tên ở nhiều Path/Domain. Nếu cần đổi scope, chủ động xóa cookie cũ đúng Path/Domain, kiểm thử parser và xoay vòng session khi cần.

## 9. Xóa cookie phải khớp Path và Domain

Để xóa cookie, server gửi lại cookie cùng tên với thời hạn đã hết. Path và Domain phải khớp phạm vi cookie cần xóa.

Cookie ban đầu:

```http
Set-Cookie: app_session=abc123; Path=/app; HttpOnly; SameSite=Lax
```

Xóa đúng phạm vi:

```http
Set-Cookie: app_session=; Path=/app; Max-Age=0; HttpOnly; SameSite=Lax
```

Nếu server chỉ gửi:

```http
Set-Cookie: app_session=; Max-Age=0
```

thì browser tính default-path từ URL response. Nếu default-path không phải `/app`, cookie ban đầu có thể vẫn tồn tại. Tương tự, cookie ban đầu có Domain attribute thì lệnh xóa cần khớp Domain; cookie host-only phải được xử lý đúng host-only scope.

Khi logout, nên xác định đầy đủ cookie name, host/domain, Path và thuộc tính liên quan; gửi lệnh xóa đúng scope và thu hồi session ở server. Xóa cookie ở browser **không thay thế** việc vô hiệu hóa session/token phía server.

## 10. Kết hợp Path với các thuộc tính bảo mật khác

### 10.1. Session cookie cho toàn host

Một cấu hình thường dùng cho session nhạy cảm:

```http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Tiền tố `__Host-` được browser hỗ trợ áp dụng yêu cầu: cookie phải có Secure, Path=/ và không có Domain. Cách này tạo host-only cookie, giảm nguy cơ cookie bị mở rộng sang subdomain và phù hợp khi session cần dùng trên nhiều route của cùng host.

Nếu ứng dụng đặt dưới `/portal` và muốn Path giới hạn ở `/portal`, không thể dùng tiền tố `__Host-` vì tiền tố này yêu cầu Path=/.

### 10.2. Path hẹp hơn cho cookie không nhạy cảm

Ví dụ cookie giao diện chỉ dùng trong khu vực app:

```http
Set-Cookie: app_theme=dark; Path=/app; SameSite=Lax
```

Path hẹp giúp browser không gửi cookie tới `/public` hoặc `/admin` nếu path không khớp. Tuy nhiên, nếu cookie chứa dữ liệu nhạy cảm hoặc quyền truy cập, cần dùng cơ chế bảo vệ tương ứng; Path không làm cookie trở nên bí mật.

### 10.3. HttpOnly và XSS

`HttpOnly` ngăn JavaScript đọc trực tiếp cookie qua `document.cookie`, nhưng browser vẫn gửi cookie trong request khớp Path và các điều kiện khác. Nếu XSS chạy trong ứng dụng, script độc hại có thể gọi API cùng phiên và đọc dữ liệu mà ứng dụng cho phép.

Do đó, phòng XSS vẫn cần:

- Tránh đưa dữ liệu không tin cậy vào `innerHTML`; dùng `textContent` khi chỉ hiển thị văn bản.
- Encode đầu ra theo ngữ cảnh và sanitize HTML nếu thật sự cần.
- Cấu hình CSP phù hợp, ưu tiên nonce/hash thay vì cho phép script inline tùy tiện.
- Cân nhắc Trusted Types để hạn chế một số DOM sink nguy hiểm ở browser hỗ trợ.

### 10.4. SameSite và CSRF

`SameSite` phân loại ngữ cảnh site; Path chỉ phân loại đường dẫn. Cookie `SameSite=Lax; Path=/app` cần cả hai điều kiện phù hợp: request cùng path và ngữ cảnh site được phép gửi. Path không thể thay thế CSRF token hoặc kiểm tra Origin/Fetch Metadata cho endpoint nhạy cảm.

Không nên dùng `GET` để thay đổi trạng thái. Với request dựa trên cookie session, server cần kiểm tra CSRF token hoặc cơ chế tương đương, xác thực và phân quyền.

## 11. Thực hành: quan sát cookie Path trên các URL

Bài thực hành dùng **Node.js 18 trở lên**, không cần cài package. Chạy trên một host và một port để tập trung vào Path.

Các URL sẽ được so sánh:

```text
http://localhost:3000/app/check
http://localhost:3000/app/sub/check
http://localhost:3000/application/check
http://localhost:3000/admin/check
```

### 11.1. Tạo server

Tạo file `path-demo.mjs` trong một thư mục thực hành riêng:

```js
import { createServer } from 'node:http';

const html = `<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Cookie Path demo</title></head>
<body>
  <h1>Cookie Path matching</h1>
  <button id="set">Đặt cookie Path=/app</button>
  <button id="set-default">Đặt cookie không khai báo Path tại /app</button>
  <button id="checks">Kiểm tra 4 đường dẫn</button>
  <button id="clear">Xóa cookie demo</button>
  <pre id="result"></pre>
  <script>
    const output = document.querySelector('#result');
    const log = value => output.textContent += value + '\\n';

    document.querySelector('#set').onclick = async () => {
      const response = await fetch('/app/set');
      log(await response.text());
    };
    document.querySelector('#set-default').onclick = async () => {
      const response = await fetch('/app/set-default');
      log(await response.text());
    };
    document.querySelector('#checks').onclick = async () => {
      for (const path of [
        '/app/check',
        '/app/sub/check',
        '/application/check',
        '/admin/check',
      ]) {
        const response = await fetch(path, { cache: 'no-store' });
        log(path + ': ' + JSON.stringify(await response.json()));
      }
    };
    document.querySelector('#clear').onclick = async () => {
      const response = await fetch('/app/clear');
      log(await response.text());
    };
  </script>
</body>
</html>`;

function hasCookie(req, name, value) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp('(?:^|;\\s*)' + escaped + '=' + value + '(?:;|$)')
    .test(req.headers.cookie || '');
}

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const path = url.pathname;

  if (path === '/demo') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
    return;
  }

  if (path === '/app/set') {
    res.setHeader('Set-Cookie',
      'path_demo=scope-app; Path=/app; HttpOnly; SameSite=Lax; Max-Age=3600');
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Da dat path_demo voi Path=/app');
    return;
  }

  if (path === '/app/set-default') {
    // Response URL là /app/set-default; default-path được suy ra là /app.
    res.setHeader('Set-Cookie',
      'default_demo=scope-default; HttpOnly; SameSite=Lax; Max-Age=3600');
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Da dat default_demo; Path mac dinh la /app');
    return;
  }

  if (path === '/app/clear') {
    res.setHeader('Set-Cookie', [
      'path_demo=; Path=/app; HttpOnly; SameSite=Lax; Max-Age=0',
      'default_demo=; Path=/app; HttpOnly; SameSite=Lax; Max-Age=0',
    ]);
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Da xoa hai cookie demo voi Path=/app');
    return;
  }

  if ([
    '/app/check',
    '/app/sub/check',
    '/application/check',
    '/admin/check',
  ].includes(path)) {
    const result = {
      path,
      pathDemoPresent: hasCookie(req, 'path_demo', 'scope-app'),
      defaultDemoPresent: hasCookie(req, 'default_demo', 'scope-default'),
    };
    console.log(result);
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(JSON.stringify(result));
    return;
  }

  res.writeHead(404).end('Not found');
}).listen(3000, () => {
  console.log('Open http://localhost:3000/demo');
});
```

### 11.2. Chạy và quan sát

Chạy:

```bash
node path-demo.mjs
```

Mở `http://localhost:3000/demo`, sau đó:

1. Nhấn **Đặt cookie Path=/app** và **Đặt cookie không khai báo Path**.
2. Mở **DevTools → Network**, bật Preserve log nếu cần.
3. Nhấn **Kiểm tra 4 đường dẫn**.
4. Quan sát JSON trên trang và log trong terminal.

Kết quả dự kiến:

| Request path | `path_demo` Path=/app | `default_demo` default-path=/app |
| --- | :---: | :---: |
| `/app/check` | Có | Có |
| `/app/sub/check` | Có | Có |
| `/application/check` | Không | Không |
| `/admin/check` | Không | Không |

Cookie được đặt với HttpOnly nên JavaScript không đọc được qua `document.cookie`; server mới là nơi quan sát Cookie request header. Nhấn **Xóa cookie demo** để kiểm tra lệnh xóa với đúng Path.

### 11.3. Kiểm tra default-path

Cookie `default_demo` được tạo từ response URL `/app/set-default` và không có thuộc tính Path. Theo default-path algorithm, browser đặt Path là `/app`. Do đó kết quả giống cookie `path_demo` đã khai báo tường minh `Path=/app`.

Thử sửa endpoint `/app/set-default` thành một endpoint response tại `/login` nhưng vẫn bỏ Path. Default-path khi đó sẽ là `/`; cookie sẽ khớp cả `/admin/check`. Đây là lý do không nên đoán rằng cookie không có Path luôn mặc định thành `/`.

### 11.4. Kiểm tra Path không phải origin boundary

Mở hai tab:

```text
http://localhost:3000/app/
http://localhost:3000/admin/
```

Hai URL cùng scheme, host và port nên cùng origin, dù Path khác nhau. SOP không tạo một vùng cách ly riêng cho `/app/` và `/admin/`. Cookie Path chỉ lọc request gửi cookie; nó không biến hai route thành hai origin độc lập.

**Lưu ý môi trường:** demo dùng HTTP localhost và không đặt Secure để đơn giản hóa. Trong production, session cookie cần HTTPS và cấu hình Secure, HttpOnly, SameSite phù hợp. Không tái sử dụng giá trị cookie demo cho dữ liệu thật.

## 12. Checklist thiết kế Path cho ứng dụng thật

1. **Xác định host và route:** Path chỉ có ý nghĩa sau khi xác định host/domain cookie phù hợp.
2. **Chọn Path rõ ràng:** khai báo tường minh, thường là `/` cho session dùng trên toàn host hoặc path ứng dụng nếu chỉ cần gửi trong một nhánh.
3. **Không dùng Path để phân quyền:** endpoint phải xác thực, authorization và kiểm tra quyền sở hữu tài nguyên.
4. **Không dùng Path để cách ly ứng dụng:** nếu app/admin hoặc nội dung không tin cậy có mức trust khác nhau, cân nhắc host/origin riêng.
5. **Tránh cookie trùng tên:** dùng tên khác nhau cho session, preference và token; không dựa vào thứ tự cookie header.
6. **Xóa đúng scope:** khi logout hoặc đổi cấu hình, gửi cookie hết hạn với cùng Path và Domain/host-only scope.
7. **Kiểm tra thuộc tính bảo mật:** Secure, HttpOnly, SameSite, Expires/Max-Age và tiền tố cookie phù hợp.
8. **Kiểm thử redirect và reverse proxy:** cookie được lọc theo URL browser gửi; route rewrite ở proxy không làm Path trở thành ranh giới bảo mật.
9. **Phòng XSS/CSRF:** HttpOnly không ngăn mọi hành động qua XSS; Path không thay thế CSRF token hoặc kiểm tra Origin.
10. **Quan sát request thực tế:** dùng Network và server log để kiểm tra cookie có được gửi đúng URL hay không.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Path=/app chỉ cho JavaScript trong /app đọc cookie.” | Path chủ yếu điều khiển việc gửi cookie; không tạo ranh giới SOP. Mã cùng origin có thể tương tác qua tài liệu cùng origin. |
| “Không khai báo Path thì cookie luôn có Path=/.” | Browser tính default-path từ request path đã nhận Set-Cookie. |
| “Path=/app khớp /application.” | Không; ký tự sau tiền tố phải thỏa quy tắc path-match, thường là dấu `/` hoặc path phải trùng chính xác. |
| “Path có phân biệt chữ hoa/chữ thường không quan trọng.” | Path matching phân biệt chữ hoa/chữ thường. |
| “Cookie được phân vùng theo port.” | Cookie không có thuộc tính Port; cùng hostname trên port khác có thể nhận cùng cookie nếu điều kiện khác phù hợp. |
| “Path=/ giới hạn cookie ở một ứng dụng.” | Path=/ khớp mọi path trên host/domain phù hợp. |
| “HttpOnly nghĩa là XSS không thể dùng phiên.” | Script không đọc trực tiếp cookie, nhưng vẫn có thể gọi hành động trong phiên nếu ứng dụng cho phép. |
| “Xóa cookie cùng tên là đủ.” | Cần xóa đúng Path và Domain/host-only scope; session phía server cũng cần thu hồi. |
| “Path cookie quyết định endpoint nào được phép.” | Server routing và authorization quyết định endpoint; Path chỉ lọc cookie browser gửi. |

## 14. Câu hỏi tự đánh giá

**Câu 1.** Cookie có `Path=/shop`. Nó có được gửi tới `/shop/cart`, `/shopping` và `/admin` không?

**Gợi ý trả lời:** Có tới `/shop/cart`; không tới `/shopping` vì ký tự tiếp theo không phải dấu `/`; không tới `/admin`.

**Câu 2.** Server trả Set-Cookie từ URL `/account/login` nhưng không khai báo Path. Default-path là gì?

**Gợi ý trả lời:** `/account`, tức phần trước dấu gạch chéo cuối cùng của request path.

**Câu 3.** `/app` và `/admin` có cùng host, scheme và port. Path có ngăn JavaScript ở app tương tác với DOM admin theo SOP không?

**Gợi ý trả lời:** Không. Hai URL cùng origin; Path không tạo origin mới hay biên giới SOP.

**Câu 4.** Hai cookie cùng tên có Path=/ và Path=/app. Server có thể biết Path nào từ Cookie request header không?

**Gợi ý trả lời:** Không. Cookie request header chỉ mang cặp tên/giá trị, không gửi lại thuộc tính Path. Tránh trùng tên và không dựa vào thứ tự.

**Câu 5.** Cookie Path=/app không được gửi tới /admin. Điều đó có chứng minh endpoint /admin không thể thực hiện hành động bằng phiên người dùng không?

**Gợi ý trả lời:** Không thể kết luận như vậy. Có thể tồn tại cookie khác hoặc cơ chế xác thực khác; server phải tự kiểm tra phiên và quyền. Path không phải authorization.

**Câu 6.** Vì sao xóa cookie Path=/app bằng Set-Cookie không có Path có thể thất bại?

**Gợi ý trả lời:** Browser tính default-path từ URL response; nếu không phải /app, lệnh xóa có thể nhắm tới cookie scope khác. Phải dùng đúng Path và Domain/host-only scope.

## Tài liệu tham khảo

- RFC 6265 — [HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265), đặc biệt các mục về cookie storage, default-path, path-match và cookie header.
- MDN — [Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie), [Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- MDN — [Document.cookie](https://developer.mozilla.org/en-US/docs/Web/API/Document/cookie), [Cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies#cookie_prefixes).
- WHATWG — [Fetch Standard: credentials and HTTP network or cache fetch](https://fetch.spec.whatwg.org/).
- OWASP — [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
