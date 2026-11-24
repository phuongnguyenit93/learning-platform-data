# Preflight request: kiểm tra trước khi gửi CORS request

## 1. Preflight request giải quyết vấn đề gì?

Một ứng dụng frontend tại `https://app.example.com` cần cập nhật dữ liệu qua API ở `https://api.example.net`. Hai địa chỉ khác origin, vì vậy JavaScript không mặc nhiên được đọc phản hồi API. Cơ chế **Cross-Origin Resource Sharing (CORS)** cho phép server công bố những origin nào được đọc phản hồi và những phương thức/header nào được phép dùng.

Với một số request cross-origin, trình duyệt gửi trước một request kiểm tra bằng phương thức **OPTIONS**. Request này gọi là **CORS preflight request**. Nó hỏi server xem request thật sắp tới có được phép dùng phương thức và các request header đã khai báo hay không. Nếu preflight không được chấp thuận, trình duyệt không gửi request thật theo luồng CORS đó.

Preflight là một phần của mô hình bảo mật trình duyệt, không phải một bước xác thực người dùng. Server vẫn phải xác thực và phân quyền request thật. Để hiểu chính xác hành vi, cần phân biệt:

- **Preflight request:** request OPTIONS do trình duyệt tự tạo để kiểm tra chính sách CORS.
- **Actual request:** request nghiệp vụ mà JavaScript muốn gửi, ví dụ GET, POST, PUT hoặc DELETE.
- **CORS response check:** bước trình duyệt kiểm tra header của phản hồi thực tế trước khi cho JavaScript đọc nội dung.

Sau bài học, bạn có thể nhận diện khi nào trình duyệt phát sinh preflight, đọc request/response OPTIONS, cấu hình các header CORS cần thiết, xử lý credentials và preflight cache, cũng như chẩn đoán lỗi bằng DevTools.

## 2. Khi nào trình duyệt gửi preflight?

Không phải mọi request cross-origin đều có preflight. Trình duyệt có thể gửi trực tiếp một **CORS-safelisted request** (trước đây thường được gọi là *simple request*) nếu request đáp ứng các điều kiện của Fetch/CORS. Những request vượt ra ngoài nhóm an toàn này thường cần preflight.

Các trường hợp phổ biến làm phát sinh preflight:

1. Phương thức không thuộc nhóm safelisted: `PUT`, `PATCH`, `DELETE` hoặc phương thức tùy chỉnh.
2. Có request header không thuộc nhóm CORS-safelisted, ví dụ `Authorization`, `X-Request-ID` hoặc `X-CSRF-Token`.
3. `Content-Type` không thuộc các giá trị safelisted, ví dụ `application/json`.
4. Một request header safelisted có giá trị không đáp ứng các giới hạn về byte/giá trị theo chuẩn.

Các phương thức safelisted thường gặp là `GET`, `HEAD` và `POST`. Các request header safelisted phổ biến gồm `Accept`, `Accept-Language`, `Content-Language`, `Content-Type` với một số MIME type giới hạn như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`, và `Range` trong dạng single-range được cho phép.

Ví dụ:

| Request từ `https://app.example.com` tới API khác origin | Preflight? | Lý do |
| --- | --- | --- |
| `GET /products` không có header tùy chỉnh | Thường không | Phương thức và header thuộc nhóm safelisted. |
| `POST /feedback` với `Content-Type: application/x-www-form-urlencoded` | Thường không | Request có thể đáp ứng điều kiện safelisted. |
| `POST /orders` với `Content-Type: application/json` | Có | MIME type JSON không thuộc nhóm safelisted. |
| `PUT /profile` | Có | PUT không phải phương thức safelisted. |
| `GET /profile` kèm `Authorization: Bearer ...` | Có | Authorization không phải request header safelisted. |
| `POST /search` kèm `X-Request-ID` | Có | Header tùy chỉnh làm request cần kiểm tra trước. |

