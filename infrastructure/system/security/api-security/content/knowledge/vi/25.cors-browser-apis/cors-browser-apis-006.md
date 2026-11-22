# Không trả dữ liệu nhạy cảm cho origin tùy ý

## 1. Vì sao CORS là ranh giới bảo vệ dữ liệu trên trình duyệt?

Một API có thể được gọi từ nhiều website và ứng dụng khác nhau. Khi JavaScript ở `https://site-a.example` gọi API tại `https://api.example`, trình duyệt xem đây là request cross-origin vì scheme, host hoặc port khác nhau. Nếu API trả dữ liệu nhạy cảm và cho phép mọi origin đọc response, một website không đáng tin có thể dùng trình duyệt của nạn nhân để đọc dữ liệu mà nạn nhân đang có quyền truy cập.

Cross-Origin Resource Sharing (CORS) là cơ chế để server khai báo những origin nào được trình duyệt cho phép đọc response. CORS mở rộng quy tắc Same-Origin Policy (SOP) của trình duyệt. Đây là cơ chế kiểm soát việc chia sẻ response cho JavaScript trong browser, không phải hệ thống xác thực người dùng hay phân quyền nghiệp vụ.

Ví dụ, nạn nhân đang đăng nhập vào `https://bank.example`. Họ mở một website không đáng tin. Website đó chạy JavaScript gọi `https://bank.example/api/profile` với cookie phiên của nạn nhân. Nếu API phản hồi `Access-Control-Allow-Origin` cho website độc hại và cho phép credential, JavaScript có thể đọc dữ liệu tài khoản.

Vì vậy, origin được phép đọc response phải được chọn theo trust relationship thực tế. Không trả dữ liệu nhạy cảm cho origin tùy ý chỉ vì request có cookie hợp lệ, đi qua HTTPS hoặc đến từ một website có tên miền gần giống tên miền của tổ chức.

## 2. Origin là gì?

Origin được xác định bởi bộ ba:

- Scheme, ví dụ `https`.
- Host, ví dụ `app.example.com`.
- Port, ví dụ `443` (port mặc định thường được chuẩn hóa khi trình duyệt serialize origin).

Các URL sau là những origin khác nhau:

| URL | Origin | Lý do |
|---|---|---|
| `https://app.example.com/home` | `https://app.example.com` | Origin chuẩn. |
| `http://app.example.com` | `http://app.example.com` | Scheme khác HTTPS. |
| `https://admin.example.com` | `https://admin.example.com` | Host khác. |
| `https://app.example.com:8443` | `https://app.example.com:8443` | Port khác. |
| `https://app.example.com/settings` | `https://app.example.com` | Path không thuộc origin. |

Origin không bao gồm path, query hoặc fragment. Hai website cùng domain gốc nhưng khác subdomain vẫn là cross-origin. Khái niệm *same-site* dùng trong cookie `SameSite` khác với *same-origin*; không được dùng hai khái niệm thay thế nhau.

Header `Origin` do trình duyệt gửi để biểu thị origin khởi tạo request trong các trường hợp phù hợp. Giá trị `null` có thể xuất hiện từ một số ngữ cảnh opaque origin như sandboxed document hoặc một số scheme đặc biệt. Không nên coi `null` là origin nội bộ đáng tin cậy.

## 3. Browser Same-Origin Policy và CORS hoạt động ra sao?

SOP hạn chế cách một document/script đọc tài nguyên từ origin khác. CORS cho phép server nới giới hạn đó có kiểm soát bằng các response header. Trình duyệt kiểm tra header và quyết định JavaScript có được đọc response hay không.

Điểm quan trọng: trong một số trường hợp, trình duyệt vẫn gửi request cross-origin nhưng không cho JavaScript đọc response nếu CORS không cho phép. Các request đơn giản (simple requests) có thể được gửi mà không cần preflight. Do đó, CORS không phải cơ chế chống CSRF và không bảo đảm request không tạo side effect.

### Simple request

Một số request đáp ứng điều kiện CORS-safelisted method/header/content type có thể được gửi trực tiếp. Ví dụ form POST truyền thống hoặc một số GET có thể được gửi dù JavaScript ở origin khác không được đọc response.

