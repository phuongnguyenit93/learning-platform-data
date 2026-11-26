# Thiết kế chính sách theo từng hành trình thay vì sao chép một cấu hình chung

## Mục tiêu và bối cảnh

Khi một ứng dụng Spring Security phục vụ đồng thời trang web có phiên đăng nhập, API nhận Bearer token, callback của nhà cung cấp danh tính và webhook từ hệ thống đối tác, việc áp dụng một bộ cấu hình HTTP giống hệt cho mọi URL dễ tạo ra hai loại lỗi trái ngược: hành trình hợp lệ không hoạt động và hành trình nhạy cảm bị nới lỏng bảo vệ quá mức.

Ví dụ, **CSRF cần được duy trì** đối với thao tác thay đổi dữ liệu được xác thực bằng cookie phiên trình duyệt; nhưng một API **chỉ** nhận Bearer token qua header `Authorization` và không sử dụng cookie để xác thực thường không cần cơ chế CSRF giống ứng dụng dùng session. Tương tự, CORS có thể cần cho API do một frontend ở origin khác gọi, nhưng không vì thế mà phải mở CORS cho trang quản trị, endpoint nội bộ hay webhook. CSP cho giao diện người dùng và `frame-ancestors` cho nội dung được đối tác nhúng cũng có những yêu cầu khác nhau.

Bài này thuộc chủ đề **Tích hợp ứng dụng** của `SPRING_SECURITY_HTTP_PROTECTION`: thiết kế các lớp phòng vệ HTTP và trình duyệt (CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session) theo từng hành trình nghiệp vụ, áp dụng trong Spring Security Servlet và Reactive, rồi kiểm thử ranh giới bảo mật thay vì sao chép nguyên một `SecurityFilterChain` hoặc `SecurityWebFilterChain` cho mọi đường dẫn.

Sau khi học, người đọc có thể:

- Lập bản đồ hành trình từ góc nhìn **người gọi, phương thức xác thực, credential tự động được trình duyệt gửi, thao tác thay đổi trạng thái và origin**.
- Quyết định có cơ sở nơi nào cần CSRF, CORS, chính sách phiên và browser headers; nhận biết ngoại lệ cần bảo vệ riêng.
- Tổ chức các filter chain có thứ tự, phạm vi URL rõ ràng và quy tắc từ chối mặc định.
- Kiểm thử cả trường hợp được phép và các trường hợp bị chặn trên Servlet/MockMvc và Reactive/WebTestClient.

## 1. Hành trình là đơn vị thiết kế chính sách

Một *hành trình* là chuỗi request thực tế để hoàn thành một tác vụ, chẳng hạn: mở trang đăng nhập → gửi form → nhận session cookie → cập nhật địa chỉ giao hàng → đăng xuất. Một URL đơn lẻ chưa đủ để mô tả rủi ro nếu không biết trình duyệt có tự gắn credential hay không, ai có quyền gọi và dữ liệu nhạy cảm nào bị tác động.

Xét ứng dụng thương mại có các nhóm truy cập sau:

