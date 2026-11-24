# Contextual output encoding: mã hóa dữ liệu theo ngữ cảnh đầu ra

## 1. Vì sao phải mã hóa đầu ra theo ngữ cảnh?

Một ứng dụng web thường nhận dữ liệu từ người dùng, URL, API bên ngoài, hệ thống lưu trữ hoặc dịch vụ tích hợp. Dữ liệu đó có thể được lưu an toàn trong database nhưng vẫn trở thành nguy hiểm khi đưa vào HTML, thuộc tính, JavaScript, CSS hoặc URL mà không xử lý đúng ngữ cảnh.

Ví dụ, ứng dụng hiển thị tên người dùng:

```javascript
const name = new URLSearchParams(location.search).get("name");
document.querySelector("#greeting").innerHTML = "Xin chào " + name;
```

Nếu `name` chứa chuỗi có cú pháp HTML, trình duyệt có thể phân tích nó thành element thay vì văn bản. Trong trường hợp dữ liệu chứa markup có khả năng thực thi, lỗi này có thể dẫn đến **Cross-Site Scripting (XSS)**. Mã độc khi chạy trong origin của ứng dụng có thể thao tác DOM, gọi API bằng phiên hiện tại hoặc lấy dữ liệu mà người dùng được phép truy cập.

**Contextual output encoding** là kỹ thuật chuyển dữ liệu không tin cậy thành dạng mà trình duyệt diễn giải như dữ liệu thuần trong đúng ngữ cảnh nơi nó được chèn vào. Mỗi ngữ cảnh có cú pháp và quy tắc phân tích khác nhau, nên không tồn tại một hàm escape duy nhất an toàn cho mọi vị trí.

Trong module bảo mật trình duyệt, kỹ thuật này là lớp phòng vệ nền tảng cho XSS, bổ sung cho CSP, Trusted Types, SOP và các security headers. Mục tiêu là giữ cho dữ liệu không thể thay đổi cấu trúc hoặc ý nghĩa của tài liệu đầu ra.

Sau bài học, bạn có thể:

- Phân biệt HTML text, HTML attribute, URL, JavaScript và CSS context.
- Chọn cách encoding phù hợp với vị trí dữ liệu được chèn.
- Sử dụng safe DOM APIs và template engine có auto-escaping.
- Nhận diện những sink nguy hiểm như `innerHTML`, `document.write` và inline event handler.
- Biết khi nào cần HTML sanitization thay vì encoding.
- Kiểm thử đầu ra để xác nhận payload được hiển thị như dữ liệu, không được diễn giải thành mã.

## 2. Nguyên tắc cốt lõi: ngữ cảnh quyết định cách encode

Hãy xem một chuỗi không tin cậy là dữ liệu. Mục tiêu của encoding là khiến parser tại vị trí đầu ra không thể hiểu chuỗi đó thành cú pháp điều khiển.

| Ngữ cảnh | Ví dụ vị trí | Cách xử lý chính |
| --- | --- | --- |
| HTML text node | `<p>USER_DATA</p>` | HTML entity encoding hoặc dùng `textContent`. |
| HTML attribute được quote | `<input value="USER_DATA">` | Attribute encoding, luôn quote giá trị và chọn attribute an toàn. |
| URL component | `?q=USER_DATA` | URL component encoding, ví dụ `URLSearchParams`. |
| URL trong HTML attribute | `<a href="...">` | Xác thực URL/scheme trước, sau đó encode cho HTML attribute. |
| JavaScript string/code | `<script>...</script>` | Tránh nội suy; truyền dữ liệu qua JSON an toàn hoặc DOM API. |
| CSS value/selector | `style="..."` hoặc stylesheet | Tránh nội suy; dùng CSSOM và allowlist giá trị. |
| HTML rich text | Nội dung cho phép một tập markup | Dùng sanitizer theo allowlist; encoding sẽ hiển thị markup thành chữ. |

**Không lấy một encoder rồi dùng cho tất cả các ngữ cảnh.** HTML entity encoding không tự bảo vệ chuỗi được đưa vào JavaScript string; URL encoding không tự bảo vệ thuộc tính HTML; CSS escaping không biến URL nguy hiểm thành an toàn.

Một quy trình an toàn thường gồm:

1. Xác định nguồn dữ liệu và kiểu dữ liệu nghiệp vụ.
2. Xác định chính xác parser/context sẽ nhận dữ liệu.
3. Dùng API hoặc encoder chuyên biệt cho context đó.
4. Xác thực thêm các giá trị có ngữ nghĩa đặc biệt, như URL, tên thuộc tính hoặc CSS value.
5. Kiểm tra lại HTML/DOM và hành vi browser.