Nếu server thực hiện thao tác thay đổi dữ liệu chỉ dựa vào cookie phiên, website độc hại có thể thử gửi request cross-site. Trình duyệt có thể chặn việc đọc response nhưng request vẫn có thể đến server. Vì vậy API dùng cookie cần CSRF protection riêng.

### Preflight request

Với request không đơn giản, trình duyệt thường gửi một request `OPTIONS` trước để hỏi server có cho phép origin, method và request header hay không.

Ví dụ browser muốn gửi `PATCH` kèm `Authorization` và `Content-Type: application/json`:

```http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, PATCH
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin
```

Sau khi preflight được chấp nhận, trình duyệt mới gửi actual request. Preflight là bước kiểm tra quyền thực hiện kiểu request cross-origin trong browser; nó không thay thế authentication hoặc authorization trên actual request. Server phải xác thực và phân quyền actual request như bình thường.

## 4. Các CORS response header quan trọng

| Header | Ý nghĩa | Lưu ý bảo mật |
|---|---|---|
| `Access-Control-Allow-Origin` | Origin được phép đọc response, hoặc `*` trong trường hợp phù hợp. | Không phản chiếu origin bất kỳ; không dùng `*` cho response credentialed. |
| `Access-Control-Allow-Credentials` | Cho phép browser chia sẻ response của request ở credentials mode `include` khi giá trị là `true`. | Giá trị hợp lệ là chuỗi `true`; không có `*` thay thế. |
| `Access-Control-Allow-Methods` | Các method được phép cho cross-origin request. | Chỉ khai báo method cần thiết. |
| `Access-Control-Allow-Headers` | Các request header được phép. | Không mở rộng tùy tiện; nêu rõ `Authorization`, `Content-Type` hoặc header riêng thật sự cần. |
| `Access-Control-Expose-Headers` | Header response ngoài safelist mà JavaScript được đọc. | Chỉ expose header cần thiết, không lộ metadata nội bộ. |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight. | Giá trị dài làm thay đổi policy có độ trễ hiệu lực ở client. |
| `Vary: Origin` | Báo cache rằng response có thể thay đổi theo Origin. | Cần khi response header CORS được tạo động theo request origin. |

`Access-Control-Allow-Origin` phải chứa một origin hợp lệ cụ thể hoặc `*`; không phải danh sách phân tách bằng dấu phẩy. Nếu cho phép nhiều origin, server phải kiểm tra origin request với allowlist rồi trả lại đúng origin đã được chấp thuận cho request đó.

## 5. Chỉ cho phép origin đã được xác định và tin cậy

Với API trả dữ liệu nhạy cảm, hãy duy trì allowlist origin rõ ràng theo môi trường và mục đích. Ví dụ:

```text
Production:
  https://app.example.com
  https://admin.example.com

Staging:
  https://staging-app.example.com
```

Mỗi origin cần có owner và lý do được phép đọc response. Không đưa domain thử nghiệm, preview deployment hoặc domain do người dùng tự tạo vào production allowlist nếu chưa có quy trình kiểm soát quyền sở hữu và vòng đời.

### So khớp origin chính xác

Origin allowlist cần so khớp theo scheme, hostname và port đã chuẩn hóa. Tránh các kiểm tra chuỗi đơn giản như:

```java
// Không an toàn: attacker có thể dùng evil-example.com.
if (origin.endsWith("example.com")) {
    allow();
}
```

Nếu thực sự cần cho phép một nhóm subdomain, phải parse origin và kiểm tra ranh giới label, đồng thời xác định rõ scheme và port. Ví dụ `app.example.com.attacker.test` không phải subdomain của `example.com`; `evil-example.com` cũng không phải `example.com`.

Không chấp nhận wildcard kiểu `*.example.com` nếu mọi subdomain không có cùng mức độ tin cậy. Một subdomain cũ bị bỏ quên, CNAME trỏ ra dịch vụ bên ngoài hoặc subdomain takeover có thể biến allowlist rộng thành đường đọc dữ liệu.

### Không phản chiếu Origin tùy ý

