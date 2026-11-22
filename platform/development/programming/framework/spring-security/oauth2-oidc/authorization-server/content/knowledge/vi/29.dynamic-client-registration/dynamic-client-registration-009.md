# Giới hạn đăng ký, phê duyệt client và phòng chống SSRF từ URL metadata

## 1. Vì sao Dynamic Client Registration cần chính sách kiểm soát?

Trong một hệ thống **OAuth 2.0/OpenID Connect Authorization Server** sử dụng **Spring Security, Spring Authorization Server và Spring Boot**, Dynamic Client Registration (DCR) cho phép client hoặc developer gửi metadata để đăng ký OAuth/OIDC client mà không cần quản trị viên tạo từng bản ghi bằng tay.

Khả năng này hữu ích khi có nhiều ứng dụng, nhiều tenant, hệ sinh thái đối tác hoặc client được tạo theo vòng đời tự động. Nhưng mỗi lần đăng ký là một lần cấp danh tính và cấu hình bảo mật cho một ứng dụng có thể xin token, yêu cầu quyền và chuyển người dùng qua authorization flow.

Nếu endpoint đăng ký mở quá rộng, kẻ tấn công có thể:

- Tạo client giả mạo tên/logo của ứng dụng hợp pháp để lừa người dùng consent.
- Yêu cầu grant type, scope hoặc authentication method vượt nhu cầu.
- Đăng ký redirect URI do attacker kiểm soát để nhận authorization response.
- Đăng ký `jwks_uri` trỏ tới dịch vụ nội bộ để kích hoạt SSRF khi AS tải khóa.
- Đưa URL độc hại vào `logo_uri`, `policy_uri`, `tos_uri` hoặc `client_uri` để lừa người dùng; nếu AS tải nội dung về để hiển thị/scan, các URL đó cũng có thể tạo SSRF.
- Đăng ký callback server-to-server như `backchannel_logout_uri` trỏ vào mạng nội bộ nếu deployment hỗ trợ tính năng này.
- Tạo số lượng lớn client rác để làm đầy database, tăng chi phí và gây denial of service.

Vì vậy, DCR cần đồng thời kiểm soát **ai được đăng ký, client được phép khai báo điều gì, metadata nào được tin cậy và Authorization Server có thể truy cập mạng tới đâu**.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, mục tiêu là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server. Bài thuộc chương **Đăng ký client động**, tập trung vào giới hạn đăng ký, quy trình phê duyệt và phòng chống SSRF từ URL metadata.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt open registration, protected registration, initial access token và software statement.
2. Thiết kế quy trình phê duyệt client trước khi cấp quyền đăng ký.
3. Giới hạn redirect URI, grant type, token endpoint authentication method và scope.
4. Cấu hình DCR trong Spring Authorization Server 1.5.x, hiểu endpoint bị tắt mặc định và quyền `client.create`/`client.read`.
5. Giữ validator mặc định và thay riêng scope validator bằng allowlist.
6. Nhận diện metadata có thể khiến AS phát sinh outbound request.
7. Thiết kế SSRF defense ở cả registration-time, fetch-time và network egress.
8. Kiểm thử approval, quota, metadata validation, DNS rebinding, redirect bypass và credential lifecycle.

**Phạm vi ví dụ:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.8 trên Servlet stack. Các API DCR được minh họa theo tài liệu/Javadoc 1.5.8; hãy đối chiếu phiên bản thực tế của dự án trước khi triển khai.

## 2. Các thành phần và thuật ngữ

### 2.1. Client Registration Request và Client Registration Response

DCR theo RFC 7591/OIDC Dynamic Client Registration 1.0 sử dụng JSON metadata:

- **Registration Request:** client gửi thông tin mong muốn như `redirect_uris`, `grant_types`, `response_types`, `token_endpoint_auth_method`, `scope`, `client_name`, `jwks_uri`.
- **Registration Response:** OP cấp `client_id`, có thể cấp `client_secret`, và trả các metadata đã chấp nhận.
- **Initial Access Token:** access token do OP cấp cho developer/client để được phép gọi Registration Endpoint khi deployment dùng protected registration.
- **Registration Access Token:** bearer token do OP cấp sau khi đăng ký, dùng để truy cập Client Configuration Endpoint của chính client.
- **Software Statement:** JWT được ký/MAC bởi một issuer mà OP tin cậy, mang các metadata đã được attestation.

`initial_access_token` và `registration_access_token` có mục đích khác nhau. Initial token cho phép **tạo registration**; registration access token cho phép **quản lý registration đã tạo** theo khả năng endpoint mà OP triển khai. Không dùng lẫn hai token này.

### 2.2. Open registration và protected registration

| Mô hình | Ai gọi được endpoint? | Khi nào phù hợp? | Rủi ro chính |
| --- | --- | --- | --- |
| Open registration | Request không cần initial access token | Hệ sinh thái công khai cần onboarding tự phục vụ và có biện pháp chống abuse | Spam client, metadata giả mạo, resource exhaustion |
| Protected registration | Developer/client phải có initial access token hợp lệ | Hệ thống nội bộ, đối tác, B2B hoặc cần phê duyệt | Quản lý token cấp phát, rò rỉ và quyền quá rộng |
| Registration qua portal | Người dùng gửi hồ sơ cho portal; portal cấp initial token sau policy/review | Doanh nghiệp cần approval, audit và kiểm soát chủ sở hữu | Cần workflow và liên kết approval với đúng payload |

RFC 7591 định nghĩa initial access token là một cơ chế tùy chọn; khi OP giới hạn các bên được phép đăng ký, việc dùng initial access token là cần thiết. RFC không định nghĩa quy trình phê duyệt của doanh nghiệp. Approval portal, kiểm tra hợp đồng, xác minh chủ sở hữu domain và policy nội bộ là phần triển khai của từng OP.

### 2.3. Metadata tự khai báo không đồng nghĩa danh tính đã được xác minh

Nếu không được bảo vệ bởi software statement được ký bởi authority mà OP tin cậy, OP phải coi client metadata là **self-asserted**. Ví dụ:

- `client_name: "Corporate Payroll"` không chứng minh client thuộc công ty đó.
- `logo_uri` trỏ tới logo chính thức không chứng minh bên đăng ký là chủ sở hữu thương hiệu.
- `software_id` và `software_version` là dữ liệu do publisher khai báo, không tự xác thực được phần mềm.
- `client_uri` có domain giống redirect URI là tín hiệu để review, không phải bằng chứng sở hữu domain.

Software statement có chữ ký chỉ có giá trị attestation khi OP xác minh chữ ký, issuer, thời hạn, audience/đối tượng nhận, claim và trust policy. Nếu statement hợp lệ và được issuer chấp nhận, metadata trong statement phải được ưu tiên hơn các giá trị JSON xung đột theo quy tắc RFC. Tuy vậy, chữ ký không tự chứng minh mọi thông tin về deployment instance hoặc người gửi request.

## 3. Xác định chính sách đăng ký trước khi bật endpoint

### 3.1. Không phải ứng dụng nào cũng cần DCR

Spring Authorization Server **tắt OIDC Client Registration Endpoint theo mặc định** vì nhiều deployment không cần client tự đăng ký. Nếu số lượng client nhỏ và thay đổi hiếm, dùng quy trình quản trị `RegisteredClientRepository` có thể đơn giản và dễ kiểm soát hơn.

