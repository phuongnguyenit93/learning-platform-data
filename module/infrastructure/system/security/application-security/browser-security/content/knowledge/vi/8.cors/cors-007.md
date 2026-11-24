# CORS Allowed headers: kiểm soát request headers cross-origin

## 1. `Access-Control-Allow-Headers` là gì?

Khi JavaScript của một trang web gửi request tới một origin khác, trình duyệt áp dụng **Cross-Origin Resource Sharing (CORS)** để quyết định JavaScript có được đọc response hay không. Với một số request, trước khi gửi request thực tế, trình duyệt gửi một request kiểm tra gọi là **preflight** bằng phương thức `OPTIONS`. Máy chủ dùng header **`Access-Control-Allow-Headers`** để khai báo những **request header** nào phía client được phép sử dụng trong request cross-origin đó.

Ví dụ frontend ở `https://app.example.test` cần gọi API ở `https://api.example.test` và gửi header `X-Request-ID`:

~~~js
const response = await fetch("https://api.example.test/v1/orders", {
  method: "GET",
  headers: {
    "X-Request-ID": "req-123"
  }
});
~~~

`X-Request-ID` không thuộc nhóm CORS-safelisted request headers. Trình duyệt sẽ cần kiểm tra quyền dùng header này qua preflight. API có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: X-Request-ID
Vary: Origin
~~~

Nếu preflight hợp lệ và các điều kiện CORS khác được đáp ứng, trình duyệt mới tiếp tục gửi request GET thực tế với `X-Request-ID`. Nếu header không được cho phép, JavaScript không được cấp quyền thực hiện request theo quy trình CORS đó và sẽ nhận lỗi CORS.

Bài học thuộc chương **CORS** của module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`. Nội dung tập trung vào cách phân biệt request headers, response headers và các header CORS; điều kiện preflight; cách cấu hình allowlist; các giới hạn với credentials, wildcard và header do browser kiểm soát; cuối cùng là kiểm chứng hành vi thực tế.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `Access-Control-Allow-Headers` trong CORS preflight.
2. Phân biệt header được gửi trong request, header được phép gửi và response header được JavaScript đọc.
3. Nhận diện CORS-safelisted request headers và trường hợp một header làm phát sinh preflight.
4. Hiểu vì sao `Content-Type: application/json`, `Authorization` và custom headers thường cần preflight.
5. Cấu hình header allowlist theo origin, method, credentials và endpoint.
6. Tránh dùng wildcard hoặc phản chiếu header do client yêu cầu một cách thiếu kiểm soát.
7. Phân biệt `Access-Control-Allow-Headers` với `Access-Control-Expose-Headers`.
8. Kiểm tra preflight và request thực tế trong DevTools, Network và log server.

## 2. Phân biệt ba nhóm header thường bị nhầm

Trong CORS, cụm từ “allowed headers” dễ gây nhầm vì có nhiều header cùng chứa từ “header” nhưng chức năng khác nhau.

| Nhóm | Header hoặc ví dụ | Ai gửi? | Ý nghĩa |
| --- | --- | --- | --- |
| Request headers của ứng dụng | `Content-Type`, `Authorization`, `X-Request-ID` | Client/browser | Metadata hoặc dữ liệu điều khiển request. |
| CORS preflight request headers | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` | Browser | Cho server biết origin, method và tên header dự kiến dùng. |
| CORS response permission headers | `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` | Server | Khai báo phạm vi tương tác cross-origin được phép. |
| Response headers của API | `X-Request-ID`, `Content-Disposition`, `ETag` | Server | Metadata trả về cho client. |
| CORS response exposure header | `Access-Control-Expose-Headers` | Server | Khai báo response header nào JavaScript được phép đọc. |

Điểm quan trọng:

- `Access-Control-Allow-Headers` nói về **request headers** mà browser được phép gửi trong request CORS.
- `Access-Control-Expose-Headers` nói về **response headers** mà JavaScript được phép đọc.
- `Access-Control-Request-Headers` là header do browser gửi trong preflight để liệt kê tên các request headers mà request thật muốn dùng.
- `Access-Control-Allow-Origin` kiểm soát origin được phép đọc response; nó không thay thế allowlist header.

### 2.1. Sơ đồ luồng preflight

~~~mermaid
sequenceDiagram
    participant JS as JavaScript app.example.test
    participant Browser as Trình duyệt
    participant API as api.example.test

    JS->>Browser: fetch() có X-Request-ID
    Browser->>API: OPTIONS /v1/orders
    Note over Browser,API: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
    API-->>Browser: ACAO, ACAM, ACAH
    Note over Browser: Kiểm tra origin, method và request headers
    Browser->>API: GET /v1/orders + X-Request-ID
    API-->>Browser: Response + CORS headers
    Browser-->>JS: Cho JavaScript đọc response nếu CORS hợp lệ