## 3. Encoding, validation và sanitization khác nhau

Ba kỹ thuật có liên quan nhưng giải quyết những vấn đề khác nhau:

| Kỹ thuật | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Validation** | Kiểm tra dữ liệu có đúng định dạng/quy tắc nghiệp vụ không. | Email phải đúng định dạng; trạng thái đơn hàng thuộc enum cho phép. |
| **Output encoding** | Giữ dữ liệu là văn bản trong context đầu ra. | Chuyển ký tự `<` thành `&lt;` trong HTML text. |
| **Sanitization** | Loại bỏ hoặc chuẩn hóa cấu trúc nguy hiểm trong nội dung được phép chứa markup. | Cho phép `<strong>` và `<a>` nhưng loại bỏ event handler và script. |

Ví dụ, nếu người dùng gửi tên hiển thị, ứng dụng nên validation độ dài và ký tự theo nghiệp vụ, rồi output encode khi hiển thị trong HTML. Không cần cho phép HTML trong tên.

Nếu ứng dụng có trình soạn thảo rich text và cần giữ định dạng như đoạn văn, danh sách hoặc liên kết, output encoding toàn bộ sẽ khiến markup hiện ra như văn bản. Khi đó cần sanitizer chuyên dụng với allowlist tag, attribute và URL scheme; không tự viết regex để “xóa script”.

**Validation đầu vào không thay thế output encoding.** Một chuỗi hợp lệ trong nghiệp vụ vẫn có thể chứa ký tự có ý nghĩa cú pháp trong HTML hoặc JavaScript. Dữ liệu từ database cũng cần được coi là không tin cậy khi render, vì nó có thể đến từ người dùng, import hoặc tích hợp bên ngoài.

## 4. HTML text context

HTML text context là dữ liệu nằm giữa hai thẻ:

```html
<p class="message">USER_DATA</p>
```

Các ký tự đặc biệt thường cần được encode thành HTML entities:

| Ký tự | Dạng entity thường dùng |
| --- | --- |
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| `"` | `&quot;` |
| `'` | `&#x27;` |

Ví dụ dữ liệu đầu vào:

```text
<img src=x onerror=alert(1)>
```

Khi được encode đúng cho HTML text, trình duyệt hiển thị nguyên chuỗi như văn bản. Nó không tạo element `img` và không đăng ký event handler.

### 4.1 Ưu tiên textContent thay vì innerHTML

Nếu chỉ cần hiển thị văn bản, dùng DOM API:

```javascript
const userMessage = "<img src=x onerror=alert(1)>";
const output = document.querySelector("#message");

output.textContent = userMessage;
```

`textContent` tạo nội dung văn bản; trình duyệt không parse chuỗi thành HTML. Tương tự, có thể tạo text node:

```javascript
const node = document.createTextNode(userMessage);
document.querySelector("#message").append(node);
```

Ngược lại:

```javascript
// Không dùng với dữ liệu không tin cậy:
output.innerHTML = userMessage;
```

`innerHTML` yêu cầu browser parse chuỗi như markup. Nếu dữ liệu chứa cú pháp HTML nguy hiểm, nó có thể tạo DOM ngoài ý muốn. Một số payload XSS có thể thực thi ngay khi parser tạo element hoặc khi event được kích hoạt.

### 4.2 Entity encoding không phải là “mã hóa dữ liệu”

HTML entity encoding là cách biểu diễn ký tự trong cú pháp HTML, không phải mã hóa bí mật. Sau khi parser xử lý, DOM text thường chứa lại ký tự ban đầu. Ví dụ `&lt;` trong source HTML trở thành ký tự `<` trong text node, nhưng vẫn là text chứ không được parse lại thành thẻ lần thứ hai.

Đừng encode nhiều lần. Nếu encode chuỗi đã encode, người dùng có thể thấy `&amp;lt;` thay vì `&lt;`. Hãy xác định rõ nơi chịu trách nhiệm encoding và không tự decode rồi đưa dữ liệu vào một HTML sink nguy hiểm.

## 5. HTML attribute context

Dữ liệu trong attribute có cú pháp riêng:

```html
<input value="USER_DATA">
<div title="USER_DATA">...</div>
```

Nếu attribute không được quote hoặc giá trị không được encode đúng, dữ liệu có thể kết thúc attribute hiện tại và tạo attribute mới. Vì vậy:

- Luôn dùng attribute có dấu quote.
- Dùng template engine hoặc encoder hỗ trợ HTML attribute context.
- Không ghép chuỗi thủ công khi có thể dùng DOM API.
- Không đặt dữ liệu không tin cậy vào tên attribute.

Ví dụ với DOM:

```javascript
const input = document.querySelector("#display-name");
input.setAttribute("value", userName);
```

Việc gán một giá trị vào attribute an toàn phụ thuộc **attribute cụ thể**. `setAttribute("value", ...)` hoặc `setAttribute("title", ...)` thường dùng để đặt dữ liệu; nhưng không dùng cùng cách với event handler:

```javascript
// Không an toàn:
element.setAttribute("onclick", userControlledCode);
```

Tên attribute như `onclick`, `onerror` là event-handler attribute; giá trị của chúng có thể được diễn giải như JavaScript. Tránh tạo event handler bằng chuỗi; dùng `addEventListener` với callback đã được kiểm soát.

### 5.1 Attribute encoding không làm mọi attribute an toàn

Ngay cả khi giá trị đã được quote và HTML-attribute-encode, các attribute có ngữ nghĩa đặc biệt vẫn cần validation riêng:

- `href` và `src` có thể chứa URL với scheme nguy hiểm.
- `style` chứa CSS, có cú pháp và khả năng tải tài nguyên riêng.
- `srcdoc` chứa cả một tài liệu HTML.
- `on*` là event-handler code.
- `formaction` có thể thay đổi đích gửi form.

Encoding bảo vệ cú pháp tại parser hiện tại; nó không tự quyết định giá trị có được phép về mặt nghiệp vụ hay không.

## 6. URL context: encode component và xác thực scheme

URL có nhiều thành phần: scheme, host, path, query và fragment. Khi dữ liệu không tin cậy được đưa vào URL, cần xác định nó nằm ở thành phần nào.

### 6.1 Query parameter

Dùng `URLSearchParams` để tạo query string:

```javascript
const query = new URLSearchParams({
  q: userSearchText,
  page: "1"
});

const url = "/search?" + query.toString();
```

API này encode giá trị query component phù hợp. Không tự ghép dữ liệu vào query bằng cách nối chuỗi:

```javascript
// Dễ sai khi userSearchText chứa &, =, # hoặc ký tự đặc biệt.
const url = "/search?q=" + userSearchText;
```

### 6.2 Path segment

Nếu dữ liệu là một path segment, có thể dùng `encodeURIComponent`:

```javascript
const userId = "team/a?b";
const path = "/users/" + encodeURIComponent(userId);
```

Không nhầm `encodeURIComponent` với `encodeURI`. `encodeURIComponent` dành cho một thành phần dữ liệu; `encodeURI` giữ lại nhiều ký tự có ý nghĩa phân tách URL và thường không phù hợp để encode dữ liệu tùy ý chèn vào một component.

### 6.3 URL được đặt trong href

Giả sử ứng dụng muốn hiển thị liên kết do người dùng cung cấp. Chỉ URL-encode là chưa đủ; cần kiểm tra scheme và đích:

```javascript
function safeHttpUrl(input) {
  try {
    const url = new URL(input, location.origin);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}

const target = safeHttpUrl(userProvidedUrl);
const link = document.querySelector("#external-link");

if (target) {
  link.href = target;
  link.textContent = "Mở liên kết";
} else {
  link.removeAttribute("href");
  link.textContent = "Liên kết không hợp lệ";
}
```

Trong ứng dụng thật, có thể cần allowlist host, chặn URL tới mạng nội bộ hoặc chỉ cho phép URL tương đối. `new URL` giúp parse và chuẩn hóa; allowlist quyết định đích nào được phép.

Các scheme như `javascript:` không được phép làm đích liên kết thông thường. `data:` cũng có thể tạo nội dung chủ động và không nên được chấp nhận chung. Không dùng kiểm tra chuỗi đơn giản như `startsWith("https")` nếu chưa parse URL; các chuỗi giả mạo có thể vượt qua kiểm tra yếu.

### 6.4 URL bên trong HTML attribute là context lồng nhau

Khi tạo:

```html
<a href="URL_FROM_USER">Mở</a>
```

cần hai bước:

1. Parse/validate URL và scheme theo chính sách.
2. Encode URL đã được chấp thuận cho HTML attribute context, hoặc gán qua DOM property `link.href`.

Không đảo thứ tự bằng cách chỉ HTML-encode URL rồi tin rằng đích đến đã an toàn.

## 7. JavaScript context: tránh nội suy dữ liệu vào code

