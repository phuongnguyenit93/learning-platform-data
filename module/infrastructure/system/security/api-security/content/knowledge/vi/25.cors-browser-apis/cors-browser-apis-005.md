# CORS không thay thế authentication

Một API có thể chỉ cho phép JavaScript từ `https://app.example.com` đọc response bằng cấu hình CORS, nhưng điều đó không chứng minh request đến từ một người dùng đã đăng nhập. CORS là cơ chế mà trình duyệt dùng để kiểm soát việc một trang web origin này có được đọc response từ origin khác hay không. Authentication xác minh danh tính của caller; authorization quyết định caller được làm gì trên endpoint và object. Đây là những trách nhiệm khác nhau.

Ví dụ, một website độc hại có thể gửi một form POST tới `https://api.example.com/transfer`. Nếu request là loại đơn giản theo quy tắc CORS, trình duyệt có thể gửi request tới server dù JavaScript của website đó không được đọc response. Nếu API dựa vào cookie phiên mà không có CSRF protection, thao tác vẫn có thể được thực hiện trong một số điều kiện. CORS không tự ngăn request và không thay thế kiểm tra session, token, quyền trên object hay CSRF token.

Trong API Security, CORS là một cấu hình browser-facing cần được giới hạn đúng origin, method, header và credential. Mọi request thực tế vẫn phải được xác thực và phân quyền ở server. Không được coi `Origin` hoặc việc request vượt qua preflight là bằng chứng danh tính.

Sau bài học, người đọc có thể:

- Phân biệt Same-Origin Policy, CORS, authentication, authorization và CSRF protection.
- Giải thích preflight request và các request đơn giản (simple requests).
- Hiểu vì sao CORS không ngăn mọi cross-origin request và không xác thực caller.
- Cấu hình allowlist origin, credential, method, header và cache an toàn.
- Tránh phản chiếu tùy ý `Origin` hoặc dùng wildcard sai cách.
- Kết hợp CORS với session/token authentication, object authorization và CSRF defense.
- Kiểm thử CORS bằng trình duyệt và xác minh server vẫn bảo vệ request trực tiếp.

## 1. Same-Origin Policy và CORS là gì?

Trình duyệt áp dụng **Same-Origin Policy (SOP)** để giới hạn cách một tài liệu hoặc script từ một origin tương tác với tài nguyên ở origin khác. Một origin được xác định bởi bộ ba:

- Scheme, ví dụ `https`.
- Host, ví dụ `app.example.com`.
- Port, ví dụ `443` hoặc port được chỉ định.

Do đó, `https://app.example.com`, `http://app.example.com` và `https://api.example.com` là các origin khác nhau. Khác port cũng tạo origin khác nhau. Path không phải thành phần của origin: `https://app.example.com/page-a` và `https://app.example.com/page-b` cùng origin.

**Cross-Origin Resource Sharing (CORS)** là cơ chế HTTP headers cho phép server chỉ định origin nào được trình duyệt cho phép đọc response cross-origin. Browser kiểm tra response headers và quyết định có cung cấp response cho script hay không.

Ví dụ server trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Content-Type: application/json

{"message":"Hello from API"}
```

Nếu JavaScript chạy từ `https://app.example.com` gọi API, trình duyệt có thể cho script đọc response. Nếu script chạy từ `https://evil.example`, origin không khớp allowlist thì trình duyệt không cho script đọc response.

Điểm quan trọng: CORS là quy tắc do trình duyệt thực thi ở phía client. Nó không phải cơ chế xác thực người dùng, không chứng minh caller là ứng dụng hợp lệ và không ngăn các client ngoài trình duyệt như `curl`, Postman, mobile app hoặc service-to-service gọi API.

## 2. CORS làm gì và không làm gì?

