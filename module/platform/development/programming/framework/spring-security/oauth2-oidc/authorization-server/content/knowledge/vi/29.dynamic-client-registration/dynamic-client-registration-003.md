# Bảo vệ đăng ký bằng initial access token và quyền đăng ký client

## 1. Bài toán: ai được phép tạo OAuth client mới?

Một nền tảng có nhiều nhóm sản phẩm cần tích hợp với Authorization Server. Nếu bất kỳ ai cũng có thể gửi JSON tới Client Registration Endpoint và tạo client, kẻ tấn công có thể tự đăng ký ứng dụng, khai báo redirect URI do mình kiểm soát, xin grant/scope rộng hoặc tạo nhiều client để lạm dụng hệ thống.

**Dynamic Client Registration (DCR)** cho phép phần mềm hoặc tổ chức đăng ký OAuth/OIDC client qua một protocol endpoint. Nhưng đăng ký động không đồng nghĩa đăng ký công khai. Với mô hình protected registration, Authorization Server chỉ nhận yêu cầu từ bên đã được cấp quyền đăng ký, thông qua **initial access token** hoặc cơ chế bảo vệ tương đương.

Bài này tập trung vào ba credential/quyền cần phân biệt:

1. **Initial access token**: token ban đầu, do registrar đã được phê duyệt sử dụng để tạo client mới.
2. **Scope client.create**: quyền cho phép registrar gọi thao tác đăng ký trong Spring Authorization Server.
3. **Registration access token**: token riêng được trả về sau khi đăng ký thành công, dùng để đọc cấu hình client qua Client Read khi được cấp quyền tương ứng.

Trong Spring Authorization Server (SAS) 1.5.8, OIDC Client Registration Endpoint **bị tắt mặc định**. Khi bật, endpoint được bảo vệ như OAuth Resource Server, yêu cầu Bearer access token; request đăng ký cần scope client.create, còn Client Read cần scope client.read. Initial token dùng cho request đăng ký phải có duy nhất scope client.create; token này chỉ dùng một lần và bị vô hiệu hóa sau khi client được đăng ký thành công.

Bài thuộc chương **Đăng ký client động** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Mục tiêu tổng thể của module là **học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt open registration và protected registration theo RFC 7591.
- Giải thích vai trò và vòng đời của initial access token.
- Cấu hình registrar riêng trong RegisteredClientRepository.
- Phát hành initial access token có đúng scope client.create và chỉ dùng cho đăng ký.
- Bật OIDC Client Registration Endpoint trong Spring Authorization Server 1.5.8.
- Phân biệt client.create, client.read, registration_access_token và token của client mới.
- Kiểm soát grant, redirect URI, scope, client authentication method và metadata trong registration request.
- Thiết kế quy trình cấp, lưu, thu hồi và audit registrar credential.
- Viết integration tests cho đăng ký hợp lệ, token thiếu/sai scope, token dùng lại và Client Read.

> **Phạm vi phiên bản:** Các ví dụ Spring sử dụng API Spring Authorization Server 1.5.8 và Spring Security 6.x. RFC 7591 mô tả protocol tổng quát; các scope client.create/client.read, quy tắc initial token một lần và cách bật endpoint dưới đây là hành vi cụ thể được tài liệu SAS 1.5.8 hướng dẫn. SPECIAL_NOTE của bài được giao để trống.

## 2. DCR và protected registration theo RFC 7591

RFC 7591 định nghĩa Client Registration Endpoint nhận HTTP POST với metadata client ở dạng JSON. Endpoint **phải được bảo vệ bằng transport-layer security**. Authorization Server có thể bảo vệ endpoint như OAuth protected resource và yêu cầu initial access token để giới hạn tổ chức hoặc developer nào được đăng ký client.

Hai mô hình thường gặp:

| Mô hình | Ai có thể đăng ký? | Bảo vệ |
| --- | --- | --- |
| Open registration | Bất kỳ phần mềm nào truy cập được endpoint, theo policy server | TLS, validation, abuse protection, quota và kiểm soát metadata |
| Protected registration | Chỉ developer/registrar đã được phê duyệt | TLS + initial access token hoặc cơ chế authorization tương đương |

Với hệ thống doanh nghiệp, partner platform hoặc authorization service dùng chung, protected registration thường phù hợp hơn vì tổ chức cần biết ai đang tạo client và vì sao.

### 2.1. Initial access token là gì?

RFC 7591 định nghĩa initial access token là OAuth access token được Authorization Server cấp cho developer/client để ủy quyền gọi Client Registration Endpoint. Token này không có một định dạng hay cách phát hành duy nhất do RFC quy định; cách cấp và xác minh nằm ngoài phạm vi protocol chung.

Một quy trình thường dùng:

1. Developer hoặc team gửi yêu cầu onboarding.
2. Operator xác minh tổ chức, owner, môi trường và mục đích tích hợp.
3. Authorization Server cấp initial access token cho registrar đã được phê duyệt.
4. Registrar gọi Client Registration Endpoint bằng Bearer token.
5. Server kiểm tra token, scope, policy và metadata request.
6. Nếu hợp lệ, server tạo registration và trả thông tin client.

Initial access token thể hiện **quyền đăng ký**, không nhất thiết là credential của client mới. Nó cũng không chứng minh mọi metadata do người đăng ký khai báo đều đúng. Server vẫn phải validate request và có thể yêu cầu software statement hoặc approval.

