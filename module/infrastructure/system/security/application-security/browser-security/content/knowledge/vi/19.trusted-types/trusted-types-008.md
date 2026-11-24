# Kiểm thử Trusted Types

> **Chương:** Trusted Types  
> **Chủ đề:** Kiểm thử Trusted Types  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Trusted Types bảo vệ các DOM injection sink như `innerHTML` bằng cách nào.
2. Phân biệt `TrustedHTML`, `TrustedScript` và `TrustedScriptURL`.
3. Kiểm tra policy được tạo, được CSP cho phép và xử lý dữ liệu không tin cậy đúng cách.
4. Triển khai theo từng giai đoạn: kiểm kê sink, Report-Only, sửa code và enforce.
5. Phát hiện default policy quá rộng, policy bypass, policy trùng tên và thư viện bên thứ ba chưa tương thích.
6. Kiểm chứng hành vi trong browser và đọc CSP violation report để đánh giá kết quả triển khai.

## 1. Trusted Types giải quyết vấn đề gì?

Nhiều lỗ hổng DOM-based XSS xuất hiện khi JavaScript đưa chuỗi không tin cậy vào một API có thể được browser phân tích thành HTML, JavaScript hoặc URL script. Ví dụ:

```js
const value = new URLSearchParams(location.search).get('message') || '';
document.querySelector('#result').innerHTML = value;
```

Nếu `value` chứa markup hoặc event handler, `innerHTML` có thể tạo DOM ngoài ý muốn. Việc kiểm tra chuỗi bằng vài biểu thức chính quy không đủ để bảo đảm an toàn cho mọi cấu trúc HTML.

**Trusted Types** là một cơ chế của browser giúp kiểm soát những sink nhạy cảm này. Khi ứng dụng bật CSP directive:

```http
Content-Security-Policy: require-trusted-types-for 'script'
```

Các sink được hỗ trợ sẽ yêu cầu giá trị có kiểu Trusted Types tương ứng thay vì chấp nhận chuỗi tùy ý. Ứng dụng phải tạo giá trị qua một `TrustedTypePolicy` có tên rõ ràng và xử lý dữ liệu trước khi chuyển nó vào sink.

Trusted Types tạo một ranh giới kiểm soát trong code: nơi nào tạo HTML/script/URL script phải đi qua policy được ứng dụng cho phép. Cơ chế này giúp phát hiện và hạn chế việc vô tình đưa chuỗi không tin cậy vào sink nguy hiểm.

**Trusted Types không tự sanitize dữ liệu.** Policy do ứng dụng viết quyết định nội dung được chấp nhận. Nếu policy trả nguyên chuỗi không tin cậy, ứng dụng vẫn có thể có XSS dù sink nhận một đối tượng `TrustedHTML`.

## 2. Ba kiểu dữ liệu Trusted Types

| Kiểu | Dùng cho | Ví dụ sink tiêu biểu |
|---|---|---|
| `TrustedHTML` | Markup HTML đã được policy xử lý | `innerHTML`, `outerHTML`, `insertAdjacentHTML` |
| `TrustedScript` | Script được tạo có kiểm soát | Một số sink nhận script như `eval` hoặc script text |
| `TrustedScriptURL` | URL dùng để tải script | `HTMLScriptElement.src` |

Đây là các kiểu khác nhau, không thể thay thế tùy ý cho nhau. Một giá trị `TrustedHTML` không phải là `TrustedScriptURL`; policy cho HTML không nên được dùng để cấp quyền tải script.

### 2.1. TrustedHTML

`TrustedHTML` biểu diễn HTML mà ứng dụng đã đưa qua policy:

```js
const htmlPolicy = trustedTypes.createPolicy('app-html', {
  createHTML(input) {
    return sanitizeWithApprovedLibrary(input);
  },
});

target.innerHTML = htmlPolicy.createHTML(untrustedMarkup);
```

`sanitizeWithApprovedLibrary` ở đây đại diện cho một sanitizer HTML đã được lựa chọn, cấu hình allowlist và kiểm thử. Trusted Types không cung cấp sẵn hàm sanitize HTML và không tự loại bỏ thẻ hoặc thuộc tính nguy hiểm.

