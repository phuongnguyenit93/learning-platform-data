# Phân biệt 401, 403 và lỗi từ chối yêu cầu ở firewall

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Ba phản hồi trông giống nhau nhưng có thể đến từ ba tầng khác nhau

Một ứng dụng Spring Boot có API `/admin/report`. Người dùng gửi request rồi thấy:

~~~http
HTTP/1.1 401 Unauthorized
~~~

hoặc:

~~~http
HTTP/1.1 403 Forbidden
~~~

Một request khác chứa URL không bình thường có thể nhận:

~~~http
HTTP/1.1 400 Bad Request
~~~

Ba kết quả này **không chỉ khác nhau về con số**:

- **401 Unauthorized** thường thể hiện client chưa cung cấp bằng chứng xác thực hợp lệ để truy cập tài nguyên, và có cơ chế thử xác thực theo HTTP.
- **403 Forbidden** thường thể hiện server hiểu request nhưng từ chối cấp quyền hoặc một lớp kiểm soát khác từ chối thao tác.
- **Request bị HTTP firewall từ chối** thường nghĩa là dạng request bị coi là không hợp lệ/không an toàn **trước bước đánh giá authorization thông thường**. HTTP status cuối cùng có thể là 400, 403 hoặc giá trị khác tùy tầng và cấu hình xử lý ngoại lệ; không được nhận diện firewall chỉ bằng status.

Trong thực tế, 403 còn xuất hiện từ **CSRF**, **CORS**, reverse proxy/WAF hoặc code nghiệp vụ. Một trang web có thể báo lỗi CSP hay CORS mà **backend thậm chí không nhận request**. Vì vậy kỹ năng chẩn đoán quan trọng là xác định **tầng đã từ chối**, không đơn thuần diễn giải mã HTTP.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích 401, 403 theo ngữ nghĩa HTTP và cách Spring Security chọn `AuthenticationEntryPoint`/`AccessDeniedHandler`.
2. Phân biệt `AuthenticationException`, `AccessDeniedException`, CSRF và `RequestRejectedException` của HTTP firewall trên Servlet.
3. Tìm bằng chứng HTTP/log để biết lỗi đến từ Spring Security, container, reverse proxy/WAF, CORS hay trình duyệt.
4. Tái hiện an toàn bằng `curl`, MockMvc và WebTestClient, bao gồm request anonymous, user thiếu quyền, token không hợp lệ và CSRF.
5. Áp dụng cách suy luận tương ứng ở Spring Security **Servlet** và **Reactive/WebFlux** mà không nhầm hai bộ filter.
6. Khắc phục lỗi cấu hình với thay đổi tối thiểu, **không tắt firewall, CSRF, CORS hoặc authorization để làm request trả 200**.

## 2. Bắt đầu từ đường đi của request, không bắt đầu từ status

Một request có thể bị từ chối trước khi controller chạy:

~~~mermaid
flowchart TD
    A[Browser hoặc HTTP client] --> B[CDN / WAF / Reverse proxy]
    B --> C[Web server / Servlet container]
    C --> D[Spring Security FilterChainProxy]
    D --> E{HTTP firewall chấp nhận request?}
    E -- Không --> F[RequestRejectedException / xử lý request bị từ chối]
    E -- Có --> G[Security filters: CORS, CSRF, auth, authorization...]
    G --> H{Đã đủ xác thực?}
    H -- Chưa --> I[AuthenticationEntryPoint: có thể 401 hoặc redirect]
    H -- Rồi --> J{Đủ quyền?}
    J -- Không --> K[AccessDeniedHandler: thường 403]
    J -- Có --> L[Controller / Business logic]
    L --> M[Response thành công hoặc lỗi nghiệp vụ]
    B --> N[Proxy/WAF cũng có thể tự từ chối]
    C --> O[Container cũng có thể tự từ chối]
~~~

Sơ đồ thể hiện **ý tưởng phân tầng**, không phải thứ tự chính xác của mọi filter trong mọi cấu hình. Ví dụ CSRF hoặc CORS có thể từ chối trước khi request tới bước authorization; một authentication filter có thể tự gọi entry point; HTTP firewall được tích hợp trong `FilterChainProxy` Servlet ở điểm xử lý request trước khi chọn chain bảo mật.

| Tầng | Cơ chế có thể từ chối | Dấu hiệu đáng tìm |
|---|---|---|
| Browser | CSP, mixed content, CORS ở khía cạnh đọc response | Console/DevTools, request có thể không tới server |
| CDN/proxy/WAF | Block rule, giới hạn URI/header, rate limit, auth ở gateway | Response có dấu hiệu edge, trace ID, log proxy |
| Servlet container / HTTP server | URL hoặc header sai cú pháp, quá dài, kích thước vượt giới hạn | Access/error log container, có thể không tới Spring |
| Spring HTTP firewall | `StrictHttpFirewall`, `RequestRejectedException` | Log firewall/`FilterChainProxy`, handler request rejection |
| Spring Security authentication | Thiếu/sai credentials, session/token hết hạn | Authentication entry point, `WWW-Authenticate`/redirect |
| Spring Security authorization | Đã xác thực nhưng thiếu authority/role | AccessDeniedHandler, security decision |
| Spring Security CSRF/CORS | Token CSRF không hợp lệ, preflight/origin bị từ chối | CSRF/CORS log, status thường 403 |
| Controller/service | Lỗi quy tắc nghiệp vụ, `ResponseStatusException`, custom handler | Handler/controller đã chạy, application log |

**Hỏi câu này trước:** Request đã đi đến đâu? Nếu request bị firewall hoặc container từ chối, không có lý do để tìm một dòng `@PreAuthorize` trong controller trước tiên.

## 3. 401 Unauthorized: xác thực chưa đủ hoặc không hợp lệ

Theo HTTP, phản hồi **401 Unauthorized** dùng cho request thiếu thông tin xác thực hợp lệ đối với tài nguyên được bảo vệ. Với authentication scheme HTTP phù hợp, response 401 đi kèm header **`WWW-Authenticate`** để chỉ ra cách client có thể xác thực.

Ví dụ HTTP Basic:

~~~http
GET /admin/report HTTP/1.1
Host: app.example.com
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Realm và cách trình bày thực tế phụ thuộc cấu hình. Không nên dùng giá trị ví dụ để khẳng định mọi Spring Security API đều trả chính xác cùng chuỗi challenge.

### Những nguyên nhân 401 thường gặp

- Client chưa gửi `Authorization` hoặc cookie/session cần thiết.
- Credential HTTP Basic không hợp lệ.
- Bearer token không có, sai định dạng, hết hạn, chữ ký sai hoặc không được tài nguyên chấp nhận.
- API yêu cầu xác thực nhưng browser đang có session hết hạn.
- Authentication không được thiết lập vào security context đúng cho request.

Với Bearer token, response có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nhưng các tham số challenge tùy trường hợp và cấu hình. Không được suy từ 401 rằng token nhất định đã hết hạn; cần xem nguyên nhân xác thực thực tế.

### 401 không giống trạng thái “user chưa đăng nhập” trong mọi giao diện

