# Cấu hình @CrossOrigin trên repository

## 1. CORS là gì và vì sao Spring Data REST cần cấu hình?

CORS (Cross-Origin Resource Sharing) là cơ chế HTTP cho phép trình duyệt đọc response từ một origin khác origin của trang web hiện tại khi server cho phép. Origin được xác định bởi bộ ba scheme, host và port.

Ví dụ:

- Frontend chạy tại https://app.example.com.
- Spring Data REST chạy tại https://api.example.com.
- Hai địa chỉ có host khác nhau nên là hai origin khác nhau.
- Một trang tại http://localhost:3000 gọi API tại http://localhost:8080 cũng là cross-origin vì port khác nhau.

Trình duyệt áp dụng same-origin policy để giới hạn việc JavaScript đọc dữ liệu từ origin khác. CORS cho server một cách khai báo origin, method và header nào được phép truy cập từ trình duyệt.

Spring Data REST hỗ trợ CORS thông qua Spring CORS support từ phiên bản 2.6. Có thể cấu hình tại repository interface bằng @CrossOrigin, trên custom repository REST controller hoặc ở cấp toàn cục bằng RepositoryRestConfigurer.

CORS là chính sách do trình duyệt thực thi. Nó không phải authentication, authorization hay cơ chế bảo vệ endpoint khỏi mọi client. Một lệnh curl, ứng dụng backend hoặc công cụ HTTP khác vẫn có thể gửi request trực tiếp dù trình duyệt bị CORS chặn.

## 2. Cấu hình CORS ngay trên repository interface

Spring Data REST cho phép đặt annotation @CrossOrigin trên repository interface. Cấu hình này áp dụng cho các REST resource được xuất bản từ repository đó.

Ví dụ:

~~~~java
@CrossOrigin
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

Khi đặt annotation như trên, repository được bật hỗ trợ cross-origin. Cấu hình mặc định khá rộng, cho phép mọi origin và method theo behavior được tài liệu Spring Data REST mô tả. Không nên dùng cấu hình mở rộng này cho production nếu ứng dụng chỉ cần một frontend cụ thể.

Nên khai báo origin và method rõ ràng:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.DELETE
    },
    maxAge = 3600
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

Trong ví dụ:

- Chỉ origin https://app.example.com được phép gọi từ trình duyệt.
- Chỉ các method GET, POST và DELETE được cho phép qua CORS.
- maxAge = 3600 cho phép trình duyệt cache kết quả preflight trong tối đa một giờ, tùy giới hạn của browser.

CORS configuration không tạo thêm endpoint hoặc method repository. Nếu repository không export DELETE, việc thêm DELETE vào danh sách CORS cũng không làm endpoint DELETE xuất hiện.

## 3. Các thuộc tính quan trọng của @CrossOrigin

Annotation @CrossOrigin của Spring Web cung cấp các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| origins | Danh sách origin được phép |
| originPatterns | Pattern dùng để so khớp origin; cần phiên bản Spring hỗ trợ |
| methods | HTTP method được phép qua CORS |
| allowedHeaders | Request header mà browser được phép gửi |
| exposedHeaders | Response header mà JavaScript được phép đọc |
| allowCredentials | Có cho phép gửi thông tin xác thực của browser hay không |
| maxAge | Thời gian cache kết quả preflight |

Một origin gồm scheme, hostname và port. Ví dụ https://app.example.com và http://app.example.com là hai origin khác nhau; https://app.example.com:8443 cũng khác origin không ghi port.

Khi dùng origins, khai báo chính xác origin, không thêm path của ứng dụng vào giá trị origin:

~~~~java
@CrossOrigin(origins = "https://app.example.com")
~~~~

Nếu có nhiều frontend hợp lệ, có thể liệt kê từng origin:

~~~~java
@CrossOrigin(origins = {
    "https://app.example.com",
    "https://admin.example.com"
})
~~~~

Một số phiên bản Spring hỗ trợ originPatterns để so khớp pattern, ví dụ các subdomain thuộc một domain được kiểm soát. Chỉ dùng pattern đủ hẹp và kiểm tra phiên bản Spring Framework trong dependency tree. Tránh pattern rộng khiến các origin ngoài dự kiến được chấp nhận.

## 4. Phân biệt allowedHeaders và exposedHeaders

Hai thuộc tính này phục vụ hai chiều khác nhau.

