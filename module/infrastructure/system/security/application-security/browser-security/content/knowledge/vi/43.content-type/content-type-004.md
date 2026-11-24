# nosniff

> **Chương:** Content type  
> **Chủ đề:** nosniff  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích MIME type và lý do browser có thể sniff nội dung response.
2. Mô tả tác dụng của response header X-Content-Type-Options: nosniff.
3. Phân biệt MIME type của HTML, JavaScript, CSS, JSON, ảnh và file tải xuống.
4. Hiểu browser áp dụng strict MIME checking cho script và stylesheet như thế nào.
5. Cấu hình Content-Type và nosniff nhất quán trên server, CDN và object storage.
6. Phục vụ file upload an toàn, tránh để nội dung không tin cậy được diễn giải như active content.
7. Chẩn đoán lỗi MIME type trên DevTools và response headers.
8. Kiểm thử behavior bằng lab local và nhận biết giới hạn của nosniff.

## 1. MIME type là gì?

MIME type mô tả loại dữ liệu của một representation. Trong HTTP response, server thường gửi header Content-Type để browser biết body là HTML, JavaScript, CSS, JSON, ảnh, âm thanh, video hay một định dạng khác.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

<!doctype html>
<html lang="vi">...</html>
```

Một số MIME type thường gặp:

| Nội dung | Content-Type thường dùng |
|---|---|
| HTML | text/html; charset=utf-8 |
| JavaScript | text/javascript |
| CSS | text/css |
| JSON | application/json |
| XML | application/xml hoặc loại XML chuyên biệt |
| Plain text | text/plain; charset=utf-8 |
| PNG | image/png |
| JPEG | image/jpeg |
| SVG | image/svg+xml |
| PDF | application/pdf |
| WebAssembly | application/wasm |
| Binary không xác định | application/octet-stream |

MIME type là metadata do server cung cấp. Browser dùng nó cùng request destination, Fetch/HTML rules và các security checks để quyết định cách xử lý body. Phần mở rộng file không đủ để xác định an toàn nội dung: file có đuôi .jpg vẫn có thể chứa HTML hoặc dữ liệu không đúng định dạng ảnh.

### 1.1. Content-Type của request và response

Hai header có mục đích khác nhau:

- Request Content-Type mô tả định dạng body mà client gửi lên, ví dụ JSON hoặc multipart/form-data.
- Response Content-Type mô tả định dạng body server trả về, ví dụ application/json hoặc text/html.

X-Content-Type-Options: nosniff là response header. Nó hướng dẫn browser không suy đoán một số loại response để xử lý như script hoặc stylesheet khi MIME type không phù hợp. Nó không xác thực MIME type request và không thay thế validation dữ liệu upload ở server.

### 1.2. MIME type phải khớp nội dung thực tế

Nếu server trả JavaScript nhưng khai báo text/plain, browser có thể từ chối thực thi tùy loại request và strict MIME checks. Nếu server trả JSON nhưng khai báo text/html, browser có thể diễn giải body thành HTML khi người dùng điều hướng trực tiếp tới URL.

Luôn đặt Content-Type dựa trên representation thực tế, không chỉ dựa vào tên file hoặc giá trị do client gửi. Với dữ liệu không xác định, application/octet-stream là lựa chọn phù hợp hơn việc đoán thành HTML hoặc JavaScript.

## 2. MIME sniffing là gì?

MIME sniffing là quá trình browser phân tích một phần nội dung response để suy đoán loại dữ liệu khi Content-Type thiếu, không rõ ràng hoặc không phù hợp với ngữ cảnh. Việc sniffing từng giúp tương thích với server cũ vốn gửi MIME type sai hoặc không gửi header.

Tuy nhiên, suy đoán có thể tạo ra ranh giới bảo mật ngoài dự kiến. Một response được ứng dụng nghĩ là plain text hoặc binary có thể bị browser diễn giải như HTML hay script nếu nó được phục vụ trong ngữ cảnh phù hợp.

Ví dụ rủi ro:

1. Người dùng upload file có nội dung HTML nhưng server lưu file dưới tên có vẻ như ảnh hoặc text.
2. Server phục vụ file với Content-Type không chính xác hoặc thiếu.
3. Attacker khiến nạn nhân mở URL file trên cùng origin với ứng dụng.
4. Browser có thể diễn giải nội dung theo cách nguy hiểm nếu MIME handling và các cơ chế khác không chặn.

Tác động cụ thể phụ thuộc browser, MIME type, request destination, cách file được điều hướng và các security controls khác. Không phải mọi response thiếu Content-Type đều tự động thực thi như script.

## 3. X-Content-Type-Options: nosniff

Header này có dạng:

```http
X-Content-Type-Options: nosniff
```

Giá trị nosniff yêu cầu browser không dùng MIME sniffing để biến response có MIME type không phù hợp thành tài nguyên script hoặc stylesheet trong các trường hợp được chuẩn hóa. Nó giúp giảm nguy cơ nội dung không tin cậy bị thực thi chỉ vì browser suy đoán sai loại response.

Đặt header trên response do ứng dụng phục vụ, đặc biệt:

- JavaScript và CSS.
- JSON/API response.
- File upload hoặc nội dung do người dùng cung cấp.
- Trang và endpoint có thể bị điều hướng hoặc nhúng.
- Static assets được phân phối qua CDN hoặc object storage.

Một cấu hình response phổ biến:

```http
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
```

Header cần được gửi trên response thực tế mà browser nhận. Cấu hình tại application server nhưng CDN xóa header, hoặc một route upload trả response không có header, vẫn để lại khoảng trống.

### 3.1. nosniff không phải bộ lọc nội dung tổng quát

nosniff không:

- Kiểm tra file có thực sự là ảnh, PDF hoặc JSON hay không.
- Làm sạch HTML hoặc ngăn XSS trong HTML hợp lệ.
- Chặn mọi navigation tới response có MIME type nguy hiểm.
- Ngăn JavaScript cùng origin đọc response mà nó có quyền truy cập.
- Thay thế CSP, sandbox, CORS, CORP hoặc authorization.
- Thu hồi file đã upload hoặc sửa MIME type sai ở source.

Nếu người dùng điều hướng trực tiếp tới response text/html, browser vẫn render HTML theo Content-Type. nosniff không biến HTML thành text/plain.

### 3.2. Phạm vi strict checking

Các browser hiện đại áp dụng MIME checks chặt cho script và stylesheet. Với response có X-Content-Type-Options: nosniff, browser chặn script/style request khi MIME type không thuộc nhóm phù hợp cho destination đó. JavaScript module luôn có MIME checking nghiêm ngặt theo module script rules; stylesheet cũng có quy tắc MIME riêng.

Chi tiết hành vi có thể khác theo loại request, browser version và tiêu chuẩn được hỗ trợ. Không dựa vào việc một browser cũ có thể sniff rồi thực thi response sai MIME. Hãy khai báo MIME đúng và kiểm tra Console/Network ở các browser mục tiêu.

## 4. nosniff với JavaScript và CSS

### 4.1. JavaScript

JavaScript response cần MIME type JavaScript phù hợp, thường là text/javascript. Ví dụ:

```http
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff
```

Nếu script URL trả text/plain hoặc text/html, browser có thể chặn script do strict MIME checking. Console thường có thông báo MIME type không hợp lệ hoặc strict MIME type checking.

Không phục vụ JavaScript dưới text/plain chỉ vì nội dung là text. Không đặt application/json cho file .js và mong browser tự hiểu đó là script.

### 4.2. CSS

Stylesheet nên được phục vụ với:

```http
Content-Type: text/css; charset=utf-8
X-Content-Type-Options: nosniff
```

Nếu link rel=stylesheet nhận response text/plain, browser có thể từ chối áp dụng stylesheet. Đây là lỗi thường gặp khi static server hoặc CDN gán MIME type dựa trên extension sai.

### 4.3. Script module và import

Module script luôn có strict MIME type checking. Cả entry module và các module được import phải được phục vụ với JavaScript MIME type hợp lệ. Thêm nosniff là defense-in-depth và giúp behavior rõ ràng hơn; nó không thay thế việc cấu hình Content-Type đúng cho toàn bộ module graph.

Nếu một module import từ CDN trả text/html do redirect tới trang lỗi hoặc trang đăng nhập, browser sẽ từ chối parse module. Kiểm tra response cuối cùng, redirect chain, Content-Type và status thay vì chỉ kiểm tra URL trong source code.

## 5. JSON, HTML và các response khác

### 5.1. JSON

API JSON nên trả:

```http
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
Cache-Control: no-store
```

nosniff giúp ngăn browser xử lý response sai MIME như script/style trong các ngữ cảnh áp dụng. Nó không tự giải quyết CSRF, JSON data exposure, authorization hoặc mọi kỹ thuật JSON hijacking cũ. API vẫn cần authentication, authorization, CORS/CSRF policy và serialization đúng.

Không trả JSON với Content-Type text/html. Nếu API trả error page HTML cho request mong JSON, client cần xử lý status và content type thay vì parse body như JSON một cách mù quáng.

### 5.2. HTML

Trang HTML phải được khai báo text/html. nosniff có thể được gửi cùng các security headers khác, nhưng không ngăn browser render HTML như HTML.

Nếu HTML có dữ liệu do người dùng kiểm soát, cần output encoding theo context, tránh DOM XSS và triển khai CSP phù hợp. nosniff không thay thế XSS defense.

### 5.3. Plain text và binary

Plain text nên trả text/plain; charset=utf-8. Binary không xác định nên dùng application/octet-stream và thường cân nhắc Content-Disposition: attachment để browser tải xuống thay vì hiển thị nội tuyến.

Content-Disposition điều khiển cách response được trình bày như inline hoặc attachment; nó không phải MIME validator. Browser vẫn cần Content-Type đúng và ứng dụng vẫn phải kiểm soát nội dung file.

## 6. File upload và download an toàn

File do người dùng upload là dữ liệu không tin cậy, kể cả khi tên file có phần mở rộng quen thuộc. Attacker có thể đổi extension, giả Content-Type trong multipart request hoặc tạo polyglot file được nhiều parser diễn giải theo cách khác nhau.

### 6.1. Không tin Content-Type do client gửi

Trong multipart/form-data, mỗi file part có thể chứa filename và Content-Type do browser/client khai báo. Giá trị này hữu ích cho UX nhưng không chứng minh định dạng thực tế.

Server nên:

1. Giới hạn kích thước, số lượng và loại file được phép.
2. Kiểm tra extension theo allowlist sau khi chuẩn hóa tên.
3. Kiểm tra file signature/magic bytes bằng parser phù hợp.
4. Parse hoặc decode file bằng thư viện cập nhật và có giới hạn tài nguyên.
5. Re-encode ảnh sang định dạng được hỗ trợ nếu workflow cho phép.
6. Lưu file ngoài web root hoặc trong object storage với quyền truy cập riêng.
7. Tạo tên lưu trữ ngẫu nhiên, không dùng trực tiếp filename do user cung cấp.
8. Khi phục vụ file, tự xác định Content-Type theo loại đã xác minh.

Magic bytes cũng không phải bằng chứng tuyệt đối: file polyglot hoặc parser differential có thể vượt qua một kiểm tra đơn giản. Hãy kết hợp allowlist, parser, giới hạn tài nguyên và quy trình xử lý phù hợp với từng định dạng.

### 6.2. Phục vụ file do người dùng cung cấp

Nếu file không cần render trong browser, ưu tiên tải xuống:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="download.bin"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

Filename trong Content-Disposition phải được encode theo chuẩn phù hợp; không nối chuỗi trực tiếp từ dữ liệu người dùng. Khi cần filename Unicode, server nên dùng cú pháp filename* theo RFC 6266 và thư viện/framework đã kiểm tra.

Nếu ứng dụng cần hiển thị ảnh inline, chỉ cho phép định dạng ảnh đã xác minh, decode rồi re-encode khi phù hợp và trả MIME type chính xác như image/png hoặc image/jpeg. Không cho phép HTML/SVG không tin cậy chạy cùng origin ứng dụng chỉ vì file có đuôi .svg hoặc .html.

### 6.3. Tách origin cho nội dung không tin cậy

Một cách giảm tác động là phục vụ user content từ một site/origin riêng biệt, không chia sẻ session cookie với ứng dụng chính. Ví dụ ứng dụng ở app.example.com và nội dung upload ở user-content.example.net. Tách registrable domain thường tạo ranh giới cookie/site mạnh hơn việc chỉ dùng subdomain cùng site.

Nếu phải phục vụ nội dung chủ động như HTML, cân nhắc:

- Dùng domain riêng không có cookie xác thực của ứng dụng.
- Dùng Content-Disposition: attachment khi không cần render.
- Dùng CSP sandbox chặt cho nội dung cần xem trong iframe.
- Không cho phép script, form submission hoặc top-level navigation ngoài nhu cầu.
- Không cấp CORS credential hoặc quyền truy cập API của ứng dụng cho origin nội dung upload.

Origin riêng giảm nguy cơ cookie và same-origin access bị chia sẻ, nhưng không thay thế kiểm tra file, CSP, authorization và kiểm soát download.

### 6.4. SVG, HTML và định dạng chủ động

SVG có thể chứa script, event handler, external references hoặc nội dung tương tác khi được mở như document. HTML hiển nhiên là active content. PDF và một số định dạng khác cũng có thể có tính năng tương tác.

Không xem SVG/HTML là ảnh hoặc dữ liệu tĩnh chỉ dựa trên extension. Nếu chỉ cần ảnh, rasterize/re-encode thành PNG/JPEG/WebP theo pipeline tin cậy. Nếu cần giữ định dạng gốc, phục vụ như attachment hoặc từ origin cách ly với policy phù hợp.

## 7. nosniff không thay thế các cơ chế khác

Các header và browser controls giải quyết những câu hỏi khác nhau:

| Cơ chế | Câu hỏi nó trả lời |
|---|---|
| Content-Type | Representation này được khai báo là loại dữ liệu nào? |
| X-Content-Type-Options: nosniff | Browser có được sniff để xử lý response như script/style khi MIME không phù hợp không? |
| CSP | Trang được phép nạp/chạy loại nội dung nào và từ nguồn nào? |
| Same-Origin Policy | Script của origin này được đọc dữ liệu origin khác tới đâu? |
| CORS | Server có cho phép JavaScript origin khác đọc response không? |
| CORP/COEP | Resource có được phép nhúng hoặc tham gia cross-origin isolation không? |
| Content-Disposition | Browser nên hiển thị nội tuyến hay gợi ý tải xuống? |
| Authentication/authorization | Ai được phép truy cập resource? |

### 7.1. nosniff không phải CORS

Một response có Content-Type application/json và nosniff vẫn không tự cho phép JavaScript từ origin khác đọc body. CORS quyết định quyền đọc cross-origin qua Fetch/XHR; nosniff không thêm Access-Control-Allow-Origin và cũng không bỏ Same-Origin Policy.

Ngược lại, CORS cho phép đọc response không có nghĩa MIME type sai trở nên an toàn. Cần cấu hình cả hai theo đúng mục đích.

### 7.2. nosniff không phải CSP

CSP có thể giới hạn nguồn script và chặn inline script theo policy. nosniff kiểm soát một phần MIME interpretation cho script/style request. Dùng CSP và nosniff cùng nhau, đồng thời bảo đảm Content-Type chính xác.

Nếu một trang HTML có XSS trong nội dung hợp lệ, nosniff không loại bỏ script đã được browser xử lý như HTML. Cần output encoding, sanitization theo context, Trusted Types khi phù hợp và CSP.

### 7.3. nosniff không phải antivirus hoặc file validator

Header không quét malware, không parse file và không bảo đảm file đúng extension. File độc hại vẫn có thể được tải xuống, lưu trữ hoặc khai thác bởi ứng dụng mở file. Upload pipeline cần scanning/validation phù hợp với loại nội dung và threat model.

## 8. Cấu hình Content-Type và nosniff đồng bộ

### 8.1. Application server

Đặt header ở middleware hoặc response helper dùng chung để mọi route static/API/upload đều nhận policy phù hợp. Với response động, xác định Content-Type trước khi ghi body; tránh gửi header chung nhưng bỏ sót route error hoặc redirect.

Ví dụ Node.js:

```js
function sendJson(res, status, data) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(data));
}

