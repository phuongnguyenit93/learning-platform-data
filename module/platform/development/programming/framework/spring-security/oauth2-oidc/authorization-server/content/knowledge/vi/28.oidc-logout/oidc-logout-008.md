# Phân biệt logout phiên SSO, thu hồi token và đăng xuất từng ứng dụng

## 1. Bối cảnh: “Đăng xuất” có nhiều phạm vi

Trong hệ thống OAuth 2.0/OpenID Connect (OIDC) sử dụng **Spring Security**, **Spring Authorization Server** và Spring Boot, người dùng có thể đăng nhập một lần tại OpenID Provider (OP) rồi truy cập nhiều ứng dụng Relying Party (RP). Khi họ bấm “Đăng xuất”, hệ thống cần xác định chính xác trạng thái nào phải kết thúc.

Có ít nhất ba loại trạng thái độc lập:

1. **Phiên cục bộ của một ứng dụng (RP local session):** cookie/session và SecurityContext do chính ứng dụng quản lý.
2. **Phiên SSO tại OP:** phiên đăng nhập của người dùng trên domain của Authorization Server/OpenID Provider.
3. **OAuth authorization/token state:** access token, refresh token và authorization grant đã cấp cho một client.

Ngoài ra, để đăng xuất một người dùng khỏi nhiều ứng dụng, OP và các RP có thể phối hợp bằng OIDC Session Management, Front-Channel Logout hoặc Back-Channel Logout.

Những cơ chế này liên quan với nhau nhưng không tự động thay thế nhau. Xóa cookie của một RP không xóa cookie SSO ở OP. Kết thúc phiên SSO ở OP cũng không tự động làm mọi access token mất hiệu lực. Thu hồi refresh token không xóa phiên đăng nhập đang tồn tại ở các RP.

Bài học thuộc chương **OIDC Logout**, tập trung phân biệt logout phiên SSO, thu hồi token và đăng xuất từng ứng dụng; đồng thời hướng dẫn cấu hình hai phía OP/RP trong Spring.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt local logout, RP-Initiated Logout, logout notification và OAuth token revocation.
2. Giải thích vì sao một người dùng có thể vẫn đăng nhập ở ứng dụng B sau khi đăng xuất khỏi ứng dụng A.
3. Chọn cơ chế phù hợp cho “đăng xuất ứng dụng này”, “đăng xuất SSO” và “đăng xuất mọi ứng dụng”.
4. Hiểu vai trò của `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` và `state`.
5. Phân biệt Front-Channel Logout và Back-Channel Logout.
6. Hiểu `sid`, `sub` và Logout Token trong Back-Channel Logout.
7. Cấu hình local logout và RP-Initiated Logout với Spring Security.
8. Bật OIDC Logout Endpoint và quản lý `SessionRegistry` trong Spring Authorization Server.
9. Phân biệt logout với RFC 7009 Token Revocation.
10. Thiết kế kiểm thử, vận hành và xử lý lỗi trong môi trường nhiều ứng dụng.

## 2. Mô hình nhiều ứng dụng dùng chung SSO

Giả sử doanh nghiệp có ba ứng dụng:

- `portal.example.com`: cổng nhân viên.
- `orders.example.com`: ứng dụng quản lý đơn hàng.
- `reports.example.com`: ứng dụng báo cáo.
- `auth.example.com`: OpenID Provider/Authorization Server.

Người dùng đăng nhập tại OP thông qua portal. Sau đó, họ mở orders và reports; hai ứng dụng này chuyển browser tới OP. Vì OP vẫn có SSO session, người dùng có thể được xác thực mà không phải nhập lại mật khẩu.

Mỗi ứng dụng vẫn có phiên cục bộ riêng. Cookie của `portal.example.com` không phải cookie của `orders.example.com`; cookie SSO của `auth.example.com` cũng là một cookie độc lập.

~~~mermaid
flowchart TB
    U[Browser / End-User]
    OP[OpenID Provider<br/>auth.example.com<br/>SSO Session]
    A[portal.example.com<br/>RP Session A]
    B[orders.example.com<br/>RP Session B]
    C[reports.example.com<br/>RP Session C]
    T[OAuth Token Store<br/>Access / Refresh Tokens]

    U --> A
    U --> B
    U --> C
    A <--> OP
    B <--> OP
    C <--> OP
    A --> T
    B --> T
    C --> T
~~~

Một thao tác logout có thể ảnh hưởng tới một hoặc nhiều thành phần trong sơ đồ. Trước khi triển khai, cần xác định phạm vi logout và cách các thành phần nhận thông báo.

## 3. Ba loại trạng thái cần phân biệt

| Trạng thái | Được quản lý bởi | Ví dụ dữ liệu | Cách kết thúc |
|---|---|---|---|
| RP local session | Từng ứng dụng | HttpSession, session cookie, SecurityContext | Local logout tại RP |
| OP SSO session | Authorization Server/OP | OP HttpSession, SSO cookie, session registry | RP-Initiated Logout hoặc logout tại OP |
| OAuth authorization/token | Authorization Server và Resource Server | Access token, refresh token, authorization grant, token state | Token Revocation, expiry hoặc policy thu hồi |

### 3.1. RP local session

RP thường tạo session riêng sau khi hoàn tất OIDC login. Session này có thể chứa SecurityContext, thông tin người dùng và tham chiếu tới Authorized Client/token được lưu phía server.

Local logout tại RP có thể:

- Xóa SecurityContext.
- Invalidate HttpSession.
- Xóa session cookie của chính domain RP.
- Xóa hoặc đánh dấu token cache của user không còn được sử dụng.
- Chuyển người dùng về trang đã đăng xuất.

Thao tác này không có quyền xóa cookie thuộc domain OP hoặc domain của RP khác.

### 3.2. OP SSO session

OP quản lý phiên đăng nhập dùng chung cho các OIDC client. Khi browser quay lại OP để bắt đầu authorization request mới, cookie SSO cho phép OP nhận ra người dùng đã đăng nhập.

Nếu RP chỉ xóa local session, OP SSO session vẫn còn. Khi người dùng bấm Login lần nữa, OP có thể cấp code mới mà không hiển thị màn hình đăng nhập.

### 3.3. OAuth token và authorization grant