| Cơ chế | Câu hỏi được trả lời | Không chứng minh |
|---|---|---|
| CORS | Origin nào được browser cho phép đọc response? | Người dùng đã đăng nhập hoặc có quyền trên dữ liệu |
| Authentication | Caller là ai hoặc credential có hợp lệ không? | Caller được truy cập mọi object |
| Function authorization | Caller được gọi chức năng này không? | Caller có quyền trên object cụ thể |
| Object/property authorization | Caller được thao tác hoặc đọc field nào? | Browser origin có được phép đọc response theo SOP không |
| CSRF protection | Request có thực sự được khởi tạo trong ý định hợp lệ của người dùng/ứng dụng không? | Danh tính caller đã được xác thực nếu thiếu authentication |
| Rate limit | Request có vượt tần suất/quota không? | Request hợp lệ về danh tính và nghiệp vụ |

CORS giúp kiểm soát khả năng đọc response cross-origin trong browser. Nó không thay thế bất kỳ lớp bảo mật server-side nào.

### 2.1. CORS không phải authentication

Một server có thể trả `Access-Control-Allow-Origin: https://app.example.com`, nhưng bất kỳ ai có thể gửi HTTP request trực tiếp tới API và tự đặt header `Origin` nếu họ dùng client không phải browser. `Origin` không phải credential bí mật và không phải bằng chứng danh tính.

Ngay cả trong browser, origin chỉ đại diện cho nơi script được tải, không phải người dùng đang thao tác. Một máy tính dùng chung có thể mở cùng origin cho nhiều user; một website được phép có thể bị XSS chiếm quyền; một subdomain được allow có thể bị takeover. Vì vậy, server vẫn cần xác minh access token/session và quyền tương ứng.

### 2.2. CORS không phải authorization

Nếu `app.example.com` nằm trong allowlist, điều đó chỉ cho phép JavaScript từ origin này đọc response nếu các điều kiện CORS khác thỏa mãn. User A trong ứng dụng vẫn không được đọc đơn hàng của user B. API phải kiểm tra quyền trên object, tenant và property như với mọi request khác.

Không viết logic kiểu:

```java
if (request.getHeader("Origin").equals("https://app.example.com")) {
    return allCustomerData;
}
```

Origin không được dùng để cấp quyền đọc dữ liệu. Nó chỉ phục vụ quyết định CORS và có thể được ghi log như một tín hiệu phụ.

## 3. Simple request và preflight request

CORS phân biệt các request mà browser có thể gửi trực tiếp với các request cần preflight.

### 3.1. Simple request

Một số request cross-origin được xem là simple theo các điều kiện về method, header và content type. Nhóm thường gặp gồm `GET`, `HEAD`, `POST` với tập header và content type được safelist theo Fetch Standard. Ví dụ form POST dùng `application/x-www-form-urlencoded` hoặc `multipart/form-data` thường có thể được gửi mà không cần preflight.

Với simple request:

1. Browser gửi request tới server.
2. Server xử lý request theo logic thông thường.
3. Browser kiểm tra CORS response headers.
4. Nếu response không cho phép origin, JavaScript không được đọc response.

Request đã có thể tới server và tạo side effect trước khi browser chặn việc đọc response. Đây là lý do CORS không phải biện pháp chống CSRF.

### 3.2. Preflight request

Với một số request không thuộc nhóm simple, browser gửi một request `OPTIONS` trước để hỏi server có cho phép method/header dự kiến không.

Ví dụ JavaScript gửi JSON kèm header `Authorization`:

```javascript
fetch("https://api.example.com/v1/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>"
  },
  body: JSON.stringify({ productId: "P-10", quantity: 1 })
});
```

Browser có thể gửi preflight:

```http
OPTIONS /v1/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin
```

Nếu preflight thành công, browser mới tiếp tục gửi actual request. Nếu thất bại, browser không gửi actual request của luồng preflight đó. Nhưng không thể suy ra rằng mọi cross-origin request đều phải preflight; simple request vẫn có thể được gửi. Các client không phải browser cũng không cần thực hiện preflight.

### 3.3. Preflight không phải lần authentication của người dùng

Preflight là request kiểm tra quyền CORS của browser, không phải request nghiệp vụ do user đã xác thực. Browser thường không gửi credential cross-origin trong preflight. Vì vậy, server nên xử lý preflight tại CORS middleware trước lớp authentication thông thường; actual request vẫn phải đi qua authentication và authorization.

