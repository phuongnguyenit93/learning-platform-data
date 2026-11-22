# allowCredentials, origin cụ thể và giới hạn của ký tự đại diện

## Mục tiêu học tập

Bài này thuộc nhóm **Cấu hình CORS** của **Spring Security reactive / WebFlux**. Sau bài học, bạn có thể:

- Giải thích đúng **origin** (scheme + hostname + port), phân biệt **same-origin** với **same-site** và biết vì sao hai ứng dụng trên `localhost` nhưng khác port vẫn là cross-origin.
- Hiểu tác dụng của `CorsConfiguration.setAllowCredentials(true)` và header `Access-Control-Allow-Credentials: true` đối với request chứa **cookie, HTTP authentication và các browser credentials**.
- Phân biệt `allowedOrigins` (danh sách origin chính xác) với `allowedOriginPatterns` (mẫu origin có điều kiện) và giới hạn nghiêm ngặt của giá trị `"*"` khi bật credentials.
- Đọc và giải thích preflight `OPTIONS` với `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` cùng những header đáp ứng CORS.
- Cấu hình CORS trong **`SecurityWebFilterChain` reactive** bằng `CorsConfiguration` và `UrlBasedCorsConfigurationSource`, để preflight chạy **trước kiểm tra xác thực**.
- Chạy ví dụ **Java 17 + Spring WebFlux + Spring Security**, gọi API từ ứng dụng JavaScript ở origin khác và kiểm thử với `WebTestClient`/`curl`.
- Tránh lỗi dùng wildcard với credential, phản chiếu Origin tùy ý, cấu hình CORS quá rộng, quên `credentials: "include"`, nhầm CORS với CSRF và sai cookie `SameSite/Secure`.

> **Phạm vi:** Spring Security **reactive** sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`. Không áp dụng nguyên xi `HttpSecurity` hoặc `CorsFilter` của Servlet MVC. Ví dụ trong bài tách rõ mã chạy độc lập với mảnh code để minh họa lỗi hoặc cấu hình thay thế.

## 1. Trước hết: origin là gì?

Một **origin** được xác định bởi bộ ba:

~~~text
origin = scheme + hostname + port
~~~

Ví dụ:

| URL | Origin | So với `http://localhost:8080` |
|---|---|---|
| `http://localhost:8080/api/me` | `http://localhost:8080` | Same-origin |
| `http://localhost:8080/static/app.html` | `http://localhost:8080` | Same-origin (path khác không làm đổi origin) |
| `http://localhost:3000` | `http://localhost:3000` | Cross-origin vì **port khác** |
| `https://localhost:8080` | `https://localhost:8080` | Cross-origin vì **scheme khác** |
| `https://api.example.test` | `https://api.example.test` | Cross-origin |
| `https://ui.example.test` | `https://ui.example.test` | Cross-origin với `https://api.example.test` dù có thể cùng site |

**Path không thuộc origin.** Giá trị của HTTP `Origin` là scheme, host và port theo quy tắc của giao thức; không có đường dẫn `/api/me` hay query string. Port mặc định của scheme có thể được chuẩn hóa/ẩn trong cách biểu diễn.

**Same-site không bằng same-origin.** Cookie `SameSite` dùng khái niệm *site* (trong browser hiện đại là schemeful site), còn CORS dùng *origin*. Hai subdomain có thể same-site nhưng vẫn cross-origin và phải qua CORS nếu JavaScript đọc response của nhau.

### 1.1. Tại sao trình duyệt cần CORS?

**Same-Origin Policy (SOP)** hạn chế JavaScript tại origin A đọc response từ origin B. **Cross-Origin Resource Sharing (CORS)** là bộ header cho phép server tại B nói với browser rằng origin A được đọc response trong điều kiện nào.

Ví dụ trang tại `http://localhost:3000` gửi request đến backend `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/me");
const user = await response.json();
~~~

Nếu backend không gửi CORS headers cho origin UI, browser có thể chặn JavaScript truy cập response. Điều này **không có nghĩa** backend không nhận request hoặc không chạy nghiệp vụ: một số loại cross-origin request vẫn có thể được gửi. CORS chủ yếu là cơ chế **trình duyệt thực thi việc chia sẻ response**, không phải authentication, authorization hay một tường lửa mạng.

HTTP client như `curl` không tự áp dụng SOP của browser; nó có thể đọc response dù thiếu CORS headers. Vì vậy phải xem cả **response headers** và hành vi trên **browser** khi debug.

## 2. allowCredentials thật sự có nghĩa gì?

Trong Spring Framework WebFlux:

~~~java
CorsConfiguration config = new CorsConfiguration();

config.setAllowedOrigins(
    List.of("http://localhost:3000"));
config.setAllowCredentials(true);
~~~

Đây là **mảnh code trong phương thức cấu hình** với import `org.springframework.web.cors.CorsConfiguration` và `java.util.List`. Khi origin request khớp và các CORS conditions khác hợp lệ, server có thể gửi:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Đây là **trích đoạn header**; framework còn có thể gửi `Vary: Access-Control-Request-Method, Access-Control-Request-Headers` và những header khác.

**`allowCredentials(true)` không tự xác thực ai cả.** Nó cho phép CORS response được chia sẻ với JavaScript trong tình huống request có credentials theo quy tắc browser, nhưng:

- Nó **không tạo session** hay tự cấp cookie.
- Nó **không ép browser phải gửi cookie**; JavaScript còn cần cấu hình `credentials` thích hợp, cookie phải thỏa Path/Domain/SameSite/Secure và chính sách trình duyệt.
- Nó **không xác minh mật khẩu**, chữ ký JWT, session ID, role hay quyền nghiệp vụ.
- Nó **không bỏ qua CSRF**, không biến POST nguy hiểm thành an toàn.
- Nó **không quyết định ai được dùng API bằng curl/Postman**; những client không phải browser có thể không áp dụng CORS.

### 2.1. Từ góc nhìn Fetch API

Khi trang ở `http://localhost:3000` gọi backend ở `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

`credentials: "include"` cho phép browser **gửi credentials** trong cross-origin request **nếu** các cookie/credential policies khác cho phép. Đối với cross-origin, giá trị mặc định `same-origin` **không** gửi cookie của origin đích như mong muốn ở ví dụ này.

