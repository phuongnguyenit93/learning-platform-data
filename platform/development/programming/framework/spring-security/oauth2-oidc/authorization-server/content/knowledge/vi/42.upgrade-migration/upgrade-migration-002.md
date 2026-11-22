# Chuyển từ Spring Security OAuth cũ sang Authorization Server hiện hành

Spring Security OAuth (thường được gọi là Spring Security OAuth 2.x) và Spring Authorization Server có mô hình cấu hình, lưu trữ và xử lý token khác nhau. Việc chuyển đổi vì vậy cần được xem là một đợt di trú hệ thống xác thực, không phải chỉ đổi dependency hoặc đổi URL endpoint.

Spring Security OAuth cũ đã được thay thế trong hệ sinh thái Spring. Spring Authorization Server cung cấp nền tảng mới để triển khai OAuth 2.0 và OpenID Connect, tích hợp với Spring Security hiện đại. Mục tiêu của bài này là giúp lập kế hoạch và thực hiện chuyển đổi có kiểm soát: giữ tương thích với client và resource server, di trú đăng ký client và consent, xử lý token đang còn hiệu lực, thay thế các điểm mở rộng cũ và kiểm thử trước khi chuyển lưu lượng.

## 1. Hiểu phạm vi thay đổi

Trong hệ thống cũ, authorization server thường được cấu hình bằng các lớp như **@EnableAuthorizationServer**, **AuthorizationServerConfigurerAdapter**, **AuthorizationServerEndpointsConfigurer**, **AuthorizationServerSecurityConfigurer** và **ClientDetailsServiceConfigurer**. Token được phát hành và quản lý qua **DefaultTokenServices**, **TokenStore**, **OAuth2Request**, **OAuth2Authentication** cùng các implementation liên quan.

Ở nền tảng mới, cấu hình được tổ chức quanh **SecurityFilterChain**, **OAuth2AuthorizationServerConfigurer**, **RegisteredClientRepository**, **OAuth2AuthorizationService**, **OAuth2AuthorizationConsentService**, **OAuth2TokenGenerator** và **AuthorizationServerSettings**.

Các khái niệm nghiệp vụ vẫn quen thuộc: client, redirect URI, scope, authorization code, access token, refresh token và consent. Tuy nhiên, cấu trúc đối tượng, schema lưu trữ, cách mở rộng endpoint và một số mặc định bảo mật đã thay đổi. Không thể coi dữ liệu Java serialized của hệ thống cũ là dữ liệu tương thích trực tiếp với hệ thống mới.

### 1.1 Bản đồ khái niệm cũ và mới

| Spring Security OAuth cũ | Spring Authorization Server | Việc cần làm |
|---|---|---|
| @EnableAuthorizationServer | SecurityFilterChain dành cho endpoint authorization server | Tạo filter chain có matcher và thứ tự phù hợp |
| AuthorizationServerConfigurerAdapter | OAuth2AuthorizationServerConfigurer cùng các bean cấu hình | Chuyển từng tùy chỉnh sang API mới |
| ClientDetailsService | RegisteredClientRepository | Chuyển client, grant, authentication method, redirect URI và scope |
| ClientDetailsServiceConfigurer | Repository in-memory, JDBC hoặc implementation riêng | Chọn nơi lưu client và quản lý schema |
| AuthorizationServerEndpointsConfigurer | Endpoint và extension point của authorization server configurer | Di trú converter, provider, token generator và endpoint tùy chỉnh |
| TokenStore | OAuth2AuthorizationService kết hợp token generator | Xác định cách lưu authorization và định dạng token |
| DefaultTokenServices | OAuth2TokenGenerator và các provider xử lý grant | Chuyển chính sách phát hành, TTL, refresh và thu hồi |
| OAuth2Authentication | OAuth2Authorization, Authentication và ngữ cảnh cấp token | Chuyển logic principal, scope và claim |
| ApprovalStore / approval records | OAuth2AuthorizationConsentService | Ánh xạ consent theo client và principal |
| ResourceServerConfigurerAdapter / @EnableResourceServer | SecurityFilterChain với oauth2ResourceServer | Di trú resource server độc lập |
| OAuth2RestTemplate | Spring Security OAuth2 Client và OAuth2AuthorizedClientManager | Di trú ứng dụng gọi API |

