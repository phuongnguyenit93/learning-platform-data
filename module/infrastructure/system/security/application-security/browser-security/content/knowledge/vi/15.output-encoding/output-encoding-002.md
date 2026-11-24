# HTML encoding: đưa dữ liệu không tin cậy vào HTML an toàn

> **Chương:** Output encoding  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

HTML encoding là kỹ thuật chuyển các ký tự có ý nghĩa đặc biệt trong HTML thành **character reference** để trình duyệt hiển thị chúng như dữ liệu thay vì diễn giải chúng như cú pháp. Đây là một biện pháp nền tảng để ngăn Cross-Site Scripting (XSS) khi ứng dụng hiển thị văn bản do người dùng cung cấp.

Tuy nhiên, không có một phép encode duy nhất an toàn cho mọi vị trí trong tài liệu HTML. Văn bản trong text node, giá trị thuộc tính, URL, JavaScript, CSS và HTML được phép đều có quy tắc phân tích khác nhau. Muốn phòng XSS đúng cách, cần xác định **ngữ cảnh output**, dùng API hoặc encoder tương ứng và giữ nguyên dữ liệu gốc cho đến lúc xuất ra.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao HTML parser có thể biến dữ liệu đầu vào thành phần tử hoặc thuộc tính có thể thực thi.
2. Phân biệt HTML text context với quoted attribute context, URL attribute, JavaScript, CSS và raw-text elements.
3. Encode đúng các ký tự HTML quan trọng như `&`, `<`, `>`, dấu nháy kép và nháy đơn.
4. Chọn `textContent`, DOM API và template auto-escaping thay cho các HTML sink nguy hiểm.
5. Phân biệt output encoding với input validation, URL validation và HTML sanitization.
6. Nhận diện lỗi double encoding, encode sai ngữ cảnh và đánh dấu dữ liệu là safe một cách tùy tiện.
7. Dùng CSP và Trusted Types như các lớp phòng vệ bổ sung.
8. Thực hành quan sát HTML encoding bằng Node.js trên localhost.

## 1. Vì sao cần HTML encoding?

### 1.1 Browser không biết dữ liệu nào là đáng tin

Trình duyệt nhận một tài liệu HTML và chạy HTML parser. Parser không biết đoạn ký tự nào do lập trình viên viết và đoạn nào do người dùng nhập. Nếu ứng dụng ghép dữ liệu trực tiếp vào HTML, parser sẽ xử lý ký tự đặc biệt theo cú pháp HTML.

Ví dụ ứng dụng muốn hiển thị tên người dùng:

~~~js
const name = '<strong>Admin</strong>';
container.innerHTML = '<p>Hello ' + name + '</p>';
~~~

Browser không hiển thị chuỗi `<strong>Admin</strong>` như văn bản. Nó tạo một phần tử `<strong>` thật và hiển thị chữ Admin in đậm.

Nếu dữ liệu có markup nguy hiểm, cùng cơ chế này có thể tạo phần tử, event handler hoặc URL kích hoạt script. Lỗi xảy ra vì **dữ liệu đã đi vào một parser sink như cú pháp HTML**.

### 1.2 HTML encoding thay đổi cách parser diễn giải ký tự

Các character reference thường dùng:

| Ký tự | Dạng encode |
|---|---|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| `"` | `&quot;` |
| `'` | `&#x27;` |

Ví dụ:

~~~text
Dữ liệu gốc:
<strong>Admin & user</strong>

Sau HTML encoding:
&lt;strong&gt;Admin &amp; user&lt;/strong&gt;
~~~

Khi parser xử lý HTML, các character reference được giải mã thành ký tự để hiển thị. Nhưng chúng không được hiểu như dấu mở thẻ hay dấu phân cách attribute ở vị trí ban đầu.

Kết quả hiển thị là:

~~~text
<strong>Admin & user</strong>
~~~

Đoạn trên được trình bày như văn bản trong trang, không tạo phần tử strong từ dữ liệu đầu vào.

### 1.3 Encoding phải được thực hiện tại nơi xuất dữ liệu

Không nên lưu sẵn HTML-encoded text vào database như thể đó là dữ liệu gốc. Cùng một nội dung có thể được dùng ở HTML text, JSON, email, CSV hoặc URL; mỗi ngữ cảnh cần cách xử lý riêng.

Mô hình phù hợp:

~~~text
Input không tin cậy
       ↓
Validate theo quy tắc nghiệp vụ
       ↓