~~~

Preflight là bước kiểm tra **chính sách CORS ở trình duyệt**, không phải xác thực người dùng hoặc cấp quyền nghiệp vụ. Request thực tế vẫn phải được server xác thực và phân quyền.

## 3. Khi nào browser gửi preflight?

Một request cross-origin thường không cần preflight nếu đáp ứng đầy đủ điều kiện của một **CORS-safelisted request**. Khi request dùng method, header hoặc giá trị không nằm trong nhóm an toàn đó, browser thường gửi preflight trước.

Các trường hợp phổ biến làm phát sinh preflight:

- Dùng method như `PUT`, `PATCH` hoặc `DELETE` (ngoài nhóm method safelisted).
- Gửi custom request header như `X-Request-ID`, `X-API-Key` hoặc `X-Client-Version`.
- Gửi `Content-Type: application/json` vì MIME type này không thuộc nhóm safelisted.
- Gửi `Authorization` hoặc một request header khác không thuộc nhóm safelisted.
- Dùng giá trị header vượt giới hạn hoặc không thỏa các điều kiện safelist.

Ví dụ:

~~~js
await fetch("https://api.example.test/v1/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Client-Version": "2.4"
  },
  body: JSON.stringify({ productId: "P-42" })
});
~~~

Trình duyệt cần kiểm tra server có cho phép method POST và các header `Content-Type`, `X-Client-Version` hay không.

### 3.1. Request CORS-safelisted headers

Các tên header cốt lõi thường được xem là safelisted gồm:

| Header | Giới hạn/điều kiện chính |
| --- | --- |
| `Accept` | Giá trị phải thỏa quy tắc safelist, bao gồm giới hạn byte và các byte không an toàn. |
| `Accept-Language` | Giá trị phải thỏa quy tắc safelist. |
| `Content-Language` | Giá trị phải thỏa quy tắc safelist. |
| `Content-Type` | MIME type essence phải là một trong các loại được cho phép: `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`. |
| `Range` | Chỉ một single byte range theo điều kiện safelist. |

Một số header client-hint có thể có quy tắc safelist riêng tùy đặc tả/trình duyệt. Khi thiết kế API, nên kiểm tra hành vi theo browser mục tiêu và không dựa vào một header hiếm gặp để bỏ qua kiểm tra CORS.

Không phải cứ tên header nằm trong bảng là mọi giá trị đều safelisted. Quy tắc còn xét **giá trị**; một số header value chứa byte không an toàn, quá dài hoặc sai cấu trúc sẽ khiến request không còn đơn giản.

### 3.2. Vì sao JSON thường kích hoạt preflight?

`Content-Type` chỉ được safelist cho một số MIME type. `application/json` không nằm trong ba MIME type safelisted, nên request POST JSON cross-origin thường phải preflight.

Ví dụ:

~~~http
Content-Type: application/json
~~~

Khác với:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

Điều này **không** có nghĩa form encoding tự động an toàn trước CSRF hoặc injection. Safelist chỉ liên quan đến quy tắc gửi request của CORS; backend vẫn phải validate, xác thực, phân quyền và chống CSRF khi phù hợp.

### 3.3. Tên header được so sánh không phân biệt hoa/thường

Tên HTTP header không phân biệt chữ hoa/thường:

~~~http
X-Request-ID: req-123
x-request-id: req-123
X-REQUEST-ID: req-123
~~~

Các dạng này cùng chỉ một tên header. Vì vậy server nên normalize tên header (thường về chữ thường) trước khi so với allowlist. Không dùng so sánh chuỗi phân biệt hoa/thường để tạo khác biệt quyền ngoài ý muốn.

## 4. Preflight request trông như thế nào?

Với request POST JSON có `X-Client-Version`, browser có thể gửi một request preflight dạng:

~~~http
OPTIONS /v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type, x-client-version
~~~

Giải thích:

- `OPTIONS`: method của preflight.
- `Origin`: origin của trang khởi tạo request.
- `Access-Control-Request-Method`: method mà request thực tế muốn dùng.
- `Access-Control-Request-Headers`: danh sách tên các request headers không safelisted mà request thực tế muốn gửi.

Browser liệt kê **tên header**, không gửi giá trị `X-Client-Version` hay nội dung JSON trong preflight. Server cần đánh giá các tên được yêu cầu theo chính sách.

### 4.1. Preflight response cho phép header

Ví dụ API cho phép origin frontend, method POST và hai request headers:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type, X-Client-Version
Vary: Origin
~~~

Nếu request thực tế dùng credentials, response CORS còn cần cấu hình credentials phù hợp (xem mục 7). Nếu server trả thiếu một header bắt buộc, browser có thể từ chối request theo CORS.

