# Tùy chỉnh endpoint bằng các extension point công khai

## 1. Mục tiêu và phạm vi

Trong mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**. Bài này trình bày cách mở rộng hành vi protocol endpoint thông qua các extension point công khai của Spring Authorization Server.

Một Authorization Server thường cần điều chỉnh theo nghiệp vụ: kiểm tra thêm điều kiện ở Authorization Endpoint, bổ sung một authorization grant, thay đổi claims trong UserInfo, thêm bước kiểm tra trước khi introspect token, hoặc định dạng lại response theo policy. Spring Authorization Server cung cấp các configurer và SPI để thực hiện những thay đổi này mà vẫn giữ vòng đời xử lý của endpoint.

Các extension point thường gặp gồm:

- `AuthenticationConverter`: chuyển HTTP request thành một đối tượng `Authentication` biểu diễn yêu cầu protocol.
- `AuthenticationProvider`: xác thực và xử lý đối tượng `Authentication` đó.
- `AuthenticationSuccessHandler`: tạo response khi xử lý thành công.
- `AuthenticationFailureHandler`: chuyển lỗi xác thực thành response protocol.
- Validator và mapper: kiểm tra tham số hoặc ánh xạ context thành claims/response.
- Các component dùng chung như `OAuth2TokenGenerator`, `OAuth2AuthorizationService` và `RegisteredClientRepository`.

**Phiên bản tham chiếu:** code và API trong bài đối chiếu Spring Authorization Server **1.5.8**. Khi dùng nhánh khác, kiểm tra Javadoc của đúng artifact/version vì tên method và endpoint configurer có thể thay đổi qua các major release.

Sau bài này, bạn có thể:

1. Hiểu cách `OAuth2AuthorizationServerConfigurer` lắp ráp endpoint vào `SecurityFilterChain`.
2. Chọn đúng extension point theo loại thay đổi.
3. Thêm converter/provider cho một extension authorization grant.
4. Tùy biến validator mà vẫn giữ các kiểm tra mặc định cần thiết.
5. Thay đổi success/error handling mà không làm sai protocol response.
6. Mở rộng UserInfo hoặc endpoint khác bằng mapper/provider.
7. Kiểm thử thứ tự xử lý, tương thích và bảo mật của extension.

## 2. Kiến trúc xử lý của một protocol endpoint

### 2.1. Endpoint filter nằm trong Authorization Server SecurityFilterChain

`OAuth2AuthorizationServerConfigurer` cấu hình các filter xử lý protocol endpoint và đăng ký chúng vào `SecurityFilterChain` dành cho Authorization Server. Một endpoint configurer là điểm cấu hình của filter tương ứng; nó không phải một REST controller độc lập.

Ví dụ cấu hình filter chain theo API 1.5.8:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .registeredClientRepository(registeredClientRepository)
                .authorizationService(authorizationService)
                .tokenGenerator(tokenGenerator)
                .tokenEndpoint(tokenEndpoint -> {
                    // Cấu hình extension point cho Token Endpoint tại đây.
                })
                .authorizationEndpoint(authorizationEndpoint -> {
                    // Cấu hình extension point cho Authorization Endpoint tại đây.
                })
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
```

Đây là phần cấu hình của Authorization Server chain. Các import và bean dependency được lược bỏ để tập trung vào endpoint configurer. Ứng dụng vẫn cần chain phù hợp cho form login, trang consent hoặc tài nguyên web khác. Hãy dùng `getEndpointsMatcher()` để áp dụng đúng chain cho các protocol endpoint và giữ thứ tự chain nhất quán với phần còn lại của ứng dụng.

Nếu dự án đã có `SecurityFilterChain` của Authorization Server, hãy bổ sung endpoint configurer vào bean hiện tại. Không tạo thêm chain cùng matcher chỉ để đăng ký một converter/provider.

### 2.2. Ba giai đoạn: pre-processing, main processing, post-processing

Spring Authorization Server tổ chức extension point theo ba giai đoạn:

```text
HTTP request
     |
     v
Endpoint Filter
     |
     v
AuthenticationConverter(s)
     |  đọc tham số, kiểm tra cấu trúc request
     |  tạo Authentication phù hợp
     v
AuthenticationManager
     |
     v
AuthenticationProvider(s)
     |  kiểm tra client, grant, authorization,
     |  policy và phát hành/tra cứu dữ liệu
     v
Authentication result
     |
     +------ thành công ------> AuthenticationSuccessHandler
     |
     +------ lỗi ------------> AuthenticationFailureHandler
                                  |
                                  v
                             HTTP response
