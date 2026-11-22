# Thứ tự CORS, preflight và filter bảo mật trong Spring WebFlux

Trong ứng dụng **Spring WebFlux** có Spring Security, request từ một frontend khác origin phải đi qua hai cơ chế độc lập: **CORS** (Cross-Origin Resource Sharing) và **authentication/authorization**. Nếu CORS được xử lý quá muộn, trình duyệt có thể gửi một request **preflight** hợp lệ nhưng server lại yêu cầu đăng nhập trước khi kiểm tra CORS. Hậu quả thường thấy là `401 Unauthorized` hoặc `403 Forbidden` cho `OPTIONS`, dù request GET/POST thực tế có token hợp lệ.

**Quy tắc quan trọng nhất:** CORS phải có cơ hội xử lý preflight **trước** bước xác thực và phân quyền. Spring Security WebFlux hỗ trợ điều đó bằng CORS integration trong `SecurityWebFilterChain` hoặc bằng một `CorsWebFilter` được đăng ký ở ngoài và chạy trước security. Không chỉ đơn giản thêm `OPTIONS /** permitAll` rồi coi như đã cấu hình CORS.

Bài này tập trung vào luồng browser → preflight → WebFilter/Security → controller; cách sắp thứ tự filter trong reactive stack; cấu hình origin/method/header/credentials an toàn; phân biệt CORS với CSRF; và một ứng dụng Java 17 có kiểm thử tích hợp bằng WebTestClient.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt same-origin policy, CORS và authentication.
2. Nhận diện request preflight theo `OPTIONS`, `Origin` và `Access-Control-Request-Method`.
3. Giải thích vì sao preflight không được chặn bởi authentication trước khi CORS xử lý.
4. Phân biệt preflight với actual CORS request và OPTIONS thông thường.
5. Biết luồng WebFilter, Spring Security `WebFilterChainProxy` và HandlerMapping trong WebFlux.
6. Cấu hình `ServerHttpSecurity.cors(...)` với reactive `CorsConfigurationSource`.
7. Cấu hình `CorsWebFilter` riêng và xác định thứ tự bằng `@Order` nếu chọn cách đó.
8. Phân biệt `SecurityWebFiltersOrder` của filter bên trong security chain với thứ tự WebFilter bên ngoài.
9. Chọn `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `allowCredentials` và `maxAge`.
10. Hiểu tại sao `@CrossOrigin` hoặc `WebFluxConfigurer.addCorsMappings` có thể không đủ nếu Security chặn preflight sớm.
11. Tránh các lỗi cấu hình với nhiều `SecurityWebFilterChain` hoặc nhiều CORS processor.
12. Kiểm thử preflight hợp lệ, origin bị cấm, header/method bị cấm và request thật có/không có credential.
13. Phân biệt CORS với CSRF; không tắt CSRF chỉ để sửa lỗi preflight.

## 2. Origin, same-origin policy và CORS

Một **origin** gồm ba thành phần: scheme, host và port. Hai địa chỉ sau khác origin dù cùng host:

~~~text
https://app.example.test
https://api.example.test
~~~

Hai địa chỉ sau cũng khác origin vì port khác nhau:

~~~text
http://localhost:3000
http://localhost:8080
~~~

Browser áp dụng same-origin policy cho nhiều loại thao tác JavaScript. Khi frontend ở `https://app.example.test` gọi API ở `https://api.example.test`, trình duyệt cần một chính sách CORS từ API để biết frontend có được phép đọc response hay không.

CORS được thể hiện qua các HTTP header, ví dụ:

~~~http
Origin: https://app.example.test
Access-Control-Allow-Origin: https://app.example.test
~~~

Header `Origin` do browser gửi để cho server biết nơi xuất phát request. Header `Access-Control-Allow-Origin` do server trả để browser quyết định có cho JavaScript tiếp cận response.

### 2.1. CORS không xác thực người dùng

CORS không xác định user là ai. Việc origin được cho phép không có nghĩa request được phép đọc dữ liệu nhạy cảm nếu thiếu token hoặc cookie hợp lệ.

- **CORS:** ứng dụng web ở origin nào được phép gọi và đọc response trong trình duyệt?
- **Authentication:** người gọi là ai?
- **Authorization:** người đó có quyền truy cập tài nguyên cụ thể không?
- **CSRF:** thao tác có tác dụng thay đổi trạng thái có được thực hiện ngoài ý muốn bằng credential được trình duyệt tự gửi không?

Server vẫn phải kiểm tra authentication và authorization cho request thực tế. Client như curl, Postman hoặc một service backend không bị browser same-origin policy ràng buộc. Vì vậy **không dùng CORS như cơ chế bảo vệ API khỏi client không phải browser**.

### 2.2. CORS cũng không phải reverse proxy allowlist

Một origin được allowlist để browser đọc response khác với IP/network allowlist. Một client không phải browser có thể tự đặt Origin tùy ý hoặc không gửi Origin. Phân quyền API phải dựa vào principal, scope, role, policy, mTLS hoặc cơ chế đáng tin cậy khác.

## 3. Preflight là gì?

Browser gửi **preflight** để hỏi server trước khi gửi actual request trong một số trường hợp: dùng HTTP method không thuộc safelisted methods, sử dụng request header không được CORS-safelisted (như Authorization) hoặc Content-Type không thuộc các loại đơn giản được CORS-safelisted.

