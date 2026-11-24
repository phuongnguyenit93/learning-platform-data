# Fetch API: gửi request và xử lý response an toàn

## 1. Fetch API là gì?

**Fetch API** là giao diện JavaScript hiện đại để gửi HTTP request và nhận response từ tài nguyên trên mạng. API này được dùng để gọi backend, tải JSON, gửi form, tải file, đọc stream và giao tiếp với các endpoint khác. Fetch hoạt động bất đồng bộ và trả về Promise.

Ví dụ đơn giản:

~~~js
const response = await fetch("/api/profile");
const profile = await response.json();

console.log(profile);
~~~

Khi chạy trong trang HTTPS, URL tương đối được resolve theo URL của document. Nếu trang ở `https://app.example.test`, request trên thường gọi `https://app.example.test/api/profile`.

Fetch API cung cấp các đối tượng chính:

- Request: mô tả request gồm URL, method, headers, body và các tùy chọn.
- Response: biểu diễn response nhận được, gồm status, headers, body và metadata.
- Headers: quản lý request/response headers.
- AbortController và AbortSignal: hủy request hoặc nhóm tác vụ bất đồng bộ.
- ReadableStream: đọc hoặc xử lý dữ liệu theo từng phần khi browser và response hỗ trợ.

Fetch là API phía client. Nó chịu các chính sách của browser như Same-Origin Policy, CORS, CSP, mixed content, cookie policy và service worker interception. Việc gọi fetch thành công không chứng minh người dùng được phép truy cập dữ liệu; backend vẫn phải xác thực và phân quyền.

Bài học thuộc chương **Fetch và XMLHttpRequest** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; nghiên cứu Same-Origin Policy, CORS, XSS, CSRF, clickjacking, CSP, Trusted Types và security headers. Bài này tập trung vào Fetch API: tạo request, xử lý response, quản lý body/headers, credentials, CORS, cache, redirect, hủy request, lỗi mạng và các thực hành an toàn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Tạo request bằng fetch(), Request và các tùy chọn RequestInit.
2. Phân biệt lỗi mạng với HTTP error status.
3. Kiểm tra Response.ok, status, headers và content type.
4. Đọc JSON, text, Blob, ArrayBuffer, FormData và stream.
5. Gửi JSON, URLSearchParams, FormData và file.
6. Hiểu body chỉ đọc một lần và cách dùng clone().
7. Cấu hình method, headers, credentials, mode và redirect.
8. Phân biệt CORS, preflight, SOP, CSP và mixed content.
9. Dùng AbortController để hủy request và quản lý timeout.
10. Thiết kế retry có giới hạn, tôn trọng idempotency và Retry-After.
11. Xử lý cache, referrer policy và dữ liệu nhạy cảm.
12. Debug request bằng DevTools và xây dựng API client có kiểm soát.

## 2. Fetch hoạt động theo mô hình Promise

Lời gọi fetch() trả về Promise<Response>. Promise thường resolve khi browser nhận được response headers, ngay cả khi server trả HTTP status như 400, 401, 404 hoặc 500.

Ví dụ:

~~~js
const response = await fetch("/api/not-found");

console.log(response.status); // 404
console.log(response.ok);     // false
~~~

Đoạn code không nhất thiết đi vào catch chỉ vì server trả 404. Đây là khác biệt quan trọng so với một số HTTP client library.

### 2.1. Khi nào Fetch reject?

Fetch thường reject khi request không thể hoàn tất ở tầng Fetch/network, ví dụ:

- Lỗi DNS, kết nối hoặc TLS.
- Request bị browser chặn bởi CORS.
- Mixed content hoặc CSP chặn request.
- URL không hợp lệ hoặc có lỗi cấu hình request.
- Request bị hủy bằng AbortSignal.
- Một số lỗi nền tảng khiến browser không thể tạo response.

Browser thường không cho JavaScript biết chi tiết nhạy cảm của lỗi CORS. Ứng dụng có thể chỉ nhận TypeError hoặc lỗi fetch tổng quát. Hãy dùng Console và Network để tìm policy thực sự gây lỗi.

### 2.2. HTTP status không phải network error

Quy tắc xử lý phổ biến:

~~~js
const response = await fetch("/api/orders");

if (!response.ok) {
  throw new Error("HTTP error: " + response.status);
}

const orders = await response.json();
~~~

Response.ok là true với status trong khoảng 200–299. 304 Not Modified là status dùng trong conditional request; HTTP cache của browser thường kết hợp response đã lưu với kết quả revalidation, nên script thường nhận representation có thể sử dụng thay vì phải tự xử lý một response 304 thô.

Không bỏ qua status và gọi response.json() như thể mọi response đều là JSON thành công. API có thể trả 204 No Content, HTML lỗi từ proxy, hoặc JSON error payload với status 4xx/5xx.

## 3. Tạo request bằng fetch()

Cú pháp cơ bản:

~~~js
fetch(input, init);
~~~

- input là URL string hoặc một Request object.
- init là đối tượng tùy chọn để thiết lập method, headers, body, mode, credentials, cache, redirect, signal và các thuộc tính khác.

Ví dụ:

~~~js
const response = await fetch("/api/orders?limit=20", {
  method: "GET",
  headers: {
    Accept: "application/json"
  },
  credentials: "same-origin"
});
~~~

Nếu init bỏ qua một thuộc tính, Fetch có thể dùng thuộc tính từ Request đầu vào hoặc giá trị mặc định. Khi cần hành vi rõ ràng, khai báo các tùy chọn quan trọng một cách tường minh.

### 3.1. Dùng URL và URLSearchParams

Không ghép query string bằng nối chuỗi thủ công nếu giá trị có thể chứa dấu cách, dấu &, dấu = hoặc ký tự Unicode.

~~~js
const url = new URL("/api/search", window.location.origin);
url.search = new URLSearchParams({
  q: "browser security",
  page: "2",
  sort: "recent"
}).toString();

const response = await fetch(url);
~~~

URLSearchParams encode các giá trị query theo quy tắc URL. Nếu URL hoặc origin lấy từ input không tin cậy, cần kiểm tra protocol và allowlist origin trước khi gửi request.

### 3.2. Request object

Có thể tạo Request trước rồi truyền vào fetch:

~~~js
const request = new Request("/api/profile", {
  method: "GET",
  headers: {
    Accept: "application/json"
  }
});

const response = await fetch(request);
~~~

