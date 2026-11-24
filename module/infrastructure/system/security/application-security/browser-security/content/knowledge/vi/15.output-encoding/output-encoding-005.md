# CSS encoding: đưa dữ liệu vào CSS an toàn

## 1. CSS encoding là gì?

**CSS encoding** là cách biểu diễn dữ liệu không tin cậy khi dữ liệu được đưa vào một ngữ cảnh cú pháp CSS. Mục tiêu là giữ cho dữ liệu được hiểu đúng như giá trị dự kiến, không thể thay đổi cấu trúc stylesheet, chèn thêm declaration, selector, rule hoặc URL ngoài ý muốn.

CSS có nhiều ngữ cảnh khác nhau: tên class/identifier, selector, chuỗi trong dấu nháy, giá trị thuộc tính, URL trong `url()` và stylesheet được nhúng trong HTML. Mỗi ngữ cảnh có quy tắc cú pháp riêng. Vì vậy, **không tồn tại một hàm escape CSS duy nhất có thể dùng an toàn cho mọi vị trí**.

Ví dụ, một ứng dụng cho người dùng chọn màu giao diện. Nếu ứng dụng ghép thẳng input vào stylesheet:

```js
const css = ".preview { color: " + userInput + "; }";
styleElement.textContent = css;
```

thì dữ liệu không còn chỉ là một giá trị màu. Kẻ tấn công có thể đưa thêm dấu phân tách và declaration CSS khác. Hậu quả có thể là thay đổi giao diện, che khuất cảnh báo, tạo request tải tài nguyên ngoài hoặc làm lộ một số thông tin qua các kỹ thuật CSS injection.

Bài viết thuộc chương **Output encoding** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Chủ đề này liên quan trực tiếp đến phòng vệ XSS, DOM injection, CSP, Trusted Types và kiểm soát dữ liệu khi trình duyệt phân tích HTML/CSS.

Sau bài học, bạn có thể:

- Phân biệt CSS injection với XSS và hiểu khi nào CSS injection có thể dẫn đến rủi ro khác.
- Nhận diện các ngữ cảnh CSS: identifier, selector, string, property value và URL.
- Hiểu vì sao HTML attribute encoding, URL encoding và CSS escaping không thay thế cho nhau.
- Dùng CSSOM, `style.setProperty()`, `textContent`, `CSS.escape()` và allowlist đúng mục đích.
- Kiểm soát giá trị màu, kích thước, class, selector và URL tài nguyên.
- Hiểu giới hạn của CSP và Trusted Types đối với CSS injection.
- Thực hành tái hiện CSS injection và sửa bằng allowlist trong môi trường local.

## 2. CSS injection là gì?

**CSS injection** xảy ra khi dữ liệu không tin cậy được đưa vào CSS mà không kiểm soát đúng cú pháp hoặc ngữ cảnh. Dữ liệu có thể làm thay đổi cách trình duyệt parse stylesheet, ví dụ thoát khỏi một giá trị dự kiến rồi chèn declaration hoặc rule khác.

Ví dụ, ứng dụng muốn tạo:

```css
.preview {
  color: blue;
}
```

Nhưng giá trị `color` do người dùng cung cấp lại chứa nhiều declaration:

```css
blue; background-color: yellow; border: 4px solid red
```

Khi ghép thành stylesheet, kết quả có thể trở thành:

```css
.preview {
  color: blue;
  background-color: yellow;
  border: 4px solid red;
}
```

Người dùng đã thay đổi nhiều thuộc tính CSS dù ứng dụng chỉ định cho phép chọn màu chữ. Đây là ví dụ về **CSS declaration injection**.

### 2.1. CSS injection có phải luôn là XSS?

Không. Trong các trình duyệt hiện đại, CSS thông thường không cung cấp khả năng thực thi JavaScript tổng quát như HTML script hoặc event handler. CSS injection thường gây tác động như:

- Thay đổi giao diện, che nút, che cảnh báo hoặc giả mạo nội dung hiển thị.
- Tạo request tải tài nguyên qua `url()`, `@import`, font hoặc hình nền.
- Làm lộ một số trạng thái giao diện trong những điều kiện cụ thể, ví dụ bằng selector và request tài nguyên được kiểm soát.
- Phá vỡ bố cục hoặc gây khó sử dụng, dẫn đến rủi ro về tính toàn vẹn và sẵn sàng.

