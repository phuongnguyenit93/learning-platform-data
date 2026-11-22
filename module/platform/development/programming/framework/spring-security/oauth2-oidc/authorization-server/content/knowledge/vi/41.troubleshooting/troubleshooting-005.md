# Vòng lặp login, mất authorization request và sai thứ tự filter chain

Trong Spring Authorization Server, một client thường bắt đầu bằng request đến **/oauth2/authorize**. Nếu người dùng chưa đăng nhập, Spring Security chuyển trình duyệt đến trang login. Sau khi xác thực thành công, trình duyệt phải quay lại authorization request ban đầu để server tiếp tục kiểm tra client, redirect URI, scope, consent và cấp authorization code.

Nếu một mắt xích trong chuỗi này bị mất, người dùng có thể bị chuyển qua lại giữa **/oauth2/authorize** và **/login**, quay về trang chủ sau khi đăng nhập, hoặc nhận lỗi **invalid_request**, **authorization_request_not_found** và **state_mismatch**.

Ba nhóm nguyên nhân thường gặp là:

- Session hoặc cookie không được giữ qua các lần redirect, khiến saved request và trạng thái xác thực biến mất.
- RequestCache, authentication success handler hoặc AuthorizationRequestRepository bị cấu hình sai, làm mất request cần tiếp tục.
- SecurityFilterChain có matcher hoặc thứ tự không đúng, khiến request login, callback hoặc Authorization Server endpoint đi vào nhầm chain.

Bài học này hướng dẫn cách phân biệt các loại request, lần theo redirect, kiểm tra session và cookie, sửa thứ tự filter chain, rồi xác minh bằng log và kiểm thử tích hợp.

## 1. Hiểu luồng đăng nhập trong Authorization Code Flow

Một authorization request thường chứa các tham số như **client_id**, **response_type**, **redirect_uri**, **scope**, **state**, **nonce** và PKCE challenge. Authorization Server phải giữ được ngữ cảnh đó trong khi người dùng đăng nhập.

Luồng đơn giản khi người dùng đăng nhập bằng form của chính ứng dụng:

~~~mermaid
sequenceDiagram
    participant C as OAuth/OIDC Client
    participant B as Browser
    participant AS as Authorization Server
    participant L as Login Page

    C->>B: Redirect đến /oauth2/authorize
    B->>AS: GET /oauth2/authorize?client_id=...&state=...
    AS->>AS: Chưa có Authentication
    AS->>AS: Lưu original request vào RequestCache
    AS-->>B: 302 Location: /login
    B->>L: GET /login
    L-->>B: Form đăng nhập
    B->>AS: POST /login + credentials + CSRF
    AS->>AS: Xác thực và lưu SecurityContext
    AS-->>B: 302 về saved authorization request
    B->>AS: GET /oauth2/authorize với request ban đầu
    AS->>AS: Tiếp tục authorize/consent
    AS-->>B: Redirect về redirect_uri với code và state
    B->>C: Callback của client
~~~

Điểm quan trọng là request quay lại sau login phải còn đầy đủ ngữ cảnh. Nếu server chỉ biết người dùng đã đăng nhập nhưng không biết request nào đang chờ, người dùng có thể bị đưa về trang mặc định thay vì tiếp tục authorization flow.

Trong luồng này, cần phân biệt ba thứ:

| Thành phần | Vai trò | Nơi thường được lưu |
|---|---|---|
| Inbound authorization request | Request từ client đi vào **/oauth2/authorize** | RequestCache/session trong lúc chuyển qua login; sau đó Authorization Server xử lý và lưu authorization state theo flow |
| SecurityContext | Danh tính người dùng sau khi login | HTTP session thông qua SecurityContextRepository, nếu ứng dụng dùng session |
| Outbound OAuth2/OIDC authorization request | Request do chính ứng dụng gửi đến IdP bên ngoài khi dùng **oauth2Login()** | AuthorizationRequestRepository, mặc định là HttpSessionOAuth2AuthorizationRequestRepository |

Không dùng tên gọi chung “authorization request” để thay thế cả ba. RequestCache xử lý request HTTP đang chờ sau login; AuthorizationRequestRepository giữ request OAuth2 do ứng dụng tạo để gửi đến nhà cung cấp danh tính; SecurityContext lưu kết quả xác thực.

## 2. Nhận diện triệu chứng trước khi thay đổi cấu hình