function sendJavaScript(res, source) {
  res.writeHead(200, {
    'Content-Type': 'text/javascript; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'public, max-age=300',
  });
  res.end(source);
}
```

### 8.2. Nginx và Apache

Nginx có thể thêm header ở server/location phù hợp:

```nginx
add_header X-Content-Type-Options "nosniff" always;
```

Apache với mod_headers có thể dùng:

```apache
Header always set X-Content-Type-Options "nosniff"
```

Kiểm tra inheritance và thứ tự cấu hình. Một location block hoặc proxy có thể thay thế/ghi đè header; cần xác minh response thực tế ở từng route.

### 8.3. CDN và object storage

CDN/object storage có thể tự gán Content-Type theo metadata object hoặc extension. Khi upload artifact, bảo đảm metadata đúng và header nosniff được gắn ở origin hoặc edge. Kiểm tra:

- Response từ origin.
- Response qua CDN/edge.
- Redirect và error response.
- File upload/download.
- Static assets có extension lạ hoặc MIME mapping tùy chỉnh.

Không chỉ kiểm tra cấu hình source. Browser nhìn thấy response cuối cùng sau redirect và proxy, nên đó mới là điểm cần xác minh.

## 9. Chẩn đoán lỗi MIME type

Khi browser không tải script hoặc stylesheet, mở DevTools → Network và Console:

1. Chọn request resource bị lỗi.
2. Kiểm tra status code và redirect chain.
3. Xem response Content-Type thực tế.
4. Xem X-Content-Type-Options có phải nosniff không.
5. Xem response body có phải trang login, error page hoặc proxy HTML thay vì asset không.
6. Kiểm tra MIME type có phù hợp destination script/style không.
7. Kiểm tra CDN/static server mapping và build artifact path.

Thông báo thường gặp có dạng strict MIME type checking, MIME type không hợp lệ hoặc stylesheet không được load vì MIME type không phải text/css. Không sửa bằng cách bỏ nosniff trước khi tìm nguyên nhân server trả sai Content-Type.

### 9.1. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| JS bị chặn với text/plain | Static server gán MIME type sai | Sửa MIME mapping thành text/javascript |
| JS nhận text/html | Asset URL bị redirect tới login/404 HTML | Sửa route, auth/static hosting và redirect |
| CSS bị chặn | Response không phải text/css | Sửa Content-Type hoặc URL |
| JSON endpoint hiển thị HTML | Error middleware trả HTML cho API | Chuẩn hóa API error response và Content-Type |
| Upload HTML được render cùng origin | File không tin cậy phục vụ inline trên domain chính | Dùng attachment hoặc origin cách ly, validation và CSP |
| Header có ở API nhưng thiếu ở static asset | Middleware không áp dụng cho CDN/static route | Cấu hình ở edge/static host và xác minh response |
| Browser khác behavior | MIME checking và sniffing khác theo request/browser | Khai báo MIME đúng, nosniff và test browser mục tiêu |

## 10. Thực hành: nosniff với Node.js

Lab tạo các endpoint có MIME type đúng và sai để bạn quan sát response headers, Console và behavior của script/style. Route sai MIME có nosniff phải bị browser chặn trong strict script/style checks; route không có nosniff được đưa vào để so sánh hành vi browser, không phải mẫu cấu hình production.

### Bước 1 — Tạo file `nosniff-lab.cjs`

```js
const http = require('node:http');

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>nosniff lab</title></head><body>',
  '<h1>X-Content-Type-Options: nosniff lab</h1>',
  '<p>Thử các script có Content-Type đúng/sai và nosniff bật/tắt.</p>',
  '<button id="good" type="button">Load correct JavaScript MIME</button>',
  '<button id="bad-nosniff" type="button">Load text/plain with nosniff</button>',
  '<button id="bad-no-header" type="button">Load text/plain without nosniff</button>',
  '<button id="json" type="button">Fetch JSON response</button>',
  '<pre id="output"></pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  "const output = document.querySelector('#output');",
  'function loadScript(path) {',
  '  const script = document.createElement("script");',
  '  script.src = path;',
  '  script.onload = () => { output.textContent += "\\nLoaded: " + path; };',
  '  script.onerror = () => { output.textContent += "\\nBlocked/failed: " + path; };',
  '  document.head.append(script);',
  '}',
  "document.querySelector('#good').addEventListener('click', () => loadScript('/assets/good.js'));",
  "document.querySelector('#bad-nosniff').addEventListener('click', () => loadScript('/assets/wrong-nosniff.js'));",
  "document.querySelector('#bad-no-header').addEventListener('click', () => loadScript('/assets/wrong-no-header.js'));",
  "document.querySelector('#json').addEventListener('click', async () => {",
  '  const response = await fetch("/api/data");',
  '  output.textContent = JSON.stringify({',
  '    status: response.status,',
  '    contentType: response.headers.get("content-type"),',
  '    nosniff: response.headers.get("x-content-type-options"),',
  '    body: await response.json(),',
  '  }, null, 2);',
  '});',
].join('\n');

