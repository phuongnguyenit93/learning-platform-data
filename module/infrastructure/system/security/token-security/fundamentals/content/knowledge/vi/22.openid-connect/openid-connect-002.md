# ID token khác access token

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **ID token** của OpenID Connect (OIDC) với **access token** của OAuth 2.0 theo mục đích, bên nhận và quy tắc xác minh.
- Giải thích vì sao **Relying Party (RP)** xác minh ID token để xử lý authentication, còn **Resource Server (RS)** xác minh access token để xử lý authorization.
- Hiểu các claims **iss, sub, aud, exp, iat, nonce, auth_time, azp** trong ID token và **aud, scope, client_id, token type** trong access token.
- Mô tả Authorization Code + PKCE và phản hồi chứa hai loại token, cùng cách sử dụng UserInfo đúng chuẩn.
- Nhận diện token substitution, cross-JWT confusion, sai audience, issuer mix-up, phân quyền nhầm theo custom role, và lỗi dùng refresh token cho API.
- Triển khai bằng thư viện OIDC/OAuth đáng tin, thiết kế kiểm thử âm tính và vận dụng checklist bảo mật.

## 1. Hai câu hỏi khác nhau: đăng nhập và truy cập API

Một ứng dụng Dashboard cho người dùng đăng nhập qua OpenID Provider, sau đó đọc Orders API. Hệ thống có **hai câu hỏi độc lập**:

**Câu hỏi xác thực:** End-User nào đã được OP xác thực cho Dashboard, và sự kiện xác thực đó có những bảo đảm gì?

OIDC định nghĩa **ID token** dành cho **Dashboard/Relying Party**, giúp RP xác minh kết quả authentication và tạo session theo policy của ứng dụng.

**Câu hỏi phân quyền:** Client có được gọi **Orders API** không, với scope và quyền trên tài nguyên cụ thể nào?

OAuth 2.0 dùng **access token** làm credential để client yêu cầu truy cập Resource Server. Orders API phải kiểm token đúng audience và quyền tài nguyên.

~~~text
OpenID Provider / Authorization Server:
    https://identity.example.test

Relying Party:
    dashboard-web

Resource Server:
    orders-api

ID token:
    aud = dashboard-web
    sub = user-42
    Ý nghĩa: assertion xác thực dành cho RP

Access token:
    aud = orders-api
    scope = orders:read
    Ý nghĩa: credential truy cập Orders API
~~~

**Cả hai có thể cùng một issuer, cùng sub và cùng dạng JWT, nhưng không được sử dụng hoán đổi.**

## 2. Bảng so sánh ID token và access token

| Tiêu chí | ID token (OIDC) | Access token (OAuth 2.0) |
| --- | --- | --- |
| **Mục đích** | Assertion xác thực End-User cho client. | Credential cho Resource Server. |
| **Bên nhận** | Relying Party/client. | API/Resource Server được chỉ định. |
| **audience (aud)** | Thường là **client_id** của RP. | Identifier của API, ví dụ orders-api. |
| **Định dạng** | JWT theo OIDC, có thể ký và mã hóa theo cấu hình. | JWT, opaque/reference token hoặc profile khác. |
| **Nội dung** | iss, sub, aud, exp, iat; nonce, auth_time, acr/amr, azp khi áp dụng. | iss, aud, exp, scope, client_id, sub và binding theo profile. |
| **Bên xác minh** | RP theo quy tắc OIDC Core. | RS theo access-token profile/introspection. |
| **Được gửi như Bearer token cho API?** | **Không**, trừ khi API có một giao thức riêng được thiết kế khác; không coi ID token là OAuth AT. | **Có**, nếu đúng audience, loại token và policy. |
| **Làm bằng chứng login OIDC?** | **Có thể**, sau khi được RP xác minh đầy đủ. | **Không tự động**; token dành cho resource không phải ID token. |
| **Đủ quyền trên tài nguyên?** | Không. | Chỉ cho phép **yêu cầu**; RS vẫn kiểm scope, permission, tenant. |
| **Thời hạn** | Hết hạn assertion độc lập với session app. | Hết hạn/trạng thái credential tại RS. |
| **Dùng để xin token mới?** | Không phải refresh token. | Access token thông thường cũng không phải refresh token. |

**JWT là định dạng; ID token/access token là mục đích giao thức.** Một chuỗi có ba phần Base64URL và chữ ký không tự chứng minh nó thuộc loại token nào.

## 3. OpenID Connect bổ sung gì cho OAuth 2.0?

OAuth 2.0 là **khung ủy quyền**. OIDC bổ sung **lớp xác thực danh tính End-User** dựa trên các cơ chế OAuth.

Những vai trò liên quan:

- **End-User:** người được xác thực.
- **OpenID Provider (OP):** thực thể cung cấp dịch vụ xác thực OIDC, đồng thời giữ trách nhiệm OAuth Authorization Server theo flow.
- **Relying Party (RP):** client sử dụng OIDC để xác minh kết quả authentication.
- **Resource Server (RS):** API bảo vệ tài nguyên và xử lý access token, có thể bao gồm UserInfo endpoint.

Một OP có thể cung cấp cả authorization endpoint, token endpoint, UserInfo và các API khác, nhưng **chúng có hợp đồng bảo mật khác nhau**.

### Scope openid và scope API

Một OIDC authentication request thường có:

~~~text
scope = openid profile email orders:read
~~~

