# Preflight, credentials và danh sách nguồn được phép trong Spring WebFlux

## 1. CORS giải quyết vấn đề gì?

CORS (Cross-Origin Resource Sharing) là cơ chế HTTP cho phép trình duyệt quyết định JavaScript từ một origin có được đọc response của server ở origin khác hay không.

Ví dụ:

- Frontend: `https://app.example.com`
- Backend API: `https://api.example.com`

Hai địa chỉ này khác origin vì hostname khác nhau, dù có thể cùng một site. Khi JavaScript ở frontend gọi API, trình duyệt gửi header `Origin`. Backend phải trả các CORS response header phù hợp để browser cho phép JavaScript đọc response.

Một origin được xác định bởi bộ ba:

~~~text
scheme + host + port
~~~

Ví dụ:

| Origin | Có cùng origin với https://app.example.com không? | Lý do |
| --- | --- | --- |
| `https://app.example.com` | Có | Cùng scheme, host, port mặc định |
| `http://app.example.com` | Không | Khác scheme |
| `https://api.example.com` | Không | Khác host |
| `https://app.example.com:8443` | Không | Khác port |
| `https://app.example.com/admin` | Không phải một origin riêng | Path không thuộc origin |

Origin trong allowlist không có path và thường không có dấu slash cuối. Dùng `https://app.example.com`, không dùng `https://app.example.com/`.

**CORS là chính sách của trình duyệt đối với response cross-origin.** Nó không thay thế authentication, authorization, CSRF protection hoặc kiểm soát truy cập ở server. Một chương trình gọi API bằng curl, Postman hay backend service không bị browser áp dụng CORS.

## 2. Hai kiểu request: simple và preflight

CORS phân biệt simple request và request cần preflight.

### 2.1. Simple request

Browser có thể gửi một số request cross-origin mà không cần hỏi trước bằng OPTIONS. Những method được safelist là:

- `GET`
- `HEAD`
- `POST`

Các request header cũng phải thuộc nhóm CORS-safelisted và thỏa điều kiện về giá trị. Ví dụ `Accept`, `Accept-Language`, `Content-Language` và `Content-Type` với một số media type được phép.

Vì vậy, một POST form đơn giản có thể được gửi trực tiếp tới server. Response vẫn phải có CORS header phù hợp thì JavaScript mới đọc được response.

### 2.2. Preflight request

Nếu request dùng method không nằm trong safelist hoặc có request header không được safelist, browser thường gửi một request OPTIONS trước. OPTIONS này được gọi là **CORS preflight**.

Ví dụ frontend muốn gửi PUT với JSON, bearer token và request ID:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization,content-type,x-request-id
~~~

Ý nghĩa:

- `Origin`: origin của trang đang gọi API.
- `Access-Control-Request-Method`: method của request thực tế sắp gửi.
- `Access-Control-Request-Headers`: các request header không safelisted mà request thực tế muốn sử dụng.

Browser chờ server cho phép origin, method và headers. Nếu preflight thất bại, browser không gửi request PUT thực tế.

Các trường hợp thường kích hoạt preflight:

| Request | Có preflight? | Lý do |
| --- | --- | --- |
| GET với Accept thông thường | Thường không | Method và headers thuộc safelist |
| POST form-urlencoded với header safelisted | Thường không | Request đáp ứng điều kiện simple request |
| PUT hoặc PATCH | Có | Method không nằm trong safelist |
| POST với Content-Type application/json | Có | Media type JSON không thuộc Content-Type safelist |
| GET có header X-Request-Id | Có | Custom header không được safelist |
| Request có Authorization header | Có | Authorization là request header cần được cho phép rõ ràng |

Chỉ bật credentials không tự nó có nghĩa mọi request đều phải preflight. Preflight chủ yếu phụ thuộc method và request headers. Credentials mode ảnh hưởng điều kiện browser chấp nhận response.

## 3. Luồng preflight và request thực tế

Một request cần preflight có hai lượt HTTP:

~~~text
JavaScript trên https://app.example.com
                  |
                  | PUT + JSON + Authorization
                  v
        Browser tạo OPTIONS preflight
                  |
                  | Origin
                  | Access-Control-Request-Method: PUT
                  | Access-Control-Request-Headers: ...
                  v
            Spring WebFlux
                  |
                  | Kiểm tra origin, method, headers
                  v
        OPTIONS response cho phép?
             /             \
           Không            Có
            |                |
            v                v
       Browser chặn     Browser gửi PUT thật
                              |
                              | Origin + credentials nếu được yêu cầu
                              v
                       Spring WebFlux
                              |
                              v
                       HTTP response
                              |
                              | ACAO + ACAC nếu cần
                              v
                   Browser cho JavaScript đọc?
~~~

Preflight là bước kiểm tra chính sách. Nó không phải request nghiệp vụ và thường không cần một method OPTIONS riêng trong controller. Spring WebFlux có thể xử lý preflight trước khi gọi handler.

## 4. Những response header quan trọng

| Response header | Ý nghĩa |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép đọc response |
| `Access-Control-Allow-Credentials` | Cho phép browser chia sẻ response khi request dùng credentials mode include |
| `Access-Control-Allow-Methods` | Các HTTP method được phép cho request thực tế |
| `Access-Control-Allow-Headers` | Các request header được phép dùng |
| `Access-Control-Expose-Headers` | Response header mà JavaScript được phép đọc thêm |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight |

### 4.1. Access-Control-Allow-Origin

Nếu chỉ cho phép một frontend:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

Nếu request không dùng credentials, server có thể trả:

~~~http
Access-Control-Allow-Origin: *
~~~

Không trả nhiều origin trong cùng một giá trị header theo dạng danh sách. CORS response cho một request phải trả origin cụ thể được phép hoặc wildcard trong trường hợp không credentials.

Nếu server chọn origin động từ allowlist, response nên có `Vary: Origin` để cache/proxy phân biệt response theo Origin request.

### 4.2. Access-Control-Allow-Methods

Ví dụ:

~~~http
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
~~~

Header này cho browser biết các method nào được phép cho request thực tế. Nó không tạo endpoint PUT trong controller và cũng không cấp quyền nghiệp vụ cho user.

Nếu API chỉ hỗ trợ GET và POST, không cần cho phép PUT, DELETE chỉ để làm preflight thành công.

### 4.3. Access-Control-Allow-Headers

Ví dụ:

~~~http
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id, X-CSRF-TOKEN
~~~

Header này cho phép browser gửi các request header tương ứng trong request thực tế.

Nếu frontend gửi `Authorization` hoặc custom header, phải đưa header đó vào allowlist. Đừng cho phép mọi header nếu API chỉ cần một tập nhỏ.

### 4.4. Access-Control-Expose-Headers

Một số response header được browser cho JavaScript đọc mặc định, ví dụ `Content-Type`, `Content-Length`, `Cache-Control`, `Last-Modified` và `Expires`.

Các header khác như `Location`, `ETag` hoặc `X-Request-Id` cần được expose nếu frontend cần đọc:

~~~http
Access-Control-Expose-Headers: Location, ETag, X-Request-Id
~~~

`Set-Cookie` là forbidden response header; JavaScript không thể đọc nó bằng cách thêm vào `Access-Control-Expose-Headers`.

### 4.5. Access-Control-Max-Age

Ví dụ:

~~~http
Access-Control-Max-Age: 3600
~~~

Browser có thể cache kết quả preflight trong thời gian được phép, giúp giảm số OPTIONS request. Đây là preflight cache của browser, không phải thời gian cache dữ liệu API thông thường. Browser có thể áp dụng giới hạn riêng thấp hơn giá trị server gửi.

Trong Spring, `maxAge(3600)` cấu hình giá trị theo giây.

## 5. Credentials là gì?

Trong Fetch/CORS, credentials gồm các thông tin như:

- HTTP cookies.
- HTTP authentication entries.
- TLS client certificates.

Với Fetch API, tùy chọn `credentials` quyết định browser có gửi credentials cross-origin và chấp nhận credentialed response hay không.

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Các giá trị phổ biến:

| Fetch credentials mode | Hành vi |
| --- | --- |
| `omit` | Không gửi credentials |
| `same-origin` | Chỉ gửi credentials cho same-origin request; đây là mặc định của fetch |
| `include` | Cho phép gửi credentials cho cả cross-origin request, nếu cookie/browser policy cho phép |

Với XMLHttpRequest, lựa chọn tương ứng là `xhr.withCredentials = true`.

### 5.1. allowCredentials(true) không tự gửi cookie

Cấu hình server:

~~~java
.allowCredentials(true)
~~~

chỉ cho browser biết response có thể được chia sẻ khi request dùng credentials mode include. Nó không tự tạo session, không tự đăng nhập user và không buộc browser gửi cookie.

Để cookie được gửi, frontend phải dùng credentials mode phù hợp; cookie còn phải thỏa quy tắc domain, path, Secure, SameSite và chính sách riêng tư của browser.

### 5.2. Preflight không mang cookie

Một chi tiết rất quan trọng: CORS preflight request luôn dùng credentials mode `same-origin`, nên browser không gửi cookie cross-origin trong OPTIONS preflight.

Tuy nhiên, request thực tế theo sau vẫn có thể dùng credentials mode `include`. Vì thế, response preflight phải thể hiện rằng server cho phép credentialed request, và response thực tế cũng phải đáp ứng quy tắc credentials.

Ví dụ preflight response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, PUT
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 3600
~~~

Browser không cần cookie ở bước OPTIONS. Nó chỉ kiểm tra chính sách để quyết định có được gửi request thực tế hay không.

### 5.3. Điều kiện của response có credentials

Nếu request có credentials mode `include`, browser yêu cầu:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Hai điều kiện:

1. `Access-Control-Allow-Origin` phải là origin cụ thể khớp với Origin request. Không được là `*`.
2. `Access-Control-Allow-Credentials` phải có giá trị chính xác `true`, chữ thường.

Các giá trị `True`, `TRUE` hoặc `1` không thay thế cho `true`.

### 5.4. Bearer token trong Authorization khác cookie credentials

Frontend có thể tự đặt bearer token:

~~~javascript
fetch("https://api.example.com/api/profile", {
  headers: {
    "Authorization": "Bearer " + token
  }
});
~~~

