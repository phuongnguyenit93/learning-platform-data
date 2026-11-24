# Nonce source — cấp quyền thực thi cho script được server tin cậy

> **Chương:** CSP nâng cao  
> **Mục tiêu:** Hiểu nonce source trong Content Security Policy (CSP), cách tạo nonce khó đoán cho từng response, gắn nonce vào script element, phân biệt nonce với host allowlist và hash, xử lý cache/SSR/CDN, kết hợp `strict-dynamic` và kiểm chứng policy trên browser.

## 1. Nonce source giải quyết vấn đề gì?

Một ứng dụng web thường có một số script inline cần chạy: script khởi tạo ứng dụng, dữ liệu cấu hình được render vào trang hoặc đoạn bootstrap tải module tiếp theo. Nếu policy chỉ cho phép script cùng origin, ứng dụng có thể phải cho phép toàn bộ inline script hoặc nới nguồn script để giữ tính năng hoạt động.

Việc cho phép rộng làm giảm khả năng CSP chặn mã được chèn qua XSS. **Nonce source** cung cấp cách cấp quyền cụ thể hơn: server tạo một giá trị ngẫu nhiên cho response, đưa giá trị đó vào CSP header và gắn cùng giá trị lên những script element được phép chạy.

Ví dụ khái niệm:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_NONCE'
```

```html
<script nonce="RANDOM_NONCE">
  initializeApplication();
</script>
```

Browser chỉ cho phép script element có nonce khớp với nonce-source trong policy. Script inline khác không có nonce hợp lệ sẽ bị chặn.

`RANDOM_NONCE` là placeholder, không phải giá trị để sao chép vào production. Nonce thực tế phải được server sinh bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG), mới cho mỗi response HTML.

## 2. Nonce là gì và browser kiểm tra như thế nào?

Nonce là một giá trị dùng cho response/document hiện tại, đóng vai trò như **dấu cấp quyền cho một phần tử script hoặc style**. Trong CSP, nonce được biểu diễn bằng source expression:

```text
'nonce-{base64-value}'
```

Khi browser gặp script element, nó kiểm tra nonce trên phần tử với nonce-source trong policy đang áp dụng. Nếu khớp và các điều kiện CSP liên quan thỏa, script được phép thực thi.

Nonce có thể áp dụng cho:

- Inline script element.
- External script element có thuộc tính nonce hợp lệ.
- Style element khi nonce-source được khai báo trong directive style tương ứng.

Nonce **không phải** session ID, access token, hash nội dung script, quyền cho mọi script trên trang hoặc cách sanitize HTML. Nó chỉ xác nhận rằng server đã đánh dấu phần tử cụ thể trong response là được phép chạy; nó không chứng minh code bên trong phần tử đó an toàn về logic.

## 3. Tạo nonce đủ khó đoán

Nonce cần được sinh từ CSPRNG. Mục tiêu là kẻ tấn công không thể đoán nonce của response trước khi chèn nội dung vào tài liệu. Khuyến nghị thực tế là dùng ít nhất 128 bit entropy; có thể dùng 16 hoặc 32 byte ngẫu nhiên rồi mã hóa Base64.

Ví dụ Node.js:

```js
import { randomBytes } from "node:crypto";

function createCspNonce() {
  return randomBytes(16).toString("base64");
}
```

Đoạn code tạo 16 byte ngẫu nhiên, tương đương 128 bit trước khi encode.

Không tạo nonce bằng:

```js
// Không an toàn: giá trị có thể đoán hoặc tái sử dụng.
const nonce1 = Date.now().toString();
const nonce2 = Math.random().toString(36);
const nonce3 = userId + "-" + timestamp;
const nonce4 = "fixed-build-nonce";
```

Các giá trị dựa trên thời gian, ID người dùng, số tăng dần hoặc chuỗi cố định không đáp ứng mục tiêu nonce ngẫu nhiên cho CSP. Hãy dùng CSPRNG của runtime hoặc framework đáng tin cậy.

### Một nonce cho một response

Một HTML response có thể chứa nhiều script được server tin cậy. Các script đó có thể dùng **cùng nonce của response hiện tại**:

```html
<script nonce="NONCE_FOR_THIS_RESPONSE">
  initializeConfig();