Request hữu ích khi cần tái sử dụng cấu hình hoặc truyền request giữa các hàm. Body của Request có thể là stream và thường chỉ tiêu thụ được một lần; không giả định cùng một Request có thể fetch lặp tùy ý sau khi body đã dùng.

### 3.3. Thứ tự ưu tiên cấu hình

Khi truyền một Request cùng init, các thuộc tính trong init có thể ghi đè cấu hình tương ứng của Request theo quy tắc constructor/fetch. Hãy tạo request ở một nơi rõ ràng và tránh merge cấu hình tùy tiện làm thay đổi method, credentials hoặc headers ngoài dự kiến.

## 4. Method và ngữ nghĩa HTTP

Các method thường dùng:

| Method | Mục đích thường gặp | Ghi chú |
| --- | --- | --- |
| GET | Đọc tài nguyên | Không gửi request body. |
| HEAD | Đọc headers/metadata | Response không có body. |
| POST | Tạo hoặc thực hiện hành động | Thường không idempotent; cần kiểm soát retry. |
| PUT | Tạo/thay thế trạng thái tại URI | Theo ngữ nghĩa HTTP, idempotent nếu server triển khai đúng. |
| PATCH | Cập nhật một phần | Idempotency phụ thuộc thiết kế operation. |
| DELETE | Xóa tài nguyên | Method được định nghĩa idempotent, nhưng response/side effect triển khai vẫn cần kiểm tra. |

Ví dụ GET:

~~~js
const response = await fetch("/api/products", {
  method: "GET"
});
~~~

Ví dụ DELETE:

~~~js
const response = await fetch("/api/products/42", {
  method: "DELETE"
});
~~~

Không đặt body cho GET hoặc HEAD theo thói quen. Browser Fetch không hỗ trợ request body cho các method này. Với thao tác thay đổi trạng thái, backend phải xác thực, phân quyền, validate dữ liệu và bảo vệ CSRF khi dùng cookie-based authentication.

## 5. Request headers

Headers truyền metadata về request như kiểu dữ liệu mong muốn, content type, authorization và các điều kiện cache.

~~~js
const response = await fetch("/api/profile", {
  headers: {
    Accept: "application/json",
    "X-Request-ID": "req-demo-001"
  }
});
~~~

Tên header không phân biệt chữ hoa/chữ thường theo HTTP. Một số header do browser kiểm soát hoặc bị cấm để script tự đặt, ví dụ Host, Cookie, Content-Length và một số header kết nối. Browser tự quản lý các header như Origin và Cookie theo ngữ cảnh request.

### 5.1. Dùng Headers object

~~~js
const headers = new Headers();

headers.set("Accept", "application/json");
headers.set("X-Request-ID", "req-demo-001");

const response = await fetch("/api/profile", { headers });
~~~

Headers API chuẩn hóa và kiểm soát header theo guard tương ứng. Một số header không thể tự đặt từ JavaScript trang; không tìm cách vượt qua giới hạn này bằng cách đổi tên header.

### 5.2. Authorization header

Nếu API dùng bearer token, request có thể có:

~~~js
const response = await fetch("/api/private", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Chỉ gửi token tới origin API được tin cậy qua HTTPS. Không đặt token trong URL, không log token và không cho user input tùy ý chọn API origin. Cân nhắc kiến trúc session cookie HttpOnly/Secure/SameSite khi phù hợp; bearer token phía JavaScript có thể bị lấy nếu XSS chạy trong origin.

### 5.3. Không tự đặt Cookie header

JavaScript browser không được tùy ý đặt Cookie request header. Browser tự quyết định cookie nào được gửi dựa trên cookie store, domain, path, Secure, SameSite, credentials mode và chính sách privacy.

Nếu cần xác thực cookie, cấu hình server Set-Cookie đúng thuộc tính và fetch credentials phù hợp. Không cố gửi cookie bằng custom header.

## 6. Gửi JSON

JSON thường được gửi bằng cách serialize object:

~~~js
const payload = {
  displayName: "An",
  notificationsEnabled: true
};

const response = await fetch("/api/profile", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json"
  },
  body: JSON.stringify(payload)
});
~~~

JSON.stringify() tạo string. Content-Type báo cho server biết định dạng request body.

### 6.1. Kiểm tra response status và body

~~~js
if (!response.ok) {
  const message = await response.text();
  throw new Error("API error " + response.status + ": " + message);
}

const result = await response.json();
~~~

Trong production, không đưa toàn bộ response lỗi vào UI hoặc log nếu nó có thể chứa stack trace, PII hoặc dữ liệu nội bộ. Chuyển lỗi thành thông báo an toàn và correlation ID phù hợp.

### 6.2. JSON parse có thể thất bại

response.json() đọc body rồi parse JSON. Nó reject nếu body không hợp lệ hoặc không thể đọc.

Các trường hợp thường gặp:
- Server trả HTML trang lỗi.
- Response rỗng trong khi code vẫn gọi json().
- Proxy trả trang đăng nhập thay vì API JSON.
- JSON bị cắt hoặc sai định dạng.
- Response body đã được tiêu thụ trước đó.

Kiểm tra status, content type và quy ước API. Với 204 No Content, không gọi json().

## 7. Gửi FormData và file upload

FormData phù hợp gửi form fields và file theo multipart/form-data:

~~~js
const formData = new FormData();

formData.append("title", "Ảnh đại diện");
formData.append("avatar", fileInput.files[0]);

const response = await fetch("/api/avatar", {
  method: "POST",
  body: formData
});
~~~

Browser tự tạo multipart boundary và Content-Type tương ứng. **Không tự đặt Content-Type: multipart/form-data** trong request này vì header cần chứa boundary mà browser tạo. Nếu tự ghi đè, server có thể không parse được body.

### 7.1. FormData từ form HTML

~~~js
const form = document.querySelector("#profile-form");
const formData = new FormData(form);

const response = await fetch(form.action, {
  method: form.method || "POST",
  body: formData
});
~~~

FormData lấy các control có name và đang được submit theo quy tắc form. Validate dữ liệu ở client để hỗ trợ UX, nhưng server phải kiểm tra loại file, kích thước, nội dung, quyền truy cập và tên file.

### 7.2. File upload và giới hạn

Client có thể kiểm tra size/type để báo lỗi sớm, nhưng metadata MIME từ client không đáng tin cậy. Server cần xác minh nội dung file, giới hạn dung lượng, lưu trữ an toàn và chống thực thi file upload.

