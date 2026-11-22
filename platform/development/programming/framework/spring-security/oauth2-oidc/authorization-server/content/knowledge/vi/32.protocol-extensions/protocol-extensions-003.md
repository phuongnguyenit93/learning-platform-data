# Tạo AuthenticationToken và AuthenticationConverter cho grant mới

## Mục tiêu bài học

Trong chương **Mở rộng giao thức** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn mở rộng OAuth 2.0 Token Endpoint bằng một authorization grant type mới trong **Spring Authorization Server 1.5.8**, sử dụng **Spring Security** và **Spring Boot**.

Một grant mở rộng cho phép Authorization Server nhận một loại bằng chứng cấp quyền mà các grant chuẩn hiện có chưa mô tả phù hợp. Ví dụ, hệ thống đối tác có thể cấp một ticket ngắn hạn, ràng buộc với một OAuth client và một tập scope. Client gửi ticket tới Token Endpoint; Authorization Server xác minh ticket rồi phát access token theo policy.

Spring Authorization Server thiết kế extension grant theo ba thành phần chính:

1. **AuthenticationToken** biểu diễn request grant sau khi đã được chuyển đổi.
2. **AuthenticationConverter** đọc HTTP request và tạo AuthenticationToken tương ứng.
3. **AuthenticationProvider** xác minh grant, kiểm tra client và tạo kết quả cấp token.

Hai thành phần đầu là trọng tâm của bài học. Provider được trình bày cùng để làm rõ AuthenticationToken được tiêu thụ như thế nào và vì sao converter không nên tự xác minh hoặc cấp token.

### Kết quả mong đợi

Sau bài học, bạn có thể:

1. Giải thích extension authorization grant theo RFC 6749 và phân biệt grant type với access token.
2. Chọn một absolute URI duy nhất cho giá trị grant_type.
3. Tạo class kế thừa OAuth2AuthorizationGrantAuthenticationToken.
4. Viết AuthenticationConverter để nhận diện grant, kiểm tra tham số và giữ client principal đã xác thực.
5. Phân biệt request thuộc grant mới với request thuộc grant chuẩn bằng cách trả null từ converter khi không khớp.
6. Viết AuthenticationProvider kiểm tra client, grant permission, ticket, scope và trạng thái replay.
7. Tạo OAuth2TokenContext, gọi OAuth2TokenGenerator và lưu OAuth2Authorization.
8. Đăng ký converter/provider vào OAuth2 Token Endpoint mà vẫn giữ các converter/provider mặc định.
9. Kiểm thử request hợp lệ, request sai, client không được phép và grant đã hết hạn hoặc đã sử dụng.
10. Đánh giá các rủi ro về replay, scope escalation, credential leakage, transaction và token lifecycle.

> **Tình huống xuyên suốt:** một đối tác gửi cho Authorization Server một ticket dùng một lần để xác nhận giao dịch của người dùng. Client đã được đăng ký với grant type riêng và scope được phép. Authorization Server phải xác thực client, kiểm tra ticket có đúng client/audience, còn hạn, chưa sử dụng, xác định subject và scope được phép, sau đó phát access token.

## 1. Extension authorization grant là gì?

### 1.1. Grant type mô tả cách client yêu cầu token

OAuth 2.0 authorization grant là credential hoặc biểu diễn authorization mà client dùng để yêu cầu access token. RFC 6749 định nghĩa các grant phổ biến như Authorization Code, Client Credentials và Refresh Token. Mục 4.5 cho phép mở rộng bằng một grant type mới.

Client gửi giá trị grant type trong request tới Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Apartner-ticket&example_partner_ticket=ONE_TIME_TICKET
~~~

Giá trị grant_type của extension phải là một absolute URI duy nhất. URI này là tên giao thức của grant, không phải endpoint URL để client gọi trực tiếp. Theo RFC 6749 mục 8.3, nếu extension cần thêm token endpoint parameters thì các parameter đó phải được đăng ký trong OAuth Parameters Registry. Với tham số vendor-specific chỉ dùng trong phạm vi triển khai riêng, RFC 6749 mục 8.2 khuyến nghị dùng tiền tố riêng để giảm nguy cơ xung đột tên; tiền tố không thay thế yêu cầu đăng ký khi parameter thuộc diện phải đăng ký.

Trong ví dụ, grant type là:

~~~text
urn:example:params:oauth:grant-type:partner-ticket
~~~

Tham số grant riêng là **example_partner_ticket**. Tiền tố example thể hiện tên miền sở hữu tham số trong một triển khai minh họa. Với extension cần interoperable giữa nhiều tổ chức, hãy tuân thủ quy trình đăng ký grant type và các token endpoint parameters theo RFC 6749 mục 8.3 và OAuth Parameters Registry. Không dùng tên tham số chung như ticket, assertion hoặc code nếu chúng có thể xung đột với extension khác.

### 1.2. Khi nào nên tạo grant mới?

Chỉ tạo extension grant khi có một loại authorization artifact hoặc trust relationship riêng mà các grant chuẩn không mô tả phù hợp.

Ví dụ có thể cần extension grant:

- Một hệ thống nghiệp vụ đã có một credential cấp quyền ngắn hạn, dùng một lần và ràng buộc với client.
- Một trust domain nội bộ phát hành signed assertion theo policy riêng.
- Một hệ thống tích hợp cần trao đổi authorization artifact từ một nền tảng legacy sang access token của Authorization Server.

Trước khi tạo grant mới, hãy kiểm tra liệu một chuẩn hiện có đã giải quyết đúng bài toán chưa. Ví dụ, Token Exchange có RFC riêng; SAML 2.0 Bearer Assertion và JWT Bearer Assertion cũng có đặc tả riêng. Không tạo một grant vendor-specific chỉ để đổi tên một flow chuẩn.

### 1.3. Extension grant không tự tạo OIDC login flow

Extension grant mở rộng cách lấy token tại Token Endpoint. Nó không tự tạo Authorization Endpoint flow, browser login, consent screen, ID Token hoặc OIDC authentication flow.