### 4.2. Sau preflight mới là request thực tế

Khi preflight thành công, browser gửi request POST thật:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Content-Type: application/json
X-Client-Version: 2.4

{"productId":"P-42"}
~~~

Server phải xử lý request thật như một request API thông thường: xác thực user, kiểm tra quyền, validate body, chống CSRF nếu cơ chế phiên yêu cầu và thực hiện nghiệp vụ. Việc preflight thành công **không** chứng minh user được quyền tạo đơn.

### 4.3. Preflight thường không mang credentials

Theo CORS protocol, preflight request được gửi mà không mang credentials của request thực tế. Vì vậy server không nên yêu cầu cookie phiên hoặc bearer token của người dùng để trả lời `OPTIONS` preflight. Thay vào đó, server đánh giá origin, method và header names theo chính sách CORS.

Điều này không làm `OPTIONS` trở thành một lỗ hổng cấp quyền: request thực tế vẫn phải được xác thực và phân quyền. Với request thực tế có credentials, CORS response phải đáp ứng quy tắc credentials tương ứng.

## 5. `Access-Control-Allow-Headers`: cú pháp và ý nghĩa

Ví dụ:

~~~http
Access-Control-Allow-Headers: Content-Type, Authorization, X-Request-ID
~~~

Đây là danh sách tên request header server cho phép trong request cross-origin được preflight. Giá trị là các header field name, phân tách bằng dấu phẩy.

Một số lưu ý:

- Tên header không phân biệt hoa/thường.
- Header được liệt kê phải là header name hợp lệ theo quy tắc HTTP.
- Đây là **quyền theo chính sách CORS của browser**, không phải lệnh cho backend bỏ qua validation.
- Cho phép một header không bắt buộc mọi request phải gửi header đó.
- Không liệt kê response header ở đây với kỳ vọng JavaScript sẽ đọc được response header đó.
- Không thể dùng ACAH để cho JavaScript đặt những header mà browser cấm script tự thiết lập.

Ví dụ server cho phép ba request header:

~~~http
Access-Control-Allow-Headers: Content-Type, Authorization, X-Request-ID
~~~

Frontend có thể dùng chúng nếu các điều kiện CORS khác cũng được đáp ứng. Server vẫn cần kiểm tra nội dung, quyền và mục đích của từng header.

### 5.1. Header custom không phải bằng chứng đáng tin cậy

Một số ứng dụng thêm header:

~~~http
X-Internal-Request: true
X-User-Role: admin
X-Trusted-Client: yes
~~~

Tên header “nội bộ”, “trusted” hoặc “admin” không khiến dữ liệu đó đáng tin. Client có thể tự gửi header qua nhiều công cụ HTTP. Nếu browser được CORS cho phép gửi header đó, nó vẫn chỉ là input của client.

Không bao giờ dùng custom request header do client tự đặt làm bằng chứng duy nhất cho:

- Vai trò quản trị.
- Danh tính user.
- Quyền sở hữu tài nguyên.
- Request đã qua bước xác thực.
- Request chắc chắn xuất phát từ frontend chính thức.

Các header như `X-User-Role` chỉ nên là dữ liệu không tin cậy nếu do client cung cấp. Quyền phải được suy ra từ session/token đã xác minh và chính sách backend.

## 6. Wildcard `*` trong Access-Control-Allow-Headers

Server có thể trả:

~~~http
Access-Control-Allow-Headers: *
~~~

Tuy nhiên, dấu `*` không phải lúc nào cũng là “cho phép mọi header”.

### 6.1. Khi request không dùng credentials

Nếu request không dùng credentials mode `include`, wildcard có thể được hiểu là cho phép mọi request header **thuộc phạm vi wildcard của CORS**.

Nhưng có ngoại lệ quan trọng: **`Authorization` không được bao phủ bởi wildcard**. Nếu request muốn gửi header Authorization, server phải nêu rõ:

~~~http
Access-Control-Allow-Headers: Authorization, X-Request-ID
~~~

Không dựa vào `Access-Control-Allow-Headers: *` để cấp quyền cho Authorization.

### 6.2. Khi request dùng credentials

Khi request có credentials mode `include`, wildcard trong `Access-Control-Allow-Headers` được xem như tên header literal `*`, chứ không phải wildcard cho mọi tên header.

Ví dụ không đủ để cho phép `X-Request-ID` trong request credentialed:

~~~http
Access-Control-Allow-Headers: *
Access-Control-Allow-Credentials: true
~~~

Server cần liệt kê tường minh:

~~~http
Access-Control-Allow-Headers: Content-Type, X-Request-ID
Access-Control-Allow-Credentials: true
~~~

Trong ứng dụng có credentials, allowlist cụ thể thường dễ kiểm tra và an toàn hơn.

