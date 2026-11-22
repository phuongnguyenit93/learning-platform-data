# Preflight method và header

Khi một trang web chạy ở origin này gọi API ở origin khác, browser áp dụng Cross-Origin Resource Sharing (CORS) để quyết định JavaScript có được đọc response hay không. Với một số request, browser gửi trước một request `OPTIONS` gọi là **CORS preflight**. Request này hỏi server liệu origin hiện tại có được phép gửi method và các request header dự kiến hay không. Server trả các CORS response header để browser quyết định có gửi request thật.

Preflight thường xuất hiện khi frontend gọi API bằng `PATCH`, `PUT`, `DELETE`, gửi `Content-Type: application/json`, hoặc thêm header như `Authorization`, `If-Match` hay `X-Request-Id`. Nếu server cấu hình sai, browser có thể chặn request thật hoặc không cho JavaScript đọc response. Nếu cấu hình quá rộng, ứng dụng có thể vô tình cho website không tin cậy đọc dữ liệu API.

Trong phạm vi `SECURITY_API_SECURITY`, CORS phải được thiết kế theo origin, endpoint, method, header và luồng nghiệp vụ. CORS là chính sách chia sẻ response với browser; nó không xác thực user, không cấp quyền trên object và không thay thế CSRF protection. API vẫn phải thực hiện authentication, function/object authorization, validation và kiểm soát side effect trên request thật.

## 1. Origin và same-origin policy

Origin được xác định bởi bộ ba:

- Scheme, ví dụ `https`.
- Hostname, ví dụ `app.example.com`.
- Port, ví dụ `443` hoặc `8443`.

Hai URL có cùng origin khi cả ba thành phần khớp sau khi áp dụng quy tắc chuẩn hóa của URL. Ví dụ:

| URL A | URL B | Quan hệ |
|---|---|---|
| `https://app.example.com` | `https://app.example.com/api` | Cùng origin |
| `https://app.example.com` | `http://app.example.com` | Khác scheme |
| `https://app.example.com` | `https://api.example.com` | Khác host |
| `https://app.example.com` | `https://app.example.com:8443` | Khác port |
| `https://app.example.com` | `https://app.example.com:443` | Cùng origin theo default HTTPS port |

Same-origin policy giới hạn cách một document đọc tài nguyên từ origin khác. CORS cho phép server công bố những origin được đọc response thông qua browser. CORS không phải cơ chế chặn mọi kết nối mạng giữa hai origin; nó là một phần của browser security model.

Header `Origin` thường được browser tự thêm vào request cross-origin. Giá trị này có dạng origin, không phải URL đầy đủ có path/query. Một số context có thể gửi `Origin: null`, ví dụ tài liệu sandbox hoặc scheme đặc biệt. Chỉ cho phép `null` nếu có use case rõ ràng và đã đánh giá rủi ro; không dùng nó như wildcard cho ứng dụng local.

## 2. Khi nào browser gửi preflight?

Browser tự gửi preflight khi request cross-origin không thuộc nhóm CORS-safelisted request. Một số trường hợp thường gặp:

- Method không safelisted, ví dụ `PUT`, `PATCH` hoặc `DELETE`.
- Request có header không safelisted, ví dụ `Authorization`, `X-Request-Id`, `If-Match` hoặc header tùy chỉnh.
- `Content-Type` có giá trị ngoài nhóm media type safelisted, ví dụ `application/json`.
- Request có thuộc tính hoặc header khác khiến nó không còn là simple request theo Fetch/CORS rules.

Các method safelisted phổ biến là `GET`, `HEAD`, `POST`. Nhóm request header safelisted bị giới hạn; `Content-Type` chỉ được safelist trong một số media type như `application/x-www-form-urlencoded`, `multipart/form-data` và `text/plain`, cùng các điều kiện về giá trị. Vì vậy, một request `POST` không tự động tránh preflight chỉ vì method là POST.

Ví dụ frontend:

```javascript
fetch("https://api.example.com/v1/orders/42", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer eyJ...",
    "If-Match": "\"version-7\"",
    "X-Request-Id": "req-123"
  },
  body: JSON.stringify({ status: "CONFIRMED" })
});
```

Do method là `PATCH` và có các header không safelisted, browser sẽ gửi preflight trước khi gửi request `PATCH` thật. Nếu preflight không được chấp nhận, browser không gửi request thật theo flow này.

