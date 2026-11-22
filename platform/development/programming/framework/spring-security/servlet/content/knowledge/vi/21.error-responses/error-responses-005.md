# 401, 403 và chuyển hướng đăng nhập trong từng loại ứng dụng

> **Ngữ cảnh:** Spring Security 6 trên **Servlet stack**, Java 17+, Spring Boot 3.x. Chủ đề thuộc **Phản hồi lỗi**: khi nào trả **401 Unauthorized**, **403 Forbidden**, khi nào **302 Redirect đến trang đăng nhập**, vì sao cùng một người dùng chưa xác thực có thể nhìn thấy hành vi khác nhau ở ứng dụng web truyền thống, API HTTP Basic, OAuth2 Resource Server/Bearer và SPA. Giải thích vai trò của `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, `SecurityContext`, CSRF và nhiều `SecurityFilterChain`. Có ví dụ Spring Boot chạy được với hai kiểu endpoint, bài kiểm thử MockMvc cho phép/chặn và bộ tình huống xử lý lỗi thực tế.

## 1. Bản đồ quyết định: ba kiểu phản hồi, ba ý nghĩa

Không thể suy diễn chỉ từ câu “người dùng không có quyền” rằng server phải luôn trả 403. Trước hết cần xác định **người dùng đã có authentication hợp lệ hay chưa**, **ứng dụng giao tiếp với browser hay API client**, và **loại authentication entry point** đã được cấu hình.

| Tình huống | Web dùng form-login/session | API dùng HTTP Basic | OAuth2 Resource Server dùng Bearer |
| --- | --- | --- | --- |
| Chưa đăng nhập, gọi endpoint bảo vệ | Thường **302** đến `/login` | **401**, header `WWW-Authenticate: Basic ...` | **401**, header `WWW-Authenticate: Bearer ...` |
| Credentials sai hoặc token không hợp lệ | Form login thất bại, thường **302** tới `/login?error` | **401** với Basic challenge | **401** với Bearer challenge và error phù hợp |
| Đã xác thực nhưng thiếu authority/role/scope | Thường **403** | Thường **403** | Thường **403**; có thể kèm Bearer `insufficient_scope` |
| Trình duyệt POST thiếu CSRF token | Thường **403**; chi tiết tùy chain/context | Có thể **403** khi CSRF bật | Với API thuần bearer stateless, CSRF thường được đánh giá riêng và chỉ tắt trong phạm vi phù hợp |
| URL không tồn tại nhưng request bị bảo vệ | Có thể redirect login **trước khi** MVC trả 404 | Có thể **401** trước khi MVC trả 404 | Có thể **401** trước khi MVC trả 404 |
| Đã xác thực, URL không tồn tại và được phép qua chain | MVC thường trả **404** | MVC thường trả **404** | MVC thường trả **404** |

**Cách nhớ:** **401 = cần authentication hợp lệ**, **403 = request bị từ chối truy cập**, **302 đến login = một UX browser để bắt đầu authentication**, không phải mã lỗi phân quyền của REST API. HTTP status thực tế phụ thuộc exception, entry point, handler và cấu hình.

Lưu ý tên lịch sử `401 Unauthorized` dễ gây hiểu nhầm: ý nghĩa HTTP là *unauthenticated or invalid authentication*. `403 Forbidden` thường có nghĩa server đã hiểu request nhưng từ chối quyền, dù HTTP không bắt buộc chỉ dùng với authenticated user; trong Spring Security, phân nhánh mặc định còn phụ thuộc nhận diện anonymous/remember-me và cách xử lý exception.

## 2. HTTP 401: Authentication challenge, không phải mọi lỗi đều 401

Theo ngữ nghĩa HTTP, `401 Unauthorized` cho biết request thiếu authentication hợp lệ cho tài nguyên đang yêu cầu. Server nên cung cấp cơ chế authentication challenge trong header `WWW-Authenticate` khi dùng HTTP authentication schemes.

Ví dụ HTTP Basic:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

Client hiểu cần gửi thông tin đăng nhập phù hợp scheme Basic, ví dụ `Authorization: Basic ...`. Chuỗi Base64 của Basic credential **không phải mã hóa bảo mật**: production phải dùng HTTPS.

Ví dụ OAuth2 Bearer khi thiếu token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Ví dụ token không hợp lệ, nếu Authorization Server/Resource Server công bố lỗi theo RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="The access token expired"
```

Đây là **mẫu minh họa**. Cách đặt `realm`, `error_description` và các headers phụ thuộc cấu hình; không phải mọi 401 luôn chứa chính xác nội dung trên. **Đừng** dùng error description để lộ raw token, user existence, signing keys hoặc metadata nội bộ.

### 2.1. Khi nào request chưa xác thực?

- Không có session/cookie hợp lệ và endpoint yêu cầu authentication.
- Không có header `Authorization` khi API yêu cầu Basic/Bearer.
- Basic username/password sai, hoặc credential bị từ chối.
- Bearer token hết hạn, sai chữ ký, sai issuer/audience, bị revoke theo policy hoặc không được resource server chấp nhận.
- Authentication trước đó không có hoặc không đạt yêu cầu của một entry point.

Không phải mọi kiểm tra token thất bại đều do **thiếu scope**. Token có thể hợp lệ về mặt xác thực nhưng thiếu scope cho resource; tình huống đó thường là **403** thay vì 401 khi resource server đã thiết lập Authentication.

### 2.2. 401 và session hết hạn

Một SPA gọi `fetch("/api/me")` có thể nhận 401 khi session hết hạn nếu backend API entry point được cấu hình cho 401. Nhưng một ứng dụng form-login mặc định có thể trả 302 đến `/login`; browser `fetch` đi theo redirect và nhận HTML login page, làm code tưởng response JSON hợp lệ.

Vì vậy không chỉ nhìn status sau cùng trong JavaScript. Kiểm tra **status ban đầu**, `Location`, `Content-Type` và các redirects được fetch/browser thực hiện.

### 2.3. Không dùng 401 thay cho lỗi nghiệp vụ bình thường

Validation lỗi input nên trả 400/422 theo API contract; resource không tìm thấy thường 404; conflict trạng thái có thể 409. Chỉ vì request được xử lý trong một hệ thống bảo mật không có nghĩa mọi lỗi ứng dụng đều là 401/403.

## 3. HTTP 403: bị từ chối, không phải bắt người dùng đăng nhập lại mãi

`403 Forbidden` thường dùng khi request đã được nhận diện nhưng **không thỏa policy**:

- User có `ROLE_USER` nhưng endpoint cần `ROLE_ADMIN`.
- Token Bearer hợp lệ nhưng không có scope `orders:write`.
- Đã đăng nhập nhưng không thuộc tenant sở hữu tài nguyên.
- User không phải owner của document, hoặc clearance thấp hơn classification.
- Method security `@PreAuthorize` trả deny và exception được dịch thành 403 ở web layer.
- Request POST/PUT/DELETE bị chặn do CSRF protection, tùy flow và entry point.