Một số trình duyệt cũ từng có tính năng CSS đặc thù có thể dẫn tới thực thi mã, nhưng không nên khái quát các hành vi legacy đó thành hành vi CSS hiện đại. CSS injection có thể kết hợp với HTML injection hoặc XSS, nhưng bản thân hai lỗi không đồng nghĩa.

### 2.2. CSS injection ảnh hưởng bảo mật như thế nào?

| Tác động | Ví dụ | Điều kiện/rủi ro |
|---|---|---|
| UI tampering | Ẩn nút cảnh báo, thay màu trạng thái, che nội dung | Người dùng có thể bị đánh lừa khi thao tác |
| UI redressing | Chồng lớp hoặc thay đổi vị trí thành phần | Có thể hỗ trợ kịch bản lừa người dùng; clickjacking vẫn cần phân tích riêng |
| Network requests | `background-image: url(...)`, `@import` | Browser có thể tải tài nguyên theo chính sách CSP và ngữ cảnh |
| Data inference | Selector nhắm đến thuộc tính/trạng thái rồi kích hoạt tải URL khác nhau | Chỉ xảy ra trong một số điều kiện; phụ thuộc DOM, CSS, CSP và chính sách trình duyệt |
| Availability | Tạo nhiều rule, tải tài nguyên lớn hoặc làm layout bất thường | Có thể làm chậm hoặc phá giao diện |

Không phải mọi CSS injection đều có thể đánh cắp dữ liệu. Khi đánh giá tác động, cần xác định attacker kiểm soát phần CSS nào, DOM nào có thể bị chọn, dữ liệu nào hiện diện trong DOM và các chính sách mạng/CSP đang áp dụng.

## 3. Những ngữ cảnh CSS cần phân biệt

CSS có cú pháp lồng nhau. Một giá trị an toàn trong ngữ cảnh này có thể không an toàn trong ngữ cảnh khác.

| Ngữ cảnh | Ví dụ | Điều cần bảo vệ |
|---|---|---|
| **Identifier** | `.user-card`, `#panel`, tên animation | Ký tự hợp lệ và cách thoát identifier |
| **Selector** | `#user-id .item` | Không cho dữ liệu thay đổi cấu trúc selector |
| **CSS string** | `content: "hello"` | Không cho dữ liệu thoát khỏi chuỗi |
| **Property value** | `color: blue`, `width: 20px` | Chỉ cho phép giá trị đúng kiểu và phạm vi |
| **URL token** | `background-image: url(...)` | Kiểm tra URL đích và cú pháp CSS URL |
| **Stylesheet rule** | `@media`, `@import`, selector và declaration | Không ghép dữ liệu không tin cậy thành rule tùy ý |
| **HTML style attribute** | `<div style="color: red">` | Đồng thời có HTML attribute context và CSS declaration context |
| **Style element** | `<style>...</style>` | Đồng thời có HTML raw-text context và CSS parser context |

Cần xác định dữ liệu được đưa vào vị trí nào trước khi chọn biện pháp. Nếu không cần cho phép người dùng viết CSS, cách an toàn nhất thường là **không nhận CSS tùy ý**.

## 4. CSS identifier và selector

### 4.1. Identifier là gì?

Identifier là tên được CSS dùng để nhận diện class, ID, animation, custom property và nhiều thành phần cú pháp khác.

Ví dụ:

```css
#profile-panel { display: block; }
.user-card { border-radius: 8px; }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
```

Nếu ID hoặc class đến từ dữ liệu người dùng, không nên nối chuỗi trực tiếp vào selector:

```js
// Không an toàn nếu userId có ký tự làm thay đổi selector.
const node = document.querySelector("#" + userId);
```

Có thể dùng `CSS.escape()` để escape một giá trị **được dùng như CSS identifier**:

```js
const node = document.querySelector("#" + CSS.escape(userId));
```

Ví dụ nếu ID là `user:42`, `CSS.escape()` tạo biểu diễn identifier phù hợp để selector tìm đúng phần tử có ID đó.

### 4.2. CSS.escape() không phải bộ escape CSS tổng quát

`CSS.escape()` được thiết kế để tạo chuỗi an toàn khi dùng làm identifier trong selector. Không dùng nó để escape:

- Toàn bộ stylesheet.
- Property value như `color`, `width`, `background`.
- Chuỗi trong `content: "..."`.
- URL trong `url(...)`.
- HTML attribute hoặc JavaScript string.

Ví dụ sai:

```js
// Sai mục đích: CSS.escape không xác thực giá trị màu.
element.style.color = CSS.escape(userColor);
```