Nếu extension cần đại diện cho một End-User, provider phải xác minh danh tính subject từ nguồn tin cậy và lưu principal phù hợp trong authorization. Không lấy username hoặc subject tùy ý từ request body rồi coi đó là người dùng đã xác thực.

### 1.4. Vai trò của ba thành phần

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant CA as Client Authentication Filter
    participant TE as Token Endpoint Filter
    participant CV as Custom AuthenticationConverter
    participant AM as AuthenticationManager
    participant AP as Custom AuthenticationProvider
    participant TS as Ticket Service
    participant TG as OAuth2TokenGenerator
    participant AS as OAuth2AuthorizationService

    C->>CA: POST /oauth2/token + client credentials
    CA->>CA: Authenticate client
    CA-->>TE: Authenticated client in SecurityContext
    TE->>CV: Convert HTTP request
    CV->>CV: Check grant_type and parameters
    CV-->>TE: PartnerTicketGrantAuthenticationToken
    TE->>AM: Authenticate grant token
    AM->>AP: Delegate by supports()
    AP->>AP: Check client and registered grant
    AP->>TS: Validate and consume ticket atomically
    TS-->>AP: Subject and approved scopes
    AP->>TG: Generate access token from OAuth2TokenContext
    TG-->>AP: OAuth2Token
    AP->>AS: Save OAuth2Authorization
    AP-->>TE: OAuth2AccessTokenAuthenticationToken
    TE-->>C: Standard OAuth2 access token response
~~~

| Thành phần | Trách nhiệm | Không nên làm |
|---|---|---|
| AuthenticationToken | Giữ dữ liệu grant đã parse và client principal. | Không tự xác minh ticket hoặc phát token. |
| AuthenticationConverter | Nhận diện grant, kiểm tra cú pháp request và tạo token. | Không truy cập hệ thống nghiệp vụ để consume ticket. |
| AuthenticationProvider | Xác minh client/grant, gọi domain service, tạo và lưu token. | Không tự viết HTTP response hoặc bỏ qua token generator. |
| OAuth2TokenGenerator | Tạo access token theo token context và token settings. | Không thay thế bước xác thực grant. |
| OAuth2AuthorizationService | Lưu authorization và token state. | Không chỉ trả token mà bỏ lưu trạng thái khi hệ thống cần introspection/revocation. |

## 2. AuthenticationToken trong Spring Authorization Server

### 2.1. AuthenticationToken là đối tượng nội bộ của Spring Security

Trong Token Endpoint, Spring Authorization Server dùng Authentication abstraction để chuyển request qua AuthenticationManager và AuthenticationProvider.

**OAuth2AuthorizationGrantAuthenticationToken** là base class cho Authentication đại diện một authorization grant. Class này giữ:

- AuthorizationGrantType.
- Client principal được xác thực ở bước client authentication.
- Additional parameters của grant.

Constructor của base class là protected, vì vậy ứng dụng tạo class riêng bằng cách kế thừa nó.

Không nhầm object này với OAuth2AccessToken. AuthenticationToken biểu diễn yêu cầu cấp quyền; OAuth2AccessToken là credential được phát hành sau khi provider xác minh grant thành công.

### 2.2. Khai báo grant type

Tạo class giữ hằng số grant type và tham số được hỗ trợ:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class PartnerTicketGrantTypes {

    public static final AuthorizationGrantType PARTNER_TICKET =
            new AuthorizationGrantType(
                    "urn:example:params:oauth:grant-type:partner-ticket");

    public static final String PARTNER_TICKET_PARAMETER =
            "example_partner_ticket";

    private PartnerTicketGrantTypes() {
    }
}
~~~

Đặt tên grant type ở một nơi dùng chung để RegisteredClient, AuthenticationToken, Converter và Provider không vô tình dùng các chuỗi khác nhau.

### 2.3. Tạo PartnerTicketGrantAuthenticationToken

Class này chứa ticket và scope client yêu cầu. Client principal được truyền vào base class để provider có thể kiểm tra OAuth2ClientAuthenticationToken.

~~~java
import java.util.Set;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationGrantAuthenticationToken;

public final class PartnerTicketGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private String ticket;
    private final Set<String> requestedScopes;

    public PartnerTicketGrantAuthenticationToken(
            String ticket,
            Authentication clientPrincipal,
            Set<String> requestedScopes) {

        super(PartnerTicketGrantTypes.PARTNER_TICKET,
                clientPrincipal,
                null);

        this.ticket = ticket;
        this.requestedScopes = Set.copyOf(requestedScopes);
    }

    public String getTicket() {
        return this.ticket;
    }

    public Set<String> getRequestedScopes() {
        return this.requestedScopes;
    }

    @Override
    public Object getCredentials() {
        return this.ticket;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.ticket = null;
    }
}
~~~

Một số quyết định quan trọng:

- Grant type được truyền vào constructor của base class.
- Client principal là Authentication đã được client authentication filter xác thực.
- Ticket là credential nhạy cảm; không đưa nó vào log, exception message hoặc toString tùy chỉnh.
- requestedScopes được sao chép thành immutable Set để tránh bị thay đổi sau khi token được tạo.
- eraseCredentials() xóa tham chiếu ticket sau khi xử lý nếu framework hoặc ứng dụng gọi thao tác xóa credentials.
- Token này không tự đánh dấu authenticated. Nó chỉ là request grant chờ AuthenticationProvider xử lý.

Nếu grant có nhiều tham số riêng, hãy thêm field có kiểu rõ ràng và validate ở converter. Chỉ đặt dữ liệu thực sự cần thiết vào additional parameters; không sao chép toàn bộ request parameter map một cách mù quáng.

## 3. Viết AuthenticationConverter

### 3.1. Converter nhận diện grant type

Spring Authorization Server dùng một chuỗi AuthenticationConverter tại Token Endpoint. Mỗi converter thử nhận diện request mà nó hiểu.

Hợp đồng quan trọng:

- Nếu grant_type không thuộc extension này, trả null để converter tiếp theo xử lý.
- Nếu grant_type đúng nhưng request sai cú pháp, ném OAuth2AuthenticationException với invalid_request.
- Nếu request hợp lệ về cú pháp, tạo PartnerTicketGrantAuthenticationToken.
- Không xác thực nội dung ticket hoặc consume ticket tại đây.

