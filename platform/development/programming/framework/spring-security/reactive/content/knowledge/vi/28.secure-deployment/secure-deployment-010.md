# Rà soát CSRF, CORS, security headers, matcher và dữ liệu nhạy cảm trước phát hành — Spring Security Reactive

## 1. Mục tiêu: biến cấu hình bảo mật thành bằng chứng có thể kiểm tra

Trước khi đưa một ứng dụng Spring Boot WebFlux ra môi trường thật, không đủ để thấy `SecurityWebFilterChain` khởi động thành công hoặc vài request trả HTTP 200. Phải chứng minh được: thao tác đổi trạng thái không thể bị giả mạo bằng trình duyệt của người đã đăng nhập; chỉ các origin được duyệt mới được mã JavaScript trong browser đọc response; header bảo mật đáp ứng cách ứng dụng được triển khai; tất cả đường dẫn và phương thức HTTP đều đi qua đúng quy tắc phân quyền; và credential, token, dữ liệu cá nhân không bị tiết lộ qua API, log, lỗi hay hạ tầng quan sát.

**Kết quả học tập:**

1. Quyết định chính sách CSRF dựa trên cách trình duyệt mang thông tin xác thực, không chỉ dựa vào việc API trả JSON.
2. Kiểm tra CORS preflight, origin allowlist, credentials và thứ tự xử lý trong WebFlux.
3. Kiểm tra các response header ở URL HTTPS thực tế, gồm phản hồi thành công và lỗi.
4. Phân tích thứ tự `authorizeExchange`, `pathMatchers`, nhiều `SecurityWebFilterChain` và đường đi qua proxy/gateway.
5. Kiểm kê các nơi dữ liệu nhạy cảm có thể bị trả ra hoặc ghi lại; tạo ma trận test và điều kiện chặn release có thể lặp lại.

**Phạm vi:** Spring Security **Reactive/WebFlux** với `ServerHttpSecurity` và `SecurityWebFilterChain`. Các API servlet như `HttpSecurity`, `SecurityFilterChain`, `OncePerRequestFilter`, `MockMvc` không dùng thay thế trực tiếp. Kiểm soát truy cập dữ liệu ở tầng service/repository vẫn cần thiết ngoài bảo vệ HTTP.

## 2. Xác định kiến trúc trước khi duyệt cấu hình

Đầu tiên lập bản đồ luồng thực tế:

```text
Browser / Mobile / Machine client
          |
          v
DNS -> CDN/WAF -> Load balancer / API Gateway (TLS, path rewrite, CORS?)
          |
          v
Spring WebFlux
    -> CorsWebFilter / CORS integration
    -> SecurityWebFilterChain (match chain -> CSRF -> authn -> authz)
    -> RouterFunction / @RestController -> Reactive service -> DB
          |
          +-> access log, tracing, audit, metrics, error handler
```

Các câu hỏi phải có đáp án cụ thể: người dùng đăng nhập bằng form + cookie `WebSession`, HTTP Basic, OAuth2 Login hay bearer JWT? Trình duyệt có tự đính kèm cookie/credential khi gửi request không? SPA nằm cùng origin hay origin khác? Có nhiều security chain, gateway đổi path, quản trị Actuator hay WebSocket không? HTTPS dừng ở đâu? Những endpoint nào thay đổi trạng thái hoặc xử lý dữ liệu nhạy cảm?

| Kiểu client / credential | CSRF cần đánh giá thế nào? | CORS cần đánh giá thế nào? |
| --- | --- | --- |
| Web app dùng session cookie | Bảo vệ các thao tác đổi trạng thái bằng token/biện pháp tương đương; SameSite là lớp bổ sung | Nếu frontend khác origin, chỉ cấp CORS cho origin tin cậy và credentials khi cần |
| SPA dùng cookie xác thực với API cross-origin | Vẫn cần chống CSRF; token gửi qua header theo cơ chế được thiết kế | Cho phép đúng origin, methods, headers và `Access-Control-Allow-Credentials` nếu dùng cookie |
| SPA chỉ gửi Bearer token **bằng JavaScript qua Authorization header**, không có credential tự gửi | Có thể cân nhắc tắt CSRF cho chain thuần stateless sau khi kiểm chứng toàn bộ điều kiện; XSS và rò token vẫn là rủi ro | Origin allowlist vẫn cần cho truy cập browser; CORS không thay thế authn/authz |
| HTTP Basic trong browser | Trình duyệt có thể giữ và tự gửi credential, nên không mặc định coi an toàn khỏi CSRF | Kiểm tra preflight nếu JavaScript gửi `Authorization` |
| Mobile/server-to-server không có browser | CSRF thường không phải mối đe dọa chính; áp dụng authn/authz và replay protection phù hợp | CORS là chính sách browser, không hạn chế được `curl` hoặc server clients |
| Ứng dụng trộn cookie + bearer hoặc nhiều chain | Duyệt từng chain/endpoint, tránh tắt CSRF chung rồi bỏ sót các flow cookie | Chính sách CORS theo miền và loại endpoint, không dùng một allowlist rộng cho tất cả |

