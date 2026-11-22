# OAuth2TokenIntrospectionEndpointConfigurer và điểm tùy chỉnh

Trong OAuth 2.0, Resource Server cần biết access token mà client gửi lên còn hợp lệ hay đã hết hạn, bị thu hồi hoặc không dành cho API đó. Với JWT, Resource Server thường tự xác minh chữ ký và claims. Với **opaque access token**, token không tự mang claims có thể đọc được; Resource Server cần hỏi Authorization Server (AS) về trạng thái hiện tại. Giao thức **OAuth 2.0 Token Introspection (RFC 7662)** định nghĩa endpoint để thực hiện việc tra cứu này.

Trong Spring Authorization Server, **OAuth2TokenIntrospectionEndpointConfigurer** là điểm cấu hình chuyên biệt cho endpoint introspection. Nó cho phép tùy chỉnh bốn giai đoạn của quá trình xử lý:

1. **Pre-processing:** chuyển HTTP request thành đối tượng Authentication bằng AuthenticationConverter.
2. **Main processing:** xác thực yêu cầu introspection và quyết định token có active hay không bằng AuthenticationProvider.
3. **Post-processing thành công:** trả OAuth2TokenIntrospection về Resource Server bằng AuthenticationSuccessHandler.
4. **Post-processing lỗi:** chuyển lỗi xác thực/xử lý thành OAuth2 error response bằng AuthenticationFailureHandler.

Bài học thuộc chương **Introspection** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Mục tiêu của module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.

> **Điểm cần nhớ:** Introspection endpoint không phải endpoint đăng nhập và không cấp token mới. Nó nhận một token đã tồn tại, xác thực client đang hỏi, kiểm tra trạng thái token trong kho authorization, rồi trả metadata cần thiết cho đúng Resource Server.

## 1. Token Introspection giải quyết vấn đề gì?

Giả sử orders-api nhận access token từ identity.example.com. Nếu token là opaque, API không thể tự đọc sub, scope, exp hoặc trạng thái thu hồi. Nó gửi token tới introspection endpoint của AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

AS xác thực client orders-api, tìm authorization tương ứng, đánh giá trạng thái token và trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "client_id": "portal-web",
  "sub": "user-42",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://identity.example.com",
  "iat": 1794850000,
  "exp": 1794850600,
  "token_type": "Bearer"
}
~~~

Đây là response minh họa; giá trị và tập claim thực tế phụ thuộc AS, token và chính sách đối với Resource Server. client_id trong ví dụ là OAuth2 Client đã yêu cầu token, còn client xác thực với introspection endpoint là Resource Server orders-api.

Nếu token không tồn tại, hết hạn, bị thu hồi hoặc Resource Server không được phép biết token đó, một introspection request đã được xác thực hợp lệ thường nhận response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

Đây không phải lỗi HTTP. active=false là kết quả nghiệp vụ của một truy vấn introspection hợp lệ. Việc trả cùng một dạng response cho token không tồn tại và token mà caller không được phép introspect giúp giảm khả năng dò đoán trạng thái nội bộ của AS.

### 1.1. Introspection khác JWT signature validation

| Tiêu chí | JWT validation tại Resource Server | Token Introspection |
|---|---|---|
| Dữ liệu token | JWT có claims và chữ ký | Token có thể opaque/reference |
| Nơi xác minh chính | Resource Server, dùng public key/validator | Authorization Server |
| Trạng thái thu hồi | Thường cần denylist, version hoặc kiểm tra bổ sung | AS có thể tra trạng thái hiện tại |
| Network request cho mỗi lần xác minh | Không bắt buộc | Thường có |
| Độ trễ và phụ thuộc AS | Thấp hơn khi xác minh offline | Phụ thuộc mạng và endpoint AS |
| Khả năng cập nhật trạng thái | Phụ thuộc mô hình bổ sung | Có thể phản ánh trạng thái mới nhanh hơn, trừ khi RS cache |
| Phù hợp | Token tự chứa, throughput cao | Opaque token, cần kiểm tra trạng thái tập trung |

Introspection cũng có thể dùng cho JWT nếu kiến trúc yêu cầu AS là nguồn quyết định trạng thái. Tuy nhiên, chỉ vì JWT có thể được gửi đến introspection endpoint không có nghĩa Resource Server phải luôn làm vậy.

### 1.2. Introspection không thay authorization nghiệp vụ

active=true có nghĩa AS xác nhận token đang hoạt động và được phép sử dụng trong ngữ cảnh đã xét. Điều đó **không tự động** cho phép mọi hành động trên mọi bản ghi.

Sau introspection, Resource Server vẫn cần kiểm tra audience, scope/authority, tenant, owner, trạng thái tài nguyên và quyền nghiệp vụ. Ví dụ token có scope orders.read không được phép gọi API hủy đơn hàng, dù active là true.

## 2. RFC 7662: hợp đồng HTTP của introspection endpoint

RFC 7662 quy định Resource Server gửi **HTTP POST** với body application/x-www-form-urlencoded. Tham số token là bắt buộc. token_type_hint là tùy chọn, giúp AS tối ưu tra cứu; nếu AS không tìm thấy token theo hint, nó vẫn phải mở rộng tìm kiếm trong các loại token được hỗ trợ.

### 2.1. Request parameters

| Tham số | Bắt buộc | Ý nghĩa |
|---|---|---|
| token | Có | Giá trị access token hoặc refresh token cần introspect |
| token_type_hint | Không | Gợi ý loại token, ví dụ access_token hoặc refresh_token |
| Tham số mở rộng | Không | Context do Resource Server gửi, nếu AS và RS có hợp đồng riêng |

Không gửi token qua query string. URL có thể bị ghi vào access log, proxy log, browser history hoặc hệ thống tracing. Body POST qua TLS giảm nguy cơ token xuất hiện trong URL; vẫn cần redaction body ở logging middleware.

### 2.2. Response và claim active

active là claim bắt buộc và có kiểu boolean. Định nghĩa active phụ thuộc AS, nhưng thường có nghĩa token được phát hành bởi AS này, chưa hết hạn, chưa bị thu hồi/invalidated, hợp lệ cho Resource Server đang gọi và được phép tiết lộ metadata cho caller đó.

