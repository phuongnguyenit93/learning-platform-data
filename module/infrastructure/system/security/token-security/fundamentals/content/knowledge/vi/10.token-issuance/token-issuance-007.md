# Gắn scope và audience được phép

Giả sử ứng dụng `shop-web` xin access token để **đọc đơn hàng**. Client gửi yêu cầu:

~~~text
scope    = orders:read payments:refund
resource = https://api.example.com/payments
~~~

Nhưng `shop-web` chỉ được đăng ký cho Orders API và người dùng không được hoàn tiền. **Authorization Server không được sao chép các giá trị client gửi vào token.** Nó phải kiểm client, grant, resource, người dùng hoặc service principal, consent và chính sách rồi mới quyết định **scope được cấp** và **audience được phép nhận token**.

Nếu AS phát hành access token có `aud=payments-api`, `scope=payments:refund` chỉ vì client yêu cầu, nó đã trao quyền ngoài chính sách. Chữ ký JWT vẫn có thể hợp lệ về mật mã nhưng **quyết định phát hành đã sai**.

Bài thuộc chương **Token issuance** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, tập trung cách gắn scope và audience khi phát hành access token trong OAuth 2.0/OIDC, áp dụng với JWT và opaque token, cùng các giới hạn về xác thực, phân quyền, refresh token, tenant, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **scope client yêu cầu**, **scope được phép**, **scope thực tế AS cấp** và **permission mà Resource Server kiểm trên tài nguyên**.
2. Phân biệt **resource indicator**, **claim `aud`** và **`client_id`**.
3. Xây dựng chính sách cấp token theo client registration, grant type, principal, resource, consent, tenant và rủi ro.
4. Mô tả cách gắn scope và audience trong Authorization Code + PKCE, Client Credentials và Refresh Token Grant.
5. Thiết kế cách phát hành JWT/opaque access token và kiểm lại ở Resource Server.
6. Ngăn leo thang scope, token substitution, audience quá rộng và token dùng sai API.
7. Đề xuất bộ kiểm thử và tiêu chí vận hành cho một hệ thống cấp token an toàn.

## 2. Ranh giới trách nhiệm: ai yêu cầu và ai quyết định?

| Thành phần | Trách nhiệm | Giới hạn tin cậy |
|---|---|---|
| **OAuth Client** | Gửi yêu cầu scope và resource để xin access token. | Giá trị request là đầu vào **chưa được phê duyệt**, không tự tạo quyền. |
| **Resource Owner / End User** | Xác thực và có thể đồng ý ủy quyền theo luồng phù hợp. | Consent không vượt qua client policy hay quyền nghiệp vụ. |
| **Authorization Server (AS)** | Kiểm client/grant/policy rồi phát hành access token với scope, audience và TTL đã chọn. | Phải cấp token trong giới hạn thẩm quyền; không tin khai báo từ client vô điều kiện. |
| **OpenID Provider (OP)** | Xác thực theo OIDC và phát hành ID token cho OIDC Client. | ID token không thay access token của API. |
| **Resource Server (RS)** | Nhận access token, xác minh issuer, audience, hiệu lực, scope và kiểm quyền trên resource. | Token hợp lệ chưa chứng minh request được truy cập mọi tài nguyên. |
| **Policy/Permission Store** | Lưu quyền client, scope, resource, membership, trạng thái và chính sách. | Cần bảo vệ toàn vẹn, cập nhật và cơ chế fail closed. |

Có hai phép quyết định độc lập:

- **AS tại thời điểm phát hành:** “Client/grant/principal này được nhận token **cho API nào**, với **scope nào**?”
- **RS tại thời điểm sử dụng:** “Access token có hợp lệ cho **API này** và có quyền thực hiện **request cụ thể** không?”

AS không nhất thiết biết đơn hàng 42 có thuộc người dùng hay tenant hiện tại không. Vì vậy, AS cấp `orders:read` vẫn không thay thế object-level authorization ở Orders API.

## 3. Scope được yêu cầu khác scope được cấp

**Scope** là chuỗi định danh một tập phạm vi ủy quyền theo chính sách OAuth. Ví dụ `orders:read`, `orders:create` và `payments:refund` do sản phẩm định nghĩa, không có ngữ nghĩa phổ quát áp dụng cho mọi API.

Quá trình xử lý cần phân biệt:

| Giai đoạn | Ví dụ | Ý nghĩa |
|---|---|---|
| **Requested scope** | `orders:read orders:create` | Client mong muốn có hai phạm vi. |
| **Client allowed scope** | `orders:read orders:create` | Scope mà client registration cho phép xin đối với API. |
| **Grant/principal authorized scope** | `orders:read` | Quyền theo grant, người dùng/consent và chính sách ở ngữ cảnh này. |
| **Issued scope** | `orders:read` | Scope thực tế AS cấp và RS có thể kiểm sau khi xác minh token. |

Cách nhìn này không bắt buộc phải có bốn cột trong database. Nó giúp tránh lỗi **gán `requestedScopes` thẳng cho `issuedScopes`**.

### 3.1. Hai cách xử lý yêu cầu vượt scope

Nếu client xin `orders:read orders:admin` nhưng không được phép `orders:admin`, AS có thể:

1. **Từ chối** do scope không hợp lệ/vượt phạm vi, theo mã lỗi OAuth phù hợp như `invalid_scope`.
2. **Cấp phạm vi hẹp hơn** nếu grant và chính sách cho phép, ví dụ chỉ `orders:read`. Khi phạm vi được cấp khác phạm vi client yêu cầu, token response phải phản ánh **scope thực tế** theo OAuth 2.0.