```

| Giai đoạn | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Pre-processing | `AuthenticationConverter` | Đọc HTTP request và tạo đối tượng xác thực đúng loại |
| Main processing | `AuthenticationProvider` | Xác thực client/grant/token và thực hiện nghiệp vụ protocol |
| Post-processing | Success/error handler | Ghi status, header và body đúng giao thức |

Không phải endpoint nào cũng có đủ cả bốn loại extension point. Ví dụ UserInfo có `userInfoMapper`, Token Endpoint có `accessTokenResponseHandler`, còn Authorization Endpoint có `consentPage`.

### 2.3. Converter và Provider có hợp đồng khác nhau

`AuthenticationConverter.convert(request)` có thể trả về:

- một `Authentication` nếu converter nhận diện request và chuyển đổi được;
- `null` nếu request không thuộc loại converter đó để converter tiếp theo xử lý;
- exception protocol nếu request có dạng thuộc converter nhưng thiếu/sai tham số.

`AuthenticationProvider` cung cấp:

- `supports(authenticationClass)` để cho biết provider xử lý loại Authentication nào;
- `authenticate(authentication)` để xác thực và trả kết quả, hoặc ném exception.

Một custom grant thường cần cả converter lẫn provider. Converter không nên tự phát hành token; provider không nên tự parse `HttpServletRequest`. Phân chia này giúp kiểm thử độc lập và giữ đúng kiến trúc Spring Security.

## 3. Bản đồ extension point theo endpoint

Các configurer công khai của Spring Authorization Server 1.5.8 cung cấp extension point tương ứng với chức năng từng endpoint:

| Endpoint/configurer | Converter | Provider | Post-processing / mapper |
| --- | --- | --- | --- |
| Authorization Endpoint | `authorizationRequestConverter(s)` | `authenticationProvider(s)` | `authorizationResponseHandler`, `errorResponseHandler`, `consentPage` |
| Client Authentication | `authenticationConverter(s)` | `authenticationProvider(s)` | `authenticationSuccessHandler`, `errorResponseHandler` |
| Token Endpoint | `accessTokenRequestConverter(s)` | `authenticationProvider(s)` | `accessTokenResponseHandler`, `errorResponseHandler` |
| Token Introspection | `introspectionRequestConverter(s)` | `authenticationProvider(s)` | `introspectionResponseHandler`, `errorResponseHandler` |
| Token Revocation | `revocationRequestConverter(s)` | `authenticationProvider(s)` | `revocationResponseHandler`, `errorResponseHandler` |
| Device Authorization | `deviceAuthorizationRequestConverter(s)` | `authenticationProvider(s)` | `deviceAuthorizationResponseHandler`, `errorResponseHandler` |
| Device Verification | `deviceVerificationRequestConverter(s)` | `authenticationProvider(s)` | `deviceVerificationResponseHandler`, `errorResponseHandler` |
| Pushed Authorization Request | `pushedAuthorizationRequestConverter(s)` | `authenticationProvider(s)` | `pushedAuthorizationResponseHandler`, `errorResponseHandler` |
| OIDC UserInfo | `userInfoRequestConverter(s)` | `authenticationProvider(s)` | `userInfoMapper`, `userInfoResponseHandler`, `errorResponseHandler` |
| OIDC Logout | `logoutRequestConverter(s)` | `authenticationProvider(s)` | `logoutResponseHandler`, `errorResponseHandler` |
| OIDC Client Registration | `clientRegistrationRequestConverter(s)` | `authenticationProvider(s)` | `clientRegistrationResponseHandler`, `errorResponseHandler` |
| Authorization Server Metadata | — | — | `authorizationServerMetadataCustomizer` |
| OIDC Provider Configuration | — | — | `providerConfigurationCustomizer` |

Tên method cụ thể cần tra Javadoc của endpoint configurer tương ứng. Bảng cho thấy mô hình chung, không có nghĩa tất cả endpoint đều dùng cùng một class hoặc cùng kiểu Authentication.

### 3.1. Thêm component và thay danh sách component

Nhiều configurer có hai dạng API:

- `...Converter(converter)` hoặc `authenticationProvider(provider)`: thêm một component.
- `...Converters(Consumer<List<AuthenticationConverter>>)` hoặc `authenticationProviders(Consumer<List<AuthenticationProvider>>)`: truy cập danh sách mặc định và các component đã thêm để tùy chỉnh.

Dạng `Consumer<List<...>>` hữu ích khi cần thay validator bên trong provider mặc định hoặc sắp xếp converter. Tuy nhiên, thay danh sách cũng có thể vô tình xóa xử lý mặc định. Hãy chỉ thay đúng component cần thiết và giữ các component còn lại.

### 3.2. Extension point và component dùng chung

`OAuth2AuthorizationServerConfigurer` còn cho phép cấu hình các thành phần nền tảng:

| Component | Ảnh hưởng |
| --- | --- |
| `RegisteredClientRepository` | Tìm client, grant type, authentication method và scope được đăng ký |
| `OAuth2AuthorizationService` | Lưu, tìm, cập nhật và xóa authorization |
| `OAuth2AuthorizationConsentService` | Lưu consent của resource owner |
| `AuthorizationServerSettings` | Issuer và các endpoint URI |
| `OAuth2TokenGenerator` | Phát hành access token, refresh token, ID Token tùy generator được cấu hình |
| Client authentication configurer | Xác thực client tại endpoint cần client authentication |

Nếu yêu cầu thay đổi liên quan token format hoặc token claims, cân nhắc `OAuth2TokenGenerator`/`OAuth2TokenCustomizer` thay vì viết lại toàn bộ Token Endpoint. Nếu yêu cầu liên quan lưu trữ, thay `OAuth2AuthorizationService` thay vì can thiệp trực tiếp vào filter.

## 4. Chọn đúng extension point

Trước khi viết code, mô tả thay đổi thành một câu hỏi cụ thể:

| Nhu cầu | Extension point phù hợp |
| --- | --- |
| Đọc thêm parameter trong request | Converter |
| Bổ sung phương thức xác thực client | `clientAuthentication().authenticationConverter(s)`, `authenticationProvider(s)` và handlers |
| Thêm validation dựa trên client, grant hoặc authorization | Provider validator hoặc custom Provider |
| Thêm một loại grant mới | Grant `AuthenticationConverter` + grant `AuthenticationProvider` + Token Endpoint |
| Tùy biến claims trong UserInfo | `userInfoMapper` |
| Tùy biến JWT/access token claims | Token customizer hoặc token generator |
| Thay response body theo chuẩn endpoint | Success handler, nếu response model cần thay đổi thực sự |
| Chuẩn hóa lỗi protocol | Error handler, nếu mapping mặc định không đáp ứng yêu cầu |
| Thay URL endpoint | `AuthorizationServerSettings` |
| Thay nơi lưu authorization | `OAuth2AuthorizationService` |
| Thay nơi lưu client/consent | `RegisteredClientRepository` / `OAuth2AuthorizationConsentService` |

Ưu tiên extension point hẹp nhất đáp ứng yêu cầu. Thay toàn bộ provider hoặc handler có phạm vi ảnh hưởng lớn hơn việc thêm một validator hoặc mapper.

## 5. Ví dụ: tùy chỉnh Authorization Endpoint validator

### 5.1. Validator mặc định kiểm tra điều gì?

Authorization Endpoint xử lý authorization request và consent. Trong Authorization Code Flow, `OAuth2AuthorizationCodeRequestAuthenticationProvider` dùng validator mặc định để kiểm tra các tham số như `redirect_uri` và `scope`. Nếu validation thất bại, provider ném `OAuth2AuthorizationCodeRequestAuthenticationException`.

Một tình huống thường gặp là bổ sung policy theo tenant hoặc môi trường. Ví dụ, ứng dụng muốn giới hạn `redirect_uri` theo một allowlist riêng, đồng thời vẫn giữ scope validator mặc định.

### 5.2. Nối validator tùy chỉnh với validator mặc định

Ví dụ dưới đây dùng `authenticationProviders(...)` để tìm provider mặc định và thay validator của nó:

```java
private Consumer<List<AuthenticationProvider>> configureAuthorizationValidator(
        RedirectUriPolicy redirectUriPolicy) {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2AuthorizationCodeRequestAuthenticationProvider codeProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    new TenantRedirectUriValidator(redirectUriPolicy)
                            .andThen(
                                OAuth2AuthorizationCodeRequestAuthenticationValidator
                                    .DEFAULT_SCOPE_VALIDATOR
                            );

            codeProvider.setAuthenticationValidator(validator);
        }
    });
}
```

Đăng ký validator trong Authorization Server chain:

```java
authorizationServer.authorizationEndpoint(endpoint ->
        endpoint.authenticationProviders(
                configureAuthorizationValidator(redirectUriPolicy)
        )
);
```

`TenantRedirectUriValidator` là validator do ứng dụng định nghĩa. Nó nhận `OAuth2AuthorizationCodeRequestAuthenticationContext`, lấy authorization request và so sánh redirect URI với policy server-side. Validator phải ném `OAuth2AuthorizationCodeRequestAuthenticationException` với `OAuth2Error` phù hợp nếu không chấp nhận request.

Ví dụ minh họa kiểm tra allowlist đơn giản:

```java
final class TenantRedirectUriValidator
        implements Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> {

    private final RedirectUriPolicy redirectUriPolicy;

    TenantRedirectUriValidator(RedirectUriPolicy redirectUriPolicy) {
        this.redirectUriPolicy = redirectUriPolicy;
    }

    @Override
    public void accept(OAuth2AuthorizationCodeRequestAuthenticationContext context) {
        OAuth2AuthorizationCodeRequestAuthenticationToken authentication =
                context.getAuthentication();

        String redirectUri = authentication.getRedirectUri();
        RegisteredClient registeredClient = context.getRegisteredClient();

        if (!redirectUriPolicy.isAllowed(registeredClient, redirectUri)) {
            OAuth2Error error = new OAuth2Error(
                    OAuth2ErrorCodes.INVALID_REQUEST,
                    "The redirect_uri is not allowed by tenant policy",
                    null
            );
            throw new OAuth2AuthorizationCodeRequestAuthenticationException(
                    error, null
            );
        }
    }
}
```

`RedirectUriPolicy` ở đây là service nghiệp vụ do ứng dụng triển khai. Policy phải dựa trên client registration/tenant đã được xác định và danh sách URI do server quản lý. Không chấp nhận URI chỉ vì nó đến từ một domain có vẻ đáng tin, không dùng wildcard rộng và không tự động thêm URI được client gửi lên vào allowlist.

### 5.3. Vì sao phải giữ validator mặc định?

Đoạn code nối `DEFAULT_SCOPE_VALIDATOR` sau validator redirect URI. Nếu thay toàn bộ validator mà bỏ scope validator, request có thể vượt qua kiểm tra scope mà Spring Authorization Server vốn thực hiện.

Khi tùy chỉnh provider mặc định:

- tìm đúng provider bằng `instanceof`;
- giữ lại các validator mặc định không có chủ đích thay thế;
- không xóa provider mặc định khỏi danh sách;
- viết test cho cả request hợp lệ và request phải bị từ chối.

Nếu thay validator redirect URI, validator tùy chỉnh phải thực thi policy ít nhất nghiêm ngặt tương đương yêu cầu bảo mật của OAuth 2.0.

## 6. Ví dụ: thêm extension authorization grant

### 6.1. Khi nào cần grant mới?

Spring Authorization Server hỗ trợ các grant chuẩn như Authorization Code, Refresh Token, Client Credentials, Device Code và Token Exchange theo phiên bản/cấu hình tương ứng. Nếu nghiệp vụ thực sự cần một grant riêng, có thể mở rộng Token Endpoint bằng một URI grant type duy nhất, ví dụ:

```text
urn:ietf:params:oauth:grant-type:custom_code
```

Grant riêng cần được mô tả rõ trong hợp đồng giữa client và Authorization Server. Không tạo grant mới chỉ để thêm một parameter vào grant chuẩn; khi đó converter/validator hiện có có thể phù hợp hơn.

### 6.2. Custom grant AuthenticationToken

Đối tượng grant token mang dữ liệu đã được converter đọc từ HTTP request. Nó nên kế thừa `OAuth2AuthorizationGrantAuthenticationToken` để provider và Token Endpoint nhận diện đúng loại:

Các đoạn code trong phần custom grant là các lớp minh họa; import được lược bỏ để tập trung vào hợp đồng của extension.

```java
public final class CustomCodeGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private final String code;

    public CustomCodeGrantAuthenticationToken(
            String code,
            Authentication clientPrincipal,
            Map<String, Object> additionalParameters) {
        super(
                new AuthorizationGrantType(
                        "urn:ietf:params:oauth:grant-type:custom_code"
                ),
                clientPrincipal,
                additionalParameters
        );
        this.code = code;
    }

    public String getCode() {
        return this.code;
    }
}
```

Đây là loại `Authentication` nội bộ của extension. `code` phải là grant credential được kiểm tra ở provider, không phải một giá trị mà converter đã xác minh.

### 6.3. Converter cho custom grant

Converter chỉ xử lý request có đúng `grant_type`; các request khác trả về `null` để converter mặc định hoặc converter khác tiếp tục xử lý:

```java
public final class CustomCodeGrantAuthenticationConverter
        implements AuthenticationConverter {

    private static final String GRANT_TYPE =
            "urn:ietf:params:oauth:grant-type:custom_code";

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grantType = request.getParameter(OAuth2ParameterNames.GRANT_TYPE);
        if (!GRANT_TYPE.equals(grantType)) {
            return null;
        }
        String[] grantTypeValues =
                request.getParameterValues(OAuth2ParameterNames.GRANT_TYPE);
        if (grantTypeValues == null || grantTypeValues.length != 1) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }
        Set<String> allowedParameters = Set.of(
                OAuth2ParameterNames.GRANT_TYPE,
                OAuth2ParameterNames.CODE,
                OAuth2ParameterNames.SCOPE,
                OAuth2ParameterNames.CLIENT_ID,
                OAuth2ParameterNames.CLIENT_SECRET
        );
        if (!allowedParameters.containsAll(request.getParameterMap().keySet())) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }

        String code = request.getParameter(OAuth2ParameterNames.CODE);
        String[] codeValues = request.getParameterValues(OAuth2ParameterNames.CODE);
        if (!StringUtils.hasText(code) || codeValues == null || codeValues.length != 1) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Map<String, Object> additionalParameters = new HashMap<>();
        String[] scopeValues = request.getParameterValues(OAuth2ParameterNames.SCOPE);
        if (scopeValues != null) {
            if (scopeValues.length != 1) {
                throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
            }
            if (StringUtils.hasText(scopeValues[0])) {
                additionalParameters.put(OAuth2ParameterNames.SCOPE, scopeValues[0]);
            }
        }

        Authentication clientPrincipal =
                SecurityContextHolder.getContext().getAuthentication();

        return new CustomCodeGrantAuthenticationToken(
                code,
                clientPrincipal,
                additionalParameters
        );
    }
}
```

Đoạn code tập trung vào parameter cần thiết. Trong implementation thực tế, nếu grant có additional parameters, hãy:

- kiểm tra parameter có xuất hiện nhiều lần hay không;
- chỉ cho phép các parameter được đặc tả;
- loại bỏ protocol parameter đã xử lý khỏi additional parameter map;
- giới hạn kích thước và kiểu dữ liệu;
- trả `null` khi grant type không thuộc converter.

Ví dụ converter trên cho phép thêm tối đa một `scope` parameter vào additional parameters. `client_id` và `client_secret` được allowlist để client authentication converter xử lý, nhưng không được sao chép vào additional parameters của grant. `CustomCodeService` cần đọc scope này, kiểm tra scope thuộc `RegisteredClient` và policy của grant, rồi trả về tập scope thực sự được cấp trong `CustomCodeResult`. Không đưa nguyên scope do client gửi thẳng vào token mà chưa kiểm tra.

Không đọc client ID từ request để xác định danh tính client đã xác thực. Dùng client principal trong `SecurityContextHolder` do client authentication filter đã thiết lập.

### 6.4. Provider cho custom grant

Provider là nơi xác thực grant credential và phát hành token. Phần khung quan trọng:

```java
public final class CustomCodeGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;
    private final CustomCodeService customCodeService;

    public CustomCodeGrantAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator,
            CustomCodeService customCodeService) {
        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
        this.customCodeService = customCodeService;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        CustomCodeGrantAuthenticationToken grant =
                (CustomCodeGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
                getAuthenticatedClientElseThrowInvalidClient(grant);
        RegisteredClient registeredClient =
                clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(grant.getGrantType())) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.UNAUTHORIZED_CLIENT
            );
        }

        // Kiểm tra code, client binding, expiry, audience và one-time use.
        CustomCodeResult result = customCodeService.consume(
                grant.getCode(), registeredClient, grant.getAdditionalParameters()
        );

        // Dựng OAuth2TokenContext và gọi tokenGenerator.generate(...).
        // Lưu OAuth2Authorization cùng access token vào authorizationService.
        // Trả OAuth2AccessTokenAuthenticationToken.
        return issueToken(grant, clientPrincipal, registeredClient, result);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return CustomCodeGrantAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
