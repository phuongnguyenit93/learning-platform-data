# JavaScript encoding

> **Chương:** Output encoding  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Khi server tạo HTML có chứa JavaScript, dữ liệu động có thể được đặt vào một đoạn mã đang được browser phân tích. Nếu dữ liệu được nối trực tiếp vào source code, ký tự trong input có thể làm thay đổi cấu trúc JavaScript hoặc thoát khỏi vị trí chuỗi dự kiến. Đây là một đường dẫn phổ biến dẫn tới **Cross-Site Scripting (XSS)**.

**JavaScript encoding** là cách biểu diễn dữ liệu không tin cậy sao cho JavaScript parser hiểu nó là giá trị dữ liệu trong một context cụ thể, không phải cú pháp hoặc câu lệnh mới. Tuy nhiên, khi JavaScript nằm trong HTML `<script>`, dữ liệu còn đi qua HTML parser trước JavaScript parser. Vì vậy, chỉ escape dấu nháy theo cú pháp JavaScript chưa chắc đã bảo vệ được toàn bộ context.

Nguyên tắc ưu tiên là **không ghép dữ liệu không tin cậy vào JavaScript source**. Hãy truyền dữ liệu qua JSON/API, DOM text, hoặc một data channel được serialize an toàn. Khi bắt buộc phải nhúng dữ liệu vào HTML, cần serializer hiểu cả JavaScript/JSON và ranh giới raw-text của HTML.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích JavaScript context và vì sao encoding phụ thuộc vị trí dữ liệu được chèn vào.
2. Phân biệt JavaScript string literal, expression, template literal, inline event handler và script block.
3. Giải thích vì sao HTML parser có thể kết thúc `<script>` trước khi JavaScript parser xử lý chuỗi.
4. Phân biệt JavaScript string escaping với JSON serialization và HTML-safe JSON serialization.
5. Nhận diện rủi ro khi dùng `eval`, `Function`, string timer và `javascript:` URL.
6. Chọn cách truyền dữ liệu an toàn thay cho nối chuỗi JavaScript.
7. Kiểm chứng output encoding bằng test case và DevTools trong môi trường lab.

## 2. JavaScript context là gì?

JavaScript context là vị trí trong source code nơi dữ liệu được chèn vào và được JavaScript parser diễn giải. Một giá trị có thể nằm trong:

- String literal dùng dấu nháy đơn hoặc kép.
- Template literal dùng dấu backtick.
- Expression hoặc vị trí nhận một giá trị JavaScript.
- Object/array literal hoặc JSON-like data.
- Inline event handler như `onclick`.
- Script block được nhúng trong HTML.
- Một vùng code được thực thi động qua `eval` hoặc `Function`.

Ví dụ:

```js
const displayName = "USER_VALUE"; // String literal
const message = `Xin chào ${USER_VALUE}`; // Template literal
const settings = { theme: USER_VALUE }; // Expression/value
```

Các vị trí này có quy tắc cú pháp khác nhau. Encoder cho string literal không thể biến input tùy ý thành một expression an toàn. Một chuỗi được escape đúng bên trong dấu nháy vẫn có thể không an toàn nếu nó được đưa vào template literal, HTML attribute hoặc vùng script của HTML theo cách khác.

**Context do cú pháp bao quanh dữ liệu quyết định.** Tên biến như `userName`, nguồn dữ liệu như database hay việc dữ liệu đã được validate không thay đổi context đầu ra.

## 3. Quy tắc ưu tiên: giữ dữ liệu tách khỏi code

Thay vì tạo JavaScript source từ dữ liệu, hãy truyền dữ liệu qua API và xử lý bằng JavaScript đã có sẵn:

```js
const response = await fetch("/api/page-data");
const pageData = await response.json();

document.querySelector("#welcome").textContent = pageData.displayName;
```

Trong cách này:

