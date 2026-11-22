# OidcUserInfoEndpointConfigurer và userInfoMapper

Trong OpenID Connect (OIDC), **ID Token** cho Relying Party (RP) biết kết quả xác thực người dùng, còn **UserInfo Endpoint** cho phép RP lấy thêm các claims về End-User bằng access token. Hai loại token có mục đích khác nhau: ID Token nói về sự kiện xác thực và subject; access token là credential để gọi protected resource. UserInfo là protected resource thuộc OpenID Provider (OP), không phải một endpoint đăng nhập khác.

Trong Spring Authorization Server, **OidcUserInfoEndpointConfigurer** cấu hình endpoint UserInfo và các bước xử lý request. Điểm tùy chỉnh quan trọng nhất là **userInfoMapper**: một Function nhận OidcUserInfoAuthenticationContext đã được xác thực và tạo ra OidcUserInfo cho response. Mapper có thể lấy claims từ ID Token, access token JWT hoặc service/domain repository; nó phải giữ đúng subject, scope và consent đã được cấp.

Bài học thuộc chương **OIDC UserInfo**, module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Nội dung tập trung vào OidcUserInfoEndpointConfigurer, OidcUserInfoAuthenticationContext và cách triển khai userInfoMapper an toàn.

> **Quy tắc quan trọng:** UserInfo response luôn phải có claim sub. RP phải so sánh chính xác sub này với sub trong ID Token. Nếu hai giá trị khác nhau, RP phải loại bỏ toàn bộ UserInfo response để tránh token substitution.

## 1. UserInfo Endpoint giải quyết vấn đề gì?

Một RP thường cần biết người dùng đã đăng nhập thành công và một số thông tin hồ sơ để hiển thị giao diện hoặc hoàn thành một tác vụ. ID Token có thể chứa một số claims, nhưng không nhất thiết chứa toàn bộ thông tin. UserInfo cho phép RP yêu cầu thêm thông tin theo access token và các scopes đã được cấp.

Ví dụ, RP yêu cầu:

~~~text
scope=openid profile email
~~~

Sau khi Authorization Server xác thực người dùng, áp dụng consent và cấp token, RP có thể gọi UserInfo:

~~~http
GET /userinfo HTTP/1.1
Host: identity.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-42",
  "name": "Nguyen Van An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true
}
~~~

RP có thể sử dụng những claims đã được OP cho phép để cá nhân hóa trải nghiệm. OP có thể lược bỏ một số claims vì privacy policy; việc một claim được yêu cầu nhưng không được trả về không tự động là lỗi giao thức.

### 1.1. ID Token và UserInfo khác nhau

| Khía cạnh | ID Token | UserInfo response |
|---|---|---|
| Mục đích | Chứng minh thông tin xác thực và subject cho RP | Trả thêm claims về End-User |
| Định dạng phổ biến | JWT đã ký | JSON object qua HTTPS |
| Credential để lấy | Được trả về từ token/authorization flow | Access token |
| Thời điểm | Khi hoàn thành OIDC authentication flow | Khi RP cần đọc thông tin người dùng |
| Claim định danh | sub | sub, phải khớp ID Token |
| Thông tin có thể thay đổi | Snapshot tại thời điểm phát hành | Có thể phản ánh hồ sơ hiện tại theo policy |
| Quyền truy cập | RP đã nhận ID Token | Access token phải có quyền phù hợp |

Không dùng ID Token làm Bearer credential để gọi UserInfo. UserInfo endpoint yêu cầu access token.

### 1.2. UserInfo không phải User Account API tổng quát

UserInfo phục vụ OIDC RP lấy các claims về End-User gắn với authorization tương ứng. Nó không nên trở thành API quản trị tài khoản, endpoint tìm kiếm người dùng hoặc cách để RP đọc mọi trường trong database identity.

Nếu RP cần thao tác nghiệp vụ riêng như đổi email, quản lý thiết bị, cập nhật địa chỉ hoặc tìm kiếm tổ chức, hãy thiết kế API phù hợp với authorization model riêng. UserInfo chỉ trả dữ liệu định danh/hồ sơ đã được OP cho phép.

## 2. Luồng OIDC từ authorization đến UserInfo

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Relying Party
    participant OP as OpenID Provider
    participant U as End-User

    RP->>OP: Authorization Request (scope=openid profile email)
    OP->>U: Authenticate + obtain consent
    U-->>OP: Authentication and consent result
    OP-->>RP: Authorization Code
    RP->>OP: Token Request + code_verifier
    OP-->>RP: ID Token + Access Token
    Note over RP: Validate ID Token signature, iss, aud, exp, nonce
    RP->>OP: GET UserInfo + Authorization: Bearer Access Token
    OP->>OP: Validate access token and resolve authorization
    OP->>OP: Map authorized claims to OidcUserInfo
    OP-->>RP: JSON claims including sub
    Note over RP: Compare UserInfo sub with ID Token sub
~~~

Các bước chính:

1. RP gửi Authentication Request có scope openid và các scopes hồ sơ cần thiết.
2. OP xác thực End-User và thu thập consent theo chính sách.
3. OP trả Authorization Code; RP đổi code lấy ID Token và Access Token.
4. RP xác minh ID Token độc lập.
5. RP gửi Access Token đến UserInfo endpoint bằng Bearer scheme.
6. OP xác minh access token, tìm authorization và tạo UserInfo claims.
7. RP xác minh sub trong UserInfo khớp chính xác sub trong ID Token.

### 2.1. UserInfo là OAuth2 protected resource

Theo OIDC Core, access token lấy từ OIDC Authentication Request phải được gửi như Bearer Token theo RFC 6750. OIDC Core khuyến nghị dùng HTTP GET và gửi token trong Authorization header. POST cũng được định nghĩa, nhưng GET với Authorization header là cách thông dụng.