Lưu dữ liệu gốc/canonical
       ↓
Khi render: xác định output context
       ↓
Encode đúng context hoặc dùng safe API
       ↓
Browser parse và hiển thị
~~~

**Output encoding là biện pháp theo ngữ cảnh tại điểm sử dụng.** Nó không thay thế validation, authorization, sanitizer hay kiểm tra URL.

## 2. HTML parser có nhiều ngữ cảnh

### 2.1 Text node context

Ví dụ:

~~~html
<p>Xin chào USER_INPUT</p>
~~~

Nếu USER_INPUT là văn bản không tin cậy, cần encode các ký tự có thể mở markup. Trong HTML text context, tối thiểu phải xử lý `&` và `<`; encoder dùng chung thường xử lý thêm `>`, dấu nháy kép và nháy đơn để dễ tái sử dụng trong quoted attribute context.

Ví dụ:

~~~js
const encoded = escapeHtml(userInput);
container.innerHTML = '<p>' + encoded + '</p>';
~~~

Cách này có thể an toàn cho text node nếu `escapeHtml` được triển khai đúng và chuỗi chỉ được đặt ở đúng ngữ cảnh text. Dùng `textContent` vẫn đơn giản và ít có khả năng sai hơn:

~~~js
const paragraph = document.createElement('p');
paragraph.textContent = userInput;
container.replaceChildren(paragraph);
~~~

`textContent` tạo text node; browser không parse dữ liệu thành HTML.

### 2.2 Quoted attribute context

Ví dụ:

~~~html
<input type="text" value="USER_INPUT">
~~~

Dữ liệu nằm trong giá trị thuộc tính được bao bằng dấu nháy kép. Nếu dữ liệu có dấu nháy kép mà không được encode, nó có thể kết thúc attribute và tạo attribute mới:

~~~text
" autofocus onfocus="alert(1)
~~~

Dùng encoder phù hợp với **quoted HTML attribute value** và luôn đặt giá trị trong dấu nháy:

~~~js
const value = escapeHtmlAttribute(userInput);
const html = '<input type="text" value="' + value + '">';
~~~

Encoder attribute phải xử lý tối thiểu `&`, `<`, `>`, dấu nháy kép và nháy đơn theo quy tắc thư viện. Trong thực tế, dùng DOM API:

~~~js
const input = document.createElement('input');
input.type = 'text';
input.value = userInput;
container.replaceChildren(input);
~~~

Không cần tự tạo HTML string và không phải tự encode attribute.

### 2.3 Unquoted attribute context

Ví dụ:

~~~html
<input value=USER_INPUT>
~~~

Giá trị không có dấu nháy dễ bị phá vỡ bởi khoảng trắng, dấu `=`, dấu backtick, dấu nháy và nhiều ký tự khác. Quy tắc encode cho unquoted attribute phức tạp và dễ sai.

**Không tạo dynamic unquoted attribute.** Luôn dùng quoted attribute trong template hoặc DOM property/API.

### 2.4 Attribute name và event handler

Dữ liệu không tin cậy không được dùng để tạo tên attribute:

~~~js
// Không an toàn: attacker có thể kiểm soát tên attribute.
element.setAttribute(userSuppliedName, userSuppliedValue);
~~~

Ngay cả khi value được HTML-encoded, một attribute nguy hiểm như `onerror` hoặc `onclick` vẫn có thể thực thi JavaScript nếu được gán theo cách phù hợp.

Không đưa dữ liệu vào event handler attribute:

~~~html
<button onclick="USER_INPUT">Click</button>
~~~

HTML encoding không phải JavaScript encoding. Dùng `addEventListener()` với hàm cố định trong source code, rồi truyền dữ liệu như đối số hoặc đọc từ DOM theo cách an toàn.

### 2.5 URL attribute là một ngữ cảnh riêng

Ví dụ:

~~~html
<a href="USER_INPUT">Mở liên kết</a>
~~~

HTML attribute encoding ngăn dữ liệu phá vỡ dấu nháy, nhưng **không làm URL trở nên an toàn**. Giá trị `javascript:...` vẫn là một URL scheme nguy hiểm trong những ngữ cảnh điều hướng phù hợp, dù nó được đặt trong một attribute đã encode.

Cần kết hợp:

1. Parse URL bằng parser chuẩn.
2. Xác định scheme được phép, thường chỉ `https:` và có thể `http:` theo yêu cầu.
3. Nếu nghiệp vụ chỉ cho phép một số website, so sánh origin với allowlist chính xác.
4. Gán vào property `href`/`src` hoặc encode attribute đúng context nếu render HTML.
5. Không cho người dùng kiểm soát tên attribute hay tạo event handler.