Nếu người dùng chọn màu, hãy kiểm tra màu theo allowlist hoặc dùng bộ phân tích màu phù hợp; đừng biến giá trị màu thành identifier.

### 4.3. Tốt hơn: không tạo selector từ input nếu không cần

Nếu đã có tham chiếu phần tử, dùng trực tiếp:

```js
const card = document.getElementById("profile-panel");
card.classList.add("is-highlighted");
```

Nếu cần chọn class do ứng dụng quản lý, dùng tập class cố định:

```js
const allowedStates = new Set(["active", "disabled", "pending"]);
if (allowedStates.has(state)) {
  card.classList.add("state-" + state);
}
```

Cách này tránh việc dữ liệu người dùng tự định nghĩa selector hoặc class tùy ý.

## 5. CSS string context

CSS string thường xuất hiện trong dấu nháy đơn hoặc kép, ví dụ:

```css
.notice::before {
  content: "Welcome";
}
```

Nếu ứng dụng ghép dữ liệu vào chuỗi CSS:

```js
const css = '.notice::before { content: "' + userText + '"; }';
```

thì dấu nháy, dấu gạch chéo ngược, newline và các ký tự điều khiển có thể thay đổi cách parser diễn giải chuỗi hoặc làm hỏng rule.

### 5.1. Tránh tự viết CSS string encoder

CSS có quy tắc escape riêng, bao gồm escape bằng dấu gạch chéo ngược và mã hex. Một escape có thể tiêu thụ tối đa sáu chữ số hex; khoảng trắng sau escape có thể có ý nghĩa phân tách. Việc tự viết encoder rất dễ thiếu trường hợp.

Nếu mục đích chỉ là hiển thị văn bản, đừng đưa dữ liệu vào CSS `content`. Dùng HTML text node:

```js
const label = document.createElement("span");
label.textContent = userText;
container.append(label);
```

Nếu cần dùng CSS pseudo-element cho nhãn cố định, giữ CSS tĩnh và đặt dữ liệu trong DOM thay vì sinh chuỗi CSS.

### 5.2. Khi thật sự cần chuỗi CSS

Hãy ưu tiên CSSOM hoặc một thư viện serializer CSS đã được kiểm chứng và chỉ nhận các kiểu dữ liệu cụ thể. Không lấy một chuỗi bất kỳ từ người dùng rồi đặt vào `content`, `font-family`, `background` hoặc thuộc tính tổng hợp khác.

Với dữ liệu cần render như text, DOM text API phù hợp hơn CSS string. Với CSS value, hãy validate theo grammar và yêu cầu nghiệp vụ của property đó.

## 6. Property value: validate theo từng thuộc tính

### 6.1. Không có một quy tắc cho mọi property

Giá trị hợp lệ của `color` khác `width`, `opacity`, `font-weight`, `transform` hoặc `background-image`.

Ví dụ:

```css
.card {
  color: #1f2937;
  width: 320px;
  opacity: 0.95;
  transform: translateX(4px);
}
```

Không nên cho người dùng nhập nguyên văn mọi property value nếu sản phẩm chỉ cần một số lựa chọn. Hãy dùng allowlist hoặc chuyển dữ liệu sang kiểu có cấu trúc:

- Màu: một tập tên màu hoặc mã hex có kiểm tra.
- Kích thước: số trong khoảng cho phép và đơn vị do ứng dụng chọn.
- Độ mờ: số trong khoảng 0 đến 1.
- Trạng thái: enum như `compact`, `comfortable`, `large`.
- Vị trí: một số hữu hạn và quy tắc layout đã định.

### 6.2. Allowlist màu

Ví dụ:

```js
const allowedColors = new Set([
  "black",
  "white",
  "navy",
  "teal",
  "tomato",
]);

function applyTextColor(element, input) {
  if (!allowedColors.has(input)) {
    throw new TypeError("Màu không nằm trong danh sách cho phép");
  }

  element.style.setProperty("color", input);
}
```

Allowlist dễ kiểm tra và thể hiện chính xác những gì sản phẩm cho phép. Nếu cần hỗ trợ mã hex, hãy xác thực theo grammar rõ ràng và độ dài cụ thể; không chỉ kiểm tra rằng chuỗi bắt đầu bằng `#`.

### 6.3. Số và đơn vị

Ví dụ cho phép chiều rộng từ 120 đến 960 pixel:

```js
function applyWidth(element, input) {
  const width = Number(input);

  if (!Number.isFinite(width) || width < 120 || width > 960) {
    throw new RangeError("Chiều rộng ngoài phạm vi");
  }

  element.style.setProperty("width", String(width) + "px");
}
```