Không mở toàn bộ endpoint `OPTIONS` cho mọi mục đích chỉ vì cần CORS. Cần phân biệt preflight có `Origin` và `Access-Control-Request-Method` với một API `OPTIONS` nghiệp vụ nếu hệ thống có sử dụng.

## 4. Các CORS response headers quan trọng

| Header | Vai trò |
|---|---|
| `Access-Control-Allow-Origin` | Origin được phép đọc response; có thể là một origin cụ thể hoặc `*` trong trường hợp phù hợp |
| `Access-Control-Allow-Methods` | Method được phép cho request cross-origin |
| `Access-Control-Allow-Headers` | Request headers mà browser được phép gửi trong actual request |
| `Access-Control-Allow-Credentials` | Cho phép browser expose response của credentialed request khi giá trị là `true` |
| `Access-Control-Expose-Headers` | Header response ngoài safelist mà JavaScript được phép đọc |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight |
| `Vary: Origin` | Báo cache rằng response có thể thay đổi theo request `Origin` |

Các header này điều khiển hành vi CORS của browser. Chúng không xác thực bearer token, session cookie hoặc API key.

### 4.1. Access-Control-Allow-Origin

Nếu API chỉ phục vụ một frontend, hãy chỉ định origin đầy đủ:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Origin gồm scheme, host và port khi port không phải mặc định. Không thêm path hoặc dấu `/` cuối tùy ý. Nếu hỗ trợ nhiều origin, server cần so khớp request origin với allowlist rồi trả lại đúng origin đã được chấp nhận.

Không phản chiếu mọi giá trị `Origin` vào `Access-Control-Allow-Origin` mà không kiểm tra. Cấu hình như sau là nguy hiểm:

```java
// Không an toàn: phản chiếu Origin do caller gửi.
response.setHeader("Access-Control-Allow-Origin", request.getHeader("Origin"));
```

Attacker có thể đặt origin của website độc hại và browser sẽ nhận được response nếu các header khác cho phép.

### 4.2. Wildcard `*`

`Access-Control-Allow-Origin: *` cho phép mọi origin đọc response trong trường hợp không dùng credentialed CORS. Không dùng wildcard cho API trả dữ liệu riêng tư hoặc response cần cookie/session credential.

Khi request dùng credentials, browser không chấp nhận `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`. Server phải trả origin cụ thể đã được allowlist.

Wildcard có thể phù hợp cho tài nguyên công khai, không nhạy cảm và không yêu cầu credential. Dù vậy, API vẫn cần bảo vệ các thao tác ghi và tài nguyên không công khai theo policy server-side.

### 4.3. Access-Control-Allow-Credentials

Đối với credentialed CORS, response cần:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Giá trị hợp lệ cho header này là chuỗi `true`. Không dùng `*` thay cho giá trị boolean. Bật credentials có nghĩa browser có thể chia sẻ response của request có credential nếu các điều kiện khác đạt; nó không chứng minh credential hợp lệ và không thay thế kiểm tra session/token.

### 4.4. Allow methods và headers theo nhu cầu

Chỉ cho phép các method và request header mà frontend thực sự cần. Ví dụ không cho phép `DELETE` hoặc `X-Admin-Override` nếu ứng dụng không sử dụng. CORS allowlist không thay thế authorization: nếu `DELETE` được liệt kê, actual request vẫn phải xác thực và kiểm tra quyền xóa object.

`Access-Control-Expose-Headers` chỉ nên liệt kê header cần cho client, ví dụ `X-Request-Id` hoặc `ETag`. Không expose header chứa secret, thông tin nội bộ hoặc dữ liệu không cần thiết.

## 5. Credentialed CORS và cookie

Một browser request có thể gửi credential như cookie hoặc HTTP authentication tùy API và cấu hình client. Với Fetch API, `credentials` mặc định là `same-origin`; để gửi cookie cross-origin, ứng dụng thường phải chỉ định `credentials: "include"`.