Ví dụ:

~~~js
function safeExternalLink(raw) {
  const url = new URL(raw, location.origin);

  if (url.protocol !== 'https:') {
    throw new Error('Only HTTPS links are allowed');
  }

  return url.href;
}

const link = document.createElement('a');
link.textContent = 'Tài liệu';
link.href = safeExternalLink(userInput);
container.replaceChildren(link);
~~~

Đoạn này giới hạn scheme HTTPS. Nếu chỉ cho phép domain cụ thể, cần bổ sung allowlist `url.origin`. Nếu cho phép URL nội bộ, so sánh với `location.origin` và kiểm tra route theo nghiệp vụ.

### 2.6 JavaScript context không phải HTML text context

Ví dụ nguy hiểm:

~~~html
<script>
  const displayName = 'USER_INPUT';
</script>
~~~

HTML encoding không đủ để bảo vệ dữ liệu chèn vào JavaScript string. HTML parser xử lý nội dung của phần tử script theo raw-text rules; chuỗi `</script>` có thể kết thúc phần tử script trước khi JavaScript parser xử lý string.

Không nối dữ liệu không tin cậy vào inline script. Ưu tiên:

- Tải dữ liệu từ endpoint JSON cùng origin.
- Đọc dữ liệu từ DOM bằng `textContent` hoặc property phù hợp.
- Gắn event handler bằng `addEventListener`.
- Nếu buộc phải nhúng JSON vào HTML, dùng serializer được thiết kế cho HTML script context và escape ký tự `<` thành `\u003c` để ngăn chuỗi `</script>` kết thúc phần tử. Không chỉ gọi `JSON.stringify()` rồi nối thẳng vào script.

### 2.7 CSS context cũng có quy tắc riêng

Ví dụ không an toàn:

~~~html
<div style="color: USER_INPUT">Text</div>
~~~

HTML attribute encoding chỉ bảo vệ cấu trúc attribute. Nó không đảm bảo giá trị CSS không chứa cú pháp hoặc URL ngoài ý muốn.

Không ghép dữ liệu không tin cậy vào CSS, `style` attribute, selector hoặc stylesheet. Ưu tiên class CSS cố định:

~~~js
const allowedThemes = new Set(['light', 'dark']);
const theme = allowedThemes.has(userTheme) ? userTheme : 'light';

document.documentElement.classList.toggle(
  'theme-dark',
  theme === 'dark'
);
~~~

Nếu cần giá trị style động, validate theo một tập giá trị nghiệp vụ hẹp (ví dụ số trong khoảng cho phép) và gán qua CSS property phù hợp. Không dùng HTML encoder thay cho CSS validation/encoding.

### 2.8 Raw-text, RCDATA và các vùng đặc biệt

Một số phần tử HTML có quy tắc phân tích khác:

| Vị trí | Quy tắc | Khuyến nghị |
|---|---|---|
| `<script>` | Raw text; end tag `</script>` có ý nghĩa với HTML parser | Không nhúng input trực tiếp; dùng JSON endpoint hoặc serializer an toàn cho script context |
| `<style>` | Raw text; CSS parser xử lý nội dung | Không ghép CSS từ input |
| `<textarea>` | RCDATA; character reference được xử lý, end tag vẫn có ý nghĩa | Dùng `.value`/`textContent` hoặc encoder đúng context |
| `<title>` | RCDATA | Encode dữ liệu text và không tạo markup |
| HTML comment | Có cú pháp kết thúc comment riêng | Không chèn dữ liệu không tin cậy vào comment |
| SVG/XML | Có quy tắc và sink riêng | Không mặc định tái sử dụng encoder HTML cho mọi trường hợp |

Khi không chắc một sink đang ở parser context nào, hãy tránh ghép chuỗi HTML và chuyển sang DOM API hoặc template engine có auto-escaping theo ngữ cảnh.

## 3. Triển khai HTML encoder

### 3.1 Encoder cho text và quoted attribute

Một encoder tối thiểu cho HTML text và quoted attribute có thể xử lý các ký tự sau:

~~~js
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}
~~~

Thứ tự quan trọng: thay `&` trước để các ampersand mới tạo ra từ `&lt;` hoặc `&amp;` không bị encode lần nữa trong cùng lượt.

Ví dụ:

~~~js
const input = '<img src=x alt="demo">';
console.log(escapeHtml(input));
// &lt;img src=x alt=&quot;demo&quot;&gt;
~~~

Đây là encoder minh họa cho **HTML text và giá trị quoted attribute**. Nó không phải sanitizer HTML, không kiểm tra URL scheme, không bảo vệ JavaScript/CSS context và không nên được dùng cho mọi loại markup.

Trong production, ưu tiên encoder của framework hoặc thư viện đã được kiểm tra. Không tự viết encoder phức tạp nếu nền tảng đã có giải pháp chuẩn.

### 3.2 Vì sao phải encode ampersand trước?

Giả sử encoder thay `<` trước, kết quả sẽ tạo ra chuỗi `&lt;`. Nếu sau đó encoder tiếp tục thay `&`, chính entity vừa tạo có thể thành `&amp;lt;` và hiển thị sai thành văn bản `&lt;`.

Thứ tự hợp lý:

1. `&` thành `&amp;`.
2. `<` thành `&lt;`.
3. `>` thành `&gt;`.
4. `"` thành `&quot;`.
5. `'` thành `&#x27;`.

Không gọi encoder lặp lại trên cùng giá trị. Double encoding có thể khiến nội dung hiển thị sai và che giấu lỗi luồng dữ liệu.

### 3.3 Không tự decode dữ liệu đã encode để “sửa” hiển thị

Nếu database chứa `&lt;script&gt;` vì một tầng đã encode, không nên decode tùy tiện rồi đưa vào `innerHTML`. Hãy xác định nguồn dữ liệu và hợp đồng lưu trữ:

- Dữ liệu gốc nên lưu ở dạng canonical, chưa HTML-encoded.
- Output layer encode đúng context mỗi lần render.
- Nếu dữ liệu cũ đã lưu encoded, thực hiện migration có kiểm soát để khôi phục dữ liệu gốc hoặc đánh dấu format rõ ràng.
- Không thử decode nhiều lần đến khi chuỗi “trông bình thường”.

## 4. Safe DOM APIs và HTML sinks

### 4.1 Ưu tiên textContent

Với văn bản thuần:

~~~js
message.textContent = userInput;
~~~

`textContent` tạo hoặc cập nhật text node; chuỗi `<img>` được hiển thị như văn bản. Đây là lựa chọn ưu tiên khi không cần cho người dùng gửi rich HTML.

### 4.2 Dùng property và API DOM cho thuộc tính

Ví dụ tạo form control:

~~~js
const label = document.createElement('label');
label.textContent = 'Tên hiển thị';

const input = document.createElement('input');
input.type = 'text';
input.value = userInput;

label.append(input);
container.replaceChildren(label);
~~~

Các property như `value`, `title`, `alt` và `textContent` phù hợp hơn việc nối HTML string. Với URL property như `href` và `src`, vẫn phải validate scheme/đích theo nghiệp vụ.

### 4.3 Những HTML sink cần xem xét kỹ

Các API sau có thể yêu cầu browser parse chuỗi thành HTML:

- `innerHTML`
- `outerHTML`
- `insertAdjacentHTML()`
- `document.write()` / `document.writeln()`
- `Range.createContextualFragment()`
- Một số API template hoặc framework có chế độ “raw HTML”

Không phải mọi lần sử dụng đều tự động là lỗ hổng. Rủi ro xuất hiện khi dữ liệu không tin cậy đi vào sink mà không được xử lý đúng context. Rà soát source-to-sink: dữ liệu đến từ đâu, được validate/encode/sanitize ra sao và sink cuối cùng là gì.

### 4.4 Khi nào cần render rich HTML?

Nếu sản phẩm cho phép người dùng viết nội dung có định dạng như đoạn văn, link, danh sách hoặc ảnh, HTML encoding toàn bộ sẽ làm markup hiển thị thành chữ. Trường hợp đó cần **HTML sanitizer** theo allowlist, không phải bỏ encoding một cách tùy tiện.

Sanitizer cần:

- Chỉ cho phép tag cần thiết.
- Chỉ cho phép attribute an toàn theo từng tag.
- Loại bỏ event handler như `onclick`, `onerror`.
- Kiểm tra URL trong `href`, `src` và các attribute liên quan.
- Loại bỏ hoặc kiểm soát `style`, SVG, MathML và các namespace phức tạp nếu không thật sự cần.
- Cập nhật thường xuyên và dùng đúng phiên bản.
- Không sanitize bằng regex đơn giản.

