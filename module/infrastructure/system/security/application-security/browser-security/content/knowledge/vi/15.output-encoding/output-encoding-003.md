# Attribute encoding — mã hóa dữ liệu đúng ngữ cảnh thuộc tính HTML

> **Chương:** Output encoding  
> **Mục tiêu:** Hiểu vì sao dữ liệu động trong HTML attribute cần được encode theo đúng ngữ cảnh; phân biệt thuộc tính văn bản, URL, boolean, event handler và style; biết cách dùng template engine hoặc DOM API an toàn, kết hợp validation cho giá trị có ngữ nghĩa đặc biệt và kiểm chứng kết quả trên browser.

## 1. Attribute encoding giải quyết vấn đề gì?

Ứng dụng web thường đưa dữ liệu người dùng hoặc dữ liệu từ API vào thuộc tính HTML, ví dụ:

- Tên hiển thị trong `title` hoặc `alt`.
- Giá trị form trong `value` hoặc `placeholder`.
- Địa chỉ liên kết trong `href`.
- Đường dẫn hình ảnh trong `src`.
- Tên lớp CSS trong `class`.

Nếu nối chuỗi trực tiếp vào HTML, dữ liệu có thể làm thay đổi cấu trúc thuộc tính hoặc tạo thêm thuộc tính ngoài ý muốn.

Ví dụ:

```html
<!-- Không an toàn: dữ liệu được chèn trực tiếp vào HTML source. -->
<input value="USER_VALUE">
```

Giả sử `USER_VALUE` chứa ký tự dấu nháy kép. Dấu nháy có thể đóng giá trị `value` sớm và làm phần còn lại được parser hiểu là markup hoặc thuộc tính mới. Đây là **attribute injection**; tùy vị trí và thuộc tính bị chèn, nó có thể dẫn đến DOM XSS hoặc thay đổi hành vi của giao diện.

**Attribute encoding** biến những ký tự có ý nghĩa cú pháp thành HTML character references phù hợp với ngữ cảnh thuộc tính, để dữ liệu vẫn được hiểu là giá trị của thuộc tính thay vì cấu trúc HTML.

Điểm cốt lõi: encode tại **đầu ra**, ngay nơi dữ liệu được đặt vào HTML attribute, và dùng đúng encoder cho loại ngữ cảnh đó. Không có một phép encode chung an toàn cho HTML text, attribute, JavaScript, CSS và URL.

## 2. HTML parser diễn giải thuộc tính như thế nào?

Trong HTML:

```html
<input title="Tên hiển thị">
<input title='Tên hiển thị'>
```

Giá trị thuộc tính có thể được bao bởi dấu nháy kép hoặc nháy đơn. Cú pháp HTML cũng cho phép giá trị không có dấu nháy trong một số trường hợp, nhưng **không nên dùng dạng unquoted cho dữ liệu động**.

Khi parser đọc một thuộc tính có dấu nháy kép:

1. Dấu nháy kép kết thúc giá trị thuộc tính.
2. Dấu `&` bắt đầu một character reference.
3. Dấu `<` và một số ký tự khác có thể ảnh hưởng đến cách parser xử lý markup.
4. Các ký tự còn lại được lưu thành giá trị thuộc tính theo quy tắc HTML.

Vì vậy, với thuộc tính được bao bằng dấu nháy kép, encoder phải ít nhất xử lý các ký tự có thể phá vỡ cú pháp như `&`, `"`, `<` và `>`. Một encoder attribute đầy đủ thường encode cả dấu nháy đơn để có thể dùng nhất quán trong các ngữ cảnh được hỗ trợ.

Ví dụ giá trị:

```text
O"Reilly & Co. <Support>
```

Khi render trong thuộc tính double-quoted, có thể được biểu diễn:

```html
<input title="O&quot;Reilly &amp; Co. &lt;Support&gt;">
```

Browser giải mã character references khi tạo DOM; giá trị thuộc tính cuối cùng vẫn là văn bản ban đầu. Việc nhìn thấy `&quot;` trong HTML source là bình thường, còn khi đọc `element.title` có thể nhận được dấu nháy kép thực.

## 3. Quy tắc quan trọng: luôn quote thuộc tính

Hãy luôn bao giá trị thuộc tính bằng dấu nháy, kể cả khi giá trị hiện tại chỉ gồm chữ và số:

```html
<!-- Nên dùng -->
<input value="customer-123">

<!-- Tránh dùng với dữ liệu động -->
<input value=customer-123>
```

Unquoted attribute có tập ký tự hợp lệ hẹp hơn và dễ bị phá cấu trúc bởi whitespace, dấu nháy, dấu bằng hoặc một số ký tự cú pháp. Encoder cho double-quoted attribute không mặc nhiên bảo vệ được unquoted context.

Chọn một kiểu quote nhất quán trong template và để template engine thực hiện attribute escaping đúng context. Nếu phải tự encode, encoder phải tương ứng chính xác với loại dấu nháy bao quanh giá trị.

## 4. Mã hóa thuộc tính HTML khác với URL encoding

Hai cơ chế thường bị nhầm:

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| **HTML attribute encoding** | Giữ dữ liệu nằm trong giá trị thuộc tính HTML | `"` thành `&quot;`, `&` thành `&amp;` |
| **URL percent-encoding** | Biểu diễn byte/ký tự trong một thành phần URL | dấu cách có thể thành `%20` |

Ví dụ:

```html
<a href="https://shop.example/search?q=red%20shoes" title="Tìm kiếm">
  Xem kết quả
</a>
```

Nếu URL được chèn vào `href` trong HTML source, ứng dụng cần **hai bước có mục đích khác nhau**:

1. Parse và kiểm tra URL theo chính sách ứng dụng: scheme, host/origin, port và những thành phần được phép.
2. Encode giá trị URL đã được chấp nhận cho HTML attribute context khi render thành markup.

URL percent-encoding không thay thế HTML attribute encoding. Ngược lại, HTML attribute encoding cũng không biến một URL nguy hiểm thành URL an toàn.

Ví dụ, một chuỗi có scheme không được phép vẫn có thể nằm hoàn toàn hợp lệ bên trong dấu nháy HTML. Parser HTML không chịu trách nhiệm xác định liên kết đó có đáng tin hay không.

## 5. Phân loại thuộc tính trước khi đưa dữ liệu vào

Không phải tất cả HTML attribute đều chỉ là văn bản. Trước khi render dữ liệu động, hãy phân loại thuộc tính:

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Văn bản thông thường** | `title`, `alt`, `placeholder`, `value`, `aria-label` | Dùng auto-escaping đúng attribute context hoặc DOM property/setAttribute với tên thuộc tính cố định |
| **URL** | `href`, `src`, `action`, `formaction`, `poster` | Parse URL, allowlist scheme/origin theo nghiệp vụ, rồi mới encode/render |
| **Event handler** | `onclick`, `onerror`, `onload` | Không đưa dữ liệu vào; đăng ký event bằng `addEventListener` với function trong code |
| **Style/CSS** | `style` | Tránh nối CSS tùy ý; dùng CSSOM property và allowlist giá trị |
| **HTML document** | `srcdoc` | Đây là nội dung HTML, không phải URL; cần tránh dữ liệu không tin cậy hoặc dùng sanitizer/iframe isolation đúng cách |
| **Boolean** | `disabled`, `checked`, `autofocus`, `multiple` | Điều khiển bằng boolean/property; không coi chuỗi `"false"` là false |
| **Tên/định danh DOM** | `id`, `name` | Dùng giá trị được kiểm soát, tránh trùng tên và DOM clobbering |
| **Tập giá trị hữu hạn** | `target`, `rel`, `type`, `autocomplete` | Chọn từ allowlist enum phù hợp với chức năng |

**HTML attribute encoding chỉ giải quyết cú pháp của HTML attribute.** Nó không xác thực ý nghĩa của giá trị, không loại bỏ scheme nguy hiểm, không làm JavaScript trong event handler an toàn và không sanitize CSS.

## 6. Thuộc tính văn bản: trường hợp phù hợp cho attribute encoding

Các thuộc tính như `title`, `alt`, `placeholder`, `aria-label` hoặc `value` thường dùng để mang văn bản. Nếu render qua HTML template, hãy dùng template engine có auto-escaping cho HTML attribute context.

Ví dụ minh họa:

```html
<!-- Template có auto-escaping đúng ngữ cảnh -->
<input
  type="text"
  name="displayName"
  value="{{ user.displayName }}"
  aria-label="{{ labels.displayName }}"
>
```

