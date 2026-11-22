# Allowlist origin cụ thể

Cross-Origin Resource Sharing (CORS) là cơ chế trình duyệt dùng để quyết định JavaScript từ một origin có được phép đọc response của request tới origin khác hay không. Với API được gọi từ web frontend, cấu hình CORS sai có thể làm lộ response chứa dữ liệu nhạy cảm cho website không đáng tin cậy. Một lỗi phổ biến là phản chiếu mọi giá trị trong header `Origin` vào `Access-Control-Allow-Origin` hoặc dùng wildcard cùng credential.

Cách thiết kế an toàn là khai báo allowlist các origin cụ thể theo môi trường và mục đích, so khớp chính xác origin đã được chuẩn hóa, chỉ bật credential khi thực sự cần, giới hạn method/header được phép và xử lý preflight đúng cách. CORS là chính sách truy cập response của browser; nó không thay thế xác thực, phân quyền, kiểm tra object/tenant hay bảo vệ CSRF.

## 1. Origin là gì?

Origin được xác định bởi bộ ba:

- Scheme: giao thức, ví dụ `https`.
- Host: hostname hoặc địa chỉ host.
- Port: cổng hiệu lực.

Ví dụ:

| URL | Origin |
|---|---|
| `https://app.example.com/dashboard` | `https://app.example.com` |
| `https://app.example.com:443/orders` | `https://app.example.com` |
| `http://app.example.com` | `http://app.example.com` |
| `https://admin.example.com` | `https://admin.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |

Path, query string và fragment không thuộc origin. Hai URL chỉ khác path vẫn cùng origin; khác scheme, host hoặc port thì là cross-origin.

Trình duyệt gửi header `Origin` trong các request cross-origin phù hợp. Server phản hồi bằng CORS headers, chẳng hạn `Access-Control-Allow-Origin`. Browser kiểm tra các header này trước khi cho JavaScript đọc response. Với một số request đơn giản, request có thể đã được gửi tới server trước khi browser chặn JavaScript đọc kết quả.

### 1.1. Origin không phải site

Origin và site là hai khái niệm khác nhau. Ví dụ `https://app.example.com` và `https://admin.example.com` là hai origin khác nhau, dù có thể được xem là cùng site theo quy tắc schemeful same-site của trình duyệt. CORS so sánh origin; cookie SameSite sử dụng khái niệm site.

Điều này quan trọng khi thiết kế cookie và CSRF: hai subdomain cùng site vẫn có thể là hai origin riêng, và một subdomain bị chiếm quyền có thể tạo rủi ro đối với cookie hoặc luồng xác thực của domain cha.

### 1.2. Chuẩn hóa origin

Allowlist nên lưu origin ở dạng chuẩn, không có path hoặc dấu slash cuối. Ví dụ hợp lệ:

~~~text
https://app.example.com
https://admin.example.com
https://partner.example.net:8443
~~~

Không dùng các giá trị như:

~~~text
https://app.example.com/
https://app.example.com/dashboard
*.example.com
example.com
~~~

Khi xử lý request, dùng parser URL/URI phù hợp để phân tích origin và so khớp theo quy tắc nhất quán. Tránh tự tách header bằng chuỗi hoặc regex đơn giản. Với hostname quốc tế hóa (IDN), cần chuẩn hóa theo cùng một profile IDNA ở lúc đăng ký và lúc kiểm tra; tránh hai biểu diễn Unicode/A-label bị hiểu khác nhau.

## 2. Vì sao phải dùng allowlist origin cụ thể?

Một website không đáng tin có thể chạy JavaScript và cố gọi API bằng browser của người dùng. Nếu API cho phép origin bất kỳ đọc response, script đó có thể lấy dữ liệu mà browser gửi kèm cookie hoặc credential của nạn nhân, tùy chính sách cookie và xác thực.

Ví dụ website độc hại:

~~~javascript
fetch("https://api.example.com/account/profile", {
  credentials: "include"
})
  .then(response => response.json())
  .then(data => sendToAttacker(data));
~~~

Nếu API phản chiếu origin của website này và cho phép credential, browser có thể cho JavaScript đọc response. Khi đó, CORS policy đã mở quyền đọc dữ liệu cho origin không được tin cậy.

