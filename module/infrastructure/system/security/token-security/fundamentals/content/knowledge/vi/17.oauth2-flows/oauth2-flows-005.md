# Refresh Token Grant

Trong một ứng dụng bán hàng, người dùng đăng nhập bằng OAuth 2.0/OpenID Connect (OIDC) để xem đơn hàng. Authorization Server cấp **access token** chỉ có hiệu lực 10 phút và một **refresh token** theo chính sách của client. Sau 10 phút, browser/BFF vẫn có thể đang có một phiên ứng dụng hợp lệ, nhưng access token cũ đã hết hạn. Ứng dụng không nhất thiết phải đưa người dùng qua màn hình đăng nhập lần nữa: **OAuth 2.0 Refresh Token Grant** cho phép một OAuth client trình refresh token hợp lệ tại **token endpoint của Authorization Server** để xin access token mới trong phạm vi đã được ủy quyền.

Điểm quan trọng: refresh token **không phải một access token dài hạn**. Nó là credential có giá trị cao, được trình **cho Authorization Server**, không phải cho Resource Server. Authorization Server phải kiểm client, grant, quyền, trạng thái và ràng buộc bảo mật trước khi phát hành token mới. Trong nhiều thiết kế, refresh token còn được **xoay vòng** để phát hiện bản sao bị đánh cắp và tái sử dụng.

Một flow được triển khai sai có thể biến refresh token bị lộ thành khả năng lấy access token mới liên tục, mở rộng `scope`/`aud` trái phép, hoặc gây logout hàng loạt khi nhiều request đồng thời dùng một refresh token đã bị rotate.

Bài thuộc chương **OAuth2 flows** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là Refresh Token Grant trong vòng đời token bảo mật, liên hệ JWT/opaque token, access/refresh token, xác thực và phân quyền OAuth 2.0/OIDC, kiểm claims/scope/audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Refresh Token Grant** dùng để làm gì và phân biệt nó với Authorization Code Grant, Client Credentials và thao tác đăng nhập lại.
2. Mô tả đầy đủ request `grant_type=refresh_token`, yêu cầu xác thực client và token response.
3. Phân biệt **access token**, **refresh token**, **ID token** và **browser/server session** trong một phiên sử dụng.
4. Nêu các giới hạn scope, audience, resource, client binding và grant khi phát hành access token mới.
5. Thiết kế **refresh token rotation**, **reuse detection**, token family, thu hồi và vòng đời idle/absolute.
6. Xử lý đồng thời nhiều request refresh trong BFF, ứng dụng nhiều instance và khi có lỗi mạng.
7. Bảo vệ token phía client và Authorization Server, bao gồm confidential/public client, DPoP hoặc mTLS khi áp dụng.
8. Phân tích lỗi `invalid_grant`, refresh token bị đánh cắp, token substitution, stale claims và các tình huống kiểm thử.

## 2. Refresh Token Grant giải quyết vấn đề nào?

### 2.1. Access token nên có tuổi thọ giới hạn

Access token thường là bearer credential được Resource Server chấp nhận khi đúng issuer, audience, scope, thời hạn và quyền tài nguyên. Nếu token bị lộ qua log, thiết bị hoặc JavaScript bị tấn công, kẻ giữ bản sao có thể thử dùng nó đến khi hết hạn hoặc bị vô hiệu hóa.

Giới hạn `exp` giúp thu hẹp cửa sổ bị lạm dụng, nhưng khiến client phải có cách lấy token mới để duy trì trải nghiệm người dùng hoặc công việc đang chạy.

**Refresh Token Grant** tách hai nhiệm vụ:

- **Access token:** cho phép gọi Resource Server đúng `aud` và `scope` trong khoảng thời gian tương đối ngắn.
- **Refresh token:** credential được Authorization Server cấp cho client để xin access token mới **theo grant và chính sách đã được cấp**, không nhất thiết yêu cầu Resource Owner tương tác lại mỗi lần.

### 2.2. Một ví dụ cụ thể

~~~text
Issuer:              https://login.example.com
OAuth client:        shop-bff
Principal:           user-742
Resource Server:     orders-api
Authorized scopes:   orders:read
Access token TTL:    10 phút (minh họa)
Refresh token:       R1 do AS quản lý

09:00  Đăng nhập/ủy quyền; AS cấp A1 và R1.
09:08  BFF vẫn gọi orders-api bằng A1 còn hạn.
09:11  A1 hết hạn; BFF xin access token mới bằng R1.
09:11  AS kiểm R1/client/grant; có thể cấp A2 và R2.
09:12  BFF dùng A2 gọi orders-api; R2 ở lại server-side store.
~~~

**Không có dòng nào yêu cầu gửi `R1` hoặc `R2` đến Orders API.** Resource Server chỉ nhận access token dành cho nó; refresh token chỉ tới token endpoint của AS.

### 2.3. Những điều Refresh Token Grant không làm

- Không tự đăng nhập lại Resource Owner, không chứng minh user vừa thực hiện MFA hay vừa consent.
- Không tự nâng cấp scope, audience, tenant hoặc role.
- Không làm browser session tại ứng dụng/Identity Provider sống mãi.
- Không phải cơ chế bảo đảm access token cũ lập tức bị thu hồi.
- Không thay thế việc Resource Server kiểm access token và quyền trên từng đối tượng.
- Không phải mọi grant đều có refresh token; **AS có quyền quyết định có cấp hay không** theo loại client và chính sách.
- Không bảo đảm refresh token tồn tại mãi hoặc còn hợp lệ cho mọi lần xin token.

## 3. Bốn vai trò và hai đường sử dụng token

| Vai trò OAuth 2.0 | Việc thực hiện |
|---|---|
| **Resource Owner (RO)** | Chủ thể có thẩm quyền cho phép truy cập tài nguyên. Trong luồng có người dùng, có thể là end user hoặc người đại diện được ủy quyền. |
| **OAuth Client** | Ứng dụng đã đăng ký, nhận và bảo vệ refresh token; thực hiện Refresh Token Grant theo cấu hình. |
| **Authorization Server (AS)** | Kiểm client/grant/refresh token, áp chính sách, phát access token mới, có thể rotate refresh token. |
| **Resource Server (RS)** | Nhận access token, kiểm `iss`, `aud`, `exp`, `scope`/permission, trạng thái nếu cần và quyền với tài nguyên. |

Sơ đồ ranh giới:

~~~mermaid
flowchart LR
    RO[Resource Owner / End User]
    C[OAuth Client / BFF]
    AS[Authorization Server]
    RS[Resource Server]

    RO -->|Cấp quyền / đăng nhập ở flow ban đầu| AS
    C -->|Refresh token R1 tới token endpoint| AS
    AS -->|Access token A2, có thể Refresh R2| C
    C -->|Access token A2 tới API| RS
    RS -. Không nhận refresh token .-> AS
~~~

**OAuth client** có thể là backend `shop-bff`, mobile app hoặc SPA; chiến lược bảo vệ refresh token khác nhau theo loại client. **AS** mới là bên quyết định token cấp tiếp. **RS** không dùng refresh grant để tự gia hạn một JWT access token đã hết hạn.

### 3.1. Refresh token liên kết với client/grant, không phải một “vé trống”

Theo OAuth 2.0, refresh token được phát hành cho client và gắn với grant/authorization phù hợp. Khi client trình refresh token, AS phải xác minh binding theo các điều kiện của grant, chẳng hạn:

~~~text
token family / grant       grant-81f
client_id                  shop-bff
principal/sub              user-742
authorized resource        orders-api
authorized scope           orders:read
issuer                     https://login.example.com
refresh status             active
client status              active
rotation version           3
grant permissions          currently permitted by policy
~~~

Các trường là **mô hình logic minh họa**, không phải payload bắt buộc của refresh token. Nếu client khác lấy R1 rồi tự khai `client_id=partner-web`, AS không được cấp access token mới cho client đó chỉ vì R1 trông hợp lệ.