Bảng này là bản đồ khái niệm, không phải ánh xạ một-một cho mọi implementation. Ví dụ, TokenStore cũ có thể lưu JWT, opaque token hoặc dữ liệu trong Redis; cách chuyển phù hợp phụ thuộc vào loại token và cách resource server xác minh token hiện tại.

### 1.2 Xác định thành phần nằm trong phạm vi

Một hệ thống OAuth thường có nhiều ứng dụng và kho dữ liệu cùng tham gia. Trước khi sửa code, lập danh sách:

- Authorization Server: endpoint, grant type, client registry, consent, token store, signing key và custom grant.
- Resource Server: cách xác minh JWT hoặc introspection, ánh xạ scope thành authority, kiểm tra issuer và audience.
- OAuth2 Client: cách lấy token, lưu authorized client, refresh token và xử lý đăng nhập.
- Ứng dụng người dùng: login, consent, session, redirect URI và logout.
- Hạ tầng: database, Redis, KMS/HSM, reverse proxy, gateway, DNS và TLS.
- Hệ thống vận hành: log, audit, metric, alert, backup và quy trình thu hồi token.

Một client có thể vẫn gọi được token endpoint nhưng API phía sau từ chối token vì issuer, audience, chữ ký hoặc claim đã đổi. Vì vậy, chỉ kiểm thử authorization server là chưa đủ.

## 2. Kiểm kê cấu hình và hành vi hệ thống cũ

Tạo bản kiểm kê từ cấu hình đang chạy và dữ liệu thực tế. Không dựa riêng vào file cấu hình vì client có thể được tạo động trong database hoặc qua trang quản trị.

Với mỗi client, ghi nhận:

| Thuộc tính | Nội dung cần thu thập |
|---|---|
| Client ID | Định danh hiện tại và hệ thống sở hữu |
| Client secret | Cách lưu, thuật toán mã hóa/băm và lịch luân chuyển |
| Client authentication | Basic, form post, public client hoặc cơ chế tùy chỉnh |
| Grant type | Authorization Code, Client Credentials, Refresh Token và grant mở rộng |
| Redirect URI | Danh sách chính xác, môi trường và chủ sở hữu |
| Scope | Scope được cấp, mặc định và quy tắc phê duyệt |
| Token policy | TTL access token, refresh token, reuse/rotation và định dạng token |
| Consent | Trạng thái phê duyệt, thời điểm và principal liên quan |
| Customization | Claim, converter, token enhancer, exception handler và endpoint riêng |

Đồng thời kiểm tra các cấu hình toàn cục: issuer, public URL sau reverse proxy, signing key, access token converter, authentication manager, password encoder, CORS, CSRF, session policy và cách xử lý lỗi.

Đối với từng luồng, lưu lại request và response đã loại bỏ bí mật. Một bộ mẫu tối thiểu nên có:

- Client Credentials thành công và thất bại.
- Authorization Code có PKCE, bao gồm trường hợp redirect URI sai.
- Refresh token thành công, hết hạn, bị thu hồi và bị dùng lại.
- Introspection hoặc resource server xác minh token.
- Revocation.
- OIDC discovery, JWKS, UserInfo và logout nếu hệ thống bật OpenID Connect.
- Các lỗi invalid_client, invalid_grant, invalid_scope và lỗi consent.

Các mẫu này sẽ trở thành bộ kiểm thử hồi quy cho hệ thống mới.

## 3. Lập kế hoạch tương thích client và resource server

### 3.1 Endpoint có thể thay đổi

Các endpoint mặc định thường gặp ở hệ thống cũ gồm /oauth/authorize, /oauth/token, /oauth/check_token và /oauth/token_key. Spring Authorization Server thường dùng /oauth2/authorize, /oauth2/token, /oauth2/introspect, /oauth2/revoke và /oauth2/jwks. Endpoint OIDC được công bố khi bật OIDC và phụ thuộc cấu hình server.

Không giả định URL mới tự động tương thích với client cũ. Có ba hướng xử lý:

1. Cập nhật client để dùng endpoint mới và triển khai theo từng nhóm.
2. Dùng reverse proxy hoặc gateway để định tuyến URL cũ sang đúng hệ thống trong giai đoạn chuyển tiếp, sau khi xác nhận request/response tương thích.
3. Giữ endpoint cũ trên authorization server cũ trong một khoảng thời gian, đồng thời cấp client mới trên server mới theo lộ trình rõ ràng.

Không tạo một proxy đổi URL đơn giản rồi coi việc di trú đã hoàn tất. Cần xác nhận phương thức xác thực client, tham số, kiểu lỗi, response token và cơ chế introspection thực sự tương thích.

### 3.2 Giữ ổn định issuer khi có thể

Issuer là định danh của authorization server và thường xuất hiện trong claim iss của JWT, metadata discovery và cấu hình resource server. Nếu đổi issuer, resource server có thể từ chối token dù chữ ký vẫn hợp lệ.

Nếu giữ issuer cũ, bảo đảm URL công khai và cấu hình issuer của server mới khớp chính xác. Cấu hình phía sau proxy cần phản ánh scheme, host và context path công khai; không để server tự suy ra issuer thành địa chỉ nội bộ.

Nếu bắt buộc đổi issuer, lập kế hoạch cập nhật client, resource server, discovery cache, allowlist và monitoring. Trong giai đoạn chuyển tiếp, resource server chỉ chấp nhận issuer cũ và mới khi có chủ đích, giới hạn thời gian và kiểm tra riêng cho từng issuer.

### 3.3 Duy trì tương thích token

Phân loại token đang dùng:

- **JWT access token:** kiểm tra thuật toán ký, kid, issuer, audience, subject, scope, thời hạn và claim tùy chỉnh.
- **Opaque access token:** cần kho trạng thái hoặc introspection endpoint để xác minh. Không thể chuyển một chuỗi opaque cũ sang kho authorization mới chỉ bằng cách sao chép giá trị.
- **Refresh token:** thường gắn với authorization record và chính sách rotation. Dữ liệu refresh token cũ không mặc nhiên dùng được trong authorization service mới.
- **Authorization code:** là thông tin ngắn hạn, dùng một lần và gắn với redirect URI/PKCE. Không nên di trú code đang chờ xử lý như dữ liệu lâu dài.

Với JWT, resource server cần tiếp tục xác minh được token cũ cho đến khi chúng hết hạn hoặc bị thu hồi theo chính sách. Nếu thay khóa ký, có thể công bố đồng thời public key cũ và mới trong JWKS trong thời gian chuyển tiếp. Giữ kid ổn định cho khóa cũ và không tái sử dụng kid cho khóa khác. Chỉ loại public key cũ sau khi không còn token hợp lệ được ký bằng khóa đó.

Với opaque token, có thể tiếp tục dùng authorization server cũ để introspect token cũ trong giai đoạn chuyển tiếp, trong khi token mới được xác minh qua server mới. Resource server cần định tuyến theo nguồn token hoặc theo cấu hình endpoint đã thống nhất. Không gửi mọi token tới một introspection endpoint nếu endpoint đó không hiểu kho token tương ứng.

## 4. Di trú client registration

RegisteredClient mô tả client theo cấu trúc mới. Khi tạo bản ghi, cần chuyển đầy đủ:

- Client ID và secret đã được chuyển sang định dạng password encoder tương thích.
- Client authentication method.
- Authorization grant type.
- Redirect URI và post-logout redirect URI nếu dùng OIDC logout.
- Scope.
- Client settings, bao gồm yêu cầu PKCE và consent.
- Token settings, bao gồm access token TTL, refresh token TTL, định dạng access token và chính sách reuse refresh token.