**Phân biệt quan trọng:** CSRF giải quyết yêu cầu đổi trạng thái được trình duyệt gửi ngoài ý muốn khi credential được tự mang theo. CORS quy định **JavaScript từ origin nào được trình duyệt cho phép truy cập response**, không phải cơ chế xác thực của server và không ngăn một request cross-site đơn giản tự được gửi đi. Cùng một hệ thống có thể cần cả hai.

## 3. Rà soát CSRF theo cách credential được gửi

### 3.1. Kiểm tra điều kiện cần bảo vệ

`CsrfWebFilter` là thành phần CSRF của Spring Security WebFlux; cấu hình mặc định có bảo vệ CSRF. Với ứng dụng sử dụng cookie/session, những thao tác `POST`, `PUT`, `PATCH`, `DELETE` phải được kiểm thử khi thiếu hoặc sai token. Các phương thức `GET`, `HEAD`, `OPTIONS`, `TRACE` phải giữ tính chất không thay đổi trạng thái; nếu `GET /delete?id=...` xóa dữ liệu thì đó là lỗi thiết kế, kể cả khi bật CSRF mặc định.

Những điểm cần rà:

- Không có `csrf.disable()` áp dụng toàn ứng dụng chỉ để “sửa lỗi 403”, không có matcher loại trừ quá rộng như `/api/**` khi vẫn dùng session/cookie.
- Đăng nhập, đăng xuất, đổi mật khẩu, cập nhật cấu hình, đăng ký webhook, cấp quyền và upload có chuyển trạng thái phải nằm trong phạm vi đánh giá. WebFlux mặc định bảo vệ đăng nhập; logout thông thường yêu cầu POST và CSRF.
- Với biểu mẫu HTML, token phải được gắn vào form. Với SPA gọi JSON API, client nên gửi token qua request header, không đặt token trong URL, log hoặc response lỗi.
- Cấu hình token repository và cơ chế client đọc token phải tương thích. Mặc định có thể lưu token trong `WebSession`; khi dùng cookie repository cho SPA, cần xét `HttpOnly`, `Secure`, `SameSite`, rotation, hết hạn và cách lấy token. Mở cookie token để JavaScript đọc chỉ khi giao thức yêu cầu; cookie phiên đăng nhập vẫn nên `HttpOnly`.
- Spring Security 6.x dùng `XorServerCsrfTokenRequestAttributeHandler` mặc định để giảm nguy cơ BREACH. Khi tự viết client lấy token hoặc thay handler, kiểm thử chính xác token client nhận và header server kiểm tra, tránh vô tình vô hiệu hóa lớp bảo vệ.
- SameSite, kiểm tra `Origin`/`Referer` hoặc Fetch Metadata (`Sec-Fetch-Site`) có thể hỗ trợ phòng thủ nhiều lớp; đừng tự coi một cấu hình SameSite là bằng chứng mọi tình huống CSRF được chặn.

**Trường hợp CSRF thường bị hiểu nhầm:** HTTP 403 khi gọi `POST` có thể đến từ CSRF dù người dùng có đúng quyền. Hãy thực hiện cùng một request và cùng danh tính ở hai biến thể **không token** và **token hợp lệ**. Sau đó kiểm tra quyền bằng một request đã có token để không nhầm lẫn 403 do thiếu vai trò với 403 do CSRF.

### 3.2. Chỉ tắt CSRF khi có lập luận bảo mật rõ ràng

Ví dụ sau **chỉ là một đoạn cấu hình minh họa**, phù hợp với chain API nhận bearer token trong `Authorization` do client chủ động đặt và hoàn toàn không chấp nhận bất kỳ cookie/session hay credential tự động nào:

```java
// Đoạn minh họa trong phần cấu hình ServerHttpSecurity,
// không phải chương trình Java độc lập.
http.csrf(csrf -> csrf.disable());
```

Để phê duyệt lựa chọn này, cần có bằng chứng: tất cả endpoint của chain dùng cơ chế auth được kiểm soát; không có form/OAuth2 login dùng cookie, HTTP Basic trong browser hoặc fallback session; gateway không chèn cookie xác thực; các endpoint mới không vô tình được đưa vào chain tắt CSRF. Nếu còn endpoint browser dùng cookie, tách security chain có matcher tường minh hoặc giữ CSRF và giải quyết vấn đề token phía client.

### 3.3. Ma trận kiểm thử CSRF