Ví dụ web/API sau khi đã xác thực:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access denied"
}
```

Đây là **JSON body gợi ý cho API**, không phải body mà Spring Security mặc định nhất thiết trả. Response mặc định có thể trống, có trang lỗi HTML, hoặc có schema tùy chỉnh.

### 3.1. 403 không tự xác định nguyên nhân

Một request `POST /api/orders` nhận 403 có thể đến từ:

1. CSRF token thiếu/sai; request bị chặn **trước khi** logic authorization role chạy.
2. User có authentication nhưng thiếu quyền `ORDER_WRITE`.
3. User có role nhưng truy cập sai tenant (ABAC).
4. Handler custom tự trả 403.
5. CORS/preflight hoặc reverse proxy chặn request trước ứng dụng, có thể cho status khác.

Khi test role, cần **cung cấp CSRF token hợp lệ nếu CSRF bật**, rồi mới kết luận lỗi 403 là do thiếu quyền. Không tắt CSRF chỉ để một test phân quyền đạt 200.

### 3.2. 403 có nên chuyển hướng login?

Thông thường, người dùng **đã xác thực nhưng không đủ quyền** nên thấy 403/permission page chứ không bị kéo vào vòng login lại. Việc redirect mọi `AccessDeniedException` về `/login` có thể tạo vòng lặp: login thành công -> truy cập trang admin -> thiếu role -> redirect login -> login lại vẫn thiếu role.

Web UX có thể hiển thị một trang giải thích “Bạn không có quyền truy cập”, nhưng cần phân biệt **không đăng nhập** với **không được phép**, bảo đảm trang lỗi không làm lộ thông tin nhạy cảm.

## 4. 302 Redirect: một lựa chọn giao diện, không đồng nghĩa authorization thành công

Với browser-based web app, `LoginUrlAuthenticationEntryPoint` thường dùng redirect:

```http
HTTP/1.1 302 Found
Location: /login
```

Browser sau đó gọi `GET /login`, hiển thị trang đăng nhập. Sau khi user submit form login thành công, request cache/success handler có thể đưa user trở lại tài nguyên đã yêu cầu trước đó.

```text
Browser: GET /web/me (chưa có session)
       |
       v
Authorization yêu cầu authenticated()
       |
       v
AuthenticationEntryPoint: 302 Location /login
       |
       v
Browser GET /login -> trang form
       |
       v
POST /login + CSRF token + credentials
       |
       +--> thành công: xác thực + session + redirect theo success handler
       +--> thất bại: thường redirect /login?error
```

**Một chuyển hướng 302 không có nghĩa user có quyền**. Nó chỉ là một bước trong luồng yêu cầu authentication. Nếu user đăng nhập thành công nhưng không có quyền tới trang gốc, request sau khi quay lại có thể nhận 403.

### 4.1. Redirect phải hợp với loại client

Browser điều hướng trang HTML thì 302 login là tự nhiên. Với mobile app, SPA gọi JSON API, background job hoặc service-to-service client, redirect sang trang HTML login thường là **không phù hợp**:

- API client có thể tự follow redirect, nhận 200 chứa HTML thay vì JSON.
- Mobile app không biết phải mở form web nào.
- Client dùng Bearer token không giải quyết được lỗi bằng login form của server.
- CORS có thể che response redirect tới IdP khác domain.
- Monitoring có thể hiểu nhầm 200 của trang login là API success.

Cần cấu hình entry point phù hợp từng `SecurityFilterChain` và URL/API contract.

### 4.2. Saved request và redirect sau login

Spring Security có cơ chế `RequestCache` để lưu một request chưa xác thực trước khi redirect đến login. Khi đăng nhập thành công, `SavedRequestAwareAuthenticationSuccessHandler` có thể đưa browser về URL trước đó.

Nhưng không nên tin một URL `redirect` do user cung cấp tùy ý để điều hướng sau login. Open redirect có thể bị lợi dụng để phishing và lộ trạng thái. Khi hỗ trợ custom return URL, cần allowlist đường dẫn nội bộ, kiểm tra scheme/host và tránh chuyển token qua query string.

### 4.3. Trang login phải được phép truy cập

Nếu `/login` cũng bị policy yêu cầu authentication và không có ngoại lệ phù hợp, user có thể bị redirect loop. Với generated login form của Spring Security, dùng `formLogin(form -> form.permitAll())` hoặc cấu hình permit đúng login page và login processing endpoint khi custom.

Cũng cần permit static assets của login page với phạm vi hẹp, nhưng không bỏ qua security headers/filters nếu không cần thiết.

## 5. Spring Security quyết định 401, 403 hoặc login redirect ở đâu?

Các thành phần quan trọng trên Servlet stack:

- `SecurityContextHolder`: giữ `Authentication` hiện tại.
- `AnonymousAuthenticationFilter`: có thể tạo `AnonymousAuthenticationToken` khi chưa có authentication khác.
- `AuthorizationFilter`: thực thi quy tắc `authorizeHttpRequests`.
- `ExceptionTranslationFilter`: nối các exception từ security chain với response dành cho HTTP.
- `AuthenticationEntryPoint`: bắt đầu authentication challenge/redirect khi cần.
- `AccessDeniedHandler`: xử lý access denied theo policy response.
- `AuthenticationTrustResolver`: giúp phân biệt anonymous và remember-me/full authentication khi lựa chọn cách xử lý.
- `RequestCache` và `SavedRequestAwareAuthenticationSuccessHandler`: hỗ trợ browser quay lại trang trước login khi phù hợp.

```text
HTTP request
    |
    v
Authentication filters (session/form/basic/bearer...)
    |
    v
SecurityContext / Authentication
    |
    v
ExceptionTranslationFilter
    |
    v
AuthorizationFilter + authorization rule
    |
    +--> ALLOW -> Controller/Service
    |
    +--> DENY -> AccessDeniedException
                   |
                   +--> anonymous/chưa đủ xác thực?
                   |       |
                   |       +--> AuthenticationEntryPoint
                   |                |
                   |                +--> form web: 302 /login
                   |                +--> Basic API: 401 + WWW-Authenticate
                   |                +--> Bearer: 401 + WWW-Authenticate
                   |
                   +--> authenticated nhưng không đủ quyền?
                           |
                           +--> AccessDeniedHandler
                                    |
                                    +--> thường 403
                                    +--> Bearer: có thể thông báo insufficient_scope
```

**Quan trọng:** `AuthenticationException` cũng được xử lý để bắt đầu authentication; lỗi credential có thể phát sinh trực tiếp trong authentication filter và được failure handler/entry point tương ứng xử lý. Sơ đồ trên mô tả đường authorization phổ biến, **không có nghĩa mọi exception đều bắt đầu ở AuthorizationFilter**.

### 5.1. AuthenticationException so với AccessDeniedException

`AuthenticationException` biểu diễn lỗi/chưa xác thực; `AuthenticationEntryPoint.commence(...)` phụ trách khởi động authentication khi được gọi. Với form login, một request login credentials sai thường đi qua `AuthenticationFailureHandler` để redirect `/login?error`, không nhất thiết ném thẳng exception đến `ExceptionTranslationFilter`.

`AccessDeniedException` thường xuất hiện khi authorization rule không cho phép, nhưng `ExceptionTranslationFilter` có thể phân nhánh: nếu principal anonymous hoặc không đạt mức authentication yêu cầu, **khởi động authentication qua entry point** thay vì trả 403. Nếu principal đã xác thực đầy đủ nhưng thiếu authority, dùng `AccessDeniedHandler`.

### 5.2. Remember-me và fullyAuthenticated()

`RememberMeAuthenticationToken` khác với authentication sau khi user vừa nhập credentials. Một endpoint `fullyAuthenticated()` có thể không chấp nhận remember-me. Khi đó có thể cần entry point để người dùng xác thực lại thay vì coi remember-me là đủ. Trải nghiệm chính xác phụ thuộc trust resolver, handler, entry point và cách remember-me được cấu hình.

Không dựa vào `authentication.isAuthenticated()` duy nhất để đánh giá “đã nhập lại mật khẩu gần đây”, vì remember-me authentication có thể vẫn có trạng thái authenticated nhưng mức tin cậy khác full authentication.

### 5.3. Khi controller ném exception

Spring MVC `@ControllerAdvice` xử lý exception tại controller/service theo cơ chế MVC, nhưng **không tự xử lý mọi exception được phát sinh trong Servlet security filters trước controller**. Muốn nhất quán response bảo mật của API, cần cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` ở Spring Security, đồng thời thiết kế riêng MVC error handling khi nghiệp vụ cần.