Ví dụ dưới đây minh họa một service client dùng Client Credentials trong repository in-memory. Đây là ví dụ cấu hình để hiểu mô hình; hệ thống production nên nạp client từ kho lưu trữ được quản lý, không tạo secret ngẫu nhiên mới mỗi lần khởi động.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(PasswordEncoder passwordEncoder) {
    RegisteredClient billingClient = RegisteredClient.withId(
            UUID.randomUUID().toString())
        .clientId("billing-service")
        .clientSecret(passwordEncoder.encode("load-from-a-secret-manager"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoice.read")
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(10))
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(billingClient);
}
~~~

Khi chuyển client secret, xác nhận password encoder của hệ thống mới có thể kiểm tra đúng định dạng đã lưu. Nếu secret cũ được lưu plaintext, không sao chép plaintext vào database mới. Có thể yêu cầu client luân chuyển secret hoặc thực hiện một quy trình chuyển đổi được kiểm soát, có giới hạn truy cập và audit. Giá trị {noop} chỉ phù hợp với thử nghiệm cô lập, không dùng cho production.

Với public client, không tạo client secret giả. Cấu hình client authentication method phù hợp cho public client và bắt buộc PKCE theo chính sách. Kiểm tra redirect URI chính xác; không nới lỏng thành wildcard để tránh phải cập nhật client.

### 4.1 Ánh xạ grant type

| Grant ở hệ thống cũ | Hướng xử lý ở hệ thống mới |
|---|---|
| authorization_code | Đăng ký Authorization Code; yêu cầu PKCE, đặc biệt với public client |
| client_credentials | Đăng ký Client Credentials và giới hạn scope theo service |
| refresh_token | Bật Refresh Token cùng TTL và rotation policy phù hợp |
| password | Chuyển sang Authorization Code + PKCE hoặc mô hình đăng nhập phù hợp; không tái tạo password grant cho hệ thống mới |
| implicit | Chuyển sang Authorization Code + PKCE |
| Custom grant | Đánh giá lại nghiệp vụ và triển khai extension point tương ứng nếu thật sự cần |

Resource Owner Password Credentials (password grant) và implicit grant không thuộc các luồng nên tiếp tục dùng trong kiến trúc mới. Với ứng dụng người dùng, Authorization Code + PKCE là hướng thay thế thông thường. Với service-to-service, dùng Client Credentials hoặc cơ chế workload identity phù hợp.

Nếu hệ thống có custom grant, mô tả chính xác cách xác thực client, xác minh credential, kiểm tra scope, tạo principal và phát hành token. Spring Authorization Server cho phép mở rộng qua authentication converter, authentication provider và token generator. Không chuyển nguyên logic cũ mà chưa kiểm tra threat model và khả năng tương thích OAuth.

## 5. Di trú authorization, consent và token store

Đây thường là phần phức tạp nhất. Schema cũ và mới có thể lưu cùng một nghiệp vụ theo cách hoàn toàn khác nhau.

### 5.1 Phân biệt các loại dữ liệu

| Dữ liệu cũ | Cách xử lý khi chuyển đổi |
|---|---|
| Client registration | Chuyển thành RegisteredClient và xác minh lại cấu hình |
| Approval / consent | Ánh xạ principal, client và scope; kiểm tra ý nghĩa từng trạng thái |
| Authorization code | Thông thường để hết hạn ở hệ thống cũ; không chuyển code đang hoạt động nếu không có cơ chế tương thích đã kiểm chứng |
| Access token JWT | Duy trì xác minh bằng khóa và claim cũ cho đến khi hết hạn hoặc thu hồi |
| Opaque access token | Tiếp tục introspect từ kho cũ hoặc để hết hạn theo kế hoạch |
| Refresh token | Tiếp tục xử lý tại hệ thống phát hành hoặc yêu cầu xác thực/cấp quyền lại theo lộ trình |
| Revocation state | Bảo đảm resource server vẫn nhìn thấy trạng thái thu hồi trong giai đoạn chuyển tiếp |

Các bảng như oauth_client_details, oauth_access_token, oauth_refresh_token, oauth_code và oauth_approvals thường xuất hiện trong triển khai cũ, nhưng tên bảng và kiểu dữ liệu có thể đã được tùy biến. Spring Authorization Server có các JDBC repository/service riêng, ví dụ JdbcRegisteredClientRepository, JdbcOAuth2AuthorizationService và JdbcOAuth2AuthorizationConsentService, với schema của phiên bản tương ứng.

Không chạy script tạo schema mới lên database production trước khi sao lưu và xem xét xung đột tên bảng. Không ghi đè schema cũ. Tạo schema đích riêng, kiểm tra index, kiểu cột, transaction, quyền database và kế hoạch rollback.

### 5.2 Không sao chép trực tiếp serialized token

Một số TokenStore cũ lưu object đã serialize hoặc cấu trúc nội bộ riêng. OAuth2AuthorizationService của hệ thống mới lưu một mô hình authorization khác. Việc sao chép blob từ bảng cũ sang bảng mới không chuyển đổi được ý nghĩa của object và có thể làm hỏng trạng thái refresh, revoke hoặc scope.

Một chiến lược an toàn thường là:

1. Di trú client registration và các cấu hình cần thiết trước.
2. Khởi chạy authorization server mới với schema mới.
3. Ngừng tạo authorization mới trên server cũ tại thời điểm cutover đã định.
4. Để token cũ được xác minh/introspect bằng cơ chế cũ cho đến khi hết hạn, hoặc thu hồi theo kế hoạch.
5. Cấp token mới từ server mới.
6. Theo dõi số token cũ còn hoạt động; chỉ ngừng hẳn kho cũ khi hết thời hạn tương thích và nghĩa vụ thu hồi đã được xử lý.

Nếu nghiệp vụ yêu cầu giữ phiên đăng nhập hoặc refresh token qua thời điểm cutover, cần một thiết kế chuyển đổi dữ liệu riêng. Thiết kế đó phải xác minh được định dạng token, client binding, principal, scope, thời hạn, trạng thái revoke, rotation và khả năng chống replay. Không đánh dấu token cũ là hợp lệ trong kho mới chỉ vì chuỗi token còn tồn tại.

### 5.3 Xử lý consent

Consent cũ có thể chứa nhiều trạng thái như approved, denied, thời điểm phê duyệt và scope đã duyệt. Consent service mới thường biểu diễn sự đồng ý theo principal, client và authorities. Cần xác định rõ:

- Scope nào người dùng đã đồng ý.
- Scope nào đã bị từ chối hoặc chưa từng được hỏi.
- Consent có hết hạn hoặc bị thu hồi không.
- Principal cũ có còn cùng định danh với principal mới không.
- Có cần yêu cầu người dùng đồng ý lại khi scope hoặc mục đích xử lý thay đổi không.

Không chuyển mọi approval cũ thành consent hợp lệ mà không phân tích ý nghĩa. Một approval bị từ chối hoặc đã hết hiệu lực không được biến thành quyền được cấp.

## 6. Cấu hình authorization server mới

Cấu hình mới dùng một filter chain cho các endpoint của authorization server và một filter chain khác cho ứng dụng đăng nhập hoặc các endpoint còn lại. Ví dụ rút gọn sau minh họa cách tách matcher và bật OIDC; các repository, token generator, issuer và decoder cần được khai báo theo kiến trúc thực tế.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}
~~~

