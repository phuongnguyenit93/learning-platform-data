# Same-Origin Policy, origin và mục đích của CORS trong Spring Security WebFlux

## Mục tiêu và phạm vi bài học

Bài thuộc nhóm **Cấu hình CORS** trong module **Spring Security - reactive**. Trước khi thay đổi `CorsWebFilter` hay `ServerHttpSecurity.cors(...)`, cần hiểu **Same-Origin Policy (SOP)** là quy tắc do *trình duyệt* thực thi; **origin** được xác định bằng bộ ba scheme–host–port; còn **Cross-Origin Resource Sharing (CORS)** là cơ chế server thông báo cho trình duyệt khi nào JavaScript từ origin khác được đọc response.

Sau bài này, bạn có thể:

1. Xác định hai URL **same-origin** hay **cross-origin** dựa vào **scheme, hostname và port**, không nhầm với URL path, DNS alias hoặc khái niệm "same-site".
2. Mô tả điều SOP bảo vệ: JavaScript của một origin không được mặc nhiên đọc phản hồi nhạy cảm từ origin khác.
3. Giải thích vì sao **cross-origin request có thể đã được gửi** dù browser không cho JavaScript đọc body; CORS không phải firewall hay cơ chế xác thực.
4. Đọc chính xác `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age` và `Vary`.
5. Phân biệt request không cần preflight với request cần **OPTIONS preflight**; hiểu thứ tự xử lý trước Spring Security trong WebFlux.
6. Cấu hình allowlist origin đúng phạm vi `/api/**` bằng `CorsConfiguration`, `UrlBasedCorsConfigurationSource` và `ServerHttpSecurity.cors(...)`.
7. Dựng ví dụ **Java 17+, Spring Boot 3.3.13, WebFlux + Spring Security**, gọi backend từ frontend khác port và kiểm thử bằng `WebTestClient`.
8. Phân biệt **CORS, authentication, authorization, CSRF và SameSite cookie**; tránh dùng wildcard origin với cross-origin credentials.
9. Chẩn đoán lỗi trong browser Network/Console và hiểu giới hạn kiểm thử bằng curl.
10. Đánh giá cấu hình CORS cho phát triển, production, API có token, UI dùng cookie và reverse proxy.

**Tóm tắt một câu:** SOP là hàng rào đọc dữ liệu giữa các origin trong trình duyệt; CORS là một cơ chế **nới có chọn lọc hàng rào đó**, không thay thế bất kỳ bước bảo vệ API nào.

## 1. Origin là gì?

Origin của một URL thường là bộ ba:

```text
origin = (scheme, host, port)

URL:    https://api.example.test:8443/v1/orders?status=new
scheme: https
host:   api.example.test
port:   8443

origin: https://api.example.test:8443
```

- **Scheme**: `http` hay `https` phải khớp; khác scheme là cross-origin.
- **Host**: hostname phải khớp; `api.example.test` khác `www.example.test`, `localhost` khác `127.0.0.1`.
- **Port**: cổng phải khớp; `localhost:5173` khác `localhost:8080`.
- **Path** (`/v1/orders`), query (`?status=new`) và fragment (`#tab`) **không thuộc origin**.
- Với HTTP/HTTPS, cổng mặc định được chuẩn hóa: `https://app.example.test` tương ứng cổng 443, `http://app.example.test` tương ứng cổng 80.
- URL có thể có opaque origin, ví dụ một số trường hợp `file:`, `data:` hoặc sandboxed iframe. Khi đó header `Origin` có thể là `null`; đây **không phải** một hostname đáng tin để tự động cho phép.

### 1.1. Bảng so sánh URL

Giả sử mã JavaScript chạy tại `https://app.example.test:443/dashboard`.

| URL được JavaScript gọi | Same-origin? | Lý do |
| --- | --- | --- |
| `https://app.example.test/api/me` | **Có** | Scheme, host và port chuẩn hóa đều giống |
| `https://app.example.test:443/orders` | **Có** | Cổng 443 là mặc định của HTTPS |
| `https://app.example.test:8443/api/me` | Không | Port khác |
| `http://app.example.test/api/me` | Không | Scheme khác; còn có thể gặp mixed-content restrictions |
| `https://api.example.test/api/me` | Không | Subdomain/host khác |
| `https://APP.EXAMPLE.TEST/api/me` | Có | Hostname DNS so khớp không phân biệt hoa thường trong ngữ cảnh thông thường |
| `https://app.example.test/api/me?x=1` | **Có** | Query khác nhưng origin không đổi |
| `https://app.example.test/another/page#top` | **Có** | Path/fragment không quyết định origin |

**Ví dụ local** sẽ dùng xuyên suốt bài:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8080

=> Cross-origin do khác PORT, dù cùng tên host localhost.
```

Đây là nguyên nhân quen thuộc khiến frontend Vite/React/Vue gọi Spring Boot đang chạy trên cổng khác và trình duyệt hiện thông báo CORS.

### 1.2. Origin khác site

**Same-origin** kiểm tra *scheme + host + port*. **Same-site** (trong bối cảnh cookie hiện đại) liên quan đến site theo scheme và registrable domain (eTLD+1, với những ngoại lệ/đặc thù hostname), **không đồng nhất với origin**.

Ví dụ:

```text
https://app.example.com  -> https://api.example.com

Cross-origin: có, vì host khác.
Có thể same-site: có, vì scheme và registrable domain giống.
```

Vì vậy một request có thể **cross-origin nhưng same-site**. Chính sách `SameSite=Lax/Strict/None` của cookie là câu chuyện khác với quyền JavaScript đọc dữ liệu theo CORS.

Không tự suy rằng "hai subdomain cùng công ty" nghĩa trình duyệt cho phép chia sẻ response mặc định. Cũng không cho rằng cookie chỉ cần `SameSite=None` là JavaScript đã được phép đọc response: CORS vẫn phải hợp lệ khi request cross-origin.

## 2. Same-Origin Policy bảo vệ điều gì?

**Same-Origin Policy** là cơ chế cô lập của trình duyệt: đoạn JavaScript từ một origin không được mặc nhiên truy cập nội dung riêng tư do origin khác cung cấp.

Giả sử:

```text
Tab A: https://bank.example (user đã đăng nhập)
Tab B: https://malicious.example (mã JS do bên khác kiểm soát)

Tab B chạy:
fetch("https://bank.example/api/balance")
```

Nếu script của Tab B đọc được response có chứa dữ liệu ngân hàng mà không có ranh giới, việc mở một website lạ sẽ đủ để đánh cắp nhiều dữ liệu đã xác thực trên site khác. SOP buộc browser kiểm tra quyền **đọc response** khi nguồn thực hiện là một origin khác.

### SOP không có nghĩa "mọi cross-origin request bị cấm gửi"

Trình duyệt vẫn có nhiều hình thức request cross-origin:

- Người dùng đi theo link sang website khác.
- Tải ảnh bằng `<img src="https://other.example/image.png">`.
- Tải script bằng `<script src="...">` dưới các quy tắc tương ứng.
- Submit HTML form đến một URL khác.
- Gửi một số `fetch`/XHR cross-origin nhưng **không đưa body/headers response cho JavaScript** nếu CORS không hợp lệ.

Việc **request có thể đến server** nhưng **JavaScript không được đọc response** là điểm quan trọng nhất. Với một số request không cần preflight, server có thể đã thực hiện thao tác thay đổi trạng thái trước khi trình duyệt chặn quyền đọc phản hồi.

### Điều SOP/CORS không giải quyết

- Không thay thế authentication/authorization của backend.
- Không ngăn mọi request gửi bởi browser, đặc biệt simple form POST.
- Không chặn curl, Postman hoặc backend-to-backend client: chúng không áp dụng SOP như browser JavaScript.
- Không bảo vệ trước CSRF nếu API dùng cookie; phải có cơ chế CSRF/Origin/Fetch Metadata phù hợp.
- Không ngăn XSS trên **chính origin** được tin cậy. Nếu website `https://app.example.com` có XSS, code độc hại chạy trên một origin mà API đã allowlist.
- Không phải hệ thống phân quyền tài liệu/người dùng: `Access-Control-Allow-Origin` không có thông tin owner, role hay tenant.
- Không kiểm soát mọi giao thức: WebSocket handshake, navigation, iframe embedding, CSP và postMessage có quy tắc riêng.