Đừng chỉ viết `@ExceptionHandler(AccessDeniedException.class)` rồi tuyên bố mọi lỗi 401/403 do filter đã đổi thành JSON.

## 6. Form-login browser app: 302 khi anonymous, 403 khi user thiếu quyền

Cấu hình web app truyền thống thường dùng session:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/public").permitAll()
        .requestMatchers("/web/admin").hasRole("ADMIN")
        .anyRequest().authenticated());

http.formLogin(form -> form.permitAll());
```

Đây là **fragment cấu hình**, không phải class độc lập.

Nếu anonymous gọi `GET /web/admin`, Spring Security có thể redirect `/login` vì anonymous cần xác thực. Nếu đã login với role USER nhưng gọi `GET /web/admin`, policy `hasRole("ADMIN")` từ chối và response thường 403.

Cùng URL nhưng **khác trạng thái principal** dẫn đến response khác nhau; điều đó đúng với thiết kế.

### 6.1. Form login credentials sai

Người dùng gửi `POST /login` với username/password sai. Với default form login, response thường redirect tới `/login?error`. Đây là **authentication failure của login processing**, khác với anonymous gọi endpoint bảo vệ (302 tới `/login`).

Đừng cấu hình thông báo quá chi tiết như “Email tồn tại nhưng sai password”, vì có thể giúp liệt kê tài khoản. Bảo vệ chống brute-force, rate limiting, session fixation, cookie flags và CSRF theo threat model.

### 6.2. Session hết hạn và chuyển hướng

Khi session `JSESSIONID` hết hạn, request tới protected web page không còn authentication từ session. Hành vi có thể giống anonymous và redirect login. Nhưng app có remember-me thì `RememberMeAuthenticationFilter` có thể tự xác thực từ cookie dài hạn; do đó không phải mọi lần session hết hạn đều dẫn tới login.

Để kiểm thử “anonymous”, không dùng cùng phiên/cookie remember-me hợp lệ từ lần đăng nhập trước.

### 6.3. 403 page cho người đã login

Web app có thể tùy chỉnh:

```java
// Fragment trong cấu hình HttpSecurity:
http.exceptionHandling(ex -> ex
        .accessDeniedPage("/access-denied"));
```

Nếu dùng trang access denied, cần permit/mapping đúng, không tạo vòng lỗi. Tùy version và cấu hình, handler có thể forward đến view, giữ status 403; **không nên** vô tình trả 200 “success” cho một lỗi bị từ chối. Test status và nội dung; đừng chỉ test có trang HTML hiển thị.

## 7. API HTTP Basic: 401 challenge thay vì redirect

HTTP Basic là một cơ chế HTTP authentication, phù hợp minh họa API client (nhưng production cần HTTPS; Basic credential không tự hết hạn như token).

```java
// Fragment API chain:
http.httpBasic(Customizer.withDefaults());
```

Trường hợp mặc định:

| API request | Kỳ vọng |
| --- | --- |
| `GET /api/me` không có Authorization | **401** với `WWW-Authenticate: Basic...` |
| `GET /api/me` Basic password sai | **401** |
| `GET /api/me` Basic đúng của role USER | **200** |
| `GET /api/admin` Basic đúng của USER, yêu cầu ADMIN | **403** |
| `GET /api/admin` Basic đúng của ADMIN | **200** |

API client dùng 401 để yêu cầu credentials, lưu ý không retry vô hạn hoặc gửi lại secret tới host khác. Không có lý do để redirect sang `/login` HTML khi contract endpoint là máy-gọi-máy.

### 7.1. 401 không phải lúc nào cũng body JSON

Default `BasicAuthenticationEntryPoint` có thể trả 401 và header Basic challenge mà không có body JSON như mong muốn. Nếu API contract yêu cầu `application/problem+json`, cần custom entry point ở đúng filter chain; đừng chờ Spring tự dựng JSON từ mọi exception.

### 7.2. CSRF với Basic

Browser cũng có thể tự gửi HTTP Basic credentials sau khi người dùng xác thực trong browser. Vì vậy **không phải cứ HTTP Basic là an toàn để tắt CSRF**. Với API chỉ được gọi bởi machine clients không mang credentials tự động, cần đánh giá threat model riêng trước khi cấu hình CSRF.

Trong dự án mẫu, CSRF giữ bật trên **cả hai chains**; `POST /api/orders` cần token hợp lệ, cho phép test phân biệt thiếu CSRF và thiếu role. Dự án dùng Basic chủ yếu để dễ test status; không tuyên bố là cấu hình API production tối ưu.

## 8. OAuth2 Resource Server/Bearer: 401 hoặc 403 theo token và scope

Với Spring Security Servlet và OAuth2 Resource Server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Đây là **fragment**; cần dependency resource-server và cấu hình issuer/JWK hoặc decoder đáng tin. API Bearer thường không redirect tới login form của chính resource server; client phải lấy access token hợp lệ từ Authorization Server theo flow riêng.

### 8.1. Thiếu token

`GET /api/orders` không có `Authorization: Bearer ...` khi resource yêu cầu authentication có thể nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Đây là challenge phù hợp OAuth2 Bearer. Không tự cho rằng backend sẽ gửi redirect đến IdP. Resource server không đồng nghĩa OAuth2 Login client.

### 8.2. Token không hợp lệ hoặc hết hạn

`BearerTokenAuthenticationEntryPoint` có thể trả 401 và gợi ý error `invalid_token` theo RFC 6750. Ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Token sai chữ ký, hết hạn, sai issuer/audience hoặc không được decoder/validator chấp nhận thì không có authentication hợp lệ. Không lấy JWT chưa verify làm cơ sở cấp authorities. Không echo raw Bearer token trong error body/log.

### 8.3. Token hợp lệ nhưng thiếu scope

Nếu token đã được xác thực nhưng thiếu `SCOPE_orders.write`, rule có thể từ chối:

```java
.requestMatchers(HttpMethod.POST, "/api/orders")
.hasAuthority("SCOPE_orders.write")
```

Với `BearerTokenAccessDeniedHandler`, response có thể là 403 cùng `WWW-Authenticate: Bearer error="insufficient_scope"`, tùy trạng thái OAuth2 authentication và các thông tin scope được cấu hình.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
```

