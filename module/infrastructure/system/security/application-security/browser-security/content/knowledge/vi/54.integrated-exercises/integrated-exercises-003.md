# Thiết lập CORS

Cross-Origin Resource Sharing (CORS) là cơ chế cho phép máy chủ công bố những response mà JavaScript từ origin khác được phép đọc. CORS mở rộng khả năng chia sẻ dữ liệu có kiểm soát bên cạnh Same-Origin Policy (SOP). Để thiết lập CORS an toàn, cần xác định rõ origin nào được truy cập, endpoint nào được chia sẻ, method và header nào cần thiết, request có dùng credentials hay không và cách bảo vệ thao tác thay đổi trạng thái.

Bài thực hành này xây dựng một luồng tích hợp giữa portal đối tác và API tài khoản. Portal chạy ở origin khác với API, cần đọc dữ liệu tài khoản bằng session cookie và gửi một thao tác cập nhật có CSRF token. Bạn sẽ cấu hình CORS theo allowlist, xử lý preflight, kiểm tra credentials, xác minh request trong trình duyệt và kiểm tra rằng origin không được phép không thể đọc response.

Thiết lập CORS không phải là bật một header chung cho toàn bộ ứng dụng. Cấu hình phải khớp với hợp đồng API và mô hình tin cậy. CORS không thay thế authentication, authorization hoặc CSRF protection; các kiểm soát đó vẫn phải được thực thi ở phía máy chủ.

## Mục tiêu

Sau bài thực hành, bạn có thể:

- Xác định chính xác origin nguồn và origin đích theo scheme, host và port.
- Phân biệt request đơn giản với request cần preflight `OPTIONS`.
- Cấu hình allowlist origin, method, request header và credentials theo từng route.
- Xử lý cookie trong request cross-origin và hiểu giới hạn của `SameSite`.
- Kết hợp CORS với CSRF token, authentication và authorization phía máy chủ.
- Kiểm thử response được expose, request bị preflight chặn và request vẫn có thể tới server dù JavaScript không đọc được response.
- Đánh giá cache, error response, redirect và các lỗi cấu hình phổ biến.

## Bối cảnh bài lab

Bạn đang vận hành một ứng dụng quản lý tài khoản. API chính phục vụ tại `https://app.example.test`. Một portal đối tác chạy tại `https://portal.example.test` cần đọc thông tin tài khoản và gửi yêu cầu đổi email cho người dùng đã đăng nhập.

Hai URL có origin khác nhau vì hostname khác nhau, nhưng cùng scheme và cùng registrable domain nên thường là same-site. Điều này giúp quan sát được sự khác nhau giữa origin và site: CORS vẫn áp dụng vì hai origin khác nhau, còn cookie `SameSite=Lax` có thể được gửi trong request same-site nếu các điều kiện cookie và Fetch credentials đáp ứng.

Thêm một origin không được tin cậy `https://evil.example.test` để kiểm tra trường hợp subdomain cùng site nhưng không được cấp quyền. Có thể thêm `https://attacker.test` để kiểm tra một site khác hoàn toàn.

| Thành phần | Origin | Vai trò |
|---|---|---|
| API ứng dụng | `https://app.example.test` | Xác thực session và xử lý dữ liệu tài khoản |
| Portal đối tác | `https://portal.example.test` | Origin được cho phép gọi một số API |
| Subdomain không tin cậy | `https://evil.example.test` | Origin cùng site nhưng không có trong allowlist |
| Website bên ngoài | `https://attacker.test` | Origin khác site để kiểm tra request cross-site |

Sử dụng tài khoản thử nghiệm và dữ liệu giả lập. Không dùng session, cookie, token hoặc dữ liệu cá nhân thật. Nếu cần cookie `Secure`, hãy chạy lab qua HTTPS với chứng chỉ mà trình duyệt thử nghiệm tin cậy.

## Hiểu luồng CORS trước khi cấu hình

SOP giới hạn JavaScript đọc dữ liệu cross-origin. CORS cho phép server chỉ định origin nào có thể đọc response thông qua các header phản hồi. Trình duyệt thực thi quy tắc này; server vẫn nhận và xử lý request theo logic của nó.

Có ba tình huống cần phân biệt:

