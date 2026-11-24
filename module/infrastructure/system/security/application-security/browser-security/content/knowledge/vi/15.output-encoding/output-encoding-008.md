# Kiểm thử output encoding

> **Chương:** Output encoding
> **Chủ đề:** Kiểm thử encoding
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập kế hoạch kiểm thử output encoding.
2. Xác định context đầu ra: HTML text, HTML attribute, URL, JavaScript, CSS và DOM sink.
3. Chọn payload an toàn để xác minh ký tự đặc biệt được encode đúng.
4. Phân biệt output encoding với input validation, HTML sanitization và CSP.

## 1. Kiểm thử output encoding nhằm xác minh điều gì?

**Output encoding** chuyển dữ liệu không tin cậy thành biểu diễn an toàn đối với **ngữ cảnh mà dữ liệu sẽ được đưa vào**. Mục tiêu là giữ dữ liệu ở vai trò dữ liệu, không để browser hiểu nó thành markup hoặc mã thực thi.

Ví dụ người dùng nhập:

```html
<img src=x onerror="document.documentElement.dataset.test='executed'">
```

Nếu ứng dụng hiển thị chuỗi này như văn bản, browser phải hiển thị nguyên văn các ký tự. Nếu ứng dụng chèn chuỗi vào HTML mà không encode, browser có thể tạo phần tử ảnh và xử lý event handler. Đây là lỗi **Cross-Site Scripting (XSS)** nếu mã không tin cậy được thực thi trong origin của ứng dụng.

Không có một hàm encode duy nhất phù hợp cho mọi ngữ cảnh. HTML text, HTML attribute, URL, JavaScript và CSS có quy tắc khác nhau.

## 2. Xác định context trước khi chọn payload

| Context đầu ra | Ví dụ sink | Cách xử lý chính |
|---|---|---|
| HTML text node | p element chứa dữ liệu | Encode ampersand, dấu nhỏ hơn và dấu lớn hơn |
| HTML attribute | input value có quote | Quote attribute và encode ký tự đặc biệt, gồm dấu nháy |
| URL component | Query parameter | Dùng URLSearchParams hoặc encodeURIComponent |
| URL trong HTML attribute | Link href | Parse/validate scheme và đích URL, sau đó HTML-attribute encode |
| JavaScript data | Giá trị trong script | Tránh nội suy trực tiếp; truyền JSON riêng |
| CSS value | Giá trị style | Dùng allowlist hoặc class cố định |
| DOM text | Text node | Ưu tiên textContent |
| DOM HTML | innerHTML | Tránh nếu không cần HTML; nếu cần, sanitizer allowlist |

### 2.1. HTML text context

```html
<p id="message">USER_VALUE</p>
```

Các ký tự cấu trúc quan trọng gồm ampersand thành **&amp;**, dấu nhỏ hơn thành **&lt;** và dấu lớn hơn thành **&gt;**.

### 2.2. HTML attribute context

```html
<input value="USER_VALUE">
```

Attribute phải được **đặt trong dấu nháy**. Ngoài ampersand và dấu ngoặc nhọn, cần encode dấu nháy tương ứng với quote bao quanh giá trị. HTML attribute encoding không quyết định giá trị có hợp lệ trong href, src hoặc action hay không; URL cần được parse và kiểm tra scheme/host riêng.

### 2.3. URL context

```js
const url = new URL('/search', 'https://app.example.test');
url.searchParams.set('q', userInput);
```

Percent encoding không thay thế URL validation. Scheme javascript: hoặc data: không tự trở nên an toàn chỉ vì đã encode.

### 2.4. JavaScript và CSS context

Không nối dữ liệu người dùng trực tiếp vào mã JavaScript inline. HTML parser có thể nhận diện dấu đóng script trước JavaScript parser. Ưu tiên endpoint JSON, response.json() và DOM textContent; tránh eval, Function và inline event handler.

Không nối chuỗi không tin cậy vào CSS. Với màu sắc, kích thước hoặc theme, map giá trị qua allowlist:

```js
const allowedColors = new Set(['red', 'blue', 'black', 'white']);
const color = allowedColors.has(inputColor) ? inputColor : 'black';
element.style.color = color;
```

## 3. Quy trình kiểm thử output encoding

