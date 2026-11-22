# XSS vẫn cần mã hóa đầu ra và xử lý dữ liệu theo ngữ cảnh

> **Module:** Spring Security – fundamentals → **Bảo vệ trình duyệt**. **Cross-Site Scripting (XSS)** là nhóm lỗi xảy ra khi dữ liệu không đáng tin được đưa vào trang web hoặc DOM khiến trình duyệt hiểu dữ liệu đó như **HTML/JavaScript/CSS có hiệu lực**, thay vì chỉ hiển thị văn bản. **Spring Security không tự động làm an toàn mọi giá trị mà controller, template hoặc JavaScript hiển thị.** Cơ chế cốt lõi là **mã hóa đầu ra đúng ngữ cảnh** (*contextual output encoding*) hoặc dùng **DOM API an toàn**; nếu sản phẩm phải render HTML do người dùng viết, cần **HTML sanitization theo allowlist**. Các cơ chế như CSP, HttpOnly, SameSite, CSRF và HTTP security headers chỉ bổ sung, không thay thế phòng chống XSS tại điểm đưa dữ liệu vào browser.

Bài học dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC**, trình bày các vị trí HTML text, attribute, URL, JavaScript, CSS, DOM và JSON. Có ví dụ chạy được với **OWASP Java Encoder**, JavaScript `textContent`, cấu hình CSP defense-in-depth và kiểm thử MockMvc.

## 1. Tại sao một ứng dụng có Spring Security vẫn bị XSS?

Hệ thống có thể cấu hình đăng nhập, phân quyền, CSRF token, cookie `HttpOnly` và nhiều security headers nhưng vẫn có controller:

```java
@GetMapping(value = "/hello", produces = "text/html")
@ResponseBody
String hello(@RequestParam String name) {
    // PHẢN VÍ DỤ: nối trực tiếp input vào HTML.
    return "<h1>Xin chào " + name + "</h1>";
}
```

Nếu `name` là một chuỗi chứa markup do người khác kiểm soát, browser có thể parse nó như một phần cấu trúc HTML thay vì văn bản. Ví dụ đầu vào mang hình dạng:

```text
<img src=x onerror=alert(1)>
```

Đây là **mẫu kiểm tra vô hại trong môi trường local** để minh họa thuộc tính sự kiện có thể trở thành mã thực thi. Không sử dụng payload tấn công trên hệ thống không được phép thử. Nếu đầu vào được nối nguyên văn, kết quả là một `<img>` trong HTML, khác hoàn toàn với việc hiển thị một chuỗi chữ `<img ...>`.

**Quyết định bảo mật phải nằm ở chỗ đưa dữ liệu ra:** Controller/API nhận và lưu dữ liệu có thể làm nhiều bước; nhưng tại thời điểm kết quả được nhúng vào **HTML, JavaScript, CSS, thuộc tính, URL hoặc DOM**, ta phải hiểu **parser nào sẽ đọc dữ liệu này**. Bộ mã hóa cho HTML text không mặc nhiên đúng cho JavaScript string, và bộ mã hóa URL component không đủ để xác minh rằng một URL có scheme an toàn.

Một Spring Security `SecurityFilterChain` có thể:
- Yêu cầu user đăng nhập trước khi truy cập route.
- Kiểm tra role/authority, CSRF và SecurityContext.
- Cài các HTTP headers như `X-Content-Type-Options`, `X-Frame-Options` hay CSP khi được cấu hình.
- Giúp hạn chế một số hậu quả nếu trang bị chèn mã.

Nhưng nó **không biết mỗi biến trong Thymeleaf/React/JSP hay mỗi lời gọi `innerHTML` của client được đặt ở parser context nào**. Việc escape/sanitize ở output là trách nhiệm của tầng render/client và thư viện template phù hợp.

## 2. Phân loại XSS và trust boundary

| Kiểu | Dòng dữ liệu | Ví dụ đặc trưng | Phòng vệ cần tập trung |
|---|---|---|---|
| **Reflected XSS** | Query/header/input request → HTML response ngay lập tức | `/search?q=...` hiển thị query thành markup | Encode tại render, template autoescape, URL validation |
| **Stored XSS** | Comment/profile/nội dung DB → trang của người khác | Bình luận chứa markup không được xử lý | Encode ở mọi output hoặc sanitize rich HTML khi được phép |
| **DOM-based XSS** | URL hash, query, message từ `postMessage`, API → DOM sink ở browser | JS gán untrusted string vào `innerHTML` | DOM `textContent`, safe APIs, URL allowlist, Trusted Types hỗ trợ |
| **Markup/template injection** | Input trở thành cú pháp template/element/attribute thay vì data | Cho user chọn raw template name hoặc unescaped HTML | Không xem input là template source; giữ syntax tin cậy cố định |

**Đường dữ liệu rất quan trọng:** attacker có thể kiểm soát query parameter, request path, form data, user profile, comment, file name, dữ liệu từ bên thứ ba, WebSocket event, API response, message bus, localStorage hoặc URL fragment. “Dữ liệu nằm trong DB” không khiến nó trở thành trusted; một đoạn stored XSS chỉ đang chờ được render vào trang khác.

### 2.1. Tài sản và hậu quả

Một XSS chạy dưới origin của ứng dụng có thể:
- Gọi API cùng origin với credential browser tự gửi.
- Đọc nội dung trang/DOM và dữ liệu người dùng được hiển thị.
- Thay đổi giao diện để phishing hoặc thao túng thao tác.
- Gửi các request có CSRF token mà chính trang có thể đọc.
- Đọc token/secret mà JavaScript được phép truy cập, hoặc tương tác với API dưới phiên của nạn nhân.

Cookie `HttpOnly` giúp script không đọc trực tiếp giá trị cookie, nhưng **không ngăn script gửi request cùng origin với cookie vẫn được browser đính kèm**. CSRF token cũng không ngăn XSS vì mã chạy trên origin hợp lệ có thể lấy/gửi token. Vì vậy cần chặn XSS ngay tại các sink.

### 2.2. Input validation khác output encoding

Validation nên kiểm tra dữ liệu **theo nghiệp vụ**: độ dài username, danh sách trạng thái, format email, số lượng, loại file. Ví dụ theme chỉ nhận `dark` hoặc `light`; `id` là số nguyên dương. Đây là cách giảm dữ liệu vô nghĩa/không hợp lệ.

Nhưng một bình luận hợp lệ có thể chứa ký tự `<`, `>`, `"`, `'`, `&`; không thể cấm hết ký tự đó cho toàn sản phẩm. Đặc biệt, một input đã được lưu an toàn ở DB có thể xuất hiện nhiều nơi:
- Trong text của `<p>`.
- Trong attribute `title`.
- Trong JSON đưa tới JS.
- Trong URL query.
- Trong một email hoặc PDF xuất ra.

Mỗi nơi cần quy tắc encoding riêng. **Không có một hàm "sanitize input" chung áp dụng đúng cho tất cả output.**

## 3. Quy tắc quan trọng nhất: mã hóa theo parser context

Giả sử biến `comment` là chuỗi raw từ DB. Các parser hoạt động khác nhau:

| Vị trí nhận dữ liệu | Ví dụ | Cách làm đúng | Điều không đủ |
|---|---|---|---|
| HTML text node | `<p>comment</p>` | HTML entity encoding hoặc `textContent` | URL encode, chỉ thay `<` |
| Quoted HTML attribute bình thường | `<input value="comment">` | Attribute encode và **luôn quote** | Chỉ encode HTML text, attribute không quote |
| URL query component | `/search?q=comment` | Percent encode **component**, build URL từ phần trusted | Encode cả URL như một giá trị hoặc validate bằng substring |
| URL nằm trong HTML attribute | `<a href="/search?q=...">` | Encode component → ghép trusted URL → HTML attribute encode | Chỉ percent encode rồi cho vào attribute bất kỳ |
| JavaScript string trong HTML `<script>` | `const x = "...";` | Tránh nhúng; hoặc encoder dành cho **script-block string** | Chỉ HTML encode, chỉ đổi quote |
| DOM text | `element.textContent = comment` | Dùng `textContent`/`createTextNode` | `innerHTML` với raw data |
| CSS value | `style="color: comment"` | Fixed property + allowlist value, dùng CSSOM khi phù hợp | HTML encode raw CSS |
| Rich HTML do user nhập | WYSIWYG comment | HTML sanitizer có policy allowlist | `th:utext` với raw content |
| Event handler/script/HTML tag/attribute name | `onclick=...` hoặc tag do user chọn | **Không đưa untrusted data vào vị trí code** | Một encoder string chung |
| JSON response | API trả `{"message":comment}` | Serializer JSON chuẩn, `Content-Type: application/json` | Nối tay JSON hoặc chèn JSON raw vào HTML |

**Sự khác biệt quyết định:** HTML parser, JavaScript parser, CSS parser và URL parser có thể xử lý cùng ký tự theo cách hoàn toàn khác. Nếu một chuỗi đi qua **hai parser**, ví dụ URL nằm trong HTML attribute, phải xử lý đủ **hai ngữ cảnh**. Nếu một giá trị còn được đưa vào DOM sink sau đó, cần xét tiếp ngữ cảnh ở client.

### 3.1. Mã hóa tại điểm cuối, không mã hóa dữ liệu gốc vô điều kiện

Trong domain/service/database, ưu tiên lưu dữ liệu **theo nghĩa gốc** sau khi đã validate theo nghiệp vụ. Encode **khi đi ra một parser cụ thể**. Không lưu `&lt;` vào mọi trường ở DB chỉ vì cần hiển thị chữ `<` trên trang: lần sau dùng nó trong JSON, email hoặc text khác có thể bị double encoding hoặc sai semantics.

Nếu cần lưu HTML đã được **sanitizer** xử lý, đó là một lựa chọn khác: lưu nội dung rich-text đã qua policy có version, có thể kèm raw original ở kho an toàn tùy nghiệp vụ, và phải kiểm soát mọi nơi sử dụng. Sanitization không có nghĩa “bất kỳ HTML nào đã qua xử lý đều an toàn cho mọi parser”.

### 3.2. Không escape nhiều lần

Ví dụ string `<b>A&B</b>` khi encode HTML một lần có thể trở thành `&lt;b&gt;A&amp;B&lt;/b&gt;`. Nếu encode lần nữa, browser có thể hiển thị nguyên `&lt;...` thay vì ký tự mong muốn.

**Quy tắc:** Đặt trách nhiệm encode rõ ràng tại boundary; nếu template engine tự escape, không gọi thêm encoder HTML text rồi đưa tiếp vào `th:text`. Dùng test trên cả input có ký tự đặc biệt lẫn input bình thường để phát hiện double-encode.

## 4. HTML text context: giữa hai thẻ

Với dữ liệu untrusted hiển thị giữa thẻ cố định:

```html
<p>Xin chào, USER_NAME</p>
```

Cần HTML entity encoding để `<` không bắt đầu element, `&` không mở entity và một số ký tự đặc biệt khác không làm thay đổi cú pháp.

Ví dụ:

| Raw character | HTML representation thường gặp |
|---|---|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| `"` | `&quot;` hoặc numeric entity |
| `'` | `&#x27;` hoặc numeric entity |

**Chú ý:** Một encoder được kiểm chứng có thể dùng numeric entities hoặc một dạng tương đương khác; test nên xác nhận **text vẫn chỉ là text** chứ không ép chính xác một cách escape duy nhất.

Sử dụng thư viện Java được duy trì:

```java
import org.owasp.encoder.Encode;

String safe = Encode.forHtmlContent(userText);
String html = "<p>" + safe + "</p>";
```

Đoạn này **minh họa trong method**, không phải class runnable độc lập. Với `Encode.forHtmlContent`, thư viện làm encoding cho **HTML text context**. Nếu đang dùng một template engine đã encode tự động, ưu tiên cách render native của engine thay vì vừa gọi Java encoder vừa dùng chế độ autoescape.

### 4.1. Browser không “tự bảo vệ” khi nhìn thấy dữ liệu trong HTML

Nếu server trả response `Content-Type: text/html`, browser parse nội dung như HTML. Một chuỗi nối raw vào HTML không trở nên an toàn vì nó xuất phát từ một API dùng Spring Security hay vì database đã dùng prepared statement. SQL injection, authentication và XSS là các ranh giới khác nhau.

### 4.2. DOM API thay HTML string khi có thể

Nếu JavaScript đang xây giao diện và chỉ muốn hiển thị văn bản:

```javascript
const message = new URLSearchParams(location.search).get("message") ?? "";
const output = document.querySelector("#message");
output.textContent = message;
```

`textContent` trên phần tử HTML thông thường sẽ đưa chuỗi thành text node, **không parse HTML**. Không tự encode HTML trước khi dùng `textContent`; nếu làm vậy người dùng sẽ thấy `&lt;` thay vì dấu `<`. Dùng `createTextNode` hoặc `insertAdjacentText` cũng hợp lý. Nhưng `textContent` gán lên `<script>` hoặc `<style>` là một ngữ cảnh khác và có thể tạo code; luôn chọn phần tử đích tin cậy.

## 5. HTML attribute context: phải quote và chọn attribute an toàn

Ví dụ giá trị nằm trong input attribute:

```html
<input name="displayName" value="USER_NAME">
```

Cần **giữ nguyên tên attribute, giữ dấu quote** và mã hóa giá trị cho **HTML attribute context**:

```java
String html = "<input name=\"displayName\" value=\"" +
    Encode.forHtmlAttribute(userName) + "\">";
```

Nếu không quote:

```html
<!-- PHẢN VÍ DỤ: attribute không được quote -->
<input value=USER_NAME>
```

Whitespace có thể kết thúc attribute value, dẫn tới việc parser đọc các phần tiếp theo thành attribute mới. Vì thế không xây HTML bằng cách nối chuỗi với unquoted attribute. Ngay cả khi quoted, **attribute name** phải cố định và an toàn.

### 5.1. Attribute không cùng mức độ nguy hiểm

Các attribute như `title`, `value` hoặc `alt` thường là text attributes. Nhưng:
- `href` / `src` cần **URL scheme + destination validation** bên cạnh attribute encoding.
- `style` phải xét **CSS parsing** và loại property/value được phép.
- `onclick`, `onerror` và các event-handler attributes đưa dữ liệu vào **JavaScript execution context**.
- `srcdoc` chứa **HTML document** và không nên nhận raw user content.
- `data-*` là dữ liệu cho JS, nhưng JS tiếp tục phải dùng nó an toàn khi chuyển sang DOM.

**Không có “forHtmlAttribute” thần kỳ khiến mọi attribute an toàn.** Với event handler, giải pháp là không nhúng input vào code; dùng sự kiện đã viết sẵn:

```javascript
const button = document.getElementById("save");
button.addEventListener("click", () => {
  saveDocument(); // trusted function
});
```

Khi set text attribute từ JavaScript:

```javascript
input.setAttribute("title", untrustedTitle);
input.value = untrustedValue;
```

DOM API set giá trị literal cho attribute/property cụ thể, không cần HTML encode trước. Tuy nhiên đừng dùng `setAttribute("onclick", value)` hay một attribute tên động chưa được approve; API đó không tự validate policy cho event/URL/CSS attributes.

## 6. URL context: encode query component, còn URL phải được phép

Giả sử ứng dụng cung cấp link tìm kiếm:

```html
<a href="/search?q=QUERY">Tìm kiếm</a>
```

Không nối input raw vào URL. Có hai bước:

1. Dùng phần URL gốc **do server quy định**, ví dụ `/search?q=`, và percent-encode riêng **value** của `q`.
2. Khi gắn URL đã xây vào `href` trong HTML, dùng **HTML attribute encoding** cho cả URL hoàn chỉnh.

Ví dụ:

```java
String url = "/search?q=" + Encode.forUriComponent(query);
String html = "<a href=\"" +
    Encode.forHtmlAttribute(url) + "\">Tìm kiếm</a>";
```

`Encode.forUriComponent` giúp kí tự `&` trong query không biến thành một parameter khác, `#` không trở thành fragment và dấu quote không phá cấu trúc HTML. Nhưng **URL encoding không phải URL validation**.

### 6.1. URL hoàn chỉnh do user đưa vào là bài toán khác

Nếu sản phẩm cho người dùng nhập “link website cá nhân”:

```text
javascript:alert(1)
data:text/html,...
//other-host.example/
https://trusted.example.attacker.net/path
```

Không thể chỉ percent-encode toàn bộ chuỗi rồi cho vào `href`. Cần:
- Parse URL và chuẩn hóa theo chuẩn phù hợp.
- Chỉ cho scheme `https` (hoặc `http` nếu được duyệt rõ ràng).
- Giới hạn host/port/path khi link đi tới tài nguyên nội bộ hoặc callback bảo mật.
- Từ chối `javascript:`, `data:`, URL relative hoặc scheme-relative nếu không thuộc hợp đồng.
- Tránh whitelist bằng `contains("trusted.example")` hoặc `endsWith("trusted.example")` thiếu dấu chấm ranh giới.
- Sau khi validate, vẫn **HTML attribute encode** khi render trong `href`.

**Nối URL từ route + ID đã kiểm tra server-side thường an toàn, dễ audit hơn việc nhận URL tùy ý.** Nếu mục tiêu chỉ là điều hướng nội bộ, dùng một **alias allowlist** như `dashboard`/`report` để server chọn đích.

### 6.2. DOM URL attribute cũng cần chính sách

Trong JavaScript:

```javascript
const url = new URL("/search", location.origin);
url.searchParams.set("q", rawQuery);
link.href = url.toString();
link.textContent = "Tìm kiếm";
```

Đây là cách tốt cho **base URL tin cậy** + query parameter. Nhưng nếu thay `"/search"` bằng một string tùy ý từ user, `new URL` chỉ parse/resolve, không xác nhận đích được phép. Với `link.href = untrustedUrl`, vẫn cần policy scheme/host.

## 7. JavaScript context: không trộn input với code

Đây là ngữ cảnh dễ sai dù đã HTML escape:

```html
<!-- PHẢN VÍ DỤ: input bị nối thẳng vào JS source -->
<script>
  const message = "USER_INPUT";
</script>
```

JavaScript parser xử lý quote, backslash, escape sequences, template literal và cú pháp expression. Ngoài ra, HTML parser có quy tắc đặc biệt đối với `<script>` và chuỗi có thể đóng khối script. **HTML entity encoding không phải JavaScript string encoding**; việc chỉ thay `"` thành `\\"` cũng không đủ để bảo vệ khối HTML chứa script.

### 7.1. Ưu tiên tránh inline script data

Cách an toàn và dễ bảo trì là:
- Server trả dữ liệu dưới dạng JSON với `Content-Type: application/json`.
- File JS riêng nhận data qua `fetch`/JSON parser.
- Khi hiển thị, JS dùng `textContent`, `value`, `createTextNode`.
- Nếu phải thao tác URL/style, dùng allowlist và API tương ứng.
- CSP có thể áp dụng `script-src 'self'`/nonce để hạn chế inline code.

Ví dụ:

```javascript
const response = await fetch("/api/display-name", {
  credentials: "same-origin"
});
const payload = await response.json();
document.getElementById("displayName").textContent = payload.name;
```

`JSON.parse`/`response.json()` giải mã dữ liệu, không chạy như JavaScript source. Không dùng `eval()` để “parse” JSON.

### 7.2. Nếu bắt buộc nhúng string vào script block

Một số ứng dụng legacy cần render giá trị vào `<script>`. Khi đó dùng encoder được tài liệu hóa cho **JavaScript string trong HTML script context**, không đưa input vào tên biến/cú pháp điều khiển:

```java
String encoded = Encode.forJavaScriptBlock(rawMessage);
String script = "<script>const message = \"" + encoded +
    "\";</script>";
```

Đây là **snippet** dùng OWASP Java Encoder, không phải cách mặc định cho thiết kế mới. Chỉ dùng khi input nằm **trọn trong string literal được quote tin cậy** và library/version hỗ trợ. Không dùng trực tiếp cho expression, dynamic JavaScript, HTML event handler hoặc template literal dạng expression `${...}`. Đừng nhầm `Encode.forJavaScriptBlock` với `Encode.forJavaScriptSource` (dành cho standalone JS source) hoặc HTML attribute encoder.

Với dữ liệu JSON nhúng vào HTML, `JSON.stringify`/serializer JSON **không tự bảo đảm** an toàn khi chèn raw vào `<script>`. Nếu cần inline initial state, phải có serialization strategy dành cho HTML script context và CSP phù hợp; lựa chọn đơn giản hơn là endpoint JSON riêng.

### 7.3. Các DOM sinks nguy hiểm

| Sink | Vấn đề | Thay thế |
|---|---|---|
| `element.innerHTML = raw` | Parse raw thành HTML | `element.textContent = raw` nếu chỉ hiển thị chữ |
| `element.outerHTML = raw` | Thay cấu trúc DOM | Dùng createElement + textContent với tags cố định |
| `element.insertAdjacentHTML(..., raw)` | Parse markup | `insertAdjacentText` / append text node |
| `document.write(raw)` | Tạo HTML bằng string | DOM API |
| `eval(raw)`, `new Function(raw)` | Biến dữ liệu thành mã | JSON.parse/data-driven logic |
| `setTimeout(rawString, ...)` | Có thể thực thi string như code | Callback function |
| `location = rawUrl` | Điều hướng tới URL không tin cậy | Validate redirect/target URL |
| `iframe.srcdoc = raw` | Parse HTML document | Tránh, hoặc sanitizer + sandbox policy chặt |
| `dangerouslySetInnerHTML` / `v-html` | Bỏ cơ chế text escaping mặc định của framework | Chỉ sanitized rich HTML có policy |
| `createElement(untrustedTag)` | User chọn tên element, có thể tạo phần tử đặc biệt | Fixed tag hoặc allowlist |

**Lưu ý:** `setAttribute()` hoặc `textContent` là an toàn **khi dùng đúng loại element/attribute**. Set `href` tới `javascript:...` hoặc đặt `textContent` trên `script` vẫn có ngữ nghĩa khác. Không biến API an toàn theo ngữ cảnh thành lời hứa “mọi trường hợp đều an toàn”.

## 8. CSS context: đừng cho user viết style source