| Hành trình và ví dụ URL | Cơ chế tin cậy chính | CSRF | CORS và trình duyệt | Phòng vệ bổ sung |
|---|---|---|---|---|
| Trang đăng nhập và mua hàng `/app/**` | Session cookie, form login | Bật cho POST/PUT/PATCH/DELETE và các phương thức thay đổi trạng thái | Thường same-origin, không cần mở CORS cho nơi khác | Cookie an toàn, chống fixation, CSP, chống clickjacking, cache phù hợp |
| Frontend SPA gọi BFF `/bff/**` | Cookie phiên do BFF cấp | Bật; SPA phải gửi token theo cơ chế đã chọn | Chỉ cho phép origin frontend đã xác minh nếu khác origin | `SameSite`, `Secure`, kiểm soát credential, không lộ CSRF token cho origin tùy ý |
| API tài nguyên `/api/**` | Chỉ Bearer token trong header `Authorization` | Có thể tắt **trong chain API** sau khi xác nhận không nhận cookie/session làm credential | Cho phép origin cụ thể nếu frontend browser cần gọi | Kiểm tra JWT, quyền theo scope, stateless, giới hạn endpoint |
| Webhook thanh toán `/webhooks/payments/**` | Chữ ký HMAC/chữ ký số từ đối tác | Không áp dụng nếu không sử dụng credential tự gửi của trình duyệt | Thường không cần CORS | Xác minh chữ ký trên raw body, timestamp, chống phát lại, idempotency |
| OAuth2/OIDC login callback `/login/oauth2/code/**` | Luồng đăng nhập có `state` và, nếu áp dụng, `nonce` | Cần đánh giá riêng theo protocol; không bỏ xác minh `state` để sửa lỗi CSRF | Không xem CORS là cơ chế bảo vệ callback | Redirect URI chính xác, cookie và session tương thích, không để matcher bỏ sót |
| Nội dung được đối tác nhúng `/embed/**` | Token hoặc quyền truy cập riêng cho nội dung nhúng | Nếu nhận cookie và thay đổi trạng thái thì vẫn cần CSRF | Tùy cách nội dung gọi API | CSP `frame-ancestors` theo đối tác, cân nhắc `X-Frame-Options` |
| Vận hành `/actuator/**` | Mạng nội bộ, quyền chuyên dụng | Theo cách xác thực và phương thức request | Không mở đại trà | Giới hạn endpoint/role, firewall/gateway và quan sát an ninh |

Bảng này là **ma trận quyết định**, không phải danh sách URL được cấp phép mặc định. Tên đường dẫn chỉ để minh họa; từng ứng dụng phải xác định URL thực tế. Nếu cùng một endpoint có thể xác thực bằng cookie **và** Bearer token, không thể kết luận “đây là API nên tắt CSRF”. Phải xác định đường xác thực nào thật sự được chấp nhận rồi mới chọn chính sách.

### Năm câu hỏi trước khi cấu hình

1. **Ai phát request?** Trình duyệt điều hướng, JavaScript của frontend, ứng dụng di động, backend đối tác hay hệ thống vận hành?
2. **Credential đến từ đâu?** Cookie được trình duyệt tự gửi, HTTP Basic, Bearer token được client chủ động đặt, hoặc chữ ký độc lập? Có đường xác thực dự phòng nào vô tình chấp nhận cookie không?
3. **Request có tác dụng gì?** Đọc dữ liệu, đổi mật khẩu, thanh toán, cập nhật phiên hay kích hoạt thao tác nhạy cảm? GET phải được thiết kế không gây tác dụng thay đổi trạng thái.
4. **Ranh giới trình duyệt ra sao?** Origin nào được gọi qua JavaScript, tài liệu có được đặt trong iframe, tài nguyên nào được tải bởi CSP, frontend có chạy khác site không?
5. **Đâu là trạng thái từ chối?** Request không thuộc hành trình nào, origin lạ, token thiếu, CSRF token sai, URL bị chuẩn hóa bất thường sẽ bị xử lý thế nào?

Câu trả lời nên được ghi thành **hợp đồng bảo mật theo hành trình**: đường dẫn và method, loại credential hợp lệ, chính sách CSRF/CORS, quyền, session, headers, cơ chế kiểm thử. Hợp đồng này giúp reviewer nhận ra một thay đổi cấu hình có mở rộng quyền sang hành trình khác hay không.

## 2. Tại sao sao chép một cấu hình chung thường sai

### 2.1. Sao chép `csrf().disable()` từ API sang web dùng cookie

Trang `/app/orders` dùng session cookie. Người dùng đã đăng nhập có thể bị dẫn tới website độc hại tự tạo POST tới ứng dụng. Trình duyệt có thể đính kèm cookie tùy `SameSite`, ngữ cảnh và chính sách của trình duyệt. Nếu server chỉ kiểm tra session và bỏ CSRF token, thao tác có nguy cơ được thực hiện dưới quyền người dùng.

**Nguyên tắc:** luôn giữ CSRF cho thao tác thay đổi trạng thái được xác thực bằng credential trình duyệt tự gửi. `SameSite` là lớp bổ sung, không thay thế một cách tổng quát cho token CSRF. API Bearer chỉ có thể tắt CSRF khi server **thực sự không** chấp nhận cookie/session/Basic được trình duyệt tự gắn để xác thực API đó.

