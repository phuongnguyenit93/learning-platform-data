# Credentialed CORS: chia sẻ response xuyên origin khi có thông tin xác thực

Một ứng dụng có thể đặt giao diện tại `https://app.example.com` và API tại `https://api.example.net`. Khi người dùng đăng nhập bằng cookie do API cấp, giao diện cần gọi API và đọc JSON trả về. Vì hai địa chỉ khác origin, trình duyệt áp dụng Same-Origin Policy (SOP) và chỉ cho JavaScript đọc response khi máy chủ API cho phép theo CORS.

Trường hợp này được gọi là **credentialed CORS**: một yêu cầu CORS được thực hiện với chế độ gửi thông tin xác thực, thường là cookie, và response chỉ được chia sẻ cho JavaScript khi máy chủ phản hồi đúng các header cho phép credentials. Cấu hình sai có thể khiến giao diện không đọc được dữ liệu, làm lộ dữ liệu cho origin không tin cậy hoặc mở thêm rủi ro CSRF.

Bài học thuộc chương **CORS nâng cao**, trong phạm vi `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`: phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web; hiểu SOP, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt CORS thông thường với credentialed CORS.
2. Giải thích thuộc tính credentials của Fetch API và withCredentials của XMLHttpRequest.
3. Cấu hình chính xác Access-Control-Allow-Origin và Access-Control-Allow-Credentials.
4. Phân tích preflight, phương thức/header được phép, response thực tế và cache preflight.
5. Hiểu ảnh hưởng của SameSite, Secure, HttpOnly và chính sách cookie bên thứ ba.
6. Thiết kế allowlist origin, tránh phản chiếu Origin tùy tiện và tránh cache sai response.
7. Phân biệt CORS với xác thực, phân quyền và CSRF protection.
8. Kiểm chứng bằng DevTools, request/response headers và trạng thái dữ liệu phía máy chủ.

## 2. Origin và credentials: hai câu hỏi độc lập

Với HTTP(S), origin được xác định bởi bộ ba **scheme + hostname + effective port**. Hai URL khác path nhưng có cùng scheme, hostname và port là cùng origin; thay scheme, hostname hoặc port sẽ tạo origin khác.

| Frontend | API | Quan hệ |
| --- | --- | --- |
| `https://app.example.com` | `https://app.example.com/api` | Same origin |
| `https://app.example.com` | `https://api.example.com` | Cross-origin, thường cùng site |
| `https://app.example.com` | `https://api.example.net` | Cross-origin, thường cross-site |
| `https://app.example.com` | `http://api.example.com` | Cross-origin và khác site theo schemeful SameSite |
| `https://app.example.com` | `https://api.example.com:8443` | Cross-origin do khác port |

**Credentials** là thông tin xác thực mà trình duyệt có thể đính kèm vào request, ví dụ cookie, TLS client certificate hoặc cơ chế HTTP authentication được trình duyệt quản lý. Trong ứng dụng web phổ biến, credentialed CORS thường nói đến cookie phiên.

Hai câu hỏi cần tách riêng:

- **Có gửi credentials không?** Phụ thuộc chế độ credentials của request, cookie scope, SameSite, Secure, trạng thái đăng nhập và chính sách riêng tư của trình duyệt.
- **JavaScript có đọc response không?** Phụ thuộc CORS response headers và các quy tắc của trình duyệt.

Một request có thể đã đến máy chủ và mang cookie nhưng JavaScript vẫn không được đọc response vì CORS không hợp lệ. Ngược lại, cấu hình CORS đúng không tự tạo cookie, đăng nhập người dùng hoặc cấp quyền truy cập tài nguyên.

## 3. Fetch API: same-origin, include và omit

Fetch API có thuộc tính `credentials` để xác định cách request sử dụng credentials:

| Giá trị | Hành vi |
| --- | --- |
| `same-origin` | Chỉ dùng credentials cho request cùng origin. Đây là mặc định của Fetch API. |
| `include` | Cho phép dùng credentials cả với request cross-origin, nếu cookie và chính sách trình duyệt cho phép. |
| `omit` | Không gửi credentials và không xử lý credentials theo cách thông thường cho request đó. |