CSS cũng có parser và các property có thể dẫn tới tải resource hoặc hành vi không mong muốn. Ví dụ:

```html
<!-- PHẢN VÍ DỤ: không nối input tự do vào style -->
<div style="background-image: USER_INPUT">...</div>
```

Không dùng HTML attribute encoding làm cách duy nhất để cho phép chuỗi CSS tùy ý. Nếu sản phẩm cho chọn màu hoặc theme, **đổi từ giá trị tùy ý thành allowlist**:

```javascript
const themes = new Set(["light", "dark", "high-contrast"]);
const selected = themes.has(rawTheme) ? rawTheme : "light";
document.documentElement.dataset.theme = selected;
```

CSS thật là static:

```css
:root[data-theme="light"] { --surface: #fff; --text: #111; }
:root[data-theme="dark"] { --surface: #111; --text: #fff; }
:root[data-theme="high-contrast"] { --surface: #000; --text: #ff0; }
```

Nếu phải set một CSS property bằng JS, dùng tên property **cố định** và value được validate theo hợp đồng của property:

```javascript
const allowed = new Set(["red", "blue", "green"]);
const color = allowed.has(rawColor) ? rawColor : "blue";
element.style.setProperty("color", color);
```

Đừng cho phép bất kỳ string trong `background-image`, `url(...)`, CSS selector hay `style` block mà chưa có policy. `style.setProperty` chỉ thiết lập value; nó **không tự xác định value có hợp lệ về mặt bảo mật**.

## 9. Rich text HTML: khi output encoding không đủ về mặt UX

Có những tính năng cho user nhập HTML qua WYSIWYG editor: bình luận có chữ đậm, gạch đầu dòng, link, bảng. Nếu dùng HTML text encoding, toàn bộ tags trở thành văn bản; **bảo mật đúng nhưng không đạt mục tiêu rich text**.

Khi sản phẩm thực sự cho phép một tập HTML giới hạn, dùng **HTML sanitizer** được duy trì, có policy allowlist cho tags, attributes, protocols. Ví dụ OWASP Java HTML Sanitizer:

```java
import org.owasp.html.PolicyFactory;
import org.owasp.html.Sanitizers;

PolicyFactory policy = Sanitizers.FORMATTING
    .and(Sanitizers.LINKS);
String safeHtml = policy.sanitize(userAuthoredHtml);
```

Đây là đoạn minh họa, không thuộc demo runnable ở mục 11. Cần thêm dependency **OWASP Java HTML Sanitizer** tương thích và xem chính sách thực tế; gói mặc định `FORMATTING`/`LINKS` chỉ là điểm khởi đầu. Nếu cần image, table, embed, iframe hay custom attributes, **phải đánh giá chính sách cụ thể**, không bật toàn bộ HTML.

### 9.1. Một sanitizer đúng cần xét điều gì?

- Tags nào được phép: `p`, `b`, `i`, `ul`, `li`, `a`? Có cần `style`, `svg`, `math` không?
- Attributes nào được phép **trên tag nào**; `href` có allowed protocols nào; có chặn `javascript:`/`data:`?
- HTML entities và URL decoding/canonicalization được xử lý thế nào?
- Có thêm `rel="noopener noreferrer"` cho link ngoài qua policy khi cần?
- Có cần phân biệt hình ảnh nội bộ và liên kết bên ngoài?
- Có sanitizer hỗ trợ browser parser semantics, malformed HTML và CSS URL syntax không?
- Library có được cập nhật bảo mật và có test attack corpus không?
- Có bảo vệ việc **thay đổi HTML sau khi sanitize**? Một component/JS code có thể tái tạo lỗ hổng khi thêm raw string về sau.
- Có cache/invalidation khi policy hoặc sanitizer version đổi không?

Không tự viết sanitizer bằng regex kiểu xóa chuỗi `<script>`. Browser có nhiều cách parse HTML, SVG/MathML, comments, entity, malformed tags, URL protocols và nested contexts; regex thông thường không phải HTML parser đáng tin cậy. Nếu không cần rich HTML, **escape thành text** sẽ đơn giản và an toàn hơn.

### 9.2. Client sanitizer

Với browser, OWASP thường khuyến nghị `DOMPurify` cho use case cần HTML sanitization. Ví dụ:

```javascript
const sanitized = DOMPurify.sanitize(untrustedHtml);
richTextContainer.innerHTML = sanitized;
```

Chỉ dùng khi `DOMPurify` được cài phiên bản an toàn, cấu hình allowlist chặt và nội dung không bị biến đổi thêm theo cách không an toàn sau sanitize. Với CSP Trusted Types, có thể cần chính sách sinh `TrustedHTML` đúng cách. Không sử dụng `innerHTML` chỉ vì muốn tiện render plain text.

## 10. Template engines và frontend frameworks

### 10.1. Thymeleaf: `th:text` khác `th:utext`

Thymeleaf trong Spring MVC cung cấp chế độ escaped text mặc định:

```html
<!-- SAFE với plain text: biến được HTML escape -->
<p th:text="${comment.body}">Nội dung</p>
<input th:value="${user.displayName}" value="">
```

Nếu `comment.body` chứa ký tự `<` và `>`, chúng được hiển thị thành chữ thay vì markup khi dùng `th:text`. Với `th:value`, engine xử lý attribute rendering theo syntax của template, nhưng **giá trị URL/CSS/event handler vẫn cần policy riêng**.

```html
<!-- CẢNH BÁO: th:utext là unescaped HTML -->
<div th:utext="${comment.body}"></div>
```

`th:utext` dùng khi bạn đã có **sanitized rich HTML** đúng policy. Nếu đưa raw user content vào, dữ liệu có thể bị parse thành markup. Cú pháp inlining cũng cần phân biệt:
- `[[${comment.body}]]`: escaped text.
- `[(${comment.body})]`: unescaped text.

**Đừng “fix” giao diện bị hiển thị ký tự HTML bằng cách đổi hết `th:text` sang `th:utext`.** Nếu muốn rich text, xử lý sanitizer đúng cách và chỉ dùng unescaped render tại thành phần được review.

### 10.2. React, Vue, Angular

Các framework frontend hiện đại thường **escape plain text bindings** mặc định:

- React: `<div>{comment.body}</div>` được xử lý là text trong normal JSX rendering; `dangerouslySetInnerHTML` là escape hatch có rủi ro.
- Vue: `{{ comment.body }}` hiển thị escaped text; `v-html` chèn HTML cần sanitizer.
- Angular: interpolation `{{ comment.body }}` dùng sanitization/escaping phù hợp theo context; các lệnh bypass như `bypassSecurityTrustHtml` phải được review cẩn thận.

Một framework tự escape không đủ bảo vệ khi code chuyển sang DOM APIs nguy hiểm, thao tác URL không validate, render HTML tùy ý hoặc dynamic script execution. **Không tin dữ liệu chỉ vì nó tới từ backend đã xác thực.**

### 10.3. JSP và Java servlet string templates

Với JSP/JSTL, sử dụng output escaping theo chuẩn của JSP/tag library; nếu dùng servlet `out.write` và nối HTML thủ công thì phải encode theo ngữ cảnh. OWASP Java Encoder cung cấp những API riêng cho HTML text, attribute, JavaScript string và URI component; ưu tiên công cụ được duy trì thay vì tự viết hàm `replace` ký tự.

### 10.4. Server-Side Rendering (SSR) và hydration