Ứng dụng web dùng **form login** có thể redirect đến trang đăng nhập thay vì trả 401:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Với ứng dụng API dùng HTTP Basic hoặc Bearer resource server, 401 phổ biến hơn. Ngoài ra, một cấu hình custom entry point hoặc ứng dụng pre-auth có thể dùng 403 cho việc chưa được xác thực. Vì vậy **status không đủ để khẳng định user đang anonymous hay đã đăng nhập**.

## 4. 403 Forbidden: không được phép thực hiện request

Một request đã được xác thực nhưng thiếu quyền có thể nhận:

~~~http
GET /admin/report HTTP/1.1
Host: app.example.com
Authorization: Basic <credentials-redacted>
~~~

~~~http
HTTP/1.1 403 Forbidden
~~~

Trong Spring Security, tình huống tiêu biểu là user có một số authority nhưng resource yêu cầu authority khác:

~~~text
User: alice
Authorities: ROLE_USER
Endpoint /admin/report: requires ROLE_ADMIN
=> Access denied
~~~

**Tuy nhiên, 403 không đồng nghĩa chắc chắn “đã login nhưng thiếu ROLE_ADMIN”.** Những lý do khác:

- POST/PUT/PATCH/DELETE không có CSRF token hợp lệ khi CSRF protection áp dụng.
- CORS preflight bị cấu hình server từ chối.
- Bearer token hợp lệ nhưng không đủ scope cho API.
- WAF/proxy từ chối một URL hoặc IP theo rule.
- Application code chủ động trả 403.
- Request chưa được xác thực nhưng entry point/custom handler của hệ thống chọn phản hồi 403.

Với OAuth 2.0 Bearer resource server, trường hợp token hợp lệ nhưng thiếu scope có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Không phải mọi ứng dụng đều bật cách xuất challenge như ví dụ. Cần phân biệt **invalid token → thường 401** với **token hợp lệ nhưng không đủ quyền/scope → thường 403**, rồi kiểm tra thông tin authentication thực tế trong Spring Security.

### Role và authority không phải chuỗi giống hệt nhau

Ví dụ:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Trong cấu hình mặc định, `hasRole("ADMIN")` yêu cầu authority tương ứng `ROLE_ADMIN`. Còn:

~~~java
.requestMatchers("/reports/**").hasAuthority("SCOPE_reports.read")
~~~

kiểm tra một authority có tên chính xác là `SCOPE_reports.read`. Nếu JWT converter, role prefix hoặc mapping claim không đúng, user có thể đăng nhập thành công nhưng vẫn nhận 403. Hãy xem **authority thực tế đã được cấp**, không chỉ nội dung token hoặc vai trò hiển thị trong giao diện.

## 5. AuthenticationEntryPoint, AccessDeniedHandler và ExceptionTranslationFilter

Ở **Spring Security Servlet**, `ExceptionTranslationFilter` là một thành phần quan trọng giúp chuyển các ngoại lệ bảo mật ở phần tiếp theo của filter chain thành phản hồi HTTP hoặc chuyển hướng.

| Tình huống | Cơ chế xử lý thông thường | Kết quả phổ biến |
|---|---|---|
| `AuthenticationException` | `AuthenticationEntryPoint` được cấu hình | HTTP Basic/Bearer thường 401; form login thường 302 |
| `AccessDeniedException` với user đã xác thực đầy đủ | `AccessDeniedHandler` | Thường 403 |
| `AccessDeniedException` nhưng authentication đang anonymous hoặc một số trạng thái remember-me | Có thể khởi động lại authentication qua entry point | 401/302/giá trị cấu hình |
| CSRF token thiếu/sai | CSRF filter có thể dùng access-denied handling của nó | Thường 403 |
| `RequestRejectedException` từ HTTP firewall | Cơ chế xử lý request rejection tại `FilterChainProxy`/container | Thường 400 ở cấu hình hiện đại, nhưng cần xác minh |

**Không phải tất cả ngoại lệ trong hệ thống đều đi qua `ExceptionTranslationFilter`.** Chẳng hạn, firewall có thể từ chối request trước khi security filters xử lý, CORS/CSRF có đường xử lý riêng, và một lỗi ở proxy/container xảy ra trước Spring Security.

### Ví dụ luồng authentication/authorization

~~~mermaid
flowchart TD
    A[Request hợp lệ tới vùng bảo vệ] --> B{Có authentication hợp lệ?}
    B -- Không --> C[AuthenticationEntryPoint]
    C --> D[401 Basic/Bearer hoặc 302 login, tùy cấu hình]
    B -- Có --> E{Đáp ứng quyền yêu cầu?}
    E -- Không --> F[AccessDeniedHandler]
    F --> G[Thông thường 403]
    E -- Có --> H[Controller]
~~~

Đây là **mô hình kết quả thường thấy**, không phải công thức “mọi anonymous đều 401, mọi authenticated đều 403”. Trạng thái `Authentication`, cách xác thực và entry point được cấu hình có thể làm kết quả khác.

## 6. HTTP firewall: từ chối request trước khi xét role

Trong **Servlet stack**, Spring Security thường dùng `StrictHttpFirewall` qua `FilterChainProxy` để áp dụng những giới hạn lên request trước khi request được chuyển qua các security filters.

Một số đặc điểm request có thể bị từ chối, tùy cấu hình và phiên bản:

- URL không được chuẩn hóa như các thành phần đường dẫn bất thường.
- Dấu `;`/path parameter hoặc dạng URL encoding bị chính sách firewall xem là không chấp nhận.
- Encoded slash/backslash hoặc các ký tự không được cho phép.
- HTTP method không nằm trong danh sách chấp nhận hoặc có cách viết không hợp lệ.
- Tên/giá trị header hoặc tham số không thỏa kiểm tra hợp lệ.
- Dấu điều khiển hoặc dạng yêu cầu mà container/proxy cũng có thể từ chối ở tầng trước.

Đây là **giới hạn dạng request**, khác với việc request có user hợp lệ và authority phù hợp hay không. Firewall không cần kiểm tra `ROLE_ADMIN` để từ chối một URL không được phép.

### RequestRejectedException là tín hiệu kỹ thuật quan trọng

Một thông điệp chẩn đoán minh họa:

~~~text
org.springframework.security.web.firewall.RequestRejectedException:
The request was rejected because the URL was not normalized
~~~

Tên và lời nhắn cụ thể thay đổi theo loại lỗi và phiên bản. Nếu log có `RequestRejectedException`, hãy kiểm tra path/header/method thực nhận, cách container/proxy chuẩn hóa request và cấu hình firewall. Đừng sửa `authorizeHttpRequests` hoặc thêm authority nếu request chưa đi tới bước authorization.

### HTTP status của firewall không phải lúc nào là 403

Trong nhiều cấu hình Spring Security Servlet hiện đại, request bị từ chối được chuyển cho một `RequestRejectedHandler` trả **HTTP 400**. Ứng dụng, phiên bản Spring Security, container, proxy hoặc handler tùy biến có thể dẫn đến status khác.

Một số hệ thống có thể ghi lỗi 500 nếu ngoại lệ không được xử lý như mong đợi; WAF có thể trả 403 cho một request tương tự trước khi nó tới Spring.