| Thao tác | Hoàn cảnh | Kỳ vọng |
| --- | --- | --- |
| GET tài nguyên chỉ đọc | Có/không credential hợp lệ | Không bị chặn bởi CSRF; phân quyền vẫn hoạt động |
| POST thay đổi dữ liệu | Đã đăng nhập bằng cookie, **thiếu token** | Bị từ chối; dữ liệu không đổi |
| POST thay đổi dữ liệu | Token CSRF **sai hoặc thuộc phiên khác** | Bị từ chối; dữ liệu không đổi |
| POST thay đổi dữ liệu | Credential, quyền và token đều đúng | Qua kiểm tra CSRF; nghiệp vụ xử lý hợp lệ |
| POST đổi vai trò | Có token nhưng thiếu quyền ADMIN | Bị từ chối **do authorization** |
| Đăng nhập / đăng xuất browser | Thiếu token với flow được bảo vệ | Không được chuyển trạng thái trái chính sách |
| CORS preflight OPTIONS | Không cookie và không token | Được CORS xử lý; không bị coi là đăng nhập thất bại |
| Session hết hạn / logout | Dùng lại token cũ | Không dùng token cũ để chuyển trạng thái của phiên đã kết thúc |

## 4. Rà soát CORS: browser origin, preflight và credentials

### 4.1. Quy tắc nền tảng

Một **origin** gồm scheme, hostname và port. `https://app.example.com` khác `http://app.example.com` hoặc `https://app.example.com:8443`. Không đánh đồng “cùng site” với “cùng origin”, cũng không cho phép mọi subdomain chỉ vì chúng có chung tên miền.

Preflight có thể có dạng:

```http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
```

Preflight thường **không mang cookie phiên**, nên phải được giải quyết trước khi bộ lọc xác thực từ chối vì thiếu danh tính. Spring Security Reactive hướng dẫn tích hợp CORS qua `CorsWebFilter` và `CorsConfigurationSource`. Cấu hình CORS nên có nguồn rõ ràng, tránh hai lớp gateway và ứng dụng gửi các giá trị `Access-Control-*` khác nhau.

Đối chiếu từng quy tắc với tài liệu API đã duyệt:

- `allowedOrigins`: liệt kê **đúng** các origin môi trường production được tin cậy; không dùng `*` khi trả credentials. Không đưa origin local/dev vào allowlist production nếu không có nhu cầu được duyệt.
- `allowedMethods`: chỉ các HTTP method thực tế mà client cần, không mặc định mở toàn bộ.
- `allowedHeaders`: chứa các header client thật sự gửi như `Authorization`, `Content-Type`, `X-CSRF-TOKEN`; không mở rộng tùy tiện.
- `allowCredentials`: chỉ bật khi client có nhu cầu browser gửi cookie hoặc credential cross-origin; kiểm tra cookie `SameSite=None; Secure` khi thực sự dùng cookie third-party và những giới hạn browser hiện hành.
- `exposedHeaders`: chỉ nêu các response header cần cho JavaScript; không expose `Set-Cookie` hay bất kỳ credential bí mật.
- `maxAge` và cache: preflight cache có thể giữ chính sách cũ; khi thay allowlist cần dự tính thời gian chuyển đổi, phối hợp CDN, và header `Vary: Origin`/preflight headers phù hợp.
- Origin không hợp lệ, `Origin: null`, biến thể port/protocol, hoặc header không được phép phải thất bại theo chính sách. Phản hồi CORS “không cho đọc” không đồng nghĩa server đã ngăn mọi tác động nghiệp vụ: vẫn cần CSRF và authorization.

**CORS là chính sách browser.** `curl` có thể gửi bất kỳ `Origin` nào và vẫn truy cập server nếu xác thực/phân quyền cho phép. Không bao giờ dùng giá trị Origin làm bằng chứng quyền người dùng hay để chọn tenant mà không có kiểm chứng riêng.

### 4.2. Dấu hiệu cấu hình nguy hiểm

| Mẫu cấu hình/triệu chứng | Rủi ro | Hướng sửa |
| --- | --- | --- |
| `allowedOriginPatterns("*")` với credentials | Bất kỳ website nào cũng có thể được cấp response CORS credentialed theo phản chiếu origin | Allowlist chính xác các origin có chủ sở hữu rõ ràng |
| Cho phép mọi `Header` / `Method` / route khi chỉ cần một SPA | Bề mặt truy cập tăng, khó audit thay đổi | Phân tách theo `/api/**`, method, header cần thiết |
| Preflight 401/302 tới trang login | Browser chặn request hợp lệ trước khi gửi request thật | Tích hợp CORS chạy trước auth, kiểm tra thứ tự filter/gateway |
| Gateway thêm `Access-Control-Allow-Origin` song song với backend | Header xung đột hoặc policy lệch | Chọn một chủ sở hữu CORS và test trên public ingress |
| Chỉ thử GET không credential | Không phát hiện lỗi POST + Authorization + CSRF header | Test OPTIONS và request thật từ origin được phép/bị cấm |
| Tin rằng CORS chặn CSRF | Form/credential tự động có thể vẫn gây side effect | Giữ cơ chế chống CSRF khi cần |