### 2.2. Initial access token khác registration access token

| Thuộc tính | Initial access token | Registration access token |
| --- | --- | --- |
| Được cấp khi nào? | Trước khi tạo client | Sau khi client registration thành công |
| Ai sử dụng? | Registrar/developer đã được phê duyệt | Chủ thể được cấp quyền quản lý/đọc registration tương ứng |
| Mục đích | Authorize tạo client mới | Truy cập Client Read hoặc thao tác registration được hỗ trợ |
| Phạm vi | Có thể giới hạn vào một lần đăng ký | Gắn với registration cụ thể |
| Trong SAS 1.5.8 | Initial token phải có đúng scope client.create, dùng một lần | Response registration có registration_access_token; Client Read dùng Bearer token có quyền client.read |

Không lưu initial access token rồi dùng nó như API key lâu dài. Không lấy registration access token của một client để đọc registration của client khác.

## 3. Ba lớp quyền trong quy trình đăng ký

Một quy trình DCR an toàn có thể phân tách:

1. **Quyền onboarding của tổ chức:** ai được yêu cầu tạo client, ai phê duyệt và registrar nào được cấp initial token.
2. **Quyền protocol của registrar:** access token có scope client.create để gọi Registration Endpoint.
3. **Quyền sử dụng của client mới:** grant types, scopes, redirect URIs, client authentication methods và token policy được ghi vào registration.

Ba lớp này không thay thế lẫn nhau. Một registrar có client.create không có nghĩa client mới được dùng mọi grant; request registration vẫn bị validation và policy giới hạn.

```mermaid
flowchart TD
    A[Developer / Product Team] --> B[Onboarding & Approval]
    B --> C[Registrar được phê duyệt]
    C --> D[Initial Access Token: client.create]
    D --> E[POST Client Registration Endpoint]
    E --> F{Token + metadata hợp lệ?}
    F -->|No| G[Reject request]
    F -->|Yes| H[Persist RegisteredClient]
    H --> I[Return client_id + registration credentials]
    I --> J[Client sử dụng grant/scope đã đăng ký]
    I --> K[Client Read với registration_access_token]
```

Authorization Server phải xác minh registrar trước khi xử lý metadata. Sau đó server phải xác minh metadata độc lập, ví dụ redirect URI chính xác, grant có hỗ trợ, scope được phép và authentication method phù hợp.

## 4. Bật OIDC Client Registration Endpoint trong Spring Authorization Server

Trong SAS 1.5.8, Dynamic Client Registration là một phần của OIDC Client Registration. Endpoint **disabled mặc định** vì nhiều hệ thống không cần onboarding client động.

