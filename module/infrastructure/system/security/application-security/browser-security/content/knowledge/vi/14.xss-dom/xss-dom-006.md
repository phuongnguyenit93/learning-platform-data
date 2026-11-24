# Attribute context: phòng vệ XSS khi đưa dữ liệu vào thuộc tính HTML

Ứng dụng web thường đưa dữ liệu người dùng vào thuộc tính HTML để hiển thị tiêu đề, đặt liên kết, chọn ảnh, điền giá trị form hoặc cấu hình thành phần giao diện. Ví dụ, tên tài liệu có thể nằm trong thuộc tính **title**, URL trong **href**, và ảnh đại diện trong **src**. Nếu dữ liệu không tin cậy được ghép vào HTML sai cách, kẻ tấn công có thể thoát khỏi thuộc tính, tạo thuộc tính mới hoặc kích hoạt một ngữ cảnh thực thi JavaScript.

**Attribute context** là ngữ cảnh mà dữ liệu được đưa vào giá trị hoặc tên thuộc tính của phần tử HTML. Cách xử lý an toàn phụ thuộc vào loại thuộc tính và cú pháp bao quanh nó. HTML attribute encoding giúp dữ liệu không phá vỡ cấu trúc của một thuộc tính được trích dẫn, nhưng **không tự làm URL, CSS hoặc JavaScript trở nên an toàn**.

Bài học thuộc chương **XSS và DOM**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web; hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nhận diện dữ liệu nằm trong quoted attribute, unquoted attribute và attribute name.
2. Giải thích vì sao HTML attribute encoding khác với URL validation, JavaScript escaping và CSS handling.
3. Phân loại thuộc tính HTML theo ngữ nghĩa: văn bản, URL, sự kiện, CSS, srcdoc và thuộc tính đặc biệt.
4. Sử dụng DOM API an toàn và tránh ghép dữ liệu không tin cậy vào HTML.
5. Kiểm soát URL bằng parser chuẩn và allowlist scheme/origin phù hợp.
6. Dùng template auto-escaping, CSP và Trusted Types như các lớp phòng vệ bổ sung.
7. Kiểm thử attribute injection và xác minh DOM sau khi trình duyệt parse.

## 2. Attribute context trong HTML parser

HTML được trình duyệt phân tích theo cú pháp. Một phần tử có tên thuộc tính, dấu bằng, giá trị thuộc tính được trích dẫn hoặc không trích dẫn:

```html
<a class="document-link"
   title="Tài liệu hướng dẫn"
   href="https://docs.example.com/guide">
  Mở tài liệu
</a>
```

Trong ví dụ, class, title và href là attribute name; nội dung sau dấu bằng là attribute value. Hai thuộc tính title và href đang dùng dấu nháy kép. Phần chữ “Mở tài liệu” nằm trong text context, không phải attribute context.

Khi dữ liệu không tin cậy được đưa vào giá trị thuộc tính, trình duyệt vẫn phân tích chuỗi theo quy tắc HTML. Nếu ký tự trong dữ liệu làm đóng dấu nháy, thêm thuộc tính hoặc kết thúc thẻ, cấu trúc DOM có thể thay đổi ngoài ý muốn.

### Ví dụ lỗi khi ghép chuỗi

```js
const title = userInput;
const html = '<input value="' + title + '">';
container.innerHTML = html;
```

Nếu userInput là “Tài liệu A”, HTML kết quả có vẻ đúng. Nhưng đầu vào:

```text
" autofocus onfocus="alert(1)
```

có thể đóng giá trị value, tạo thuộc tính onfocus và khiến mã chạy khi phần tử nhận focus. Đây là **attribute injection dẫn tới XSS** do dữ liệu điều khiển cấu trúc HTML.

Một payload kiểm thử khác:

```text
" ><img src=x onerror=alert(1)>
```

Trong môi trường lab, payload này minh họa cách dữ liệu thoát khỏi thuộc tính và tạo phần tử mới. Không thử payload trên hệ thống mà mình không có quyền kiểm thử.

## 3. Quoted attribute và unquoted attribute

### Quoted attribute

Giá trị thuộc tính nên luôn được bao bằng dấu nháy:

```html
<input value="Nội dung">
<input value='Nội dung'>
```

Khi dùng dấu nháy kép, ký tự dấu nháy kép trong dữ liệu phải được encode để không kết thúc giá trị. Một HTML attribute encoder phù hợp thường encode ít nhất:

| Ký tự | Biểu diễn HTML entity |
| --- | --- |
| & | &amp; |
| " | &quot; |
| ' | &#x27; |
| < | &lt; |
| > | &gt; |

Encode cả hai loại dấu nháy là lựa chọn an toàn và nhất quán cho quoted attribute. Ví dụ, đầu vào “Minh "An" & Lan” có thể được biểu diễn:

```html
value="Minh &quot;An&quot; &amp; Lan"
```

Trình duyệt parse giá trị thuộc tính thành chuỗi ban đầu, trong khi cấu trúc HTML vẫn giữ nguyên. Entity được giải mã thành ký tự trong **giá trị thuộc tính**; nó không được parse lại như dấu phân cách cú pháp của attribute đang mở.

### Unquoted attribute

HTML cũng cho phép giá trị không có dấu nháy trong một số trường hợp:

```html
<input value=hello>
```

Nhưng unquoted attribute có tập ký tự phân cách phức tạp hơn: khoảng trắng, tab, xuống dòng, dấu bằng, dấu nháy, dấu backtick và một số ký tự cú pháp khác có thể kết thúc hoặc làm thay đổi giá trị. Điều này khiến việc encode thủ công dễ thiếu sót.

**Quy tắc thực hành: luôn quote giá trị thuộc tính.** Không tạo HTML bằng cách ghép chuỗi và không cố xây dựng encoder tùy chỉnh cho unquoted attribute. Nếu dùng template engine, viết cú pháp thuộc tính có dấu nháy và bật auto-escaping đúng ngữ cảnh.

## 4. HTML attribute encoding bảo vệ điều gì?

HTML attribute encoding bảo vệ **cấu trúc cú pháp của giá trị thuộc tính** khi dữ liệu được đặt vào một quoted attribute thông thường. Nó giúp ngăn dữ liệu chứa dấu nháy hoặc dấu ngoặc nhọn phá vỡ markup.

```js
const element = document.createElement('input');
element.setAttribute('value', untrustedText);
```

Ở đây không có HTML string để parser phân tích lại, nên untrustedText được đặt làm giá trị của attribute value; ký tự trong chuỗi không thể tạo thêm thuộc tính HTML mới. Tuy nhiên, cách này chỉ an toàn về cấu trúc khi **tên thuộc tính là cố định và thuộc tính có ngữ nghĩa phù hợp**.

### Encoding không thay thế semantic validation

```html
<a href="javascript:alert(1)">Mở liên kết</a>
```

Ngay cả khi URL được HTML-encode đúng để không thoát khỏi dấu nháy, giá trị javascript: vẫn có thể mang ngữ nghĩa thực thi khi người dùng kích hoạt liên kết. HTML encoding bảo vệ dấu phân cách của markup; nó không xác nhận scheme hoặc đích URL.

Tương tự:

- Encode dấu nháy không biến onclick thành thuộc tính vô hại.
- Encode ký tự HTML không xác thực CSS trong style.
- Encode URL không chứng minh host đích đáng tin.
- Encode chuỗi không biến srcdoc thành văn bản thuần.

Hãy phân loại **ngữ nghĩa của thuộc tính** trước khi chọn cách xử lý dữ liệu.

## 5. Phân loại attribute context theo ngữ nghĩa