Ví dụ frontend ở `https://app.example.test` muốn gọi GET có header Authorization:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/items",
  {
    method: "GET",
    headers: { Authorization: "Bearer token-from-auth-flow" },
    credentials: "include"
  }
);
~~~

Browser có thể gửi trước:

~~~http
OPTIONS /api/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

**Request preflight thường không mang cookie hoặc Authorization credential.** `Access-Control-Request-Headers: authorization` chỉ nói rằng actual request dự kiến sẽ gửi header Authorization; bản thân preflight chưa cung cấp bearer token.

Nếu hợp lệ, server trả lời, ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Sau đó browser mới gửi actual GET với credential theo cấu hình fetch. Lưu ý response code có thể là 200 hoặc 204 tùy server/framework; điều quan trọng là success status và các CORS response headers phù hợp.

### 3.1. Điều kiện nhận diện preflight

Một CORS preflight chuẩn có:

1. HTTP method `OPTIONS`.
2. Header `Origin`.
3. Header `Access-Control-Request-Method` chứa HTTP method của actual request.

`Access-Control-Request-Headers` có thể có hoặc không, tùy actual request dự định gửi những header nào.

**Không phải mọi OPTIONS đều là CORS preflight.** Một request `OPTIONS /api/items` không có Origin và Access-Control-Request-Method không được hiểu là preflight chỉ vì method là OPTIONS.

### 3.2. CORS simple request và actual request

Một số request đơn giản có thể không cần preflight, nhưng vẫn mang Origin. Server vẫn phải trả header CORS phù hợp cho actual response nếu muốn browser đọc được.

Ví dụ:

~~~http
GET /api/public-data HTTP/1.1
Origin: https://app.example.test
~~~

Response thành công không có `Access-Control-Allow-Origin` vẫn có thể bị browser từ chối truy cập từ JavaScript, dù HTTP status thực là 200.

### 3.3. Preflight cache

`Access-Control-Max-Age` cho browser biết thời gian có thể cache kết quả preflight theo giới hạn mà browser áp dụng. Đây không phải cache của actual API response, và không làm mất hiệu lực của authentication/authorization trên các actual request tiếp theo.

## 4. Vì sao thứ tự CORS trước Spring Security lại quan trọng?

Giả sử API `/api/items` yêu cầu authentication cho mọi request:

~~~text
Browser                    WebFlux Server

OPTIONS /api/items
Origin: app.example.test
AC-Request-Method: GET
(no Authorization)   -------->
                              Security kiểm tra trước
                              => user anonymous
                      <-------- 401 Unauthorized

Browser dừng; actual GET không được gửi
~~~

Request thực tế có token hợp lệ cũng không cứu được tình huống này vì browser đã dừng sau preflight không thành công.

Luồng đúng:

~~~text
Browser                    WebFlux Server

OPTIONS + Origin +
Access-Control-Request-Method
(no credentials)    -------->
                              CORS kiểm tra origin/method/headers
                              => hợp lệ
                      <-------- 200 + Access-Control-Allow-*

GET /api/items
Authorization: ...  -------->
                              CORS kiểm tra actual request
                              Authentication xác minh credential
                              Authorization kiểm tra quyền
                              Handler/controller
                      <-------- 200 + data + CORS headers
~~~

Với preflight không hợp lệ, CORS processor phải từ chối, thường bằng `403 Invalid CORS request`. Không có lý do chuyển tiếp preflight không hợp lệ vào business controller.

### 4.1. “Trước Security” hiểu chính xác thế nào?

Không bắt buộc phải có một WebFilter bean nằm hoàn toàn ngoài Spring Security. Có hai cách hợp lệ:

- **CORS nằm trong SecurityWebFilterChain:** gọi `http.cors(cors -> cors.configurationSource(source))`; Spring Security đặt CORS processor ở giai đoạn CORS trong chuỗi nội bộ trước authentication/authorization.
- **CorsWebFilter độc lập:** tạo một WebFilter chạy đủ sớm trước `WebFilterChainProxy` của Spring Security; preflight có thể được xử lý và kết thúc trước khi tới Security.

Điểm cốt lõi là CORS processor **thực thi trước các bước có thể từ chối anonymous request**, không phải cứ có annotation hoặc bean tên “cors” là đủ.

## 5. Các tầng filter và handler trong WebFlux

WebFlux xử lý request qua một chuỗi `WebFilter` rồi tới `WebHandler`/`DispatcherHandler`, sau đó là `HandlerMapping` và controller.

Spring Security reactive tích hợp qua `WebFilterChainProxy`, bên trong có các `SecurityWebFilterChain` và security filters.

~~~text
HTTP server
   |
   v
WebFilter chain (ordered by @Order / Ordered)
   |
   +--> CorsWebFilter độc lập (nếu dùng)
   |
   +--> Spring Security WebFilterChainProxy
   |       |
   |       +--> chọn SecurityWebFilterChain
   |       |
   |       +--> internal CORS (nếu cấu hình)
   |       +--> Authentication
   |       +--> Authorization
   |       +--> các security filters khác
   |
   +--> WebFilter nghiệp vụ còn lại
   |
   v
DispatcherHandler
   |
   v
HandlerMapping / controller / functional endpoint
~~~

Sơ đồ có tính khái quát: thứ tự chính xác phụ thuộc bean và security chain được cấu hình. Không nên mặc định một custom WebFilter nằm trước hoặc sau toàn bộ security nếu chưa xem `@Order` của nó.