Fetch API không có sự kiện upload progress tương đương XMLHttpRequest.upload.onprogress phổ biến trong browser. Nếu giao diện cần progress upload chi tiết và tương thích rộng, XMLHttpRequest vẫn là lựa chọn thực tế cho phần upload.

## 8. URLSearchParams và form-urlencoded

Để gửi dữ liệu application/x-www-form-urlencoded:

~~~js
const body = new URLSearchParams({
  username: "an",
  remember: "true"
});

const response = await fetch("/login/preferences", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
  },
  body
});
~~~

URLSearchParams tự encode key/value theo định dạng form URL-encoded. Không nối chuỗi thủ công nếu dữ liệu có ký tự đặc biệt.

Định dạng này thường dùng với endpoint form legacy. Authentication và CSRF defense vẫn phải được xử lý theo thiết kế server.

## 9. Đọc Response

Fetch trả về Response object. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| status | HTTP status code. |
| statusText | Status text do browser cung cấp; có thể rỗng hoặc không hữu ích. |
| ok | true nếu status thuộc 200–299. |
| headers | Headers của response mà script được phép đọc. |
| url | URL cuối cùng của response sau redirect trong các trường hợp thông thường. |
| redirected | Cho biết request đã được redirect. |
| type | Loại response như basic, cors, opaque hoặc opaqueredirect. |
| body | ReadableStream của response body nếu có. |
| bodyUsed | Cho biết body đã được tiêu thụ hay chưa. |

Ví dụ:

~~~js
console.log({
  status: response.status,
  ok: response.ok,
  url: response.url,
  redirected: response.redirected,
  type: response.type
});
~~~

Response headers cross-origin bị giới hạn bởi CORS. Server có thể cần Access-Control-Expose-Headers để JavaScript đọc một số response headers không nằm trong safelisted response headers.

## 10. Đọc JSON, text, Blob và ArrayBuffer

Response body có các phương thức tiêu thụ phổ biến:

| Phương thức | Kết quả |
| --- | --- |
| json() | Parse body thành JavaScript value. |
| text() | Đọc body thành string. |
| blob() | Đọc thành Blob. |
| arrayBuffer() | Đọc thành ArrayBuffer. |
| formData() | Parse form data khi response phù hợp. |
| bytes() | Trả Uint8Array trong browser hỗ trợ API mới này. |

Ví dụ text:

~~~js
const response = await fetch("/health");
const text = await response.text();
~~~

Ví dụ tải ảnh:

~~~js
const response = await fetch("/images/banner.png");

if (!response.ok) {
  throw new Error("Không tải được ảnh");
}

const imageBlob = await response.blob();
const objectUrl = URL.createObjectURL(imageBlob);

imageElement.src = objectUrl;
~~~

Khi không còn cần object URL, gọi URL.revokeObjectURL() để giải phóng tài nguyên. Không tạo object URL liên tục mà không cleanup.

### 10.1. Response body chỉ đọc một lần

Body là stream. Sau khi gọi json(), text(), blob() hoặc reader.read(), body thường được đánh dấu đã dùng. Gọi phương thức tiêu thụ thứ hai trên cùng Response sẽ lỗi.

~~~js
const response = await fetch("/api/profile");

const data = await response.json();
// Không gọi response.text() sau đó.
~~~

Nếu cần đọc cùng response theo hai nhánh, clone trước khi tiêu thụ:

~~~js
const response = await fetch("/api/profile");
const copy = response.clone();

const data = await response.json();
const raw = await copy.text();
~~~

clone() tạo một bản sao response/stream theo cơ chế tee. Với body lớn, việc đọc cả hai nhánh có thể tăng bộ nhớ và buffering; chỉ clone khi thật sự cần.

## 11. Streaming response

Response.body có thể là ReadableStream. Thay vì chờ tải toàn bộ body rồi mới xử lý, ứng dụng có thể đọc từng chunk.

~~~js
const response = await fetch("/api/export");

if (!response.ok || !response.body) {
  throw new Error("Response không thể stream");
}

const reader = response.body.getReader();

while (true) {
  const { done, value } = await reader.read();

  if (done) break;

  processChunk(value);
}
~~~

value thường là Uint8Array. Ứng dụng có thể giải mã text bằng TextDecoder hoặc chuyển dữ liệu cho parser phù hợp.

### 11.1. Backpressure và cancel

ReadableStream cho phép consumer kiểm soát tốc độ đọc. Nếu không còn cần dữ liệu, có thể cancel reader:

~~~js
await reader.cancel("Không cần tải tiếp");
~~~

Cần xử lý lỗi đọc stream và giải phóng reader khi hoàn tất. Không giữ toàn bộ chunk trong array nếu mục tiêu là xử lý dữ liệu lớn với bộ nhớ giới hạn.

### 11.2. Giải mã text theo chunk

Một chunk không nhất thiết kết thúc đúng ranh giới ký tự UTF-8. Dùng TextDecoder với streaming option để giữ phần byte chưa hoàn chỉnh giữa các chunk:

~~~js
const decoder = new TextDecoder();
let output = "";

while (true) {
  const { done, value } = await reader.read();

  if (done) {
    output += decoder.decode();
    break;
  }

  output += decoder.decode(value, { stream: true });
}
~~~

Với dữ liệu rất lớn, nên xử lý từng đoạn thay vì nối tất cả thành một string lớn.

## 12. Body là tài nguyên có vòng đời

Request body có thể là string, Blob, FormData, URLSearchParams, ArrayBuffer, TypedArray, DataView hoặc ReadableStream tùy loại và hỗ trợ browser.

Một số body là stream và chỉ tiêu thụ được một lần. Khi retry request có body, cần tạo lại body hoặc tạo Request mới từ dữ liệu nguồn; không giả định body stream cũ có thể phát lại.

### 12.1. Streaming upload

Một số browser hỗ trợ gửi ReadableStream làm request body. Với request streaming, implementation Fetch yêu cầu tùy chọn `duplex: "half"`:

~~~js
const stream = createUploadStream();

const response = await fetch("/api/upload-stream", {
  method: "POST",
  body: stream,
  duplex: "half"
});
~~~

Streaming upload còn có giới hạn tương thích và yêu cầu về request mode/redirect. Kiểm tra browser mục tiêu trước khi dùng; với upload thông thường, Blob, File hoặc FormData thường đơn giản hơn. Không giả định stream body có thể replay sau lỗi.

