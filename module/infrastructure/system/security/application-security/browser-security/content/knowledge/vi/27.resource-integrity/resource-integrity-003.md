# Cross-origin resource — tải tài nguyên từ origin khác một cách an toàn

> **Chương:** Resource integrity  
> **Mục tiêu:** Hiểu cách browser tải script, stylesheet, ảnh, font, media và dữ liệu từ origin khác; phân biệt request mode no-CORS/CORS, credentials và opaque response; cấu hình thuộc tính `crossorigin`; kết hợp CORS, Subresource Integrity (SRI), CORP, COEP và CSP; kiểm tra tài nguyên thực tế bằng DevTools.

## 1. Cross-origin resource là gì?

Một trang web hiếm khi chỉ tải tài nguyên từ chính origin của nó. Giao diện có thể lấy JavaScript từ CDN, font từ nhà cung cấp, ảnh từ image service, dữ liệu từ API hoặc nhúng video từ một nền tảng khác.

Một tài nguyên được xem là **cross-origin** khi origin của URL tài nguyên khác origin của document hoặc context khởi tạo request. Với URL HTTP(S), origin gồm scheme, host và port.

Ví dụ:

| Document | Resource | Quan hệ |
| --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/assets/app.js` | Same-origin |
| `https://app.example.com` | `https://cdn.example.com/app.js` | Cross-origin |
| `https://app.example.com` | `http://app.example.com/logo.png` | Cross-origin và mixed content |
| `https://app.example.com` | `https://app.example.com:8443/api` | Cross-origin do khác port |
| `https://app.example.com` | `https://api.example.net/data` | Cross-origin |

Cross-origin không đồng nghĩa cross-site. Hai subdomain HTTPS có thể khác origin nhưng cùng schemeful site. Browser dùng origin, site, request mode, credentials mode và loại tài nguyên để quyết định cách xử lý.

## 2. Vì sao browser không xử lý mọi cross-origin resource giống nhau?

Các loại tài nguyên có mục đích khác nhau:

- Script được tải để thực thi trong document.
- Stylesheet được áp dụng để định dạng giao diện.
- Ảnh, audio và video được hiển thị hoặc phát.
- Font được dùng để vẽ văn bản.
- Fetch/XHR lấy dữ liệu mà JavaScript muốn đọc.
- Worker chạy code trong execution context riêng.

Nếu browser cấm mọi tải cross-origin, CDN, font, API và tích hợp web sẽ khó hoạt động. Nếu cho phép mọi script đọc mọi response, dữ liệu giữa các origin sẽ mất ranh giới bảo mật.

Vì vậy, browser có nhiều cơ chế:

| Cơ chế | Vai trò |
| --- | --- |
| Same-Origin Policy (SOP) | Giới hạn cách document/script đọc dữ liệu cross-origin |
| CORS | Cho phép server opt-in để JavaScript đọc response cross-origin |
| CORP | Cho server tài nguyên giới hạn việc dùng response trong request no-CORS |
| COEP | Yêu cầu tài nguyên cross-origin opt-in khi document chọn chính sách embedder nghiêm ngặt |
| CSP | Giới hạn những nguồn tài nguyên document được phép tải |
| SRI | Kiểm tra nội dung script/stylesheet bên ngoài có khớp hash đã khai báo |

Các cơ chế này bổ sung cho nhau. Không cơ chế nào thay thế authentication và authorization phía server.

## 3. Request mode: no-CORS và CORS

Browser không chỉ kiểm tra URL; nó còn gắn **mode** cho request.

### no-CORS mode

Một số HTML element mặc định tải tài nguyên cross-origin theo no-CORS. Browser có thể cho tài nguyên được dùng theo mục đích của element nhưng giới hạn việc JavaScript đọc response.

Ví dụ ảnh:

```html
<img src="https://images.example.net/photo.jpg" alt="Ảnh">
```

Ảnh có thể hiển thị dù server không trả CORS header. Tuy nhiên, nếu vẽ ảnh cross-origin này lên canvas mà không có CORS phù hợp, canvas bị taint và JavaScript không thể đọc pixel bằng các API đọc dữ liệu canvas.

### CORS mode

Request CORS yêu cầu server tài nguyên trả các header cho phép origin gọi request. Ví dụ:

```js
const response = await fetch("https://api.example.net/products");
const products = await response.json();
```

Fetch mặc định dùng mode CORS. JavaScript chỉ đọc được response nếu CORS check thành công.

### no-cors không phải cách bỏ qua CORS

```js
const response = await fetch("https://api.example.net/private", {
  mode: "no-cors",
});

console.log(response.type); // "opaque" nếu request hoàn tất theo no-CORS
```

Opaque response không cho JavaScript đọc status, headers hoặc body như response thông thường. Chọn no-CORS không biến một API riêng tư thành API có thể đọc được.

## 4. Opaque response và giới hạn đọc dữ liệu

Khi Fetch nhận response no-CORS cross-origin, browser có thể trả về một **opaque response**. JavaScript nhìn thấy một đối tượng Response bị giới hạn:

- `response.type` là `"opaque"`.
- Status được biểu diễn là 0.
- Headers không thể đọc theo cách thông thường.
- Body không thể đọc bằng `text()`, `json()` hoặc `blob()`.

Opaque response có ích cho một số trường hợp tải tài nguyên mà code không cần đọc nội dung, nhưng không phù hợp với API dữ liệu.

Nếu ứng dụng cần đọc response, hãy:

1. Dùng request mode CORS (thường là mặc định của Fetch).
2. Cấu hình server tài nguyên trả `Access-Control-Allow-Origin` phù hợp.
3. Nếu gửi credentials, cấu hình allow-origin cụ thể và `Access-Control-Allow-Credentials: true`.
4. Chỉ cho phép method/header cần thiết.

Không dùng service worker hoặc proxy client-side để giả vờ biến opaque response thành response có thể đọc. Nếu cần proxy, hãy thiết kế server-side proxy có authentication, authorization, kiểm tra đích URL và chống SSRF.

## 5. Cách các HTML element tải cross-origin resource

Mỗi loại element có request mode và yêu cầu khác nhau:

| Element/API | Hành vi cross-origin thường gặp | Điều cần nhớ |
| --- | --- | --- |
| Classic `<script src>` | Có thể tải no-CORS nếu không có `crossorigin` | Script có thể thực thi; lỗi chi tiết cross-origin bị giới hạn |
| Module `<script type="module">` | Dùng CORS | Server phải cho phép origin tải module |
| `<link rel="stylesheet">` | Stylesheet có thể được áp dụng cross-origin | Đọc CSSOM bị giới hạn nếu không có CORS phù hợp |
| `<img>` | Thường no-CORS mặc định | Có thể hiển thị; canvas bị taint nếu không có CORS |
| `<audio>`, `<video>` | Có thể tải media cross-origin | CORS cần thiết cho một số thao tác đọc/đưa frame vào canvas |
| `<link rel="preload">` | Mode phụ thuộc loại tài nguyên và thuộc tính `crossorigin` | Mode preload cần khớp với request sử dụng sau |
| Font qua `@font-face` | Thường yêu cầu CORS cross-origin | Font server phải trả CORS header |
| Fetch/XHR | CORS mode theo mặc định | Cần server opt-in để JavaScript đọc response |
| Worker | Script worker phải thỏa quy tắc same-origin/CORS theo loại worker và cách tạo | Không giả định worker cross-origin giống ảnh hoặc classic script |

Không suy luận request mode chỉ từ hostname. Kiểm tra element, thuộc tính, initiator và request trong Network.

## 6. Classic script và module script

Classic script:

```html
<script src="https://cdn.example.net/library.js"></script>
```

Classic script cross-origin có thể được tải và thực thi mà không cần CORS header khi không bật CORS mode. Tuy nhiên, browser thường hạn chế thông tin lỗi chi tiết được đưa tới trang gọi; nhiều lỗi chỉ hiện dạng tổng quát như `Script error.`.

Có thể bật CORS mode bằng thuộc tính:

```html
<script
  src="https://cdn.example.net/library.js"
  crossorigin="anonymous"
></script>
```

Khi đó CDN phải trả CORS header phù hợp. Lợi ích gồm nhận thông tin lỗi chi tiết hơn và đáp ứng yêu cầu CORS của một số cơ chế như SRI cross-origin.

Module script luôn dùng CORS:

```html
<script type="module" src="https://cdn.example.net/app.mjs"></script>
```