**Nguyên tắc:** CORS quyết định "JavaScript từ nguồn web nào được xem response", không quyết định "người dùng nào được truy cập tài nguyên nào".

## 3. CORS hoạt động ở mức HTTP thế nào?

CORS (**Cross-Origin Resource Sharing**) là cơ chế chuẩn hóa việc browser và server thương lượng **quyền đọc response từ origin khác**, chủ yếu qua HTTP headers.

Browser gửi `Origin`:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
```

Server có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"public"}
```

Browser so `Origin` của trang gọi với `Access-Control-Allow-Origin` của response và các điều kiện liên quan. Khi khớp, JavaScript được phép truy cập response theo chính sách CORS.

**Cần phân biệt hai nhóm header:**

| Header | Ai gửi? | Tác dụng |
| --- | --- | --- |
| `Origin` | Browser trong request | Cho biết origin của môi trường phát sinh request |
| `Access-Control-Request-Method` | Browser, trong OPTIONS preflight | Xin phép HTTP method sẽ dùng |
| `Access-Control-Request-Headers` | Browser, trong OPTIONS preflight | Xin phép các request headers không safelisted sẽ dùng |
| `Access-Control-Allow-Origin` | Server response | Origin cụ thể hoặc `*` (theo điều kiện) được JavaScript đọc |
| `Access-Control-Allow-Methods` | Server, thường trong preflight | Method được cho phép với CORS |
| `Access-Control-Allow-Headers` | Server, thường trong preflight | Request headers được phép gửi trong actual request |
| `Access-Control-Allow-Credentials` | Server response | Cho phép browser **đưa response của credentialed request** cho JavaScript khi những điều kiện còn lại hợp lệ |
| `Access-Control-Expose-Headers` | Server response | Bổ sung các response headers JavaScript có thể đọc ngoài nhóm CORS-safelisted |
| `Access-Control-Max-Age` | Server, preflight response | Gợi ý browser cache kết quả preflight trong thời gian giới hạn |
| `Vary: Origin` | Server/proxy | Thông báo cho cache rằng response có thể khác theo origin |

Một response **không** được viết:

```http
Access-Control-Allow-Origin: https://site-a.test, https://site-b.test
```

để biểu thị danh sách origin. Header `Access-Control-Allow-Origin` có **một origin duy nhất** hoặc `*` khi hợp lệ. Server có thể cấu hình allowlist nhiều origin, nhưng response phải chọn và trả origin phù hợp với request, không nối danh sách thành một giá trị.

### 3.1. Vì sao cần Vary?

Nếu backend phản ánh **một origin được allowlist** vào `Access-Control-Allow-Origin`, hai request cùng URL từ hai origin hợp lệ có thể nhận response headers khác nhau. Một CDN/cache không xét `Origin` có thể cache sai phản hồi.

`Vary: Origin` thông báo cache rằng representation/headers phụ thuộc `Origin`. Với preflight, còn có thể cần `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers` theo implementation.

**CORS là policy ở từng request/response**, nên cache, ingress, reverse proxy hoặc API gateway có thể làm chính sách sai nếu tự chèn/xóa/ghi đè headers. Kiểm thử cả trước và sau proxy khi triển khai thật.

## 4. Simple request và preflight

### 4.1. Cross-origin request không cần preflight

Ví dụ GET chỉ sử dụng request headers safelisted:

```javascript
fetch("http://localhost:8080/api/public")
  .then(response => response.json())
  .then(data => console.log(data));
```

Nếu origin trang gọi là `http://localhost:5173` thì browser có thể gửi GET ngay. Server vẫn phải trả `Access-Control-Allow-Origin` hợp lệ để JavaScript đọc JSON. Nếu thiếu CORS header, **GET có thể đã đến server** và đã nhận HTTP 200, nhưng `fetch` bị browser báo lỗi CORS; JS không được đọc JSON.

Thuật ngữ “simple request” thường dùng cho những request **không cần preflight**. Các điều kiện safelisted gồm:

- Method thuộc `GET`, `HEAD` hoặc `POST`.
- Không có request headers ngoài danh sách CORS-safelisted (với các giới hạn/điều kiện giá trị).
- Với `Content-Type` do client đặt, chỉ một số media type safelisted như `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain` (còn các điều kiện cụ thể).
- Một số đặc thù như event listeners của `XMLHttpRequest.upload` hoặc stream upload có thể khiến request không còn loại đơn giản; đừng chỉ nhớ mỗi method.

**Không nên suy "POST luôn preflight"**: một form POST với content type safelisted có thể được browser gửi trực tiếp. Đó là lý do CORS không thể thay thế CSRF protection.

### 4.2. Request cần preflight

Ví dụ frontend gửi JSON POST hoặc request có `Authorization`:

```javascript
fetch("http://localhost:8080/api/private", {
  method: "GET",
  headers: {
    "Authorization": "Basic " + btoa("alice:learn")
  }
});
```

Header `Authorization` không thuộc nhóm CORS-safelisted, nên browser thường gửi **OPTIONS preflight** trước actual GET. Một request `POST` với `Content-Type: application/json` cũng thường cần preflight.

Preflight request minh họa:

```http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Response CORS thành công:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Demo-Trace
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Các chữ hoa/thường, thứ tự/dấu cách của header values và status thành công có thể khác theo server/browser. Đây là **ví dụ giao thức**, không phải kết quả byte-for-byte từ một phiên chạy thực tế.

Nếu preflight hợp lệ, browser **mới gửi actual request**:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Basic <base64-demo-credentials>
```

Preflight **không dùng để xác thực người dùng** và theo Fetch/CORS không mang credentials như cookie đăng nhập trong tình huống thông thường. Browser xác nhận trước "origin này có được dùng method/header này không?", không hỏi "user này có quyền xem /api/private không?".

### 4.3. Nếu preflight thất bại thì sao?

Browser không gửi actual request sau khi preflight không được cho phép. DevTools Network thường thấy OPTIONS bị chặn, thiếu `Access-Control-Allow-*` hoặc response 401/403/302 không phù hợp.

Nếu actual request đã được gửi mà actual response thiếu `Access-Control-Allow-Origin` hợp lệ, JavaScript có thể vẫn gặp “CORS error” mặc dù server đã hoàn thành xử lý. **Phải xem cả hai request** và phân biệt:

- `OPTIONS` preflight lỗi → actual request **không được gửi**.
- Không preflight, hoặc preflight thành công nhưng **actual** lỗi CORS → actual request **có thể đã tới server**.
- Actual response HTTP 401/403 với CORS headers hợp lệ → JavaScript có thể đọc status 401/403. Đây là lỗi authentication/authorization, **không phải** lỗi CORS.

### 4.4. Preflight cache

`Access-Control-Max-Age` cho phép browser cache kết quả preflight theo những yếu tố của request. Thời gian hiệu lực có thể bị browser giới hạn riêng, nên không xem 600 giây là đảm bảo tuyệt đối. Khi debug, một preflight có thể không xuất hiện ở mỗi lần bấm vì đã được cache.

Preflight cache **không phải HTTP cache của response nghiệp vụ**; nó chỉ cache quyết định CORS đối với method/headers/origin tương ứng. Thay `Access-Control-Max-Age` không làm token đăng nhập sống lâu hơn.

## 5. CORS khác authentication, authorization và CSRF

### 5.1. Một bảng ngắn