### 6.3. `Access-Control-Allow-Origin: *` cũng có giới hạn riêng

Đừng nhầm wildcard ở ACAH với wildcard ở ACAO. Với request có credentials, browser không chấp nhận:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Server phải trả origin cụ thể được cho phép, ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Đây là hai quy tắc khác nhau: ACAH kiểm soát request header names; ACAO kiểm soát origin được đọc response.

## 7. Credentials và request headers

Credentials có thể gồm cookie, thông tin xác thực HTTP được browser quản lý và client certificate trong các bối cảnh tương ứng. Với Fetch API, tùy chọn `credentials` điều khiển cách request xử lý credentials:

~~~js
fetch("https://api.example.test/v1/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Với CORS credentialed request, server thường cần:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Nếu request có custom request header, preflight phải cho phép header đó một cách tường minh:

~~~http
Access-Control-Allow-Headers: X-Request-ID, Content-Type
~~~

Các lưu ý:

1. `credentials: "include" không bỏ qua `SameSite`, `Secure`, cookie domain/path hoặc chính sách cookie của browser.
2. ACAH không làm cookie trở thành request header mà JavaScript tự đặt; browser quản lý cookie.
3. CORS credentials không thay thế CSRF protection.
4. Backend vẫn phải kiểm tra session, token, authorization và quyền trên từng tài nguyên.
5. Không sử dụng wildcard khi cần credentialed CORS; nêu rõ origin và header names.

### 7.1. Ví dụ Fetch dùng Authorization và custom header

~~~js
const response = await fetch("https://api.example.test/v1/profile", {
  method: "GET",
  headers: {
    "Authorization": "Bearer ACCESS_TOKEN",
    "X-Request-ID": "req-789"
  }
});

if (!response.ok) {
  throw new Error("Không lấy được hồ sơ");
}

const profile = await response.json();
~~~

Browser sẽ cần preflight do `Authorization` và `X-Request-ID` không thuộc nhóm request headers safelisted. API phải cho phép chúng bằng ACAH, cùng origin/method theo chính sách.

**Lưu ý:** Bearer token trong JavaScript có rủi ro nếu trang bị XSS. CORS cho phép gửi header không đồng nghĩa token được lưu hoặc bảo vệ an toàn. Hãy quản lý token theo threat model và chống XSS.

## 8. Những header JavaScript không thể tùy ý đặt

`Access-Control-Allow-Headers` không thể cấp quyền cho JavaScript thiết lập mọi header. Fetch định nghĩa **forbidden request-header names** và các quy tắc bảo vệ tương ứng để browser giữ quyền kiểm soát một số header.

Ví dụ những header mà script không thể tùy ý thiết lập:

- `Host` và `Content-Length`.
- `Cookie` và `Cookie2`.
- `Origin` (browser quản lý trong những ngữ cảnh áp dụng).
- Các header có prefix `Sec-`.
- Một số header kết nối hoặc điều khiển giao thức như `Connection` và `Transfer-Encoding`.

Danh sách chính xác có quy tắc và ngoại lệ theo Fetch; đây là ví dụ để nhận diện nguyên tắc, không phải danh sách đầy đủ.

Ví dụ:

~~~js
const headers = new Headers();
headers.set("X-Request-ID", "req-123");
headers.set("Cookie", "session=anything");
headers.set("Host", "internal.example.test");

console.log([...headers.entries()]);
~~~

Việc thêm header bị cấm có thể bị browser bỏ qua hoặc xử lý theo quy tắc Fetch. ACAH không thể thay đổi điều đó.

Nếu ứng dụng cần gửi cookie, dùng cơ chế credentials và cookie policy phù hợp, không cố tự tạo header `Cookie`. Nếu cần `Origin`, browser tự tạo trong những request thích hợp; server không nên dựa vào giá trị client ngoài browser như bằng chứng xác thực.

## 9. `Access-Control-Allow-Headers` khác `Access-Control-Expose-Headers`

Đây là cặp header thường bị nhầm.

### 9.1. Cho phép gửi request header

`Access-Control-Allow-Headers` cho phép browser sử dụng request header không safelisted trong request cross-origin sau khi preflight thành công.

~~~http
Access-Control-Allow-Headers: X-Request-ID, Content-Type
~~~

### 9.2. Cho phép JavaScript đọc response header

Giả sử API trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
X-Request-ID: req-123
Content-Disposition: attachment; filename="report.csv"
~~~

Một số response header safelisted có thể được JavaScript đọc theo quy tắc CORS. Các header khác cần được expose:

~~~http
Access-Control-Expose-Headers: X-Request-ID, Content-Disposition
~~~

Sau đó frontend có thể đọc:

~~~js
const response = await fetch("https://api.example.test/report");
console.log(response.headers.get("X-Request-ID"));
console.log(response.headers.get("Content-Disposition"));
~~~

### 9.3. Không dùng ACAH để expose response header

Ví dụ sai mục đích:

~~~http
Access-Control-Allow-Headers: X-Request-ID
~~~

Header này **không** khiến JavaScript đọc được response header `X-Request-ID`. Muốn expose response header đó, cần:

~~~http
Access-Control-Expose-Headers: X-Request-ID
~~~

Một số response header nhạy cảm như `Set-Cookie` là **forbidden response-header name** và không thể được expose cho JavaScript chỉ bằng cách liệt kê trong `Access-Control-Expose-Headers`. Cookie được browser quản lý theo cơ chế riêng.

## 10. Server nên xây allowlist như thế nào?

Một cấu hình tốt bắt đầu từ nhu cầu thực của từng endpoint, không phải bật mọi header để tránh lỗi.

Ví dụ endpoint tạo đơn có hợp đồng:

| Request header | Có cần? | Lý do | Chính sách |
| --- | --- | --- | --- |
| `Content-Type` | Có | JSON body | Cho phép. |
| `Authorization` | Có trong mô hình bearer token | Token xác thực | Cho phép tường minh; xác minh token ở backend. |
| `X-Request-ID` | Có thể | Correlation/trace ID | Cho phép nếu cần; giới hạn định dạng và độ dài. |
| `X-User-Role` | Không | Không được tin role từ client | Không cho phép/không dùng làm quyền. |
| `X-Internal-Request` | Không | Không phải bằng chứng nội bộ | Không dựa vào header này để cấp quyền. |

Ví dụ cấu hình cho route đó:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type, Authorization, X-Request-ID
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Nếu route không dùng cookie hoặc credentials, bỏ ACA-Credentials và thiết kế ACAO/ACAH theo chính sách không credentialed phù hợp. Không cấp một cấu hình chung rộng cho mọi route nếu endpoint có độ nhạy cảm khác nhau.

### 10.1. Quy trình xử lý preflight ở server

Một quy trình khái niệm:

1. Nhận `OPTIONS` tới đúng resource.
2. Đọc `Origin`, `Access-Control-Request-Method` và danh sách `Access-Control-Request-Headers`.
3. So origin với allowlist chính xác (scheme, host, port).
4. So method với danh sách method endpoint hỗ trợ.
5. Parse header names, normalize về chữ thường và kiểm tra từng tên trong allowlist của endpoint.
6. Nếu hợp lệ, trả các CORS response headers phù hợp.
7. Nếu không hợp lệ, không cấp quyền CORS; ghi nhận lỗi theo chính sách, tránh phản chiếu tùy ý dữ liệu đầu vào.
8. Khi request thật tới, xác thực và phân quyền độc lập; validate header values và body.

**Không phản chiếu nguyên xi** `Access-Control-Request-Headers` vào `Access-Control-Allow-Headers` mà không kiểm tra. Nếu làm vậy, server đang để client tự đề xuất quyền header. Cần so từng tên với allowlist đã định nghĩa.

### 10.2. Pseudocode allowlist

~~~js
const allowedOrigins = new Set([
  "https://app.example.test"
]);

const allowedMethods = new Set(["GET", "POST"]);

const allowedHeaders = new Set([
  "content-type",
  "authorization",
  "x-request-id"
]);

function parseRequestedHeaderNames(value) {
  if (!value) return [];

  return value
    .split(",")
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
}

function evaluatePreflight(request) {
  const origin = request.headers.origin;
  const method = request.headers["access-control-request-method"];
  const requestedHeaders = parseRequestedHeaderNames(
    request.headers["access-control-request-headers"]
  );

  if (!allowedOrigins.has(origin)) return { allowed: false };
  if (!allowedMethods.has(method)) return { allowed: false };

  const allHeadersAllowed = requestedHeaders.every((name) =>
    allowedHeaders.has(name)
  );

  if (!allHeadersAllowed) return { allowed: false };

  return {
    allowed: true,
    origin,
    method,
    headers: requestedHeaders
  };
}
~~~

Đây là pseudocode minh họa, không phải middleware hoàn chỉnh. Cần xử lý header parsing, token syntax, lỗi HTTP, endpoint mapping, credentials, cache và CORS response theo framework/server thực tế. Không lấy kết quả `allowed: true` làm kết luận người dùng có quyền thực hiện nghiệp vụ.

### 10.3. Không yêu cầu xác thực phiên trên preflight

Vì browser preflight không mang credentials của request thực tế, middleware yêu cầu cookie đăng nhập cho mọi `OPTIONS` có thể làm request CORS hợp lệ thất bại trước khi gửi request thật.

Cách xử lý:

- Cho phép endpoint xử lý preflight theo origin/method/header policy đã cấu hình.
- Không thực hiện nghiệp vụ thay đổi dữ liệu trong preflight.
- Không trả allowlist cho origin tùy ý.
- Request thực tế vẫn phải qua authentication/authorization bình thường.
- Với credentialed CORS, response CORS cần cấu hình credentials đúng; cookie thật vẫn chịu chính sách browser.

## 11. Cache của preflight và header `Vary`

Server có thể chỉ định thời gian browser cache kết quả preflight bằng:

~~~http
Access-Control-Max-Age: 600
~~~

Đơn vị là giây. Browser có thể áp dụng giới hạn riêng và không nhất thiết cache đúng thời gian server yêu cầu.

Cần phân biệt:

- **Preflight cache** của browser lưu quyền CORS đã kiểm tra theo các khóa liên quan đến origin, URL, method và header names.
- **HTTP cache** và cache trung gian có quy tắc riêng. Nếu response thay đổi theo request header hoặc origin, phải cấu hình `Vary` tương ứng để tránh dùng nhầm response đã cache.

Ví dụ server tạo `Access-Control-Allow-Origin` động theo origin:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Nếu cache HTTP lưu response OPTIONS phụ thuộc cả origin, requested method và requested headers, cân nhắc:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Chỉ thêm những chiều thực sự ảnh hưởng response. Cấu hình cache sai có thể khiến response CORS được tái sử dụng trong ngữ cảnh không phù hợp.

## 12. Các lỗi cấu hình thường gặp

### Lỗi 1 — Chỉ cho phép origin mà quên header

Frontend gửi:

~~~js
fetch("https://api.example.test/data", {
  headers: { "X-Request-ID": "abc" }
});
~~~

Server chỉ trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Preflight không được phép dùng `X-Request-ID`, nên browser chặn luồng CORS. Cần thêm header name vào ACAH nếu thực sự cần.

### Lỗi 2 — Dùng sai ACAH để đọc response header

Server muốn frontend đọc `X-RateLimit-Remaining` nhưng chỉ trả:

~~~http
Access-Control-Allow-Headers: X-RateLimit-Remaining
~~~

Đây là sai chiều. Cần `Access-Control-Expose-Headers`:

~~~http
Access-Control-Expose-Headers: X-RateLimit-Remaining
~~~

### Lỗi 3 — Nghĩ `Content-Type: application/json` là safelisted

`application/json` không nằm trong ba MIME type safelisted của Content-Type. POST JSON cross-origin thường cần preflight. Server phải cho phép `Content-Type` trong ACAH.

### Lỗi 4 — Dùng wildcard với credentials

~~~http
Access-Control-Allow-Headers: *
Access-Control-Allow-Credentials: true
~~~

Wildcard không hoạt động như danh sách mọi header khi credentials mode là include. Liệt kê header names cần thiết tường minh.

### Lỗi 5 — Quên Authorization không được wildcard bao phủ

~~~http
Access-Control-Allow-Headers: *
~~~

Không đủ để cho phép `Authorization`. Cần ghi rõ:

~~~http
Access-Control-Allow-Headers: Authorization, Content-Type
~~~

### Lỗi 6 — Phản chiếu mọi header mà client yêu cầu

Nếu server copy trực tiếp `Access-Control-Request-Headers` vào ACAH, allowlist không còn thể hiện chính sách rõ ràng. Hãy parse, normalize, kiểm tra từng tên theo endpoint policy.

### Lỗi 7 — Nhầm ACAH là xác thực

Cho phép `X-Admin-Action` trong CORS không chứng minh người gửi là admin. Client ngoài browser cũng có thể tự gửi header này. Backend phải xác minh session/token và quyền thực tế.

### Lỗi 8 — Bỏ qua header do browser cấm script tự đặt

Liệt kê `Cookie`, `Host` hoặc `Origin` trong ACAH không cho JavaScript quyền vượt qua forbidden header rules. Dùng cơ chế browser quản lý đúng chức năng.

## 13. Ma trận quyết định: request header có cần ACAH không?

| Request header | Safelisted? | Thường cần preflight khi cross-origin? | Ghi chú |
| --- | --- | --- | --- |
| `Accept` với giá trị hợp lệ | Có | Không vì riêng header này | Giá trị vẫn phải thỏa safelist. |
| `Accept-Language` hợp lệ | Có | Không vì riêng header này | Có giới hạn giá trị. |
| `Content-Type: application/x-www-form-urlencoded` | Có | Không vì riêng header này | Không có nghĩa request an toàn nghiệp vụ. |
| `Content-Type: multipart/form-data` | Có | Không vì riêng header này | Browser thường tự quản lý boundary khi dùng FormData. |
| `Content-Type: text/plain` | Có | Không vì riêng header này | Vẫn cần kiểm tra nội dung ở server. |
| `Content-Type: application/json` | Không | **Có** | Cần ACAH cho Content-Type. |
| `Authorization` | Không | **Có** | Phải nêu tường minh; wildcard không bao phủ. |
| `X-Request-ID` | Không | **Có** | Custom header. |
| `X-API-Key` | Không | **Có** | Không nên dùng header như bằng chứng duy nhất của quyền. |
| `Range` single range hợp lệ | Có | Không vì riêng header này | Range nhiều khoảng có thể không safelisted. |
| `Cookie` do script tự đặt | Forbidden | Script không được tùy ý đặt | Cookie do browser quản lý. |
| `Host` do script tự đặt | Forbidden | Script không được tùy ý đặt | Browser/network stack quản lý. |

Nếu request đã preflight do method không safelisted, browser kiểm tra method và tất cả request headers không safelisted mà request thật định gửi. Bảng trên nói về tác động của từng header riêng lẻ; các yếu tố khác trong request vẫn có thể làm phát sinh preflight.

## 14. Thực hành A — Quan sát preflight trong DevTools

Thực hiện trong môi trường local hoặc staging do bạn kiểm soát. Chuẩn bị:

- Frontend: `http://localhost:3000`.
- API: `http://localhost:4000`.
- API có endpoint `POST /v1/demo` và xử lý `OPTIONS` cho endpoint đó.

Mở DevTools → **Network**, bật Preserve log và chạy từ frontend:

~~~js
fetch("http://localhost:4000/v1/demo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "demo-001"
  },
  body: JSON.stringify({ message: "hello" })
});
~~~

