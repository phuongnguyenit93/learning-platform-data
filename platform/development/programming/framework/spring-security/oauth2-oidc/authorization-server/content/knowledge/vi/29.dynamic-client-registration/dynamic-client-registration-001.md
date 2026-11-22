# OAuth 2.0 Dynamic Client Registration và OIDC Client Registration

## 1. Mục tiêu và bối cảnh

Trong chương **Đăng ký client động** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, OAuth 2.0 client thường phải được đăng ký trước tại Authorization Server (AS). Cách làm truyền thống yêu cầu quản trị viên hoặc quy trình provisioning tạo client, cấu hình redirect URI, grant type, scope và phương thức xác thực client. Khi có nhiều ứng dụng, tenant, môi trường triển khai hoặc phần mềm do đối tác phát triển, quy trình thủ công có thể trở thành nút thắt.

**Dynamic Client Registration (DCR)** cho phép một client hoặc tổ chức phát triển client gửi metadata tới Registration Endpoint để AS tạo một client registration và trả về định danh cùng cấu hình cần thiết. Với OpenID Connect (OIDC), giao thức đăng ký được định nghĩa trong **OpenID Connect Dynamic Client Registration 1.0**. OAuth 2.0 có chuẩn tương thích là **RFC 7591**; quản lý cấu hình client sau đăng ký được mở rộng bởi **RFC 7592**.

**Spring Authorization Server (SAS)** hỗ trợ OIDC Client Registration Endpoint thông qua `OidcClientRegistrationEndpointConfigurer`. Endpoint này mặc định bị tắt; khi bật, nó cung cấp xử lý registration và Client Read theo implementation của SAS. Việc đăng ký động vẫn phải được kiểm soát bằng access token, metadata validation, persistence và chính sách cấp quyền phù hợp.

Sau bài học, bạn có thể:

- Phân biệt static client registration, OAuth 2.0 DCR (RFC 7591) và OIDC Client Registration 1.0.
- Hiểu vai trò của Client Registration Endpoint, Initial Access Token, Registration Access Token và Registration Client URI.
- Đọc và xây dựng registration request/response theo JSON metadata contract.
- Phân biệt OIDC Client Read với các thao tác update/delete trong RFC 7592.
- Bật `clientRegistrationEndpoint` trong `OAuth2AuthorizationServerConfigurer`.
- Cấu hình registrar client, `client.create`, `client.read` và `JwtDecoder`.
- Ánh xạ metadata sang `RegisteredClient` và lưu bền vững bằng `RegisteredClientRepository`.
- Tùy chỉnh converter/provider/validator để hỗ trợ metadata riêng mà vẫn giữ validation mặc định.
- Bảo vệ redirect URI, grant types, scopes, client authentication, software statements và registration credentials.
- Thiết kế vòng đời, thu hồi, kiểm toán, giới hạn abuse và kiểm thử DCR trong môi trường production.

**Phạm vi phiên bản:** Code minh họa hướng tới **Spring Authorization Server 1.5.x**, **Spring Security 6.x** và **Spring Boot 3.x**; một số API có thể khác ở bản 1.0/1.1 hoặc các phiên bản tiếp theo. Tài liệu Spring hiện hành mô tả SAS 1.5.8. Các quy tắc giao thức dựa trên RFC 7591, RFC 7592 và OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2. Đọc response và kiểm tra endpoint thật của dependency đang dùng trước khi công bố integration contract.

## 2. Vì sao cần đăng ký client động?

Một OAuth2 client cần metadata để AS biết cách xử lý request và cấp token. Metadata điển hình gồm redirect URI hợp lệ, response type và grant type, scope được yêu cầu, client authentication method tại Token Endpoint, loại ứng dụng (web/native), JWK Set hoặc JWKS URI của client nếu dùng private key JWT/request signing, thông tin hiển thị và các lựa chọn OIDC.

Với static registration, người vận hành tạo cấu hình trước và cấp `client_id` cho nhóm phát triển. Với DCR, quá trình này được thực hiện bằng giao thức HTTP/JSON.

### 2.1. Static registration và dynamic registration

| Tiêu chí | Static registration | Dynamic registration |
| --- | --- | --- |
| Tạo client | Admin/provisioning tạo thủ công hoặc qua API nội bộ | Client/registrar gửi registration request |
| Cấp client ID | Quy trình vận hành | AS cấp khi registration thành công |
| Thay đổi metadata | Qua admin/config deployment | Qua registration workflow hoặc client configuration endpoint được hỗ trợ |
| Kiểm soát | Dễ gắn với quy trình phê duyệt hiện có | Phải thiết kế initial access token, policy và rate limit |
| Phù hợp | Số client ít, danh tính đối tác đã biết | Nhiều deployment/tenant, onboarding tự động |
| Rủi ro | Cấu hình thủ công sai hoặc drift | Spam registration, metadata giả, redirect URI abuse, credential leakage |

DCR không tự động làm một ứng dụng trở thành client đáng tin cậy. AS vẫn phải quyết định ai được đăng ký, metadata nào được chấp nhận và client được phép sử dụng grant/scope nào.

### 2.2. Những tình huống phù hợp

- Nền tảng SaaS cấp một client riêng cho mỗi tenant sau khi tenant hoàn tất onboarding.
- Sản phẩm tích hợp với nhiều đối tác, mỗi đối tác có redirect URI và khóa riêng.
- Phần mềm được triển khai tại nhiều tổ chức với URL callback khác nhau.
- OIDC relying party cần đăng ký metadata với OpenID Provider theo giao thức chuẩn.
- Một portal provisioning cấp registration token có giới hạn cho developer hoặc deployment agent.

### 2.3. Khi nào không nên mở DCR công khai?

Open registration cho phép bất kỳ ai gửi metadata mà không cần Initial Access Token. Điều này có thể phù hợp một số ecosystem, nhưng tạo ra chi phí và rủi ro: attacker tạo số lượng lớn client; client giả tên/logo của thương hiệu; metadata chứa redirect URI do attacker kiểm soát; registration cũ khó phân loại; AS không biết ai chịu trách nhiệm nếu không có developer identity/attestation.

Với nền tảng doanh nghiệp, **protected dynamic registration** thường là điểm bắt đầu an toàn hơn: chỉ registrar/developer đã được cấp quyền mới nhận Initial Access Token để đăng ký client.

## 3. Các chuẩn và ranh giới giao thức

Ba tài liệu thường được nhắc cùng nhau nhưng có phạm vi khác nhau.

| Chuẩn | Vai trò | Phạm vi |
| --- | --- | --- |
| RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol | Định nghĩa đăng ký OAuth2 client bằng metadata JSON | Registration request/response, client metadata và Initial Access Token |
| OpenID Connect Dynamic Client Registration 1.0 | Định nghĩa cách OIDC RP đăng ký với OP và đọc thông tin registration | OIDC client metadata, registration response, Client Configuration Endpoint và Client Read |
| RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol | Mở rộng quản lý registration sau khi tạo | Đọc, cập nhật và xóa client registration bằng Registration Access Token |