Ví dụ frontend gọi API cùng origin:

```js
const response = await fetch('/api/profile');
const profile = await response.json();
```

Với `credentials: 'same-origin'` mặc định, cookie cùng origin có thể được gửi theo điều kiện cookie. CORS không cần thiết cho request này.

Ví dụ frontend gọi API khác origin và cần cookie phiên:

```js
const response = await fetch('https://api.example.net/profile', {
  method: 'GET',
  credentials: 'include'
});

if (!response.ok) {
  throw new Error('Không thể tải hồ sơ');
}

const profile = await response.json();
```

`include` yêu cầu Fetch sử dụng credentials cho request cross-origin, nhưng **không đảm bảo cookie sẽ được gửi**. Cookie còn phải phù hợp với host/domain, path, Secure, SameSite, thời hạn và chính sách cookie bên thứ ba của trình duyệt.

Nếu không cần cookie hoặc HTTP authentication xuyên origin, hãy giữ mặc định `same-origin` hoặc dùng `omit` theo yêu cầu. Không bật `include` cho mọi API chỉ để “sửa lỗi CORS”.

### XMLHttpRequest

Với XMLHttpRequest, thuộc tính tương ứng là `withCredentials`:

```js
const xhr = new XMLHttpRequest();
xhr.open('GET', 'https://api.example.net/profile');
xhr.withCredentials = true;
xhr.onload = () => {
  if (xhr.status >= 200 && xhr.status < 300) {
    console.log(xhr.responseText);
  }
};
xhr.send();
```

`withCredentials = true` yêu cầu sử dụng credentials cho request CORS. Máy chủ vẫn phải cấp quyền credentialed CORS; nếu response không đạt quy tắc, JavaScript không thể đọc nội dung.

## 4. Hai header cốt lõi của credentialed CORS

Giả sử frontend có origin `https://app.example.com` và API cho phép đúng frontend đó đọc response có credentials. API có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Ý nghĩa:

- `Access-Control-Allow-Origin` (ACAO) xác định origin được phép đọc response. Với credentialed CORS, phải trả **một origin cụ thể**, không dùng wildcard `*`.
- `Access-Control-Allow-Credentials` (ACAC) phải có giá trị chính xác là chữ thường `true` khi response được chia sẻ cho request có credentials. Không có giá trị `*`, `yes` hoặc `True` thay thế.
- `Vary: Origin` báo cho cache rằng response có thể thay đổi theo request header `Origin`, tránh dùng response đã cấp phép cho origin A để phục vụ nhầm origin B.

Origin trong ACAO là **origin**, không phải URL đầy đủ: không có path, query, fragment hoặc dấu `/` cuối. Scheme, hostname và port phải khớp với origin request.

### Vì sao ACAO wildcard không hợp lệ?

Response sau không hợp lệ để JavaScript đọc trong request credentialed:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Khi credentials mode là `include`, trình duyệt không chấp nhận wildcard ACAO. Máy chủ phải trả origin cụ thể đã được kiểm tra. Nếu frontend thực sự không cần credentials, có thể dùng wildcard cho tài nguyên công khai phù hợp; khi đó không nên bật credentials một cách không cần thiết.

### Không thể liệt kê nhiều origin trong một ACAO

Response kiểu:

```http
Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com
```

không phải cách hợp lệ để cho phép hai origin. Máy chủ chỉ trả **một giá trị ACAO** cho mỗi response. Nếu có allowlist nhiều origin, máy chủ xác minh `Origin` của request rồi chọn đúng một origin hợp lệ để phản hồi. Khi response thay đổi theo Origin, phải gửi `Vary: Origin`.

## 5. Preflight trong credentialed CORS

Một số request cross-origin cần trình duyệt gửi preflight `OPTIONS` trước request chính. Điều này thường xảy ra khi dùng method ngoài nhóm đơn giản, custom request header hoặc `Content-Type: application/json`.

Ví dụ:

```js
await fetch('https://api.example.net/orders/42', {
  method: 'PATCH',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken
  },
  body: JSON.stringify({ status: 'confirmed' })
});
```