| Loại thuộc tính | Ví dụ | Cách xử lý chính |
| --- | --- | --- |
| Văn bản/giá trị dữ liệu | title, alt, value, placeholder, aria-label, data-* | Dùng DOM property/API phù hợp hoặc HTML attribute encoding trong quoted attribute. |
| URL | href, src, action, formaction, poster, cite, SVG href | Parse và validate URL, allowlist scheme/origin theo chức năng; sau đó gán qua DOM API hoặc encode đúng ngữ cảnh HTML. |
| Event handler | onclick, onerror, onload, onfocus | Không đưa dữ liệu vào; dùng addEventListener() với handler cố định. |
| CSS | style, CSS custom property | Không ghép CSS không tin cậy; dùng CSSOM và validate giá trị theo thuộc tính. |
| HTML lồng bên trong | srcdoc | Xem là một tài liệu HTML riêng; tránh dữ liệu không tin cậy hoặc sanitize bằng thư viện chuyên dụng và sandbox. |
| Attribute name | Tên thuộc tính được tạo động | Không lấy từ dữ liệu không tin cậy; dùng allowlist tên thuộc tính cố định. |
| Điều khiển điều hướng/tải | target, download, rel, sandbox, referrerpolicy | Chỉ cho phép các giá trị được ứng dụng định nghĩa; không coi HTML encoding là validation. |

## 6. Thuộc tính văn bản: ưu tiên DOM API

Với thuộc tính chỉ dùng để hiển thị văn bản hoặc dữ liệu đơn giản, hãy tạo phần tử và gán giá trị qua API:

```js
const input = document.createElement('input');
input.type = 'text';
input.value = userSuppliedName;
input.setAttribute('aria-label', userSuppliedLabel);
container.append(input);
```

Hoặc với nội dung hiển thị:

```js
const heading = document.createElement('h2');
heading.textContent = userSuppliedTitle;
container.append(heading);
```

value, setAttribute() với tên thuộc tính cố định và textContent không yêu cầu dựng HTML string. Chúng tránh việc dữ liệu được parse lại như markup.

Tuy nhiên, không phải mọi thuộc tính đều là văn bản thuần. href, src, style, srcdoc và onclick có ngữ nghĩa đặc biệt. Dùng setAttribute() không tự làm các giá trị đó an toàn.

### data-* không tự thực thi nhưng vẫn có thể trở thành nguồn nguy hiểm

```js
const card = document.createElement('div');
card.dataset.description = untrustedDescription;
```

data-description là dữ liệu tùy chỉnh; bản thân việc gán nó không thực thi HTML. Nhưng nếu mã khác lấy lại dữ liệu rồi đưa vào innerHTML, eval, URL hoặc CSS sink, nguy cơ XSS xuất hiện ở **điểm sử dụng sau đó**.

Hãy theo dõi luồng dữ liệu từ nguồn (URL, API, storage, postMessage, data-*) tới sink. Một thuộc tính lưu dữ liệu an toàn không biến dữ liệu đó thành đáng tin cho mọi ngữ cảnh.

## 7. URL attributes: validate URL trước khi gán

Các thuộc tính như href, src, action, formaction, poster và cite có thể khiến trình duyệt điều hướng, gửi form hoặc tải tài nguyên. Đối với chúng, cần **kiểm tra ngữ nghĩa URL**, không chỉ HTML-encode.

### Ví dụ không an toàn

```js
link.setAttribute('href', userProvidedUrl);
```

Nếu người dùng cung cấp javascript:..., URL vẫn có thể mang scheme nguy hiểm dù DOM API đã đặt giá trị thành công.

### Parse bằng URL và kiểm tra scheme/origin

Ví dụ ứng dụng chỉ cho phép liên kết HTTPS đến một số host tài liệu:

```js
const allowedHosts = new Set([
  'docs.example.com',
  'support.example.com'
]);

function validateDocumentUrl(rawValue) {
  const url = new URL(rawValue, window.location.origin);

  if (url.protocol !== 'https:') {
    throw new Error('Chỉ chấp nhận HTTPS');
  }
  if (!allowedHosts.has(url.hostname)) {
    throw new Error('Host không được phép');
  }
  if (url.username || url.password) {
    throw new Error('Không chấp nhận userinfo trong URL');
  }
  return url;
}

const link = document.createElement('a');
link.textContent = 'Mở tài liệu';
link.href = validateDocumentUrl(userProvidedUrl).href;
link.rel = 'noopener noreferrer';
container.append(link);
```

new URL() chuẩn hóa và parse URL, giúp kiểm tra protocol, hostname, port và các thành phần. Allowlist phải khớp chính xác theo yêu cầu; không dùng includes("example.com"), startsWith("https://trusted.example") hoặc kiểm tra chuỗi sơ sài vì có thể chấp nhận host giả như docs.example.com.attacker.net.

