# CORS toàn cục, @CrossOrigin và CorsWebFilter trong Spring WebFlux

CORS (Cross-Origin Resource Sharing) là cơ chế để trình duyệt quyết định JavaScript từ một origin có được phép đọc response của một server khác origin hay không. Trong Spring WebFlux, có ba cách cấu hình thường gặp: khai báo chính sách toàn cục bằng WebFluxConfigurer, giới hạn quyền cho controller bằng @CrossOrigin, và xử lý CORS ở tầng WebFilter bằng CorsWebFilter.

Ba cách này nằm ở các tầng khác nhau. Cấu hình toàn cục phù hợp khi nhiều API dùng chung chính sách; @CrossOrigin tiện khi một controller hoặc method cần quy tắc riêng; CorsWebFilter hữu ích khi muốn xử lý CORS ở tầng filter, bao gồm functional endpoints và các trường hợp cần CORS chạy trước Spring Security.

Bài học thuộc nhóm **Cấu hình WebFlux**, tập trung vào giao thức CORS, preflight request, cách chọn cấu hình, cách kết hợp chính sách, credentials, wildcard origin, thứ tự filter và kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích same-origin policy và vai trò của CORS trong trình duyệt.
- Phân biệt origin theo scheme, host và port.
- Nhận biết simple request và preflight OPTIONS request.
- Đọc các request/response header quan trọng của CORS.
- Cấu hình CORS toàn cục bằng WebFluxConfigurer.addCorsMappings().
- Dùng @CrossOrigin ở cấp controller hoặc method.
- Cấu hình CorsWebFilter và UrlBasedCorsConfigurationSource.
- Chọn cách cấu hình phù hợp với annotated controller và functional endpoint.
- Hiểu cách cấu hình global và local được kết hợp.
- Cấu hình credentials an toàn, tránh wildcard origin không hợp lệ.
- Phân biệt allowedHeaders với exposedHeaders.
- Hiểu maxAge, Vary: Origin và ảnh hưởng của cache.
- Đặt CORS đúng vị trí khi ứng dụng dùng Spring Security reactive.
- Kiểm thử preflight và actual request bằng WebTestClient.

## 2. Same-origin policy và CORS

Trình duyệt áp dụng same-origin policy để hạn chế JavaScript đọc dữ liệu từ origin khác. Một origin được xác định bởi ba thành phần:

- Scheme: http hoặc https.
- Host: tên miền hoặc địa chỉ máy chủ.
- Port: cổng kết nối.

Ví dụ:

| URL | So với https://app.example.com | Cùng origin? |
| --- | --- | --- |
| https://app.example.com/orders | Cùng scheme, host, port | Có |
| https://app.example.com:443/profile | Cổng mặc định của HTTPS | Có |
| http://app.example.com/orders | Khác scheme | Không |
| https://api.example.com/orders | Khác host | Không |
| https://app.example.com:8443/orders | Khác port | Không |

CORS cho phép server công bố origin nào được đọc response, method nào được dùng, request header nào được gửi và response header nào JavaScript được phép nhìn thấy.

Ví dụ frontend chạy tại https://app.example.com gọi API tại https://api.example.com. Đây là cross-origin request. API cần trả các CORS response header phù hợp để trình duyệt cho phép frontend đọc kết quả.

### CORS không phải cơ chế xác thực

CORS là chính sách do trình duyệt thực thi. Nó không thay thế authentication, authorization hoặc CSRF protection.

- HTTP client như curl, Postman hoặc service-to-service client không tự áp dụng same-origin policy của trình duyệt.
- CORS không ngăn một chương trình bên ngoài gửi request tới server.
- CORS chủ yếu quyết định trình duyệt có cho JavaScript đọc response hay không.
- Server vẫn phải xác thực người dùng và kiểm tra quyền trên từng API.
- Với cookie/session authentication, vẫn phải đánh giá CSRF theo mô hình bảo mật của ứng dụng.

Không dùng CORS như cách bảo vệ dữ liệu nhạy cảm. Nếu API không yêu cầu đăng nhập, CORS không biến API đó thành API riêng tư.

## 3. Simple request và preflight request