Để bật endpoint:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(oidc ->
                oidc.clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
```

Đây là phần cấu hình endpoint. Ứng dụng còn cần RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, key/token services và các bean OAuth/OIDC liên quan.

### 4.1. JwtDecoder là dependency bắt buộc

Client Registration Endpoint của SAS 1.5.8 là OAuth protected resource, nhận access token dạng Bearer. Tài liệu SAS yêu cầu một bean JwtDecoder cho endpoint này.

Ví dụ:

```java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

Ví dụ trên giả định ứng dụng đã có JWKSource<SecurityContext> phù hợp. JwtDecoder xác minh access token JWT được gửi tới Registration Endpoint; nó không thay thế logic kiểm tra scope client.create hoặc policy registrar.

### 4.2. Endpoint xử lý cả registration và Client Read

OidcClientRegistrationEndpointFilter xử lý hai loại request:

- Client Registration: tạo registration mới.
- Client Read: truy xuất cấu hình client đã đăng ký.

Các thành phần mặc định bao gồm:

| Thành phần | Vai trò |
| --- | --- |
| OidcClientRegistrationAuthenticationConverter | Chuyển HTTP request thành authentication request |
| OidcClientRegistrationAuthenticationProvider | Xử lý tạo client registration |
| OidcClientConfigurationAuthenticationProvider | Xử lý Client Read |
| Success handler | Serialize OIDC Client Registration response |
| Failure handler | Trả OAuth error response |

Giữ converter/provider mặc định nếu chỉ cần bảo vệ endpoint bằng scope. Chỉ custom khi có yêu cầu metadata hoặc validation cụ thể.

## 5. Cấu hình registrar trong RegisteredClientRepository

Registrar là một OAuth client đã được tạo trước và được cấp quyền đăng ký client mới. Một cấu hình minh họa:

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {

    RegisteredClient registrar = RegisteredClient.withId(
                    UUID.randomUUID().toString())
            .clientId("platform-registrar")
            .clientSecret(passwordEncoder.encode("replace-with-managed-secret"))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("client.create")
            .scope("client.read")
            .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
```

Đây là ví dụ học tập. Production cần lưu registrar trong repository bền vững, mã hóa secret bằng PasswordEncoder, lấy secret từ secret manager và có quy trình rotate. Không dùng secret literal trong source code.

### 5.1. Vì sao registrar dùng Client Credentials?

Registrar là workload hoặc service thực hiện onboarding; nó không cần End-User đăng nhập để thực hiện nhiệm vụ này. Client Credentials phù hợp cho machine-to-machine khi registrar được tin cậy và quản lý như service account.

Có thể dùng phương thức client authentication khác nếu policy cho phép, ví dụ private_key_jwt hoặc mTLS. Điều quan trọng là xác thực registrar đúng trước khi phát initial access token.

### 5.2. Scope của registrar không phải scope của client mới

client.create và client.read là quyền của registrar đối với Client Registration Endpoint. Chúng không phải scope nghiệp vụ của ứng dụng được tạo.

| Chủ thể | Scope | Mục đích |
| --- | --- | --- |
| Registrar | client.create | Tạo registration |
| Registrar | client.read | Đọc registration khi được cấp |
| Client mới orders-web | openid, orders.read | Quyền mà ứng dụng yêu cầu khi chạy |
| Client mới billing-worker | billing.write | Quyền nghiệp vụ của workload nếu được duyệt |

Không thêm client.create vào mọi client mới. Client thông thường không được phép tự tạo thêm client khác.

## 6. Lấy initial access token với đúng scope

Theo hướng dẫn SAS 1.5.8, access token dùng cho Client Registration request phải có **một scope duy nhất là client.create**. Nếu token chứa scope bổ sung, Registration Endpoint sẽ từ chối request.

Ví dụ Token Endpoint request:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

Response minh họa:

```json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 120,
  "scope": "client.create"
}
```

Giá trị expires_in ở trên chỉ minh họa. Chọn thời hạn ngắn theo rủi ro và quy trình onboarding; không sao chép con số nếu chưa có policy.

### 6.1. Không xin scope nghiệp vụ cùng initial token

Request sau không hợp lệ theo quy tắc SAS 1.5.8 cho initial registration token:

```http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create%20orders.read
```

Token có client.create orders.read sẽ bị Registration Endpoint từ chối. Registrar nên lấy một token riêng cho tác vụ tạo client, với đúng scope cần thiết.

### 6.2. Initial token phải được bảo vệ như credential có quyền cao

Initial token cho phép tạo OAuth client. Nếu bị lộ, kẻ tấn công có thể tạo registration với redirect URI hoặc metadata do họ kiểm soát, trong giới hạn validation của server.

Do đó:

- Chỉ truyền qua HTTPS.
- Không đưa vào URL, query string, source code hoặc log.
- Không chia sẻ qua ticket/chat không được bảo vệ.
- Giữ token trong memory/secret store trong thời gian ngắn.
- Giới hạn registrar và phạm vi tổ chức/môi trường.
- Ưu tiên token ngắn hạn và one-time use.

## 7. Đăng ký client bằng initial access token

Client Registration request là HTTP POST với JSON body. Initial access token được gửi trong Authorization Bearer header.

```http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "orders-web",
  "application_type": "web",
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/company"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile orders.read",
  "token_endpoint_auth_method": "client_secret_basic"
}
```

/connect/register là path thường dùng trong ví dụ SAS; hãy kiểm tra endpoint path đã cấu hình trong deployment của mình. JSON trên chỉ là ví dụ request, không có nghĩa mọi metadata field đều được chấp nhận ở mọi policy.

### 7.1. Metadata request là dữ liệu đầu vào chưa đáng tin

Registrar đã được xác thực chỉ chứng minh **ai gửi request**. Các giá trị như client_name, redirect_uris, grant_types, scope, logo_uri, jwks_uri vẫn phải được validate.

Server nên kiểm tra:

- Grant types nằm trong allowlist của hệ thống.
- Response types phù hợp grant và OIDC flow.
- Redirect URI chính xác, HTTPS trong production và không dùng wildcard nguy hiểm.
- Post-logout redirect URI được kiểm tra riêng.
- Token endpoint authentication method phù hợp loại client.
- Scope thuộc tập được phép và được duyệt cho ứng dụng.
- JWKS URI/sector identifier/logo URL không dẫn tới SSRF hoặc nội dung độc hại.
- Không chấp nhận metadata không được hỗ trợ hoặc có kiểu dữ liệu sai.

### 7.2. Client response sau khi đăng ký

Response minh họa:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "client_id": "generated-client-id",
  "client_secret": "GENERATED_CLIENT_SECRET",
  "client_name": "orders-web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/company"
  ],
  "scope": "openid profile orders.read",
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://login.example.com/connect/register/generated-client-id"
}
```

Đây là response minh họa. Server có thể trả các metadata field khác tùy implementation. Secret chỉ được hiển thị theo response contract tại thời điểm cấp; client phải lưu an toàn ngay khi nhận.

### 7.3. Initial access token chỉ sử dụng một lần trong SAS

Theo hướng dẫn SAS 1.5.8, initial access token **chỉ có thể dùng một lần**. Sau khi client được đăng ký thành công, token bị invalidated. Nếu cùng token được gửi lại, request phải thất bại.

One-time use làm giảm khả năng replay token bị đánh cắp. Tuy vậy, cần kiểm thử hành vi khi request bị timeout sau khi server đã persist client nhưng client không nhận được response. Không tự retry cùng token và tạo thêm registration; trước tiên phải có quy trình reconciliation/audit để xác định kết quả lần gọi đầu.

## 8. Client Read và registration_access_token

Sau registration, response có thể cung cấp:

- registration_access_token: Bearer token để truy cập registration.
- registration_client_uri: URI dùng cho Client Read.

Client Read dùng registration access token có scope client.read theo policy SAS 1.5.8. Ví dụ:

```http
GET /connect/register/generated-client-id HTTP/1.1
Host: login.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
```

Response Client Read trả metadata client tương ứng; không trả lại registration_access_token như một phần của response đọc. Bảo vệ registration access token tương tự credential quản trị vì nó cho phép truy cập dữ liệu registration.

