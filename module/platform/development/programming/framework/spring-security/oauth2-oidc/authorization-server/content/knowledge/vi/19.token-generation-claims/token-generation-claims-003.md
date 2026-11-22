# OAuth2TokenContext, JwtEncodingContext và OAuth2TokenClaimsContext

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, token không chỉ là một chuỗi ngẫu nhiên hoặc một JWT được ký. Mỗi token được tạo trong một ngữ cảnh cụ thể: client nào đang yêu cầu, principal nào liên quan, grant type nào đang được xử lý, scope nào đã được chấp thuận, token type nào đang được sinh và Authorization Server nào phát hành.

Spring Authorization Server truyền những thông tin đó qua hệ thống **token context**. Ba kiểu cần hiểu rõ là:

- <code>OAuth2TokenContext</code>: ngữ cảnh chung mà token generator dùng để quyết định token cần sinh và các dữ liệu liên quan.
- <code>JwtEncodingContext</code>: ngữ cảnh chuyên biệt cho quá trình tạo JWT, có builder cho JWS header và JWT claims trước khi ký.
- <code>OAuth2TokenClaimsContext</code>: ngữ cảnh chuyên biệt cho claims của access token dạng reference/opaque, được tạo bởi <code>OAuth2AccessTokenGenerator</code>.

Ví dụ xuyên suốt: Alice đăng nhập vào <code>orders-web</code>, chấp thuận scope <code>orders.read</code> và <code>orders.write</code>. Authorization Server cấp access token cho Orders API. API cần biết issuer, audience, thời hạn và scope. Nếu access token là JWT, Resource Server có thể xác minh chữ ký và claims mà không cần gọi Authorization Server mỗi request. Nếu access token là reference token, Resource Server thường gọi introspection để biết trạng thái và claims do Authorization Server lưu giữ.

Sau bài học, bạn có thể:

1. Mô tả những dữ liệu có trong <code>OAuth2TokenContext</code> và lý do token generator cần chúng.
2. Phân biệt ngữ cảnh tạo JWT với ngữ cảnh tạo claims cho reference access token.
3. Viết <code>OAuth2TokenCustomizer</code> đúng generic type và chỉ tùy chỉnh đúng token type.
4. Thêm claims có nguồn tin cậy, không lấy dữ liệu nhạy cảm hoặc quyền từ request chưa xác thực.
5. Hiểu mối liên hệ giữa <code>JwtGenerator</code>, <code>OAuth2AccessTokenGenerator</code>, <code>OAuth2RefreshTokenGenerator</code> và <code>DelegatingOAuth2TokenGenerator</code>.
6. Giữ nguyên các kiểm tra mặc định về issuer, subject, audience, thời hạn, scope và token format khi thêm custom claims.
7. Kiểm thử claims trên JWT, reference token/introspection và các grant khác nhau.

**Phạm vi phiên bản:** Ví dụ Java theo API Spring Authorization Server 1.5.x và Spring Security 6.x, sử dụng Servlet stack. Các bản Spring Security mới đã tích hợp Authorization Server có thể thay đổi package hoặc cách cấu hình; cần đối chiếu version dự án. Những class nghiệp vụ như <code>TenantMembershipService</code> trong bài là abstraction do ứng dụng tự triển khai.

## 2. Token generation pipeline

### 2.1. Từ authorization grant tới token

Token Endpoint hoặc một endpoint giao thức khác xác minh yêu cầu grant trước. Khi grant hợp lệ, provider xây dựng ngữ cảnh token và gọi <code>OAuth2TokenGenerator</code>. Generator phù hợp tạo token; provider sau đó lưu authorization/token metadata và trả kết quả cho endpoint.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant E as Authorization Endpoint / Token Endpoint
    participant P as AuthenticationProvider
    participant CTX as OAuth2TokenContext
    participant G as OAuth2TokenGenerator
    participant J as JwtGenerator
    participant O as OAuth2AccessTokenGenerator
    participant S as OAuth2AuthorizationService
    C->>E: Authorization request hoặc token request
    E->>P: Grant authentication đã được parse
    P->>P: Xác minh client, grant, consent, scope và policy
    P->>CTX: Xây token context cho token type cần tạo
    P->>G: generate(context)
    G->>J: Thử tạo JWT nếu format/token type phù hợp
    J-->>G: Jwt hoặc null
    G->>O: Thử tạo reference access token nếu phù hợp
    O-->>G: OAuth2AccessToken hoặc null
    G-->>P: Token do generator phù hợp tạo
    P->>S: Lưu authorization và token metadata
    P-->>E: Authentication thành công
    E-->>C: Token response theo OAuth/OIDC
~~~

Sơ đồ minh họa vai trò của generator; thứ tự cụ thể của các generator trong <code>DelegatingOAuth2TokenGenerator</code> phụ thuộc cách ứng dụng cấu hình. Generator không thay thế việc xác minh grant. Một token context được xây dựng **sau khi** provider đã xác định client, principal và quyền có thể cấp.

### 2.2. Bốn giai đoạn cần phân biệt

| Giai đoạn | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Nhận request | Filter + <code>AuthenticationConverter</code> | Đọc tham số giao thức, tạo grant authentication request. |
| Xác minh grant | <code>AuthenticationProvider</code> | Xác thực client, authorization, code/refresh token, consent, scope và policy. |
| Tạo token | <code>OAuth2TokenContext</code> + <code>OAuth2TokenGenerator</code> + customizer | Xây dữ liệu token theo ngữ cảnh, ký JWT hoặc tạo reference token. |
| Lưu và phản hồi | <code>OAuth2AuthorizationService</code> + endpoint filter | Lưu trạng thái cần thiết và xuất token response. |

