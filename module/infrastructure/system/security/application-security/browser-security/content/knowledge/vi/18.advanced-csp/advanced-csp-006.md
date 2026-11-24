# Inline script: kiểm soát mã JavaScript nhúng bằng Content Security Policy

## 1. Inline script là gì?

Trong một trang web, JavaScript có thể được tải từ file riêng hoặc được viết trực tiếp trong tài liệu HTML. Mã JavaScript viết ngay trong HTML được gọi là **inline script**. Ví dụ đơn giản:

```html
<script>
  document.querySelector("#status").textContent = "Sẵn sàng";
</script>
```

Inline script cũng xuất hiện dưới những dạng ít dễ nhận ra hơn:

- Event handler attribute như `onclick`, `onerror` hoặc `onload`.
- URL dùng scheme `javascript:`.
- Một số cách thực thi mã được tạo động từ chuỗi.

Khi ứng dụng triển khai **Content Security Policy (CSP)** nghiêm ngặt, browser mặc định có thể chặn inline script nếu chính sách không cấp quyền rõ ràng. Mục tiêu là ngăn một đoạn mã được chèn vào HTML ngoài ý muốn chạy trong origin của ứng dụng.

Ví dụ, một trang có CSP:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'
```

thì file JavaScript từ cùng origin có thể được phép tải, nhưng một block `<script>...</script>` không có nonce/hash được cấp quyền sẽ bị chặn. Chính sách này cũng không cho phép event handler inline chỉ vì handler nằm trên phần tử HTML cùng origin.

Trong module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, CSP được học cùng ranh giới browser, origin, cookie, SOP và phòng vệ XSS. Bài này tập trung vào cách kiểm soát inline script: xác định đúng loại mã nhúng, chọn nonce hoặc hash, xử lý event handler cũ, triển khai dần và kiểm chứng kết quả trong browser.

### Kết quả học tập

Sau bài này, người học có thể:

1. Nhận diện inline script block, event handler attribute và `javascript:` URL.
2. Giải thích cách `script-src`, `script-src-elem` và `script-src-attr` điều khiển các dạng script khác nhau.
3. So sánh `unsafe-inline`, nonce, hash và `unsafe-hashes`.
4. Tạo nonce ngẫu nhiên cho từng response và gắn đúng vào header cùng script được phép.
5. Chuyển event handler inline sang `addEventListener` và file JavaScript riêng.
6. Triển khai CSP Report-Only, đọc vi phạm và chuyển sang enforcement.
7. Phân biệt inline script với `eval`, inline style và JSON data block.

## 2. Vì sao cần kiểm soát inline script?

HTML là tài liệu có cấu trúc, còn script là mã có thể thực thi trong origin của trang. Nếu dữ liệu không tin cậy bị chèn vào HTML tại vị trí mà browser diễn giải thành script, payload có thể chạy với quyền của trang đó.

Ví dụ trang hiển thị nội dung do người dùng gửi:

```html
<div class="comment">
  USER_CONTENT
</div>
```

Nếu ứng dụng ghép dữ liệu thô vào response mà không encode HTML context, người dùng có thể làm thay đổi cấu trúc tài liệu. Trong một số vị trí, nội dung chèn vào có thể tạo phần tử script hoặc event handler. Đây là một đường dẫn thường gặp của reflected hoặc stored XSS.

CSP bổ sung một lớp kiểm soát: browser chỉ thực thi inline script khi chính sách cho phép theo cơ chế được khai báo. Nếu ứng dụng không dùng `unsafe-inline`, payload inline không có nonce/hash hợp lệ thường bị chặn.

Tuy vậy, CSP không phải sanitizer:

- CSP không biến HTML injection thành dữ liệu an toàn.
- Một payload vẫn có thể thay đổi DOM hoặc nội dung trang dù script bị chặn.
- Script hợp lệ được cấp nonce vẫn có thể có lỗi XSS nếu nó đưa dữ liệu không tin cậy vào sink nguy hiểm.
- Một chính sách có `unsafe-inline` hoặc nguồn script quá rộng có thể làm giảm đáng kể hiệu quả bảo vệ.

Do đó, vẫn phải encode output đúng context, dùng safe DOM APIs, sanitize rich HTML khi cần và kiểm tra source-to-sink.

## 3. Những dạng inline script CSP cần kiểm soát

### 3.1. Inline script block

Đây là nội dung JavaScript nằm giữa cặp thẻ `<script>`:

```html
<script>
  initializePage();
</script>
```

Script module cũng có thể được viết inline:

```html
<script type="module">
  import { start } from "/assets/app.js";
  start();
