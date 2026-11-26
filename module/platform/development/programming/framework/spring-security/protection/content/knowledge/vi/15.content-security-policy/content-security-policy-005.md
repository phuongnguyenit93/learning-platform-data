# script-src, style-src và mã inline

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet và Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bối cảnh: tại sao JavaScript và CSS cần quy tắc riêng?

Trong một website, JavaScript có thể đọc hoặc sửa DOM, tương tác với trạng thái giao diện và gọi API; CSS điều khiển cách hiển thị, tải thêm ảnh/font và có thể làm nội dung khó đọc hoặc tạo giao diện gây hiểu lầm. Nếu ứng dụng chèn trực tiếp HTML do người dùng kiểm soát vào trang, kẻ tấn công có thể cố đưa script, thuộc tính xử lý sự kiện hoặc style trái ý muốn vào đó.

**Content Security Policy (CSP)** là lớp phòng vệ do **trình duyệt** áp dụng dựa trên HTTP response header mà ứng dụng cung cấp. Hai directive quan trọng:

- `script-src`: đặt nguồn và một số điều kiện cho phép thực thi JavaScript.
- `style-src`: đặt nguồn và một số điều kiện cho phép áp dụng CSS.

Điểm khó không nằm ở việc viết tên directive, mà là phân biệt **tệp ngoài** với **mã nội tuyến (inline)**. Cùng một policy có thể cho phép `/js/app.js` nhưng từ chối `<script>alert(1)</script>`, hoặc cho phép `/css/main.css` nhưng từ chối `style="color:red"`.

Ví dụ:

~~~html
<!-- File JS/CSS từ URL -->
<script src="/js/app.js"></script>
<link rel="stylesheet" href="/css/app.css">

<!-- Mã inline nằm trực tiếp trong HTML -->
<script>initPage();</script>
<button onclick="submitForm()">Gửi</button>
<style>.banner { color: navy; }</style>
<p style="color: red;">Cảnh báo</p>
~~~

Với chính sách:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
~~~

hai tệp cùng origin thường được phép tải, nhưng những đoạn script/style nội tuyến ở ví dụ trên bị từ chối nếu không có cách cấp phép inline thích hợp.

**Mục tiêu bài học:** giải thích chính xác hành vi của `script-src`, `style-src` và các directive chi tiết; xử lý mã inline bằng cách tái cấu trúc, nonce hoặc hash; cấu hình tương ứng trong Spring Security Servlet và WebFlux; xác minh chính sách trong trình duyệt thay vì chỉ nhìn header.

## 2. Đọc source list: cùng origin không có nghĩa là inline

Mỗi directive thường gồm tên và một hoặc nhiều *source expression*:

~~~http
Content-Security-Policy: script-src 'self' https://static.example.net; style-src 'self' https://styles.example.net
~~~

| Biểu thức | Ý nghĩa thực tế |
|---|---|
| `'self'` | Nguồn từ cùng origin với tài liệu: scheme, host và port phù hợp |
| `'none'` | Không có nguồn nào được phép; sử dụng riêng trong source list |
| `https://static.example.net` | Cho phép nguồn phù hợp với origin/URL được chỉ định theo quy tắc CSP |
| `https:` | Mở rộng cho các nguồn HTTPS, thường quá rộng đối với script |
| `'unsafe-inline'` | Cho phép nhiều dạng script/style inline; gây giảm bảo vệ nếu dùng thiếu kiểm soát |
| `'unsafe-eval'` | Cho phép những cơ chế biên dịch chuỗi thành code của JavaScript trong phạm vi CSP tương ứng |
| `'nonce-...'` | Cho phép một số thẻ script/style inline có thuộc tính nonce khớp |
| `'sha256-...'`, `'sha384-...'`, `'sha512-...'` | Cho phép mã inline có nội dung khớp giá trị hash; còn phụ thuộc loại mã và directive |

`'self'` không bao gồm mọi subdomain. Nếu trang chạy trên `https://app.example.com`, script từ `https://cdn.example.com` là **khác origin** và không tự được cho phép. Ngược lại, `'self'` cũng không phải cấp phép cho mọi đoạn JavaScript viết ngay trong HTML.

Khi **không khai báo** `script-src` hoặc `style-src`, trình duyệt có thể dùng `default-src` theo chuỗi fallback tương ứng. Khi directive chuyên biệt đã có, danh sách nguồn của nó **không tự cộng thêm** nguồn từ `default-src`.

~~~http
Content-Security-Policy: default-src 'self'; script-src https://scripts.example.net
~~~

Trong ví dụ này, script từ chính origin có thể bị từ chối vì `script-src` chỉ khai báo nguồn script ngoài. Muốn cho phép cả hai:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://scripts.example.net
~~~

## 3. script-src kiểm soát những hình thức thực thi nào?

Script có thể được đưa vào trang bằng nhiều đường:

~~~html
<!-- A. Script ngoài -->
<script src="/js/main.js"></script>

<!-- B. Script inline -->
<script>
  console.log("ready");
</script>

<!-- C. Inline event handler -->
<button onclick="saveDraft()">Lưu</button>