| Cơ chế | Câu hỏi nó trả lời | Thực thi chính |
| --- | --- | --- |
| **Same-Origin Policy** | JS từ origin này có được đọc dữ liệu ở origin khác mặc định không? | Trình duyệt |
| **CORS** | Server cho phép JS từ origin nào được đọc response với method/header/credentials nào? | Browser kiểm tra headers server trả |
| **Authentication** | Đây là ai, đã xác minh credentials/token chưa? | Backend/Spring Security |
| **Authorization** | Principal này được làm gì với resource nào? | Backend/Spring Security và service/domain |
| **CSRF protection** | Browser đang mang cookie có bị website khác lợi dụng gửi request thay đổi trạng thái không? | Server + token/Origin/Fetch Metadata/cookie policy |
| **Cookie SameSite** | Browser có gửi cookie trong bối cảnh cross-site này không? | Trình duyệt |
| **CSP (Content Security Policy)** | Trang được phép tải/chạy nội dung hoặc kết nối đi đâu? | Trình duyệt kiểm tra policy của trang |
| **TLS/HTTPS** | Dữ liệu có được bảo vệ trên đường truyền không? | Client–server transport |

### 5.2. CORS không chặn curl

`curl` không có cơ chế SOP như browser. Kẻ tấn công vẫn có thể:

```bash
curl -i -H 'Origin: https://evil.example' \
  http://localhost:8080/api/private
```

Thậm chí kẻ đó có thể **giả header Origin** trong một non-browser client. Vì vậy, **không lấy `Origin` làm bằng chứng người gọi đáng tin hay đã được cấp quyền**. Backend phải kiểm tra session/token/role/resource như bình thường.

Một `Access-Control-Allow-Origin` hợp lệ cũng không chứng minh request được ủy quyền. Với `/api/private`, Spring Security vẫn cần xác thực. Ngược lại, request từ browser bị CORS chặn có thể đã được backend xử lý dù người gọi không đọc được response.

### 5.3. CORS không thay thế CSRF

Một website lạ có thể gửi một số simple cross-origin POST hoặc form submission mang cookie theo điều kiện của browser. SOP có thể ngăn **đọc response**, nhưng **không đảo ngược side effect** đã xảy ra. Nếu API dùng cookie/session để định danh browser, server cần CSRF protection cho thao tác thay đổi trạng thái khi phù hợp, và cookie policy giúp giảm rủi ro.

Trong Spring Security WebFlux, `CsrfWebFilter` bảo vệ những request cần thiết theo cấu hình. **Không bật CORS để rồi tắt CSRF một cách máy móc.** Đối với API Bearer-only trong header, nguy cơ CSRF khác, nhưng phải đánh giá cơ chế gửi credentials (cookie, Basic, token tự động hay explicit), không dựa vào tên "REST".

### 5.4. Có CORS rồi vẫn có thể 401/403

Ví dụ frontend từ `http://localhost:5173` gọi `GET /api/private`. Backend trả:

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
WWW-Authenticate: Basic ...
```

Điều này là hợp lệ: CORS cho phép JavaScript **biết status 401**, không tự tạo Authentication. Nếu user được xác thực nhưng thiếu role, response có thể là 403. Browser phải được phép đọc response lỗi theo chính sách CORS nếu muốn xử lý status một cách rõ ràng trong frontend.

## 6. Credentialed requests: cookie, Authorization và wildcard

### 6.1. Fetch credentials mode

Trong `fetch()`, `credentials` kiểm soát khi nào browser gửi credentials do browser quản lý (đặc biệt là cookies và HTTP auth state) và xử lý `Set-Cookie`. Các giá trị phổ biến:

- `same-origin`: mặc định; tự động gửi credentials cho cùng origin, không tự gửi cross-origin cookies như `include`.
- `include`: cho phép gửi credentials cả cross-origin **nếu cookie policy, SameSite/Secure, browser privacy settings và những điều kiện khác cho phép**.
- `omit`: không dùng credentials do browser quản lý.

Ví dụ UI dùng session cookie qua origin khác:

```javascript
fetch("https://api.example.test/api/me", {
  credentials: "include"
});
```

Để JavaScript đọc response của request có credentials cross-origin, backend cần:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

**Không được dùng**:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

cho request cần credentials. Browser sẽ không đưa response cho JavaScript. Server phải trả **một origin cụ thể** được phép. Spring `CorsConfiguration` cũng không cho đặt `allowedOrigins("*")` cùng `allowCredentials(true)` theo cấu hình thông thường.

### 6.2. Authorization header tự đặt

Một frontend có thể chủ động đặt `Authorization: Bearer ...` hoặc Basic cho API. Header đó không safelisted nên thường gây preflight và phải nằm trong `allowedHeaders` của CORS.

```javascript
fetch("https://api.example.test/api/me", {
  headers: {
    "Authorization": "Bearer " + token
  },
  credentials: "omit"
});
```

Đây là cơ chế gửi token **tường minh**, không phải cookie tự động. Trình duyệt vẫn áp dụng CORS với request cross-origin và preflight cần cho Authorization header. `Access-Control-Allow-Credentials` đặc biệt liên quan đến **credentials mode include**; không thể dùng nó làm phép thử xem Bearer token hợp lệ hay chưa.

Token không nên nhúng trong source code frontend công khai, localStorage tùy tiện hoặc URL query; phải thiết kế lưu trữ/luồng OAuth2 phù hợp threat model. Đoạn code chỉ mô tả cơ chế HTTP.

### 6.3. SameSite cookie và third-party cookie

Ngay cả khi backend đã trả `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials: true`, browser vẫn có thể **không gửi cookie**, ví dụ:

- Cookie bị giới hạn `SameSite=Lax` hoặc `Strict` trong bối cảnh cross-site;
- Cookie cần `SameSite=None; Secure` để tham gia một số cross-site request qua HTTPS;
- Browser chặn third-party cookies theo chính sách riêng;
- Cookie sai `Domain`/`Path`, đã hết hạn, hoặc frontend/backend khác hostname/scheme;
- Request không dùng `credentials: "include"` dù backend mong cookie.

`SameSite=None; Secure` không phải lời khuyên bật trên mọi cookie: nó tăng vùng rủi ro cross-site và cần CSRF protection, HTTPS và đánh giá sản phẩm. Với hai subdomain có cùng site nhưng khác origin, CORS vẫn bắt buộc để browser JS đọc response, dù SameSite không nhất thiết chặn cookie.

### 6.4. Expose response headers

JavaScript không tự đọc được mọi response header cross-origin dù CORS cho phép body. Nếu server trả:

```http
X-Server-Variant: webflux-demo
Access-Control-Expose-Headers: X-Server-Variant
```

JS mới có thể đọc:

```javascript
const version = response.headers.get("X-Server-Variant");
```

Một số response headers thuộc nhóm CORS-safelisted được đọc mặc định, nhưng custom headers cần expose. **`Set-Cookie` không thể được expose cho JavaScript bằng `Access-Control-Expose-Headers`** vì nó là forbidden response-header name; browser có thể xử lý cookie nhưng JS không đọc trực tiếp nội dung header ấy.

## 7. CORS trong Spring WebFlux và Spring Security reactive

### 7.1. HandlerMapping, @CrossOrigin và CorsWebFilter

Spring WebFlux hỗ trợ CORS tại nhiều nơi:

1. `@CrossOrigin` trên annotated controller hoặc method.
2. Cấu hình `WebFluxConfigurer.addCorsMappings(...)` tại `HandlerMapping`.
3. `CorsWebFilter` xử lý CORS ở tầng filter.
4. `ServerHttpSecurity.cors(...)` tích hợp CORS filter vào **Spring Security WebFlux chain** ở vị trí thích hợp.

Với ứng dụng đã bật Spring Security, **preflight cần được xử lý trước bước authentication**. Nếu request `OPTIONS` không mang session cookie/Authorization và security đòi authenticated trước khi CORS chạy, preflight có thể nhận 401/redirect, khiến browser không gửi actual request.

Tài liệu Spring Security reactive hướng dẫn dùng `CorsWebFilter` hoặc CORS integration qua `CorsConfigurationSource`; `ServerHttpSecurity.CorsSpec.configurationSource(...)` đảm bảo filter được gắn theo thứ tự thích hợp trong security chain.

### 7.2. Một nguồn cấu hình, một nơi xử lý rõ ràng

Chọn một chiến lược:

- **Trong security chain:** `.cors(spec -> spec.configurationSource(source))`, dùng bean `UrlBasedCorsConfigurationSource`; đây là lựa chọn ví dụ chính.
- **Filter toàn cục:** bean `CorsWebFilter` được đặt thứ tự thích hợp trước Spring Security nếu cấu hình ứng dụng yêu cầu.
- **HandlerMapping-only:** `@CrossOrigin` hoặc `WebFluxConfigurer` có thể phù hợp những ứng dụng không có security preflight blocking, nhưng phải kiểm tra tích hợp với Spring Security.

**Không tự động khai báo cả `CorsWebFilter` toàn cục và `.cors(...)` dùng cùng chính sách** mà không hiểu thứ tự/response header duplication. Với nhiều `SecurityWebFilterChain`, CORS source/matcher phải áp dụng cho tất cả endpoints cần cross-origin; nếu preflight rơi vào chain không có CORS support, frontend vẫn lỗi.

### 7.3. Các loại cấu hình phải khớp API reactive

| Mục đích | WebFlux reactive | Servlet MVC |
| --- | --- | --- |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| CORS filter | `org.springframework.web.cors.reactive.CorsWebFilter` | `org.springframework.web.filter.CorsFilter` |
| CORS source | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` |
| Request context | `ServerWebExchange` | `HttpServletRequest` |
| CORS config object | `org.springframework.web.cors.CorsConfiguration` | `org.springframework.web.cors.CorsConfiguration` |