Đoạn code là khung cấu hình cho API của phiên bản Spring Authorization Server được chọn. Cần kiểm tra dependency management và tài liệu đúng phiên bản trước khi áp dụng; không ghép các phiên bản Spring Boot, Spring Security và Authorization Server tùy ý.

Trong triển khai hoàn chỉnh, khai báo repository và service phù hợp:

- RegisteredClientRepository để đọc client.
- OAuth2AuthorizationService để lưu authorization và token.
- OAuth2AuthorizationConsentService để lưu consent.
- OAuth2TokenGenerator và các bean ký JWT hoặc phát hành opaque token.
- AuthorizationServerSettings để cố định issuer và endpoint URI.
- JwtDecoder khi các tính năng OIDC hoặc thành phần khác cần giải mã JWT.

Đối với endpoint đăng nhập, filter chain thứ hai phải có cơ chế xác thực người dùng thật, session policy và CSRF phù hợp. Không cho phép endpoint authorization chạy trước một filter chain quá rộng khiến request bị xử lý sai.

### 6.1 Chuyển claim và token customization

Trong hệ thống cũ, claim có thể được thêm qua TokenEnhancer, AccessTokenConverter hoặc code tùy chỉnh trong DefaultTokenServices. Trong hệ thống mới, JWT access token có thể được tùy biến qua OAuth2TokenCustomizer với ngữ cảnh JwtEncodingContext. Hãy chuyển từng claim với nguồn dữ liệu và quy tắc rõ ràng.