**Không** khẳng định mọi 403 đều có `insufficient_scope` hoặc tự chế header bất kể nguyên nhân. Handler có thể khác nếu không có authenticated OAuth2 token, nếu cấu hình custom, hoặc policy bị từ chối vì tenant/resource ownership chứ không phải scope.

### 8.4. JWT có scope nhưng vẫn bị ABAC deny

`hasAuthority("SCOPE_orders.write")` chỉ kiểm tra quyền tổng quát. User có scope đúng vẫn có thể không được sửa order khác tenant. Khi method security `@PreAuthorize` kiểm tra ownership/tenant và deny, API thường trả 403; nên tránh tiết lộ tài nguyên của tenant khác trong error detail.

### 8.5. Không gọi OAuth2 login trên Resource Server chỉ để giải quyết 401

`oauth2Login()` dùng cho ứng dụng đăng nhập người dùng bằng browser/authorization code flow; `oauth2ResourceServer().jwt()` dùng cho request mang Bearer access token. Chúng có thể cùng tồn tại trong một hệ thống có thiết kế rõ, nhưng không thay thế cho nhau. Một API nhận JWT không nên tùy tiện trả trang login HTML cho mọi 401.

## 9. SPA, mobile và machine-to-machine: chọn contract lỗi phù hợp

### 9.1. SPA có session cookie

Một SPA cùng origin với Spring Boot backend có thể dùng session cookie. Khi session hết hạn, REST endpoint nên trả một response mà JavaScript xử lý ổn định, thường **401 JSON**, trong khi URL trang HTML có thể chuyển hướng tới login.

Giải pháp có thể là **nhiều SecurityFilterChain** theo `/api/**` và `/web/**`, hoặc custom `DelegatingAuthenticationEntryPoint` với request matchers phù hợp. Cần tránh cấu hình một global entry point làm HTML web pages mất redirect hoặc API lại nhận HTML login.

### 9.2. SPA với Bearer access token

API trả 401 khi token thiếu/hết hạn; frontend có thể chủ động điều hướng tới login hoặc thực hiện refresh theo thiết kế authorization của ứng dụng. Một 401 **không** phải lệnh bắt buộc tự retry token refresh vô hạn; cần giới hạn retry và phân biệt lỗi issuer, audience, token revoked, networking.

Nếu access token còn hiệu lực nhưng thiếu quyền, 403 nên dẫn tới UI “không được phép” hoặc flow yêu cầu admin cấp quyền, không tự refresh vô hạn để hy vọng được tăng scope.

### 9.3. Mobile application

Mobile không nên phụ thuộc vào redirect HTML 302 trả từ API JSON. Authentication có thể được xử lý trong browser riêng qua OAuth2 Authorization Code + PKCE, nhưng **API resource server** vẫn dùng 401/403 đúng HTTP contract. Mobile hiển thị login/permission UX từ status, không để backend bí mật trả HTML form.

### 9.4. Machine-to-machine

Service account gọi API bằng Bearer token hoặc client credentials flow. 401/403 thường được xử lý bằng logs, metrics và token management, không có browser để hiển thị trang login. Nếu token thiếu scope thì operator/client configuration phải thay đổi; retry cùng token sau 403 thường vô ích.

### Bảng đề xuất hành vi client

| Client | 401 | 403 | 302 login |
| --- | --- | --- | --- |
| Browser page truyền thống | Thường do entry point convert thành redirect | Hiển thị access denied | Thường phù hợp |
| SPA `fetch` REST API | Hiện trạng thái hết authentication, điều hướng frontend/login | Hiển thị thiếu quyền | Dễ bị follow redirect thành HTML ngoài ý muốn |
| Mobile API client | Kích hoạt authentication flow do app kiểm soát | Hiển thị thiếu quyền/không cho thao tác | Không nên trả HTML login từ API |
| M2M API client | Kiểm tra/nhận token mới nếu policy cho phép | Không retry vô hạn, báo thiếu scope/quyền | Không phù hợp |
| OAuth2 Resource Server | Bearer challenge | Bearer insufficient scope/ABAC deny | Không phải mặc định |

## 10. Nhiều SecurityFilterChain để tách API và web

Spring Security Servlet hỗ trợ nhiều filter chains được sắp bằng `@Order`. Ví dụ:

```text
Request /api/me
  -> SecurityFilterChain @Order(1) securityMatcher("/api/**")
  -> HTTP Basic entry point
  -> thiếu authentication -> 401

Request /web/me
  -> SecurityFilterChain @Order(2) catch-all
  -> formLogin entry point
  -> thiếu authentication -> 302 /login
```

Đây không phải “rule cụ thể hơn tự thắng”. `FilterChainProxy` chọn **chain đầu tiên** match. Nếu catch-all chain đứng trước API chain, nó có thể che API chain, khiến API cũng redirect login thay vì trả 401.

### 10.1. securityMatcher khác requestMatchers

- `securityMatcher("/api/**")`: request nào đi vào **toàn bộ chain** và dùng các filters/entry point tương ứng.
- `requestMatchers("/api/admin")` trong `authorizeHttpRequests`: chọn **authorization rule bên trong chain** đã được chọn.

Một rule `requestMatchers("/api/admin").hasRole("ADMIN")` **không thể bảo vệ** `/api/admin` nếu nó nằm trong chain chỉ match `/web/**`.

### 10.2. Fallback chain

Nếu chỉ có API chain `securityMatcher("/api/**")` mà không có fallback cho các URL khác, request ngoài `/api/**` có thể không đi qua Spring Security chain nào. Hãy thiết kế fallback chain xử lý web hoặc deny-by-default theo phạm vi ứng dụng.

## 11. CSRF: tại sao POST có thể 403 trước khi kiểm tra role?

Spring Security bật CSRF theo mặc định đối với các request unsafe phù hợp. Khi browser dựa trên session cookie hoặc những credentials browser tự gửi, CSRF là một lớp bảo vệ quan trọng.

```text
POST /api/orders (đã HTTP Basic user ADMIN)
    |
    +--> Không có CSRF token
    |
    v
CsrfFilter -> AccessDeniedException / CSRF failure path
    |
    v
Thông thường 403
    |
    +--> Rule hasRole("ADMIN") chưa cần chạy
```

Vì vậy “request ADMIN mà vẫn 403” **chưa đủ** để kết luận admin role sai. Trong MockMvc, test rule role bằng `with(csrf())`; sau đó test riêng việc thiếu CSRF có bị chặn hay không.

### 11.1. Khi nào cân nhắc disable CSRF?

Đối với API thuần stateless sử dụng Bearer token trong `Authorization` header và **không** sử dụng browser credentials tự gửi, tổ chức có thể quyết định CSRF không cần thiết trên API chain đó. Nếu tắt, chỉ nên tắt trong **chain phù hợp** sau khi đánh giá authentication mechanism, cookies và CORS. Đừng tắt CSRF cho toàn bộ web app dùng session/form login chỉ để API hoạt động.

### 11.2. 403 CSRF và 403 thiếu quyền khác nhau

Một test chỉ assert `status().isForbidden()` cho POST không chắc đã test authorization. Thiết kế test nên gồm:

1. Người có quyền + **không** CSRF → reject.
2. Người thiếu quyền + **có** CSRF → reject vì authorization.
3. Người có quyền + **có** CSRF → success.
4. Anonymous + CSRF → entry point/unauthenticated response phù hợp.

Sau đó kiểm tra request có/không thực sự thay đổi dữ liệu. Test negative status cùng test không có side effect.

## 12. API JSON errors và Problem Details

REST API thường muốn một schema lỗi ổn định, ví dụ theo RFC 9457 Problem Details:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication required"
}
```

Hoặc:

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access denied"
}
```

`Content-Type` có thể là `application/problem+json`. Các field `type`, `title`, `status`, `detail` là cấu trúc phổ biến, nhưng tổ chức có thể có contract bổ sung. Không dùng detail tiết lộ “User alice thuộc tenant north nhưng document 102 thuộc south” nếu điều đó làm lộ metadata nhạy cảm.

**Quan trọng:** JSON body không thay thế nghĩa vụ `WWW-Authenticate` khi sử dụng HTTP Basic/Bearer challenges. Nếu custom 401, phải giữ header challenge đúng scheme để client hiểu request cần loại authentication nào.

### 12.1. Cấu hình handler riêng ở đúng chain

Đây là fragment mô tả tùy biến response cho một **API chain**. Không dán nó trực tiếp vào project Basic demo bên dưới mà chưa phân tích entry point của Basic và expected `WWW-Authenticate`:

```java
http.exceptionHandling(ex -> ex
        .authenticationEntryPoint((request, response, authError) -> {
            response.setStatus(401);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.setHeader("WWW-Authenticate", "Basic realm=\"api\"");
            response.getWriter().write(
                    "{\"type\":\"about:blank\",\"title\":\"Unauthorized\",\"status\":401}");
        })
        .accessDeniedHandler((request, response, denied) -> {
            response.setStatus(403);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(
                    "{\"type\":\"about:blank\",\"title\":\"Forbidden\",\"status\":403}");
        }));
```

Đoạn code là **fragment nằm trong cấu hình HttpSecurity**, giả định Basic API. Không dùng header `Basic` cho Bearer resource server; với Bearer hãy giữ semantics RFC 6750 và ưu tiên `BearerTokenAuthenticationEntryPoint`/`BearerTokenAccessDeniedHandler` hoặc mở rộng có kiểm chứng. Với production nên dùng serializer phù hợp, tránh tự nối JSON từ input, tránh lỗi double-commit response và có thống kê lỗi.

### 12.2. MVC ControllerAdvice không bao phủ toàn bộ filter

`@ControllerAdvice` có thể trả `ProblemDetail` cho lỗi domain/controller, nhưng một `AuthenticationException` bị bắt ở security filter chain có thể không đi qua exception handler MVC. Khi muốn response API thống nhất, cấu hình cả security entry point/denied handler **và** MVC error handler; test cả hai đường đi.

### 12.3. Không redirect đến URL do user nhập

Nếu API hoặc web có tham số `returnUrl`, tuyệt đối không redirect tùy ý tới domain ngoài hoặc URL chứa open redirect. Chỉ chấp nhận relative internal path hoặc allowlist và tránh query string chứa tokens. Đặc biệt với OIDC login, redirect URI phải được đăng ký ở IdP.

## 13. Dự án Spring Boot chạy được: cùng app, web 302 và API 401

Bài demo dùng **Java 17+**, **Spring Boot 3.3.5** (Spring Security 6.x do Boot quản lý), **Gradle 8.5**, HTTP Basic cho `/api/**` và form login cho web. Không cần cơ sở dữ liệu/IdP.

Mục tiêu thực hành:

- Anonymous `GET /api/me` → **401** + Basic challenge.
- Anonymous `GET /web/me` → **302** tới `/login`.
- Alice login form rồi `GET /web/admin` → **403**.
- Alice dùng Basic gọi `GET /api/admin` → **403**.
- Admin đúng role vào `/web/admin` và `/api/admin` → **200**.
- POST API với đúng role nhưng **thiếu CSRF** → **403**.
- POST API với sai role **và có CSRF** → **403**.
- POST API với đúng role **và có CSRF** → **200**.
- Form credentials sai → redirect với `error`; không nhầm với 401 API.
- `/api/public` công khai và không làm mở các endpoint khác.
- Logout web sau login có CSRF, session bị invalidate.

### 13.1. Cấu trúc thư mục

```text
security-response-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SecurityResponseTest.java
```

### 13.2. settings.gradle

```groovy
rootProject.name = 'security-response-demo'
```

