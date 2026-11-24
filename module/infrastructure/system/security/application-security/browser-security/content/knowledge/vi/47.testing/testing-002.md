# SOP test

> **Chương:** Kiểm thử  
> **Chủ đề:** SOP test  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định chính xác hai URL có cùng origin hay khác origin.
2. Thiết kế test case cho Same-Origin Policy (SOP) với scheme, host và port.
3. Kiểm tra giới hạn đọc DOM, storage, window reference và dữ liệu từ frame khác origin.
4. Phân biệt thao tác được phép gửi/nhúng với thao tác bị chặn đọc bởi SOP.
5. Tách lỗi SOP khỏi lỗi CORS, CSP, CORP/COEP, cookie hoặc mixed content.
6. Kiểm tra `postMessage()` an toàn giữa hai window khác origin.
7. Dùng DevTools và một lab hai origin để xác minh behavior thực tế của browser.
8. Viết kết luận kiểm thử có bằng chứng, không suy luận chỉ từ một thông báo Console.

## 1. Same-Origin Policy bảo vệ điều gì?

Same-Origin Policy (SOP) là một nhóm quy tắc của browser nhằm cô lập dữ liệu giữa các origin. Mục tiêu chính là ngăn một trang web tùy ý đọc dữ liệu riêng của trang khác đang mở trong cùng browser, ví dụ DOM, storage hoặc response mà trang kia có quyền truy cập.

Hãy hình dung người dùng đăng nhập vào `https://bank.example` rồi mở một trang không tin cậy ở tab khác. Nếu không có SOP, script ở trang không tin cậy có thể thử đọc nội dung tài khoản, form hoặc dữ liệu trong trang ngân hàng. SOP giới hạn quyền truy cập chéo origin ở browser.

SOP không phải một firewall chặn mọi request cross-origin. Browser vẫn cho phép nhiều loại request hoặc nhúng tài nguyên từ origin khác. Điều quan trọng là phân biệt:

- **Gửi request hoặc nhúng resource:** có thể được phép tùy API, element và policy.
- **Đọc response hoặc truy cập nội dung resource:** thường bị giới hạn bởi SOP, trừ khi cơ chế chia sẻ như CORS cho phép.

Do đó, một request đã xuất hiện trong Network panel không có nghĩa JavaScript gửi request được phép đọc response.

## 2. Xác định origin

Origin được xác định bởi bộ ba:

```text
scheme + host + port
```

Ví dụ:

| URL | Origin | So với `https://app.example.test` |
|---|---|---|
| `https://app.example.test/home` | `https://app.example.test:443` | Cùng origin |
| `https://app.example.test:443/profile` | `https://app.example.test:443` | Cùng origin |
| `http://app.example.test` | `http://app.example.test:80` | Khác scheme |
| `https://api.example.test` | `https://api.example.test:443` | Khác host |
| `https://app.example.test:8443` | `https://app.example.test:8443` | Khác port |
| `https://app.example.test:443` | `https://app.example.test:443` | Cùng origin dù path khác |

Port mặc định được chuẩn hóa theo scheme: HTTP thường là 80, HTTPS thường là 443. Vì vậy `https://app.example.test` và `https://app.example.test:443` có cùng origin.

Path, query và fragment không tham gia vào origin. Hai URL có path khác nhau vẫn cùng origin nếu scheme, host và port giống nhau.

### 2.1. Same-origin và same-site không giống nhau

Hai URL có thể khác origin nhưng cùng site. Ví dụ:

- `https://app.example.test`
- `https://api.example.test`

Chúng khác host nên khác origin. Tuy nhiên, chúng thường cùng schemeful site vì cùng registrable domain `example.test`.

Tương tự, `http://localhost:8080` và `http://localhost:8081` khác origin vì port khác, dù host và scheme giống nhau. Khác biệt này rất hữu ích để kiểm thử SOP cục bộ.

Cookie không được phân vùng theo port. Cookie được quản lý theo domain/host, path, Secure, SameSite và các thuộc tính liên quan; do đó hai port trên cùng host có thể cùng nhận cookie phù hợp. Đây là lý do không dùng cookie scope để suy luận hai URL có cùng origin.

### 2.2. Opaque origin và URL đặc biệt

Không phải mọi URL đều có origin dạng tuple thông thường:

- `data:` thường có opaque origin duy nhất.
- Iframe có `sandbox` nhưng không có `allow-same-origin` được gán opaque origin.
- `about:blank` và một số document tạo động có thể kế thừa origin từ creator/opener tùy cách tạo.
- `blob:` thường gắn với origin của context tạo blob URL.
- `file:` có behavior khác nhau giữa browser và môi trường; không dùng file URL làm nền tảng cho test SOP có thể lặp lại.

Khi test các trường hợp này, ghi nhận browser/version và cách document được tạo. Không suy luận origin chỉ bằng cách nhìn chuỗi URL.

### 2.3. document.domain là cơ chế legacy