**Một lỗi import đặc biệt nguy hiểm:** Hai package có class tên `UrlBasedCorsConfigurationSource` nhưng khác kiểu. Với `ServerHttpSecurity.CorsSpec.configurationSource(...)`, phải dùng **reactive** `CorsConfigurationSource`. Nếu IDE tự import class Servlet, code có thể không compile hoặc dẫn tới cấu hình sai mô hình.

## 8. Ví dụ Java 17+ chạy được: backend 8080 và frontend 5173

Chúng ta tạo:

- Spring Boot WebFlux backend tại `http://localhost:8080`.
- Frontend HTML/JavaScript đơn giản tại `http://localhost:5173`.
- Chỉ cho phép CORS từ `http://localhost:5173`, trong phạm vi `/api/**`.
- Không cho phép gửi cookies cross-origin (`allowCredentials=false`) trong demo cơ bản.
- Cho phép `GET`/`POST`/`OPTIONS`, headers `Authorization`, `Content-Type` và `X-Demo-Trace`.
- `GET /api/public` công khai, `GET /api/private` yêu cầu HTTP Basic, `POST /api/changes` yêu cầu đăng nhập nhưng vẫn chịu CSRF mặc định.
- Test CORS *và* authorization/CSRF riêng, chứng minh CORS không phải security permission.

### 8.1. Cấu trúc dự án

```text
sop-cors-webflux/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/SopCorsApplication.java
    test/
      java/example/SopCorsApplicationTests.java
  client/
    index.html
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'sop-cors-webflux'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` của Servlet. Spring Boot BOM cung cấp phiên bản Spring Security, Reactor và Framework nhất quán với Boot 3.3.13. Bài này chọn phiên bản cố định để ví dụ dễ tái lập; sản phẩm thật phải cập nhật theo vòng đời hỗ trợ và cảnh báo bảo mật.

### 8.2. Backend: SopCorsApplication.java

Tạo `src/main/java/example/SopCorsApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SopCorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SopCorsApplication.class, args);
    }

    @GetMapping("/api/public")
    public ResponseEntity<Map<String, String>> publicData() {
        return ResponseEntity.ok()
                .header("X-Server-Variant", "webflux-demo")
                .body(Map.of("message", "PUBLIC_OK"));
    }

    @GetMapping("/api/private")
    public ResponseEntity<Map<String, String>> privateData() {
        return ResponseEntity.ok()
                .header("X-Server-Variant", "webflux-demo")
                .body(Map.of("message", "PRIVATE_OK"));
    }

    @PostMapping("/api/changes")
    public Map<String, String> changeData() {
        // Mục đích: làm rõ CSRF vẫn hoạt động.
        // Không thay đổi dữ liệu thật trong bài demo.
        return Map.of("message", "CHANGED");
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Chỉ tin đúng origin của frontend demo.
        config.setAllowedOrigins(List.of(
                "http://localhost:5173"));

        // CORS method không đồng nghĩa backend cấp quyền.
        config.setAllowedMethods(List.of(
                "GET", "POST", "OPTIONS"));

        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Demo-Trace"));

        config.setExposedHeaders(List.of(
                "X-Server-Variant"));

        // Demo dùng Authorization header, không dùng cookie
        // qua cross-origin fetch với credentials: include.
        config.setAllowCredentials(false);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                // Đặt CorsWebFilter vào đúng vị trí security chain.
                .cors(spec -> spec.configurationSource(corsSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/private")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.POST, "/api/changes")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Không disable CSRF cho POST /api/changes.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Giải thích thiết kế:**

1. `corsConfigurationSource()` xác định một allowlist origin **chính xác**. Không có `*` và không dùng `Origin` của request như một danh tính đáng tin.
2. `registerCorsConfiguration("/api/**", config)` chỉ áp dụng cấu hình CORS cho path API. Các endpoint khác không tự được mở cho frontend.
3. `.cors(spec -> spec.configurationSource(corsSource))` tích hợp CORS vào Spring Security WebFlux chain và xử lý preflight trước bước authorization cần người dùng. Không tạo `CorsWebFilter` toàn cục thứ hai.
4. `setAllowedHeaders(...)` phải có `Authorization` để preflight của fetch Basic/JWT được chấp nhận; `Content-Type` cho JSON POST.
5. `setExposedHeaders(...)` cho JS đọc header `X-Server-Variant` trong response cross-origin; không phải cấp quyền truy cập endpoint.
6. `setAllowCredentials(false)` minh họa API không dùng cookie từ browser ở khác origin; chỉ gửi Basic header tường minh trong demo. Đừng dùng `credentials: "include"` ở client rồi kỳ vọng server đáp ứng khi không bật credentialed CORS.
7. `/api/public` trả 200 khi không đăng nhập. `/api/private` vẫn phải có HTTP Basic hợp lệ, dù origin trong allowlist.
8. `POST /api/changes` tồn tại nhưng CSRF **vẫn bật**. Request POST có Basic credentials và CORS hợp lệ mà thiếu CSRF token vẫn có thể bị **403**. Điều này chứng minh CORS không cho phép bỏ qua CSRF.
9. `{noop}learn` chỉ là dữ liệu học tập cục bộ; ứng dụng thật dùng password encoder thích hợp, TLS/HTTPS và authentication mechanism phù hợp.
10. Đừng tự sửa controller bằng `@CrossOrigin("*")` sau khi đã cấu hình nguồn tập trung nếu chưa đánh giá việc gộp chính sách.

### 8.3. Frontend index.html

Tạo `client/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Same-Origin Policy và CORS demo</title>
</head>
<body>
  <h1>Frontend localhost:5173 → WebFlux localhost:8080</h1>
  <p>Ví dụ chỉ sử dụng tài khoản local demo.</p>

  <button id="public">GET công khai</button>
  <button id="private">GET có Basic Authorization</button>
  <button id="post">POST JSON (CSRF vẫn bật)</button>

  <pre id="output" aria-live="polite"></pre>

  <script>
    const base = "http://localhost:8080";
    const output = document.getElementById("output");

    async function run(path, options) {
      output.textContent = "Đang gọi " + path;
      try {
        const response = await fetch(base + path, options);
        const body = await response.text();
        const variant = response.headers.get("X-Server-Variant");

        output.textContent = JSON.stringify({
          status: response.status,
          ok: response.ok,
          variant: variant,
          body: body
        }, null, 2);
      } catch (error) {
        output.textContent =
            "Fetch thất bại; kiểm tra DevTools Network/Console: "
            + String(error);
      }
    }

    document.getElementById("public").onclick = () =>
      run("/api/public", { method: "GET" });

    document.getElementById("private").onclick = () =>
      run("/api/private", {
        method: "GET",
        headers: {
          "Authorization": "Basic " + btoa("alice:learn")
        }
      });

    document.getElementById("post").onclick = () =>
      run("/api/changes", {
        method: "POST",
        headers: {
          "Authorization": "Basic " + btoa("alice:learn"),
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ action: "demo" })
      });
  </script>