</script>
```

Với CSP, script element inline được kiểm soát bởi `script-src-elem` nếu directive này có mặt; nếu không, browser dùng `script-src` làm fallback. Nonce hoặc hash có thể cấp quyền cho một script element cụ thể.

### 3.2. Event handler attribute

HTML cho phép gắn mã JavaScript trực tiếp vào attribute:

```html
<button onclick="saveProfile()">Lưu</button>
<img src="/missing.png" onerror="showFallback()">
```

Đây cũng là inline script. Nó được điều khiển bởi `script-src-attr` nếu chính sách khai báo directive này; nếu không, browser fallback về `script-src`.

Nonce không cấp quyền cho event handler attribute. Cách chuyển đổi nên dùng:

```html
<button id="save-profile" type="button">Lưu</button>
```

```js
document
  .querySelector("#save-profile")
  .addEventListener("click", saveProfile);
```

Tách hành vi khỏi markup giúp CSP nghiêm ngặt hơn, đồng thời dễ kiểm thử, tái sử dụng và quản lý sự kiện.

### 3.3. URL dùng `javascript:`

Ví dụ:

```html
<a href="javascript:showHelp()">Trợ giúp</a>
```

`javascript:` URL có thể thực thi mã khi được kích hoạt trong những ngữ cảnh browser cho phép. CSP kiểm soát loại URL này qua các quy tắc inline script; không coi nó là một liên kết HTTPS bình thường.

Hãy thay bằng liên kết hoặc button có hành vi được gắn qua JavaScript:

```html
<button id="help" type="button">Trợ giúp</button>
```

```js
document.querySelector("#help").addEventListener("click", showHelp);
```

### 3.4. Các cơ chế khác không nên nhầm lẫn

| Cơ chế | Ví dụ | CSP liên quan |
| --- | --- | --- |
| Inline script block | `<script>run()</script>` | `script-src-elem` hoặc fallback `script-src` |
| Event handler | `<button onclick="run()">` | `script-src-attr` hoặc fallback `script-src` |
| `javascript:` URL | `<a href="javascript:run()">` | Inline script checks trong CSP |
| `eval`/`Function` | `eval(text)`, `new Function(text)` | `unsafe-eval` trong `script-src` |
| Timer nhận chuỗi | `setTimeout("run()", 10)` | Cũng thuộc nhóm string evaluation, cần `unsafe-eval` |
| Inline style | `<div style="color:red">` | `style-src-attr` hoặc fallback `style-src` |
| JSON data block | `<script type="application/json">...</script>` | Là dữ liệu không thực thi; không phải script JavaScript thông thường |

Không bật `unsafe-eval` để sửa lỗi inline script, và không bật `unsafe-inline` chỉ vì ứng dụng đang dùng `eval`. Đây là các quyền khác nhau, cần xử lý riêng.

## 4. Các CSP directive điều khiển inline script

### 4.1. `script-src`

`script-src` là directive chính sách script phổ biến. Nó xác định nguồn script và các cơ chế cho phép thực thi như nonce/hash:

```http
Content-Security-Policy: script-src 'self' 'nonce-RANDOM_VALUE'
```

Directive này cũng là fallback cho `script-src-elem` và `script-src-attr` khi các directive chuyên biệt không được khai báo.

### 4.2. `script-src-elem`

`script-src-elem` áp dụng cho script được nạp qua phần tử `<script>`, gồm script element có `src` và inline script block:

```http
Content-Security-Policy: script-src 'self'; script-src-elem 'self' 'nonce-RANDOM_VALUE'
```

Khi `script-src-elem` được khai báo, nó điều khiển script element; `script-src` vẫn có thể điều khiển những loại script khác như event handler attribute thông qua fallback nếu không có `script-src-attr`.

### 4.3. `script-src-attr`

`script-src-attr` điều khiển event handler attributes:

```http
Content-Security-Policy: script-src 'self'; script-src-attr 'none'
```

Với cấu hình này, handler inline như `onclick="..."` bị chặn. Một event listener được đăng ký từ file JavaScript hợp lệ vẫn có thể hoạt động.

### 4.4. Quan hệ fallback

| Directive được khai báo | Inline script element | Event handler attribute |
| --- | --- | --- |
| Chỉ `script-src` | Theo `script-src` | Theo `script-src` |
| `script-src` + `script-src-elem` | Theo `script-src-elem` | Theo `script-src` |
| `script-src` + `script-src-attr` | Theo `script-src` | Theo `script-src-attr` |
| Cả ba directive | Theo `script-src-elem` | Theo `script-src-attr` |

Nếu một directive chuyên biệt có mặt, browser dùng nó cho loại script tương ứng thay vì lấy chính sách từ `script-src`. Điều này hữu ích khi muốn chặn event handler nhưng vẫn cho phép script element có nonce/hash.

### 4.5. Ví dụ chính sách chặn inline theo mặc định

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; script-src-attr 'none'; object-src 'none'; base-uri 'none'
```

Chính sách này:

- Cho phép script cùng origin theo source list.
- Cho phép script element có nonce khớp với nonce của response.
- Chặn event handler attribute inline.
- Chặn object/plugin không cần thiết.
- Ngăn thay đổi base URL bằng `<base>`.

Nonce phải được tạo mới cho mỗi response bằng CSPRNG. Chuỗi `RANDOM_PER_RESPONSE` trong ví dụ chỉ là placeholder; không được dùng nguyên văn trong production.