Ví dụ:

```javascript
fetch("https://api.example.com/v1/me", {
  method: "GET",
  credentials: "include"
});
```

Server phải trả origin cụ thể và `Access-Control-Allow-Credentials: true` nếu muốn browser cho script đọc response. Nhưng cookie còn chịu chính sách `SameSite`, `Secure`, third-party cookie restrictions và cấu hình browser. CORS không tự làm cookie được gửi; cũng không bảo đảm cookie được gửi trong mọi môi trường.

Với cookie session:

- Đặt `Secure` để chỉ gửi qua HTTPS.
- Đặt `HttpOnly` để JavaScript không đọc trực tiếp cookie.
- Chọn `SameSite=Lax` hoặc `Strict` khi phù hợp; nếu cần cross-site cookie, thường phải dùng `SameSite=None; Secure` và chấp nhận các giới hạn của browser.
- Dùng CSRF token hoặc cơ chế CSRF defense phù hợp cho thao tác thay đổi trạng thái.
- Rotate session ID sau đăng nhập hoặc thay đổi mức quyền; hết hạn và thu hồi session đúng cách.

Không bật `allowCredentials` toàn cục chỉ để frontend “đỡ lỗi”. Chỉ bật cho origin và endpoint thực sự cần cookie/credential cross-origin.

## 6. CORS không thay thế CSRF protection

CSRF (Cross-Site Request Forgery) xảy ra khi browser của người dùng gửi request tới một site mà người dùng đã có phiên đăng nhập, trong khi request được khởi tạo từ một trang khác ngoài ý muốn của người dùng.

Ví dụ user đã đăng nhập `bank.example.com` bằng cookie. Một website độc hại có thể tạo form gửi POST tới endpoint chuyển tiền. Browser có thể đính kèm cookie theo chính sách cookie hiện hành. Nếu endpoint không có CSRF protection, server có thể xử lý request dù website độc hại không đọc được response.

Điều này cho thấy:

- CORS chủ yếu kiểm soát việc script đọc response cross-origin.
- CSRF protection kiểm soát request thay đổi trạng thái được gửi thay mặt người dùng.
- Authentication xác minh session/token.
- Authorization xác minh quyền thực hiện giao dịch.

Các biện pháp CSRF thường dùng với cookie-based authentication:

- Synchronizer token pattern hoặc signed double-submit cookie theo thiết kế phù hợp.
- Kiểm tra `Origin`/`Referer` như một lớp bổ sung, với xử lý rõ ràng khi header thiếu.
- `SameSite` cookie để giảm một số request cross-site.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Yêu cầu custom header/CSRF token cho request ghi nếu kiến trúc phù hợp; custom header thường khiến browser preflight nhưng lợi ích bảo mật đến từ token/validation server-side, không phải chỉ từ preflight.

Không coi `SameSite` hoặc CORS là lớp duy nhất cho thao tác nhạy cảm. Với bearer token được JavaScript gắn vào header và không tự động gửi theo cookie, mô hình CSRF khác cookie session, nhưng vẫn cần bảo vệ token khỏi XSS và thực thi authorization ở server.

## 7. Origin không phải danh tính và không nên là trust boundary duy nhất

Browser tự đặt `Origin` cho nhiều request cross-origin, nhưng client không phải browser có thể tự tạo header này. Vì vậy, server không được dùng `Origin` như credential hoặc bằng chứng user identity.

Ví dụ sai:

```java
if ("https://admin.example.com".equals(request.getHeader("Origin"))) {
    // Không được suy ra caller là admin.
    grantAdminAccess();
}
```

Đúng hơn, server xác thực access token/session, lấy principal đáng tin cậy, kiểm tra role/scope và quyền trên object. CORS chỉ quyết định browser origin nào được đọc response.

### 7.1. Origin `null`

Một số ngữ cảnh browser có thể gửi `Origin: null`, ví dụ tài liệu sandboxed hoặc một số scheme opaque. Không thêm `null` vào allowlist một cách tùy tiện. Nếu ứng dụng có nhu cầu hợp lệ, phải hiểu chính xác nguồn request và rủi ro; thường nên từ chối origin này cho API chứa dữ liệu riêng tư.

