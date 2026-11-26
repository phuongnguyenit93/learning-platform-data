# Kiểm tra CORS preflight và origin bị từ chối

## Mục tiêu học tập

Bài học thuộc chương **Kiểm thử Servlet** của module **SPRING_SECURITY_HTTP_PROTECTION**. Trọng tâm là kiểm chứng cấu hình CORS tại ranh giới trình duyệt và Spring Security, đặc biệt khi một `OPTIONS` preflight đến trước request thật hoặc khi `Origin` không nằm trong allowlist.

Sau bài học, người học có thể:

1. Phân biệt **same-origin, cross-origin, same-site**, preflight, simple request, actual CORS request và request hoàn toàn không đi qua browser.
2. Xác định khi nào browser tạo preflight dựa trên method, request headers và `Content-Type`; nhận diện `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Diễn giải các header phản hồi `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age`, `Access-Control-Expose-Headers` và `Vary`.
4. Cấu hình `CorsConfigurationSource` và `HttpSecurity.cors()` để xử lý preflight **trước khi yêu cầu authentication**, nhưng không cho phép origin ngoài ý muốn hoặc vô hiệu hóa CSRF.
5. Viết kiểm thử `MockMvc` cho origin được phép, origin bị từ chối, method/header không hợp lệ, credentialed CORS, route ngoài phạm vi, preflight không có cookie và actual request không có authentication.
6. Nhận diện khác biệt giữa response HTTP `403 Invalid CORS request`, `401`, `302 /login`, `403` CSRF và lỗi browser “blocked by CORS policy”.
7. Kiểm tra CORS ở **hai lượt request**: preflight hợp lệ **chưa chứng minh** actual POST sẽ được xác thực, được ủy quyền hoặc có CSRF token hợp lệ.
8. Test reverse proxy/CDN, preflight cache, `Vary`, duplicated CORS headers, forwarded origin/host và cấu hình nhiều `SecurityFilterChain`.
9. Thực hiện browser E2E với origin thật, credentials mode và cookie SameSite; phân biệt kết quả `MockMvc` với hành vi browser.
10. Chỉ ra vì sao **CORS không phải lớp chống CSRF, không phải xác thực hoặc phân quyền API**, và khi nào phải giữ token/session/Origin/Fetch Metadata checks độc lập.

## 1. Bài toán thực tế: trình duyệt hỏi phép trước khi gửi request

Giả định hệ thống có:

~~~text
Frontend SPA:       https://portal.example.net
Spring API Servlet: https://api.example.com
Origin không tin:   https://attacker.example.org
Internal worker:    một Java service gọi backend HTTP trực tiếp
~~~

Trang SPA gọi API để tạo đơn hàng:

~~~javascript
const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: "P-100", quantity: 2 })
});
~~~

Đây là request **cross-origin** vì scheme + hostname + port của SPA khác API. Browser thường gửi một request **preflight OPTIONS** trước để hỏi server có cho phép origin/method/headers đó trong ngữ cảnh CORS không.

~~~mermaid
sequenceDiagram
    participant SPA as Browser tại portal.example.net
    participant API as Spring Servlet API
    SPA->>API: OPTIONS /api/orders
    Note over SPA,API: Origin, Access-Control-Request-Method=POST,<br/>Access-Control-Request-Headers=content-type,x-csrf-token
    API-->>SPA: 200 OK + Access-Control-Allow-* hợp lệ
    SPA->>API: POST /api/orders + session cookie + CSRF header nếu policy cho phép
    API->>API: Authentication, CSRF, authorization, business validation
    API-->>SPA: 201/401/403/422... + CORS response headers
~~~

**Tách rõ hai câu hỏi khác nhau:**

- **CORS preflight:** Trình duyệt có được phép tiến hành một **cross-origin JavaScript request** với method/headers đã công bố không?
- **Spring Security/business:** Actual POST có người dùng hợp lệ, CSRF token đúng và quyền tạo đơn hàng không?

Một preflight thành công không tạo session, không cấp vai trò và không làm POST được miễn `CsrfFilter`.

### 1.1. Tại sao preflight thường không mang cookie?

Preflight do browser thực hiện để thương lượng chính sách CORS, và theo mô hình Fetch, request preflight thông thường **không kèm credential của user**, kể cả khi actual fetch dùng `credentials: "include"`. Vì thế `OPTIONS` có thể đến server mà không có `JSESSIONID` hay `Authorization`.

Nếu tầng authentication đòi cookie trước khi xử lý CORS, server có thể trả `401`/`302` và browser chặn request thật dù origin hợp lệ. Đây là lý do **CORS phải được xử lý trước Spring Security authentication checks** đối với preflight.

Một số browser/platform có khác biệt trong các chi tiết client TLS certificate; không dùng ngoại lệ triển khai để thiết kế “preflight phải có session cookie”.

### 1.2. Mô hình ba lớp

~~~mermaid
flowchart LR
    B[Browser JS tại origin A] --> C{Browser CORS / preflight}
    C -->|Preflight được cho phép| S[Spring Security Filters]
    C -->|Không được cho phép| X[Browser chặn JS request / response]
    S --> A[Authentication]
    A --> T[CSRF và Authorization]
    T --> V[Controller và Service]
~~~

**Lưu ý:** Browser thực hiện kiểm chính sách; server chỉ phát response headers để browser đánh giá. Một HTTP client như `curl`, Java `HttpClient` hoặc Postman không bị browser SOP/CORS hạn chế. Việc `curl` nhận 200 không chứng minh JavaScript từ site attacker đọc được response; ngược lại, việc browser báo CORS error không chứng minh backend đã từ chối mọi side effect.

## 2. Origin, site, CORS và CSRF: bốn khái niệm khác nhau

### 2.1. Origin gồm scheme, host và port

~~~text
https://portal.example.net
https://portal.example.net:8443
http://portal.example.net
https://api.example.com
~~~

Đây là bốn origin khác nhau theo định nghĩa của browser. URL path và query **không phải** thành phần của origin. Request header `Origin` có dạng scheme/host/port (không mang path).

**Site** dùng trong các chính sách cookie như `SameSite` là khái niệm khác, thường dựa trên schemeful registrable domain. Hai subdomain `https://app.example.com` và `https://api.example.com` là **cross-origin**, nhưng có thể **same-site**.

Do đó:

- Cross-origin fetch có thể cần CORS ngay cả khi hai host same-site.
- SameSite cookie policy có thể cho phép cookie ở ngữ cảnh same-site nhưng cookie vẫn phải đúng `Domain`/`Path`.
- CSRF token có thể vẫn cần khi browser tự gửi session cookie, kể cả giữa các subdomain same-site.
- CORS không phải cơ chế kiểm quyền trên từng project/order/user.

### 2.2. Same-origin request không cần CORS

Một trang tại `https://api.example.com` gọi `fetch("/api/orders")` từ chính origin đó không cần cơ chế CORS để đọc response. Nếu trình duyệt gửi `Origin` trên một số same-origin methods, điều đó **không tự biến request thành cross-origin**.

Một unit test gửi `Origin: https://api.example.com` vẫn hữu ích để kiểm cấu hình server, nhưng không thay được test từ một frontend origin thật khác.

### 2.3. CORS chỉ điều khiển khả năng browser JS truy cập cross-origin resources

CORS trả lời liệu JavaScript từ origin A có thể truy cập response của origin B theo phương thức tương ứng. Nó **không** là xác thực user, không cấp `ROLE_USER` và không ngăn mọi loại cross-origin request được gửi.

Một HTML form có thể gửi cross-site POST mà không dùng JavaScript CORS fetch; với credential cookie cho phép, request có thể tới server. Việc JS attacker không đọc response **không ngăn** server đã thực thi update nếu endpoint thiếu CSRF.

### 2.4. Browser, curl và M2M khác nhau

| Client | Có thực thi browser CORS không? | Cần kiểm gì ở server? |
|---|---|---|
| Browser SPA dùng `fetch` cross-origin | Có | CORS, authentication, CSRF khi dùng cookie, authorization |
| Browser form submit cross-site | Không qua CORS preflight thông thường | CSRF/token, session cookie, business authz |
| Browser top-level 302 navigation | Không cần CORS để điều hướng | Redirect URI, session, giao thức auth |
| Java backend HTTP client | Không | Credential/token validation, TLS, authorization |
| Postman/curl | Không | Cùng server validations như backend clients |
| Webhook server-to-server | Không | Signature/replay/idempotency, không coi Origin là auth |

**Định nghĩa mục tiêu kiểm thử:** ở bài này, ta muốn chứng minh server cung cấp policy CORS **chỉ cho frontend được duyệt**, browser thực hiện policy đó, và security filters vẫn thực thi với request thật.

## 3. Preflight là gì và khi nào browser tạo?

### 3.1. Request `OPTIONS` có bộ ba header nhận diện

Ví dụ preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://portal.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Ý nghĩa:

- **`Origin`:** origin của JavaScript context phát request.
- **`Access-Control-Request-Method`:** method của **actual request sẽ được gửi**, không phải method của preflight.
- **`Access-Control-Request-Headers`:** tên các non-safelisted/request headers browser dự định gửi (ví dụ `content-type`, `x-csrf-token`); có thể vắng nếu không cần.
- **`OPTIONS`:** method của preflight, **không phải** method mà controller tạo đơn hàng nên xử lý.

Spring và browser nhận diện một CORS preflight dựa trên `OPTIONS` + `Origin` + `Access-Control-Request-Method`. Một `OPTIONS` không có đủ các header ấy không mặc định là CORS preflight.

### 3.2. Ví dụ các request thường kích hoạt preflight

| Actual request từ browser JS | Thường có preflight? | Lý do |
|---|---|---|
| `GET` với headers safelisted, request đơn giản | Thường không | Method/header đủ điều kiện CORS-safelisted |
| `HEAD` với headers safelisted | Thường không | Method safelisted |
| `POST` với `Content-Type: application/x-www-form-urlencoded` và headers safelisted | Thường không | Method/header safelisted, còn phụ thuộc chi tiết request |
| `POST` với `Content-Type: text/plain` | Thường không | Content type safelisted theo ràng buộc Fetch |
| `POST` với `Content-Type: multipart/form-data` | Thường không | Có điều kiện safelisted; browser tạo boundary đúng |
| `POST` với `Content-Type: application/json` | **Có** | JSON không là CORS-safelisted content type |
| `POST` với `X-CSRF-TOKEN` | **Có** | Custom request header không safelisted |
| `GET` với `Authorization: Bearer ...` | **Có** | Authorization header không safelisted |
| `PUT`/`PATCH`/`DELETE` | **Có** | Method không safelisted |
| `GET` thêm `X-Request-ID` | **Có** | Custom header không safelisted |
| `POST` dùng credential cookie nhưng không có non-safelisted method/headers | **Không phải vì cookie mà preflight** | Credentials mode không tự kích hoạt preflight |

Đây là các kết luận thông thường; tiêu chuẩn Fetch còn điều kiện chi tiết về header values, content type, request mode và các tình huống như CORS-unsafe request-header names. **Không viết logic server giả định tất cả POST đều preflight.**

### 3.3. Server không nên “tự preflight” thay browser

Server nhận một `OPTIONS` và kiểm allowed origin/method/headers. Request thật **có thể không được gửi** nếu browser không chấp nhận response, nhưng attacker dùng client không bị CORS ràng buộc vẫn có thể gọi API.

Vì thế không lấy số lượng OPTIONS requests làm số lượng users được cấp quyền; không tạo đơn hàng, khởi tạo thanh toán hay gọi business service trong preflight.

### 3.4. Diagram preflight và actual request

~~~mermaid
sequenceDiagram
    participant JS as SPA JavaScript
    participant Browser as Browser CORS engine
    participant Filter as CorsFilter / Security CORS
    participant Auth as Spring Security & controller

    JS->>Browser: fetch POST JSON với X-CSRF-TOKEN
    Browser->>Filter: OPTIONS Origin + Request-Method + Request-Headers
    Filter->>Filter: Check origin, method, headers, credentials
    alt Policy cho phép
        Filter-->>Browser: 200 + Allow-Origin/Methods/Headers
        Browser->>Auth: POST JSON + Cookie/CSRF nếu hợp lệ
        Auth-->>Browser: HTTP 201/401/403 + CORS policy
        Browser-->>JS: Response hoặc CORS failure
    else Policy từ chối
        Filter-->>Browser: 403 / không có CORS allow headers
        Browser-->>JS: TypeError / CORS error; không gửi actual POST
    end
~~~

Ở một request **không cần preflight**, browser có thể gửi actual request ngay; nếu origin không được cho phép, backend vẫn có thể xử lý request trước khi browser quyết định **không cho JS đọc response**. Đây là ranh giới cần ghi nhớ để thiết kế CSRF và server authorization.

## 4. Phản hồi CORS preflight hợp lệ

### 4.1. HTTP example với frontend được duyệt

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.net
Access-Control-Allow-Methods: GET,POST,PATCH,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Status có thể là `200` hoặc một status thành công khác tùy CORS processor/server. Điều browser quan tâm là response thỏa CORS protocol, chứ **không bắt buộc đúng một status cố định**. Spring `CorsFilter` thường trả `200` cho preflight hợp lệ.

`Access-Control-Allow-Credentials: true` chỉ có ý nghĩa khi ứng dụng cho phép credentialed cross-origin request; nó không làm preflight tự mang cookie.

### 4.2. Ý nghĩa từng response header

| Header | Mục đích | Điều dễ sai |
|---|---|---|
| `Access-Control-Allow-Origin` | Origin được phép đọc response | Không dùng `*` cùng credentialed CORS |
| `Access-Control-Allow-Methods` | Actual methods được browser cho phép sử dụng | Đừng chỉ cho `OPTIONS` mà bỏ `POST` cần thiết |
| `Access-Control-Allow-Headers` | Request header names được phép trên actual request | Quên `Content-Type`, `Authorization` hay `X-CSRF-TOKEN` |
| `Access-Control-Allow-Credentials` | Cho phép cross-origin credentialed response khi set `true` | Không cấp phép user/role; credential vẫn phải hợp lệ |
| `Access-Control-Max-Age` | Gợi ý thời gian cache kết quả preflight | Browser áp giới hạn riêng; policy thay đổi có thể chưa thấy ngay |
| `Access-Control-Expose-Headers` | Cho JS đọc các response headers ngoài safelisted headers của **actual response** | Không phải header bắt buộc ở preflight |
| `Vary` | Giúp caches phân biệt phản hồi theo `Origin`, requested method/headers | Proxy gộp/sửa/strip Vary gây cache nhầm policy |

### 4.3. Không nhầm allow-header với expose-header

- `Access-Control-Allow-Headers: X-CSRF-TOKEN`: browser có thể **gửi** request header `X-CSRF-TOKEN` trong actual request sau preflight.
- `Access-Control-Expose-Headers: X-Request-ID`: JavaScript từ frontend có thể **đọc** header `X-Request-ID` từ actual response nếu CORS hợp lệ.

Hai danh sách giải quyết **hai chiều dữ liệu khác nhau**. Không đưa `Set-Cookie` vào exposed headers rồi mong JavaScript đọc được: `Set-Cookie` là forbidden response header name, browser không cho frontend JS truy cập theo cách đó.