| Scope | Mục đích |
| --- | --- |
| **openid** | Yêu cầu dịch vụ xác thực OIDC. |
| **profile** | Yêu cầu những claims hồ sơ chuẩn khi policy cho phép. |
| **email** | Yêu cầu claims về email theo OIDC. |
| **orders:read** | Scope nghiệp vụ dành cho Orders API theo policy riêng. |

**openid không phải role admin và không cấp quyền orders:approve.** Scope OIDC yêu cầu thông tin xác thực/hồ sơ khác với scope authorization cho RS.

Không có scope **openid**/giao thức OIDC phù hợp, một OAuth access token thông thường **không tự là ID token**.

## 4. Cấu trúc ID token

ID token là JWT với claims chuẩn theo OIDC. Ví dụ payload mô phỏng:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "pairwise-user-72a9",
  "aud": "dashboard-web",
  "iat": 1730000000,
  "exp": 1730000600,
  "auth_time": 1729999950,
  "nonce": "EXAMPLE_NONCE_FROM_LOGIN_REQUEST",
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:level2"
}
~~~

Đây là **JSON minh họa, chưa phải JWT hoàn chỉnh**, các NumericDate thuộc dữ liệu giả trong quá khứ.

| Claim | Ý nghĩa | Điều RP cần biết |
| --- | --- | --- |
| **iss** | Issuer của OP. | Phải đúng issuer tin cậy đã chọn cho giao dịch. |
| **sub** | Subject của End-User tại OP. | Định danh theo issuer, không mặc định là email/ID toàn cục. |
| **aud** | Bên nhận ID token. | Phải chứa **client_id của RP**. |
| **exp** | Hết hạn assertion. | Phải kiểm token chưa quá hạn. |
| **iat** | Thời điểm phát hành token. | Có thể áp freshness/độ hợp lý. |
| **auth_time** | Thời điểm OP xác thực End-User. | Cần khi request có max_age hoặc policy yêu cầu. |
| **nonce** | Liên kết ID token với authentication request. | Nếu đã gửi, phải kiểm đúng nonce của transaction. |
| **acr** | Authentication Context Class Reference. | Diễn giải theo profile bảo đảm xác thực. |
| **amr** | Authentication Methods References. | Không tự là permission API. |
| **azp** | Authorized Party theo các tình huống OIDC. | Kiểm với client_id theo quy tắc OIDC khi có/cần. |
| **at_hash/c_hash** | Các hash liên kết access token/code trong flow phù hợp. | Kiểm theo response type/profile, không mặc định luôn có. |

ID token **không bắt buộc chứa email, display name, picture, role hoặc toàn bộ group memberships**. Nếu cần thêm claims, RP có thể dùng **UserInfo** khi được cấp phép.

### Subject không phải định danh toàn cục giữa các issuer

Hai OP khác nhau có thể phát **sub=user-42** nhưng nói về hai người khác nhau. Nên ánh xạ principal bằng:

~~~text
principalKey = (validatedIssuer, validatedSubject)
~~~

OIDC cũng cho phép **pairwise subject**, nên một End-User có thể có các sub khác nhau giữa các RP/sector. Không tự gộp tài khoản chỉ vì email trùng mà không có identity-linking policy đáng tin.

## 5. Access token chứa gì?

Access token phục vụ **OAuth authorization**, không bắt buộc là JWT.

Một JWT access token theo mô hình RFC 9068 có thể có payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "pairwise-user-72a9",
  "aud": "https://orders.example.test/api",
  "client_id": "dashboard-web",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-access-token-id"
}
~~~

Header minh họa:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "example-key-id"
}
~~~

Đây **không phải access token thật**. RS không được chỉ decode JSON rồi tin claims nếu chưa xác minh chữ ký/issuer/profile.

### Opaque access token

AS có thể phát một giá trị opaque không tự đọc được như JWT:

~~~text
access_token = "EXAMPLE_OPAQUE_BEARER_TOKEN"
~~~

RS có thể hỏi **introspection endpoint** đáng tin về active, audience, scope, client_id và trạng thái liên quan. Client không được dựa vào việc token trông giống JWT hay opaque để tự gán danh tính người dùng.

### Access token có thể đại diện workload

Với **client_credentials**, access token thường đại diện cho client/service principal, không nhất thiết có End-User. Claim sub của service token không được RP diễn giải như một user login chỉ vì là một chuỗi hợp lệ.

### Audience và scope đều cần kiểm

**aud** quyết định **RS nào được nhận token**; **scope** giới hạn những hành động được cấp. RS còn phải kiểm permission theo bản ghi và tenant hiện hành.

Nếu token có scope **orders:read** nhưng aud=reports-api, **Orders phải từ chối**. Nếu aud=orders-api nhưng scope chỉ là orders:read, endpoint **orders:approve** vẫn phải từ chối.

## 6. Sơ đồ hai ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Browser / End-User"] -->|"OIDC authorization"| OP["OpenID Provider / AS"]
    OP -->|"ID token + access token"| RP["Relying Party"]
    RP -->|"Kiểm ID token: aud=client_id, iss, exp, nonce"| S["Login/session"]
    RP -->|"Bearer access token"| RS["Orders API"]
    RS -->|"Kiểm AT: aud=Orders, iss, type, scope, exp"| P["API permission"]
    P -->|"Tenant/ownership"| D[("Orders DB")]
~~~

