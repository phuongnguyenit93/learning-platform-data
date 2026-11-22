# Tùy chỉnh metadata converter, provider và chính sách đăng ký

OpenID Connect Dynamic Client Registration (DCR) cho phép một Relying Party (RP) gửi metadata của chính nó tới OpenID Provider (OP) để được cấp `client_id` và thông tin cần thiết cho các lần tương tác tiếp theo. Thay vì nhập cấu hình client thủ công cho từng lần triển khai, tổ chức có thể tự động hóa onboarding, quản lý redirect URI, token endpoint authentication method, scopes và những metadata riêng của nền tảng.

Trong Spring Authorization Server, DCR được triển khai qua **OpenID Connect Client Registration Endpoint**. Endpoint này mặc định bị tắt. Khi bật, `OidcClientRegistrationEndpointConfigurer` cho phép tùy chỉnh request converter, authentication provider, response handler và error handler. Các provider mặc định lại có những converter riêng để chuyển `OidcClientRegistration` thành `RegisteredClient` và chuyển ngược lại.

**Tùy chỉnh metadata converter, provider và chính sách đăng ký** là việc thiết kế nhất quán cả ba phần: dữ liệu client gửi lên, cách Authorization Server lưu dữ liệu vào registration, và cách server trả lại đúng metadata trong response/Client Read. Đồng thời, server phải kiểm tra quyền đăng ký, giới hạn metadata được chấp nhận và bảo vệ các endpoint khỏi client không được phép.

Bài học thuộc chương **Đăng ký client động** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.

Sau bài học, bạn có thể:

- Giải thích luồng OIDC Dynamic Client Registration và Client Read.
- Bật `clientRegistrationEndpoint` bằng `OidcClientRegistrationEndpointConfigurer`.
- Phân biệt HTTP request converter với metadata converters của provider.
- Tùy chỉnh `OidcClientRegistrationAuthenticationProvider` và `OidcClientConfigurationAuthenticationProvider`.
- Ánh xạ metadata mở rộng vào `ClientSettings` và trả lại qua Client Registration/Client Read.
- Bảo toàn validation mặc định cho redirect URI, post-logout redirect URI và `jwks_uri`.
- Xây dựng allowlist scope, grant type và token endpoint authentication method.
- Phân biệt Initial Access Token với Registration Access Token.
- Thiết kế chính sách protected registration, quota, audit, secret handling và vòng đời client.
- Kiểm thử đăng ký, đọc lại, metadata round-trip và các trường hợp bị từ chối.

## 1. Dynamic Client Registration giải quyết vấn đề gì?

Một Authorization Server thường cần lưu thông tin cho mỗi OAuth/OIDC client:

- `client_id` và có thể có `client_secret`;
- redirect URIs và post-logout redirect URIs;
- grant types và response types;
- token endpoint authentication method;
- scopes mà client được phép yêu cầu;
- JWK Set URL hoặc thuật toán ký ID Token;
- tên hiển thị, logo, thông tin liên hệ và metadata khác.

Nếu mọi client đều được tạo thủ công, onboarding nhiều tenant, môi trường triển khai hoặc ứng dụng SaaS có thể tốn thời gian và dễ sai cấu hình. DCR cho phép client/developer gửi metadata tới Registration Endpoint để OP đánh giá và tạo registration.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    autonumber
    participant D as Client Developer / Registrar
    participant AS as Authorization Server
    participant DB as RegisteredClientRepository
    participant C as OIDC Client

    D->>AS: Xin Initial Access Token
    AS-->>D: Initial Access Token (client.create)
    D->>AS: POST Client Registration + Bearer token
    AS->>AS: Xác thực registrar và kiểm tra metadata
    AS->>AS: OidcClientRegistration -> RegisteredClient
    AS->>DB: Lưu RegisteredClient
    AS-->>D: client_id, credentials, metadata, registration_access_token, registration_client_uri
    C->>AS: GET registration_client_uri + Registration Access Token
    AS->>DB: Tìm registration và xác minh quyền đọc
    AS-->>C: Client Registration metadata
~~~

DCR có thể được triển khai theo mô hình open registration hoặc protected registration. Trong môi trường doanh nghiệp, protected registration thường phù hợp hơn: chỉ registrar/developer đã được cấp Initial Access Token mới có quyền tạo client. DCR không đồng nghĩa mọi người dùng Internet đều được phép tạo client mới.

### 1.1. DCR không phải Client Authentication

Ba hoạt động khác nhau:

| Hoạt động | Mục đích | Credential/quyền liên quan |
| --- | --- | --- |
| Dynamic Client Registration | Tạo registration mới cho client. | Initial Access Token với quyền `client.create` trong cấu hình Spring Authorization Server. |
| Client Read / Client Configuration | Đọc metadata của registration đã tạo. | Registration Access Token gắn với client và quyền `client.read`. |
| OAuth Client Authentication | Xác thực client khi gọi Token/Introspection/Revocation Endpoint. | `client_secret_basic`, `private_key_jwt`, mTLS hoặc phương thức đã đăng ký. |

Một client mới nhận `client_id` qua DCR chưa có nghĩa nó đã được xác thực trong các token request. Phương thức xác thực và grant types của client vẫn phải được cấu hình, lưu và kiểm tra theo policy.

## 2. Client Registration Endpoint và Client Read Endpoint

OIDC Dynamic Client Registration 1.0 định nghĩa hai thao tác quan trọng:

- **Client Registration Request:** client gửi HTTP POST cùng metadata để đăng ký.
- **Client Read Request:** client gửi HTTP GET tới Client Configuration Endpoint để đọc metadata đã đăng ký.

Trong Spring Authorization Server 1.5.8, `OidcClientRegistrationEndpointFilter` xử lý cả Client Registration request và Client Read request. Filter mặc định sử dụng hai provider:

| Provider | Vai trò |
| --- | --- |
| `OidcClientRegistrationAuthenticationProvider` | Xử lý việc tạo registration, chuyển metadata thành `RegisteredClient`, lưu client và tạo response. |
| `OidcClientConfigurationAuthenticationProvider` | Xử lý Client Read, tìm registration đã tồn tại và chuyển thành `OidcClientRegistration` response. |