## 5. Cho phép inline script bằng nonce

### 5.1. Nonce hoạt động như thế nào?

Nonce là một giá trị ngẫu nhiên, khó đoán, được server tạo cho một response. Server đặt nonce đó trong CSP header và trong thuộc tính `nonce` của từng script element được phép:

```http
Content-Security-Policy: script-src 'self' 'nonce-abc123...'
```

```html
<script nonce="abc123...">
  initializePage();
</script>
```

Browser so sánh nonce trong script element với nonce source trong policy. Chỉ script có giá trị khớp mới được cấp quyền bởi nonce đó. Script element khác không có nonce hoặc có nonce sai sẽ bị chặn, trừ khi nó được cho phép bởi một nguồn/chính sách khác.

Nonce không phải mật khẩu người dùng và không phải token xác thực. Nó là một phần của chính sách thực thi script cho một response cụ thể.

### 5.2. Yêu cầu với nonce

- Tạo bằng CSPRNG ở server hoặc tầng edge đáng tin cậy.
- Dùng giá trị đủ dài, thường chọn ít nhất 128 bit ngẫu nhiên.
- Tạo nonce mới cho từng response HTML; không hardcode và không tái sử dụng lâu dài.
- Đặt cùng giá trị vào CSP header và đúng những script element được phép.
- Không để dữ liệu không tin cậy quyết định hoặc sửa giá trị nonce.
- Không đưa nonce vào URL, log công khai hoặc nội dung không cần thiết.
- Không thêm nonce vào mọi script một cách máy móc; mỗi script được cấp nonce đều trở thành một phần của trusted computing base.

Ví dụ server-side pseudocode:

```js
import { randomBytes } from "node:crypto";

function renderPage(req, res) {
  const nonce = randomBytes(16).toString("base64");

  res.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self' 'nonce-" +
      nonce +
      "'; script-src-attr 'none'; object-src 'none'; base-uri 'none'"
  );

  res.render("page", { cspNonce: nonce });
}
```

Trong template:

```html
<script nonce="{{ cspNonce }}">
  initializePage();
</script>
<script src="/assets/app.js" defer></script>
```

Ví dụ giả định template engine escape attribute đúng cách. Tên hàm và API phụ thuộc framework; cần xác nhận nonce được tạo mới cho từng response và header/HTML nhận đúng cùng một giá trị.

### 5.3. Nonce và cache

Nonce gắn với một response. Nếu CDN hoặc reverse proxy cache HTML chứa nonce cũ nhưng CSP header được tạo lại bằng nonce mới, browser sẽ thấy hai giá trị không khớp và chặn script hợp lệ. Ngược lại, nếu cache nguyên response cùng nonce quá lâu, nonce có thể bị tái sử dụng qua nhiều lượt truy cập.

Khi dùng nonce với cache:

- Ưu tiên render động cho HTML có nonce.
- Nếu dùng edge rendering, tạo nonce tại edge và đồng bộ header với HTML trong cùng response.
- Không cache HTML và CSP header theo hai đường độc lập có thể làm lệch nonce.
- Nếu kiến trúc không thể cấp nonce riêng cho từng response, cân nhắc hash cho block ổn định hoặc chuyển script sang file ngoài.

Nonce trong HTML có thể được quan sát bởi người nhận response; đó là điều bình thường. An toàn đến từ việc nonce mới, không thể đoán trước và chỉ cấp cho script đã được ứng dụng tin cậy chọn.

### 5.4. Nonce không cấp quyền cho mọi dạng inline code

Nonce gắn với phần tử `<script>`. Nó không cấp quyền cho event handler attribute như `onclick`, cũng không biến `javascript:` URL thành cơ chế được khuyến nghị. Hãy chuyển các handler sang `addEventListener` và bỏ `javascript:` URL.

## 6. Cho phép inline script bằng hash

### 6.1. Hash source expression

Hash phù hợp khi nội dung inline script ổn định, ví dụ một block bootstrap nhỏ không thay đổi giữa các response. Server hoặc build pipeline tính hash của nội dung script rồi đưa hash vào CSP:

```http
Content-Security-Policy: script-src 'self' 'sha256-BASE64_DIGEST'
```

```html
<script>
  initializeStaticWidget();
</script>
```

Browser tính digest của nội dung script và so sánh với hash source trong policy. Nội dung phải khớp chính xác; chỉ cần thay đổi khoảng trắng, xuống dòng hoặc một ký tự cũng có thể làm hash không còn khớp.

### 6.2. Tính hash trong build pipeline

Ví dụ Node.js tạo SHA-256 base64 từ đúng nội dung inline script:

```js
import { createHash } from "node:crypto";

const scriptContent = "\n  initializeStaticWidget();\n";
const digest = createHash("sha256")
  .update(scriptContent, "utf8")
  .digest("base64");

const sourceExpression = "'sha256-" + digest + "'";
console.log(sourceExpression);
```