## 5. Rà soát security headers trên **response** thực tế

Spring Security cung cấp một số header mặc định, nhưng chính sách phù hợp vẫn phụ thuộc loại ứng dụng, deployment và frontend. Dùng `curl -I` với endpoint chấp nhận HEAD hoặc `curl -i` với GET, đồng thời xem Network trong browser trên HTTPS domain thật. Kiểm tra cả response 200, 401, 403, redirect và trang lỗi do gateway tạo; header ở Spring không đảm bảo header ở CDN/ingress cuối cùng.

| Header / thuộc tính | Điều cần xác minh | Ghi chú |
| --- | --- | --- |
| `Strict-Transport-Security` (HSTS) | Xuất hiện trên HTTPS, có thời gian hợp lý; cấu hình ở proxy nếu TLS terminate tại proxy | Mặc định Spring Security chỉ thêm khi request được nhận diện HTTPS; `includeSubDomains` chỉ dùng nếu tất cả subdomain hỗ trợ HTTPS |
| `X-Content-Type-Options: nosniff` | Có trên response cần bảo vệ, `Content-Type` được gán đúng | Không thay thế việc xác thực nội dung tệp upload |
| `X-Frame-Options: DENY` | Không bị proxy xóa, trừ trang cần iframe có chính sách riêng | Kết hợp `frame-ancestors` trong CSP khi phục vụ HTML |
| `Content-Security-Policy` | Có policy phù hợp với tài nguyên HTML/SPA thực tế; cấm nguồn script không cần thiết | Không có CSP “tối ưu chung”; Spring Security không tự cấu hình CSP mặc định |
| `Cache-Control: no-store` và liên quan | Dữ liệu cá nhân/credential không bị cache ở browser/CDN | Không xóa cache header bảo mật rộng rãi chỉ để tăng tốc static assets |
| `Referrer-Policy` | Không rò đường dẫn/định danh nhạy cảm vào `Referer` ngoài tổ chức | Chọn `no-referrer` hoặc `strict-origin-when-cross-origin` theo sản phẩm |
| `Permissions-Policy` | Chặn các tính năng browser không dùng, nếu phục vụ trang web | Không thay thế kiểm soát API |
| `Set-Cookie` | Session cookie có `Secure`, `HttpOnly`, `SameSite`, `Path` và `Domain` đúng | `SameSite=None` cần `Secure` trên browser hiện đại; giảm phạm vi domain nếu có thể |
| `X-XSS-Protection` | Không bật lại “XSS filter” đời cũ để thay CSP | Giá trị `0` là chủ ý với trình duyệt hiện đại |

Lưu ý: Spring Security có header mặc định như no-cache, nosniff và chống nhúng iframe; **CSP cần chủ động khai báo**. Việc gọi `headers(headers -> headers.disable())` có thể vô hiệu hóa một loạt bảo vệ. Test trực tiếp trên miền ngoài và so sánh với bản staging; đừng kết luận chỉ bằng bean Java.

**TLS và proxy:** kiểm tra redirect HTTP sang HTTPS theo đường vào thực tế, chứng chỉ hợp lệ, chính sách forward headers chỉ tin proxy được quản lý. Header do client tự gửi như `X-Forwarded-Proto` không được phép khiến hệ thống tin rằng request HTTP không mã hóa là HTTPS nếu edge chưa làm sạch header đó.

**CSP rollout:** ứng dụng HTML/SPA có inline script, fonts, iframe, analytics cần inventory thật; kiểm thử `Content-Security-Policy-Report-Only` trước khi chuyển sang enforce nếu cần. Đối với backend chỉ trả text/JSON, CSP ngăn thực thi nội dung trong browser có giá trị hạn chế hơn; bảo vệ chính vẫn là Content-Type chính xác, authorization và chặn rò dữ liệu.

## 6. Rà soát matcher và phủ kín route

### 6.1. Đọc quy tắc như một chuỗi quyết định có thứ tự

Trong `authorizeExchange`, Spring Security xét các rule theo thứ tự khai báo; rule trúng trước được dùng. Vì vậy:

```java
// Sai về thứ tự: rule rộng làm mất ý nghĩa hạn chế phía sau.
authorize
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll();
```

Hãy đặt các quyền cụ thể trước và có fallback:

```java
// Đúng hướng: từng route/method được phân định và phần còn lại từ chối.
authorize
    .pathMatchers(HttpMethod.GET, "/public").permitAll()
    .pathMatchers("/api/admin", "/api/admin/**").hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/profile").authenticated()
    .pathMatchers(HttpMethod.POST, "/api/profile").hasAnyRole("USER", "ADMIN")
    .anyExchange().denyAll();
```

Các đoạn trên là **một phần lambda cấu hình**, không phải file Java độc lập; mã chạy đầy đủ ở mục 8. Kiểm tra cả đường dẫn gốc `/api/admin` lẫn `/api/admin/**`, chữ hoa/thường, slash cuối, encoding, matrix params nếu có, method khác nhau, và route được gateway rewrite. Không giả định cùng policy cho mọi method khi chỉ GET cần public.