</body>
</html>
```

Không đưa username/password thật vào file JavaScript phát cho browser. `btoa("alice:learn")` chỉ chứng minh browser gửi `Authorization` từ frontend học tập, **không bảo vệ credentials**. Bản production nên dùng một cơ chế đăng nhập/token được thiết kế, không hardcode secret hoặc Basic password trong JS.

### 8.4. Chạy hai origin

Terminal 1, từ thư mục dự án:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun`.

Terminal 2: nếu có Python 3 trên máy, chạy:

```bash
python3 -m http.server 5173 --directory client
```

Trên Windows có Python Launcher, có thể chạy `py -m http.server 5173 --directory client`. Nếu không cài Python, có thể sử dụng development server tĩnh khác để phục vụ đúng `client/index.html` trên `http://localhost:5173`; đừng mở file bằng `file://` vì opaque origin có thể khác.

Mở browser tại `http://localhost:5173`, mở DevTools → Network → Preserve log. Lần lượt nhấn ba nút:

| Nút | Preflight? | Actual request kỳ vọng | Kết quả JavaScript |
| --- | --- | --- | --- |
| GET công khai | Không cần trong ví dụ | GET `/api/public` | Đọc được 200, `PUBLIC_OK`, `X-Server-Variant` |
| GET có Basic | Có, vì header `Authorization` | GET `/api/private` có Basic đúng | Đọc được 200, `PRIVATE_OK` |
| POST JSON | Có, vì JSON Content-Type và Authorization | POST `/api/changes` | Thường đọc được status **403** do CSRF, không phải CORS |

Nếu request actual nhận lỗi 401/403 **và có CORS headers hợp lệ**, JS vẫn truy cập được `response.status`. Trong Fetch API, HTTP 4xx/5xx **không tự reject Promise**; chúng thường tạo `Response` với `ok=false`. Promise chỉ bị reject cho network-level/CORS failure và những lỗi fetch khác. Đây là khác biệt rất quan trọng khi debug frontend.

**Giới hạn demo:** 403 của POST phụ thuộc Spring Security CSRF mặc định và việc gửi request thiếu token; ví dụ không cố tạo token rồi submit, vì bài học không dạy quy trình login/session CSRF đầy đủ.

## 9. Kiểm thử backend bằng WebTestClient

Tạo `src/test/java/example/SopCorsApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SopCorsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void allowedOriginCanReadPublicEndpoint() {
        client.get().uri("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().valueEquals(
                        "X-Server-Variant", "webflux-demo")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS)
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }

    @Test
    void preflightForAuthorizationHeaderWorksWithoutLogin() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void unlistedOriginPreflightIsRejected() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void allowedOriginStillNeedsAuthentication() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173");
    }

    @Test
    void validBasicCredentialsAllowPrivateResource() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PRIVATE_OK");
    }

    @Test
    void postCanPassCorsButFailCsrf() {
        client.post().uri("/api/changes")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameOriginStyleRequestWithoutOriginStillWorks() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }
}
```

Chạy:

```bash
gradle test
```

**Những gì test chứng minh:**

- Cấu hình cho phép origin `localhost:5173` truy cập GET public và preflight cho Authorization header.
- Preflight **không cần tài khoản đăng nhập**; nếu bị challenge 401, phải kiểm tra vị trí CORS filter.
- Một origin không nằm trong allowlist bị reject khi xin OPTIONS, không nhận `Access-Control-Allow-Origin`.
- `GET /api/private` vẫn cần HTTP Basic: CORS success **không** đồng nghĩa authorization success.
- `POST /api/changes` thiếu CSRF token vẫn 403; cấu hình CORS cho POST không vô hiệu CSRF.
- Request không có `Origin` có thể hoạt động bình thường như một request HTTP thông thường.

**Giới hạn của WebTestClient:** Nó không phải trình duyệt và không thực thi **Same-Origin Policy** trong JS. Nó chỉ gửi header và kiểm tra phản hồi backend. Vì vậy cần test thêm trong Chrome/Firefox với frontend thật để khẳng định trải nghiệm browser fetch và preflight.

## 10. Kiểm thử thủ công bằng curl: đọc đúng kết quả

### 10.1. Simple GET với Origin hợp lệ

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
```

Bạn kỳ vọng HTTP 200 và header:

```http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Server-Variant
```

### 10.2. Preflight OPTIONS

```bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/private
```

Kỳ vọng preflight được CORS filter xử lý, có `Access-Control-Allow-Origin` và `Access-Control-Allow-Methods`/`Headers`. **Không** thêm `Authorization` vào preflight; đây không phải actual request.

### 10.3. Origin không hợp lệ

```bash
curl -i -X OPTIONS \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/private
```

Cấu hình `CorsWebFilter` của demo sẽ từ chối preflight không hợp lệ, thông thường là 403. Trong trình duyệt, actual request không được gửi sau preflight bị từ chối. Khi thử bằng `curl`, chỉ thấy phản hồi server, **không chứng minh browser đã ngăn một script đọc body**.

### 10.4. CORS OK nhưng security vẫn yêu cầu auth

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private

curl -i -u alice:learn \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
```

Lệnh đầu kỳ vọng 401 Basic challenge, lệnh sau 200. Cả hai có thể có CORS headers cho phép frontend đã allowlist biết HTTP status, nhưng chỉ lệnh hai có credentials hợp lệ.

**Rất quan trọng:** `curl` có thể đặt `Origin` tùy ý và đọc response bất kể `Access-Control-Allow-Origin`. Không dùng việc curl đọc được response để kết luận CORS đã hoạt động trong browser. Hãy đối chiếu header, rồi thử browser thật.

### 10.5. Sai URL frontend

Nếu chạy server frontend bằng `http://127.0.0.1:5173` nhưng backend chỉ cho `http://localhost:5173`, thì **Origin khác** vì hostname khác; preflight có thể fail. Dùng đúng URL cho tất cả bài test. Port 5173 và 8080 khác nhau là chủ đích.

## 11. Ma trận chính sách CORS