## 4. Vòng đời một Refresh Token Grant

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant C as OAuth Client / BFF
    participant AS as Authorization Server
    participant DB as Refresh Token / Grant Store
    participant API as Resource Server

    U->>C: Sử dụng ứng dụng
    C->>AS: Authorization Code + PKCE (flow ban đầu)
    AS->>DB: Tạo grant, lưu token state
    AS-->>C: Access A1 + Refresh R1 (nếu được cấp)
    C->>API: Bearer A1, aud đúng API
    API-->>C: Kết quả khi A1 hợp lệ
    Note over C: A1 gần hết hạn hoặc đã hết hạn
    C->>AS: POST /token, grant_type=refresh_token, R1
    AS->>DB: Kiểm R1, client, grant, revoke, expiry, policy
    DB-->>AS: Active, authorized
    AS->>DB: Atomic rotate R1 -> R2 nếu áp dụng
    AS-->>C: Access A2, có thể Refresh R2
    C->>C: Lưu token mới an toàn
    C->>API: Bearer A2
    API->>API: Xác minh A2 và quyền hiện tại
    API-->>C: Kết quả / từ chối
~~~

Sơ đồ biểu thị một trường hợp phổ biến, **không phải AS nào cũng rotate refresh token ở mỗi lần sử dụng**. Trong nhiều môi trường, rotate hoặc ràng buộc refresh token với khóa client là yêu cầu quan trọng của hồ sơ bảo mật; ở phần sau sẽ phân biệt chính sách và loại client.

### 4.1. Khác Authorization Code Grant ở điểm nào?

**Authorization Code Grant** thường được dùng để có grant và token ban đầu sau khi người dùng đã được xác thực/ủy quyền. Client nhận authorization code rồi đổi code bằng PKCE và có thể client authentication.

**Refresh Token Grant** dùng **refresh token đã cấp** trong một grant hợp lệ để xin access token mới, thường không cần mở lại authorization UI. Nó không chở authorization code hoặc `code_verifier` của lần login trước. PKCE là cơ chế bảo vệ **authorization code**, không phải bằng chứng sở hữu refresh token.

### 4.2. Khác Client Credentials Grant ra sao?

Với Client Credentials, client xin token bằng danh tính/quyền của **dịch vụ**, thường chỉ cần lặp lại grant tại AS khi access token hết hạn. **Thông thường không cần phát refresh token cho Client Credentials**, và RFC 6749 nêu refresh token **SHOULD NOT** được cấp trong response của grant này.

Nếu nhà cung cấp có cơ chế khác theo profile, phải kiểm hợp đồng rõ ràng; không giả định có một refresh token gắn với end user khi không có end user.

## 5. Request `grant_type=refresh_token`

Client gửi **HTTP POST** tới **token endpoint** qua TLS, với payload thường là `application/x-www-form-urlencoded`.

### 5.1. Confidential client: xác thực client tại token endpoint

Ví dụ dùng HTTP Basic cho client có credentials, chỉ để minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <illustrative-client-authentication>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&
refresh_token=R1_EXAMPLE_ONLY
~~~

Trong thực tế cần URL-encode form đúng chuẩn; body trên được xuống dòng để dễ đọc. Confidential client **phải được AS xác thực** bằng phương thức đã đăng ký khi áp dụng. Có thể dùng client secret Basic, `private_key_jwt` hoặc mTLS; Basic không phải phương pháp duy nhất và bí mật thực tế **không được ghi vào tài liệu/log**.

`refresh_token` là **required** trong Refresh Token Grant; `grant_type` phải đúng chính xác `refresh_token`.

### 5.2. Public client: không có bí mật đáng tin trên thiết bị

Public client như ứng dụng mobile hoặc SPA không thể bảo vệ client secret nhúng trong mã phân phối cho người dùng như confidential client. Một request minh họa khi AS đã đăng ký public client:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&
refresh_token=R1_PUBLIC_EXAMPLE&
client_id=shop-mobile
~~~

Khi public client không xác thực bằng client authentication, AS cần client ID để nhận diện client/grant theo yêu cầu OAuth 2.0. **`client_id` không phải mật khẩu** và chỉ gửi đúng chuỗi client ID không chứng minh thiết bị đang giữ token hợp lệ. AS còn phải kiểm refresh token được cấp **cho client đó**, trạng thái và cơ chế bảo vệ rotation/sender-binding.

Nhiều public client hiện đại cần **refresh token rotation hoặc sender-constrained refresh token** theo OAuth 2.0 Security BCP; không được xem ví dụ HTTP này là cấu hình bảo mật đầy đủ.

### 5.3. Tham số tùy chọn `scope`

Một request có thể chỉ yêu cầu **phạm vi đã cấp hoặc phạm vi hẹp hơn**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=R1_EXAMPLE_ONLY&
scope=orders%3Aread
~~~

Theo RFC 6749, `scope` khi refresh là **optional**; nếu có, phạm vi yêu cầu **không được chứa scope ngoài phạm vi grant ban đầu**. Nếu không có, nó được hiểu theo phạm vi đã cấp ban đầu, vẫn phải chịu chính sách hiện hành. AS có thể hạn chế hoặc từ chối do quyền đã thay đổi.

**Không cần** truyền lại `scope` ở mọi refresh; cần tuân thủ hợp đồng AS và giữ rõ scope được cấp.

### 5.4. Có thể yêu cầu resource/audience không?

**RFC 8707** mô tả tham số `resource` cho các yêu cầu token phù hợp và được AS hỗ trợ. Ví dụ minh họa:

~~~text
grant_type=refresh_token
refresh_token=R1_EXAMPLE_ONLY
resource=https://api.example.com/orders
scope=orders:read
~~~

AS **không được** vì thấy `resource` mới mà phát access token cho mọi API tùy ý. Resource đích phải phù hợp **grant, client registration, chính sách AS và phạm vi đã được ủy quyền**. Tùy provider, việc đổi `resource` khi refresh có thể bị cấm, được phép trong một tập đã ủy quyền hoặc yêu cầu token mới/authorization flow khác.

`aud` trong access token là **quyết định phát hành của AS**. Không nhất thiết `resource` bằng nguyên văn chuỗi `aud`. Khi phải chuyển quyền sang API khác hoặc thay actor/delegation, có thể cần một grant khác hoặc token exchange được AS kiểm soát; không mở rộng grant bằng cách thay chuỗi resource.

## 6. Response khi refresh thành công

### 6.1. Trường hợp refresh token rotation

Một response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "A2_EXAMPLE_ONLY",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "R2_EXAMPLE_ONLY",
  "scope": "orders:read"
}
~~~

Theo OAuth 2.0, response thành công **phải có access token và token type**; `expires_in` được khuyến nghị, `refresh_token` có thể xuất hiện, và `scope` được trả về khi phạm vi được cấp khác phạm vi yêu cầu theo quy tắc. Header `Cache-Control: no-store` và `Pragma: no-cache` bảo vệ response chứa token/credentials.

Nếu AS phát `R2` thay `R1`, client phải:

1. Coi `R2` là refresh token mới cho grant/family tương ứng.
2. Cập nhật token store bằng cơ chế phù hợp và **không tiếp tục sử dụng `R1`**.
3. Xử lý lỗi ghi token theo chính sách, vì sử dụng lại `R1` có thể bị AS xem là reuse.
4. Giữ `A2` ở phía client/server phù hợp, không lộ token qua log hoặc crash report.

### 6.2. Trường hợp không trả refresh token mới

AS có thể trả response không chứa `refresh_token`:

~~~json
{
  "access_token": "A2_EXAMPLE_ONLY",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Trong một profile không rotate, client có thể tiếp tục dùng refresh token hiện hành **nếu AS vẫn cho phép**. Nhưng không được kết luận “không có trường `refresh_token` tức R1 mãi hợp lệ”: grant có thể bị thu hồi, hết hạn hoặc AS dùng chính sách khác. Client phải bám theo quy tắc phát hành/rotation đã thỏa thuận.

### 6.3. `scope` trong response không phải dữ liệu trang trí

Nếu AS giảm scope sau khi người dùng bị hạ quyền, access token mới có thể chỉ được phép `orders:read` thay vì `orders:read orders:create`. Client không được dùng scope cũ/role trong session để giả định token mới vẫn đủ quyền tạo đơn.

Với JWT, `scope` có thể nằm trong token claims; với opaque token, RS lấy metadata qua introspection. Cả hai phải phản ánh **scope AS thực sự cấp** theo profile.

### 6.4. OIDC có thể trả ID token trong refresh response không?

Trong OIDC, khi refresh một grant liên quan xác thực người dùng, OP **có thể** trả `id_token` mới theo quy tắc của OpenID Connect Core. Không được mặc định mọi refresh response luôn có ID token, và `id_token` mới **không tự chứng minh người dùng vừa xác thực lại**.

Nếu ID token được trả về, OIDC Client cần xác minh theo quy tắc refresh/OIDC profile: đúng `iss`, `aud`, `sub` và các điều kiện tương ứng. Không gửi ID token tới Resource Server thay access token. Nếu ứng dụng cần MFA mới hoặc `auth_time` đủ gần, cần **reauthentication/step-up** phù hợp thay vì dùng `iat` mới của token.

## 7. Authorization Server phải kiểm gì trước khi cấp A2?

Đây là phần quyết định an ninh. AS không chỉ kiểm `R1` “có tồn tại trong database hay không”.

| Điều kiện | Ví dụ xác minh | Nguy cơ nếu bỏ |
|---|---|---|
| **Token endpoint và TLS** | Chỉ nhận qua HTTPS tại AS tin cậy | Rò refresh token khi truyền. |
| **Client identity** | Đúng client đăng ký; confidential client authentication khi yêu cầu | Client khác dùng token không thuộc grant của mình. |
| **Grant binding** | R1 gắn với `client_id=shop-bff` và grant `grant-81f` | Token bị tráo giữa ứng dụng/phiên. |
| **Refresh token validity** | Random token lookup/cryptographic proof hợp lệ, chưa revoke/expired | Token giả hoặc đã chết được dùng lại. |
| **Rotation/reuse policy** | R1 đang active, chưa spent; kiểm family/sequence | Bỏ lọt token bị đánh cắp hoặc xử lý sai bản sao. |
| **Sender binding khi áp dụng** | DPoP proof/mTLS key/cert đúng confirmation/binding | Token bị sao chép có thể dùng ngoài thiết bị/client. |
| **Client/grant status** | Client active, grant/consent chưa bị revoke | Tiếp tục cấp token cho ứng dụng bị khóa. |
| **Principal/tenant policy** | User còn active, membership/quyền phù hợp theo policy | Duy trì scope/tenant đã bị thu hồi. |
| **Scope** | Requested scope không vượt scope ban đầu/current policy | Leo thang quyền. |
| **Audience/resource** | Resource nằm trong grant và client allowed resources | Cấp access token cho API khác. |
| **TTL và security policy** | Access token expires theo risk/client/resource limits | Token mới dài hạn hoặc không kiểm trạng thái. |
| **Rate limits/anomaly** | Quá nhiều lần refresh, token reuse, vị trí/rủi ro lạ | Credential stuffing, brute force hoặc replay. |

### 7.1. Pseudocode phía Authorization Server

~~~text
function refreshGrant(request, authenticatedClient):
    assert request.grant_type == "refresh_token"
    assert request.refresh_token present
    assert tls_and_token_endpoint_policy_valid

    client = resolveAndAuthenticateClient(authenticatedClient, request)
    if client invalid or disabled:
        reject according to OAuth client error policy

    token = findAndVerifyRefreshCredential(request.refresh_token)
    if token invalid, expired or revoked:
        reject invalid_grant

    if token.client_id != client.id:
        reject invalid_grant
    if senderBindingRequired(token) and !verifyProofOfPossession(token, request):
        reject

    with atomicFamilyTransaction(token.family_id):
        latest = readCurrentFamilyAndGrantState(token.family_id)

        if token is spent or not latest.current:
            handleReuseSignalAndRevokeFamilyPerPolicy()
            reject invalid_grant

        if grant revoked or principal/client policy disallows refresh:
            reject invalid_grant

        authorizedScopes = policy.allowedScopes(client, grant, resource)
        requestedScopes = request.scope or grant.originallyGrantedScopes
        if requestedScopes exceed grant or policy:
            reject invalid_scope or invalid_grant per context

        target = resolveResourceWithinOriginalGrant(request.resource)
        if target not permitted:
            reject invalid_target per supported profile

        newAccess = issueAccessToken(
            issuer = configuredIssuer,
            client = client,
            subject = grant.principal,
            audience = target.canonicalAudience,
            scopes = approvedScopes,
            ttl = policy.accessTokenTtl
        )

        if rotationPolicyEnabled:
            newRefresh = generateNewSecureRefreshToken()
            atomicallyMarkOldSpentAndPersistNew(newRefresh, token.family_id)
        else:
            newRefresh = none

        commit()
    return oauthTokenResponse(newAccess, newRefresh, approvedScopes)
~~~

**Pseudocode minh họa**: không đầy đủ mọi kiểu lỗi, cơ chế khóa/transaction hoặc sender-binding chuẩn. Trong thực tế, kiểm client authentication diễn ra trước/đồng thời với kiểm grant theo OAuth; việc xử lý `invalid_scope`, `invalid_target` hay `invalid_grant` phụ thuộc tình huống và profile. **Không log raw R1** để điều tra.

### 7.2. Giới hạn không được vượt khi refresh

~~~text
newIssuedScopes ⊆ originallyGrantedScopes
newIssuedScopes ⊆ currentlyAllowedScopesByPolicy
newIssuedAudience ∈ originallyAuthorizedResourcesAndClientPolicy
newAccessToken.exp <= AS_currentPolicyLimit
clientOfRefreshRequest == clientBoundToRefreshGrant
~~~

Nếu AS cho phép **downscoping** bằng refresh, token mới có thể có quyền ít hơn token trước. Không cho phép “nâng quyền qua refresh” chỉ nhờ bổ sung `scope=admin`, đổi `resource=payments-api` hoặc sửa `tenant_id` trong form.

### 7.3. Access token mới phải có claims được quyết định lại

Ví dụ JWT access token A1:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read orders:create",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

Nếu user bị hạ quyền sau đó, A2 có thể là:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "iat": 1893453000,
  "exp": 1893453600
}
~~~

Các timestamp chỉ minh họa, không phải JWT đã ký. `iat` mới thể hiện **thời điểm token được phát hành**, **không phải thời điểm user vừa đăng nhập lại**. AS/RS cần chiến lược xử lý stale permissions nếu dữ liệu quyền có thể thay đổi trong thời gian sống của JWT.

## 8. Refresh token rotation và token family

**Refresh token rotation** là cơ chế mỗi lần refresh thành công, AS phát refresh token mới, đánh dấu token cũ đã dùng/hết hiệu lực, và giữ quan hệ token trong cùng một **token family/grant**.

Ví dụ:

~~~text
Initial issuance:
    R1 (active)      -> access A1

First refresh:
    R1 (spent)
    R2 (active)      -> access A2

Second refresh:
    R2 (spent)
    R3 (active)      -> access A3

Suspicious reuse:
    R1 presented again
    AS detects spent token and responds per reuse policy
~~~

### 8.1. Reuse detection hoạt động ra sao?

Nếu một refresh token đã bị rotate được trình lại, AS không thể mặc nhiên biết chính xác bên nào là chủ hợp pháp và bên nào là attacker. Vì vậy các triển khai rotation có thể **thu hồi token family đang active** và yêu cầu client/user xác thực lại, nhằm giảm nguy cơ kẻ có bản sao tiếp tục lấy token mới.

**Điểm tinh tế:** chính ứng dụng có thể vô tình dùng lại R1 vì hai request đồng thời hoặc crash. Một tín hiệu reuse không luôn chứng minh có tấn công, nhưng nó là sự kiện cần xử lý an toàn. Đừng tắt reuse detection chỉ để tránh logout.

### 8.2. Cần thao tác trạng thái nguyên tử ở AS

Giả sử hai request cùng trình R1 gần nhau. Nếu AS chỉ:

~~~text
1. SELECT token WHERE status=active
2. issue new token
3. UPDATE old token status=spent
~~~

mà không bảo vệ race, cả hai request có thể đọc “active” trước bước UPDATE và được cấp hai refresh token mới. Hậu quả là family phân nhánh, khó phát hiện replay hoặc ghi đè token state.

Một thiết kế an toàn phải đảm bảo **chỉ một chuyển trạng thái hợp lệ** từ R1 active sang spent cùng R2 active cho mỗi family, thông qua transaction/lock/CAS đủ mạnh.

~~~text
BEGIN ATOMIC TRANSACTION
  assert R1.version == expected AND R1.status == ACTIVE
  mark R1 as SPENT
  create R2 as ACTIVE in same family
  record family.current = R2
COMMIT
~~~

Cú pháp là pseudocode; database isolation, unique constraints, token family version và failover cần được thiết kế theo hạ tầng cụ thể.

### 8.3. Có nên có grace window?