Cú pháp `{{ ... }}` ở đây chỉ là ký hiệu template minh họa; hành vi auto-escaping phụ thuộc engine và chế độ cấu hình. Phải kiểm tra tài liệu framework và xác minh output HTML thực tế.

Nếu template engine cung cấp raw output như `|safe`, `raw`, `unescaped` hoặc API tương tự, không dùng nó cho dữ liệu chưa được kiểm soát. Raw output bỏ qua lớp escaping và có thể mở lại lỗi injection.

### Ví dụ DOM API

Khi cập nhật DOM phía client, API sau đặt dữ liệu thành giá trị thuộc tính mà không parse lại chuỗi thành HTML:

```js
const input = document.querySelector("#display-name");
input.value = userProvidedName;
input.setAttribute("aria-label", userProvidedName);
```

Tên thuộc tính ở đây được cố định trong code và là thuộc tính văn bản thông thường. Đây là cách phù hợp hơn việc nối chuỗi HTML rồi gán vào `innerHTML`.

Tuy nhiên, giá trị của `data-*` hoặc `aria-*` vẫn có thể được JavaScript khác đọc lại và đưa vào sink nguy hiểm. Việc đặt dữ liệu an toàn ở một bước không làm cho mọi bước sử dụng sau đó tự động an toàn.

## 7. URL-valued attributes: phải validate trước khi encode

Các thuộc tính như `href`, `src`, `action`, `formaction` và `poster` mang URL. Chỉ HTML attribute encoding là chưa đủ.

Ví dụ:

```js
function setSafeHref(anchor, input) {
  const url = new URL(input, window.location.origin);

  if (url.protocol !== "https:" && url.origin !== window.location.origin) {
    throw new Error("Chỉ cho phép HTTPS hoặc liên kết nội bộ");
  }

  anchor.href = url.href;
  anchor.rel = "noopener noreferrer";
}
```

Điều kiện trong ví dụ là một chính sách minh họa: nó cho phép HTTPS hoặc URL cùng origin. Ứng dụng thực cần quyết định có cho phép HTTP nội bộ, cổng cụ thể, URL tương đối, domain đối tác hay không. Nếu chỉ cho phép một số website, dùng allowlist origin cụ thể.

Không xác thực URL bằng:

```js
// Sai: chuỗi có thể xuất hiện trong userinfo, path hoặc hostname giả.
if (input.includes("trusted.example")) {
  anchor.href = input;
}
```

Hãy parse bằng `new URL()`, kiểm tra `protocol`, `origin` và các thành phần cần thiết. Cần chú ý:

- `javascript:` và các scheme không phù hợp với nghiệp vụ không được chấp nhận chỉ vì chuỗi nằm trong attribute đã encode.
- `data:`, `blob:` và các scheme đặc biệt chỉ được phép khi có yêu cầu cụ thể và đánh giá riêng.
- URL có username/password không nên được chấp nhận như một đích liên kết thông thường.
- URL tương đối cần được resolve với base URL đã xác định, rồi mới so sánh origin.
- Redirect ở server đích có thể chuyển người dùng sang một host khác; nếu yêu cầu bảo vệ redirect, phải kiểm tra cả luồng redirect.

### `srcset` là trường hợp đặc biệt

`srcset` có cú pháp gồm nhiều URL và descriptor, ví dụ các biến thể ảnh theo mật độ hoặc kích thước. Không xử lý toàn bộ chuỗi bằng một lần encode hoặc một phép tách chuỗi đơn giản. Nếu nhận danh sách URL từ người dùng, parse theo cú pháp phù hợp, xác thực từng URL rồi mới tạo giá trị `srcset`.

## 8. Event handler attribute không phải thuộc tính văn bản

Các thuộc tính bắt đầu bằng `on` như `onclick`, `onerror` hoặc `onload` có thể được browser diễn giải như mã JavaScript. HTML attribute encoding không biến chuỗi JavaScript thành dữ liệu vô hại trong ngữ cảnh này.

Không làm như sau:

```js
// Không gán dữ liệu không tin cậy vào event-handler attribute.
element.setAttribute("onclick", userInput);
```

Hãy đăng ký event bằng function được định nghĩa trong code:

```js
button.addEventListener("click", () => {
  submitForm();
});
```

Nếu cần truyền dữ liệu vào handler, giữ dữ liệu ở biến hoặc thuộc tính văn bản đã được xử lý đúng và kiểm tra kiểu/giá trị trước khi sử dụng. Không biên dịch dữ liệu thành code.