Không có quy tắc rằng AS luôn phải tự động giảm scope. Với thao tác nhạy cảm, từ chối rõ ràng có thể dễ hiểu và an toàn hơn. Quan trọng là **không bao giờ cấp vượt quyền**.

### 3.2. Scope không phải quyền trên từng bản ghi

Một token `scope=orders:read` chưa cho phép đọc:

- Đơn hàng của người dùng khác.
- Đơn hàng thuộc tenant khác.
- Đơn hàng đang được bảo vệ theo một chính sách nghiệp vụ riêng.
- Mọi API có chữ `orders` trong tên.

RS vẫn phải kiểm **subject, tenant, action, resource, trạng thái và policy**. Scope giới hạn khả năng gọi một nhóm chức năng, không thay ownership, RBAC, ABAC hay ReBAC.

### 3.3. Nếu client không gửi scope?

AS áp dụng **default scope được cấu hình và đã cho phép** hoặc từ chối theo grant/chính sách. Không được coi “không chỉ định scope” là “cấp mọi scope”. Với endpoint yêu cầu scope cụ thể, Resource Server phải từ chối token không có bằng chứng scope phù hợp.

Trong OIDC, `openid` kích hoạt ngữ cảnh OpenID Connect; nó không tự là permission đọc đơn hàng. `offline_access` liên quan yêu cầu quyền truy cập offline theo quy tắc OIDC, không phải quyền gọi mọi API.

## 4. Audience: token thực sự dành cho ai?

`aud` (*audience*) là định danh **bên nhận mà token hướng tới**. Trong JWT, nó có thể là một chuỗi hoặc một mảng chuỗi (RFC 7519). Với access token OAuth, bên nhận thường là Resource Server tương ứng.

~~~text
Issuer:          https://login.example.com
Client ID:       shop-web
Subject:         user-742
Orders audience: orders-api
Payments aud:    payments-api
Requested scope: orders:read
~~~

Các claim có mục đích khác nhau:

| Claim | Đại diện cho | Không được nhầm với |
|---|---|---|
| `iss` | Nguồn phát hành token | Client hoặc API nhận token |
| `sub` | Principal/token subject | Client ID hoặc scope |
| `client_id` | OAuth client gắn với token theo profile | Bên nhận access token |
| `aud` | API/bên nhận token | Scope hoặc quyền tenant |
| `scope` | Phạm vi được cấp | Quyền đối với tất cả bản ghi |
| `exp` | Thời điểm hết hiệu lực | Trạng thái chưa bị thu hồi |

**Token `aud=payments-api` không được dùng ở `orders-api`**, dù cùng AS ký và scope có thể chứa `orders:read`. Ngược lại, token aud đúng nhưng thiếu scope cũng không được thực hiện action không được cấp.

### 4.1. Audience là định danh logic, không nhất thiết là URL HTTP

Ví dụ hệ thống có:

~~~text
Endpoint mạng:      https://api.example.com/v2/orders
Resource indicator: https://api.example.com/orders
Audience token:     orders-api
~~~

Ba giá trị có thể khác nhau nếu AS và RS thống nhất mapping. Đổi DNS, hostname, gateway hay API version không nhất thiết đòi thay audience.

Phép kiểm audience phải dựa trên **danh sách định danh chính xác đã khai báo**, có phân biệt hoa/thường. Tránh `startsWith`, `contains` hoặc wildcard, vì chúng có thể chấp nhận token dành cho resource khác.

### 4.2. Không cấp audience tùy ý theo request

AS nên xác định:

1. Resource được yêu cầu có nằm trong danh mục API do AS quản lý không?
2. Client và grant hiện tại có được xin resource đó không?
3. Scope requested có thuộc resource đó không?
4. Principal/consent/policy có cho phép quyền tương ứng không?
5. Audience canonical được phát hành là định danh nào?

Nếu không thể resolve hoặc client không được phép xin resource, AS phải **từ chối thay vì tự đưa chuỗi request vào `aud`**.

## 5. Resource Indicators trong OAuth 2.0

**RFC 8707 — Resource Indicators for OAuth 2.0** cung cấp tham số `resource` để client chỉ định Resource Server mục tiêu theo các grant/endpoint được AS hỗ trợ.

Ví dụ authorization request (xuống dòng để đọc):

~~~http
GET /authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20orders%3Aread&
  resource=https%3A%2F%2Fapi.example.com%2Forders&
  state=opaque-state&
  code_challenge=illustrative-s256-challenge&
  code_challenge_method=S256
Host: login.example.com
~~~

`state` và `code_challenge` ở đây chỉ minh họa; hệ thống thật phải tạo giá trị ngẫu nhiên/PKCE hợp lệ, kiểm `state` và dùng HTTPS. AS xử lý:

~~~text
requested resource = https://api.example.com/orders
resolved resource  = orders-api
client registered  = shop-web
permitted scopes   = orders:read, orders:create
requested scopes   = orders:read
issued audience    = orders-api
issued scope       = orders:read
~~~

**`resource` là yêu cầu; `aud` là kết quả của quyết định phát hành.** AS có thể ánh xạ giá trị `resource` sang một audience khác về chuỗi, miễn hợp đồng rõ và an toàn.

### 5.1. Khi không có `resource`

AS có thể dùng resource mặc định **an toàn và không mơ hồ** theo client/grant, hoặc từ chối nếu không thể xác định đối tượng nhận. Không được tự cấp token audience quá rộng chỉ vì client bỏ tham số.

### 5.2. Nhiều resource indicators

RFC 8707 hỗ trợ yêu cầu nhiều resource trong những trường hợp phù hợp. Tuy nhiên, token đa audience tăng diện lộ và nguy cơ token của một API bị dùng ở API khác. Nếu Orders và Payments có ranh giới khác nhau, **ưu tiên token riêng cho mỗi audience** theo chính sách. AS có thể từ chối yêu cầu nhiều resource; không nên mặc định một token có thể truy cập tất cả.