**RP được tin để xử lý session sau ID token validation. RS được tin để thực thi authorization trên tài nguyên sau access token validation.** Một bước thành công không thay bước còn lại.

## 7. Authorization Code + PKCE: nhận hai token cùng lúc

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider / AS
    participant RS as Orders API

    RP->>RP: Tạo state, PKCE verifier/challenge và nonce nếu dùng
    RP->>U: Redirect tới /authorize
    U->>OP: Authorization request scope=openid
    OP->>OP: Xác thực user và kiểm grant/consent/policy
    OP-->>U: Redirect code và state
    U->>RP: Callback code + state
    RP->>RP: Kiểm state, issuer và pending transaction
    RP->>OP: HTTPS POST /token code + verifier và client auth nếu cần
    OP->>OP: Kiểm code một lần, PKCE, client/redirect/grant
    OP-->>RP: ID token + access token (RT nếu policy cấp)
    RP->>RP: Xác minh ID token, tạo session theo policy
    RP->>RS: HTTPS request + access token
    RS->>RS: Kiểm token, scope, permission
    RS-->>RP: Dữ liệu hoặc từ chối
~~~

- **state** gắn authorization response với transaction của browser/client.
- **PKCE** ràng code với verifier, kiểm tại token endpoint.
- **nonce** liên kết ID token với authentication request theo OIDC khi được dùng.
- **iss/issuer** giúp nhận biết đúng OP; nhiều AS cần chống mix-up.

PKCE không thay ID token validation; nonce không thay state; ID token không thay access token.

## 8. Ví dụ HTTP Authorization Code + PKCE

Tất cả giá trị token/code/nonce ở đây là placeholder.

### 8.1 Authorization request

~~~http
GET /authorize?response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&scope=openid%20profile%20orders%3Aread&state=EXAMPLE_STATE&nonce=EXAMPLE_NONCE&code_challenge=EXAMPLE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Request thực đi qua HTTPS, redirect URI phải đúng registration và challenge/verifier phải được sinh theo PKCE.

### 8.2 Authorization response

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth2/callback?code=EXAMPLE_CODE&state=EXAMPLE_STATE
~~~

RP kiểm state/issuer trước khi token exchange.

### 8.3 Token request

~~~http
POST /token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=dashboard-web&code=EXAMPLE_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&code_verifier=EXAMPLE_PKCE_VERIFIER
~~~

Ví dụ lược bỏ client authentication để mô tả public client; **confidential backend phải xác thực theo phương thức đã đăng ký**.

### 8.4 Token response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "id_token": "EXAMPLE_OIDC_ID_TOKEN",
  "access_token": "EXAMPLE_ORDERS_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "openid profile orders:read",
  "refresh_token": "EXAMPLE_OPTIONAL_REFRESH_TOKEN"
}
~~~

ID token và access token xuất hiện trong cùng JSON nhưng **có nơi dùng và phép kiểm riêng**. Refresh token chỉ xuất hiện khi grant/policy cho phép; TTL 900 giây cũng chỉ là ví dụ.

### 8.5 Gọi Resource Server

Đúng:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ORDERS_ACCESS_TOKEN
~~~

Sai:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_OIDC_ID_TOKEN
~~~

Orders API **không được chấp nhận ID token thay OAuth access token**.

## 9. RP xác minh ID token theo OIDC

Một ID token không hợp lệ chỉ vì nó **có ba thành phần Base64URL** hoặc có claim sub.

Các bước chính của ID token validation:

1. **Issuer:** iss khớp OP đã được cấu hình/được chọn trong giao dịch.
2. **Signature và thuật toán:** xác minh bằng khóa/algorithms được tin theo OP metadata, không từ JWT header tự trỏ tới host lạ.
3. **Audience:** aud chứa client_id của RP; áp OIDC rules cho **azp** và multi-aud khi có.
4. **Thời gian:** exp chưa qua; iat được xử lý theo policy độ mới.
5. **Nonce:** nếu RP đã gửi nonce, kiểm token nonce khớp giá trị lưu trong transaction.
6. **auth_time:** khi request **max_age**, yêu cầu và kiểm auth_time theo quy tắc OIDC.
7. **Claims theo flow:** kiểm at_hash/c_hash trong trường hợp flow/profile đòi hỏi.
8. **Principal mapping:** chỉ ánh xạ (issuer, sub) sang account theo chính sách đáng tin.

### Issuer không được chọn từ callback tự khai

~~~text
Expected OP:
    https://identity.example.test

Received iss:
    https://unexpected.example.test

Result:
    DENY
~~~

Đừng lấy **jwks_uri**, token endpoint hoặc key từ một URL do callback/ID token không đáng tin đề xuất rồi thay trust configuration.

### Audience là client ID, không phải API

~~~text
RP client_id:
    dashboard-web

ID token aud:
    dashboard-web

Kết quả:
    Đúng audience của RP (vẫn cần checks khác)
~~~

Nếu ID token có aud=mobile-app, Dashboard từ chối dù iss/sub/signature đúng.

Nếu aud có nhiều phần tử, client xử lý azp theo OIDC; không coi ID token của một client khác cùng issuer là sử dụng được ở mọi client.

### auth_time không phải iat

iat là thời điểm token được phát, còn auth_time là thời điểm xác thực End-User. ID token vừa phát **không chứng minh user vừa làm MFA** nếu auth_time cũ. Với **max_age** hoặc step-up theo chính sách, phải kiểm ngữ nghĩa đúng.