Chỉ bật DCR khi có use case cụ thể như:

- Developer portal tạo client cho đối tác sau khi được phê duyệt.
- Tenant quản lý nhiều ứng dụng độc lập.
- Hệ sinh thái plugin/integration cần onboarding tự phục vụ.
- Nền tảng cấp client theo môi trường hoặc theo vòng đời workload.

Nếu bật endpoint, phải thiết kế luôn authentication, authorization, rate limiting, metadata policy, persistence, audit và incident response.

### 3.2. Phân loại client

| Loại client | Grant thường dùng | Authentication method | Điều kiện cần xem xét |
| --- | --- | --- | --- |
| Web application phía server | `authorization_code`, có thể `refresh_token` | `client_secret_basic`, `private_key_jwt` hoặc mTLS | HTTPS redirect URI, secret/key rotation, PKCE nếu phù hợp |
| SPA chạy trong browser | `authorization_code` + PKCE | `none` | Public client, không cấp client secret, redirect URI chặt chẽ |
| Native application | `authorization_code` + PKCE | `none` hoặc phương thức theo profile | Loopback/custom scheme theo policy nền tảng, không nhúng secret dùng chung |
| Machine-to-machine | `client_credentials` | `private_key_jwt`, mTLS hoặc secret theo policy | Scope hẹp, owner rõ, key lifecycle |
| Client cần signed request object | Theo flow thực tế | Thường `private_key_jwt` hoặc key-based method | JWK Set tin cậy, `jwks_uri` và outbound fetch an toàn |

Không chấp nhận mọi grant type và authentication method chỉ vì thư viện hỗ trợ chúng. Tạo allowlist theo loại client và mục đích nghiệp vụ; từ chối tổ hợp grant không hợp lệ hoặc không được policy phê duyệt.

### 3.3. Bảng quyết định metadata

| Metadata | Policy khuyến nghị |
| --- | --- |
| `redirect_uris` | Bắt buộc cho redirect-based flow; HTTPS trong production web; exact allowlist; không wildcard |
| `post_logout_redirect_uris` | Đăng ký riêng; không tự sao chép từ `redirect_uris` |
| `grant_types` | Allowlist theo client type; chỉ cấp grant thực sự cần |
| `response_types` | Phù hợp grant/flow; tránh implicit trong thiết kế mới |
| `token_endpoint_auth_method` | Allowlist; public client dùng `none`, confidential client cần phương thức phù hợp |
| `scope` | Chỉ cấp scope OP hỗ trợ và client được phê duyệt |
| `jwks_uri` | HTTPS, SSRF policy, fetch-time egress enforcement và JWK schema validation |
| `jwks` | Nếu chấp nhận, kiểm tra JWK set; không cho private/symmetric key material |
| `client_name`, `logo_uri`, `client_uri`, `policy_uri`, `tos_uri` | Xem là dữ liệu tự khai báo; encode khi hiển thị và cảnh báo nguồn bên thứ ba |
| `software_id`, `software_version` | Đối chiếu inventory/attestation nếu cần chống impersonation hoặc duplicate |
| `sector_identifier_uri`, `request_uris`, `backchannel_logout_uri` | Chỉ bật khi feature cần thiết; áp dụng SSRF/egress policy tương ứng |

### 3.4. Giới hạn số lượng và kích thước

Một policy có thể xác định:

- Số registration mới mỗi developer/tenant/registrar trong một giờ/ngày.
- Tổng số client đang hoạt động theo tenant và theo issuer.
- Số redirect URI, grant type, response type, scope và metadata extension tối đa trên một client.
- Kích thước tối đa của JSON request, software statement, JWK Set và từng URL.
- Thời gian tồn tại của client tạm thời hoặc client không hoạt động.
- Số lần thử đăng ký thất bại và cooldown khi có dấu hiệu abuse.
- Giới hạn đồng thời của các tác vụ fetch metadata và scan logo.

Rate limit theo IP đơn thuần chưa đủ: NAT/proxy có thể làm nhiều developer chung một IP, còn botnet có thể đổi IP. Kết hợp principal/registrar, tenant, software identity, IP/network reputation và quota tổng.

## 4. Quy trình phê duyệt client

### 4.1. Approval không phải trạng thái có sẵn trong RFC 7591

DCR mô tả giao thức gửi metadata và nhận thông tin client. Nó không định nghĩa các trạng thái `PENDING`, `APPROVED`, `REJECTED` hay giao diện quản trị phê duyệt. Spring Authorization Server cung cấp endpoint và provider để xử lý đăng ký, nhưng không tự cung cấp một business approval workflow hoàn chỉnh.

Với deployment cần phê duyệt, hãy đặt bước review trước thời điểm cấp quyền gọi Registration Endpoint:

1. Developer gửi hồ sơ qua portal đã xác thực.
2. Hệ thống lưu metadata đề nghị và danh tính chủ sở hữu ở trạng thái pending.
3. Policy engine kiểm tra loại ứng dụng, domain, redirect URI, grant, scope, auth method, JWK và metadata URL.
4. Người phê duyệt xem thông tin, bằng chứng sở hữu và rủi ro.
5. Chỉ sau khi được duyệt, hệ thống mới cấp initial access token hoặc thực hiện registration thay mặt developer.
6. OP lưu registration, trả `client_id` và credential theo loại client.
7. Hệ thống ghi audit event và thông báo kết quả.

### 4.2. Gắn approval với đúng metadata đã được duyệt

Một lỗi thiết kế là duyệt hồ sơ A rồi cấp một initial access token dùng được cho bất kỳ payload nào. Người nhận token có thể thay `redirect_uris`, `grant_types`, `scope` hoặc `jwks_uri` sau khi được duyệt.

Approval nên gắn với:

- Tenant/organization và người chịu trách nhiệm.
- Client type, môi trường và use case.
- Danh sách redirect/post-logout URI.
- Grant type, response type và token endpoint authentication method.
- Scope được phép.
- JWK hoặc `jwks_uri` đã review.
- Các URL metadata/callback đã được kiểm tra.
- Phiên bản payload hoặc digest của canonical metadata đã duyệt.
- Hạn sử dụng, số lần dùng và registrar được phép dùng approval.

Khi đăng ký, server phải bảo đảm payload cuối cùng khớp nội dung được duyệt. Có thể để portal thực hiện registration từ bản ghi đã duyệt, hoặc bổ sung validator/gate kiểm tra payload digest trước khi provider lưu client. Việc cấp initial token đơn thuần không tự ràng buộc token với metadata cụ thể.

### 4.3. Các trạng thái và chuyển trạng thái gợi ý

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> NEEDS_CHANGES: Yêu cầu bổ sung
    NEEDS_CHANGES --> PENDING: Developer cập nhật
    PENDING --> REJECTED: Từ chối
    PENDING --> APPROVED: Review đạt
    APPROVED --> TOKEN_ISSUED: Cấp quyền đăng ký
    TOKEN_ISSUED --> REGISTERED: Registration thành công
    TOKEN_ISSUED --> EXPIRED: Hết hạn/chưa dùng
    REGISTERED --> SUSPENDED: Có sự cố hoặc vi phạm
    REGISTERED --> DEPROVISIONED: Thu hồi client
    SUSPENDED --> REGISTERED: Khôi phục sau review
    SUSPENDED --> DEPROVISIONED: Thu hồi vĩnh viễn
    REJECTED --> [*]
    EXPIRED --> [*]
    DEPROVISIONED --> [*]