```

`getAuthenticatedClientElseThrowInvalidClient(...)` và `issueToken(...)` là helper của ví dụ, cần triển khai theo API của Spring Authorization Server. Provider phải kiểm tra:

1. Client đã được xác thực.
2. `RegisteredClient` có khai báo custom grant type.
3. Code thuộc đúng client/subject/audience và chưa hết hạn.
4. Code chưa từng được sử dụng; thao tác consume phải atomic để chống replay.
5. Scope được yêu cầu nằm trong scope client được phép và policy grant; tập scope thực sự cấp phải nằm trong kết quả đã xác thực của custom code service.
6. Token generator trả token hợp lệ; nếu không, trả lỗi protocol phù hợp.
7. Authorization được lưu trước khi response thành công được gửi về client.

Không để TODO validation trong production. Mẫu provider chính thức của Spring minh họa cách tạo `OAuth2TokenContext`, gọi `OAuth2TokenGenerator`, xây dựng `OAuth2Authorization`, lưu authorization và trả `OAuth2AccessTokenAuthenticationToken`.

### 6.5. Đăng ký converter và provider

Thêm hai component vào Token Endpoint:

```java
authorizationServer.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint
            .accessTokenRequestConverter(
                    new CustomCodeGrantAuthenticationConverter()
            )
            .authenticationProvider(
                    new CustomCodeGrantAuthenticationProvider(
                            authorizationService,
                            tokenGenerator,
                            customCodeService
                    )
            )
);
```

Client cũng phải được đăng ký với `AuthorizationGrantType` tương ứng:

```java
AuthorizationGrantType customGrant =
        new AuthorizationGrantType(
                "urn:ietf:params:oauth:grant-type:custom_code"
        );