### Không tự bật alg=none

Một số profile/đàm phán OIDC có ngoại lệ đặc thù rất hạn chế; RP production thông thường nên yêu cầu chữ ký và thuật toán được cấu hình đúng. **Decode thành JSON không phải verify.**

## 10. Mã giả tạo session sau khi xác minh ID token

~~~text
function onOidcCallback(browserSession, response):
    state = strictParseState(response)
    tx = browserSession.pending.removeAtomically(state)

    if tx missing or expired:
        DENY("unexpected_callback")

    verifyIssuerResponseAgainstExpectedOp(response, tx.issuer)

    if response.error is present:
        STOP_WITH_SAFE_ERROR()

    code = strictParseAuthorizationCode(response)

    tokens = exchangeAtTrustedTokenEndpoint(
        issuer = tx.issuer,
        code = code,
        redirectUri = tx.redirectUri,
        pkceVerifier = tx.verifier,
        clientAuthentication = registeredMethod
    )

    idToken = trustedOidcLibrary.validateIdToken(
        tokens.id_token,
        expectedIssuer = tx.issuer,
        expectedClientId = tx.clientId,
        expectedNonce = tx.nonce if one was sent,
        requiredAuthTime = tx.maxAge if requested,
        trustedKeysAndAlgorithms = configuredOpMetadata
    )

    if idToken invalid:
        DENY("invalid_id_token")

    principal = trustedAccountMapping(
        idToken.issuer,
        idToken.subject
    )

    if principal disabled or sessionPolicyDenies(principal):
        DENY("account_not_allowed")

    rotateOrCreateSession(browserSession, principal)

    // Access token thuộc token manager, không phải ID token.
    // Không gửi ID token làm Bearer AT tới Resource Server.
~~~

Đây là pseudocode về trách nhiệm, **không tự triển khai JOSE/OIDC cryptography**. Các bước bổ sung phải tuân theo OIDC flow, browser session policy và profile ứng dụng.

## 11. Resource Server kiểm access token theo hợp đồng khác

Orders API nhận **access token**, không chạy lại OIDC browser login.

Với JWT AT theo RFC 9068:

~~~text
1. Lấy Bearer credential từ transport được hỗ trợ.
2. Xác minh issuer, signature, thuật toán và khóa tin cậy.
3. Kiểm token type/profile đúng access token.
4. Kiểm audience dành cho Orders API.
5. Kiểm exp/nbf và claims bắt buộc.
6. Kiểm scope của endpoint.
7. Kiểm client/principal, tenant, permission và trạng thái tài nguyên.
8. Chỉ khi đạt tất cả mới xử lý request.
~~~

Với opaque AT, RS có thể introspect:

~~~http
POST /introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_RS_AUTH
Content-Type: application/x-www-form-urlencoded

token=EXAMPLE_OPAQUE_ACCESS_TOKEN
~~~

Ví dụ metadata được xác thực:

~~~json
{
  "active": true,
  "sub": "pairwise-user-72a9",
  "client_id": "dashboard-web",
  "aud": "https://orders.example.test/api",
  "scope": "orders:read",
  "exp": 1730000900
}
~~~

**active=true không đủ**. Orders còn kiểm audience, loại token, scope và permission. Introspection phải có TLS/client authorization và cache giới hạn theo chính sách thu hồi.

**Không dùng ID token aud=dashboard-web ở API aud=orders-api** dù cả hai được ký bởi cùng issuer.

## 12. UserInfo: lấy hồ sơ bằng access token

OIDC định nghĩa **UserInfo endpoint**, nơi RP có thể lấy claims End-User đã được cấp phép. RP gọi UserInfo bằng **access token phù hợp**, không phải ID token.

~~~mermaid
sequenceDiagram
    participant RP as Relying Party
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint

    RP->>OP: Authorization Code + PKCE
    OP-->>RP: ID token và access token
    RP->>RP: Validate ID token
    RP->>UI: GET /userinfo với Bearer access token
    UI->>UI: Kiểm token và policy claims
    UI-->>RP: Claims gồm sub
    RP->>RP: Kiểm UserInfo sub đúng ID token sub
~~~

~~~http
GET /userinfo HTTP/1.1
Host: identity.example.test
Authorization: Bearer EXAMPLE_USERINFO_ACCESS_TOKEN
~~~

~~~json
{
  "sub": "pairwise-user-72a9",
  "name": "Example User",
  "email": "user@example.test",
  "email_verified": true
}
~~~

**RP phải kiểm sub trong UserInfo Response khớp chính xác sub trong ID token**. Nếu khác, không được dùng claims UserInfo để cập nhật session người đã đăng nhập.

Không mặc định access token dành cho UserInfo cũng được Orders API chấp nhận. Audience/resource của AT cần phù hợp RS đích; nếu một profile có nhiều audiences, AS/RS phải có hợp đồng chặt.

UserInfo **không bắt buộc** cho mọi login; ID token có thể đủ cho mục đích xác thực cơ bản theo policy.

## 13. Custom role trong ID token không biến thành quyền API

Một OP có thể bổ sung claims như **roles**, **groups**, **department** hoặc **tenant** vào ID token theo hợp đồng riêng. Những claims đó không phải bằng chứng rằng ID token được phép sử dụng ở Resource Server.

