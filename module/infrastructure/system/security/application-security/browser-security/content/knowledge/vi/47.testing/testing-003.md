# CORS test

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt origin với site và xác định chính xác khi nào hai URL là cross-origin.
- Thiết kế một phép thử CORS có thể tái hiện bằng hai origin cục bộ.
- Kiểm tra simple request, preflight request và response trong DevTools.
- Đọc và đánh giá các header Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers, Access-Control-Allow-Credentials và Access-Control-Expose-Headers.
- Kiểm tra request có credentials, cookie SameSite và giới hạn của wildcard.
- Phân biệt lỗi CORS ở trình duyệt với lỗi HTTP, lỗi mạng, xác thực và phân quyền ở máy chủ.
- Viết ma trận kiểm thử để xác minh cấu hình CORS trước khi triển khai.

## 1. CORS test kiểm tra điều gì?

Cross-Origin Resource Sharing (CORS) là cơ chế mà máy chủ dùng các response header để cho trình duyệt biết JavaScript từ một origin có được phép đọc response của một request cross-origin hay không. CORS được triển khai bởi trình duyệt dựa trên giao thức HTTP và Fetch; máy chủ cần trả các header phù hợp với chính sách truy cập mà ứng dụng mong muốn.

Một bài CORS test kiểm tra đồng thời ba điều:

1. **Trình duyệt gửi request nào?** Request có phải simple request hay cần preflight bằng OPTIONS? Có gửi credentials không?
2. **Máy chủ trả header nào?** Origin, method, request header và credentials có được cho phép chính xác không?
3. **JavaScript nhận được gì?** Response có được trình duyệt cho phép đọc hay bị chặn bởi CORS check?

CORS không phải cơ chế xác thực hoặc phân quyền nghiệp vụ. Một response có Access-Control-Allow-Origin hợp lệ chỉ cho phép JavaScript trong origin được chỉ định đọc response theo chính sách CORS. Máy chủ vẫn phải xác thực người dùng, kiểm tra quyền trên từng tài nguyên và xác thực dữ liệu đầu vào.

CORS cũng không ngăn mọi request cross-origin được gửi đi. Một số request đơn giản có thể đến máy chủ dù JavaScript không đọc được response. Với request cần preflight, trình duyệt gửi OPTIONS trước và chỉ gửi request thực tế nếu preflight thành công. Sự khác nhau này rất quan trọng khi đánh giá CSRF.

## 2. Chuẩn bị môi trường kiểm thử

### 2.1. Origin được xác định như thế nào?

Một origin gồm ba thành phần:

- Scheme: giao thức như http hoặc https.
- Host: tên miền hoặc địa chỉ IP.
- Port: cổng kết nối.

Hai URL có origin khác nhau nếu khác ít nhất một trong ba thành phần này.

| URL A | URL B | Kết quả |
|---|---|---|
| http://app.example.test | http://api.example.test | Khác host, cross-origin |
| https://app.example.test | http://app.example.test | Khác scheme, cross-origin |
| https://app.example.test | https://app.example.test:8443 | Khác port, cross-origin |
| http://127.0.0.1:5500 | http://127.0.0.1:8000 | Khác port, cross-origin |
| https://app.example.test/path-a | https://app.example.test/path-b | Cùng origin |
| https://app.example.test:443 | https://app.example.test | Cùng origin theo port mặc định |

Đường dẫn và query string không tham gia xác định origin. Port mặc định được chuẩn hóa theo scheme. Cần chú ý rằng khái niệm site dùng trong một số quy tắc cookie, chẳng hạn SameSite, khác với origin: hai cổng khác nhau có thể là hai origin nhưng vẫn cùng schemeful site vì port không tham gia phép so sánh site.

Trong bài thực hành, ta dùng ba địa chỉ loopback:

| Thành phần | Địa chỉ | Vai trò |
|---|---|---|
| Trang được phép | http://127.0.0.1:5500 | Origin gọi API hợp lệ |
| Trang bị từ chối | http://127.0.0.1:5501 | Origin dùng để kiểm tra allowlist |
| API thử nghiệm | http://127.0.0.1:8000 | Máy chủ trả response CORS |

Ba cổng khác nhau tạo ba origin khác nhau. Tất cả dịch vụ chỉ lắng nghe trên địa chỉ loopback 127.0.0.1, không mở ra mạng LAN hoặc Internet.

### 2.2. Công cụ cần có

- Node.js phiên bản còn được hỗ trợ, dùng module HTTP tích hợp sẵn, không cần cài package.
- Một trình duyệt hiện đại như Chrome, Edge hoặc Firefox.
- DevTools với các thẻ Console và Network.
- Terminal để chạy máy chủ và gửi request kiểm tra header bằng curl.exe.

Không dùng tài khoản thật, token thật, cookie thật hoặc dữ liệu cá nhân trong lab. Môi trường này chỉ dành cho kiểm thử trên máy cục bộ.

## 3. Dựng hai origin và một API thử nghiệm

Tạo tệp cors-lab.js trong một thư mục tạm. Ví dụ dưới đây tạo hai trang giống nhau trên cổng 5500 và 5501, cùng API trên cổng 8000. API chỉ cho phép origin 5500 đọc response theo CORS.

~~~javascript
const http = require("node:http");

const HOST = "127.0.0.1";
const ALLOWED_ORIGIN = "http://127.0.0.1:5500";

function sendJson(res, status, data) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(data));
}

function setCors(res, origin, credentials = false) {
  res.setHeader("Vary", "Origin");

  if (origin === ALLOWED_ORIGIN) {
    res.setHeader("Access-Control-Allow-Origin", origin);

    if (credentials) {
      res.setHeader("Access-Control-Allow-Credentials", "true");
    }
  }
}

function readBody(req, limit = 4096) {
  return new Promise((resolve, reject) => {
    let body = "";
    let tooLarge = false;

    req.on("data", (chunk) => {
      if (tooLarge) {
        return;
      }

      body += chunk;
      tooLarge = Buffer.byteLength(body, "utf8") > limit;
    });

    req.on("end", () => {
      if (tooLarge) {
        reject(new Error("Request body too large"));
      } else {
        resolve(body);
      }
    });
    req.on("error", reject);
  });
}