Một số provider hỗ trợ “overlap/grace” ngắn để tránh false positive khi phản hồi bị mất hoặc nhiều request hợp lệ đồng thời. Tuy nhiên, **grace quá rộng** làm tăng khoảng thời gian attacker có bản sao R1 vẫn có thể sử dụng nó.

Nếu cần grace window, phải:

- Tài liệu hóa chính xác các điều kiện và thời hạn.
- Không phát tùy ý nhiều token family song song.
- Xác định cách phân biệt retry hợp lệ và reuse bất thường theo binding/risk.
- Giới hạn tần suất, theo dõi và kiểm thử case mất response.
- Tránh suy diễn rằng một grace window luôn là yêu cầu OAuth.

Trong kiến trúc BFF, **single-flight refresh ở client** là cách giảm đáng kể request trùng; không nên chỉ dựa vào AS nới lỏng reuse detection.

## 9. Bảo vệ public client và confidential client

### 9.1. Confidential client

Backend/BFF có thể bảo vệ client secret hoặc private key/mTLS certificate, và thường xác thực với AS tại token endpoint. **Client authentication là một lớp binding**: refresh token được dùng trong ngữ cảnh client đúng.

Nhưng confidential client vẫn có thể bị compromise; nếu cả refresh token và client credentials cùng bị lấy, attacker có thể thử refresh. Cần giữ secrets ở nơi an toàn, kiểm quyền, audit, rotation và bảo vệ token store.

### 9.2. Public client

SPA/native app không có client secret lâu dài có thể giữ bí mật khỏi chính người dùng/thiết bị. Do đó, chỉ dựa vào `client_id` không đủ để bảo vệ refresh token bị sao chép.

**RFC 9700 (OAuth 2.0 Security BCP)** yêu cầu refresh token cho public client phải **được ràng buộc với bên gửi (sender-constrained) hoặc dùng refresh token rotation**, để hỗ trợ phát hiện/cản trở replay. AS còn phải quyết định liệu có cấp refresh token cho public client dựa trên đánh giá rủi ro.

Các biện pháp bổ sung:

- Dùng Authorization Code + PKCE cho luồng authorization; **PKCE không tự bảo vệ refresh token sau cấp**.
- Lưu token theo hướng dẫn nền tảng, giảm khả năng bị XSS/malware lấy.
- Áp dụng rotation, token family, absolute/idle expiry và reuse detection.
- Sender binding như DPoP nếu client và AS/RS hỗ trợ đúng chuẩn.
- Cân nhắc **BFF** để giữ refresh token ở server thay vì lưu trực tiếp trong browser.

### 9.3. Sender-constrained refresh token

Một refresh token có thể được **ràng buộc với khóa/chứng chỉ của client**, chẳng hạn DPoP hoặc mTLS theo profile đã hỗ trợ. Khi trình token, client phải cung cấp bằng chứng sở hữu tương ứng. AS phải **thực sự kiểm binding**, không chỉ nhìn claim hoặc header được gửi.

Sender binding làm giảm khả năng một bản sao refresh token được dùng nếu attacker **không có private key/chứng chỉ**. Nó không thay thế bảo vệ thiết bị/server, vì một compromise mạnh có thể lấy cả khóa hoặc lợi dụng session đang chạy.

Đối với **sender-constrained access token**, Resource Server cũng phải kiểm proof và binding. Việc AS ràng buộc refresh token **không mặc định** biến mọi access token mới thành sender-constrained nếu không phát hành/kiểm theo chính sách tương ứng.

## 10. Các loại thời hạn trong vòng đời refresh token

Không có một con số TTL phù hợp mọi hệ thống. Cần phân biệt:

| Thời hạn/trạng thái | Ý nghĩa |
|---|---|
| **Access token expiry** | `exp` của access token; API không chấp nhận sau hạn theo validator và clock skew policy. |
| **Refresh token absolute lifetime** | Hạn tối đa của refresh token/grant family; rotation không nhất thiết kéo dài vô hạn. |
| **Refresh token idle expiration** | Hết hạn khi không được dùng trong khoảng thời gian theo chính sách. |
| **Grant/consent expiration** | Sự cho phép của Resource Owner hoặc tổ chức không còn active. |
| **Client status** | Client bị disabled/revoked, khiến refresh không được chấp nhận theo chính sách. |
| **User/account status** | User bị khóa, membership tenant bị gỡ hoặc policy yêu cầu reauthentication. |
| **Application browser session** | Cookie/session riêng của ứng dụng; không tự đồng nghĩa refresh grant còn hợp lệ. |
| **OP/SSO session** | Phiên xác thực tại Identity Provider; có thể khác phiên BFF và token lifetime. |

### 10.1. Rotation không có nghĩa sống mãi

Một hệ thống có thể phát R2, R3, R4 cho cùng family, nhưng vẫn **chặn tại absolute expiration ban đầu**. Hoặc dùng sliding lifetime với trần tuyệt đối riêng. Chính sách này là lựa chọn của AS; không được mặc định “mỗi lần refresh là được cộng thêm 30 ngày mãi mãi”.

### 10.2. Refresh token hết hạn trước browser session

Nếu browser còn session BFF nhưng refresh token bị thu hồi/hết hạn, BFF **không thể tự mint access token**. Nó phải bắt đầu lại flow authorization/reauthentication theo chính sách hoặc trả lỗi tương ứng. Không tự copy JWT cũ và sửa `exp`, vì như vậy làm hỏng chữ ký và phá ranh giới phát hành.

### 10.3. Browser logout không phải tự động revoke mọi JWT

Khi người dùng logout khỏi BFF, session cookie nên bị invalidate phía server. AS refresh grant có thể cần revoke riêng; access JWT còn hạn tại RS có thể vẫn được chấp nhận nếu RS chỉ xác minh cục bộ và không có state/denylist. Vì thế cần thiết kế **logout, revocation và access-token TTL** thành các cơ chế bổ sung, không nhầm lẫn.

## 11. Lưu trữ refresh token ở client và Authorization Server

Refresh token là credential có thể duy trì quyền truy cập không cần Resource Owner tương tác mỗi lần; vì vậy **không nên xử lý như thông tin cấu hình bình thường**.

### 11.1. AS có thể lưu hash/HMAC của token opaque

Nhiều AS phát refresh token dạng chuỗi ngẫu nhiên với entropy cao từ CSPRNG. Bên phát hành có thể lưu **HMAC/digest phục vụ lookup** thay vì raw token:

~~~text
Refresh token R2 gửi cho client qua TLS

Authorization Server store:
  token_lookup_key      = HMAC-SHA256(secretLookupKey, R2)
  family_id             = fam-81f
  sequence              = 2
  client_id             = shop-bff
  grant_id              = grant-81f
  subject               = user-742
  allowed_resources     = [orders-api]
  granted_scopes        = [orders:read]
  status                = ACTIVE
  issued_at             = ...
  last_used_at          = ...
  absolute_expires_at   = ...
  sender_key_binding    = ... (nếu có)
  version               = 7
~~~

Đây là **schema minh họa**. Khi R2 được trình, AS dùng khóa lookup nội bộ để xác định record, kiểm client/binding, family, thời hạn và trạng thái trước khi quyết định có rotate. Record đã spent có thể được giữ đủ thời gian theo chính sách để phát hiện reuse.

- Token phải khó đoán, sinh bằng CSPRNG với entropy mạnh, không dùng timestamp/user ID.
- HMAC key riêng cho lookup, không dùng JWT signing key hoặc client secret; có kế hoạch bảo vệ/rotation.
- Lưu trạng thái family, token version, revoke và expiry bằng database/transaction đủ nhất quán.
- Không ghi raw R1/R2 trong logs, traces, query string, metric labels hoặc thông báo lỗi.
- Backup/snapshot và quyền truy cập database cũng thuộc bề mặt rủi ro; cần TLS, encryption/ACL, retention.
- Không cần mặc định áp thuật toán hash mật khẩu chậm cho refresh token random có entropy cao nếu cơ chế keyed lookup đã được đánh giá.

OAuth không bắt buộc refresh token phải là JWT hay opaque. Nếu provider dùng định dạng có cấu trúc, **client vẫn không được tự quyết hiệu lực/grant bằng cách decode nó**; AS là nguồn thẩm quyền xác thực refresh token.

### 11.2. Client giữ token mới nhất như thế nào?

Với confidential backend/BFF, sử dụng **server-side authorized-client/token store** có kiểm soát quyền đọc và mã hóa theo threat model. Record có thể gồm:

~~~text
key:
  (issuer, client_id, principal_ref, grant_ref)

value:
  access_token_secret
  access_token_expiry
  refresh_token_secret
  refresh_family_version
  authorized_scopes
  authorized_audience
  last_successful_refresh_at
~~~

Nên tách refresh token khỏi browser, hạn chế nơi đọc được raw secret, cập nhật bằng CAS/transaction và không serialize record này ra DTO response/log. Một **server-side session store** của browser có thể giữ tham chiếu `grant_ref`, không cần chứa toàn bộ token; nhưng triển khai có thể gộp theo framework nếu an toàn.

### 11.3. Token storage khác browser session

- **Browser session cookie:** bí mật dùng để BFF tra trạng thái ứng dụng. Nó có idle/absolute expiry riêng.
- **Access token:** credential dùng tại RS, có `exp` và `aud`/`scope`.
- **Refresh token:** credential trình tại AS để xin access token mới, theo grant/client binding.
- **OP session:** phiên đăng nhập của nhà cung cấp danh tính, không tự đồng nghĩa session BFF.

Logout browser không tự đồng nghĩa AS đã revoke refresh grant, và access token hết hạn không tự kết thúc browser session. Phải quản lý **những vòng đời khác nhau**.

## 12. BFF và các request refresh đồng thời

Một dashboard gửi ba API request cùng lúc. Cả ba đến các BFF instance khác nhau và thấy A1 sắp hết hạn. Nếu đều gửi R1, một request thành công rotate thành R2 trong khi request còn lại có thể bị coi là reuse.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as BFF instance A
    participant B as BFF instance B
    participant S as Authorized Client Store
    participant AS as Authorization Server

    A->>S: Read refresh R1, version 5
    B->>S: Read refresh R1, version 5
    A->>AS: Refresh R1
    AS-->>A: Access A2, Refresh R2
    B->>AS: Refresh R1
    AS-->>B: invalid_grant / reuse event
    A->>S: Save R2, version 6
    B->>S: Old state may trigger unwanted logout or overwrite
~~~

### 12.1. Single-flight hoặc distributed lock theo grant

BFF có thể phối hợp để **một grant chỉ có một lần refresh đang thực thi** tại một thời điểm:

~~~text
function getUsableAccessToken(grantRef):
    current = tokenStore.read(grantRef)
    if current.access.remainingLifetime > safetyWindow:
        return current.access

    with distributedSingleFlightLock(grantRef):
        latest = tokenStore.read(grantRef)

        if latest.access.remainingLifetime > safetyWindow:
            return latest.access

        result = callTokenEndpoint(latest.refresh)

        if result is unambiguously invalid_grant:
            invalidateGrantAndSessionAsPolicyRequires()
            requireReauthorization()

        if result succeeded:
            tokenStore.compareAndSwap(
                grantRef,
                expectedVersion = latest.version,
                nextAccess = result.access_token,
                nextRefresh = result.refresh_token
                              if returned else latest.refresh,
                nextVersion = latest.version + 1
            )
            return result.access_token
~~~

Đoạn này là **pseudocode**, không phải distributed lock production hoàn chỉnh. Cần có fencing, timeout, crash recovery, lost update protection, transaction semantics và logic xử lý lỗi. Sau khi lấy lock, **đọc lại token** vì request khác có thể đã refresh. Cập nhật token phải nguyên tử; token mới không được bị ghi đè bởi trạng thái cũ.

### 12.2. Trường hợp AS rotate nhưng response bị mất

~~~text
BFF -> AS: Dùng R1 để refresh
AS: Mark R1 SPENT, issue R2
AS -> BFF: Response chứa R2 bị mất do timeout
BFF: Chỉ còn R1, không biết AS đã commit hay chưa
~~~

Retry R1 có thể gây reuse detection và revoke family. Không thể suy luận “timeout nghĩa là AS chưa dùng R1”.

Giải pháp phụ thuộc **retry/idempotency semantics của AS**: nếu AS có cơ chế retry an toàn được tài liệu hóa thì theo đó; một số AS có overlap/grace đã kiểm soát; khi không thể khôi phục, cần invalidate grant và yêu cầu authorization lại. **Không retry vô hạn** hoặc kéo dài tuổi thọ token ở client để che lỗi.

### 12.3. Chọn thời điểm refresh

Không refresh trên mọi request. Dùng **safety window** có giới hạn trước khi access token hết hạn, dựa trên TTL, latency/clock skew, nhưng không đặt cửa sổ quá rộng gây refresh storm/rotation liên tục. Có thể refresh khi một request hợp lệ nhận `401` do token hết hạn, nhưng phải kiểm nguyên nhân và tránh vòng lặp retry vô hạn.

## 13. Browser, mobile và BFF: chọn nơi lưu token

| Kiến trúc | Nơi giữ refresh token | Rủi ro đặc thù |
|---|---|---|
| **BFF/confidential backend** | Token store phía server | Ít lộ cho browser JavaScript; phải bảo vệ Redis/JDBC, CSRF/session cookie, concurrency và logout. |
| **SPA public client** | Nếu AS cấp, môi trường browser theo chính sách | XSS/script cùng origin có thể lấy token; rotation hoặc sender binding, đánh giá BFF. |
| **Native mobile public client** | OS secure storage/keychain khi có, có thể thêm key binding | Thiết bị bị chiếm quyền vẫn có thể lộ token/khóa. |
| **CLI/desktop client** | OS credential vault hoặc secret store thích hợp | Public client thường không có client secret bảo vệ đáng tin. |
| **Server-to-server** | Backend credential manager nếu thật sự được cấp | Với client credentials thường xin access token mới trực tiếp; refresh token thường không cần. |

### 13.1. Vì sao `localStorage` gây lo ngại?

JavaScript cùng origin có thể đọc `localStorage`; XSS hoặc thư viện script bị compromise có thể sao chép token. `sessionStorage` có vòng đời khác nhưng không chống script cùng origin đọc dữ liệu. `HttpOnly` cookie không cho JS đọc trực tiếp nhưng browser tự gửi cookie, dẫn đến cần **CSRF protection**; XSS vẫn có thể thực hiện request đã xác thực.

Với BFF, browser giữ session cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, backend giữ OAuth token. Điều này giảm khả năng browser script lấy raw refresh token, nhưng không thay thế CSRF, CSP/output encoding, session fixation protection, idle/absolute expiry và server-side invalidation.

### 13.2. OIDC `offline_access` không bảo đảm refresh token

`offline_access` là scope yêu cầu quyền truy cập offline trong OIDC theo các điều kiện của OP, consent và policy. Không phải cứ có `openid` là chắc chắn được cấp refresh token; yêu cầu `offline_access` cũng **không bắt buộc AS luôn cấp**. OIDC mô tả điều kiện consent, bao gồm cách xử lý `prompt=consent` theo ngữ cảnh và profile.

AS phải đánh giá rủi ro, client type, grant và chính sách. Nếu không có refresh token, client phải dùng một flow authorization khác phù hợp để lấy token mới, không tự “tạo” refresh token hoặc dùng ID token thay nó.

### 13.3. Mất thiết bị hoặc đăng xuất khỏi mobile

Ứng dụng nên hỗ trợ revoke refresh grant/device session ở AS khi mất thiết bị, đăng xuất hoặc nghi compromise; xóa credential local khi có thể. Token rotation/reuse detection có thể phát hiện bản sao dùng song song nhưng không chứng minh bên nào là chủ hợp pháp.

## 14. Lỗi OAuth token endpoint và retry policy

### 14.1. `invalid_grant`

Ví dụ refresh token bị revoke/hết hạn, sai client hoặc đã rotate:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Không nên trả lý do quá chi tiết “token R1 thuộc user X” hoặc “secret còn hạn Y phút” vì làm lộ metadata. Client phải ngừng dùng credential bị từ chối, xử lý token store/session và bắt đầu authorization mới khi phù hợp.

### 14.2. `invalid_client`, `invalid_scope`, `invalid_target`

- **`invalid_client`:** client authentication thiếu hoặc sai; confidential client không được tự fallback sang public-client mode. Với xác thực qua Authorization header, OAuth yêu cầu challenge HTTP phù hợp, thường `401`.
- **`invalid_scope`:** scope yêu cầu không hợp lệ hoặc vượt giới hạn, không được lén nâng quyền.
- **`invalid_target`:** có thể dùng theo RFC 8707 khi resource mục tiêu không chấp nhận được trong flow/profile đã hỗ trợ.