1. **Request được gửi và response được expose:** origin được cho phép, request đáp ứng CORS và JavaScript đọc được status/body theo quyền được cấp.
2. **Request được gửi nhưng response không được expose:** server có thể đã xử lý request, nhưng browser không cho script đọc response vì thiếu hoặc sai CORS header.
3. **Preflight thất bại:** browser không gửi request chính đối với request cần preflight, vì server không chấp nhận origin, method hoặc header được yêu cầu.

Form HTML và một số request đơn giản có thể gửi cross-origin mà không cần preflight. Do đó, CORS không phải cơ chế ngăn CSRF. Một request `POST` từ form có thể tới server dù JavaScript ở trang gửi không đọc được response.

### Origin là bộ ba

Origin gồm scheme, host và port. Các địa chỉ sau là những origin khác nhau:

- `https://app.example.test` và `https://portal.example.test`: khác host.
- `https://portal.example.test` và `http://portal.example.test`: khác scheme.
- `https://portal.example.test` và `https://portal.example.test:8443`: khác port.

Path, query và fragment không thuộc origin. So sánh origin bằng URL đã được parse và giá trị chuẩn hóa, không dùng `includes`, `endsWith` hoặc regex chỉ kiểm tra một phần hostname.

### Request đơn giản và preflight

Một request có thể được gửi mà không cần preflight nếu method, header và content type đáp ứng điều kiện CORS safelisted. Những trường hợp thường gặp là `GET`, `HEAD`, `POST` cùng một số header và content type như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`.

Browser thường gửi preflight khi request dùng method như `PATCH`, `PUT`, `DELETE`, custom header hoặc `Content-Type: application/json`. Preflight là request `OPTIONS` chứa:

- `Origin`: origin của trang gọi.
- `Access-Control-Request-Method`: method của request chính.
- `Access-Control-Request-Headers`: danh sách header mà request chính muốn gửi.

Server phản hồi bằng các header `Access-Control-Allow-*` phù hợp. Nếu preflight không thành công, browser không gửi request chính. Preflight không phải authentication và thường không mang cookie phiên; server không nên yêu cầu session cookie để trả lời một preflight hợp lệ.

## Xác định hợp đồng CORS

Trước khi viết cấu hình, lập bảng quyền cho từng endpoint. Không dùng một policy rộng cho mọi route nếu nhu cầu khác nhau.

| Endpoint | Origin được phép | Method | Request header | Credentials | Mục đích |
|---|---|---|---|---|---|
| `GET /api/public-info` | Không cần CORS hoặc origin đối tác cụ thể theo yêu cầu | `GET` | Không có header tùy chỉnh | Không | Dữ liệu công khai |
| `GET /api/account` | `https://portal.example.test` | `GET` | `X-Request-Id` nếu cần | Có | Đọc thông tin tài khoản theo session |
| `PATCH /api/account/email` | `https://portal.example.test` | `PATCH` | `Content-Type`, `X-CSRF-Token` | Có | Cập nhật email với CSRF token |
| `POST /api/account/email-form-test` | Không cấp quyền CORS | `POST` | Form URL-encoded | Session có thể được gửi trong same-site lab | Endpoint chỉ dùng để chứng minh CORS không thay thế CSRF |

Trong lab, chỉ `portal.example.test` được đọc API tài khoản. `evil.example.test` và `attacker.test` không được cấp quyền CORS. Không thêm origin vào allowlist chỉ vì nó là subdomain cùng site.

### Quyết định về credentials

Nếu API dùng cookie phiên, request cross-origin từ portal cần `credentials: "include"`. Server phải trả:

```http
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
```

Không dùng `Access-Control-Allow-Origin: *` cho response có credentials. Khi credentials được bật, origin phải là giá trị cụ thể được kiểm tra trong allowlist. `Access-Control-Allow-Credentials` chỉ có giá trị hợp lệ là `true`; không dùng `false` để biểu thị không cho phép.

Nếu API không cần cookie hoặc HTTP authentication, ưu tiên `credentials: "omit"` và không gửi `Access-Control-Allow-Credentials`. Càng ít endpoint cần credentials cross-origin thì phạm vi rủi ro càng nhỏ.

### Cookie trong bài lab

Cookie phiên của `app.example.test` nên là host-only và có các thuộc tính phù hợp, ví dụ:

```http
Set-Cookie: __Host-session=TEST_SESSION_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie `__Host-` cần `Secure`, `Path=/` và không có `Domain`. Nó không được chia sẻ cho `portal.example.test`; trình duyệt gửi cookie tới `app.example.test` khi portal gọi API nếu quy tắc cookie cho phép. Vì hai origin trong lab cùng site, `SameSite=Lax` có thể cho phép cookie trong request same-site. `fetch()` vẫn cần `credentials: "include"` vì đây là request cross-origin.

Nếu hai ứng dụng ở hai site khác nhau, cookie cross-site thường cần `SameSite=None; Secure`, nhưng chính sách chặn third-party cookie của trình duyệt vẫn có thể ngăn cookie được gửi. CORS thành công không đảm bảo cookie được gửi. Quan sát request thực tế trong Network và thiết kế tích hợp theo chính sách browser mà sản phẩm hỗ trợ.

## Cấu hình CORS phía server

Ví dụ dưới đây dùng Node.js và Express để minh họa middleware theo route. Điều chỉnh framework, route và policy theo ứng dụng của bạn. Đây là mẫu học tập, cần review cùng authentication, CSRF middleware, error handler và cấu hình proxy trước khi dùng production.

```js
const corsPolicies = new Map([
  ["/api/account", {
    origins: new Set(["https://portal.example.test"]),
    methods: new Set(["GET"]),
    headers: new Set(["x-request-id"]),
    credentials: true,
    exposedHeaders: new Set(["X-Request-Id"])
  }],
  ["/api/account/email", {
    origins: new Set(["https://portal.example.test"]),
    methods: new Set(["PATCH"]),
    headers: new Set(["content-type", "x-csrf-token"]),
    credentials: true,
    exposedHeaders: new Set(["X-Request-Id"])
  }]
]);

function corsPolicy(req, res, next) {
  const policy = corsPolicies.get(req.path);
  if (!policy) return next();

  // Phân biệt cả response không có Origin với response có Origin trong cache.
  res.vary("Origin");
  const origin = req.get("Origin");
  if (!origin) return next();

  if (req.method === "OPTIONS") {
    res.vary("Access-Control-Request-Method");
    res.vary("Access-Control-Request-Headers");

    const requestedMethod = (req.get("Access-Control-Request-Method") || "").toUpperCase();
    const requestedHeaders = (req.get("Access-Control-Request-Headers") || "")
      .split(",")
      .map((header) => header.trim().toLowerCase())
      .filter(Boolean);

    const originAllowed = policy.origins.has(origin);
    const methodAllowed = policy.methods.has(requestedMethod);
    const headersAllowed = requestedHeaders.every((header) => policy.headers.has(header));

    if (!originAllowed || !methodAllowed || !headersAllowed) {
      return res.sendStatus(403);
    }

    res.set("Access-Control-Allow-Origin", origin);
    if (policy.credentials) {
      res.set("Access-Control-Allow-Credentials", "true");
    }
    res.set("Access-Control-Allow-Methods", [...policy.methods].join(", "));
    if (requestedHeaders.length > 0) {
      res.set("Access-Control-Allow-Headers", requestedHeaders.join(", "));
    }
    res.set("Access-Control-Max-Age", "600");
    return res.sendStatus(204);
  }

  if (policy.origins.has(origin) && policy.methods.has(req.method)) {
    res.set("Access-Control-Allow-Origin", origin);
    if (policy.credentials) {
      res.set("Access-Control-Allow-Credentials", "true");
    }
    if (policy.exposedHeaders.size > 0) {
      res.set("Access-Control-Expose-Headers", [...policy.exposedHeaders].join(", "));
    }
  }

  next();
}

