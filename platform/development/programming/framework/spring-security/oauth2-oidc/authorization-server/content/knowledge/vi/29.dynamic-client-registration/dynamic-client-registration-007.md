# Registration access token và endpoint cấu hình client OIDC

## 1. Bối cảnh: đăng ký client xong vẫn cần quản lý registration

Trong hệ thống OAuth 2.0/OpenID Connect (OIDC) sử dụng **Spring Security**, **Spring Authorization Server** và Spring Boot, một ứng dụng có thể đăng ký với OpenID Provider (OP) bằng Dynamic Client Registration thay vì phải được quản trị viên tạo thủ công trước.

Sau khi đăng ký thành công, OP cấp `client_id`, có thể cấp `client_secret`, và có thể trả thêm hai giá trị quan trọng:

- **`registration_access_token`**: Bearer token dùng để truy cập cấu hình của một client đã đăng ký.
- **`registration_client_uri`**: URL Client Configuration Endpoint dành riêng cho registration đó.

Hai giá trị này cho phép client đọc lại cấu hình mà OP đang lưu. Trong OIDC Dynamic Client Registration 1.0, thao tác được định nghĩa cho Client Configuration Endpoint là **HTTP GET**. Các thao tác update/delete mở rộng được mô tả riêng trong RFC 7592 (Experimental), không nên giả định mọi OP đều hỗ trợ.

Bài học thuộc chương **Đăng ký client động**, tập trung vào Registration Access Token và Client Configuration Endpoint, gồm giao thức OIDC, cách sử dụng an toàn, và cấu hình tương ứng trong Spring Authorization Server.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Initial Access Token với Registration Access Token.
2. Giải thích quan hệ giữa `registration_access_token`, `registration_client_uri` và `client_id`.
3. Đọc lại cấu hình client bằng Client Configuration Endpoint.
4. Hiểu các trường trong Registration Response và Read Response.
5. Bảo vệ Registration Access Token như một credential có quyền quản lý client.
6. Xử lý token rotation, secret rotation và trạng thái registration.
7. Bật Dynamic Client Registration trong Spring Authorization Server.
8. Cấp quyền `client.create` và `client.read` cho registrar client.
9. Gọi `/connect/register` và đọc URL `registration_client_uri` bằng Spring `WebClient`.
10. Mở rộng client metadata bằng converter phù hợp.
11. Phân biệt OIDC Registration 1.0 với RFC 7592 Management Protocol.
12. Thiết kế kiểm thử, giám sát và quy trình thu hồi registration.

## 2. Registration Access Token là gì?

Registration Access Token (RAT) là OAuth 2.0 Bearer Token do Authorization Server cấp cho **một client registration cụ thể**. Token này xác thực caller khi caller truy cập Client Configuration Endpoint để đọc thông tin registration.

Ví dụ, sau khi OP đăng ký `inventory-web`, nó có thể trả:

~~~json
{
  "client_id": "inventory-web-7f21",
  "registration_access_token": "RAT_VALUE_FROM_AUTHORIZATION_SERVER",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21"
}
~~~

Đây là ví dụ minh họa. URL thật phải được lấy nguyên vẹn từ response; không tự ghép từ `client_id` hoặc đoán path.

### 2.1. RAT gắn với một registration

Registration Access Token:

- Được OP phát hành và liên kết với một client registration.
- Được gửi trong header `Authorization: Bearer ...` tới Client Configuration Endpoint.
- Cho phép đọc thông tin client theo quyền OP cấp.
- Có thể cho phép các thao tác quản lý bổ sung nếu OP triển khai extension tương ứng.
- Phải được bảo vệ như một credential có giá trị cao.

RAT không phải `client_secret`, không phải access token gọi API nghiệp vụ, và không phải Initial Access Token dùng để tạo registration.

### 2.2. RAT có thể rất nhạy cảm

Một client secret thường xác thực client tại Token Endpoint. RAT xác thực quyền truy cập vào hồ sơ registration; hồ sơ này có thể chứa client secret, redirect URIs, grant types, JWK metadata và các cấu hình bảo mật khác.

Nếu kẻ tấn công lấy được RAT, họ có thể đọc metadata nhạy cảm của client. Nếu OP hỗ trợ RFC 7592 update/delete, token còn có thể cho phép thay đổi hoặc xóa registration. Vì vậy, RAT cần được bảo vệ ít nhất tương đương credential dài hạn.

## 3. Phân biệt ba loại credential trong Dynamic Client Registration

Có ba giá trị thường bị nhầm:

| Credential | Được cấp cho ai? | Dùng ở đâu? | Mục đích |
|---|---|---|---|
| Initial Access Token | Registrar/developer hoặc hệ thống onboarding | Client Registration Endpoint | Cho phép tạo registration mới |
| Registration Access Token | Một client registration vừa được tạo | Client Configuration Endpoint | Đọc/quản lý registration đó |
| Client Secret | Confidential client | Token Endpoint | Xác thực client khi xin token |

### 3.1. Initial Access Token

Initial Access Token (IAT) là token do OP cấp theo chính sách riêng để bảo vệ Client Registration Endpoint. RFC 7591 cho phép endpoint đăng ký mở hoặc yêu cầu IAT; cách phát hành IAT nằm ngoài phạm vi RFC.

