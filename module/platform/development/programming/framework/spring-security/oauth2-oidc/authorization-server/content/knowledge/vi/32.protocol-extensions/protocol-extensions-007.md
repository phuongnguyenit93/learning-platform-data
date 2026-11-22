# Đăng ký extension vào Token Endpoint và cập nhật metadata phù hợp

OAuth 2.0 cho phép Authorization Server mở rộng cách client yêu cầu access token. Khi một nghiệp vụ cần một loại authorization grant chưa có trong các grant chuẩn, server có thể triển khai **extension authorization grant** tại Token Endpoint. Trong Spring Authorization Server, extension này được nối vào pipeline xử lý token request bằng một `AuthenticationConverter` và một `AuthenticationProvider`.

Việc thêm converter/provider mới chỉ làm server xử lý được request. Client còn cần biết grant type và các tham số mà server hỗ trợ. Vì vậy, cần cập nhật Authorization Server Metadata để công bố grant type phù hợp, đồng thời đăng ký grant type đó trong `RegisteredClient` cho từng client được phép sử dụng.

Bài học thuộc chương **Mở rộng giao thức**, module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Nội dung tập trung vào việc đăng ký extension grant tại Token Endpoint, phát hành token theo contract của Spring Authorization Server và công bố metadata nhất quán.

> **Nguyên tắc triển khai:** Một extension grant chỉ được xem là hoàn chỉnh khi request parser, provider, client registration, token generation, persistence, error response và discovery metadata cùng mô tả một capability thống nhất.

## 1. Extension grant trong OAuth 2.0

RFC 6749 cho phép client yêu cầu access token bằng một extension grant type. Client gửi giá trị `grant_type` là một URI tuyệt đối do Authorization Server định nghĩa, kèm các tham số cần thiết cho grant đó.

Ví dụ một grant riêng dùng mã cấp quyền một lần:

~~~text
urn:example:params:oauth:grant-type:custom-code
~~~

Client gửi request tới Token Endpoint hiện có:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Acustom-code&
code=ONE_TIME_CODE&
scope=profile.read%20orders.read
~~~

Token Endpoint vẫn là endpoint OAuth 2.0 chuẩn. Extension thay đổi cách server diễn giải `grant_type` và những tham số đi kèm, không tạo một endpoint token riêng.

### 1.1. Khi nào cần extension grant?

Một extension grant phù hợp khi hệ thống có một credential hoặc quy trình cấp quyền riêng mà không thể biểu diễn đúng bằng grant type hiện có. Ví dụ:

- Đổi một assertion do hệ thống doanh nghiệp phát hành lấy access token;
- Đổi một one-time code được phát hành sau một quy trình xác minh riêng;
- Tích hợp một cơ chế delegation đã có trong tổ chức;
- Thực hiện token issuance dựa trên một loại bằng chứng được định nghĩa bởi protocol extension.

Không nên tạo grant type mới chỉ để đổi tên một grant chuẩn hoặc thêm một tham số không làm thay đổi semantics của grant. Khi có thể mở rộng claim/token customization trong grant hiện có, hãy cân nhắc cách đó trước.

### 1.2. Extension grant không phải client authentication method

Hai khái niệm này nằm ở hai bước khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Client authentication method | Client là ai? | `client_secret_basic`, `private_key_jwt`, `tls_client_auth` |
| Authorization grant type | Client dựa trên quyền/bằng chứng nào để xin token? | `authorization_code`, `client_credentials`, extension grant URI |

Một client có thể xác thực bằng `client_secret_basic` rồi dùng extension grant. Việc thêm grant type không tự động tạo hoặc thay đổi cơ chế client authentication.

### 1.3. Dùng URI tuyệt đối làm grant type

RFC 6749 yêu cầu extension grant type là absolute URI. Một URN theo namespace riêng có thể dùng cho extension nội bộ. Nếu extension được chia sẻ giữa nhiều tổ chức, cần công bố specification và chọn namespace có quyền kiểm soát để tránh xung đột.

Không dùng các tên ngắn như `custom_code` hoặc `my_grant` làm giá trị extension grant công khai. Chúng dễ trùng với định nghĩa khác và không đáp ứng yêu cầu URI tuyệt đối.

Ví dụ constant:

~~~java
public static final AuthorizationGrantType CUSTOM_CODE =
    new AuthorizationGrantType(
        "urn:example:params:oauth:grant-type:custom-code");
~~~

`AuthorizationGrantType` là value object của Spring Security. Với grant type tùy chỉnh, tạo instance bằng URI đã thống nhất giữa Authorization Server và client.

## 2. Pipeline xử lý Token Endpoint

Spring Authorization Server tổ chức xử lý token request theo ba giai đoạn:

1. **Pre-processing:** `AuthenticationConverter` đọc HTTP request và tạo một `Authentication` đại diện cho grant.
2. **Main processing:** `AuthenticationProvider` xác thực client, grant và điều kiện cấp quyền; sau đó tạo access token.
3. **Post-processing:** success handler chuyển kết quả thành OAuth2 access token response; error handler trả OAuth2 error khi thất bại.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant CA as Client Authentication Filter
    participant F as OAuth2TokenEndpointFilter
    participant CV as Custom AuthenticationConverter
    participant PM as AuthenticationManager
    participant AP as Custom AuthenticationProvider
    participant TG as OAuth2TokenGenerator
    participant AS as OAuth2AuthorizationService

    C->>CA: POST /oauth2/token + client credentials
    CA->>CA: Authenticate client
    CA->>F: Continue filter chain
    F->>CV: Convert grant request
    CV-->>F: CustomCodeGrantAuthenticationToken
    F->>PM: Authenticate grant token
    PM->>AP: Select provider by supports()
    AP->>AP: Validate client, grant and one-time code
    AP->>TG: Generate access token
    TG-->>AP: OAuth2Token
    AP->>AS: Save OAuth2Authorization
    AP-->>PM: OAuth2AccessTokenAuthenticationToken
    PM-->>F: Authentication success
    F-->>C: OAuth2 access token response
~~~

### 2.1. Client authentication xảy ra trước grant provider

Token Endpoint filter nhận request sau khi client authentication đã được xử lý trong Authorization Server filter chain. Converter có thể lấy client principal từ `SecurityContextHolder`; provider vẫn phải kiểm tra principal đó là một `OAuth2ClientAuthenticationToken` đã authenticated.

Không tự xác thực client bằng cách đọc `client_secret` trong custom grant converter. Hãy dùng client authentication pipeline của Spring Authorization Server để áp dụng đúng phương thức xác thực, error handling và security policy.

### 2.2. Converter phải nhường request của grant khác

Token Endpoint sử dụng một `DelegatingAuthenticationConverter` gồm các converter mặc định. Converter của extension chỉ xử lý đúng `grant_type` mà nó sở hữu. Nếu request dùng grant type khác, converter phải trả `null` để converter tiếp theo có thể xử lý.

Nếu converter custom nhận mọi request rồi ném lỗi, nó có thể chặn authorization_code, refresh_token, client_credentials hoặc các grant đã được framework hỗ trợ.

### 2.3. Provider được chọn qua supports()

`AuthenticationManager` chọn provider dựa trên `supports(Class<?>)`. Provider custom phải trả `true` cho đúng custom grant authentication token class. Không viết provider nhận mọi `Authentication` nếu không có lý do rõ ràng.

## 3. Đăng ký grant type trong RegisteredClient

Một extension grant được cài đặt ở server không có nghĩa mọi client đều được phép dùng nó. Mỗi `RegisteredClient` phải khai báo grant type trong `authorizationGrantTypes`.

~~~java
AuthorizationGrantType customCodeGrant =
    new AuthorizationGrantType(
        "urn:example:params:oauth:grant-type:custom-code");

