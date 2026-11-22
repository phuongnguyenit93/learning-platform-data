# Kiểm tra quyền sở hữu token trước khi thu hồi

Token Revocation Endpoint cho phép OAuth client yêu cầu Authorization Server vô hiệu hóa access token hoặc refresh token mà client không còn cần sử dụng. Endpoint này nhận một credential có giá trị bảo mật cao: token cần thu hồi. Vì vậy, trước khi thay đổi trạng thái authorization, Authorization Server phải xác minh client đang gọi endpoint và kiểm tra token có thực sự được cấp cho client đó hay không.

**Quyền sở hữu token trong ngữ cảnh revocation là quan hệ giữa token và OAuth client đã được Authorization Server cấp token đó.** Trong Spring Authorization Server, quan hệ này được lưu qua `OAuth2Authorization.registeredClientId`. Khi xử lý request, server so sánh giá trị này với ID nội bộ của `RegisteredClient` gắn với client đã xác thực. Nếu hai ID không khớp, server không được vô hiệu hóa token.

Việc kiểm tra này ngăn client A dùng Token Revocation Endpoint để làm mất hiệu lực token của client B. Nó cũng ngăn việc lấy `principalName`, subject, scope hoặc dữ liệu do request gửi lên làm bằng chứng sở hữu token.

Bài học thuộc chương **Revocation** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, với mục tiêu học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot.

Sau bài học, bạn có thể:

- Phân biệt client đã xác thực, client được cấp token và resource owner.
- Giải thích quan hệ giữa `RegisteredClient`, `OAuth2Authorization` và token được lưu.
- Kiểm tra quyền sở hữu token trước mọi thao tác thu hồi.
- Hiểu hành vi của Spring Authorization Server `OAuth2TokenRevocationAuthenticationProvider`.
- Xử lý token không tồn tại, token đã thu hồi và token thuộc client khác theo RFC 7009.
- Thiết kế chính sách cho public client, confidential client và quyền thu hồi quản trị.
- Kiểm thử ranh giới sở hữu, xử lý race condition, token family và khả năng lan truyền trạng thái revocation.

## 1. Vì sao phải kiểm tra quyền sở hữu token?

Giả sử một Authorization Server cấp token cho hai client:

- `orders-web` là ứng dụng đặt hàng.
- `billing-worker` là dịch vụ xử lý thanh toán.

Mỗi token được cấp trong một authorization gắn với client cụ thể. Nếu `orders-web` biết hoặc đoán được token của `billing-worker`, nó không được phép yêu cầu thu hồi token đó.

```mermaid
flowchart TD
    AS["Authorization Server"] --> A["Authorization A<br/>registeredClientId = orders-web"]
    AS --> B["Authorization B<br/>registeredClientId = billing-worker"]
    A --> TA["Access/Refresh token A"]
    B --> TB["Access/Refresh token B"]
    C["Client orders-web<br/>đã xác thực"] --> REQ["POST /oauth2/revoke<br/>token = token B"]
    REQ --> CHECK{"Token B có thuộc<br/>orders-web?"}
    TB --> CHECK
    CHECK -->|Không| DENY["Từ chối revocation<br/>không thay đổi token B"]
    CHECK -->|Có| REVOKE["Vô hiệu hóa token"]
```

Nếu server chỉ tìm token theo chuỗi rồi lập tức đánh dấu revoked, bất kỳ client nào gửi được token hợp lệ đều có thể gây gián đoạn phiên của client khác. Hành vi này tạo ra lỗ hổng authorization ở chính endpoint quản lý credential.

Kiểm tra ownership bảo đảm:

1. Request được gắn với một client đã được xác thực hoặc nhận diện hợp lệ theo loại client.
2. Token được tìm thấy trong authorization store.
3. Authorization chứa token đó được cấp cho chính client đang yêu cầu thu hồi.
4. Chỉ sau khi ownership hợp lệ, server mới thay đổi trạng thái token hoặc token family.

**Biết token không đồng nghĩa sở hữu token.** Một chuỗi bearer token có thể bị lộ qua log, telemetry, browser storage, proxy hoặc hệ thống khác. Token value là dữ liệu cần tra cứu, không phải bằng chứng client được phép thu hồi nó.

## 2. Phân biệt client, resource owner và token owner

OAuth có nhiều danh tính cùng xuất hiện trong một authorization. Không nên gộp chúng thành một khái niệm.

