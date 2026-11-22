# Kiểm thử CSRF, CORS, session fixation và logout redirect

Một Spring Authorization Server xử lý đồng thời các yêu cầu từ trình duyệt người dùng, ứng dụng OAuth client và các hệ thống backend. Mỗi nhóm request có cách mang thông tin xác thực và rủi ro khác nhau. Nếu tắt CSRF cho toàn bộ ứng dụng để token endpoint dễ gọi, hoặc mở CORS cho mọi origin để một SPA hoạt động, các trang đăng nhập và consent có thể bị đặt vào tình huống không an toàn. Nếu chỉ kiểm tra đăng nhập thành công mà không kiểm tra vòng đời session và đích chuyển hướng sau logout, ứng dụng vẫn có thể gặp lỗi chiếm dụng phiên hoặc open redirect.

Bài học này xây dựng cách kiểm thử bốn nhóm kiểm soát trong Spring Security và Spring Authorization Server: CSRF cho thao tác dựa trên session trình duyệt, CORS cho request cross-origin từ trình duyệt, session fixation sau xác thực và redirect sau đăng xuất. Các ví dụ dùng endpoint mặc định phổ biến; khi ứng dụng thay đổi endpoint hoặc phiên bản Spring Boot/Spring Security, hãy đồng bộ matcher và cấu hình theo endpoint thực tế.

## 1. Xác định đúng ranh giới bảo mật

Trước khi viết test, cần phân biệt các luồng thường gặp trong Authorization Server:

| Luồng | Cách xác thực chủ yếu | Kiểm soát cần chú ý |
|---|---|---|
| Mở `/oauth2/authorize` | Cookie session của người dùng tại Authorization Server | Session hợp lệ, đăng nhập, `state` do client quản lý, consent và CSRF cho form POST |
| Gửi form đăng nhập hoặc consent | Cookie session và dữ liệu form | CSRF token, kiểm soát session fixation |
| Gọi `/oauth2/token` | Client authentication hoặc thông tin client công khai cùng authorization code và PKCE | Xác thực client, kiểm tra code/PKCE, CORS nếu SPA gọi trực tiếp từ trình duyệt |
| Gọi introspection hoặc revocation | Client authentication theo chính sách endpoint | Xác thực client, giới hạn quyền, không dựa vào cookie đăng nhập của người dùng |
| Đăng xuất khỏi trang đăng nhập của Authorization Server | Cookie session của người dùng | CSRF cho POST, vô hiệu hóa session và chuyển hướng an toàn |
| RP-Initiated Logout của OIDC | Yêu cầu logout theo giao thức, thường có `id_token_hint` | Xác minh client, kiểm tra `post_logout_redirect_uri` và bảo toàn `state` |

`state` trong authorization request giúp OAuth client liên kết response với request ban đầu và bảo vệ callback của client khỏi một số kiểu CSRF. `nonce` liên kết ID token với yêu cầu OIDC. Hai giá trị này không thay thế CSRF token cho form đăng nhập, form consent hoặc form logout do Authorization Server phục vụ.

Một quy tắc quan trọng là chỉ cần bảo vệ CSRF cho request thay đổi trạng thái dựa trên thông tin xác thực mà trình duyệt tự động gửi, điển hình là cookie session. Token endpoint thường nhận yêu cầu từ backend của client hoặc từ SPA theo authorization code + PKCE; nó phải kiểm tra cơ chế xác thực OAuth tương ứng. CORS quyết định trình duyệt có được phép đọc phản hồi cross-origin, còn CSRF token xác minh request có được tạo từ ngữ cảnh ứng dụng hợp lệ. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 2. Kiểm thử CSRF

### Vì sao phải giữ CSRF cho đăng nhập và consent?

CSRF xảy ra khi trình duyệt đã có cookie phiên hợp lệ nhưng bị một trang khác dụ gửi request thay mặt người dùng. Trình duyệt có thể tự động đính kèm cookie đến Authorization Server. Nếu server chỉ kiểm tra cookie mà không yêu cầu bằng chứng request được tạo từ trang hợp lệ, một website bên ngoài có thể kích hoạt thao tác ngoài ý muốn.