RegisteredClient client = RegisteredClient.withId("custom-client-internal-id")
    .clientId("custom-client")
    .clientSecret(passwordEncoder.encode(clientSecret))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(customCodeGrant)
    .scope("profile.read")
    .scope("orders.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

Đây là ví dụ confidential client. Secret phải được encode bằng `PasswordEncoder` phù hợp; không dùng `{noop}` cho production. Token lifetime và scopes là policy của client, cần điều chỉnh theo rủi ro của grant.

### 3.1. Provider phải kiểm tra grant được client cho phép

Trong provider, kiểm tra:

~~~java
if (!registeredClient.getAuthorizationGrantTypes()
        .contains(customCodeGrant)) {
    throw new OAuth2AuthenticationException(
        OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
}
~~~

Đây là kiểm tra bắt buộc ở thời điểm phát token. Không dựa duy nhất vào việc client đã có trong database hoặc extension đã được đăng ký trên server.

### 3.2. RegisteredClient scopes và requested scopes

Client chỉ được yêu cầu scopes mà registration cho phép. Với grant dựa trên one-time code, code cũng có thể giới hạn scopes mà chủ thể đã được cấp. Provider cần lấy giao của các policy này hoặc từ chối khi request vượt quyền:

~~~text
requested scopes
    ⊆ RegisteredClient allowed scopes
    ⊆ scopes authorized by the grant
~~~

Không tự động cấp tất cả scopes của RegisteredClient chỉ vì request bỏ trống `scope`. Hãy định nghĩa rõ default scopes của extension và kiểm tra chúng trong provider.

### 3.3. Dynamic Client Registration

Nếu Authorization Server hỗ trợ Dynamic Client Registration, endpoint đăng ký client cũng cần có policy cho custom grant type. Việc metadata công bố grant type không đồng nghĩa endpoint đăng ký sẽ chấp nhận mọi client yêu cầu grant đó.

Chỉ cho phép DCR đăng ký custom grant khi client đủ điều kiện, grant đã được enable và registration policy kiểm soát được loại client, scopes, authentication method cùng quyền sử dụng.

## 4. Thiết kế contract của extension trước khi viết code

Trước khi triển khai converter/provider, hãy mô tả protocol contract để server và client không hiểu khác nhau.

Ví dụ contract cho `custom-code`:

| Thành phần | Quy ước |
|---|---|
| `grant_type` | `urn:example:params:oauth:grant-type:custom-code` |
| `code` | One-time code, bắt buộc, chỉ dùng một lần |
| `scope` | Danh sách scopes phân tách bằng dấu cách, bắt buộc trong ví dụ |
| Client authentication | Confidential client xác thực bằng phương thức đã đăng ký |
| Code binding | Code được ràng buộc với client và chủ thể |
| Expiration | Code có thời hạn ngắn |
| Success | OAuth2 access token response chuẩn |
| Invalid code | `invalid_grant` |
| Client không được cấp grant | `unauthorized_client` |
| Scope không hợp lệ | `invalid_scope` |

### 4.1. Phân biệt request parameters và token response parameters

Request parameters mô tả bằng chứng client gửi lên để đổi token. Token response parameters mô tả kết quả token server cấp. Không tự đưa dữ liệu đầu vào như `code`, assertion hoặc secret vào response.

Nếu extension cần một response parameter riêng, chỉ thêm khi có specification rõ ràng và client thực sự cần nó. Các trường chuẩn `access_token`, `token_type`, `expires_in`, `refresh_token` và `scope` vẫn phải tuân theo semantics OAuth2.

### 4.2. Quy định cardinality và validation

Mỗi parameter cần quy định:

- Bắt buộc hay tùy chọn;
- Chỉ xuất hiện một lần hay có thể lặp;
- Kiểu dữ liệu và giới hạn độ dài;
- Cách mã hóa;
- Cách xử lý parameter không được nhận diện;
- Error code khi thiếu, lặp hoặc sai định dạng.

Token request chuẩn dùng `application/x-www-form-urlencoded` qua HTTPS. Không đặt grant code, assertion hoặc credential trong query string.

## 5. Triển khai CustomCodeGrantAuthenticationToken

Spring Authorization Server cung cấp base class `OAuth2AuthorizationGrantAuthenticationToken`. Custom token class kế thừa class này để giữ grant type, client principal và các additional parameters.

~~~java
public final class CustomCodeGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    public static final AuthorizationGrantType GRANT_TYPE =
        new AuthorizationGrantType(
            "urn:example:params:oauth:grant-type:custom-code");

    private String code;
    private final Set<String> requestedScopes;

    public CustomCodeGrantAuthenticationToken(
            String code,
            Set<String> requestedScopes,
            Authentication clientPrincipal) {
        super(GRANT_TYPE, clientPrincipal, Collections.emptyMap());
        Assert.hasText(code, "code cannot be empty");
        Assert.notEmpty(requestedScopes, "requestedScopes cannot be empty");
        this.code = code;
        this.requestedScopes = Collections.unmodifiableSet(
            new LinkedHashSet<>(requestedScopes));
    }

    public String getCode() {
        return this.code;
    }

    public Set<String> getRequestedScopes() {
        return this.requestedScopes;
    }

    @Override
    public Object getCredentials() {
        return this.code;
    }

    @Override
    public void eraseCredentials() {
        this.code = null;
        super.eraseCredentials();
    }
}
~~~

Token class giữ code như credential để có thể xóa khỏi object sau khi xử lý. Trong ứng dụng thực, không log `Authentication` object hoặc `getCredentials()`.

### 5.1. Vì sao không dùng Authentication chung?

Custom grant token class tạo một kiểu riêng để:

- Provider có thể xác định chính xác loại grant;
- Converter chuyển dữ liệu HTTP sang một object có cấu trúc;
- Test có thể kiểm tra request parsing độc lập;
- Không làm lẫn dữ liệu custom với các grant chuẩn;
- Lưu lại grant type đúng trong `OAuth2Authorization`.

### 5.2. Giữ dữ liệu tối thiểu

Chỉ giữ code, scopes và những tham số cần thiết cho provider. Không sao chép toàn bộ request parameter map nếu trong đó có `client_secret`, assertion, dữ liệu nhạy cảm hoặc các parameter chưa được định nghĩa.

## 6. Triển khai CustomCodeGrantAuthenticationConverter

Converter chỉ xử lý request có grant type khớp với extension. Ví dụ dưới đây yêu cầu mỗi parameter xuất hiện đúng một lần, yêu cầu code và scope, rồi chuyển client principal cùng dữ liệu đã kiểm tra thành custom grant token.

~~~java
public final class CustomCodeGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String[] grantTypes =
            request.getParameterValues(OAuth2ParameterNames.GRANT_TYPE);

        if (grantTypes == null) {
            return null;
        }
        if (grantTypes.length != 1) {
            throw invalidRequest();
        }
        if (!CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue()
                .equals(grantTypes[0])) {
            return null;
        }

        Set<String> allowedParameters = Set.of(
            OAuth2ParameterNames.GRANT_TYPE,
            OAuth2ParameterNames.CLIENT_ID,
            OAuth2ParameterNames.CLIENT_SECRET,
            OAuth2ParameterNames.CLIENT_ASSERTION,
            OAuth2ParameterNames.CLIENT_ASSERTION_TYPE,
            OAuth2ParameterNames.CODE,
            OAuth2ParameterNames.SCOPE);
        if (!allowedParameters.containsAll(request.getParameterMap().keySet())) {
            throw invalidRequest();
        }

        String code = requiredSingleParameter(
            request, OAuth2ParameterNames.CODE);
        String scope = requiredSingleParameter(
            request, OAuth2ParameterNames.SCOPE);

        String[] scopeValues =
            StringUtils.tokenizeToStringArray(scope, " ");
        if (scopeValues.length == 0) {
            throw invalidRequest();
        }
        Set<String> requestedScopes =
            new LinkedHashSet<>(Arrays.asList(scopeValues));
        if (requestedScopes.size() != scopeValues.length) {
            throw invalidRequest();
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new CustomCodeGrantAuthenticationToken(
            code, requestedScopes, clientPrincipal);
    }

    private static String requiredSingleParameter(
            HttpServletRequest request, String name) {
        String[] values = request.getParameterValues(name);
        if (values == null || values.length != 1
                || !StringUtils.hasText(values[0])) {
            throw invalidRequest();
        }
        return values[0];
    }

    private static OAuth2AuthenticationException invalidRequest() {
        return new OAuth2AuthenticationException(
            OAuth2ErrorCodes.INVALID_REQUEST);
    }
}
~~~