Client Registration Endpoint mặc định là `/connect/register`; có thể đổi bằng `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)`.

**Không nhầm Client Read với toàn bộ Dynamic Client Management.** DCR/Client Configuration specification có các thao tác quản lý registration rộng hơn, nhưng phần endpoint Spring Authorization Server 1.5.8 được mô tả ở đây xử lý đăng ký và đọc thông tin. Không giả định PUT/PATCH/DELETE hoặc toàn bộ RFC 7592 lifecycle operations tự động được bật chỉ vì endpoint registration đã hoạt động.

## 3. Bật Client Registration Endpoint trong Spring Authorization Server

OIDC endpoints được kích hoạt qua `oidc(...)`. Client Registration Endpoint cần được bật tường minh bằng `clientRegistrationEndpoint(...)`.

Ví dụ theo Spring Authorization Server 1.5.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .oidc(oidc ->
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

Đây là phần bật endpoint. Ứng dụng thực tế còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, `AuthorizationServerSettings`, JWK source và các filter chain tương ứng.

### 3.1. JwtDecoder là dependency bắt buộc

Spring Authorization Server sử dụng OAuth2 Resource Server support để xác minh Bearer access token tại Client Registration/Client Read Endpoint. Theo cấu hình hiện hành, cần có `JwtDecoder` bean:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Các import liên quan:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import com.nimbusds.jose.jwk.source.JWKSource;
~~~

Nếu endpoint trả 401 dù converter/provider đã cấu hình đúng, hãy kiểm tra Bearer token, `JwtDecoder`, issuer/signature validation và filter chain thực tế.

### 3.2. Cấu hình endpoint path

Có thể thay path mặc định:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .oidcClientRegistrationEndpoint("/connect/v1/register")
        .build();
}
~~~

Discovery metadata phải công bố đúng `registration_endpoint`. Client cần dùng URL mà OP công bố hoặc URL đã cấu hình tin cậy; không tự ghép host/path từ dữ liệu không đáng tin.

## 4. Các extension points của OidcClientRegistrationEndpointConfigurer

`OidcClientRegistrationEndpointConfigurer` cấu hình `OidcClientRegistrationEndpointFilter` và cung cấp các điểm mở rộng:

~~~mermaid
flowchart LR
    HTTP["HTTP POST / GET"] --> CONV["Request Converter"]
    CONV --> AUTH["OidcClientRegistrationAuthenticationToken"]
    AUTH --> PROVIDERS["AuthenticationManager"]
    PROVIDERS --> REG["Registration Provider"]
    PROVIDERS --> READ["Configuration Provider"]
    REG --> SAVE["RegisteredClientRepository"]
    SAVE --> RESPONSE["Client Registration Response"]
    READ --> RESPONSE
    RESPONSE --> SUCCESS["Client Registration Response Handler"]
    PROVIDERS -->|OAuth error| ERROR["Error Response Handler"]
~~~

| API | Vai trò | Khi nào cần tùy biến |
| --- | --- | --- |
| `clientRegistrationRequestConverter(...)` | Thêm `AuthenticationConverter` để chuyển HTTP request thành `OidcClientRegistrationAuthenticationToken`. | Khi cần định dạng request đặc biệt hoặc thêm ngữ cảnh được kiểm soát. |
| `clientRegistrationRequestConverters(...)` | Truy cập danh sách converter mặc định và converter bổ sung. | Khi cần điều chỉnh thứ tự hoặc thay converter cụ thể. |
| `authenticationProvider(...)` | Thêm provider xử lý authentication request. | Khi có provider riêng cho một loại registration. |
| `authenticationProviders(...)` | Truy cập danh sách provider mặc định để cấu hình/thêm/bỏ. | Khi cần gắn validator hoặc metadata converter vào provider mặc định. |
| `clientRegistrationResponseHandler(...)` | Xử lý response thành công cho Registration hoặc Client Read. | Khi cần response handling/audit tùy chỉnh. |
| `errorResponseHandler(...)` | Xử lý OAuth error response. | Khi cần telemetry hoặc error formatting theo chính sách. |

Mặc định filter dùng:

- `OidcClientRegistrationAuthenticationConverter`;
- `OidcClientRegistrationAuthenticationProvider`;
- `OidcClientConfigurationAuthenticationProvider`;
- success handler nội bộ trả `OidcClientRegistration`;
- failure handler nội bộ trả `OAuth2Error`.

**Không cần viết request converter mới chỉ vì muốn lưu thêm metadata.** Nếu JSON đã được đọc thành `OidcClientRegistration` với claims mở rộng, có thể giữ request converter mặc định và tùy chỉnh các metadata converters ở provider. Đây là đường đi đơn giản hơn và ít nguy cơ phá vỡ protocol parsing.

## 5. Phân biệt các lớp converter

Có nhiều converter trong DCR; chúng xử lý các ranh giới dữ liệu khác nhau.

| Converter | Hướng chuyển đổi | Nơi sử dụng |
| --- | --- | --- |
| `OidcClientRegistrationAuthenticationConverter` | `HttpServletRequest` → `OidcClientRegistrationAuthenticationToken` | Endpoint filter, pre-processing. |
| `OidcClientRegistrationHttpMessageConverter` | JSON/map ↔ `OidcClientRegistration` | HTTP message serialization/deserialization. |
| `OidcClientRegistrationRegisteredClientConverter` | `OidcClientRegistration` → `RegisteredClient` | Registration provider, tạo client để lưu. |
| `RegisteredClientOidcClientRegistrationConverter` | `RegisteredClient` → `OidcClientRegistration` | Registration response và Client Read response. |

Có thể nhớ bằng sơ đồ:

~~~mermaid
flowchart TD
    JSON["JSON metadata từ client"] --> HTTP["HTTP Message Converter"]
    HTTP --> OIDC["OidcClientRegistration"]
    OIDC --> REGCONV["OidcClientRegistrationRegisteredClientConverter"]
    REGCONV --> RC["RegisteredClient"]
    RC --> REPO["RegisteredClientRepository"]
    REPO --> BACK["RegisteredClientOidcClientRegistrationConverter"]
    BACK --> RESPONSE["OidcClientRegistration response"]
    RESPONSE --> JSONOUT["JSON trả client"]