Kiểm thử cần đi từ dữ liệu nguồn đến sink cuối cùng trong browser, thay vì chỉ nhìn chuỗi đã escape trong một helper.

### Bước 1 — Lập danh sách nguồn dữ liệu

Tìm dữ liệu không tin cậy có thể xuất hiện trong giao diện:

- Query string và path parameter.
- Form input, tên hiển thị, bình luận, mô tả và tên file.
- Dữ liệu lưu trong database rồi render ở trang khác (stored input).
- API response, webhook hoặc dịch vụ bên thứ ba.
- Nội dung import/export, thông báo lỗi và log được đưa vào dashboard.
- Dữ liệu được JavaScript cập nhật vào DOM sau khi trang đã tải.

Không chỉ kiểm tra trường nhập ngay sau submit. Một giá trị có thể được lưu và hiển thị trong profile, danh sách quản trị, email preview hoặc trang báo cáo.

### Bước 2 — Xác định sink và context thực tế

Theo từng luồng dữ liệu, ghi rõ:

1. Dữ liệu được render trong text node, attribute, URL, script, CSS hay DOM API nào?
2. Framework/template engine có auto-escape không?
3. Có helper raw/safe/trusted nào bỏ qua auto-escape không?
4. Dữ liệu có được decode hoặc ghép vào chuỗi sau khi encode không?
5. Có nhiều renderer khác nhau cho SSR, hydration, component hoặc trang quản trị không?

Không kết luận “framework đã auto-escape” rồi bỏ qua kiểm thử. Các helper raw/safe, dangerouslySetInnerHTML, innerHTML hoặc template helper đặc biệt có thể bỏ qua bảo vệ mặc định.

### Bước 3 — Chọn bộ dữ liệu kiểm thử

Bắt đầu bằng chuỗi marker không thực thi:

```text
OE-CANARY-2026
& < > " ' backtick / % = ; : ( ) [ ]
Tiếng Việt: Đăng nhập — Đà Nẵng
Unicode: é, é, 😀
```

Các giá trị này giúp phát hiện:

- Ký tự bị mất hoặc đổi thứ tự.
- Ampersand tạo entity ngoài dự kiến.
- Dấu ngoặc nhọn tạo markup.
- Dấu quote làm thoát attribute.
- Dấu phần trăm hoặc Unicode bị encode/decode sai.
- Double encoding như &amp;lt; thay vì &lt;.

Sau đó dùng payload cấu trúc trong môi trường kiểm thử được phép:

```text
"><svg onload="document.documentElement.dataset.oe='executed'"></svg>
</textarea><svg onload="document.documentElement.dataset.oe='executed'"></svg>
</script><script>document.documentElement.dataset.oe='executed'</script>
javascript:document.documentElement.dataset.oe='executed'
```

Đây là **canary không phá hoại**: nó chỉ đặt thuộc tính data-oe trên document nếu được thực thi. Chỉ dùng trên ứng dụng local/staging được phép kiểm thử; không gửi payload tới hệ thống bên thứ ba hoặc dữ liệu người dùng thật.

### Bước 4 — Kiểm tra kết quả trong browser

Với mỗi payload:

1. Gửi dữ liệu qua đúng luồng sản phẩm (form, query, API hoặc dữ liệu đã lưu).
2. Mở DevTools → Elements và tìm marker.
3. Kiểm tra dữ liệu nằm trong text node hay đã tạo element/attribute mới.
4. Mở Console và kiểm tra document.documentElement.dataset.oe; giá trị không được đặt bởi payload.
5. Kiểm tra Network để biết server trả chuỗi raw, encoded hay đã decode.
6. Lặp lại sau refresh, điều hướng, mở trang quản trị và thao tác DOM động.

Không chỉ tìm chuỗi %3C hoặc &lt; trong View Source. Browser parse HTML entities thành ký tự trong DOM text node; điều cần xác minh là dữ liệu vẫn nằm trong context dữ liệu và không tạo cấu trúc/mã thực thi ngoài ý muốn.

### Bước 5 — Kiểm thử hồi quy và nhiều browser

Lặp lại test trên các luồng render quan trọng và browser được sản phẩm hỗ trợ. Kiểm tra:

- SSR và client-side render/hydration.
- Dữ liệu mới nhập và dữ liệu đã lưu từ trước.
- Chuỗi rỗng, Unicode, emoji và chuỗi dài trong giới hạn ứng dụng.
- Các trường hợp encode một lần, decode một lần và dữ liệu đã được encode từ nguồn khác.
- Template thông thường và template có helper raw/safe.

## 4. Bộ test theo từng context

| Context | Payload nên thử | Kết quả an toàn mong đợi |
|---|---|---|
| HTML text | Thẻ b có marker | Hiển thị nguyên văn; không tạo thẻ b |
| HTML attribute | Dấu quote và chuỗi tạo event attribute | Giá trị vẫn nằm trong một attribute đã quote; không tạo attribute mới |
| URL query | Giá trị chứa ampersand và dấu bằng | Vẫn là một giá trị query; không tạo parameter mới |
| URL destination | Scheme javascript hoặc data | URL bị từ chối hoặc thay bằng đích an toàn theo policy |
| JavaScript block | Dữ liệu chứa dấu đóng script | Không kết thúc script element hoặc tạo script mới |
| CSS value | Dữ liệu chứa dấu chấm phẩy và declaration khác | Chỉ giá trị allowlist được chấp nhận |
| DOM text | Markup truyền qua textContent | Chỉ hiển thị văn bản; không có node mới |
| DOM HTML | Markup không tin cậy vào innerHTML | Không dùng trực tiếp; nếu cần HTML phải sanitize và kiểm thử allowlist |

Một test pass không có nghĩa toàn bộ ứng dụng an toàn. Phải lập danh sách sink và kiểm thử từng context đang được sử dụng.

## 5. Encode đúng một lần và tránh double encoding

Output encoding phải xảy ra tại điểm render theo context. Nếu encode quá sớm rồi lưu giá trị đã encode trong database, các trang khác có thể encode lần nữa:

```text
Input:                 <b>Hi</b>
Encode HTML lần 1:     &lt;b&gt;Hi&lt;/b&gt;
Encode HTML lần 2:     &amp;lt;b&amp;gt;Hi&amp;lt;/b&amp;gt;
```

Double encoding thường làm nội dung hiển thị sai, nhưng cách “sửa” bằng decode trước khi render có thể tạo lỗ hổng nếu dữ liệu được đưa vào context khác.

Quy tắc:

- Lưu dữ liệu ở dạng dữ liệu gốc đã validate theo nghiệp vụ, không lưu HTML-escaped chỉ để dùng cho một màn hình.
- Encode tại điểm xuất theo context.
- Không decode dữ liệu không tin cậy chỉ để giao diện “đẹp hơn”.
- Ghi rõ hàm helper đang xử lý context nào.
- Nếu dữ liệu đi qua nhiều tầng, xác định tầng nào chịu trách nhiệm encode và không encode lặp.

### 5.1. Phân biệt output encoding và HTML sanitization

**Output encoding** biến ký tự có ý nghĩa cú pháp thành biểu diễn dữ liệu. Ví dụ dấu nhỏ hơn thành &lt;, khiến browser hiển thị ký tự đó.

**HTML sanitization** phân tích markup và loại bỏ phần tử, attribute hoặc URL không được cho phép, đồng thời giữ lại một tập HTML hợp lệ. Sanitization chỉ cần khi sản phẩm thật sự cho phép người dùng nhập rich text/HTML.

Không dùng regex tự chế để “xóa script”. HTML có parser, namespace, attribute và nhiều cách biểu diễn khác nhau; hãy dùng sanitizer được duy trì, cấu hình allowlist tối thiểu và kiểm thử đầu ra sau sanitize.

Nếu sản phẩm chỉ cần văn bản, không cần sanitizer: hiển thị bằng text node/textContent và encode đúng context.

## 6. Kiểm thử URL và attribute lồng nhau

Một URL được đặt trong HTML attribute đi qua **hai lớp**:

1. Kiểm tra URL có scheme/host được phép.
2. Encode giá trị URL khi đưa vào HTML attribute.

Ví dụ:

```js
function allowedLink(raw) {
  let url;
  try {
    url = new URL(raw, 'https://app.example.test');
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  if (url.origin !== 'https://app.example.test') return null;
  return url.href;
}
```

Sau đó render:

```js
const href = allowedLink(userSuppliedUrl);
if (href !== null) {
  linkElement.setAttribute('href', href);
  linkElement.textContent = 'Mở liên kết';
} else {
  linkElement.removeAttribute('href');
}
```

Trong ví dụ DOM này, setAttribute nhận giá trị đã parse và kiểm tra; textContent hiển thị label như text. Nếu render bằng chuỗi HTML, cần HTML-attribute encode URL đã được kiểm tra. Không dùng encodeURIComponent trên cả URL hoàn chỉnh vì sẽ encode delimiter và làm hỏng cấu trúc.

Kiểm thử các trường hợp:

- URL tương đối trong ứng dụng.
- URL HTTPS hợp lệ thuộc allowlist.
- URL HTTP nếu policy không cho phép.
- Scheme javascript: và data:.
- URL có userinfo như https://trusted.example@attacker.test/.
- Host giả dạng bằng suffix như app.example.test.attacker.test.
- Dấu quote, ampersand và Unicode trong query string.

## 7. Kiểm thử DOM sink và framework

### 7.1. DOM API ưu tiên

Khi chỉ cần hiển thị dữ liệu:

```js
const message = new URLSearchParams(location.search).get('message') || '';
document.querySelector('#message').textContent = message;
```

Các sink cần rà soát kỹ:

- innerHTML, outerHTML, insertAdjacentHTML.
- document.write.
- eval, Function, setTimeout/setInterval nhận chuỗi mã.
- Thuộc tính event handler như onclick được tạo từ chuỗi.
- href, src, action, formaction nhận URL không được kiểm tra.
- CSS text hoặc style declaration được ghép từ dữ liệu.

Không phải mọi lời gọi setAttribute đều an toàn. Tên attribute, loại attribute và giá trị vẫn cần kiểm tra; đặc biệt với event handler và URL-bearing attributes.

### 7.2. Kiểm thử auto-escaping của template engine

Với template engine, xác minh:

1. Biểu thức thông thường có auto-escape trong đúng context không?
2. Có helper raw/safe nào tắt escape không?
3. HTML attribute có được quote và encode đúng không?
4. Dữ liệu đưa vào script/style block có serializer chuyên dụng không?
5. Khi template được render qua partial/component khác, context có bị thay đổi không?

Template engine có thể auto-escape HTML text nhưng vẫn không đảm bảo URL trong href an toàn về scheme. Auto-escape là lớp hữu ích, không thay URL validation hoặc kiểm thử DOM sink.

### 7.3. Trusted Types và CSP là defense-in-depth

**Trusted Types** giúp kiểm soát việc đưa chuỗi vào một số DOM sink nguy hiểm trên browser hỗ trợ. Có thể bật chế độ bắt buộc qua CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'
```

Khi triển khai, ứng dụng cần policy Trusted Types có kiểm soát và refactor các sink hợp lệ. Không tạo policy mặc định nhận mọi chuỗi rồi gọi createHTML mà không sanitize.

**Content Security Policy (CSP)** với nonce/hash và hạn chế nguồn script giúp giảm hậu quả XSS, nhưng không thay output encoding. Một payload có thể vẫn tạo markup nguy hiểm dù CSP vô tình chặn việc thực thi trong một browser cụ thể; lỗi encoding vẫn cần được sửa.

Trong kiểm thử, xác minh:

- CSP có được gửi dưới dạng HTTP response header không?
- Console có violation report khi thử payload không?
- Script inline hợp lệ có nonce/hash phù hợp không?
- Có unsafe-inline hoặc unsafe-eval làm suy yếu policy không?
- Trusted Types có chặn sink không được phép hay policy đang cho qua mọi chuỗi?

## 8. Thực hành: lab output encoding với Node.js

Bài lab tạo trang hiển thị query parameter trong HTML text và attribute. Server dùng hàm HTML escape cho hai context và kiểm tra URL trước khi tạo liên kết. Ta dùng Node.js built-in, không cần package ngoài.

### Bước 1 — Tạo file output-encoding-lab.cjs

```js
const http = require('node:http');

