# Spring MVC — CorsFilter, allowed origins, credentials và hạn chế ký tự đại diện

## 1. Mục tiêu và bài toán thực tế

Một ứng dụng có frontend chạy tại `https://app.example.com`, API Spring MVC tại `https://api.example.com` và giao diện quản trị tại `https://admin.example.com`. Đây là các **origins khác nhau**. Trình duyệt áp dụng *same-origin policy* và chỉ cho JavaScript đọc phản hồi từ API khác origin nếu API khai báo quyền truy cập CORS thích hợp.

Một lỗi cấu hình thường gặp là bật:

~~~java
configuration.addAllowedOrigin("*");
configuration.setAllowCredentials(true);
~~~

Cách này **không hợp lệ** trong Spring Framework 6.2: khi cho phép credentials, `allowedOrigins` không được chứa `"*"` vì browser không chấp nhận kết hợp `Access-Control-Allow-Origin: *` với credentialed CORS response. Spring có cơ chế kiểm tra cấu hình và có thể từ chối kết hợp đó. Đổi sang một pattern rộng như `allowedOriginPatterns("*")` có thể khiến cấu hình hợp lệ về mặt kỹ thuật nhưng **vẫn nguy hiểm về chính sách**: gần như mọi website được echo origin để JavaScript đọc dữ liệu có credentials nếu các điều kiện cookie và trình duyệt cho phép.

Bài học này giúp bạn:

- Phân biệt `CorsFilter`, `CorsConfiguration`, `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource` và `DefaultCorsProcessor`.
- Hiểu **allowed origins** chính xác theo scheme/host/port; phân biệt `allowedOrigins` với `allowedOriginPatterns`.
- Hiểu lúc nào dùng `allowCredentials(true)` và các yêu cầu đối với `Access-Control-Allow-Origin` / `Access-Control-Allow-Credentials`, cookies, `fetch(credentials: "include")`.
- Giải thích khác biệt giữa wildcard trong **origins**, **origin patterns**, **allowed methods**, **allowed headers** và **exposed headers**.
- Cấu hình CORS ở Servlet filter boundary, tích hợp đúng với Spring Security và tránh cấu hình chồng chéo.
- Thực hành Spring Boot 3.5.0, Java 17 với `CorsFilter`, allowlist rõ ràng, kiểm thử preflight/actual requests bằng MockMvc và browser.
- Nhận diện lỗi CORS giả do HTTP 401/403/500, preflight bị chặn, cookie không được gửi, proxy/CDN và header phản hồi sai.

**Phạm vi:** Spring Framework 6.2, Spring MVC **Servlet stack**, HTTP(S) origins và trình duyệt hiện đại. Với Spring WebFlux, loại tương ứng là `CorsWebFilter` — không dùng nhầm `CorsFilter` của servlet.

## 2. Nhắc lại CORS theo ranh giới xử lý của Servlet Filter

**Origin** của HTTP(S) là bộ ba scheme + hostname + effective port. Một trang ở `https://app.example.com` gọi API `https://api.example.com` là cross-origin; đổi path trên cùng scheme/host/port không tạo origin khác. `http://localhost:5173` và `http://localhost:8080` khác origin dù cùng host.

**Điểm mới của bài này là vị trí xử lý:** browser áp dụng Same-Origin Policy và kiểm tra phản hồi CORS, còn `CorsFilter` chạy ở **Servlet filter chain phía server, trước MVC controller** khi được đăng ký và sắp thứ tự tương ứng. Filter chọn `CorsConfiguration` cho request, kiểm tra preflight hoặc actual request và có thể kết thúc yêu cầu mà chưa gọi handler. Nó không tự cấp danh tính, quyền nghiệp vụ hay CSRF token.

Ví dụ, browser gửi `Origin: https://app.example.com` tới `/api/orders`. Nếu policy cho phép, CORS response có thể mang `Access-Control-Allow-Origin: https://app.example.com` cùng `Vary: Origin`; nếu không, frontend không được đọc body theo cơ chế CORS, ngay cả khi actual HTTP request đã tới server. **Một bộ header trả đúng không chứng minh authentication/authorization đúng**.

Bài trước đã giải thích cú pháp origin và preflight; các mục sau tập trung vào `CorsFilter`/`CorsConfigurationSource`, wildcard với credentials, thứ tự filter và rủi ro policy quá rộng. Với những bài đọc độc lập, chỉ cần nhớ rằng `curl` không thực thi giới hạn CORS của browser, và same-site cookie **không đồng nghĩa** same-origin.

## 3. CORS preflight diễn ra ở đâu?

Một request JavaScript cross-origin có thể **không cần OPTIONS** nhưng vẫn cần actual response được CORS cho phép.

Ví dụ GET chỉ dùng safelisted headers:

~~~javascript
fetch("https://api.example.com/api/status");
~~~

Thường browser gửi GET trực tiếp (không preflight). Response vẫn cần ACAO thích hợp cho JavaScript đọc.

Ngược lại, JSON POST:

~~~javascript
fetch("https://api.example.com/api/orders", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({productId: 10, quantity: 2})
});
~~~

thường được browser kiểm tra bằng preflight trước:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Nếu cấu hình cho phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

thì browser có thể gửi actual POST tiếp theo. Method trong `Access-Control-Request-Method` là **method của actual request**, không phải OPTIONS. Vì vậy trong `allowedMethods` thông thường khai báo GET/POST/PUT mà client cần thực hiện, **không cần thêm OPTIONS chỉ vì preflight dùng OPTIONS**.

Một số điều kiện thường tạo preflight:

| Request do script tạo | Preflight thông thường |
| --- | --- |
| GET không custom request headers | Không |
| POST `application/x-www-form-urlencoded` với safelisted headers | Không |
| POST `multipart/form-data` theo điều kiện safelisted | Không |
| POST `application/json` | Có |
| PUT/PATCH/DELETE | Có |
| GET có `Authorization` | Có |
| GET thêm `X-API-Key` hoặc `X-Request-ID` | Có |
| POST có custom header `X-Tenant-ID` | Có |

Các quy tắc safelisted còn có giới hạn về giá trị/độ dài headers và trường hợp đặc biệt theo Fetch/browser; bảng trên là các tình huống phổ biến, không phải toàn bộ thuật toán chuẩn.