### 4.4. Credentialed CORS cần origin cụ thể

Với `credentials: "include"` và phiên cookie, response actual phải chứa `Access-Control-Allow-Origin` là **origin cụ thể khớp request**, cùng `Access-Control-Allow-Credentials: true`; wildcard `*` không hợp lệ cho credentialed response.

~~~http
# Không hợp lệ cho JS credentialed fetch:
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

CORS chỉ cho frontend từ origin đó **đọc response bằng JS**. Session cookie còn phải thỏa `Domain`, `Path`, `Secure`, `SameSite` và browser third-party cookie policy. Response header `Access-Control-Allow-Credentials` **không ép browser gửi cookie** bất chấp SameSite.

### 4.5. Vary là bắt buộc phải xét khi cache phản hồi theo Origin

Nếu API cho phép hai frontend `portal.example.net` và `admin.example.net`, server có thể trả `Access-Control-Allow-Origin` khác nhau dựa trên `Origin`. Một shared cache không phân biệt Origin có thể phục vụ response header hoặc nội dung sai client.

CORS processor thường thêm `Vary: Origin` và có thể có `Access-Control-Request-Method` / `Access-Control-Request-Headers`. Kiểm tại **public edge** sau proxy/CDN, không chỉ trong MockMvc. Với private user data, còn phải kiểm `Cache-Control` và cache keys theo authentication/tenant; **Vary không thay kiểm quyền**.

## 5. Preflight bị từ chối: origin, method và headers là ba nguyên nhân khác nhau

### 5.1. Origin không nằm trong allowlist

Ví dụ attacker đưa JavaScript từ `https://attacker.example.org`:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://attacker.example.org
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Với Spring CORS processor mặc định và một cấu hình origin allowlist không chứa origin này, kết quả thường là:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/plain

Invalid CORS request
~~~

Thông điệp cụ thể, status và các header khác có thể thay đổi theo Spring version, proxy hoặc custom `CorsProcessor`. Mục tiêu test ổn định là **không cấp `Access-Control-Allow-Origin: https://attacker.example.org`** và browser **không được cho phép gửi actual request dựa trên preflight đó**.

**Đừng chỉ assert status 403 mà bỏ qua header:** Một proxy có thể trả 200 với CORS allow header thiếu; browser vẫn chặn. Một server khác có thể từ chối theo cách khác. Với bài test dùng đúng Spring `DefaultCorsProcessor` và cấu hình cụ thể, status `403` là assertion hữu ích.

### 5.2. Origin đúng nhưng method không được phép

Server chỉ cho `GET` và `POST` tại route này. Browser hỏi:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://portal.example.net
Access-Control-Request-Method: DELETE
~~~

Dù `Origin` hợp lệ, method **DELETE** không nằm trong policy dành cho route đó; preflight phải bị từ chối. Không tự động thêm mọi HTTP method chỉ vì frontend “dùng REST”.

Cần test **method mà browser dự định gửi** ở `Access-Control-Request-Method`. Việc OPTIONS được xử lý hợp lệ không đồng nghĩa allowed-methods phải chứa OPTIONS; trình duyệt hỏi cho actual method.

### 5.3. Origin và method đúng nhưng request headers không hợp lệ

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://portal.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-admin-override
~~~

Nếu allowlist chỉ gồm `Content-Type`, `X-CSRF-TOKEN` và `X-Request-ID`, header `X-Admin-Override` phải bị chặn ở preflight.

**Lưu ý:** CORS header allowlist không thay kiểm authorization nghiệp vụ. Kể cả một attacker không dùng browser có thể tự gửi `X-Admin-Override`, server vẫn phải **không tin header đó là quyền admin**.

### 5.4. Origin "null" và origin sai cú pháp

Browser có thể gửi:

~~~http
Origin: null
~~~

trong một số ngữ cảnh opaque origin, sandboxed iframe, `file:` và môi trường đặc biệt. `null` không phải một hostname “an toàn vì không có domain”; nếu origin null được allow, nhiều context không liên quan có thể đạt cùng giá trị. Mặc định **không đưa `"null"` vào allowed origins** trừ khi có nhu cầu thật, threat model, authz và kiểm thử cụ thể.

Các origin kỳ lạ như `https://portal.example.net.evil.invalid`, origin có port khác hoặc scheme `http` khác `https` cũng phải bị từ chối nếu policy chỉ cho exact `https://portal.example.net`.

### 5.5. Các case dễ gây false positive

| Kiểm thử | Kết luận đúng | Sai lầm cần tránh |
|---|---|---|
| OPTIONS không có `Origin` | Không là CORS preflight chuẩn | Gọi mọi OPTIONS là preflight |
| OPTIONS có `Origin` nhưng không có `Access-Control-Request-Method` | Có thể là CORS actual-style OPTIONS tùy request, không là preflight | Assert chắc chắn phải trả Allow-Methods |
| `Origin: https://portal.example.net` + method DELETE | Origin pass, method fail | Chỉ kiểm allow-origin |
| `Origin: https://attacker.example.org` + method POST | Origin fail | Chỉ kiểm status nhưng response lại có ACAO attacker |
| `Origin: null` | Không tin mặc định | Cho phép vì không có host |
| `Origin: https://portal.example.net:8443` | Khác origin chuẩn 443 | Dùng `startsWith` để allow |
| `Origin: http://portal.example.net` | Khác scheme | Cho phép cả HTTP và HTTPS tùy tiện |
| `Origin: https://sub.portal.example.net` | Khác host | Cho wildcard subdomain không cần thiết |

## 6. Spring Security Servlet: vị trí thực thi CORS so với Security Filter Chain

### 6.1. Preflight cần được xử lý trước authentication

Luồng Spring Boot Servlet phổ biến:

~~~mermaid
flowchart TD
    A[Servlet container] --> P{Reverse proxy/WAF có xử lý OPTIONS?}
    P -->|Forward| S[Spring Security FilterChainProxy]
    S --> C[Spring CORS integration]
    C -->|Preflight hợp lệ| R[Trả CORS response, không gọi controller]
    C -->|Preflight không hợp lệ| X[Từ chối theo CorsProcessor]
    C -->|Actual browser request| F[Authn + CsrfFilter + authorization]
    F --> D[DispatcherServlet -> Controller/Service]
    P -->|Proxy trả trước| E[Response của proxy; Spring không xử lý]
~~~

Spring Security documentation khuyến nghị **CORS phải được xử lý trước Spring Security**, bởi preflight không mang session cookie. Cấu hình `http.cors(Customizer.withDefaults())` với `CorsConfigurationSource` thích hợp để tích hợp xử lý CORS trong chuỗi bảo mật.

**Không cần phải** thêm `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` trên toàn ứng dụng để CORS hoạt động khi filter CORS đã đứng đúng vị trí. PermitAll cho OPTIONS **không tự sinh** `Access-Control-Allow-Origin` hoặc kiểm requested method/headers.

### 6.2. Thứ tự logic

~~~text
Browser OPTIONS preflight
  -> CORS policy kiểm Origin + requested method/headers
  -> nếu valid: CORS processor xử lý và kết thúc OPTIONS
  -> không đòi JSESSIONID/Bearer/CSRF
  -> browser có thể quyết định gửi actual request

Browser POST actual request
  -> CORS policy cho phép origin (đối với browser)
  -> Spring Security filters kiểm CSRF và authentication
     (thứ tự filter thực tế có thể để CsrfFilter chặn trước auth)
  -> AuthorizationFilter/service kiểm quyền nếu request đi tiếp
  -> Controller xử lý và phản hồi.
~~~

Filter order chi tiết thay đổi theo Spring version và chain; nhưng **hợp đồng cần kiểm** là preflight hợp lệ được xử lý trước khi bị yêu cầu authentication. Một HTTP response CORS hợp lệ ở preflight **không chứng minh** actual request đã được phép theo authz.

### 6.3. Vì sao `OPTIONS permitAll` có thể che lỗi?

Ví dụ cấu hình chưa có CORS processor:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
    .anyRequest().authenticated()
)
~~~

Nó có thể khiến `OPTIONS` qua authorization, nhưng browser vẫn cần **đúng Access-Control-Allow-* headers**. Kết quả có thể 200/404/405 từ framework hoặc controller mà không có ACAO, nên browser chặn.

Ngược lại, nếu CORS filter từ chối origin, thêm permitAll cho OPTIONS **không nên** biến origin attacker thành được phép. Cần sửa allowlist/configuration và thứ tự lọc đúng, không mở quá rộng.

### 6.4. Đừng gắn CorsFilter trùng lặp thiếu kiểm soát

Có thể cấu hình CORS ở:

- `CorsConfigurationSource` kết hợp `HttpSecurity.cors()`;
- MVC `WebMvcConfigurer.addCorsMappings` / `@CrossOrigin` theo controller;
- Một `CorsFilter` bean hoặc filter registration riêng;
- API gateway/reverse proxy/CDN.

Nếu nhiều nơi cùng ghi headers, response có thể chứa **hai `Access-Control-Allow-Origin`** hoặc policy mâu thuẫn. Browser có thể từ chối duplicate ACAO, dù developer tưởng “allowlist đã đúng”.

Chọn **owner của chính sách rõ ràng**. Nếu Spring Security tự sử dụng MVC configuration, test đúng route + filter chain; nếu gateway xử lý preflight trước, cần integration test gateway và xác nhận Spring vẫn bảo vệ actual requests.

## 7. Cấu hình Servlet hoàn chỉnh theo origin allowlist

### 7.1. Ví dụ có Cookie session và Spring CSRF

Giả định ứng dụng web browser dùng session cookie; frontend `https://portal.example.net` gọi `/api/**` trên backend `https://api.example.com`, cần credentials và CSRF token riêng cho unsafe requests.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chỉ frontend được duyệt; scheme/host/port phải khớp.
        cors.setAllowedOrigins(List.of(
            "https://portal.example.net"
        ));

        // Chỉ business methods thật sự được dùng.
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PATCH"
        ));

        // Headers mà frontend thực sự gửi.
        cors.setAllowedHeaders(List.of(
            "Content-Type",
            "X-CSRF-TOKEN",
            "X-Request-ID"
        ));

        // Header response mà JavaScript được đọc.
        cors.setExposedHeaders(List.of("X-Request-ID"));

        // Cho browser credentialed fetch từ origin cụ thể.
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Browser dựa trên session cookie: giữ CSRF.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích các giả định:**

- `CorsConfigurationSource` là bean Spring Security có thể sử dụng khi gọi `http.cors(withDefaults())`.
- Chính sách chỉ được đăng ký `/api/**`; không cần mở CORS cho mọi trang HTML/login/management routes.
- Origin hợp lệ là **`https://portal.example.net` chính xác**; `https://attacker.example.org` không được phép.
- Methods chỉ GET/POST/PATCH, nên test DELETE bị từ chối.
- Headers hợp lệ gồm `Content-Type`, `X-CSRF-TOKEN` và `X-Request-ID`, nên test `X-Admin-Override` bị từ chối.
- `setAllowCredentials(true)` không tạo session và không cấp authentication. RP phải thiết kế cookie `Secure; HttpOnly; SameSite` phù hợp cross-site browser requests, CSRF token bootstrap và authorization.
- Các endpoint thật `/api/orders`, `/api/orders/{id}` và controller fixtures **không được tự động tạo** bởi security config.
- `formLogin` tạo login entrypoints thích hợp trong web app, nhưng actual XHR không authenticated có thể nhận redirect tùy entrypoint; nếu API muốn `401 JSON`, phải cấu hình authentication entry point theo route.
- Cấu hình này **không đồng thời là cấu hình cho M2M Bearer-only**; nếu hệ thống dùng cả hai, cần tách chains và credential contract rõ.

### 7.2. Vì sao không dùng wildcard origin với credentials?

Sai:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
~~~

Spring `CorsConfiguration` có kiểm tra cấu hình và có thể từ chối `allowedOrigins("*")` kết hợp `allowCredentials(true)`; browser cũng không chấp nhận `ACAO: *` trong credentialed requests.

Khi nhiều origins được duyệt, liệt kê cụ thể:

~~~java
cors.setAllowedOrigins(List.of(
    "https://portal.example.net",
    "https://admin.example.net"
));
~~~

Nếu sử dụng `setAllowedOriginPatterns` cho môi trường nhiều subdomains, pattern phải được quản trị chặt và kiểm test negative. `*.example.net` có thể tin nhầm subdomain do đối tác/attacker kiểm soát; không dùng pattern chỉ để tiện tránh cập nhật allowlist.

### 7.3. Case-sensitive và exact origin matching

Origin gồm scheme + host + port. `https://portal.example.net` khác:

~~~text
http://portal.example.net          # khác scheme
https://portal.example.net:8443    # khác port
https://portal.example.net.evil.invalid
https://sub.portal.example.net     # khác host
null                                # opaque origin
~~~

Không tự viết:

~~~java
if (origin.startsWith("https://portal.example.net")) {
    // Sai: attacker origin có prefix tương tự!
}
~~~

Để Spring CORS processor xử lý `allowedOrigins` exact allowlist. Nếu tổ chức cần dynamic tenant origins, chỉ nạp từ dữ liệu đã kiểm soát và audit; không phản chiếu `Origin` bất kỳ theo request.

### 7.4. CORS config trên nhiều security chains

Một app có `/api/browser/**` dùng cookie session và `/api/m2m/**` dùng Bearer-only:

- Browser route có thể cấp CORS cho portal và giữ CSRF.
- M2M route không cần CORS nếu chỉ có backend workers; nếu cũng có SPA JS Bearer API, phải đánh giá policy riêng.
- `HttpSecurity.cors()` cần được áp ở chain **khớp route**, không chỉ một chain khác.
- `securityMatcher` và `@Order` quyết định chain nào được chọn; chain đầu tiên match sẽ xử lý request.
- Một `OPTIONS /api/browser/orders` có thể vào chain sai nếu matcher chỉ kiểm POST; kiểm matcher thực tế cho OPTIONS.
- Đừng cấu hình permitAll cho `/**` hay bỏ CSRF trên toàn ứng dụng chỉ vì preflight bị 401.

### 7.5. Gợi ý cấu hình cho nhiều CORS origins mà không mở rộng quyền

Đối với SPA khác môi trường, tạo config theo môi trường đã được duyệt (local dev/production), không cho `Origin: http://localhost:3000` vào production nếu không có lý do. Nếu có, ghi rõ risk, hạn chế route/user data và kiểm bảo vệ từ origin local.

**Không** dựa vào hostname CORS như “đối tác” để map role/tenant: một site bị xâm nhập hoặc XSS trên allowed origin vẫn có thể gửi requests với browser credentials trong phạm vi người dùng, và backend phải kiểm authentication, CSRF, resource ACL.

## 8. Cookie, credentials và CSRF trên actual request

### 8.1. AllowCredentials không ép browser gửi Cookie

Để cross-site credentialed fetch thực sự mang session cookie:

- JavaScript request dùng `credentials: "include"` nếu khác origin.
- Cookie đúng `Domain`/`Path`/`Secure` và chưa hết hạn.
- Với cross-site subresource/fetch, `SameSite=Lax/Strict` thường **không gửi**; `SameSite=None; Secure` là điều kiện cần trong nhiều mô hình, nhưng chưa đủ nếu browser chặn third-party cookies.
- Cookie không thể được đọc bởi JavaScript nếu `HttpOnly`; điều đó không ngăn browser gửi cookie.
- Server phải trả allowed origin/credentials headers đúng nếu muốn browser JS đọc credentialed response.

### 8.2. Ví dụ status khác nhau sau preflight pass

Sau khi preflight hợp lệ, actual POST có thể:

| Actual POST | Kết quả server | Ý nghĩa |
|---|---|---|
| Không có session, nhưng CSRF token hợp lệ hoặc request không cần CSRF | `401` hoặc `302 /login` theo entrypoint | CORS pass, authentication chưa có |
| Không có session và cũng thiếu CSRF trên unsafe POST | Có thể `403` từ CsrfFilter trước auth entrypoint | Phải phân biệt lỗi CSRF với lỗi authentication |
| Có session, thiếu CSRF token | Thường `403` | CSRF chặn |
| Có CSRF đúng, user không có quyền tạo order | `403`/`404` theo policy | Authorization chặn |
| User đủ quyền, payload không hợp lệ | `400`/`422` | Business validation chặn |
| User đủ quyền, CSRF đúng, payload hợp lệ | `201` | Controller/service xử lý |
| Browser fetch bị chặn đọc response do thiếu ACAO ở error handler | JS báo CORS error dù backend đã trả status | Response policy trên error paths chưa đồng nhất |

**Preflight success ≠ API success.** Test phải quan sát cả hai request và response phù hợp; đừng biến `/api/orders` thành `permitAll()` để “CORS hết lỗi”.

### 8.3. Token CSRF header có thể kích hoạt preflight

Một SPA session-based đọc CSRF token từ bootstrap endpoint hoặc cookie repository được thiết kế đúng, rồi gửi:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: "P-100" })
});
~~~

`X-CSRF-TOKEN` là **non-safelisted request header**, do đó preflight có thể hỏi quyền gửi nó. Nhưng việc Spring CORS cho phép header name đó **không kiểm giá trị CSRF token**. `CsrfFilter` mới so submitted token và expected repository sau preflight trên actual POST.

### 8.4. Token CSRF không được lưu chung với OAuth state

Một SPA/Servlet RP có thể dùng OAuth/OIDC login với `state`/nonce/PKCE trên callback, rồi tạo browser session. Những token giao thức login **không thay** CSRF token của POST nghiệp vụ. Khi callback OIDC fail state, sửa repo/cookie/redirect; khi POST thiếu CSRF, sửa token bootstrap/handler/session. Không bật `csrf.disable()` để chữa CORS preflight.

### 8.5. Cookie API và double-submit cần được thiết kế đúng

Nếu dùng `CookieCsrfTokenRepository` để SPA đọc CSRF cookie, Spring Security có thể dùng request handlers khác nhau cho raw cookie token và masked form token (chống BREACH). Các ví dụ Spring Security hiện đại có cách cấu hình dành riêng cho SPA; cần test HTTP request token và callback thực tế theo version. **Không** dùng `HttpOnly=false` cho session cookie; nếu cần JS đọc CSRF cookie, điều đó chỉ áp vào **cookie lưu CSRF token**, không phải session ID.

## 9. Thiết kế bộ kiểm thử CORS Servlet bằng MockMvc

### 9.1. Phân chia test theo tầng

Không nên gộp mọi thứ thành một assertion “OPTIONS trả 200”. Nên có các nhóm:

1. **Contract CORS preflight:** origin/method/headers/credentials/Max-Age/Vary, không cần authenticated user.
2. **Contract actual CORS response:** origin được phép có ACAO/ACAC trên GET/POST tương ứng, kể cả 401/403 nếu security/proxy thực thi.
3. **Authentication và CSRF:** preflight pass không giúp POST thiếu session/CSRF được phép.
4. **Authorization nghiệp vụ:** user đủ CSRF nhưng sai role/tenant vẫn không được ghi dữ liệu.
5. **Browser integration:** browser có thực sự tạo preflight, giữ credentials, kiểm CORS, cookie SameSite và cache không?
6. **Public edge:** ingress/CDN/WAF có forward OPTIONS và giữ `Vary`/ACAO đúng hay không?

`MockMvc` rất phù hợp cho nhóm 1–4 trên Spring MVC/Security, **nhưng không là trình duyệt** và không tự quyết định có tạo OPTIONS trước POST hay không.

### 9.2. Dependency kiểm thử

Một Spring Boot Servlet test profile thường có:

~~~text
spring-boot-starter-test
spring-security-test
~~~

Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để nạp `SecurityFilterChain` và `CorsConfigurationSource` thật, không mock `CorsFilter`/CSRF filter. Nếu dùng `@WebMvcTest`, phải import chính xác security/CORS configuration cần test; nếu bỏ sót, kết quả có thể là test MVC slice **không chứa policy production**.

### 9.3. Dựng preflight bằng request headers

Code lõi:

~~~java
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD;
import static org.springframework.http.HttpHeaders.ORIGIN;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

mvc.perform(options("/api/orders")
        .header(ORIGIN, "https://portal.example.net")
        .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .header(
            ACCESS_CONTROL_REQUEST_HEADERS,
            "content-type,x-csrf-token"));
~~~

**Không** gọi `.with(user("alice"))`, `.with(csrf())` hoặc gửi `JSESSIONID` vào preflight khi mục tiêu là mô phỏng browser tiêu chuẩn. Một preflight hợp lệ phải được xử lý **ngay cả khi không có session cookie**.