function escapeHtml(value) {
  const replacements = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return String(value).replace(/[&<>"']/g, (char) => replacements[char]);
}

function allowedLink(raw) {
  let url;
  try {
    url = new URL(raw, 'http://localhost:3000');
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  if (url.origin !== 'http://localhost:3000') return null;
  return url.href;
}

function pageFor(query, rawLink) {
  const safeQuery = escapeHtml(query);
  const safeLink = allowedLink(rawLink);
  const linkMarkup = safeLink
    ? '<a id="user-link" href="' + escapeHtml(safeLink) +
      '" rel="noopener">Mở URL nội bộ đã kiểm tra</a>'
    : '<span id="link-rejected">URL bị từ chối</span>';

  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<title>Output encoding lab</title></head><body>',
    '<h1>Kiểm thử output encoding</h1>',
    '<form action="/render" method="GET">',
    '<label>Query <input name="q" value="' + safeQuery + '"></label>',
    '<label>URL <input name="link" value="' + escapeHtml(rawLink) + '"></label>',
    '<button type="submit">Render</button></form>',
    '<h2>HTML text context</h2>',
    '<p id="result">' + safeQuery + '</p>',
    '<h2>HTML attribute context</h2>',
    '<p id="attribute-value" data-value="' + safeQuery + '">Attribute đã được quote và escape</p>',
    '<h2>URL context</h2>',
    linkMarkup,
    '</body></html>',
  ].join('\n');
}

if (require.main === module) {
  http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost:3000');
    if (url.pathname !== '/' && url.pathname !== '/render') {
      res.writeHead(404);
      return res.end('Not found');
    }
    const query = url.searchParams.get('q') || '';
    const rawLink = url.searchParams.get('link') || '/';
    const html = pageFor(query, rawLink);
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    });
    res.end(html);
  }).listen(3000, () => {
    console.log('Mở http://localhost:3000');
  });
}

module.exports = { escapeHtml, allowedLink, pageFor };
```

Chạy:

```sh
node output-encoding-lab.cjs
```

Mở trang tại localhost port 3000, bật Developer Tools → Elements, Console và Network.

### Bước 2 — Kiểm thử HTML text và attribute

Nhập vào trường Query:

```text
OE-CANARY-2026 <b>bold</b> "double" 'single' & extra
```

Nhấn Render và xác minh:

- Trong phần HTML text, chuỗi thẻ b hiển thị nguyên văn, không tạo node b.
- Giá trị attribute data-value giữ nguyên dữ liệu sau khi browser parse HTML entity.
- Dấu quote không tạo thêm attribute.
- DOM không có phần tử hoặc event handler mới được tạo từ payload.

Tiếp theo thử payload:

```text
"><svg onload="document.documentElement.dataset.oe='executed'"></svg>
```

Trong Elements, kiểm tra phần tử svg có bị tạo thành node ngoài ý muốn không. Trong Console, đọc thuộc tính document.documentElement.dataset.oe. Kết quả mong đợi là undefined. Vì lab escape HTML text và attribute, payload phải hiển thị như dữ liệu. CSP trong lab là lớp bổ sung; không dùng việc CSP chặn event làm bằng chứng duy nhất rằng output encoding đúng.

### Bước 3 — Kiểm thử URL validation

Nhập lần lượt các giá trị sau vào trường URL:

| Giá trị | Kết quả mong đợi |
|---|---|
| /help | Chấp nhận URL nội bộ |
| http://localhost:3000/help | Chấp nhận |
| https://localhost:3000/help | Từ chối vì origin khác scheme |
| javascript:document.documentElement.dataset.oe='executed' | Từ chối |
| data:text/html,<h1>test</h1> | Từ chối |
| http://localhost:3000.evil.test/ | Từ chối |
| http://attacker.test/ | Từ chối |

Lab chỉ cho phép origin chính xác http://localhost:3000. Nếu URL bị từ chối, trang hiển thị thông báo từ chối và không tạo liên kết có href.

### Bước 4 — Kiểm thử tự động bằng Node.js

Tạo file output-encoding.test.cjs cạnh file lab:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const { escapeHtml, allowedLink, pageFor } =
  require('./output-encoding-lab.cjs');

test('escapeHtml encode các ký tự HTML cấu trúc', () => {
  assert.equal(
    escapeHtml("<tag attr=\"x\" data-y='z'>&"),
    '&lt;tag attr=&quot;x&quot; data-y=&#39;z&#39;&gt;&amp;'
  );
});

test('escapeHtml giữ Unicode', () => {
  assert.equal(escapeHtml('Đà Nẵng 😀'), 'Đà Nẵng 😀');
});

test('escapeHtml không tạo markup từ input', () => {
  const output = escapeHtml('<svg onload=x></svg>');
  assert.equal(output, '&lt;svg onload=x&gt;&lt;/svg&gt;');
});

test('allowedLink chỉ nhận origin nội bộ và HTTP(S)', () => {
  assert.equal(allowedLink('/help'), 'http://localhost:3000/help');
  assert.equal(allowedLink('javascript:alert(1)'), null);
  assert.equal(allowedLink('data:text/html,test'), null);
  assert.equal(allowedLink('http://attacker.test/'), null);
  assert.equal(allowedLink('http://localhost:3000.evil.test/'), null);
});

test('pageFor escape dữ liệu trong text và attribute', () => {
  const html = pageFor('<b>marker</b>', '/help');
  assert.match(html, /&lt;b&gt;marker&lt;\/b&gt;/);
  assert.doesNotMatch(html, /<p id="result"><b>marker<\/b><\/p>/);
});

test('pageFor không render href khi URL không hợp lệ', () => {
  const html = pageFor('hello', 'javascript:alert(1)');
  assert.match(html, /id="link-rejected"/);
  assert.doesNotMatch(html, /href="javascript:/i);
});
```