Giá trị đưa vào policy là hash source expression với thuật toán và base64 digest. Phải hash đúng phần nội dung script theo cách browser kiểm tra, không gồm thẻ `<script>` bao quanh. Hãy tính từ artifact cuối cùng được render, chú ý encoding và line endings; không hash một phiên bản source khác với nội dung thực tế.

### 6.3. Khi nào chọn nonce, khi nào chọn hash?

| Tiêu chí | Nonce | Hash |
| --- | --- | --- |
| Nội dung script | Có thể thay đổi theo response | Thường ổn định |
| Cách cấp quyền | Gắn nonce vào script element và CSP header | Gắn digest của nội dung vào policy |
| Tạo policy | Runtime hoặc edge | Build/release pipeline hoặc runtime |
| Cache | Cần giữ header và HTML cùng nonce mới | Dễ phù hợp hơn với nội dung tĩnh |
| Bảo trì | Cần đồng bộ mỗi response | Phải cập nhật hash khi nội dung thay đổi |
| Phù hợp | SSR, bootstrap động, trang có script inline hợp lệ | Block nhỏ, cố định, ít thay đổi |

Nếu một block script thay đổi theo dữ liệu người dùng, hash không phải cách biến dữ liệu đó thành an toàn. Hãy tách dữ liệu khỏi mã, serialize đúng cách và render bằng API an toàn.

## 7. `unsafe-inline` và `unsafe-hashes`

### 7.1. Vì sao `unsafe-inline` nguy hiểm?

Source expression `unsafe-inline` cho phép inline script theo phạm vi directive áp dụng. Điều này có thể bao gồm inline script block và event handler attribute, đồng thời làm giảm khả năng CSP chặn payload XSS được chèn vào HTML.

Ví dụ chính sách quá rộng:

```http
Content-Security-Policy: script-src 'self' 'unsafe-inline'
```

Với chính sách này, browser được phép thực thi nhiều dạng inline script. Nếu một trang có XSS injection point, attacker có thể tận dụng quyền inline đã mở sẵn.

Trong các browser hỗ trợ nonce/hash theo CSP hiện đại, khi source list của directive có nonce/hash source thì `unsafe-inline` trong cùng directive không được dùng để mở lại inline script. Tuy nhiên, không nên dựa vào quy tắc này để giữ một policy khó hiểu hoặc để hỗ trợ browser cũ; hãy loại bỏ `unsafe-inline` sau khi chuyển đổi.

### 7.2. `unsafe-hashes` là ngoại lệ có giới hạn

Một số ứng dụng cũ chưa thể thay toàn bộ event handler attribute ngay. CSP có source expression `unsafe-hashes` cho phép hash cụ thể của nội dung event handler được chấp nhận:

```http
Content-Security-Policy: script-src 'self'; script-src-attr 'unsafe-hashes' 'sha256-HANDLER_DIGEST'
```

Hash được tính từ nội dung handler, ví dụ `saveProfile()`; không bao gồm tên attribute `onclick=` hoặc dấu ngoặc kép bao quanh. Chỉ handler có nội dung khớp hash được cho phép theo policy.

`unsafe-hashes` là giải pháp chuyển tiếp, không phải lựa chọn mặc định:

- Chỉ hash những handler cụ thể thật sự cần giữ.
- Không thêm `unsafe-inline` cùng lúc để tránh vô hiệu hóa mục tiêu giới hạn.
- Tránh handler ngắn, phổ biến hoặc có thể bị tái sử dụng ở vị trí không mong muốn.
- Chuyển dần sang `addEventListener` và loại bỏ hash khi có thể.

### 7.3. Không nhầm các keyword

| Keyword | Ý nghĩa |
| --- | --- |
| `unsafe-inline` | Cho phép inline script theo directive và quy tắc CSP áp dụng |
| `unsafe-hashes` | Cho phép hash cụ thể cho inline event handler khi kết hợp hash source phù hợp |
| `unsafe-eval` | Cho phép một số API đánh giá chuỗi thành mã, như `eval` và `Function` |
| `strict-dynamic` | Cho phép lan truyền sự tin cậy từ script được cấp nonce/hash tới script được nó nạp động theo CSP3 |

Không dùng keyword rộng hơn chỉ để dập lỗi console. Hãy xác định chính xác loại script bị chặn và xử lý đúng directive.

## 8. strict-dynamic và script được nạp động

Một ứng dụng có thể dùng bootstrap script nhỏ để tải các module hoặc bundle khác theo cấu hình. CSP3 có source expression `strict-dynamic`, cho phép lan truyền sự tin cậy từ script element đã được cấp nonce/hash tới script không do HTML parser chèn (non-parser-inserted) mà script tin cậy tạo và nạp động theo các điều kiện của CSP.

Ví dụ chính sách:

```http
Content-Security-Policy: script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic' 'self'; object-src 'none'; base-uri 'none'
```

