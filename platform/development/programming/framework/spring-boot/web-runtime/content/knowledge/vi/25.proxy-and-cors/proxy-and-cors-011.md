# Phân biệt CORS với CSRF, lỗi định tuyến và lỗi từ proxy trong Spring Boot

## 1. Vấn đề: browser báo “CORS error” nhưng lỗi gốc có thể hoàn toàn khác

Một frontend ở `http://localhost:5173` gọi backend Spring Boot ở `http://localhost:8080`:

```javascript
fetch("http://localhost:8080/api/notes", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "hello" })
});
```

Browser hiện “blocked by CORS policy”. Liệu cấu hình `allowedOrigins` của Spring Boot bị sai? **Chưa thể kết luận.** Những tình huống sau đều có thể tạo ra triệu chứng gần giống:

1. CORS thật: backend không cho phép origin, method, request headers hoặc credentials.
2. `OPTIONS` preflight bị Spring Security từ chối trước khi CORS được xử lý.
3. Backend trả **`403` vì CSRF token thiếu/sai**; response lỗi không có header CORS nên browser che nội dung.
4. Frontend gọi sai URL/path/method, backend trả **`404` hoặc `405`**.
5. Reverse proxy rewrite `/api` sai, redirect sang login/HTTPS hoặc chặn `OPTIONS`.
6. Nginx/gateway không kết nối được backend, timeout hoặc backend crash, trả **`502`/`503`/`504`**.
7. Lỗi DNS, TLS certificate, mixed content, mạng hoặc browser extension làm request thất bại ở tầng dưới.

**Quy tắc chẩn đoán:** đừng bắt đầu bằng `allowedOrigins("*")` hay tắt `csrf()`. Bắt đầu bằng việc xác định **request nào thất bại, ai phát response, status/headers thực là gì, backend có nhận request không**. CORS là cơ chế kiểm soát **JavaScript của browser có được đọc response cross-origin**, không phải danh sách mọi lỗi HTTP.

Bài này tập trung vào Spring Boot web runtime với Spring MVC, Spring Security, WebFlux và reverse proxy. Có ví dụ Spring Boot **3.5.x, Java 17+**, lệnh `curl`, kiểm thử `MockMvc`, sơ đồ quyết định và các tình huống triển khai thực.

## 2. Bốn tầng khác nhau: browser, security, router và reverse proxy

Một request frontend thường đi qua nhiều tầng:

```text
JavaScript / Browser
   |
   | 1) kiểm tra origin, preflight khi cần,
   |    chính sách CORS sau khi nhận response
   |
   v
DNS / TLS / CDN / Nginx / Ingress / API Gateway
   |
   | 2) chọn host/path, route upstream,
   |    terminate TLS, timeout, rewrite URI,
   |    auth/rate limit của gateway
   |
   v
Spring Security filter chain
   |
   | 3) CORS integration, authn/authz, CSRF,
   |    security headers, session
   |
   v
Spring MVC DispatcherServlet / WebFlux HandlerMapping
   |
   | 4) match path, HTTP method, consumes/produces,
   |    bind argument, execute controller
   |
   v
Service / Database / Downstream
   |
   v
HTTP response trở ngược qua proxy -> Browser
   |
   +--> Browser có thể che response nếu CORS không đạt
```

Các tầng này **không thay thế nhau**:

| Cơ chế | Câu hỏi chính | Thường xử lý ở đâu? | Biểu hiện liên quan |
| --- | --- | --- | --- |
| **CORS** | Script từ origin A có được truy cập response của origin B không? | Browser thực thi; server phát headers cho phép | Console CORS error, preflight `OPTIONS`, thiếu `Access-Control-Allow-Origin` |
| **CSRF protection** | Request đổi trạng thái do browser tự gắn cookie có phải hành động hợp lệ của người dùng? | Server/Spring Security | Thường `403 Forbidden` nếu token thiếu/sai |
| **Authentication/authorization** | Người gửi là ai, có quyền với tài nguyên không? | Spring Security/gateway | `401`/`403`, redirect tới login |
| **Routing/mapping** | Method và path có endpoint phù hợp không? | Proxy router, Spring MVC/WebFlux | `404`, `405`, `415`, `406` |
| **Reverse proxy/upstream** | Có chuyển request đến đúng backend được không? | Nginx, Ingress, LB, API Gateway | `502`, `503`, `504`, redirect, 404 của gateway |
| **Network/TLS** | Có kết nối an toàn, hợp lệ tới endpoint được không? | DNS, TCP, TLS, browser/OS | Connection refused, DNS/TLS error, mixed content |

Một status **`403` không tự chứng minh CSRF**, vì CORS processor cũng có thể trả 403, authorization có thể trả 403 và gateway/WAF cũng có thể chặn. Một status **`404` không tự chứng minh controller sai**: gateway hoặc proxy cũng có thể phát 404 trước khi request tới Spring.

## 3. CORS thật sự làm gì?

### 3.1. Origin là scheme + host + port

`Origin` thường có dạng:

```text
http://localhost:5173
https://app.example.com
https://app.example.com:8443
```

Hai URL có origin khác nhau khi khác **scheme, hostname hoặc port**:

| Trang đang mở | API được gọi | Same-origin? | Cần xem CORS cho browser fetch? |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | Không, khác port | Có |
| `https://app.example.com` | `https://api.example.com` | Không, khác host | Có |
| `https://app.example.com` | `http://app.example.com` | Không, khác scheme | Có; còn có thể bị chặn mixed content |
| `https://app.example.com` | `https://app.example.com/api` | Có | Thường không có cross-origin CORS |
| `http://localhost:5173` | `http://127.0.0.1:8080` | Không, khác hostname và port | Có |

**Same-origin khác same-site.** Hai subdomain `app.example.com` và `api.example.com` có thể cùng *site* theo quy tắc cookie `SameSite` nhưng vẫn **cross-origin** và cần CORS. CORS không tự điều khiển cookie `Domain`/`Path`/`Secure`/`SameSite`.

### 3.2. Browser quyết định, không phải server “bật quyền mạng”

Một response GET có thể được backend trả đúng `200 OK`. Tuy nhiên nếu request là cross-origin và browser không nhận `Access-Control-Allow-Origin` hợp lệ, JavaScript bị **cấm đọc response**. HTTP request **có thể đã tới server và đã được xử lý**; không phải cứ Console báo CORS là controller chưa chạy.

`curl` và Postman thường không thực thi chính sách CORS giống browser. Vì vậy:

- `curl` có thể nhận body 200, trong khi script browser bị chặn.
- `curl -H "Origin: ..."` giúp kiểm tra **headers do server phát**, nhưng không chứng minh browser thực tế đã cho phép JavaScript đọc body.
- Server-to-server gọi trực tiếp thường không cần CORS, dù vẫn cần auth, network policy, TLS và kiểm tra quyền.

### 3.3. CORS response headers quan trọng

| Header | Ý nghĩa |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép đọc response, hoặc `*` cho một số trường hợp không dùng credentials |
| `Access-Control-Allow-Methods` | Các HTTP methods được phép ở **preflight** |
| `Access-Control-Allow-Headers` | Các request headers được phép ở **preflight** |
| `Access-Control-Allow-Credentials: true` | Cho phép browser hiển thị response khi cross-origin request dùng credentials, nếu origin cụ thể được chấp nhận |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả **preflight** (subject to browser limits) |
| `Access-Control-Expose-Headers` | Các response headers bổ sung JavaScript có thể đọc |
| `Vary: Origin` | Hỗ trợ cache phân biệt response headers khi CORS phụ thuộc Origin |

