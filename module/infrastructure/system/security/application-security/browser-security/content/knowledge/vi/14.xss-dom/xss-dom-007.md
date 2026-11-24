# JavaScript context: xử lý dữ liệu an toàn trong mã JavaScript

## 1. JavaScript context là gì?

**JavaScript context** là vị trí mà dữ liệu được đưa vào và được parser JavaScript diễn giải như một phần của mã. Cùng một chuỗi có thể an toàn khi hiển thị như văn bản nhưng trở thành mã hoặc làm thay đổi cấu trúc chương trình khi được chèn vào một vị trí JavaScript khác.

Ví dụ ứng dụng muốn chào người dùng bằng tên lấy từ request:

~~~js
const name = "An";
document.querySelector("#welcome").textContent = "Xin chào, " + name;
~~~

Cách này đưa dữ liệu vào DOM dưới dạng văn bản. Nhưng nếu server ghép trực tiếp dữ liệu vào mã JavaScript được sinh ra:

~~~html
<script>
  const name = "USER_INPUT";
  document.querySelector("#welcome").textContent = name;
</script>
~~~

thì USER_INPUT đang nằm trong **JavaScript string literal**. Nếu dữ liệu có dấu nháy, dấu gạch chéo ngược hoặc chuỗi làm thoát khỏi ngữ cảnh string, parser có thể hiểu phần còn lại là cú pháp JavaScript mới. Đây là một dạng lỗi **cross-site scripting (XSS)**.

Bảo vệ JavaScript context đòi hỏi hiểu chính xác dữ liệu đang được đưa vào vị trí nào: nội dung script, chuỗi có nháy, template literal, thuộc tính event handler, URL có scheme thực thi, hay một DOM sink. **Không có một hàm escape chung an toàn cho mọi context.**

Bài học thuộc chương **XSS và DOM** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung giải thích cách HTML parser và JavaScript parser tương tác, vì sao encode sai context vẫn nguy hiểm, cách truyền dữ liệu mà không sinh mã động, và vai trò cũng như giới hạn của CSP, Trusted Types.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt HTML text context, HTML attribute context, JavaScript string context và JavaScript code context.
2. Giải thích vì sao dữ liệu được đặt trong phần tử SCRIPT chịu cả HTML parsing và JavaScript parsing.
3. Nhận diện rủi ro khi chèn dữ liệu vào string literal, template literal, event handler và JavaScript URL.
4. Hiểu vì sao JSON.stringify hữu ích nhưng chưa tự động an toàn khi nhúng vào HTML script.
5. Chọn phương án truyền dữ liệu an toàn: DOM text APIs, external JavaScript, JSON response hoặc serialization có escaping đúng.
6. Nhận diện các sink nguy hiểm như innerHTML, eval, Function, setTimeout(string) và document.write.
7. Hiểu CSP và Trusted Types hỗ trợ giảm rủi ro như thế nào và không giải quyết điều gì.
8. Kiểm chứng source-to-sink bằng DevTools với dữ liệu thử nghiệm vô hại.

## 2. Một dữ liệu có thể đi qua nhiều parser

Khi server trả HTML có script inline, trình duyệt xử lý nội dung theo nhiều lớp:

1. HTTP response được nhận và giải mã.
2. HTML parser nhận diện thẻ script và nội dung script.
3. HTML parser có quy tắc đặc biệt cho nội dung script; dấu đóng </script> có thể kết thúc phần tử script.
4. Phần nội dung script được JavaScript engine parse và thực thi.
5. JavaScript có thể tiếp tục đưa dữ liệu vào DOM, URL, CSS, request hoặc một API thực thi khác.

~~~mermaid
flowchart TD
    A["Input không tin cậy"] --> B["Server template / client code"]
    B --> C["HTML parser"]
    C --> D{"Vị trí trong tài liệu?"}
    D -->| "Text node" | E["HTML text parsing"]
    D -->| "Thuộc tính" | F["HTML attribute parsing"]
    D -->| "Nội dung script" | G["JavaScript parser"]
    G --> H{"Vị trí JS"}
    H --> I["String / template literal"]
    H --> J["Code / expression"]
    H --> K["Event handler / JS URL"]
    I --> L["Runtime value"]
    J --> M["Code execution"]
    K --> M
~~~

Một giá trị có thể đi qua **HTML parser trước**, rồi mới tới JavaScript parser. Vì vậy chỉ escape theo quy tắc JavaScript mà quên HTML parser có thể vẫn tạo XSS.