Nếu CDN không trả `Access-Control-Allow-Origin` cho module, browser chặn module dù URL có thể truy cập trực tiếp trong tab. Các import tiếp theo của module graph cũng phải thỏa quy tắc tải module.

## 7. Stylesheet, font và CSSOM

Stylesheet cross-origin có thể được tải và áp dụng cho trang mà không cần JavaScript đọc nội dung CSS. Tuy nhiên, truy cập quy tắc CSS qua CSSOM có thể bị giới hạn:

```js
const sheet = document.querySelector("link[rel=stylesheet]").sheet;

try {
  console.log(sheet.cssRules);
} catch (error) {
  console.error("Không được đọc CSSOM cross-origin", error);
}
```

Nếu cần đọc CSSOM cross-origin, stylesheet phải được tải theo CORS mode và server trả CORS header phù hợp.

Font cross-origin thường cần CORS. Ví dụ:

```css
@font-face {
  font-family: "BrandFont";
  src: url("https://fonts.example.net/brand.woff2") format("woff2");
  font-display: swap;
}
```

Font host cần cấu hình ACAO phù hợp cho origin của trang. Nếu font không tải được, browser có thể dùng font fallback và ghi lỗi trong Console.

## 8. Ảnh, canvas và thuộc tính crossorigin

Ảnh cross-origin có thể hiển thị mà không cần CORS:

```html
<img id="photo" src="https://images.example.net/photo.jpg" alt="Ảnh">
```

Nhưng khi vẽ lên canvas, canvas bị taint nếu ảnh không được tải theo CORS thành công. Các thao tác đọc pixel như `getImageData()` hoặc xuất dữ liệu canvas có thể bị chặn.

Để dùng ảnh trong canvas có thể đọc:

```html
<img
  id="photo"
  src="https://images.example.net/photo.jpg"
  crossorigin="anonymous"
  alt="Ảnh"
>
```

Server ảnh phải trả CORS header, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Hoặc dùng wildcard nếu tài nguyên thực sự công khai và không cần credentials:

```http
Access-Control-Allow-Origin: *
```

Không đặt `crossorigin="anonymous"` rồi giả định browser tự cấp quyền. Thuộc tính này yêu cầu CORS; server vẫn phải opt-in.

## 9. Thuộc tính crossorigin có những giá trị nào?

Thuộc tính `crossorigin` điều khiển CORS settings attribute của một số HTML element.

| Giá trị | Request mode | Credentials mode |
| --- | --- | --- |
| Không có thuộc tính | Phụ thuộc loại element; nhiều resource dùng no-CORS | Phụ thuộc loại element |
| `anonymous` hoặc giá trị rỗng | CORS | `same-origin` |
| `use-credentials` | CORS | `include` |

Ví dụ:

```html
<script
  src="https://cdn.example.net/app.js"
  crossorigin="anonymous"
></script>

<img
  src="https://images.example.net/avatar.png"
  crossorigin="use-credentials"
  alt="Avatar"
>
```

Với `anonymous`, cross-origin request không gửi credentials theo chế độ include; same-origin request vẫn có thể dùng credentials theo quy tắc same-origin. Với `use-credentials`, request CORS có thể gửi credentials cross-origin và server phải trả origin cụ thể cùng `Access-Control-Allow-Credentials: true`.

Chỉ dùng `use-credentials` khi thật sự cần cookie hoặc HTTP authentication cross-origin. Credentials làm tăng yêu cầu bảo vệ CSRF và quyền riêng tư.

## 10. CORS response headers

Server tài nguyên dùng các response header CORS để opt-in:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Các header thường gặp:

| Header | Ý nghĩa |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép đọc response |
| `Access-Control-Allow-Credentials` | Cho phép response được chia sẻ với credentialed request khi giá trị là `true` |
| `Access-Control-Allow-Methods` | Method được phép trong preflight |
| `Access-Control-Allow-Headers` | Request header được phép trong preflight |
| `Access-Control-Expose-Headers` | Response header bổ sung mà JavaScript được phép đọc |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight |
| `Vary: Origin` | Báo cache rằng response có thể khác theo request Origin |