Vì thế:

> **Dấu hiệu nhận diện firewall đáng tin là vị trí/tác nhân từ chối và log hoặc handler request rejection, không phải chỉ con số 400/403.**

### Không tắt StrictHttpFirewall chỉ để sửa URL lỗi

Một cách khắc phục sai thường thấy là mở toàn bộ dấu chấm phẩy, URL encoding hoặc ký tự mà firewall mặc định chặn, trong khi nguyên nhân thực là proxy rewrite sai hoặc client gửi URL chưa chuẩn hóa.

Trước khi điều chỉnh firewall, hãy:

1. Xác định **giá trị request gốc** và URL mà Spring thực sự nhận.
2. Tìm tầng đầu tiên làm thay đổi hoặc từ chối URL.
3. Xem đường dẫn được ứng dụng yêu cầu có thể biểu diễn bằng URL chuẩn, path variable hoặc query parameter phù hợp không.
4. Nếu thật sự có nhu cầu cho phép một dạng request, đánh giá rủi ro path matching, authorization, proxy/container và có test hồi quy bảo mật trước khi thay đổi cấu hình.

Một ngoại lệ firewall quá rộng có thể tạo **sự khác nhau về cách hiểu URL** giữa container, proxy và Spring Security, làm suy yếu việc khớp security rule.

## 7. So sánh các tình huống bằng ma trận

| Request/tình trạng | Kết quả thường thấy | Lớp cần điều tra đầu tiên |
|---|---|---|
| GET tài nguyên bảo vệ, không có credentials, dùng HTTP Basic | 401 + Basic challenge | Authentication entry point |
| GET tài nguyên bảo vệ, Bearer token không hợp lệ | Thường 401 | Authentication/decoder/entry point |
| GET với user có `ROLE_USER`, endpoint yêu cầu `ROLE_ADMIN` | Thường 403 | Authorization + authorities |
| POST cùng origin, user có quyền nhưng thiếu CSRF token | Thường 403 | CSRF filter |
| Browser preflight OPTIONS gửi origin không được phép | Có thể 403 | CORS processor |
| Request path bị StrictHttpFirewall từ chối | Thường 400, có thể khác | HTTP firewall + rejection handler |
| URL hoặc header sai cú pháp bị container từ chối | Có thể 400/431 hoặc khác | Container/gateway |
| WAF rule chặn một request | Thường 403 hoặc mã do WAF cấu hình | CDN/proxy/WAF |
| CSP `connect-src` chặn `fetch` ở browser | Không nhất thiết có response từ backend | Browser Console/Network |
| Browser nhận API response nhưng CORS không cho đọc | JS có thể thất bại dù server đã xử lý HTTP | CORS/browser và API response |
| Form login yêu cầu xác thực | Có thể 302 tới login | Authentication entry point |
| Controller tự trả `ResponseStatusException(FORBIDDEN)` | 403 | Controller/service |

**Một dòng 403 trong Network không thể thay thế việc định vị filter hoặc tầng đã trả 403.** Hai response cùng status có thể đòi hỏi cách sửa hoàn toàn khác.

## 8. CORS và preflight: 403 không nhất thiết là authorization

Browser có thể gửi preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Nếu backend không có CORS configuration cho origin, method hoặc header tương ứng, CORS processor có thể từ chối, ví dụ trả 403 hoặc thông báo:

~~~text
Invalid CORS request
~~~

Đây **không phải** bằng chứng user thiếu `ROLE_ADMIN`. Ngược lại, preflight thành công không đồng nghĩa request POST thật đã được authenticated hoặc có đủ CSRF token.

### Một lỗi dẫn đến hai hiện tượng

Ứng dụng có thể cấu hình:

~~~text
Browser -> OPTIONS preflight -> 403 từ CORS
Browser -> không gửi POST thật
~~~

Developer chỉ nhìn backend “không thấy POST” rồi đi sửa JWT hoặc authorization, nhưng nguyên nhân là preflight bị từ chối.

Khi debug:

1. Kiểm tra `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` của preflight.
2. Xác minh CORS config nằm ở **API nhận request**, được tích hợp đúng vào Spring Security chain.
3. Xác định response preflight từ Spring, gateway hay container.
4. Không cấp `Access-Control-Allow-Origin: *` bừa bãi, đặc biệt cho luồng credentials.
5. Sau khi preflight đạt, kiểm tra authentication, CSRF và authorization của **request thực**.

Việc cho qua mọi `OPTIONS` bằng một authorization rule không tự tạo CORS headers đúng. CORS và authorization là hai trách nhiệm liên quan nhưng độc lập.

## 9. CSRF: một 403 với user đã đăng nhập và đủ quyền

Xét form thay đổi dữ liệu:

~~~html
<form method="post" action="/admin/report">
  <button type="submit">Tạo báo cáo</button>
</form>
~~~

Trong ứng dụng dùng session cookie và CSRF protection, request POST thường cần token CSRF hợp lệ. User có thể có `ROLE_ADMIN` nhưng POST vẫn nhận 403 nếu thiếu token.

**Điểm dễ nhầm:** GET `/admin/report` thành công, POST cùng URL bị 403 **không tự chứng minh** rule authorization khác nhau. POST có thể bị `CsrfFilter` từ chối trước khi controller chạy.

Khi dùng Thymeleaf và form, cần bảo đảm token CSRF được chèn/đưa vào theo cách Spring Security và template integration của ứng dụng hỗ trợ. Với JavaScript gọi API, cần biết token được lấy và gửi bằng header/field nào; không nên tắt CSRF toàn hệ thống chỉ vì request AJAX trả 403.

### Cùng mã 403, hai nguyên nhân khác nhau

~~~text
GET /admin/report + ROLE_USER
  -> 403 vì không đủ ROLE_ADMIN

POST /admin/report + ROLE_ADMIN + thiếu CSRF token
  -> 403 vì CSRF protection
~~~

Cách khắc phục tình huống đầu là kiểm tra quyền và mapping role. Tình huống thứ hai là bổ sung CSRF token vào request hợp lệ. **Không** khắc phục cả hai bằng cách đổi endpoint thành `permitAll()`.

## 10. Browser CSP, mixed content và CORS có thể khiến “request bị từ chối” mà không có 401/403

Ví dụ frontend HTML trả:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self'
~~~

JavaScript thử:

~~~javascript
fetch("https://api.example.net/orders")
  .catch(error => console.error(error));
~~~

Nếu API không thuộc `connect-src` của tài liệu, browser có thể từ chối kết nối **trước khi server API nhận request**. JavaScript thường thấy lỗi kiểu `TypeError: Failed to fetch`, còn Console có thông báo CSP violation. Không có lý do để tìm 401/403 trong API log nếu request không hề tới backend.

Ngược lại, một request cross-origin có thể thực sự được server xử lý và trả HTTP 200/401/403, nhưng browser không cho JavaScript đọc response vì **CORS**. UI vẫn có thể báo “network error”; HTTP status ở tab Network và exception JavaScript không nhất thiết tương đương.

Trang HTTPS cố tải HTTP hoặc WebSocket `ws:` còn có thể bị browser chặn vì mixed content/TLS. Đây không phải kết quả từ `AuthorizationManager`.