Ví dụ, phần tử SCRIPT là một phần tử HTML. Trình duyệt nhận diện thẻ script trước khi JavaScript engine xử lý chuỗi bên trong. Một chuỗi trông giống </script> có thể đóng phần tử script ngay cả khi người viết template nghĩ rằng nó đang nằm trong dấu nháy JavaScript.

## 3. Phân biệt các context đầu ra

| Context | Ví dụ | Parser/diễn giải | Cách ưu tiên |
| --- | --- | --- | --- |
| HTML text | `<p>USER_INPUT</p>` | HTML parser tạo text/markup | Template auto-escaping hoặc text API. |
| HTML attribute thường | `<input value="USER_INPUT">` | HTML attribute parser | Attribute encoding đúng quote context; DOM property/API phù hợp. |
| JavaScript string trong script | `const x = "USER_INPUT";` | HTML script handling rồi JavaScript parser | Tránh chèn trực tiếp; truyền JSON an toàn hoặc lấy dữ liệu qua API. |
| JavaScript template literal | Template source chứa dữ liệu động | JavaScript parser với interpolation | Không chèn dữ liệu trực tiếp vào source; dùng biến runtime. |
| JavaScript expression/code | `doSomething(USER_INPUT)` | JavaScript parser coi input là cú pháp | Không biến input thành code; dùng data structure và allowlist. |
| Event handler attribute | `<button onclick="doThing('USER_INPUT')">` | HTML attribute + JavaScript handler | Tránh inline handler; dùng addEventListener. |
| JavaScript URL | `href="javascript:USER_INPUT"` | URL scheme và JavaScript execution | Không dùng; chỉ cho phép URL scheme an toàn theo allowlist. |
| DOM HTML sink | `element.innerHTML = value` | HTML fragment parser | Dùng textContent; nếu bắt buộc HTML, sanitize. |

Quy tắc cốt lõi: **encoding phải phù hợp với context cuối cùng**. HTML encoding không thay JavaScript string encoding; JavaScript string encoding không thay URL validation; URL encoding không thay HTML attribute encoding.

## 4. JavaScript string context: dấu nháy không phải biên an toàn

Giả sử server tạo:

~~~html
<script>
  const displayName = "An";
</script>
~~~

Nếu template nối chuỗi từ input, dấu nháy trong dữ liệu có thể làm hỏng cú pháp hoặc thoát khỏi string. Các ký tự có ý nghĩa cần quan tâm gồm:

- Dấu nháy đơn và kép.
- Dấu gạch chéo ngược.
- Dấu xuống dòng và các ký tự điều khiển.
- Dấu phân cách cú pháp, dấu ngoặc và toán tử.
- Chuỗi có thể làm HTML parser kết thúc thẻ script như </script>.

Không nên tự tạo một hàm chỉ thay dấu nháy kép:

~~~js
function escapeJs(value) {
  return value.replaceAll('"', '\\"');
}
~~~

Hàm này bỏ sót nhiều trường hợp và không xử lý HTML parser. Escape dấu nháy kép đơn lẻ không đủ cho mọi JavaScript context.

### 4.1. Ví dụ lỗi khi ghép dữ liệu vào string

~~~js
// Server-side template minh họa anti-pattern:
const html = "<script>const userName = '" + userInput + "';</script>";
~~~

Dữ liệu có thể chứa dấu nháy, backslash, newline hoặc chuỗi kết thúc script. Tùy đầu vào và cách template serialize, mã được sinh ra có thể khác với ý định.

**Cách tốt nhất:** không chèn dữ liệu không tin cậy vào JavaScript source. Hãy truyền dữ liệu như dữ liệu, rồi để JavaScript đọc ở runtime.

## 5. Truyền dữ liệu an toàn thay vì sinh JavaScript động

### 5.1. Dùng DOM text API khi chỉ cần hiển thị chữ

~~~html
<p id="welcome"></p>
<script src="/assets/welcome.js" defer></script>
~~~

External script:

~~~js
const params = new URLSearchParams(location.search);
const name = params.get("name") ?? "";

document.querySelector("#welcome").textContent =
  "Xin chào, " + name;
~~~

Dữ liệu từ query được giữ như chuỗi và gán qua textContent, không được parse thành HTML hay JavaScript source.