- JavaScript source là code tĩnh do ứng dụng kiểm soát.
- JSON parser chuyển response thành dữ liệu.
- `textContent` đặt giá trị thành text node, không parse thành HTML.
- Dữ liệu không được thực thi như code chỉ vì nó chứa dấu nháy hoặc ký tự đặc biệt.

Nếu cần truyền một giá trị server-rendered vào frontend, cân nhắc endpoint JSON, framework hydration có serializer an toàn hoặc data attribute được HTML-attribute-encode đúng cách. Tránh tạo đoạn `<script>` bằng nối chuỗi.

## 4. JavaScript string literal context

Một cách nội suy thường gặp:

```html
<script>
  const displayName = 'USER_VALUE';
</script>
```

Nếu dữ liệu chứa dấu nháy kết thúc string, backslash, newline hoặc ký tự điều khiển, nó có thể làm thay đổi cú pháp. JavaScript string literal có quy tắc escape riêng; HTML entity encoding không phải encoder JavaScript.

Ví dụ, nếu dữ liệu có dấu nháy đơn và được nối vào giữa cặp dấu nháy đơn mà không encode, parser có thể hiểu phần sau là code thay vì nội dung string. Chỉ escape ký tự `'` cũng chưa đủ: cần xử lý backslash, ký tự điều khiển, line terminator và các ranh giới parser khác.

### 4.1 Những ký tự cần quan tâm

Trong string literal, serializer phải xử lý tối thiểu:

- Dấu phân cách string đang dùng (`'` hoặc `"`).
- Dấu backslash `\\`.
- Newline, carriage return, tab và ký tự điều khiển.
- Line separator và paragraph separator (`U+2028`, `U+2029`) khi tương thích với môi trường đích cần được bảo đảm.
- Các ký tự có thể làm thay đổi parser context khi script được nhúng trong HTML, đặc biệt dấu `<` mở đầu chuỗi `</script`.

Đừng tự viết hàm thay ký tự theo một vài ví dụ. JavaScript có escape sequence, Unicode escape, surrogate pair và quy tắc parser riêng. Hãy dùng serializer/encoder được thiết kế rõ cho context đầu ra hoặc tránh nội suy.

## 5. JavaScript expression context

Expression context là nơi JavaScript mong đợi một giá trị hoặc biểu thức:

```js
const userId = USER_VALUE;
const options = { enabled: USER_VALUE };
```

Không có một phép “JavaScript string escape” chung nào có thể làm cho input tùy ý trở thành expression an toàn. Nếu muốn truyền một chuỗi, nó phải được serialize thành một string literal hợp lệ; nếu muốn truyền object/array, cần serializer dữ liệu phù hợp. Không đặt input thô vào vị trí expression.

Ví dụ, thay vì:

```html
<script>
  const pageConfig = USER_JSON_TEXT;
</script>
```

hãy lấy dữ liệu qua API:

```js
const pageConfig = await fetch("/api/page-config").then((r) => r.json());
```

Hoặc nếu kiến trúc server-rendered cần nhúng dữ liệu, dùng cơ chế serialize có bảo vệ HTML script context như trình bày ở mục 8. Không dùng validation kiểu “chỉ chứa chữ và số” để biến một expression thành an toàn; cú pháp JavaScript rộng hơn nhiều.

## 6. Template literal context

Template literal dùng dấu backtick và cho phép biểu thức nội suy bằng `${...}`:

```js
const greeting = `Xin chào ${displayName}`;
```

Nếu dữ liệu được nối vào bên trong template literal source, các ký tự backtick, backslash và chuỗi `${` có thể ảnh hưởng cấu trúc. Một encoder dành cho string dùng dấu nháy kép không tự động an toàn trong template literal.

Không tạo template literal source bằng cách ghép chuỗi từ input. Hãy tạo template trong code tĩnh và truyền dữ liệu qua biến:

```js
const greeting = `Xin chào ${pageData.displayName}`;
document.querySelector("#welcome").textContent = greeting;
```

Ở đây `${pageData.displayName}` là expression được viết sẵn trong code; dữ liệu chỉ được lấy làm giá trị runtime, không được parser đọc lại như source code.