Chèn dữ liệu vào JavaScript inline là một trong những context khó xử lý nhất:

```html
<script>
  const displayName = "USER_DATA";
</script>
```

Nếu chỉ escape dấu nháy mà không xét quy tắc HTML parser và JavaScript parser, chuỗi có thể phá vỡ string hoặc thẻ script. Đặc biệt, HTML parser nhận diện chuỗi đóng `</script>` ngay cả khi chuỗi đó xuất hiện bên trong một JavaScript string literal. Vì vậy, chỉ dùng `JSON.stringify` rồi nối thẳng vào inline script chưa chắc đã an toàn.

### 7.1 Ưu tiên không đưa dữ liệu vào JavaScript source

Phương án tốt nhất là tải dữ liệu qua endpoint JSON hoặc đưa dữ liệu vào DOM bằng cơ chế phù hợp, rồi để script bên ngoài đọc:

```html
<p id="welcome" data-display-name="Lan"></p>
<script src="/assets/profile.js" defer></script>
```

Script:

```javascript
const welcome = document.querySelector("#welcome");
const displayName = welcome.dataset.displayName;
welcome.textContent = "Xin chào " + displayName;
```

Trong template server-side, giá trị của `data-display-name` vẫn phải được encode đúng cho HTML attribute context.

### 7.2 Nhận dữ liệu JSON từ API

```javascript
const response = await fetch("/api/profile");
if (!response.ok) throw new Error("Không tải được hồ sơ");

const profile = await response.json();
document.querySelector("#name").textContent = profile.displayName;
```

JSON response nên có content type phù hợp như `application/json`. Khi dữ liệu đã được parse thành object, vẫn cần xử lý an toàn theo context lúc hiển thị. JSON không tự trở thành HTML an toàn.

### 7.3 Nếu buộc phải nhúng JSON trong HTML

Một số ứng dụng render dữ liệu khởi tạo vào trang. Cách an toàn cần dùng serializer được thiết kế cho **HTML script-data context**, không chỉ JSON serializer thông thường. Serializer cần xử lý các ký tự có thể kết thúc phần tử script, ví dụ escape dấu nhỏ hơn thành `\u003c` để chuỗi `</script>` không bị HTML parser nhận thành thẻ đóng.

Ví dụ ý tưởng về đầu ra an toàn:

```html
<script type="application/json" id="bootstrap-data">
{"displayName":"Lan \u003c/script\u003e"}
</script>
```

Sau đó đọc text và parse JSON:

```javascript
const raw = document.querySelector("#bootstrap-data").textContent;
const bootstrapData = JSON.parse(raw);
```

Trong thực tế, hãy dùng serializer/template engine đã được tài liệu hóa rõ ràng cho ngữ cảnh này. Không tự viết hàm escape JSON/HTML dựa trên một vài phép replace và không đưa kết quả vào executable inline script.

## 8. CSS context: không nối chuỗi dữ liệu vào stylesheet

CSS có parser và cú pháp riêng. Dữ liệu không tin cậy được nối vào CSS có thể làm thay đổi declaration, selector hoặc URL tải tài nguyên. Vì vậy, tránh:

```html
<div style="background: USER_VALUE">Nội dung</div>
```

hoặc:

```javascript
// Không nên đưa chuỗi không tin cậy vào CSS text.
element.style.cssText = userControlledCss;
```

### 8.1 Dùng CSSOM và allowlist giá trị

Nếu chỉ cần đặt một thuộc tính có giá trị được giới hạn:

```javascript
const allowedColors = new Set(["blue", "green", "gray"]);
const requestedColor = userPreference;

const color = allowedColors.has(requestedColor)
  ? requestedColor
  : "gray";

element.style.color = color;
```

Với giá trị số, parse và giới hạn miền:

```javascript
const requestedSize = Number(userPreference);
const fontSize = Number.isFinite(requestedSize)
  ? Math.min(24, Math.max(12, requestedSize))
  : 16;

element.style.fontSize = fontSize + "px";
```

`element.style.color` và các thuộc tính CSSOM cụ thể phù hợp hơn việc gán toàn bộ `cssText`. Tuy vậy, vẫn cần validation theo thuộc tính; không đưa chuỗi tùy ý vào những thuộc tính có thể chứa URL hoặc cú pháp phức tạp.

### 8.2 CSS.escape không phải CSS value sanitizer

`CSS.escape()` hữu ích để escape một chuỗi dùng làm **CSS identifier** trong selector:

```javascript
const id = userProvidedId;
const element = document.querySelector("#" + CSS.escape(id));
```