Một số ứng dụng cũ từng đặt document.domain về một domain cha chung để nới lỏng truy cập giữa các subdomain cùng site. Cơ chế này đã lỗi thời, có giới hạn và không phù hợp với kiến trúc mới; nó cũng làm thay đổi các giả định về origin và có thể xung đột với các tính năng isolation hiện đại. Khi kiểm thử ứng dụng legacy, ghi nhận cả hai document có đặt document.domain hay không. Với ứng dụng mới, dùng postMessage hoặc API server được thiết kế rõ ràng thay vì dựa vào document.domain.

## 3. Những gì SOP giới hạn

SOP áp dụng khác nhau tùy loại resource và API. Bảng dưới đây là mô hình thực hành khái quát:

| Thao tác từ origin A tới origin B | Behavior thường gặp |
|---|---|
| Đọc `iframe.contentDocument` của B | Bị chặn hoặc trả về `null`/ném SecurityError khi truy cập thuộc tính cross-origin |
| Đọc DOM của window B | Bị giới hạn |
| Đọc `localStorage`/IndexedDB của B | Bị chặn theo origin boundary |
| Gọi `fetch()` tới B không có CORS | Request có thể được gửi, nhưng JavaScript không đọc được response |
| Nhúng ảnh bằng `<img>` | Thường được phép; đọc pixel canvas có thể bị chặn do canvas bị taint |
| Nhúng script classic bằng `<script src>` | Có thể được tải và thực thi; code chạy trong origin của document nhúng |
| Nhúng stylesheet bằng `<link rel="stylesheet">` | Thường được phép, nhưng đọc CSSOM cross-origin bị giới hạn trừ khi đáp ứng điều kiện CORS |
| Điều hướng tab/window tới B | Thường được phép |
| Gửi form tới B | Có thể được phép; SOP không tự ngăn side effect tại server |
| Gửi `window.postMessage()` giữa hai window | Được thiết kế để giao tiếp cross-origin có kiểm soát |

Behavior chính xác còn phụ thuộc API, request mode, CORS headers, CSP, CORP/COEP và browser. Hãy test từng loại truy cập riêng thay vì kết luận “SOP chặn cross-origin” cho mọi trường hợp.

### 3.1. SOP và DOM access

Trang A có thể giữ reference tới window của iframe B, nhưng không được đọc tùy ý DOM hoặc JavaScript state của B:

```js
const frame = document.querySelector('#remote-frame');

try {
  const title = frame.contentWindow.document.title;
  console.log('Title:', title);
} catch (error) {
  console.log('Cross-origin DOM access blocked:', error.name);
}
```

Reference tới `contentWindow` không đồng nghĩa với quyền đọc document bên trong. Browser chỉ cho phép một tập thuộc tính Window hạn chế; truy cập `document` của frame khác origin bị giới hạn.

### 3.2. SOP và storage

Web Storage, IndexedDB và nhiều API lưu trữ được phân vùng theo origin. Trang A không thể trực tiếp đọc `localStorage` hoặc IndexedDB của B chỉ bằng cách biết URL của B.

Storage partitioning và third-party context có thể bổ sung thêm lớp phân vùng theo top-level site. Vì vậy, kết quả thực tế còn phụ thuộc browser privacy features, iframe context và quyền truy cập storage.

### 3.3. SOP không ngăn mọi cross-origin request

Một trang độc hại vẫn có thể cố gửi request tới endpoint của website khác thông qua form, image, navigation hoặc một số request Fetch. Nếu browser đính kèm cookie phù hợp, server có thể nhận request và thực hiện side effect.

SOP chủ yếu bảo vệ việc đọc dữ liệu. Phòng chống request giả mạo làm thay đổi trạng thái cần CSRF token, SameSite cookie, kiểm tra Origin/Referer, Fetch Metadata và thiết kế method/authorization đúng. Không coi SOP là CSRF defense.

## 4. Phân biệt SOP và CORS

SOP là quy tắc mặc định giới hạn quyền đọc cross-origin. CORS (Cross-Origin Resource Sharing) là cơ chế mà server dùng response headers để cho phép một số origin đọc response qua các API như Fetch/XHR.

Ví dụ server B trả:

```http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
```

Nếu request được gửi từ origin đã cho phép và các điều kiện khác phù hợp, browser cho JavaScript đọc response. CORS không phải header mà client tự thêm để tự cấp quyền; quyền đọc được quyết định bởi response từ server và browser enforcement.

### 4.1. Request đơn giản và preflight

Một số cross-origin request thuộc nhóm simple request có thể được gửi mà không cần preflight. Browser vẫn kiểm tra response CORS trước khi cho JavaScript đọc.

Request có method/header/content type ngoài nhóm được xem là simple có thể cần preflight `OPTIONS`. Browser hỏi server liệu origin, method và headers có được phép trước khi gửi request chính.

