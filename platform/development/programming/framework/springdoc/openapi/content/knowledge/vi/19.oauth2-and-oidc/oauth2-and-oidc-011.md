# CORS, redirect URI và nguyên nhân đăng nhập thành công nhưng gọi API thất bại

Một ứng dụng web có thể đăng nhập người dùng thành công qua OAuth2 hoặc OpenID Connect, quay lại trang frontend bình thường, nhưng request tiếp theo tới API lại thất bại. Tình huống này thường khiến nhóm phát triển nghĩ rằng cấu hình OAuth2 sai. Thực tế, luồng đăng nhập và luồng gọi API gồm nhiều request khác nhau, chịu sự chi phối của các cơ chế khác nhau: **redirect URI**, **CORS**, quản lý token, xác thực ở Resource Server và phân quyền.

Điểm cần làm rõ là request nào đã thành công và request nào thất bại. Redirect từ Identity Provider về ứng dụng không chứng minh trình duyệt đã đổi được authorization code thành token; có token cũng không chứng minh token đó dành cho API đang gọi; và API nhận được token vẫn có thể từ chối vì sai audience hoặc thiếu scope.

Bài này theo dõi toàn bộ đường đi từ trình duyệt tới Identity Provider và Resource Server, giải thích vai trò của redirect URI và CORS, cấu hình CORS trong Spring Security, rồi đưa ra quy trình điều tra lỗi bằng Network tab, curl và MockMvc.

## 1. Phân biệt redirect URI với CORS

Hai khái niệm này thường xuất hiện cùng lúc nhưng giải quyết hai vấn đề khác nhau.

**Redirect URI** là địa chỉ mà Authorization Server chuyển trình duyệt về sau khi người dùng hoàn tất bước xác thực và cấp quyền. URI này phải khớp với URI đã đăng ký cho OAuth2 client theo quy tắc của nhà cung cấp.

**CORS (Cross-Origin Resource Sharing)** là cơ chế mà trình duyệt dùng để quyết định JavaScript của một origin có được phép đọc phản hồi từ origin khác hay không. Server trả các HTTP response header CORS để cho phép hoặc từ chối việc chia sẻ phản hồi.

| Thành phần | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Redirect URI | Sau đăng nhập, trình duyệt quay về đâu? | **https://app.example.com/login/oauth2/code/my-client** |
| CORS | JavaScript từ origin frontend có được đọc phản hồi API không? | Cho phép **https://app.example.com** gọi **https://api.example.com** |
| Authentication | Token hoặc session có hợp lệ không? | JWT signature, issuer, expiration hoặc session |
| Authorization | Danh tính đã xác thực có quyền gọi operation không? | Scope **orders.read** hoặc role **ADMIN** |

Một redirect URI đúng không tự cấu hình CORS. CORS hợp lệ cũng không sửa được redirect URI sai. Hai cấu hình phải được kiểm tra độc lập.

## 2. Origin là gì và khi nào trình duyệt áp dụng CORS?

Một origin được xác định bởi bộ ba:

- Scheme, chẳng hạn **https**.
- Host, chẳng hạn **app.example.com**.
- Port, chẳng hạn **443** hoặc **8080**.

Hai URL có cùng origin khi cả ba thành phần này giống nhau. Ví dụ:

| Frontend | API | Có khác origin? |
|---|---|---|
| https://app.example.com | https://app.example.com/api | Không |
| https://app.example.com | https://api.example.com | Có, khác host |
| http://localhost:3000 | http://localhost:8080 | Có, khác port |
| https://app.example.com | http://api.example.com | Có, khác scheme |

Khi JavaScript dùng fetch hoặc XMLHttpRequest để gọi một origin khác, trình duyệt áp dụng CORS. Nếu server không trả các header phù hợp, trình duyệt chặn JavaScript đọc phản hồi. Request có thể đã tới server và server thậm chí đã xử lý xong, nhưng frontend vẫn báo lỗi CORS vì phản hồi không được phép chia sẻ.

CORS là chính sách của trình duyệt. Công cụ như curl, Postman hoặc một backend gọi backend không tự áp dụng chính sách CORS như trình duyệt. Vì vậy, curl thành công không chứng minh trình duyệt sẽ cho JavaScript đọc phản hồi.