<!-- D. JavaScript URL -->
<a href="javascript:alert('demo')">Thử</a>
~~~

Với `script-src 'self'` và không có cấp phép inline, trường hợp A được phép tải nếu URL cùng origin; B và C thường bị chặn khi trình duyệt cố thực thi. JavaScript URL trong trường hợp D cũng thuộc những dạng script nội tuyến mà CSP có thể chặn.

Một ví dụ dữ liệu không đáng tin cậy:

~~~html
<div class="comment">
  <img src="/does-not-exist" onerror="alert('XSS demo')">
</div>
~~~

Nếu bình luận bị đưa vào DOM như HTML có khả năng thực thi, `onerror` có thể chạy. `script-src 'self'` tạo thêm hàng rào chặn handler nội tuyến. Tuy vậy, việc CSP chặn handler **không sửa lỗi đưa dữ liệu người dùng vào HTML**, và một phần nội dung giả mạo vẫn có thể hiển thị. Ứng dụng vẫn phải escape đúng ngữ cảnh và sanitize nếu thật sự cho người dùng nhập HTML.

### Vì sao script từ nguồn được phép vẫn có rủi ro?

Một script từ origin trong danh sách `script-src` có thể được tải dù mã bên trong nguy hiểm. Những tình huống cần xem xét gồm hệ thống upload cho phép phục vụ JavaScript từ cùng origin, CDN bị chiếm quyền hoặc thư viện thứ ba có hành vi không mong muốn. CSP dựa trên nguồn **không thay thế** kiểm soát nguồn code, bảo vệ đường upload, đánh giá dependency hay tránh DOM XSS.

## 4. script-src-elem và script-src-attr trong CSP Level 3

CSP Level 3 cho phép tách chi tiết hơn:

- `script-src-elem`: quy tắc dành cho thẻ `<script>`, gồm việc tải script ngoài và script inline nằm trong thẻ đó.
- `script-src-attr`: quy tắc dành cho JavaScript trong thuộc tính xử lý sự kiện, chẳng hạn `onclick` hoặc `onerror`.
- `script-src`: quy tắc chung cho những hành vi script nằm trong phạm vi của nó và là nguồn fallback cho các directive chi tiết khi vắng mặt.

Khi kiểm tra một script element, trình duyệt tìm `script-src-elem` trước; nếu không có, dùng `script-src`, rồi `default-src`. Với inline event handler, quy tắc ưu tiên `script-src-attr`, sau đó `script-src`, cuối cùng `default-src`.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-attr 'none'; object-src 'none'
~~~

Script ngoài cùng origin vẫn có thể tải. Event handler trong thuộc tính bị chặn rõ ràng bởi `script-src-attr 'none'`; đối với trình duyệt chưa hỗ trợ directive này, `script-src 'self'` vẫn không cho phép handler inline thông thường.

**Cạm bẫy fallback:**

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-elem https://static.example.net; script-src-attr 'none'
~~~

Ở trình duyệt có hỗ trợ `script-src-elem`, script từ `/js/app.js` **không tự được phép** chỉ vì `script-src 'self'` có mặt: nguồn script element đã được quy định riêng là `https://static.example.net`. Muốn cho cả hai:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-elem 'self' https://static.example.net; script-src-attr 'none'
~~~

| Loại script | Directive ưu tiên | Khi directive ưu tiên vắng mặt |
|---|---|---|
| `<script src="...">` | `script-src-elem` | `script-src` → `default-src` |
| `<script>...</script>` | `script-src-elem` | `script-src` → `default-src` |
| `onclick`, `onerror` | `script-src-attr` | `script-src` → `default-src` |
| Các hành vi script khác, ví dụ các phép đánh giá chuỗi thành code | `script-src` và từ khóa tương ứng | `default-src` theo quy tắc của loại hành vi |

Hỗ trợ chi tiết giữa các phiên bản trình duyệt có thể khác nhau; chính sách triển khai cần được kiểm tra trên browser mà người dùng thực tế sử dụng.

## 5. style-src: stylesheet ngoài, style block và style attribute

CSS cũng có nhiều đường đưa vào trang:

~~~html
<!-- A. Stylesheet ngoài -->
<link rel="stylesheet" href="/css/layout.css">

<!-- B. Style block inline -->
<style>
  .notice { color: darkred; }
</style>

<!-- C. Style attribute inline -->
<div style="font-weight: bold">Thông báo</div>
~~~

Với:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'
~~~

stylesheet A cùng origin được phép, còn B và C không được cấp quyền inline theo policy này. Điều đó dễ ảnh hưởng đến thư viện UI tạo thẻ `<style>` động hoặc template sử dụng nhiều thuộc tính `style`.

CSP Level 3 có thêm:

- `style-src-elem`: quy tắc cho stylesheet liên quan đến thẻ `<link rel="stylesheet">` và `<style>`.
- `style-src-attr`: quy tắc áp dụng cho thuộc tính HTML `style="..."`.

Tương tự script, fallback là:

| Loại CSS | Directive ưu tiên | Fallback |
|---|---|---|
| `<link rel="stylesheet">` | `style-src-elem` | `style-src` → `default-src` |
| `<style>...</style>` | `style-src-elem` | `style-src` → `default-src` |
| `style="..."` | `style-src-attr` | `style-src` → `default-src` |

Ví dụ tách giới hạn:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; style-src-elem 'self'; style-src-attr 'none'
~~~

Chính sách này chủ đích cho stylesheet cùng origin nhưng cấm các thuộc tính `style` inline. Nếu bỏ `style-src-elem` và `style-src-attr`, browser quay về `style-src 'self'` theo quy tắc fallback thích hợp.

**Phân biệt URL được tải từ bên trong CSS:** `style-src` kiểm soát stylesheet, còn URL ảnh ở `background-image: url(...)` thường được kiểm soát thêm bởi `img-src` và font được kiểm soát bởi `font-src`. Một stylesheet có thể tải thành công mà hình nền/font vẫn bị từ chối.

**Giới hạn đánh giá:** một số thao tác CSSOM từ JavaScript (ví dụ cập nhật thuộc tính style bằng API DOM) có cách xử lý khác việc chèn trực tiếp `style="..."` vào HTML. Hãy kiểm thử đúng luồng cập nhật giao diện mà ứng dụng sử dụng; không suy rằng `style-src` sẽ ngăn mọi thay đổi hình thức từ script đã được phép chạy.

## 6. Hai lựa chọn ưu tiên khi phải xử lý mã inline

Đối với cả JavaScript và CSS, cách triển khai dễ kiểm soát nhất thường là **chuyển nội dung ra file riêng** hoặc **cho phép có kiểm soát bằng nonce/hash**.

### 6.1. Chuyển JavaScript inline thành file

Trước khi sửa:

~~~html
<button id="save" onclick="saveDraft()">Lưu</button>
<script>
  function saveDraft() {
    console.log("saved");
  }
</script>
~~~

Sau khi sửa:

~~~html
<button id="save" type="button">Lưu</button>
<script src="/js/draft.js" defer></script>
~~~

~~~javascript
// /js/draft.js — file được phục vụ từ cùng origin
document.getElementById("save").addEventListener("click", () => {
  console.log("saved");
});
~~~

Với `script-src 'self'`, file `/js/draft.js` được phép tải theo CSP, trong khi cách viết handler trực tiếp trong thuộc tính không còn cần thiết.

### 6.2. Chuyển CSS inline thành stylesheet

Trước:

~~~html
<p style="color: darkred; font-weight: bold">Có lỗi</p>
~~~

Sau:

~~~html
<link rel="stylesheet" href="/css/site.css">
<p class="error-message">Có lỗi</p>
~~~

~~~css
/* /css/site.css */
.error-message {
  color: darkred;
  font-weight: bold;
}
~~~

Với `style-src 'self'`, stylesheet được phép tải; trang không còn phụ thuộc vào thuộc tính style inline.

**Vì sao nên ưu tiên cách này?** Script/CSS ở file có URL rõ ràng, dễ kiểm kê và dễ kiểm thử. Tuy nhiên, cách này không tự bảo đảm code an toàn: phải kiểm soát nội dung tệp, origin và luồng deploy.

## 7. Nonce: cho phép đúng thẻ script và style được tin cậy

**Nonce** là giá trị khó đoán, mới cho mỗi response HTML. Server cấp phép cho một số thẻ `<script>` hoặc `<style>` bằng cách gắn giá trị nonce vào cả CSP header lẫn thuộc tính `nonce` của thẻ tin cậy.

Giả sử server tạo nonce `DEMO_RANDOM_VALUE_PER_RESPONSE`, chỉ dùng để minh họa cú pháp:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-DEMO_RANDOM_VALUE_PER_RESPONSE'; style-src 'self' 'nonce-DEMO_RANDOM_VALUE_PER_RESPONSE'; object-src 'none'; base-uri 'self'
~~~

Trong HTML của **chính response đó**:

~~~html
<script nonce="DEMO_RANDOM_VALUE_PER_RESPONSE">
  initializeApp();
</script>

<style nonce="DEMO_RANDOM_VALUE_PER_RESPONSE">
  .banner { color: navy; }
</style>
~~~

Trình duyệt hỗ trợ nonce có thể cho phép các khối script/style trên, trong khi những khối inline không có nonce hợp lệ vẫn bị từ chối. Điều này **không** đồng nghĩa mọi inline handler hoặc inline style attribute có cùng chuỗi ký tự được cấp phép: nonce là cơ chế gắn với những phần tử được hỗ trợ (đáng chú ý `<script>` và `<style>`), không phải cách thêm `nonce` vào `onclick` hoặc `style="..."`.

### Những yêu cầu bắt buộc khi dùng nonce