~~~http
GET https://identity.example.com/userinfo
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Không gửi access token trong query string. URL thường xuất hiện trong reverse proxy logs, tracing, browser history hoặc analytics. Cũng không gửi ID Token, refresh token hay client secret thay cho access token.

### 2.2. openid scope là điều kiện của OIDC

openid phân biệt một OAuth2 authorization request thông thường với OIDC Authentication Request. Các scopes profile, email, address, phone bổ sung yêu cầu về nhóm claims tiêu chuẩn.

Một client chỉ yêu cầu profile mà không có openid không thể coi đó là một OIDC UserInfo authorization hợp lệ. Cấu hình RegisteredClient và flow cấp token cần hỗ trợ OIDC scopes tương ứng.

## 3. Các standard claims và scopes

OIDC Core định nghĩa các nhóm claims tiêu chuẩn. Scope cho biết nhóm claims mà RP yêu cầu; OP vẫn có thể áp dụng consent, privacy policy và giới hạn dữ liệu thực tế.

| Scope | Các claims tiêu biểu | Ví dụ |
|---|---|---|
| openid | sub | Subject identifier ổn định trong phạm vi issuer |
| profile | name, given_name, family_name, middle_name, nickname, preferred_username, profile, picture, website, gender, birthdate, zoneinfo, locale, updated_at | Tên, ảnh và thông tin hồ sơ |
| email | email, email_verified | Địa chỉ email và trạng thái xác minh |
| address | address | Địa chỉ dạng JSON object |
| phone | phone_number, phone_number_verified | Số điện thoại và trạng thái xác minh |

### 3.1. Claim address là object

address không phải một chuỗi tùy ý nếu sử dụng cấu trúc chuẩn OIDC. Ví dụ:

~~~json
{
  "address": {
    "formatted": "123 Nguyen Hue, District 1, Ho Chi Minh City",
    "street_address": "123 Nguyen Hue",
    "locality": "Ho Chi Minh City",
    "region": "Ho Chi Minh",
    "postal_code": "700000",
    "country": "VN"
  }
}
~~~

Chỉ trả các trường address mà người dùng đã cho phép và RP có lý do sử dụng. Địa chỉ đầy đủ có thể là PII nhạy cảm; không tự động trả vì client yêu cầu scope.

### 3.2. email_verified và phone_number_verified

Các boolean này là trạng thái xác minh do OP quản lý. Không đặt email_verified=true chỉ vì người dùng đã nhập email hoặc vì email có định dạng hợp lệ. Tương tự, phone_number_verified=true chỉ khi quy trình xác minh số điện thoại đã hoàn tất theo policy.

Nếu không có bằng chứng xác minh, trả false hoặc bỏ claim theo semantics của hệ thống; không tự suy đoán.

### 3.3. Scope yêu cầu không đồng nghĩa quyền vô hạn

RP có thể yêu cầu profile email address phone, nhưng OP không bắt buộc phải trả mọi trường. OP có thể chỉ trả claims có trong hồ sơ, chỉ trả claims thuộc scopes đã được cấp, áp dụng consent và policy theo client, lược bỏ claims nhạy cảm, không trả claim chưa được xác minh hoặc dùng subject identifier pairwise theo client/sector.

Một claim không được trả nên được omit khỏi JSON thay vì xuất hiện với giá trị null hoặc chuỗi rỗng.

## 4. Subject identifier và yêu cầu khớp sub

sub là định danh subject do OP cấp. Trong một issuer, subject identifier phải locally unique và không được tái sử dụng cho một End-User khác. Kết hợp iss và sub là định danh ổn định mà RP có thể dựa vào.

UserInfo response MUST luôn có sub. RP cũng MUST xác minh sub trong UserInfo khớp chính xác với sub của ID Token. Nếu khác nhau, RP không được sử dụng các claims trong response.

Ví dụ ID Token:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": "portal-web",
  "sub": "user-42",
  "exp": 1794850600
}
~~~

UserInfo hợp lệ:

~~~json
{
  "sub": "user-42",
  "name": "Nguyen Van An"
}
~~~

UserInfo không hợp lệ với ID Token trên:

~~~json
{
  "sub": "user-84",
  "name": "Another User"
}
~~~

Trong trường hợp thứ hai, RP phải bỏ toàn bộ response. Không cố gắng sửa subject bằng cách ghi đè sub theo ID Token vì như vậy có thể che giấu token substitution hoặc lỗi liên kết authorization.

### 4.1. public và pairwise subject

- **Public subject:** cùng một subject identifier được cung cấp cho các client theo policy của OP.
- **Pairwise subject:** mỗi client/sector nhận một sub khác nhau để giảm khả năng các RP liên kết hoạt động của cùng End-User.

UserInfo mapper không được tự tạo một sub ngẫu nhiên mỗi request. Nó phải lấy đúng subject đã gắn với authorization/ID Token được dùng trong flow. Nếu OP dùng pairwise identifiers, ID Token và UserInfo của cùng authorization phải dùng cùng pairwise subject.

### 4.2. Không dùng email làm khóa subject

Email có thể thay đổi, có thể được tái sử dụng hoặc có thể chưa xác minh. Không thay sub bằng email, username hoặc database primary key tùy tiện. RP nên dùng cặp iss + sub làm khóa nhận diện theo OIDC.

## 5. Bật OIDC UserInfo Endpoint trong Spring Authorization Server

