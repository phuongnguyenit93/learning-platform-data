# Không dùng Origin như identity duy nhất

Trong chương **CORS không thay authorization** của module `SECURITY_API_SECURITY`, header `Origin` chỉ cho biết origin mà trình duyệt gắn với một request trong ngữ cảnh web. Nó không chứng minh người dùng là ai, request thuộc tenant nào, client có quyền gì hoặc request có được gửi bởi một trình duyệt thật hay không. Một API dùng `Origin` như danh tính duy nhất có thể bị gọi trực tiếp bằng HTTP client tự tạo header, bị khai thác qua request không cần đọc response, hoặc bị vượt qua khi header vắng mặt hay mang giá trị `null`.

CORS (Cross-Origin Resource Sharing) là cơ chế để trình duyệt quyết định JavaScript từ origin nào được phép đọc response cross-origin. CORS không phải cơ chế xác thực người gọi và cũng không phải quy tắc phân quyền trên endpoint, object hay field dữ liệu. API vẫn phải xác thực principal, kiểm tra permission và tenant scope trên từng request. Với cookie/session, cần thêm CSRF protection vì trình duyệt có thể tự gửi credential trong một request mà trang độc hại khởi tạo.

## 1. Origin là gì và nó nói lên điều gì?

Một web origin được xác định bởi bộ ba **scheme, host và port**. Ví dụ:

| URL | Origin |
|---|---|
| `https://app.example.com/dashboard` | `https://app.example.com` |
| `https://app.example.com:443/settings` | `https://app.example.com` (port mặc định của HTTPS) |
| `http://app.example.com` | `http://app.example.com` |
| `https://api.example.com` | `https://api.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |

Path, query và fragment không thuộc origin. Hai URL khác path nhưng cùng scheme, host và port có cùng origin. Ngược lại, khác scheme, hostname hoặc port thì là cross-origin.

Origin khác với các khái niệm thường bị nhầm:

- **Site** là khái niệm dùng trong một số cơ chế trình duyệt như cookie `SameSite`; same-site không đồng nghĩa same-origin.
- **Host** chỉ là hostname, không bao gồm scheme và port.
- **Referer** có thể chứa URL nguồn và chịu ảnh hưởng của Referrer Policy; nó không thay thế Origin hoặc authentication.
- **User identity** là danh tính đã được xác minh bằng session, token, certificate hoặc workload identity.
- **Client identity** là ứng dụng hoặc workload được xác minh theo cơ chế như OAuth client authentication hoặc mTLS.

Ví dụ `https://app.example.com` và `https://admin.example.com` khác origin dù có thể cùng site. Không suy ra một origin được tin cậy chỉ vì hostname có chung hậu tố hoặc cùng domain tổ chức.

### 1.1. Trình duyệt gửi Origin trong những trường hợp nào?

Trình duyệt thường gửi `Origin` trong các request cross-origin và trong một số request cùng origin tùy method/ngữ cảnh. Header này được browser quản lý; JavaScript thông thường không được tự do đặt hoặc ghi đè `Origin` như một custom header. Tuy nhiên, điều đó chỉ giới hạn script chạy trong browser.

Các công cụ như `curl`, Postman, script server-side, bot hoặc chương trình tùy chỉnh có thể gửi bất kỳ giá trị `Origin` nào. Một request có thể tự khai báo:

```http
POST /v1/transfers HTTP/1.1
Host: api.example.com
Origin: https://trusted-app.example.com
Content-Type: application/json
Authorization: Bearer <token>
```

Server không thể kết luận request thực sự đến từ trang `trusted-app.example.com` chỉ dựa vào header này. Kẻ gọi trực tiếp có thể tự tạo header, bỏ header hoặc thay bằng origin khác.

### 1.2. Origin có thể vắng mặt hoặc là `null`

Không phải mọi request đều có một origin thông thường:

- Một số client không phải browser không gửi `Origin`.
- Một số request cùng origin hoặc ngữ cảnh đặc biệt có thể không có header theo semantics của trình duyệt.
- Tài liệu sandbox, URL `file:`, `data:` và một số opaque origin có thể được serialize thành `null`.
- Một request có thể đi qua proxy hoặc thành phần trung gian làm thay đổi header nếu cấu hình không đúng.