**Credentials không tự nó làm phát sinh preflight.** Một request GET cross-origin dùng `credentials: "include"` nhưng không có phương thức/header ngoài nhóm safelisted có thể được gửi mà không cần OPTIONS. Tuy nhiên, phản hồi vẫn phải đáp ứng quy tắc CORS dành cho credentials thì JavaScript mới đọc được.

## 3. Luồng hoạt động của preflight

Giả sử frontend muốn cập nhật hồ sơ:

```javascript
const response = await fetch("https://api.example.net/v1/profile", {
  method: "PUT",
  mode: "cors",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer access-token"
  },
  body: JSON.stringify({ displayName: "Lan" })
});

if (!response.ok) {
  throw new Error("Không cập nhật được hồ sơ");
}

const result = await response.json();
```

Do phương thức PUT, Content-Type JSON và Authorization, trình duyệt cần preflight. Trình tự tổng quát:

```text
JavaScript ở app.example.com
        │
        │ fetch(PUT, application/json, Authorization)
        ▼
Trình duyệt đánh giá CORS request
        │
        │ OPTIONS preflight
        ▼
API trả Access-Control-Allow-*
        │
        ├── Không đạt ──> Chặn request thật; fetch báo lỗi CORS
        │
        └── Đạt
              │
              ▼
        Gửi request PUT thật
              │
              ▼
        API xử lý, trả response
              │
              ▼
        Trình duyệt kiểm tra CORS response
              │
              ├── Không đạt ──> JavaScript không đọc được response
              └── Đạt ────────> JavaScript nhận Response
```

Preflight thành công **không bảo đảm request thật thành công**. Request thật vẫn có thể bị từ chối vì session hết hạn, token sai, thiếu quyền, dữ liệu không hợp lệ hoặc lỗi server. Ngược lại, server có thể đã xử lý request thật nhưng JavaScript không đọc được phản hồi nếu response thực tế thiếu header CORS hợp lệ.

## 4. Đọc request OPTIONS preflight

Với ví dụ trên, trình duyệt có thể gửi request tương tự:

```http
OPTIONS /v1/profile HTTP/1.1
Host: api.example.net
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization, content-type
```

Ý nghĩa:

| Header | Ý nghĩa |
| --- | --- |
| `Origin` | Origin của document khởi tạo request. |
| `Access-Control-Request-Method` | Phương thức mà request thật muốn sử dụng. |
| `Access-Control-Request-Headers` | Danh sách request header không safelisted mà request thật muốn gửi. |

Header trong `Access-Control-Request-Headers` thường được biểu diễn bằng tên chữ thường và danh sách phân tách dấu phẩy. Server nên so sánh tên header theo quy tắc không phân biệt hoa thường, đồng thời chỉ chấp nhận những header nghiệp vụ đã cho phép.

**Preflight request không mang credentials của request thật.** Không kỳ vọng cookie phiên hoặc Authorization header của request thật xuất hiện trong OPTIONS. Nếu preflight gateway bắt buộc có session cookie mới trả lời, trình duyệt có thể không hoàn tất được luồng. Server cần xử lý OPTIONS theo chính sách CORS cho route, trong khi request thật vẫn phải qua xác thực và phân quyền bình thường.

## 5. Phản hồi preflight và các header cần thiết

API có thể trả về:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Không phải ứng dụng nào cũng cần tất cả header trong ví dụ. Ý nghĩa từng header:

| Response header | Vai trò |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép dùng request cross-origin và đọc phản hồi. Với credentials, cần trả origin cụ thể thay vì `*`. |
| `Access-Control-Allow-Methods` | Các phương thức được phép cho request thật. |
| `Access-Control-Allow-Headers` | Các request header không safelisted được phép gửi. |
| `Access-Control-Allow-Credentials` | Cho phép response được đọc trong request có credentials khi giá trị là chính xác `true`. |
| `Access-Control-Max-Age` | Thời gian đề nghị lưu kết quả preflight trong CORS-preflight cache của trình duyệt. |
| `Vary` | Hướng dẫn HTTP cache phân biệt response theo các request header có ảnh hưởng đến nội dung response. |

### 5.1 Access-Control-Allow-Origin

