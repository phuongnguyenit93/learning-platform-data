# CORS theo origin cụ thể và giới hạn trên các endpoint giao thức

## 1. Bối cảnh và mục tiêu

Một OAuth 2.0/OpenID Connect Authorization Server thường phục vụ nhiều loại client: ứng dụng web chạy trong browser, backend-for-frontend (BFF), service-to-service, mobile app và các Resource Server. Khi JavaScript chạy ở một origin gọi API tại origin khác, browser áp dụng **Cross-Origin Resource Sharing (CORS)** để quyết định JavaScript có được đọc response hay không.

Ví dụ:

- Trang quản trị chạy tại `https://console.example.com`.
- Authorization Server chạy tại `https://auth.example.com`.
- Inventory API chạy tại `https://inventory.example.com`.

Ba URL có cùng registrable domain nhưng khác origin vì hostname khác nhau. Khi JavaScript ở console gọi Token Endpoint hoặc UserInfo endpoint, browser có thể yêu cầu CORS response headers. Một service backend gọi cùng endpoint không bị browser áp dụng CORS.

Cấu hình CORS cho Authorization Server cần trả lời ba câu hỏi:

1. Origin nào được phép gọi bằng browser?
2. Endpoint giao thức nào thực sự cần cross-origin access?
3. Mỗi endpoint cần method, request header, credentials và response header nào?

Sau bài học, bạn có thể:

1. Phân biệt origin, site và URL.
2. Giải thích same-origin policy, CORS và preflight.
3. Thiết kế allow-list origin cụ thể theo môi trường.
4. Phân chia CORS policy theo từng endpoint OAuth 2.0/OIDC.
5. Cấu hình `CorsConfigurationSource` và `HttpSecurity.cors()` trong Spring Security.
6. Đặt CORS filter đúng thứ tự trước authentication.
7. Phân biệt CORS với authentication, authorization, CSRF và redirect URI validation.
8. Quản lý credentialed requests, allowed headers, exposed headers và preflight cache.
9. Tránh origin reflection, wildcard nguy hiểm và cấu hình CORS trùng lặp.
10. Kiểm thử cả preflight, actual request, negative origin và từng endpoint.

**Phạm vi phiên bản:** Ví dụ tham chiếu Spring Authorization Server 1.5.8, Spring Security 6.x và Spring Boot 3.x. Endpoint path có thể thay đổi qua `AuthorizationServerSettings`; hãy đồng bộ CORS path mapping với cấu hình endpoint thực tế.

## 2. Origin và same-origin policy

### 2.1. Origin gồm những gì?

Origin được xác định bởi bộ ba:

- Scheme: `http` hoặc `https`.
- Host: hostname hoặc địa chỉ host.
- Port: cổng hiệu lực của URL.

Ví dụ:

| URL | So với `https://console.example.com` | Cùng origin? |
| --- | --- | --- |
| `https://console.example.com/dashboard` | Cùng scheme, host và port mặc định. | Có |
| `https://console.example.com:8443` | Khác port. | Không |
| `http://console.example.com` | Khác scheme. | Không |
| `https://auth.example.com` | Khác host. | Không |
| `https://console.example.net` | Khác host. | Không |

Path không tham gia vào origin. Hai URL có path khác nhau nhưng cùng scheme, host và port vẫn cùng origin.

### 2.2. Same-origin policy

Same-origin policy (SOP) là cơ chế của browser giới hạn cách một document hoặc script tương tác với tài nguyên từ origin khác. CORS là cơ chế server khai báo những cross-origin response nào browser được phép chia sẻ với JavaScript.

Ví dụ JavaScript ở console gọi:

~~~javascript
const response = await fetch("https://inventory.example.com/inventory", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Browser kiểm tra response CORS headers. Nếu origin không được phép, JavaScript không được đọc response và browser báo lỗi CORS.

### 2.3. CORS không phải request firewall

CORS chủ yếu kiểm soát việc browser chia sẻ response cho script. Nó không xác thực caller và không ngăn mọi request cross-origin:

- `curl`, backend service và HTTP client không bị browser áp dụng CORS.
- Một số request đơn giản có thể được browser gửi tới server dù JavaScript không được đọc response.
- Request có preflight bị browser chặn trước khi gửi actual request nếu preflight không được chấp thuận.
- Attacker vẫn có thể gửi request bằng công cụ ngoài browser.

Vì vậy CORS không thay thế authentication, authorization, rate limit, input validation hoặc CSRF protection.

## 3. CORS request và preflight

### 3.1. Simple request

Một số request đáp ứng điều kiện của Fetch/CORS safelist có thể được browser gửi trực tiếp mà không cần preflight. Server vẫn phải trả `Access-Control-Allow-Origin` phù hợp để JavaScript đọc response.

Không nên dựa vào việc request có preflight hay không để quyết định request có an toàn. CORS policy áp dụng cho cả preflight và actual response.

### 3.2. Preflight request

Browser gửi preflight bằng HTTP OPTIONS khi request cần kiểm tra trước, ví dụ method không nằm trong safelist, request có header tùy chỉnh hoặc content type không được safelist.

Ví dụ JavaScript gọi UserInfo với Bearer token:

~~~http
OPTIONS /userinfo HTTP/1.1
Host: auth.example.com
Origin: https://console.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Server trả lời nếu origin, method và header được phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://console.example.com
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Authorization
Access-Control-Max-Age: 600
Vary: Origin
~~~

Browser sau đó mới gửi actual request. Status cụ thể có thể phụ thuộc filter/server; điều quan trọng là response chứa đúng các CORS headers được yêu cầu.

### 3.3. Các response header chính

| Header | Ý nghĩa |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép đọc response. |
| `Access-Control-Allow-Methods` | HTTP method được phép cho request cross-origin. |
| `Access-Control-Allow-Headers` | Request headers mà browser được phép gửi. |
| `Access-Control-Allow-Credentials` | Cho phép browser expose response khi request dùng credentials mode `include`. |
| `Access-Control-Expose-Headers` | Response headers mà JavaScript được phép đọc. |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight. |
| `Vary: Origin` | Báo cache rằng response phụ thuộc vào request Origin. |

`OPTIONS` là method dùng để thực hiện preflight; `Access-Control-Allow-Methods` liệt kê method của actual request mà server cho phép, chẳng hạn GET hoặc POST.

## 4. Xác định endpoint nào cần CORS

Không nên bật cùng một CORS policy rộng cho toàn bộ Authorization Server. Mỗi endpoint có cách sử dụng khác nhau.

### 4.1. Authorization Endpoint

Authorization Endpoint thường được browser truy cập bằng top-level navigation hoặc redirect trong Authorization Code Flow. Đây không phải lời gọi `fetch()` thông thường, nên thường không cần CORS.

Không bật CORS rộng cho `/oauth2/authorize` chỉ vì SPA là client. SPA có thể điều hướng browser tới Authorization Endpoint, xác thực người dùng và nhận redirect về callback URI.

### 4.2. Token Endpoint

Token Endpoint có thể cần CORS nếu một browser-based public client trực tiếp gửi authorization code tới Token Endpoint để đổi token. Trường hợp điển hình là SPA dùng Authorization Code + PKCE và thực hiện token exchange trong browser.

Trong mô hình BFF, backend đổi authorization code và browser chỉ gọi BFF cùng origin; Token Endpoint là back-channel và thường không cần CORS cho browser.

Nếu cho phép SPA gọi Token Endpoint:

- Chỉ cho phép exact origin của SPA đã đăng ký.
- Chỉ mở method POST.
- Chỉ mở request headers cần thiết.
- Không nhúng client secret vào SPA.
- Yêu cầu Authorization Code + PKCE và redirect URI đã đăng ký chính xác.
- Không coi CORS là bằng chứng client hợp lệ.

### 4.3. Discovery và JWKS

OIDC Discovery và JWKS thường được client/backend đọc qua HTTPS. Nếu browser JavaScript hoặc thư viện chạy trong browser trực tiếp tải metadata/JWKS từ Authorization Server, có thể cần CORS GET.

Nếu chỉ backend tải discovery/JWKS, browser không cần CORS cho các endpoint này. JWKS và metadata thường là dữ liệu public; nếu cho phép `*`, chỉ cân nhắc khi endpoint thật sự public, không dùng cookie credentials và không làm lộ dữ liệu tenant riêng.

### 4.4. UserInfo Endpoint

Một OIDC relying party chạy trong browser có thể gọi UserInfo bằng Bearer access token. Nếu kiến trúc cho phép browser gọi trực tiếp, cấu hình CORS cho exact frontend origins, GET/POST theo phương thức endpoint hỗ trợ và header Authorization.

Nếu UserInfo được gọi qua BFF, chỉ cần backend-to-backend access; không cần CORS từ browser tới endpoint này.

### 4.5. Revocation và introspection

Token Revocation và Token Introspection thường là back-channel endpoint dành cho confidential client hoặc Resource Server. Không mở CORS cho browser chỉ để thuận tiện.

Các endpoint này cần client authentication và policy riêng. CORS không bảo vệ credential và không thay thế quyền introspection/revocation.

### 4.6. PAR, Device Authorization, logout và Dynamic Client Registration

Pushed Authorization Requests, Device Authorization và Dynamic Client Registration thường được gọi từ backend hoặc client có credential theo protocol. Browser có thể điều hướng tới verification URI hoặc end-session/logout URI, nhưng navigation không đồng nghĩa cần CORS.

Chỉ thêm CORS khi có use case browser fetch thực tế, đã xác định origin và method cần thiết. Không bật wildcard trên toàn bộ protocol endpoint matcher.

### 4.7. Ma trận endpoint tham khảo

| Endpoint | Browser fetch thường cần? | CORS policy khuyến nghị |
| --- | --- | --- |
| `/oauth2/authorize` | Không; dùng navigation/redirect. | Không bật theo mặc định. |
| `/oauth2/token` | Có thể, với SPA PKCE trực tiếp đổi code. | POST và exact SPA origins. |
| `/.well-known/openid-configuration` | Chỉ khi browser trực tiếp discovery. | GET cho origin cần thiết hoặc không bật. |
| `/.well-known/oauth-authorization-server` | Chỉ khi browser trực tiếp đọc metadata. | GET cho origin cần thiết hoặc không bật. |
| `/oauth2/jwks` | Chỉ khi browser trực tiếp tải JWKS. | GET/HEAD cho origin cần thiết hoặc public read policy. |
| `/userinfo` | Có thể, nếu SPA gọi trực tiếp. | GET/POST theo endpoint, Authorization header và exact origins. |
| `/oauth2/revoke` | Không nên từ browser. | Không bật theo mặc định. |
| `/oauth2/introspect` | Không; back-channel. | Không bật theo mặc định. |
| `/oauth2/par` | Không; back-channel. | Không bật theo mặc định. |
| `/oauth2/device_authorization` | Không; back-channel. | Không bật theo mặc định. |
| `/connect/register` | Không; registration cần policy riêng. | Không bật theo mặc định. |
| `/connect/logout` | Thường navigation/form flow. | Không bật theo mặc định. |

Các path trên là path mặc định phổ biến; kiểm tra endpoint settings của ứng dụng trước khi cấu hình.

## 5. Thiết kế allow-list origin cụ thể

### 5.1. Exact origin

Origin allow-list nên khai báo đầy đủ scheme, hostname và port:

~~~text
https://console.example.com
https://portal.example.com
https://admin.example.com:8443
~~~

Các giá trị sau không tương đương:

~~~text
http://console.example.com
https://console.example.com:8443
https://console.example.net
~~~

Không thêm path hoặc trailing slash vào origin. Origin là scheme + host + port, không phải URL đầy đủ của trang.

### 5.2. Không phản chiếu Origin tùy ý

Một cấu hình nguy hiểm là đọc request `Origin` rồi trả lại nguyên giá trị đó trong `Access-Control-Allow-Origin` mà không kiểm tra allow-list. Điều này có thể cho mọi website truy cập response bằng JavaScript.

Không dùng logic kiểu:

~~~java
response.setHeader("Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

Hãy so sánh origin với danh sách được quản trị. Nếu không khớp, không cấp CORS headers và để CORS processor từ chối preflight/response theo policy.

### 5.3. Wildcard và credentials

`Access-Control-Allow-Origin: *` chỉ phù hợp với tài nguyên public không yêu cầu browser credentials. Khi bật `allowCredentials=true`, không được kết hợp `allowedOrigins("*")`; browser cũng không chấp nhận wildcard origin cho credentialed response.

Nếu cần cookie/session credentials:

- Dùng exact origins.
- Chỉ bật `allowCredentials=true` khi thực sự cần.
- Không cho phép origin tùy ý.
- Kết hợp cookie `Secure`, `HttpOnly`, `SameSite` phù hợp.
- Giữ CSRF protection cho endpoint dùng cookie/session.

### 5.4. allowedOriginPatterns

Spring hỗ trợ origin patterns, nhưng pattern rộng như `https://*.example.com` có thể tin cả subdomain không được kiểm soát hoặc subdomain bị takeover. Chỉ dùng pattern khi mọi hostname khớp pattern thuộc cùng trust boundary và được quản lý an toàn.

Với Authorization Server, exact origins dễ review và ít tạo lỗ hổng hơn. Không dùng pattern `*` để giải quyết nhanh lỗi CORS.

### 5.5. Origin null và localhost

Không cho phép origin `null` trong production nếu không có use case đã đánh giá. Origin null có thể xuất hiện từ sandboxed iframe, file URL hoặc opaque origin context.

Môi trường phát triển có thể cần `http://localhost:3000` hoặc port khác. Khai báo rõ từng origin development trong profile development; không đưa origin localhost vào production allow-list.

### 5.6. CORS origin không phải redirect URI

Hai danh sách này phục vụ hai mục đích khác nhau:

- CORS origin xác định browser origin được phép đọc response cross-origin.
- Redirect URI xác định nơi Authorization Server được phép gửi authorization response.

Một SPA origin được CORS cho phép không đồng nghĩa mọi callback URL trên origin đó đều hợp lệ. Authorization Server vẫn phải so khớp redirect URI chính xác theo client registration, đồng thời áp dụng PKCE, state và OIDC nonce khi phù hợp.

## 6. Cấu hình CORS theo endpoint trong Spring Framework

### 6.1. Tạo CorsConfigurationSource

Ví dụ tạo policy riêng cho Token Endpoint, metadata/JWKS và UserInfo:

~~~java
@Bean
CorsConfigurationSource authorizationServerCorsConfigurationSource() {
    CorsConfiguration tokenCors = new CorsConfiguration();
    tokenCors.setAllowedOrigins(List.of(
        "https://console.example.com"
    ));
    tokenCors.setAllowedMethods(List.of("POST"));
    tokenCors.setAllowedHeaders(List.of("Content-Type"));
    tokenCors.setAllowCredentials(false);
    tokenCors.setMaxAge(600L);

    CorsConfiguration publicReadCors = new CorsConfiguration();
    publicReadCors.setAllowedOrigins(List.of(
        "https://console.example.com",
        "https://portal.example.com"
    ));
    publicReadCors.setAllowedMethods(List.of("GET", "HEAD"));
    publicReadCors.setAllowedHeaders(List.of("Accept"));
    publicReadCors.setExposedHeaders(List.of("ETag", "Cache-Control"));
    publicReadCors.setAllowCredentials(false);
    publicReadCors.setMaxAge(1800L);

    CorsConfiguration userInfoCors = new CorsConfiguration();
    userInfoCors.setAllowedOrigins(List.of(
        "https://console.example.com"
    ));
    userInfoCors.setAllowedMethods(List.of("GET", "POST"));
    userInfoCors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    userInfoCors.setExposedHeaders(List.of("WWW-Authenticate"));
    userInfoCors.setAllowCredentials(false);
    userInfoCors.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/oauth2/token", tokenCors);
    source.registerCorsConfiguration(
        "/.well-known/openid-configuration", publicReadCors);
    source.registerCorsConfiguration(
        "/.well-known/oauth-authorization-server", publicReadCors);
    source.registerCorsConfiguration("/oauth2/jwks", publicReadCors);
    source.registerCorsConfiguration("/userinfo", userInfoCors);
    return source;
}
~~~

Đây là policy minh họa. Nếu SPA không gọi trực tiếp Token Endpoint, bỏ mapping `/oauth2/token`. Nếu không browser nào tải metadata/JWKS hoặc gọi UserInfo, không cần các mapping tương ứng.

### 6.2. Allowed headers phải theo request thực tế

Trong ví dụ:

- Token Endpoint cho `Content-Type` để browser gửi form body hoặc request cần header này.
- Metadata/JWKS chỉ cho `Accept`.
- UserInfo cho `Authorization` vì browser gửi Bearer token, và `Content-Type` nếu dùng POST.

Không cho phép mọi header theo thói quen. Nếu triển khai DPoP, thêm header `DPoP` chỉ khi endpoint thực sự hỗ trợ và browser client cần gửi nó. Header tùy chỉnh phải được đưa vào allow-list có chủ đích.

### 6.3. Allowed methods phải tối thiểu

Token Endpoint chỉ cần POST. Metadata/JWKS thường chỉ cần GET và có thể HEAD. UserInfo dùng GET hoặc POST theo hỗ trợ của endpoint.

Không thêm PUT, PATCH, DELETE chỉ vì API khác dùng các method đó. CORS methods phải khớp protocol endpoint đang phục vụ.

### 6.4. Exposed headers

JavaScript chỉ đọc được một số response headers safelisted mặc định. Nếu ứng dụng cần đọc `ETag`, `Cache-Control` hoặc `WWW-Authenticate`, khai báo chúng trong `setExposedHeaders`.

Không expose header nội bộ hoặc header chứa credential. Access token trong response body của Token Endpoint vẫn là dữ liệu nhạy cảm; CORS cho phép JavaScript của origin đó đọc body nên chỉ mở origin đã tin cậy.

### 6.5. allowCredentials

`allowCredentials` điều khiển việc browser có thể expose response khi request được gửi với credentials mode `include`, ví dụ cookie hoặc HTTP authentication do browser quản lý. Nó không phải công tắc cho phép gửi Bearer token trong header `Authorization`.

Nếu JavaScript tự đặt Bearer token vào `Authorization`, hãy cho phép header này bằng `allowedHeaders`. Thông thường token endpoint cho SPA PKCE không cần cookie credentials, nên `allowCredentials(false)` là lựa chọn phù hợp.

## 7. Tích hợp với Spring Security và Spring Authorization Server

### 7.1. CORS phải chạy trước authentication

Preflight request thường không mang session cookie hoặc Bearer token của actual request. Nếu Spring Security yêu cầu authentication trước khi CORS xử lý, preflight có thể bị trả 401/403 dù origin hợp lệ.

Spring Security tích hợp CORS qua `http.cors(...)`. Khi cấu hình CORS đúng, CORS filter xử lý preflight trước các filter authentication/authorization thích hợp.

### 7.2. Cấu hình Authorization Server SecurityFilterChain

Ví dụ với endpoint matcher của Spring Authorization Server:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource authorizationServerCorsConfigurationSource)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .cors(cors -> cors.configurationSource(
            authorizationServerCorsConfigurationSource))
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

Endpoint matcher của Authorization Server xác định filter chain xử lý các protocol endpoint. `CorsConfigurationSource` tiếp tục giới hạn origin/method/header theo path; chain matcher không có nghĩa mọi endpoint đều được CORS.

Ứng dụng vẫn cần các bean và cấu hình khác như authentication, JWK source, issuer, exception handling và chain cho application endpoints.

### 7.3. Cấu hình chain khác

Nếu cùng ứng dụng có API hoặc application endpoint trong một `SecurityFilterChain` khác, chain đó phải cấu hình CORS riêng nếu cần cross-origin access:

~~~java
http.cors(cors -> cors.configurationSource(apiCorsConfigurationSource));
~~~

CORS được tích hợp theo từng security chain. Cấu hình CORS trong Authorization Server chain không tự động cấu hình CORS cho API chain khác hoặc một service Resource Server triển khai riêng.

### 7.4. Không permitAll OPTIONS một cách thay thế

Không dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` như cách thay thế CORS configuration. Cách đó không xác minh Origin, requested method hoặc requested headers.

CORS processor phải kiểm tra preflight và chỉ chấp thuận khi policy khớp. Một OPTIONS request thông thường không phải preflight vẫn phải tuân theo security policy của endpoint.

### 7.5. Tránh cấu hình CORS trùng lặp

Chọn một nơi chịu trách nhiệm phát CORS headers cho mỗi request:

- Spring Security `http.cors(...)`, hoặc
- một CORS filter/edge gateway được thiết kế rõ ràng.

Không để CDN, reverse proxy, servlet filter và Spring Security cùng thêm `Access-Control-Allow-Origin` theo các policy khác nhau. Hai header allow-origin trùng nhau có thể khiến browser từ chối response hoặc tạo hành vi khó dự đoán.

## 8. CORS cho browser-based OAuth client

### 8.1. SPA dùng Authorization Code + PKCE

Một SPA có thể thực hiện:

1. Tạo `code_verifier` và `code_challenge`.
2. Điều hướng browser tới Authorization Endpoint.
3. Người dùng xác thực và consent nếu cần.
4. Authorization Server redirect về callback URI đã đăng ký với authorization code.
5. SPA gửi POST tới Token Endpoint để đổi code và verifier.
6. SPA gọi UserInfo hoặc API bằng access token.

Trong flow này:

- Authorization Endpoint dùng navigation, thường không cần CORS.
- Token Endpoint cần CORS nếu SPA trực tiếp gọi từ browser.
- UserInfo cần CORS nếu SPA trực tiếp fetch.
- API riêng cần CORS policy riêng nếu browser gọi trực tiếp.

Nếu dùng BFF, browser chỉ gọi BFF và BFF gọi Token Endpoint/UserInfo/API ở back-channel. Đây thường là cách giảm việc access token nằm trong JavaScript runtime.

### 8.2. Không có client secret trong SPA

SPA là public client. Client secret được nhúng trong JavaScript bundle không còn bí mật và không chứng minh được danh tính confidential client.

Đăng ký SPA với client authentication phù hợp cho public client, dùng Authorization Code + PKCE và redirect URI chính xác. CORS chỉ quyết định browser được đọc response từ origin nào.

### 8.3. CORS không thay PKCE hoặc state

CORS không bảo vệ authorization code khỏi interception và không chống login CSRF. SPA vẫn cần PKCE, state và kiểm tra callback; OIDC cần nonce khi áp dụng. Redirect URI phải được so khớp theo client registration.

Không giảm yêu cầu PKCE chỉ vì Token Endpoint chỉ cho phép origin của SPA.

## 9. CORS, cookie credentials và CSRF

### 9.1. Bearer token và cookie session khác nhau

Browser fetch có thể gửi Bearer token trong header `Authorization`. Trường hợp này cần `Authorization` trong allowed headers nhưng không nhất thiết cần `allowCredentials(true)`.

Nếu request dựa vào cookie session, browser có thể cần `credentials: "include"` và server cần `Access-Control-Allow-Credentials: true` cùng exact allowed origin. Cookie còn chịu các thuộc tính Secure, HttpOnly, SameSite và domain/path.

### 9.2. CORS không ngăn CSRF

Một website độc hại có thể cố gửi request tới endpoint dùng cookie của người dùng. CORS có thể ngăn JavaScript đọc response nhưng không bảo đảm request không được gửi. Với simple request, request có thể tới server dù response bị browser chặn.

Do đó:

- Giữ CSRF protection cho endpoint dùng cookie/session.
- Không dùng CORS làm CSRF defense.
- Không bật credentialed CORS cho origin không tin cậy.
- Tách API bearer-token stateless khỏi browser session endpoint nếu kiến trúc yêu cầu.

### 9.3. Token Endpoint và cookie

Token Endpoint dành cho SPA PKCE thường xác thực public client qua authorization code, redirect URI và PKCE; không cần dựa vào cookie session của Authorization Server ở cross-origin fetch. Vì vậy không bật `allowCredentials(true)` nếu không có yêu cầu cụ thể.

Nếu thiết kế có cookie credentials, đánh giá riêng CSRF, SameSite, origin allow-list và browser behavior; không bật chỉ để khắc phục một lỗi preflight.

## 10. Origin động và multi-tenant

### 10.1. Origin của frontend tenant

Trong nền tảng multi-tenant, mỗi tenant có thể có frontend origin riêng, ví dụ:

- `https://acme.portal.example.com`
- `https://fabrikam.portal.example.com`
- `https://app.customer.example`

Không suy ra origin hợp lệ chỉ từ tenant ID, Host header hoặc suffix hostname. Cần một registry đã xác minh liên kết tenant với frontend origin được phép.

### 10.2. CORS policy động

Nếu cần cấu hình động, `CorsConfigurationSource` có thể tra allow-list theo request Origin rồi trả policy chỉ khi origin đã được đăng ký và trạng thái tenant cho phép.

Logic cần bảo đảm:

- Origin được parse/normalize theo quy tắc origin, không xử lý như URL tùy ý.
- So khớp scheme, host và port chính xác.
- Tenant/domain binding đã verified và active.
- Không phản chiếu Origin chưa xác minh.
- Không dùng cache quá lâu khi origin bị thu hồi.
- `Vary: Origin` được phát để cache không dùng response của tenant này cho tenant khác.

### 10.3. Wildcard subdomain không thay thế registry

Cho phép `https://*.portal.example.com` chỉ an toàn nếu toàn bộ subdomain trong pattern được nền tảng kiểm soát, không có tenant tự tạo subdomain tùy ý và không tồn tại nguy cơ dangling DNS/subdomain takeover.

Với custom domain, exact origin registry thường là lựa chọn phù hợp hơn.

## 11. Reverse proxy, CDN và cache

### 11.1. Chọn một lớp phát CORS headers

Nếu CORS được xử lý tại Spring Security, gateway/CDN nên chuyển tiếp request và response headers nhất quán. Nếu CORS được xử lý ở edge, không để ứng dụng thêm một policy khác.

Quyết định này cần được ghi rõ trong deployment configuration để tránh lỗi chỉ xuất hiện ở production.

### 11.2. Vary header

Khi response thay đổi theo Origin, cache cần nhận biết điều đó. `Vary: Origin` ngăn shared cache phục vụ response có `Access-Control-Allow-Origin` của một origin cho origin khác.

Với preflight response, cân nhắc `Vary` theo `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` khi cache ở proxy/CDN.

### 11.3. Preflight cache

`Access-Control-Max-Age` cho phép browser cache kết quả preflight. Giá trị lớn giảm số OPTIONS request nhưng làm thay đổi policy có thể mất thời gian mới có hiệu lực ở browser.

Chọn TTL theo mức độ thay đổi allow-list. Với endpoint nhạy cảm, dùng thời gian vừa phải và có kế hoạch khi thu hồi origin. Không nhầm preflight cache với cache access token hoặc cache authorization.

### 11.4. TLS và public URL

CORS origin phải là origin public mà browser thực sự gọi, ví dụ HTTPS domain của Authorization Server. Reverse proxy phải chuyển tiếp scheme/host đúng và chỉ tin forwarded headers từ proxy được tin cậy.

Không cho phép một Origin giả điều khiển issuer, redirect URI hoặc endpoint URL được công bố.

## 12. Các lỗi thường gặp

### Lỗi 1: Dùng wildcard cho mọi endpoint

**Triệu chứng:** Website không liên quan có thể đọc response cross-origin từ endpoint được mở.

**Nguyên nhân:** Cấu hình `allowedOrigins("*")` trên toàn server.

**Cách xử lý:** Dùng exact origin allow-list và policy riêng cho từng endpoint.

### Lỗi 2: Cho rằng CORS xác thực client

**Triệu chứng:** Backend hoặc curl vẫn gọi được endpoint dù browser bị CORS chặn.

**Nguyên nhân:** Nhầm browser policy với server-side authentication.

**Cách xử lý:** Xác thực client/token và authorize request độc lập với CORS.

### Lỗi 3: Preflight nhận 401

**Triệu chứng:** Browser báo lỗi CORS trước khi gửi actual request.

**Nguyên nhân:** Authentication filter xử lý OPTIONS trước CORS.

**Cách xử lý:** Tích hợp `http.cors(...)` để CORS xử lý trước authentication.

### Lỗi 4: Cho phép mọi header và method

**Triệu chứng:** Policy khó review và mở rộng ngoài nhu cầu.

**Nguyên nhân:** Dùng wildcard headers/methods.

**Cách xử lý:** Khai báo chính xác `POST`, `GET`, `Authorization`, `Content-Type` theo endpoint.

### Lỗi 5: Dùng allowCredentials với wildcard origin

**Triệu chứng:** Framework từ chối cấu hình hoặc browser không expose response.

**Nguyên nhân:** Kết hợp `Access-Control-Allow-Credentials: true` với `Access-Control-Allow-Origin: *`.

**Cách xử lý:** Dùng exact origins và chỉ bật credentials khi cần.

### Lỗi 6: Cho rằng Authorization header cần allowCredentials

**Triệu chứng:** Bật cookie credentials không cần thiết chỉ để gửi Bearer token.

**Nguyên nhân:** Nhầm allowed headers với Fetch credentials mode.

**Cách xử lý:** Cho phép `Authorization` trong `allowedHeaders`; giữ `allowCredentials(false)` nếu không gửi cookie/browser credentials.

### Lỗi 7: Mở CORS cho Authorization Endpoint

**Triệu chứng:** Toàn bộ protocol endpoints được áp dụng một policy rộng.

**Nguyên nhân:** Nhầm browser navigation với fetch/XHR.

**Cách xử lý:** Không bật CORS cho authorization navigation nếu không có use case cụ thể.

### Lỗi 8: CORS origin và redirect URI dùng chung danh sách

**Triệu chứng:** Callback URL không hợp lệ hoặc frontend origin được tin quá rộng.

**Nguyên nhân:** Trộn hai loại cấu hình.

**Cách xử lý:** Quản lý CORS origins và redirect URIs riêng.

### Lỗi 9: Gateway và ứng dụng cùng thêm CORS headers

**Triệu chứng:** Response có nhiều `Access-Control-Allow-Origin`.

**Nguyên nhân:** Cấu hình CORS ở nhiều tầng.

**Cách xử lý:** Chọn một lớp sở hữu CORS response cho mỗi route.

### Lỗi 10: Thu hồi origin nhưng cache vẫn cho phép

**Triệu chứng:** Browser tiếp tục dùng kết quả preflight đã cache trong một khoảng thời gian.

**Nguyên nhân:** `Access-Control-Max-Age` quá dài.

**Cách xử lý:** Chọn TTL phù hợp và hiểu rằng thay đổi policy không xóa ngay cache preflight của mọi browser.

## 13. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Exact SPA origin gọi Token Endpoint POST | CORS headers khớp allow-list. |
| Origin không nằm trong allow-list | Không có allow-origin hợp lệ; preflight bị từ chối. |
| Origin đúng nhưng method PUT | Preflight bị từ chối. |
| Origin đúng nhưng header tùy chỉnh chưa cho phép | Preflight bị từ chối. |
| Origin đúng, UserInfo GET có Authorization | Preflight và actual request được xử lý đúng. |
| Origin đúng, credentials mode include nhưng policy false | Browser không expose credentialed response. |
| Wildcard origin với allowCredentials true | Cấu hình không hợp lệ/không được browser chấp nhận. |
| Authorization Endpoint top-level navigation | Hoạt động qua redirect, không phụ thuộc CORS. |
| Revocation/introspection từ browser | Không có CORS allow-list; back-channel vẫn yêu cầu authentication. |
| Preflight OPTIONS không có session | CORS filter xử lý trước authentication. |
| OPTIONS thông thường không phải preflight | Vẫn tuân theo security policy endpoint. |
| `Origin: null` | Bị từ chối theo production policy. |
| Sai scheme hoặc port | Bị từ chối như origin khác. |
| Tenant origin đã bị thu hồi | Không còn được CORS allow sau khi policy/cache cập nhật. |
| Response đi qua CDN | `Vary` và allow-origin không bị cache sai tenant/origin. |
| Request bằng curl | Có thể gửi dù không có CORS; authentication/authorization vẫn được kiểm tra. |

## 14. Kiểm thử với MockMvc

Ví dụ preflight test:

~~~java
mockMvc.perform(options("/oauth2/token")
        .header("Origin", "https://console.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://console.example.com"))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("POST")));