Access token và refresh token là credential đại diện quyền truy cập. Chúng có vòng đời riêng, có thể được lưu trong authorization store và có thể bị thu hồi theo policy.

Xóa session cookie không làm token tự động bị thu hồi. Ngược lại, thu hồi token không nhất thiết xóa browser session của OP hoặc local session của RP.

## 4. Bốn kiểu thao tác người dùng thường gọi chung là logout

| Nhu cầu sản phẩm | Phạm vi mong muốn | Cơ chế phù hợp |
|---|---|---|
| Đăng xuất khỏi ứng dụng hiện tại | Chỉ RP đang mở | Local logout |
| Đăng xuất khỏi SSO | Kết thúc phiên tại OP | RP-Initiated Logout |
| Đăng xuất khỏi mọi ứng dụng đã đăng nhập | OP kết thúc SSO và các RP nhận thông báo, xóa local session | RP-Initiated Logout kết hợp Front/Back-Channel hoặc cơ chế tương đương |
| Đăng xuất và vô hiệu hóa credential | Kết thúc session cần thiết và thu hồi token/grant | Logout flow kết hợp RFC 7009 theo policy |

Không phải mọi sản phẩm đều cần “logout all”. Ứng dụng ngân hàng, quản trị hoặc dữ liệu nhạy cảm có thể yêu cầu thu hồi refresh token và access token khi user logout. Ứng dụng nội bộ có thể chỉ cần local logout khi người dùng chuyển sang tài khoản khác trên cùng máy.

## 5. Local logout: chỉ đăng xuất một ứng dụng

Local logout là thao tác tại RP. Spring Security cung cấp logout support mặc định và có thể cấu hình qua `logout()` DSL.

Ví dụ:

~~~java
@Configuration
@EnableWebSecurity
class ApplicationSecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Với cấu hình servlet mặc định, Spring Security cung cấp endpoint `POST /logout`. Request cần CSRF token khi CSRF protection được bật, đây là mặc định phù hợp cho ứng dụng web dùng cookie/session.

### 5.1. Spring Security làm gì khi local logout?

Các logout handler mặc định thường thực hiện các bước cần thiết để:

- Xóa Authentication khỏi SecurityContext.
- Xóa SecurityContext khỏi repository.
- Invalidate HttpSession nếu có.
- Xóa cookie session theo cấu hình.
- Gọi LogoutSuccessHandler sau khi logout handlers hoàn tất.

Ứng dụng có thể bổ sung handler để xóa dữ liệu session riêng hoặc dọn authorized-client/token cache phía server.

### 5.2. Local logout không kết thúc OP SSO session

Ví dụ người dùng đăng xuất tại `orders.example.com`:

1. Spring Security xóa session của orders.
2. Cookie session của orders hết hiệu lực.
3. Cookie SSO tại `auth.example.com` vẫn còn.
4. Session của portal và reports vẫn còn.
5. Nếu user truy cập orders lần nữa, OP có thể đăng nhập lại ngay nhờ SSO session.

Đây là hành vi đúng khi sản phẩm muốn “Sign out from this application”.

### 5.3. Không dùng GET để thay đổi trạng thái logout

Đối với local logout dùng cookie, giữ CSRF protection và sử dụng POST. Không tạo endpoint GET như `/logout?user=...` để xóa session, vì browser, crawler hoặc trang bên thứ ba có thể kích hoạt request ngoài ý muốn.

Không đặt access token hoặc refresh token trong URL để logout.

## 6. RP-Initiated Logout: yêu cầu OP kết thúc phiên SSO

**OpenID Connect RP-Initiated Logout 1.0** định nghĩa cách RP yêu cầu OP đăng xuất End-User. RP chuyển User Agent tới Logout Endpoint của OP, thường lấy từ Provider Discovery Metadata qua thuộc tính `end_session_endpoint`.

RP-Initiated Logout là thao tác do một ứng dụng khởi tạo, nhưng mục tiêu là phiên người dùng ở OP. Nó có thể được kết hợp với Session Management, Front-Channel Logout và/hoặc Back-Channel Logout để thông báo cho các RP khác.

### 6.1. Các tham số thường dùng

| Tham số | Ý nghĩa |
|---|---|
| `id_token_hint` | ID Token OP đã cấp cho RP; RECOMMENDED để OP nhận diện phiên/user cần logout |
| `post_logout_redirect_uri` | URI OP chuyển browser về sau logout; phải đăng ký trước với OP |
| `state` | Giá trị opaque để RP liên kết callback logout với transaction đã khởi tạo |
| `client_id` | Client ID tại OP; có thể dùng khi không gửi id_token_hint hoặc trong trường hợp được chuẩn cho phép |
| `logout_hint` | Gợi ý nhận diện user theo semantics do OP định nghĩa |
| `ui_locales` | Gợi ý ngôn ngữ giao diện logout |

`id_token_hint` là ID Token đã được OP cấp cho RP, không phải access token. OP dùng nó như một gợi ý về user/session; đây không phải access token để gọi Resource Server.

### 6.2. Luồng RP-Initiated Logout

~~~mermaid
sequenceDiagram
    actor U as End-User / Browser
    participant RP as RP / orders.example.com
    participant OP as OP / auth.example.com
    participant R2 as Other RP / portal.example.com

    U->>RP: POST /logout
    RP->>RP: Xóa local session
    RP-->>U: Redirect tới end_session_endpoint
    U->>OP: GET/POST Logout Endpoint + id_token_hint + state
    OP->>OP: Xác minh hint và tìm OP session
    OP->>OP: Kết thúc OP SSO session
    opt Có logout notification được hỗ trợ
        OP-->>R2: Front-channel hoặc Back-channel logout
        R2->>R2: Xóa session tương ứng
    end
    OP-->>U: Redirect về post_logout_redirect_uri
    U->>RP: Callback + state
    RP->>RP: Kiểm tra state và hiển thị trang logout
~~~

OP phải hỗ trợ GET và POST tại Logout Endpoint theo RP-Initiated Logout specification. RP có thể sử dụng một trong hai phương thức theo implementation và policy.

### 6.3. RP-Initiated Logout không đồng nghĩa logout mọi RP

Khi OP kết thúc SSO session, browser sẽ không còn SSO session đó cho authorization request tiếp theo. Tuy nhiên, các RP khác có thể vẫn giữ local session đã tạo trước đó.