Mở Network tab của trình duyệt hoặc ghi lại chuỗi request/response. Chú ý URL, status, Location, cookie được gửi và cookie được trả về.

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| **/oauth2/authorize** → **/login** → **/oauth2/authorize** → **/login** lặp lại | Session mất, SecurityContext không được lưu hoặc request login bị chain khác bắt | Cookie session, session store và chain xử lý **/login** |
| Đăng nhập thành công nhưng chuyển về **/** hoặc dashboard | Success handler dùng default target và bỏ qua saved request | AuthenticationSuccessHandler và RequestCache |
| Sau login nhận **invalid_request** hoặc thiếu **client_id**/**redirect_uri** | Saved request bị mất hoặc request bị thay đổi | Location sau login và query parameters ban đầu |
| **/login** tự redirect về **/login** | Login page bị yêu cầu Authentication hoặc bị chain Authorization Server bắt nhầm | securityMatcher, requestMatchers, permitAll |
| Login thành công nhưng callback IdP báo **authorization_request_not_found** | Session hoặc AuthorizationRequestRepository không tìm được outbound request | Cookie, state, repository và callback chain |
| **state_mismatch** hoặc **invalid_state_parameter** | Request state và callback state không còn tương ứng | Session, nhiều tab, proxy và request repository |
| Login POST trả **403** | CSRF token thiếu/sai hoặc form action sai | Hidden CSRF field, cookie và request method |
| Chỉ lỗi khi chạy nhiều replica | Session hoặc request state nằm trong memory của một pod | Shared session store và định tuyến giữa các pod |
| Chỉ lỗi sau khi qua ingress | Cookie Secure/SameSite, forwarded headers hoặc path rewrite sai | Header Set-Cookie, X-Forwarded-* và public URL |

Không kết luận rằng lỗi nằm ở OAuth2 chỉ vì trình duyệt đang ở trang **/oauth2/authorize**. Hãy xác định request đầu tiên có hành vi khác với mong đợi.

## 3. Kiểm tra SecurityFilterChain và thứ tự matcher

### 3.1. Spring Security chỉ dùng chain đầu tiên khớp request

**FilterChainProxy** kiểm tra các **SecurityFilterChain** theo thứ tự. Với một request, chain đầu tiên có **securityMatcher** khớp sẽ được chọn. Các chain phía sau không tiếp tục bổ sung filter cho request đó.

Điều này có nghĩa:

- **@Order(1)** được xét trước **@Order(2)**.
- **securityMatcher(...)** quyết định request thuộc chain nào.
- **requestMatchers(...)** bên trong **authorizeHttpRequests** quyết định quyền truy cập sau khi chain đã được chọn.
- Một chain có matcher **anyRequest()** đặt quá sớm có thể bắt toàn bộ request và làm các chain chuyên biệt phía sau không bao giờ chạy.

Đây là khác biệt quan trọng nhất khi chẩn đoán lỗi thứ tự filter chain.

### 3.2. Dùng chain riêng cho Authorization Server và ứng dụng login

Một cấu trúc thường dùng là:

1. Chain ưu tiên cao cho các endpoint của Authorization Server.
2. Chain cho API riêng nếu ứng dụng có API stateless.
3. Chain ứng dụng web ở cuối, xử lý login page và các trang HTML.

Ví dụ dưới đây dùng API configurer mới của Spring Authorization Server. Cần đối chiếu với phiên bản dependency của dự án.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RequestCache requestCache) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .requestCache(cache ->
            cache.requestCache(requestCache)
        )
        .exceptionHandling(exceptions ->
            exceptions.defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
            )
        );

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        RequestCache requestCache,
        AuthenticationSuccessHandler authenticationSuccessHandler)
        throws Exception {

    http
        .requestCache(cache ->
            cache.requestCache(requestCache)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/login",
                "/assets/**",
                "/favicon.ico"
            ).permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .successHandler(authenticationSuccessHandler)
            .permitAll()
        );

    return http.build();
}

@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}
~~~

Trong ví dụ:

- Chain đầu chỉ khớp endpoint matcher do Authorization Server configurer cung cấp.
- **/login** không thuộc matcher của Authorization Server, vì vậy request đi vào chain ứng dụng.
- **RequestCache** được dùng chung để lưu request ban đầu và phục hồi nó sau khi login.
- Trang login và tài nguyên tĩnh được phép truy cập trước khi người dùng xác thực.
- **LoginUrlAuthenticationEntryPoint** đưa request HTML chưa xác thực đến **/login**.

