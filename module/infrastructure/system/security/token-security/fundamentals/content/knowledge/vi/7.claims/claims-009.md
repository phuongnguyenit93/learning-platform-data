# Client ID và authorized party

Trong một hệ thống bán hàng, ứng dụng `shop-web` đưa người dùng tới OpenID Provider để đăng nhập, nhận ID token và access token, rồi gọi API `orders-api`. Các token có thể xuất hiện những trường `client_id`, `azp`, `aud` và `sub`. Tất cả đều trông như định danh, nhưng **chúng chỉ những bên khác nhau và phục vụ các phép kiểm khác nhau**.

- `client_id` xác định **OAuth client**, tức ứng dụng đã đăng ký với Authorization Server.
- `azp` (*authorized party*) trong **OIDC ID token** xác định **client được phát hành ID token**.
- `aud` xác định **bên nhận token**: với ID token thường là OIDC Client, với access token thường là Resource Server (API).
- `sub` xác định **chủ thể mà token đề cập**: có thể là người dùng hoặc service principal, tùy loại token/grant.
- `scope` mô tả **phạm vi ủy quyền**, nhưng API vẫn phải kiểm quyền cụ thể trên tài nguyên.

Đặc biệt, **client ID hoặc authorized party khớp không có nghĩa request được phép**. Bên nhận còn phải xác minh token đúng issuer, đúng mục đích, còn hiệu lực, có audience phù hợp và đáp ứng chính sách cấp quyền.

Bài thuộc chương **Claims** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, liên hệ các trường trên với phát hành và xác minh JWT/opaque access token, access/refresh token, OAuth 2.0/OpenID Connect, scope, audience, thu hồi và nguy cơ token bị đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích client ID được cấp khi nào, ai quản lý, và vì sao client ID không phải bí mật.
2. Diễn giải `azp` đúng theo OIDC, đặc biệt khi ID token có nhiều audience.
3. Phân biệt `client_id`, `azp`, `aud`, `sub`, `iss`, `scope` và actor trong cơ chế ủy quyền.
4. Thiết kế phép kiểm ID token tại OIDC Client và access token tại Resource Server.
5. Xây dựng chính sách cho phép hoặc hạn chế client sau khi xác minh token mà không bỏ qua quyền người dùng, tenant và đối tượng dữ liệu.
6. Phân tích token substitution, client impersonation, nhầm audience và bearer token replay.

## 2. Mỗi định danh thuộc một vai trò

Một luồng OAuth 2.0/OIDC có những thành phần:

| Vai trò | Ví dụ | Chức năng |
|---|---|---|
| **End User / Resource Owner** | `user-742` | Người đăng nhập hoặc chủ tài nguyên tùy grant và hệ thống. |
| **OAuth Client** | `shop-web` | Ứng dụng yêu cầu token và có `client_id` đã đăng ký. |
| **Authorization Server (AS)** | `https://login.example.com` | Xử lý grant, cấp access token và có thể cấp refresh token. |
| **OpenID Provider (OP)** | `https://login.example.com` | Bên xác thực theo OIDC và phát hành ID token cho client; thường kiêm AS. |
| **Resource Server** | `orders-api` | Bảo vệ API, xác minh access token và quyết định cấp quyền cho request. |
| **Dịch vụ gọi API** | `inventory-worker` | Có thể là OAuth client riêng, dùng grant cho ứng dụng/dịch vụ. |

Ví dụ năm định danh riêng:

~~~text
issuer         https://login.example.com
subject        user-742
client_id      shop-web
API audience   orders-api
tenant         tenant-beta
~~~

`client_id=shop-web` không trả lời người dùng đang đăng nhập là ai, tenant nào có quyền, và chắc chắn cũng không chứng minh máy đang gửi bearer token hiện tại là thiết bị của `shop-web`.

## 3. `client_id` là gì?

**OAuth Client Identifier** (`client_id`) là định danh AS cấp cho client khi đăng ký. AS sử dụng nó để tìm cấu hình và áp dụng chính sách cho ứng dụng, ví dụ redirect URI hợp lệ, các grant được cho phép, yêu cầu xác thực client, scope, quyền truy cập từng audience.

Yêu cầu authorize minh họa:

~~~http
GET /authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20profile%20orders%3Aread&
  state=opaque-state&
  code_challenge=pkce-challenge&
  code_challenge_method=S256
Host: login.example.com
~~~