### 5.2. Lấy dữ liệu từ JSON endpoint

Một ứng dụng có thể tải dữ liệu qua API:

~~~js
const response = await fetch("/api/profile", {
  credentials: "same-origin",
  headers: { "Accept": "application/json" }
});

if (!response.ok) {
  throw new Error("Không tải được hồ sơ");
}

const profile = await response.json();
document.querySelector("#welcome").textContent =
  "Xin chào, " + profile.displayName;
~~~

JSON response được parse thành object dữ liệu. Tuy nhiên, dữ liệu JSON vẫn không tự an toàn cho mọi sink: nếu sau đó gán profile.displayName vào innerHTML hoặc dùng nó làm JavaScript code, rủi ro vẫn xuất hiện.

### 5.3. Dùng thuộc tính data-* cho dữ liệu nhỏ, không nhạy cảm

~~~html
<div id="app" data-display-name="An"></div>
<script src="/assets/app.js" defer></script>
~~~

External script:

~~~js
const root = document.querySelector("#app");
const displayName = root.dataset.displayName ?? "";

document.querySelector("#welcome").textContent = displayName;
~~~

Nếu server render HTML attribute, template engine phải encode attribute context đúng cách. data-* không tự làm đầu vào an toàn; nó chỉ là cách lưu dữ liệu trong DOM.

Không đưa token bí mật hoặc dữ liệu nhạy cảm vào data attribute chỉ vì nó không xuất hiện trong URL.

## 6. Nhúng JSON trong HTML: an toàn hơn nhưng cần đúng serialization

Một pattern được dùng là nhúng dữ liệu JSON vào phần tử script có type không thực thi:

~~~html
<script id="initial-data" type="application/json">
{"displayName":"An","theme":"dark"}
</script>
~~~

JavaScript đọc nội dung:

~~~js
const node = document.querySelector("#initial-data");
const initialData = JSON.parse(node.textContent);

document.querySelector("#welcome").textContent =
  initialData.displayName;
~~~

type="application/json" làm phần tử script trở thành **data block**, không phải JavaScript được thực thi như script thông thường. Nhưng HTML parser vẫn xử lý nội dung phần tử script theo quy tắc script data; chuỗi </script> vẫn có thể kết thúc phần tử. Do đó **không được chỉ gọi JSON.stringify rồi nối kết quả vào HTML mà không xử lý ký tự có thể kết thúc script**.

### 6.1. JSON.stringify không phải HTML script escaping

JSON.stringify serialize object thành JSON hợp lệ. Nhưng nếu chuỗi bên trong chứa ký tự <, kết quả có thể chứa </script> nguyên dạng. HTML parser không hiểu rằng dấu đóng này chỉ nằm trong một JSON string; nó vẫn có thể đóng phần tử script.

Ví dụ dữ liệu:

~~~js
const data = {
  displayName: "</script><script>console.log('demo')</script>"
};

console.log(JSON.stringify(data));
~~~

Nếu serialize rồi nhúng trực tiếp vào HTML script data block, parser HTML có thể nhận diện dấu đóng script trước khi JSON.parse được gọi.

### 6.2. Nếu phải nhúng JSON, escape ký tự có thể kết thúc script

Một cách thường dùng là serialize JSON, sau đó thay ký tự < bằng escape Unicode \u003c trước khi đưa vào HTML script context:

~~~js
function serializeJsonForHtmlScript(value) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c");
}

const json = serializeJsonForHtmlScript({
  displayName: "</script><script>demo()</script>"
});
~~~

Khi nhúng kết quả vào script data block:

~~~html
<script id="initial-data" type="application/json">
{"displayName":"\u003c/script>\u003cscript>demo()\u003c/script>"}
</script>
~~~

HTML parser không còn thấy ký tự < mở đầu chuỗi </script>; khi JavaScript gọi JSON.parse, escape Unicode được giải mã thành ký tự dữ liệu ban đầu.

Trong triển khai thực tế, ưu tiên helper của template framework đã được thiết kế để **serialize JSON an toàn trong HTML context**. Quy tắc hoàn chỉnh còn cần xem xét các ký tự đặc biệt, charset, CSP và cách framework tạo output. Không tự giả định một thay thế chuỗi ngắn đã đáp ứng mọi context.

### 6.3. JSON data block không phải vùng bí mật

Nội dung trong script type application/json vẫn nằm trong DOM và có thể được script cùng trang đọc. Không nhúng password, session secret, access token hoặc dữ liệu mà user hiện tại không được phép xem.