Với browser hỗ trợ CSP3, script có nonce hợp lệ có thể nạp script khác bằng DOM API; sự tin cậy được lan truyền theo cơ chế `strict-dynamic`. Khi `strict-dynamic` được áp dụng cùng nonce/hash source, browser CSP3 bỏ qua host/scheme source expression như `'self'` cho việc cho phép script; trong browser cũ không hiểu `strict-dynamic`, `'self'` có thể đóng vai trò fallback.

### 8.1. Vì sao cần thận trọng?

`strict-dynamic` chuyển một phần trách nhiệm tin cậy sang script loader. Nếu script được cấp nonce nhận URL script từ dữ liệu không tin cậy rồi nạp tùy ý, kẻ tấn công có thể lợi dụng loader để tải mã ngoài dự kiến.

Ví dụ thiết kế cần tránh:

```js
function loadPlugin(urlFromUser) {
  const script = document.createElement("script");
  script.src = urlFromUser;
  document.head.append(script);
}
```

Script loader phải chọn module từ allowlist hoặc manifest đáng tin cậy, kiểm tra identifier và không dùng URL tùy ý do người dùng gửi. Nonce không biến một script loader thiếu kiểm soát thành an toàn.

### 8.2. Khi nào dùng?

- Ứng dụng có bootstrap loader đã được review và cần tải bundle/module động.
- Có kiểm soát rõ ràng nguồn và danh tính các script con.
- Đã kiểm thử browser CSP3 và fallback browser mục tiêu.
- Có giám sát các script được tải trong production.

Nếu ứng dụng không cần tải script động, policy nonce/hash đơn giản thường dễ hiểu và dễ audit hơn.

## 9. Chuyển inline handler sang JavaScript riêng

### 9.1. Trước: handler nằm trong HTML

```html
<button onclick="submitOrder()">Đặt hàng</button>
<a href="javascript:openDetails()">Chi tiết</a>
```

Các đoạn mã này khiến ứng dụng phụ thuộc vào quyền inline script. Chúng cũng trộn cấu trúc HTML với hành vi, làm việc rà soát CSP và kiểm thử khó hơn.

### 9.2. Sau: markup không chứa mã thực thi

```html
<button id="submit-order" type="button">Đặt hàng</button>
<button id="open-details" type="button">Chi tiết</button>
<script src="/assets/orders.js" defer></script>
```

File /assets/orders.js:

```js
document
  .querySelector("#submit-order")
  .addEventListener("click", submitOrder);

document
  .querySelector("#open-details")
  .addEventListener("click", openDetails);
```

Với script ngoài, CSP có thể cho phép file cùng origin bằng `'self'`. Nếu script đến từ CDN hoặc nhà cung cấp bên ngoài, chỉ cho phép nguồn cần thiết; cân nhắc Subresource Integrity (SRI) để browser kiểm tra nội dung file có khớp hash đã khai báo hay không.

### 9.3. Event delegation

Với danh sách phần tử được tạo động, có thể dùng event delegation thay vì gắn handler inline hoặc thêm listener cho từng phần tử:

```js
document.querySelector("#orders").addEventListener("click", event => {
  const button = event.target.closest("[data-action]");
  if (!button) return;

  if (button.dataset.action === "cancel") {
    cancelOrder(button.dataset.orderId);
  }
});
```

Data attribute chỉ mang dữ liệu; nó không phải mã. Tuy nhiên, giá trị như order ID vẫn phải được validate và kiểm tra quyền ở server trước khi hủy đơn. Không lấy tên hàm từ attribute rồi gọi qua global object nếu dữ liệu đó có thể bị kiểm soát.

## 10. Inline style và JSON data block không phải inline JavaScript

### 10.1. Inline style có policy riêng

Ví dụ:

```html
<div style="color: red">Thông báo</div>
<style>
  .notice { color: red; }
</style>
```

Đây là CSS, không phải JavaScript. Browser điều khiển chúng bằng `style-src`, `style-src-elem` hoặc `style-src-attr` tùy vị trí. Việc thêm nonce vào `script-src` không cấp quyền cho inline style. Tách style sang file CSS hoặc dùng class thường giúp policy rõ ràng hơn.

### 10.2. JSON data block không thực thi như script

Một ứng dụng có thể nhúng dữ liệu JSON trong script element có MIME type không thực thi:

```html
<script id="page-data" type="application/json">
  {"displayName":"An"}
</script>
```

Đây là data block, không phải JavaScript chạy như script thông thường. Client có thể đọc text và parse:

```js
const raw = document.querySelector("#page-data").textContent;
const pageData = JSON.parse(raw);
document.querySelector("#display-name").textContent =
  pageData.displayName;
```

Tuy nhiên, nếu dữ liệu JSON được ghép trực tiếp vào HTML, HTML parser vẫn xử lý ranh giới của phần tử script. Một chuỗi chứa thẻ đóng script có thể phá cấu trúc data block trước khi JSON.parse được gọi. Hãy dùng serializer dành cho HTML embedding, escape ký tự `<` thành dạng JSON Unicode escape phù hợp như `\u003C`, hoặc tải JSON từ endpoint riêng. JSON serialization đơn thuần không đủ để bảo vệ mọi cách nhúng vào HTML.
 