### 8.1. Không dùng nhầm token

| Token | Dùng ở đâu? | Quyền |
| --- | --- | --- |
| Registrar client secret/private key | Token Endpoint | Xác thực registrar |
| Initial access token | Client Registration POST | Tạo client; SAS yêu cầu client.create duy nhất và one-time |
| Registration access token | Client Read | Đọc registration tương ứng với client.read |
| Client secret/private key mới | Token Endpoint của client mới | Xác thực client mới theo registration |
| Access token nghiệp vụ của client mới | Resource Server/API | Gọi API theo scope/audience đã cấp |

Không dùng registration_access_token để gọi API nghiệp vụ. Không dùng access token của client mới để đọc registration nếu nó không có đúng quyền và ràng buộc tương ứng.

### 8.2. Client Read không phải quyền đọc mọi client

Registration access token được gắn với registration cụ thể. Một token của orders-web không được dùng để đọc cấu hình billing-worker. Server phải kiểm tra token, registration identifier và quyền truy cập; không dựa vào client ID do caller tự khai.

### 8.3. Phạm vi quản lý của SAS cần được xác minh

OIDC Dynamic Client Registration specification có các thao tác registration management rộng hơn chỉ đọc. Tuy nhiên, trong tài liệu SAS 1.5.8, endpoint được mô tả rõ cho **Client Registration và Client Read**. Không mặc định suy ra PUT update hoặc DELETE registration được hỗ trợ chỉ vì chuẩn OIDC có định nghĩa; kiểm tra API/version thực tế trước khi thiết kế lifecycle.

## 9. Cấu hình registrar và token policy trong Spring

Registrar thường là confidential client dùng Client Credentials. Token cấp cho tác vụ tạo client nên có scope duy nhất client.create.

Ví dụ minh họa token settings:

```java
RegisteredClient registrar = RegisteredClient.withId(
                UUID.randomUUID().toString())
        .clientId("platform-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(2))
                .build())
        .build();
```

Thời hạn hai phút là ví dụ minh họa, không phải giá trị bắt buộc. Nếu cần token client.read, cấp riêng theo quy trình phù hợp. Khi xin initial token để đăng ký, request scope vẫn chỉ là client.create.

### 9.1. Cấp initial token

Quy trình có thể dùng Client Credentials:

```text
grant_type=client_credentials
scope=client.create
```

Đừng cấp scope client.create cho service chỉ cần Client Read. Tách registrar role theo trách nhiệm:

- Registration service: client.create.
- Registration inspection service: client.read.
- Admin workflow: quyền phê duyệt và vận hành ở lớp quản trị riêng.

### 9.2. Initial token một lần và lưu trạng thái

Để đảm bảo one-time use trong môi trường nhiều instance, trạng thái token/authorization phải được chia sẻ và cập nhật nguyên tử. Nếu mỗi node có authorization store riêng, cùng một token có thể bị chấp nhận đồng thời ở hai node trước khi trạng thái invalidated được đồng bộ.

SAS sử dụng OAuth2AuthorizationService để lưu authorization state. Production cần repository bền vững, giao dịch và cơ chế cập nhật trạng thái nhất quán. Kiểm thử concurrency để chứng minh một initial token không thể tạo hai client.

## 10. Phân quyền registrar theo môi trường và tổ chức

Một hệ thống có thể có nhiều registrar:

| Registrar | Môi trường/phạm vi | Quyền |
| --- | --- | --- |
| internal-dev-registrar | Development clients | client.create, có thể client.read trong dev |
| partner-onboarding | Partner sandbox | Chỉ tạo client cho partner đã duyệt |
| production-registrar | Production | Tạo client theo approval ticket và policy chặt |
| registration-auditor | Production read-only | client.read theo phạm vi được giao |

Không nhất thiết tất cả registrar phải chia sẻ cùng secret hoặc cùng quyền. Phân tách credential giúp thu hồi một registrar bị lộ mà không ảnh hưởng toàn bộ onboarding.

### 10.1. Gắn registrar với tenant/organization

Scope client.create cho biết registrar có quyền tạo registration theo protocol. Nếu hệ thống multi-tenant, cần thêm policy ở application layer để xác định registrar được tạo client cho tenant nào.

Không tin organization_id hoặc tenant_id do caller gửi trong JSON nếu chưa được đối chiếu với danh tính registrar và approval record. Có thể dùng server-side policy hoặc signed software statement để ràng buộc metadata.

### 10.2. Phân tách môi trường

Initial token cấp cho sandbox không nên dùng ở production. Tách issuer, registrar credentials, audience/resource và storage theo môi trường. Không copy production registration token vào local development hoặc CI logs.

## 11. Validation metadata và giới hạn quyền client mới

Initial access token chỉ mở quyền gọi endpoint. Nó **không miễn validation** cho registration payload.

### 11.1. Redirect URI

Redirect URI là ranh giới bảo mật quan trọng của Authorization Code Flow. Kiểm tra URI chính xác, scheme/host/path và policy của từng client. Tránh wildcard rộng, open redirect, URI trỏ localhost trong production hoặc domain không thuộc tổ chức.

Không chấp nhận redirect URI do registrar truyền chỉ vì registrar có client.create; registrar có thể bị lỗi hoặc bị xâm phạm.

### 11.2. Grant types và response types

Chỉ cho phép grant types server thực sự hỗ trợ và client cần. Không cấp Client Credentials cho browser app; không cấp Password Grant; không cho public client dùng client secret như thể secret có thể giữ kín.