Trình duyệt có thể gửi preflight:

```http
OPTIONS /orders/42 HTTP/1.1
Host: api.example.net
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-csrf-token
```

Preflight thông báo origin nguồn, method và header mà request thật dự định dùng. **Preflight request không mang credentials của request thật**; máy chủ không nên đòi cookie phiên để trả lời `OPTIONS` này. Sau khi preflight được chấp nhận, request thật mới được gửi theo cấu hình credentials và các chính sách cookie.

Response preflight minh họa:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Max-Age: 600
Vary: Origin
```

Ở request thật, response cần có các header CORS phù hợp, bao gồm:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Hãy bảo đảm các response lỗi cũng có header CORS phù hợp nếu frontend cần đọc thông tin lỗi. Nếu chỉ response 200 có ACAO/ACAC mà response 401/403/500 thiếu chúng, frontend thường chỉ thấy lỗi CORS chung thay vì đọc được status/body thực tế.

### Wildcard trong các header preflight và exposed headers

Với request credentialed, không dựa vào wildcard để thay thế danh sách rõ ràng:

- `Access-Control-Allow-Origin: *` không hợp lệ khi credentials mode là `include`.
- `Access-Control-Allow-Headers: *` không có ý nghĩa wildcard tổng quát trong credentialed request; hãy liệt kê header cần thiết.
- `Access-Control-Allow-Methods: *` cũng không thay thế danh sách method cụ thể trong credentialed request.
- `Access-Control-Expose-Headers: *` không có nghĩa là lộ mọi response header khi credentials được dùng; liệt kê tên header cần đọc.

Ví dụ rõ ràng:

```http
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
```

`Authorization` là request header cần khai báo tường minh trong `Access-Control-Allow-Headers` khi được dùng; không giả định wildcard sẽ bao gồm nó.

## 6. Cookie vẫn chịu chính sách riêng của trình duyệt

Credentialed CORS cho phép JavaScript đọc response theo CORS; nó **không bỏ qua cookie policy**. Cookie chỉ được gửi nếu đáp ứng các thuộc tính và chính sách liên quan.

Ví dụ cookie phiên:

```http
Set-Cookie: __Host-session=OPAQUE_SESSION; Path=/; Secure; HttpOnly; SameSite=None
```

Đây là ví dụ cookie cần dùng trong bối cảnh cross-site. `SameSite=None` phải đi cùng `Secure`; `HttpOnly` ngăn JavaScript đọc cookie trực tiếp; tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không có thuộc tính `Domain`. Tuy nhiên, ngay cả cookie hợp lệ theo thuộc tính này vẫn có thể bị trình duyệt chặn hoặc phân vùng theo chính sách third-party cookie.

### Phân biệt same-origin, same-site và cross-site

| Frontend và API | Same origin? | Same-site? | Lưu ý cookie |
| --- | --- | --- | --- |
| `https://app.example.com` và `https://app.example.com/api` | Có | Có | Request cùng origin, không cần CORS. |
| `https://app.example.com` và `https://api.example.com` | Không | Thường có | Cần CORS để JavaScript đọc response; cookie có thể là same-site tùy scope. |
| `https://app.example.com` và `https://api.example.net` | Không | Không | Cookie cross-site thường cần `SameSite=None; Secure`, nhưng chính sách bên thứ ba vẫn có thể chặn. |
| `http://app.example.com` và `https://api.example.com` | Không | Không theo schemeful SameSite | Cần xem cả scheme và cookie attributes. |

Một API ở subdomain khác thường là cross-origin nhưng same-site. Vì vậy, `SameSite=Lax` không phải cơ chế ngăn tất cả request từ subdomain khác. Nếu một subdomain bị chiếm quyền hoặc có mức độ tin cậy thấp, cookie same-site có thể vẫn được gửi theo một số luồng.

### Third-party cookie restrictions và partitioning

Trình duyệt hiện đại có thể chặn, giới hạn hoặc phân vùng cookie trong ngữ cảnh bên thứ ba. Hành vi phụ thuộc trình duyệt, cài đặt quyền riêng tư, chế độ duyệt web, chính sách doanh nghiệp và các API đặc biệt được hỗ trợ.