### 2.1. Simple request vẫn chịu CORS

Một request đơn giản có thể được browser gửi mà không cần preflight. Tuy nhiên, response vẫn phải vượt qua CORS check thì JavaScript mới đọc được. Vì thế, việc không có preflight không có nghĩa request được tin cậy hoặc được phép thực hiện nghiệp vụ.

Ví dụ HTML form có thể gửi một số request cross-origin mà không cần preflight. Server vẫn phải bảo vệ side effect bằng CSRF token, SameSite cookie, authorization và các kiểm soát phù hợp. Không dựa vào preflight như một lớp chống CSRF.

## 3. Cấu trúc một CORS preflight request

Một preflight thường có dạng:

```http
OPTIONS /v1/orders/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type,if-match,x-request-id
```

Các trường quan trọng:

| Header | Ý nghĩa |
|---|---|
| `Origin` | Origin của trang đang thực hiện request |
| `Access-Control-Request-Method` | Method browser muốn dùng cho request thật |
| `Access-Control-Request-Headers` | Danh sách request header không safelisted browser dự định gửi |

`OPTIONS` là method của preflight. `Access-Control-Request-Method` mới là method nghiệp vụ dự kiến, ví dụ `PATCH`. Server phải đánh giá method được yêu cầu này, không nhầm nó với method OPTIONS.

Danh sách trong `Access-Control-Request-Headers` thường được browser gửi ở dạng chữ thường. So sánh tên header phải không phân biệt hoa/thường theo quy tắc HTTP. Server nên parse thành danh sách token, chuẩn hóa và so với allowlist; không so khớp bằng substring.

Preflight không phải request nghiệp vụ. Nó không mang body của request thật và browser không gửi cookie hoặc HTTP credentials của request thật trong preflight. Do đó, CORS preflight handler không thể dựa vào session cookie của user để quyết định user có quyền sửa order hay không. Nó chỉ có thể quyết định origin, method và header có được phép theo CORS policy.

## 4. Cấu trúc CORS preflight response

Một response thành công có thể là:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, If-Match, X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Ý nghĩa:

| Response header | Vai trò |
|---|---|
| `Access-Control-Allow-Origin` | Origin được phép thực hiện CORS request và đọc response |
| `Access-Control-Allow-Methods` | Các method được phép theo CORS policy |
| `Access-Control-Allow-Headers` | Các request header không safelisted được phép gửi |
| `Access-Control-Allow-Credentials` | Cho phép browser chia sẻ response cho request có credentials mode `include` khi giá trị là `true` |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight |
| `Vary` | Cho cache trung gian biết response phụ thuộc vào request header nào |

Response preflight thường không cần body; `204 No Content` là lựa chọn phù hợp. `200 OK` cũng có thể được dùng. Điều quan trọng là status thành công và CORS response header phải đáp ứng request được hỏi.

### 4.1. Kiểm tra origin

Server so sánh `Origin` với allowlist origin đã cấu hình. Origin gồm scheme, host và port; không chỉ là domain. Ví dụ `https://app.example.com` khác `http://app.example.com` và khác `https://app.example.com:8443`.

Không phản chiếu bất kỳ `Origin` nào nhận được vào `Access-Control-Allow-Origin`. Cấu hình kiểu “lấy Origin từ request rồi trả lại nguyên văn” tương đương cho phép mọi website có thể truy cập response bằng browser.

Nếu có nhiều origin hợp lệ, server chọn đúng origin đang được phép và trả một giá trị `Access-Control-Allow-Origin` duy nhất. Không trả danh sách phân tách bằng dấu phẩy trong header này.

### 4.2. Kiểm tra method

Đọc `Access-Control-Request-Method`, chuẩn hóa theo quy tắc method token và kiểm tra nó thuộc allowlist cho route tương ứng. Ví dụ endpoint đọc order có thể cho `GET`, trong khi endpoint cập nhật có thể cho `PATCH` và cần permission riêng ở request thật.

`Access-Control-Allow-Methods` công bố method browser được phép gửi qua CORS. Nó không cấp quyền nghiệp vụ. Nếu `PATCH` xuất hiện trong danh sách này, user vẫn phải có permission `orders:update` và quyền trên order cụ thể khi request thật đến.