OIDC Registration 1.0 tương thích với RFC 7591 và định nghĩa Client Configuration Endpoint cho thao tác **GET Client Read**. RFC 7592 bổ sung các thao tác quản lý như PUT/DELETE. Không nên mặc định một OIDC Client Registration Endpoint hỗ trợ toàn bộ RFC 7592 chỉ vì response có `registration_client_uri`.

### 3.1. DCR không phải Client Credentials grant

Hai khái niệm có liên quan nhưng khác mục đích:

- `client_credentials` là OAuth2 grant để client lấy access token truy cập resource.
- DCR là giao thức để tạo một client registration tại AS.
- Một registrar client có thể dùng `client_credentials` để lấy **Initial Access Token** mang scope `client.create`.
- Client mới được tạo có grant types và authentication methods riêng trong registration metadata.

DCR không tự cấp user session và không thay thế Authorization Code Flow hoặc các grant khác.

### 3.2. OIDC Registration Endpoint và discovery

OIDC Provider Configuration có thể công bố trường `registration_endpoint`. RP có thể lấy URL từ discovery document thay vì hard-code endpoint.

Không tự nối `/connect/register` vào issuer rồi giả định mọi deployment dùng path mặc định. Kiểm tra metadata do OP công bố, TLS và issuer trước khi gọi.

## 4. Vòng đời registration

Một flow protected registration điển hình:

```mermaid
sequenceDiagram
    autonumber
    participant D as Developer / Deployment Agent
    participant R as Registrar Client
    participant AS as Authorization Server
    participant DB as RegisteredClientRepository
    participant C as Newly Registered Client

    D->>R: Request permission to provision client
    R->>AS: Token request: client_credentials + client.create
    AS-->>R: Initial Access Token
    R->>AS: POST registration_endpoint + Bearer token + JSON metadata
    AS->>AS: Validate token, metadata and policy
    AS->>DB: Persist RegisteredClient
    AS-->>R: 201 Created + client_id + credentials + registration metadata
    AS-->>R: registration_access_token + registration_client_uri
    R->>C: Deliver client credentials securely
    C->>AS: Normal OAuth/OIDC flow using assigned client_id
    C->>AS: GET registration_client_uri + registration access token
    AS-->>C: Current client registration metadata
```

Các giai đoạn:

1. Developer hoặc deployment system được phê duyệt.
2. Registrar client lấy Initial Access Token.
3. Registrar gửi metadata tới Client Registration Endpoint.
4. AS kiểm tra access token, redirect URI, grant, scope, auth method và policy.
5. AS tạo `RegisteredClient` và lưu vào repository.
6. AS trả registration response; client lưu credentials an toàn.
7. Client sử dụng `client_id` và phương thức xác thực được cấp.
8. Client có thể đọc registration của chính nó nếu AS cấp Registration Access Token và Client Configuration Endpoint.

### 4.1. Ba định danh/credential không được nhầm

| Giá trị | Do ai cấp? | Dùng để làm gì? | Phạm vi |
| --- | --- | --- | --- |
| `client_id` | AS | Định danh client trong các OAuth/OIDC requests | Không phải secret |
| Initial Access Token | AS hoặc provisioning workflow | Cho phép registrar gọi registration endpoint | Cấp quyền tạo client theo policy |
| Registration Access Token | AS sau registration nếu hỗ trợ | Xác thực Client Configuration/Read request | Gắn với một registration |
| `client_secret` | AS nếu client là confidential và method cần secret | Client authentication tại Token Endpoint | Secret của client |
| `registration_client_uri` | AS | URL chính xác để client đọc cấu hình registration | Không phải credential; cần đi cùng Registration Access Token |

Initial Access Token và Registration Access Token đều có thể là bearer token, nhưng chúng có **mục đích và quyền khác nhau**. Không dùng Initial Access Token để gọi API business; không dùng client secret thay Registration Access Token.

## 5. Client metadata: những gì client được yêu cầu đăng ký?

Registration request là JSON object với metadata ở cấp cao nhất. Ví dụ:

```json
{
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "client_name": "Partner Portal",
  "client_uri": "https://portal.example.com",
  "policy_uri": "https://portal.example.com/privacy",
  "tos_uri": "https://portal.example.com/terms",
  "token_endpoint_auth_method": "private_key_jwt",
  "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
  "scope": "openid profile email"
}
```

Đây là request minh họa. AS có thể từ chối metadata, thay giá trị được phép thay thế, áp dụng default hoặc bỏ qua field không hỗ trợ. Client phải đọc registration response và sử dụng **giá trị AS đã chấp nhận**, không coi mọi giá trị trong request là cấu hình đã được duyệt.

### 5.1. Nhóm metadata quan trọng

| Metadata | Ý nghĩa | Lưu ý kiểm soát |
| --- | --- | --- |
| `redirect_uris` | Các callback được đăng ký | Bắt buộc trong OIDC registration; phải validate chặt |
| `response_types` | Response types client dự định dùng | Không bật implicit flow nếu không có lý do tương thích rõ |
| `grant_types` | Grant types client dự định dùng | Cấp tối thiểu cần thiết |
| `application_type` | `web` hoặc `native` | Ảnh hưởng quy tắc redirect URI |
| `client_name` | Tên hiển thị | Không phải bằng chứng danh tính phần mềm |
| `logo_uri` | URL logo | Có thể bị lạm dụng để giả mạo thương hiệu hoặc tracking |
| `client_uri` | Website của client | Kiểm tra scheme/host và quyền hiển thị |
| `policy_uri` / `tos_uri` | Chính sách riêng tư/điều khoản | Cần URL hợp lệ và có thể kiểm tra |
| `token_endpoint_auth_method` | Cách client xác thực tại Token Endpoint | Phải nằm trong allowlist được AS hỗ trợ |
| `jwks_uri` | URL JWK Set của client | HTTPS, kiểm tra remote key source/SSRF |
| `jwks` | JWK Set gửi trực tiếp | Chỉ public keys; không nhận private/symmetric key |
| `scope` | Scope client yêu cầu | AS vẫn áp policy và giới hạn quyền |
| `subject_type` | `public` hoặc `pairwise` | Chỉ khi OP hỗ trợ và metadata policy cho phép |
| `sector_identifier_uri` | Nguồn danh sách redirect URI cho pairwise subject | Phải validate HTTPS và JSON document |
| `contacts` | Địa chỉ liên hệ người chịu trách nhiệm | PII của người liên hệ; giới hạn quyền truy cập |
| `software_statement` | JWT attestation metadata do publisher ký | Phải xác minh chữ ký, issuer, audience và thời hạn |

### 5.2. Grant type và response type phải nhất quán

Với OIDC Authorization Code Flow:

```json
{
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"]
}
```