Do đó:

- `credentials: 'include'` không ép trình duyệt gửi cookie đã bị chính sách riêng tư chặn.
- CORS thành công không chứng minh cookie đã được gửi; hãy kiểm tra request headers/cookie trong Network.
- Cookie `SameSite=None; Secure` là điều kiện cần trong nhiều trường hợp cross-site, nhưng không đảm bảo cookie bên thứ ba luôn được chấp nhận.
- Storage partitioning có thể khiến dữ liệu lưu trữ trong iframe bên thứ ba khác với dữ liệu khi mở cùng site ở tab cấp cao.
- Nếu sản phẩm phụ thuộc đăng nhập bên thứ ba, hãy đánh giá top-level redirect, luồng đăng nhập có chuyển hướng, hoặc cơ chế được trình duyệt/nhà cung cấp hỗ trợ.

Không mở rộng cookie `Domain` hoặc bỏ `SameSite` một cách tùy tiện để làm tích hợp hoạt động. Hãy xác định chính xác frontend, API, site và yêu cầu cookie.

## 7. CORS không phải authentication, authorization hay CSRF protection

Đây là điểm bảo mật quan trọng nhất của credentialed CORS:

- **CORS** quyết định JavaScript ở origin nào được đọc response.
- **Authentication** xác định người dùng hoặc client là ai.
- **Authorization** xác định danh tính đó được phép làm gì trên tài nguyên nào.
- **CSRF protection** xác minh request thay đổi trạng thái được gửi trong ngữ cảnh hợp lệ và có ý định được xác nhận.

Một request có thể được máy chủ thực hiện nhưng response bị trình duyệt chặn khỏi JavaScript vì thiếu CORS headers. Vì vậy, CORS không đảm bảo server không xử lý request.

Ví dụ, một trang độc hại có thể gửi form hoặc một request đơn giản đến API ngân hàng. Nếu trình duyệt gửi cookie phiên và endpoint không kiểm tra CSRF, thao tác có thể xảy ra dù trang độc hại không đọc được response. Điều này giải thích vì sao **CORS không thể thay thế CSRF token**.

### Bảo vệ endpoint thay đổi trạng thái

Với endpoint `PATCH /orders/42`, máy chủ nên:

1. Xác thực session hoặc token theo kiến trúc.
2. Kiểm tra người dùng có quyền thay đổi đúng đơn hàng 42.
3. Kiểm tra CSRF token được gắn với phiên/ngữ cảnh hợp lệ khi dùng cookie tự động gửi.
4. Kiểm tra `Origin` và/hoặc Fetch Metadata như một lớp bổ sung, với chính sách rõ cho header vắng mặt.
5. Validate method, content type, dữ liệu và trạng thái nghiệp vụ.
6. Chỉ thay đổi dữ liệu sau khi mọi kiểm tra thành công.

Ví dụ client gửi token:

```js
await fetch('https://api.example.net/orders/42', {
  method: 'PATCH',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken
  },
  body: JSON.stringify({ status: 'confirmed' })
});
```

Máy chủ phải thực sự xác minh `X-CSRF-Token`. Việc custom header gây preflight có thể làm giảm một số request cross-origin từ browser nếu preflight không được cho phép, nhưng không nên coi đó là lớp bảo vệ CSRF duy nhất. Các endpoint có thể bị gọi bằng form hoặc các cơ chế khác, và lỗi cấu hình CORS có thể mở lại đường đi.

`GET` không được thay đổi trạng thái nghiệp vụ. Không tạo endpoint như `GET /transfer?to=...` hoặc `GET /delete?id=...`, vì top-level navigation và form có thể kích hoạt những request đó mà không cần JavaScript đọc response.

## 8. Thiết kế allowlist origin an toàn

Máy chủ thường cần cho phép một số frontend cụ thể. Không nên phản chiếu bất kỳ giá trị `Origin` nào mà client gửi lên.

### Ví dụ triển khai phía server

Pseudo-code:

```js
const allowedOrigins = new Set([
  'https://app.example.com',
  'https://admin.example.com'
]);

function applyCors(request, response) {
  const origin = request.headers.origin;

  if (origin && allowedOrigins.has(origin)) {
    response.setHeader('Access-Control-Allow-Origin', origin);
    response.setHeader('Access-Control-Allow-Credentials', 'true');
    response.setHeader('Vary', 'Origin');
  }
}
```

Đây là logic minh họa; framework thực tế có thể quản lý nhiều header `Vary` và response headers theo cách riêng. Nếu response đã có `Vary: Accept-Encoding`, hãy **bổ sung** `Origin` vào danh sách `Vary`, không ghi đè làm mất giá trị cũ.

### Những cách kiểm tra origin không an toàn

| Kiểu kiểm tra | Vấn đề |
| --- | --- |
| Phản chiếu `Origin` bất kỳ vào ACAO | Mọi website có thể được cấp quyền đọc response credentialed nếu ACAC cũng bật. |
| Kiểm tra `origin.includes('example.com')` | Có thể chấp nhận `https://example.com.attacker.net`. |
| Kiểm tra `origin.endsWith('example.com')` | Có thể chấp nhận hostname giả có suffix đánh lừa nếu không kiểm tra dấu phân cách hostname. |
| Chỉ so hostname, bỏ qua scheme/port | Có thể cho phép HTTP hoặc port ngoài dự kiến. |
| Chấp nhận `Origin: null` tùy tiện | Các tài liệu opaque origin như sandboxed iframe hoặc `data:` có thể gửi origin null. |
| Dùng regex quá rộng | Có thể chấp nhận subdomain không đáng tin hoặc chuỗi hostname ngoài ý muốn. |

Hãy parse origin theo chuẩn và so sánh với danh sách cấu hình chính xác. Allowlist nên được quản trị như cấu hình bảo mật, có review khi thêm origin mới và không lấy trực tiếp từ dữ liệu người dùng.

### Trường hợp Origin null

Một số ngữ cảnh như sandboxed iframe không có `allow-same-origin`, `data:` URL hoặc tài liệu opaque origin có thể gửi `Origin: null`. Không cho phép `null` chỉ để một tích hợp iframe hoạt động. Nếu cần hỗ trợ một luồng đặc biệt, hãy xác định rõ threat model, xác minh thông điệp/nguồn theo cách phù hợp và không cấp quyền đọc dữ liệu nhạy cảm cho mọi opaque origin.

## 9. Cache và Vary: Origin

Giả sử API phản hồi động:

- Request từ `https://app.example.com` nhận `Access-Control-Allow-Origin: https://app.example.com`.
- Request từ `https://admin.example.com` nhận `Access-Control-Allow-Origin: https://admin.example.com`.

Nếu CDN hoặc shared cache không biết response phụ thuộc vào header `Origin`, nó có thể phục vụ response đã tạo cho origin A sang request của origin B. Điều này có thể gây lỗi CORS hoặc tạo rủi ro chia sẻ response không đúng ngữ cảnh.

Đặt:

```http
Vary: Origin
```

khi ACAO được chọn động dựa trên Origin. Cache cần tính `Origin` vào cache key theo quy tắc `Vary`. Nếu response mang dữ liệu riêng tư theo người dùng, cần chính sách cache phù hợp như `Cache-Control: private` hoặc `no-store`, tùy nhu cầu; `Vary: Origin` **không thay thế** cache control theo danh tính.

Không cache response credentialed của nhiều người dùng chung một cache key chỉ vì origin giống nhau. Cookie/session và nội dung response có thể khác nhau giữa người dùng cùng origin.

## 10. Các header CORS thường gặp