Trình duyệt có thể gửi một số cross-origin request trực tiếp. Với request không thuộc nhóm đơn giản, trình duyệt thường gửi một request kiểm tra trước, gọi là **preflight**.

### Simple request

Một số request có thể không cần preflight, ví dụ GET đơn giản hoặc POST với Content-Type thuộc nhóm được CORS xem là safelisted, miễn là method và request headers thỏa điều kiện của chuẩn.

Request thực tế có thể chứa:

~~~http
GET /api/products HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Accept: application/json
~~~

Server trả response có thể gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json
~~~

Trình duyệt kiểm tra Access-Control-Allow-Origin. Nếu origin được phép, JavaScript có thể đọc response.

### Preflight request

Các request như PUT, DELETE hoặc request có header tùy chỉnh như Authorization thường cần preflight. Trình duyệt gửi OPTIONS trước request thật:

~~~http
OPTIONS /api/products/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Server cần trả lời bằng chính sách tương ứng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Nếu preflight hợp lệ, trình duyệt mới tiếp tục gửi request thật. Nếu preflight thất bại, trình duyệt thường không gửi request thật.

Không phải mọi OPTIONS request đều là CORS preflight. Một preflight có Origin và Access-Control-Request-Method; OPTIONS thông thường có thể là request nghiệp vụ hoặc request do công cụ khác gửi.

## 4. Các CORS header quan trọng

| Header | Hướng | Ý nghĩa |
| --- | --- | --- |
| Origin | Request | Origin của trang web khởi tạo request |
| Access-Control-Request-Method | Preflight request | Method mà trình duyệt muốn gửi |
| Access-Control-Request-Headers | Preflight request | Các request header mà trình duyệt muốn gửi |
| Access-Control-Allow-Origin | Response | Origin được phép đọc response, hoặc * trong trường hợp phù hợp |
| Access-Control-Allow-Methods | Response | Các method được phép |
| Access-Control-Allow-Headers | Response | Các request header được phép |
| Access-Control-Allow-Credentials | Response | Cho phép request dùng credentials của browser |
| Access-Control-Expose-Headers | Response | Các response header được JavaScript đọc |
| Access-Control-Max-Age | Preflight response | Thời gian trình duyệt có thể cache kết quả preflight |
| Vary | Response | Chỉ ra request header ảnh hưởng đến response/cache variant |

### allowedHeaders và exposedHeaders khác nhau

Hai cấu hình này thường bị nhầm:

- **allowedHeaders:** request header mà browser được phép gửi, ví dụ Authorization, Content-Type, X-Request-Id.
- **exposedHeaders:** response header mà JavaScript được phép đọc, ví dụ X-Request-Id hoặc ETag.

Ví dụ, server có thể trả X-Request-Id nhưng JavaScript không đọc được header đó nếu nó không nằm trong danh sách exposed headers (trừ các response header safelisted mặc định).

### allowCredentials

Khi browser cần gửi cookie hoặc credentials theo credentials mode, server phải cho phép credentials bằng:

~~~http
Access-Control-Allow-Credentials: true
~~~

Trong Spring, cấu hình tương ứng là allowCredentials(true).

Nếu cho phép credentials, không được dùng allowedOrigins("*"). CORS không cho phép response kết hợp wildcard origin với Access-Control-Allow-Credentials: true. Hãy chỉ định origin cụ thể hoặc dùng allowedOriginPatterns với danh sách pattern được kiểm soát. Khi dùng pattern, Spring trả lại origin thực tế đã khớp thay vì gửi ký tự wildcard.

### maxAge

maxAge quy định thời gian browser có thể cache kết quả preflight, tính bằng giây. Giá trị lớn giúp giảm số OPTIONS request nhưng cũng khiến thay đổi chính sách có thể chưa có hiệu lực với các kết quả đã cache cho đến khi hết hạn.

maxAge không phải thời hạn cache response API thông thường.

## 5. Cấu hình CORS toàn cục bằng WebFluxConfigurer

Với annotated controller, cách phổ biến là tạo class implements WebFluxConfigurer và override addCorsMappings().

~~~java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Content-Type",
                "Authorization",
                "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Giải thích:

- addMapping("/api/**") áp dụng chính sách cho các URL khớp path pattern.
- allowedOrigins() liệt kê origin cụ thể được phép.
- allowedMethods() giới hạn method.
- allowedHeaders() giới hạn request header.
- exposedHeaders() công bố response header cho JavaScript.
- allowCredentials(true) cho phép browser gửi credentials theo chính sách CORS.
- maxAge(3600) cho browser cache preflight tối đa một giờ.

Cấu hình toàn cục phù hợp khi nhiều controller cùng chia sẻ một chính sách. Có thể khai báo nhiều mapping cho các nhóm URL khác nhau, ví dụ /api/public/** và /api/admin/**.

### Ví dụ nhiều nhóm endpoint

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/public/**")
        .allowedOrigins("https://www.example.com")
        .allowedMethods("GET")
        .allowedHeaders("Accept")
        .maxAge(1800);

    registry.addMapping("/api/admin/**")
        .allowedOrigins("https://admin.example.com")
        .allowedMethods("GET", "POST", "PUT", "DELETE")
        .allowedHeaders("Authorization", "Content-Type")
        .allowCredentials(true)
        .maxAge(300);
}
~~~

Tách mapping giúp chính sách rõ ràng theo khu vực API. Không mở toàn bộ /api/** nếu chỉ một nhóm frontend cần truy cập.

## 6. Dùng @CrossOrigin ở cấp controller hoặc method

@CrossOrigin là annotation khai báo CORS tại controller hoặc handler method.

### Cấu hình ở cấp controller

~~~java
@RestController
@RequestMapping("/reports")
@CrossOrigin(
    origins = "https://dashboard.example.com",
    allowedHeaders = {"Authorization", "Content-Type"},
    methods = {RequestMethod.GET, RequestMethod.POST},
    maxAge = 1800)
public class ReportController {

    @GetMapping
    public List<String> reports() {
        return List.of("daily", "monthly");
    }
}
~~~

Các handler trong controller áp dụng chính sách annotation này, trừ khi method có cấu hình local bổ sung hoặc thay thế theo quy tắc kết hợp của Spring.

### Cấu hình ở cấp method

~~~java
@RestController
@RequestMapping("/documents")
public class DocumentController {

    @GetMapping("/{id}")
    @CrossOrigin(
        origins = "https://reader.example.com",
        methods = RequestMethod.GET)
    public Map<String, String> find(@PathVariable String id) {
        return Map.of("id", id, "name", "guide.pdf");
    }

    @PostMapping
    @CrossOrigin(
        origins = "https://editor.example.com",
        methods = RequestMethod.POST,
        allowedHeaders = {"Content-Type", "Authorization"})
    public Map<String, String> create() {
        return Map.of("status", "created");
    }
}
~~~

Method-level annotation hữu ích khi từng endpoint cần origin hoặc method khác nhau.

### Giá trị mặc định cần lưu ý

Nếu không chỉ định thuộc tính, @CrossOrigin có các mặc định khá rộng: mọi origin, mọi request header và các method mà handler hỗ trợ; maxAge mặc định là 1800 giây. Hãy khai báo rõ origins và các quyền cần thiết thay vì dựa vào mặc định trong ứng dụng production.

Đặc biệt, không thêm @CrossOrigin trống vào controller chỉ để “bật CORS” nếu chính sách toàn cục đang giới hạn origin. Một cấu hình local rộng có thể làm thay đổi kết quả kết hợp và mở rộng quyền ngoài dự kiến.

## 7. Kết hợp cấu hình toàn cục và @CrossOrigin

Spring cho phép kết hợp CORS config toàn cục với cấu hình local ở controller/method. Các danh sách như origins, methods, allowed headers và exposed headers có thể được kết hợp; một số thuộc tính đơn như allowCredentials và maxAge có quy tắc ưu tiên giá trị local khi được đặt.

Vì vậy, không nên suy luận rằng annotation local luôn thu hẹp cấu hình toàn cục. Một danh sách origin local rộng, đặc biệt là wildcard, có thể mở rộng chính sách hiệu lực.

Ví dụ:

- Global chỉ cho https://app.example.com.
- Một method có @CrossOrigin(origins = "https://admin.example.com").
- Cấu hình hiệu lực có thể cho phép cả hai origin theo cách kết hợp của Spring.

Hãy xem chính sách hiệu lực là kết quả của cả hai nguồn. Nếu cần chính sách chặt chẽ, hãy khai báo origin rõ ràng ở cả global và local, sau đó kiểm thử bằng request có Origin tương ứng.

Không cấu hình credentials cùng wildcard origin. Nếu global và local kết hợp thành wildcard trong khi credentials được bật, cấu hình có thể bị từ chối hoặc không tạo được response CORS hợp lệ.

## 8. allowedOrigins và allowedOriginPatterns

Spring cung cấp hai cách để khai báo origin:

- allowedOrigins: danh sách origin chính xác.
- allowedOriginPatterns: danh sách pattern để khớp origin.

Ví dụ origin chính xác:

~~~java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com")
~~~

Ví dụ pattern:

~~~java
.allowedOriginPatterns(
    "https://*.example.com",
    "https://preview-*.example.net")
~~~

Pattern hữu ích khi có nhiều subdomain được kiểm soát, chẳng hạn tenant hoặc môi trường preview. Với allowedOriginPatterns, Spring kiểm tra origin thực tế và trả lại origin khớp trong Access-Control-Allow-Origin. Cách này có thể dùng cùng allowCredentials(true), nhưng pattern vẫn phải giới hạn vào các domain đáng tin cậy.

Tránh các pattern rộng như * trong hệ thống có credentials. Không phản chiếu bất kỳ Origin nào mà client gửi lên. Origin là dữ liệu do caller cung cấp; phải đối chiếu với allowlist hoặc pattern được kiểm soát.

## 9. CorsWebFilter là gì?

CorsWebFilter là WebFilter của Spring WebFlux xử lý CORS ở tầng reactive filter. Nó nhận CorsConfigurationSource để tìm chính sách theo request path.

CorsWebFilter đặc biệt hữu ích khi:

- Muốn xử lý CORS ở tầng filter trước các filter khác.
- Dùng functional endpoints với RouterFunction.
- Muốn tập trung chính sách CORS trong một bean.
- Cần CORS chạy trước Spring Security để preflight không bị yêu cầu authentication.

Ví dụ cấu hình:

~~~java
package com.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class FilterCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.com"));
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(
            List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);

        return new CorsWebFilter(source);
    }
}
~~~

Trong ví dụ, source đăng ký chính sách cho /api/**. CorsWebFilter đọc Origin và các preflight header, tìm configuration phù hợp, rồi xử lý CORS trước khi request đi sâu vào filter chain.

### CorsWebFilter và WebFluxConfigurer có phải bật cùng lúc?

Thông thường, hãy chọn một cách làm chủ đạo cho cùng một path:

- WebFluxConfigurer.addCorsMappings() cho cấu hình CORS gắn với WebFlux handler mappings.
- CorsWebFilter cho xử lý CORS ở tầng filter.

Không đăng ký hai chính sách khác nhau cùng path nếu chưa hiểu rõ thứ tự và cách chúng tương tác. Cấu hình trùng lặp có thể gây response header khó dự đoán hoặc làm việc debug preflight phức tạp.

Nếu dùng Spring Security, hãy chọn cách tích hợp CORS mà Security quản lý hoặc bảo đảm filter CORS chạy trước Security. Không thêm nhiều filter CORS chỉ để cố sửa lỗi preflight.

## 10. CORS với functional endpoints

Functional endpoint dùng RouterFunction và HandlerFunction thay cho annotation controller:

~~~java
@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
            RequestPredicates.GET("/functional/status"),
            request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("status", "ok")));
    }
}
~~~

Functional route không có method để đặt @CrossOrigin như annotated controller. Khi cần CORS cho nhóm route này, CorsWebFilter là lựa chọn rõ ràng vì nó áp dụng theo request path ở tầng filter.

Ví dụ, đăng ký /functional/** trong UrlBasedCorsConfigurationSource:

~~~java
source.registerCorsConfiguration("/functional/**", functionalCorsConfig);
~~~

Có thể dùng cùng CorsWebFilter để đăng ký nhiều path pattern, mỗi pattern một CorsConfiguration. Chính sách cần thống nhất với các endpoint annotated khác nếu chúng cùng phục vụ một frontend.

## 11. CORS và Spring Security WebFlux

CORS phải được xử lý trước bước authorization của Spring Security. Một preflight request thường không có cookie session hoặc thông tin xác thực như request thật. Nếu Security chặn OPTIONS trước khi CORS xử lý, browser sẽ báo preflight thất bại và không gửi request thật.

Với Spring Security reactive, có thể cung cấp CorsConfigurationSource và bật CORS trong ServerHttpSecurity:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(
        List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));
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
        CorsConfigurationSource corsConfigurationSource) {

    return http
        .cors(cors ->
            cors.configurationSource(corsConfigurationSource))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đoạn này cần dependency spring-boot-starter-security và các import tương ứng từ Spring Security. Nếu ứng dụng đã dùng CorsWebFilter riêng, hãy tránh đăng ký một chính sách CORS thứ hai trong Security mà không có chủ đích. Chọn một cấu hình rõ ràng và xác nhận CORS được xử lý trước authorization.

Cho phép OPTIONS trong authorization rule làm rõ ý định đối với preflight, nhưng không thay thế cấu hình CORS. Server vẫn phải kiểm tra Origin, method và headers được yêu cầu.

CORS cũng không làm cho request thật được miễn authentication. Request GET/POST thực tế vẫn phải qua authentication và authorization theo chính sách ứng dụng.

## 12. Credentials, cookie và Authorization header

Nếu frontend dùng cookie session hoặc credentials mode, cấu hình cần đồng bộ giữa browser và server.

Ví dụ frontend:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Server cần trả origin cụ thể và:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Không được trả:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser sẽ từ chối response này theo quy tắc CORS.

Nếu frontend gửi Authorization header, preflight phải cho phép header đó trong Access-Control-Allow-Headers. allowCredentials và việc cho phép Authorization header là hai cấu hình có liên quan tới request nhưng không đồng nghĩa: Authorization là request header cần được allow; allowCredentials kiểm soát credentials mode của browser.

Với cookie cross-site, còn cần xem xét thuộc tính cookie như SameSite và Secure. CORS đúng không bảo đảm browser sẽ gửi cookie nếu cookie policy không cho phép.

## 13. Vary: Origin và cache

Khi server trả response khác nhau tùy Origin, cache phải biết response phụ thuộc header Origin. Vary: Origin giúp cache phân biệt các biến thể response theo origin.

Với preflight, response còn phụ thuộc method và request headers được yêu cầu; vì vậy response có thể chứa:

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Spring CORS processor quản lý các Vary header phù hợp trong quá trình xử lý. Nếu tự viết filter/proxy để thêm CORS header, cần giữ đúng Vary để tránh cache response của một origin rồi phục vụ nhầm cho origin khác.

Không cấu hình CDN cache CORS response theo URL duy nhất nếu response header thay đổi theo Origin mà cache key không xét Origin.

## 14. Cách chẩn đoán lỗi CORS

Lỗi CORS thường hiển thị trong browser console, nhưng nguyên nhân có thể nằm ở server, proxy, authentication hoặc cache.

Quy trình kiểm tra:

1. Mở DevTools Network và tìm OPTIONS request.
2. Kiểm tra Origin của trang frontend.
3. Kiểm tra Access-Control-Request-Method.
4. Kiểm tra Access-Control-Request-Headers.
5. Xem status và response header của preflight.
6. Đối chiếu Access-Control-Allow-Origin với origin thật.
7. Kiểm tra method và header được cho phép.
8. Nếu dùng credentials, xác nhận allow-credentials là true và allow-origin không phải *.
9. Kiểm tra OPTIONS có bị Spring Security, gateway hoặc reverse proxy chặn không.
10. Kiểm tra redirect: preflight và redirect giữa các origin có thể không được browser xử lý như mong đợi.
11. Kiểm tra Vary và cache nếu chỉ một số người dùng/origin gặp lỗi.
12. Kiểm tra response thực tế bằng curl, nhưng nhớ rằng curl không thực thi same-origin policy của browser.

### Ví dụ kiểm tra preflight bằng curl

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/products" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Lệnh này cho phép quan sát response header. Nó không chứng minh browser chắc chắn cho JavaScript đọc response; cần kiểm tra chính sách browser và request thực tế.

### Một số dấu hiệu thường gặp

- **No Access-Control-Allow-Origin:** server không áp dụng CORS config cho path/origin hoặc proxy đã bỏ header.
- **Origin không khớp:** khác scheme, host hoặc port; kiểm tra cả port.
- **Method không được phép:** Access-Control-Request-Method không nằm trong allowedMethods.
- **Header không được phép:** một request header không nằm trong allowedHeaders.
- **Credentials không hợp lệ:** wildcard origin được dùng cùng credentials.
- **Preflight nhận 401/403:** Security hoặc gateway chặn OPTIONS trước CORS.
- **JavaScript không đọc được custom response header:** thiếu exposedHeaders.
- **Chỉ lỗi sau deploy:** proxy/cache hoặc origin production khác origin local.

## 15. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này dùng cấu hình toàn cục bằng WebFluxConfigurer và một endpoint riêng dùng @CrossOrigin. CorsWebFilter được trình bày như một lựa chọn thay thế; không đăng ký đồng thời filter đó trong cùng ứng dụng mẫu.

### Cấu trúc project

~~~text
webflux-cors-demo/
├── pom.xml
└── src
    ├── main/java/com/example/cors
    │   ├── CorsDemoApplication.java
    │   ├── GlobalCorsConfiguration.java
    │   └── CorsController.java
    └── test/java/com/example/cors
        └── CorsControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-cors-demo</artifactId>
  <version>1.0.0</version>

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

### CorsDemoApplication.java

~~~java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### GlobalCorsConfiguration.java

~~~java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Content-Type",
                "Authorization",
                "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

### CorsController.java

~~~java
package com.example.cors;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CorsController {

    @GetMapping("/api/products")
    public List<Map<String, String>> products() {
        return List.of(
            Map.of("id", "p-1", "name", "Keyboard"),
            Map.of("id", "p-2", "name", "Mouse"));
    }

    @GetMapping("/api/products/{id}")
    public Map<String, String> product(@PathVariable String id) {
        return Map.of("id", id, "name", "Example product");
    }

    @GetMapping("/annotated/info")
    @CrossOrigin(
        origins = "https://admin.example.com",
        methods = RequestMethod.GET,
        allowedHeaders = {"Authorization"})
    public Map<String, String> annotatedInfo() {
        return Map.of("scope", "method-level CORS");
    }
}
~~~

Endpoint /api/** dùng chính sách toàn cục. Endpoint /annotated/info dùng @CrossOrigin riêng và minh họa cấu hình theo method.

### CorsControllerTests.java

~~~java
package com.example.cors;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(CorsController.class)
@Import(GlobalCorsConfiguration.class)
class CorsControllerTests {

    @Autowired
    private WebTestClient client;

    @Test
    void allowsConfiguredOriginOnActualRequest() {
        client.get()
            .uri("/api/products")
            .header("Origin", "https://app.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com")
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Credentials",
                "true")
            .expectHeader()
            .exists("Access-Control-Expose-Headers");
    }

    @Test
    void acceptsPreflightForAllowedMethodAndHeaders() {
        client.options()
            .uri("/api/products")
            .header("Origin", "https://app.example.com")
            .header(
                "Access-Control-Request-Method",
                "POST")
            .header(
                "Access-Control-Request-Headers",
                "authorization,content-type,x-request-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://app.example.com")
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Credentials",
                "true")
            .expectHeader()
            .exists("Access-Control-Allow-Methods")
            .expectHeader()
            .exists("Access-Control-Allow-Headers");
    }

    @Test
    void rejectsPreflightFromUnknownOrigin() {
        client.options()
            .uri("/api/products")
            .header("Origin", "https://untrusted.example.org")
            .header(
                "Access-Control-Request-Method",
                "GET")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void appliesMethodLevelCrossOrigin() {
        client.get()
            .uri("/annotated/info")
            .header("Origin", "https://admin.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://admin.example.com");
    }
}
~~~

Các test xác minh response header CORS cho actual request, preflight, origin không được phép và annotation method-level. WebTestClient kiểm tra hành vi server; nó không thay thế kiểm thử browser thật vì browser còn áp dụng chính sách same-origin và cookie.

Chạy test:

~~~bash
mvn -q test
~~~

Nếu bốn test pass, Maven kết thúc với exit code 0.

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra actual request:

~~~bash
curl -i "http://localhost:8080/api/products" \
  -H "Origin: https://app.example.com"
~~~

Kiểm tra preflight:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/products" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

## 16. Lỗi thường gặp và cách khắc phục

1. **Nhầm origin với domain.** Origin gồm scheme, host và port. Hãy so sánh đầy đủ URL origin.
2. **Cho rằng CORS là authentication.** CORS chỉ là chính sách browser đọc response; server vẫn phải xác thực và phân quyền.
3. **Chỉ cấu hình allowedOrigins nhưng quên method.** Preflight có thể thất bại nếu method yêu cầu không được phép.
4. **Quên Authorization trong allowedHeaders.** Browser gửi preflight và server từ chối custom header.
5. **Dùng allowedHeaders như exposedHeaders.** Một cái cho request header; cái kia cho response header JavaScript được đọc.
6. **Dùng wildcard origin cùng credentials.** Cấu hình này không hợp lệ; dùng origin cụ thể hoặc pattern có kiểm soát.
7. **Phản chiếu mọi Origin request.** Điều đó tương đương cho phép mọi website; hãy kiểm tra allowlist.
8. **Để @CrossOrigin mặc định rộng.** Khai báo rõ origins, methods và headers cho endpoint.
9. **Cho rằng method-level annotation luôn thu hẹp global.** Cấu hình local và global được kết hợp; danh sách local có thể mở rộng quyền.
10. **Đăng ký CorsWebFilter và WebFluxConfigurer cho cùng path mà không có chủ đích.** Có thể tạo chính sách trùng lặp hoặc response header khó hiểu.
11. **Để Spring Security chặn OPTIONS.** CORS cần được xử lý trước authorization; tích hợp CORS trong Security reactive.
12. **Cho rằng permitAll OPTIONS là đủ.** Preflight còn cần CORS response header đúng origin, method và headers.
13. **Quên exposedHeaders.** Browser có thể nhận response header nhưng JavaScript không đọc được custom header.
14. **Đặt maxAge quá dài khi chính sách thay đổi thường xuyên.** Browser có thể tiếp tục dùng kết quả preflight cache cũ.
15. **Quên Vary: Origin.** Cache có thể dùng response của origin này cho origin khác.
16. **Kiểm tra bằng curl rồi kết luận browser sẽ hoạt động.** curl không áp dụng CORS; cần kiểm tra bằng browser.
17. **Chỉ kiểm tra actual GET mà bỏ preflight.** PUT, DELETE hoặc custom headers có thể thất bại trước khi request thật được gửi.
18. **Nhầm mọi OPTIONS là preflight.** Preflight phải có Origin và Access-Control-Request-Method.
19. **Dùng CORS để bảo vệ API khỏi server khác.** Server-to-server client không bị browser same-origin policy chi phối.
20. **Không xét cookie SameSite/Secure.** CORS hợp lệ vẫn chưa đủ để browser gửi cookie cross-site.

## 17. Checklist triển khai CORS

Trước khi phát hành WebFlux API, hãy kiểm tra:

- **Origin inventory:** frontend production, staging và local dev dùng origin nào?
- **Path scope:** CORS áp dụng cho path nào?
- **Allowed origins:** có dùng allowlist cụ thể không?
- **Methods:** chỉ cho phép method cần thiết?
- **Request headers:** Authorization, Content-Type và custom headers đã khai báo?
- **Exposed headers:** JavaScript cần đọc header nào?
- **Credentials:** có thực sự cần cookie/credentials không?
- **Wildcard:** không kết hợp wildcard origin với credentials?
- **Preflight:** OPTIONS được xử lý trước authentication/authorization?
- **Configuration style:** WebFluxConfigurer, @CrossOrigin hay CorsWebFilter?
- **Combination:** global/local policy có vô tình mở rộng origin không?
- **Functional routes:** nếu dùng RouterFunction, filter-level policy đã bao phủ?
- **Cache:** Vary và maxAge phù hợp?
- **Security:** authentication, authorization và CSRF vẫn được cấu hình riêng?
- **Testing:** actual request, preflight, denied origin và credentials được kiểm thử?
- **Browser:** đã kiểm tra DevTools trên origin production thực tế?

## 18. Bài tập tự kiểm tra

**Bài 1.** Hai URL có cùng host nhưng khác scheme có cùng origin không?  
**Đáp án:** Không. Origin bao gồm scheme, host và port.

**Bài 2.** Preflight request thường dùng HTTP method nào?  
**Đáp án:** OPTIONS.

**Bài 3.** Access-Control-Request-Method cho biết điều gì?  
**Đáp án:** Method mà browser muốn dùng cho request thật.

**Bài 4.** allowedHeaders và exposedHeaders khác nhau thế nào?  
**Đáp án:** allowedHeaders cho phép request gửi header; exposedHeaders cho phép JavaScript đọc response header.

**Bài 5.** Vì sao không dùng allowedOrigins("*") cùng allowCredentials(true)?  
**Đáp án:** CORS không cho phép wildcard Access-Control-Allow-Origin kết hợp Access-Control-Allow-Credentials: true.

**Bài 6.** WebFluxConfigurer.addCorsMappings() dùng để làm gì?  
**Đáp án:** Khai báo chính sách CORS toàn cục theo URL mapping.

**Bài 7.** @CrossOrigin có thể đặt ở đâu?  
**Đáp án:** Ở cấp controller hoặc handler method.

**Bài 8.** CorsWebFilter xử lý CORS ở tầng nào?  
**Đáp án:** WebFilter reactive, trước phần handler/filter chain tiếp theo.

**Bài 9.** Vì sao CORS cần chạy trước Spring Security?  
**Đáp án:** Preflight thường không mang cookie/session; nếu Security chặn trước, browser không nhận được CORS response hợp lệ.

**Bài 10.** maxAge có ý nghĩa gì?  
**Đáp án:** Thời gian browser có thể cache kết quả preflight, tính bằng giây.

**Bài 11.** Vary: Origin giúp gì?  
**Đáp án:** Báo cho cache biết response phụ thuộc Origin để tránh dùng nhầm response giữa các origin.

**Bài 12.** curl thành công có chứng minh browser không gặp lỗi CORS không?  
**Đáp án:** Không. curl không thực thi same-origin policy; cần kiểm tra browser và preflight thực tế.

## 19. Ghi nhớ

CORS là cơ chế browser kiểm soát việc JavaScript đọc response cross-origin. Origin gồm scheme, host và port. Preflight dùng OPTIONS cùng Origin, Access-Control-Request-Method và có thể có Access-Control-Request-Headers. Server phải trả đúng Access-Control-Allow-Origin, Methods, Headers và Credentials nếu cần.

Trong WebFlux, WebFluxConfigurer.addCorsMappings() cấu hình chính sách toàn cục; @CrossOrigin cấu hình ở controller hoặc method; CorsWebFilter xử lý CORS ở tầng filter và phù hợp khi cần bao phủ functional routes hoặc xử lý trước Spring Security. Chọn một cách cấu hình chủ đạo cho từng path, tránh đăng ký chính sách trùng lặp.

Credentials không thể đi cùng wildcard origin. allowedHeaders điều khiển request header; exposedHeaders điều khiển response header JavaScript được đọc. maxAge cache preflight; Vary: Origin giúp cache phân biệt response theo origin. Cuối cùng, CORS không thay thế authentication, authorization hay CSRF protection. Hãy kiểm thử actual request, preflight và browser production.

### Tài liệu tham khảo

- Spring Framework, [CORS in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html).
- Spring Framework, [WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework Javadoc, [CrossOrigin](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/CrossOrigin.html).
- Spring Framework Javadoc, [CorsWebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html).
- Spring Framework Javadoc, [CorsConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html).
- Spring Security, [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- MDN, [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS).