1. Tạo nonce bằng bộ sinh số ngẫu nhiên **mật mã học**, không dùng chuỗi cố định, timestamp, số tăng dần hoặc giá trị dự đoán được.
2. Tạo giá trị **mới cho từng response HTML**, gắn cùng giá trị vào CSP header và những thẻ tin cậy trên response đó.
3. Đảm bảo dữ liệu do người dùng kiểm soát không có quyền lấy nonce rồi gắn nó vào script bị chèn. Nếu một ứng dụng cho phép kẻ tấn công sửa markup của thẻ script được gắn nonce, CSP không thể bảo đảm an toàn.
4. Phối hợp với bộ render template và cache: header và HTML phải có nonce khớp; cache không được vô tình biến nonce thành một giá trị lâu dài dùng lại cho nhiều người.
5. Tránh đặt CSP nonce trong string hằng của cấu hình Spring Security. `policyDirectives("script-src 'nonce-fixed'")` chỉ ghi chuỗi cố định, không tạo nonce động.
6. Không coi nonce là secret ứng dụng dùng để xác thực người dùng; đó là giá trị CSP theo response, có thể được trình duyệt dùng trong quá trình xử lý tài liệu.

**Không dùng nonce để sửa mọi vi phạm một cách tự động.** Một trang đã có script bên thứ ba hay inline handler không đáng tin thì việc thêm nonce cho chúng chỉ cấp quyền thực thi thêm. Phải xác định mã nào thực sự đáng tin.

## 8. Hash: cấp phép theo nội dung chính xác

Một lựa chọn khác là khai báo hash của đoạn mã inline tin cậy:

~~~http
Content-Security-Policy: script-src 'self' 'sha256-BASE64_HASH_OF_INLINE_SCRIPT'; object-src 'none'
~~~

~~~html
<script>initializeApp();</script>
~~~

Trong ví dụ, `BASE64_HASH_OF_INLINE_SCRIPT` là **ký hiệu thay thế**, không phải hash hợp lệ. Muốn dùng thật, server phải tính SHA-256 trên **đúng chuỗi byte/nội dung script** theo quy tắc CSP và mã hóa Base64. Nội dung thay đổi một ký tự, dấu cách hay xuống dòng có thể làm hash không còn khớp. Không đưa các thẻ `<script>` vào phần nội dung cần hash.

Ví dụ lệnh trong môi trường có OpenSSL để lấy hash của **chính xác** chuỗi `initializeApp();` (không có newline):

~~~bash
printf %s 'initializeApp();' | openssl dgst -sha256 -binary | openssl base64 -A
~~~

Sau đó thêm kết quả vào directive dạng `'sha256-<giá-trị-Base64>'`. Với script inline có xuống dòng hoặc indent, cần tính hash đúng toàn bộ nội dung giữa hai thẻ. Trong nhiều trình duyệt, thông báo vi phạm ở DevTools có thể gợi ý hash cho chính đoạn script bị chặn; vẫn cần xác minh đó là nội dung tin cậy trước khi cấp quyền.

Hash có thể phù hợp với script/style inline nhỏ, **ổn định**. Với đoạn mã nội tuyến thay đổi theo người dùng hoặc phiên, nonce động theo response thường dễ quản lý hơn. Các thuật toán `sha256`, `sha384` và `sha512` là những lựa chọn được CSP hỗ trợ; không tự chế format hoặc dùng hash không đúng encoding.

### Hash cho style block

Cơ chế tương tự áp dụng cho một thẻ `<style>` tin cậy:

~~~http
Content-Security-Policy: style-src 'self' 'sha256-BASE64_HASH_OF_STYLE_BLOCK'
~~~

~~~html
<style>.notice { color: darkred; }</style>
~~~

Vẫn phải tính hash trên **nội dung chính xác** của khối style. Nếu formatter thay đổi whitespace của CSS inline, hash cần được tạo lại.

### Inline attribute không giống inline element

Hash được dùng trực tiếp cho `<script>...</script>` hoặc `<style>...</style>` **không tự động** mở quyền cho event handler như `onclick="..."` hoặc thuộc tính `style="..."`. Một số trường hợp CSP hỗ trợ `'unsafe-hashes'` kết hợp hash để cho phép những nội dung inline attribute có hash khớp.

Ví dụ cú pháp minh họa:

~~~http
Content-Security-Policy: script-src 'self'; script-src-attr 'unsafe-hashes' 'sha256-BASE64_HASH_OF_HANDLER'
~~~

Không dùng placeholder này trong sản xuất. `'unsafe-hashes'` có rủi ro cấp quyền cho đúng chuỗi handler nếu chuỗi đó xuất hiện ở vị trí khác do kẻ tấn công chèn; mức hỗ trợ/diễn giải cũng phụ thuộc trình duyệt. **Ưu tiên chuyển event handler thành `addEventListener` và thuộc tính style thành CSS class.** Chỉ sử dụng hash cho attribute khi đã đánh giá kỹ yêu cầu tương thích và rủi ro.

## 9. unsafe-inline, unsafe-eval và strict-dynamic: hiểu trước khi dùng

Ba từ khóa này thường xuất hiện khi sửa lỗi giao diện hoặc cập nhật framework, nhưng tác động rất khác nhau.