| Quan sát | Hướng xác minh |
|---|---|
| Console nêu `Content Security Policy: connect-src` | Xem CSP trên **response HTML**, không chỉ response API |
| Console nêu `CORS policy` | Xem origin, preflight và CORS response headers của API |
| Console nêu `Mixed Content` | Xem scheme HTTPS/WSS và cấu hình TLS |
| Network có HTTP 401/403 thật | Đối chiếu server/proxy logs và security filters |
| Network không có request thật tới API | Tìm blocker ở browser hoặc bước trước khi gửi |

## 11. Reverse proxy, gateway và WAF: người trả 403 có thể không phải Spring

Kiến trúc thường gặp:

~~~mermaid
flowchart LR
    B[Browser] --> E[CDN / WAF]
    E --> P[Reverse proxy / Gateway]
    P --> S[Spring Security]
    S --> C[Controller]
~~~

Ví dụ WAF chặn một request do rule chống bot hoặc kiểm tra URL, rồi tự trả:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/html
~~~

Request đó có thể **chưa đến container Spring**. Spring Security log không có `AccessDeniedException`, controller không có trace và việc nới role không thay đổi kết quả.

Những dấu hiệu giúp định vị:

- Header/body/error page mang dấu hiệu gateway, CDN hoặc WAF.
- Trace/request ID xuất hiện ở proxy nhưng không xuất hiện ở ứng dụng.
- Đường gọi thẳng origin trong môi trường kiểm soát được cho kết quả khác đường public.
- Chỉ một số vùng edge, user-agent, IP hoặc method gặp lỗi.
- Proxy chuẩn hóa/giải mã URL khác container khiến firewall hoặc route matching thay đổi.

**Không chỉ dựa vào các header được nêu tên để quy nguồn gốc**, vì một gateway có thể thêm header vào cả response từ ứng dụng. Cần đối chiếu access log, trace và cấu hình cụ thể của từng tầng.

### Sự khác nhau về URL normalization

Một URL có đường dẫn lặp, dấu chấm phẩy hoặc encoding đặc biệt có thể:

1. Bị proxy/WAF từ chối ngay.
2. Được proxy rewrite thành đường dẫn khác.
3. Được container từ chối.
4. Đi đến Spring Security rồi bị `StrictHttpFirewall` từ chối.

Nếu không ghi lại **request thực nhận tại từng tầng**, một nhóm có thể nhầm đây là lỗi route `@RequestMapping` hoặc method security. Không nên vô hiệu kiểm tra normalization ở firewall chỉ vì proxy đang gửi URL không chuẩn.

## 12. Quy trình chẩn đoán sáu câu hỏi

Khi nhận một ticket “API trả 401/403”, hãy hỏi theo thứ tự:

1. **HTTP response có thật không?** Browser Console báo CORS/CSP/mixed content hay Network hiển thị một response 401/403 từ server?
2. **Response do tầng nào sinh?** CDN/WAF, proxy, container, firewall, security filter hay controller? Có trace ID/log tương ứng không?
3. **Request nào thất bại?** Method, URL, query, headers cần thiết, `Origin`, cookies, auth scheme, CSRF token? Đã ẩn dữ liệu nhạy cảm chưa?
4. **Authentication state là gì?** Anonymous, session hợp lệ, Basic credentials, Bearer token, remember-me, authenticated principal? Có challenge/redirect không?
5. **Authorization/CSRF/CORS nào áp dụng?** Endpoint đòi role/authority/scope gì, POST có CSRF token chưa, preflight có đúng origin/method/headers không?
6. **Khác biệt theo môi trường?** Direct origin so với public proxy, Servlet so với WebFlux, security chain nào, phiên bản config nào?

Đừng thay đổi nhiều lớp cùng lúc. Chọn **một giả thuyết**, tạo ca tái hiện, lưu bằng chứng, sửa tối thiểu và kiểm thử hồi quy.

### Sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A[Quan sát lỗi ở client] --> B{Có HTTP response 401/403/400?}
    B -- Không --> C[Kiểm tra CSP, CORS, mixed content, DNS/TLS]
    B -- Có --> D{Request tới Spring app không?}
    D -- Không --> E[Kiểm tra CDN/WAF, proxy, container]
    D -- Có --> F{Có RequestRejectedException/firewall log?}
    F -- Có --> G[Điều tra URI/method/header và normalization]
    F -- Không --> H{Có CSRF hoặc CORS rejection?}
    H -- Có --> I[Kiểm tra token hoặc preflight]
    H -- Không --> J{Authentication hợp lệ?}
    J -- Không --> K[Entry point, 401 hoặc redirect tùy scheme]
    J -- Có --> L{Đủ quyền?}
    L -- Không --> M[AccessDeniedHandler, thường 403]
    L -- Có --> N[Kiểm tra controller/business handler]
~~~

Sơ đồ là **heuristic điều tra**, không phải khẳng định request chỉ có thể qua đúng một nhánh. Ví dụ một authentication entry point custom có thể trả 403, hoặc một controller có thể chủ động trả 401; cần xác nhận bằng log và response thực.

## 13. Tái hiện bằng HTTP client: có phương pháp, không làm lộ credentials

Ví dụ giả định ứng dụng lab chạy tại `http://localhost:8080`, có route `/admin/report` bảo vệ bằng HTTP Basic và `ROLE_ADMIN`. Những lệnh dưới đây **không phải yêu cầu phải chạy trong STEP 4**; khi thực hành, chỉ gọi hệ thống bạn có quyền kiểm thử.

### 13.1. Request không có xác thực

~~~bash
curl -i http://localhost:8080/admin/report
~~~

Với HTTP Basic được bật và route yêu cầu authenticated, phản hồi thường là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Nếu thay vì 401 bạn nhận 302 đến `/login`, ứng dụng có thể dùng entry point của form login. Nếu nhận 403, kiểm tra một entry point khác hoặc lớp bảo vệ đi trước; **đừng sửa cấu hình cho tới khi biết ai trả status**.

### 13.2. Request đã xác thực nhưng thiếu quyền

~~~bash
curl -i -u analyst http://localhost:8080/admin/report
~~~

Lệnh dùng `-u analyst` để chương trình hỏi password thay vì đặt mật khẩu trong command line. Giả sử backend có user `analyst` với `ROLE_USER` và credential hợp lệ; phản hồi thường là 403 vì không có `ROLE_ADMIN`.

**Không** dán bearer token, session cookie hoặc mật khẩu thật vào ticket, tài liệu hoặc log. Nếu buộc phải dùng client test, lưu secret trong cơ chế quản lý bí mật/biến môi trường phù hợp và che khi chia sẻ output.

### 13.3. Kiểm tra preflight CORS riêng

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/orders \
  -H 'Origin: https://frontend.example.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Đây là mô phỏng preflight. Response cần được so với **CORS configuration đã chủ đích**, bao gồm origin, method và request headers. Một response 403 kiểu `Invalid CORS request` chỉ ra hướng điều tra khác với GET admin trả 403 vì thiếu role.