## 7. Template literal và interpolation

Template literal dùng dấu backtick và hỗ trợ interpolation qua một biểu thức nằm giữa dấu dollar và ngoặc nhọn. Nếu dữ liệu được ghép vào **source code** của template literal, dấu backtick hoặc interpolation marker có thể làm thay đổi cấu trúc cú pháp.

Anti-pattern:

~~~js
// Không nối input vào source template literal:
const source = "const message = " + String.fromCharCode(96) + userInput + String.fromCharCode(96) + ";";
~~~

Cách đúng là tạo template literal trong code đã cố định, rồi truyền dữ liệu vào biến runtime:

~~~js
const userInput = getUntrustedInput();
const message = "Xin chào, " + userInput;

document.querySelector("#welcome").textContent = message;
~~~

Không nhầm interpolation trong template literal với template engine phía server. Server-side template có thể được xử lý trước khi JavaScript tới browser; cần hiểu từng lớp template và context đầu ra.

## 8. JavaScript expression và code context

Dữ liệu được đặt vào vị trí expression có thể bị parser coi là cú pháp thay vì giá trị.

Ví dụ thiết kế sai:

~~~js
// Anti-pattern: input trở thành một phần của biểu thức được sinh ra.
const code = "calculateTotal(" + userInput + ")";
eval(code);
~~~

Nếu userInput là chuỗi dữ liệu mà ứng dụng muốn tính toán, hãy parse thành kiểu dữ liệu và dùng hàm cố định:

~~~js
const amount = Number(userInput);

if (!Number.isFinite(amount) || amount < 0 || amount > 100000) {
  throw new Error("Giá trị không hợp lệ");
}

const total = calculateTotal(amount);
~~~

Nếu cần chọn hành động, dùng allowlist:

~~~js
const actions = {
  preview: () => showPreview(),
  refresh: () => refreshData()
};

const requestedAction = getUntrustedInput();
const action = actions[requestedAction];

if (action) {
  action();
}
~~~

Không cho phép input tự định nghĩa tên hàm, câu lệnh hoặc biểu thức sẽ được eval thực thi.

## 9. Event handler attribute: HTML context lồng JavaScript context

Ví dụ:

~~~html
<button onclick="showMessage('hello')">Bấm</button>
~~~

Thuộc tính onclick chứa mã JavaScript. Khi chèn input vào đó, dữ liệu đi qua ít nhất hai lớp: HTML attribute parsing và JavaScript event-handler parsing.

Anti-pattern:

~~~html
<button onclick="showMessage('USER_INPUT')">Bấm</button>
~~~

Chỉ HTML-encode hoặc chỉ JavaScript-escape có thể không xử lý đúng cả hai lớp. Các dấu nháy, entity decoding, whitespace và quy tắc handler có thể khiến đầu vào thay đổi cú pháp.

**Ưu tiên bỏ inline event handler:**

~~~html
<button id="greet">Chào</button>
~~~

~~~js
const name = getUntrustedInput();

document.querySelector("#greet").addEventListener("click", () => {
  document.querySelector("#welcome").textContent =
    "Xin chào, " + name;
});
~~~

Mã handler được đặt trong external script cố định; dữ liệu chỉ được dùng như giá trị runtime. Cách này cũng dễ áp dụng CSP nghiêm ngặt hơn vì không cần inline event handler.

## 10. JavaScript URL và navigation context

Một URL có scheme javascript: có thể thực thi JavaScript khi được dùng trong một số ngữ cảnh điều hướng:

~~~html
<a href="javascript:...">Mở</a>
~~~

Không dùng dữ liệu không tin cậy để xây JavaScript URL. Cũng không chỉ kiểm tra chuỗi bắt đầu bằng http hoặc dùng includes để xác định URL an toàn.

Nếu cần điều hướng, parse URL và allowlist scheme/origin:

~~~js
function safeInternalPath(value) {
  const url = new URL(value, location.origin);

  if (url.origin !== location.origin) {
    throw new Error("Chỉ cho phép điều hướng nội bộ");
  }

  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("Scheme không được phép");
  }

  return url.pathname + url.search + url.hash;
}
~~~

Ví dụ trên minh họa kiểm tra URL cùng origin; ứng dụng production cần quyết định scheme nào được phép, cách xử lý userinfo, path đặc biệt, redirect tiếp theo và môi trường HTTP/HTTPS. Không dùng javascript: hoặc data: làm đích điều hướng từ input không tin cậy.