</script>
<script nonce="NONCE_FOR_THIS_RESPONSE" src="/assets/bootstrap.js"></script>
```

Không cần tạo nonce riêng cho từng script trong cùng một document. Điều quan trọng là nonce mới ở lần render response tiếp theo và CSP header phải khớp với HTML của chính response đó.

## 4. Nonce source trong script-src

Policy có nonce-source thường được khai báo như sau:

```http
Content-Security-Policy: default-src 'self'; script-src 'nonce-RANDOM_NONCE'; object-src 'none'; base-uri 'self'
```

Khi có nonce-source trong `script-src`, các script element mang nonce hợp lệ được phép chạy. Script element không có nonce hợp lệ sẽ bị chặn, kể cả khi nó nằm inline trong HTML.

Ví dụ HTML:

```html
<!-- Được phép: nonce khớp với response header. -->
<script nonce="RANDOM_NONCE">
  renderApplication();
</script>

<!-- Bị chặn: không có nonce. -->
<script>
  renderUnexpectedCode();
</script>

<!-- Bị chặn: nonce không khớp. -->
<script nonce="different-value">
  renderUnexpectedCode();
</script>
```

Nếu policy chỉ có nonce-source và không có host source, script external không mang nonce cũng không được phép chỉ vì URL nằm cùng origin. Đây là khác biệt quan trọng so với policy `script-src 'self'`.

## 5. Nonce có thể cấp quyền cho external script

Nonce không chỉ dành cho inline script. Một script element tải file bên ngoài cũng có thể được cấp quyền bằng nonce:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_NONCE'
```

```html
<script nonce="RANDOM_NONCE" src="/assets/app.js"></script>
```

Nếu nonce khớp, browser có thể cho phép script element này theo cơ chế nonce. Vì vậy, nonce gắn với **element được đánh dấu**, không phải hash hay danh sách host của file.

Điều này cũng có nghĩa cần kiểm soát nơi server/template gắn nonce. Nếu dữ liệu không tin cậy có thể điều khiển toàn bộ script element hoặc thuộc tính nonce, cơ chế cấp quyền có thể bị lạm dụng. Không đưa nonce vào dữ liệu do người dùng kiểm soát và không tạo HTML script element từ input.

Với external script tĩnh từ CDN, có thể cân nhắc thêm Subresource Integrity (SRI) để browser kiểm tra nội dung file. Nonce trả lời “element này được server cho phép chạy?”, còn SRI trả lời “nội dung tải về có khớp hash mong đợi không?”.

## 6. Nonce không cấp quyền cho event handler hoặc javascript: URL

Nonce trên phần tử `script` không tự động cho phép inline event handler:

```html
<!-- Nonce trên script element không cho phép onclick này. -->
<button onclick="saveProfile()">Lưu</button>
```

Tương tự, nonce không phải cách cho phép URL `javascript:...`:

```html
<a href="javascript:runAction()">Thực hiện</a>
```

Hãy chuyển event handler sang listener được định nghĩa trong script hợp lệ:

```html
<button id="save-profile">Lưu</button>
```

```js
document
  .querySelector("#save-profile")
  .addEventListener("click", saveProfile);
```