### 5.1. Order của WebFilter độc lập

Khi khai báo một `WebFilter` thành Spring bean, dùng `@Order` trên bean hoặc implement `Ordered` để xác định ưu tiên. Giá trị order nhỏ hơn được thực thi sớm hơn. Đối với một independent CorsWebFilter, có thể chọn `Ordered.HIGHEST_PRECEDENCE` để bảo đảm nó chạy rất sớm.

### 5.2. SecurityWebFiltersOrder là thứ tự khác

`SecurityWebFiltersOrder` quy định vị trí tương đối của các filter **bên trong** Spring Security chain, chẳng hạn CORS, authentication hay authorization. Nó không thay thế `@Order` của mọi WebFilter bean ngoài security.

Ví dụ khi cần custom authentication filter trong security chain, Spring Security có API `addFilterAt` hoặc `addFilterBefore`/`addFilterAfter` theo SecurityWebFiltersOrder. Với CORS, ưu tiên cơ chế `http.cors(...)` thay vì tự đặt một custom filter vào một vị trí phỏng đoán.

### 5.3. HandlerMapping CORS có thể chạy quá muộn

Spring WebFlux hỗ trợ CORS trên HandlerMapping thông qua `@CrossOrigin` và `WebFluxConfigurer.addCorsMappings`. Khi không có Spring Security chặn từ trước, chúng có thể hoạt động tốt.

Nhưng nếu Security từ chối anonymous OPTIONS ngay trong WebFilter chain, request **không đến được HandlerMapping**. Do đó cấu hình CORS tại controller không đủ để sửa thứ tự security. Với Spring Security WebFlux, cấu hình CORS integration ở vị trí trước authentication/authorization.

## 6. Phương án khuyến nghị: CORS trong SecurityWebFilterChain

Với API WebFlux được bảo vệ bằng Spring Security, một cách rõ ràng là tạo reactive `UrlBasedCorsConfigurationSource` và cấp nó cho `ServerHttpSecurity.cors`.

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.test")
    );
    config.setAllowedMethods(List.of("GET"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Trace-Id")
    );
    config.setAllowCredentials(true);
    config.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", config);
    return source;
}