ACAO thường chứa một origin cụ thể hoặc wildcard `*`; nó không phải danh sách origin phân tách bằng dấu phẩy. Nếu server hỗ trợ nhiều origin, server phải xác minh Origin request với allowlist rồi trả lại đúng một origin được phép.

Ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Khi request có credentials, browser không chấp nhận `Access-Control-Allow-Origin: *`. Server phải trả origin cụ thể và `Access-Control-Allow-Credentials: true`.

## 11. Simple request và preflight

Một số CORS request có thể được gửi trực tiếp nếu đáp ứng điều kiện simple request. Các request có method, header hoặc Content-Type ngoài tập safelisted thường cần preflight.

Ví dụ request JSON với custom header:

```js
fetch("https://api.example.net/orders", {
  method: "PUT",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-123",
  },
  body: JSON.stringify({ status: "confirmed" }),
});
```

Browser có thể gửi preflight:

```http
OPTIONS /orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-request-id
```

Server trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: PUT
Access-Control-Allow-Headers: Content-Type, X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin
```

Sau khi preflight thành công, browser mới gửi actual request. Nếu preflight thất bại, actual request không được gửi theo flow CORS đó.

Đừng nhầm preflight với authentication. Endpoint OPTIONS cần trả policy CORS phù hợp; actual request vẫn phải xác thực và phân quyền độc lập.

## 12. CORS không phải cơ chế ngăn server nhận request

Với một số simple request, browser có thể gửi actual request trước khi biết response có được phép chia sẻ cho JavaScript hay không. Nếu CORS check thất bại, JavaScript không đọc được response, nhưng request có thể đã tới server và hành động có thể đã xảy ra.

Vì vậy:

- CORS không thay CSRF token.
- CORS không thay SameSite cookie.
- CORS không thay authorization.
- CORS không phải firewall chống request từ command-line client hoặc server khác.
- CORS không ngăn người dùng truy cập URL trực tiếp.

Nếu endpoint thay đổi trạng thái, hãy dùng method phù hợp, CSRF protection cho cookie-based session, xác minh Origin/Fetch Metadata khi thích hợp và kiểm tra authorization ở server.

## 13. Credentials và CORS

Fetch có thể gửi credentials theo cấu hình:

```js
const response = await fetch("https://api.example.net/profile", {
  credentials: "include",
});
```

Khi credentials được gửi cross-origin, server cần:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không thể kết hợp credentialed CORS response với wildcard ACAO. Ngoài ra, cookie vẫn chịu các thuộc tính Secure, HttpOnly, SameSite, Domain, Path và chính sách third-party cookie của browser.

Credentials mode `include` không đảm bảo cookie chắc chắn được gửi; cookie policy và browser privacy controls vẫn có hiệu lực. Không dùng CORS để thay thế thiết kế session an toàn.

## 14. Subresource Integrity (SRI) cho tài nguyên cross-origin

SRI cho phép browser kiểm tra nội dung của script hoặc stylesheet có khớp hash được khai báo trong HTML hay không. Điều này hữu ích khi tải thư viện tĩnh từ CDN:

```html
<script
  src="https://cdn.example.net/library-4.2.0.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"