// Đăng ký CORS middleware trước authentication để preflight không cần cookie.
app.use(corsPolicy);
```

Các điểm cần hiểu trong ví dụ:

- Policy được khai báo theo route và chứa origin, method, header, credentials riêng.
- Origin được so sánh chính xác với allowlist. Không phản chiếu mọi giá trị `Origin`.
- Preflight chỉ được trả lời khi origin, method và toàn bộ request header được cho phép.
- `Vary: Origin` được đặt vì response CORS thay đổi theo origin. Preflight còn thay đổi theo method và request header.
- `Access-Control-Max-Age` giới hạn thời gian browser có thể cache kết quả preflight; giá trị thực tế có thể bị browser giới hạn.
- `Access-Control-Expose-Headers` chỉ cần khi JavaScript phải đọc response header ngoài danh sách safelisted.
- Middleware không cấp quyền truy cập dữ liệu và không thay thế CSRF. Request thực tế từ origin không được cho phép vẫn có thể tới route; server phải bảo vệ side effect độc lập.

Trong ứng dụng production, cần đảm bảo middleware CORS chạy trước middleware xác thực để xử lý preflight, nhưng authentication, authorization và CSRF vẫn phải chạy trên request chính. Đảm bảo error handler cũng trả CORS header cho origin hợp lệ khi response là `401`, `403` hoặc `500`, nếu frontend cần đọc mã lỗi. Không expose stack trace hoặc dữ liệu nội bộ chỉ để xử lý lỗi CORS.

### CSRF và authorization vẫn phải chạy

Endpoint `PATCH /api/account/email` cần kiểm tra session, CSRF token và quyền sửa tài khoản. Ví dụ thứ tự xử lý:

```js
app.patch(
  "/api/account/email",
  requireSession,
  requireCsrfTokenBoundToSession,
  requireAccountOwner,
  validateEmail,
  updateEmail
);
```

Các middleware trên là tên minh họa. `requireCsrfTokenBoundToSession` phải xác minh token hợp lệ và ràng buộc với phiên hiện tại; `requireAccountOwner` phải kiểm tra quyền ở server. Không tin `userId` hoặc role do frontend gửi lên. Nếu token thiếu/sai, từ chối trước khi cập nhật dữ liệu.

CORS chỉ quyết định browser có expose response cho script của portal hay không. Nó không ngăn form HTML từ site khác gửi một request đơn giản, cũng không ngăn curl hoặc client không phải trình duyệt. CSRF token, xác thực và phân quyền bảo vệ thao tác ở phía server.

Để kiểm tra khác biệt này, tạo một endpoint chỉ dùng trong lab là `POST /api/account/email-form-test`. Endpoint nhận form URL-encoded nhưng vẫn chạy `requireSession`, `requireCsrfTokenBoundToSession` và kiểm tra quyền trước khi cập nhật. Không thêm endpoint thử nghiệm này vào production. Từ `evil.example.test`, gửi form:

```html
<form action="https://app.example.test/api/account/email-form-test" method="POST">
  <input type="hidden" name="email" value="forged@example.test">
  <button type="submit">Gửi form thử nghiệm</button>
</form>
```

Đây là request cross-origin nhưng same-site giữa hai subdomain HTTPS. Cookie host-only của `app.example.test` có thể được gửi tới API theo quy tắc cookie; CORS không cần cho phép trang gửi form. Server phải từ chối vì form không có CSRF token hợp lệ và không được thay đổi email. Khi thử với `attacker.test` là site khác, cookie `SameSite=Lax` thường không được gửi trong form POST cross-site; vẫn giữ CSRF validation để bảo vệ các cấu hình cookie và luồng khác.

## Gọi API từ portal

Ví dụ đọc tài khoản bằng cookie phiên:

```js
async function loadAccount() {
  const response = await fetch("https://app.example.test/api/account", {
    method: "GET",
    mode: "cors",
    credentials: "include",
    headers: {
      "X-Request-Id": crypto.randomUUID()
    }
  });

  if (!response.ok) {
    throw new Error(`Account API failed: ${response.status}`);
  }

  return response.json();
}
```

Ví dụ cập nhật email bằng CSRF token đã được lấy qua luồng bootstrap tin cậy và ràng buộc với session:

```js
async function updateAccountEmail(email, csrfToken) {
  const response = await fetch("https://app.example.test/api/account/email", {
    method: "PATCH",
    mode: "cors",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify({ email })
  });

  if (!response.ok) {
    throw new Error(`Update failed: ${response.status}`);
  }

  return response.json();
}
```

Request `PATCH` với `application/json` và `X-CSRF-Token` cần preflight. Browser gửi `OPTIONS` trước; nếu preflight được chấp nhận, browser mới gửi `PATCH` thật. `credentials: "include"` cho phép gửi cookie phù hợp với quy tắc cookie và chính sách trình duyệt.

Không tự đặt header `Origin` trong JavaScript; đây là forbidden request header do browser quản lý. Không đặt token trong URL hoặc log. Nếu token được cấp cho portal, portal phải thuộc miền tin cậy tương ứng; XSS tại portal có thể sử dụng token mà portal đọc được, vì vậy cần bảo vệ cả hai ứng dụng.

## Kiểm thử bằng Chrome DevTools

### Kiểm tra request hợp lệ

1. Mở `https://app.example.test` và đăng nhập tài khoản lab.
2. Mở portal `https://portal.example.test` trong cùng browser profile.
3. Mở DevTools → Network, bật Preserve log.
4. Gọi `GET /api/account` từ portal.
5. Chọn request và kiểm tra Request Headers, Response Headers, cookie và response body.
6. Gọi `PATCH /api/account/email` và quan sát request `OPTIONS` cùng request `PATCH`.