Header `Authorization` là request header cần được cho phép trong preflight. Nó không có nghĩa browser tự gửi cookie. Nếu chỉ dùng bearer token do JavaScript quản lý và không cần cookie/HTTP authentication cross-origin, thường không cần bật `credentials: "include"`.

Cấu hình CORS vẫn phải cho phép `Authorization` trong allowed headers. Nếu request thực tế dùng credentials mode include, server còn phải đáp ứng ACAO cụ thể và ACAC true.

## 6. Wildcard và credentials: quy tắc phải nhớ

### 6.1. Không dùng allowedOrigins("*") cùng allowCredentials(true)

Cấu hình sau không hợp lệ theo CORS:

~~~java
configuration.setAllowedOrigins(List.of("*"));
configuration.setAllowCredentials(true);
~~~

Browser không chấp nhận:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Khi credentials mode là include, server phải trả origin cụ thể. Spring cũng kiểm tra và từ chối tổ hợp wildcard origin với credentials.

Cấu hình đúng là liệt kê các origin tin cậy:

~~~java
configuration.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com"));

configuration.setAllowCredentials(true);
~~~

### 6.2. allowedOriginPatterns

Spring hỗ trợ `allowedOriginPatterns` khi cần match một nhóm origin có cấu trúc:

~~~java
configuration.setAllowedOriginPatterns(List.of(
        "https://*.preview.example.com"));

configuration.setAllowCredentials(true);
~~~

Khi pattern khớp, Spring trả origin thực tế đã match trong `Access-Control-Allow-Origin`, không trả chuỗi pattern hoặc wildcard. Vì vậy, API này có thể dùng với credentials.

Tuy nhiên, pattern càng rộng thì càng nhiều website có thể được tin cậy. `allowedOriginPatterns("*")` gần như cho phép mọi origin và rất nguy hiểm khi kết hợp credentials. Chỉ dùng pattern có giới hạn rõ ràng, chẳng hạn một miền preview do tổ chức kiểm soát.

Nếu chỉ có vài frontend cố định, `allowedOrigins` với danh sách chính xác thường dễ audit hơn.

### 6.3. Wildcard ở methods, headers và exposed headers

CORS specification cũng giới hạn cách wildcard được hiểu khi credentials mode là include.

- Với allowed methods và allowed headers, wildcard không nên được xem là quyền cho mọi method/header khi có credentials.
- Spring có cách xử lý tiện dụng: khi cấu hình wildcard cho allowed methods/headers, nó có thể phản chiếu method và header được yêu cầu trong preflight vào response.
- Với exposed headers, Spring có hỗ trợ wildcard nhưng CORS specification không định nghĩa wildcard theo cùng cách cho credentialed response.

Để cấu hình rõ ràng và dễ kiểm tra, hãy liệt kê method, request header và exposed response header thực sự cần thiết thay vì dựa vào wildcard.

## 7. Danh sách origin được phép nên được thiết kế thế nào?

Một allowlist tốt phải mô tả đúng các frontend có quyền truy cập API.

### 7.1. Origin là giá trị chính xác

Ví dụ:

~~~java
.allowedOrigins(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173")
~~~

Ba origin trên là ba môi trường/ứng dụng riêng. Các biến thể scheme hoặc port không tự động được cho phép.

Không viết:

- `https://app.example.com/dashboard`: origin không chứa path.
- `https://*.example.com` trong allowedOrigins: wildcard này không thuộc dạng exact origin.
- `https://app.example.com/`: dấu slash cuối không phải dạng serialized origin thông thường.
- `https://app.example.com:3000` nếu frontend thực tế chạy port khác.

### 7.2. Tách origin development và production

Không nên giữ localhost trong allowlist production nếu không có lý do. Cấu hình có thể đến từ environment variables hoặc configuration properties:

~~~yaml
app:
  cors:
    allowed-origins:
      - https://app.example.com
      - https://admin.example.com
~~~

Local profile có thể bổ sung:

~~~yaml
app:
  cors:
    allowed-origins:
      - http://localhost:5173
      - http://localhost:3000
~~~

Ví dụ YAML cần được bind vào cấu hình Java phù hợp. Không nên đọc danh sách origin từ request rồi tự phản chiếu mà không xác minh allowlist.

### 7.3. Cẩn thận với Origin: null

Một số môi trường như file URL, sandboxed iframe hoặc opaque origin có thể gửi:

~~~http
Origin: null
~~~

Không cho phép `null` chỉ để làm một trang thử nghiệm hoạt động. Chỉ thêm nó nếu có use case cụ thể và hiểu rõ những nguồn có thể mang opaque origin.

### 7.4. Không dùng substring để kiểm tra origin

Không tự viết:

~~~java
if (origin.contains("example.com")) {
    // allow
}
~~~

Kiểm tra substring có thể chấp nhận hostname giả như `example.com.attacker.test` hoặc những origin không thuộc miền tin cậy.

Dùng `CorsConfiguration`, exact allowlist hoặc pattern matching được giới hạn rõ ràng. Không lấy `Referer` thay cho `Origin`; CORS dựa trên Origin request header.

## 8. Cấu hình CORS toàn cục bằng WebFluxConfigurer

Với annotated controller, cách thông dụng là triển khai `WebFluxConfigurer` và đăng ký URL pattern qua `CorsRegistry`.

~~~java
@Configuration
public class WebCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods(
                        "GET", "POST", "PUT", "PATCH", "DELETE")
                .allowedHeaders(
                        "Authorization",
                        "Content-Type",
                        "X-Request-Id",
                        "X-CSRF-TOKEN")
                .exposedHeaders(
                        "Location",
                        "ETag",
                        "X-Request-Id")
                .allowCredentials(true)
                .maxAge(3600);
    }
}
~~~