| Từ khóa | Dùng với | Tác động và lưu ý |
|---|---|---|
| `'unsafe-inline'` | Script/style directive tương ứng | Cho phép những hình thức mã inline rộng; làm giảm khả năng chặn nội dung bị chèn |
| `'unsafe-eval'` | Các quy tắc thực thi script | Nới hạn chế đối với những API chuyển chuỗi thành JavaScript như `eval`/`Function`; không giống cấp phép inline handler |
| `'strict-dynamic'` | `script-src` | Chuyển một phần mô hình tin cậy sang script đã được cấp phép bằng nonce/hash; ảnh hưởng cách script tin cậy nạp tiếp script |

### 9.1. Vì sao unsafe-inline nguy hiểm?

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline'
~~~

Trong cấu hình này, nhiều đoạn script inline và handler được phép chạy. Nếu ứng dụng còn lỗi HTML injection, giá trị phòng vệ trước các payload inline giảm đáng kể. Với `style-src 'unsafe-inline'`, các giới hạn đối với inline CSS cũng bị nới lỏng. Một số tương tác giữa `'unsafe-inline'` và nonce/hash có khác biệt theo phiên bản CSP/browser; điều đó không biến việc thêm `'unsafe-inline'` thành phương án sửa lỗi mặc định an toàn.

### 9.2. unsafe-eval không giải quyết cùng lỗi với unsafe-inline

Một số thư viện có thể dùng:

~~~javascript
const fn = new Function("return 2 + 2");
const result = fn();
~~~

Với chính sách script không cho `'unsafe-eval'`, trình duyệt có thể từ chối thao tác biên dịch chuỗi như trên. Hướng xử lý ưu tiên là thay thư viện hoặc dùng bản build không yêu cầu đánh giá chuỗi thành code; chỉ cấp phép `'unsafe-eval'` khi đã cân nhắc rủi ro và có căn cứ cụ thể. Nếu ứng dụng dùng WebAssembly, còn có các quy tắc liên quan như `'wasm-unsafe-eval'` mà cần xem xét riêng theo trình duyệt hỗ trợ.

### 9.3. strict-dynamic dành cho thiết kế nâng cao

Ví dụ một policy có nonce:

~~~http
Content-Security-Policy: script-src 'nonce-NONCE_PER_RESPONSE' 'strict-dynamic'; object-src 'none'; base-uri 'none'
~~~

Ở trình duyệt hỗ trợ, `'strict-dynamic'` cho phép sự tin cậy từ script được xác thực bằng nonce/hash lan sang những script mà nó tải động theo các điều kiện của CSP; đồng thời có thể khiến host allowlist/`'self'` bị bỏ qua cho kiểm tra script tương ứng. **Đừng thêm `'strict-dynamic'` khi chưa hiểu cách frontend nạp script**, đặc biệt khi ứng dụng đang dựa vào allowlist nguồn.

Để giữ tương thích với trình duyệt khác phiên bản, có thể cần thiết kế fallback phù hợp và kiểm thử trên browser mục tiêu. Đây là chủ đề mở rộng; với ứng dụng server-rendered đơn giản, chuyển script ra file cùng origin hoặc dùng nonce/hash đúng cách thường dễ vận hành hơn.

## 10. Thiết kế CSP thực tế cho ứng dụng có script và style

Giả sử dashboard chạy ở `https://app.example.com`, phục vụ file JS/CSS cùng origin, hiển thị ảnh từ chính origin, gọi API tại `https://api.example.com` và không cho trang khác nhúng dashboard.

Một chính sách khởi đầu:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self'; style-src-attr 'none'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

**Những điều chính sách này cho phép hoặc chặn:**

| Hành vi | Dự đoán theo CSP | Chỉ thị |
|---|---|---|
| Nạp `/js/app.js` | Cho phép | `script-src 'self'` |
| Nạp `https://unknown.example/x.js` | Chặn | `script-src` |
| `<script>alert(1)</script>` không nonce/hash | Chặn | `script-src` |
| `onclick="..."` | Chặn | `script-src-attr 'none'` hoặc fallback |
| Nạp `/css/app.css` | Cho phép | `style-src 'self'` |
| `<style>...</style>` không nonce/hash | Chặn | `style-src` |
| `style="color:red"` | Chặn | `style-src-attr 'none'` hoặc fallback |
| Gọi `fetch("https://api.example.com/profile")` | Được phép theo CSP; còn phụ thuộc CORS của API | `connect-src` |
| Nạp ảnh cùng origin | Cho phép | `img-src 'self'` |
| Website khác nhúng dashboard bằng iframe | Chặn | `frame-ancestors 'none'` |

“Cho phép” trong bảng là **không bị policy CSP này từ chối**. Các chính sách bảo mật khác, CORS, kết nối mạng, server 404/500 hoặc những CSP thực thi khác vẫn có thể tác động.

### Nếu buộc phải dùng một số inline block

Ứng dụng có thể giữ chính sách tệp cùng origin và bổ sung nonce **động**:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' 'nonce-VALUE_PER_RESPONSE'; script-src-attr 'none'; style-src 'self' 'nonce-VALUE_PER_RESPONSE'; style-src-attr 'none'; img-src 'self'; object-src 'none'; base-uri 'self'
~~~