## 11. Rollout CSP cho ứng dụng hiện có

Không nên chuyển một ứng dụng lớn sang enforcement mà chưa biết các inline script hợp lệ đang tồn tại ở đâu. Một quy trình triển khai có kiểm soát:

1. **Kiểm kê:** tìm script block, event handler attribute, javascript: URL, string evaluation và script loader.
2. **Phân loại:** xác định script nào là mã ứng dụng, mã bên thứ ba, mã bootstrap và mã có thể bỏ.
3. **Refactor:** chuyển handler sang addEventListener, chuyển script ổn định sang file ngoài, tách dữ liệu khỏi mã.
4. **Chọn cơ chế:** dùng nonce cho script inline động hoặc hash cho block ổn định; không bật unsafe-inline để che lỗi.
5. **Report-Only:** gửi policy thử nghiệm, thu thập vi phạm và xử lý false positive.
6. **Enforcement:** chuyển sang Content-Security-Policy sau khi các luồng hợp lệ hoạt động.
7. **Giám sát:** theo dõi report, kiểm thử release và rà soát thay đổi template/script.

### 11.1. Ví dụ Report-Only

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; script-src-attr 'none'; object-src 'none'; base-uri 'none'; report-to csp-reports
Reporting-Endpoints: csp-reports="https://reports.example.com/csp"
```

Content-Security-Policy-Report-Only chỉ ghi nhận vi phạm, không chặn script. Reporting-Endpoints khai báo endpoint group cho cơ chế Reporting API. Nếu cần hỗ trợ browser cũ, đánh giá thêm report-uri theo ma trận tương thích.

Endpoint báo cáo cần giới hạn kích thước, rate, retention và quyền truy cập; không đưa token hoặc dữ liệu cá nhân vào báo cáo tùy chỉnh. Báo cáo CSP có thể chứa URL, directive và sample theo cấu hình, vì vậy cần xử lý như telemetry có thể chứa dữ liệu nhạy cảm.

### 11.2. Đọc báo cáo vi phạm

Khi nhận một CSP violation report, xem:

- Directive bị vi phạm, ví dụ script-src-elem hay script-src-attr.
- blocked-uri hoặc nguồn bị chặn.
- Trang phát sinh vi phạm.
- Script hoặc template tạo ra hành vi.
- Vi phạm là mã hợp lệ còn sót, extension/browser injection hay dấu hiệu XSS.

Không tự động thêm nguồn bị chặn vào allowlist. Trước tiên xác minh nguồn đó có thuộc ứng dụng và có cần thiết không. Browser extension hoặc công cụ bảo mật có thể tạo report không phản ánh lỗi ứng dụng; cần phân loại bằng chứng.

## 12. Thực hành: kiểm tra nonce và chặn event handler

Thực hành trong môi trường local do bạn kiểm soát. Ví dụ Node.js dưới đây tạo nonce mới cho từng response, cho phép script element có nonce và chặn event handler attribute.

Tạo file lab:

```js
const http = require("node:http");
const { randomBytes } = require("node:crypto");