Request trên được xuống dòng cho dễ đọc; trong thực tế phải mã hóa thành URL hợp lệ và dùng HTTPS. **AS không cấp token chỉ vì request tự khai `client_id`**. Nó còn phải xác minh redirect URI, code/PKCE, trạng thái người dùng và các điều kiện của grant. Với confidential client, token endpoint còn áp dụng client authentication khi phù hợp.

### 3.1. Client ID không phải mật khẩu

| Thành phần | Có bí mật không? | Dùng làm gì? |
|---|---|---|
| `client_id` | **Không**; thường có thể công khai | Định danh ứng dụng với AS và trong metadata token. |
| `client_secret` | **Có** nếu được cấp cho confidential client | Một cách xác thực client tại token endpoint, theo phương thức được cấu hình. |
| `code_verifier` trong PKCE | Cần bảo vệ trong một lần thực hiện luồng | Ràng buộc đổi authorization code với bên đã khởi tạo luồng. |
| Access token dạng bearer | **Có**; ai cầm token có thể thử dùng nó | Trình token tới Resource Server theo audience/scope/quyền. |
| Refresh token | **Có**, thường cần bảo vệ nghiêm ngặt | Xin access token mới tại AS, không dùng tại API nghiệp vụ. |

Một SPA hoặc mobile application là **public client**: không thể coi bí mật nhúng trong mã phát cho người dùng là secret đáng tin. Với **confidential client** chạy tại backend, AS có thể yêu cầu `client_secret`, `private_key_jwt` hoặc mTLS. Cả hai loại vẫn có `client_id`.

**Client authentication** chứng minh caller của token endpoint phù hợp client đã đăng ký; `client_id` đơn lẻ chỉ là tên đăng ký. Không dùng `X-Client-Id: shop-web` do người gọi API tự gửi như chứng cứ xác thực.

### 3.2. Client ID phụ thuộc issuer

Hai Authorization Server có thể cùng có client tên `shop-web`, nhưng đó là hai bản đăng ký riêng biệt:

~~~text
https://login.example.com       + shop-web
https://login.partner.example    + shop-web
~~~

Chính sách nên xét **cặp (issuer, client_id)**, đặc biệt trong hệ thống liên kết nhiều nhà cung cấp danh tính. Một client ID giống nhau không đồng nghĩa quyền giống nhau. Hãy so sánh giá trị theo quy ước định danh của issuer, không tự chuyển chữ hoa/thường hoặc chuẩn hóa thiếu căn cứ.

### 3.3. Client ID trong các grant

- **Authorization Code + PKCE:** client đổi code được cấp trong luồng có người dùng; token có thể đại diện cho quyền được ủy quyền thay mặt người dùng.
- **Client Credentials:** token được cấp theo quyền của chính ứng dụng/dịch vụ, có thể không có end user.
- **Refresh Token Grant:** client trình refresh token cho AS để xin access token mới; quá trình này không nhất thiết yêu cầu người dùng đăng nhập lại.

Vì thế, cùng claim `client_id` có thể xuất hiện trong token của người dùng hoặc của service. **Không suy ra `sub` chắc chắn là user chỉ từ client ID.**

## 4. `azp`: authorized party trong OIDC

Trong **OpenID Connect Core**, claim `azp` (*Authorized Party*) trong **ID token** mô tả **client mà ID token được phát hành cho**. Nó là định danh OAuth 2.0 client, thường chính là `client_id` của OIDC Client nhận token.

Ví dụ ID token:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "shop-web",
  "azp": "shop-web",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

- `iss` là OP phát hành.
- `sub` là chủ thể xác thực.
- `aud` cho biết ID token hướng tới OIDC Client nào.
- `azp` khi hiện diện định danh authorized party được cấp ID token.

**`azp` không phải role, không phải scope, không phải bằng chứng client đã được phép thực hiện giao dịch và không biến ID token thành access token của API.**

### 4.1. ID token chỉ có một audience

Một ID token có `aud=shop-web` nhưng **không có `azp`** có thể vẫn hợp lệ nếu các điều kiện OIDC khác đúng. Không được viết validator giả định mọi ID token đều bắt buộc có `azp`.

Khi `azp` có hiện diện, client nên kiểm giá trị là **client ID của mình**. Nếu `aud=shop-web` nhưng `azp=another-client` thì cần coi là không khớp bên nhận và từ chối theo chính sách xác minh ID token.

### 4.2. ID token có nhiều audience

OIDC cho phép ID token có `aud` chứa nhiều giá trị. Trong trường hợp đó, OIDC Core **khuyến nghị (SHOULD)** có `azp`; OIDC Client cũng **nên kiểm** có `azp` và kiểm nó khớp client ID khi hiện diện.

Ví dụ:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["shop-web", "partner-web"],
  "azp": "shop-web",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

