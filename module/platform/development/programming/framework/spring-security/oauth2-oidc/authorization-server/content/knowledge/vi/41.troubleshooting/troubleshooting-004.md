# redirect_uri mismatch và lỗi post_logout_redirect_uri

Hai lỗi URI thường gặp khi tích hợp OAuth 2.0 và OpenID Connect là Authorization Server từ chối callback sau khi người dùng đăng nhập, hoặc người dùng đã đăng xuất nhưng không được chuyển về ứng dụng. Cả hai thường xuất phát từ việc URI gửi trong request không khớp với URI đã đăng ký cho client. Tuy nhiên, hai tham số phục vụ hai giai đoạn khác nhau và được kiểm tra bằng hai danh sách đăng ký riêng.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, ta quản lý client, consent, authorization code, token và các endpoint OIDC. Bài thuộc chương **Chẩn đoán lỗi**, tập trung vào cách tìm nguyên nhân của **redirect_uri mismatch** trong Authorization Code flow và **post_logout_redirect_uri** trong RP-Initiated Logout. Mục tiêu là xác định URI nào đang được gửi, URI nào đã đăng ký và thành phần nào tạo ra sai khác.

## 1. Phân biệt hai URI và thời điểm kiểm tra

**redirect_uri** là callback mà Authorization Server dùng để trả authorization response về client sau khi người dùng hoàn tất authorization. Nó xuất hiện trong authorization request và thường được gửi lại khi client đổi authorization code tại token endpoint. Authorization code được ràng buộc với client và redirect URI đã dùng trong flow.

**post_logout_redirect_uri** là địa chỉ mà OpenID Provider (OP) có thể chuyển trình duyệt đến sau khi hoàn tất RP-Initiated Logout. URI này được gửi đến OIDC logout endpoint cùng thông tin nhận diện phiên/client, thường là id_token_hint và có thể có state. URI phải nằm trong danh sách post-logout redirect URI đã đăng ký cho client.

| Tham số | Luồng | Endpoint kiểm tra | Danh sách đăng ký |
|---|---|---|---|
| **redirect_uri** | OAuth 2.0 Authorization Code | Authorization endpoint và token endpoint | RegisteredClient redirect URIs |
| **post_logout_redirect_uri** | OpenID Connect RP-Initiated Logout | OIDC logout endpoint | RegisteredClient post-logout redirect URIs |

Hai danh sách này độc lập. Đăng ký callback đăng nhập không tự động cho phép dùng cùng địa chỉ sau khi logout. Tương tự, thêm URI vào danh sách post-logout không sửa được lỗi callback khi đổi authorization code.

Luồng Authorization Code:

~~~mermaid
sequenceDiagram
    participant B as Browser / Client
    participant AS as Authorization Server
    B->>AS: /oauth2/authorize với redirect_uri
    AS->>AS: So khớp URI với client đã đăng ký
    AS-->>B: Redirect về callback với code và state
    B->>AS: /oauth2/token với code và redirect_uri
    AS->>AS: Kiểm tra code, client và redirect_uri
    AS-->>B: Access token (và token khác nếu được cấp)
~~~

Luồng RP-Initiated Logout:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    B->>RP: Đăng xuất khỏi ứng dụng
    RP->>OP: end_session_endpoint với id_token_hint và post_logout_redirect_uri
    OP->>OP: Xác thực phiên và URI đã đăng ký
    OP-->>B: Redirect về post-logout URI cùng state nếu hợp lệ
~~~

## 2. Xác định chính xác URI được đăng ký

Trong Spring Authorization Server, callback và post-logout callback được khai báo riêng trên RegisteredClient. Ví dụ sau đăng ký một ứng dụng web local có Authorization Code và OIDC:

~~~java
RegisteredClient webClient = RegisteredClient
        .withId("web-client-id")
        .clientId("web-client")
        .clientSecret(passwordEncoder.encode("local-client-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("http://127.0.0.1:8080/login/oauth2/code/web-client")
        .postLogoutRedirectUri("http://127.0.0.1:8080/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .requireProofKey(true)
                .build())
        .build();
~~~

Public client có thể dùng ClientAuthenticationMethod.NONE và không khai báo client secret. Phần quan trọng ở đây là callback đăng nhập được thêm bằng **redirectUri(...)**, còn địa chỉ sau logout được thêm bằng **postLogoutRedirectUri(...)**. Kiểm tra API của phiên bản Spring Authorization Server trong dự án nếu builder có khác biệt; không thay thế hai thuộc tính bằng một danh sách dùng chung.

Nếu client có nhiều callback hợp lệ, gọi redirectUri nhiều lần. Nếu có nhiều địa chỉ sau logout, gọi postLogoutRedirectUri nhiều lần. Chỉ đăng ký các địa chỉ thực sự thuộc quyền kiểm soát của ứng dụng:

~~~java
RegisteredClient webClient = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret(passwordEncoder.encode("local-client-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/login/oauth2/code/web-client")
        .redirectUri("https://app.example.com/oauth/callback")
        .postLogoutRedirectUri("https://app.example.com/")
        .postLogoutRedirectUri("https://app.example.com/signed-out")
        .scope(OidcScopes.OPENID)
        .build();
~~~

Trong cấu hình JDBC, các URI này được lưu cùng RegisteredClient. Nếu thay đổi cấu hình Java nhưng ứng dụng đang đọc client từ database, giá trị trong database mới là dữ liệu được dùng khi xử lý request. Kiểm tra đúng record client trong kho dữ liệu qua công cụ quản trị có quyền phù hợp; không suy luận rằng bean cấu hình đã ghi đè record đang tồn tại.

Không dùng wildcard như **https://*.example.com/** hoặc cho phép mọi URI do request gửi lên. Redirect URI là ranh giới bảo mật: nếu kẻ tấn công có thể điều khiển nơi Authorization Server gửi authorization response, authorization code có thể bị chuyển đến endpoint không đáng tin cậy.

## 3. Kiểm tra redirect_uri trong Authorization Code flow

Với một web client Spring Security OAuth2 Client, callback mặc định thường có dạng:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ, khi ứng dụng chạy tại **http://127.0.0.1:8080** và registration ID là **web-client**, URI được gửi thường là:

~~~text
http://127.0.0.1:8080/login/oauth2/code/web-client
~~~

Đăng ký chính xác giá trị này trong Authorization Server. Cấu hình client có thể đặt redirect URI tường minh:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-client:
            provider: local-authorization-server
            client-id: web-client
            client-secret: ${WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          local-authorization-server:
            issuer-uri: https://identity.example.com
~~~

Trong YAML, placeholder **{baseUrl}** được Spring Security OAuth2 Client thay bằng base URL của request. Nếu ứng dụng đứng sau reverse proxy, base URL mà ứng dụng nhận được có thể khác URL người dùng nhìn thấy. Ví dụ proxy kết thúc TLS bên ngoài bằng HTTPS nhưng chuyển tiếp đến ứng dụng qua HTTP; nếu forwarded headers không được xử lý đúng, client có thể tạo callback bắt đầu bằng **http://** thay vì **https://**.

Đối chiếu các thành phần sau theo đúng thứ tự:

1. Giá trị **redirect-uri** trong ClientRegistration hoặc URL được public client tạo ra.
2. Tham số **redirect_uri** thực tế trong request đến authorization endpoint.
3. URI trong danh sách redirect URIs của RegisteredClient được Authorization Server sử dụng.
4. Tham số **redirect_uri** trong request đổi code tại token endpoint.
5. URI được gắn với authorization code mà server đã lưu.

Các giá trị phải khớp theo quy tắc của Authorization Server. Theo OAuth 2.0, so khớp redirect URI thông thường là so sánh chính xác chuỗi URI đã đăng ký. Không giả định server sẽ tự chuẩn hóa các URI có vẻ tương đương về mặt trình duyệt.

RFC 8252 có ngoại lệ hẹp cho native app dùng loopback IP literal như **127.0.0.1** hoặc **[::1]**: port có thể thay đổi theo cổng listener được hệ điều hành cấp. Ngoại lệ này dành cho loopback redirect URI của native app, không phải quy tắc chung cho web client và không cho phép wildcard hostname. Khi dùng Spring Authorization Server, xác minh phiên bản và cách triển khai validator có hỗ trợ ngoại lệ này trước khi chọn port động.

Những sai khác nhỏ nhưng thường gây lỗi:

| Sai khác | Ví dụ |
|---|---|
| Hostname | **localhost** và **127.0.0.1** |
| Scheme | **http** và **https** |
| Port | **8080** và **8443** |
| Path | **/callback** và **/login/oauth2/code/web-client** |
| Dấu gạch cuối | **/callback** và **/callback/** |
| Context path | **/app/callback** và **/callback** |
| Chữ hoa/thường | **/Callback** và **/callback** |
| Query string | URI có và không có **?tenant=demo** |
| Encoding | Ký tự được percent-encode một lần hoặc hai lần |

Không tự loại bỏ dấu gạch cuối, đổi hostname hoặc decode rồi encode lại URI để ép hai giá trị khớp. Hãy chọn một URI chuẩn và dùng cùng giá trị trong client, cấu hình server và môi trường triển khai.

### Kiểm tra token request

Sau khi Authorization Server chuyển trình duyệt về callback, client đổi authorization code tại token endpoint. Nếu authorization request đã gửi redirect_uri, token request phải gửi lại cùng giá trị:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fweb-client
~~~

Nếu URI ở token request khác URI dùng trong authorization request, Authorization Server phải từ chối đổi code. Tùy thời điểm sai khác, lỗi có thể xuất hiện tại authorization endpoint hoặc token endpoint. Ở token endpoint, lỗi thường được biểu diễn bằng OAuth error **invalid_grant** vì authorization code không còn hợp lệ cho request hiện tại. Không xử lý bằng cách bỏ redirect_uri khỏi token request nếu tham số đó đã được dùng ở authorization request.

## 4. Kiểm tra post_logout_redirect_uri trong OIDC logout

RP-Initiated Logout bắt đầu từ Relying Party (RP), thường là ứng dụng web. RP điều hướng trình duyệt đến **end_session_endpoint** của OpenID Provider. Endpoint này được công bố trong OpenID Provider Configuration khi nhà cung cấp hỗ trợ logout.

Một logout request thường có các tham số:

| Tham số | Mục đích |
|---|---|
| **id_token_hint** | ID Token đã được cấp cho RP, giúp OP nhận diện phiên và client liên quan |
| **post_logout_redirect_uri** | Địa chỉ người dùng sẽ quay lại sau khi OP xử lý logout |
| **state** | Giá trị RP tạo để đối chiếu response sau logout |
| **client_id** | Có thể dùng trong một số trường hợp để nhận diện RP theo hỗ trợ của OP |

Khi có post_logout_redirect_uri, OP kiểm tra URI đó thuộc danh sách post-logout URI đã đăng ký cho client tương ứng. URI phải là địa chỉ tuyệt đối hợp lệ và không có fragment. Nếu URI không được đăng ký hoặc không thể xác định client hợp lệ, OP không được chuyển trình duyệt đến địa chỉ tùy ý do request cung cấp.

Với Spring Authorization Server, cần bật OIDC logout endpoint trong cấu hình Authorization Server. Ví dụ theo API cấu hình của các phiên bản hỗ trợ logout endpoint:

~~~java
http.with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(oidc ->
                oidc.logoutEndpoint(Customizer.withDefaults())
        )
);
~~~

Kiểm tra cấu hình endpoint và phiên bản thư viện của dự án nếu API DSL có khác biệt. OIDC logout endpoint không được bật chỉ vì client đã đăng ký scope **openid**; cần cấu hình endpoint và thành phần xử lý logout tương ứng.

### Cấu hình RP trong Spring Security

Spring Security cung cấp **OidcClientInitiatedLogoutSuccessHandler** để tạo logout request dựa trên metadata của provider và ID Token của phiên đăng nhập:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository clientRegistrationRepository) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(
                    clientRegistrationRepository);

    handler.setPostLogoutRedirectUri("{baseUrl}");
    return handler;
}
~~~

Gắn handler vào logout configuration:

~~~java
http.logout(logout -> logout
        .logoutSuccessHandler(oidcLogoutSuccessHandler)
);
~~~

Giá trị **{baseUrl}** được mở rộng theo request của ứng dụng. Nếu ứng dụng có context path hoặc chạy sau proxy, kiểm tra URL sau khi mở rộng có đúng với URI trong RegisteredClient hay không. Trong một môi trường có nhiều host, không dựa vào Host header tùy ý từ client để tạo redirect URI; cấu hình trusted proxy và allowed host rõ ràng.

ClientRegistration phải có thông tin OIDC provider phù hợp, thường thông qua **issuer-uri** và discovery metadata. Metadata cần cung cấp **end_session_endpoint** nếu RP dùng handler tự động này. Kiểm tra issuer, discovery document và endpoint logout đang được dùng; không tự ghép một URL logout từ hostname không xác thực.

## 5. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra |
|---|---|---|
| Authorization endpoint báo redirect URI không hợp lệ | Callback chưa đăng ký hoặc khác scheme/host/port/path | So sánh request authorize với redirect URIs của RegisteredClient |
| Đăng nhập thành công nhưng đổi code nhận invalid_grant | redirect_uri ở token request khác URI ở authorization request; code hết hạn hoặc đã dùng | So sánh hai request và thời điểm/ID authorization, không ghi raw code |
| Chỉ lỗi khi chạy sau reverse proxy | Ứng dụng tạo base URL từ scheme/host nội bộ | Kiểm tra forwarded headers, proxy configuration và URI thực tế được tạo |
| Chạy local được nhưng production lỗi | Khác hostname, TLS termination, context path hoặc port | So sánh cấu hình theo môi trường và callback thực tế |
| Logout xong không quay về ứng dụng | post_logout_redirect_uri chưa đăng ký hoặc sai URI | So sánh logout request với post-logout redirect URIs |
| Logout endpoint báo thiếu hoặc không hợp lệ id_token_hint | RP không gửi ID Token của phiên OIDC hoặc session đã mất | Kiểm tra OIDC authentication và logout handler |
| Logout thành công nhưng state không được xử lý | RP không giữ state hoặc callback không đối chiếu state | Kiểm tra state tạo ra, gửi đi và nhận lại |
| Một client logout được, client khác không | Mỗi client có danh sách post-logout URI riêng | Kiểm tra đúng RegisteredClient được xác định bởi ID Token/client_id |

### Reverse proxy và forwarded headers

Một cấu hình thường gặp là:

~~~text
Browser -- HTTPS --> Reverse proxy -- HTTP --> Spring application
~~~

Nếu Spring application chỉ nhìn thấy kết nối HTTP nội bộ, **{baseUrl}** có thể mở rộng thành HTTP. Để xử lý đúng, proxy phải gửi các header chuyển tiếp phù hợp như **Forwarded** hoặc **X-Forwarded-Proto**, **X-Forwarded-Host**, **X-Forwarded-Port**. Ứng dụng chỉ nên tin các header này khi request đến từ proxy tin cậy.

Với Spring Boot, có thể cấu hình chiến lược forwarded headers theo phiên bản đang sử dụng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Không bật tin cậy forwarded headers cho mọi nguồn request khi ứng dụng có thể được truy cập trực tiếp từ mạng không tin cậy. Kiểm tra proxy có ghi đè header do người dùng gửi hay không và chỉ nhận traffic từ proxy đã được kiểm soát.

## 6. Quy trình khắc phục từng bước

**Bước 1: Xác định loại request lỗi.** Xem lỗi xảy ra ở authorization endpoint, token endpoint hay OIDC logout endpoint. Ghi lại endpoint, client ID đã chuẩn hóa, môi trường và nhóm lỗi. Không ghi authorization code, access token, refresh token, ID Token hoặc client secret.

**Bước 2: Lấy URI thực tế từ request.** Trong browser developer tools hoặc log đã masking, xác định tham số redirect_uri hoặc post_logout_redirect_uri. Kiểm tra cả giá trị sau khi URL được decode đúng một lần để hiểu URI mà server nhận. Không tự ý sửa encoding trước khi so sánh.

**Bước 3: Xác định client thực sự được chọn.** Kiểm tra client_id ở authorization request, client authentication tại token endpoint và client được nhận diện từ id_token_hint ở logout flow. Với JDBC repository, xác nhận record RegisteredClient đang được ứng dụng đọc.

**Bước 4: So sánh đúng danh sách.** Với login, so sánh redirect_uri với redirectUris. Với logout, so sánh post_logout_redirect_uri với postLogoutRedirectUris. Không thêm một URI vào cả hai danh sách chỉ để làm request qua được; xác định URI đó phục vụ flow nào.

**Bước 5: Kiểm tra URL bên ngoài proxy.** Đối chiếu scheme, host, port và context path mà trình duyệt sử dụng với URL ứng dụng suy ra từ request. Kiểm tra forwarded headers và cấu hình proxy.

**Bước 6: Kiểm tra lại authorization code hoặc logout session.** Với token exchange, xác minh code chưa hết hạn, chưa dùng và được cấp cho đúng client. Với logout, xác minh RP còn ID Token phù hợp để gửi id_token_hint và OP có thể xác định client.

**Bước 7: Chạy lại cả ca thành công và ca từ chối.** Xác minh URI đã đăng ký được chấp nhận, URI khác một ký tự bị từ chối, redirect không đi đến host ngoài allowlist và state được đối chiếu ở phía client.

## 7. Ví dụ kiểm thử URI hợp lệ và không hợp lệ

Có thể kiểm tra metadata và RegisteredClient trong integration test, sau đó gửi request qua endpoint thực. Với callback login, dùng đúng URI đã đăng ký:

~~~java
String registeredCallback =
        "https://app.example.com/login/oauth2/code/web-client";

RegisteredClient client = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri(registeredCallback)
        .postLogoutRedirectUri("https://app.example.com/")
        .scope(OidcScopes.OPENID)
        .build();

assertThat(client.getRedirectUris()).contains(registeredCallback);
assertThat(client.getPostLogoutRedirectUris())
        .contains("https://app.example.com/");
~~~

Các assertion này xác minh dữ liệu fixture. Bài integration test cần gửi authorization request và logout request đến filter chain thật để chứng minh endpoint thực thi đúng chính sách.

Ma trận test nên có ít nhất các trường hợp:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| redirect_uri khớp chính xác với callback đã đăng ký | Authorization request được tiếp tục |
| redirect_uri khác port hoặc path | Request bị từ chối an toàn |
| redirect_uri có hostname khác dù cùng trỏ về máy local | Request bị từ chối |
| Token request gửi lại đúng redirect_uri đã dùng | Authorization code có thể được đổi nếu các điều kiện khác hợp lệ |
| Token request đổi một ký tự trong redirect_uri | Code exchange bị từ chối |
| post_logout_redirect_uri nằm trong danh sách client | OP có thể redirect sau khi logout thành công |
| post_logout_redirect_uri không được đăng ký | OP từ chối redirect đến URI đó |
| URI logout có fragment | Không chấp nhận URI không phù hợp quy tắc |
| state được gửi trong logout request | RP đối chiếu đúng state khi nhận response |

Không chỉ kiểm tra status code. Kiểm tra cả Location header khi có redirect và bảo đảm hostname đích đúng allowlist. Khi URI không hợp lệ, Authorization Server không được phản hồi bằng cách redirect đến URI chưa được xác minh.

## 8. Những cách sửa tạo ra rủi ro

- Không dùng wildcard hoặc prefix matching cho redirect URI.
- Không tự động thêm URI lấy từ request vào RegisteredClient khi phát hiện mismatch.
- Không bỏ kiểm tra redirect_uri tại token endpoint để tránh invalid_grant.
- Không dùng redirect URI đăng nhập thay cho post-logout redirect URI mà không đăng ký rõ ràng ở danh sách tương ứng.
- Không tin mọi Forwarded hoặc X-Forwarded header từ Internet.
- Không log authorization code, ID Token, access token, refresh token hoặc client secret trong quá trình điều tra.
- Không chuyển người dùng đến URI tùy ý khi logout endpoint không xác thực được client.

Nếu ứng dụng cần nhiều hostname theo môi trường, hãy quản lý từng URI đã duyệt trong cấu hình hoặc dữ liệu client. Mỗi môi trường nên có callback và post-logout URI rõ ràng, thay vì một quy tắc suy diễn từ request.

## 9. Checklist hoàn tất

- Callback đăng nhập được đăng ký bằng redirectUri và khớp chính xác với URI client gửi.
- Token request gửi lại redirect_uri giống giá trị đã dùng để cấp authorization code.
- Post-logout callback được đăng ký riêng bằng postLogoutRedirectUri.
- OIDC logout endpoint được bật và RP lấy đúng end_session_endpoint từ provider metadata.
- RP gửi id_token_hint phù hợp và giữ state để kiểm tra response.
- Base URL sau reverse proxy có scheme, host, port và context path đúng.
- Forwarded headers chỉ được tin cậy từ proxy đã cấu hình.
- URI không hợp lệ bị từ chối và không tạo redirect đến host tùy ý.
- Integration test bao phủ cả callback login, token exchange và logout redirect.
- Log và metrics không chứa code, token, secret hoặc dữ liệu phiên nhạy cảm.

Khi xử lý theo đúng flow và danh sách đăng ký, redirect_uri mismatch và post_logout_redirect_uri failure có thể được khoanh vùng nhanh mà vẫn giữ nguyên kiểm tra bảo mật của OAuth 2.0 và OpenID Connect.