Nếu ứng dụng chỉ cần hiển thị văn bản, không cần tạo HTML. Dùng `textContent` sẽ đơn giản hơn:

```js
target.textContent = untrustedText;
```

### 2.2. TrustedScriptURL

`TrustedScriptURL` dành cho URL được dùng để tải script. Policy nên giới hạn chính xác nguồn script:

```js
const allowedScriptPaths = new Set(['/assets/app.js']);

const scriptUrlPolicy = trustedTypes.createPolicy('app-script-url', {
  createScriptURL(input) {
    const url = new URL(input, location.origin);
    if (url.origin !== location.origin ||
        !allowedScriptPaths.has(url.pathname)) {
      throw new TypeError('Script URL không được cho phép');
    }
    return url.href;
  },
});

const script = document.createElement('script');
script.src = scriptUrlPolicy.createScriptURL('/assets/app.js');
document.head.append(script);
```

Không tạo policy trả lại URL bất kỳ do người dùng cung cấp. `TrustedScriptURL` là một quyết định tin cậy về nguồn mã sẽ được tải; hãy dùng allowlist hẹp và CSP `script-src` làm lớp kiểm soát bổ sung.

### 2.3. TrustedScript

`TrustedScript` dành cho một số sink nhận JavaScript dưới dạng chuỗi. Trong ứng dụng thông thường, nên tránh tạo mã JavaScript từ dữ liệu động và loại bỏ các API như `eval()` hoặc `Function()` nếu không có yêu cầu thiết kế rất rõ.

Trusted Types không biến việc thực thi code động thành một thực hành an toàn. Nếu bắt buộc dùng, policy phải chỉ tạo script từ logic cố định do ứng dụng kiểm soát; không chuyển input người dùng thành script đáng tin cậy.

## 3. Policy là ranh giới tin cậy của ứng dụng

Policy được tạo qua `trustedTypes.createPolicy(name, rules)`:

```js
const policy = trustedTypes.createPolicy('app-html', {
  createHTML(input) {
    return sanitizeHtml(input);
  },
  createScriptURL(input) {
    return validateScriptUrl(input);
  },
});
```

Các hàm `createHTML`, `createScript` và `createScriptURL` là nơi ứng dụng xác định cách chuyển dữ liệu đầu vào thành giá trị Trusted Types. Không phải policy nào cũng cần cả ba hàm; chỉ định nghĩa những loại ứng dụng thực sự dùng.

Một policy tốt cần:

- Có tên mô tả mục đích, ví dụ `app-html` hoặc `app-script-url`.
- Chỉ tạo kiểu mà policy sở hữu; không dùng một policy tổng quát cho mọi sink.
- Xử lý dữ liệu bằng sanitizer hoặc allowlist phù hợp với loại dữ liệu.
- Từ chối đầu vào không hợp lệ thay vì tự đoán ý định.
- Có unit test và browser test cho các trường hợp hợp lệ/không hợp lệ.
- Hạn chế số nơi trong code được phép gọi `createPolicy`.

Mặc định, browser không cho tạo nhiều policy trùng tên trong cùng document. Nếu CSP chủ động cho phép từ khóa `'allow-duplicates'` trong directive `trusted-types`, giới hạn này có thể được nới lỏng; tránh bật ngoại lệ đó nếu không có nhu cầu tương thích cụ thể. Kiểm thử nên xác minh policy name chỉ được khởi tạo tại module dự kiến và không bị thư viện khác chiếm trước.

### 3.1. Trusted Types không phải sanitizer

Đoạn sau vẫn nguy hiểm:

```js
const unsafePolicy = trustedTypes.createPolicy('unsafe-html', {
  createHTML(input) {
    return input;
  },
});

target.innerHTML = unsafePolicy.createHTML(untrustedInput);
```

Sink không còn nhận chuỗi thô, nhưng policy đã cấp nhãn tin cậy cho nội dung không được làm sạch. Đây là lỗi thiết kế policy. Trong review, cần đọc implementation của từng policy, không chỉ tìm xem ứng dụng có gọi `createPolicy` hay không.

