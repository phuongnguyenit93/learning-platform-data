# Same-origin policy exception

> **Chương:** Same-origin policy  
> **Chủ đề:** Same-origin policy exception — các tương tác liên origin được phép, cơ chế chia sẻ dữ liệu có kiểm soát và những giới hạn của Same-Origin Policy (SOP).  
> **Phạm vi:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY. Bài học đặt SOP trong mô hình bảo mật giữa trình duyệt, origin, cookie và ứng dụng web; kết nối với CORS, iframe, cookie, cách ly trình duyệt và phòng vệ XSS, CSRF, clickjacking.

## Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Giải thích vì sao **SOP không đồng nghĩa với cấm mọi yêu cầu cross-origin**.
2. Phân loại hoạt động cross-origin thành **ghi/gửi yêu cầu**, **nhúng tài nguyên** và **đọc dữ liệu**.
3. Nhận diện những tương tác hợp lệ như điều hướng, HTML form, `<img>`, classic `<script>`, iframe, một tập con API của `Window`.
4. Giải thích vai trò của **CORS**, **postMessage**, `crossorigin` và canvas tainting, đồng thời phân biệt quyền đọc phản hồi với quyền đọc DOM.
5. Hiểu trường hợp **kế thừa origin**, **opaque origin** và cơ chế `document.domain` đã lỗi thời.
6. Xác định rủi ro của JSONP, script bên thứ ba, CSRF, XS-Leaks, clickjacking và cấu hình CORS quá rộng.
7. Tự kiểm chứng hành vi trong DevTools và chọn biện pháp phòng vệ tương ứng.

## 1. SOP là quy tắc kiểm soát quyền, không phải lệnh cấm mọi kết nối

Với URL HTTP(S), **origin** được nhận diện bởi ba thành phần:

```text
origin = (scheme, host, port)

https://app.example.com:443/profile
        |        |         |
      scheme     host      port

https://app.example.com    ≡ https://app.example.com:443
https://app.example.com    ≠ https://api.example.com
https://app.example.com    ≠ http://app.example.com
https://app.example.com    ≠ https://app.example.com:8443
```

**Same-Origin Policy (SOP)** là tập hợp quy tắc mà browser thực thi để ngăn một origin tùy tiện **đọc hoặc thao tác** dữ liệu của origin khác. Các quy tắc phụ thuộc loại tài nguyên và API; không tồn tại một quy tắc đơn giản “khác origin thì không kết nối”.

Ví dụ một trang tại `https://news.example` có thể dẫn người dùng sang `https://bank.example`. Điều đó cần thiết cho web. Browser cũng có thể tải ảnh, CSS hoặc script từ máy chủ khác. Nhưng JavaScript trên trang tin không được mặc nhiên đọc DOM, dữ liệu tài khoản hoặc phản hồi API riêng tư của ngân hàng.

Vì vậy, khi nói **SOP exception**, cần phân biệt ba nhóm:

- **Tương tác vốn được cho phép:** điều hướng, một số loại request, nhúng tài nguyên và thao tác hạn chế với cửa sổ cross-origin.
- **Chia sẻ có kiểm soát:** máy chủ cấp quyền đọc phản hồi bằng CORS hoặc hai cửa sổ chủ động trao đổi thông điệp bằng `postMessage`.
- **Trường hợp origin đặc biệt/cơ chế lịch sử:** `about:blank`, `srcdoc`, `blob:`, `data:`, iframe sandbox và `document.domain`.

Không phải tất cả các trường hợp trên đều là “ngoại lệ vượt rào SOP” theo cùng một nghĩa. Chúng có những nguyên tắc và giới hạn riêng.

### Ba câu hỏi cốt lõi

Với bất kỳ tương tác cross-origin nào, hãy hỏi theo thứ tự:

1. **Có thể gửi request hoặc tải tài nguyên không?**
2. **Mã JavaScript có thể đọc phản hồi, DOM hoặc dữ liệu chi tiết không?**
3. **Máy chủ có cho phép hành động đó theo xác thực và phân quyền không?**

Một câu trả lời “Có” ở câu 1 **không kéo theo** “Có” ở câu 2 hoặc 3.

## 2. Bức tranh tổng quát: những gì cross-origin vẫn có thể làm

| Hoạt động | Có thể diễn ra cross-origin? | JavaScript của trang gọi có đọc đầy đủ dữ liệu đích? | Kiểm soát liên quan |
|---|---|---|---|
| Nhấp `<a href>` sang website khác | Thường có | Không tự nhận quyền đọc trang được mở | Navigation policy, `noopener`, COOP |
| Gửi HTML `<form>` đến origin khác | Thường có | Không vì vậy đọc được DOM/response cross-origin | CSRF token, SameSite, kiểm tra Origin |
| Nạp ảnh bằng `<img>` | Thường có | Không mặc nhiên đọc được pixel qua canvas | CORS với `crossorigin`, CORP, CSP |
| Nạp classic script bằng `<script src>` | Thường có | **Script được nạp chạy trong ngữ cảnh trang nhúng** | CSP, kiểm soát nguồn, SRI |
| Nạp stylesheet bằng `<link rel=stylesheet>` | Thường có | Không mặc nhiên đọc được CSS rules qua CSSOM | CORS/CSSOM, CSP |
| Nhúng tài liệu bằng `<iframe>` | Có thể | Không đọc trực tiếp DOM cross-origin | SOP, `frame-ancestors`, sandbox |
| `fetch()` đến API khác origin | Có thể gửi request theo Fetch/CORS | Chỉ khi đáp ứng cơ chế đọc phù hợp | CORS, credentials, server auth |
| `postMessage` đến iframe hoặc popup | Có | Chỉ nhận nội dung được bên gửi chủ động đưa vào message | `targetOrigin`, `event.origin`, schema validation |
| Đọc `localStorage` của origin khác | Không bằng API thông thường | Không | Origin-bound storage; có thể partition thêm |
| Đọc trực tiếp DOM iframe cross-origin | Không, trừ trường hợp origin/relaxation hợp lệ | Không | SOP |
| Tạo WebSocket đến server khác origin | Có thể nếu chính sách khác cho phép | Đọc được dữ liệu server chủ động gửi trong kết nối được chấp nhận | Kiểm tra `Origin`, xác thực/phân quyền, CSP `connect-src` |