## 9. Style attribute và CSS context

Thuộc tính `style` chứa CSS, không phải văn bản thông thường. HTML attribute encoding chỉ bảo vệ lớp cú pháp HTML bên ngoài; nó không kiểm soát cách CSS parser diễn giải giá trị.

Tránh:

```js
// Không nối CSS tùy ý từ input.
element.setAttribute("style", userProvidedCss);
```

Nếu chỉ cần cho người dùng chọn màu, dùng allowlist:

```js
const allowedColors = new Set(["navy", "teal", "maroon"]);

function setThemeColor(element, input) {
  if (!allowedColors.has(input)) {
    throw new Error("Màu không được hỗ trợ");
  }
  element.style.color = input;
}
```

CSSOM property giúp cập nhật một thuộc tính CSS cụ thể thay vì parse một chuỗi style tùy ý. Với các giá trị phức tạp như URL, kích thước hoặc biểu thức, vẫn cần validation theo grammar và nghiệp vụ.

## 10. Boolean attribute và thuộc tính có tập giá trị giới hạn

Boolean attribute được quyết định chủ yếu bởi **sự hiện diện** của thuộc tính, không phải chuỗi text bên trong:

```html
<input disabled="false">
```

Trong HTML, input trên vẫn bị disabled vì thuộc tính `disabled` có mặt. Nếu dữ liệu là false, hãy bỏ thuộc tính hoặc cập nhật property:

```js
input.disabled = Boolean(isDisabled);
```

Với thuộc tính có tập giá trị hữu hạn, dùng allowlist:

```js
const allowedTargets = new Set(["_self", "_blank"]);

function setTarget(anchor, target) {
  if (!allowedTargets.has(target)) {
    throw new Error("Target không hợp lệ");
  }
  anchor.target = target;
  if (target === "_blank") {
    anchor.rel = "noopener noreferrer";
  }
}
```

Không dùng encoding để thay thế kiểm tra enum. Chuỗi `"administrator"` có thể được encode hoàn toàn hợp lệ nhưng vẫn không phải một giá trị mà ứng dụng muốn chấp nhận.

## 11. Tên thuộc tính phải cố định

Encoder giá trị thuộc tính không bảo vệ được khi **tên thuộc tính** do người dùng kiểm soát. Ví dụ:

```js
// Nguy hiểm: dữ liệu điều khiển cả tên lẫn giá trị attribute.
element.setAttribute(userSuppliedName, userSuppliedValue);
```

Nếu tên trở thành một event handler hoặc thuộc tính có ngữ nghĩa đặc biệt, việc encode value không ngăn được hành vi đó.

Hãy:

- Viết tên thuộc tính cố định trong source code.
- Dùng allowlist nếu ứng dụng thật sự cần chọn một thuộc tính từ dữ liệu.
- Không cho dữ liệu điều khiển tên event handler hoặc tên thuộc tính có thể tải tài nguyên/thực thi.
- Tránh đưa `id` và `name` tùy ý vào DOM toàn cục; các tên này có thể gây DOM clobbering hoặc xung đột với code khác.

## 12. Attribute encoding ở server-side template

Trong server-side rendering, cách an toàn là dùng template engine có auto-escaping đúng context. Ví dụ khái niệm:

```html
<a
  title="{{ product.name }}"
  href="{{ validatedProductUrl }}"
>
  {{ product.name }}
</a>
```

Ở đây:

- `product.name` được encode theo HTML text hoặc attribute context tùy vị trí.
- `validatedProductUrl` phải được parse và kiểm tra scheme/origin trước khi render.
- Engine phải escape cả attribute value và text node theo đúng context.
- Không sử dụng raw/unescaped output cho dữ liệu không tin cậy.

Một số template engine chỉ auto-escape HTML text hoặc có chế độ auto-escape phụ thuộc file/template. Hãy xác nhận engine hỗ trợ context-aware escaping cho thuộc tính, không giả định mọi cú pháp template đều giống nhau.

Nếu tự xây encoder trong hệ thống, ưu tiên thư viện/framework đã được kiểm chứng. Hàm ví dụ dưới đây chỉ minh họa thứ tự thay thế cho một giá trị double-quoted attribute đơn giản:

```js
function escapeDoubleQuotedAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("'", "&#x27;");
}
```

Phải encode `&` trước để không encode lại những ampersand vừa sinh ra. Tuy nhiên, hàm minh họa này **không phải HTML sanitizer, URL validator hay encoder cho mọi context**; không tự thay thế thư viện output encoding đã được kiểm chứng trong production.

## 13. Tránh double encoding và encode sai thời điểm

Output encoding nên được thực hiện **một lần tại sink cuối cùng**:

1. Lưu dữ liệu theo dạng dữ liệu gốc đã được xác thực theo nghiệp vụ.
2. Khi render vào HTML attribute, dùng attribute encoder hoặc auto-escaping phù hợp.
3. Không decode entity sau khi đã encode để “khôi phục” giá trị trước khi đưa vào browser.
4. Nếu dữ liệu chuyển sang context khác, áp dụng xử lý tương ứng cho context mới.

Double encoding có thể khiến người dùng thấy chuỗi `&amp;quot;` thay vì dấu nháy mong muốn. Nguy hiểm hơn, nếu một tầng decode dữ liệu sau khi encode, các ký tự cú pháp có thể xuất hiện trở lại trước khi đến sink.

Không lưu dữ liệu đã HTML-encode như thể đó là dữ liệu sạch. Một giá trị được encode cho HTML attribute có thể không phù hợp khi xuất ra JSON, email, CSV hoặc URL.

## 14. Attribute encoding trong framework và DOM API

Framework thường có cơ chế escape mặc định, nhưng cần biết đâu là ranh giới:

| Nền tảng/cách dùng | Hành vi cần kiểm tra |
| --- | --- |
| JSX/React attribute thông thường | Giá trị thường được escape khi render; `dangerouslySetInnerHTML` bỏ qua cơ chế này |
| Vue interpolation và binding | Text/attribute binding thông thường được xử lý; `v-html` đưa HTML raw vào DOM |
| Angular template binding | Có cơ chế context-aware sanitization; API bypass security trust cần được rà soát |
| Server-side template engine | Kiểm tra chế độ auto-escape và raw output helper của engine cụ thể |
| Vanilla DOM | `setAttribute` với tên cố định và thuộc tính văn bản thường không parse chuỗi thành HTML; URL/style/event vẫn cần policy riêng |

Không dựa vào tên framework để kết luận ứng dụng an toàn. Hãy rà soát:

- Raw HTML escape hatches.
- Binding URL, style hoặc resource URL.
- Attribute name được tạo động.
- Directive/plugin tự gọi `innerHTML`.
- Component nhận HTML/URL từ CMS hoặc API.
- Dữ liệu trong `data-*` được đọc lại và đưa vào sink khác.

## 15. Kiểm thử attribute encoding trong browser

Thực hành trên ứng dụng lab do bạn kiểm soát. Dùng dữ liệu kiểm tra vô hại để quan sát parser, không cần payload thực thi JavaScript.

### Bước 1 — Tạo trường hiển thị thuộc tính

Tạo một input có giá trị động từ query hoặc dữ liệu thử nghiệm:

```html
<input id="preview" title="Tên hiển thị">
```

Thử dữ liệu có:

```text
O"Reilly & Co. <Support>
```

Quan sát HTML response trong Network/View Source và DOM trong Elements. Giá trị thuộc tính phải vẫn là một thuộc tính duy nhất; dấu nháy trong dữ liệu không được tạo thêm attribute.

### Bước 2 — Kiểm tra giá trị DOM

Trong Console:

```js
const input = document.querySelector("#preview");
console.log(input.getAttribute("title"));
console.log(input.title);
```

Hai giá trị có thể thể hiện văn bản đã được parser giải mã từ character references. Hãy xác minh chúng tương ứng với dữ liệu gốc, không tạo node/attribute mới.

### Bước 3 — Kiểm tra URL attribute riêng

Thử một URL HTTPS được cho phép và một URL có scheme bị policy từ chối. Xác minh server/client kiểm tra URL trước khi gán `href`; HTML escaping không được xem là bằng chứng URL hợp lệ.

### Bước 4 — Kiểm tra boolean và event handler

Thử giá trị false cho `disabled` bằng property và xác minh control thực sự được bật. Tìm trong code các phép gán `on*` hoặc tên thuộc tính động; chuyển sang `addEventListener` với handler cố định.