const scriptBody = [
  "document.body.dataset.labScript = 'executed';",
  "document.querySelector('#output').textContent += '\\nScript body executed';",
].join('\n');

const cssBody = 'body { border-top: 4px solid #2563eb; }';

function send(res, status, headers, body = '') {
  res.writeHead(status, headers);
  res.end(body);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method === 'GET' && url.pathname === '/') {
    return send(res, 200, {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
      'Cache-Control': 'no-store',
    }, page);
  }

  if (req.method === 'GET' && url.pathname === '/app.js') {
    return send(res, 200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    }, appJs);
  }

  if (req.method === 'GET' && url.pathname === '/assets/good.js') {
    return send(res, 200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
    }, scriptBody);
  }

  if (req.method === 'GET' && url.pathname === '/assets/wrong-nosniff.js') {
    return send(res, 200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
    }, scriptBody);
  }

  if (req.method === 'GET' && url.pathname === '/assets/wrong-no-header.js') {
    return send(res, 200, {
      'Content-Type': 'text/plain; charset=utf-8',
    }, scriptBody);
  }

  if (req.method === 'GET' && url.pathname === '/assets/wrong.css') {
    return send(res, 200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
    }, cssBody);
  }

  if (req.method === 'GET' && url.pathname === '/api/data') {
    return send(res, 200, {
      'Content-Type': 'application/json; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, type: 'application/json' }));
  }

  if (req.method === 'GET' && url.pathname === '/download/sample') {
    return send(res, 200, {
      'Content-Type': 'application/octet-stream',
      'Content-Disposition': 'attachment; filename="sample.txt"',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'private, no-store',
    }, 'Synthetic download content. This is not an executable file.');
  }

  return send(res, 404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
  }, 'Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node nosniff-lab.cjs
```

Mở http://localhost:3000. Nếu cổng 3000 đang được sử dụng, đổi cổng trong server và URL base trong new URL().

### Bước 3 — So sánh script

1. Mở DevTools → Network và Console.
2. Nhấn **Load correct JavaScript MIME**; script phải tải và thực thi.
3. Nhấn **Load text/plain with nosniff**; browser phải chặn script do MIME type không hợp lệ.
4. Nhấn **Load text/plain without nosniff**; quan sát behavior và Console. Browser có thể sniff hoặc vẫn chặn theo implementation/request rules. Không dựa vào trường hợp nào để cấu hình production.
5. So sánh response Content-Type và X-Content-Type-Options của ba route.

### Bước 4 — JSON và download

1. Nhấn **Fetch JSON response**; kiểm tra application/json và nosniff.
2. Mở /download/sample; browser nhận application/octet-stream và Content-Disposition attachment.
3. Kiểm tra response headers trong Network.
4. Mở trực tiếp /assets/wrong.css hoặc tạo link stylesheet tới route đó để xem CSS MIME check trong Console.

Lab không dùng file người dùng upload, không chạy third-party script và chỉ trả nội dung synthetic.

## 11. Checklist triển khai nosniff

- [ ] Mọi response có Content-Type đúng với representation thực tế.
- [ ] JavaScript dùng JavaScript MIME type hợp lệ.
- [ ] CSS dùng text/css.
- [ ] JSON API dùng application/json.
- [ ] Static host/CDN không ghi đè MIME mapping sai.
- [ ] X-Content-Type-Options: nosniff được gửi trên response cần bảo vệ.
- [ ] Redirect/error route không trả HTML thay cho JS/CSS mà không được phát hiện.
- [ ] File upload không tin filename hoặc Content-Type do client cung cấp.
- [ ] Upload được validate bằng allowlist, parser/signature và giới hạn tài nguyên.
- [ ] User content được phục vụ dạng attachment hoặc từ origin cách ly khi phù hợp.
- [ ] SVG/HTML không tin cậy không chạy cùng origin ứng dụng.
- [ ] Download dùng Content-Disposition phù hợp và MIME type đã xác minh.
- [ ] CSP, CORS và authorization được cấu hình riêng theo mục đích.
- [ ] DevTools được dùng để kiểm tra response cuối cùng sau CDN/redirect.
- [ ] Có test cho script/style sai MIME và route static/error.

## 12. Câu hỏi tự kiểm tra

**1.** Content-Type mô tả điều gì?  
**Trả lời:** MIME type của representation trong HTTP response hoặc request body, tùy header được xét.

**2.** MIME sniffing là gì?  
**Trả lời:** Browser phân tích nội dung response để suy đoán loại dữ liệu khi MIME metadata thiếu hoặc không rõ trong các ngữ cảnh được hỗ trợ.

**3.** X-Content-Type-Options: nosniff có tác dụng chính gì?  
**Trả lời:** Ngăn browser sniff để xử lý response như script hoặc stylesheet khi MIME type không phù hợp theo strict checking rules.

**4.** nosniff có biến response text/html thành text/plain không?  
**Trả lời:** Không. Browser vẫn render HTML như HTML khi navigation tới response có Content-Type text/html.

**5.** JavaScript nên được phục vụ với MIME type nào?  
**Trả lời:** JavaScript MIME type hợp lệ, phổ biến là text/javascript.

**6.** Vì sao không tin Content-Type trong multipart upload?  
**Trả lời:** Client kiểm soát giá trị đó và có thể khai báo sai so với nội dung file thực tế.

**7.** nosniff có thay thế CSP không?  
**Trả lời:** Không. CSP giới hạn nguồn và hành vi nội dung; nosniff kiểm soát một phần MIME interpretation.

**8.** nosniff có thay CORS không?  
**Trả lời:** Không. CORS quyết định quyền đọc response cross-origin; nosniff không cấp quyền đó.

**9.** Vì sao nên tách origin cho user uploads?  
**Trả lời:** Giảm khả năng nội dung không tin cậy chia sẻ cookie và same-origin privileges với ứng dụng chính.

**10.** Nếu JS bị chặn vì MIME type text/html, nên làm gì?  
**Trả lời:** Kiểm tra route, redirect, error page, static server và Content-Type; sửa response thực tế thay vì bỏ nosniff.

## Tổng kết

X-Content-Type-Options: nosniff giúp browser không diễn giải một số response sai MIME như script hoặc stylesheet trong các ngữ cảnh strict checking. Header này phát huy tác dụng khi server khai báo Content-Type chính xác và được gửi nhất quán qua application server, CDN và object storage. Nó không làm sạch HTML, không xác thực file upload, không chặn mọi navigation và không thay CSP, CORS hay authorization. Với user content, cần xác minh định dạng, phục vụ bằng attachment hoặc origin cách ly và kiểm tra response cuối cùng trên browser mục tiêu.