const page = [
  "<!doctype html>",
  "<html lang='vi'>",
  "<meta charset='utf-8'>",
  "<meta name='viewport' content='width=device-width, initial-scale=1'>",
  "<title>CORS test</title>",
  "<body>",
  "<h1>CORS test</h1>",
  "<p>Origin hiện tại: <strong id='origin'></strong></p>",
  "<button id='public'>GET public wildcard</button>",
  "<button id='simple'>GET allowlist</button>",
  "<button id='simple-post'>POST text/plain</button>",
  "<button id='preflight'>POST JSON + custom header</button>",
  "<button id='set-cookie'>Set cookie</button>",
  "<button id='whoami'>Kiểm tra cookie</button>",
  "<button id='wildcard-credentials'>Wildcard + credentials</button>",
  "<pre id='output'>Chưa chạy phép thử.</pre>",
  "<script>",
  "const API = 'http://127.0.0.1:8000';",
  "const output = document.querySelector('#output');",
  "document.querySelector('#origin').textContent = location.origin;",
  "async function run(label, action) {",
  "  output.textContent = label + ': đang chạy...';",
  "  try {",
  "    const result = await action();",
  "    output.textContent = label + ': ' + JSON.stringify(result, null, 2);",
  "  } catch (error) {",
  "    output.textContent = label + ': ' + error.name + ': ' + error.message;",
  "  }",
  "}",
  "document.querySelector('#public').addEventListener('click', () => run('public', async () => {",
  "  const response = await fetch(API + '/public');",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "document.querySelector('#simple').addEventListener('click', () => run('simple', async () => {",
  "  const response = await fetch(API + '/simple');",
  "  return { status: response.status, trace: response.headers.get('X-Trace-Id'), body: await response.json() };",
  "}));",
  "document.querySelector('#simple-post').addEventListener('click', () => run('simple POST', async () => {",
  "  const response = await fetch(API + '/simple-post', {",
  "    method: 'POST',",
  "    headers: { 'Content-Type': 'text/plain' },",
  "    body: 'hello from a CORS simple request'",
  "  });",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "document.querySelector('#preflight').addEventListener('click', () => run('preflight POST', async () => {",
  "  const response = await fetch(API + '/update', {",
  "    method: 'POST',",
  "    headers: {",
  "      'Content-Type': 'application/json',",
  "      'X-Demo-Key': 'lab-only'",
  "    },",
  "    body: JSON.stringify({ message: 'hello' })",
  "  });",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "document.querySelector('#set-cookie').addEventListener('click', () => run('set cookie', async () => {",
  "  const response = await fetch(API + '/set-cookie', { credentials: 'include' });",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "document.querySelector('#whoami').addEventListener('click', () => run('whoami', async () => {",
  "  const response = await fetch(API + '/whoami', { credentials: 'include' });",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "document.querySelector('#wildcard-credentials').addEventListener('click', () => run('wildcard credentials', async () => {",
  "  const response = await fetch(API + '/wildcard-credentials', { credentials: 'include' });",
  "  return { status: response.status, body: await response.json() };",
  "}));",
  "</script>",
  "</body>",
  "</html>"
].join("");

function startPageServer(port) {
  const server = http.createServer((req, res) => {
    if (req.url !== "/") {
      res.writeHead(404);
      res.end("Not found");
      return;
    }

    res.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    });
    res.end(page);
  });

  server.listen(port, HOST, () => {
    console.log("Page: http://" + HOST + ":" + port);
  });
}

const allowedMethods = new Set(["GET", "POST"]);
const allowedHeaders = new Set(["content-type", "x-demo-key"]);

const api = http.createServer(async (req, res) => {
  const origin = req.headers.origin;

  if (req.method === "OPTIONS") {
    const requestedMethod = req.headers["access-control-request-method"];
    const requestedHeaders = (req.headers["access-control-request-headers"] || "")
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean);

    const methodAllowed = allowedMethods.has(requestedMethod);
    const headersAllowed = requestedHeaders.every((name) => allowedHeaders.has(name));

    if (origin !== ALLOWED_ORIGIN || !methodAllowed || !headersAllowed) {
      res.writeHead(403, { "Cache-Control": "no-store" });
      res.end();
      return;
    }

    res.writeHead(204, {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Methods": "GET, POST",
      "Access-Control-Allow-Headers": "Content-Type, X-Demo-Key",
      "Access-Control-Max-Age": "60",
      "Vary": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
    });
    res.end();
    return;
  }

  if (req.url === "/public" && req.method === "GET") {
    res.setHeader("Access-Control-Allow-Origin", "*");
    sendJson(res, 200, { message: "Public response; no credentials" });
    return;
  }

  if (req.url === "/wildcard-credentials" && req.method === "GET") {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Credentials", "true");
    sendJson(res, 200, { message: "This combination is rejected by credentialed CORS" });
    return;
  }

  if (req.url === "/simple" && req.method === "GET") {
    setCors(res, origin);
    res.setHeader("Access-Control-Expose-Headers", "X-Trace-Id");
    res.setHeader("X-Trace-Id", "cors-lab-001");
    sendJson(res, 200, { message: "Allowlisted simple GET" });
    return;
  }

  if (req.url === "/simple-post" && req.method === "POST") {
    setCors(res, origin);
    try {
      const body = await readBody(req);
      sendJson(res, 200, { receivedLength: body.length });
    } catch (error) {
      sendJson(res, 413, { error: error.message });
    }
    return;
  }

  if (req.url === "/update" && req.method === "POST") {
    setCors(res, origin);
    try {
      const body = await readBody(req);
      sendJson(res, 200, { receivedLength: body.length, updated: true });
    } catch (error) {
      sendJson(res, 413, { error: error.message });
    }
    return;
  }

  if (req.url === "/set-cookie" && req.method === "GET") {
    setCors(res, origin, true);
    res.setHeader(
      "Set-Cookie",
      "lab_session=demo123; HttpOnly; SameSite=Lax; Path=/; Max-Age=600"
    );
    sendJson(res, 200, { cookieSet: true });
    return;
  }

  if (req.url === "/whoami" && req.method === "GET") {
    setCors(res, origin, true);
    const cookie = req.headers.cookie || "";
    const received = /(?:^|;\s*)lab_session=demo123(?:;|$)/.test(cookie);
    sendJson(res, 200, { cookieReceived: received });
    return;
  }

  sendJson(res, 404, { error: "Not found" });
});

startPageServer(5500);
startPageServer(5501);

api.listen(8000, HOST, () => {
  console.log("API: http://" + HOST + ":8000");
});
~~~