Ứng dụng tự thêm đơn vị `px`, không cho người dùng điều khiển dấu chấm phẩy hoặc phần CSS còn lại. Cần kiểm tra `Number.isFinite` để loại `NaN`, `Infinity` và các giá trị không hợp lệ.

### 6.4. CSSOM không thay thế validation

`element.style.setProperty(property, value)` thao tác với CSS declaration thông qua CSSOM, tránh việc ghép toàn bộ stylesheet thành chuỗi. Nhưng API này **không phải bộ lọc nghiệp vụ**. Trình duyệt vẫn parse giá trị theo cú pháp CSS của property; giá trị không phù hợp có thể bị bỏ qua hoặc được chấp nhận theo grammar rộng hơn dự kiến.

Ví dụ:

```js
element.style.setProperty("color", userInput);
```

Cách gọi này tốt hơn việc nối `userInput` vào cả stylesheet, nhưng vẫn nên validate `userInput` theo danh sách màu hoặc grammar mà sản phẩm cho phép. Đặc biệt, không đưa CSS token stream tùy ý vào custom property rồi thay thế nó ở nhiều property khác nhau.

## 7. Custom properties (CSS variables)

CSS custom properties thường bắt đầu bằng `--`:

```css
:root {
  --brand-color: #0f766e;
  --panel-gap: 16px;
}

.card {
  color: var(--brand-color);
  gap: var(--panel-gap);
}
```

Có thể cập nhật custom property qua CSSOM:

```js
document.documentElement.style.setProperty("--brand-color", "#0f766e");
```

Custom property nhận token stream CSS rộng hơn nhiều kiểu property thông thường. Nếu dữ liệu không tin cậy được đặt vào custom property, rồi `var()` đưa dữ liệu đó vào property khác, việc kiểm tra phải xét **nơi custom property được tiêu thụ**, không chỉ nơi nó được gán.

Ví dụ, nếu `--user-value` được đưa vào `background` hoặc `background-image`, dữ liệu có thể mang cú pháp nhiều lớp. Hãy validate dữ liệu theo property đích và tránh dùng custom property như kênh truyền CSS tùy ý.

## 8. URL trong CSS: url() và @import

### 8.1. CSS có thể tải tài nguyên

CSS hỗ trợ URL trong nhiều vị trí:

```css
.hero {
  background-image: url("/images/banner.webp");
}

@import url("/styles/theme.css");

@font-face {
  font-family: "Brand";
  src: url("/fonts/brand.woff2");
}
```

Nếu attacker kiểm soát URL trong CSS, trình duyệt có thể phát request đến tài nguyên ngoài tùy CSP, loại tài nguyên, chính sách tải và ngữ cảnh. Điều này có thể tạo tracking hoặc kênh gửi một số tín hiệu; tác động cụ thể phụ thuộc tài nguyên và chính sách trình duyệt.

### 8.2. Validate URL riêng với CSS encoding

Không dùng CSS escaping để quyết định URL có đáng tin hay không. Cần parse URL, kiểm tra scheme và origin/host theo allowlist trước khi sử dụng.

Ví dụ cho một ảnh chỉ được tải từ CDN đã biết:

```js
const IMAGE_ORIGIN = "https://static.example.com";

function parseAllowedImageUrl(input) {
  const url = new URL(input, IMAGE_ORIGIN);

  if (url.protocol !== "https:" || url.origin !== IMAGE_ORIGIN) {
    throw new TypeError("Nguồn ảnh không được phép");
  }

  if (url.username || url.password) {
    throw new TypeError("Không chấp nhận userinfo");
  }

  return url;
}

const image = document.createElement("img");
image.src = parseAllowedImageUrl(userInput).href;
image.alt = "Ảnh minh họa";
container.append(image);
```

Nếu có thể dùng `<img src>` thay vì CSS `background-image`, hãy ưu tiên phần tử ảnh và thuộc tính URL chuyên dụng. Nếu thực sự cần URL trong CSS, phải dùng serializer CSS phù hợp cho URL token/string; không nối URL tùy ý vào `url()`.

### 8.3. url() và @import không phải nơi để chèn dữ liệu tùy ý

Ví dụ nguy hiểm:

```js
const css = ".avatar { background-image: url('" + userInput + "'); }";
styleElement.textContent = css;
```

Ngay cả khi URL được đặt trong dấu nháy, dữ liệu vẫn nằm trong stylesheet parser context. Dấu nháy, dấu gạch chéo ngược hoặc các quy tắc escape có thể làm thay đổi cú pháp nếu không được serialize đúng. Ngoài ra, một URL hợp lệ về cú pháp vẫn có thể trỏ tới host không được phép.