Phía backend cần đáp lại origin chính xác và `Access-Control-Allow-Credentials: true`. Nếu thiếu một trong các điều kiện, request có thể đến server nhưng browser không trao response cho JavaScript.

| Fetch credentials mode | Khi request sang origin khác | Lưu ý |
|---|---|---|
| `omit` | Không gửi credentials | Có thể dùng cho API public không phụ thuộc cookie |
| `same-origin` | Không gửi browser credentials cho cross-origin request | Đây là mặc định của `fetch` |
| `include` | Cho phép gửi theo cookie/browser policies | Không vượt được SameSite, Secure, third-party cookie blocking hoặc CORS policy |

**Không nhầm `include` với “bỏ mọi chính sách browser”.** Nếu browser chặn third-party cookies, chỉ thay `credentials` không thể khiến cookie được gửi. Nếu response không có CORS headers đúng, browser vẫn không cho JS đọc.

### 2.2. Header credentials và response

Cặp header thường gặp:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
~~~

Giá trị `true` của `Access-Control-Allow-Credentials` là chuỗi literal đúng; không có `Access-Control-Allow-Credentials: false` như giá trị thay thế có ý nghĩa tương đương. Khi không cho credentialed access, thường **không gửi header này**, không cố gửi `false`.

Không nên dựa vào `Set-Cookie` có mặt trong response để kết luận JavaScript sẽ đọc được cookie hoặc trình duyệt chấp nhận nó. Cookie còn phụ thuộc thuộc tính HttpOnly, Domain, Path, Secure, SameSite và browser policy; `Set-Cookie` là một forbidden response header name đối với JS Fetch API.

## 3. Vì sao credentials=true không được ghép với allowedOrigins("*")?

Cấu hình lỗi thường thấy:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true); // KHÔNG HỢP LỆ
~~~

Theo Spring Framework `CorsConfiguration` và CORS protocol, khi cho phép credentials, response `Access-Control-Allow-Origin` **không được có giá trị `*`**. Nếu máy chủ trả:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

browser sẽ từ chối chia sẻ response với request dùng credentials. Spring Framework cũng **không chấp nhận** tổ hợp `allowedOrigins("*")` + `allowCredentials(true)` khi kiểm tra cấu hình; có thể ném `IllegalArgumentException` trong quá trình validate/handle request tùy thời điểm sử dụng configuration.

**Cách đúng:** Khai báo origin cụ thể, hoặc dùng `allowedOriginPatterns` theo quy tắc được kiểm soát, và trả **origin thực tế đã được kiểm tra** cho request.

### 3.1. Cấu hình an toàn nhất: danh sách cố định

~~~java
config.setAllowedOrigins(List.of(
    "https://app.example.test",
    "https://admin.example.test"));
config.setAllowCredentials(true);
~~~

Nếu request đến từ `https://app.example.test`, response CORS hợp lệ có thể là:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Nếu request đến từ `https://evil.example.test`, server không nên gửi header cho phép origin đó; preflight không hợp lệ thường bị từ chối. **Không** gửi danh sách origin bằng dấu phẩy trong một `Access-Control-Allow-Origin`: header response chỉ biểu diễn **một origin cụ thể hoặc `*`**, không phải chuỗi `https://a,https://b`.

### 3.2. Khi không dùng credentials: wildcard có thể hợp lệ

Với một tài nguyên **công khai**, không cần cookies/HTTP authentication và không chứa dữ liệu cá nhân:

~~~java
CorsConfiguration publicCors = new CorsConfiguration();
publicCors.setAllowedOrigins(List.of("*"));
publicCors.setAllowedMethods(List.of("GET"));
publicCors.setAllowCredentials(false);
~~~

Spring có thể trả:

~~~http
Access-Control-Allow-Origin: *
~~~

Đó là thiết kế khác với credentialed CORS. Không ghép public origin wildcard vào endpoint dữ liệu người dùng và cho rằng role/authentication sẽ bù được mọi rủi ro chia sẻ response. Nếu API dùng Bearer token do frontend gắn thủ công, cần xác định Fetch credentials mode, cơ chế auth và dữ liệu được phép lộ; đừng vội áp dụng wildcard mà không đánh giá threat model.

## 4. allowedOrigins và allowedOriginPatterns

Hai API có tên gần giống nhưng hành vi khác nhau:

| Thuộc tính | Kỳ vọng đầu vào | Dùng với `allowCredentials(true)` | Header khi match |
|---|---|---|---|
| `setAllowedOrigins(...)` | Danh sách **origin chính xác**, hoặc literal `*` | Được với origin cụ thể; **không** với `*` | Exact origin hoặc `*` khi không credentials |
| `setAllowedOriginPatterns(...)` | Danh sách **pattern**, có wildcard ở host và port list theo cú pháp Spring | Có thể, nếu pattern được tin cậy/giới hạn | **Origin thật đã match**, không phải pattern hoặc `*` |

Ví dụ nếu cần hỗ trợ nhiều subdomain được quản lý:

~~~java
config.setAllowedOriginPatterns(List.of(
    "https://*.trusted.example.test"));
config.setAllowCredentials(true);
~~~

Khi request từ `https://shop.trusted.example.test` khớp, Spring trả:

~~~http
Access-Control-Allow-Origin: https://shop.trusted.example.test
Access-Control-Allow-Credentials: true
~~~

**Chú ý:** Đây là ví dụ minh họa pattern; nếu một subdomain bị chiếm hoặc được cấp cho người thuê không tin cậy, pattern wildcard biến origin đó thành **được phép đọc response chứa credential**, một rủi ro rất lớn. Ưu tiên allowlist hữu hạn. Không sử dụng pattern `"*"` chỉ để tránh lỗi validate của `allowedOrigins("*")` — dù API có thể tạo header cụ thể, policy lúc đó cho phép mọi origin khớp.

### 4.1. Pattern port và scheme

Spring Framework hỗ trợ các dạng pattern như:

~~~text
https://*.example.test
https://*.example.test:[8080,8443]
https://*.example.test:[*]
~~~

Đây là **dữ liệu cấu hình minh họa**. Port wildcard `[*]` có thể tiện cho local testing nhưng tăng phạm vi được cho phép; ở production nên giới hạn port thật. `https://...` không tự cấp quyền cho `http://...`; scheme nằm trong origin và phải khớp.