**Nếu preflight thất bại**, browser thường **không gửi actual request**. Nếu GET không preflight nhưng response thiếu ACAO, server đã có thể xử lý request, chỉ việc đọc response bị chặn. Phân biệt hai trường hợp này khi debug.

## 4. CorsFilter trong Spring Servlet stack

`org.springframework.web.filter.CorsFilter` là servlet filter của Spring Framework; nó có thể dùng trước `DispatcherServlet` và trước việc handler/controller thực thi, tùy thứ tự đăng ký. Nó dùng một `CorsConfigurationSource` để quyết định cấu hình nào áp dụng cho request, rồi dùng `CorsProcessor` (mặc định `DefaultCorsProcessor`) để xử lý giao thức CORS.

Mô hình:

~~~text
Browser
  |
  v
Servlet Filter Chain
  |
  +-- CorsFilter
  |     |
  |     +-- CorsConfigurationSource -> chọn policy theo request URL
  |     |
  |     +-- CorsProcessor -> kiểm Origin, method, requested headers
  |           |
  |           +-- hợp lệ preflight: ghi CORS headers và kết thúc OPTIONS
  |           +-- không hợp lệ: reject, không đi tiếp controller
  |           +-- actual request hợp lệ: thêm CORS headers, tiếp tục chain
  |
  +-- Security filters (nếu được tích hợp/đặt thứ tự đúng)
  |
  v
DispatcherServlet -> Controller -> Service
  |
  v
HTTP response
~~~

### 4.1. Các lớp và trách nhiệm

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `CorsFilter` | Servlet filter thực hiện CORS processing ở filter chain | Bean/filter registration |
| `CorsConfiguration` | Dữ liệu policy: origins, methods, headers, credentials, maxAge | `config.setAllowedOrigins(...)` |
| `CorsConfigurationSource` | Chọn `CorsConfiguration` cho từng request | Custom source hoặc URL mapping |
| `UrlBasedCorsConfigurationSource` | Map các URL patterns sang CORS policy | `registerCorsConfiguration("/api/**", config)` |
| `CorsProcessor` | Thuật toán đánh giá CORS request và ghi headers | `DefaultCorsProcessor` |
| `WebMvcConfigurer#addCorsMappings` | Cấu hình CORS ở MVC handler mappings | Không nhất thiết tạo CorsFilter riêng |
| `@CrossOrigin` | Cấu hình CORS tại controller/method | Phạm vi endpoint |
| `http.cors(...)` | Spring Security tích hợp CORS processing trong filter chain | Dùng khi bật Security |

**Không cần triển khai `OPTIONS` endpoint cho từng controller** chỉ để trả preflight nếu filter/MVC CORS processing đã được cấu hình đúng. Việc mở toàn bộ OPTIONS để “sửa lỗi CORS” không phải thay thế cho origin/method/header policy.

### 4.2. Điều gì xảy ra với actual request không có Origin?

Một HTTP request thông thường không có header `Origin` có thể không cần CORS processing: filter để request đi tiếp mà không phải chặn vì origin. Ví dụ `curl http://localhost:8080/api/status` vẫn nhận HTTP response mặc dù chính sách CORS có allowlist hẹp. Đây là hành vi hợp lý: server authorization phải được kiểm tra **riêng**.

Khi có `Origin` không nằm trong policy, `DefaultCorsProcessor` thường reject CORS request (ví dụ HTTP 403). Cần test trạng thái thực tế của phiên bản và filter setup, không coi Origin là authentication credential.

### 4.3. Filter khác CORS trên HandlerMapping

CORS của Spring MVC cũng có thể được định nghĩa ở `HandlerMapping` qua `@CrossOrigin` và `WebMvcConfigurer#addCorsMappings`. Nhưng nếu Spring Security filter chain chặn preflight trước khi request vào MVC, policy đặt ở handler mapping có thể chưa được áp dụng đúng lúc. `CorsFilter` hoặc Security CORS integration xử lý sớm hơn là giải pháp.

**Chọn một nơi chủ đạo để quản lý policy**, thay vì đồng thời tự đăng ký `CorsFilter`, dùng `http.cors(...)` và thêm nhiều `@CrossOrigin("*")` mà không kiểm soát cách chúng kết hợp. Cấu hình chồng chéo có thể tạo duplicate ACAO headers, sai response hoặc mở quyền ngoài dự định.

## 5. allowedOrigins: danh sách origin chính xác

`CorsConfiguration#setAllowedOrigins(...)` được dùng khi bạn biết các frontend origins được cho phép:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173"
));
~~~

**Origin gồm scheme + host + port**. `http://localhost:5173` không tự bao gồm `http://localhost:3000`. Tương tự `https://example.com` không tự cho phép `https://app.example.com`.

### 5.1. Allowed origins hợp lệ và không hợp lệ

| Giá trị cấu hình | Diễn giải |
| --- | --- |
| `https://app.example.com` | Cho phép đúng origin app |
| `http://localhost:5173` | Cho phép frontend local dev đúng port |
| `https://app.example.com:8443` | Cho phép đúng HTTPS host và port 8443 |
| `*` | Wildcard origin khi policy không dùng credentialed mode |
| `https://*.example.com` trong **allowedOrigins** | **Không phải** cú pháp wildcard hostname theo cách `allowedOriginPatterns` |
| `https://app.example.com/path` | Sai ý niệm: origin không có path |
| `https://app.example.com, https://admin.example.com` trong một HTTP ACAO header | Không phải định dạng ACAO chứa nhiều origins |

Spring có thể hỗ trợ chuỗi cấu hình phân tách bằng dấu phẩy trong `setAllowedOrigins(...)`, thuận tiện khi resolve property placeholder. Nhưng **HTTP header `Access-Control-Allow-Origin` chỉ nên biểu thị một origin được chọn hoặc `*`**, không trả danh sách CSV.

### 5.2. Không dùng prefix, contains hoặc suffix checks tự chế

Phản ví dụ:

~~~java
// Không phải cách kiểm origin an toàn.
if (origin.startsWith("https://app.example.com")) {
    response.setHeader("Access-Control-Allow-Origin", origin);
}
~~~

Giá trị `https://app.example.com.attacker.test` cũng bắt đầu bằng chuỗi trên nhưng là host khác. Các lỗi tương tự xuất hiện khi dùng `contains("example.com")`, regex không anchor đúng hoặc so domain mà bỏ scheme/port.