Response types phải phù hợp Authorization Endpoint và grant. Ví dụ Authorization Code client thường dùng response_types là code, không quảng cáo implicit response nếu không được triển khai và cho phép.

### 11.3. Scope

Scope request là đề xuất của client, không phải quyền được tự cấp. Server cần allowlist theo product/API, tenant và approval. Scope nội bộ như client.create, admin.write không được tự động cấp cho client mới.

### 11.4. Token endpoint authentication method

Confidential client cần một phương thức xác thực được server hỗ trợ như client_secret_basic, private_key_jwt hoặc mTLS. Public client không có khả năng bảo vệ secret; dùng none cùng PKCE theo policy phù hợp.

### 11.5. Metadata URI và SSRF

Các trường như jwks_uri, logo_uri, sector_identifier_uri hoặc URL mở rộng có thể khiến server/client truy cập mạng. Nếu server fetch URL do registrar khai báo, cần kiểm soát SSRF: chặn loopback, link-local, private IP không được phép, redirect ngoài policy, DNS rebinding và scheme không an toàn.

Không fetch URL tùy ý từ registration request chỉ để xác minh metadata. Dùng egress policy, timeout, response size limit và allowlist domain khi cần.

## 12. Software Statement và initial access token

RFC 7591 cho phép request chứa software_statement, là JWT được issuer tin cậy ký để attestation một tập metadata client. Initial access token và software statement có vai trò khác nhau:

- Initial access token chứng minh caller được phép sử dụng Registration Endpoint.
- Software statement có thể chứng thực metadata như publisher, software ID, redirect URI hoặc grant policy.
- JSON metadata thông thường là dữ liệu self-asserted của client.

Nếu cùng một metadata field xuất hiện trong software statement và JSON body, quy tắc RFC yêu cầu giá trị từ software statement có độ ưu tiên theo protocol. Authorization Server vẫn phải đánh giá toàn bộ request và trust relationship.

SAS 1.5.8 có extension point cho custom metadata converter/provider, nhưng không nên giả định chỉ bật Client Registration Endpoint là đã có một trust framework/software statement policy hoàn chỉnh. Nếu tổ chức cần attestation, phải xây issuer trust, signature validation, audience/expiry/replay checks và mapping metadata riêng.

## 13. Tùy biến client metadata trong Spring Authorization Server

SAS có converter mặc định chuyển OIDC client registration metadata thành RegisteredClient và ngược lại. Nếu muốn hỗ trợ metadata riêng như logo_uri, contacts hoặc organization_id, cần tùy chỉnh converter/provider có kiểm soát.

Các extension point chính:

- clientRegistrationRequestConverter(...) và clientRegistrationRequestConverters(...).
- authenticationProvider(...) và authenticationProviders(...).
- clientRegistrationResponseHandler(...).
- errorResponseHandler(...).
- OidcClientRegistrationAuthenticationProvider.setRegisteredClientConverter(...).
- OidcClientRegistrationAuthenticationProvider.setClientRegistrationConverter(...).
- OidcClientConfigurationAuthenticationProvider.setClientRegistrationConverter(...).

Ví dụ định hướng:

```java
Consumer<List<AuthenticationProvider>> customizeRegistrationProviders =
        providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registration) {
                registration.setAuthenticationValidator(
                        OidcClientRegistrationAuthenticationValidator
                                .DEFAULT_REDIRECT_URI_VALIDATOR
                );
            }
        });
```

Đây là skeleton. Trong production, kết hợp các validator mặc định cần thiết như redirect URI, post-logout redirect URI, JWK Set URI và scope validator; không thay validator mặc định bằng một validator yếu hơn chỉ để chấp nhận request.

### 13.1. Chỉ lưu metadata được whitelist

Ví dụ, nếu chỉ hỗ trợ logo_uri và contacts, hãy:

1. Khai báo hai field là metadata được hỗ trợ.
2. Validate kiểu, độ dài và URL/contact format.
3. Lưu trong ClientSettings hoặc storage domain riêng.
4. Khi Client Read, serialize lại đúng hai field đó.
5. Bỏ qua hoặc từ chối metadata không được hỗ trợ theo policy.

Không lưu nguyên JSON tùy ý vào settings rồi trả lại cho caller khác. Điều đó có thể biến registration thành nơi lưu dữ liệu không kiểm soát hoặc làm rò metadata nội bộ.

### 13.2. Converter không phải nơi duy nhất để kiểm tra quyền

Converter chịu trách nhiệm chuyển đổi representation. Authentication provider/policy layer phải kiểm tra registrar token, registration scope, metadata validation và approval. Đừng nhét toàn bộ authorization logic vào converter rồi vô tình bỏ qua khi Client Read sử dụng converter khác.

## 14. Registration response và lưu credential an toàn

Sau khi tạo client, server có thể trả client_id, client_secret (nếu client dùng secret), registration_access_token và registration_client_uri.

Client onboarding system cần:

- Lưu client_secret trong secret manager; không hiển thị lại sau khi đã lưu nếu không cần.
- Lưu registration_access_token tách biệt với client secret.
- Giới hạn người/automation có thể đọc registration token.
- Ghi nhận owner, tenant, environment, approval ID và thời điểm cấp.
- Không log response body chứa credential.
- Có quy trình rotate/revoke credential theo khả năng endpoint và admin workflow.