### Bước 5 — Kiểm tra framework raw output

Tìm `dangerouslySetInnerHTML`, `v-html`, raw template helper hoặc API tương tự. Với từng trường hợp, xác định source dữ liệu, context và sanitizer/Trusted Types policy nếu có.

## 16. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Dấu nháy làm mất phần còn lại của attribute | Thiếu attribute encoding hoặc giá trị không được quote | Dùng auto-escaping đúng context và luôn quote |
| Browser tạo thêm thuộc tính ngoài ý muốn | Attribute injection | Encode value, cố định tên thuộc tính, không dùng raw HTML |
| Chuỗi `javascript:` vẫn nằm trong `href` sau khi encode | HTML encoding không kiểm tra URL scheme | Parse URL và allowlist scheme/origin |
| `onclick` vẫn có hành vi dù value đã escape | Event handler là JavaScript context | Không gán dữ liệu vào event attribute; dùng addEventListener |
| Style có hành vi ngoài dự kiến | CSS context bị xử lý như text attribute | Dùng CSSOM và allowlist giá trị |
| Hiển thị `&amp;quot;` trong giao diện | Double encoding hoặc encode sai tầng | Xác định output sink và chỉ encode một lần |
| Framework tự escape nhưng lỗi vẫn xuất hiện | Có raw HTML binding, URL binding hoặc sink khác | Theo dõi source-to-sink và escape hatch |
| `disabled="false"` vẫn bị khóa | Boolean attribute dựa trên sự hiện diện | Dùng property boolean hoặc thêm/bỏ attribute |

## 17. Checklist triển khai attribute encoding

- Luôn quote giá trị thuộc tính HTML.
- Dùng auto-escaping hoặc encoder đúng cho HTML attribute context.
- Encode các ký tự cú pháp như ampersand, dấu nháy và dấu ngoặc nhọn góc theo encoder đã chọn.
- Giữ tên thuộc tính cố định; không cho dữ liệu điều khiển tên hoặc event handler.
- Phân loại URL, style, event, boolean và srcdoc; không coi tất cả là text attribute.
- Validate URL scheme/origin trước khi render vào `href`, `src`, `action` hoặc `formaction`.
- Dùng allowlist cho thuộc tính có tập giá trị giới hạn.
- Dùng DOM property hoặc `setAttribute` với tên cố định cho thuộc tính văn bản; tránh nối HTML và gán `innerHTML`.
- Dùng CSSOM và giá trị CSS được kiểm soát thay vì chuỗi style tùy ý.
- Rà soát raw output helper, framework escape hatch và dữ liệu được tái sử dụng ở sink khác.
- Encode đúng một lần tại output sink; không lưu dữ liệu HTML-encoded như dữ liệu gốc.
- Kiểm thử HTML source và DOM đã parse trong browser, bao gồm các giá trị có dấu nháy, ampersand và Unicode.

## 18. Câu hỏi tự kiểm tra

1. Vì sao dữ liệu trong HTML attribute cần được encode theo context?
2. Vì sao luôn nên quote thuộc tính, kể cả khi giá trị chỉ gồm chữ và số?
3. HTML attribute encoding khác URL percent-encoding như thế nào?
4. Vì sao một URL được encode đúng HTML vẫn có thể dùng scheme không an toàn?
5. Vì sao `onclick` không thể được xử lý như `title`?
6. Vì sao `style` cần kiểm soát theo CSS context?
7. Vì sao `disabled="false"` vẫn có thể làm input bị disabled?
8. Vì sao tên thuộc tính phải cố định hoặc lấy từ allowlist?
9. Trusted template auto-escaping và raw HTML helper khác nhau ở đâu?
10. Vì sao không nên lưu dữ liệu đã HTML-encoded rồi tái sử dụng ở JSON hoặc URL?

**Ghi nhớ:** Attribute encoding giữ dữ liệu nằm trong giá trị thuộc tính HTML thay vì phá cấu trúc markup. Hãy luôn quote thuộc tính, dùng auto-escaping hoặc encoder đúng context, cố định tên thuộc tính và phân loại giá trị trước khi render. URL cần validation riêng; event handler, style và srcdoc cần chính sách riêng; boolean attribute cần boolean property. Encode đúng một lần tại output sink, đồng thời dùng DOM API an toàn và kiểm chứng HTML source lẫn DOM thực tế trên browser.