`Origin: null` không có nghĩa là “không có rủi ro” hoặc “người dùng ẩn danh”. Nó là giá trị hợp lệ trong một số ngữ cảnh opaque origin, nhưng thường không nên được allowlist cho API chứa dữ liệu nhạy cảm. Nếu API dùng `Origin` để kiểm tra nguồn browser cho CSRF, cần định nghĩa rõ cách xử lý absent, `null` và giá trị malformed; không âm thầm coi chúng là trusted.

## 2. CORS kiểm soát điều gì?

CORS là chính sách do browser thực thi. Server trả các response header để cho browser biết JavaScript từ origin nào được đọc response. CORS không ngăn một client không phải browser gửi request đến API.

Ví dụ server cho phép frontend tại `https://app.example.com` đọc response:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu response không có header CORS phù hợp, browser có thể chặn JavaScript đọc response. Điều đó không có nghĩa server không nhận request hoặc không thực hiện side effect.

### 2.1. Simple request có thể tới server dù CORS không cho đọc response

Một số request cross-origin không cần preflight. Browser có thể gửi request trước; sau đó mới kiểm tra response header và chặn JavaScript đọc nội dung nếu CORS không cho phép.

Ví dụ một form từ website độc hại có thể gửi request POST với content type dạng form tới endpoint nếu endpoint chấp nhận loại request đó. Browser có thể gửi cookie phù hợp cùng request. Dù script không đọc được response, server vẫn có thể xử lý giao dịch nếu không có CSRF protection.

Vì vậy, “CORS chặn response” không tương đương “CORS chặn request”. Đây là lý do không được dùng CORS thay CSRF hoặc authorization.

### 2.2. Preflight không phải authorization

Với một số request, browser gửi preflight `OPTIONS` trước để hỏi server có cho phép origin, method và request headers dự kiến hay không:

```http
OPTIONS /v1/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, PATCH
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin
```

Preflight chỉ cho browser biết request dự kiến có phù hợp với CORS policy hay không. Nó không chứng minh user đã đăng nhập, không kiểm tra quyền `PATCH` trên profile cụ thể và không thay thế việc xác thực request thực tế. Preflight thường không mang credential của request thực tế; do đó server không nên coi preflight thành một phiên đăng nhập hoặc một quyết định cấp quyền.

Request `PATCH` thực tế vẫn phải qua authentication, function authorization, object authorization, validation và CSRF control nếu dùng cookie/session.

### 2.3. CORS không bảo vệ API khỏi curl, backend hoặc mobile app

Browser thực thi CORS; HTTP client thông thường không bắt buộc tuân thủ. Một attacker có thể gọi API bằng script server-side hoặc công cụ HTTP và không cần CORS response header. Mobile app native cũng không dựa vào CORS như browser.

Nếu một endpoint chỉ hoạt động khi `Origin` nằm trong allowlist, điều đó vẫn không đủ để xác thực caller. Attacker có thể tự đặt header đúng. Endpoint phải có cơ chế authentication độc lập và authorization theo principal.

## 3. Vì sao Origin không phải identity?

Identity cần được gắn với một chủ thể có thể xác minh, thu hồi, giới hạn quyền và audit. Origin không đáp ứng các đặc tính đó.

### 3.1. Header có thể bị giả mạo ngoài browser

Browser kiểm soát `Origin` trong các request do trang web khởi tạo, nhưng server không thể biết request đến từ browser hay HTTP client chỉ bằng header. Bất kỳ client nào có thể kết nối tới API đều có thể gửi:

```bash
curl https://api.example.com/v1/admin/users \
  -H "Origin: https://trusted-app.example.com" \
  -H "Authorization: Bearer <token>"
```

Nếu server cho phép vì Origin khớp mà không xác minh token và permission, attacker chỉ cần tự khai báo origin được tin cậy.

### 3.2. Origin xác định nguồn web, không xác định người dùng

Hàng nghìn người dùng có thể truy cập cùng một frontend origin. Từ `https://app.example.com`, server không biết request do user nào thực hiện, user thuộc tenant nào, role nào hoặc membership còn hiệu lực không.

