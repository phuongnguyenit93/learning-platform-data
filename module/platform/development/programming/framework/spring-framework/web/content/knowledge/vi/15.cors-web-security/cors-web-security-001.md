# Spring MVC — Same-origin policy, origin và điều kiện phát sinh CORS

## 1. Mục tiêu và câu hỏi cốt lõi

Giả sử ứng dụng frontend chạy ở `http://localhost:5500` và backend Spring MVC chạy ở `http://localhost:8080`. Khi browser thực thi:

~~~javascript
const response = await fetch("http://localhost:8080/api/info");
const data = await response.json();
console.log(data);
~~~

hai URL có **cùng host `localhost` nhưng khác cổng**, vì vậy chúng có **khác origin**. Browser áp dụng chính sách cùng nguồn gốc (same-origin policy, SOP). Muốn frontend JavaScript đọc được kết quả từ backend, server cần trả phản hồi CORS phù hợp. Ngược lại, nếu HTML/frontend cũng được phục vụ từ `http://localhost:8080`, lời gọi tới `/api/info` là same-origin và không cần cấp quyền CORS riêng.

Sau bài học, bạn có thể:

- Định nghĩa chính xác **origin = scheme + hostname + port hiệu lực** và phân biệt same-origin, cross-origin, same-site và cross-site.
- Giải thích SOP bảo vệ **đọc/khả năng tương tác** với tài nguyên từ origin khác, chứ không phải tường lửa chặn mọi yêu cầu mạng hay mọi nhúng tài nguyên.
- Xác định **khi nào browser dùng cơ chế CORS**, khi nào request cross-origin cần **preflight OPTIONS**, và khi nào không cần preflight nhưng response vẫn phải được browser cho phép đọc.
- Hiểu `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age` và `Vary: Origin`.
- Phân biệt CORS với authentication, authorization, CSRF, cookie SameSite, CSP và server-to-server HTTP requests.
- Cấu hình Spring MVC bằng `WebMvcConfigurer#addCorsMappings` hoặc `@CrossOrigin`, tích hợp Spring Security theo đúng filter order.
- Chạy ứng dụng Java 17 / Spring Boot 3.5.0 và kiểm thử CORS bằng MockMvc, browser DevTools và curl.

**Phạm vi:** trình duyệt web hiện đại, Spring Framework 6.2 / Spring MVC (Servlet stack). CORS là chính sách được **trình duyệt thực thi** theo Fetch Standard; bản thân server vẫn có thể nhận một HTTP request ngay cả khi script bị từ chối quyền đọc response.

## 2. Origin thực chất là gì?

Trong bối cảnh HTTP(S), origin thường được biểu diễn bằng bộ ba:

~~~text
origin = (scheme, host, port)
~~~

Ví dụ:

~~~text
https://app.example.com:443
  │           │            │
scheme       host         effective port
~~~

Nếu không viết cổng, browser dùng cổng mặc định của scheme: HTTP thường là 80, HTTPS là 443. Vì vậy `https://app.example.com` và `https://app.example.com:443` có cùng origin.

**Path, query và fragment không nằm trong origin.** Hai URL này cùng origin:

~~~text
https://shop.example.com/products?page=1
https://shop.example.com/account#settings
~~~

Nhưng chỉ một trong ba thành phần scheme, host hoặc port khác là đủ tạo cross-origin.

### 2.1. Bảng so sánh origin

Chọn origin của trang nguồn: `https://shop.example.com`.

| URL đích | Same-origin? | Lý do |
| --- | --- | --- |
| `https://shop.example.com/products` | Có | Scheme, host, port giống nhau; path không quan trọng |
| `https://shop.example.com:443/api` | Có | 443 là cổng HTTPS mặc định |
| `https://shop.example.com?q=java` | Có | Query không đổi origin |
| `http://shop.example.com/api` | Không | Khác scheme: HTTP thay vì HTTPS |
| `https://api.example.com/data` | Không | Khác hostname/subdomain |
| `https://shop.example.com:8443/api` | Không | Khác port |
| `https://example.com/api` | Không | Host gốc khác `shop.example.com` |
| `https://shop.example.com.evil.test/api` | Không | Đây là host khác hoàn toàn |

Với môi trường development:

| Trang nguồn | API đích | Kết luận |
| --- | --- | --- |
| `http://localhost:3000` | `http://localhost:8080` | Cross-origin: khác port |
| `http://localhost:8080` | `http://localhost:8080/api` | Same-origin |
| `http://localhost:8080` | `http://127.0.0.1:8080` | Cross-origin: hostname khác |
| `https://localhost:8080` | `http://localhost:8080` | Cross-origin: scheme khác |

Lưu ý hostnames DNS trỏ tới cùng IP **không** khiến chúng tự trở thành cùng origin. SOP dựa vào origin của URL, không dựa trên IP đích sau DNS resolution.

### 2.2. Same-origin khác same-site

Hai thuật ngữ này thường bị nhầm:

- **Origin** thường xét `scheme + host + port`.
- **Site** hiện đại thường là **scheme + registrable domain** (schemeful same-site); cổng không phải tiêu chí phân biệt site. Registrable domain dựa trên quy tắc public suffix; với `localhost` có xử lý đặc thù trình duyệt.

Ví dụ `https://app.example.com` và `https://api.example.com` **cross-origin** (host khác) nhưng thường **same-site** (cùng scheme và registrable domain `example.com`). `http://localhost:5500` và `http://localhost:8080` cũng cross-origin do khác port nhưng thường được coi là same-site trong môi trường local.

**Hệ quả:** cấu hình cookie `SameSite` không tự xử lý bài toán CORS. Cookie SameSite kiểm soát gửi cookie theo quan hệ site; SOP/CORS kiểm soát quyền đọc response giữa origins. Một request có thể **cross-origin nhưng same-site**.

### 2.3. Opaque origin, file và Origin: null