Nếu có nhiều `SecurityWebFilterChain`, **`securityMatcher`** quyết định chain nào nhận exchange trước khi các `pathMatchers` bên trong hoạt động; `@Order` và thứ tự khớp chain là điểm bắt buộc review. Một endpoint không nằm trong chain dự định có thể rơi vào chain khác với chính sách yếu hơn. Đừng dùng `permitAll` để sửa một endpoint nhạy cảm trước khi xác nhận vì sao nó bị chặn.

### 6.2. Checklist bao phủ route

Lập inventory từ code/controller, functional `RouterFunction`, gateway route, Actuator/management, Swagger/OpenAPI UI, WebSocket handshake, file upload và endpoint phát hành riêng. Với mỗi route cần có **phương thức, danh tính, role/scope, tenant, CSRF và kết quả test**.

| Route minh họa | Method | Ai được vào | Điều kiện bổ sung |
| --- | --- | --- | --- |
| `/public` | GET | Không đăng nhập | Không thay đổi dữ liệu |
| `/api/profile` | GET | Người đã xác thực | Dữ liệu phải là của chính principal |
| `/api/profile` | POST | USER/ADMIN | CSRF nếu browser dùng cookie/Basic; validate input và ownership |
| `/api/admin/report` | GET | ADMIN | Không cho role USER đọc thông tin quản trị |
| `/api/admin/roles` | POST | ADMIN | CSRF khi thích hợp, audit sau commit, kiểm tra tenant |
| `/actuator/**` | GET/POST tùy endpoint | Theo chính sách management riêng | Không lộ `env`, `configprops`, heap dump, loggers ở public |
| Route không khai báo | Bất kỳ | Không ai | Fail closed: `denyAll` khi inventory đầy đủ |

Ngoài matcher, phải kiểm tra **cấp bản ghi**: có vai trò USER không đồng nghĩa được đọc `/users/{otherUserId}`. Ở service/repository cần so sánh chủ thể/tenant từ `ReactiveSecurityContextHolder` hoặc principal đã xác thực với owner của đối tượng. Không dùng role hay tenantId do client tự khai báo làm nguồn tin cậy.

Khi dùng WebFlux method security, xác nhận bật đúng reactive method security và thật sự test `@PreAuthorize`/`@PostAuthorize` ở vị trí áp dụng được; HTTP matcher không tự kiểm tra mọi lời gọi nội bộ. Đừng nhầm annotation bảo mật của Spring MVC/Servlet với chain Reactive.

## 7. Rà soát rò rỉ dữ liệu nhạy cảm trước release

Tạo **data-flow inventory**: dữ liệu vào qua header, URL, body, file upload và credential; dữ liệu ra qua response, exception, log, trace, metric, audit, cache, export và diagnostics. Lập danh sách gồm tên trường, mức nhạy cảm, nơi lưu, ai có quyền truy cập, thời hạn và phương pháp masking/retention.

### 7.1. Những nguồn rò rỉ phải kiểm tra

| Vị trí | Sai sót thường gặp | Điều kiện chấp nhận |
| --- | --- | --- |
| Request/response log, Netty wiretap, `WebClient` debug | In toàn bộ `Authorization`, `Cookie`, body login, OTP, refresh token | Log theo allowlist trường; mask/không ghi bí mật; tắt verbose debug tại production |
| Exception và error JSON | Stack trace, SQL, token, internal hostname, user record xuất hiện ở 4xx/5xx | Error contract ngắn gọn với mã lỗi/correlation ID; chi tiết nằm trong log nội bộ đã lọc |
| API DTO / serializer | Trả password hash, secret, field nội bộ, toàn bộ entity DB | DTO response riêng, mapping trường được phép và test snapshot/contract |
| URL và query string | Token, reset link, email/PII đi vào browser history, proxy log, `Referer` | Không truyền secret trong query nếu có lựa chọn an toàn; link dùng một lần và thời hạn ngắn |
| Cookies, browser storage | Session/refresh token đọc được bởi JS hoặc gửi sang domain rộng | `HttpOnly` cho auth cookie, `Secure`, `SameSite` và `Domain`/`Path` tối thiểu |
| Tracing/metrics | Token/PII đi vào span attributes, baggage hoặc label cardinality cao | Chỉ dùng định danh tương quan không bí mật, giới hạn thuộc tính và cardinality |
| Audit trail | “Lưu tất cả body để truy vết” | Ghi ai/làm gì/kết quả/object ID an toàn; không ghi credential hoặc bản ghi PII đầy đủ |
| Cache/CDN | Response cá nhân bị cache công khai hoặc giữa tenant | `Cache-Control` phù hợp, không share cache key khi thiếu user/tenant và auth scope |
| Actuator/diagnostics | `/actuator/env`, `heapdump`, `loggers`, config nội bộ mở công khai | Chỉ expose endpoint được duyệt; hạn chế mạng, danh tính và quyền |
| Client error / CORS | JS từ origin lạ đọc response có dữ liệu cá nhân | Không trả dữ liệu nhạy cảm khi chưa có authn/authz; allowlist origin chính xác |