Đối với `shop-web`, có thể đạt phần kiểm audience/authorized party nếu chữ ký, issuer và các điều kiện khác đều hợp lệ. `partner-web` **không nên sử dụng token này như ID token của nó**, vì `azp` không khớp client ID của `partner-web` dù nó cũng nằm trong `aud`.

Nếu ID token đa audience thiếu `azp`, ứng dụng áp dụng quy tắc OIDC và chính sách an ninh đã thống nhất. Một **chính sách chặt** thường chọn từ chối khi thiếu `azp` với token đa audience. Cần phân biệt **SHOULD** trong đặc tả với **MUST**; không mô tả quy tắc khuyến nghị như yêu cầu bắt buộc toàn cầu.

### 4.3. `azp` có thể xuất hiện trong access token, nhưng phải xét profile

Một số nhà cung cấp danh tính đưa `azp` vào JWT **access token** để biểu diễn một khái niệm client. Tuy nhiên, **ngữ nghĩa chuẩn được trình bày ở trên dành cho OIDC ID token**. OAuth 2.0 không mặc định mọi access token có `azp` với ý nghĩa thống nhất.

Nếu Resource Server muốn sử dụng `azp` trong access token, cần hợp đồng rõ ràng với issuer: token profile nào, trường này chỉ client nào, có thể khác `client_id` không, và validator sẽ kiểm ra sao. **Không viết logic fallback tự động lấy `azp` thay `client_id` cho mọi issuer.**

## 5. So sánh các claim liên quan

| Trường | Câu hỏi trả lời | Điều không được suy ra |
|---|---|---|
| `iss` | Ai phát hành token? | Khớp chuỗi issuer không đủ; còn phải xác minh token bằng khóa/metadata đáng tin. |
| `sub` | Token nói về chủ thể nào? | Chủ thể luôn là người dùng hoặc có quyền trên mọi tenant. |
| `aud` | Bên nào được nhận token? | Audience đúng là đủ permission nghiệp vụ. |
| `client_id` | OAuth client nào gắn với việc xin/cấp token theo profile? | Người gửi bearer token hiện tại chắc chắn là client đó. |
| `azp` | Trong OIDC ID token, client được phát hành token là ai? | API có thể chấp nhận ID token, hoặc chủ thể có quyền admin. |
| `scope` | Những phạm vi nào được cấp? | Có quyền trên mọi đối tượng dữ liệu hoặc tổ chức. |
| `iat` | Token được phát hành lúc nào? | Người dùng vừa xác thực/MFA vào lúc đó. |
| `exp` | Token hết hạn khi nào? | Token chưa từng bị thu hồi trước hạn. |
| `auth_time` | OP xác thực người dùng lúc nào? | Phương thức xác thực chắc chắn đủ mạnh nếu không kiểm policy. |
| `act` | Actor trong token exchange/delegation theo profile là ai? | Đồng nghĩa với `azp` hoặc `client_id`. |

Ví dụ khi AS cấp access token thay mặt người dùng:

~~~text
iss       https://login.example.com
sub       user-742
client_id shop-web
aud       orders-api
scope     orders:read
~~~

Ở đây `sub` là người dùng, `client_id` là ứng dụng, `aud` là API. Nếu AS cấp theo **client credentials**, principal có thể là `inventory-worker` và `sub` có thể đại diện cho chính client theo profile, không có người dùng nào trực tiếp tham gia.

**Không trộn khái niệm authorized party của ID token với authorization của Resource Server.** Một client được cấp token không có nghĩa token cho phép mọi hành động.

## 6. ID token và access token của cùng một lần đăng nhập

### 6.1. ID token gửi cho OIDC Client

Payload minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "shop-web",
  "azp": "shop-web",
  "auth_time": 1893452340,
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

**Bên nhận:** `shop-web`. Client cần kiểm issuer, chữ ký/thuật toán, audience, authorized party khi có, thời gian và các điều kiện OIDC theo luồng như `nonce`.

### 6.2. JWT access token gửi cho Resource Server

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
  "exp": 1893456000,
  "jti": "access-a12f"
}
~~~

**Bên nhận:** `orders-api`. API kiểm access token đúng profile, nguồn phát hành, chữ ký, audience, thời hạn, scope, quyền trên bản ghi và tenant. `client_id` có thể bổ sung chính sách client allowlist nếu ứng dụng cần.

**RFC 9068** định nghĩa JWT Profile for OAuth 2.0 Access Tokens, bao gồm claim `client_id` theo yêu cầu của profile. Nhưng JWT access token **không theo RFC 9068** hoặc token riêng của provider có thể có quy ước khác; chỉ xác minh dựa trên hợp đồng profile và issuer đã chọn.