## 11. Những JavaScript sinks cần nhận diện

Một **sink** là API hoặc vị trí mà dữ liệu được diễn giải theo một ngữ cảnh có khả năng tạo markup, code hoặc hành vi.

| Sink/API | Diễn giải | Khuyến nghị |
| --- | --- | --- |
| textContent | Text node | Ưu tiên để hiển thị văn bản. |
| innerText | Text theo cách hiển thị/layout | Có thể dùng khi cần semantics hiển thị; không phải HTML parser. |
| innerHTML | Parse HTML fragment | Tránh với dữ liệu không tin cậy; nếu cần HTML, sanitize. |
| outerHTML | Parse và thay thế markup | Tránh input không tin cậy. |
| insertAdjacentHTML | Parse HTML fragment | Sanitize đúng ngữ cảnh hoặc tránh. |
| document.write | Ghi/parse HTML vào document | Tránh trong ứng dụng hiện đại, đặc biệt với input. |
| eval | Parse và thực thi JavaScript source | Không dùng với input; thường không cần. |
| Function | Biên dịch function từ chuỗi | Tránh sinh code từ dữ liệu. |
| setTimeout(string) | Có thể đánh giá chuỗi như code | Dùng callback function. |
| setInterval(string) | Có thể đánh giá chuỗi như code | Dùng callback function. |
| setAttribute("onclick", ...) | Có thể tạo event-handler code | Dùng addEventListener. |
| location = value | Điều hướng tới URL | Parse và kiểm tra scheme/origin theo allowlist. |

### 11.1. Dùng callback thay chuỗi cho timer

Không dùng:

~~~js
setTimeout("refreshDashboard()", 1000);
~~~

Dùng:

~~~js
setTimeout(() => refreshDashboard(), 1000);
~~~

Callback là function đã được parse trong source code; không cần biến chuỗi thành JavaScript source ở runtime.

### 11.2. setAttribute không làm mọi attribute an toàn

Gán:

~~~js
element.setAttribute("title", userInput);
~~~

khác với:

~~~js
element.setAttribute("onclick", userInput);
~~~

Thuộc tính title được xử lý như giá trị attribute; onclick có semantics là JavaScript event handler. Tên attribute và sink quyết định context. Không dùng cùng một quy tắc cho mọi attribute.

## 12. Encoding theo context: vì sao không có “escape tất cả”

| Kỹ thuật | Dùng cho | Không giải quyết |
| --- | --- | --- |
| HTML text encoding | Dữ liệu trong text node HTML | JavaScript source, URL scheme, SQL. |
| HTML attribute encoding | Giá trị trong HTML attribute có quote | Event handler JavaScript, URL đích không an toàn. |
| JavaScript string serialization/escaping | Giá trị string trong JS context theo serializer phù hợp | HTML parser kết thúc script, DOM sink khác. |
| URL component encoding | Một thành phần path/query | Cho phép scheme/origin, XSS ở HTML/JS. |
| JSON serialization | Chuyển object thành JSON data | Tự động an toàn khi nhúng vào HTML script. |
| HTML sanitizer | Cho phép một tập HTML markup | JavaScript code context, URL ngoài allowlist, mọi DOM sink. |

Ví dụ cùng chuỗi dữ liệu:

~~~text
Alice "Admin" & <Manager>
~~~

- Nếu hiển thị như text HTML, cần HTML text encoding hoặc textContent.
- Nếu đưa vào một HTML attribute, cần attribute encoding và quote đúng.
- Nếu đưa vào JavaScript string, cần serializer JavaScript phù hợp và xét HTML script parser.
- Nếu dùng làm URL, phải parse và kiểm tra scheme/origin/path.
- Nếu dùng làm SQL value, phải bind parameter.

Không thể dùng một hàm escape rồi áp dụng ở mọi nơi.

## 13. CSP: giảm khả năng thực thi mã được chèn

Content Security Policy (CSP) cho phép server định nghĩa nguồn script và một số hành vi thực thi được phép. Một chính sách ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'none'
~~~

Ý nghĩa khái quát:

- default-src 'self' đặt mặc định nguồn cho nhiều loại tài nguyên.
- script-src giới hạn nguồn script và script inline được cấp nonce.
- object-src 'none' vô hiệu hóa plugin object/embed.
- base-uri 'none' ngăn thay đổi base URL qua thẻ base.