RegisteredClient registeredClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("integration-client")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(customGrant)
        .scope("records.read")
        .build();
```

Đoạn code giả định `passwordEncoder` và `clientSecret` được cung cấp từ cấu hình/secret manager. Secret và repository trong ví dụ cần được cấu hình theo môi trường thực tế. Không dùng secret hard-coded hoặc `{noop}` cho production.

### 6.6. Gọi Token Endpoint

Client đã xác thực gửi request theo contract custom grant:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64(integration-client:CLIENT_SECRET)
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:custom_code&code=ONE_TIME_CODE
```

Đây là ví dụ minh họa giao thức của extension. Tên parameter và semantics của code phải được đặc tả rõ cho client, bao gồm expiry, client binding, replay protection và lỗi trả về.

## 7. Ví dụ: tùy biến UserInfo bằng mapper

### 7.1. Khi mapper là đủ?

UserInfo Endpoint là OAuth2 protected resource. Client gửi Access Token dạng Bearer; provider xác thực token và lấy authorization liên quan. Nếu chỉ cần thay đổi claims trong response, `userInfoMapper` là extension point phù hợp. Không cần thay converter hoặc provider nếu cơ chế xác thực Access Token vẫn đúng.

Mapper nhận `OidcUserInfoAuthenticationContext`, trong đó có:

- Access Token dùng cho request;
- `OAuth2Authorization` gắn với Access Token;
- ID Token và các thông tin liên quan authorization.

### 7.2. Tạo UserInfo response có scope gate

Ví dụ dưới đây chỉ trả claims theo scope đã cấp, luôn lấy `sub` từ ID Token gắn với authorization hiện tại:

```java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            OidcIdToken idToken = context.getAuthorization()
                    .getToken(OidcIdToken.class)
                    .getToken();
            String subject = idToken.getSubject();
            Set<String> scopes = context.getAccessToken().getScopes();

            Map<String, Object> claims = new LinkedHashMap<>();
            claims.put("sub", subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.putAll(profileService.loadProfileClaims(subject));
            }
            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.putAll(profileService.loadEmailClaims(subject));
            }
            if (scopes.contains(OidcScopes.PHONE)) {
                claims.putAll(profileService.loadPhoneClaims(subject));
            }

            // Không cho profile service ghi đè subject.
            claims.put("sub", subject);
            return new OidcUserInfo(claims);
        };
```

Đăng ký mapper trong OIDC configurer:

```java
authorizationServer.oidc(oidc ->
        oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)
        )
);
```

`profileService` là service do ứng dụng triển khai. Các method chỉ trả claim được phép theo scope và consent. Nếu profile service trả dữ liệu thiếu, mapper có thể bỏ claim tùy chọn; không tạo giá trị giả để lấp response.

### 7.3. Các điều kiện cần giữ

- `sub` trong UserInfo phải là subject tương ứng với Access Token/ID Token hiện tại.
- Không lấy subject từ query parameter hoặc một profile identifier do client gửi lên.
- Chỉ trả claims được cho phép bởi scope, consent và privacy policy.
- Không trả password, recovery data, security answer hoặc thuộc tính nội bộ.
- Nếu `sub` không thể lấy từ authorization hợp lệ, fail request; không tự tạo subject khác.
- Test response với Access Token có scope khác nhau và với profile service trả dữ liệu thiếu.

Nếu muốn tùy biến quá trình xác thực Access Token hoặc cách lấy authorization, khi đó mới cân nhắc `authenticationProviders(...)`. Nếu chỉ thay claims, mapper giữ phạm vi thay đổi nhỏ hơn.

## 8. Success handler, error handler và consent page

### 8.1. Success handler là phần trả response protocol