Với preflight hợp lệ, kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`. Với request thật, kiểm tra response có origin cụ thể và credentials đúng policy. Xác nhận browser gửi cookie phiên phù hợp, CSRF token hợp lệ và dữ liệu thay đổi đúng một lần.

### Kiểm tra origin không được phép

Mở `https://evil.example.test` và gọi cùng API. Với origin không nằm trong allowlist, JavaScript không được đọc response. Đối với request cần preflight, browser phải dừng trước request chính nếu preflight không được chấp nhận.

Thử thêm một form HTML POST từ `evil.example.test` tới endpoint lab để chứng minh CORS không chặn mọi request cross-origin. Nếu request tới server, CSRF middleware phải từ chối thao tác và dữ liệu không được thay đổi. Dùng endpoint thử nghiệm an toàn và không tạo giao dịch thật.

### Kiểm tra response lỗi

Từ portal được phép, tạo một request thiếu session hoặc dùng CSRF token không hợp lệ. Frontend cần đọc được status/mã lỗi nếu CORS header được áp dụng cho response lỗi. Server không được trả stack trace, session ID hoặc token trong body.

Nếu Console chỉ hiện thông báo CORS chung, xem Network và log server để xác định request có được gửi hay không, response nào được trả và middleware nào đã xử lý. CORS error không phải lúc nào cũng chỉ ra nguyên nhân chính xác cho JavaScript.

## Kiểm thử bằng curl

`curl` hữu ích để kiểm tra response header của server và mô phỏng preflight. Nó không thực thi SOP/CORS như browser và có thể tự đặt header `Origin`; do đó, kết quả curl không thay thế browser test.

Mô phỏng preflight cho request cập nhật:

```bash
curl -i -X OPTIONS "https://app.example.test/api/account/email" \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Response mong đợi có status thành công cho preflight và các header allow phù hợp với policy. Không cần gửi cookie trong preflight.

Thử origin không được phép:

```bash
curl -i -X OPTIONS "https://app.example.test/api/account/email" \
  -H "Origin: https://evil.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Server không được cấp `Access-Control-Allow-Origin` cho origin này. Có thể trả `403` hoặc response không có các header CORS cần thiết; điều quan trọng là browser không chấp nhận preflight. Không coi status `403` là bắt buộc trong mọi thiết kế.

## Cache và response header

Nếu `Access-Control-Allow-Origin` thay đổi theo request origin, response cần `Vary: Origin` để cache không dùng nhầm response đã được tạo cho origin khác. Với preflight, response còn phụ thuộc `Access-Control-Request-Method` và `Access-Control-Request-Headers`, nên cần `Vary` tương ứng nếu cache preflight response.

Nếu API trả dữ liệu theo session hoặc credentials, cấu hình cache cẩn thận. Dùng `Cache-Control: private` hoặc `no-store` theo độ nhạy cảm và nhu cầu cache. `Vary: Origin` không thay thế kiểm soát cache theo người dùng/credentials.

Các header quan trọng:

| Header | Mục đích | Lưu ý |
|---|---|---|
| `Access-Control-Allow-Origin` | Origin được đọc response | Một origin cụ thể hoặc `*` chỉ trong trường hợp phù hợp không credentials |
| `Access-Control-Allow-Credentials` | Cho phép response credentialed | Giá trị phải là `true` |
| `Access-Control-Allow-Methods` | Method được phép trong CORS | Chỉ liệt kê method cần thiết |
| `Access-Control-Allow-Headers` | Request header được phép | Allowlist header cụ thể |
| `Access-Control-Expose-Headers` | Header response được JavaScript đọc | Chỉ expose trường cần thiết |
| `Access-Control-Max-Age` | Thời gian cache preflight | Browser có thể áp dụng giới hạn riêng |
| `Vary` | Khai báo chiều làm thay đổi response | Bao gồm `Origin`; preflight thêm method/header khi cần |