| Header | Do ai gửi? | Vai trò |
| --- | --- | --- |
| `Origin` | Trình duyệt | Nêu origin nguồn của request khi quy tắc request yêu cầu. |
| `Access-Control-Allow-Origin` | Server | Chỉ định origin được phép đọc response. |
| `Access-Control-Allow-Credentials` | Server | Cho phép chia sẻ response khi request dùng credentials; giá trị phải là `true`. |
| `Access-Control-Allow-Methods` | Server | Liệt kê method được phép cho request CORS/preflight. |
| `Access-Control-Allow-Headers` | Server | Liệt kê request headers mà client được phép gửi. |
| `Access-Control-Expose-Headers` | Server | Cho phép JavaScript đọc thêm response headers ngoài danh sách safelisted. |
| `Access-Control-Max-Age` | Server | Đề xuất thời gian cache kết quả preflight theo giới hạn trình duyệt. |
| `Access-Control-Request-Method` | Trình duyệt | Method mà request thật dự định dùng, trong preflight. |
| `Access-Control-Request-Headers` | Trình duyệt | Các request headers mà request thật dự định gửi, trong preflight. |

Ví dụ response đầy đủ hơn cho API credentialed:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
Vary: Origin
```

Không cần expose mọi response header. Chỉ expose những header mà frontend thực sự cần đọc. Một số header như `Set-Cookie` không thể được expose cho JavaScript qua `Access-Control-Expose-Headers`; `Set-Cookie` là forbidden response-header name. Trình duyệt xử lý cookie theo chính sách riêng.

## 11. Thực hành: credentialed CORS với hai origin cục bộ

Mục tiêu là quan sát riêng:

1. Request cross-origin có credentials hay không.
2. Preflight có được chấp nhận không.
3. JavaScript có đọc response không.
4. Cookie có thực sự được gửi không.
5. Request có tác dụng phụ ở server dù response bị CORS chặn hay không.

Thực hành chỉ dùng môi trường local do người học kiểm soát, dữ liệu giả và cookie thử nghiệm.

### 11.1. Sơ đồ môi trường

```text
Frontend: http://localhost:3000
API:      http://localhost:4000
```

Hai origin khác nhau vì khác port. Trong production, ưu tiên HTTPS và cookie `Secure`; localhost có quy tắc đặc biệt cho một số secure context, nên thí nghiệm HTTP chỉ dùng để học CORS, không mô phỏng đầy đủ cấu hình cookie production.

### 11.2. Frontend gọi API

```js
async function loadProfile() {
  const response = await fetch('http://localhost:4000/profile', {
    method: 'GET',
    credentials: 'include'
  });

  if (!response.ok) {
    throw new Error('API status: ' + response.status);
  }

  return response.json();
}

loadProfile()
  .then((profile) => console.log(profile))
  .catch((error) => console.error(error));