### 7.2. Subdomain và wildcard origin

Allow toàn bộ `*.example.com` có thể nguy hiểm nếu có subdomain do người dùng kiểm soát, subdomain staging yếu, hosting tĩnh cho phép upload hoặc hệ thống con dễ bị takeover. Một origin được tin cậy có thể trở thành điểm đọc dữ liệu API nếu bị chiếm quyền.

Ưu tiên allowlist origin cụ thể. Nếu cần pattern, giới hạn chặt scheme, hostname boundary và port; không dùng phép so chuỗi kiểu `endsWith("example.com")` vì `evil-example.com` có thể vượt qua. Kiểm tra bằng URL parser và so sánh hostname chính xác hoặc subdomain boundary đúng.

## 8. Cấu hình CORS an toàn cho nhiều môi trường

Production, staging và local development thường cần origin khác nhau. Không dùng cấu hình dev rộng trong production.

Ví dụ policy:

| Môi trường | Origin được phép | Credentials |
|---|---|---|
| Production | `https://app.example.com` | Chỉ bật nếu dùng cookie/session cross-origin |
| Admin production | `https://admin.example.com` | Chỉ endpoint admin cần và có authentication riêng |
| Staging | `https://staging-app.example.net` | Credential staging riêng, dữ liệu staging |
| Local development | `http://localhost:3000` | Chỉ trong profile dev, không đưa vào production |

Không cho phép `http://localhost:*` hoặc mọi subdomain trong production chỉ để developer dễ thử nghiệm. Cũng không dùng cùng cookie, token hoặc credential giữa staging và production.

### 8.1. Dynamic allowlist và Vary: Origin

Nếu server hỗ trợ nhiều origin, nó có thể kiểm tra origin request trong allowlist rồi trả lại origin cụ thể. Khi response thay đổi theo `Origin`, cần gửi:

```http
Vary: Origin
```

Điều này giúp cache phân biệt representation theo origin. Nếu thiếu `Vary: Origin`, shared cache có thể dùng response đã tạo cho một origin để phục vụ origin khác. Với response nhạy cảm hoặc credentialed, cân nhắc `Cache-Control: private, no-store` thay vì chia sẻ cache.

Không tạo `Access-Control-Allow-Origin` từ chuỗi tùy ý. Không thêm origin vào allowlist chỉ vì request gửi tới từ một subdomain của tổ chức; phải xác minh owner, mức độ tin cậy và khả năng bị takeover.

## 9. Ví dụ cấu hình Spring Boot và Spring Security

Ví dụ cấu hình origin cụ thể cho API:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
    ));
    configuration.setAllowedMethods(List.of(
            "GET", "POST", "PATCH", "DELETE", "OPTIONS"
    ));
    configuration.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
    ));
    configuration.setExposedHeaders(List.of(
            "X-Request-Id", "ETag"
    ));
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
```

Kích hoạt CORS trong Spring Security:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/public/**").permitAll()
                    .anyRequest().authenticated()
            )
            .build();
}
```

Đây là ví dụ khung. Trong ứng dụng dùng cookie/session, không tắt CSRF chỉ vì đã cấu hình CORS; hãy cấu hình CSRF token và cookie theo authentication model. Endpoint `/api/public/**` vẫn cần validation, rate limit và authorization nếu có tài nguyên không công khai. Các request actual ngoài public vẫn phải authenticated.

Spring Security cần xử lý CORS trước authentication để preflight không bị từ chối chỉ vì nó không mang session/access token. Cấu hình phải được kiểm tra với filter chain thực tế, nhất là khi có nhiều `SecurityFilterChain`, gateway hoặc custom CORS filter.

### 9.1. Tránh cấu hình rộng

Không kết hợp `allowedOrigins("*")` với `allowCredentials(true)`. Không bật `allowedOriginPatterns("*")` để né giới hạn wildcard. Không cho phép mọi method/header chỉ vì một frontend đang gặp lỗi preflight. Hãy xem request thực tế trong DevTools để xác định origin, method và header cần thiết.