Trên Windows PowerShell, `curl` có thể là alias tùy môi trường; dùng chương trình `curl.exe` trực tiếp nếu cần thao tác bằng cú pháp command line như trên. Các ví dụ dùng cú pháp thông dụng của `curl` trong shell POSIX; có thể cần điều chỉnh cách escape/quote khi chạy trong PowerShell.

### 13.4. Kiểm tra dạng URL bị firewall từ chối

~~~bash
curl --path-as-is -i 'http://localhost:8080/api//orders'
~~~

`--path-as-is` giúp kiểm tra một URL mang đặc điểm đường dẫn bất thường mà HTTP client có thể chuẩn hóa ở những tình huống khác. Tuy nhiên, proxy/container vẫn có thể tự chuẩn hóa hoặc từ chối trước Spring.

Nếu kết quả là 400, cần **log firewall hoặc trace đường đi request** để chứng minh nguyên nhân. Nếu 404, có thể request đã đi tới routing. Nếu 403, cũng không đủ kết luận đã đi qua firewall hay authorization.

Để test một trường hợp dấu chấm phẩy chỉ ở môi trường lab:

~~~bash
curl --path-as-is -i 'http://localhost:8080/api;test=1/orders'
~~~

Đừng dùng URL lạ để thử tải vào hệ thống ngoài quyền kiểm soát. Các ví dụ này chỉ hỗ trợ **diagnostics có kiểm soát**, không thay thế unit test của firewall và test qua proxy thực tế.

### 13.5. So sánh public path và origin

Nếu staging có reverse proxy:

~~~bash
curl -i https://staging.example.net/admin/report
~~~

và nếu có quyền gọi trực tiếp upstream:

~~~bash
curl -i http://localhost:8080/admin/report
~~~

Hãy so sánh status, `WWW-Authenticate`, `Location`, response body, trace ID và log tương ứng. **Không suy rằng hai request thật sự giống nhau** nếu `Host`, scheme, cookie, route hoặc auth header khác; lập một bảng so sánh trước khi kết luận gateway là nguyên nhân.

## 14. Spring Security Servlet: cấu hình mẫu để phân biệt 401 và 403

Giả sử ứng dụng Spring MVC sử dụng HTTP Basic cho vùng API lab và có authority theo role:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        );

        // Dùng HTTP Basic để 401 có challenge dễ kiểm tra.
        http.httpBasic(Customizer.withDefaults());

        // Giữ CSRF protection mặc định. Không disable chỉ để test 403.
        return http.build();
    }
}
~~~

Ví dụ controller có cả GET và POST để kiểm tra trường hợp CSRF:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoReportController {

    @GetMapping("/admin/report")
    public String report() {
        return "report ready";
    }

    @PostMapping("/admin/report")
    public ResponseEntity<Void> generateReport() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Giả sử user có `ROLE_USER` và user khác có `ROLE_ADMIN` được định nghĩa trong môi trường test, ta có thể dự đoán:

| Request | Authentication | CSRF | Kết quả |
|---|---|---|---|
| GET `/admin/report` | Anonymous | Không cần cho GET thông thường | Thường 401 (HTTP Basic) |
| GET `/admin/report` | Authenticated, `ROLE_USER` | Không cần | 403 |
| GET `/admin/report` | Authenticated, `ROLE_ADMIN` | Không cần | 200 |
| POST `/admin/report` | Authenticated, `ROLE_ADMIN` | **Thiếu** token khi CSRF áp dụng | 403 |
| POST `/admin/report` | Authenticated, `ROLE_ADMIN` | Token hợp lệ | 204 theo controller |

**Lưu ý:** code security config trên không tạo user/password trong database; MockMvc có thể mô phỏng authentication qua `spring-security-test`. Để gọi thật bằng `curl` có HTTP Basic, backend phải có cấu hình user/credentials hợp lệ. Mã 401/403 trong bảng là kết quả dự kiến **khi đúng cấu hình ví dụ**, không phải quy tắc áp cho mọi project.

### Không dùng permitAll để chữa AccessDeniedException tùy tiện

Một cách sửa sai:

~~~java
// Sai về nguyên tắc nếu endpoint cần chỉ ADMIN mới được truy cập.
.requestMatchers("/admin/**").permitAll()
~~~

Cách này có thể làm 403 biến mất bằng cách **xóa ranh giới authorization**, nhưng không sửa lỗi mapping roles/authorities. Hãy kiểm tra user thực tế có `ROLE_ADMIN` hay không, đường dẫn có khớp matcher mong muốn không, và method security như `@PreAuthorize` có đặt yêu cầu khác không.

## 15. Kiểm thử Servlet với MockMvc: tách ba đường từ chối

Giả sử test dùng `spring-security-test` và Spring Security filters được tích hợp vào MockMvc.

### 15.1. Anonymous → 401

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/admin/report"))
    .andExpect(status().isUnauthorized());
~~~

Khi API dùng HTTP Basic và entry point mặc định phù hợp, có thể kiểm tra thêm header challenge:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/admin/report"))
    .andExpect(header().string(
        "WWW-Authenticate",
        containsString("Basic")
    ));
~~~

Nếu dự án dùng form login, bài test 401 này cần được thay bằng phép kiểm tra redirect theo cấu hình, **không ép form login trả 401 chỉ để khớp một ví dụ**.

### 15.2. Đã login nhưng thiếu role → 403

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/admin/report")
        .with(user("analyst").roles("USER")))
    .andExpect(status().isForbidden());
~~~

`roles("USER")` thiết lập authority theo quy tắc role mặc định, tương ứng `ROLE_USER`. Đây là phép thử authorization, không phải phép kiểm tra tính đúng đắn của mật khẩu.

### 15.3. Có đúng role nhưng POST thiếu CSRF token → 403

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(post("/admin/report")
        .with(user("admin").roles("ADMIN")))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/admin/report")
        .with(user("admin").roles("ADMIN"))
        .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Việc `with(csrf())` giúp test có CSRF token phù hợp theo cơ chế của `spring-security-test`. Hai request chỉ khác token, còn authentication và route như nhau; điều này làm bằng chứng về CSRF mạnh hơn một lần POST nhận 403 không có đối chứng.

Nếu application dùng một CSRF repository hoặc custom request handler khác mặc định, test cần cấu hình tương thích. Không suy rằng `with(csrf())` tự kiểm thử toàn bộ đường truyền token từ browser cookie/template.

### 15.4. Test firewall khác test response handler

Có thể unit-test trực tiếp `StrictHttpFirewall`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertThrows;

class FirewallBehaviorTest {

    @Test
    void rejectsSemicolonPathByDefault() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request = new MockHttpServletRequest(
            "GET", "/api;test=1/orders"
        );
        request.setServletPath("/api;test=1/orders");

        assertThrows(
            RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(request)
        );
    }
}
~~~

Test này kiểm tra **điều kiện firewall từ chối**. Nó không chứng minh HTTP response cuối cùng trả 400 hay 403, vì test không đi qua `RequestRejectedHandler`, servlet container hoặc proxy. Muốn xác nhận status, cần một integration test qua cấu hình hoàn chỉnh và phiên bản Spring Security mà dự án dùng.

