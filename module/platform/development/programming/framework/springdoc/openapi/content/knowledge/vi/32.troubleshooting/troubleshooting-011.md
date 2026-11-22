# Lỗi 401, 403, CSRF hoặc CORS khi gọi thử

Khi mở Swagger UI thành công nhưng thao tác **Try it out** trả 401, 403 hoặc báo CORS, cần xác định request nào bị từ chối và lớp nào xử lý request đó. Swagger UI chỉ là giao diện chạy trong trình duyệt; request tới OpenAPI document, request tới API thật và request preflight của trình duyệt có thể đi qua các endpoint, filter và security rule khác nhau.

Trong Spring Boot có springdoc-openapi, bốn nhóm lỗi thường gặp là:

- **401 Unauthorized:** request thiếu thông tin xác thực hoặc credential không hợp lệ.
- **403 Forbidden:** người dùng đã được xác thực nhưng không đủ quyền; hoặc Spring Security từ chối request vì CSRF token thiếu/sai.
- **CSRF:** request thay đổi trạng thái không gửi token hợp lệ trong ứng dụng dùng cơ chế xác thực dựa trên cookie/session.
- **CORS:** trình duyệt chặn request cross-origin vì server không cho phép origin, method hoặc header được yêu cầu.

Không xử lý cả bốn bằng cách tắt Spring Security. Hãy dùng Network tab để tìm request bị lỗi, xem status và response headers, rồi sửa đúng filter chain, authorization rule, CSRF repository hoặc CORS configuration.

## 1. Xác định request nào đang lỗi

Swagger UI thường tạo ra nhiều request khác nhau:

| Request | Mục đích | Lỗi thường gặp |
|---|---|---|
| /swagger-ui.html | URL vào Swagger UI, thường redirect sang giao diện | 302 loop, 401, 403 hoặc 404 |
| /swagger-ui/** | JavaScript, CSS và tài nguyên giao diện | 401, 403 hoặc 404 |
| /v3/api-docs/swagger-config | Tải cấu hình Swagger UI | 401, 403 hoặc 404 |
| /v3/api-docs | Tải OpenAPI document mặc định | 401, 403 hoặc 404 |
| /v3/api-docs/{group} | Tải document của một group | 401, 403 hoặc 404 |
| /api/** | API nghiệp vụ được gọi bằng Try it out | 400, 401, 403, 404, 415 hoặc lỗi khác |
| OPTIONS /api/** | CORS preflight do trình duyệt gửi trước request thật | 401, 403 hoặc thiếu CORS headers |

Mở Developer Tools của trình duyệt, chọn tab **Network**, bật Preserve log, sau đó thực hiện lại thao tác lỗi. Lọc theo Fetch/XHR và xem:

1. Request URL và HTTP method.
2. Status code của request.
3. Request headers, nhất là Origin, Authorization, Cookie, Content-Type, Accept và Access-Control-Request-*.
4. Response headers, nhất là WWW-Authenticate, Access-Control-Allow-Origin, Access-Control-Allow-Credentials và Access-Control-Allow-Headers.
5. Response body nếu trình duyệt cho phép đọc.
6. Có request OPTIONS trước request thật hay không.

Ví dụ: giao diện /swagger-ui/index.html trả 200 nhưng /v3/api-docs trả 401 thì lỗi nằm ở quyền truy cập OpenAPI document. Nếu document tải được, nhưng POST /api/products trả 403, hãy kiểm tra authorization hoặc CSRF của endpoint nghiệp vụ.

Thông báo “Failed to fetch” hoặc “NetworkError” không đủ để kết luận server không chạy. CORS có thể khiến JavaScript không đọc được response, dù server đã trả 401 hoặc 403. Hãy kiểm tra request và response headers trong Network tab.

## 2. Phân biệt 401 và 403

401 và 403 thể hiện hai trạng thái khác nhau:

| Status | Ý nghĩa thường gặp | Câu hỏi chẩn đoán |
|---|---|---|
| 401 Unauthorized | Chưa xác thực hoặc credential không hợp lệ | Request có gửi token/cookie không? Token còn hạn, đúng issuer/audience và chữ ký không? |
| 403 Forbidden | Đã xác thực nhưng không được phép; hoặc request bị chặn bởi CSRF | User có role/scope phù hợp không? Request có CSRF token không? |

Với HTTP Bearer authentication, response 401 thường đi kèm WWW-Authenticate: Bearer. Token có thể thiếu, hết hạn, sai chữ ký, sai issuer/audience hoặc không được chấp nhận bởi resource server.

403 thường xuất hiện khi principal đã được xác định nhưng thiếu authority hoặc scope. Tuy nhiên, CSRF filter cũng thường trả 403 khi request dùng method thay đổi trạng thái mà không có CSRF token hợp lệ. Vì vậy, không kết luận mọi 403 đều là lỗi role.

## 3. Xác minh Swagger UI và OpenAPI endpoints có được phép truy cập

Một cấu hình Spring Security có thể yêu cầu xác thực cho toàn bộ ứng dụng. Nếu muốn người dùng mở tài liệu công khai, cần cho phép các endpoint Swagger UI và springdoc trước rule yêu cầu authentication.

Ví dụ với Spring Boot 3 / Spring Security 6 trở lên:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs",
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml"
                ).permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
            )
            // Chỉ bỏ qua CSRF cho API nếu API này stateless và chỉ dùng bearer token.
            .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ));

        return http.build();
    }
}
~~~

Trong ví dụ:

- permitAll() chỉ áp dụng cho đường dẫn tài liệu và giao diện Swagger UI.
- /api/admin/** vẫn yêu cầu role ADMIN.
- /api/** vẫn yêu cầu authentication.
- JWT resource server vẫn xác thực request nghiệp vụ.

Không thêm /api/** vào permitAll() chỉ để Swagger UI gọi được API. Giao diện có thể tải công khai trong khi API vẫn được bảo vệ.

Các path trên là path mặc định thường gặp. Nếu đổi springdoc.api-docs.path, springdoc.swagger-ui.path, dùng context path hoặc reverse proxy prefix, hãy cập nhật matcher theo URL thực tế. Một số phiên bản cũ có thể phục vụ tài nguyên qua /webjars/**; chỉ thêm matcher này nếu Network tab cho thấy ứng dụng thực sự dùng đường dẫn đó.

Nếu OpenAPI document chứa endpoint nội bộ hoặc thông tin không dành cho mọi người, không mở công khai chỉ để sửa 401. Có thể bảo vệ document, tách group public/private hoặc phát hành một document đã lọc riêng.

## 4. Thứ tự rule và nhiều SecurityFilterChain

requestMatchers được đánh giá theo thứ tự khai báo trong một SecurityFilterChain. Rule rộng như /api/** hoặc anyRequest().authenticated() đặt trước rule cụ thể có thể làm rule sau không được áp dụng như mong đợi.

Nếu ứng dụng có nhiều SecurityFilterChain, Spring Security chọn chain theo securityMatcher và thứ tự @Order. Cho phép Swagger UI trong một chain không có tác dụng nếu request thực tế được một chain khác bắt trước.

Ví dụ có một chain riêng cho API:

Ví dụ dùng AbstractHttpConfigurer trong cấu hình hiện đại; import tương ứng là org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        // Chỉ dùng khi toàn bộ chain API stateless và xác thực bằng bearer token.
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            Customizer.withDefaults()
        ));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webAndDocsSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs/**",
                "/v3/api-docs.yaml"
            ).permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Ví dụ minh họa việc phân chia chain; cấu hình thực tế phải bao gồm các rule và authentication mechanism của ứng dụng. Chain đầu chỉ khớp /api/**, do đó không xử lý /v3/api-docs hay /swagger-ui/**. Chain thứ hai xử lý phần còn lại. Dòng tắt CSRF trong chain đầu chỉ phù hợp khi mọi request API dùng bearer token stateless; nếu API dùng cookie/session, giữ CSRF và yêu cầu token.

Khi chẩn đoán 401/403, kiểm tra cả securityMatcher, @Order, rule cụ thể và rule tổng quát. Bật log Spring Security ở mức DEBUG trong môi trường phát triển để xem chain/filter nào xử lý request; không để log debug nhạy cảm ở production.

## 5. Swagger UI Authorize không tự cấu hình Spring Security

Nút **Authorize** trong Swagger UI lấy security scheme từ OpenAPI document và gắn credential vào các request mà Swagger UI gửi theo scheme đó. Nó không tạo user, không cấp role và không thay thế cấu hình Spring Security.

Ví dụ khai báo HTTP Bearer JWT trong OpenAPI:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product API",
        version = "v1"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {}
~~~

Gắn requirement vào operation hoặc controller:

~~~java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "bearerAuth")
class ProductController {

    @GetMapping
    List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

Khi người dùng nhập JWT vào Authorize, Swagger UI có thể gửi:

~~~http
Authorization: Bearer eyJ...
~~~

Kiểm tra trong Network tab xem header Authorization có thực sự xuất hiện trên request API hay không. Nếu không có, kiểm tra security scheme, requirement, cách nhập token và cấu hình Swagger UI.

@SecurityScheme và @SecurityRequirement chỉ mô tả bảo mật trong OpenAPI. Chúng không cấu hình oauth2ResourceServer, JWT decoder, role mapping hoặc authorization rule của Spring Security. Hai phần phải được cấu hình nhất quán.

### Lưu ý khi OpenAPI document cũng được bảo vệ

Swagger UI phải tải document trước khi hiển thị đầy đủ operation. Nút Authorize thường chỉ có thể được dùng sau khi UI đã tải cấu hình/document và người dùng nhìn thấy giao diện.

Nếu /v3/api-docs yêu cầu bearer token nhưng token chỉ được nhập qua Authorize sau khi document tải xong, có thể xảy ra vòng lặp: UI không tải được document nên không hiển thị nút Authorize để nhập token.

Các cách xử lý:

- Cho phép truy cập document public nếu nội dung được phép công khai.
- Cung cấp document tĩnh hoặc document public đã lọc.
- Dùng cơ chế cookie/session đã xác thực trước khi mở Swagger UI.
- Nếu có yêu cầu đặc biệt, cấu hình request interceptor để gửi credential khi tải document; bảo đảm không làm lộ token.

Không nhầm việc Authorize gửi token tới operation với việc Swagger UI tải /v3/api-docs/swagger-config và /v3/api-docs.

## 6. Chẩn đoán token Bearer và OAuth2

Khi API trả 401, kiểm tra:

1. Request có Authorization: Bearer ... không?
2. Token có bị cắt, có dấu ngoặc kép hoặc tiền tố Bearer lặp lại không?
3. Token còn hạn (exp) không?
4. iss và aud có khớp cấu hình resource server không?
5. JWT ký bằng key mà server tin cậy không?
6. Token có đúng loại token dành cho API này không?
7. Clock của máy cấp token và máy chạy API có lệch đáng kể không?
8. Reverse proxy có xóa hoặc không chuyển tiếp header Authorization không?

Với OAuth2, phân biệt access token với ID token. ID token dành cho client nhận diện người dùng; API resource server thường cần access token có audience và scope phù hợp.

Khi API trả 403, kiểm tra mapping authority:

- Scope products.read thường được ánh xạ thành authority SCOPE_products.read trong cấu hình resource server mặc định.
- Role ADMIN thường được kiểm tra bằng hasRole("ADMIN"), tương ứng authority ROLE_ADMIN.
- hasAuthority("SCOPE_products.read") và hasRole("products.read") không tương đương.

Ví dụ:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/products/**")
        .hasAuthority("SCOPE_products.read")
    .requestMatchers(HttpMethod.POST, "/api/products/**")
        .hasAuthority("SCOPE_products.write")
    .anyRequest().authenticated()
);
~~~

Không đưa JWT thật vào source code, ảnh chụp màn hình, ticket hoặc log. Khi cần debug, dùng token test có thời hạn ngắn và quyền tối thiểu; chỉ chia sẻ các claim không nhạy cảm đã được làm sạch.

## 7. Phân biệt CSRF với authentication

CSRF (Cross-Site Request Forgery) là kiểu tấn công lợi dụng việc trình duyệt tự động gửi credential của người dùng, thường là cookie session. Kẻ tấn công có thể khiến trình duyệt đã đăng nhập gửi request thay đổi trạng thái tới một website khác.

Spring Security bật bảo vệ CSRF mặc định cho các request có khả năng thay đổi trạng thái như POST, PUT, PATCH và DELETE. Request GET, HEAD, OPTIONS và TRACE được xem là safe methods theo mặc định matcher.

Khi CSRF được bật, request cần gửi CSRF token hợp lệ ngoài cookie xác thực. Cookie session chứng minh phiên đăng nhập; CSRF token chứng minh request thay đổi trạng thái có nguồn gốc từ ứng dụng đã cấp token.

Các triệu chứng thường gặp:

- GET API thành công nhưng POST/PUT/DELETE trả 403.
- Request từ Swagger UI trả 403 dù JWT có vẻ hợp lệ.
- Server log báo thiếu hoặc không khớp CSRF token.
- Cookie session có mặt nhưng header CSRF không có.

Không tắt CSRF chỉ vì thấy 403. Trước tiên xác định ứng dụng dùng session cookie, cookie authentication hay bearer token được gửi tường minh trong Authorization header.

## 8. Khi nào có thể bỏ qua CSRF cho API?

Nếu API thực sự stateless và chỉ xác thực bằng bearer token trong Authorization header, trình duyệt không tự động đính kèm header này như cookie session. Trong kiến trúc đó, CSRF protection cho riêng API có thể không cần thiết.

Có thể bỏ qua CSRF cho path API bằng matcher cụ thể:

~~~java
http
    .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        Customizer.withDefaults()
    ));
~~~

Chỉ dùng cách này khi /api/** không dựa vào cookie/session hoặc credential tự động gửi từ trình duyệt. Nếu API dùng cookie authentication, Basic authentication được trình duyệt tự động gửi, hoặc session dùng chung với giao diện web, bỏ qua CSRF có thể mở ra lỗ hổng.

Một lựa chọn an toàn hơn khi ứng dụng có cả web session và API stateless là tách thành các SecurityFilterChain riêng: chain API stateless có CSRF policy riêng; chain web vẫn giữ CSRF protection.

Không tắt CSRF toàn cục để Swagger UI gọi được một operation nếu ứng dụng còn form login hoặc endpoint thay đổi trạng thái dựa trên session cookie.

## 9. Cấu hình CSRF token cho Swagger UI

Nếu ứng dụng dùng session/cookie authentication và vẫn cần CSRF, Swagger UI phải gửi token trong header hoặc request parameter mà server mong đợi.

Springdoc có property hỗ trợ CSRF của Swagger UI khi dùng tên header/cookie tiêu chuẩn:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
~~~

Property này mặc định là false và có từ springdoc-openapi v1.4.4. Theo cấu hình Spring Security thường gặp với CookieCsrfTokenRepository, cookie có tên XSRF-TOKEN và header có tên X-XSRF-TOKEN. Springdoc Swagger UI có thể tự đọc và gửi token theo quy ước tiêu chuẩn khi tính năng CSRF được bật và phiên bản đang dùng hỗ trợ property này.

Nếu ứng dụng dùng tên cookie/header tùy chỉnh hoặc cách lưu token khác, cần cấu hình requestInterceptor của Swagger UI để lấy token và gắn đúng header. Kiểm tra tài liệu phiên bản springdoc đang cài; không giả định property mới tồn tại trong mọi phiên bản cũ.

Ví dụ CookieCsrfTokenRepository cho ứng dụng cần JavaScript đọc CSRF cookie:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

HttpOnly=false cho phép JavaScript đọc cookie CSRF. Chỉ áp dụng cho cookie chứa CSRF token, không áp dụng cho session cookie hoặc cookie chứa access token. Dùng HTTPS, cấu hình SameSite phù hợp và đánh giá yêu cầu bảo mật của ứng dụng trước khi bật.

Spring Security hiện đại có deferred token và BREACH protection; SPA có một số khác biệt khi lấy token từ cookie. Nếu dùng custom SPA flow hoặc nâng cấp Spring Security, làm theo hướng dẫn CSRF tương ứng với đúng phiên bản thay vì sao chép cấu hình cũ.

## 10. CORS là gì và khi nào Swagger UI cần CORS?

CORS (Cross-Origin Resource Sharing) là cơ chế trình duyệt dùng để kiểm soát JavaScript có được đọc response từ origin khác hay không.

Origin gồm scheme, host và port. Ví dụ:

| Swagger UI | API | Có cross-origin? |
|---|---|---|
| http://localhost:8080 | http://localhost:8080 | Không |
| http://localhost:8080 | http://localhost:9090 | Có, khác port |
| https://docs.example.com | https://api.example.com | Có, khác host |
| https://docs.example.com | http://api.example.com | Có, khác scheme |

Nếu Swagger UI và API cùng origin, trình duyệt không cần CORS cho request đó. Nếu Swagger UI gọi API ở origin khác, server API phải trả các CORS headers phù hợp.

CORS cũng có thể cần thiết khi Swagger UI tải OpenAPI document từ một URL ngoài domain hiện tại, ví dụ springdoc.swagger-ui.url trỏ tới service khác. Khi đó, origin cần được cho phép ở server cung cấp document.

CORS không phải authentication và không cấp quyền truy cập API. Nó chỉ điều khiển hành vi trình duyệt đối với cross-origin request. curl, Postman hoặc service-to-service client không áp dụng chính sách CORS của trình duyệt.

## 11. Vì sao CORS preflight bị 401 hoặc 403?

Với request cross-origin có method hoặc header không đơn giản, trình duyệt gửi request preflight bằng OPTIONS trước:

~~~http
OPTIONS /api/products HTTP/1.1
Origin: https://docs.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server phải xác nhận origin, method và headers được phép. Nếu preflight thành công, trình duyệt mới gửi POST thật.

Preflight thường không mang cookie session. Nếu Spring Security xác thực request OPTIONS trước khi CORS được xử lý, filter chain có thể trả 401/403 vì request chưa có cookie. Do đó, CORS phải được xử lý trước Spring Security authorization.

Bật CORS integration trong Spring Security:

~~~java
http.cors(Customizer.withDefaults());
~~~

Spring Security có thể dùng CorsConfigurationSource phù hợp. Khi có nhiều CorsConfigurationSource hoặc nhiều SecurityFilterChain, chỉ rõ source cho từng chain nếu Spring Security không thể tự chọn.

Không chỉ thêm requestMatchers(HttpMethod.OPTIONS, "/**").permitAll() rồi bỏ qua CORS configuration. Cho phép OPTIONS không tự tạo Access-Control-Allow-Origin, Access-Control-Allow-Methods hoặc Access-Control-Allow-Headers; trình duyệt vẫn có thể chặn request.

## 12. Cấu hình CorsConfigurationSource

Ví dụ cho Swagger UI tại https://docs.example.com gọi API:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
        List.of("https://docs.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of(
            "Authorization",
            "Content-Type",
            "Accept",
            "X-XSRF-TOKEN",
            "X-Requested-With"
        )
    );
    configuration.setExposedHeaders(
        List.of("Location", "WWW-Authenticate")
    );
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

Và bật trong filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Giải thích:

- allowedOrigins liệt kê origin được phép, gồm scheme và port nếu có.
- allowedMethods liệt kê method mà browser có thể gọi.
- allowedHeaders phải bao gồm header mà preflight yêu cầu, chẳng hạn Authorization, Content-Type và header CSRF.
- exposedHeaders liệt kê response header mà JavaScript cần đọc; ví dụ Location.
- allowCredentials(true) cho phép request có credentials theo CORS protocol.
- maxAge cho phép browser cache kết quả preflight trong khoảng thời gian nhất định.
- Đăng ký đúng path API, tránh áp dụng policy rộng hơn nhu cầu.

Nếu dùng allowCredentials(true), không dùng allowedOrigins("*"). Cần khai báo origin cụ thể hoặc origin patterns được kiểm soát. Nếu API không dùng cookie/credential mode của browser, cân nhắc allowCredentials(false) và chỉ cho phép các header cần thiết.

Đối với nhiều origin, liệt kê từng origin tin cậy. Không phản chiếu tùy ý giá trị Origin từ request thành Access-Control-Allow-Origin.

## 13. CORS với cookie và CSRF

Nếu Swagger UI ở origin khác và API dùng session cookie, cần phối hợp CORS, cookie và CSRF:

1. CORS cho phép chính xác origin của Swagger UI.
2. Server cho phép credentials.
3. Browser gửi cookie khi request dùng credential mode phù hợp.
4. Cookie có SameSite/Secure phù hợp với topology thực tế.
5. Swagger UI lấy được CSRF token theo cơ chế của ứng dụng.
6. Preflight cho phép header CSRF, ví dụ X-XSRF-TOKEN.
7. Request POST/PUT/PATCH/DELETE gửi CSRF token đúng.

Access-Control-Allow-Credentials: true không tự khiến browser gửi cookie. Client cũng phải gửi request với credentials phù hợp, và cookie phải đáp ứng SameSite/Secure. Với Swagger UI, kiểm tra phiên bản và cấu hình request interceptor nếu cần điều khiển credential mode.

Cookie cross-site thường cần thuộc tính SameSite=None; Secure, nhưng chỉ cấu hình như vậy khi kiến trúc thực sự cần cross-site cookie và toàn bộ luồng dùng HTTPS. Không hạ SameSite của mọi cookie chỉ để khắc phục một lỗi Try it out.

CORS preflight không thay thế CSRF token. Một origin được phép gọi API vẫn phải cung cấp CSRF token nếu endpoint dùng cookie/session và CSRF protection đang bật.

## 14. Kiểm tra OpenAPI security scheme và server URL

Swagger UI gọi URL dựa trên OpenAPI document. Nếu servers trỏ sai host, port, scheme hoặc context path, Try it out có thể gọi nhầm origin và gặp CORS hoặc 404.

Ví dụ khai báo server:

~~~java
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com",
            description = "Production API"
        )
    }
)
class OpenApiServerConfiguration {}
~~~

Trong môi trường local, có thể dùng profile hoặc cấu hình document phù hợp để không gọi nhầm production. Không commit server URL staging hoặc localhost như URL duy nhất cho mọi môi trường.

Kiểm tra phần servers trong /v3/api-docs, sau đó nhìn Request URL mà Swagger UI thực sự gửi. Nếu ứng dụng chạy sau reverse proxy hoặc có context path, cấu hình forwarded headers và public URL đúng với môi trường triển khai.

Security scheme trong OpenAPI cũng cần đúng loại:

- HTTP bearer cho Authorization: Bearer ...
- HTTP basic cho Basic authentication.
- OAuth2 cho authorization/token flows và scopes.
- apiKey cho API key đặt ở header, query hoặc cookie.

Khai báo sai scheme có thể khiến Swagger UI gửi credential sai định dạng dù Spring Security được cấu hình đúng.

## 15. Kiểm thử CORS preflight bằng curl

Có thể kiểm tra response preflight mà không cần mở Swagger UI:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/products" \
  -H "Origin: https://docs.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Với origin và request được phép, response thường cần có:

~~~http
Access-Control-Allow-Origin: https://docs.example.com
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Vary: Origin
~~~

Nếu dùng credentials, response cần Access-Control-Allow-Credentials: true và Access-Control-Allow-Origin phải là origin cụ thể, không phải *.

curl không thực thi CORS policy của browser; nó chỉ giúp xem server trả headers gì. Request thành công bằng curl không chứng minh browser sẽ chấp nhận response. Cuối cùng vẫn cần kiểm tra bằng trình duyệt ở đúng origin.

## 16. Kiểm thử CORS bằng MockMvc

MockMvc có thể gửi preflight request và kiểm tra CORS headers:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductCorsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsSwaggerUiOriginToSendAuthorizedPostRequest() throws Exception {
        mockMvc.perform(options("/api/products")
                .header(HttpHeaders.ORIGIN, "https://docs.example.com")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://docs.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            ));
    }
}
~~~

Test giả định CORS policy cho phép credentials. Nếu ứng dụng dùng bearer header và không dùng cookie, có thể đặt allowCredentials false và điều chỉnh assertion.

Thêm test cho origin không được phép:

~~~java
@Test
void doesNotAllowUntrustedOrigin() throws Exception {
    mockMvc.perform(options("/api/products")
            .header(HttpHeaders.ORIGIN, "https://untrusted.example")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            ))
        .andExpect(header().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
        ));
}
~~~

Không chỉ test origin được phép. Một CORS configuration quá rộng có thể làm test happy path pass nhưng mở API cho origin không mong muốn.

## 17. Kiểm thử CSRF token

Với MockMvc và spring-security-test, có thể xác minh endpoint yêu cầu CSRF:

~~~java
@Test
void rejectsStateChangingRequestWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice").roles("USER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "displayName": "Alice" }
                """))
        .andExpect(status().isForbidden());
}

@Test
void acceptsStateChangingRequestWithCsrfToken() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "displayName": "Alice" }
                """))
        .andExpect(status().isOk());
}
~~~

Thêm dependency test nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hai test trên giả định /web/profile dùng session authentication và CSRF protection. Nếu API stateless đã được cấu hình bỏ qua CSRF, không áp dụng assertion này cho /api/**; hãy test đúng policy của từng chain.

Để kiểm tra flow cookie thực tế của Swagger UI, cần integration/browser test: tải trang, nhận cookie CSRF, gửi request thay đổi trạng thái và xác minh header token được đính kèm. MockMvc .with(csrf()) chỉ kiểm tra filter xử lý token, không chứng minh JavaScript trong Swagger UI đã đọc cookie và gửi header đúng.

## 18. Kiểm thử security của tài liệu và giao diện

Nếu Swagger UI được mở công khai, kiểm tra các endpoint sau trả 200 hoặc redirect hợp lệ:

- /swagger-ui.html
- /swagger-ui/index.html
- /v3/api-docs/swagger-config
- /v3/api-docs

Ví dụ:

~~~java
@Test
void exposesSwaggerUiAndOpenApiDocument() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ));

    mockMvc.perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk());
}
~~~

Nếu policy yêu cầu document có xác thực, test theo credential và role phù hợp thay vì mong đợi public 200. Cũng kiểm tra tài nguyên giao diện không bị chặn trong khi document được phép, hoặc ngược lại.

Với nhiều SecurityFilterChain, test từng endpoint là cách nhanh để phát hiện chain matcher sai. Một trang HTML 200 không chứng minh các JavaScript/CSS và document JSON đều được phép tải.

## 19. Chẩn đoán CORS khi Swagger UI dùng document hoặc API bên ngoài

Swagger UI có thể cấu hình URL document ngoài ứng dụng:

~~~yaml
springdoc:
  swagger-ui:
    url: https://catalog.example.com/v3/api-docs
~~~

Khi đó trình duyệt tải document từ catalog.example.com. Server cung cấp document phải cho phép origin đang phục vụ Swagger UI. Nếu document tải được nhưng servers trong document trỏ tới host khác, request Try it out cũng cần CORS trên API host đó.

Phân biệt hai luồng:

1. **CORS khi tải OpenAPI document:** browser gọi URL được cấu hình trong Swagger UI.
2. **CORS khi gọi operation:** browser gọi URL trong servers hoặc URL được Swagger UI suy ra.

Mỗi host có thể có policy khác nhau. Bật CORS ở ứng dụng đang phục vụ Swagger UI không tự bật CORS ở API service bên ngoài.

## 20. Đọc log và response headers để xác định lớp từ chối

Trong môi trường phát triển, có thể bật log:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.cors: DEBUG
~~~

Log giúp nhận biết:

- SecurityFilterChain nào được chọn.
- Request bị từ chối ở authentication, authorization hay CSRF filter.
- CORS configuration có khớp origin/method/header không.
- Authentication provider hoặc JWT decoder từ chối credential.

Tắt hoặc hạ log sau khi chẩn đoán. Không ghi access token, session ID, CSRF token hoặc dữ liệu nhạy cảm vào log.

Một số dấu hiệu:

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| 401 và WWW-Authenticate: Bearer | Token, issuer, audience, expiry, signature |
| 403 với log CSRF missing/invalid token | Cookie/header CSRF, token repository, request method |
| 403 với log AccessDenied | Role, authority, scope, matcher |
| OPTIONS 401/403 | CORS chưa chạy trước security hoặc source không được chọn |
| Response không có Access-Control-Allow-Origin | Origin không được phép, path không khớp hoặc CORS chưa cấu hình |
| API trả 200 nhưng browser báo CORS | Response thực tế thiếu CORS headers hoặc redirect sang origin khác |
| /v3/api-docs 401 nhưng UI HTML 200 | Matcher cho document chưa được permit hoặc docs được bảo vệ có chủ đích |

## 21. Những cách sửa dễ gây rủi ro

Tránh các cách xử lý sau:

- Tắt toàn bộ Spring Security chỉ để Swagger UI hoạt động.
- permitAll() cho toàn bộ /api/**.
- Cho phép allowedOrigins("*") cùng allowCredentials(true).
- Tắt CSRF toàn cục khi ứng dụng còn session/cookie authentication.
- Cho phép mọi method/header/origin mà không có nhu cầu rõ ràng.
- Trả token hoặc cookie vào OpenAPI example.
- Hard-code access token vào Swagger UI configuration.
- Cho phép /v3/api-docs/** công khai khi document chứa endpoint nội bộ hoặc schema nhạy cảm.
- Dùng @Hidden để xử lý 401/403; annotation này chỉ ảnh hưởng tài liệu, không cấu hình authorization.

Nếu tài liệu cần public nhưng API cần bảo vệ, cho phép đọc document theo policy riêng và giữ security rule của API. Nếu chính document cũng nhạy cảm, bảo vệ nó bằng authentication có chủ đích và cung cấp credential trước khi Swagger UI tải document.

## 22. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Swagger UI HTML trả 401 | /swagger-ui/** chưa được phép hoặc cần đăng nhập | Kiểm tra matcher và authentication policy |
| Swagger UI HTML 200 nhưng /v3/api-docs 401 | OpenAPI endpoint chưa được phép | Thêm matcher đúng cho docs hoặc cấp credential trước khi tải |
| Try it out trả 401 | Thiếu/sai token hoặc cookie | Kiểm tra Authorization/Cookie trong Network |
| Try it out trả 403 cho GET | Thiếu role/scope hoặc policy authorization | Kiểm tra principal và authority mapping |
| POST trả 403, GET thành công | CSRF token thiếu/sai hoặc authorization POST khác GET | Kiểm tra CSRF header và rule method |
| OPTIONS trả 401 | Preflight bị authentication xử lý trước CORS | Bật http.cors() và cấu hình CORS source |
| OPTIONS trả 403 | Origin/method/header không được phép hoặc filter chặn | So sánh Access-Control-Request-* với policy |
| Browser báo CORS nhưng curl thành công | CORS là chính sách của browser | Kiểm tra response headers bằng browser Network tab |
| Authorization không có trong request | Security scheme hoặc Authorize chưa cấu hình đúng | Kiểm tra OpenAPI security scheme và token |
| Cookie không được gửi cross-origin | credentials mode hoặc SameSite/Secure không phù hợp | Kiểm tra cookie attributes và browser request |
| CSRF cookie có nhưng POST vẫn 403 | Không gửi header đúng, token stale hoặc handler mismatch | Kiểm tra XSRF-TOKEN và X-XSRF-TOKEN |
| CORS chỉ lỗi ở production | Proxy, host, HTTPS hoặc public origin khác local | Kiểm tra Origin và forwarded headers |
| Một API group trả 401 | Group endpoint có security policy khác | Kiểm tra URL group và filter chain |
| Swagger UI gọi nhầm localhost | servers trong OpenAPI sai môi trường | Cấu hình server URL theo profile/môi trường |

## 23. Quy trình xử lý một lỗi Try it out

Thực hiện theo thứ tự:

1. Mở Network tab và tái hiện lỗi.
2. Xác định request lỗi là Swagger UI asset, swagger-config, OpenAPI document, OPTIONS preflight hay API operation.
3. Ghi lại URL, method, status, Origin và request headers.
4. Nếu 401, kiểm tra authentication credential và WWW-Authenticate.
5. Nếu 403, kiểm tra CSRF trước, sau đó kiểm tra role/scope và authorization matcher.
6. Nếu CORS, kiểm tra preflight, origin, method, allowed headers và credentials.
7. Xác định SecurityFilterChain thực sự xử lý request.
8. Sửa matcher hoặc cấu hình đúng lớp; không mở rộng quyền toàn bộ API.
9. Kiểm thử bằng MockMvc hoặc WebTestClient.
10. Kiểm thử lại trong trình duyệt ở đúng origin và môi trường triển khai.

## 24. Tài liệu tham khảo

- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): thứ tự xử lý CORS, CorsConfigurationSource và tích hợp với SecurityFilterChain.
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token, cookie repository, JavaScript application và SPA.
- [Springdoc OpenAPI FAQ](https://springdoc.org/faq.html): bật CSRF support cho Swagger UI bằng springdoc.swagger-ui.csrf.enabled.
- [Springdoc OpenAPI Properties](https://springdoc.org/properties.html): cấu hình Swagger UI, endpoint OpenAPI và các property liên quan.
- [Spring Security – Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matcher và authorization rule.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác thực bearer JWT.
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS configuration trong Spring MVC.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): origin, preflight và CORS response headers.

## 25. Tổng kết áp dụng

401 thường chỉ ra vấn đề authentication; 403 có thể là authorization hoặc CSRF; CORS là chính sách cross-origin của trình duyệt. Ba nhóm lỗi này có thể xuất hiện trên những request khác nhau trong cùng một thao tác Swagger UI.

Hãy xác định đúng request trong Network tab, kiểm tra security filter chain và headers, sau đó điều chỉnh đúng matcher, token flow hoặc CORS policy. Giữ API nghiệp vụ được bảo vệ, chỉ mở các tài nguyên tài liệu theo chủ đích và chỉ bỏ qua CSRF cho những endpoint thực sự stateless. Khi Swagger UI, OpenAPI security scheme và Spring Security runtime được cấu hình nhất quán, thao tác Try it out sẽ phản ánh đúng cách client thật gọi API.