Success handler nhận kết quả Authentication đã được provider xử lý. Tùy endpoint, nó phải trả đúng response:

| Endpoint | Thành công cần trả |
| --- | --- |
| Authorization | Redirect/authorization response theo `response_type` và `response_mode` |
| Token | OAuth2 access token response |
| Introspection | Token introspection response |
| Revocation | Response theo RFC 7009 |
| UserInfo | UserInfo claims response |
| Client Registration | Registration hoặc Client Read response |

Success handler tùy chỉnh phải giữ status code, `Content-Type`, `Cache-Control`, `Pragma`, header và body theo giao thức. Với token response, đặc biệt không bỏ `Cache-Control: no-store` và `Pragma: no-cache`.

Nếu chỉ muốn thêm log hoặc metric, hãy dùng observability phù hợp ở lớp service/filter mà không thay response handler. Nếu thay response body, hãy xác nhận client vẫn parse được đúng schema OAuth/OIDC.

### 8.2. Error handler không được làm lộ nội bộ

Error handler nhận exception và tạo protocol error response. Khi tùy chỉnh:

- giữ `error` code theo OAuth2/OIDC;
- chỉ trả `error_description` đủ hữu ích cho client;
- không trả stack trace, SQL error, internal class name hoặc dữ liệu nhạy cảm;
- giữ HTTP status phù hợp với lỗi;
- ghi log nội bộ bằng correlation ID và error category, không log raw token/client secret.

Không biến mọi lỗi thành HTTP 200 hoặc một response thành công giả. Client cần phân biệt được `invalid_request`, `invalid_client`, `invalid_grant`, `unauthorized_client`, `invalid_scope` và `server_error` khi các mã đó áp dụng.

### 8.3. Consent page là điểm tùy chỉnh giao diện

Authorization Endpoint có `consentPage(...)` để chuyển resource owner đến trang consent do ứng dụng cung cấp. Trang consent phải:

- hiển thị client đang yêu cầu quyền và các scope cụ thể;
- cho phép người dùng đồng ý/từ chối theo policy;
- gửi form bằng HTTP POST đến Authorization Endpoint;
- gửi lại `client_id`, `state` và danh sách scope người dùng đã chấp thuận;
- bảo vệ CSRF và không tự động đồng ý chỉ vì request hợp lệ.

`state` trong luồng consent là dữ liệu ràng buộc request; giữ nguyên giá trị do server cung cấp và kiểm tra theo flow. Không dùng query parameter `scope` của trang consent làm nguồn quyền duy nhất.

### 8.4. Metadata endpoint cũng có customizer

Authorization Server Metadata và OIDC Provider Configuration có customizer cho builder response. Đây là extension point phù hợp để công bố metadata bổ sung được giao thức cho phép. Chỉ công bố endpoint, grant type, response type, signing algorithm hoặc capability mà server thực sự hỗ trợ; metadata công bố phải khớp cấu hình runtime.

## 9. Kiểm thử extension point

### 9.1. Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| EXT-01 | Authorization Server chain dùng `getEndpointsMatcher()` | Protocol endpoint được xử lý bởi đúng chain |
| EXT-02 | Thêm converter cho grant riêng | Request có grant type riêng được nhận diện |
| EXT-03 | Converter gặp grant type khác | Trả `null` để converter tiếp theo xử lý |
| EXT-04 | Request thiếu parameter bắt buộc | Converter trả lỗi protocol `invalid_request` |
| EXT-05 | Parameter bắt buộc xuất hiện lặp | Request bị từ chối |
| EXT-06 | Custom AuthenticationToken | Được provider hỗ trợ đúng class |
| EXT-07 | Provider nhận Authentication không hỗ trợ | `supports()` trả false |
| EXT-08 | Client chưa xác thực gọi custom grant | Bị từ chối bởi client authentication |
| EXT-09 | Client không đăng ký custom grant | Provider trả `unauthorized_client` |
| EXT-10 | Grant code sai/hết hạn | Provider từ chối với lỗi grant phù hợp |
| EXT-11 | Dùng lại grant code đã consume | Replay bị từ chối; không phát hành token thứ hai |
| EXT-12 | Token generator trả null | Không lưu authorization thành công; trả `server_error` |
| EXT-13 | Authorization service lưu thất bại | Không gửi token response thành công |
| EXT-14 | Custom validator từ chối redirect URI | Authorization request bị từ chối |
| EXT-15 | Custom redirect validator vẫn nối scope validator mặc định | Scope không hợp lệ tiếp tục bị từ chối |
| EXT-16 | UserInfo Access Token thiếu scope `email` | Mapper không trả email claim |
| EXT-17 | UserInfo `sub` không thể lấy từ authorization | Request thất bại, không tạo subject giả |
| EXT-18 | Profile service trả dữ liệu chứa `sub` khác | Mapper giữ subject từ ID Token |
| EXT-19 | Success handler Token Endpoint | Response tuân thủ schema và cache headers |
| EXT-20 | Error handler nhận `OAuth2AuthenticationException` | Error code/status phù hợp, không lộ stack trace |
| EXT-21 | Custom consent page nhận state | POST consent gửi lại state/client/scope hợp lệ |
| EXT-22 | Metadata customizer công bố capability không được hỗ trợ | Test cấu hình phải thất bại |
| EXT-23 | Custom grant converter/provider được đăng ký cùng converter mặc định | Grant chuẩn vẫn hoạt động |
| EXT-24 | Dùng `authenticationProviders(...)` để thay validator | Provider mặc định khác vẫn còn trong danh sách |
| EXT-25 | Hai extension converter cùng nhận một grant type | Test phát hiện thứ tự/ownership không rõ ràng |
| EXT-26 | Custom provider ném exception nội bộ | Error response không tiết lộ implementation detail |
| EXT-27 | Custom grant scope vượt scope client | Request bị từ chối |
| EXT-28 | Token response có JWT claims tùy chỉnh | Chữ ký, issuer, audience và claims vẫn hợp lệ |
| EXT-29 | Nâng phiên bản Spring Authorization Server | Compile và integration test xác nhận method/API tương thích |
| EXT-30 | Nhiều instance dùng extension cùng version | Token/authorization được lưu và đọc nhất quán |
| EXT-31 | Custom client authentication converter được thêm | Phương thức mặc định như `client_secret_basic` vẫn hoạt động |