Các imports chính:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.util.StringUtils;
~~~

### 6.1. Vì sao kiểm tra parameter lặp?

`getParameter()` chỉ trả về một giá trị và có thể che khuất việc client gửi parameter nhiều lần. Với các trường như grant_type, code và scope, converter nên kiểm tra cardinality trước khi tạo authentication token.

Không chọn tùy tiện giá trị đầu tiên hoặc cuối cùng khi client gửi code nhiều lần. Request mơ hồ phải bị từ chối bằng `invalid_request`.

### 6.2. Không lấy client ID làm bằng chứng xác thực

Converter có thể nhận client_id từ form body, nhưng đây chỉ là identifier. Client principal đáng tin cậy phải đến từ client authentication filter của Spring Authorization Server. Provider sẽ kiểm tra principal đó đã authenticated và lấy RegisteredClient từ authentication token.

### 6.3. Additional parameters cần allowlist

Ví dụ trên không chuyển toàn bộ request parameters vào `additionalParameters`. Nếu extension có trường như tenant, audience hoặc resource, hãy định nghĩa rõ tên và kiểu, kiểm tra số lần xuất hiện, validate độ dài/cú pháp và chỉ chuyển các trường đã định nghĩa. Không chuyển client_secret, assertion raw hoặc credential khác vào metadata token tùy tiện.

Allowlist trong converter cũng phải tính đến các form parameters chuẩn mà client authentication method đang dùng, chẳng hạn client_secret_post hoặc private_key_jwt. Ví dụ trên cho phép client_secret, client_assertion và client_assertion_type đi qua parser nhưng không đọc chúng để xác thực; client authentication filter vẫn chịu trách nhiệm kiểm tra.

## 7. Triển khai AuthenticationProvider

Provider thực hiện các bước bảo mật có ý nghĩa quyết định: xác minh client, kiểm tra RegisteredClient cho phép grant, tiêu thụ grant một lần, giới hạn scopes và tạo token.

Đối với ví dụ custom-code, một service nghiệp vụ sẽ xác minh code, client binding, expiration, trạng thái đã dùng và principal được cấp quyền. Việc consume phải atomic để hai request đồng thời không thể đổi cùng một code thành hai access tokens.

### 7.1. Contract của dịch vụ xác minh code

~~~java
public interface CustomCodeGrantService {

    Optional<CustomCodeGrantSubject> consume(
        String code,
        String registeredClientId,
        Set<String> requestedScopes
    );
}

public record CustomCodeGrantSubject(
        Authentication principal,
        Set<String> authorizedScopes) {
}
~~~

Service này là domain service do ứng dụng triển khai. Phương thức consume phải kiểm tra code tồn tại, chưa hết hạn, chưa bị thu hồi, chưa từng sử dụng, được phát hành cho đúng RegisteredClient và cho phép requested scopes. Chỉ sau khi mọi kiểm tra thành công, service mới đánh dấu code đã dùng trong cùng transaction/atomic operation rồi trả principal cùng scopes đã được cấp. Nếu scope không được cấp, service ném invalid_scope và giữ nguyên trạng thái code theo policy đã định nghĩa.

### 7.2. CustomCodeGrantAuthenticationProvider