Quan sát:

1. Request `OPTIONS` xuất hiện trước.
2. Trong Request Headers, tìm `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Preflight thường liệt kê `content-type` và `x-request-id` trong header request.
4. Trong Response Headers, kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
5. Nếu preflight thành công, quan sát request POST thực tế và response của nó.

Nếu API không trả ACAH cho `X-Request-ID`, browser sẽ báo CORS error và không cho JavaScript thực hiện luồng cross-origin theo chính sách đó.

## 15. Thực hành B — So sánh header safelisted và không safelisted

Từ cùng frontend, thử từng request:

~~~js
// Thường không preflight vì Accept là safelisted với giá trị phù hợp.
fetch("http://localhost:4000/v1/demo", {
  headers: { "Accept": "application/json" }
});

// Thường preflight vì X-Debug là custom header.
fetch("http://localhost:4000/v1/demo", {
  headers: { "X-Debug": "1" }
});

// Thường preflight vì application/json không phải safelisted Content-Type.
fetch("http://localhost:4000/v1/demo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ ok: true })
});
~~~

Ghi nhận số request OPTIONS và header được browser liệt kê. Thay đổi giá trị Content-Type hoặc dùng giá trị Accept không thỏa quy tắc safelist trong môi trường thử nghiệm để xem hành vi thay đổi.

Không kết luận chỉ dựa trên tên header: **giá trị và toàn bộ request** có thể ảnh hưởng quyết định preflight.

## 16. Thực hành C — Kiểm tra wildcard và Authorization

Trên API thử nghiệm, trước hết cấu hình:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Headers: *
~~~

Từ frontend thử gửi custom header:

~~~js
fetch("http://localhost:4000/v1/demo", {
  headers: { "X-Debug": "1" }
});
~~~

Quan sát hành vi với request không dùng credentials.

Sau đó thử:

~~~js
fetch("http://localhost:4000/v1/demo", {
  headers: { "Authorization": "Bearer demo-token" }
});
~~~

Wildcard không bao phủ `Authorization`; server cần cho phép tường minh:

~~~http
Access-Control-Allow-Headers: Authorization, X-Debug
~~~

Cuối cùng, thử request với `credentials: "include" và xác minh wildcard không còn có ý nghĩa “mọi header”. Bài thử chỉ dùng token giả, không dùng thông tin xác thực thật.