Khi SSR render HTML rồi frontend hydrate, cùng dữ liệu có thể được nhúng:
- Vào HTML text node: cần HTML text encoding.
- Vào JSON initial state trong `<script>`: cần xử lý **cả JSON và HTML script context** hoặc chuyển sang endpoint JSON riêng.
- Vào HTML attributes: cần attribute encoding và URL validation tương ứng.
- Vào client DOM sau hydrate: dùng safe sinks.

**Một giá trị được bảo vệ ở một boundary không tự được bảo vệ nếu bị chuyển sang parser khác.**

## 11. Ví dụ Spring Boot 3.x / Java 17+ chạy được

Ta viết một ứng dụng Spring MVC nhỏ:
- `GET /demo?name=...` trả HTML hiển thị tên theo **HTML text context**, **quoted HTML attribute context**, và **URL query component nằm trong href**.
- File JS tĩnh dùng `textContent` để hiển thị cùng query parameter, không dùng `innerHTML`.
- `GET /search?q=...` và `GET /api/display-name?name=...` trả JSON bằng Jackson thay vì tự nối JSON string.
- Spring Security cho phép các GET demo, từ chối các route còn lại, thêm **CSP defense-in-depth** để hạn chế thực thi inline script. CSP không phải cơ chế chính thay encoding.
- MockMvc kiểm tra browser không nhận markup do người dùng trực tiếp tạo và kiểm tra CSP headers.

### 11.1. Dependencies

Dùng Spring Initializr tạo project Java 17+, **Spring Boot 3.x**, chọn Gradle, **Spring Web**, **Spring Security**. Trong `build.gradle` do Initializr tạo, đặt khối dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.owasp.encoder:encoder:1.6.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối dependencies**, không phải toàn bộ `build.gradle`: giữ plugins, repositories, Java version và BOM từ project. `org.owasp.encoder` là thư viện **OWASP Java Encoder**; version `1.6.0` là bản chính thức được công bố tháng 10/2026. Nếu dự án dùng BOM/security update riêng, chọn phiên bản an toàn tương thích và kiểm thử.

### 11.2. Tệp Java ứng dụng

Tạo `src/main/java/example/xss/XssEncodingApplication.java`:

```java
package example.xss;

import java.util.Map;

import org.owasp.encoder.Encode;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class XssEncodingApplication {
    public static void main(String[] args) {
        SpringApplication.run(XssEncodingApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/demo", "/search", "/api/display-name",
                    "/js/**").permitAll()
                .anyRequest().denyAll())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "frame-ancestors 'none'")))
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping(value = "/demo",
                produces = MediaType.TEXT_HTML_VALUE)
    String demo(@RequestParam(defaultValue = "") String name) {
        String safeHtmlText = Encode.forHtmlContent(name);
        String safeAttribute = Encode.forHtmlAttribute(name);
        String searchUrl =
            "/search?q=" + Encode.forUriComponent(name);
        String safeHref = Encode.forHtmlAttribute(searchUrl);

        return """
            <!doctype html>
            <html lang="vi">
            <head>
              <meta charset="UTF-8">
              <title>Context-aware XSS encoding</title>
            </head>
            <body>
              <h1>Xin chào, %s</h1>
              <label>Giá trị thô được hiển thị an toàn:
                <input readonly value="%s">
              </label>
              <p><a href="%s">Tìm kiếm tên này</a></p>
              <p id="domText"></p>
              <script src="/js/demo.js" defer></script>
            </body>
            </html>
            """.formatted(
                safeHtmlText, safeAttribute, safeHref);
    }

    @GetMapping("/search")
    Map<String, String> search(
            @RequestParam(defaultValue = "") String q) {
        return Map.of("query", q);
    }

    @GetMapping("/api/display-name")
    Map<String, String> displayName(
            @RequestParam(defaultValue = "") String name) {
        return Map.of("name", name);
    }
}
```

**Đọc code:**

1. `Encode.forHtmlContent(name)` xử lý raw value vào `<h1>...`. Browser hiển thị input có dấu đặc biệt như văn bản, không tạo element tùy ý.
2. `Encode.forHtmlAttribute(name)` xử lý input vào một attribute `value` **đã quote**. Không dùng input để chọn tên element hay attribute.
3. `Encode.forUriComponent(name)` chỉ encode query value `q`; phần route `/search?q=` do server chọn. `Encode.forHtmlAttribute(searchUrl)` tiếp tục bảo vệ khi URL vào `href`.
4. `Map.of("name", name)` được Spring MVC/Jackson serialize thành JSON với MIME JSON đúng theo auto-configuration. Nó trả dữ liệu, không tự render HTML. Nếu frontend lấy JSON này rồi dùng `innerHTML`, frontend vẫn có thể gây XSS.
5. `SecurityFilterChain` chỉ cấp quyền tới các GET demo; không tự làm escape input. `contentSecurityPolicy(...)` là thêm lớp bảo vệ HTTP response; các giải pháp encoder/safe DOM vẫn bắt buộc.
6. `default-src 'self'` và `script-src 'self'` cho phép script từ chính origin, nhưng không phải CSP nghiêm ngặt nhất cho mọi ứng dụng. CSP cần cân nhắc nonces/hashes, third-party resources, reporting, strict-dynamic, Trusted Types và tính tương thích.
7. Demo không lưu DB, không tạo trang login, không cần session cho GET public. Nếu thêm đăng nhập/user-generated content, cần kiểm tra thêm authorization và lưu trữ.

### 11.3. File JavaScript độc lập, không inline code

Tạo `src/main/resources/static/js/demo.js`:

```javascript
"use strict";

const params = new URLSearchParams(window.location.search);
const name = params.get("name") ?? "";
const target = document.getElementById("domText");

if (target) {
  // Data trở thành plain text, không được parse thành HTML.
  target.textContent = name;
}
```

Chạy dưới CSP `script-src 'self'` vì file được serve từ cùng origin. `textContent` không cần HTML encoding sẵn; hãy đưa raw string cho DOM text API. Không thay nó bằng `target.innerHTML = name`.

CSP trong demo **không có `'unsafe-inline'`**, nên phần JavaScript chạy trong file tĩnh, không phải inline `<script>...`. Không dùng event attributes `onclick`/`onerror` làm code của sản phẩm.

### 11.4. Chạy và thử thủ công

Trong project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mở ở local:

```text
http://localhost:8080/demo?name=Alice
```

Kỳ vọng:
- Trang hiển thị `Xin chào, Alice`.
- Input readonly chứa `Alice`.
- Link dẫn tới `/search?q=Alice`.
- Script tĩnh hiển thị `Alice` ở paragraph `domText`.

Để kiểm tra input ký tự đặc biệt, dùng browser encode URL khi nhập query, ví dụ ở DevTools hoặc qua thao tác encode URI component của browser. **Đừng thử payload tấn công ở hệ thống thật không có quyền kiểm thử.** Quan sát element inspector: chuỗi cần được hiển thị như text, không xuất hiện thêm `<img>`/`<script>` element phát sinh từ input.

### 11.5. Integration tests bằng MockMvc

Tạo `src/test/java/example/xss/XssEncodingApplicationTest.java`:

```java
package example.xss;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class XssEncodingApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void untrustedMarkupIsDisplayedAsHtmlText()
            throws Exception {
        String raw = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/demo").param("name", raw))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_HTML))
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html).contains("&lt;img");
                assertThat(html)
                    .doesNotContain("<img src=x onerror=");
            });
    }

    @Test
    void quotesCannotBreakQuotedAttribute() throws Exception {
        String raw = "\"><svg onload=alert(1)>";

        mvc.perform(get("/demo").param("name", raw))
            .andExpect(status().isOk())
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html)
                    .doesNotContain("value=\"\"><svg");
                assertThat(html).contains("value=\"");
            });
    }

    @Test
    void urlQueryComponentIsEncoded() throws Exception {
        mvc.perform(get("/demo").param("name", "a&b"))
            .andExpect(status().isOk())
            .andExpect(result -> {
                String html = result.getResponse()
                    .getContentAsString();
                assertThat(html)
                    .contains("/search?q=a%26b");
            });
    }

    @Test
    void jsonEndpointReturnsDataNotHtml() throws Exception {
        String value = "<img src=x onerror=alert(1)>";

        mvc.perform(get("/api/display-name")
                .param("name", value))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.name").value(value));
    }

    @Test
    void cspHeaderAddsDefenseInDepth() throws Exception {
        mvc.perform(get("/demo").param("name", "Alice"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; " +
                "object-src 'none'; base-uri 'self'; " +
                "frame-ancestors 'none'"));
    }

    @Test
    void maliciousPostIsNotAnAllowedRoute()
            throws Exception {
        mvc.perform(get("/unexpected"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Giải thích ma trận test:**

| Test | Kỳ vọng | Giới hạn suy ra |
|---|---|---|
| Raw markup đưa vào HTML text | Status 200, có `&lt;img`, không có raw `<img ...>` | Chứng minh text encoding server-side ở ví dụ |
| Input bắt đầu bằng quote rồi markup | Value attribute không bị đóng bằng raw quote | Chứng minh quoted attribute encoding ở ví dụ |
| Input có `&` trong query | `%26` trong link | Chứng minh URL query component không biến thành parameter khác |
| JSON chứa string có markup | JSON giữ đúng dữ liệu, MIME `application/json` | Không chứng minh frontend dùng JSON an toàn; frontend vẫn cần safe DOM sink |
| CSP header | Header chính sách xuất hiện | Chỉ chứng minh cấu hình header, không chứng minh mọi XSS bị chặn |
| Endpoint không khai báo | 403 | Đường đi bị deny; không liên quan đến XSS escaping |

**Lưu ý:** Test này không thay browser security testing, static analysis, dependency audit, fuzzing sanitizer, chính sách CSP toàn hệ thống hay review tất cả điểm render. Nếu người học thay đổi version OWASP Java Encoder, representation các entity có thể thay; nên tập trung vào kết quả **không tạo executable markup**. Mã đã được review tĩnh theo Spring Boot 3 / Security 6 conventions; hãy chạy build/test trong project thực tế để xác nhận đúng version.

## 12. CSP: lớp bổ sung, không thay escape

**Content Security Policy (CSP)** là response header hướng dẫn browser giới hạn nguồn script, style, object, frame và một số hành vi khác. Ví dụ:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Khi không dùng `'unsafe-inline'`, browser có thể chặn nhiều inline scripts/event handlers, làm giảm tác động của một số payload XSS. Nhưng:
- Một chính sách chỉ `script-src 'self'` vẫn cho phép script từ chính origin, có thể quá rộng nếu origin lưu file JS do người dùng upload.
- CSP sai/thiếu trên một response hoặc bị cấu hình nới lỏng có thể bị bypass theo điều kiện ứng dụng.
- CSP không sửa HTML syntax đã bị inject; attacker vẫn có thể thay đổi nội dung trang, link hoặc biểu mẫu trong phạm vi browser cho phép.
- CSP không thay sanitize khi render rich HTML, cũng không thay URL protocol validation.
- Spring Security **không tự tạo CSP phù hợp cho mọi ứng dụng**; developer phải chọn policy, triển khai và kiểm thử.

Với ứng dụng lớn, ưu tiên khảo sát chính sách bằng `Content-Security-Policy-Report-Only`, test rồi mới enforce; cân nhắc nonces/hashes, `strict-dynamic`, `object-src 'none'`, `base-uri` và `frame-ancestors` theo mức hỗ trợ. Đừng thêm `'unsafe-inline'` để bỏ qua lỗi mà không hiểu trade-off.

### 12.1. Trusted Types

Trong browser hỗ trợ **Trusted Types**, CSP directive `require-trusted-types-for 'script'` có thể yêu cầu các DOM sinks nguy hiểm nhận kiểu dữ liệu được tạo qua policy đã thiết kế. Điều này giúp hạn chế `innerHTML`/một số HTML injection sinks. Nhưng một policy permissive chỉ trả raw string thì vô hiệu lợi ích; Trusted Types không tự sanitize. Test browser support và migration trước khi bật rộng.

### 12.2. HTTP response headers còn lại

`X-Content-Type-Options: nosniff` giúp giảm MIME-sniffing ở một số ngữ cảnh. `X-Frame-Options` và `frame-ancestors` liên quan clickjacking/embedding. `Referrer-Policy` ảnh hưởng thông tin gửi qua Referer. Những headers này có ích nhưng không tự chuyển raw user text thành safe HTML text.

**Không nhầm `X-XSS-Protection` cũ với phòng vệ XSS hiện đại**: cơ chế lọc XSS trên một số browser đời cũ đã lỗi thời/không được khuyến nghị dùng làm chiến lược chính. Cốt lõi vẫn là contextual encoding, sanitization khi cần, safe DOM APIs và CSP bổ sung.

## 13. XSS và CSRF khác nhau, nhưng có thể hỗ trợ nhau

| Kiểm soát | Mục tiêu | Giới hạn liên quan XSS |
|---|---|---|
| Contextual output encoding | Không cho untrusted data thành mã có hiệu lực ở output | Cần đúng ngữ cảnh và bao phủ tất cả sinks |
| HTML sanitizer | Cho phép một tập rich HTML được phép | Policy cần được duy trì; thay đổi sau sanitize có thể gây lỗi |
| CSP | Giảm khả năng chạy script/resource không được phép | Không sửa lỗi render raw HTML |
| Cookie `HttpOnly` | Hạn chế JS đọc trực tiếp cookie | Script XSS vẫn có thể gửi requests với cookie |
| Cookie `SameSite` | Giảm một số cross-site cookie requests | Không chặn script chạy trong chính origin hợp lệ |
| CSRF token | Chống request giả mạo từ site khác khi browser tự gửi credential | XSS same-origin có thể lấy token |
| CORS | Kiểm soát browser cross-origin JS đọc response | Không ngăn XSS của chính origin |
| Input validation | Ràng buộc định dạng/dữ liệu hợp lệ | Không thay output encoding |
| Authorization | User có quyền truy cập tài nguyên cụ thể hay không | XSS có thể hành động trong phạm vi quyền của nạn nhân |
| Prepared statement | Chống SQL injection | Không encode dữ liệu cho HTML/JS |

**Hệ quả:** Nếu một trang dính XSS, attacker có thể gọi endpoint và gửi CSRF token của trang như một request hợp lệ. Bật CSRF không làm XSS biến mất. Ngược lại, escape output giúp giảm khả năng XSS nhưng không thay CSRF protection trên browser cookie-based unsafe requests.

## 14. Security review cho các vị trí đặc biệt

### 14.1. URL trong `href`/`src`

Nếu giá trị là URL tuyệt đối, **phải kiểm tra scheme và destination**. Khi chèn vào HTML source, sau validation vẫn phải attribute encode. Với links do user nhập, có thể chỉ chấp nhận `https`; với image sources, có thể chỉ cho CDN tin cậy. Chú ý URL bắt đầu bằng `//`, backslash, protocol-relative và URL decoding nhiều lần nếu hệ thống có proxy/rewriter.

### 14.2. DOM data attributes