Converter được gọi trong filter chain sau khi client authentication đã được xử lý. Client principal hiện tại có thể lấy từ SecurityContextHolder. Không tin client_id trong form body thay cho principal đã xác thực.

### 3.2. Mã AuthenticationConverter

~~~java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.util.StringUtils;

public final class PartnerTicketGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String[] grantTypes =
                request.getParameterMap().get(OAuth2ParameterNames.GRANT_TYPE);

        if (grantTypes == null || grantTypes.length == 0) {
            return null;
        }

        boolean containsPartnerTicketGrant = Arrays.stream(grantTypes)
                .anyMatch(PartnerTicketGrantTypes.PARTNER_TICKET.getValue()::equals);
        if (!containsPartnerTicketGrant) {
            return null;
        }

        if (grantTypes.length != 1
                || !PartnerTicketGrantTypes.PARTNER_TICKET.getValue()
                        .equals(grantTypes[0])) {
            throw invalidRequest();
        }

        String[] tickets = request.getParameterMap().get(
                PartnerTicketGrantTypes.PARTNER_TICKET_PARAMETER);

        if (tickets == null || tickets.length != 1
                || !StringUtils.hasText(tickets[0])) {
            throw invalidRequest();
        }

        Set<String> requestedScopes = parseScopes(request);

        Authentication clientPrincipal =
                SecurityContextHolder.getContext().getAuthentication();

        if (clientPrincipal == null) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_CLIENT);
        }

        return new PartnerTicketGrantAuthenticationToken(
                tickets[0],
                clientPrincipal,
                requestedScopes);
    }

    private static Set<String> parseScopes(HttpServletRequest request) {
        String[] scopeParameters =
                request.getParameterMap().get(OAuth2ParameterNames.SCOPE);

        if (scopeParameters == null) {
            return Set.of();
        }

        if (scopeParameters.length != 1
                || !StringUtils.hasText(scopeParameters[0])) {
            throw invalidRequest();
        }

        return Arrays.stream(scopeParameters[0].trim().split("\\s+"))
                .filter(StringUtils::hasText)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private static OAuth2AuthenticationException invalidRequest() {
        return new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
    }
}
~~~

Đây là converter dành cho một grant cụ thể. Nó chỉ parse hai tham số được định nghĩa trong ví dụ: ticket và scope. Các tham số client authentication như client_id/client_secret được filter client authentication xử lý riêng; converter không dùng chúng để xác định danh tính client.

### 3.3. Vì sao phải kiểm tra số lần xuất hiện của tham số?

HTTP form có thể chứa nhiều giá trị cho cùng một parameter. Nếu converter chỉ gọi getParameter(), servlet thường trả về giá trị đầu tiên và có thể che giấu request mơ hồ.

Với ticket, request phải có chính xác một giá trị. Với scope, ví dụ này cũng yêu cầu một parameter scope duy nhất chứa danh sách scope phân tách bằng dấu cách.

Các trường hợp cần từ chối:

| Request | Kết quả |
|---|---|
| Không có grant_type | Converter trả null. |
| Grant type khác | Converter trả null. |
| Grant type đúng, thiếu ticket | invalid_request. |
| Ticket rỗng | invalid_request. |
| Ticket xuất hiện nhiều lần | invalid_request. |
| Scope xuất hiện nhiều lần | invalid_request. |
| Scope rỗng nhưng có parameter | invalid_request. |
| Request đúng cú pháp | Trả PartnerTicketGrantAuthenticationToken. |

Nếu extension có thêm tham số như audience, tenant hoặc assertion type, hãy xác định cú pháp, cardinality và quy tắc validation riêng cho từng trường. Không lấy tùy tiện giá trị đầu tiên của mọi parameter rồi đưa vào additionalParameters.

### 3.4. Converter không thực hiện nghiệp vụ

Không nên gọi PartnerTicketService.consume() trong converter. Converter có nhiệm vụ chuyển đổi request thành Authentication object. Việc xác minh chữ ký, thời hạn, audience, trạng thái đã dùng, subject và quyền scope thuộc provider/domain service.

Tách trách nhiệm như vậy giúp:
- Converter không gây side effect khi filter chain thử nhiều converter.
- Provider là nơi duy nhất quyết định grant có hợp lệ hay không.
- Unit test của converter không cần database hoặc hệ thống đối tác.
- Có thể thay đổi cách xác minh ticket mà không phải sửa cách parse HTTP.

## 4. Viết AuthenticationProvider

### 4.1. Provider xác minh grant và cấp access token

AuthenticationProvider xử lý PartnerTicketGrantAuthenticationToken. Các bước chính:

1. Xác nhận client principal là OAuth2ClientAuthenticationToken đã authenticated.
2. Lấy RegisteredClient từ client principal.
3. Xác nhận client đã đăng ký grant type PARTNER_TICKET.
4. Xác minh ticket bằng domain service.
5. Ràng buộc ticket với client, audience, subject, expiry và scope.
6. Tạo OAuth2TokenContext.
7. Gọi OAuth2TokenGenerator để tạo access token.
8. Tạo và lưu OAuth2Authorization.
9. Trả OAuth2AccessTokenAuthenticationToken cho Token Endpoint filter.

Provider không tự ghi JSON hoặc HTTP status. Token Endpoint filter và success/error handler chuẩn sẽ serialize kết quả.

### 4.2. Contract cho dịch vụ xác minh ticket

Ví dụ định nghĩa domain service:

~~~java
import java.util.Optional;
import java.util.Set;

import org.springframework.security.core.Authentication;

public interface PartnerTicketService {

    Optional<ConsumedPartnerTicket> consume(
            String ticket,
            String clientId,
            Set<String> requestedScopes,
            Set<String> clientAllowedScopes);
}
~~~

Kết quả xác minh:

~~~java
import java.util.Set;

import org.springframework.security.core.Authentication;

public record ConsumedPartnerTicket(
        Authentication subjectPrincipal,
        Set<String> authorizedScopes,
        String grantId) {

    public ConsumedPartnerTicket {
        authorizedScopes = Set.copyOf(authorizedScopes);
    }
}
~~~