## 3. Các request trong một luồng OAuth2/OIDC trên trình duyệt

Với Authorization Code Flow và PKCE, luồng thường có các bước:

~~~mermaid
sequenceDiagram
    participant B as Browser / Frontend
    participant I as Identity Provider
    participant A as Application / BFF
    participant R as Resource Server API

    B->>I: Điều hướng tới authorization endpoint
    I->>B: Đăng nhập và consent
    I->>A: Redirect về redirect_uri kèm authorization code
    A->>I: Đổi code lấy token (server-to-server nếu BFF)
    I->>A: Access token / ID token
    A->>B: Tạo session hoặc trả kết quả đăng nhập
    B->>R: Gọi API với access token hoặc session cookie
    R->>B: API response và CORS headers
~~~

Trong ứng dụng SPA thuần, frontend có thể tự đổi authorization code lấy token bằng PKCE. Khi đó trình duyệt gửi request tới token endpoint của Identity Provider; token endpoint phải cho phép origin frontend theo chính sách CORS của nhà cung cấp.

Trong mô hình BFF (Backend for Frontend), backend ứng dụng nhận callback, đổi code lấy token ở phía server và giữ token ở server. Trình duyệt thường chỉ nhận session cookie của BFF. Việc backend gọi token endpoint hoặc API server-to-server không bị CORS của trình duyệt chi phối.

Authorization redirect thường là điều hướng trang ở cấp trình duyệt, không phải lệnh fetch/XHR mà JavaScript dùng để đọc dữ liệu cross-origin. Vì vậy, CORS thường không phải nguyên nhân khiến thao tác điều hướng tới trang đăng nhập bị chặn; hãy kiểm tra redirect URI và callback trước. CORS có thể xuất hiện ở bước SPA gọi token endpoint hoặc gọi API bằng fetch/XHR.

Các bước cần phân biệt:

1. Điều hướng top-level tới authorization endpoint.
2. Identity Provider redirect về redirect URI.
3. Đổi authorization code thành token.
4. Frontend hoặc BFF gọi Resource Server API.
5. Resource Server xác minh token và áp dụng quyền.

Đăng nhập thành công ở bước 2 không bảo đảm bước 3 hoặc bước 4 đã thành công.

## 4. Redirect URI phải khớp chính xác

Với Spring Security OAuth2 Client, redirect URI mặc định thường có dạng:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ cấu hình client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          my-client:
            provider: my-provider
            client-id: example-client
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          my-provider:
            issuer-uri: https://id.example.com
~~~

Đăng ký redirect URI tương ứng ở Identity Provider, ví dụ:

~~~text
https://app.example.com/login/oauth2/code/my-client
~~~

Giá trị phải phù hợp với URI mà ứng dụng thực sự gửi trong authorization request. Nhà cung cấp thường so khớp scheme, host, port, path và có thể cả dấu gạch chéo cuối. Không dựa vào việc hai URL trông gần giống nhau.

### Các lỗi redirect URI thường gặp

- Đăng ký **http** nhưng môi trường thực tế dùng **https**.
- Sai host hoặc port sau khi triển khai.
- Thiếu context path hoặc reverse proxy prefix.
- Sai registrationId trong callback path.
- Một bên có dấu gạch chéo cuối, bên kia không có.
- Ứng dụng tạo redirect URI nội bộ như **http://localhost:8080** trong khi người dùng truy cập qua domain HTTPS công khai.

Nếu Identity Provider trả lỗi redirect_uri_mismatch, hãy so sánh giá trị redirect_uri thực tế trong authorization request với danh sách URI đã đăng ký. Không sửa CORS để xử lý lỗi mismatch.

## 5. Reverse proxy có thể làm sai redirect URI

Ứng dụng thường chạy phía sau Nginx, ingress hoặc load balancer. Browser truy cập HTTPS, nhưng proxy chuyển tiếp tới Spring Boot bằng HTTP nội bộ. Nếu ứng dụng không nhận đúng forwarded headers, Spring có thể tạo base URL theo kết nối nội bộ và gửi redirect URI sai.

Ví dụ:

~~~text
Browser -> https://app.example.com
Proxy   -> http://spring-app:8080
~~~