~~~java
public final class CustomCodeGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final CustomCodeGrantService grantService;
    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;

    public CustomCodeGrantAuthenticationProvider(
            CustomCodeGrantService grantService,
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
        Assert.notNull(grantService, "grantService cannot be null");
        Assert.notNull(authorizationService,
            "authorizationService cannot be null");
        Assert.notNull(tokenGenerator, "tokenGenerator cannot be null");
        this.grantService = grantService;
        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        CustomCodeGrantAuthenticationToken grant =
            (CustomCodeGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
            getAuthenticatedClientElseThrowInvalidClient(grant);
        RegisteredClient registeredClient =
            clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(CustomCodeGrantAuthenticationToken.GRANT_TYPE)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        Set<String> requestedScopes = grant.getRequestedScopes();
        if (!registeredClient.getScopes().containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        CustomCodeGrantSubject grantSubject;
        String code = grant.getCode();
        try {
            grantSubject = this.grantService
                .consume(code, registeredClient.getId(), requestedScopes)
                .orElseThrow(() -> new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_GRANT));
        } finally {
            grant.eraseCredentials();
        }

        if (grantSubject.principal() == null
                || !grantSubject.principal().isAuthenticated()) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_GRANT);
        }
        if (!grantSubject.authorizedScopes().containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext =
            DefaultOAuth2TokenContext.builder()
                .registeredClient(registeredClient)
                .principal(grantSubject.principal())
                .authorizationServerContext(
                    AuthorizationServerContextHolder.getContext())
                .authorizedScopes(requestedScopes)
                .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                .authorizationGrantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE)
                .authorizationGrant(grant)
                .build();

        OAuth2Token generatedToken =
            this.tokenGenerator.generate(tokenContext);
        if (generatedToken == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    OAuth2ErrorCodes.SERVER_ERROR,
                    "The token generator failed to generate an access token.",
                    null));
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            generatedToken.getTokenValue(),
            generatedToken.getIssuedAt(),
            generatedToken.getExpiresAt(),
            requestedScopes);

        OAuth2Authorization.Builder authorizationBuilder =
            OAuth2Authorization.withRegisteredClient(registeredClient)
                .principalName(grantSubject.principal().getName())
                .authorizationGrantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE)
                .authorizedScopes(requestedScopes)
                .attribute(
                    Principal.class.getName(),
                    grantSubject.principal());

        if (generatedToken instanceof ClaimAccessor claimAccessor) {
            authorizationBuilder.token(accessToken, metadata ->
                metadata.put(
                    OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                    claimAccessor.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        this.authorizationService.save(authorizationBuilder.build());

        return new OAuth2AccessTokenAuthenticationToken(
            registeredClient, clientPrincipal, accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return CustomCodeGrantAuthenticationToken.class
            .isAssignableFrom(authentication);
    }

    private static OAuth2ClientAuthenticationToken
            getAuthenticatedClientElseThrowInvalidClient(
                    Authentication authentication) {
        Object principal = authentication.getPrincipal();
        if (principal instanceof OAuth2ClientAuthenticationToken client
                && client.isAuthenticated()) {
            return client;
        }
        throw new OAuth2AuthenticationException(
            OAuth2ErrorCodes.INVALID_CLIENT);
    }
}
~~~

Đoạn code minh họa provider cho user-centric custom grant: code service trả về principal của người dùng, vì vậy token context và authorization record dùng principal đó. Nếu extension là machine-to-machine và code đại diện cho client thay vì resource owner, principal cần được xác định theo semantics của grant.

### 7.3. Những điều provider phải xác minh

| Kiểm tra | Lý do |
|---|---|
| Client đã authenticated | Không cấp token cho request chưa xác thực client |
| Client cho phép custom grant | Registration là ranh giới quyền sử dụng grant |
| Code đúng client | Ngăn client A đổi code được phát hành cho client B |
| Code còn hạn và chưa dùng | Chống replay |
| Code gắn với đúng subject/audience | Ngăn đổi code sang người dùng hoặc resource khác |
| Scopes thuộc client và grant | Không cấp quyền vượt quá consent/policy |
| Token generator tạo được token | Không trả success nếu token generation thất bại |
| Authorization được persist | Introspection, revocation và audit cần state |

### 7.4. Vì sao phải consume code atomic?

Nếu provider chỉ đọc code rồi đánh dấu used ở một thao tác riêng, hai request đồng thời có thể cùng đọc trạng thái chưa dùng và đều phát token. Hãy dùng database transaction với conditional update, unique constraint hoặc compare-and-set để chỉ một request tiêu thụ thành công.

Ví dụ điều kiện update:

~~~sql
UPDATE custom_grant_code
SET consumed_at = CURRENT_TIMESTAMP
WHERE code_hash = ?
  AND registered_client_id = ?
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Chỉ chấp nhận grant khi số hàng được cập nhật bằng 1. Lưu hash của code nếu có thể; tránh lưu raw bearer-like code ở dạng đọc được.

### 7.5. Không tự động cấp refresh token

Ví dụ trên chỉ cấp access token. Nếu extension cần refresh token, phải quy định riêng: client có được đăng ký refresh_token grant không, refresh token có phù hợp semantics của extension không, rotation/reuse policy ra sao, scope có được thu hẹp khi refresh không và authorization record được cập nhật thế nào.

Không phát refresh token chỉ vì token generator có thể tạo nó.

### 7.6. Transaction giữa code consumption và authorization save

Provider có hai thao tác quan trọng: đánh dấu grant code đã dùng và lưu OAuth2Authorization chứa access token mới. Nếu code được commit thành consumed trước khi token generation hoặc authorization save thành công, client có thể mất code mà chưa nhận được token. Đây là fail-closed behavior nhưng có thể yêu cầu người dùng/ứng dụng xin code mới.

Nếu code store và OAuth2AuthorizationService dùng cùng relational database, nên đặt thao tác claim/consume code và lưu authorization trong một transaction phù hợp để lỗi token generation hoặc save có thể rollback toàn bộ. Có thể triển khai orchestration trong một application service được quản lý transaction, thay vì giả định hai repository tự động dùng chung transaction.

Nếu hai store không hỗ trợ cùng transaction, thiết kế state machine như issued → processing → consumed, idempotency key hoặc quy trình recovery có kiểm soát. Không tự đưa code về trạng thái unused sau lỗi không xác định, vì request trước có thể đã phát token thành công nhưng response bị mất.

## 8. Đăng ký converter và provider vào Token Endpoint

`OAuth2TokenEndpointConfigurer` cung cấp hai extension point chính:

- `accessTokenRequestConverter(...)` thêm converter cho request;
- `authenticationProvider(...)` thêm provider xử lý authentication token do converter tạo.

Ví dụ cấu hình trong Authorization Server `SecurityFilterChain`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        AuthenticationConverter customCodeGrantAuthenticationConverter,
        AuthenticationProvider customCodeGrantAuthenticationProvider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                    customCodeGrantAuthenticationConverter)
                .authenticationProvider(
                    customCodeGrantAuthenticationProvider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Khai báo các component như Spring beans:

~~~java
@Bean
AuthenticationConverter customCodeGrantAuthenticationConverter() {
    return new CustomCodeGrantAuthenticationConverter();
}

@Bean
AuthenticationProvider customCodeGrantAuthenticationProvider(
        CustomCodeGrantService grantService,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
    return new CustomCodeGrantAuthenticationProvider(
        grantService, authorizationService, tokenGenerator);
}
~~~

### 8.1. Thêm converter/provider, không thay thế pipeline mặc định

Phương thức `accessTokenRequestConverter(...)` và `authenticationProvider(...)` thêm component vào pipeline. Các converter/provider mặc định cho authorization_code, refresh_token, client_credentials, device_code và token_exchange vẫn tiếp tục hoạt động.

Chỉ dùng `accessTokenRequestConverters(...)` hoặc `authenticationProviders(...)` khi cần thao tác cả danh sách mặc định, ví dụ điều chỉnh thứ tự, thay provider cụ thể hoặc loại bỏ một implementation mặc định. Khi thay danh sách, phải bảo đảm không vô tình xóa các grant type ứng dụng vẫn đang sử dụng.

### 8.2. Converter không nhận diện grant khác

Với request không có `grant_type` hoặc có grant type khác, converter custom trả `null`. Các converter mặc định tiếp tục xử lý. Nếu grant type không được bất kỳ converter/provider nào hỗ trợ, Token Endpoint trả lỗi `unsupported_grant_type` theo OAuth2 error handling.

### 8.3. Giữ success/error handler mặc định

Nếu custom provider trả về `OAuth2AccessTokenAuthenticationToken`, success handler mặc định có thể serialize thành `OAuth2AccessTokenResponse`. Chỉ thay `accessTokenResponseHandler(...)` khi extension thực sự cần response format khác và có specification cho client.

Tương tự, giữ `errorResponseHandler(...)` mặc định nếu không có yêu cầu thay đổi. Một error handler tự viết phải giữ status code, JSON shape và OAuth2 error semantics.

## 9. Request và response của extension grant

Client phải xác thực tại Token Endpoint bằng client authentication method đã đăng ký. Sau đó request chứa `grant_type` extension và các parameters đã định nghĩa trong contract.

### 9.1. Ví dụ request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic Y3VzdG9tLWNsaWVudDpzZWNyZXQ=
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Acustom-code&
code=ONE_TIME_CODE&
scope=profile.read%20orders.read
~~~

Trong production, `Authorization` header chứa credential của client phải được tạo bởi OAuth2 client library và truyền qua TLS. Ví dụ base64 chỉ minh họa HTTP Basic; Base64 không phải mã hóa bảo mật.

### 9.2. Response thành công

Nếu provider trả `OAuth2AccessTokenAuthenticationToken`, handler mặc định trả response chuẩn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJraWQiOiJzaWduaW5nLWtleSIs...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "profile.read orders.read"
}
~~~

Không đưa code đã đổi, raw assertion hoặc thông tin xác minh nội bộ vào response. Client chỉ cần credential và các metadata của token.

### 9.3. Error response

Các error codes cần được dùng đúng ngữ cảnh:

| Error | Khi nào dùng? |
|---|---|
| `invalid_request` | Thiếu parameter bắt buộc, parameter lặp hoặc request không đúng contract |
| `invalid_client` | Client authentication thất bại |
| `unauthorized_client` | Client đã authenticated nhưng không được phép dùng grant này |
| `unsupported_grant_type` | Server không hỗ trợ grant type trong request |
| `invalid_grant` | Code/assertion sai, hết hạn, đã dùng hoặc không gắn với client |
| `invalid_scope` | Scope yêu cầu không được client/grant cho phép |
| `server_error` | Lỗi nội bộ không thể xử lý request |

Không trả chi tiết nội bộ như lý do code hash không tồn tại, client binding mismatch hay code đã bị replay. Với các trường hợp đó, `invalid_grant` thường là phản hồi phù hợp; log nội bộ chỉ lưu correlation ID và mã sự kiện đã được redacted.

## 10. Cập nhật Authorization Server Metadata

RFC 8414 định nghĩa `grant_types_supported` là metadata tùy chọn: một JSON array liệt kê các OAuth 2.0 grant type mà Authorization Server hỗ trợ. Các giá trị có cùng semantics với `grant_types` trong Dynamic Client Registration.

Sau khi triển khai custom grant, metadata nên công bố URI của grant để client có thể discovery capability thay vì hardcode giả định.

### 10.1. Dùng authorizationServerMetadataCustomizer

Spring Authorization Server cung cấp `OAuth2AuthorizationServerMetadataEndpointConfigurer.authorizationServerMetadataCustomizer(...)`. Consumer nhận `OAuth2AuthorizationServerMetadata.Builder`; builder có phương thức `grantType(String)` để thêm một giá trị vào `grant_types_supported`.

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http.with(authorizationServer, server -> server
    .authorizationServerMetadataEndpoint(metadataEndpoint ->
        metadataEndpoint.authorizationServerMetadataCustomizer(metadata ->
            metadata.grantType(
                CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
        )
    )
);
~~~

Đây là fragment của cấu hình Authorization Server. Trong cấu hình đầy đủ, giữ `securityMatcher(...)`, các endpoint configurers và `http.build()` như những ví dụ trước.

### 10.2. Kết quả metadata

Authorization Server Metadata response sẽ có grant type extension trong danh sách:

~~~json
{
  "issuer": "https://identity.example.com",
  "authorization_endpoint": "https://identity.example.com/oauth2/authorize",
  "token_endpoint": "https://identity.example.com/oauth2/token",
  "jwks_uri": "https://identity.example.com/oauth2/jwks",
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials",
    "urn:example:params:oauth:grant-type:custom-code"
  ]
}
~~~

Các endpoint và grant type trong JSON chỉ là ví dụ. Response thực tế được tạo từ `AuthorizationServerSettings`, các endpoint đã bật và metadata customizer của ứng dụng.

### 10.3. Không thay toàn bộ grant list ngoài ý muốn

Builder có `grantTypes(Consumer<List<String>>)` cho phép add, replace hoặc remove danh sách. Nếu chỉ thêm một extension, dùng `grantType(...)` là rõ ràng nhất. Nếu dùng `grantTypes(...)`, phải giữ lại các grant type chuẩn mà server thực sự hỗ trợ.

Không công bố grant type chỉ vì một client được đăng ký có grant đó. Metadata mô tả capability của Authorization Server trên toàn hệ thống; `RegisteredClient` vẫn quyết định client cụ thể có được phép sử dụng capability ấy không.

## 11. Đồng bộ OIDC Provider Configuration khi OIDC được bật

Một Authorization Server có thể công bố cả OAuth 2.0 Authorization Server Metadata theo RFC 8414 và OpenID Provider Configuration theo OpenID Connect Discovery. Hai metadata documents có nhiều trường chung, bao gồm grant types supported.

Nếu client discovery thông qua OIDC `/.well-known/openid-configuration`, hãy cập nhật provider configuration tương ứng để client không nhận một danh sách grant type khác với metadata OAuth2.

~~~java
http.with(authorizationServer, server -> server
    .oidc(oidc -> oidc
        .providerConfigurationEndpoint(endpoint ->
            endpoint.providerConfigurationCustomizer(metadata ->
                metadata.grantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
            )
        )
    )
);
~~~

`OidcProviderConfiguration.Builder` kế thừa metadata builder dùng chung, vì vậy có thể dùng `grantType(...)` để thêm extension grant. Đoạn code chỉ áp dụng khi OIDC provider configuration endpoint được bật.

### 11.1. Cấu hình hai metadata endpoints cùng một policy

Trong ứng dụng bật cả OAuth2 Authorization Server Metadata và OIDC:

~~~java
.authorizationServerMetadataEndpoint(endpoint ->
    endpoint.authorizationServerMetadataCustomizer(metadata ->
        metadata.grantType(
            CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
    )
)
.oidc(oidc -> oidc
    .providerConfigurationEndpoint(endpoint ->
        endpoint.providerConfigurationCustomizer(metadata ->
            metadata.grantType(
                CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
        )
    )
)
~~~

Nên lấy grant type từ cùng một constant hoặc cấu hình dùng chung để tránh một metadata endpoint được cập nhật nhưng endpoint còn lại bị bỏ sót.

### 11.2. Custom metadata cho parameters riêng

RFC 8414 không định nghĩa một trường tổng quát để mô tả mọi request parameter riêng của từng extension grant. Nếu client cần discovery các parameter như code, assertion, resource hoặc tenant, tổ chức có thể công bố một custom metadata claim đã được namespace và mô tả trong extension specification.

Ví dụ minh họa:

~~~java
metadata.claim(
    "urn:example:metadata:custom-code-grant",
    Map.of(
        "grant_type",
        CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue(),
        "required_parameters", List.of("code", "scope"),
        "code_usage", "single-use"
    )
);
~~~

Claim này là metadata riêng của extension, không phải field chuẩn của RFC 8414. Chỉ công bố khi có specification, schema và versioning rõ ràng. Client không nhận diện extension vẫn phải bỏ qua metadata claim không biết theo nguyên tắc xử lý extension của định dạng metadata.

### 11.3. Không sửa metadata không liên quan

Thêm custom grant không tự động làm thay đổi:

- `token_endpoint_auth_methods_supported`;
- `token_endpoint_auth_signing_alg_values_supported`;
- `response_types_supported`;
- `code_challenge_methods_supported`;
- `scopes_supported`;
- `revocation_endpoint` hoặc `introspection_endpoint`.

Chỉ thay những metadata fields khi capability tương ứng thực sự thay đổi. Ví dụ thêm grant không có nghĩa server bắt đầu hỗ trợ `private_key_jwt` hoặc một JWS signing algorithm mới.

### 11.4. Cấu hình thống nhất cho Token Endpoint và metadata

Trong ứng dụng hoàn chỉnh, đặt converter/provider và cả hai metadata customizers trong cùng một cấu hình Authorization Server:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        AuthenticationConverter customCodeGrantAuthenticationConverter,
        AuthenticationProvider customCodeGrantAuthenticationProvider)
        throws Exception {

    String grantType =
        CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue();
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                    customCodeGrantAuthenticationConverter)
                .authenticationProvider(
                    customCodeGrantAuthenticationProvider)
            )
            .authorizationServerMetadataEndpoint(endpoint ->
                endpoint.authorizationServerMetadataCustomizer(metadata ->
                    metadata.grantType(grantType)
                )
            )
            .oidc(oidc -> oidc
                .providerConfigurationEndpoint(endpoint ->
                    endpoint.providerConfigurationCustomizer(metadata ->
                        metadata.grantType(grantType)
                    )
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Ví dụ trên bật OIDC. Nếu ứng dụng không triển khai OIDC, bỏ block oidc và chỉ cấu hình OAuth2 Authorization Server Metadata. Các RegisteredClient, OAuth2AuthorizationService, AuthorizationServerSettings, JWKSource và token generator vẫn phải được khai báo theo cấu hình ứng dụng.

## 12. Metadata, client registration và runtime phải nhất quán

Ba lớp cần phản ánh cùng một khả năng:

| Lớp | Câu hỏi phải trả lời |
|---|---|
| Runtime Token Endpoint | Converter/provider có xử lý grant type này không? |
| RegisteredClient | Client cụ thể có được phép sử dụng grant type này không? |
| Authorization Server Metadata | Server có công bố grant type này là capability được hỗ trợ không? |

Một số trạng thái không nhất quán thường gặp:

- Metadata công bố grant nhưng converter/provider chưa được đăng ký;
- Runtime đã xử lý grant nhưng metadata không công bố;
- Metadata và runtime đều hỗ trợ nhưng RegisteredClient không cho phép;
- Một node đã deploy extension còn node khác chưa deploy;
- OAuth2 metadata đã cập nhật nhưng OIDC discovery còn giá trị cũ.

### 12.1. Metadata là capability ở cấp server

`grant_types_supported` không liệt kê grant riêng cho từng client. Nó mô tả grant types mà Authorization Server hỗ trợ nói chung. Client-specific authorization vẫn nằm trong `RegisteredClient.getAuthorizationGrantTypes()`.

Không tự động đưa mọi grant type tìm thấy trong database RegisteredClient vào metadata. Một registration cũ hoặc bị cấu hình sai không chứng minh runtime đang triển khai grant đó.

### 12.2. Metadata không thay thế registration validation

Client đọc `grant_types_supported` có thể biết server hỗ trợ extension. Khi đăng ký hoặc gửi token request, server vẫn phải kiểm tra client registration, authentication method, grant permission và scope policy.

### 12.3. Rolling deployment

Khi triển khai extension trên nhiều nodes:

1. Deploy code có converter/provider và policy tương thích tới các node;
2. Đảm bảo RegisteredClient data được cập nhật theo release;
3. Xác minh mọi node có cùng extension version;
4. Sau khi runtime sẵn sàng, công bố metadata mới;
5. Theo dõi request lỗi `unsupported_grant_type`, `unauthorized_client` và `invalid_grant`;
6. Khi rollback, gỡ grant khỏi metadata và client registrations theo kế hoạch tương thích.

Không công bố metadata mới trước khi toàn bộ đường xử lý đã sẵn sàng trên topology mà load balancer có thể định tuyến tới.

## 13. Extension grant và Dynamic Client Registration

RFC 8414 dùng cùng giá trị grant type với trường `grant_types` của Dynamic Client Registration. Điều này giúp client biết capability chung trước khi yêu cầu đăng ký.

Tuy nhiên, DCR có thể áp dụng allowlist riêng. Một số server chỉ cho phép administrator cấp custom grant; một số chỉ cho phép loại client cụ thể hoặc yêu cầu review trước khi bật.

### 13.1. Kiểm tra grant type khi đăng ký client

Registration service nên:

- Xác minh grant type là một capability server thực sự hỗ trợ;
- Kiểm tra caller được phép yêu cầu grant type đó;
- Áp dụng policy theo loại client và tenant;
- Kiểm tra grant type tương thích với client authentication method;
- Ghi lại ai cấp quyền và khi nào;
- Từ chối grant URI không được biết hoặc không được policy cho phép.

### 13.2. Client đã đăng ký trước đó

Khi thêm extension grant vào một hệ thống đang chạy, không nên tự động thêm grant vào mọi RegisteredClient. Hãy xác định danh sách client được phép và cập nhật registration qua quy trình quản trị/migration có audit.

### 13.3. Xóa grant khỏi client

Khi một client không còn được phép dùng extension:

1. Xóa grant type khỏi RegisteredClient;
2. Provider phải từ chối request mới với `unauthorized_client`;
3. Xác định token/authorization đã phát hành có tiếp tục hiệu lực đến expiry hay bị revoke;
4. Cập nhật client documentation và registration policy;
5. Chỉ xóa metadata server-wide khi extension không còn được hỗ trợ cho bất kỳ client nào.

Việc bỏ grant khỏi một client không có nghĩa server ngừng hỗ trợ grant cho toàn bộ clients khác.

## 14. Bảo mật extension grant

Extension grant thường mang một loại credential hoặc assertion riêng. Vì server tự định nghĩa semantics, nhóm triển khai phải viết threat model và validation contract rõ ràng. Việc converter parse được request không có nghĩa bằng chứng trong request đã hợp lệ.

### 14.1. Bảo vệ one-time code

Với grant dùng code:

- Sinh code bằng cryptographically secure random generator;
- Có entropy đủ lớn để chống brute force;
- Chỉ lưu hash/digest nếu không cần khôi phục raw code;
- Ràng buộc code với registered client, subject, tenant và audience khi phù hợp;
- Đặt expiry ngắn và giới hạn số lần thử;
- Tiêu thụ code đúng một lần bằng thao tác atomic;
- Không đưa code vào URL, logs, traces hoặc analytics;
- Có rate limit theo client và nguồn request.

Nếu code là mã ngắn do người dùng nhập, cần có cơ chế chống dò mã mạnh hơn: entropy, giới hạn thử, lockout/rate limit, thời gian hiệu lực ngắn và kiểm tra binding. Không coi mã ngắn là credential đủ an toàn chỉ vì nó chỉ được dùng một lần.

### 14.2. Bảo vệ assertion

Nếu extension dùng JWT/SAML assertion thay cho code, provider phải xác minh theo specification của assertion:

- Chữ ký và thuật toán được phép;
- Issuer đáng tin cậy;
- Audience khớp Authorization Server;
- Expiration và not-before;
- Issued-at nằm trong cửa sổ thời gian cho phép;
- Subject/actor và delegation semantics;
- Unique identifier như jti để chống replay;
- Key rotation và trust configuration.

Không chấp nhận assertion chỉ vì parse được payload. Không dùng thuật toán none hoặc cho client tự chọn thuật toán ngoài allowlist.

### 14.3. Client authentication và transport

Token Endpoint phải dùng HTTPS. Client confidential phải xác thực bằng phương thức đã đăng ký. Với client có quyền cao hoặc assertion nhạy cảm, cân nhắc private_key_jwt hoặc mutual TLS theo threat model và khả năng của hệ thống.

Không nhận client secret trong query string. Không tự viết client authentication thứ hai bên trong custom provider. Không bỏ qua kết quả xác thực đã được filter chain tạo ra.

### 14.4. Scope và subject

Provider cần giới hạn quyền theo ba nguồn: scopes client được đăng ký, scopes của grant và scopes client yêu cầu. Token subject phải đến từ nguồn đã xác minh. Không dùng username hoặc subject do client gửi lên làm bằng chứng identity.

Với grant machine-to-machine, principal có thể là client. Với grant đại diện cho End-User, principal phải được xác minh từ code/assertion và token claims cần phản ánh đúng subject/delegation semantics. Không tự động coi mọi custom grant là OIDC login flow hoặc phát ID Token.

### 14.5. Token lifetime và refresh

Chọn access token lifetime ngắn phù hợp mức rủi ro. Chỉ cấp refresh token nếu extension có mô hình ủy quyền lâu dài, rotation, revocation và client storage phù hợp. Nếu grant chỉ là one-time exchange, access token ngắn hạn có thể đủ.

Nếu access token là JWT, Resource Server cần kiểm tra issuer, audience, signature, expiry và scopes. Nếu dùng opaque token, introspection path phải tra được authorization đã lưu.

### 14.6. Logging và error disclosure

Không log raw code, assertion, client secret, access token hoặc refresh token. Dùng correlation ID, client ID đã xác thực, grant type, error code và latency. Lỗi trả client nên đủ để client xử lý nhưng không tiết lộ code có tồn tại, thuộc client nào hoặc đã bị dùng bởi ai.

## 15. Extension grant hay mở rộng một grant hiện có?

Không phải mọi thay đổi Token Endpoint đều cần một AuthorizationGrantType mới.

| Yêu cầu | Hướng tiếp cận |
|---|---|
| Có một loại credential/authorization grant mới với semantics riêng | Extension grant và custom AuthenticationConverter/Provider |
| Thêm claim vào access token hiện có | OAuth2TokenCustomizer |
| Điều chỉnh validation cho grant chuẩn | Tùy chỉnh provider/validator hiện có |
| Thêm tham số cho một grant chuẩn | Chỉ mở rộng converter/provider nếu contract yêu cầu và không phá semantics chuẩn |
| Thay đổi JSON token response | Custom response handler khi có specification rõ |
| Thêm client authentication method | Client authentication extension, không phải authorization grant |
| Thêm endpoint protocol hoàn toàn mới | Endpoint filter/configurer riêng và metadata phù hợp |

### 15.1. Không overloading parameter chuẩn

Không tái sử dụng code, assertion, scope hoặc client_id với ý nghĩa khác nhau tùy grant mà không mô tả rõ. Nếu extension cần parameter riêng, chọn tên không gây nhầm với parameter chuẩn và định nghĩa cách xử lý duplicate/unknown fields.

### 15.2. Giữ tương thích với grant chuẩn

Converter custom chỉ xử lý URI của extension và trả null cho request khác. Provider custom chỉ hỗ trợ custom authentication token. Không thay default token endpoint converter/provider list nếu không có lý do tương thích được kiểm chứng.

## 16. Kiểm thử extension grant

Kiểm thử nên tách thành converter tests, provider tests, endpoint integration tests và metadata tests. Mỗi lớp xác minh một phần của contract.

### 16.1. Converter tests

Kiểm tra ít nhất:

- Request dùng custom grant tạo đúng authentication token;
- Request dùng grant chuẩn trả null để converter khác xử lý;
- Thiếu grant_type;
- grant_type lặp;
- Thiếu code;
- code lặp hoặc rỗng;
- Thiếu scope;
- scope rỗng hoặc lặp;
- Request có thêm parameter ngoài contract;
- Client principal được lấy từ SecurityContext.

Ví dụ kiểm tra request có grant type khác:

~~~java
@Test
void returnsNullForGrantTypeOwnedByAnotherConverter() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.addParameter("grant_type", "client_credentials");

    Authentication result =
        new CustomCodeGrantAuthenticationConverter().convert(request);

    assertThat(result).isNull();
}
~~~

### 16.2. Provider tests

Mock hoặc fake CustomCodeGrantService, OAuth2AuthorizationService và token generator để kiểm tra:

- Client chưa authenticated bị từ chối;
- Client không có custom grant nhận unauthorized_client;
- Code sai, hết hạn, đã dùng hoặc không thuộc client nhận invalid_grant;
- Scope vượt quyền nhận invalid_scope;
- Token generator trả null tạo server_error;
- Authorization được save với đúng grant type, principal, scopes và token metadata;
- Code chỉ được consume một lần;
- Principal trong token context là principal đã được grant service xác minh.

### 16.3. Token Endpoint integration test với MockMvc

Integration test nên dùng SecurityFilterChain, client authentication và token generator thật của test context:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomCodeGrantEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void issuesAccessTokenForValidCustomCodeGrant() throws Exception {
        String code = customCodeGrantFixture();

        mvc.perform(post("/oauth2/token")
                .with(httpBasic("custom-client", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type",
                    "urn:example:params:oauth:grant-type:custom-code")
                .param("code", code)
                .param("scope", "profile.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"))
            .andExpect(jsonPath("$.expires_in").isNumber());
    }
}
~~~

Đây là test skeleton. customCodeGrantFixture() phải tạo code hợp lệ, ràng buộc với client test và scopes tương ứng. Endpoint path và client authentication phải khớp AuthorizationServerSettings cùng RegisteredClient của test application.

### 16.4. Negative endpoint tests

Tạo tests cho:

- Client credentials sai;
- Client đã authenticated nhưng không đăng ký custom grant;
- Code sai/hết hạn/đã dùng;
- Scope không thuộc client;
- Scope không thuộc grant;
- Unknown grant type;
- Request thiếu hoặc lặp parameter;
- Hai request đồng thời đổi cùng code, chỉ một request thành công.

Đặc biệt, kiểm thử replay phải chạy ở persistence layer thực hoặc test double có atomic semantics. Một unit test tuần tự không chứng minh code consumption an toàn khi concurrent requests.

### 16.5. Metadata tests

Gọi Authorization Server Metadata endpoint và xác nhận grant_types_supported có URI extension. Nếu OIDC bật, gọi OpenID Provider Configuration endpoint và xác nhận grant type tương ứng cũng xuất hiện.

Ngoài ra kiểm tra metadata không có duplicate grant type, grant type công bố khớp chính xác giá trị trong RegisteredClient và converter, endpoint URL lấy từ cấu hình thực tế, các grant type chuẩn vẫn còn và custom metadata claim đúng schema/version đã công bố.

Ví dụ kiểm tra RFC 8414 metadata bằng MockMvc:

~~~java
@Test
void advertisesCustomGrantTypeInAuthorizationServerMetadata()
        throws Exception {
    mvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.grant_types_supported",
            hasItem(CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())));
}
~~~