```

Trạng thái trong sơ đồ thuộc approval service của deployment. Không coi đây là các trạng thái mà OIDC hoặc `RegisteredClient` tự cung cấp.

### 4.4. Checklist người phê duyệt

Người review nên trả lời:

- Ai sở hữu ứng dụng và ai chịu trách nhiệm vận hành?
- Domain/redirect URI có thuộc tổ chức hoặc vendor đã ký hợp đồng không?
- Client là public hay confidential? Có khai báo secret cho SPA/native app không?
- Grant type có phù hợp use case? Có yêu cầu grant không được phép không?
- Scope có vượt nhu cầu? Có quyền admin hoặc dữ liệu nhạy cảm không?
- Token endpoint auth method có phù hợp năng lực bảo vệ credential?
- JWK có hợp lệ, có public key, thuật toán được cho phép và key owner rõ?
- Metadata URL/callback có thể khiến OP gọi tới mạng nội bộ không?
- Có `software_id`/software statement để xác minh publisher không?
- Có thời hạn review lại, owner, contact và kế hoạch deprovision không?

## 5. Dynamic Client Registration trong Spring Authorization Server

### 5.1. Endpoint bị tắt theo mặc định

Spring Authorization Server 1.5.8 cung cấp OIDC Client Registration Endpoint, mặc định là:

```text
POST /connect/register
GET  <registration_client_uri được trả về trong registration response>
```

Path Registration Endpoint có thể đổi qua `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)`. Client Read phải dùng đúng `registration_client_uri` mà OP trả về; không tự suy ra path hoặc ghép `client_id` vào URL. Endpoint xử lý Client Registration và Client Read. **DCR bị tắt theo mặc định**; phải bật trong OIDC configurer của Authorization Server Security Filter Chain.

Đây là OAuth2 protected resource: request phải mang bearer access token. Spring Security Resource Server support được cấu hình cho endpoint, nhưng cần có bean `JwtDecoder` để xác minh access token.

### 5.2. Cấu hình endpoint và giữ các validator mặc định

Ví dụ cấu hình endpoint:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class DynamicClientRegistrationSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .oidc(oidc -> oidc
                    .clientRegistrationEndpoint(endpoint ->
                        endpoint.authenticationProviders(
                                registrationPolicy())))
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    private static Consumer<List<AuthenticationProvider>> registrationPolicy() {
        Set<String> allowedScopes = Set.of("openid", "profile", "email");

        return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registration) {
                registration.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_REDIRECT_URI_VALIDATOR
                        .andThen(OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                        .andThen(OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                        .andThen(scopeAllowlist(allowedScopes))
                );
            }
        });
    }

    private static Consumer<OidcClientRegistrationAuthenticationContext>
            scopeAllowlist(Set<String> allowedScopes) {

        return context -> {
            OidcClientRegistrationAuthenticationToken request =
                    context.getAuthentication();
            OidcClientRegistration registration = request.getClientRegistration();

            // Client Read request does not contain a new registration payload.
            if (registration == null) {
                return;
            }

            List<String> requestedScopes = registration.getScopes();
            if (requestedScopes != null
                    && !allowedScopes.containsAll(requestedScopes)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_client_metadata",
                        "One or more requested scopes are not permitted", null));
            }
        };
    }
}
```

Đây là ví dụ policy theo allowlist scope. Hãy bổ sung các rule grant type, response type, authentication method và redirect URI phù hợp client type. Các import và bean khác của Authorization Server (issuer, signing JWK, client repository, authorization service, login chain) vẫn phải được cấu hình trong ứng dụng.

Spring Authorization Server yêu cầu bean `JwtDecoder` để xác minh bearer access token gọi DCR endpoint. Nếu access token của AS là JWT được ký bởi JWK Set của chính AS, có thể cấu hình decoder theo issuer tin cậy:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder registrationAccessTokenDecoder() {
    String issuer = "https://auth.example.com";
    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(issuer + "/oauth2/jwks")
            .build();
    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(issuer));
    return decoder;
}
```

Đây là ví dụ cho JWT access token. Nếu hệ thống dùng token format khác, phải chọn decoder/introspection strategy phù hợp với implementation và phiên bản endpoint; không tắt signature/issuer validation để làm DCR hoạt động.

Ví dụ decoder kiểm tra issuer và thời gian mặc định. Nếu deployment phát hành audience riêng cho DCR endpoint, bổ sung audience validator tương ứng; không chỉ xác minh chữ ký mà bỏ qua issuer/audience policy.

### 5.3. Hiểu rõ bốn validator mặc định

Trong Spring Authorization Server 1.5.8, `OidcClientRegistrationAuthenticationValidator` cung cấp validator riêng cho các metadata quan trọng:

| Validator | Hành vi mặc định |
| --- | --- |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Từ chối URI có fragment, không có scheme hoặc dùng scheme không an toàn như `javascript`, `data`, `vbscript` |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Áp dụng cùng rule với redirect URI |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Từ chối `jwks_uri` không dùng HTTPS |
| `DEFAULT_SCOPE_VALIDATOR` | Từ chối request có scope không rỗng |

Validator cho `jwks_uri` chỉ xác nhận scheme HTTPS. Nó **không phải SSRF firewall**: một URL HTTPS có thể resolve tới IP private, loopback hoặc cloud metadata endpoint.

Hai nhóm validator `SIMPLE_*_VALIDATOR` giữ hành vi tương thích cũ:

- `SIMPLE_JWK_SET_URI_VALIDATOR` không validation `jwks_uri`.
- `SIMPLE_SCOPE_VALIDATOR` chấp nhận mọi scope.
- Các SIMPLE redirect validator chỉ kiểm tra fragment, nên có thể chấp nhận URI gây open redirect hoặc XSS tùy ngữ cảnh.

Không dùng SIMPLE validator như cách sửa nhanh lỗi tương thích. Nếu cần nhận scope, hãy thay riêng scope validator bằng allowlist như ví dụ; vẫn giữ các validator mặc định cho redirect và `jwks_uri`.

### 5.4. Cấp registrar client và initial access token

Spring guide dùng một client registrar đã đăng ký trước, có `client_credentials` và scope `client.create`; có thể cấp thêm quyền đọc theo policy:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId("registrar-internal-id")
        .clientId("developer-portal-registrar")
        .clientSecret(encodedRegistrarSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
```

`encodedRegistrarSecret` phải được mã hóa bằng encoder mà Authorization Server sử dụng; secret minh họa không được commit vào source control.

Trong Spring guide 1.5.8, initial access token dùng để tạo client phải có **scope duy nhất** là `client.create`. Sau khi đăng ký thành công, token này chỉ được dùng một lần và bị invalidated. Không cấp token registrar có thêm scope API nghiệp vụ hoặc quyền quản trị khác.

Ví dụ token request:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

Nếu dùng approval portal, chỉ cấp token sau khi hồ sơ được duyệt và payload cuối cùng được ràng buộc với nội dung đã duyệt. Initial access token của Spring là quyền gọi registration endpoint; tự nó không chứa toàn bộ quyết định approval của doanh nghiệp.

### 5.5. Đăng ký và đọc client

Request đăng ký:

```http
POST /connect/register HTTP/1.1
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Orders Portal",
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "redirect_uris": ["https://orders.example.com/login/oauth2/code/oidc"],
  "scope": "openid profile"
}
```