| Trường hợp | CORS | Authentication / CSRF | Kết quả hợp lý |
| --- | --- | --- | --- |
| Public GET từ origin allowlist | Được phép | Không yêu cầu auth | JavaScript đọc được 200 |
| Public GET từ origin khác | Không cho browser đọc | Handler có thể vẫn chạy tùy loại request | CORS error trên browser; actual có thể tới server |
| Private GET từ origin allowlist, không credentials | Được phép về origin | Không authenticated | JS đọc được 401/challenge theo policy |
| Private GET từ origin allowlist, Basic hợp lệ | Preflight/actual CORS OK | Authenticated | JS đọc được 200 |
| JSON POST từ origin allowlist, thiếu CSRF | Preflight OK | CSRF từ chối | JS đọc được 403 nếu actual có headers CORS hợp lệ |
| Credentialed cookie request với ACAO `*` | Browser không cho đọc | Session backend có thể vẫn hoạt động | CORS failure; cấu hình sai |
| Credentials include với ACAO cụ thể + ACAC true | Browser cho phép response nếu cookie policy cũng cho phép | Backend vẫn phải xác thực/ủy quyền/CSRF | Tùy policy, không tự động 200 |
| curl với Origin bất kỳ | curl không thực thi SOP | Backend auth áp dụng | curl đọc response như client HTTP |
| Browser same-origin | Không cần cross-origin CORS negotiation | Auth/CSRF vẫn còn | Tùy policy backend |
| Browser request không hợp lệ ở preflight | OPTIONS bị từ chối | Actual chưa gửi | JS nhận CORS/network error |
| Browser GET được gửi nhưng actual thiếu ACAO | Actual có thể đã tới backend | Side effect (nếu có) không tự rollback | JS không được đọc response |

Không đoán status từ phía browser console một cách máy móc. Ví dụ, một CORS failure thường hiện là **network error** cho Fetch API, dù tab Network cho thấy HTTP 403 ở preflight hoặc 200 ở actual. Khi CORS hợp lệ mà backend trả 401, JS nhận `Response` có `status=401`; đây là tình huống khác.

## 12. Khi nào dùng allowedOrigins("*") và khi nào không?

### 12.1. Dữ liệu thật sự công khai và không credentials

Với public resource không nhạy cảm, phục vụ cho mọi website, `Access-Control-Allow-Origin: *` có thể là một lựa chọn hợp lệ khi request không dùng credentials mode include và server thực sự muốn cho mọi origin đọc response.

Ví dụ một API tra cứu thông tin công khai (không người dùng, không cookie/session, không thông tin nội bộ) có thể sử dụng wildcard sau khi đã đánh giá quota/abuse. **CORS wildcard không tự biến private API thành public**, nhưng nếu authentication yếu hoặc endpoint lộ dữ liệu thì việc cho mọi site đọc response làm tăng mức độ phơi bày.

### 12.2. API có cookie/session hoặc dữ liệu người dùng

Nếu cho phép credentials, **không dùng** `allowedOrigins("*")`. Chọn allowlist cụ thể:

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of(
        "https://app.example.test",
        "https://admin.example.test"));
config.setAllowCredentials(true);
```

Đây là **mảnh minh họa**, không phải cấu hình demo đầy đủ; nếu chạy cần import `CorsConfiguration`, `List` và đăng ký source/filter phù hợp.

Với credentials, việc phản ánh một origin đã đối chiếu từ allowlist là khác với **phản ánh vô điều kiện bất cứ Origin nào**:

```java
// RẤT NGUY HIỂM: mọi origin gửi lên đều thành allowed origin.
config.addAllowedOriginPattern("*");
config.setAllowCredentials(true);
```

`allowedOriginPatterns` có thể dùng khi thật sự cần các pattern được kiểm soát (ví dụ danh sách subdomain thuộc tổ chức) và Spring có logic phản ánh origin match. Nhưng pattern `*` kết hợp credentials trên thực tế mở mọi origin, có thể tạo rủi ro rất lớn khi API dựa trên session cookie. Đừng dùng nó như mẹo "sửa lỗi wildcard" mà không có threat model.

### 12.3. Kết hợp môi trường phát triển và production

Chỉ allowlist chính xác origin thật của từng môi trường:

```text
dev:     http://localhost:5173
staging: https://staging-app.example.test
prod:    https://app.example.test
```

Không để `http://localhost:5173` trong production nếu không cần, và không tự cấu hình `allowedOriginPatterns("https://*.example.test")` khi có subdomain do bên thứ ba điều khiển. Với API có credentials, **mọi origin trong allowlist là một phần trust boundary**, nên cần kiểm soát người có thể deploy JavaScript trên origin đó.

## 13. Vấn đề thường gặp trong Spring Security reactive

### 13.1. OPTIONS nhận 401 trước khi vào controller

**Triệu chứng:** DevTools có `OPTIONS /api/private` trả 401, frontend báo preflight fail.

**Nguyên nhân:** Security xử lý preflight như request unauthenticated, trước khi CORS được xử lý.

**Hướng sửa:** Dùng `CorsConfigurationSource` và tích hợp `.cors(spec -> spec.configurationSource(source))`, hoặc `CorsWebFilter` toàn cục đúng thứ tự. Không phải cứ `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` là đủ; browser vẫn yêu cầu **đúng CORS response headers** ở preflight.

### 13.2. GET public HTTP 200 nhưng browser báo CORS error

Response thực tế có thể thiếu `Access-Control-Allow-Origin` hoặc giá trị không khớp `Origin`. Kiểm tra cả response của **actual GET**; không chỉ preflight. CORS headers cần có trên error response nữa nếu frontend muốn xử lý status.

### 13.3. Browser báo "blocked by CORS" nhưng backend thấy request đã chạy

Không phải mâu thuẫn. Simple request có thể đã gửi; browser chỉ chặn JavaScript đọc response. Điều này đặc biệt quan trọng với POST có side effect: không dùng CORS như CSRF defense.

### 13.4. Chỉ cấu hình @CrossOrigin tại controller

Preflight có thể bị Spring Security chặn **trước** khi request tới HandlerMapping; `@CrossOrigin` không cứu được mọi cấu hình. Nên xác minh rằng CORS thực sự được tích hợp sớm và test OPTIONS không mang credentials.

### 13.5. Import nhầm package của CorsConfigurationSource

Với WebFlux:

```java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

**Không** import `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet khi dùng `ServerHttpSecurity.CorsSpec`.

### 13.6. Origin sai dù trông giống nhau

`http://localhost:5173`, `http://127.0.0.1:5173`, `https://localhost:5173` và `http://localhost:5174` là những origin khác nhau. Host, scheme và port phải khớp. Kiểm tra header `Origin` thực do browser gửi.

### 13.7. Bearer Authorization bị preflight từ chối

Header `Authorization` không được khai báo trong `allowedHeaders` hoặc method chưa nằm trong `allowedMethods`. Kiểm tra `Access-Control-Request-Headers: authorization` ở OPTIONS và response `Access-Control-Allow-Headers`.

### 13.8. CORS hợp lệ nhưng cookie không đi cùng request

Cần phân biệt `credentials: "include"`, cookie `SameSite`/`Secure`/`Domain`/`Path`, browser third-party cookie settings và policy của backend. Có `Access-Control-Allow-Credentials: true` không bắt buộc browser gửi cookie nếu cookie vốn không được phép gửi.

### 13.9. Browser phản hồi credentialed CORS không hợp lệ với wildcard

`Access-Control-Allow-Origin: *` không hợp lệ khi request dùng credentials mode include. Trả đúng origin sau allowlist check, kèm `Access-Control-Allow-Credentials: true`; đừng mở `allowedOriginPatterns("*")` để tránh lỗi mà mất trust boundary.

### 13.10. CORS xuất hiện hai lần

Tạo `CorsWebFilter` bean toàn cục đồng thời bật `ServerHttpSecurity.cors(...)` với nguồn khác có thể tạo headers lặp/khác policy hoặc lỗi khó debug. Chọn một chiến lược rõ ràng, kiểm tra thứ tự filters và test response actual/preflight.

### 13.11. Frontend dùng mode: no-cors để "sửa lỗi"

```javascript
fetch("http://localhost:8080/api/public", {
  mode: "no-cors"
});
```

Thường tạo **opaque response** mà JavaScript không đọc được status/body/headers như một normal CORS response. Đây không phải cách truy cập API JSON. Sửa server origin policy đúng yêu cầu thay vì tắt việc kiểm soát của trình duyệt.

### 13.12. Server trả redirect 302 cho preflight