Ngay cả khi origin là frontend chính thức, một user thường vẫn không được gọi chức năng admin, đọc dữ liệu tenant khác hoặc xem field nội bộ. Authorization cần dựa trên principal đã xác thực và policy của operation/resource.

### 3.3. Origin không xác định ứng dụng đã được cài đặt hoặc client thật

Hostname có thể được truy cập từ nhiều trình duyệt, bị chiếm subdomain, trỏ tới hosting không còn được quản lý hoặc bị compromise qua XSS. Một origin nằm trong allowlist không chứng minh code đang chạy trên đó an toàn.

Đặc biệt, allowlist toàn bộ `*.example.com` có thể vô tình tin cả subdomain do người dùng tạo, preview deployment, hệ thống marketing hoặc dịch vụ cũ. Nếu một subdomain bị takeover, attacker có thể chạy JavaScript dưới origin đã được tin cậy và đọc response mà CORS cho phép.

### 3.4. Origin không chứng minh request chưa bị replay hoặc giả mạo

Origin không có nonce, chữ ký hoặc cơ chế chống replay. Một giá trị header giống nhau có thể xuất hiện trong nhiều request độc lập. Không dùng Origin làm bằng chứng cho giao dịch, ký request hoặc chống replay webhook.

## 4. Authentication và authorization phải độc lập với CORS

Mỗi endpoint cần có policy riêng. Một API có thể chỉ cho browser frontend chính thức đọc response, nhưng vẫn cần xác minh caller và quyền trên dữ liệu.

### 4.1. Authentication xác minh principal

Các cơ chế thường dùng:

- Session cookie được server quản lý và bảo vệ.
- OAuth 2.0/OIDC access token với chữ ký/introspection, issuer, audience, expiry và scope phù hợp.
- mTLS hoặc workload identity cho service-to-service.
- API key cho một số integration có kiểm soát, với owner, scope, rotation và revocation.

Không nhận `userId`, `tenantId`, role hoặc permission từ `Origin`, query parameter hay request body như bằng chứng danh tính. Các giá trị này phải được lấy từ principal/context đã xác minh hoặc kiểm tra qua policy.

### 4.2. Function authorization kiểm tra action

Sau authentication, xác minh principal có được gọi operation hay không. Ví dụ `GET /v1/profile` có thể yêu cầu `profile:read`, còn `PATCH /v1/profile` yêu cầu `profile:write`. Một origin được allowlist không làm user có thêm scope.

### 4.3. Object authorization kiểm tra resource

Một user có `orders:read` vẫn chỉ được đọc order thuộc phạm vi được phép. Truy vấn cần gắn tenant/owner hoặc policy relationship từ principal đã xác minh. Không dùng origin frontend để thay kiểm tra owner.

### 4.4. Property authorization lọc field

Response chỉ trả field principal được phép xem. CORS có thể cho JavaScript đọc toàn bộ response body nếu origin được cho phép; vì vậy nếu response chứa field nhạy cảm, lỗi authorization hoặc DTO sẽ gây rò dữ liệu xuyên origin. CORS không phải bộ lọc field.

### 4.5. Ví dụ quyết định độc lập

| Origin | Principal | Permission/resource | CORS | API decision |
|---|---|---|---|---|
| Frontend tin cậy | User A đã xác thực | Đọc order của A | Cho phép browser đọc | Cho phép nếu policy pass |
| Frontend tin cậy | User A đã xác thực | Đọc order của tenant B | Cho phép browser đọc | Từ chối object/tenant authorization |
| Frontend tin cậy | User thường | Gọi admin mutation | Cho phép browser đọc | Từ chối function authorization |
| Website lạ | User A đã xác thực | Đọc dữ liệu của A | Không cho browser đọc | API vẫn phải xác thực và quyết định; không dựa vào CORS để thay policy |
| Không có Origin | Token service hợp lệ | Gọi operation service được cấp | CORS không áp dụng | Cho phép nếu service authorization pass |
| Origin giả từ curl | Không có credential | Đọc dữ liệu riêng | CORS không được client thực thi | Từ chối authentication |

Lưu ý: “CORS không cho browser đọc” không nhất thiết có nghĩa request không tới server. API decision trong bảng vẫn dựa trên authentication/authorization và các kiểm soát khác.