Response khi active=true có thể chứa các claim tiêu chuẩn:

| Claim | Ý nghĩa |
|---|---|
| scope | Danh sách scope đã được cấp |
| client_id | Client đã yêu cầu token |
| username | Tên hiển thị của resource owner, nếu có |
| sub | Subject của token |
| aud | Audience/resource nhận token |
| iss | Issuer phát hành token |
| exp | Thời điểm hết hạn |
| iat | Thời điểm phát hành |
| nbf | Thời điểm token bắt đầu có hiệu lực |
| jti | Định danh token |
| token_type | Loại token, ví dụ Bearer |

Các trường ngoài active có thể tùy chọn theo RFC và triển khai. AS có thể trả các claim khác theo hợp đồng đã thống nhất với Resource Server. Không gửi dữ liệu nhạy cảm chỉ vì có thể truy cập được từ authorization record.

### 2.3. Vì sao token không active chỉ nên trả active:false?

RFC 7662 khuyến nghị không đưa thêm claim vào response của token không active. Nếu response nói token hết hạn, bị thu hồi, không tồn tại hay thuộc client khác, caller có thể dùng khác biệt đó để dò trạng thái token hoặc suy ra thông tin nội bộ.

Vì vậy, token không tìm thấy, hết hạn, bị thu hồi/invalidated hoặc không được phép introspect đều có thể trả active=false. Không trả sub, client_id, exp hoặc lý do cụ thể trong response inactive.

### 2.4. Lỗi xác thực client khác với token inactive

| Tình huống | Kết quả phù hợp |
|---|---|
| Resource Server xác thực đúng, token không active | HTTP 200 với active:false |
| Resource Server xác thực đúng, token active | HTTP 200 với active:true và claims được phép |
| Client authentication sai | HTTP 401 hoặc lỗi authentication theo cơ chế OAuth2 |
| Request thiếu/sai định dạng | Lỗi request phù hợp |
| AS không thể truy cập authorization store | Lỗi server/availability; không giả vờ token active |

Không biến lỗi database, timeout hoặc lỗi nội bộ thành active=true. Nếu AS không thể xác định trạng thái token, cần từ chối an toàn và ghi nhận sự cố.

## 3. Luồng xử lý trong Spring Authorization Server

OAuth2TokenIntrospectionEndpointConfigurer cấu hình OAuth2TokenIntrospectionEndpointFilter. Filter nhận HTTP request, chuyển request thành một đối tượng Authentication, đưa đối tượng đó vào AuthenticationManager, sau đó dùng success/failure handler để trả response.

~~~mermaid
flowchart TD
    A[POST /oauth2/introspect] --> B[Client Authentication Filter]
    B --> C{Resource Server client authenticated?}
    C -->|No| X[401 / OAuth2 client error]
    C -->|Yes| D[OAuth2TokenIntrospectionEndpointFilter]
    D --> E[AuthenticationConverter]
    E --> F[OAuth2TokenIntrospectionAuthenticationToken]
    F --> G[AuthenticationManager]
    G --> H[OAuth2TokenIntrospectionAuthenticationProvider]
    H --> I[OAuth2AuthorizationService]
    I --> J{Token active and caller allowed?}
    J -->|Yes| K[OAuth2TokenIntrospection active=true]
    J -->|No| L[OAuth2TokenIntrospection active=false]
    K --> M[AuthenticationSuccessHandler]
    L --> M
    M --> N[HTTP 200 JSON]
    H -->|AuthenticationException| O[AuthenticationFailureHandler]
    O --> P[OAuth2 error response]
~~~

Có hai bước xác thực khác nhau:

1. **Client authentication:** chứng minh caller được phép gọi introspection endpoint.
2. **Token introspection:** đánh giá token mà caller muốn kiểm tra và quyết định caller đó có được nhận metadata hay không.

Một token được kiểm tra không phải credential dùng để xác thực Resource Server tại endpoint introspection. Resource Server cần credential riêng của chính nó.

### 3.1. Default components

Trong Spring Authorization Server 1.5.x, endpoint filter mặc định sử dụng:

| Giai đoạn | Thành phần mặc định | Vai trò |
|---|---|---|
| Parse request | OAuth2TokenIntrospectionAuthenticationConverter | Đọc token, token_type_hint và additional parameters |
| Xử lý chính | OAuth2TokenIntrospectionAuthenticationProvider | Dùng client registration và authorization service để xử lý introspection |
| Thành công | Internal success handler | Trả OAuth2TokenIntrospection dưới dạng JSON |
| Thất bại | OAuth2ErrorAuthenticationFailureHandler | Trả OAuth2 error response |

OAuth2TokenIntrospectionAuthenticationProvider được khởi tạo với RegisteredClientRepository và OAuth2AuthorizationService. Authorization service là nguồn dữ liệu để tra cứu các authorization và token liên quan. Các implementation thường dùng là InMemoryOAuth2AuthorizationService cho development/test và JdbcOAuth2AuthorizationService cho persistence.

## 4. OAuth2TokenIntrospectionEndpointConfigurer cung cấp những extension points nào?

Configurer có sáu phương thức cấu hình chính:

| Phương thức | Kiểu mở rộng | Khi nào dùng? |
|---|---|---|
| introspectionRequestConverter(...) | Thêm AuthenticationConverter | Nhận một định dạng request mở rộng |
| introspectionRequestConverters(...) | Truy cập danh sách converter mặc định và converter bổ sung | Thay đổi thứ tự, loại bỏ hoặc tùy biến converter |
| authenticationProvider(...) | Thêm AuthenticationProvider | Xử lý một loại introspection authentication riêng |
| authenticationProviders(...) | Truy cập danh sách provider | Thay thế, bọc hoặc bổ sung provider mặc định |
| introspectionResponseHandler(...) | AuthenticationSuccessHandler | Tùy chỉnh response thành công, header, audit hoặc serialization |
| errorResponseHandler(...) | AuthenticationFailureHandler | Tùy chỉnh cách trả lỗi và audit lỗi |