## 10. Authentication vẫn phải chạy trên actual request

Với bearer token, frontend có thể gửi:

```http
Authorization: Bearer <access-token>
```

Server cần xác minh chữ ký hoặc introspection, issuer, audience, expiry và scope theo thiết kế. CORS chỉ cho phép browser gửi header `Authorization` qua preflight khi policy cho phép và đọc response nếu CORS response hợp lệ. CORS không xác minh token.

Với session cookie, server phải kiểm tra session ở mỗi request và áp dụng CSRF protection cho thao tác có side effect. Với API key, server xác minh key và giới hạn quyền theo client. Với service-to-service, dùng workload identity/mTLS hoặc token phù hợp; CORS thường không liên quan vì client không phải browser.

Sau authentication, API cần kiểm tra:

1. Caller có quyền chức năng gọi endpoint không?
2. Caller có quyền trên object được yêu cầu không?
3. Caller được đọc hoặc ghi những property nào?
4. Trạng thái object và quy tắc nghiệp vụ có cho phép thao tác không?
5. Quota/rate limit có bị vượt không?

Không dùng CORS allowlist làm thay thế bất kỳ câu hỏi nào trong số này.

## 11. Những cấu hình CORS nguy hiểm thường gặp

| Cấu hình/lỗi | Rủi ro | Cách xử lý |
|---|---|---|
| Phản chiếu mọi `Origin` | Website bất kỳ có thể đọc response nếu credential/header phù hợp | So khớp allowlist chính xác |
| Wildcard với credential | Browser không chấp nhận cấu hình credentialed CORS; dễ dẫn tới workaround sai | Trả origin cụ thể và bật credential có chọn lọc |
| Allow mọi subdomain | Subdomain yếu/takeover có thể đọc API | Chỉ allow origin cần thiết; quản lý subdomain |
| Tin `Origin` để cấp quyền | Client không phải browser có thể giả mạo header | Authentication và authorization server-side |
| Cho phép `null` tùy tiện | Origin opaque có thể truy cập response | Từ chối mặc định hoặc policy rất cụ thể |
| Allow mọi method/header | Mở rộng bề mặt browser API không cần thiết | Allowlist tối thiểu |
| Bật credentials toàn bộ API | Tăng rủi ro lộ dữ liệu qua origin được tin cậy | Tách endpoint và bật có chọn lọc |
| Thiếu `Vary: Origin` | Cache có thể dùng nhầm response theo origin | Thêm `Vary: Origin` hoặc tắt shared cache |
| Chỉ bảo vệ CORS ở gateway | Đường truy cập trực tiếp có thể không áp dụng policy | Bảo đảm policy tại edge phù hợp và server vẫn authz |
| Cho rằng preflight chặn CSRF | Simple request có thể được gửi và tạo side effect | CSRF token/SameSite/Origin validation |

## 12. Kiểm thử CORS đúng cách

Kiểm thử cần dùng browser thật hoặc browser automation vì CORS là cơ chế browser thực thi. `curl` có thể gửi header `Origin` và hiển thị response, nhưng nó không tự áp dụng quy tắc CORS như browser.

### 12.1. Ma trận kiểm thử origin

| Origin/request | Kết quả mong đợi |
|---|---|
| Origin production được allowlist | Browser đọc response nếu các điều kiện khác đạt |
| Origin không được allowlist | Browser không cho JavaScript đọc response |
| Origin gần giống nhưng khác hostname | Không được cho phép |
| Origin `null` | Bị từ chối trừ khi có policy đặc biệt được phê duyệt |
| Credentialed request từ origin hợp lệ | Origin cụ thể và `Allow-Credentials: true` |
| Credentialed request từ origin lạ | Không expose response; server vẫn kiểm tra request/CSRF |
| Request với method không được phép | Preflight thất bại; browser không gửi actual request thuộc luồng preflight |
| Request với header không được phép | Preflight thất bại |
| Simple cross-origin POST | Xác minh server vẫn có CSRF/authentication; không giả định preflight sẽ xảy ra |