~~~

Hai converter provider-level là phần thường cần mở rộng khi lưu metadata riêng:

- `setRegisteredClientConverter(...)` nhận converter `OidcClientRegistration` → `RegisteredClient`.
- `setClientRegistrationConverter(...)` nhận converter `RegisteredClient` → `OidcClientRegistration`.

Nếu metadata custom chỉ được đọc nhưng không được lưu, nó mất sau khi registration kết thúc. Nếu metadata được lưu nhưng converter response không đọc lại, nó mất trong response và Client Read. Cần thực hiện **round-trip** cả hai chiều.

## 6. Lưu custom metadata trong RegisteredClient

`RegisteredClient` có các thuộc tính chuẩn như `clientId`, `clientSecret`, redirect URIs, grant types, scopes và client authentication methods. Một số metadata OIDC như `logo_uri` hoặc `contacts` không có property chuyên biệt tương ứng trong `RegisteredClient`.

Một cách phù hợp là lưu metadata mở rộng trong `ClientSettings` bằng custom setting keys. Trong ví dụ của bài, `logo_uri` và `contacts` là metadata client được OIDC DCR định nghĩa; chúng được xử lý như custom settings đối với mô hình `RegisteredClient` vì model này không có property chuyên biệt tương ứng. Các trường riêng của tổ chức như `tenant_code` phải được server xác minh hoặc tự gán, không được tin như một claim tự khai.

Các keys minh họa:
- `logo_uri`: URL logo của client;
- `contacts`: danh sách liên hệ vận hành;
- `tenant_code`: mã tenant nội bộ do server cấp hoặc xác minh;
- `registration_source`: nguồn onboarding được server xác định.

Không lưu những giá trị nhạy cảm tùy tiện vào metadata hiển thị công khai. Chỉ giữ các trường cần thiết và quyết định rõ trường nào được trả lại cho client.

### 6.1. Metadata converter từ OidcClientRegistration sang RegisteredClient

Converter đầu vào nên delegate cho converter chuẩn trước, sau đó bổ sung các setting được allowlist:

~~~java
public final class CustomRegisteredClientConverter
        implements Converter<OidcClientRegistration, RegisteredClient> {

    private static final Set<String> CUSTOM_METADATA =
        Set.of("logo_uri", "contacts");

    private final OidcClientRegistrationRegisteredClientConverter delegate =
        new OidcClientRegistrationRegisteredClientConverter();

    @Override
    public RegisteredClient convert(OidcClientRegistration registration) {
        RegisteredClient registeredClient = this.delegate.convert(registration);

        ClientSettings.Builder settings = ClientSettings.withSettings(
            registeredClient.getClientSettings().getSettings()
        );

        registration.getClaims().forEach((name, value) -> {
            if (CUSTOM_METADATA.contains(name) && value != null) {
                settings.setting(name, value);
            }
        });

        return RegisteredClient.from(registeredClient)
            .clientSettings(settings.build())
            .build();
    }
}
~~~

Đoạn code trên minh họa cơ chế lưu. Trước khi gọi converter, validator phải xác minh kiểu và nội dung của `logo_uri`, `contacts`; không tin giá trị chỉ vì nó nằm trong JSON metadata. Nếu `contacts` phải là danh sách chuỗi, hãy từ chối object hoặc kiểu dữ liệu khác thay vì ép kiểu không kiểm soát.

### 6.2. Metadata converter từ RegisteredClient sang OidcClientRegistration

Converter chiều ngược lại bắt đầu từ response chuẩn rồi thêm metadata đã lưu:

~~~java
public final class CustomClientRegistrationConverter
        implements Converter<RegisteredClient, OidcClientRegistration> {

    private static final Set<String> CUSTOM_METADATA =
        Set.of("logo_uri", "contacts");

    private final RegisteredClientOidcClientRegistrationConverter delegate =
        new RegisteredClientOidcClientRegistrationConverter();

    @Override
    public OidcClientRegistration convert(RegisteredClient registeredClient) {
        OidcClientRegistration base = this.delegate.convert(registeredClient);
        Map<String, Object> claims = new HashMap<>(base.getClaims());

        ClientSettings settings = registeredClient.getClientSettings();
        for (String name : CUSTOM_METADATA) {
            Object value = settings.getSetting(name);
            if (value != null) {
                claims.put(name, value);
            }
        }

        return OidcClientRegistration.withClaims(claims).build();
    }
}
~~~

Converter này được dùng cho cả response sau khi đăng ký và Client Read. Dùng `new HashMap<>(base.getClaims())` để giữ lại các metadata chuẩn đã được converter mặc định tạo ra; không dựng một map mới chỉ chứa custom fields vì như vậy sẽ làm mất `client_id`, `redirect_uris`, `grant_types` và những trường khác.

### 6.3. Đăng ký cả hai converter vào provider

Cấu hình `OidcClientRegistrationAuthenticationProvider` và `OidcClientConfigurationAuthenticationProvider`:

~~~java
public final class CustomClientMetadataConfig {

    public static Consumer<List<AuthenticationProvider>>
            configureCustomClientMetadataConverters() {

        Converter<OidcClientRegistration, RegisteredClient> toRegisteredClient =
            new CustomRegisteredClientConverter();

        Converter<RegisteredClient, OidcClientRegistration> toClientRegistration =
            new CustomClientRegistrationConverter();

        return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
                registrationProvider.setRegisteredClientConverter(toRegisteredClient);
                registrationProvider.setClientRegistrationConverter(toClientRegistration);
            }

            if (provider instanceof OidcClientConfigurationAuthenticationProvider configurationProvider) {
                configurationProvider.setClientRegistrationConverter(toClientRegistration);
            }
        });
    }
}
~~~

Các provider có trách nhiệm khác nhau:

- Registration provider dùng converter chiều vào để tạo `RegisteredClient`.
- Registration provider dùng converter chiều ra để tạo response sau POST.
- Configuration provider dùng converter chiều ra để trả response cho Client Read.