**Không** gửi `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true` khi frontend dùng credentialed CORS request. Browser từ chối tổ hợp này. Với credentials, hãy cấu hình **origin cụ thể**, ví dụ `http://localhost:5173`, và đánh giá mức tin cậy của origin đó.

`Access-Control-Allow-Origin` không phải nơi liệt kê nhiều origin phân tách bằng dấu phẩy; mỗi response chỉ nên có một giá trị origin hợp lệ (hoặc wildcard khi được phép). Đừng để Spring và Nginx **cùng thêm hai header Allow-Origin** dẫn đến giá trị trùng lặp/sai.

### 3.4. CORS không phải xác thực

Cho `https://frontend.example.com` đọc API không chứng minh người dùng đã đăng nhập. Token/session và authorization vẫn phải được xử lý riêng. Ngược lại, một request có token hợp lệ vẫn có thể bị browser chặn hiển thị response nếu CORS policy không đúng.

Không dùng `Origin` như bằng chứng xác thực người dùng. `Origin` có thể được client không phải browser tự đặt; server không nên trao quyền dữ liệu chỉ vì chuỗi Origin trùng allowlist.

## 4. Preflight OPTIONS: cách nhận diện và vì sao hay lỗi

### 4.1. Khi nào có preflight?

Browser có thể tự gửi **CORS preflight request** trước actual request nếu method, Content-Type hoặc custom headers nằm ngoài tập request được CORS “safelisted”. Ví dụ một `POST` với `Content-Type: application/json` và `X-CSRF-TOKEN` thường cần preflight:

```http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Response cho phép có thể là:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Đây là response **minh họa**; status thành công có thể là 200/204 tùy server/framework và các header/order thật tùy cấu hình. Browser chỉ gửi actual POST sau khi preflight thỏa điều kiện.

### 4.2. Preflight thường không kèm cookie xác thực

Preflight `OPTIONS` là request browser dùng để xin phép. **Nó không mang session cookie authentication** theo mô hình CORS phổ biến. Nếu Spring Security bắt phải đăng nhập **trước khi xử lý CORS**, preflight có thể bị chặn `401` hoặc redirect, dù actual request có cookie hợp lệ.

Spring Security khuyến nghị CORS được xử lý **trước** các kiểm tra xác thực phụ thuộc cookie; cách phổ biến là cấu hình `http.cors(...)` với nguồn cấu hình CORS phù hợp. Không “sửa” preflight bằng cách tắt toàn bộ authentication/CSRF cho mọi API.

### 4.3. Một request OPTIONS bất kỳ chưa chắc là preflight

Lệnh:

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes
```

**Không** mô phỏng đầy đủ CORS preflight, vì thiếu `Origin` và `Access-Control-Request-Method`. Hãy gửi đúng các headers:

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Với cấu hình ở ví dụ mục 9, lệnh này nên trả một phản hồi preflight thành công kèm Allow-Origin. Nếu bị 401/403/404/405/redirect, cần xác định **tầng nào** xử lý OPTIONS và vì sao.

### 4.4. “Simple request” không đảm bảo an toàn CSRF

Một form HTML `POST` với `application/x-www-form-urlencoded` có thể **không** cần preflight, nhưng vẫn có thể gửi cookie/session của người dùng theo chính sách browser. Điều đó là lý do **CORS không thay thế CSRF protection**.

Bỏ Content-Type JSON hay custom header để né preflight chỉ giải quyết một biểu hiện, không tự sửa quyền truy cập, tính đúng đắn của API hoặc rủi ro CSRF. Hãy xây dựng endpoint đúng hợp đồng và cấu hình bảo mật rõ ràng.

### 4.5. Preflight thành công chưa chắc actual request thành công

Ví dụ CORS filter xử lý `OPTIONS /api/missing` cho toàn bộ `/api/**` trước Spring MVC routing: preflight có thể **200**, nhưng `GET /api/missing` vẫn **404** vì route không tồn tại. Tương tự, preflight POST có thể 200 nhưng actual POST thiếu CSRF token sẽ **403**.

Vì vậy luôn kiểm tra **cả preflight và actual request**. Không dùng chỉ một `OPTIONS 200` làm bằng chứng end-to-end API hoạt động.

## 5. CSRF: khác CORS cả về mục tiêu lẫn thời điểm kiểm tra

**Cross-Site Request Forgery (CSRF)** là kiểu lợi dụng việc browser có thể tự gắn credentials (đặc biệt cookie/session) khi gửi request đến một ứng dụng người dùng đã đăng nhập. Một site khác có thể dụ browser thực hiện một hành động mà người dùng không chủ đích.

Ví dụ ứng dụng ngân hàng có endpoint thay đổi dữ liệu:

```http
POST /api/transfer
Cookie: SESSION=...
Content-Type: application/x-www-form-urlencoded

amount=100&to=attacker
```

Nếu API chỉ dựa vào session cookie và không kiểm tra nguồn/CSRF token khi cần, request do một trang khác tạo có thể gây tác động. Trình duyệt **không cần cho script bên ngoài đọc response** thì side effect vẫn có thể đã xảy ra. **CORS thường kiểm soát quyền đọc response của JavaScript; CSRF bảo vệ việc thực hiện thao tác đổi trạng thái.**

### 5.1. Spring Security và trạng thái 403

Trong mô hình Spring Security Servlet mặc định, CSRF protection được bật cho các method **không an toàn** (thường POST, PUT, PATCH, DELETE). Một POST thiếu token hoặc token sai có thể bị **CsrfFilter từ chối 403**, ngay cả khi:

- Request đi từ same-origin;
- CORS được cấu hình hoàn toàn chính xác;
- User đã được xác thực;
- Endpoint thực sự tồn tại và method đúng.

Ngược lại, `GET` thông thường không yêu cầu CSRF token; **GET không được làm thay đổi dữ liệu quan trọng**. Nếu GET lại thực hiện chuyển tiền/xóa dữ liệu, đó là lỗi thiết kế API và có thể làm yếu mô hình bảo vệ.

### 5.2. Vì sao response 403 có thể hiện như lỗi CORS?

Có hai trường hợp:

1. **403 có Allow-Origin đúng**: script cross-origin có thể đọc response 403 và frontend xử lý lỗi đúng.
2. **403 không có Allow-Origin phù hợp**: browser che nội dung/status khỏi JS và thông báo CORS. Root cause vẫn có thể là CSRF, auth hoặc WAF.

Do đó cần đối chiếu Network response, server security logs và header thật, không đoán từ duy nhất thông báo trên Console.

### 5.3. CORS policy đúng không thay CSRF token

- `Access-Control-Allow-Origin` quy định origin nào được JS đọc response, **không** phải token chống request giả mạo.
- `SameSite=Lax`/`Strict` của cookie giúp giảm một số bối cảnh cross-site request nhưng không đủ để loại bỏ mọi CSRF.
- Một subdomain có thể same-site nhưng không phải nguồn đáng tin; CSRF vẫn cần xem threat model.
- CORS credentialed requests tăng độ tin cậy cần dành cho origin được phép, không tự loại bỏ yêu cầu CSRF.
- Nếu API chỉ nhận Bearer token do JS tự gắn trong `Authorization`, không dựa vào cookie auto-sent, nguy cơ CSRF thường khác. **Không tắt CSRF chỉ vì endpoint trả JSON**; cần đánh giá cụ thể cơ chế credentials.