Allowlist cụ thể giúp giới hạn những web application được phép đọc response. Mỗi origin nên gắn với một ứng dụng, môi trường và owner đã xác minh. Không đưa origin thử nghiệm, preview deployment hoặc domain không còn kiểm soát vào allowlist production.

### 2.1. Các cách cấu hình nguy hiểm

| Cấu hình | Rủi ro |
|---|---|
| Phản chiếu mọi giá trị `Origin` | Bất kỳ website nào cũng có thể được cấp quyền đọc response |
| `Access-Control-Allow-Origin: *` cho API trả dữ liệu riêng tư | Mọi origin đều được phép đọc response không credential |
| Wildcard origin cùng credential | Browser từ chối cấu hình này; cố workaround bằng phản chiếu origin sẽ tạo lỗ hổng |
| Allowlist bằng substring | Có thể chấp nhận domain giả như `app.example.com.attacker.test` |
| Cho phép mọi subdomain | Subdomain bị chiếm hoặc do bên thứ ba kiểm soát có thể được tin nhầm |
| Cho phép `null` tùy tiện | Các origin opaque như sandboxed document hoặc local file có thể được cấp quyền |
| Cho phép mọi method/header | Mở rộng bề mặt API và preflight ngoài nhu cầu |
| Dùng CORS làm authorization | Non-browser client có thể bỏ qua cơ chế browser CORS |

## 3. Thiết kế allowlist origin chính xác

### 3.1. So khớp toàn bộ origin

Nếu chỉ cho phép frontend production, cấu hình rõ:

~~~text
https://app.example.com
https://admin.example.com
~~~

So sánh toàn bộ origin gồm scheme, host và port. Không chỉ so sánh hostname, vì `http://app.example.com` và `https://app.example.com` là hai origin khác nhau; `https://app.example.com:8443` cũng khác origin mặc định.

Không dùng kiểm tra kiểu:

~~~java
origin.contains("example.com")
~~~

hoặc:

~~~java
origin.endsWith("example.com")
~~~

Các cách này có thể chấp nhận hostname giả hoặc tên miền có suffix gây nhầm lẫn. Nếu cần hỗ trợ subdomain, hãy parse hostname, kiểm tra ranh giới nhãn DNS và chỉ áp dụng cho domain mà tổ chức kiểm soát đầy đủ. Với credentialed API, ưu tiên danh sách origin cụ thể thay vì wildcard subdomain.

### 3.2. Không phản chiếu Origin vô điều kiện

Mẫu nguy hiểm:

~~~java
response.setHeader("Access-Control-Allow-Origin",
                   request.getHeader("Origin"));
response.setHeader("Access-Control-Allow-Credentials", "true");
~~~

Đoạn này biến mọi origin gửi request thành origin được tin cậy. Cách đúng là kiểm tra origin với allowlist trước rồi mới trả lại đúng origin đã được chấp nhận:

~~~java
if (allowedOrigins.contains(parsedOrigin)) {
    response.setHeader("Access-Control-Allow-Origin",
                       parsedOrigin.toString());
    response.setHeader("Vary", "Origin");
}
~~~

Đây chỉ là minh họa logic. Nên dùng CORS processor của framework thay vì tự viết header handling, để xử lý preflight, duplicate header và các trường hợp protocol theo chuẩn.

Nếu origin không nằm trong allowlist, không trả `Access-Control-Allow-Origin` cho origin đó. Có thể ghi nhận request bị từ chối ở mức metadata phù hợp, nhưng không phản chiếu giá trị đầu vào vào response hoặc log không kiểm soát.

### 3.3. Xử lý Origin thiếu, null hoặc bất thường

- **Không có Origin:** có thể là same-origin request, non-browser client hoặc request không thuộc CORS flow. Không tự động từ chối chỉ vì thiếu header; xác thực và authorization vẫn phải được thực hiện.
- **Origin: null:** có thể xuất hiện từ opaque origin như sandboxed iframe, data URL hoặc một số ngữ cảnh local file. Chỉ cho phép nếu có use case được đánh giá và kiểm soát cụ thể.
- **Origin sai định dạng hoặc nhiều giá trị:** từ chối CORS processing và không tạo allow-origin header.
- **Origin không khớp allowlist:** không cấp quyền đọc response cho origin đó.