### 4.3. Kiểm tra request header

Parse `Access-Control-Request-Headers` thành danh sách header và kiểm tra từng tên với allowlist. Ví dụ:

```text
Allowed request headers:
  Authorization
  Content-Type
  If-Match
  X-Request-Id
```

Không cho phép mọi header chỉ để tránh lỗi frontend. Header như `X-Tenant-Id`, `X-Admin-Override` hoặc `X-Internal-Role` có thể bị client lợi dụng nếu backend tin chúng như security context. Nếu một header thực sự cần thiết, phải xác định rõ ai tạo, ai được phép gửi và server xác minh giá trị ra sao.

Header `Authorization` cần được cho phép rõ ràng khi client gửi bearer token. Không giả định wildcard trong `Access-Control-Allow-Headers` sẽ xử lý mọi header đặc biệt; hãy liệt kê rõ `Authorization` và các header cần dùng.

## 5. Phân biệt allow method, allow header và expose header

Ba nhóm header thường bị nhầm:

- `Access-Control-Allow-Methods`: method browser được phép gửi.
- `Access-Control-Allow-Headers`: request header browser được phép gửi.
- `Access-Control-Expose-Headers`: response header JavaScript được phép đọc ngoài nhóm response header safelisted.

Ví dụ API trả `ETag` và `X-Request-Id`. Browser nhận response nhưng JavaScript không nhất thiết đọc được hai header này nếu server không expose:

```http
Access-Control-Expose-Headers: ETag, X-Request-Id
```

`Access-Control-Expose-Headers` không cho phép client gửi request header. Ngược lại, `Access-Control-Allow-Headers` không làm response header trở nên visible cho JavaScript. Chỉ expose header thật sự cần thiết; không expose `Set-Cookie` để JavaScript đọc cookie vì browser không cho phép truy cập header này theo cách thông thường.

## 6. Credentials và wildcard

Request có credentials có thể mang cookie, HTTP authentication hoặc TLS client certificate tùy cơ chế browser. Trong Fetch API, frontend thường yêu cầu gửi credential cross-origin bằng `credentials: "include"`.

Ví dụ:

```javascript
fetch("https://api.example.com/v1/profile", {
  method: "GET",
  credentials: "include"
});
```

Khi server cho phép credentialed CORS request, response cần có:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Giá trị của `Access-Control-Allow-Credentials` phải là `true` đúng dạng quy định. Khi credentials mode là `include`, không thể dùng `Access-Control-Allow-Origin: *`; server phải trả origin cụ thể đã được kiểm tra. Wildcard không được dùng để mở quyền đọc response có credentials.

### 6.1. Cookie vẫn chịu SameSite và Secure

CORS không tự làm cookie được gửi. Cookie còn chịu `SameSite`, `Secure`, domain/path và browser privacy policy. Cookie cross-site thường cần `SameSite=None; Secure`, nhưng chính sách browser và third-party cookie restrictions có thể ảnh hưởng khả năng sử dụng. Cần test trên browser thực tế và không coi CORS header là đủ để thiết lập session.

### 6.2. Không kết hợp wildcard với credential

Cấu hình sau không hợp lệ cho credentialed CORS:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Không khắc phục bằng cách phản chiếu Origin tùy ý. Hãy dùng allowlist chính xác, trả đúng origin đã được xác minh và giới hạn credentialed endpoint ở các frontend thực sự cần.

### 6.3. Authorization header và credentials mode

Bearer token được gửi trong header `Authorization` là một request header cần được cho phép trong preflight. Việc gửi header này không đồng nghĩa browser tự động gửi cookie. `Access-Control-Allow-Headers` phải liệt kê `Authorization`; `Access-Control-Allow-Credentials` phụ thuộc vào credentials mode của request, không phải chỉ vì có header tên Authorization.

Trong mọi trường hợp, server vẫn phải xác minh chữ ký/issuer/audience/expiry của token và kiểm tra permission trên endpoint/object. CORS chỉ cho phép browser thực hiện và đọc response theo origin policy.

## 7. Origin allowlist an toàn

Một allowlist origin nên là cấu hình server-side có owner và quy trình thay đổi. Ví dụ:

```text
Production:
  https://app.example.com
  https://admin.example.com

Staging:
  https://staging-app.example.com
```