**Các giá trị không được lộ:** password, password hash, client secret, API key, JWT đầy đủ, access/refresh token, session ID, OTP/recovery code, private key, database URL có credential, dữ liệu thanh toán nhạy cảm. Ngay cả email/IP/username có thể là dữ liệu cá nhân: cần nguyên tắc tối thiểu hóa. Một lỗi 401/403 không được nêu “tài khoản A tồn tại, đã khóa” nếu ứng dụng yêu cầu chống account enumeration.

### 7.2. Thực hành trong reactive pipeline

- Không gọi `block()` chỉ để ghi log/mask dữ liệu khi xử lý request; dùng API không chặn hoặc hệ thống ghi phù hợp. Không bật Reactor/Netty wiretap toàn cục ở production rồi phụ thuộc việc xóa log về sau.
- Không đặt raw credential vào `Reactor Context`, MDC, trace baggage hoặc message broker. Context giúp truyền thông tin theo luồng, không tự động mã hóa hay bảo vệ dữ liệu.
- Từ chối mass assignment: DTO chỉ khai báo field được client sửa, kiểm tra kiểu, kích thước, giá trị và owner/tenant ở service; không bind JSON tùy ý thẳng vào entity có trường `role`/`enabled`.
- Luôn dùng TLS cho credential; kiểm tra `WebClient`, redirect, proxy và tài khoản dịch vụ phía downstream. Không gửi bearer token sang origin khác theo redirect không kiểm soát.
- Tách mật khẩu/secret khỏi source và artifact, dùng secret manager và quyền đọc giới hạn. Biến môi trường cũng có thể lộ trong crash dump hoặc diagnostic endpoint; tự nó không phải bằng chứng an toàn.
- Nếu cần audit chính thức, sử dụng schema có cấu trúc và kho lưu bảo vệ toàn vẹn, tránh lưu payload nguyên bản. Ứng dụng phải cho phép tra cứu sự kiện theo quyền có kiểm soát.

## 8. Ví dụ chạy được: cấu hình WebFlux để kiểm tra trước phát hành

Ví dụ này dùng **Java 17**, **Spring Boot 3.3.13**, Spring WebFlux và Spring Security Reactive. Nó minh họa một chính sách có bốn loại endpoint, CORS chỉ cho `https://app.example.com`, giữ CSRF mặc định, HTTP Basic cho thử nghiệm và các security header. Tài khoản/mật khẩu cứng trong source **chỉ dùng trong demo cục bộ**, không phải cấu hình production. Endpoint POST chỉ trả chuỗi minh họa, chưa cập nhật cơ sở dữ liệu.

### 8.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-release-review</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 8.2. `src/main/java/dev/example/release/ReactiveReleaseReviewApplication.java`

```java
package dev.example.release;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ReactiveReleaseReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveReleaseReviewApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReviewSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var member = User.withUsername("member")
                .password(encoder.encode("demo-member"))
                .roles("USER")
                .build();
        var admin = User.withUsername("root")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(member, admin);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        var configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(1800L);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public").permitAll()
                        .pathMatchers("/api/admin", "/api/admin/**")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/profile")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/profile")
                            .hasAnyRole("USER", "ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .cors(withDefaults())
                .csrf(withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                  "default-src 'none'; object-src 'none'; frame-ancestors 'none'")))
                .build();
    }
}

@RestController
class ReviewApi {
    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName());
    }

    @PostMapping("/api/profile")
    public Mono<String> updateProfileDemo() {
        return Mono.just("accepted");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> report() {
        return Mono.just("admin report");
    }
}
```

**Giải thích:**

- `GET /public` công khai, còn mọi method không khai báo bị `denyAll`. `GET /api/profile` yêu cầu authenticated; `POST /api/profile` yêu cầu USER hoặc ADMIN; nhánh admin đặt trước và yêu cầu ADMIN.
- `httpBasic(withDefaults())` bật Basic cho bài thử; `csrf(withDefaults())` cố ý giữ bảo vệ CSRF. Dù Basic đã cung cấp tên/mật khẩu đúng, một `POST` không token vẫn có thể 403.
- `corsConfigurationSource` dùng origin chính xác cho `/api/**`, cho phép client gửi `Authorization`, `Content-Type` và `X-CSRF-TOKEN`; `allowCredentials(true)` chỉ phù hợp khi ứng dụng thực sự cần credential cross-origin. Đưa vào production phải thay origin/credentials phù hợp.
- CSP ví dụ `default-src 'none'` an toàn cho API thuần text. Nếu application phục vụ HTML/SPA từ cùng server, thay bằng chính sách hợp lệ cho script/style/image/font thực tế và kiểm thử chức năng.
- Chỉ có một chain trong demo. Dự án thật phải phân tích mọi chain và auth mechanism; những thành phần thêm như OAuth2, resource server, gateway, actuator cần kiểm thử riêng.