Chạy test:

```sh
node --test output-encoding.test.cjs
```

Các unit test xác minh hàm escape và URL allowlist. Chúng **không thay thế browser test**: HTML parser, attribute parsing, script context, CSS và DOM API phải được kiểm tra trong môi trường browser.

## 9. Chẩn đoán lỗi output encoding

Khi một payload hiển thị sai hoặc tạo DOM ngoài ý muốn:

1. **Xác định dữ liệu nguồn:** query, form, database, API hay dữ liệu được JavaScript tạo?
2. **Tìm sink cuối:** HTML text, attribute, URL, script, style, innerHTML hay API DOM khác?
3. **Kiểm tra đúng encoder:** hàm hiện tại có được thiết kế cho context đó không?
4. **Kiểm tra thời điểm encode:** có decode hoặc ghép chuỗi sau khi encode không? Có encode trước khi lưu rồi encode lần nữa khi render không?
5. **Kiểm tra parser thực tế:** dùng Elements/DOM, không chỉ nhìn View Source hoặc chuỗi response.
6. **Kiểm tra mọi renderer:** SSR, hydration, component, partial, dashboard quản trị và trang xem lại dữ liệu đã lưu.
7. **Kiểm tra defense-in-depth:** CSP/Trusted Types có đang che một lỗi encoding không? Vẫn sửa sink ngay cả khi CSP chặn payload.
8. **Tạo regression test:** giữ lại input gây lỗi dưới dạng test case không phá hoại để ngăn lỗi quay lại.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Dấu nhỏ hơn hiển thị thành &lt; | Double encoding hoặc dữ liệu đã được encode trước khi lưu | Lưu dữ liệu gốc, encode tại output đúng context |
| Dấu quote làm vỡ attribute | Attribute không quote hoặc encoder thiếu quote | Quote attribute và encode dấu nháy |
| Scheme javascript xuất hiện trong href | Chỉ HTML-escape mà không validate URL scheme | Parse URL, allowlist scheme/host rồi attribute-encode |
| HTML text an toàn nhưng innerHTML vẫn tạo node | Dùng HTML sink cho dữ liệu text | Dùng textContent; nếu cần rich HTML thì sanitize |
| CSP chặn payload nhưng markup lạ vẫn xuất hiện | Encoding sai, CSP chỉ chặn một số hành vi thực thi | Sửa output encoding và kiểm tra DOM |
| SSR an toàn nhưng nội dung đổi sau hydration | Client-side code dùng sink khác hoặc bỏ auto-escape | Kiểm tra DOM sink trong client bundle |
| Chỉ một số trang bị XSS | Có helper raw/safe hoặc renderer khác nhau | Tìm toàn bộ sink và thống nhất policy |
| Unicode bị lỗi hoặc mất ký tự | Encoding/decoding không nhất quán | Dùng UTF-8 xuyên suốt và test Unicode |