Khởi chạy trong terminal tại thư mục chứa tệp:

~~~powershell
node .\cors-lab.js
~~~

Mở trang được cho phép:

~~~text
http://127.0.0.1:5500/
~~~

Mở thêm trang dùng để kiểm tra origin bị từ chối:

~~~text
http://127.0.0.1:5501/
~~~

Hai trang dùng cùng giao diện, nhưng API chỉ cho phép origin cổng 5500. Để dừng máy chủ, quay lại terminal và nhấn Ctrl+C.

Mã lab chỉ lắng nghe trên loopback, dùng dữ liệu minh họa và không thực hiện thao tác nhạy cảm. Không triển khai mã này thành máy chủ công khai.

## 4. Kiểm tra simple request

### 4.1. Simple request là gì?

Một request thuộc nhóm CORS-safelisted request có thể được gửi mà không cần preflight nếu đáp ứng các điều kiện của Fetch. Các điều kiện thường gặp:

- Method là GET, HEAD hoặc POST.
- Các request header nằm trong danh sách safelisted và giá trị đáp ứng giới hạn tương ứng. Các tên thường gặp gồm Accept, Accept-Language, Content-Language, Content-Type và Range; Range chỉ được safelist trong dạng byte range đơn được Fetch cho phép.
- Nếu có Content-Type, giá trị media type thuộc một trong các nhóm application/x-www-form-urlencoded, multipart/form-data hoặc text/plain, đồng thời không vi phạm các điều kiện bổ sung của Fetch.
- Request không chứa các header không safelisted như Authorization hoặc X-Demo-Key.

Không phải mọi POST đều là simple request. POST với Content-Type application/json thường cần preflight; POST có header tùy chỉnh cũng cần preflight.

### 4.2. Thử GET từ origin được phép

Mở trang ở cổng 5500, mở DevTools, chọn Network và bấm GET allowlist.

Kết quả mong đợi:

1. Trình duyệt gửi GET đến http://127.0.0.1:8000/simple.
2. Request có header Origin: http://127.0.0.1:5500.
3. Không có OPTIONS preflight trước request này.
4. Response chứa Access-Control-Allow-Origin: http://127.0.0.1:5500.
5. JavaScript đọc được JSON và header X-Trace-Id vì response khai báo Access-Control-Expose-Headers.

Trong Network, kiểm tra Request Headers và Response Headers. Mở Console để xem lỗi nếu fetch bị reject.

### 4.3. Thử wildcard cho tài nguyên công khai

Bấm GET public wildcard. API trả:

~~~http
Access-Control-Allow-Origin: *
Content-Type: application/json; charset=utf-8
~~~

Cả origin 5500 và 5501 đều có thể đọc response này vì endpoint công khai không dùng credentials. Đây là cách phù hợp cho tài nguyên thực sự công khai và không phụ thuộc cookie hoặc thông tin xác thực của người dùng.

Không dùng wildcard cho dữ liệu cá nhân, dữ liệu theo tài khoản hoặc response có credentials. Wildcard không chứng minh người gọi là người dùng hợp lệ và không thay thế authorization.

Bấm Wildcard + credentials để kiểm tra trường hợp sai. Endpoint cố ý trả cả Access-Control-Allow-Origin: * và Access-Control-Allow-Credentials: true; vì fetch dùng credentials: include, trình duyệt từ chối cho JavaScript đọc response. Đây là test âm để quan sát lỗi trong Console và Network.

### 4.4. Thử POST không cần preflight

Từ trang 5500, bấm POST text/plain. Request dùng method POST và Content-Type text/plain, không thêm header tùy chỉnh. Trình duyệt có thể gửi request trực tiếp mà không gửi OPTIONS.

Trong Network, kiểm tra:

- Chỉ có request POST đến /simple-post.
- Request Content-Type là text/plain.
- Response có Access-Control-Allow-Origin đúng origin.
- JavaScript đọc được response JSON.

Điểm cần ghi nhận: request đã đến server trước khi trình duyệt quyết định JavaScript có được đọc response hay không. Đây là lý do một website có thể vẫn cần chống CSRF dù đã cấu hình CORS chặt.

## 5. Kiểm tra preflight request

### 5.1. Khi nào trình duyệt gửi OPTIONS?

Trình duyệt gửi preflight khi request không đáp ứng điều kiện CORS-safelisted. Một số nguyên nhân phổ biến:

- Dùng method như PUT, PATCH hoặc DELETE.
- Dùng Content-Type application/json.
- Gửi header tùy chỉnh như X-Demo-Key.
- Gửi Authorization.
- Dùng request header hoặc thuộc tính khác khiến request không còn thuộc nhóm safelisted.

Preflight là request OPTIONS do trình duyệt tạo. Nó mô tả origin, method dự kiến và danh sách request header mà request thực tế muốn sử dụng.

Ví dụ request preflight tương ứng với nút POST JSON:

~~~http
OPTIONS /update HTTP/1.1
Host: 127.0.0.1:8000
Origin: http://127.0.0.1:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-demo-key
~~~

Máy chủ cần phản hồi cho phép đúng origin, method và các header được yêu cầu. Với lab, response hợp lệ có dạng:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: http://127.0.0.1:5500
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-Demo-Key
Access-Control-Max-Age: 60
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Sau khi preflight thành công, trình duyệt mới gửi POST thực tế. Request OPTIONS không mang cookie hoặc HTTP credentials của request thực tế. Khi request thực tế dùng credentials, response preflight cần cho phép credentials bằng Access-Control-Allow-Credentials: true để trình duyệt chấp nhận luồng đó.

### 5.2. Thử POST JSON và header tùy chỉnh

Từ trang 5500, bấm POST JSON + custom header.

Trong Network, lọc theo từ khóa update hoặc OPTIONS. Bạn cần nhìn thấy hai request:

1. OPTIONS /update: preflight.
2. POST /update: request thực tế sau khi preflight được chấp nhận.

Kiểm tra các trường:

| Trường | Giá trị mong đợi |
|---|---|
| Origin | http://127.0.0.1:5500 |
| Access-Control-Request-Method | POST |
| Access-Control-Request-Headers | content-type,x-demo-key |
| Access-Control-Allow-Origin | http://127.0.0.1:5500 |
| Access-Control-Allow-Methods | Có POST |
| Access-Control-Allow-Headers | Có Content-Type và X-Demo-Key |