### 8.3. Kiểm thử tích hợp với WebTestClient và Spring Security Test

Tạo `src/test/java/dev/example/release/ReactiveReleaseReviewSecurityTest.java`:

```java
package dev.example.release;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveReleaseReviewSecurityTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void configureClient() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void matcherAndRoleMatrix() {
        client.get().uri("/public").exchange()
                .expectStatus().isOk();

        client.get().uri("/api/profile").exchange()
                .expectStatus().isUnauthorized();

        client.mutateWith(mockUser("member").roles("USER"))
                .get().uri("/api/admin/report").exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("root").roles("ADMIN"))
                .get().uri("/api/admin/report").exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("root").roles("ADMIN"))
                .get().uri("/unlisted").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unsafeMethodRequiresCsrfToken() {
        client.mutateWith(mockUser("member").roles("USER"))
                .post().uri("/api/profile").exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("member").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/api/profile").exchange()
                .expectStatus().isOk();
    }

    @Test
    void corsPreflightAllowsOnlyTrustedOrigin() {
        client.options().uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "authorization,content-type,x-csrf-token")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com");

        client.options().uri("/api/profile")
                .header("Origin", "https://untrusted.example")
                .header("Access-Control-Request-Method", "POST")
                .exchange()
                .expectHeader().doesNotExist(
                        "Access-Control-Allow-Origin");
    }

    @Test
    void securityHeadersArePresent() {
        client.get().uri("/public").exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().valueEquals(
                        "X-Frame-Options", "DENY")
                .expectHeader().exists(
                        "Content-Security-Policy");
    }
}
```

Ở đây `mockUser(...)` tạo principal để tập trung kiểm thử authorization; `csrf()` thêm token hợp lệ cho exchange giả lập. Test này **không chứng minh mật khẩu Basic được kiểm tra, không chứng minh HSTS trên HTTPS công khai, không chứng minh gateway/CORS ngoài edge hoạt động**. Cần thêm test end-to-end qua entry point thật trước khi release.

Chạy bằng:

```bash
mvn test
mvn spring-boot:run
```

Từ terminal khác, thử một số request:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/profile
curl -i -u member:demo-member http://localhost:8080/api/profile
curl -i -u member:demo-member http://localhost:8080/api/admin/report
curl -i -u root:demo-admin http://localhost:8080/api/admin/report
curl -i -u member:demo-member -X POST http://localhost:8080/api/profile

curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
```

Dự kiến: `/public` → 200 với body `public`; `/api/profile` không credential → 401; với member → 200 và body `member`; member vào admin → 403; root vào admin → 200 và body `admin report`; member POST không token → 403; preflight hợp lệ có `Access-Control-Allow-Origin: https://app.example.com`. Header động, thông báo lỗi và log có thể thay đổi theo môi trường nên không đưa stdout giả cố định. Để xác nhận **POST với token hợp lệ** hãy xem test WebTestClient ở trên; không thể chỉ thêm một header token tùy ý trong `curl` rồi mong được chấp nhận.

**Hạn chế của demo:** tài khoản trong bộ nhớ, không có HTTPS/gateway, không lưu audit chính thức, không thực hiện đổi trạng thái, không có phân quyền theo object/tenant. Đây là mẫu cấu hình và test, không phải bản production có thể phát hành nguyên trạng.

## 9. Ma trận nghiệm thu trước phát hành

Chạy test tự động trên phiên bản build dự định release, sau đó lặp lại **smoke test qua ingress domain thật** ở staging giống production. Ma trận phải có cả “được phép” và “bị từ chối”, nếu không một cấu hình `denyAll` toàn cục cũng có thể trông có vẻ an toàn.

| Nhóm | Thử nghiệm tối thiểu | Bằng chứng cần lưu |
| --- | --- | --- |
| CSRF | POST/PUT/PATCH/DELETE không token, token sai, token đúng; logout và session hết hạn; kiểm tra DB không đổi khi bị chặn | HTTP status + truy vết không có side effect |
| CORS | Preflight origin đúng/sai, credentials, các header/method; so sánh response qua gateway và từ app | Request/response headers được ẩn danh; không có origin lạ được cấp quyền đọc |
| Headers | 200/401/403/5xx trên HTTPS; HSTS, cache, nosniff, frame, CSP nếu có HTML, cookie flags | Header snapshot từ public URL, trình duyệt thực, kiểm tra CDN |
| Matchers | Anonymous, USER, ADMIN; GET/POST; route gốc/nhánh; route lạ; nhiều chain và method security | Ma trận route-role-method, kết quả test, chủ sở hữu từng exception |
| Sensitive data | Response DTO, lỗi validation/500, debug log, trace, audit, Actuator, export, URL query | Bộ lọc canary/test data; không xuất hiện token/secret/PII ngoài policy |
| Domain/tenant | Người dùng A đọc/sửa object B; tenant A truy cập dữ liệu B | Test IDOR/BOLA; query phải lọc owner/tenant |
| Deploy/edge | Redirect HTTPS, forwarded headers, CORS giữa CDN và app, cookie trên browser | Kết quả từ domain/port public đúng cấu hình |
| Vận hành | Cảnh báo 401/403 bất thường, log redaction, key rotation, sự cố CORS/CSP, rollback | Dashboard, runbook, retention và trách nhiệm rõ ràng |