Không cho user cung cấp `@import`, `url()` hoặc toàn bộ stylesheet nếu sản phẩm không có yêu cầu rõ ràng. Với chức năng chọn ảnh, nhận một URL đã xác thực hoặc một asset ID được server ánh xạ thường an toàn hơn.

## 9. HTML attribute context và CSS context lồng nhau

Khi viết:

```html
<div style="color: red">Nội dung</div>
```

trình duyệt xử lý HTML trước, sau đó phân tích giá trị style như CSS declaration list. Đây là hai lớp cú pháp:

1. **HTML attribute context:** dấu ngoặc kép, dấu nhỏ hơn và các ký tự HTML đặc biệt cần được xử lý theo quy tắc attribute.
2. **CSS declaration context:** giá trị sau đó phải phù hợp grammar của từng property và không được chèn declaration ngoài ý muốn.

HTML escaping không đảm bảo CSS value an toàn. CSS escaping cũng không thay thế HTML attribute encoding.

Ví dụ, template cần escape attribute theo cơ chế auto-escaping của framework, nhưng dữ liệu đưa vào `style` vẫn cần được validate theo property. Cách tốt hơn thường là tránh tạo style attribute từ chuỗi không tin cậy và dùng class cố định hoặc CSSOM.

### 9.1. Style element có thêm HTML raw-text boundary

Trong HTML:

```html
<style>
  .notice { color: blue; }
</style>
```

nội dung bên trong `<style>` được HTML parser xử lý theo raw-text rules trước khi CSS parser nhận stylesheet. Chuỗi `</style>` có thể kết thúc phần tử style ở tầng HTML ngay cả khi người viết nghĩ nó đang nằm trong CSS string hoặc comment.

Do đó, việc escape theo CSS context không tự động bảo vệ mọi trường hợp khi ghép dữ liệu vào `<style>`. Không chèn input không tin cậy vào nội dung style element. Hãy giữ stylesheet tĩnh và cập nhật giá trị cụ thể qua CSSOM sau khi validate.

## 10. CSS.escape, CSSOM và các API an toàn

| API | Dùng cho | Không dùng để |
|---|---|---|
| `CSS.escape(value)` | Escape identifier dùng trong selector | Escape property value, CSS string hoặc URL |
| `element.style.setProperty()` | Cập nhật một CSS declaration qua CSSOM | Chấp nhận mọi CSS tùy ý mà không validation |
| `element.classList.add/remove()` | Thêm/xóa class đã định nghĩa | Nhận tên class tùy ý mà không kiểm soát |
| `textContent` | Đưa dữ liệu vào DOM như văn bản | Tạo rich HTML |
| `CSS.supports(property, value)` | Kiểm tra browser có nhận cú pháp property/value không | Xác thực quyền nghiệp vụ hoặc allowlist |
| `new URL()` | Parse và chuẩn hóa URL | Chứng minh URL trỏ đến nguồn được tin cậy |

### 10.1. CSS.supports() chỉ kiểm tra cú pháp

Ví dụ:

```js
CSS.supports("color", "rebeccapurple"); // true
CSS.supports("color", "not-a-color");   // false
```

Nếu `CSS.supports()` trả true, điều đó chỉ có nghĩa browser hỗ trợ giá trị theo CSS grammar. Nó không nói sản phẩm có muốn cho phép màu đó hay không, cũng không đánh giá side effect của property phức tạp.

Với input người dùng, hãy dùng allowlist nghiệp vụ trước; `CSS.supports()` có thể là bước kiểm tra tương thích bổ sung.

### 10.2. Chọn class cố định thường tốt hơn sinh CSS

Thay vì:

```js
styleElement.textContent =
  ".card { color: " + userColor + "; background: " + userBackground + "; }";
```

hãy định nghĩa class:

```css
.card--light { color: #111827; background: #ffffff; }
.card--dark { color: #f9fafb; background: #111827; }
.card--brand { color: #ffffff; background: #0f766e; }
```

Sau đó chọn trạng thái bằng class:

```js
const allowedThemes = new Set(["light", "dark", "brand"]);

if (allowedThemes.has(theme)) {
  card.classList.remove("card--light", "card--dark", "card--brand");
  card.classList.add("card--" + theme);
}
```

Đây là cách đơn giản, dễ review và tránh cho dữ liệu đầu vào trở thành CSS source.