Contract của service phải bảo đảm:

- Ticket tồn tại, chưa hết hạn và có chữ ký/integrity hợp lệ nếu dùng signed ticket.
- Ticket được phát hành cho đúng client hoặc audience.
- Ticket chưa được sử dụng.
- Ticket gắn với subject đã được xác thực.
- Requested scopes là tập con của quyền trong ticket và quyền client được cấp.
- Nếu client không gửi scope, service chọn default scopes theo policy.
- Việc kiểm tra và consume ticket dùng một lần phải có tính atomic.

Service trả Optional.empty() khi ticket không hợp lệ, hết hạn, đã dùng hoặc không dành cho client. Lỗi hạ tầng như database timeout cần được phân biệt với ticket invalid; không biến outage thành invalid_grant.

### 4.3. Mã AuthenticationProvider

~~~java
import java.util.Optional;
import java.util.Set;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.ClaimAccessor;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AccessTokenAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.security.oauth2.server.authorization.token.DefaultOAuth2TokenContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;
import org.springframework.util.Assert;

public final class PartnerTicketGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;
    private final PartnerTicketService partnerTicketService;

    public PartnerTicketGrantAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator,
            PartnerTicketService partnerTicketService) {

        Assert.notNull(authorizationService,
                "authorizationService cannot be null");
        Assert.notNull(tokenGenerator,
                "tokenGenerator cannot be null");
        Assert.notNull(partnerTicketService,
                "partnerTicketService cannot be null");

        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
        this.partnerTicketService = partnerTicketService;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        PartnerTicketGrantAuthenticationToken grant =
                (PartnerTicketGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
                getAuthenticatedClientElseThrowInvalidClient(grant);

        RegisteredClient registeredClient =
                clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(PartnerTicketGrantTypes.PARTNER_TICKET)) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        Optional<ConsumedPartnerTicket> consumedTicket =
                this.partnerTicketService.consume(
                        grant.getTicket(),
                        registeredClient.getClientId(),
                        grant.getRequestedScopes(),
                        registeredClient.getScopes());

        ConsumedPartnerTicket consumed = consumedTicket
                .orElseThrow(() -> new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_GRANT));

        Authentication subjectPrincipal = consumed.subjectPrincipal();
        Set<String> authorizedScopes = consumed.authorizedScopes();

        if (subjectPrincipal == null || !subjectPrincipal.isAuthenticated()) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_GRANT);
        }

        if (authorizedScopes.isEmpty()
                || !registeredClient.getScopes().containsAll(authorizedScopes)
                || !authorizedScopes.containsAll(grant.getRequestedScopes())) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext =
                DefaultOAuth2TokenContext.builder()
                        .registeredClient(registeredClient)
                        .principal(subjectPrincipal)
                        .authorizationServerContext(
                                AuthorizationServerContextHolder.getContext())
                        .authorizedScopes(authorizedScopes)
                        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                        .authorizationGrantType(grant.getGrantType())
                        .authorizationGrant(grant)
                        .build();

        OAuth2Token generatedToken =
                this.tokenGenerator.generate(tokenContext);

        if (generatedToken == null) {
            OAuth2Error error = new OAuth2Error(
                    OAuth2ErrorCodes.SERVER_ERROR,
                    "The token generator failed to generate the access token.",
                    null);
            throw new OAuth2AuthenticationException(error);
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                generatedToken.getTokenValue(),
                generatedToken.getIssuedAt(),
                generatedToken.getExpiresAt(),
                authorizedScopes);

        OAuth2Authorization.Builder authorizationBuilder =
                OAuth2Authorization.withRegisteredClient(registeredClient)
                        .principalName(subjectPrincipal.getName())
                        .authorizationGrantType(grant.getGrantType())
                        .authorizedScopes(authorizedScopes)
                        .attribute("partner_ticket_grant_id",
                                consumed.grantId());

        if (generatedToken instanceof ClaimAccessor claimAccessor) {
            authorizationBuilder.token(accessToken, metadata ->
                    metadata.put(
                            OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                            claimAccessor.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        OAuth2Authorization authorization = authorizationBuilder.build();
        this.authorizationService.save(authorization);

        return new OAuth2AccessTokenAuthenticationToken(
                registeredClient,
                clientPrincipal,
                accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return PartnerTicketGrantAuthenticationToken.class
                .isAssignableFrom(authentication);
    }

    private static OAuth2ClientAuthenticationToken
            getAuthenticatedClientElseThrowInvalidClient(
                    Authentication authentication) {

        Object principal = authentication.getPrincipal();

        if (principal instanceof OAuth2ClientAuthenticationToken clientPrincipal
                && clientPrincipal.isAuthenticated()
                && clientPrincipal.getRegisteredClient() != null) {
            return clientPrincipal;
        }

        throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_CLIENT);
    }
}
~~~

Đây là ví dụ provider cho access token. Nó không phát refresh token. Nếu nghiệp vụ cần refresh token, phải thiết kế riêng chính sách cấp, lưu, rotate, reuse detection và revoke; không tự động thêm refresh token chỉ vì Token Endpoint response hỗ trợ trường này.

### 4.4. Vì sao cần kiểm tra RegisteredClient?

Client authentication thành công chỉ chứng minh client sở hữu credential hợp lệ. Nó không có nghĩa client được phép dùng mọi grant.

RegisteredClient phải khai báo grant type extension:

~~~java
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient partnerClient =
        RegisteredClient.withId("partner-client-registration-id")
                .clientId("partner-integration")
                .clientSecret(passwordEncoder.encode(partnerClientSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        PartnerTicketGrantTypes.PARTNER_TICKET)
                .scope("orders.read")
                .scope("orders.write")
                .build();
~~~

Secret phải được hash bằng PasswordEncoder phù hợp. RegisteredClient cần được lưu qua RegisteredClientRepository. Không đưa secret plaintext vào source code hoặc migration production.

Nếu client chưa đăng ký grant type, provider trả **unauthorized_client**. Nếu client chưa xác thực, provider trả **invalid_client**. Hai lỗi này có ý nghĩa khác nhau.

### 4.5. Scope phải bị giới hạn ở cả client và grant

Có hai tập quyền cần kiểm tra:

- Scope client được phép yêu cầu theo RegisteredClient.
- Scope ticket hoặc authorization artifact thực sự cấp.

Scope cuối cùng phải nằm trong giao của hai tập đó. Nếu client yêu cầu scope ngoài quyền của client hoặc ticket, từ chối bằng invalid_scope.

Không tin scope do client gửi và không copy toàn bộ scope trong ticket sang access token nếu ticket chưa được kiểm tra audience, client binding và subject.

### 4.6. Tạo token bằng OAuth2TokenGenerator

OAuth2TokenContext truyền các thông tin cần thiết cho token generator:

| Thuộc tính | Ý nghĩa |
|---|---|
| registeredClient | Client đang yêu cầu token. |
| principal | Subject đã được xác minh từ ticket service. |
| authorizationServerContext | Context của Authorization Server đang xử lý request. |
| authorizedScopes | Scope đã được cấp sau khi kiểm tra. |
| tokenType | Loại token cần tạo, ở đây là access_token. |
| authorizationGrantType | Grant type extension. |
| authorizationGrant | AuthenticationToken của grant hiện tại. |

OAuth2TokenGenerator có thể tạo JWT hoặc reference/opaque access token tùy generator và token settings. Nếu không có generator nào hỗ trợ token context, generate() có thể trả null; provider phải trả server_error thay vì tạo token rỗng.

Nếu ứng dụng tự cấu hình token generator, hãy bảo đảm generator hỗ trợ định dạng token được RegisteredClient yêu cầu. Với JWT, cần JWK/NimbusJwtEncoder và signing key phù hợp. Với reference token, cần OAuth2AccessTokenGenerator và Resource Server/introspection path tương ứng.

Ví dụ một generator chain có thể tạo JWT hoặc reference access token và hỗ trợ refresh token cho các grant chuẩn khác:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Bean
OAuth2TokenGenerator<?> tokenGenerator(
        JWKSource<SecurityContext> jwkSource) {

    JwtGenerator jwtGenerator =
            new JwtGenerator(new NimbusJwtEncoder(jwkSource));
    OAuth2AccessTokenGenerator accessTokenGenerator =
            new OAuth2AccessTokenGenerator();
    OAuth2RefreshTokenGenerator refreshTokenGenerator =
            new OAuth2RefreshTokenGenerator();

    return new DelegatingOAuth2TokenGenerator(
            jwtGenerator,
            accessTokenGenerator,
            refreshTokenGenerator);
}
~~~

Đây là ví dụ generator chain theo hướng dẫn SAS. Nếu ứng dụng đã có token generator được cấu hình và quản lý tập trung, hãy inject bean hiện có vào provider thay vì tạo thêm chain khác. Việc chain hỗ trợ refresh token không có nghĩa provider của partner-ticket tự phát refresh token; provider trong bài chỉ yêu cầu ACCESS_TOKEN.

### 4.7. Vì sao phải lưu OAuth2Authorization?

Sau khi tạo access token, provider lưu OAuth2Authorization thông qua OAuth2AuthorizationService. Authorization lưu registered client, principal, grant type, scope, token và metadata.

Việc lưu authorization cho phép các thành phần khác của Authorization Server tra cứu token, introspection, revocation và các lifecycle operation. Không bỏ qua bước này chỉ vì JWT có thể được Resource Server xác minh offline.

Trong ví dụ, provider lưu grantId thay vì raw ticket. Raw ticket là credential dùng một lần và không nên được lưu hoặc log nếu không có yêu cầu bảo mật rõ ràng.

## 5. Đăng ký converter và provider vào Token Endpoint

### 5.1. Cấu hình endpoint

Spring Authorization Server 1.5.8 cung cấp OAuth2TokenEndpointConfigurer với hai extension points:

- **accessTokenRequestConverter(...)** thêm AuthenticationConverter.
- **authenticationProvider(...)** thêm AuthenticationProvider.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        PartnerTicketGrantAuthenticationConverter converter,
        PartnerTicketGrantAuthenticationProvider provider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
            .with(configurer, authorizationServer ->
                    authorizationServer.tokenEndpoint(tokenEndpoint ->
                            tokenEndpoint
                                    .accessTokenRequestConverter(converter)
                                    .authenticationProvider(provider)))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Hai phương thức trên thêm converter/provider vào cấu hình Token Endpoint. Các converter/provider grant chuẩn của Spring Authorization Server vẫn được giữ lại. Converter mới trả null với grant type không thuộc nó, để các converter mặc định tiếp tục xử lý.

Nếu dùng accessTokenRequestConverters(...) hoặc authenticationProviders(...), API cung cấp Consumer để truy cập danh sách mặc định và tùy chỉnh danh sách. Hãy thêm phần tử vào danh sách hoặc decorate provider phù hợp; không thay toàn bộ danh sách nếu không có lý do và không muốn vô tình xóa grant chuẩn.

### 5.2. Token Endpoint vẫn dùng client authentication chuẩn

OAuth2 Token Endpoint filter xử lý grant request sau client authentication. Vì vậy:

- Client credentials được xác minh bởi client authentication filter/provider.
- Converter lấy client principal từ SecurityContextHolder.
- Provider kiểm tra principal đó là OAuth2ClientAuthenticationToken đã authenticated.
- Không tự xác minh client secret lần thứ hai trong converter.
- Không dùng client_id trong body làm bằng chứng danh tính.

Nếu ứng dụng dùng client_secret_post, client_secret_basic, private_key_jwt hoặc mTLS, hãy để client authentication configurer xử lý theo RegisteredClient. Custom grant chỉ bổ sung bước xác minh authorization artifact.

### 5.3. Request lấy token

Ví dụ request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_PARTNER_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Apartner-ticket&example_partner_ticket=ONE_TIME_TICKET&scope=orders.read
~~~

Nếu request hợp lệ và grant được cấp, Token Endpoint trả response chuẩn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Token Endpoint filter dùng OAuth2AccessTokenAuthenticationToken do provider trả về để tạo response. Provider không tự viết JSON response.

## 6. Error semantics cho custom grant

Provider và converter phải dùng các OAuth2 error code phù hợp. Không trả thông tin nội bộ về ticket, subject, database hoặc chữ ký cho client.

| Tình huống | OAuth2 error | Ý nghĩa |
|---|---|---|
| Thiếu ticket, ticket rỗng hoặc parameter lặp | invalid_request | Request không đúng cú pháp. |
| Client authentication thất bại | invalid_client | Client không được xác thực. |
| Client chưa đăng ký grant type | unauthorized_client | Client đã xác thực nhưng không được phép dùng grant. |
| Ticket sai, hết hạn, replay hoặc không thuộc client | invalid_grant | Authorization artifact không hợp lệ. |
| Scope vượt quyền client/ticket | invalid_scope | Scope được yêu cầu không được phép. |
| Token generator không tạo được token | server_error | Lỗi xử lý nội bộ. |
| Ticket service hoặc database gặp lỗi hạ tầng | server_error | Không thể hoàn tất xử lý do lỗi dịch vụ. |

### 6.1. Không tiết lộ nguyên nhân nhạy cảm

Không trả các thông báo như:
- Ticket tồn tại nhưng đã bị dùng bởi một client khác.
- Ticket thuộc một người dùng cụ thể.
- Subject bị khóa hoặc account không tồn tại.
- Chữ ký ticket sai ở byte nào.
- Database hoặc dịch vụ xác minh nào đang lỗi.

Có thể log category đã chuẩn hóa và correlation ID nội bộ. Không log raw ticket, client secret hoặc access token.

### 6.2. Phân biệt invalid_grant với server_error

Ticket sai hoặc hết hạn là lỗi authorization artifact, ánh xạ thành invalid_grant. Database timeout khi kiểm tra ticket là lỗi hạ tầng; không được giả vờ ticket invalid vì hệ thống chưa thể xác minh.

Tách exception của domain service theo nhóm:
- Invalid/expired/replayed ticket: kết quả không hợp lệ, trả invalid_grant.
- Client/audience/scope mismatch: từ chối grant hoặc scope theo policy.
- Database/remote service unavailable: lỗi server.
- Lỗi lập trình hoặc token generator: lỗi server và cần alert.

## 7. Bảo vệ ticket và grant lifecycle

### 7.1. Ticket phải có vòng đời ngắn và ràng buộc rõ

Một ticket được dùng làm authorization grant cần có các thuộc tính tối thiểu:

- Entropy đủ cao nếu ticket là opaque random value.
- Thời hạn ngắn và kiểm tra expiry ở server.
- Audience hoặc client binding rõ ràng.
- Subject được xác định từ nguồn tin cậy.
- Scope được cấp cụ thể.
- Trạng thái one-time-use/replay được lưu và kiểm tra atomic.
- Có issuer/signature validation nếu ticket là signed artifact.
- Không thể tái sử dụng sau khi đã consume.

Không nhận một ticket chỉ vì nó có định dạng JWT hoặc có chữ ký. Phải xác minh thuật toán, issuer, audience, expiry, key trust, token purpose và replay policy.

### 7.2. Consume phải atomic

Hai request đồng thời có thể gửi cùng một ticket. Nếu service thực hiện thao tác “đọc chưa dùng” rồi “đánh dấu đã dùng” tách rời, cả hai request có thể cùng nhận kết quả hợp lệ.

Dùng transaction, compare-and-set, unique constraint hoặc một cơ chế atomic consume để chỉ một request thắng. Test race condition bằng nhiều request đồng thời.

### 7.3. Ticket consumption và token persistence cần transaction plan

Trong provider, ticket có thể được consume trước khi token generator tạo token và authorization được lưu. Nếu token generation hoặc authorization save thất bại sau khi consume, client có thể mất khả năng retry.

Nếu ticket store và authorization store cùng database, cân nhắc transaction bao trùm việc consume và lưu authorization. Nếu hai hệ thống độc lập, thiết kế reservation/commit hoặc idempotency key để xử lý retry an toàn. Không giữ ticket ở trạng thái có thể tái sử dụng chỉ để thuận tiện retry.

### 7.4. Không tự động phát refresh token

Extension grant trong ví dụ chỉ phát access token. Nếu phát refresh token, phải trả lời:

- Client có được phép nhận refresh token không?
- Refresh token có còn gắn với cùng subject và scope không?
- Có rotate mỗi lần refresh không?
- Có reuse detection và revoke family không?
- User deprovisioning hoặc ticket revocation ảnh hưởng thế nào?
- AuthorizationService lưu refresh token và metadata ra sao?

Không thêm OAuth2RefreshTokenGenerator vào provider rồi mặc định refresh flow sẽ an toàn. Refresh token phải có policy riêng.

### 7.5. Giới hạn scope và audience

Access token phải có audience/resource phù hợp với API đích. Nếu extension token được phát cho nhiều API, cần policy rõ ràng cho từng resource. Không để ticket do một đối tác cấp có thể yêu cầu mọi scope chỉ vì client đăng ký nhiều scope.

Scope cuối cùng phải bị giới hạn bởi:
1. Scope mà RegisteredClient được phép dùng.
2. Scope ticket đã cấp.
3. Scope mà authorization policy của subject cho phép.
4. Resource/audience mà token được phát hành cho.

## 8. Kiểm thử AuthenticationToken, Converter và Provider

### 8.1. Unit test cho AuthenticationToken

Kiểm tra:
- Grant type đúng với hằng số.
- Client principal được giữ nguyên.
- Ticket được lưu để provider xác minh.
- Requested scopes là immutable.
- getCredentials() trả ticket trong lúc xử lý.
- eraseCredentials() xóa ticket sau khi xử lý.

Không kiểm tra ticket bằng cách in toàn bộ AuthenticationToken ra test log.

### 8.2. Unit test cho AuthenticationConverter

| Test case | Kết quả |
|---|---|
| grant_type khác | Trả null. |
| Không có grant_type | Trả null. |
| grant_type đúng, ticket thiếu | invalid_request. |
| ticket rỗng | invalid_request. |
| ticket lặp nhiều lần | invalid_request. |
| scope lặp nhiều lần | invalid_request. |
| scope hợp lệ | Tạo Set scope đúng. |
| Client principal có trong SecurityContext | Được gắn vào AuthenticationToken. |
| Client principal không có | invalid_client. |

Ví dụ test cấu trúc:

~~~java
@Test
void returnsNullForDifferentGrantType() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setParameter(
            OAuth2ParameterNames.GRANT_TYPE,
            AuthorizationGrantType.CLIENT_CREDENTIALS.getValue());

    Authentication result = converter.convert(request);

    assertThat(result).isNull();
}
~~~

Test request thiếu ticket:

~~~java
@Test
void rejectsRequestWithoutTicket() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setParameter(
            OAuth2ParameterNames.GRANT_TYPE,
            PartnerTicketGrantTypes.PARTNER_TICKET.getValue());

    assertThatThrownBy(() -> converter.convert(request))
            .isInstanceOf(OAuth2AuthenticationException.class);
}
~~~