Nếu dự án dùng API cũ, cấu hình **OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http)** trong chain đầu rồi bổ sung OIDC, RequestCache và exception handling phù hợp. Không trộn hai kiểu cấu hình configurer trong cùng một chain.

### 3.3. Đừng để catch-all chain đứng trước Authorization Server

Ví dụ dễ gây lỗi:

~~~java
@Bean
@Order(1)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {
    OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);
    return http.build();
}
~~~

Chain đầu không khai báo **securityMatcher**, vì vậy nó khớp mọi request. Các endpoint như **/oauth2/authorize**, **/oauth2/token** hoặc **/oauth2/jwks** có thể bị xử lý như request ứng dụng thông thường. Chain Authorization Server phía sau không được chọn.

Biểu hiện có thể là endpoint trả **404**, redirect login sai, thiếu protocol filter hoặc hành vi không nhất quán giữa các endpoint.

Cách sửa là đặt chain Authorization Server trước và dùng endpoint matcher cụ thể; chain ứng dụng catch-all phải đứng sau.

### 3.4. Đừng để chain Authorization Server bắt cả /login

Một lỗi ngược lại xảy ra khi chain Authorization Server dùng matcher quá rộng:

~~~java
http.securityMatcher("/**");
~~~

Nếu chain này đứng đầu và áp dụng các filter/rule chỉ dành cho Authorization Server, **/login**, **/assets/** hoặc callback **/login/oauth2/code/** cũng có thể đi vào chain đó. Login page có thể không được render, POST login không được xử lý, hoặc request bị chuyển hướng liên tục.

Hãy dùng **authorizationServerConfigurer.getEndpointsMatcher()** hoặc matcher cụ thể theo endpoint. Đừng dùng catch-all cho chain chuyên biệt.

### 3.5. Tách API stateless bằng matcher riêng

Nếu ứng dụng có REST API không dùng session, đặt chain API giữa Authorization Server và chain web:

~~~java
@Bean
@Order(2)
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults())
        )
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form.loginPage("/login").permitAll());

    return http.build();
}
~~~

Chain API chỉ khớp **/api/**; nó không được bắt **/oauth2/authorize** hoặc **/login**. Không đặt **SessionCreationPolicy.STATELESS** trong chain web có form login nếu flow cần session để lưu RequestCache và SecurityContext.

## 4. Khắc phục mất inbound authorization request

### 4.1. Hiểu RequestCache

Khi người dùng chưa xác thực truy cập một URL được bảo vệ, **ExceptionTranslationFilter** có thể lưu request vào **RequestCache** trước khi gọi AuthenticationEntryPoint.

Với ứng dụng web dùng session, implementation mặc định thường là **HttpSessionRequestCache**. Request được lưu trong HTTP session để success handler có thể chuyển trình duyệt về URL ban đầu sau khi login.

Nếu ứng dụng thay RequestCache bằng **NullRequestCache**, dùng session stateless hoặc success handler luôn redirect đến trang cố định, request ban đầu có thể bị mất.

Ví dụ cấu hình chủ động một RequestCache dùng chung:

~~~java
@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}
~~~

Cấu hình cùng bean đó trong chain xử lý Authorization Server và chain xử lý form login. Việc dùng chung giúp hai chain đọc/ghi cùng saved request trong session.

Không thay bằng **NullRequestCache** trong luồng browser authorization cần quay lại URL ban đầu.

### 4.2. Kiểm tra AuthenticationSuccessHandler

Success handler mặc định của form login có thể sử dụng saved request để chuyển trình duyệt về request đang chờ. Nếu ứng dụng tự viết handler như sau:

~~~java
.successHandler((request, response, authentication) ->
    response.sendRedirect("/dashboard")
)
~~~

thì request authorization ban đầu bị bỏ qua. Người dùng đăng nhập thành công nhưng Authorization Server không tiếp tục flow mà client đã khởi tạo.

Nếu cần xử lý thêm sau login, có thể dùng **SavedRequestAwareAuthenticationSuccessHandler** làm nền và chỉ tùy biến phần thực sự cần thiết:

~~~java
@Bean
AuthenticationSuccessHandler authenticationSuccessHandler(
        RequestCache requestCache) {
    SavedRequestAwareAuthenticationSuccessHandler handler =
            new SavedRequestAwareAuthenticationSuccessHandler();

    handler.setRequestCache(requestCache);
    handler.setDefaultTargetUrl("/dashboard");
    handler.setAlwaysUseDefaultTargetUrl(false);

    return handler;
}
~~~

