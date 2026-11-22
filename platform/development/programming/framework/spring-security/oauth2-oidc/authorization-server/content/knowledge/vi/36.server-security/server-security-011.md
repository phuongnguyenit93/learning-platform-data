# Thiết lập security headers và bảo vệ giao diện login, consent

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của các HTTP security response headers trong một OAuth 2.0/OpenID Connect Authorization Server.
- Nhận biết các header Spring Security đã bật mặc định và các chính sách ứng dụng cần tự thiết kế như Content Security Policy (CSP), Referrer Policy và Permissions Policy.
- Áp dụng cùng một bộ header cho cả filter chain xử lý protocol endpoint và filter chain xử lý giao diện web.
- Bảo vệ trang đăng nhập, trang xin consent, session cookie và dữ liệu nhạy cảm hiển thị trên trình duyệt.
- Phân biệt CSRF token của Spring Security với tham số `state` mà Spring Authorization Server sử dụng trong consent flow.
- Kiểm tra header, chính sách CSP và hành vi của login/consent bằng MockMvc, trình duyệt và `curl`.

## 1. Vì sao Authorization Server cần bảo vệ giao diện web?

Authorization Server thường có hai nhóm bề mặt cần bảo vệ. Nhóm thứ nhất là các protocol endpoint như authorization endpoint, token endpoint, revocation endpoint và các endpoint OpenID Connect. Nhóm thứ hai là giao diện mà người dùng trực tiếp tương tác, thường gồm trang login, trang consent, trang lỗi và trang logout.

Trang login tiếp nhận thông tin xác thực và tạo session đăng nhập. Trang consent hiển thị ứng dụng đang yêu cầu quyền gì và cho phép người dùng quyết định có cấp quyền hay không. Nếu các trang này bị nhúng vào website độc hại, bị chèn script, bị cache trên máy dùng chung hoặc để lộ thông tin qua request phụ, kẻ tấn công có thể đánh cắp thông tin, đánh lừa thao tác hoặc làm người dùng cấp quyền ngoài ý muốn.

HTTP security headers cho phép máy chủ hướng dẫn trình duyệt cách xử lý nội dung. Chúng bổ sung một lớp phòng vệ cho trình duyệt, nhưng không thay thế xác thực, phân quyền, kiểm tra đầu vào, mã hóa đầu ra, CSRF protection hay cấu hình OAuth 2.0/OIDC đúng chuẩn. Ví dụ, CSP có thể hạn chế nguồn script được phép chạy, nhưng ứng dụng vẫn phải encode dữ liệu do người dùng cung cấp để ngăn XSS.

Trong Spring Security, các header được ghi vào response bởi `HeaderWriterFilter`. Cấu hình header nằm trong từng `SecurityFilterChain`; request chỉ đi qua chain đầu tiên khớp với request matcher. Vì vậy, một cấu hình header chỉ nằm trong chain giao diện có thể không bảo vệ các protocol endpoint được xử lý bởi chain ưu tiên cao hơn.

## 2. Các header quan trọng