Nonce phải ngẫu nhiên, khó đoán và mới cho mỗi HTML response; chỉ gắn vào script do ứng dụng tin cậy tạo. Không dùng nonce cố định hoặc đưa nonce vào dữ liệu không tin cậy.

### 13.1. CSP không thay thế context-safe output

CSP có thể chặn một số cách thực thi script, nhưng không biến việc chèn input vào JavaScript source thành thiết kế an toàn. Có thể còn các đường thực thi khác, policy có thể cấu hình sai hoặc browser hỗ trợ khác nhau. Phải sửa source-to-sink và tránh sinh code từ input.

### 13.2. Tránh phụ thuộc vào unsafe-inline và unsafe-eval

Các directive unsafe-inline làm nới lỏng kiểm soát inline script/handler; unsafe-eval cho phép các API đánh giá chuỗi thành code trong những điều kiện CSP tương ứng.

Không thêm chúng chỉ để “sửa lỗi CSP” khi ứng dụng có thể chuyển sang external script, nonce/hash và callback function.

## 14. Trusted Types: kiểm soát một số DOM injection sinks

Trusted Types là cơ chế giúp kiểm soát việc truyền chuỗi vào một số DOM XSS sinks trong các browser hỗ trợ. Khi bật enforcement, ứng dụng có thể yêu cầu dữ liệu đưa vào các sink như innerHTML phải được tạo qua Trusted Types policy được cấp phép.

Header minh họa:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types appHtml
~~~

Ứng dụng cần định nghĩa policy có sanitize thật:

~~~js
const policy = trustedTypes.createPolicy("appHtml", {
  createHTML(input) {
    return DOMPurify.sanitize(input);
  }
});
~~~

Sau đó:

~~~js
target.innerHTML = policy.createHTML(untrustedHtml);
~~~

Đây là ví dụ khái niệm; sanitizer phải được cấu hình phù hợp với yêu cầu sản phẩm và phiên bản được bảo trì. Không tạo policy trả nguyên input như:

~~~js
// Không an toàn: policy chỉ đóng dấu chuỗi mà không sanitize.
createHTML(input) {
  return input;
}
~~~

Trusted Types **không**:

- Tự động sanitize mọi HTML.
- Bảo vệ mọi JavaScript source context hoặc URL scheme.
- Thay thế CSP, output encoding hoặc kiểm tra redirect.
- Ngăn XSS trong browser không hỗ trợ enforcement.
- Chứng minh một giá trị HTML là an toàn nếu policy của ứng dụng viết sai.

## 15. JSON và JavaScript context trong server template

Khi server render dữ liệu vào HTML, hãy ưu tiên template engine có auto-escaping đúng và helper chuyên dụng cho JavaScript/JSON context. Không tự dùng một helper HTML escape rồi đặt output vào script.

### 15.1. Phân biệt JSON response với JSON nhúng trong HTML

JSON response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff

{"displayName":"An"}
~~~

Browser/client đọc response và parse JSON bằng API:

~~~js
const data = await response.json();
~~~

Đây thường là cách tách biệt dữ liệu và code rõ ràng.

Ngược lại, JSON nhúng vào HTML:

~~~html
<script type="application/json" id="data">...</script>
~~~

vẫn đi qua HTML parser. Cần serializer dành cho HTML script context, không chỉ JSON.stringify.

### 15.2. Không nhầm application/json với script executable

script type application/json không được thực thi như JavaScript thông thường. Nhưng nó vẫn là một phần tử script trong HTML parsing model, do đó phải xử lý dấu đóng script đúng cách. Nếu dữ liệu có thể chứa </script>, không escape phù hợp có thể làm thay đổi DOM và tạo thêm markup.

## 16. DOM-based XSS: source, transformation và sink

DOM XSS thường được phân tích theo ba thành phần:

- **Source:** dữ liệu có thể bị người dùng hoặc bên ngoài kiểm soát.
- **Transformation:** thao tác decode, nối chuỗi, chuẩn hóa hoặc chuyển kiểu.
- **Sink:** API/thuộc tính diễn giải dữ liệu thành HTML, JavaScript, URL hoặc hành vi.

Các source phổ biến:

- location.search, location.hash, location.href.
- document.referrer.
- postMessage event data.
- Dữ liệu từ API, localStorage, sessionStorage hoặc IndexedDB.
- Dữ liệu từ DOM hoặc nội dung người dùng đã lưu.

Một flow nguy hiểm:

~~~js
const message = new URLSearchParams(location.search).get("message") ?? "";
target.innerHTML = message;
~~~

Một flow ưu tiên text:

~~~js
const message = new URLSearchParams(location.search).get("message") ?? "";
target.textContent = message;
~~~

Không phải mọi source đều luôn độc hại; điều quan trọng là **đầu vào có thể bị kiểm soát** và sink diễn giải nó như thế nào. Dữ liệu từ API nội bộ cũng cần xem xét nếu có thể chứa nội dung người dùng.

## 17. Thực hành A — Quan sát JavaScript context trong script data

Thực hiện trên file local hoặc staging do bạn kiểm soát. Tạo một trang thử với dữ liệu JSON cố định, không chạy payload thực thi:

~~~html
<script type="application/json" id="test-data">
{"message":"hello"}
</script>
<pre id="output"></pre>
<script>
  const data = JSON.parse(
    document.querySelector("#test-data").textContent
  );
  document.querySelector("#output").textContent = data.message;
</script>
~~~

Thử thay message bằng một chuỗi dữ liệu hiển thị có chứa dấu nháy, backslash, Unicode và ký tự <, >. Quan sát DOM và kết quả JSON parse.

**Mục tiêu:** thấy JSON data block là dữ liệu được parse, nhưng vẫn nằm trong HTML document; không nhúng bí mật hoặc dữ liệu chưa serialize an toàn.

## 18. Thực hành B — So sánh textContent và innerHTML bằng markup vô hại

Tạo trang test có:

~~~html
<div id="text-output"></div>
<div id="html-output"></div>
~~~

Trong Console:

~~~js
const harmless = "<strong>Demo text</strong>";

document.querySelector("#text-output").textContent = harmless;
document.querySelector("#html-output").innerHTML = harmless;
~~~

Quan sát tab Elements:

- Vùng text-output chứa chuỗi ký tự.
- Vùng html-output chứa một phần tử strong thật.

Không cần dùng payload script. Bài thử chứng minh hai sink có semantics khác nhau; dữ liệu người dùng chỉ nên đi vào HTML parser khi ứng dụng thực sự cần markup và có sanitizer đúng.

## 19. Thực hành C — Kiểm tra inline handler và external handler

Tạo hai nút:

~~~html
<button onclick="showDemo()">Inline handler</button>
<button id="external">External handler</button>
~~~

Sau đó chuyển logic sang external script:

~~~js
function showDemo() {
  document.querySelector("#output").textContent = "Đã nhấn nút";
}

document.querySelector("#external").addEventListener("click", showDemo);
~~~

Thử CSP chỉ cho phép script nguồn tin cậy và nonce phù hợp. Quan sát inline handler bị chặn theo policy trong khi external handler hợp lệ vẫn chạy.

**Mục tiêu:** hiểu việc tách hành vi khỏi HTML giúp giảm nested context và hỗ trợ CSP chặt chẽ hơn.

## 20. Thực hành D — Nhận diện source-to-sink trong DevTools

Trong trang thử nghiệm, dùng query string chỉ chứa text:

~~~text
/demo?message=hello%20browser
~~~

Đặt breakpoint tại nơi đọc location.search và nơi gán dữ liệu vào DOM. Trong DevTools:

1. Xác định source.
2. Theo dõi giá trị sau parse/decode.
3. Xác định sink.
4. Thử thay sink từ innerHTML sang textContent.
5. Xác minh dữ liệu hiển thị như chữ, không tạo node HTML.
6. Kiểm tra CSP Console để hiểu policy đang cho phép/chặn script nào.

Không chạy payload phá hoại hoặc thử trên hệ thống không được phép.

## 21. Checklist review JavaScript context