| Thành phần | Ý nghĩa | Vai trò trong kiểm tra ownership |
| --- | --- | --- |
| `RegisteredClient` | Client đã đăng ký tại Authorization Server. | Là danh tính client được dùng để đối chiếu token owner. |
| `OAuth2ClientAuthenticationToken` | Authentication biểu diễn client sau khi client authentication thành công. | Cung cấp `RegisteredClient` của requester. |
| `OAuth2Authorization` | Trạng thái authorization đã được cấp cho client/principal. | Chứa `registeredClientId`, `principalName`, grant, scopes và token metadata. |
| `principalName` | Danh tính resource owner hoặc client tùy grant. | Không phải khóa ownership của client. |
| Resource owner | Người dùng đã cấp quyền trong authorization flow. | Có thể quản lý consent/ủy quyền qua luồng riêng; không tự động là client gọi revocation endpoint. |
| Access/refresh token | Credential được phát hành trong authorization. | Phải được tra về authorization và client đã được cấp token. |

Ví dụ với authorization code:

- Resource owner đăng nhập là `alice`.
- Client là `orders-web`.
- Authorization được lưu với `registeredClientId` của `orders-web` và `principalName` là `alice`.
- Access token được cấp cho `orders-web` trong authorization của Alice.

`alice` là chủ thể đã ủy quyền truy cập, nhưng request tới RFC 7009 revocation endpoint được gửi bởi OAuth client. Server phải kiểm tra client được xác thực có khớp với client của authorization hay không.

Với `client_credentials`, `principalName` có thể biểu diễn client/service principal. Dù vậy, trường dùng để đối chiếu ownership vẫn là `registeredClientId`, vì nó liên kết authorization với registration cụ thể.

## 3. Ownership được lưu trong mô hình Spring Authorization Server

`OAuth2Authorization` chứa các dữ liệu quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| `id` | ID duy nhất của authorization. |
| `registeredClientId` | ID nội bộ của `RegisteredClient` đã được cấp authorization. |
| `principalName` | Tên principal (resource owner hoặc client). |
| `authorizationGrantType` | Grant đã dùng để tạo authorization. |
| `authorizedScopes` | Các scope được cấp. |
| `tokens` | Access token, refresh token, authorization code và metadata tương ứng. |
| `attributes` | Thông tin bổ sung của authorization flow. |

Trong đó, `registeredClientId` là khóa liên kết ownership cần kiểm tra. Nó là giá trị tương ứng với `RegisteredClient.getId()`, **không phải** `RegisteredClient.getClientId()`.

Ví dụ:

```java
RegisteredClient registeredClient = RegisteredClient
    .withId("client-record-91")
    .clientId("orders-web")
    .clientSecret("{bcrypt}...")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://orders.example.com/login/oauth2/code/app")
    .scope("orders.read")
    .build();

OAuth2Authorization authorization = OAuth2Authorization
    .withRegisteredClient(registeredClient)
    .principalName("alice")
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizedScopes(Set.of("orders.read"))
    .build();
```

Trong ví dụ, authorization được liên kết với internal ID `client-record-91`. Khi client xác thực là `orders-web`, server lấy `RegisteredClient` tương ứng và so sánh `registeredClient.getId()` với `authorization.getRegisteredClientId()`.

Không so sánh nhầm:

- `registeredClient.getId()` là khóa registration nội bộ.
- `registeredClient.getClientId()` là identifier mà client dùng trong giao thức.
- `authorization.getPrincipalName()` là principal name, không phải client ID.
- `authorization.getAuthorizedScopes()` là quyền được cấp, không phải bằng chứng sở hữu.

Hai client có thể cùng yêu cầu một scope hoặc cùng có một resource owner. Điều đó không làm authorization của họ trở thành một.

## 4. Luồng xử lý Token Revocation Endpoint

Theo RFC 7009, client gửi HTTP POST tới revocation endpoint với token cần thu hồi và `token_type_hint` tùy chọn. Request cũng chứa thông tin xác thực client theo loại client.

Ví dụ:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Authorization: Basic b3JkZXJzLXdlYjpzZWNyZXQ=
Content-Type: application/x-www-form-urlencoded