Các ví dụ dùng MockHttpServletRequest và AssertJ; cần import test dependencies tương ứng trong project.

### 8.3. Unit test cho AuthenticationProvider

Các tình huống cần có:

- Authentication không phải PartnerTicketGrantAuthenticationToken: supports() trả false.
- Client principal không authenticated: invalid_client.
- Client không đăng ký grant type: unauthorized_client.
- Ticket sai/hết hạn/replayed: invalid_grant.
- Ticket thuộc client khác: invalid_grant.
- Scope ngoài RegisteredClient hoặc ticket: invalid_scope.
- Subject principal không authenticated: từ chối grant.
- Token generator trả null: server_error.
- Token được tạo: OAuth2AuthorizationService.save() được gọi.
- Token claims được lưu metadata nếu generated token triển khai ClaimAccessor.
- Response Authentication là OAuth2AccessTokenAuthenticationToken.
- Scope trong access token và OAuth2Authorization đúng với scope đã cấp.

### 8.4. Integration test cho Token Endpoint

Sử dụng MockMvc hoặc test client để gọi endpoint thật với client authentication:

1. Đăng ký client có grant type PARTNER_TICKET.
2. Cấu hình converter/provider trong Authorization Server SecurityFilterChain.
3. Cấp ticket fixture hợp lệ cho đúng client.
4. POST form request tới /oauth2/token.
5. Kiểm tra HTTP 200, access_token, token_type, expires_in và scope.
6. Xác minh authorization đã được lưu.
7. Gửi lại cùng ticket và xác nhận request thứ hai bị từ chối.
8. Gửi request bằng client không được đăng ký grant và xác nhận unauthorized_client.
9. Gửi grant type chuẩn như client_credentials và xác nhận converter custom trả null, flow mặc định vẫn hoạt động.
10. Kiểm tra token được Resource Server chấp nhận hoặc introspection trả active theo cấu hình.