Nó không phải encoder chung cho mọi CSS property value, URL hoặc toàn bộ stylesheet. Hãy phân biệt selector identifier với CSS declaration value.

## 9. DOM-based output và các sink cần kiểm soát

Trong ứng dụng client-side, dữ liệu có thể đi từ URL, storage, postMessage hoặc API tới DOM. Lỗi xảy ra khi dữ liệu không tin cậy đi vào một **DOM sink** có khả năng parse hoặc thực thi.

### 9.1 Safe sinks thường dùng

| API | Cách dùng an toàn điển hình | Lưu ý |
| --- | --- | --- |
| `textContent` | Hiển thị văn bản. | Không parse chuỗi thành HTML. |
| `createTextNode()` | Tạo text node. | Phù hợp với nội dung văn bản. |
| `value` | Đặt giá trị input/textarea. | Kiểm tra logic nghiệp vụ riêng. |
| `setAttribute()` | Đặt attribute dữ liệu như `title` hoặc `aria-label`. | Tránh `on*`, `srcdoc`; URL/style cần validation riêng. |
| `addEventListener()` | Gắn callback code đã kiểm soát. | Không tạo handler bằng chuỗi. |
| CSSOM property cụ thể | Đặt CSS value đã validation. | Tránh `cssText` với dữ liệu tùy ý. |

### 9.2 Những sink nguy hiểm

- `innerHTML`, `outerHTML`, `insertAdjacentHTML`.
- `document.write()` và `document.writeln()`.
- `eval()`, `Function()` và các API thực thi chuỗi như code.
- `setTimeout("...")` hoặc `setInterval("...")` với chuỗi.
- Event-handler attributes như `onclick`, `onerror`.
- `iframe.srcdoc` với HTML không tin cậy.
- `element.style.cssText` hoặc ghép chuỗi stylesheet.

Không phải mọi lần sử dụng sink đều tạo lỗ hổng, nhưng chúng yêu cầu kiểm soát nghiêm ngặt dữ liệu đầu vào và ngữ cảnh. Nếu chỉ cần hiển thị văn bản, chọn safe sink để không phải tự quản lý HTML parsing.

### 9.3 Ví dụ DOM XSS từ URL fragment

Fragment URL không được gửi tới server trong HTTP request thông thường, nhưng JavaScript có thể đọc nó:

```javascript
const fragment = location.hash.slice(1);

// Không an toàn: parse fragment thành HTML.
// document.querySelector("#preview").innerHTML = fragment;

// An toàn hơn nếu chỉ cần hiển thị:
document.querySelector("#preview").textContent = fragment;
```

Đừng cho rằng dữ liệu từ `location.hash`, `localStorage`, `sessionStorage`, `postMessage` hoặc API nội bộ là đáng tin. Chúng đều có thể bị ảnh hưởng bởi input của người dùng hoặc nguồn bên ngoài.

## 10. Template engine và auto-escaping

Template engine hiện đại thường hỗ trợ tự động escape biến khi render vào HTML text hoặc attribute context. Ví dụ khái niệm:

```text
<p>{{ user.displayName }}</p>
```

Nếu engine bật auto-escaping, biến được encode phù hợp trước khi đưa vào HTML. Tuy nhiên, behavior phụ thuộc engine và loại template:

- Một số engine chỉ auto-escape trong HTML context.
- Một số cú pháp như `{{{value}}}` hoặc `|safe` có thể tắt escaping.
- Template trong JavaScript, CSS hoặc URL có thể cần cơ chế chuyên biệt.
- Template string tự ghép trong frontend không tự có auto-escaping.

Không đánh dấu dữ liệu người dùng là “safe HTML” chỉ để làm giao diện hiển thị đúng. Các thao tác tắt escaping như `raw`, `safe`, triple braces hoặc tương tự cần được giới hạn cho nội dung đã được sanitizer đáng tin cậy.

### 10.1 Một nguồn dữ liệu, nhiều output context

Cùng một giá trị display name có thể được hiển thị ở nhiều nơi:

- HTML text trong trang hồ sơ.
- Attribute `title` trong tooltip.
- Query parameter của URL tìm kiếm.
- JSON response cho frontend.

Không lưu một phiên bản “đã HTML-encode” trong database để tái sử dụng cho tất cả vị trí. Hãy lưu dữ liệu nghiệp vụ ở dạng chuẩn, rồi encode tại điểm xuất theo đúng context. Điều này tránh double encoding và giúp cùng dữ liệu được dùng an toàn trong nhiều định dạng.

## 11. Context lồng nhau và thứ tự xử lý