Mẫu nguy hiểm là lấy nguyên header `Origin` rồi gán vào `Access-Control-Allow-Origin` mà không kiểm tra:

```http
Origin: https://attacker.example

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://attacker.example
Access-Control-Allow-Credentials: true
```

Nếu response chứa dữ liệu nhạy cảm và browser gửi credential của nạn nhân, website attacker có thể đọc response. Đây là lỗi CORS misconfiguration thường gặp.

Không dùng logic “nếu Origin có mặt thì echo lại”. Nếu origin không nằm trong allowlist, không trả `Access-Control-Allow-Origin` cho nó. Với endpoint nhạy cảm, có thể từ chối request browser theo policy riêng, nhưng đừng nhầm việc không có CORS header với authorization: server vẫn cần kiểm tra quyền và chống CSRF.

### Cẩn thận với `Origin: null`

Không thêm `null` vào allowlist chỉ để làm một iframe, file hoặc môi trường local hoạt động. Nhiều ngữ cảnh không liên quan có thể có opaque origin serialize thành `null`; cho phép nó có thể cấp quyền đọc response cho những document không mong muốn. Hãy dùng origin HTTPS cụ thể cho môi trường ứng dụng và cấu hình development riêng.

## 6. Wildcard và credentialed request

Với response credentialed, server không được dùng `Access-Control-Allow-Origin: *`. Browser sẽ không chấp nhận wildcard này khi request ở credentials mode `include`. Server phải trả đúng origin đã được xác minh trong allowlist và:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Trong JavaScript, request dùng cookie cross-site có thể được gửi với `credentials: "include"`:

```javascript
const response = await fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include",
  headers: {
    "Accept": "application/json"
  }
});

const profile = await response.json();
```

Chỉ bật credentialed CORS cho origin thực sự cần dùng cookie hoặc browser-managed credentials. Nếu API dùng bearer token được JavaScript chủ động đặt trong `Authorization` header và không dựa vào cookie/browser credentials, thường có thể để `allowCredentials` là false nhưng vẫn cho phép header `Authorization` qua `Access-Control-Allow-Headers`. Phân biệt CORS credentials mode với việc request có một header mang tên Authorization.

Nếu dùng cookie cross-site, cookie thường cần `SameSite=None; Secure` để browser gửi trong bối cảnh cross-site, nhưng chính sách cookie của trình duyệt và third-party-cookie restrictions vẫn có thể ảnh hưởng. Không xem CORS header là cách bật/tắt cookie; cần cấu hình cookie và CSRF riêng.

## 7. CORS không phải CSRF protection

Cross-Site Request Forgery (CSRF) lợi dụng việc browser tự gửi credential (thường là cookie) đến một website mà user đã đăng nhập. CORS chủ yếu quyết định JavaScript ở origin khác có đọc được response hay không. Hai cơ chế giải quyết hai vấn đề khác nhau.

Ví dụ, website độc hại có thể gửi form POST đơn giản đến endpoint chuyển tiền. Nếu browser đính kèm cookie phiên và server không kiểm tra CSRF, giao dịch có thể được thực hiện dù JavaScript không đọc được response.

Với API dùng cookie/session:

- Dùng CSRF token phù hợp framework cho thao tác thay đổi trạng thái.
- Cấu hình `SameSite` cho cookie theo use case; `Strict`/`Lax` khi có thể, `None; Secure` chỉ khi thật sự cần cross-site.
- Kiểm tra `Origin` hoặc `Referer` ở server cho state-changing request theo policy; xử lý trường hợp header thiếu một cách rõ ràng.
- Không thực hiện thay đổi dữ liệu qua GET/HEAD.
- Dùng content type và custom header theo contract, nhưng không coi preflight là biện pháp CSRF duy nhất.
- Vẫn xác thực và phân quyền theo principal, object và tenant.

Với bearer token không tự động được browser gửi như cookie, mô hình CSRF có thể khác; tuy vậy cần bảo vệ token khỏi XSS, không lưu token dài hạn ở nơi dễ bị đọc và vẫn áp dụng CORS allowlist để giới hạn website được đọc response.

## 8. CORS không thay thế authentication hoặc authorization