Giải thích:

- `addMapping("/api/**")` giới hạn chính sách vào API path.
- `allowedOrigins` là danh sách frontend được phép.
- `allowedMethods` là các method của request thực tế.
- `allowedHeaders` là các request header frontend được gửi.
- `exposedHeaders` là response header JavaScript cần đọc.
- `allowCredentials(true)` cho phép chia sẻ response của request có credentials mode include.
- `maxAge(3600)` cho phép cache preflight tối đa theo cấu hình 3600 giây, subject to browser caps.

Không cần thêm OPTIONS vào allowedMethods chỉ vì preflight dùng OPTIONS. `Access-Control-Allow-Methods` mô tả method của request thực tế được hỏi trong `Access-Control-Request-Method`. Chỉ thêm OPTIONS nếu API thực sự cung cấp OPTIONS như một method nghiệp vụ.

Không cần tự viết controller xử lý OPTIONS cho từng route nếu CORS đã được cấu hình đúng.

### 8.1. Không bật @EnableWebFlux chỉ để cấu hình CORS

Trong Spring Boot, chỉ cần một class `@Configuration` implements `WebFluxConfigurer` cho ví dụ trên. Không thêm `@EnableWebFlux` nếu không có chủ đích thay thế cấu hình WebFlux auto-configuration của Boot.

### 8.2. Giá trị mặc định của CorsRegistry

Khi dùng `CorsRegistry.addMapping`, Spring khởi tạo cấu hình theo permit defaults. Các mặc định thường gồm:

- Cho phép mọi origin.
- Cho phép mọi request header.
- Cho phép GET, HEAD và POST.
- Không bật credentials.
- Max age 30 phút.

Đừng dựa vào defaults cho API production. Hãy ghi rõ origin, method, header và credentials theo contract thực tế.

## 9. @CrossOrigin cho cấu hình theo controller

Nếu chỉ một controller hoặc method cần chính sách CORS riêng, có thể dùng `@CrossOrigin`:

~~~java
@RestController
@RequestMapping("/api/reports")
@CrossOrigin(
        origins = "https://app.example.com",
        methods = {
                RequestMethod.GET,
                RequestMethod.POST
        },
        allowedHeaders = {
                "Content-Type",
                "Authorization"
        },
        exposedHeaders = "X-Request-Id",
        allowCredentials = "true",
        maxAge = 3600)
public class ReportController {
    // Endpoints
}
~~~

Có thể đặt annotation ở class hoặc method. Cấu hình class áp dụng cho các method trong controller; method-level config có thể bổ sung hoặc điều chỉnh.

Spring cho phép kết hợp global CORS và local CORS. Các danh sách như origins, methods, headers và exposed headers thường được kết hợp theo hướng additive; các thuộc tính đơn như allowCredentials và maxAge có thể bị local config ghi đè.

Điều này có nghĩa thêm một annotation local có thể mở rộng danh sách origin/method được phép so với global config. Hãy review cả hai nơi khi điều tra vì sao một route có quyền rộng hơn dự kiến.

Dùng một chính sách global nhất quán cho API thông thường; chỉ dùng annotation cho ngoại lệ có lý do rõ ràng.

## 10. CorsWebFilter cho functional endpoints

Với functional routing qua `RouterFunction` và `HandlerFunction`, có thể dùng `CorsWebFilter`:

~~~java
@Configuration
public class FunctionalCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.com"));

        config.setAllowedMethods(List.of(
                "GET", "POST", "PUT"));

        config.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id"));

        config.setExposedHeaders(List.of(
                "Location",
                "X-Request-Id"));

        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);

        return new CorsWebFilter(source);
    }
}
~~~

`CorsWebFilter` nhận `CorsConfigurationSource` và xử lý CORS ở tầng WebFilter. Đây là lựa chọn phù hợp khi ứng dụng dùng functional endpoints hoặc cần filter-level processing.

Không đăng ký đồng thời nhiều lớp CORS trùng nhau nếu không có chủ đích. Nếu vừa cấu hình global HandlerMapping, vừa có CorsWebFilter, vừa có gateway thêm header, response có thể xuất hiện header trùng hoặc chính sách không nhất quán.

## 11. Tích hợp với Spring Security WebFlux

Khi có Spring Security, thứ tự xử lý rất quan trọng.

CORS phải được xử lý trước security authorization. Preflight OPTIONS không mang cookie cross-origin. Nếu Spring Security chạy trước và yêu cầu authenticated session, nó có thể từ chối OPTIONS vì không có session cookie. Browser khi đó không gửi request thực tế.

Spring Security reactive hỗ trợ CORS bằng `ServerHttpSecurity.cors` và đặt `CorsWebFilter` ở đúng vị trí trong security chain.

Ví dụ:

~~~java
@Configuration
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of(
                "https://app.example.com",
                "https://admin.example.com"));

        config.setAllowedMethods(List.of(
                "GET", "POST", "PUT", "PATCH", "DELETE"));

        config.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id",
                "X-CSRF-TOKEN"));

        config.setExposedHeaders(List.of(
                "Location",
                "X-Request-Id"));

        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().permitAll())
                .build();
    }
}
~~~

Cần dependency `spring-boot-starter-security` ngoài `spring-boot-starter-webflux`.

Điểm quan trọng:

- CORS source chứa allowlist dùng chung.
- `http.cors(...)` tích hợp CORS vào Spring Security filter chain.
- Security vẫn xác thực và phân quyền request thực tế.
- Preflight được xử lý trước authentication/authorization nên không cần session cookie ở OPTIONS.
- Không đăng ký thêm một CorsWebFilter độc lập cùng chính sách nếu Spring Security đã quản lý CORS cho chain đó.

Nếu ứng dụng dùng cookie session, giữ CSRF protection phù hợp với authentication model. CORS không thay thế CSRF token.

## 12. Cookie, SameSite và cross-origin credentials

Origin và site là hai khái niệm khác nhau.

Ví dụ:

- Frontend: `https://app.example.com`
- API: `https://api.example.com`

Hai URL khác origin nhưng thường cùng site theo registrable domain. Vì vậy, chính sách SameSite của cookie không hoàn toàn giống quy tắc same-origin của CORS.

Nếu frontend và API thực sự cross-site, cookie thường cần:

~~~http
Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly; SameSite=None
~~~

Lưu ý:

- `SameSite=None` yêu cầu `Secure` trong browser hiện đại.
- `HttpOnly` ngăn JavaScript đọc cookie trực tiếp.
- Browser privacy/third-party-cookie policies vẫn có thể chặn cookie ngay cả khi CORS đúng.
- Cookie domain/path và HTTPS phải phù hợp.
- Frontend cần dùng `credentials: "include"` nếu muốn gửi cookie cross-origin.

Ví dụ:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Nếu browser không gửi cookie, hãy kiểm tra DevTools Application/Storage và Network để xem cookie có bị loại do SameSite, Secure, domain, expiration hoặc third-party cookie policy hay không. Đừng chỉ tăng CORS wildcard để sửa lỗi cookie.

## 13. CORS không thay thế authentication, authorization và CSRF

CORS chủ yếu quyết định browser có chia sẻ response với JavaScript cross-origin hay không. Nó không phải firewall và không bảo vệ endpoint khỏi mọi HTTP client.

Một số hệ quả:

1. curl, Postman và backend service có thể gửi request mà không cần CORS.
2. Một simple cross-origin request có thể được gửi tới server dù browser cuối cùng không cho JavaScript đọc response.
3. Server vẫn phải xác thực người dùng và kiểm tra quyền trên từng resource.
4. Cookie-authenticated state-changing endpoint vẫn cần CSRF protection phù hợp.
5. Không được xem một origin được allowlist là một danh tính user đáng tin cậy.

Ví dụ, một form HTML có thể gửi POST đơn giản từ một website khác. Nếu server dựa vào cookie session và không có CSRF defense, request có thể được xử lý dù attacker không đọc được response.

Vì vậy:

- Dùng Spring Security authentication.
- Dùng authorization theo user/role/resource.
- Dùng CSRF token hoặc chiến lược CSRF phù hợp với session cookie.
- Đặt SameSite cookie theo threat model.
- Giới hạn CORS origins để giảm website có thể đọc response.
- Không cho phép credentialed CORS với mọi origin.

CORS là một lớp browser policy bổ sung, không phải cơ chế phân quyền nghiệp vụ.

## 14. Cache, Vary và preflight

Khi server trả `Access-Control-Allow-Origin` dựa trên origin của request, response khác nhau theo Origin. Shared cache hoặc reverse proxy cần biết điều đó.

Dùng:

~~~http
Vary: Origin
~~~

Với preflight response, cache còn phải phân biệt method và request headers được hỏi; các response CORS thường dùng:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring CORS processing quản lý các Vary header tương ứng. Nếu gateway hoặc cache đứng trước ứng dụng, kiểm tra xem tầng đó có giữ lại Vary hay không.

Không cache response có dữ liệu user-specific như thể nó là public response. CORS không tự làm response an toàn để chia sẻ qua cache.

## 15. Private Network Access

Một số browser triển khai thêm kiểm tra khi website public muốn gọi tài nguyên ở địa chỉ mạng riêng, chẳng hạn thiết bị trong LAN hoặc service nội bộ.

Spring Framework hỗ trợ cấu hình `allowPrivateNetwork` trên `CorsConfiguration`/`CorsRegistration` ở các phiên bản có API này.

Chỉ bật khi ứng dụng thực sự cần browser truy cập private network và đã có threat model phù hợp. Không bật private network access cùng allow-all origin. Hãy giới hạn origin cụ thể và kiểm tra browser behavior/version đang hỗ trợ chính sách này.

Đây là một chính sách bổ sung bên cạnh CORS thông thường, không phải lý do để mở rộng allowlist cho mọi website.

## 16. Ví dụ Spring Boot WebFlux Java 17+ chạy được