Trong ví dụ Spring Authorization Server 1.5.8, registrar client dùng Client Credentials để xin access token chỉ có scope `client.create`. Token này được sử dụng cho request POST đăng ký và bị vô hiệu sau khi registration thành công.

### 3.2. Registration Access Token

RAT được trả về trong Registration Response nếu OP hỗ trợ Client Configuration Endpoint. Client dùng RAT để gọi URL trong `registration_client_uri`.

RAT có vòng đời gắn với registration và có thể là credential dài hạn. Không dùng IAT để gọi Client Configuration Endpoint và không dùng RAT để xin access token nghiệp vụ.

### 3.3. Client Secret

Client Secret xác thực confidential client ở Token Endpoint theo `token_endpoint_auth_method`, ví dụ `client_secret_basic`. Nó không thay thế RAT.

Một response có thể trả cả `client_secret` và `registration_access_token`; phải lưu chúng ở vị trí bảo mật, tách mục đích và giới hạn quyền truy cập.

## 4. Client Configuration Endpoint làm gì?

Client Configuration Endpoint là protected resource của OP, cung cấp thông tin registration đã được lưu. OP trả URL endpoint trong `registration_client_uri`.

Trong OIDC Dynamic Client Registration 1.0, endpoint:

- Được provision tùy chọn.
- Chỉ hoạt động khi registration response trả cả `registration_client_uri` và `registration_access_token`.
- Yêu cầu client gửi RAT dưới dạng Bearer Token trong mọi request.
- Định nghĩa HTTP GET để đọc cấu hình.
- Không yêu cầu client tự xây URL endpoint từ `client_id`.

Ví dụ request:

~~~http
GET /connect/register?client_id=inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Accept: application/json
Authorization: Bearer RAT_VALUE_FROM_AUTHORIZATION_SERVER
~~~

Đường dẫn trên chỉ minh họa. Client phải sử dụng đúng URI mà OP đã trả.

### 4.1. Client Configuration Endpoint là protected resource

RAT được gửi như OAuth Bearer Token. OP xác thực token, xác định registration gắn với token và chỉ trả thông tin của registration đó.

Không nhận `client_id` từ query rồi chỉ dựa vào giá trị này để trả cấu hình. Server phải đối chiếu client được chỉ định với client mà RAT đã được cấp cho.

### 4.2. Read operation nên idempotent

OIDC Registration 1.0 khuyến nghị GET read không làm thay đổi cấu hình registration. Client có thể đọc lại để đồng bộ metadata sau khi onboarding hoặc kiểm tra trạng thái cấu hình.

Nếu OP có cơ chế rotation credential, response có thể phản ánh giá trị đã thay đổi. Client phải cập nhật secret/token theo quy tắc của OP và không tiếp tục dùng credential cũ nếu response báo giá trị mới.

## 5. Vòng đời: từ đăng ký tới đọc cấu hình

Một quy trình điển hình:

~~~mermaid
sequenceDiagram
    participant R as Registrar / Onboarding Service
    participant OP as OpenID Provider
    participant DB as RegisteredClient Store
    participant C as Newly Registered Client

    R->>OP: POST /connect/register + Initial Access Token
    OP->>OP: Validate registrar, scope and client metadata
    OP->>DB: Persist RegisteredClient
    DB-->>OP: Registration created
    OP-->>R: 201 Created + client_id + RAT + registration_client_uri
    R->>C: Deliver client credentials and registration data securely
    C->>OP: GET registration_client_uri + RAT
    OP->>OP: Validate RAT and registration binding
    OP->>DB: Read registered client metadata
    DB-->>OP: Current client configuration
    OP-->>C: 200 OK + client metadata
~~~

Các bước:

1. Registrar xin Initial Access Token.
2. Registrar gửi metadata client tới Client Registration Endpoint.
3. OP validate và tạo registration.
4. OP trả `client_id`, có thể có `client_secret`, và có thể có RAT/URI quản lý.
5. Client lưu credential và URL quản lý một cách an toàn.
6. Khi cần đồng bộ, client gửi GET tới URL đó kèm RAT.
7. OP xác minh quyền và trả cấu hình hiện tại.

### 5.1. Hai giai đoạn xác thực khác nhau

- Registration Endpoint kiểm tra Initial Access Token hoặc policy đăng ký mở.
- Configuration Endpoint kiểm tra Registration Access Token thuộc đúng client.

Không dùng chung một token cho cả hai giai đoạn chỉ vì cả hai đều dùng Bearer scheme.

## 6. Discovery và URL registration

OIDC Provider Configuration có thể công bố `registration_endpoint`, cho biết nơi RP gửi request đăng ký. Client Configuration Endpoint là URL riêng của từng registration và được trả trong `registration_client_uri`.

Ví dụ metadata rút gọn:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "registration_endpoint": "https://auth.example.com/connect/register"
}
~~~

Đây là metadata minh họa. OP có thể dùng URI khác; client nên lấy `registration_endpoint` từ Discovery metadata của issuer đã tin cậy.

### 6.1. Không tự dựng registration_client_uri

Sau khi đăng ký, OP trả `registration_client_uri`. Client phải dùng nguyên URL đó. URL có thể chứa client ID trong path hoặc query, hoặc dùng cấu trúc khác theo deployment.