`response_types` mô tả response type ở Authorization Endpoint; `grant_types` mô tả grant tại Token Endpoint. Ví dụ `code` tương ứng với `authorization_code`.

Không thêm `client_credentials` chỉ vì registrar client dùng grant đó. Registrar và client mới là hai registration khác nhau. Client mới chỉ nhận grant cần cho use case của nó.

### 5.3. Web client và native client

- Web confidential client thường xác thực bằng `private_key_jwt`, mTLS hoặc client secret được bảo vệ ở backend.
- Native app là public client; không nhúng client secret dùng chung vào binary phân phối.
- Public client nên sử dụng Authorization Code + PKCE với `S256`.
- Web redirect URI production nên dùng HTTPS.
- Native loopback redirect có thể dùng localhost/loopback theo quy tắc dành cho native app.
- Không coi `application_type` là bằng chứng client confidential/public; auth method và deployment model phải được đánh giá riêng.

### 5.4. JWK metadata

Nếu client dùng `private_key_jwt` hoặc ký request, AS cần public key để xác minh. `jwks_uri` trỏ đến JWK Set public của client. Không chấp nhận private key fields hoặc symmetric secrets trong JWK Set.

Khi dùng `jwks_uri`, AS cần kiểm soát việc truy xuất từ xa: HTTPS, DNS, redirect, response size, timeout và địa chỉ mạng private. Nếu client gửi `jwks` trực tiếp, server vẫn phải validate key type, algorithm và mục đích sử dụng.

## 6. Registration request và response theo OIDC

### 6.1. HTTP request

Client gửi POST với content type JSON:

```http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer <INITIAL_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json

{
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"],
  "client_name": "Partner Portal",
  "token_endpoint_auth_method": "private_key_jwt",
  "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
  "scope": "openid profile email"
}
```

Endpoint path trong ví dụ là mặc định thường dùng của SAS. Production phải dùng `registration_endpoint` được công bố trong OIDC discovery hoặc URL đã được quản trị xác nhận.

### 6.2. Registration response

Khi thành công, OIDC registration endpoint thường trả HTTP `201 Created` và JSON chứa metadata đã đăng ký cùng các giá trị do AS cấp:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "portal-tenant-42",
  "client_id_issued_at": 1790000000,
  "client_secret": "REDACTED_IF_ISSUED",
  "client_secret_expires_at": 1792592000,
  "registration_access_token": "REDACTED_REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=portal-tenant-42",
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_method": "private_key_jwt",
  "scope": "openid profile email"
}
```

Các trường là ví dụ, không đảm bảo SAS luôn trả đủ mọi field. `client_secret` chỉ xuất hiện khi phương thức/loại client cần secret. Nếu server phát client secret, `client_secret_expires_at` phải được xử lý theo contract; giá trị `0` biểu thị secret không hết hạn theo OIDC registration metadata.

### 6.3. Server có thể chuẩn hóa metadata

AS có thể từ chối một field không hợp lệ, áp default cho field bị bỏ qua, thay một số giá trị được phép thay thế, bỏ qua field không hỗ trợ hoặc giới hạn grant, scope, response type và authentication method theo policy.

Với `redirect_uris`, không được tự ý thay bằng URI không do client đăng ký và không được nới validation. Client nên đọc response để biết chính xác cấu hình được lưu.

### 6.4. Error response

Registration error thường là HTTP `400 Bad Request` với JSON error, ví dụ:

```json
{
  "error": "invalid_redirect_uri",
  "error_description": "One or more redirect URI values are invalid"
}
```

Các lỗi có thể gặp:

- `invalid_redirect_uri`: redirect URI không hợp lệ.
- `invalid_client_metadata`: một metadata field không hợp lệ.
- `invalid_token`/Bearer error: Initial Access Token không hợp lệ hoặc hết hạn.
- Lỗi server/storage: AS không thể hoàn tất registration.

Không trả stack trace, secret, thông tin token nội bộ hoặc dữ liệu của client khác trong error description.

## 7. Initial Access Token: bảo vệ quyền tạo client

RFC 7591 cho phép AS yêu cầu Initial Access Token để giới hạn bên được phép đăng ký. OIDC Registration 1.0 cũng mô tả token này như một cơ chế provisioning tùy chọn. Cách cấp và validate token nằm ngoài phạm vi chuẩn; tổ chức cần định nghĩa quy trình riêng.

### 7.1. Registrar client

Một registrar client là client đã được cấu hình trước để thực hiện provisioning. Ví dụ:

```java
RegisteredClient registrarClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("platform-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
```

Đây là ví dụ cấu hình SAS. Trong production, dùng secret ngẫu nhiên và secret manager; không dùng `{noop}` hoặc secret dễ đoán; chỉ provisioning service giữ credential registrar; giới hạn registrar theo organization/tenant/environment; theo dõi mọi registration được tạo; không cấp `client.create` cho client business thông thường.

### 7.2. Lấy Initial Access Token trong SAS

SAS how-to sử dụng `client_credentials` và yêu cầu token request có **duy nhất scope `client.create`**:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <BASE64_REGISTRAR_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

Sau khi nhận access token, registrar dùng nó làm Bearer token ở registration endpoint.

**Hành vi cụ thể của SAS 1.5.x:** tài liệu hướng dẫn SAS mô tả Initial Access Token này chỉ được dùng một lần; sau khi client được đăng ký thành công, token bị invalidated. Đây là chi tiết implementation của hướng dẫn SAS, không nên khái quát thành yêu cầu chung của mọi DCR server.

### 7.3. Không gộp scope read vào Initial Access Token

SAS guide yêu cầu token đăng ký có một scope duy nhất `client.create`. Việc registrar client được cấu hình thêm `client.read` không có nghĩa token đăng ký được phép mang cả hai scope.

Hãy tách rõ token dùng tạo client (`client.create`) và token dùng đọc registration (`client.read`) theo cơ chế Registration Access Token/client configuration của SAS.

### 7.4. Quy trình cấp token ban đầu

Một provisioning workflow có thể:

1. Xác minh developer/organization qua portal hoặc CI workload identity.
2. Tạo Initial Access Token có thời hạn ngắn.
3. Gắn token với tenant, môi trường, quota và policy cần thiết.
4. Chuyển token qua secret channel tới deployment agent.
5. Ghi audit issuance metadata, không ghi raw token.
6. Cho phép token được sử dụng đúng số lần/đúng thời gian.
7. Thu hồi token nếu workflow bị hủy hoặc phát hiện compromise.

Không cấp một Initial Access Token vĩnh viễn dùng chung cho tất cả developer.

## 8. Registration Access Token và Client Configuration Endpoint

Sau khi đăng ký, response có thể chứa `registration_access_token` và `registration_client_uri`. Registration Access Token là credential có quyền truy cập registration; cần được bảo vệ như secret.

### 8.1. Client Read

OIDC Registration 1.0 định nghĩa GET Client Read:

```http
GET /connect/register?client_id=portal-tenant-42 HTTP/1.1
Host: auth.example.com
Authorization: Bearer <REGISTRATION_ACCESS_TOKEN>
Accept: application/json
```

**Client phải sử dụng nguyên URL trong `registration_client_uri`** mà AS trả về. Không tự xây URL bằng cách nối path hoặc thay query parameter. AS có thể dùng path parameter, query parameter hoặc cấu trúc URL riêng. Nếu AS trả `registration_client_uri`, URL đó phải dùng HTTPS và response phải trả kèm `registration_access_token`; không được chỉ trả một trong hai giá trị.

Response thường là HTTP `200 OK` và trả metadata hiện tại của registration. Không nên cache registration response chứa secret hoặc registration access token ở nơi không an toàn.

### 8.2. Client Read không phải update/delete

OIDC Registration 1.0 định nghĩa thao tác GET cho Client Read. RFC 7592 mở rộng DCR management với các thao tác cập nhật và xóa registration, sử dụng Registration Access Token.

Theo tài liệu SAS 1.5.8, `OidcClientRegistrationEndpointFilter` xử lý Client Registration và Client Read; provider mặc định bao gồm `OidcClientRegistrationAuthenticationProvider` và `OidcClientConfigurationAuthenticationProvider`. Không suy ra endpoint SAS đã hỗ trợ PUT/DELETE RFC 7592 nếu phiên bản/ứng dụng chưa triển khai và kiểm thử các thao tác đó.

### 8.3. Quyền của Registration Access Token

- Chỉ dùng cho registration tương ứng.
- Không dùng làm access token truy cập business API.
- Không gửi trong URL/query string.
- Không ghi vào application logs, tracing hoặc support ticket.
- Có quy trình revoke/rotate khi bị lộ.
- Client phải giữ `registration_client_uri` cùng credential ở secret storage phù hợp.

Nếu token mất, không nên cho phép khôi phục registration chỉ bằng `client_id` công khai. Cần admin recovery hoặc provisioning workflow đã xác thực.

## 9. Bật OIDC Client Registration Endpoint trong SAS

OIDC phải được bật trong Authorization Server configurer, sau đó bật riêng Client Registration Endpoint. OIDC Client Registration Endpoint **bị tắt mặc định**, vì không phải deployment nào cũng cần DCR.

### 9.1. Cấu hình SecurityFilterChain

```java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(oidc ->
                            oidc.clientRegistrationEndpoint(
                                    Customizer.withDefaults())))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là khung cấu hình. Ứng dụng vẫn cần các bean hạ tầng như `RegisteredClientRepository`, `OAuth2AuthorizationService`, key source, user authentication và `AuthorizationServerSettings` phù hợp.