### Allowlist phải phù hợp với từng loại URL

Không có một danh sách scheme đúng cho mọi thuộc tính:

- Liên kết điều hướng có thể chỉ cho phép https: và các đường dẫn tương đối.
- Ảnh có thể cần https: hoặc tài nguyên cùng origin; cân nhắc có cho phép data: hay không.
- Form action nên trỏ đến endpoint do ứng dụng kiểm soát.
- Media src có thể có yêu cầu khác với link tài liệu.
- Không cho phép javascript: trong thuộc tính URL có khả năng thực thi.
- data: có thể chứa nội dung chủ động tùy loại tài nguyên; không cho phép rộng chỉ vì nó tiện nhúng.

Nếu URL được gửi tới server hoặc được dùng để redirect, server cũng phải validate. Kiểm tra ở frontend không phải ranh giới bảo mật đáng tin vì người dùng có thể sửa JavaScript hoặc gửi request trực tiếp.

### Những thuộc tính URL dễ bị bỏ sót

| Thuộc tính | Tác dụng | Lưu ý bảo mật |
| --- | --- | --- |
| href | Điều hướng liên kết | Validate scheme/host; cân nhắc noopener cho tab mới. |
| src | Tải tài nguyên | Có thể tạo request ra bên ngoài và tiết lộ metadata/referrer. |
| action | Đích gửi form | Chỉ cho phép endpoint phù hợp; xem xét CSRF và rò rỉ dữ liệu form. |
| formaction | Ghi đè đích form ở nút submit | Không để dữ liệu không tin cậy chọn endpoint. |
| poster | Tải ảnh poster video | Validate URL và chính sách tải tài nguyên. |
| srcset | Danh sách URL ảnh theo độ phân giải | Cần parser/logic phù hợp; không xử lý như một URL đơn giản. |
| SVG href/xlink:href | Tham chiếu tài nguyên hoặc điều hướng trong SVG | Tránh SVG markup không tin cậy; kiểm soát URL và nội dung SVG. |
| base href | Thay đổi base URL dùng để phân giải URL tương đối | Không cho người dùng kiểm soát; cân nhắc CSP base-uri. |

## 8. Event handler attributes: không nội suy JavaScript vào HTML

Các thuộc tính bắt đầu bằng on như onclick, onerror, onload và onfocus là event handler attributes. Giá trị của chúng được xử lý như mã JavaScript theo cú pháp event handler, không phải chuỗi văn bản bình thường.

Ví dụ cần tránh:

```js
button.setAttribute('onclick', userProvidedCode);
```

Hoặc:

```html
<button onclick="doSomething('USER_INPUT')">Thực hiện</button>
```

HTML attribute encoding không phải JavaScript string encoding. Khi có nhiều parser lồng nhau (HTML parser rồi JavaScript parser), một encoder cho lớp HTML không đủ để bảo vệ lớp JavaScript.

### Dùng addEventListener

```js
const button = document.createElement('button');
button.textContent = 'Xem chi tiết';
button.addEventListener('click', () => {
  openDetailsForRecord(recordId);
});
container.append(button);
```

Handler được viết trong mã ứng dụng, còn dữ liệu chỉ đi vào tham số đã được validate. Không biến dữ liệu người dùng thành mã JavaScript.

### CSP hỗ trợ loại bỏ inline handler

Một Content Security Policy có script-src nghiêm ngặt thường chặn inline event handler. Ví dụ:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'none'
```

Không thêm unsafe-inline chỉ để giữ các onclick cũ hoạt động. Hãy chuyển handler sang addEventListener() và dùng nonce/hash theo thiết kế CSP. CSP là lớp phòng vệ bổ sung; nó không thay thế việc tránh tạo event handler từ dữ liệu không tin cậy.

## 9. CSS attributes và style

style chứa cú pháp CSS, không phải văn bản HTML thông thường:

```html
<div style="color: red; margin: 8px">Thông tin</div>
```

Nếu ghép dữ liệu không tin cậy vào style, dữ liệu có thể phá vỡ cú pháp CSS hoặc đưa vào một giá trị CSS không mong muốn. HTML attribute encoding không kiểm tra tính hợp lệ của CSS.

Tránh:

```js
element.setAttribute('style', userProvidedCss);
```

Ưu tiên cập nhật thuộc tính CSS cụ thể và validate giá trị theo allowlist:

```js
const allowedColors = new Set(['red', 'green', 'blue', 'black']);

