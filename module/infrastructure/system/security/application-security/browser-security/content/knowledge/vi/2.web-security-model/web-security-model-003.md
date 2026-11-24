# Web document trong mô hình bảo mật web

## 1. Web document là gì?

Một **web document** (tài liệu web) là tài liệu mà trình duyệt tải và biểu diễn trong một ngữ cảnh duyệt, thường bắt đầu từ một phản hồi HTML. Khi trình duyệt phân tích HTML, nó tạo một đối tượng `Document` và cây **DOM (Document Object Model)** để JavaScript có thể đọc hoặc thay đổi nội dung trang. Tài liệu cũng có thể nhúng CSS, hình ảnh, script và các tài liệu khác qua `iframe`.

Trong bảo mật ứng dụng web, document là một ranh giới quan trọng: mã chạy trong document được trình duyệt kiểm soát theo **origin** của tài liệu, các chính sách cách ly và quyền mà ứng dụng cấp. Việc hiểu ranh giới này là nền tảng để giải thích Same-Origin Policy (SOP), CORS, XSS, CSRF, clickjacking, CSP, Trusted Types và security headers.

Sơ đồ khái niệm:

```text
URL + HTTP response
  ├─ Response headers (CSP, cookie, frame-ancestors, ...)
  └─ HTML ──trình phân tích──> Document / DOM
                               │
                               ├─ Window: môi trường chạy JavaScript
                               ├─ Origin: ranh giới truy cập giữa các tài liệu
                               ├─ Tài nguyên: CSS, ảnh, script, fetch, ...
                               └─ iframe ──> Document khác (có thể khác origin)
```

**Mục tiêu sau bài học:** phân biệt `Document`, `Window`, DOM và origin; dự đoán tài liệu nào có thể truy cập lẫn nhau; hiểu giới hạn của SOP/CORS; và chọn biện pháp phòng vệ phù hợp khi tài liệu xử lý dữ liệu hoặc nội dung không tin cậy.

## 2. Các thành phần và vòng đời của document

| Khái niệm | Vai trò | Ý nghĩa bảo mật |
| --- | --- | --- |
| **Document** | Đại diện tài liệu đã tải, chứa DOM và các API như `querySelector`, `createElement`. | Script được phép thao tác DOM của document mà nó có quyền truy cập. |
| **Window** | Môi trường toàn cục cho script của một tài liệu; cung cấp `location`, `history`, `parent`, `top`. | Tham chiếu đến window khác không đồng nghĩa với quyền đọc DOM của window đó. |
| **Ngữ cảnh duyệt** | Vùng hiển thị tài liệu: tab/cửa sổ ở cấp cao nhất hoặc `iframe` lồng nhau. | Mỗi `iframe` có thể chứa một document với origin riêng. |
| **DOM** | Cấu trúc nút được dựng từ HTML và thay đổi lúc chạy. | Chèn dữ liệu không tin cậy vào các vị trí thực thi HTML/JavaScript có thể gây XSS. |
| **HTTP response** | Chứa nội dung và header được máy chủ trả về. | Nhiều chính sách, như CSP `frame-ancestors`, phải được gửi bằng response header. |

Quy trình điển hình:

1. Người dùng điều hướng tới một URL; trình duyệt yêu cầu tài nguyên, xử lý chuyển hướng và nhận phản hồi.
2. Trình duyệt xác định origin của document được tải, áp dụng các chính sách từ response header rồi phân tích HTML để tạo DOM.
3. Script được cho phép chạy trong môi trường của document. Script có thể gọi API DOM, gửi yêu cầu mạng hoặc giao tiếp với document khác theo các quy tắc bảo mật.
4. Khi điều hướng sang trang khác, tài liệu mới được nạp; origin và quyền phải được đánh giá theo **document mới**. Không được giả định một `iframe` hay cửa sổ giữ nguyên nguồn gốc sau điều hướng.

Ví dụ:

```html
<!doctype html>
<html lang="vi">
  <head><meta charset="utf-8"><title>Trang hồ sơ</title></head>
  <body>
    <h1 id="title">Hồ sơ người dùng</h1>
    <script>
      // Chạy trong môi trường Window của document hiện tại.
      document.querySelector("#title").textContent = "Hồ sơ đã tải";
      console.log(location.origin);
    </script>
  </body>
</html>
```

Đoạn script có quyền sửa phần tử `#title` vì nó chạy trong chính document này. Nếu thay script bằng một tệp JavaScript tải từ máy chủ bên thứ ba qua `<script src="...">`, script ấy **vẫn chạy với quyền của document nhúng nó**, chứ không tự động bị cách ly theo origin của nơi lưu tệp. Đây là lý do cần kiểm soát script bên thứ ba và ngăn XSS.