## 6. Danh mục chính sách ở Authorization Server

AS cần kết hợp dữ liệu đáng tin cậy, chẳng hạn:

| Nguồn policy | Thông tin | Tác dụng |
|---|---|---|
| Client registration | `shop-web` chỉ được authorization code và resource `orders-api` | Chặn request ngoài grant/resource được đăng ký |
| Resource catalog | `orders-api` hỗ trợ `orders:read`, `orders:create` | Xác định namespace scope và audience đúng |
| Grant context | Authorization code đã xác thực, consent hoặc quyền đã cấp | Giới hạn phạm vi theo grant thực tế |
| Subject/user policy | `user-742` chỉ được xem đơn ở tenant Beta | Hạn chế quyền theo người dùng/ngữ cảnh |
| Service policy | `orders-worker` được đồng bộ, không có end-user | Cấp quyền đúng service principal |
| Session/security state | MFA, client bị khóa, phiên hết hạn, mức rủi ro | Có thể yêu cầu step-up, từ chối hoặc giảm TTL |
| Token profile | JWT `at+jwt` hoặc opaque + introspection | Quyết định định dạng/claims/cách kiểm |
| Grant/refresh store | Grant scope/resource đã cấp, trạng thái và rotation | Ngăn refresh mở rộng quyền ngoài grant |

Ví dụ **policy mô tả**, không phải cấu hình có thể nạp trực tiếp vào sản phẩm:

~~~yaml
authorizationServer:
  issuer: https://login.example.com

  resources:
    orders-api:
      resourceIndicator: https://api.example.com/orders
      availableScopes: [orders:read, orders:create, orders:cancel]
      accessTokenTtlSeconds: 600
    payments-api:
      resourceIndicator: https://api.example.com/payments
      availableScopes: [payments:read, payments:refund]
      accessTokenTtlSeconds: 300

  clients:
    shop-web:
      type: public
      grants: [authorization_code, refresh_token]
      allowedResources: [orders-api]
      scopesByResource:
        orders-api: [orders:read, orders:create]
      requirePkce: true

    orders-worker:
      type: confidential
      grants: [client_credentials]
      allowedResources: [orders-api]
      scopesByResource:
        orders-api: [orders:read]

    refunds-service:
      type: confidential
      grants: [client_credentials]
      allowedResources: [payments-api]
      scopesByResource:
        payments-api: [payments:refund]
~~~

Các danh sách trong client registration biểu diễn **trần được phép xin token**, không phải mọi quyền sẽ tự động được cấp trong từng lần. `shop-web` đăng ký `orders:create` vẫn có thể chỉ được cấp `orders:read` khi user/consent/policy không cho phép tạo đơn.

## 7. Thuật toán quyết định scope và audience

Pseudocode dưới đây mô tả thứ tự quyết định tại AS. Đây là **mô hình chính sách**, không phải implementation OAuth đầy đủ hoặc cú pháp lỗi chuẩn cho tất cả endpoint.

~~~text
function decideAccessToken(request, authenticatedClient, grantContext):
    client = loadActiveClientRegistration(authenticatedClient.id)
    if client is missing or disabled:
        reject

    if request.grantType not in client.allowedGrantTypes:
        reject

    grant = validateGrantAndBindings(request, client, grantContext)
    if grant is invalid:
        reject

    resource = resolveResourceOrSafeDefault(request.resource, client, grant)
    if resource is unknown or not client.allowedResources.contains(resource):
        reject invalid_target

    requestedScopes = parseScopesOrSafeDefaults(request.scope, client)
    if requestedScopes contains unknown/invalid resource scopes:
        reject invalid_scope

    allowedByClient = client.scopesFor(resource)
    allowedByGrant = grant.authorizedScopesFor(resource)
    allowedByPolicy = policy.scopesFor(
        principal = grant.principal,
        client = client,
        resource = resource,
        tenant = grant.trustedTenantContext
    )

    grantedScopes = requestedScopes
        INTERSECT allowedByClient
        INTERSECT allowedByGrant
        INTERSECT allowedByPolicy

    if policy.requiresFullMatch and grantedScopes != requestedScopes:
        reject invalid_scope

    if grantedScopes violates minimum/mandatory policy:
        reject

    return issueAccessToken(
        issuer = configuredIssuer,
        subject = grant.principal,
        clientId = client.id,
        audience = resource.canonicalAudience,
        scopes = grantedScopes,
        expiresIn = policy.chooseTtl(client, grant, resource),
        trustedContext = policy.minimalTrustedClaims(grant)
    )
~~~

**Điều kiện quan trọng:**

~~~text
issuedScopes ⊆ clientAllowedScopesForResource
issuedScopes ⊆ grantAuthorizedScopesForResource
issuedScopes ⊆ policyAllowedScopesForPrincipalAndTenant

issuedAudience ∈ resourcesAllowedForClientAndGrant
issuedTtl <= maximumTtlAllowedByPolicy
~~~

Phép giao scope minh họa nguyên tắc “không cấp vượt hạn mức”. Với grant không có end user, `grantAuthorizedScopes` là quyền của **service/client**. Nhiều hệ thống còn có policy phụ thuộc rủi ro, consent, tổ chức, hợp đồng hoặc giới hạn giao dịch nên không thể chỉ làm giao tập hợp đơn giản.

**Tuyệt đối không dùng phép hợp quyền client và user** rồi cấp mọi scope xuất hiện ở một trong hai tập. Nếu client được phép X nhưng user được phép Y, điều đó không tự tạo quyền cấp cả X và Y.