Kiểm tra các claim thường được resource server sử dụng: iss, sub, aud, exp, iat, jti, scope hoặc scp, tenant, role và các claim nghiệp vụ. Không đưa dữ liệu nhạy cảm hoặc thông tin cá nhân không cần thiết vào access token. Nếu thay tên claim, phải cập nhật resource server và policy cùng lúc.

Đối với opaque token, claim không được đọc trực tiếp từ JWT; resource server lấy thông tin qua introspection hoặc cơ chế xác minh tương ứng. Không áp dụng logic JWT customizer cho opaque token rồi giả định kết quả giống nhau.

### 6.2 Khóa ký và JWKS

Thiết lập nguồn khóa có quản lý vòng đời. Trong production, private key nên được bảo vệ bằng secret manager, KMS hoặc HSM theo yêu cầu hệ thống. Public key được công bố qua JWKS; private key không bao giờ được đưa vào response JWKS hoặc log.

Khi di trú:

- Ghi nhận thuật toán ký và kid đang được resource server tin cậy.
- Xác nhận server mới phát hành JWT có thuật toán và claim tương thích.
- Nếu đổi khóa, công bố public key cũ và mới trong giai đoạn chồng lấp.
- Kiểm thử cache JWKS và thời gian cập nhật khóa ở resource server.
- Chỉ gỡ khóa cũ khi mọi token được ký bằng khóa đó đã hết hạn hoặc bị thu hồi và không còn yêu cầu xác minh.

Không dùng khóa HMAC yếu hoặc chia sẻ secret ký token với client. Chọn thuật toán bất đối xứng và chính sách xoay khóa phù hợp với môi trường.

## 7. Di trú resource server và OAuth2 client

### 7.1 Resource server

Nếu resource server cũ dùng @EnableResourceServer hoặc ResourceServerConfigurerAdapter, chuyển sang Spring Security SecurityFilterChain và cấu hình oauth2ResourceServer.

Với JWT, khai báo JwtDecoder hoặc issuer/JWK Set URI theo cơ chế discovery phù hợp. Xác minh issuer, audience, thời hạn, thuật toán ký và claim cần thiết. Với opaque token, cấu hình introspection endpoint và thông tin xác thực client có quyền introspect.

Các scope thường được ánh xạ thành authority có tiền tố SCOPE_. Nếu hệ thống cũ dùng ROLE_, claim role riêng hoặc converter tùy chỉnh, chuyển mapping đó một cách tường minh. Không hạ yêu cầu phân quyền chỉ để làm cho token mới vượt qua kiểm thử.

Trong giai đoạn chuyển tiếp, resource server có thể cần xác minh token cũ và mới. Tách validator theo issuer, key set hoặc nguồn introspection; ghi nhận nguồn xác minh để có thể ngừng đường tương thích cũ đúng thời điểm.

### 7.2 OAuth2 client

Các ứng dụng dùng OAuth2RestTemplate của Spring Security OAuth cũ cần chuyển sang OAuth2 Client hiện đại. Spring Security cung cấp ClientRegistration, OAuth2AuthorizedClientService và OAuth2AuthorizedClientManager để quản lý đăng ký client và token được cấp.

Khi chuyển đổi, kiểm tra:

- Client registration và authentication method.
- Authorization Code + PKCE cho ứng dụng người dùng.
- Client Credentials cho service-to-service.
- Cách lưu authorized client và refresh token.
- Cách xử lý token hết hạn, refresh thất bại và logout.
- Cấu hình redirect URI và callback sau đăng nhập.

Không lưu access token hoặc refresh token vào log, URL, browser local storage hoặc kho dữ liệu không được bảo vệ. Với ứng dụng web, ưu tiên mô hình server-side/BFF khi phù hợp để giảm việc phơi bày token cho trình duyệt.

## 8. Lộ trình cutover có kiểm soát

Một đợt di trú nên được chia thành các giai đoạn có tiêu chí hoàn thành rõ ràng.

### Giai đoạn 1: Chuẩn bị