## 7. Inline event handler và JavaScript trong HTML attribute

Các attribute như `onclick`, `onerror`, `onload` chứa JavaScript được browser biên dịch trong ngữ cảnh HTML attribute. Ví dụ:

```html
<button onclick="showMessage('USER_VALUE')">Mở</button>
```

Đây là **hai context lồng nhau**:

1. HTML quoted attribute context.
2. JavaScript source context bên trong event handler.

Một lần HTML attribute encoding không giải quyết đầy đủ cú pháp JavaScript bên trong. Ngược lại, chỉ JavaScript string escaping không bảo vệ cú pháp HTML attribute bên ngoài. Việc cố áp dụng nhiều lớp escape thủ công rất dễ sai thứ tự hoặc tạo double encoding.

**Cách xử lý tốt nhất là bỏ inline event handler.** Dùng event listener trong file JavaScript tĩnh:

```html
<button id="open-message">Mở</button>
```

```js
const button = document.querySelector("#open-message");
button.addEventListener("click", () => {
  showMessage(pageData.message);
});
```

Code handler không được tạo từ input. Dữ liệu được truyền như giá trị runtime. Cách này cũng giúp triển khai CSP chặt chẽ dễ hơn vì không phụ thuộc inline event handler.

## 8. Ranh giới HTML `<script>` và JavaScript parser

Đây là điểm đặc biệt dễ bị bỏ sót khi nói về JavaScript encoding.

Khi browser đọc HTML, **HTML parser xử lý nội dung `<script>` như raw text**. Nó tìm dấu kết thúc script `</script` theo quy tắc HTML trước khi JavaScript parser phân tích toàn bộ nội dung thành code. Vì vậy, một chuỗi JavaScript có chứa `</script>` vẫn có thể kết thúc element script ở tầng HTML parser, ngay cả khi ký tự đó đang nằm bên trong dấu nháy JavaScript.

Ví dụ minh họa cấu trúc dễ lỗi:

```html
<script>
  const text = "DỮ_LIỆU_CÓ_CHUỖI_ĐÓNG_SCRIPT";
</script>
```

JavaScript string escaping thông thường không nhất thiết xử lý ranh giới HTML này. Nếu serializer chỉ escape dấu nháy mà giữ nguyên `<`, HTML parser vẫn có thể nhận ra chuỗi bắt đầu thẻ đóng script.

**Giải pháp ưu tiên:** không nhúng dữ liệu không tin cậy vào executable script. Nếu bắt buộc phải serialize dữ liệu trong `<script>`, cần dùng serializer hiểu HTML script raw-text context, thường biểu diễn ký tự `<` bằng escape Unicode `\u003c` trong JSON output để chuỗi `</script` không xuất hiện dưới dạng ký tự literal trong HTML source. Cũng cần xử lý các line separator theo yêu cầu tương thích.

## 9. JSON serialization không đồng nghĩa HTML-safe JSON

`JSON.stringify` tạo một chuỗi JSON hợp lệ cho dữ liệu JavaScript. Nhưng **JSON hợp lệ chưa chắc an toàn khi nhúng trực tiếp vào HTML**.

Ví dụ:

```js
const json = JSON.stringify({ message: userInput });
```

Nếu `json` được đặt trực tiếp vào nội dung `<script>` hoặc `<script type="application/json">`, HTML parser vẫn nhận diện dấu đóng `</script`. `type="application/json"` làm script element trở thành data block thay vì JavaScript thực thi, nhưng **không thay đổi quy tắc HTML parser tìm thẻ đóng script**.

Vì vậy, có hai lớp serialization khác nhau:

| Lớp | Mục tiêu | Ví dụ |
| --- | --- | --- |
| JSON serialization | Biểu diễn object/array/string thành cú pháp JSON hợp lệ | `JSON.stringify(value)` |
| HTML-safe JSON serialization | Bảo đảm JSON có thể đặt trong HTML script raw-text mà không tạo chuỗi đóng element hoặc làm sai HTML | JSON serializer của framework có escape `<` thành `\u003c` và xử lý ký tự đặc biệt phù hợp |