UserInfo endpoint thuộc OIDC. Cần bật OIDC trên OAuth2AuthorizationServerConfigurer:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(userInfoMapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình cho filter chain của Authorization Server. Ứng dụng còn cần các beans như RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, JWKSource<SecurityContext>, login chain và consent flow theo use case.

### 5.1. UserInfo cần JwtDecoder

Trong cấu hình UserInfo endpoint chuẩn của Spring Authorization Server 1.5.x, OIDC tự cấu hình Resource Server support để xác thực access token, nhưng cần một bean JwtDecoder:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Bean này cho phép Resource Server support xác minh access token JWT trước khi request đến mapper. JWKSource phải cung cấp signing key phù hợp và được quản lý an toàn. Không nhầm JwtDecoder dùng xác minh access token đến UserInfo với mapper đọc claims.

### 5.2. Hai SecurityFilterChain thường gặp

Một deployment thường có Authorization Server filter chain ưu tiên cao, match các protocol endpoints; application filter chain xử lý login, session, consent page và các routes còn lại.

UserInfo request mang Bearer token, không phải browser login session. Nếu matcher/order sai, request có thể bị chuyển tới form login hoặc bị application chain xử lý như một endpoint thông thường.

### 5.3. URL UserInfo

RP nên lấy URL từ userinfo_endpoint trong OpenID Provider Configuration thay vì hardcode. Endpoint phải dùng HTTPS trong deployment thực tế. Nếu đổi public host, context path hoặc reverse proxy, discovery và route runtime phải đồng bộ.

## 6. OidcUserInfoEndpointConfigurer có những điểm mở rộng nào?

OidcUserInfoEndpointConfigurer cho phép tùy chỉnh các giai đoạn pre-processing, main processing và post-processing của UserInfo request.

| API | Vai trò | Dùng khi nào? |
|---|---|---|
| userInfoRequestConverter(...) | Thêm AuthenticationConverter | Request format cần mở rộng |
| userInfoRequestConverters(...) | Thao tác danh sách converter mặc định và bổ sung | Điều chỉnh thứ tự hoặc thay converter |
| authenticationProvider(...) | Thêm AuthenticationProvider | Xử lý loại authentication riêng |
| authenticationProviders(...) | Thao tác danh sách provider | Thêm, bỏ hoặc tùy chỉnh provider |
| userInfoResponseHandler(...) | AuthenticationSuccessHandler | Tùy chỉnh HTTP success response |
| errorResponseHandler(...) | AuthenticationFailureHandler | Tùy chỉnh OAuth2 error response |
| userInfoMapper(...) | Function<OidcUserInfoAuthenticationContext, OidcUserInfo> | Ánh xạ context đã xác thực thành claims UserInfo |

### 6.1. Pre-processing: request converter

Converter mặc định nội bộ lấy Authentication từ SecurityContext và tạo OidcUserInfoAuthenticationToken với principal tương ứng. Phần lớn ứng dụng không cần tự viết converter cho request chuẩn.

Chỉ thêm converter khi có một protocol extension hoặc request handling đặc thù đã được thiết kế. Converter không nên tự đọc database hồ sơ, tự quyết định claims hay bỏ qua access-token authentication.

### 6.2. Main processing: authentication provider

Provider mặc định là OidcUserInfoAuthenticationProvider, được tạo với OAuth2AuthorizationService. Nó xử lý OidcUserInfoAuthenticationToken, liên kết bearer access token với authorization và sử dụng mapper để tạo OidcUserInfo.

Trong Spring Authorization Server 1.5.8, provider này là final; nó có setUserInfoMapper(...), và configurer cung cấp API userInfoMapper(...) để cài mapper. Thông thường không cần subclass provider hoặc tự thay toàn bộ authentication flow chỉ để thay đổi claims.

### 6.3. Post-processing: response và error handlers

userInfoResponseHandler trả UserInfo response sau khi provider xác thực thành công. errorResponseHandler trả OAuth2 error khi authentication thất bại. Nếu chỉ cần thay đổi dữ liệu claims, hãy dùng mapper và giữ response handler mặc định.

Viết response handler riêng đồng nghĩa ứng dụng chịu trách nhiệm giữ đúng JSON serialization, content type, status code và error semantics. Không dùng handler để bỏ qua token validation hoặc tự biến request không hợp lệ thành success.

## 7. OidcUserInfoAuthenticationContext chứa dữ liệu gì?

Mapper nhận một OidcUserInfoAuthenticationContext. Context này cung cấp:

| API | Nội dung |
|---|---|
| getAuthentication() | OidcUserInfoAuthenticationToken của request |
| getAccessToken() | OAuth2 access token dùng để gọi UserInfo |
| getAuthorization() | OAuth2Authorization chứa OidcIdToken và OAuth2AccessToken gắn với bearer token |
| get(key) / hasKey(key) | Các context attributes bổ sung nếu có |

Nhờ đó mapper có thể lấy subject từ ID Token/authorization đã lưu, đọc scopes của access token, lấy claims đã có trong ID Token, tra cứu hồ sơ từ database hoặc domain service và quyết định claims nào được phép xuất hiện trong response.

### 7.1. Authentication token và principal

OidcUserInfoAuthenticationToken có principal là Authentication đã được xác thực và có thể chứa OidcUserInfo sau khi provider xử lý. Không coi access token raw hoặc request parameter là nguồn dữ liệu hồ sơ đáng tin cậy.

Khi access token là JWT và resource-server support tạo JwtAuthenticationToken, mapper có thể đọc JWT claims từ principal. Đây là một lựa chọn; nó không có nghĩa nên sao chép toàn bộ access token claims sang UserInfo.

### 7.2. Authorization record là điểm liên kết quan trọng

getAuthorization() giúp mapper truy cập authorization đã phát hành token. Điều này hữu ích để liên kết đúng subject, ID Token và scopes. Không tra cứu người dùng theo một claim do caller gửi lên hoặc theo email không được xác minh.

## 8. Default userInfoMapper hoạt động thế nào?

Theo mặc định trong Spring Authorization Server:

1. UserInfo filter nhận Bearer access token và xác thực token bằng Resource Server support.
2. Provider tìm authorization tương ứng trong OAuth2AuthorizationService.
3. Mapper nội bộ lấy các standard claims từ ID Token.
4. Claims được chọn theo các scopes đã được yêu cầu trong authorization.
5. Provider tạo OidcUserInfo; success handler trả JSON response.

Đây là cách phù hợp khi ID Token đã chứa các standard claims cần thiết và ứng dụng muốn dùng cùng nguồn claims cho ID Token/UserInfo.

### 8.1. Khi nào default mapping là đủ?

Nếu application đã thêm name, email, email_verified hoặc các standard claims phù hợp vào ID Token, và scope authorization đã xác định claim nào được chia sẻ, default mapper thường là lựa chọn đơn giản nhất.

### 8.2. Khi nào cần custom mapper?

Custom mapper hữu ích khi UserInfo cần đọc dữ liệu hồ sơ mới nhất từ database, một số claims chỉ được trả qua UserInfo, cần lọc claims theo tenant/client policy, dữ liệu nằm trong LDAP/domain service hoặc cần chuyển đổi cấu trúc dữ liệu sang OIDC standard claims.

Không dùng custom mapper chỉ để sao chép toàn bộ claims từ một token sang JSON. Điều đó có thể tiết lộ internal claims, authorization metadata hoặc thông tin không dành cho RP.

## 9. Tùy chỉnh ID Token hay UserInfo Mapper?

Spring Authorization Server hướng dẫn rằng cách ưu tiên để tùy chỉnh UserInfo là thêm standard claims vào ID Token; default mapper sau đó có thể sử dụng các claims này theo scopes. Khi cần tùy chỉnh toàn bộ UserInfo response hoặc lấy dữ liệu động, dùng userInfoMapper.

| Nhu cầu | Cách tiếp cận |
|---|---|
| Claim cần có trong ID Token và UserInfo | OAuth2TokenCustomizer<JwtEncodingContext> cho ID Token |
| Claim chỉ cần trong UserInfo | userInfoMapper |
| Claim lấy từ domain service tại thời điểm UserInfo request | userInfoMapper + service |
| Thay đổi HTTP headers/serialization | userInfoResponseHandler |
| Thay đổi cách authenticate UserInfo request | Authentication converter/provider có chủ đích |

### 9.1. Thêm claims vào ID Token

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
        UserInfoService userInfoService) {

    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            OidcUserInfo userInfo =
                userInfoService.loadUser(context.getPrincipal().getName());
            context.getClaims().claims(claims ->
                claims.putAll(userInfo.getClaims()));
        }
    };
}
~~~