Không hiểu `allowedOriginPatterns` như một regex tự do nhận mọi đường dẫn URL. Nó là pattern origin theo ngữ nghĩa Spring CORS. Nếu dùng nhầm `https://*.example.test/any/path`, bạn đang đưa path vào nơi chỉ kỳ vọng origin; cần sửa.

### 4.2. “Phản chiếu Origin” đúng và sai

Một CORS processor hợp lệ có thể **trả lại** `Origin` request dưới dạng `Access-Control-Allow-Origin` **sau khi so khớp allowlist/pattern an toàn**. Đây không phải là hành vi tùy tiện.

**Sai lầm nguy hiểm:**

~~~java
// MẪU PHẢN VÍ DỤ - không dùng trong production.
String origin = exchange.getRequest().getHeaders().getOrigin();
exchange.getResponse().getHeaders()
    .set("Access-Control-Allow-Origin", origin);
exchange.getResponse().getHeaders()
    .set("Access-Control-Allow-Credentials", "true");
~~~

Đây là **mảnh code phản ví dụ**, không phải ứng dụng hoàn chỉnh. Nó tin mọi header Origin và có thể cấp cho một trang độc hại quyền đọc response chứa dữ liệu người dùng khi browser gửi credentials. Server phải đối chiếu Origin với allowlist đáng tin **trước** khi trả header tương ứng.

### 4.3. Origin null

Một số môi trường như sandboxed iframe, `file://` hoặc document có opaque origin có thể gửi `Origin: null`. Không mặc định cho phép literal `"null"` hoặc wildcard nhằm “làm CORS chạy” khi không hiểu nguồn request; điều này có thể mở quyền cho những origin không đáng tin.

## 5. Giới hạn của dấu * không chỉ nằm ở allowedOrigins

Trong Spring Framework/CORS, các chỗ xuất hiện `*` có ngữ nghĩa **khác nhau**:

| Cấu hình/header | Khi credentials=true | Điều cần nhớ |
|---|---|---|
| `allowedOrigins("*")` → `Access-Control-Allow-Origin: *` | **Không hợp lệ** | Phải trả origin cụ thể hoặc origin matched pattern |
| `allowedOriginPatterns("https://*.trusted...")` | Có thể hợp lệ | Server phát origin request đã match; nên giới hạn pattern |
| `allowedMethods("*")` | Spring có thể **chép method** yêu cầu trong preflight vào response | Không đồng nghĩa mọi method nghiệp vụ được authorization cho phép |
| `allowedHeaders("*")` | Spring có thể **chép danh sách header** yêu cầu trong preflight vào response | Nên giới hạn header được chấp nhận |
| `exposedHeaders("*")` | Có điểm tương thích liên quan browser/spec; Spring có thể phát `*` | Với credentialed API, ưu tiên danh sách cụ thể để tránh bất định |
| `Access-Control-Allow-Origin: *` trong HTTP response | Browser chặn response của credentialed request | Không khắc phục được bằng cách chỉ bật `include` trên frontend |

Spring Framework documentation giải thích rằng khi `allowCredentials=true` và `allowedHeaders` hoặc `allowedMethods` chứa `*`, Spring **echo** những header/method từ preflight thay vì nhất thiết phát literal `*`. Điều này khác với `allowedOrigins`. Còn `exposedHeaders("*")` có ngoại lệ tương thích thực tế, nên với dữ liệu nhạy cảm hãy dùng exposed-header allowlist cố định.

**Khuyến nghị:** Với hệ thống thật, hãy khai báo hữu hạn những origin, HTTP methods, request headers và response headers thực sự cần. Dấu `*` là một quyết định chia sẻ dữ liệu cần review, không phải “thao tác sửa lỗi browser”.

## 6. Preflight OPTIONS: vì sao CORS phải chạy trước Spring Security?

Trình duyệt gửi **preflight** khi request cross-origin có method hoặc header không thuộc diện CORS-safelisted, ví dụ GET kèm header `X-Client-Trace` hay POST JSON với `Content-Type: application/json`.

Request preflight có hình thức:

~~~http
OPTIONS /api/me HTTP/1.1
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-trace
~~~

Preflight chuẩn **không gửi cookie/session credentials**. Nó hỏi server rằng origin này có thể gửi GET mang header tùy biến hay không. Nếu Spring Security yêu cầu Authentication **trước** khi CORS xử lý, preflight có thể bị từ chối 401 dù actual request sẽ có session hợp lệ. Đây là lỗi cấu hình rất phổ biến.

Với cấu hình đúng, response preflight có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-client-trace
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Đây chỉ là **trích đoạn dự kiến**; status 200/204, capitalization, danh sách Vary, header ordering và cache details tùy runtime. Không có `Set-Cookie` trong preflight là bình thường; **preflight không phải lần đăng nhập**.

Nếu preflight hợp lệ, browser mới gửi **actual request**. Actual request có thể vẫn nhận 401/403 từ Authentication/Authorization hoặc bị CSRF chặn — **CORS pass không có nghĩa business API pass**.

### 6.1. Các header chính của preflight

| Header | Hướng | Vai trò |
|---|---|---|
| `Origin` | Client → Server | Origin của JavaScript khởi tạo request |
| `Access-Control-Request-Method` | Browser → Server | HTTP method muốn dùng cho actual request |
| `Access-Control-Request-Headers` | Browser → Server | Những request headers không safelisted dự kiến gửi |
| `Access-Control-Allow-Origin` | Server → Browser | Origin được phép đọc response |
| `Access-Control-Allow-Credentials` | Server → Browser | Cho phép chia sẻ response credentialed |
| `Access-Control-Allow-Methods` | Server → Browser | Những HTTP methods được phép theo CORS |
| `Access-Control-Allow-Headers` | Server → Browser | Những request headers được phép theo CORS |
| `Access-Control-Max-Age` | Server → Browser | Thời gian có thể cache quyết định preflight, browser có giới hạn |
| `Vary` | Server → Cache | Cần phân biệt response dựa trên Origin/method/headers khi policy thay đổi |

### 6.2. Vary: Origin quan trọng cho cache/CDN