## 11. CSP và CSS injection

**Content Security Policy (CSP)** có thể hạn chế stylesheet được tải và cách style inline được sử dụng. Ví dụ:

```http
Content-Security-Policy: default-src 'self'; style-src 'self'; style-src-attr 'none'; object-src 'none'; base-uri 'none'
```

- `style-src` kiểm soát nguồn stylesheet và là fallback cho các directive style cụ thể hơn.
- `style-src-attr` kiểm soát inline style attribute trong trình duyệt hỗ trợ directive này.
- `style-src-elem` kiểm soát phần tử style và link stylesheet trong trình duyệt hỗ trợ.
- `object-src 'none'` và `base-uri 'none'` là các lớp hardening liên quan khác, không trực tiếp encode CSS value.

CSP giúp hạn chế nơi CSS được tải và có thể chặn một số inline style, nhưng **không phải CSS sanitizer**. Nếu ứng dụng cho phép một stylesheet hợp lệ chứa dữ liệu attacker-controlled, CSP không nhất thiết ngăn dữ liệu thay đổi declaration trong stylesheet đó.

### 11.1. CSP không thay validation/encoding

Giả sử stylesheet đến từ `'self'` nhưng server đã ghép input không an toàn vào stylesheet. Browser vẫn tải stylesheet same-origin và parse nội dung. CSP `style-src 'self'` không biết declaration nào đến từ người dùng.

Vì vậy, phải sửa data flow và chỉ đưa giá trị đã validate vào CSSOM/property phù hợp. CSP là defense in depth.

### 11.2. Trusted Types không phải CSS encoder

Trusted Types tập trung vào một số DOM injection sink, đặc biệt các sink liên quan script/HTML. Nó không tự động biến mọi CSS property value, selector hoặc stylesheet string thành an toàn.

Nếu ứng dụng dùng Trusted Types để bảo vệ `innerHTML`, vẫn phải xử lý riêng CSS injection. Không xem TrustedHTML là một kiểu dữ liệu có thể dùng thay cho CSS value đã được kiểm tra.

## 12. Thực hành: tái hiện và sửa CSS injection trong local

Bài lab dưới đây tạo một trang HTML cục bộ. Nút "Thử cách ghép chuỗi" chèn giá trị vào stylesheet; nút "Cách an toàn" chỉ chấp nhận màu từ allowlist và cập nhật CSS qua CSSOM.

### 12.1. Tạo file CSS injection lab

Tạo file `css-encoding-lab.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CSS encoding lab</title>
  <style id="dynamic-style"></style>
  <style>
    body { font-family: sans-serif; padding: 2rem; }
    .preview {
      border: 1px solid #888;
      padding: 1rem;
      margin-top: 1rem;
      color: #111827;
      background: white;
    }
    .status { margin-top: 1rem; }
  </style>
</head>
<body>
  <h1>CSS injection lab</h1>
  <label for="css-value">Giá trị màu:</label>
  <input id="css-value" value="teal">
  <button id="unsafe">Thử cách ghép chuỗi</button>
  <button id="safe">Cách an toàn</button>

  <div class="preview" id="preview">
    Nội dung xem trước
  </div>
  <p class="status" id="status" aria-live="polite"></p>

  <script>
    const input = document.getElementById("css-value");
    const preview = document.getElementById("preview");
    const styleElement = document.getElementById("dynamic-style");
    const status = document.getElementById("status");

    document.getElementById("unsafe").addEventListener("click", () => {
      // DEMO CÓ LỖI: input có thể chứa thêm declaration CSS.
      styleElement.textContent =
        ".preview { color: " + input.value + "; }";
      status.textContent = "Đã ghép input trực tiếp vào stylesheet.";
    });

    const allowedColors = new Set([
      "black", "white", "navy", "teal", "tomato"
    ]);

    document.getElementById("safe").addEventListener("click", () => {
      const value = input.value.trim().toLowerCase();

      if (!allowedColors.has(value)) {
        status.textContent = "Từ chối: màu không nằm trong allowlist.";
        return;
      }

      preview.style.setProperty("color", value);
      styleElement.textContent = "";
      status.textContent = "Đã cập nhật màu qua CSSOM sau khi kiểm tra.";
    });
  </script>
</body>
</html>
```

Mở file trong browser. Nhập giá trị bình thường như `teal`, sau đó thử chuỗi sau ở nút ghép chuỗi:

```text
teal; background-color: yellow; border: 6px solid red
```