Ví dụ này tạo API:

~~~text
GET /api/profile
PUT /api/profile
~~~

Frontend được phép:

~~~text
https://app.example.com
https://admin.example.com
~~~

API chấp nhận credentials mode include, cho phép PUT và các header Authorization, Content-Type, X-Request-Id. Response expose X-Request-Id và Location.

### 16.1. Cấu trúc dự án

~~~text
webflux-cors-demo/
  pom.xml
  src/main/java/example/cors/CorsDemoApplication.java
  src/main/java/example/cors/WebCorsConfiguration.java
  src/main/java/example/cors/ProfileController.java
  src/test/java/example/cors/CorsIntegrationTest.java
~~~

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Spring Boot BOM quản lý Spring Framework, Reactor và các dependency tương thích.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-cors-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

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

### 16.3. Class khởi động

**src/main/java/example/cors/CorsDemoApplication.java**

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### 16.4. Cấu hình allowlist

**src/main/java/example/cors/WebCorsConfiguration.java**

~~~java
package example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods(
                        "GET", "POST", "PUT", "PATCH", "DELETE")
                .allowedHeaders(
                        "Authorization",
                        "Content-Type",
                        "X-Request-Id",
                        "X-CSRF-TOKEN")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id")
                .allowCredentials(true)
                .maxAge(3600);
    }
}
~~~

### 16.5. Controller

**src/main/java/example/cors/ProfileController.java**

~~~java
package example.cors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    public Mono<ResponseEntity<Map<String, String>>> read() {
        return Mono.just(
                ResponseEntity.ok()
                        .header("X-Request-Id", "demo-123")
                        .body(Map.of(
                                "id", "user-1",
                                "displayName", "WebFlux learner")));
    }

    @PutMapping
    public Mono<Map<String, String>> update(
            @RequestBody Map<String, String> body) {

        return Mono.just(body);
    }
}
~~~

Controller không tự kiểm tra Origin. CORS policy được áp dụng ở WebFlux infrastructure; authentication và authorization thuộc security layer của ứng dụng.

### 16.6. Kiểm thử preflight và actual response

**src/test/java/example/cors/CorsIntegrationTest.java**

~~~java
package example.cors;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders() {
        client.options()
                .uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header(
                        "Access-Control-Request-Headers",
                        "authorization,content-type,x-request-id")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com")
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials",
                        "true")
                .expectHeader().exists(
                        "Access-Control-Allow-Methods")
                .expectHeader().exists(
                        "Access-Control-Allow-Headers")
                .expectHeader().valueEquals(
                        "Access-Control-Max-Age",
                        "3600");
    }

    @Test
    void actualResponseContainsCorsHeaders() {
        client.get()
                .uri("/api/profile")
                .header("Origin", "https://app.example.com")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin",
                        "https://app.example.com")
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials",
                        "true")
                .expectHeader().exists(
                        "Access-Control-Expose-Headers")
                .expectHeader().valueEquals(
                        "X-Request-Id",
                        "demo-123");
    }

    @Test
    void rejectsOriginOutsideAllowlist() {
        client.options()
                .uri("/api/profile")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "PUT")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Các test này kiểm tra:

- OPTIONS preflight từ origin được phép.
- PUT được khai báo trong allowlist.
- Authorization, Content-Type và X-Request-Id được chấp nhận.
- Response thực tế có CORS headers và exposed headers.
- Origin không nằm trong allowlist bị từ chối.

WebTestClient kiểm tra HTTP response. Nó không mô phỏng toàn bộ chính sách thực thi CORS của browser; cần thêm browser test cho cookie và third-party-cookie behavior nếu ứng dụng dùng session credentials.

### 16.7. Chạy test

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

Nếu test thành công, cả ba test method hoàn tất. Đây là ví dụ tích hợp WebFlux trên embedded server do Spring Boot quản lý.

## 17. Gửi request từ browser

Ví dụ request có cookie credentials và custom headers:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/profile",
  {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": "browser-123",
      "Authorization": "Bearer " + token
    },
    body: JSON.stringify({
      displayName: "Reactive learner"
    })
  }
);

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const requestId = response.headers.get("X-Request-Id");
const profile = await response.json();
~~~

Browser sẽ preflight vì method PUT và các custom headers. Nếu preflight hợp lệ, browser mới gửi PUT thực tế.

`credentials: "include"` yêu cầu browser dùng credentials cross-origin nếu cookie/browser policy cho phép. Server phải trả origin cụ thể và `Access-Control-Allow-Credentials: true`. Header `X-Request-Id` chỉ đọc được từ JavaScript vì server đã expose nó.

Nếu chỉ dùng bearer token và không cần cookie cross-origin, có thể bỏ `credentials: "include"`; vẫn phải cho phép header Authorization trong preflight.

## 18. Kiểm tra preflight bằng curl

Gửi OPTIONS để xem response header:

~~~bash
curl -i -X OPTIONS \
  https://api.example.com/api/profile \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
~~~

Response mong đợi có các header tương tự:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Expose-Headers: Location,X-Request-Id
Access-Control-Max-Age: 3600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Kiểm tra response thực tế:

~~~bash
curl -i \
  https://api.example.com/api/profile \
  -H "Origin: https://app.example.com"