token=<TOKEN_VALUE>&token_type_hint=refresh_token
```

Đây là request minh họa; token và credential phải được bảo vệ, không ghi vào log. Endpoint phải dùng HTTPS vì request truyền credential có giá trị bảo mật.

Quy trình xử lý:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant F as Revocation Endpoint Filter
    participant P as Revocation AuthenticationProvider
    participant S as OAuth2AuthorizationService

    C->>F: POST token + token_type_hint
    F->>P: OAuth2TokenRevocationAuthenticationToken
    P->>P: Xác thực/nhận diện client
    P->>S: findByToken(token)
    S-->>P: OAuth2Authorization hoặc không tìm thấy
    P->>P: So sánh registeredClientId
    alt Client sở hữu token
        P->>P: Kiểm tra token và trạng thái
        P->>S: Lưu authorization đã invalidate
        P-->>F: Revocation thành công
        F-->>C: HTTP 200
    else Token không tồn tại hoặc đã không còn hiệu lực
        P-->>F: Xử lý no-op theo protocol
        F-->>C: HTTP 200
    else Token thuộc client khác
        P-->>F: Từ chối ownership
        F-->>C: OAuth error
    end
```

Các bước cần được thực hiện theo thứ tự:

1. Parse request và lấy `token`, `token_type_hint`.
2. Xác thực client hoặc nhận diện public client theo cấu hình.
3. Tìm authorization chứa token.
4. Đối chiếu client requester với `registeredClientId` của authorization.
5. Kiểm tra token được tìm thấy và trạng thái của token.
6. Chỉ khi ownership hợp lệ mới invalidate token và lưu authorization.
7. Trả response theo RFC 7009 và chính sách lỗi của endpoint.

**Không được invalidate trước rồi mới kiểm tra client.** Ownership check phải đứng trước mọi side effect như đánh dấu token invalidated, revoke refresh token liên quan, vô hiệu hóa authorization hoặc phát event thu hồi.

## 5. Quy tắc ownership theo RFC 7009

RFC 7009 `2.1 quy định Authorization Server xác thực credential của confidential client, sau đó xác minh token có được cấp cho client đang yêu cầu thu hồi hay không. Nếu validation thất bại, request bị từ chối. Phần Security Considerations cũng nêu token bị thu hồi phải thuộc client gửi request.

### 5.1. Confidential client

Confidential client phải xác thực bằng phương thức đã đăng ký, ví dụ:

- `client_secret_basic`
- `client_secret_post`
- `private_key_jwt`
- `client_secret_jwt`
- `tls_client_auth`
- `self_signed_tls_client_auth`

Sau khi authentication thành công, server lấy `RegisteredClient` từ authentication principal. Không dùng `client_id` trong body làm danh tính đã xác thực nếu client authentication filter đã cung cấp principal đáng tin cậy.

### 5.2. Public client

Public client không giữ được credential bí mật có thể xác thực bằng `client_id` theo cơ chế public client được RFC 7009 cho phép. Authorization Server vẫn phải kiểm tra `client_id` hợp lệ và đối chiếu token với registration của public client đó.

`client_id` không phải secret. Việc một bên biết public client ID không cho phép bên đó thu hồi token của confidential client hoặc public client khác.

Public client có thể cần PKCE ở authorization code flow để bảo vệ authorization code. PKCE không thay thế ownership check tại revocation endpoint; server vẫn phải liên kết token với đúng `RegisteredClient`.

### 5.3. Client credentials sai và token không thuộc client

Cần phân biệt hai tình huống:

| Tình huống | Ý nghĩa | Xử lý |
| --- | --- | --- |
| Client authentication thất bại | Credential sai, client không hợp lệ hoặc client không được phép dùng phương thức đã gửi. | Từ chối authentication, thường là `401 invalid_client` theo OAuth client authentication. |
| Client xác thực hợp lệ nhưng token thuộc client khác | Requester không có quyền thu hồi authorization của token đó. | Không invalidate token; từ chối ownership theo policy/implementation. |
| Token không tồn tại hoặc không tìm thấy | Server không có authorization tương ứng. | Trả `200 OK` theo RFC 7009, không tiết lộ token có tồn tại hay không. |
| Token đã bị thu hồi/hết hạn | Token không còn active. | Xử lý idempotent; response thành công không làm token active trở lại. |

Trong Spring Authorization Server, provider revocation mặc định kiểm tra client đã xác thực và so sánh internal ID của `RegisteredClient` với `OAuth2Authorization.registeredClientId`. Khi client khác sở hữu token, provider mặc định hiện hành từ chối với OAuth error `invalid_client`. Hãy xác minh hành vi cụ thể theo phiên bản thư viện mà ứng dụng đang dùng.

## 6. token_type_hint chỉ là gợi ý tra cứu

RFC 7009 định nghĩa hai giá trị phổ biến:

- `access_token`
- `refresh_token`

Client có thể gửi hint để Authorization Server tối ưu việc tìm token. Hint không phải bằng chứng rằng token thật sự thuộc loại được khai báo.

Nếu không tìm được token theo hint, server phải mở rộng tìm kiếm qua các loại token được hỗ trợ. Server cũng có thể bỏ qua hint nếu có thể tự nhận diện token.

Ví dụ client gửi:

```http
POST /oauth2/revoke
Content-Type: application/x-www-form-urlencoded