Một backend trả origin A cho request từ A, origin B cho request từ B. Nếu CDN cache response của A rồi phục vụ lại cho B mà không xét `Vary: Origin`, CORS có thể lỗi hoặc tạo vấn đề chia sẻ tài nguyên. Nếu server dùng danh sách origin cụ thể và phản chiếu origin sau kiểm tra, nên có `Vary: Origin`, và với preflight có thể cần `Access-Control-Request-Method`/`Access-Control-Request-Headers`.

**CORS headers không tự tạo cache isolation cho dữ liệu người dùng.** Với response cá nhân hóa theo cookie/authorization, cần thêm policy cache phù hợp như `Cache-Control: private/no-store` khi cần; không dựa chỉ vào Vary: Origin.

### 6.3. Không “sửa” preflight bằng permitAll mọi URL

Nếu `OPTIONS /api/me` bị 401, cách đúng là cấu hình **CORS processor/filter chạy sớm** và cấp phép Origin/method/headers đúng. Tạo rule `anyExchange().permitAll()` hoặc bỏ Authentication là sai. Có những tình huống phải cấu hình matcher xử lý OPTIONS, nhưng điều đó không thay thế CORS header validation.

## 7. Cấu hình CORS cho Spring Security reactive

Spring Security reactive tích hợp với CORS support của Spring Framework. Theo reference, bạn có thể khai báo bean `UrlBasedCorsConfigurationSource` trong package `org.springframework.web.cors.reactive` và bật CORS integration trong `ServerHttpSecurity`:

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(List.of(
        "http://localhost:3000",
        "https://portal.example.test"));
    config.setAllowCredentials(true);
    config.setAllowedMethods(List.of("GET", "OPTIONS"));
    config.setAllowedHeaders(List.of("X-Client-Trace"));
    config.setExposedHeaders(List.of("X-Trace-Id"));
    config.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}

@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .cors(Customizer.withDefaults())
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **hai method cấu hình đặt trong class Spring có imports** (ứng dụng hoàn chỉnh ở mục 8). Những quyết định cần đọc đúng:

1. `setAllowedOrigins(...)` cho phép **đúng** hai origin, không chấp nhận mọi website.
2. `setAllowCredentials(true)` cho phép credentialed responses theo CORS.
3. `setAllowedMethods(...)` chỉ cho GET và OPTIONS trong bài minh họa; production nên liệt kê đúng methods API.
4. `setAllowedHeaders(...)` chỉ cho header tùy chỉnh `X-Client-Trace` trong preflight của ví dụ; nếu POST JSON thật, cần thêm `Content-Type`/`X-XSRF-TOKEN` phù hợp.
5. `setExposedHeaders(...)` để frontend có thể đọc `X-Trace-Id` (không cần dùng dấu `*`).
6. `registerCorsConfiguration("/api/**", config)` áp policy CORS cho API URLs, không nhất thiết cho `/login` hoặc static resources.
7. `.cors(Customizer.withDefaults())` tích hợp CORS vào security chain; dùng bean configuration source. Không cần đồng thời đăng ký một custom `CorsWebFilter` thứ hai cho cùng URL nếu đã tích hợp như trên.
8. `authorizeExchange(...)` vẫn bảo vệ API sau preflight, độc lập với allowCredentials.

### 7.1. CorsWebFilter và @CrossOrigin

Bạn cũng có thể dùng một bean `CorsWebFilter` của WebFlux khi cần xử lý CORS sớm, hoặc `@CrossOrigin`/WebFlux MVC-style handler mappings cho controller. Tuy nhiên cần biết chính xác lớp nào đang xử lý preflight trước security, tránh nhiều nguồn CORS config chồng nhau.

- `CorsWebFilter` của WebFlux nằm trong `org.springframework.web.cors.reactive`, không dùng `org.springframework.web.filter.CorsFilter` Servlet.
- `@CrossOrigin(origins=..., allowCredentials="true")` là lựa chọn ở controller khi policy hẹp, nhưng nếu đang có security filters, phải bảo đảm preflight được xử lý đúng thứ tự.
- Cấu hình global và local có thể được kết hợp theo quy tắc Spring, đôi khi mở rộng allowed origins ngoài ý muốn. Với API có credentials, nên quản lý policy tập trung, review các annotation bổ sung.
- Đừng bật cùng một CORS policy ở gateway và ứng dụng theo cách tạo header `Access-Control-Allow-Origin` trùng lặp. Browser không chấp nhận nhiều giá trị origins khác nhau ở một header.

### 7.2. Khi có nhiều SecurityWebFilterChain

Nếu có chain cho `/api/**` và chain riêng cho `/web/**`, xác định matcher và thứ tự `@Order` rõ ràng. `CorsConfigurationSource`, CORS integration và exception handling cần áp dụng đúng chain; endpoint ngoài matcher có thể không nhận CORS headers bạn mong đợi. Đừng gắn policy wildcard cho catch-all chỉ để làm frontend hết lỗi.

## 8. Demo Java 17 chạy được: cookie session và CORS từ frontend port 3000

Ví dụ dùng **Java 17**, **Spring Boot 3.5.16**, Spring Security reactive và WebFlux. Cấu hình minh họa một frontend origin `http://localhost:3000` truy cập backend `http://localhost:8080`, cookie session gửi qua `credentials:"include"`. Bài thực hành dùng cả form login (cho browser) và HTTP Basic (để dễ kiểm thử curl), nhưng production chỉ nên bật cơ chế thực sự cần.

**Chức năng:**

- `GET /api/public`: API công khai, không cần Authentication.
- `GET /api/me`: API authenticated; trả username và header demo `X-Trace-Id`.
- `GET /login`: form login Spring Security tạo ra; đăng nhập `learner` bằng password `demo-pass`.
- CORS `allowCredentials=true`, **chỉ** cho origin `http://localhost:3000` hoặc `https://portal.example.test`.
- Frontend static `index.html` được phục vụ **ở port 3000**, gọi API 8080 bằng `fetch`.

### 8.1. Cấu trúc

~~~text
webflux-cors-credentials-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/example/CorsCredentialsDemo.java
│   └── test/java/example/CorsCredentialsIntegrationTest.java
└── ui/
    └── index.html
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-credentials-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle/Gradle Wrapper tương thích. Spring Boot quản lý các phiên bản Spring Security, Reactor và Spring Framework; không tự trộn các version rời rạc cho bài thực hành.