### 13.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 13.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 13.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("study123"))
                .roles("USER", "EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("study123"))
                .roles("USER", "ADMIN", "EDITOR")
                .build();

        return new InMemoryUserDetailsManager(alice, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {

        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                        .hasRole("EDITOR")
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // CSRF không bị tắt: kể cả Basic API, POST cần token theo demo.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/goodbye").permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form.permitAll());

        http.logout(logout -> logout
                .logoutSuccessUrl("/goodbye")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll());

        return http.build();
    }
}
```

**Giải thích:**

1. `@Order(1)` API chain với `securityMatcher("/api/**")` đứng trước web fallback chain. Do đó API thiếu authentication dùng **HTTP Basic entry point**, không bị form-login chain redirect HTML.
2. `@Order(2)` web chain là fallback, dùng form login/session, nên anonymous web page thường nhận redirect `/login`.
3. `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`. User `alice` chỉ có `ROLE_USER`, vì thế đã login vẫn bị 403.
4. `httpBasic(Customizer.withDefaults())` gửi Basic challenge khi cần authentication. Cấu hình API ở đây là **stateless** đối với security session.
5. CSRF **không bị disable** ở API hoặc web. Vì browser có thể tự gửi Basic credentials, đây là lựa chọn dễ hiểu cho bài minh họa, dù production pure bearer API có thể có chính sách khác.
6. `.requestMatchers(HttpMethod.POST, "/api/orders")` có rule cho role EDITOR. Dòng `.anyRequest().authenticated()` là fallback của API chain.
7. Web form login và logout dùng các endpoint chuẩn của Spring Security. Page `/login` được generated khi không đặt custom login page.
8. Username/password trong source chỉ cho localhost demo, không dùng trong production.

**Không tạo `SecurityFilterChain` catch-all đứng trước API chain** vì làm API nhận entry point sai. **Không thêm `http.formLogin()` vào API chain** nếu contract API dự kiến là Basic-only; nếu có cả Basic và form trên cùng chain, phải định nghĩa rõ request matcher của entry point.

### 13.6. DemoController.java

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/goodbye")
    public String goodbye() {
        return "goodbye";
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/admin")
    public String webAdmin(Authentication authentication) {
        return "web-admin:" + authentication.getName();
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin(Authentication authentication) {
        return "api-admin:" + authentication.getName();
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public String createOrder(Authentication authentication) {
        return "created:" + authentication.getName();
    }
}
```

Endpoint API `POST /api/orders` cố ý trả **201 Created** khi thành công, phù hợp operation tạo dữ liệu; không nhầm với `200 OK`. Kiểm thử dưới đây assert **201** chứ không mặc định mọi success đều 200.

Chưa có database trong demo. `@ResponseStatus(HttpStatus.CREATED)` chỉ làm rõ status contract; sản phẩm thực cần validation, resource ownership và transaction.

## 14. SecurityResponseTest: kiểm thử status, redirect và challenge header

`src/test/java/demo/SecurityResponseTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityResponseTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginWeb(String username) throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", username)
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection());

        return session;
    }

    @Test
    void publicApiDoesNotChallenge() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
    }

    @Test
    void anonymousApiGets401AndBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void invalidBasicCredentialsGet401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void validBasicUserGets200() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api:alice"));
    }

    @Test
    void userWithoutAdminRoleGets403Not401() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "study123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminGets200OnApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-admin:admin"));
    }

    @Test
    void anonymousWebGets302ToLogin() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void anonymousWebAdminAlsoRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/web/admin"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void loginFormGetsBrowserSession() throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(get("/web/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web:alice"));
    }

    @Test
    void loggedInWebUserWithoutAdminRoleGets403()
            throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(get("/web/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void loggedInWebAdminGets200() throws Exception {
        MockHttpSession session = loginWeb("admin");

        mvc.perform(get("/web/admin").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web-admin:admin"));
    }

    @Test
    void invalidFormLoginRedirectsWithError() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String redirected = result.getResponse().getRedirectedUrl();
        assertNotNull(redirected);
        assertTrue(redirected.contains("/login?error"));
    }

    @Test
    void apiPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("editor", "study123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithCsrfButWithoutRoleIsForbidden()
            throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("alice", "study123"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithRoleAndCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("editor", "study123"))
                        .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created:editor"));
    }

    @Test
    void webLogoutInvalidatesSession() throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertTrue(session.isInvalid());

        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void unknownApiPathWithoutLoginCanBe401BeforeMvc404()
            throws Exception {
        mvc.perform(get("/api/unknown"))
                .andExpect(status().isUnauthorized());
    }
}
```

**Kết quả dự kiến:** 17 JUnit tests PASS với cấu hình và phiên bản trong demo. Đây là **kỳ vọng sau khi đọc và kiểm tra mã**, không phải tuyên bố đã chạy test trong môi trường thực tế. Một số response/header có thể thay đổi nếu thêm filter/entry point tùy chỉnh hoặc nâng framework version; hãy chạy test khi tích hợp.

### 14.1. Bốn điều test chứng minh rõ

1. **API challenge:** 401 có `WWW-Authenticate` Basic, khác với 302 của form-login.
2. **Authenticated thiếu role:** Alice nhận 403 trên `/api/admin` và `/web/admin`; không redirect login lại.
3. **Credential failure:** Basic sai dẫn đến 401; form login sai dẫn đến redirect `/login?error`.
4. **CSRF vs authorization:** POST thiếu CSRF 403, POST đủ CSRF nhưng thiếu role 403, POST đủ cả hai thành công **201**.

### 14.2. Những điều test chưa chứng minh

- Không có Bearer JWT decoder/IdP trong project nên không thể coi 17 tests này đã xác minh RFC 6750 Bearer behavior thực tế.
- Không test CORS preflight từ browser hoặc reverse proxy/TLS.
- Không test request cache/saved request ở tất cả browser/session states.
- Không test JSON `ProblemDetail` handlers tùy biến (project dùng default responses).
- Không test session fixation/remember-me, phân quyền đối tượng (IDOR/BOLA) hoặc rate limiting.

Đây là những suite bổ sung cần có khi chuyển từ bài học sang sản phẩm.

## 15. Chạy ứng dụng và quan sát HTTP

Với JDK 17+ và Gradle 8.5 (hoặc Gradle Wrapper tương thích), tại thư mục dự án:

```bash
gradle test
gradle bootRun
```

Với Gradle Wrapper trên macOS/Linux:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell khi project có wrapper:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Thử API localhost (HTTP chỉ dùng demo, không gửi credentials qua mạng thật):

```bash
curl -i http://localhost:8080/api/public

curl -i http://localhost:8080/api/me

curl -i -u alice:study123 \
     http://localhost:8080/api/me

curl -i -u alice:study123 \
     http://localhost:8080/api/admin

curl -i -u admin:study123 \
     http://localhost:8080/api/admin
```

Kết quả dự kiến lần lượt: **200**, **401** kèm `WWW-Authenticate: Basic...`, **200**, **403**, **200**.

Thử browser ở `http://localhost:8080/web/me`: khi chưa login thường được redirect `/login`. Đăng nhập bằng `alice/study123`, truy cập `/web/admin` sẽ bị 403. Đăng nhập bằng `admin/study123` thì truy cập được.

**Không** khuyến nghị gọi `POST /login` với `curl` không có session/CSRF token; dạng form login mặc định có CSRF token liên quan request. Nếu POST `/api/orders` mà thiếu CSRF, 403 là behavior dự kiến của demo.

### 15.1. Thử curl và redirects

Mặc định `curl -i` không tự follow redirect; nó hiển thị status 302 và Location. Nếu dùng `curl -L`, client tự gửi request tiếp theo và có thể cho bạn thấy **200 HTML trang login**, che giấu response 302 ban đầu.

Khi debug, hãy kiểm tra từng response trong redirect chain. Với browser DevTools, quan sát cột Status/Location/Content-Type và request initiator. Không chụp/gửi cookie giá trị thực hoặc Basic Authorization header chứa credential.

## 16. Resource Server Bearer: bộ test bổ sung nên viết thế nào?

Với resource server thực, cần dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Và security rules phù hợp:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public")
                .permitAll()
        .requestMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
        .anyRequest().authenticated());

http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Các đoạn trên là **fragments cấu hình** của một dự án riêng, **không thêm vào cùng API Basic chain của demo** nếu chưa thiết kế multi-scheme behavior. Cần cấu hình JWT decoder/JWK/issuer cho production.

### 16.1. Kiểm thử JWT với spring-security-test

Có thể dùng `SecurityMockMvcRequestPostProcessors.jwt()` để tạo authenticated JWT trong **MockMvc tests** và đưa authorities/scopes vào security context một cách có kiểm soát:

```java
// Fragment bên trong một MockMvc test có api matcher và Bearer rules:
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
   .andExpect(status().isCreated());
```

Đây chỉ là **fragment**, cần import static `jwt()` và `SimpleGrantedAuthority`, setup tương ứng. Nó test authorization với `JwtAuthenticationToken` giả lập; **không** chứng minh JWT signature/issuer/JWK validation thật. Nếu CSRF bật ở chain đó, thêm `with(csrf())` để test role/scope; với pure Bearer stateless chain, quyết định CSRF dựa trên threat model đã được xem xét.

### 16.2. Test 401 challenge thật

Để kiểm chứng `WWW-Authenticate: Bearer` trên request thiếu token hoặc invalid token thực sự, cần gọi endpoint **không dùng `jwt()`**, có `BearerTokenAuthenticationFilter` và resource-server entry point trong test context. Có thể cấu hình mock `JwtDecoder` ném `JwtException` tương ứng để xác minh invalid token; đừng tự suy ra 401 từ một test dùng `jwt()` vì helper đó bỏ qua decoder.

### 16.3. Test 403 insufficient_scope