Ví dụ khái niệm:

~~~js
// Ví dụ giả định DOMPurify đã được cài và cấu hình đúng.
const clean = DOMPurify.sanitize(untrustedHtml, {
  ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'a'],
  ALLOWED_ATTR: ['href', 'title']
});

container.innerHTML = clean;
~~~

Cấu hình thực tế cần quy định URL protocol, target/rel cho link và những tùy chọn sanitizer theo phiên bản đang dùng. Nếu chỉ cần văn bản, `textContent` đơn giản và an toàn hơn.

## 5. Template engine và auto-escaping

### 5.1 Auto-escaping giảm lỗi thủ công

Nhiều template engine có auto-escaping mặc định. Ví dụ cú pháp minh họa:

~~~html
<p>{{ user.displayName }}</p>
~~~

Trong engine có auto-escaping HTML, giá trị thường được encode khi render vào text context. Tuy nhiên, không phải mọi cú pháp template đều tự động an toàn; hành vi phụ thuộc engine, cấu hình và ngữ cảnh.

Cần kiểm tra:

- Engine có bật auto-escape mặc định không?
- Biểu thức đang nằm trong HTML text hay attribute, script, style?
- Có dùng filter/helper `raw`, `safe`, `unsafe` hoặc tắt escaping không?
- Có truyền chuỗi HTML đã sanitize hay chuỗi chưa xử lý?
- Template có tạo event handler hoặc URL attribute từ dữ liệu không?

### 5.2 “Safe HTML” là lời khẳng định có rủi ro

Các helper như `safe`, `raw`, `dangerouslySetInnerHTML` thường bỏ qua auto-escaping hoặc đưa HTML trực tiếp vào sink. Chỉ dùng khi dữ liệu đã được sanitize bằng một quy trình đáng tin cậy, có allowlist rõ và phù hợp với context cuối cùng.

Không đánh dấu dữ liệu là safe chỉ vì nó đến từ database, người dùng nội bộ, CMS hoặc API của công ty. Dữ liệu có thể đã bị đầu độc từ một nguồn khác.

### 5.3 Encode đúng nơi, đúng một lần

Một lỗi thường gặp là encode ở controller rồi template engine lại auto-escape. Kết quả bị double encoding. Lỗi khác là tắt auto-escape vì “dữ liệu đã encode”, sau đó một trường hợp sử dụng khác đưa dữ liệu vào attribute hoặc JavaScript context.

Hãy thống nhất hợp đồng:

- Controller truyền dữ liệu gốc hoặc kiểu dữ liệu đã sanitize rõ ràng.
- Template engine auto-escape theo context được hỗ trợ.
- Chỉ dùng raw HTML ở một điểm được kiểm soát và có sanitizer phù hợp.
- Không trộn lẫn “đã encode”, “đã sanitize” và “trusted” thành một trạng thái mơ hồ.

## 6. HTML encoding và các lớp phòng vệ khác

### 6.1 Encoding không phải input validation

Validation xác định dữ liệu có hợp lệ theo nghiệp vụ hay không, ví dụ tên hiển thị dài tối đa 80 ký tự. Encoding đảm bảo dữ liệu được diễn giải đúng tại output context.

Ví dụ một chuỗi tên có thể hợp lệ về nghiệp vụ nhưng chứa `<` hoặc `&`. Không nhất thiết phải từ chối tên đó; có thể hiển thị an toàn bằng text encoding.

### 6.2 Encoding không phải URL validation

Một URL có thể được HTML-encoded đúng nhưng vẫn dùng scheme không được phép. Kiểm tra URL phải parse thành phần scheme/origin và áp dụng allowlist. Với link ngoài, thường chỉ cho phép HTTPS; với link nội bộ, giới hạn cùng origin và route.

### 6.3 Encoding không phải sanitizer

- **Encoding:** biến dữ liệu thành văn bản an toàn trong một context cụ thể.
- **Sanitization:** phân tích HTML có cấu trúc và loại bỏ những phần tử/attribute không được phép để giữ lại một tập markup an toàn.
- **Validation:** kiểm tra dữ liệu có đáp ứng quy tắc nghiệp vụ không.
- **Trusted Types:** kiểm soát việc đưa string vào một số DOM XSS sink.
- **CSP:** giới hạn nguồn và hành vi script/resource ở browser.

Các lớp này bổ sung nhau. Không có lớp nào làm cho mọi dữ liệu không tin cậy trở nên an toàn trong mọi ngữ cảnh.