Ví dụ preflight response:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type, X-Lab-Token
Access-Control-Max-Age: 600
Vary: Origin
```

Preflight thành công chỉ cho phép browser tiếp tục gửi request chính. Response của request chính vẫn cần CORS headers phù hợp để JavaScript đọc được.

### 4.2. Credentialed CORS

Nếu Fetch dùng `credentials: 'include'`, server phải trả origin cụ thể và:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không dùng `Access-Control-Allow-Origin: *` cùng credentialed request. Browser không cho JavaScript đọc response credentialed nếu cấu hình wildcard như vậy.

Cookie còn chịu quy tắc SameSite, Secure, domain/path, third-party cookie policy và browser privacy settings. `credentials: 'include'` không bảo đảm cookie luôn được gửi.

### 4.3. CORS không phải authorization hoặc CSRF defense

CORS kiểm soát JavaScript browser có thể đọc response cross-origin. Nó không thay thế xác thực và phân quyền ở server. Một request đơn giản có thể tới server dù browser không cho JavaScript đọc response.

Vì vậy, server không được dựa vào CORS để ngăn mọi request trái phép hoặc side effect. Dùng authorization cho resource và CSRF protection cho thao tác thay đổi trạng thái.

### 4.4. no-cors không vượt qua SOP

`fetch(url, { mode: 'no-cors' })` không cấp quyền đọc response. Response thường là opaque: JavaScript không đọc được status, headers hoặc body theo cách thông thường. `no-cors` phù hợp với một số tình huống tải resource hạn chế, không phải workaround để đọc API.

## 5. Phân biệt SOP với CSP, CORP và COEP

Các cơ chế này bảo vệ những ranh giới khác nhau:

| Cơ chế | Vai trò |
|---|---|
| SOP | Giới hạn script truy cập dữ liệu giữa các origin |
| CORS | Server cho phép origin cụ thể đọc response cross-origin |
| CSP | Trang giới hạn nguồn tài nguyên và hành vi được phép |
| CORP | Resource khai báo context cross-origin nào được phép nhúng |
| COEP | Document yêu cầu các resource cross-origin đáp ứng điều kiện để tham gia cross-origin isolation |
| COOP | Tách browsing context group trong các tình huống phù hợp, giảm liên kết window giữa site |
| Permissions Policy | Kiểm soát một số browser features trong document và iframe |

Một request có thể bị chặn bởi CSP trước khi tới network; có thể tải được nhưng bị CORS chặn đọc; hoặc bị CORP/COEP ngăn nhúng. Khi test thất bại, xác định lớp policy thực sự gây lỗi.

## 6. Kiểm thử SOP có hệ thống

### 6.1. Chuẩn bị hai origin

Dùng hai origin khác port trên cùng host:

- Origin A: `http://localhost:8080`
- Origin B: `http://localhost:8081`

Chúng khác origin vì port khác. Cách thiết lập này tránh phụ thuộc DNS công cộng và giúp quan sát SOP trong môi trường local.

Không dùng hai path khác nhau trên cùng một port để giả lập cross-origin; path không tham gia vào origin.

### 6.2. Test matrix

| ID | Điều kiện | Thao tác | Kết quả mong đợi |
|---|---|---|---|
| SOP-01 | Cùng origin A | Fetch `/api/same` | JavaScript đọc được JSON |
| SOP-02 | A gọi B không ACAO | Fetch `/api/no-cors` | Request xuất hiện nhưng Fetch reject vì CORS; JS không đọc body |
| SOP-03 | A gọi B có ACAO đúng | Fetch `/api/allow-a` | JavaScript đọc được JSON |
| SOP-04 | A gọi B bằng POST + custom header | Preflight OPTIONS rồi POST | OPTIONS được chấp nhận; request chính thành công |
| SOP-05 | A nhúng iframe B | Đọc `contentWindow.document` | Bị chặn bởi SOP |
| SOP-06 | A và iframe B dùng postMessage | Gửi PING/PONG với targetOrigin chính xác | Hai bên trao đổi message; mỗi bên xác minh origin/source |
| SOP-07 | A nhúng ảnh từ B | Tải ảnh vào `<img>` | Ảnh có thể hiển thị |
| SOP-08 | A vẽ ảnh B lên canvas không CORS | Gọi `getImageData()` | Canvas bị taint và thao tác đọc pixel ném SecurityError |
| SOP-09 | Cùng host khác port | So sánh `location.origin` | Origin khác nhau |
| SOP-10 | Cookie host-only trên localhost | Gọi B từ A với credentials phù hợp | Cookie không phân biệt port; việc gửi còn phụ thuộc SameSite/credentials/browser policy |

Để kiểm tra SOP-10, đặt một cookie host-only trên host localhost khi truy cập B, sau đó từ A gọi endpoint B bằng Fetch với credentials include và cấu hình credentialed CORS chính xác. Server B có thể xác nhận cookie đã tới request; JavaScript không đọc được giá trị nếu cookie có HttpOnly. Hai port khác origin nhưng cookie host-only không có thuộc tính port, nên cùng host có thể nhận cookie. Kết quả vẫn phụ thuộc SameSite, Secure, scheme và browser privacy policy.

### 6.3. Thu thập bằng chứng