### 3.2. Tách policy theo mục đích

Không nên có một policy `default` hoặc `app` làm mọi việc:

- Policy HTML có thể sanitize rich text theo allowlist phần tử và thuộc tính.
- Policy URL script chỉ chấp nhận đường dẫn asset cố định.
- Policy script, nếu thực sự cần, chỉ tạo code cố định do ứng dụng sở hữu.

Tách policy giúp reviewer biết vì sao một giá trị được tin cậy và giảm khả năng một hàm tiện ích rộng cấp quyền quá mức.

## 4. CSP điều khiển Trusted Types

Hai CSP directive quan trọng:

```http
Content-Security-Policy:
  require-trusted-types-for 'script';
  trusted-types app-html app-script-url;
```

- `require-trusted-types-for 'script'` bật kiểm tra Trusted Types cho các injection sink được browser hỗ trợ.
- `trusted-types app-html app-script-url` giới hạn tên policy được phép tạo trong document.

Nếu không khai báo `trusted-types`, chính sách không giới hạn tên policy bởi directive này. Trong production, nên liệt kê chính xác policy name cần thiết. Có thể dùng `trusted-types 'none'` khi muốn cấm tạo policy, nhưng khi đó ứng dụng không thể tạo các giá trị Trusted Types qua policy.

### 4.1. Enforce và Report-Only

**Enforce** chặn việc đưa chuỗi không phải Trusted Types vào sink được bảo vệ:

```http
Content-Security-Policy:
  require-trusted-types-for 'script';
  trusted-types app-html app-script-url;
```

**Report-Only** ghi nhận vi phạm nhưng không chặn thao tác:

```http
Content-Security-Policy-Report-Only:
  require-trusted-types-for 'script';
  trusted-types app-html app-script-url;
  report-uri /csp-report;
```

Report-Only phù hợp để kiểm kê sink và tìm code path chưa được migrate trước khi bật enforcement. Nó không phải chế độ bảo vệ cuối cùng: request và thao tác DOM vi phạm vẫn có thể tiếp tục.

### 4.2. Default policy

Một policy tên `default` có hành vi đặc biệt: khi code truyền chuỗi thường vào một sink được bảo vệ, browser có thể gọi default policy để chuyển chuỗi đó thành Trusted Types. Nếu dùng policy này, tên `default` cũng phải được CSP cho phép trong directive `trusted-types`. Cơ chế này hữu ích trong một số giai đoạn migrate, nhưng cũng có thể che giấu những call site chưa được sửa.

Tránh default policy kiểu:

```js
trustedTypes.createPolicy('default', {
  createHTML(input) {
    return input;
  },
});
```

Policy trên biến mọi chuỗi thành HTML được tin cậy mà không xử lý gì. Nó làm mất mục tiêu của Trusted Types. Nếu cần default policy tạm thời, policy phải áp dụng xử lý an toàn, ghi nhận call site và có kế hoạch loại bỏ sau migration.

### 4.3. CSP cần được gửi từ server

Trong production, phát CSP dưới dạng HTTP response header để áp dụng nhất quán cho document. Không dựa vào một thẻ meta được chèn muộn trong HTML để thay thế header cho toàn bộ policy. Khi có nhiều CSP policy cùng áp dụng, browser kết hợp chúng theo hướng giới hạn hơn; thêm một policy không nới lỏng policy đang có.

## 5. Quy trình kiểm thử Trusted Types

Kiểm thử nên diễn ra theo từng giai đoạn. Mục tiêu là tìm đủ sink và policy chưa phù hợp trước khi bật enforcement rộng.

### Bước 1 — Kiểm kê injection sink

Tìm trong source code và dependency các API có thể đưa dữ liệu vào parser hoặc script:

- HTML: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`.
- Fragment/parser: `Range.createContextualFragment`, `DOMParser.parseFromString` với MIME type HTML ở browser hỗ trợ.
- Script: `eval`, `Function` và các sink nhận script string.
- Script URL: `HTMLScriptElement.src` và các API tải script động.
- Framework wrapper hoặc helper có thể gọi những API trên ở bên trong.

Danh sách sink được bảo vệ phụ thuộc browser và phiên bản. Dùng tài liệu tương thích của browser mục tiêu và quan sát violation thực tế; không coi danh sách trên là toàn bộ API có thể liên quan.

### Bước 2 — Ghi nhận luồng dữ liệu

Với mỗi sink, ghi:

1. Dữ liệu đến từ URL, form, API, database hay thư viện bên thứ ba?
2. Call site nào tạo hoặc thay đổi dữ liệu?
3. Có thể dùng `textContent` hoặc DOM API an toàn hơn không?
4. Nếu cần HTML, sanitizer nào xử lý và allowlist gồm những gì?
5. Policy nào được phép tạo Trusted Types và policy đó có test không?

Ưu tiên xóa sink không cần thiết trước khi viết policy. Ví dụ nội dung chỉ cần hiển thị văn bản thì thay `innerHTML` bằng `textContent`, không cần tạo `TrustedHTML`.

### Bước 3 — Chạy Report-Only

Triển khai header Report-Only trên môi trường test hoặc một nhóm traffic có kiểm soát. Dùng DevTools Console và CSP reports để tìm:

- Sink đang nhận chuỗi thô.
- Route hoặc thao tác UI kích hoạt sink.
- Thư viện bên thứ ba tạo HTML động.
- Policy name không nằm trong allowlist.
- Code path hiếm gặp chỉ chạy trong trang quản trị, editor hoặc luồng đăng nhập.

Ghi nhận route, loại sink, call stack nếu browser cung cấp và phiên bản ứng dụng. Không đưa nguyên nội dung nhạy cảm hoặc dữ liệu người dùng vào log report.

### Bước 4 — Sửa code và tạo policy tối thiểu

Với từng vi phạm:

- Dùng `textContent` nếu mục tiêu là hiển thị text.
- Với rich text, dùng sanitizer được duy trì và cấu hình allowlist tối thiểu.
- Tạo policy theo đúng mục đích, không dùng policy trả nguyên input.
- Với script URL, allowlist origin/path cụ thể; không nhận URL tùy ý.
- Cập nhật hoặc thay dependency đang gọi sink không an toàn.
- Thêm test cho đầu vào hợp lệ, input độc hại, input sai định dạng và trường hợp rỗng.

### Bước 5 — Enforce trên môi trường staging

Bật `require-trusted-types-for 'script'` cùng danh sách policy name chính xác. Chạy regression trên toàn bộ route và workflow. Một assignment chuỗi thô vào sink phải bị chặn và phát sinh lỗi/report; assignment bằng đối tượng Trusted Types do policy hợp lệ tạo ra phải hoạt động.

Chỉ chuyển sang production sau khi các luồng quan trọng đã được kiểm thử và vi phạm còn lại đã được giải quyết hoặc có quyết định xử lý rõ ràng.

## 6. Các phép thử cần có

| Phép thử | Kết quả mong đợi khi enforce |
|---|---|
| Gán chuỗi thường vào `innerHTML` | Browser từ chối, thường phát sinh TypeError và CSP violation |
| Gán `TrustedHTML` từ policy được phép | Sink chấp nhận giá trị |
| Tạo policy name không nằm trong CSP `trusted-types` | Browser từ chối tạo policy |
| Tạo policy trùng tên lần thứ hai | Browser từ chối theo mặc định; chỉ cho phép nếu CSP chủ động bật `'allow-duplicates'` |
| Policy sanitize đầu vào chứa markup không cho phép | Kết quả chỉ còn nội dung theo allowlist |
| Policy trả nguyên input không tin cậy | Test bảo mật phải thất bại vì policy không an toàn, dù sink chấp nhận |
| Gán `TrustedHTML` vào sink cần `TrustedScriptURL` | Không được chấp nhận như kiểu tương ứng |
| Dùng script URL ngoài allowlist | Policy từ chối trước khi gán vào `script.src` |
| Thư viện bên thứ ba gán chuỗi thô vào sink | Vi phạm được phát hiện; cần sửa, cấu hình hoặc thay thư viện |
| Browser không hỗ trợ Trusted Types | Feature detection nhận biết; CSP directive có thể không được thực thi bởi browser đó |

Không chỉ test trường hợp chặn. Cũng phải xác minh nội dung hợp lệ vẫn hoạt động, rich text đúng allowlist vẫn hiển thị và workflow không bị lỗi do enforcement.

## 7. Đọc CSP violation và chẩn đoán

Khi một sink bị chặn, Console thường cho biết Trusted Types requirement hoặc policy violation. CSP report có thể cung cấp loại directive, document URI, blocked URI và vị trí vi phạm tùy browser.

Khi chẩn đoán:

1. Xác định document và route phát sinh violation.
2. Tìm call stack hoặc source location trong DevTools.
3. Xác định sink thực tế; không chỉ sửa dòng cuối nếu dữ liệu được tạo sai từ trước.
4. Kiểm tra policy name có được CSP cho phép không.
5. Đọc policy implementation: có sanitizer/allowlist không, hay chỉ trả input?
6. Kiểm tra dependency hoặc framework wrapper có gọi sink gián tiếp không.
7. Xác nhận violation có đến từ code production, extension hoặc browser tooling trong môi trường test không.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| innerHTML ném TypeError | Gán chuỗi thường khi enforcement bật | Tìm call site, chuyển sang textContent hoặc policy HTML phù hợp |
| createPolicy bị từ chối | Tên policy không được CSP allowlist hoặc policy cùng tên đã tồn tại | Kiểm tra directive trusted-types và chỗ khởi tạo policy |
| Report-Only có violation nhưng giao diện vẫn chạy | Report-Only ghi nhận mà không chặn | Sửa các sink rồi bật enforcement ở staging |
| Enforce làm hỏng editor/rich text | Dependency tạo HTML bằng chuỗi thô | Nâng cấp/cấu hình dependency và tích hợp sanitizer/policy |
| Không có violation dù code có sink nguy hiểm | Chưa bật directive, browser không hỗ trợ hoặc đường code chưa chạy | Xác minh response header, browser support và test workflow |
| TrustedHTML vẫn chứa payload nguy hiểm | Policy cấp nhãn mà không sanitize | Sửa policy; Trusted Types không tự làm sạch HTML |
| Default policy khiến app vẫn nhận chuỗi | Default policy tự chuyển chuỗi tại sink | Gỡ policy rộng, ghi nhận call site và migrate tường minh |

## 8. Thực hành: lab Trusted Types với Node.js

Lab này tạo một trang local có hai chế độ:

- `mode=report`: CSP Report-Only ghi nhận việc gán chuỗi thô vào `innerHTML` nhưng vẫn cho phép thao tác.
- `mode=enforce`: CSP bắt buộc Trusted Types và chặn việc gán chuỗi thô.

Trang có một policy `app-text` chỉ chuyển input thành HTML-escaped text. Vì policy chỉ cho phép hiển thị văn bản, nó không cố giữ markup rich text.

### Bước 1 — Tạo file `trusted-types-lab.cjs`

```js
const http = require('node:http');
const crypto = require('node:crypto');