Dùng Spring `CorsConfiguration` với **exact origins** hoặc patterns được duyệt bảo mật. Với multi-tenant hoặc dynamic trusted origins, cần chính sách cho phép rõ ràng, kiểm soát danh tính/ownership của origin đã đăng ký và tránh attacker tự đăng ký một origin để đọc dữ liệu nhạy cảm của tenant khác.

### 5.3. Default deny và applyPermitDefaultValues

Một instance `new CorsConfiguration()` **mặc định chưa cho phép origins nào**, bạn phải cấu hình. Tuy nhiên:

~~~java
cors.applyPermitDefaultValues();
~~~

áp dụng một bộ giá trị mặc định tương đối rộng cho những field chưa được đặt: origin `*`, methods GET/HEAD/POST, allowed headers `*`, max age 1800 giây. Với API nhạy cảm, **đừng gọi method này mà chưa hiểu defaults**; nên thiết lập từng trường theo nhu cầu.

## 6. allowedOriginPatterns: wildcard hostname/port có điều kiện

Spring cung cấp:

~~~java
cors.setAllowedOriginPatterns(List.of(
        "https://*.example.com",
        "http://localhost:[5173,3000]"
));
~~~

`allowedOriginPatterns` hỗ trợ pattern theo hostname và port. Ví dụ Javadoc của Spring Framework 6.2:

~~~text
https://*.example.com
https://*.example.com:[8080,8081]
https://*.example.com:[*]
~~~

Lưu ý ví dụ `http://localhost:[5173,3000]` chỉ phù hợp nếu tất cả các origin dev này được phép; đừng dùng `:[*]` cho production nếu bạn muốn giới hạn port. Kiểm tra policy thực tế theo exact scheme/host/port và bộ test allow/deny.

### 6.1. Tại sao allowedOriginPatterns dùng được với credentials?

Khi request Origin khớp một pattern, Spring trả:

~~~http
Access-Control-Allow-Origin: https://tenant-a.example.com
~~~

thay vì trả wildcard pattern `https://*.example.com` hoặc `*`. Vì vậy `allowedOriginPatterns` có thể kết hợp với `allowCredentials(true)` về mặt API.

Tuy nhiên, đây chỉ giải quyết **định dạng ACAO**, không giải quyết **độ tin cậy của origin**. Nếu attacker có quyền kiểm soát `evil.example.com`, pattern `https://*.example.com` cũng có thể cho phép attacker-origin nếu nó match. Điều này có thể tạo khả năng đọc response credentialed trong browser của người dùng, tùy cookie và các kiểm soát khác.

### 6.2. allowedOriginPatterns("*") nguy hiểm thế nào?

~~~java
cors.setAllowedOriginPatterns(List.of("*"));
cors.setAllowCredentials(true);
~~~

Cấu hình này có thể qua được kiểm tra wildcard vốn áp dụng cho `allowedOrigins("*")`, vì Spring **echo actual matched origin** vào ACAO. Nhưng nó thực tế mở **credentialed CORS** tới nhiều origin không xác định, một rủi ro đặc biệt lớn nếu API dùng cookie session.

**Kết luận:** “Spring chấp nhận cú pháp” không đồng nghĩa “an toàn”. Với dữ liệu người dùng, ưu tiên explicit allowlist, chính sách kiểm soát tenant domain và tests cho origin độc hại.

### 6.3. Wildcard không nên thay thế trust policy

Rủi ro thường bị bỏ quên:

- Người ngoài có thể đăng ký tên miền phụ trong tổ chức thông qua dịch vụ tạo subdomain.
- DNS takeover khiến subdomain cũ trở thành host do attacker kiểm soát.
- Môi trường preview deployments có URLs không cố định nhưng cũng không phải origin đáng tin cho dữ liệu production.
- Một wildcard có thể cho cả origin HTTPS/HTTP hoặc nhiều ports nếu pattern không giới hạn chặt.
- Domain có Unicode/punycode/uppercase/port đặc biệt; tự so sánh chuỗi thủ công dễ sai.

Khi cần origin động theo tenant, lưu một allowlist có kiểm duyệt và chuẩn hóa origin chính xác; không dùng `allowedOriginPatterns("*")` để tránh quản trị danh sách.

## 7. Credentials: cookie, authentication và trình duyệt

`CorsConfiguration#setAllowCredentials(true)` điều khiển việc CORS response có thể cho browser expose kết quả của request sử dụng credentials.

Ví dụ frontend:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const me = await response.json();
~~~

Server thường cần:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không** dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser sẽ không cho script đọc credentialed response. Spring `CorsConfiguration#validateAllowCredentials()` kiểm tra quy tắc wildcard origin tương ứng.

### 7.1. CORS credentials không phải login

Bật `allowCredentials(true)` **không tự xác thực user**, không tự set cookie và không cho một trang ngoại lai quyền gọi API nếu authorization backend từ chối. Nó chỉ là một phần của cơ chế browser chia sẻ response.

Bạn vẫn cần:

- Authentication (session, JWT, OIDC, v.v.) và authorization kiểm tra quyền theo user/resource/tenant.
- CSRF protection nếu browser có cookie/session auth cho các thao tác thay đổi trạng thái.
- Cookie policy `Secure`, `HttpOnly`, `SameSite`, Domain và Path thích hợp.
- TLS/HTTPS cho production.
- CORS allowlist đủ hẹp và có quy trình review.

### 7.2. Cookie có được gửi không?

`fetch(..., {credentials:"include"})` chỉ **cho phép** browser gửi cookies hợp lệ theo điều kiện. Cookie thật sự được gửi còn phụ thuộc domain/path, Secure, SameSite, third-party cookie blocking/partitioning và chính sách trình duyệt.

| Tình huống | Điểm cần nhớ |
| --- | --- |
| `app.example.com` gọi `api.example.com` | Cross-origin, thường same-site nếu scheme thống nhất |
| `app.example.com` gọi `api.other.test` | Cross-origin và cross-site |
| Cookie `SameSite=Lax` | Không đương nhiên được gửi trong cross-site fetch |
| Cookie `SameSite=None; Secure` | Thường là yêu cầu cho một số cross-site cookie flows, vẫn chịu browser policies |
| `credentials: "same-origin"` mặc định của fetch | Không tự gửi credentials tới một origin khác |
| `credentials: "include"` | Cho phép gửi credentials theo browser cookie rules |