~~~

`curl` không thực thi CORS như browser. Nó chỉ giúp xem server có trả header đúng hay không. Một lệnh curl thành công không chứng minh browser sẽ chấp nhận request; browser còn áp dụng Fetch/CORS, cookie và privacy policy.

## 19. Chẩn đoán lỗi CORS trong browser

Khi frontend báo CORS error, kiểm tra Network tab theo thứ tự:

1. Có OPTIONS preflight không?
2. OPTIONS có status 200/204 không?
3. `Origin` gửi lên có đúng scheme, host, port không?
4. `Access-Control-Allow-Origin` có khớp origin không?
5. `Access-Control-Allow-Methods` có chứa method thực tế không?
6. `Access-Control-Allow-Headers` có chứa mọi custom request header không?
7. Nếu dùng credentials include, response có ACAO cụ thể và ACAC true không?
8. Request thực tế có được gửi sau OPTIONS không?
9. Actual response có ACAO/ACAC phù hợp không?
10. Nếu JavaScript không đọc được response header, header đó đã nằm trong `Access-Control-Expose-Headers` chưa?
11. Cookie có bị browser loại do SameSite, Secure hoặc third-party-cookie policy không?
12. Gateway, reverse proxy hoặc CDN có ghi đè/nhân đôi CORS header không?

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| OPTIONS trả 401/403 | Security chặn preflight trước CORS | Tích hợp CORS vào Spring Security để xử lý trước authorization |
| No Access-Control-Allow-Origin | Không có config match hoặc origin không được phép | Kiểm tra URL mapping và exact origin |
| Wildcard origin không dùng được với cookie | Credentials mode include không chấp nhận ACAO `*` | Dùng danh sách origin cụ thể hoặc pattern giới hạn |
| Method PUT bị từ chối | PUT chưa nằm trong allowedMethods | Thêm đúng method thực tế |
| Header Authorization bị từ chối | Header chưa nằm trong allowedHeaders | Thêm Authorization rõ ràng |
| JSON POST bị preflight fail | Content-Type application/json chưa được cho phép | Thêm Content-Type vào allowedHeaders |
| Request thực tế được gửi nhưng JS không đọc response | Actual response thiếu CORS headers hoặc credentials mismatch | Kiểm tra response thực tế, không chỉ OPTIONS |
| JS không đọc được X-Request-Id | Header chưa được expose | Thêm X-Request-Id vào exposedHeaders |
| Cookie không xuất hiện trong request | Frontend thiếu credentials include hoặc cookie policy chặn | Kiểm tra fetch/XHR và thuộc tính cookie |
| curl hoạt động nhưng browser thất bại | curl không enforce CORS | Kiểm tra Network tab và response header browser nhận |
| Có hai Access-Control-Allow-Origin | Gateway và app cùng thêm header | Chọn một layer làm chủ CORS |
| Chỉ lỗi ở response 401/500 | Error response do proxy/security tạo thiếu CORS header | Áp dụng CORS tại đúng layer trả response lỗi |

## 20. Các lỗi cấu hình nguy hiểm

### 20.1. Phản chiếu mọi Origin

Không làm:

~~~java
response.getHeaders().set(
        "Access-Control-Allow-Origin",
        request.getHeaders().getOrigin());
~~~

Nếu không kiểm tra allowlist, bất kỳ website nào cũng có thể được phản chiếu thành origin được phép. Khi đi cùng credentials, điều này có thể cho website độc hại đọc response chứa dữ liệu user.

Dùng Spring CorsConfiguration để kiểm tra origin trước khi phản chiếu.

### 20.2. Cho phép mọi origin cùng credentials

Không dùng:

~~~java
.allowedOrigins("*")
.allowCredentials(true)
~~~

Tổ hợp này không hợp lệ và không phải cách sửa lỗi CORS. Hãy khai báo exact origins hoặc một tập allowedOriginPatterns có giới hạn.

### 20.3. Mở mọi method và header

Cấu hình:

~~~java
.allowedMethods("*")
.allowedHeaders("*")
~~~

có thể tiện cho môi trường thử nghiệm nhưng mở rộng bề mặt truy cập. Chỉ cho phép method và header API thực sự dùng.

### 20.4. Dùng CORS như authentication

Không coi việc Origin nằm trong allowlist là bằng chứng user đã đăng nhập. Một HTTP client không phải browser có thể giả mạo Origin. Authentication và authorization phải được kiểm tra độc lập.

### 20.5. Cho phép Origin: null tùy tiện

Không thêm `null` vào allowlist chỉ để làm file:// hoặc sandbox iframe chạy được. Hãy xác định nguồn request và threat model trước khi cho phép.

## 21. Checklist trước khi đưa CORS vào production