Nếu AuthorizationServerSettings dùng issuer path hoặc metadata endpoint path tùy chỉnh, hãy gọi URL được cấu hình thay vì hardcode path mặc định trong test. Với ứng dụng bật OIDC, thêm assertion tương tự cho OpenID Provider Configuration response.

### 16.6. Kiểm thử persistence và concurrent replay

Nếu code store dùng JDBC, Redis hoặc một shared store, chạy integration tests trên backend thực tế. Testcontainers có thể khởi tạo database engine phù hợp để kiểm tra transaction, conditional update và unique constraints. Tạo hai request đồng thời với cùng code và xác minh chỉ một request consume thành công.

## 17. Vận hành, versioning và quan sát

Extension grant là một phần của protocol contract. Khi client đã tích hợp, thay đổi URI hoặc semantics request có thể phá vỡ khả năng lấy token.

### 17.1. Versioning contract

Giữ grant URI ổn định khi chỉ sửa implementation nội bộ mà không đổi semantics. Nếu có breaking change về parameters, validation, token subject hoặc response semantics, hãy công bố version mới hoặc quy tắc tương thích rõ ràng.

Không âm thầm đổi nghĩa của cùng một grant URI giữa các release. Nếu server cần hỗ trợ song song hai phiên bản, đăng ký converter/provider cho từng grant URI và công bố cả hai trong metadata.