**Điều kiện chung:** CSP, COOP, COEP, CORP, iframe sandbox, chính sách trình duyệt, loại request và cấu hình server có thể hạn chế thêm. Bảng trên mô tả hành vi mặc định phổ biến, không cam kết mọi URL hoặc mọi browser đều cho phép.

## 3. Cross-origin writes: gửi request khác với đọc dữ liệu

Một số thao tác “ghi” hoặc gây tác động đến server có thể thực hiện từ một trang thuộc origin khác. Trong cách phân loại truyền thống của SOP, nhóm này thường được gọi là **cross-origin writes**.

### 3.1. Điều hướng và HTML form

Ví dụ một trang khác origin có thể cung cấp liên kết:

```html
<a href="https://account.example/settings">
  Mở trang tài khoản
</a>
```

Hoặc gửi biểu mẫu:

```html
<form action="https://shop.example/account/preferences" method="POST">
  <input name="newsletter" value="off">
  <button type="submit">Lưu</button>
</form>
```

Browser có thể gửi POST tới `shop.example`, theo chính sách điều hướng, cookie và biểu mẫu. Nếu server chỉ dựa vào cookie phiên tự động gửi mà không có bảo vệ CSRF, request có thể thực hiện thao tác ngoài ý muốn của người dùng.

**Điểm quan trọng:** Việc browser cho phép submit form **không cho JavaScript của site gửi quyền đọc DOM của trang đích**. Tuy nhiên, server vẫn có thể đã xử lý thay đổi trạng thái.

Phòng vệ chính ở server:

- Kiểm tra **CSRF token** không thể đoán, ràng buộc đúng phiên/ngữ cảnh.
- Kiểm tra `Origin`, có chiến lược `Referer` nếu phù hợp; không coi header này là phương thức xác thực duy nhất.
- Cấu hình `SameSite=Lax` hoặc `Strict` khi phù hợp với luồng nghiệp vụ; hiểu rằng *same-site* không đồng nghĩa *same-origin*.
- Dùng **Fetch Metadata** (`Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`) làm tín hiệu bổ sung để từ chối request cross-site không mong muốn.
- Không thiết kế thao tác thay đổi trạng thái qua `GET`; vẫn thực thi xác thực và phân quyền.

**Ví dụ:** `https://blog.example.com` và `https://account.example.com` khác origin nhưng cùng site theo schemeful site. Nếu blog có thể bị kiểm soát bởi bên ít tin cậy hơn, riêng `SameSite` chưa đủ để phòng tấn công xuất phát từ subdomain đó.

### 3.2. Cross-origin writes có thể bị hạn chế thêm

Không nên hiểu “form thường được phép” thành “mọi yêu cầu đều đến server”:

- Cookie có thể không được gửi vì `SameSite`, `Secure` hoặc chính sách third-party.
- Trang đích có thể từ chối request bằng xác thực, phân quyền hoặc CSRF token.
- CSP `form-action` trên trang gửi, sandbox và một số chính sách điều hướng có thể chặn thao tác.
- Một số Fetch/XHR requests khác origin phải vượt qua **CORS preflight** trước khi request thực tế được gửi.

Khi chẩn đoán, cần phân biệt **browser ngăn gửi**, **browser ngăn đọc**, và **server tự từ chối**.

## 4. Cross-origin embeds: nạp được không có nghĩa đọc được

Web tồn tại được nhờ khả năng nhúng tài nguyên từ nhiều origin. Những trường hợp được phép nhúng là nguồn gốc của nhiều nhầm lẫn về SOP.

### 4.1. Ảnh và canvas: nạp ảnh được, đọc pixel có thể bị chặn

Trang `https://app.example.com` có thể nhúng ảnh:

```html
<img src="https://cdn.example.net/banner.png" alt="Banner">
```

Ảnh có thể hiển thị trên trang; nhưng nếu JavaScript dùng ảnh cross-origin **chưa được cấp quyền đọc phù hợp** để vẽ lên canvas, canvas thường bị đánh dấu **tainted** và API lấy pixel bị chặn.

```js
const img = new Image();
img.src = 'https://cdn.example.net/banner.png';

img.onload = () => {
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);

  try {
    const pixels = ctx.getImageData(0, 0, 1, 1);
    console.log(pixels.data);
  } catch (error) {
    console.log(error.name); // Thường là SecurityError
  }
};
```

Nếu chủ sở hữu ảnh muốn cho phép xử lý pixel từ origin khác, có thể dùng CORS:

```html
<img
  src="https://cdn.example.net/banner.png"
  crossorigin="anonymous"
  alt="Banner">
```

Server ảnh cần trả header CORS phù hợp, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Sau khi ảnh **thực sự được tải thành công theo chế độ CORS**, canvas có thể giữ trạng thái origin-clean. Chỉ thêm thuộc tính `crossorigin` ở phía client là chưa đủ nếu server không cho phép. Đặt `crossOrigin` trong JavaScript **trước khi** gán `src`.

Cùng nguyên tắc này liên quan đến một số nguồn video, SVG và nội dung khác khi được dùng trong canvas; quy tắc chi tiết phụ thuộc loại tài nguyên và API.