Header Origin do browser tạo trong các luồng thông thường, nhưng client không phải browser có thể tự đặt header này. Do đó, Origin không phải bằng chứng danh tính hoặc bằng chứng request đến từ frontend đáng tin cậy.

### 3.4. Môi trường development, staging và production

Tách allowlist theo môi trường:

| Môi trường | Origin ví dụ | Quy tắc |
|---|---|---|
| Local development | `http://localhost:3000` | Chỉ dùng ở profile local/dev |
| Staging | `https://staging-app.example.com` | Chỉ cấp quyền cho staging API |
| Production | `https://app.example.com` | Danh sách production đã phê duyệt |
| Admin production | `https://admin.example.com` | Origin riêng, scope và quyền admin vẫn được kiểm tra |

Không để localhost, preview URL hoặc staging origin trong allowlist production nếu không có nhu cầu rõ ràng. Không dùng một cấu hình wildcard chung cho mọi profile để giảm công sức triển khai.

## 4. Credentialed CORS

Credentialed request là request browser có thể gửi thông tin xác thực như cookie, HTTP authentication hoặc client certificate theo chế độ credentials. Trong Fetch API, frontend thường yêu cầu cookie cross-origin bằng:

~~~javascript
fetch("https://api.example.com/account", {
  credentials: "include"
});
~~~

Để browser cho JavaScript đọc response credentialed, server phải trả cả hai header phù hợp:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

`Access-Control-Allow-Origin` phải là origin cụ thể; không thể dùng `*` cùng `Access-Control-Allow-Credentials: true`. Browser sẽ không chấp nhận wildcard cho trường hợp credentialed này.

### 4.1. Chỉ bật credential khi cần

Nếu API dùng bearer token do frontend chủ động gắn trong Authorization header và không dùng cookie cross-origin, có thể không cần bật `allowCredentials` cho CORS. Header Authorization vẫn thường làm request phát sinh preflight vì đây không phải CORS-safelisted request header; cần khai báo header này trong allowlist request headers.

Không bật credential toàn cục chỉ để “cho chắc”. Với API cookie/session, credentialed CORS cần allowlist hẹp và CSRF protection. Với API public không có dữ liệu riêng tư, cân nhắc không bật credential và chỉ trả dữ liệu được phép công khai.

### 4.2. Cookie vẫn chịu chính sách browser

CORS không tự quyết định cookie có được gửi hay không. Cookie còn chịu các thuộc tính:

- `Secure`: chỉ gửi qua kết nối HTTPS.
- `HttpOnly`: JavaScript không đọc trực tiếp cookie.
- `SameSite`: kiểm soát cookie trong ngữ cảnh cross-site.
- `Domain` và `Path`: xác định phạm vi cookie.
- `Expires`/`Max-Age`: vòng đời cookie.

Cross-site cookie thường cần `SameSite=None; Secure`, nhưng browser có thể áp dụng thêm cơ chế chặn third-party cookies. Không nên dựa vào CORS để thay thế thiết kế session/cookie an toàn.

### 4.3. Credential không có nghĩa origin được tin vô điều kiện

Một origin trong allowlist chỉ được phép đọc response theo CORS policy. API vẫn phải xác thực session/token, kiểm tra quyền chức năng, object ownership, tenant và trạng thái nghiệp vụ. Nếu một tài khoản bị chiếm hoặc frontend hợp lệ có lỗi XSS, CORS allowlist không ngăn được mọi hành vi trái phép.

## 5. Preflight request

Browser gửi preflight trước một số cross-origin request, thường khi request dùng method không safelisted, header tùy chỉnh hoặc content type không safelisted. Preflight là request `OPTIONS` có các header:

~~~http
OPTIONS /api/orders/123 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Server có thể phản hồi:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-ID
Access-Control-Max-Age: 600
Vary: Origin
~~~

Browser dùng response này để quyết định có gửi actual request hay không. Preflight không phải là thao tác nghiệp vụ và không nên yêu cầu session cookie như một request thông thường; CORS middleware cần xử lý nó trước các authorization filter có thể chặn OPTIONS. Actual request sau đó vẫn phải được xác thực và phân quyền bình thường.

### 5.1. Giới hạn method

Chỉ khai báo method cần thiết cho API:

~~~text
GET, POST, PATCH, DELETE
~~~