Không dùng <code>OAuth2TokenCustomizer</code> như một nơi thay thế authorization policy. Customizer có thể thêm claim vào token, nhưng nếu grant chưa được xác minh hoặc scope đã sai thì việc thêm một claim đẹp không làm yêu cầu trở nên hợp lệ.

## 3. OAuth2TokenContext: ngữ cảnh chung của token

### 3.1. Các thông tin cốt lõi

<code>OAuth2TokenContext</code> là interface mô tả ngữ cảnh mà <code>OAuth2TokenGenerator</code> nhận được. Những accessor quan trọng gồm:

| Accessor | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| <code>getRegisteredClient()</code> | Client đã được xác thực/đăng ký cho grant hiện tại. | <code>orders-web</code>. |
| <code>getPrincipal()</code> | Principal gắn với quá trình cấp token. | Alice trong Authorization Code; client principal trong Client Credentials. |
| <code>getAuthorizationServerContext()</code> | Context của Authorization Server, gồm issuer và thông tin cấu hình liên quan. | <code>https://auth.example.com</code>. |
| <code>getAuthorization()</code> | Authorization đang được tạo/cập nhật, nếu có trong ngữ cảnh. | Bản ghi chứa authorization code hoặc refresh token. |
| <code>getAuthorizedScopes()</code> | Tập scope đã được chấp thuận/cho phép cho token hiện tại. | <code>orders.read</code>. |
| <code>getTokenType()</code> | Loại token đang được sinh. | <code>OAuth2TokenType.ACCESS_TOKEN</code>. |
| <code>getAuthorizationGrantType()</code> | Grant type đang được xử lý. | <code>authorization_code</code>. |
| <code>getAuthorizationGrant()</code> | Authentication object đại diện grant request. | Authorization Code authentication hoặc Refresh Token authentication. |

Các accessor này giúp customizer hiểu token đang thuộc **client nào, principal nào, grant nào, scope nào và token type nào**. Không phải mọi field đều có giá trị trong mọi luồng. Ví dụ, một số bước tạo token ban đầu chưa có <code>OAuth2Authorization</code> hoàn chỉnh; customizer phải xử lý trường hợp optional/null theo API thực tế thay vì mặc định authorization luôn tồn tại.

### 3.2. Ví dụ xây DefaultOAuth2TokenContext

Trong provider, một token context có thể được xây như sau:

~~~java
OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext.builder()
    .registeredClient(registeredClient)
    .principal(principal)
    .authorizationServerContext(
        AuthorizationServerContextHolder.getContext())
    .authorizedScopes(authorizedScopes)
    .tokenType(OAuth2TokenType.ACCESS_TOKEN)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrant(authorizationGrantAuthentication)
    .build();

OAuth2Token generated = tokenGenerator.generate(tokenContext);
~~~

Đây là ví dụ cấu trúc, thường provider chuẩn đã thực hiện việc này. <code>registeredClient</code>, <code>principal</code>, <code>authorizedScopes</code> và <code>authorizationGrantAuthentication</code> phải được lấy từ kết quả xác minh grant. Không tự lấy các giá trị tương ứng từ form body rồi đưa vào context.

Với refresh token, provider còn có thể đưa authorization hiện có vào context để token generator/customizer có ngữ cảnh của grant đã lưu. Hãy dùng provider mặc định hoặc mở rộng đúng hook; đừng tự viết một token endpoint khác chỉ để tạo context.

### 3.3. Client principal không phải lúc nào cũng là End-User

Giá trị <code>getPrincipal()</code> phụ thuộc grant:

| Grant | Principal thường gặp | Ý nghĩa |
| --- | --- | --- |
| Authorization Code | Người dùng đã xác thực | Token đại diện quyền đã được End-User cấp cho client. |
| Client Credentials | Client đã xác thực | Token đại diện ứng dụng/service; không có End-User mặc định. |
| Refresh Token | Principal gắn với authorization gốc | Token mới tiếp tục ngữ cảnh authorization đã lưu. |
| Device Authorization | Người dùng đã xác minh thiết bị sau khi hoàn tất flow | Phụ thuộc trạng thái device authorization. |
| Token Exchange | Subject/actor theo grant exchange | Cần giữ đúng semantics của subject token và actor token. |

Vì vậy, đoạn customizer lấy <code>context.getPrincipal().getAuthorities()</code> rồi coi tất cả là role người dùng có thể sai khi grant là Client Credentials. Cần phân nhánh theo grant type và kiểu principal, hoặc đọc entitlement từ nguồn tin cậy đã được ràng buộc với client/principal.

### 3.4. Scope đã được cấp khác scope client có thể xin

<code>RegisteredClient.getScopes()</code> là danh sách scope client được đăng ký có thể yêu cầu. <code>OAuth2TokenContext.getAuthorizedScopes()</code> biểu diễn phạm vi đã được chấp thuận/cho phép trong **authorization hiện tại**. Khi tạo access token, customizer nên dựa vào <code>authorizedScopes</code>, không sao chép toàn bộ scope đăng ký vào claim.

Ví dụ client được đăng ký <code>orders.read</code>, <code>orders.write</code>, <code>orders.admin</code>, nhưng Alice chỉ chấp thuận <code>orders.read</code>. Token không được có claim scope chứa cả ba quyền. Customizer không phải nơi tự mở rộng quyền; mọi thay đổi phạm vi phải được xử lý ở authorization/grant policy trước khi token generation.