Một giá trị có thể đi qua nhiều parser. Khi đó, cần xử lý từng lớp theo thứ tự phù hợp.

### 11.1 URL bên trong HTML attribute

Ví dụ:

```html
<a href="USER_URL">Mở</a>
```

Quy trình:

1. Parse URL bằng API chuẩn.
2. Kiểm tra scheme, host và port theo allowlist/nghiệp vụ.
3. Tạo URL cuối cùng.
4. Encode cho HTML attribute context hoặc gán qua DOM property.

Không đảo thứ tự bằng cách chỉ HTML-encode URL rồi tin rằng đích đến đã an toàn.

### 11.2 Dữ liệu JavaScript trong HTML

Đặt chuỗi vào JavaScript inline đồng thời chịu ảnh hưởng của HTML parser và JavaScript parser. Một hàm escape cho JavaScript string không nhất thiết ngăn HTML parser kết thúc thẻ script. Vì vậy, lựa chọn tốt nhất là không nhúng dữ liệu trực tiếp vào executable script; dùng external script, JSON endpoint hoặc DOM data được attribute-encode.

Nếu bắt buộc nhúng JSON, dùng serializer chuyên cho HTML script-data context có xử lý ký tự nhỏ hơn/chuỗi đóng script; sau đó đọc bằng textContent và JSON.parse. Không tự ghép JSON bằng nối chuỗi.

### 11.3 URL component trong query và attribute

Khi tạo URL có query:

```javascript
const url = new URL("/search", location.origin);
url.searchParams.set("q", userSearchText);

const link = document.querySelector("#search-link");
link.href = url.href;
```

URL API xử lý component query. Nếu render URL vào HTML source thủ công, kết quả vẫn phải được encode cho attribute. Nếu gán qua DOM property `href`, browser xử lý việc đặt property; ứng dụng vẫn phải xác thực scheme/đích trước.

## 12. HTML sanitization cho nội dung rich text

Nếu sản phẩm cho phép người dùng định dạng nội dung, ví dụ bài viết có tiêu đề, đoạn văn, danh sách và liên kết, encode toàn bộ HTML sẽ làm mất định dạng. Thay vào đó, dùng sanitizer trưởng thành theo allowlist:

- Cho phép những element cần thiết như `p`, `strong`, `em`, `ul`, `ol`, `li`.
- Chỉ cho phép attribute cần thiết, ví dụ `href` đã được kiểm tra.
- Loại bỏ event handler `on*`, script, iframe hoặc element nguy hiểm theo chính sách.
- Kiểm tra scheme URL; không cho `javascript:` trong liên kết.
- Tránh cho phép style tùy ý nếu không có nhu cầu rõ ràng.
- Cập nhật thư viện sanitizer để nhận bản vá bảo mật.

Sanitization khác với output encoding: sanitizer giữ lại một tập cấu trúc HTML được phép; encoding biến toàn bộ markup thành văn bản. Không dùng regex tự viết để xóa chuỗi `<script>`, vì XSS có nhiều cách biểu diễn và parser context phức tạp.

### 12.1 Đưa HTML đã sanitize vào DOM

Khi thật sự cần HTML, quy trình là sanitize theo allowlist rồi mới đưa kết quả vào sink. Ví dụ minh họa:

```javascript
// sanitizeRichText phải là wrapper cho thư viện sanitizer
// được duy trì, cấu hình allowlist rõ ràng.
const cleanHtml = sanitizeRichText(untrustedRichText);
container.innerHTML = cleanHtml;
```

Tên hàm trên là minh họa; không phải hàm có sẵn của browser. Không tự tạo sanitizer bằng một vài phép replace. Nếu môi trường hỗ trợ Trusted Types, có thể yêu cầu các sink HTML nhận TrustedHTML từ policy được kiểm soát.

## 13. CSP và Trusted Types hỗ trợ output encoding như thế nào?

Output encoding đúng context là lớp phòng vệ chính. **Content Security Policy (CSP)** và **Trusted Types** giúp giảm khả năng XSS nếu có lỗi ở nơi khác.

### 13.1 Content Security Policy

Ví dụ CSP có nonce:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-random-per-response'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Nonce phải được tạo ngẫu nhiên cho từng response và gắn đúng vào script được phép. CSP giúp giới hạn nguồn script và giảm tác động của một số lỗi injection; nó không biến việc dùng `innerHTML` với dữ liệu không tin cậy thành an toàn.

### 13.2 Trusted Types