### 8.2. Backend hoàn chỉnh

Tệp `src/main/java/example/CorsCredentialsDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CorsCredentialsDemo {

    public static void main(String[] args) {
        SpringApplication.run(CorsCredentialsDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Plaintext chỉ để demo localhost; production phải hash password.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Origin có cả scheme + host + port; không thêm dấu / ở cuối.
        cors.setAllowedOrigins(List.of(
            "http://localhost:3000",
            "https://portal.example.test"));

        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("X-Client-Trace"));
        cors.setExposedHeaders(List.of("X-Trace-Id"));
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @RestController
    static class Api {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            exchange.getResponse().getHeaders().set(
                "X-Trace-Id", "local-demo-trace");

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }
    }
}
~~~

**Đọc code theo trách nhiệm:**

- `UrlBasedCorsConfigurationSource` thuộc **reactive** package. CORS config áp vào `/api/**`, nên preflight của `/api/me` được xử lý theo allowlist.
- `cors.setAllowedOrigins(List.of(...))` dùng hai origin cụ thể; **không** dùng `*` cùng `allowCredentials=true`.
- `setAllowedHeaders(List.of("X-Client-Trace"))` cho phép header custom của JS, làm GET trở thành preflighted request. Trên GET không có Content-Type JSON nên không cần `Content-Type` trong allowedHeaders của demo.
- `setExposedHeaders(List.of("X-Trace-Id"))` cho JS đọc response header demo qua `response.headers.get(...)`.
- `setMaxAge(1800L)` là chỉ dẫn cache preflight, không phải TTL session/token; browser có thể giới hạn thời gian cache.
- `.cors(Customizer.withDefaults())` tích hợp với Security để xử lý preflight **trước authentication**.
- `.formLogin(Customizer.withDefaults())` cung cấp một trang login cho browser; không dùng raw username query parameter làm principal.
- `.httpBasic(Customizer.withDefaults())` chỉ giúp phép thử HTTP client/test đơn giản. Trong ứng dụng thật có thể bỏ Basic nếu chỉ dùng form/session.
- `/api/me` yêu cầu Authentication hợp lệ. CORS allowlist không làm người ngoài tự có quyền đọc danh tính của bất cứ ai.

### 8.3. Frontend chạy ở origin khác

Tệp `ui/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux Credentialed CORS Demo</title>
</head>
<body>
  <h1>Cross-origin request với credentials</h1>

  <p>Đăng nhập vào backend tại
     <a href="http://localhost:8080/login"
        target="_blank" rel="noopener">
        http://localhost:8080/login
     </a>
     với learner / demo-pass (chỉ localhost).
  </p>

  <button id="callApi">Gọi /api/me</button>
  <pre id="result" aria-live="polite"></pre>

  <script type="module">
    "use strict";

    const api = "http://localhost:8080";

    document.getElementById("callApi")
      .addEventListener("click", async () => {
        const target = document.getElementById("result");
        target.textContent = "Đang yêu cầu...";

        try {
          const response = await fetch(api + "/api/me", {
            method: "GET",
            mode: "cors",
            credentials: "include",
            headers: {
              "X-Client-Trace": "browser-demo"
            }
          });

          const contentType =
            response.headers.get("Content-Type") || "";

          if (!response.ok ||
              !contentType.includes("application/json")) {
            throw new Error("HTTP " + response.status
              + ": cần đăng nhập, hoặc API không trả JSON");
          }

          const data = await response.json();
          const traceId = response.headers.get("X-Trace-Id");

          target.textContent = JSON.stringify(
            { data, traceId }, null, 2);
        } catch (error) {
          target.textContent = String(error.message || error)
            + " — kiểm tra Network/CORS và cookie chính xác.";
        }
      });
  </script>
</body>
</html>
~~~

**Mô hình localhost:** mở UI ở `http://localhost:3000` và API ở `http://localhost:8080`. Hai origin khác nhau vì port, dù cùng site cho nhiều chính sách cookie. Nhấn link login để mở **trang backend** ở origin 8080, nhập tài khoản demo, rồi quay lại UI và nhấn nút **Gọi /api/me**.

Frontend **không lấy cookie HttpOnly bằng document.cookie**. Browser tự quản lý cookie login và gửi nó theo `credentials:"include"` nếu chính sách cookie cho phép. `X-Client-Trace` chỉ là header demo, không phải credential; nó cố ý khiến browser tạo preflight để người học quan sát.

### 8.4. Khởi chạy

Terminal 1, trong thư mục dự án:

~~~bash
gradle bootRun
~~~

Với Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Terminal 2, trong thư mục `webflux-cors-credentials-demo/ui`, nếu Python 3 đã được cài:

~~~bash
python -m http.server 3000
~~~

Mở `http://localhost:3000`, đăng nhập qua link backend 8080, sau đó gọi API. Trong Browser Developer Tools → Network, bạn có thể thấy:

1. `OPTIONS http://localhost:8080/api/me` (preflight, **không** có cookie), có `Origin`, requested method GET và requested header `x-client-trace`.
2. Preflight phản hồi có `Access-Control-Allow-Origin: http://localhost:3000` và `Access-Control-Allow-Credentials: true`.
3. `GET http://localhost:8080/api/me` thực tế, có session cookie nếu login thành công.
4. Actual response trả JSON có `"username":"learner"`, đồng thời `X-Trace-Id` đọc được nhờ `Access-Control-Expose-Headers`.

Nếu bước 4 thất bại do chưa login, response có thể là login redirect/401 tùy entry point và request headers; client có thể thấy lỗi CORS tại trang login **không nằm trong policy /api/**. Đây không có nghĩa backend đã vô hiệu hóa Authentication. Trước tiên bảo đảm session login ở 8080 hoạt động rồi mới kiểm tra CORS cho `/api/me`.

**Không sử dụng cấu hình demo ở môi trường mạng thật:** password `{noop}` và HTTP không có TLS chỉ để kiểm tra trên localhost. Với production cần password hashing, HTTPS, Secure/HttpOnly cookie, chống CSRF, giới hạn origin được review và xử lý session đúng.

## 9. Kiểm tra bằng curl: quan sát chính xác headers

HTTP client như curl **không thực thi CORS như browser**, nhưng rất hữu ích để xem server trả header nào.

### 9.1. Preflight hợp lệ

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-Client-Trace'
~~~

Điều cần thấy:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: X-Client-Trace
~~~

Đây là **trích đoạn header kỳ vọng**, case chữ và status 200/204 có thể tùy runtime. Preflight không cần `Authorization` hoặc cookie vì browser preflight không mang credentials.

### 9.2. Preflight từ origin không được phép

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-Client-Trace'
~~~

Với Spring CORS processor mặc định, preflight không hợp lệ thường bị **403**. Không nên có `Access-Control-Allow-Origin: https://evil.example.test`. Tình huống browser thực tế có thể chỉ hiện “CORS blocked”, dù response status đã được server tạo.

### 9.3. Actual request hợp lệ

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: http://localhost:3000' \
  -H 'X-Client-Trace: curl-demo' \
  'http://localhost:8080/api/me'
~~~

Vì HTTP Basic test xác thực thành công, request có thể trả **200** cùng `Access-Control-Allow-Origin: http://localhost:3000`, `Access-Control-Allow-Credentials: true` và JSON chứa username. **Curl không chứng minh browser có thể gửi session cookie**, nhưng chứng minh API authentication và header CORS độc lập.

### 9.4. Actual request từ origin sai

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: https://evil.example.test' \
  'http://localhost:8080/api/me'
~~~

Spring CORS processor có thể trực tiếp từ chối origin không được phép với 403; tại minimum nó không được gửi header cho phép origin ấy. Trong mọi trường hợp, browser sẽ không cấp JavaScript ở origin đó quyền đọc response credentialed nếu CORS policy không cho phép.

**Đừng kết luận API an toàn chỉ vì trình duyệt báo CORS error.** Nếu API không kiểm tra session/role/CSRF, một request từ client không phải browser vẫn có thể tạo side effect. CORS là một lớp browser isolation, không thay authorization server-side.

## 10. Integration tests bằng WebTestClient

Các test dưới đây chứng minh ba ranh giới: **preflight không bị HTTP authentication chặn**, **origin lạ không được phép** và **actual authenticated request có đúng CORS headers**.

Tệp `src/test/java/example/CorsCredentialsIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsCredentialsIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String GOOD_ORIGIN = "http://localhost:3000";
    private static final String BAD_ORIGIN = "https://evil.example.test";

    @Test
    void acceptedPreflightRequiresNoAuthentication() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Client-Trace")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().valueContains(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                "X-Client-Trace");
    }

    @Test
    void untrustedOriginPreflightIsDenied() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, BAD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Client-Trace")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void validCredentialsFromAllowedOriginReceiveCORSHeaders() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .header("X-Client-Trace", "test-client")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().valueEquals("X-Trace-Id",
                                      "local-demo-trace")
            .expectHeader().valueContains(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Trace-Id")
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }

    @Test
    void publicRouteAcceptsAllowedOriginWithoutCredentials() {
        client.get().uri("/api/public")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }

    @Test
    void sameOriginStyleRequestNeedsNoCORSHeaders() {
        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Với Gradle Wrapper dùng `./gradlew test` hoặc `gradlew.bat test`. Kỳ vọng các phép kiểm tra đạt trên cấu hình đã đưa, nhưng **phải chạy thực tế để xác nhận**. Đoạn test không khởi chạy browser hay xác nhận SameSite cookie policies; cần test end-to-end trên browser khi tích hợp production.

**Gợi ý mở rộng test:**

- Preflight request từ origin hợp lệ nhưng yêu cầu header **không** nằm trong `allowedHeaders`.
- Method không thuộc `allowedMethods`.
- `Origin: null` không được cấu hình.
- Trường hợp role không đủ nhưng origin hợp lệ → Authorization vẫn trả 403.
- Browser credentialed fetch khi cookie SameSite chặn.
- Trường hợp frontend ở HTTPS nhưng backend gọi HTTP bị mixed-content block.
- Reverse proxy/CDN giữ đúng `Vary: Origin` và không cache response cá nhân hóa sai.

## 11. CORS và CSRF phải được phân biệt

Một nhầm lẫn nguy hiểm là **“Đã giới hạn allowOrigins, vậy có thể tắt CSRF”**. Hai cơ chế có mục tiêu khác nhau:

| Cơ chế | Câu hỏi chính |
|---|---|
| Authentication | Request thuộc principal nào? |
| Authorization | Principal có quyền xem/sửa tài nguyên không? |
| CORS | Browser cho JavaScript từ origin nào **đọc response** của tài nguyên cross-origin? |
| CSRF | Browser gửi request thay đổi trạng thái với credential tự động có thực sự do ứng dụng/người dùng hợp lệ khởi tạo? |
| SameSite cookie | Browser có thể gửi cookie trong các ngữ cảnh cross-site nào? |
| CSP/XSS defenses | Script không đáng tin có thể chạy trên origin hợp lệ hay không? |

CORS thường **không chặn mọi cách gửi một HTTP request**. Một trang độc hại vẫn có thể tạo HTML form POST và browser có thể gửi cookie theo policy. Nếu backend dựa vào cookie/session, phải áp dụng CSRF token/Origin checking theo threat model. **CORS allowlist không thay thế CSRF.**

### 11.1. Credentialed POST JSON

Một JavaScript client hợp lệ có thể thực hiện:

~~~javascript
await fetch("https://api.example.test/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-XSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ itemId: 42 })
});
~~~

Đây là **mảnh JS minh họa**, với `csrfToken` đã được frontend nhận qua cơ chế cấp phát CSRF token hợp lệ; **không phải endpoint POST có sẵn trong demo Java mục 8**. Backend cần đồng thời:

1. CORS allowlist cho origin frontend, allowCredentials true.
2. `allowedMethods` có `POST`, `allowedHeaders` có `Content-Type` và `X-XSRF-TOKEN`.
3. Authentication session/token hợp lệ, CSRF token đúng theo repository/request handler.
4. Authorization trên tài nguyên/nghiệp vụ, xác thực dữ liệu và giao dịch phù hợp.

Không bật `allowedHeaders("*")` hay `allowedMethods("*")` một cách mặc định để bỏ qua việc thiết kế các ranh giới trên.

### 11.2. SameSite không sửa được CORS sai

Nếu frontend ở `https://ui.example.test` và API ở `https://api.example.test`, hai origin khác nhau nhưng cùng site theo schemeful site. `SameSite=Lax` **có thể** cho phép cookie trong những request cùng site, nhưng **CORS vẫn cần** allow origin UI và allowCredentials để JS đọc response.

Nếu frontend và API ở hai site thực sự khác nhau, cookie `SameSite=Lax` có thể bị chặn cho cross-site subresource fetch. Có thể cần `SameSite=None; Secure` trong thiết kế được xem xét kỹ, nhưng browser cũng có thể chặn third-party cookie dù đã đặt None/Secure. Không tự đặt mọi cookie thành cross-site chỉ để “fix CORS”.

### 11.3. HTTPS và mixed content

Trang được serve từ `https://ui.example.test` gọi `http://api.example.test` có thể bị browser chặn vì **mixed content**, trước cả khi bạn có thể quan sát đúng CORS response. Nên dùng HTTPS cho cả UI và API ở production. `Secure` cookie không được gửi qua HTTP network thông thường (localhost có các ngoại lệ browser nhất định, nhưng không được dựa vào chúng ở production).

## 12. Những lỗi thực tế dễ mắc

**Lỗi 1 — setAllowCredentials(true) cùng allowedOrigins("*").**

Không hợp lệ theo Spring/CORS. Chuyển sang danh sách origin cụ thể. Không thay bằng `allowedOriginPatterns("*")` nếu mục đích chỉ là mở hết mọi nguồn.

**Lỗi 2 — Set Access-Control-Allow-Origin bằng Origin request mà không validate.**

Đây là allow-all disguised as dynamic reflection. Chỉ phản chiếu sau khi so với allowlist/pattern tin cậy.

**Lỗi 3 — Cho tất cả subdomain quyền đọc session data.**

Một subdomain bị chiếm hoặc do bên ngoài quản lý có thể trở thành origin được tin cậy. Rà soát wildcard patterns, tenant-subdomains và domain takeover.

**Lỗi 4 — Cho phép hai origins bằng header cách nhau bởi dấu phẩy.**

`Access-Control-Allow-Origin: https://a.test, https://b.test` không phải cách khai báo danh sách hợp lệ. Server phải match request Origin và trả **một** origin.

**Lỗi 5 — Không gửi credentials:"include" từ JavaScript cross-origin.**

Server allowCredentials true không ép browser gửi cookie. Đặt đúng Fetch credentials mode, nhưng vẫn phải xem SameSite/Secure/Domain/Path.

**Lỗi 6 — Nghĩ credentials:"include" sửa được response Access-Control-Allow-Origin:"*".**

Không. Browser sẽ block credentialed response nếu ACAO là `*`.

**Lỗi 7 — Preflight OPTIONS bị 401 do Spring Security chạy trước CORS.**

CORS phải xử lý trước Authentication, vì preflight chuẩn không có cookie. Dùng CORS integration/filter của WebFlux đúng.

**Lỗi 8 — PermitAll toàn bộ API để “cho preflight”.**

Rất nguy hiểm: `anyExchange().permitAll()` bỏ authorization bảo vệ tài nguyên. Cấu hình CORS đúng thay vì bỏ auth.

**Lỗi 9 — CORS chạy nhưng API vẫn 403 do CSRF.**

Preflight cho phép không tự bảo đảm POST có CSRF token đúng. Giữ CSRF khi browser sử dụng cookie/session.

**Lỗi 10 — Chỉ test bằng curl rồi nói browser chắc chắn hoạt động.**

Curl không có SOP, không thực thi browser CORS, SameSite hay mixed content. Test cả header server lẫn trình duyệt.

**Lỗi 11 — Chỉ xét hostname mà quên scheme/port.**

`http://localhost:3000` khác `http://localhost:8080`; HTTPS khác HTTP; port trong origin là quan trọng.

**Lỗi 12 — Cho Origin null vô điều kiện.**

Một opaque/sandboxed origin có thể báo `null`. Không coi null tương đương trusted frontend.

**Lỗi 13 — Bật exposedHeaders("*") không review.**

Ở credentialed CORS, browser/spec có sắc thái tương thích; nên liệt kê headers thực sự frontend cần đọc.

**Lỗi 14 — Vary/Cache-Control không phù hợp.**

Khi ACAO thay đổi theo Origin, cần Vary: Origin; dữ liệu cá nhân hóa cần cache policy riêng để tránh rò rỉ qua CDN/proxy.

**Lỗi 15 — Có hai CORS filter cùng ghi header.**

CORS config ở gateway + framework + custom middleware có thể tạo giá trị header trùng lặp, làm browser từ chối response. Giữ một nguồn policy được kiểm soát.

**Lỗi 16 — Cấu hình WebMVC `CorsFilter` trong app WebFlux.**

Dùng `CorsWebFilter`/`UrlBasedCorsConfigurationSource` của reactive hoặc tích hợp qua `ServerHttpSecurity.cors(...)`.

**Lỗi 17 — Mở CORS để “bảo vệ API khỏi curl”.**

CORS không phải chặn mạng, không bảo vệ API khỏi client tự tạo request. Cần Authentication, Authorization, rate limiting và kiểm tra input ở server.

**Lỗi 18 — Quên headers trong preflight.**

Frontend gửi `X-XSRF-TOKEN` hoặc `Authorization` nhưng config chỉ cho `Content-Type`; browser chặn trước actual request. Thêm chính xác những headers cần thiết và test.

**Lỗi 19 — Dùng credentials với wildcard cho user-specific GET.**

Không chỉ sai protocol, còn là dấu hiệu policy chia sẻ dữ liệu quá rộng; chỉ cho phép những origin chính thức.

**Lỗi 20 — Lấy kết quả preflight 200 làm bằng chứng user authenticated.**

Preflight không mang credential. Authentication xảy ra trên actual request riêng; 200 preflight không cấp quyền nghiệp vụ.

## 13. Checklist review trước production

1. **Inventory:** Liệt kê những origin frontend **thật sự** cần gọi API, bao gồm scheme/host/port của từng environment.
2. **Credential model:** API dùng session cookies, HTTP Basic, Bearer token hay một kết hợp? Xác định đúng Fetch credentials mode và browser behavior.
3. **Allow credentials:** Chỉ `setAllowCredentials(true)` khi thật sự cần credentialed CORS, không bật theo thói quen.
4. **Allowed origins:** Dùng danh sách origin cụ thể; không `*` khi credentials true.
5. **Patterns:** Nếu cần wildcard subdomain, kiểm tra domain ownership, tenant model, TLS, port và rủi ro takeover; có giới hạn rõ.
6. **Preflight:** OPTIONS từ origin được cho phép phải được xử lý trước authentication.
7. **Allowed methods:** Chỉ cho GET/POST/PUT/PATCH/DELETE thực sự cần; không dùng wildcard vô cớ.
8. **Allowed headers:** Liệt kê Content-Type, Authorization, X-XSRF-TOKEN hoặc headers khác theo client thực tế.
9. **Exposed headers:** Chỉ liệt kê response headers frontend cần; không mặc định exposed `*`.
10. **Access-Control-Allow-Origin:** Trả một origin đã match, không trả comma list hoặc phản chiếu arbitrary Origin.
11. **Cache:** Vary: Origin phù hợp; response cá nhân hóa không bị CDN cache cho user khác.
12. **CSRF:** Với credential browser tự gửi, có CSRF token/Origin policy phù hợp; không tắt chỉ vì CORS pass.
13. **Cookies:** SameSite/Secure/Domain/Path/HttpOnly đúng cho session, HTTPS và kiến trúc cross-site.
14. **Origin null:** Không được phép trừ khi có trường hợp tin cậy được xem xét rõ.
15. **Same-site vs same-origin:** Không nhầm subdomain/port với việc tự động được cấp CORS.
16. **Multiple chains:** Chính sách CORS được áp cho đúng SecurityWebFilterChain, không có filter/gateway ghi trùng.
17. **Authentication:** CORS pass không bypass đăng nhập, disabled user hoặc token validation.
18. **Authorization:** Origin được tin cậy không thay thế role/ownership/tenant checks.
19. **Browser QA:** Test thật trên browser với UI origin, API origin, cookie và response error.
20. **Regression:** Test allowed/disallowed origin, preflight, allowed/disallowed headers/methods, credentialed GET và CSRF POST.
21. **Operational controls:** Log/métrics sanitized, rate limiting, TLS, secrets management, không log raw cookie/token.
22. **Change management:** Khi thêm frontend origin mới, đánh giá ownership và threat model thay vì thêm `*` cho nhanh.

## 14. Tự kiểm tra kiến thức

**1.** `allowCredentials(true)` có làm browser tự gửi cookie cho mọi cross-origin fetch không?

**Đáp án:** Không. Frontend cần `credentials:"include"` trong trường hợp cross-origin, và cookie vẫn phải thỏa các chính sách browser. Header server chỉ cho phép chia sẻ response credentialed.

**2.** Có thể dùng `setAllowedOrigins(List.of("*"))` đồng thời `setAllowCredentials(true)` không?

**Đáp án:** Không. Spring và browser không cho phép ACAO wildcard với credentials; dùng exact allowlist hoặc origin patterns được kiểm soát.

**3.** `allowedOriginPatterns("https://*.trusted.example.test")` khác `allowedOrigins("*")` ở response thế nào?

**Đáp án:** Khi pattern match, Spring trả **origin cụ thể** đã match, không phải literal `*`. Nhưng pattern rộng vẫn có thể không an toàn, nhất là khi subdomain không tin cậy.

**4.** Vì sao preflight không được yêu cầu session cookie?

**Đáp án:** Browser preflight chuẩn không gửi credentials. CORS phải xử lý preflight trước authentication, nếu không có thể bị 401 sai.

**5.** `Access-Control-Allow-Origin` có thể chứa `https://a.example,https://b.example` không?

**Đáp án:** Không. Server kiểm tra Origin rồi trả một origin hợp lệ hoặc `*` trong trường hợp non-credentialed.

**6.** UI ở `https://ui.example.test` và API ở `https://api.example.test` là same-site, vậy có cần CORS không?

**Đáp án:** Có, vì khác origin. SameSite cookie và CORS dùng hai khái niệm khác nhau.

**7.** Browser gửi request POST có cookie và CORS cho phép origin. Vậy có cần CSRF token không?

**Đáp án:** Với cookie-auth state-changing request, vẫn cần CSRF protection theo threat model. CORS chỉ quyết định quyền đọc response, không thay thế chống giả mạo request.

**8.** Server trả 200 cho preflight. Có chứng minh người dùng đã đăng nhập chưa?

**Đáp án:** Chưa. Preflight không mang credentials; actual request riêng mới thực hiện Authentication/Authorization.

**9.** Điều gì xảy ra khi JS chạy từ `localhost:3000` gọi `localhost:8080` mà không có `credentials:"include"`?

**Đáp án:** Dù hai địa chỉ cùng host, chúng khác origin do port. Fetch ở mặc định same-origin sẽ không gửi credentials cho cross-origin, nên API session có thể coi user anonymous.

**10.** Có cách nào cấu hình wildcard methods/headers với allowCredentials true trong Spring không?

**Đáp án:** Với `allowedMethods("*")` hoặc `allowedHeaders("*")`, Spring có thể phát lại method/header đã được yêu cầu trong preflight thay vì literal `*`. Tuy nhiên production nên có danh sách hữu hạn; `allowedOrigins("*")` vẫn bị cấm khi credentials true.

**11.** Nếu curl đọc được API từ evil origin thì CORS đã thất bại?

**Đáp án:** Không thể kết luận. Curl không thực thi SOP/CORS của browser; phải xem headers server và test trên browser. Authentication/Authorization trên server vẫn là bắt buộc.

**12.** Một request cross-origin GET không preflight có thể gửi tới server nhưng JavaScript không đọc response được không?

**Đáp án:** Có. Browser có thể gửi request và sau đó chặn script đọc response nếu CORS policy không hợp lệ. Đây là lý do CORS không đủ chống CSRF.

## Tài liệu chính thức

- Spring Security — CORS for Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Framework — CORS trong WebFlux, Credentialed Requests, Global Configuration: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — `CorsConfiguration` API (allowedOrigins, allowedOriginPatterns, allowCredentials): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Security 6.5 — `ServerHttpSecurity` CORS DSL: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- MDN — CORS, Credentialed Requests and Wildcards: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Fetch Request credentials mode: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — SameSite cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