## 3. Origin và site: hai khái niệm không thể hoán đổi

Với URL HTTP(S) thông thường, **origin** được xác định bằng bộ ba:

```text
origin = (scheme, host, port)
Ví dụ: https://app.example.com:443
```

Port mặc định của HTTPS là `443` và của HTTP là `80`. Vì vậy `https://app.example.com` và `https://app.example.com:443` có cùng origin. Đường dẫn, query string và fragment không tham gia xác định origin.

Giả sử document hiện tại có origin `https://app.example.com`:

| URL đích | Cùng origin? | Giải thích |
| --- | --- | --- |
| `https://app.example.com/profile` | Có | Cùng scheme, host và port. |
| `https://api.example.com/data` | Không | Host khác, dù thuộc cùng miền đăng ký. |
| `http://app.example.com/` | Không | Scheme HTTP khác HTTPS. |
| `https://app.example.com:8443/` | Không | Port khác. |
| `https://example.net/` | Không | Host khác. |

**Site** là khái niệm dùng nhiều trong ngữ cảnh cookie và chống CSRF. Với cách tính *schemeful same-site* của trình duyệt hiện đại, site dựa vào scheme và miền đăng ký (registrable domain, ví dụ `example.com`); subdomain và port thường không làm thay đổi site. Do đó:

- `https://app.example.com` và `https://api.example.com`: **khác origin, cùng site**.
- `https://app.example.com` và `http://app.example.com`: **khác origin, khác site** vì khác scheme.
- `https://app.example.com` và `https://example.net`: **khác origin, khác site**.

Không nên dùng “same-site” để kết luận hai trang được phép đọc DOM lẫn nhau. **SOP xét origin; cookie `SameSite` xét site.**

Một số document có origin đặc biệt:

- `about:blank` và `iframe srcdoc` thông thường thừa hưởng origin từ tài liệu tạo/nhúng chúng; không nên coi chúng mặc nhiên là vùng cách ly.
- Document tại URL `data:` thường nhận **opaque origin** (origin duy nhất, không bằng origin của trang tạo ra nó).
- `iframe` có `sandbox` nhưng thiếu quyền `allow-same-origin` cũng được gán opaque origin. Khi biểu diễn dưới dạng chuỗi, opaque origin thường xuất hiện là `"null"`; đây **không phải** tên miền đáng tin cậy.

Origin không phải phạm vi cookie. Cookie có quy tắc riêng theo domain, path, `Secure`, `HttpOnly` và `SameSite`; port không dùng để phân vùng cookie. Ngược lại, `localStorage` về cơ bản bị phân tách theo origin. Vì vậy hai ứng dụng chạy cùng host ở hai port có thể khác origin nhưng vẫn phải cẩn thận với cookie được gửi tới host đó.

## 4. Same-Origin Policy bảo vệ tài liệu như thế nào?

**Same-Origin Policy (SOP)** là cơ chế cách ly mặc định của trình duyệt, giới hạn khả năng một document đọc và thao tác dữ liệu của document hoặc phản hồi mạng thuộc origin khác.

Ví dụ trang `https://app.example.com` nhúng:

```html
<iframe id="reports" src="https://reports.example.net/"></iframe>
```

Mã chạy ở document cha có thể giữ tham chiếu `iframe.contentWindow` để dùng một số API liên cửa sổ được cho phép. Nhưng nó **không thể đọc DOM** của document bên trong `iframe` khác origin:

```javascript
const frame = document.querySelector("#reports");

// Khi iframe đã tải một document khác origin:
console.log(frame.contentDocument); // null

// Cố đọc nội dung qua Window có thể ném SecurityError.
console.log(frame.contentWindow.document.body.textContent);
```

Điều này cũng áp dụng theo chiều ngược lại: document trong `iframe` khác origin không được tự do đọc DOM cha. SOP không có nghĩa “mọi tương tác cross-origin đều bị cấm”:

| Hoạt động | Hành vi tổng quát |
| --- | --- |
| Đọc/sửa DOM của document cùng origin | Thường được phép, nếu không có cơ chế cách ly bổ sung. |
| Đọc/sửa DOM của document khác origin | Bị SOP hạn chế. |
| Nhúng hình ảnh, stylesheet, một số script hoặc `iframe` từ origin khác | Nhiều hình thức được phép theo mặc định, nhưng CSP, CORS, CORP hoặc chính sách nhúng có thể giới hạn. |
| Gửi biểu mẫu hoặc một số yêu cầu cross-origin | Có thể xảy ra; máy chủ vẫn phải tự xác thực và chống CSRF. |
| Đọc nội dung phản hồi `fetch`/XHR cross-origin | Cần server cho phép bằng CORS (hoặc một cơ chế được thiết kế riêng). |
| Trao đổi dữ liệu giữa hai cửa sổ khác origin | Có thể dùng `postMessage` và kiểm tra nguồn gửi. |