`data-id` có thể chứa string không tin cậy được attribute encoded đúng, nhưng nếu JavaScript đọc `dataset.id` rồi đưa vào `innerHTML` sẽ xuất hiện một **sink mới**. Dữ liệu không “miễn nhiễm” vì trước đó từng ở trong attribute an toàn.

### 14.3. SVG, MathML, template và iframes

SVG/MathML có những cú pháp và attributes đặc thù, có thể liên quan scripting/foreign content. Đừng đưa raw user SVG vào DOM. `iframe.srcdoc` là HTML document context; `sandbox` có thể hạn chế một số quyền nhưng không thay content sanitization. Với email templates, PDF/HTML renderers và Markdown-to-HTML converters, áp dụng riêng policy của renderer và chống HTML injection.

### 14.4. File upload và filename

Filename có thể do client kiểm soát; nếu hiển thị trong HTML table, phải encode. Nếu cho upload HTML/SVG và serve cùng origin với cookie/session ứng dụng, người dùng khác có thể xem nội dung active từ origin tin cậy. Cần content-type, `Content-Disposition`, separate asset origin/sandbox, file scanning và download policy phù hợp. Chỉ lọc ký tự filename trong upload endpoint không bảo vệ mọi đường render tên file.

### 14.5. HTML trong API error và log viewer

Error message có thể chứa request path/parameter. Nếu một error page tự nối message vào HTML hoặc admin log viewer dùng `innerHTML` để hiển thị logs, XSS vẫn có thể xảy ra. Hãy xem error pages, audit dashboards, analytics, email preview, Markdown render và backoffice tools như các output sinks đầy đủ.

### 14.6. Localization và rich content

Text từ localization bundle thường được xem là trusted code/data do team quản lý, nhưng **giá trị tham số interpolation** (user name, comment) vẫn không tin cậy. Nếu một message có HTML được team viết sẵn, chỉ những biến chứa untrusted data bên trong mới cần context encoding phù hợp; tránh bật unescaped rendering cho cả vùng chứa tham số raw.

### 14.7. Cache và đa tenant

Một trang có data user-specific mà cache dùng chung có thể rò thông tin dù escape đúng; đây là lỗi khác với XSS. Nhưng khi cache fragments chứa HTML đã render, đảm bảo giá trị đã được encoded đúng cho đúng context và cache key đúng tenant/user. Không lấy một fragment HTML đã encode rồi nhúng vào JavaScript source chỉ vì nó “an toàn từ trước”.

## 15. Debug XSS theo nguồn, đường đi và sink

### Bước 1: xác định nguồn dữ liệu

Dữ liệu đến từ query/body/header, DB, file, third-party API, `postMessage`, localStorage hay URL fragment? Đừng dựa vào tên field “safeContent”. Một comment lưu từ admin cũng có thể chứa HTML không mong muốn.

### Bước 2: xác định parser/sink cuối

Nội dung được:
- Nối vào HTML response?
- Đưa vào `th:text` hay `th:utext`?
- Gắn vào `innerHTML`/`textContent`?
- Đưa vào `href`, `src`, `style`, event handler?
- Đặt trong inline `<script>` hay JSON?
- Render bằng Markdown/WYSIWYG plugin?

**Chọn encoder/sanitizer theo sink, không chọn theo dữ liệu nguồn.**

### Bước 3: kiểm tra tác dụng của encoding

Nếu chỉ cần text, giá trị `<tag>` phải hiển thị thành chữ và **không sinh DOM element `tag` mới**. Với attribute, quote trong input không được tạo attribute mới. Với URL, input không được đổi destination/scheme. Với JS, input không được thay đổi cấu trúc script. Với CSS, input không được thoát khỏi property/value đã được giới hạn.

### Bước 4: kiểm tra cả SSR và client updates

Có thể response ban đầu được escape đúng, nhưng JS sau khi fetch dữ liệu lại dùng `innerHTML`. Dùng browser DevTools, source review, lint rules, DOM sink scanning và security tests để tìm điểm sau cùng. Đừng kết luận “HTML server an toàn nên mọi state update an toàn”.

### Bước 5: đánh giá defense-in-depth

CSP headers có đầy đủ không; có `unsafe-inline` không; có Trusted Types phù hợp không; cookie flags và authorization được thiết kế ra sao; có nơi serve uploaded HTML/SVG cùng origin không. Các biện pháp này giảm rủi ro nhưng không thay sửa sink.

## 16. Lỗi phổ biến và cách sửa

| Anti-pattern | Lỗi thực chất | Thay thế |
|---|---|---|
| `"<p>" + input + "</p>"` | Raw input thành HTML markup | `Encode.forHtmlContent` hoặc template escaped text |
| `<input value=...>` không quote | Dễ tạo thêm attributes | Giữ quoted value + attribute encode |
| `th:utext` với user comment | Parse raw HTML | `th:text` hoặc sanitized rich HTML |
| `innerHTML = input` cho plain text | DOM XSS | `textContent = input` |
| `eval(JSON)` | Data bị chạy như JavaScript | `response.json()` / `JSON.parse` |
| Chỉ `replace("<", "&lt;")` | Không hiểu parser/context | OWASP Java Encoder / autoescape |
| URL component encode toàn bộ URL không validate | Vẫn có URL scheme/destination nguy hiểm | Parse/allowlist scheme/host, encode component |
| HTML escape dữ liệu bên trong inline JS | Sai parser context | Tránh inline JS hoặc JavaScript block encoder phù hợp |
| HTML escape data rồi đưa tiếp `textContent` | Hiển thị double-escaped | Dùng raw data cho safe DOM text sink |
| Sanitizer bằng regex | Không xử lý malformed HTML/parsers | OWASP Java HTML Sanitizer hoặc DOMPurify |
| CSP là phòng vệ duy nhất | Có thể bị bypass, trang vẫn bị sửa DOM | Encode/sanitize + CSP |
| `HttpOnly` hoặc CSRF token thay XSS defense | Script cùng origin vẫn thao tác được | Sửa output sink |
| Mở rộng `unsafe-inline` để app chạy | Nới CSP | Refactor JS tĩnh/nonces/hashes |
| Trust toàn bộ data từ API authenticated | API cũng có thể chứa stored XSS | Encode ở frontend render |
| Kiểm tra “input không chứa script” | Bỏ qua event handlers, SVG, attributes | Validate hợp đồng + context encoding |
| Trả JSON qua `text/html` | Browser có thể diễn giải sai ngữ cảnh | Serializer chuẩn + MIME đúng |
| Upload HTML/SVG rồi serve same-origin | Active content chạy ở trusted origin | File validation, isolated origin/download policy |
| Một helper `escapeHtml` dùng cho JS/CSS/URL | Sai parser context | API chuyên biệt cho từng sink |
| Chỉ test chuỗi hiện trên trang | Bỏ sót DOM element mới | Kiểm tra DOM và negative browser tests |

## 17. Checklist cho code review và CI

### HTML/template

- [ ] Mỗi lần hiển thị user-generated text có escaped output hoặc safe DOM API.
- [ ] Không có raw `th:utext`/`dangerouslySetInnerHTML`/`v-html` với untrusted content chưa sanitize.
- [ ] Ordinary text attribute values luôn quoted và encode theo attribute context.
- [ ] URL attributes có validation scheme/destination rồi mới encode cho HTML.
- [ ] Không dùng untrusted input làm element name, attribute name, event handler, script source.
- [ ] HTML sanitizer chỉ dùng khi cần rich text, có policy explicit và thư viện được duy trì.
- [ ] Input validation dùng cho business rules, không bị nhầm là XSS encoding.