Muốn kết thúc local session tại các RP khác, cần cơ chế thông báo logout mà cả OP và RP hỗ trợ. Không được suy ra rằng chỉ redirect browser qua OP là đủ để xóa session server-side tại tất cả ứng dụng.

## 7. Discovery và end_session_endpoint

RP nên lấy Logout Endpoint từ Provider Configuration Discovery đã xác minh, thay vì tự ghép URL dựa trên một path đoán trước.

Ví dụ metadata rút gọn:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.com/connect/logout"
}
~~~

Đây là ví dụ minh họa. URI thực tế phụ thuộc cấu hình OP. Khi hỗ trợ RP-Initiated Logout và Discovery, metadata cần công bố `end_session_endpoint`; URL này phải dùng HTTPS.

RP nên:

- Tin issuer đã cấu hình hoặc discovery từ nguồn tin cậy.
- Xác minh TLS của OP.
- Chỉ gửi logout request tới endpoint đã được discovery/configuration xác nhận.
- Không nhận logout URL tùy ý từ query parameter của browser.
- Kiểm tra callback state trước khi hoàn tất UI logout.

## 8. post_logout_redirect_uri và state

`post_logout_redirect_uri` cho phép OP chuyển browser về RP sau khi logout. URI này phải được đăng ký trước trong metadata của client, ví dụ `post_logout_redirect_uris` hoặc cơ chế registration tương đương.

Không chấp nhận redirect URL tùy ý từ user input. Nếu OP cho phép open redirect, attacker có thể lợi dụng trang logout đáng tin cậy để đưa người dùng tới website giả mạo.

`state` giúp RP liên kết logout response với request ban đầu. RP cần tạo giá trị khó đoán, lưu trong logout transaction và xác minh khi nhận callback. Không dùng state cố định hoặc tin state do browser tự gửi mà không so khớp.

Ví dụ request logic:

~~~http
GET /connect/logout?
    id_token_hint=SIGNED_ID_TOKEN&
    post_logout_redirect_uri=https%3A%2F%2Forders.example.com%2Flogged-out&
    state=RANDOM_LOGOUT_STATE
Host: auth.example.com
~~~

Trên wire, query parameters cần được URL-encode. Không ghi ID Token hoặc state nhạy cảm vào access log.

## 9. Đăng xuất từ RP bằng Spring Security

Spring Security OAuth2 Client cung cấp `OidcClientInitiatedLogoutSuccessHandler` để triển khai RP-Initiated Logout.

Ví dụ:

~~~java
@Configuration
@EnableWebSecurity
class OidcClientSecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        OidcClientInitiatedLogoutSuccessHandler logoutSuccessHandler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        logoutSuccessHandler.setPostLogoutRedirectUri("{baseUrl}");

        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(logoutSuccessHandler));

        return http.build();
    }
}
~~~

`OidcClientInitiatedLogoutSuccessHandler` sử dụng ClientRegistration để lấy thông tin OP, bao gồm endpoint logout từ discovery khi registration có issuer URI. Handler tạo redirect request sau khi local logout handlers chạy.

### 9.1. Cấu hình ClientRegistration

Ví dụ Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          order-oidc:
            provider: local-op
            client-id: order-web
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          local-op:
            issuer-uri: https://auth.example.com
~~~

Secret trong ví dụ là placeholder. Không commit credential thật vào repository. Client registration cần khớp với client được đăng ký tại OP.

### 9.2. Cấu hình post-logout redirect URI

Giá trị `{baseUrl}` được handler hỗ trợ và được thay bằng base URL của ứng dụng. OP vẫn phải có URI tương ứng trong danh sách post-logout redirect URI được đăng ký cho client.

Không cho phép browser tự truyền một URI bất kỳ vào `setPostLogoutRedirectUri` hoặc logout request.

### 9.3. GET hay POST tới OP?

Spring Security mặc định redirect tới Logout Endpoint bằng HTTP GET. Có thể cấu hình Form Post redirect strategy nếu OP yêu cầu hoặc policy cần POST:

~~~java
logoutSuccessHandler.setRedirectStrategy(new FormPostRedirectStrategy());
~~~

Kiểm tra tương thích với OP và trình duyệt trước khi đổi phương thức. Việc dùng POST tới OP không thay thế CSRF protection của endpoint local logout tại RP.

## 10. Bật OIDC Logout Endpoint ở Spring Authorization Server

Trong Spring Authorization Server 1.x, OIDC cần được bật trên Authorization Server SecurityFilterChain. OIDC configurer đăng ký RP-Initiated Logout Endpoint và các protocol endpoints liên quan.

Ví dụ khung cấu hình:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Trong cấu hình đầy đủ, ứng dụng còn cần RegisteredClientRepository, OAuth2AuthorizationService, token generator, signing key/JWK source, issuer và chain xác thực End-User.

`oidc(Customizer.withDefaults())` bật OIDC Logout Endpoint theo cấu hình mặc định. Khi cần tùy biến logout request, có thể dùng `logoutEndpoint` extension point của `OidcLogoutEndpointConfigurer`.

### 10.1. Extension points của OidcLogoutEndpointConfigurer

Spring Authorization Server 1.5.8 cung cấp các điểm mở rộng như:

- `logoutRequestConverter` / `logoutRequestConverters`: đọc và chuyển HTTP request thành logout authentication token.
- `authenticationProvider` / `authenticationProviders`: xử lý xác thực và validation logout request.
- `logoutResponseHandler`: xử lý thành công và thực hiện logout.
- `errorResponseHandler`: trả OAuth/OIDC error response.

Không thay toàn bộ provider hoặc success handler nếu chưa hiểu đầy đủ validation mặc định. Một custom handler phải giữ kiểm tra ID Token hint, client registration và post-logout redirect URI theo contract.

### 10.2. SessionRegistry trong Authorization Server

Spring Authorization Server dùng `SessionRegistry` để theo dõi các phiên đã xác thực khi OIDC được bật. OIDC Logout Endpoint tra SessionRegistry để tìm SessionInformation tương ứng với End-User yêu cầu logout.

Nếu không đăng ký bean riêng, framework dùng `SessionRegistryImpl` mặc định. Khi đăng ký `SessionRegistryImpl`, nên đăng ký thêm `HttpSessionEventPublisher` để cập nhật registry khi session bị hủy.

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