Nếu chỉ cấu hình converter ở Registration provider, client có thể nhận metadata ngay sau POST nhưng không thấy metadata đó khi GET registration về sau.

## 7. Cấu hình endpoint với metadata converters

Có thể kết hợp provider customizer vào `authenticationProviders(...)`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(oidc ->
                oidc.clientRegistrationEndpoint(endpoint ->
                    endpoint.authenticationProviders(
                        CustomClientMetadataConfig
                            .configureCustomClientMetadataConverters()
                    )
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

Ví dụ này tập trung vào việc gắn metadata converters. Hãy bổ sung validator policy của tổ chức vào cùng consumer hoặc compose các consumer theo thứ tự rõ ràng. Không tạo thêm một Authorization Server filter chain trùng matcher chỉ để cài một converter.

## 8. Tùy chỉnh AuthenticationProvider và validation policy

`OidcClientRegistrationAuthenticationProvider` có thể tùy chỉnh bằng:

- `setRegisteredClientConverter(...)`;
- `setClientRegistrationConverter(...)`;
- `setAuthenticationValidator(...)`;
- `setPasswordEncoder(...)`.

`OidcClientConfigurationAuthenticationProvider` cung cấp `setClientRegistrationConverter(...)` để thay đổi dữ liệu trả về trong Client Read.

Validator nhận `OidcClientRegistrationAuthenticationContext` và phải ném `OAuth2AuthenticationException` khi request metadata không hợp lệ.

### 8.1. Các validator mặc định trong Spring Authorization Server 1.5.8

`OidcClientRegistrationAuthenticationValidator` kiểm tra các trường:

| Validator | Ý nghĩa |
| --- | --- |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Từ chối redirect URI có fragment, thiếu scheme hoặc dùng scheme không an toàn như `javascript:`, `data:` và `vbscript:`. |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Áp dụng quy tắc tương tự cho post-logout redirect URI. |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Yêu cầu `jwks_uri` dùng HTTPS. |
| `DEFAULT_SCOPE_VALIDATOR` | Từ chối request có giá trị scope không rỗng theo policy mặc định. |

Các `SIMPLE_*_VALIDATOR` tồn tại để tương thích hành vi cũ:

- `SIMPLE_REDIRECT_URI_VALIDATOR` chủ yếu chỉ kiểm tra fragment.
- `SIMPLE_POST_LOGOUT_REDIRECT_URI_VALIDATOR` cũng là kiểm tra lỏng.
- `SIMPLE_JWK_SET_URI_VALIDATOR` không thực hiện validation HTTPS.
- `SIMPLE_SCOPE_VALIDATOR` chấp nhận mọi scope.

Các validator `SIMPLE_*` có thể cho phép metadata nguy hiểm như redirect URI không an toàn, `jwks_uri` dẫn tới endpoint nội bộ hoặc scope tùy ý. Chỉ sử dụng khi có yêu cầu tương thích cụ thể, đánh giá rủi ro và biện pháp thay thế rõ ràng.

### 8.2. Vì sao không dùng SIMPLE_SCOPE_VALIDATOR một cách máy móc?

Trong Spring Authorization Server 1.5.8, `DEFAULT_SCOPE_VALIDATOR` từ chối scope không rỗng. Nếu deployment muốn client đăng ký các scope, phải thay phần scope validation bằng policy riêng. Ví dụ cho phép một tập scope có giới hạn:

~~~java
private static final Set<String> ALLOWED_SCOPES =
    Set.of("openid", "profile", "email", "orders.read");

private static Consumer<OidcClientRegistrationAuthenticationContext>
        allowedScopeValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        List<String> requestedScopes = registration.getScopes();
        if (requestedScopes == null || requestedScopes.isEmpty()) {
            return;
        }

        if (!ALLOWED_SCOPES.containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_client_metadata",
                    "The registration request contains an unsupported scope",
                    null
                )
            );
        }
    };
}
~~~

Ví dụ này cho phép scope trong allowlist. Trong hệ thống nhiều tenant, allowlist có thể được tính theo registrar, software statement hoặc tenant policy; không nên dùng một danh sách toàn cục nếu mỗi nhóm registrar có quyền khác nhau.

### 8.3. Kết hợp URI validators mặc định với scope allowlist

Khi gọi `setAuthenticationValidator(...)`, validator mới thay thế validator hiện tại. Vì vậy, phải compose các validator an toàn cần giữ lại:

~~~java
private static Consumer<List<AuthenticationProvider>>
        configureRegistrationValidators() {

    Consumer<OidcClientRegistrationAuthenticationContext> validator =
        OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
            .andThen(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR
            )
            .andThen(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_JWK_SET_URI_VALIDATOR
            )
            .andThen(allowedScopeValidator())
            .andThen(clientCapabilityValidator())
            .andThen(customMetadataValidator());

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(validator);
        }
    });
}
~~~

Ở đây không gọi `DEFAULT_SCOPE_VALIDATOR`, vì validator đó từ chối mọi scope không rỗng. Scope được kiểm tra bởi allowlist riêng. Các validator URI nghiêm ngặt vẫn được giữ lại.

Có thể ghép hai cấu hình:

~~~java
.authenticationProviders(
    configureRegistrationValidators()
        .andThen(
            CustomClientMetadataConfig
                .configureCustomClientMetadataConverters()
        )
)
~~~

Đảm bảo mỗi provider chỉ được cấu hình một lần cho từng concern và tránh customizer sau ghi đè validator vừa thiết lập trước đó.

## 9. Chính sách cho grant types, response types và authentication methods

Scope không phải metadata duy nhất cần kiểm soát. Client có thể gửi `grant_types`, `response_types` và `token_endpoint_auth_method`; các giá trị này ảnh hưởng trực tiếp tới cách client được phép hoạt động.

Ví dụ chính sách:

| Metadata | Policy minh họa |
| --- | --- |
| `grant_types` | Chỉ cho phép `authorization_code`, `refresh_token` và `client_credentials` theo loại client. |
| `response_types` | Với web OIDC client, chỉ cho phép `code`. |
| `token_endpoint_auth_method` | Cho phép `client_secret_basic`, `private_key_jwt` hoặc `none` tùy loại client. |
| `redirect_uris` | Exact allowlist theo từng client; HTTPS cho web clients, ngoại lệ loopback theo native-app policy. |
| `post_logout_redirect_uris` | Exact allowlist riêng, không tái sử dụng tự động redirect URIs. |
| `jwks_uri` | HTTPS và host/network policy được kiểm soát. |
| `scope` | Allowlist theo tenant, product hoặc registrar. |

Một validator bổ sung có thể đọc metadata qua `context.getAuthentication().getClientRegistration()` và kiểm tra grant/auth method trước khi provider lưu client:

~~~java
private static final Set<String> ALLOWED_GRANTS =
    Set.of("authorization_code", "refresh_token");

private static final Set<String> ALLOWED_AUTH_METHODS =
    Set.of("client_secret_basic", "private_key_jwt", "none");

private static Consumer<OidcClientRegistrationAuthenticationContext>
        clientCapabilityValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        List<String> grantTypes = registration.getGrantTypes();
        if (grantTypes != null && !ALLOWED_GRANTS.containsAll(grantTypes)) {
            throw invalidClientMetadata("Unsupported grant_types");
        }

        String authenticationMethod =
            registration.getTokenEndpointAuthenticationMethod();

        if (authenticationMethod != null
                && !ALLOWED_AUTH_METHODS.contains(authenticationMethod)) {
            throw invalidClientMetadata(
                "Unsupported token_endpoint_auth_method"
            );
        }
    };
}

private static OAuth2AuthenticationException invalidClientMetadata(
        String description) {

    return new OAuth2AuthenticationException(
        new OAuth2Error("invalid_client_metadata", description, null)
    );
}
~~~

Đây là policy minh họa. Trong production, allowlist phải phụ thuộc registrar/client class. Ví dụ `none` chỉ dành cho public clients; `client_secret_basic` và `private_key_jwt` dành cho confidential clients theo quy trình cấp credential tương ứng. Không cho client tự khai `token_endpoint_auth_method=none` để né xác thực nếu tổ chức chỉ chấp nhận confidential clients.

### 9.1. Bắt buộc PKCE cho public clients

Với public client, cần yêu cầu PKCE cho Authorization Code flow. Khi chuyển metadata thành `RegisteredClient`, có thể áp dụng policy bằng `ClientSettings.requireProofKey(true)` cho nhóm client được xác định là public. Không chỉ dựa vào metadata `token_endpoint_auth_method` chưa được xác minh; kết hợp loại ứng dụng/registrar policy và validation.

Nếu public clients không được phép dùng `client_credentials`, hãy từ chối grant đó trong registration validator. Việc bỏ một grant khỏi response metadata mà vẫn lưu grant đó trong `RegisteredClient` là cấu hình không nhất quán.

## 10. Xây dựng validator cho custom metadata

Custom metadata cũng là input không đáng tin. Ví dụ `logo_uri` và `contacts`:

| Field | Validation nên có |
| --- | --- |
| `logo_uri` | Phải là HTTPS URL, giới hạn host/domain theo policy, giới hạn độ dài và không cho scheme nguy hiểm. |
| `contacts` | Phải là danh sách string, giới hạn số phần tử và độ dài, chuẩn hóa email/URI theo format mà ứng dụng yêu cầu. |
| `tenant_code` | Không nhận tenant quyền cao do client tự khai; lấy từ registrar identity hoặc kiểm tra tenant membership. |
| `software_id` | Chỉ chấp nhận giá trị trong danh mục software đã được tổ chức tin cậy. |

Ví dụ kiểm tra metadata mở rộng:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customMetadataValidator() {

    return context -> {
        OidcClientRegistration registration =
            context.getAuthentication().getClientRegistration();

        String logoUri = registration.getClaimAsString("logo_uri");
        if (logoUri != null) {
            URI uri;
            try {
                uri = URI.create(logoUri);
            }
            catch (IllegalArgumentException ex) {
                throw invalidClientMetadata("Invalid logo_uri");
            }

            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null) {
                throw invalidClientMetadata("Unsafe logo_uri");
            }
        }

        Object contacts = registration.getClaims().get("contacts");
        if (contacts != null) {
            if (!(contacts instanceof List<?> values)
                    || values.size() > 10
                    || values.stream().anyMatch(value ->
                        !(value instanceof String text)
                            || text.isBlank()
                            || text.length() > 254)) {
                throw invalidClientMetadata("Invalid contacts");
            }
        }
    };
}
~~~

Ví dụ chỉ kiểm tra cấu trúc cơ bản. Nếu server hoặc trang quản trị sẽ tải logo từ URL, cần chống SSRF: chặn IP private/loopback/link-local, kiểm soát DNS rebinding và redirect, giới hạn egress, timeout và kích thước tải. Cách an toàn hơn là chỉ hiển thị logo từ host đã allowlist hoặc proxy qua dịch vụ media có kiểm soát.

## 11. Đăng ký registrar client

Trong Spring Authorization Server, một client đã được đăng ký trước đóng vai trò registrar để gọi Client Registration Endpoint.

Registrar cần:

- Grant `client_credentials` để lấy access token.
- Scope `client.create` để tạo registration.
- Scope `client.read` nếu cần đọc lại registration.