Trong Authorization Server, những request cần xem xét gồm:

- POST form đăng nhập, nếu ứng dụng dùng form login.
- POST form consent khi người dùng chấp thuận hoặc từ chối scope.
- POST logout để kết thúc session.
- Các form quản trị hoặc thao tác thay đổi cấu hình client nếu chúng được phục vụ trong cùng ứng dụng.

Spring Security bật CSRF protection mặc định cho các HTTP method có thể thay đổi trạng thái, chẳng hạn POST, PUT, PATCH và DELETE. Các method GET, HEAD, TRACE và OPTIONS được xem là an toàn theo quy ước và không yêu cầu CSRF token mặc định. Ứng dụng không nên biến GET thành thao tác thay đổi dữ liệu.

Với form server-rendered, CSRF token cần có mặt trong form. Thymeleaf tích hợp Spring Security có thể tự đưa hidden field vào form POST. Với form HTML tự xây, thêm token rõ ràng:

```html
<form action="/oauth2/authorize" method="post">
  <input type="hidden" name="client_id" value="web-client">
  <input type="hidden" name="state" value="state-from-authorization-request">
  <input type="hidden" name="_csrf" value="${csrfToken}">
  <button type="submit" name="consent_action" value="authorize">
    Chấp thuận
  </button>
</form>
```

Tên parameter và cách render token phải lấy từ `CsrfToken` do Spring Security cung cấp; không tạo token cố định hoặc tự đặt giá trị. Với template engine, dùng biểu thức tích hợp của framework để tránh in nhầm biểu thức chưa được xử lý ra HTML.

### Chỉ miễn CSRF cho endpoint giao thức phù hợp

Các OAuth client không gửi CSRF token của session người dùng khi gọi token endpoint. Vì vậy, một số POST endpoint giao thức cần được loại khỏi CSRF filter, nhưng phạm vi miễn trừ phải cụ thể. Ví dụ dưới đây minh họa các endpoint back-channel mặc định được bảo vệ bằng client authentication:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    RequestMatcher csrfExemptProtocolPosts = request -> {
        if (!"POST".equals(request.getMethod())) {
            return false;
        }
        return Set.of(
                "/oauth2/token",
                "/oauth2/introspect",
                "/oauth2/revoke"
        ).contains(request.getServletPath());
    };

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .csrf(csrf -> csrf.ignoringRequestMatchers(csrfExemptProtocolPosts))
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}
```

Đây là ví dụ minh họa với endpoint mặc định. Nếu đổi `AuthorizationServerSettings`, hãy cập nhật matcher theo các URI thực tế. Nếu bật device authorization hoặc một endpoint POST back-channel khác, chỉ thêm endpoint đó sau khi xác minh request không dựa vào cookie session của người dùng và có cơ chế xác thực giao thức tương ứng.

Không đưa `/oauth2/authorize`, trang xác minh device, form consent, `/login` hoặc `/logout` vào danh sách miễn trừ. Đặc biệt, request POST consent thường đi qua authorization endpoint và vẫn cần CSRF token. Không dùng `ignoringRequestMatchers(authorizationServerConfigurer.getEndpointsMatcher())` như một cách tắt nhanh cho toàn bộ Authorization Server nếu endpoint matcher đó cũng bao phủ các thao tác trình duyệt.

### Viết test CSRF bằng MockMvc

Spring Security Test cung cấp `csrf()` để gửi request có token hợp lệ. Test nên kiểm tra cả trường hợp thiếu token, token sai và token đúng:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CsrfSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "secret"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginPostWithInvalidCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "secret")
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginPostWithValidCsrfReachesAuthentication() throws Exception {
        mockMvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "wrong-password")
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());
    }
}
```

Trong test cuối, thông tin đăng nhập sai vẫn có thể tạo redirect về trang login với thông báo lỗi; mục đích của test là xác nhận request vượt qua CSRF filter và đến được bước xác thực. Hãy điều chỉnh status và URL theo `AuthenticationFailureHandler` thực tế.