Không cấp tất cả method chỉ vì framework hỗ trợ. Nếu một route chỉ đọc dữ liệu, không cần cho origin đó gọi DELETE hoặc PATCH. Lưu ý CORS method allowlist chỉ là quyền browser được phép gửi cross-origin; server vẫn phải kiểm tra method và quyền nghiệp vụ.

### 5.2. Giới hạn request headers

Chỉ cho phép header mà frontend thực sự cần gửi, ví dụ:

~~~text
Authorization, Content-Type, X-Request-ID, X-CSRF-TOKEN
~~~

Không phản chiếu mọi giá trị `Access-Control-Request-Headers` mà browser gửi. Nếu request header không được cho phép, preflight phải thất bại theo CORS policy.

### 5.3. Max age

`Access-Control-Max-Age` cho browser cache kết quả preflight trong một khoảng thời gian. Giá trị lớn giảm số lần OPTIONS nhưng khiến thay đổi policy có thể chưa có hiệu lực ngay ở browser đang giữ cache. Chọn thời gian phù hợp với tần suất thay đổi policy và yêu cầu thu hồi quyền. Browser có thể áp dụng giới hạn riêng đối với giá trị max age.

## 6. Response headers và cache

Các header CORS chính:

| Header | Vai trò |
|---|---|
| `Access-Control-Allow-Origin` | Origin được phép đọc response |
| `Access-Control-Allow-Credentials` | Cho phép browser expose response của credentialed request |
| `Access-Control-Allow-Methods` | Method được phép cho cross-origin request |
| `Access-Control-Allow-Headers` | Request headers được phép |
| `Access-Control-Expose-Headers` | Response headers JavaScript được phép đọc |
| `Access-Control-Max-Age` | Thời gian browser cache preflight |
| `Vary: Origin` | Báo cache rằng response phụ thuộc Origin |

### 6.1. Vary: Origin

Nếu server chọn `Access-Control-Allow-Origin` động từ allowlist, response cần `Vary: Origin` để shared cache/CDN không dùng response được tạo cho origin A để phục vụ origin B.

Ví dụ:

~~~http
Vary: Origin
Access-Control-Allow-Origin: https://app.example.com
~~~

Nếu response có nhiều chiều biến thiên, cần hợp nhất `Vary` thay vì ghi đè header do proxy/framework đã thiết lập. Với preflight, cache có thể còn cần phân biệt `Access-Control-Request-Method` và `Access-Control-Request-Headers` khi response phụ thuộc hai giá trị đó.

Không cache công khai response chứa dữ liệu theo session/credential chỉ vì đã cấu hình CORS. Cache-Control và cache key phải phản ánh tính riêng tư của dữ liệu.

### 6.2. Expose response headers

Browser không cho JavaScript đọc mọi response header tùy ý. Nếu frontend cần đọc header như `Location` hoặc `X-Request-ID`, khai báo rõ:

~~~http
Access-Control-Expose-Headers: Location, X-Request-ID
~~~

Không expose toàn bộ header nếu không cần. Tránh làm lộ header nội bộ chứa thông tin vận hành, trace, backend topology hoặc dữ liệu nhạy cảm.

### 6.3. Không trả nhiều Access-Control-Allow-Origin values

`Access-Control-Allow-Origin` chỉ nhận một origin được chọn hoặc wildcard trong trường hợp phù hợp. Không trả danh sách phân tách bằng dấu phẩy như:

~~~http
Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com
~~~

Thay vào đó, parse Origin của request, xác minh nó nằm trong allowlist, rồi trả đúng một origin. Nếu origin không hợp lệ, không trả header cho phép.

## 7. CORS không thay thế CSRF và authorization

Đây là điểm dễ hiểu nhầm nhất khi cấu hình browser API.

### 7.1. CORS chủ yếu kiểm soát việc đọc response

Với một số request đơn giản, browser có thể gửi request cross-origin nhưng không cho JavaScript đọc response nếu CORS check thất bại. Do đó, CORS không bảo đảm server không thực hiện side effect.

Ví dụ website độc hại có thể gửi một HTML form cross-site tới endpoint thay đổi email hoặc tạo giao dịch. Nếu endpoint dùng cookie tự động được browser gửi và không có CSRF defense, thao tác có thể được thực hiện dù attacker không đọc được response.

### 7.2. CSRF protection

Nếu API xác thực bằng cookie/session, cần CSRF protection phù hợp:

- Dùng synchronizer token hoặc double-submit cookie được thiết kế đúng.
- Kiểm tra token CSRF trên request thay đổi trạng thái.
- Dùng SameSite cookie như một lớp giảm rủi ro, không coi đó là biện pháp duy nhất.
- Có thể kiểm tra Origin/Referer như defense in depth cho các request nhạy cảm.
- Không cho phép method an toàn như GET tạo side effect.
- Không tắt CSRF chỉ vì đã cấu hình CORS.

Với API dùng bearer token trong Authorization header và không dựa vào cookie tự động, mô hình CSRF khác; vẫn phải bảo vệ token khỏi XSS, storage không an toàn và lộ qua log.

### 7.3. Authorization ở server

Mọi request vẫn phải qua:

1. Authentication: xác minh principal/session/token.
2. Function authorization: kiểm tra quyền gọi operation.
3. Object authorization: kiểm tra quyền trên object cụ thể.
4. Tenant isolation: giới hạn dữ liệu theo tenant đã xác minh.
5. Business validation: kiểm tra trạng thái và quy tắc nghiệp vụ.

Origin được allowlist không có nghĩa mọi user của frontend đó được quyền truy cập mọi tài nguyên. CORS không phải access control cho API client nói chung.

## 8. Cấu hình CORS trong Spring Security

Với Spring MVC/Spring Security, nên cấu hình CORS tập trung và để Spring xử lý preflight. Ví dụ:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://admin.example.com"
    ));
    config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH", "DELETE"
    ));
    config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-CSRF-TOKEN"
    ));
    config.setExposedHeaders(List.of(
            "Location",
            "X-Request-ID"
    ));
    config.setAllowCredentials(true);
    config.setMaxAge(Duration.ofMinutes(10));

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Kết nối cấu hình với Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

Ví dụ trên giả định API dùng cookie/session hoặc credentialed browser flow nên bật allowCredentials. Nếu không cần credentialed CORS, đặt false hoặc bỏ qua cấu hình đó. CSRF configuration cần phù hợp với cơ chế xác thực thực tế; không vô hiệu hóa CSRF chỉ để làm CORS hoạt động.

### 8.1. Vì sao CORS phải chạy trước authorization filter?

Preflight là request OPTIONS do browser tự gửi trước actual request. Nó thường không mang session credential như actual request. Nếu một authentication filter chặn OPTIONS trước khi CORS processor trả preflight response, browser sẽ báo lỗi CORS dù endpoint thực tế có thể đã được bảo vệ đúng.

Spring Security tích hợp CORS khi gọi `http.cors` và tìm được `CorsConfigurationSource` phù hợp. Nếu tự đăng ký CorsFilter hoặc cấu hình ở proxy, phải bảo đảm chỉ có một policy nhất quán và CORS xử lý trước security filter có thể từ chối preflight. Tránh cho phép mọi OPTIONS một cách rộng rãi nếu ứng dụng còn có endpoint OPTIONS mang ý nghĩa nghiệp vụ.

### 8.2. Cẩn thận với allowedOriginPatterns

Spring hỗ trợ origin patterns trong một số phiên bản. Pattern tiện cho môi trường có nhiều subdomain, nhưng wildcard rộng cùng credential có thể vô tình tin mọi subdomain. Chỉ dùng pattern khi domain boundary được kiểm soát, parser/canonicalization rõ ràng và quy tắc không khớp domain giả. Với production frontend đã biết, `setAllowedOrigins` với danh sách chính xác dễ kiểm tra hơn.

### 8.3. Không cấu hình CORS ở nhiều tầng theo cách mâu thuẫn

CORS có thể được cấu hình ở CDN, API gateway, reverse proxy, servlet container và application. Nếu nhiều tầng cùng thêm header, response có thể có header trùng hoặc policy khác nhau. Chọn một nơi làm nguồn policy chính; các tầng khác phải chuyển tiếp hoặc áp dụng cùng cấu hình. Kiểm tra response thực tế sau gateway/CDN, không chỉ kiểm tra bean trong application.

## 9. Thiết kế cấu hình theo môi trường và tenant

### 9.1. Cấu hình riêng theo profile

Ví dụ cấu hình logic:

~~~yaml
app:
  cors:
    allowed-origins:
      - https://app.example.com
      - https://admin.example.com
    allowed-methods:
      - GET
      - POST
      - PATCH
      - DELETE
    allow-credentials: true
~~~

Development có thể bổ sung localhost trong profile riêng. Production không nên kế thừa wildcard hoặc danh sách dev một cách vô tình. Nên validate cấu hình khi startup: origin phải là origin tuyệt đối, scheme được phép, không có path/query/fragment và không có wildcard nếu policy yêu cầu exact allowlist.

### 9.2. Multi-tenant frontend origins

Một SaaS có thể có nhiều custom domain cho tenant. Không nên tự động cho phép bất kỳ hostname nào chỉ vì request có tenant ID tương ứng.

Quy trình phù hợp:

1. Tenant đăng ký domain qua giao diện quản trị.
2. Server xác minh quyền kiểm soát domain theo phương thức phù hợp.
3. Domain được liên kết với tenant và trạng thái xác minh.
4. CORS policy chỉ trả allow-origin khi domain canonical nằm trong registry đã xác minh và tenant đang active.
5. Domain bị thu hồi hoặc mất xác minh phải bị loại khỏi allowlist.
6. Cache policy phải phản ánh thay đổi domain và không dùng response cho origin khác.

CORS origin chỉ quyết định browser origin nào được đọc response. Nó không xác định tenant của user và không thay thế tenant membership check. Một custom domain hợp lệ vẫn có thể có user không có quyền trên tenant.

### 9.3. Preview deployment

Các URL preview có thể được tạo động theo pull request. Không dùng pattern kiểu mọi subdomain của hosting provider nếu nhiều nhóm hoặc người dùng bên ngoài có thể tạo subdomain. Có thể dùng một registry ngắn hạn, chỉ cấp origin cho preview đã xác thực, giới hạn dữ liệu test và tự hết hạn sau khi deployment bị xóa.

## 10. Quan sát và xử lý lỗi CORS

CORS error thường được browser hiển thị như lỗi network cho JavaScript, trong khi server vẫn nhận request. Để điều tra, cần xem cả browser console/network và server/gateway log.

Theo dõi:

- Origin được yêu cầu và kết quả allowlist, ở dạng đã redact/chuẩn hóa.
- Method và request headers được yêu cầu trong preflight.
- Route, environment, response status và CORS policy ID.
- Số lượng preflight, tỷ lệ bị từ chối và thay đổi đột biến theo origin.
- Header CORS thực tế sau gateway/CDN.
- Lỗi duplicate header hoặc response có nhiều allow-origin values.

Không log token, cookie hoặc body nhạy cảm chỉ để debug CORS. Không trả chi tiết cấu hình nội bộ hoặc toàn bộ allowlist trong error response.

Một số nguyên nhân phổ biến:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Browser báo thiếu Allow-Origin | Origin không nằm trong allowlist, CORS filter không chạy hoặc proxy xóa header |
| Credentialed request bị browser chặn | Thiếu Allow-Credentials true hoặc Allow-Origin là wildcard |
| OPTIONS trả 401/403 | Preflight bị authentication/authorization filter chặn trước CORS |
| Request GET hoạt động nhưng PATCH thất bại | Preflight method chưa được cho phép |
| Authorization header bị chặn | Header chưa có trong Allow-Headers |
| Frontend không đọc được Location | Header chưa có trong Expose-Headers |
| Lỗi chỉ xảy ra qua CDN | Cache key/Vary Origin hoặc header bị CDN ghi đè |
| Một subdomain lạ được chấp nhận | Pattern/suffix allowlist quá rộng hoặc phản chiếu Origin |

## 11. Kiểm thử CORS trong browser và API