Response chứa metadata đã đăng ký và các thông tin quản lý như `client_id`, `registration_access_token`, `registration_client_uri`; confidential client có thể nhận `client_secret`. Client phải lưu credential an toàn ngay khi nhận.

Registrar có thể được cấp scope `client.read` khi deployment cho phép registrar thực hiện Client Read. Với per-client management flow trong Spring guide 1.5.8, Client Read sử dụng `registration_access_token` dạng bearer tại `registration_client_uri` được trả về sau registration. Hai loại quyền này cần được quản lý theo đúng flow đã chọn; không dùng initial access token `client.create` để đọc registration. Registration access token là credential dài hạn có thể cho phép đọc thông tin registration; nếu triển khai endpoint quản lý đầy đủ theo RFC 7592, credential có thể có quyền cập nhật/xóa registration. Không đưa token này vào log, browser storage công khai, URL hoặc ticket.

Theo tài liệu Protocol Endpoints 1.5.8, Client Read request cần bearer access token có scope `client.read`; guide minh họa cách đọc registration vừa tạo bằng cặp `registration_access_token` và `registration_client_uri`. Registrar có thể được cấp scope `client.read` để thực hiện luồng đọc được bảo vệ theo cấu hình của deployment.

**Giới hạn phiên bản:** tài liệu Spring Authorization Server 1.5.8 mô tả Client Registration và Client Read. RFC 7592 còn định nghĩa Client Update và Client Delete; không suy luận rằng endpoint mặc định của mọi phiên bản Spring đã triển khai đầy đủ PUT/DELETE. Nếu cần vòng đời đó, xác nhận API của phiên bản đang dùng hoặc xây dựng management workflow riêng với cùng mức bảo vệ.

### 5.6. Custom metadata cần converter

Spring guide minh họa custom metadata như `logo_uri` và `contacts` bằng cách cấu hình:

- `OidcClientRegistrationAuthenticationProvider.setRegisteredClientConverter(...)`.
- `OidcClientRegistrationAuthenticationProvider.setClientRegistrationConverter(...)`.
- `OidcClientConfigurationAuthenticationProvider.setClientRegistrationConverter(...)`.

Điều này quan trọng khi metadata extension cần được lưu và trả lại qua Client Read. Không giả định mọi metadata field trong OIDC Registration 1.0 đều tự động được map vào `RegisteredClient`. Chỉ hỗ trợ những field đã có schema, validation, persistence, readback và security policy rõ ràng.

## 6. SSRF có thể xuất hiện từ metadata URL như thế nào?

### 6.1. SSRF là gì trong bối cảnh Authorization Server?

Server-Side Request Forgery (SSRF) xảy ra khi attacker điều khiển URL hoặc đích mạng mà một thành phần server thực hiện HTTP request tới. Trong DCR, client đăng ký có thể đưa URL vào metadata. Nếu AS hoặc worker nền tải URL đó, server có thể bị lợi dụng để truy cập:

- Loopback như `127.0.0.1`, `::1` hoặc dịch vụ localhost.
- Dải private IPv4 như `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- IPv6 unique-local/link-local, địa chỉ IPv4-mapped IPv6 hoặc dải NAT64 có thể ánh xạ tới địa chỉ bị chặn.
- Cloud/container metadata endpoint, service discovery, internal admin API, database proxy hoặc control plane.
- Dịch vụ chỉ có thể truy cập từ mạng backend của Authorization Server.

Tác động phụ thuộc quyền mạng của AS: lộ thông tin nội bộ, truy cập credential metadata, gọi API nội bộ hoặc làm cạn tài nguyên bằng request chậm/lớn.

### 6.2. Phân loại metadata URL theo hành vi

Không phải mọi URL metadata đều tự động gây SSRF. Nguy cơ xuất hiện khi một thành phần **server-side dereference** URL hoặc gửi request tới URL đó:

| Metadata/feature | Hành vi có thể phát sinh | Rủi ro |
| --- | --- | --- |
| `jwks_uri` | AS tải JWK Set khi cần xác minh chữ ký client/request hoặc xử lý flow liên quan | SSRF, DNS rebinding, response JWK độc hại/lớn |
| `sector_identifier_uri` | OIDC OP tải JSON array tại registration time để xác minh redirect URI | SSRF ngay trong registration request |
| `request_uri` / `request_uris` | Authorization Server tải Request Object khi xử lý authorization request | SSRF ở thời điểm authorize |
| `backchannel_logout_uri` | OP gửi HTTP POST Logout Token tới RP | SSRF outbound callback khi logout |
| `logo_uri` | OP tải logo để hiển thị/scan hoặc browser tải ảnh | Server-side SSRF nếu proxy/download; phishing/privacy nếu browser tải |
| `client_uri`, `tos_uri`, `policy_uri` | OP hiển thị link cho người dùng; có thể tải/scan nếu deployment triển khai | Phishing/malicious content; SSRF nếu server fetch |

`jwks_uri` là metadata chuẩn trong RFC 7591. OIDC Dynamic Client Registration 1.0 còn định nghĩa `sector_identifier_uri`; OIDC Core định nghĩa `request_uri` và hành vi Authorization Server tải Request Object. Back-Channel Logout định nghĩa OP gửi POST tới `backchannel_logout_uri`. Nếu triển khai các feature này, phải kiểm soát outbound destination tại đúng nơi phát sinh request.

Theo OIDC Registration, `sector_identifier_uri` dùng HTTPS và tham chiếu JSON array chứa các redirect URI đã đăng ký; OP phải tải và xác minh array này lúc registration. Theo OIDC Core, `request_uri` phải dùng HTTPS, trừ trường hợp Request Object được ký theo cách AS có thể xác minh; AS tải Request Object khi xử lý authorization request nếu chưa có cache hợp lệ.

`backchannel_logout_uri` không được chứa fragment và SHOULD dùng HTTPS; OIDC cho phép HTTP trong một số trường hợp confidential client nếu OP cho phép. Quy tắc scheme của protocol không thay thế SSRF policy: endpoint HTTPS vẫn có thể trỏ tới private IP hoặc internal service.

### 6.3. Phân biệt server-side fetch và browser-side load

Nếu Authorization Server chỉ render `logo_uri` thành một ảnh để browser tự tải, request ảnh do browser của người dùng thực hiện, không phải SSRF trực tiếp từ server. Tuy nhiên, vẫn có nguy cơ phishing, tracking và nội dung độc hại.

Nếu AS tải logo về để resize, cache, malware scan hoặc proxy, request đó đi từ server và trở thành SSRF surface. Tương tự, nếu AS tải `policy_uri` để kiểm tra liên kết, không được dùng HTTP client mặc định để fetch URL tự do.

RFC 7591 cảnh báo metadata URL hiển thị cho End-User có thể bị dùng để dụ click vào nội dung nguy hiểm; spec khuyến nghị kiểm tra quan hệ host/scheme với redirect URI và cảnh báo nguồn third-party. Việc làm theo khuyến nghị bằng cách tải nội dung về phải đi kèm SSRF-safe fetcher.

### 6.4. Vì sao kiểm tra HTTPS là chưa đủ?

Một URL như:

```text
https://169.254.169.254/latest/meta-data/
https://127.0.0.1:8443/admin
https://internal-service.corp.example/secrets
```

vẫn có thể dùng scheme HTTPS. Tương tự, hostname trông công khai có thể trả về địa chỉ private khi resolve DNS hoặc thay đổi câu trả lời DNS giữa bước kiểm tra và bước kết nối.

Spring Authorization Server 1.5.8 có `DEFAULT_JWK_SET_URI_VALIDATOR` để từ chối `jwks_uri` không dùng HTTPS. Validator này không kiểm tra toàn bộ DNS/IP/port/redirect/egress policy. Do đó, cấu hình validator mặc định là cần thiết nhưng không đủ để tuyên bố đã chống SSRF.

## 7. Thiết kế SSRF-safe metadata fetch

### 7.1. Ưu tiên allowlist host theo use case

Nếu tổ chức chỉ cho phép client thuộc một số publisher/partner đã biết, allowlist host là biện pháp dễ kiểm soát:

- Chỉ cho phép FQDN thuộc domain publisher/partner đã xác minh.
- Chỉ cho phép HTTPS và port đã định nghĩa (thường là 443).
- Từ chối URL có user-info, fragment hoặc scheme ngoài policy.
- Không chấp nhận IP literal nếu không có yêu cầu cụ thể.
- Không tự động cho phép mọi subdomain bằng wildcard nếu không quản lý được toàn bộ DNS/delegation.
- Áp dụng allowlist riêng cho từng metadata type; `jwks_uri` và `backchannel_logout_uri` có trust model khác nhau.

Allowlist domain không thay thế kiểm tra địa chỉ IP. Domain được allowlist vẫn có thể bị cấu hình DNS sai hoặc bị chiếm quyền.

### 7.2. Kiểm tra DNS và IP đích

Nếu business bắt buộc hỗ trợ URL tùy ý trên Internet:

1. Parse URL bằng thư viện URI chuẩn; từ chối hostname rỗng, user-info, scheme lạ và port không được phép.
2. Resolve tất cả bản ghi A và AAAA bằng resolver được kiểm soát.
3. Chuẩn hóa IPv4-mapped IPv6/NAT64 và kiểm tra toàn bộ địa chỉ trả về.
4. Từ chối loopback, private, link-local, unique-local, multicast, unspecified, reserved, carrier-grade NAT, metadata IP và mọi dải không phải public unicast theo policy.
5. Kết nối tới chính IP đã xác minh (pin DNS result cho request), nhưng vẫn giữ hostname gốc cho HTTP Host, TLS SNI và certificate validation.
6. Nếu DNS thay đổi, thực hiện lại kiểm tra cho request tiếp theo.

Không chỉ resolve DNS để kiểm tra rồi để HTTP client tự resolve lại khi connect. Đó là khoảng trống time-of-check/time-of-use có thể bị DNS rebinding khai thác. Kiểm tra mọi A/AAAA result; không chấp nhận chỉ vì một địa chỉ hợp lệ nếu các địa chỉ còn lại trỏ vào mạng nội bộ.

### 7.3. Xử lý redirect

Tắt tự động follow HTTP redirect trong metadata fetcher. Một URL public có thể trả `302 Location: http://169.254.169.254/` và khiến HTTP client đi vào internal network.