1. Hoàn thành kiểm kê client, grant, scope, endpoint, token và customization.
2. Chốt ma trận phiên bản Spring Boot, Spring Security và Spring Authorization Server tương thích.
3. Sao lưu database, cấu hình khóa và dữ liệu consent.
4. Dựng môi trường staging có dữ liệu đã ẩn danh.
5. Chốt issuer, public endpoint, signing key, token TTL và chính sách tương thích.

### Giai đoạn 2: Xây dựng server mới

1. Tạo filter chain riêng cho authorization server.
2. Cấu hình client repository, authorization service và consent service.
3. Chuyển client registration và kiểm tra secret.
4. Cấu hình Authorization Code + PKCE, Client Credentials và Refresh Token theo nhu cầu.
5. Cấu hình JWT hoặc opaque token, issuer và JWKS.
6. Chuyển claim, consent page, login flow và custom grant đã được duyệt.
7. Kiểm thử các endpoint và lỗi OAuth ở staging.

### Giai đoạn 3: Chuyển resource server và client

1. Cập nhật resource server để xác minh token mới.
2. Nếu cần, bổ sung xác minh token cũ có thời hạn.
3. Cập nhật client theo từng nhóm, bắt đầu từ client thử nghiệm.
4. Kiểm tra redirect URI, PKCE, scope, refresh và logout.
5. Xác nhận audit và monitoring nhận diện được nguồn token.

### Giai đoạn 4: Cutover

1. Chọn thời điểm ít tải và thông báo cho chủ sở hữu client.
2. Dừng hoặc giới hạn việc tạo authorization mới trên server cũ theo kế hoạch.
3. Định tuyến client đã chọn tới endpoint mới.
4. Theo dõi lỗi xác thực, token issuance, introspection, latency và tỷ lệ 401/403.
5. Giữ đường xác minh token cũ cho tới khi hết hạn hoặc được thu hồi.
6. Chuyển tiếp các nhóm client còn lại sau khi nhóm trước đạt tiêu chí ổn định.

Tránh để hai authorization server cùng phát hành token cho cùng một luồng client mà không có định tuyến và quy tắc trạng thái rõ ràng. Đặc biệt, không để refresh token được phát hành bởi server A nhưng gửi ngẫu nhiên tới server B. Trong giai đoạn chạy song song, cần biết chính xác server nào sở hữu authorization và refresh token của từng client.

### Giai đoạn 5: Kết thúc

Khi token cũ đã hết hạn hoặc được xử lý theo chính sách, tắt endpoint cũ, thu hồi credential không còn dùng, lưu trữ audit cần thiết và xóa dữ liệu cũ theo quy trình retention. Cập nhật tài liệu vận hành, dashboard, alert và quy trình khôi phục.

## 9. Kiểm thử hồi quy và bảo mật

Dùng cùng một bộ request/response mẫu đã thu thập ở giai đoạn kiểm kê. Kiểm tra cả kết quả giao thức và tác động đến API được bảo vệ.

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Client auth | Basic, post, public client theo cấu hình | Chỉ authentication method được đăng ký mới được chấp nhận |
| Authorization Code | Redirect URI hợp lệ và không hợp lệ | Chỉ URI đã đăng ký chính xác được chấp nhận |
| PKCE | S256 đúng, verifier sai hoặc thiếu | Chỉ giao dịch có proof hợp lệ được đổi code |
| Client Credentials | Client hợp lệ, secret sai, scope ngoài quyền | Token chỉ được cấp cho client và scope được phép |
| Refresh Token | Còn hạn, hết hạn, bị revoke, dùng lại sau rotation | Hành vi đúng TTL và chính sách rotation |
| Consent | Chưa đồng ý, đã đồng ý, thu hồi, scope thay đổi | Không cấp quyền vượt quá consent |
| JWT | Chữ ký, issuer, audience, exp, kid và claim | Resource server chỉ chấp nhận token hợp lệ |
| Opaque token | Introspection hợp lệ, không hợp lệ, dependency lỗi | Không coi lỗi introspection là token hợp lệ |
| Revocation | Thu hồi access/refresh token theo khả năng triển khai | Trạng thái thu hồi được phản ánh đúng |
| OIDC | Discovery, JWKS, UserInfo, nonce và logout | Metadata và claim khớp cấu hình |
| Tương thích | Token cũ trong thời gian chồng lấp | Chỉ token còn hiệu lực và đúng chính sách được chấp nhận |
| Vận hành | Database, Redis, KMS hoặc JWKS gián đoạn | Hệ thống lỗi có kiểm soát và phục hồi đúng thiết kế |