Các nguyên tắc:

- So khớp origin đầy đủ gồm scheme, host và port.
- Không dùng `contains("example.com")` để kiểm tra domain.
- Không chấp nhận `https://example.com.attacker.invalid` như subdomain hợp lệ.
- Nếu cho phép subdomain động, xác định boundary domain chính xác và cách xử lý IDN/punycode.
- Không tự động thêm mọi preview deployment hoặc domain do tenant cung cấp vào allowlist credentialed.
- Không lấy allowed origin từ query, body hoặc header do client gửi.
- Không cho phép `Origin: null` trừ khi có use case và threat review riêng.
- Tách allowlist production/staging/local; tránh đưa localhost hoặc dev domain vào production.

Nếu nhiều tenant có custom domain, cần xác minh domain ownership trước khi cho phép. Khi domain bị gỡ khỏi tenant hoặc hết quyền sở hữu, cập nhật CORS policy và cache một cách có kiểm soát.

## 8. Preflight không phải authentication hoặc authorization

Preflight thường không mang cookie hoặc credential của request thật. Vì vậy, server không thể dùng nó để xác định user hiện tại có quyền `orders:update` hay không. Nó chỉ xác định browser có thể gửi request với origin, method và header được hỏi hay không.

Ví dụ, server có thể cho phép origin `https://app.example.com` gửi `PATCH` đến `/v1/orders/{id}`. Khi request `PATCH` thật đến, server vẫn phải:

1. Xác thực bearer token/session.
2. Xác định principal và tenant từ security context đáng tin.
3. Kiểm tra permission `orders:update`.
4. Tải order trong phạm vi tenant được phép.
5. Kiểm tra object-level authorization và trạng thái workflow.
6. Validate body, version/ETag và business rule.
7. Thực hiện cập nhật trong transaction và ghi audit.

Không dùng thành công của preflight như bằng chứng rằng request thật được phép. Một origin được phép gọi API không có nghĩa mọi user từ origin đó có quyền trên mọi object.

## 9. CORS không thay thế CSRF protection

CORS và CSRF giải quyết vấn đề khác nhau:

| Cơ chế | Mục tiêu |
|---|---|
| CORS | Kiểm soát browser origin nào được đọc response cross-origin và trong điều kiện nào request không đơn giản được gửi |
| CSRF protection | Ngăn website khác lợi dụng credential tự động được browser gửi để thực hiện hành động ngoài ý muốn |
| Authentication | Xác định caller là ai |
| Authorization | Xác định caller được làm gì trên function/object nào |

Một form cross-origin có thể gửi một số simple request mà không cần preflight. Browser có thể không cho JavaScript đọc response nhưng side effect ở server vẫn có thể xảy ra. Vì vậy, API dùng cookie/session cho thao tác thay đổi dữ liệu cần CSRF token hoặc biện pháp tương đương, SameSite cookie phù hợp và kiểm tra Origin/Referer theo threat model.

Không tắt CSRF protection chỉ vì đã cấu hình CORS. Với API dùng bearer token trong Authorization header do JavaScript chủ động gắn, rủi ro CSRF thường khác với cookie tự động gửi, nhưng vẫn cần đánh giá XSS, token storage và credential flow.

## 10. Preflight và HTTP OPTIONS trong API

`OPTIONS` là HTTP method dùng để hỏi khả năng giao tiếp của target resource. CORS preflight là một trường hợp browser dùng OPTIONS với các header `Origin`, `Access-Control-Request-Method` và có thể `Access-Control-Request-Headers`.

Không nên nhầm mọi OPTIONS request với CORS preflight. Một client không phải browser có thể gọi OPTIONS để lấy capability hoặc API có thể định nghĩa hành vi OPTIONS riêng. Server nên nhận diện preflight bằng tổ hợp header phù hợp, áp dụng CORS policy và không thực hiện side effect.

### 10.1. Preflight phải được xử lý trước authentication filter phù hợp

Vì preflight không có session cookie của request thật, middleware authentication yêu cầu login trên mọi request có thể trả `401` cho OPTIONS trước khi CORS filter xử lý. Browser sau đó không gửi request thật dù token trong request thật hợp lệ.