></script>
```

`BASE64_DIGEST` là placeholder; phải thay bằng digest thực được tạo từ đúng file phát hành.

Với tài nguyên cross-origin, SRI yêu cầu request CORS-enabled và server phải trả CORS header cho phép. Thuộc tính `crossorigin="anonymous"` thường được dùng để bật CORS request không gửi credentials cross-origin.

Nếu CDN không trả ACAO phù hợp, browser không thể hoàn tất kiểm tra SRI cross-origin và script/stylesheet bị chặn. Chỉ thêm thuộc tính `integrity` mà không cấu hình CORS ở CDN là chưa đủ.

SRI hỗ trợ thuật toán SHA-256, SHA-384 và SHA-512. Dùng hash được tạo từ artifact đã kiểm chứng; không tự gõ digest và không lấy hash từ một nguồn chưa xác minh.

## 15. Tạo và duy trì SRI hash

Hash phải tương ứng chính xác với nội dung tài nguyên được phát hành. Ví dụ tạo hash SHA-384 bằng OpenSSL:

```bash
openssl dgst -sha384 -binary library.min.js | openssl base64 -A
```

Sau đó thêm tiền tố thuật toán:

```text
sha384-<base64-digest>
```

Quy trình build/deploy nên:

1. Lấy package từ nguồn tin cậy và khóa phiên bản dependency.
2. Kiểm tra artifact hoặc package theo quy trình supply-chain của dự án.
3. Tạo hash từ đúng file sẽ được CDN phục vụ.
4. Ghi hash vào HTML/template/manifest cùng phiên bản.
5. Kiểm thử browser tải tài nguyên và xác minh SRI thành công.
6. Khi nâng cấp thư viện, cập nhật URL và hash trong cùng một thay đổi đã review.

Nếu nội dung file thay đổi dù chỉ một byte, hash có thể không khớp và browser chặn tài nguyên. Đây là hành vi mong muốn khi CDN hoặc đường phân phối trả nội dung khác artifact đã được duyệt.

## 16. SRI không thay thế CORS hoặc CSP

Ba cơ chế trả lời ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| CSP | Document được phép tải script từ nguồn nào? |
| CORS | Server có cho origin này đọc response không? |
| SRI | Nội dung script/stylesheet tải về có khớp hash mong đợi không? |

Ví dụ policy:

```http
Content-Security-Policy: script-src 'self' https://cdn.example.net
```

Policy cho phép nguồn CDN, nhưng không xác minh nội dung CDN. SRI bổ sung kiểm tra nội dung:

```html
<script
  src="https://cdn.example.net/library.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"
></script>
```

CORS cho phép browser thực hiện việc tải cross-origin theo mode cần thiết cho SRI. Nếu thiếu một trong các điều kiện, script có thể bị chặn.

SRI cũng không bảo vệ khỏi trường hợp attacker kiểm soát cả HTML và integrity metadata, ví dụ compromise server phát hành ứng dụng. Vì vậy, bảo vệ build pipeline, deploy credentials và origin HTML vẫn rất quan trọng.

## 17. CORP và COEP trong resource loading

CORP là response header của tài nguyên:

```http
Cross-Origin-Resource-Policy: same-origin
```

Các giá trị chính:

- `same-origin`: chỉ cho phép cùng origin dùng tài nguyên trong ngữ cảnh CORP áp dụng.
- `same-site`: cho phép cùng site.
- `cross-origin`: cho phép cross-origin.

CORP chủ yếu được kiểm tra với request no-CORS. Nó không cho JavaScript đọc response; việc đó vẫn cần CORS.

COEP trên document:

```http
Cross-Origin-Embedder-Policy: require-corp
```

yêu cầu tài nguyên cross-origin opt-in phù hợp:

- Resource tải theo CORS mode cần vượt qua CORS check.
- Resource tải theo no-CORS cần CORP cho phép trong ngữ cảnh đó.

Khi bật COEP, hãy kiểm kê ảnh, script, font, media, worker và tài nguyên bên thứ ba. Một resource trước đây hiển thị được có thể bị chặn nếu server của nó chưa opt-in.

COEP `credentialless` có hành vi khác với `require-corp` đối với một số request no-CORS cross-origin và credentials; chỉ chọn sau khi kiểm tra browser support và tác động tới cookie/authentication.

## 18. CSP source policy và resource origin

CSP giới hạn nguồn mà document được phép tải:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.net; img-src 'self' https://images.example.net; font-src 'self' https://fonts.example.net; connect-src 'self' https://api.example.net
```

Các directive thường dùng:

| Directive | Resource |
| --- | --- |
| `script-src` | Script |
| `style-src` | Stylesheet |
| `img-src` | Ảnh |
| `font-src` | Font |
| `media-src` | Audio/video |
| `connect-src` | Fetch, XHR, WebSocket và kết nối liên quan |
| `worker-src` | Worker/service worker theo phạm vi CSP |
| `frame-src` | Frame mà document tải |

CSP allowlist không thay CORS. Cho phép một origin trong `connect-src` không làm server tự trả ACAO; JavaScript vẫn cần CORS để đọc response. Tương tự, `img-src` cho phép browser tải ảnh nhưng không tự làm canvas sạch taint.

Không thêm mọi CDN vào `default-src` chỉ để sửa lỗi. Hãy dùng directive hẹp cho từng loại tài nguyên.

## 19. Preload và crossorigin consistency

Resource hint có thể tải tài nguyên trước khi parser tới element sử dụng. Nếu preload và request thật dùng mode/credentials khác nhau, browser có thể không tái sử dụng response đã tải hoặc phát sinh request thừa.