### 9.2. Kiểm thử theo từng tầng

**Converter unit test**

- Dùng `MockHttpServletRequest`.
- Kiểm tra request thuộc converter, request không thuộc converter và parameter lặp.
- Xác nhận converter không làm thay đổi `SecurityContext`.

**Provider unit test**

- Mock `OAuth2AuthorizationService`, `OAuth2TokenGenerator` và service xác thực grant.
- Kiểm tra client/grant/scope, expiry, replay và token generator failure.
- Xác nhận authorization chỉ được lưu sau khi grant hợp lệ và token được tạo.

**Endpoint integration test**

- Khởi động `SecurityFilterChain` thật với endpoint configurer.
- Gửi HTTP request đã xác thực client.
- Kiểm tra status, headers, body và persisted authorization.
- Kiểm tra grant chuẩn vẫn chạy sau khi thêm extension.

**Protocol interoperability test**

- Dùng client thực hoặc test client gửi request.
- Xác nhận OAuth2/OIDC error và success response có đúng schema.
- Xác nhận discovery metadata khớp endpoint thực tế.

## 10. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Converter không chạy | Chưa thêm converter vào đúng endpoint configurer hoặc filter chain khác bắt request | Kiểm tra `getEndpointsMatcher()` và endpoint path |
| Converter custom chạy với grant chuẩn | Converter không trả `null` cho grant type không thuộc nó | Kiểm tra grant type trước khi parse parameter |
| Provider không được gọi | `supports()` không khớp class Authentication hoặc provider chưa đăng ký | Kiểm tra token class và `authenticationProvider(...)` |
| Provider custom chặn provider mặc định | Provider custom nhận quá rộng hoặc list provider bị thay sai | Thu hẹp `supports()` và giữ provider mặc định |
| Client bị `unauthorized_client` | `RegisteredClient` không đăng ký grant type | Thêm đúng `AuthorizationGrantType` theo policy |
| `invalid_grant` dù code có vẻ đúng | Code hết hạn, đã dùng, sai client binding hoặc sai audience | Kiểm tra lifecycle và binding của grant |
| `invalid_scope` | Custom validator bỏ scope hoặc provider không kiểm tra scope client | Giữ default validator hoặc viết policy đầy đủ |
| Authorization redirect URI không được chấp nhận | Validator custom không khớp chính xác URI đăng ký | Dùng exact matching và kiểm tra registration |
| UserInfo thiếu claim | Scope/consent không cho phép hoặc mapper không map claim | Kiểm tra Access Token scopes và mapper |
| UserInfo `sub` không khớp | Mapper lấy subject từ nguồn profile khác | Khóa `sub` theo ID Token/authorization hiện tại |
| Response Token Endpoint sai schema | Custom success handler tự serialize body không đúng chuẩn | Giữ response converter/schema và cache headers |
| Error trả HTTP 200 | Custom error handler ghi response status sai | Dùng HTTP status và OAuth error mapping phù hợp |
| Consent page lặp lại | Không gửi đúng client_id/state/scope hoặc consent không được lưu | Kiểm tra form POST và `OAuth2AuthorizationConsentService` |
| Extension hoạt động local nhưng lỗi cluster | Một instance thiếu provider/module hoặc version khác | Đồng bộ artifact/configuration giữa các node |
| Upgrade compile lỗi | API configurer hoặc signature method thay đổi | Đọc Javadoc và migration guide đúng version |

### 10.1. Phân biệt lỗi request và lỗi provider

- **Request parsing:** HTTP parameter thiếu, lặp hoặc sai định dạng; sửa converter.
- **Authentication/grant validation:** client, grant credential, scope hoặc authorization không hợp lệ; sửa provider/validator.
- **Token generation/persistence:** token generator hoặc authorization service lỗi; sửa dependency và transaction.
- **Response mapping:** status/header/body không đúng; sửa success/error handler.

Không xử lý lỗi của một tầng bằng cách bỏ qua kiểm tra ở tầng khác.

## 11. Nguyên tắc bảo mật và vận hành

### 11.1. Giữ nguyên protocol invariant

Extension point cho phép tùy chỉnh logic, nhưng mọi extension vẫn phải giữ các invariant của giao thức:

- client authentication được xác minh trước khi xử lý grant cần client authentication;
- redirect URI được so khớp chính xác với URI đã đăng ký;
- scope không vượt quyền client, user consent hoặc policy;
- authorization code và custom grant credential phải chống replay;
- token có issuer, audience, thời hạn, subject và claims phù hợp;
- revocation/introspection nhìn thấy trạng thái token đã lưu;
- response success/error đúng chuẩn OAuth2/OIDC.