Không tự nối `registration_endpoint + "?client_id=" + client_id`. Cách làm này có thể tạo sai URL hoặc gửi RAT tới endpoint không đúng.

### 6.2. Tin cậy issuer trước khi gọi URL

Client phải xác minh Discovery metadata thuộc OP dự kiến và sử dụng TLS. Không chấp nhận `registration_client_uri` do người dùng hoặc một client không tin cậy tự cung cấp rồi gửi RAT tới đó.

Nếu ứng dụng hỗ trợ nhiều issuer, lưu quan hệ giữa registration, issuer và URL endpoint để tránh nhầm credential giữa các OP.

## 7. Registration Response và các trường quan trọng

Một response thành công thường dùng HTTP `201 Created` và JSON:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "inventory-web-7f21",
  "client_secret": "CLIENT_SECRET_VALUE",
  "client_secret_expires_at": 0,
  "registration_access_token": "RAT_VALUE",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21",
  "token_endpoint_auth_method": "client_secret_basic",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read"
}
~~~

### 7.1. Các trường định danh và credential

| Trường | Ý nghĩa |
|---|---|
| `client_id` | Client identifier duy nhất do OP cấp |
| `client_secret` | Secret của confidential client nếu OP cấp |
| `client_secret_expires_at` | Thời điểm secret hết hạn theo NumericDate; `0` biểu thị không hết hạn |
| `client_id_issued_at` | Thời điểm cấp client ID nếu được trả |
| `registration_access_token` | RAT để gọi Client Configuration Endpoint |
| `registration_client_uri` | URL cấu hình riêng của client |

Nếu OP trả `registration_access_token`, nó phải đồng thời trả `registration_client_uri`; nếu không provision Client Configuration Endpoint thì có thể bỏ cả hai.

### 7.2. Metadata client

Response cũng chứa metadata đã được OP chấp nhận, có thể gồm:

- `redirect_uris`
- `grant_types`
- `response_types`
- `token_endpoint_auth_method`
- `client_name`
- `logo_uri`
- `client_uri`
- `policy_uri`
- `tos_uri`
- `jwks_uri` hoặc `jwks`
- `scope`
- Các OIDC metadata như signing/encryption algorithms

OP có thể từ chối hoặc thay thế một số giá trị được yêu cầu, vì vậy client phải lưu **giá trị thực tế trong response**, không giả định tất cả request metadata đã được chấp nhận nguyên trạng.

### 7.3. Cache-Control

Registration response chứa credential nên OP nên trả `Cache-Control: no-store`. Client cũng không nên đưa response vào HTTP cache, log, tracing span hoặc analytics payload.

## 8. Client Read Request

Khi đã có `registration_client_uri` và RAT, client gọi HTTP GET:

~~~http
GET /connect/register?client_id=inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Accept: application/json
Authorization: Bearer RAT_VALUE
~~~

Client cần:

1. Dùng HTTPS và kiểm tra certificate của OP.
2. Gửi RAT trong Authorization header.
3. Không đưa RAT vào URL query string.
4. Gọi đúng `registration_client_uri` đã nhận.
5. Xử lý lỗi Bearer token theo RFC 6750.
6. Parse JSON và kiểm tra metadata trước khi cập nhật local config.

### 8.1. Read Response

Response thành công thường dùng HTTP 200:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "inventory-web-7f21",
  "client_secret": "CURRENT_CLIENT_SECRET",
  "client_secret_expires_at": 0,
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21",
  "token_endpoint_auth_method": "client_secret_basic",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read"
}
~~~

Read Response không nhất thiết phải trả lại `registration_access_token` hoặc `registration_client_uri`, trừ khi các giá trị đó được cập nhật theo semantics của OP.

### 8.2. Không tự thay cấu hình runtime khi chưa kiểm tra

Client nên validate response trước khi cập nhật local configuration. Ví dụ, nếu `redirect_uris` thay đổi ngoài change request dự kiến, cần phát hiện drift và yêu cầu quy trình phê duyệt phù hợp.

Không tự động tin mọi metadata trả về nếu nó sẽ được dùng để tạo redirect, gọi endpoint hoặc tải khóa.

## 9. Quy tắc HTTP và lỗi

| Tình huống | Status thường gặp | Ý nghĩa |
|---|---:|---|
| Đọc registration thành công | 200 | Trả client metadata |
| RAT thiếu/không hợp lệ/hết hạn | 401 | Bearer authentication thất bại |
| Client không có quyền đọc registration | 403 | Đã xác thực nhưng không được phép |
| Client không tồn tại hoặc token không còn hợp lệ | 401 theo OIDC Registration error rules | Tránh tiết lộ registration tồn tại |
| Metadata registration request không hợp lệ | 400 | `invalid_client_metadata` hoặc lỗi phù hợp |
| Redirect URI không hợp lệ | 400 | `invalid_redirect_uri` |
| Registrar không đủ quyền | 401/403 tùy cơ chế xác thực và policy | Không được phép tạo client |

OIDC Registration 1.0 quy định Client Configuration Endpoint không nên trả HTTP 404 cho lỗi read; phản hồi 401 giúp hạn chế dò đoán registration.