Nếu nghiệp vụ thật sự cần redirect:

- Giới hạn số hop rất nhỏ.
- Parse và chạy toàn bộ scheme/host/port/DNS/IP validation lại trên từng Location.
- Không forward Authorization header, cookie, client credential hoặc custom header sang origin mới.
- Không cho phép redirect sang scheme khác hoặc port ngoài allowlist.
- Phát hiện vòng lặp và từ chối URL chain bất thường.

### 7.4. Giới hạn HTTP và nội dung

Metadata fetcher cần giới hạn:

- Connect timeout, response timeout và tổng thời gian xử lý.
- Số byte response tối đa và kích thước JSON/JWK Set.
- Số lượng JWK, kích thước từng key và độ sâu JSON.
- Content-Type mong đợi; ví dụ JWK Set phải là JSON hợp lệ.
- Số kết nối đồng thời, queue size và rate theo client/host.
- Retry count và backoff; không retry vô hạn.

TLS certificate verification phải bật. Không bỏ qua hostname verification để “hỗ trợ endpoint đối tác”. Không parse HTML/XML tùy ý khi endpoint chỉ được mong đợi trả JSON; nếu cần scan nội dung, chạy trong worker cô lập với giới hạn tài nguyên.

### 7.5. Network egress là lớp phòng thủ bắt buộc

Ứng dụng nên chạy trong network segment chỉ được outbound tới những đích cần thiết. Firewall, Kubernetes NetworkPolicy, service mesh egress gateway hoặc proxy kiểm soát outbound cần:

- Deny mặc định các dải private/internal và cloud metadata service.
- Chặn loopback/link-local/multicast và endpoint quản trị không cần thiết.
- Chỉ mở DNS resolver và Internet destinations theo policy.
- Giới hạn egress của metadata fetch worker riêng khỏi mạng core AS.
- Log destination host/IP, policy decision và request ID nhưng không log token/secret.

Application validation và network egress control bổ sung cho nhau. Một bug parser, DNS rebinding hoặc redirect bypass không được phép tạo đường truy cập tùy ý vào control plane.

### 7.6. Một interface cho policy và fetcher

Tách policy kiểm tra URL khỏi code provider để có thể test:

```java
import java.net.URL;

public interface ClientMetadataUrlPolicy {

    // Chỉ kiểm tra URL có được phép dùng cho loại metadata này.
    // Không tải URL trong method validation đồng bộ.
    void validateJwksUri(URL uri);

    void validateSectorIdentifierUri(URL uri);
}

public interface SafeClientMetadataFetcher {

    // Implementation phải pin DNS/IP đã xác minh, không follow redirect
    // tự động, có timeout/size limit và egress policy.
    byte[] fetchJwkSet(URL uri);

    byte[] fetchSectorIdentifierDocument(URL uri);
}
```

Interface trên mô tả ranh giới trách nhiệm, không phải một SSRF-safe HTTP client hoàn chỉnh. Implementation thực tế phải tích hợp DNS resolver, HTTP client, TLS, redirect policy và network egress đã nêu ở trên.

## 8. Bổ sung URL validation vào Spring provider

### 8.1. Kiểm tra URL metadata trong registration context

```java
import java.net.URL;
import java.util.function.Consumer;

import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;

private static Consumer<OidcClientRegistrationAuthenticationContext>
        metadataUrlValidator(ClientMetadataUrlPolicy policy) {

    return context -> {
        OidcClientRegistrationAuthenticationToken request =
                context.getAuthentication();
        OidcClientRegistration registration =
                request.getClientRegistration();

        // Client Read không gửi metadata registration mới.
        if (registration == null) {
            return;
        }

        URL jwksUri = registration.getJwkSetUrl();
        if (jwksUri != null) {
            policy.validateJwksUri(jwksUri);
        }

        URL sectorUri = registration.getClaimAsURL("sector_identifier_uri");
        if (sectorUri != null) {
            policy.validateSectorIdentifierUri(sectorUri);
        }
    };
}
```

Thêm validator vào chuỗi đang cấu hình cho `OidcClientRegistrationAuthenticationProvider`:

```java
OidcClientRegistrationAuthenticationValidator
    .DEFAULT_REDIRECT_URI_VALIDATOR
    .andThen(OidcClientRegistrationAuthenticationValidator
        .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
    .andThen(OidcClientRegistrationAuthenticationValidator
        .DEFAULT_JWK_SET_URI_VALIDATOR)
    .andThen(scopeAllowlist(allowedScopes))
    .andThen(metadataUrlValidator(metadataUrlPolicy))
```

Đoạn này bổ sung policy kiểm tra URL và scope. Nó không tải JWK Set hoặc sector document ngay trong validator. Nếu cần đọc nội dung `sector_identifier_uri` theo OIDC Registration, hãy dùng `SafeClientMetadataFetcher` với đầy đủ SSRF protection rồi kiểm tra JSON array có chứa các redirect URI đã đăng ký.

### 8.2. Kiểm tra lại ở thời điểm fetch

Không chỉ kiểm tra URL một lần lúc đăng ký. DNS record, redirect response, domain ownership và nội dung endpoint có thể thay đổi sau đó. Mỗi lần AS tải JWK Set hoặc Request Object phải áp dụng fetch policy tại thời điểm kết nối.

Với `backchannel_logout_uri`, kiểm tra đích ở cả lúc đăng ký và lúc gửi logout request. Registration-time approval không bảo đảm domain sẽ luôn trỏ tới cùng IP trong suốt vòng đời client.

### 8.3. Giới hạn URL extension

Nếu bật custom metadata như `sector_identifier_uri`, `request_uris` hoặc `backchannel_logout_uri`, cần xác định:

- Metadata đó được parse/lưu/trả lại bằng converter nào.
- Component nào sẽ thực hiện outbound request.
- Thời điểm fetch và điều kiện cache.
- HTTP method, headers và payload được phép.
- Egress identity/quyền mạng của component fetch.
- Cách disable metadata hoặc suspend client khi URL bị thay đổi/vi phạm policy.

Không thêm một field URL vào `RegisteredClient` chỉ vì converter có thể lưu nó. Chỉ hỗ trợ metadata khi có consumer thực tế và security control tương ứng.

## 9. Bảo vệ registration credential và vòng đời client

### 9.1. Initial access token

Initial access token là credential để gọi Registration Endpoint. Trong Spring guide, token dùng để tạo client có scope duy nhất `client.create`, và chỉ dùng một lần. Với protected registration:

- Cấp token qua kênh developer portal đã xác thực hoặc quy trình out-of-band.
- Dùng thời hạn ngắn, entropy cao, một lần sử dụng và giới hạn registrar.
- Không ghi token vào application log, analytics, URL hoặc ticket.
- Thu hồi token khi hồ sơ bị từ chối, hết hạn hoặc phát hiện bị lộ.
- Không cấp token `client.create` cho mọi user đã đăng nhập.

Nếu approval cần ràng buộc payload, initial token cần liên kết với approval record hoặc payload digest ở server. Một bearer token chỉ có scope `client.create` nhưng không ràng buộc metadata sẽ cho phép người giữ token thay request body trước khi đăng ký.

### 9.2. Registration access token

`registration_access_token` là bearer credential gắn với registration đã tạo. Tùy endpoint management mà OP triển khai, holder có thể đọc hoặc thay đổi client configuration. Vì vậy:

- Chỉ trả token qua HTTPS và chỉ một lần trong response registration.
- Client lưu trong secret manager/secure storage, không lưu trong browser local storage công khai.
- Không đưa token vào `registration_client_uri` hoặc query string.
- Redact `Authorization` header trong reverse proxy, APM, tracing và error report.
- Hỗ trợ rotate/revoke theo RFC 7592 nếu management endpoint được triển khai.
- Khi deprovision client, vô hiệu hóa cả registration access token liên quan.

Client secret và registration access token là hai credential khác nhau. Client secret dùng tại Token Endpoint theo authentication method; registration access token dùng tại Client Configuration Endpoint.

### 9.3. Client Read, Update và Delete

RFC 7592 định nghĩa các thao tác Client Read, Client Update và Client Delete qua Client Configuration Endpoint. Registration access token là bearer token để bảo vệ các thao tác đó.

Spring Authorization Server 1.5.8 hướng dẫn Registration và Client Read. Khi cần Update/Delete, hãy xác nhận hỗ trợ của đúng phiên bản hoặc triển khai management API/portal riêng. Management API cần:

- Xác minh registration token thuộc đúng client.
- Không cho client đổi `client_id`.
- Kiểm tra metadata mới bằng cùng policy như registration ban đầu.
- Không cho phép tự nâng grant, scope, redirect URI hoặc authentication method ngoài approval.
- Rotate registration token/secret theo policy và vô hiệu hóa token cũ đúng thời điểm.
- Audit mọi thay đổi metadata và deprovision.

### 9.4. Software statement

Nếu deployment nhận `software_statement`, cần:

1. Chỉ tin issuer đã được cấu hình trong trust store.
2. Xác minh chữ ký với thuật toán/key được cho phép.
3. Kiểm tra `iss`, `aud`, `exp`, `nbf`, `jti` và replay policy.
4. Kiểm tra metadata trong statement có đúng product, software version, redirect URI và client type đã được publisher phê duyệt.
5. Khi JSON request và statement cùng khai báo một metadata field, áp dụng quy tắc precedence của OIDC DCR.
6. Không coi statement tự ký hoặc ký bởi issuer chưa tin cậy là bằng chứng danh tính.

Software statement không thay thế initial access token trong protected registration. Một token cấp quyền gọi endpoint và một statement attests metadata là hai cơ chế khác nhau.

## 10. Giới hạn metadata và client policy

### 10.1. Redirect URI cần policy riêng

Validator mặc định của Spring từ chối fragment, thiếu scheme và unsafe scheme; nhưng việc URI có cú pháp hợp lệ không chứng minh client sở hữu domain đó. Với redirect-based flow:

- Yêu cầu đăng ký từng URI chính xác; không dùng wildcard.
- Web callback production dùng HTTPS.
- Chỉ cho phép localhost HTTP trong môi trường phát triển theo policy.
- Native app dùng custom scheme/loopback theo profile và bằng chứng ràng buộc ứng dụng.
- Không cho phép URI chứa user-info hoặc fragment.
- Kiểm tra domain ownership qua DNS challenge, HTTPS challenge hoặc quy trình vendor review khi cần.
- Ở Authorization Endpoint, so sánh request `redirect_uri` với URI đã đăng ký theo đúng protocol.

Không cho phép client đăng ký redirect URI trỏ vào open redirector của domain hợp lệ. Host hợp lệ không đảm bảo path callback không chuyển tiếp sang host khác.

### 10.2. Grant type và response type

Chọn allowlist theo loại client. Ví dụ:

| Client type | Allowlist gợi ý |
| --- | --- |
| Server-side web | `authorization_code`; `refresh_token` nếu có rotation/reuse detection phù hợp |
| SPA/native public | `authorization_code` với PKCE; không phát client secret |
| Machine-to-machine | `client_credentials` với scope riêng và client authentication mạnh |
| Client legacy | Chỉ giữ grant cần thiết trong thời gian migration có deadline |

Không cho phép implicit hoặc resource owner password credentials trong thiết kế mới. Không cấp đồng thời grant type không tương thích với mô hình client chỉ vì request có thể khai báo chúng.

### 10.3. Scope là quyền client có thể yêu cầu, không phải consent của người dùng