@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        UrlBasedCorsConfigurationSource corsConfigurationSource) {

    return http
        .cors(cors ->
            cors.configurationSource(corsConfigurationSource)
        )
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là cấu hình trọng tâm; ví dụ ứng dụng hoàn chỉnh ở phần sau còn có import, controller và user store.

**Tại sao cách này hoạt động?**

- Source cung cấp policy CORS cho URL /api/**.
- Security tích hợp CORS processor ở đúng vị trí trong chain.
- Preflight hợp lệ được xử lý mà không cần credential.
- Actual request tiếp tục qua authentication/authorization.
- Origin bị cấm, HTTP method hoặc request header bị cấm sẽ bị CORS processor từ chối.

### 6.1. Import đúng package reactive

CORS của WebFlux dùng:

~~~java
org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource
org.springframework.web.cors.reactive.CorsConfigurationSource
org.springframework.web.cors.reactive.CorsWebFilter
~~~

Không nhập nhầm `org.springframework.web.cors.UrlBasedCorsConfigurationSource` hoặc servlet `CorsFilter`. Chúng thuộc mô hình Servlet/Spring MVC, không phải reactive WebFlux.

`CorsConfiguration` (đối tượng policy) dùng package chung:

~~~java
org.springframework.web.cors.CorsConfiguration
~~~

### 6.2. Có cần permitAll OPTIONS không?

Trong cấu hình trên, không bắt buộc có:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Preflight hợp lệ được CORS integration xử lý trước authorization. Nếu ứng dụng có OPTIONS endpoint thực sự không phải CORS preflight, endpoint đó vẫn phải tuân theo chính sách authorization phù hợp.

Cho phép mọi OPTIONS chỉ giải quyết một phần chuyện authorization; nó **không tạo** các header `Access-Control-Allow-*` và không kiểm tra origin/method/header. Do đó `permitAll OPTIONS` không thay thế CORS processor.

## 7. Phương án thay thế: CorsWebFilter chạy trước Security

Một cách hợp lệ khác là đăng ký `CorsWebFilter` ở tầng WebFilter độc lập.

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter corsWebFilter(
        UrlBasedCorsConfigurationSource corsSource) {

    return new CorsWebFilter(corsSource);
}
~~~

Cách này xử lý preflight sớm ở ngoài security filter chain. Tuy nhiên, hãy **chọn một cơ chế quản lý CORS chính** cho cùng phạm vi URL:

- Nếu dùng `http.cors(...configurationSource...)`, không tự thêm CorsWebFilter độc lập mà chưa có lý do rõ ràng.
- Nếu dùng CorsWebFilter độc lập, tránh đồng thời tạo CORS processor thứ hai trong Spring Security hoặc HandlerMapping với policy khác.
- Nếu cần nhiều policy cho nhiều path, thể hiện chúng trong cùng một source hoặc thiết kế chain rõ ràng.

**Không ghép cả hai cách vào một ứng dụng mẫu một cách máy móc.** Hai processor CORS cùng xử lý request có thể tạo header trùng, chính sách khác nhau hoặc hành vi debug khó hiểu.

### 7.1. Khi nào dùng CorsWebFilter ngoài chain?

Có thể hữu ích khi muốn CORS áp dụng chung cho nhiều `SecurityWebFilterChain` hoặc nhiều kiểu WebFlux handler (annotated/functional) và policy được quản lý tập trung trước Security.

### 7.2. Khi nào dùng http.cors?

Thích hợp khi muốn CORS là một phần rõ ràng của cấu hình Security, nhất là API có ít security chain. Dù chọn phương án nào, hãy test preflight thực tế qua HTTP chứ không chỉ kiểm tra có bean được tạo.

## 8. Cấu hình CorsConfiguration an toàn

Các thuộc tính chính:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| `allowedOrigins` | Origin chính xác được phép | https://app.example.test |
| `allowedOriginPatterns` | Pattern origin có kiểm soát | https://*.example.test |
| `allowedMethods` | HTTP methods **thực tế** được phép | GET, POST |
| `allowedHeaders` | Request headers client được phép gửi | Authorization, Content-Type |
| `exposedHeaders` | Response headers được JS đọc ngoài safelist | X-Request-Id |
| `allowCredentials` | Cho phép credentialed CORS request | true/false |
| `maxAge` | Thời gian cache preflight (giây) | 1800 |

### 8.1. allowedMethods không nhất thiết có OPTIONS

Preflight dùng method OPTIONS, nhưng `Access-Control-Request-Method: GET` hỏi phép cho **GET thực tế**. Vì vậy nếu endpoint chỉ cho GET, `allowedMethods(List.of("GET"))` đủ để xử lý preflight GET. Chỉ thêm OPTIONS nếu ứng dụng thực sự muốn hỗ trợ OPTIONS như một method được yêu cầu, không phải vì preflight dùng OPTIONS.

### 8.2. Allowed headers khác exposed headers

`allowedHeaders` kiểm soát header **request** mà browser được phép gửi, ví dụ Authorization và X-Trace-Id.

`exposedHeaders` cho phép JavaScript đọc thêm header **response** không nằm trong CORS-safelisted response headers, ví dụ X-Request-Id.

Đặt `exposedHeaders("Authorization")` không giúp browser gửi Authorization. Cần `allowedHeaders("Authorization")`.

### 8.3. allowCredentials=true và wildcard

Khi cho phép credentials, không đặt `allowedOrigins("*")`. Spring từ chối kết hợp wildcard origin với `allowCredentials(true)` vì response phải chỉ rõ origin hợp lệ.

Dùng allowlist chính xác:

~~~java
config.setAllowedOrigins(
    List.of("https://app.example.test")
);
config.setAllowCredentials(true);
~~~

Nếu thực sự cần dynamic origins, `allowedOriginPatterns` có thể phản chiếu origin được match, nhưng pattern phải đủ hẹp. Không dùng `https://*` hay pattern mở rộng vô hạn cho API có cookie/session/token.

### 8.4. Cẩn trọng với localhost trong development

Origin bao gồm port. Nếu frontend ở localhost:5173, đó là origin khác localhost:3000. Tạo profile riêng cho dev:

~~~java
config.setAllowedOrigins(
    List.of(
        "http://localhost:5173",
        "https://app.example.test"
    )
);
~~~

Không đem origin localhost không cần thiết vào policy production. Không nhầm tên host của server API với origin của frontend.

### 8.5. Vary và caching

Một response thay đổi theo Origin cần cache phân biệt các origin. Spring CORS processor thường thêm `Vary` cho Origin và các preflight request headers liên quan. Nếu dùng reverse proxy/CDN, phải bảo toàn các header Vary và không cache một response có Access-Control-Allow-Origin của origin A để trả nhầm cho origin B.

## 9. CORS, Basic Auth, bearer token và cookie

Preflight thường không mang credential; actual request có thể mang:

- Cookie session khi browser được cấu hình và cookie policy cho phép.
- Authorization: Basic hoặc Bearer.
- Một số cơ chế chứng thực khác theo browser/network.

Trong bài demo, actual GET có HTTP Basic authentication; preflight chỉ hỏi có được gửi header Authorization từ origin đã allowlist hay không.

### 9.1. Không phải bật credentials=true cho mọi API

Nếu frontend chỉ gửi request cross-origin không dùng cookie hoặc các loại credential cần CORS credentials mode, có thể không cần `allowCredentials(true)`. Cần chọn theo cách frontend thực sự gọi fetch/XHR.

Với `fetch(..., {credentials: "include"})`, response cần `Access-Control-Allow-Credentials: true` và origin rõ ràng, không phải `*`.

### 9.2. Preflight không phải nơi kiểm tra JWT

Không nên đòi JWT trên preflight. Browser gửi `Access-Control-Request-Headers: authorization` nhưng không gửi bearer token của actual request trong header Authorization ở preflight. Token được kiểm tra khi actual request đến Security filter chain.

### 9.3. Authentication thành công không bảo đảm CORS thành công

Một request GET có token hợp lệ nhưng từ origin không được allowlist vẫn bị browser chặn đọc response, hoặc bị server CorsWebFilter từ chối. Ngược lại, origin allowlist không làm GET thiếu token được phép vào controller.

## 10. CORS khác CSRF

**CORS** kiểm soát khả năng JavaScript cross-origin đọc response và một số tình huống browser gửi request có preflight. **CSRF** phòng tránh browser tự gửi credential như session cookie để thực hiện thao tác thay đổi trạng thái trái ý người dùng.

Chúng liên quan nhưng không thay thế nhau.

### 10.1. OPTIONS preflight và CSRF

Preflight là OPTIONS, thuộc nhóm HTTP methods thường được coi là an toàn. Mặc định Spring Security CSRF protection tập trung vào methods thay đổi trạng thái như POST/PUT/PATCH/DELETE, không chặn OPTIONS preflight vì thiếu CSRF token.

Nếu preflight bị 401/403, trước tiên kiểm tra cấu hình CORS, authentication/authorization, origin, requested method/headers và thứ tự filter. Không mặc định tắt CSRF để chữa lỗi CORS.

### 10.2. Actual POST vẫn cần bảo vệ phù hợp

Giả sử preflight POST được chấp nhận. Browser gửi actual POST bằng session cookie nhưng không có CSRF token, Spring Security vẫn có thể trả 403. Đó là một lớp bảo vệ khác và có thể là hành vi đúng.

Một API dùng bearer token trong Authorization header, không dựa trên credential tự động gửi, có thể đánh giá CSRF khác với ứng dụng dùng cookie-based session. Quyết định vô hiệu hóa CSRF phải dựa trên threat model và cơ chế authentication, không phải dựa vào việc frontend chạy ở origin khác.

### 10.3. Không vô hiệu hóa toàn bộ Security để thử CORS

Tránh các cách sửa nguy hiểm:

~~~java
// Không phải phương án đúng:
.authorizeExchange(a -> a.anyExchange().permitAll())
.csrf(csrf -> csrf.disable())
~~~

Chúng thay đổi security policy của toàn bộ ứng dụng mà không bảo đảm CORS đã được xử lý đúng.

## 11. Nhiều SecurityWebFilterChain và thứ tự @Order

Spring Security WebFlux có thể chọn một trong nhiều `SecurityWebFilterChain` theo `securityMatcher` và `@Order`.

Ví dụ các nhóm route:

~~~text
/api/**   -> API security chain
/admin/** -> Admin security chain
/**       -> fallback chain
~~~

Các chain có order thấp hơn được kiểm tra trước. Một request được chọn vào chain khớp đầu tiên; các chain khác không được ghép lại thành một tập filter chung.

### 11.1. Lỗi thường gặp với nhiều chain

Nếu cấu hình CORS chỉ trong chain /api/** nhưng preflight vào /admin/**, chain /admin/** có thể từ chối request trước khi chạy CORS processor mong muốn.

Nếu các securityMatcher phụ thuộc HTTP method, đừng quên preflight dùng **OPTIONS** còn actual request dùng GET/POST. Matcher chỉ chọn GET có thể không khớp OPTIONS, dẫn tới request đi vào fallback chain khác.

### 11.2. Hướng thiết kế

- Dùng CORS source nhất quán cho các path cần cross-origin.
- Nếu CORS cấu hình trong từng Security chain, bảo đảm preflight cũng khớp đúng chain.
- Có thể dùng một CorsWebFilter toàn cục chạy trước tất cả security chains nếu phù hợp kiến trúc.
- Tránh đăng ký nhiều bean CORS có policy xung đột.
- Test từng path thực tế có Origin, Access-Control-Request-Method và Access-Control-Request-Headers.

### 11.3. Thứ tự của rule trong authorizeExchange

Ngay cả trong một chain, thứ tự rule cũng quan trọng:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

Rule cụ thể đặt trước rule rộng. Tuy nhiên, các rule này giải quyết authorization, không thay thế CORS. Nếu CORS processor đã xử lý preflight trước authorization thì request OPTIONS hợp lệ không cần tới permitAll rule.

## 12. Ví dụ hoàn chỉnh Java 17, Spring Boot và WebTestClient

Ví dụ sử dụng Java 17 và **Spring Boot 3.5.16** (phiên bản có sẵn trên Maven Central). Đây là phiên bản cố định để dễ tái hiện ví dụ; khi triển khai production, dùng phiên bản đang được hỗ trợ và cập nhật bản vá bảo mật phù hợp.

Ứng dụng cung cấp một endpoint `GET /api/items` có authentication. Chỉ frontend `https://app.example.test` được phép gửi CORS GET với header Authorization/X-Trace-Id. Preflight hợp lệ phải được xử lý trước authentication, trong khi actual GET thiếu credential vẫn bị 401.

### 12.1. Cấu trúc dự án

~~~text
webflux-cors-security/
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/CorsSecurityApplication.java
    └── test/
        └── java/demo/CorsSecurityApplicationTest.java
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 12.3. CorsSecurityApplication.java

~~~java
package demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class CorsSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsSecurityApplication.class, args);
    }
}

record ItemView(String code, String label) {}

@RestController
@RequestMapping("/api")
class ItemController {

    @GetMapping("/items")
    Mono<List<ItemView>> getItems() {
        return Mono.just(List.of(
            new ItemView("ITEM-1", "visible after authentication")
        ));
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(
            List.of(
                "Authorization",
                "Content-Type",
                "X-Trace-Id"
            )
        );
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {

        return http
            .cors(cors ->
                cors.configurationSource(corsConfigurationSource)
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails reader = User.withUsername("reader")
            .password(passwordEncoder.encode("read-pass"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**Đặc điểm của ví dụ:**

1. CORS policy áp dụng `/api/**`.
2. Chỉ cho `https://app.example.test`.
3. `allowedMethods(GET)` vẫn cho phép preflight OPTIONS hỏi quyền GET.
4. `allowedHeaders` cho phép actual request gửi Authorization, Content-Type và X-Trace-Id.
5. `allowCredentials(true)` trả thông tin để browser dùng credentialed request từ origin được phép.
6. `http.cors(...)` đặt CORS processor vào vị trí đúng trong security chain.
7. `/api/**` vẫn yêu cầu authentication.
8. HTTP Basic ở đây là cơ chế demo; user/password được tạo bằng BCrypt.
9. Cấu hình không vô hiệu hóa CSRF; GET không yêu cầu CSRF token.
10. Không cần `OPTIONS /** permitAll`.

**Ghi chú production:** Không dùng user/password hard-coded; thay bằng identity provider, secret manager hoặc user store thích hợp. Không dùng HTTP Basic trên kết nối không mã hóa; triển khai API trên HTTPS/TLS. CORS chỉ là lớp kiểm soát browser, không thay thế authentication/authorization.

### 12.4. CorsSecurityApplicationTest.java

Test dùng server HTTP thật trên port ngẫu nhiên để đi qua CORS filter và security chain.

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorsSecurityApplicationTest {

    private static final String ALLOWED =
        "https://app.example.test";

    private static final String DENIED =
        "https://evil.example.test";

    @Autowired
    WebTestClient client;

    @Test
    void preflightIsAcceptedWithoutAuthentication() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,x-trace-id"
            )
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            )
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            );
    }

    @Test
    void actualGetWithoutAuthenticationRemainsProtected() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            );
    }

    @Test
    void authenticatedGetFromAllowedOriginSucceeds() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(headers ->
                headers.setBasicAuth("reader", "read-pass")
            )
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            )
            .expectBody()
            .jsonPath("$[0].code").isEqualTo("ITEM-1");
    }

    @Test
    void preflightFromOtherOriginIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, DENIED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithForbiddenMethodIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithForbiddenHeaderIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "x-admin-secret"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void actualGetFromDeniedOriginIsRejected() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, DENIED)
            .headers(headers ->
                headers.setBasicAuth("reader", "read-pass")
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void ordinaryOptionsIsNotCorsPreflight() {
        client.options()
            .uri("/api/items")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void sameOriginStyleRequestStillRequiresAuthentication() {
        client.get()
            .uri("/api/items")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

**Ý nghĩa từng nhóm kiểm thử:**

- Preflight hợp lệ **không cần Authorization/cookie** và nhận CORS headers.
- Actual GET từ origin hợp lệ nhưng thiếu authentication vẫn trả 401.
- Actual GET có HTTP Basic hợp lệ trả 200 và JSON.
- Origin khác allowlist trả 403 ngay cả khi request có Basic credentials.
- Preflight xin method POST bị từ chối vì policy chỉ cho GET.
- Preflight xin header X-Admin-Secret bị từ chối vì header không được allowlist.
- OPTIONS không có đủ header preflight vẫn phải qua security rules.
- GET không có Origin cũng không tự được phép truy cập vì Security còn hiệu lực.

Các test kiểm tra hành vi HTTP thực tế. Chúng không giả định browser gửi token ở preflight, và không khẳng định một header CORS có thể thay thế user authorization.

### 12.5. Chạy build và test

Nếu đã có Gradle wrapper trong dự án:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có wrapper nhưng đã cài Gradle 8.x tương thích, chạy:

~~~bash
gradle test
~~~

Chạy ứng dụng:

~~~bash
gradle bootRun
~~~

Các test sử dụng cổng ngẫu nhiên; không cần khởi động server riêng trước khi chạy test.

### 12.6. Test thủ công bằng curl

Khởi động ứng dụng trên localhost:8080. Gửi preflight:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
~~~

Kết quả dự kiến: response thành công cùng `Access-Control-Allow-Origin` cho origin được phép; request này **không cần** Authorization.

Gửi actual request có credential:

~~~bash
curl -i -u reader:read-pass \
  -H "Origin: https://app.example.test" \
  http://localhost:8080/api/items
~~~

Kết quả dự kiến: HTTP 200 và JSON gồm phần tử có `code=ITEM-1`. Đây là test trực tiếp API bằng curl; curl hiển thị response nhưng không cưỡng chế CORS như browser.

Gửi actual request không có credential:

~~~bash
curl -i \
  -H "Origin: https://app.example.test" \
  http://localhost:8080/api/items
~~~

Kết quả dự kiến: HTTP 401, dù origin hợp lệ. Đó là minh chứng CORS không thay thế Security.

## 13. JavaScript frontend và cấu hình credentials

Ví dụ frontend gọi API bằng Bearer token:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/items",
  {
    method: "GET",
    headers: {
      Authorization: "Bearer " + accessToken,
      "X-Trace-Id": traceId
    },
    credentials: "include"
  }
);

if (!response.ok) {
  throw new Error("HTTP status: " + response.status);
}

const items = await response.json();
~~~

Đây là đoạn minh họa phía frontend, không chạy trực tiếp với server demo chỉ bật HTTP Basic. Để dùng Bearer token, backend cần cấu hình OAuth2 Resource Server/JWT authentication hoặc cơ chế token tương ứng. CORS policy chỉ cho browser gửi những header này và đọc response, không tự nhận diện token.

### 13.1. credentials mode

`credentials: "include"` yêu cầu browser gửi các credential phù hợp theo cookie policy/authentication mechanism và đòi response có `Access-Control-Allow-Credentials: true` từ origin cụ thể. Nếu API không cần cookie hay credentialed mode, cấu hình `allowCredentials(false)` có thể phù hợp hơn.

### 13.2. Không để token trong URL

Không truyền bearer token trong query string chỉ để tránh header Authorization hoặc preflight. Query string có thể bị log ở proxy, analytics, browser history. Preflight là hành vi bình thường, nên cấu hình server đúng thay vì lách nó.

## 14. Gỡ lỗi preflight 401/403 theo thứ tự

Khi frontend báo lỗi CORS, đừng sửa ngẫu nhiên. Dùng quy trình sau:

### 14.1. Kiểm tra request thực tế trong DevTools

Xem Network tab và phân biệt:

- OPTIONS preflight có status gì?
- Có Origin và Access-Control-Request-Method không?
- Browser xin những request headers nào?
- Có response `Access-Control-Allow-Origin` không?
- Actual GET/POST có được gửi sau preflight không?
- Actual request trả 401/403/500 hay browser chỉ báo không đọc được response?

Đừng chỉ dựa vào dòng “CORS error” trên console; trình duyệt đôi khi ẩn response khỏi JavaScript nếu CORS thất bại.

### 14.2. Preflight trả 401

Nguyên nhân thường gặp: security đã yêu cầu authentication trước CORS.

Kiểm tra:
1. Có `http.cors(...)` hoặc CorsWebFilter chạy đủ sớm không?
2. Reactive CorsConfigurationSource có đúng package không?
3. Path có nằm trong registered CORS mapping không?
4. Nhiều security chain có làm preflight rơi vào chain khác không?
5. Có custom WebFilter tự kiểm tra token trên mọi request, kể cả OPTIONS, trước CORS không?

### 14.3. Preflight trả 403

Có thể do CORS policy cố tình từ chối, không nhất thiết là lỗi authentication.

Kiểm tra:
- Origin có đúng scheme/host/port?
- Access-Control-Request-Method có nằm trong allowedMethods?
- Access-Control-Request-Headers có header chưa được allowedHeaders?
- Có cấu hình allowedCredentials=true với allowedOrigins="*" không?
- Có CORS processor thứ hai với policy xung đột không?

### 14.4. Preflight 200 nhưng actual request 401

CORS có thể đã đúng. Kiểm tra token/cookie, Authorization format, expired credential, authentication provider, proxy có chuyển tiếp Authorization không. Không sửa bằng cách nới allowedOrigins.

### 14.5. Preflight 200 nhưng actual request 403

Có thể do authorization (thiếu role/scope), CSRF với request thay đổi trạng thái, hoặc actual CORS policy khác preflight. Phân biệt bằng log server/security, status, response headers và loại request.

### 14.6. Preflight không xảy ra

Không phải request nào cũng cần preflight. Một GET đơn giản có thể chỉ có actual request. Nếu actual response thiếu CORS headers, browser vẫn có thể chặn đọc body. Đừng dựa trên việc “không thấy OPTIONS” để kết luận CORS không liên quan.

### 14.7. Proxy hoặc gateway chặn OPTIONS

Cấu hình chính xác ở Spring vẫn vô ích nếu gateway trả 401/403 trước khi request tới ứng dụng.

Kiểm tra:
- API gateway/WAF rule.
- Nginx/Ingress method allowlist.
- CORS config ở CDN và backend có bị áp dụng hai lần?
- Reverse proxy có giữ Origin và Access-Control-Request-*?
- OPTIONS có tới Spring service không?

Nếu gateway xử lý CORS thay backend, policy tại gateway phải thống nhất và không làm mất bảo vệ request thực tế.

## 15. Quan sát filter order và log an toàn

### 15.1. Log phân biệt preflight với actual request

Ở môi trường phát triển có thể log method, path và sự hiện diện của các header (không log token):

~~~text
OPTIONS /api/items
Origin=https://app.example.test
Access-Control-Request-Method=GET
Access-Control-Request-Headers=authorization
authorization-present=false

GET /api/items
Origin=https://app.example.test
authorization-present=true
~~~

Không log giá trị Authorization hoặc cookie. Một custom filter chạy **sau** CORS processor có thể không thấy preflight đã được CORS xử lý và kết thúc. Nếu cần metrics preflight, đặt điểm quan sát phù hợp trước CORS hoặc dùng logging ở gateway/network layer.

### 15.2. Thứ tự custom WebFilter

Với WebFilter bean tự tạo, `@Order` quyết định thứ tự trong outer WebFilter chain. Đối với security-internal filter, dùng API của `ServerHttpSecurity` và `SecurityWebFiltersOrder`.

Không thêm một filter tự yêu cầu Authorization trên mọi request ở `Ordered.HIGHEST_PRECEDENCE` rồi kỳ vọng `http.cors(...)` (bên trong Security) vẫn xử lý preflight trước filter đó. Nếu có filter như vậy, hoặc chuyển authentication vào Security chain, hoặc để CORS chạy trước custom filter.

### 15.3. Metrics nên theo dõi

- Số preflight và tỷ lệ 2xx/4xx.
- Thời gian xử lý preflight.
- Số CORS rejection theo nhóm lý do (origin/method/header) nhưng tránh tag có cardinality cao.
- Số actual 401/403 theo route và auth mechanism.
- Tần suất lỗi browser CORS sau khi deploy.
- Dữ liệu proxy/gateway có chặn OPTIONS không.

Không dùng Origin tùy ý do user gửi làm metric tag không giới hạn vì cardinality có thể tăng rất nhanh.

## 16. Các lỗi cấu hình thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Để authentication chặn trước CORS | Preflight không credential bị 401 | Tích hợp CORS trước authentication |
| Chỉ thêm OPTIONS permitAll | Không có CORS response headers | Tạo CorsConfigurationSource và processor |
| Chỉ thêm @CrossOrigin với security chặn sớm | HandlerMapping không được gọi | Cấu hình CORS trong/ngoài Security |
| Dùng CorsFilter của Servlet cho WebFlux | Sai type/lifecycle | Dùng CorsWebFilter/reactive CorsConfigurationSource |
| allowedMethods có OPTIONS nhưng không có GET | Preflight hỏi GET vẫn bị từ chối | Khai báo actual methods GET/POST |
| allowedHeaders quên Authorization | Preflight Bearer request bị 403 | Allowlist Authorization |
| exposedHeaders dùng thay allowedHeaders | Browser không được gửi header | Phân biệt request/response headers |
| allowedOrigins "*" với allowCredentials true | Cấu hình không hợp lệ và thiếu an toàn | Exact origin allowlist |
| Dùng allowedOriginPatterns quá rộng | Browser origin ngoài ý định được phép | Giới hạn pattern và test |
| Lặp CorsWebFilter và http.cors với policy khác | Header/behavior khó đoán | Một nguồn CORS chính rõ ràng |
| Nhiều SecurityWebFilterChain nhưng CORS chỉ ở một chain | OPTIONS đi sai chain và thất bại | Kiểm tra matcher/order/preflight |
| Custom WebFilter auth chạy trước CORS | Preflight vẫn bị chặn | Đổi order hoặc tích hợp vào Security |
| Tắt CSRF để sửa preflight | Mất bảo vệ thao tác state-changing | Chẩn đoán CORS và CSRF riêng |
| Tắt mọi authorization để sửa 401 | Endpoint không còn bảo vệ | Giữ actual request authenticated |
| Không phân biệt origin scheme/port | localhost dev hoặc HTTPS bị chặn | Khai báo origin chính xác |
| Gateway chặn OPTIONS | Spring không nhận preflight | Sửa gateway/proxy method policy |
| Browser báo CORS khi actual trả 500 | Chẩn đoán sai | Xem Network và server logs |
| Test chỉ controller bằng unit test | Không kiểm chứng filter/security order | Dùng integration WebTestClient |
| Giả định curl kiểm tra CORS browser | Không phát hiện lỗi enforcement | Kết hợp curl header test và browser test |

## 17. Checklist trước production

1. Frontend origins được allowlist chính xác theo scheme/host/port?
2. Các actual methods có trong allowedMethods?
3. Những request headers thực sự dùng (Authorization/Content-Type/custom headers) có trong allowedHeaders?
4. allowCredentials có đúng mô hình cookie/token hay bị bật không cần thiết?
5. Không có wildcard origin với credentials?
6. Preflight được xử lý trước authentication/authorization?
7. Có một CORS policy chính nhất quán, không nhiều processor mâu thuẫn?
8. Các SecurityWebFilterChain đều xử lý đúng preflight theo securityMatcher và @Order?
9. Custom WebFilter có tự chặn OPTIONS trước CORS không?
10. @CrossOrigin/addCorsMappings nếu có có mâu thuẫn với policy trong Security không?
11. OPTIONS preflight không bị gateway/CDN/WAF chặn?
12. Actual request thiếu authentication vẫn trả 401?
13. Actual request thiếu authorization vẫn trả 403?
14. CSRF bảo vệ đúng cho phương thức thay đổi trạng thái khi dùng session/cookie?
15. Có test Origin hợp lệ, Origin bị cấm, method/header không được phép?
16. Có test preflight không credential, actual request có credential, và actual request không credential?
17. Logging không lộ Authorization/cookie/token?
18. Có theo dõi preflight failure và actual 401/403 sau deployment?

**Tổng kết:** Preflight là một HTTP OPTIONS có Origin và Access-Control-Request-Method, thường không mang cookie/Authorization. Trong Spring WebFlux, phải để CORS processor xử lý nó trước authentication/authorization; dùng `ServerHttpSecurity.cors(configurationSource)` hoặc một `CorsWebFilter` độc lập có thứ tự sớm. `@CrossOrigin` và `WebFluxConfigurer.addCorsMappings` hoạt động ở HandlerMapping, có thể quá muộn khi security chặn trước. CORS không xác thực user, cũng không thay CSRF: actual request vẫn phải đi qua kiểm tra quyền, còn POST/PUT/PATCH/DELETE có thể vẫn cần CSRF token theo mô hình credential. Hãy test toàn bộ filter chain bằng WebTestClient trên HTTP thực để tránh sửa sai tầng.

## Tài liệu tham khảo

- Spring Security 6.5 — Reactive CORS Integration: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Security — WebFlux Security and WebFilter Architecture: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — WebFilter in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — ServerHttpSecurity.CorsSpec API: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Boot 3.5 — Test WebFlux with WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security — CSRF in Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Boot 3.5.16 release (baseline example): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