Các extension points tương ứng với ba lớp xử lý: **pre-processing**, **main processing** và **post-processing**. Cần chọn đúng lớp để thay đổi; ví dụ converter chỉ parse request, không phải nơi kết luận token active.

## 5. Cấu hình endpoint trong SecurityFilterChain

Ví dụ dưới đây dùng API cấu hình fluent của Spring Authorization Server 1.5.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenIntrospectionEndpoint(introspection -> introspection
                .introspectionRequestConverters(configureRequestConverters())
                .authenticationProviders(configureProviders())
                .introspectionResponseHandler(introspectionSuccessHandler())
                .errorResponseHandler(introspectionFailureHandler())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình. Cần có các bean hạ tầng như RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, client authentication và các filter chain còn lại. Nếu không cần tùy chỉnh một giai đoạn, giữ default handler/converter/provider của framework.

### 5.1. Cấu hình endpoint URI

Mặc định endpoint introspection thường là /oauth2/introspect. Có thể thay đổi qua AuthorizationServerSettings:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .tokenIntrospectionEndpoint("/oauth2/v1/introspect")
        .build();
}
~~~

URL công khai còn phụ thuộc context path và reverse proxy. Resource Server phải được cấu hình trỏ tới đúng endpoint HTTPS. Nếu đổi endpoint, cần cập nhật cấu hình Resource Server và metadata/discovery phù hợp.

### 5.2. Bảo vệ endpoint bằng client authentication

Introspection endpoint phải yêu cầu caller được xác thực/ủy quyền. Với Resource Server, thường đăng ký một confidential client riêng:

~~~java
RegisteredClient ordersApi = RegisteredClient.withId("orders-api-internal")
    .clientId("orders-api")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("token.introspect")
    .build();
~~~

Đây là ví dụ registration minh họa. Việc có scope token.introspect trong registration **không tự động** làm Spring Authorization Server giới hạn quyền introspect theo scope đó; phải có policy enforcement phù hợp nếu muốn áp dụng. Client secret phải đến từ secret manager, không hardcode vào source code hoặc log.

Trong production có thể dùng private_key_jwt, tls_client_auth hoặc self_signed_tls_client_auth theo khả năng triển khai. Không cho phép public client không có credential gọi endpoint introspection như một API công khai.

## 6. Pre-processing: introspectionRequestConverter

Converter nhận HttpServletRequest, đọc tham số giao thức và tạo OAuth2TokenIntrospectionAuthenticationToken. Converter mặc định hiểu request theo RFC 7662. Khi thêm tham số mở rộng, cần giữ nguyên khả năng xử lý token và token_type_hint.

### 6.1. Khi nào cần converter tùy chỉnh?

Ví dụ tổ chức muốn Resource Server gửi thêm resource_id để AS giới hạn claims được trả theo từng API:

~~~http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_TOKEN&token_type_hint=access_token&resource_id=orders-api
~~~

resource_id là extension riêng giữa AS và RS, không phải tham số chuẩn bắt buộc của RFC 7662. AS phải xác thực resource_id thuộc caller đã xác thực; không tin một giá trị tùy ý do request body gửi lên.

### 6.2. Converter mở rộng là pre-processing, không phải authorization

Một converter tùy chỉnh có thể kiểm tra cấu trúc request, đọc additional parameters, chuẩn hóa dữ liệu và tạo OAuth2TokenIntrospectionAuthenticationToken có additionalParameters.

Converter không nên tự quyết định token active, tin resource_id mà không đối chiếu client, bỏ qua client principal đã xác thực, gọi token store rồi tự tạo response JSON hoặc bỏ qua request chuẩn mà converter mặc định đang hỗ trợ.

### 6.3. Ví dụ converter có additional parameter (pseudocode)

~~~java
// PSEUDOCODE: mô tả điểm mở rộng, cần điều chỉnh theo phiên bản và
// converter mặc định của dự án trước khi dùng production.
AuthenticationConverter resourceAwareConverter = request -> {
    String token = request.getParameter("token");
    if (!StringUtils.hasText(token)) {
        return null;
    }

    Authentication clientPrincipal =
        SecurityContextHolder.getContext().getAuthentication();

    String tokenTypeHint = request.getParameter("token_type_hint");
    String resourceId = request.getParameter("resource_id");

    Map<String, Object> additionalParameters = new HashMap<>();
    if (StringUtils.hasText(resourceId)) {
        additionalParameters.put("resource_id", resourceId);
    }

    return new OAuth2TokenIntrospectionAuthenticationToken(
        token, clientPrincipal, tokenTypeHint, additionalParameters);
};
~~~

Đoạn code trên minh họa constructor của OAuth2TokenIntrospectionAuthenticationToken; nó chưa thay thế đầy đủ converter mặc định. Nếu dùng trực tiếp, phải đảm bảo xử lý request malformed, duplicate parameter, body encoding và client authentication đúng contract. Một cách an toàn hơn là bọc/delegate converter mặc định, rồi bổ sung context sau khi parse thành công.

### 6.4. Thêm converter mà vẫn giữ default

Configurer cho phép thao tác trên danh sách converter:

~~~java
private Consumer<List<AuthenticationConverter>> configureRequestConverters() {
    return converters -> {
        // Giữ OAuth2TokenIntrospectionAuthenticationConverter mặc định.
        // Chỉ thêm converter mở rộng khi nó có thể nhận diện request riêng.
        converters.add(0, resourceAwareConverter());
    };
}
~~~

Nếu converter mở rộng không xử lý một request, nó nên trả null để converter tiếp theo có thể xử lý. Không xóa converter mặc định trừ khi đã thay thế toàn bộ contract và có integration tests tương đương.

## 7. Main processing: AuthenticationProvider

AuthenticationProvider nhận OAuth2TokenIntrospectionAuthenticationToken và thực hiện xử lý chính. Provider mặc định OAuth2TokenIntrospectionAuthenticationProvider được tạo từ RegisteredClientRepository và OAuth2AuthorizationService.