~~~

Test negative origin:

~~~java
mockMvc.perform(options("/oauth2/token")
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Status chính xác có thể phụ thuộc cấu hình filter và Spring version; quan trọng là origin không được nhận `Access-Control-Allow-Origin` hợp lệ. Bổ sung test actual request với Origin hợp lệ và không hợp lệ, cũng như test từng path được map.

Không chỉ test preflight. Cần xác nhận response của actual request có CORS headers để browser đọc được body, kể cả response lỗi khi endpoint trả 4xx.

## 15. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Origin model | Đã xác định exact scheme, host và port? |
| Allow-list | Không phản chiếu Origin và không dùng wildcard rộng? |
| Endpoint scope | Chỉ mở endpoint có browser fetch use case? |
| Authorization endpoint | Dùng navigation/redirect, không bật CORS tùy tiện? |
| Token endpoint | Chỉ exact SPA origins, POST và public-client PKCE nếu browser exchange? |
| Discovery/JWKS | Chỉ bật GET nếu browser cần trực tiếp tải? |
| UserInfo | Exact origins và Authorization header theo use case? |
| Back-channel endpoints | Revocation/introspection/PAR không mở browser CORS? |
| Methods | Chỉ có method endpoint hỗ trợ? |
| Headers | Chỉ có Content-Type/Authorization/custom headers cần thiết? |
| Credentials | `allowCredentials` chỉ bật khi cần cookie/browser credentials? |
| CSRF | Cookie/session endpoint vẫn có CSRF protection? |
| Filter order | CORS xử lý preflight trước authentication? |
| Multiple chains | Mỗi chain cần CORS đã cấu hình riêng? |
| Proxy/CDN | Chỉ một lớp phát CORS headers và cache theo Vary? |
| Preflight TTL | Max-Age phù hợp khả năng thu hồi policy? |
| Tenant origin | Origin động tra từ registry đã xác minh? |
| Logging | Không log token/secret hoặc dữ liệu nhạy cảm? |
| Tests | Có positive, negative, preflight và actual-request tests? |

## 16. Bài tập thực hành

Một hệ thống có:

- SPA quản trị tại `https://console.example.com`.
- Authorization Server tại `https://auth.example.com`.
- Inventory API tại `https://inventory.example.com`.
- BFF tại `https://bff.example.com`.

SPA có thể chọn một trong hai kiến trúc: gọi Token Endpoint trực tiếp bằng Authorization Code + PKCE, hoặc dùng BFF để đổi code ở back-channel. SPA cũng có thể gọi UserInfo trực tiếp hoặc qua BFF. Revocation và introspection chỉ được gọi bởi backend.

Hãy thực hiện:

1. Vẽ request flow cho SPA trực tiếp và BFF.
2. Lập bảng endpoint nào cần CORS trong từng kiến trúc.
3. Cấu hình exact origin allow-list theo environment.
4. Viết `CorsConfigurationSource` riêng cho token, discovery/JWKS và UserInfo nếu cần.
5. Tích hợp CORS vào Authorization Server `SecurityFilterChain`.
6. Cấu hình CORS riêng cho API chain nếu SPA gọi Inventory API trực tiếp.
7. Giữ `allowCredentials(false)` cho bearer-token flow không dùng cookie.
8. Kiểm thử preflight, actual request, origin sai, method sai và header sai.
9. Kiểm tra `Vary` khi response được cache qua CDN.
10. Chứng minh revocation/introspection không cần browser CORS.

**Tiêu chí đạt:** Mỗi endpoint có policy theo use case; origin được so khớp chính xác; preflight được xử lý trước authentication; CORS không thay thế PKCE, authentication, authorization hoặc CSRF; không có wildcard/credentialed-origin reflection.

## 17. Tài liệu đối chiếu

- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): origin, preflight, credentials và CORS response headers.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/docs/Web/HTTP/CORS): mô tả browser behavior, preflight và response headers.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): tích hợp CORS filter với Spring Security.
- [Spring Framework — CORS Support](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `CorsConfigurationSource` và CORS processing.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): endpoint và Authorization Server configuration.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, token endpoint, client registration semantics và redirect URI.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth clients, redirect flows và token usage.
- [OWASP — Cross-Origin Resource Sharing Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Origin_Resource_Sharing_Cheat_Sheet.html): kiểm soát origin và các cấu hình CORS an toàn.