### 9.1. Những điều kiện phải chặn phát hành

Chưa đạt QA nếu xuất hiện ít nhất một trong các tình huống sau: một request có thể thay đổi trạng thái trái phép vì thiếu CSRF/authorization; origin không được duyệt có thể đọc dữ liệu credentialed; rule `permitAll` hoặc chain matcher vượt phạm vi đã phê duyệt; secret/token/PII xuất hiện ngoài nơi được phép; header an toàn quan trọng bị mất tại edge; endpoint quản trị lộ ra public; test chỉ chứng minh 403 nhưng không có positive test chứng minh nghiệp vụ hợp lệ vẫn chạy.

Với lỗi hạ tầng quan sát hoặc CSP vi phạm policy mới, quyết định chặn release phải theo chính sách tổ chức và mức ảnh hưởng đã định, kèm người sở hữu và kế hoạch khôi phục. Không “chữa” CORS hoặc CSRF bằng việc vô hiệu hóa toàn bộ lớp bảo vệ mà không quay lại threat model.

### 9.2. Bản ghi review ngắn nên lưu cùng release

```yaml
security_review:
  build_id: "release-candidate-id"
  deployment: "staging-public-ingress"
  authentication: ["http-basic-demo"] # Thay bằng cơ chế thật
  csrf:
    decision: "enabled-for-browser-flows"
    tests: ["unsafe-no-token-denied", "valid-token-allowed"]
  cors:
    approved_origins: ["https://app.example.com"]
    preflight_positive_negative: "passed"
  headers:
    https_edge_verified: true
    csp_checked_for_html: true
  matcher_coverage:
    all_routes_inventory: true
    default_fallback: "deny"
    positive_negative_authorization_tests: true
  sensitive_data:
    api_response_review: true
    logs_traces_actuator_review: true
  open_findings: []
  approver: "security-owner"
```

Các giá trị ở trên **minh họa cấu trúc chứng cứ**, không xác nhận một hệ thống cụ thể đã được kiểm thử. Thực tế nên lưu ID test run, thời điểm, commit/build hash, môi trường, người phê duyệt và các ngoại lệ được chấp thuận. Khi có thay đổi auth flow, domain, route, proxy hoặc login cookie sau QA, phải chạy lại các ca bị ảnh hưởng trước release.

## 10. Sai lầm thường gặp và cách phát hiện nhanh

1. **Thấy 403 khi POST thì tắt CSRF:** chạy lại ca không token, token hợp lệ và role đúng; xác định lớp nào từ chối trước khi sửa.
2. **CORS `*` để “cho frontend hoạt động”:** chỉ rõ origin, method, header và credentials; thử origin lạ qua preflight thật.
3. **Cho `OPTIONS` đi qua login redirect:** sửa thứ tự CORS, không yêu cầu cookie ở preflight.
4. **Đặt `/api/**.permitAll()` trước `/api/admin/**`:** duyệt thứ tự matcher; test cả USER được phép và USER bị từ chối.
5. **Cấu hình đúng trong Spring nhưng sai tại CDN:** kiểm tra header, path rewrite, TLS và CORS trên URL public.
6. **Chỉ test unauthenticated request:** phải test authenticated user thiếu quyền, user đúng quyền, cross-tenant và từng HTTP method.
7. **Cho rằng HSTS/CSP luôn được bật mặc định:** HSTS cần HTTPS được nhận diện đúng, CSP cần policy riêng; xác minh response cuối cùng.
8. **Ghi request/response đầy đủ để debug production:** dùng field allowlist, loại secret, gỡ wiretap và hạn chế thời hạn log.
9. **Đưa cùng entity DB ra API:** response DTO rõ trường, có kiểm tra dữ liệu theo user/tenant.
10. **Chỉ chụp screenshot QA:** bổ sung test tái lập, bằng chứng request/response đã lọc, build ID và owner cho từng exception.

## 11. Tài liệu chính thức để đối chiếu

- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive CORS: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security — Reactive HTTP Headers: https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html
- Spring Security — Reactive request authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive WebFlux security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — HTTP Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