Nếu ứng dụng tạo callback thành **http://spring-app:8080/login/oauth2/code/my-client**, URI đó sẽ không khớp với URI công khai đã đăng ký.

Spring Boot có thể được cấu hình để xử lý forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Proxy cần chuyển tiếp thông tin scheme, host và port bên ngoài, thường qua các header **Forwarded** hoặc **X-Forwarded-***. Chỉ tin các forwarded headers từ reverse proxy đáng tin cậy; không để client bên ngoài tự giả mạo chúng.

Sau khi cấu hình, kiểm tra redirect_uri được gửi trong authorization request. Đừng chỉ kiểm tra giá trị property vì proxy và context path có thể làm thay đổi URL cuối cùng.

## 6. CORS preflight: vì sao API không thấy request GET/POST?

Trước một số cross-origin request, trình duyệt gửi một request kiểm tra gọi là **preflight** bằng HTTP OPTIONS. Preflight hỏi server liệu origin, method và request headers sắp dùng có được phép hay không.

Ví dụ frontend gửi:

~~~http
GET /api/orders
Origin: https://app.example.com
Authorization: Bearer <access-token>
~~~

Vì **Authorization** không phải CORS-safelisted request header, trình duyệt thường gửi preflight:

~~~http
OPTIONS /api/orders
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Server cần trả lời bằng các header phù hợp, ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin
~~~

Sau khi preflight được chấp nhận, trình duyệt mới gửi request GET thật. Nếu OPTIONS bị Spring Security trả 401/403 hoặc không có header CORS phù hợp, request GET có thể không bao giờ được gửi.

Một request dùng **Content-Type: application/json** cũng thường cần preflight vì application/json không thuộc nhóm CORS-safelisted content type. Các custom header như **X-Request-Id** cũng cần được cho phép.

## 7. Các CORS response header quan trọng

| Header | Vai trò |
|---|---|
| **Access-Control-Allow-Origin** | Origin được phép đọc phản hồi |
| **Access-Control-Allow-Methods** | Các HTTP method được phép |
| **Access-Control-Allow-Headers** | Các request header mà client được phép gửi |
| **Access-Control-Allow-Credentials** | Cho phép trình duyệt chia sẻ phản hồi của request có credentials |
| **Access-Control-Expose-Headers** | Cho phép JavaScript đọc thêm response header |
| **Access-Control-Max-Age** | Thời gian trình duyệt có thể cache kết quả preflight |
| **Vary: Origin** | Báo cho cache rằng phản hồi có thể thay đổi theo Origin |

Nếu frontend gửi bearer token trong Authorization, header này phải nằm trong Access-Control-Allow-Headers. Nếu API trả header như Location, ETag hoặc X-Request-Id mà JavaScript cần đọc, hãy khai báo chúng trong Access-Control-Expose-Headers.

Không nhầm Access-Control-Allow-Headers với Access-Control-Expose-Headers: một bên cho phép client gửi request header, bên kia cho phép JavaScript đọc response header.

### Không dùng wildcard với credentials

Khi request dùng cookie hoặc browser credentials, server phải trả origin cụ thể, ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không thể dùng Access-Control-Allow-Origin với giá trị wildcard (*) cùng Access-Control-Allow-Credentials: true. Trình duyệt sẽ từ chối chia sẻ phản hồi theo quy tắc CORS.

Với bearer token được frontend tự đặt trong Authorization header và không dùng cookie/session credentials, có thể cấu hình CORS không cho credentials nhưng vẫn phải cho phép header Authorization. Chỉ bật credentials khi ứng dụng thật sự cần gửi cookie hoặc browser-managed credentials.

## 8. Cấu hình CORS trong Spring Security

Với Spring Security, nên để CORS được xử lý trước bước xác thực. Preflight OPTIONS thường không mang access token; nếu authentication filter chặn OPTIONS trước khi CORS xử lý, trình duyệt sẽ nhận 401 hoặc 403 và không gửi request thật.

Ví dụ cấu hình CORS tập trung cho API:

~~~java
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
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(
            List.of("https://app.example.com")
        );
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
        );
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id")
        );
        config.setExposedHeaders(
            List.of("Location", "X-Request-Id")
        );
        config.setAllowCredentials(false);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Trong ví dụ, ứng dụng chỉ cho phép frontend có origin **https://app.example.com** gọi API dưới **/api/**. Cấu hình không cho credentials vì ví dụ dùng bearer token do frontend chủ động gắn vào Authorization header, không dùng cookie session cross-origin.

Kết nối cấu hình này với Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                Customizer.withDefaults()
            ))
            .build();
    }
}
~~~

Khi có bean CorsConfigurationSource, Spring Security có thể dùng nó cho cấu hình CORS. Đặt **.cors(Customizer.withDefaults())** trong SecurityFilterChain để tích hợp CORS vào security filter chain. Không tạo một cấu hình CORS thứ hai với origin hoặc header khác nhau mà không có chủ đích.

## 9. Cho phép cookie/session credentials

Nếu frontend dùng cookie session cross-origin, cấu hình phải cho phép credentials và dùng origin cụ thể:

~~~java
config.setAllowedOrigins(
    List.of("https://app.example.com")
);
config.setAllowCredentials(true);
~~~

Frontend cần gửi request với credentials:

~~~javascript
fetch("https://api.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Cookie còn phải phù hợp với thuộc tính Domain, Path, Secure và SameSite. Với cookie cross-site, trình duyệt thường yêu cầu **SameSite=None; Secure**; chính sách chặn third-party cookies của trình duyệt vẫn có thể ảnh hưởng. CORS không tự làm cookie được gửi nếu thuộc tính cookie hoặc chính sách trình duyệt không cho phép.

Nếu chỉ dùng bearer header, đừng bật allowCredentials một cách mặc định. Chỉ mở quyền credentials khi thực sự có cookie hoặc browser credentials cần gửi qua origin khác.

## 10. Cấu hình CORS bằng Spring MVC

Nếu ứng dụng không dùng Spring Security, hoặc muốn khai báo CORS ở tầng MVC, có thể dùng WebMvcConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Authorization", "Content-Type", "X-Request-Id"
            )
            .exposedHeaders("Location", "X-Request-Id")
            .allowCredentials(false)
            .maxAge(3600);
    }
}
~~~

Khi có Spring Security, CORS cần được tích hợp đúng thứ tự trong security filter chain. Có thể dùng CorsConfigurationSource như ví dụ trước hoặc một cấu hình CORS được Spring Security nhận biết. Tránh để MVC và Security trả các header CORS mâu thuẫn.

**@CrossOrigin** phù hợp cho cấu hình ở controller hoặc method, nhưng khi nhiều controller cùng chia sẻ chính sách, cấu hình tập trung dễ kiểm tra hơn. Dù dùng cách nào, phải kiểm tra preflight thực tế và bảo đảm OPTIONS được xử lý trước authentication.

## 11. Vì sao đăng nhập thành công nhưng API vẫn trả 401?

HTTP 401 thường cho biết request chưa được xác thực thành công. Sau khi login, kiểm tra các nguyên nhân sau:

### Frontend chưa có access token

Đăng nhập qua redirect có thể chỉ tạo session ở backend. Nếu frontend gọi API trực tiếp bằng bearer token nhưng không có token, request không thể được xác thực.

Trong mô hình BFF, browser thường gọi BFF bằng cookie session; BFF mới giữ access token và gọi API phía server. Không nên kỳ vọng frontend đọc được access token nếu kiến trúc cố ý giữ token ở backend.

### Dùng ID token thay cho access token

OIDC ID token chứng minh thông tin xác thực người dùng cho client. Access token được cấp để truy cập resource server. Không gửi ID token tới API trừ khi API được thiết kế rõ ràng để chấp nhận loại token đó.

### Access token dành cho API khác

Token có thể hợp lệ với Identity Provider nhưng không dành cho Resource Server đang gọi. Kiểm tra audience, issuer, expiration và các claim mà API yêu cầu. Một JWT có chữ ký hợp lệ vẫn có thể bị API từ chối nếu audience không khớp.

### Token không được gửi đúng header

Với HTTP bearer, request cần có dạng:

~~~http
Authorization: Bearer <access-token>
~~~

Kiểm tra Network tab để xác nhận header thực tế có được gửi không. Tránh gửi hai tiền tố Bearer hoặc đặt token vào query string.