Một số thư viện server cung cấp tùy chọn HTML-safe JSON như `JSON_HEX_TAG` hoặc cơ chế tương đương. Cách triển khai phụ thuộc ngôn ngữ/framework. Không mặc định rằng `JSON.stringify` hoặc `JSON.stringify` cộng HTML encoding thông thường đã đủ.

### 9.1 Ví dụ dùng data block khi phải render server-side

Markup có thể dùng data block:

```html
<script id="page-data" type="application/json">
  {"title":"Tiêu đề đã serialize an toàn cho HTML script context"}
</script>
```

Sau đó đọc nội dung như JSON:

```js
const dataElement = document.querySelector("#page-data");
const pageData = JSON.parse(dataElement.textContent);
document.querySelector("#title").textContent = pageData.title;
```

Điều kiện bắt buộc: server phải tạo nội dung bằng **HTML-safe JSON serializer** trước khi đặt vào data block. Đừng chèn JSON thô. Nếu có thể, endpoint JSON riêng vẫn là lựa chọn dễ kiểm soát hơn.

## 10. JavaScript encoding khác HTML encoding và URL encoding

Các loại encoding giải quyết những parser/grammar khác nhau:

| Loại | Mục tiêu | Không thay thế |
| --- | --- | --- |
| JavaScript string encoding | Biểu diễn dữ liệu như literal trong JavaScript string context | HTML raw-text handling, URL validation |
| JSON serialization | Chuyển giá trị thành JSON | HTML-safe serialization khi nhúng vào `<script>` |
| HTML text/attribute encoding | Bảo vệ cú pháp HTML text/attribute | JavaScript expression/string grammar |
| URL component encoding | Biểu diễn thành phần URL như query parameter | Validate scheme/host; HTML attribute encoding |
| CSS encoding/validation | Xử lý giá trị theo CSS context | JavaScript hoặc HTML encoding |

Ví dụ: encode `&` thành `&amp;` là thao tác HTML entity; JavaScript parser không xem `&amp;` như cách escape string tổng quát. Ngược lại, `\\u003c` là dạng escape Unicode trong JavaScript/JSON string, không phải cách mã hóa HTML attribute. Chọn encoder theo context cuối cùng, không theo nguồn dữ liệu.

## 11. `eval`, `Function` và timer nhận chuỗi

Các API thực thi chuỗi biến dữ liệu thành source code:

```js
eval(userSuppliedText);
new Function(userSuppliedText)();
setTimeout(userSuppliedText, 1000);
```

Nếu dữ liệu có thể bị người dùng hoặc nguồn ngoài kiểm soát, các API này tạo ra đường thực thi code trực tiếp. JavaScript string encoding không thể biến một đoạn code không tin cậy thành logic an toàn; escape string chỉ có ý nghĩa nếu mục tiêu là một string literal, không phải một chương trình cần thực thi.

Hãy truyền function thay vì chuỗi:

```js
setTimeout(() => {
  refreshStatus();
}, 1000);
```

Nếu ứng dụng cần biểu thức hoặc rule động, dùng parser cho một ngôn ngữ dữ liệu giới hạn, schema validation và allowlist thao tác. Không dùng JavaScript evaluator để thực thi cấu hình hoặc biểu thức do người dùng cung cấp.

## 12. `javascript:` URL không phải bài toán escape string

Một URL như `javascript:...` có thể được browser diễn giải như mã trong một số ngữ cảnh điều hướng. Việc HTML-encode hoặc JavaScript-escape chuỗi không biến scheme này thành URL an toàn.

Khi xử lý link do người dùng cung cấp:

1. Parse bằng `URL` với base rõ ràng nếu cho phép URL tương đối.
2. Allowlist scheme cần thiết, thường là `https:` và có thể `http:` theo chính sách.
3. Kiểm tra host/path nếu chỉ cho phép đích nội bộ.
4. Gán URL đã kiểm tra vào `href` bằng DOM property.
5. Khi render HTML phía server, vẫn encode giá trị URL theo HTML attribute context.