### 2.2. Sao chép CORS `*` vào mọi endpoint

CORS quyết định **mã JavaScript của origin nào được phép đọc phản hồi** trong trình duyệt; CORS không thay cho xác thực, phân quyền, CSRF, chữ ký webhook hay bảo vệ server-to-server. Origin không được phép có thể bị trình duyệt chặn đọc phản hồi, nhưng request vẫn có thể được gửi trong một số trường hợp, nên hành động nhạy cảm phải có kiểm soát server-side.

Dùng `allowedOrigins("*")` đồng thời cho phép credentials là cấu hình không hợp lệ theo chuẩn CORS. Với cookie cross-origin phải khai báo origin cụ thể, `allowCredentials(true)` nếu thực sự cần và duy trì kiểm soát CSRF. Không sử dụng CORS để “sửa” lỗi 401/403 của API bằng cách cấp quyền cho tất cả origin.

### 2.3. Sao chép CSP và chống iframe cho cả nội dung nhúng

`frame-ancestors 'none'` phù hợp với trang quản trị hoặc luồng thanh toán không được nhúng. Tuy nhiên, nếu một widget được phép nhúng vào portal của đối tác, chỉ route `/embed/**` mới cần `frame-ancestors https://partner.example` với origin đã duyệt. Khi đó `X-Frame-Options: DENY` hoặc `SAMEORIGIN` có thể gây xung đột ở một số trình duyệt/cách xử lý; cần kiểm tra tập header thực tế và trình duyệt mục tiêu, không nới lỏng toàn ứng dụng.

### 2.4. Sao chép session policy sang API

`SessionCreationPolicy.STATELESS` yêu cầu Spring Security không tạo hoặc dùng `HttpSession` để lấy `SecurityContext` cho chain đó. Nó **không tự động biến một endpoint chấp nhận cookie thành an toàn CSRF**, cũng không xóa cookie do thành phần khác phát hành. Ngược lại, ép ứng dụng form login thành stateless sẽ làm mất ngữ cảnh đăng nhập qua phiên nếu không có cơ chế thay thế.

## 3. Thiết kế chính sách Servlet theo đường đi thực tế

Spring Security Servlet sử dụng `FilterChainProxy` và nhiều `SecurityFilterChain`. Khi có nhiều chain, **chain đầu tiên có `securityMatcher` khớp request sẽ được chọn**. Các `requestMatchers` nằm bên trong `authorizeHttpRequests` chỉ phân quyền **sau khi chain đã được chọn**; chúng không tự chuyển request sang chain khác.

Ví dụ sau phân chia web `/app/**`, API `/api/**` và chain dự phòng cho URL chưa được đặc tả. Đây là cấu hình minh họa cho ứng dụng dùng Spring Security với Servlet và OAuth2 Resource Server; ứng dụng cần cung cấp `JwtDecoder` hoặc cấu hình `issuer-uri` hợp lệ cho API JWT.

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebSecurity
class JourneySecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain app(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/app/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/app/login", "/app/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/app/login")
                .loginProcessingUrl("/app/login")
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/app/logout")
                .logoutSuccessUrl("/app/login?logout"))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; script-src 'self'; " +
                    "style-src 'self'; object-src 'none'; " +
                    "base-uri 'self'; frame-ancestors 'none'")));
        return http.build();
    }

    @Bean
    @Order(99)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://portal.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