Ở nút "Thử cách ghép chuỗi", nhiều declaration có thể được áp dụng. Ở nút "Cách an toàn", giá trị bị từ chối vì không nằm trong allowlist. Ví dụ này minh họa CSS injection vào declaration; nó không thực thi JavaScript.

### 12.2. Quan sát CSSOM và DOM

Mở DevTools:

1. Chọn tab **Elements** và chọn phần tử `#dynamic-style`.
2. Quan sát stylesheet được tạo sau khi nhấn nút ghép chuỗi.
3. Chọn phần tử `#preview` và xem tab **Computed** để xác định property đã thay đổi.
4. Chuyển sang nút an toàn và quan sát style được cập nhật trực tiếp trên phần tử.
5. Thử giá trị `red; display: none` và xác nhận allowlist từ chối.
6. Kiểm tra Console để chắc chắn không có lỗi cú pháp.

### 12.3. Bài tập mở rộng

- Thay allowlist màu bằng allowlist theme (`light`, `dark`, `brand`) và class CSS cố định.
- Thêm trường chiều rộng nhưng chỉ nhận số từ 120 đến 960, đơn vị do code tự thêm.
- Thêm trường ID rồi dùng `CSS.escape()` khi tạo selector; thử ID có dấu hai chấm hoặc dấu cách.
- Thêm trường URL ảnh và kiểm tra URL bằng `new URL()` cùng allowlist origin trước khi gán vào `img.src`.
- Viết CSP `style-src-attr 'none'` trên một server local rồi quan sát inline style attribute bị ảnh hưởng thế nào; kiểm tra khả năng hỗ trợ directive của browser.

Không dùng lab để thử nghiệm trên website hoặc tài khoản không thuộc quyền kiểm thử của bạn.

## 13. Checklist xử lý dữ liệu đưa vào CSS

1. **Xác định context:** Identifier, selector, string, property value, URL, style attribute hay style element?
2. **Ưu tiên không nhận CSS tùy ý:** Dùng class, theme và enum được định nghĩa trước.
3. **Identifier:** Dùng `CSS.escape()` khi dữ liệu thực sự là một identifier trong selector.
4. **Selector:** Tránh nối selector từ input; ưu tiên tham chiếu DOM và class cố định.
5. **Property value:** Validate theo từng property; dùng allowlist, range và kiểu dữ liệu cụ thể.
6. **CSSOM:** Dùng `style.setProperty()` cho giá trị đã được kiểm tra; API này không thay validation.
7. **String:** Tránh đưa dữ liệu người dùng vào CSS `content`; hiển thị văn bản bằng `textContent`.
8. **URL:** Parse URL, giới hạn scheme/host/origin và dùng phần tử `img` khi phù hợp; không nối input vào `url()`.
9. **HTML nesting:** Với style attribute, xử lý cả HTML attribute context và CSS value context; với style element, tránh ghép input vào raw text.
10. **Custom properties:** Kiểm tra dữ liệu tại property tiêu thụ `var()`, không chỉ tại nơi gán custom property.
11. **CSP:** Đặt `style-src`, cân nhắc `style-src-attr` và `style-src-elem`; xem CSP là defense in depth.
12. **Trusted Types:** Không xem Trusted Types là bộ CSS encoder.
13. **Kiểm thử:** Thử dấu chấm phẩy, dấu nháy, backslash, newline, dấu ngoặc, `url()` và giá trị ngoài allowlist.
14. **Review tác động:** Xem liệu CSS có thể ẩn cảnh báo, thay đổi giao diện, tạo network request hoặc làm lộ trạng thái DOM không.

## 14. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "CSS.escape() escape được mọi CSS." | Nó dành cho identifier, đặc biệt khi tạo selector. |
| "HTML attribute encoding đủ an toàn cho style attribute." | Cần bảo vệ cả lớp HTML attribute và CSS declaration/value. |
| "CSS injection luôn là XSS." | CSS thường không thực thi JavaScript tổng quát; tác động có thể là UI tampering, request hoặc data inference. |
| "Dùng style.setProperty là không cần validate." | CSSOM tránh ghép stylesheet nhưng vẫn cần kiểm soát grammar và giá trị nghiệp vụ. |
| "CSS.supports() trả true nghĩa là giá trị được phép." | Nó chỉ kiểm tra browser chấp nhận cú pháp property/value. |
| "Escape URL bằng CSS là đủ." | URL cần parse và kiểm tra scheme/host/origin riêng. |
| "CSP style-src tự loại CSS injection." | CSP kiểm soát nguồn/style policy, không sanitize dữ liệu trong stylesheet được phép tải. |
| "Trusted Types bảo vệ mọi sink." | Trusted Types không phải CSS encoding API. |
| "Có thể decode/escape nhiều lần cho chắc." | Xử lý nhiều lần có thể thay đổi cú pháp; xác định context và encode đúng một lần tại sink. |
| "Người dùng chỉ nhập màu thì có thể cho nhập mọi CSS color grammar." | Nếu nghiệp vụ chỉ cần vài màu, allowlist cụ thể giảm bề mặt và dễ review hơn. |