### 9.2. Đăng ký JwtDecoder

SAS yêu cầu `JwtDecoder` cho OIDC Client Registration Endpoint. Nếu ứng dụng đã có `JWKSource<SecurityContext>`, có thể tạo decoder như sau:

```java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
            .jwtDecoder(jwkSource);
}
```

Không bỏ qua decoder chỉ vì endpoint đã nằm trong Authorization Server filter chain. Endpoint cần xác minh Bearer access token trước khi xử lý registration/read request.

### 9.3. Đường dẫn endpoint

Đường dẫn mặc định thường là `/connect/register`. Có thể cấu hình qua `AuthorizationServerSettings`:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/register")
            .build();
}
```

Nếu đổi endpoint path, phải đồng bộ discovery metadata, gateway, reverse proxy, client registrar và integration tests. Client nên lấy URL từ `registration_endpoint` hoặc cấu hình tin cậy, không hard-code mặc định.

### 9.4. Endpoint là protected resource

Theo tài liệu SAS 1.5.8:

- Client Registration request yêu cầu Bearer access token có scope `client.create`.
- Client Read request yêu cầu access token có scope `client.read`.
- `JwtDecoder` bean là bắt buộc.
- Endpoint filter dùng converter/provider mặc định để xử lý registration và read.

Đây là hành vi của implementation SAS được mô tả trong tài liệu, không phải mô tả mọi server hỗ trợ open DCR theo RFC 7591.

## 10. Cấu hình registrar và persistence

### 10.1. RegisteredClientRepository

SAS dùng `RegisteredClientRepository` để lưu và truy xuất client registration. Ví dụ đơn giản trong test có thể dùng `InMemoryRegisteredClientRepository`, nhưng production nên dùng persistence bền vững, ví dụ `JdbcRegisteredClientRepository` hoặc implementation phù hợp.

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}
```

Đoạn code giả định schema SAS đã được triển khai và datasource được cấu hình. In-memory repository phù hợp demo/test đơn giản; nó không chia sẻ trạng thái giữa các replica và mất registration khi process restart.

### 10.2. Mapping metadata sang RegisteredClient

Registration provider chuyển OIDC metadata thành `RegisteredClient` thông qua converter. Các thông tin quan trọng được lưu trong client ID, client secret được xử lý theo chính sách credential storage (thường lưu dạng hash), client authentication methods, authorization grant types, redirect URIs, scopes, client settings, token settings và metadata mở rộng trong settings nếu ứng dụng có converter riêng.

Không lưu toàn bộ JSON request vào một cột rồi dùng nó làm nguồn duy nhất cho authorization. AS cần một registration model có kiểu dữ liệu và validation rõ ràng.

### 10.3. Client ID phải duy nhất

`client_id` được AS cấp và phải duy nhất trong phạm vi AS. Không dùng email, tenant name hoặc display name làm client ID nếu chúng có thể thay đổi hoặc trùng nhau. Internal registration ID của database và public `client_id` là hai khái niệm riêng.

### 10.4. Client secret storage

Nếu registration tạo confidential client với secret, hãy tạo secret có entropy cao, lưu dạng hash phù hợp với `PasswordEncoder`, không ghi secret vào logs, chỉ chuyển secret cho đúng owner qua kênh an toàn, có chính sách expiry/rotation và không phát secret cho public client dùng `none` authentication.

Không nhầm secret của client mới với secret của registrar client.

## 11. Tùy chỉnh validation và provider trong SAS

`OidcClientRegistrationEndpointConfigurer` cung cấp các extension point cho pre-processing, main processing và post-processing.

| Extension point | API | Trách nhiệm |
| --- | --- | --- |
| Request conversion | `clientRegistrationRequestConverter` | Chuyển HTTP request thành registration authentication |
| Converter collection | `clientRegistrationRequestConverters` | Thêm/thay converter trong danh sách |
| Provider | `authenticationProvider` | Thêm provider xử lý registration/read |
| Provider collection | `authenticationProviders` | Tùy chỉnh danh sách provider mặc định |
| Success handler | `clientRegistrationResponseHandler` | Tạo HTTP registration/read response |
| Error handler | `errorResponseHandler` | Trả lỗi registration/read |

Không thay toàn bộ pipeline nếu chỉ cần thêm một kiểm tra metadata. Giữ các converter/provider mặc định giúp bảo toàn việc parse và xử lý giao thức.