Đây là cách minh họa từ Spring guide. Trong production, service phải trả claims theo scopes/consent đã được cấp và không nhúng PII quá mức vào ID Token. OidcUserInfo cần có subject nhất quán.

### 9.2. Khi ID Token quá lớn

ID Token thường được RP nhận ở token response và có thể được lưu trong session/cookie hoặc truyền qua các thành phần khác. Đưa mọi thông tin hồ sơ vào ID Token làm tăng kích thước và lượng PII được phân phối. Chỉ đưa các claims RP thực sự cần tại thời điểm authentication; dữ liệu hồ sơ có thể tải qua UserInfo khi cần.

## 10. Viết userInfoMapper theo scope và consent

Một custom mapper nên thực hiện các bước:

1. Lấy authorization và ID Token gắn với access token hiện tại.
2. Xác định subject ổn định từ ID Token/authorization.
3. Lấy scopes của access token đã được cấp.
4. Tra cứu hồ sơ từ nguồn tin cậy bằng subject.
5. Chỉ đưa claims thuộc scopes và policy đã cho phép vào response.
6. Luôn thêm sub đúng như ID Token.
7. Bỏ các trường không có dữ liệu hoặc không được phép tiết lộ.

Ví dụ mapper minh họa:

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        UserInfoService userInfoService) {

    return context -> {
        OAuth2Authorization authorization = context.getAuthorization();
        OidcIdToken idToken = authorization
            .getToken(OidcIdToken.class)
            .getToken();

        String subject = idToken.getSubject();
        Set<String> scopes = context.getAccessToken().getScopes();
        UserProfile profile = userInfoService.loadBySubject(subject);

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", profile.name());
            putIfPresent(claims, "given_name", profile.givenName());
            putIfPresent(claims, "family_name", profile.familyName());
            putIfPresent(claims, "preferred_username",
                profile.preferredUsername());
            putIfPresent(claims, "picture", profile.pictureUrl());
        }

        if (scopes.contains(OidcScopes.EMAIL)) {
            putIfPresent(claims, "email", profile.email());
            putIfPresent(claims, "email_verified",
                profile.emailVerified());
        }

        if (scopes.contains(OidcScopes.PHONE)) {
            putIfPresent(claims, "phone_number", profile.phoneNumber());
            putIfPresent(claims, "phone_number_verified",
                profile.phoneNumberVerified());
        }

        if (scopes.contains(OidcScopes.ADDRESS)) {
            putIfPresent(claims, "address", profile.address());
        }

        return new OidcUserInfo(claims);
    };
}

private static void putIfPresent(
        Map<String, Object> claims, String name, Object value) {
    if (value == null) {
        return;
    }
    if (value instanceof String text && text.isBlank()) {
        return;
    }
    claims.put(name, value);
}
~~~

UserInfoService và UserProfile là domain types do ứng dụng định nghĩa. Đoạn code minh họa cách phân quyền claims theo scopes; cần bổ sung xử lý authorization record thiếu ID Token, user không còn tồn tại, consent bị thu hồi và policy riêng theo RegisteredClient. Không để exception hạ tầng biến thành một response chứa claims mặc định.

### 10.1. Không chỉ dựa vào requested scopes

Request ban đầu có thể yêu cầu nhiều scopes nhưng người dùng hoặc policy không chấp thuận tất cả. Mapper phải dựa trên scopes thực sự gắn với access token/authorization đã được cấp, không dựa vào chuỗi query scope tự đọc từ request UserInfo.

### 10.2. Client-specific disclosure policy

Cùng một subject có thể đăng nhập qua nhiều RP. Một RP cần email, RP khác chỉ cần subject. Có thể áp dụng policy dựa trên RegisteredClient đã gắn với authorization, nhưng không được dùng client ID tùy ý từ UserInfo request để quyết định dữ liệu được tiết lộ.

### 10.3. Claims request parameter