## 4. JwtEncodingContext: ngữ cảnh tạo JWT

### 4.1. Builder cho JWS header và JWT claims

<code>JwtEncodingContext</code> mở rộng <code>OAuth2TokenContext</code> và bổ sung hai builder quan trọng:

- <code>getJwsHeader()</code>: builder của JOSE/JWS header, ví dụ thuật toán và metadata khóa ký.
- <code>getClaims()</code>: builder của <code>JwtClaimsSet</code>, dùng để thêm hoặc điều chỉnh claims trước khi JWT được encode/ký.

<code>JwtGenerator</code> xây JWT từ context này và dùng <code>JwtEncoder</code> để ký. Sau khi chữ ký được tạo, việc chỉnh claim trong token không còn là một thao tác an toàn: thay đổi payload sẽ làm chữ ký không hợp lệ. Vì vậy customizer chạy **trước** bước encode.

~~~mermaid
flowchart TD
    A["JwtGenerator nhận OAuth2TokenContext"] --> B["Tạo JwtEncodingContext"]
    B --> C["Thiết lập JWS header mặc định"]
    C --> D["Thiết lập JWT claims mặc định"]
    D --> E["OAuth2TokenCustomizer<JwtEncodingContext>"]
    E --> F["JwtEncoder"]
    F --> G["JWS compact: header.payload.signature"]
    G --> H["Jwt được lưu trong OAuth2Authorization"]
~~~

Sơ đồ tập trung vào JWT generation. Chi tiết claim mặc định và header phụ thuộc token type, OIDC và cấu hình JWK/encoder. Đừng giả định mọi loại JWT đều có cùng claims.

### 4.2. Ví dụ thêm claim cho access token JWT

Giả sử ứng dụng có <code>TenantMembershipService</code> truy xuất tenant hiện hành đã được xác minh cho principal và client:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        TenantMembershipService tenantMemberships) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        // Chỉ dùng scope đã được chấp thuận cho authorization hiện tại.
        context.getClaims().claim(
            "scope", context.getAuthorizedScopes());

        String tenantId = tenantMemberships.findAuthorizedTenant(
            context.getRegisteredClient(),
            context.getPrincipal(),
            context.getAuthorization());

        if (tenantId != null) {
            context.getClaims().claim(
                "https://claims.example.com/tenant_id", tenantId);
        }
    };
}
~~~

<code>TenantMembershipService</code> là service minh họa do ứng dụng xây dựng; phương thức <code>findAuthorizedTenant(...)</code> phải kiểm tra quan hệ tenant với principal và client từ dữ liệu tin cậy. Không lấy tenant ID trực tiếp từ header <code>X-Tenant</code> hoặc request parameter chưa được xác minh.

Đoạn code chỉ xử lý JWT access token. Nếu ứng dụng đã có scope claim mặc định, hãy kiểm tra token được tạo thực tế trước khi tự ghi lại claim <code>scope</code>; không cần ghi đè claim mặc định chỉ để tạo cùng giá trị. Mục tiêu của ví dụ là minh họa cách context cung cấp scope đã được chấp thuận và cách thêm một claim tùy biến có namespace.

### 4.3. Thêm role có chọn lọc

Một customizer có thể đưa role vào JWT access token khi token đại diện cho người dùng:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> userRoleCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        if (!AuthorizationGrantType.AUTHORIZATION_CODE.equals(
                context.getAuthorizationGrantType())) {
            return; // Không coi Client Credentials là user login.
        }

        Authentication principal = context.getPrincipal();
        Set<String> roles = principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .filter(authority -> authority.startsWith("ROLE_"))
            .map(authority -> authority.substring("ROLE_".length()))
            .collect(Collectors.toUnmodifiableSet());

        context.getClaims().claim("roles", roles);
    };
}
~~~

Đây là ví dụ minh họa. Ứng dụng thực cần bảo đảm authorities của principal được nạp từ nguồn tin cậy và đã được cập nhật theo policy. Không đưa mọi authority như <code>SCOPE_orders.read</code>, <code>ROLE_...</code>, quyền nội bộ quản trị hoặc thông tin kỹ thuật vào một claim <code>roles</code> không phân biệt. Resource Server phải có quy tắc rõ ràng về cách ánh xạ claim sang GrantedAuthority.

**Lưu ý về nhiều customizer:** Không nên khai báo nhiều bean cùng generic type rồi giả định framework sẽ luôn tự kết hợp theo thứ tự mong muốn. Nếu cần nhiều chính sách JWT, kết hợp chúng trong một <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> có thứ tự rõ ràng hoặc cấu hình trực tiếp vào <code>JwtGenerator</code>.

### 4.4. JWS header và key selection

JWS header chứa thông tin phục vụ xác minh chữ ký, chẳng hạn <code>alg</code>, <code>kid</code> và <code>typ</code> theo profile. <code>JwtEncodingContext.getJwsHeader()</code> cho phép tùy chỉnh header trước khi ký. Tuy nhiên:

- Thuật toán phải phù hợp với key và chính sách server; không cho client chọn tùy ý <code>alg</code>.
- <code>kid</code> phải xác định đúng khóa ký đang dùng trong JWK Set; không đặt một giá trị không tồn tại trong kho khóa.
- Không công bố private key hoặc secret trong header/claim.
- Chỉ đặt <code>typ</code> khi tuân thủ profile token và Resource Server tương ứng; ví dụ JWT access token theo RFC 9068 có quy tắc type riêng.
- Rotation key cần công bố public key phù hợp và duy trì giai đoạn tương thích để Resource Server xác minh token còn hiệu lực.