function setLabelColor(element, candidate) {
  if (!allowedColors.has(candidate)) {
    throw new Error('Màu không được phép');
  }
  element.style.color = candidate;
}
```

Với kích thước, chỉ nhận kiểu số trong khoảng cho phép rồi thêm đơn vị do ứng dụng kiểm soát:

```js
function setCardWidth(element, candidate) {
  const width = Number(candidate);
  if (!Number.isFinite(width) || width < 120 || width > 800) {
    throw new Error('Chiều rộng không hợp lệ');
  }
  element.style.width = width + 'px';
}
```

Đặc biệt thận trọng với background, backgroundImage, listStyleImage và các thuộc tính nhận URL hoặc hàm CSS. Nếu cần URL trong CSS, validate URL theo chính sách tài nguyên trước; không cho phép người dùng cung cấp một đoạn CSS tùy ý.

## 10. srcdoc: thuộc tính chứa một tài liệu HTML khác

iframe.srcdoc nhận một chuỗi HTML để tạo tài liệu bên trong iframe:

```js
frame.srcdoc = userProvidedHtml;
```

Đây không phải một quoted attribute thông thường. Nội dung chuỗi sẽ được parse như **HTML document** trong browsing context của iframe. HTML attribute encoding bên ngoài không làm nội dung bên trong an toàn.

Ưu tiên không dùng srcdoc với HTML không tin cậy. Nếu sản phẩm cần hiển thị nội dung do người dùng tạo:

- Dùng thư viện HTML sanitizer được duy trì và cấu hình theo nhu cầu.
- Chỉ cho phép một tập phần tử/thuộc tính cần thiết.
- Loại bỏ event handler, script, URL scheme nguy hiểm và các phần tử chủ động không cần thiết.
- Đặt iframe sandbox với quyền tối thiểu; cân nhắc opaque origin bằng cách không cấp allow-same-origin.
- Kiểm tra postMessage nếu frame cần giao tiếp với trang cha.
- Không đưa dữ liệu đã sanitize vào một sink khác mà chưa xét lại ngữ cảnh.

Ví dụ minh họa nội dung tĩnh do ứng dụng kiểm soát:

```html
<iframe
  sandbox
  title="Bản xem trước nội dung"
  srcdoc="<p>Nội dung xem trước tĩnh</p>">
</iframe>
```

Không ghép trực tiếp HTML do người dùng gửi vào thuộc tính srcdoc. Nếu cần xử lý nội dung HTML phong phú, hãy dùng sanitizer có cấu hình và kiểm thử cụ thể; không tự viết bộ lọc bằng regex.

## 11. Attribute name và thuộc tính được tạo động

Rủi ro không chỉ nằm ở giá trị. Nếu tên thuộc tính do người dùng kiểm soát, họ có thể chọn thuộc tính có ngữ nghĩa thực thi hoặc tải tài nguyên:

```js
element.setAttribute(userProvidedAttributeName, userProvidedValue);
```

Ví dụ tên thuộc tính có thể là onerror, onclick, src, href hoặc style. Việc encode giá trị không giúp bảo vệ tên thuộc tính.

Hãy dùng allowlist tên thuộc tính cố định:

```js
const allowedTextAttributes = new Set([
  'title',
  'aria-label',
  'data-description'
]);