### 5.4. Lấy CSRF token và gửi lại

Với Spring Security + HTTP session, có thể cung cấp endpoint `GET /api/csrf` trả CSRF token cho browser. Frontend phải gửi token trong header (ví dụ `X-CSRF-TOKEN`) hoặc form parameter phù hợp, đồng thời giữ session cookie:

```javascript
const api = "http://localhost:8080";
const csrfResponse = await fetch(api + "/api/csrf", {
  credentials: "include"
});
const { headerName, token } = await csrfResponse.json();

const response = await fetch(api + "/api/notes", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ text: "hello" })
});
const result = await response.json();
console.log(response.status, result);
```

Đây là **snippet chạy trong module/async context của browser**, không phải một file HTML độc lập. Giả sử trang ở `http://localhost:5173`, backend chạy demo mục 9, browser hỗ trợ cookie và CORS credentials, kết quả thực tế khi thành công là status 200 và JSON `{"saved":"hello"}`. Token có thể thay đổi theo session/lifecycle; sau login/logout có thể cần lấy mới.

**Quan trọng:** trường hợp SPA cross-site qua cookie bị ràng buộc bởi `SameSite`, `Secure` và chính sách third-party cookies. Dùng `credentials:"include"` không vượt qua các ràng buộc ấy.

## 6. Routing trong Spring Boot: 404, 405, 415, 406 không phải “lỗi CORS” mặc định

### 6.1. Mapping của controller

Ví dụ:

```java
@RestController
@RequestMapping("/api")
class DemoController {
    @GetMapping("/ping")
    String ping() { return "pong"; }

    @PostMapping(path="/notes", consumes="application/json")
    String create(@RequestBody String body) { return body; }
}
```

Đây là **class minh họa**, cần imports Spring MVC và đặt trong package được quét. Mapping kết hợp thành:

- `GET /api/ping`;
- `POST /api/notes` nhận `application/json`.

Một số trường hợp:

| Request | Kết quả thường gặp | Nguyên nhân |
| --- | --- | --- |
| `GET /api/ping` | `200` | Match path và method |
| `GET /api/pinng` | `404` | Sai chính tả path |
| `GET /api/notes` | `405` | Path được map nhưng GET không được hỗ trợ |
| `POST /api/notes` với `Content-Type: text/plain` | `415` | Controller yêu cầu JSON |
| `GET` endpoint có ràng buộc `produces` không phù hợp `Accept` | `406` | Không có media type thỏa mãn |
| `POST /api/notes` thiếu CSRF token (khi Security bật) | Có thể `403` **trước khi route/deserialize** | Security filter chặn trước Controller |
| `OPTIONS` preflight thiếu cấu hình CORS | Có thể 403/4xx | CORS processor/filter hoặc lớp phía trước từ chối |

Status thực phụ thuộc security filters, exception handlers, proxy và cấu hình; không phải bảng bảo đảm trong mọi project. Ví dụ nếu auth chặn trước routing, cùng URL sai vẫn có thể trả 401/403 thay vì 404.

### 6.2. Những lỗi định tuyến cụ thể

- Thiếu context path: backend thật chạy ở `/shop/api/ping` nhưng frontend gọi `/api/ping`.
- Proxy prefix sai: proxy expose `/backend/api/ping` nhưng forward tới `/api/ping` hoặc `/ping`.
- Trailing slash: `/api/users` và `/api/users/` không phải lúc nào cũng tự coi tương đương trong các phiên bản Spring Framework hiện đại.
- HTTP method sai: frontend gửi `PUT` còn controller chỉ có `@PostMapping`.
- Cấu hình `consumes`/`produces` không khớp Content-Type/Accept.
- Controller nằm ngoài vùng component scan, route chưa được đăng ký.
- Đường dẫn đến actuator/management port hoặc API gateway mapping nhầm service.
- Lỗi security làm route chưa được đánh giá, gây nhầm lẫn rằng controller không tồn tại.

### 6.3. Quan sát tuyến request

Spring MVC đặt routing dưới `DispatcherServlet` và `RequestMappingHandlerMapping`. Nếu request **đã vào Spring** mà không có handler phù hợp, có thể thấy log/exception liên quan `NoHandlerFoundException`, `NoResourceFoundException` hoặc `HttpRequestMethodNotSupportedException` tùy phiên bản/cấu hình.

Nếu request **chưa tới Spring**, việc sửa `@GetMapping` thường vô ích. Cần log ở reverse proxy, ingress và Spring access log.

Đừng tạo một `@RequestMapping("/**")` bắt mọi đường dẫn để “xử lý CORS” khi nguyên nhân là route sai. Cách đó có thể che 404 chính đáng và phá static resources.

## 7. Reverse proxy, gateway và những mã lỗi ở tầng trước backend

### 7.1. Các lỗi thường gặp

| Status/hiện tượng | Nguồn có thể | Đặc điểm |
| --- | --- | --- |
| `301`/`302`/`307`/`308` | Proxy hoặc application redirect | Preflight/credentials có thể gặp lỗi khi bị redirect, đặc biệt đổi origin hoặc scheme |
| `401 Unauthorized` | Authentication filter, gateway auth, proxy auth | Chưa xác thực hoặc cần credentials |
| `403 Forbidden` | Authorization, CSRF, CORS filter, WAF | Cần phân biệt bằng headers, log và loại request |
| `404 Not Found` | Spring route hoặc gateway route | Request có thể chưa đến app |
| `405 Method Not Allowed` | Spring mapping hoặc gateway policy | Path đúng nhưng method sai |
| **`502 Bad Gateway`** | Proxy nhận upstream response không hợp lệ, kết nối lỗi | Backend tắt, sai port, upstream TLS/HTTP protocol mismatch |
| **`503 Service Unavailable`** | Gateway hoặc backend | Không có healthy upstream, overload, maintenance |
| **`504 Gateway Timeout`** | Proxy đợi upstream quá lâu | Backend/DB chậm, timeout hoặc network issue |
| `413 Content Too Large` | Proxy hoặc server | Body vượt giới hạn |
| `431 Request Header Fields Too Large` | Proxy hoặc server | Header/cookie quá lớn |
| TLS/DNS/connection failure | Network stack, certificate, browser | Có thể **không có status HTTP** vì response chưa được tạo |

Các mã `502`/`503`/`504` thường xuất hiện ở gateway nhưng backend cũng có thể chủ động trả 503; không gán một mã cho một thành phần mà không xem log và Server/Via headers thực tế.

### 7.2. Nginx có thể làm hỏng path dù CORS cấu hình đúng

Ví dụ backend Spring có `GET /api/ping`, proxy public ở port 8088. **Cấu hình minh họa Nginx HTTP local**:

```nginx
server {
    listen 8088;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

Vì `proxy_pass` ở đây **không có URI path** sau hostname/port, Nginx thông thường giữ nguyên request URI: `GET /api/ping` tới upstream vẫn là `/api/ping`.

Nếu sửa thành:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Dấu slash **cuối** trong `proxy_pass .../;` chỉ ra URI prefix `/`. Theo quy tắc rewrite của Nginx, phần `/api/` khớp location có thể bị thay bằng `/`, nên `/api/ping` trở thành `/ping` ở upstream. Spring controller đang đợi `/api/ping` sẽ trả **404**, dù CORS chưa hề sai.

Đây là lý do cần kiểm tra **URL ngoài proxy lẫn URI backend thực nhận**.

### 7.3. `OPTIONS` có thể bị chặn trước khi tới Spring

Nginx/Ingress/Gateway có thể:

- Từ chối `OPTIONS` theo allowed methods hoặc auth policy.
- Redirect từ HTTP sang HTTPS hoặc từ `/api` sang `/api/`.
- Bỏ/ghi đè headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
- Phát response preflight tự xử lý nhưng thiếu `Access-Control-Allow-Headers`.
- Thêm `Access-Control-Allow-Origin` lần thứ hai trong khi Spring cũng thêm.
- Trả `502`/`504` không kèm CORS response headers, khiến browser chỉ hiển thị “CORS failed”.

Khi CORS được xử lý tại proxy **thay vì backend**, phải thiết kế một owner rõ ràng, bảo đảm preflight và actual responses nhất quán, kể cả responses lỗi. Không lắp hai lớp “thêm CORS cho mọi response” một cách mù quáng.

### 7.4. Forwarded headers không phải bộ sửa mọi lỗi

Sau TLS termination, proxy có thể gửi `Forwarded` hoặc `X-Forwarded-Proto`, `X-Forwarded-Host` để backend xây URL/redirect đúng. Spring Boot hỗ trợ `server.forward-headers-strategy` (ví dụ `framework` để dùng `ForwardedHeaderFilter` trong Servlet MVC).

```properties
# Chỉ bật khi backend thực sự sau proxy tin cậy.
server.forward-headers-strategy=framework
```

Điều này có thể giúp redirect scheme/host, nhưng **không tự sửa** sai `proxy_pass`, không mở port backend bị đóng, không sửa OAuth callback hoặc CORS origin allowlist. Phải bảo đảm client Internet **không tự chèn giả mạo forwarded headers** vào đường tin cậy; proxy cần lọc/ghi đè headers.

### 7.5. Kiểm tra trực tiếp và qua proxy

```bash
# Backend trực tiếp:
curl -i http://localhost:8080/api/ping

# Proxy phía trước backend:
curl -i http://localhost:8088/api/ping
```

Nếu direct trả 200 còn proxied trả 404/502, tập trung vào gateway route, rewrite, DNS/upstream port và logs. Nếu cả hai trả 404, xem Spring mapping và context path. Khi so sánh CORS, thêm cùng `Origin` ở cả hai request.

Trong môi trường container/Kubernetes, `localhost` bên trong **pod/container của proxy** không tự trỏ tới Spring Boot container khác. Dùng đúng service DNS/name/port của runtime. Các địa chỉ trên chỉ minh họa hai process cùng host ở môi trường local.

## 8. Quy trình chẩn đoán bắt đầu từ bằng chứng

### Bước 1 — Xác định request thất bại

Mở DevTools → **Network**, lọc `Fetch/XHR` rồi xem:

- Request URL thực (scheme, hostname, port, path, query).
- Request Method: `OPTIONS` hay actual `GET`/`POST`/`PUT`?
- Status code nếu browser có thể hiển thị.
- Request headers: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, `Cookie`, `Authorization`.
- Response headers: `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Vary`, `Location` và dấu hiệu response từ proxy.
- Timing: DNS, connect, TLS, waiting, failed/canceled.

**Console là tín hiệu; Network + logs là bằng chứng.** Một dòng `TypeError: Failed to fetch` có thể bao trùm lỗi CORS, TLS và mạng — đừng biến nó thành kết luận duy nhất.

### Bước 2 — Tách preflight khỏi actual request

Nếu browser có `OPTIONS` rồi không có actual request, tập trung vào **preflight**. Nếu `OPTIONS` đã thành công nhưng POST trả lỗi, tập trung vào **CSRF/auth/route/validation/proxy** cho actual request.

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Đảm bảo dùng **đúng origin** của trang thật (kể cả port) và **đúng headers/method** của actual request. Một preflight test GET không chứng minh POST với `Authorization` sẽ được chấp nhận.

### Bước 3 — Gửi actual request, xem status thật

```bash
curl -i http://localhost:8080/api/ping \
  -H "Origin: http://localhost:5173"
```

Nếu HTTP status là 200 nhưng thiếu Allow-Origin, đó là CORS response policy. Nếu 403/404/502, xác định nguyên nhân HTTP thật, sau đó mới xem thêm headers CORS. `curl` không chặn việc đọc response như browser.

### Bước 4 — So sánh qua từng hop

Cùng method/path/Origin:

- Gọi backend trực tiếp (nếu mạng và quyền cho phép).
- Gọi ingress/gateway public.
- So sánh `status`, `Location`, `Access-Control-*`, `Server`/`Via` và request ID.
- Nếu khác nhau, xem rewrite/route/filter/header ở hop làm thay đổi kết quả.

Không chia sẻ cookie, Bearer token, session ID hoặc CSRF token thật trong log công khai khi thu bằng chứng.

### Bước 5 — Định vị Spring xử lý đến đâu

- **Không có request trong backend access log**: nghi proxy, DNS/upstream, TLS, load balancer, routing.
- **Có request trong access log nhưng controller không chạy**: nghi CORS filter, security/CSRF, handler mapping hoặc exception trước controller.
- **Controller chạy rồi status 5xx**: nghi service/database/serialization, đồng thời xem proxy timeout ở phía ngoài.
- **Controller 200 nhưng browser fail CORS**: xem response headers tại client-facing proxy, duplicates và credentials.
- **Server trả 404/405**: xem path, method, context path và component scanning.

### Bước 6 — Sửa đúng lớp và xác minh lại

Không tắt security/filter theo kiểu “cho qua để test production”. Sửa origin allowlist, security chain, controller mapping hoặc proxy route **đúng nơi phát lỗi**. Sau đó chạy lại **preflight + actual request + browser behavior**, và bảo đảm các origins không được phép vẫn bị chặn.

## 9. Demo hoàn chỉnh: Spring Boot MVC + Spring Security + CORS và CSRF

Demo này giúp quan sát bốn điều khác nhau trên cùng server:

1. Allowed-origin preflight `OPTIONS` thành công dù request chưa có session.
2. `GET /api/ping` trả JSON và có CORS header khi gửi Origin hợp lệ.
3. `POST /api/notes` **không có CSRF token** trả `403` dù CORS policy cho phép.
4. Cùng POST **có session cookie và CSRF token hợp lệ** thành công.
5. `GET /api/missing` trả `404`; `GET /api/notes` trả `405` dù CORS được phép.

Dùng **Java 17+**, **Maven** và **Spring Boot 3.5.0** (bản phát hành đã có của dòng 3.5). Phiên bản demo cố định để dễ tái hiện; production cần dùng phiên bản patch đang được bảo trì. Demo **cho phép mọi request ở tầng authorization** để cô lập bài học về CORS/CSRF; **không** xem đây là security policy phù hợp cho API thật.

### 9.1. Cấu trúc

```text
cors-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/corsdemo/
    │   │   └── CorsDiagnosisApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/corsdemo/
            └── CorsDiagnosisTest.java