Về mặt logic, provider cần xác nhận principal gọi introspection là client đã được xác thực, tra cứu token theo giá trị và token type hint, xác định token thuộc authorization nào, kiểm tra token còn active/chưa expired/chưa invalidated, áp dụng chính sách xem Resource Server hiện tại có được biết token đó hay không và tạo OAuth2TokenIntrospection với active cùng các claim được phép.

Không nên suy ra token active chỉ từ việc tìm thấy một record. Authorization record có thể tồn tại trong database sau khi access token đã hết hạn hoặc bị invalidated.

### 7.1. OAuth2AuthorizationService là nguồn dữ liệu trung tâm

OAuth2AuthorizationService quản lý các OAuth2 authorization và cho phép tìm kiếm token:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(tokenValue, OAuth2TokenType.ACCESS_TOKEN);
~~~

Đây là ví dụ tra cứu ở tầng service, không phải đoạn code để thay thế provider mặc định. findByToken có thể trả null; token type hint có thể là null nếu implementation cần tìm theo nhiều loại token. Cách tìm và đánh giá trạng thái phải tuân thủ hợp đồng của provider/version.

OAuth2Authorization.Token cung cấp trạng thái như isExpired(), isInvalidated() và isActive(). Khi tự xây provider, phải dùng trạng thái token thực tế và chính sách hiện hành; không chỉ kiểm tra authorization != null.

### 7.2. Token type hint chỉ là gợi ý

RFC 7662 quy định token_type_hint là optional. Nếu AS không tìm được token theo hint, nó phải tiếp tục tìm kiếm trên các loại token được hỗ trợ. Không trả active:false chỉ vì caller gửi nhầm hint khi token thực tế vẫn thuộc loại khác được AS hỗ trợ.

### 7.3. Provider mặc định và custom provider

Configurer cung cấp authenticationProvider(provider) để thêm provider và authenticationProviders(consumer) để truy cập danh sách provider mặc định và provider bổ sung.

OAuth2TokenIntrospectionAuthenticationProvider của Spring Authorization Server 1.5.x là class final, có constructor nhận RegisteredClientRepository và OAuth2AuthorizationService; không có setter kiểu setAuthenticationValidator() như một số provider grant khác. Vì vậy, không nên viết code giả định có thể subclass provider này hoặc gọi một method tùy chỉnh không tồn tại.

Nếu cần policy introspection riêng, có thể thêm provider cho loại Authentication mở rộng do converter riêng tạo ra, bọc logic mặc định bằng một provider delegate hoặc thay provider mặc định bằng implementation riêng khi thực sự phải thay đổi semantics.

Khi custom provider hỗ trợ cùng loại authentication với provider mặc định, thứ tự trong AuthenticationManager quan trọng. Phải kiểm tra provider nào được gọi trước, provider nào xử lý request, và tránh tạo fallback làm bỏ qua policy.

### 7.4. Ví dụ cấu hình provider list

~~~java
private Consumer<List<AuthenticationProvider>> configureProviders() {
    return providers -> {
        // Ví dụ: đăng ký provider chuyên xử lý custom authentication type.
        // Không xóa provider mặc định nếu custom provider chưa thay thế
        // đầy đủ việc xác minh token theo RFC 7662.
        providers.add(0, tenantAwareIntrospectionProvider());
    };
}
~~~

tenantAwareIntrospectionProvider() là bean do ứng dụng tự xây. Nếu provider xử lý cùng OAuth2TokenIntrospectionAuthenticationToken với provider mặc định, cần quy định rõ khi nào nó xử lý, khi nào delegate, và bảo đảm một request không thể rơi qua provider khác để bỏ qua tenant check.

## 8. Custom response claims và giới hạn thông tin trả về

OAuth2TokenIntrospection là model response của Spring Authorization Server. Builder cho phép khai báo active, scope, clientId, subject, audience, issuer, expiresAt, issuedAt, notBefore, id, username và custom claims.

Ví dụ tạo model response:

~~~java
OAuth2TokenIntrospection introspection =
    OAuth2TokenIntrospection.builder(true)
        .clientId("portal-web")
        .subject("user-42")
        .audience("orders-api")
        .scope("orders.read")
        .issuer("https://identity.example.com")
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .claim("tenant_id", "tenant-17")
        .build();
~~~

Ví dụ này minh họa API model, không phải đoạn code để thay thế provider mặc định. Khi thêm claim, phải lấy giá trị từ authorization record hoặc nguồn dữ liệu tin cậy, không lấy thẳng từ request caller.

### 8.1. Khi nào nên thêm custom claim?

Một số trường hợp hợp lý: Resource Server cần tenant_id để áp dụng isolation; API cần assurance context nếu token thực sự có thông tin đó; hệ thống cần authorization_id hoặc identifier nội bộ không nhạy cảm để correlation; AS cần trả cnf cho sender-constrained token theo contract hỗ trợ.

Không nên trả email, số điện thoại, địa chỉ hoặc PII nếu Resource Server không cần; danh sách mọi role trong toàn hệ thống khi API chỉ cần scope giới hạn; nội dung consent hoặc dữ liệu nội bộ không liên quan; claims của token inactive; secret, refresh token, client secret hoặc thông tin key material.

### 8.2. Giới hạn response theo Resource Server

RFC 7662 cho phép AS trả response khác nhau cho các Resource Server khác nhau. Ví dụ:

| Resource Server | Claims có thể cần |
|---|---|
| orders-api | sub, aud, scope, tenant_id, exp |
| billing-api | sub, aud, scope, account_id, exp |
| analytics-api | sub pseudonymized, aud, scope, exp |

Để làm được điều này, AS cần xác định Resource Server qua client đã xác thực, kiểm tra token có được phát cho resource đó hay không, lọc scopes/claims theo allowlist, không tiết lộ tenant hoặc subject của resource khác và trả active:false nếu caller không được phép biết trạng thái token theo policy.

Không dùng aud do request body tự khai làm bằng chứng duy nhất. audience phải được đối chiếu với claims/authorization đã được AS lưu và xác minh.

### 8.3. Không thay active bằng custom status

Có thể thêm claim nội bộ như risk_level hoặc policy_version, nhưng không thay thế claim active bắt buộc. Resource Server phải có quy tắc rõ ràng cho custom claims; nếu không, dữ liệu bổ sung chỉ làm response phức tạp hơn mà không tăng bảo mật.