### 14.3. Timeout và `5xx` không chắc có thể retry

| Tình huống | Xử lý an toàn |
|---|---|
| `400 invalid_grant` | Ngừng dùng refresh token đó; xử lý revoke/relogin theo policy. |
| `401 invalid_client` | Điều tra client auth/secret rotation; không downgrade authentication. |
| `invalid_scope` / `invalid_target` | Sửa policy/request hoặc yêu cầu grant mới, không tự mở rộng quyền. |
| `429 Too Many Requests` | Backoff theo AS; tránh refresh storm, không log token. |
| `5xx` sau khi request đã đến AS | Kết quả có thể mơ hồ; chỉ retry nếu có semantics an toàn của AS. |
| Network timeout sau khi gửi R1 | R1 có thể đã spent; không tự retry vô hạn. |
| Token store outage | Fail closed; không chấp nhận grant/trạng thái không thể xác minh. |
| Đồng hồ lệch | Đồng bộ thời gian và áp dụng clock skew có giới hạn; không bỏ expiry. |

**Refresh Token Grant với rotation không phải thao tác idempotent mặc định.** Cơ chế retry cần dựa vào hợp đồng AS, không chỉ logic HTTP generic retry.

## 15. Resource Server kiểm access token mới như thế nào?

Refresh thành công không làm Resource Server đổi vai trò. Resource Server **không bao giờ cần nhận R1/R2**; nó chỉ nhận access token A2 đã được AS cấp cho API.

### 15.1. JWT access token mới

Ví dụ payload JWT (chưa có chữ ký, chỉ để giải thích):

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "iat": 1893453000,
  "nbf": 1893453000,
  "exp": 1893453600,
  "jti": "a2-8f31"
}
~~~

Resource Server phải kiểm:

1. JWT đúng **token type/profile**, ví dụ JWT access token theo RFC 9068 nếu hệ thống chọn profile đó; không chấp nhận ID token hoặc refresh token thay access token.
2. Chữ ký và thuật toán bằng khóa tin cậy gắn với issuer; không chỉ Base64URL-decode payload rồi tin.
3. `iss` đúng AS tin cậy; `aud` thực sự chỉ Resource Server này.
4. `exp`, `nbf` và các điều kiện thời gian.
5. `scope` đủ cho endpoint, cộng **quyền trên từng đối tượng/tenant** và các ràng buộc nghiệp vụ.
6. DPoP/mTLS proof/binding khi token có sender constraint, cùng trạng thái/revocation nếu policy yêu cầu.

Nếu token A1 có `orders:read orders:cancel`, còn A2 sau refresh chỉ có `orders:read`, endpoint hủy đơn **phải bị từ chối**. Một phiên ứng dụng cũ còn flag `canCancel=true` không làm A2 tự có thêm scope.

### 15.2. Opaque access token

Một Resource Server có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** để kiểm A2:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "exp": 1893453600
}
~~~

Ngoài `active`, các trường tùy AS và hợp đồng. `active=true` **không cho phép mọi API**: vẫn phải kiểm audience/scope/permission và trạng thái cần thiết. Introspection endpoint phải đáng tin, kết nối qua TLS, xác thực Resource Server nếu AS yêu cầu; cache introspection có thể làm chậm tác động của revocation.

### 15.3. `iat` mới không đồng nghĩa user vừa đăng nhập

A2 thường có `iat` mới nhưng có thể được cấp **không có tương tác người dùng**. Nếu thanh toán, đổi mật khẩu hoặc thao tác nhạy cảm cần MFA gần đây, phải kiểm `auth_time`, `acr`/`amr` theo profile, session assurance hoặc thực hiện **reauthentication/step-up**. Không kiểm “`iat` trong năm phút gần đây” như thay thế bằng chứng xác thực mới.

### 15.4. Subject và tenant có thể còn quyền khác trước

Refresh token thường gắn grant ban đầu của một subject, nhưng user có thể đã bị giảm quyền ở tenant. AS có thể giảm scope hoặc từ chối refresh; RS cũng nên kiểm membership/ownership **tại thời điểm request** tùy mức rủi ro. Không coi quyền từ JWT cũ là hợp đồng vĩnh viễn.

## 16. Thu hồi grant, logout và phát hiện token bị lộ

### 16.1. Những trạng thái khác nhau

| Hành động | Tác dụng chính | Giới hạn |
|---|---|---|
| **Revoke refresh token/grant ở AS** | Chặn xin access token mới theo grant đó. | Không tự vô hiệu hóa JWT access token cũ ở RS offline. |
| **Revoke opaque access token** | AS/RS có thể trả inactive khi tra lookup/introspection. | Introspection cache có thể gây trễ. |
| **Denylist JWT hoặc token version** | RS có thể từ chối JWT còn hạn qua state check. | Cần phối hợp trạng thái và cache/revocation policy. |
| **Đợi access token hết hạn** | Giới hạn thời gian còn có thể dùng. | Không bảo vệ tức thời khi access token còn hiệu lực. |
| **Logout browser/BFF** | Hủy session ứng dụng, xóa cookie browser. | Không tự revoke refresh grant hay OP session. |
| **OIDC/SSO logout** | Kết thúc những phiên được quy định bởi profile logout. | Không đồng nghĩa mọi access token từng cấp đều invalid. |

**RFC 7009** định nghĩa endpoint thu hồi token. AS có thể thu hồi refresh/access token hoặc các token liên quan trong grant theo quy định và chính sách; không suy ra một request revoke sẽ làm mọi RS xác minh JWT cục bộ lập tức nhận biết.

### 16.2. Khi phát hiện R1 đã spent nhưng bị trình lại

Một playbook an toàn:

1. Từ chối R1 và đánh giá trạng thái token family.
2. Áp dụng reuse policy: có thể revoke active refresh token cùng family để chặn cả attacker lẫn client cho đến khi authorization lại.
3. Không dùng lại R1 hoặc phát thêm R3 chỉ để giữ trải nghiệm, trừ khi provider có retry semantics rõ.
4. Ghi audit metadata như issuer/client/grant reference đã được phép, error code, thời gian và trace ID; **không ghi token thô**.
5. Điều tra cả hai khả năng: token bị đánh cắp **hoặc** client concurrency/response-loss bug. Tín hiệu reuse không chứng minh ngay thủ phạm.
6. Đánh giá các access token còn hạn, quyền truy cập nhạy cảm, có cần denylist/state check hoặc buộc reauthentication không.

### 16.3. Rút consent hoặc user mất quyền tenant

Resource Owner có thể rút quyền cho client; tổ chức có thể gỡ user khỏi tenant. AS phải ngăn cấp token mới qua grant không còn được phép; RS có thể phải kiểm quyền hiện hành nếu dữ liệu cần thu hồi tức thì.

**Refresh Token Grant không làm permission “đóng băng” vĩnh viễn**. Một thiết kế chỉ lưu scope/role từ lần login đầu tiên mà không có chiến lược revalidation sẽ tạo stale authorization, đặc biệt với JWT access token còn hạn dài.

### 16.4. Khi chỉ còn một access token bị lộ

Nếu access token A2 bị lộ qua log, revoke refresh token có thể ngăn cấp A3 nhưng **không bảo đảm A2 lập tức bị từ chối**. Xử lý theo khả năng revoke/state của RS/AS; không tự động rotate JWT signing key nếu chỉ một bearer token lộ mà private key vẫn an toàn.

## 17. Java/Spring Security: lớp quản lý authorized client

Trong ứng dụng Java/Spring, nên dùng **OAuth2AuthorizedClientManager** và lưu trữ authorized client phù hợp, thay vì tự viết POST token endpoint cho mọi request rồi tự quản lý mọi OAuth error.

Ví dụ cấu hình **Spring Security OAuth2 Client** cho một service chạy ngoài ngữ cảnh `HttpServletRequest`, giả định đã có client registration và `OAuth2AuthorizedClientService`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class OAuthClientRefreshConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, authorizedClients
        );

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là **cấu hình mẫu**, chưa phải ứng dụng hoàn chỉnh. `refreshToken()` chỉ thực hiện refresh khi có authorized client với refresh token phù hợp; nó **không tạo initial user grant**, không tự đăng nhập người dùng, cũng không tự đảm bảo có refresh token được cấp. Với web app có `HttpServletRequest` thường cần manager/repository thích hợp cho request context.