### 11.1. Tùy chỉnh validator của provider

SAS guide minh họa việc cấu hình validator cho `OidcClientRegistrationAuthenticationProvider`. Ví dụ sau giữ các validator tiêu chuẩn về redirect URI, post-logout redirect URI, JWK Set URI và scope:

```java
private Consumer<List<AuthenticationProvider>>
        configureRegistrationValidators() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OidcClientRegistrationAuthenticationProvider registrationProvider) {

            registrationProvider.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_REDIRECT_URI_VALIDATOR
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .SIMPLE_SCOPE_VALIDATOR));
        }
    });
}
```

Sau đó cấu hình trong DSL:

```java
authorizationServer.oidc(oidc ->
        oidc.clientRegistrationEndpoint(endpoint ->
                endpoint.authenticationProviders(
                        configureRegistrationValidators())));
```

Tên lớp/phương thức validator cần đối chiếu version dependency. Ví dụ trên minh họa cách nối validator chuẩn; khi thay validator, phải bảo đảm không vô tình bỏ validation bắt buộc khác của version đang dùng.

### 11.2. Thêm metadata tùy chỉnh

Giả sử nền tảng muốn lưu `logo_uri` hoặc `contacts`. Cần mở rộng cả hai chiều:

1. Chuyển OIDC registration metadata sang `RegisteredClient` hoặc client settings.
2. Chuyển `RegisteredClient` về OIDC registration response khi Client Read.

SAS guide minh họa các converter:

- `OidcClientRegistrationRegisteredClientConverter`: OIDC registration → RegisteredClient.
- `RegisteredClientOidcClientRegistrationConverter`: RegisteredClient → OIDC registration.
- `OidcClientRegistrationAuthenticationProvider`: cấu hình registered-client converter và response converter.
- `OidcClientConfigurationAuthenticationProvider`: cấu hình converter cho Client Read.

Không chỉ lưu custom field ở registration mà quên response/read; nếu không, client sẽ không đọc lại được cấu hình đã đăng ký.

### 11.3. Ví dụ cấu hình provider converters

Khung cấu hình theo API SAS 1.5.x:

```java
private Consumer<List<AuthenticationProvider>>
        configureCustomMetadataConverters(
                Converter<OidcClientRegistration, RegisteredClient>
                        registeredClientConverter,
                Converter<RegisteredClient, OidcClientRegistration>
                        clientRegistrationConverter) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setRegisteredClientConverter(
                    registeredClientConverter);
            registrationProvider.setClientRegistrationConverter(
                    clientRegistrationConverter);
        }

        if (provider instanceof
                OidcClientConfigurationAuthenticationProvider configurationProvider) {
            configurationProvider.setClientRegistrationConverter(
                    clientRegistrationConverter);
        }
    });
}
```

Các converter truyền vào là implementation do ứng dụng xây dựng hoặc delegate từ converter mặc định. Đây là khung tích hợp, cần kiểm tra constructor và package theo version. Chỉ lưu metadata đã được allowlist và validate; không copy mọi field tùy ý vào client settings.

### 11.4. Custom metadata không tự trở thành quyền

Ví dụ `tenant_id` hoặc `billing_plan` có thể được lưu trong registration settings, nhưng giá trị do client gửi không được xem là nguồn có thẩm quyền. Server phải xác minh tenant/plan từ provisioning system. Client không được tự khai `tenant_id` để chuyển mình sang tenant khác hoặc tự nâng quyền.


## 12. Software Statements và attestation

RFC 7591 hỗ trợ `software_statement` như một JWT chứa metadata được software publisher hoặc authority ký. Nó có thể giúp AS xác minh nguồn gốc phần mềm và metadata đã được attestation.

Một software statement có thể mang software identifier/version, publisher/organization, redirect URI claims, approved grant types/scopes, JWK information hoặc policy references, thời gian phát hành/hết hạn và định danh statement.

### 12.1. Xác minh software statement

Không tin JWT chỉ vì nó parse được. AS cần kiểm tra:

- Chữ ký bằng key của publisher/authority đã tin cậy.
- `iss` và `aud` theo trust contract.
- `exp`, `iat` và thời hạn cho phép.
- `jti` hoặc replay controls nếu profile cần.
- Metadata trong statement có khớp request không.
- Publisher có được phép đăng ký loại client này không.
- Statement có bị thu hồi hoặc signer bị compromise không.

### 12.2. SAS và software_statement

SAS hỗ trợ mở rộng metadata thông qua converter/provider, nhưng không nên mặc định mọi software statement profile được xác minh tự động chỉ vì OIDC DCR endpoint đã bật. Nếu cần attestation, triển khai validator/trust service rõ ràng trước khi lưu registration.

Không dùng một `software_statement` đã ký làm lý do bỏ redirect URI validation hoặc registrar authorization. Attestation là tín hiệu trust bổ sung; AS vẫn phải áp policy của chính mình.

## 13. Redirect URI: ranh giới bảo mật quan trọng nhất

Redirect URI quyết định nơi Authorization Server gửi authorization response. Nếu attacker đăng ký redirect URI do họ kiểm soát, họ có thể nhận authorization code hoặc token response trong các flow cấu hình sai.

### 13.1. So khớp chính xác

- So sánh redirect URI request với giá trị đã đăng ký theo quy tắc protocol.
- Không dùng wildcard domain tùy tiện.
- Không chấp nhận prefix match kiểu `https://trusted.example.com.attacker.test`.
- Không tự bỏ path/query khi so sánh.
- Không cho client tự sửa redirect URI trong authorization request.
- Revalidate khi client cập nhật metadata.

### 13.2. Web và native redirect URI

| Client type | Redirect URI thường dùng | Chính sách |
| --- | --- | --- |
| Web | HTTPS callback do client kiểm soát | Không cho HTTP production tùy tiện |
| Native | Custom URI scheme hoặc loopback redirect phù hợp | Áp dụng quy tắc native app và PKCE |
| SPA/browser-based public client | HTTPS callback | Dùng Authorization Code + PKCE; không nhúng secret |

`localhost` không phải cách lách validation cho web confidential client. Loopback redirect là trường hợp riêng của native application theo profile tương ứng.

### 13.3. Không cho wildcard vì tiện triển khai

Ví dụ nguy hiểm:

```text
https://*.example.com/callback
https://example.com/*
https://portal.example.com/callback*
```

Wildcard có thể mở đường cho subdomain takeover hoặc redirect sang ứng dụng không thuộc quyền kiểm soát. Nếu nền tảng cần nhiều tenant host, hãy đăng ký chính xác từng redirect URI sau khi xác minh domain ownership hoặc dùng quy trình onboarding domain riêng.

### 13.4. Post logout redirect URI

Nếu hỗ trợ OIDC logout, `post_logout_redirect_uris` cũng phải được validate và ràng buộc với registration. Không tái sử dụng allowlist redirect URI cho logout một cách thiếu kiểm tra; hai endpoint có thể có contract và validator khác nhau.