### 6.4 CSP giúp giảm tác động XSS

Ví dụ response header:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
~~~

CSP hạn chế script và tài nguyên được phép tải. Nonce phải được tạo ngẫu nhiên cho mỗi response và chỉ gắn với script tin cậy. Tránh dùng `'unsafe-inline'` nếu mục tiêu là giảm khả năng thực thi inline script.

CSP là defense-in-depth. Nếu output encoding sai, CSP có thể giảm khả năng khai thác nhưng không sửa dữ liệu đã đi vào sai context.

### 6.5 Trusted Types giúp kiểm soát HTML sink

Ở browser hỗ trợ, Trusted Types có thể yêu cầu các sink như `innerHTML` nhận `TrustedHTML` thay vì string tùy ý.

Ví dụ policy minh họa:

~~~js
const policy = trustedTypes.createPolicy('app-html', {
  createHTML(input) {
    return DOMPurify.sanitize(input);
  }
});

container.innerHTML = policy.createHTML(untrustedHtml);
~~~

Policy phải dùng sanitizer đúng cấu hình. Không tạo policy kiểu “trả nguyên input” vì như vậy chỉ chuyển string nguy hiểm thành TrustedHTML mà không lọc gì.

Response header có thể yêu cầu Trusted Types:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Trusted Types không thay thế HTML encoding trong text context, URL validation, server-side authorization hay CSP đầy đủ. Nó là một cơ chế bổ sung giúp tập trung kiểm soát những DOM sink nguy hiểm.

## 7. Những lỗi HTML encoding thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nối input vào `innerHTML` | Browser parse dữ liệu thành markup | Dùng `textContent` hoặc encode đúng HTML context |
| Encode `<` nhưng quên `&` | Entity đầu vào có thể được diễn giải ngoài ý muốn | Encode `&` trước, rồi các ký tự khác |
| Dùng text encoder cho URL | Scheme `javascript:` vẫn có thể nguy hiểm | Parse và allowlist scheme/origin |
| Dùng HTML encoder cho JavaScript string | Có thể thoát string hoặc kết thúc `script` | Không nhúng input vào inline JS; dùng JSON endpoint/serializer đúng context |
| Dùng HTML encoder cho CSS | Không ngăn CSS injection | Tránh CSS động; validate giá trị theo allowlist |
| Đặt dynamic attribute không có quote | Khoảng trắng/dấu phân cách phá cấu trúc | Luôn dùng quoted attributes hoặc DOM API |
| Cho input vào `onclick` | JavaScript có thể được thực thi | Dùng `addEventListener` với code cố định |
| Encode hai lần | Hiển thị `&lt;` thay vì `<` | Encode đúng một lần ở output |
| Bỏ auto-escape bằng `safe/raw` | HTML không tin cậy đi thẳng vào sink | Chỉ dùng sau sanitizer và review |
| Dùng regex để sanitize HTML | Parser khác nhau, dễ bỏ sót cấu trúc | Dùng HTML sanitizer chuyên dụng |
| Cho rằng database data là trusted | Stored XSS qua dữ liệu đã lưu | Xem mọi nguồn ngoài trust boundary là untrusted |
| Cho rằng CSP/Trusted Types thay encoding | Có thể vẫn có sink/context chưa được bảo vệ | Kết hợp các lớp theo vai trò riêng |

## 8. Thực hành: quan sát HTML encoding bằng Node.js

Bài lab dùng Node.js tích hợp, không cần package ngoài. Mục tiêu là so sánh dữ liệu được hiển thị như văn bản với dữ liệu được parse như HTML. Chỉ chạy server trên localhost.

### 8.1 Tạo file `html-encoding-lab.mjs`

~~~js
import { createServer } from 'node:http';

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');
  const input = url.searchParams.get('q') ?? '';

  const safeText = escapeHtml(input);

  const page = [
    '<!doctype html>',
    '<html lang="vi">',
    '<head><meta charset="utf-8"><title>HTML encoding lab</title></head>',
    '<body>',
    '<h1>HTML encoding lab</h1>',
    '<h2>Input được hiển thị bằng HTML encoding</h2>',
    '<p id="result">' + safeText + '</p>',
    '<h2>Giá trị gốc trong response đã được encode</h2>',
    '<pre>' + safeText + '</pre>',
    '<p>Thử query q=%3Cstrong%3EXin%20chao%3C%2Fstrong%3E</p>',
    '</body></html>'
  ].join('\n');

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
  });
  res.end(page);
}).listen(3000, 'localhost', () => {
  console.log('HTML encoding lab: http://localhost:3000');
});
~~~