## 17. Thực hành D — Phân biệt ACAH và ACEH

Cho API thử nghiệm trả:

~~~http
X-Request-ID: demo-123
Content-Disposition: attachment; filename="demo.txt"
~~~

Frontend:

~~~js
const response = await fetch("http://localhost:4000/v1/demo");

console.log(response.headers.get("Content-Type"));
console.log(response.headers.get("X-Request-ID"));
console.log(response.headers.get("Content-Disposition"));
~~~

Ban đầu, một số response headers không safelisted có thể không đọc được qua Fetch API. Thêm vào response:

~~~http
Access-Control-Expose-Headers: X-Request-ID, Content-Disposition
~~~

Gọi lại và quan sát. Không thay ACAH để giải quyết bài thử này; ACAH áp dụng cho request headers, còn ACEH áp dụng cho response headers.

## 18. Checklist review cấu hình Allowed Headers

- [ ] Liệt kê chính xác request headers mà frontend thực sự cần cho từng endpoint.
- [ ] Phân biệt header safelisted với header làm phát sinh preflight; xem cả tên và giá trị.
- [ ] Kiểm tra `Content-Type` có dùng MIME type safelisted hay không.
- [ ] Nêu rõ `Authorization` khi cần; không trông chờ wildcard.
- [ ] Với credentialed request, dùng origin và header names cụ thể; không dùng wildcard như danh sách bao quát.
- [ ] Normalize header names theo quy tắc không phân biệt hoa/thường trước khi so allowlist.
- [ ] Không phản chiếu tùy ý `Access-Control-Request-Headers`.
- [ ] Không cho phép header giả danh vai trò/quyền nội bộ chỉ vì frontend yêu cầu.
- [ ] Không cố cho phép các forbidden request headers như `Cookie` hoặc `Host` qua ACAH.
- [ ] Xử lý preflight `OPTIONS` không phụ thuộc cookie phiên của request thật; không thực hiện nghiệp vụ trong preflight.
- [ ] Request thực tế vẫn xác thực, phân quyền, validate header values và body.
- [ ] Nếu cần JavaScript đọc response header, cấu hình ACEH riêng; không nhầm với ACAH.
- [ ] Nếu ACAO thay đổi theo origin, trả `Vary: Origin`; nếu HTTP cache cho OPTIONS phụ thuộc method/header, cấu hình Vary tương ứng.
- [ ] Cấu hình `Access-Control-Max-Age` hợp lý và kiểm tra hành vi cache thực tế.
- [ ] Kiểm tra trên browser mục tiêu bằng Network và log server; không dùng `curl` để kết luận browser CORS thành công.