**Không sửa firewall để unit test này PASS bằng cách mở toàn bộ semicolon.** Nếu ứng dụng hợp lệ cần path parameter, phải đánh giá yêu cầu nghiệp vụ và những sự khác nhau giữa container, proxy, path matching trước.

## 16. Reactive/WebFlux: cùng ý nghĩa 401/403, khác bộ filter

Spring Security Reactive dùng `SecurityWebFilterChain` thay vì `SecurityFilterChain` Servlet. Cơ chế tương ứng có thể gồm `AuthenticationWebFilter`, `ExceptionTranslationWebFilter`, `AuthorizationWebFilter`, `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`.

**Không mang nguyên class Servlet như `ExceptionTranslationFilter`, `StrictHttpFirewall`, `HttpServletRequest` sang cấu hình WebFlux.** Các tầng xử lý request, exception và HTTP server ở Reactive có API và đường đi khác nhau.

### 16.1. Cấu hình WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveDemoSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        // CSRF có trách nhiệm riêng, không tắt để che lỗi POST.
        return http.build();
    }
}
~~~

Ví dụ controller WebFlux:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveReportController {

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("report ready");
    }

    @PostMapping("/admin/report")
    public Mono<ResponseEntity<Void>> generateReport() {
        return Mono.just(ResponseEntity.noContent().build());
    }
}
~~~

### 16.2. Kiểm thử WebTestClient

Với test đã tích hợp Spring Security:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

// Không có authentication, dùng HTTP Basic: thường 401.
webTestClient.get()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isUnauthorized();

// Có USER nhưng thiếu ADMIN: 403.
webTestClient.mutateWith(mockUser("analyst").roles("USER"))
    .get()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isForbidden();

// Có ADMIN nhưng thiếu CSRF khi POST: 403.
webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
    .post()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isForbidden();

// Có ADMIN và token CSRF hợp lệ: controller trả 204.
webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
    .mutateWith(csrf())
    .post()
    .uri("/admin/report")
    .exchange()
    .expectStatus().isNoContent();
~~~

Các helper cần dependency `spring-security-test` và cấu hình WebTestClient phù hợp với Spring Security. Mỗi test giả định route tồn tại và các thành phần authentication/CSRF tương ứng với config trên.

### 16.3. Firewall trong Reactive: đừng đồng nhất với Servlet

Nếu WebFlux nhận một đường dẫn bất thường, request có thể bị từ chối ở HTTP server, proxy hoặc cơ chế firewall/validation dành cho WebFlux tùy phiên bản và cấu hình. Điều tra cần dựa vào **WebFlux security logs**, request thực nhận, exception thực tế và response, thay vì trông đợi luôn có `org.springframework.security.web.firewall.RequestRejectedException` của Servlet.

Các ví dụ `StrictHttpFirewall`/`HttpFirewall` ở mục 6 và 15 áp dụng cho Servlet. Khi dùng Reactive, tham khảo API firewall phù hợp với phiên bản Spring Security đang sử dụng, và kiểm thử từ HTTP server thật nếu mục tiêu là URL encoding/normalization. Một test WebTestClient mock handler chưa chắc đi qua cùng đường parsing như Netty hoặc reverse proxy của production.

## 17. Log và quan sát: bằng chứng nào nên lưu, cái gì không nên lưu?

Để phân biệt tầng xử lý, có thể bật log có chọn lọc **trên môi trường phát triển/staging có quyền kiểm soát**:

~~~properties
# Chỉ dùng trong môi trường chẩn đoán có kiểm soát.
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.firewall=DEBUG
~~~

Muốn quan sát sâu hơn trong thời gian ngắn có thể cần mức TRACE ở component cụ thể, nhưng phải cân nhắc chi phí và dữ liệu nhạy cảm. **Không bật DEBUG/TRACE toàn hệ thống lâu dài trong production** chỉ để tìm một 403.

### Cần thu thập gì?

| Bằng chứng | Giá trị chẩn đoán |
|---|---|
| Timestamp + request/correlation ID | Ghép request qua CDN, proxy và Spring |
| HTTP method, route/path đã chuẩn hóa và path gốc nếu có thể thu an toàn | Tìm lỗi firewall/path matching |
| Status, `WWW-Authenticate`, `Location` | Phân biệt entry point/redirect |
| Loại principal/authentication, không phải secret | Xác định anonymous vs authenticated |
| Authority/scope cần thiết và authority thực tế đã cấp, theo chính sách log an toàn | Tìm nguyên nhân authorization 403 |
| `CsrfException` hoặc thông tin CSRF validation không chứa token | Nhận diện POST 403 vì CSRF |
| CORS origin/method/header được cho phép hay không | Nhận diện preflight rejection |
| `RequestRejectedException` và loại vi phạm firewall | Nhận diện request bị từ chối trước authorization |
| Upstream status và edge trace | Nhận diện WAF/proxy/container |
| Browser Console/Network (đã che dữ liệu nhạy cảm) | Phân biệt CSP/CORS/mixed content |

### Tuyệt đối tránh đưa vào log/chia sẻ

- Mật khẩu HTTP Basic, bearer token/JWT gốc, session cookie, CSRF token đầy đủ.
- Request/response body chứa thông tin cá nhân, dữ liệu tài chính hoặc bí mật.
- Query string chứa token, API key hoặc dữ liệu nhạy cảm.
- Stack trace/DEBUG output chưa xử lý khi gửi ra kênh công khai.

Thông điệp lỗi trả cho client nên có **mức thông tin vừa đủ**; chi tiết nội bộ phục vụ chẩn đoán nằm trong hệ thống log bảo vệ theo quyền truy cập.

### Nếu không thấy Spring Security log

Không thấy log authentication/authorization có thể vì request:

1. Bị browser chặn trước khi gửi.
2. Bị CDN/WAF/proxy/container từ chối.
3. Đi vào một ứng dụng/service hoặc security chain khác dự kiến.
4. Bị firewall xử lý ở một bước trước các log bạn đang quan sát.
5. Không có log phù hợp do mức logging hoặc correlation chưa đúng.

Đừng kết luận “Spring Security không chạy” chỉ vì không thấy một thông điệp DEBUG cụ thể.

## 18. Nhiều SecurityFilterChain, matcher và method security

Một ứng dụng có thể có **hai chuỗi bảo mật**:

~~~text
SecurityFilterChain A: /api/** → OAuth2 Resource Server/Bearer
SecurityFilterChain B: phần còn lại → Form login/Session
~~~

Trong Servlet, `FilterChainProxy` lựa chọn chain phù hợp theo cơ chế matcher và thứ tự. Một request đi vào **chain khác dự kiến** có thể dẫn tới:

- API trả 302 sang trang đăng nhập thay vì 401 Bearer.
- Route HTML bị yêu cầu token Bearer thay vì session.
- CSRF áp dụng khác với thiết kế endpoint API.
- Authorization rule trong chain dự kiến hoàn toàn không được sử dụng.

### Điều tra theo thứ tự

1. Xác định URL thực nhận sau mọi context path, proxy rewrite và URL normalization.
2. Xem chain nào được chọn, điều kiện `securityMatcher` và thứ tự `@Order`.
3. Xem `authorizeHttpRequests`/`authorizeExchange` trong chain ấy.
4. Xem auth scheme/entry point và CSRF/CORS của chain.
5. Nếu request qua được web authorization, kiểm tra method security tại service/controller.

**Đừng chỉ tìm rule `requestMatchers("/admin/**")`** nếu ứng dụng có `securityMatcher("/api/**")` trên một chain khác. Một request `/admin/report` có thể không đi qua chain bạn đang đọc.

### Method security có thể tạo thêm 403

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public String readReport() {
    return "report";
}
~~~

Ngay cả khi HTTP matcher chỉ yêu cầu `authenticated()`, method này có thể từ chối user thiếu authority. Cần phân biệt 403 phát sinh tại URL authorization với 403 do method security hoặc code nghiệp vụ.

Nếu bạn thay rule HTTP thành `permitAll()` nhưng method vẫn cần scope, việc đó không giúp user thiếu scope truy cập hợp lệ và lại có thể mở rộng bề mặt không mong muốn trước lời gọi method.

## 19. Session hết hạn, remember-me và các trường hợp 401/403 không trực giác

Với ứng dụng dùng cookie session:

~~~text
Lúc đầu:
  Browser có session hợp lệ và ROLE_ADMIN
  GET /admin/report -> 200

Một thời gian sau:
  Session hết hạn
  GET /admin/report -> 302 /login hoặc 401, tùy entry point
~~~

Nếu frontend JavaScript mặc định coi mọi lỗi là “thiếu quyền”, nó có thể hiển thị thông báo sai: session đã hết hạn thực chất là **cần xác thực lại**, không phải role bị thu hồi.

Tình huống khác: user vừa đăng nhập, có authority nhưng POST bị 403 vì CSRF token được lấy từ phiên trước. Trong môi trường nhiều tab hoặc sau khi đổi session, frontend có thể đang giữ token CSRF cũ.

### Những câu hỏi cần xác minh

- Cookie session có được gửi cùng request không? Các thuộc tính `Secure`, `HttpOnly`, `SameSite`, Path và Domain có phù hợp?
- Browser truy cập HTTPS qua proxy nhưng backend nghĩ request là HTTP? Trust proxy/forwarded headers có cấu hình đúng không?
- Authentication trong security context thuộc request nào, có bị thay qua async/reactive pipeline không?
- Cơ chế remember-me có được coi là đủ cho thao tác nhạy cảm hay cần xác thực lại?
- Sau login/logout/đổi session, frontend đã cập nhật CSRF token tương ứng chưa?
- API sử dụng Bearer token độc lập với cookie session hay đang trộn hai cơ chế?

**Không sửa bằng cách kéo dài session vô hạn, cho phép cookie không an toàn hoặc bỏ xác thực lại**. Hãy xác định đúng vòng đời session/token và thiết kế UX phù hợp cho trường hợp cần đăng nhập lại.

## 20. Handler tùy biến: mã status không còn phản ánh đường mặc định

Spring Security cho phép tùy biến cách phản hồi:

- `AuthenticationEntryPoint` quyết định cách bắt đầu authentication khi cần.
- `AccessDeniedHandler` xử lý tình huống từ chối quyền.
- Cơ chế request rejection của HTTP firewall xử lý các request bị từ chối.
- CORS/CSRF có thể có đường xử lý riêng.
- `@ControllerAdvice`, exception handler hoặc gateway có thể tạo/mapping lỗi ở tầng khác.

Một ứng dụng có thể chủ động biến một lỗi authentication thành 403 hoặc trả JSON chuẩn riêng. Vì vậy log “Access denied” không đủ khẳng định response luôn là 403; cần nhìn **handler thực sự được gọi** và status cuối.

### Thiết kế response nhất quán nhưng vẫn giữ ngữ nghĩa

Một API có thể dùng body lỗi chung:

~~~json
{
  "type": "https://app.example.com/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "requestId": "example-request-id"
}
~~~

Ví dụ này chỉ minh họa định dạng lỗi có cấu trúc. Không bắt buộc mọi API phải dùng URL `type` này; trong production nó cần là định danh loại lỗi do hệ thống sở hữu, không phải giá trị sao chép ngẫu nhiên.

Khi thiết kế error response:

1. Giữ ngữ nghĩa 401 cho yêu cầu cần xác thực và 403 cho yêu cầu không được phép nếu đó là kết quả đúng của hệ thống.
2. Giữ challenge `WWW-Authenticate` phù hợp cho HTTP authentication scheme.
3. Không tiết lộ mật khẩu, token, policy nội bộ hoặc chi tiết quyền nhạy cảm trong body lỗi.
4. Dùng request ID để đối chiếu server logs thay vì đưa stack trace cho client.
5. Không ghép CSRF, firewall, CORS và authorization thành một “access denied” mơ hồ trong log nội bộ.

### Khi nào một 403 có thể là quyết định chủ đích?

Một dịch vụ có thể dùng 403 để không tiết lộ chi tiết tình trạng tài nguyên hoặc do chính sách xác thực đặc thù. Việc chọn status phải được review theo HTTP semantics và yêu cầu bảo mật, chứ không nên để mỗi controller tự đổi mã tùy hứng.

Một số API chọn 404 cho tài nguyên người dùng không có quyền biết tới; khi đó **404 cũng không tự chứng minh route không tồn tại**. Trình tự chẩn đoán vẫn phải dựa vào log và nơi sinh response.

## 21. Ba kịch bản điều tra trọn vẹn

### Kịch bản A — 401 từ API Bearer, không phải thiếu role

**Hiện tượng:** frontend gọi `GET /api/me` và nhận 401; nhóm phát triển nghi ngờ API yêu cầu authority sai.

**Bằng chứng cần tìm:**

1. Response có `WWW-Authenticate: Bearer` hoặc challenge tương ứng không?
2. Request có gửi token tới đúng origin/path không?
3. Token có hết hạn, sai issuer/audience hoặc bị decoder từ chối không?
4. Authentication thành công và security context đã có principal chưa?

**Kết luận mẫu:** nếu token bị từ chối trước khi có authentication, sửa mapping role chưa có ý nghĩa. Cần khắc phục vòng đời/token configuration/credentials trước, rồi mới thử authorization.

### Kịch bản B — Cùng user GET 200, POST 403

**Hiện tượng:** admin xem được báo cáo nhưng bấm “Tạo báo cáo” nhận 403.

**Kiểm tra:**

1. POST có đi đúng route và đúng security chain không?
2. Có CSRF token hợp lệ trong header/field theo cấu hình không?
3. Request POST có bị preflight CORS từ chối trước khi gửi không?
4. Khi thêm token CSRF hợp lệ trong **môi trường test**, kết quả có chuyển thành 204/200 theo controller không?
5. Có method-level authorization riêng cho POST không?

**Kết luận mẫu:** nếu POST với token hợp lệ thành công còn POST không token bị 403, nguyên nhân là CSRF, không phải user thiếu `ROLE_ADMIN`. Giữ CSRF protection và sửa cách frontend nhận/gửi token.

### Kịch bản C — URL bình thường 200, URL có semicolon nhận 400

**Hiện tượng:** `GET /api/orders` thành công nhưng `GET /api;test=1/orders` trả 400.

**Kiểm tra:**

1. Response do proxy/container hay Spring trả?
2. Log có `RequestRejectedException` không?
3. URL gốc và URL tới Spring có giữ nguyên phần semicolon không?
4. Firewall có dùng `StrictHttpFirewall` mặc định hay custom?
5. Client có thể biểu diễn tham số bằng query string hoặc path variable an toàn hơn không?

**Kết luận mẫu:** nếu test firewall và log xác nhận URL bị từ chối trước authorization, cấp thêm `ROLE_ADMIN` không thể sửa lỗi. Chọn URL canonical hoặc thiết kế lại request; mọi thay đổi firewall cần security review.

## 22. Bài thực hành tổng hợp

**Bối cảnh:** Xây dựng một ứng dụng Spring Boot lab có các route:

~~~text
GET  /public/ping      công khai
GET  /admin/report     yêu cầu ROLE_ADMIN
POST /admin/report     yêu cầu ROLE_ADMIN và CSRF token phù hợp
GET  /api/orders       dữ liệu thử nghiệm
~~~

**Nhiệm vụ:**

1. Cấu hình Servlet SecurityFilterChain dùng HTTP Basic, giới hạn `/admin/**` bằng `hasRole("ADMIN")` và giữ CSRF protection.
2. Tạo ca GET admin **không authentication**; xác nhận 401 và HTTP Basic challenge.
3. Tạo ca GET với `ROLE_USER`; xác nhận 403 và đối chiếu authorization rule.
4. Tạo ca GET với `ROLE_ADMIN`; xác nhận controller hoạt động.
5. Thử POST với `ROLE_ADMIN` nhưng **không có CSRF token**; xác nhận 403. Thêm token trong test, xác nhận controller trả 204.
6. Gọi một URL bất thường qua `curl --path-as-is` trong môi trường lab. Tìm log hoặc unit test `StrictHttpFirewall` để biết có `RequestRejectedException` không; đừng kết luận chỉ từ HTTP 400.
7. Thử preflight với `Origin` không được phép. Quan sát điểm từ chối của CORS và phân biệt với 403 từ authorization.
8. Tạo một HTML test có CSP `connect-src 'self'`, gọi API từ origin khác, quan sát browser có chặn trước khi gửi hay không.
9. Thêm reverse proxy/WAF giả lập; so sánh response trực tiếp origin và qua public hostname khi rule gateway từ chối.
10. Chuyển các ca 401, 403 do role, 403 do CSRF sang **WebFlux/WebTestClient**, không dùng Servlet firewall class trong WebFlux.
11. Nếu có nhiều security chain, tạo ca đi nhầm chain và giải thích vì sao API có thể nhận redirect 302 thay vì 401.
12. Lập bảng kết quả nêu method/path, authentication state, CSRF/CORS, layer từ chối, HTTP status, log chứng minh và giải pháp nhỏ nhất.

### Câu hỏi tự đánh giá

1. Vì sao HTTP 401 thường đi với `WWW-Authenticate`? Một form-login app có thể trả gì thay 401?
2. HTTP 403 có luôn nghĩa người dùng đã đăng nhập và thiếu role không?
3. Khi user authenticated thiếu `ROLE_ADMIN`, thành phần nào thường xử lý authorization failure?
4. `ExceptionTranslationFilter` có xử lý mọi lỗi HTTP firewall trước filter chain không?
5. Vì sao cần tìm `RequestRejectedException` hoặc điểm từ chối thay vì chỉ nhìn status 400?
6. Một 403 `Invalid CORS request` khác một 403 do `AccessDeniedHandler` ở điểm nào?
7. Vì sao admin gửi GET thành công nhưng POST vẫn có thể bị 403?
8. HTTP firewall từ chối semicolon hoặc path không chuẩn nhằm hạn chế loại vấn đề gì?
9. Vì sao không nên thêm wildcard hoặc tắt `StrictHttpFirewall` để làm request thành công?
10. Khi browser báo lỗi CSP, Spring API có nhất thiết nhận được request không?
11. Tại sao proxy/WAF có thể trả 403 mà Spring Security không có log access denied?
12. `hasRole("ADMIN")` thường tương ứng authority gì trong cấu hình mặc định?
13. Sự khác biệt giữa `SecurityFilterChain` Servlet và `SecurityWebFilterChain` Reactive ảnh hưởng bài test như thế nào?
14. Vì sao request nhận 302 login có thể là lỗi entry point/chain không phù hợp với API?
15. Bằng chứng nào cho phép bạn phân biệt 403 do CSRF với 403 do thiếu quyền?
16. Khi custom handler trả status khác mặc định, nên dựa vào thông tin gì để xác định nguyên nhân?

## 23. Bảng tra cứu nhanh khi xử lý sự cố

| Hỏi gì trước? | Dấu hiệu ưu tiên | Hướng xử lý |
|---|---|---|
| Có request thật tới server không? | Browser Console/Network | CSP, mixed content, CORS hoặc mạng |
| 401 do đâu? | Challenge, entry point, authentication failure | Kiểm tra credentials/session/token |
| 403 do authorization? | Authentication hợp lệ, denied authority/scope | Kiểm tra role/authority và rule |
| 403 do CSRF? | Mutating method, token thiếu/sai, CSRF log | Sửa cơ chế truyền token |
| 403 do CORS? | OPTIONS preflight, `Invalid CORS request` | Sửa CORS tại API |
| 403 do proxy/WAF? | Edge response/traces, thiếu app log | Kiểm tra gateway rule |
| 400 do HTTP firewall? | `RequestRejectedException`, URI/method/header lạ | Chuẩn hóa client/proxy; review firewall |
| Có redirect 302? | `Location: /login`, entry point form | Xác minh auth scheme và chain |
| Servlet và Reactive khác gì? | Filter/exception handler, HTTP server khác | Dùng đúng API/test cho stack |
| Sửa xong đã an toàn? | Regression test + log + browser | Giữ CSRF/CORS/firewall/session |

## 24. Ghi nhớ

**401 chủ yếu nói về xác thực; 403 chủ yếu nói về việc không được phép; HTTP firewall từ chối request vì hình dạng request không được chấp nhận, có thể trước khi authorization được đánh giá.** Trong Spring Security Servlet, các thành phần quan trọng là `AuthenticationEntryPoint`, `AccessDeniedHandler`, `ExceptionTranslationFilter`, `StrictHttpFirewall` và `RequestRejectedHandler`. Một 403 có thể là CSRF, CORS hoặc proxy/WAF; một request bị firewall chặn thường xuất hiện ở 400 trong nhiều cấu hình nhưng không có status cố định cho mọi tầng.

Hãy tìm **điểm từ chối**, authentication state, authority, token CSRF, preflight, path/header thực nhận và log từ proxy/container/Spring. Tái hiện bằng request được kiểm soát, MockMvc/WebTestClient và browser, rồi sửa **đúng lớp**. Cách chẩn đoán này bảo vệ các lớp phòng vệ HTTP trong `SPRING_SECURITY_HTTP_PROTECTION`: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session phải tiếp tục phối hợp, chứ không bị tắt để che một mã lỗi.