### 17.2. Metrics

Theo dõi các chỉ số không chứa credential:

| Metric | Mục đích |
|---|---|
| oauth2_custom_grant_requests_total | Số request theo grant type và kết quả |
| oauth2_custom_grant_success_total | Số lần phát token thành công |
| oauth2_custom_grant_invalid_grant_total | Code/assertion không hợp lệ |
| oauth2_custom_grant_replay_total | Số lần phát hiện replay |
| oauth2_custom_grant_provider_duration | Thời gian xác minh và cấp token |
| oauth2_custom_grant_token_generation_errors | Lỗi token generator |
| oauth2_metadata_requests_total | Theo dõi metadata endpoint |

Không dùng code, assertion, subject raw hoặc token value làm metric labels.

### 17.3. Audit

Audit record có thể gồm client ID đã xác thực, grant URI, correlation ID, kết quả, scopes đã cấp, principal đã pseudonymize và timestamp. Không ghi raw code hoặc assertion.

### 17.4. Rollback

Rollback extension cần xử lý ba phần: metadata, client registrations và runtime. Trước khi gỡ provider, xác định token đã cấp còn hiệu lực bao lâu, refresh token có được phát hành không và Resource Server tiếp tục xác minh token theo policy nào.

Không xóa grant khỏi metadata trong khi client vẫn đang được định tuyến tới node có thể xử lý request theo cách khác. Các node cần có cấu hình nhất quán trong toàn bộ thời gian rollout/rollback.