Cần kiểm thử từ browser thật vì CORS enforcement do browser thực hiện. Kiểm tra bằng curl/Postman chỉ cho biết server trả header gì; các công cụ đó không tự áp dụng same-origin policy như browser.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Exact allowlist | Origin production đã đăng ký | Browser đọc response nếu các kiểm soát khác cho phép |
| Unknown origin | Website bên ngoài không có trong allowlist | Không có Allow-Origin phù hợp; browser không expose response |
| Scheme mismatch | http thay cho https | Bị từ chối |
| Port mismatch | Port 8443 thay cho 443 | Bị từ chối nếu không đăng ký |
| Suffix attack | app.example.com.attacker.test | Bị từ chối |
| Prefix attack | evil-app.example.com khi chỉ cho phép app.example.com | Bị từ chối |
| Subdomain takeover | Subdomain không còn thuộc tổ chức | Không nằm trong allowlist hoặc bị thu hồi |
| Null origin | Origin: null | Bị từ chối trừ use case đã phê duyệt |
| Missing Origin | Request không có Origin | Không coi là browser origin được cấp quyền; auth/authz vẫn hoạt động |
| Credentialed request | Cookie/session và origin hợp lệ | ACAO là origin cụ thể và ACAC là true |
| Wildcard with credentials | ACAO là * và credentials include | Browser không chấp nhận |
| Preflight | OPTIONS với PATCH và Authorization | Trả method/header được phép trước actual request |
| Disallowed method | Origin hợp lệ nhưng method không được phép | Preflight thất bại |
| Disallowed header | Request header tùy chỉnh không được phép | Preflight thất bại |
| Exposed header | Frontend đọc X-Request-ID | Chỉ đọc được khi được expose |
| Cache separation | Hai origin gọi qua CDN | Cache không dùng nhầm CORS header của origin khác |
| CSRF | Form cross-site gửi request thay đổi trạng thái bằng cookie | CSRF defense ngăn thao tác trái phép |
| Authorization | Origin hợp lệ gọi object ngoài quyền | API vẫn trả kết quả từ chối theo policy |
| Non-browser client | curl tự đặt Origin giả | Không được xem Origin là danh tính hoặc quyền truy cập |

### 11.1. Kiểm tra response preflight bằng curl

Có thể dùng curl để xem server trả gì:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders/123" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Lệnh này chỉ kiểm tra response HTTP. Nó không chứng minh browser sẽ chấp nhận toàn bộ flow, không kiểm tra cookie policy và không thay thế browser integration test.

### 11.2. Browser integration test

Tạo hai trang test ở hai origin khác nhau: một origin trong allowlist và một origin không được phép. Kiểm tra:

- JavaScript từ origin hợp lệ đọc được response dự kiến.
- JavaScript từ origin không hợp lệ không đọc được response.
- Preflight được xử lý đúng.
- Credential chỉ được gửi khi fetch credentials mode và cookie policy cho phép.
- Request có side effect vẫn cần CSRF token/authorization.
- CDN/cache không trộn response giữa hai origin.

## 12. Checklist trước khi phát hành

- [ ] Mỗi môi trường có allowlist origin riêng và owner xác nhận.
- [ ] Origin được parse/canonicalize và so khớp chính xác theo scheme, host, port.
- [ ] Không phản chiếu Origin vô điều kiện.
- [ ] Không dùng substring hoặc wildcard subdomain rộng.
- [ ] Origin null và Origin thiếu được xử lý theo policy rõ ràng.
- [ ] Chỉ bật credentialed CORS khi cần; không kết hợp wildcard với credentials.
- [ ] Allowed methods và allowed headers chỉ gồm những giá trị cần thiết.
- [ ] Exposed headers được giới hạn; không lộ metadata nội bộ.
- [ ] Preflight OPTIONS được xử lý trước authorization filter phù hợp.
- [ ] Cache/CDN có Vary: Origin khi response phụ thuộc origin; không cache nhầm dữ liệu credentialed.
- [ ] Cookie Secure/HttpOnly/SameSite được thiết kế phù hợp.
- [ ] CSRF protection được duy trì cho luồng xác thực bằng cookie.
- [ ] Authentication, function/object authorization và tenant isolation vẫn được thực thi.
- [ ] CORS policy không mâu thuẫn giữa CDN, gateway, proxy và application.
- [ ] Có browser test cho origin hợp lệ, origin lạ, preflight, credentials, cache và CSRF.

Allowlist origin cụ thể giới hạn website nào được browser cho phép đọc response của API. Chính sách cần so khớp đầy đủ scheme, host và port, tránh phản chiếu Origin, giới hạn credential/method/header và xử lý cache/preflight đúng cách. CORS không xác minh danh tính người gọi, không chặn mọi request cross-origin và không thay thế CSRF hay authorization. Khi các kiểm soát này được thiết kế riêng và kiểm thử trên browser thật, API có thể phục vụ frontend hợp lệ mà không mở response cho origin ngoài dự kiến.