Với mỗi test, lưu:

- URL của document nguồn và destination.
- `location.origin` ở mỗi context.
- API hoặc element được dùng.
- Request method, mode, credentials và headers.
- Status, response headers và redirect chain trong Network.
- Console error đầy đủ.
- Kết quả JavaScript quan sát được.
- Browser/version và trạng thái privacy settings liên quan.

Không chỉ ghi “CORS error”. Một CORS error có thể là biểu hiện browser không cho JavaScript đọc response, trong khi request đã tới server. Phải đối chiếu Network panel và log phía server để biết request có được gửi hay không.

## 7. Kiểm thử postMessage giữa hai origin

SOP giới hạn việc đọc DOM của window khác origin, nhưng `window.postMessage()` được thiết kế để hai window trao đổi dữ liệu có kiểm soát.

### 7.1. Gửi với targetOrigin cụ thể

Từ trang A gửi message tới iframe B:

```js
const frame = document.querySelector('#remote-frame');

frame.contentWindow.postMessage(
  { type: 'SOP_LAB_PING', requestId: 'ping-1' },
  'http://localhost:8081'
);
```

Không dùng wildcard `*` khi biết chính xác origin đích và message có dữ liệu nhạy cảm. Nếu window đích điều hướng sang origin khác trước khi nhận message, targetOrigin cụ thể giúp browser không gửi message tới document mới không mong muốn.

### 7.2. Kiểm tra cả origin và source khi nhận

Trang A:

```js
const frame = document.querySelector('#remote-frame');

window.addEventListener('message', (event) => {
  if (event.origin !== 'http://localhost:8081') return;
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== 'SOP_LAB_PONG') return;

  console.log('Validated reply from frame B');
});
```

Trang B:

```js
window.addEventListener('message', (event) => {
  if (event.origin !== 'http://localhost:8080') return;
  if (event.source !== window.parent) return;
  if (event.data?.type !== 'SOP_LAB_PING') return;

  window.parent.postMessage(
    { type: 'SOP_LAB_PONG' },
    'http://localhost:8080'
  );
});
```

`event.origin` xác định origin của sender tại thời điểm gửi; `event.source` giúp ràng buộc đúng window/frame. Sau đó vẫn phải validate `event.data` theo schema và giới hạn độ dài payload. Origin hợp lệ không chứng minh mọi message từ origin đó đều đáng tin: bất kỳ script nào chạy trong cùng origin có thể gọi postMessage.

Không gửi session token, cookie, password hoặc dữ liệu tài khoản qua message nếu không có thiết kế xác thực và nhu cầu rõ ràng. Nếu message mang lệnh, chỉ chấp nhận một allowlist command hẹp.

## 8. Thực hiện SOP test trong DevTools

### 8.1. Kiểm tra origin trực tiếp

Trên tab A và B, chạy trong Console:

```js
({
  href: location.href,
  origin: location.origin,
  protocol: location.protocol,
  host: location.host,
});
```

Ghi lại kết quả. `location.host` gồm hostname và port; `location.hostname` không gồm port. So sánh `location.origin` để kiểm tra tuple origin.

### 8.2. Thử truy cập iframe

1. Mở trang A có iframe trỏ tới B.
2. Trong Console của A, lấy reference tới iframe.
3. Thử đọc `frame.contentWindow.document.title`.
4. Xác nhận browser báo SecurityError hoặc chặn truy cập thuộc tính cross-origin.
5. Trong DevTools của frame B, xác nhận document B vẫn tải và chạy độc lập.

Nếu iframe không tải, kiểm tra trước `X-Frame-Options`, CSP `frame-ancestors`, CSP `frame-src`, mixed content và network error. Đây có thể là lỗi nhúng frame chứ chưa phải bằng chứng SOP đã chặn DOM access.

### 8.3. Thử Fetch không CORS và có CORS

1. Từ A, fetch endpoint B không trả `Access-Control-Allow-Origin`.
2. Xem Network: request có thể đã được gửi và server ghi nhận request.
3. Xem Console: Fetch reject do CORS; JavaScript không đọc được body.
4. Fetch endpoint B có ACAO khớp origin A.
5. Xác nhận JavaScript đọc được JSON.
6. Thử POST có custom header và xem OPTIONS preflight xuất hiện trước request chính.

Nếu preflight thất bại, request chính thường không được gửi. Nếu request đơn giản thất bại CORS, request có thể đã tới server nhưng response không được expose cho JavaScript.

### 8.4. Thử canvas taint

1. Nhúng ảnh từ B bằng `<img>` mà không đặt `crossOrigin`.
2. Chờ ảnh load thành công.
3. Vẽ ảnh lên canvas.
4. Gọi `getImageData()` hoặc `toDataURL()`.
5. Xác nhận browser ném SecurityError do canvas bị taint.

Nếu resource B trả CORS header phù hợp và image được tải ở CORS mode với `crossOrigin` phù hợp, canvas có thể origin-clean. Việc ảnh hiển thị được không đồng nghĩa pixel có thể đọc.