OIDC Core có cơ chế yêu cầu claims chi tiết qua claims request parameter. Không giả định chỉ vì mapper nhận được context thì ứng dụng đã tự động hỗ trợ đầy đủ mọi yêu cầu individual claims. Nếu cần triển khai semantics này, phải lưu/đọc request context tương ứng, xác minh yêu cầu với consent/policy và kiểm thử riêng. Scope-based mapping mặc định là một cơ chế khác.

## 11. Cấu hình userInfoMapper qua configurer

Ví dụ wiring mapper vào UserInfo endpoint:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        UserInfoService userInfoService) throws Exception {

    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper =
        userInfoMapper(userInfoService);

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(mapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Ví dụ tập trung vào API cấu hình. Trong codebase thực tế, có thể tách mapper thành bean riêng để dễ unit test, inject service và quản lý dependency. Không tạo một mapper singleton chứa mutable state giữa các request.

### 11.1. Giữ converter/provider mặc định khi không cần thay

Nếu chỉ custom mapper, hãy giữ default request converter, provider, success handler và failure handler. Chỉ dùng userInfoRequestConverters(...), authenticationProviders(...), userInfoResponseHandler(...) hoặc errorResponseHandler(...) khi có yêu cầu rõ ràng.

### 11.2. Thay đổi danh sách provider

Configurer có thể cho truy cập danh sách provider mặc định để thêm/bỏ/customize. Nhưng provider mặc định OidcUserInfoAuthenticationProvider là final. Nếu thay provider, ứng dụng phải tự bảo toàn các bước xác minh bearer token, liên kết authorization, kiểm tra token và tạo response claims. Thay provider chỉ để thay claims thường không cần thiết; userInfoMapper là API đúng mục đích.

## 12. RegisteredClient và OIDC scopes

RegisteredClient cần cho phép OIDC scopes mà RP sẽ yêu cầu:

~~~java
RegisteredClient client = RegisteredClient.withId("portal-web-id")
    .clientId("portal-web")
    .clientSecret(passwordEncoder.encode(clientSecret))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://portal.example.com/login/oauth2/code/portal-web")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope(OidcScopes.EMAIL)
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

Đây là ví dụ confidential client cho Authorization Code Flow. Public client cần cấu hình phù hợp với PKCE và không được gán client secret giả. Consent requirement tùy UX và policy; nếu bật consent, consent page phải lưu lựa chọn scopes được người dùng chấp thuận.

### 12.1. Đăng ký scope không có nghĩa mọi claim được trả

RegisteredClient.scope(...) cho phép client yêu cầu scope. Nó không tự tạo hồ sơ người dùng, không tự xác minh email/phone và không bắt buộc OP trả toàn bộ claims. Mapper/domain service vẫn phải lọc claims theo dữ liệu và policy.

### 12.2. Client yêu cầu scopes cụ thể

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&scope=openid%20profile%20email&redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&state=STATE_VALUE&code_challenge=CHALLENGE&code_challenge_method=S256
~~~

Authorization request cần các tham số bảo vệ tương ứng như state, PKCE và redirect URI đã đăng ký. Sau consent, access token chỉ nên chứa scopes thực tế được cấp.

## 13. Access token JWT và dữ liệu UserInfo

Trong cấu hình Spring Authorization Server thông dụng, UserInfo endpoint sử dụng Resource Server support để xác thực access token JWT; vì vậy JwtDecoder là bean bắt buộc cho endpoint tích hợp sẵn.

Có một số nguồn dữ liệu mapper có thể sử dụng:

| Nguồn | Ưu điểm | Lưu ý |
|---|---|---|
| Claims trong ID Token/authorization | Dữ liệu nhất quán với authorization đã phát hành | Là snapshot tại thời điểm cấp token |
| Claims trong access token JWT | Có thể lấy từ JwtAuthenticationToken và custom access token claims | Access token có thể mang internal/resource claims không dành cho UserInfo |
| Domain service/database | Hồ sơ mới nhất và dữ liệu chuyên biệt | Cần authorization, latency budget, cache và error handling |
| LDAP/external identity service | Tích hợp hệ thống danh tính hiện có | Không để dependency chậm làm treo endpoint |

### 13.1. Mapper dựa trên JWT principal

Spring guide có ví dụ lấy JwtAuthenticationToken từ OidcUserInfoAuthenticationToken.getPrincipal() rồi tạo OidcUserInfo từ JWT claims. Cách này ngắn gọn khi access token JWT đã chứa đúng claims cần trả.

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper =
    context -> {
        OidcUserInfoAuthenticationToken authentication =
            context.getAuthentication();
        JwtAuthenticationToken principal =
            (JwtAuthenticationToken) authentication.getPrincipal();

        Map<String, Object> claims =
            new HashMap<>(principal.getToken().getClaims());

        return new OidcUserInfo(claims);
    };
~~~

Đây là ví dụ minh họa API của Spring. Trong production, không copy toàn bộ claims như vậy nếu access token có aud, internal role, tenant metadata, policy flags hoặc dữ liệu chỉ dành cho Resource Server. Hãy dùng allowlist và luôn bảo đảm sub đúng với ID Token.

### 13.2. Opaque access token

Spring Authorization Server 1.5.x UserInfo endpoint tích hợp sẵn yêu cầu JwtDecoder và xác thực access token qua Resource Server JWT support. Nếu kiến trúc cần opaque access token, phải đánh giá một cơ chế Resource Server/introspection tích hợp riêng hoặc implementation phù hợp; không giả định built-in UserInfo filter sẽ tự hiểu mọi opaque token chỉ vì Authorization Server có introspection endpoint.

## 14. Consent, privacy và dữ liệu hồ sơ

UserInfo response có thể chứa dữ liệu nhận dạng cá nhân. Cần thiết kế disclosure theo nguyên tắc **data minimization**:

- Chỉ trả claims thuộc scopes/claims request được cấp;
- Kiểm tra consent và client policy;
- Không trả internal database IDs nếu không phải subject identifier công khai;
- Không trả email/phone verification status sai;
- Không trả địa chỉ đầy đủ cho RP không cần;
- Không dùng mapper để vượt qua consent đã lưu;
- Hỗ trợ thu hồi consent theo authorization lifecycle của ứng dụng.

### 14.1. Consent và scopes đã cấp

Consent UI có thể hiển thị profile, email, address, phone theo nhóm thông tin dễ hiểu. Khi người dùng chỉ chấp thuận openid profile, mapper không được trả email chỉ vì email có sẵn trong database.

Nếu consent bị thu hồi sau khi access token đã được cấp, cần xác định policy hiệu lực: revoke authorization/access token, giới hạn thời gian sống token hoặc tra cứu consent hiện tại trong mapper. Không giả định thay đổi consent tự động thay đổi mọi access token đã phát hành.

### 14.2. Không đưa PII vào logs

Không log raw UserInfo JSON, access token, email, phone, address hoặc toàn bộ claims trong production. Có thể ghi request correlation ID, client ID đã xác thực, subject đã pseudonymize, scope names, status và latency theo privacy policy.

### 14.3. Không trả claim với giá trị giả

Không trả email_verified=true nếu chưa xác minh. Không trả phone_number_verified=true theo mặc định. Không tạo tên/avatar placeholder để thay dữ liệu thiếu. Claim không có hoặc không được phép trả nên được omit.

## 15. UserInfo response handler và error handler

userInfoResponseHandler chịu trách nhiệm chuyển authentication thành HTTP response. Success handler mặc định của Spring Authorization Server trả OidcUserInfo dưới dạng UserInfo response.

Chỉ tùy chỉnh response handler nếu cần:

- Thêm headers/correlation metadata;
- Serialization đặc biệt đã được đăng ký/hỗ trợ;
- Audit success mà không ghi PII;
- Điều chỉnh cache policy theo privacy requirements.

### 15.1. Không tính claims trong success handler

Success handler không nên tự gọi database, tự quyết định subject hoặc thêm claims sau mapper. Đưa logic dữ liệu vào mapper/domain service để dễ unit test và đảm bảo response luôn được tạo theo cùng một policy.

### 15.2. Error response

errorResponseHandler xử lý OAuth2AuthenticationException. Các lỗi thường gặp:

| Trường hợp | Kết quả thường thấy |
|---|---|
| Thiếu access token | 401 / Bearer challenge |
| Token sai chữ ký, hết hạn hoặc không hợp lệ | 401 invalid_token |
| Token không đủ scope theo policy | 403 insufficient_scope khi phù hợp |
| Authorization record không tồn tại/không liên kết | Từ chối request |
| Domain service lỗi | Lỗi server phù hợp, không trả claims suy đoán |

Không biến lỗi lookup user thành response success chỉ có sub nếu điều đó che giấu sự cố hoặc vi phạm contract của ứng dụng. Chọn rõ semantics: claim tùy chọn có thể omit; lỗi làm không thể xác định đúng subject/authorization phải fail closed.

## 16. Kiểm tra subject consistency ở Relying Party

RP chịu trách nhiệm xác minh UserInfo response sau khi nhận:

1. Xác minh ID Token: signature, iss, aud, exp, nonce và các kiểm tra OIDC tương ứng.
2. Gọi UserInfo bằng access token đã nhận từ token response.
3. Xác minh TLS/endpoint trust.
4. Parse JSON claims.
5. So sánh userinfo.sub với id_token.sub theo exact string match.
6. Nếu khác nhau, bỏ toàn bộ UserInfo response.
7. Nếu khớp, chỉ sử dụng claims được RP cho phép lưu/hiển thị.

### 16.1. Vì sao cần kiểm tra sub dù TLS và token đều hợp lệ?

Một access token có thể bị thay thế hoặc bị gắn nhầm với authorization khác. Việc xác minh chữ ký ID Token không tự chứng minh UserInfo response đang nói về cùng subject. Exact match sub ngăn RP ghép nhầm hồ sơ người dùng.

### 16.2. Không merge claims trước khi kiểm tra

Không cập nhật hồ sơ local từ UserInfo rồi mới so sánh sub. Phải xác minh subject trước, sau đó mới chấp nhận bất kỳ claim nào. Nếu mismatch, discard toàn bộ response và ghi nhận security event phù hợp.

## 17. Kiểm thử UserInfo endpoint với MockMvc

Integration tests nên chạy qua SecurityFilterChain và provider thật, dùng access token JWT hợp lệ cùng authorization record đã lưu trong OAuth2AuthorizationService.

### 17.1. Positive test với Bearer token

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OidcUserInfoEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsUserInfoForValidOidcAccessToken() throws Exception {
        String accessToken = fixtureOidcAccessToken(
            "user-42", Set.of("openid", "profile", "email"));

        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + accessToken)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.name").value("Nguyen Van An"))
            .andExpect(jsonPath("$.email").value("an@example.com"));
    }
}
~~~