Thứ tự chữ hoa/chữ thường của tên header không phân biệt khi so khớp. Danh sách header trong request có thể được trình duyệt chuẩn hóa về chữ thường.

### 5.3. Thử origin không nằm trong allowlist

Mở http://127.0.0.1:5501/ và bấm GET allowlist.

Kết quả mong đợi:

- Server nhận GET /simple.
- Response không có Access-Control-Allow-Origin phù hợp.
- JavaScript không được đọc response và fetch reject.
- Console hiển thị thông báo CORS tương ứng.

Đây là simple request nên request vẫn có thể đến server. Tiếp theo, bấm POST JSON + custom header. Trình duyệt gửi OPTIONS, API trả 403 vì origin không được cho phép, và POST thực tế không được gửi.

So sánh hai tình huống giúp phân biệt:

- Simple request: request có thể đã được gửi, nhưng response bị chặn khỏi JavaScript.
- Request cần preflight: nếu OPTIONS thất bại, request thực tế không được gửi theo luồng CORS.

### 5.4. Preflight cache

Trình duyệt có thể lưu kết quả preflight theo Access-Control-Max-Age, trong giới hạn do trình duyệt áp dụng. Khi thay đổi cấu hình allowlist hoặc header, một phép thử có thể vẫn dùng kết quả đã cache.

Khi kết quả không khớp cấu hình vừa sửa:

- Kiểm tra Network xem có OPTIONS mới không.
- Đợi preflight cache hết hạn hoặc thay đổi test case để tạo tổ hợp method/header mới.
- Thử trong hồ sơ trình duyệt sạch nếu cần.
- Phân biệt preflight cache với HTTP cache thông thường; thao tác Disable cache không phải lúc nào cũng xóa preflight cache.

## 6. Kiểm tra credentials và cookie

### 6.1. Request credentials hoạt động thế nào?

Fetch mặc định dùng credentials: same-origin. Với request cross-origin, cookie và HTTP credentials không được gửi theo mặc định. Nếu chức năng cần gửi cookie, client phải dùng credentials: include và server phải trả các header CORS tương ứng.

Ví dụ:

~~~javascript
const response = await fetch("https://api.example.test/account", {
  method: "GET",
  credentials: "include"
});

const data = await response.json();
~~~

Response cho credentialed request phải chỉ định origin cụ thể và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Giá trị của Access-Control-Allow-Credentials phải là chuỗi true viết thường. Response dùng Access-Control-Allow-Origin: * sẽ không được chấp nhận cho request có credentials mode include.

### 6.2. Thử cookie trong lab

Từ trang 5500:

1. Bấm Set cookie.
2. Sau khi request thành công, bấm Kiểm tra cookie.
3. API trả cookieReceived: true nếu trình duyệt gửi cookie lab_session.
4. Mở Network để kiểm tra request /set-cookie và /whoami.
5. Quan sát rằng JavaScript không đọc được header Set-Cookie trực tiếp.

Cookie trong lab có HttpOnly và SameSite=Lax. Hai trang và API dùng cùng host 127.0.0.1, chỉ khác port. Chúng là các origin khác nhau nhưng cùng site theo cách so sánh scheme và site của cookie. Vì vậy, bài này minh họa CORS cross-origin cùng site; nó không mô phỏng đầy đủ cookie third-party giữa hai site khác nhau.

Nếu thử với hai site khác nhau, cần đánh giá thêm:

- SameSite=Strict hoặc Lax có thể ngăn cookie được gửi trong một số ngữ cảnh cross-site.
- SameSite=None thường cần Secure.
- Chính sách chặn third-party cookie của trình duyệt có thể ngăn cookie dù CORS header đúng.
- Domain, Path, Secure, HttpOnly, thời hạn cookie và chính sách partitioning cũng ảnh hưởng kết quả.
- credentials: include không vượt qua chính sách cookie của trình duyệt.

CORS thành công không có nghĩa cookie chắc chắn được gửi. Hãy kiểm tra Request Headers và cookie storage, đồng thời xem chính sách cookie của trình duyệt.

### 6.3. Header response có credentials và wildcard

Cấu hình sau không hợp lệ cho credentialed request:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Trình duyệt từ chối cho JavaScript đọc response vì origin wildcard không được dùng với credentials mode include. Cần phản hồi origin cụ thể sau khi kiểm tra allowlist.

Không phản chiếu tùy tiện Origin nhận được. Nếu server luôn sao chép giá trị Origin vào Access-Control-Allow-Origin, website bất kỳ có thể được cấp quyền đọc response. Hãy so khớp origin đã parse với allowlist chính xác, gồm scheme, host và port.

## 7. Kiểm tra từng CORS response header

| Header | Dùng để làm gì? | Cách kiểm thử |
|---|---|---|
| Access-Control-Allow-Origin | Cho phép một origin đọc response hoặc dùng wildcard cho tài nguyên công khai | So khớp chính xác scheme, host và port |
| Access-Control-Allow-Methods | Khai báo method được phép trong preflight | Thử method có trong và ngoài danh sách |
| Access-Control-Allow-Headers | Khai báo request header được phép trong preflight | Thử header safelisted, header tùy chỉnh và Authorization |
| Access-Control-Allow-Credentials | Cho phép response được đọc trong request có credentials mode include | Kiểm tra giá trị true và origin cụ thể |
| Access-Control-Expose-Headers | Cho JavaScript đọc thêm response header ngoài danh sách safelisted | Thử response.headers.get với header tùy chỉnh |
| Access-Control-Max-Age | Giới hạn thời gian cache kết quả preflight | Thay đổi policy và kiểm tra preflight cache |
| Vary: Origin | Báo cache rằng response phụ thuộc Origin | Kiểm tra response động qua CDN hoặc shared cache |

### 7.1. Access-Control-Allow-Origin

Server có thể trả một origin cụ thể:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Hoặc wildcard cho tài nguyên công khai:

~~~http
Access-Control-Allow-Origin: *
~~~

Không được trả nhiều origin phân tách bằng dấu phẩy trong cùng một header. Nếu cần cho phép nhiều origin, server phải kiểm tra Origin với allowlist rồi phản hồi lại một origin phù hợp cho request đó. Khi response thay đổi theo Origin, cần có Vary: Origin để cache không phục vụ nhầm response của origin này cho origin khác.

### 7.2. Access-Control-Allow-Methods và Access-Control-Allow-Headers