### 6.3. Opaque access token và introspection

Nếu access token là opaque, Resource Server thường hỏi AS thông qua OAuth 2.0 Token Introspection:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

`client_id` trong RFC 7662 là metadata có thể được trả về, xác định client đã yêu cầu token. Không phải mọi phản hồi introspection đều có tất cả các trường ngoài `active`. API phải tin đúng endpoint AS, bảo vệ TLS, xác thực bên gọi introspection theo chính sách và kiểm audience/scope/trạng thái cần thiết.

### 6.4. Refresh token có vai trò khác

Refresh token gửi từ client tới **token endpoint của Authorization Server** để đổi lấy access token mới. Nó không được gửi tới `orders-api`, dù token ở dạng JWT hay opaque. AS phải kiểm refresh token thuộc grant/client phù hợp, còn hiệu lực và chưa bị revoke hoặc reuse ngoài chính sách rotation.

## 7. Sơ đồ luồng tin cậy và trách nhiệm xác minh

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as OIDC Client (shop-web)
    participant AS as OP / Authorization Server
    participant API as Resource Server (orders-api)
    U->>C: Chọn đăng nhập
    C->>AS: Authorization request + client_id + PKCE + state
    AS->>AS: Kiểm client registration và xác thực người dùng
    AS-->>C: Authorization code
    C->>AS: Đổi code + code_verifier (+ client auth nếu cần)
    AS-->>C: ID token + access token (+ refresh token nếu có)
    C->>C: Xác minh ID token: iss, aud, azp nếu có, exp, nonce...
    C->>API: Bearer access token
    API->>API: Xác minh access token: iss, aud, exp, scope
    API->>API: Kiểm client policy nếu cần, quyền user/tenant/resource
    API-->>C: Chấp nhận hoặc từ chối
~~~

Từ sơ đồ:

1. **AS/OP** biết client đăng ký và xác định token được cấp cho đối tượng nào.
2. **OIDC Client** xác minh ID token cho chính mình, đặc biệt `aud` và `azp` theo OIDC.
3. **Resource Server** xác minh **access token** cho API mình, không dùng ID token làm bằng chứng quyền.
4. Bên nào cầm một bản sao **bearer token** có thể cố gửi lại; `client_id` và `azp` không tự ràng buộc bên gửi.

## 8. Kiểm ID token: audience và authorized party

Pseudocode sau thể hiện **một chính sách xác minh OIDC chặt**. Đây là mô hình, không phải thư viện đầy đủ:

~~~text
function validateIdToken(token, issuer, ownClientId, expectedNonce):
    claims = trustedOidcLibrary.verifyIdToken(
        token = token,
        issuer = issuer,
        allowedAlgorithms = clientConfig.algorithms,
        trustedKeys = clientConfig.issuerKeys
    )
    if claims.invalid:
        reject

    if ownClientId not in claims.aud:
        reject

    if claims.aud contains multiple values AND claims.azp is missing:
        reject  # lựa chọn chính sách chặt, phù hợp khuyến nghị OIDC

    if claims.azp is present AND claims.azp != ownClientId:
        reject

    if claims.exp is expired:
        reject

    if expectedNonce is required AND claims.nonce != expectedNonce:
        reject

    validateRemainingOidcConditions(claims)
    return trustedIdentityContext
~~~

Các kiểm tra như `nonce`, `auth_time`, `acr`, `at_hash`/`c_hash` và chi tiết xử lý token phản hồi phụ thuộc luồng, response type và yêu cầu OIDC; dùng thư viện OIDC uy tín. **Không đủ chỉ Base64URL-decode JWT rồi thấy `azp` khớp**: kẻ tấn công có thể tự viết JSON giả nếu validator không kiểm chữ ký/issuer.

**Điểm tinh tế:** OIDC cho phép token một audience không chứa `azp`. Với token có nhiều audience, đặc tả dùng quy tắc **SHOULD** cho `azp`, nên ví dụ trên là **chính sách strict của ứng dụng**, không phải phát biểu rằng mọi IdP bắt buộc luôn phát `azp` trong mọi token.

## 9. Resource Server kiểm `client_id` thế nào?

API có thể thiết lập chính sách chỉ cho token được cấp cho những client cụ thể thực hiện một hành động, ví dụ:

~~~yaml
resourceServer:
  trustedIssuer: https://login.example.com
  acceptedAudience: orders-api
  acceptedTokenPurpose: access_token