function setSafeTextAttribute(element, name, value) {
  if (!allowedTextAttributes.has(name)) {
    throw new Error('Attribute không được phép');
  }
  element.setAttribute(name, value);
}
```

Allowlist này chỉ minh họa cho nhóm thuộc tính văn bản. Không đưa href, src, style, event handler hoặc srcdoc vào cùng nhóm; chúng cần logic kiểm soát riêng.

Trong đa số giao diện, tốt hơn là chọn một component và một tập thuộc tính cố định trong mã thay vì cho phép dữ liệu API định nghĩa cấu trúc HTML tùy ý.

## 12. Template engine và framework

Template engine hiện đại thường có auto-escaping khi nội suy dữ liệu vào HTML text hoặc quoted attribute:

```html
<input value="{{ userDisplayName }}">
```

Trong cú pháp của một số engine, biểu thức được escape tự động; nhưng quy tắc cụ thể phụ thuộc framework, template language và chế độ cấu hình. Cần xác minh rằng:

- Auto-escaping đang bật.
- Giá trị được đặt trong quoted attribute.
- Không dùng helper kiểu raw, safe, dangerouslySetInnerHTML hoặc tắt escaping cho dữ liệu không tin cậy.
- Không nội suy dữ liệu vào event handler, CSS, URL nguy hiểm hoặc attribute name.
- URL vẫn được validate theo scheme/origin sau khi escape.

Ví dụ React:

```jsx
function ProfileLink({ displayName, profileUrl }) {
  const url = validateProfileUrl(profileUrl);
  return (
    <a href={url.href} title={displayName}>
      {displayName}
    </a>
  );
}
```

JSX tự escape giá trị văn bản và thuộc tính thông thường theo cơ chế của React, nhưng ứng dụng vẫn phải validate profileUrl. Không dùng dangerouslySetInnerHTML cho dữ liệu không tin cậy.

Ví dụ với template server-side:

```html
<input type="text" value="{{ escapedDisplayName }}">
```

Tên escapedDisplayName trong ví dụ chỉ thể hiện giá trị được template engine auto-escape theo HTML attribute context; không nên tự encode trước ở tầng business rồi lại encode lần nữa nếu framework đã làm việc đó. Hãy dùng cú pháp chuẩn của engine và tránh double encoding.

### Encode đúng một lần, tại đúng sink

Không nên encode dữ liệu ngay khi nhận từ API rồi lưu phiên bản đã encode vào database. Cùng một dữ liệu có thể cần hiển thị trong HTML text, attribute, JSON hoặc URL; mỗi ngữ cảnh có quy tắc khác nhau.

Quy trình phù hợp:

1. Giữ dữ liệu ở dạng dữ liệu gốc đã validate theo nghiệp vụ.
2. Xác định nơi sử dụng và loại sink.
3. Encode/escape theo đúng ngữ cảnh ngay trước khi render nếu dùng HTML template.
4. Với URL/CSS/event handler, thực hiện semantic validation hoặc thay bằng API an toàn.
5. Tránh encode lặp khiến hiển thị sai hoặc làm các lớp parser hiểu khác nhau.

## 13. Trusted Types và CSP: lớp phòng vệ bổ sung

Trusted Types giúp kiểm soát dữ liệu đi vào một số DOM injection sink như innerHTML, outerHTML, insertAdjacentHTML, document.write và một số API tương tự. Khi bật enforcement, ứng dụng cần cung cấp giá trị Trusted Type phù hợp thay vì tùy tiện đưa string vào sink.

Ví dụ CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Chính sách này yêu cầu Trusted Types cho các sink được hỗ trợ và chỉ cho phép policy có tên app-html. Policy phải được tạo có kiểm soát và nên gọi sanitizer đã được kiểm chứng. Không tạo policy “tin mọi chuỗi” chỉ để làm ứng dụng hết lỗi.

Trusted Types không tự validate:

- URL được gán vào href hoặc src.
- Scheme javascript: hoặc host không tin cậy.
- Giá trị CSS trong style.
- Tên attribute động.
- Dữ liệu nghiệp vụ hoặc quyền truy cập.

CSP script-src có thể hạn chế script và inline event handler; base-uri có thể ngăn thay đổi base URL; object-src 'none' giảm bề mặt plugin cũ. Các chính sách này hỗ trợ giảm tác động của lỗi nhưng không thay thế output encoding và semantic validation.

## 14. Quy trình phân tích một attribute sink

Khi review một đoạn code nhận dữ liệu và đặt vào thuộc tính, hãy đi theo thứ tự:

1. **Tìm nguồn dữ liệu:** form, query string, fragment, API response, postMessage, storage, CMS hoặc nội dung bên thứ ba.
2. **Xác định sink:** template attribute, setAttribute, property assignment, innerHTML, srcdoc, CSSOM hoặc event handler.
3. **Phân loại ngữ nghĩa:** văn bản, URL, CSS, JavaScript, HTML document hay attribute name.
4. **Kiểm tra cấu trúc:** thuộc tính có được quote không, tên thuộc tính có cố định không, có parser lồng nhau không?
5. **Chọn biện pháp:** DOM API an toàn, auto-escaping, HTML attribute encoding, URL allowlist, CSS value validation, sanitizer hoặc loại bỏ sink.
6. **Kiểm tra CSP/Trusted Types:** đây là lớp bổ sung và có enforcement thật hay chỉ report-only?
7. **Kiểm thử DOM cuối cùng:** xem Elements/Console/Network, xác nhận dữ liệu không tạo attribute hoặc node ngoài ý muốn.

### Bảng quyết định nhanh

| Nếu dữ liệu đi vào... | Nên làm |
| --- | --- |
| title, alt, value, aria-label | Gán qua property/DOM API hoặc dùng auto-escaped quoted attribute. |
| href, src, action | Parse URL, validate protocol/host/port theo allowlist, sau đó gán. |
| onclick, onerror, onload | Không gán dữ liệu; dùng addEventListener() với handler cố định. |
| style | Không nhận CSS tùy ý; cập nhật property cụ thể sau validation. |
| srcdoc | Xem là HTML document; tránh hoặc sanitize và sandbox. |
| Attribute name | Không nhận từ user; chọn tên cố định qua allowlist. |
| innerHTML | Tránh; nếu bắt buộc, sanitizer đã kiểm chứng và Trusted Types/CSP. |

## 15. Thực hành: kiểm tra attribute injection trong DevTools

Thực hành trên trang lab local do người học kiểm soát. Dùng dữ liệu giả, không thử trên website của người khác.

### 15.1. Tạo ví dụ cố ý không an toàn

Trong trang lab, tạo một vùng chứa:

```html
<div id="unsafe-output"></div>
<div id="safe-output"></div>
```

Chạy trong Console:

```js
const input = '" autofocus onfocus="alert(1)';
document.querySelector('#unsafe-output').innerHTML =
  '<input value="' + input + '">';