```

### 9.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cors-diagnosis-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

Spring Boot parent quản lý phiên bản các Spring dependencies; không ghim riêng `spring-security-web` hoặc `spring-webmvc`. `spring-security-test` cho phép MockMvc mô phỏng CSRF token hợp lệ trong test.

### 9.3. Java source đầy đủ: controller + security config

Tệp duy nhất `src/main/java/com/example/corsdemo/CorsDiagnosisApplication.java`:

```java
package com.example.corsdemo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class DemoApiController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    // Gọi GET để lấy token phù hợp với session hiện tại.
    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken token) {
        return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
    }

    @PostMapping(path = "/notes",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> create(@RequestBody NoteInput input) {
        return Map.of("saved", input.text());
    }

    public record NoteInput(String text) {}
}

@Configuration
class WebSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Origin của frontend demo; khác origin với port 8080.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().permitAll())
                .build();
    }
}
```

Mã này là một tệp Java hợp lệ: chỉ `CorsDiagnosisApplication` là `public` top-level class, `DemoApiController` và `WebSecurityConfig` cùng package được Spring quét. `record NoteInput` là kiểu dữ liệu request hợp lệ với Java 17 và Jackson mà starter web dùng.

**Giải thích điểm quan trọng:**

- `UrlBasedCorsConfigurationSource` đăng ký policy cho `/api/**`.
- `http.cors(Customizer.withDefaults())` tích hợp CORS ở vị trí phù hợp trong Spring Security filter chain, để preflight không bị coi là một request chưa đăng nhập bình thường.
- `.csrf(Customizer.withDefaults())` **giữ CSRF bật**. Đây là cơ chế độc lập với CORS.
- `.anyRequest().permitAll()` **chỉ tắt ràng buộc authorization trong demo**, không vô hiệu hóa CsrfFilter. Bởi thế POST thiếu token vẫn có thể trả 403.
- `GET /api/csrf` tải token vào session khi cần; browser/curl phải giữ cookie session để POST dùng cùng token.
- `setAllowCredentials(true)` chỉ hợp lệ với một origin cụ thể đã cấu hình, không dùng wildcard `*`.
- `setMaxAge(1800L)` là thời gian cache **preflight** theo giây, không phải session timeout hay thời gian JWT còn hạn.
- Không đăng ký thủ công thêm một `CorsFilter` thứ hai và không thêm `@CrossOrigin("*")` vào tất cả controller; cấu hình nhiều lớp dễ tạo header trùng.

**Giới hạn:** Demo không có login và chỉ lưu dữ liệu “note” ở kết quả response; không có database. Mục tiêu là quan sát luồng request, không phải xây dựng hệ thống lưu trữ hay mô hình auth production.

### 9.4. `application.properties`

```properties
server.port=8080
spring.application.name=cors-diagnosis-demo
```

Đây là file hoàn chỉnh cho cấu hình cơ bản. CORS policy và SecurityFilterChain đã nằm ở Java config. Nếu cổng 8080 đang bận, có thể đổi `server.port` và cập nhật URL kiểm tra.

### 9.5. Chạy

Từ thư mục `cors-diagnosis-demo`, cần Java 17+ và Maven:

```bash
mvn clean package
java -jar target/cors-diagnosis-demo-1.0.0.jar
```

Có thể dùng `mvn spring-boot:run` để phát triển. Với project mới khởi động, không cần frontend thực sự chạy tại 5173 để thực hiện kiểm tra CORS bằng `curl`: server chỉ xét chuỗi `Origin` gửi trong request.

### 9.6. Kiểm tra route GET và CORS

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/ping
```

Các phần quan trọng kỳ vọng:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"status":"ok"}
```

Đây là **phần response minh họa**: thứ tự và tập headers, HTTP reason phrase thay đổi theo servlet container và phiên bản; body JSON có một key `status` với giá trị `ok`. Browser fetch có credentials từ origin 5173 có thể đọc response nếu cookie policy và các điều kiện khác cho phép.

Thử origin không được phép:

```bash
curl -i -H "Origin: https://not-allowed.example" \
  http://localhost:8080/api/ping
```

CORS processor ở cấu hình demo không chấp nhận origin này; status thường **403** với thông tin “Invalid CORS request”. Không sửa bằng cách thêm mọi origin khi chính sách thiết kế chỉ cho phép một frontend.

### 9.7. Kiểm tra preflight trước POST JSON

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Kỳ vọng preflight thành công (thường HTTP 200), có `Access-Control-Allow-Origin: http://localhost:5173`, `Access-Control-Allow-Methods` chứa POST, `Access-Control-Allow-Headers` cho phép content-type và x-csrf-token, `Access-Control-Allow-Credentials: true`. **Không cần gửi cookie hoặc CSRF token trong preflight**.

### 9.8. POST không token: lỗi CSRF, không phải lỗi origin

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  --data '{"text":"demo"}'
```

Kỳ vọng **403 Forbidden** vì thiếu CSRF token. CORS đã cho phép origin, nhưng Spring Security vẫn chặn thao tác không an toàn. Một response 403 có `Access-Control-Allow-Origin` hợp lệ giúp browser nhìn thấy status thực thay vì bị che dưới dạng CORS error.

### 9.9. POST có token hợp lệ: phân biệt lỗi đã được sửa ở đâu

Đầu tiên lấy token và session cookie:

```bash
curl -i -c cookies.txt -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/csrf
```

Body JSON có dạng:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "<giá-trị-token-thay-đổi-theo-session>"
}
```

Chuỗi trong dấu ngoặc nhọn ở đây là **mô tả placeholder**, không phải output literal để copy. Hãy lấy giá trị `token` thực từ response và gửi nó trong header request tiếp theo, đồng thời gửi cùng cookie jar:

```bash
curl -i -b cookies.txt -X POST http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: PASTE_ACTUAL_TOKEN_HERE" \
  --data '{"text":"demo"}'
```

Thay `PASTE_ACTUAL_TOKEN_HERE` bằng token lấy từ chính session. Khi hợp lệ, response:

```http
HTTP/1.1 200
Content-Type: application/json

{"saved":"demo"}
```

Đây là response minh họa rút gọn. Với Spring Security 6, token trả qua `CsrfToken` có thể được **mask** để giảm rủi ro BREACH; sử dụng nguyên giá trị trả về, không tự sửa hoặc hash lại. Nếu token không khớp cookie session, request sẽ vẫn bị 403 — đó là hành vi bảo vệ đúng.

Nếu muốn tránh trích token thủ công, có thể dùng `curl` kết hợp công cụ JSON như `jq` hoặc frontend fetch đã trình bày ở mục 5.4.

### 9.10. Kiểm tra lỗi route và method

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/missing

curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/notes
```

Với cấu hình demo: request đầu là **404**, request thứ hai là **405** vì `/api/notes` chỉ chấp nhận POST. Có thể vẫn có `Access-Control-Allow-Origin` phù hợp, nhưng không biến một route sai thành route đúng.

Lưu ý khi dùng method không an toàn để thử 405: Spring Security có thể chặn CSRF **trước** routing, làm bạn nhận 403 thay vì 405. Vì thế dùng GET (safe) tới route chỉ hỗ trợ POST là cách thử minh bạch hơn.

### 9.11. Lưu ý về shell

Các lệnh ví dụ dùng Bash/Linux/macOS với `\` để nối dòng. Trong PowerShell, dùng `curl.exe` và đặt lệnh trên một dòng hoặc nối theo cú pháp PowerShell; quoting JSON cũng có thể cần điều chỉnh. Trên Windows, Postman hoặc một công cụ HTTP client hỗ trợ header là phương án khác.

Đừng chạy lệnh có token/cookie thật trên terminal dùng chung rồi đưa lịch sử command/log công khai. Demo không chứa credentials production.

## 10. Kiểm thử MockMvc: tách bạch CORS, CSRF và routing

Hai dependencies test đã có trong POM ở mục 9:

- `spring-boot-starter-test`: JUnit Jupiter + Spring Test/MockMvc và các thư viện test;
- `spring-security-test`: request post-processors như `csrf()`.

Tệp hoàn chỉnh `src/test/java/com/example/corsdemo/CorsDiagnosisTest.java`:

```java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDiagnosisTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightSucceeds() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"demo\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"demo\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.saved").value("demo"));
    }

    @Test
    void wrongRouteIsNotFound() throws Exception {
        mvc.perform(get("/api/missing"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodIsNotAllowed() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

Chạy:

```bash
mvn test
```

Các tests độc lập và không chia sẻ session cần thiết ngoài request. MockMvc chạy qua Spring Security filter chain nếu cấu hình test như trên. Không khẳng định test đã kiểm tra toàn bộ reverse proxy: **MockMvc không đi qua Nginx/CDN**, vì vậy vẫn cần HTTP integration smoke tests trên đường triển khai thật.

## 11. Những cách cấu hình CORS đúng trong Spring MVC

Spring MVC có nhiều điểm cấu hình; nên chọn một cơ chế rõ ràng và bảo đảm Spring Security nhìn thấy policy đó.

### 11.1. `@CrossOrigin` cho một controller

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET, RequestMethod.POST})
@RestController
@RequestMapping("/api/public-info")
class PublicInfoController {
    @GetMapping
    String read() { return "ok"; }
}
```

Đây là **snippet minh họa**, cần imports `CrossOrigin`, `RequestMethod`, `RestController`, `RequestMapping`, `GetMapping`. Khi API có Spring Security, phải **kết hợp** chính sách với filter chain. Không đặt `@CrossOrigin` trên endpoint không phù hợp chỉ để “hết lỗi Console”.

### 11.2. `WebMvcConfigurer#addCorsMappings`

```java
@Configuration
class CorsMvcConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
```

Đây là **snippet cấu hình MVC**, cần imports tương ứng. Có thể dùng cùng `http.cors(Customizer.withDefaults())` để Spring Security tích hợp CORS của MVC. **Đừng thêm fragment này song song với bean `corsConfigurationSource` của demo** rồi kỳ vọng mọi cấu hình merge theo ý muốn; khi có nhiều CORS sources/filter chains, cơ chế chọn bean/mapping có thể phức tạp. Hãy dùng một source rõ và kiểm thử.

### 11.3. CORS filter trong Spring Security

Một `UrlBasedCorsConfigurationSource` cung cấp policy cho `SecurityFilterChain` là lựa chọn dễ làm rõ thứ tự xử lý, nhất là khi có nhiều endpoints hoặc security chains. Ví dụ mục 9 dùng cách này. Với ứng dụng dùng nhiều `SecurityFilterChain`, cần xác định CORS source và path matcher của **từng chain** thay vì tin rằng một cấu hình vô điều kiện áp dụng cho mọi path.

**Không cấu hình** `allowCredentials(true)` và `allowedOrigins("*")`. Nếu thật sự phải cho phép nhiều origin cấu hình động, Spring hỗ trợ `allowedOriginPatterns` nhưng phải giới hạn pattern chặt, có test và review security — không dùng pattern quá rộng cho API có cookie/session nhạy cảm.

### 11.4. CORS trên WebFlux

Spring WebFlux hỗ trợ CORS qua `WebFluxConfigurer`/`CorsWebFilter` và hạ tầng reactive `HandlerMapping`. Ví dụ **snippet dành riêng cho WebFlux**:

```java
@Configuration
class CorsWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true);
    }
}
```

Imports phải dùng `org.springframework.web.reactive.config.WebFluxConfigurer` và `org.springframework.web.reactive.config.CorsRegistry`. Với **Spring Security WebFlux**, tích hợp CORS qua `SecurityWebFilterChain`/`CorsWebFilter` tương ứng; không đem nguyên `HttpSecurity`/`SecurityFilterChain` của Servlet MVC vào runtime reactive. CSRF reactive cũng có hỗ trợ và chính sách riêng.

## 12. Browser fetch, cookies, Authorization và bẫy credentials

### 12.1. Cross-origin fetch không tự gửi cookie như same-origin

Default `fetch` credentials mode thường là `same-origin`. Nếu SPA `http://localhost:5173` gọi API `http://localhost:8080` và cần cookie/session, frontend dùng:

```javascript
fetch("http://localhost:8080/api/ping", {
  credentials: "include"
});
```

Server phải cho phép origin cụ thể cùng `Access-Control-Allow-Credentials: true`. Nhưng **cookie vẫn phải** đáp ứng `Domain`/`Path`/`Secure`/`SameSite`/browser privacy policy. `credentials:"include"` không phá được quy định third-party cookies, và không sửa 401/403 của server.

### 12.2. CORS không đồng nghĩa “cho phép mọi request có Authorization”

Khi gửi `Authorization: Bearer ...`, browser thường tạo preflight do header không nằm trong tập safelisted; server phải cho phép `Authorization` trong `Access-Control-Allow-Headers` nếu API thiết kế sử dụng header đó. Ngoài ra backend **vẫn phải xác minh token và quyền**.

Demo ở mục 9 chỉ cho phép `Content-Type`/`X-CSRF-TOKEN`, **cố ý không cho `Authorization`**. Nếu thêm Bearer token vào frontend mà không cập nhật CORS header allowlist, preflight có thể fail dù endpoint/cookie đều không có vấn đề. Khi đổi contract, cập nhật policy có chủ đích và thêm tests.

### 12.3. Vấn đề 401/403 bị che

Giả sử API trả `401` và redirect sang `/login`, nhưng login page không có CORS headers. JS thấy CORS error thay vì nội dung lỗi đăng nhập. Cách đúng thường là:

- API trả status `401`/`403` phù hợp và response headers CORS đúng cho allowed origin;
- frontend xử lý auth errors trong JSON/status, không redirect API fetch sang trang HTML login cross-origin;
- gateway và Spring cùng tuân theo một chiến lược error response;
- không mở CORS ra tất cả origins để “có thể đọc lỗi” khi dữ liệu nhạy cảm.

### 12.4. Không dùng `mode:"no-cors"` để chữa lỗi

```javascript
fetch("https://api.example.com/private", { mode: "no-cors" });
```

Kết quả có thể là **opaque response**, JavaScript không đọc được status/body/headers thông thường. Đây không phải cách đưa API cross-origin thành công để ứng dụng xử lý JSON. Hãy cấu hình CORS đúng ở server hoặc kiến trúc reverse proxy hợp lệ.

## 13. Bảo mật và caching khi sửa CORS/proxy

### 13.1. Vì sao không bật wildcard ở mọi nơi?

Khi API trả dữ liệu cá nhân theo cookie/session, việc cho phép origin bất kỳ kết hợp credentials có thể mở đường cho trang không đáng tin đọc dữ liệu người dùng (nếu browser cho phép). Đó là một thay đổi security policy lớn, không phải bản sửa network nhỏ.

Một allowlist nên dựa vào **origin thật của frontend** ở từng môi trường, ví dụ dev, staging, production; đừng chấp nhận mọi hostname có hậu tố gần giống. Với origins lấy từ cấu hình/environment, kiểm tra chính xác scheme và port và không ghép từ `Host` request chưa được tin cậy.

### 13.2. `Vary` và cache

Khi server chọn `Access-Control-Allow-Origin` dựa trên header `Origin`, response shared cache cần tránh trộn headers/data giữa các origins. `Vary: Origin` cùng các header preflight liên quan có thể giúp cache phân biệt. Một reverse proxy/CDN tự thêm CORS headers có thể xóa/ghi đè Vary không đúng, gây browser chặn không ổn định.

**Không** coi `Vary: Origin` là authorization. Dữ liệu cá nhân vẫn cần `Cache-Control: private` hoặc `no-store` theo tính chất nội dung và kiểm tra quyền trên server.

### 13.3. Đừng tắt CSRF toàn cục để qua 403

Khi backend dùng cookie session hoặc HTTP Basic được browser tự gửi, CSRF protection thường có ý nghĩa. Chỉ tắt CSRF cho API **thật sự không dựa trên credentials tự động của browser** sau khi đánh giá threat model; quyết định phải nằm ở cấu hình security có scope rõ. Giữ CSRF với các browser-driven unsafe requests và test flow login/logout/token rotation.

Nếu dùng `CookieCsrfTokenRepository` cho SPA, cần hiểu `HttpOnly`, handler BREACH/token masking và cách JavaScript nhận token; không chỉ copy một đoạn cấu hình cũ của Spring Security mà không kiểm tra phiên bản.

### 13.4. Không log secrets khi debug

Các headers cần quan sát như `Origin`, `Access-Control-Request-Method` và correlation ID thường an toàn hơn việc in toàn bộ `Cookie`, `Authorization`, CSRF token. Ở production, log có request ID, method, path đã chuẩn hóa, status, upstream, latency và phân lớp lỗi; che/redact thông tin nhạy cảm.

## 14. Ma trận triệu chứng → nguyên nhân → phép thử

| Triệu chứng | Nhóm lỗi nhiều khả năng | Phép thử nhanh |
| --- | --- | --- |
| Browser báo thiếu `Access-Control-Allow-Origin`; curl trả 200 | CORS response policy | `curl -i -H "Origin: ..."`, xem headers |
| Preflight `OPTIONS` 401, không có actual POST | Spring Security/gateway chặn preflight | Kiểm tra `http.cors()`, preflight logs, auth gateway |
| Preflight trả 403 “Invalid CORS request” | CORS allowlist/method/header | So `Origin`/method/request headers với policy |
| OPTIONS 200 nhưng POST 403 | CSRF/authorization có thể chặn actual request | Xem `CsrfFilter`, token/cookie và security logs |
| OPTIONS 200 nhưng GET/POST 404 | Controller route hoặc proxy rewrite | Direct backend request, inspect mapping |
| GET 404 khi frontend dùng `/api/ping`, direct `/api/ping` lại 200 | Proxy routing/rewrite | Nginx `proxy_pass` và ingress path rules |
| GET 405 | Sai HTTP method | Xem `@GetMapping`/`@PostMapping`, `Allow` header |
| POST 415 | Sai Content-Type | So với `consumes`, JSON vs form |
| GET 406 | Sai Accept/produces | So `Accept` và `produces` |
| Browser console báo CORS; network response 502 | Upstream connection/proxy | Gateway error logs, service name, port |
| Browser console báo CORS; network 504 | Upstream timeout | Gateway timeout và backend/DB duration |
| Browser không có response HTTP, báo TLS | Certificate/mixed content/network | Kiểm tra HTTPS cert, DNS, browser Security |
| CORS credential error khi Allow-Origin=* | Wildcard không hợp lệ với credentials | Dùng origin cụ thể và Allow-Credentials |
| CORS error chỉ khi login hết hạn | Redirect/error response thiếu headers | Xem 302/401/403 và Location/headers |
| CORS chỉ lỗi trên staging | Origin/port/proxy policy khác môi trường | So dev/staging Origin và Ingress config |
| Có hai Allow-Origin headers | Spring và proxy cùng phát | Chọn owner CORS, bỏ duplicate |
| CORS pass nhưng API vẫn 401 | Auth thiếu/hết hạn | Kiểm tra token/session và auth logs |
| CORS pass nhưng dữ liệu sai | Business logic/DB/serialization | Kiểm tra controller/service/downstream |
| POST từ tab khác site gây thay đổi dữ liệu | CSRF defense thiếu hoặc route unsafe | Xem CSRF token, SameSite, HTTP method |
| CORS hết lỗi sau `mode:"no-cors"` nhưng JS không đọc JSON | Opaque response | Bỏ `no-cors`, sửa allowlist |

**Không dựa duy nhất vào status để phân loại**; cùng status có thể do nhiều tầng phát. Tìm request ID và đối chiếu log từng hop là bước quyết định trong hệ thống có nhiều proxy.

## 15. Checklist vận hành và quy trình xử lý sự cố 10 phút

Khi nhận một bug report “frontend bị CORS”:

1. **Sao chép URL, method, origin và thời điểm lỗi** từ Network, không lấy chỉ một dòng Console.
2. Kiểm tra lỗi là **network/TLS** hay có HTTP response thật.
3. Nếu có `OPTIONS`, gửi lại bằng `curl` với đúng `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
4. Kiểm tra `Access-Control-Allow-Origin`, methods, headers, credentials và `Vary`; không sửa wildcard bừa.
5. Gửi **actual request** bằng curl để lấy status thật; khi cần dùng cookie/token test, xử lý secrets kín.
6. Nếu `401/403`, tách authentication, authorization, CSRF và CORS processor; giữ nguyên các security controls cần thiết.
7. Nếu `404/405/415/406`, kiểm tra route, method, Content-Type/Accept, context path và controller scan.
8. Nếu `502/503/504`, kiểm tra proxy/gateway upstream, health, timeout, DNS, port và logs.
9. Gọi trực tiếp backend và qua proxy với cùng request để tìm hop thay đổi.
10. Áp dụng bản sửa **đúng tầng**, rồi test cả origin hợp lệ lẫn origin bị từ chối, preflight và actual request.
11. Xác minh browser fetch thực sự đọc được response, không chỉ `curl`.
12. Giữ lại regression test và correlation IDs để sự cố không lặp.

**Bảo đảm tài liệu kiểm thử:** mô tả status/hành vi ở đây áp dụng với ví dụ đã cấu hình rõ. Production có thể khác tùy SecurityFilterChain, middleware, route mapping và reverse proxy. Một request có thể bị chặn ở tầng sớm trước khi chạm tầng vốn sẽ tạo status khác.

## 16. Bài tập tình huống và đáp án

### Tình huống A — POST mất, OPTIONS 401

Frontend gửi JSON POST có Authorization header. Network thấy OPTIONS 401, không có POST.

**Chẩn đoán:** preflight bị auth/proxy từ chối trước khi actual request; thường cần tích hợp CORS trước cơ chế xác thực hoặc cho gateway xử lý OPTIONS đúng. Không gửi session cookie vào preflight để “vượt” lỗi.

### Tình huống B — OPTIONS 200, POST 403

Preflight có Allow-Origin, Allow-Methods và Allow-Headers đúng; actual POST thiếu CSRF token.

**Chẩn đoán:** CORS đã qua. Với cookie session và Spring Security CSRF, 403 rất có thể do token; xem CsrfFilter log. Đừng tắt CSRF nếu app vẫn dựa vào cookie.

### Tình huống C — curl backend 200, browser proxy 404

`curl http://localhost:8080/api/ping` là 200. URL ngoài Nginx `http://localhost:8088/api/ping` là 404.

**Chẩn đoán:** xem `proxy_pass` có trailing slash, ingress rewrite/path prefix và backend URI nhận. Nếu proxy đã đổi `/api/ping` thành `/ping`, CORS không sửa được đường dẫn.

### Tình huống D — Console “CORS”, Network 502

Proxy trả 502 và không có CORS headers; Spring không ghi nhận request trong access log.

**Chẩn đoán:** ưu tiên kiểm tra upstream endpoint/port, service DNS, process state hoặc gateway connection. Browser báo CORS chỉ là lớp che response lỗi.

### Tình huống E — Origin hợp lệ nhưng fetch credentials vẫn bị chặn

Response có `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`.

**Chẩn đoán:** tổ hợp wildcard với credentials không hợp lệ. Dùng Allow-Origin đúng origin được tin cậy; đảm bảo cookie policy cũng phù hợp.

### Tình huống F — Chuyển `mode:"no-cors"` làm hết thông báo nhưng không đọc được response

**Chẩn đoán:** browser trả opaque response. Request không biến thành API JSON dùng được. Phải sửa CORS ở server/proxy hoặc thiết kế kết nối cùng origin.

### Tình huống G — Preflight 200 cho URL không có route

`OPTIONS /api/unknown` được CORS filter cho phép nhưng actual `POST /api/unknown` 404 (nếu vượt qua security).

**Chẩn đoán:** preflight ở filter có thể đi trước routing; một kết quả OPTIONS 200 xác nhận policy method/header, **không xác nhận endpoint tồn tại**.

### Tình huống H — Bị 403 khi gọi bằng Postman, nhưng không có Origin

**Chẩn đoán:** Postman không thực thi browser CORS policy; lỗi nhiều khả năng thuộc auth/authorization/CSRF/gateway, không phải Browser CORS. Xem response/log thật.

### Tình huống I — Spring Boot thấy `http` dù URL người dùng là HTTPS

Gateway terminate TLS và gửi HTTP nội bộ. Backend tạo redirect sai host/scheme.

**Chẩn đoán:** kiểm tra forwarded headers, `server.forward-headers-strategy`, trust boundary và gateway rewrite. Không coi `Origin` hay việc bật CORS là công cụ sửa mọi redirect.

### Tình huống J — SPA và API cùng registrable domain nhưng khác subdomain

`https://app.example.com` gọi `https://api.example.com`.

**Chẩn đoán:** vẫn cross-origin nên cần CORS, dù có thể same-site theo chính sách cookie. Nếu cookie là host-only của app thì API chưa chắc nhận nó; kiểm tra cookie domain/path/credentials riêng.

## 17. Câu hỏi tự đánh giá

1. **CORS và CSRF khác nhau ở đâu?** CORS kiểm soát truy cập response cross-origin từ script browser; CSRF bảo vệ thao tác đổi trạng thái khỏi request giả mạo dùng credentials tự động.
2. **CORS error có chứng minh server không nhận request không?** Không. Server có thể đã xử lý và trả 200/403/500, nhưng browser chặn JS đọc response.
3. **Vì sao preflight thường không cần session cookie?** Browser gửi OPTIONS để hỏi policy trước actual request; security chain cần xử lý CORS trước auth dựa vào cookie.
4. **Preflight 200 có chứng minh route POST đúng không?** Không. CORS filter có thể trả 200 cho path không có handler; actual request vẫn 404/405.
5. **Khi POST 403 mà GET 200, nên xem gì?** CSRF token, authentication/authorization, method/path và logs; không tự động gọi đó là lỗi CORS.
6. **`Access-Control-Allow-Origin: *` có dùng với credentialed request không?** Không. Cần origin cụ thể và `Access-Control-Allow-Credentials: true`.
7. **Hai origin khác nhau chỉ vì port không?** Có. `localhost:5173` và `localhost:8080` là cross-origin.
8. **Vì sao `curl` thành công nhưng browser thất bại?** Curl không thực thi CORS policy của browser và cũng có thể khác cookie, TLS trust hoặc header.
9. **403 có luôn nghĩa CSRF?** Không. CORS processor, authorization, WAF/gateway cũng có thể trả 403.
10. **502 là lỗi Spring controller chắc chắn?** Không. Nó thường do proxy không nhận response upstream hợp lệ, nhưng cần đối chiếu logs.
11. **Nginx `proxy_pass http://backend/;` có thể làm gì với `location /api/`?** Có thể thay prefix `/api/` bằng `/`, gây sai route backend.
12. **`Vary: Origin` có phải authorization?** Không. Nó giúp cache phân biệt response variants theo Origin, không cấp quyền.
13. **`mode:"no-cors"` có giúp đọc API JSON không?** Không. Opaque response không dùng để đọc nội dung bình thường.
14. **Khi Spring Security chặn trước controller, có chắc controller mapping sai không?** Không. Request có thể chưa tới HandlerMapping; phải kiểm tra filter chain.
15. **Spring WebFlux dùng `HttpSecurity` của MVC được không?** Không. WebFlux có `SecurityWebFilterChain` và CORS reactive tương ứng.
16. **Khi frontend gọi API khác origin dùng session cookie, cần xét những gì?** CORS allowlist + credentials, cookie policy, auth/CSRF và proxy/TLS.

## 18. Nguồn tham khảo chính thức

- [Spring Framework — CORS trên Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): preflight/actual requests, `@CrossOrigin`, global CORS mappings, allowed credentials.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): yêu cầu xử lý CORS trước các auth filters; tích hợp `CorsConfigurationSource` với SecurityFilterChain.
- [Spring Security — CSRF protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, token repository, Spring MVC CSRF endpoint, test và BREACH masking.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CORS trong reactive stack.
- [Spring Boot 3.5 — Embedded web servers và forwarded headers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): TLS termination, proxy headers, config.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): Origin, preflight, CORS response headers và credentials.
- [MDN — CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): các lý do browser báo CORS error và cách chẩn đoán.
- [MDN — Fetch credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): cookie, credentialed requests và opaque responses.
- [Nginx — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_pass`, URI rewrite, proxy timeout và upstream errors.
- [Spring Framework — Annotated controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): request mapping và xử lý method/media types.

**Ghi nhớ:** một thông báo “CORS error” là **triệu chứng trên browser**, không phải chẩn đoán root cause. Hãy kiểm tra **OPTIONS hay actual request**, **response/status thật**, **Spring Security (CSRF/auth)**, **HandlerMapping (path/method)** và **reverse proxy (rewrite/upstream)** theo đúng thứ tự. Chỉ khi đã xác định tầng phát lỗi mới sửa CORS policy, CSRF flow, controller hay proxy — không mở wildcard hoặc tắt security để che sai sót.