Preflight có thể bị redirect về trang login và browser không tiếp tục actual request hoặc báo lỗi tùy trường hợp. Xử lý CORS **trước** authentication; nếu frontend là SPA gọi API, ưu tiên security chain có semantics 401 JSON/Bearer thay vì redirect HTML cho các requests API.

### 13.13. Reverse proxy/CDN tự thêm header bừa bãi

Ingress/nginx/gateway có thể:

- Thêm `Access-Control-Allow-Origin: *` lên mọi response;
- Ghi đè allowlist của Spring Boot;
- Bỏ `Vary: Origin` hoặc cache response dưới key sai;
- Không trả đúng CORS headers cho 401/403/5xx;
- Không chuyển OPTIONS tới backend hoặc tự trả preflight không nhất quán.

Hãy quyết định **một tầng quản lý CORS** (gateway hoặc ứng dụng) với contract và kiểm thử end-to-end, không cho hai nơi phản ánh origin độc lập mà không kiểm soát.

### 13.14. Origin null được cho phép thiếu suy xét

Request `Origin: null` có thể đến từ opaque origins như sandboxed iframes hoặc file URLs. Không treat `null` là "không có Origin". Nếu cần hỗ trợ ứng dụng đặc thù, dùng giải pháp xác thực/allowlist có threat model rõ ràng, không cho phép null chỉ vì frontend local mở bằng file.

### 13.15. Đường path CORS không khớp backend route

Cấu hình chỉ cho `/api/**`, nhưng request thực đi tới `/graphql`, `/oauth/token`, `/actuator/**` hoặc đường rewritten sau proxy. CORS source không match thì browser có thể không nhận headers mong muốn. Chỉ mở những endpoint cần cross-origin, và kiểm tra path mà WebFlux thực sự nhìn thấy sau reverse proxy.

### 13.16. CORS allowMethods nhưng route không tồn tại

Cho phép `POST` qua preflight không tự sinh `@PostMapping` hay cấp quyền. Backend có thể trả 404/405/403 sau khi actual request chạy. Kiểm tra riêng authorization, CSRF, routing và validation.

## 14. Tình huống thiết kế thực tế

### 14.1. SPA gọi API bằng Bearer JWT

```text
SPA: https://app.example.test
API: https://api.example.test
Auth: Authorization: Bearer <token>
```

Cần allowlist đúng origin SPA và cho phép header `Authorization`, method cần thiết. Preflight không mang Bearer token; resource server xác minh JWT ở **actual request**. Giữ CORS policy tách khỏi JWT issuer/audience/scope. Không nhầm CORS allowlist thành danh sách khách hàng được cấp token.

Nếu frontend không dùng browser-managed cookies, có thể không cần `Access-Control-Allow-Credentials: true`. Tuy nhiên cần đánh giá nơi giữ token và XSS; không lấy "Bearer-only" làm lý do bỏ mọi bảo vệ khác.

### 14.2. SPA dùng cookie session

```text
SPA: https://app.example.test
API: https://api.example.test
Session: Cookie
```

Yêu cầu có thể gồm:

- CORS allowlist origin SPA cụ thể;
- `Access-Control-Allow-Credentials: true`;
- `fetch(...,{credentials:"include"})` nếu browser phải gửi cookie qua origin khác;
- Cookie policy `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` phù hợp;
- CSRF token hoặc defense tương đương cho thao tác thay đổi trạng thái;
- Authorization theo user và resource;
- HTTPS và session fixation/logout/timeout theo policy.

Đây là thiết kế nhạy cảm hơn so với public GET. **Không sửa CORS mà quên CSRF hoặc cookie security.**

### 14.3. Backend-to-backend hoặc curl

Service gọi service qua `WebClient` không bị browser SOP; CORS không quyết định cho phép server-side HTTP client. Cần mTLS, OAuth client credentials, network policy hoặc authentication khác. Nếu một `WebClient` bị 401/403, sửa authentication/authorization, không tự bật CORS.

### 14.4. API public nhưng giới hạn tốc độ

`Access-Control-Allow-Origin: *` cho phép browser JS từ mọi origin đọc response public, nhưng **không giới hạn lượng gọi** và không thay thế quota/rate limiting/abuse detection. Phải áp dụng chính sách rate limit theo API key/user/IP đúng mô hình và chống enumeration/scraping.

### 14.5. Nhiều SecurityWebFilterChain

`WebFilterChainProxy` chọn chain đầu tiên khớp. Nếu API Bearer chain `/api/**` có CORS mà UI chain `/app/**` không có, một frontend cross-origin truy cập `/app/**` có thể gặp lỗi. Với mỗi chain, hãy kiểm tra:

1. `securityMatcher` có bao phủ URL actual và OPTIONS?
2. CORS được xử lý trước authentication?
3. `CorsConfigurationSource` có mapping path đúng?
4. Các rule `authorizeExchange` và HTTP entry point có trả status đúng cho API?
5. Không có chain precedence vô tình làm request rơi vào chain sai.

Không giả định một `@CrossOrigin` trên một controller sẽ sửa mọi chain security.

## 15. Cách debug có hệ thống bằng DevTools

### Bước 1: Xác nhận origin thực

Trong Console:

```javascript
console.log(window.location.origin);
```

Ghi lại chính xác scheme/host/port và so với `setAllowedOrigins(...)`. Đừng so sánh chỉ domain cha.

### Bước 2: Xem OPTIONS có tồn tại không

Trong Network, lọc `OPTIONS` và đường dẫn API. Nếu có preflight, xem:

```text
Request Headers:
  Origin
  Access-Control-Request-Method
  Access-Control-Request-Headers

Response Headers:
  Access-Control-Allow-Origin
  Access-Control-Allow-Methods
  Access-Control-Allow-Headers
  Access-Control-Allow-Credentials (khi cần)
  Access-Control-Max-Age
  Vary
```

Nếu OPTIONS bị 401/redirect, kiểm tra thứ tự CORS/security. Nếu bị 403 do Origin/method/header không được cho phép, điều chỉnh **đúng allowlist** chứ không mở wildcard tùy tiện.

### Bước 3: Xem actual response

Nếu OPTIONS hợp lệ, kiểm tra **GET/POST thật** đã gửi chưa, status là bao nhiêu và response có ACAO không. Nếu actual 401/403 mà headers CORS đúng, chuyển sang debug token/session/roles/CSRF, không còn là lỗi CORS ở nghĩa browser permission.

### Bước 4: Kiểm tra fetch credentials và cookie

Nếu backend dựa vào session, xem `credentials: "include"`, cookie policy, SameSite/Secure, host/path và Set-Cookie. Không chỉ nhìn `Access-Control-Allow-Credentials` mà kết luận cookie chắc chắn đã đi.

### Bước 5: Phân biệt browser với curl

Tái hiện OPTIONS bằng curl để xem backend config, nhưng **phải thử browser thật** để xác nhận SOP. Curl đọc response không chứng minh JavaScript có thể đọc được response.

### Bước 6: Xem proxy và cache

Nếu local đúng nhưng production sai, kiểm tra nginx/ingress/CDN, CORS headers bị nhân đôi, rewrite path và `Vary`. Tránh sửa đồng thời cả Spring Boot và gateway mà không biết nguồn phát CORS header.

### Bước 7: Kiểm tra các negative cases

- Origin không thuộc allowlist;
- Origin có port/scheme khác;
- Request header không được cho phép;
- Request method không được cho phép;
- Credentialed request với wildcard;
- Unauthorized user nhưng CORS hợp lệ;
- POST thiếu CSRF;
- API trả 500 có CORS/error handling đúng nếu frontend cần đọc lỗi.

**Các negative tests quan trọng ngang test thành công**, vì một CORS policy quá rộng có thể "chạy được" nhưng phơi dữ liệu tới origin không đáng tin.

## 16. Checklist trước khi triển khai