Đây là khung test. fixtureOidcAccessToken(...) phải tạo JWT được ký bằng key test mà JwtDecoder tin cậy, đồng thời lưu authorization chứa access token và ID Token tương ứng vào OAuth2AuthorizationService. URL /userinfo phải khớp endpoint matcher của deployment đang kiểm thử.

### 17.2. Negative test không có token

~~~java
@Test
void rejectsRequestWithoutBearerToken() throws Exception {
    mvc.perform(get("/userinfo")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isUnauthorized());
}
~~~

Kiểm tra endpoint không bị mở anonymous hoặc rơi qua form login HTML trong khi client yêu cầu JSON.

### 17.3. Negative test token không hợp lệ

~~~java
@Test
void rejectsInvalidAccessToken() throws Exception {
    mvc.perform(get("/userinfo")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer NOT_A_VALID_JWT")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isUnauthorized());
}
~~~

Có thể bổ sung expired token, sai signature, sai issuer và authorization record không còn hợp lệ. Không chỉ mock mapper vì cần xác minh token authentication filter hoạt động.

### 17.4. Test scope-based claims filtering

Tạo hai authorization fixtures:

- Token A có openid profile;
- Token B có openid email.

Kỳ vọng:

- Cả hai response đều có sub;
- Token A có profile claims được phép và không có email;
- Token B có email claims được phép và không có profile claims;
- email_verified phản ánh trạng thái thực tế;
- Claims thiếu bị omit, không trả null/empty.

### 17.5. Test subject consistency

Tạo ID Token có sub=user-42, nhưng cố tình cấu hình test UserInfo mapper trả sub=user-84. Ở phía RP integration test, response phải bị loại bỏ hoàn toàn và không được merge claims vào local account. Đây là test quan trọng chống token substitution.

### 17.6. Test mapper và domain service

Unit test riêng cho mapper:

- ID Token/authorization thiếu subject;
- Hồ sơ người dùng không tồn tại;
- Scope không được cấp;
- Email chưa verified;
- Profile có field null/blank;
- Domain service timeout;
- Client không được phép nhận claim nhạy cảm;
- Pairwise subject được giữ nguyên.

Giữ test mapper tách khỏi HTTP tests để xác định lỗi nằm ở policy mapping hay filter chain.

## 18. Hiệu năng và độ sẵn sàng của mapper

UserInfo được gọi trong request path của RP. Nếu mapper thực hiện database query hoặc gọi dịch vụ ngoài, độ trễ đó tác động trực tiếp tới login/profile retrieval.

Khuyến nghị:

- Dùng query có index theo subject identifier;
- Chỉ đọc các cột cần thiết;
- Đặt timeout cho LDAP/HTTP calls;
- Tránh gọi một dịch vụ ngoài cho từng claim;
- Có circuit breaker/bulkhead nếu dependency quan trọng;
- Cache có TTL và invalidation policy rõ ràng;
- Không cache response chứa PII công khai;
- Theo dõi latency và lỗi theo dependency.

### 18.1. Cache theo subject và authorization context

Nếu cache dữ liệu hồ sơ, cache key nên gắn với subject/tenant và policy context phù hợp. Không cache một response UserInfo hoàn chỉnh rồi dùng chung giữa các RP nếu claims được giới hạn theo client hoặc consent khác nhau.

### 18.2. Dữ liệu mới nhất hay snapshot?

Chọn rõ semantics:

- **Snapshot:** claims lấy từ ID Token/authorization tại thời điểm cấp token; ổn định trong vòng đời token.
- **Live profile:** mapper đọc database hiện tại; thay đổi hồ sơ có thể xuất hiện ngay ở UserInfo tiếp theo.

Không trộn hai semantics mà không xác định ưu tiên. Subject phải ổn định dù dữ liệu hồ sơ thay đổi.

## 19. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên bật .oidc(...) | Không có UserInfo endpoint | Bật OIDC configurer |
| Thiếu JwtDecoder bean | UserInfo resource-server authentication không hoạt động | Cấu hình decoder phù hợp JWK source |
| Gửi ID Token tới UserInfo | Sai credential type | Gửi access token |
| Gửi token trong query string | Token rò qua URL/log | Dùng Authorization Bearer header |
| Mapper không trả sub | Vi phạm OIDC Core | Luôn thêm subject từ authorization/ID Token |
| Mapper tự tạo sub khác ID Token | RP có thể ghép nhầm user | Giữ subject gốc, test exact match |
| Copy toàn bộ JWT claims | Rò internal claims/PII | Dùng allowlist |
| Dựa vào scopes requested thay vì granted | Trả claims chưa được cấp | Dùng scopes gắn với access token/authorization |
| Trả email_verified=true mặc định | Khẳng định sai trạng thái xác minh | Lấy trạng thái từ nguồn xác minh |
| Mapper query bằng email | Subject không ổn định, dễ nhầm tài khoản | Lookup theo subject |
| Tự viết success handler không đúng JSON | RP không parse được UserInfo | Giữ default handler nếu không cần custom |
| Log raw UserInfo/token | Rò PII và credential | Redact logs, audit metadata tối thiểu |
| Dùng UserInfo như account search API | Lộ dữ liệu vượt OIDC consent | Thiết kế API nghiệp vụ riêng |

## 20. Vận hành và giám sát

Theo dõi endpoint ở mức không chứa dữ liệu nhạy cảm:

| Metric/event | Mục đích |
|---|---|
| oidc_userinfo_requests_total | Số request theo kết quả |
| oidc_userinfo_authentication_failures_total | Token lỗi/hết hạn/không hợp lệ |
| oidc_userinfo_mapper_duration | Thời gian map claims |
| oidc_userinfo_profile_lookup_errors | Lỗi database/LDAP/profile service |
| oidc_userinfo_claims_count | Theo dõi số lượng claims trả về |
| oidc_userinfo_scope_distribution | Phân bố scope đã cấp |
| oidc_userinfo_subject_mismatch | Security event phía RP nếu phát hiện mismatch |

Không ghi raw subject, email, phone, access token hoặc toàn bộ UserInfo JSON trong metric labels. Dùng correlation ID và pseudonymous identifiers theo privacy policy.

### 20.1. Rate limiting

UserInfo là protected resource, nhưng vẫn có thể bị lạm dụng bởi client hoặc token bị lộ. Có thể giới hạn request theo client, subject, token family hoặc IP theo policy. Không dùng IP làm định danh duy nhất vì client có thể đi qua NAT/proxy.

### 20.2. Cache và HTTP headers

UserInfo response có thể chứa PII. Cần cân nhắc Cache-Control: no-store hoặc policy cache riêng tư phù hợp, tránh shared proxy/browser cache lưu dữ liệu người dùng. Nếu thay response handler mặc định, kiểm tra header thực tế qua integration test.

### 20.3. Data access audit

Tổ chức có thể cung cấp cho End-User khả năng xem RP nào đã truy cập thông tin UserInfo và thời điểm nào. Audit phải xác định client đã xác thực và phạm vi scopes, đồng thời giới hạn retention và truy cập audit log.

## 21. Checklist production

1. **OIDC enabled:** OAuth2AuthorizationServerConfigurer.oidc(...) được bật?
2. **Discovery:** userinfo_endpoint công bố đúng URL HTTPS?
3. **JWT validation:** có JwtDecoder bean và trust đúng signing keys/issuer?
4. **Bearer token:** endpoint chỉ chấp nhận access token theo Bearer scheme?
5. **Authorization:** token gắn với OIDC authorization có openid scope và scopes phù hợp?
6. **Subject:** mapper luôn trả sub từ ID Token/authorization gốc?
7. **RP validation:** client so sánh exact sub với ID Token và discard response khi mismatch?
8. **Scopes:** claims được giới hạn theo scopes đã cấp và consent?
9. **PII:** chỉ trả claims tối thiểu, không lộ internal attributes?
10. **Verification flags:** email_verified/phone_number_verified lấy từ trạng thái thực?
11. **Mapper:** lookup theo subject, timeout và error handling rõ?
12. **Provider:** giữ default provider nếu không cần thay semantics?
13. **Response:** JSON content type, headers và error semantics đúng?
14. **Transport:** HTTPS, không truyền token trong URL?
15. **Logging:** không ghi token, raw UserInfo hoặc PII?
16. **Testing:** positive/negative, scope filtering, subject mismatch, expired/bad signature?
17. **Performance:** database/external lookups có timeout, index, cache policy?
18. **Operations:** metrics, audit, rate limiting và incident handling?

## 22. Bài tập vận dụng

**Tình huống A — Subject mismatch:** ID Token có sub=user-42, UserInfo mapper trả sub=user-84. RP cần xử lý thế nào? Vì sao không được chỉ ghi đè claim sub rồi dùng các claims khác?

**Tình huống B — Scope filtering:** RP yêu cầu openid profile email, nhưng consent chỉ cấp openid profile. Mapper có được trả email từ database không? Thiết kế test chứng minh.

**Tình huống C — UserInfo từ database:** Một mapper gọi LDAP để lấy name, email, phone. Làm sao giới hạn timeout, tránh trả claim chưa xác minh và xử lý khi LDAP unavailable?

**Tình huống D — ID Token quá lớn:** Đội phát triển thêm toàn bộ profile, address và phone vào ID Token để không cần UserInfo. Hãy phân tích rủi ro privacy/size và lựa chọn giữa token customizer với UserInfo mapper.

**Tình huống E — Access token opaque:** Deployment chuyển access token từ JWT sang opaque nhưng giữ nguyên UserInfo filter chain tích hợp. Điều gì cần xem xét về JwtDecoder và Resource Server support của Spring Authorization Server?

**Tình huống F — Pairwise subject:** Một user đăng nhập hai RP và nhận hai sub khác nhau. Mapper cần bảo đảm điều gì để UserInfo của mỗi RP vẫn khớp ID Token?

**Gợi ý:** A phải discard toàn bộ response; B chỉ trả claims thuộc scopes thực sự cấp; C cần timeout, circuit breaker, authoritative verification flags và fail policy rõ; D nên giữ ID Token gọn và tải claims phù hợp qua UserInfo; E built-in endpoint yêu cầu JwtDecoder/JWT resource-server support nên phải thiết kế integration khác nếu opaque; F giữ subject đã gắn với authorization của từng RP, không tự sinh subject mới.

## 23. Tổng kết

OidcUserInfoEndpointConfigurer là điểm cấu hình UserInfo endpoint của Spring Authorization Server. Nó cung cấp converter, provider, success/error handlers và userInfoMapper. Với phần lớn ứng dụng, nên giữ request converter/provider/handlers mặc định và tùy chỉnh mapper khi cần thay đổi claims.

OidcUserInfoAuthenticationContext cung cấp authentication, access token và authorization chứa ID Token cùng access token. Mapper có thể lấy standard claims từ ID Token, đọc scopes đã cấp hoặc gọi domain service để lấy hồ sơ. Mọi quyết định trả claims phải dựa trên authorization/consent và policy đáng tin cậy.

UserInfo endpoint là OAuth2 protected resource, yêu cầu Bearer access token. Cấu hình Spring Authorization Server 1.5.x cần OIDC được bật và JwtDecoder bean. RP phải xác minh sub trong UserInfo khớp chính xác sub của ID Token; nếu không, toàn bộ response phải bị loại bỏ.

Thiết kế mapper an toàn nghĩa là giữ sub ổn định, lọc claims theo scopes/consent, không tiết lộ PII/internal claims, xử lý dependency có giới hạn và kiểm thử cả positive lẫn negative flows. Như vậy UserInfo trở thành một giao diện hồ sơ OIDC nhất quán, có thể vận hành và mở rộng mà vẫn bảo vệ quyền riêng tư của End-User.

## 24. Tài liệu tham khảo

- [OpenID Connect Core 1.0 incorporating errata set 2 — Section 5.3 UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html): UserInfo request/response, Bearer access token, sub matching, standard claims và privacy.
- [OpenID Connect Core 1.0 — Section 5.4 Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): ánh xạ profile, email, address, phone sang standard claims.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer header và protected resource error semantics.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): bật UserInfo endpoint, ID Token customization và userInfoMapper.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OidcUserInfoEndpointConfigurer, defaults và endpoint filter.
- [Spring Authorization Server API — OidcUserInfoEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): các phương thức cấu hình và userInfoMapper.
- [Spring Authorization Server API — OidcUserInfoAuthenticationContext](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationContext.html): context attributes, access token và authorization.
- [Spring Authorization Server API — OidcUserInfoAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationProvider.html): provider mặc định và setUserInfoMapper.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication và JwtDecoder.