## 15. Câu hỏi ôn tập

1. CSS injection là gì và khác Reflected XSS như thế nào?
2. Vì sao một input chứa dấu chấm phẩy có thể thoát khỏi property value và chèn declaration mới?
3. `CSS.escape()` phù hợp với ngữ cảnh nào? Vì sao không dùng nó cho màu hoặc URL?
4. Vì sao style attribute cần cả HTML attribute encoding và CSS validation?
5. Tại sao ghép input vào `<style>` có thêm rủi ro từ HTML raw-text parsing?
6. `style.setProperty()` giúp gì và không giải quyết điều gì?
7. Vì sao custom property cần được đánh giá tại nơi `var()` được sử dụng?
8. `CSS.supports()` có thể thay allowlist nghiệp vụ không?
9. CSS `url()` và `@import` có thể tạo rủi ro nào?
10. CSP `style-src` và `style-src-attr` khác nhau ở điểm nào?
11. Trusted Types có phải CSS encoder không?
12. Khi chỉ cần hiển thị nội dung người dùng, vì sao `textContent` phù hợp hơn CSS `content`?

**Đáp án định hướng:** (1) CSS injection thay đổi cú pháp/ý nghĩa stylesheet; Reflected XSS dẫn đến thực thi script trong origin nạn nhân. (2) Dấu chấm phẩy kết thúc declaration hiện tại. (3) Escape identifier trong selector; grammar của property và URL khác. (4) HTML parser xử lý attribute trước CSS parser. (5) `</style>` có thể đóng phần tử ở tầng HTML trước khi CSS parser xử lý. (6) Cập nhật declaration qua CSSOM, nhưng không xác thực giá trị nghiệp vụ. (7) Token stream có thể trở thành cú pháp của property tiêu thụ. (8) Không. (9) Tải tài nguyên ngoài, tracking hoặc một số kênh suy luận dữ liệu. (10) Một directive kiểm soát nguồn stylesheet, directive kia kiểm soát inline style attribute. (11) Không. (12) `textContent` tạo text node, không yêu cầu parser CSS hoặc HTML diễn giải dữ liệu.

## 16. Tài liệu tham khảo

- [MDN — CSS.escape()](https://developer.mozilla.org/en-US/docs/Web/API/CSS/escape_static): Escape giá trị khi dùng như CSS identifier.
- [MDN — CSS Object Model (CSSOM)](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Object_Model): API thao tác stylesheet và style declaration.
- [MDN — CSSStyleDeclaration.setProperty()](https://developer.mozilla.org/en-US/docs/Web/API/CSSStyleDeclaration/setProperty): Cập nhật một property qua CSSOM.
- [MDN — CSS.supports()](https://developer.mozilla.org/en-US/docs/Web/API/CSS/supports_static): Kiểm tra browser hỗ trợ property/value.
- [W3C — CSS Syntax Module Level 3](https://www.w3.org/TR/css-syntax-3/): Tokenization, parsing và serialization của CSS.
- [OWASP — CSS Injection](https://owasp.org/www-community/attacks/CSS_Injection): Tổng quan nguy cơ CSS injection và các dạng tác động.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): Các directive CSP, bao gồm chính sách stylesheet.
- [MDN — style-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src): Kiểm soát nguồn stylesheet.
- [MDN — style-src-attr](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src-attr): Kiểm soát inline style attribute.
- [MDN — Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API): Phạm vi và giới hạn của Trusted Types đối với DOM injection sink.

**Kết nối với mô hình bảo mật web:** CSS encoding là một phần của output encoding theo ngữ cảnh. Dữ liệu đưa vào selector, CSS string, property value hoặc URL cần cách xử lý khác nhau. HTML escaping, URL validation, CSS.escape, CSSOM, CSP và Trusted Types giải quyết các lớp vấn đề riêng; kết hợp đúng từng lớp giúp ngăn dữ liệu người dùng thay đổi cấu trúc stylesheet hoặc tạo hành vi ngoài ý muốn.