## 8. Authorization Code + PKCE: cấp access token cho người dùng

Giả sử `shop-web` yêu cầu `orders:read` cho `user-742` thuộc tenant Beta. AS đã xác định người dùng có thể đọc đơn trong tenant này và đã xử lý consent/chính sách của grant.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as OAuth Client shop-web
    participant AS as Authorization Server/OP
    participant P as Grant and policy store
    participant API as Orders Resource Server
    U->>C: Bắt đầu xem đơn
    C->>AS: Authorize: client_id, scope, resource, state, PKCE
    AS->>P: Kiểm client registration và requested resource
    P-->>AS: shop-web được phép xin orders-api
    AS->>U: Xác thực và consent theo chính sách
    U-->>AS: Hoàn tất yêu cầu
    AS->>P: Xác định grant scopes và tenant policy
    P-->>AS: orders:read, tenant-beta
    AS-->>C: Authorization code
    C->>AS: Token endpoint: code + code_verifier
    AS->>AS: Kiểm code binding, grant và client
    AS-->>C: Access token aud=orders-api, scope=orders:read
    C->>API: GET /orders/42 + Bearer token
    API->>API: Xác minh token và quyền trên đơn hàng
    API-->>C: 200 hoặc từ chối
~~~

**Authorization code không phải access token**; client phải đổi tại token endpoint theo giao thức. **PKCE** giảm nguy cơ authorization code bị chặn và đổi trái phép; PKCE **không tự quyết định scope/audience** nếu policy AS cấu hình sai.

### 8.1. Token request ví dụ

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=illustrative-auth-code&
redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
client_id=shop-web&
code_verifier=original-pkce-verifier
~~~

Public client dùng PKCE theo chính sách phù hợp; nó không thể bảo vệ `client_secret` nhúng trong browser/mobile như confidential client. Backend/confidential client có thể phải xác thực tại token endpoint.

### 8.2. Token response

Ví dụ phản hồi rút gọn:

~~~json
{
  "access_token": "<illustrative-bearer-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

AS công bố `scope` thực sự khi khác phạm vi client yêu cầu theo OAuth. Nếu yêu cầu OIDC hợp lệ, response có thể có **ID token**; nếu chính sách cho phép, có thể có **refresh token**. Chúng khác mục đích; Resource Server chỉ nhận **access token** đúng audience.

Nếu user từ chối consent cần thiết hoặc principal bị khóa, AS không được chỉ dựa vào client registration để cấp quyền.

## 9. Client Credentials: cấp token cho ứng dụng/dịch vụ

Dịch vụ `orders-worker` cần đọc đơn để chạy tác vụ định kỳ, không có người dùng đang đăng nhập trực tiếp.

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <illustrative-confidential-client-credentials>

grant_type=client_credentials&
scope=orders%3Aread&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

AS phải **xác thực confidential client**, kiểm grant, scope và resource. Có thể dùng client secret, `private_key_jwt`, mTLS hoặc cơ chế khác đã đăng ký.

Nếu client được cấp đúng quyền:

~~~text
authenticated client = orders-worker
grant type            = client_credentials
principal             = orders-worker (service)
approved resource     = orders-api
issued audience       = orders-api
issued scope          = orders:read
~~~

Nếu worker xin `payments:refund` hoặc `resource=payments-api` ngoài allowed resources, AS **không được cấp token đó**. Không tự đặt `sub=user-742` cho service token vì chẳng có end user được xác thực trong grant này.

Ở JWT access-token profile, `sub` có quy tắc cụ thể tùy grant; RS phải xác định chính xác **principal là service hay user** trước khi cấp quyền.

### 9.1. Quyền service theo tenant

Nếu `orders-worker` chỉ được sao lưu tenant Beta, policy cũng phải hạn chế tenant, không mở mọi tenant chỉ vì nó chạy ở mạng nội bộ. Scope `orders:read` vẫn không thay object-level/tenant authorization.

## 10. JWT: claims của một token đã được cấp

AS có thể phát JWT access token ký bất đối xứng (JWS) với protected header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453000,
  "jti": "access-9c2b",
  "tenant_id": "tenant-beta"
}
~~~

`tenant_id` trong ví dụ là claim **tùy biến theo hợp đồng** AS–RS. `at+jwt` được sử dụng trong JWT Profile for OAuth 2.0 Access Tokens (RFC 9068); token nào áp dụng profile này phải tuân thủ các yêu cầu của profile.

| Claim | Nguồn giá trị | Kiểm soát |
|---|---|---|
| `iss` | Cấu hình AS | Không lấy issuer tùy ý từ request client |
| `sub` | Principal/grant đã xác minh | User hay service tùy grant/profile |
| `aud` | Resource được AS phê duyệt | Không copy tùy ý `resource` |
| `client_id` | Client registration/grant | Không nhầm với audience |
| `scope` | Quyết định scope thực tế | Không copy scope vượt quyền |
| `iat`, `nbf`, `exp` | Đồng hồ và TTL policy AS | Giới hạn thời gian phù hợp |
| `jti` | AS nếu cần định danh token | Không tự chống replay |
| `tenant_id` nếu có | Tenant context được kiểm tin cậy | Không tự cấp quyền mọi bản ghi tenant |

**JWT ký không có nghĩa payload được mã hóa.** Với JWT JWS, payload có thể bị đọc sau Base64URL decode. Đừng đưa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào token.

### 10.1. Token ký đúng vẫn có thể cấp sai quyền

Nếu AS ký một token `scope=payments:refund` cho client không có quyền, chữ ký vẫn hợp lệ. Sai sót nằm ở **quyết định phát hành**, còn RS phải tiếp tục kiểm audience, scope và quyền nghiệp vụ để hạn chế hậu quả. Không được coi “signature valid” là đồng nghĩa “authorization valid”.