### 10.3. SessionRegistry trong môi trường nhiều instance

`SessionRegistryImpl` mặc định giữ thông tin trong memory của process. Nếu OP chạy nhiều instance, cần thiết kế session tracking nhất quán giữa các node hoặc dùng cơ chế session/registry chia sẻ phù hợp.

Nếu login được xử lý ở node A nhưng logout request đi tới node B mà node B không tìm thấy session, kết quả có thể không như mong đợi. Kiểm thử load balancer, sticky session, session store và event propagation trong môi trường triển khai thật.

## 11. RegisteredClient và post-logout redirect URI

Client cần đăng ký các URI mà OP được phép redirect tới sau logout. Ví dụ registration:

~~~java
RegisteredClient orderWeb = RegisteredClient
    .withId("order-web-registration")
    .clientId("order-web")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://orders.example.com/login/oauth2/code/order-oidc")
    .postLogoutRedirectUri("https://orders.example.com/logged-out")
    .scope(OidcScopes.OPENID)
    .build();
~~~

Đây là đoạn cấu hình minh họa. Các grant, scope, redirect URI và token settings cần phù hợp client thật.

OP phải xác minh `post_logout_redirect_uri` thuộc danh sách đã đăng ký cho đúng client. Nếu request có `id_token_hint` và `client_id`, OP phải bảo đảm client ID tương ứng với ID Token đã phát hành.

Không dùng wildcard quá rộng như `https://*.example.com/**` cho post-logout redirect URI nếu không có thiết kế registration an toàn.

## 12. Logout một RP hay nhiều RP?

Giả sử user đã đăng nhập ở portal, orders và reports:

| Thao tác | Portal local session | Orders local session | Reports local session | OP SSO session |
|---|---|---|---|---|
| Local logout ở orders | Còn | Xóa | Còn | Còn |
| RP-Initiated Logout từ orders, không có RP notification | Còn | Xóa theo local handler | Có thể còn | Kết thúc |
| OP logout có Back-Channel notification tới cả ba RP | Xóa nếu nhận/validate notification | Xóa | Xóa | Kết thúc |
| Chỉ revoke refresh token của orders | Còn | Có thể vẫn còn | Còn | Còn |
| Revoke token và local logout orders | Còn | Xóa | Còn | Còn, trừ khi có RP-Initiated Logout |

Bảng này giả định mỗi RP có session riêng và OP hỗ trợ các thao tác tương ứng. Kết quả cụ thể phụ thuộc notification mechanism, session correlation và token validation strategy.

## 13. Session Management, Front-Channel và Back-Channel Logout

RP-Initiated Logout là cơ chế RP yêu cầu OP logout. Các cơ chế Session Management, Front-Channel và Back-Channel giải quyết việc thông báo trạng thái logout từ OP tới RP.

| Cơ chế | Đường truyền | Ưu điểm | Hạn chế |
|---|---|---|---|
| Session Management | Browser iframe/postMessage | Theo dõi trạng thái OP session | Phụ thuộc browser, iframe và cookie policy |
| Front-Channel Logout | OP dùng User Agent để gọi logout URI của RP | Dễ tích hợp với xóa cookie/local browser state | Có thể bị browser chặn third-party context, tab đóng hoặc network lỗi |
| Back-Channel Logout | OP gọi trực tiếp RP server-to-server | Không phụ thuộc browser đang mở; phù hợp server-side session | RP phải có endpoint công khai và session store/correlation phù hợp |

RP-Initiated Logout có thể dùng riêng hoặc kết hợp với một hay nhiều cơ chế notification trên. Chọn theo khả năng của OP/RP và yêu cầu sản phẩm.

## 14. Front-Channel Logout

Front-Channel Logout dùng User Agent để truyền yêu cầu logout từ OP tới RP. OP có thể render logout URI của các RP trong iframe; RP nhận request rồi xóa trạng thái phiên liên quan.

Client đăng ký `frontchannel_logout_uri`. Nếu yêu cầu session-specific logout, OP và RP có thể trao đổi thêm `iss` và `sid`.

### 14.1. Cách hoạt động

~~~mermaid
sequenceDiagram
    actor U as Browser
    participant OP as OpenID Provider
    participant RP1 as portal RP
    participant RP2 as orders RP

    U->>OP: Logout tại OP
    OP->>U: Trang logout chứa iframe logout URI
    U->>RP1: GET /frontchannel-logout?iss=...&sid=...
    RP1->>RP1: Xóa session tương ứng
    U->>RP2: GET /frontchannel-logout?iss=...&sid=...
    RP2->>RP2: Xóa session tương ứng
    OP-->>U: Hoàn tất trang logout
~~~

### 14.2. Hạn chế cần tính đến

Front-channel phụ thuộc browser có thể tải các iframe và gửi cookie phù hợp. Cookie SameSite, third-party cookie restrictions, content security policy, browser privacy settings hoặc tab đóng có thể ảnh hưởng việc nhận thông báo.

Vì vậy, Front-Channel Logout có thể hữu ích nhưng không nên được coi là cơ chế đảm bảo mọi RP session đều bị xóa trong mọi điều kiện.

### 14.3. Xác minh thông tin logout

Nếu RP nhận `iss` và `sid`, có thể đối chiếu với session/ID Token đã lưu cho phiên tương ứng. Chỉ xóa đúng session thuộc OP và user đã xác minh. Không xây dựng endpoint logout chỉ dựa vào một tham số user ID không được xác thực.

## 15. Back-Channel Logout

Back-Channel Logout dùng giao tiếp trực tiếp server-to-server. OP gửi HTTP POST tới `backchannel_logout_uri` đã đăng ký của RP và đính kèm Logout Token.

Logout Token là JWT có claims mô tả logout action. RP phải xác minh chữ ký, issuer, audience, thời gian và các claims bắt buộc theo OIDC Back-Channel Logout 1.0 trước khi kết thúc session.

### 15.1. Logout Token và claims

Logout Token thường có:

| Claim | Ý nghĩa |
|---|---|
| `iss` | Issuer của OP |
| `aud` | Client ID/RP nhận logout |
| `iat` | Thời điểm phát hành |
| `jti` | ID duy nhất để phát hiện replay |
| `events` | Phải chứa member `http://schemas.openid.net/event/backchannel-logout` với object rỗng làm giá trị |
| `sid` | Session ID tại OP, nếu logout theo một session |
| `sub` | Subject End-User, nếu logout mọi session RP của subject |