### 14.1. Không trả secret trong Client Read nếu không có lý do

Một số response registration có thể chứa metadata nhạy cảm theo contract. Hệ thống phải xác định trường nào được trả ở lúc tạo và lúc đọc. Client Read không phải lý do để log hoặc phổ biến lại client secret. Nếu implementation trả field credential theo đặc tả, chỉ caller có registration access token hợp lệ mới được đọc.

### 14.2. Xử lý response bị mất

Nếu POST registration timeout, không biết chắc server đã tạo client hay chưa. Initial access token có thể đã bị consume. Không retry mù quáng nhiều lần bằng token mới vì có thể tạo duplicate registrations.

Quy trình recovery:

1. Ghi correlation/request ID trước khi gọi.
2. Kiểm tra audit log hoặc registration store bằng dữ liệu reconciliation đã được phê duyệt.
3. Xác định client đã tạo hay chưa.
4. Nếu đã tạo, lấy lại thông tin theo quy trình quản trị an toàn; không cố đọc bằng initial token đã dùng.
5. Nếu chưa tạo, yêu cầu cấp initial token mới theo approval.

Nếu cần idempotency, thiết kế idempotency key và persistence riêng ở onboarding service; đừng giả định RFC 7591 hay SAS tự đảm bảo idempotency cho mọi retry.

## 15. Rate limit, audit và chống lạm dụng

Protected registration vẫn cần abuse controls:

| Kiểm soát | Mục đích |
| --- | --- |
| Rate limit theo registrar/tenant/IP | Hạn chế tạo client hàng loạt |
| Quota số registration | Giới hạn số client cho mỗi partner/product |
| Approval workflow | Chặn metadata hoặc quyền vượt phạm vi |
| Audit immutable | Truy vết ai tạo client, lúc nào và bằng quyền nào |
| Credential rotation | Giảm tác động khi registrar secret/token bị lộ |
| Alert bất thường | Phát hiện nhiều lỗi, redirect URI lạ hoặc grant/scope bất thường |
| Egress restrictions | Hạn chế SSRF khi xử lý metadata URI |
| Transaction/one-time token state | Ngăn replay initial access token giữa các node |

Audit event nên lưu registrar identity, registration ID, owner/tenant, grant/scope được duyệt, redirect URI đã normalize, approval reference và kết quả. Không lưu raw initial access token, client secret hoặc registration access token trong log.

### 15.1. Thu hồi registrar credential

Khi registrar bị xâm phạm:

1. Disable registrar client hoặc thu hồi credential.
2. Thu hồi/invalid initial access tokens chưa sử dụng.
3. Điều tra các registration được tạo trong khoảng thời gian nghi ngờ.
4. Disable client mới có metadata/quyền bất thường.
5. Rotate registrar secret/private key và xem xét token đã phát hành.
6. Kiểm tra audit log và thông báo các resource owner liên quan theo incident policy.

### 15.2. Thu hồi registration access

Registration access token có thể bị lộ riêng với client secret. Cần có cách disable registration hoặc thu hồi token theo khả năng server và quy trình admin. Nếu SAS endpoint không cung cấp thao tác update/delete mà hệ thống cần, dùng quản trị server-side có kiểm soát hoặc xây extension phù hợp; không gọi một method chưa được hỗ trợ.

## 16. Multi-instance và tính nguyên tử của one-time token

Trong production nhiều instance, một initial access token không được chấp nhận đồng thời ở hai node.

Rủi ro:

1. Request A đến node 1 và request B đến node 2 gần như cùng lúc.
2. Cả hai node đọc token là active trước khi trạng thái invalidated được ghi.
3. Cả hai có thể tạo registration nếu storage/update không có tính nguyên tử.

Biện pháp:

- Dùng OAuth2AuthorizationService với storage dùng chung.
- Đảm bảo transaction/locking hoặc conditional update cho one-time use.
- Không dựa vào in-memory authorization store trong môi trường nhiều node.
- Test hai request đồng thời dùng cùng initial token.
- Kiểm tra retry/load balancer không gửi lại request ngoài ý muốn.
- Đồng bộ thời gian và trạng thái token giữa các instance.

One-time token là một tính chất bảo mật cần được xác minh trong toàn bộ deployment, không chỉ khi chạy một JVM local.

## 17. Request/response minh họa từ đầu đến cuối

### 17.1. Lấy initial token

```bash
curl --request POST "https://login.example.com/oauth2/token" \
  --user "$REGISTRAR_CLIENT_ID:$REGISTRAR_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=client.create"
```

Giữ access token trong secret store hoặc memory của onboarding service. Không echo token ra terminal log trong production.

### 17.2. Tạo client

```bash
curl --request POST "https://login.example.com/connect/register" \
  --header "Authorization: Bearer $INITIAL_ACCESS_TOKEN" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --data '{
    "client_name": "orders-web",
    "application_type": "web",
    "redirect_uris": [
      "https://orders.example.com/login/oauth2/code/company"
    ],
    "grant_types": [
      "authorization_code",
      "refresh_token"
    ],
    "response_types": ["code"],
    "scope": "openid profile orders.read",
    "token_endpoint_auth_method": "client_secret_basic"
  }'
```

### 17.3. Đọc registration

```bash
curl --request GET "$REGISTRATION_CLIENT_URI" \
  --header "Authorization: Bearer $REGISTRATION_ACCESS_TOKEN" \
  --header "Accept: application/json"
```