Consent POST cũng cần test độc lập. Gửi request thiếu CSRF token phải bị từ chối trước khi consent được ghi nhận; gửi request có token hợp lệ phải đi tiếp đến bước kiểm tra người dùng, client, scope và trạng thái authorization. Không chỉ kiểm tra status code: hãy xác nhận consent trong persistence không thay đổi khi request bị CSRF từ chối.

Với token endpoint được miễn CSRF có chủ đích, test cần chứng minh request không bị chặn bởi CSRF filter nhưng vẫn phải qua xác thực client và kiểm tra grant. Một request thiếu client authentication có thể trả OAuth error như `invalid_client`; điều cần tránh là bị trả `403` do CSRF token của browser. Sau đó thêm test thành công với client hợp lệ và PKCE đúng để xác nhận luồng hoàn chỉnh.

## 3. Kiểm thử CORS

### CORS bảo vệ điều gì?

Same-Origin Policy của trình duyệt hạn chế JavaScript đọc phản hồi từ origin khác. CORS cho phép server công bố origin, method và header nào được phép truy cập tài nguyên cross-origin. CORS không xác thực client, không thay thế CSRF protection và không ngăn mọi request cross-site được gửi đến server. Ví dụ, một HTML form đơn giản có thể gửi request cross-site dù JavaScript ở origin khác không đọc được phản hồi.

Trong OAuth/OIDC, trang `/oauth2/authorize` thường được mở bằng điều hướng trình duyệt và redirect giữa các origin. Điều đó không có nghĩa cần bật CORS rộng cho authorization endpoint. CORS thường cần thiết khi SPA gọi trực tiếp token endpoint từ JavaScript để đổi authorization code bằng PKCE. Chỉ cho phép origin của SPA đã đăng ký và những method/header mà luồng thực sự cần.

### Cấu hình CORS giới hạn cho token endpoint