Ví dụ preload module/script:

```html
<link
  rel="preload"
  href="https://cdn.example.net/app.js"
  as="script"
  crossorigin="anonymous"
>

<script
  src="https://cdn.example.net/app.js"
  crossorigin="anonymous"
></script>
```

Hãy giữ thuộc tính `crossorigin` và credentials mode nhất quán giữa preload và element sử dụng. Với font cross-origin:

```html
<link
  rel="preload"
  href="https://fonts.example.net/brand.woff2"
  as="font"
  type="font/woff2"
  crossorigin
>
```

Font preload thường cần thuộc tính crossorigin để request mode phù hợp với cách font được tải.

## 20. Cache, CDN và Vary: Origin

Nếu server phản hồi CORS dựa trên request Origin, response có thể khác theo origin. Cache trung gian cần biết điều đó:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cache-Control: public, max-age=3600
```

Nếu CDN bỏ qua `Vary: Origin` hoặc cache key không tính Origin trong cấu hình riêng, response chứa ACAO của một origin có thể bị phát cho origin khác. Điều này gây lỗi CORS hoặc mở rộng chia sẻ ngoài dự kiến.

Các điểm cần kiểm tra:

- CDN có giữ nguyên ACAO, ACAC và Vary không?
- Response 200 và 304 có header nhất quán không?
- Có nhiều origin trong allowlist và server phản chiếu đúng một origin không?
- Cache key có được cấu hình tương ứng với Origin không?
- Preflight response có cache lifetime phù hợp không?
- Khi thay đổi allowlist, cache cũ đã được purge hoặc hết TTL chưa?

Không dùng `Vary: Origin` như thay thế cấu hình cache key nếu CDN có quy tắc cache riêng.

## 21. Chọn chiến lược theo loại tài nguyên

| Tình huống | Cách tải phù hợp | Kiểm soát cần có |
| --- | --- | --- |
| Thư viện JS public từ CDN | Classic script hoặc module theo yêu cầu ứng dụng | CSP; SRI; CORS nếu dùng module/SRI cross-origin |
| Font từ font CDN | CSS `@font-face` | CORS trên font response; CSP `font-src` |
| Ảnh public | `img` no-CORS nếu chỉ hiển thị | CSP `img-src`; CORP nếu cần giới hạn no-CORS embedding |
| Ảnh cần đọc pixel canvas | `img crossorigin="anonymous"` | CORS ACAO từ image host |
| API dữ liệu | Fetch CORS | ACAO allowlist; credentials policy; authorization; CSRF nếu cookie session |
| Stylesheet cần đọc CSSOM | Stylesheet CORS-enabled | `crossorigin` và ACAO |
| Video dùng trong canvas | Media CORS-enabled khi cần đọc frame | `crossorigin` và CORS ở media host |
| Resource trong COEP require-corp | CORS mode hoặc no-CORS có CORP opt-in | CORS hoặc CORP đúng theo request mode |

Không bật credentials cho resource công khai nếu không cần. Không dùng `cross-origin` CORP cho response riêng tư chỉ để làm tích hợp hoạt động.

## 22. Ví dụ triển khai: CDN cho script và font

Giả sử ứng dụng tại `https://app.example.com` dùng thư viện và font từ CDN.

HTML:

```html
<script
  src="https://cdn.example.net/vendor-4.2.0.min.js"
  integrity="sha384-BASE64_DIGEST"
  crossorigin="anonymous"
></script>

<link
  rel="stylesheet"
  href="https://cdn.example.net/theme.css"
  crossorigin="anonymous"
>
```

Response script/style từ CDN có thể trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cross-Origin-Resource-Policy: cross-origin
```

CORP có ý nghĩa cho request no-CORS; trong ví dụ CORS-enabled, CORS check là cơ chế cho phép tải/đọc theo mode tương ứng. Nếu CDN phục vụ công khai cho mọi website và không dùng credentials, có thể cân nhắc ACAO wildcard.

CSP document:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.net; style-src 'self' https://cdn.example.net; font-src 'self' https://fonts.example.net; object-src 'none'; base-uri 'self'
```

Đảm bảo:

- Digest SRI khớp chính xác artifact script.
- CDN trả CORS header cho các request CORS-enabled.
- Font host trả ACAO phù hợp.
- CSP chỉ cho phép host cần thiết.
- Phiên bản file và hash được cập nhật đồng bộ trong deploy.

## 23. Kiểm thử cross-origin resource bằng DevTools

Thực hiện trong môi trường lab/staging với hai origin do bạn kiểm soát, ví dụ `https://app.example.test` và `https://cdn.example.test`. Không dùng token hoặc dữ liệu riêng tư.

### Bước 1 — Tạo resource cross-origin

Phục vụ một ảnh, một script và một JSON response từ origin CDN thử nghiệm. Ghi nhận Content-Type và response header.

### Bước 2 — Thử no-CORS

Tải ảnh bằng `<img>` không có thuộc tính crossorigin. Xác minh ảnh có thể hiển thị nhưng canvas bị taint nếu vẽ ảnh vào canvas và đọc pixel.

### Bước 3 — Thử CORS mode

Thêm `crossorigin="anonymous"` cho ảnh và ACAO phù hợp ở server. Vẽ lại lên canvas và thử `getImageData()`. Sau đó bỏ ACAO để quan sát browser chặn CORS-enabled request.

### Bước 4 — Thử Fetch

Dùng Fetch mặc định để đọc JSON. Kiểm tra preflight nếu request dùng method/header không safelisted. Thử sai origin và xác minh JavaScript không đọc được response.

### Bước 5 — Thử SRI

Thêm `integrity` và `crossorigin="anonymous"` vào script CDN. Dùng digest đúng để xác nhận script tải thành công; sau đó dùng digest sai trong lab để quan sát browser chặn thực thi.

### Bước 6 — Thử CORP/COEP

Thêm CORP `same-origin` cho resource rồi thử tải no-CORS từ app origin khác. Bật COEP `require-corp` trên document lab và kiểm tra resource nào bị chặn do thiếu CORS/CORP opt-in.

### Bước 7 — Kiểm tra Network

Với từng request, xem:

- Initiator và element/API khởi tạo.
- Request mode/credentials nếu DevTools hiển thị.
- Request Origin và preflight OPTIONS.
- Response ACAO, ACAC, Vary, CORP.
- CSP/COEP của document.
- Console message và trạng thái SRI.

Đừng chỉ kiểm tra URL mở trực tiếp trong tab; hãy kiểm tra request được khởi tạo từ document thật vì mode và policy có thể khác.

## 24. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Module script cross-origin bị chặn | Thiếu ACAO hoặc origin không được cho phép | Cấu hình CORS trên module host |
| Classic script chạy nhưng lỗi chỉ hiện `Script error.` | Script được tải no-CORS | Dùng crossorigin và CORS header nếu cần error detail |
| Ảnh hiển thị nhưng canvas không đọc được | Ảnh tải no-CORS làm canvas taint | Dùng crossorigin anonymous và ACAO |
| Font không tải | Font cross-origin thiếu CORS | Thêm ACAO đúng ở font server |
| Fetch trả lỗi CORS | ACAO thiếu/sai, credentials wildcard hoặc preflight thất bại | Kiểm tra request/response và OPTIONS |
| Fetch no-CORS trả status 0 | Opaque response | Dùng CORS mode và server opt-in nếu cần đọc |
| SRI script CDN bị chặn | Hash sai hoặc cross-origin request thiếu CORS | Kiểm tra artifact/hash và crossorigin/ACAO |
| Preload tải hai lần | Mode/credentials của preload khác request thật | Đồng bộ crossorigin và thuộc tính resource |
| Resource bị chặn sau khi bật COEP | Thiếu CORS hoặc CORP opt-in | Kiểm tra request mode và response policy |
| CDN trả ACAO của origin khác | Cache không vary theo Origin | Cấu hình Vary/cache key và purge cache |
| CSP chặn dù CORS đúng | Origin chưa nằm trong directive CSP phù hợp | Sửa CSP theo loại resource; CORS vẫn giữ riêng |