### 10.2. Key và issuer

AS giữ private signing key khi dùng chữ ký bất đối xứng; RS kiểm bằng public key/JWKS đã được gắn với issuer tin cậy. `kid` chỉ giúp chọn khóa trong tập khóa đã tin. Không để token hoặc client tự quyết URL khóa/thuật toán mà AS/RS sẽ tin.

## 11. Opaque token: scope và audience nằm trong metadata

Không bắt buộc access token phải là JWT. AS có thể sinh **opaque random reference token** với CSPRNG có entropy đủ lớn, lưu metadata trong token store và trả chuỗi bí mật cho client.

~~~text
Token record at Authorization Server
  token_lookup_hash
  principal         = user-742
  client_id         = shop-web
  audience          = orders-api
  scopes            = [orders:read]
  issued_at
  expires_at
  revoked_at
  tenant_context    = tenant-beta (if profile supports)
~~~

Bản thân raw token không chứa claims để API tự đọc. RS có thể hỏi **OAuth 2.0 Token Introspection (RFC 7662)** hoặc nguồn lookup tin cậy.

Ví dụ response introspection:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893453000
}
~~~

Ngoài `active`, các trường phụ thuộc AS/hợp đồng. RS phải xác thực đúng endpoint AS qua TLS và danh tính Resource Server khi yêu cầu, kiểm `active`, audience, scope và quyền.

**`active=true` không có nghĩa được gọi mọi API hoặc mọi endpoint.** Cache introspection có thể làm chậm hiệu lực revocation; thiếu metadata đủ để kiểm policy cần xử lý an toàn.

### 11.1. So sánh hai định dạng ở thời điểm phát hành

| Tiêu chí | JWT access token | Opaque access token |
|---|---|---|
| Ai chọn scope/audience | AS theo policy | AS theo policy |
| Nơi lưu dữ liệu | Claims trong token đã ký | Metadata trạng thái/token store |
| RS kiểm | Chữ ký, issuer, aud, time, scope | Introspection/lookup, active, aud, scope |
| Thu hồi ngay | Cần state/denylist hoặc TTL ngắn | Có thể thấy sớm nếu lookup mới, phụ thuộc cache |
| Scope/ownership ở API | RS vẫn kiểm | RS vẫn kiểm |
| Bearer bị sao chép | Có thể bị phát lại | Có thể bị phát lại |

Định dạng không thay chính sách cấp quyền. Cả hai đều phải có **audience rõ, scope đã được duyệt và chiến lược TTL/thu hồi**.

## 12. Resource Server phải kiểm lại khi sử dụng

AS là bên phát hành, nhưng RS không được chỉ nhìn thấy chữ ký hợp lệ rồi cho phép.

~~~mermaid
flowchart TD
    A[Request với access token] --> B{Token đã được xác minh?}
    B -->|Không| X[401 - invalid token]
    B -->|Có| C{Đúng issuer, audience, purpose?}
    C -->|Không| X
    C -->|Có| D{Token còn hiệu lực?}
    D -->|Không| X
    D -->|Có| E{Có scope endpoint cần?}
    E -->|Không| Y[403 - insufficient scope]
    E -->|Có| F{Có quyền trên tenant và resource?}
    F -->|Không| Z[403 hoặc 404 theo policy]
    F -->|Có| G[Cho phép request]
~~~

Mã HTTP cụ thể tùy giao thức và chính sách. Token thiếu/hỏng thường `401`; token hợp lệ nhưng thiếu scope có thể `403` với `insufficient_scope`; Resource Server có thể dùng `404` để tránh tiết lộ sự tồn tại của tài nguyên không được phép xem.

### 12.1. Pseudocode cho Orders API

~~~text
function getOrder(request, orderId):
    access = trustedAccessTokenValidator.validate(
        request.Authorization,
        expectedIssuer = "https://login.example.com",
        expectedAudience = "orders-api",
        requiredPurpose = "access_token"
    )
    if access.invalid:
        return 401

    if "orders:read" not in access.scopes:
        return 403

    order = repository.findByAuthorizedTenantAndId(
        access.trustedTenant,
        orderId
    )
    if order is missing:
        return 404

    if not policy.canReadOrder(access.principal, order):
        return 403

    return 200 with allowed order fields
~~~

Dùng thư viện chuẩn JWT hoặc introspection, không tự decode JWT rồi coi claims đã tin. Với nhiều tenant, context phải được xác minh từ token/tra cứu chính sách, không lấy raw tenant ID do client gửi.

### 12.2. Các lỗi riêng biệt

- Token `aud=orders-api`, `scope=orders:read` gọi DELETE cần `orders:cancel` → **thiếu scope**.
- Token `aud=payments-api` có `scope=orders:read` gọi Orders API → **sai audience**.
- Token đúng aud và scope nhưng order thuộc tenant khác → **sai resource authorization**.
- ID token có `aud=shop-web` được gửi đến Orders API → **sai loại token/đối tượng nhận**.

Các trường hợp cần validator và mã lỗi thích hợp; không thể dùng một flag `isLoggedIn` để thay thế.

## 13. Refresh token: không mở rộng scope hay resource vô điều kiện

Refresh token được client trình đến **token endpoint của AS** để xin access token mới trong giới hạn grant, không gửi đến API nghiệp vụ.

Grant minh họa:

~~~text
subject                 user-742
client                  shop-web
authorized audience     orders-api
authorized scopes       orders:read
refresh token           bound to this client/grant
~~~

Nếu client gửi refresh token cùng yêu cầu:

~~~text
scope    = orders:read payments:refund
resource = payments-api
~~~