### 9.1. 401 và 403 không giống nhau

- `401 Unauthorized`: RAT không hợp lệ, thiếu hoặc client/registration không còn tồn tại theo semantics giao thức.
- `403 Forbidden`: RAT hợp lệ nhưng caller không có quyền thực hiện thao tác được yêu cầu.

Client không nên retry vô hạn với cùng một token đã bị từ chối. Hãy kiểm tra token storage, rotation và trạng thái registration.

## 10. Registration Access Token và token rotation

RAT là Bearer Token; bất kỳ ai sở hữu token đều có thể thực hiện các thao tác mà OP cho phép. OIDC Registration 1.0 cho phép OP trả RAT trong registration response; nếu OP không hỗ trợ quản lý registration, có thể không trả RAT và URL cấu hình.

RFC 7592 bổ sung khả năng xoay Registration Access Token khi client đọc hoặc cập nhật registration. Nếu response trả token mới, client phải bỏ token cũ ngay và lưu token mới trước lần gọi tiếp theo.

### 10.1. Xử lý rotation an toàn

Một client quản lý registration nên:

1. Đọc RAT hiện tại từ secret store.
2. Gọi configuration endpoint qua TLS.
3. Kiểm tra response có `registration_access_token` mới hay không.
4. Nếu có, ghi token mới an toàn và xác nhận lưu thành công.
5. Sau đó mới đánh dấu token cũ không còn được dùng.
6. Nếu response không có token mới, giữ token hiện tại theo contract của OP.

Không ghi token mới vào log để debug. Không gửi lại token cũ sau khi server đã thông báo rotation.

### 10.2. RAT có thể dài hạn

RFC 7592 khuyến nghị RAT không hết hạn trong khi client vẫn active để tránh mất khả năng quản lý registration. Tuy nhiên, OP có thể rotation token hoặc dùng policy khác để giới hạn rủi ro.

Đây là lý do RAT cần secret storage, quyền truy cập tối thiểu, audit và quy trình thu hồi rõ ràng.

## 11. Registration Access Token không phải client_secret

| Đặc điểm | Registration Access Token | Client Secret |
|---|---|---|
| Mục đích | Đọc/quản lý registration | Xác thực client tại Token Endpoint |
| Endpoint | `registration_client_uri` | Token Endpoint |
| Cách gửi | Bearer Token | Theo `token_endpoint_auth_method` |
| Phạm vi | Một registration | Một OAuth client |
| Có thể đọc client metadata? | Có, theo quyền OP cấp | Không tự có quyền đọc cấu hình |
| Có thể xin token API? | Không theo semantics RAT | Dùng để client authentication trong grant được phép |
| Khi lộ | Lộ cấu hình, có thể cho phép update/delete nếu extension bật | Kẻ tấn công có thể giả client tại Token Endpoint |

Không dùng client secret thay RAT để gọi Client Configuration Endpoint. Không dùng RAT thay client secret để gọi Token Endpoint.

## 12. OIDC Registration 1.0 và RFC 7592 khác nhau thế nào?

Đây là ranh giới giao thức quan trọng:

| Khả năng | OIDC Dynamic Client Registration 1.0 | RFC 7592 |
|---|---|---|
| Đăng ký client | Có, qua POST Registration Endpoint | Mở rộng RFC 7591 |
| Trả `registration_access_token` và `registration_client_uri` | Tùy chọn theo response | Có trong management response |
| Đọc cấu hình | GET | GET |
| Cập nhật cấu hình | Không định nghĩa trong OIDC Registration 1.0 | PUT |
| Xóa registration | Không định nghĩa trong OIDC Registration 1.0 | DELETE |
| Tình trạng đặc tả | OpenID Foundation Final Specification | RFC Experimental |

OIDC Registration 1.0 định nghĩa GET là HTTP method duy nhất cho Client Configuration Endpoint. Phần update/delete được bổ sung bởi **OAuth 2.0 Dynamic Client Registration Management Protocol — RFC 7592**, là Experimental RFC.

### 12.1. PUT trong RFC 7592

Nếu OP triển khai RFC 7592, client có thể gửi PUT tới Client Configuration Endpoint với toàn bộ metadata đã đăng ký. Đây là cập nhật toàn bộ representation; metadata bị bỏ qua có thể được hiểu là null/empty theo RFC.

Client phải giữ `client_id` hiện tại; không được tự đặt client secret mới. Server có thể cấp secret hoặc RAT mới trong response.

### 12.2. DELETE trong RFC 7592

Nếu OP triển khai RFC 7592, DELETE có thể deprovision client registration. Sau khi xóa, `client_id`, `client_secret` và RAT của registration bị vô hiệu hóa. Server SHOULD thu hồi authorization grants và token liên quan nếu có thể.

Không gọi PUT hoặc DELETE chỉ vì OP trả `registration_client_uri`. Phải xác nhận OP hỗ trợ RFC 7592 và phương thức tương ứng.

## 13. Spring Authorization Server hỗ trợ phần nào?

Theo tài liệu Spring Authorization Server 1.5.8:

- Dynamic Client Registration mặc định bị tắt.
- Có thể bật OIDC Client Registration Endpoint bằng `clientRegistrationEndpoint(...)`.
- Registrar client dùng scope `client.create` để đăng ký.
- Scope `client.read` có thể được cấu hình để đọc client registration.
- Registration Response trả `registration_access_token` và `registration_client_uri`.
- Tài liệu hướng dẫn sử dụng RAT để GET lại client configuration.

Tài liệu hướng dẫn chính thức minh họa **đăng ký và đọc cấu hình**. Không nên suy luận rằng Spring Authorization Server 1.5.8 mặc định triển khai toàn bộ PUT/DELETE của RFC 7592. Nếu cần update/delete, phải xác minh API/version hoặc tự xây dựng extension tương thích và kiểm thử đầy đủ.

## 14. Bật Client Registration Endpoint trong Spring Authorization Server

Trong Spring Authorization Server 1.x, bật endpoint trong Authorization Server SecurityFilterChain:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

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
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
~~~

Các điểm chính:

- `getEndpointsMatcher()` giới hạn chain cho protocol endpoints của Authorization Server.
- `oidc(...)` bật OIDC configurer.
- `clientRegistrationEndpoint(...)` bật Dynamic Client Registration endpoint.
- Cấu hình này không tự động cho phép mọi người đăng ký; endpoint vẫn phải kiểm tra Initial Access Token và registrar policy.

Trong cấu hình đầy đủ còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, signing key/JWK source, issuer và user authentication chain tùy ứng dụng.

## 15. Cấu hình registrar client

Registrar là client có quyền tạo các client khác. Ví dụ:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {

    RegisteredClient registrar = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode("SECRET_FROM_SECRET_MANAGER"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
~~~

Đây là ví dụ học tập. Production nên dùng secret manager, encoder phù hợp và persistent `RegisteredClientRepository` như JDBC repository.

### 15.1. Hai scope có ý nghĩa khác nhau

- `client.create`: cho phép registrar xin Initial Access Token để tạo registration.
- `client.read`: cho phép registrar đọc registration theo policy Spring Authorization Server guide.

Registrar không nên có thêm scopes API hoặc quyền admin không liên quan. Scope phải được cấp chính xác trong access token.

### 15.2. In-memory repository chỉ phù hợp demo

`InMemoryRegisteredClientRepository` mất dữ liệu khi process restart và không phù hợp deployment nhiều node cần registration bền vững. Production cần lưu registration và authorization state trong kho dữ liệu có backup, transaction và kiểm soát truy cập.

## 16. Xin Initial Access Token trong Spring Authorization Server

Theo hướng dẫn Spring Authorization Server, registrar dùng Client Credentials để xin token với đúng scope `client.create`:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Response minh họa:

~~~json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "client.create"
}
~~~

Trong hướng dẫn SAS 1.5.8, request Initial Access Token phải chỉ có scope `client.create`; nếu access token có scope bổ sung, request registration sẽ bị từ chối. Token ban đầu chỉ được dùng một lần và bị vô hiệu sau khi client được đăng ký thành công.

### 16.1. Không dùng client.read trong Initial Access Token

Registrar có thể được cấu hình `client.read` để lấy token cho thao tác đọc theo guide, nhưng Initial Access Token dùng tạo client phải chỉ có `client.create`.

Phân biệt scope registrar được phép xin với scope thực tế được đưa vào token hiện tại.

## 17. Gửi request đăng ký và nhận RAT

Client Registration Endpoint mặc định trong ví dụ Spring Authorization Server là `/connect/register`. Tốt nhất lấy `registration_endpoint` từ discovery metadata.

Request mẫu:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Inventory Web",
  "application_type": "web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read",
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Sau khi validate, OP trả registration response. Client phải lưu:

- `client_id`
- `client_secret` nếu được cấp
- `registration_access_token`
- `registration_client_uri`
- Metadata thực tế đã được OP chấp nhận

Không lưu response này vào application log. Hãy chuyển credential tới secret store qua kênh được bảo vệ.

## 18. Đọc registration bằng WebClient

Spring Authorization Server guide dùng `WebClient` để POST registration và GET configuration. Ví dụ DTO rút gọn:

~~~java
public record ClientRegistrationResponse(
    @JsonProperty("client_id") String clientId,
    @JsonProperty("client_secret") String clientSecret,
    @JsonProperty("registration_access_token") String registrationAccessToken,
    @JsonProperty("registration_client_uri") String registrationClientUri,
    @JsonProperty("client_name") String clientName,
    @JsonProperty("redirect_uris") List<String> redirectUris,
    @JsonProperty("grant_types") List<String> grantTypes,
    String scope) {
}
~~~

Gọi endpoint đã được OP trả về:

~~~java
public ClientRegistrationResponse readRegistration(
        WebClient webClient,
        String registrationClientUri,
        String registrationAccessToken) {

    return webClient
        .get()
        .uri(registrationClientUri)
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBearerAuth(registrationAccessToken))
        .retrieve()
        .bodyToMono(ClientRegistrationResponse.class)
        .block();
}
~~~

Đoạn code minh họa servlet/blocking caller. Ứng dụng reactive nên giữ pipeline reactive và không gọi `block()` trên event-loop thread.

### 18.1. Bảo vệ URI và token trước khi gọi

Trước khi gọi, ứng dụng cần xác nhận:

- `registrationClientUri` đến từ response của OP tin cậy.
- Scheme là HTTPS.
- Host/issuer phù hợp registration đã lưu.
- RAT được lấy từ secret storage tương ứng registration.
- HTTP client kiểm tra TLS certificate.
- Redirect tự động không làm lộ Authorization header sang origin khác.

Không cho phép caller truyền `registrationClientUri` tùy ý.

## 19. Tùy biến client metadata trong Spring Authorization Server

Spring Authorization Server chuyển đổi OIDC client registration metadata sang `RegisteredClient` bằng converter. Với metadata chuẩn, converter mặc định xử lý các trường framework hỗ trợ.

Nếu cần custom metadata như `logo_uri`, `contacts` hoặc trường riêng của tổ chức, cần mở rộng converter ở cả hai chiều:

1. Registration Request → `RegisteredClient`.
2. `RegisteredClient` → Client Configuration Response.

Trong Spring Authorization Server 1.5.8, các provider có thể được tùy biến thông qua:

- `OidcClientRegistrationAuthenticationProvider`
- `OidcClientConfigurationAuthenticationProvider`
- `OidcClientRegistrationRegisteredClientConverter`
- `RegisteredClientOidcClientRegistrationConverter`

### 19.1. Giữ metadata trong ClientSettings

Ví dụ hướng tiếp cận:

~~~java
ClientSettings.Builder settings =
    ClientSettings.withSettings(registeredClient.getClientSettings().getSettings());

settings.setting("logo_uri", clientRegistration.getClaim("logo_uri"));
settings.setting("contacts", clientRegistration.getClaim("contacts"));

RegisteredClient updated = RegisteredClient.from(registeredClient)
    .clientSettings(settings.build())
    .build();
~~~

Đây là đoạn minh họa cho việc lưu custom metadata; trong converter thực tế cần allowlist field, kiểm tra kiểu dữ liệu, giới hạn kích thước và giữ converter mặc định cho các field chuẩn.

### 19.2. Cấu hình provider converter

Khi tùy biến, cần cập nhật converter ở provider xử lý registration và provider xử lý configuration response. Nếu chỉ lưu custom metadata lúc POST nhưng không chuyển đổi lại khi GET, client sẽ không nhìn thấy những trường đã đăng ký.

Không chấp nhận mọi custom claim rồi lưu thẳng vào `ClientSettings`. Chỉ cho phép metadata được định nghĩa, kiểm tra và có ý nghĩa rõ ràng.

## 20. Bảo mật metadata và tránh SSRF

Dynamic Client Registration nhận metadata do client gửi. Một số metadata chứa URL mà OP có thể truy cập hoặc hiển thị, ví dụ:

- `jwks_uri`
- `sector_identifier_uri`
- `logo_uri`
- `client_uri`
- `policy_uri`
- `tos_uri`

Nếu OP tự tải URL, metadata độc hại có thể gây SSRF, truy cập mạng nội bộ hoặc tải nội dung không mong muốn.

### 20.1. Kiểm tra URL

OP nên áp dụng:

- Chỉ chấp nhận HTTPS cho endpoint/key URL theo metadata yêu cầu.
- Chặn loopback, link-local, private IP và địa chỉ metadata cloud khi không được phép.
- Kiểm soát DNS rebinding và redirect tới host không tin cậy.
- Giới hạn timeout, response size và content type.
- Hạn chế egress network của tiến trình Authorization Server.
- Không render HTML/script từ metadata client.

### 20.2. Redirect URI là metadata bảo mật cao

`redirect_uris` phải được xác minh chính xác và so khớp theo quy tắc OIDC/OAuth. Không chấp nhận wildcard rộng hoặc URI do browser truyền vào authorization request mà không có trong registration.

Client có thể yêu cầu metadata, nhưng OP là bên quyết định giá trị được lưu.

### 20.3. Logo và thông tin hiển thị

Một client độc hại có thể dùng tên/logo giống ứng dụng hợp pháp để phishing. OP nên kiểm tra nguồn logo, liên hệ giữa host logo và redirect URI, và hiển thị trạng thái trust/approval cho client mới.

## 21. Bảo vệ Registration Access Token

RAT là Bearer Token nên possession đồng nghĩa có quyền truy cập endpoint theo policy. Các biện pháp:

- Sinh token có entropy cao, khó đoán.
- Chỉ truyền qua TLS và xác minh server certificate.
- Lưu trong secret manager hoặc vault, mã hóa khi lưu.
- Không log header Authorization, token response hoặc RAT.
- Giới hạn service account được đọc RAT.
- Tách RAT theo từng client registration.
- Có audit cho mọi lần đọc registration.
- Thu hồi RAT khi client deprovision.
- Xem xét rotation theo khả năng OP.
- Không đưa RAT vào browser local storage nếu có thể giữ ở backend.

### 21.1. RAT không phải metadata công khai

`client_id` có thể xuất hiện trong log và protocol message; RAT thì không. `registration_client_uri` cũng không phải bí mật xác thực độc lập, nhưng khi kết hợp với RAT có thể dẫn tới truy cập cấu hình nhạy cảm.

Không coi URL quản lý là một cơ chế bảo mật; quyền đến từ RAT.

## 22. Stateless registration và trường hợp không có RAT

