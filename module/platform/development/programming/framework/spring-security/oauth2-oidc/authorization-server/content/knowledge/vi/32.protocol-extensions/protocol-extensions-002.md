# Khai báo AuthorizationGrantType và đăng ký grant cho client

## 1. AuthorizationGrantType nằm ở đâu trong OAuth 2.0?

OAuth 2.0 định nghĩa authorization grant là thông tin đại diện cho quyền mà Resource Owner cấp cho Client, hoặc quyền của chính Client trong một số flow. Client gửi grant tới Token Endpoint để xin access token. Các grant chuẩn gồm Authorization Code, Client Credentials và Refresh Token; OAuth 2.0 cũng cho phép mở rộng bằng **Extension Grant**.

Trong Spring Authorization Server (SAS), `AuthorizationGrantType` là kiểu dữ liệu biểu diễn giá trị của tham số `grant_type`. `RegisteredClient` lưu tập grant mà một client được phép sử dụng. Khi cấu hình client, ta khai báo grant chuẩn bằng hằng số có sẵn hoặc tạo một `AuthorizationGrantType` mới cho extension grant.

`AuthorizationGrantType` giữ giá trị chuỗi của grant, cung cấp `getValue()` và so sánh bằng `equals`/`hashCode`. Vì vậy, nên tạo một hằng số dùng chung và tránh khai báo các chuỗi grant rải rác ở nhiều lớp.