routes:
  "GET /orders/{id}":
    requiredScope: orders:read
    allowedClients: [shop-web, inventory-worker]
    requiredChecks: [resourceOwnership, tenantPolicy]

  "POST /orders/{id}/archive":
    requiredScope: orders:archive
    allowedClients: [inventory-worker]
    requiredChecks: [servicePolicy, tenantPolicy]
~~~

Đây là **mẫu chính sách minh họa**, không phải cấu hình có thể nạp nguyên vẹn vào Spring Security. Nếu API dùng client allowlist, các bước cần thiết:

1. Xác minh access token trước: đúng issuer/khóa hoặc introspection, audience, token purpose, expiry và profile.
2. Lấy `client_id` từ **claims/metadata đã xác minh**, không lấy từ header `X-Client-Id` do caller tự đặt.
3. So với allowlist **gắn với issuer và policy đã cấu hình**.
4. Kiểm scope, role, tenant, quyền trên tài nguyên và mọi điều kiện nghiệp vụ.
5. Nếu muốn xác minh **caller hiện tại** có nắm khóa của client, dùng sender-constrained token như DPoP/mTLS với proof được kiểm đúng, không dựa vào chuỗi `client_id`.

### 9.1. Pseudocode kiểm một request

~~~text
function getOrder(request, orderId):
    access = validateAccessToken(
        bearer = request.Authorization,
        trustedIssuer = "https://login.example.com",
        audience = "orders-api",
        requiredTokenPurpose = "access"
    )

    if access.invalid:
        return 401

    if access.client_id not in approvedClientsForIssuer:
        return 403

    if "orders:read" not in access.scopes:
        return 403

    order = repository.findByTenantAndId(access.trustedTenant, orderId)
    if order is missing:
        return 404

    if not policy.canReadOrder(access.subject, access.trustedTenant, order):
        return 403

    return 200 with allowed order fields
~~~

Đoạn trên giả định đã có tenant context tin cậy và quyền truy cập thông qua policy. Cách lưu tenant trong token hay tra backend là chi tiết triển khai. `client_id` allowlist **chỉ là một điều kiện bổ sung**; endpoint công cộng có thể không cần allowlist riêng nếu đã có chính sách access token/quyền đầy đủ.

### 9.2. Dùng Spring Security đúng vai trò

Spring Security OAuth2 Resource Server có thể xác minh JWT hoặc dùng opaque token introspection. Nếu ứng dụng dùng JWT, thông tin `client_id` có thể đọc từ `Jwt` **sau khi decoder/validator đã kiểm**. Annotation kiểu `hasAuthority('SCOPE_orders:read')` chỉ kiểm scope đã ánh xạ, không kiểm `aud` nếu chưa cấu hình validator, cũng không tự kiểm ownership/tenant.

Nên đặt policy về client ID và quyền bản ghi trong service hoặc authorization layer có thể tái sử dụng; không phân tán điều kiện client ID dưới các controller rồi bỏ sót đường batch/export.

## 10. Những tình huống nhiều client hoặc nhiều dịch vụ

### 10.1. SPA trực tiếp gọi API

~~~text
OAuth client    shop-spa
client type     public
access aud      orders-api
access sub      user-742
client_id       shop-spa
~~~

Vì SPA là public client, `client_id=shop-spa` không chứng minh request HTTP hiện tại chắc chắn do code chính chủ gửi. Token bearer bị lộ có thể được bên khác trình lại. Resource Server vẫn cần xác minh token và permission thực tế.

### 10.2. Backend-for-Frontend

~~~text
OAuth client    shop-bff
client type     confidential
access aud      orders-api
access sub      user-742
client_id       shop-bff
~~~

Người dùng dùng giao diện browser nhưng OAuth client thực tế có thể là **BFF server**. API thấy `client_id=shop-bff`, không nhất thiết thấy tên ứng dụng JavaScript. BFF có thể lưu token phía server và cấp session cookie cho browser theo chính sách của nó.

### 10.3. Client credentials

~~~text
OAuth client    inventory-worker
grant type      client_credentials
access aud      orders-api
access sub      inventory-worker  (theo profile minh họa)
client_id       inventory-worker
scope           orders:sync
~~~

Không có end user được xác thực trong ví dụ này. Resource Server cần áp dụng **service principal permissions**, không gán role của một người dùng bằng cách suy diễn từ client ID.

### 10.4. Token exchange và actor

Trong kiến trúc service A gọi service B **thay mặt người dùng**, Authorization Server có thể hỗ trợ OAuth 2.0 Token Exchange (RFC 8693). Token mới có thể có subject/actor và client ID theo profile.