## 10. Checklist kiểm thử

Trước khi kết luận một luồng output an toàn, xác minh:

- [ ] Đã xác định mọi nguồn dữ liệu không tin cậy.
- [ ] Đã xác định context cuối cùng của từng sink.
- [ ] HTML text và attribute được encode riêng theo đúng context.
- [ ] Attribute luôn có dấu quote; không có event handler từ dữ liệu.
- [ ] URL được parse và kiểm tra scheme/host trước khi render.
- [ ] JavaScript không nội suy trực tiếp dữ liệu vào code inline.
- [ ] CSS không ghép từ chuỗi tùy ý; giá trị được allowlist.
- [ ] DOM text dùng textContent; innerHTML có lý do và sanitizer rõ ràng nếu cần.
- [ ] Đã kiểm tra auto-escape bypass và helper raw/safe.
- [ ] Không decode hoặc encode lặp làm thay đổi ý nghĩa dữ liệu.
- [ ] Browser DOM không có node/attribute ngoài ý muốn và canary không thực thi.
- [ ] CSP/Trusted Types được dùng như defense-in-depth, không thay output encoding.
- [ ] Có regression test cho payload và context đã kiểm thử.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao không thể dùng một hàm encode duy nhất cho HTML, URL, JavaScript và CSS?  
**Trả lời:** Mỗi context có cú pháp và delimiter khác nhau. Encoder đúng cho HTML text không đảm bảo an toàn cho URL scheme, JavaScript string hoặc CSS declaration.

**2.** Trong HTML text node, ký tự nào tối thiểu phải encode để không tạo markup?  
**Trả lời:** Ampersand, dấu nhỏ hơn và dấu lớn hơn; khi dùng helper cho attribute cần xử lý thêm dấu quote.

**3.** Vì sao attribute phải được quote ngay cả khi đã encode?  
**Trả lời:** Quote tạo ranh giới rõ ràng cho giá trị; encoding bổ sung ngăn dữ liệu thoát khỏi ranh giới đó.

**4.** HTML-attribute encoding có làm scheme javascript trong href an toàn không?  
**Trả lời:** Không. Phải parse URL và allowlist scheme/host; sau đó mới encode giá trị cho attribute.

**5.** Vì sao JSON.stringify một chuỗi chưa chắc đủ an toàn khi chèn vào script block?  
**Trả lời:** HTML parser nhận diện dấu đóng script trước JavaScript parser, nên chuỗi có thể kết thúc script element. Tốt hơn là truyền JSON riêng hoặc dùng serializer an toàn cho script context.

**6.** Khi nào cần HTML sanitization thay vì output encoding?  
**Trả lời:** Khi sản phẩm thật sự cần cho phép một tập HTML/rich text. Nếu chỉ hiển thị văn bản, dùng text node và output encoding.

**7.** CSP chặn event handler độc hại có chứng minh output encoding đúng không?  
**Trả lời:** Không. CSP là lớp giảm thiểu bổ sung; markup vẫn có thể bị tạo sai context và lỗi encoding vẫn cần sửa.

**8.** Vì sao không nên lưu chuỗi đã HTML-escaped vào database?  
**Trả lời:** Dữ liệu có thể được render ở context khác hoặc bị encode lần nữa. Nên lưu dữ liệu gốc đã validate theo nghiệp vụ và encode tại điểm output.

**9.** Kiểm thử unit cho hàm escape có đủ xác nhận ứng dụng không có XSS không?  
**Trả lời:** Không. Cần kiểm tra sink thực tế, HTML parser, DOM sau render, client-side code và mọi đường đi dữ liệu.

## Tổng kết

Kiểm thử output encoding phải bắt đầu bằng việc xác định **dữ liệu không tin cậy đi vào context nào**. Dùng HTML encoding cho text/attribute, URL parser và allowlist cho URL, tránh nội suy JavaScript/CSS, ưu tiên DOM API an toàn và kiểm tra kết quả trong browser. Unit test giúp giữ đúng hành vi của helper, còn browser test xác minh parser và sink thực tế. CSP, Trusted Types và sanitization có vai trò riêng; chúng bổ sung cho output encoding, không thay thế việc encode đúng context tại mọi điểm render.