Giả sử Dashboard nhận ID token cho client_id dashboard-web với custom claim **roles = [order_manager]**. Dashboard có thể dùng thông tin đã xác minh để điều chỉnh giao diện theo chính sách. Tuy nhiên, khi user yêu cầu duyệt Order #123, Orders API vẫn phải:

1. Nhận **access token** đúng token profile và audience Orders.
2. Kiểm issuer, chữ ký hoặc introspection, thời hạn và scope orders:approve.
3. Xác định principal từ dữ liệu đã xác minh; phân biệt người dùng với service identity.
4. Đọc tenant/owner/trạng thái của Order #123 từ dữ liệu đáng tin.
5. Kiểm permission hiện hành và quy tắc separation of duties.
6. Thực hiện thay đổi trong transaction có kiểm soát.

Một browser có thể sửa request body, header hoặc localStorage. Không được tin field **role=admin** mà frontend tự gửi. Ngay cả role trong JWT đã ký cũng có thể **cũ** hoặc thiếu phạm vi tenant.

### Role claim khác scope

| Thành phần | Nguồn/mục đích | Bên thực thi |
| --- | --- | --- |
| **roles trong ID token** | Custom claim mà OP gửi cho client theo hợp đồng authentication/identity. | RP có thể dùng theo policy, không thay API authorization. |
| **scope trong access token** | Quyền yêu cầu OAuth được AS cấp theo client/grant/resource. | RS kiểm scope cho endpoint. |
| **permission trên tài nguyên** | Quyền cụ thể theo role, tenant, ownership, trạng thái nghiệp vụ. | RS/policy engine kiểm tại request. |

Một End-User có role order_manager ở tenant-blue không mặc nhiên có quyền ở tenant-green.

## 14. Thời hạn ID token không phải thời hạn phiên đăng nhập

Ví dụ người dùng đăng nhập lúc 10:00. RP kiểm ID token, tạo session cookie và quản lý session theo idle timeout/absolute timeout của chính ứng dụng. ID token hết hạn lúc 10:05 nhưng session vẫn có thể được chấp nhận lúc 10:10 nếu **session policy** cho phép.

Đây không tự là lỗi, vì ID token là assertion được xác minh tại một thời điểm; RP session có vòng đời riêng.

Ngược lại, một End-User có thể bị khóa sau khi ID token được phát. **JWT đã ký không tự cập nhật** trạng thái account. RP cần chiến lược session invalidation, logout khi áp dụng, kiểm account status hoặc yêu cầu xác thực lại.

| Mốc | Ý nghĩa | Bên kiểm |
| --- | --- | --- |
| **iat của ID token** | Token được phát khi nào. | RP. |
| **auth_time** | Người dùng được OP xác thực khi nào. | RP khi cần freshness/max_age. |
| **exp của ID token** | Assertion hết hạn lúc nào. | RP. |
| **exp của access token** | Credential API hết hạn lúc nào. | Resource Server. |
| **Thời hạn refresh token** | Có được xin token mới ở AS nữa không. | Authorization Server. |
| **App session timeout** | Cookie/session ứng dụng còn hợp lệ không. | RP/backend. |

### auth_time khác iat

Một ID token vừa được OP phát từ phiên đã đăng nhập trước đó có thể có **iat gần đây nhưng auth_time cũ**. Nếu hành động nhạy cảm yêu cầu user vừa xác thực lại hoặc phải có MFA, RP cần dùng **max_age, auth_time và acr/amr** theo profile/chính sách. Chỉ kiểm token mới được phát chưa đủ.

### Access token có vòng đời độc lập

Access token có thể hết hạn trước hoặc sau ID token. Orders API phải kiểm AT của request, không dựa vào việc ID token trong RP session vẫn hợp lệ. Việc RP login thành công cũng không chứng minh client được cấp scope cho Payments API.

## 15. Refresh token là credential thứ ba

OIDC Code flow có thể nhận **refresh token** nếu AS/OP và chính sách cho phép.

| Token | Bên nhận đúng | Mục đích |
| --- | --- | --- |
| **ID token** | Relying Party/client. | Xác minh sự kiện xác thực End-User. |
| **Access token** | Resource Server/API. | Yêu cầu truy cập theo grant. |
| **Refresh token** | AS token endpoint. | Đổi lấy token mới nếu grant/RT còn hiệu lực. |

Không gửi refresh token tới Orders API; cũng không coi ID token là refresh token.

Khi dùng refresh_token grant, OP **có thể** phát ID token mới bên cạnh access token mới theo OIDC profile. Nếu có, RP vẫn cần xác minh ID token mới theo quy tắc phù hợp. **Refresh không đồng nghĩa người dùng vừa đăng nhập lại hoặc hoàn thành MFA mới**.

Refresh token cần lưu trữ an toàn, client binding, rotation hoặc sender-constraining theo loại client, revocation và giới hạn thời hạn. Không ghi RT trong log hay URL.

## 16. Client credentials không có nghĩa End-User đã đăng nhập

Một workload như nightly-report-worker có thể dùng **client_credentials** để xin access token aud=reports-api và scope=reports:generate.

AS xác thực confidential client, áp client/resource/scope policy và phát AT cho workload. **Grant này không mặc định có End-User**, không phát một OIDC ID token để đại diện cho người dùng đang đăng nhập.

Ngay cả khi access token có claim sub, RS phải hiểu sub theo grant/token profile. Một service principal có ID trùng với tên tài khoản user không phải lý do để cấp quyền của user đó.