function page(mode, nonce) {
  const script = [
    "const mode = " + JSON.stringify(mode) + ";",
    "const input = document.querySelector('#input');",
    "const output = document.querySelector('#output');",
    "const status = document.querySelector('#status');",
    "function escapeHtml(value) {",
    "  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;',",
    "    '\"': '&quot;', \"'\": '&#39;' };",
    "  return String(value).replace(/[&<>\"']/g, (ch) => map[ch]);",
    "}",
    "let textPolicy = null;",
    "if (window.trustedTypes) {",
    "  textPolicy = trustedTypes.createPolicy('app-text', {",
    "    createHTML(value) { return escapeHtml(value); }",
    "  });",
    "}",
    "document.querySelector('#safe').addEventListener('click', () => {",
    "  const safeValue = textPolicy ? textPolicy.createHTML(input.value)",
    "    : escapeHtml(input.value);",
    "  output.innerHTML = safeValue;",
    "  status.textContent = 'Đã render qua policy app-text';",
    "});",
    "document.querySelector('#raw').addEventListener('click', () => {",
    "  try {",
    "    output.innerHTML = input.value;",
    "    status.textContent = 'Raw assignment đã chạy; xem Console/Report';",
    "  } catch (error) {",
    "    status.textContent = error.name + ': ' + error.message;",
    "  }",
    "});",
    "document.querySelector('#mode').textContent = 'CSP mode: ' + mode;",
    "document.querySelector('#support').textContent =",
    "  window.trustedTypes ? 'Trusted Types API: supported' : 'Trusted Types API: unavailable';"
  ].join('\n');

  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<title>Trusted Types lab</title></head><body>',
    '<h1>Kiểm thử Trusted Types</h1>',
    '<p id="mode"></p><p id="support"></p>',
    '<label>Input <textarea id="input"><b>canary</b></textarea></label>',
    '<p><button id="safe" type="button">Render qua policy an toàn</button>',
    '<button id="raw" type="button">Thử raw innerHTML</button></p>',
    '<p id="status"></p><div id="output"></div>',
    '<script nonce="' + nonce + '">' + script + '</script>',
    '</body></html>'
  ].join('\n');
}

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method === 'POST' && url.pathname === '/csp-report') {
    let size = 0;
    req.on('data', (chunk) => { size += chunk.length; });
    req.on('end', () => {
      console.log('CSP report received; bytes=' + size);
      res.writeHead(204);
      res.end();
    });
    return;
  }

  if (url.pathname !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  const mode = url.searchParams.get('mode') === 'enforce'
    ? 'enforce' : 'report';
  const nonce = crypto.randomBytes(18).toString('base64');
  const basePolicy =
    "default-src 'none'; script-src 'nonce-" + nonce +
    "'; style-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'";
  const trustedPolicy =
    "require-trusted-types-for 'script'; trusted-types app-text; report-uri /csp-report";

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');

  if (mode === 'enforce') {
    res.setHeader('Content-Security-Policy', basePolicy + '; ' + trustedPolicy);
  } else {
    res.setHeader('Content-Security-Policy', basePolicy);
    res.setHeader('Content-Security-Policy-Report-Only', trustedPolicy);
  }

  res.end(page(mode, nonce));
}).listen(3000, () => {
  console.log('Report-Only: http://localhost:3000/?mode=report');
  console.log('Enforce:     http://localhost:3000/?mode=enforce');
});
```

Chạy:

```sh
node trusted-types-lab.cjs
```

Mở trang bằng browser có hỗ trợ Trusted Types, bật DevTools → Console và Network. Lab dùng nonce mới cho mỗi response và không tải script từ nguồn bên ngoài.

### Bước 2 — Kiểm tra Report-Only

Mở `http://localhost:3000/?mode=report`.