**alwaysUseDefaultTargetUrl(false)** cho phép saved request được ưu tiên khi tồn tại; **/dashboard** chỉ là đích mặc định khi không có request cần phục hồi. Nếu tự triển khai success handler, phải giữ hành vi tương đương và không xóa saved request trước khi sử dụng.

### 4.3. Kiểm tra RequestCache có thực sự lưu request

Khi nhận redirect đến **/login**, kiểm tra session có được tạo và saved request có tồn tại. Những trường hợp thường làm mất request:

- RequestCache bị thay bằng **NullRequestCache**.
- Ứng dụng đặt **SessionCreationPolicy.STATELESS** trong chain xử lý browser authorization.
- Custom **SecurityContextRepository** hoặc success handler xóa session.
- Login page và endpoint login dùng cookie path/domain khác nhau.
- Session store không chia sẻ giữa các replica.
- Proxy làm mất cookie hoặc trình duyệt không gửi lại cookie.
- Request bị rewrite sang URL khác trước khi được lưu.

RequestCache chỉ giữ request HTTP đang chờ. Nó không thay thế authorization state persistence của Spring Authorization Server và cũng không thay thế AuthorizationRequestRepository của Spring OAuth2 Client.

### 4.4. Không làm biến đổi tham số authorization trong quá trình redirect

So sánh URL trước và sau login. Các tham số như **client_id**, **redirect_uri**, **response_type**, **scope**, **state**, **nonce**, **code_challenge**, **code_challenge_method** phải được giữ đúng theo request ban đầu.

Nếu ứng dụng tự tạo redirect URL bằng cách nối chuỗi, có thể xảy ra:

- Mất query parameter.
- URL encode hai lần.
- Dấu **&** bị encode hoặc bị loại bỏ.
- **redirect_uri** bị thay scheme/host/path.
- **state** hoặc PKCE challenge bị thay đổi.
- Request URI của PAR bị mất.

Không dựng lại authorization URL từ một danh sách tham số rút gọn. Dùng saved request hoặc cơ chế protocol request đã được framework cung cấp.

## 5. Khắc phục mất outbound OAuth2/OIDC authorization request

Một tình huống khác là Spring Authorization Server dùng **oauth2Login()** để đăng nhập người dùng thông qua một IdP bên ngoài. Ví dụ ứng dụng chuyển người dùng đến Google, Keycloak hoặc một identity provider nội bộ.

Khi đó, Spring Security OAuth2 Client tạo một **OAuth2AuthorizationRequest** chứa **state**, **nonce**, redirect URI, client registration ID và các tham số giao thức. Mặc định, **HttpSessionOAuth2AuthorizationRequestRepository** lưu request trong HTTP session để callback có thể tìm lại.

Luồng:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Application
    participant IDP as External IdP

    B->>APP: GET /oauth2/authorization/corporate
    APP->>APP: Tạo OAuth2AuthorizationRequest và lưu session
    APP-->>B: 302 đến IdP với state
    B->>IDP: Authorization Request
    IDP-->>B: Redirect về /login/oauth2/code/corporate?code=...&state=...
    B->>APP: Callback kèm session cookie
    APP->>APP: Tìm request theo session và so sánh state
    APP->>IDP: Token Request
    IDP-->>APP: Token Response
    APP-->>B: Login thành công
~~~

Nếu callback không mang đúng session cookie, repository không tìm thấy request đã lưu. Kết quả thường là **authorization_request_not_found** hoặc lỗi state.

Kiểm tra:

- Request khởi tạo và callback dùng cùng browser profile.
- Cookie session được gửi trong cả hai request.
- Callback path **/login/oauth2/code/** thuộc chain có **oauth2Login()**.
- Session store chia sẻ giữa các replica.
- Không có middleware xóa session hoặc đổi cookie path.
- Không có custom AuthorizationRequestRepository lưu request ở nơi khác với nơi callback đọc.
- **state** trong callback khớp với request đã lưu.
- Nếu có nhiều tab hoặc nhiều login đồng thời, repository tùy chỉnh không ghi đè request của tab khác.

Cấu hình chain web có thể bật **oauth2Login()** cùng form login theo yêu cầu:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form.loginPage("/login").permitAll())
    .oauth2Login(Customizer.withDefaults());
~~~

Đảm bảo callback không bị một chain API stateless hoặc chain Authorization Server quá rộng bắt trước chain web.

## 6. Kiểm tra session, cookie và reverse proxy

### 6.1. Xác minh cookie session trong browser

Trong DevTools, xem response redirect đầu tiên có **Set-Cookie** không và request tiếp theo có gửi lại cookie không.

Kiểm tra các thuộc tính:

| Thuộc tính | Vấn đề có thể gây ra |
|---|---|
| Domain | Cookie không được gửi nếu domain không khớp host công khai |
| Path | Cookie không được gửi đến **/login** hoặc **/oauth2/authorize** nếu path quá hẹp |
| Secure | Cookie chỉ gửi qua HTTPS; proxy/ứng dụng hiểu sai scheme có thể gây hành vi không nhất quán |
| SameSite | Trình duyệt có thể bỏ cookie trong điều hướng hoặc callback cross-site |
| HttpOnly | Nên bật để JavaScript không đọc cookie session |
| Max-Age/Expires | Session cookie hết hạn trước khi người dùng hoàn tất đăng nhập |