Đảm bảo header CORS có mặt trên response lỗi dành cho origin hợp lệ nếu client cần đọc lỗi. Kiểm tra CDN, reverse proxy và application server để tránh header bị ghi đè hoặc bị loại bỏ. Không trả nhiều giá trị `Access-Control-Allow-Origin` trong một response; browser yêu cầu một giá trị hợp lệ.

## Ma trận kiểm thử

Chạy cả trường hợp được phép và bị từ chối. Một cấu hình từ chối mọi request có thể “xanh” với test âm tính nhưng làm hỏng tích hợp hợp lệ.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| CORS-01 | Portal được phép gọi GET có credentials | Browser expose response; cookie hợp lệ được gửi |
| CORS-02 | Origin không được phép gọi GET | JavaScript không đọc được response |
| CORS-03 | Portal gửi PATCH với header đã allow | Preflight thành công, request chính được gửi |
| CORS-04 | Origin không được phép gửi PATCH | Preflight thất bại; browser không gửi request chính |
| CORS-05 | Method không nằm trong allowlist | Preflight bị từ chối |
| CORS-06 | Request header không nằm trong allowlist | Preflight bị từ chối |
| CORS-07 | Credentials dùng cùng `Access-Control-Allow-Origin: *` | Browser từ chối CORS response |
| CORS-08 | `Origin: null` | Không được cấp quyền nếu không có nhu cầu và policy riêng đã review |
| CORS-09 | Cookie bị chặn bởi SameSite/third-party policy | Quan sát cookie không được gửi; phân biệt với CORS failure |
| CORS-10 | Form POST cross-origin | Request có thể tới server; CSRF validation phải từ chối side effect |
| CORS-11 | API trả 401/403 cho origin được phép | Frontend đọc được status/mã lỗi mà không lộ chi tiết nội bộ |
| CORS-12 | Response thay đổi theo Origin | `Vary: Origin` có mặt; cache không trộn response giữa origin |
| CORS-13 | Request cùng origin | Không cần CORS để JavaScript đọc response |
| CORS-14 | Client gọi API trực tiếp bằng curl | Server vẫn yêu cầu authentication, authorization và CSRF phù hợp |

Với từng ca, lưu origin nguồn, endpoint, method, preflight, request thật, cookie có được gửi không, response header, status, quyết định server và trạng thái dữ liệu trước/sau. Che token và cookie trong ảnh chụp hoặc báo cáo.

## Lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Phản chiếu mọi `Origin` | Website bất kỳ có thể được cấp quyền đọc response | So sánh origin với allowlist chính xác |
| Dùng `*` cùng credentials | Browser không chấp nhận response credentialed | Trả origin cụ thể đã được phê duyệt |
| Allowlist bằng `endsWith` hoặc `includes` | Host giả mạo có thể vượt qua kiểm tra chuỗi | Parse URL và so sánh origin đầy đủ |
| Cho phép `null` tùy tiện | Opaque origin không đáng tin cậy có thể được cấp quyền | Từ chối mặc định; chỉ cho phép khi có thiết kế riêng |
| Cho phép mọi method/header | Mở rộng bề mặt API ngoài nhu cầu | Allowlist theo endpoint và chức năng |
| Yêu cầu cookie ở preflight | Browser không gửi preflight như request có credentials thông thường | Xử lý OPTIONS trước authentication và không trả dữ liệu nhạy cảm |
| Chỉ thêm header cho response 200 | Frontend không đọc được lỗi 401/403/500 | Áp dụng CORS middleware trước route/error handling |
| Quên `Vary: Origin` | Cache có thể phục vụ nhầm response theo origin | Thêm Vary phù hợp ở proxy và application |
| Nghĩ CORS chặn CSRF | Form hoặc request đơn giản vẫn có thể tới server | Dùng CSRF token, Origin/Fetch Metadata và authorization |
| Tin CORS là authentication | Client không phải browser có thể tự gửi request | Xác thực và phân quyền server-side trên mọi request |
| Bỏ qua cookie policy | Request được CORS cho phép nhưng thiếu session | Kiểm tra `credentials`, `SameSite`, `Secure` và third-party cookie policy |
| Cho phép origin staging trong production | Môi trường ít tin cậy có thể đọc dữ liệu production | Tách allowlist theo môi trường và kiểm tra deploy config |