## 9. Post-processing thành công: introspectionResponseHandler

introspectionResponseHandler là AuthenticationSuccessHandler xử lý kết quả đã xác thực và ghi response HTTP. Dùng khi cần tùy chỉnh response headers, gắn correlation ID, ghi audit metadata an toàn, áp dụng serializer hoặc response wrapper đã thống nhất, hay kiểm soát cache headers.

### 9.1. Handler không phải nơi quyết định token active

Success handler chạy sau khi AuthenticationProvider đã xử lý thành công. Nó không nên tự tìm token, tự kiểm tra expiry hoặc tự biến token inactive thành active. Logic đó thuộc provider/domain service.

### 9.2. Response handler tùy chỉnh (pseudocode)

~~~java
AuthenticationSuccessHandler introspectionSuccessHandler() {
    return (request, response, authentication) -> {
        OAuth2TokenIntrospectionAuthenticationToken result =
            (OAuth2TokenIntrospectionAuthenticationToken) authentication;

        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        // Default protocol response handler đã được thay thế ở đây.
        // Nếu tự serialize, phải trả JSON claims đúng RFC 7662,
        // giữ active và không tiết lộ thông tin ngoài policy.
        objectMapper.writeValue(
            response.getOutputStream(),
            result.getTokenClaims().getClaims());
    };
}
~~~

Đây là pseudocode cho ý tưởng custom serialization; cần inject ObjectMapper, xử lý content type/status, exception và response commitment đúng cách. Nếu chỉ cần thêm claims, hãy xử lý ở provider và giữ success handler mặc định thay vì tự viết lại HTTP serialization.

### 9.3. Cache headers

Introspection response chứa metadata bảo mật và có thể thay đổi khi token bị revoke. Không để intermediary cache response theo mặc định. Nếu muốn Resource Server cache, việc cache phải được thiết kế rõ ở phía Resource Server với TTL phù hợp, không dựa vào browser/proxy cache công khai.

## 10. Post-processing lỗi: errorResponseHandler

errorResponseHandler nhận lỗi OAuth2AuthenticationException và tạo OAuth2 error response. Có thể dùng để chuẩn hóa log/audit, gắn request correlation ID, ánh xạ lỗi hạ tầng thành lỗi giao thức phù hợp, ẩn stack trace và chi tiết nội bộ, giữ đúng HTTP status và OAuth2 error contract.

Không dùng failure handler để đổi một token không active thành HTTP 401. Với một introspection request đã được xác thực và hợp lệ về cú pháp, token không active thường là response 200 với active:false.

Ví dụ failure handler:

~~~java
AuthenticationFailureHandler introspectionFailureHandler() {
    return (request, response, exception) -> {
        // Ghi metric/audit bằng request ID và error code.
        // Không ghi token, client secret hoặc stack trace vào response.
        oauth2ErrorResponseHandler().onAuthenticationFailure(
            request, response, exception);
    };
}
~~~

oauth2ErrorResponseHandler() là placeholder cho handler OAuth2 chuẩn của ứng dụng. Trong code thực tế có thể giữ nguyên default handler nếu không có nhu cầu tùy chỉnh; nếu tự viết, cần bảo toàn status, error và các header phù hợp.

## 11. Client authentication và quyền introspect

RFC 7662 yêu cầu endpoint phải có cơ chế authorization để ngăn token scanning. Spring Authorization Server cấu hình client authentication cho introspection endpoint. Các phương thức client authentication thường hỗ trợ gồm client_secret_basic, client_secret_post, client_secret_jwt, private_key_jwt, tls_client_auth và self_signed_tls_client_auth theo cấu hình.

Resource Server không nên dùng public client không có credential để hỏi trạng thái token. Với hệ thống lớn, nên đăng ký từng Resource Server hoặc nhóm API với danh tính riêng, quyền introspection tối thiểu và audit độc lập.

### 11.1. Client được xác thực không có nghĩa được introspect mọi token

Xác thực orders-api chỉ chứng minh caller là orders-api. AS còn cần quyết định token có thuộc issuer/realm/tenant mà API này được phép truy vấn không, token có audience phù hợp không, API có được xem claims nhạy cảm không, có cần giới hạn scope được trả về không và caller có đang cố dò token của client/tenant khác không.

Nếu token không tồn tại hoặc caller không được phép biết trạng thái token, trả active:false theo chính sách để tránh làm lộ thông tin.

### 11.2. Tách credential introspection khỏi credential gọi API

Credential mà orders-api dùng để gọi introspection endpoint là credential của **Resource Server**. Nó khác access token của user mà API đang kiểm tra. Không chuyển access token của user thành client credential để introspect chính nó.

### 11.3. Không log token trong introspection request

Introspection body có token là credential. Cần redact body ở reverse proxy, servlet filter, APM và HTTP client logging; không đưa token vào exception message; không log Basic Authorization header hoặc client secret; dùng correlation ID không chứa token; giới hạn retention của audit và log bảo mật.

## 12. Resource Server sử dụng introspection endpoint

Spring Security Resource Server hỗ trợ opaque token thông qua OpaqueTokenIntrospector. Khi dùng Spring Boot, có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-api
          client-secret: ORDERS_API_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

Trong production, lấy secret từ secret manager hoặc cơ chế cấu hình bảo mật. Không commit secret vào application.yml.

### 12.1. SecurityFilterChain cho Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Spring Security dùng OpaqueTokenAuthenticationProvider và OpaqueTokenIntrospector để gọi AS, kiểm tra active và ánh xạ scope thành authorities có prefix SCOPE_. Authentication sau khi xác thực thường có principal kiểu OAuth2AuthenticatedPrincipal; controller có thể đọc các attributes đã được introspection trả về.

### 12.2. Dùng SpringOpaqueTokenIntrospector

Có thể khai báo bean để cấu hình trực tiếp:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        IntrospectionClientProperties properties) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(properties.introspectionUri())
        .clientId(properties.clientId())
        .clientSecret(properties.clientSecret())
        .build();
}
~~~