Một cấu hình Spring Boot thường dùng khi ứng dụng công khai qua HTTPS:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.forward-headers-strategy=framework
~~~

Các property phụ thuộc phiên bản Spring Boot. Xác nhận cấu hình cookie thực tế trong response **Set-Cookie**; không chỉ dựa vào file properties.

**SameSite=Lax** thường phù hợp với điều hướng top-level GET đến Authorization Server. Nếu hệ thống có callback cross-site bằng POST, ví dụ một flow sử dụng **response_mode=form_post**, cần đánh giá cookie nào phải đi kèm callback. Cookie cần gửi trong cross-site POST có thể cần **SameSite=None; Secure**. Không chuyển toàn bộ cookie sang **None** nếu không có yêu cầu thực tế.

### 6.2. Kiểm tra HTTPS termination và forwarded headers

Khi TLS kết thúc ở ingress hoặc reverse proxy, ứng dụng có thể nhận request nội bộ bằng HTTP trong khi trình duyệt truy cập HTTPS. Nếu forwarded headers không được xử lý đúng, ứng dụng có thể:

- Tạo redirect về **http://** thay vì **https://**.
- Phát cookie Secure không nhất quán.
- Tạo URL công khai sai host hoặc port.
- So sánh redirect URI không đúng.
- Tạo vòng lặp redirect giữa proxy và ứng dụng.

Cấu hình **server.forward-headers-strategy** phù hợp với hạ tầng và chỉ tin header từ proxy được kiểm soát. Không cho client internet tự gửi **X-Forwarded-Proto**, **X-Forwarded-Host** để quyết định URL bảo mật của ứng dụng.

Kiểm tra header mà ứng dụng nhận và URL trong **Location** response. Giá trị **issuer**, endpoint discovery và redirect URI phải nhất quán với public URL.

### 6.3. Kiểm tra path prefix và rewrite rule

Nếu public URL là **https://auth.example.com/security** nhưng proxy chuyển request đến ứng dụng bằng **/**, cần xác định ứng dụng có chạy với context path hay proxy strip prefix.

Các lỗi thường gặp:

- Browser được redirect đến **/login** thay vì **/security/login**.
- Callback **/login/oauth2/code/corporate** bị rewrite thành đường dẫn không đúng.
- Authorization endpoint được công bố với path khác path proxy đang route.
- Cookie **Path=/security** không được gửi đến **/login** ở root.

Kiểm tra đồng thời ingress rule, context path, **AuthorizationServerSettings**, login page URL và cookie path. Tránh sửa từng URL rời rạc mà không xác định một public base path thống nhất.

### 6.4. Nhiều replica cần session store dùng chung

Nếu request **/oauth2/authorize** đến pod A, nhưng login GET/POST hoặc callback đến pod B, pod B phải đọc được session đã được pod A tạo.

Sticky session có thể giảm xác suất request đổi pod, nhưng không thay thế shared session store. Khi pod restart hoặc scale down, session cục bộ vẫn mất.

Có thể dùng Spring Session với Redis hoặc JDBC. Kiểm tra:

- Mọi replica dùng cùng namespace/session repository.
- Cookie session có cùng domain, path và signing/encryption configuration nếu có.
- Redis/JDBC có thể truy cập từ mọi pod.
- Session TTL đủ dài cho login và consent.
- Serialization tương thích giữa các phiên bản trong rolling deployment.
- Session fixation strategy sau login không làm mất saved request.

Không tự gọi **session.invalidate()** sau login nếu còn cần saved request hoặc OAuth2AuthorizationRequest trong session. Spring Security có session fixation protection; hãy giữ chiến lược mặc định phù hợp hoặc cấu hình migration session có chủ đích.