Với CSP, có thể khai báo rõ:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_NONCE'; script-src-attr 'none'
```

`script-src-attr 'none'` chặn inline event handler trong browser hỗ trợ directive này. Nếu không khai báo directive chuyên biệt, browser dùng fallback từ `script-src` hoặc `default-src`.

## 7. Nonce và script-src-elem / script-src-attr

CSP có các directive script chuyên biệt:

| Directive | Phạm vi |
| --- | --- |
| `script-src` | Chính sách script tổng quát và fallback |
| `script-src-elem` | Phần tử `<script>` inline/external |
| `script-src-attr` | Inline event handler trong attribute như `onclick` |

Nếu policy có `script-src-elem`, directive này được dùng cho script element thay vì fallback về `script-src`. Do đó, nonce cần có trong directive đang thực sự áp dụng:

```http
Content-Security-Policy: script-src 'self'; script-src-elem 'nonce-RANDOM_NONCE'; script-src-attr 'none'
```

Trong ví dụ này, script element cần nonce khớp với `script-src-elem`. Việc chỉ thêm nonce vào `script-src` không đủ nếu `script-src-elem` đã được khai báo và không có nonce-source.

Khi debug, hãy đọc toàn bộ CSP header và xác định directive hiệu lực theo fallback; đừng chỉ tìm thấy chuỗi `nonce-` ở đâu đó trong header rồi kết luận script sẽ được phép.

## 8. Nonce và strict-dynamic

Ứng dụng hiện đại có thể dùng một script bootstrap để tải các module hoặc chunk khác. `strict-dynamic` cho phép browser hỗ trợ CSP3 mở rộng niềm tin từ script được cho phép bằng nonce hoặc hash sang script mà script đáng tin cậy nạp động theo các quy tắc của CSP.

Ví dụ policy:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_NONCE' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

Script bootstrap:

```html
<script nonce="RANDOM_NONCE" src="/assets/bootstrap.js"></script>
```

Bootstrap nạp chunk:

```js
const chunk = document.createElement("script");
chunk.src = "/assets/dashboard.chunk.js";
document.head.append(chunk);
```

Trong browser hỗ trợ, script bootstrap được cấp nonce có thể truyền niềm tin cho script mà nó nạp động. Điều này làm bootstrap trở thành **root of trust**.

Nếu bootstrap dùng URL do người dùng điều khiển, đọc plugin manifest không đáng tin hoặc tạo script từ dữ liệu API mà không kiểm tra, `strict-dynamic` có thể mở rộng quyền tới script ngoài dự kiến. Hãy bảo vệ loader, manifest và quy trình build như thành phần bảo mật quan trọng.

### Fallback cho browser cũ

Một policy tương thích có thể kết hợp nonce, `strict-dynamic` và host source tối thiểu:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_NONCE' 'strict-dynamic' 'self' https://cdn.example.com
```

Browser CSP3 hiện đại dùng nonce/strict-dynamic theo quy tắc hỗ trợ; browser cũ không hiểu `strict-dynamic` có thể dùng các host source làm fallback. Hãy kiểm thử browser mục tiêu và tránh thêm wildcard chỉ để tương thích.

## 9. Nonce và hash source: chọn cơ chế nào?

Nonce và hash đều có thể cho phép inline script mà không cần `unsafe-inline`, nhưng phù hợp với tình huống khác nhau:

| Tiêu chí | Nonce | Hash |
| --- | --- | --- |
| Giá trị được tạo từ | CSPRNG cho response | Digest nội dung script |
| Thay đổi giữa response | Có | Không, nếu nội dung không đổi |
| Phù hợp | HTML render động, bootstrap, SSR | Inline script tĩnh, ổn định |
| Ràng buộc | Element phải có nonce khớp | Nội dung phải khớp digest chính xác |
| Vấn đề vận hành | Đồng bộ header/HTML và cache | Tính lại hash khi nội dung thay đổi |

Ví dụ hash-source:

```http
Content-Security-Policy: script-src 'sha256-BASE64_DIGEST'
```

`BASE64_DIGEST` là placeholder. Hash được tính từ nội dung inline script theo đúng quy tắc CSP; thay đổi whitespace hoặc ký tự có thể làm digest không khớp.

Không dùng nonce thay cho hash khi script tĩnh được build sẵn và dễ quản lý digest; cũng không dùng hash cho inline script thay đổi theo dữ liệu mỗi response nếu việc duy trì digest trở nên phức tạp.

## 10. Nonce phải mới cho mỗi response HTML

Nonce cần không thể đoán trước và không nên được tái sử dụng giữa các response. Nếu server dùng một nonce cố định:

```http
Content-Security-Policy: script-src 'nonce-static-value'
```

thì người tấn công biết giá trị đó có thể chèn script element với cùng nonce vào response khác. Khi nonce được tái sử dụng, lợi ích của việc cấp quyền ngẫu nhiên theo response bị suy giảm.

Quy tắc triển khai:

- Tạo nonce mới mỗi lần server render HTML response.
- Dùng cùng một nonce cho header và mọi script element hợp lệ trong response đó.
- Không dùng nonce làm ID người dùng, session ID hoặc giá trị cấu hình dài hạn.
- Không ghi nonce vào log hoặc telemetry không cần thiết.
- Không nhận nonce từ query, form, cookie hay header do client gửi để quyết định script nào được phép.