## 5. CORS allowlist phải kiểm tra origin chính xác

Nếu API phục vụ browser frontend, CORS allowlist xác định origin nào được browser đọc response. Allowlist nên nhỏ, rõ và được quản lý như cấu hình bảo mật.

### 5.1. So sánh origin tuple, không tìm chuỗi con

Không dùng các cách kiểm tra như:

```java
origin.contains("example.com")
origin.endsWith("example.com")
origin.startsWith("https://app.example.com")
```

Các cách trên có thể chấp nhận `https://evil-example.com`, `https://app.example.com.attacker.test` hoặc `https://app.example.com@attacker.test`. So sánh origin đã parse và canonicalize theo tuple scheme, host, port.

Ví dụ policy:

```text
Allowed origins:
  https://app.example.com
  https://admin.example.com
  https://partner.example.net

Not allowed:
  http://app.example.com
  https://app.example.com:8443
  https://evil-example.com
  https://app.example.com.attacker.test
  null
```

Scheme và port là một phần của origin. Nếu production chỉ dùng HTTPS, không cho phép HTTP chỉ vì hostname giống nhau. Không dùng wildcard port hoặc wildcard host nếu không có nhu cầu được đánh giá.

### 5.2. Parse và canonicalize an toàn

Khi kiểm tra Origin ở server-side, cần parse giá trị theo grammar của origin thay vì dùng regex tùy tiện. Từ chối giá trị malformed, nhiều origin trong một header nếu framework không hỗ trợ rõ, userinfo, path, query hoặc fragment. Chuẩn hóa hostname/IDN theo cùng quy tắc với allowlist và so sánh port hiệu lực.

Đối với CORS, ưu tiên cấu hình origin literal trong framework thay vì tự phản chiếu header. Nếu cần allowlist động theo tenant, lấy origin từ cấu hình server đã xác minh, chuẩn hóa khi lưu, và kiểm tra exact match tại runtime. Không cho tenant tự thêm wildcard hoặc origin bất kỳ nếu chưa có quy trình xác minh quyền sở hữu.

### 5.3. Cẩn thận với wildcard subdomain

Wildcard như `https://*.example.com` có thể bao gồm subdomain preview, customer-hosted hoặc subdomain không còn kiểm soát. Nếu thực sự cần wildcard, xác định rõ quy tắc label, độ sâu, port và scheme; đánh giá toàn bộ subdomain có thể được tạo bởi người dùng hoặc pipeline ngoài quyền kiểm soát.

Ưu tiên danh sách hostname cụ thể. Xóa origin khỏi allowlist khi service ngừng hoạt động hoặc subdomain bị chuyển quyền. Quy trình DNS/domain ownership phải đi cùng lifecycle của CORS configuration.

### 5.4. Không phản chiếu Origin tùy ý

Mẫu nguy hiểm là đọc `Origin` từ request rồi trả nguyên giá trị vào `Access-Control-Allow-Origin` mà không kiểm tra:

```java
response.setHeader("Access-Control-Allow-Origin", request.getHeader("Origin"));
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Nếu phản chiếu mọi origin, website do attacker kiểm soát có thể đọc response của user đang đăng nhập bằng cookie nếu browser gửi credential và các điều kiện CORS khác được đáp ứng. Chỉ trả origin sau khi exact-match allowlist. Không dùng `null` như một origin tin cậy chung.

### 5.5. `Vary: Origin` khi response phụ thuộc Origin

Nếu server trả `Access-Control-Allow-Origin` khác nhau tùy Origin, response cần `Vary: Origin` để cache trung gian phân biệt representation theo request header. Nếu thiếu, CDN/proxy có thể cache response mang CORS header cho origin A rồi phục vụ cho origin B.

`Vary: Origin` chỉ xử lý cache variation, không xác thực origin và không sửa lỗi allowlist. Với response chứa dữ liệu cá nhân hoặc phụ thuộc principal, vẫn cần cache policy phù hợp như `Cache-Control: private` hoặc `no-store` tùy use case.

## 6. CORS với credential và cookie

Khi browser gửi credential cross-origin, policy phải chính xác hơn vì response có thể chứa dữ liệu gắn với session người dùng.

### 6.1. Không dùng wildcard với credential

Nếu response dùng:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

browser sẽ không cho JavaScript đọc response theo CORS credentialed request. Không cố lách bằng cách phản chiếu mọi Origin. Hãy chỉ trả một origin cụ thể đã được allowlist và bật credentials khi thực sự cần.

Ví dụ response cho origin được phép:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

`Access-Control-Allow-Credentials: true` có cú pháp giá trị chính xác là chữ `true`. Không dùng wildcard cho `Access-Control-Allow-Origin` khi cho phép credentials.

### 6.2. Cookie cross-site cần chính sách riêng

Nếu frontend và API thực sự cross-site, cookie thường cần `SameSite=None; Secure` để browser gửi trong ngữ cảnh cross-site, nhưng điều này làm tăng yêu cầu CSRF protection. Hãy đặt `HttpOnly`, `Secure`, `SameSite` phù hợp và domain/path hẹp nhất có thể. Không mở cookie domain ra toàn bộ parent domain nếu không cần.

SameSite là lớp giảm CSRF, không phải authorization. CORS cũng không thay thế CSRF token hoặc kiểm tra nguồn request. Browser privacy policy và third-party cookie restrictions có thể ảnh hưởng việc gửi cookie; không dựa vào hành vi đó như ranh giới bảo mật.

### 6.3. Chỉ cho phép header và method cần thiết

Giới hạn `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` theo frontend contract. Không cần cho phép mọi method/header nếu client chỉ cần `GET`, `POST`, `PATCH` và một số header cụ thể.

`Access-Control-Allow-Methods` không cấp quyền API cho user. Nó chỉ cho browser biết method nào có thể dùng trong cross-origin request. Server vẫn phải kiểm tra method, route, principal và permission.

### 6.4. Expose response header có chủ đích

Browser JavaScript chỉ đọc được một số response header mặc định. `Access-Control-Expose-Headers` mở thêm header cho script. Chỉ expose những header client cần, ví dụ `X-Request-Id` hoặc `Content-Disposition` nếu có lý do. Không expose header chứa internal topology, debug metadata hoặc credential.

## 7. Origin check có thể hỗ trợ CSRF nhưng không thay identity

Origin có thể là một tín hiệu để server kiểm tra nguồn browser đối với request thay đổi trạng thái. Tuy nhiên, đây là một lớp CSRF defense, không phải authentication hoặc authorization.

### 7.1. Khi nào nên kiểm tra Origin ở server?

Với endpoint dùng cookie/session, có thể kiểm tra Origin trên request thay đổi trạng thái (`POST`, `PUT`, `PATCH`, `DELETE`) để chỉ chấp nhận browser origin đã được xác định. Nếu Origin không có, policy có thể kiểm tra Referer theo quy tắc rõ hoặc yêu cầu CSRF token; không tự động coi thiếu Origin là trusted.

Origin check phải so sánh exact origin. Không cho phép mọi subdomain chỉ vì cùng domain. Không dùng `Referer` chứa chuỗi domain như một phép so sánh thay thế.

### 7.2. CSRF token vẫn cần thiết theo mô hình session

Với cookie được browser tự động gửi, dùng CSRF token theo framework và mô hình session, kết hợp SameSite và kiểm tra Origin/Referer như defense in depth. CSRF token phải gắn với session hoặc cơ chế xác minh phù hợp, không đặt trong cookie mà browser tự gửi theo cùng cách rồi coi đó là secret đã được chứng minh.

Đừng tắt CSRF chỉ vì API có CORS. Nếu chỉ dùng bearer token trong `Authorization` header do JavaScript chủ động đặt và token không tự động được browser đính kèm, rủi ro CSRF thường khác với cookie session; tuy nhiên vẫn phải đánh giá nơi lưu token, XSS, credential tự động khác và các endpoint chấp nhận cookie.

### 7.3. Không coi preflight là CSRF token

Preflight không phải bằng chứng request thực tế được người dùng chủ động chấp thuận. Một số request đơn giản không cần preflight; preflight cũng có thể được cache. Vì vậy, không dùng “request đã qua OPTIONS” làm điều kiện duy nhất để cho phép mutation.

### 7.4. Không dùng Origin để bảo vệ endpoint service-to-service

Service-to-service request thường không có browser origin. Nếu endpoint yêu cầu service identity, dùng mTLS, workload identity hoặc access token có audience/scope. Không bắt mọi service phải giả lập một Origin frontend để vượt qua policy.

## 8. Cấu hình CORS an toàn trong Spring

Ví dụ dưới đây dùng origin literal và chỉ cho phép những method/header cần thiết. Cần điều chỉnh theo frontend thực tế, authentication mechanism và phiên bản Spring Framework/Spring Security.

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com"
    ));
    config.setAllowedMethods(List.of("GET", "POST", "PATCH", "DELETE"));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type", "X-CSRF-TOKEN", "X-Request-Id"
    ));
    config.setExposedHeaders(List.of("X-Request-Id", "Content-Disposition"));
    config.setAllowCredentials(true);
    config.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/v1/**", config);
    source.registerCorsConfiguration("/v2/**", config);
    return source;
}
```