Script và style block có nonce khớp được cho phép; inline handler và style attribute vẫn bị từ chối theo các directive dành cho attribute. Chính sách minh họa chưa mở `connect-src`, `font-src` hay các nguồn khác; khi dùng thật phải bổ sung đúng nhu cầu ứng dụng.

## 11. Cấu hình Spring Security Servlet với policy tĩnh

Trong ứng dụng Spring MVC trên Servlet stack, sử dụng `SecurityFilterChain` và DSL dành cho headers:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {
    private static final String CSP_POLICY =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "script-src-attr 'none'; " +
            "style-src 'self'; " +
            "style-src-attr 'none'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.com; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );
        return http.build();
    }
}
~~~

Spring Security đưa chuỗi directive do ứng dụng cung cấp vào header `Content-Security-Policy` trên những response đi qua chain áp dụng. Cấu hình này **không tự tạo nonce hoặc hash**. Với Servlet, cũng có thể dùng `ContentSecurityPolicyHeaderWriter` nếu dự án đăng ký header writers trực tiếp, nhưng hai cách không cần được chồng lên nhau cho cùng một policy.

### Khi nào cần policy theo từng response?

Nếu template HTML chứa script/style inline hợp lệ và dùng nonce, giá trị CSP phải thay đổi theo **mỗi response**. Không tạo nonce ở cấp hằng `static final` hoặc cấu hình `application.yml`. Cần thiết kế thành phần tạo nonce trước khi render view, truyền vào template model/request và ghi header khớp với nonce đó trước khi response được commit.

Đây là một ví dụ **Servlet filter minh họa** cho luồng tạo nonce và gắn header (cần đăng ký đúng một lần trong dự án):

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonceFilter extends OncePerRequestFilter {
    private final SecureRandom secureRandom = new SecureRandom();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        byte[] randomBytes = new byte[16];
        secureRandom.nextBytes(randomBytes);
        String nonce = Base64.getEncoder().encodeToString(randomBytes);

        // View/template cần đọc đúng thuộc tính này từ request.
        request.setAttribute("cspNonce", nonce);

        response.setHeader(
            "Content-Security-Policy",
            "default-src 'self'; " +
            "script-src 'self' 'nonce-" + nonce + "'; " +
            "style-src 'self' 'nonce-" + nonce + "'; " +
            "object-src 'none'; base-uri 'self'; form-action 'self'"
        );

        chain.doFilter(request, response);
    }
}
~~~

**Đây là đoạn minh họa cơ chế, chưa phải cấu hình production hoàn chỉnh.** Cần xác định URL nào thực sự trả HTML, vị trí đăng ký và thứ tự filter, cách template nhận nonce, hành vi redirect/error/cache và những security header còn lại. Nếu đã có `http.headers().contentSecurityPolicy(...)` cho cùng response, không để cấu hình đó vô tình ghi đè policy nonce; hãy có một chủ thể rõ ràng chịu trách nhiệm header cuối cùng.

Với Thymeleaf, có thể truyền nonce từ request/model đến thẻ được tin cậy:

~~~html
<!-- Ví dụ template khi cspNonce đã được cung cấp trong request/model -->
<script th:attr="nonce=${cspNonce}">
  initializeApp();
</script>
<style th:attr="nonce=${cspNonce}">
  .banner { color: navy; }
</style>
~~~

Khi HTML đã được render, cả hai thuộc tính nonce phải nhận **đúng giá trị** xuất hiện trong CSP header của response đó. Không gắn nonce vào markup do người dùng kiểm soát.

## 12. Cấu hình Spring Security Reactive/WebFlux

Với WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Chính sách tĩnh về script/style giữ nguyên ý nghĩa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
                "default-src 'none'; " +
                "script-src 'self'; " +
                "script-src-attr 'none'; " +
                "style-src 'self'; " +
                "style-src-attr 'none'; " +
                "img-src 'self'; " +
                "font-src 'self'; " +
                "connect-src 'self' https://api.example.com; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "form-action 'self'; " +
                "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Nếu WebFlux server-rendered frontend cần nonce động, nguyên tắc vẫn giống Servlet: một WebFilter/chuỗi xử lý request tạo nonce, cung cấp nonce cho renderer và đặt header tương ứng trên HTTP response trước khi commit. Không bê nguyên `HttpServletRequest`, `OncePerRequestFilter` hoặc `ContentSecurityPolicyHeaderWriter` của Servlet sang reactive chain; đây là hai API khác nhau.

Trong kiến trúc frontend tách khỏi backend (ví dụ HTML/JavaScript được phát từ CDN, Spring WebFlux chỉ trả JSON), **CSP của tài liệu HTML phải xuất từ hệ thống phục vụ HTML**. Một CSP gắn lên response API không tự trở thành chính sách của trang được phát từ origin khác.

## 13. Kiểm thử header và hành vi của trình duyệt

### 13.1. Kiểm thử response của Servlet