CORS headers đúng nhưng cookie không được gửi dẫn đến backend 401; console có thể báo CORS nếu 401 response không có headers CORS hợp lệ. Phải debug đồng thời **cookie transmission**, **server authorization** và **CORS response**.

### 7.3. Cookie session + CORS không chống CSRF

Cross-origin form submissions hoặc những request không cần preflight vẫn có thể gây thao tác thay đổi trạng thái nếu server dựa vào cookie mà thiếu CSRF protection. CORS chủ yếu quản lý **quyền đọc response**, không thay cơ chế chống CSRF.

Đừng tắt CSRF cho mọi POST chỉ vì frontend SPA gọi API. Với cookie/session authentication, sử dụng CSRF token và cookie policies hợp lý; nếu ứng dụng dùng bearer token trong header do frontend kiểm soát, bề mặt CSRF khác nhưng vẫn cần phân tích thiết kế.

### 7.4. Preflight không cần authenticated session

CORS preflight thường không mang cookies của actual request. Nếu security filter chain yêu cầu đăng nhập ngay với OPTIONS, preflight nhận 401/403 trước khi controller chạy và actual POST không bao giờ được gửi.

Do đó **CORS processing phải chạy trước security authentication checks**. Spring Security hỗ trợ tích hợp sẵn khi cung cấp `CorsConfigurationSource` và kích hoạt `http.cors(...)`. Không giải quyết bằng cách bỏ mọi policy xác thực hoặc mở toàn bộ OPTIONS tùy tiện.

## 8. Wildcards trong methods, headers và exposeHeaders

Các dấu `*` ở các thuộc tính khác nhau **không có cùng ý nghĩa**.

| Thuộc tính | Ví dụ | Ý nghĩa | Khuyến nghị |
| --- | --- | --- | --- |
| `allowedOrigins` | `*` | Cho phép mọi origin, không dùng với credentials=true | Public non-credentialed resources nếu thực sự muốn public |
| `allowedOriginPatterns` | `https://*.example.com` | Match origins theo hostname/port pattern | Chỉ nếu toàn bộ host match được tin cậy |
| `allowedOriginPatterns` | `*` | Pattern match origin rất rộng và có thể echo origin | Không dùng cho cookie-based private APIs |
| `allowedMethods` | `GET,POST` | Actual methods được phép cho CORS | Liệt kê methods thật sự cần |
| `allowedMethods` | `*` | Spring có thể reflect requested method theo preflight, nhất là credentials mode | Tránh nếu methods có rủi ro cao |
| `allowedHeaders` | `Content-Type,Authorization` | Script được phép gửi các request headers tương ứng | Allowlist rõ |
| `allowedHeaders` | `*` | Có thể reflect requested headers theo Spring handling trong credentials mode | Không nên mở vô điều kiện |
| `exposedHeaders` | `X-Request-ID` | Cho JavaScript đọc response header ngoài safelist | Chỉ expose headers cần thiết |
| `exposedHeaders` | `*` | Có hành vi/spec/browser caveats khi credentials bật | Liệt kê tường minh để portable |
| `maxAge` | `1800` | Preflight cache lifetime (giây), browser có thể áp trần | Dùng khi policy tương đối ổn định |

**Điểm tinh tế của Spring:** với `allowedMethods("*")` hoặc `allowedHeaders("*")` và credentials enabled, Spring có thể ghi lại chính method/headers được yêu cầu trong preflight response, thay vì nguyên literal `*`. Với `exposedHeaders("*")`, Spring Framework có thể vẫn phát header literal `*` kể cả khi credentials bật do ràng buộc thời điểm xây dựng response headers. Tuy nhiên theo semantics CORS/Fetch và khác biệt trình duyệt, đừng dựa vào wildcard expose trong credentialed flows; dùng tên headers cụ thể.

Không để danh sách `allowedHeaders` bị hiểu là **authorization field allowlist**: nó chỉ kiểm soát browser có thể gửi một request header; backend vẫn phải validate content, token, scopes và business permissions.

### 8.1. Cấu hình cụ thể an toàn hơn

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "Authorization", "X-Request-ID"));
cors.setExposedHeaders(List.of("X-Request-ID", "Location"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);
cors.validateAllowCredentials();
~~~

Ở đây việc `allowCredentials(true)` có thể phù hợp nếu bạn thực sự cần cookie credentials và origin đã được bảo đảm tin cậy. Với API public/không cookie, có thể đặt `allowCredentials(false)` hoặc không bật tính năng này.

### 8.2. allowPrivateNetwork và private network access

Spring Framework 6.2 có `setAllowPrivateNetwork(...)` cho các user agents áp dụng những quy tắc hạn chế truy cập mạng private/local. Đây là **vùng chính sách bổ sung**, không phải flag chung dùng để sửa mọi lỗi localhost. Spring có validation riêng ngăn `allowedOrigins("*")` kết hợp không an toàn khi bật private-network permission.

Nếu cần cho origin công khai gọi API trên private network, phải phân tích SSRF-like browser pivots, mức tin cậy của origin, trình duyệt hỗ trợ và threat model. Không thêm `allowPrivateNetwork(true)` cùng wildcard chỉ để preflight qua được.

## 9. CorsFilter và cấu hình URL-based

Một cấu hình bằng Java thuần:

~~~java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "Authorization"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);

UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", cors);

CorsFilter corsFilter = new CorsFilter(source);
~~~

Đoạn này là **fragment** minh họa tạo object; nếu đặt thành `@Bean` trong Spring Boot servlet app, filter được đăng ký vào filter chain theo cách cấu hình tương ứng.

### 9.1. Vì sao giới hạn URL paths?

Một ứng dụng có thể có:

~~~text
/api/public/**
/api/account/**
/api/admin/**
/actuator/**
/internal/**
~~~

Không nên áp dụng một wildcard policy như nhau cho tất cả. Ví dụ:

- Public API có thể cho phép một vài origins không credentialed.
- API tài khoản dùng session cần explicit trusted origins và credentials policy.
- Admin API cần allowlist chặt, authentication/authorization và CSRF policy.
- Actuator/admin nội bộ không nên mặc nhiên nhận CORS từ `/**`.
- Endpoints nội bộ thường không cần cho browser origins bất kỳ đọc.

Khi dùng `UrlBasedCorsConfigurationSource`, có thể đăng ký **các path patterns khác nhau** với cấu hình khác nhau. Đảm bảo thứ tự/độ cụ thể và pattern matching phù hợp; test URL đúng path và URL ngoài phạm vi. Nếu proxy rewrite path, so policy với path backend thấy thật.

### 9.2. Có cần FilterRegistrationBean không?

Spring Boot servlet có thể tự đăng ký một bean `Filter` thành Servlet filter. Với yêu cầu ordering/dispatcher types/URL patterns riêng, có thể dùng `FilterRegistrationBean<CorsFilter>` **thay vì** để bean CorsFilter tự đăng ký theo cách không kiểm soát.

Ví dụ minh họa:

~~~java
@Bean
FilterRegistrationBean<CorsFilter> corsRegistration(
        UrlBasedCorsConfigurationSource source) {
    FilterRegistrationBean<CorsFilter> reg =
            new FilterRegistrationBean<>(new CorsFilter(source));
    reg.setOrder(Ordered.HIGHEST_PRECEDENCE);
    reg.addUrlPatterns("/api/*");
    return reg;
}
~~~

Cần imports `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.core.Ordered`, `org.springframework.context.annotation.Bean`. Nếu chọn cách này, hãy tránh đăng ký **thêm một bean CorsFilter khác** làm filter chạy hai lần; chỉ đăng ký một path phù hợp và test request filter order.

### 9.3. Không bỏ qua ERROR/ASYNC dispatch

`CorsFilter` kế thừa cơ chế `OncePerRequestFilter`. Tùy filter registration và Servlet dispatch type, hành vi trên `REQUEST`, `ASYNC`, `ERROR` có thể khác. Nếu response 500 được xử lý ở ERROR dispatch và ACAO không có, browser có thể chỉ thấy lỗi CORS thay vì body lỗi. Khi có async/streaming/security/proxy, cần integration tests trên embedded server để xác định CORS headers vẫn áp dụng an toàn.

Không tùy tiện thêm ACAO bằng tay ở nhiều điểm (filter, error handler, reverse proxy) vì response có thể chứa header trùng hoặc không tương thích.

## 10. Ba chiến lược tích hợp CORS trong Spring Boot

### 10.1. Chỉ Spring MVC (không Spring Security)

Với ứng dụng Servlet MVC đơn giản, có thể chọn:

- `@CrossOrigin` ở controller/method; hoặc
- `WebMvcConfigurer#addCorsMappings` cho nhóm URL; hoặc
- `CorsFilter` với `UrlBasedCorsConfigurationSource` khi muốn xử lý CORS ở servlet filter boundary.

Các cách đều có thể hợp lệ tùy nhu cầu. Nhưng nếu bạn đang học `CorsFilter`, hãy triển khai rõ một filter và tập trung kiểm thử policy thay vì cấu hình đủ cả ba.

### 10.2. Có Spring Security: ưu tiên Security CORS integration

Spring Security hướng dẫn cung cấp bean `UrlBasedCorsConfigurationSource` và bật CORS integration để CORS xử lý trước các security checks cần authentication:

~~~java
@Configuration
class SecurityCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
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
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
~~~

Imports cần dùng:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
~~~

Fragment này là **phương án thay thế độc lập**, không thêm cạnh cấu hình `CorsFilter` runnable ở mục 11. Cần dependency `spring-boot-starter-security`, authentication config và CSRF token flow phù hợp nếu dùng cookie session. Không sao chép snippet này như một cấu hình security production hoàn chỉnh.

Quan trọng: **không đăng ký cùng một CorsFilter bean global lẫn cấu hình `http.cors(...)` khác nhau** mà không hiểu thứ tự và trách nhiệm xử lý. Hãy dùng một `CorsConfigurationSource` chính thống, kiểm tra preflight trong security filter chain, 401/403 có CORS headers và không mở rộng CORS tùy tiện.

### 10.3. Khi gateway xử lý CORS

Một gateway/CDN có thể xử lý preflight và ACAO trước khi request tới Spring. Nếu gateway là nơi chủ đạo quản lý CORS, backend cần hiểu chính sách này và không phát ACAO trùng. Nhưng backend vẫn cần authentication/authorization riêng; đừng dùng việc gateway đã cho ACAO làm tín hiệu user đã được tin cậy.

Cần test toàn bộ request path từ browser qua gateway tới backend, đặc biệt khi gateway trả 502/503/504 hoặc khi app trả 401/403, vì các response này cũng cần chính sách CORS nhất quán nếu frontend được phép đọc chi tiết lỗi.

## 11. Dự án chạy được: CorsFilter, credentials và origins allowlist

Ứng dụng demo:

- Spring Boot 3.5.0, Java 17+, Maven.
- Backend chạy tại `http://localhost:8080`.
- Frontend demo chạy ở `http://localhost:5173`; cho phép thêm origin `https://app.example.com`.
- Chỉ URL `/api/**` có CORS policy này.
- Không dùng `@CrossOrigin` hay `WebMvcConfigurer#addCorsMappings` để tránh double configuration.
- Bật `allowCredentials(true)` để chứng minh ACAO **đúng origin** và `Access-Control-Allow-Credentials: true`. **Demo không có login/cookie**, nên điều này không biến API thành authenticated application; xem lưu ý bảo mật bên dưới.
- Có GET `/api/hello`, POST JSON `/api/echo`, custom response header `X-Request-ID` và tests.

### 11.1. Cấu trúc

~~~text
cors-filter-demo/
├── pom.xml
├── src/
│   ├── main/java/demo/CorsFilterApplication.java
│   └── test/java/demo/CorsFilterApiTest.java
└── web-client/
    └── index.html
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cors-filter-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

### 11.3. CorsFilterApplication.java

Lưu toàn bộ Java dưới đây vào `src/main/java/demo/CorsFilterApplication.java`. Chỉ một class public ở cấp top-level; các class/record còn lại package-private nên Java cho phép đặt chung file.

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

@SpringBootApplication
public class CorsFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsFilterApplication.class, args);
    }
}

@Configuration
class CorsFilterConfig {
    @Bean
    CorsFilter corsFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
                "http://localhost:5173",
                "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type",
                "Authorization",
                "X-Request-ID"
        ));
        cors.setExposedHeaders(List.of("X-Request-ID", "Location"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        // Fail fast với tổ hợp wildcard origins và credentials sai.
        cors.validateAllowCredentials();

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsFilter(source);
    }
}

record EchoRequest(String message) {
}

record EchoResponse(String echo) {
}

@RestController
@RequestMapping("/api")
class DemoApiController {
    @GetMapping(path = "/hello",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, String>> hello() {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(Map.of("message", "Hello from Spring MVC"));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<EchoResponse> echo(
            @RequestBody EchoRequest request) {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new EchoResponse("Echo: " + request.message()));
    }
}
~~~

**Vì sao config như vậy?**

- `CorsFilter` là bean Spring Boot tự đăng ký trong servlet environment; bạn không phải tự viết `OPTIONS` controller.
- `UrlBasedCorsConfigurationSource` chỉ áp dụng policy cho `/api/**`, không mặc nhiên cho Actuator/admin/internal endpoints.
- `setAllowedOrigins(...)` chứa **hai origins chính xác**, không chứa wildcard.
- `allowCredentials(true)` làm response cần ACAO theo một matched origin cụ thể, cộng `Access-Control-Allow-Credentials: true`.
- `setAllowedMethods(List.of("GET","POST"))` đủ cho actual GET/POST; preflight method OPTIONS không cần thêm vào list.
- `setAllowedHeaders` cho phép JSON Content-Type và hai request headers nếu frontend cần; không mở `*`.
- `setExposedHeaders` cho browser JavaScript đọc `X-Request-ID` hoặc `Location` khi response có các header ấy.
- `maxAge=1800` cho browser được cache preflight tối đa theo giới hạn trình duyệt.
- `validateAllowCredentials()` giúp phát hiện cấu hình không hợp lệ sớm. Khi thay origins bằng `*` đồng thời giữ credentials true, ứng dụng không nên khởi động thành công với policy đó.

**Quan trọng:** Demo có `allowCredentials(true)` để quan sát CORS response semantics, nhưng API hoàn toàn **không có đăng nhập hay dữ liệu private**. Khi triển khai API thực tế, chỉ bật credentials nếu origin đã được tin cậy và authentication/authorization/CSRF/cookie policies đã được thiết kế đầy đủ.

### 11.4. Frontend thử nghiệm web-client/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>CorsFilter demo</title>
</head>
<body>
  <h1>Test CORS credentials + allowlist</h1>
  <button id="get">GET /api/hello</button>
  <button id="post">POST JSON /api/echo</button>
  <pre id="result"></pre>
  <script>
    const base = "http://localhost:8080";
    const output = document.querySelector("#result");

    async function request(path, options = {}) {
      try {
        const response = await fetch(base + path, {
          credentials: "include",
          ...options
        });
        const requestId = response.headers.get("X-Request-ID");
        const body = await response.json();
        output.textContent = JSON.stringify({
          httpStatus: response.status,
          requestId,
          body
        }, null, 2);
      } catch (error) {
        output.textContent =
          "Không đọc được response: " + error.message
          + ". Xem DevTools Network/Console.";
      }
    }

    document.querySelector("#get").onclick = () =>
      request("/api/hello");

    document.querySelector("#post").onclick = () =>
      request("/api/echo", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: "Xin chào"})
      });
  </script>
</body>
</html>
~~~

Mặc dù `credentials: "include"` được khai báo, demo không tạo cookie hoặc session. Do đó bạn đang kiểm tra **CORS response có cho phép credentials mode** chứ chưa kiểm thử đăng nhập thực tế. Nếu tích hợp cookie session sau này, cần xem xét `SameSite`, CSRF tokens, browser third-party cookie policy và Spring Security.

### 11.5. Khởi chạy

Terminal 1 tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Terminal 2:

~~~bash
python -m http.server 5173 --directory web-client
~~~

Mở browser:

~~~text
http://localhost:5173
~~~

Trong DevTools/Network:

1. GET /api/hello thường gửi actual GET không preflight khi không có custom request headers.
2. POST JSON /api/echo thường gửi OPTIONS preflight trước actual POST.
3. Headers trả về chứa ACAO đúng `http://localhost:5173`, ACAC true, và `Access-Control-Expose-Headers` cho X-Request-ID.
4. Đổi frontend sang cổng khác (ví dụ 5174) mà không đổi allowed origins: cross-origin script từ đó sẽ bị từ chối.

Response GET tương đương:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Response POST tương đương:

~~~json
{"echo":"Echo: Xin chào"}
~~~

UUID của X-Request-ID thay đổi theo mỗi actual API request. Response preflight được filter xử lý trước controller nên không tự mang X-Request-ID do controller tạo; đây là hành vi mong đợi của demo.

### 11.6. Curl: phân biệt actual và preflight

Actual request từ trusted origin:

~~~bash
curl -i 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173'
~~~

Header điển hình:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID, Location
Vary: Origin
Content-Type: application/json
~~~

Preflight JSON POST:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Preflight thành công có thể nhận:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Dấu phẩy/casing/thứ tự headers có thể thay đổi tùy Spring/container; không so raw HTTP text để xác định policy đúng.

Dùng origin không nằm trong allowlist:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

`DefaultCorsProcessor` của Spring Framework 6.2 thường trả **403 Invalid CORS request**. Browser sẽ không gửi actual POST nếu preflight bị từ chối. Nhưng `curl` vẫn in HTTP response dù không có ACAO vì curl không thực thi SOP.

### 11.7. MockMvc kiểm thử allowlist, credentials và wildcard limitations

File `src/test/java/demo/CorsFilterApiTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.cors.CorsConfiguration;

import java.util.List;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsFilterApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void trustedOriginCanReadActualResponseWithCredentials() throws Exception {
        mvc.perform(get("/api/hello")
                .header("Origin", "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"))
            .andExpect(header().string(
                    "Access-Control-Expose-Headers",
                    containsString("X-Request-ID")))
            .andExpect(jsonPath("$.message").value("Hello from Spring MVC"));
    }

    @Test
    void secondExactTrustedOriginIsAllowed() throws Exception {
        mvc.perform(get("/api/hello")
                .header("Origin", "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "https://app.example.com"));
    }

    @Test
    void requestsWithoutOriginStillWork() throws Exception {
        mvc.perform(get("/api/hello"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void approvedJsonPostPreflightDoesNotRunController()
            throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Methods", containsString("POST")))
            .andExpect(header().string(
                    "Access-Control-Allow-Headers",
                    containsString("content-type")))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void unapprovedMethodIsRejected() throws Exception {
        mvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unapprovedHeaderIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "X-Private-Admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    void wildcardOriginCannotBeCombinedWithCredentials() {
        CorsConfiguration invalid = new CorsConfiguration();
        invalid.setAllowedOrigins(List.of("*"));
        invalid.setAllowCredentials(true);
        assertThrows(IllegalArgumentException.class,
                invalid::validateAllowCredentials);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test phân biệt allowed origins, rejected origins, allowed methods/headers và validation của wildcard configuration. Test preflight xác nhận giao thức CORS xử lý trước actual controller flow; code controller chỉ có GET và POST nên không có business OPTIONS handler.

**Hạn chế:** MockMvc không thay thế browser khi kiểm thử actual cookie policies, third-party cookie restrictions, CSRF/authentication filters và gateway. Để kiểm thử production, bổ sung embedded-server/browser E2E với cookies và Spring Security.

## 12. Nếu muốn dùng allowedOriginPatterns trong thực tế

Giả sử toàn bộ subdomains của `trusted.example.com` thật sự do cùng tổ chức kiểm soát:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.com"
));
cors.setAllowedMethods(List.of("GET"));
cors.setAllowedHeaders(List.of("Authorization"));
cors.setAllowCredentials(true);
~~~

Spring sẽ trả ACAO theo **matched request Origin**. Điều này có thể phù hợp cho host nội bộ do tổ chức sở hữu, nhưng chỉ sau khi đánh giá domain takeover, tenant isolation và cookies.

### 12.1. Test pattern trực tiếp

Dùng `CorsConfiguration#checkOrigin` để xác minh:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.com"));
config.setAllowCredentials(true);

String matched =
        config.checkOrigin("https://team.trusted.example.com");
String rejected =
        config.checkOrigin("https://attacker.example");
~~~

Ở đây `matched` thường là giá trị origin cụ thể, còn `rejected == null`. Đây là **fragment** trong class/method có imports Java phù hợp, không phải chương trình độc lập. Nếu business policy cần host chính xác, vẫn nên chọn `setAllowedOrigins` thay vì patterns.

### 12.2. Không hiểu nhầm allowOriginPatterns với allowCredentials=false

Một số developer chuyển sang `allowedOriginPatterns` chỉ để tránh lỗi cấu hình wildcard, dù API không cần credentials. Nếu API thực sự là public non-credentialed resource, `allowedOrigins("*")` có thể là một lựa chọn có chủ ý; nếu API private, dùng explicit origins theo trust boundary. Không nên dùng pattern phức tạp chỉ vì “Spring hỗ trợ”.

### 12.3. Multiple trusted origins

Một API có frontend user và admin riêng:

~~~java
cors.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com"
));
~~~

Spring đánh giá `Origin` đến và phản hồi bằng **một matched origin**, không trả một ACAO header là chuỗi CSV của hai origins. Nếu phản hồi vary theo origin, cần `Vary: Origin` để CDN/proxy không cache sai ACAO.

Đặc biệt, nếu admin page có authentication/authorization riêng, việc cho origin admin trong allowlist vẫn không khiến user thường có quyền đọc admin data.

## 13. Debug CORS và các lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| “CORS policy blocked”, Network hiện 200 | Actual response thiếu/sai ACAO | So Origin và ACAO, status/body |
| OPTIONS trả 401/403 rồi không có POST | CORS filter xử lý sau Security hoặc allowlist sai | Filter order, `http.cors(...)`, headers preflight |
| Lỗi khi bật `allowCredentials(true)` với origin `*` | Cấu hình wildcard không hợp lệ | Dùng exact origins hoặc pattern được kiểm duyệt |
| Trình duyệt báo wildcard ACAO không hợp lệ với cookie | ACAO `*` + credentialed fetch | Trả matched origin + ACAC true |
| HTTP 200 nhưng JS không đọc `X-Request-ID` | Thiếu `Access-Control-Expose-Headers` | Expose đúng header |
| GET chạy, POST JSON thất bại | POST có preflight, config thiếu POST/Content-Type | Kiểm OPTIONS preflight |
| GET từ local 5173 chạy, local 5174 thất bại | Khác origin do port | Add đúng trusted dev origin khi cần |
| CORS đúng nhưng /api/me trả 401 | Cookie/token không gửi/invalid | Credentials mode, SameSite, auth logs |
| CORS lỗi khi backend có exception 500 | Error response không có ACAO hoặc proxy trả lỗi | Kiểm backend error handling/gateway |
| CORS chập chờn sau CDN | CDN cache ACAO theo origin sai | Kiểm `Vary: Origin` và cache policy |
| Có hai ACAO headers khác nhau | Gateway + app hoặc nhiều filters tự thêm | Chọn một nơi quản lý CORS |
| Preflight lỗi khi gửi X-API-Key | Header không nằm allowedHeaders | Review policy rồi thêm header cần thiết |
| Security vẫn chặn POST sau preflight OK | Actual request cần auth/CSRF | Không nhầm preflight approval với authorization |
| `Origin: null` bị chặn | Opaque origin không được cho phép | Dùng dev HTTP server thay file:// |
| Curl đọc được dữ liệu còn JS không | Curl không thực thi SOP/CORS | Test trong browser/DevTools |

### 13.1. Thứ tự debug nên thực hiện

1. Xác định chính xác `window.location.origin` ở frontend và URL API.
2. Phân biệt request có OPTIONS hay không.
3. Nếu có OPTIONS, kiểm `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` của preflight.
4. Kiểm server trả ACAO/ACAM/ACAH/ACAC phù hợp; với credentials, ACAO phải là origin cụ thể.
5. Nếu actual request đã tới server, kiểm HTTP status/backend logs/response ACAO. Một backend 500 không phải “đơn thuần lỗi CORS”.
6. Kiểm fetch credentials mode và cookie policy nếu sử dụng session.
7. Kiểm URL path matching `/api/**` và tình trạng nhiều CORS configurations.
8. Nếu bật Security, đảm bảo CORS processing trước authentication của preflight; sau đó vẫn kiểm authorization/CSRF của actual request.
9. Nếu có proxy/CDN, kiểm headers có bị xóa/nhân đôi và cache đúng theo Origin không.
10. Xác minh bằng MockMvc/embedded server và browser, không chỉ bằng curl/Postman.

### 13.2. Tránh mode:"no-cors"

Phản ví dụ:

~~~javascript
fetch("https://api.example.com/private", {
  mode: "no-cors"
});
~~~

Điều này **không cấp quyền đọc JSON**. Browser thường trả **opaque response** cho script, không cho đọc body/status như một API response bình thường. Đừng coi đây là cách sửa cấu hình server.

### 13.3. Không tắt browser security để phát triển

Khởi chạy Chrome/Firefox bằng những flags vô hiệu hóa web security có thể che lỗi chính sách và tạo nguy cơ cho phiên duyệt. Nên dùng dev proxy hoặc cấu hình CORS đúng cho origin frontend.

## 14. Security review cho credentialed CORS

Với cookie-based API, hãy tự hỏi:

- CORS cho phép **những origin nào chính xác**? Ai kiểm soát DNS/domain của từng origin?
- Có subdomain nào do tenant/user tự tạo không? Có dangling DNS hay preview domains chưa kiểm soát?
- Cookies có cần cross-site không, và browser có thực sự gửi chúng không?
- CSRF token được gửi/kiểm tra như thế nào? API endpoints ghi dữ liệu có được bảo vệ?
- Các lỗi 401/403/500 có response headers CORS hợp lệ cho trusted origin mà không làm lộ thông tin?
- Có policy khác cho admin/internal endpoints không?
- Mức độ tin cậy của wildcard hostname patterns có vượt quá ranh giới bảo mật không?
- Có third-party script trong allowed frontend origin có thể đọc user-specific API data không? CORS tin tưởng **origin**, không phân biệt từng đoạn JS chạy trong origin đó.
- Có yêu cầu chống XSS/CSP ở frontend không? Nếu origin đáng tin bị XSS, attacker script cùng origin có thể được hưởng CORS permission.
- Data cần bảo vệ có bị cache shared bởi CDN sau khi response có ACAO/ACAC không? Cần Cache-Control riêng.
- Có một quy trình thay đổi allowed origins, logging và audit thay vì để client tự đăng ký origin không kiểm chứng không?

CORS đúng chỉ là một lớp trong hệ thống bảo mật. Đặc biệt với `allowCredentials(true)`, hãy xem việc cho thêm một origin như **mở rộng trust boundary** cần review.

## 15. Bài tập tự luyện

**Bài 1 — Allowed origins:** Trang `https://app.example.com` gọi API `https://api.example.com`. Viết `CorsConfiguration` chỉ cho phép app, HTTP methods GET/POST, Content-Type/Authorization và không dùng wildcard. Tại sao `https://app.example.com.attacker.test` không được phép?

**Bài 2 — Wildcard credentials:** Giải thích tại sao `allowedOrigins("*") + allowCredentials(true)` bị từ chối và tại sao thay bằng `allowedOriginPatterns("*") + allowCredentials(true)` có thể chạy nhưng không an toàn.

**Bài 3 — Domain pattern:** Tổ chức có `a.trusted.example.com`, `b.trusted.example.com` nhưng có một subdomain do user tạo. Bạn có nên dùng `https://*.trusted.example.com` cho credentialed CORS không? Đề xuất exact allowlist.

**Bài 4 — Preflight:** Frontend POST JSON có Authorization header. Viết OPTIONS request với Origin, Access-Control-Request-Method và Access-Control-Request-Headers. Phân biệt method OPTIONS với actual POST trong allowedMethods.

**Bài 5 — Security:** CORS preflight trả 401 khi Spring Security có session authentication. Giải thích vì sao preflight không có cookie và viết cấu hình `http.cors(Customizer.withDefaults())` + `CorsConfigurationSource` để xử lý đúng thứ tự.

**Bài 6 — Cookies:** Vì sao `fetch(credentials:"include")` + ACAO/ACAC đúng vẫn có thể nhận 401? Phân tích SameSite, Secure, Domain, Path và browser third-party cookie policy.

**Bài 7 — Expose headers:** API trả X-Request-ID nhưng `response.headers.get("X-Request-ID")` là null. Bạn cần cấu hình nào ở server? Nó có làm X-Request-ID trở thành request header được phép gửi không?

**Bài 8 — Test:** Viết MockMvc preflight tests cho allow origin `http://localhost:5173`, deny `https://evil.example`, POST được phép và DELETE bị từ chối.

**Bài 9 — Error responses:** Một origin hợp lệ nhận lỗi 500 từ upstream nhưng browser chỉ báo CORS. Những tầng nào có thể làm mất ACAO? Tại sao mở ACAO "*" không phải sửa lỗi thực?

**Bài 10 — Architect:** Thiết kế policy cho `/api/public/**` (không credentials), `/api/account/**` (credentials + exact origins) và `/api/admin/**` (allowlist chặt + authorization). Chọn CorsFilter/MVC/Security integration sao cho policy không chồng chéo.

## 16. Tổng kết

- **`CorsFilter`** xử lý CORS ở Servlet filter boundary thông qua `CorsConfigurationSource` và `CorsProcessor`; thường phù hợp khi muốn CORS xử lý sớm, đặc biệt trước Spring Security.
- **`allowedOrigins`** nên liệt kê các origins chính xác (scheme, host, port). Không dùng `"*"` khi `allowCredentials(true)`.
- **`allowedOriginPatterns`** hỗ trợ wildcard hostname/port, có thể được dùng với credentials vì Spring echo origin khớp; nhưng pattern quá rộng có thể mở ra rủi ro lớn.
- **Credentials không phải authentication**, và CORS không thay CSRF protection, authorization hoặc cookie security.
- **Wildcards trong methods/headers/exposedHeaders** có quy tắc khác wildcard origins; ưu tiên allowlist rõ để giảm bất ngờ về semantics/browser.
- **Preflight OPTIONS** phải được xử lý trước xác thực; actual request vẫn phải đi qua authentication/authorization/CSRF thích hợp.
- Trong dự án Spring MVC, nên có **một chính sách CORS có ownership rõ**, kiểm thử positive/negative origins, methods, headers, credentials và các responses lỗi.
- Khi browser báo CORS error, hãy kiểm cả network, status, cookies, security filter chain và proxy — không chỉ thêm `@CrossOrigin("*")`.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html).
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): `allowedOrigins`, `allowedOriginPatterns`, `allowCredentials` và validation.
- [Spring Framework 6.2 — CorsFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/CorsFilter.html).
- [Spring Framework 6.2 — DefaultCorsProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/DefaultCorsProcessor.html).
- [Spring Security — CORS Servlet Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html).
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, headers, credentials.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin).
- [WHATWG Fetch Standard](https://fetch.spec.whatwg.org/): normative CORS protocol, credentials và response tainting.
