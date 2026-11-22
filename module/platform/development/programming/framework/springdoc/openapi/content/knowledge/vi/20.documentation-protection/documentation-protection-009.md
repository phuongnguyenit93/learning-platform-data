# CORS chỉ tác động truy cập từ trình duyệt, không thay quyền truy cập máy chủ

CORS (Cross-Origin Resource Sharing) là cơ chế để server công bố những origin nào được phép đọc response của một request cross-origin từ trình duyệt. Khi Swagger UI được phục vụ ở một origin và API hoặc tài liệu OpenAPI ở origin khác, trình duyệt áp dụng Same-Origin Policy và kiểm tra các CORS header do server trả về.

CORS không xác thực người gọi, không kiểm tra vai trò hoặc scope, không bảo vệ endpoint khỏi <code>curl</code>, Postman hay một service backend khác. Nó là chính sách mà trình duyệt thực thi để kiểm soát JavaScript có được gửi một số request cross-origin và đọc response hay không. Quyền truy cập tài nguyên vẫn phải được kiểm soát ở server bằng authentication, authorization và các lớp bảo vệ phù hợp.

## 1. Origin là gì?

Một origin được xác định bởi ba thành phần:

- Scheme, ví dụ <code>http</code> hoặc <code>https</code>.
- Host, ví dụ <code>docs.example.com</code>.
- Port, ví dụ <code>443</code> hoặc <code>8080</code>.

Chỉ cần một trong ba thành phần khác nhau thì origin đã khác:

| Trang Swagger UI | API | Kết quả |
|---|---|---|
| <code>https://docs.example.com</code> | <code>https://docs.example.com/api/orders</code> | Cùng origin |
| <code>https://docs.example.com</code> | <code>https://api.example.com</code> | Khác host, cross-origin |
| <code>https://docs.example.com</code> | <code>http://docs.example.com</code> | Khác scheme, cross-origin |
| <code>http://localhost:3000</code> | <code>http://localhost:8080</code> | Khác port, cross-origin |

Đường dẫn <code>/swagger-ui</code> và <code>/api</code> không tham gia vào phép so sánh origin. Hai URL có thể khác path nhưng vẫn cùng origin nếu scheme, host và port giống nhau.

Ví dụ, nếu Swagger UI mở tại <code>https://docs.example.com/swagger-ui/index.html</code> và gọi <code>https://api.example.com/orders</code>, trình duyệt xem đây là request cross-origin. API phải trả các CORS header phù hợp để JavaScript trên trang tài liệu được phép đọc response.

## 2. CORS kiểm soát điều gì?

Same-Origin Policy giới hạn cách một trang web đọc tài nguyên từ origin khác. CORS cho phép server nới giới hạn đó có chọn lọc bằng response header.

Với một request cross-origin, trình duyệt kiểm tra origin của trang gọi và các quy tắc CORS từ server đích. Tùy loại request, trình duyệt có thể:

- Gửi request trực tiếp rồi chỉ cho JavaScript đọc response nếu CORS hợp lệ.
- Gửi một request preflight <code>OPTIONS</code> trước để hỏi server có cho phép method và header dự kiến không.
- Chặn JavaScript đọc response nếu response thiếu hoặc sai CORS header.
- Không gửi request thực tế nếu preflight không được chấp nhận.

Điểm quan trọng: CORS không phải một lớp phân quyền của API. Với một số request đơn giản, trình duyệt vẫn có thể gửi request đến server nhưng không cho JavaScript đọc response. Vì vậy server vẫn phải kiểm tra quyền và xử lý request an toàn.

## 3. Phân biệt CORS, authentication và authorization

Ba cơ chế giải quyết ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi | Ví dụ |
|---|---|---|
| CORS | JavaScript từ origin nào được phép gửi/đọc request cross-origin theo chính sách trình duyệt? | Cho phép <code>https://docs.example.com</code> đọc response API |
| Authentication | Người gọi là ai? Credential có hợp lệ không? | Xác minh JWT Bearer token |
| Authorization | Người gọi được phép thực hiện hành động nào trên tài nguyên nào? | Chỉ người có <code>orders:read</code> được đọc đơn hàng |

Một request có thể vượt qua CORS nhưng vẫn bị từ chối bởi authentication hoặc authorization:

- Browser gửi request từ origin được cho phép, nhưng không có token: server trả <code>401 Unauthorized</code>.
- Token hợp lệ nhưng thiếu quyền: server trả <code>403 Forbidden</code>.
- Token hợp lệ và đủ quyền: server có thể trả <code>200 OK</code>.

Ngược lại, server có thể xử lý request và trả status, nhưng browser không cho JavaScript đọc response vì CORS header không phù hợp. Khi đó giao diện có thể chỉ báo lỗi CORS dù server đã ghi nhận request. Hãy kiểm tra tab Network và log backend để biết request có đến server hay không.

## 4. CORS không bảo vệ API khỏi client ngoài trình duyệt

Các công cụ như <code>curl</code>, Postman, ứng dụng di động native và service backend không bị trình duyệt áp dụng Same-Origin Policy. Chúng có thể gửi request trực tiếp đến API nếu mạng cho phép.

Ví dụ, lệnh sau vẫn có thể gọi API dù origin không nằm trong danh sách CORS:

~~~bash
curl -i \
  -H "Origin: https://untrusted.example" \
  https://api.example.com/api/orders
~~~

<code>curl</code> sẽ hiển thị response server trả về. Nó không tự từ chối response chỉ vì <code>Access-Control-Allow-Origin</code> không khớp. Header <code>Origin</code> trong lệnh cũng do client tự đặt được, nên server không được xem nó như credential xác thực.

Do đó, không được dùng CORS như biện pháp bảo vệ dữ liệu. Endpoint nhạy cảm cần authentication và authorization ở server; nếu cần giới hạn truy cập ở tầng mạng, dùng firewall, gateway, private network hoặc cơ chế kiểm soát phù hợp.

## 5. Preflight request và actual request

Trình duyệt gửi preflight khi request cross-origin không thuộc nhóm request đơn giản. Ví dụ thường gặp là request JSON có header <code>Authorization</code>, hoặc request dùng method <code>PUT</code>, <code>PATCH</code> hay <code>DELETE</code>.

Preflight là request <code>OPTIONS</code> có các header như:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://docs.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

Server cần trả các header cho biết origin, method và header nào được phép. Ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://docs.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Nếu preflight thành công, trình duyệt mới gửi actual request theo method và header đã khai báo. Response thực tế cũng cần CORS header phù hợp để JavaScript đọc được.

Không phải request cross-origin nào cũng có preflight. Một request đơn giản có thể được gửi trực tiếp. Vì thế, việc chỉ kiểm tra preflight chưa đủ; hãy kiểm tra cả response của actual request.

## 6. Những CORS header quan trọng

| Header | Do ai gửi? | Ý nghĩa |
|---|---|---|
| <code>Origin</code> | Browser | Origin của trang khởi tạo request |
| <code>Access-Control-Request-Method</code> | Browser trong preflight | Method mà actual request muốn sử dụng |
| <code>Access-Control-Request-Headers</code> | Browser trong preflight | Danh sách header mà actual request muốn gửi |
| <code>Access-Control-Allow-Origin</code> | Server | Origin được phép truy cập response |
| <code>Access-Control-Allow-Methods</code> | Server | Các method được phép cho request cross-origin |
| <code>Access-Control-Allow-Headers</code> | Server | Các request header được phép |
| <code>Access-Control-Allow-Credentials</code> | Server | Cho phép browser dùng credential trong CORS request |
| <code>Access-Control-Expose-Headers</code> | Server | Các response header bổ sung mà JavaScript được phép đọc |
| <code>Access-Control-Max-Age</code> | Server | Thời gian browser có thể cache kết quả preflight |
| <code>Vary: Origin</code> | Server | Báo cache rằng response có thể thay đổi theo Origin |

<code>Access-Control-Allow-Origin</code> thường là một origin cụ thể hoặc <code>*</code> trong trường hợp không dùng credential. Khi server chọn origin động từ allowlist, <code>Vary: Origin</code> giúp cache không dùng nhầm response CORS giữa các origin.

<code>Access-Control-Expose-Headers</code> cần thiết nếu JavaScript phải đọc header không nằm trong danh sách response header được expose mặc định. Ví dụ, nếu UI hoặc frontend cần đọc <code>X-Request-Id</code> hay <code>Location</code>, server có thể expose các header đó.

## 7. Cấu hình CORS cho Spring Security

Khi ứng dụng dùng Spring Security, nên cấu hình CORS trong filter chain để CORS được xử lý trước các bước xác thực. Preflight thường không mang cookie hoặc Bearer token như actual request; nếu authentication filter chặn <code>OPTIONS</code> trước khi CORS xử lý, trình duyệt sẽ báo lỗi.