~~~text
sub       user-742
client_id service-a
act       { sub: service-a }   # minh họa actor theo hợp đồng
aud       service-b-api
scope     invoice:read
~~~

**`act`, `azp` và `client_id` không phải ba tên thay thế nhau.** Actor phản ánh thực thể đang hành động trong ngữ cảnh delegated token theo chuẩn/hợp đồng; client ID mô tả client đã xin/cấp token; `azp` có ngữ nghĩa OIDC ID token. API B cần kiểm audience B, chuỗi ủy quyền phù hợp, scope và quyền trên dữ liệu.

### 10.5. Nhiều issuer và tenant

Nếu hệ thống tin nhiều IdP, hai token cùng `client_id=shop-web` vẫn có thể thuộc hai client khác nhau. API phải kiểm `iss` và profile trước khi ánh xạ client ID sang chính sách. Trong ứng dụng nhiều tenant, **client ID không phải tenant ID**; quyền phải được kiểm theo cặp principal–tenant và tài nguyên thực tế.

### 10.6. Claim riêng của provider

Có provider dùng `appid`, `cid`, `azp` hoặc tên claim riêng trong access token cho danh tính ứng dụng. Không có quy tắc chung “thiếu `client_id` thì cứ lấy `azp`”. Hãy ghi rõ **issuer, phiên bản token, profile, tên claim, ngữ nghĩa và bên dùng claim** trước khi triển khai.

## 11. Lỗ hổng thường gặp khi hiểu sai các claim

| Lỗi | Tác động | Phòng chống |
|---|---|---|
| Coi `client_id` là bí mật | Caller khai tên của ứng dụng khác để giả danh | Dùng client authentication khi phù hợp; client ID đơn lẻ chỉ là định danh |
| Tin `X-Client-Id` do client gửi | Request có thể giả ứng dụng đặc quyền | Chỉ tin metadata token xác minh hoặc nguồn nội bộ đã xác thực |
| Chỉ decode JWT rồi tin claims | Kẻ tấn công tự đặt `client_id`/`azp`/`sub` | Xác minh chữ ký, issuer, khóa, thuật toán, thời gian và token profile |
| Kiểm `client_id` nhưng bỏ `aud` | Token dành cho API khác bị chấp nhận | Kiểm audience chứa Resource Server hiện tại |
| Nhận ID token như access token | Token có `azp` đúng nhưng không cấp quyền API | Tách ID-token validator và access-token validator |
| Bỏ kiểm `azp` ở ID token đa audience | Nhầm client được phát hành token | Tuân quy tắc OIDC, dùng strict policy khi cần |
| Coi `azp` là role/scope | Cấp quyền admin vì authorized party khớp | Áp quyền bằng access token và policy nghiệp vụ |
| Coi `sub` luôn là user | Token client credentials bị cấp quyền người dùng | Phân biệt principal type, grant và token profile |
| Chỉ check scope mà không check tài nguyên | IDOR/BOLA, rò dữ liệu tenant khác | Kiểm ownership/tenant tại service, truy vấn dữ liệu đúng phạm vi |
| Client bị vô hiệu nhưng token cũ còn hạn | API vẫn chấp nhận JWT theo chữ ký/`exp` | TTL, kiểm trạng thái hoặc revocation khi yêu cầu |
| Cho rằng `client_id` chống token replay | Attacker dùng lại bearer token bị lộ | Bảo vệ token, DPoP/mTLS khi cần, thu hồi và giám sát |

### 11.1. Token bị đánh cắp vẫn giữ nguyên client ID

Giả sử `shop-web` nhận access token hợp lệ, nhưng token xuất hiện trong access log rồi bị kẻ khác lấy. Nếu attacker gửi nguyên bearer token tới `orders-api`, mọi claim, kể cả `client_id=shop-web`, vẫn giữ nguyên. Chữ ký JWT vẫn đúng; opaque token có thể vẫn introspect active.

Vì vậy **`client_id` mô tả ngữ cảnh cấp token**, không phải bằng chứng về bên gửi hiện tại. Cần kết hợp:

- HTTPS và lưu trữ token an toàn theo loại client;
- Không để token vào URL, log, analytics hoặc crash report;
- TTL access token ngắn, scope và audience tối thiểu;
- Refresh token rotation và phát hiện reuse;
- Thu hồi hoặc kiểm trạng thái khi nghi ngờ compromise;
- DPoP/mTLS sender-constrained token với proof/binding được Resource Server kiểm thực tế;
- Kiểm authorization tài nguyên, tenant và nghiệp vụ ở mỗi request.