OIDC Registration 1.0 cho phép OP thực hiện stateless dynamic registration. Khi không lưu trạng thái registration ở server, OP có thể không có cơ sở để phát RAT gắn với một registration.

Trong trường hợp đó, OP có thể chỉ trả thông tin cần thiết để client hoạt động và bỏ cả:

- `registration_access_token`
- `registration_client_uri`

Client phải chấp nhận khả năng này. Không coi response thiếu RAT là lỗi nếu OP không provision Client Configuration Endpoint.

Nếu ứng dụng bắt buộc phải đọc lại hoặc quản lý metadata sau registration, hãy chọn OP có stateful registration hoặc thiết kế provisioning API riêng đã được bảo vệ.

## 23. Update/Delete theo RFC 7592: phần mở rộng tùy chọn

RFC 7592 bổ sung các thao tác quản lý registration ngoài OIDC Registration 1.0.

### 23.1. PUT — cập nhật metadata

Nếu OP triển khai RFC 7592, client có thể gửi PUT tới Client Configuration Endpoint với toàn bộ metadata đã đăng ký. Đây là cập nhật toàn bộ representation; metadata bị bỏ qua có thể được hiểu là null/empty theo RFC.

Client phải giữ `client_id` hiện tại; không được tự đặt client secret mới. Server có thể cấp secret hoặc RAT mới trong response.

Ví dụ minh họa khi OP tuyên bố hỗ trợ RFC 7592:

~~~http
PUT /register/inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Authorization: Bearer RAT_VALUE
Content-Type: application/json

{
  "client_id": "inventory-web-7f21",
  "client_name": "Inventory Web Production",
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "scope": "openid profile inventory.read"
}
~~~

### 23.2. DELETE — deprovision registration

Nếu OP triển khai RFC 7592, DELETE có thể deprovision client registration. Sau khi xóa, `client_id`, `client_secret` và RAT của registration bị vô hiệu hóa. Server SHOULD thu hồi authorization grants và token liên quan nếu có thể.

Ví dụ:

~~~http
DELETE /register/inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Authorization: Bearer RAT_VALUE
~~~

Response thành công theo RFC 7592 là `204 No Content`.

### 23.3. Giới hạn với Spring Authorization Server

OIDC Registration 1.0 chỉ định nghĩa GET ở Client Configuration Endpoint. RFC 7592 PUT/DELETE là extension Experimental. Hướng dẫn Spring Authorization Server 1.5.8 trình bày registration và retrieval; không mặc định coi PUT/DELETE đã được framework triển khai.

Nếu cần update/delete, phải xác minh chính xác phiên bản và endpoint implementation, hoặc tự xây extension có authorization, validation, transaction, audit và test tương ứng.

## 24. Kiểm thử Registration Access Token và Configuration Endpoint

### 24.1. Ma trận registrar và registration

| Test case | Kết quả mong đợi |
|---|---|
| Registrar có `client.create` | Xin Initial Access Token thành công |
| Token có thêm scope không được phép | Registration bị từ chối theo policy |
| Không có Initial Access Token khi OP yêu cầu | 401 |
| Metadata redirect URI hợp lệ | Registration được tạo |
| Redirect URI không hợp lệ | 400 `invalid_redirect_uri` hoặc lỗi phù hợp |
| Grant/response type không nhất quán | Registration bị từ chối |
| Registration thành công | Trả `client_id` và metadata đã được OP chấp nhận |
| OP provision management endpoint | Trả cả RAT và registration_client_uri |
| OP stateless | Có thể bỏ cả hai trường quản lý |

### 24.2. Ma trận Client Configuration Endpoint

| Test case | Kết quả mong đợi |
|---|---|
| GET với RAT đúng | 200 và client metadata |
| GET thiếu RAT | 401 |
| GET với RAT sai/hết hạn | 401 |
| RAT thuộc registration khác | Không được đọc registration mục tiêu |
| Client đã bị deprovision | 401 theo protocol semantics |
| Token hợp lệ nhưng không có quyền đọc | 403 |
| Read request lặp lại | Không thay đổi registration |
| Response có secret mới | Cập nhật secret an toàn |
| Response có RAT mới | Lưu token mới và bỏ token cũ |
| Response không có RAT mới | Tiếp tục theo token hiện tại |

### 24.3. Kiểm thử an ninh

- RAT không xuất hiện trong access log hoặc tracing.
- Không gửi RAT tới host khác origin.
- URL metadata không truy cập được địa chỉ private/internal ngoài allowlist.
- Registration không cho phép redirect URI wildcard nguy hiểm.
- Client không thể đọc registration khác bằng cách thay `client_id`.
- Deprovision làm RAT cũ mất hiệu lực.
- Token rotation không để client tiếp tục dùng token cũ.
- Cluster nhiều node đọc cùng registration state nhất quán.
- Custom metadata chỉ được lưu theo allowlist.
- Response JSON không bị cache.

## 25. Vận hành và observability

### 25.1. Metrics

Theo dõi:

- Registration requests theo registrar client.
- Registration success/failure và lỗi metadata.
- Initial Access Token issuance/consumption.
- Client Configuration GET requests.
- RAT authentication failure và 403 authorization failure.
- Tỷ lệ registration có/không có RAT.
- Credential rotation và secret expiry.
- Số client registrations active/deprovisioned.
- Lỗi `RegisteredClientRepository` và authorization store.
- Thời gian từ deprovision tới lúc token/grant liên quan bị vô hiệu.

Không đưa RAT, client secret hoặc token raw vào metric labels.

### 25.2. Audit event

Các event phù hợp:

~~~text
DYNAMIC_CLIENT_REGISTRATION_REQUESTED
DYNAMIC_CLIENT_REGISTRATION_CREATED
DYNAMIC_CLIENT_REGISTRATION_REJECTED
CLIENT_CONFIGURATION_READ
REGISTRATION_ACCESS_TOKEN_ROTATED
CLIENT_SECRET_ROTATED
DYNAMIC_CLIENT_REGISTRATION_DEPROVISIONED
CLIENT_METADATA_VALIDATION_FAILED
~~~

Audit nên có registrar/client ID, issuer, correlation ID, outcome, metadata field names đã thay đổi và timestamp. Không ghi secret/token values hoặc toàn bộ metadata có PII.

### 25.3. Runbook khi client không đọc được cấu hình

1. Kiểm tra OP có trả cả `registration_access_token` và `registration_client_uri` không.
2. Xác minh URL lấy từ response gốc, không bị tự dựng.
3. Kiểm tra issuer/host/TLS certificate.
4. Kiểm tra RAT có thuộc đúng registration không.
5. Kiểm tra token có bị rotation và ứng dụng còn dùng giá trị cũ không.
6. Kiểm tra client registration còn tồn tại không.
7. Kiểm tra registrar/management policy và scope.
8. Kiểm tra `RegisteredClientRepository` và authorization store.
9. Kiểm tra response status 401/403 và `WWW-Authenticate`.
10. Kiểm tra cluster consistency và audit event.

Không giải quyết lỗi bằng cách tắt kiểm tra RAT hoặc cho phép GET cấu hình client công khai.

## 26. Checklist production

- [ ] Dynamic Client Registration được bật có chủ đích.
- [ ] Registrar có scope `client.create` riêng và quyền tối thiểu.
- [ ] Initial Access Token khác Registration Access Token.
- [ ] Initial Access Token chỉ mang scope cần thiết theo registrar policy.
- [ ] Registration Response được lưu an toàn.
- [ ] `registration_access_token` và `registration_client_uri` được xử lý theo cặp.
- [ ] Client sử dụng nguyên `registration_client_uri` OP đã trả.
- [ ] RAT chỉ gửi qua HTTPS trong Authorization header.
- [ ] RAT được lưu trong secret manager/vault, không ghi log.
- [ ] Client xác minh issuer và origin trước khi gửi RAT.
- [ ] Client xử lý RAT/secret rotation nếu response trả giá trị mới.
- [ ] Client chấp nhận stateless registration không có RAT/URI.
- [ ] OIDC Client Configuration Endpoint GET được kiểm thử.
- [ ] Metadata redirect URI, grant, scope, JWK và endpoint được validate.
- [ ] Custom metadata được allowlist và chuyển đổi hai chiều.
- [ ] RegisteredClientRepository và authorization state có persistence phù hợp.
- [ ] Không giả định OIDC Registration 1.0 định nghĩa PUT/DELETE.
- [ ] RFC 7592 chỉ được triển khai khi OP tuyên bố hỗ trợ extension.
- [ ] Deprovision vô hiệu RAT và xử lý token/grant liên quan theo policy.
- [ ] Có audit, metrics, redaction và runbook.

### Kiến thức cốt lõi

**Registration Access Token** là Bearer credential gắn với một client registration. Nó được dùng tại **Client Configuration Endpoint** thông qua URL `registration_client_uri` do OP trả. Client phải dùng URL nguyên vẹn và gửi RAT trong Authorization header qua TLS.

Trong OIDC Dynamic Client Registration 1.0, Client Configuration Endpoint định nghĩa GET để đọc metadata. **Initial Access Token** dùng để bảo vệ thao tác tạo registration; **Registration Access Token** dùng để đọc/quản lý registration sau khi tạo; **client_secret** dùng để xác thực confidential client tại Token Endpoint. Ba credential này có mục đích và phạm vi khác nhau.

Spring Authorization Server 1.5.8 cho phép bật Client Registration Endpoint, cấp registrar scope `client.create`/`client.read`, tạo registration và đọc lại cấu hình bằng RAT. Update/Delete thuộc RFC 7592 Experimental và phải được xác minh hoặc triển khai riêng. RAT cần được bảo vệ như một secret có quyền cao, có rotation, revocation, audit và kiểm thử phù hợp.

## Tài liệu tham khảo

- [OpenID Connect Dynamic Client Registration 1.0 — Client Configuration Endpoint](https://openid.net/specs/openid-connect-registration-1_0.html#ClientConfigurationEndpoint)
- [OpenID Connect Dynamic Client Registration 1.0 — Client Registration Response](https://openid.net/specs/openid-connect-registration-1_0.html#ClientRegistrationResponse)
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol (Experimental)](https://www.rfc-editor.org/rfc/rfc7592)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — OidcClientConfigurationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientConfigurationAuthenticationProvider.html)
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html)