Trong browser hỗ trợ Trusted Types, ứng dụng có thể yêu cầu các DOM XSS sink chỉ nhận kiểu dữ liệu tin cậy:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

Khi bật chính sách, các sink như `innerHTML` có thể từ chối chuỗi thông thường và yêu cầu `TrustedHTML` từ policy được đăng ký. Policy phải gọi sanitizer đã được kiểm tra; không tạo policy trả nguyên input:

```javascript
// Minh họa ý tưởng; sanitizeRichText phải dùng sanitizer đáng tin cậy.
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return sanitizeRichText(input);
  }
});

container.innerHTML = htmlPolicy.createHTML(untrustedHtml);
```

Trusted Types không tự sanitize dữ liệu. Nếu policy trả nguyên chuỗi, ứng dụng vẫn có XSS nhưng đã đóng gói nó trong một kiểu được tin cậy sai cách. Hãy giới hạn nơi tạo policy, tránh policy tổng quát cho toàn ứng dụng và kiểm tra mọi sink.

## 14. Lỗi thường gặp khi encode đầu ra

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng HTML encoding cho JavaScript context | HTML parser và JS parser có quy tắc khác nhau. | Tránh inline JS; dùng JSON serializer phù hợp hoặc DOM API. |
| URL encode toàn bộ URL | Có thể encode cả dấu phân cách scheme/host/path làm URL sai; không xác thực scheme. | Encode component, parse URL và allowlist đích. |
| HTML-encode nhưng vẫn cho `javascript:` trong href | Attribute encoding không kiểm soát scheme. | Validate URL scheme/host trước khi gán. |
| Dùng `innerHTML` để hiển thị text | Browser parse dữ liệu thành markup. | Dùng `textContent`. |
| Dùng `setAttribute` cho `onclick` | Giá trị được diễn giải như JavaScript. | Dùng `addEventListener` với callback tin cậy. |
| Tự viết sanitizer bằng regex | Không xử lý đầy đủ cú pháp HTML và parser edge cases. | Dùng sanitizer được duy trì với allowlist. |
| Encode dữ liệu trước khi lưu database | Một phiên bản encoded không phù hợp mọi output context. | Lưu dữ liệu chuẩn; encode tại điểm xuất. |
| Encode nhiều lần | Gây double encoding và hiển thị sai. | Xác định một lớp chịu trách nhiệm encoding cho từng context. |
| Tin dữ liệu từ database/API | Nguồn dữ liệu có thể bắt đầu từ người dùng hoặc hệ thống bên ngoài. | Xem dữ liệu là untrusted cho tới khi được xử lý đúng tại sink. |
| Tắt auto-escaping bằng `safe`/`raw` | Bỏ lớp bảo vệ mặc định của template. | Chỉ dùng với HTML đã sanitize và có lý do rõ ràng. |

## 15. Kiểm thử contextual output encoding

Kiểm thử cần xác nhận cả hai điều: dữ liệu hiển thị đúng cho người dùng và parser không tạo cấu trúc/thực thi ngoài dự kiến.

### 15.1 Bộ giá trị thử nghiệm

Trong ứng dụng lab, dùng các chuỗi vô hại để kiểm tra parser:

```text
<hello>
Tom & Jerry
"double quote" and 'single quote'
</script>
javascript:alert(1)
line 1
line 2
```

Các chuỗi này giúp phát hiện:

- HTML text/attribute có bị kết thúc sớm không.
- Ký tự ampersand có làm sai entity không.
- JavaScript inline có thể bị kết thúc bởi chuỗi đóng script không.
- URL scheme có được validation không.
- Dữ liệu xuống dòng có phá cấu trúc hoặc logic không.

Không cần chạy payload thực thi để chứng minh output encoding; kiểm tra DOM và cách hiển thị đã đủ cho nhiều test.

### 15.2 Kiểm tra HTML text

1. Gửi chuỗi `<hello>` vào trường tên.
2. Render ra phần tử bằng `textContent` hoặc template auto-escape.
3. Quan sát trang: chuỗi phải hiển thị nguyên văn.
4. Kiểm tra Elements: không được tạo một element `hello` mới từ dữ liệu.

### 15.3 Kiểm tra attribute

1. Đưa dấu nháy kép, dấu nháy đơn và ký tự `<` vào giá trị thử nghiệm.
2. Render vào `title` hoặc `value` đã quote.
3. Kiểm tra dữ liệu không tạo thêm attribute hoặc thay đổi cấu trúc element.
4. Thử riêng URL attribute với scheme không được phép và xác nhận bị từ chối.

### 15.4 Kiểm tra DOM sink