Thông thường nên để <code>JwtGenerator</code>, <code>JwtEncoder</code> và JWK source chọn thuật toán/khóa theo cấu hình. Chỉ can thiệp header khi có một yêu cầu profile rõ ràng và integration test chứng minh Resource Server xử lý đúng.

## 5. OAuth2TokenClaimsContext: claims cho reference access token

### 5.1. Vì sao cần context riêng?

Không phải access token nào cũng là JWT. Spring Authorization Server hỗ trợ định dạng:

| Token format | Đặc điểm |
| --- | --- |
| <code>SELF_CONTAINED</code> | Access token JWT chứa claims và chữ ký; Resource Server có thể xác minh cục bộ bằng issuer/JWK. |
| <code>REFERENCE</code> | Access token là chuỗi tham chiếu khó đoán; thông tin authorization/claims nằm phía server và Resource Server thường gọi introspection. |

Với access token dạng reference, <code>OAuth2AccessTokenGenerator</code> tạo token value và xây claims context cho claims liên quan đến access token. <code>OAuth2TokenClaimsContext</code> cũng mở rộng <code>OAuth2TokenContext</code>, nhưng cung cấp builder <code>getClaims()</code> kiểu <code>OAuth2TokenClaimsSet.Builder</code>, không phải <code>JwtClaimsSet.Builder</code> và không có JWS header.

Claims được dùng trong metadata/token authorization phía server và có thể xuất hiện trong kết quả introspection theo cấu hình. Không có JWT để Resource Server decode trực tiếp. **Đừng cố dùng <code>JwtEncodingContext</code> để tùy chỉnh reference token**, vì generator không đi qua bước JWT encoding.

### 5.2. Ví dụ custom claim cho reference access token

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> referenceTokenCustomizer(
        TenantMembershipService tenantMemberships) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        String tenantId = tenantMemberships.findAuthorizedTenant(
            context.getRegisteredClient(),
            context.getPrincipal(),
            context.getAuthorization());

        if (tenantId != null) {
            context.getClaims().claim(
                "https://claims.example.com/tenant_id", tenantId);
        }

        context.getClaims().claim(
            "authorization_grant",
            context.getAuthorizationGrantType().getValue());
    };
}
~~~

<code>OAuth2TokenClaimsContext</code> dùng để tùy chỉnh claims cho reference access token do <code>OAuth2AccessTokenGenerator</code> tạo. Ví dụ cần được cấu hình đúng với token format <code>REFERENCE</code>; nếu client đang dùng <code>SELF_CONTAINED</code>, customizer này không thay thế JWT customizer.

Khi Resource Server dùng opaque token introspection, kiểm tra response thực tế có claim tùy biến theo contract hay không. Chỉ thêm claim trong server-side metadata mà không cấu hình/introspection endpoint hoặc không cho Resource Server sử dụng nó thì chưa tạo ra quyền nghiệp vụ.

### 5.3. Đừng nhầm opaque access token với refresh token

<code>OAuth2TokenClaimsContext</code> không phải một cách tùy chỉnh refresh token. Refresh token là credential dùng để xin access token mới; reference access token là token truy cập tài nguyên có giá trị tham chiếu. Hai loại token có vòng đời, mục đích và chính sách lưu trữ khác nhau.

## 6. Chọn đúng generator và customizer

### 6.1. Generator thường gặp

| Generator | Vai trò |
| --- | --- |
| <code>JwtGenerator</code> | Sinh JWT, bao gồm JWT access token self-contained và ID Token trong luồng OIDC tương ứng. |
| <code>OAuth2AccessTokenGenerator</code> | Sinh reference/opaque access token và claims metadata tương ứng. |
| <code>OAuth2RefreshTokenGenerator</code> | Sinh refresh token theo client/token settings và điều kiện grant. |
| <code>DelegatingOAuth2TokenGenerator</code> | Thử các generator theo thứ tự, trả token từ generator phù hợp. |

Mỗi generator có phạm vi hỗ trợ riêng. Việc thêm customizer không khiến mọi generator xử lý mọi token type.

### 6.2. Cấu hình format trên RegisteredClient

Ví dụ chọn JWT access token:

~~~java
RegisteredClient ordersClient = RegisteredClient.withId("orders-record-001")
    .clientId("orders-web")
    // Các client authentication method, grant và redirect URI được lược bỏ.
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .scope("orders.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .build())
    .build();
~~~

Ví dụ chọn reference access token:

~~~java
TokenSettings referenceSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .build();
~~~

Các thời hạn là giá trị minh họa. <code>accessTokenFormat</code> ảnh hưởng generator phù hợp và cách Resource Server xác minh. Không đổi format ở Authorization Server mà quên cập nhật Resource Server: JWT decoder không thể xác minh chuỗi opaque như JWT; opaque token introspection cũng không thay thế việc kiểm tra audience/claims ở API.

### 6.3. Đăng ký customizer với generator

Trong cấu hình Spring Authorization Server mặc định, các bean <code>OAuth2TokenCustomizer</code> có generic type phù hợp có thể được kết nối vào generator tương ứng theo cơ chế cấu hình của version đang dùng. Nếu ứng dụng **tự tạo <code>OAuth2TokenGenerator</code>**, phải gắn customizer vào đúng generator một cách tường minh.

Ví dụ minh họa khi tự lắp generator:

~~~java
@Bean
OAuth2TokenGenerator<?> tokenGenerator(
        JwtEncoder jwtEncoder,
        OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
        OAuth2TokenCustomizer<OAuth2TokenClaimsContext> claimsCustomizer) {

    JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
    jwtGenerator.setJwtCustomizer(jwtCustomizer);

    OAuth2AccessTokenGenerator accessTokenGenerator =
        new OAuth2AccessTokenGenerator();
    accessTokenGenerator.setAccessTokenCustomizer(claimsCustomizer);

    OAuth2RefreshTokenGenerator refreshTokenGenerator =
        new OAuth2RefreshTokenGenerator();

    return new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        accessTokenGenerator,
        refreshTokenGenerator);
}
~~~