## 9. Thực hành: SOP lab với hai Node.js origin

Lab tạo hai HTTP server:

- A: `http://localhost:8080` — trang kiểm thử.
- B: `http://localhost:8081` — API và iframe khác origin.

Lab cho phép quan sát same-origin fetch, cross-origin fetch không CORS, CORS allowlist, preflight, iframe DOM restriction, postMessage và canvas taint. Không dùng tài khoản, cookie hoặc dữ liệu thật.

### Bước 1 — Tạo file `sop-lab.cjs`

```js
const http = require('node:http');

const ORIGIN_A = 'http://localhost:8080';
const ORIGIN_B = 'http://localhost:8081';

function send(res, status, headers, body = '') {
  res.writeHead(status, headers);
  res.end(body);
}

const appPage = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>SOP test lab - Origin A</title></head><body>',
  '<h1>SOP test lab — Origin A</h1>',
  '<p id="origins"></p>',
  '<button id="same" type="button">Same-origin fetch</button>',
  '<button id="blocked" type="button">Cross-origin fetch without CORS</button>',
  '<button id="allowed" type="button">Cross-origin fetch with CORS</button>',
  '<button id="preflight" type="button">Cross-origin POST with preflight</button>',
  '<button id="dom" type="button">Try reading iframe DOM</button>',
  '<button id="message" type="button">Send postMessage PING</button>',
  '<button id="canvas" type="button">Try reading remote image pixels</button>',
  '<iframe id="remote-frame" title="Origin B frame" src="' + ORIGIN_B + '/frame"></iframe>',
  '<p><img id="remote-image" alt="Remote test image" src="' + ORIGIN_B + '/pixel.svg"></p>',
  '<pre id="output"></pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  'const ORIGIN_B = "http://localhost:8081";',
  "const frame = document.querySelector('#remote-frame');",
  "const output = document.querySelector('#output');",
  "document.querySelector('#origins').textContent = 'A origin: ' + location.origin + ' | B origin: ' + ORIGIN_B;",
  'function show(label, value) {',
  '  output.textContent = label + "\\n" + (typeof value === "string" ? value : JSON.stringify(value, null, 2));',
  '}',
  "document.querySelector('#same').addEventListener('click', async () => {",
  '  try {',
  '    const response = await fetch("/api/same");',
  '    show("Same-origin response", await response.json());',
  '  } catch (error) { show("Same-origin error", error.message); }',
  '});',
  "document.querySelector('#blocked').addEventListener('click', async () => {",
  '  try {',
  '    const response = await fetch(ORIGIN_B + "/api/no-cors");',
  '    show("Unexpected readable response", await response.text());',
  '  } catch (error) { show("Expected CORS rejection", error.message); }',
  '});',
  "document.querySelector('#allowed').addEventListener('click', async () => {",
  '  try {',
  '    const response = await fetch(ORIGIN_B + "/api/allow-a");',
  '    show("CORS-allowed response", await response.json());',
  '  } catch (error) { show("CORS error", error.message); }',
  '});',
  "document.querySelector('#preflight').addEventListener('click', async () => {",
  '  try {',
  '    const response = await fetch(ORIGIN_B + "/api/preflight", {',
  '      method: "POST",',
  '      headers: {',
  '        "Content-Type": "application/json",',
  '        "X-Lab-Token": "synthetic-only",',
  '      },',
  '      body: JSON.stringify({ action: "PING" }),',
  '    });',
  '    show("Preflight + POST response", await response.json());',
  '  } catch (error) { show("Preflight/CORS error", error.message); }',
  '});',
  "document.querySelector('#dom').addEventListener('click', () => {",
  '  try {',
  '    show("Unexpected DOM access", frame.contentWindow.document.title);',
  '  } catch (error) { show("Expected SOP block", error.name + ": " + error.message); }',
  '});',
  "window.addEventListener('message', (event) => {",
  '  if (event.origin !== ORIGIN_B) return;',
  '  if (event.source !== frame.contentWindow) return;',
  '  if (event.data?.type !== "SOP_LAB_PONG") return;',
  '  show("Validated postMessage reply", event.data);',
  '});',
  "document.querySelector('#message').addEventListener('click', () => {",
  '  frame.contentWindow.postMessage({ type: "SOP_LAB_PING" }, ORIGIN_B);',
  '  show("postMessage", "PING sent to " + ORIGIN_B);',
  '});',
  "document.querySelector('#canvas').addEventListener('click', async () => {",
  "  const image = document.querySelector('#remote-image');",
  '  try {',
  '    if (!image.complete) await new Promise((resolve, reject) => {',
  '      image.addEventListener("load", resolve, { once: true });',
  '      image.addEventListener("error", reject, { once: true });',
  '    });',
  '    const canvas = document.createElement("canvas");',
  '    canvas.width = image.naturalWidth;',
  '    canvas.height = image.naturalHeight;',
  '    const context = canvas.getContext("2d");',
  '    context.drawImage(image, 0, 0);',
  '    context.getImageData(0, 0, 1, 1);',
  '    show("Canvas", "Pixels are readable (check whether CORS was enabled).");',
  '  } catch (error) { show("Expected canvas restriction", error.name + ": " + error.message); }',
  '});',
].join('\n');

const framePage = [
  '<!doctype html><html lang="vi"><meta charset="utf-8">',
  '<title>Origin B frame</title><body><h2>Origin B iframe</h2>',
  '<p>This document is served from port 8081.</p>',
  '<script>',
  'window.addEventListener("message", (event) => {',
  '  if (event.origin !== "http://localhost:8080") return;',
  '  if (event.source !== window.parent) return;',
  '  if (event.data?.type !== "SOP_LAB_PING") return;',
  '  window.parent.postMessage({ type: "SOP_LAB_PONG" }, "http://localhost:8080");',
  '});',
  '</script></body></html>',
].join('\n');

const pixelSvg = [
  '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2" viewBox="0 0 2 2">',
  '<rect width="2" height="2" fill="#d33"/>',
  '</svg>',
].join('');

const serverA = http.createServer((req, res) => {
  const url = new URL(req.url, ORIGIN_A);

  if (req.method === 'GET' && url.pathname === '/') {
    return send(res, 200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    }, appPage);
  }

  if (req.method === 'GET' && url.pathname === '/app.js') {
    return send(res, 200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    }, appJs);
  }

  if (req.method === 'GET' && url.pathname === '/api/same') {
    return send(res, 200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, origin: 'A', message: 'same-origin read allowed' }));
  }

  return send(res, 404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store',
  }, 'Not found on Origin A');
});

const serverB = http.createServer((req, res) => {
  const url = new URL(req.url, ORIGIN_B);
  const origin = req.headers.origin;
  const corsHeaders = {
    'Access-Control-Allow-Origin': ORIGIN_A,
    'Vary': 'Origin',
  };

  if (req.method === 'GET' && url.pathname === '/frame') {
    return send(res, 200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    }, framePage);
  }

  if (req.method === 'GET' && url.pathname === '/pixel.svg') {
    return send(res, 200, {
      'Content-Type': 'image/svg+xml',
      'Cache-Control': 'no-store',
    }, pixelSvg);
  }

  if (req.method === 'GET' && url.pathname === '/api/no-cors') {
    console.log('[B] no-CORS endpoint received request from:', origin || '(no Origin)');
    return send(res, 200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, origin: 'B', cors: false }));
  }

  if (req.method === 'GET' && url.pathname === '/api/allow-a') {
    return send(res, 200, {
      ...corsHeaders,
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, origin: 'B', cors: 'allowed for A' }));
  }

  if (url.pathname === '/api/preflight' && req.method === 'OPTIONS') {
    const requestedMethod = req.headers['access-control-request-method'];
    const requestedHeaders = (req.headers['access-control-request-headers'] || '')
      .toLowerCase()
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    const allowedHeaders = ['content-type', 'x-lab-token'];
    const headersAllowed = requestedHeaders.every((value) => allowedHeaders.includes(value));

    if (origin !== ORIGIN_A || requestedMethod !== 'POST' || !headersAllowed) {
      return send(res, 403, { 'Cache-Control': 'no-store' }, '');
    }

    return send(res, 204, {
      ...corsHeaders,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Lab-Token',
      'Access-Control-Max-Age': '300',
    });
  }

  if (url.pathname === '/api/preflight' && req.method === 'POST') {
    if (origin !== ORIGIN_A) {
      return send(res, 403, { 'Cache-Control': 'no-store' }, 'Origin not allowed');
    }

    return send(res, 200, {
      ...corsHeaders,
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, origin: 'B', preflight: 'passed' }));
  }

  return send(res, 404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store',
  }, 'Not found on Origin B');
});

serverA.listen(8080, 'localhost', () => {
  console.log('Origin A listening at ' + ORIGIN_A);
});

serverB.listen(8081, 'localhost', () => {
  console.log('Origin B listening at ' + ORIGIN_B);
});
```