**allowedHeaders** kiểm soát request header mà trình duyệt được phép gửi trong cross-origin request. Ví dụ:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    allowedHeaders = {
        "Content-Type",
        "Authorization",
        "If-None-Match",
        "If-Match"
    }
)
~~~~

Nếu frontend gửi Authorization hoặc Content-Type: application/json, server cần cho phép các header tương ứng trong CORS policy. Header do browser tự thêm như Origin không cần khai báo thủ công.

**exposedHeaders** kiểm soát response header mà JavaScript được phép đọc. Một số response header không nằm trong danh sách CORS-safelisted response headers sẽ bị browser ẩn khỏi JavaScript nếu server không expose chúng.

Spring Data REST có thể trả các header như ETag, Location hoặc Link. Nếu frontend cần đọc các giá trị này, hãy expose tường minh:

~~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    exposedHeaders = {
        "ETag",
        "Location",
        "Link"
    }
)
~~~~

Ví dụ, khi dùng ETag để conditional GET hoặc If-Match để cập nhật có điều kiện, frontend chạy trên origin khác cần đọc ETag từ response. Chỉ cho phép request header If-Match/If-None-Match là chưa đủ; nếu JavaScript cần lấy ETag, hãy expose response header ETag.

## 5. Ví dụ repository hoàn chỉnh

Một cấu hình giới hạn cho API people có thể viết:

~~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.RequestMethod;

@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.PUT,
        RequestMethod.PATCH,
        RequestMethod.DELETE
    },
    allowedHeaders = {
        "Content-Type",
        "Authorization",
        "If-None-Match",
        "If-Match"
    },
    exposedHeaders = {
        "ETag",
        "Location",
        "Link"
    },
    maxAge = 3600
)
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

Đây là ví dụ cho frontend cần đọc, tạo, cập nhật và xóa people. Nếu ứng dụng chỉ đọc dữ liệu, nên thu hẹp methods xuống GET và HEAD theo contract endpoint.

Các import quan trọng:

- org.springframework.web.bind.annotation.CrossOrigin
- org.springframework.web.bind.annotation.RequestMethod
- org.springframework.data.rest.core.annotation.RepositoryRestResource

Đặt annotation trên repository interface giúp cấu hình CORS cho cả nhóm resource của repository. Nếu chỉ muốn áp dụng cho một route custom, cân nhắc annotation trên method của controller thay vì mở toàn repository.

## 6. Preflight request và OPTIONS

Không phải cross-origin request nào cũng cần preflight. Với một số request đơn giản, browser có thể gửi request trực tiếp. Với request dùng method hoặc header không thuộc nhóm đơn giản, browser thường gửi một request OPTIONS trước để hỏi server có cho phép request thật hay không.

Ví dụ frontend gửi PATCH với JSON và If-Match. Browser có thể gửi:

~~~~http
OPTIONS /people/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, if-match
~~~~

Server cần trả các header CORS phù hợp, ví dụ:

~~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization, If-None-Match, If-Match
Access-Control-Max-Age: 3600
Vary: Origin
~~~~

Sau khi preflight thành công, browser mới gửi request PATCH thực tế. Nếu preflight thất bại, JavaScript thường chỉ nhận lỗi CORS và request thực tế có thể không được gửi.

OPTIONS preflight không phải thao tác cập nhật resource. Nó là bước thương lượng quyền cross-origin giữa browser và server.

Khi debug, hãy kiểm tra cả request OPTIONS lẫn request GET/POST/PATCH thực tế. Chỉ kiểm tra response của request thật có thể bỏ sót lỗi preflight.

## 7. Cấu hình CORS toàn cục qua RepositoryRestConfigurer

Nếu nhiều repository dùng chung policy, có thể cấu hình CORS theo path ở cấp Spring Data REST bằng RepositoryRestConfigurer.

Ví dụ:

~~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE"
            )
            .allowedHeaders(
                "Content-Type",
                "Authorization",
                "If-None-Match",
                "If-Match"
            )
            .exposedHeaders(
                "ETag",
                "Location",
                "Link"
            )
            .allowCredentials(false)
            .maxAge(3600);
    }
}
~~~~