**Đặc biệt:** sử dụng thư viện không có nghĩa refresh token rotation đã được đồng bộ **across multiple processes/instances**. Cần kiểm implementation của `OAuth2AuthorizedClientService`, cơ chế lưu token, concurrency/lost update, failure handler, token endpoint authentication, timeout/retry và tính nguyên tử khi lưu R2. Đừng tự giả định một bean này giải quyết reuse detection.

### 17.1. Logic scope ở AS có thể được kiểm bằng Java

Ví dụ thu hẹp scope hoặc từ chối request mở rộng quyền. Đây chỉ là **pure policy function**, không thay thế toàn bộ AS:

~~~java
import java.util.Set;

public final class RefreshScopePolicy {
    private RefreshScopePolicy() {}

    public static Set<String> chooseScopes(
            Set<String> originalGrantScopes,
            Set<String> currentlyAllowedScopes,
            Set<String> requestedScopesOrNull) {

        Set<String> requested = requestedScopesOrNull == null
            ? originalGrantScopes
            : requestedScopesOrNull;

        if (!originalGrantScopes.containsAll(requested)) {
            throw new IllegalArgumentException("invalid_scope");
        }
        if (!currentlyAllowedScopes.containsAll(requested)) {
            throw new IllegalArgumentException("scope_not_permitted");
        }
        return Set.copyOf(requested);
    }
}
~~~

Hàm minh họa **chính sách từ chối thay vì tự giảm scope**. Trong OAuth thật, mã lỗi, thời điểm trả lỗi và cách dùng scope còn tùy grant/profile; `scope_not_permitted` ở đây là mã nội bộ, **không phải OAuth error code chuẩn**. AS cần kiểm client, resource/audience, grant, principal, sender binding, rotation và TTL riêng.

Nếu muốn **downscope**, phải thiết kế cách trả `scope` thực tế, nguyên tắc không tăng quyền và kiểm phù hợp OIDC/AS policy; không thể chỉ gộp mọi tập quyền của user và client.

### 17.2. Token client giữ không được làm thay quyết định AS

Ngay cả khi BFF đã lưu `grantedScopes` và `audience`, khi refresh nó phải dùng response thực tế của AS để cập nhật access token/permissions. Không tự sửa claim của A1, tăng `exp` hoặc phát bearer token mới ký bằng key không có thẩm quyền.

## 18. Quan sát và bảo vệ bí mật trong telemetry

Refresh token có thể bị lộ qua HTTP client wire logging, `exception.message`, body request/response `/token`, OpenTelemetry span hoặc APM. Với chuỗi R1 bị lộ, attacker có thể trình token trước khi người dùng nhận được R2.

### 18.1. Log theo mã sự kiện, không log credential

Ví dụ bản ghi audit an toàn:

~~~json
{
  "event": "oauth_refresh_failed",
  "issuer": "https://login.example.com",
  "client_id": "shop-bff",
  "grant_ref": "grant-81f",
  "result": "invalid_grant",
  "reason_category": "credential_rejected",
  "route": "POST /oauth2/token",
  "trace_id": "b7d9f1225a6e4c7ab30d2189444b5f60"
}
~~~

`grant_ref` chỉ được ghi nếu là tham chiếu nội bộ **được phép xuất audit**, không phải raw token hoặc session ID; nó vẫn có thể liên kết người dùng và cần RBAC/retention. **Không** ghi `refresh_token`, `access_token`, client secret, raw Authorization header, token endpoint body, DPoP proof hoặc JWT payload nhạy cảm.

### 18.2. Metrics và cảnh báo

~~~text
oauth_refresh_total{result=success|invalid_grant|invalid_client|error}
oauth_refresh_duration_seconds
oauth_refresh_rotation_total
oauth_refresh_reuse_detected_total
oauth_refresh_family_revoked_total
oauth_refresh_store_conflict_total
oauth_refresh_timeout_total
oauth_refresh_client_retry_total
~~~

Đây là tên metric minh họa. Không dùng `refresh_token`, `access_token`, session cookie, email, raw subject hoặc token family ID làm label vì rò dữ liệu và high cardinality.

Theo dõi reuse tăng, request refresh trùng sau deploy, `invalid_grant` tập trung ở một instance, CAS conflict và login lại hàng loạt. Các tín hiệu cần có context vận hành nhưng không được lộ token trong trace.

### 18.3. Bảo vệ mọi bản sao

Audit store/Redis/JDBC, gateway, HTTP client logger, trace collector, APM SaaS, alert system và backup đều cần quyền truy cập tối thiểu, encryption/TLS, retention và secret scrubbing. Nếu refresh token thật đã xuất hiện trong một sink, xử lý như **credential exposure**: ngăn rò tiếp, revoke grant/family phù hợp, điều tra truy cập, xử lý bản sao và thêm canary tests.

## 19. Các lỗi thiết kế hay gặp

| Lỗi | Tác động | Khắc phục |
|---|---|---|
| Xem refresh token như access token dài hạn | API nhận credential không dành cho nó, tăng nơi lộ | Chỉ AS token endpoint nhận refresh token. |
| Gắn lại `exp` của JWT cũ ở client | Token sai chữ ký/không có thẩm quyền phát hành | AS phát token mới, RS xác minh độc lập. |
| AS chỉ kiểm R1 có trong DB | Token không đúng client/grant/sender vẫn được cấp | Client binding, grant status, sender proof khi có. |
| Copy `scope`/`resource` từ request | Leo thang scope hoặc audience | Kiểm grant ban đầu và current policy. |
| Public client giữ refresh token không rotation/sender constraint | Token theft khó phát hiện hoặc giảm tác động | Tuân OAuth Security BCP, rotation hoặc sender binding. |
| Client không lưu R2 sau rotation | Tiếp tục dùng R1, kích hoạt reuse/revoke | Atomic persistence và failure handling. |
| Nhiều BFF instance refresh cùng R1 | `invalid_grant` và logout oan | Single-flight/CAS theo grant. |
| AS rotation không nguyên tử | Family phân nhánh khi race | Transaction/lock/version và reuse policy. |
| Retry vô hạn sau timeout | Dùng lại token đã spent | Provider-defined retry hoặc reauthorization. |
| Đồng nhất refresh với reauthentication | Bỏ kiểm MFA freshness | `auth_time`/step-up; không dùng `iat` thay thế. |
| Đọc JWT claims mà không verify | Attacker tự đặt subject/audience/scope | Signature, issuer, token type, aud và expiry. |
| JWT access token cũ còn quyền sau revoke | Resource Server cho phép stale access | TTL ngắn hoặc state/denylist/introspection theo rủi ro. |
| Ghi raw token vào log/trace | Credential replay từ telemetry | Không thu thập token; redact tại nguồn. |
| Browser session còn nên grant chắc chắn còn | Sử dụng trạng thái authorization đã hết | Phân biệt session, refresh grant và OP session. |
| Nhận ID token là access token sau refresh | Token confusion | Tách OIDC Client vs Resource Server validation. |

## 20. Bài thực hành và kiểm thử

### 20.1. Kịch bản có ba token

~~~text
Ban đầu:
  client = shop-bff
  subject = user-742
  audience = orders-api
  granted scopes = orders:read
  access A1 expires in 10 minutes
  refresh R1 active

Lần refresh #1:
  shop-bff gửi R1
  AS cấp A2 và R2
  R1 bị đánh dấu SPENT

Lần refresh #2:
  shop-bff phải dùng R2
  AS có thể cấp A3 và R3
~~~

Câu hỏi và gợi ý trả lời:

1. **A1 hết hạn có buộc user đăng nhập lại không?** Không, nếu grant/refresh/session và policy cho phép refresh.
2. **BFF có được gửi R2 tới Orders API không?** Không; chỉ access token dành cho Orders API được gửi tới đó.
3. **Một request vẫn dùng R1 sau khi R2 đã cấp?** Có thể bị AS coi là reuse; phải xử lý family/relogin theo chính sách.
4. **R2 có thể xin `payments:refund` không?** Không nếu scope/resource đó ngoài grant và chính sách.
5. **A2 có `iat` mới, có nghĩa user vừa MFA lại?** Không; refresh không tự chứng minh xác thực mới.
6. **Nếu R2 bị revoke, A2 có còn dùng được không?** Có thể còn đến `exp` nếu RS chỉ kiểm JWT cục bộ và không có cơ chế revoke/state bổ sung.