Đây là cấu hình thay thế cách framework tự tạo token generator mặc định; không vừa khai báo một generator tùy chỉnh vừa kỳ vọng generator mặc định tự động được ghép thêm. Nếu dự án không cần tự lắp generator, ưu tiên đăng ký customizer bean theo tài liệu version đang dùng. Khi tự lắp, phải giữ đủ generator cho các token type cần hỗ trợ, thứ tự phù hợp và các bean <code>JwtEncoder</code>/<code>JWKSource</code> đúng.

**Lưu ý về generic injection:** Nếu ứng dụng có nhiều customizer cùng generic type, constructor injection có thể trở nên mơ hồ hoặc Spring không tự chọn theo ý muốn. Kết hợp logic vào một bean có thứ tự rõ ràng hoặc inject đúng bean bằng qualifier. Không tạo vòng phụ thuộc giữa token generator và customizer.

## 7. Phân biệt claims của Access Token và ID Token

### 7.1. Access token dành cho Resource Server

Access token biểu diễn quyền truy cập tài nguyên. Những claim thường quan trọng gồm:

| Claim | Mục đích |
| --- | --- |
| <code>iss</code> | Issuer Authorization Server phát hành token. |
| <code>sub</code> | Subject mà token đại diện theo grant. |
| <code>aud</code> | Resource Server/API đích được phép nhận token. |
| <code>exp</code> | Thời điểm hết hạn. |
| <code>iat</code> | Thời điểm phát hành. |
| <code>jti</code> | ID của token, hữu ích cho audit/denylist theo thiết kế. |
| <code>scope</code> hoặc claim tương đương | Các quyền OAuth đã được cấp. |
| <code>client_id</code> | Client mà token được cấp cho. |

Danh sách claim chính xác phụ thuộc profile, grant và cấu hình generator. Hãy decode một token test hoặc xem introspection response của đúng version để xác nhận. Không giả định mọi claim trên đều tự xuất hiện trong mọi token hoặc mọi Resource Server dùng cùng tên claim.

### 7.2. ID Token dành cho OIDC Client

ID Token là token xác nhận thông tin xác thực End-User cho OIDC Client. Nó có các claim OIDC như <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, và có thể có <code>auth_time</code>, <code>nonce</code>, <code>acr</code>, <code>amr</code> hoặc claims khác theo request/chính sách.

**Không dùng ID Token làm access token để gọi API.** Audience của ID Token thường liên quan đến OIDC Client; audience của access token phải liên quan đến Resource Server. Một customizer cần phân biệt token type, grant và đối tượng nhận token trước khi thêm claims.

### 7.3. Không đưa dữ liệu chỉ để giao diện hiển thị vào token

Không phải dữ liệu nào frontend muốn hiển thị cũng nên nằm trong access token. Token có thể đi qua browser, proxy, log, mobile storage và nhiều API; JWT payload chỉ Base64URL encode chứ không được mã hóa mặc định. Tránh đưa:

- Mật khẩu, refresh token, API key, client secret, private key hoặc credential xác thực.
- Số giấy tờ, địa chỉ nhà, dữ liệu tài chính/nhạy cảm không cần thiết.
- Danh sách role/permission khổng lồ không phục vụ authorization ở Resource Server.
- Dữ liệu thay đổi liên tục mà token TTL không phản ánh kịp.
- Thông tin nội bộ như đường dẫn database, tên host nội bộ hoặc stack trace.

Ưu tiên claim tối thiểu, ổn định, có ý nghĩa với Resource Server và được phát hành theo consent/policy.

## 8. Quy tắc thiết kế custom claims

### 8.1. Dùng namespace tránh va chạm

Tên claim chung như <code>role</code>, <code>tenant</code>, <code>permissions</code> có thể xung đột với ứng dụng khác hoặc profile sau này. Với dữ liệu riêng của hệ thống, có thể dùng URI namespace thuộc quyền kiểm soát, ví dụ:

~~~json
{
  "https://claims.example.com/tenant_id": "tenant-42",
  "https://claims.example.com/entitlements": [
    "orders.read"
  ]
}
~~~

Đây là JSON minh họa, không phải token thực. URI namespace không nhất thiết là endpoint có thể gọi; nó định danh không gian tên claim. Cần tài liệu hóa kiểu dữ liệu, semantics, owner và version của claim.

### 8.2. Dựa vào nguồn dữ liệu tin cậy