```

Không thêm `mode: 'no-cors'` để “sửa” lỗi. `no-cors` trả opaque response mà JavaScript không đọc được body, status và headers theo cách thông thường.

### 11.3. API response mong đợi

Với request từ `http://localhost:3000`, API có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Vary: Origin
Set-Cookie: demo-session=opaque-value; Path=/; HttpOnly; SameSite=Lax
```

Cookie trên là cookie thử nghiệm. `SameSite=Lax` thường cho phép request same-site; localhost hai port khác origin nhưng cùng site trong ngữ cảnh này. Để mô phỏng cross-site production cần hai hostname/site khác nhau và HTTPS, đồng thời phải tính đến third-party cookie restrictions.

### 11.4. Thử preflight

Thử request PATCH:

```js
await fetch('http://localhost:4000/profile', {
  method: 'PATCH',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': 'demo-token'
  },
  body: JSON.stringify({ displayName: 'Demo' })
});
```

Trong Network, quan sát request `OPTIONS` trước. API phải phản hồi cho phép origin, method `PATCH`, và các header `Content-Type`, `X-CSRF-Token`. Preflight không mang cookie phiên; request PATCH thực tế mới có thể mang cookie theo điều kiện credentials/cookie policy.

### 11.5. Thử các cấu hình lỗi có chủ đích

Chỉ thay đổi cấu hình trên API local:

| Cấu hình thử | Kết quả mong đợi |
| --- | --- |
| ACAO là `*`, ACAC là `true` | Trình duyệt từ chối chia sẻ response credentialed. |
| ACAO không khớp origin frontend | JavaScript không đọc được response. |
| Thiếu ACAC `true` | Response credentialed không được chia sẻ cho JavaScript. |
| Preflight không cho phép `PATCH` | Request PATCH thật không được gửi theo luồng preflight đó. |
| Preflight không cho phép `X-CSRF-Token` | Request thật bị chặn trước khi gửi theo luồng preflight đó. |
| Request GET đơn giản, response thiếu CORS | Request có thể đã đến API; JavaScript không đọc được response. |
| Origin không nằm trong allowlist | API không cấp ACAO cho origin đó. |

Khi thử lỗi CORS, kiểm tra cả **Network và server log**. Một lỗi CORS ở Console chỉ cho biết JavaScript không được đọc response; nó không tự chứng minh request chưa tới server hoặc không làm thay đổi dữ liệu.

## 12. Checklist production

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Origin allowlist | Origin được parse và so khớp chính xác? | Chỉ origin được phê duyệt được phản hồi ACAO. |
| Credentials | API có thật sự cần cookie cross-origin? | Chỉ bật `include`/`withCredentials` ở request cần thiết. |
| ACAO | Response credentialed có origin cụ thể? | Không dùng `*`, không trả nhiều origin trong một header. |
| ACAC | Response có giá trị chính xác `true` khi cần? | Header hiện diện ở response thật và các response liên quan. |
| Preflight | OPTIONS được xử lý đúng method/header? | Không phụ thuộc cookie phiên để trả preflight; request thật vẫn xác thực. |
| Cookie | Cookie có `Secure`, `HttpOnly`, `SameSite` và scope phù hợp? | Cookie được gửi đúng bối cảnh, không mở rộng Domain vô cớ. |
| Third-party policy | Trình duyệt có chặn/phân vùng cookie không? | Kiểm thử các trình duyệt và chế độ quyền riêng tư mục tiêu. |
| CSRF | Endpoint thay đổi dữ liệu có token/Origin/Fetch Metadata phù hợp? | Không dựa vào CORS như lớp chống CSRF duy nhất. |
| Authorization | API kiểm tra quyền trên từng tài nguyên? | CORS không quyết định người dùng được xem/sửa dữ liệu nào. |
| Cache | Response thay đổi theo Origin có `Vary: Origin`? | Không dùng chung cache sai ngữ cảnh; dữ liệu riêng tư có cache policy riêng. |
| Error responses | 401/403/4xx/5xx có header cần thiết? | Frontend có thể đọc lỗi hợp lệ; không che lỗi thành CORS chung. |
| Logging | Origin, cookie và token có bị ghi thừa? | Không log cookie/token; redaction ở gateway, app và APM. |

## 13. Câu hỏi tự kiểm tra

1. Vì sao `credentials: 'include'` không bảo đảm cookie sẽ được gửi trong mọi request cross-origin?
2. Tại sao response có `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` không hợp lệ?
3. Origin trong `Access-Control-Allow-Origin` phải khớp những thành phần nào? Có được thêm path hoặc dấu `/` cuối không?
4. Vì sao preflight không mang cookie phiên nhưng request thật vẫn có thể mang cookie?
5. Khi allowlist có nhiều origin, tại sao server chỉ trả một ACAO và cần `Vary: Origin`?
6. CORS cho phép frontend đọc response có đồng nghĩa API đã xác thực và phân quyền người dùng không?
7. Nếu GET đơn giản đã tới server nhưng response bị CORS chặn, dữ liệu có thể đã thay đổi không? Làm sao kiểm chứng?
8. Hai subdomain khác origin nhưng cùng site có thể ảnh hưởng `SameSite` và CSRF như thế nào?
9. Tại sao `Access-Control-Allow-Headers: *` không nên được dùng thay danh sách rõ ràng trong credentialed CORS?
10. Khi trình duyệt chặn third-party cookie, những phương án kiến trúc nào có thể thay thế việc cố nới lỏng cookie?

**Tiêu chí hoàn thành:** người học có thể thiết kế một luồng credentialed CORS với origin allowlist rõ ràng, cookie phù hợp, preflight chính xác và cache an toàn; đồng thời chứng minh rằng CORS chỉ kiểm soát việc chia sẻ response, còn xác thực, phân quyền và chống CSRF phải được thực hiện độc lập ở máy chủ.