1. Nhập `Hello <b>Trusted Types</b>` vào textarea.
2. Nhấn **Render qua policy an toàn**. Nội dung phải hiển thị như text; thẻ b không trở thành element.
3. Nhấn **Thử raw innerHTML**. Ở chế độ Report-Only, thao tác có thể vẫn chạy, nhưng browser ghi nhận violation trong Console và gửi report tới `/csp-report`.
4. Quan sát terminal có log report nhận được. Report-Only không chặn sink, nên không coi việc giao diện vẫn chạy là test pass cho enforcement.

### Bước 3 — Kiểm tra Enforce

Mở `http://localhost:3000/?mode=enforce`.

1. Nhấn **Render qua policy an toàn**. Policy `app-text` trả về nội dung đã HTML-escape dưới dạng `TrustedHTML`; sink chấp nhận.
2. Nhấn **Thử raw innerHTML**. Browser hỗ trợ Trusted Types phải từ chối chuỗi thường tại sink; trạng thái hiển thị lỗi TypeError hoặc lỗi tương ứng.
3. Mở Console và xác minh thông báo Trusted Types/CSP.
4. Thử nhập chuỗi chứa `<img src=x onerror=...>`; policy text phải hiển thị nguyên văn và không tạo phần tử ảnh.

Kết quả mong đợi là policy được CSP cho phép hoạt động, còn assignment chuỗi thô bị chặn. Nếu browser không hỗ trợ Trusted Types, trang sẽ báo API unavailable; không dùng browser đó để kết luận enforcement đã hoạt động.