### 4.2. Classic script: một trường hợp đặc biệt quan trọng

Trang có thể tải một **classic script** từ origin khác:

```html
<script src="https://cdn.partner.example/widget.js"></script>
```

Nếu script được tải và chạy, nó **thực thi trong môi trường của trang đã nhúng script**. Nó có thể đọc DOM, thao tác UI và dùng những API mà script hợp lệ của trang có quyền sử dụng.

Vì vậy, tải classic script khác origin **không cô lập quyền của script ở origin CDN**. Đây là quyết định tin cậy mã bên thứ ba. Các biện pháp giảm rủi ro gồm:

- Chỉ tải script từ nhà cung cấp được đánh giá và theo chính sách CSP phù hợp.
- Dùng **Subresource Integrity (SRI)** với nội dung tĩnh có hash ổn định khi phù hợp; xem xét chính sách CORS/crossorigin tương ứng.
- Giới hạn công cụ tag manager và script có khả năng chèn thêm script tùy ý.
- Khi thật sự cần ranh giới thực thi cho mã/HTML ít tin cậy, dùng **iframe ở origin riêng**, sandbox và giao thức `postMessage` giới hạn.

**Phân biệt với module scripts:** ES module được tải từ origin khác bằng cơ chế module tiêu chuẩn thường yêu cầu **CORS**. Không áp nguyên xi quy tắc classic script không-CORS cho `<script type="module">` hoặc `import()`.

### 4.3. CSS, font và stylesheet rules

Stylesheet cross-origin thường có thể áp dụng qua:

```html
<link rel="stylesheet" href="https://cdn.example.net/ui.css">
```

Nhưng mã JavaScript không mặc nhiên được đọc mọi chi tiết CSSOM như `sheet.cssRules` của stylesheet cross-origin. Truy cập có thể bị `SecurityError` nếu tài nguyên không được cấp quyền CORS phù hợp. **Sử dụng hiệu ứng hiển thị CSS** và **đọc nội dung quy tắc CSS** là hai năng lực khác nhau.

Font tải từ origin khác qua CSS có các yêu cầu CORS riêng; một số loại tài nguyên không giống classic `<img>` hay classic `<script>`. Khi một tài nguyên không tải được, xem DevTools để xác định đó là lỗi CORS, CSP, MIME, CORP hay lỗi mạng thông thường.

### 4.4. Iframe: nhúng không trao toàn quyền DOM

```html
<iframe
  id="help"
  src="https://help.partner.example/faq"
  title="Trợ giúp"></iframe>
```

Nếu server trang đích cho phép framing, iframe có thể xuất hiện. Tuy nhiên, `https://app.example.com` không mặc nhiên được đọc:

```js
const help = document.getElementById('help');

try {
  console.log(help.contentWindow.document.body.innerText);
} catch (error) {
  console.error('SOP chặn đọc DOM:', error.name);
}
```

Trang được nhúng có thể tự bảo vệ chống clickjacking bằng header phản hồi:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Cần phân biệt:

| Chính sách | Bên đặt | Kiểm soát |
|---|---|---|
| CSP `frame-src` | Trang cha | Trang cha được phép tải iframe từ nguồn nào |
| CSP `frame-ancestors` | Trang con/trang đích | Những trang nào được phép nhúng trang con |
| `X-Frame-Options` | Trang con/trang đích | Quyền bị nhúng trên browser hỗ trợ, với lựa chọn hạn chế hơn |
| `sandbox` trên iframe | Trang cha | Những năng lực bị hạn chế của tài liệu bên trong iframe |

SOP giới hạn quyền đọc DOM, **không phải cơ chế chống framing hoàn chỉnh**.

## 5. Cross-origin reads: CORS là cách chia sẻ có điều kiện

Mặc định, một script ở `https://app.example.com` không được tự do đọc phản hồi từ API `https://api.example.com` bằng `fetch()`. **CORS (Cross-Origin Resource Sharing)** cung cấp cơ chế cho API thông báo browser rằng một số origin được phép đọc tài nguyên.

### 5.1. Ví dụ yêu cầu GET cross-origin

```js
const response = await fetch('https://api.example.com/catalog');
const items = await response.json();
console.log(items);
```

Nếu API cho phép ứng dụng đọc:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

[{"id":1,"name":"Sổ tay"}]
```

Khi điều kiện CORS và các chính sách khác đáp ứng, JavaScript đọc được JSON.

**CORS mở quyền đọc phản hồi cho request được CORS điều khiển. Nó không trao quyền đọc DOM của iframe `https://api.example.com`, không cấp quyền truy cập `localStorage` của origin đó và không tự thay đổi quyền nghiệp vụ trên server.**

### 5.2. Preflight: có request được gửi trước, có request bị chặn

Một số request cross-origin không thuộc nhóm CORS-safelisted phải kiểm tra trước bằng `OPTIONS`. Ví dụ:

```js
await fetch('https://api.example.com/orders', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ productId: 17 }),
});
```

Preflight điển hình:

```http
OPTIONS /orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Nếu API đáp ứng:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
Vary: Origin
```

Browser có thể tiếp tục gửi POST thực tế. Nếu preflight thất bại, **request POST dự kiến sau preflight** không được gửi theo luồng này.

Ngược lại, request GET đơn giản có thể đã đến máy chủ trước khi browser phát hiện response không được đọc vì CORS. Do đó, **CORS không phải hàng rào chống CSRF hoặc hệ thống phân quyền máy chủ**.

### 5.3. Credential và cấu hình CORS

Ví dụ API cần cookie phiên cross-origin:

```js
const response = await fetch('https://api.example.com/me', {
  credentials: 'include',
});
```