Bài thuộc chương **Mở rộng giao thức** của module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`. Nội dung tập trung vào khai báo grant type và đăng ký grant cho client bằng Spring Authorization Server 1.5.8.

Sau bài học, bạn có thể:
1. Phân biệt authorization grant, grant type, client authentication method và scope.
2. Đọc giá trị grant type và biết khi nào cần tạo `AuthorizationGrantType` mới.
3. Chọn identifier ổn định cho extension grant.
4. Đăng ký grant chuẩn hoặc custom grant vào `RegisteredClient`.
5. Lưu client registration qua `RegisteredClientRepository`.
6. Kiểm tra client có được phép dùng grant đang yêu cầu hay không.
7. Hiểu vì sao khai báo grant cho client chưa làm Token Endpoint xử lý được grant mới.
8. Kết nối registration với `AuthenticationConverter` và `AuthenticationProvider` khi triển khai extension grant.

## 2. Phân biệt grant type, client authentication method và scope

Ba khái niệm thường xuất hiện cùng nhau trong một `RegisteredClient` nhưng có ý nghĩa khác nhau:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Authorization grant type** | Client được dùng flow nào để xin token? | `authorization_code`, `client_credentials`, custom extension URI |
| **Client authentication method** | Client chứng minh danh tính với Token Endpoint bằng cách nào? | `client_secret_basic`, `private_key_jwt`, `tls_client_auth`, `none` |
| **Scope** | Client được phép xin quyền truy cập nào? | `orders.read`, `orders.write`, `profile` |

Ví dụ một confidential client có thể:
- Xác thực bằng `private_key_jwt`.
- Được phép dùng `client_credentials`.
- Chỉ được xin scope `orders.read`.

Grant type không phải scope. Đưa `partner_assertion` vào scope không đăng ký một authorization grant. Tương tự, khai báo `client_secret_basic` không cho phép client sử dụng grant `client_credentials`.

Một request Token Endpoint hợp lệ phải đồng thời đáp ứng:
- Client được xác thực theo authentication method đã đăng ký.
- Grant type được hỗ trợ bởi Authorization Server.
- Grant type nằm trong danh sách được phép của chính client đó.
- Dữ liệu grant và scope được xác minh theo policy của flow.

## 3. AuthorizationGrantType trong Spring Security

`AuthorizationGrantType` thuộc package:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
~~~

Các hằng số chuẩn thường dùng:

| Hằng số | Giá trị giao thức | Ý nghĩa |
| --- | --- | --- |
| `AUTHORIZATION_CODE` | `authorization_code` | Đổi authorization code lấy token |
| `CLIENT_CREDENTIALS` | `client_credentials` | Client xin token cho chính nó |
| `REFRESH_TOKEN` | `refresh_token` | Đổi refresh token lấy token mới |
| `DEVICE_CODE` | `urn:ietf:params:oauth:grant-type:device_code` | Device Authorization Grant |
| `JWT_BEARER` | `urn:ietf:params:oauth:grant-type:jwt-bearer` | JWT Bearer Grant |
| `TOKEN_EXCHANGE` | `urn:ietf:params:oauth:grant-type:token-exchange` | Token Exchange |

Tập hằng số cụ thể phụ thuộc phiên bản Spring Security được SAS sử dụng. Không nên chép hằng số từ tài liệu của version mới hơn vào project đang chạy version cũ mà chưa kiểm tra API.

Đối với grant chuẩn, hãy dùng hằng số có sẵn thay vì tự tạo đối tượng với chuỗi tương ứng:

Đoạn code dưới đây giả định clientSecret đã được đọc từ secret manager và PasswordEncoder đã được cấu hình:

~~~java
RegisteredClient registeredClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Dùng hằng số giúp code thể hiện rõ ý định và tránh lỗi đánh máy. Khi cần một extension grant chưa có hằng số chuẩn, tạo đối tượng bằng constructor nhận giá trị chuỗi.

## 4. Chọn identifier cho extension grant

RFC 6749, mục 4.5, yêu cầu client chỉ định extension grant bằng một **absolute URI** trong tham số `grant_type` của Token Endpoint. URI này do Authorization Server định nghĩa. Request có thể kèm các tham số bổ sung cần thiết để mang authorization grant.

Ví dụ identifier minh họa:

~~~text
https://auth.example.com/oauth/grants/partner-assertion
~~~

Có thể dùng URI dạng HTTPS hoặc URN, miễn là absolute URI và được quản trị ổn định. Khi chọn identifier:
- Dùng namespace thuộc quyền kiểm soát của tổ chức.
- Chọn một giá trị duy nhất, không xung đột với grant chuẩn hoặc extension của đối tác.
- Giữ nguyên identifier sau khi client registration và authorization record đã được lưu.
- Không dùng URL tạm, hostname môi trường dev hoặc giá trị thay đổi theo version.
- Không nhúng secret, tenant credential hoặc dữ liệu nhạy cảm vào identifier.
- Tài liệu hóa ý nghĩa grant, tham số, quy tắc xác thực và lỗi giao thức.

Identifier là giá trị giao thức được client gửi nguyên dạng trong `grant_type`; nó không phải URL endpoint để client gọi trực tiếp. Không bắt buộc máy chủ phải phục vụ trang web tại URI này.

Nếu identifier thay đổi, client, Authorization Server, database, integration test, monitoring và metadata đều phải được cập nhật đồng bộ. Trong thực tế, nên xem identifier như một phần contract lâu dài của giao thức.

### 4.1. Khai báo hằng số custom grant

~~~java
package com.example.authorizationserver.grants;

import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class PartnerAssertionGrantTypes {

    public static final String PARTNER_ASSERTION_VALUE =
            "https://auth.example.com/oauth/grants/partner-assertion";

    public static final AuthorizationGrantType PARTNER_ASSERTION =
            new AuthorizationGrantType(PARTNER_ASSERTION_VALUE);

    private PartnerAssertionGrantTypes() {
    }
}
~~~

Ví dụ dùng `auth.example.com` dành cho tài liệu. Khi triển khai, thay bằng namespace ổn định do tổ chức quản lý. Nên đặt hằng số ở một package dùng chung giữa registration, Token Endpoint converter/provider và test để tránh mỗi nơi tự khai báo một chuỗi khác nhau.

### 4.2. Không tự tạo custom grant nếu đã có grant chuẩn phù hợp

Trước khi tạo identifier mới, hãy kiểm tra OAuth/OIDC và các extension đã được chuẩn hóa. Ví dụ, nếu nghiệp vụ là Token Exchange, hãy đánh giá RFC 8693 và grant `token-exchange` đã có trong version tương ứng. Tự tạo grant gần giống chuẩn sẽ làm giảm interoperability và buộc client tích hợp riêng.

## 5. Đăng ký grant cho client bằng RegisteredClient.Builder

`RegisteredClient` là mô hình metadata client mà Authorization Server đã đăng ký. Trường `authorizationGrantTypes` là tập grant mà client có thể sử dụng. SAS cung cấp phương thức `authorizationGrantType(...)` để thêm một grant vào builder.

Ví dụ client đối tác được phép dùng `client_credentials` và extension grant `partner_assertion`:

~~~java
import org.springframework.core.env.Environment;

@Bean
RegisteredClient partnerGateway(PasswordEncoder passwordEncoder, Environment environment) {
    String partnerSecret = environment.getRequiredProperty("app.clients.partner-gateway.secret");
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("partner-gateway")
            .clientSecret(passwordEncoder.encode(partnerSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
            .scope("orders.read")
            .scope("orders.status")
            .build();
}
~~~

Đoạn code là ví dụ cấu hình; `partnerSecret` phải được cấp từ secret manager hoặc nguồn cấu hình được bảo vệ, không hard-code raw secret vào source code.

Các điểm cần chú ý:
- `withId(...)` nhận ID nội bộ của registration, khác với `clientId(...)` mà client dùng trên giao thức.
- Có thể gọi `authorizationGrantType(...)` nhiều lần để thêm nhiều grant.
- `authorizationGrantTypes(Consumer<Set<AuthorizationGrantType>>)` cho phép thêm, thay thế hoặc xóa phần tử trong tập grant.
- `scope(...)` khai báo scope được phép xin; nó không đăng ký grant.
- `clientAuthenticationMethod(...)` khai báo cách client xác thực; nó cũng không đăng ký grant.
- Chỉ cấp extension grant cho các client thực sự cần nó.

### 5.1. Chỉ đăng ký extension grant cho client được phê duyệt

Không nên thêm custom grant vào tất cả client theo mặc định. Có thể tách registration theo trust tier:

~~~java
RegisteredClient webClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("customer-portal")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.com/login/oauth2/code/customer")
        .scope("openid")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();

RegisteredClient partnerClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("partner-gateway")
        .clientSecret(passwordEncoder.encode(partnerSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .scope("orders.read")
        .build();
~~~

Portal dùng Authorization Code + PKCE. Partner Gateway mới được cấp extension grant. Việc tách client giúp giới hạn blast radius nếu credential hoặc grant-specific authorization bị lộ.

Đây là các builder fragment trong một registration service; passwordEncoder và partnerSecret được inject từ cấu hình/secret manager của ứng dụng.

Không cấp custom grant cho public client chỉ vì client yêu cầu. Hãy xác định flow có thể thực hiện an toàn với loại client đó hay không, và client có thể giữ/đưa bằng chứng grant một cách phù hợp hay không.

## 6. Đăng ký client trong repository

Sau khi tạo `RegisteredClient`, Authorization Server cần lưu nó qua `RegisteredClientRepository`. Repository được dùng trong client authentication, authorization grant processing, token introspection và các protocol flow khác.

Ví dụ đơn giản cho development/test:

~~~java
import org.springframework.core.env.Environment;

@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder, Environment environment) {
    String clientSecret = environment.getRequiredProperty("app.clients.partner-gateway.secret");
    RegisteredClient partnerClient = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("partner-gateway")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
            .scope("orders.read")
            .build();

    return new InMemoryRegisteredClientRepository(partnerClient);
}
~~~

`InMemoryRegisteredClientRepository` phù hợp cho demo, kiểm thử hoặc ứng dụng nhỏ có vòng đời registration cố định. Dữ liệu trong bộ nhớ mất khi process restart và không được chia sẻ giữa các instance.

Với production, thường dùng `JdbcRegisteredClientRepository` hoặc implementation lưu trữ bền vững khác. Ví dụ khởi tạo JDBC repository:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(JdbcOperations jdbcOperations) {
    return new JdbcRegisteredClientRepository(jdbcOperations);
}
~~~

Database phải có schema `oauth2-registered-client-schema.sql` tương ứng version SAS đang dùng. Nếu dùng custom repository, implementation phải giữ đầy đủ grant type, authentication methods, redirect URI, scope và settings khi ghi/đọc registration.

### 6.1. Kiểm tra registration đã lưu

Sau khi lưu client, đọc lại từ repository và xác minh grant có trong tập cho phép:

~~~java
RegisteredClient saved = registeredClientRepository.findByClientId("partner-gateway");

if (saved == null ||
        !saved.getAuthorizationGrantTypes()
                .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION)) {
    throw new IllegalStateException("Partner assertion grant is not registered");
}
~~~

Kiểm tra này hữu ích trong integration test, startup validation hoặc quy trình onboarding. Không nên để code kiểm tra registration chỉ chạy ở test nếu client có thể được tạo/cập nhật động sau khi ứng dụng khởi động.

## 7. Đăng ký grant trong Dynamic Client Registration

Nếu Authorization Server hỗ trợ Dynamic Client Registration (DCR), client registration request có thể chứa metadata `grant_types`. Đây là danh sách grant mà client khai báo muốn sử dụng. DCR endpoint phải xác minh từng giá trị và chỉ chấp nhận grant mà server hỗ trợ, đồng thời policy cho phép client đó dùng.

Ví dụ metadata:

~~~json
{
  "client_name": "Partner Gateway",
  "grant_types": [
    "client_credentials",
    "https://auth.example.com/oauth/grants/partner-assertion"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "orders.read"
}
~~~

AS không được xem giá trị `grant_types` do client tự gửi là quyền được cấp mặc nhiên. Quy trình đăng ký cần:
1. Xác thực registrar hoặc Initial Access Token theo policy.
2. Kiểm tra client owner, software statement hoặc trust tier nếu có.
3. Kiểm tra mỗi grant type nằm trong allowlist của Authorization Server.
4. Xác định extension grant có được phép cho loại client và authentication method này hay không.
5. Lưu tập grant đã được duyệt vào `RegisteredClient`.
6. Trả về metadata đã được server chấp nhận.

Nếu DCR endpoint không hỗ trợ custom grant, hãy từ chối hoặc xử lý theo policy được công bố. Không tự ý bỏ qua grant lạ rồi phản hồi client rằng grant đó đã được đăng ký.

DCR và custom grant là hai năng lực riêng:
- DCR tạo/cập nhật client registration.
- Extension grant implementation xử lý request cấp token.
- DCR có thể cho phép đăng ký tên grant nhưng Token Endpoint vẫn cần converter/provider tương ứng.

## 8. Đọc danh sách grant từ RegisteredClient

Trong runtime, code xử lý token request cần truy cập `RegisteredClient` đã được xác thực để biết client có quyền dùng grant nào.

~~~java
Set<AuthorizationGrantType> allowedGrantTypes =
        registeredClient.getAuthorizationGrantTypes();

boolean allowed = allowedGrantTypes.contains(
        PartnerAssertionGrantTypes.PARTNER_ASSERTION
);

if (!allowed) {
    throw new OAuth2AuthenticationException(
            OAuth2ErrorCodes.UNAUTHORIZED_CLIENT
    );
}
~~~

Đây là kiểm tra allowlist theo client. `registeredClient` phải lấy từ client principal đã được xác thực bởi Spring Security; không truy vấn theo `client_id` tùy ý trong form rồi tin kết quả như một bằng chứng client authentication.

Khi client gửi một grant type:
- Nếu server không hỗ trợ grant đó, Token Endpoint không thể xử lý và thường trả `unsupported_grant_type`.
- Nếu server có provider nhưng client chưa được cấp grant đó, provider phải từ chối client với `unauthorized_client`.
- Nếu grant artifact sai, hết hạn, không đúng audience hoặc đã replay, trả `invalid_grant` theo semantics của extension.
- Nếu thiếu/thừa tham số hoặc tham số lặp không hợp lệ, trả `invalid_request`.

Không dựa vào giao diện client hoặc cấu hình phía client để thực thi quyền. Authorization Server phải kiểm tra lại ở phía server cho mọi token request.

## 9. Request Token Endpoint với extension grant

Sau khi client được đăng ký grant, client gửi token request tới Token Endpoint. Với ví dụ partner assertion, request có thể như sau:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(partner-gateway:CLIENT_SECRET)
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=https%3A%2F%2Fauth.example.com%2Foauth%2Fgrants%2Fpartner-assertion&assertion=SIGNED_PARTNER_ASSERTION&scope=orders.read
~~~

Trong request:
- grant_type phải khớp chính xác identifier đã khai báo trong PartnerAssertionGrantTypes.
- assertion là dữ liệu grant-specific do extension định nghĩa; trong ví dụ là assertion đã ký.
- Client xác thực theo phương thức đã đăng ký, ở đây là client_secret_basic.
- scope chỉ chứa scope mà client được phép yêu cầu và grant provider cho phép cấp.

Client không gửi một URI mới hoặc tự chọn tên grant. Client và Authorization Server phải thống nhất cùng một identifier và cùng contract tham số.

Response thành công vẫn theo định dạng access token response của OAuth 2.0:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
~~~

Các giá trị token chỉ là placeholder. Nếu extension phát hành refresh token, server phải xác định rõ policy refresh và đăng ký thêm grant refresh_token cho client nếu client được phép dùng flow đó.

## 10. Token Endpoint cần AuthenticationConverter và AuthenticationProvider

SAS xử lý Token Endpoint theo pipeline:

~~~mermaid
flowchart LR
    A[HTTP POST /oauth2/token] --> B[Client authentication]
    B --> C[AuthenticationConverter chain]
    C --> D[Custom grant Authentication token]
    D --> E[AuthenticationProvider]
    E --> F[Validate client grant allowlist]
    F --> G[Validate grant artifact and policy]
    G --> H[OAuth2TokenGenerator]
    H --> I[Persist OAuth2Authorization]
    I --> J[OAuth2 access token response]
~~~

Hai thành phần chính:

**AuthenticationConverter**
- Đọc request HTTP và xác định có đúng custom grant_type mà converter phụ trách hay không.
- Nếu không phải grant của mình, trả null để converter khác xử lý.
- Kiểm tra tham số bắt buộc, tham số trùng và định dạng.
- Tạo một đối tượng Authentication riêng biểu diễn custom grant.
- Lấy client principal từ SecurityContext sau khi client authentication đã chạy.

**AuthenticationProvider**
- Nhận custom grant Authentication token.
- Xác nhận client đã được xác thực.
- Đọc RegisteredClient từ client principal.
- Kiểm tra grant type nằm trong RegisteredClient.getAuthorizationGrantTypes().
- Xác minh assertion/credential và policy của extension.
- Tạo access token, lưu authorization và trả kết quả cho Token Endpoint.

Việc tách converter và provider giúp việc parse HTTP request độc lập với nghiệp vụ xác thực grant. Không đặt toàn bộ validation và token issuance trong controller riêng rồi bỏ qua Token Endpoint pipeline chuẩn.

### 10.1. Converter chỉ nhận đúng grant của nó

Mẫu logic của converter:

~~~java
public Authentication convert(HttpServletRequest request) {
    String grantType = request.getParameter(OAuth2ParameterNames.GRANT_TYPE);

    if (!PartnerAssertionGrantTypes.PARTNER_ASSERTION_VALUE.equals(grantType)) {
        return null;
    }

    String assertion = request.getParameter("assertion");
    if (!StringUtils.hasText(assertion) ||
            request.getParameterValues("assertion").length != 1) {
        throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
    }

    Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

    return new PartnerAssertionGrantAuthenticationToken(
            clientPrincipal, assertion, extractAdditionalParameters(request));
}
~~~

Đây là skeleton minh họa; PartnerAssertionGrantAuthenticationToken và extractAdditionalParameters(...) là thành phần do ứng dụng định nghĩa. Khi triển khai thực tế:
- Dùng getParameterValues để phát hiện tham số bắt buộc xuất hiện nhiều lần.
- Loại grant_type, client_id và tham số đã xử lý khỏi additional parameters.
- Không tin client_id trong form thay cho client principal đã được xác thực.
- Không ghi assertion nguyên bản vào log.
- Không nuốt lỗi của grant khác; trả null khi converter không phụ trách request.

### 10.2. Provider phải kiểm tra allowlist của client

Trước khi xác minh grant artifact, provider cần xác nhận client đã được xác thực và có quyền sử dụng grant:

~~~java
RegisteredClient registeredClient = authenticatedClient.getRegisteredClient();

if (!registeredClient.getAuthorizationGrantTypes()
        .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION)) {
    throw new OAuth2AuthenticationException(OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
}
~~~

Nếu grant không nằm trong tập grant của client, dừng xử lý ngay. Không được cho rằng việc converter nhận diện được grant_type đồng nghĩa client có quyền dùng nó.

## 11. Cấu hình extension grant tại OAuth2 Token Endpoint

Sau khi có converter và provider, đăng ký chúng trong cấu hình Authorization Server:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                        new PartnerAssertionGrantAuthenticationConverter())
                .authenticationProvider(
                        new PartnerAssertionGrantAuthenticationProvider(
                                authorizationService, tokenGenerator))
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

SAS cung cấp accessTokenRequestConverter(...) và authenticationProvider(...) như extension points của Token Endpoint. Hai lời gọi trên thêm custom components vào pipeline hiện có. Nếu có nhiều custom grant, có thể đăng ký nhiều converter/provider tương ứng hoặc dùng consumer để quản lý danh sách.

Ứng dụng vẫn cần các bean nền tảng như:
- RegisteredClientRepository để đọc client registration.
- OAuth2AuthorizationService để lưu authorization và token.
- OAuth2TokenGenerator để phát hành access token/refresh token.
- JWK source và token encoder nếu phát hành JWT.
- Security filter chain và client authentication configuration cho Token Endpoint.

Không xem filter chain ở trên là toàn bộ cấu hình Authorization Server độc lập.

## 12. Trách nhiệm của AuthenticationProvider khi phát hành token

Provider không chỉ kiểm tra client grant allowlist. Nó phải xác minh chính authorization grant theo contract đã thiết kế.

Với partner assertion dạng JWT, các bước kiểm tra có thể gồm:
1. Xác minh chữ ký bằng key của issuer được tin cậy.
2. Kiểm tra iss, aud, exp, iat và các claim bắt buộc.
3. Kiểm tra subject/partner identity có được phép dùng tại client hiện tại hay không.
4. Kiểm tra assertion chưa bị sử dụng lại; nếu có jti, dùng replay store có tính atomic.
5. Kiểm tra requested scope nằm trong tập scope được client và grant policy cho phép.
6. Xác định principal và quyền được cấp.
7. Tạo access token với audience, claims, lifetime và token type phù hợp.
8. Lưu authorization để hỗ trợ introspection, revocation và refresh nếu flow cho phép.

Không chấp nhận assertion chỉ vì decode được payload. Phải xác minh chữ ký, issuer, audience, thời gian và replay theo profile. Với grant dùng one-time code/assertion, consume grant phải atomic để hai request đồng thời không cùng đổi một grant lấy hai token.

### 12.1. Tạo OAuth2TokenContext

Provider sử dụng OAuth2TokenGenerator cùng OAuth2TokenContext để tạo token. Mẫu phần cốt lõi:

~~~java
OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext.builder()
        .registeredClient(registeredClient)
        .principal(clientPrincipal)
        .authorizationServerContext(AuthorizationServerContextHolder.getContext())
        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
        .authorizedScopes(authorizedScopes)
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .authorizationGrant(partnerAssertionAuthentication)
        .build();

OAuth2Token generatedAccessToken = tokenGenerator.generate(tokenContext);
if (generatedAccessToken == null) {
    throw new OAuth2AuthenticationException(new OAuth2Error(OAuth2ErrorCodes.SERVER_ERROR));
}
~~~

Sau khi sinh token, provider tạo OAuth2AccessToken, gắn token vào OAuth2Authorization cùng metadata claims nếu token là JWT, rồi gọi OAuth2AuthorizationService.save(...). Có lưu authorization mới giúp server quản lý token lifecycle nhất quán với các grant chuẩn.

Ví dụ rút gọn phần tạo authorization sau khi token đã được sinh và authorizedScopes đã được kiểm tra:

~~~java
OAuth2AccessToken accessToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        generatedAccessToken.getTokenValue(),
        generatedAccessToken.getIssuedAt(),
        generatedAccessToken.getExpiresAt(),
        authorizedScopes
);

OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(clientPrincipal.getName())
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .authorizedScopes(authorizedScopes)
        .accessToken(accessToken)
        .build();

authorizationService.save(authorization);
~~~

Đoạn code trên là phần minh họa; implementation hoàn chỉnh cần:
- Kiểm tra client principal có đúng kiểu và đang authenticated.
- Lưu principal name, registered client ID và authorization grant type.
- Lưu claims metadata khi token generator trả token có claims.
- Xử lý refresh token chỉ khi grant/policy cho phép.
- Trả OAuth2AccessTokenAuthenticationToken cho Token Endpoint.
- Không lưu raw assertion nếu không cần; nếu phải lưu để audit, hãy mã hóa hoặc lưu fingerprint.

## 13. Phân biệt đăng ký grant với việc phát hành token

| Việc cấu hình | Kết quả | Có đủ để dùng custom grant? |
| --- | --- | --- |
| Tạo AuthorizationGrantType | Có object biểu diễn identifier | Không |
| Thêm vào RegisteredClient | Client được allowlist grant | Không |
| Lưu qua RegisteredClientRepository | Server có thể đọc registration | Không |
| Đăng ký AuthenticationConverter | Token Endpoint có thể parse request | Chưa đủ |
| Đăng ký AuthenticationProvider | Có logic xác minh và phát hành token | Cần kết hợp converter |
| Cấu hình token generator và authorization service | Có thể phát hành và lưu token | Cần policy/validation đầy đủ |

Một client có thể được đăng ký partner_assertion nhưng request vẫn thất bại nếu:
- Server chưa cài converter/provider.
- Client chưa được xác thực.
- Provider không chấp nhận client đó.
- Assertion không hợp lệ hoặc đã bị replay.
- Scope vượt quá quyền được cấp.
- Token generator không hỗ trợ loại token yêu cầu.

Đây là lý do cần kiểm thử registration và Token Endpoint như hai lớp riêng biệt.

## 14. Quản lý grant type trong client lifecycle

Grant type là metadata bảo mật của client. Khi thêm hoặc xóa một grant:
- Kiểm tra owner, use case và lý do nghiệp vụ.
- Đánh giá grant có yêu cầu confidential client hoặc sender-constrained credential không.
- Kiểm tra grant-specific scopes và resource/audience.
- Cập nhật RegisteredClient qua repository có transaction.
- Đồng bộ metadata ở các node/cache.
- Audit actor, client ID, grant cũ, grant mới và thời điểm thay đổi.
- Đánh giá authorization/token đã phát hành theo grant cũ có cần thu hồi hay không.

Không tự động cấp custom grant cho mọi client mới. Nếu DCR được bật, validator phải áp dụng allowlist và policy tương tự registration tĩnh.

Khi bỏ grant khỏi RegisteredClient, provider vẫn có thể còn trong Token Endpoint. Provider phải kiểm tra allowlist ở mỗi request để client mất quyền ngay sau khi registration cập nhật. Không chỉ ẩn grant ở client UI hoặc metadata discovery.

Nếu thay identifier, nên coi đó là migration giao thức:
1. Tạo identifier mới và provider mới.
2. Quyết định giai đoạn tương thích giữa hai identifier.
3. Chỉ đăng ký grant mới cho client đã migrate.
4. Theo dõi usage của identifier cũ.
5. Thu hồi grant cũ sau thời hạn chuyển đổi.
6. Xóa provider cũ khi không còn client/authorization sử dụng.

## 15. Ma trận kiểm thử khai báo và sử dụng grant

| Tình huống | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Built-in grant | Đăng ký client_credentials | Grant xuất hiện trong RegisteredClient |
| Custom grant | Đăng ký Partner Assertion | Grant custom được lưu đúng URI |
| Wrong identifier | Tạo AuthorizationGrantType với URI khác | Không match allowlist |
| Duplicate registration | Thêm cùng grant nhiều lần | Tập grant không tạo quyền khác biệt |
| Client disallowed | Client không có custom grant gửi request | unauthorized_client |
| Provider missing | Client có grant nhưng server không cài provider | unsupported_grant_type hoặc lỗi endpoint tương ứng |
| Converter mismatch | Request dùng grant khác | Custom converter trả null, converter chuẩn tiếp tục |
| Missing assertion | Thiếu tham số bắt buộc | invalid_request |
| Duplicate assertion | Gửi assertion nhiều lần | invalid_request |
| Invalid signature | Assertion ký bằng key không tin cậy | invalid_grant |
| Wrong issuer/audience | Assertion không dành cho AS/client | invalid_grant |
| Expired assertion | Assertion quá hạn | invalid_grant |
| Replay | Gửi lại one-time assertion | Request sau bị từ chối |
| Scope escalation | Xin scope ngoài allowlist | Từ chối |
| Repository restart | Khởi động lại với JDBC repository | Grant vẫn được đọc đúng |
| Client update | Xóa custom grant khỏi registration | Provider từ chối client ở request tiếp theo |
| Concurrent redemption | Hai request dùng cùng assertion | Chỉ một request consume thành công |

Kiểm thử phải xác minh cả HTTP response và trạng thái lưu trữ. Ví dụ, một request bị từ chối không được tạo authorization hoặc token record ở trạng thái active.

### 15.1. Kiểm tra registration trong unit/integration test

Một test tập trung có thể kiểm tra grant type đã được thêm đúng:

~~~java
@Test
void partnerClientHasPartnerAssertionGrant() {
    RegisteredClient client = registeredClientRepository
            .findByClientId("partner-gateway");

    assertThat(client).isNotNull();
    assertThat(client.getAuthorizationGrantTypes())
            .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION);
}
~~~

Một integration test cho Token Endpoint nên kiểm tra thêm:
- Client authentication thực sự thành công.
- Request được converter của custom grant nhận diện.
- Provider xác minh assertion và kiểm tra grant allowlist.
- Authorization được lưu qua OAuth2AuthorizationService.
- Access token có claims/audience đúng và chỉ có scope được cho phép.
- Replay hoặc assertion không hợp lệ không tạo token mới.

Không chỉ test rằng Set trong RegisteredClient chứa custom grant. Bài kiểm thử đó xác nhận registration, nhưng không chứng minh extension grant đã hoạt động từ HTTP request đến token response.

## 16. Bài tập tình huống

Một hệ thống B2B có Authorization Server và nhiều partner gateway. Các gateway cần gửi một JWT assertion do hệ thống đối tác ký để lấy access token đọc đơn hàng. Authorization Server đặt tên extension grant là:

~~~text
https://auth.example.com/oauth/grants/partner-assertion
~~~

Chỉ client partner-gateway-a và partner-gateway-b được phép dùng grant này. Client customer-portal chỉ dùng Authorization Code + PKCE.

Hãy phân tích:
1. Vì sao partner-assertion phải là absolute URI?
2. Khai báo AuthorizationGrantType ở package nào và dùng chung ra sao?
3. Đăng ký grant cho hai partner gateway bằng RegisteredClient.Builder như thế nào?
4. Vì sao không cấp grant cho customer-portal?
5. Làm sao bảo đảm client đã được xác thực trước khi provider đọc assertion?
6. Provider phải kiểm tra những claim nào của JWT assertion?
7. Làm thế nào chống replay khi partner gửi cùng assertion hai lần?
8. Nếu client xin orders.write trong khi chỉ được cấp orders.read, kết quả phải ra sao?
9. Vì sao chỉ thêm grant vào RegisteredClient chưa đủ để Token Endpoint cấp token?
10. Khi thu hồi grant khỏi partner gateway, cần đồng bộ repository/cache/provider như thế nào?

**Gợi ý:** Dùng một hằng số AuthorizationGrantType duy nhất cho cả registration, converter, provider và test. RegisteredClient là allowlist theo client; provider vẫn phải kiểm tra allowlist ở runtime. Assertion cần xác minh chữ ký, issuer, audience, thời hạn và replay. Chỉ cấp scope tối thiểu và không cho public client sử dụng flow đòi hỏi credential mà client không thể bảo vệ.

## 17. Checklist triển khai

1. **Protocol:** kiểm tra grant có chuẩn sẵn hay cần extension grant.
2. **Identifier:** dùng absolute URI ổn định, unique và thuộc namespace được quản lý.
3. **Constant:** khai báo một AuthorizationGrantType dùng chung trong code.
4. **Client allowlist:** chỉ thêm grant cho RegisteredClient được phê duyệt.
5. **Client authentication:** chọn authentication method phù hợp loại client và threat model.
6. **Scopes:** tách scope khỏi grant type; áp dụng least privilege.
7. **Persistence:** lưu grant qua RegisteredClientRepository; dùng JDBC/custom repository bền vững trong production.
8. **DCR:** validate grant_types theo server allowlist và policy client.
9. **Converter:** parse request đúng grant, phát hiện tham số thiếu/lặp và không log credential.
10. **Provider:** xác minh client, grant allowlist, grant artifact, issuer/audience/time/replay.
11. **Token issuance:** tạo token context, generate token và persist authorization.
12. **Error handling:** phân biệt unsupported_grant_type, unauthorized_client, invalid_grant, invalid_request.
13. **Lifecycle:** audit thay đổi grant và đồng bộ cache/cluster.
14. **Testing:** kiểm tra cả registration, token endpoint, replay, scope escalation và persistence.
15. **Documentation:** công bố contract tham số, identifier, client eligibility, scopes, token claims và lỗi.

## 18. Tài liệu chuẩn và Spring cần đối chiếu

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.5 Extension Grants](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): absolute URI trong grant_type và extension grant request.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): hướng dẫn bảo mật OAuth hiện đại khi chọn grant và xác thực client.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): grant chuẩn cho use case token exchange.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): converter, provider, cấu hình Token Endpoint và request custom grant.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth2TokenEndpointConfigurer và extension points.
- [Spring Authorization Server 1.5.8 — RegisteredClient.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html): authorizationGrantType và authorizationGrantTypes.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient và RegisteredClientRepository.
- [Spring Security — AuthorizationGrantType API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/AuthorizationGrantType.html): constructor, built-in constants và getValue().

**Ghi nhớ:** AuthorizationGrantType biểu diễn identifier của authorization grant. RegisteredClient.Builder.authorizationGrantType(...) đăng ký grant vào allowlist của một client; nó không tự cài logic cấp token. Với custom extension grant, cần identifier absolute URI ổn định, converter để parse request và provider để xác thực grant, kiểm tra client allowlist, phát hành token và lưu authorization. Luôn tách grant type khỏi client authentication method và scope, chỉ cấp grant cho client phù hợp, và kiểm tra quyền ở phía Authorization Server trong mọi token request.