Với Spring Security filters được bật và một route HTML hợp lệ như `/dashboard`, có thể dùng MockMvc:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("style-src 'self'")
    ));
~~~

Test trên chỉ chứng minh **server xuất header**, không chứng minh inline code đã bị chặn. Với filter nonce động, test cần kiểm tra nonce trong header khác nhau giữa các response và khớp nonce trong HTML của **chính response đó**, nhưng không nên kiểm tra bằng một nonce được hard-code.

### 13.2. Kiểm thử WebFlux

~~~java
// Trong lớp test có WebTestClient và route /dashboard.
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*"
    );
~~~

### 13.3. Ma trận hành vi trên browser

Trên trang demo có CSP `script-src 'self'; style-src 'self'`, không có nonce/hash và không khai báo chỉ thị chi tiết nới lỏng:

| Tình huống | Kết quả dự kiến về CSP |
|---|---|
| Tải `/js/app.js` từ cùng origin | Được phép |
| Tải script từ origin không nằm trong policy | Bị chặn |
| `<script>console.log(1)</script>` | Bị chặn |
| `onclick="alert(1)"` | Bị chặn |
| `href="javascript:alert(1)"` | Bị chặn khi cố thực thi |
| Tải `/css/app.css` từ cùng origin | Được phép |
| `<style>.x{color:red}</style>` | Bị chặn |
| `style="color:red"` | Bị chặn |
| Thẻ script/style inline có nonce hợp lệ trong policy tương ứng | Được phép theo điều kiện nonce |
| Thẻ inline với nonce không khớp, không có hash phù hợp | Bị chặn |

Quy trình kiểm chứng:

1. Trong Network của DevTools, chọn request **tài liệu HTML**; xem header CSP thực tế.
2. Thử từng trường hợp bằng một trang kiểm thử do bạn kiểm soát, quan sát Console/Issues để đọc directive gây chặn.
3. Khi thẻ script/style hợp lệ dùng nonce/hash, kiểm tra nonce được gắn vào đúng thẻ và CSP header của đúng response.
4. Phân biệt báo cáo của `Content-Security-Policy-Report-Only` với chặn do `Content-Security-Policy`. Report-Only tự nó **không chặn** hành vi mà chỉ ghi nhận vi phạm.
5. Kiểm thử trong những trình duyệt mục tiêu, nhất là khi dùng `script-src-elem`/`script-src-attr`, `style-src-elem`/`style-src-attr` hoặc `'strict-dynamic'`.

Đừng chỉ chạy `alert(1)` trong DevTools Console rồi kết luận CSP có hoặc không bảo vệ trang. Mã chạy từ Console có thể chịu điều kiện khác với HTML/DOM được phân tích từ trang. Cần thử đúng điểm chèn và đường thực thi của ứng dụng.

## 14. Chẩn đoán xung đột triển khai

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Bấm nút không có tác dụng | Handler `onclick` nội tuyến bị `script-src` hoặc `script-src-attr` chặn | Chuyển sang `addEventListener` trong file JS tin cậy |
| Trang báo lỗi khi chạy script ở template | `<script>` inline không có nonce/hash được phép | Chuyển ra file hoặc phát nonce/hash đúng cơ chế |
| CDN script bị chặn nhưng script nội bộ hoạt động | `script-src`/`script-src-elem` không cho CDN | Cân nhắc tự phục vụ hoặc thêm chính xác nguồn đã đánh giá |
| JS từ `'self'` vẫn bị chặn | Có `script-src-elem` chuyên biệt hoặc nhiều CSP thực thi khác | Đọc đầy đủ header và chuỗi fallback |
| CSS biến mất sau khi bật CSP | Stylesheet ngoài không nằm trong `style-src`/`style-src-elem` | Khai báo đúng nguồn CSS |
| CSS-in-JS hoặc component library bị mất style | Thẻ `<style>` động hoặc thuộc tính style bị hạn chế | Chọn cách render/style tương thích; đánh giá nonce/hash |
| Hash script không khớp sau deploy | Whitespace/build output thay đổi | Tính lại hash từ nội dung được trình duyệt nhận |
| Nonce xuất hiện trong header nhưng script vẫn bị chặn | Nonce trong HTML khác header, thẻ không được cấp nonce hoặc policy khác chặn | Kiểm tra response HTML và tất cả CSP header |
| Nonce cố định giữa nhiều response | Dùng hằng hoặc cache không đúng | Thiết kế phát nonce theo response và điều chỉnh cache |
| `new Function(...)` bị chặn | Policy hạn chế đánh giá code từ chuỗi | Loại bỏ nhu cầu `eval`/`Function` hoặc đánh giá `'unsafe-eval'` rất thận trọng |
| Script không lỗi CSP nhưng fetch thất bại | `connect-src` hoặc CORS của API có thể chặn ở bước khác | Tách phân tích CSP kết nối và response CORS |
| Header CSP có trong API nhưng trang thiếu | Frontend HTML do server/CDN khác trả | Đặt policy ở response HTML thực tế |

### Các nguyên tắc khi sửa lỗi