Không dùng regex đơn giản như `startsWith("https")` thay cho parser URL. `javascript:` phải bị từ chối nếu ứng dụng không có nhu cầu đặc biệt (thông thường không có).

## 13. JavaScript encoding ở server-side template

Một template engine có thể cung cấp filter/encoder cho JavaScript context. Cần kiểm tra rõ filter đó bảo vệ **string literal nào**, có xử lý dấu backslash, quote, control character và line separator không, và liệu nó có xử lý ranh giới HTML `<script>` hay không.

Không giả định các filter sau tương đương:

- HTML escape.
- JavaScript string escape.
- JSON serialize.
- HTML-safe JSON serialize.

Tên filter trong mỗi framework có thể gây hiểu nhầm. Hãy đọc tài liệu chính thức của đúng framework/version và kiểm thử output HTML thực tế. Tránh tự xây dựng filter bằng các lệnh replace rời rạc.

Một template an toàn hơn thường dùng external JavaScript và data endpoint. Nếu server phải render bootstrap data, dùng helper được framework thiết kế để serialize dữ liệu vào HTML script context, không nối chuỗi thủ công.

## 14. CSP và Trusted Types hỗ trợ nhưng không thay encoding

**Content Security Policy (CSP)** có thể hạn chế inline script, event handler và nguồn script được phép tải. Một policy dùng nonce/hash giúp giảm khả năng script không được phép thực thi. Nhưng CSP không biến việc nối dữ liệu vào JavaScript source thành an toàn; một script đã được tin cậy vẫn có thể chứa lỗi injection.

**Trusted Types** kiểm soát một số DOM sink nhận HTML/script-like string, ví dụ `innerHTML`. Cơ chế này hữu ích cho DOM XSS, nhưng không phải encoder cho JavaScript inline context và không tự bảo vệ mọi chỗ nhúng dữ liệu vào script.