Tích hợp với Spring Security:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.OPTIONS, "/v1/**", "/v2/**").permitAll()
            .requestMatchers("/v1/**", "/v2/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Ví dụ chỉ minh họa cấu trúc. CORS processing cần chạy trước authentication để preflight không bị từ chối chỉ vì không mang credential; `OPTIONS permitAll` không được hiểu là cho phép mutation. Request thực tế vẫn phải authenticated và authorized. Nếu dùng cookie/session, giữ CSRF protection và cấu hình token; không tắt CSRF chỉ vì đã bật CORS. Nếu có route public-by-design, khai báo riêng theo operation thay vì mở rộng matcher cho mọi route.

Không cấu hình `allowedOriginPatterns("*")` cùng `allowCredentials(true)` để tiện phát triển. Nếu local development cần origin riêng, thêm đúng origin development trong profile phù hợp và bảo đảm profile đó không thể vô tình được bật ở production.

### 8.1. Origin allowlist động theo tenant

Một số sản phẩm cho phép tenant đăng ký custom frontend domain. Khi đó, chỉ lấy domain từ bảng cấu hình đã được xác minh quyền sở hữu và gắn với tenant. Cần:

- Xác minh tenant có quyền kiểm soát domain trước khi kích hoạt.
- Chuẩn hóa scheme, hostname và port khi lưu.
- Exact-match origin khi xử lý request.
- Thu hồi ngay khi domain hết hiệu lực hoặc ownership thay đổi.
- Không cho tenant dùng `null`, wildcard toàn cục hoặc origin của tenant khác.
- Cache cấu hình có TTL/invalidating rõ để thay đổi allowlist có hiệu lực kịp thời.

Origin động vẫn chỉ quyết định browser nào được đọc response. Nó không cấp quyền truy cập dữ liệu tenant; principal và tenant authorization vẫn phải được kiểm tra độc lập.

## 9. Những lỗi cấu hình CORS thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng Origin làm authentication | Client giả header có thể vượt qua | Xác thực bằng token/session/mTLS |
| Chỉ kiểm tra CORS, bỏ authorization | User đã đăng nhập có thể gọi object/action trái quyền | Function, object và property authorization |
| Nghĩ CORS chặn request | Simple request vẫn có thể tới server và tạo side effect | CSRF protection và server-side authorization |
| Phản chiếu mọi Origin | Website attacker có thể đọc response credentialed | Exact allowlist trước khi trả ACAO |
| `endsWith("example.com")` | Chấp nhận hostname giả có hậu tố tương tự | Parse và so sánh origin tuple |
| Cho phép `Origin: null` | Tin opaque origin không cần thiết | Từ chối `null` trừ use case đã đánh giá |
| Wildcard cùng credentials | Browser từ chối response; dev có thể phản chiếu mọi origin để workaround | Origin cụ thể và credential policy rõ |
| Cho phép mọi method/header | Mở rộng bề mặt browser API ngoài nhu cầu | Allowlist method/header tối thiểu |
| Thiếu `Vary: Origin` | Cache có thể phục vụ CORS header sai origin | Thêm `Vary: Origin` khi response thay đổi theo Origin |
| Cho phép mọi subdomain | Subdomain takeover có thể mở đường đọc response | Allowlist hostname cụ thể, quản lý ownership |
| Dùng preflight làm quyền | Request thực tế không được authorize đúng | Kiểm tra request thực tế và CSRF |
| Tắt CSRF vì đã bật CORS | Cookie session vẫn có thể bị gửi tự động | Giữ CSRF token/SameSite/Origin checks |
| Dựa vào Origin cho service API | Service client không có browser Origin | Workload identity, mTLS hoặc OAuth token |

## 10. Kiểm thử CORS, Origin và authorization

Kiểm thử phải phân biệt ba lớp: browser CORS behavior, server authentication/authorization và CSRF behavior. Một test chỉ kiểm tra `Access-Control-Allow-Origin` không chứng minh endpoint an toàn.

### 10.1. Ma trận Origin

| Request Origin | CORS response mong đợi | Server-side trust/authorization |
|---|---|---|
| Origin chính xác trong allowlist | Trả ACAO cụ thể | Vẫn xác thực và kiểm tra permission/resource |
| Origin không nằm trong allowlist | Không trả ACAO phù hợp | Request vẫn có thể tới server; policy authz không đổi |
| Origin giả từ curl | Không dựa vào browser CORS | Token/session và authorization quyết định |
| `Origin: null` | Từ chối trừ ngoại lệ được duyệt | Không coi `null` là identity |
| Không có Origin | Không thêm ACAO tùy tiện | Service/client vẫn được xác thực bình thường |
| Origin sai scheme/port | Không cho phép | Không suy ra trusted từ hostname giống nhau |
| Subdomain không được đăng ký | Không cho phép | Không có quyền chỉ vì cùng parent domain |
| Header malformed/nhiều giá trị | Từ chối hoặc xử lý theo parser/framework đã định nghĩa | Không fallback thành trusted |

### 10.2. Kiểm thử browser

Từ browser thật, kiểm tra:

- Origin được allowlist có thể đọc response cần thiết.
- Origin không được allowlist không đọc được response.
- Credentialed request chỉ hoạt động với origin cụ thể và cấu hình cookie phù hợp.
- Preflight trả đúng method/header và không lộ dữ liệu.
- Simple request không tạo side effect trái phép khi CSRF token thiếu/sai.
- CORS header không bị cache hoặc gateway làm sai.

Không chỉ dùng unit test của CORS configuration. Browser integration test giúp xác nhận behavior mà browser thực sự thực thi.

### 10.3. Kiểm thử non-browser client

Dùng `curl` hoặc HTTP client để gửi Origin giả, Origin thiếu và Origin `null`. Xác minh việc thay đổi Origin không làm thay đổi authentication hoặc permission. Request không credential phải bị từ chối dù tự khai báo origin tin cậy.

Đây là test quan trọng để chứng minh server không dùng Origin như identity. Cũng kiểm tra API không trả dữ liệu nhạy cảm chỉ vì request có `Origin` được allowlist.

### 10.4. Kiểm thử CSRF cho cookie/session

Tạo trang test ở origin khác và thử gửi request thay đổi trạng thái bằng cookie session của browser test. Xác minh CSRF token/Origin policy chặn request. Bao gồm form/simple content type, request có preflight và trường hợp Origin absent/null theo policy.

Test phải xác minh database state và downstream side effect không thay đổi khi CSRF bị từ chối. Không chỉ kiểm tra browser không đọc được response.

### 10.5. Kiểm thử authorization độc lập

Với Origin hợp lệ, thử:

- Anonymous gọi endpoint cần đăng nhập.
- User thường gọi admin action.
- User A đọc object của tenant B.
- User không có permission đọc field nhạy cảm.
- Token sai audience/expired/đã revoke.

Mọi trường hợp phải bị từ chối theo policy dù CORS cho phép origin. Với Origin không hợp lệ nhưng token hợp lệ, server vẫn không được cấp quyền vượt quá principal; CORS chỉ quyết định browser có thể đọc response.

### 10.6. Ma trận kiểm thử tổng hợp

| Lớp | Trường hợp | Kết quả cần xác minh |
|---|---|---|
| CORS | Allowed origin | ACAO đúng origin, `Vary: Origin` nếu động |
| CORS | Disallowed origin | Không có ACAO cho origin đó |
| CORS | Credentials | Không wildcard; cookie policy đúng |
| CORS | Preflight | Method/header allowlist chính xác |
| Authentication | Không token | Từ chối dù Origin trusted |
| Authentication | Token sai audience/expiry | Từ chối dù Origin trusted |
| Authorization | Sai role/scope | Từ chối dù Origin trusted |
| Object/tenant | Resource ngoài phạm vi | Từ chối, không lộ dữ liệu |
| Property | Field nhạy cảm | Không xuất hiện trong response |
| CSRF | Cookie request từ site khác | Từ chối và không có side effect |
| Non-browser | Curl giả Origin | Không thể giả danh user/client |
| Cache | Nhiều Origin | Không dùng nhầm CORS response của origin khác |

## 11. Logging và vận hành

Có thể ghi nhận Origin để điều tra CORS/CSRF, nhưng không dùng nó làm principal hoặc khóa phân quyền. Log nên bao gồm:

- Origin sau khi parse/canonicalize (hoặc trạng thái absent/null/malformed).
- CORS decision: allowed/denied và policy version.
- Authentication result và principal ID nội bộ theo chính sách log.
- Authorization decision, operation và resource scope.
- CSRF decision nếu có.
- Correlation ID và gateway/service instance.

Không ghi access token, cookie, CSRF secret hoặc toàn bộ request body. Origin do client gửi cũng là input không tin cậy; giới hạn độ dài và sanitize trước khi đưa vào log để tránh log injection.

Theo dõi:

- Tỷ lệ CORS deny theo origin và endpoint.
- Origin mới hoặc subdomain bất thường xuất hiện.
- Request mutation bằng cookie bị CSRF reject.
- Tỷ lệ request không có Origin trên browser-only route nếu contract yêu cầu Origin.
- Token/authz failure theo operation, không chỉ theo origin.
- CORS allowlist thay đổi và ai phê duyệt.

Không tự động thêm Origin lạ vào allowlist chỉ vì traffic tăng hoặc khách hàng báo lỗi. Xác minh domain ownership, consumer, môi trường và yêu cầu nghiệp vụ trước khi thay đổi.

## 12. Checklist review trước khi phát hành

- [ ] `Origin` được xem là metadata của browser request, không phải user/client identity.
- [ ] Mọi endpoint có authentication độc lập với CORS.
- [ ] Function, object, tenant và property authorization được kiểm tra server-side.
- [ ] Không cấp quyền dựa trên `Origin`, `Referer` hoặc `Sec-Fetch-Site` đơn lẻ.
- [ ] CORS allowlist dùng origin cụ thể, exact-match scheme/host/port.
- [ ] Không dùng substring/suffix regex hoặc phản chiếu Origin tùy ý.
- [ ] `Origin: null`, absent và malformed có policy rõ; không mặc định trusted.
- [ ] Wildcard subdomain chỉ dùng khi có threat assessment và quản lý ownership.
- [ ] Credentialed CORS không dùng `Access-Control-Allow-Origin: *`.
- [ ] Method, request header và exposed response header được giới hạn.
- [ ] Response phụ thuộc Origin có `Vary: Origin`; cache dữ liệu riêng được kiểm soát.
- [ ] Preflight được xử lý trước authentication khi cần, nhưng request thực tế vẫn authn/authz.
- [ ] Cookie/session có CSRF protection; CORS không được dùng để thay CSRF.
- [ ] Service-to-service dùng workload identity, mTLS hoặc token có audience/scope.
- [ ] Có browser test và non-browser test giả mạo Origin.
- [ ] Test xác minh request bị từ chối không tạo side effect.
- [ ] Log Origin có giới hạn/redaction và không coi nó là principal.

## Kết luận

`Origin` cho biết nguồn web mà browser gắn với request, nhưng không xác minh người dùng, ứng dụng hay quyền truy cập. CORS chỉ điều khiển browser có được đọc response cross-origin; request vẫn có thể tới server và client ngoài browser không bị CORS ràng buộc. Hãy dùng Origin allowlist chính xác để cấu hình browser access, authentication để xác minh principal, authorization để kiểm soát action/object/field, và CSRF protection cho credential tự động như cookie. Tách các trách nhiệm này giúp tránh biến một header có thể giả mạo thành ranh giới bảo mật của API.