IntrospectionClientProperties là configuration object do ứng dụng định nghĩa và nạp từ secret manager. Nếu đã cung cấp OpaqueTokenIntrospector bean hoặc gọi introspector(...) trong DSL, cấu hình Boot tự động cho introspector có thể bị thay thế.

### 12.3. Scope được ánh xạ thành authority

Nếu introspection trả:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Resource Server mặc định ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Vì vậy rule hasAuthority("SCOPE_orders.read") phù hợp với ví dụ. Nếu muốn ánh xạ roles/permissions khác, dùng custom introspector hoặc authentication converter có chủ đích.

## 13. Tùy chỉnh OpaqueTokenIntrospector ở Resource Server

OpaqueTokenIntrospector là phía client gọi introspection endpoint. Nó khác OAuth2TokenIntrospectionEndpointConfigurer ở phía AS:

| Thành phần | Nằm ở đâu? | Trách nhiệm |
|---|---|---|
| OAuth2TokenIntrospectionEndpointConfigurer | Authorization Server | Nhận và xử lý request introspection |
| OpaqueTokenIntrospector | Resource Server | Gọi endpoint và biến response thành principal đã xác thực |
| OpaqueTokenAuthenticationProvider | Resource Server | Dùng introspector để xác thực Bearer token |
| OAuth2TokenIntrospectionAuthenticationProvider | Authorization Server | Tra cứu authorization/token và tạo introspection result |

Ví dụ custom introspector delegate tới Spring implementation rồi bổ sung authority:

~~~java
final class CustomAuthoritiesIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    CustomAuthoritiesIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            extractAuthorities(principal.getAttributes());

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(), principal.getAttributes(), authorities);
    }
}
~~~

extractAuthorities(...) là hàm do ứng dụng triển khai. Không được tự thêm authority chỉ dựa trên dữ liệu do request caller gửi. Chỉ ánh xạ các claim đã được AS xác minh và trả về trong response.

## 14. Cache introspection: hiệu năng và độ mới của trạng thái

Introspection thường tạo network round trip tới AS cho mỗi token authentication. Cache ở Resource Server có thể giảm latency và tải, nhưng làm chậm khả năng nhận biết token vừa bị revoke.

### 14.1. Trade-off

| TTL cache | Ưu điểm | Rủi ro |
|---|---|---|
| Không cache | Trạng thái mới nhất theo AS mỗi request | Tăng latency, tải và phụ thuộc AS |
| Rất ngắn | Cân bằng hiệu năng và revocation freshness | Vẫn có cửa sổ stale ngắn |
| Dài | Giảm mạnh số lần introspection | Token revoked vẫn có thể được chấp nhận tới khi cache hết hạn |

### 14.2. TTL phải bị giới hạn bởi thời gian token còn sống

Nếu token chỉ còn 20 giây nhưng cache TTL là 5 phút, Resource Server không được tiếp tục tin cache quá thời điểm exp. TTL hiệu lực nên là giá trị nhỏ hơn giữa:

~~~text
cacheTTL = min(configuredTTL, token.exp - now, revocationFreshnessBudget)
~~~

Đây là công thức thiết kế minh họa. Nếu response không có exp, cần một TTL ngắn do policy quy định. Không cache response active vô thời hạn.

### 14.3. Cache inactive response

Có thể cache active:false trong thời gian ngắn để giảm token scanning và tải AS, nhưng cần giới hạn kích thước và chống cache pollution do attacker gửi token ngẫu nhiên. Không tạo cache key bằng cách lưu raw token trong log hoặc metrics; dùng hash an toàn phù hợp với hệ thống.

### 14.4. Không fail-open khi AS lỗi

Nếu introspection endpoint timeout hoặc unavailable, Resource Server không biết token còn active hay không. Với API bảo mật, mặc định nên từ chối request hoặc trả lỗi hạ tầng phù hợp, không tự coi token là active. Có thể dùng circuit breaker, retry có giới hạn, timeout và stale cache có policy rõ ràng; không dùng stale cache vô hạn.

## 15. Multi-Resource Server và giới hạn claims

Một access token có thể được sử dụng trong nhiều resource boundary, nhưng không phải Resource Server nào cũng cần biết toàn bộ thông tin token. AS nên áp dụng nguyên tắc **minimum disclosure**.

~~~mermaid
flowchart LR
    T[Access token] --> AS[Authorization Server]
    AS --> O[orders-api introspection client]
    AS --> B[billing-api introspection client]
    AS --> A[analytics-api introspection client]
    O --> OR[claims: sub, aud, orders scope]
    B --> BR[claims: sub, aud, billing scope]
    A --> AR[claims: pseudonymous subject, aud, analytics scope]
~~~

Để thực hiện, AS cần xác định Resource Server qua client đã xác thực, kiểm tra token có được phát cho resource đó hay không, lọc scopes/claims theo allowlist, không tiết lộ tenant hoặc subject của resource khác và trả active:false nếu caller không được phép biết trạng thái token theo policy.

Không dùng aud do request body tự khai làm bằng chứng duy nhất. audience phải được đối chiếu với claims/authorization đã được AS lưu và xác minh.

## 16. Tùy chỉnh endpoint: chọn đúng extension point

| Nhu cầu | Extension point nên dùng | Lý do |
|---|---|---|
| Đọc thêm resource_id hoặc context parameter | introspectionRequestConverter(s) | Đây là bước chuyển HTTP thành authentication request |
| Kiểm tra client có được hỏi token của tenant/resource này không | authenticationProvider(s) hoặc service policy được provider gọi | Đây là quyết định authorization của introspection |
| Thêm claims đã được phép vào response | Custom provider tạo OAuth2TokenIntrospection | Claims cần dựa trên trạng thái token và caller |
| Thêm correlation header, audit thành công, custom JSON serialization | introspectionResponseHandler | Xử lý HTTP response sau khi authentication thành công |
| Chuẩn hóa lỗi, audit thất bại, ẩn lỗi nội bộ | errorResponseHandler | Xử lý authentication failure |
| Đổi endpoint path | AuthorizationServerSettings | Đây là cấu hình endpoint URI, không phải converter/provider |
| Đổi cách lưu authorization/token | OAuth2AuthorizationService | Đây là persistence/query model, dùng bởi provider |
| Đổi cách Resource Server gọi introspection | OpaqueTokenIntrospector | Đây là client-side integration ở RS |