## 18. Endpoint paths, issuer và discovery

Authorization Server Metadata và OIDC Provider Configuration được client dùng để tìm endpoint URL. Khi cấu hình endpoint path tùy chỉnh, hãy để Spring Authorization Server tạo metadata từ cùng AuthorizationServerSettings thay vì tự viết URL hardcode trong metadata customizer.

Ví dụ cấu hình endpoint settings:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .tokenEndpoint("/oauth2/v2/token")
        .authorizationEndpoint("/oauth2/v2/authorize")
        .build();
}
~~~

Các path trong ví dụ chỉ minh họa. Metadata response cần trả token_endpoint trỏ đúng path mà Token Endpoint filter thực sự phục vụ. Extension grant vẫn dùng cùng token endpoint path này.

### 18.1. Hai discovery documents

Các client OAuth2 có thể đọc Authorization Server Metadata theo RFC 8414. OIDC Relying Parties thường đọc OpenID Provider Configuration. Nếu server bật cả hai, hãy kiểm tra:

- issuer giống nhau;
- token_endpoint trỏ cùng endpoint;
- grant_types_supported nhất quán;
- jwks_uri, authorization_endpoint và các endpoint khác phản ánh đúng cấu hình;
- URLs dùng public origin mà client có thể truy cập.

### 18.2. Reverse proxy và public issuer

Trong môi trường có ingress/reverse proxy, metadata không được công bố hostname nội bộ hoặc HTTP scheme không an toàn. Cấu hình issuer và forwarded headers theo deployment để server tạo URL public chính xác. Kiểm tra metadata từ góc nhìn client bên ngoài, không chỉ kiểm tra URL nội bộ trong container.

### 18.3. Không tự sửa token_endpoint để phân biệt grant

Không tạo một token endpoint riêng cho mỗi extension nếu không có yêu cầu protocol đặc biệt. Client chọn grant bằng grant_type tại Token Endpoint. Việc có một endpoint chuẩn giúp client tái sử dụng client authentication, error handling và token response processing.