### JavaScript/DOM

- [ ] Không dùng `innerHTML`/`outerHTML`/`insertAdjacentHTML` với raw user strings.
- [ ] Ưu tiên `textContent`, `createTextNode` và safe property assignments cho data.
- [ ] Không dùng `eval`/`new Function` để parse JSON hay input.
- [ ] Dữ liệu nhúng trong `<script>` được loại bỏ hoặc encoded đúng JavaScript block + enclosing HTML context.
- [ ] CSS dynamic styles chỉ dùng fixed property + allowlisted value.
- [ ] SPA/SSR/hydration được xem như nhiều boundaries, không chỉ một lần escape.
- [ ] Trusted Types policy không trả raw string bừa bãi khi được bật.

### Defense-in-depth

- [ ] CSP được cấu hình cho ứng dụng thực, có kiểm thử/reporting, không phụ thuộc vào `unsafe-inline`.
- [ ] Cookie HttpOnly, Secure, SameSite phù hợp, hiểu chúng không chặn XSS same-origin.
- [ ] CSRF protection vẫn áp dụng cho browser cookie-based unsafe requests.
- [ ] Authorization trên role/tenant/owner không phụ thuộc vào việc HTML đã escape.
- [ ] Uploaded active content không chạy trong origin chính của app.
- [ ] JSON trả đúng Content-Type và frontend không parse JSON data thành code.
- [ ] Logs, error pages, admin dashboards và rich text views đều được review.

### Testing

- [ ] MockMvc test raw tag như `<img>` không thành executable markup.
- [ ] Test quotes không thoát khỏi attribute value.
- [ ] Test `&` và `#` trong URL query không đổi cấu trúc URL.
- [ ] Test JSON serializer trả đúng data/MIME, không dùng string concatenation.
- [ ] Test DOM browser với query/hash/`postMessage`, không có injected elements.
- [ ] Test sanitizer với malformed HTML, SVG/MathML, URL protocols và HTML entities.
- [ ] Test CSP headers trên các response HTML, kèm chính sách production qua browser.
- [ ] Test cả chuỗi bình thường và Unicode/emoji để phát hiện double encoding.
- [ ] Test sau upgrade template/framework/encoder/sanitizer để tránh thay đổi semantics.

## 18. Bài tập tự kiểm tra

**Câu 1.** Một controller yêu cầu login và dùng `hasAuthority('DOC_READ')`, nhưng nối `comment.body` vào HTML string không escape. Spring Security đã chặn XSS chưa?

**Đáp án:** Chưa. Login/authorization kiểm soát caller, còn dữ liệu được render thành HTML do template/controller quyết định. Cần escape theo HTML text context hoặc sanitize nếu cần rich HTML.

**Câu 2.** Input `<b>hello</b>` được đưa vào `th:text` và `th:utext`. Khác nhau?

**Đáp án:** `th:text` escape để browser hiển thị ký tự `<b>hello</b>` như văn bản; `th:utext` đưa markup cho browser parse. Dùng `th:utext` với user HTML chỉ sau một sanitizer phù hợp.

**Câu 3.** `element.textContent = rawValue` có cần gọi `Encode.forHtmlContent` trước không?

**Đáp án:** Không. Với HTML text element thông thường, `textContent` tạo text node trực tiếp. Nếu encode trước, UI có thể hiển thị ký tự `&lt;` thay vì `<`.

**Câu 4.** Đã dùng `Encode.forHtmlAttribute` cho `href` chứa `javascript:...`. Link tự động an toàn?

**Đáp án:** Không. Attribute encoding bảo vệ HTML cú pháp, không cấm scheme nguy hiểm. Phải validate scheme/destination trước, rồi attribute encode tại render.

**Câu 5.** Đã JSON serialize biến tên user, sau đó nối JSON string trực tiếp vào một inline `<script>`. Đúng chưa?

**Đáp án:** Chưa chắc. JSON serializer tạo JSON, còn browser sẽ parse **HTML script context**. Phải xử lý cả context hoặc chuyển sang endpoint `application/json` riêng để JS fetch.

**Câu 6.** Vì sao `SameSite` hoặc `HttpOnly` không thay XSS protection?

**Đáp án:** XSS chạy trong chính origin của app có thể thao tác DOM, đọc dữ liệu UI và gửi requests mà browser gắn cookie. Cookie flags hạn chế một số hậu quả, không chặn script injection.

**Câu 7.** Sản phẩm cần cho người dùng nhập chữ đậm và link. Escape mọi HTML sẽ mất format. Nên làm gì?

**Đáp án:** Sử dụng sanitizer có allowlist tags/attributes/protocols như OWASP Java HTML Sanitizer hoặc DOMPurify rồi render rich HTML tại điểm được review; không dùng regex xóa tag nguy hiểm.

**Câu 8.** CSP header có `script-src 'self'` và không có `unsafe-inline`. Có thể không encode output nữa không?

**Đáp án:** Không. CSP là defense-in-depth; ứng dụng vẫn phải encode/sanitize tại output. Policy còn phụ thuộc toàn origin, external scripts, browser support và cấu hình riêng.

**Câu 9.** Cùng raw string được đưa vào HTML `<p>` và URL query. Có dùng một hàm escape không?

**Đáp án:** Không. `<p>` dùng HTML text encoding, query dùng percent encoding cho **component** rồi HTML attribute encoding nếu đặt trong `href`.

**Câu 10.** Database lưu comment sau khi đã chạy HTML encoder rồi frontend dùng `textContent`. Có đúng không?

**Đáp án:** Dữ liệu bị encode quá sớm cho một context, sau đó đưa vào một safe DOM sink có thể gây double encoding. Ưu tiên raw domain data với validation nghiệp vụ, encode tại output boundary tương ứng.

## 19. Tham khảo chính thức và tiêu chuẩn thực hành

- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): các context HTML/attribute/JavaScript/CSS/URL, HTML sanitization, sink an toàn và phòng vệ bổ sung.
- [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html): nguồn/sink DOM, parser contexts và những API cần tránh.
- [OWASP Java Encoder — Contextual Output Encoding](https://owasp.org/projects/java-encoder): `forHtmlContent`, `forHtmlAttribute`, `forUriComponent`, `forJavaScriptBlock` và chú ý context.
- [OWASP Java HTML Sanitizer](https://owasp.org/projects/java-html-sanitizer): PolicyFactory, Sanitizers và chính sách allowlist.
- [Thymeleaf 3.1 — Tutorial: Escaped vs Unescaped Text](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html): `th:text`, `th:utext`, `[[...]]` và `[(...)]`.
- [Spring Security — HTTP Security Response Headers / CSP](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): CSP và ranh giới của HTTP response headers.
- [MDN — Element.textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent): DOM text sink và khác biệt với `innerHTML`.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): directives, browser behavior và nguồn script.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): cách triển khai CSP như defense-in-depth.

**Ghi nhớ:** Với dữ liệu không đáng tin, hỏi **“Giá trị này đi vào parser nào?”** trước khi chọn cách bảo vệ. HTML text → HTML text encoding hoặc safe DOM text API. HTML attribute → quote + attribute encoder. URL → build bằng trusted base, encode từng component, validate scheme/host rồi attribute encode nếu render trong HTML. JavaScript/CSS → tránh chèn raw, dùng API được kiểm soát. Rich HTML → sanitizer theo allowlist. Spring Security và CSP hỗ trợ giảm thiểu, nhưng **không thay thế xử lý đầu ra đúng ngữ cảnh**.