Tạo JWT authentication đã được xác minh theo test setup nhưng **không** có `SCOPE_orders.write`, gọi protected action; kỳ vọng 403. Kiểm tra `WWW-Authenticate` Bearer error trong test tích hợp với handler tương ứng, thay vì hard-code rằng mọi authorization failure đều có cùng header. Nếu API dùng ownership policy, một 403 không nhất thiết phải có `insufficient_scope`, đặc biệt khi scope đủ nhưng tài nguyên thuộc tenant khác.

## 17. Khi nào nên trả 404 thay vì 403?

Giả sử API `GET /api/documents/102` truy cập tài liệu nhạy cảm thuộc tenant khác. Nếu trả 403 cho ID tồn tại nhưng 404 cho ID không tồn tại, attacker có thể đoán tài liệu hợp lệ thông qua status.

Một hệ thống có thể áp dụng **resource concealment**: với tài nguyên ngoài phạm vi tenant/ownership, trả 404 theo API contract để không xác nhận sự tồn tại. Tuy nhiên:

- 404 không thay thế việc thực thi quyền thực sự.
- Không chỉ đổi status nhưng để response time/error detail tiết lộ metadata.
- Đừng dùng 404 che mọi lỗi vận hành/missing authentication; cần phân biệt authentication challenge và resource visibility.
- Quy tắc phải nhất quán ở service/query (tenant-scoped repository) và controller/exception translation.

HTTP 403 vẫn phù hợp khi user được phép biết tài nguyên tồn tại nhưng không được thực hiện action. Chọn giữa 403 và 404 cần chính sách bảo mật/UX rõ, không chỉ thói quen.

## 18. 405, 400, 409 và lỗi validation không phải security denial

| Status | Trường hợp phổ biến | Vì sao không dùng tùy tiện 401/403? |
| --- | --- | --- |
| **400 Bad Request** | JSON sai cấu trúc, tham số không hợp lệ, thiếu required field | Lỗi input có thể không liên quan authentication |
| **401 Unauthorized** | Thiếu/credential authentication không hợp lệ | Client cần authentication hợp lệ |
| **403 Forbidden** | Đã xác thực nhưng thiếu quyền; CSRF failure | Authentication không tự cấp quyền action |
| **404 Not Found** | Không tìm thấy resource hoặc che giấu resource ngoài phạm vi | Không khẳng định thiếu credentials |
| **405 Method Not Allowed** | Path có handler nhưng HTTP method không được map | Không có nghĩa user thiếu role |
| **409 Conflict** | Resource state xung đột, duplicate action | Không phải quyền truy cập |
| **429 Too Many Requests** | Rate limiting | Không nên dùng 401 để che tình trạng bị giới hạn request |

Spring Security có thể chặn request **trước khi đến MVC**. Ví dụ anonymous gọi `/api/missing`, nếu API chain yêu cầu authentication trước, request có thể nhận 401 thay vì 404; sau khi authenticated, MVC mới trả 404.

Tương tự, POST thiếu CSRF có thể nhận 403 trước khi Spring MVC xác định handler có hỗ trợ method hay không. **Status quan sát là kết quả của thứ tự filters và MVC, không chỉ route tồn tại.**

## 19. CORS preflight và phản hồi lỗi bất ngờ

Browser cross-origin có thể gửi `OPTIONS` preflight trước `GET/POST` thực, thường không kèm cookie/session/Authorization như request chính. Nếu SecurityFilterChain yêu cầu authentication cho mọi `OPTIONS`, API có thể trả 401/redirect và browser chặn request, tạo cảm giác API login “bị lỗi”.

Khi cần CORS:

- Cấu hình `http.cors(...)` và `CorsConfigurationSource`/Spring MVC CORS cho origins/methods/headers tin cậy.
- Đảm bảo CORS được xử lý đủ sớm trong security chain và preflight hợp lệ không bị buộc authentication không cần thiết.
- Không mặc định `permitAll("OPTIONS /**")` cho mọi hệ thống nếu không hiểu threat model.
- Không dùng wildcard origin với credentials một cách tùy tiện.
- Không tắt CSRF chỉ vì “đã bật CORS”. CORS và CSRF giải quyết hai nguy cơ khác nhau.

Debug preflight bằng browser DevTools/Network và response headers như `Access-Control-Allow-Origin`. Không kết luận “401 user sai mật khẩu” khi request bị chặn thực tế là OPTIONS preflight.

## 20. Log và telemetry: tìm đúng thành phần trả status

Khi request không đúng kỳ vọng, kiểm tra theo thứ tự:

1. **Request thực tế:** method, path, query, content type; không log raw Authorization/cookie.
2. **Chain được chọn:** `securityMatcher`, `@Order`, fallback.
3. **Authentication mechanism:** form login, Basic, Bearer, session, remember-me.
4. **SecurityContext:** có `Authentication` hợp lệ không? Principal anonymous hay authenticated? Authorities nào?
5. **Exception:** `AuthenticationException`, `AccessDeniedException`, `InvalidCsrfTokenException`, hay MVC exception?
6. **Entry point/handler:** `AuthenticationEntryPoint` nào bắt đầu authentication? `AccessDeniedHandler` nào đã trả 403?
7. **Response status và headers:** 302 `Location`, 401 `WWW-Authenticate`, 403 và headers Bearer khi phù hợp.
8. **Redirect chain:** client có tự follow redirect tới HTML login không?
9. **Authorization rule:** có role/scope/tenant/ownership không? Rule match đầu tiên là gì?
10. **CSRF/CORS:** POST thiếu token hay preflight OPTIONS thất bại?
11. **Proxy/IdP:** redirect/forwarded scheme/host/path có đúng và được tin cậy không?
12. **Thử lại có kiểm soát:** sửa đúng credential/role, đừng retry vô hạn.

Có thể bật trong môi trường dev:

```properties
logging.level.org.springframework.security=DEBUG
```

**Cảnh báo:** đừng log `Authorization` header, Bearer JWT, Basic password, session IDs, cookies, CSRF tokens, user private data. Error response không nên xuất raw exceptions/stack traces cho public clients.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| API JSON trả 302 đến form login | Client follow redirect, nhận HTML sai contract | API entry point trả 401/challenge phù hợp |
| Web truyền thống luôn trả 401 JSON | Browser không tự hiện login flow | Form-login chain và redirect hợp lý |
| User đã login thiếu role mà lại redirect login | Loop/UX sai, không tăng quyền | Dùng AccessDeniedHandler/403 |
| Không có `WWW-Authenticate` với HTTP Basic | Client không hiểu auth challenge | Giữ Basic entry point/header |
| Dùng Basic challenge cho Bearer API | Sai scheme, lỗi client interoperability | RFC 6750 Bearer handlers |
| Token JWT có signature invalid nhưng trả 403 | Nhầm invalid authentication với thiếu scope | Trả 401 theo token error semantics |
| Token hợp lệ thiếu scope nhưng trả 401 | Client refresh/relogin vô ích | Trả 403 khi authorization deny |
| Chỉ đổi MVC `@ControllerAdvice` | Lỗi Security filter vẫn default HTML/redirect | Cấu hình entry point/denied handler |
| Web fallback chain đặt trước API chain | API bị xử lý bởi form login | `@Order` + `securityMatcher` đúng |
| Không có fallback chain | URL có thể không được Spring Security bảo vệ | Thiết kế catch-all/fallback |
| Bật `csrf.disable()` toàn app để POST 200 | Mở CSRF trên form/session | Chỉ thay đổi theo threat model đúng chain |
| Test 403 của POST không có `with(csrf())` | Test chỉ chứng minh CSRF chặn | Thêm test có CSRF và kiểm tra role riêng |
| 200 HTML login sau API redirect bị coi là API success | JSON parser lỗi/hành vi khó debug | Kiểm tra redirect history/content type |
| Redirect URI nhận tùy ý từ query | Open redirect/phishing | Allowlist internal return URLs |
| Log nguyên JWT/Basic credentials | Lộ bearer/password | Redaction và access control logs |
| 403 tiết lộ owner/tenant khác | Information disclosure | Error detail chung, resource concealment |
| Anonymous 401 được giải thích như đã login thiếu quyền | Debug sai nguyên nhân | Xác định Authentication thực |
| Dùng 401 cho lỗi validation | Client retry credential vô ích | HTTP status theo lỗi thật |
| Retry 403 vô hạn trong app client | Tải hệ thống và không giải quyết thiếu quyền | Điều hướng user/permissions flow phù hợp |