### API không chấp nhận issuer hoặc thuật toán

Resource Server có thể được cấu hình với issuer-uri hoặc jwk-set-uri không khớp token. Kiểm tra cấu hình decoder, key rotation, issuer và các validator tùy chỉnh.

## 12. Vì sao login thành công nhưng API trả 403?

HTTP 403 thường cho biết request đã được xác thực nhưng danh tính không đủ quyền, dù chính sách cụ thể của ứng dụng có thể thay đổi.

Các nguyên nhân thường gặp:

- Access token không chứa scope cần thiết.
- Claim scope được ánh xạ thành authority khác với biểu thức hasAuthority hoặc hasRole.
- API yêu cầu role nhưng token chỉ có scope.
- Người dùng đã đăng nhập nhưng không được cấp quyền cho resource cụ thể.
- CSRF protection từ chối request thay đổi trạng thái trong ứng dụng dùng cookie/session.

Với Spring Security Resource Server, scope thường được ánh xạ thành authority có tiền tố **SCOPE_**. Ví dụ scope orders.read có thể được kiểm tra bằng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Nếu ứng dụng dùng role, cần cấu hình mapping claim phù hợp và phân biệt hasRole("ADMIN") với hasAuthority("ROLE_ADMIN").

## 13. CORS không thay thế CSRF

CORS kiểm soát việc JavaScript từ origin khác đọc phản hồi. CSRF bảo vệ server khỏi một số request giả mạo được trình duyệt gửi kèm thông tin xác thực tự động, thường là cookie session.

Nếu API dùng bearer token được frontend gắn rõ trong Authorization header và không dựa vào cookie tự động, rủi ro CSRF khác với ứng dụng dùng session cookie. Nếu xác thực bằng cookie, cần đánh giá CSRF protection, SameSite cookie và cách gửi CSRF token.

Không tắt CSRF chỉ vì gặp lỗi CORS. Cũng không thêm CORS header để cố sửa một lỗi CSRF 403. Hãy xác định filter hoặc cơ chế nào tạo ra phản hồi lỗi.

## 14. Swagger UI và CORS

Swagger UI cũng là frontend chạy trong trình duyệt. Nếu Swagger UI ở origin khác API, nút Try it out chịu chính sách CORS giống ứng dụng frontend.

Ví dụ:

- Swagger UI: **https://docs.example.com**
- API: **https://api.example.com**

API cần cho phép origin của trang docs nếu người dùng muốn gửi request từ Swagger UI. Security Scheme trong OpenAPI giúp Swagger UI biết cách thêm Authorization header, nhưng không cấu hình CORS ở server.

Kiểm tra cả:

- servers trong OpenAPI có trỏ tới đúng API host và base path không.
- CORS cho phép origin của Swagger UI.
- CORS cho phép header Authorization và Content-Type.
- Spring Security cho phép preflight.
- Token dùng trong Authorize có audience, issuer và scope phù hợp.

Nếu tài liệu tải được nhưng Try it out thất bại, hãy kiểm tra request API trong Network tab; tải OpenAPI JSON và gọi operation là hai request khác nhau.

## 15. Quy trình điều tra theo từng bước trong DevTools

Mở Developer Tools của trình duyệt, chọn tab Network, bật Preserve log rồi thực hiện đăng nhập và gọi API. Tìm các request theo thứ tự thời gian:

1. Authorization endpoint của Identity Provider.
2. Callback tới redirect URI.
3. Token endpoint nếu SPA đổi code trực tiếp.
4. Request OPTIONS preflight tới API.
5. Request API thật như GET hoặc POST.

Với mỗi request, kiểm tra:

| Request | Điều cần xem |
|---|---|
| Authorization redirect | redirect_uri, client_id, response_type, scope, state, code_challenge |
| Callback | URL, status, code/error parameter, cookie và state |
| Token exchange | Status, CORS response headers, grant_type, lỗi invalid_grant hoặc invalid_client |
| OPTIONS preflight | Origin, Access-Control-Request-Method, Access-Control-Request-Headers và response CORS headers |
| API request | Authorization header hoặc cookie, status, response body và CORS headers |