Non-browser client như `curl`, ứng dụng server-to-server hoặc script riêng có thể gửi request với header `Origin` bất kỳ hoặc không gửi Origin. Những client này không bị trình duyệt thực thi CORS. Vì vậy, CORS không thể ngăn chúng truy cập API.

Mỗi endpoint vẫn phải:

- Xác thực access token, session, API key hoặc workload identity theo hợp đồng.
- Kiểm tra permission chức năng, object ownership, tenant và field được phép.
- Validate request và giới hạn tài nguyên.
- Bảo vệ thao tác thay đổi trạng thái bằng CSRF nếu credential được browser tự động gửi.
- Trả dữ liệu tối thiểu cần thiết; không dùng CORS để che giấu dữ liệu mà endpoint vốn không nên trả.

Nếu một API chỉ dành cho backend-to-backend, có thể không cần bật CORS. Việc endpoint không có CORS không làm endpoint an toàn trước caller ngoài browser; cần network control, authentication và authorization.

## 9. Cache và `Vary: Origin`

Nếu server chọn `Access-Control-Allow-Origin` theo request Origin, response có thể khác nhau giữa các origin. Cache trung gian phải biết rằng Origin là một chiều phân biệt representation.

Ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu thiếu `Vary: Origin`, shared cache có thể lưu response được tạo cho origin được phép rồi phục vụ response đó cho request từ origin khác. Hành vi chính xác phụ thuộc cache key và cấu hình proxy/CDN; đừng giả định mọi cache tự phân biệt Origin.

Với dữ liệu cá nhân hoặc dữ liệu nhạy cảm, cân nhắc:

```http
Cache-Control: private, no-store
```

Không để CDN/shared cache lưu response có cookie hoặc dữ liệu theo user nếu chưa thiết kế cache key, authorization và invalidation phù hợp. CORS không ngăn cache lưu dữ liệu.

## 10. Cấu hình CORS trong Spring Security

Ví dụ cấu hình Spring theo allowlist origin cụ thể:

```java
@Configuration
public class CorsConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        config.setAllowedMethods(List.of("GET", "POST", "PATCH", "DELETE"));
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-CSRF-TOKEN",
            "X-Request-ID"
        ));
        config.setExposedHeaders(List.of("X-Request-ID"));
        config.setAllowCredentials(true);
        config.setMaxAge(Duration.ofMinutes(10));

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
```