Hai header này chủ yếu phục vụ preflight. Danh sách phải bao gồm method và request header mà trình duyệt báo trong Access-Control-Request-Method và Access-Control-Request-Headers.

Không nhầm Access-Control-Allow-Headers với danh sách response header mà JavaScript được đọc. Đối với response header, dùng Access-Control-Expose-Headers.

Wildcard trong Access-Control-Allow-Headers và Access-Control-Allow-Methods có quy tắc riêng khi request dùng credentials. Để tránh cấu hình khó đoán, nên khai báo rõ method và header cần dùng. Authorization cần được liệt kê tường minh; không dựa vào wildcard để cho phép header này.

### 7.3. Access-Control-Expose-Headers

JavaScript chỉ đọc được các response header nằm trong CORS-safelisted response headers hoặc được máy chủ công khai qua Access-Control-Expose-Headers.

Ví dụ:

~~~http
Access-Control-Expose-Headers: X-Trace-Id, X-Request-Region
~~~

Sau đó:

~~~javascript
const traceId = response.headers.get("X-Trace-Id");
~~~

Set-Cookie là forbidden response-header name và không thể được JavaScript đọc thông qua Access-Control-Expose-Headers. Dùng Network hoặc công cụ kiểm tra cookie của trình duyệt để xác minh Set-Cookie.

## 8. Kiểm thử cấu hình sai và lỗi thường gặp

| Cấu hình hoặc tình huống | Triệu chứng trong trình duyệt | Cách xác minh |
|---|---|---|
| Thiếu Access-Control-Allow-Origin | Fetch reject dù server có thể trả HTTP 200 | Xem response header và Origin request |
| Origin sai scheme, host hoặc port | Một môi trường chạy được, môi trường khác bị chặn | So sánh location.origin với giá trị allowlist |
| Dùng wildcard cùng credentials include | Console báo wildcard không được phép với credentials | Kiểm tra ACAO và ACAC |
| Thiếu method trong preflight response | OPTIONS không đạt CORS check, request thật không gửi | So sánh Access-Control-Request-Method với ACAM |
| Thiếu request header trong allowlist | Preflight bị chặn khi có header tùy chỉnh | So sánh ACR-Headers với ACAH |
| Không xử lý OPTIONS | Server trả 404, 405 hoặc redirect | Xem request OPTIONS trong Network |
| OPTIONS yêu cầu đăng nhập cookie | Preflight thất bại vì preflight không mang credentials | Cho OPTIONS kiểm tra policy CORS mà không đòi cookie; xác thực request thực tế |
| Origin động nhưng thiếu Vary: Origin | Cache có thể trả header của origin khác | Kiểm tra cache/CDN và response Vary |
| Dùng Access-Control-Expose-Headers sai | Fetch thành công nhưng JavaScript đọc header trả null | Kiểm tra safelisted response headers và ACEH |
| Cookie không được gửi | CORS thành công nhưng server không thấy cookie | Kiểm tra credentials mode, SameSite, Secure và cookie policy |
| Redirect ở preflight hoặc giữa các bước | Trình duyệt báo lỗi CORS hoặc redirect không được chấp nhận | Xem status, Location và chuỗi request |
| Server trả 401/403 | JavaScript có thể thấy lỗi CORS hoặc HTTP tùy header trên response lỗi | Kiểm tra status và CORS header cả trên response lỗi |

CORS error trong Console thường không cho biết toàn bộ nguyên nhân. Luôn xem Network để xác định request đã gửi hay chưa, status nào được trả, response header có gì và lỗi xảy ra ở OPTIONS hay request thực tế.

## 9. Kiểm thử bằng DevTools

### 9.1. Quy trình quan sát

1. Mở DevTools trước khi chạy test.
2. Chọn Network và bật Preserve log nếu cần theo dõi chuyển hướng.
3. Xóa danh sách request cũ.
4. Bấm một nút lab để tạo đúng một request.
5. Lọc theo tên endpoint hoặc OPTIONS.
6. Mở từng request, xem Headers, Payload, Response và Timing.
7. Ghi lại Origin, method, request headers, status và CORS response headers.
8. Đối chiếu kết quả với giả thuyết của test case.
9. Chụp bằng chứng đã che token, cookie, query nhạy cảm và dữ liệu người dùng.

### 9.2. Đọc preflight trong Network

Trong request OPTIONS, tập trung vào:

- Request URL và Origin.
- Access-Control-Request-Method.
- Access-Control-Request-Headers.
- Status code của response.
- Access-Control-Allow-Origin.
- Access-Control-Allow-Methods.
- Access-Control-Allow-Headers.
- Access-Control-Allow-Credentials nếu luồng có credentials.
- Vary và Access-Control-Max-Age.

Nếu OPTIONS thành công nhưng POST không xuất hiện, kiểm tra xem có lỗi JavaScript trước khi fetch, lỗi mạng hoặc request bị hủy hay không. Nếu POST xuất hiện nhưng response không đọc được, kiểm tra CORS header trên chính response POST, không chỉ response OPTIONS.

### 9.3. Đọc lỗi Console

Một số thông báo thường gặp:

- No Access-Control-Allow-Origin header: response thiếu ACAO hoặc response lỗi không có CORS header.
- The value of Access-Control-Allow-Origin must not be the wildcard when credentials mode is include: dùng wildcard với credentialed request.
- Request header field is not allowed by Access-Control-Allow-Headers: thiếu header trong ACAH.
- Method is not allowed by Access-Control-Allow-Methods: thiếu method trong ACAM.
- Response to preflight request doesn't pass access control check: preflight trả status hoặc header không hợp lệ.

Thông báo có thể khác theo trình duyệt và phiên bản. Dùng Network để tìm request đầu tiên thất bại.

## 10. Kiểm tra header bằng curl

curl.exe có thể gửi header Origin và hiển thị response header:

~~~powershell
curl.exe -i -H "Origin: http://127.0.0.1:5500" http://127.0.0.1:8000/simple
~~~

Kiểm tra preflight:

~~~powershell
curl.exe -i -X OPTIONS http://127.0.0.1:8000/update -H "Origin: http://127.0.0.1:5500" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type,x-demo-key"
~~~

Kiểm tra origin bị từ chối:

~~~powershell
curl.exe -i -H "Origin: http://127.0.0.1:5501" http://127.0.0.1:8000/simple
~~~

Khi đọc kết quả, xác nhận status, ACAO, ACAC, ACAM, ACAH và Vary. Với preflight, kiểm tra response có cho phép method và header đã yêu cầu hay không.