Các biến shell ở trên là placeholder. Path registration thực tế phải lấy từ registration_client_uri trong response thay vì tự ghép client ID nếu server trả URI khác.

## 18. Ma trận kiểm thử protected registration

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| DCR mặc định tắt | Không bật clientRegistrationEndpoint | Registration endpoint không hoạt động như DCR |
| Endpoint bật | Cấu hình OIDC Client Registration + JwtDecoder | Endpoint nhận request theo contract |
| Thiếu Bearer token | POST registration không Authorization header | Bị từ chối |
| Token không hợp lệ | Bearer token sai chữ ký/hết hạn | Bị từ chối |
| Token thiếu client.create | Access token không có scope này | Bị từ chối |
| Token có scope thừa | client.create orders.read | Bị từ chối theo quy tắc SAS 1.5.8 |
| Token chỉ client.create | Initial token đúng scope | Request registration có thể tiếp tục validation |
| Token dùng lại | Gửi lại initial token đã consume | Bị từ chối |
| Registrar không được phép | Client không được cấp scope client.create | Không thể đăng ký |
| Client Read thiếu token | GET registration URI không Bearer | Bị từ chối |
| Client Read thiếu client.read | Bearer token không đủ scope | Bị từ chối |
| Client Read đúng token | Registration access token đúng client | Trả metadata registration được phép |
| Token của client A đọc client B | URI registration B nhưng token A | Bị từ chối |
| Redirect URI không hợp lệ | URI không được duyệt | Registration bị từ chối |
| Grant không hỗ trợ | Request yêu cầu grant không được server hỗ trợ | Bị từ chối |
| Grant không được phép | Grant được server hỗ trợ nhưng bị policy client cấm | Bị từ chối |
| Scope quá rộng | Request xin scope admin/internal | Bị từ chối hoặc giảm theo policy rõ ràng |
| Public client gửi secret method | Metadata không tương thích loại client | Bị từ chối |
| Custom metadata không whitelist | JSON có field lạ | Bỏ qua hoặc từ chối theo policy |
| Logo/JWKS URI nội bộ | URL trỏ loopback/private network | Bị chặn bởi SSRF policy |
| Duplicate registration | Request tương tự được gửi nhiều lần | Có reconciliation/idempotency policy, không tạo trùng ngoài ý muốn |
| Timeout sau commit | Server tạo client nhưng response mất | Reconciliation không retry mù |
| Concurrent initial token replay | Hai node dùng cùng token cùng lúc | Chỉ một request thành công |
| Registrar credential revoked | Disable registrar trước request | Token mới không được cấp; credential cũ không dùng được theo policy |
| Initial token expired | Hết hạn trước registration | Bị từ chối |
| Registration token revoked | Client Read bằng token đã revoke | Bị từ chối |
| Registration response secret | Client mới dùng secret | Secret được lưu an toàn và không log |
| Multi-tenant mismatch | Registrar gửi tenant không thuộc phạm vi | Bị từ chối |
| Approval missing | Không có approval record | Bị từ chối ở policy layer |
| Rate limit exceeded | Registrar vượt quota | Bị throttle/reject |
| Audit trail | Registration thành công/thất bại | Có event cần thiết, không chứa raw credential |
| Reverse proxy | Public HTTPS, backend private | Token/URI không lộ internal host; Authorization header được chuyển an toàn |

### 18.1. Test one-time token bằng integration test

Pseudocode:

```java
MvcResult first = registerClient(initialAccessToken, validRequest);
assertThat(first.getResponse().getStatus()).isEqualTo(201);

MvcResult replay = registerClient(initialAccessToken, anotherValidRequest);
assertThat(replay.getResponse().getStatus()).isBetween(400, 499);
```

Đây là pseudocode; registerClient(...) là helper của test. Test cần xác minh trạng thái registration trong repository để bảo đảm chỉ một client được tạo, không chỉ dựa vào HTTP status.

### 18.2. Test scope chính xác

Kiểm tra ít nhất ba trường hợp:

```java
// Token có đúng một scope
assertRegistrationAllowed(Set.of("client.create"));

// Token thiếu quyền tạo
assertRegistrationRejected(Set.of("client.read"));

// Token có scope bổ sung
assertRegistrationRejected(Set.of("client.create", "orders.read"));
```

SAS 1.5.8 hướng dẫn initial token phải chứa scope client.create duy nhất. Giữ test này tách biệt với policy của Client Read và scope nghiệp vụ của client mới.

## 19. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Registration endpoint trả 404 | DCR chưa bật hoặc path/proxy sai | Kiểm tra clientRegistrationEndpoint(...), endpoint matcher và ingress |
| 401 khi POST registration | Thiếu Bearer token, token sai chữ ký/hết hạn | Kiểm tra token issuer, audience, JwtDecoder và Authorization header |
| 403/invalid_scope | Initial token không có đúng client.create | Kiểm tra scope token thực tế |
| Token có client.create nhưng vẫn bị từ chối | Token có thêm scope hoặc đã dùng | Kiểm tra toàn bộ scope và trạng thái one-time |
| Không thể tạo initial token | Registrar thiếu Client Credentials hoặc scope chưa đăng ký | Kiểm tra RegisteredClient của registrar |
| Client Read trả lỗi | Sai registration URI/token hoặc thiếu client.read | Dùng URI response trả về và token đúng quyền |
| Custom metadata biến mất | Converter mặc định không map field custom | Cấu hình cả RegisteredClient converter và response converter |
| Registration trả redirect URI error | URI không khớp validator/policy | Kiểm tra scheme, host, path và validator |
| DCR endpoint bật nhưng app không khởi động | Thiếu JwtDecoder bean | Đăng ký decoder đúng key source |
| Client bị tạo hai lần sau timeout | Retry mù hoặc thiếu idempotency/reconciliation | Tra audit/registration store trước khi retry |
| One-time token được dùng ở hai node | Authorization store không dùng chung/cập nhật không nguyên tử | Kiểm tra persistence, transaction và concurrency test |
| Secret xuất hiện trong log | HTTP body/response logging | Mask Authorization/body và tắt logging credential |
| URL metadata gây SSRF | Không validate URL/egress | Chặn private/link-local, redirect và DNS rebinding |