- [ ] Xác định đầy đủ frontend origin theo scheme, host và port.
- [ ] Không đưa path hoặc trailing slash vào origin.
- [ ] Dùng exact allowedOrigins khi có tập frontend cố định.
- [ ] Chỉ dùng allowedOriginPatterns cho miền preview/tenant đã giới hạn.
- [ ] Không dùng wildcard origin với credentials.
- [ ] Chỉ bật allowCredentials khi thật sự cần cookie/HTTP credentials cross-origin.
- [ ] Hiểu rằng preflight không gửi cookie nhưng actual request có thể dùng credentials.
- [ ] Liệt kê method thực tế trong allowedMethods.
- [ ] Liệt kê request headers cần thiết trong allowedHeaders.
- [ ] Expose response headers mà frontend cần đọc.
- [ ] Đặt maxAge hợp lý và hiểu browser có thể giới hạn cache.
- [ ] Xử lý CORS trước Spring Security authentication/authorization.
- [ ] Không đăng ký nhiều filter/config CORS trùng nhau.
- [ ] Dùng Vary phù hợp khi response thay đổi theo Origin.
- [ ] Không coi CORS là authentication, authorization hoặc CSRF protection.
- [ ] Cookie cross-site có SameSite/Secure phù hợp.
- [ ] Có test preflight thành công, origin bị từ chối và actual response.
- [ ] Có browser integration test nếu dùng cookie credentials.
- [ ] Kiểm tra CORS header tại gateway/CDN/proxy và error response.
- [ ] Không log token, cookie hoặc thông tin nhạy cảm khi debug.

## 22. Tự kiểm tra

**Câu 1.** Origin gồm những thành phần nào?

Scheme, host và port. Path không thuộc origin.

**Câu 2.** Khi nào browser gửi CORS preflight?

Khi request cần kiểm tra trước, thường do method không safelisted hoặc có request header không safelisted.

**Câu 3.** Preflight dùng HTTP method nào?

OPTIONS, kèm Access-Control-Request-Method và có thể có Access-Control-Request-Headers.

**Câu 4.** Preflight có mang cookie cross-origin không?

Không. Preflight dùng credentials mode same-origin; request thực tế theo sau vẫn có thể dùng credentials include.

**Câu 5.** Vì sao response có credentials không được dùng Access-Control-Allow-Origin: *?

Browser yêu cầu ACAO khớp chính xác Origin request khi credentials mode là include.

**Câu 6.** Access-Control-Allow-Credentials có giá trị nào hợp lệ?

Giá trị chính xác là `true`, chữ thường.

**Câu 7.** allowedOrigins và allowedOriginPatterns khác nhau thế nào?

allowedOrigins nhận danh sách origin cụ thể hoặc wildcard đặc biệt; allowedOriginPatterns hỗ trợ pattern và Spring trả origin thực tế đã match.

**Câu 8.** Authorization có cần khai báo trong allowedHeaders không?

Có. Đây là request header cần được cho phép rõ ràng trong preflight.

**Câu 9.** allowCredentials(true) có tự gửi cookie không?

Không. Browser client phải dùng credentials mode phù hợp và cookie phải đáp ứng domain, Secure, SameSite và browser privacy policy.

**Câu 10.** Khi dùng Spring Security WebFlux, CORS nên chạy ở đâu?

Trước security authorization. Dùng `ServerHttpSecurity.cors` với CorsConfigurationSource để Spring Security đặt CorsWebFilter đúng thứ tự.

**Câu 11.** CORS có ngăn curl gọi API không?

Không. CORS là browser policy; server vẫn phải kiểm tra authentication, authorization và CSRF.

**Câu 12.** Vì sao response cần Access-Control-Expose-Headers?

Để JavaScript đọc các response header ngoài nhóm safelisted, ví dụ Location hoặc X-Request-Id.

**Câu 13.** maxAge dùng để làm gì?

Cho browser biết thời gian cache kết quả preflight; nó không cache response body của API.

**Câu 14.** Vì sao chỉ test OPTIONS bằng curl là chưa đủ?

curl không thực thi browser CORS hoặc cookie policy. Cần test actual request và browser Network behavior.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework — CORS trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): preflight, actual request, @CrossOrigin, global configuration, CorsWebFilter và credentialed request.
- [Spring Framework — CorsConfiguration JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): allowedOrigins, allowedOriginPatterns, allowedMethods, allowedHeaders, allowCredentials, maxAge và allowPrivateNetwork.
- [Spring Framework — CorsRegistration JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/CorsRegistration.html): cấu hình URL-based CORS cho WebFlux.
- [Spring Framework — CorsWebFilter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html): reactive CORS WebFilter.
- [Spring Security — CORS cho Reactive Applications](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/cors.html): CORS phải được xử lý trước Spring Security và cấu hình CorsConfigurationSource.
- [ServerHttpSecurity.CorsSpec JavaDoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): cấu hình CORS và CorsConfigurationSource trong reactive security chain.
- [WHATWG Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#cors-protocol): preflight, credentials mode, request/response headers, wildcard restrictions và CORS check.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): giải thích thực hành về browser preflight, credentials và CORS response headers.

**Ghi nhớ:** Xây allowlist từ origin thật của frontend, cấu hình method và header cụ thể, và chỉ bật credentials khi có nhu cầu. Preflight OPTIONS không mang cookie nhưng phải cho phép chính sách của request thực tế; response credentialed cần ACAO khớp chính xác Origin và ACAC là true. Trong WebFlux có thể dùng WebFluxConfigurer hoặc CorsWebFilter; khi tích hợp Spring Security, dùng ServerHttpSecurity.cors để CORS được xử lý trước authorization. CORS không thay thế authentication, authorization hay CSRF protection.