curl không thực thi chính sách CORS của trình duyệt. Nó sẽ hiển thị response kể cả khi một trình duyệt sẽ chặn JavaScript đọc response. Người gọi curl cũng có thể tự đặt Origin, vì vậy Origin không phải bằng chứng xác thực danh tính. Dùng curl để kiểm tra cấu hình HTTP phía server; dùng trình duyệt để xác minh hành vi CORS thực tế.

## 11. CORS và CSRF: hai mục tiêu kiểm thử khác nhau

CORS và CSRF thường bị nhầm lẫn vì cả hai đều liên quan request cross-origin, nhưng chúng giải quyết vấn đề khác nhau.

- CORS kiểm soát JavaScript của origin nào được đọc response cross-origin.
- CSRF là hành vi khiến trình duyệt của người dùng gửi request đã được xác thực ngoài ý muốn đến một website.
- SameSite cookie giúp hạn chế việc cookie được gửi trong một số ngữ cảnh cross-site.
- CSRF token, kiểm tra Origin/Referer phù hợp và xác nhận bổ sung bảo vệ thao tác thay đổi trạng thái ở phía server.
- Xác thực và authorization vẫn phải được kiểm tra trên từng API.

Một HTML form có thể gửi một số request cross-origin đơn giản mà không cần preflight. Trình duyệt có thể chặn JavaScript đọc response nhưng request vẫn tới server. Nếu endpoint thay đổi dữ liệu chỉ dựa vào cookie phiên và không có kiểm soát CSRF phù hợp, ứng dụng vẫn có thể bị tấn công.

Không thêm CORS allowlist rồi coi đó là biện pháp chống CSRF. Cần kiểm thử độc lập endpoint có thay đổi trạng thái, cách server xác minh CSRF token, cookie SameSite, Origin/Referer và quyền của tài khoản.

## 12. CORS và bảo mật API

Một cấu hình CORS đúng vẫn có thể đi cùng một API không an toàn. Khi kiểm thử API, hãy tách các lớp sau:

| Lớp | Câu hỏi kiểm tra |
|---|---|
| Network | DNS, TLS, kết nối và route có hoạt động không? |
| HTTP | Server trả status và response body nào? |
| CORS | Browser có cho JavaScript đọc response không? |
| Authentication | Request có danh tính hợp lệ không? |
| Authorization | Danh tính đó có quyền truy cập tài nguyên này không? |
| CSRF | Request dùng cookie phiên có được bảo vệ khỏi hành động giả mạo không? |
| Validation | Body, query và header có được kiểm tra không? |
| Rate limiting | API có giới hạn tần suất phù hợp không? |

CORS allowlist không nên dùng để quyết định một người dùng có được đọc dữ liệu tài khoản hay không. Một client ngoài trình duyệt có thể gọi API trực tiếp. Máy chủ phải dựa trên session, token hoặc cơ chế xác thực phù hợp và kiểm tra quyền nghiệp vụ.

Không phản chiếu Origin tùy tiện. Tránh kiểm tra bằng chuỗi con hoặc hậu tố lỏng lẻo như chỉ tìm thấy trusted.example trong origin. Hãy parse URL và so sánh origin đã chuẩn hóa với allowlist đầy đủ. Không cho phép null một cách mặc định; opaque origin có thể gửi Origin: null trong một số ngữ cảnh như tài liệu sandbox hoặc file.

## 13. Ma trận kiểm thử CORS

Dùng ma trận sau để kiểm thử API trước khi triển khai. Điền kết quả thực tế, status, header và ảnh chụp Network cho mỗi ca.

| ID | Origin | Method | Request header / credentials | Kết quả mong đợi |
|---|---|---|---|---|
| CORS-01 | Được phép | GET | Header safelisted | Không preflight; JavaScript đọc response |
| CORS-02 | Không được phép | GET | Header safelisted | Request có thể đến server; JavaScript không đọc response |
| CORS-03 | Được phép | POST | Content-Type: text/plain | Không preflight nếu không có header ngoài safelist |
| CORS-04 | Được phép | POST | Content-Type: application/json | Có OPTIONS; POST chỉ gửi khi preflight hợp lệ |
| CORS-05 | Được phép | POST | X-Demo-Key | Có OPTIONS; ACAH phải cho phép header |
| CORS-06 | Được phép | PUT | Method PUT | OPTIONS thất bại vì PUT chưa được allowlist; request thực tế không gửi |
| CORS-07 | Không được phép | POST | JSON hoặc header tùy chỉnh | OPTIONS bị từ chối; request thực tế không gửi |
| CORS-08 | Được phép | GET | credentials: include, cookie phù hợp | ACAO cụ thể, ACAC true và cookie policy cho phép |
| CORS-09 | Được phép | GET | credentials: include, ACAO là * | Trình duyệt không cho JavaScript đọc response |
| CORS-10 | Được phép | GET | Đọc X-Trace-Id | Chỉ đọc được nếu header được expose |
| CORS-11 | Được phép | GET | Response theo Origin động | Có Vary: Origin |
| CORS-12 | Origin null | GET | Opaque origin | Bị từ chối nếu null không nằm trong policy rõ ràng |

### 13.1. Tiêu chí PASS

Một ca kiểm thử chỉ PASS khi:

- Request được gửi đúng như dự kiến.
- Nếu có preflight, OPTIONS chứa đúng Origin, method và request header dự kiến.
- Server trả status và CORS response header phù hợp với policy.
- Trình duyệt cho phép hoặc chặn JavaScript đọc response đúng như mong đợi.
- Với credentials, request header, cookie policy, ACAO và ACAC đều phù hợp.
- Không có dữ liệu nhạy cảm xuất hiện trong log, URL hoặc ảnh chụp bằng chứng.
- Kết quả được ghi lại với browser, version, origin và thời điểm kiểm thử.

Không đánh dấu PASS chỉ vì curl nhận HTTP 200. Phải xác minh trong trình duyệt, vì curl không áp dụng CORS enforcement.

### 13.2. Mẫu ghi nhận kết quả