## 14. Giới hạn grant, scope và client authentication

DCR là điểm tạo security principal cho các OAuth flows. Một metadata request không được tự quyết định quyền vượt policy AS.

### 14.1. Grant allowlist

Ví dụ nền tảng chỉ cho Authorization Code và Refresh Token:

```text
Allowed:
authorization_code
refresh_token

Denied unless explicitly approved:
implicit
password
client_credentials
device_code
custom_grant
```

Đây là policy ví dụ, không phải danh sách grant bắt buộc của OIDC. Registrar phải kiểm tra từng grant type và business use case trước khi lưu.

### 14.2. Scope allowlist

- Client chỉ được yêu cầu scope nằm trong catalog được phép.
- Scope có quyền cao cần approval riêng.
- Không tự động cấp tất cả scopes được client gửi.
- Scope trong metadata không thay thế consent/authorization khi user cấp quyền.
- Client không thể tự thêm scope bằng cách sửa request Token Endpoint sau registration.

### 14.3. Token Endpoint authentication method

| Method | Phù hợp | Lưu ý |
| --- | --- | --- |
| `client_secret_basic` | Confidential web/backend client | Secret phải được bảo vệ |
| `client_secret_post` | Tương thích legacy khi cần | Secret nằm trong form body; tránh nếu không cần |
| `private_key_jwt` | Workload/backend có private key | AS cần public JWKS đã xác minh |
| `tls_client_auth` | Workload có mTLS identity | Quản lý certificate lifecycle |
| `none` | Public client | Không có client secret; yêu cầu PKCE cho Authorization Code |

Không chấp nhận auth method chỉ vì tên nằm trong request. Phải kiểm tra method đó được AS hỗ trợ và client type được phép dùng.

### 14.4. PKCE

Với public client, yêu cầu PKCE, ưu tiên `S256`. Không cho client tự bỏ PKCE chỉ bằng cách đăng ký metadata khác nếu policy của AS yêu cầu proof key.

Với SAS, có thể cấu hình `ClientSettings.requireProofKey` cho registration được tạo. Cần đảm bảo converter/policy ánh xạ metadata và defaults đúng với client type.

## 15. Bảo vệ remote metadata và chống SSRF

Một số metadata có URL để AS hoặc admin console truy cập, ví dụ `jwks_uri`, `sector_identifier_uri`, `logo_uri`, `client_uri`, `policy_uri` và `tos_uri`.

Không phải URL nào cũng cần server fetch. Nhưng nếu backend, validator, image proxy hoặc admin UI truy xuất URL do client cung cấp, phải xử lý SSRF và nội dung độc hại.

### 15.1. Kiểm soát URL

- Yêu cầu HTTPS cho metadata key/sector URI theo chuẩn tương ứng.
- Chặn loopback, private IP, link-local và cloud metadata addresses khi backend fetch.
- Kiểm tra DNS resolution và DNS rebinding.
- Giới hạn redirects; không follow sang host không được phép.
- Đặt connect/read timeout và response size cap.
- Validate content type/schema.
- Không chấp nhận file scheme hoặc protocol không cần thiết.
- Không tin logo image hoặc client name như bằng chứng danh tính.

### 15.2. JWK Set

- Chỉ nhận public keys.
- Kiểm tra `kty`, `use`, `key_ops`, `alg`, key size và thuật toán được allowlist.
- Không cho key URL nội bộ.
- Cache có TTL và hỗ trợ rotation.
- Xác minh key thuộc client registration đã được duyệt.
- Không dùng JWK set của client để xác minh token do AS ký.

### 15.3. Metadata display

Client name, logo, website và policy URI có thể được hiển thị trên consent page. Attacker có thể dùng tên/biểu tượng giả để mạo danh ứng dụng khác. Nên hiển thị publisher/organization đã xác minh, gắn registration với developer account/tenant, phân biệt tên tự khai và tên đã được attest, kiểm soát domain ownership, không render HTML từ metadata và dùng safe image proxy hoặc allowlist khi tải logo.

## 16. Persistence, cập nhật và deprovisioning

### 16.1. Shared storage cho nhiều AS instances

Trong cluster, mọi node phải nhìn thấy cùng registration state. Nếu mỗi node dùng in-memory repository riêng:

- Client tạo ở node A có thể không tồn tại ở node B.
- Token Endpoint có thể trả `invalid_client` tùy node.
- Client Read có thể đọc metadata khác nhau.
- Revocation/disable policy không nhất quán.

Production cần shared durable store, backup, migration schema, index theo client ID và transaction phù hợp.

### 16.2. Cập nhật registration

Nếu triển khai RFC 7592 update hoặc admin update riêng:

- Xác thực đúng Registration Access Token hoặc admin identity.
- Chỉ cho phép thay metadata nằm trong policy.
- Không thay client ID.
- Kiểm tra redirect URI mới trước khi commit.
- Có optimistic locking/versioning để tránh lost update.
- Audit metadata trước/sau theo cách không ghi secret.
- Xem xét revoke authorization/token cũ khi security-sensitive fields thay đổi.

### 16.3. Xóa hoặc disable client

Deprovisioning không chỉ xóa một row. Quy trình cần cân nhắc:

1. Đánh dấu client disabled hoặc ngừng cấp grant mới.
2. Revoke các authorization/refresh tokens liên quan theo policy.
3. Làm cho access token hiện tại bị từ chối theo mô hình validation.
4. Thu hồi Registration Access Token và client secret.
5. Xóa hoặc archive metadata theo retention policy.
6. Ghi audit ai yêu cầu và lý do.
7. Đảm bảo mọi AS replica và Resource Server cache nhận thay đổi.

Nếu Resource Server xác minh JWT offline, disable client ở AS không tự làm mọi JWT đã phát mất hiệu lực ngay. Cần introspection, denylist, event invalidation hoặc access token TTL phù hợp.

### 16.4. Client secret rotation

Khi secret bị lộ hoặc hết hạn:

- Xác minh quyền người yêu cầu rotation.
- Phát secret mới theo quy trình an toàn.
- Cho phép overlap có giới hạn nếu cần zero-downtime.
- Thu hồi secret cũ sau thời gian chuyển đổi.
- Cập nhật client secret storage.
- Không đưa secret mới vào logs hoặc ticket.
- Kiểm tra client auth failures sau rotation.

Không dùng Client Read như một thao tác rotation. OIDC Client Read là thao tác đọc; update/rotation phải theo cơ chế được server hỗ trợ và được bảo vệ riêng.

## 17. Ví dụ end-to-end với curl

### 17.1. Lấy Initial Access Token

Ví dụ registrar đã được đăng ký trước:

```bash
curl -i -X POST "https://auth.example.com/oauth2/token" \
  -u "platform-registrar:REDACTED_REGISTRAR_SECRET" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=client.create"
```