### 8.2 Chạy và thử

~~~bash
node html-encoding-lab.mjs
~~~

Mở:

~~~text
http://localhost:3000/?q=%3Cstrong%3EXin%20chao%3C%2Fstrong%3E
~~~

Kết quả mong đợi:

- Trang hiển thị nguyên văn `<strong>Xin chao</strong>`.
- Chữ Xin chao không được render thành chữ đậm.
- View Source/Network cho thấy các dấu `<` và `>` đã được chuyển thành character reference.
- DevTools Elements cho thấy nội dung trong `<p>` là text, không có phần tử `strong` do input tạo.

### 8.3 So sánh với sink không an toàn

Đoạn code dưới đây chỉ dùng để nhận diện lỗi, **không thêm vào server lab**:

~~~js
// Không an toàn nếu input là dữ liệu không tin cậy.
result.innerHTML = input;

// An toàn hơn khi chỉ hiển thị văn bản.
result.textContent = input;
~~~

Thử với chuỗi:

~~~text
</p><strong>Injected markup</strong><p>
~~~

Ở sink `innerHTML`, browser tạo markup mới. Với `textContent`, browser hiển thị nguyên văn chuỗi. Bài thử không cần thực thi script để chứng minh sự khác nhau giữa text và HTML parsing.

### 8.4 Thử quoted attribute

Ví dụ tạo input:

~~~js
const field = document.createElement('input');
field.value = '" autofocus data-demo="test';
container.replaceChildren(field);
~~~

Browser đặt chuỗi vào property `value`, không tạo attribute mới. So sánh với việc ghép chuỗi HTML mà không encode:

~~~js
// Không an toàn: dữ liệu có thể kết thúc dấu nháy attribute.
container.innerHTML =
  '<input value="' + userInput + '">';
~~~

Dùng Elements/DOM inspector để kiểm tra cấu trúc attribute. Không cần chạy payload có event handler hoặc script trong lab.

## 9. Chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `<b>` hiển thị thành chữ b thay vì markup | Dữ liệu được HTML-encoded | Đúng nếu sản phẩm chỉ cần hiển thị text; dùng sanitizer nếu cần rich HTML |
| Văn bản hiển thị `&amp;lt;` | Double encoding | Xác định tầng encode; chỉ encode tại output context một lần |
| Dấu nháy làm vỡ attribute | Thiếu quoted attribute encoding | Dùng DOM property hoặc encoder đúng context và quote |
| Link hiển thị đúng nhưng bấm chuyển sang scheme lạ | Chỉ HTML-encoded, chưa validate URL | Parse URL và allowlist scheme/origin |
| CSP báo inline script bị chặn | Policy không cho inline script hoặc nonce/hash thiếu | Dùng external script/nonce hợp lệ; không nới unsafe-inline tùy tiện |
| Trusted Types báo TypeError tại innerHTML | Sink yêu cầu TrustedHTML nhưng nhận string | Dùng sanitizer policy đã review hoặc safe DOM API |
| HTML rich text bị mất định dạng | Encode toàn bộ markup | Dùng sanitizer allowlist có kiểm soát |
| XSS vẫn xảy ra dù text node đã encode | Dữ liệu đi vào sink khác như href, script, style hoặc DOM API | Truy vết source-to-sink và xác định context thật |
| Template render safe làm script chạy | Auto-escaping bị tắt | Gỡ safe/raw hoặc sanitize HTML đúng policy |
| Attribute onclick chạy dù value đã encode | HTML encoding không phải JS sanitization | Không dùng event handler attribute; dùng addEventListener |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chuỗi `<script>` cần được encode khi hiển thị trong HTML text node?

**Đáp án:** Dấu `<` có thể mở một start tag. Encode thành `&lt;` khiến parser tạo ký tự text thay vì tạo phần tử script.

**Câu 2.** Vì sao cần encode `&` trước `<`?

**Đáp án:** Vì encoding dấu `<` tạo ra chuỗi entity có `&`. Nếu thay `&` sau, entity vừa tạo có thể bị encode lần nữa và gây double encoding.

**Câu 3.** HTML encoding trong `href` có đủ để chặn `javascript:` không?

**Đáp án:** Không. HTML encoding bảo vệ cấu trúc attribute; cần parse URL và allowlist scheme/đích theo nghiệp vụ.