- Đọc **tên directive hiệu lực** mà DevTools thông báo; đừng nới `default-src` nếu lỗi chỉ ở script hoặc style.
- Nếu `script-src-elem` hoặc `style-src-elem` đã khai báo, đừng kỳ vọng `script-src`/`style-src` tự mở rộng quyền cho phần tử.
- Không thêm `'unsafe-inline'` hoặc `'unsafe-eval'` chỉ để làm cảnh báo biến mất.
- Tránh ghép các giá trị từ request, hostname tùy ý hay input người dùng vào CSP header; chính sách phải xuất phát từ cấu hình tin cậy.
- Xác định response nào do Spring Security chain phục vụ và response nào bị reverse proxy/CDN chỉnh sửa. Khi có nhiều CSP thực thi, trình duyệt áp dụng **tất cả** chính sách chứ không lấy chính sách cuối cùng làm giá trị duy nhất.
- Khi triển khai policy chặt lên sản phẩm đang chạy, có thể dùng header `Content-Security-Policy-Report-Only` để quan sát trước, rồi chuyển sang header thực thi sau khi xử lý những vi phạm hợp lệ.

## 15. Bài thực hành tổng hợp

**Tình huống:** Một dashboard Spring MVC có file JS và CSS cùng origin, một widget dùng inline handler và một component dùng style block tạo lúc render. Nhóm phát triển muốn chặn mã chèn nhưng giữ chức năng của dashboard.

1. Thiết lập CSP với `script-src 'self'; style-src 'self'` và kiểm tra response HTML trong DevTools.
2. Thử `<script>console.log('test')</script>`, thuộc tính `onclick="alert('test')"` và `<style>.test{color:red}</style>` trong môi trường kiểm thử; ghi lại directive chặn từng trường hợp.
3. Chuyển handler `onclick` sang `addEventListener` trong file `/js/app.js`; chuyển style attribute sang CSS class. Xác nhận tính năng vẫn hoạt động mà không cần `'unsafe-inline'`.
4. Với một script/style block hợp lệ cần giữ inline, thiết kế nonce ngẫu nhiên theo response. Kiểm tra nonce khớp CSP header và HTML; xác minh một khối inline không được cấp nonce vẫn bị chặn.
5. Nếu script/style ổn định, thử hash và ghi nhận ảnh hưởng của việc thay một ký tự hoặc thêm newline.
6. Bổ sung `script-src-attr 'none'` và `style-src-attr 'none'` rồi kiểm tra cách trình duyệt xử lý thuộc tính inline. Ghi rõ kết quả ở từng browser mục tiêu.
7. Dùng `Content-Security-Policy-Report-Only` để đánh giá policy mới trên một trang mẫu trước khi chuyển sang chế độ thực thi.
8. Tái hiện cấu hình tương tự ở một ứng dụng WebFlux; đối chiếu tên header và hành vi browser, không chỉ kiểm tra code server.

**Câu hỏi tự đánh giá:**

1. Vì sao `script-src 'self'` không cấp quyền cho `<script>...</script>`?
2. `script-src-elem` và `script-src-attr` khác nhau ở những điểm nào? Khi thiếu chúng, trình duyệt dùng fallback nào?
3. Vì sao `style-src 'self'` vẫn có thể chặn một thuộc tính `style="..."`?
4. Sự khác nhau giữa nonce cho thẻ `<script>` và hash cho mã inline là gì? Khi nào chọn mỗi cơ chế?
5. Vì sao nonce cần thay đổi theo response và phải đồng bộ giữa header với HTML?
6. Tại sao một hash cho thẻ script không tự cấp phép cho `onclick` có cùng nội dung?
7. `'unsafe-inline'` và `'unsafe-eval'` điều khiển những nguy cơ khác nhau như thế nào?
8. Nếu JavaScript hợp lệ được tải từ CDN nhưng `fetch` vẫn lỗi, nên kiểm tra thêm directive và cơ chế nào?

## 16. Ghi nhớ

`script-src` và `style-src` là hai directive cốt lõi của CSP để giới hạn **JavaScript** và **CSS**. Cho phép file từ `'self'` không đồng nghĩa cho phép nội dung inline. Khi dùng CSP Level 3, `script-src-elem`/`script-src-attr` và `style-src-elem`/`style-src-attr` giúp chỉ rõ quy tắc cho phần tử và thuộc tính, nhưng cũng làm thay đổi chuỗi fallback cần kiểm thử.

Với nội dung inline hợp lệ, hãy ưu tiên chuyển sang file an toàn; khi cần thiết, dùng nonce ngẫu nhiên theo response hoặc hash đúng nội dung, tránh mở `'unsafe-inline'`/`'unsafe-eval'` tùy tiện. Trong Spring Security Servlet hoặc WebFlux, ứng dụng cung cấp chuỗi directive và trả header trên **tài liệu HTML thực sự**; trình duyệt quyết định hành vi bị chặn. CSP chỉ là một lớp phòng vệ bên cạnh escape/sanitize, CSRF, CORS, HSTS, HTTP firewall và bảo vệ session.