Cấu hình CORS middleware/filter cần chạy trước authorization filter xử lý request nghiệp vụ. Điều này không có nghĩa mở mọi endpoint OPTIONS cho mọi hành vi; CORS handler chỉ trả preflight response theo origin/method/header policy. Request OPTIONS thực tế có ý nghĩa nghiệp vụ vẫn phải được bảo vệ theo endpoint contract.

### 10.2. Không redirect preflight

Tránh để OPTIONS preflight bị redirect do trailing slash, HTTP-to-HTTPS hoặc canonical host. Browser có thể xử lý redirect của preflight khác nhau hoặc từ chối flow tùy trường hợp. Frontend nên gọi đúng HTTPS URL cuối cùng; gateway nên trả CORS response trực tiếp cho OPTIONS trên route canonical.

### 10.3. Không thực hiện side effect trong preflight

Preflight chỉ là kiểm tra khả năng gửi request. Không tạo record, cập nhật trạng thái, gửi email, tiêu thụ quota nghiệp vụ hoặc kích hoạt job trong handler này. Nếu handler có log, chỉ ghi metadata cần thiết và không ghi token/body nhạy cảm.

## 11. CORS và cache

Nếu server chọn `Access-Control-Allow-Origin` động dựa trên request `Origin`, response phụ thuộc vào header đó. Khi đó cần trả:

```http
Vary: Origin
```

Với preflight response được tính theo method/header yêu cầu, cache trung gian có thể cần thêm:

```http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Thiếu `Vary` có thể khiến proxy/CDN dùng response đã tạo cho một origin hoặc method khác. Điều này có thể gây lỗi cho client hoặc làm lộ response qua cache misconfiguration.

### 11.1. Access-Control-Max-Age

`Access-Control-Max-Age` cho biết browser có thể cache kết quả preflight trong bao lâu, tính bằng giây. Ví dụ:

```http
Access-Control-Max-Age: 600
```

Giá trị quá thấp làm browser gửi OPTIONS thường xuyên, tăng latency và tải. Giá trị quá cao làm thay đổi CORS policy mất thời gian mới có hiệu lực với các preflight result đã cache. Browser có thể áp dụng giới hạn tối đa riêng; không giả định mọi browser giữ cache đúng bằng giá trị server gửi.

Khi thu hồi một origin hoặc header khỏi allowlist, cần tính đến preflight cache, CDN/proxy cache và rollout giữa nhiều instance. Không dùng `Access-Control-Max-Age` như cơ chế thu hồi quyền ngay lập tức. Nếu cần chặn khẩn cấp, policy ở tầng request thật và authorization vẫn phải từ chối; CORS không phải lớp kiểm soát truy cập chính.

## 12. CORS trên response thật và response lỗi

Preflight thành công chỉ cho phép browser gửi request thật. Response thật cũng cần CORS header phù hợp để JavaScript đọc được. Điều này bao gồm response `200`, `400`, `401`, `403`, `404`, `409`, `422` và một số `5xx` nếu muốn frontend đọc error body.

Nếu CORS header chỉ được gắn khi controller thành công, frontend có thể thấy một lỗi CORS chung thay vì status/error code thật khi backend trả `401` hoặc `403`. Hãy đặt CORS middleware ở vị trí áp dụng nhất quán cho response, kể cả khi authentication/authorization hoặc exception handler từ chối request.

Tuy nhiên, không thêm `Access-Control-Allow-Origin` tùy tiện vào mọi response nếu origin không được phép. Chỉ phản hồi CORS cho origin đã qua policy. Error body vẫn phải tuân theo error contract an toàn, không lộ stack trace hoặc dữ liệu ngoài quyền.

## 13. Ví dụ cấu hình với Spring Boot và Spring Security

Spring Security cần CORS được cấu hình để CORS processing diễn ra trước các bước authentication/authorization phù hợp. Ví dụ:

```java
@Configuration
class CorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        org.springframework.web.cors.CorsConfiguration config =
            new org.springframework.web.cors.CorsConfiguration();

        config.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
        ));
        config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH", "DELETE"
        ));
        config.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "If-Match", "X-Request-Id"
        ));
        config.setExposedHeaders(List.of(
            "ETag", "X-Request-Id"
        ));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
```

Security filter chain:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .build();
}
```

