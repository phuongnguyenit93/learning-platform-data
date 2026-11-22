# Phối hợp CORS với Spring Security và yêu cầu OPTIONS

## 1. Vì sao CORS và Spring Security cần phối hợp?

CORS (Cross-Origin Resource Sharing) cho phép trình duyệt đọc response từ một origin khác khi server cho phép. Với ứng dụng Spring Data REST, frontend thường chạy ở origin riêng, ví dụ:

- Frontend: \`https://app.example.com\`
- API: \`https://api.example.com\`

Hai địa chỉ có host khác nhau nên là cross-origin. Khi frontend gọi API bằng JavaScript, browser áp dụng same-origin policy và kiểm tra các CORS response header.

Spring Security lại kiểm tra authentication và authorization trước khi request tới controller hoặc Spring Data REST exporter. Nếu CORS được xử lý quá muộn, request preflight có thể bị Spring Security từ chối trước khi server trả các header CORS cần thiết.

Điểm quan trọng là **CORS phải được xử lý trước bước xác thực của Spring Security**. Preflight request thường không gửi cookie phiên đăng nhập như JSESSIONID. Nếu security filter yêu cầu người dùng đã đăng nhập trước khi CORS được xử lý, preflight có thể nhận 401 hoặc 403 và browser sẽ không gửi request thực tế.

Spring Security hỗ trợ tích hợp CORS qua \`http.cors(...)\`. Ứng dụng có thể cung cấp \`CorsConfigurationSource\` để mô tả origin, method và header được phép.

## 2. Preflight OPTIONS là gì?

Một số cross-origin request được browser gửi trực tiếp. Những request khác cần một bước kiểm tra trước gọi là **preflight**. Browser gửi HTTP OPTIONS để hỏi server xem request thật có được phép hay không.

Preflight thường xuất hiện khi request dùng:

- Method không thuộc nhóm CORS-safelisted, chẳng hạn PUT, PATCH hoặc DELETE.
- Header không thuộc nhóm safelisted, chẳng hạn Authorization, If-Match hoặc If-None-Match.
- Content-Type không thuộc các giá trị safelisted; ví dụ \`application/json\` thường khiến browser thực hiện preflight.

Ví dụ frontend muốn gửi PATCH JSON với If-Match. Browser có thể gửi request:

~~~~http
OPTIONS /people/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, if-match
~~~~

Ba thành phần cần hiểu:

- \`Origin\` cho biết trang web đang chạy ở origin nào.
- \`Access-Control-Request-Method\` cho biết method của request thực tế mà browser muốn gửi.
- \`Access-Control-Request-Headers\` liệt kê các request header mà browser muốn dùng.

Preflight không phải thao tác PATCH resource. Nó là bước thương lượng quyền cross-origin. Nếu preflight được chấp nhận, browser mới gửi request PATCH thật.

Không phải mọi OPTIONS đều là preflight. Một request OPTIONS thông thường có thể là endpoint API dùng để khám phá khả năng của resource. Có thể nhận diện CORS preflight bằng các dấu hiệu Origin, Access-Control-Request-Method và method OPTIONS; Spring cung cấp \`CorsUtils.isPreFlightRequest(...)\` để kiểm tra.

## 3. Luồng xử lý đúng với Spring Security

Luồng cần đạt được:

~~~~text
Browser
   |
   | OPTIONS + Origin + Access-Control-Request-Method
   v
Spring Security CORS filter
   |
   +-- Origin/method/header không hợp lệ --> từ chối preflight
   |
   +-- Preflight hợp lệ
          |
          v
       Trả CORS response headers
       Không yêu cầu session cookie cho preflight
          |
          v
       Browser gửi request thật
          |
          v
       Spring Security authentication
          |
          v
       Authorization rules
          |
          v
       Spring Data REST / repository
          |
          v
       Response thực tế kèm CORS headers
~~~~

CORS filter của Spring Security được đặt trước các filter bảo mật có thể yêu cầu authentication. Khi cấu hình đúng, preflight hợp lệ được xử lý trước; request thực tế vẫn đi qua authentication và authorization bình thường.

Cho phép preflight không có nghĩa là cho phép người dùng đọc hoặc sửa resource. CORS chỉ cho browser biết request cross-origin có được phép tiếp tục hay không. Security rules vẫn quyết định ai được truy cập API.

## 4. Cấu hình CorsConfigurationSource

Một cách phổ biến là khai báo bean \`CorsConfigurationSource\`. Bean này mô tả policy mà Spring Security dùng khi xử lý CORS.

Ví dụ frontend ở \`https://app.example.com\`, cần GET, POST, PUT, PATCH và DELETE:

~~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();

        configuration.setAllowedOrigins(
                List.of("https://app.example.com")
        );

        configuration.setAllowedMethods(List.of(
                "GET", "POST", "PUT", "PATCH", "DELETE"
        ));

        configuration.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match"
        ));

        configuration.setExposedHeaders(List.of(
                "ETag",
                "Location",
                "Link"
        ));

        configuration.setAllowCredentials(true);
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
~~~~

Ý nghĩa các cấu hình:

| Cấu hình | Mục đích |
|---|---|
| allowedOrigins | Origin frontend được phép truy cập |
| allowedMethods | Method thực tế mà browser được phép gửi |
| allowedHeaders | Request header frontend được phép gửi |
| exposedHeaders | Response header JavaScript được phép đọc |
| allowCredentials | Cho phép browser gửi credentials như cookie |
| maxAge | Thời gian browser cache kết quả preflight |

Trong ví dụ, \`/**\` áp dụng policy cho mọi URL. Nếu Spring Data REST có base path như \`/api\`, có thể giới hạn mapping thành \`/api/**\`. Khi ứng dụng có nhiều security filter chain, cần bảo đảm chain xử lý các REST URL cũng sử dụng cấu hình CORS tương ứng.

### allowedMethods và OPTIONS

Trong preflight, browser gửi method OPTIONS nhưng header \`Access-Control-Request-Method\` chứa method thật, ví dụ PATCH. CORS processor kiểm tra method được yêu cầu đó.

Vì vậy, để cho phép request PATCH, \`allowedMethods\` phải có PATCH. Thêm OPTIONS vào danh sách không thay thế việc cho phép PATCH. Chỉ thêm OPTIONS như một method được phép nếu API còn có nhu cầu xử lý OPTIONS thông thường.

### allowedHeaders và exposedHeaders

Hai cấu hình này có hướng khác nhau:

- \`allowedHeaders\` cho phép browser gửi header trong request, ví dụ Authorization, Content-Type, If-Match.
- \`exposedHeaders\` cho phép JavaScript đọc response header, ví dụ ETag, Location hoặc Link.

Ví dụ, nếu frontend dùng ETag để cập nhật có điều kiện, cần expose ETag để JavaScript đọc được giá trị từ response. Chỉ thêm If-Match vào allowedHeaders chưa đủ cho chiều đọc ETag.

## 5. Bật CORS trong SecurityFilterChain

Khi có bean \`CorsConfigurationSource\`, bật CORS trong cấu hình Spring Security:

~~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsUtils;
import org.springframework.web.cors.CorsConfigurationSource;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            CorsConfigurationSource corsConfigurationSource)
            throws Exception {

        http
            .cors(cors -> cors.configurationSource(
                    corsConfigurationSource
            ))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(CorsUtils::isPreFlightRequest)
                    .permitAll()
                .anyRequest()
                    .authenticated()
            );

        return http.build();
    }
}
~~~~

Dòng \`http.cors(...)\` yêu cầu Spring Security tích hợp CORS filter và dùng policy đã khai báo. CORS filter xử lý preflight trước bước authorization.

Matcher \`CorsUtils::isPreFlightRequest\` cho phép request preflight đi qua authorization rules nếu nó đến được bước đó. Trong luồng cấu hình chuẩn, CORS filter thường xử lý và kết thúc preflight hợp lệ trước khi request đến các filter phía sau. Quy tắc permitAll ở đây làm rõ chủ đích của security policy.

Không nên chỉ viết:

~~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~~

rồi cho rằng CORS đã hoạt động. Quy tắc trên chỉ cho phép một số request OPTIONS qua authorization; nó không tự tạo \`Access-Control-Allow-Origin\`, \`Access-Control-Allow-Methods\` hoặc \`Access-Control-Allow-Headers\`. Browser vẫn có thể từ chối preflight nếu CORS response header không hợp lệ.

Nếu phiên bản Spring Security cũ dùng cấu hình khác, điều chỉnh DSL theo phiên bản. Với Spring Security hiện đại, nên dùng bean \`SecurityFilterChain\` và lambda DSL thay cho ví dụ WebSecurityConfigurerAdapter cũ.

## 6. Spring Data REST và RepositoryRestConfigurer

Spring Data REST có CORS support riêng cho repository resources. Có thể cấu hình ở cấp REST exporter bằng \`RepositoryRestConfigurer\`:

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

        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE"
            )
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "If-Match",
                "If-None-Match"
            )
            .exposedHeaders(
                "ETag",
                "Location",
                "Link"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~~

Cấu hình này áp dụng cho các REST resources do Spring Data REST export. Có thể dùng mapping cụ thể như \`/people/**\` nếu chỉ repository people cần policy này.

Trong ứng dụng có Spring Security, cần nhớ hai điểm:

1. CORS config của Spring Data REST được áp dụng trong lớp xử lý REST/MVC.
2. Security filter chain chạy trước handler mapping. Vì vậy, nếu Spring Security chặn preflight trước khi request tới Spring Data REST, cấu hình RepositoryRestConfigurer một mình có thể chưa đủ.

Hãy cấu hình CORS ở Spring Security bằng \`http.cors(...)\` và \`CorsConfigurationSource\` để preflight được xử lý trước authentication. Nếu đồng thời giữ cấu hình RepositoryRestConfigurer, hãy đặt cùng origin, method, request header, exposed header và credentials policy ở cả hai nơi.

Không để hai cấu hình mâu thuẫn. Nếu security filter cho phép origin rộng hơn cấu hình REST, request có thể được xử lý với policy không như dự định. Nếu cấu hình REST cho phép nhưng security filter từ chối preflight trước đó, browser vẫn không gửi request thật.

Spring MVC \`WebMvcConfigurer.addCorsMappings(...)\` không nên được mặc định xem là cấu hình cho Spring Data REST exporter. Dùng đúng extension point của từng lớp và kiểm tra response thực tế.

## 7. Cấu hình credentials và cookie

Nếu frontend dùng cookie phiên đăng nhập, browser cần gửi credentials trong cross-origin request. Cấu hình server phải cho phép credentials:

~~~~java
configuration.setAllowedOrigins(
        List.of("https://app.example.com")
);
configuration.setAllowCredentials(true);
~~~~

Frontend có thể dùng:

~~~~javascript
fetch("https://api.example.com/people", {
    method: "GET",
    credentials: "include"
});
~~~~

Với cookie authentication, cần kiểm tra thêm:

- Cookie có thuộc domain/path phù hợp không.
- Cookie có thuộc tính Secure khi dùng HTTPS không.
- SameSite có cho phép gửi cookie trong ngữ cảnh cross-site cần thiết không.
- Browser có chặn third-party cookie theo chính sách riêng không.
- CSRF protection có được cấu hình cho request thay đổi dữ liệu không.

Không dùng wildcard origin \`*\` khi cho phép credentials. Khi \`allowCredentials(true)\`, khai báo origin cụ thể hoặc pattern được kiểm soát chặt chẽ.

Nếu frontend chỉ gửi bearer token tường minh trong header Authorization và không dùng cookie hoặc HTTP authentication tự động, thường có thể để allowCredentials false nhưng vẫn phải cho phép Authorization trong allowedHeaders. Header Authorization và cookie credentials là hai vấn đề khác nhau.

Không bật credentials chỉ vì frontend và API khác origin. Chỉ bật khi request thực sự cần cookie hoặc thông tin xác thực browser tương ứng.

## 8. CORS không thay thế authentication, authorization và CSRF

CORS là cơ chế browser kiểm soát việc JavaScript đọc response cross-origin. Nó không phải hàng rào xác thực người dùng.

Ví dụ:

- curl có thể gửi request trực tiếp và không thực thi CORS policy như browser.
- Backend service có thể gọi API nếu network và authentication cho phép.
- Một request có CORS hợp lệ vẫn có thể bị Spring Security trả 401 nếu chưa đăng nhập.
- Người dùng đã đăng nhập vẫn có thể nhận 403 nếu không có quyền trên resource.
- Với cookie authentication, request thay đổi dữ liệu vẫn cần được bảo vệ khỏi CSRF.

Không tắt CSRF chỉ vì đã cấu hình CORS. Chỉ cân nhắc disable CSRF cho API thực sự stateless, xác thực bằng bearer token không được browser tự động gửi và không dựa vào cookie/session ambient credentials. Nếu dùng cookie/session, giữ CSRF protection và cấu hình token flow phù hợp với frontend.

Một policy CORS đúng chỉ trả lời câu hỏi: “Origin này có được phép thực hiện request cross-origin và đọc response trong browser không?”. Authentication và authorization trả lời câu hỏi: “Ai đang gọi và người đó có quyền gì?”.

## 9. Kiểm tra preflight bằng curl

curl không thực thi same-origin policy, nhưng có thể gửi một preflight giả lập để kiểm tra response header.

Ví dụ frontend muốn PATCH JSON và gửi If-Match:

~~~~bash
curl -i -X OPTIONS \
  "https://api.example.com/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type, if-match"
~~~~

Response mong đợi có các header tương tự:

~~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, If-Match, If-None-Match
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~~

Status preflight hợp lệ có thể là 200 hoặc 204 tùy cấu hình. Điều quan trọng là các CORS response header cho phép đúng origin, method và request header browser yêu cầu.

Nếu browser gửi \`Access-Control-Request-Headers: content-type, if-match\`, server phải cho phép cả hai header đó. Tên header không phân biệt hoa thường, nhưng giá trị cần tương ứng với policy.

## 10. Kiểm tra request thật sau preflight

Sau khi preflight thành công, browser gửi request thực tế. Ví dụ:

~~~~bash
curl -i -X PATCH \
  "https://api.example.com/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Content-Type: application/merge-patch+json" \
  -H 'If-Match: "7"' \
  -H "Authorization: Bearer <access-token>" \
  -d '{"firstName":"Alice Smith"}'
~~~~

Request thực tế vẫn phải vượt qua authentication và authorization. Nếu token thiếu hoặc hết hạn, API có thể trả 401. Nếu người dùng không có quyền, API có thể trả 403. Đây là kết quả security bình thường, không có nghĩa CORS preflight đã sai.

Nếu frontend cần đọc ETag hoặc Location trong response, kiểm tra header đó xuất hiện trong \`Access-Control-Expose-Headers\`. Nếu không, browser có thể nhận response nhưng JavaScript không đọc được các header đó.

## 11. Chỉ cho phép preflight, không mở mọi OPTIONS

Một số cấu hình bảo mật dùng:

~~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~~

Cách này cho mọi request OPTIONS qua authorization trên toàn bộ URL. Nếu ứng dụng có OPTIONS endpoint nghiệp vụ hoặc nhiều route, rule này có thể rộng hơn cần thiết.

Ưu tiên nhận diện CORS preflight:

~~~~java
.requestMatchers(CorsUtils::isPreFlightRequest).permitAll()
~~~~

Cách này chỉ nhắm đến request OPTIONS có cấu trúc preflight CORS. Những OPTIONS request thông thường vẫn chịu security rule tương ứng.

Tuy vậy, permitAll không thay thế CorsConfigurationSource. Một preflight từ origin không được phép vẫn phải bị CORS processor từ chối. Không dùng permitAll để mở toàn bộ API cho mọi origin.

## 12. Nhiều SecurityFilterChain và thứ tự filter

Ứng dụng lớn có thể có nhiều \`SecurityFilterChain\`, ví dụ:

- Một chain cho /api/**.
- Một chain cho /actuator/**.
- Một chain cho form login và trang web.
- Một chain riêng cho Spring Data REST base path.

Khi đó cần kiểm tra:

1. Chain nào match URL của repository resource.
2. Chain đó có bật \`http.cors(...)\` không.
3. CorsConfigurationSource có mapping cho URL đó không.
4. CORS filter có đứng trước authentication/authorization filter không.
5. Preflight có bị một chain khác bắt trước không.
6. Tất cả chain liên quan có cùng policy mong muốn không.

Nếu Spring Data REST dùng base path /api, mapping CORS và security matcher cần khớp với /api/**. Không cấu hình CorsConfigurationSource cho /rest/** trong khi repository thực tế nằm ở /api/**.

Khi debug nhiều chain, bật log phù hợp của Spring Security để xác định chain nào đã match và filter nào trả response. Không nên thêm permitAll rộng để che lỗi chọn nhầm chain.

## 13. Kiểm thử bằng MockMvc

Có thể mô phỏng preflight bằng MockMvc:

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

Nếu test setup dùng status 204 cho preflight, điều chỉnh matcher theo response thực tế của cấu hình. Nên kiểm tra thêm:

- Origin được phép nhận Access-Control-Allow-Origin.
- Origin không được phép không nhận header allow-origin.
- PATCH được cho phép khi Access-Control-Request-Method là PATCH.
- Header If-Match được cho phép khi browser yêu cầu.
- ETag được expose khi frontend cần đọc.
- Preflight không cần cookie session.
- Request PATCH thực tế vẫn cần authentication.
- Request thực tế bị từ chối nếu thiếu quyền.
- CSRF vẫn được áp dụng đúng với cookie authentication.

MockMvc test có thể xác nhận filter chain và response header trong ứng dụng. Kiểm thử browser thật vẫn hữu ích để xác nhận cookie, SameSite, credentials mode và hành vi của browser.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| OPTIONS trả 401 | Preflight bị authentication xử lý trước CORS | Bật http.cors() và cung cấp CorsConfigurationSource |
| OPTIONS trả 403 | Origin, method hoặc request header không nằm trong policy; hoặc security chain chặn | Kiểm tra Access-Control-Request-* và CORS policy |
| Preflight thành công nhưng PATCH trả 401 | Request thật thiếu hoặc sai authentication | Kiểm tra token/session của request thật |
| Preflight thành công nhưng PATCH trả 403 | Người dùng không có quyền hoặc CSRF token thiếu | Kiểm tra authorization và CSRF riêng |
| Chỉ cấu hình RepositoryRestConfigurer nhưng OPTIONS vẫn bị chặn | Security filter chain chặn trước REST handler mapping | Cấu hình CORS trong Spring Security |
| Permit OPTIONS nhưng browser vẫn báo CORS | Authorization cho qua nhưng response thiếu CORS headers | Cấu hình CorsConfigurationSource; permitAll không đủ |
| PATCH bị từ chối dù OPTIONS được permitAll | allowedMethods không có PATCH | Thêm PATCH vào allowedMethods |
| If-Match bị từ chối trong preflight | allowedHeaders thiếu If-Match | Thêm If-Match vào allowedHeaders |
| JavaScript không đọc được ETag | ETag chưa nằm trong exposedHeaders | Expose ETag |
| Cookie không được gửi | allowCredentials hoặc cookie attributes chưa đúng | Kiểm tra credentials, SameSite, Secure và domain |
| CORS hoạt động ở một route nhưng không ở route khác | Mapping hoặc SecurityFilterChain không bao phủ URL | Kiểm tra base path, matcher và source mapping |
| OPTIONS endpoint thông thường bị mở rộng quyền | Dùng permitAll cho mọi OPTIONS | Dùng CorsUtils.isPreFlightRequest |
| curl thành công nhưng browser lỗi | curl không thực thi CORS policy | Kiểm tra preflight và browser DevTools |
| Origin wildcard đi cùng credentials | Cấu hình CORS không hợp lệ cho credentials | Dùng origin cụ thể hoặc pattern được kiểm soát |

## 15. Checklist triển khai

Trước khi đưa API vào sử dụng, xác nhận:

- [ ] Xác định chính xác origin của frontend theo scheme, host và port.
- [ ] CorsConfigurationSource bao phủ URL Spring Data REST thực tế.
- [ ] SecurityFilterChain bật http.cors(...).
- [ ] CORS được xử lý trước authentication.
- [ ] Preflight hợp lệ không cần cookie session.
- [ ] allowedMethods có method thật mà frontend muốn gọi.
- [ ] allowedHeaders có các header custom như Authorization, Content-Type, If-Match.
- [ ] exposedHeaders có ETag, Location hoặc Link nếu JavaScript cần đọc.
- [ ] allowCredentials chỉ bật khi cần cookie/credentials.
- [ ] Nếu dùng RepositoryRestConfigurer, policy không mâu thuẫn với policy trong Spring Security.
- [ ] Request thật vẫn cần authentication và authorization.
- [ ] CSRF được cấu hình theo mô hình xác thực, không bị tắt chỉ vì CORS.
- [ ] Đã kiểm thử origin hợp lệ, origin không hợp lệ, preflight và request thật.
- [ ] Nếu có nhiều SecurityFilterChain, chain dành cho REST API cũng được cấu hình CORS.

## 16. Kết luận

Khi Spring Data REST chạy cùng Spring Security, CORS phải được xử lý trước authentication để browser preflight OPTIONS không bị từ chối chỉ vì request chưa mang cookie phiên đăng nhập. Cấu hình \`CorsConfigurationSource\` mô tả origin, method, request header, exposed response header và credentials; \`http.cors(...)\` bật tích hợp CORS trong SecurityFilterChain.

Preflight hợp lệ chỉ cho phép browser gửi request thật. Request thật vẫn phải vượt qua authentication, authorization và CSRF policy phù hợp. Với Spring Data REST, RepositoryRestConfigurer có thể cấu hình CORS cho REST exporter; nếu đồng thời dùng Spring Security CORS filter, hãy giữ hai policy nhất quán và bảo đảm security filter chain bao phủ đúng URL. Chỉ permit CORS preflight bằng matcher phù hợp; cho phép mọi OPTIONS không tự tạo CORS headers. Hãy kiểm tra riêng preflight, request thật và response header trong browser.

## Tài liệu tham khảo

- [Spring Security Reference — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — CORS configuration API](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Framework Reference — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