token=<TOKEN_VALUE>&token_type_hint=access_token
```

Nếu giá trị thực tế là refresh token, server không được mặc định kết luận token không tồn tại chỉ vì tìm kiếm access token thất bại.

Trong Spring Authorization Server, `OAuth2AuthorizationService.findByToken(token, tokenType)` là điểm truy vấn authorization. Provider mặc định có thể tìm theo token mà không giới hạn loại (`tokenType` là `null`), qua đó tránh phụ thuộc hoàn toàn vào hint. Khi triển khai persistence riêng, phải bảo đảm fallback tương đương RFC 7009.

Không dùng `token_type_hint` để chọn client hoặc thay ownership check. Client không thể biến token của client khác thành token của mình bằng cách khai một hint khác.

## 7. Thuật toán kiểm tra ownership trước khi invalidate

Có thể mô tả logic bằng pseudocode:

```text
request = parseRevocationRequest()
requester = authenticateOrIdentifyClient(request)

authorization = authorizationService.findByToken(
    request.token,
    resolveTokenTypeHint(request.token_type_hint)
)

if authorization == null:
    return HTTP 200

if authorization.registeredClientId != requester.registeredClient.id:
    reject ownership
    do not mutate authorization
    return OAuth error

token = authorization.findToken(request.token)

if token == null or token is not active:
    return HTTP 200

updatedAuthorization = invalidateAccordingToPolicy(
    authorization,
    token
)