API thường cần phản hồi:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không dùng `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true` với kỳ vọng browser cho JavaScript đọc phản hồi credentialed. Cookie có thực sự được gửi còn phụ thuộc `Domain`, `Path`, `Secure`, `SameSite` và chính sách third-party cookies.

Đối với server có nhiều origin hợp lệ, dùng allowlist chính xác:

```js
// Pseudocode phía server, áp dụng cho request CORS từ trình duyệt:
const allowedOrigins = new Set([
  'https://app.example.com',
  'https://admin.example.com',
]);

const requestingOrigin = request.headers.origin;

if (allowedOrigins.has(requestingOrigin)) {
  response.setHeader('Access-Control-Allow-Origin', requestingOrigin);
  response.setHeader('Vary', 'Origin');
}

// Vẫn phải xác thực, phân quyền và phòng CSRF độc lập.
```

Không phản chiếu vô điều kiện mọi `Origin` nhận được. Không cho rằng request thiếu `Origin` là an toàn. HTTP client ngoài browser có thể gọi API trực tiếp, nên **CORS không thể thay việc kiểm tra quyền trên server**.

### 5.4. `mode: 'no-cors'` không phải lối đi vòng

```js
const response = await fetch('https://api.example.com/private', {
  mode: 'no-cors',
});

console.log(response.type); // Thường là "opaque"
```

Trong tình huống thông thường, JavaScript không đọc được body/headers của **opaque response**. `no-cors` giới hạn cách gửi và kiểu response được quan sát; nó không phải tính năng vô hiệu hóa SOP.

## 6. Cross-origin Window: một số thao tác hạn chế vẫn tồn tại

Hai cửa sổ hoặc khung khác origin có thể giữ tham chiếu đến nhau, nhưng API `Window` cross-origin bị giới hạn đáng kể.

Một số thao tác thường được phép trong giới hạn cụ thể:

- Gọi `postMessage()` để gửi thông điệp có chủ đích.
- Quan sát các thuộc tính hạn chế như `closed` trong những tình huống phù hợp.
- Sử dụng `focus()` hoặc `blur()` khi browser cho phép.
- Điều hướng một số cửa sổ bằng cách **ghi** `location` theo quy tắc điều hướng và sandbox; điều này **không** cho quyền **đọc** `location.href` khác origin.
- Tham chiếu một số quan hệ cửa sổ như `parent` hoặc `top` nhưng không vì vậy có quyền truy cập nội dung bên trong.

Chẳng hạn:

```js
const popup = window.open(
  'https://login.partner.example/authorize',
  'partner-login'
);

if (popup) {
  // Có thể gửi thông điệp khi đối tác đã sẵn sàng nhận.
  popup.postMessage(
    { type: 'HELLO' },
    'https://login.partner.example'
  );

  // Không thể tự do đọc popup.document khi popup khác origin.
}
```

Không xem `window.open()` luôn thành công: popup blocker có thể ngăn. **Cross-Origin-Opener-Policy (COOP)** và các đặc tính mở tab như `rel="noopener"` có thể cắt quan hệ `opener` hoặc ảnh hưởng tham chiếu.

Khi mở liên kết không cần tương tác với tab cũ, nên dùng:

```html
<a href="https://partner.example" target="_blank" rel="noopener noreferrer">
  Mở trang đối tác
</a>
```

Các chi tiết API được hỗ trợ có thể khác theo phiên bản browser; **không xây hệ thống dựa trên giả định có thể tùy ý thao tác cửa sổ cross-origin**.

## 7. postMessage: giao tiếp giữa origin mà không phá SOP

`window.postMessage()` là cách được nền tảng thiết kế để giao tiếp giữa cửa sổ cha–iframe hoặc giữa các popup khác origin.

### 7.1. Gửi dữ liệu với `targetOrigin` cụ thể

Giả sử frontend `https://app.example.com` nhúng widget `https://widget.partner.example`.

**Trang cha:**

```html
<iframe
  id="partner-widget"
  src="https://widget.partner.example/panel"
  title="Đối tác">
</iframe>
```

```js
const frame = document.querySelector('#partner-widget');
const expectedOrigin = 'https://widget.partner.example';

function askForHeight() {
  frame.contentWindow.postMessage(
    { type: 'GET_HEIGHT', requestId: 'height-1' },
    expectedOrigin
  );
}

window.addEventListener('message', (event) => {
  if (event.origin !== expectedOrigin) return;
  if (event.source !== frame.contentWindow) return;

  const message = event.data;
  if (
    !message ||
    message.type !== 'HEIGHT' ||
    message.requestId !== 'height-1' ||
    !Number.isInteger(message.value) ||
    message.value < 100 ||
    message.value > 1200
  ) {
    return;
  }

  frame.style.height = String(message.value) + 'px';
});
```

**Trang widget:** khi nhận `GET_HEIGHT`, nó phải tự kiểm tra `event.origin === 'https://app.example.com'` và cấu trúc message; nếu đáp ứng thì trả lời bằng `event.source.postMessage(payload, 'https://app.example.com')`.

### 7.2. Các nguyên tắc an toàn

1. **Bên gửi** dùng `targetOrigin` chính xác khi gửi dữ liệu nhạy cảm; tránh `'*'` trừ khi kịch bản đặc biệt thật sự yêu cầu và đã đánh giá rủi ro.
2. **Bên nhận** kiểm tra `event.origin`, và `event.source` nếu đang ràng buộc giao tiếp với một cửa sổ cụ thể.
3. Xác thực kiểu dữ liệu, schema, giới hạn kích thước và giá trị của `event.data`. Không đưa message thẳng vào `innerHTML` hoặc dùng làm lệnh không kiểm soát.
4. Nếu widget có thể điều hướng, nhớ rằng `event.origin` mô tả origin tại **thời điểm message được gửi**, còn đối tượng cửa sổ có thể đã điều hướng sau đó; duy trì cơ chế xác nhận phiên/giao thức khi cần.
5. Không nhận `event.origin === 'null'` như một chứng chỉ danh tính của tất cả iframe sandbox: nhiều opaque origins có thể serialize thành chuỗi `"null"`.