### 8.5. Kiểm tra concurrency và failure

Không dừng ở test đơn request. Hãy kiểm thử:

- Hai request consume cùng ticket đồng thời.
- Ticket service timeout.
- AuthorizationService.save() thất bại sau khi ticket được consume.
- Token generator lỗi.
- Retry sau timeout ở client.
- Nhiều Authorization Server instances cùng xác minh ticket.
- Đồng hồ giữa ticket issuer và Authorization Server lệch nhau.
- Ticket bị revoke trong lúc request đang xử lý.

## 9. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Request custom grant trả unsupported_grant_type | Converter không được đăng ký hoặc grant_type URI không khớp. | Kiểm tra converter, URI và thứ tự Token Endpoint configuration. |
| Converter không được gọi | Token Endpoint filter chain không chứa converter hoặc request không vào endpoint matcher. | Kiểm SecurityFilterChain và accessTokenRequestConverter. |
| Grant type không được hỗ trợ dù converter chạy | RegisteredClient không đăng ký grant type. | Thêm AuthorizationGrantType vào RegisteredClient. |
| Client bị invalid_client | Client authentication chưa thành công hoặc converter/provider không nhận đúng client principal. | Kiểm client auth filter, SecurityContext và RegisteredClient. |
| Client nhận unauthorized_client | Client đã authenticated nhưng không được phép grant. | Kiểm RegisteredClient.authorizationGrantTypes. |
| Ticket hợp lệ vẫn invalid_grant | Ticket binding sai client/audience, expiry, replay hoặc clock skew. | Kiểm domain service và test fixture. |
| Ticket có thể dùng hai lần | Consume không atomic hoặc replay state không shared giữa nodes. | Dùng transaction/unique constraint/atomic update. |
| Token thiếu scope | Provider không đưa authorizedScopes vào token context hoặc access token. | Kiểm token context và OAuth2AccessToken scopes. |
| Token có scope vượt quyền | Tin scope client gửi hoặc không giao với ticket scopes. | Kiểm scope ở provider/domain service. |
| Access token trả về nhưng introspection inactive | Authorization không được lưu hoặc token metadata/lookup không khớp. | Kiểm OAuth2AuthorizationService và token persistence. |
| Client credentials grant chuẩn bị hỏng | Custom configurer thay toàn bộ converter/provider list. | Dùng phương thức add hoặc bảo toàn danh sách mặc định. |
| Ticket bị lộ trong logs | Logging toàn bộ request, Authentication hoặc exception. | Redact tham số và credentials; log correlation ID. |
| Retry làm mất ticket | Ticket bị consume trước khi token persistence thất bại. | Thiết kế reservation/commit hoặc idempotency. |
| Token generator trả null | Generator không hỗ trợ token type/format đã yêu cầu. | Kiểm generator chain, JWK và TokenSettings. |
| Token không đúng audience | Token customizer/policy không gắn resource/audience phù hợp. | Xác định resource policy và kiểm Resource Server. |