## 25. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Cross-origin resource luôn bị chặn.” | Nhiều loại resource có thể được tải; quyền đọc response phụ thuộc mode và policy. |
| “no-CORS giúp đọc API không có CORS.” | Fetch no-CORS trả opaque response, không cho đọc body/status/headers. |
| “CORS là cơ chế authorization.” | CORS kiểm soát browser chia sẻ response với JavaScript; server vẫn phải xác thực và phân quyền. |
| “Ảnh hiển thị được thì canvas đọc được.” | Ảnh no-CORS có thể hiển thị nhưng làm canvas taint. |
| “Classic script và module script tải giống nhau.” | Module dùng CORS; classic script có thể tải no-CORS nếu không bật crossorigin. |
| “SRI tự cho phép tải CDN.” | SRI kiểm tra nội dung; cross-origin SRI còn cần CORS-enabled request và ACAO phù hợp. |
| “CORP cho JavaScript đọc response.” | CORS mới cho phép JavaScript đọc response cross-origin. |
| “CSP allowlist thay CORS.” | CSP giới hạn nguồn document được tải; CORS quyết định response có được chia sẻ cho script. |
| “crossorigin anonymous gửi cookie cross-origin.” | Anonymous dùng credentials mode same-origin; use-credentials mới yêu cầu include. |
| “URL CDN mở trực tiếp được thì script chắc chắn tải được.” | Request mode, CSP, CORS, SRI, COEP và MIME có thể làm kết quả khác. |

## 26. Checklist triển khai cross-origin resource

- Lập danh sách origin cung cấp script, style, font, image, media, API và worker.
- Phân biệt same-origin, same-site và cross-origin; không dùng site làm thay thế origin allowlist.
- Xác định request mode của từng element/API; không dùng no-CORS để né CORS.
- Dùng CORS allowlist chính xác cho API và resource mà JavaScript cần đọc.
- Không kết hợp credentialed CORS với ACAO wildcard; dùng ACAC và origin cụ thể.
- Thêm `Vary: Origin` và cấu hình cache/CDN tương ứng khi response phụ thuộc Origin.
- Dùng `crossorigin` đúng với nhu cầu; tránh use-credentials nếu không cần.
- Dùng SRI cho script/stylesheet tĩnh từ CDN; xác minh hash từ artifact đã kiểm chứng.
- Với SRI cross-origin, bật CORS request và cấu hình ACAO trên CDN.
- Dùng CORP cho resource no-CORS cần giới hạn; chọn same-origin/same-site/cross-origin theo trust boundary.
- Khi bật COEP, kiểm kê và opt-in mọi resource cross-origin bằng CORS hoặc CORP phù hợp.
- Dùng CSP directive riêng như script-src, style-src, img-src, font-src và connect-src.
- Kiểm tra MIME type, redirect, cache, preload mode và browser support.
- Bảo vệ API bằng authentication, authorization và CSRF controls độc lập.
- Kiểm thử bằng Network/Console trên browser mục tiêu và response thực tế sau CDN.

## 27. Câu hỏi tự kiểm tra

1. Cross-origin được xác định bằng những thành phần nào của URL?
2. Vì sao cross-origin không đồng nghĩa cross-site?
3. no-CORS mode cho phép điều gì và giới hạn điều gì?
4. Opaque response có thể đọc status, headers và body không?
5. Classic script và module script khác nhau thế nào về CORS?
6. Vì sao ảnh có thể hiển thị nhưng canvas vẫn bị taint?
7. crossorigin anonymous và use-credentials khác nhau về credentials mode ra sao?
8. Khi nào browser gửi preflight OPTIONS?
9. Vì sao CORS không thay CSRF hoặc authorization?
10. Vì sao SRI cho script cross-origin cần CORS-enabled request?
11. CORP và COEP phối hợp như thế nào?
12. Vì sao preload và request thật cần thống nhất crossorigin?
13. Vai trò của Vary: Origin trong cache là gì?
14. CSP, CORS, CORP và SRI giải quyết những câu hỏi bảo mật khác nhau nào?

**Ghi nhớ:** Cross-origin resource loading phụ thuộc loại tài nguyên, request mode, credentials và policy của browser. Dùng CORS khi JavaScript cần đọc response; dùng CORP/COEP để kiểm soát việc nhúng resource no-CORS; dùng SRI để xác minh nội dung script/stylesheet; và dùng CSP để giới hạn nguồn tải. Thuộc tính crossorigin phải phù hợp với mode và server response. CORS, CORP và SRI đều bổ sung cho authentication, authorization và CSRF protection ở server.