Tìm các điểm nhận dữ liệu:

- `innerHTML`, `outerHTML`, `insertAdjacentHTML`.
- `document.write`.
- `eval`, `Function`, timer nhận chuỗi.
- `setAttribute("on...")`.
- `srcdoc`, `style.cssText`.

Với mỗi sink, xác định nguồn dữ liệu và kiểm tra có sanitizer/Trusted Types hoặc cách thay thế bằng safe API hay không. Một source-to-sink review hữu ích hơn chỉ tìm chuỗi innerHTML vì một số sink được gọi gián tiếp qua framework hoặc thư viện.

### 15.5 Kiểm tra regression tự động

Có thể viết test xác nhận dữ liệu được hiển thị như text:

```javascript
const payload = "<hello>&\"'";
renderDisplayName(payload);

const output = document.querySelector("#display-name");
console.assert(output.textContent === payload);
console.assert(output.querySelector("hello") === null);
```

Đối với rich text sanitizer, test theo allowlist:

- Element được phép vẫn tồn tại.
- Event handler bị loại bỏ.
- URL scheme nguy hiểm bị loại bỏ hoặc attribute bị xóa.
- Nội dung văn bản được giữ lại.
- Regression corpus được chạy lại khi nâng phiên bản sanitizer.

## 16. Checklist triển khai

- [ ] Xác định context cụ thể tại mỗi điểm render dữ liệu.
- [ ] Dùng template auto-escaping hoặc safe DOM API cho văn bản.
- [ ] Quote mọi HTML attribute và không nhận tên attribute tùy ý.
- [ ] URL được parse, kiểm tra scheme/host và encode từng component.
- [ ] Không nội suy dữ liệu không tin cậy vào JavaScript source hoặc CSS source.
- [ ] Không dùng event-handler attribute; dùng addEventListener.
- [ ] Tránh các DOM XSS sink hoặc bảo vệ bằng sanitizer/Trusted Types.
- [ ] Rich text được sanitize bằng thư viện duy trì và allowlist tối thiểu.
- [ ] Không đánh dấu dữ liệu chưa sanitize là safe/raw.
- [ ] Lưu dữ liệu chuẩn, output encode đúng lúc, tránh double encoding.
- [ ] CSP được triển khai như defense in depth.
- [ ] Kiểm thử text, attribute, URL, script-data và DOM sink.
- [ ] Kiểm tra dữ liệu đến từ database, API, URL, storage và postMessage.

## 17. Câu hỏi tự kiểm tra

1. Vì sao HTML entity encoding không bảo vệ JavaScript string context?
2. Dữ liệu trong `href` cần những bước nào ngoài HTML attribute encoding?
3. Vì sao `textContent` an toàn hơn `innerHTML` khi chỉ hiển thị văn bản?
4. Tại sao `JSON.stringify` thông thường chưa đủ nếu nối trực tiếp vào inline `<script>`?
5. `CSS.escape()` dùng cho selector identifier hay mọi CSS value?
6. Khi nào output encoding phù hợp, khi nào cần HTML sanitization?
7. Vì sao không nên lưu dữ liệu đã HTML-encode trong database?
8. Trusted Types có tự sanitize chuỗi không? Policy tạo `TrustedHTML` cần làm gì?
9. Một template engine có auto-escaping có thể vẫn tạo XSS trong trường hợp nào?
10. Vì sao CORS, SOP và CSP không thay thế contextual output encoding?

## 18. Tổng kết

**Contextual output encoding** giữ dữ liệu không tin cậy ở dạng dữ liệu khi được đưa vào HTML, attribute, URL, JavaScript hoặc CSS. Mỗi context có parser riêng, vì vậy phải chọn encoder hoặc API đúng vị trí; không dùng HTML encoding như giải pháp chung. Với văn bản, ưu tiên `textContent` và template auto-escaping. Với URL, parse/validate scheme và đích, encode component rồi xử lý đúng HTML attribute context. Với JavaScript và CSS, tránh nội suy dữ liệu vào source; dùng JSON/DOM/CSSOM APIs và allowlist.

Khi cần rich text, dùng sanitizer được duy trì theo allowlist. CSP và Trusted Types là lớp phòng vệ bổ sung, không thay thế encoding và sanitization đúng cách. Hãy lưu dữ liệu ở dạng chuẩn, encode tại điểm xuất, kiểm tra các source-to-sink path và xác nhận bằng DOM/DevTools cùng regression tests. Đây là nền tảng để giảm XSS và giữ ranh giới bảo mật của origin ứng dụng.