| Trường | Giá trị cần ghi |
|---|---|
| Test ID | CORS-xx |
| Ngày giờ | Thời điểm thực hiện và múi giờ |
| Browser | Tên và phiên bản |
| Frontend origin | Scheme, host, port |
| API URL | URL endpoint |
| Method | GET, POST, PUT, PATCH, DELETE... |
| Request headers | Danh sách header liên quan |
| Credentials | omit, same-origin hoặc include |
| Preflight | Có/không; status và response header |
| Actual response | Status và CORS response header |
| Console | Thông báo lỗi hoặc không có lỗi |
| Kết quả | PASS/FAIL và lý do |
| Bằng chứng | Ảnh Network đã che dữ liệu nhạy cảm |

## 14. Cách xử lý khi kết quả không như mong đợi

Đi theo thứ tự từ request đến response:

1. **Xác định origin thực tế.** Đọc location.origin ở trang gọi API, không tự suy ra từ hostname nhìn thấy trên thanh địa chỉ.
2. **Xác định request có được gửi không.** Network có OPTIONS, request thực tế hay không có request nào?
3. **Nếu có OPTIONS, kiểm tra preflight trước.** Đối chiếu Access-Control-Request-Method và Access-Control-Request-Headers với ACAM và ACAH.
4. **Nếu request thực tế được gửi, kiểm tra response thực tế.** CORS header phải có trên response mà JavaScript muốn đọc, bao gồm response lỗi nếu ứng dụng cần đọc lỗi đó.
5. **Kiểm tra credentials.** Xem fetch credentials mode, ACAO, ACAC, cookie attributes và chính sách cookie của browser.
6. **Kiểm tra cache và redirect.** Xem preflight cache, Vary, CDN, proxy và Location.
7. **Kiểm tra Console và server log.** Ghép thời điểm request, request ID và status để tìm đúng lỗi.
8. **Lặp lại với một ca tối giản.** Bỏ header tùy chỉnh hoặc credentials để cô lập nguyên nhân, rồi thêm từng điều kiện trở lại.

Một số tình huống cần phân biệt:

- Nếu Console báo CORS nhưng server log có request, có thể request đã tới server và response bị chặn.
- Nếu chỉ có OPTIONS và không có POST, preflight có thể thất bại.
- Nếu không có OPTIONS lẫn request thực tế, xem lại code phía client, DNS, TLS, mixed content hoặc lỗi JavaScript trước khi fetch.
- Nếu server trả 401 hoặc 403, kiểm tra authentication và authorization. Response lỗi cũng cần CORS header nếu frontend được phép đọc nội dung lỗi.
- Nếu curl hoạt động nhưng browser thất bại, kiểm tra preflight, Origin, credentials, cookie và redirect trong DevTools.

## 15. Những lỗi thiết kế cần tránh

**Phản chiếu mọi Origin.** Trả lại bất kỳ Origin nào nhận được có thể cấp quyền đọc response cho website do kẻ tấn công kiểm soát. Dùng allowlist rõ ràng.

**Dùng wildcard cho response nhạy cảm.** Wildcard phù hợp với dữ liệu thực sự công khai. Với dữ liệu gắn với người dùng hoặc credentials, chỉ định origin cụ thể và kiểm tra danh tính, quyền ở server.

**Cho phép mọi method và header theo thói quen.** Chỉ cho phép những method và request header cần thiết. Authorization cần được khai báo rõ.

**Coi preflight là lớp xác thực.** OPTIONS không xác thực người dùng và không thay thế authorization. Request có thể được gửi từ client không áp dụng CORS.

**Bỏ kiểm tra CSRF vì đã có CORS.** Simple request có thể được gửi mà không cần preflight. Endpoint thay đổi trạng thái vẫn cần phòng vệ CSRF.

**Không thêm Vary: Origin khi response động.** Cache có thể dùng response của origin này cho origin khác. Cấu hình cache phải phù hợp với cách server phản hồi origin.

**Coi credentials: include là đủ để gửi cookie.** SameSite, Secure, third-party cookie blocking, partitioning và domain/path vẫn có thể ngăn cookie.

**Chỉ kiểm tra trên một trình duyệt.** Hãy kiểm tra các trình duyệt mục tiêu và phiên bản được hỗ trợ vì thông báo lỗi, cache và chính sách cookie có thể khác nhau.

## 16. Checklist trước khi đóng một CORS test

- [ ] Ghi rõ origin của frontend và API.
- [ ] Kiểm tra origin khác scheme, host và port.
- [ ] Thử simple GET và simple POST.
- [ ] Thử Content-Type application/json và custom request header để kích hoạt preflight.
- [ ] Kiểm tra OPTIONS status, ACAO, ACAM, ACAH và ACAC.
- [ ] Xác minh request thực tế có được gửi sau preflight hay không.
- [ ] Thử origin được phép và origin bị từ chối.
- [ ] Thử credentials include và kiểm tra cookie policy.
- [ ] Kiểm tra wildcard với credentials bị từ chối.
- [ ] Kiểm tra Access-Control-Expose-Headers.
- [ ] Kiểm tra Vary: Origin khi response động.
- [ ] Kiểm tra response 401/403 và redirect.
- [ ] Xác minh CSRF độc lập với CORS.
- [ ] Đối chiếu kết quả curl với hành vi thực tế trong browser.
- [ ] Lưu bằng chứng đã che thông tin nhạy cảm và ghi browser/version.

## 17. Câu hỏi tự kiểm tra

### Câu 1

Hai trang có URL http://127.0.0.1:5500 và http://127.0.0.1:8000. Chúng có cùng origin không?

A. Có, vì host giống nhau.  
B. Không, vì port khác nhau.  
C. Có, vì đều dùng HTTP.  
D. Chỉ khác origin khi path khác nhau.

**Đáp án: B.** Origin gồm scheme, host và port. Hai cổng khác nhau tạo hai origin khác nhau.

### Câu 2

Một GET cross-origin dùng các header safelisted. Khi server thiếu Access-Control-Allow-Origin, điều gì có thể xảy ra?

A. Trình duyệt luôn chặn request trước khi gửi.  
B. Request có thể đến server nhưng JavaScript không được đọc response.  
C. Server tự động trả 401.  
D. Trình duyệt tự thêm ACAO.

**Đáp án: B.** CORS check có thể chặn quyền đọc response sau khi simple request đã được gửi.

### Câu 3

POST dùng Content-Type application/json thường có đặc điểm gì?

A. Luôn là simple request.  
B. Thường cần preflight vì Content-Type này không nằm trong CORS-safelisted Content-Type values.  
C. Không được trình duyệt hỗ trợ.  
D. Chỉ chạy khi có cookie.

**Đáp án: B.** Trình duyệt thường gửi OPTIONS trước request JSON.