### 11.2. Không xóa mặc định nếu không thay thế có chủ đích

Các danh sách `authenticationProviders(...)` và `...Converters(...)` có thể chứa nhiều thành phần mặc định. Khi dùng `clear()` hoặc remove, hãy ghi rõ lý do và kiểm thử tất cả grant/flow liên quan. Một converter/provider bị xóa có thể làm Authorization Code, Refresh Token, Client Credentials, Device Code hoặc Token Exchange ngừng hoạt động.

### 11.3. Kiểm soát input và secret

- Giới hạn kích thước request và số lượng parameter.
- Từ chối parameter trùng ở nơi protocol yêu cầu một giá trị duy nhất.
- Không ghi raw authorization code, refresh token, access token hoặc client secret vào log.
- Không tin additional parameter chỉ vì nó được converter đưa vào map.
- Validate tenant/client binding ở provider.
- Dùng transaction hoặc thao tác consume atomic cho credential one-time.
- Giới hạn thời gian xử lý và external service call trong provider.

### 11.4. Quan sát và audit

Ghi nhận:

- endpoint và extension name;
- request correlation ID;
- client ID đã xác thực;
- grant type và outcome category;
- validation failure category;
- provider/token generator/persistence latency;
- version ứng dụng và extension.

Không ghi token value, authorization code, raw consent details hoặc PII không cần thiết. Dùng metric label có cardinality thấp; không đưa user ID hoặc token vào metric label.

### 11.5. Versioning và triển khai

Extension cần được triển khai đồng bộ với Spring Authorization Server version. Trong cluster:

- mọi node phải có cùng converter/provider và cùng grant policy;
- client registration phải được đồng bộ trước khi bật grant;
- database schema và authorization service phải tương thích;
- rolling deployment phải hỗ trợ đọc trạng thái do version trước ghi;
- nếu đổi URI grant type hoặc request contract, version hóa contract và có thời gian chuyển tiếp.

Không coi internal implementation class hoặc method protected là SPI công khai. Dùng API configurer, public interface và public context được tài liệu hóa; kiểm tra Javadoc khi nâng version.

## 12. Checklist production và tài liệu đối chiếu

### 12.1. Checklist trước khi phát hành extension

- [ ] Đã xác định endpoint và extension point hẹp nhất phù hợp.
- [ ] Extension dùng public API của đúng Spring Authorization Server version.
- [ ] `AuthenticationConverter` chỉ nhận đúng loại request và trả `null` cho loại khác.
- [ ] Converter kiểm tra parameter bắt buộc, parameter lặp và kích thước input.
- [ ] `AuthenticationProvider.supports()` chỉ nhận đúng Authentication type.
- [ ] Provider xác minh client, grant, scope, expiry, audience và replay.
- [ ] Custom validator giữ các validator mặc định không có chủ đích thay đổi.
- [ ] Success handler giữ đúng schema, status và cache/security headers.
- [ ] Error handler không lộ stack trace, secret hoặc internal details.
- [ ] Custom grant được khai báo trong `RegisteredClient` đúng client.
- [ ] Token generator và authorization service được dùng theo lifecycle chuẩn.
- [ ] Có unit test cho converter/provider và integration test cho endpoint.
- [ ] Có regression test cho các grant/endpoint chuẩn.
- [ ] Có test cluster/version compatibility.
- [ ] Có metrics, audit và correlation ID.
- [ ] Không log credential hoặc PII không cần thiết.

### Bản đồ ghi nhớ

```text
OAuth2AuthorizationServerConfigurer
        |
        +--> Endpoint Configurer
                 |
                 v
             Endpoint Filter
                 |
                 v
          AuthenticationConverter
                 |
                 v
          Authentication Token
                 |
                 v
          AuthenticationProvider
                 |
          +------+------+
          |             |
          v             v
     Authorization   TokenGenerator
        Service          |
          |              v
          +--------> Authentication result
                          |
                   +------+------+
                   |             |
                   v             v
              SuccessHandler  ErrorHandler
                   |             |
                   v             v
              Protocol response
```

**Điểm cần nhớ:** Spring Authorization Server cho phép tùy chỉnh endpoint qua configurer công khai. Converter xử lý HTTP request thành Authentication; provider xác minh và thực hiện nghiệp vụ; success/error handler trả response protocol. Custom grant cần converter, provider và grant type được đăng ký ở client. Với validation, hãy giữ các kiểm tra mặc định không có chủ đích thay đổi. Với UserInfo, ưu tiên `userInfoMapper` nếu chỉ cần thay claims. Mọi extension phải giữ protocol invariant, có regression test và triển khai đồng nhất giữa các instance.

## Tài liệu chuẩn để đối chiếu

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): extension point của Authorization, PAR, Device, Token, Introspection, Revocation, OIDC UserInfo và Client Registration endpoints.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer`, component dùng chung và cấu hình `SecurityFilterChain`.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): converter/provider/handler và consent page.
- [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): access token request converters, providers và response handlers.
- [Spring Authorization Server 1.5.8 — OAuth2ClientAuthenticationConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2ClientAuthenticationConfigurer.html): client credential converters, providers và handlers.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): custom grant `AuthenticationConverter`, `AuthenticationProvider` và Token Endpoint.
- [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): custom `userInfoMapper` và claims theo authorization context.
- [Spring Authorization Server 1.5.8 — OidcUserInfoEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): request converter, provider, mapper và handlers.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authorization grant, token endpoint, error response và extension grant.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): tham chiếu khi extension có liên quan đăng ký client động.