AS **không được mở rộng** grant từ đọc đơn thành hoàn tiền chỉ vì refresh token còn hiệu lực. Tùy chính sách và khả năng của AS, phải từ chối hoặc chỉ cấp token hợp lệ trong phạm vi grant cũ.

Theo OAuth 2.0, scope yêu cầu khi refresh **không được chứa scope chưa được cấp ban đầu**. Nếu không gửi scope, phạm vi thường nằm trong giới hạn grant đã cấp, nhưng AS vẫn có thể giảm theo quyền/trạng thái hiện tại. Nếu AS hỗ trợ `resource` khi refresh, nó cũng phải bị ràng buộc bởi resource được ủy quyền và policy AS.

### 13.1. Refresh token rotation

AS có thể xoay vòng refresh token, vô hiệu hóa token cũ và phát hiện reuse đáng ngờ. Điều này giảm tác động của refresh token bị đánh cắp nhưng:

- Không làm access token mới tự có quyền rộng hơn.
- Không tự chứng minh user vừa đăng nhập hay MFA lại.
- Không mặc định vô hiệu hóa JWT access token cũ chưa hết hạn.
- Không thay kiểm scope, audience và trạng thái client/tenant.

`iat` mới của access token không tương đương `auth_time` xác thực người dùng.

## 14. Token exchange và hệ thống nhiều API

Orders Service đôi khi cần gọi Billing Service thay mặt người dùng. **Không chuyển tiếp tùy tiện** access token `aud=orders-api` tới Billing rồi để Billing bỏ kiểm audience.

Nếu AS hỗ trợ **OAuth 2.0 Token Exchange (RFC 8693)**, service có thể yêu cầu token mới theo ngữ cảnh ủy quyền:

~~~text
Subject token:
  aud   = orders-api
  scope = orders:read
  sub   = user-742

Exchange request:
  requesting client = orders-service
  target audience   = billing-api
  requested scope   = invoices:read

AS policy:
  verify subject token and grant
  verify requesting actor/client
  verify delegation rights
  verify target resource and scope

Token only if authorized:
  aud   = billing-api
  scope = invoices:read
  subject and actor according to profile
~~~

**Token exchange không tự động sao chép mọi quyền của token nguồn sang token đích.** AS phải kiểm người thực hiện exchange được phép thay mặt chủ thể, resource đích hợp lệ, scope mới đúng grant và policy.

### 14.1. Token có nhiều audience

JWT có thể chứa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["orders-api", "payments-api"],
  "scope": "orders:read payments:read",
  "exp": 1893453000
}
~~~

Token trên hướng đến nhiều API; nếu là bearer token, nơi nào làm lộ token có thể tăng bề mặt lạm dụng tại API còn lại. Khi các Resource Server có ranh giới quyền khác nhau, **token riêng theo audience và scope tối thiểu thường dễ quản lý hơn**. Nếu phát token đa audience, AS phải đánh giá toàn bộ các resource, RS vẫn phải kiểm policy riêng và ngăn token substitution.

### 14.2. Audience alias khi đổi tên API

Nếu Orders API đổi định danh từ `orders-api` sang `https://api.example.com/orders` nhưng giữ cùng ranh giới tin cậy, AS/RS có thể dùng alias chính xác trong giai đoạn migration. Đây không phải lý do chấp nhận `payments-api` hoặc mọi audience có cùng prefix. Cần thời hạn gỡ alias và kiểm token đã phát hành còn sống.

## 15. Tenant, quyền thay đổi và sự cố token

Hệ thống SaaS có thể có một user là admin tenant Anpha nhưng viewer tại Beta. Nếu user yêu cầu `orders:create` trong Beta, AS phải xét đúng membership/role và ngữ cảnh tenant nếu chính sách cấp token phụ thuộc điều đó.

Token minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "tenant_id": "tenant-beta",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

`tenant_id` là claim tùy biến phải được AS gắn từ **ngữ cảnh đã xác minh**, không sao chép header `X-Tenant-Id` do client tự gửi. RS vẫn kiểm bản ghi thuộc Beta và user được quyền xem bản ghi đó.

### 15.1. Quyền bị thu hồi sau khi cấp

JWT scope `orders:create` có thể còn hạn dù role user vừa bị hạ. Các biện pháp tương ứng mức rủi ro:

- Access token TTL ngắn và scope hẹp.
- Kiểm membership/permission hiện tại tại API hoặc Policy Decision Point.
- Denylist/token version/session state nếu cần vô hiệu hóa sớm.
- Introspection với opaque token và cache TTL phù hợp.
- Thu hồi phiên/refresh token để chặn cấp token mới.

**Logout, revoke refresh token và revoke access token là các thao tác có hiệu lực khác nhau.** Phải mô tả rõ token nào bị vô hiệu, khi nào, có chịu ảnh hưởng của cache và clock skew không.

### 15.2. Bearer token bị đánh cắp vẫn có thể được dùng

Scope/audience hẹp **giảm phạm vi tác hại** nhưng không khiến bearer token chống phát lại. Nếu attacker sao chép token hợp lệ `aud=orders-api`, `scope=orders:read`, token có thể được gửi lại cho Orders API trước hạn.

Biện pháp bổ sung:

1. Dùng HTTPS; tránh token trong query string, URL, log, analytics và crash report.
2. Lưu token an toàn phù hợp browser, mobile hoặc backend; giới hạn quyền truy cập.
3. TTL ngắn, scope/audience tối thiểu, refresh rotation và phát hiện reuse.
4. Revocation/introspection/denylist khi cần phản ứng sớm.
5. DPoP hoặc mTLS sender-constrained access token nếu kiến trúc hỗ trợ; API phải kiểm proof/chứng chỉ và binding theo chuẩn.
6. Kiểm tenant, ownership, transaction policy và rủi ro ở mỗi request.