### Câu 4

Header nào cho server biết method mà request thực tế muốn dùng trong preflight?

A. Access-Control-Allow-Methods.  
B. Access-Control-Request-Method.  
C. Access-Control-Expose-Headers.  
D. Vary.

**Đáp án: B.** Request OPTIONS chứa Access-Control-Request-Method; server phản hồi bằng Access-Control-Allow-Methods.

### Câu 5

Một request dùng credentials: include. Response nào phù hợp?

A. Access-Control-Allow-Origin: * và Access-Control-Allow-Credentials: true.  
B. Access-Control-Allow-Origin: origin cụ thể và Access-Control-Allow-Credentials: true.  
C. Chỉ cần Access-Control-Allow-Methods.  
D. Không cần CORS header.

**Đáp án: B.** Credentialed request yêu cầu origin cụ thể và ACAC có giá trị true.

### Câu 6

Preflight request có mang cookie phiên của request thực tế không?

A. Có, luôn gửi toàn bộ cookie.  
B. Không, CORS preflight request không mang credentials của request thực tế.  
C. Chỉ mang cookie HttpOnly.  
D. Chỉ mang cookie SameSite=None.

**Đáp án: B.** Server không nên yêu cầu cookie đăng nhập để xử lý OPTIONS preflight.

### Câu 7

JavaScript gọi response.headers.get("X-Trace-Id") nhưng nhận null dù response có header đó. Nguyên nhân có thể là gì?

A. Header không được expose qua Access-Control-Expose-Headers.  
B. Header luôn bị trình duyệt xóa khỏi Network.  
C. Request phải dùng POST.  
D. Phải bật credentials: include.

**Đáp án: A.** Header không thuộc safelisted response headers cần được server expose.

### Câu 8

Tại sao server cần Vary: Origin khi Access-Control-Allow-Origin thay đổi theo Origin request?

A. Để bật TLS.  
B. Để cache phân biệt response theo Origin và tránh dùng nhầm response.  
C. Để buộc browser gửi cookie.  
D. Để bỏ qua preflight.

**Đáp án: B.** Vary giúp cache hiểu response phụ thuộc request header Origin.

### Câu 9

curl nhận HTTP 200 nhưng fetch trong browser báo CORS. Kết luận phù hợp nhất là gì?

A. curl đã chứng minh CORS hoạt động.  
B. curl không áp dụng CORS enforcement; cần kiểm tra response header và luồng request trong browser.  
C. Browser luôn sai khi khác curl.  
D. Chỉ cần đổi method sang POST.

**Đáp án: B.** curl kiểm tra HTTP response, còn browser thực thi CORS.

### Câu 10

Vì sao cấu hình CORS không thay thế CSRF token?

A. Vì CORS chỉ áp dụng với HTTPS.  
B. Vì một số request cross-origin đơn giản vẫn có thể được gửi dù response bị chặn khỏi JavaScript.  
C. Vì CSRF chỉ xảy ra trên cùng origin.  
D. Vì preflight luôn gửi cookie.

**Đáp án: B.** CSRF bảo vệ thao tác được xác thực; CORS chủ yếu kiểm soát việc đọc response.

### Câu 11

Một server cho phép mọi origin bằng cách sao chép nguyên văn Origin request vào Access-Control-Allow-Origin. Rủi ro chính là gì?

A. Không thể gửi OPTIONS.  
B. Website không tin cậy có thể được phép đọc response nếu các điều kiện CORS khác phù hợp.  
C. Trình duyệt sẽ tự đổi host.  
D. Cookie tự động bị xóa.

**Đáp án: B.** Server cần xác minh Origin với allowlist thay vì phản chiếu tùy ý.

### Câu 12

Nếu OPTIONS thất bại, request POST cần preflight sẽ thế nào?

A. Browser vẫn gửi POST rồi bỏ qua response.  
B. Browser không gửi request thực tế theo luồng CORS.  
C. Browser chuyển POST thành GET.  
D. Server tự động thử lại bằng curl.

**Đáp án: B.** Preflight phải thành công trước khi browser gửi request thực tế.

## 18. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Origin | Bộ ba scheme, host và port |
| Cross-origin | Hai URL có ít nhất một thành phần origin khác nhau |
| Same-site | Khái niệm dùng trong một số chính sách cookie, khác với origin |
| CORS | Cơ chế chia sẻ tài nguyên cross-origin do browser thực thi theo response header |
| Simple request | Request đáp ứng điều kiện CORS-safelisted nên không cần preflight |
| Preflight | Request OPTIONS kiểm tra method và header dự kiến |
| Credentials mode | Chế độ Fetch quyết định việc gửi credentials trong request |
| Allowlist | Danh sách origin được máy chủ cho phép |
| ACAO | Access-Control-Allow-Origin |
| ACAM | Access-Control-Allow-Methods |
| ACAH | Access-Control-Allow-Headers |
| ACAC | Access-Control-Allow-Credentials |
| ACEH | Access-Control-Expose-Headers |
| Vary | Response header hướng dẫn cache phân biệt biến thể response theo request header |
| CSRF | Giả mạo request đã được xác thực từ trình duyệt người dùng |
| Opaque origin | Origin không có bộ ba scheme/host/port thông thường, có thể được biểu diễn là null |

## Tài liệu tham khảo

- WHATWG — [Fetch Standard: CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): định nghĩa CORS protocol, preflight và các thuật toán kiểm tra.
- MDN Web Docs — [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): tổng quan CORS, simple request, preflight và response header.
- MDN Web Docs — [CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS/Errors): cách nhận diện và xử lý lỗi CORS trong trình duyệt.
- MDN Web Docs — [Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Origin): cú pháp và cách dùng ACAO.
- MDN Web Docs — [Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Credentials): yêu cầu khi response được dùng với credentials.
- MDN Web Docs — [Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Headers): kiểm soát request header trong preflight.
- MDN Web Docs — [Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Expose-Headers): công khai response header cho JavaScript.
- MDN Web Docs — [Using Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): Fetch, credentials và xử lý response.
- OWASP — [Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): phòng vệ CSRF và mối quan hệ với request cross-origin.

CORS là chính sách được browser thực thi, còn cấu hình server và kiểm soát truy cập ứng dụng cần được đánh giá riêng. Khi kiểm thử thực tế, đối chiếu hành vi với Fetch Standard và tài liệu của các trình duyệt mục tiêu.