`jti` nếu có chỉ định danh token; **nó không tự chống replay** nếu không có cơ chế trạng thái/chống phát lại tương ứng.

## 12. Vòng đời client ID trong access/refresh token

### 12.1. Phát hành

AS xác định client đã đăng ký, grant được phép, chủ thể liên quan, audience/scope và thời hạn token. Với OIDC, OP quyết định ID token được phát hành cho client nào và điền `aud`/`azp` theo quy tắc. Với access token, issuer xác định `client_id` và các claim theo profile của Resource Server.

### 12.2. Refresh

Client dùng refresh token tại AS. AS kiểm binding với client/grant, trạng thái và chính sách rotation trước khi cấp access token mới. Một access token vừa refresh có `iat` mới nhưng **không có nghĩa user vừa đăng nhập hoặc MFA lại**; cũng không đảm bảo role/tenant vẫn có quyền nếu hệ thống không kiểm cập nhật.

### 12.3. Vô hiệu hóa client hoặc thu hồi quyền

Nếu `shop-web` bị khóa tại AS, AS có thể ngăn cấp token mới. Tuy nhiên, access JWT đã phát hành vẫn có thể được API kiểm cục bộ chấp nhận đến `exp` nếu không có trạng thái bổ sung. Tùy nhu cầu thu hồi nhanh, API/AS dùng TTL ngắn, token revocation, denylist, introspection hoặc kiểm trạng thái client/grant.

**Thu hồi refresh token ngăn xin token mới nhưng không mặc định vô hiệu hóa mọi access JWT đang còn hạn.** Cache introspection có thể làm chậm hiệu lực khi opaque token bị revoke.

## 13. Bảng tình huống quyết định

Giả sử OIDC Client là `shop-web`, API là `orders-api`, yêu cầu scope `orders:read`.

| Token hoặc request | Bên xác minh | Kết luận |
|---|---|---|
| ID token có `aud=shop-web`, `azp=shop-web`, chữ ký/issuer hợp lệ | `shop-web` | Có thể nhận nếu mọi kiểm tra OIDC còn lại đạt |
| ID token chỉ có `aud=shop-web`, không có `azp` | `shop-web` | Không tự từ chối chỉ vì thiếu `azp` |
| ID token có `aud=["shop-web","partner-web"]` và `azp=shop-web` | `shop-web` | Đạt kiểm aud/azp nếu token còn hợp lệ |
| Cùng ID token gửi tới `partner-web` | `partner-web` | Từ chối khi `azp` không khớp client |
| ID token `aud=shop-web` được gửi tới `orders-api` như access token | API | Từ chối: sai mục đích và audience |
| Access JWT có `aud=orders-api`, `client_id=shop-web` và scope đọc | API | Còn phải kiểm issuer, thời gian, quyền tài nguyên |
| Access JWT có `aud=billing-api` nhưng `client_id=shop-web` | Orders API | Từ chối: sai audience |
| Access token đúng client/scope nhưng đơn thuộc người dùng khác | Orders API | Từ chối: không đủ quyền trên đối tượng |
| Opaque token active với `client_id=shop-web`, thiếu metadata audience/scope cần thiết | API | Từ chối nếu không đủ căn cứ cấp quyền |
| Bearer token bị sao chép có `client_id=shop-web` | API | Vẫn có nguy cơ replay đến khi hết hạn/thu hồi nếu không sender-bound |
| Token client credentials có `sub=inventory-worker` | API | Áp dụng service principal policy, không tự coi là end user |

## 14. Bài tập thực hành

### Bài 1 — Phân tích hai token

**Token A (ID token):**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["shop-web", "partner-web"],
  "azp": "shop-web",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

**Token B (access token):**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Câu hỏi và gợi ý:

1. **Ai nên nhận Token A?** OIDC Client `shop-web`, sau khi xác minh toàn bộ OIDC; `partner-web` không nên nhận vì `azp` không khớp.
2. **API `orders-api` có dùng Token A làm Bearer không?** Không, đó là ID token dành cho client.
3. **Token B có cho phép `DELETE /orders/42` không?** Không vì thiếu scope xóa; còn cần quyền bản ghi.
4. **`client_id=shop-web` có chứng minh request đang do code `shop-web` gửi không?** Không, bearer token có thể bị sao chép.
5. **`sub=user-742` là client ID không?** Không, đó là subject theo nghĩa token/profile.

### Bài 2 — Chọn validator

~~~text
OIDC Client nhận ID token:
  verify signature/algorithm and trusted issuer
  check own client_id in aud
  check azp when present; handle multiple aud under OIDC policy
  check exp, nonce and all flow-specific conditions