Nếu chỉ cho phép frontend `https://app.example.com`, server có thể trả:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Không nên phản chiếu tùy ý header `Origin` nhận được. Nếu server hỗ trợ nhiều frontend, hãy parse và đối chiếu origin với allowlist chính xác gồm scheme, host và port. Tránh kiểm tra bằng chuỗi con như `origin.includes("example.com")` vì `https://example.com.attacker.test` không phải origin được phép.

Origin opaque có thể được serialize thành `null`. Không đưa `Origin: null` vào allowlist một cách tùy tiện; nhiều ngữ cảnh khác nhau có thể có cùng chuỗi serialization này.

### 5.2 Access-Control-Allow-Methods

Với request thật dùng PUT, preflight response phải cho phép phương thức PUT:

```http
Access-Control-Allow-Methods: GET, POST, PUT
```

Header này không tự thay thế kiểm tra quyền của endpoint. Server vẫn cần kiểm tra người dùng có được phép cập nhật hồ sơ hay không. `OPTIONS` thường được xử lý để trả chính sách CORS; nó không có nghĩa endpoint nghiệp vụ phải mở công khai mọi phương thức được liệt kê.

### 5.3 Access-Control-Allow-Headers

Nếu request thật gửi `Authorization` và `Content-Type`, server cần cho phép chúng:

```http
Access-Control-Allow-Headers: Authorization, Content-Type
```

Không dùng wildcard để thay thế allowlist header trong luồng credentials. Đặc biệt, `Authorization` là header cần được liệt kê tường minh; không dựa vào `Access-Control-Allow-Headers: *` để cấp quyền cho nó.

### 5.4 Access-Control-Allow-Credentials

Khi frontend dùng:

```javascript
fetch("https://api.example.net/me", {
  credentials: "include"
});
```

Response CORS cần có:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Với credentials mode `include`, `Access-Control-Allow-Origin: *` không hợp lệ để cho JavaScript đọc phản hồi. Giá trị `Access-Control-Allow-Credentials` phải là chữ thường `true`. Việc cookie thực sự được gửi còn phụ thuộc thuộc tính cookie `SameSite`, `Secure`, chính sách cookie bên thứ ba và cài đặt trình duyệt.

### 5.5 Access-Control-Max-Age và Vary

`Access-Control-Max-Age` cho phép trình duyệt lưu kết quả preflight trong một **CORS-preflight cache** riêng. Ví dụ:

```http
Access-Control-Max-Age: 600
```

Giá trị này là thời gian tối đa server đề nghị; trình duyệt có thể áp dụng giới hạn thấp hơn. Cache preflight không đồng nhất với HTTP cache thông thường. Thay đổi chính sách CORS có thể chưa có hiệu lực ngay trên client nếu kết quả preflight cũ còn được lưu.

Nếu server chọn `Access-Control-Allow-Origin` động theo request `Origin`, nên gửi:

```http
Vary: Origin
```

Nếu response OPTIONS cũng được cache bởi tầng HTTP/CDN theo method/header yêu cầu, cân nhắc `Vary: Access-Control-Request-Method, Access-Control-Request-Headers` để tránh dùng nhầm kết quả cho một request khác. Hãy cấu hình cache theo thực tế hệ thống, không sao chép máy móc một danh sách Vary không cần thiết.

## 6. Request thật sau preflight

Sau khi preflight được chấp nhận, trình duyệt mới gửi request thật. Với `credentials: "include"`, request thật có thể mang cookie phù hợp:

```http
PUT /v1/profile HTTP/1.1
Host: api.example.net
Origin: https://app.example.com
Content-Type: application/json
Authorization: Bearer access-token
Cookie: session=opaque-session-id

{"displayName":"Lan"}
```

Server xử lý request như một API thông thường: xác thực session/token, kiểm tra quyền, xác thực dữ liệu, chống CSRF nếu luồng cookie yêu cầu, rồi trả phản hồi.

Phản hồi thật cũng cần header CORS tương ứng:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin

{"id":"user-123","displayName":"Lan"}
```

Một lỗi phổ biến là cấu hình header cho OPTIONS nhưng quên thêm CORS header vào response thật. Khi đó preflight có thể thành công, server có thể đã cập nhật hồ sơ, nhưng JavaScript vẫn báo lỗi CORS vì không được phép đọc response.

Nếu JavaScript cần đọc response header không safelisted, ví dụ `X-Request-ID`, server cần thêm:

```http
Access-Control-Expose-Headers: X-Request-ID
```

Nếu không, header đó có thể tồn tại trong Network panel nhưng không xuất hiện qua `response.headers.get("X-Request-ID")`.

## 7. Cấu hình server an toàn

Server nên có một chính sách CORS tường minh cho từng nhóm endpoint. Ví dụ cấu hình khái niệm:

```text
Allowed origins:
  - https://app.example.com

Allowed methods:
  - GET
  - POST
  - PUT

Allowed request headers:
  - Authorization
  - Content-Type
  - X-Request-ID

Credentials:
  - true (chỉ cho origin đã được allowlist)

Preflight max age:
  - 600 seconds
```

Một luồng xử lý phía server có thể mô tả như sau:

```text
Nhận request
   │
   ├─ Có Origin?
   │    ├─ Không ──> Xử lý theo chính sách same-origin/non-CORS
   │    └─ Có
   │         │
   │         ├─ Origin nằm trong allowlist?
   │         │    ├─ Không ──> Không cấp CORS permission
   │         │    └─ Có
   │         │         │
   │         │         ├─ OPTIONS + Access-Control-Request-Method?
   │         │         │    └─ Trả preflight headers theo route policy
   │         │         │
   │         │         └─ Request thật
   │         │              ├─ Xác thực
   │         │              ├─ Phân quyền
   │         │              ├─ Kiểm tra CSRF nếu cần
   │         │              └─ Xử lý và trả CORS headers
```

Các nguyên tắc quan trọng:

1. **Allowlist chính xác:** đối chiếu origin chuẩn hóa; không dùng wildcard hoặc regex lỏng cho API nhạy cảm.
2. **Xử lý OPTIONS riêng:** preflight không có credentials nên không bắt buộc session cookie; vẫn phải xác định route, origin, method và header được phép.
3. **Bảo vệ request thật:** không bỏ xác thực/phân quyền chỉ vì OPTIONS được phép.
4. **Header nhất quán:** response thật, kể cả response lỗi mà frontend cần đọc, cũng phải có CORS header đúng.
5. **Không tin Origin như danh tính:** header Origin giúp áp dụng chính sách trình duyệt; nó không thay thế session, token hoặc authorization.
6. **Giới hạn tối thiểu:** chỉ cho phép method/header cần thiết và chỉ bật credentials ở những endpoint cần.

### Ví dụ pseudocode xử lý OPTIONS

```javascript
const allowedOrigins = new Set([
  "https://app.example.com"
]);
const allowedMethods = new Set(["GET", "POST", "PUT"]);
const allowedHeaders = new Set([
  "authorization",
  "content-type",
  "x-request-id"
]);