## 7. Kiểm tra login page và CSRF

Nếu dùng trang login tùy chỉnh, form phải gửi đúng endpoint xử lý và CSRF token.

Ví dụ HTML:

~~~html
<form method="post" action="/login">
  <label for="username">Username</label>
  <input id="username" name="username" type="text" autocomplete="username">

  <label for="password">Password</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password">

  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_MODEL">
  <button type="submit">Sign in</button>
</form>
~~~

**CSRF_TOKEN_FROM_MODEL** là placeholder. Template engine cần render giá trị token thực tế từ request/model theo cấu hình Spring Security. Không gửi nguyên chuỗi placeholder.

Kiểm tra:

- Form method là POST.
- Action trỏ đúng **loginProcessingUrl**.
- Tên field khớp **usernameParameter** và **passwordParameter** nếu đã tùy chỉnh.
- CSRF token được render và gửi.
- Trang login và asset không bị yêu cầu Authentication.
- POST login không bị một chain khác bắt trước **UsernamePasswordAuthenticationFilter**.
- Sau khi login, SecurityContext được lưu để request kế tiếp nhận ra người dùng.

Không tắt CSRF toàn ứng dụng để sửa lỗi **403** của login form. Nếu một protocol endpoint cần quy tắc CSRF riêng, áp dụng matcher hẹp và theo hướng dẫn của phiên bản Spring Authorization Server đang dùng.

## 8. Chẩn đoán theo chuỗi redirect

Một cách thực tế là ghi lại từng bước và xác định vị trí vòng lặp.

### Trường hợp A: session mất sau redirect

Chuỗi quan sát:

~~~text
GET /oauth2/authorize?...        -> 302 /login
GET /login                       -> 200
POST /login                      -> 302 /oauth2/authorize?...
GET /oauth2/authorize?...        -> 302 /login
~~~

Nguyên nhân thường là SecurityContext không được giữ hoặc session cookie không được gửi lại. Kiểm tra **Set-Cookie**, request Cookie, session ID, session store và SecurityContextRepository.

### Trường hợp B: login thành công nhưng saved request bị bỏ qua

~~~text
GET /oauth2/authorize?...        -> 302 /login
POST /login                      -> 302 /
GET /                              -> 200
~~~

Nguyên nhân thường là custom success handler luôn redirect về **/**. Kiểm tra **SavedRequestAwareAuthenticationSuccessHandler**, RequestCache và **alwaysUseDefaultTargetUrl**.

### Trường hợp C: login page bị bảo vệ bởi chính chain sai

~~~text
GET /oauth2/authorize?...        -> 302 /login
GET /login                       -> 302 /login
GET /login                       -> 302 /login
~~~

Nguyên nhân có thể là **/login** bị chain Authorization Server hoặc chain catch-all không đúng xử lý, hoặc rule **/login** không **permitAll**. Kiểm tra thứ tự chain, matcher và login page configuration.

### Trường hợp D: outbound IdP callback không tìm thấy request

~~~text
GET /oauth2/authorization/corporate -> 302 external-idp
GET /login/oauth2/code/corporate?... -> 4xx
~~~

Kiểm tra session cookie có được gửi trong callback không, AuthorizationRequestRepository có đọc đúng session không và callback có đi qua chain chứa **oauth2Login()** không.

### Trường hợp E: login POST bị CSRF từ chối

~~~text
GET /login                       -> 200
POST /login                      -> 403
~~~

Kiểm tra hidden CSRF field, cookie CSRF nếu dùng cookie-based repository, form action và request content type. Phân biệt **403** do CSRF với **401** do credential sai.

## 9. Dùng log để xác định chain và RequestCache

Trong môi trường phát triển hoặc staging, có thể bật log Spring Security ở mức TRACE trong thời gian ngắn:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Log giúp nhận biết:

- Request đang được **FilterChainProxy** chuyển đến chain nào.
- Matcher nào khớp request.
- **AuthorizationFilter** có yêu cầu Authentication không.
- **ExceptionTranslationFilter** có gọi AuthenticationEntryPoint không.
- RequestCache có lưu saved request không.
- Authentication thành công hay thất bại.
- SecurityContext có được lưu và khôi phục không.

Không bật TRACE rộng trong production trong thời gian dài. Log có thể làm tăng lượng dữ liệu và vô tình ghi thông tin request nhạy cảm tùy cấu hình. Không log password, cookie session, authorization code, client secret, access token, refresh token hoặc toàn bộ query string chứa dữ liệu nhạy cảm.