Một điểm dễ nhầm: SOP bảo vệ việc **đọc dữ liệu từ trình duyệt**, không biến máy chủ thành hệ thống phân quyền. Kẻ tấn công vẫn có thể gửi HTTP request ngoài trình duyệt; phía server phải kiểm tra quyền ở mọi endpoint.

### SOP khác CORS ra sao?

SOP đặt ra giới hạn mặc định. **Cross-Origin Resource Sharing (CORS)** là giao thức header HTTP cho phép server khai báo origin nào được JavaScript trên trình duyệt **đọc phản hồi cross-origin**.

Giả sử frontend tại `https://app.example.com` gọi API tại `https://api.example.com`:

```javascript
fetch("https://api.example.com/me", {
  credentials: "include"
}).then(response => response.json());
```

Với request có kèm thông tin xác thực, phản hồi hợp lệ để JavaScript frontend đọc thường cần các header như:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Server không thể dùng `Access-Control-Allow-Origin: *` cho phản hồi đọc với `credentials: "include"`. Trình duyệt có thể gửi một yêu cầu *preflight* (OPTIONS) trước những request không thuộc nhóm “simple”, nhưng **không phải mọi request cross-origin đều có preflight**. Việc request đã được gửi hoặc cookie đã được đính kèm còn phụ thuộc quy tắc credentials và cookie; CORS không thay thế xác thực, phân quyền hay chống CSRF.

## 5. Iframe, sandbox và biên giới tin cậy

`iframe` nhúng một document vào bên trong document khác. Đây là cách hữu ích để tách giao diện bên thứ ba, nhưng cần xác định chính xác quyền được cấp:

```html
<!-- Mặc định sandbox chặn script và nhiều khả năng khác;
     nội dung nhúng cũng nhận opaque origin. -->
<iframe
  title="Bản xem trước nội dung"
  sandbox=""
  srcdoc="<h1>Nội dung xem trước</h1>">
</iframe>
```

Thuộc tính `sandbox` chỉ mở dần quyền khi thêm các token `allow-*`, ví dụ `allow-scripts` hoặc `allow-forms`. Cấp `allow-same-origin` làm cho nội dung không bị ép về opaque origin. **Không kết hợp `allow-scripts` với `allow-same-origin` cho nội dung cùng origin không tin cậy**: nội dung có thể lấy lại nhiều quyền và làm suy yếu mục đích sandbox.

Cần phân biệt hai hướng điều khiển:

- **Trang chủ động nhúng** quyết định dùng `sandbox` và những quyền iframe được cấp.
- **Trang bị nhúng** có thể dùng response header `Content-Security-Policy: frame-ancestors ...` để quyết định origin nào được phép nhúng mình, qua đó giảm clickjacking.

Nếu cần nhận dữ liệu từ tài liệu khác origin, hãy thiết kế thông điệp rõ ràng, có kiểm tra nguồn. Không tắt giới hạn origin để “cho iframe hoạt động”.

## 6. Giao tiếp có kiểm soát bằng postMessage

`window.postMessage` cho phép gửi dữ liệu giữa document cha, `iframe` hoặc cửa sổ khác origin. Bên gửi dùng **`targetOrigin` chính xác**; bên nhận xác minh `event.origin`, `event.source` và cấu trúc dữ liệu.

Ví dụ document cha tại `http://localhost:3000` và iframe tại `http://localhost:4000` (hai origin khác nhau vì port khác):

**Trang cha** (`http://localhost:3000/index.html`):

```html
<iframe id="child" src="http://localhost:4000/child.html"></iframe>
<script>
  const child = document.querySelector("#child");

  child.addEventListener("load", () => {
    // Không đọc DOM khác origin; gửi thông điệp có đích rõ ràng.
    child.contentWindow.postMessage(
      { type: "PING", id: "request-1" },
      "http://localhost:4000"
    );
  });

  window.addEventListener("message", (event) => {
    if (event.origin !== "http://localhost:4000") return;
    if (event.source !== child.contentWindow) return;
    if (event.data?.type !== "PONG" || event.data.id !== "request-1") return;
    console.log("Đã nhận phản hồi hợp lệ từ iframe");
  });
</script>
```

**Trang iframe** (`http://localhost:4000/child.html`):