Kích hoạt CORS integration trong Spring Security filter chain:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .cors(Customizer.withDefaults())
        // Giữ cấu hình CSRF phù hợp với loại credential của ứng dụng.
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .build();
}
```

Ví dụ này dùng `allowCredentials(true)` vì giả định browser cần gửi cookie/session. Nếu API chỉ dùng bearer token trong Authorization header và không dùng browser-managed credentials, cân nhắc `false`. Không đặt `allowedOrigins("*")` cùng `allowCredentials(true)`. Cũng không dùng `allowedOriginPatterns("*")` để né giới hạn wildcard; pattern rộng vẫn có thể phản chiếu origin không đáng tin.

CORS phải được xử lý đúng thứ tự để preflight `OPTIONS` không bị authentication filter từ chối trước khi CORS handler xử lý. Cấu hình cụ thể tùy phiên bản Spring Security và cách triển khai gateway/proxy; tránh bật CORS ở nhiều tầng với policy mâu thuẫn. Chọn một điểm quản lý rõ ràng và kiểm thử response cuối cùng mà browser thực sự nhận.

## 11. Thiết kế allowlist theo môi trường và tenant

Origin được phép có thể khác nhau giữa local development, staging và production. Không dùng danh sách dev chung cho production.

- Production chỉ chứa origin HTTPS đã được owner xác nhận.
- Localhost origin chỉ dùng trong cấu hình development riêng, không đưa vào production mặc định.
- Preview deployment cần cơ chế đăng ký, thời hạn và xác minh owner; không tự động tin mọi preview subdomain.
- Nếu mỗi tenant có custom domain, xác minh quyền sở hữu domain trước khi thêm origin và thu hồi khi domain không còn gắn với tenant.
- Không cho tenant tự đăng ký origin rồi lập tức đọc dữ liệu của tenant khác; origin allowlist và tenant authorization là hai policy riêng.
- Rà soát domain hết hạn, DNS/CNAME, subdomain không còn được quản lý và nguy cơ subdomain takeover.

Nếu allowlist được lưu trong database, việc sửa allowlist là hành động bảo mật: cần authorization admin, audit, approval phù hợp, validation origin và quy trình revoke. Không lấy danh sách origin từ request body của chính request đang được xử lý.

## 12. Các lỗi CORS thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
|---|---|---|
| Echo mọi giá trị `Origin` | Website attacker có thể đọc response, nhất là khi có credential. | So khớp exact allowlist trước khi trả ACAO. |
| `Access-Control-Allow-Origin: *` trên dữ liệu nhạy cảm | Mọi origin có thể đọc response không credentialed; không phù hợp dữ liệu riêng tư. | Chỉ cho phép origin cần thiết; không dùng wildcard cho dữ liệu cá nhân. |
| Wildcard cùng `Allow-Credentials: true` | Browser từ chối CORS response; đội vận hành có thể tìm cách echo origin và tạo lỗ hổng. | Trả exact origin đã xác minh. |
| Cho phép `Origin: null` | Nhiều opaque origin không liên quan có thể được chấp nhận. | Từ chối `null`, dùng origin cụ thể. |
| `endsWith("example.com")` | Có thể chấp nhận `evil-example.com`. | Parse origin và kiểm tra exact host/label boundary. |
| Cho phép mọi subdomain | Subdomain takeover hoặc host không cùng mức tin cậy có thể đọc dữ liệu. | Allowlist origin cụ thể hoặc quản lý subdomain chặt chẽ. |
| CORS được coi là authorization | Non-browser client bỏ qua CORS; object/tenant không được kiểm tra. | Authentication và authorization tại API/service. |
| CORS được coi là CSRF protection | Simple request vẫn có thể được gửi và tạo side effect. | CSRF token, SameSite, Origin/Referer checks và method semantics. |
| Dynamic ACAO thiếu `Vary: Origin` | Cache có thể phục vụ response với CORS header sai origin. | Thêm `Vary: Origin`; cấu hình cache an toàn. |
| Cho phép mọi method/header | Mở rộng khả năng browser gọi API ngoài nhu cầu. | Chỉ khai báo method/header cần thiết. |
| Expose mọi response header | JavaScript đọc được metadata hoặc header không cần thiết. | Expose allowlist header tối thiểu. |
| Preflight bị chặn bởi auth filter | Browser không gửi actual request dù caller hợp lệ. | Xử lý CORS/preflight đúng thứ tự; actual request vẫn phải xác thực. |

## 13. Kiểm thử CORS và dữ liệu nhạy cảm

Kiểm thử cần xác minh header response và hành vi thực tế của browser. Chỉ gọi API bằng `curl` không kiểm tra được browser enforcement; nên có integration test bằng browser automation cho các luồng quan trọng.

| Ca kiểm thử | Request/điều kiện | Kết quả mong đợi |
|---|---|---|
| Origin được phép | Request từ `https://app.example.com`. | Trả exact `Access-Control-Allow-Origin` theo policy. |
| Origin không được phép | Request từ `https://attacker.example`. | Không trả ACAO cho origin đó; không cho JavaScript đọc response. |
| Origin giả gần giống | `https://app.example.com.attacker.test` hoặc `https://evil-example.com`. | Không khớp allowlist. |
| Scheme/port khác | HTTP thay vì HTTPS hoặc port lạ. | Bị từ chối nếu không nằm trong allowlist. |
| Origin null | Gửi từ sandboxed/opaque-origin context. | Không được cho phép trừ khi có use case đặc biệt đã đánh giá. |
| Credentialed request | Origin được phép gửi cookie với credentials include. | Exact ACAO và `Access-Control-Allow-Credentials: true`; cookie policy vẫn được áp dụng. |
| Wildcard credential | Thử ACAO `*` cùng credentials. | Cấu hình bị test phát hiện; browser không chấp nhận response credentialed. |
| Preflight | OPTIONS với method/header được phép. | Trả method/header đúng policy và max-age hợp lý. |
| Method/header ngoài allowlist | Request yêu cầu `PUT` hoặc header lạ. | Preflight không được chấp thuận. |
| CSRF | Website khác gửi form/simple request đến endpoint thay đổi trạng thái. | CSRF defense từ chối; không tạo side effect. |
| Cache variation | Hai origin khác nhau gọi qua CDN/shared cache. | Response không rò CORS header hoặc dữ liệu giữa origin; Vary/cache policy đúng. |
| Non-browser caller | Gọi API bằng client tự đặt hoặc bỏ Origin. | Authentication/authorization vẫn quyết định quyền truy cập. |
| Tenant isolation | Origin hợp lệ nhưng user yêu cầu object/tenant ngoài quyền. | Bị từ chối bởi authorization; CORS không cấp quyền dữ liệu. |
| Error response | API trả 401/403/500 cho origin được phép. | Header CORS nhất quán nếu frontend cần đọc lỗi; không lộ stack trace/dữ liệu nhạy cảm. |