Có thể thêm log ứng dụng đã làm sạch dữ liệu, ví dụ:

- Correlation ID.
- Tên endpoint.
- Tên filter chain hoặc phiên bản ứng dụng.
- Kết quả authentication.
- Có saved request hay không.
- Mã lỗi OAuth.
- Replica/pod xử lý request.

Không ghi session ID đầy đủ; nếu cần tương quan, dùng hash hoặc identifier đã được bảo vệ.

## 10. Kiểm thử hồi quy cho login và authorization request

### 10.1. Kiểm thử saved request qua form login

Một kiểm thử tích hợp cần xác minh request ban đầu được lưu, login thành công và redirect trở lại authorization endpoint.

Ví dụ minh họa với MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationLoginFlowTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldReturnToAuthorizationRequestAfterLogin() throws Exception {
        MvcResult authorizationStart = mockMvc.perform(
                get("/oauth2/authorize")
                    .param("response_type", "code")
                    .param("client_id", "web-client")
                    .param("redirect_uri",
                            "https://client.example.com/callback")
                    .param("scope", "openid profile")
                    .param("state", "state-123")
                    .param("code_challenge", "TEST_CHALLENGE")
                    .param("code_challenge_method", "S256"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) authorizationStart.getRequest().getSession(false);

        assertThat(session).isNotNull();
        assertThat(authorizationStart.getResponse().getRedirectedUrl())
                .contains("/login");

        MvcResult loginResult = mockMvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertThat(loginResult.getResponse().getRedirectedUrl())
                .contains("/oauth2/authorize")
                .contains("client_id=web-client")
                .contains("state=state-123");
    }
}
~~~

Ví dụ cần có user test, client đã đăng ký, CSRF support và endpoint path tương ứng với ứng dụng. Giá trị PKCE challenge trong ví dụ là fixture minh họa; test end-to-end nên tạo challenge S256 đúng từ verifier.

Với cấu hình session fixation thay đổi session ID, test HTTP thực tế cần tiếp tục bằng session cookie mới trong response login. MockMvc có thể dùng cùng session object tùy strategy; khi kiểm tra hành vi cookie ở mức browser, dùng embedded server hoặc test HTTP client giữ cookie jar.

### 10.2. Kiểm thử chain login và callback

Tạo các ca riêng:

| Ca | Request | Kết quả mong đợi |
|---|---|---|
| CHAIN-01 | **GET /oauth2/authorize** chưa đăng nhập | Được chuyển đến login page |
| CHAIN-02 | **GET /login** chưa đăng nhập | Trả trang login, không redirect lặp |
| CHAIN-03 | **POST /login** credential hợp lệ | Xác thực thành công, redirect về saved request |
| CHAIN-04 | **POST /login** thiếu CSRF | Bị từ chối theo CSRF policy |
| CHAIN-05 | **GET /oauth2/jwks** | Được xử lý bởi Authorization Server chain |
| CHAIN-06 | **GET /login/oauth2/code/corporate** | Được xử lý bởi chain có oauth2Login |
| CHAIN-07 | **GET /api/profile** | Được xử lý bởi API chain nếu ứng dụng có chain riêng |
| CHAIN-08 | Tải **/assets/login.css** | Không bị yêu cầu login nếu asset được public |
| CHAIN-09 | Request authorization qua replica khác | Saved request và SecurityContext vẫn được tìm thấy |
| CHAIN-10 | Hai tab khởi tạo login đồng thời | State của mỗi flow không bị ghi đè ngoài ý muốn |

### 10.3. Kiểm thử callback từ IdP bên ngoài

Nếu dùng **oauth2Login()**, kiểm thử thêm:

- AuthorizationRequestRepository lưu request khi redirect đến IdP.
- Callback có cookie session và đúng **state**.
- State sai bị từ chối.
- Callback thiếu session không được tự động chấp nhận.
- Callback route được chain ứng dụng xử lý.
- Session store dùng chung giữa các replica.
- Custom success handler không bỏ qua saved request của ứng dụng.

Không mock việc xác thực thành công theo cách bỏ qua hoàn toàn state validation nếu mục tiêu là kiểm tra lỗi mất authorization request.

## 11. Checklist khắc phục theo thứ tự

Khi gặp login loop hoặc mất authorization request, thực hiện theo thứ tự:

1. Ghi lại chuỗi redirect, status và **Location**.
2. Xác định request nào đầu tiên bị chuyển hướng ngoài dự kiến.
3. Xác định chain nào khớp **/oauth2/authorize**, **/login**, **/login/oauth2/code/** và API.
4. Kiểm tra **@Order** và phạm vi **securityMatcher**.
5. Kiểm tra **/login** và asset có **permitAll** không.
6. Kiểm tra RequestCache có lưu request ban đầu không.
7. Kiểm tra success handler có dùng saved request không.
8. Kiểm tra session cookie được trả về và gửi lại qua redirect.
9. Kiểm tra **SessionCreationPolicy**, SecurityContextRepository và thao tác invalidate session.
10. Kiểm tra SameSite, Secure, Domain, Path và HTTPS forwarded headers.
11. Nếu có nhiều replica, kiểm tra shared session store và serialization.
12. Nếu dùng **oauth2Login**, kiểm tra AuthorizationRequestRepository và state ở callback.
13. Chạy lại test từ request authorize đến sau login, không chỉ test trang login riêng.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| **/oauth2/authorize** đi vào app chain | Catch-all chain đứng trước | Đưa Authorization Server chain lên trước, dùng endpoint matcher |
| **/login** đi vào Authorization Server chain | Matcher quá rộng | Thu hẹp matcher của chain Authorization Server |
| Đăng nhập xong về trang chủ | Success handler luôn dùng default target | Dùng SavedRequestAwareAuthenticationSuccessHandler |
| Request ban đầu không được lưu | NullRequestCache hoặc stateless session | Dùng HttpSessionRequestCache cho browser flow |
| Session mất sau redirect | Cookie bị chặn hoặc session không chia sẻ | Sửa cookie/proxy và dùng shared session store |
| Login page redirect lặp | **/login** chưa permitAll hoặc bị chain sai bắt | Sửa chain order và authorization rules |
| Login POST 403 | CSRF token thiếu hoặc sai | Render hidden CSRF token và kiểm tra form action |
| Callback IdP báo request not found | AuthorizationRequestRepository không tìm thấy session state | Giữ cookie/session và dùng repository nhất quán |
| Lỗi chỉ xảy ra ở một pod | Session hoặc state lưu local memory | Dùng Redis/JDBC shared session và state store phù hợp |
| URL quay lại thiếu query parameters | Redirect URL được dựng thủ công hoặc proxy rewrite | Dùng saved request và kiểm tra public path |
| Chỉ lỗi trên HTTPS | Forwarded headers hoặc Secure cookie sai | Cấu hình proxy trust và forwarded header đúng |
| Nhiều tab làm state mismatch | Repository tùy chỉnh ghi đè request đang chờ | Lưu request theo state/correlation key và hỗ trợ nhiều flow đồng thời |

## 13. Checklist trước khi đưa vào production

- [ ] Authorization Server chain dùng endpoint matcher cụ thể và có thứ tự ưu tiên phù hợp.
- [ ] Application login chain đứng sau Authorization Server chain.
- [ ] API stateless, nếu có, dùng matcher riêng và không bắt login/callback.
- [ ] **/login**, login processing URL và asset được truy cập theo policy mong muốn.
- [ ] RequestCache của chain Authorization Server và chain login được cấu hình nhất quán.
- [ ] Success handler giữ hành vi phục hồi saved request.
- [ ] Browser flow có session và SecurityContext được lưu qua request.
- [ ] Cookie Domain, Path, Secure, HttpOnly và SameSite phù hợp với public URL.
- [ ] Forwarded headers chỉ được tin từ proxy đã kiểm soát.
- [ ] Nhiều replica dùng session store chung nếu flow có thể đổi pod.
- [ ] Session fixation protection không làm mất saved request.
- [ ] Nếu dùng **oauth2Login**, AuthorizationRequestRepository giữ request đến callback.
- [ ] Có kiểm thử login loop, mất query parameter, state mismatch, CSRF và nhiều replica.
- [ ] Log đủ để xác định chain và RequestCache nhưng không ghi credential/token.
- [ ] Có thể chạy synthetic authorization flow sau mỗi lần deploy.

Vòng lặp login thường là dấu hiệu request bị chuyển qua một chain không phù hợp hoặc session không còn được nhận diện. Mất authorization request thường liên quan đến RequestCache, success handler, cookie hoặc repository lưu outbound request. Khi xác định đúng loại request và chain xử lý nó, việc sửa lỗi sẽ tập trung vào đúng matcher, session và cơ chế phục hồi thay vì thay đổi ngẫu nhiên nhiều cấu hình bảo mật.