`postMessage` **không tự chia sẻ DOM hay storage**. Nó cho mỗi bên quyền quyết định thông tin nào được xuất bản qua message.

## 8. Legacy exception: `document.domain` và nới lỏng origin

Trong lịch sử, các ứng dụng ở hai subdomain có thể cố giảm ràng buộc DOM bằng cách đặt `document.domain` về miền cha chung. Ví dụ tài liệu ở:

```text
https://app.example.com
https://reports.example.com
```

có thể từng sử dụng, **ở cả hai phía**:

```js
// Ví dụ lịch sử để nhận diện mã cũ.
// KHÔNG áp dụng cho kiến trúc hoặc tính năng mới.
document.domain = 'example.com';
```

Trên các browser/ngữ cảnh cũ hỗ trợ kỹ thuật này, việc cả hai tài liệu chủ động đặt miền cha hợp lệ có thể cho phép **một số kiểm tra same-origin liên quan đến DOM** giữa hai trang được nới lỏng. Cơ chế lịch sử này có hành vi đặc biệt, kể cả việc ảnh hưởng tới so sánh port khi setter được áp dụng.

Nhưng có những giới hạn quan trọng:

- `document.domain` là **deprecated**; việc hỗ trợ và hành vi phụ thuộc browser và cấu hình cách ly, một số môi trường sẽ không cho phép hoặc khiến setter không có tác dụng mong đợi.
- **Cả hai phía** phải đáp ứng điều kiện; chỉ một trang thay đổi không đủ.
- Không được đặt tùy tiện thành public suffix như `com` hoặc miền không hợp lệ.
- Không nên kỳ vọng cơ chế này mở quyền cho `localStorage`, `IndexedDB`, `BroadcastChannel`, `SharedWorker` hoặc những API lưu trữ/trao đổi khác.
- CSP, sandbox, origin-keyed agent clusters và các cơ chế bảo mật khác có thể ngăn hoặc hạn chế cách làm này.
- Khi cùng miền cha chứa subdomain ít tin cậy, nới lỏng DOM làm tăng rủi ro lan truyền sự cố giữa các ứng dụng.

**Hướng thay thế hiện đại:** giữ các origin tách biệt, dùng API CORS rõ ràng cho dữ liệu cần chia sẻ, hoặc dùng iframe + `postMessage` có kiểm tra nguồn và schema. Không triển khai tính năng mới dựa vào `document.domain`.

## 9. Kế thừa origin và opaque origin: trường hợp trông giống ngoại lệ

Một số tài liệu không có origin HTTP(S) thông thường từ URL hiển thị. Đây là **quy tắc xác lập origin**, không phải cơ chế mở quyền tùy ý.

| Ngữ cảnh | Hành vi origin thường gặp | Lưu ý |
|---|---|---|
| `about:blank` mới tạo | Thường kế thừa origin của tài liệu tạo/điều hướng nó | Sandbox và ngữ cảnh tạo có thể thay đổi kết quả |
| Iframe `srcdoc` | Thường cùng origin với trang nhúng nếu không bị sandbox áp origin riêng | Không phải nơi an toàn để render HTML không tin cậy nếu không cô lập |
| `blob:` URL | Gắn với origin của môi trường tạo blob trong những trường hợp thông thường | Có thêm quy tắc storage partitioning |
| Trang `data:` | Thường nhận **opaque origin** mới | Không coi serialized `"null"` là cùng danh tính |
| Iframe `sandbox` thiếu `allow-same-origin` | Bị đặt vào ngữ cảnh origin đặc biệt/opaque | Các quyền khác còn phụ thuộc token sandbox |
| `file:` | Có thể khác theo browser và ngữ cảnh | Không dùng file local để suy hành vi của website HTTP(S) |

### 9.1. Iframe sandbox và origin

Ví dụ:

```html
<iframe
  sandbox="allow-scripts"
  src="https://untrusted.example/widget">
</iframe>
```

Iframe này được cho phép chạy script, nhưng vì **không** có `allow-same-origin` nên tài liệu bị áp một origin đặc biệt phục vụ sandbox. Việc URL trong `src` nhìn giống origin quen thuộc không đồng nghĩa nó giữ đầy đủ quyền origin ấy.

Tránh kết hợp `allow-scripts` và `allow-same-origin` khi nhúng **nội dung không tin cậy cùng origin với trang cha**, vì tài liệu có thể có cách vượt qua hiệu lực sandbox trong những cấu hình đó.

### 9.2. Opaque origin serialize thành `null`

Khi một opaque origin được biểu diễn thành chuỗi, giá trị thường là `"null"`. Hai opaque origins độc lập có thể cùng serialize thành `"null"` nhưng **không trở thành same-origin**.

Trong giao tiếp CORS, request có thể mang:

```http
Origin: null
```

Server không nên bật `Access-Control-Allow-Origin: null` tùy tiện cho dữ liệu nhạy cảm. Giá trị này có thể đến từ nhiều môi trường như tài liệu sandbox và `data:`, nên không xác định được một đối tác tin cậy duy nhất chỉ qua chữ `null`.

## 10. JSONP: phương án lịch sử lợi dụng tải script cross-origin

Trước khi CORS phổ biến, một số hệ thống sử dụng **JSONP (JSON with Padding)** để nhận dữ liệu từ origin khác.

Ý tưởng là server không trả JSON thuần, mà trả một lời gọi JavaScript:

```js
// Minh họa dạng phản hồi JSONP từ server cũ:
receiveCatalog({ items: ['book', 'pen'] });
```

Trang có thể tải endpoint đó như classic script. Vì tải classic script cross-origin thường được phép, dữ liệu được truyền vào callback.

Tuy nhiên, JSONP có các nhược điểm bảo mật lớn:

- Endpoint được tải **như mã JavaScript**, mang rủi ro thực thi mã trong origin của trang nhúng.
- Nếu callback hoặc phản hồi không được kiểm soát chặt, có thể gây script injection.
- JSONP không có cơ chế phân quyền tương đương CORS; dữ liệu nhạy cảm dễ bị phơi lộ nếu thiết kế sai.
- Không phù hợp cho ứng dụng mới cần giao thức rõ ràng, phân quyền và phương thức HTTP đầy đủ.

**Khuyến nghị:** với hệ thống hiện đại, dùng API JSON + CORS allowlist + xác thực/phân quyền; chỉ xử lý JSONP như một ràng buộc tương thích của hệ thống cũ cần được loại bỏ có kế hoạch.

## 11. WebSocket: một ngoại lệ dễ bỏ sót trong thiết kế xác thực

WebSocket cho phép trình duyệt thiết lập kênh giao tiếp hai chiều đến server khác origin theo giao thức riêng. Cơ chế truy cập WebSocket **không giống Fetch/CORS**: browser không tự áp dụng chính sách `Access-Control-Allow-Origin` để bảo vệ kết nối WebSocket.

Ví dụ client:

```js
const ws = new WebSocket('wss://realtime.example.com/stream');

ws.addEventListener('message', (event) => {
  console.log('Thông điệp từ server:', event.data);
});
```

Khi handshake diễn ra, browser thường đưa header `Origin` thể hiện nguồn của trang tạo kết nối. **Server WebSocket phải tự quyết định có chấp nhận origin đó hay không**, đồng thời kiểm tra cookie/token, xác thực phiên, phân quyền kênh và bảo vệ các thao tác nhạy cảm.

Nếu server chấp nhận mọi origin nhưng dùng cookie phiên tự động để cấp quyền, có thể dẫn đến rủi ro **Cross-Site WebSocket Hijacking**. Cần kiểm tra `Origin` theo allowlist cùng với xác thực/ủy quyền thực sự; không coi `Origin` là chứng thực người dùng. CSP `connect-src` ở client có thể giới hạn điểm kết nối, nhưng không thay thế chính sách ở server.

## 12. Không có “SOP exception” nào thay thế phòng vệ ứng dụng

Cho phép tài nguyên hoặc giao tiếp cross-origin có thể cần thiết nhưng cũng tạo bề mặt tấn công. Một số rủi ro điển hình:

| Rủi ro | Vì sao SOP chưa đủ? | Biện pháp phù hợp |
|---|---|---|
| **XSS** | Script độc chạy ngay trong origin hợp lệ, sử dụng quyền của trang | Encoding theo ngữ cảnh, DOM API an toàn, sanitizer, CSP, Trusted Types |
| **CSRF** | Request cross-origin có thể được gửi; cookie có thể kèm theo | CSRF token, SameSite, kiểm tra Origin/Fetch Metadata, phân quyền |
| **Clickjacking** | Frame cross-origin có thể hiển thị dù DOM không đọc được | CSP `frame-ancestors`, `X-Frame-Options`, xác nhận nghiệp vụ |
| **Rò rỉ qua CORS** | API cấp quyền đọc quá rộng hoặc phản chiếu origin | Allowlist chính xác, xử lý credentials đúng, không bỏ kiểm soát server |
| **Script bên thứ ba bị xâm nhập** | Classic script cross-origin chạy với quyền trang nhúng | Giảm nguồn script, CSP, SRI khi phù hợp, cô lập iframe |
| **postMessage injection** | Giao thức nhận thông điệp quá tin dữ liệu gửi tới | `event.origin`/`source`, xác minh schema, mã hóa đầu ra |
| **XS-Leaks** | Một số tín hiệu về trạng thái tài nguyên có thể lộ qua thời gian, tải/không tải, kích thước hoặc hành vi điều hướng dù không đọc body | SameSite, Fetch Metadata, chính sách cô lập, thiết kế response nhất quán |
| **WebSocket hijacking** | WebSocket không tự tuân CORS như Fetch | Kiểm tra Origin tại handshake, xác thực và phân quyền server |

### 12.1. CSP và Trusted Types đóng vai trò gì?