## Checklist trước khi phát hành

- [ ] Mỗi endpoint có danh sách origin, method và request header cần thiết.
- [ ] Origin được parse/chuẩn hóa và so sánh chính xác; không phản chiếu tùy ý.
- [ ] `Access-Control-Allow-Origin` chỉ có một giá trị phù hợp.
- [ ] Credentials chỉ bật khi cần và không dùng wildcard origin.
- [ ] Preflight xử lý OPTIONS trước authentication, không yêu cầu cookie.
- [ ] Method/header được kiểm tra theo route.
- [ ] CORS header được áp dụng cho response lỗi cần thiết.
- [ ] `Vary: Origin` và các chiều preflight được cấu hình đúng.
- [ ] Cookie có thuộc tính phù hợp; đã kiểm tra browser gửi cookie thực tế.
- [ ] CSRF token, authentication và authorization vẫn được thực thi ở server.
- [ ] Test browser bao gồm origin hợp lệ, origin lạ, same-site khác origin và site khác.
- [ ] Test xác nhận trạng thái dữ liệu không đổi sau request giả mạo.
- [ ] Không có token, cookie hoặc dữ liệu cá nhân trong log/bằng chứng.
- [ ] Allowlist có chủ sở hữu, mục đích và quy trình review khi tích hợp thay đổi.

## Thực hành tổng hợp

Triển khai lab với ba origin: `app.example.test`, `portal.example.test` và `evil.example.test`. API tài khoản chỉ cho portal đọc và cập nhật thông tin theo session. Origin `evil.example.test` cùng site nhưng không được tin cậy.

Thực hiện các bước:

1. Tạo endpoint `GET /api/account` và `PATCH /api/account/email` với tài khoản giả lập.
2. Cấu hình cookie phiên host-only, `Secure`, `HttpOnly` và `SameSite=Lax` trên HTTPS.
3. Viết policy CORS theo route, allowlist đúng portal, chỉ cho method/header cần thiết và bật credentials cho hai endpoint cần session.
4. Xử lý preflight `OPTIONS` trước middleware xác thực; không trả dữ liệu tài khoản trong preflight.
5. Bảo vệ `PATCH` bằng CSRF token gắn với session, authentication và kiểm tra quyền phía server.
6. Gọi API từ portal bằng `fetch()` với `credentials: "include"`; xác nhận GET và PATCH hoạt động.
7. Gọi API từ `evil.example.test`; xác nhận browser không expose response và preflight không cho phép request PATCH.
8. Gửi form POST từ `evil.example.test` tới endpoint lab `POST /api/account/email-form-test`; xác nhận server không thực hiện thay đổi khi thiếu CSRF token dù cookie same-site có thể được gửi.
9. Kiểm tra response lỗi, `Vary`, redirect và cookie trong DevTools Network.
10. Chạy ma trận kiểm thử, ghi lại kết quả và khôi phục dữ liệu lab.

Sản phẩm bàn giao của bài thực hành gồm bảng hợp đồng CORS, cấu hình server, đoạn gọi API phía portal, ma trận test, ảnh/chụp header đã che dữ liệu nhạy cảm và báo cáo giải thích vì sao CORS không thay thế CSRF hoặc authorization.

## Ghi nhớ

- CORS cho phép JavaScript từ origin được chọn đọc response; nó không xác thực người dùng và không chặn mọi request cross-origin.
- Origin gồm scheme, host và port; same-site không đồng nghĩa same-origin.
- Request dùng method/header không safelisted thường cần preflight `OPTIONS`.
- Preflight không cần session cookie; xử lý OPTIONS trước authentication nhưng không cấp quyền truy cập dữ liệu.
- Credentials cần `credentials: "include"`, origin cụ thể và `Access-Control-Allow-Credentials: true`.
- Cookie vẫn chịu `SameSite`, `Secure` và chính sách third-party cookie của trình duyệt.
- Request không được CORS cho phép vẫn có thể tới server; CSRF token và authorization phải bảo vệ side effect.
- Dùng allowlist chính xác, `Vary: Origin`, kiểm thử browser thật và xác nhận trạng thái dữ liệu.