Ngoài kiểm thử chức năng, thực hiện kiểm thử tải ở token endpoint, kiểm thử rate limit, fault injection cho database/Redis/KMS và kiểm thử xoay khóa. Xác minh log không chứa client secret, access token, refresh token, authorization code hoặc private key.

## 10. Rollback và các lỗi di trú thường gặp

Rollback cần được thiết kế trước cutover. Nếu server mới đã phát hành refresh token hoặc authorization record mà server cũ không hiểu, chuyển toàn bộ traffic ngược về server cũ có thể làm người dùng mất phiên hoặc tạo lỗi refresh. Vì vậy, rollback phải tính đến token đã phát hành sau cutover, không chỉ việc đổi DNS.

Một phương án có thể là giữ server mới tiếp tục xử lý token do chính nó phát hành trong thời gian khôi phục, hoặc chuyển client sang luồng xác thực lại có kiểm soát. Quyết định phụ thuộc khả năng chạy song song và yêu cầu sẵn sàng của hệ thống.

Các lỗi thường gặp cần tránh:

- Chỉ thay dependency nhưng giữ nguyên cấu hình cũ.
- Chuyển client mà bỏ sót authentication method, PKCE hoặc redirect URI.
- Sao chép trực tiếp blob token đã serialize vào schema mới.
- Đổi issuer hoặc signing key mà không cập nhật resource server.
- Chuyển mọi approval cũ thành consent hợp lệ.
- Tiếp tục password grant hoặc implicit grant trong thiết kế mới.
- Để nhiều server xử lý cùng refresh token mà không có cơ chế định tuyến.
- Thay đổi scope hoặc claim khiến API phân quyền khác trước.
- Xóa public key cũ trước khi token ký bằng khóa đó hết hạn.
- Coi việc token endpoint trả 200 là bằng chứng toàn bộ luồng API đã hoạt động.

Trước khi cutover, ghi lại điều kiện dừng: tỷ lệ lỗi vượt ngưỡng, client không lấy được token, resource server từ chối token hợp lệ, introspection không sẵn sàng, hoặc audit bị thiếu. Mỗi điều kiện cần có người chịu trách nhiệm và hành động khôi phục cụ thể.

## 11. Tiêu chí hoàn thành

Di trú được xem là hoàn thành về mặt kỹ thuật khi:

- Tất cả client đang hoạt động đã được kiểm kê và có mapping sang cấu hình mới.
- Grant type không còn được hỗ trợ đã có phương án thay thế được xác nhận.
- Client registration, secret, scope, redirect URI và consent được chuyển đúng chính sách.
- Authorization server mới phát hành token và xử lý lỗi theo cấu hình đã duyệt.
- Resource server xác minh đúng issuer, audience, chữ ký, scope và claim.
- Token cũ được xác minh, introspect hoặc để hết hạn theo kế hoạch chuyển tiếp.
- Refresh token và authorization record không bị gửi nhầm giữa hai server.
- JWKS và quy trình xoay khóa hoạt động trong giai đoạn chồng lấp.
- Bộ kiểm thử hồi quy, bảo mật, tải và fault injection đạt tiêu chí.
- Rollback, monitoring, audit và tài liệu vận hành đã được cập nhật.
- Endpoint cũ và dữ liệu cũ chỉ được ngừng khi không còn token hoặc client phụ thuộc.

Việc chuyển từ Spring Security OAuth cũ sang Spring Authorization Server là thay đổi kiến trúc của hệ thống cấp quyền. Khi tách rõ client registration, authorization state, token validation và trách nhiệm của từng ứng dụng, nhóm có thể chuyển đổi theo từng giai đoạn, giữ được khả năng tương thích cần thiết và kiểm soát rủi ro trong thời gian cutover.