```html
<script>
  window.addEventListener("message", (event) => {
    if (event.origin !== "http://localhost:3000") return;
    if (event.source !== window.parent) return;
    if (event.data?.type !== "PING" || typeof event.data.id !== "string") return;

    event.source.postMessage(
      { type: "PONG", id: event.data.id },
      event.origin
    );
  });
</script>
```

Ví dụ dùng hostname/port cố định để kiểm chứng tại máy cục bộ. Trong ứng dụng thật, danh sách origin cho phép phải do cấu hình đáng tin cậy xác định. Không kiểm tra bằng cách tìm chuỗi con (ví dụ `origin.includes("example.com")`) vì `example.com.attacker.test` cũng có thể khớp. Không dùng `"*"` làm `targetOrigin` khi thông điệp chứa dữ liệu nhạy cảm, và không đưa thẳng `event.data` vào `innerHTML`.

## 7. Khi document xử lý dữ liệu không tin cậy

Ranh giới của document trở nên đặc biệt quan trọng khi HTML, dữ liệu URL, phản hồi API hoặc thông điệp đến từ bên ngoài được đưa vào DOM.

### XSS: dữ liệu trở thành mã thực thi

Đây là cách chèn dữ liệu URL **không an toàn**:

```javascript
const name = new URLSearchParams(location.search).get("name") ?? "bạn";
document.querySelector("#welcome").innerHTML = "Xin chào, " + name;
```

Kẻ tấn công có thể điều khiển `name` để chèn markup hoặc thuộc tính xử lý sự kiện không mong muốn. Thay bằng API tạo **text node**:

```javascript
const name = new URLSearchParams(location.search).get("name") ?? "bạn";
document.querySelector("#welcome").textContent = "Xin chào, " + name;
```

Khi nghiệp vụ thật sự cần cho phép HTML do người dùng cung cấp, phải dùng bộ lọc HTML được duy trì tốt với chính sách rõ ràng, không tự viết bộ lọc bằng regex. Chú ý cả những “sink” khác như `insertAdjacentHTML`, `document.write`, handler HTML và URL dạng `javascript:`.

**Content Security Policy (CSP)** giúp giới hạn nguồn script và giảm tác động của một số lỗi chèn mã. **Trusted Types** (ở các trình duyệt hỗ trợ) có thể yêu cầu dữ liệu đưa vào các DOM XSS sink phải qua chính sách tạo kiểu tin cậy. Cả hai là lớp phòng vệ bổ sung, không thay cho output encoding và xử lý dữ liệu đúng ngữ cảnh.

### CSRF: trình duyệt mang theo trạng thái xác thực

Một document ở origin khác có thể gây ra một số request tới ứng dụng; trình duyệt có thể tự đính kèm cookie theo quy tắc cookie. Nếu endpoint thay đổi trạng thái chỉ dựa vào cookie và thiếu chống CSRF, người dùng đã đăng nhập có nguy cơ bị yêu cầu thực hiện hành động ngoài ý muốn.

Phòng vệ theo lớp: cookie phiên đặt `Secure`, `HttpOnly`, `SameSite=Lax` hoặc `Strict` tùy luồng; kiểm tra CSRF token hoặc tín hiệu `Origin` phù hợp trên request thay đổi trạng thái; không thay đổi dữ liệu qua GET; server luôn xác minh quyền. `HttpOnly` giảm rủi ro script đọc cookie, **không tự ngăn trình duyệt gửi cookie**.

### Clickjacking: document bị đặt trong khung giả mạo

Kẻ tấn công có thể cố nhúng trang đăng nhập hoặc nút hành động vào một iframe và phủ lớp giao diện đánh lừa người dùng nhấp chuột. Response header sau chặn việc nhúng trang nếu ứng dụng không cần được frame:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Nếu ứng dụng phải được nhúng bởi một số origin, hãy khai báo danh sách cho phép cụ thể trong `frame-ancestors`. Chỉ thị này phải ở **HTTP response header**, không có tác dụng khi đặt trong thẻ `<meta http-equiv>`.

## 8. Security headers và quyền áp dụng cho document