Logout Token phải chứa ít nhất một trong hai claim `sid` hoặc `sub`, và không được chứa claim `nonce`. RP cần xác minh chữ ký bằng khóa của issuer tin cậy, `iss`, `aud`, `iat`, `jti`, event claim và các điều kiện thời gian/replay theo OIDC Back-Channel Logout 1.0.

Logout Token không phải ID Token. Nó phải được xử lý theo validation rules riêng; không đưa nó vào code path xác thực user như một ID Token.

### 15.2. `sid` và `sub` khác nhau thế nào?

- Có `sid`: RP kết thúc session được liên kết với OP session ID đó.
- Có `sub` nhưng không có `sid`: RP kết thúc các session của End-User tương ứng trong client context.
- RP cần kiểm tra `aud` để bảo đảm Logout Token dành cho đúng client.
- `jti` cần được theo dõi để chống xử lý lặp/replay trong khoảng thời gian phù hợp.

Không coi `sid` là định danh user toàn cục. Nó là opaque session identifier trong ngữ cảnh issuer.

### 15.3. Luồng Back-Channel Logout

~~~mermaid
sequenceDiagram
    participant OP as OpenID Provider
    participant RP as orders RP
    participant SR as OIDC Session Registry
    participant DB as Session Store

    OP->>RP: POST backchannel_logout_uri + Logout Token
    RP->>RP: Verify JWT signature, iss, aud, events, iat, jti
    RP->>SR: Tìm session theo sid hoặc sub
    SR->>DB: Invalidate các RP session phù hợp
    DB-->>SR: Session invalidated
    RP-->>OP: HTTP success response
~~~

Request Back-Channel Logout dùng POST form với tham số `logout_token`:

~~~http
POST /logout/connect/back-channel/order-oidc HTTP/1.1
Host: orders.example.com
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN
~~~

RP chỉ xử lý logout sau khi xác minh token và tìm được session khớp `sid` hoặc `sub`. Không nhận một giá trị user ID đơn thuần thay cho Logout Token.

Back-channel đáng tin cậy hơn front-channel trong môi trường server-side vì không phụ thuộc browser. Tuy vậy, endpoint RP phải truy cập được từ OP, có TLS, kiểm tra token chặt chẽ và xử lý idempotent.

## 16. Back-Channel Logout trong Spring Security

Spring Security hỗ trợ RP nhận Back-Channel Logout. Với servlet stack, cần cấu hình OIDC login và back-channel logout support.

Ví dụ theo DSL của Spring Security:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}