Đặc biệt với upload file lớn, cân nhắc chunk/resumable upload ở tầng ứng dụng. Fetch không tự cung cấp cơ chế resume một upload đã bị ngắt.

## 13. Credentials và cookie

Fetch có tùy chọn credentials để điều khiển việc gửi credential và xử lý Set-Cookie:

| Giá trị | Hành vi khái quát |
| --- | --- |
| same-origin | Gửi credential cho request same-origin; đây là mặc định. |
| include | Cho phép gửi credential cả cross-origin, subject to cookie/browser policy. |
| omit | Không gửi credential và không xử lý credential theo chế độ thông thường. |

Ví dụ same-origin:

~~~js
const response = await fetch("/api/account", {
  credentials: "same-origin"
});
~~~

Ví dụ cross-origin cần cookie:

~~~js
const response = await fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

credentials: include không bảo đảm cookie chắc chắn được gửi. Cookie còn phụ thuộc Domain, Path, Secure, SameSite, partitioning và chính sách third-party cookie của browser.

### 13.1. Set-Cookie không đọc được từ JavaScript

Set-Cookie là forbidden response header name. JavaScript không thể đọc giá trị Set-Cookie qua response.headers.get("Set-Cookie"). Browser xử lý cookie theo cookie policy.

Để tạo cookie session an toàn, server thường dùng:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

HttpOnly ngăn JavaScript trang đọc cookie qua document.cookie. Nó không ngăn browser tự gửi cookie trong request phù hợp và không thay thế CSRF defense.

### 13.2. Credentials và CORS

Khi cross-origin request dùng credentials: include, server cần trả:
- Access-Control-Allow-Origin với origin cụ thể, không phải wildcard *.
- Access-Control-Allow-Credentials: true.
- Vary: Origin nếu response thay đổi theo Origin.

Không phản chiếu Origin tùy tiện mà không kiểm tra allowlist. CORS không phải authorization; server vẫn phải xác minh user và quyền truy cập.

## 14. CORS và preflight

Same-Origin Policy giới hạn việc script đọc response từ origin khác. CORS là cơ chế server dùng response headers để cho phép browser chia sẻ response cross-origin với script.

Ví dụ:
- App: `https://app.example.test`
- API: `https://api.example.test`

Đây là cross-origin vì host khác nhau. Fetch mặc định dùng mode cors cho request thông thường từ script.

### 14.1. Simple request và preflight

Một số request CORS có thể được gửi trực tiếp theo điều kiện safelisted method, headers và content type. Các request không đáp ứng điều kiện này có thể cần preflight OPTIONS trước request chính.

Ví dụ JSON với custom header thường kích hoạt preflight:

~~~js
fetch("https://api.example.test/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "req-123"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Browser có thể gửi OPTIONS và kiểm tra các header như:
- Access-Control-Request-Method.
- Access-Control-Request-Headers.
- Origin.

Server phản hồi bằng Access-Control-Allow-Origin, Access-Control-Allow-Methods và Access-Control-Allow-Headers phù hợp.

### 14.2. Preflight không phải CSRF defense

Một số request cross-origin có thể được gửi mà không cần preflight. CORS chủ yếu kiểm soát việc script đọc response, không thay thế cơ chế chống CSRF.

Nếu ứng dụng dùng cookie tự động gửi, endpoint thay đổi trạng thái cần CSRF protection phù hợp như token, kiểm tra Origin/Fetch Metadata, SameSite cookie và thiết kế method đúng. Không dựa vào việc request JSON thường cần preflight để coi API đã an toàn CSRF.

### 14.3. Expose response headers

Một số response headers không được script đọc cross-origin theo mặc định. Server có thể khai báo:

~~~http
Access-Control-Expose-Headers: X-Request-ID, Content-Disposition
~~~

Không expose toàn bộ headers nếu không cần. Đặc biệt không đưa credential hoặc metadata nội bộ vào header chỉ để frontend đọc.

## 15. mode: cors, same-origin và no-cors

Fetch Request mode kiểm soát cách request xử lý cross-origin:

| Mode | Hành vi |
| --- | --- |
| cors | Cho phép cross-origin request theo CORS; đây là mode phổ biến cho fetch từ trang. |
| same-origin | Nếu URL cross-origin, request bị từ chối. |
| no-cors | Giới hạn request và thường trả opaque response cho cross-origin. |

Ví dụ same-origin-only:

~~~js
const response = await fetch("/api/private", {
  mode: "same-origin"
});
~~~

### 15.1. no-cors không vượt CORS hoặc mixed content

no-cors không phải cách để đọc response cross-origin. Opaque response thường có type opaque, status 0, headers bị ẩn và body không đọc được từ JavaScript.

Request no-cors cũng bị giới hạn method và headers. Nó không biến endpoint HTTP thành HTTPS và không vượt qua mixed content blocking.

Dùng no-cors chỉ cho trường hợp cụ thể cần gửi request mà không cần đọc response và phù hợp với mô hình opaque response, chẳng hạn một số cache/resource use case. Không dùng nó để sửa lỗi CORS của API JSON.

## 16. CSP connect-src và mixed content

CSP directive connect-src giới hạn nguồn mà document có thể kết nối bằng fetch, XMLHttpRequest, WebSocket, EventSource và Beacon.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.test wss://realtime.example.test
~~~

Nếu API host không nằm trong allowlist, browser có thể chặn theo CSP ngay cả khi endpoint dùng HTTPS và CORS hợp lệ.

Trang HTTPS gọi HTTP API là mixed content và browser hiện đại chặn các request Fetch/XHR insecure. CORS header không biến HTTP thành kết nối an toàn. Dùng HTTPS cho API và kiểm tra redirect chain không downgrade về HTTP.

CSP connect-src, CORS và mixed content là các lớp khác nhau; một request có thể vượt qua một lớp nhưng bị lớp khác chặn.

## 17. Redirect behavior

Fetch mặc định dùng redirect: "follow", nghĩa là browser tự theo redirect trong phạm vi quy tắc Fetch/CORS/security.

Các lựa chọn:

| Giá trị | Hành vi |
| --- | --- |
| follow | Tự theo redirect; mặc định. |
| error | Reject nếu response là redirect. |
| manual | Trả response redirect theo chế độ manual; trong browser có thể là opaqueredirect và không cho script đọc Location cross-origin. |

Ví dụ từ chối redirect:

~~~js
const response = await fetch("/api/data", {
  redirect: "error"
});
~~~

redirect: "manual" không phải cách đọc mọi Location header hoặc né CORS. Browser áp dụng giới hạn để không lộ thông tin redirect cross-origin. Nếu API cần trả kết quả nghiệp vụ, thiết kế response JSON rõ ràng thay vì redirect bất ngờ.

### 17.1. Redirect có thể làm thay đổi method

Các status redirect 301, 302, 303, 307 và 308 có ngữ nghĩa khác nhau về việc giữ hoặc đổi method/body. Browser xử lý theo Fetch/HTTP rules. Với API thay đổi trạng thái, tránh redirect không cần thiết; kiểm tra Network redirect chain và bảo đảm request không bị chuyển tới origin ngoài dự kiến.

### 17.2. Không tin URL redirect tùy ý

Nếu server nhận URL returnTo/next từ người dùng, cần allowlist destination. Open redirect có thể dẫn người dùng tới trang giả mạo và làm rò rỉ dữ liệu trong một số luồng. Client cũng nên kiểm tra URL mà ứng dụng chủ động điều hướng tới.

## 18. Cache mode và HTTP caching

Fetch có tùy chọn cache điều khiển cách request tương tác với HTTP cache của browser:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| default | Browser áp dụng HTTP caching rules thông thường. |
| no-store | Bỏ qua cache và không lưu response vào HTTP cache theo chế độ Fetch này. |
| reload | Bỏ qua cache khi lấy response nhưng có thể cập nhật cache. |
| no-cache | Có thể dùng cache nhưng yêu cầu revalidation khi phù hợp; không đồng nghĩa không lưu. |
| force-cache | Ưu tiên response cache nếu có, kể cả response cũ theo điều kiện cache. |
| only-if-cached | Chỉ lấy từ cache; Fetch yêu cầu mode là same-origin. |

Ví dụ:

~~~js
const response = await fetch("/api/catalog", {
  cache: "no-cache"
});
~~~

### 18.1. no-cache khác no-store

- no-cache: response có thể được lưu nhưng cần revalidate trước khi tái sử dụng theo HTTP rules.
- no-store: yêu cầu không lưu response trong HTTP cache theo chế độ tương ứng.

Tên gọi dễ gây nhầm. Với dữ liệu nhạy cảm, server cần đặt Cache-Control phù hợp; không chỉ dựa vào client fetch option. Các cache khác như Cache Storage và service worker có logic riêng.

### 18.2. Dữ liệu cá nhân và cache

Response chứa thông tin tài khoản hoặc giao dịch cần policy cache rõ ràng, ví dụ Cache-Control: no-store khi không muốn browser HTTP cache lưu. Không cache response nhạy cảm trong Cache Storage nếu không có lý do offline, kiểm soát user namespace và cleanup.

Logout cần xử lý session server, cookie và các kho client có thể còn dữ liệu cá nhân.

## 19. Referrer và referrerPolicy

Fetch có thể kiểm soát referrer behavior bằng referrer và referrerPolicy theo giới hạn của browser.

Ví dụ:

~~~js
const response = await fetch("https://api.example.test/data", {
  referrerPolicy: "strict-origin-when-cross-origin"
});
~~~

Một số policy thường gặp:

- no-referrer: không gửi Referer.
- origin: chỉ gửi origin.
- strict-origin: gửi origin khi không downgrade.
- strict-origin-when-cross-origin: thường gửi full referrer same-origin và chỉ origin cross-origin khi an toàn.
- same-origin: chỉ gửi referrer với request same-origin.
- no-referrer-when-downgrade: policy cũ, không nên mặc định chọn cho ứng dụng mới.

Referrer có thể chứa path/query nhạy cảm nếu URL được thiết kế không tốt. Không đặt token hoặc secret trong URL; dùng referrer policy ở document/server và request khi có nhu cầu cụ thể.

## 20. AbortController: hủy request

Fetch không có timeout mặc định. Dùng AbortController để hủy request khi người dùng rời màn hình, đổi truy vấn hoặc request quá lâu.

~~~js
const controller = new AbortController();

try {
  const responsePromise = fetch("/api/search?q=browser", {
    signal: controller.signal
  });

  // Mô phỏng hành động hủy từ nút Cancel của giao diện.
  controller.abort();
  await responsePromise;
} catch (error) {
  if (error.name === "AbortError") {
    console.log("Người dùng đã hủy request");
  } else {
    throw error;
  }
}
~~~

Khi signal bị abort, Promise fetch reject với AbortError trong trường hợp thông thường. Nếu response đã nhận headers nhưng body còn đang đọc, abort cũng có thể làm body read bị hủy.

### 20.1. Timeout bằng AbortSignal.timeout

Browser hỗ trợ AbortSignal.timeout() có thể dùng:

~~~js
const response = await fetch("/api/report", {
  signal: AbortSignal.timeout(5000)
});
~~~

API này có thể chưa có ở một số browser/version. Dùng feature detection hoặc AbortController kết hợp timer do ứng dụng quản lý nếu cần compatibility.

### 20.2. Kết hợp nhiều tín hiệu hủy

AbortSignal.any() được hỗ trợ có thể kết hợp signal do người dùng hủy và signal timeout:

~~~js
const controller = new AbortController();
const timeoutSignal = AbortSignal.timeout(8000);

const signal = AbortSignal.any([
  controller.signal,
  timeoutSignal
]);

const response = await fetch("/api/search", { signal });
~~~

Kiểm tra hỗ trợ trước khi dùng trong browser mục tiêu. Không nuốt mọi lỗi abort như lỗi server; UI nên phân biệt người dùng chủ động hủy với timeout.

### 20.3. Hủy không có nghĩa server chắc chắn chưa xử lý

Browser hủy việc chờ/đọc request hoặc response không bảo đảm server chưa nhận request hoặc chưa thực hiện side effect. Với POST thanh toán/tạo đơn, server có thể đã xử lý trước khi client abort.

Dùng idempotency key và endpoint status để xác định kết quả giao dịch. Không tự gửi lại một operation không idempotent chỉ vì client nhận AbortError.

## 21. Error handling có cấu trúc

Một API client nên phân biệt:
- Network/CORS/CSP/TLS failure: fetch reject và không có Response đọc được.
- Abort: request bị hủy hoặc timeout.
- HTTP error: có Response nhưng status không thành công.
- Parse error: response body không theo định dạng mong đợi.
- Application error: JSON hợp lệ nhưng nghiệp vụ trả kết quả lỗi.

Ví dụ helper:

~~~js
async function fetchJson(url, options = {}) {
  let response;

  try {
    response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...options.headers
      }
    });
  } catch (error) {
    if (error.name === "AbortError" || error.name === "TimeoutError") {
      throw error;
    }

    throw new Error("Không thể kết nối API");
  }

  const contentType = response.headers.get("content-type") || "";

  if (!response.ok) {
    const requestId = response.headers.get("x-request-id");
    throw new Error(
      "API trả HTTP " + response.status +
      (requestId ? " (request " + requestId + ")" : "")
    );
  }

  if (response.status === 204) {
    return null;
  }

  if (!contentType.includes("application/json")) {
    throw new TypeError("API không trả JSON như mong đợi");
  }

  return response.json();
}
~~~