Spring Security đã bật một số header an toàn theo mặc định. Với Servlet stack, bộ mặc định gồm:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
X-Frame-Options: DENY
X-XSS-Protection: 0
```

`Strict-Transport-Security` chỉ được thêm vào response HTTPS. CSP, Referrer Policy và Permissions Policy không được Spring Security tự đặt vì chính sách phù hợp phụ thuộc vào nội dung và chức năng của từng ứng dụng.

| Header | Mục đích | Hướng cấu hình cho Authorization Server |
|---|---|---|
| `Cache-Control`, `Pragma`, `Expires` | Ngăn trình duyệt và cache trung gian lưu response nhạy cảm. | Giữ mặc định cho login, consent, trang tài khoản và response chứa dữ liệu cá nhân. |
| `X-Content-Type-Options: nosniff` | Ngăn trình duyệt tự đoán MIME type và diễn giải nội dung sai loại. | Giữ mặc định; server phải trả `Content-Type` chính xác cho HTML, CSS, JavaScript và file tải xuống. |
| `Strict-Transport-Security` | Ghi nhớ rằng domain phải được truy cập bằng HTTPS. | Dùng HTTPS toàn bộ; chỉ bật `includeSubDomains` khi mọi subdomain liên quan đều hỗ trợ HTTPS. |
| `X-Frame-Options` | Hạn chế trang bị nhúng vào `frame` hoặc `iframe`, giảm clickjacking. | Dùng `DENY` nếu không có nhu cầu nhúng giao diện. Nếu cần nhúng cùng origin, cân nhắc `SAMEORIGIN` và đồng bộ với CSP `frame-ancestors`. |
| `Content-Security-Policy` | Giới hạn nguồn script, style, ảnh, frame và nơi form được gửi. | Khai báo rõ các nguồn cần thiết; triển khai `Report-Only` trước khi enforce. |
| `Referrer-Policy` | Giới hạn thông tin URL được gửi trong header `Referer`. | Dùng `strict-origin-when-cross-origin` hoặc `no-referrer` cho trang có dữ liệu nhạy cảm trong URL. |
| `Permissions-Policy` | Tắt các tính năng trình duyệt mà giao diện không cần. | Có thể tắt camera, microphone và geolocation trên login/consent. |

### 2.1. Cache control

Spring Security mặc định gửi `no-store` cùng các chỉ thị cache liên quan để tránh trường hợp người dùng đăng xuất nhưng người tiếp theo bấm Back và xem lại nội dung nhạy cảm. Điều này đặc biệt hữu ích cho trang login, consent và trang quản lý tài khoản.

Không nên tắt cache control trên toàn bộ ứng dụng chỉ để tăng tốc tải trang. Với tài nguyên tĩnh như CSS, JavaScript và ảnh có version hoặc content hash trong tên file, ứng dụng có thể đặt cache policy riêng. Spring Security cho phép response có cache header do ứng dụng đặt ghi đè chính sách mặc định. Không đưa thông tin cá nhân, authorization code, token hoặc nội dung consent vào tài nguyên tĩnh có thể cache.

`no-cache` không đồng nghĩa với `no-store`: `no-cache` vẫn cho phép lưu response nhưng yêu cầu xác thực lại trước khi sử dụng; `no-store` yêu cầu cache không lưu response. Cũng cần kiểm tra service worker hoặc cache do JavaScript quản lý vì các cơ chế đó không nhất thiết tuân theo HTTP cache headers.

### 2.2. HSTS và HTTPS

HSTS giúp trình duyệt tự chuyển các lần truy cập tiếp theo sang HTTPS sau khi nhận header từ một response HTTPS hợp lệ. Giá trị `max-age=31536000` tương ứng một năm. `includeSubDomains` mở rộng chính sách tới mọi subdomain; chỉ bật khi tất cả subdomain đó đã có TLS hoạt động ổn định. `preload` là cam kết vận hành rộng hơn và cần đáp ứng các điều kiện của danh sách HSTS preload, vì vậy không nên bật chỉ để hoàn thành một cấu hình mẫu.

Spring Security chỉ gửi HSTS khi request được nhận diện là HTTPS. Nếu TLS kết thúc tại reverse proxy hoặc load balancer, ứng dụng phía sau phải nhận diện đúng scheme gốc thông qua forwarded headers từ proxy đáng tin cậy. Proxy cần xóa forwarded headers do client tự gửi trước khi đặt lại giá trị chuẩn. Nếu ứng dụng luôn nhận request như HTTP, HSTS có thể không xuất hiện dù người dùng truy cập URL HTTPS ở bên ngoài.

### 2.3. Clickjacking và CSP

`X-Frame-Options: DENY` chặn trình duyệt hiển thị trang trong frame. CSP cung cấp chỉ thị hiện đại hơn là `frame-ancestors 'none'`; hai chính sách nên nhất quán. Nếu giao diện thực sự cần được nhúng bởi một origin xác định, hãy khai báo rõ origin đó trong `frame-ancestors` và đánh giá lại X-Frame-Options. Không sử dụng `ALLOW-FROM`, vì chỉ thị này đã lỗi thời và không được hỗ trợ rộng rãi.

CSP kiểm soát nguồn mà trình duyệt được phép tải script, style, ảnh, font, kết nối và frame. Một policy cơ bản cho trang login/consent có thể gồm:

```http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'
```

Các chỉ thị đáng chú ý:

- `default-src 'self'`: dùng origin hiện tại làm mặc định cho các loại tài nguyên chưa có chỉ thị riêng.
- `base-uri 'self'`: giới hạn URL gốc mà thẻ `base` được phép sử dụng.
- `object-src 'none'`: chặn plugin nhúng như object/embed.
- `frame-ancestors 'none'`: không cho origin khác nhúng trang.
- `form-action 'self'`: chỉ cho form gửi tới cùng origin. Điều này phù hợp khi login và consent được xử lý trên cùng Authorization Server.
- `script-src 'self'`: chỉ cho script cùng origin chạy; không cho phép inline script hoặc `eval`.

Đây là policy khởi đầu, không phải chuỗi có thể áp dụng nguyên trạng cho mọi hệ thống. Nếu giao diện dùng CDN, font ngoài, analytics hoặc inline script/style, trình duyệt có thể chặn các tài nguyên đó. Ưu tiên chuyển script/style sang file tĩnh cùng origin. Nếu thực sự cần inline code, dùng nonce ngẫu nhiên theo từng response hoặc hash được tính từ nội dung cố định; tránh thêm `'unsafe-inline'` hay `'unsafe-eval'` chỉ để làm mất cảnh báo CSP.

Nên triển khai bằng `Content-Security-Policy-Report-Only` trước, thu thập vi phạm trong môi trường kiểm thử, sửa các nguồn hợp lệ còn thiếu rồi mới chuyển sang `Content-Security-Policy` để enforce. CSP giảm tác động của một số lỗi injection, nhưng không thay thế output encoding và kiểm soát XSS.

## 3. Cấu hình header cho các SecurityFilterChain

Một cấu hình Authorization Server điển hình có ít nhất hai chain:

1. Chain có `@Order(1)` và `securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())` xử lý protocol endpoint của Spring Authorization Server.
2. Chain có `@Order(2)` xử lý login page, consent page, logout và các request web còn lại.

`HeaderWriterFilter` thuộc từng chain. Hãy dùng một hàm cấu hình chung và gọi hàm đó trong cả hai chain để tránh policy khác nhau giữa response login, consent và protocol endpoint.

Ví dụ dưới đây dùng API Servlet của Spring Security và Spring Authorization Server 1.5.x. Nếu dự án đã chuyển sang Spring Security 7.x, Spring Authorization Server đã được tích hợp vào Spring Security; hãy đối chiếu phiên bản dependency và API tương ứng của dự án.

```java
package com.example.authorizationserver.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
                .oidc(Customizer.withDefaults())
                .authorizationEndpoint(endpoint -> endpoint
                    .consentPage("/oauth2/consent")
                )
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            );

        configureSecurityHeaders(http);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/css/**", "/images/**").permitAll()
                .requestMatchers("/oauth2/consent").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            );

        configureSecurityHeaders(http);
        return http.build();
    }

    private static void configureSecurityHeaders(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .frameOptions(frameOptions -> frameOptions.deny())
            .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(31_536_000)
                .includeSubDomains(false)
            )
            .contentSecurityPolicy(csp -> csp.policyDirectives(
                "default-src 'self'; " +
                "base-uri 'self'; " +
                "object-src 'none'; " +
                "frame-ancestors 'none'; " +
                "form-action 'self'; " +
                "img-src 'self' data:; " +
                "style-src 'self'; " +
                "script-src 'self'"
            ))
            .referrerPolicy(referrer -> referrer.policy(
                ReferrerPolicyHeaderWriter.ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN
            ))
            .permissionsPolicy(permissions -> permissions.policy(
                "camera=(), microphone=(), geolocation=()"
            ))
        );
    }
}
```

Trong ví dụ:

- Chain thứ nhất chỉ khớp các endpoint được Spring Authorization Server đăng ký. Header được thêm vào response của các endpoint đó.
- Chain thứ hai xử lý `/login` và `/oauth2/consent`. Trang consent yêu cầu người dùng đã đăng nhập; trang login và tài nguyên giao diện cần thiết được phép truy cập trước đăng nhập.
- Cả hai chain gọi `configureSecurityHeaders`, nên response từ hai vùng đều có cùng policy.
- Các header mặc định như cache control và `X-Content-Type-Options` vẫn được giữ. Không gọi `defaultsDisabled()` hoặc `headers.disable()` nếu chưa có kế hoạch thay thế đầy đủ các header mặc định.
- HSTS được cấu hình một năm và không mở rộng sang subdomain trong ví dụ. Hãy chỉ đổi `includeSubDomains(false)` thành `true` sau khi xác minh toàn bộ subdomain đã hỗ trợ HTTPS.
- `frameOptions().deny()` và CSP `frame-ancestors 'none'` cùng cấm nhúng. Nếu sản phẩm có yêu cầu nhúng cụ thể, hãy thiết kế lại hai chính sách đồng bộ.
- `Permissions-Policy` tắt camera, microphone và geolocation. Chỉ mở lại tính năng mà giao diện thực sự cần.

Nếu ứng dụng có chain thứ ba cho API, actuator hoặc một khu vực riêng, cần đánh giá và áp dụng header tương ứng trong chain đó. `permitAll()` chỉ quyết định quyền truy cập; nó không bỏ qua các filter trong chain và không tự thêm header cho request nằm ngoài chain.

### 3.1. Chuyển sang CSP Report-Only

Trong giai đoạn thử nghiệm, đổi cấu hình CSP thành:

```java
.contentSecurityPolicy(csp -> csp
    .policyDirectives(
        "default-src 'self'; base-uri 'self'; object-src 'none'; " +
        "frame-ancestors 'none'; form-action 'self'; " +
        "img-src 'self' data:; style-src 'self'; script-src 'self'"
    )
    .reportOnly()
)
```

Với `Report-Only`, trình duyệt ghi nhận hoặc gửi báo cáo vi phạm nhưng chưa chặn tài nguyên. Theo dõi console và endpoint nhận báo cáo nếu đã cấu hình, phân loại nguồn hợp lệ và nguồn không mong muốn, rồi mới bật policy enforce. Không đưa dữ liệu nhạy cảm hoặc token vào nội dung báo cáo tùy chỉnh.

## 4. Bảo vệ trang login

### 4.1. Phân quyền và CSRF

Trang `GET /login` cần truy cập được khi người dùng chưa đăng nhập để họ có thể bắt đầu quá trình xác thực. Tuy nhiên, endpoint xử lý đăng nhập `POST /login` phải nằm trong cơ chế form login của Spring Security và được bảo vệ bằng CSRF token. CSRF protection được bật mặc định cho các request thay đổi trạng thái trong cấu hình web thông thường.

Với Thymeleaf, form đăng nhập có thể được viết như sau:

```html
<form th:action="@{/login}" method="post">
    <label for="username">Tên đăng nhập</label>
    <input id="username" name="username" type="text"
           autocomplete="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <button type="submit">Đăng nhập</button>
</form>
```

Spring MVC tích hợp `RequestDataValueProcessor` để hỗ trợ đưa CSRF token vào form được render qua Spring MVC/Thymeleaf. Hãy kiểm tra HTML thực tế mà trình duyệt nhận được có hidden field `_csrf` hay chưa. Nếu form được tạo bằng HTML thuần hoặc không đi qua tích hợp đó, cần tự đưa token vào form:

```html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
```

Chỉ sử dụng một cơ chế chèn token để tránh hidden field bị lặp. Không tắt CSRF trên toàn bộ application chain để xử lý một lỗi form; hãy tìm đúng request matcher và cấu hình ngoại lệ hẹp khi có lý do kỹ thuật rõ ràng.

### 4.2. Nội dung và session

Trang login nên hiển thị lỗi xác thực chung, chẳng hạn “Tên đăng nhập hoặc mật khẩu không hợp lệ”, để tránh tiết lộ tài khoản nào tồn tại. Dùng `autocomplete="username"` và `autocomplete="current-password"` để hỗ trợ password manager. Không ghi mật khẩu, CSRF token hoặc session ID vào log, URL hay analytics.

Cookie session trong môi trường production cần có `Secure`, `HttpOnly` và `SameSite` phù hợp. `Secure` yêu cầu trình duyệt chỉ gửi cookie qua HTTPS; `HttpOnly` ngăn JavaScript đọc cookie; `SameSite` giảm việc cookie tự động được gửi trong một số request cross-site. `SameSite=Lax` thường phù hợp với điều hướng top-level phổ biến của OAuth/OIDC. Nếu triển khai `response_mode=form_post`, SSO hoặc logout có luồng cross-site đặc biệt, phải kiểm thử hành vi cookie và chỉ dùng `SameSite=None; Secure` khi flow thật sự cần.

Ví dụ cấu hình cookie session trong Spring Boot, đặt trong profile production:

```yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Không bật `secure: true` trong môi trường HTTP local mà không chuẩn bị HTTPS, vì trình duyệt sẽ không gửi cookie qua kết nối HTTP. Bảo đảm session fixation protection của Spring Security vẫn hoạt động và session ID được thay đổi sau khi xác thực thành công theo chiến lược session đang dùng.

## 5. Bảo vệ trang consent

Consent là một quyết định cấp quyền. Người dùng cần biết ứng dụng nào đang yêu cầu quyền, những scope nào được yêu cầu, dữ liệu hoặc hành động nào tương ứng với từng scope và lựa chọn của họ sẽ được lưu như thế nào. Một trang consent khó hiểu có thể khiến người dùng chấp thuận quyền quá rộng dù cơ chế kỹ thuật vẫn hoạt động.

### 5.1. Luồng consent của Spring Authorization Server

Khi bật consent page tùy chỉnh bằng `authorizationEndpoint(endpoint -> endpoint.consentPage("/oauth2/consent"))`, Spring Authorization Server chuyển trình duyệt tới trang đó khi authorization request cần người dùng cấp consent. Query string của trang consent chứa:

- `client_id`: định danh client đang yêu cầu quyền.
- `scope`: danh sách scope được yêu cầu, phân tách bằng dấu cách.
- `state`: token bảo vệ CSRF của authorization flow do Spring Authorization Server tạo.

Trang consent tùy chỉnh cần tạo form `HTTP POST` gửi tới authorization endpoint được cấu hình trong `AuthorizationServerSettings`. Form phải gửi lại `client_id`, `state` và các `scope` mà người dùng chấp thuận. Ví dụ dưới đây giả định authorization endpoint mặc định là `/oauth2/authorize`.

`state` ở đây là token của consent flow trong Spring Authorization Server. Nó có vai trò chống CSRF cho thao tác cấp quyền và phải được giữ nguyên từ query string đến form POST. Không tự tạo giá trị mới, không bỏ qua và không thay nó bằng `_csrf` của Spring Security. Hai token phục vụ hai cơ chế và hai luồng khác nhau.

Spring Authorization Server tự cấu hình CSRF matcher để bỏ qua kiểm tra CSRF chung của `CsrfFilter` đối với các protocol endpoint thuộc `getEndpointsMatcher()`. Authorization endpoint sẽ xác thực `state` theo cơ chế của authorization flow. Trang login vẫn đi qua application chain và vẫn cần CSRF token của Spring Security. Nếu bạn thêm custom POST endpoint bên ngoài matcher của Spring Authorization Server, endpoint đó phải có CSRF policy riêng phù hợp.

### 5.2. Render thông tin client và scope an toàn

Controller xử lý `GET /oauth2/consent` nên:

1. Đọc `client_id`, `scope` và `state` từ request đã được framework parse.
2. Tra cứu client từ `RegisteredClientRepository` bằng `client_id` để lấy tên ứng dụng và thông tin đã đăng ký. Không tin một tên ứng dụng hoặc logo tùy ý do trình duyệt gửi lên.
3. Chuyển từng scope thành mô tả dễ hiểu do Authorization Server quản lý. Không hiển thị nguyên HTML do client hoặc người dùng cung cấp.
4. Đưa `client_id`, `state` và danh sách scope vào model để template render bằng cơ chế auto-escaping.
5. Yêu cầu người dùng chọn rõ scope muốn cấp. Không tự đánh dấu những scope nhạy cảm là đã chấp thuận nếu thiết kế sản phẩm yêu cầu hành động chủ động.

Ví dụ controller minh họa cách lấy thông tin client và chuẩn bị model:

```java
@Controller
public class ConsentController {

    private final RegisteredClientRepository registeredClientRepository;

    public ConsentController(RegisteredClientRepository registeredClientRepository) {
        this.registeredClientRepository = registeredClientRepository;
    }

    @GetMapping("/oauth2/consent")
    public String consent(
            @RequestParam("client_id") String clientId,
            @RequestParam(value = "scope", required = false) String requestedScopes,
            @RequestParam("state") String state,
            Model model) {

        RegisteredClient client = registeredClientRepository.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        String displayName = client.getClientName() != null
                ? client.getClientName()
                : client.getClientId();

        List<String> scopes = requestedScopes == null || requestedScopes.isBlank()
                ? List.of()
                : Arrays.stream(requestedScopes.split("\\s+"))
                    .filter(scope -> !scope.isBlank())
                    .toList();

        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("clientName", displayName);
        model.addAttribute("state", state);
        model.addAttribute("scopes", scopes);
        return "consent";
    }
}
```

Các import cần thiết cho ví dụ controller gồm `java.util.Arrays`, `java.util.List`, `org.springframework.security.oauth2.server.authorization.client.RegisteredClient`, `RegisteredClientRepository`, `org.springframework.stereotype.Controller`, `org.springframework.ui.Model`, `org.springframework.web.bind.annotation.GetMapping`, `RequestParam` và `org.springframework.web.server.ResponseStatusException`, `org.springframework.http.HttpStatus`. Bổ sung các import này trong lớp thực tế.

Template `consent.html` có thể tạo form như sau:

```html
<h1>Cho phép ứng dụng truy cập?</h1>
<p>Ứng dụng: <strong th:text="${clientName}">Tên ứng dụng</strong></p>
<p>Ứng dụng yêu cầu các quyền sau:</p>

<form th:action="@{/oauth2/authorize}" method="post">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <div th:each="scope : ${scopes}">
        <label>
            <input type="checkbox" name="scope"
                   th:value="${scope}" checked>
            <span th:text="${scope}">Mô tả quyền</span>
        </label>
    </div>

    <button type="submit">Cho phép</button>
</form>
```

`th:text` và `th:value` giúp encode dữ liệu khi render vào HTML. Tránh `th:utext` cho tên client, mô tả scope hoặc dữ liệu request. Trong sản phẩm thực tế, hãy dùng bảng ánh xạ scope sang mô tả dễ hiểu, ví dụ `profile` là “Xem thông tin hồ sơ cơ bản”, thay vì yêu cầu người dùng hiểu tên kỹ thuật. Hiển thị tên client đã đăng ký và domain/nhà phát hành đã được xác minh nếu hệ thống có thông tin đó.

Form trên gửi mỗi scope được chọn thành một HTTP parameter `scope`. Các giá trị được gửi phải là những scope đã có trong authorization request ban đầu. `client_id` và `state` phải được gửi lại chính xác. Nếu người dùng từ chối consent, hãy triển khai hành vi từ chối theo contract của phiên bản Spring Authorization Server đang dùng và kiểm thử response OAuth2 tương ứng; không giả lập việc từ chối bằng cách sửa `state` hoặc redirect tùy ý.

### 5.3. Giảm rò rỉ dữ liệu trên trang consent

Trang consent thường nhận `client_id`, `scope` và `state` trong query string. Vì vậy:

- Không tải analytics, quảng cáo, font hoặc script bên thứ ba trên trang login/consent nếu không có yêu cầu rõ ràng. Tài nguyên ngoài có thể nhận metadata request và tạo thêm nơi dữ liệu bị lộ.
- Đặt Referrer Policy phù hợp. `strict-origin-when-cross-origin` chỉ gửi origin khi request đi cross-origin; `no-referrer` chặt hơn nếu trang có query string nhạy cảm và không cần referrer.
- Giữ cache control `no-store` cho response login/consent và không lưu nội dung các trang này vào service worker cache.
- Không ghi toàn bộ query string của consent URL, `state`, authorization code hoặc session ID vào application log, reverse proxy access log hay telemetry nếu không có cơ chế che dữ liệu.
- Không hiển thị nội dung do client cung cấp như HTML. Dùng allowlist cho logo hoặc metadata đã được quản trị và kiểm tra.

## 6. Kiểm tra và xác minh

Kiểm tra cần bao phủ cả hai filter chain và luồng OAuth thực tế. Chỉ kiểm tra trang login là chưa đủ, vì protocol endpoint có thể nằm trong chain khác.

### 6.1. Kiểm tra bằng MockMvc

Ví dụ kiểm tra header của trang login trên HTTPS:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPageContainsSecurityHeaders() throws Exception {
        mockMvc.perform(get("/login").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string("Strict-Transport-Security",
                    containsString("max-age=31536000")))
            .andExpect(header().string("Content-Security-Policy",
                    containsString("frame-ancestors 'none'")))
            .andExpect(header().string("Permissions-Policy",
                    containsString("camera=()")));
    }
}
```

Đoạn test giả định `GET /login` trả `200 OK` từ controller và template login tùy chỉnh. Nếu endpoint của bạn chuyển hướng hoặc dùng trang login mặc định được sinh tự động, điều chỉnh status assertion theo response thực tế.

Thực hiện kiểm tra tương tự với trang consent đã đăng nhập. Để xác minh header trên authorization endpoint, chạy một authorization request hợp lệ qua flow test của Spring Authorization Server và kiểm tra response/redirect từ chain thứ nhất. Test integration cần một `RegisteredClient` phù hợp, redirect URI đã đăng ký và user đã xác thực; một request thiếu tham số OAuth2 có thể trả lỗi protocol nhưng vẫn có thể dùng để kiểm tra header nếu response được tạo trong đúng chain.

### 6.2. Kiểm tra bằng curl và trình duyệt

Gọi trang login qua HTTPS:

```bash
curl -sS -D - -o /dev/null https://auth.example.com/login
```

Kiểm tra các header sau có mặt và đúng giá trị:

- `Cache-Control` chứa `no-store` cho trang nhạy cảm.
- `X-Content-Type-Options` là `nosniff`.
- `X-Frame-Options` phù hợp với `frame-ancestors`.
- `Strict-Transport-Security` chỉ xuất hiện trên HTTPS response.
- `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only` có policy dự kiến.
- `Referrer-Policy` và `Permissions-Policy` có giá trị phù hợp.

Trong DevTools của trình duyệt, mở tab Network và kiểm tra response của `GET /login`, `GET /oauth2/consent` và authorization endpoint. Tab Console giúp phát hiện tài nguyên bị CSP chặn. Thử mở trang login/consent từ một trang HTML khác bằng iframe để xác minh chính sách chống clickjacking. Kiểm tra HTML được render để xác nhận form login có CSRF token và consent form có đúng `client_id`, `state` cùng các scope đã chọn.

### 6.3. Kiểm thử các tình huống bảo mật

| Tình huống | Kết quả mong đợi |
|---|---|
| Truy cập login qua HTTPS | Response có bộ header bảo mật, cache control không lưu trang nhạy cảm. |
| Truy cập authorization endpoint | Header được áp dụng bởi authorization-server filter chain. |
| Truy cập consent khi chưa đăng nhập | Luồng xác thực chuyển người dùng tới login theo cấu hình. |
| Login POST thiếu hoặc sai CSRF token | Request bị từ chối bởi CSRF protection của Spring Security. |
| Consent POST thiếu hoặc sửa `state` | Spring Authorization Server từ chối authorization/consent request. |
| Consent POST thay đổi `client_id` hoặc gửi scope ngoài yêu cầu ban đầu | Authorization flow không được cấp quyền vượt quá request hợp lệ. |
| Trang login/consent bị nhúng vào iframe | Trình duyệt chặn theo X-Frame-Options/CSP đã cấu hình. |
| Tài nguyên ngoài không nằm trong CSP | Bị chặn khi enforce; được ghi nhận khi chạy Report-Only. |
| Đăng xuất rồi bấm Back | Trình duyệt không hiển thị lại nội dung nhạy cảm từ HTTP cache. |

## 7. Lỗi cấu hình thường gặp

### Chỉ thêm header vào một filter chain

**Triệu chứng:** Trang login có CSP và HSTS nhưng response từ protocol endpoint thiếu header, hoặc ngược lại.

**Nguyên nhân:** Các chain có request matcher và thứ tự riêng. Request được xử lý bởi chain đầu tiên khớp; cấu hình trong chain khác không tự động áp dụng.

**Cách xử lý:** Đặt cấu hình header trong hàm dùng chung và gọi từ mọi chain có liên quan. Kiểm tra chain bằng request thực tế thay vì chỉ đọc cấu hình Java.

### CSP chặn CSS hoặc JavaScript của login page

**Triệu chứng:** Trang login không có style, nút không hoạt động hoặc Console báo vi phạm `script-src`/`style-src`.

**Nguyên nhân:** Policy chỉ cho phép `'self'`, trong khi template đang dùng CDN hoặc inline code.

**Cách xử lý:** Chuyển tài nguyên về origin của ứng dụng, hoặc khai báo allowlist hẹp cho origin đã kiểm soát. Với inline code cần nonce/hash. Chạy Report-Only trước khi enforce và không thêm `'unsafe-inline'` một cách tùy tiện.

### HSTS không xuất hiện sau reverse proxy

**Triệu chứng:** Người dùng truy cập HTTPS nhưng response từ ứng dụng không có `Strict-Transport-Security`.

**Nguyên nhân:** TLS kết thúc ở proxy, còn ứng dụng nhìn thấy request HTTP và không nhận diện scheme gốc.

**Cách xử lý:** Cấu hình forwarded-header handling đúng với hạ tầng, chỉ tin header từ proxy được kiểm soát và bảo đảm proxy loại bỏ forwarded header do client gửi.

### Consent form báo lỗi hoặc không hoàn tất authorization

**Triệu chứng:** Người dùng bấm Cho phép nhưng server trả lỗi request, consent không được lưu hoặc flow không quay về client.

**Nguyên nhân:** Form không gửi POST tới authorization endpoint, thiếu `client_id`, mất `state`, hoặc gửi scope không nằm trong authorization request.

**Cách xử lý:** Kiểm tra query string mà Spring Authorization Server gửi tới consent page và payload form POST. Giữ nguyên `state`, gửi lại đúng client ID và chỉ gửi các scope người dùng chấp thuận. Không thay `state` bằng CSRF token của login form.

### Tắt toàn bộ CSRF để xử lý lỗi form

**Triệu chứng:** Login form hoạt động sau khi tắt CSRF nhưng các endpoint web khác dễ bị CSRF.

**Nguyên nhân:** Cấu hình đã loại bỏ lớp bảo vệ cho mọi request thay đổi trạng thái.

**Cách xử lý:** Giữ CSRF cho login và các form ứng dụng. Spring Authorization Server tự cấu hình matcher để xử lý CSRF cho protocol endpoint của nó; custom endpoint nằm ngoài matcher phải có chính sách riêng và được kiểm thử.

### HSTS `includeSubDomains` gây gián đoạn dịch vụ

**Triệu chứng:** Một subdomain cũ chỉ hỗ trợ HTTP không còn truy cập được sau khi trình duyệt ghi nhớ HSTS.

**Nguyên nhân:** Header áp dụng chính sách HTTPS cho cả subdomain.

**Cách xử lý:** Chỉ bật `includeSubDomains` sau khi kiểm kê và triển khai TLS cho mọi subdomain. HSTS được trình duyệt lưu theo `max-age`, nên việc sửa cấu hình server không lập tức xóa chính sách đã được trình duyệt ghi nhớ.

## 8. Quy trình triển khai đề xuất

1. Liệt kê toàn bộ `SecurityFilterChain`, request matcher và endpoint giao diện/protocol mà mỗi chain xử lý.
2. Giữ các header mặc định của Spring Security; xác nhận cache control và `X-Content-Type-Options` hoạt động.
3. Chốt HTTPS, reverse proxy và phạm vi HSTS trước khi bật `includeSubDomains` hoặc preload.
4. Xây CSP cho login/consent dựa trên tài nguyên thực tế, bắt đầu ở chế độ Report-Only.
5. Áp dụng header policy cho mọi chain liên quan bằng hàm cấu hình chung.
6. Rà soát login form, CSRF token, session cookie, consent form, `client_id`, `state` và danh sách scope.
7. Chạy integration test, kiểm tra response headers bằng `curl`, kiểm tra CSP trong browser và diễn tập toàn bộ authorization-code flow.
8. Chuyển CSP sang enforce sau khi các vi phạm hợp lệ đã được xử lý; tiếp tục theo dõi sau mỗi lần thay đổi template hoặc tài nguyên frontend.

## 9. Kết luận

Security headers giúp trình duyệt xử lý response an toàn hơn; login và consent cần thêm kiểm soát về session, CSRF, nội dung hiển thị và dữ liệu được gửi qua form. Với Spring Authorization Server, cần nhớ cấu hình headers ở từng filter chain, giữ CSRF cho form đăng nhập và round-trip `state` của consent flow đúng theo contract của authorization endpoint. Hãy kiểm tra cả response headers lẫn hành vi của một authorization request hoàn chỉnh trước khi đưa policy vào production.

## Tài liệu tham khảo

1. [Spring Security Reference — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
2. [Spring Security Reference — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
3. [Spring Authorization Server Reference — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html)
4. [Spring Authorization Server Reference — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
5. [Spring Authorization Server API — OAuth2AuthorizationEndpointConfigurer.consentPage](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html)
6. [OWASP Cheat Sheet — HTTP Headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
7. [OWASP Cheat Sheet — Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html)
8. [OWASP Cheat Sheet — Content Security Policy](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
9. [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797)
10. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