## 10. Bài tập thực hành

**Bối cảnh:** một đối tác thanh toán gửi ticket ngắn hạn cho client partner-integration. Ticket được cấp sau khi người dùng xác nhận giao dịch. Authorization Server phải đổi ticket thành access token chỉ có scope orders.read.

### Yêu cầu

1. Định nghĩa grant type absolute URI cho partner-ticket.
2. Định nghĩa tham số ticket riêng có namespace rõ ràng.
3. Tạo PartnerTicketGrantAuthenticationToken kế thừa OAuth2AuthorizationGrantAuthenticationToken.
4. Viết converter nhận diện grant_type, kiểm tra ticket, scope và parameter cardinality.
5. Đảm bảo converter trả null cho grant type không thuộc nó.
6. Tạo PartnerTicketService để xác minh ticket, client binding, audience, expiry và replay.
7. Viết provider kiểm tra OAuth2ClientAuthenticationToken và RegisteredClient grant type.
8. Giới hạn scope theo client và ticket.
9. Tạo OAuth2TokenContext và phát access token.
10. Lưu OAuth2Authorization bằng OAuth2AuthorizationService.
11. Đăng ký converter/provider bằng OAuth2TokenEndpointConfigurer.
12. Kiểm thử request hợp lệ, ticket replay, sai client, scope escalation và token generator failure.
13. Kiểm thử hai request đồng thời dùng cùng ticket.
14. Xác nhận client_credentials grant chuẩn vẫn hoạt động.
15. Viết runbook cho ticket service outage, token persistence failure và key rotation.