### Bước 2 — Chạy lab

```sh
node sop-lab.cjs
```

Mở `http://localhost:8080`. Nếu một trong hai port đang được dùng, đổi port trong `ORIGIN_A`/`ORIGIN_B` và các URL literal tương ứng trong `appJs`/`framePage`; giữ hai origin khác nhau.

### Bước 3 — Thực hiện test

1. Nhấn **Same-origin fetch**: nhận JSON thành công từ A.
2. Nhấn **Cross-origin fetch without CORS**: B ghi nhận request nhưng A không đọc được response.
3. Nhấn **Cross-origin fetch with CORS**: A đọc được JSON do B cho phép origin A.
4. Nhấn **Cross-origin POST with preflight**: Network hiển thị OPTIONS trước POST; server chỉ cho phép origin A, method POST và hai header đã allowlist.
5. Nhấn **Try reading iframe DOM**: browser chặn truy cập document B.
6. Nhấn **Send postMessage PING**: B kiểm tra origin/source của A rồi trả PONG; A kiểm tra origin/source của B.
7. Nhấn **Try reading remote image pixels**: ảnh có thể hiển thị nhưng canvas pixel access bị chặn do ảnh cross-origin không có CORS.

### Bước 4 — Đối chiếu Network và Console

- `/api/no-cors` thường có request/response 200 trong Network dù Fetch ở A reject.
- `/api/allow-a` có `Access-Control-Allow-Origin: http://localhost:8080`.
- `/api/preflight` có OPTIONS 204 trước POST và các Access-Control-Allow-* phù hợp.
- `/frame` tải được nhưng DOM của nó không đọc được từ A.
- `postMessage` hoạt động vì hai phía xác minh origin và source.
- `/pixel.svg` có thể tải và hiển thị; đọc pixel canvas thất bại.