Ví dụ CSP định hướng:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; object-src 'none'; base-uri 'none'
```

`{RANDOM_PER_RESPONSE}` là placeholder; server phải sinh nonce ngẫu nhiên mới cho mỗi response và gắn cùng nonce vào script được phép. Không copy placeholder literal vào production. Hãy triển khai CSP theo luồng script thực tế, kiểm tra report-only trước khi cưỡng chế nếu ứng dụng có nhiều tích hợp.

## 15. Chọn cách truyền dữ liệu an toàn

| Nhu cầu | Cách ưu tiên | Lưu ý |
| --- | --- | --- |
| Hiển thị text | JSON/API rồi `textContent` | Không parse dữ liệu thành HTML |
| Cấu hình frontend | Endpoint JSON | Giữ code và data tách biệt |
| Giá trị nhỏ trong server-rendered HTML | Quoted `data-*` attribute với HTML attribute encoding | Đọc bằng `dataset`; không dùng event handler attribute |
| Bootstrap object bắt buộc inline | Framework HTML-safe JSON serializer | Xử lý `</script`, line separator và parser context |
| Nội dung HTML có định dạng | Sanitizer chuyên dụng rồi đưa vào HTML sink | Chỉ khi thật sự cần markup |
| Hành động UI | `addEventListener` với closure | Không tạo inline handler từ dữ liệu |
| Timer/callback | Truyền function | Không truyền chuỗi code cho timer |
| URL do người dùng nhập | URL parser + scheme/host allowlist | Sau đó encode theo context khi render HTML |

## 16. Quy trình review JavaScript context

Khi tìm thấy dữ liệu được render vào JavaScript, hãy thực hiện các bước:

1. **Tìm source:** dữ liệu từ query string, form, API, database, cookie, storage, `postMessage` hay hệ thống ngoài?
2. **Xác định vị trí:** string literal, expression, template literal, inline handler, executable script hay JSON data block?
3. **Kiểm tra parser lồng nhau:** JavaScript có nằm trong HTML `<script>` hoặc quoted attribute không?
4. **Ưu tiên tách code/data:** chuyển sang API JSON, data attribute hoặc DOM API.
5. **Nếu cần serialize:** dùng serializer đúng cho JS/JSON và HTML raw-text context; không tự escape thủ công.
6. **Loại bỏ dynamic execution:** tìm `eval`, `Function`, string timer và `javascript:` URL.
7. **Kiểm tra URL riêng:** parse và allowlist scheme/host trước khi gán.
8. **Bổ sung CSP:** hạn chế inline script/event handler và nguồn script; dùng Trusted Types cho sink phù hợp.
9. **Test output cuối:** xem HTML response, DOM sau parse, Console và hành vi của browser với input biên.

## 17. Thực hành kiểm chứng trong môi trường lab

Thực hiện trên ứng dụng local hoặc trang lab bạn quản lý, với dữ liệu giả. Không thử nghiệm trên tài khoản hoặc website bên ngoài.

### Bài thử A — String literal và dấu nháy

Tạo trang lab nhận tham số `name`, rồi so sánh hai cách: nối trực tiếp vào source `<script>` và lấy dữ liệu từ endpoint JSON. Dùng input chứa dấu nháy đơn/kép, backslash và newline; quan sát response source và Console.

**Kỳ vọng:** Nối chuỗi trực tiếp có thể làm hỏng cú pháp hoặc thay đổi cấu trúc script. Cách lấy JSON giữ dữ liệu tách khỏi source code.

### Bài thử B — Template literal

Trong một trang lab, truyền dữ liệu có backtick và chuỗi `${...}` vào một template literal được tạo từ source động; so sánh với template literal tĩnh dùng biến runtime.

**Kỳ vọng:** Template literal source động cần xử lý cú pháp riêng; template tĩnh chỉ chèn giá trị runtime không khiến dữ liệu được parse lại như code.

### Bài thử C — Ranh giới `</script>`

Tạo dữ liệu JSON lab có một chuỗi chứa `</script>` và render lần lượt bằng JSON thô trong `<script type="application/json">` và bằng HTML-safe JSON serializer. Xem DOM trong Elements và nội dung response trong Network.

**Kỳ vọng:** Data block vẫn bị HTML parser xử lý theo raw-text rule; serializer an toàn phải ngăn chuỗi đóng script xuất hiện literal trong HTML source (ví dụ escape `<` thành `\u003c`). JSON hợp lệ đơn thuần chưa đủ.

### Bài thử D — Inline event handler và event listener

So sánh nút có `onclick` được ghép từ dữ liệu với nút có `addEventListener` trong file JavaScript tĩnh. Quan sát CSP khi chặn inline handler.

**Kỳ vọng:** Event listener tách code khỏi data và phù hợp hơn với CSP chặt. Không dùng input người dùng làm source handler.

### Bài thử E — API thực thi chuỗi

Trong code lab, tìm `eval`, `Function`, `setTimeout`/`setInterval` nhận chuỗi. Thay bằng callback hoặc parser dữ liệu giới hạn, sau đó kiểm tra chức năng còn hoạt động.

**Kỳ vọng:** Ứng dụng không cần biên dịch input thành JavaScript source để thực hiện tác vụ UI thông thường.

## 18. Các lỗi thường gặp

| Nhận định/cách làm sai | Vì sao không an toàn | Hướng xử lý |
| --- | --- | --- |
| Dùng HTML escape cho JavaScript string | HTML entity không phải JavaScript string escape | Tách data khỏi code hoặc dùng serializer đúng context |
| Chỉ escape dấu nháy | Bỏ sót backslash, newline, control char và parser boundary | Dùng serializer đã được kiểm chứng |
| Cho rằng `JSON.stringify` đủ để nhúng `<script>` | HTML parser vẫn nhận diện `</script>` | Dùng HTML-safe JSON serializer hoặc endpoint riêng |
| Dùng JavaScript encoder trong HTML attribute | HTML parser chạy trước và có cú pháp attribute riêng | Bỏ inline handler; nếu bắt buộc cần encoder cho từng context lồng nhau |
| Nối input vào template literal source | Backtick và `${` có thể thay đổi cấu trúc | Template tĩnh, dữ liệu runtime |
| Dùng `eval` để đọc cấu hình | Biến dữ liệu thành code thực thi | JSON.parse và schema validation |
| Tin URL đã JavaScript-escape | Escape không kiểm tra scheme/host | Parse URL và allowlist scheme/host |
| Dùng `javascript:` URL | URL trở thành đường thực thi code | Từ chối scheme không được phép |
| Tắt auto-escaping của template | Dữ liệu có thể trở thành source code/markup | Dùng serializer/encoder context-aware |
| Cho rằng CSP sửa được mọi injection | Script được tin cậy vẫn có thể có lỗi | Sửa source/sink và encoding tại gốc |

## 19. Checklist review JavaScript encoding

- [ ] Dữ liệu không tin cậy không được nối trực tiếp vào JavaScript source.
- [ ] Phân biệt string literal, expression, template literal, inline handler và script block.
- [ ] Ưu tiên endpoint JSON hoặc data channel tách khỏi code.
- [ ] Nếu serialize inline, dùng serializer hiểu HTML `<script>` raw-text context.
- [ ] Đã kiểm thử chuỗi `</script`, dấu nháy, backslash, newline và Unicode line separator.
- [ ] Không dùng `eval`, `Function` hoặc timer nhận chuỗi không tin cậy.
- [ ] Không dùng `javascript:` URL; URL được parse và allowlist scheme/host.
- [ ] Không dùng inline event handler được tạo từ dữ liệu.
- [ ] Đã kiểm tra template filter thực sự bảo vệ context nào.
- [ ] CSP hạn chế inline script và Trusted Types được áp dụng ở sink phù hợp khi có thể.
- [ ] Test kiểm tra HTML response, DOM cuối cùng và hành vi browser.
- [ ] Không log hoặc đưa dữ liệu nhạy cảm vào URL/test artifact.

## 20. Câu hỏi tự kiểm tra

1. Vì sao JavaScript string encoding không thể bảo vệ mọi JavaScript expression context?
2. Tại sao `</script>` có thể kết thúc script dù nó nằm trong dấu nháy JavaScript?
3. JSON hợp lệ khác HTML-safe JSON như thế nào?
4. Vì sao `<script type="application/json">` vẫn cần xử lý chuỗi đóng script?
5. Inline event handler chứa những context lồng nhau nào?
6. Vì sao template literal cần chú ý backtick và `${`?
7. `eval` và `setTimeout` nhận chuỗi tạo ra rủi ro gì?
8. Vì sao JavaScript escaping không thay thế URL scheme validation?
9. CSP và Trusted Types hỗ trợ những lớp phòng vệ nào, và giới hạn của chúng là gì?

## 21. Ghi nhớ

JavaScript encoding chỉ có ý nghĩa khi biết dữ liệu được chèn vào **string literal, expression, template literal hay một context lồng trong HTML**. Đặc biệt, HTML parser xử lý `<script>` trước JavaScript parser và có thể nhận diện `</script>` ngay cả khi chuỗi nằm trong JavaScript string. Vì vậy, `JSON.stringify` hoặc escape dấu nháy đơn thuần chưa đủ để nhúng dữ liệu an toàn vào HTML.

Ưu tiên giữ code và data tách biệt bằng JSON/API, DOM API và `textContent`. Nếu buộc phải inline data, dùng serializer HTML-safe đã được kiểm chứng; tránh inline event handler, `eval`, `Function` và string timer; validate URL độc lập; bổ sung CSP và Trusted Types phù hợp. **Dữ liệu phải được serialize theo parser context cuối cùng để browser luôn hiểu nó là giá trị, không phải source code ngoài ý muốn.**