**Tiêu chí hoàn thành:** custom grant hoạt động tại /oauth2/token; client được xác thực độc lập; ticket được kiểm tra và consume một lần; scope không vượt policy; access token được sinh bởi OAuth2TokenGenerator và authorization được lưu; các grant chuẩn vẫn hoạt động.

## 11. Checklist trước khi triển khai production

- [ ] Grant type dùng absolute URI duy nhất.
- [ ] Các token endpoint parameters có tên riêng và cú pháp được tài liệu hóa.
- [ ] Đã xem xét đăng ký extension theo RFC 6749.
- [ ] AuthenticationToken kế thừa OAuth2AuthorizationGrantAuthenticationToken.
- [ ] Converter chỉ parse request và không consume grant.
- [ ] Converter trả null cho grant type khác.
- [ ] Duplicate/missing/empty parameters được kiểm tra.
- [ ] Client principal lấy từ SecurityContextHolder sau client authentication.
- [ ] Provider kiểm tra OAuth2ClientAuthenticationToken đã authenticated.
- [ ] RegisteredClient phải cho phép grant type extension.
- [ ] Ticket kiểm tra issuer, signature/integrity, expiry, audience, client binding và replay.
- [ ] Consume ticket có tính atomic giữa nhiều request và nhiều instance.
- [ ] Scope được giới hạn bởi RegisteredClient và authorization artifact.
- [ ] Subject principal được lấy từ nguồn tin cậy.
- [ ] OAuth2TokenContext chứa đúng registered client, principal, grant type, scopes và grant token.
- [ ] Token được tạo bằng OAuth2TokenGenerator.
- [ ] OAuth2Authorization được lưu qua OAuth2AuthorizationService.
- [ ] Không log ticket, client secret hoặc access token.
- [ ] Error response dùng invalid_request, invalid_client, unauthorized_client, invalid_grant, invalid_scope hoặc server_error đúng trường hợp.
- [ ] Token Endpoint success/error handler chuẩn được giữ.
- [ ] Converter/provider mặc định của Spring Authorization Server vẫn hoạt động.
- [ ] Refresh token chỉ được phát nếu có policy riêng.
- [ ] Có unit, integration, replay, concurrency và failure tests.
- [ ] Có transaction/idempotency plan cho ticket consume và authorization save.
- [ ] Có rate limit, monitoring, alert và runbook cho ticket service.

## Tổng kết

Spring Authorization Server 1.5.8 mở rộng Token Endpoint thông qua AuthenticationConverter và AuthenticationProvider. Converter nhận diện grant_type, kiểm tra cú pháp request và tạo một AuthenticationToken kế thừa OAuth2AuthorizationGrantAuthenticationToken. Provider xử lý token đó, kiểm tra client và RegisteredClient, xác minh authorization artifact, tạo OAuth2TokenContext, gọi OAuth2TokenGenerator và lưu OAuth2Authorization.

Thiết kế an toàn giữ converter không có side effect, xác thực client bằng pipeline chuẩn, kiểm tra grant type theo RegisteredClient, consume ticket có tính atomic, giới hạn scope và không để lộ credential. Việc đăng ký converter/provider phải giữ các implementation mặc định để Authorization Code, Refresh Token, Client Credentials và các grant chuẩn khác tiếp tục hoạt động.

Một extension grant chỉ hoàn chỉnh khi cả request parsing, grant validation, token generation, authorization persistence, error response và replay protection đều được kiểm thử.

## Tài liệu tham khảo

1. [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): ví dụ AuthenticationConverter, AuthenticationProvider, Token Endpoint configuration và request access token.
2. [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): accessTokenRequestConverter, authenticationProvider, response handler và error handler.
3. [Spring Authorization Server 1.5.8 — OAuth2AuthorizationGrantAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationGrantAuthenticationToken.html): base class cho Authentication biểu diễn authorization grant.
4. [Spring Authorization Server 1.5.8 — OAuth2ClientAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2ClientAuthenticationToken.html): authenticated client principal và RegisteredClient.
5. [Spring Authorization Server 1.5.8 — OAuth2AccessTokenAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AccessTokenAuthenticationToken.html): Authentication result dùng để trả access token response.
6. [Spring Authorization Server 1.5.8 — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html): token context và các thuộc tính generator cần.
7. [Spring Authorization Server 1.5.8 — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): tạo OAuth2Token từ OAuth2TokenContext và trường hợp trả null.
8. [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): authorization state và token lookup.
9. [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html): principal, grant type, scopes và token metadata.
10. [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): extension authorization grants và absolute URI grant_type.
11. [RFC 6749 — Section 8.3, Defining New Authorization Grant Types](https://www.rfc-editor.org/rfc/rfc6749.html#section-8.3): absolute URI cho grant type và yêu cầu đăng ký các token endpoint parameters bổ sung.
12. [RFC 6749 — Section 5.2, Error Response](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.2): OAuth2 token endpoint error codes.
13. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): các khuyến nghị bảo mật OAuth2 hiện hành.