Browser có thể hiển thị CORS failure như lỗi mạng cho JavaScript. Đối chiếu log server B để xác nhận request có đến server hay không.

### 9.1. Kiểm tra HTTP routes trước khi mở browser

Có thể kiểm tra server đang phục vụ đúng route và header bằng curl:

```sh
curl -i http://localhost:8080/
curl -i http://localhost:8080/api/same
curl -i http://localhost:8081/api/no-cors
curl -i http://localhost:8081/api/allow-a -H "Origin: http://localhost:8080"
```

Kiểm tra preflight:

```sh
curl -i -X OPTIONS http://localhost:8081/api/preflight \
  -H "Origin: http://localhost:8080" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-lab-token"
```

Curl chỉ xác minh server response. Curl không thực thi SOP/CORS enforcement của browser; cần mở trang A trong browser để kiểm tra việc JavaScript có được đọc response hay không.

### 9.2. Dừng lab

Nhấn Ctrl+C trong terminal đang chạy Node.js. Hai server A và B sẽ dừng cùng tiến trình.

## 10. Chẩn đoán kết quả SOP test

| Triệu chứng | Nguyên nhân có thể | Cách phân biệt |
|---|---|---|
| Fetch reject nhưng server log có request | CORS không cho expose response | Kiểm tra ACAO và request trong Network |
| Fetch reject và không có request chính | Preflight bị từ chối hoặc request bị chặn trước network | Tìm OPTIONS và Console error |
| Iframe không hiển thị | X-Frame-Options, CSP frame-ancestors/frame-src, mixed content hoặc lỗi network | Kiểm tra response headers và Console trước khi test DOM |
| Iframe hiển thị nhưng DOM access lỗi | SOP giới hạn đọc document cross-origin | Xác nhận origin A/B và SecurityError |
| Ảnh hiển thị nhưng canvas read lỗi | Canvas bị taint bởi resource cross-origin không CORS | Kiểm tra `crossOrigin`, ACAO và request mode |
| postMessage không có phản hồi | targetOrigin sai, frame chưa load hoặc validation quá chặt/sai | Kiểm tra event.origin, event.source và listener lifecycle |
| CORS chỉ lỗi khi gửi credentials | ACAO wildcard, thiếu ACAC, cookie bị SameSite/privacy policy chặn | Kiểm tra response headers và cookie policy |
| Kết quả khác giữa localhost và domain thật | Scheme/port/site/cookie hoặc HTTPS khác nhau | Ghi location.origin, site, port và cookie attributes |
| Test file:// khác browser | Origin file có behavior đặc thù | Chuyển sang HTTP localhost để test có thể lặp lại |

### 10.1. Không nhầm lỗi browser với lỗi ứng dụng

Khi browser chặn đọc response, JavaScript thường chỉ nhận một lỗi tổng quát. Body response và chi tiết CORS có thể không được expose cho script. Dùng DevTools và log server để xác định:

- Request có được phát ra không?
- Có OPTIONS preflight không?
- Server trả status và headers gì?
- Redirect có đổi origin không?
- Response cuối cùng có đúng ACAO/ACAC không?
- CSP/CORP/COEP có chặn request hoặc embedding trước đó không?

Không tắt browser security flags để làm test “pass”. Điều đó thay đổi threat model và che khuất behavior cần kiểm tra.

## 11. Mẫu ghi nhận kết quả kiểm thử

Mỗi test case nên ghi đầy đủ:

| Trường | Ví dụ |
|---|---|
| Test ID | SOP-02 |
| Browser/version | Chrome stable, version cụ thể |
| Source origin | http://localhost:8080 |
| Target origin | http://localhost:8081 |
| Action | fetch('/api/no-cors') từ trang A |
| Expected | Request có thể tới B, JavaScript không đọc được response |
| Actual | Promise reject; Network cho thấy B trả 200 không có ACAO |
| Evidence | Screenshot Network/Console, server log, response headers |
| Verdict | PASS nếu actual khớp expected |
| Notes | Không dùng Node fetch để kết luận browser CORS enforcement |

### 11.1. Tiêu chí PASS/FAIL