Ví dụ với Spring Boot 3 và Spring Security 6:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://docs.example.com"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id")
        );
        cors.setExposedHeaders(List.of("Location", "X-Request-Id"));
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong ví dụ:

- Chỉ origin <code>https://docs.example.com</code> được phép gọi API cross-origin.
- Chỉ các method được liệt kê được phép.
- Header <code>Authorization</code>, <code>Content-Type</code> và <code>X-Request-Id</code> được cho phép trong request.
- JavaScript được phép đọc <code>Location</code> và <code>X-Request-Id</code> trong response.
- Cấu hình chỉ áp dụng cho đường dẫn <code>/api/**</code>.

Đây là cấu hình minh họa cho Bearer token được JavaScript chủ động gửi qua header <code>Authorization</code>. Header này được cho phép bằng <code>setAllowedHeaders</code>; riêng nó không đòi hỏi <code>allowCredentials(true)</code>. Thay origin, method, header và path bằng giá trị của hệ thống.

Chỉ bật <code>setAllowCredentials(true)</code> nếu browser cần gửi credential theo chế độ credentials, chẳng hạn cookie session hoặc HTTP authentication được browser quản lý. Khi bật, không dùng <code>allowedOrigins("*")</code>; hãy khai báo origin cụ thể hoặc dùng allowlist được kiểm soát. Không phản chiếu tùy tiện mọi giá trị <code>Origin</code> nhận được từ request.

Nếu dùng JWT resource server như trong ví dụ filter chain, ứng dụng cần dependency <code>spring-boot-starter-oauth2-resource-server</code> và cấu hình issuer hoặc JWT decoder phù hợp. Phần CORS không thay thế cấu hình đó.

## 8. CORS bằng WebMvcConfigurer khi không cấu hình qua Spring Security

Ứng dụng Spring MVC không dùng Spring Security có thể khai báo CORS qua <code>WebMvcConfigurer</code>:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Authorization", "Content-Type", "X-Request-Id")
            .exposedHeaders("Location", "X-Request-Id")
            .maxAge(3600);
    }
}
~~~

Chọn một nơi cấu hình có chủ đích để tránh các policy chồng lấn hoặc mâu thuẫn. Nếu Spring Security hiện diện, cấu hình CORS phải được tích hợp với filter chain, ví dụ bằng <code>CorsConfigurationSource</code> và <code>.cors(withDefaults())</code>, hoặc bảo đảm Spring Security sử dụng cấu hình MVC phù hợp.

Không thêm một CORS filter tùy chỉnh thứ hai nếu chưa hiểu thứ tự filter và cách merge policy. Hai lớp cùng sửa CORS header có thể tạo response lặp <code>Access-Control-Allow-Origin</code> hoặc hành vi khó dự đoán.

## 9. CORS cho Swagger UI và tài liệu OpenAPI

Có thể có hai request cross-origin riêng:

1. Swagger UI tải file đặc tả OpenAPI từ <code>/v3/api-docs</code> hoặc URL tài liệu được cấu hình.
2. Swagger UI gửi request thử nghiệm đến endpoint API như <code>/api/orders</code>.

Nếu UI và tài liệu OpenAPI ở hai origin khác nhau, endpoint cung cấp tài liệu cũng cần CORS phù hợp để trình duyệt tải được spec. Nếu UI và API ở hai origin khác nhau, API cần CORS phù hợp cho các request Try it out.

Trong ví dụ <code>CorsConfigurationSource</code> ở trên, mapping chỉ áp dụng cho <code>/api/**</code>. Nếu tài liệu JSON được phục vụ cross-origin, hãy đăng ký thêm policy cho các đường dẫn tài liệu tương ứng, ví dụ <code>/v3/api-docs</code>, <code>/v3/api-docs/**</code> và <code>/v3/api-docs.yaml</code>. Có thể giới hạn nhóm tài liệu ở method <code>GET</code> và chỉ các request header thực sự cần thiết.

Ví dụ:

- Swagger UI: <code>https://docs.example.com</code>
- OpenAPI JSON: <code>https://api.example.com/v3/api-docs</code>
- API: <code>https://api.example.com/api/**</code>

Trong trường hợp này, hãy xác định policy cho cả <code>/v3/api-docs/**</code> và <code>/api/**</code>. Có thể dùng chung allowlist origin nhưng vẫn nên áp dụng method/header tối thiểu cho từng nhóm đường dẫn.

Nếu Swagger UI và API được phục vụ cùng origin qua reverse proxy, browser không cần CORS cho các request đó. Khi thay đổi domain hoặc tách host tài liệu, cần rà soát lại policy.

## 10. CORS không thay thế việc bảo vệ Swagger UI và OpenAPI JSON

Một trang Swagger UI có thể không cho browser của origin lạ đọc tài liệu, nhưng endpoint <code>/v3/api-docs</code> vẫn có thể truy cập trực tiếp bằng <code>curl</code> hoặc một client khác. CORS không biến tài liệu thành riêng tư.

Nếu tài liệu API chỉ dành cho nhân viên hoặc đối tác, hãy bảo vệ độc lập:

- Trang Swagger UI, thường gồm <code>/swagger-ui/**</code> và điểm vào <code>/swagger-ui.html</code> hoặc path tùy chỉnh.
- Tài liệu JSON <code>/v3/api-docs/**</code>.
- Tài liệu YAML <code>/v3/api-docs.yaml</code> hoặc path tùy chỉnh.
- Các endpoint tài liệu nhóm nếu ứng dụng dùng <code>GroupedOpenApi</code>.

Dùng Spring Security, reverse proxy, gateway hoặc cơ chế identity của tổ chức để yêu cầu đăng nhập và quyền phù hợp. CORS có thể được cấu hình bổ sung để giới hạn origin của browser, nhưng không phải lớp kiểm soát truy cập chính.

Tương tự, bảo vệ trang Swagger UI không tự bảo vệ các endpoint API. API nghiệp vụ cần rule xác thực và phân quyền riêng.

## 11. CORS, cookie và CSRF

CORS và CSRF có liên quan trong một số kiến trúc trình duyệt nhưng không thay thế nhau.

- CORS điều khiển việc browser cho phép JavaScript cross-origin đọc response và, với request cần preflight, có thể ngăn actual request được gửi.
- CSRF là kiểu tấn công lợi dụng việc browser tự động gửi credential (thường là cookie session) để khiến người dùng đã đăng nhập thực hiện hành động ngoài ý muốn.

Một số request đơn giản có thể được gửi cross-origin mà không cần preflight. Vì vậy, chỉ dựa vào CORS để chống CSRF là không đủ, đặc biệt với API dùng cookie tự động gửi theo request.

Nếu ứng dụng xác thực bằng session cookie:

- Bật CSRF protection phù hợp với kiểu client và cách gửi token CSRF.
- Đặt cookie <code>SameSite</code>, <code>Secure</code> và <code>HttpOnly</code> theo kiến trúc.
- Chỉ bật CORS credentials cho origin tin cậy.
- Kiểm tra <code>Access-Control-Allow-Credentials</code> và origin cụ thể.

Ví dụ, một frontend cần gửi cookie session trong request cross-origin phải chủ động bật credentials ở client:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Server khi đó cần cấu hình origin cụ thể và <code>allowCredentials(true)</code>. Browser vẫn tự áp dụng chính sách cookie như <code>SameSite</code>; CORS không thể buộc browser gửi cookie mà cookie policy không cho phép.

Nếu ứng dụng dùng Bearer token do JavaScript chủ động thêm vào header Authorization, request thường cần preflight. Tuy nhiên, server vẫn phải xác thực token và kiểm tra quyền; không coi việc request có header Authorization là bằng chứng hợp lệ.

## 12. Cách kiểm tra lỗi CORS

Khi Swagger UI báo lỗi CORS, hãy kiểm tra theo thứ tự:

1. Xác định origin chính xác của trang Swagger UI trong thanh địa chỉ.
2. Xem Request URL và origin của API hoặc endpoint OpenAPI trong tab Network.
3. Nếu có preflight, kiểm tra request <code>OPTIONS</code>, status và các header <code>Access-Control-Request-*</code>.
4. Kiểm tra response preflight có <code>Access-Control-Allow-Origin</code>, <code>Access-Control-Allow-Methods</code> và <code>Access-Control-Allow-Headers</code> phù hợp không.
5. Kiểm tra response của actual request có <code>Access-Control-Allow-Origin</code> và các header cần expose không.
6. Nếu dùng cookie/credential, kiểm tra <code>Access-Control-Allow-Credentials</code> và origin không phải wildcard.
7. Kiểm tra log backend và gateway để xác định request có đến server hay chưa.
8. Sau khi CORS hợp lệ, kiểm tra tiếp status HTTP, token và quyền truy cập.

Một preflight có thể thất bại vì gateway chặn <code>OPTIONS</code>, Spring Security xử lý request trước CORS, method/header chưa được allow hoặc origin không nằm trong allowlist. Sửa đúng policy ở server thay vì tắt bảo vệ trình duyệt.

### 12.1. Dùng curl để xem CORS header

Có thể kiểm tra server trả header gì bằng lệnh:

~~~bash
curl -i \
  -H "Origin: https://docs.example.com" \
  https://api.example.com/api/orders
~~~

Để mô phỏng preflight:

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://docs.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  https://api.example.com/api/orders
~~~

Các lệnh này giúp kiểm tra response header phía server. Chúng không mô phỏng đầy đủ việc browser thực thi CORS và không chứng minh JavaScript sẽ được phép đọc response. Luôn xác nhận lại trong browser Network/Console.

## 13. Lỗi thường gặp

**Cho rằng CORS là authentication.** CORS chỉ là chính sách browser. API vẫn phải xác minh token, session hoặc credential ở server.

**Cho rằng CORS chặn curl và Postman.** Các công cụ này không thực thi Same-Origin Policy. Request vẫn có thể đến API.

**Chỉ cấu hình CORS cho API mà quên <code>/v3/api-docs</code>.** Swagger UI có thể không tải được đặc tả nếu spec ở origin khác.

**Chỉ cấu hình preflight mà quên actual response.** Browser cần CORS header phù hợp trên response thực tế để JavaScript đọc được.

**Dùng wildcard origin với credentials.** Khi cho phép credentials, cần origin cụ thể; không dùng <code>Access-Control-Allow-Origin: *</code>.

**Chặn OPTIONS bằng authentication trước khi CORS xử lý.** Tích hợp CORS vào Spring Security để preflight được xử lý đúng thứ tự.

**Mở mọi origin để sửa lỗi nhanh.** Chỉ thêm origin tin cậy, method và header cần thiết.

**Dùng CORS thay CSRF protection.** Request đơn giản vẫn có thể được gửi cross-origin; cookie authentication cần chính sách CSRF phù hợp.

**Nhầm lỗi CORS với 401/403.** CORS là lỗi browser policy; 401/403 là response HTTP liên quan xác thực/phân quyền. Kiểm tra Network và log server để phân biệt.

## 14. Danh sách rà soát trước khi công bố tài liệu

- [ ] Đã xác định origin của Swagger UI, OpenAPI JSON/YAML và API.
- [ ] Chỉ cho phép các origin tài liệu tin cậy.
- [ ] Chỉ cho phép method và request header cần thiết.
- [ ] Đã cấu hình CORS cho endpoint tài liệu nếu spec khác origin với UI.
- [ ] Đã cấu hình CORS cho API nếu Try it out gọi cross-origin.
- [ ] Preflight <code>OPTIONS</code> được xử lý trước authentication filter phù hợp.
- [ ] Actual response có CORS header để browser đọc được.
- [ ] <code>allowCredentials</code> chỉ bật khi cần và không kết hợp wildcard origin.
- [ ] Bearer token trong header <code>Authorization</code> được allow rõ ràng; không bật credentials chỉ vì có Bearer token.
- [ ] Authentication và authorization vẫn được thực thi tại server.
- [ ] Swagger UI, <code>/v3/api-docs</code> và các endpoint tài liệu được bảo vệ độc lập nếu cần riêng tư.
- [ ] CSRF được xử lý riêng khi dùng cookie/session authentication.
- [ ] Đã kiểm tra bằng browser Network và xác nhận response header thực tế.

## Tài liệu tham khảo

- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): cách trình duyệt thực thi CORS và preflight.
- [Fetch Standard – CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): thuật toán CORS của trình duyệt.
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cấu hình CORS trong Spring MVC.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): tích hợp CORS với Security filter chain.
- [Spring Boot – Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): cấu hình bảo mật ứng dụng Spring Boot.
- [OWASP – Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): vì sao CORS không thay thế biện pháp chống CSRF.
- [springdoc-openapi](https://springdoc.org/): cấu hình endpoint OpenAPI và Swagger UI trong Spring Boot.