## 19. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Token Endpoint trả unsupported_grant_type | Converter không nhận diện URI hoặc converter chưa được đăng ký | Kiểm tra grant URI, converter bean và tokenEndpoint configurer |
| Converter nhận request nhưng provider không chạy | supports() trả false hoặc provider chưa được đăng ký | Kiểm tra authentication token class và provider wiring |
| Client nhận unauthorized_client | RegisteredClient không có custom grant | Kiểm tra authorizationGrantTypes của đúng registration |
| Client nhận invalid_client | Client authentication thất bại | Kiểm tra authentication method, secret/key và filter chain |
| Client nhận invalid_grant | Code sai, hết hạn, đã dùng hoặc không gắn với client | Kiểm tra code store, client binding, expiry và replay |
| Client nhận invalid_scope | Scope vượt RegisteredClient hoặc grant authorization | Kiểm tra scope contract và policy |
| Token generator trả null | Generator không hỗ trợ token context hoặc thiếu JWK/encoder | Kiểm tra token generator, JWKSource và token customizer |
| Access token phát hành nhưng introspection không tìm thấy | Authorization không được save hoặc service khác instance | Kiểm tra OAuth2AuthorizationService wiring và persistence |
| Metadata không có custom grant | Metadata customizer chưa gắn đúng endpoint | Kiểm tra authorizationServerMetadataEndpoint |
| OAuth2 metadata đúng nhưng OIDC discovery sai | Chưa cập nhật providerConfigurationCustomizer | Đồng bộ cả hai discovery documents |
| Metadata công bố grant nhưng client không dùng được | Runtime hoặc RegisteredClient không cho phép | Kiểm tra converter/provider và client registration |
| Chỉ một số node xử lý được grant | Deployment/configuration không đồng nhất | Kiểm tra version, config và rollout |
| Token response thiếu scope | Provider không đưa authorized scopes vào token context/response | Kiểm tra token context và access token scopes |
| Code bị dùng hai lần khi có request đồng thời | Consume không atomic | Kiểm tra transaction/conditional update |

### 19.1. Quy trình chẩn đoán

1. Đọc grant_type chính xác từ request đã redacted.
2. Xác minh client authentication thành công.
3. Kiểm tra RegisteredClient được resolve và có grant type.
4. Kiểm tra converter trả đúng custom Authentication token.
5. Kiểm tra AuthenticationManager chọn provider qua supports().
6. Kiểm tra grant service xác minh và consume code.
7. Kiểm tra requested scopes và authorized scopes.
8. Kiểm tra token generator và authorization persistence.
9. Đọc metadata từ public discovery URL để so sánh capability.

Không log raw grant code, assertion, client secret hoặc token để chẩn đoán. Dùng correlation ID và error category.

## 20. Checklist production

1. **Grant identifier:** URI tuyệt đối, ổn định và được công bố trong extension contract?
2. **Converter:** Chỉ nhận đúng grant type, từ chối parameter thiếu/lặp và nhường request khác?
3. **Provider:** supports() chỉ nhận custom grant token class?
4. **Client authentication:** Token Endpoint dùng client authentication pipeline chuẩn?
5. **Client permission:** RegisteredClient cụ thể được phép dùng extension grant?
6. **Grant validation:** Code/assertion được xác minh chữ ký, issuer, audience, expiry và binding?
7. **Replay:** One-time code được consume atomic và chỉ thành công một lần?
8. **Scopes:** Requested scopes là subset của client scopes và grant scopes?
9. **Principal:** Subject lấy từ nguồn đã xác minh?
10. **Token generation:** Dùng OAuth2TokenGenerator chung và token customizer đúng policy?
11. **Persistence:** OAuth2Authorization được lưu với grant type, principal, scopes và token metadata?
12. **Response:** Success handler trả OAuth2AccessTokenResponse chuẩn?
13. **Errors:** invalid_request, invalid_client, unauthorized_client, invalid_grant, invalid_scope và unsupported_grant_type dùng đúng ngữ cảnh?
14. **Metadata:** grant_types_supported công bố đúng capability thực tế?
15. **OIDC discovery:** Provider Configuration nhất quán nếu OIDC được bật?
16. **DCR:** Dynamic registration có allowlist/policy cho custom grant?
17. **Transport:** HTTPS và không gửi credential trong URL?
18. **Observability:** Không log code/assertion/token; có metrics, audit và replay alert?
19. **Testing:** Converter, provider, MockMvc, metadata và concurrent replay tests?
20. **Deployment:** Các node có cùng code/config và rollout/rollback tương thích?

## 21. Bài tập vận dụng

**Tình huống A — Grant không được nhận diện:** Client gửi grant_type URI đúng nhưng Token Endpoint trả unsupported_grant_type. Hãy lần theo filter, converter, Authentication token và provider để tìm điểm chưa được đăng ký.

**Tình huống B — Client không được phép:** Converter và provider đều hoạt động nhưng một client nhận unauthorized_client. Giải thích vì sao server-level support không thay thế RegisteredClient grant permission.

**Tình huống C — Replay:** Hai request đồng thời gửi cùng one-time code và cả hai đều nhận access token. Thiết kế lại consume operation để chỉ một request cập nhật trạng thái thành công.

**Tình huống D — Scope escalation:** Client được đăng ký profile.read nhưng gửi profile.read và orders.read. Xây dựng kiểm tra bảo đảm token không chứa scope ngoài registration hoặc grant.

**Tình huống E — Metadata drift:** RFC 8414 metadata có custom grant nhưng OIDC discovery không có. Cập nhật provider configuration và viết integration test xác minh hai response nhất quán.

**Tình huống F — Token không introspect được:** Client nhận access token thành công nhưng introspection báo inactive. Kiểm tra authorization persistence, token metadata và OAuth2AuthorizationService được inject vào provider.

**Tình huống G — Breaking change:** Extension cần đổi parameter code thành assertion và thay đổi semantics subject. Hãy quyết định giữ URI hay phát hành grant URI phiên bản mới, rồi lập kế hoạch rollout.

**Gợi ý:** A kiểm tra converter/provider wiring; B kiểm tra RegisteredClient; C dùng atomic conditional update; D kiểm tra giao các scope sets; E cập nhật cả hai discovery customizers; F lưu OAuth2Authorization; G dùng versioned extension contract khi thay đổi semantics không tương thích.

## 22. Tổng kết

Spring Authorization Server mở rộng Token Endpoint bằng cách đăng ký AuthenticationConverter và AuthenticationProvider. Converter nhận diện grant type, validate request parameters và tạo một OAuth2AuthorizationGrantAuthenticationToken riêng. Provider xác thực client, kiểm tra RegisteredClient cho phép grant, xác minh bằng chứng, áp dụng scopes, tạo access token và lưu OAuth2Authorization.

Extension grant cần một URI tuyệt đối và client phải đăng ký grant type đó trong RegisteredClient. Authorization Server Metadata theo RFC 8414 công bố capability ở cấp server qua grant_types_supported; nếu OIDC được bật và client discovery qua OpenID Provider Configuration, metadata OIDC cũng cần được cập nhật để hai discovery documents nhất quán.

Metadata không cấp quyền cho client. Runtime converter/provider, RegisteredClient permission và metadata phải phản ánh cùng một capability. Một extension grant production còn cần chống replay, ràng buộc code với client/subject, giới hạn scopes, bảo vệ credential, kiểm thử concurrent requests và quy trình versioning/rollback.

## 23. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.5 Extension Grants](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): URI tuyệt đối trong grant_type và additional request parameters.
- [RFC 6749 — Section 5 Issuing an Access Token](https://www.rfc-editor.org/rfc/rfc6749.html#section-5): token response và error semantics.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): grant_types_supported và các metadata fields.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client grant_types và registration policy.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): security guidance cho OAuth2 clients, authorization servers và resource servers.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): converter, provider, token endpoint configuration và request example.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth2TokenEndpointConfigurer, default converters/providers và metadata endpoint.
- [Spring Authorization Server API — OAuth2TokenEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): API đăng ký access token request converters/providers.
- [Spring Authorization Server API — OAuth2AuthorizationServerMetadataEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerMetadataEndpointConfigurer.html): authorizationServerMetadataCustomizer.
- [Spring Authorization Server API — AbstractOAuth2AuthorizationServerMetadata.AbstractBuilder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/AbstractOAuth2AuthorizationServerMetadata.AbstractBuilder.html): grantType/grantTypes và metadata builder methods.
- [Spring Authorization Server API — OAuth2AuthorizationGrantAuthenticationToken](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationGrantAuthenticationToken.html): base class cho custom grant authentication token.
- [Spring Authorization Server API — OAuth2AccessTokenAuthenticationToken](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AccessTokenAuthenticationToken.html): kết quả authentication khi cấp access token.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2Authorization, OAuth2TokenGenerator và authorization services.