1. **Origin chính xác:** cấu hình scheme+host+port theo từng environment, không dùng hostname gần giống.
2. **Giới hạn path:** chỉ mở CORS cho endpoint cần thiết, ví dụ `/api/**`; không mặc định toàn bộ Actuator/admin endpoints.
3. **Allowed methods/headers:** chỉ cho các method/header thực cần; `Authorization` và `Content-Type` phải được liệt kê khi dùng tương ứng.
4. **Expose headers:** chỉ expose thông tin frontend cần; không thể expose `Set-Cookie` cho JS.
5. **Credentials:** `allowCredentials(true)` chỉ khi thực sự cần, tuyệt đối không dùng `allowedOrigins("*")` cùng credentials.
6. **Cookie/CSRF:** xem xét SameSite, Secure, HttpOnly, Origin/Fetch Metadata/CSRF token và HTTPS nếu session-based.
7. **Thứ tự filter:** preflight xử lý trước authentication, không bị 401/302 không cần thiết.
8. **Một nguồn policy:** tránh CORS headers mâu thuẫn giữa WebFlux, Spring Security và proxy.
9. **Authorization riêng:** CORS không thay permission/role/resource owner/tenant checks.
10. **Response lỗi:** 401/403/5xx có CORS headers đúng khi client được phép đọc; không lộ stack traces hay secrets.
11. **Cache:** bảo đảm `Vary: Origin` và preflight caching phù hợp; test dưới CDN.
12. **Non-browser clients:** curl/backend-to-backend vẫn phải được xác thực; không tin Origin do client giả.
13. **Observability:** theo dõi preflight success/deny, Origin không hợp lệ, authentication failure, CSRF failure và HTTP errors riêng.
14. **Cấu hình tối thiểu:** không dùng `@CrossOrigin("*")` hoặc `allowedOriginPatterns("*")` chỉ để xóa thông báo console.
15. **Browser tests:** kiểm tra frontend dev/prod trên browser thực, không dựa độc nhất WebTestClient.
16. **Nâng cấp:** kiểm tra API Spring Security WebFlux của phiên bản Boot đang dùng, đặc biệt package reactive CORS và multiple chains.

## 17. Câu hỏi tự kiểm tra

**1. `http://localhost:5173` và `http://localhost:8080` có same-origin không?**  
Không, vì port khác, dù cùng hostname.

**2. Thay `/api/a` bằng `/api/b` trên cùng server có đổi origin không?**  
Không. Path không thuộc bộ ba origin.

**3. SOP có cấm mọi request cross-origin được gửi không?**  
Không. Nhiều request vẫn được gửi; SOP/CORS chủ yếu hạn chế JavaScript đọc response cross-origin.

**4. CORS cho frontend đọc `/api/private` có đồng nghĩa người dùng được quyền xem dữ liệu không?**  
Không. Spring Security vẫn kiểm tra authentication/authorization; request có thể nhận 401/403.

**5. Khi nào xuất hiện OPTIONS preflight?**  
Khi request cross-origin không thuộc nhóm safelisted, ví dụ có header Authorization hoặc gửi JSON POST với `Content-Type: application/json`.

**6. Preflight có dùng session cookie hoặc Bearer token của request thật để chứng minh quyền không?**  
Theo chuẩn Fetch, CORS preflight không mang credentials; nó kiểm tra origin/method/headers trước, không thay authentication của actual request.

**7. Nếu browser chặn đọc response của một simple POST, server có thể đã thay đổi dữ liệu chưa?**  
Có thể đã. Vì vậy CORS không thay thế CSRF protection.

**8. CORS request có credentials mode include với `Access-Control-Allow-Origin: *` có hợp lệ không?**  
Không. Cần origin cụ thể được phép và `Access-Control-Allow-Credentials: true`.

**9. Vì sao `Vary: Origin` có giá trị với CDN?**  
Vì response headers có thể khác nhau theo Origin; cache thiếu Vary có thể tái sử dụng nhầm CORS policy.

**10. `Access-Control-Expose-Headers` có cho JS đọc `Set-Cookie` không?**  
Không. Set-Cookie là forbidden response-header name với Fetch.

**11. Bật `@CrossOrigin` trên controller có chắc preflight đi qua Spring Security đúng không?**  
Không. CORS phải được tích hợp/đặt trước authentication; cần test OPTIONS khi Spring Security bật.

**12. CORS error trong DevTools có luôn nghĩa server không nhận request không?**  
Không. Preflight fail thường làm actual không được gửi; nhưng simple/actual response thiếu headers có thể xảy ra sau khi backend đã xử lý.

**13. `Origin: null` có nghĩa request không có Origin?**  
Không. Đây có thể là opaque origin; không tự động allow.

**14. Có thể dùng `mode:"no-cors"` để đọc JSON API không?**  
Thông thường không. Response sẽ opaque, JavaScript không đọc body/status như một response CORS bình thường.

**15. Cookie SameSite có đồng nghĩa CORS allowlist không?**  
Không. SameSite liên quan gửi cookie theo site, CORS liên quan quyền đọc response của JavaScript theo origin.

**16. Dùng curl với Origin giả mà vẫn đọc response có chứng minh CORS sai không?**  
Không. Curl không thực thi SOP của browser; phải xem backend headers và browser behavior.

**17. Tại sao trong demo preflight OPTIONS thành công mà POST /api/changes có thể 403?**  
Vì CORS chỉ cho phép method/header về mặt cross-origin; Spring Security CSRF vẫn bảo vệ POST không có token.

**18. Nếu Access-Control-Allow-Origin đúng nhưng frontend vẫn không gửi cookie thì kiểm tra gì?**  
`fetch.credentials`, cookie SameSite/Secure/Domain/Path, third-party cookie policies và HTTPS; sau đó kiểm tra authentication/session server.

**19. Vì sao cấu hình WebFlux phải import `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`?**  
Vì `ServerHttpSecurity.CorsSpec` nhận nguồn CORS reactive; class Servlet có tên tương tự nhưng thuộc kiểu khác.

**20. Một API public có thể dùng `Access-Control-Allow-Origin: *` không?**  
Có thể khi thực sự là dữ liệu công khai, không dựa credentials và có chính sách rate limit phù hợp; không mặc định áp dụng cho dữ liệu riêng tư.

**Ghi nhớ:** SOP bảo vệ việc truy cập dữ liệu giữa các origin trong trình duyệt. CORS là sự đồng ý có giới hạn của server để browser cho phép JavaScript từ origin cụ thể **đọc response**, sử dụng origin, method, headers và credential mode. Với Spring Security WebFlux, cấu hình đúng `CorsConfigurationSource` và xử lý **preflight trước authentication**; giữ authentication, authorization và CSRF như những lớp riêng. Hãy dùng test browser + WebTestClient để xác nhận cả tình huống được phép và bị từ chối.

## Tài liệu tham khảo

- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): khái niệm origin, same-origin access, exception và opaque origins.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): CORS headers, preflight, credentialed requests, lỗi browser.
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): fetch, credentials mode, xử lý response và CORS errors.
- [WHATWG — Fetch Standard](https://fetch.spec.whatwg.org/): các thuật ngữ CORS protocol, preflight và credentials.
- [Spring Security — CORS for WebFlux](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS trước security, CorsWebFilter và CorsConfigurationSource.
- [Spring Security 6.3 — ServerHttpSecurity.CorsSpec](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): `configurationSource(...)` của DSL reactive và thứ tự tích hợp.
- [Spring Framework — CORS in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): @CrossOrigin, HandlerMapping, CorsWebFilter, credentials và global policy.
- [Spring Framework — CorsConfiguration API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowedOrigins, allowedOriginPatterns, allowedHeaders, maxAge, allowCredentials.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain, HTTP Basic và authorizeExchange.
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): sự khác biệt giữa CSRF và CORS trong ứng dụng dùng cookie.