### 9.4. Bộ test preflight cho origin hợp lệ

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_MAX_AGE;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD;
import static org.springframework.http.HttpHeaders.ORIGIN;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightAllowedTests {

    @Autowired MockMvc mvc;

    @Test
    void allowedOriginPostAndHeadersPassWithoutCookie()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(ORIGIN, "https://portal.example.net")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(
                    ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://portal.example.net"))
            .andExpect(header().string(
                ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                ACCESS_CONTROL_ALLOW_HEADERS,
                containsString("x-csrf-token")))
            .andExpect(header().string(
                ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().string(
                ACCESS_CONTROL_MAX_AGE, "600"));
    }

    @Test
    void allowlistedGetPreflightAlsoSucceeds()
            throws Exception {

        // GET chỉ cần preflight nếu request JS có
        // non-safelisted headers hoặc điều kiện tương ứng.
        mvc.perform(options("/api/orders")
                .header(ORIGIN, "https://portal.example.net")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(ACCESS_CONTROL_REQUEST_HEADERS,
                    "x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://portal.example.net"));
    }
}
~~~

Các assertions sử dụng đúng **cấu hình chương 7** và default Spring `CorsProcessor`. Nếu ứng dụng thay `CorsConfigurationSource`, origins/headers/methods/status phải cập nhật theo hợp đồng mới; **không làm test pass bằng cách mở wildcard**.

### 9.5. Kiểm `Vary` không phụ thuộc định dạng một dòng

`Vary` có thể được trả ở nhiều dòng hoặc một dòng phân tách dấu phẩy theo proxy/servlet API. Không nên chỉ so toàn bộ header bằng một chuỗi cứng. Ví dụ:

~~~java
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.http.HttpHeaders.VARY;

// Sau mvc.perform(...).andReturn():
MvcResult result = mvc.perform(options("/api/orders")
        .header(ORIGIN, "https://portal.example.net")
        .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .header(ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
    .andExpect(status().isOk())
    .andReturn();

String vary = String.join(",",
    result.getResponse().getHeaders(VARY));

assertTrue(vary.contains("Origin"));
assertTrue(vary.contains("Access-Control-Request-Method"));
assertTrue(vary.contains("Access-Control-Request-Headers"));
~~~

Đây là **trích đoạn đặt trong test method**, không phải Java class độc lập. Trong môi trường proxy/CDN, kiểm `Vary` ở public HTTP response nữa.

### 9.6. Cần test cả HEAD và PATCH?

Nếu allowed methods gồm `GET`, `POST`, `PATCH`, nên test **PATCH** được cho phép và **DELETE** bị từ chối. `HEAD` không tự được cho phép chỉ vì `GET` được permit ở security matcher; `CorsConfiguration` và controller semantics cần rõ. Nếu client dùng HEAD, liệt kê/cấu hình và test theo hợp đồng thực.

### 9.7. Phân biệt “không có cookie” và “không có headers”

Preflight có **Origin + Access-Control-Request-Method**, nhưng không cần Cookie. Một preflight có thể không có `Access-Control-Request-Headers` nếu actual request không dùng headers cần hỏi trước. Đừng viết filter nội bộ yêu cầu `X-CSRF-TOKEN` có trên **OPTIONS**; token CSRF được gửi trên **actual POST** khi browser đã được phép gửi custom header.

## 10. MockMvc: origin bị từ chối

### 10.1. Test exact origin không có trong allowlist

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN;
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD;
import static org.springframework.http.HttpHeaders.ORIGIN;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightDeniedOriginTests {

    @Autowired MockMvc mvc;

    @Test
    void rejectsUnknownOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header(ORIGIN, "https://attacker.example.org")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void rejectsLookalikeHost() throws Exception {
        mvc.perform(options("/api/orders")
                .header(ORIGIN,
                    "https://portal.example.net.evil.invalid")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void rejectsDifferentScheme() throws Exception {
        mvc.perform(options("/api/orders")
                .header(ORIGIN, "http://portal.example.net")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void rejectsUnexpectedPort() throws Exception {
        mvc.perform(options("/api/orders")
                .header(ORIGIN,
                    "https://portal.example.net:8443")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void rejectsOpaqueNullOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header(ORIGIN, "null")
                .header(ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

Test này mô tả behavior của default Spring CORS processor trên `/api/**`. Nếu backend không có CORS config cho path, Spring/security/proxy có thể phản hồi khác; assertion phải bám **contract deployment**, nhưng tiêu chí cốt lõi vẫn là attacker origin **không được cấp phép**.

### 10.2. Test không chỉ origin mà còn method/header

~~~java
import static org.springframework.http.HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS;

@Test
void deniesDisallowedDeleteMethod() throws Exception {
    mvc.perform(options("/api/orders")
            .header(ORIGIN, "https://portal.example.net")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(
            ACCESS_CONTROL_ALLOW_ORIGIN));
}

@Test
void deniesUnexpectedCustomHeader() throws Exception {
    mvc.perform(options("/api/orders")
            .header(ORIGIN, "https://portal.example.net")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-admin-override"))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(
            ACCESS_CONTROL_ALLOW_ORIGIN));
}
~~~

Đặt hai methods này vào một test class đã có `@Autowired MockMvc mvc` và static imports tương ứng.

**Quan trọng:** Bị CORS từ chối vì `x-admin-override` không có nghĩa server có kiểm quyền “admin override”; controller/service vẫn phải bỏ qua hoặc chặn một header tự khai nếu client không tin cậy.

### 10.3. Không dùng suffix allowlist tự chế

Nếu bạn tự viết policy:

~~~java
boolean allow = origin.endsWith("example.net");
~~~

có thể nhầm `https://evil-example.net` hoặc các hostname tương tự tùy điều kiện. Dùng exact origins hoặc một pattern đã kiểm chặt; test các host nhìn giống, scheme/port khác, subdomain tùy ý và origin null.

### 10.4. Test `Origin` header bị giả không chứng minh xác thực

Một HTTP client ngoài browser có thể tự gửi:

~~~http
Origin: https://portal.example.net
~~~

nên không được dùng `Origin` như một credential hay kiểm user role. Nó là tín hiệu browser/CORS, có thể dùng như lớp kiểm bổ sung trong CSRF defense-in-depth nếu được thiết kế đúng nhưng **không thay signed token/session authz**.

## 11. MockMvc: OPTIONS không phải preflight và route ngoài policy

### 11.1. OPTIONS thiếu bộ header preflight

~~~java
mvc.perform(options("/api/orders"))
    // Tùy auth/filter/controller, có thể 302/401/403/200/405.
    // Không nên hardcode status nếu mục tiêu là phân loại request.
    .andReturn();
~~~

Mục tiêu là kiểm request này **không tự được cấp CORS policy cho một origin nào**. Nếu hệ thống có custom OPTIONS handler hoặc API gateway special behavior, test theo hợp đồng cụ thể. Đừng cho `OPTIONS` permitAll toàn app chỉ để test “không có Origin” trả 200.

### 11.2. OPTIONS có Origin nhưng thiếu requested method

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://portal.example.net
~~~

Đây **không phải preflight tiêu chuẩn** vì thiếu `Access-Control-Request-Method`. CORS processor có thể xử lý nó khác với preflight và có thể cho actual-style CORS headers hoặc chuyển tiếp vào chain tùy config/stack. Vì vậy không assert nó “phải trả 403” như preflight denied.

### 11.3. Route ngoài `/api/**`

Cấu hình ví dụ chỉ đăng ký CORS policy cho `/api/**`. Khi request là:

~~~http
OPTIONS /admin/users HTTP/1.1
Origin: https://portal.example.net
Access-Control-Request-Method: DELETE
~~~

Spring có thể không có `CorsConfiguration` cho route này, hoặc security chain khác/proxy xử lý nó. Điều cần kiểm là **không cấp phép CORS cho /admin/** ngoài chủ đích. Nếu hệ thống cần invariant “mọi preflight ngoài /api/** trả 403”, hãy cấu hình explicit reject/route policy và kiểm thực tế, không suy từ `registerCorsConfiguration("/api/**", cors)` rằng mọi path khác chắc chắn 403.

### 11.4. OPTIONS không là request nghiệp vụ

Controller `@PostMapping("/api/orders")` không được gọi chỉ vì browser hỏi preflight cho POST. Nếu test fixture có counter hoặc mock service, hãy assert:

~~~text
OPTIONS /api/orders với Origin hợp lệ
  -> response CORS
  -> orderService.create(...) calls = 0

OPTIONS /api/orders với Origin attacker
  -> denied CORS
  -> orderService.create(...) calls = 0
~~~

Bộ test này giúp phát hiện custom filter/controller đã triển khai side effect trên OPTIONS hoặc lệch method semantics.

## 12. Actual CORS request: authentication, CSRF và authorization tách biệt

### 12.1. Không phải actual request nào cũng đi qua preflight

Một JavaScript `GET` safelisted có thể đi **thẳng** tới server, không có OPTIONS. Một cross-origin HTML form submit cũng có thể được gửi mà không cần browser preflight CORS. Vì vậy **CORS không bảo đảm attacker không bao giờ gửi được request**; mọi write endpoint vẫn cần server-side authentication/CSRF/authz.

### 12.2. Test actual GET có allowed Origin và principal

Ví dụ giả định có `GET /api/orders` trả 200 cho user Alice:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

mvc.perform(get("/api/orders")
        .header(ORIGIN, "https://portal.example.net")
        .with(user("alice")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://portal.example.net"))
    .andExpect(header().string(
        ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
~~~

`with(user("alice"))` chỉ tạo mock security principal cho test; nó **không chứng minh browser đã có session cookie** và không test login flow. Dùng test HTTP/session/browser E2E để chứng minh cookie persistence/SameSite.

### 12.3. POST có principal nhưng không CSRF vẫn bị từ chối

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mvc.perform(post("/api/orders")
        .header(ORIGIN, "https://portal.example.net")
        .contentType("application/json")
        .content("{\"productId\":\"P-100\",\"quantity\":2}")
        .with(user("alice")))
    .andExpect(status().isForbidden());
~~~

Nếu cấu hình mẫu ở phần 7 dùng default CSRF và route `/api/orders` không được miễn, `CsrfFilter` trả 403 trước controller. Preflight CORS có thể **đã pass**, nhưng actual POST thiếu CSRF vẫn bị từ chối.

### 12.4. POST có CSRF token hợp lệ còn cần quyền nghiệp vụ

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/api/orders")
        .header(ORIGIN, "https://portal.example.net")
        .contentType("application/json")
        .content("{\"productId\":\"P-100\",\"quantity\":2}")
        .with(user("alice"))
        .with(csrf()))
    // Giả định fixture controller trả 201 khi tạo order.
    .andExpect(status().isCreated());
~~~

Đây là **test snippet** cần đặt trong class có `MockMvc mvc` và một controller/service fixture trả 201. `csrf()` chỉ cấp token phù hợp trong test; không chứng minh API đã kiểm object-level authorization. Khi user sai tenant/role, service vẫn phải từ chối và không tạo order.

### 12.5. Unauthorized actual request có thể có CORS headers

Với đúng origin được duyệt, một actual request thiếu session có thể trả `302 /login` hoặc `401` tùy authentication entry point. CORS processor cần tiếp tục phát `Access-Control-Allow-Origin` thích hợp trên response để browser JS quan sát status khi policy cho phép.

Nếu một error handler hoặc proxy trả `401` nhưng **không có ACAO** ở actual response, browser có thể chỉ hiển thị “blocked by CORS” thay vì JS đọc được status. Test hai điều độc lập:

- Backend thật trả status/auth error nào?
- Browser có được phép đọc response đó theo CORS policy không?

**Không sửa bằng cách cho unauthenticated requests thành 200.** Sửa owner CORS headers/error path.

### 12.6. Actual request từ denied Origin cũng phải được bảo vệ ở server

Với một simple cross-origin request không preflight, browser có thể đã gửi request trước khi từ chối cho JS đọc response. Spring CorsProcessor có thể từ chối actual CORS request dựa trên Origin; nhưng **không xây hệ thống phụ thuộc CORS là lớp ngăn business mutation duy nhất**.

Attacker có thể dùng nonbrowser client với Origin giả, hoặc một endpoint/gateway khác bypass CORS. Authentication, CSRF (khi browser ambient credentials), authorization và idempotency vẫn là các rào cản chính.

## 13. Nhiều SecurityFilterChain, MVC CORS mappings và thứ tự filter

### 13.1. Một request đi qua chain nào?

Một Spring Servlet application có thể tách:

~~~text
/api/browser/**  -> session cookie + CSRF + CORS cho portal
/api/m2m/**      -> Bearer-only Resource Server
/admin/**        -> browser admin chain, không mở CORS cho SPA bên ngoài
/actuator/**     -> management security riêng
~~~

Nếu `OPTIONS /api/browser/orders` bị chain M2M match nhầm, response có thể là `401` hoặc thiếu CORS headers. **CORS xử lý sớm chỉ có ý nghĩa trong chain hoặc filter áp dụng cho URL đó.**

### 13.2. Ví dụ tách route nhưng vẫn giữ nguyên tắc

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain m2m(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/m2m/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .formLogin(AbstractHttpConfigurer::disable)
        .httpBasic(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .csrf(AbstractHttpConfigurer::disable)
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserApi(HttpSecurity http)
        throws Exception {
    return http
        .securityMatcher("/api/browser/**")
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Đây là **phương án thay thế** cho config một chain trong phần 7; nếu dùng, CORS source cũng phải map `/api/browser/**`, không còn chỉ `/api/**` theo giả định cũ. Cần thêm chain cho login pages/other web routes theo kiến trúc. Không copy cả hai snippets vào một application mà không điều chỉnh security matcher/order.

### 13.3. Không áp permitAll OPTIONS vào mọi route chỉ vì một SPA

Sai hướng:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
    .anyRequest().authenticated())
~~~

Nó có thể mở những OPTIONS ngoài scope preflight mà vẫn **không có** CORS allow headers. Định nghĩa CORS source route-specific và đặt xử lý preflight trước authentication. Nếu cần một explicit OPTIONS matcher cho thiết kế khác, giới hạn path/method và test không có credential side effects.

### 13.4. CORS Servlet ở Spring MVC và Spring Security

Khi Spring MVC nằm trên classpath, Spring Security có thể sử dụng CORS configuration từ MVC khi không có một source cụ thể. Nhưng một app có nhiều `CorsConfigurationSource`/filter beans sẽ dễ trở nên mơ hồ.

Một controller có:

~~~java
@CrossOrigin(origins = "https://portal.example.net")
@GetMapping("/api/orders")
public java.util.List<String> getOrders() {
    // Chỉ là dữ liệu fixture; production phải kiểm quyền user.
    return java.util.List.of("test-order");
}
~~~

có thể hoạt động theo MVC CORS mapping, nhưng đừng trộn nhiều allowlists khác nhau giữa `@CrossOrigin`, `WebMvcConfigurer`, `CorsFilter` và Spring Security rồi cho rằng browser sẽ chọn “cấu hình chặt nhất”.

**Khuyến nghị học tập:** Với policy CORS ở Security boundary, sử dụng một `CorsConfigurationSource` tập trung cho các API paths, test header response sau Security và kiểm cả đường lỗi.

### 13.5. Khi filter bên ngoài Spring xử lý trước

Nếu có một `CorsFilter` đăng ký qua Servlet container, nó có thể xử lý preflight **trước** `FilterChainProxy`; cấu hình này cũng có thể đúng khi intentional. Nhưng đừng để container CorsFilter và `http.cors` cùng phát duplicated headers hoặc áp hai policies khác nhau.

Phân tích **filter registration order thực** và **wire response**. Những lời giải kiểu “thêm một CorsFilter mới” có thể làm lỗi từ 401 chuyển thành duplicate ACAO trên browser.

### 13.6. Authentication entry point khi JS gọi API

Với browser SPA, một API chưa đăng nhập trả `302 Location: /login` có thể khiến fetch theo redirect tới HTML, sau đó browser báo lỗi CORS/JSON parsing. Tùy contract, API có thể nên trả `401 JSON` thay vì 302, còn browser navigation login tiếp tục dùng form/OAuth redirect.

Đó là **thiết kế entry point riêng**, không phải lý do bỏ authentication. CORS phải được phát phù hợp trên cả `401`/`403` response để browser JS đọc và hiển thị thông báo khi origin được duyệt.

## 14. Những trường hợp “browser báo CORS” nhưng nguyên nhân không phải origin allowlist

### 14.1. Redirect trước preflight thành công

Một preflight có thể nhận:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Do Spring Security/MVC/gateway xử lý authentication trước CORS. Browser có thể từ chối/không hoàn tất preflight qua redirect theo tình huống/browser, và console báo CORS failure.

**Điểm cần sửa:** bảo đảm CORS preflight được xử lý **trước authentication**. Không tạo một phiên login giả cho OPTIONS và không thêm cookie cho preflight.

### 14.2. CORS headers thiếu trên error response

Request từ allowed origin hợp lệ nhưng API trả `401`/`403`/`500` qua error handler hoặc proxy, và error response không có `Access-Control-Allow-Origin`. Browser có thể che status gốc bằng “blocked by CORS policy” khi JS truy cập response.

Cách chẩn đoán:

1. Xem Network có OPTIONS thành công không.
2. Xem **actual response status** ở Network/HTTP logs.
3. Kiểm ACAO/ACAC của actual response, không chỉ preflight.
4. Xác định error response do Spring, container, gateway hay CDN phát.
5. Đảm bảo chính sách allowlist được áp nhất quán nhưng **không trả 200** để che lỗi auth.

### 14.3. Duplicate ACAO từ Spring và Nginx

~~~http
Access-Control-Allow-Origin: https://portal.example.net
Access-Control-Allow-Origin: *
~~~

Một số browser từ chối response có nhiều ACAO hoặc origin không hợp lệ. Nếu proxy thêm wildcard trong khi Spring đã trả origin cụ thể, sửa **ownership**: một lớp chịu trách nhiệm policy hoặc các lớp được phối hợp không ghi đè/nhân đôi.

Không bắt browser chọn header “ít rộng hơn”; đây là response không hợp lệ theo CORS protocol.

### 14.4. Wildcard credentials

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Dù method/header được phép, browser không expose credentialed response cho frontend. Trả exact ACAO và ACAC true khi chính sách thực sự muốn cho origin đó truy cập bằng credentials.

### 14.5. Authorization header không có trong Allowed-Headers

Frontend dùng:

~~~javascript
fetch("https://api.example.com/api/profile", {
  headers: {
    "Authorization": `Bearer ${accessToken}`
  }
});
~~~

Browser thường preflight vì `Authorization` không là safelisted request header. Nếu allowed headers chỉ có `Content-Type` và `X-CSRF-TOKEN`, preflight bị từ chối **dù token hợp lệ**.

Chỉnh allowlist header `Authorization` **chỉ cho API thực sự nhận Bearer từ browser**. Đừng thêm `Authorization` bừa bãi lên mọi cookie-only route hoặc cho rằng allow header cấp quyền Bearer; Resource Server vẫn phải validate token.

### 14.6. Browser không gửi cookie do SameSite/third-party cookie policy

Preflight trả 200 và CORS headers đầy đủ, nhưng actual POST không có session cookie vì `SameSite=Lax` không đi cross-site fetch hoặc browser chặn third-party cookies.

Backend có thể trả `401`/`302` vì thiếu authentication, hoặc `403` từ CsrfFilter nếu unsafe POST cũng thiếu CSRF token. Lỗi gốc vẫn có thể là **cookie policy/credential contract**, chứ không phải preflight. `Access-Control-Allow-Credentials: true` không vượt qua SameSite. Kiểm:

- Frontend `credentials: "include"`;
- Cookie `Secure; HttpOnly; SameSite=None` nếu cross-site context thật sự cần, cùng browser privacy policy;
- Domain/Path của API cookie;
- CSRF token bootstrap và CORS policy đúng;
- Kiến trúc BFF/same-site reverse proxy nếu third-party cookies không đáng tin.

### 14.7. CSP connect-src chặn fetch trước khi có CORS

CSP ở **frontend document** có thể chặn `fetch` tới API:

~~~http
Content-Security-Policy: connect-src 'self'
~~~

Khi SPA tại `portal.example.net` gọi `api.example.com`, CSP `connect-src 'self'` có thể chặn trước khi browser gửi request. Cần cho origin API trong **frontend CSP `connect-src`** theo yêu cầu, đồng thời backend API trả CORS hợp lệ.

**CSP và CORS là hai ranh giới khác nhau:** CSP quyết định tài liệu frontend được gọi endpoint nào; CORS quyết định JavaScript frontend có được đọc response của API không.

### 14.8. Private Network Access và chính sách trình duyệt mới

Browser/platform có thể thực hiện thêm kiểm tra hoặc preflight đối với request từ public page tới private/local network, với headers liên quan như:

~~~http
Access-Control-Request-Private-Network: true
~~~

và response policy tương ứng như `Access-Control-Allow-Private-Network` trong những triển khai hỗ trợ. Đặc tả/hành vi được cập nhật theo browser/version. **Không bật cho mọi origin chỉ vì preflight PNA fail**; đánh giá private network exposure, trusted origins, proxy và trạng thái tiêu chuẩn của browser đang hỗ trợ.

Bộ test thông thường về CORS `Origin`, methods và headers không tự chứng minh một chính sách PNA hợp lệ.

### 14.9. Redirect sang origin khác giữa các requests

Nếu `https://api.example.com/api/orders` redirect sang `https://legacy.example.net/orders`, browser có thể đánh giá origin mới và các hạn chế CORS/redirect. Không xây login/API flow phụ thuộc arbitrary cross-origin redirects; test exact location, credential forwarding, response CORS cuối và không lộ Authorization header qua redirects không được quản trị.

### 14.10. TLS, DNS, ad blockers và browser extensions

Một request có thể fail trước CORS do DNS/TLS/certificate, blocked mixed content, network timeout, CSP, extension/ad blocker hoặc proxy/WAF. Browser console đôi khi trình bày chung bằng lỗi “TypeError: Failed to fetch”; phải đọc Network và server logs, không kết luận origin không allow chỉ từ text JavaScript exception.

## 15. Origin bị từ chối và những giới hạn của chính sách CORS

### 15.1. Browser không phải người dùng được xác thực

Một attacker có thể chạy HTTP client:

~~~bash
curl -i \
  -H "Origin: https://portal.example.net" \
  https://api.example.com/api/orders
~~~

`curl` có thể **tự đặt Origin giả**. Backend không được tin origin header để cấp quyền admin hoặc bỏ authentication. Test này hữu ích để xem response CORS headers nhưng không chứng minh caller thực sự đến từ portal.

### 15.2. Cross-origin simple request vẫn có thể gửi

Nếu attacker tạo:

~~~html
<form method="post"
      action="https://api.example.com/api/orders"
      enctype="application/x-www-form-urlencoded">
  <input name="productId" value="P-100">
  <button>Submit</button>
</form>
~~~

browser có thể gửi form submission mà không thực hiện CORS preflight như fetch. Nếu cookie được browser gửi theo cookie policy, backend phải cần CSRF token/authz để ngăn mutation trái ý người dùng.

**Không dùng “chúng ta chặn mọi preflight từ attacker” làm bằng chứng hệ thống miễn nhiễm CSRF.**

### 15.3. CORS không cấp quyền đọc tài nguyên giữa người dùng cùng origin

CORS origin `https://portal.example.net` được cho phép không nghĩa Alice ở portal có quyền đọc order của Bob. Browser header phản ánh origin code, **không** phải individual user/tenant. API cần session/JWT authn, per-object authorization, tenant boundary và response caching đúng.

### 15.4. Origin allowlist có thể bị XSS/compromise

Nếu origin `portal.example.net` bị XSS hoặc supply-chain script compromise, code attacker chạy **tại origin được allowlist**, nên CORS không bảo vệ khỏi mọi hành vi đó. CSP, script isolation/SRI, CSRF, authentication, authorization và monitoring vẫn cần thiết.

### 15.5. Origin null không phải “same-origin”

`Origin: null` có thể đến từ sandboxed/opaque origins. Mở `null` trong CORS allowlist có thể cho phép nhiều context không tin cậy có cùng serialized origin. Khi thực sự cần hỗ trợ file-based clients hay sandbox, xem lại kiến trúc trước khi mở `null`; thường tốt hơn là phục vụ frontend qua HTTPS origin định danh rõ.

### 15.6. Same-site cross-origin cũng có rủi ro

Cho tất cả subdomains `*.example.com` qua `allowedOriginPatterns` có thể cấp quyền CORS cho một subdomain bị takeover hoặc host do khách hàng tạo. Còn với CSRF, SameSite cookies có thể được gửi giữa subdomains **same-site**; đây là lý do càng không nên dựa vào SameSite để thay CSRF khi có trust boundary giữa subdomains.

## 16. Caching preflight và chính sách Vary

### 16.1. Preflight cache khác HTTP response cache

Browser có thể cache kết quả preflight theo rules riêng của Fetch và `Access-Control-Max-Age`, chịu browser-specific caps và partitioning. Một `Access-Control-Max-Age: 600` gợi ý tối đa 600 giây, không cam kết mọi browser sẽ cache đúng 600 giây.

Preflight cache **không tạo authentication session** và không có nghĩa actual data được cache. Chỉ cache quyết định có cần gửi thêm OPTIONS cho cùng loại request context hay không.

### 16.2. Test thay đổi policy phải tính tới cache

Trong E2E:

1. Gọi từ allowed origin, tạo preflight và xác nhận headers.
2. Thay CORS allowlist tại server.
3. Browser có thể vẫn sử dụng preflight cache cũ cho đến khi hết hạn theo browser.
4. Để test chính sách mới, dùng fresh browser context/profile, URL/path hoặc cache controls phù hợp với harness thay vì chỉ reload trang.
5. Kiểm actual response CORS headers và business authorization ngay cả khi preflight còn được cache.

Không kết luận “server vẫn cấp origin attacker” từ một lần browser không gửi OPTIONS sau khi config thay đổi.

### 16.3. Shared HTTP cache phải phân biệt Origin

Nếu server trả ACAO dựa trên Origin, `Vary: Origin` giúp tránh dùng response policy của origin A cho origin B. Với preflight có methods/headers khác nhau, `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers` cũng hữu ích.

**Nhưng:** Với dữ liệu riêng tư, cần `Cache-Control: private/no-store` phù hợp, auth-aware cache keys và không cache chung body cho nhiều users. `Vary: Origin` chỉ phân biệt frontend origin, không phân biệt user.

### 16.4. CDN/WAF xử lý OPTIONS trước Spring

Một CDN có thể:

- Trả `200` cho tất cả OPTIONS với ACAO wildcard;
- Chặn OPTIONS và trả `405`;
- Cache ACAO của origin A rồi trả cho B;
- Thêm `Access-Control-Allow-Credentials: true` sai;
- Strip `Vary` hoặc gộp duplicate headers;
- Trả `401` do WAF không cho OPTIONS.

Lúc đó `MockMvc` nội bộ vẫn pass, nhưng browser production fail. Cần **HTTP integration test qua public origin**, kiểm response status/headers theo allowed và denied origins, và ghi rõ owner layer chịu trách nhiệm CORS.

### 16.5. Vary không làm origin trở thành trusted

Nếu một backend chỉ reflect bất kỳ `Origin` và luôn thêm `Vary: Origin`, nó vẫn có **CORS policy quá rộng**. `Vary` chỉ giải quyết cache correctness, không phải allowlist validation.

## 17. HTTP integration qua public edge: kiểm cả Spring, proxy và CDN

### 17.1. Vì sao cần test HTTP thật ngoài MockMvc?

`MockMvc` chạy trong bối cảnh Servlet/Spring tests, chủ yếu kiểm **filter chain/controller**. Nhưng browser production nhận response từ:

~~~text
Browser
  -> DNS/TLS
  -> CDN/WAF/Ingress
  -> Reverse proxy
  -> Servlet container
  -> Spring Security CORS integration
  -> Controller
  -> Reverse proxy / CDN response
  -> Browser
~~~

Nếu ingress chặn OPTIONS hoặc thêm ACAO wildcard, nội bộ Spring pass vẫn chưa đủ. Vì vậy cần một bộ integration tests bằng HTTP client hoặc terminal **tới đúng public hostname** trong môi trường test an toàn.

### 17.2. Mẫu curl cho preflight được phép

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://portal.example.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

**Kỳ vọng với policy chương 7:** HTTP thành công, ACAO đúng `https://portal.example.net`, ACAM chứa POST, ACAH cho `content-type`/`x-csrf-token`, ACAC `true` và `Vary` phù hợp.

Đừng gửi session cookie/client secret trong preflight để “giúp” nó vượt authentication. Mục tiêu là chứng minh unauthenticated OPTIONS được xử lý đúng.

### 17.3. Mẫu curl cho origin bị từ chối

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://attacker.example.org' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

**Kỳ vọng:** không cấp ACAO cho attacker; nếu Spring `DefaultCorsProcessor` xử lý, thường trả `403 Invalid CORS request`. Kiểm cả response status, headers và source trả response qua request ID/observability, không chỉ so nội dung body.

### 17.4. Thử method và header bị cấm độc lập

~~~bash
# Origin hợp lệ, method không nằm trong allowlist:
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://portal.example.net' \
  -H 'Access-Control-Request-Method: DELETE'

# Origin + POST hợp lệ, header không được phép:
curl -i -X OPTIONS 'https://api.example.com/api/orders' \
  -H 'Origin: https://portal.example.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: x-admin-override'
~~~

Cả hai phải không cấp phép CORS theo policy ví dụ. Nếu CDN đang cho phép mọi OPTIONS và Spring không nhận request, test phải phát hiện sự lệch policy này.

### 17.5. Curl có thể giả Origin nên không thay browser test

Bằng `curl` bạn có thể đặt bất cứ `Origin` nào, nên nó phù hợp để **xem server CORS response** nhưng không chứng minh browser sẽ tạo preflight, áp cookies, chặn JS đọc response hoặc thực hiện credentialed CORS.

Khi kiểm browser behavior, dùng browser profile thật với frontend origin thật và quan sát Network/Console, không chỉ chạy curl một lần.

### 17.6. So response giữa internal và public endpoint

| So sánh | Kiểm điều gì? |
|---|---|
| MockMvc internal vs public HTTP | Header do Spring và edge có giống policy không? |
| HTTPS public vs HTTP upstream | Có sai `X-Forwarded-Proto`/redirect/cookie Secure không? |
| Allowed origin vs attacker origin | Proxy có reflect origin tùy ý không? |
| Path `/api/**` vs `/admin/**` | Có bị CORS mở rộng scope không? |
| Preflight vs actual response | Error handlers có giữ ACAO cho allowed origin không? |
| Multiple allowed origins | `Vary: Origin` và cache có phục vụ đúng policy không? |
| New deployment vs cached preflight | Browser/CDN có còn policy cũ trong thời gian TTL không? |

## 18. Browser E2E: chứng minh browser thực thi CORS như mong đợi

### 18.1. Hai frontend origins và một API HTTPS

Môi trường test:

~~~text
Allowed frontend: https://portal.example.test
Denied frontend:  https://attacker.other.test
Servlet API:      https://api.example.test
~~~

Các hostname cần DNS/hosts và TLS certificates dùng được trong test. Không đặt cả hai frontend vào cùng một origin rồi kỳ vọng đánh giá cross-origin. CORS allowlist trong test profile phải dùng `https://portal.example.test` tương ứng, thay vì URL production trong chương 7.

Tạo một **test-only endpoint** `GET /api/cors-probe`, trả `200` kèm JSON vô hại và response header `X-Request-ID`. Cho phép anonymous **chỉ trên route test**, không mở business `/api/orders` hoặc quản lý session production. Không đưa endpoint probe public vào production nếu không có nhu cầu.

### 18.2. Browser request GET có custom header sẽ preflight

Trang test tại allowed frontend:

~~~javascript
async function probeCors() {
  const response = await fetch(
    "https://api.example.test/api/cors-probe",
    {
      method: "GET",
      headers: {
        "X-Request-ID": "cors-probe-1"
      }
    }
  );

  return {
    status: response.status,
    requestId: response.headers.get("X-Request-ID"),
    data: await response.json()
  };
}
~~~

`X-Request-ID` thường kích hoạt preflight. Vì đây là **public test route** không dùng cookie, `credentials: "include"` không cần thiết. Kiểm API cho phép `X-Request-ID` và `Access-Control-Expose-Headers: X-Request-ID` để JavaScript đọc header response.

### 18.3. Playwright kiểm allowed origin

~~~javascript
import { test, expect } from "@playwright/test";

test("allowed frontend đọc được CORS probe response", async ({ page }) => {
  await page.goto("https://portal.example.test/cors-test.html");

  const result = await page.evaluate(async () => {
    try {
      const response = await fetch(
        "https://api.example.test/api/cors-probe",
        { headers: { "X-Request-ID": "probe-1" } }
      );

      return {
        kind: "resolved",
        status: response.status,
        requestId: response.headers.get("X-Request-ID")
      };
    } catch (error) {
      return { kind: "blocked", errorName: error.name };
    }
  });

  expect(result.kind).toBe("resolved");
  expect(result.status).toBe(200);
  expect(result.requestId).toBeTruthy();
});
~~~

**Điều kiện:** Test environment có probe fixture, API CORS config allow frontend origin, GET và `X-Request-ID`, đồng thời CSP `connect-src` của trang test cho API origin. Nếu browser nhận ACAO thiếu/method/header không được phép, `fetch` reject và test fail.

### 18.4. Playwright kiểm denied origin

~~~javascript
test("denied frontend không thể đọc CORS probe", async ({ page }) => {
  await page.goto("https://attacker.other.test/cors-test.html");

  const result = await page.evaluate(async () => {
    try {
      const response = await fetch(
        "https://api.example.test/api/cors-probe",
        { headers: { "X-Request-ID": "attacker-probe" } }
      );
      return { kind: "resolved", status: response.status };
    } catch (error) {
      return { kind: "blocked", errorName: error.name };
    }
  });

  expect(result.kind).toBe("blocked");
});
~~~

**Cần bảo đảm** trang attacker test có CSP cho phép `connect-src https://api.example.test`; nếu CSP chặn trước CORS, test vẫn có `kind=blocked` nhưng **không chứng minh CORS**. Kết hợp Network/Console và server/proxy logs để xác nhận preflight đã tới API, bị policy CORS từ chối và actual GET không được gửi sau preflight.

### 18.5. Không chỉ quan sát JavaScript exception

Browser có thể báo `TypeError: Failed to fetch` vì CORS, CSP, TLS, DNS, network, extension hoặc request cancellation. Để xác định nguyên nhân:

1. Mở Network tab, bật preserve log.
2. Tìm `OPTIONS /api/cors-probe` được browser tạo.
3. Xem `Origin`, `Access-Control-Request-Method`, requested headers.
4. Xem response ACAO/ACAM/ACAH/ACAC và status.
5. Nếu browser gửi actual GET, xem response ACAO và status.
6. Kiểm Console violation log xác định CORS/CSP/network.
7. Đối chiếu request ID với Spring/proxy logs **đã ẩn credential**.

Không suy rằng mọi Promise rejection đều vì origin không được phép.

### 18.6. Browser credentialed fetch cần test riêng

Với browser session API, test:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/orders",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ productId: "P-100", quantity: 1 })
  }
);
~~~

Để request **thành công end-to-end**, test phải có:

- User đã đăng nhập bằng cơ chế session được hỗ trợ;
- Cookie có thể được gửi trong cross-site fetch theo SameSite/3PC policy;
- CSRF token lấy từ nguồn hợp lệ, gắn đúng session;
- CORS origin/method/headers/credentials phù hợp;
- User có quyền tạo order, payload hợp lệ;
- Error paths và session rotation được kiểm thêm.

Nếu preflight pass nhưng actual POST trả 403 do CSRF, **đó là test bảo mật pass cho CSRF negative case**, không phải bằng chứng CORS đang sai.

### 18.7. Browser không phải MockMvc

| Hành vi | MockMvc | Browser E2E |
|---|---|---|
| Gửi `Origin`/preflight headers thủ công | Có | Browser tự sinh theo Fetch |
| Chạy Spring Security filters | Có | Có nếu gọi backend thật |
| Áp SameSite để quyết định Cookie | Không | Có |
| Tạo preflight cache và browser cap | Không | Có |
| Chặn JavaScript đọc response khi CORS fail | Không | Có |
| Áp CSP `connect-src` | Không | Có |
| Có redirect/network/TLS behavior | Giả lập ở Servlet test | Có |
| Chạy extensions/privacy controls | Không | Tùy browser profile |
| Phát hiện proxy/WAF trước Spring | Không | Có khi qua public endpoint |
| Kiểm side effects trong DB | Có nếu fixture tích hợp DB | Có qua kiểm backend state test |

**Kết luận:** MockMvc kiểm **server-side policy**, browser kiểm **policy được thực thi trong ngữ cảnh user thật**. Cần cả hai.

## 19. CORS preflight không phải bằng chứng xác thực hoặc quyền ghi

### 19.1. Một API M2M bearer-only có cần CSRF token?

Nếu endpoint thật sự chỉ nhận `Authorization: Bearer` do client chủ động thêm và **không** nhận cookie/session/Basic fallback, browser-induced ambient credential CSRF có threat model khác. Có thể cân nhắc miễn CSRF **riêng đường Bearer-only**, nhưng:

- Browser SPA gửi Authorization header thường gây preflight;
- CORS policy vẫn cần nếu API cho JavaScript từ origin khác đọc response;
- Resource Server phải validate issuer/audience/signature/expiry/scopes và per-object authorization;
- Nếu custom gateway có cookie fallback, API không còn bearer-only và phải đánh giá CSRF lại.

Không áp `csrf.disable()` trên toàn `/api/**` chỉ vì một vài endpoints JWT.

### 19.2. Origin bị cấm không thay credential invalid

Một allowed origin có thể gửi request với Bearer token sai, và server trả 401. Một denied origin cũng có thể có valid Bearer token nếu token bị lộ. CORS không xác minh ai sở hữu token; token validation và browser policy là hai lớp độc lập.

### 19.3. Reverse proxy cùng origin làm browser không cần CORS

Một BFF/reverse-proxy có thể phục vụ SPA và API dưới cùng public origin:

~~~text
https://app.example.com/            SPA
https://app.example.com/api/orders   API qua reverse proxy/BFF
~~~

Browser không cần CORS cho same-origin fetch. Nhưng **CSRF vẫn có thể cần** nếu session cookie ambient tự gửi và unsafe POST. Chọn same-origin deployment có thể giảm complexity CORS, không làm Spring authorization/CSRF trở nên không cần thiết.

### 19.4. Preflight không là rate-limit credential unit

Một preflight thường không mang user identity, nên rate limiting bằng user ID/session trên OPTIONS có thể hoạt động sai. Có thể áp network-level abuse controls ở gateway, nhưng không bắt user login để OPTIONS pass. Actual POST vẫn rate-limit theo user/tenant/API key và kiểm idempotency khi thích hợp.

### 19.5. DDoS và OPTIONS flood

Attacker ngoài browser có thể gửi nhiều OPTIONS với Origin giả. CORS checks cần đơn giản, không gọi DB/IdP hoặc business service nặng cho từng preflight. Dùng bounded allowed-origin config/cache, network WAF/rate limiting theo IP khi phù hợp và tránh response chứa bí mật. CORS không là lớp chống DDoS đầy đủ.

## 20. Ma trận 60 ca kiểm thử CORS preflight và origin bị từ chối

Đây là bộ regression mẫu cho chính sách Servlet ở phần 7, đã được nhóm theo **thực tế HTTP**, **security filters**, **browser** và **hạ tầng**. Khi sản phẩm chọn một policy khác, thay kết quả kỳ vọng có chủ đích, không đơn giản biến mọi request thành pass.

### 20.1. Nhóm A — preflight đúng và sai Origin

| ID | Request/điều kiện | Mong đợi |
|---|---|---|
| **CORS-01** | OPTIONS + allowed Origin + requested POST + allowed headers | Preflight thành công, ACAO chính xác |
| **CORS-02** | OPTIONS + allowed Origin + requested GET + custom allowed header | Preflight thành công |
| **CORS-03** | OPTIONS + allowed Origin + requested PATCH | Preflight thành công vì policy cho PATCH |
| **CORS-04** | OPTIONS + Origin attacker | Từ chối, không cấp ACAO attacker |
| **CORS-05** | Origin `https://portal.example.net.evil.invalid` | Từ chối lookalike host |
| **CORS-06** | Origin `http://portal.example.net` | Từ chối khác scheme |
| **CORS-07** | Origin `https://portal.example.net:8443` | Từ chối khác port |
| **CORS-08** | Origin `https://sub.portal.example.net` | Từ chối subdomain không đăng ký |
| **CORS-09** | Origin `null` | Không allow mặc định |
| **CORS-10** | Origin khác nhau giữa nhiều requests | ACAO chỉ trả cho allowlisted Origin tương ứng |
| **CORS-11** | Preflight không mang Cookie/JSESSIONID | Vẫn pass nếu CORS policy hợp lệ |
| **CORS-12** | Preflight không mang Authorization | Vẫn pass nếu CORS policy hợp lệ |

### 20.2. Nhóm B — method, headers và route

| ID | Request/điều kiện | Mong đợi |
|---|---|---|
| **CORS-13** | Allowed Origin + requested DELETE | Bị từ chối vì DELETE không allowed |
| **CORS-14** | Allowed Origin + requested CONNECT/TRACE | Bị từ chối theo policy/HTTP firewall |
| **CORS-15** | Allowed Origin + requested POST + `content-type` | Pass nếu header allowed |
| **CORS-16** | Allowed Origin + `x-csrf-token` | Pass cho header name, chưa validate token |
| **CORS-17** | Allowed Origin + `x-request-id` | Pass nếu header allowed |
| **CORS-18** | Allowed Origin + `x-admin-override` | Preflight denied |
| **CORS-19** | Allowed Origin + `authorization` nhưng policy cookie-only không allow | Preflight denied theo config minh họa |
| **CORS-20** | OPTIONS thiếu `Origin` | Không coi là CORS preflight |
| **CORS-21** | OPTIONS có Origin, thiếu `Access-Control-Request-Method` | Không coi là preflight chuẩn |
| **CORS-22** | OPTIONS có Origin nhưng `Access-Control-Request-Method` bất thường | Không cấp quyền bừa bãi; xử lý error policy |
| **CORS-23** | Preflight tới `/api/orders` | Áp đúng CORS source `/api/**` |
| **CORS-24** | Preflight tới `/admin/users` | Không cấp ACAO nhờ `/api/**` policy |
| **CORS-25** | Preflight tới unknown `/api/not-existing` | Hành vi được thiết kế; không dùng CORS thay route authz |
| **CORS-26** | OPTIONS hợp lệ qua gateway tới Spring | Không bị redirect login/401 trước CORS |
| **CORS-27** | OPTIONS được xử lý | Không gọi controller create/update/delete |
| **CORS-28** | Preflight response `Access-Control-Allow-Methods` | Chứa requested actual method, không chỉ OPTIONS |

### 20.3. Nhóm C — credentials, actual response và CSRF

| ID | Request/điều kiện | Mong đợi |
|---|---|---|
| **CORS-29** | Credentialed CORS với ACAO `*` | Bị browser từ chối, không dùng trong policy |
| **CORS-30** | Credentialed request từ allowed Origin | ACAO exact + ACAC `true` khi được thiết kế |
| **CORS-31** | Preflight pass, actual POST không auth | 401/302 nếu CSRF đã hợp lệ; nếu thiếu CSRF có thể 403; không tạo order |
| **CORS-32** | Preflight pass, actual POST có auth nhưng thiếu CSRF | 403, không ghi nghiệp vụ |
| **CORS-33** | Preflight pass, actual POST CSRF sai | 403, không ghi nghiệp vụ |
| **CORS-34** | Preflight pass, actual POST CSRF đúng nhưng sai tenant | 403/404 theo contract, không ghi |
| **CORS-35** | Preflight pass, actual POST auth/CSRF/authz đều đúng | Controller xử lý payload hợp lệ |
| **CORS-36** | Actual GET từ allowed Origin có user | ACAO đúng + response theo ACL |
| **CORS-37** | Actual GET từ denied Origin | Không cho JS attacker đọc response |
| **CORS-38** | Actual request là simple cross-origin POST không preflight | Server vẫn bảo vệ CSRF/authz |
| **CORS-39** | POST dùng session cookie nhưng browser SameSite chặn cookie | Auth fail an toàn, không bỏ auth |
| **CORS-40** | Response `401` cho allowed Origin | Error vẫn có CORS policy cho JS đọc nếu architecture yêu cầu |
| **CORS-41** | Response `403` CSRF cho allowed Origin | Không bị che thành 200; no side effects |
| **CORS-42** | Header `X-Request-ID` được expose | JS đọc được trên actual response khi policy cho phép |
| **CORS-43** | JS muốn đọc `Set-Cookie` | Không được expose như regular response header |
| **CORS-44** | Bearer M2M API chỉ có browser session cookie | Không được nâng thành M2M identity |
| **CORS-45** | Origin header bị client giả mạo | Không bypass authentication/authorization |

### 20.4. Nhóm D — cache, proxy và browser

| ID | Request/điều kiện | Mong đợi |
|---|---|---|
| **CORS-46** | `Vary: Origin` và requested method/headers | Có trên preflight/cached policy tương ứng |
| **CORS-47** | Preflight cache còn hiệu lực sau config change | Test dùng fresh context, tránh kết luận sai |
| **CORS-48** | CDN cache ACAO của origin A trả cho origin B | Phát hiện lỗi Vary/cache và khắc phục |
| **CORS-49** | Spring và proxy cùng ghi ACAO | Không có duplicate/conflicting headers |
| **CORS-50** | Proxy trả 302 login cho OPTIONS | Phát hiện lỗi ordering/routing |
| **CORS-51** | Proxy trả 405 cho OPTIONS | Phát hiện lỗi trước Spring |
| **CORS-52** | Proxy trả wildcard ACAO cho mọi origin | Không được coi là policy đạt yêu cầu |
| **CORS-53** | Browser allowed frontend tạo preflight thực | Network cho thấy OPTIONS đúng Origin/method/headers |
| **CORS-54** | Browser attacker frontend tạo preflight | Actual request bị chặn sau CORS reject |
| **CORS-55** | Frontend CSP connect-src không cho API | Phân biệt CSP failure với CORS failure |
| **CORS-56** | Browser blocked third-party cookies | Phân biệt auth/cookie failure với preflight |
| **CORS-57** | PNA-related preflight trên browser hỗ trợ | Không cấp private-network exposure ngoài policy |
| **CORS-58** | Browser E2E trên Chrome/Firefox/Safari được hỗ trợ | CORS/cookie behavior được kiểm theo profile |
| **CORS-59** | Same-site subdomain cross-origin | CORS vẫn cần khi JS khác origin, CSRF không tự mất |
| **CORS-60** | Headers policy sau public HTTPS edge | Khớp contract, không chỉ internal MockMvc |

### 20.5. Tiêu chí pass ngoài mã HTTP

Một test denied Origin được xem là mạnh khi chứng minh:

- Không có `Access-Control-Allow-Origin` cho attacker (và không có credentialed allow policy cho attacker).
- Browser không cho phép actual request sau **preflight fail**.
- Backend không thực hiện business side effects trên OPTIONS.
- Nếu actual simple request vẫn có thể đến server qua kênh không cần preflight, authentication/CSRF/authorization vẫn ngăn side effects trái phép.
- Không có CORS policy rộng từ proxy/CDN làm lệch cấu hình Spring.

Một test allowed Origin được xem là mạnh khi chứng minh:

- Preflight không cần user cookie để pass.
- Actual request chỉ được xử lý sau authentication, CSRF (khi áp) và authorization.
- Error response vẫn trung thực về HTTP status và mang CORS headers khi frontend được phép đọc.
- Không lộ private data giữa users/tenants hoặc qua shared cache.

## 21. Chẩn đoán: OPTIONS 401/403/404/405 và browser CORS error

### 21.1. Bảng xác định tầng lỗi

| Dấu hiệu | Nguồn có khả năng | Bước kiểm tra |
|---|---|---|
| OPTIONS trả 401 | Authentication chạy trước CORS | `http.cors`, filter order, SecurityFilterChain matcher |
| OPTIONS trả 302 tới login | Form/OIDC login entrypoint xử lý preflight | CORS trước auth, đừng login OPTIONS |
| OPTIONS trả 403 `Invalid CORS request` | Origin, requested method/header không hợp lệ | So allowlist + path + requested values |
| OPTIONS trả 403 nhưng không phải CorsProcessor | CSRF/custom filter/WAF/deny matcher | Kiểm nguồn 403, không kết luận origin reject |
| OPTIONS trả 404 | Proxy/backend không route OPTIONS, CORS source không áp | Tìm request đi qua lớp nào |
| OPTIONS trả 405 | Handler/proxy từ chối method | Kiểm CorsFilter trước controller, gateway routing |
| OPTIONS trả 200 nhưng thiếu ACAO | PermitAll OPTIONS nhưng không có CORS policy | Cấu hình `CorsConfigurationSource` đúng route |
| OPTIONS trả 200 ACAO `*` và ACAC true | Policy không hợp lệ cho credentialed browser fetch | Exact allowlisted Origin, no wildcard |
| OPTIONS trả 200 nhưng ACAM không có POST | Actual method không allowed | Chỉnh allow methods đúng nghiệp vụ |
| OPTIONS trả 200 nhưng ACAH thiếu x-csrf-token | Requested header không allowed | Allow header name nếu API cần |
| Preflight pass, POST trả 401 | No session/authentication trên actual | Cookie SameSite/credentials/auth entrypoint |
| Preflight pass, POST trả 403 | CSRF hoặc authorization | Kiểm `CsrfFilter`/authorities, không mở CORS bừa bãi |
| POST trả 201 nhưng frontend báo CORS | Actual response thiếu/mâu thuẫn ACAO/ACAC | Error/success headers và proxy |
| GET có response nhưng JS không đọc header X-Request-ID | Thiếu `Access-Control-Expose-Headers` | Cấu hình exposed headers |
| Chỉ thất bại với `Authorization` header | Preflight header không allowed hoặc auth token invalid | Phân biệt OPTIONS và actual 401 |
| Chỉ fail sau khi triển khai CDN | CDN thêm header/cache/method deny | So internal vs public response |
| Chỉ fail với browser privacy mode | Cookie/partition/3PC | Kiểm Cookie actual, không chỉ ACAO |
| Chỉ fail với user đăng nhập lâu | Session/CSRF rotation | Kiểm token/session lifecycle |
| Chỉ fail với port 8443 | Origin allowlist không chứa port | Đăng ký origin đúng scheme/host/port |
| Chỉ fail khi dùng HTTP frontend | Scheme mismatch, mixed content/TLS | Đừng mở insecure origin vào prod |
| Lỗi Origin `null` | Sandboxed/file/opaque context | Không allow "null" mù quáng |
| Console báo CSP connect-src violation | Frontend CSP chặn fetch | Sửa frontend CSP, không phải Spring CORS |
| Console báo PNA/private network | Browser network trust policy | Đánh giá private-network access riêng |
| OPTIONS không xuất hiện | Request safelisted/cache/CSP blocked | Kiểm Fetch semantics và preflight cache |
| OPTIONS xuất hiện lặp lại nhiều | Browser cache cap/requests khác headers/method/origin | Kiểm max-age, cache partition, headers |
| Spring logs không thấy OPTIONS | Proxy/WAF/CDN trả trước | Test public edge và ingress routing |
| Spring trả ACAO đúng nhưng browser thấy 2 headers | Proxy thêm duplicate | Một owner chính sách, sửa edge |
| CORS đúng nhưng Bob đọc đơn hàng Alice | BOLA/IDOR | Object-level authorization, không liên quan origin |

### 21.2. Decision tree điều tra

~~~mermaid
flowchart TD
    A[Browser fetch thất bại] --> B{Network có OPTIONS không?}
    B -->|Không| C[Request safelisted? Preflight cache? CSP/TLS chặn?]
    B -->|Có| D{OPTIONS tới Spring hay proxy xử lý?}
    D -->|Proxy| E[Check WAF/CDN status, header, routing]
    D -->|Spring| F{Origin, method, headers được allow?}
    F -->|Không| G[Policy deny đúng? Negative test]
    F -->|Có| H{Response preflight đủ ACAO/ACAM/ACAH/ACAC?}
    H -->|Không| I[CorsConfigurationSource, chain, duplicate headers]
    H -->|Có| J{Browser có gửi actual request?}
    J -->|Không| K[Browser policy/cache/credentials/PNA]
    J -->|Có| L{Actual status là gì?}
    L -->|401 hoặc 302| M[Authentication/session cookie/entrypoint]
    L -->|403| N[CSRF hoặc authorization; kiểm no side effects]
    L -->|2xx| O[Kiểm actual response ACAO/ACAC và JS visibility]
~~~

### 21.3. Một incident log an toàn nên chứa gì?

~~~text
requestId: req-2026-11-26-42
pathCategory: api-orders
method: OPTIONS
corsOriginClass: ALLOWED / DENIED / NULL / ABSENT
corsRequestedMethod: POST
corsRequestedHeaderNames: content-type,x-csrf-token
corsOutcome: ALLOWED / ORIGIN_DENIED / METHOD_DENIED / HEADER_DENIED
filterOwner: spring / gateway
httpStatus: 200 / 403
durationMs: ...
~~~

Không ghi raw Cookie, Authorization token, CSRF token value, client secret, PII, full request bodies hoặc arbitrary unvalidated header values. Header names có thể được log sau sanitization/bounding; attacker vẫn có thể gửi chuỗi dài/malformed để làm nhiễu logs.

### 21.4. Diagnostic không được đổi policy vô tội vạ

**Những sửa lỗi sai phổ biến:**

~~~java
// Sai: mở mọi origin và method/header không cần thiết.
cors.addAllowedOriginPattern("*");
cors.addAllowedMethod("*");
cors.addAllowedHeader("*");
cors.setAllowCredentials(true);

// Sai: bỏ CSRF của web session để POST không còn 403.
http.csrf(csrf -> csrf.disable());
~~~

Nới policy có thể làm preflight xanh nhưng tăng quyền đọc dữ liệu từ JavaScript bên ngoài hoặc bỏ lớp bảo vệ mutation. Sửa **đúng origin/method/header/route** đã được phê duyệt và kiểm regression toàn hệ thống.

### 21.5. Khi xác định lỗi không phải CORS

Nếu browser frontend request được gửi và Spring trả `403` vì user sai role, đó là **authorization failure**. Đừng thay CORS để response biến thành success. Nếu preflight không tới Spring do certificate/TLS, đó là **network failure**. Nếu browser báo “blocked by CSP”, đó là **frontend CSP failure**.

Một triage report tốt phải ghi **request stage, method, origin, response source, status, headers và security decision**, thay vì chung chung “CORS đang lỗi”.

## 22. Quy trình thực hành: dựng và chạy test theo từng bước

### Bước 1 — Khai báo một hợp đồng CORS đo được

Ví dụ sản phẩm xác định:

~~~text
Backend base URL: https://api.example.com
CORS paths:      /api/**
Allowed origin:  https://portal.example.net
Allowed methods: GET, POST, PATCH
Allowed headers: Content-Type, X-CSRF-TOKEN, X-Request-ID
Exposed headers: X-Request-ID
Credentials:     true
Max-Age:         600 seconds
Other origins:   denied
/admin/**:       no CORS allowlist for portal
~~~

Đừng chỉ ghi “cho phép frontend gọi API”; phải biết exact scheme/host/port, credentials mode, methods, request headers và auth/CSRF model.

### Bước 2 — Cấu hình CORS source trước authentication

Tạo `CorsConfigurationSource` như phần 7 và `http.cors(Customizer.withDefaults())` trong chain chứa `/api/**`. Giữ Spring CSRF nếu API nhận browser session cookie trên unsafe methods. Không bật wildcard hoặc permitAll toàn `/api/**`.

### Bước 3 — Test preflight positive không có session

MockMvc gửi `OPTIONS` với allowed Origin, requested POST và hai request headers. Kiểm:

- Response thành công, không redirect tới login.
- ACAO đúng exact Origin.
- ACAM chứa POST, ACAH chứa content-type/x-csrf-token.
- ACAC true và max-age phù hợp.
- Không tạo order hoặc tác động nghiệp vụ.
- `Vary` phản ánh request dimensions thích hợp.

### Bước 4 — Test negative origin và lookalikes

Gửi origins:

~~~text
https://attacker.example.org
http://portal.example.net
https://portal.example.net:8443
https://portal.example.net.evil.invalid
https://sub.portal.example.net
null
~~~

Với allowlist trên, tất cả phải không được cấp ACAO. Nếu một origin được cấp, đó là **policy failure** dù endpoint đang yêu cầu authentication.

### Bước 5 — Test method/header không được phép

Origin đúng nhưng requested DELETE hoặc `x-admin-override` phải fail. Kiểm không nhầm `Access-Control-Request-Method` với method OPTIONS hoặc cho mọi header vì frontend chỉ cần một custom header.

### Bước 6 — Test actual request sau preflight

Gửi POST có Origin hợp lệ nhưng:

- Không có auth: nhận authentication failure.
- Có principal nhưng thiếu CSRF: 403, không ghi order.
- Có principal và CSRF sai: 403, không ghi order.
- Có principal/CSRF đúng nhưng thiếu authority/tenant: denied, không ghi.
- Có principal/CSRF/authz đúng: business validation + response theo hợp đồng.

Một test pass ở bước 3 **không được bỏ qua bước 6**.

### Bước 7 — HTTP test qua public ingress

Gọi curl OPTIONS tới public HTTPS URL, không chỉ MockMvc. So Spring headers với public response; kiểm WAF/ingress không trả 401/302/405, không thêm wildcard ACAO hoặc strip `Vary`.

### Bước 8 — Browser E2E từ hai origins thật

Frontend approved origin gọi API, kiểm browser preflight và JS đọc response. Frontend attacker gọi cùng endpoint với custom header, browser phải chặn do CORS. Đồng thời test simple POST/CSRF để chứng minh server không dựa vào browser CORS làm rào cản duy nhất.

### Bước 9 — Kiểm session/SameSite và frontend CSP riêng

Nếu frontend dùng cookie session cross-site, kiểm `credentials`, cookie `SameSite/Secure/Domain/Path` và third-party cookie policy. Nếu browser không gửi OPTIONS, kiểm có phải preflight cache, request safelisted hoặc CSP `connect-src` chặn trước.

### Bước 10 — Ghi nhận regression và release gate

Lưu kết quả 60 cases theo version/config, browser matrix, public hostname, thời điểm, policy revision và request ID đã redact. Khi thay allowed origins/headers, filter chain order, proxy hoặc session model, chạy lại positive **và** negative tests trước phát hành.

### 22.1. Kết quả kỳ vọng của một buổi thực hành

~~~text
[PASS] Allowed Origin OPTIONS POST không cookie -> ACAO chính xác
[PASS] Denied Origin -> no ACAO attacker
[PASS] Method DELETE -> denied
[PASS] Header x-admin-override -> denied
[PASS] OPTIONS không tạo order
[PASS] Actual POST thiếu CSRF -> 403, DB unchanged
[PASS] Actual POST sai tenant -> denied, DB unchanged
[PASS] Public edge headers không duplicate
[PASS] Browser allowed origin có thể đọc probe response
[PASS] Browser denied origin không đọc được probe response
[PASS] Không mở /admin/** qua allowlist /api/**
[PASS] Không cần auth cho preflight nhưng actual vẫn cần auth.
~~~

**Không báo “CORS an toàn” chỉ từ GET 200 hoặc OPTIONS 200**. Phải có negative origin/method/header, auth/CSRF và browser/server evidence.

## 23. Checklist triển khai và review pull request

| Hạng mục | Tiêu chí kiểm chứng |
|---|---|
| **Danh sách origins** | Exact HTTPS origins đã phê duyệt; không phản chiếu `Origin` tùy ý |
| **Scheme/port** | Xác định rõ dev/test/prod, tránh mở HTTP dev trong prod |
| **Origin null** | Bị từ chối mặc định |
| **Subdomain patterns** | Không wildcard ngoài yêu cầu; kiểm takeover/lookalike |
| **Allowed methods** | Chỉ methods API thật cần, test DELETE/PATCH rõ |
| **Allowed request headers** | Chỉ header names cần, gồm CSRF/Authorization nếu áp dụng |
| **Exposed response headers** | Chỉ header JS thật cần; không tưởng `Set-Cookie` đọc được |
| **AllowCredentials** | Bật chỉ khi cần browser credentials, không dùng ACAO wildcard |
| **CSRF của browser session** | POST/PUT/PATCH/DELETE chịu CSRF token nếu dùng ambient cookie |
| **Authentication** | Preflight không cần cookie; actual request phải auth |
| **Authorization** | ACL theo user/tenant/object; CORS không là role |
| **Security chain selection** | `/api/**` OPTIONS vào chain/processor đúng |
| **CORS filter order** | Xử lý preflight trước authentication entrypoints |
| **OPTIONS permitAll** | Không dùng thay CORS processor; nếu cần matcher thì scope hẹp |
| **Session cookie** | Secure, HttpOnly, SameSite, Domain/Path và browser privacy policy |
| **OAuth/OIDC** | Login redirect/token state là flow riêng, không thay CSRF/CORS |
| **Spring MVC CORS** | `@CrossOrigin`/`WebMvcConfigurer` không xung đột source tập trung |
| **Filter duplication** | Không có hai owner ghi ACAO trái nhau |
| **Response errors** | 401/403/5xx đúng status, ACAO nhất quán cho allowed origins |
| **Response Vary** | Cache phân biệt origin/requested method/headers |
| **Preflight Max-Age** | Giá trị được phê duyệt, test policy changes có fresh context |
| **Route scope** | Không cấp CORS cho admin/actuator chỉ vì cần /api browser |
| **Proxy/CDN** | Public edge giữ method OPTIONS, origin validation, Vary/ACAO |
| **CSP connect-src** | Frontend cho phép đúng API origin, không nhầm với backend CORS |
| **PNA/private network** | Đánh giá riêng, không mở rộng private access tùy tiện |
| **No side effects** | OPTIONS không gọi business write; denied POST không ghi DB |
| **Unit test** | MockMvc allowed/denied origins/methods/headers |
| **Integration** | HTTP public endpoint với allowed/denied origins |
| **Browser E2E** | Approved frontend và attacker frontend ở origins thật |
| **Logs** | Không ghi credential/cookie/CSRF value hoặc arbitrary header payload |
| **Incident response** | Có cây chẩn đoán xác định lỗi ở preflight/actual/proxy/CSRF |
| **Change management** | CORS allowlist và security chain thay đổi phải qua review/regression |

### 23.1. Phiếu debug một preflight

~~~text
Case ID: CORS-XX
Environment: local/test/staging/production
Public API URL: https://api.example.com/api/orders
Request method observed: OPTIONS
Origin: classification ALLOWED / DENIED / NULL / ABSENT
Requested actual method: POST
Requested header names: content-type,x-csrf-token
CORS source mapping: /api/**
Selected security chain: browser-api / m2m / other
Filter owner: Spring / gateway / other
Status: 200 / 401 / 403 / 404 / 405 / ...
ACAO present and exact: yes/no
ACAM contains method: yes/no
ACAH covers requested headers: yes/no
ACAC matches credential contract: yes/no
Vary correct: yes/no
Actual request sent by browser: yes/no
Actual auth and CSRF outcomes:
Business side effects observed: yes/no
Browser/network error classification:
Remediation owner and regression test:
~~~

Không đưa giá trị `Cookie`, `Authorization`, `X-CSRF-TOKEN`, access token, session ID hoặc thông tin cá nhân vào ticket. Log `Origin` cũng cần length/syntax validation và redaction khi chứa chuỗi không tin cậy quá dài.

### 23.2. Khi thay đổi security chain hoặc CORS policy

Một thay đổi nhỏ như “cho thêm `PATCH`” có thể làm browser gửi actual requests mà trước đó preflight chặn. Vì vậy:

1. Review API methods/authorization tương ứng.
2. Review CSRF matcher với PATCH/DELETE.
3. Review method-level security/service ACL.
4. Review allowed origins và header list.
5. Test phương thức mới từ approved frontend.
6. Test attacker Origin vẫn denied.
7. Test denied method khác vẫn denied.
8. Test 401/403 statuses qua public edge.
9. Kiểm preflight cache và browser old sessions.
10. Cập nhật inventory/release notes theo workflow.

**Không** dùng thay đổi CORS để “cấp quyền” cho API method mà chưa có controller/authz phù hợp.

## 24. Bài tập thực hành và đáp án định hướng

### Bài 1 — OPTIONS 401 dù Origin đúng

**Tình huống:** Frontend gửi `POST JSON` và browser có preflight từ `https://portal.example.net`. Server trả `401` cho OPTIONS; khi dùng Postman gửi POST với token thì lại được 201.

**Câu hỏi:** Lỗi có chắc là token không hợp lệ không? Chữa thế nào?

**Gợi ý:** Preflight browser thông thường không gửi cookie/authentication. Kiểm CORS được xử lý trước Spring authentication bằng `http.cors()` và CORS source đúng path/chain; không bắt OPTIONS phải login và không bỏ auth cho actual POST.

### Bài 2 — CORS “200 OK” nhưng browser vẫn chặn

**Tình huống:** OPTIONS trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: POST
~~~

Frontend dùng `credentials: "include"`.

**Gợi ý:** ACAO wildcard không hợp lệ với credentialed CORS; cần exact allowed origin và ACAC true nếu app chủ đích cho cross-origin credentials. Việc đổi header không tự cấp session/authz hoặc CSRF.

### Bài 3 — Header X-CSRF-TOKEN bị cấm

**Tình huống:** OPTIONS từ allowed origin hỏi `content-type,x-csrf-token`, server trả 403.

**Gợi ý:** Kiểm `CorsConfiguration.allowedHeaders` có tên `X-CSRF-TOKEN` và `Content-Type` chưa; đừng nhầm cho phép header name với bỏ token value validation. Actual POST vẫn cần `CsrfFilter`.

### Bài 4 — Host nhìn giống được allow

**Tình huống:** App có custom Origin check `origin.startsWith("https://portal.example.net")`. Browser từ `https://portal.example.net.attacker.invalid` nhận ACAO phản chiếu.

**Gợi ý:** Đây là origin allowlist bypass. Sử dụng exact origin validation bằng Spring CORS processor hoặc cấu hình pattern được audit; test lookalike host/scheme/port.

### Bài 5 — Preflight pass nhưng order được tạo không cần CSRF

**Tình huống:** Security team chỉ test OPTIONS allowed/denied. Sau đó attacker gửi form POST thay đổi dữ liệu và endpoint xử lý vì `csrf.disable()`.

**Gợi ý:** CORS không chặn mọi request, đặc biệt simple form/navigation và nonbrowser clients; bật CSRF cho session-cookie write endpoints, kiểm authorization và no-side-effects tests.

### Bài 6 — Đăng nhập thành công nhưng browser không gửi session cookie

**Tình huống:** SPA ở `portal.example.net` gọi API `api.example.com` với `credentials: "include"`, preflight 200, actual POST 401. Cookie có `SameSite=Lax`.

**Gợi ý:** Lax cookie thường không đi cross-site fetch; kiểm cookie Scope/Secure/SameSite, browser 3PC policy và auth architecture. ACAC true không ép cookie xuất hiện. Có thể cân nhắc BFF/same-origin API hoặc cookie policy được review thay vì tắt authentication.

### Bài 7 — CDN thêm ACAO wildcard

**Tình huống:** `MockMvc` thấy exact ACAO nhưng Chrome thấy hai ACAO headers.

**Gợi ý:** Proxy/CDN có thể thêm wildcard. Xác định owner CORS policy, bỏ header trùng, test public edge với hai origins và `Vary`. Không mặc định browser chọn giá trị hợp lệ.

### Bài 8 — Tại sao GET có thể không có OPTIONS?

**Tình huống:** Frontend `GET` một resource với headers safelisted, không thấy OPTIONS; developer kết luận CORS filter không chạy.

**Gợi ý:** CORS-safelisted request có thể không cần preflight; browser vẫn kiểm ACAO trên **actual response**. Preflight cache cũng có thể loại OPTIONS ở lần gọi sau. Tạo GET với custom header phù hợp nếu muốn test preflight.

### Bài 9 — CORS sai hay CSP chặn trước?

**Tình huống:** Browser console có `Refused to connect ... because it violates Content Security Policy directive connect-src 'self'`, Spring không thấy request.

**Gợi ý:** Frontend CSP chặn fetch trước; phải cho API origin trong `connect-src` của frontend nếu được duyệt. Backend CORS vẫn là policy riêng phải kiểm. Không mở `Access-Control-Allow-Origin: *` để chữa CSP.

### Bài 10 — Origin null trong iframe sandbox

**Tình huống:** Một trang sandbox gửi `Origin: null`, developer đề nghị allow origin này vì “không thuộc attacker domain”.

**Gợi ý:** `null` đại diện nhiều opaque contexts; không phải một origin đáng tin cậy. Tránh allow mặc định, thay bằng frontend HTTPS origin có kiểm soát hoặc kiến trúc message/capability thích hợp.

### Bài 11 — Max-Age khiến chính sách test “không đổi”

**Tình huống:** Team xóa origin partner khỏi allowlist, nhưng browser đang mở vẫn không gửi OPTIONS ở lần gọi sau.

**Gợi ý:** Browser có thể dùng preflight cache cho cùng request context; dùng fresh browser context, chờ expiry hoặc thay test partition/path phù hợp. Kiểm actual response CORS và server authz, không suy rằng policy chưa deploy.

### Bài 12 — Hai SecurityFilterChains trùng matcher

**Tình huống:** `@Order(1)` stateless bearer chain match `/api/**`; browser chain có CORS ở order 2. OPTIONS SPA tới `/api/browser/orders` trả 401.

**Gợi ý:** Chain đầu match trước nên CORS browser chain không chạy. Sửa route matchers và order; gắn CORS source vào đúng chain, không thêm permitAll `/**` hoặc bỏ Bearer auth.

### Bài 13 — Origin được duyệt nhưng Bob xem order của Alice

**Tình huống:** Preflight và CORS headers hoàn toàn đúng, nhưng backend `GET /api/orders/42` chỉ kiểm `authenticated()`, không kiểm owner.

**Gợi ý:** Đó là BOLA/IDOR, không phải lỗi CORS. Kiểm object ACL/tenant ở service và không cache private responses cho user khác.

### Bài 14 — 403 của CorsProcessor khác 403 của CsrfFilter

**Tình huống:** Hai requests đều trả 403: `OPTIONS` từ attacker và `POST` từ portal có session nhưng không CSRF token.

**Gợi ý:** OPTIONS bị CORS processor từ chối vì Origin, actual POST bị CSRF filter từ chối. Kiểm request method, Origin, Access-Control-Request-Method, selected filters, security logs đã redact và side effects. Không sửa cả hai bằng wildcard CORS hoặc `csrf.disable()`.

### Bài 15 — Header Authorization và Cookie API

**Tình huống:** Browser SPA Bearer client gửi `Authorization: Bearer ...` tới `/api/bearer/**`, preflight fail vì allowedHeaders chỉ có Content-Type.

**Gợi ý:** Nếu endpoint được thiết kế cho SPA Bearer và origin được tin cậy, thêm `Authorization` vào CORS allow headers trên **đúng route**; Resource Server vẫn phải validate JWT/opaque token. Không bật CORS tùy ý cho M2M endpoints không có browser clients.

### Bài 16 — Đánh giá một security incident

Một team báo “CORS blocked” và nêu duy nhất đoạn JavaScript `TypeError: Failed to fetch`.

**Yêu cầu:** Nêu ít nhất tám thông tin cần thu thập.

**Gợi ý:** Frontend origin; API URL; method; request headers; credentials mode; preflight có/không; preflight status/ACAO/ACAM/ACAH/ACAC; actual status và headers; Cookie/SameSite classification; selected chain; proxy owner; browser Console CSP/TLS/network error; no-side-effects; request ID. Không thu raw secrets.

## 25. Câu hỏi tự đánh giá và lời giải

**Câu 1.** Một request được coi là CORS preflight tiêu chuẩn theo cấu trúc HTTP nào?

**Đáp án:** Thường là `OPTIONS` có `Origin` và `Access-Control-Request-Method`; có thể kèm `Access-Control-Request-Headers` khi actual request dùng headers cần hỏi phép.

**Câu 2.** `Access-Control-Request-Method: POST` có nghĩa server đang nhận POST không?

**Đáp án:** Không. Request hiện tại là OPTIONS; header chỉ mô tả method của actual request mà browser định gửi sau preflight.

**Câu 3.** Browser preflight có nhất thiết mang `JSESSIONID` hoặc Bearer token không?

**Đáp án:** Không. Preflight theo browser thường không có credentials của user, nên CORS cần được xử lý trước authentication. Actual request mới có credential theo Fetch/cookie policy.

**Câu 4.** Vì sao `OPTIONS /api/orders` trả 200 không chứng minh origin được phép?

**Đáp án:** Browser còn cần `Access-Control-Allow-Origin` và khi cần `Allow-Methods`/`Allow-Headers`/`Allow-Credentials` tương ứng; một OPTIONS permitAll nhưng thiếu CORS headers vẫn có thể bị browser từ chối.

**Câu 5.** Với `Origin: https://attacker.example.org` không trong allowlist, assertion nào quan trọng?

**Đáp án:** Không được cấp ACAO cho attacker; với Spring DefaultCorsProcessor trên route có policy, thường có 403. Cần kiểm cả origin/method/headers, không chỉ status.

**Câu 6.** `https://portal.example.net:8443` có cùng origin với `https://portal.example.net` không?

**Đáp án:** Không. Origin gồm scheme, host và port; khác port là khác origin. Không dùng prefix matching để cho phép cả hai.

**Câu 7.** `Origin: null` có đồng nghĩa origin tin cậy của ứng dụng không?

**Đáp án:** Không. Nó có thể đại diện sandbox/opaque/file contexts; không allow mặc định.

**Câu 8.** Tại sao `POST application/json` từ browser cross-origin thường preflight?

**Đáp án:** `application/json` không thuộc CORS-safelisted Content-Type; browser hỏi trước với OPTIONS. Ngoài ra custom header `X-CSRF-TOKEN` cũng có thể kích hoạt preflight.

**Câu 9.** GET cross-origin có phải lúc nào cũng preflight không?

**Đáp án:** Không. GET với các request headers safelisted thường không cần preflight. GET thêm `Authorization` hoặc header tùy chỉnh thường cần.

**Câu 10.** Khi muốn cho frontend gửi header `X-CSRF-TOKEN`, dùng response header nào?

**Đáp án:** `Access-Control-Allow-Headers` trên preflight. Tuy nhiên giá trị CSRF token vẫn được `CsrfFilter` kiểm riêng trên actual POST.

**Câu 11.** Khi muốn JS đọc `X-Request-ID` từ response, dùng header nào?

**Đáp án:** `Access-Control-Expose-Headers: X-Request-ID` trên actual CORS response, nếu header không thuộc danh sách response-safelisted.

**Câu 12.** Có thể expose `Set-Cookie` để JavaScript đọc raw session cookie không?

**Đáp án:** Không. `Set-Cookie` là forbidden response header name; browser không cho JS đọc theo cách đó. Session cookie nên có HttpOnly và được quản lý qua browser.

**Câu 13.** Vì sao ACAO `*` không phù hợp với credentialed fetch?

**Đáp án:** Credentialed cross-origin response không được browser expose nếu ACAO là wildcard. Phải dùng exact allowed Origin và ACAC true khi server chủ đích cấp quyền.

**Câu 14.** `Access-Control-Allow-Credentials: true` có làm browser luôn gửi cookie `SameSite=Lax` vào cross-site fetch không?

**Đáp án:** Không. Cookie gửi hay không còn phụ thuộc credentials mode, Domain/Path/Secure/SameSite và third-party cookie policy. ACAC chủ yếu là phần của CORS policy khi đọc response.

**Câu 15.** Khi preflight pass nhưng POST trả 403, nên sửa CORS đầu tiên không?

**Đáp án:** Không. Trước hết xác định actual 403 là CSRF, authorization hay custom policy. Nếu là CSRF/token thiếu, phải sửa token/session, không nới ACAO.

**Câu 16.** Vì sao CORS không thay CSRF?

**Đáp án:** CORS không chặn mọi loại request cross-origin được gửi (form/simple requests có thể đến server) và không áp với nonbrowser clients. Browser session-cookie unsafe mutations vẫn cần CSRF và authorization.

**Câu 17.** Một controller nhận `@CrossOrigin("*")` có tự xác thực user không?

**Đáp án:** Không. CORS chỉ điều chỉnh browser JS đọc response theo policy; authentication/session/JWT và object-level authorization là các lớp riêng.

**Câu 18.** `HttpSecurity.cors(Customizer.withDefaults())` giúp xử lý vấn đề nào?

**Đáp án:** Tích hợp CORS policy vào Spring Security, cho preflight được xử lý trước authentication khi source phù hợp. Nó không tự tạo allowlist an toàn hoặc miễn CSRF cho actual requests.

**Câu 19.** Vì sao không dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` làm giải pháp duy nhất?

**Đáp án:** PermitAll cho OPTIONS không phát đầy đủ ACAO/ACAM/ACAH và có thể mở scope rộng không cần thiết. Cần CORS processor/source đúng path/order.

**Câu 20.** Nếu `MockMvc` pass nhưng browser thấy duplicate ACAO, nguồn lỗi có thể ở đâu?

**Đáp án:** Reverse proxy/CDN/gateway có thể thêm header ngoài Spring. Test HTTP public edge và chọn một owner policy.

**Câu 21.** Vì sao phải kiểm `Vary: Origin` khi server trả ACAO khác nhau theo Origin?

**Đáp án:** Shared HTTP caches cần phân biệt response theo Origin để tránh phục vụ headers/policy của frontend A cho frontend B. Với preflight, còn phải xem requested method/headers.

**Câu 22.** `Access-Control-Max-Age: 600` có chắc browser cache preflight đúng 600 giây không?

**Đáp án:** Không. Browser có giới hạn/cache partition riêng. Test thay policy có thể cần fresh browser context và vẫn phải kiểm actual response.

**Câu 23.** Một attacker dùng curl đặt `Origin: https://portal.example.net` có thể được cấp user role không?

**Đáp án:** Không. Header Origin có thể bị giả trong nonbrowser clients, không là credential hoặc authority. Backend phải kiểm token/session và permissions.

**Câu 24.** Một API trả 401 JSON nhưng frontend báo CORS error có thể do đâu?

**Đáp án:** Error response thiếu ACAO/ACAC hoặc proxy ghi headers khác; cần kiểm Network actual status và response CORS policy, không đổi 401 thành 200.

**Câu 25.** `Sec-Fetch-Site` và `Origin` có thay token CSRF hoàn toàn không?

**Đáp án:** Không mặc định. Chúng có thể là defense-in-depth với chính sách theo endpoint, nhưng request contexts, browser support và nonbrowser spoofing phải được xét; session-cookie unsafe endpoints vẫn nên có cơ chế CSRF phù hợp.

**Câu 26.** Nếu API là Bearer-only M2M, có bắt buộc bật CORS để worker gọi được không?

**Đáp án:** Không. M2M HTTP clients không bị browser SOP/CORS. CORS chỉ cần nếu có browser JS cross-origin client; API vẫn cần token validation/authz.

**Câu 27.** Vì sao `SameSite` và CORS không có cùng phạm vi?

**Đáp án:** SameSite dựa trên site và điều khiển cookie gửi trong một số ngữ cảnh; CORS dựa trên origin và điều khiển JS cross-origin resource access. Hai subdomains có thể same-site nhưng cross-origin.

**Câu 28.** Một CSP `connect-src 'self'` của SPA có thể làm test CORS false positive không?

**Đáp án:** Có. CSP có thể chặn fetch trước khi API nhận preflight; cần cho API origin trong CSP test page hoặc quan sát Network để biết CORS có thực sự được kiểm.

**Câu 29.** Preflight bị chặn có chứng minh business service không thể bị gọi bằng request từ attacker không?

**Đáp án:** Không. Attacker có thể dùng nonbrowser client hoặc request không cần preflight; server phải bảo vệ authentication/CSRF/authorization và không có side effects trái phép.

**Câu 30.** Khi browser JavaScript nhận TypeError thay vì 403, thông tin nào cần kiểm đầu tiên?

**Đáp án:** Network có OPTIONS không, response status/headers, actual request có được gửi không, Console CSP/CORS/TLS errors, proxy ownership, cookie credential behavior và request ID.

## Kết luận

**Kiểm tra CORS preflight và origin bị từ chối** là bài tập cốt lõi để hiểu ranh giới giữa **browser policy**, **Servlet filters** và **Spring Security**. Một `OPTIONS` preflight có `Origin`, `Access-Control-Request-Method` và đôi khi `Access-Control-Request-Headers`; nó có thể đến **không mang session cookie**, nên phải được xử lý bởi CORS processor **trước authentication** nếu frontend origin/method/headers hợp lệ.

Một cấu hình tốt không chỉ cấp `Access-Control-Allow-Origin` cho frontend được phê duyệt mà còn **từ chối chính xác** attacker origin, lookalike hostname, khác scheme/port, origin `null`, method và request headers không cho phép. Với credentialed CORS, response phải dùng **exact origin**, không dùng wildcard `*`; `Access-Control-Allow-Credentials` không thay authentication, không ép SameSite cookie được gửi và không cấp quyền nghiệp vụ.

**Preflight thành công không cho phép bỏ Spring CSRF token**. Actual POST vẫn phải qua authentication, `CsrfFilter` khi browser dùng session cookie, role/tenant/object authorization và business validation. Một form cross-site hoặc client không phải browser có thể gửi request không bị ràng buộc bởi CORS theo cùng cách, nên CORS **không thể là lớp chống CSRF hoặc xác thực duy nhất**.

Trong Spring Security Servlet, dùng `CorsConfigurationSource` với `HttpSecurity.cors()` đúng `SecurityFilterChain` và URL scope, tránh duplicated policy giữa Spring MVC, Servlet CorsFilter và CDN/gateway. **MockMvc** xác minh header/filter behavior, **HTTP integration** xác minh public edge, còn **browser E2E** chứng minh browser thực thi preflight, CORS, cookie SameSite và CSP. Cả positive/negative tests phải kiểm **không có side effects** khi request bị từ chối.

Cách áp dụng nhất quán module **SPRING_SECURITY_HTTP_PROTECTION** là: *mở CORS tối thiểu cho những frontend origins thực sự cần; kiểm tra preflight không yêu cầu credential, nhưng không làm suy yếu CSRF, xác thực, phân quyền và security headers của request thật.*

## Tài liệu tham khảo

- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS phải được xử lý trước Spring Security, `http.cors` và `CorsConfigurationSource`.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): MVC global/handler CORS mappings, `@CrossOrigin` và `CorsConfiguration`.
- [Spring Framework — CorsConfiguration API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowed origins, patterns, methods, headers, credentials và max age.
- [Spring Framework — UrlBasedCorsConfigurationSource API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/UrlBasedCorsConfigurationSource.html): register URL path-specific CORS policies.
- [Spring Framework — CorsUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsUtils.html): nhận diện CORS/preflight requests.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CsrfFilter, CSRF token lifecycle, SPA integration.
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher order và authorization.
- [Spring Security — Testing Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, spring-security-test và bảo vệ request.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, CORS request/response headers và credentialed requests.
- [MDN — CORS preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request): khái niệm, OPTIONS và preflight cache.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): exact origin và wildcard.
- [MDN — Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials): credentialed browser requests.
- [MDN — Access-Control-Request-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Request-Headers): requested non-safelisted headers.
- [MDN — Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers): allowlist request headers.
- [MDN — Access-Control-Max-Age](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Max-Age): preflight cache.
- [MDN — Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary): HTTP cache variation.
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `omit`, `same-origin` và `include`.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): SameSite, Secure và cookie scope.
- [MDN — Content-Security-Policy: connect-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src): frontend CSP fetch destinations.
- [WHATWG Fetch Standard](https://fetch.spec.whatwg.org/): mô hình CORS request, preflight, credential modes và preflight cache.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF token, Origin checks và SameSite defense-in-depth.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): authentication, authorization và API hardening.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): OPTIONS, safe methods và HTTP semantics.