Nếu cần workload identity, hãy dùng client authentication/authorization và token profile machine-to-machine phù hợp. Nếu cần End-User login, hãy dùng OIDC flow đúng.

## 17. Chống cross-JWT confusion và token substitution

Giả sử cùng một OP ký cả ID token và JWT access token bằng cùng bộ khóa. Một API chỉ kiểm **chữ ký và exp** rồi chấp nhận mọi JWT sẽ có nguy cơ nhận nhầm ID token của Dashboard.

Đây là **cross-JWT confusion**: một token hợp lệ ở ngữ cảnh này bị dùng tại ngữ cảnh khác.

Các phép kiểm phải tách rõ:

| Điều kiện | RP xác minh ID token | Orders API xác minh access token |
| --- | --- | --- |
| **Issuer** | OP của authentication transaction. | AS được RS cấu hình tin cậy. |
| **Audience** | client_id của RP. | Resource identifier của Orders API. |
| **Token profile** | OIDC ID token. | JWT AT theo RFC 9068 hoặc opaque theo hợp đồng. |
| **Signature** | Thuật toán/keys theo cấu hình OP. | Thuật toán/keys theo cấu hình RS. |
| **Nonce** | Kiểm nếu RP đã gửi trong auth request. | Không dùng nonce OIDC làm quyền API. |
| **Scope** | ID token không là grant API. | RS kiểm scope của endpoint. |
| **Principal** | End-User mapping theo issuer/sub. | User/service identity theo grant/profile. |
| **Policy** | Tạo và quản lý session ứng dụng. | Quyết định thao tác trên bản ghi/tenant. |

**Token type marker** như typ=at+jwt là một phần hữu ích của JWT access-token profile RFC 9068, nhưng không thay kiểm signature, issuer, audience và scope.

Một số OP không đặt một nhãn typ=ID_TOKEN thống nhất trên mọi ID token. RP nên dùng **OIDC verifier chuyên biệt**, không tự đoán chỉ từ một header tùy biến.

### Nếu aud tình cờ trùng thì sao?

Có thể có một cấu hình kém tách biệt khiến client_id của RP trùng identifier audience của API. Khi đó **kiểm aud đơn thuần không đủ** ngăn nhận nhầm ID token.

RS phải còn kiểm **token type/profile, tập claims, trusted issuer và binding theo hợp đồng**. Nên tách identifier/validation rules để hạn chế cross-JWT confusion theo RFC 8725.

## 18. Java/Spring Security: phân tách login và API

Một ứng dụng có cả browser UI và REST API có thể dùng **hai SecurityFilterChain** khác nhau: một cho OAuth2 Login/OIDC, một cho JWT OAuth Resource Server.