Không phải mọi tài liệu có origin dạng HTTP(S) rõ ràng. Một số tài liệu sandboxed, `data:`, hoặc `file:` có thể có **opaque origin**. Khi chuyển thành chuỗi trong request `Origin`, browser có thể dùng:

~~~http
Origin: null
~~~

Đừng hiểu `null` là một domain tin cậy, cũng đừng whitelist nó chỉ để làm thử nghiệm local. Những tài liệu không tin cậy khác nhau cũng có thể biểu diễn origin thành `null`.

**Thực hành tốt:** chạy frontend development qua một HTTP server như `http://localhost:5500` thay vì mở file HTML trực tiếp bằng `file:///...`; khi đó origin và request dễ kiểm thử hơn.

`document.domain` từng được sử dụng để nới tương tác giữa subdomains, nhưng cơ chế đó đã bị loại bỏ/không được khuyến nghị; không dùng như một cách chữa lỗi CORS trong ứng dụng hiện đại.

## 3. Same-origin policy hạn chế điều gì?

SOP là cơ chế cô lập các nội dung từ những nguồn khác nhau. Ví dụ, người dùng đăng nhập webmail `https://mail.example.com`; một website bất kỳ `https://attacker.test` không được tự đọc thư, token hay nội dung API private của webmail chỉ bằng cách chạy JavaScript `fetch()`.

### 3.1. Đọc, gửi và nhúng là ba hành vi khác nhau

| Hoạt động | Mặc định theo SOP/browser | Ví dụ |
| --- | --- | --- |
| Script từ origin A đọc response JSON/HTML của origin B bằng `fetch`/XHR | Bị giới hạn, trừ khi server B cấp quyền CORS phù hợp | `fetch("https://api.example.com/private")` |
| Điều hướng browser sang một site khác | Thường được phép | Click link, `window.location` |
| HTML form gửi POST cross-origin | Nhiều trường hợp được phép gửi | `<form action="https://other.test/pay" method="post">` |
| Nhúng ảnh/audio/video cross-origin | Thường được phép hiển thị theo loại resource/chính sách khác | `<img src="https://cdn.test/p.png">` |
| Nhúng script truyền thống từ origin khác | Thường được phép tải/chạy theo loại script và CSP | `<script src="https://cdn.test/lib.js">` |
| Module script cross-origin hoặc JS đọc pixels canvas từ ảnh cross-origin | Có thể yêu cầu CORS hoặc bị taint | `<script type="module">`, `canvas.toDataURL()` |
| Truy cập DOM của một iframe cross-origin | Bị hạn chế chặt | Parent script đọc DOM từ `iframe` khác origin |
| Truy cập `localStorage`/IndexedDB của origin B từ origin A | Bị cô lập theo origin | `localStorage.getItem(...)` ở site khác |

Do đó, câu “SOP chặn mọi cross-origin request” là **sai**. Một số request **được gửi** nhưng JavaScript **không được đọc response** nếu CORS không cho phép.

Một `<img>` cross-origin có thể hiển thị được, nhưng khi vẽ ảnh đó lên canvas, browser có thể đánh dấu canvas là “tainted” và chặn đọc pixels trừ khi resource đáp ứng chính sách CORS.

### 3.2. Vì sao CSRF vẫn tồn tại?

Vì cross-origin form submissions hoặc các request nhất định vẫn có thể gửi, một website độc hại có thể cố gây ra thay đổi trên site khác nếu browser gửi cookie đăng nhập tương ứng. **CORS không tự chống CSRF** và không phải nơi duy nhất chặn request tạo thay đổi trạng thái.

Backend vẫn cần các biện pháp như:

- CSRF tokens thích hợp cho cookie/session-based authentication.
- Cookie `SameSite`, `Secure` và `HttpOnly` phù hợp.
- Kiểm tra `Origin`/`Referer` trong những tình huống cần thiết, theo chính sách xác định.
- Authentication, authorization, idempotency và kiểm tra nghiệp vụ.
- Không thực hiện thao tác thay đổi trạng thái chỉ bằng GET.

CORS là **quy tắc chia sẻ quyền truy cập response cho trình duyệt**, không phải hệ thống phân quyền của server.

## 4. Khi nào một request trở thành CORS request?

Trong bài này, tập trung vào một JavaScript `fetch()` từ origin của tài liệu A tới URL B:

1. Nếu A và B **same-origin**, không cần CORS để script đọc response.
2. Nếu A và B **cross-origin**, browser thực hiện các kiểm tra theo Fetch/CORS; server B cần opt-in với các HTTP response headers phù hợp để JS đọc response.
3. Tùy HTTP method, headers và Content-Type, browser có thể gửi **preflight OPTIONS** trước request chính.
4. Request có thể được gửi thành công nhưng **response vẫn bị browser chặn** nếu headers không hợp lệ.

Ví dụ frontend ở `http://localhost:5500`:

~~~javascript
// Cross-origin vì backend chạy ở port 8080.
const result = await fetch("http://localhost:8080/api/info");
console.log(await result.json());
~~~

Request thường mang header:

~~~http
GET /api/info HTTP/1.1
Origin: http://localhost:5500
Accept: */*
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: http://localhost:5500
Vary: Origin

{"service":"cors-demo","status":"ok"}
~~~

Nếu chính sách hợp lệ, browser cho JS truy cập JSON. Nếu không có `Access-Control-Allow-Origin` tương thích, browser chặn JavaScript đọc kết quả dù Network tab có thể ghi nhận HTTP 200.

**Origin header do user agent tạo trong CORS flow.** Một request server-to-server hoặc `curl` có thể gửi/không gửi header Origin và vẫn nhận HTTP response vì không có browser enforcement. Vì vậy không coi `Origin` là bằng chứng xác thực người gọi.

### 4.1. CORS không nhất thiết tạo một HTTP request mới

Hai khái niệm độc lập:

- **CORS actual request:** request chính như GET/POST/PUT/... tới API.
- **CORS preflight request:** OPTIONS gửi **trước actual request** để hỏi server có cho phép method/headers dự định hay không.

Một cross-origin GET thông thường **không có preflight**, nhưng actual response vẫn phải có ACAO phù hợp. Một POST JSON cross-origin thường cần preflight trước khi gửi JSON body.

## 5. Những điều kiện tạo preflight OPTIONS

Preflight không phát sinh chỉ vì “frontend và backend khác cổng”. Nó phụ thuộc tổ hợp method, request headers và một số điều kiện khác của Fetch. Cách học phổ biến là so với tập **CORS-safelisted**.

### 5.1. Những request thường không cần preflight

Một request cross-origin có thể không cần preflight khi đồng thời đáp ứng các điều kiện tương ứng, ví dụ:

- Method là `GET`, `HEAD` hoặc `POST`.
- Request headers do script tự đặt chỉ thuộc nhóm CORS-safelisted (như `Accept`, `Accept-Language`, `Content-Language`, và một số trường hợp `Content-Type`, `Range`), với giới hạn hợp lệ của giá trị/header.
- Nếu có `Content-Type` do script đặt, essence media type phù hợp trong ba loại: `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`.
- Không có các yếu tố bổ sung buộc preflight theo Fetch (một số streaming/upload cases và nền tảng browser có chính sách bổ sung).

Ví dụ:

~~~javascript
// Cross-origin GET thường không preflight,
// nhưng vẫn cần Access-Control-Allow-Origin để JS đọc body.
fetch("http://localhost:8080/api/info");
~~~

Một POST form-urlencoded cũng có thể không preflight:

~~~javascript
fetch("http://localhost:8080/api/form", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: "name=Lan"
});
~~~

**Không có preflight không có nghĩa backend đã cấp quyền.** Browser vẫn kiểm tra actual CORS response, và request POST có thể đã đến server trước khi browser chặn JS đọc response.

### 5.2. Những request thường cần preflight

| Yêu cầu script tạo | Preflight thông thường? | Nguyên nhân |
| --- | --- | --- |
| GET không custom headers | Không | Safelisted method/headers |
| POST `Content-Type: application/x-www-form-urlencoded` | Không | Safelisted content type |
| POST `Content-Type: text/plain` | Không | Safelisted content type |
| POST `Content-Type: application/json` | **Có** | `application/json` không thuộc safelisted Content-Type |
| PUT/DELETE/PATCH | **Có** | Method ngoài GET/HEAD/POST |
| GET thêm `Authorization: Bearer ...` | **Có** | Authorization không phải safelisted header |
| GET thêm `X-Request-ID`, `X-Tenant-ID` hoặc `X-API-Key` | **Có** | Custom request headers |
| POST có header `Content-Type: application/json` và credentials | **Có** | JSON content type đã đủ yêu cầu preflight |

Một client thêm header tùy chỉnh chỉ để “debug” có thể vô tình tạo preflight cho request trước đó không cần. Nhưng không nên bỏ authentication headers cần thiết chỉ để tránh OPTIONS; phải cấu hình CORS/authorization đúng.

### 5.3. Luồng preflight thực tế cho JSON POST

Frontend:

~~~javascript
const res = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Xin chào" })
});
console.log(await res.json());
~~~

Browser gửi trước:

~~~http
OPTIONS /api/echo HTTP/1.1
Origin: http://localhost:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Response cho phép có thể như sau:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Sau preflight thành công, browser gửi request chính:

~~~http
POST /api/echo HTTP/1.1
Origin: http://localhost:5500
Content-Type: application/json

{"message":"Xin chào"}
~~~

Actual response cần có header CORS phù hợp:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Content-Type: application/json

{"echo":"Xin chào"}
~~~

Từ góc nhìn ứng dụng MVC, preflight thông thường được xử lý ở tầng CORS khi handler mapping/config đã xác định, **không cần bạn tự viết OPTIONS controller** chỉ để trả ACAO. Preflight có thể bị từ chối khi origin, method, headers không được cấu hình.

**Lưu ý:** Status/headers cụ thể (200/204, thứ tự, capitalization) có thể khác theo implementation. Điều cần kiểm tra là **origin/method/headers chính sách cho phép** và browser có tiếp tục actual request hay không. Browser có thể cache kết quả preflight trong giới hạn riêng, nên không chắc mỗi POST JSON đều tạo OPTIONS mới.

### 5.4. CORS preflight và credentials

Theo Fetch, preflight CORS thông thường **không mang credentials của actual request** (ví dụ cookies). Vì vậy hệ thống dùng session authentication mà chặn mọi OPTIONS nếu thiếu cookie có thể làm preflight thất bại.

Đó là lý do khi tích hợp Spring Security, CORS processing thường phải xảy ra **trước authentication/authorization filters**. Không có nghĩa bạn nên mở mọi OPTIONS trên toàn internet một cách không điều kiện; vẫn áp dụng origin/method/header allowlist ở CORS layer.

## 6. CORS response headers giải nghĩa

| Header server trả | Tác dụng |
| --- | --- |
| `Access-Control-Allow-Origin` | Cho phép **một origin cụ thể** hoặc `*` trong những điều kiện được phép |
| `Access-Control-Allow-Methods` | Trong preflight response, liệt kê methods mà cross-origin script được phép dùng |
| `Access-Control-Allow-Headers` | Trong preflight response, cho phép headers do script dự định gửi |
| `Access-Control-Allow-Credentials` | Cho phép browser expose response cho credentialed requests khi hợp lệ |
| `Access-Control-Expose-Headers` | Cho JS đọc thêm response headers ngoài tập safelisted |
| `Access-Control-Max-Age` | Cho browser cache kết quả preflight, subject to browser limits |
| `Vary: Origin` | Báo cho caches response có thể khác theo request Origin |

### 6.1. Access-Control-Allow-Origin không phải danh sách CSV

Header này có thể là:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

hoặc với resource public không dùng credentials:

~~~http
Access-Control-Allow-Origin: *
~~~

**Không** ghi nhiều origins ngăn bởi dấu phẩy trong một giá trị ACAO để hy vọng browser chọn:

~~~http
Access-Control-Allow-Origin: https://a.example, https://b.example
~~~

Đó không phải định dạng danh sách origins hợp lệ cho ACAO. Nếu server cho phép nhiều origins, nó thường so `Origin` request với allowlist rồi phản chiếu **một origin đã được kiểm tra** phù hợp. Khi phản hồi khác theo origin, dùng `Vary: Origin` để tránh shared caches dùng nhầm response.

### 6.2. Credentials và wildcard

Nếu frontend dùng cookie/cross-origin credentials:

~~~javascript
fetch("https://api.example.com/account", {
  credentials: "include"
});
~~~

và backend muốn cho script đọc response, thường cần:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không** kết hợp credentialed CORS response với:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser sẽ không cho script đọc credentialed response trong trường hợp này. Với credentialed flow, cách dùng wildcard cho allowed methods/headers/exposed headers cũng có các hạn chế; an toàn nhất là khai báo tường minh allowlist theo nhu cầu thực.

Ghi nhớ rằng `credentials: "include"` không bảo đảm cookie thật sự được gửi. Browser còn áp dụng cookie domain/path, `Secure`, `SameSite` và **third-party cookie policies**. Với cross-site cookies, cấu hình `SameSite=None; Secure` thường là điều kiện cần (không đủ) trong bối cảnh HTTPS phù hợp.

### 6.3. Expose-Headers không tự expose mọi header

Browser cho JS đọc một số CORS-safelisted response headers; muốn đọc header tùy chỉnh, ví dụ `X-Request-ID`, server có thể trả:

~~~http
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: 32fd0d93-2d40-43fe-bdd0-7e672f210501
~~~

Frontend:

~~~javascript
const res = await fetch("http://localhost:8080/api/info");
const id = res.headers.get("X-Request-ID");
console.log(id);
~~~

Nếu CORS chỉ cho đọc body nhưng chưa expose custom response header, JavaScript có thể nhận `null` từ `headers.get` dù Network tab có thấy header đó.

### 6.4. Max-Age và cache

`Access-Control-Max-Age: 1800` là thời gian browser được phép cache **preflight result**, tính theo giây, subject to browser implementation cap. Nó **không phải** cache lifetime của actual JSON response.

Không dùng preflight cache như cơ chế phân quyền người dùng. Khi thay đổi CORS policy, có thể cần chờ các preflight caches trên browser hết hạn theo giới hạn của chúng. HTTP caches và browser CORS preflight caches là các cơ chế khác nhau.

## 7. Không có CORS header thì server có xử lý request không?

Một nhầm lẫn rất thường gặp:

> “Trong Chrome thấy lỗi CORS nên server chắc chắn không nhận được request.”

Không nhất thiết đúng.

### 7.1. Trường hợp GET không preflight

Browser có thể gửi GET, server trả 200, **nhưng browser chặn JavaScript đọc** vì response không có ACAO phù hợp. Network panel có thể thấy GET và payload, còn `fetch` ở script báo lỗi như `TypeError: Failed to fetch` hoặc console CORS message.

### 7.2. Trường hợp POST JSON có preflight

Browser gửi OPTIONS trước. Nếu OPTIONS không được cho phép, browser **không gửi actual POST**. Đây là nguyên nhân backend controller POST không hề thấy request.

### 7.3. CORS không giống status HTTP

| Tình huống | Server thực tế | JS quan sát |
| --- | --- | --- |
| GET cross-origin, HTTP 200, thiếu ACAO | Server xử lý GET thành công | JS không được đọc response |
| POST JSON, preflight bị 403 | Actual POST có thể không được gửi | Fetch bị chặn bởi CORS |
| GET có ACAO đúng, HTTP 404 JSON | Server báo resource không tồn tại | JS đọc được status 404/body vì CORS cho phép |
| GET có ACAO đúng, HTTP 500 JSON | Server lỗi thật | JS có thể đọc status 500/body nếu CORS cho phép |
| GET same-origin HTTP 401 | Không cần CORS | JS thấy HTTP 401 theo semantics |
| `curl` tới server không ACAO | curl vẫn đọc response | curl không thực thi SOP |

Tức là **CORS approval chỉ quyết định quyền script truy cập response**, không thay thế HTTP status, network connectivity, TLS, DNS, authentication hoặc server-side authorization.

## 8. CORS khác các cơ chế an toàn khác như thế nào?

### 8.1. CORS và CSRF

- **CORS:** browser có cho JavaScript ở origin A đọc response của origin B không?
- **CSRF:** một trang độc hại có thể khiến browser của người dùng thực hiện hành động đã xác thực tại server khác hay không?

Một request HTML form POST cross-site có thể được gửi **không cần server cấp phép CORS để script đọc kết quả**. Vì vậy CSRF token / SameSite cookie / kiểm tra Origin phù hợp vẫn cần thiết cho cookie-authenticated state changes.

### 8.2. CORS và authentication/authorization

CORS không chứng minh người gọi là ai. `Origin` không phải token đăng nhập, và công cụ ngoài browser có thể tự gửi giá trị Origin bất kỳ. Backend phải xác thực JWT/session/API key riêng, kiểm tra quyền trên từng resource và tenant.

Một origin được allow CORS nhưng user chưa đăng nhập có thể nhận HTTP 401; nếu CORS response đúng thì frontend **đọc được response 401** để hiển thị/login. Không vì thế mà cấp quyền xem resource.

### 8.3. CORS và CSP

**Content Security Policy (CSP)** — chẳng hạn `connect-src` — do **trang nguồn** công bố để giới hạn frontend được phép kết nối tới đâu. CORS chủ yếu là lựa chọn của **server đích** về origin nào được đọc response. Một request có thể bị CSP chặn trước khi network call hoặc bị CORS chặn sau khi call. Hai chính sách bổ sung, không thay thế nhau.

### 8.4. CORS và SOP cho cookies/storage/DOM

CORS không làm localStorage hay IndexedDB của origin B tự hiện ra cho script của origin A. Nó cũng không cho trang A đọc DOM của iframe cross-origin tùy ý. Cookie có domain/path/site policies riêng và credentials mode của fetch; không suy ra "cho phép CORS" đồng nghĩa "chia sẻ mọi storage".

### 8.5. Browser versus backend, Postman và curl

Server-to-server HTTP clients, command-line `curl`, Postman và nhiều mobile native clients không chịu SOP enforcement giống browser JavaScript. Dù bạn cấu hình CORS nghiêm ngặt, một attacker vẫn có thể gọi trực tiếp public API endpoint nếu mạng và authentication cho phép.

**CORS không phải firewall hay server authorization.** Đừng dùng allowedOrigins như “chỉ ứng dụng hợp lệ được gọi API” nếu không có authentication/authorization.

## 9. Spring MVC xử lý CORS ở đâu?

Spring MVC có hỗ trợ CORS trong `HandlerMapping`. Khi request được map tới handler:

- Với **preflight**, MVC có thể xử lý OPTIONS trực tiếp theo CORS configuration, không cần vào controller business method.
- Với actual cross-origin request, MVC kiểm tra origin/config và thêm headers CORS phù hợp nếu được cho phép.
- Nếu không có CORS configuration phù hợp, preflight có thể bị từ chối; simple/actual request không nhận headers CORS để browser đọc được response.

Spring hỗ trợ hai cách khai báo phổ biến:

1. **Cục bộ** với `@CrossOrigin` ở class hoặc method controller.
2. **Toàn cục có giới hạn URL paths** qua `WebMvcConfigurer#addCorsMappings`.

Bạn cũng có thể dùng `CorsFilter` khi cần xử lý CORS ở mức filter chain hoặc tích hợp với Spring Security. Chỉ nên chọn **một policy chủ đạo** và kiểm tra cách nó kết hợp với các rule cục bộ, tránh allow quá rộng hoặc trả headers xung đột.

### 9.1. @CrossOrigin cho một handler

Ví dụ ngắn:

~~~java
@RestController
@RequestMapping("/api")
public class ExampleController {

    @CrossOrigin(origins = "https://app.example.com")
    @GetMapping("/catalog")
    public List<String> catalog() {
        return List.of("Java", "Spring");
    }
}
~~~

Imports từ `org.springframework.web.bind.annotation` và `java.util.List`. Khi mục đích chỉ là một số endpoint, local annotation dễ nhìn. Tuy nhiên khi API có nhiều endpoints cùng chính sách, global configuration rõ và ít copy-paste hơn.

**Không nên** thêm `@CrossOrigin(origins = "*")` tùy tiện lên mọi controller để "lỗi biến mất". Điều đó có thể vô tình cho các trang web tùy ý đọc dữ liệu API không credentialed khi các lớp bảo vệ khác chưa được thiết kế đúng.

### 9.2. Global CORS với WebMvcConfigurer

~~~java
@Configuration
public class ApiCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(1800);
    }
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Cấu hình này hạn chế **URL path**, origin, method, headers và thời gian preflight cache. Không đặt `@EnableWebMvc` trong ứng dụng Spring Boot nếu chỉ cần tùy chỉnh CORS, vì nó có thể thay thế các phần MVC auto-configuration hữu ích.

**Lưu ý kết hợp:** CORS configuration global và `@CrossOrigin` cục bộ có cơ chế combine của Spring. Nhiều thuộc tính dạng danh sách có thể được hợp nhất, làm phạm vi được phép **rộng hơn mong đợi**. Review cấu hình cuối và viết tests cho các origin được phép và bị cấm.

### 9.3. Khi có Spring Security

CORS preflight thông thường không mang cookie/session credentials của actual request. Nếu Spring Security yêu cầu xác thực ngay trước khi CORS được xử lý, OPTIONS có thể bị từ chối.

Trong ứng dụng Spring Security Servlet:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .cors(Customizer.withDefaults())
            // Khai báo authentication, authorization và CSRF phù hợp ứng dụng.
            .build();
}
~~~

Fragment này **chưa đủ** thành cấu hình security production: cần dependency Spring Security và chính sách bảo vệ/authorization. `http.cors(...)` giúp Security tích hợp CORS configuration đúng thứ tự. Không dùng `permitAll OPTIONS /**` như một cách chữa chung thay vì cấu hình CORS chính xác, và không tắt CSRF vô điều kiện cho ứng dụng dựa cookie/session.

Trong hệ thống có gateway, hãy xác định **gateway hay Spring backend chịu trách nhiệm CORS headers**, tránh cả hai thêm ACAO khác nhau hoặc phản hồi preflight không nhất quán.

## 10. Dự án chạy được: Spring Boot 3.5 và frontend khác port

Demo sau tạo backend API ở `http://localhost:8080`, chỉ cho browser frontend từ `http://localhost:5500` đọc response cross-origin. Có endpoint GET không preflight và POST JSON có preflight. Frontend chỉ dùng JavaScript fetch, không có session/cookies trong demo.

### 10.1. Cấu trúc

~~~text
cors-origin-demo/
├── pom.xml
├── src/main/java/demo/CorsOriginApplication.java
├── src/test/java/demo/CorsOriginTest.java
└── web-client/index.html
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cors-origin-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. CorsOriginApplication.java

Tất cả đoạn mã dưới đây nằm trong **một file** `src/main/java/demo/CorsOriginApplication.java`. Chỉ class `CorsOriginApplication` là public; các record/controller/config còn lại là package-private, nên Java 17 cho phép đặt chung file.

~~~java
package demo;

import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsOriginApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsOriginApplication.class, args);
    }
}

@Configuration
class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                // Đúng origin frontend local: scheme + host + port.
                .allowedOrigins("http://localhost:5500")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

record InfoResponse(String service, String status) {
}

record EchoRequest(String message) {
}

record EchoResponse(String echo) {
}

@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping(path = "/info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<InfoResponse> info() {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new InfoResponse("cors-demo", "ok"));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<EchoResponse> echo(
            @RequestBody EchoRequest request) {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new EchoResponse("Echo: " + request.message()));
    }
}
~~~

**Điều ứng dụng minh họa:**

- `GET /api/info` từ origin `http://localhost:5500`: actual request không bắt buộc có preflight nếu headers safelisted.
- `POST /api/echo` với `Content-Type: application/json`: browser cần preflight OPTIONS.
- Browser chỉ được đọc response khi response headers CORS hợp lệ; `X-Request-ID` được expose để frontend JS đọc.
- `allowCredentials(false)`: ví dụ không hỗ trợ cross-origin cookie-authenticated requests. Nếu dùng cookies, chính sách phải được thiết kế lại, không chỉ đổi false thành true.
- Chỉ origin `http://localhost:5500` được cho phép trong demo; `http://localhost:5501` hoặc `http://127.0.0.1:5500` là origin khác.

Chương trình **không bật Spring Security**, không giả lập đăng nhập hay quyền truy cập. Đừng lấy cấu hình CORS này làm chính sách authentication production.

### 10.4. Frontend web-client/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>CORS từ localhost:5500</title>
</head>
<body>
  <h1>Thử cross-origin fetch</h1>
  <button id="get">GET /api/info</button>
  <button id="post">POST JSON /api/echo</button>
  <pre id="output"></pre>
  <script>
    const api = "http://localhost:8080";
    const output = document.querySelector("#output");

    async function callApi(path, options) {
      try {
        const response = await fetch(api + path, options);
        const requestId = response.headers.get("X-Request-ID");
        const payload = await response.json();
        output.textContent = JSON.stringify({
          status: response.status,
          requestId,
          payload
        }, null, 2);
      } catch (error) {
        // Nếu là lỗi CORS, browser không cho JS đọc response body.
        output.textContent = "Fetch failed. Xem Network/Console: "
          + error.message;
      }
    }

    document.querySelector("#get").addEventListener("click", () => {
      callApi("/api/info");
    });

    document.querySelector("#post").addEventListener("click", () => {
      callApi("/api/echo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Xin chào" })
      });
    });
  </script>
</body>
</html>
~~~

### 10.5. Khởi động backend và frontend

Terminal 1, trong thư mục `cors-origin-demo`:

~~~bash
mvn spring-boot:run
~~~

Terminal 2, cũng trong thư mục project, dùng Python 3:

~~~bash
python -m http.server 5500 --directory web-client
~~~

Mở bằng browser:

~~~text
http://localhost:5500
~~~

Nhấn nút GET rồi mở DevTools/Network. Bạn sẽ thường thấy **GET /api/info** từ frontend tới backend và response có `Access-Control-Allow-Origin: http://localhost:5500`. Nhấn POST JSON, thường có **OPTIONS /api/echo** trước POST do Content-Type là `application/json`.

Ví dụ kết quả GET (UUID thay đổi mỗi lần):

~~~json
{
  "status": 200,
  "requestId": "40eb6b51-c2f7-4b73-9921-73084776ad6f",
  "payload": {
    "service": "cors-demo",
    "status": "ok"
  }
}
~~~

Ví dụ kết quả POST:

~~~json
{
  "status": 200,
  "requestId": "39e5594b-6306-4715-9e3e-6fce6ba1b6ec",
  "payload": {
    "echo": "Echo: Xin chào"
  }
}
~~~

Các request IDs chỉ là ví dụ, không cố định; không phụ thuộc thời gian response hay số lần OPTIONS thực tế vì preflight cache có thể làm OPTIONS không xuất hiện ở mỗi lần thử.

### 10.6. Kiểm tra bằng curl: không thay thế kiểm thử browser

Mô phỏng actual GET với header Origin:

~~~bash
curl -i 'http://localhost:8080/api/info' \
  -H 'Origin: http://localhost:5500'
~~~

Bạn có thể thấy:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Expose-Headers: X-Request-ID
Vary: Origin
Content-Type: application/json
~~~

Headers có thể còn thêm các trường khác; thứ tự và một số casing khác nhau tùy container.

Mô phỏng preflight:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Response preflight hợp lệ thường có:

~~~http
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

Bây giờ đổi Origin thành origin không được phép:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5501' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Spring MVC có thể từ chối preflight (thông thường trả **403 Invalid CORS request**). Browser sẽ không gửi actual POST cho preflight bị từ chối.

**Nhưng:** `curl` **không thực thi SOP/CORS**; dù nhận HTTP response 200/403, nó vẫn hiển thị bytes. Một phép thử CORS hoàn chỉnh cần **browser DevTools** hoặc integration tests xác minh policy headers.

### 10.7. MockMvc tests: origin được phép và bị cấm

Tạo `src/test/java/demo/CorsOriginTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsOriginTest {
    @Autowired
    MockMvc mvc;

    @Test
    void allowsActualGetFromTrustedOrigin() throws Exception {
        mvc.perform(get("/api/info")
                .header("Origin", "http://localhost:5500"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5500"))
            .andExpect(header().string(
                    "Access-Control-Expose-Headers", "X-Request-ID"))
            .andExpect(jsonPath("$.service").value("cors-demo"));
    }

    @Test
    void requestWithoutOriginNeedsNoCorsHeader() throws Exception {
        mvc.perform(get("/api/info"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void jsonPostPreflightIsApproved() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5500")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "http://localhost:5500"))
            .andExpect(header().string(
                    "Access-Control-Allow-Methods",
                    containsString("POST")))
            .andExpect(header().string(
                    "Access-Control-Allow-Headers",
                    containsString("content-type")));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5501")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthorizedMethodForCorsIsRejected() throws Exception {
        mvc.perform(options("/api/info")
                .header("Origin", "http://localhost:5500")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Những test này xác minh Spring MVC CORS handler: actual response headers, preflight permit/reject theo origin và method, request không có Origin không cần ACAO. Để thấy browser enforcement và credentials/cookie behavior, vẫn cần chạy browser hoặc E2E test.

**Lưu ý status:** implementation Spring CORS có thể chọn status khác cho một số preflight thành công theo cấu hình; test này nhắm đúng Spring MVC 6.2 điển hình. Nếu đổi framework/custom CorsProcessor, điều chỉnh expectation theo HTTP semantics thực tế, không bỏ kiểm tra origin/method/headers.

## 11. Các tình huống CORS phát sinh trong dự án thật

### 11.1. Frontend và API cùng domain nhưng khác port

Trang `http://localhost:5173` gọi `http://localhost:8080` là cross-origin. Cho phép đúng `http://localhost:5173` tại backend hoặc dùng development reverse proxy để frontend gọi `/api` cùng origin của dev server. Dev proxy là công cụ làm URL **same-origin từ góc nhìn browser**, không phải "tắt bảo mật của trình duyệt".

### 11.2. Frontend HTTPS nhưng backend HTTP

`https://app.example.com` gọi `http://api.example.com` vừa cross-origin vừa có nguy cơ **mixed content**. Trước khi tính CORS, browser có thể chặn request do chính sách mixed content. Giải pháp đúng là phục vụ API qua HTTPS; không dùng ACAO để hợp thức hóa HTTP không an toàn.

### 11.3. Proxy đổi Host/Origin

Khi có gateway hoặc reverse proxy, browser thấy public URL khác backend internal address. CORS policy cần dựa trên **public origin chính xác của frontend**; forwarded headers phải đến từ trusted proxies và được cấu hình an toàn. Không tự phản chiếu bất kỳ `Origin` nào mà không allowlist.

### 11.4. Cookie login và khác subdomain

Trang `https://app.example.com` gọi `https://api.example.com` là cross-origin, mặc dù thường same-site. Khi dùng `fetch(..., {credentials:"include"})` và server cho phép credentials, cần allow một origin cụ thể + `Access-Control-Allow-Credentials: true`; cookie policy và CSRF vẫn cần thiết. Không suy ra same-site là không cần CORS.

### 11.5. CORS error che lỗi thật

Server đang trả 500 trước khi CORS processor gắn headers hoặc error handler/gateway trả response khác. Browser chỉ báo “CORS policy blocked”, khiến developer tưởng origin sai. Kiểm tra logs server, HTTP status và actual headers bằng DevTools/curl, rồi sửa **lỗi backend** và error response CORS policy đúng, không bật wildcard bừa để che 500.

### 11.6. Preflight bị authentication filter chặn

Browser gửi OPTIONS không có session cookie; Security filter trả 401/403 trước CORS config. Backend POST controller không được gọi. Hãy cấu hình CORS với Spring Security ở đúng tầng và để policy CORS xử lý OPTIONS, đồng thời giữ authorization cho actual request. Không vì vậy mà bỏ auth của mọi endpoint.

### 11.7. Response cache theo nhầm origin

Server cho `https://a.example`, nhưng CDN cache phản hồi ACAO của A và trả cho B. Nếu ACAO được chọn động, header `Vary: Origin` giúp cache phân biệt variants. CORS không tự cấm caching nội dung nhạy cảm; riêng `Cache-Control` phải đặt theo data privacy.

### 11.8. Custom header làm phát sinh OPTIONS

Frontend thêm `X-Client-Version`, `X-Trace-ID` hoặc `Authorization`. Kể cả GET cũng có thể cần preflight. Nếu API thiếu `allowedHeaders` tương ứng, preflight bị từ chối. Cấu hình chỉ cho phép headers thực sự cần; tránh dùng `*` mặc định trên mọi endpoint nhạy cảm.

## 12. Những lỗi phổ biến cần tránh

1. **So origin theo domain mà quên port:** localhost:3000 khác localhost:8080.
2. **Nhầm path/query là thành phần origin:** `/a` và `/b` trên cùng scheme/host/port là same-origin.
3. **Nhầm same-site và same-origin:** subdomains có thể same-site nhưng vẫn cross-origin.
4. **Cho rằng mọi cross-origin request đều có preflight:** GET thông thường không cần OPTIONS.
5. **Cho rằng không có preflight thì không cần ACAO:** actual response vẫn phải cho phép JavaScript đọc.
6. **Nhầm CORS với authentication:** bất kỳ HTTP client ngoài browser vẫn có thể gọi API nếu không có auth.
7. **Cho rằng CORS là CSRF protection:** cross-site form POST có thể tới server dù không có CORS.
8. **Dùng `Access-Control-Allow-Origin: *` cho credentialed requests:** browser không expose response.
9. **Viết nhiều ACAO origins trong một header CSV:** không đúng format hợp lệ.
10. **Tin header Origin do client cung cấp là bảo mật:** non-browser clients có thể giả mạo.
11. **Whitelist `Origin: null` để hỗ trợ file://:** opaque origins không phải danh tính tin cậy.
12. **Thêm @CrossOrigin("*") lên tất cả controllers:** vô tình mở quyền đọc response rộng hơn yêu cầu.
13. **Cấu hình CORS ở Spring MVC nhưng Security chặn OPTIONS trước:** cần tích hợp CORS trước security checks.
14. **Quên expose custom response header:** JS không đọc được `X-Request-ID` dù Network tab thấy.
15. **Dùng `fetch(..., {mode:"no-cors"})` như cách sửa:** response thường opaque, JS không đọc JSON/status như mong muốn.
16. **Tắt browser web security để demo chạy:** che lỗi cấu hình, tạo rủi ro local environment và không phải giải pháp triển khai.
17. **Chỉ test bằng curl:** curl không thực thi SOP; phải có browser kiểm tra.
18. **Bỏ qua Vary: Origin ở reverse proxy/cache:** cached CORS headers có thể sai theo origin.
19. **Coi 200 ở Network là fetch thành công:** browser có thể đã chặn response.
20. **Không xem lỗi ngoài CORS:** TLS, mixed content, DNS, CSP, server error và redirect có thể là nguyên nhân thật.

## 13. Cách debug theo thứ tự

Khi Console báo CORS error:

1. **Xác nhận origin trang nguồn** bằng `window.location.origin` và origin URL API: so scheme, host, effective port.
2. **Quan sát Network:** có OPTIONS không? Nếu có, xem request `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. **Kiểm tra response preflight:** ACAO có khớp? method/header có được allow? Có HTTP 401/403/redirect?
4. **Nếu actual request xảy ra**, xem HTTP status và response ACAO; nhớ 500/404 thật vẫn có thể bị console hiển thị như CORS block.
5. **Kiểm tra credentials mode:** `same-origin` mặc định hay `include`? Cookie có bị SameSite/Secure/third-party policy chặn không? ACA-Credentials có hợp lệ?
6. **Kiểm tra Spring config:** mapping path, `@CrossOrigin` vs `addCorsMappings`, allowed origins/methods/headers, exposed headers.
7. **Nếu có Spring Security**, kiểm tra filter order và `http.cors(...)`, CSRF handling, preflight không có session cookies.
8. **Nếu có proxy/gateway**, xem response ACAO có bị thêm trùng/xóa, Vary headers, public scheme/host có bị rewrite.
9. **Đừng sửa bằng wildcard ngay:** trước tiên xác định policy mong muốn và test một origin hợp lệ/một origin bị từ chối.
10. **Test browser + server:** curl để xem HTTP bytes, MockMvc để kiểm CORS processing, E2E browser để xác nhận browser enforcement.

## 14. Câu hỏi và bài tập

**Bài 1 — Tính origin:** Trang `https://shop.example.com:443/cart` gọi `https://shop.example.com/api`, `http://shop.example.com/api` và `https://api.example.com/api`. Xác định trường hợp nào same-origin và giải thích scheme/host/port.

**Bài 2 — Same-site:** `https://app.example.com` gọi `https://api.example.com`. Chúng same-origin hay same-site? Vì sao câu trả lời có ảnh hưởng khác nhau đối với CORS và Cookie SameSite?

**Bài 3 — Preflight:** Với bốn fetch requests: GET thuần, POST JSON, POST form-urlencoded và GET có header Authorization, hãy dự đoán cái nào cần OPTIONS và vì sao.

**Bài 4 — Đọc response:** Một GET cross-origin trả HTTP 200 JSON nhưng không có ACAO. Server đã nhận request chưa? Browser JavaScript có đọc body không?

**Bài 5 — Credentials:** Viết cấu hình CORS cho frontend `https://app.example.com` dùng cookie-authenticated API. Vì sao không thể dùng ACAO `*` với credentials? Cần kiểm tra thêm cookie policy và CSRF gì?

**Bài 6 — Spring MVC:** Dùng `WebMvcConfigurer#addCorsMappings` chỉ cho phép `https://admin.example.com` gọi GET `/api/admin/**`; không cho phép origin bất kỳ khác. Viết MockMvc preflight test cho GET cùng origin đó và DELETE bị từ chối.

**Bài 7 — Debug:** Trình duyệt báo CORS error khi API 500. Liệt kê ba cách phân biệt backend thật sự lỗi với thiếu CORS headers và vì sao bật wildcard không chữa root cause.

**Bài 8 — Proxy:** Gateway và backend đều tự thêm ACAO. Cách nào kiểm tra header trùng? Nên chọn một nơi chịu trách nhiệm ra sao?

**Bài 9 — Browser và curl:** Vì sao curl thành công với endpoint không cấu hình CORS nhưng fetch từ localhost:5500 thất bại? Nêu đúng lớp thực thi chính sách.

**Bài 10 — Security:** Giải thích vì sao CORS không bảo đảm endpoint thanh toán khỏi CSRF, và vì sao một server API cần authorization ngay cả khi allowedOrigins chỉ có một domain.

## 15. Ghi nhớ

- **Origin của HTTP(S) = scheme + host + effective port**; khác một thành phần là cross-origin.
- SOP hạn chế quyền truy cập của script giữa origins, **không chặn tuyệt đối mọi request/navigations/embeddings**.
- Cross-origin browser fetch có thể **không cần preflight**, nhưng JS chỉ đọc response nếu **actual CORS response cho phép**.
- **Preflight OPTIONS** thường xuất hiện với JSON POST, custom headers hoặc methods như PUT/DELETE.
- CORS là chính sách browser/server opt-in; **không thay authentication, authorization, CSRF protection hoặc cookie security**.
- Credentialed requests không thể dùng ACAO wildcard `*`; phải dùng origin được phép cụ thể cùng các điều kiện khác.
- Trong Spring MVC, chọn `@CrossOrigin` hoặc `addCorsMappings` hợp lý; khi có Spring Security, xử lý CORS trước authentication/authorization.
- Debug dựa trên **origin thật, OPTIONS, actual response, credentials, HTTP status và network** — không chỉ đọc câu thông báo CORS trong Console.

## 16. Tài liệu chính thức

- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): định nghĩa origin, các loại tương tác cross-origin, SOP.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): safelisted/simple requests, preflight, credentials và headers.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): origin cụ thể, wildcard, credentials và Vary.
- [Fetch Standard](https://fetch.spec.whatwg.org/): định nghĩa hiện đại của CORS protocol và request/response handling.
- [Spring Framework 6.2 — MVC CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html): @CrossOrigin, WebMvcConfigurer, CorsProcessor và cấu hình toàn cục.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước Spring Security.