```

Trong tab Elements, mở rộng #unsafe-output và quan sát phần tử input. Dữ liệu đã tạo ra một attribute mới vì dấu nháy đóng giá trị value. Nếu focus input, handler minh họa có thể chạy trong môi trường lab.

### 15.2. Sửa bằng DOM API

```js
const safeInput = document.createElement('input');
safeInput.type = 'text';
safeInput.value = input;
safeInput.setAttribute('aria-label', 'Giá trị thử nghiệm');
document.querySelector('#safe-output').replaceChildren(safeInput);
```

Quan sát Elements: chuỗi đầu vào được giữ như giá trị của input; không xuất hiện onfocus mới. value có thể hiển thị trong property hoặc attribute tùy cách trình duyệt serialize DOM, nhưng cấu trúc không bị dữ liệu phá vỡ.

### 15.3. Kiểm tra URL attribute

Thử:

```js
const link = document.createElement('a');
link.textContent = 'Liên kết thử nghiệm';
link.href = 'javascript:alert(1)';
document.querySelector('#safe-output').append(link);
```

DOM API đã gán được giá trị, nhưng URL vẫn có scheme javascript:. Điều này chứng minh setAttribute hoặc property assignment không tự xác thực URL. Thay bằng hàm validate scheme/origin và kiểm tra giá trị URL trước khi tạo liên kết.

### 15.4. Kiểm tra event handler

Thử trong lab:

```js
const button = document.createElement('button');
button.setAttribute('onclick', 'alert(1)');
button.textContent = 'Inline handler';
document.querySelector('#safe-output').append(button);
```

Sau đó tạo một button khác với addEventListener(). So sánh thuộc tính trong Elements và hành vi dưới CSP chặn inline script. Mục tiêu là xác nhận event handler attribute là một ngữ cảnh JavaScript đặc biệt.

### 15.5. Kiểm tra CSP và Trusted Types

Nếu lab có thể cấu hình response headers:

1. Bật CSP script-src không có unsafe-inline.
2. Quan sát inline event handler bị chặn và lỗi được ghi trong Console.
3. Bật require-trusted-types-for 'script' trên một trang thử nghiệm tương thích.
4. Thử đưa string trực tiếp vào innerHTML; quan sát lỗi enforcement.
5. Tạo policy có sanitizer đã được kiểm chứng nếu ứng dụng thực sự cần HTML.

Không đưa policy tin mọi chuỗi vào production. CSP/Trusted Types phải được triển khai cùng quy trình kiểm thử chức năng và báo cáo vi phạm.

### 15.6. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| DOM trước/sau injection | Dữ liệu không tạo thêm thuộc tính hoặc phần tử ngoài dự kiến trong bản sửa. |
| URL property | Scheme/host được validate trước khi gán. |
| Event listener | Mã xử lý sự kiện nằm trong JavaScript cố định, không trong chuỗi đầu vào. |
| Console dưới CSP | Inline handler hoặc sink vi phạm bị chính sách chặn theo dự kiến. |
| Trusted Types | Sink HTML yêu cầu giá trị tin cậy và policy không tin mọi string. |

## 16. Checklist phòng vệ attribute context

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Quoting | Giá trị attribute có luôn được quote không? | Dùng dấu nháy; không tạo unquoted attribute từ dữ liệu. |
| Attribute name | Tên thuộc tính có cố định không? | Không lấy attribute name từ user input; allowlist nếu cần cấu hình. |
| Text attribute | Dữ liệu có được đặt vào thuộc tính văn bản đúng cách? | DOM API hoặc auto-escaping phù hợp. |
| URL attribute | URL đã được parse và validate scheme/origin? | Allowlist rõ; không dựa vào HTML encoding hoặc kiểm tra chuỗi sơ sài. |
| Event handler | Có nội suy dữ liệu vào on* không? | Không dùng inline handler; dùng addEventListener(). |
| CSS | Có ghép dữ liệu vào style không? | Dùng CSSOM và validate giá trị từng property. |
| srcdoc | Có đưa HTML không tin cậy vào iframe không? | Tránh; nếu cần, sanitizer và sandbox quyền tối thiểu. |
| Template | Auto-escaping có bật và đúng context không? | Không dùng raw/safe bypass cho dữ liệu không tin cậy. |
| DOM sink | Có dùng innerHTML hoặc sink HTML khác không? | Ưu tiên textContent/DOM API; sanitizer và Trusted Types nếu bắt buộc. |
| CSP | Inline handler và nguồn script có bị kiểm soát không? | Chính sách được enforce, không mở rộng unsafe-inline tùy tiện. |
| Logging/testing | Có test payload và kiểm tra DOM cuối cùng không? | Có bằng chứng trong Elements/Console và test regression. |

## 17. Câu hỏi tự kiểm tra

1. Vì sao quoted attribute an toàn hơn unquoted attribute khi xử lý dữ liệu không tin cậy?
2. HTML attribute encoding bảo vệ điều gì và không bảo vệ điều gì?
3. Vì sao href="javascript:..." vẫn nguy hiểm dù dấu nháy và ký tự HTML đã được encode đúng?
4. Vì sao setAttribute('onclick', value) không phải cách an toàn để đặt event handler?
5. Khi nào cần URL validation thay vì chỉ HTML attribute encoding?
6. Vì sao style và srcdoc phải được xem là các ngữ cảnh riêng?
7. Attribute name động tạo ra rủi ro gì? Allowlist cần áp dụng ở đâu?
8. Auto-escaping của framework có thay thế việc validate URL scheme không?
9. Trusted Types bảo vệ một số DOM sink nào và không thay thế semantic validation của thuộc tính nào?
10. Làm thế nào chứng minh dữ liệu đầu vào không tạo event handler hoặc URL nguy hiểm trong DOM cuối cùng?

**Tiêu chí hoàn thành:** người học có thể nhận diện chính xác attribute context, chọn biện pháp theo ngữ nghĩa của từng thuộc tính, tránh nội suy dữ liệu vào event handler/CSS/HTML document, validate URL trước khi gán, và chứng minh bằng DevTools rằng dữ liệu không tin cậy không làm thay đổi cấu trúc DOM hoặc tạo đường thực thi ngoài dự kiến.