Helper này là ví dụ tối giản. Ứng dụng thật cần quản lý header merge, body, credentials, timeout và error schema theo API contract. Không đưa response body thô vào thông báo người dùng hoặc telemetry nếu có thể chứa dữ liệu nhạy cảm.

### 21.1. Đọc lỗi JSON có giới hạn

Một API có thể trả JSON error body. Nếu cần đọc, giới hạn field được phép và không serialize toàn bộ response:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Dữ liệu không hợp lệ",
  "requestId": "req-demo-001"
}
~~~

UI chỉ hiển thị thông điệp phù hợp. Stack trace, SQL error, internal host và credential không nên được gửi cho client.

## 22. Retry, backoff và idempotency

Fetch không tự retry request khi network failure. Ứng dụng có thể retry có giới hạn cho lỗi tạm thời, nhưng phải xét method và trạng thái nghiệp vụ.

Nguyên tắc:
- Retry GET/HEAD thường an toàn hơn nếu endpoint tuân thủ ngữ nghĩa HTTP.
- PUT/DELETE có ngữ nghĩa idempotent nhưng implementation vẫn cần được kiểm tra.
- Không tự retry POST tạo giao dịch nếu chưa có idempotency key hoặc cơ chế chống tạo trùng.
- Không retry lỗi 400/401/403 một cách mù quáng.
- Tôn trọng Retry-After khi server trả 429 hoặc 503.
- Dùng exponential backoff và jitter để tránh nhiều client retry đồng loạt.
- Không retry AbortError do người dùng chủ động hủy.

Ví dụ backoff minh họa:

~~~js
function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function retryDelay(response, fallbackMs) {
  const value = response.headers.get("Retry-After");
  if (!value) return fallbackMs;

  const seconds = Number(value);
  if (Number.isFinite(seconds)) {
    return Math.min(30000, Math.max(0, seconds * 1000));
  }

  const date = Date.parse(value);
  return Number.isNaN(date)
    ? fallbackMs
    : Math.min(30000, Math.max(0, date - Date.now()));
}

async function fetchGetWithRetry(makeRequest, maxAttempts = 3) {
  const retryableStatuses = new Set([429, 500, 502, 503, 504]);

  if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
    throw new TypeError("maxAttempts phải là số nguyên dương");
  }

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    // makeRequest tạo một Request mới cho mỗi lần thử.
    const request = makeRequest();
    if (!(request instanceof Request) || !["GET", "HEAD"].includes(request.method)) {
      throw new TypeError("Ví dụ này chỉ retry Request GET hoặc HEAD");
    }

    const response = await fetch(request);

    if (!retryableStatuses.has(response.status) || attempt === maxAttempts - 1) {
      return response;
    }

    const fallback = 500 * Math.pow(2, attempt);
    const waitMs = retryDelay(response, fallback);
    await response.body?.cancel();
    await delay(Math.random() * waitMs);
  }
}

const response = await fetchGetWithRetry(
  () => new Request("/api/catalog", { method: "GET" })
);
~~~

Ví dụ chỉ retry một GET có thể tạo lại từ request factory; nó không tự retry mọi lỗi network hoặc policy failure. Với request khác, chỉ retry khi endpoint thực sự idempotent và body có thể tạo lại. Production cần kết hợp signal hủy, giới hạn thời gian tổng, jitter và xử lý Retry-After. Không retry POST không idempotent nếu server chưa hỗ trợ idempotency key.

### 22.1. Idempotency key

Với operation tạo giao dịch có thể cần retry, client gửi một idempotency key duy nhất cho operation; server lưu kết quả theo key và bảo đảm cùng key không tạo side effect lặp.

~~~js
const response = await fetch("/api/payments", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Idempotency-Key": "payment-attempt-demo-001"
  },
  body: JSON.stringify({ orderId: "order-42" })
});
~~~

Key cần được tạo và quản lý theo giao dịch, không dùng một hằng số chung cho mọi request. Server phải thực thi semantics idempotency; chỉ gửi header từ client không tự tạo bảo đảm.

## 23. Fetch và CSRF

Nếu ứng dụng xác thực bằng cookie, browser có thể tự gửi cookie phù hợp cùng Fetch request. Một request thay đổi trạng thái có thể bị kích hoạt từ trang khác tùy method, content type, credentials và cookie policy.

CORS không phải biện pháp chống CSRF. Ngay cả khi script tấn công không đọc được response, request vẫn có thể tới server trong các trường hợp phù hợp.

Biện pháp cần phối hợp:
- SameSite cookie phù hợp.
- CSRF token cho request thay đổi trạng thái khi kiến trúc yêu cầu.
- Kiểm tra Origin hoặc Fetch Metadata ở server.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Xác thực và authorization ở backend.
- Kiểm tra content type, schema và quyền tài nguyên.

Fetch Metadata headers như Sec-Fetch-Site có thể giúp server nhận diện request cross-site, nhưng không nên dùng một header đơn lẻ thay toàn bộ CSRF defense.

## 24. Fetch và URL do người dùng kiểm soát

Không để input không tin cậy quyết định tùy ý API origin:

~~~js
const apiUrl = new URL(userProvidedUrl);
fetch(apiUrl, {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Nếu người dùng chọn một host ngoài, ứng dụng có thể gửi token hoặc dữ liệu nhạy cảm tới origin đó. Hãy cấu hình API origin từ môi trường tin cậy và allowlist scheme/host/port.

Ví dụ kiểm tra:

~~~js
function buildApiUrl(path) {
  const base = new URL("https://api.example.test");
  const url = new URL(path, base);

  if (url.origin !== base.origin || url.protocol !== "https:") {
    throw new TypeError("API destination không hợp lệ");
  }

  return url;
}
~~~

Không ghép URL tùy tiện từ dữ liệu query, localStorage hoặc postMessage. Nếu nghiệp vụ cần gọi nhiều host, dùng allowlist tường minh và xác định credential nào được gửi tới từng host.

## 25. Fetch, HTTPS và mixed content

Trang HTTPS gọi API HTTP là mixed content. Browser hiện đại chặn các request Fetch/XHR insecure; không dùng mode: no-cors hoặc CORS headers để né.

~~~js
// Không an toàn từ trang HTTPS:
fetch("http://api.example.test/data");

// Dùng HTTPS:
fetch("https://api.example.test/data");

// Hoặc cùng origin qua reverse proxy:
fetch("/api/data");
~~~

Kiểm tra redirect chain: một HTTPS endpoint redirect tới HTTP vẫn có thể bị chặn. CSP connect-src giới hạn host được phép kết nối, còn TLS xác minh endpoint và mã hóa request/response.

Không tự fallback HTTPS xuống HTTP khi certificate hoặc endpoint gặp lỗi. Sửa TLS, DNS, proxy hoặc cấu hình API.

## 26. Service Worker có thể intercept Fetch

Khi trang nằm trong scope của một Service Worker active, request Fetch có thể phát fetch event và được worker xử lý. Worker có thể:
- Trả response từ Cache Storage.
- Gửi request tới network.
- Kết hợp cache và network.
- Trả offline fallback.
- Áp dụng chiến lược cache theo loại tài nguyên.

Vì vậy, response nhận được từ fetch() không nhất thiết vừa được lấy trực tiếp từ server. Khi debug, kiểm tra Application → Service Workers, Cache Storage và Network để xác định nguồn response.

Service Worker không được bỏ qua các quy tắc bảo mật của browser. Nó vẫn chịu origin, CORS, CSP/security policy và giới hạn của Fetch.

## 27. Keepalive và request khi trang kết thúc

Fetch có tùy chọn keepalive cho một số request nhỏ có thể tiếp tục khi document bắt đầu unload:

~~~js
fetch("/api/telemetry", {
  method: "POST",
  body: JSON.stringify({ event: "page_exit" }),
  headers: {
    "Content-Type": "application/json"
  },
  keepalive: true
});
~~~

Keepalive có giới hạn kích thước và không bảo đảm request sẽ được giao trong mọi tình huống. Với telemetry nhỏ, navigator.sendBeacon() có thể phù hợp hơn. Không dùng keepalive để upload file lớn hoặc bảo đảm hoàn tất giao dịch.

Không dựa vào beforeunload để lưu dữ liệu quan trọng duy nhất. Lưu draft trong quá trình thao tác và xác nhận kết quả quan trọng qua server.

## 28. Debug Fetch API bằng DevTools

Khi request không hoạt động:

1. Mở DevTools → Network.
2. Lọc Fetch/XHR.
3. Kiểm tra Request URL, method và status.
4. Xem Request Headers, Payload và Response.
5. Kiểm tra Initiator để biết code tạo request.
6. Nếu cross-origin, tìm OPTIONS preflight và CORS response headers.
7. Nếu không có request hoặc browser đánh dấu blocked, xem Console để tìm CSP, mixed content hoặc CORS.
8. Kiểm tra redirect chain và URL cuối.
9. Xem Timing và cache source khi response có vẻ cũ.
10. Kiểm tra service worker interception và Cache Storage.
11. Kiểm tra response body có đúng content type/schema không.
12. Xác minh cookie/credentials trong tab Cookies mà không sao chép giá trị credential vào ticket.

### 28.1. Phân biệt các lỗi thường gặp

| Hiện tượng | Nơi kiểm tra |
| --- | --- |
| fetch reject, không có Response | Network/TLS, CORS, CSP, mixed content, AbortSignal. |
| Response 401 | Session/token và authentication server. |
| Response 403 | Authorization, CSRF hoặc policy server. |
| Response 404 | URL, route và API deployment. |
| Response 429 | Rate limit và Retry-After. |
| Response 500 | Server logs bằng request ID, không log secret. |
| json() reject | Body rỗng, HTML error hoặc JSON sai định dạng. |
| Response cũ | HTTP cache, Cache Storage và Service Worker. |

curl có thể giúp kiểm tra server và redirect nhưng không áp dụng đầy đủ browser CORS, CSP, cookie và mixed content policy. Dùng browser thật để xác minh hành vi client.

## 29. Ví dụ API client có kiểm soát

Ví dụ sau giới hạn API về một HTTPS origin đã cấu hình, đặt Accept mặc định, cho phép caller hủy request và xử lý 204/HTTP error:

~~~js
function createApiClient(baseUrl) {
  const base = new URL(baseUrl);

  if (base.protocol !== "https:") {
    throw new TypeError("API phải dùng HTTPS");
  }

  return async function apiFetch(path, options = {}) {
    const url = new URL(path, base);

    if (url.origin !== base.origin) {
      throw new TypeError("API URL vượt khỏi origin đã cấu hình");
    }

    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) {
      headers.set("Accept", "application/json");
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: options.credentials ?? "same-origin",
      redirect: options.redirect ?? "error"
    });

    if (!response.ok) {
      throw new Error("API trả HTTP " + response.status);
    }

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.toLowerCase().includes("application/json")) {
      throw new TypeError("API không trả JSON");
    }

    return response.json();
  };
}

const apiFetch = createApiClient("https://api.example.test");
~~~

Ví dụ này là điểm khởi đầu, không phải thư viện hoàn chỉnh. Nếu API ở same-origin app thay vì host riêng, dùng base URL tương ứng. Nếu API cross-origin và cần cookie, thiết kế CORS/credentials tường minh; không ép same-origin như ví dụ. Nếu cần retry, timeout, schema validation hoặc idempotency, bổ sung theo contract của endpoint.

## 30. Checklist review Fetch API