Resource Server nhận JWT access token:
  verify access token type/profile, issuer, signature, keys
  verify aud for this API and exp/nbf
  apply client_id allowlist only if policy requires it
  check scope, tenant and resource-level permissions

Resource Server nhận opaque access token:
  introspect via trusted AS with protected connection
  verify active, audience, scope and required metadata
  check tenant and resource-level permissions
~~~

Hãy thử bỏ một dòng rồi xác định lỗi: bỏ `aud` có thể chấp nhận token của API khác; bỏ `azp` trong luồng đa audience có thể nhầm authorized party; bỏ resource policy dẫn đến IDOR/BOLA.

### Bài 3 — Kiểm thử âm tính

1. HTTP request chỉ khai `client_id=admin-app` mà không có token.
2. JWT bị sửa payload `client_id` nhưng chữ ký không được tạo lại.
3. Access token đúng `client_id` nhưng issuer không thuộc nguồn tin cậy.
4. ID token đa audience có `azp` trỏ sang client khác.
5. ID token hợp lệ bị gửi tới Resource Server.
6. Access token có đúng client ID nhưng sai audience.
7. Client credentials token bị cấp quyền người dùng.
8. API cho phép một client đã đăng ký nhưng không kiểm scope hoặc tenant.
9. Bearer token bị đánh cắp và phát lại.
10. Client bị vô hiệu hóa nhưng JWT còn hạn; kiểm chính sách thu hồi thực tế.

## 15. Checklist triển khai

- [ ] Xác định đúng OAuth client, issuer, Resource Server và principal; không trộn các vai trò.
- [ ] `client_id` dùng làm **định danh**, không dùng làm secret hay bằng chứng caller có token hợp pháp.
- [ ] Phân biệt public/confidential client, PKCE và phương thức client authentication.
- [ ] Với ID token, kiểm `aud` chứa client ID của mình, `azp` khi có; xử lý token đa audience theo OIDC và chính sách rõ ràng.
- [ ] Không giả định mọi ID token bắt buộc có `azp`.
- [ ] Không tự gán nghĩa OIDC ID token của `azp` cho mọi access token.
- [ ] Với access token, kiểm issuer, chữ ký/JWKS hoặc introspection, audience, expiry, loại token và scope.
- [ ] Nếu áp dụng client allowlist, dùng `client_id` đã xác minh cùng issuer; không tin header/body client tự gửi.
- [ ] Kiểm role, tenant và quyền tài nguyên dù client ID nằm trong allowlist.
- [ ] Không dùng ID token hoặc refresh token thay access token dành cho API.
- [ ] Có chính sách client revoked, refresh token rotation, TTL và xử lý claims cũ.
- [ ] Bảo vệ bearer token khỏi lộ và replay; dùng sender-constrained token khi cần.
- [ ] Kiểm thử nhiều issuer, nhiều client, đa audience, sai `azp`, sai `aud`, sai scope và BOLA/IDOR.

**Ghi nhớ:** `client_id` cho biết **OAuth client**, `azp` trong **OIDC ID token** xác định **authorized party được cấp ID token**, `aud` là **bên nhận token**, `sub` là **chủ thể**, còn `scope` là **phạm vi được cấp**. Chỉ tin các claim sau khi đã xác minh token và ngữ cảnh. Một client ID hoặc authorized party hợp lệ không tự chứng minh quyền truy cập tài nguyên và không chống được bearer token bị đánh cắp/phát lại.

### Tài liệu chuẩn tham khảo

- **RFC 6749** — The OAuth 2.0 Authorization Framework: client registration, `client_id`, grant, scope và access/refresh token.
- **RFC 7636** — Proof Key for Code Exchange (PKCE).
- **OpenID Connect Core 1.0** — ID token, audience, `azp` và quy tắc xác minh OIDC.
- **RFC 7519** — JSON Web Token (JWT), các claim `iss`, `sub`, `aud` và thời gian.
- **RFC 9068** — JWT Profile for OAuth 2.0 Access Tokens, gồm `client_id`.
- **RFC 7662** — OAuth 2.0 Token Introspection.
- **RFC 8693** — OAuth 2.0 Token Exchange, actor/delegation.
- **RFC 8725** — JSON Web Token Best Current Practices.
- **RFC 6750** — OAuth 2.0 Bearer Token Usage.
- **RFC 9449** — OAuth 2.0 Demonstrating Proof of Possession (DPoP).
- **RFC 9700** — Best Current Practice for OAuth 2.0 Security.