Trình tự điều tra: **registrar authentication → initial token claims/scope → one-time token state → registration endpoint → metadata validation → persistence → registration response → Client Read authorization**.

## 20. Checklist trước production

- [ ] DCR chỉ được bật khi có yêu cầu onboarding động rõ ràng.
- [ ] Client Registration Endpoint chỉ truy cập qua HTTPS.
- [ ] Có quy trình approval trước khi cấp initial access token.
- [ ] Registrar là confidential client/service account được quản trị riêng.
- [ ] Initial token chỉ có scope client.create, TTL ngắn và one-time use.
- [ ] Token state được lưu bền vững và cập nhật nguyên tử giữa các instance.
- [ ] JwtDecoder được cấu hình để xác minh Bearer token của DCR endpoint.
- [ ] Registration request được validate về redirect URI, grant, response type, scope, auth method và metadata URI.
- [ ] client.create/client.read chỉ cấp cho registrar/service cần thiết.
- [ ] Initial access token, registration access token và client secret được lưu tách biệt.
- [ ] Registration response không bị log hoặc gửi tới bên không được phép.
- [ ] Client Read bị giới hạn vào đúng registration.
- [ ] Custom metadata được whitelist và serialize có kiểm soát.
- [ ] Có rate limit, quota, audit và alert bất thường.
- [ ] Có quy trình revoke registrar credential, initial token và registration access.
- [ ] Có recovery khi request timeout sau khi server đã persist client.
- [ ] Có test replay, concurrent use, wrong scope, wrong client và tenant mismatch.
- [ ] Không giả định SAS hỗ trợ update/delete registration nếu chưa xác minh phiên bản/API.

## 21. Tình huống tổng hợp: partner onboarding có phê duyệt

Một nền tảng cho phép đối tác đăng ký ứng dụng OIDC để đăng nhập vào portal.

**Bước 1 — Onboarding:** đối tác gửi tên tổ chức, owner kỹ thuật, domain callback và môi trường. Operator kiểm tra domain, hợp đồng và mục đích sử dụng.

**Bước 2 — Cấp registrar token:** hệ thống cấp initial access token ngắn hạn cho registrar đã xác thực. Token chỉ có client.create.

**Bước 3 — Đăng ký client:** registrar gửi JSON với client name, redirect URI HTTPS, Authorization Code + Refresh Token, response type code, scope đã duyệt và authentication method phù hợp.

**Bước 4 — Validation:** server kiểm tra redirect URI theo domain đã xác minh, scope theo sản phẩm, grant theo loại ứng dụng và policy tenant.

**Bước 5 — Cấp credential:** server tạo client_id, secret nếu cần, registration access token và registration client URI. Onboarding service lưu credential trong secret manager.

**Bước 6 — Client Read:** service kiểm tra lại metadata qua registration URI với registration access token có client.read; không dùng initial token đã consume.

**Bước 7 — Audit và vận hành:** lưu owner, approval ID, metadata đã duyệt, thời gian tạo và registrar identity. Khi đối tác rời hệ thống, disable client/credential theo admin policy và thu hồi token liên quan.

Luồng này cho phép đối tác tự động hóa tích hợp nhưng giữ quyền tạo client trong phạm vi đã phê duyệt.

## 22. Tổng kết

Protected Dynamic Client Registration dùng token để kiểm soát ai được tạo OAuth/OIDC client mới. Trong Spring Authorization Server 1.5.8:

1. OIDC Client Registration Endpoint **disabled mặc định**; cần bật rõ ràng bằng clientRegistrationEndpoint(...).
2. Endpoint là OAuth protected resource, yêu cầu Bearer access token và JwtDecoder.
3. Initial access token dùng cho registration phải có **duy nhất scope client.create**.
4. Initial token **chỉ sử dụng một lần**; sau khi đăng ký thành công, SAS invalidates token.
5. client.read là quyền cho Client Read; registration access token và URI được trả trong registration response.
6. Quyền registrar không tự cấp grant/scope cho client mới; metadata vẫn phải qua validation và approval.
7. Production cần bảo vệ credential, audit, quota, transaction, concurrency và recovery sau timeout.

RFC 7591 định nghĩa cơ chế đăng ký động và cho phép protected registration qua initial access token. Spring Authorization Server cung cấp implementation OIDC Client Registration có quy tắc scope và one-time token cụ thể. Hãy phân biệt protocol tổng quát với hành vi framework, rồi kiểm thử cả luồng thành công lẫn replay/unauthorized cases trước khi mở endpoint production.

### Tài liệu tham khảo

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server 1.5.8 — How-to: Register a Client Dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