### Bước 4 — Thử policy name không được phép

Trong DevTools Console ở trang enforce, thử tạo policy khác:

```js
trustedTypes.createPolicy('unlisted-policy', {
  createHTML(value) { return value; }
});
```

CSP `trusted-types app-text` không cho tạo policy `unlisted-policy`; browser phải từ chối. Phép thử này xác minh allowlist policy name đang có hiệu lực.

Không thêm policy không an toàn vào trang production để “thử cho chạy”. Chỉ thực hiện trong lab local.

### Bước 5 — Đánh giá policy và sink

Mở source lab và trả lời:

- Vì sao `app-text` escape input trước khi trả về `TrustedHTML`?
- Vì sao policy này chỉ phù hợp với nội dung text và không phải sanitizer cho rich text?
- Nếu cần cho phép một số thẻ định dạng, cần thêm bước sanitizer allowlist nào?
- Vì sao raw assignment có thể chạy trong Report-Only nhưng bị chặn trong Enforce?
- Nếu bỏ directive `trusted-types app-text`, policy name nào có thể được tạo?

## 9. Kiểm thử policy cho rich text và script URL

Lab trên chỉ render text. Với ứng dụng rich text, cần dùng sanitizer đã được duy trì và cấu hình rõ các thẻ/attribute được phép. Ví dụ kiến trúc:

```js
const richTextPolicy = trustedTypes.createPolicy('app-rich-text', {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'a'],
      ALLOWED_ATTR: ['href', 'title'],
      RETURN_TRUSTED_TYPE: false,
    });
  },
});

container.innerHTML = richTextPolicy.createHTML(untrustedRichText);
```

Đây là ví dụ tích hợp; cần cấu hình phiên bản DOMPurify hỗ trợ Trusted Types phù hợp với cách ứng dụng dùng policy, đồng thời kiểm tra URL trong thuộc tính href và các trường hợp namespace/parser. Không tự viết sanitizer bằng regex.

Đối với script URL, test cả:

- Đường dẫn asset được allowlist.
- URL cùng host nhưng path không nằm trong allowlist.
- URL ngoài origin.
- Scheme không phải HTTP(S).
- URL có userinfo hoặc hostname giả mạo.
- Redirect phía server có thể dẫn tới nguồn script khác.

TrustedScriptURL policy và CSP `script-src` cần cùng giới hạn nguồn tải script. Không cấp TrustedScriptURL cho URL chỉ vì hostname có chứa tên domain tin cậy.

## 10. Tương thích browser và rollout production

Trusted Types được hỗ trợ không đồng đều giữa browser và phiên bản. Trước khi triển khai:

1. Xác định browser/version trong ma trận hỗ trợ sản phẩm.
2. Feature-detect `window.trustedTypes` trong code cần tương thích.
3. Kiểm thử CSP enforcement trên từng browser mục tiêu.
4. Giữ output encoding, sanitizer và DOM API an toàn làm biện pháp nền tảng; đừng dựa duy nhất vào Trusted Types.
5. Kiểm tra extension, embedded webview và môi trường kiosk nếu sản phẩm hỗ trợ.

Rollout thực tế:

- Bắt đầu bằng inventory và Report-Only.
- Nhóm violation theo route, sink và thư viện.
- Loại bỏ sink không cần thiết; thay bằng textContent/DOM API an toàn.
- Tạo policy có tên và phạm vi nhỏ; thêm unit/browser test.
- Bật enforce trên staging và chạy workflow quan trọng.
- Theo dõi report sau khi phát hành; không thu thập dữ liệu người dùng nhạy cảm trong report.
- Khi policy thay đổi, kiểm thử cả luồng cũ và luồng mới trước khi rollout tiếp.

## 11. Checklist kiểm thử Trusted Types