## 19. Những ngộ nhận thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “ACAH cho phép JavaScript đọc response headers.” | **Sai** | Dùng `Access-Control-Expose-Headers` cho việc đó. |
| “CORS-safelisted nghĩa là dữ liệu an toàn.” | **Sai** | Safelist chỉ ảnh hưởng preflight, không chứng minh nội dung an toàn. |
| “POST JSON luôn là simple request.” | **Sai** | `application/json` không thuộc safelisted Content-Type. |
| “Chỉ cần ACAO là đủ cho mọi custom header.” | **Sai** | Request header không safelisted cần được cho phép qua preflight. |
| “`Access-Control-Allow-Headers: *` luôn cho phép tất cả.” | **Sai** | Có giới hạn với credentials và ngoại lệ Authorization. |
| “Cho phép Authorization nghĩa là token hợp lệ.” | **Sai** | Backend phải xác minh token và quyền. |
| “ACAH có thể cho JavaScript đặt Cookie hoặc Host.” | **Sai** | Forbidden request-header rules vẫn áp dụng. |
| “OPTIONS preflight đã xác thực người dùng.” | **Sai** | Preflight thường không mang credentials; request thật phải xác thực. |
| “CORS thay thế CSRF.” | **Sai** | Một số request cross-origin vẫn có thể được gửi mà không cần đọc response. |
| “Dùng curl thành công chứng minh CORS đúng.” | **Sai** | curl không thực thi SOP/CORS như browser. |
| “Tên header phân biệt chữ hoa/thường.” | **Sai** | HTTP field names không phân biệt hoa/thường. |
| “Chỉ cần cho phép mọi X-* header để khỏi lỗi frontend.” | **Sai** | Cấp quyền quá rộng, làm giảm khả năng kiểm soát chính sách. |