| Dữ liệu muốn thêm | Nguồn nên dùng | Không nên lấy từ |
| --- | --- | --- |
| Tenant ID | Membership/tenant service đã xác minh principal và client. | Query parameter hoặc header chưa kiểm tra. |
| Roles | Authority đã được xác thực, policy hiện hành. | Claim do browser/client gửi. |
| Entitlements | Permission service hoặc authorization domain có thẩm quyền. | Toàn bộ scope client đăng ký. |
| Authentication assurance | Kết quả xác thực/MFA được lưu trong context tin cậy. | Boolean <code>mfa=true</code> từ form. |
| Resource audience | Resource indicator đã xác minh và policy của client/grant. | URL tùy ý do caller gửi. |
| Subject | Principal ID ổn định theo semantics grant. | Email hoặc username có thể đổi nếu cần định danh lâu dài. |

### 8.3. Giữ claim nhất quán với scope

Giả sử token context có <code>authorizedScopes = {orders.read}</code>. Không tạo claim:

~~~json
{
  "permissions": ["orders.read", "orders.write", "orders.admin"]
}
~~~

trừ khi một policy độc lập và đã xác minh thực sự cấp các quyền đó. Nếu Resource Server dùng cả scope và custom permission claim, hai nguồn phải có quy tắc precedence rõ ràng; nếu không, API có thể vô tình cho phép quyền lớn hơn scope.

### 8.4. Không thay các claim giao thức tùy tiện

Các claim như <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, <code>jti</code>, <code>nonce</code> có semantics chuẩn. Đừng ghi đè issuer từ <code>AuthorizationServerContext</code> bằng giá trị request, đổi subject của một authorization mà không có mapping được thiết kế, kéo dài <code>exp</code> vượt TokenSettings hoặc bỏ audience để token dùng được ở mọi API.

Nếu cần audience cụ thể, xác minh resource indicator và client policy ở provider trước, sau đó tạo claim audience từ kết quả đã xác minh. Nếu cần custom TTL, cấu hình TokenSettings hoặc token generation policy phù hợp; không chỉ đặt <code>exp</code> tùy ý trong customizer rồi bỏ qua giới hạn vận hành.

## 9. Những grant khác nhau tạo context khác nhau

### 9.1. Authorization Code

Principal thường là End-User đã xác thực. Scope đã được chấp thuận và consent liên quan đến client. Customizer có thể thêm claim hồ sơ/tenant/role nếu nguồn dữ liệu hợp lệ và token là access token dành cho Resource Server. Không đưa toàn bộ thông tin hồ sơ vào mọi token chỉ vì principal có các thuộc tính đó.

### 9.2. Client Credentials

Principal là client đã xác thực; không có người dùng Alice ở phía sau. Claim <code>sub</code>, <code>client_id</code>, roles và tenant phải biểu diễn service identity theo policy. Không đọc authorities của client rồi đặt tên claim <code>user_roles</code> như thể đó là quyền người dùng.

### 9.3. Refresh Token

Refresh grant tiếp tục một authorization đã có. Customizer cần tôn trọng scope đã được cấp, token settings, trạng thái client và các policy cập nhật. Nếu quyền người dùng/tenant đã bị thu hồi sau lần phát hành trước, chỉ sao chép claims cũ có thể giữ quyền quá lâu; cần xác minh chính sách hiện hành ở điểm refresh/provider thích hợp.

### 9.4. Device Authorization

Sau khi người dùng xác minh device code và chấp thuận, principal/token context phản ánh authorization đã được hoàn tất. Không dùng <code>user_code</code> như subject hoặc claim định danh; user code là mã xác minh ngắn hạn, không phải danh tính người dùng và không nên xuất hiện trong token.

### 9.5. Token Exchange

Token Exchange có thể có subject token và actor token, nên custom claims cần giữ đúng quan hệ subject/actor và audience/resource. Không sao chép mọi claims của subject token sang token mới một cách mù quáng; một số claim có thể không được phép chuyển tiếp hoặc cần giảm quyền.

## 10. Kiểm thử token context và claims

### 10.1. Unit test customizer JWT

Một cách đơn giản là tách phần tính claims thành một hàm thuần/strategy riêng, rồi kiểm tra các trường hợp grant/token type. Ví dụ test policy:

~~~java
@Test
void accessTokenCustomizerDoesNotAddUserRolesForClientCredentials() {
    // Giả định đã tạo JwtEncodingContext test với:
    // tokenType=ACCESS_TOKEN, grantType=CLIENT_CREDENTIALS,
    // principal là client authentication, không phải End-User.
    JwtEncodingContext context = testContextForClientCredentials();

    jwtTokenCustomizer().customize(context);

    assertThat(context.getClaims().build().getClaims())
        .doesNotContainKey("roles");
}
~~~

<code>testContextForClientCredentials()</code> là helper do test tự xây dựng, không phải API Spring. Test kiểm tra rằng customizer không diễn giải nhầm client principal thành user role. Đối với builder trong context, nên tạo fixture theo API của đúng version và không gọi <code>build()</code> sớm trong production.

### 10.2. Integration test JWT access token

Với Authorization Server test thực:

1. Đăng ký client và user fixture; cấu hình JWT/self-contained access token.
2. Hoàn tất Authorization Code + PKCE và consent với scope <code>orders.read</code>.
3. Đổi code lấy token.
4. Decode token bằng public JWK/test decoder, xác minh <code>iss</code>, <code>aud</code>, <code>exp</code>, <code>scope</code> và custom claim tenant/role.
5. Xác nhận token không có scope ngoài consent và không có dữ liệu nhạy cảm.
6. Gọi Resource Server test để kiểm tra claims được ánh xạ đúng thành quyền.

Không chỉ kiểm tra chuỗi JSON của token chưa xác minh chữ ký. Dùng decoder/JWK phù hợp để chứng minh token được ký bởi key của Authorization Server.