**Câu 4.** Có thể dùng HTML encoder cho dữ liệu trong `onclick` không?

**Đáp án:** Không. `onclick` là JavaScript context bên trong attribute; HTML encoding không bảo vệ cú pháp JavaScript. Dùng event listener với code cố định.

**Câu 5.** Vì sao không nên ghép input vào `<script>` dù đã gọi `JSON.stringify()`?

**Đáp án:** HTML parser xử lý end tag `</script>` trước khi JavaScript parser hiểu string. Nếu phải nhúng JSON, cần serializer cho HTML script context, escape `<` thành `\u003c`, hoặc tốt hơn lấy dữ liệu qua JSON endpoint.

**Câu 6.** Khi nào cần sanitizer thay vì HTML encoding?

**Đáp án:** Khi sản phẩm cần cho phép một tập HTML rich text. Sanitizer phân tích markup và chỉ giữ tag/attribute được phép; encoding sẽ biến toàn bộ markup thành text.

**Câu 7.** `textContent` khác `innerHTML` như thế nào?

**Đáp án:** `textContent` tạo text node; `innerHTML` parse chuỗi thành markup. Với dữ liệu text không tin cậy, ưu tiên `textContent`.

**Câu 8.** Template engine bật auto-escaping có bảo đảm mọi ngữ cảnh đều an toàn không?

**Đáp án:** Không. Cần kiểm tra engine và context cụ thể; JavaScript, CSS, URL và các raw HTML sink có quy tắc riêng. Tránh `safe/raw` tùy tiện.

**Câu 9.** CSP và Trusted Types có thay thế output encoding không?

**Đáp án:** Không. Chúng là defense-in-depth và kiểm soát một số hành vi/sink; vẫn phải encode hoặc dùng API an toàn đúng context.

**Câu 10.** Dữ liệu đã lưu trong database có thể được coi là trusted và đưa thẳng vào `innerHTML` không?

**Đáp án:** Không. Dữ liệu có thể đến từ người dùng hoặc hệ thống khác và bị stored XSS. Phải xử lý theo output context ở mỗi điểm render.

## 11. Checklist HTML encoding an toàn

Trước khi render dữ liệu không tin cậy, hãy kiểm tra:

1. **Xác định sink:** text node, quoted attribute, URL, JavaScript, CSS, HTML parser hay rich text?
2. **Ưu tiên API an toàn:** `textContent`, `createElement`, property DOM và `addEventListener`.
3. **Encode đúng context:** dùng HTML text/attribute encoder phù hợp; không dùng một encoder cho JS/CSS/URL.
4. **Quote attribute:** không tạo dynamic unquoted attributes.
5. **Không tạo event handler động:** tránh `onclick`, `onerror` và các `on*` attributes.
6. **Validate URL riêng:** scheme và origin phải nằm trong allowlist; HTML encoding không đủ.
7. **Sanitize rich HTML:** dùng parser/sanitizer chuyên dụng với allowlist tag/attribute.
8. **Giữ auto-escaping:** tránh `safe`, `raw`, `dangerouslySetInnerHTML` nếu không có quy trình kiểm soát.
9. **Encode đúng một lần:** lưu dữ liệu gốc, encode ở output; không double encode/decode.
10. **CSP và Trusted Types:** cấu hình như lớp bổ sung, không coi là thay thế encoding.
11. **UTF-8:** response HTML khai báo `charset=utf-8`, dùng UTF-8 nhất quán giữa server, template và browser.
12. **Kiểm thử source-to-sink:** thử dữ liệu có dấu `<`, `&`, dấu nháy, URL scheme lạ và HTML đóng thẻ trong từng context.

**Ghi nhớ:** HTML encoding biến ký tự có ý nghĩa cú pháp thành dữ liệu hiển thị. Nó chỉ bảo vệ **đúng ngữ cảnh HTML mà encoder được thiết kế cho**. Hãy ưu tiên safe DOM APIs và template auto-escaping; validate URL riêng, sanitize khi cần rich HTML, và dùng CSP/Trusted Types để tăng thêm khả năng phòng vệ XSS.

## Tài liệu tham khảo

- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [WHATWG HTML Standard — Parsing HTML documents](https://html.spec.whatwg.org/multipage/parsing.html)
- [MDN — HTML entities](https://developer.mozilla.org/en-US/docs/Glossary/Entity)
- [MDN — textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent)
- [MDN — innerHTML](https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [W3C — Trusted Types](https://www.w3.org/TR/trusted-types/)