authorizationService.save(updatedAuthorization)
return HTTP 200
```

Một số điểm phải giữ nguyên khi chuyển pseudocode thành code:

- `requester` lấy từ client authentication đã thành công.
- `authorization.registeredClientId` là ID nội bộ của registration.
- Token được tra từ authorization store, không suy đoán owner từ chuỗi token.
- Nếu không tìm thấy token, không trả lỗi tiết lộ token có tồn tại.
- Nếu tìm thấy token nhưng client khác sở hữu, không gọi `invalidate(...)`, không lưu authorization và không phát side effect.
- Nếu token đã invalidated hoặc expired, request có thể được xử lý như thao tác idempotent.
- Nếu token active và owner khớp, áp dụng chính sách revoke token và token liên quan.

### 7.1. So sánh internal ID, không so sánh principalName

Ví dụ đúng về nguyên tắc:

```java
boolean ownsAuthorization(
        OAuth2ClientAuthenticationToken clientPrincipal,
        OAuth2Authorization authorization) {

    RegisteredClient requester = clientPrincipal.getRegisteredClient();

    return requester != null
        && requester.getId().equals(authorization.getRegisteredClientId());
}
```

Đây là helper minh họa cho ownership predicate. Trong endpoint thật, chỉ gọi nó sau khi client principal đã được xác thực; không nhận `OAuth2ClientAuthenticationToken` do request tự tạo.

Ví dụ sai:

```java
// Sai: hai client có thể cùng có principalName.
if (authorization.getPrincipalName().equals(requester.getName())) {
    authorizationService.save(authorization.invalidate(token));
}
```

`principalName` thường là resource owner trong authorization code flow. Alice có thể cấp quyền cho nhiều client khác nhau; việc cùng `principalName = alice` không cho phép client A thu hồi token của client B.

### 7.2. Không dùng scope làm ownership

Hai client có thể cùng được cấp `orders.read`. Scope mô tả quyền truy cập tài nguyên, không phải quyền quản lý token. Không viết logic kiểu:

```java
// Sai: cùng scope không chứng minh cùng client.
if (authorization.getAuthorizedScopes().contains("orders.read")) {
    revoke(token);
}
```

Ownership phải dựa trên quan hệ authorization-client đã lưu.

## 8. Hành vi mặc định trong Spring Authorization Server

Spring Authorization Server cung cấp Token Revocation Endpoint qua `OAuth2TokenRevocationEndpointConfigurer`. Filter endpoint chuyển HTTP request thành `OAuth2TokenRevocationAuthenticationToken`, sau đó provider xử lý authentication và revocation.

Các thành phần liên quan:

| Thành phần | Trách nhiệm |
| --- | --- |
| `OAuth2TokenRevocationEndpointFilter` | Nhận request HTTP và điều phối xử lý endpoint. |
| `OAuth2TokenRevocationAuthenticationConverter` | Chuyển request parameters thành authentication request object. |
| `OAuth2TokenRevocationAuthenticationToken` | Mang token và token type hint trong quá trình xử lý. |
| `OAuth2TokenRevocationAuthenticationProvider` | Xác thực requester, tìm authorization, kiểm tra client ownership và invalidate token. |
| `OAuth2AuthorizationService` | Tra cứu và lưu authorization/token state. |
| `RegisteredClientRepository` | Cung cấp client registration đã được xác thực. |

Provider mặc định thực hiện logic ownership quan trọng:

1. Lấy authenticated client từ revocation authentication context.
2. Lấy `RegisteredClient` tương ứng.
3. Tìm `OAuth2Authorization` chứa token.
4. So sánh `RegisteredClient.getId()` với `OAuth2Authorization.getRegisteredClientId()`.
5. Nếu khác nhau, từ chối bằng OAuth error thay vì invalidate token.
6. Nếu trùng, tìm token metadata và invalidate token tương ứng.
7. Lưu authorization đã cập nhật.

Điều này có nghĩa ứng dụng dùng provider mặc định và `OAuth2AuthorizationService` chuẩn đã có kiểm tra ownership cơ bản. Tuy nhiên, ứng dụng vẫn phải bảo đảm persistence lookup chính xác, client authentication đúng và không có custom provider khác bỏ qua điều kiện ownership.

### 8.1. Cấu hình endpoint và extension point

Có thể cấu hình endpoint qua Authorization Server configurer:

```java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.tokenRevocationEndpoint(revocation ->
                revocation
                    .revocationRequestConverters(converters -> {
                        // Giữ converter mặc định hoặc thêm converter
                        // theo protocol extension đã được kiểm soát.
                    })
                    .authenticationProviders(providers -> {
                        // Giữ provider mặc định có ownership check.
                        // Chỉ thay đổi khi đã triển khai và kiểm thử
                        // đầy đủ authentication + ownership policy.
                    })
            )
        );

    return http.build();
}
```

Ví dụ minh họa extension point của endpoint. Trong cấu hình production, bảo đảm các filter chain khác không vô tình cho phép truy cập endpoint revocation mà bỏ qua client authentication. Không xóa provider mặc định nếu custom provider thay thế chưa thực hiện đầy đủ các kiểm tra tương đương.

### 8.2. Khi nào cần custom AuthenticationProvider?

Chỉ cần custom provider nếu nghiệp vụ có yêu cầu ngoài hành vi mặc định, ví dụ:

- Có mô hình delegated client với quan hệ parent/child đã được quản trị rõ.
- Có quyền revocation quản trị được cấp riêng.
- Cần audit hoặc cascade revocation theo authorization family.
- Có authorization store tùy chỉnh cần transaction hoặc lookup đặc biệt.

Nếu thêm quyền delegated, phải kiểm tra policy rõ ràng, chẳng hạn client B được ủy quyền thu hồi token của client A trong một tenant hoặc một nhóm authorization cụ thể. Không mở rộng bằng điều kiện lỏng như cùng principal name, cùng tenant header do request gửi hoặc cùng scope.

## 9. Token không tồn tại, token đã thu hồi và token thuộc client khác

Ba tình huống này có mục tiêu bảo mật và response khác nhau.

| Tình huống | Có tìm thấy authorization? | Có ownership? | Có invalidate? | Response thường gặp |
| --- | --- | --- | --- | --- |
| Token không tồn tại | Không | Không xác định | Không | `200 OK` |
| Token đã hết hạn/đã revoke | Có thể có | Có thể khớp | Không cần thay đổi | `200 OK` |
| Token active của requester | Có | Có | Có | `200 OK` |
| Token active của client khác | Có | Không | **Không** | OAuth error theo RFC/implementation; SAS mặc định dùng `invalid_client` |

RFC 7009 trả `200 OK` khi token được thu hồi thành công hoặc token gửi lên không hợp lệ/không tồn tại. Điều này giúp client không phải phân biệt token đã hết hạn, đã revoke hay chưa từng tồn tại.

Token thuộc client khác là trường hợp ownership validation thất bại, được RFC 7009 `2.1 mô tả là request phải bị từ chối và client được thông báo lỗi. Không được gộp trường hợp này với token không tồn tại rồi vô tình revoke token của client khác.