### 10.3. Integration test reference token/introspection

Khi dùng <code>OAuth2TokenFormat.REFERENCE</code>:

1. Cấu hình Resource Server dùng opaque token introspection.
2. Cấp access token qua grant thực.
3. Gọi introspection endpoint bằng client authentication phù hợp.
4. Xác minh token active và custom claims có mặt theo contract đã thiết kế.
5. Thu hồi authorization/token, gọi introspection lại và xác nhận trạng thái inactive theo hành vi lưu trữ.

Reference token value không thể decode thành JWT. Đừng viết test giả định mọi access token đều có ba phần phân tách bằng dấu chấm.

### 10.4. Ma trận kiểm thử cần có

| Tình huống | Kết quả mong đợi |
| --- | --- |
| JWT access token, Authorization Code | Chỉ có claims hợp lệ theo user, client, consent và scope. |
| JWT access token, Client Credentials | Claim biểu diễn client/service; không tự có user role. |
| ID Token OIDC | Claim theo OIDC và đúng audience của client. |
| Reference access token | Claims được lưu/đưa ra introspection theo policy. |
| Refresh grant | Scope/claims không vượt authorization còn hiệu lực. |
| Token context thiếu authorization tùy chọn | Customizer xử lý an toàn, không NullPointerException. |
| Tenant không được xác minh | Không phát tenant claim hoặc từ chối theo policy. |
| Scope không được chấp thuận | Không xuất hiện trong token. |
| Client request thêm claim từ form | Bị bỏ qua hoặc từ chối; không tin dữ liệu chưa xác thực. |
| Token generator trả null | Grant provider xử lý lỗi, không phát token rỗng. |
| JWK rotation | Token ký bằng key hợp lệ và Resource Server xác minh được trong cửa sổ rotation. |
| JWT claim customizer lỗi | Không báo thành công nếu token chưa được tạo an toàn. |
| Nhiều customizer cùng generic type | Thứ tự/compose rõ ràng, không ghi đè claims ngoài ý muốn. |
| Audience sai Resource Server | Resource Server từ chối token. |
| Claim nhạy cảm không cần thiết | Không xuất hiện trong token/introspection. |

### 10.5. Kiểm thử tương thích giữa token và Resource Server

Token claims chỉ hữu ích nếu Resource Server hiểu chúng. Cần kiểm tra:

- Issuer được Resource Server tin cậy.
- Audience chứa đúng API đích, không quá rộng.
- Scope được ánh xạ thành authority theo cấu hình thật.
- Custom claim có kiểu dữ liệu ổn định (string, array, number, boolean).
- Token hết hạn bị từ chối theo clock skew đã định.
- Opaque introspection trả đúng <code>active</code>, scope, client/principal và claims được cho phép.

## 11. Các lỗi thiết kế phổ biến

### Lỗi 1: Dùng JwtEncodingContext cho opaque access token

**Triệu chứng:** Custom claim xuất hiện trong JWT test nhưng không xuất hiện ở introspection khi chuyển client sang reference format.

**Nguyên nhân:** <code>JwtGenerator</code> không tạo reference access token.

**Cách xử lý:** Dùng <code>OAuth2TokenCustomizer&lt;OAuth2TokenClaimsContext&gt;</code> cho claims của reference access token và kiểm tra cấu hình <code>OAuth2AccessTokenGenerator</code>.

### Lỗi 2: Dùng OAuth2TokenClaimsContext cho JWT

**Triệu chứng:** Customizer opaque không được gọi khi access token có format SELF_CONTAINED.

**Nguyên nhân:** Generator phù hợp là <code>JwtGenerator</code> và context là <code>JwtEncodingContext</code>.

**Cách xử lý:** Đăng ký đúng customizer/generator theo token format.

### Lỗi 3: Đưa mọi registered scopes vào token

**Triệu chứng:** Access token có <code>orders.write</code> dù người dùng chỉ chấp thuận <code>orders.read</code>.

**Nguyên nhân:** Lấy <code>RegisteredClient.getScopes()</code> thay cho <code>OAuth2TokenContext.getAuthorizedScopes()</code>.

**Cách xử lý:** Dựa vào tập scope đã được grant/consent chấp thuận và kiểm thử quyền cuối cùng ở Resource Server.

### Lỗi 4: Xem principal luôn là người dùng

**Triệu chứng:** Client Credentials token chứa role của một tài khoản người dùng không liên quan hoặc customizer ném lỗi vì principal không có dữ liệu user.

**Nguyên nhân:** Không phân biệt grant type và principal.

**Cách xử lý:** Nhánh theo grant, kiểu principal và nguồn entitlement đã xác minh.

### Lỗi 5: Ghi đè claim chuẩn

**Triệu chứng:** Resource Server từ chối issuer/audience hoặc token có thời hạn ngoài policy.

**Nguyên nhân:** Customizer thay <code>iss</code>, <code>sub</code>, <code>aud</code> hoặc <code>exp</code> bằng dữ liệu request/giá trị cố định.

**Cách xử lý:** Giữ claim chuẩn do generator/context cung cấp; chỉ thay đổi khi có profile và policy được kiểm soát.

### Lỗi 6: Coi JWT payload là dữ liệu bí mật

**Triệu chứng:** Người dùng có thể đọc email, tenant, roles hoặc dữ liệu nội bộ từ access token.

**Nguyên nhân:** Nhầm Base64URL với encryption.