Không chia sẻ authorization code, access token, refresh token, ID token, session cookie hoặc giá trị state/nonce thật trong log hay ảnh chụp màn hình công khai.

### Đọc dấu hiệu lỗi

- **Redirect mismatch**: kiểm tra redirect_uri và đăng ký tại Identity Provider.
- **OPTIONS 401/403**: kiểm tra CORS filter và thứ tự Spring Security.
- **OPTIONS 2xx nhưng thiếu Allow-Origin**: origin không khớp hoặc CORS mapping không áp dụng.
- **OPTIONS cho phép nhưng GET 401**: kiểm tra access token, session, issuer, audience và expiration.
- **GET 403**: kiểm tra scope, authority, role và CSRF.
- **GET 2xx nhưng browser vẫn báo CORS**: phản hồi của request thật thiếu header CORS, dù preflight đã thành công.
- **API trả 2xx nhưng JavaScript không đọc được response header**: kiểm tra Access-Control-Expose-Headers.

## 16. Dùng curl để kiểm tra preflight

Có thể mô phỏng OPTIONS để xem server trả header nào:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Kết quả cần có origin được phép, method GET và các header được yêu cầu. Nếu dùng cookie credentials, kiểm tra thêm:

~~~http
Access-Control-Allow-Credentials: true
Access-Control-Allow-Origin: https://app.example.com
~~~

curl chỉ cho biết server đã trả header gì. curl không thực thi thuật toán CORS của trình duyệt và không chứng minh JavaScript sẽ được phép đọc response.

Có thể kiểm tra request thật:

~~~bash
curl -i "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer invalid-token"
~~~

Trong môi trường test, thay token giả bằng token được cấp đúng cho API. Không ghi token thật vào lệnh được chia sẻ hoặc shell history.

## 17. Kiểm thử CORS preflight bằng MockMvc

Integration test giúp phát hiện cấu hình CORS bị mất sau khi thay đổi Spring Security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsPreflightFromFrontend() throws Exception {
        mockMvc.perform(options("/api/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://app.example.com"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().is2xxSuccessful())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("GET")
            ));
    }
}
~~~

Test này xác nhận preflight được trả lời và origin/method mong muốn được cho phép. Có thể bổ sung kiểm tra Access-Control-Allow-Headers có Authorization và Content-Type.

Nên có test từ origin không được phép để xác nhận server không cấp Allow-Origin cho origin đó. Đồng thời, test request GET thật để xác nhận response thực tế cũng có header CORS; chỉ test OPTIONS là chưa đủ.

Nếu endpoint được bảo vệ, test cần kiểm tra riêng:

- OPTIONS preflight được xử lý mà không yêu cầu access token.
- GET thật yêu cầu token hợp lệ.
- Token thiếu quyền nhận 403 theo chính sách.
- Response lỗi 401/403 vẫn có header CORS phù hợp để frontend đọc được lỗi.

## 18. CORS và redirect URI trong môi trường triển khai

Một cấu hình hoạt động ở localhost có thể hỏng khi đưa lên staging hoặc production vì origin và host công khai thay đổi.

| Môi trường | Frontend origin | API origin | Redirect URI |
|---|---|---|---|
| Local | http://localhost:3000 | http://localhost:8080 | http://localhost:8080/login/oauth2/code/my-client hoặc callback SPA đã đăng ký |
| Staging | https://app.staging.example.com | https://api.staging.example.com | https://app.staging.example.com/login/oauth2/code/my-client |
| Production | https://app.example.com | https://api.example.com | https://app.example.com/login/oauth2/code/my-client |

Tách danh sách origin và redirect URI theo môi trường. Không cho phép wildcard để tiện triển khai nếu ứng dụng dùng cookie credentials hoặc cần giới hạn website được phép gọi API.

Khi dùng nhiều domain frontend, liệt kê chính xác từng origin được phép hoặc dùng allowed origin patterns có kiểm soát. Nếu cho phép credentials, cần bảo đảm phản hồi trả về origin cụ thể, không phải wildcard.