Ví dụ:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {
    RegisteredClient registrar = RegisteredClient
        .withId("registrar-internal-id")
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode("replace-with-secret"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
~~~

Ví dụ dùng in-memory repository để dễ hiểu. Production nên dùng persistent `RegisteredClientRepository` và secret management phù hợp; không hardcode secret trong source hoặc cấu hình công khai.

### 11.1. Lấy Initial Access Token

Registration request cần Initial Access Token có đúng scope `client.create` theo cấu hình Spring Authorization Server. Token không được có thêm scope khác.

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <BASE64_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Ví dụ request trên lấy access token từ registrar client. Trong Spring Authorization Server 1.5.8, Initial Access Token dùng cho lần đăng ký là one-time token: sau khi registration thành công, token này bị invalidated. Không tái sử dụng token đó cho nhiều client.

### 11.2. Initial Access Token và Registration Access Token

Hai token có mục đích khác nhau:

| Token | Được cấp cho | Dùng để | Phạm vi |
| --- | --- | --- | --- |
| Initial Access Token | Registrar/developer đã được phê duyệt. | Gọi Registration Endpoint để tạo client mới. | Có thể được giới hạn theo `client.create`; trong SAS guide token chỉ có scope này và dùng một lần. |
| Registration Access Token | Client vừa được đăng ký. | Gọi Client Configuration Endpoint để đọc metadata của chính registration đó. | Gắn với một client cụ thể; không phải token dùng để tạo client khác. |

Không trả Registration Access Token cho người dùng cuối hoặc log nó trong application log. Nó là bearer credential để đọc thông tin registration và phải được bảo vệ như một secret.

## 12. Gửi Client Registration Request

Ví dụ POST request:

~~~http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer <INITIAL_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json

{
  "client_name": "orders-portal",
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/portal"
  ],
  "post_logout_redirect_uris": [
    "https://orders.example.com/signed-out"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email orders.read",
  "logo_uri": "https://orders.example.com/assets/logo.png",
  "contacts": [
    "platform@example.com"
  ]
}
~~~

Response thành công có thể chứa:

- `client_id`;
- `client_secret` nếu client dùng phương thức cần secret;
- các metadata đã được OP chấp nhận;
- `registration_access_token`;
- `registration_client_uri`.

OP có thể từ chối, thay thế hoặc bổ sung một số metadata theo specification và policy. Client phải sử dụng các giá trị server trả về, không giả định mọi giá trị yêu cầu đều được giữ nguyên.

### 12.1. Client Read

Client dùng `registration_client_uri` và Registration Access Token để đọc registration:

~~~http
GET <REGISTRATION_CLIENT_URI_FROM_RESPONSE> HTTP/1.1
Authorization: Bearer <REGISTRATION_ACCESS_TOKEN>
Accept: application/json
~~~

Trong Spring Authorization Server, Client Read yêu cầu access token có scope `client.read`. Client phải dùng nguyên URL `registration_client_uri` server trả về; không tự ghép URL từ client ID hoặc hostname.

Response Client Read nên giữ các metadata chuẩn và custom metadata đã được lưu. Không trả lại `registration_access_token` như một trường thông tin đọc thông thường nếu protocol/implementation không yêu cầu.

## 13. Tùy chỉnh password encoder và client secret

`OidcClientRegistrationAuthenticationProvider` hỗ trợ `setPasswordEncoder(...)` để encode client secret được tạo trong quá trình registration. Nếu không cấu hình riêng, provider sử dụng `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.

Ví dụ gắn encoder:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

Nếu custom provider hoặc custom registration workflow tự tạo client secret, phải encode trước khi lưu và chỉ trả plaintext secret đúng một lần theo response contract. Không lưu plaintext secret trong `ClientSettings`, custom metadata, audit log hoặc response Client Read.

Với public clients dùng `token_endpoint_auth_method=none`, không phát hành client secret như thể đó là confidential client. Với `private_key_jwt`, lưu JWK Set URL hoặc key reference cần thiết theo policy; không nhận private key của client làm metadata public.

## 14. Chính sách bảo mật cho Dynamic Client Registration

DCR có thể tạo ra client có khả năng xin token tới API của tổ chức. Vì vậy, registration policy phải giới hạn ai được đăng ký và client được phép làm gì.

### 14.1. Ưu tiên protected registration

Trong protected registration:

- Initial Access Token chỉ cấp cho registrar/developer được phê duyệt.
- Token có TTL ngắn và scope tối thiểu `client.create`.
- Token nên dùng một lần nếu mô hình registration cho phép.
- Registrar có quota theo tenant/team.
- Mỗi lần tạo registration có audit event và nguồn yêu cầu.

Open registration có thể cần trong một số hệ sinh thái công khai, nhưng cần rate limit, abuse detection, quota, review và chính sách thu hồi client. Không bật endpoint chỉ vì nó nằm trong OIDC specification.

### 14.2. Redirect URI

Redirect URI là ranh giới bảo mật quan trọng. Nên:

- Từ chối URI không có scheme, URI có fragment và scheme nguy hiểm.
- Dùng HTTPS cho web clients.
- Chỉ cho loopback HTTP trong trường hợp native app theo policy cụ thể.
- So khớp chính xác redirect URI khi xử lý authorization request.
- Không dùng wildcard hoặc prefix match.
- Kiểm tra host/domain ownership nếu mô hình đăng ký yêu cầu.

Validator mặc định trong SAS 1.5.8 kiểm tra các điều kiện an toàn cơ bản. Nó không thay thế quy trình xác minh quyền kiểm soát domain hoặc exact-match validation ở Authorization Endpoint.

### 14.3. JWK Set URI và SSRF

Validator mặc định yêu cầu `jwks_uri` dùng HTTPS. Điều này chưa đủ để bảo vệ mọi deployment: HTTPS URL vẫn có thể trỏ tới địa chỉ nội bộ hoặc dịch vụ metadata trong mạng riêng.

Nếu server tải JWK Set từ URL do client cung cấp, cần:

- Allowlist domain hoặc trust domain theo registrar.
- Chặn loopback, private, link-local và IP đặc biệt.
- Kiểm tra DNS resolution và chống DNS rebinding.
- Giới hạn redirect, timeout, response size và tần suất refresh.
- Không cho phép URL trỏ tới cloud metadata service hoặc control plane nội bộ.

### 14.4. Grant types và scopes

Không cho client tự cấp quyền cho chính nó. `scope` trong registration metadata mô tả phạm vi client muốn sử dụng; OP phải giới hạn theo registrar, tenant, product và API policy.

Tương tự, `grant_types` không nên được chấp nhận vô điều kiện. Ví dụ public client có thể chỉ được phép Authorization Code + PKCE; không tự cấp `client_credentials` cho một SPA.

### 14.5. Logo và thông tin hiển thị

Metadata `client_name`, `logo_uri`, `policy_uri` và `contacts` có thể xuất hiện trên consent page hoặc giao diện quản trị. Một client độc hại có thể giả mạo thương hiệu, dùng logo gây nhầm lẫn hoặc đưa URL tải nội dung nguy hiểm.

Nên:

- Gắn nhãn client chưa được tin cậy.
- Kiểm tra logo host với redirect domain hoặc domain đã xác minh.
- Không render HTML do client gửi.
- Escape text và dùng CSP.
- Không tự động tải logo từ URL tùy ý trên server.
- Có quy trình duyệt metadata nhạy cảm trước khi hiển thị cho End-User.

### 14.6. Quota, duplicate và lifecycle

Đặt giới hạn số registration theo registrar/tenant, tốc độ tạo, số redirect URIs, số scopes và kích thước metadata. Cần có quy trình:

- phát hiện đăng ký trùng;
- thu hồi client bị lạm dụng;
- xoay secret;
- cập nhật metadata theo luồng quản trị hỗ trợ;
- xóa registration hết hạn theo chính sách;
- lưu audit và nguồn phê duyệt.

Đừng dùng `client_name` làm khóa duy nhất. Dùng client ID do server tạo và internal ID ổn định.

## 15. Lỗi thường gặp khi tùy chỉnh provider/converter

### 15.1. Metadata custom có trong response POST nhưng mất khi GET

Registration provider đã được cấu hình converter chiều vào/ra, nhưng `OidcClientConfigurationAuthenticationProvider` chưa được cấu hình converter chiều ra. Dùng chung `CustomClientRegistrationConverter` cho cả hai provider.

### 15.2. Metadata custom mất sau khi lưu

Converter chiều vào không copy claim sang `ClientSettings` hoặc persistence layer không serialize custom setting. Kiểm tra `RegisteredClient` ngay sau khi convert và đọc lại từ repository sau khi lưu.

### 15.3. Metadata response làm mất các field chuẩn

Custom converter tạo `OidcClientRegistration` từ map rỗng thay vì copy `base.getClaims()`. Hãy delegate converter mặc định, copy claims chuẩn rồi thêm custom keys.

### 15.4. Scope registration luôn bị từ chối

SAS 1.5.8 có `DEFAULT_SCOPE_VALIDATOR` từ chối scope không rỗng. Nếu muốn nhận scope, thay phần này bằng allowlist riêng. Đừng chuyển thẳng sang `SIMPLE_SCOPE_VALIDATOR` mà không kiểm soát.

### 15.5. Redirect URI hoặc jwks_uri bị từ chối

Kiểm tra scheme, fragment, HTTPS và chính sách domain. Không tắt strict validator chỉ để làm một registration request lỗi được chấp nhận.

### 15.6. Client registration trả 401

Kiểm tra Initial Access Token, chữ ký/issuer/audience, TTL và Bearer header. Token phải có `client.create` theo yêu cầu của endpoint.

### 15.7. Client Read trả 401/403

Kiểm tra Registration Access Token, `registration_client_uri` và scope `client.read`. Không dùng Initial Access Token để đọc registration sau khi token đã bị consume.

### 15.8. Client Read trả 404 do tự dựng URL

Dùng nguyên `registration_client_uri` trong response. Không tự nối `/connect/register/{client_id}` nếu server đã cung cấp một URL đầy đủ.

### 15.9. Client secret xuất hiện trong log hoặc database plaintext

Kiểm tra `PasswordEncoder`, custom metadata converters, audit serialization và response logging. Secret chỉ xuất hiện trong response đăng ký theo protocol; không ghi lại ở log và không lưu plaintext.

### 15.10. Endpoint trả 404

Kiểm tra `oidc.clientRegistrationEndpoint(...)` đã bật chưa, `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)` có khớp route không, request có đi qua Authorization Server filter chain không và proxy có route endpoint không.

## 16. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Registration endpoint bị tắt | Endpoint không được phục vụ như DCR endpoint. |
| Bật endpoint và gửi POST với Initial Access Token hợp lệ | Tạo `RegisteredClient` và trả registration response. |
| Không gửi access token trong protected registration | Bị từ chối. |
| Token thiếu `client.create` | Bị từ chối. |
| Token có thêm scope ngoài `client.create` trong flow yêu cầu token đơn scope | Bị từ chối. |
| Dùng lại Initial Access Token đã đăng ký thành công | Bị từ chối vì token đã invalidated. |
| GET Client Read với Registration Access Token hợp lệ và `client.read` | Trả metadata registration. |
| GET với token sai hoặc thiếu quyền | Trả lỗi xác thực/authorization phù hợp. |
| Redirect URI có fragment hoặc scheme nguy hiểm | Validator từ chối. |
| Post-logout redirect URI không hợp lệ | Validator từ chối. |
| `jwks_uri` dùng HTTP | Default validator từ chối. |
| Scope ngoài allowlist | Custom scope validator từ chối. |
| Grant type không được policy cho phép | Registration bị từ chối. |
| Authentication method không được policy cho phép | Registration bị từ chối. |
| Metadata `logo_uri` sai scheme | Custom metadata validator từ chối. |
| `contacts` là object thay vì list string | Custom metadata validator từ chối. |
| Metadata custom hợp lệ | Lưu được trong `ClientSettings`. |
| Client Registration response | Có metadata chuẩn và custom metadata được phép. |
| Client Read sau khi lưu | Trả lại đúng metadata custom đã lưu. |
| Repository JDBC restart rồi Client Read | Metadata custom vẫn còn sau khi khởi động lại. |
| Custom converter không làm mất standard claims | `client_id`, grants, redirect URIs và scopes vẫn đúng. |
| Public client yêu cầu client secret | Hành vi phải bị giới hạn theo client policy. |
| Registrar vượt quota | Bị từ chối và có audit event. |
| Hai registration đồng thời cùng client metadata | Server tạo client ID duy nhất, không ghi đè registration khác. |
| Client cố gửi `tenant_code` của tenant khác | Validator/registrar policy từ chối hoặc thay bằng tenant identity tin cậy. |
| Registration response logging | Không ghi client secret/Registration Access Token. |

### 16.1. Integration test cho metadata round-trip

Test cần chứng minh dữ liệu đi qua đủ các lớp:

1. Gửi POST registration có `logo_uri` và `contacts`.
2. Xác nhận response POST chứa hai trường đó.
3. Đọc `registration_client_uri` và `registration_access_token`.
4. Gọi GET Client Read bằng token đó.
5. Xác nhận response GET có cùng custom metadata.
6. Đọc `RegisteredClient` từ repository và xác nhận `ClientSettings` có các custom settings.
7. Restart application hoặc dùng test repository persistent để kiểm tra dữ liệu vẫn tồn tại.

Không chỉ kiểm tra converter riêng lẻ. Integration test phải chạy qua HTTP message converter, authentication converter, provider, repository và response handler.

### 16.2. Test validator

Viết test riêng cho:

- redirect URI thiếu scheme;
- redirect URI có fragment;
- scheme `javascript:` hoặc `data:`;
- post-logout redirect URI sai;
- `jwks_uri` không HTTPS;
- scope ngoài allowlist;
- grant type ngoài allowlist;
- auth method không hỗ trợ;
- custom metadata sai kiểu.

Kiểm tra cả OAuth error code và việc **không có client mới được lưu** sau request thất bại.

## 17. Vận hành và quan sát

Theo dõi các sự kiện:

| Metric/event | Mục đích |
| --- | --- |
| Registration success/failure | Theo dõi tỷ lệ tạo client và lỗi metadata. |
| Registrar client ID | Xác định nguồn tạo registration. |
| Registration quota usage | Phát hiện tạo client bất thường. |
| Validation error by field | Phát hiện redirect/JWKS/scope policy mismatch. |
| Client Read success/failure | Phát hiện token hoặc permission lỗi. |
| Custom metadata persistence failure | Phát hiện lỗi converter/JDBC serialization. |
| Client secret issuance | Theo dõi số lượng secret được cấp mà không ghi giá trị secret. |
| Initial Access Token consumption | Phát hiện token bị dùng lại hoặc abuse. |

Không log Initial Access Token, Registration Access Token, client secret hoặc toàn bộ request/response registration. Nếu cần correlation, dùng request ID, registrar client ID và internal registration ID; không đưa bearer credential vào metric label.

Trong môi trường nhiều instance, các node phải dùng chung `RegisteredClientRepository` persistent và cấu hình converter/validator giống nhau. Nếu node A lưu custom settings nhưng node B dùng converter khác, Client Read có thể trả metadata thiếu hoặc response không nhất quán.

## 18. Checklist triển khai

- [ ] OIDC Client Registration Endpoint chỉ được bật khi có nhu cầu nghiệp vụ.
- [ ] Endpoint dùng HTTPS và được công bố qua `registration_endpoint` chính xác.
- [ ] Có `JwtDecoder` bean để xác minh Bearer token.
- [ ] Registration endpoint được bảo vệ bằng Initial Access Token hoặc một policy open registration đã đánh giá rủi ro.
- [ ] Registrar có scope tối thiểu `client.create`.
- [ ] Client Read chỉ dùng Registration Access Token với scope `client.read`.
- [ ] Initial Access Token có scope đúng theo flow và được consume theo policy.
- [ ] Phân biệt Initial Access Token với Registration Access Token.
- [ ] Giữ request converter/provider mặc định nếu không cần thay đổi protocol parsing.
- [ ] Custom converter chiều vào delegate converter chuẩn rồi lưu custom keys vào `ClientSettings`.
- [ ] Custom converter chiều ra giữ claims chuẩn và thêm metadata mở rộng.
- [ ] Cả `OidcClientRegistrationAuthenticationProvider` và `OidcClientConfigurationAuthenticationProvider` dùng converter chiều ra phù hợp.
- [ ] Validator giữ `DEFAULT_REDIRECT_URI_VALIDATOR`, `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` và `DEFAULT_JWK_SET_URI_VALIDATOR`.
- [ ] Scope được kiểm tra bằng allowlist cụ thể; không chấp nhận tùy ý mọi scope.
- [ ] Không sử dụng `SIMPLE_*_VALIDATOR` trừ khi có đánh giá tương thích và rủi ro.
- [ ] Grant types, response types và token endpoint auth methods được giới hạn theo loại client.
- [ ] Public clients được áp dụng PKCE theo policy.
- [ ] `logo_uri`, `jwks_uri` và custom URLs có policy chống SSRF/phishing.
- [ ] Client secret được encode và không log plaintext.
- [ ] Registration response và Client Read không tiết lộ dữ liệu nội bộ.
- [ ] Có quota, rate limit, audit, lifecycle và quy trình revoke client.
- [ ] Integration test chứng minh custom metadata round-trip qua repository.
- [ ] Test âm tính xác nhận request lỗi không tạo registration.
- [ ] Các instance production dùng chung repository và cùng validator/converter configuration.

**Ghi nhớ:** `OidcClientRegistrationAuthenticationProvider` chuyển metadata đầu vào thành `RegisteredClient` và tạo response; `OidcClientConfigurationAuthenticationProvider` trả metadata khi Client Read. Custom metadata phải được ánh xạ cả hai chiều và lưu trong một nơi có thể persist, ví dụ `ClientSettings`. Hãy giữ validator URI nghiêm ngặt, áp dụng allowlist cho scopes/grants/auth methods và bảo vệ Registration Endpoint bằng Initial Access Token có quyền tối thiểu.

## 19. Tài liệu tham khảo

- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): Client Registration Request/Response, Initial Access Token, Registration Access Token và Client Configuration Endpoint.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): metadata registration, software statements và protected/open registration.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): quản lý registration sau khi tạo; cần phân biệt với các thao tác endpoint cụ thể Spring Authorization Server hỗ trợ.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật endpoint, custom metadata converters, registrar và initial access token.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, filter và các provider mặc định.
- [OidcClientRegistrationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): validator, password encoder và metadata converters.
- [OidcClientConfigurationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientConfigurationAuthenticationProvider.html): Client Read provider và response converter.
- [OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/default và simple validators.
- [OidcClientRegistration API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.html): metadata claims của Client Registration.
- [RegisteredClient API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.html): model client registration trong Spring Authorization Server.
- [ClientSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.html): custom settings và client security settings.