## 22. Checklist trước khi triển khai

- [ ] Phân loại endpoint: HTML browser page, session API, Basic API hay Bearer Resource Server.
- [ ] Anonymous HTML page dẫn tới đúng trang login (nếu UX dùng form).
- [ ] Anonymous API nhận 401/challenge, không nhận HTML login ngoài ý muốn.
- [ ] Authenticated thiếu role/scope/tenant nhận deny phù hợp, thường 403.
- [ ] Basic 401 có `WWW-Authenticate: Basic`.
- [ ] Bearer 401/403 có header/error theo RFC 6750 khi phù hợp.
- [ ] Invalid credentials và insufficient authorization có regression tests riêng.
- [ ] CSRF bật/tắt theo threat model, không tắt global chỉ để test API.
- [ ] POST có role nhưng thiếu CSRF, có CSRF nhưng thiếu role, đủ cả hai được test độc lập.
- [ ] CORS preflight và OPTIONS hoạt động theo policy.
- [ ] `securityMatcher`/`@Order` chọn đúng chain, có fallback coverage.
- [ ] Form login page và login processing không gây redirect loop.
- [ ] Custom errors nhất quán giữa Security filters và MVC controllers.
- [ ] API errors có JSON contract, status đúng và không tiết lộ secret.
- [ ] Fetch/mobile client xử lý redirect, 401 và 403 theo loại UX.
- [ ] URL không tồn tại và resource concealment có quy tắc 404 rõ.
- [ ] Không có open redirect qua returnUrl/post-login URL.
- [ ] Test anonymous, authenticated USER, ADMIN và Basic invalid login.
- [ ] Khi nâng Spring Security/Boot, chạy lại tests status/header/redirect.
- [ ] Logs/metrics không chứa Authorization/cookies/JWT/CSRF secrets.

## 23. Câu hỏi tự kiểm tra

1. **Tại sao anonymous vào trang web có thể nhận 302 chứ không phải 401?** Vì form-login entry point khởi động authentication bằng browser redirect tới `/login`.
2. **HTTP Basic API chưa có credential thường trả gì?** 401 và `WWW-Authenticate: Basic`.
3. **User đã login nhưng thiếu `ROLE_ADMIN` thì gì?** Thường 403 qua `AccessDeniedHandler`, không bắt login lại mãi.
4. **OAuth2 access token hết hạn thường trả gì?** 401 với Bearer challenge/error phù hợp, không phải 403 insufficient scope.
5. **Token hợp lệ nhưng thiếu scope thì sao?** Thường 403; Bearer handler có thể nêu `insufficient_scope`.
6. **Có thể dùng Basic header cho JWT resource server không?** Không, cần challenge đúng `Bearer`.
7. **403 của POST có chắc do thiếu role?** Không; có thể do CSRF token thiếu/sai.
8. **Vì sao `fetch` đôi khi thấy 200 HTML thay vì 302?** Client đã follow redirect đến trang login và trả final response.
9. **`ExceptionTranslationFilter` làm gì?** Kết nối `AuthenticationException`/`AccessDeniedException` trong security chain với `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` phù hợp.
10. **`AuthenticationEntryPoint` khác `AccessDeniedHandler` ra sao?** Entry point khởi động authentication, handler xử lý denied access khi đã ở trạng thái phù hợp.
11. **Có thể dùng một form-login chain cho mọi API không?** Có thể cấu hình được nhưng thường sai API contract nếu API mong 401 JSON/challenge.
12. **`securityMatcher` khác `requestMatchers` ở đâu?** Chọn phạm vi cả filter chain so với chọn rule cấp quyền bên trong chain.
13. **Anonymous gọi URL không tồn tại có nhất thiết nhận 404 không?** Không; Security có thể chặn 401/redirect trước khi MVC xử lý.
14. **Đổi `@ControllerAdvice` có đảm bảo xử lý mọi lỗi từ filters không?** Không; cần cấu hình Security entry points/handlers.
15. **Tại sao cần custom response cho SPA?** Để trả status/body mà JS hiểu, không trả HTML login redirect ngoài ý muốn.
16. **401 có cần body JSON không?** Không bắt buộc; challenge header quan trọng với HTTP auth schemes.
17. **Đăng nhập sai form mặc định có phải 401 JSON?** Không; thường redirect tới `/login?error` qua failure handler.
18. **Vì sao không redirect 403 về login?** User đã authenticated nhưng thiếu quyền; login lại có thể không đổi chính sách và tạo vòng lặp.
19. **CSRF và CORS có giống nhau không?** Không; CORS giới hạn cross-origin browser access, CSRF bảo vệ request state-changing dùng browser credentials.
20. **Khi 403 do tenant resource, có nên lộ tenant ID thật trong error detail?** Không, tránh information disclosure.
21. **Khi nào 404 tốt hơn 403?** Khi policy muốn che sự tồn tại của resource ngoài quyền user, với contract nhất quán.
22. **Test Spring Security bằng MockMvc nên assert gì?** Status, challenge/Location header, body phù hợp và đôi khi state/cookie, không chỉ một status chung.
23. **Có thể dùng test `jwt()` để chứng minh JWT signature validation?** Không; nó mock Authentication và bỏ qua decoder/cryptographic validation.
24. **Tại sao không disable CSRF cho toàn app?** Web session/form login có thể bị request CSRF nếu browser tự gửi cookie.
25. **Nếu client thấy 403 thì nên refresh token mãi không?** Không; có thể là thiếu quyền thật, cần permission flow thay vì retry vô hạn.

**Ghi nhớ:** **401** thường là dấu hiệu thiếu/sai authentication và đi kèm **challenge header** khi dùng Basic/Bearer; **403** thường là authorization denied với authentication đã có (hoặc CSRF denial); **302 đến `/login`** là cách browser web form-login bắt đầu đăng nhập. Spring Security Servlet quyết định điều này qua **SecurityFilterChain**, **AuthenticationEntryPoint**, **AccessDeniedHandler** và xử lý exception phù hợp. Hãy chọn contract theo **loại ứng dụng**, test cả status/header/redirect/CSRF/role, không để API bất ngờ nhận trang login HTML, và không dùng status đơn lẻ để kết luận nguyên nhân lỗi.