Mapping /people/** áp dụng policy cho các URL thuộc resource people, bao gồm item path như /people/42. Nếu có association hoặc custom route ở path khác, hãy cấu hình mapping tương ứng.

Ưu điểm của cấu hình toàn cục:

- Gom policy ở một nơi.
- Dùng path pattern để chọn nhóm endpoint.
- Khai báo rõ origin, method, request header và exposed response header.
- Có thể phối hợp với cấu hình annotation ở mức repository hoặc controller.

Dùng cấu hình global khi nhiều repository chia sẻ cùng policy. Dùng annotation khi một repository cần policy riêng. Tránh khai báo các policy chồng lấn nhưng không rõ mục tiêu; hãy kiểm tra response header thực tế sau khi kết hợp.

## 8. Lưu ý quan trọng: Spring MVC CORS không tự áp dụng cho Spring Data REST

Spring Data REST có cấu hình CORS riêng thông qua RepositoryRestConfigurer. Tài liệu Spring Data REST nêu rõ cấu hình Spring Web MVC hiện có không tự động được áp dụng cho Spring Data REST resources.

Vì vậy, nếu ứng dụng đã có:

~~~~java
@Bean
WebMvcConfigurer webMvcConfigurer() {
    return new WebMvcConfigurer() {
        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/api/**")
                    .allowedOrigins("https://app.example.com");
        }
    };
}
~~~~

thì không nên giả định repository resource của Spring Data REST đã được cấu hình CORS theo mapping này. Hãy cấu hình riêng qua RepositoryRestConfigurer hoặc @CrossOrigin trên repository.

Custom controller được đánh dấu @RepositoryRestController có thể dùng @CrossOrigin theo cơ chế controller method của Spring MVC. Các controller này cũng có thể kế thừa cấu hình @CrossOrigin từ repository tương ứng theo tài liệu Spring Data REST.

## 9. CORS với credentials, cookie và Authorization

Một số frontend cần gửi cookie phiên đăng nhập hoặc thông tin xác thực browser. Khi đó CORS policy phải cho phép credentials.

Trong cấu hình toàn cục:

~~~~java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization")
    .allowCredentials(true)
    .maxAge(3600);
~~~~

Khi allowCredentials được bật:

- Không dùng wildcard origin "*" cùng credentials.
- Khai báo origin cụ thể hoặc origin pattern được kiểm soát.
- Browser phải gửi request với credentials mode phù hợp, ví dụ fetch dùng credentials: "include" khi cần cookie cross-origin.
- Cookie vẫn chịu các chính sách SameSite, Secure, domain và path của browser.
- CORS không thay thế kiểm tra session, token, CSRF hoặc quyền truy cập.

Nếu frontend dùng bearer token trong Authorization header, cần cho phép Authorization trong allowedHeaders. Việc gửi token không đồng nghĩa phải bật cookie credentials; chọn policy dựa trên cách xác thực thực tế của ứng dụng.

Không bật credentials chỉ vì frontend và backend nằm ở hai origin khác nhau. Chỉ bật khi ứng dụng thật sự cần browser gửi cookie hoặc thông tin xác thực liên quan.

## 10. CORS không phải authorization hoặc CSRF protection

CORS chủ yếu kiểm soát việc browser cho JavaScript đọc response cross-origin. Nó không ngăn một client ngoài browser gọi API và cũng không chứng minh người gọi có quyền trên dữ liệu.

Ví dụ:

- curl vẫn có thể gửi DELETE trực tiếp đến endpoint.
- Một backend khác vẫn có thể gọi API nếu mạng và authentication cho phép.
- Một trang web có thể gửi một số loại request cross-origin nhưng browser không cho JavaScript đọc response nếu CORS không cho phép.
- Nếu endpoint dùng cookie authentication, cần đánh giá CSRF riêng; CORS policy không thay thế CSRF protection.

Do đó, vẫn phải cấu hình authentication, authorization, method security, tenant checks và CSRF theo mô hình ứng dụng. Không dùng danh sách allowedOrigins như danh sách người dùng được phép truy cập dữ liệu.

## 11. Kiểm thử CORS bằng curl

curl không thực thi same-origin policy như browser, nhưng có thể gửi request và kiểm tra response header.

### Kiểm tra request GET thực tế

~~~~bash
curl -i \
  -H "Origin: https://app.example.com" \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people
~~~~

Kiểm tra response có Access-Control-Allow-Origin phù hợp với origin được phép.

### Kiểm tra preflight OPTIONS

~~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type, if-match" \
  http://localhost:8080/people/42
~~~~

Kiểm tra:

- Access-Control-Allow-Origin có đúng origin.
- Access-Control-Allow-Methods có PATCH.
- Access-Control-Allow-Headers có content-type và if-match.
- Access-Control-Max-Age có giá trị mong đợi.
- Response không bị authentication layer chặn trước khi CORS được xử lý.

### Kiểm tra origin không được phép

~~~~bash
curl -i \
  -H "Origin: https://untrusted.example.net" \
  http://localhost:8080/people
~~~~

Server không nên trả Access-Control-Allow-Origin cho origin ngoài policy. Tuy nhiên, endpoint vẫn có thể trả status HTTP bình thường; điều quan trọng là browser không được phép expose response cho JavaScript của origin đó.

## 12. Kiểm thử bằng MockMvc và trình duyệt

Có thể kiểm tra preflight trong integration test:

~~~~java
mockMvc.perform(options("/people/42")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "PATCH")
        .header(
            "Access-Control-Request-Headers",
            "content-type, if-match"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.com"
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("PATCH")
    ));
~~~~

Có thể bổ sung test cho origin không được phép, header không được phép, method không được phép, credentials và exposed headers.

Cuối cùng, kiểm tra trong browser DevTools:

1. Mở Network.
2. Gửi request từ frontend ở origin khác.
3. Xem request OPTIONS nếu browser thực hiện preflight.
4. Kiểm tra response CORS header.
5. Xem request thực tế có được gửi hay không.
6. Đọc Console để xác định origin, method hoặc header nào bị từ chối.

curl và MockMvc xác nhận response header theo request mô phỏng; browser test xác nhận hành vi thực tế của same-origin policy, cookie và frontend.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Frontend báo CORS dù API trả 200 | Response thiếu Access-Control-Allow-Origin hoặc origin không khớp | Kiểm tra Origin và policy repository/path |
| OPTIONS bị 401 hoặc 403 | Security filter chặn preflight trước CORS handling | Cấu hình thứ tự xử lý CORS phù hợp với Spring Security |
| GET chạy nhưng PATCH thất bại | Preflight không cho phép PATCH hoặc header PATCH cần chưa được allow | Kiểm tra Access-Control-Allow-Methods và Allow-Headers |
| JavaScript không đọc được ETag | ETag chưa nằm trong exposedHeaders | Expose ETag |
| Authorization không gửi được | Authorization chưa được cho phép trong allowedHeaders | Thêm Authorization vào allowedHeaders |
| Cookie không được gửi | Chưa bật credentials hoặc browser cookie policy không cho phép | Kiểm tra allowCredentials, fetch credentials và cookie attributes |
| Cấu hình WebMvcConfigurer không tác dụng | Spring Data REST có CORS registry riêng | Dùng RepositoryRestConfigurer hoặc @CrossOrigin trên repository |
| Dùng "*" với credentials | CORS không cho phép wildcard origin cùng credentials | Khai báo origin cụ thể hoặc pattern an toàn |
| Origin local chạy nhưng production lỗi | Scheme, host hoặc port production khác cấu hình | Khai báo đúng origin production |
| curl thành công nhưng browser lỗi | curl không thực thi CORS policy | Kiểm tra OPTIONS và Console trong browser |

## 14. Kết luận

@CrossOrigin trên repository interface cho phép cấu hình CORS cho các REST resource được Spring Data REST xuất bản từ repository. Có thể giới hạn origin, HTTP method, request header, response header được expose và thời gian cache preflight. Với policy dùng chung hoặc cần cấu hình theo URL path, RepositoryRestConfigurer cung cấp CorsRegistry ở cấp Spring Data REST.

Cần nhớ rằng CORS của Spring Data REST có cấu hình riêng; WebMvcConfigurer không tự động áp dụng cho repository resources. Preflight OPTIONS phải được xử lý trước request thực tế khi browser yêu cầu, response header phải phù hợp với origin/method/header mà frontend sử dụng, và ETag/Location/Link cần được expose nếu JavaScript phải đọc chúng. CORS không thay authentication, authorization hay CSRF protection. Hãy dùng origin cụ thể, giới hạn method/header cần thiết và kiểm tra cả response thực tế lẫn preflight trong browser.

## Tài liệu tham khảo

- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Framework Reference — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Guides — Enabling Cross Origin Requests for a RESTful Web Service](https://spring.io/guides/gs/rest-service-cors)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