Không trả response body chứa client ID owner, principal name, scopes, token expiration hoặc lý do nội bộ chi tiết. Error response phải tuân theo OAuth endpoint contract và không tiết lộ nhiều dữ liệu hơn mức cần thiết.

## 10. Thu hồi token liên quan trong cùng authorization

Một authorization có thể chứa access token và refresh token. Revocation policy phải xác định khi thu hồi một token thì các token liên quan có bị vô hiệu hóa không.

RFC 7009 `2.1 quy định:

- Khi token được gửi là refresh token và AS hỗ trợ thu hồi access token, AS **SHOULD** invalidate các access token dựa trên cùng authorization grant.
- Khi token được gửi là access token, AS **MAY** revoke refresh token tương ứng.
- Policy có thể revoke thêm token liên quan hoặc authorization grant nếu thiết kế hệ thống yêu cầu.

Đây là cascade policy sau khi ownership đã được xác minh. Không được cascade sang authorization khác chỉ vì cùng resource owner, cùng client name hoặc cùng scope.

```mermaid
flowchart TD
    REQUEST["Revocation request"] --> OWNER{"Requester owns authorization?"}
    OWNER -->|No| STOP["Không thay đổi token nào"]
    OWNER -->|Yes| TYPE{"Token được gửi"}
    TYPE -->|Refresh token| REF["Invalidate refresh token"]
    REF --> ACCESS["Theo RFC: SHOULD invalidate<br/>access tokens cùng grant"]
    TYPE -->|Access token| AT["Invalidate access token"]
    AT --> MAY["Theo policy: MAY invalidate<br/>refresh token tương ứng"]
    ACCESS --> SAVE["Lưu authorization atomically"]
    MAY --> SAVE