CSP là lớp chính sách bổ sung để kiểm soát nguồn tải và khả năng thực thi của tài nguyên trên trang:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
```

Nonce phải được tạo ngẫu nhiên cho **mỗi response** và áp vào các script inline hợp lệ tương ứng; không sao chép một nonce tĩnh vào ứng dụng. Chính sách là ví dụ định hướng, cần điều chỉnh theo tài nguyên và luồng chức năng cụ thể.

Trusted Types có thể yêu cầu các sink DOM nhạy cảm chỉ nhận giá trị đã qua policy hợp lệ, trên những browser hỗ trợ:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Đây là lớp phòng vệ cho **DOM XSS**. Trusted Types không mở hoặc đóng quyền đọc cross-origin của CORS, và không thay việc dùng `textContent`, encoding, sanitization đúng ngữ cảnh.

### 12.2. COOP, COEP, CORP và sandbox khác CORS thế nào?

- **CORS:** server thông báo cho browser origin nào được **đọc response** trong những yêu cầu chịu CORS.
- **CORP (Cross-Origin-Resource-Policy):** server đặt giới hạn ai có thể tải/nhúng tài nguyên trong một số ngữ cảnh `no-cors`.
- **COEP (Cross-Origin-Embedder-Policy):** trang yêu cầu các tài nguyên nhúng thỏa quy tắc CORS/CORP tương ứng; có thể cần cho môi trường *cross-origin isolated*.
- **COOP (Cross-Origin-Opener-Policy):** ảnh hưởng nhóm browsing context, quan hệ opener và cách ly cửa sổ.
- **Iframe sandbox:** trang cha hạ quyền của tài liệu nhúng và có thể áp opaque origin.
- **CSP:** quy định nguồn tải, hành vi thực thi, kết nối, framing và các giới hạn khác cho tài liệu.

Những chính sách này bổ sung cho mô hình origin; bật một header thiếu kiểm thử có thể làm hỏng CDN, đăng nhập popup hoặc iframe đối tác. Hãy xác định mục đích và kiểm chứng tác động trước khi triển khai.

## 13. Thực hành kiểm chứng trên môi trường kiểm soát

Dùng hai origin thử nghiệm:

```text
Frontend: http://localhost:3000
API:      http://localhost:4000
```

Hai URL **khác origin do port**, dù cùng host. Có thể sử dụng hai server demo của riêng bạn và DevTools (Network, Console, Application). Không cần gửi request đến hệ thống ngoài quyền quản lý.

### Thí nghiệm A — GET cross-origin: gửi được, đọc chưa chắc được

Từ trang frontend chạy:

```js
fetch('http://localhost:4000/public')
  .then((response) => response.json())
  .then((data) => console.log('Đọc được:', data))
  .catch((error) => console.error('Không đọc được:', error));
```

Thực hiện hai lượt:

1. API trả JSON **không có** `Access-Control-Allow-Origin`.
2. API trả `Access-Control-Allow-Origin: http://localhost:3000`.

Ghi lại **request có xuất hiện ở Network không**, **log server có nhận GET không** và **JavaScript có đọc được JSON không**. Trường hợp 1, browser có thể đã gửi GET nhưng không cho script đọc body; trường hợp 2, đọc được nếu không có chính sách khác ngăn cản.

### Thí nghiệm B — Preflight khác HTML form

Từ frontend gửi JSON:

```js
fetch('http://localhost:4000/echo', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ test: true }),
}).catch(console.error);
```

Quan sát `OPTIONS` preflight. Thử API từ chối rồi cấp CORS headers phù hợp để thấy khi nào POST thực tế được gửi.

Sau đó thử một HTML form tới endpoint demo riêng:

```html
<form action="http://localhost:4000/echo-form" method="POST">
  <input name="value" value="demo">
  <button type="submit">Gửi</button>
</form>
```

Form có thể được gửi dù API không cấp quyền đọc bằng CORS. Đây là minh họa vì sao server cần chống CSRF riêng.

### Thí nghiệm C — Nhúng iframe và quyền DOM

Từ frontend:

```html
<iframe id="other" src="http://localhost:4000/page"></iframe>
```

Trong Console của frontend:

```js
const other = document.getElementById('other');
try {
  console.log(other.contentWindow.document.title);
} catch (error) {
  console.log('Không đọc được DOM:', error.name);
}
```

Tiếp theo, trên response của `/page`, thử thêm `Content-Security-Policy: frame-ancestors 'none'`. So sánh hai trường hợp: iframe **được nhúng nhưng DOM bị giới hạn** và iframe **bị từ chối nhúng**.

### Thí nghiệm D — postMessage hợp lệ

Trong trang `http://localhost:4000/page` (trang con):

```js
window.parent.postMessage(
  { type: 'READY', version: 1 },
  'http://localhost:3000'
);
```

Trong trang frontend:

```js
const frame = document.getElementById('other');

window.addEventListener('message', (event) => {
  if (event.origin !== 'http://localhost:4000') return;
  if (event.source !== frame.contentWindow) return;

  if (event.data?.type === 'READY' && event.data.version === 1) {
    console.log('Đã nhận thông điệp hợp lệ');
  }
});
```

Cần chắc chắn listener ở trang cha được đăng ký **trước khi iframe gửi thông điệp**, hoặc trang cha gửi yêu cầu và đợi phản hồi, để tránh bỏ lỡ sự kiện. Giao tiếp thành công nhưng quyền đọc DOM iframe vẫn bị SOP giới hạn.

### Thí nghiệm E — Canvas tainting

Tải ảnh từ API/CDN thử nghiệm khác origin, vẽ vào `canvas` và thử `getImageData`. Quan sát `SecurityError` trong ngữ cảnh không có quyền CORS. Cấu hình `crossorigin="anonymous"` và `Access-Control-Allow-Origin` phù hợp, tải lại ảnh và đối chiếu. Dùng ảnh demo, không dùng dữ liệu riêng tư.

### Phiếu quan sát

| Thử nghiệm | Request/tài nguyên có thể tải? | Script có thể đọc nội dung? | Minh chứng nên thu |
|---|---|---|---|
| GET thiếu CORS | Có thể | Không qua Fetch/CORS | Network, server log, Console |
| GET có CORS đúng | Có thể | Có khi đủ điều kiện | ACAO, JSON đã đọc |
| POST JSON bị từ chối preflight | `OPTIONS` có thể tới server | Không; POST sau preflight bị chặn | OPTIONS response, thiếu POST |
| Form POST cross-origin | Có thể | Không tự mở DOM đích | Request trên server |
| Iframe cross-origin | Có thể | Không trực tiếp đọc DOM | Lỗi `SecurityError` |
| postMessage được xác thực nguồn | Có | Đọc nội dung được gửi chủ động | `event.origin`, payload |
| Ảnh cross-origin vẽ canvas thiếu CORS | Có thể | Không đọc pixel | `SecurityError` |