**Cách xử lý:** Chỉ đưa claims cần thiết; nếu cần confidentiality, dùng kiến trúc/token encryption phù hợp thay vì JWT ký thông thường.

### Lỗi 7: Customizer truy vấn dịch vụ từ xa cho mọi token

**Triệu chứng:** Token endpoint chậm, timeout, cấp token không ổn định khi permission service gián đoạn.

**Nguyên nhân:** Customizer gọi nhiều HTTP request đồng bộ ở đường nóng.

**Cách xử lý:** Chuẩn bị dữ liệu entitlement ở bước authorization phù hợp, dùng cache có TTL/invalidation hoặc policy service có SLA; quyết định fail-open/fail-closed rõ ràng.

### Lỗi 8: Khai báo token generator riêng nhưng quên generator mặc định

**Triệu chứng:** Access token JWT chạy nhưng refresh token hoặc reference token không được tạo.

**Nguyên nhân:** Thay composite generator mà chỉ giữ một generator.

**Cách xử lý:** Khi tự lắp <code>DelegatingOAuth2TokenGenerator</code>, thêm tất cả generator cần thiết theo grant/token format và kiểm thử hồi quy.

### Lỗi 9: Coi customizer là nơi quyết định authorization

**Triệu chứng:** Token được phát hành dù client không được phép grant hoặc consent chưa hợp lệ.

**Nguyên nhân:** Chỉ kiểm tra một điều kiện trong customizer, bỏ qua provider.

**Cách xử lý:** Xác minh grant/client/scope trước khi token generation; customizer chỉ tạo claims từ context đã được xác minh.

## 12. Checklist triển khai production

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Context | Client, principal, grant type, authorized scopes và token type có được lấy từ nguồn xác thực không? |
| Token format | Client dùng JWT hay reference token? Resource Server xác minh theo cách nào? |
| Customizer | Generic type có khớp generator/token format không? |
| Claims | Claim nào thực sự cần cho API? Có PII/secret thừa không? |
| Scope | Token có đúng scope được chấp thuận, không phải toàn bộ scope đăng ký không? |
| Subject | Subject có ổn định và đúng semantics của grant không? |
| Audience | Token chỉ dành cho resource đã được phép không? |
| Issuer/expiry | Issuer và TTL lấy từ cấu hình/token settings đáng tin không? |
| JWS | Thuật toán, kid và key rotation tương thích với Resource Server không? |
| OIDC | ID Token claims có đúng client audience và semantics OIDC không? |
| Opaque token | Introspection có trả custom claims theo contract và revocation đúng không? |
| Persistence | Token metadata/authorization được lưu nhất quán và có thể thu hồi không? |
| Performance | Customizer có tránh I/O đồng bộ nặng và xử lý lỗi dependency không? |
| Observability | Không log token/claim nhạy cảm; có metrics cho lỗi generation? |
| Tests | Có test theo grant, token type, token format, Resource Server và key rotation không? |

## 13. Bài tập vận dụng

Một Authorization Server phục vụ hai API là Orders và Billing. Client <code>orders-web</code> dùng Authorization Code + PKCE; client <code>billing-worker</code> dùng Client Credentials. Cả hai đều có thể được cấp access token JWT hoặc reference token theo cấu hình.

1. Vẽ pipeline từ grant provider đến <code>OAuth2TokenGenerator</code> và mô tả dữ liệu được đưa vào <code>OAuth2TokenContext</code>.
2. Tạo <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> thêm claim tenant chỉ khi principal đã được xác minh là thành viên tenant đó.
3. Chỉ thêm role claim cho Authorization Code; chứng minh Client Credentials không bị gán user role.
4. Đổi Orders client sang <code>OAuth2TokenFormat.REFERENCE</code>, cấu hình <code>OAuth2TokenCustomizer&lt;OAuth2TokenClaimsContext&gt;</code> và kiểm tra introspection response.
5. Giải thích vì sao <code>registeredClient.getScopes()</code> không thể thay <code>context.getAuthorizedScopes()</code> khi tạo claim scope.
6. Thiết kế audience cho Orders API và Billing API, bảo đảm token của Orders không được Billing chấp nhận.
7. Viết test xác minh ID Token không bị dùng như access token và audience khác nhau.
8. Thử thêm một claim nhạy cảm không cần thiết rồi phân tích rủi ro khi JWT payload bị đọc bởi client.
9. Cấu hình customizer bean và nếu tự lắp token generator, chứng minh tất cả generator cần thiết vẫn hoạt động.
10. Kiểm thử key rotation, token expiry, Resource Server authorization và reference token revocation.

**Tiêu chí đạt:** Bạn phải chỉ ra được **context nào được dùng cho token nào**, **claim lấy từ nguồn nào**, **token được Resource Server nào nhận**, và **customizer không thể mở rộng quyền ngoài authorization đã được xác minh**.

## 14. Tài liệu đối chiếu

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>OAuth2TokenContext</code>, token generator, customizer và authorization model.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): grant providers và điểm tạo token trong endpoint.
- [Spring Authorization Server — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html): contract context chung.
- [Spring Authorization Server — JwtEncodingContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtEncodingContext.html): JWS header builder và JWT claims builder.
- [Spring Authorization Server — OAuth2TokenClaimsContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenClaimsContext.html): claims context cho access token generator.
- [Spring Authorization Server — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): hợp đồng sinh token.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): access token format và thời hạn.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claims chuẩn và cấu trúc JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, issuer/audience/type và claims.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 và bảo vệ access token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, claims và scope OIDC.