- [ ] Kiểm tra response.ok/status; không giả định 4xx/5xx làm fetch reject.
- [ ] Phân biệt network/CORS/CSP/mixed-content failure với HTTP error.
- [ ] Dùng URL/URLSearchParams thay vì nối query string thủ công.
- [ ] Allowlist API origin và chỉ gửi credential tới host tin cậy.
- [ ] Không gửi body với GET/HEAD.
- [ ] Đặt Content-Type phù hợp với body JSON/form.
- [ ] Không tự đặt multipart Content-Type cho FormData.
- [ ] Kiểm tra file upload ở server; không tin MIME/filename từ client.
- [ ] Kiểm tra content type trước khi parse response JSON.
- [ ] Xử lý 204 No Content mà không gọi json().
- [ ] Không tiêu thụ response/request body nhiều lần.
- [ ] Clone response chỉ khi cần và cân nhắc bộ nhớ với body lớn.
- [ ] Dùng stream cho payload lớn và cancel khi không cần.
- [ ] Quản lý Blob URL và revoke khi dùng xong.
- [ ] Chọn credentials mode phù hợp; hiểu cookie policy vẫn áp dụng.
- [ ] Không cố đọc Set-Cookie từ JavaScript.
- [ ] Cấu hình CORS chính xác, nhất là credentials và Vary: Origin.
- [ ] Không dùng no-cors để né CORS hoặc mixed content.
- [ ] Không coi preflight/CORS là CSRF defense.
- [ ] Dùng CSP connect-src allowlist endpoint cần thiết.
- [ ] Không cho user input tùy ý chọn URL nhận token/dữ liệu.
- [ ] Kiểm tra redirect và không cho downgrade HTTPS xuống HTTP.
- [ ] Chọn cache mode phù hợp và đặt Cache-Control phía server.
- [ ] Không cache response nhạy cảm ngoài nhu cầu có kiểm soát.
- [ ] Dùng AbortController cho cancel/timeout và phân biệt AbortError.
- [ ] Retry có giới hạn; không retry POST không idempotent nếu thiếu cơ chế server.
- [ ] Tôn trọng Retry-After và dùng backoff/jitter khi phù hợp.
- [ ] Bảo vệ endpoint cookie-authenticated khỏi CSRF.
- [ ] Không log token, cookie, PII hoặc response body nhạy cảm.
- [ ] Kiểm tra service worker và DevTools khi response đến từ cache.
- [ ] Xác minh API authorization ở server cho mọi request.

## 31. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “HTTP 404 làm fetch reject.” | **Sai** | Fetch thường resolve với Response; kiểm tra ok/status. |
| “response.json() không bao giờ lỗi nếu server trả 200.” | **Sai** | Body có thể rỗng, sai JSON hoặc là HTML. |
| “Fetch tự đặt Content-Type application/json.” | **Sai** | Với JSON string, ứng dụng cần đặt Content-Type phù hợp. |
| “FormData phải tự đặt multipart/form-data.” | **Sai** | Browser cần tự thêm boundary vào Content-Type. |
| “Response body có thể đọc nhiều lần.” | **Sai** | Body stream chỉ tiêu thụ một lần; clone trước nếu cần hai nhánh. |
| “no-cors cho phép đọc API cross-origin.” | **Sai** | Response thường opaque và không đọc được. |
| “CORS ngăn mọi CSRF request.” | **Sai** | CORS chủ yếu kiểm soát đọc response; request đơn giản vẫn có thể được gửi. |
| “credentials: include bảo đảm cookie được gửi.” | **Sai** | SameSite, Secure, domain, partitioning và third-party policy vẫn áp dụng. |
| “JavaScript có thể đọc Set-Cookie.” | **Sai** | Set-Cookie là forbidden response header. |
| “Fetch có timeout mặc định.” | **Sai** | Dùng AbortController hoặc AbortSignal.timeout khi hỗ trợ. |
| “Abort nghĩa là server chưa thực hiện operation.” | **Sai** | Server có thể đã nhận và xử lý request trước khi client hủy. |
| “Có thể retry mọi POST khi network lỗi.” | **Sai** | Operation có thể đã được xử lý; cần idempotency key hoặc trạng thái giao dịch. |
| “redirect: manual cho phép đọc Location cross-origin.” | **Sai** | Browser có thể trả opaqueredirect và ẩn thông tin redirect. |
| “no-cache có nghĩa không lưu response.” | **Sai** | no-cache yêu cầu revalidation; no-store mới yêu cầu không lưu HTTP cache. |
| “HTTPS bảo đảm response không xem được trong DevTools.” | **Sai** | TLS bảo vệ đường truyền, browser vẫn phải giải mã response. |
| “CSP connect-src thay CORS.” | **Sai** | CSP giới hạn đích kết nối; CORS kiểm soát chia sẻ response cross-origin. |
| “Service Worker cache là HTTP cache.” | **Sai** | Cache Storage và HTTP cache là các cơ chế khác nhau. |
| “Client-side validation là authorization.” | **Sai** | Server phải xác minh session, quyền và tài nguyên. |

## 32. Tổng kết

Fetch API cung cấp một mô hình Promise thống nhất để tạo request và xử lý response. Điểm quan trọng nhất khi dùng API là phân biệt lỗi network với HTTP status, kiểm tra response trước khi parse, quản lý body stream đúng vòng đời và cấu hình method/headers/credentials theo nhu cầu thực tế.

Fetch hoạt động bên trong các ranh giới bảo mật của browser. CORS không thay authorization hoặc CSRF defense; no-cors không phải cách đọc response cross-origin; HTTPS và CSP không thay nhau; Abort không chứng minh server chưa thực hiện side effect. Backend phải xác thực, phân quyền, validate dữ liệu và bảo vệ các thao tác thay đổi trạng thái.

Ba nguyên tắc cần nhớ:

1. **Xử lý response có chủ đích:** kiểm tra status, content type, body và lỗi parse; nhớ 4xx/5xx thường vẫn resolve Promise.
2. **Tôn trọng browser security model:** cấu hình credentials, CORS, CSP, redirect, cache và HTTPS đúng; không dùng no-cors hoặc fallback HTTP để né policy.
3. **Bảo vệ operation ở server:** kiểm tra CSRF, authorization và idempotency; hủy request không đồng nghĩa hủy side effect đã xảy ra.

Khi review một Fetch call, hãy hỏi: **request đang tới origin nào, method/body/header có đúng contract, browser có gửi cookie hoặc token không, CORS/CSP/mixed content có cho phép, response status và content type là gì, body đã bị đọc chưa, redirect/cache có làm thay đổi kết quả, và server có xác minh quyền cũng như chống request lặp không?** Trả lời những câu hỏi này giúp xây dựng API client rõ ràng, dễ debug và an toàn trong browser.