### 20.2. Ma trận negative tests

| Tình huống | Kết quả mong đợi |
|---|---|
| Thiếu `grant_type` hoặc khác `refresh_token` | AS từ chối theo OAuth request validation. |
| Thiếu `refresh_token` | AS từ chối `invalid_request` hoặc lỗi phù hợp. |
| Refresh token chuỗi ngẫu nhiên không tồn tại | Không phát access token; `invalid_grant`. |
| R1 đã hết hạn/đã revoke | `invalid_grant`, không phát token. |
| Confidential client sai client authentication | `invalid_client` hoặc lỗi phù hợp; không downgrade auth. |
| Client B dùng R1 của Client A | AS từ chối, không cấp token cho B. |
| Public client tự đổi `client_id` của grant | AS kiểm binding và từ chối. |
| Sender-bound R1 nhưng thiếu DPoP proof/mTLS binding | AS từ chối, không bỏ proof check. |
| R1 bị rotate thành R2 rồi R1 xuất hiện lại | Reuse detection/family policy được kích hoạt. |
| Hai refresh request dùng R1 đồng thời | Chỉ một transition hợp lệ ở AS; client có single-flight. |
| Response AS chứa R2 nhưng token store ghi thất bại | Không retry R1 vô hạn; xử lý reauthorization/failure. |
| Request `scope=orders:read payments:refund` ngoài grant | Không cấp scope mới; reject hoặc policy phù hợp. |
| Request `resource=payments-api` ngoài grant | Không cấp token Payments; `invalid_target`/lỗi profile. |
| Consent/grant đã bị rút | AS không phát access token mới. |
| Client bị disabled | AS không tiếp tục refresh trái policy. |
| User bị xóa membership tenant | AS/RS xử lý quyền thay đổi theo policy; không tự giữ admin. |
| Access JWT A2 đúng chữ ký nhưng sai `aud` | Resource Server từ chối. |
| Opaque A2 `active=true` nhưng thiếu scope | Resource Server từ chối endpoint cần scope. |
| OIDC refresh response có ID token nhưng `sub` khác grant | OIDC Client từ chối theo OIDC validation. |
| Browser logout nhưng AS grant còn active | Kiểm cơ chế revoke/cleanup đã thiết kế; không giả định tự động. |
| Refresh token canary bị chèn vào exception message | Test logs/traces thất bại nếu có token. |
| Token endpoint timeout sau rotation | Không lặp credential tùy tiện; xử lý theo provider semantics. |

### 20.3. Test chống race với token family

~~~text
test "one token per rotation":
    createFamily(R1 active)
    runRefreshInParallel(R1, R1)

    assert one transition is committed from R1 to successor
    assert no two independent active successors exist
    assert second request follows defined reuse/error policy

test "BFF refresh single-flight":
    createGrantedSessionWithExpiringAccess(R1)
    invokeBffFromTwoNodesConcurrently()

    assert at most one refresh attempt consumes R1
    assert both callers eventually use saved access A2 if successful
    assert saved refresh state references R2, not R1

test "scope and audience cannot expand":
    issueGrant(client=shop-bff, scopes={orders:read},
               resources={orders-api})
    refresh(scope={payments:refund}, resource=payments-api)

    assert no token with payments audience or refund scope was issued
~~~

Đây là pseudocode kiểm thử. Dùng mock AS/store hoặc integration test với clock điều khiển được; không sử dụng refresh token production và không chỉ dựa vào `Thread.sleep` để chứng minh expiry.

### 20.4. Bài tập phân tích sự cố

Một đợt deploy mới khiến 40% người dùng BFF phải đăng nhập lại khi dashboard mở sáu request song song; log cho thấy `invalid_grant` tăng mạnh nhưng không có dấu hiệu compromise khác.

Hãy phân tích:

- Có bao nhiêu BFF instance cùng đọc một refresh token trước khi có lock?
- AS có bật rotation và revoke family khi reuse không?
- Token store có version/CAS hay có nguy cơ last-write-wins?
- Request timeout/retry middleware có tự gửi lại R1 không?
- Các instance có chung token store không?
- Có thể dùng single-flight/atomic write để giảm false positive mà không tắt reuse detection không?
- Nếu AS response bị mất sau khi rotate, failure/relogin policy đã rõ chưa?

**Không chữa sự cố bằng cách tắt kiểm refresh token reuse hoặc kéo dài refresh token vô hạn.** Sửa race và retry semantics tại nguồn.

## 21. Checklist triển khai

- [ ] Hiểu rõ Refresh Token Grant chỉ cấp **access token mới tại AS**, không tự xác thực lại user.
- [ ] Refresh token chỉ được gửi tới token endpoint qua HTTPS, không gửi tới Resource Server.
- [ ] Client nhận dạng đúng public/confidential type và tuân thủ client authentication/binding.
- [ ] AS kiểm refresh credential, client/grant binding, revoke/expiry, scope, resource và policy trước phát hành.
- [ ] Scope khi refresh không mở rộng ngoài grant ban đầu; audience/resource theo grant và client policy.
- [ ] Public client có rotation hoặc sender-constrained refresh token theo OAuth Security BCP.
- [ ] Nếu rotate, AS chỉ cho một chuyển trạng thái family nguyên tử và có reuse detection/response policy.
- [ ] Client lưu refresh token mới sau rotation; không tiếp tục dùng token cũ.
- [ ] Nhiều BFF instance có single-flight/lock/CAS và xử lý lost response/timeout hợp lý.
- [ ] Không retry vô hạn `invalid_grant` hay timeout có kết quả mơ hồ.
- [ ] Access token mới được kiểm `iss`, `aud`, `exp`, token purpose, `scope` và quyền bản ghi tại RS.
- [ ] `iat` của token mới không được coi là `auth_time` hoặc MFA mới.
- [ ] Có chính sách absolute/idle expiration của refresh grant và trạng thái account/client/consent.
- [ ] Phân biệt logout browser/BFF, OP session và AS grant/access token revocation.
- [ ] Refresh token/client secret không nằm trong logs, traces, exception, URL hoặc JSON response cho browser trong BFF.
- [ ] Token store có TLS, encryption/ACL, backup protection, versioning và secret management.
- [ ] OIDC ID token (nếu trả khi refresh) được client xác minh theo OIDC; không chuyển cho API.
- [ ] Có negative tests cho wrong client, replay, race, scope escalation, audience substitution, lost response, revoke và token theft.
- [ ] Khi thiếu căn cứ xác minh grant, hệ thống **fail closed**.

**Ghi nhớ:** **Refresh Token Grant** giúp client xin access token mới mà không yêu cầu người dùng đăng nhập lại trong mỗi lần access token hết hạn. Refresh token là **credential có giá trị cao**, gắn với **client/grant**, chỉ dùng tại **Authorization Server token endpoint**, phải bảo vệ và thường được **rotate hoặc sender-bind** theo chính sách. Token mới không được mở rộng scope/audience trái phép; Resource Server vẫn kiểm access token và quyền trên tài nguyên. Việc xử lý đồng thời, thu hồi, timeout và replay là một phần của thiết kế bảo mật, không chỉ là chi tiết kỹ thuật phụ.

### Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** mục 6 Refreshing an Access Token, client authentication, scope, token response và `invalid_grant`.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token, public clients, rotation/sender binding, grant và phòng chống replay.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** access token được gửi tới Resource Server và nguy cơ token bị đánh cắp.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke token tại Authorization Server.
- **RFC 7662 — OAuth 2.0 Token Introspection:** RS kiểm opaque access token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** yêu cầu resource và hạn chế audience.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token JWT, `client_id`, `aud`, `scope` và Resource Server validation.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `iat`, `jti`.
- **RFC 8725 — JSON Web Token Best Current Practices:** audience/issuer validation, token confusion và thuật toán.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code, khác refresh token proof.
- **RFC 8693 — OAuth 2.0 Token Exchange:** token mới cho audience/actor khác khi được AS ủy quyền.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession và token binding.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client authentication và sender constraints.
- **OpenID Connect Core 1.0:** offline access, ID token validation và refresh token flow.
- **OWASP OAuth 2.0 Cheat Sheet / Session Management Cheat Sheet:** bảo vệ client credentials, browser session, token storage và revoke.
- **Spring Security Reference — OAuth2 Client:** `OAuth2AuthorizedClientManager`, refresh-token provider và authorized-client storage.


