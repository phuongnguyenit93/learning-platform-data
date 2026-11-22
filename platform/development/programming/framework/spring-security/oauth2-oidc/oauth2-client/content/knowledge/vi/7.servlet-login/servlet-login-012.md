# 7.12. SecurityMatcher, nhiều filter chain và lựa chọn chain cho callback

## 1. Vì sao callback OAuth2 Login cần đúng SecurityFilterChain?

Trong ứng dụng Spring Security Servlet, đường dẫn đăng nhập OAuth 2.0/OIDC thường không được xử lý trực tiếp bằng một controller tự viết. Spring Security đăng ký các **security filter**, trong đó có filter tạo authorization request và filter tiếp nhận authorization response chứa <code>code</code> và <code>state</code> tại callback.

Khi ứng dụng chỉ có một <code>SecurityFilterChain</code> áp dụng cho mọi request, việc định tuyến tới các filter này tương đối đơn giản. Nhưng trong ứng dụng thực tế, ta thường tách cấu hình bảo mật theo vùng:

- <code>/api/**</code>: API xác thực bằng bearer token, có thể không sử dụng HTTP session.
- <code>/admin/**</code>: trang quản trị yêu cầu chính sách riêng.
- <code>/app/**</code>: giao diện web đăng nhập qua OAuth2/OIDC, sử dụng session.
- <code>/oauth2/authorization/{registrationId}</code>: endpoint khởi tạo đăng nhập OAuth2.
- <code>/login/oauth2/code/{registrationId}</code>: endpoint nhận callback sau khi nhà cung cấp cấp authorization code.

Lúc này, một câu hỏi có tính quyết định là: **request callback thuộc filter chain nào?** Nếu callback đi vào chain không có <code>OAuth2LoginAuthenticationFilter</code>, Spring Security sẽ không xử lý authorization code như mong muốn, dù application đã có một chain khác bật <code>oauth2Login()</code>.

Ví dụ hiện tượng:

1. Người dùng vào <code>/app/dashboard</code> và được chuyển tới OpenID Provider.
2. Người dùng đăng nhập thành công tại provider.
3. Provider redirect về <code>/login/oauth2/code/company?code=...&amp;state=...</code>.
4. Ứng dụng trả 404, 401, 403, điều hướng lặp lại trang login hoặc không tạo authentication.

Một nguyên nhân thường gặp là **<code>FilterChainProxy</code> đã chọn chain sai hoặc không có chain nào khớp callback**, vì các <code>securityMatcher</code> được cấu hình quá hẹp hoặc thứ tự chain không phù hợp.

> **Nguyên tắc chính:** <code>FilterChainProxy</code> chọn **filter chain khớp đầu tiên** theo thứ tự đã đăng ký. Không có cơ chế tự thử tiếp chain thứ hai khi filter của chain đầu không xử lý callback.

## 2. Kiến trúc FilterChainProxy và cách chọn chain

<code>DelegatingFilterProxy</code> nối servlet filter của ứng dụng với Spring Security. Bên trong, <code>FilterChainProxy</code> chứa danh sách các <code>SecurityFilterChain</code>. Mỗi chain có một <code>RequestMatcher</code> và các security filter tương ứng.

Khi request đi vào:

1. <code>FilterChainProxy</code> kiểm tra request với matcher của chain có độ ưu tiên cao nhất.
2. Nếu khớp, nó chạy danh sách filter của chain đó.
3. Nếu không khớp, nó kiểm tra chain tiếp theo.
4. Ngay khi gặp **chain đầu tiên khớp**, việc lựa chọn kết thúc.
5. Nếu không chain nào khớp, request không được bảo vệ bởi các Spring Security filter chain trong danh sách này.

~~~mermaid
flowchart TD
    R["HTTP Request"] --> P["FilterChainProxy"]
    P --> A{"Chain @Order(1) match?"}
    A -->|Có| F1["Chỉ chạy filter của chain 1"]
    A -->|Không| B{"Chain @Order(2) match?"}
    B -->|Có| F2["Chỉ chạy filter của chain 2"]
    B -->|Không| C{"Chain fallback match?"}
    C -->|Có| F3["Chạy filter fallback"]
    C -->|Không| N["Không có Spring Security chain phù hợp"]
    F1 --> X["Không thử chain kế tiếp"]
    F2 --> X
    F3 --> X
~~~

Một chain có thể bật <code>oauth2Login()</code>; chain khác chỉ bật JWT bearer hoặc HTTP Basic. **Chọn chain** quyết định filter nào tồn tại đối với request đó. Quy tắc <code>authorizeHttpRequests</code> của một chain khác không thể bù cho filter bị thiếu.

### 2.1. Vai trò của @Order

Khi định nghĩa nhiều bean <code>SecurityFilterChain</code>, Spring Security cần thứ tự rõ ràng:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    // matcher cụ thể cho API
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // chain cho web và OAuth2 Login
    return http.build();
}
~~~

Giá trị <code>@Order</code> **càng nhỏ càng được xét sớm**. Vì thuật toán chọn chain dừng tại match đầu tiên, hãy đặt matcher hẹp trước matcher rộng; một chain không cấu hình <code>securityMatcher</code> thường là chain bao phủ tất cả request còn lại và nên đặt sau các chain đặc thù.

Đừng dựa vào thứ tự khai báo method trong file Java hoặc tên bean để quyết định ưu tiên. Khi có nhiều chain trùng phạm vi, thứ tự là một phần quan trọng của thiết kế bảo mật.

## 3. SecurityMatcher khác requestMatchers như thế nào?

Hai API có tên tương tự nhưng hoạt động ở **hai tầng khác nhau**.

| Cấu hình | Tầng thực thi | Câu hỏi được trả lời |
|---|---|---|
| <code>http.securityMatcher(...)</code> | Chọn <code>SecurityFilterChain</code> trong <code>FilterChainProxy</code> | Request này **đi vào chain nào**? |
| <code>authorizeHttpRequests(auth -&gt; auth.requestMatchers(...))</code> | Quy tắc authorization **bên trong chain đã chọn** | Người dùng/request có được phép truy cập URL này không? |
| <code>authorizeHttpRequests(auth -&gt; auth.anyRequest()...)</code> | Quy tắc authorization cuối trong chain | Với request thuộc chain này mà chưa khớp quy tắc trước, quyết định gì? |

Ví dụ:

~~~java
http
    .securityMatcher("/app/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/app/public/**").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

Ở đây:

- Chain chỉ được xét là phù hợp với URL <code>/app/**</code>.
- Trong phạm vi đó, <code>/app/public/**</code> được phép truy cập không cần authentication.
- Các URL <code>/app/**</code> khác phải được xác thực.
- URL <code>/login/oauth2/code/company</code> **nằm ngoài phạm vi chain**, nên callback mặc định không được <code>OAuth2LoginAuthenticationFilter</code> trong chain này xử lý.

Ngay cả khi bổ sung:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login/oauth2/code/**").permitAll()
    .anyRequest().authenticated())
~~~

thì vấn đề **vẫn còn**: security matcher của chain đã loại callback trước khi tới bước authorization. Chỉ sửa <code>requestMatchers(...).permitAll()</code> không khiến URL được route vào chain.

> <code>permitAll()</code> là quyết định authorization. Nó không định tuyến request sang chain khác và cũng không tự tạo OAuth2 Login filter.

### 3.1. Matcher đánh giá phần nào của URL?

Thông thường matcher đường dẫn của Spring Security xét **request path phía ứng dụng** (phụ thuộc servlet mapping và loại matcher), không lấy cả protocol, host hay query string để so khớp literal pattern.

Ví dụ callback:

~~~text
GET /login/oauth2/code/company?code=abc123&state=xyz456
~~~

Matcher đường dẫn <code>/login/oauth2/code/**</code> dựa vào path <code>/login/oauth2/code/company</code>; tham số <code>code</code> và <code>state</code> được filter xử lý sau khi chain được chọn. Nếu ứng dụng deploy dưới context path như <code>/portal</code>, việc match pattern còn chịu quy tắc của servlet/context path; đừng tự cộng context path vào pattern mà không kiểm tra matcher thực tế.

Các phiên bản Spring Security và môi trường MVC có thể dùng cơ chế matcher khác nhau, chẳng hạn MVC-aware matcher hoặc PathPattern-based matcher. Để kết quả nhất quán, nên dùng các pattern đơn giản, kiểm tra request path thật, và sử dụng API RequestMatcher phù hợp với phiên bản đang triển khai.

## 4. Những endpoint OAuth2 Login Servlet mặc định

Khi bật:

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

Spring Security cấu hình các thành phần của OAuth2/OIDC Login trong **chính chain hiện tại**.

| Endpoint mặc định | Thành phần liên quan | Chức năng |
|---|---|---|
| <code>GET /oauth2/authorization/{registrationId}</code> | <code>OAuth2AuthorizationRequestRedirectFilter</code> | Tìm ClientRegistration, tạo authorization request và redirect trình duyệt tới Authorization Server |
| <code>/login/oauth2/code/{registrationId}</code> | <code>OAuth2LoginAuthenticationFilter</code> | Nhận authorization response tại callback, đối chiếu state và thực hiện token exchange |
| <code>/login</code> | Trang đăng nhập mặc định được tạo khi điều kiện phù hợp, hoặc trang login do ứng dụng cung cấp | Cho người dùng chọn phương thức đăng nhập |
| <code>/login?error</code> | Trang đăng nhập/đường dẫn xử lý thất bại tùy cấu hình | Thể hiện kết quả xác thực thất bại |

Các hằng/API quan trọng của framework:

~~~java
OAuth2AuthorizationRequestRedirectFilter.DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
// "/oauth2/authorization"

OAuth2LoginAuthenticationFilter.DEFAULT_FILTER_PROCESSES_URI
// "/login/oauth2/code/*"
~~~

<code>DEFAULT_FILTER_PROCESSES_URI</code> là **pattern** xử lý callback của filter; ví dụ redirect URI thực tế sau khi thay template là <code>/login/oauth2/code/company</code>. Giá trị <code>registrationId</code> phải tương ứng với ClientRegistration do ứng dụng cấu hình.

Thông thường redirect URI của Client được khai báo:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Và URL thực tế được đăng ký tại provider, ví dụ:

~~~text
https://app.example.org/login/oauth2/code/company
~~~

Lưu ý có **ba lớp cấu hình phải khớp nhau**:

1. <code>ClientRegistration.redirectUri</code> tạo URL gửi lên nhà cung cấp.
2. Provider đăng ký/chấp nhận chính xác callback URL.
3. <code>OAuth2LoginAuthenticationFilter</code> trong **chain được chọn** nhận path callback tương ứng.

Một URL được provider cho phép nhưng nằm ngoài mọi chain có OAuth2 Login filter vẫn không hoàn tất đăng nhập.

## 5. Cách thiết kế dễ hiểu: API chain trước, Web chain làm fallback

Khi ứng dụng có API dùng JWT và web giao diện đăng nhập OIDC, cách phổ biến là:

- Chain 1: chỉ nhận <code>/api/**</code>, dùng OAuth2 Resource Server JWT cho API.
- Chain 2: nhận mọi request còn lại, bật <code>oauth2Login()</code> cho web; nhờ vậy cả authorization start URL và callback mặc định đều rơi vào chain này.

### 5.1. Cấu hình Java hoàn chỉnh

Ví dụ Spring Boot 3 / Spring Security 6:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        // Không gọi securityMatcher: webChain nhận mọi request còn lại.
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đoạn cấu hình này minh họa **hai vai trò**: API JWT Resource Server và web OAuth2 Client. Để chạy phần API, cần <code>spring-boot-starter-oauth2-resource-server</code> cùng cấu hình <code>JwtDecoder</code> hoặc thuộc tính <code>spring.security.oauth2.resourceserver.jwt.issuer-uri</code> phù hợp. Để chạy web OIDC cần <code>spring-boot-starter-oauth2-client</code> và một <code>ClientRegistration</code> hợp lệ. Hai issuer liên quan có thể giống nhau nếu cùng nhà cung cấp, nhưng hai loại cấu hình phục vụ nhiệm vụ khác nhau.

Ví dụ <code>application.yml</code> khi cùng issuer xác thực API JWT và web OIDC:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/company
      client:
        registration:
          company:
            provider: company
            client-id: web-app
            client-secret: replace-with-secret-from-secure-configuration
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Các URL và credential ở đây là placeholder. Trong ứng dụng thật, client secret phải lấy từ secret store hoặc biến môi trường; không lưu secret thật trong source repository.

Trong ví dụ này, từng request được chọn như sau:

| Request | Chain đầu tiên khớp | Kết quả chính |
|---|---|---|
| <code>GET /api/orders</code> | <code>@Order(1)</code> API | Kiểm tra bearer token bằng resource-server JWT |
| <code>GET /</code> | <code>@Order(2)</code> Web | Truy cập công khai |
| <code>GET /dashboard</code> | <code>@Order(2)</code> Web | Yêu cầu authentication; có thể khởi động login |
| <code>GET /oauth2/authorization/company</code> | <code>@Order(2)</code> Web | Authorization redirect filter xử lý |
| <code>GET /login/oauth2/code/company?code=...&amp;state=...</code> | <code>@Order(2)</code> Web | OAuth2 Login callback filter xử lý |

Điểm thiết kế quan trọng là chain API **không bao trùm callback**; web chain được đặt sau và không giới hạn matcher nên có thể nhận các URL hỗ trợ đăng nhập nằm ngoài <code>/dashboard</code>.

### 5.2. Vì sao không đặt catch-all trước?

Nếu đảo thứ tự:

~~~java
@Order(1) // web chain không giới hạn matcher
@Order(2) // api chain securityMatcher("/api/**")
~~~

thì web chain sẽ khớp **mọi** request trước; API chain gần như không bao giờ được chọn. Điều này có thể vô tình khiến API bị xử lý theo login/session thay vì chính sách JWT như thiết kế. Vì vậy phải đặt **chain đặc thù trước, fallback sau**.

### 5.3. Lưu ý về CSRF và session

Trong ví dụ, chỉ chain API không sử dụng browser session và được cấu hình tắt CSRF. Web chain vẫn giữ CSRF mặc định vì nó sử dụng session/cookie và có các request thay đổi trạng thái. Đừng tắt CSRF toàn ứng dụng chỉ vì một số API bearer-token cần chính sách khác.

OAuth2 Login của Servlet thường lưu authorization request và <code>state</code> trong HTTP session, qua <code>HttpSessionOAuth2AuthorizationRequestRepository</code> mặc định. Web chain cần giữ cookie/session đúng lúc người dùng rời ứng dụng tới OP rồi quay về callback. Nếu callback bị bắt bởi một chain stateless không có OAuth2 Login, cả filter lẫn cơ chế truy xuất authorization request có thể không phù hợp.

## 6. Khi web chain cũng có securityMatcher: phải bao gồm callback

Một số hệ thống yêu cầu mỗi vùng ứng dụng có chain riêng, thay vì dùng web fallback rộng. Khi đó phải đưa **mọi URL liên quan đến OAuth2 Login** vào security matcher của đúng chain.

Ví dụ cấu hình ba chain:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ScopedSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain oidcWebChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                "/", "/app", "/app/**",
                "/login", "/login/**",
                "/oauth2/authorization/**",
                "/assets/**", "/error")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error",
                    "/assets/**", "/oauth2/authorization/**",
                    "/login/oauth2/code/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
~~~

Ở chain web:

- <code>/app</code>, <code>/app/**</code> là các trang ứng dụng cần đăng nhập.
- <code>/oauth2/authorization/**</code> để filter bắt đầu OAuth2 Login được gọi.
- <code>/login</code> và <code>/login/**</code> bao phủ trang login, đường dẫn lỗi và **<code>/login/oauth2/code/{registrationId}</code> callback**.
- <code>/assets/**</code>, <code>/error</code> phục vụ trang đăng nhập và lỗi.
- Chain fallback xử lý những request chưa khớp; tránh để request nằm ngoài Spring Security mà không có chính sách.

Ví dụ web chain dùng <code>/login/**</code> nên callback đã nằm trong phạm vi. Nếu muốn tách chính xác hơn, có thể liệt kê cả <code>/login/oauth2/code/**</code> trong <code>securityMatcher</code>. Điểm quan trọng là **vùng match của chain** phải bao gồm callback trước khi xét authorization.

Tương tự, nếu có trang login tùy biến tại <code>/signin</code> hoặc URL logout, assets, CSS, API phụ cho trang login, chúng phải được xét trong thiết kế chain và authorization để tránh redirect loop hoặc 404.

Nếu chỉ có web chain với <code>securityMatcher("/app/**")</code> và không có fallback xử lý login endpoints, callback có thể không thuộc bất kỳ chain nào. Khi đó filter tiếp nhận callback không chạy dù provider chuyển hướng tới URL hợp lệ.

## 7. Tùy biến đường dẫn callback: đồng bộ cả ba phía

Mặc định callback là <code>/login/oauth2/code/{registrationId}</code>. Đôi khi ứng dụng cần một đường dẫn riêng, ví dụ:

~~~text
/signin/oauth2/callback/{registrationId}
~~~

Muốn đổi callback, cần đồng bộ:

1. **Địa chỉ redirect URI** mà Client gửi cho Authorization Server.
2. **Endpoint processing matcher** của <code>OAuth2LoginAuthenticationFilter</code>.
3. **SecurityMatcher của chain** chứa OAuth2 Login filter.
4. Cấu hình **allowed redirect URIs** tại Authorization Server/IdP.

### 7.1. Cấu hình redirectionEndpoint().baseUri()

Ví dụ:

~~~java
@Bean
@Order(2)
SecurityFilterChain oidcWebChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher(
            "/", "/app/**", "/login", "/signin",
            "/signin/oauth2/callback/**",
            "/oauth2/authorization/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/", "/login", "/signin",
                "/oauth2/authorization/**",
                "/signin/oauth2/callback/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .redirectionEndpoint(redirect -> redirect
                .baseUri("/signin/oauth2/callback/*")));

    return http.build();
}
~~~

Đoạn trên là **cấu hình thay thế** cho web chain ở các ví dụ trước; các phần khác của ứng dụng như API/fallback chain có thể giữ nguyên. Với mẫu này, <code>redirectionEndpoint().baseUri()</code> dùng pattern <code>/*</code> để match một đoạn <code>registrationId</code> trong callback; còn <code>securityMatcher</code> có thể bao quát URL bằng <code>/**</code>. Các pattern thực tế cần phù hợp phiên bản và loại RequestMatcher trong ứng dụng.

Tương ứng, trong ClientRegistration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: web-app
            client-secret: replace-with-secret-from-secure-configuration
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/signin/oauth2/callback/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Và provider phải cho phép callback thực tế, ví dụ:

~~~text
https://app.example.org/signin/oauth2/callback/company
~~~

Nếu chỉ đổi <code>redirect-uri</code> ở YAML, provider sẽ redirect về URL mới nhưng OAuth2 Login filter vẫn mặc định chờ <code>/login/oauth2/code/*</code>. Nếu chỉ đổi <code>redirectionEndpoint().baseUri()</code>, provider vẫn có thể redirect về URL cũ. Nếu đồng bộ hai phần đó nhưng quên <code>securityMatcher</code>, callback vẫn không vào đúng chain. **Cả ba điểm trên và registration tại IdP đều phải nhất quán.**

### 7.2. Thay authorizationEndpoint().baseUri()

Endpoint khởi tạo đăng nhập cũng có thể tùy biến:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .baseUri("/sso/start")))
~~~

Khi đó URL bắt đầu login thường là:

~~~text
/sso/start/{registrationId}
~~~

Nếu web chain có giới hạn matcher, cần bao gồm <code>/sso/start/**</code> thay cho <code>/oauth2/authorization/**</code> hoặc thêm cả hai tùy chiến lược chuyển đổi. Tùy biến authorization base URI **khác** tùy biến callback base URI: một endpoint khởi tạo flow, endpoint còn lại tiếp nhận kết quả.

Khi sử dụng trang login tùy biến, các link đăng nhập phải dẫn đúng authorization base URI mới. Trang login là một endpoint do ứng dụng hiển thị, trong khi filter xử lý redirect sang provider theo quy tắc riêng.

## 8. Hai chain cùng khớp callback: vì sao @Order quan trọng?

Xét cấu hình sai sau:

~~~java
@Bean
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/login/**", "/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain oidcChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/app/**", "/login/oauth2/code/**",
                         "/oauth2/authorization/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Callback <code>/login/oauth2/code/company</code> **khớp cả hai** matcher:

- Chain <code>@Order(1)</code> khớp <code>/login/**</code> trước.
- Chain <code>@Order(2)</code> dù có <code>oauth2Login()</code> cũng **không được thử**.
- Chain đầu chỉ có HTTP Basic và các filter tương ứng, nên không có OAuth2 Login callback processing.

Sửa bằng cách **thu hẹp chain thứ nhất** chỉ còn các đường dẫn thực sự thuộc HTTP Basic/API, hoặc thiết kế lại namespace để callback thuộc duy nhất chain web mong muốn. Chỉ đẩy <code>oidcChain</code> lên trước đôi khi chưa đủ: cách đó có thể tạo xung đột mới với các endpoint khác. Nên lập bảng path và mục tiêu bảo mật của từng chain.

### 8.1. Bảng quyết định chain

| Path | Chain mong muốn | Có oauth2Login filter? | Có session hợp lệ? |
|---|---|---|---|
| <code>/api/orders</code> | API bearer/JWT | Không cần | Thường không |
| <code>/app/dashboard</code> | OIDC web | Có | Có |
| <code>/oauth2/authorization/company</code> | OIDC web | Có | Có, cần lưu authorization request |
| <code>/login/oauth2/code/company</code> | **Chính OIDC web chain** | **Có** | **Có, để lấy state/authorization request** |
| <code>/login</code> | OIDC web (nếu dùng trang này) | Theo cấu hình | Theo flow |
| Các URL không được định nghĩa | Fallback | Tùy mục tiêu | Chính sách deny/allow rõ ràng |

Thứ tự callback và authorization start path nên được kiểm tra như một cặp. Nếu start request nằm trong web chain nhưng callback nằm trong API chain, ứng dụng sẽ tạo được authorization request mà không hoàn tất login. Ngược lại, callback match đúng chain nhưng start path không được filter xử lý thì người dùng chưa thể khởi tạo flow hợp lệ.

## 9. State, session và SecurityContext qua nhiều chain

Trong Authorization Code Flow cho ứng dụng Servlet, Client gửi tham số <code>state</code> khi bắt đầu đăng nhập. Khi nhà cung cấp redirect về callback, Spring Security đối chiếu <code>state</code> và lấy lại authorization request ban đầu. Repository mặc định của OAuth2 Login thường là **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>**.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant W as Web SecurityFilterChain
    participant S as HTTP Session
    participant OP as OpenID Provider
    B->>W: GET /oauth2/authorization/company
    W->>S: Lưu OAuth2AuthorizationRequest + state
    W-->>B: 302 redirect tới OP
    B->>OP: Authorization Request
    OP-->>B: 302 callback có code + state
    B->>W: GET /login/oauth2/code/company
    W->>S: Lấy authorization request đã lưu
    W->>W: Xác minh state, đổi code lấy token
    W-->>B: Thiết lập authentication / redirect thành công
~~~

Để hoàn tất luồng:

- **Start và callback** nên được xử lý trong chain OAuth2 Login có cấu hình phù hợp.
- Browser phải gửi lại session cookie tương ứng khi redirect từ IdP về ứng dụng.
- Nếu chạy nhiều instance, cần cơ chế chia sẻ/định tuyến session thích hợp, tùy kiến trúc và session store.
- Cookie <code>Secure</code>, <code>SameSite</code>, domain, path và cấu hình reverse proxy ảnh hưởng việc browser gửi cookie trở lại.
- Custom <code>AuthorizationRequestRepository</code> phải giữ đầy đủ authorization request, state và các thuộc tính cần thiết như PKCE verifier khi được sử dụng.

**Không quy mọi lỗi <code>invalid_state</code> cho SecurityMatcher.** Một callback có thể đi đúng chain nhưng thất bại vì mất session cookie, authorization request đã hết hạn, request đã được xử lý một lần, hoặc callback thuộc lần đăng nhập khác. Chain routing là một bước kiểm tra cần thiết trong chuỗi nguyên nhân.

### 9.1. SessionCreationPolicy và chain stateless

<code>SessionCreationPolicy.STATELESS</code> có thể phù hợp cho JWT API, nơi mỗi request được xác thực độc lập bằng bearer token. Đối với OAuth2 Login Servlet thông thường, trạng thái authorization request phải tồn tại qua browser redirect. Việc đưa callback vào chain stateless có thể khiến filter xử lý OAuth2 Login bị thiếu hoặc trạng thái đăng nhập không được duy trì như kỳ vọng.

Nếu kiến trúc yêu cầu đăng nhập không dùng session, phải thiết kế rõ một <code>AuthorizationRequestRepository</code> và cơ chế duy trì authentication phù hợp. Đây là thay đổi kiến trúc, không thể chỉ bật <code>STATELESS</code> và kỳ vọng OAuth2 Login mặc định hoạt động như cũ.

### 9.2. Mối quan hệ với SecurityContextRepository

OAuth2 Login thành công tạo <code>Authentication</code> cho người dùng và phải làm cho authentication khả dụng trong những request tiếp theo. Với ứng dụng session-based, Spring Security thường duy trì SecurityContext qua session theo cấu hình tương ứng.

Nếu web chain và một chain khác sử dụng SecurityContextRepository hoặc session policy khác nhau, kết quả có thể là đăng nhập callback thành công nhưng trang đích lại coi người dùng chưa xác thực. Cần kiểm tra **chain xử lý callback và chain bảo vệ trang đích**, không chỉ riêng request callback.

## 10. Cách tìm nguyên nhân callback không hoạt động

### 10.1. Xác nhận request có vào đúng chain không

Trong môi trường phát triển, có thể bật log có giới hạn:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Tùy phiên bản, log có thể giúp quan sát chain nào được xét/chọn và danh sách filter được chạy. Khi cần thông tin rộng hơn, có thể bật mức DEBUG cho namespace <code>org.springframework.security</code> trong thời gian ngắn ở môi trường kiểm thử.

Nên kiểm tra riêng hai request:

~~~text
GET /oauth2/authorization/company
GET /login/oauth2/code/company?code=...&state=...
~~~

Mục tiêu là xác nhận **hai request thuộc chain nào** và chain đó có các filter tương ứng. Không ghi nguyên authorization code, state, access token, ID Token, refresh token hoặc client secret vào log/ticket. Khi cần trace, hãy dùng path, registration ID, request correlation ID và loại lỗi đã được loại bỏ dữ liệu nhạy cảm.

### 10.2. Các bước phân tích theo thứ tự

1. **Xác định callback thực tế** mà IdP redirect tới, bao gồm hostname, scheme, context path và đường dẫn.
2. **Kiểm tra ClientRegistration.redirectUri** và redirect URI được đăng ký tại IdP có khớp URL đó không.
3. **Liệt kê các bean SecurityFilterChain theo @Order**, cùng security matcher của từng chain.
4. **Tìm chain khớp đầu tiên với callback**. Đừng giả định chain chứa <code>oauth2Login()</code> được chọn chỉ vì nó có matcher phù hợp.
5. **Kiểm tra filter processing URI** của <code>OAuth2LoginAuthenticationFilter</code> trong chain được chọn có khớp callback không.
6. **Đối chiếu authorization start URL** và <code>OAuth2AuthorizationRequestRedirectFilter</code> có nằm trong đúng chain, đúng base URI không.
7. **Kiểm tra state/session**, cookie và authorization request repository nếu filter đã xử lý callback nhưng authentication thất bại.
8. **Kiểm tra lỗi token exchange/ID Token validation** khi callback routing và session đều hợp lệ.

Một request thử được tự dựng với <code>code=abc</code> thường sẽ thất bại vì code không hợp lệ. Điều đó **không chứng minh callback filter sai**. Để kiểm tra login end-to-end cần thực hiện một flow thật với Authorization Server thử nghiệm hoặc môi trường phát triển.

### 10.3. Bảng lỗi và hướng xử lý

| Triệu chứng | Nơi cần kiểm tra | Hướng giải quyết |
|---|---|---|
| Callback trả 404, không có login processing | Không chain nào khớp hoặc chain được chọn thiếu OAuth2 Login filter | Mở rộng securityMatcher cho callback hoặc dùng web fallback |
| Callback trả 401 với HTTP Basic challenge | Chain API/basic có matcher quá rộng và được chọn trước web chain | Thu hẹp chain API; sắp lại @Order đúng phạm vi |
| Callback trả 403 | Authorization rule trong chain được chọn, CSRF cho phương thức callback tùy biến, hoặc handler khác | Kiểm tra chain trước, sau đó kiểm tra method/filter và authorization |
| Login redirect loop | Trang login/start/callback thuộc chain khác, hoặc authentication không được lưu/đọc cho trang đích | Kiểm tra routing, session, SecurityContextRepository và success URL |
| Provider báo <code>redirect_uri_mismatch</code> | Redirect URI sai ở ClientRegistration hoặc IdP | Đồng bộ template, URL thực tế, scheme/host/path |
| OAuth2 Login filter nhận callback nhưng báo lỗi state | Session cookie mất, authorization request không còn hoặc state sai | Kiểm tra cookie, session store, callback thuộc cùng flow |
| Token endpoint trả <code>invalid_grant</code> | Code sai/hết hạn/đã dùng, redirect URI/PKCE không hợp lệ | Chẩn đoán token exchange sau khi xác nhận callback vào đúng chain |
| Authentication thành công rồi vẫn bị coi là anonymous | Chain trang đích khác chain callback, session/security context policy không đồng nhất | Kiểm tra persistence và matcher của request tiếp theo |
| Authorization start URL báo 404 | Start path nằm ngoài chain có <code>OAuth2AuthorizationRequestRedirectFilter</code> | Đưa start URL vào đúng chain và kiểm tra custom authorization base URI |
| Web chain không bao giờ được chọn | Catch-all chain có @Order cao hơn | Đưa chain đặc thù trước, chain fallback sau |

## 11. Các hiểu lầm cần tránh

**“Chỉ cần thêm permitAll cho callback.”** Không đủ. <code>permitAll</code> xử lý authorization sau khi đã chọn chain. Chain cần match URL callback và có filter xử lý callback.

**“Request khớp hai chain thì cả hai chain đều chạy.”** Sai. <code>FilterChainProxy</code> sử dụng match đầu tiên; chain còn lại không được xét.

**“Callback được provider redirect tới đúng URL thì Spring Security chắc chắn xử lý.”** Sai. URL tại provider, ClientRegistration redirect URI, securityMatcher và OAuth2 Login filter processing URI phải khớp về vai trò.

**“Có thể chuyển callback sang API stateless chain vì đó chỉ là một URL GET.”** Callback cần state/authorization request và cơ chế tạo authentication của OAuth2 Login. Đặt nó trong chain chỉ thiết kế cho JWT bearer thường gây hỏng flow.

**“Để web chain match /app/** là đủ cho login của các trang /app.”** Sai nếu authorization start và callback ở ngoài <code>/app/**</code>. Phạm vi chain phải bao phủ cả những endpoint hạ tầng phục vụ đăng nhập.

**“Chain nào đặt dưới cùng cũng an toàn vì không match thì framework tự bảo vệ.”** Không chắc. Nếu không chain nào khớp request thì Spring Security không áp dụng các security filter của mình cho request đó. Một fallback chain với chính sách rõ ràng giúp tránh lỗ hổng ngoài dự kiến.

**“Thứ tự @Order chỉ ảnh hưởng tốc độ.”** Sai. Nó có thể thay đổi chính sách xác thực, filter được kích hoạt và khả năng hoàn tất OAuth2/OIDC Login.

## 12. Bài thực hành

### Bài 1 — Xác định chain cho các request

Cho ba chain:

~~~text
Chain A: @Order(1), securityMatcher("/api/**"), JWT resource server
Chain B: @Order(2), securityMatcher("/app/**"), oauth2Login()
Chain C: @Order(3), catch-all, denyAll
~~~

Hỏi callback mặc định <code>/login/oauth2/code/company</code> vào chain nào?

**Giải thích:** Callback không khớp A, không khớp B và rơi vào C. Vì C không có OAuth2 Login callback filter, login sẽ không hoàn tất. Thêm <code>/login/oauth2/code/**</code> và <code>/oauth2/authorization/**</code> vào securityMatcher của B (đồng thời tính các đường dẫn login cần thiết), hoặc chuyển B thành web fallback và thiết kế lại chain C.

### Bài 2 — Trùng matcher

Cho:

~~~text
Chain A: @Order(1), securityMatcher("/login/**"), httpBasic()
Chain B: @Order(2), securityMatcher("/login/oauth2/code/**"), oauth2Login()
~~~

Hỏi chain nào xử lý <code>/login/oauth2/code/company</code>?

**Giải thích:** Chain A khớp trước. Chain B không chạy. Thay vì chỉ sửa <code>permitAll</code>, hãy thay matcher của A để không chiếm callback, hoặc dùng namespace riêng cho HTTP Basic.

### Bài 3 — Tùy biến callback

Ứng dụng muốn callback <code>/sso/callback/{registrationId}</code>. Hãy xác định những nơi cần thay:

1. <code>ClientRegistration.redirectUri</code>: <code>{baseUrl}/sso/callback/{registrationId}</code>.
2. <code>oauth2Login().redirectionEndpoint().baseUri("/sso/callback/*")</code>.
3. <code>securityMatcher</code> của chain OIDC phải bao gồm <code>/sso/callback/**</code>.
4. Cấu hình allowed redirect URI tại IdP, ví dụ <code>https://app.example.org/sso/callback/company</code>.

Nếu ứng dụng có proxy/context path, hãy kiểm tra thêm URL thực tế được nhìn thấy ở browser và Authorization Server.

### Bài 4 — Mất session sau redirect

Start URL và callback đều vào web chain đúng, nhưng callback báo không tìm thấy authorization request. Hãy liệt kê ba điểm kiểm tra.

**Gợi ý trả lời:** (1) browser có gửi cookie session khi quay từ IdP không; (2) session có tồn tại trên instance nhận callback không, đặc biệt khi load balancing; (3) custom authorization request repository hoặc cấu hình cookie có làm mất <code>state</code>/authorization request/PKCE verifier không. Không chỉ sửa chain khi chain đã đúng.

### Bài 5 — Đọc sơ đồ và thiết kế fallback

Thiết kế một ứng dụng có các URL:

~~~text
/api/orders
/app/dashboard
/oauth2/authorization/company
/login/oauth2/code/company
/health
~~~

Yêu cầu API dùng JWT, web dùng OIDC Login, <code>/health</code> chỉ truy cập theo chính sách vận hành riêng. Có thể dùng API chain trước, web chain sau và một chain/matcher rõ ràng cho health hoặc đặt health dưới fallback được kiểm soát. Vẽ bảng mapping path → chain rồi thử xác định callback chain trước khi viết Java config.

## 13. Tổng kết kiến thức cốt lõi

Trong Spring Security Servlet, **lựa chọn SecurityFilterChain là bước đi trước mọi quyết định authorization và xác thực của filter bên trong chain**. <code>securityMatcher</code> quyết định chain nào có cơ hội xử lý request; <code>requestMatchers</code> quyết định quyền truy cập sau khi chain được chọn.

Với OAuth 2.0/OIDC Login, phải tính đến **cả authorization start endpoint và callback endpoint** ngoài trang ứng dụng. Nếu bật <code>oauth2Login()</code> ở chain giới hạn <code>/app/**</code>, hãy bổ sung các login endpoint vào phạm vi chain hoặc chuyển web chain thành fallback phù hợp. Luôn xem thứ tự <code>@Order</code>: request match chain đầu tiên sẽ không chạy tiếp chain khác.

Khi tùy biến callback, đồng bộ **redirect URI trong ClientRegistration**, **registration tại IdP**, **<code>redirectionEndpoint().baseUri()</code>** và **<code>securityMatcher</code>** của chain có OAuth2 Login. Sau routing, kiểm tra tiếp session/state, token exchange và OIDC ID Token validation để chẩn đoán đầy đủ.

### Tài liệu tham khảo

- **Spring Security Reference — Servlet Architecture:** <code>FilterChainProxy</code>, <code>SecurityFilterChain</code>, thứ tự match và nhiều filter chain.
- **Spring Security Reference — Java Configuration / HttpSecurity:** <code>securityMatcher</code>, <code>authorizeHttpRequests</code> và <code>requestMatchers</code>.
- **Spring Security Reference — OAuth2 Login (Servlet):** authorization endpoint, redirection endpoint, callback filter và authorization request repository.
- **Spring Security Java API:** <code>OAuth2AuthorizationRequestRedirectFilter</code>, <code>OAuth2LoginAuthenticationFilter</code>, <code>HttpSessionOAuth2AuthorizationRequestRepository</code> và <code>SecurityFilterChain</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Grant, redirect URI và token request.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token và các điều kiện kiểm tra OIDC.