Claim `jti` chỉ định danh token; nó **không tự chống replay** nếu không có cơ chế trạng thái và kiểm chứng bổ sung.

## 16. Tình huống cấp token và quyết định đúng

Giả sử AS có cấu hình:

~~~text
Client shop-web:
  allowed grants = authorization_code, refresh_token
  allowed resource = orders-api
  allowed scopes = orders:read, orders:create

Client orders-worker:
  allowed grant = client_credentials
  allowed resource = orders-api
  allowed scopes = orders:read

Client refunds-service:
  allowed grant = client_credentials
  allowed resource = payments-api
  allowed scopes = payments:refund

User user-742 / tenant-beta:
  allowed business actions = read orders
  disallowed = create orders, refund payments
~~~

| Yêu cầu | Quyết định AS | Lý do |
|---|---|---|
| `shop-web`, user-742, `orders-api`, `orders:read` | Có thể cấp nếu grant/consent hợp lệ | Resource, client và user policy phù hợp. |
| `shop-web`, user-742, `orders-api`, `orders:create` | Từ chối hoặc giảm scope theo policy | User chưa được phép tạo đơn. |
| `shop-web` xin `payments-api`, `payments:refund` | Từ chối | Client không được phép resource này. |
| `orders-worker` xin `orders-api`, `orders:read` | Có thể cấp | Đúng client credentials và service policy. |
| `orders-worker` xin `orders:create` | Từ chối | Vượt allowed scope của client. |
| `refunds-service` xin `payments-api`, `payments:refund` | Có thể cấp | Đúng service resource và scope. |
| `shop-web` xin resource không tồn tại | Từ chối | Không có resource được phê duyệt. |
| `shop-web` refresh xin `payments:refund` | Từ chối | Mở rộng trái grant ban đầu. |
| Client bị khóa xin token mới | Từ chối | Trạng thái client không hợp lệ. |
| User chưa consent scope nhạy cảm | Xử lý consent hoặc từ chối | Đăng ký client không thay authorization của user. |
| Client gửi scope `superadmin:all` không xác định | Từ chối | Scope không có trong policy. |

Bảng trên chỉ minh họa **quyết định phát hành tại AS**. Khi dùng token, RS vẫn có trách nhiệm xác minh token và quyền với tài nguyên.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Copy `request.scope` nguyên vào JWT | Scope escalation | Kiểm client, grant, user, consent và resource. |
| Copy `request.resource` vào `aud` không kiểm | Cấp token cho API không được phép | Resolve theo resource catalog và allowed audience. |
| Coi `client_id` là quyền truy cập | Client bất kỳ có thể xin scope nhạy cảm | Dùng registration/grant/policy, không tin tên client đơn lẻ. |
| Chỉ xét user role toàn cục | Quyền tenant A lấn sang B | Kiểm đúng membership/role theo tenant. |
| Dùng phép hợp quyền client + user | Cấp quyền khi chỉ một bên được phép | Ràng buộc đầy đủ điều kiện, không union. |
| Giảm scope nhưng không phản ánh scope thực tế | Client hiểu sai quyền đã cấp | Trả scope đã cấp theo giao thức. |
| Bỏ `aud` hoặc token purpose | Token của API khác hoặc ID token được dùng nhầm | Cấp và kiểm audience/loại token chính xác. |
| Phát JWT dài hạn chứa role cũ | Quyền tồn tại sau khi bị thu hồi | TTL ngắn, state check/revocation theo nhu cầu. |
| Mở scope khi refresh không cần grant mới | Leo thang đặc quyền không có consent | Ràng buộc refresh grant, scope/resource. |
| RS chỉ kiểm chữ ký | Token hợp lệ nhưng thiếu scope/ownership vẫn qua | Kiểm scope và policy endpoint/bản ghi. |
| Cấp token đa audience quá rộng | Cross-API token reuse | Cấp token riêng và policy theo resource. |
| AS fail open khi policy service lỗi | Cấp scope không có căn cứ | Fail closed hoặc chế độ dự phòng được phê duyệt. |
| Ghi bearer token vào log | Attacker có thể phát lại | Redact token, bảo vệ lưu trữ và đường truyền. |

## 18. Bài thực hành

### Bài 1 — Xây dựng policy cho hai API

Nền tảng học tập có:

~~~yaml
resources:
  course-api:
    scopes: [courses:read, courses:publish]
  billing-api:
    scopes: [invoices:read, invoices:refund]

clients:
  learner-web:
    resources: [course-api]
    scopesByResource:
      course-api: [courses:read]
  instructor-web:
    resources: [course-api]
    scopesByResource:
      course-api: [courses:read, courses:publish]
  billing-worker:
    resources: [billing-api]
    scopesByResource:
      billing-api: [invoices:read]
~~~

Hãy xét:

1. `learner-web` xin `courses:read` cho `course-api` → **có thể cấp** khi grant/user policy hợp lệ.
2. `learner-web` xin `courses:publish` → **không cấp**, vì client không được phép.
3. `instructor-web` xin `courses:publish` → **có thể cấp** khi subject có quyền và điều kiện authorization khác đạt.
4. `instructor-web` xin `invoices:refund` → **không cấp**, sai resource và scope.
5. `billing-worker` xin `invoices:refund` → **không cấp**, vượt client allowed scopes.
6. Token `aud=billing-api`, `scope=courses:read` gửi tới Course API → **RS phải từ chối**, vì sai audience.

### Bài 2 — Tìm lỗi trong thuật toán AS

Một nhóm viết:

~~~text
token.aud   = request.resource
token.scope = request.scope
token.sub   = request.userId
sign(token)
~~~

Các lỗi cần nhận ra:

- Client có thể gửi resource ngoài allowed audience.
- Client có thể xin scope chưa được grant hoặc scope không thuộc resource.
- `request.userId` có thể bị giả mạo nếu không được ràng buộc với principal của grant.
- Không kiểm client registration, consent, tenant, client state hoặc TTL.
- **Ký token chỉ làm sai sót thành một token được ký hợp lệ**, không sửa được authorization.

Cách sửa: kiểm grant/client/subject từ nguồn tin cậy, resolve resource, giới hạn scope, chọn TTL và token profile đúng, chỉ phát hành sau khi có quyết định policy hợp lệ.

### Bài 3 — Ma trận kiểm thử âm tính

| Test | Input | Kỳ vọng |
|---|---|---|
| Client không đăng ký | `client_id` lạ | Từ chối. |
| Grant không được phép | Public client xin `client_credentials` | Từ chối. |
| Unknown resource | `resource=https://unknown.example.com` | Từ chối, có thể dùng `invalid_target` theo RFC 8707. |
| Resource sai client | `shop-web` xin `payments-api` | Không phát payments token. |
| Unknown scope | `orders:superadmin` | Từ chối/`invalid_scope` phù hợp. |
| Scope vượt consent | Xin tạo đơn khi user chỉ được đọc | Không phát scope tạo đơn. |
| Disabled client | Client vừa bị khóa | Không cấp token mới. |
| Scope escalation qua refresh | Refresh `orders:read` xin `payments:refund` | Từ chối mở rộng trái grant. |
| JWT sai issuer/audience | Token của API khác gửi Orders API | RS từ chối. |
| Token đúng aud nhưng không có scope | Gọi endpoint cần `orders:cancel` | RS từ chối. |
| ID token ở API | `aud=shop-web` | RS từ chối. |
| Object/tenant khác | Đơn thuộc tenant khác | RS từ chối. |
| Opaque inactive | Introspection `active=false` | RS từ chối. |
| Token bị thu hồi | JWT còn hạn hoặc cache introspection cũ | Kiểm theo chính sách vô hiệu hóa đã công bố. |
| Bearer bị đánh cắp | Replay token còn hiệu lực | Kiểm TTL, sender binding và phản ứng rủi ro đã thiết kế. |

### Bài 4 — Audit phát hành

Ví dụ log metadata, **không ghi token thô**:

~~~json
{
  "event": "access_token_issued",
  "issuer": "https://login.example.com",
  "client_id": "shop-web",
  "grant_type": "authorization_code",
  "audience": "orders-api",
  "issued_scopes": ["orders:read"],
  "decision": "allowed",
  "policy_version": "2026-11",
  "correlation_id": "req-7f2a"
}
~~~

Không log authorization code, client secret, PKCE verifier, access/refresh token, OTP hoặc thông tin nhạy cảm không cần thiết. Với request bị từ chối, ghi mã lỗi và chính sách gây từ chối để điều tra.

## 19. Checklist triển khai

- [ ] Có **resource catalog** với audience canonical và scope hợp lệ theo từng resource.
- [ ] Client registration giới hạn grant, resource và scope; không lấy request client làm nguồn cấp quyền.
- [ ] AS kiểm principal, consent, tenant, session/client state và policy trước khi cấp token.
- [ ] Đã định nghĩa rõ trường hợp scope quá rộng được từ chối hay thu hẹp, và cách trả scope thực tế.
- [ ] Nếu hỗ trợ RFC 8707, AS xác minh resource indicator trước khi ánh xạ thành audience.
- [ ] Khi request thiếu resource/scope, dùng default an toàn hoặc từ chối; không cấp mọi quyền.
- [ ] JWT có claims đúng token profile, được ký bằng khóa bảo vệ; opaque token có entropy và metadata đáng tin.
- [ ] RS kiểm issuer, signature/introspection, audience, thời gian, token type, scope và object-level authorization.
- [ ] Không dùng ID token hoặc refresh token làm access token của RS.
- [ ] Refresh grant không mở rộng scope/resource vượt grant và policy đã ủy quyền.
- [ ] Client credentials xác định service principal, không giả định có end user.
- [ ] Token exchange hoặc token đa audience được kiểm chính sách cho từng resource.
- [ ] TTL, revocation, key rotation, introspection cache và quyền thay đổi được xử lý theo rủi ro.
- [ ] Token được lưu/truyền an toàn; có biện pháp chống đánh cắp/phát lại.
- [ ] Test lỗi wrong audience, scope escalation, invalid resource, tenant mismatch và token substitution.
- [ ] Khi không đủ dữ liệu chính sách, AS/RS **fail closed**.

**Ghi nhớ:** client **yêu cầu** scope và resource; Authorization Server **quyết định và phát hành** access token có **scope thuộc phạm vi được phép** và **audience đúng Resource Server được phê duyệt**. Khi sử dụng, Resource Server vẫn phải **xác minh token và kiểm quyền trên tài nguyên**. Chữ ký hợp lệ không biến một scope hoặc audience bị cấp sai thành quyền hợp lệ.

### Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client, grant, scope, authorization và refresh token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** tham số `resource` và xác định Resource Server.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims và cách dùng JWT access token.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `iat`.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh issuer, audience và thuật toán.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và metadata opaque token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách dùng bearer token.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code.
- **RFC 8693 — OAuth 2.0 Token Exchange:** ủy quyền cho resource và actor khác.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với khóa của bên gửi.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** giới hạn audience/scope, chống lạm dụng.
- **OpenID Connect Core 1.0:** phân biệt ID token và access token trong các luồng OIDC.