Scope trong registration metadata mô tả tập scope client dự kiến sử dụng. Nó không tự cấp quyền cho client hoặc thay thế user consent. Khi authorization request đến:

- Scope phải nằm trong tập client được phép sử dụng.
- Scope phải nằm trong tập scope OP hỗ trợ.
- User/tenant policy và consent vẫn quyết định quyền thực tế.
- Scope đặc quyền cần approval riêng và có owner.
- Không chấp nhận scope tùy ý chỉ vì client tự khai báo.

Trong Spring Authorization Server 1.5.8, `DEFAULT_SCOPE_VALIDATOR` từ chối mọi registration request có scope không rỗng. Nếu ứng dụng cần khai báo scope trong DCR, dùng validator allowlist riêng như ví dụ ở mục 5.2; không thay bằng `SIMPLE_SCOPE_VALIDATOR` để chấp nhận tất cả.

### 10.4. JWK Set và client authentication

Nếu client dùng `jwks_uri`:

- Chỉ nhận HTTPS và áp dụng SSRF-safe URL policy.
- JWK Set chỉ chứa public key; từ chối private/symmetric key material.
- Chỉ chấp nhận thuật toán ký nằm trong allowlist.
- Giới hạn kích thước document, số key và kích thước mỗi key.
- Không cho `jwks_uri` và `jwks` xuất hiện đồng thời trong cùng registration.
- Cache theo policy có thời hạn; có chiến lược key rotation và xử lý fetch failure.

Nếu deployment chấp nhận `jwks` inline, dữ liệu vẫn cần schema/algorithm validation; nó không có khả năng tự cập nhật key như URL tham chiếu.

### 10.5. Metadata hiển thị cho End-User

Các trường `client_name`, `logo_uri`, `client_uri`, `tos_uri`, `policy_uri` là dữ liệu do client cung cấp trừ khi được attestation. Khi render consent page:

- Escape HTML và attribute; không chèn metadata trực tiếp vào markup.
- Dùng CSP và content isolation cho ảnh/link bên thứ ba.
- Hiển thị nhãn cảnh báo rằng tên/logo/link do publisher khai báo.
- Có thể dùng interstitial warning trước khi mở policy/terms link chưa tin cậy.
- Nếu proxy/download logo, dùng safe fetcher và giới hạn content type/size.
- Không coi việc host logo trùng host redirect URI là chứng minh publisher.

### 10.6. Metadata extension phải có schema và vòng đời

Với mỗi custom field, định nghĩa:

- JSON type, độ dài, format và required/optional.
- Ai được gửi và ai được đọc.
- Có thể sửa sau registration không.
- Có làm phát sinh outbound request không.
- Có được hiển thị cho End-User không.
- Có cần consent/approval không.
- Cách migrate, version và deprecate.

Không lưu toàn bộ JSON request thô như metadata không kiểm soát rồi đưa trực tiếp vào consent page hoặc authorization logic. Chỉ lưu field đã allowlist và đã validate.

## 11. Kiểm thử DCR, approval và SSRF

### 11.1. Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| D01 | Gọi Registration Endpoint khi DCR chưa bật | Endpoint không xử lý registration |
| D02 | Request thiếu bearer access token | Từ chối authentication |
| D03 | Token registrar có đúng scope `client.create` | Có thể tạo registration theo policy |
| D04 | Token có `client.create` và scope khác | Từ chối theo yêu cầu token chỉ có `client.create` |
| D05 | Dùng lại initial access token đã đăng ký thành công | Từ chối vì token đã được tiêu thụ |
| D06 | Token không có scope `client.create` | Từ chối |
| D07 | Client Read dùng credential hợp lệ | Chỉ trả registration mà credential được phép đọc |
| D08 | `redirect_uris` có fragment | Validator mặc định từ chối |
| D09 | `redirect_uris` dùng scheme `javascript`/`data` | Validator mặc định từ chối |
| D10 | `redirect_uris` là HTTPS hợp lệ nhưng domain chưa chứng minh quyền sở hữu | Approval/domain policy yêu cầu bằng chứng hoặc từ chối |
| D11 | Request khai báo scope nằm trong allowlist | Validator scope cho qua |
| D12 | Request khai báo scope ngoài allowlist | Từ chối `invalid_client_metadata` |
| D13 | Request khai báo `jwks_uri` dùng HTTP | Validator mặc định từ chối |
| D14 | Request khai báo HTTPS `jwks_uri` trỏ tới loopback/private IP | SSRF policy từ chối |
| D15 | Hostname resolve ra cả public và private IP | Từ chối toàn bộ host |
| D16 | DNS đổi từ public sang private sau validation | Fetch-time DNS pinning/egress policy chặn |
| D17 | Public URL redirect tới link-local metadata IP | Redirect bị tắt hoặc hop mới bị policy từ chối |
| D18 | URL dùng IPv4-mapped IPv6 trỏ tới private IPv4 | Normalize và từ chối |
| D19 | URL dùng NAT64 biểu diễn metadata IP | Normalize/policy từ chối |
| D20 | `jwks_uri` trả HTML thay vì JWK Set JSON | Fetcher từ chối content type/schema |
| D21 | JWK Set quá lớn hoặc có quá nhiều keys | Chặn theo byte/key limits |
| D22 | JWK Set chứa private/symmetric key material | Từ chối |
| D23 | `sector_identifier_uri` trả JSON không phải array redirect URI | Registration thất bại |
| D24 | `sector_identifier_uri` không chứa toàn bộ redirect URI đã đăng ký | Registration thất bại |
| D25 | `logo_uri` chứa nội dung HTML/script độc hại | Không render raw HTML; scan/proxy theo policy |
| D26 | `policy_uri` trỏ tới trang phishing | Hiển thị cảnh báo nguồn third-party và interstitial |
| D27 | `backchannel_logout_uri` trỏ tới internal address | Registration hoặc dispatch policy từ chối |
| D28 | Metadata extension chưa được converter hỗ trợ | Từ chối hoặc bỏ theo schema; không âm thầm tin cậy |
| D29 | Software statement ký bởi issuer không tin cậy | Từ chối |
| D30 | Software statement hết hạn/sai audience/sai chữ ký | Từ chối |
| D31 | JSON metadata xung đột software statement hợp lệ | Statement precedence theo OIDC DCR |
| D32 | Approval đã duyệt nhưng payload bị thay đổi | Payload digest/gate phát hiện và từ chối |
| D33 | Approval token hết hạn hoặc đã dùng | Không thể tạo registration |
| D34 | Developer vượt quota registration | Rate limit/quota từ chối và ghi audit |
| D35 | Registrar không có quyền cho tenant mục tiêu | Từ chối |
| D36 | Client secret/registration token xuất hiện trong log | Security test phát hiện redaction failure |
| D37 | Client bị suspend/deprovision nhưng vẫn có credential | Authentication/policy layer từ chối |
| D38 | Registration access token bị lộ | Có thể revoke/rotate và audit sự kiện |
| D39 | Metadata URL timeout hoặc trả lỗi | Fail closed; không dùng dữ liệu cache không hợp lệ |
| D40 | Outbound fetch vượt concurrency/response limit | Queue/rate/size guard chặn |

### 11.2. Kiểm thử bằng HTTP filter chain

Unit test validator là cần thiết nhưng chưa đủ. Integration test nên:

1. Khởi động Authorization Server test với DCR bật và registrar test.
2. Lấy access token có scope `client.create` đúng policy.
3. Gửi POST registration qua HTTP filter chain thật.
4. Xác minh response, `client_id`, registration access token và dữ liệu được lưu.
5. Gọi Client Read với credential hợp lệ.
6. Gửi request có scope ngoài allowlist, redirect URI xấu và `jwks_uri` xấu.
7. Kiểm tra status/error response và xác nhận không có registration ngoài ý muốn trong repository.
8. Kiểm tra initial access token không thể dùng lần thứ hai.

Với SSRF, dùng DNS resolver/HTTP server test có thể điều khiển để mô phỏng public-to-private rebinding, redirect chain, IPv6, timeout và response quá lớn. Không kiểm thử bằng cách gọi thật vào cloud metadata production.

### 11.3. Kiểm thử approval race và idempotency

Approval workflow cần test concurrency:

- Hai request cùng dùng một approval token chỉ tạo tối đa một registration.
- Hai request cùng digest không vượt quota instance nếu software policy chỉ cho một instance.
- Approval bị revoke trước khi registration commit thì request phải thất bại.
- Payload thay đổi giữa review và submit phải bị phát hiện.
- Hai admin phê duyệt đồng thời không tạo trạng thái mâu thuẫn.
- Retry do network timeout không tạo client duplicate ngoài ý muốn.

Dùng transaction/unique constraint/atomic consume cho approval token và registration digest. Không dựa vào kiểm tra trạng thái ở memory một node.

## 12. Vận hành và ứng phó sự cố

### 12.1. Metric và audit

Theo dõi tối thiểu:

- Registration success/failure theo registrar, tenant, client type và error code.
- Số lượng pending/approved/rejected/expired registration.
- Tỷ lệ scope/grant/auth method bị từ chối.
- Số request vượt rate limit/quota.
- Outbound metadata fetch latency, timeout, response size, redirect attempt và SSRF policy rejection.
- DNS/IP policy result, egress firewall deny và JWK Set parse failures.
- Credential issuance/rotation/revocation và client suspend/deprovision.

Audit event nên lưu actor, tenant, approval ID, client ID, metadata digest, policy version, decision, timestamp và reason. Không lưu raw bearer token, client secret hoặc nội dung JWK private key.

### 12.2. Khi phát hiện SSRF attempt

1. Từ chối registration/fetch đang vi phạm policy.
2. Ghi nhận hostname, resolved IP, redirect chain, metadata type và registrar identity.
3. Suspend approval/registrar nếu có dấu hiệu lạm dụng có chủ đích.
4. Kiểm tra outbound firewall/proxy logs xem AS đã kết nối tới địa chỉ nội bộ nào.
5. Nếu credential/token có thể đã bị lộ, revoke initial access token, registration access token hoặc client credential liên quan.
6. Kiểm tra JWK cache, authorization events và service nội bộ bị truy cập.
7. Cập nhật domain/IP deny policy và regression tests.

Không đưa URL đầy đủ có token query hoặc credential vào incident ticket công khai. Redact user-info, query secrets và header trước khi lưu bằng chứng.

### 12.3. Suspend và deprovision client

`RegisteredClient` là bản mô tả client đã đăng ký; approval state và operational status có thể cần một store riêng. Khi client bị suspend:

- Không phát token mới cho client.
- Chặn client ở client authentication/authorization policy layer.
- Xử lý refresh token/authorization grant theo incident policy.
- Ngừng outbound callback và metadata fetch không còn cần.
- Thu hồi registration access token và credential nếu bị compromise.
- Giữ audit record theo retention policy.

Khi deprovision, xóa/vô hiệu registration theo cơ chế quản lý đang dùng, invalidation cache trên mọi AS instance và bảo đảm registration token cũ không thể đọc hoặc sửa registration đã bị xóa.

## 13. Checklist trước production

**Registration access**

- [ ] DCR chỉ bật khi có use case và owner.
- [ ] Protected registration dùng registrar identity và initial access token scope hẹp.
- [ ] Token `client.create` có TTL/one-time use/quota và được ràng buộc với approval payload.
- [ ] Client Read/management token là bearer secret, được bảo vệ và rotate/revoke.
- [ ] Rate limit và quota áp dụng theo tenant/registrar/client type.

**Metadata policy**

- [ ] Redirect URI được validate scheme/fragment và có domain ownership policy khi cần.
- [ ] Grant type, response type, auth method và scope có allowlist.
- [ ] Scope DCR không dùng SIMPLE validator chấp nhận tùy ý.
- [ ] `jwks_uri` chỉ HTTPS và có SSRF-safe fetch policy.
- [ ] `jwks`/`jwks_uri` không xuất hiện đồng thời; JWK Set chỉ chứa public keys.
- [ ] Custom metadata có schema, converter, persistence, readback và owner.
- [ ] Software statement chỉ được tin sau khi verify issuer/signature/claims.

**SSRF defense**

- [ ] Tất cả metadata URL có server-side fetcher đều được phân loại.
- [ ] DNS A/AAAA được kiểm tra; private/reserved/loopback/link-local/metadata IP bị chặn.
- [ ] DNS result được pin tới kết nối; không có TOCTOU gap.
- [ ] Redirect tự động bị tắt hoặc mỗi hop được validate lại.
- [ ] TLS hostname verification, timeout, byte limit, content type và concurrency limit được bật.
- [ ] Egress firewall deny-by-default và cô lập metadata fetch worker.
- [ ] Backchannel callback được kiểm tra cả registration-time và dispatch-time.

**Approval và vận hành**

- [ ] Approval state nằm trong workflow có audit và transaction.
- [ ] Payload digest được kiểm tra lại lúc registration.
- [ ] Có quy trình suspend, rotate credential, deprovision và cache invalidation.
- [ ] Log redaction không để lộ bearer token, client secret hoặc private key.
- [ ] Có integration tests và SSRF regression tests trên mọi metadata fetch path.

## 14. Tài liệu tham khảo

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, initial access token, software statement và security considerations.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): Client Read/Update/Delete và registration access token.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): metadata OIDC, `sector_identifier_uri` và validation.
- [OpenID Connect Core 1.0 — Request Objects](https://openid.net/specs/openid-connect-core-1_0.html#RequestObjects): `request_uri` và việc Authorization Server tải Request Object.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): `backchannel_logout_uri` và server-to-server logout request.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật endpoint, initial access token, đăng ký và đọc client.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, providers, converters và endpoint security.
- [Spring Authorization Server 1.5.8 API — OidcClientRegistrationAuthenticationValidator](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): DEFAULT và SIMPLE validators cho redirect URI, post-logout URI, JWK Set URI và scope.
- [OWASP Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlist, DNS rebinding, redirect handling, private IP ranges và egress defense.

**Kết luận:** Dynamic Client Registration là cơ chế cấp danh tính và cấu hình bảo mật cho client, không chỉ là một API ghi JSON. Hãy giới hạn ai được đăng ký, gắn approval với đúng metadata đã duyệt, allowlist grant/scope/redirect URI, bảo vệ registration credentials và kiểm soát mọi outbound request có thể phát sinh từ URL metadata. Trong Spring Authorization Server 1.5.8, endpoint bị tắt theo mặc định; các validator mặc định là lớp nền cần thiết, nhưng `jwks_uri` chỉ được kiểm tra HTTPS nên SSRF vẫn cần DNS/IP validation, redirect control và network egress defense ở thời điểm fetch.