### 12.2. Kiểm thử authentication và authorization độc lập

Các test quan trọng:

- Gọi API bằng `curl` không có token; server phải trả `401` dù client tự gửi `Origin` hợp lệ.
- Gửi token hết hạn hoặc sai audience; server phải từ chối.
- User A đã đăng nhập gọi ID object của user B; server phải từ chối theo object authorization.
- User có quyền đọc nhưng không có quyền cập nhật; PATCH phải bị từ chối.
- Gọi từ origin được allowlist nhưng không có session/token; không được cấp dữ liệu riêng tư.
- Gọi từ origin không được allowlist bằng credential hợp lệ; browser không đọc response, nhưng server vẫn phải thực thi authentication/authorization và CSRF policy đúng.
- Gửi simple form POST cross-site tới thao tác thay đổi trạng thái; CSRF defense phải ngăn request trái phép.
- Gửi preflight OPTIONS không có credential; CORS middleware trả đúng policy nhưng không thực hiện nghiệp vụ.
- Kiểm tra `Vary: Origin`, cache và response khi đổi origin.

### 12.3. Kiểm thử qua DevTools

Trong Browser DevTools:

1. Mở tab Network và lọc request tới API.
2. Kiểm tra request `OPTIONS` có `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` hay không.
3. Kiểm tra response preflight có allow origin/method/header phù hợp không.
4. Kiểm tra actual request có được gửi hay không.
5. Xem response headers, credentials mode và cookie policy.
6. Đọc Console để biết browser báo lỗi CORS nào; nhớ rằng JavaScript thường chỉ nhận lỗi chung, không đọc được response bị CORS chặn.

Không kết luận server không xử lý request chỉ vì JavaScript báo CORS error. Hãy kiểm tra access log và business event để biết request đã tới server và có side effect hay chưa.

## 13. Checklist cấu hình CORS và API Security

- [ ] CORS được hiểu là browser response-sharing policy, không phải authentication.
- [ ] Mọi actual request vẫn xác minh session/token/API key hoặc service identity.
- [ ] Authorization theo function, object và property được thực thi ở server.
- [ ] Cookie-based authentication có CSRF protection phù hợp.
- [ ] Origin allowlist dùng scheme/host/port chính xác; không phản chiếu tùy ý.
- [ ] Không dùng wildcard cho credentialed CORS.
- [ ] Chỉ bật credentials cho origin/endpoint thực sự cần.
- [ ] Chỉ cho phép method và request header cần thiết.
- [ ] `Access-Control-Expose-Headers` chỉ liệt kê header client cần đọc.
- [ ] Dynamic origin response có `Vary: Origin` và cache policy phù hợp.
- [ ] `Origin: null` và subdomain wildcard được xử lý có chủ đích.
- [ ] Preflight được xử lý trước authentication filter; actual request vẫn được bảo vệ.
- [ ] Không coi preflight là CSRF defense hoặc bằng chứng caller đáng tin.
- [ ] Production/staging/development có origin và credential tách biệt.
- [ ] Có test browser cho allowed/disallowed origin và test server-side cho authn/authz/CSRF.
- [ ] Có kiểm tra log/business event khi browser báo CORS error để phát hiện side effect đã xảy ra.

## Kết luận

CORS kiểm soát việc browser có cho JavaScript đọc response cross-origin hay không. Nó không xác minh danh tính người dùng, không cấp quyền trên object và không bảo đảm request không được gửi tới server. Simple request có thể được gửi mà không cần preflight; client không phải browser có thể bỏ qua CORS hoàn toàn. Hãy cấu hình origin cụ thể, giới hạn credential/method/header, xử lý preflight đúng thứ tự và tiếp tục thực thi authentication, authorization cùng CSRF protection trên server. Khi các lớp này được tách bạch, CORS trở thành một cơ chế chia sẻ tài nguyên cho browser có kiểm soát thay vì một ranh giới bảo mật bị hiểu nhầm.