Kiểm tra response body, cookie, header exposed, cache behavior và side effect. Một origin không đọc được response vẫn có thể đã kích hoạt hành động nếu CSRF protection thiếu.

## 14. Giám sát và xử lý sự cố

Có thể ghi nhận origin, route, method, quyết định allow/deny, preflight result, credential mode theo mức cần thiết, request ID và response status. Không ghi cookie, access token, CSRF token hoặc dữ liệu nhạy cảm trong log.

Theo dõi:

- Request từ origin không nằm trong allowlist và tần suất tăng đột biến.
- Origin mới được thêm, wildcard/pattern được mở rộng hoặc `null` được cho phép.
- Thay đổi CORS policy trên gateway, application, CDN hoặc reverse proxy.
- Tỷ lệ preflight fail, actual request fail và lỗi credentials.
- Domain/subdomain trong allowlist hết hạn, DNS/CNAME thay đổi hoặc có nguy cơ takeover.
- Response nhạy cảm bị cache công khai hoặc thiếu `Vary: Origin`.
- CSRF failure và các request state-changing từ cross-site context.

Khi phát hiện origin lạ được phép đọc dữ liệu, thu hẹp allowlist ngay, kiểm tra access log và cache/CDN, xác định endpoint/field nhạy cảm bị lộ, đánh giá credential/session có thể bị sử dụng và revoke/rotate nếu cần. Nếu domain được allowlist bị chiếm quyền, gỡ origin hoặc tạm dừng tích hợp, khắc phục domain ownership và rà soát các request trong thời gian bị ảnh hưởng.

## 15. Checklist trước khi cho phép một origin

- [ ] Origin có owner, use case và lý do nghiệp vụ cụ thể?
- [ ] Origin được xác định chính xác theo scheme, host và port?
- [ ] Domain/subdomain được tổ chức kiểm soát và không có nguy cơ takeover?
- [ ] Có tránh echo Origin tùy ý, wildcard rộng và `Origin: null`?
- [ ] Credentialed CORS chỉ bật cho origin cần thiết và dùng exact ACAO?
- [ ] Method, request header và exposed response header được giới hạn?
- [ ] Dynamic ACAO có `Vary: Origin` và cache policy phù hợp?
- [ ] API vẫn xác thực, phân quyền object/tenant và trả dữ liệu tối thiểu?
- [ ] Cookie/session có SameSite/Secure phù hợp và state-changing request có CSRF protection?
- [ ] Preflight được xử lý đúng nhưng actual request vẫn được authorize?
- [ ] Có test browser cho origin hợp lệ, origin lạ, credentials, preflight, CSRF và cache?
- [ ] Có audit/alert khi allowlist hoặc CORS policy thay đổi?

Chỉ cho phép origin đã được xác định, quản lý và có nhu cầu đọc response. CORS cần được cấu hình theo exact origin allowlist, credential mode, method và header tối thiểu; cache phải tôn trọng `Vary: Origin`. CORS không thay thế authentication, authorization hoặc CSRF protection. Với dữ liệu nhạy cảm, server vẫn phải kiểm tra quyền trên từng endpoint và object, đồng thời chỉ trả đúng dữ liệu mà caller được phép nhận.