## 20. Tổng kết

`Access-Control-Allow-Headers` là một phần của CORS preflight, cho phép server khai báo những **request header names** mà browser được phép dùng trong request cross-origin. Nó hoạt động cùng `Access-Control-Allow-Origin` và `Access-Control-Allow-Methods` để kiểm tra chính sách trước request thật.

Ba nguyên tắc cần nhớ:

1. **Đúng chiều:** ACAH cho phép request headers; ACEH cho phép JavaScript đọc response headers. Đừng dùng lẫn hai header này.
2. **Đúng phạm vi:** Header safelist có điều kiện; custom headers, JSON Content-Type và Authorization thường cần preflight. Wildcard có giới hạn, đặc biệt với credentials và Authorization.
3. **Đúng trách nhiệm:** CORS không phải authentication, authorization hay CSRF protection. Server phải allowlist origin/method/header theo nhu cầu, validate input và kiểm tra quyền trên request thật.

Khi debug một lỗi CORS, hãy xem lần lượt: **request có preflight không, browser yêu cầu những header nào, server cho phép những header nào, credentials có được dùng không, và request thực tế đã tới backend hay chưa?** Cách phân tích này giúp sửa đúng cấu hình mà vẫn giữ chính sách cross-origin ở mức tối thiểu cần thiết.