Một anti-pattern phổ biến là đặt toàn bộ logic vào converter hoặc success handler. Điều này làm lẫn parse request, authorization decision và response serialization, khiến việc kiểm thử và audit khó hơn.

## 17. Kiểm thử bằng MockMvc

Integration test nên đi qua filter chain thật, xác thực client thật trong test fixture và provider thật hoặc provider custom đã được cấu hình. Chỉ mock method findByToken không chứng minh endpoint đang bảo vệ đúng client authentication và response semantics.

### 17.1. Test token active

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenIntrospectionEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedResourceServerCanIntrospectActiveToken() throws Exception {
        String accessToken = fixtureActiveAccessToken();

        mvc.perform(post("/oauth2/introspect")
                .with(httpBasic("orders-api", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", accessToken)
                .param("token_type_hint", "access_token"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.active").value(true))
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.scope").value("orders.read"));
    }
}
~~~

Đây là khung test cần RegisteredClient confidential orders-api, client secret encoder, authorization/token fixture đã được lưu trong OAuth2AuthorizationService và endpoint filter chain. Không hardcode secret production; test-secret chỉ dùng trong test profile.

### 17.2. Test token inactive

~~~java
@Test
void unknownOrRevokedTokenReturnsInactiveResponse() throws Exception {
    mvc.perform(post("/oauth2/introspect")
            .with(httpBasic("orders-api", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "UNKNOWN_OR_REVOKED_TOKEN")
            .param("token_type_hint", "access_token"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.active").value(false))
        .andExpect(jsonPath("$.sub").doesNotExist())
        .andExpect(jsonPath("$.client_id").doesNotExist());
}
~~~

Test này kiểm tra không tiết lộ thêm claims khi token inactive. Nếu custom policy có response khác, phải đối chiếu RFC và hợp đồng bảo mật.

### 17.3. Test client authentication thất bại

~~~java
@Test
void introspectionRequiresAuthenticatedClient() throws Exception {
    mvc.perform(post("/oauth2/introspect")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "ANY_TOKEN"))
        .andExpect(status().isUnauthorized());
}
~~~

Status cụ thể phụ thuộc cấu hình client authentication và entry point, nhưng endpoint không được xử lý như API công khai không xác thực.

### 17.4. Test Resource Server gọi introspection

Nên có integration test riêng cho orders-api:

1. Cấu hình OpaqueTokenIntrospector trỏ tới AS test;
2. Gửi request protected resource với Authorization: Bearer opaque-token;
3. Xác minh RS gọi endpoint introspection bằng client credentials;
4. Với active=true, request tiếp tục tới authorization rule;
5. Với active=false, RS trả 401;
6. Với token active nhưng thiếu scope, RS trả 403;
7. Khi token bị revoke, lần introspection tiếp theo phải nhận trạng thái inactive theo cache policy.

### 17.5. Test custom provider và response handler

Kiểm tra provider từ chối token của tenant khác, provider không thêm custom claim khi active=false, response handler không log token, error handler không đưa stack trace ra ngoài, resource_id không thể được caller dùng để đọc claims của resource khác và provider mặc định vẫn xử lý request chuẩn nếu custom converter/provider không nhận request.

## 18. Các tình huống lỗi và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| RS nhận 401 cho mọi token | Sai introspection URI hoặc client credentials | Kiểm tra endpoint, TLS và client authentication |
| AS trả 401 | Client không được xác thực hoặc phương thức auth không khớp registration | Kiểm tra RegisteredClient và HTTP Authorization |
| AS trả 200 active:false | Token không tồn tại, hết hạn, revoked hoặc caller không được phép xem | Kiểm tra authorization store và policy ở môi trường test; không tiết lộ lý do cho caller |
| AS trả 500 | Persistence lỗi, custom provider/handler exception | Kiểm tra trace nội bộ, không fail-open |
| Scope không được map | Response thiếu scope hoặc custom converter thay authorities | Kiểm tra introspection response và OpaqueTokenIntrospector |
| RS nhận scope nhưng endpoint vẫn 403 | Scope thiếu hoặc rule yêu cầu authority khác | Kiểm tra prefix SCOPE_ và authorization matcher |
| Token vừa revoke nhưng vẫn dùng được | RS cache response active quá lâu | Kiểm tra cache TTL và revocation SLA |
| Custom parameter bị bỏ qua | Converter mặc định xử lý request trước hoặc converter custom không nhận diện request | Kiểm tra thứ tự converter |
| Custom provider không được gọi | Provider mặc định đứng trước hoặc custom provider không supports loại Authentication | Kiểm tra thứ tự provider và type |
| Response handler không chạy | Request chưa qua authentication thành công hoặc endpoint matcher sai | Kiểm tra filter chain và AuthenticationManager |

## 19. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Mở introspection endpoint không cần authentication | Token scanning và rò metadata | Yêu cầu Resource Server client authentication |
| Gửi token qua GET query string | Token có thể lọt vào access log/history | Dùng POST form body qua TLS |
| Trả claims khi active=false | Lộ sự tồn tại và trạng thái token | Chỉ trả active:false |
| Coi active=true là đủ cho mọi API | Thiếu kiểm tra audience/scope/tenant | Resource Server vẫn authorize theo policy |
| Converter quyết định token active | Trộn parsing và authorization | Đưa quyết định vào provider/domain service |
| Success handler tự tra cứu token | Lặp business logic và khó kiểm soát | Provider tạo kết quả, handler chỉ trả response |
| Thay provider mặc định nhưng bỏ kiểm tra expiry/revocation | Token cũ có thể được chấp nhận | Giữ hoặc tái triển khai đầy đủ validation |
| Tin resource_id từ request body | Resource Server có thể lấy claims ngoài phạm vi | Bind resource vào authenticated client |
| Cache active response quá lâu | Token revoked vẫn được chấp nhận | TTL ngắn và không vượt exp/revocation budget |
| Fail-open khi AS unavailable | Không xác định token vẫn được chấp nhận | Fail-closed hoặc stale-cache policy có giới hạn |
| Log token/client secret | Credential leakage | Redact body và Authorization header |
| Cho mọi Resource Server xem mọi claim | Rò PII/tenant data | Minimum disclosure theo client/audience |

## 20. Checklist production

1. **Endpoint URI:** AuthorizationServerSettings công bố đúng introspection path và reverse proxy route?
2. **Client authentication:** chỉ Resource Server/client được cấp quyền mới gọi endpoint?
3. **TLS:** request và response đi qua HTTPS với certificate validation?
4. **Request format:** POST form-urlencoded; token không xuất hiện trong query/log?
5. **Converter:** giữ default request parser hoặc mở rộng có kiểm soát, không bỏ tham số chuẩn?
6. **Provider:** tra token trong OAuth2AuthorizationService, kiểm tra expiry/invalidated/active?
7. **Caller authorization:** Resource Server chỉ xem token và claims thuộc phạm vi được phép?
8. **Response:** active luôn có kiểu boolean; inactive response không tiết lộ claims khác?
9. **Custom claims:** lấy từ nguồn tin cậy và chỉ trả dữ liệu tối thiểu?
10. **Response handler:** giữ Cache-Control no-store, không log token và không làm sai OAuth response?
11. **Error handler:** phân biệt client auth failure với token inactive, không lộ stack trace?
12. **Resource Server:** kiểm tra active, audience, scope và quyền nghiệp vụ?
13. **Cache:** TTL ngắn, không vượt exp, phù hợp revocation SLA?
14. **Availability:** timeout, retry, circuit breaker và fail-closed policy rõ ràng?
15. **Multi-node:** OAuth2AuthorizationService có persistence nhất quán để các AS node cùng thấy revoke/update?
16. **Observability:** metric cho latency, active/inactive ratio, error, store failure và cache hit; không chứa token?
17. **Testing:** có positive, inactive, invalid-client, wrong-tenant, custom claims, revocation và outage tests?
18. **Version alignment:** code dùng đúng package/API theo Spring Authorization Server 1.5.x hoặc Spring Security 7.0+?

## 21. Bài tập vận dụng

**Tình huống A — Token bị thu hồi:** orders-api vừa introspect token nhận active=true. Sau đó user logout và AS revoke token. Nếu RS cache response 60 giây, token còn có thể được chấp nhận trong bao lâu? Hãy thiết kế TTL theo SLA.

**Tình huống B — Resource Server giả mạo audience:** Caller orders-api gửi resource_id=billing-api trong introspection request để lấy claims billing. AS nên xác định resource nào bằng dữ liệu nào?

**Tình huống C — Custom provider:** Một custom provider được thêm vào danh sách nhưng provider mặc định vẫn xử lý request trước. Hãy phân tích ảnh hưởng thứ tự provider và cách viết test chứng minh custom policy đang thực sự chạy.

**Tình huống D — Token inactive:** Resource Server gửi một token ngẫu nhiên, client authentication hợp lệ. Vì sao response đúng thường là HTTP 200 với active:false, thay vì HTTP 401?

**Tình huống E — AS database timeout:** Introspection provider không thể xác định trạng thái token. Hãy chọn hành vi an toàn và mô tả cách giám sát lỗi hạ tầng.

**Gợi ý:** A phụ thuộc cache TTL và revocation freshness budget; B phải bind resource vào client principal đã xác thực; C phải kiểm tra provider order và supports; D vì request introspection được xác thực, kết quả token inactive không phải lỗi xác thực caller; E không fail-open, cần fail-closed hoặc stale-cache có giới hạn được phê duyệt.

## 22. Tổng kết

OAuth2TokenIntrospectionEndpointConfigurer là điểm tùy chỉnh endpoint introspection trong Spring Authorization Server. Nó cung cấp converter cho pre-processing, provider cho xử lý chính, success handler cho response thành công và failure handler cho OAuth2 error response.

Provider mặc định phối hợp RegisteredClientRepository với OAuth2AuthorizationService để tìm authorization và đánh giá token. Response cần có active boolean; nếu token không tồn tại, hết hạn, revoked hoặc caller không được phép biết trạng thái, AS nên trả active:false mà không tiết lộ thêm claims.

Các extension points phải được dùng đúng vai trò: converter parse request, provider thực hiện authorization/introspection, response handler serialize kết quả, error handler trả lỗi. Nếu cần custom claims hoặc giới hạn theo Resource Server, quyết định phải dựa trên client đã xác thực và authorization record tin cậy.

Ở phía Resource Server, OpaqueTokenIntrospector gọi endpoint, đọc active và ánh xạ scopes thành authorities. Việc cache cần cân bằng hiệu năng với khả năng nhận biết token bị revoke; khi AS không thể xác định trạng thái token, không được tự coi token là active.

Nắm vững các điểm tùy chỉnh này giúp thiết kế introspection endpoint dễ mở rộng nhưng vẫn giữ đúng RFC 7662, đồng thời phối hợp nhất quán giữa Authorization Server, Resource Server, kho authorization và chính sách bảo mật toàn hệ thống.

## 23. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request, response, active, client authorization, caching và security considerations.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client authentication, access token và OAuth2 error response.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth2TokenIntrospectionEndpointConfigurer, filter, converter, provider và handlers.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): OAuth2AuthorizationServerConfigurer, AuthorizationServerSettings và endpoint configuration.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2AuthorizationService, authorization/token lifecycle và JDBC/in-memory implementations.
- [Spring Authorization Server API — OAuth2TokenIntrospectionEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenIntrospectionEndpointConfigurer.html): API chi tiết các extension points trong nhánh 1.5.x.
- [Spring Authorization Server API — OAuth2TokenIntrospectionAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html): provider mặc định và dependencies.
- [Spring Authorization Server API — OAuth2TokenIntrospection.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2TokenIntrospection.Builder.html): xây response claims.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): OpaqueTokenIntrospector, OpaqueTokenAuthenticationProvider, authority mapping và customization.
- [Spring Security 7 — OAuth 2.0 Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): API sau khi Authorization Server được tích hợp vào Spring Security 7.