Nonce không cần được giữ bí mật sau khi response đã tới browser. Nó xuất hiện trong HTML và CSP header. Mục tiêu là kẻ tấn công không thể dự đoán nonce trước khi tạo nội dung được chèn vào response; nonce cố định hoặc có thể đoán được làm hỏng đặc tính đó.

## 11. Cache, CDN và SSR: đồng bộ nonce với HTML

Nonce chỉ có ý nghĩa khi giá trị trong CSP header khớp với thuộc tính nonce trong HTML **cùng response**.

Một lỗi phổ biến:

1. Origin server render HTML và CSP với nonce A.
2. CDN cache HTML và header.
3. Một tầng proxy thay header bằng nonce B nhưng không sửa HTML, hoặc ngược lại.
4. Browser nhận cặp không khớp và chặn script hợp lệ.

Rủi ro khác là shared cache phát lại nguyên HTML cùng nonce cũ cho nhiều người dùng. Nếu nonce bị tái sử dụng qua nhiều response, người tấn công có thêm cơ hội biết giá trị trước khi khai thác một response khác.

Các chiến lược:

| Kiến trúc | Cách xử lý |
| --- | --- |
| HTML cá nhân hóa từ server | Thường dùng `Cache-Control: private, no-store` hoặc policy cache phù hợp để tránh shared cache lưu nonce |
| CDN render HTML tại edge | Tạo nonce ở edge và thay thế đồng bộ trong header lẫn script element |
| Static HTML | Cân nhắc hash-source cho inline script tĩnh hoặc bỏ inline script |
| SSR framework | Dùng hook/request context tạo một nonce cho response và truyền cùng giá trị vào document template |
| Service Worker cache | Kiểm tra không phát lại HTML có nonce cũ như response mới ngoài thiết kế |

Không phải mọi ứng dụng đều phải dùng `no-store`; quyết định phụ thuộc dữ liệu cá nhân, cache architecture và cách nonce được tạo. Nếu cần cache HTML, phải thiết kế cơ chế re-nonce nhất quán tại đúng tầng phát response.

## 12. Ví dụ Node.js/Express: tạo nonce một lần cho response

Ví dụ dưới đây minh họa cách tạo nonce trong middleware và chia sẻ cùng giá trị cho CSP header và template:

```js
import { randomBytes } from "node:crypto";

app.use((req, res, next) => {
  const nonce = randomBytes(16).toString("base64");

  res.locals.cspNonce = nonce;
  res.setHeader(
    "Content-Security-Policy",
    [
      "default-src 'self'",
      "script-src 'nonce-" + nonce + "' 'strict-dynamic'",
      "script-src-attr 'none'",
      "object-src 'none'",
      "base-uri 'none'",
      "frame-ancestors 'none'",
    ].join("; ")
  );

  next();
});
```

Trong template:

```html
<script nonce="{{ cspNonce }}" src="/assets/bootstrap.js"></script>
<script nonce="{{ cspNonce }}">
  window.appConfig = {{ serializedConfig }};
</script>
```

`{{ ... }}` chỉ là ký hiệu template minh họa; cần dùng template engine có escaping phù hợp. Dữ liệu cấu hình JavaScript phải được serialize an toàn theo đúng context, không nối chuỗi JSON tùy ý vào script block.

Các điểm cần lưu ý:

- Middleware chạy đúng một lần cho mỗi HTML response và trước khi render template.
- Không tạo nonce một lần ở lúc khởi động process rồi dùng lại cho mọi request.
- Không để route hoặc template tự tạo nonce riêng khác với giá trị trong header.
- Không gắn nonce cho mọi node được tạo từ dữ liệu người dùng.
- Nếu response là JSON hoặc tài nguyên không chứa script element, không cần phát nonce CSP chỉ vì middleware đang tồn tại; có thể giới hạn CSP ở HTML document route.
- Nếu dùng nhiều CSP header, nonce phải được cho phép trong mọi policy enforcement liên quan.

## 13. Nonce hiding và giới hạn của nonce

Browser hiện đại có cơ chế ẩn giá trị nonce khi truy cập qua một số API attribute thông thường, ví dụ `getAttribute("nonce")` có thể trả chuỗi rỗng, trong khi thuộc tính DOM `element.nonce` vẫn cho phép code truy cập giá trị.