- [ ] Đã kiểm kê các injection sink và call site.
- [ ] Đã xác định browser/version hỗ trợ trong môi trường triển khai.
- [ ] Đã chạy CSP Report-Only và phân loại violation.
- [ ] Sink chỉ dùng hiển thị text đã chuyển sang textContent khi phù hợp.
- [ ] Policy HTML dùng sanitizer/allowlist đã được kiểm thử.
- [ ] Policy ScriptURL chỉ cho phép asset cụ thể.
- [ ] Không có policy trả nguyên input không tin cậy.
- [ ] Policy name được giới hạn bằng CSP trusted-types.
- [ ] Không dùng default policy rộng để che sink chưa migrate.
- [ ] Enforce chặn assignment chuỗi thô tại sink được bảo vệ.
- [ ] TrustedHTML/TrustedScriptURL đúng kiểu và đúng mục đích.
- [ ] Thư viện bên thứ ba đã được kiểm tra dưới enforcement.
- [ ] CSP report được tiếp nhận mà không ghi dữ liệu nhạy cảm.
- [ ] Có regression test cho input hợp lệ, input xấu và policy bị từ chối.

## 12. Câu hỏi tự kiểm tra

**1.** Trusted Types có tự động sanitize HTML không?  
**Trả lời:** Không. Trusted Types yêu cầu sink nhận giá trị được tạo qua policy; policy phải tự dùng sanitizer hoặc logic allowlist an toàn.

**2.** `require-trusted-types-for 'script'` làm gì?  
**Trả lời:** Bật kiểm tra Trusted Types cho các injection sink được browser hỗ trợ, từ chối chuỗi thường khi enforcement có hiệu lực.

**3.** Directive `trusted-types app-html app-script-url` kiểm soát điều gì?  
**Trả lời:** Giới hạn tên policy mà document được phép tạo.

**4.** Vì sao `TrustedHTML` không thể thay cho `TrustedScriptURL`?  
**Trả lời:** Đây là các kiểu đại diện cho mục đích tin cậy khác nhau: HTML markup và URL tải script.

**5.** Vì sao policy trả nguyên input là nguy hiểm?  
**Trả lời:** Nó cấp nhãn TrustedHTML cho dữ liệu không được xử lý; sink chấp nhận nhưng XSS vẫn có thể xảy ra.

**6.** Report-Only có chặn assignment chuỗi thô không?  
**Trả lời:** Không. Nó ghi nhận violation để quan sát và sửa trước khi enforce.

**7.** Vì sao default policy có thể gây khó khăn khi migration?  
**Trả lời:** Browser tự gọi policy này khi chuỗi thường đi vào sink, khiến call site chưa được sửa có thể tiếp tục chạy và bị che khuất.

**8.** Khi nào nên dùng `textContent` thay vì tạo `TrustedHTML`?  
**Trả lời:** Khi chỉ cần hiển thị văn bản. textContent không yêu cầu HTML parser xử lý chuỗi.

**9.** CSP `script-src` còn cần thiết khi đã bật Trusted Types không?  
**Trả lời:** Có. Trusted Types kiểm soát việc tạo giá trị đưa vào sink; CSP script-src giới hạn nguồn script được tải/thực thi.

**10.** Nếu browser không hỗ trợ Trusted Types thì sao?  
**Trả lời:** Cơ chế này có thể không được thực thi. Ứng dụng vẫn phải dùng output encoding, sanitizer phù hợp và DOM API an toàn trên mọi browser được hỗ trợ.

## Tổng kết

Kiểm thử Trusted Types cần xác minh cả **sink, policy và CSP**. Trước tiên kiểm kê sink, chạy Report-Only để tìm code path, thay các thao tác chỉ hiển thị text bằng `textContent`, rồi tạo policy nhỏ có sanitizer hoặc allowlist phù hợp. Enforce `require-trusted-types-for 'script'` cùng danh sách policy name chính xác và xác minh chuỗi thô bị chặn trong browser mục tiêu. Trusted Types không tự làm sạch dữ liệu; chất lượng bảo vệ phụ thuộc vào policy và các lớp output encoding, sanitizer, CSP được ứng dụng triển khai.