Ví dụ Java/Spring Security 6:

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.core.annotation.Order;
    import org.springframework.security.config.Customizer;
    import org.springframework.security.config.annotation.web.builders.HttpSecurity;
    import org.springframework.security.web.SecurityFilterChain;

    @Configuration
    public class OidcAndApiSecurity {
        @Bean
        @Order(1)
        SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
            http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth ->
                    oauth.jwt(Customizer.withDefaults())
                );
            return http.build();
        }

        @Bean
        @Order(2)
        SecurityFilterChain webChain(HttpSecurity http) throws Exception {
            http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/login/**", "/oauth2/**")
                        .permitAll()
                    .anyRequest().authenticated()
                )
                .oauth2Login(Customizer.withDefaults());
            return http.build();
        }
    }

**Đây là ví dụ tổ chức security boundaries, chưa phải cấu hình production đầy đủ.** Cần bổ sung client registration, issuer metadata, PKCE/state, cookie/session/CSRF, audience validator, type/profile JWT, permission endpoints và lỗi bảo mật.

Đặc biệt, chỉ bật **oauth2ResourceServer().jwt()** không tự khẳng định rằng ứng dụng đã cấu hình đầy đủ RFC 9068 **typ=at+jwt** hoặc **aud=orders-api**. Những validator phù hợp phải được tích hợp vào JwtDecoder và authorization rules.

### Audience validator cho Orders API

    import java.util.List;
    import org.springframework.security.oauth2.core.OAuth2Error;
    import org.springframework.security.oauth2.core.OAuth2TokenValidator;
    import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
    import org.springframework.security.oauth2.jwt.Jwt;

    public final class OrdersAudienceValidator
            implements OAuth2TokenValidator<Jwt> {

        private static final String EXPECTED =
                "https://orders.example.test/api";

        @Override
        public OAuth2TokenValidatorResult validate(Jwt token) {
            List<String> audiences = token.getAudience();
            boolean valid = audiences != null
                    && audiences.size() == 1
                    && EXPECTED.equals(audiences.get(0));

            if (valid) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token audience mismatch",
                    null
                )
            );
        }
    }

Validator minh họa này **chỉ kiểm audience**, với policy đúng một recipient. Phải kết hợp issuer, chữ ký, thuật toán, time, token type và scope. **Không dùng nó cho ID token** vì ID token có audience của RP/client.

### Không tự làm JOSE validation trong controller

Đừng chỉ Base64URL-decode header/payload rồi chấp nhận JSON, hoặc lấy URL JWKS từ header JWT để tải khóa bất kỳ. Dùng thư viện OIDC/OAuth/JOSE đã kiểm chứng, cấu hình OP/issuer/keys tin cậy.

## 19. Backend-for-Frontend, cookie session và access token

Trong **BFF pattern**, browser có thể chỉ giữ session cookie ứng dụng. Backend nhận code, đổi code qua token endpoint, xác minh ID token và lưu OAuth token theo chính sách server-side.

Luồng trách nhiệm:

1. Browser khởi tạo login qua BFF.
2. BFF thực hiện Authorization Code + PKCE và kiểm state/issuer.
3. BFF xác minh **ID token** để nhận diện End-User và tạo session.
4. BFF lưu **access token/refresh token** trong token manager được bảo vệ.
5. BFF gọi Orders API bằng **access token dành cho Orders**, không phải ID token.
6. Orders API kiểm AT và quyền dữ liệu.

BFF giảm việc JavaScript browser phải giữ token dài hạn, nhưng **không thay Resource Server validation**.

Nếu API lại sử dụng browser cookie thay vì Bearer AT, phải thiết kế **session authentication và CSRF protection** riêng. Không sử dụng rule “có session cookie hoặc bất kỳ JWT cùng issuer thì cho tất cả API qua”.

## 20. Tình huống: Alice đăng nhập Dashboard rồi đọc Orders

Hệ thống:

- OP/AS: https://identity.example.test.
- RP: dashboard-web tại https://app.example.test.
- RS: Orders API tại https://orders.example.test/api.
- Alice: order_manager ở tenant-blue, chỉ order_viewer ở tenant-green.

### A. Login

RP bắt đầu OIDC Authorization Code + PKCE, nhận ID token sau token exchange.

RP xác minh **iss=https://identity.example.test**, **aud=dashboard-web**, chữ ký, exp và nonce theo transaction khi có. Sau đó RP map issuer+sub tới account Alice và tạo session nếu account policy cho phép.

### B. API request

RP/BFF gửi **access token** cho Orders với **aud=https://orders.example.test/api** và scope **orders:read**.

Orders API kiểm token và permission. Alice không tự có quyền sửa đơn tenant-green chỉ vì đã được OP xác thực hoặc có một role ở tenant-blue.

### C. Token bị dùng nhầm

Nếu BFF gửi ID token vào Authorization header của Orders, API phải từ chối **sai mục đích/type/audience**, dù RP đã đăng nhập thành công.

### D. Quyền thay đổi

Nếu Alice bị rút role manager sau khi token phát, ID token/AT JWT còn hạn có thể vẫn chứa snapshot cũ. RS cần tuân theo policy **permission freshness/revocation** và kiểm tài nguyên hiện hành.

## 21. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Gửi ID token cho API như Bearer. | Token không dành cho RS. | Dùng AT đúng audience/type. |
| Dùng AT làm ID token để login. | Không đúng hợp đồng OIDC RP. | Xác minh OIDC ID token. |
| Chỉ decode JWT payload. | Không xác minh nguồn/độ toàn vẹn. | Verify signature, issuer, aud, time, profile. |
| Chỉ kiểm chữ ký và exp. | Token của client/API khác có thể được nhận. | Kiểm audience và token type. |
| RP chấp nhận ID token aud của client khác. | Client substitution. | OIDC aud/azp validation. |
| Không kiểm nonce đã gửi. | ID token replay/injection. | Nonce đúng authentication transaction. |
| Không kiểm state/PKCE. | Login CSRF hoặc code interception. | Authorization Code + PKCE và state binding. |
| Chọn token endpoint do callback tự khai. | Lộ code/verifier/secret sai issuer. | Metadata tin cậy và mix-up defense. |
| Dùng email làm identity key duy nhất. | Ghép nhầm user khác issuer. | Issuer+sub và account linking policy. |
| Không kiểm UserInfo sub. | Trộn claims của người khác. | So sub chính xác với ID token. |
| Tin roles trong ID token để cấp quyền API. | Role stale, sai audience/tenant. | RS kiểm AT và resource policy. |
| Dùng exp của ID token làm hạn AT. | Vòng đời khác nhau. | Kiểm riêng từng token/session. |
| Gửi RT tới API. | Lộ credential dài hạn, sai mục đích. | RT chỉ tại AS token endpoint. |
| Client credentials thành user login. | Nhầm service principal với End-User. | Tách grant/principal type. |
| Cho JWT alg=none tùy tiện. | Assertion không được xác minh. | Thuật toán/khóa tin cậy theo profile. |
| Ghi raw ID/AT/RT vào logs. | Rò rỉ claims, token và session context. | Redaction, least privilege và retention. |

## 22. Negative tests

| Test | Tình huống | Kết quả |
| --- | --- | --- |
| Valid ID token. | RP nhận ID token issuer/aud/nonce/exp đúng. | Tiếp tục session policy. |
| ID token issuer sai. | Sub giống nhưng OP khác. | RP từ chối. |
| ID token audience sai. | aud=mobile-app thay vì dashboard-web. | RP từ chối. |
| Multi-aud azp sai. | azp trái client_id. | RP từ chối theo OIDC. |
| ID token hết hạn. | exp đã qua. | RP từ chối. |
| ID token chữ ký sai. | Payload bị sửa. | RP từ chối. |
| Thuật toán ngoài policy. | Không chữ ký hoặc alg không được chấp nhận. | RP từ chối. |
| Nonce thiếu. | Đã gửi nonce nhưng ID token thiếu. | RP từ chối. |
| Nonce khác. | Token từ giao dịch khác. | RP từ chối. |
| auth_time thiếu khi max_age. | max_age yêu cầu nhưng claim thiếu. | RP từ chối theo OIDC. |
| auth_time quá cũ. | Không đạt freshness. | Yêu cầu reauth hoặc từ chối. |
| ID token tại API. | Gửi ID token làm Bearer ở Orders. | RS từ chối. |
| AT dùng làm login. | RP dùng access token thay ID token. | RP từ chối. |
| AT audience sai. | aud=reports-api gửi Orders. | RS từ chối. |
| AT scope thiếu. | orders:read cho endpoint approve. | RS từ chối. |
| AT hết hạn. | exp đã qua. | RS từ chối. |
| Opaque AT active nhưng aud sai. | Introspection active=true cho RS khác. | RS từ chối. |
| UserInfo sub mismatch. | ID token Alice, UserInfo Bob. | RP từ chối claims. |
| Hai issuer cùng sub. | OP-A/OP-B cùng user-42. | Không tự gộp account. |
| Client credentials giả End-User. | Service AT gửi cho RP login. | Không tạo user session. |
| Role bị rút. | ID token còn hạn, permission đã đổi. | RS theo freshness policy. |
| Callback sai state. | Transaction của phiên khác. | RP từ chối. |
| PKCE sai verifier. | Code-A với verifier-B. | AS từ chối. |
| Issuer mix-up. | OP-B response cho OP-A transaction. | RP từ chối. |
| RT dùng làm API AT. | Refresh token gửi Orders. | RS từ chối. |
| JWT typ giả. | typ=at+jwt nhưng chữ ký sai. | RS từ chối. |
| Introspection outage. | RS không xác minh được opaque token. | Fail safe. |
| Audience identifier trùng. | ID token aud trùng RS do cấu hình. | RS kiểm type/profile riêng. |
| Cross-tenant. | AT đúng aud nhưng order tenant khác. | RS từ chối theo policy. |

### Ma trận tối thiểu

**Cho hệ thống có RP client_id=dashboard-web và RS audience=orders-api:**

1. ID token aud=dashboard-web tại RP: kiểm OIDC authentication, chưa bỏ account policy.
2. ID token aud=dashboard-web tại Orders API: **DENY**.
3. Access token aud=orders-api tại Orders API: kiểm tiếp scope/permission.
4. Access token aud=orders-api tại RP ID-token validator: **DENY**.
5. Access token aud=payments-api tại Orders API: **DENY**.

## 23. Checklist trước production

1. **Ranh giới:** Đã tách rõ OP/AS, RP và RS?
2. **OIDC request:** Scope openid, client registration và redirect URI đúng?
3. **Flow:** Authorization Code + PKCE, state và issuer correlation?
4. **ID token chữ ký:** RP kiểm alg/keys từ issuer được tin?
5. **Issuer:** ID token iss khớp OP của transaction?
6. **Audience:** ID token aud chứa client_id, azp xử lý theo OIDC?
7. **Thời gian:** exp/iat, auth_time khi max_age yêu cầu?
8. **Nonce:** Nếu đã gửi, RP kiểm nonce ID token?
9. **Mapping:** Identity key issuer+sub, có linking policy?
10. **UserInfo:** Dùng access token phù hợp, sub khớp ID token?
11. **AT profile:** RS chỉ nhận JWT access token đúng profile hoặc opaque đã introspect?
12. **AT audience:** RS kiểm đúng resource identifier, không nhận ID token?
13. **AT scope:** RS kiểm scope endpoint; openid/profile/email không thay permission?
14. **Resource policy:** RS kiểm tenant, ownership, trạng thái bản ghi?
15. **Service identity:** Client credentials không bị hiểu thành End-User login?
16. **Refresh:** RT chỉ ở token endpoint, có storage/rotation/revocation policy?
17. **Session:** RP quản lý session TTL/logout/account status riêng?
18. **Freshness:** Hành động nhạy cảm có max_age/auth_time/step-up phù hợp?
19. **Cross-token:** Validator ID token và AT khác nhau, chống JWT confusion?
20. **TLS:** Mọi hop chứa code/token qua HTTPS với hostname validation?
21. **Logs:** Không ghi raw ID token, AT, RT, code, verifier hoặc client secret?
22. **Negative tests:** Có các test ID-token-at-API, AT-as-ID-token, sai aud/issuer/type/nonce/azp/UserInfo sub?

## Kết luận

**ID token và access token không thể sử dụng thay thế cho nhau**, dù cùng một OpenID Provider có thể phát cả hai trong cùng luồng Authorization Code + PKCE.

- **ID token** là **authentication assertion dành cho Relying Party/client**. RP cần xác minh issuer, chữ ký/thuật toán, audience=client_id, thời hạn và nonce/auth_time/azp theo OIDC.
- **Access token** là **credential dành cho Resource Server**. RS kiểm đúng audience, loại token/profile, scope, trạng thái và permission trên tài nguyên. Access token có thể là JWT hoặc opaque.
- **Refresh token**, nếu có, dùng ở token endpoint của AS để xin token mới, không phải bằng chứng đăng nhập hoặc credential API.

Tách **authentication ở RP** khỏi **authorization ở RS** giúp phòng token substitution, cross-JWT confusion và sai lầm cho rằng **đăng nhập thành công tự động cấp mọi quyền API**.

### Tài liệu tham khảo

- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 — Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth)
- [OpenID Connect Core 1.0 — UserInfo](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo)
- [OpenID Connect Core 1.0 — UserInfo Validation](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponseValidation)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)