http.createServer((_req, res) => {
  const nonce = randomBytes(16).toString("base64");
  const policy = [
    "default-src 'self'",
    "script-src 'self' 'nonce-" + nonce + "'",
    "script-src-attr 'none'",
    "object-src 'none'",
    "base-uri 'none'"
  ].join("; ");

  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": policy,
    "Cache-Control": "no-store"
  });

  const html =
    "<!doctype html><meta charset=\"utf-8\">" +
    "<title>CSP inline script lab</title>" +
    "<h1>Inline script lab</h1>" +
    "<button id=\"inline\" onclick=\"alert('handler inline')\">Handler inline</button>" +
    "<button id=\"safe\" type=\"button\">Event listener</button>" +
    "<p id=\"result\">Chưa chạy</p>" +
    "<script>" +
    "document.body.dataset.unauthorized = 'ran';" +
    "</script>" +
    "<script nonce=\"" + nonce + "\">" +
    "document.querySelector('#safe').addEventListener('click', function () {" +
    "document.querySelector('#result').textContent = 'Listener hợp lệ đã chạy';" +
    "});" +
    "</script>";

  res.end(html);
}).listen(3000, "127.0.0.1", () => {
  console.log("Mở http://127.0.0.1:3000");
});
```

Chạy file bằng Node.js và mở địa chỉ local. Kết quả kỳ vọng:

- Script block không có nonce bị browser chặn; Console hiển thị CSP violation.
- Event handler onclick bị chặn bởi script-src-attr 'none'.
- Script block có nonce chạy và đăng ký listener cho nút Event listener.
- Nhấn nút Event listener cập nhật dòng trạng thái.
- Mỗi lần tải lại trang, server tạo nonce mới; header và script element vẫn khớp trong cùng response.

Ví dụ chỉ dùng dữ liệu và hành vi vô hại trong local lab. Không tái sử dụng nonce cố định của ví dụ hoặc nới policy production để làm bài thử hoạt động.

### 12.1. Kiểm tra header và DOM

1. Mở DevTools → Network, chọn document response.
2. Kiểm tra Response Headers có Content-Security-Policy.
3. So sánh nonce trong header với nonce của script được cấp quyền trong HTML response.
4. Mở Console và xác nhận script không nonce cùng event handler inline bị chặn.
5. Nhấn nút được gắn addEventListener và xác nhận hành vi hợp lệ vẫn hoạt động.
6. Reload trang, xác nhận nonce mới được tạo và vẫn khớp.

Không sao chép nonce từ production vào issue, log hoặc tài liệu công khai. Khi kiểm thử, chỉ cần ghi nhận nonce đã đổi và script hợp lệ được chạy.
 
## 13. Ma trận kiểm thử CSP inline script

| Mã | Trường hợp | Chính sách | Kết quả mong muốn |
| --- | --- | --- | --- |
| CSP-IN-01 | Inline script block không nonce/hash | script-src không có unsafe-inline | Browser chặn script |
| CSP-IN-02 | Inline script block có nonce khớp | Nonce trong header và element giống nhau | Script được phép |
| CSP-IN-03 | Nonce sai hoặc thiếu | Nonce source được cấu hình | Browser chặn script |
| CSP-IN-04 | Script block được hash chính xác | Hash source khớp nội dung thực tế | Script được phép |
| CSP-IN-05 | Script block thay đổi một ký tự | Hash cũ vẫn giữ nguyên | Browser chặn script |
| CSP-IN-06 | Event handler attribute | script-src-attr 'none' | Handler bị chặn |
| CSP-IN-07 | Event listener từ file ngoài | Script file được phép tải | Listener hoạt động |
| CSP-IN-08 | javascript: URL | Không cấp quyền inline | Browser chặn hành vi |
| CSP-IN-09 | eval hoặc Function | Không có unsafe-eval | Browser chặn string evaluation |
| CSP-IN-10 | Inline style attribute | style-src-attr được cấu hình riêng | Kết quả theo style policy, không theo script-src |
| CSP-IN-11 | JSON data block | MIME type không thực thi | Không chạy như JavaScript; JSON parse thành công |
| CSP-IN-12 | Nonce sau reload | Nonce mới mỗi response | Header và HTML khớp, giá trị thay đổi |

### 13.1. Chẩn đoán lỗi thường gặp

Nếu script hợp lệ bị chặn, kiểm tra theo thứ tự:

1. Header CSP thực tế của response, không chỉ cấu hình trong source code.
2. Directive áp dụng: script-src-elem, script-src-attr hay fallback script-src.
3. Nonce có khớp chính xác giữa header và element không.
4. Hash có được tính từ đúng nội dung script đã render không, gồm khoảng trắng và line ending.
5. HTML cache có làm lệch nonce với header không.
6. Có nhiều CSP policy cùng được áp dụng không; các policy enforcement đồng thời đều phải được đáp ứng.
7. Script loader có tạo script động và policy có strict-dynamic hay không.
8. Browser có hỗ trợ directive hoặc keyword đang dùng không.

Không xử lý lỗi bằng cách thêm ngay unsafe-inline hoặc unsafe-eval. Trước hết xác định chính xác script nào bị chặn và vì sao nó cần được phép.
 
## 14. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| Inline script chỉ là thẻ script có nội dung | Event handler attribute và javascript: URL cũng thuộc nhóm inline script cần kiểm soát |
| Có script-src self thì inline script cùng trang được chạy | self cho phép nguồn script cùng origin; nó không tự cấp quyền cho inline block |
| Thêm nonce vào script-src là cho phép mọi inline code | Nonce cấp quyền cho script element có nonce khớp; không cấp cho event handler attribute |
| Nonce có thể là một chuỗi cố định | Nonce cần ngẫu nhiên, khó đoán và mới cho từng response |
| Có thể dùng hash mà không quan tâm whitespace | Hash phải khớp nội dung script chính xác |
| unsafe-inline chỉ mở một đoạn script cụ thể | Nó mở rộng quyền inline theo directive và làm yếu khả năng ngăn XSS |
| unsafe-hashes giống unsafe-inline | unsafe-hashes chỉ cho phép handler có nội dung khớp hash được khai báo |
| unsafe-eval sửa được lỗi inline script | unsafe-eval điều khiển string evaluation như eval/Function; đây là quyền khác |
| Nonce an toàn nên có thể gắn vào mọi script | Chỉ cấp nonce cho script đã review; nonce mở quyền thực thi cho element đó |
| CSP tự làm sạch HTML không tin cậy | CSP là chính sách thực thi, không phải HTML sanitizer |
| JSON trong script element luôn vô hại | Data block không thực thi, nhưng vẫn cần bảo vệ ranh giới HTML khi nhúng dữ liệu |
| Inline style bị điều khiển bởi script-src | CSS có các directive style-src riêng |
| strict-dynamic làm mọi script loader an toàn | Script được cấp quyền vẫn phải kiểm soát nguồn script con và dữ liệu điều khiển loader |

## 15. Tình huống tổng hợp: chuyển trang quản trị sang CSP nghiêm ngặt

**Bối cảnh:** trang quản trị có nhiều template server-side. Một số nút dùng onclick, một số script bootstrap được render trực tiếp trong HTML và một thư viện bên thứ ba được tải từ CDN. Nhóm vận hành muốn chặn inline script để giảm rủi ro XSS mà không làm hỏng chức năng.

Thiết kế chuyển đổi:

1. Kiểm kê toàn bộ script element, event handler attribute, javascript: URL, eval/Function và script loader.
2. Chuyển handler sang file JavaScript riêng dùng addEventListener hoặc event delegation.
3. Chuyển script bootstrap tĩnh sang file ngoài; nếu thật sự cần dữ liệu động, serialize dữ liệu riêng và dùng nonce cho script element nhỏ đã review.
4. Nếu block inline cố định, tính hash từ đúng nội dung cuối cùng và cập nhật hash trong build pipeline.
5. Không bật unsafe-inline; nếu cần giữ một số handler legacy trong thời gian ngắn, đánh giá unsafe-hashes cho từng handler và đặt thời hạn loại bỏ.
6. Chỉ cho phép CDN cụ thể; cân nhắc SRI và quy trình cập nhật hash khi vendor thay đổi.
7. Triển khai Report-Only, phân loại report và sửa các luồng hợp lệ.
8. Chuyển sang enforcement, theo dõi vi phạm sau release và kiểm thử các luồng quản trị quan trọng.

### Mẫu báo cáo

| Thành phần | Trạng thái ban đầu | Thay đổi | Bằng chứng |
| --- | --- | --- | --- |
| Nút thao tác | onclick inline | addEventListener trong file riêng | Nút hoạt động; handler inline bị chặn |
| Bootstrap | Script inline thay đổi theo request | Nonce per response hoặc JSON data + file ngoài | Nonce/header khớp; dữ liệu parse đúng |
| Script cố định | Block inline ổn định | Hash source expression | Hash khớp artifact phát hành |
| Thư viện CDN | Host allowlist rộng | Nguồn cụ thể + SRI nếu phù hợp | Network và integrity check |
| CSP rollout | Chưa có enforcement | Report-Only rồi enforcement | Report được phân loại; không còn vi phạm hợp lệ |

### Tiêu chí hoàn thành

- Inline handler và javascript: URL đã được loại bỏ hoặc có kế hoạch chuyển tiếp giới hạn, được review.
- Inline script hợp lệ chỉ được cấp quyền bằng nonce/hash cụ thể.
- Nonce được tạo mới cho từng response và không bị lệch do cache.
- Script loader không nhận URL tùy ý từ dữ liệu không tin cậy.
- Các script ngoài chỉ được tải từ nguồn đã đánh giá.
- CSP report được phân loại và policy enforcement được kiểm thử.
- Các chức năng quản trị quan trọng vẫn hoạt động trong browser mục tiêu.

## 16. Checklist triển khai inline script

- [ ] Kiểm kê script block, module inline, event handler attribute và javascript: URL.
- [ ] Phân biệt inline script với eval/Function và inline style.
- [ ] Dùng script-src-elem và script-src-attr khi cần chính sách tách biệt.
- [ ] Loại bỏ unsafe-inline khỏi policy enforcement.
- [ ] Chuyển event handler sang addEventListener hoặc event delegation.
- [ ] Dùng nonce CSPRNG mới cho mỗi response nếu cần inline script động.
- [ ] Đồng bộ nonce giữa CSP header và script element; kiểm soát cache.
- [ ] Dùng hash cho block ổn định và tính từ nội dung thực tế.
- [ ] Chỉ dùng unsafe-hashes như giải pháp chuyển tiếp có giới hạn.
- [ ] Chỉ dùng strict-dynamic khi script loader được kiểm soát.
- [ ] Không nhúng dữ liệu JSON thô vào HTML script element.
- [ ] Dùng CSP Report-Only trước khi enforcement và phân loại report.
- [ ] Kiểm thử browser thực tế, cả trường hợp bị chặn và được phép.
- [ ] Kết hợp CSP với output encoding, safe DOM APIs và sanitizer để phòng XSS.

### Ghi nhớ

**CSP kiểm soát inline script bằng cách yêu cầu quyền thực thi rõ ràng.** Ưu tiên chuyển event handler và mã ổn định sang file JavaScript riêng. Khi cần inline script, dùng nonce ngẫu nhiên mới cho từng response hoặc hash của nội dung cố định. Tránh unsafe-inline; chỉ cân nhắc unsafe-hashes cho một số handler legacy trong giai đoạn chuyển đổi. script-src-elem và script-src-attr giúp tách chính sách cho script element và event handler. CSP là lớp phòng vệ bổ sung: output encoding, validation, sanitizer và kiểm soát source-to-sink vẫn cần thiết.