Điều này nhằm giảm khả năng rò rỉ nonce qua một số kỹ thuật đọc attribute/CSS, nhưng **không phải ranh giới bảo mật chống JavaScript độc hại**. Script đã thực thi trong origin có thể truy cập DOM và các API được phép; ứng dụng không được dựa vào nonce hiding để bảo vệ khỏi XSS đã chạy.

Nonce cũng không sửa các vấn đề sau:

- Script hợp lệ có lỗi logic hoặc bị compromise.
- Bootstrap đáng tin cậy nạp URL do attacker kiểm soát.
- Dữ liệu không tin cậy đi vào `innerHTML`, event handler hoặc sink khác.
- Server gắn nonce cho script element được tạo từ nội dung không tin cậy.
- Cookie/session và authorization bị cấu hình sai.

Nonce là một cơ chế **allow-list theo element**, không phải sanitizer và không phải sandbox.

## 14. Nhiều CSP policy và Report-Only

Nếu tài liệu nhận nhiều policy enforcement, browser áp dụng đồng thời. Để script có nonce chạy, mỗi policy enforcement liên quan phải cho phép nonce đó theo directive có hiệu lực. Một policy khác không có nonce hoặc đặt `script-src 'none'` có thể tiếp tục chặn script.

`Content-Security-Policy-Report-Only` giúp quan sát policy mới:

```http
Content-Security-Policy-Report-Only: script-src 'nonce-RANDOM_NONCE'; object-src 'none'
```

Report-Only không chặn script; nó ghi nhận vi phạm theo cấu hình báo cáo. Nếu response đồng thời có CSP enforcement, enforcement policy vẫn chặn theo quy tắc của nó.

Quy trình:

1. Bật Report-Only với nonce-source dự kiến.
2. Kiểm tra tất cả inline và external script hợp lệ.
3. Xác minh template gắn nonce cho đúng element.
4. Kiểm tra lỗi do cache, CDN và nhiều CSP header.
5. Chuyển sang enforcement sau khi xử lý các vi phạm hợp lệ.

Không coi Report-Only là bằng chứng đã bảo vệ ứng dụng. Nó chỉ giúp thu thập thông tin trước khi enforcement.

## 15. Chẩn đoán nonce không hoạt động

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Inline script bị chặn dù có nonce | Giá trị trong HTML không khớp header | Xem response header và HTML của cùng request |
| External script cùng origin bị chặn | Script không có nonce và policy không có `'self'` | Kiểm tra element có nonce hoặc policy có host source phù hợp |
| Nonce có trong `script-src` nhưng script vẫn bị chặn | `script-src-elem` đã được khai báo riêng | Kiểm tra directive thực sự áp dụng cho script element |
| Event handler không chạy | Nonce không cấp quyền cho `onclick`/`onerror` | Chuyển sang `addEventListener` |
| Chỉ lỗi khi qua CDN | Header và HTML bị cache/thay đổi không đồng bộ | So sánh response tại origin và response cuối |
| Một số tab chạy, tab khác lỗi | HTML cache hoặc nhiều response dùng nonce khác nhau | Kiểm tra nonce theo từng response/document |
| Script chunk động bị chặn | Root script thiếu nonce hoặc loader không được tin cậy | Kiểm tra bootstrap và `strict-dynamic` |
| Nonce cố định qua nhiều lần tải | Nonce được tạo lúc startup hoặc HTML cache phát lại | Sinh nonce mới theo response và kiểm tra cache |
| CSP Report-Only có report nhưng script vẫn chạy | Report-Only không enforcement | Triển khai enforcement sau giai đoạn quan sát |

Khi debug, kiểm tra cả Network response headers, View Source/Elements và Console. Không chỉ xem DOM property của nonce rồi kết luận header đang đúng.

## 16. Thực hành: kiểm chứng nonce source

Thực hiện trong ứng dụng lab do bạn kiểm soát, dùng script vô hại và không thử khai thác website bên ngoài.

### Bước 1 — Tạo hai script element

Trang HTML thử nghiệm có hai script:

```html
<script nonce="NONCE_FROM_SERVER">
  document.querySelector("#status").textContent = "Nonce script chạy";
</script>

<script>
  document.querySelector("#status").textContent = "Script không có nonce";
</script>
```

Server trả policy:

```http
Content-Security-Policy: default-src 'self'; script-src 'nonce-NONCE_FROM_SERVER'; object-src 'none'
```