function handlePreflight(req, res) {
  const origin = req.headers.origin;
  const requestedMethod =
    req.headers["access-control-request-method"];
  const requestedHeaders = (req.headers[
    "access-control-request-headers"
  ] ?? "")
    .split(",")
    .map(value => value.trim().toLowerCase())
    .filter(Boolean);

  if (!allowedOrigins.has(origin)) {
    return res.status(403).end();
  }

  if (!allowedMethods.has(requestedMethod)) {
    return res.status(405).end();
  }

  if (!requestedHeaders.every(name => allowedHeaders.has(name))) {
    return res.status(403).end();
  }

  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT");
  res.setHeader(
    "Access-Control-Allow-Headers",
    "Authorization, Content-Type, X-Request-ID"
  );
  res.setHeader("Access-Control-Max-Age", "600");
  res.setHeader(
    "Vary",
    "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
  );
  return res.status(204).end();
}
```

Đây là pseudocode minh họa, không phải middleware dùng nguyên trạng. Trong hệ thống thực tế, cần xử lý header lặp, giá trị không hợp lệ, route-specific policy, method chuẩn hóa, logging và response lỗi. CORS header cho request thật phải được thêm ở middleware phù hợp sau khi server quyết định chính sách origin.

## 8. Những nhầm lẫn và lỗi thường gặp

### 8.1 “Preflight chặn mọi request không được phép”

Không chính xác. Request CORS-safelisted có thể được gửi mà không có preflight. Nếu server thực hiện hành động trước khi response CORS được kiểm tra, hành động đã xảy ra dù JavaScript không đọc được response. Do đó không dùng CORS làm cơ chế chống CSRF hoặc xác thực.

### 8.2 “OPTIONS thành công nghĩa là API cho phép người dùng”

Không. OPTIONS chỉ xác nhận trình duyệt có thể tiếp tục request theo chính sách CORS. Request thật vẫn phải qua authentication, authorization, validation và CSRF protection.

### 8.3 “Chỉ cần header ở OPTIONS”

Không. Preflight response và actual response có nhiệm vụ riêng. Nếu actual response thiếu `Access-Control-Allow-Origin` phù hợp, JavaScript vẫn không đọc được kết quả.

### 8.4 “credentials: include luôn tạo preflight”

Không. Credentials mode không tự làm request trở thành non-safelisted. Một GET không có header ngoài nhóm safelisted có thể được gửi mà không OPTIONS, nhưng response phải đáp ứng quy tắc credentials.

### 8.5 “Dùng mode: no-cors để bỏ qua CORS”

Không. `mode: "no-cors"` không cấp quyền đọc response. Kết quả thường là **opaque response** với status/body/header không thể truy cập theo cách thông thường. Đây không phải cách khắc phục CORS cho API cần dữ liệu.

### 8.6 “Postman hoặc curl chạy được thì trình duyệt phải chạy được”

Không. curl/Postman không thực thi mô hình SOP/CORS giống trình duyệt. Chúng có thể gửi request trực tiếp và hiển thị response dù thiếu CORS header. Cần kiểm tra trong browser DevTools để xác minh hành vi thực tế của CORS.

### 8.7 “Mọi lỗi CORS đều do server chưa cho phép origin”

Chưa đủ. Có thể lỗi do preflight bị redirect, OPTIONS bị authentication gateway chặn, method/header chưa được allow, wildcard dùng sai với credentials, response lỗi thiếu CORS header, cache cũ hoặc request URL chuyển hướng sang endpoint khác.

### 8.8 Redirect sau preflight

Một số luồng cross-origin có preflight rồi mới gặp redirect ở request thật có thể gặp khác biệt hỗ trợ giữa trình duyệt. Nếu API có thể tránh redirect, hãy gọi trực tiếp URL cuối cùng; đặc biệt kiểm tra chuỗi redirect, scheme, host và CORS header ở từng phản hồi liên quan.

## 9. Chẩn đoán preflight bằng DevTools

Mở Developer Tools → **Network**, bật giữ log khi cần, sau đó thực hiện request từ frontend. Tìm request OPTIONS và request thật tương ứng.

| Quan sát | Câu hỏi cần kiểm tra |
| --- | --- |
| OPTIONS không xuất hiện | Request có cùng origin? Method/header có thực sự cần preflight? Request có bị chặn trước khi phát ra không? |
| OPTIONS trả 401/403 | Gateway có yêu cầu cookie/token cho preflight không? Origin/method/header có trong allowlist không? |
| OPTIONS trả 404/405 | Server hoặc reverse proxy có route OPTIONS? |
| OPTIONS trả 3xx | Có redirect HTTP/HTTPS, slash chuẩn hóa hoặc chuyển host không? |
| OPTIONS 2xx nhưng request thật không xuất hiện | Các giá trị Allow-Origin/Methods/Headers/Credentials có khớp request không? |
| Request thật xuất hiện nhưng JavaScript báo CORS | Actual response có CORS header hợp lệ không? Response lỗi hoặc redirect có bị thiếu header? |
| Response đọc được nhưng cookie không gửi | Kiểm tra credentials mode, SameSite, Secure, domain/path, chính sách cookie bên thứ ba. |
| Thay đổi cấu hình nhưng lỗi vẫn còn | Kiểm tra CORS-preflight cache và HTTP/CDN cache; thử profile hoặc phiên thử nghiệm mới. |

### Thí nghiệm: tạo preflight có thể quan sát

Giả sử có hai server phát triển:

- Frontend: `http://localhost:3000`.
- API: `http://localhost:4000`.