```

**Giải thích các quyết định:**

- Chain API chỉ match `/api/**`, xác thực bằng Bearer JWT và dùng policy stateless. Việc tắt CSRF **chỉ đúng với giả định** API không có đường xác thực sử dụng cookie/session. Nếu triển khai thêm session auth, phải đánh giá và điều chỉnh lại.
- `cors(Customizer.withDefaults())` lấy `CorsConfigurationSource` khai báo cho `/api/**`. CORS preflight cần được bộ lọc CORS xử lý trước bước xác thực thông thường; nếu chỉ cấp `permitAll()` cho OPTIONS mà không có cấu hình CORS đúng thì trình duyệt vẫn có thể chặn.
- Chain web giữ CSRF. Form đăng nhập được đặt đúng `/app/login` cho cả GET và POST, logout tại `/app/logout`; ứng dụng phải có trang render GET `/app/login`. Việc đổi đường dẫn quan trọng vì form login mặc định ở `/login` sẽ nằm **ngoài** chain bị giới hạn bởi `/app/**`.
- CSP ở web chỉ cho script/style từ cùng origin; không dùng `unsafe-inline`. Nếu giao diện thật sử dụng inline script/style, cần thiết kế nonce/hash hoặc sửa cách phân phối tài nguyên và kiểm thử trước khi bật cưỡng chế.
- Chain fallback từ chối các request chưa được xác định. Nếu ứng dụng có `/actuator/health`, `/error`, callback OAuth hoặc tài nguyên tĩnh nằm ngoài `/app/**`, phải thiết kế matcher và quyền tương ứng một cách chủ đích; không xóa fallback chỉ để một URL mới “chạy được”.

Lưu ý: ví dụ này chỉ dùng cho ba nhóm route đã mô tả. Một ứng dụng có BFF dùng cookie, webhook có chữ ký hoặc OAuth callback sẽ cần chain/quy tắc bổ sung **theo hợp đồng của từng hành trình**. Thêm một chain phải kiểm tra thứ tự `@Order` và sự trùng lặp matcher: một chain `/**` đặt sớm sẽ nuốt mọi chain cụ thể phía sau.

### 3.1. Form, CSRF token và session trong web

Form HTML gửi POST tới `/app/login`, `/app/orders` hoặc `/app/logout` phải mang token CSRF do server cấp, ví dụ hidden input có tên và giá trị lấy từ đối tượng `CsrfToken` của request. Không hard-code token trong template. Khi dùng Thymeleaf tích hợp Spring Security, có thể lấy `_csrf.parameterName` và `_csrf.token` từ model/request hoặc để tích hợp form của framework chèn token theo cơ chế được hỗ trợ.

```html
<form method="post" action="/app/orders">
  <!-- name và value được render động từ CsrfToken của request -->
  <input type="hidden" name="_csrf" value="TOKEN_DUOC_SERVER_RENDER">
  <button type="submit">Xác nhận đơn hàng</button>
</form>
```

Sau khi đăng nhập hoặc đăng xuất, token CSRF có thể bị xóa/thay mới theo cơ chế quản lý phiên và CSRF của phiên bản Spring Security. SPA/BFF cần quy trình **lấy lại token** sau những chuyển đổi đó; không giữ mãi token cũ trong bộ nhớ. Với client JavaScript, có thể công bố token qua endpoint cùng origin được bảo vệ phù hợp hoặc theo cơ chế repository/handler của Spring Security và gửi lại bằng header ở các request thay đổi trạng thái.

Session cookie cần `Secure` khi chạy HTTPS, `HttpOnly` cho cookie phiên, `SameSite` phù hợp với từng luồng và kiểm soát thời hạn đăng nhập. Đảm bảo session fixation protection hoạt động khi xác thực; cấu hình proxy đúng để ứng dụng nhận biết request HTTPS. `SameSite=None` thường đòi `Secure` và có thể chịu giới hạn third-party cookies của trình duyệt: phải thử trực tiếp luồng đăng nhập/nhúng thay vì mặc định mọi cookie sẽ được gửi.

### 3.2. Trường hợp SPA + BFF

Trong mô hình SPA gọi BFF dùng cookie, endpoint `/bff/orders` nhìn bề ngoài như REST API nhưng trình duyệt tự gửi cookie xác thực. Vì vậy **CSRF phải được giữ**, kể cả khi phản hồi là JSON. Nếu SPA và BFF ở hai origin khác nhau, CORS phải giới hạn origin cụ thể, có `allowCredentials(true)` khi cần cookie cross-origin, và request JavaScript phải cung cấp CSRF token qua header mà backend xác minh. CORS và CSRF giải quyết hai lớp vấn đề khác nhau.

Ngược lại, API JWT trong code ở trên dùng `Authorization: Bearer ...`; trình duyệt không tự phát minh giá trị header token cho một trang độc hại. Điều này giúp tách chính sách CSRF, nhưng không miễn API khỏi kiểm soát phân quyền, hạn chế scope, xác minh issuer/audience và các rủi ro như XSS làm lộ token trong frontend.

## 4. Áp dụng cùng nguyên tắc trên Spring Security Reactive

WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity`; cách chọn chain vẫn dựa trên matcher và thứ tự ưu tiên, nhưng API cấu hình, filter và thư viện kiểm thử **khác Servlet**. Không sao chép nguyên class `HttpSecurity` hay kiểu `CorsConfigurationSource` của Servlet sang Reactive.

Ví dụ dưới đây minh họa riêng API WebFlux chỉ nhận JWT. Nó phù hợp với dịch vụ WebFlux chỉ cung cấp API; nếu dịch vụ còn phục vụ trang web cookie/BFF, cần thêm chain cho hành trình đó, bật CSRF và xử lý login theo đúng matcher trước fallback.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
class ReactiveJourneySecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(auth -> auth.anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(99)
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth.anyExchange().denyAll())
            .build();
    }
}
```

Với frontend khác origin, thêm CORS cho chain WebFlux bằng nguồn cấu hình từ `org.springframework.web.cors.reactive`, khai báo origin/method/header chính xác và kiểm tra preflight. Đừng dùng nhầm `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet khi viết cấu hình Reactive. Nếu API có cookie xác thực hoặc dùng WebSession cho người dùng, chính sách CSRF phải được thiết kế lại tương ứng.

Đối với giao diện React/Angular/Vue chạy với BFF WebFlux, một chain `/bff/**` nên giữ `csrf(Customizer.withDefaults())`; phía client phải lấy token thông qua cơ chế deferred CSRF token phù hợp và đưa vào các request thay đổi trạng thái. Các phương thức logout/login, endpoint lấy token và callback phải cùng nằm trong phạm vi matcher thích hợp.

## 5. Headers và HTTP firewall: chính sách chung có ngoại lệ có kiểm soát

Không phải mỗi thuộc tính đều cần cấu hình lặp lại trên từng chain. Một số phòng vệ phải được bảo đảm trên **toàn bộ điểm vào hệ thống**, còn khác biệt theo hành trình cần được giải thích.

| Cơ chế | Nguyên tắc triển khai | Khi cần khác biệt |
|---|---|---|
| HTTPS và HSTS | Ép HTTPS từ ingress/gateway; kiểm tra `Strict-Transport-Security` trên phản hồi HTTPS. | Chỉ bật `includeSubDomains` sau khi xác nhận mọi subdomain liên quan hỗ trợ HTTPS; HSTS không được trình duyệt tiếp nhận từ HTTP. |
| CSP | Giới hạn `default-src`, `script-src`, `object-src`, `base-uri` cho trang HTML. | Trang đăng nhập, widget nhúng hoặc frontend có CDN khác nhau cần chính sách theo route, không cấp origin tùy ý. |
| Chống clickjacking | Bảo vệ trang nhạy cảm bằng `frame-ancestors` và header tương thích. | Chỉ cho phép partner origin trên widget thực sự phải nhúng; kiểm tra xung đột `X-Frame-Options`. |
| Cache-Control | Không cache thông tin đăng nhập, trang chứa token và phản hồi nhạy cảm qua cache chia sẻ. | Asset có fingerprint có thể cache dài; phản hồi API public cần hợp đồng cache riêng. |
| Session/cookie | Rotation/fixation protection, timeout, `Secure`, `HttpOnly`, `SameSite` đúng ranh giới. | API bearer không phụ thuộc session; BFF cookie cần đánh giá CSRF và cross-site. |
| HTTP firewall | Không cho phép URL bất thường, phương thức nguy hiểm không dùng, đường dẫn mơ hồ. | `StrictHttpFirewall` và hành vi chuẩn hóa URL thường nằm ở mức ứng dụng/filter proxy, không thể tùy tiện xem là ngoại lệ độc lập trong mỗi chain. |
| Reverse proxy | Chỉ tin các forwarded headers từ proxy/ingress do tổ chức quản lý. | Nhiều hop proxy và termination TLS cần kiểm chứng origin/scheme thực tế. |

Đặc biệt, matcher dùng để **chọn chain** và matcher dùng để **phân quyền** có thể xử lý URL đã chuẩn hóa khác với cách ingress/router biểu diễn đường dẫn. Kiểm tra các biến thể dấu gạch chéo, dấu chấm phẩy, chuỗi mã hóa và method lạ ở cả gateway lẫn ứng dụng; không mở rộng `StrictHttpFirewall` để né một lỗi routing mà chưa hiểu tác động.

Luồng ngoại lệ nên có người sở hữu, lý do, phạm vi URI/method/origin cụ thể, kiểm thử phủ định và thời điểm đánh giá lại. Ví dụ “partner chỉ được nhúng `/embed/receipt/**`” hữu ích hơn nhiều so với “tắt frame protection vì đối tác cần iframe”.

## 6. Kiểm thử bằng ma trận hành trình

Điều quan trọng không chỉ là một request hợp lệ trả về 200, mà còn là một request **vượt ranh giới** bị từ chối. Với Servlet, dùng Spring Security Test và MockMvc; với WebFlux, dùng WebTestClient cùng `spring-security-test`. Luôn gắn test với controller hoặc route thật của ứng dụng để phân biệt lỗi bảo mật và lỗi 404 do thiếu handler.

| Tình huống kiểm thử | Kỳ vọng |
|---|---|
| POST `/app/orders` có user/session nhưng thiếu hoặc sai CSRF token | 403; nghiệp vụ chưa chạy |
| POST `/app/orders` với user và CSRF token hợp lệ | Vượt qua lớp CSRF, sau đó phải chịu phân quyền/nghiệp vụ |
| POST `/api/orders` với JWT hợp lệ, không gửi CSRF token | Không bị chặn bởi CSRF; vẫn kiểm tra scope/role |
| POST `/api/orders` chỉ có session cookie của `/app/**`, không có Bearer token | Không được coi là người dùng đã xác thực API |
| OPTIONS preflight từ origin được phép tới `/api/**` | CORS trả origin/method/header phù hợp trước xác thực bearer |
| Preflight từ origin không được phép | Không cấp quyền CORS |
| GET `/app/login` và POST `/app/login` | Trang đăng nhập truy cập được, POST được filter xử lý và vẫn kiểm tra CSRF |
| Request ngoài các chain đã định nghĩa | Bị fallback từ chối |
| Response HTTPS của trang nhạy cảm | Có HSTS, CSP/frame protection và cache policy theo hợp đồng |
| Logout/login hoặc refresh session | Token CSRF và session theo vòng đời dự kiến; client lấy lại token khi cần |
| Webhook chữ ký sai hoặc replay | Bị từ chối trước xử lý nghiệp vụ |

Ví dụ kiểm thử Servlet, giả định ứng dụng đã có handler `/app/orders` và `/api/orders`; có thể chỉnh `status()` cuối theo mã HTTP mà controller thật trả về:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

// Không có CSRF token: web dùng cookie phải từ chối.
mockMvc.perform(post("/app/orders").with(user("alice")))
       .andExpect(status().isForbidden());

// Có CSRF token: vượt qua lớp CSRF; còn phụ thuộc quyền/controller.
mockMvc.perform(post("/app/orders").with(user("alice")).with(csrf()));

// API JWT không dùng CSRF token. Kiểm tra tiếp kết quả từ handler.
mockMvc.perform(post("/api/orders").with(jwt()));
```

Trong WebFlux, dùng `WebTestClient` với `SecurityMockServerConfigurers.mockJwt()` để kiểm tra xác thực Bearer, và `SecurityMockServerConfigurers.csrf()` cho các hành trình dùng CSRF. Không chuyển máy móc các post processor của MockMvc sang WebTestClient. Với CORS, gửi đúng `Origin` và `Access-Control-Request-Method` trong OPTIONS; với HSTS, tạo request mang scheme HTTPS để kiểm tra phản hồi phù hợp.

### Lỗi triển khai thường gặp và cách chẩn đoán

| Triệu chứng | Điểm cần kiểm tra trước |
|---|---|
| Login hiển thị nhưng POST login 404/405 | `loginProcessingUrl` và `securityMatcher` có khớp không; controller GET và filter POST có cùng route dự kiến không |
| SPA nhận 403 ngay sau khi đăng nhập | CSRF token có được lấy mới, header đúng tên và session/cookie có hợp lệ không |
| Preflight 401/403 | CORS filter/source có áp dụng cho đúng chain và xử lý trước xác thực không; origin/header/method có thuộc allowlist không |
| API “chỉ JWT” vẫn cho phép cookie login | Có chain khác match trước không; có filter session/form/basic hoặc custom auth cho API không |
| Trang nhúng bị trình duyệt từ chối | CSP `frame-ancestors`, `X-Frame-Options`, response từ redirect và origin của trang cha |
| HSTS không xuất hiện khi gọi HTTP | Kiểm tra request HTTPS và TLS termination/forwarded headers; HSTS chỉ phát huy hiệu lực với HTTPS |
| Endpoint mới bị 403 | Route có nằm ngoài matcher rồi rơi vào fallback `denyAll` không; thiết kế hành trình trước khi nới quyền |

## 7. Quy trình thay đổi chính sách khi tích hợp tính năng mới

Giả sử đội sản phẩm muốn cho cổng đối tác đặt widget thanh toán trong iframe và gọi API. Có thể triển khai theo thứ tự:

1. **Vẽ chuỗi request:** trang đối tác → iframe `/embed/checkout/**` → BFF/API → redirect/callback. Xác định origin trang cha, origin iframe, credential, cookie và method thay đổi dữ liệu.
2. **Chọn auth và CSRF:** nếu iframe dùng cookie cho POST thì giữ CSRF và thử các giới hạn cookie cross-site thực tế; nếu cấp token riêng, xác định nơi lưu, thời hạn, audience và cách chống phát lại.
3. **Giới hạn nhúng và CORS:** chỉ `frame-ancestors` với partner được duyệt cho trang iframe; API chỉ mở CORS cho origin thực sự gọi bằng JavaScript. Hai loại origin này không nhất thiết giống nhau.
4. **Cấu hình chain cụ thể:** matcher đủ hẹp, auth/CSRF/session/headers tương ứng; không làm thay đổi bảo vệ mặc định của `/app/**` hay `/api/**`.
5. **Kiểm thử cả đường hợp lệ và bị chặn:** origin được duyệt và origin lạ, token hợp lệ/hết hạn, session thiếu, preflight, callback sai `state`, clickjacking trên URL ngoài phạm vi.
6. **Quan sát khi triển khai:** ghi nhận kết quả xác thực/phân quyền, các lỗi CSRF/CORS và CSP reporting nếu sử dụng; tránh log token, cookie, chữ ký hoặc dữ liệu nhạy cảm.

Đối với việc nâng cấp Spring Security, cần kiểm tra lại API DSL, cách xử lý CSRF token bất đồng bộ/deferred, CORS integration, matcher và security headers theo phiên bản đang chạy. Không kết luận bảo vệ hoạt động chỉ vì ứng dụng khởi động thành công: các test ở ranh giới mới chứng minh hành trình hợp lệ và hành trình bị cấm được phân biệt.

## Kết luận

Thiết kế HTTP protection tốt bắt đầu từ **hành trình và mô hình credential**, rồi mới chọn cấu hình Spring Security. Mỗi chain cần có ranh giới rõ, chính sách phù hợp với cách browser hay client sử dụng endpoint, điều kiện ngoại lệ có giải thích và test phủ định. Nhờ vậy, việc thêm API, SPA/BFF, webhook, callback hoặc trang nhúng không vô tình làm yếu đi CSRF, CORS, CSP, HSTS, firewall và bảo vệ session của những hành trình khác.