Một cấu hình khởi đầu để thảo luận (cần điều chỉnh theo tài nguyên và luồng thực tế):

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-Frame-Options: DENY
```

| Cơ chế | Mục đích trong mô hình document | Lưu ý |
| --- | --- | --- |
| **CSP** | Giới hạn nguồn script, tài nguyên, khả năng nhúng và một số hành vi của document. | Nonce phải được tạo mới, khó đoán cho từng response; không sao chép `{RANDOM_PER_RESPONSE}` như một giá trị cố định. |
| **Trusted Types** | Giảm việc truyền chuỗi tùy ý vào một số API DOM có khả năng gây XSS. | Có thể dùng CSP `require-trusted-types-for 'script'` ở trình duyệt hỗ trợ; cần kiểm tra tương thích và thiết kế policy. |
| **`frame-ancestors` / X-Frame-Options** | Quy định ai được phép nhúng document. | Giảm clickjacking; `frame-ancestors` là lựa chọn linh hoạt hơn. |
| **`X-Content-Type-Options: nosniff`** | Giảm diễn giải nội dung sai MIME type trong các ngữ cảnh bị ảnh hưởng. | Server vẫn phải trả `Content-Type` đúng. |
| **`Referrer-Policy`** | Kiểm soát mức thông tin URL được gửi trong `Referer`. | Không coi URL chứa token bí mật là nơi lưu trữ an toàn. |
| **Cookie attributes** | Kiểm soát cách cookie được lưu, đọc và gửi trong request. | Không quyết định quyền truy cập DOM; thuộc về chính sách cookie. |

Không phải mọi header đều phù hợp với mọi ứng dụng. Ví dụ `frame-ancestors 'none'` sẽ chặn cả luồng nhúng hợp lệ của sản phẩm; một CSP quá chặt có thể làm hỏng tài nguyên cần thiết. Nên triển khai theo chính sách thiết kế, kiểm tra trên môi trường thử nghiệm và quan sát cảnh báo CSP trước khi áp dụng rộng.

## 9. Bài thực hành: xác minh ranh giới document

Hãy dùng hai local web server phục vụ ví dụ ở mục 6 tại hai cổng `3000` và `4000` (đều dùng `http://localhost`), sau đó mở DevTools ở trang cha.

1. **Dự đoán trước khi chạy:** vì khác port, hai document có cùng origin hay không? Cha có thể đọc `child.contentWindow.document.body` không?
2. **Quan sát SOP:** sau khi iframe tải xong, chạy `document.querySelector("#child").contentDocument` tại console trang cha. Kết quả dự kiến là `null`; truy cập trực tiếp DOM qua `contentWindow.document` bị hạn chế.
3. **Quan sát `postMessage`:** mở console, thấy `PONG` được chấp nhận khi origin, source và payload đúng. Thử đổi `targetOrigin` thành origin không khớp; thông điệp sẽ không được giao như dự kiến.
4. **Kiểm tra tính tin cậy:** sửa điều kiện kiểm tra `event.origin` để giả định tất cả nguồn đều đáng tin và tự giải thích rủi ro. Sau đó khôi phục điều kiện kiểm tra chính xác.
5. **Thử sandbox có chủ đích:** thêm `sandbox="allow-scripts"` vào iframe. Vì iframe lúc này có opaque origin, `event.origin` của thông điệp từ iframe không còn bằng `http://localhost:4000`; bộ kiểm tra của cha sẽ từ chối. Đây là kết quả bảo vệ có chủ ý, không phải lý do để bỏ kiểm tra nguồn.

**Câu hỏi tự kiểm tra:**

- Một script được tải từ CDN khác origin nhưng chạy trong trang của bạn sẽ có quyền DOM của ai?
- Vì sao CORS cho phép đọc phản hồi API không đồng nghĩa API đó đã kiểm tra quyền người dùng?
- Tại sao cùng site nhưng khác origin vẫn bị chặn truy cập DOM?
- Tại sao `iframe srcdoc` không `sandbox` không thể được mặc định xem là vùng an toàn cho HTML không tin cậy?
- Khi gặp XSS, CSRF và clickjacking, cơ chế nào bảo vệ tại DOM, request và khả năng nhúng document tương ứng?

## 10. Tổng kết

**Web document là đơn vị nội dung và môi trường thực thi mà trình duyệt gắn với một origin cùng các chính sách bảo mật.** `Document` biểu diễn DOM, `Window` là môi trường chạy script, còn `iframe` tạo thêm một document với ranh giới riêng. SOP hạn chế đọc chéo origin; CORS cho phép server mở quyền đọc phản hồi mạng có kiểm soát; `postMessage` hỗ trợ truyền thông điệp liên document khi kiểm tra nguồn chặt chẽ.

Một thiết kế an toàn bắt đầu bằng việc xác định **dữ liệu đến từ đâu, được đưa vào document nào, script nào được chạy và hành động nào cần server xác thực**. Từ mô hình đó mới chọn đúng lớp phòng vệ: xử lý DOM an toàn và CSP/Trusted Types cho XSS; token và kiểm tra request cùng cookie cho CSRF; `frame-ancestors` cho clickjacking; sandbox và kiểm tra `postMessage` cho nội dung nhúng.