## 19. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Login báo thành công nhưng callback lỗi | Redirect URI không khớp hoặc state/cookie callback bị mất | So sánh redirect_uri đã gửi và URI đăng ký; kiểm tra cookie/state |
| Callback thành công nhưng frontend không có token | Ứng dụng dùng BFF/session hoặc token exchange chưa hoàn tất | Xác định kiến trúc SPA hay BFF và kiểm tra token exchange |
| Token endpoint báo CORS | SPA đổi code trực tiếp nhưng IdP không cho phép origin frontend | Cấu hình origin tại IdP hoặc dùng BFF phù hợp |
| OPTIONS trả 401/403 | Spring Security chặn preflight trước CORS | Bật http.cors và bảo đảm CORS xử lý trước authentication |
| OPTIONS thành công nhưng GET bị CORS | Response của request thật thiếu header CORS | Kiểm tra CORS mapping cho path/method và exception response |
| Authorization không được phép | Thiếu Authorization trong allowed headers | Bổ sung header vào allowedHeaders |
| JSON request bị preflight thất bại | Content-Type hoặc method chưa được cho phép | Cho phép application/json, method và header cần thiết |
| Cookie không được gửi | credentials mode, SameSite, Secure, Domain hoặc third-party cookie policy | Kiểm tra request credentials và cookie attributes |
| Wildcard origin không chạy với cookie | credentials không cho phép Access-Control-Allow-Origin là * | Trả origin cụ thể và bật allowCredentials khi cần |
| API trả 401 dù login thành công | Không có access token, dùng ID token, audience/issuer sai hoặc token hết hạn | Kiểm tra Authorization header và claims của access token |
| API trả 403 | Thiếu scope/role hoặc CSRF từ chối | Kiểm tra authority mapping và CSRF |
| Redirect URI sai sau proxy | Ứng dụng không nhận scheme/host bên ngoài | Cấu hình forwarded headers và kiểm tra redirect URI thực tế |
| Swagger UI tải được docs nhưng Try it out lỗi | API origin chưa cho phép origin của trang docs | Thêm origin Swagger UI vào CORS nếu được phép |
| curl chạy được nhưng browser lỗi | curl không thực thi CORS | Kiểm tra preflight và response headers trong Network tab |

## 20. Checklist trước khi đưa OAuth2/OIDC frontend vào môi trường thật

- [ ] Đã xác định frontend dùng SPA trực tiếp hay mô hình BFF.
- [ ] Redirect URI thực tế khớp chính xác URI đã đăng ký tại Identity Provider.
- [ ] Reverse proxy chuyển tiếp đúng scheme, host, port và context path.
- [ ] Authorization Code Flow dùng PKCE khi phù hợp với public client.
- [ ] Token endpoint cho phép origin frontend nếu browser đổi code trực tiếp.
- [ ] API CORS allowlist chỉ chứa origin cần thiết.
- [ ] CORS cho phép method và request header thực tế, đặc biệt Authorization và Content-Type.
- [ ] OPTIONS preflight không bị yêu cầu bearer token.
- [ ] Response thành công và response lỗi đều có CORS header phù hợp.
- [ ] Nếu dùng session cookie cross-origin, credentials, SameSite, Secure và Domain được cấu hình đúng.
- [ ] Access token dành cho đúng Resource Server; không dùng ID token thay access token.
- [ ] Issuer, audience, expiration, scope và authority mapping đã được kiểm tra.
- [ ] CSRF được đánh giá riêng nếu xác thực dựa trên cookie.
- [ ] Swagger UI origin được cho phép nếu cần Try it out từ domain docs.
- [ ] Có test preflight và test request API thật.

## Kết luận

Redirect URI xác định nơi Identity Provider đưa trình duyệt trở lại sau đăng nhập; CORS xác định JavaScript từ origin nào được phép đọc phản hồi cross-origin. Hai cơ chế độc lập và không thay thế xác thực hoặc phân quyền. Khi đăng nhập thành công nhưng API thất bại, hãy lần theo authorization redirect, callback, token exchange, OPTIONS preflight và request API thật. Trong Spring Security, cấu hình CORS để preflight được xử lý trước authentication, cho phép đúng origin/method/header và chỉ bật credentials khi cần cookie. Sau đó kiểm tra access token, issuer, audience, scope, CSRF và forwarded headers. Network tab cho biết bước nào lỗi; curl giúp xem response header; MockMvc giúp giữ cấu hình CORS ổn định qua các thay đổi.