Ví dụ dưới đây cho phép một SPA cụ thể gọi POST token endpoint. Không bật credential cookie vì token request nên dùng cơ chế OAuth client và PKCE, không dựa vào cookie session của Authorization Server:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration tokenCors = new CorsConfiguration();
    tokenCors.setAllowedOrigins(List.of("https://app.example.com"));
    tokenCors.setAllowedMethods(List.of("POST"));
    tokenCors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    tokenCors.setAllowCredentials(false);
    tokenCors.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/oauth2/token", tokenCors);
    return source;
}
```

Bật CORS trong filter chain phục vụ token endpoint:

```java
http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .cors(Customizer.withDefaults());
```

Đoạn này được ghép vào cấu hình Authorization Server ở phần trước. Nếu token endpoint đã được đổi đường dẫn, cập nhật path đăng ký CORS. Cấu hình CORS cần được xử lý trước bước xác thực để preflight OPTIONS không bị yêu cầu đăng nhập như một request nghiệp vụ.

Không dùng `allowedOrigins("*")` cho hệ thống có cookie hoặc thông tin xác thực trình duyệt. Khi `allowCredentials` bật, origin phải được chỉ định cụ thể; wildcard không phải cách thay thế cho danh sách origin tin cậy. Cũng không phản chiếu tùy tiện giá trị `Origin` do client gửi lên. Nếu cần nhiều môi trường, quản lý danh sách origin theo cấu hình môi trường và kiểm tra khi khởi động.

### Kiểm thử preflight và origin bị từ chối

Trình duyệt thường gửi preflight OPTIONS trước request cross-origin có method hoặc header không đơn giản. Test cần kiểm tra origin hợp lệ nhận được các header CORS phù hợp và origin lạ bị từ chối:

```java
@Test
void tokenEndpointAllowsConfiguredSpaOrigin() throws Exception {
    mockMvc.perform(options("/oauth2/token")
                    .header(HttpHeaders.ORIGIN, "https://app.example.com")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"));
}

@Test
void tokenEndpointRejectsUnconfiguredOrigin() throws Exception {
    mockMvc.perform(options("/oauth2/token")
                    .header(HttpHeaders.ORIGIN, "https://evil.example")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
}
```

Hành vi status của request CORS bị từ chối có thể phụ thuộc cấu hình và phiên bản; trong mọi trường hợp, origin không được phép không được nhận `Access-Control-Allow-Origin` hợp lệ. Bổ sung test request POST thật từ origin được phép và xác minh response có header CORS. Test preflight riêng lẻ chưa chứng minh endpoint xử lý token đúng.

Một bộ test CORS nên bao gồm origin hợp lệ, origin gần giống nhưng khác hostname, HTTP thay cho HTTPS, port khác, method không được phép, header không được phép và request không có `Origin`. Đảm bảo không vô tình mở CORS cho `/oauth2/authorize`, `/login`, `/logout` hoặc toàn bộ `/**` chỉ vì SPA cần gọi `/oauth2/token`.

## 4. Kiểm thử session fixation

### Cơ chế đổi session ID sau đăng nhập

Session fixation xảy ra khi kẻ tấn công biết hoặc kiểm soát được session ID trước lúc người dùng đăng nhập, rồi lợi dụng việc ứng dụng giữ nguyên ID đó sau khi xác thực. Khi người dùng đăng nhập thành công, session ID cần được thay đổi để session trước xác thực không thể trở thành session đã xác thực.

Spring Security cung cấp session fixation protection. Trên servlet container hỗ trợ Servlet 3.1 trở lên, chiến lược mặc định thường dùng `changeSessionId`, tức thay đổi ID của session hiện tại. Có thể khai báo rõ để chính sách dễ đọc và dễ kiểm thử:

```java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

    return http.build();
}
```

Các chiến lược khác có thể gồm `newSession` hoặc `migrateSession`, tùy phiên bản và nhu cầu ứng dụng. `changeSessionId` giữ session hiện tại nhưng đổi định danh; `newSession` tạo session mới; `migrateSession` tạo session mới và chuyển các attribute hiện có. Chọn chiến lược phù hợp với servlet container và dữ liệu ứng dụng lưu trong session. Không chọn `none` chỉ để tránh thay đổi session trong một test.

### Test session ID trước và sau xác thực

Test cần tạo session trước đăng nhập, giữ lại ID cũ, thực hiện login thành công và kiểm tra ID sau xác thực đã thay đổi:

```java
@Test
void sessionIdChangesAfterSuccessfulAuthentication() throws Exception {
    MockHttpSession preAuthSession = new MockHttpSession();
    String oldSessionId = preAuthSession.getId();

    MvcResult result = mockMvc.perform(post("/login")
                    .session(preAuthSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "correct-password"))
            .andExpect(authenticated())
            .andReturn();

    HttpSession authenticatedSession = result.getRequest().getSession(false);
    assertNotNull(authenticatedSession);
    assertNotEquals(oldSessionId, authenticatedSession.getId());
}
```

Test này giả định ứng dụng có user `alice` và mật khẩu kiểm thử tương ứng. Nếu login thành công qua một `AuthenticationSuccessHandler` tùy chỉnh, giữ nguyên kiểm tra session ID và điều chỉnh phần thiết lập dữ liệu.

Kiểm tra thêm các thuộc tính session cần được giữ lại hoặc xóa theo chủ đích. Ví dụ, một thuộc tính phục vụ ngôn ngữ giao diện có thể được chuyển sang session mới; dữ liệu chưa xác thực không nên được coi là bằng chứng xác thực. Với session store phân tán như Spring Session Redis, kiểm tra cả ID mới được lưu và ID cũ không còn khôi phục được session đã xác thực.

MockMvc hữu ích để kiểm tra logic filter, nhưng không mô phỏng hoàn toàn cookie và hành vi session của servlet container thật. Nên có ít nhất một kiểm thử tích hợp chạy trên container tương ứng với production: lấy cookie trước login, đăng nhập, xác minh cookie/session ID đổi và thử dùng lại cookie cũ. Cookie cũ không được truy cập vào tài nguyên cần xác thực.

## 5. Kiểm thử logout và redirect an toàn

### Logout cục bộ của Authorization Server

Đăng xuất cục bộ thường là POST `/logout` khi CSRF protection đang bật. Spring Security sẽ xóa authentication và vô hiệu hóa session theo logout handler. Có thể cấu hình URL đích cố định và xóa cookie session:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .invalidateHttpSession(true)
        .clearAuthentication(true)
        .deleteCookies("JSESSIONID")
        .logoutSuccessUrl("/login?logout"));
```

Tên cookie phải khớp với cấu hình thực tế; nếu dùng Spring Session, tên cookie có thể đã được tùy chỉnh. `logoutSuccessUrl` ở ví dụ là đường dẫn cố định trong cùng ứng dụng. Không lấy trực tiếp `redirect`, `returnUrl` hoặc `next` từ query parameter rồi chuyển hướng mà không kiểm tra.

Test logout cần bao gồm request thiếu CSRF token, request có token hợp lệ, redirect chính xác, session bị vô hiệu hóa và cookie được xóa nếu ứng dụng cấu hình xóa cookie:

```java
@Test
void logoutRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/logout").with(user("alice")))
            .andExpect(status().isForbidden());
}

@Test
void logoutInvalidatesSessionAndUsesFixedRedirect() throws Exception {
    MockHttpSession session = new MockHttpSession();

    mockMvc.perform(post("/logout")
                    .session(session)
                    .with(user("alice"))
                    .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(cookie().maxAge("JSESSIONID", 0));

    assertTrue(session.isInvalid());
}
```

Một số ứng dụng dùng custom `LogoutSuccessHandler` hoặc Spring Session nên response cookie có thể khác. Khi đó hãy kiểm tra hành vi tương đương: session ID cũ không còn hợp lệ, authentication đã bị xóa và redirect chỉ đến URL được cho phép. Không làm test yếu đi bằng cách bỏ kiểm tra session invalidation.

### RP-Initiated Logout của OpenID Connect

Đăng xuất OIDC có mục tiêu rộng hơn logout local: relying party (RP) yêu cầu OpenID Provider kết thúc phiên SSO và có thể chuyển người dùng về callback đã đăng ký. `post_logout_redirect_uri` phải được kiểm tra với danh sách URI đã đăng ký của client. Một URI chỉ khác scheme, hostname, port, path hoặc dấu gạch chéo cũng cần được đánh giá theo quy tắc so khớp của implementation; không dùng kiểm tra chuỗi con kiểu `contains("example.com")`.

Khi đăng ký client, cấu hình URI sau logout cụ thể, ví dụ:

```java
RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("web-client")
        // Các cấu hình client, grant type và redirect URI khác...
        .postLogoutRedirectUri("https://app.example.com/logout/callback")
        .build();
```

Kiểm thử RP-Initiated Logout nên xác minh:

- URI đã đăng ký được chấp nhận theo đúng client và điều kiện giao thức.
- URI chưa đăng ký, URI của hostname gần giống, URI đổi scheme/port hoặc URI trỏ đến domain bên ngoài bị từ chối.
- `id_token_hint` được kiểm tra theo quy tắc của provider; không dùng một token bất kỳ làm bằng chứng phiên hợp lệ.
- `state` được trả lại nguyên vẹn trong redirect hợp lệ để RP đối chiếu với yêu cầu logout ban đầu.
- Trường hợp thiếu hoặc không hợp lệ `post_logout_redirect_uri` đi theo hành vi an toàn đã định nghĩa, chẳng hạn hiển thị trang xác nhận hoặc trang kết thúc cố định.
- Logout thực sự kết thúc session tại provider theo chính sách, kể cả khi redirect bị từ chối.

Không nhầm `logoutSuccessUrl` của Spring Security với `post_logout_redirect_uri` của OIDC. URL đầu tiên điều khiển redirect sau logout local trong ứng dụng; URL thứ hai là tham số giao thức được kiểm tra theo client đã đăng ký. Không cho phép một query parameter tùy ý ghi đè cả hai chính sách.

## 6. Tổ chức các filter chain để test đúng phạm vi

Authorization Server thường cần một filter chain riêng cho các endpoint OAuth2/OIDC và một chain khác cho trang đăng nhập, consent hoặc giao diện ứng dụng. Thứ tự và matcher của chain quyết định filter nào được áp dụng. Cấu hình một chain quá rộng có thể khiến endpoint giao thức nhận nhầm chính sách của trang web, hoặc trang consent vô tình được miễn CSRF.

Một cách tổ chức phổ biến là:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    // Áp dụng cấu hình CSRF và CORS có phạm vi cho endpoint giao thức tại đây.
    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()))
        .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout"));

    return http.build();
}
```

Đây là khung cấu hình để chỉ ra ranh giới giữa hai chain; ghép phần CSRF matcher và CORS source đã trình bày ở trên vào chain Authorization Server. Trang consent có thể được phục vụ qua authorization endpoint, vì vậy phải xác nhận matcher và CSRF policy thực tế vẫn yêu cầu token cho POST consent. Cấu hình filter chain cần được kiểm tra sau mỗi lần thay endpoint hoặc nâng cấp Spring Security/Spring Authorization Server.

## 7. Ma trận kiểm thử bảo mật

Ma trận sau giúp tránh việc chỉ kiểm tra happy path:

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| CSRF | POST login không có token | Bị từ chối; không tạo authentication |
| CSRF | POST login với token sai | Bị từ chối |
| CSRF | POST consent không có token | Bị từ chối; không lưu consent |
| CSRF | POST logout không có token | Bị từ chối; session vẫn còn hiệu lực |
| CSRF | Token endpoint không có CSRF token nhưng client hợp lệ | Request qua CSRF filter và được xử lý theo xác thực client, code và PKCE |
| CORS | Preflight từ origin SPA đã cho phép | Có header CORS đúng origin và method |
| CORS | Origin lạ hoặc hostname giả mạo gần giống | Không có quyền CORS; không trả header allow-origin hợp lệ |
| CORS | Method/header không nằm trong allowlist | Preflight bị từ chối |
| Session fixation | Login thành công từ session trước xác thực | Session ID đổi sau xác thực |
| Session fixation | Dùng lại session ID trước login | Không khôi phục được session đã xác thực |
| Logout local | Logout thành công | Authentication bị xóa, session vô hiệu hóa và redirect đúng URL cố định |
| Logout OIDC | Redirect URI đã đăng ký | Redirect đúng URI và giữ nguyên `state` |
| Logout OIDC | Redirect URI không đăng ký hoặc external attacker origin | Không chuyển hướng đến URI không tin cậy |

Nên chạy test với cùng loại servlet container và session repository như production. Với Redis hoặc kho session phân tán, thêm kiểm thử để xác minh session ID mới được lưu, session cũ bị vô hiệu hóa và hành vi vẫn đúng khi request tiếp theo được chuyển đến instance khác.

## 8. Checklist trước khi phát hành

- [ ] CSRF protection vẫn bật cho login, consent, logout và các form thay đổi trạng thái dựa trên session.
- [ ] Danh sách endpoint miễn CSRF chỉ gồm POST back-channel đã được đánh giá; không miễn authorization/consent hoặc logout.
- [ ] OAuth client authentication, PKCE và kiểm tra authorization code vẫn hoạt động sau khi miễn CSRF cho token endpoint.
- [ ] CORS chỉ bật ở endpoint cần gọi cross-origin, với origin, method và header cụ thể.
- [ ] Không dùng wildcard origin cùng credential cookie; CORS không bị xem là biện pháp thay thế CSRF.
- [ ] Session ID đổi sau xác thực; session cũ không còn truy cập được tài nguyên bảo vệ.
- [ ] Logout yêu cầu CSRF token, xóa authentication và vô hiệu hóa session.
- [ ] Redirect sau logout local dùng URL cố định hoặc allowlist được kiểm tra chặt chẽ.
- [ ] OIDC `post_logout_redirect_uri` được xác minh theo client đã đăng ký; `state` được bảo toàn.
- [ ] Có test dương tính và âm tính cho từng nhóm kiểm soát, chạy trên cấu hình gần production.

Kiểm thử bảo mật hiệu quả phải chứng minh cả request hợp lệ được xử lý và request sai bị chặn tại đúng lớp bảo vệ. Với Spring Authorization Server, giữ ranh giới rõ giữa form dựa trên session, endpoint giao thức OAuth/OIDC và request cross-origin của SPA giúp CSRF, CORS, session fixation và logout redirect hoạt động đúng mà không làm gián đoạn luồng cấp quyền.