**Không kết luận từ Console đơn lẻ.** Luôn đối chiếu request/response headers, tình trạng preflight, network log, server log và trình duyệt được kiểm thử.

## 14. Quy trình phân tích một “ngoại lệ SOP” trong thực tế

Khi gặp một tình huống “trang A làm được việc gì đó với origin B”, áp dụng quy trình:

1. **Xác định origin thật:** scheme, host, port của trang nguồn và đích; có sandbox, `about:blank` hoặc opaque origin không?
2. **Xác định hành động:** điều hướng, submit form, nhúng tài nguyên, đọc DOM, đọc canvas, `fetch`, postMessage hay WebSocket?
3. **Hỏi đó là ghi, nhúng hay đọc:** request thành công có thể khác hoàn toàn việc script được đọc dữ liệu.
4. **Kiểm tra chính sách browser:** SOP, CORS/preflight, CSP, CORP, COOP, COEP, iframe sandbox, mixed content và các chính sách cookie/storage khi liên quan.
5. **Kiểm tra phía server:** đã có xác thực, phân quyền, CSRF token, allowlist origin, kiểm tra handshake và xử lý dữ liệu chưa?
6. **Thu thập bằng chứng:** URL, headers, method, response status, log server và biểu hiện ở Console/Network.
7. **Đánh giá bề mặt tấn công:** khả năng XSS, CSRF, clickjacking, XS-Leaks, script/CDN bên thứ ba hoặc dữ liệu nhạy cảm bị cho phép chia sẻ quá rộng.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Nếu SOP tồn tại, tại sao trang của bạn vẫn hiển thị được ảnh từ CDN khác origin?  
**Đáp án:** Browser cho phép nhiều kiểu nhúng cross-origin. Tuy nhiên, JavaScript không mặc nhiên được đọc pixel của ảnh qua canvas.

**Câu 2.** `https://blog.example.com` có thể gửi POST form đến `https://account.example.com` không? Điều đó chứng minh SOP bị vô hiệu hóa hay sao?  
**Đáp án:** Form cross-origin thường có thể gửi. Đây là loại tương tác được web hỗ trợ; không trao quyền đọc DOM và server vẫn phải chống CSRF.

**Câu 3.** API bật CORS cho `https://app.example.com` thì frontend có được truy cập trực tiếp `localStorage` của `https://api.example.com` không?  
**Đáp án:** Không. CORS áp dụng cho quyền đọc phản hồi của những request tương ứng, không biến hai origin thành một.

**Câu 4.** Tại sao `<script src="https://cdn.partner.example/plugin.js">` có thể rủi ro hơn iframe đối tác?  
**Đáp án:** Classic script được nạp trực tiếp chạy trong môi trường và với nhiều quyền của trang nhúng; iframe khác origin chịu giới hạn SOP và có thể bị sandbox.

**Câu 5.** Dùng `fetch(..., { mode: 'no-cors' })` có giúp đọc JSON riêng tư bị CORS chặn không?  
**Đáp án:** Không. Phản hồi thường opaque và không thể đọc body trong JavaScript.

**Câu 6.** Nếu `postMessage` nhận sự kiện có `event.origin === 'null'`, có thể kết luận đó là iframe sandbox mình tin cậy không?  
**Đáp án:** Không. Nhiều opaque origin có thể serialize thành `"null"`; cần thiết kế giao thức xác thực nguồn/dữ liệu an toàn và không coi `null` là danh tính riêng biệt.

**Câu 7.** Có nên tạo tính năng mới bằng `document.domain = 'example.com'` để hai subdomain đọc DOM của nhau?  
**Đáp án:** Không. Đây là cơ chế legacy đã deprecated, bị giới hạn và có thể làm tăng rủi ro; ưu tiên CORS cho API hoặc `postMessage` cho liên lạc giữa cửa sổ.

**Câu 8.** Vì sao server WebSocket không thể dựa vào `Access-Control-Allow-Origin` để bảo vệ kết nối?  
**Đáp án:** WebSocket handshake không thực thi CORS như Fetch; server phải tự kiểm tra Origin theo chính sách, đồng thời xác thực và phân quyền.

**Câu 9.** Khi một GET cross-origin xuất hiện ở server log nhưng JavaScript báo CORS error, có mâu thuẫn không?  
**Đáp án:** Không. Request có thể đến server, nhưng browser không cho JavaScript đọc phản hồi.

**Câu 10.** SOP có ngăn tất cả tấn công clickjacking không?  
**Đáp án:** Không. SOP giới hạn đọc DOM cross-origin; dùng CSP `frame-ancestors` và/hoặc `X-Frame-Options` để hạn chế bị nhúng trái phép.

## Ghi nhớ

**SOP bảo vệ ranh giới dữ liệu giữa các origin, nhưng web vẫn chủ động hỗ trợ nhiều tương tác cross-origin.** Điều hướng, form, ảnh, classic script và iframe có thể hoạt động; điều đó không có nghĩa JavaScript được đọc toàn bộ dữ liệu của origin đích. CORS là cơ chế chia sẻ phản hồi có kiểm soát; `postMessage` là cơ chế trao đổi thông điệp có chủ đích; `document.domain` là ngoại lệ lịch sử không nên dùng cho thiết kế mới; WebSocket, canvas và sandbox có các quy tắc riêng.

Khi đánh giá một trường hợp “SOP exception”, hãy phân biệt **quyền gửi**, **quyền nhúng**, **quyền đọc** và **quyền thực thi nghiệp vụ**. Chỉ khi nhìn rõ từng quyền, bạn mới có thể chọn chính xác CORS, CSP, Trusted Types, cookie attributes, CSRF token, sandbox, security headers và các kiểm tra phía server để bảo vệ ứng dụng web.