```

Trong source Spring Authorization Server hiện hành, provider mặc định tìm authorization bằng `findByToken(token, null)`, kiểm tra ownership rồi gọi `invalidate(...)` cho token được tìm thấy. Vì vậy không nên suy luận rằng mọi phiên bản/cấu hình tự động cascade sang toàn bộ token family. RFC 7009 khuyến nghị (SHOULD) thu hồi các access token cùng grant khi refresh token bị thu hồi và AS hỗ trợ access-token revocation. Hãy kiểm tra đúng phiên bản đang dùng và viết integration test xác nhận access token liên quan cũng bị vô hiệu hóa; nếu policy cần cascade mà implementation không làm, bổ sung xử lý sau ownership check trong cùng transaction.

## 11. Race condition và tính nhất quán của authorization store

Ownership check phải được thực hiện trong một transaction hoặc cơ chế nhất quán phù hợp với việc cập nhật token.

Ví dụ hai request đồng thời:

- Request A từ client đúng gửi token để revoke.
- Request B từ một tiến trình khác thực hiện refresh token hoặc cập nhật authorization.
- Nếu hai thao tác đọc/ghi không được phối hợp, có thể xảy ra lost update hoặc token mới vẫn được phát hành sau khi authorization đã bị thu hồi.

Khuyến nghị:

1. Dùng transaction cho lookup, ownership check và persistence update khi storage hỗ trợ.
2. Cân nhắc optimistic locking/version column hoặc row-level locking khi có concurrent refresh/revoke.
3. Không thực hiện ownership check trên một replica stale rồi ghi vào primary mà không kiểm tra lại version.
4. Publish revocation event sau khi transaction commit; consumer phải xử lý idempotent.
5. Đồng bộ cache/token state ở Resource Server theo SLA.
6. Với refresh-token rotation, bảo đảm refresh provider không tái sử dụng authorization state đã bị revoke.

Nếu ownership không khớp, transaction không được ghi bất kỳ thay đổi token nào. Không phát event revocation hoặc xóa cache cho authorization thuộc client khác.

## 12. JWT, opaque token và hiệu lực revocation

Ownership check được thực hiện ở Authorization Server. Khả năng Resource Server nhận biết token đã bị thu hồi phụ thuộc token format.

| Token format | Resource Server xác minh | Tác động của revocation |
| --- | --- | --- |
| Opaque/reference token | Thường gọi introspection hoặc tra trạng thái tập trung. | Có thể phản ánh trạng thái revoked nhanh, phụ thuộc cache và consistency. |
| JWT self-contained | Xác minh chữ ký và claims offline. | JWT đã phát hành có thể tiếp tục được chấp nhận đến `exp` nếu API không kiểm tra denylist/introspection. |

Đối với JWT offline, chỉ cập nhật `OAuth2Authorization` ở AS không làm mọi Resource Server tự biết token đã revoked. Nếu yêu cầu thu hồi gần như tức thì, cần cơ chế bổ sung như:

- Short-lived access token.
- Token introspection hoặc central authorization check.
- Denylist theo `jti` hoặc token identifier đã chuẩn hóa.
- Event-driven cache invalidation có bảo đảm delivery/ordering.
- Token version hoặc authorization version được Resource Server kiểm tra.

Không dùng raw token làm cache key/log key nếu không cần thiết. Với JWT, `jti` chỉ hữu ích nếu hệ thống có cơ chế tra cứu/denylist tương ứng; claim tồn tại tự nó không tạo revocation.

## 13. Bảo vệ endpoint khỏi token guessing và abuse

Revocation endpoint nhận token từ client nên có thể bị lạm dụng để thử đoán token hoặc gây tải lên authorization store.

Các biện pháp cần cân nhắc:

- Yêu cầu client authentication/identification đúng loại.
- Dùng HTTPS và endpoint URI lấy từ metadata/documentation đáng tin cậy.
- Không nhận token qua query string; dùng POST body `application/x-www-form-urlencoded`.
- Không ghi raw token, refresh token hoặc client secret vào application log, tracing hay error message.
- Rate limit theo client, IP và tín hiệu abuse phù hợp; tránh chỉ rate limit theo token vì attacker có thể gửi token ngẫu nhiên.
- Dùng token có entropy cao và storage lookup có index phù hợp.
- Giới hạn kích thước token input và số lượng lookup fallback.
- Không cho phép token type hint tùy ý kích hoạt truy vấn không giới hạn.
- Trả response không tiết lộ token không tồn tại hay token thuộc client nào.
- Audit sự kiện revocation bằng authorization ID, client ID đã xác thực, loại token và kết quả; tránh lưu credential thô.

RFC 7009 lưu ý revocation endpoint có thể bị dùng để đoán token và gây denial of service. Ownership check là điều kiện cần, nhưng cần kết hợp rate limiting và bảo vệ persistence layer.

## 14. Kiểm thử quyền sở hữu token

Test ownership phải kiểm tra cả kết quả HTTP và **trạng thái authorization sau request**. Chỉ assert response code là chưa đủ; một endpoint có thể trả lỗi nhưng đã lỡ invalidate token trước đó.

### 14.1. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Client A xác thực và revoke access token của A | Token A bị invalidated. |
| Client A xác thực và revoke refresh token của A | Refresh token A bị invalidated; cascade access token theo policy/RFC. |
| Client A gửi token của client B | Ownership bị từ chối; authorization B không thay đổi. |
| Client B gửi token của client A | Ownership bị từ chối; authorization A không thay đổi. |
| Client secret sai | `invalid_client`; không lookup hoặc mutate token theo requester chưa xác thực. |
| Public client gửi đúng client_id và token của chính nó | Request được xử lý theo policy public client. |
| Public client gửi token của client khác | Ownership mismatch; không revoke token khác. |
| Token không tồn tại | `200 OK`; không tiết lộ token có tồn tại. |
| Token đã revoke | `200 OK` theo xử lý idempotent. |
| Token hết hạn | Không active; response không tiết lộ trạng thái nội bộ. |
| `token_type_hint` đúng | Tra cứu tối ưu đúng loại token. |
| `token_type_hint` sai nhưng token thuộc loại khác | Server fallback search theo RFC 7009. |
| Cùng principalName nhưng hai client khác nhau | Không được xem là cùng owner. |
| Cùng scope nhưng hai client khác nhau | Không được xem là cùng owner. |
| Token refresh rotation vừa xảy ra | Revoke và refresh có kết quả nhất quán theo transaction policy. |
| Hai request revoke đồng thời cùng token | Kết quả idempotent; không tạo trạng thái active trở lại. |
| Token thuộc tenant khác nhưng cùng client ID | Chỉ revoke nếu authorization ownership/policy thực sự cho phép; không tin tenant header. |
| Custom provider được đăng ký | Vẫn giữ client authentication và ownership validation. |
| Database lookup trả authorization sai token do index bug | Test phát hiện token value phải khớp token metadata thực tế trước khi mutate. |
| JWT offline sau revocation | Resource Server xử lý theo TTL/denylist/introspection policy đã thiết kế. |

### 14.2. Integration test với hai client

Chuẩn bị:

- Client A: `orders-web`.
- Client B: `billing-worker`.
- Authorization A chứa token A và `registeredClientId` của A.
- Authorization B chứa token B và `registeredClientId` của B.

Các bước:

1. Xác thực client A.
2. Gửi token A tới revocation endpoint.
3. Kiểm tra token A được đánh dấu invalidated.
4. Tạo lại authorization B hoặc dùng token B còn active.
5. Vẫn dùng client A gửi token B tới endpoint.
6. Kiểm tra request bị từ chối theo ownership policy.
7. Đọc lại authorization B và assert access token/refresh token vẫn active.
8. Xác thực client B và gửi token B.
9. Kiểm tra token B được invalidated.
10. Kiểm tra audit không chứa raw token.

### 14.3. Test không dựa vào principalName

Tạo hai authorization:

- Authorization A: `registeredClientId = client-A`, `principalName = alice`.
- Authorization B: `registeredClientId = client-B`, `principalName = alice`.

Sau đó xác thực client A và gửi token B. Kết quả phải là ownership mismatch dù cả hai authorization cùng `principalName = alice`.

Test này phát hiện lỗi phổ biến là dùng resource owner name để thay thế client ownership.

## 15. Checklist triển khai

- [ ] Revocation endpoint chỉ nhận POST qua HTTPS.
- [ ] Client được xác thực/nhận diện đúng theo confidential hoặc public client policy.
- [ ] Requester lấy từ authenticated client principal, không lấy từ body/header tùy ý.
- [ ] Token được tra cứu trong `OAuth2AuthorizationService`.
- [ ] Ownership check so sánh `RegisteredClient.getId()` với `OAuth2Authorization.getRegisteredClientId()`.
- [ ] Ownership check chạy trước mọi `invalidate`, `save`, event hoặc cache mutation.
- [ ] Không dùng `principalName`, scope, subject DN hoặc tenant header làm bằng chứng ownership.
- [ ] Token không tồn tại và token đã revoked được xử lý idempotent theo RFC 7009.
- [ ] Token thuộc client khác bị từ chối; authorization của owner không thay đổi.
- [ ] `token_type_hint` chỉ dùng để tối ưu lookup và có fallback theo RFC.
- [ ] Cascade policy cho access/refresh token cùng authorization được xác định rõ.
- [ ] Custom provider giữ nguyên client authentication, ownership check và protocol response semantics.
- [ ] Transaction/locking ngăn race giữa revoke và refresh.
- [ ] Cache/introspection/JWT Resource Server có chính sách lan truyền revocation rõ.
- [ ] Rate limit và giới hạn lookup bảo vệ endpoint khỏi token guessing/DoS.
- [ ] Log/audit không lưu raw access token, refresh token hoặc client secret.
- [ ] Integration test bao gồm client A revoke token B và xác nhận token B vẫn active.

**Ghi nhớ:** Authorization Server chỉ được thu hồi token sau khi xác minh requester là client đã được cấp token đó. Trong Spring Authorization Server, hãy dùng `OAuth2Authorization.registeredClientId` và internal ID của `RegisteredClient` làm căn cứ ownership. Token value chỉ giúp tìm authorization; `principalName`, scope và dữ liệu request không thay thế được phép kiểm tra này.

**Tài liệu tham khảo:**

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): `2.1 yêu cầu kiểm tra client và token ownership; `2.2 quy định response; `5 bàn về token guessing.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Revocation Endpoint, converter, authentication provider và response handler.
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService` và token state.
- [OAuth2TokenRevocationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationProvider.html): provider mặc định cho revocation.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication và các loại client.