Dùng access token trả về làm Initial Access Token. Theo hướng dẫn SAS, token chỉ có scope `client.create`.

### 17.2. Đăng ký client

```bash
curl -i -X POST "https://auth.example.com/connect/register" \
  -H "Authorization: Bearer REDACTED_INITIAL_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{
    "application_type": "web",
    "redirect_uris": [
      "https://portal.example.com/login/oauth2/code/partner"
    ],
    "response_types": ["code"],
    "grant_types": ["authorization_code", "refresh_token"],
    "client_name": "Partner Portal",
    "token_endpoint_auth_method": "private_key_jwt",
    "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
    "scope": "openid profile email"
  }'
```

Không lưu raw Initial Access Token trong shell history, CI output hoặc process logs. Trong automation, lấy credential từ secret manager và redaction request headers.

### 17.3. Đọc registration

Dùng chính xác `registration_client_uri` trong response:

```bash
curl -i \
  -H "Authorization: Bearer REDACTED_REGISTRATION_ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://auth.example.com/connect/register?client_id=portal-tenant-42"
```

URL trên chỉ minh họa. Client phải sử dụng URI thực tế mà AS trả về, không tự tạo query parameter theo ví dụ.

## 18. Kiểm thử DCR trong Spring Boot

### 18.1. Unit tests cho metadata policy

Kiểm thử redirect URI đúng allowlist, redirect URI sai host/path/scheme, grant type ngoài allowlist, scope vượt quyền, public client khai báo secret authentication method, confidential client thiếu credential strategy, JWKS URI không HTTPS hoặc trỏ private address, JWK Set chứa private/symmetric key, software statement sai chữ ký/issuer/audience/expiry, custom metadata ngoài allowlist và domain/tenant mismatch.

### 18.2. Integration test registration

Ví dụ MockMvc kiểm tra registration thành công:

```java
@Test
void registerClientWithInitialAccessToken() throws Exception {
    mockMvc.perform(post("/connect/register")
            .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + initialAccessToken)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "application_type": "web",
                  "redirect_uris": [
                    "https://portal.example.com/callback"
                  ],
                  "response_types": ["code"],
                  "grant_types": ["authorization_code"],
                  "client_name": "Portal",
                  "token_endpoint_auth_method": "private_key_jwt",
                  "jwks_uri": "https://portal.example.com/jwks.json",
                  "scope": "openid profile"
                }
                """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.client_id").isNotEmpty())
        .andExpect(jsonPath("$.registration_access_token").isNotEmpty())
        .andExpect(jsonPath("$.registration_client_uri").isNotEmpty())
        .andExpect(jsonPath("$.redirect_uris[0]")
                .value("https://portal.example.com/callback"));
}
```

Đây là skeleton. Test context cần SAS security chain, `JwtDecoder`, JWK source, registrar client, token store và persistent `RegisteredClientRepository`. Response fields phụ thuộc cấu hình và loại client.

### 18.3. Test Initial Access Token

| Test | Kỳ vọng |
| --- | --- |
| Không gửi Bearer token | Từ chối theo bearer authentication |
| Token hết hạn | Từ chối |
| Token không có `client.create` | Từ chối registration |
| Token có thêm scope ngoài `client.create` theo SAS guide | Registration bị từ chối |
| Dùng Initial Access Token lần thứ hai | Bị từ chối theo hành vi one-time của SAS guide |
| Registrar không được phép tạo client | Từ chối theo authorization policy |

### 18.4. Test Client Read

| Test | Kỳ vọng |
| --- | --- |
| Registration Access Token hợp lệ + URI đúng | HTTP 200 và metadata registration |
| Token hết hạn/không hợp lệ | Bearer error |
| Token của client A truy cập registration B | Không đọc được registration B |
| Thiếu scope `client.read` | Từ chối |
| Client Read response | Không làm thay đổi registration |
| Registration URI bị thay query/path | Không dùng URL tự dựng; dùng URI server trả về |

### 18.5. Test bảo mật và vận hành

- Nhiều request đăng ký đồng thời không tạo client ID trùng.
- AS restart vẫn đọc được registration.
- Node A tạo client, node B nhận diện client.
- Database lỗi không trả response thành công giả.
- Rate limit hoạt động theo registrar/tenant.
- Raw token/secret không xuất hiện trong logs.
- Domain/tenant isolation được giữ.
- Deprovisioning vô hiệu client theo policy.
- Key rotation không làm mất khả năng xác minh registrar token.
- Metadata discovery công bố đúng registration endpoint.

## 19. Observability và quản trị vòng đời

### 19.1. Metrics

Nên theo dõi số registration thành công/thất bại, lỗi theo loại, registration rate theo registrar/tenant, số client active/disabled, thời gian xử lý registration/read, tỷ lệ client không hoạt động, số lần token bị dùng sai, client secret expiry/rotation failures và client authentication failures sau provisioning.

Không dùng raw access token, client secret hoặc registration access token làm metric label.

### 19.2. Audit

Audit record có thể lưu registrar identity đã xác thực, tenant/organization, client ID được cấp, metadata names đã thay đổi và policy decision, redirect domains đã được phê duyệt, thời điểm/correlation ID/approval reference và software publisher/statement identity nếu có.

Không ghi raw secret/token. Hạn chế ai được xem contact metadata và thông tin nhận diện developer.

### 19.3. Cleanup và inventory

- Owner và business purpose cho từng registration.
- Environment/tenant tag.
- Expiration hoặc review date.
- Quy trình disable client không còn dùng.
- Báo cáo redirect domains và auth methods.
- Kiểm tra registration trùng lặp.
- Retention/archival cho audit và client metadata.
- Quy trình khôi phục nếu client mất registration access token.