- [ ] Xác định parser và context cuối cùng cho mọi dữ liệu không tin cậy.
- [ ] Tránh ghép dữ liệu trực tiếp vào JavaScript source hoặc inline script.
- [ ] Ưu tiên external script và truyền dữ liệu qua API/JSON hoặc DOM data.
- [ ] Nếu nhúng JSON vào HTML script data block, dùng serializer an toàn cho HTML script context; không chỉ JSON.stringify.
- [ ] Nhớ HTML parser có thể kết thúc phần tử script khi gặp </script> trong nội dung.
- [ ] Không chèn input vào template literal source; dùng biến runtime.
- [ ] Tránh inline event handler; dùng addEventListener.
- [ ] Không dùng javascript: URL hoặc redirect đích tùy ý.
- [ ] Dùng textContent cho text; sanitize khi bắt buộc render HTML.
- [ ] Tránh eval, Function và timer nhận string.
- [ ] Không coi encodeURIComponent, HTML escape hoặc JSON.stringify là biện pháp universal.
- [ ] Áp dụng CSP nonce/hash và tránh unsafe-inline/unsafe-eval nếu có thể.
- [ ] Bật Trusted Types enforcement theo lộ trình nếu browser mục tiêu hỗ trợ; policy phải sanitize thật.
- [ ] Rà soát source từ query, hash, referrer, postMessage, storage và API.
- [ ] Kiểm tra dữ liệu qua nhiều tầng template/parser, không chỉ một lớp escape.
- [ ] Không nhúng secret hoặc dữ liệu ngoài quyền vào HTML/JSON data block.
- [ ] Kiểm thử trên browser mục tiêu bằng DevTools, CSP reports và test source-to-sink.

## 22. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Đã đặt input trong dấu nháy JavaScript thì an toàn.” | **Sai** | Input có thể thoát khỏi string hoặc làm thay đổi cú pháp; còn có HTML parser bên ngoài. |
| “HTML escape dùng được trong JavaScript string.” | **Sai** | Mỗi context có quy tắc encoding riêng. |
| “JSON.stringify luôn an toàn khi nhúng vào script.” | **Sai** | Chuỗi </script> có thể kết thúc phần tử script ở HTML parser. |
| “Script type application/json không qua HTML parser.” | **Sai** | Nó là data block, nhưng vẫn nằm trong script element parsing model. |
| “Template literal không thể bị injection.” | **Sai** | Chèn input vào source template có thể phá dấu backtick hoặc interpolation. |
| “Inline onclick chỉ là HTML attribute.” | **Sai** | Giá trị được diễn giải như JavaScript event-handler code. |
| “URL encode là đủ để ngăn javascript: URL.” | **Sai** | Cần parse và allowlist scheme/origin. |
| “textContent và innerHTML tương đương.” | **Sai** | Một cái tạo text; cái kia parse HTML. |
| “CSP làm mọi output encoding không cần thiết.” | **Sai** | CSP là lớp giảm tác động, không thay sửa source-to-sink. |
| “Trusted Types tự sanitize HTML.” | **Sai** | Policy của ứng dụng phải tạo TrustedHTML an toàn. |
| “HttpOnly ngăn XSS.” | **Sai** | XSS vẫn có thể thao tác trong origin và gọi API. |
| “Input từ API nội bộ luôn đáng tin.” | **Sai** | API có thể chứa dữ liệu người dùng hoặc dữ liệu đã bị thay đổi. |

## 23. Tổng kết

JavaScript context là một trong những vị trí nhạy cảm nhất trong xử lý dữ liệu web vì input có thể bị parser hiểu thành cú pháp và thực thi. Một trang có thể kết hợp HTML parser, JavaScript parser, URL parser và DOM APIs; chỉ escape theo một lớp không đảm bảo dữ liệu an toàn ở lớp tiếp theo.

Ba nguyên tắc cần nhớ:

1. **Đừng biến dữ liệu thành mã:** tránh ghép input vào script source, template literal source, event handler hoặc eval; dùng biến runtime và API DOM an toàn.
2. **Đúng context, đúng serializer:** HTML text, attribute, JavaScript string, JSON trong script và URL có quy tắc khác nhau. JSON.stringify không tự xử lý HTML script termination.
3. **Defense in depth:** dùng CSP nonce/hash, Trusted Types, external scripts, sanitizer phù hợp và kiểm tra backend; các lớp này bổ trợ chứ không thay thế việc xử lý source-to-sink đúng.

Khi review một đoạn template hoặc JavaScript, hãy hỏi: **input đến từ đâu, HTML parser nhìn thấy gì, JavaScript parser nhìn thấy gì, sink diễn giải dữ liệu như thế nào, và có thể truyền dữ liệu bằng API thay cho sinh mã không?** Trả lời được những câu hỏi đó giúp ngăn DOM/reflected XSS mà vẫn giữ luồng dữ liệu rõ ràng.