Thay `NONCE_FROM_SERVER` bằng cùng giá trị ngẫu nhiên trong response header và script được phép.

**Kỳ vọng:** script có nonce chạy; script không có nonce bị chặn. Console hiển thị vi phạm CSP cho script không được phép.

### Bước 2 — Tải lại nhiều lần

Tải lại trang nhiều lần và quan sát response:

- Nonce của response mới phải khác response trước.
- Nonce trong header phải khớp nonce trong script element cùng response.
- Script hợp lệ vẫn chạy sau mỗi lần render.

Không lưu nonce vào file cấu hình hoặc biến toàn cục để tái sử dụng.

### Bước 3 — Thử external script

Tạo file script tĩnh cùng origin và thêm nonce lên script element. Bỏ nonce rồi tải lại để quan sát khác biệt giữa nonce-source và `'self'`.

### Bước 4 — Thử event handler

Thêm `onclick` vào button. Xác nhận nonce trên script element không cấp quyền cho event handler; thay bằng `addEventListener` trong script hợp lệ.

### Bước 5 — Thử strict-dynamic

Cho bootstrap có nonce nạp một file chunk từ đường dẫn cố định trong lab. So sánh hành vi với policy không có `strict-dynamic`. Không để URL chunk phụ thuộc query hoặc input người dùng.

### Bước 6 — Kiểm tra cache

Nếu lab có proxy/CDN, tải qua cache và xác nhận nonce header/HTML luôn đồng bộ, không bị tái sử dụng giữa các response. Nếu không có CDN, kiểm tra response server và cache browser/service worker.

## 17. Checklist triển khai nonce-source

- Sinh nonce bằng CSPRNG, tối thiểu 128 bit entropy.
- Tạo nonce mới cho mỗi HTML response.
- Dùng cùng nonce trong CSP header và mọi script element được server cho phép trong response đó.
- Không nhận nonce từ client và không để input người dùng điều khiển thuộc tính nonce.
- Không dùng nonce cố định, timestamp, Math.random hoặc giá trị suy ra từ user/session ID.
- Hiểu nonce áp dụng cho script/style element; không dùng nó để cấp quyền cho event handler hoặc `javascript:` URL.
- Kiểm tra `script-src-elem` nếu directive này được khai báo riêng.
- Chỉ dùng `strict-dynamic` khi root script và loader được kiểm soát.
- Đồng bộ nonce qua SSR, template, CDN và cache; không phát lại HTML có nonce cũ ngoài thiết kế.
- Cân nhắc hash-source cho inline script tĩnh.
- Dùng SRI cho external script tĩnh bên thứ ba khi phù hợp.
- Dùng Report-Only để quan sát trước enforcement; kiểm tra mọi policy header đang áp dụng.
- Kiểm thử response mới, cache hit, nhiều tab và browser mục tiêu.

## 18. Câu hỏi tự kiểm tra

1. Nonce source là gì và browser đối chiếu giá trị nào?
2. Vì sao nonce phải được tạo bằng CSPRNG và mới cho mỗi response?
3. Một response có nhiều script hợp lệ có cần nonce khác nhau cho từng script không?
4. Nonce có thể cấp quyền cho external script element không?
5. Vì sao nonce không cấp quyền cho `onclick` hoặc URL `javascript:`?
6. Nếu `script-src-elem` được khai báo, nó ảnh hưởng việc áp dụng nonce như thế nào?
7. `strict-dynamic` mở rộng niềm tin từ bootstrap script theo cách nào?
8. Vì sao cache/CDN phải đồng bộ nonce giữa CSP header và HTML?
9. Nonce hiding có bảo vệ ứng dụng khỏi script XSS đã thực thi không?
10. Khi nào hash-source phù hợp hơn nonce-source?

**Ghi nhớ:** Nonce source cấp quyền thực thi cho script element được server đánh dấu bằng một giá trị ngẫu nhiên khó đoán. Hãy sinh nonce bằng CSPRNG cho từng response, đồng bộ cùng giá trị giữa CSP header và HTML, kiểm soát root script/loader nếu dùng `strict-dynamic`, và xử lý cache để không tái sử dụng nonce ngoài thiết kế. Nonce không cấp quyền cho event handler, không sanitize dữ liệu và không thay thế phòng vệ XSS; nó là một lớp kiểm soát thực thi trong CSP.