DCR có thể tạo nhiều client ngắn hạn. Nếu không có inventory và cleanup, registry sẽ tích tụ client mồ côi mà tổ chức không biết ai còn sở hữu.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `/connect/register` trả 404 | Endpoint OIDC Client Registration chưa bật hoặc path sai | Kiểm tra `clientRegistrationEndpoint` và `AuthorizationServerSettings` |
| Trả 401/invalid_token | Thiếu Initial Access Token, token sai/hết hạn hoặc decoder không xác minh được | Kiểm tra Bearer token, issuer/JWKS và `JwtDecoder` |
| Trả 403/scope error | Token thiếu `client.create` hoặc có scope không đúng contract | Lấy token với scope yêu cầu |
| `client.create` và `client.read` bị lẫn | Registrar token mang scope sai | Tách token registration và registration access token |
| `invalid_redirect_uri` | URI không hợp lệ hoặc không đúng policy | Kiểm tra scheme/host/path, application type |
| `invalid_client_metadata` | Grant, auth method, JWKS hoặc metadata không hợp lệ | Kiểm tra validator và allowlist |
| Client tạo được nhưng Token Endpoint trả invalid_client | Registration không được persist hoặc auth method/secret mapping sai | Kiểm tra repository và converter |
| Client Read trả 401 | Registration Access Token sai/hết hạn hoặc URL không đúng | Dùng token và URI từ response |
| Client Read trả dữ liệu không cập nhật | Converter không round-trip custom metadata | Kiểm tra converter hai chiều |
| Custom metadata bị mất | Chỉ sửa registration converter, không sửa read converter | Cập nhật provider và configuration provider |
| SAS endpoint không chạy | Thiếu `JwtDecoder` | Đăng ký decoder từ JWKSource |
| Client ID trùng khi nhiều node | ID generation/repository uniqueness sai | UUID/random ID và DB unique constraint |
| Một node không thấy client mới | In-memory/local repository | Dùng shared persistent repository |
| Secret xuất hiện trong log | Request/response body logging | Redaction và tắt body logging cho endpoint |
| Registration bị spam | Open registration hoặc token cấp quá rộng | Protected registration, quota và rate limit |
| Metadata logo giả mạo app khác | Tin client_name/logo_uri tự khai | Publisher attestation và verified organization |
| Backend fetch URL nội bộ | Không có SSRF controls | Egress allowlist, DNS/IP validation, redirect restrictions |
| Disable client nhưng JWT vẫn dùng được | Resource Server xác minh JWT offline | Introspection, denylist hoặc token TTL phù hợp |

## 21. Anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách làm phù hợp |
| --- | --- | --- |
| Bật open DCR không có rate limit | Spam và registry pollution | Protected registration hoặc quota |
| Cấp Initial Access Token dùng chung, không hết hạn | Compromise một token có thể tạo nhiều client | Token ngắn hạn, giới hạn tenant, single-use khi phù hợp |
| Tin redirect URI do client gửi | Authorization code theft | Exact validation và domain ownership |
| Cho phép mọi grant/scope | Client có quyền vượt use case | Allowlist và least privilege |
| Dùng client secret cho public app | Secret bị trích xuất từ binary | Public client + PKCE |
| Coi client_name/logo_uri là identity proof | Phishing/brand impersonation | Publisher verification/software statement |
| Tin software_statement chỉ vì decode JWT được | Attacker tự tạo attestation giả | Verify signature và trust chain |
| Lưu raw Registration Access Token trong logs | Chiếm quyền đọc registration | Secret handling và redaction |
| Dựng registration_client_uri bằng client_id | Sai route hoặc bypass contract | Dùng URI chính xác từ response |
| Chỉ custom registration converter | Client Read mất metadata | Custom cả chiều RegisteredClient → response |
| Cho client tự khai tenant_id để cấp quyền | Cross-tenant privilege escalation | Resolve tenant từ provisioning authority |
| Coi OIDC Client Read là RFC 7592 đầy đủ | Gọi PUT/DELETE không được hỗ trợ | Kiểm tra endpoint implementation/version |
| Xóa client record nhưng giữ token state không kiểm soát | Token cũ có thể còn hoạt động | Deprovisioning phối hợp authorization/revocation |
| Coi registration thành công là client đã được trust | Client metadata chưa được attested | Approval, policy và runtime authorization |

## 22. Checklist nghiệm thu production

- [ ] Đã xác định use case cần DCR và phạm vi registrar được phép.
- [ ] Phân biệt RFC 7591, OIDC Registration 1.0 và RFC 7592.
- [ ] OIDC Client Registration Endpoint chỉ bật khi có nhu cầu.
- [ ] Discovery công bố đúng `registration_endpoint`.
- [ ] Có registrar client và scope `client.create` giới hạn.
- [ ] Initial Access Token được bảo vệ, hết hạn và có quota/single-use policy.
- [ ] Theo SAS guide, token registration chỉ có `client.create`.
- [ ] Có `JwtDecoder` bean và JWK source phù hợp.
- [ ] `RegisteredClientRepository` dùng persistence chia sẻ trong production.
- [ ] Client ID duy nhất và không phụ thuộc display name/email.
- [ ] Redirect URI exact validation; không wildcard tùy tiện.
- [ ] Grant types, response types, scopes và auth methods nằm trong allowlist.
- [ ] Public/native clients dùng PKCE và không nhận secret không cần thiết.
- [ ] JWKS/sector URI được kiểm tra HTTPS, schema và SSRF policy.
- [ ] Software statement được xác minh chữ ký/issuer/audience/expiry nếu dùng.
- [ ] Registration response có cache control phù hợp và secret không bị log.
- [ ] Registration Access Token được lưu như bearer secret.
- [ ] Client dùng chính xác `registration_client_uri` được trả về.
- [ ] Đã kiểm thử Client Read và giới hạn của SAS version.
- [ ] Custom metadata có converter hai chiều và allowlist.
- [ ] Có quy trình disable/delete/rotation và revoke token liên quan.
- [ ] Có tenant isolation, audit, rate limit, monitoring và cleanup.
- [ ] Có integration tests cho token, redirect, scope, metadata, persistence và nhiều instance.
- [ ] Có runbook khi registrar token hoặc client credential bị compromise.

## 23. Bản đồ ghi nhớ

```mermaid
flowchart TD
    DISC["OIDC Discovery"] --> ENDPOINT["registration_endpoint"]
    OWNER["Approved developer / provisioning"] --> REGISTRAR["Registrar Client"]
    REGISTRAR --> TOKEN["Initial Access Token<br/>scope client.create"]
    TOKEN --> POST["POST Client Registration + JSON metadata"]
    POST --> VALIDATE["Validate bearer token + client metadata"]
    VALIDATE --> STORE["RegisteredClientRepository"]
    STORE --> RESPONSE["201 Created<br/>client_id + client credentials"]
    RESPONSE --> ACCESS["registration_access_token"]
    RESPONSE --> URI["registration_client_uri"]
    ACCESS --> READ["GET Client Read"]
    URI --> READ
    READ --> META["Current registration metadata"]
    STORE --> AUTH["Normal OAuth/OIDC client flows"]
```

**Dynamic Client Registration là quy trình tạo client có kiểm soát bằng metadata và giao thức chuẩn.** RFC 7591 định nghĩa OAuth2 registration; OIDC Registration 1.0 bổ sung contract cho relying parties và thao tác Client Read; RFC 7592 mở rộng các thao tác quản lý registration. Trong Spring Authorization Server, OIDC Client Registration Endpoint có sẵn nhưng mặc định tắt, yêu cầu Bearer access token với scope phù hợp và cần `JwtDecoder`. Registrar, Initial Access Token, Registration Access Token, metadata validation và persistence phải được thiết kế thành một vòng đời bảo mật. Khi giữ redirect URI chính xác, cấp quyền tối thiểu, xác minh metadata và quản trị deprovisioning, DCR có thể tự động hóa onboarding mà vẫn duy trì ranh giới tin cậy của OAuth 2.0/OpenID Connect.

## 24. Tài liệu tham khảo

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592)
- [OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-registration-1_0.html)
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