Đây là cấu hình minh họa. Cần dùng đúng class `CorsConfiguration` của Spring Web (không nhầm với class cùng tên trong framework khác), kiểm tra phiên bản Spring Security và cấu hình filter chain thực tế. Khi CORS được tích hợp đúng, preflight được CORS processing xử lý trước authorization. Không cần mở rộng `permitAll()` cho toàn bộ API chỉ để làm preflight chạy.

### 13.1. Phân tách policy theo route

Không nhất thiết mọi endpoint dùng cùng allowlist. Ví dụ:

| Route | Origin | Method | Header | Credentials |
|---|---|---|---|---|
| `/api/public/**` | Website public đã duyệt | `GET` | Header tối thiểu | Không |
| `/api/profile/**` | Frontend ứng dụng | `GET`, `PATCH` | `Authorization`, `Content-Type`, `X-Request-Id` | Theo auth model |
| `/api/admin/**` | Admin portal riêng | Method tối thiểu | Header cần thiết | Có thể có, kèm authz mạnh |

Với route quản trị, giới hạn origin ở admin portal không thay authentication, MFA/step-up hoặc permission `admin:*`. Nếu admin API chỉ được gọi server-to-server, có thể không cần bật CORS browser access.

### 13.2. `allowedOriginPatterns` cần thận trọng

Một số framework cho phép pattern origin. Pattern rộng như `https://*.example.com` có thể bao gồm subdomain do bên thứ ba hoặc tenant tự quản lý. Khi dùng credentials, pattern có thể khiến framework phản chiếu origin phù hợp vào response. Chỉ dùng pattern khi domain ownership và subdomain lifecycle được kiểm soát; nếu có thể, ưu tiên danh sách origin chính xác.

### 13.3. Không thêm CORS header ở nhiều lớp tùy tiện

Nếu CDN, API gateway, reverse proxy và application đều tự thêm CORS header, response có thể có nhiều `Access-Control-Allow-Origin` hoặc policy không đồng nhất. Chọn một lớp chịu trách nhiệm chính hoặc định nghĩa rõ cách phối hợp. Đảm bảo preflight và request thật đi qua cùng policy; không để gateway cho phép origin mà service lại phản chiếu origin bất kỳ.

## 14. Kiểm thử preflight bằng command line và browser

Có thể dùng `curl` để kiểm tra response header của server:

```bash
curl -i -X OPTIONS 'https://api.example.com/v1/orders/42' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: authorization,content-type,if-match,x-request-id'
```

Response cần có origin chính xác, method `PATCH`, toàn bộ header được yêu cầu và credentials header nếu request thật dùng credentials mode `include`. `curl` chỉ giúp xem server response; nó không thực thi browser CORS algorithm và không chứng minh JavaScript có thể đọc response.

### 14.1. Kiểm thử trong browser DevTools

Trong Network panel:

1. Tìm request `OPTIONS` phát sinh trước request thật.
2. Kiểm tra `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Xem response status và `Access-Control-Allow-*`.
4. Xác nhận request thật có được gửi hay bị browser dừng ở preflight.
5. Kiểm tra response thật có `Access-Control-Allow-Origin` phù hợp.
6. Kiểm tra console để xem lỗi CORS cụ thể.

Không chỉ test bằng Postman hoặc curl. Các công cụ này không bị browser same-origin/CORS enforcement như JavaScript trong trang web.

### 14.2. Ma trận test cần có

| Tình huống | Kết quả mong đợi |
|---|---|
| Origin trong allowlist | Preflight thành công nếu method/header được phép |
| Origin không được phép | Không trả quyền CORS cho origin đó |
| `Origin: null` | Bị từ chối trừ khi có policy riêng đã duyệt |
| Method được phép | `Access-Control-Allow-Methods` bao gồm method yêu cầu |
| Method không được phép | Preflight thất bại; request thật không được browser gửi theo flow đó |
| Header được phép | Tất cả header yêu cầu nằm trong allowlist |
| Header tùy chỉnh không được phép | Preflight thất bại |
| `Authorization` | Được liệt kê rõ trong allow headers nếu client gửi |
| Credentials `include` | ACAO là origin cụ thể và ACAC là `true` |
| Wildcard cùng credentials | Không được cấu hình/không được browser chấp nhận |
| Actual response `401`/`403` | CORS header vẫn đúng cho origin hợp lệ để frontend đọc error contract |
| Origin động | `Vary: Origin` được thiết lập |
| Preflight động theo method/header | Cache variation phù hợp, không dùng nhầm response |
| OPTIONS qua gateway | Không redirect và không bị auth filter chặn sai |
| Simple cross-origin request | CSRF và authorization vẫn bảo vệ side effect |
| OPTIONS không phải preflight | Được xử lý theo API contract và access control riêng |
| Browser cache preflight | Thay đổi policy được rollout/thu hồi có tính đến max-age |

## 15. Những lỗi CORS thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Phản chiếu mọi Origin | Website bất kỳ có thể đọc response | Allowlist origin chính xác |
| `Access-Control-Allow-Origin: *` với credentials | Browser từ chối credentialed response; cấu hình có thể tạo hiểu nhầm | Trả origin cụ thể và ACAC đúng khi cần |
| Quên `Authorization` trong allow headers | Preflight thất bại khi frontend gửi bearer token | Liệt kê rõ header cần thiết |
| Nhầm OPTIONS với method thật | Cho phép sai method hoặc xử lý sai preflight | Đọc `Access-Control-Request-Method` |
| Yêu cầu login trên preflight | OPTIONS bị `401`, request thật không được gửi | Đặt CORS processing trước authz phù hợp |
| Chỉ thêm CORS header cho response 2xx | Frontend không đọc được lỗi 401/403 | Áp CORS policy nhất quán cho error response hợp lệ |
| Coi preflight là CSRF protection | Simple request vẫn có thể gây side effect | CSRF token/SameSite và authorization |
| Dùng `contains()` cho domain | Origin giả có thể vượt kiểm tra | Parse origin và so khớp chính xác |
| Không có `Vary: Origin` | Cache có thể trả response CORS của origin khác | Thiết lập Vary đúng khi response động |
| Cấu hình CORS ở nhiều lớp | Duplicate/conflicting headers | Chọn owner policy và test end-to-end |
| Mở `OPTIONS /**` không điều kiện | Route OPTIONS khác có thể bị mở ngoài ý muốn | Xử lý preflight có nhận diện và policy rõ |
| Test chỉ bằng Postman/curl | Bỏ sót browser enforcement và cookie behavior | Test bằng browser thực tế |

## 16. Checklist review CORS preflight

- [ ] Origin được xác định theo scheme, host và port; allowlist có owner.
- [ ] Không phản chiếu Origin tùy ý hoặc dùng wildcard với credentialed request.
- [ ] `Origin: null` bị từ chối trừ khi có use case được duyệt.
- [ ] Preflight được nhận diện qua OPTIONS và `Access-Control-Request-*` headers.
- [ ] Method được kiểm tra qua `Access-Control-Request-Method`, không nhầm với OPTIONS.
- [ ] Request header được parse thành danh sách và so với allowlist; `Authorization` được khai báo rõ khi cần.
- [ ] `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers` và credentials được trả đúng semantics.
- [ ] `Access-Control-Expose-Headers` chỉ gồm response header JavaScript cần đọc.
- [ ] Preflight không yêu cầu session credential và không thực hiện side effect.
- [ ] CORS filter chạy trước authentication/authorization filter xử lý request nghiệp vụ.
- [ ] Request thật vẫn có authentication, function/object authorization, validation và CSRF protection phù hợp.
- [ ] CORS header có trên response thật và error response cho origin được phép.
- [ ] `Vary` và `Access-Control-Max-Age` phù hợp với cache và quy trình thu hồi policy.
- [ ] Gateway/proxy/application không phát duplicate hoặc conflicting CORS headers.
- [ ] OPTIONS không bị redirect; route và method thật được test qua browser.
- [ ] Có test positive/negative cho origin, method, header, credential, cache và CSRF.

Preflight là cuộc trao đổi giữa browser và server để xác định một origin có thể gửi một method cùng các header cụ thể hay không. Server cần kiểm tra origin, method và từng header theo policy của endpoint, trả CORS response header chính xác và xử lý cache phù hợp. Sau đó request thật vẫn phải đi qua authentication, authorization trên function/object, validation và bảo vệ CSRF cần thiết. Khi phân biệt rõ hai giai đoạn này, API vừa hỗ trợ frontend cross-origin đúng cách vừa tránh dùng CORS như một cơ chế cấp quyền hoặc bảo vệ nghiệp vụ.