Frontend gọi:

```javascript
fetch("http://localhost:4000/api/items/42", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "lab-42"
  },
  body: JSON.stringify({ name: "Notebook" })
})
  .then(response => response.json())
  .then(console.log)
  .catch(console.error);
```

Do PATCH, JSON và header tùy chỉnh, trình duyệt cần OPTIONS. API thử nghiệm có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET, POST, PATCH, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Request-ID
Access-Control-Max-Age: 300
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Response PATCH thật cũng cần:

```http
Access-Control-Allow-Origin: http://localhost:3000
Content-Type: application/json
Vary: Origin
```

Thử lần lượt:

1. Xóa `PATCH` khỏi `Access-Control-Allow-Methods`. Quan sát OPTIONS thất bại và request PATCH không được gửi theo luồng CORS.
2. Khôi phục PATCH nhưng xóa `X-Request-ID` khỏi `Access-Control-Allow-Headers`. Preflight vẫn bị từ chối vì request muốn gửi header này.
3. Cho phép preflight, sau đó xóa `Access-Control-Allow-Origin` khỏi response PATCH. Server có thể xử lý request, nhưng JavaScript không đọc được response.
4. Khôi phục header, gửi lại request. Quan sát OPTIONS có thể không xuất hiện ở lần tiếp theo vì kết quả đã được cache.
5. Thay URL API sang một origin khác và kiểm tra lại. Đừng giả định kết quả cache cho origin/method/header trước tự động áp dụng cho request mới.

Thực hành chỉ trên server thử nghiệm do bạn kiểm soát; không dùng endpoint nhạy cảm hoặc gửi dữ liệu thật.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `POST` với `application/json` thường cần preflight nhưng `POST` với `application/x-www-form-urlencoded` có thể không?
2. Header nào trong OPTIONS cho biết phương thức và request header mà request thật muốn dùng?
3. Vì sao preflight không cần session cookie nhưng request thật vẫn có thể dùng `credentials: "include"`?
4. Nếu OPTIONS trả 204 và đầy đủ header, tại sao JavaScript vẫn có thể báo lỗi CORS sau khi server xử lý request?
5. Tại sao `Access-Control-Allow-Origin: *` không phù hợp với response có credentials?
6. `Access-Control-Max-Age` tác động tới loại cache nào? Vì sao thay đổi cấu hình CORS có thể chưa xuất hiện ngay ở trình duyệt?
7. CORS preflight có thay thế CSRF token hoặc authorization ở backend không?
8. Vì sao curl/Postman thành công không chứng minh request sẽ thành công từ JavaScript trong trình duyệt?

## 11. Tổng kết

**CORS preflight request** là request OPTIONS do trình duyệt tự gửi trước một số request cross-origin không thuộc nhóm safelisted. Nó mô tả origin, phương thức và các request header dự kiến bằng `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Server trả lời bằng `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và các header liên quan. Nếu preflight đạt yêu cầu, trình duyệt mới gửi request thật; response thật vẫn phải vượt qua kiểm tra CORS riêng.

Thiết kế an toàn cần allowlist origin chính xác, method/header tối thiểu, xử lý OPTIONS không phụ thuộc credentials của request thật, cấu hình CORS nhất quán cho actual response và cache phù hợp. **CORS kiểm soát quyền JavaScript đọc phản hồi trong trình duyệt; nó không thay thế xác thực, phân quyền hay phòng vệ CSRF ở server.** Kiểm chứng bằng Network panel của trình duyệt là cách đáng tin cậy để hiểu request nào đã được gửi và response nào thực sự được phép đọc.