@Bean
SecurityFilterChain relyingPartySecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(oidc ->
            oidc.backChannel(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Khi bật, Spring Security đăng ký endpoint dạng:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

`registrationId` là định danh ClientRegistration của RP. OP cần đăng ký URI tương ứng làm back-channel logout URI.

### 16.1. HttpSessionEventPublisher

Spring Security khuyến nghị đăng ký `HttpSessionEventPublisher` để các session đã invalidate được loại khỏi registry:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Nếu không dọn session registry, dữ liệu mapping session có thể còn tồn tại sau khi session đã bị invalidate.

### 16.2. Cookie name và Spring Session

Cơ chế mặc định sử dụng cookie `JSESSIONID` để liên kết session cookie với `OidcSessionInformation`. Nếu ứng dụng dùng Spring Session với cookie mặc định `SESSION`, cần cấu hình session cookie name phù hợp cho handler.

Không thay cookie name tùy tiện sau khi đã triển khai mà không kiểm thử session correlation.

### 16.3. Cluster và OidcSessionRegistry

Spring Security mặc định có thể lưu liên kết OP session và RP session trong memory. Với cluster nhiều instance, nên xem xét custom `OidcSessionRegistry` lưu mapping trong database hoặc distributed store.

Nếu OP gửi Back-Channel Logout tới node A nhưng session mapping chỉ có trên node B, logout có thể không tìm thấy session. Session registry cần nhất quán với session store và lifecycle event.

### 16.4. Phiên bản Spring

API `oidcLogout` và các handler phụ thuộc dòng Spring Security đang dùng. Đối chiếu tài liệu đúng version (6.x/7.x) trước khi sao chép cấu hình; không trộn reactive API với servlet API.

## 17. Spring Authorization Server và giới hạn hỗ trợ cần hiểu rõ

Trong Spring Authorization Server 1.5.8, OIDC Logout Endpoint là implementation của **RP-Initiated Logout**. `OidcLogoutEndpointConfigurer` cung cấp extension points cho request converter, authentication provider, response handler và error handler. `OidcLogoutAuthenticationProvider` dùng `SessionRegistry` để tra session của End-User.

Điều đó cung cấp cơ chế OP xử lý yêu cầu logout và kết thúc phiên được theo dõi. Nó không tự chứng minh rằng mọi RP khác đã xóa local session. Để đạt logout nhiều ứng dụng, OP cần triển khai hoặc tích hợp cơ chế notification mà các RP đăng ký hỗ trợ.

### 17.1. Cấu hình logout endpoint mặc định

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, server ->
        server.oidc(oidc ->
            oidc.logoutEndpoint(Customizer.withDefaults())
        )
    );
~~~

Đây là phần cấu hình endpoint; ứng dụng vẫn cần các bean và filter chain đầy đủ của Authorization Server. Khi chỉ bật OIDC mặc định, logout endpoint được cấu hình theo defaults của framework.

### 17.2. Tùy biến validation

Spring Authorization Server có default validator kiểm tra `post_logout_redirect_uri`. Nếu thay đổi validator, phải giữ nguyên allowlist/registration validation và ném `OAuth2AuthenticationException` khi request không hợp lệ.

Không cho phép bất kỳ redirect URI nào do browser gửi. Không bỏ kiểm tra client ID/ID Token hint để “logout luôn thành công”.

### 17.3. Phân biệt OP session với RP session registry

SessionRegistry của Spring Authorization Server theo dõi phiên đã xác thực ở OP. OidcSessionRegistry của Spring Security OAuth2 Client theo dõi liên kết giữa OP session và session cục bộ tại RP. Đây là hai registry ở hai vai trò khác nhau, không thể dùng một registry thay cho registry kia nếu không có integration rõ ràng.

## 18. Token Revocation theo RFC 7009

Token Revocation là một giao thức OAuth riêng, cho phép client thông báo Authorization Server rằng access token hoặc refresh token không còn được sử dụng.

RFC 7009 định nghĩa request HTTP POST tới Revocation Endpoint, dùng `application/x-www-form-urlencoded` và xác thực client theo cơ chế OAuth đã đăng ký.

Ví dụ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

`token_type_hint` có thể là `access_token` hoặc `refresh_token`. Đây chỉ là hint hỗ trợ tra cứu; nếu không tìm thấy token theo hint, AS phải mở rộng tìm kiếm theo các token type được hỗ trợ.

### 18.1. Revocation response

Theo RFC 7009, AS trả HTTP 200 khi token đã được revoke thành công hoặc token gửi lên không hợp lệ. Cách trả lời này tránh tiết lộ token nào tồn tại, giúp giảm token enumeration.

Client cần xác thực với AS và chỉ được revoke token thuộc client đó theo validation của server.

### 18.2. Revocation không tự động logout browser

Revocation làm token/authorization state mất hiệu lực theo policy của AS. Nó không tự xóa cookie SSO ở OP hoặc session cookie ở RP.

Ví dụ revoke refresh token của `orders-web`:

- OP có thể không còn cấp access token mới từ refresh token đó.
- Local session của orders có thể vẫn còn.
- Browser vẫn có thể có SSO session tại OP.
- Portal và reports không tự động bị logout.
- User có thể cần login lại hoặc cấp quyền lại khi ứng dụng cần token mới.

Nếu sản phẩm muốn cả logout lẫn revoke, phải thực hiện cả hai hành động theo trình tự và policy.

## 19. Revocation của JWT access token và opaque token

Hiệu quả thu hồi phụ thuộc cách Resource Server xác minh access token.

| Loại access token | Cách RS xác minh | Hệ quả khi revoke |
|---|---|---|
| JWT self-contained | Xác minh chữ ký/claims cục bộ | RS offline có thể tiếp tục chấp nhận JWT tới khi hết hạn nếu không có denylist/event/status check |
| Opaque/reference | Gọi introspection hoặc tra state tập trung | Có thể nhận trạng thái inactive sau khi revocation được cập nhật và lan truyền |
| JWT + revocation list/event | Local validation kết hợp trạng thái tập trung | Có thể rút ngắn thời gian từ revoke tới deny, tùy propagation |

RFC 7009 quy định server vô hiệu token và token liên quan theo policy. Nhưng với JWT access token đã phát và được RS xác minh offline, RS không tự biết token đã bị revoke nếu không có cơ chế cập nhật trạng thái.

Vì vậy, nếu cần hiệu lực revoke gần như tức thời, cân nhắc opaque token + introspection, denylist/shared status, event propagation hoặc access token TTL ngắn. Mỗi lựa chọn có chi phí latency, availability và consistency khác nhau.

### 19.1. Revoke refresh token có thể ảnh hưởng access token liên quan

RFC 7009 quy định nếu AS hỗ trợ revoke access token, khi revoke refresh token thì AS SHOULD revoke các access token dựa trên cùng grant. Nếu AS không hỗ trợ revoke access token, JWT đã phát có thể còn hiệu lực đến khi hết hạn.

Không hứa với người dùng rằng “revoke refresh token” chắc chắn cắt mọi request API ngay lập tức nếu Resource Server đang validate JWT offline.

## 20. Kết hợp local logout, RP-Initiated Logout và revocation

Một luồng logout toàn diện có thể gồm:

1. RP nhận POST logout đã được CSRF bảo vệ.
2. RP lưu lại ID Token hint và token references cần thiết trước khi xóa Authentication.
3. RP xóa local session và cookie.
4. Backend của RP gọi Revocation Endpoint cho refresh/access token theo policy và credential hợp lệ.
5. RP redirect browser tới OP Logout Endpoint bằng ID Token hint.
6. OP kết thúc SSO session.
7. OP gửi Front-Channel/Back-Channel notification tới các RP đã đăng ký.
8. Các RP nhận notification xác minh và xóa session tương ứng.
9. RP ban đầu xử lý post-logout callback và kiểm tra state.

Thứ tự có thể khác tùy kiến trúc. Nếu local logout handler xóa Authentication trước, cần lưu ID Token/authorized client cần thiết trong transaction an toàn để logout handler vẫn có dữ liệu tạo request tới OP.

### 20.1. Không để lỗi revocation chặn local logout vô thời hạn

Local logout phải kết thúc session tại RP ngay cả khi AS tạm unavailable. Có thể ghi nhận revocation pending và retry ở backend theo policy, nhưng không giữ user authenticated chỉ vì endpoint revoke timeout.

Nếu không thể revoke, cần ghi rõ trạng thái vận hành và áp dụng TTL/incident policy. Không log raw token trong retry queue hoặc audit.

### 20.2. Đừng revoke token của ứng dụng khác

Client chỉ nên revoke token được cấp cho chính client đó. Không lấy token của portal, orders hoặc reports rồi gửi từ client khác để cố thu hồi. Token ownership và client authentication phải được AS kiểm tra.

## 21. Cookie, session store và logout an toàn

Logout có hiệu lực khi cả trạng thái phía server và cookie phía browser được xử lý đúng.

### 21.1. Xóa session server-side

Invalidate HttpSession hoặc xóa session record khỏi distributed session store. Chỉ xóa cookie phía browser nhưng để session server tồn tại có thể tạo session orphan và làm phức tạp audit/cleanup.

### 21.2. Xóa cookie đúng domain/path

RP chỉ có thể xóa cookie thuộc domain/path mà nó kiểm soát. `orders.example.com` không thể trực tiếp xóa cookie host-only của `auth.example.com` hoặc cookie của `portal.example.com`.

Cookie cần được xóa với các thuộc tính Domain/Path phù hợp cookie ban đầu. Cookie session nên có Secure, HttpOnly và SameSite policy phù hợp flow.

### 21.3. Session fixation và chuyển tài khoản

Sau khi xác thực user mới, RP cần session fixation protection theo Spring Security. Khi logout và login bằng tài khoản khác, không tái sử dụng state/session cũ chứa identity hoặc token cache của user trước.

### 21.4. CSRF và logout endpoint

Local logout qua browser cookie nên dùng POST và CSRF protection. Back-channel endpoint là machine-to-machine protocol endpoint; chỉ miễn CSRF cho đúng endpoint theo cấu hình framework và phải xác minh Logout Token theo chuẩn.

Không tắt CSRF toàn bộ ứng dụng chỉ để Back-Channel Logout hoạt động.

## 22. Kiểm thử logout trong hệ thống nhiều ứng dụng

### 22.1. Ma trận local logout và SSO

| Kịch bản | Kết quả mong đợi |
|---|---|
| Local logout ở RP A | Chỉ session A bị xóa |
| RP A logout rồi login lại khi OP session còn | Có thể đăng nhập lại không cần nhập credential |
| RP-Initiated Logout ở RP A | OP xử lý logout request và kết thúc SSO session theo policy |
| OP logout không có RP notification | Local session B/C có thể còn |
| OP logout có Back-Channel notification | RP nhận và xóa đúng session được chỉ định |
| User đăng nhập lại sau OP logout | OP yêu cầu authentication mới nếu không còn session hợp lệ |

### 22.2. Ma trận token revocation

| Kịch bản | Kết quả mong đợi |
|---|---|
| Revoke refresh token hợp lệ | AS đánh dấu token inactive |
| Revoke token không tồn tại | HTTP 200 theo RFC 7009 |
| Revoke bằng client credential sai | AS từ chối client authentication |
| Revoke token thuộc client khác | AS từ chối theo ownership validation |
| Revoke refresh token có access token liên quan | Kết quả cascade theo policy và RFC |
| JWT access token được validate offline | Có thể còn hiệu lực tới exp nếu không có status check |
| Opaque token được introspect | RS nhận inactive khi trạng thái revoke đã được cập nhật |
| AS trả 503 | Client coi token vẫn có thể tồn tại và retry theo Retry-After/policy |

### 22.3. Ma trận Front-Channel và Back-Channel

- Browser chặn third-party cookie hoặc iframe.
- Browser đóng tab trước khi nhận Front-Channel request.
- RP không reachable từ OP.
- Logout Token sai chữ ký.
- Logout Token sai issuer hoặc audience.
- Logout Token thiếu event claim.
- Logout Token bị replay với cùng jti.
- Logout Token chứa sid không tồn tại.
- Logout Token chứa sub và nhiều RP session.
- RP chạy nhiều instance với session registry phân tán.
- Session cookie name khác JSESSIONID.
- Notification tới cùng session được gửi nhiều lần.

Kết quả mong đợi là RP chỉ kết thúc session khớp issuer, client và subject/session đã xác minh; xử lý lặp phải idempotent.

## 23. Integration test với Spring Security và Spring Authorization Server

### 23.1. Test local logout

Dùng MockMvc:

~~~java
mockMvc.perform(post("/logout")
        .with(csrf())
        .with(user("user-42")))
    .andExpect(status().is3xxRedirection());
~~~

Test cần xác minh session không còn authenticated và cookie/session state được xử lý đúng. Đường dẫn redirect phụ thuộc LogoutSuccessHandler.

### 23.2. Test RP-Initiated Logout

- Đăng nhập bằng OIDC test provider.
- Gửi POST tới local logout endpoint với CSRF token.
- Xác minh local session đã bị xóa.
- Xác minh redirect tới end_session_endpoint đã lấy từ ClientRegistration/discovery.
- Kiểm tra id_token_hint và post_logout_redirect_uri được tạo đúng.
- Kiểm tra state callback được đối chiếu với transaction.
- Kiểm tra redirect URI chưa đăng ký bị từ chối tại OP.

### 23.3. Test OIDC Logout Endpoint của OP

Với Spring Authorization Server:

- Bật OIDC configurer.
- Đăng nhập End-User và đăng ký session trong SessionRegistry.
- Gửi request logout với ID Token hint hợp lệ.
- Xác minh provider tìm đúng session và xử lý logout.
- Thử ID Token hint sai issuer/client.
- Thử post_logout_redirect_uri chưa đăng ký.
- Thử client_id không khớp ID Token hint.
- Kiểm tra SessionRegistry được cleanup khi HttpSession bị invalidate.

### 23.4. Test Back-Channel Logout của RP

- Đăng nhập RP và lưu mapping OP session ID với RP session ID.
- Gửi Logout Token ký bằng test key tin cậy.
- Xác minh đúng audience/issuer/events/iat/jti.
- Gửi token có sid và xác minh chỉ session tương ứng bị xóa.
- Gửi token có sub và xác minh các session của subject trong client context bị xóa.
- Gửi token sai chữ ký hoặc replay và xác minh bị từ chối.
- Chạy test qua nhiều node để kiểm tra registry consistency.

## 24. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ local logout xóa SSO session | User quay lại app vẫn được đăng nhập tự động | Dùng RP-Initiated Logout nếu muốn kết thúc OP session |
| Nghĩ OP logout tự xóa session mọi RP | Ứng dụng khác vẫn giữ session | Bật Front/Back-Channel hoặc cơ chế notification |
| Nghĩ revoke token xóa browser session | User vẫn thấy đang đăng nhập ở RP/OP | Kết hợp session logout |
| Nghĩ revoke refresh token luôn cắt JWT access token ngay | API vẫn nhận JWT còn hạn | Dùng introspection/denylist/event hoặc TTL ngắn |
| Gửi access token làm id_token_hint | OP không xác định đúng phiên | Gửi ID Token đã được OP cấp cho RP |
| Không đăng ký post_logout_redirect_uri | OP từ chối callback hoặc không redirect | Đăng ký URI chính xác |
| Chấp nhận redirect URI từ browser | Open redirect/phishing | Allowlist theo client |
| Dùng state cố định | Logout callback injection/CSRF | Tạo state ngẫu nhiên theo transaction |
| Không có SessionRegistry phù hợp | OP không tìm được session | Kiểm tra session registration và event publisher |
| Dùng SessionRegistry memory trong cluster | Logout phụ thuộc node | Dùng registry/session store chia sẻ |
| Back-channel không validate Logout Token | Attacker có thể ép logout user | Verify signature, iss, aud, events, iat, jti |
| Không kiểm tra sid/sub | Logout nhầm quá nhiều hoặc quá ít session | Áp dụng đúng semantics |
| Front-channel là cơ chế duy nhất | Logout notification có thể bị browser chặn | Cân nhắc Back-Channel |
| Xóa cookie nhưng không invalidate server session | Session orphan hoặc vẫn còn hiệu lực phía server | Xóa cả session store |
| Tắt CSRF toàn ứng dụng cho logout | Tăng bề mặt CSRF | Giữ POST local logout và cấu hình chính xác protocol endpoint |
| Log ID Token/refresh token/Logout Token | Rò rỉ credential hoặc PII | Redact token, giới hạn audit |
| Không kiểm thử callback và nhiều app | Hành vi logout khác kỳ vọng sản phẩm | Test multi-RP end-to-end |

## 25. Observability và runbook

### 25.1. Metrics nên theo dõi

- Local logout success/failure theo RP.
- RP-Initiated Logout request và OP response.
- OIDC logout error theo client/error code.
- SessionRegistry active sessions và cleanup failures.
- Front-Channel/Back-Channel notification success, latency và retry.
- Logout Token validation failures: signature, issuer, audience, event, replay.
- Token revocation success/failure, 503 và Retry-After.
- Thời gian từ logout tại OP tới lúc RP session bị invalidate.
- Access token còn được Resource Server chấp nhận sau revoke.
- Session count và token count sau logout theo policy.

Không đưa raw token, ID Token, Logout Token, refresh token hoặc PII vào metric labels.

### 25.2. Audit event

Có thể ghi event:

~~~text
RP_LOCAL_LOGOUT_COMPLETED
RP_INITIATED_LOGOUT_REQUESTED
OP_SSO_SESSION_TERMINATED
OIDC_FRONTCHANNEL_LOGOUT_SENT
OIDC_BACKCHANNEL_LOGOUT_SENT
RP_BACKCHANNEL_LOGOUT_RECEIVED
RP_SESSION_INVALIDATED
OAUTH_TOKEN_REVOCATION_REQUESTED
OAUTH_TOKEN_REVOCATION_COMPLETED
OAUTH_TOKEN_REVOCATION_FAILED
~~~

Audit nên chứa correlation ID, client ID, issuer, session identifier đã pseudonymize, token fingerprint khi cần, outcome và timestamp. Không ghi raw credential.

### 25.3. Runbook khi user vẫn đăng nhập sau logout

1. Xác định user bấm local logout hay RP-Initiated Logout.
2. Kiểm tra local HttpSession và session cookie của RP đã bị xóa chưa.
3. Kiểm tra OP SSO cookie/session còn tồn tại không.
4. Kiểm tra browser có được redirect tới end_session_endpoint không.
5. Kiểm tra OP có nhận id_token_hint và tìm được session trong SessionRegistry không.
6. Kiểm tra OP có gửi notification tới các RP khác không.
7. Kiểm tra Back-Channel Logout Token và RP session registry.
8. Kiểm tra access token/refresh token còn active không và Resource Server xác minh theo JWT hay introspection.
9. Kiểm tra session store, cache, clock, proxy và cookie SameSite/Domain/Path.
10. Đối chiếu với yêu cầu sản phẩm: logout một app, SSO hay mọi app.

Không khắc phục bằng cách xóa mọi token của mọi client khi chưa xác định phạm vi và quyền sở hữu.

## 26. Checklist production

- [ ] Đã phân định local RP session, OP SSO session và OAuth token state.
- [ ] Local logout dùng POST và giữ CSRF protection.
- [ ] RP local logout invalidate server session và xóa cookie đúng domain/path.
- [ ] RP-Initiated Logout dùng end_session_endpoint từ OP Discovery đáng tin cậy.
- [ ] id_token_hint là ID Token do OP cấp cho đúng RP.
- [ ] post_logout_redirect_uri được đăng ký trước và kiểm tra theo client.
- [ ] state được tạo theo transaction và xác minh khi callback.
- [ ] Spring Authorization Server bật OIDC Logout Endpoint đúng phiên bản.
- [ ] SessionRegistry theo dõi session OP và được cleanup qua session lifecycle events.
- [ ] Session registry hoạt động nhất quán khi OP chạy nhiều instance.
- [ ] Đã quyết định có cần Front-Channel/Back-Channel notification hay không.
- [ ] RP Back-Channel Logout endpoint xác minh chữ ký, iss, aud, events, iat và jti.
- [ ] sid/sub được xử lý đúng phạm vi session.
- [ ] RP session registry được chia sẻ nếu RP chạy nhiều instance.
- [ ] Token revocation dùng RFC 7009 và xác thực client.
- [ ] Không giả định JWT offline mất hiệu lực ngay sau revocation.
- [ ] Refresh token, access token và session cookie có policy riêng.
- [ ] Lỗi revocation không giữ local user session sống vô thời hạn.
- [ ] Không log ID Token, refresh token, access token hoặc Logout Token thô.
- [ ] Có integration test cho local logout, RP-Initiated, notification và token revocation.
- [ ] Có metrics, audit và runbook cho logout propagation.

### Kiến thức cốt lõi

**Local logout** kết thúc phiên của một ứng dụng. **RP-Initiated Logout** yêu cầu OpenID Provider kết thúc phiên SSO của End-User. Để các ứng dụng khác cũng xóa local session, OP và RP cần phối hợp bằng Session Management, Front-Channel Logout hoặc Back-Channel Logout.

**Token Revocation theo RFC 7009** là thao tác riêng để vô hiệu access/refresh token theo policy của Authorization Server. Nó không tự xóa browser session. Với JWT access token được Resource Server xác minh offline, token có thể còn được chấp nhận tới khi hết hạn nếu không có cơ chế kiểm tra trạng thái bổ sung.

Trong Spring Security, dùng `logout()` cho local logout và `OidcClientInitiatedLogoutSuccessHandler` để khởi tạo RP-Initiated Logout. Trong Spring Authorization Server, bật OIDC Logout Endpoint và quản lý `SessionRegistry`. Với yêu cầu logout nhiều ứng dụng, triển khai notification và session correlation rõ ràng; kiểm thử cả trường hợp browser không nhận Front-Channel và Back-Channel chạy qua nhiều instance.

## Tài liệu tham khảo

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0-final.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0-final.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