- **PASS:** behavior quan sát được khớp expected result và có bằng chứng từ browser/network/server.
- **FAIL:** browser cho phép đọc dữ liệu cross-origin trái với policy mong đợi, hoặc cơ chế allowlist/CORS/postMessage hoạt động rộng hơn thiết kế.
- **BLOCKED/INCONCLUSIVE:** request không chạy vì lỗi môi trường, extension, CSP, DNS, TLS hoặc cấu hình test; chưa đủ bằng chứng kết luận SOP.

Phân biệt FAIL với INCONCLUSIVE giúp tránh báo cáo nhầm lỗi cấu hình môi trường thành lỗi SOP.

## 12. Checklist kiểm thử SOP

- [ ] Ghi chính xác scheme, host và port của mọi origin.
- [ ] Xác nhận path/query/fragment không làm thay đổi origin.
- [ ] Tách same-origin khỏi same-site.
- [ ] Test ít nhất một cặp origin khác port.
- [ ] Test đọc DOM iframe khác origin.
- [ ] Test storage boundary khi có trang kiểm thử riêng.
- [ ] Phân biệt request được gửi với response được JavaScript đọc.
- [ ] Test Fetch không CORS và Fetch có ACAO allowlist.
- [ ] Test preflight OPTIONS và request chính.
- [ ] Test credentialed CORS nếu ứng dụng có cookie/credential.
- [ ] Test postMessage bằng targetOrigin cụ thể, event.origin, event.source và schema.
- [ ] Test ảnh cross-origin và canvas taint khi ứng dụng xử lý media.
- [ ] Kiểm tra CSP, CORP, COEP, X-Frame-Options và mixed content nếu resource bị chặn.
- [ ] Không dùng CORS như authorization hoặc CSRF defense.
- [ ] Không dùng mode no-cors như cách vượt SOP.
- [ ] Thu thập Network, Console và server log.
- [ ] Ghi browser/version và privacy settings liên quan.
- [ ] Không tắt browser security để làm test pass.
- [ ] Dùng HTTP localhost thay file:// để kết quả có thể lặp lại.
- [ ] Phân loại PASS, FAIL hoặc INCONCLUSIVE theo bằng chứng.

## 13. Câu hỏi tự kiểm tra

**1.** Origin được xác định bởi những thành phần nào?  
**Trả lời:** Scheme, host và port; path, query và fragment không tham gia vào origin.

**2.** `http://localhost:8080` và `http://localhost:8081` có cùng origin không?  
**Trả lời:** Không. Port khác nhau nên origin khác nhau, dù chúng có thể cùng site.

**3.** SOP có chặn mọi request cross-origin không?  
**Trả lời:** Không. Nhiều request/embedding vẫn được phép; SOP chủ yếu giới hạn việc đọc dữ liệu cross-origin.

**4.** Vì sao request B có thể xuất hiện trong Network nhưng Fetch ở A vẫn reject?  
**Trả lời:** Request có thể đã tới server nhưng response không có CORS headers cho phép A đọc.

**5.** CORS giải quyết phần nào của SOP?  
**Trả lời:** CORS cho phép server opt-in để browser expose response cross-origin cho origin được chỉ định.

**6.** Khi nào browser gửi preflight OPTIONS?  
**Trả lời:** Khi request không thuộc nhóm simple request, ví dụ dùng method hoặc header không được safelist.

**7.** Vì sao iframe B hiển thị được nhưng A không đọc được document B?  
**Trả lời:** Browser có thể cho nhúng/navigate cross-origin nhưng SOP vẫn giới hạn quyền đọc DOM.

**8.** Vì sao ảnh cross-origin hiển thị nhưng canvas không đọc được pixel?  
**Trả lời:** Ảnh có thể được tải để hiển thị, nhưng canvas bị taint nếu resource không được chia sẻ qua CORS phù hợp.

**9.** Vì sao phải kiểm tra cả event.origin và event.source khi nhận postMessage?  
**Trả lời:** Origin xác minh nguồn theo origin; source ràng buộc đúng window/frame. Payload vẫn cần validate theo schema.

**10.** SOP có thay thế CSRF protection không?  
**Trả lời:** Không. Request cross-origin có thể tới server và gây side effect dù response không đọc được; server vẫn cần CSRF defense và authorization.

## Tổng kết

SOP test phải bắt đầu bằng việc xác định đúng origin theo scheme, host và port. Sau đó kiểm tra riêng quyền đọc DOM/storage, Fetch, iframe, embedding, canvas và postMessage. Một request cross-origin có thể tới server mà JavaScript không đọc được response; CORS là cơ chế server opt-in cho quyền đọc, còn CSP/CORP/COEP và frame policies kiểm soát những lớp khác. Dùng hai localhost origin khác port để tái hiện behavior, thu thập bằng chứng từ Network, Console và server log, rồi phân loại PASS/FAIL/INCONCLUSIVE. SOP không thay authorization hoặc CSRF protection, và không nên bị vô hiệu hóa trong quá trình kiểm thử.
