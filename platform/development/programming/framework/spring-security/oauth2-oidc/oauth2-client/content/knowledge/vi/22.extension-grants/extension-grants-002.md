# 22.2. JWT Bearer Grant và trường hợp trao đổi assertion

Trong **Spring Security OAuth 2.0/OIDC Client**, các luồng quen thuộc như Authorization Code, Refresh Token và Client Credentials thường bắt đầu từ một **`ClientRegistration`** và để Spring quản lý `OAuth2AuthorizedClient`. Tuy nhiên, một số hệ thống tích hợp doanh nghiệp cần một cơ chế khác: **dùng một JWT assertion đã được một bên tin cậy phát hành để xin OAuth access token tại Token Endpoint**.

Đó là trường hợp của **JWT Bearer Authorization Grant** được mô tả trong **RFC 7523**, dựa trên OAuth 2.0 Assertion Framework của **RFC 7521**.

Một yêu cầu có thể trông như sau:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-jwt-assertion>&
scope=orders.read
```

Authorization Server (AS) **không đơn giản chấp nhận một JWT bất kỳ**. Nó phải kiểm tra issuer, subject, audience, thời hạn, chữ ký, chính sách tin cậy, khả năng dùng lại assertion và quyền được phát token. Nếu hợp lệ theo contract đã đăng ký, AS có thể cấp access token để client gọi Resource Server.

Điều dễ gây nhầm lẫn nhất là JWT có thể xuất hiện ở **ba vị trí khác nhau**:

- **JWT Bearer Grant:** JWT là **authorization grant/assertion**, được gửi bằng tham số `assertion`.
- **JWT Client Authentication (`private_key_jwt`):** JWT là **bằng chứng xác thực chính OAuth client**, được gửi bằng tham số `client_assertion`.
- **OAuth 2.0 Token Exchange (RFC 8693):** một token/assertion có thể được đưa vào `subject_token` theo giao thức **token exchange**, với `grant_type` khác.

Ba cơ chế này có thể tồn tại trong cùng một hệ thống, thậm chí kết hợp ở một số Authorization Server, nhưng **không thể dùng thay thế lẫn nhau chỉ vì đều chứa JWT**.

Bài học trình bày vai trò của assertion, cấu trúc request, các JWT claims quan trọng, ví dụ ký JWT, kiểm soát replay, phân biệt grant và client authentication, so sánh với Token Exchange, cách tích hợp mở rộng trong Spring Security Client và những tình huống triển khai thực tế.

## 1. JWT Bearer Grant giải quyết vấn đề gì?

Giả sử một tổ chức có:

- Hệ thống **Identity/Token Broker** đã xác thực nhân viên hoặc workload bằng một cơ chế sẵn có.
- **Authorization Server** chuyên cấp OAuth access token cho APIs.
- **Spring Boot integration service** cần lấy access token nhưng không thực hiện browser redirect của Authorization Code Flow.
- **Resource Server** như Orders API, chỉ nhận OAuth access token thuộc audience/scopes được phép.

Token Broker có thể phát một **JWT assertion ngắn hạn, được ký bằng khóa tin cậy**. Spring service mang assertion này đến AS. AS xác minh assertion, đánh giá chính sách rồi cấp access token cho Orders API.

```mermaid
sequenceDiagram
    autonumber
    participant Source as Identity / Assertion Issuer
    participant App as Spring OAuth2 Client
    participant AS as Authorization Server
    participant API as Orders API

    Source->>App: JWT assertion đã ký
    App->>App: Bảo vệ assertion, không coi là API token
    App->>AS: POST /token, grant_type=jwt-bearer, assertion=JWT
    AS->>AS: Xác minh iss/sub/aud/exp/chữ ký/replay/policy
    alt Assertion được chấp nhận
        AS-->>App: OAuth access token + granted scopes
        App->>API: Authorization: Bearer access token
        API->>API: Kiểm tra token, audience, scope, quyền dữ liệu
        API-->>App: Kết quả
    else Assertion bị từ chối
        AS-->>App: OAuth error (ví dụ invalid_grant)
    end
```

Điểm then chốt: **assertion được dùng để yêu cầu token; token mới được cấp mới là credential mà Resource Server nhận**.

### 1.1. Những tình huống thường xuất hiện

| Trường hợp | Ý tưởng | Điều kiện bắt buộc |
|---|---|---|
| Tích hợp SSO/STS doanh nghiệp | STS phát signed JWT mô tả subject, client đổi lấy access token | AS tin issuer/key và có authorization policy |
| Hệ thống batch hành động thay subject đã xác thực | Client trình JWT assertion theo một thỏa thuận delegation | Subject/issuer phải được cấp quyền, không phải self-assert tùy ý |
| Identity federation | Assertion từ trust domain A được AS B tiếp nhận | Federation contract, audience, signature và claim mapping |
| Legacy token broker | Broker phát JWT ngắn hạn để đổi lấy OAuth token | AS hỗ trợ grant theo RFC 7523 |
| Workload sử dụng JWT assertion | Workload có credential dạng signed JWT từ issuer tin cậy | AS xác định rõ quyền workload và phạm vi cấp token |

Một hệ thống không nên chọn JWT Bearer Grant chỉ vì muốn “khỏi đăng nhập”. Đây là **một cơ chế authorization grant có quan hệ tin cậy đã định nghĩa**, không phải đường tắt cho phép client tự đặt bất kỳ `sub` nào rồi lấy access token với danh tính đó.

## 2. Nhắc lại Authorization Grant, Client Authentication và Access Token

Trong OAuth 2.0 cần phân biệt ba khái niệm:

1. **Authorization grant:** một bằng chứng/ủy quyền mà client trình với AS để xin access token.
2. **Client authentication:** AS kiểm tra **OAuth client nào** đang gọi Token Endpoint, theo phương thức được đăng ký.
3. **Access token:** credential AS cấp để client trình với Resource Server.

```text
Authorization grant
   + (Client authentication khi cần)
   + Token Endpoint policy
       |
       v
Authorization Server
       |
       v
Access token
       |
       v
Resource Server
```

Một JWT assertion có thể được dùng làm **grant**; một JWT assertion *khác* có thể được dùng để xác thực client. Trong cả hai trường hợp, tên trường form và mục đích xác minh khác nhau.

### 2.1. Không phải JWT nào cũng là access token

JWT chỉ là một **định dạng token/assertion** dựa trên JSON, có thể được ký bằng JWS. Có nhiều loại JWT:

- **OIDC ID Token:** kết quả authentication dành cho Relying Party.
- **OAuth JWT access token:** credential dành cho Resource Server.
- **JWT assertion trong RFC 7523:** bằng chứng phục vụ Token Endpoint.
- **JWT dùng cho `private_key_jwt`:** bằng chứng client sở hữu private key.
- **JWT do một Token Broker/STS phát hành:** có thể là input cho cơ chế trao đổi nếu AS hỗ trợ.

Chữ ký hợp lệ **không tự quyết định mục đích token**. Một ID Token hợp lệ dành cho OAuth client không được mặc định đem làm JWT bearer assertion hoặc access token gửi API.

## 3. RFC 7521 và RFC 7523 có quan hệ thế nào?

### 3.1. RFC 7521: Assertion Framework

RFC 7521 mô tả mô hình dùng **assertion** cho OAuth 2.0, gồm hai hướng:

- **Assertion làm authorization grant.**
- **Assertion làm client authentication credential.**

Framework tách bạch hai vai trò để một profile định nghĩa assertion format, validation và các tham số request cụ thể.

### 3.2. RFC 7523: JWT profile

RFC 7523 quy định profile dùng **JWT** cho cả hai hướng trên.

Với **authorization grant**, Token Endpoint nhận:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<JWT>
```

Với **client authentication**, Token Endpoint nhận:

```text
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<JWT>
```

Hai URN khác nhau. Không tự thay `assertion` thành `client_assertion`, hoặc thay grant type bằng client assertion type.

### 3.3. Kể cả khi dùng JWT, chính sách cấp token vẫn thuộc AS

RFC 7523 xác định một giao thức trao assertion. Nó không cung cấp một sơ đồ role/permission toàn cục cho mọi hệ thống.

Ví dụ AS có thể quy định:

```text
Trusted issuer:
  https://broker.corp.example

Allowed subject namespace:
  employee:*

Audience:
  https://auth.example.org/oauth2/token

Allowed client:
  integration-portal

Allowed scopes:
  orders.read

Forbidden:
  role escalation
  cross-tenant subject substitution
  arbitrary audience
```

Đây là chính sách **do triển khai** quyết định, không phải quyền tự phát sinh chỉ vì JWT chứa một claim `scope`.

## 4. Cấu trúc JWT assertion

Một JWT được ký bằng JWS có dạng:

```text
BASE64URL(protected-header)
.
BASE64URL(claims-payload)
.
BASE64URL(signature)
```

Ví dụ header JSON trước khi encode:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "broker-key-2026-11"
}
```

Ví dụ payload:

```json
{
  "iss": "https://broker.corp.example",
  "sub": "employee-725",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794800090,
  "jti": "c6ca42e2-9aaf-4bb0-8a2e-19b60ce85ab5"
}
```

Các số timestamp chỉ minh họa. Trong hệ thống thực tế phải tạo theo **thời gian hiện hành**, không hard-code các giá trị này.

### 4.1. Ý nghĩa của các claims

| Claim | Vai trò trong JWT bearer profile | Điều cần kiểm tra |
|---|---|---|
| `iss` | Issuer đã phát assertion | Có thuộc issuer đáng tin cậy không? |
| `sub` | Subject mà assertion đại diện | Chủ thể có hợp lệ và được phép theo contract không? |
| `aud` | Đối tượng nhận assertion, thường là AS/Token Endpoint | Có đúng audience Token Endpoint mà AS chấp nhận không? |
| `exp` | Thời điểm assertion hết hiệu lực | Chưa hết hạn, giới hạn TTL |
| `iat` | Thời điểm phát | Hợp lý theo clock skew/chính sách |
| `nbf` | Không hợp lệ trước thời điểm này | Đã đến thời điểm hiệu lực chưa? |
| `jti` | ID riêng của assertion | Kiểm soát replay trong khoảng thời gian hiệu lực |
| `kid` | Header để chọn khóa xác minh | Chỉ chọn khóa thuộc trust store của issuer |
| `alg` | Thuật toán JWS | Thuộc allowlist, không chấp nhận `none` |
| Claims nghiệp vụ | Tenant, mục đích, quyền, actor... | Đúng schema và nguồn đã được ủy quyền |

Theo JWT bearer profile, `iss`, `sub`, `aud` và `exp` là các claims trọng yếu bắt buộc của JWT assertion; `iat`, `nbf`, `jti` có vai trò bổ sung theo profile/chính sách. Với bảo mật hiện đại, `jti`/TTL ngắn và replay detection rất đáng cân nhắc khi AS hỗ trợ.

### 4.2. Audience của assertion khác audience của access token

**Audience của assertion** thường hướng đến AS hoặc Token Endpoint:

```text
assertion.aud =
  https://auth.example.org/oauth2/token
```

**Audience của access token được AS phát hành** hướng đến Resource Server:

```text
access_token.aud =
  orders-api
```

Không đặt `assertion.aud=orders-api` rồi kỳ vọng AS phải chấp nhận nếu hợp đồng yêu cầu Token Endpoint URL. Và không đưa assertion có audience Token Endpoint đến Orders API để giả làm access token.

### 4.3. Claims nghiệp vụ không tự có hiệu lực

Một JWT chứa:

```json
{
  "sub": "employee-725",
  "role": "ADMIN",
  "scope": "orders.write"
}
```

không tự buộc AS cấp scope `orders.write`. AS phải:

1. Xác định issuer có quyền phát claim đó hay không.
2. Kiểm tra client registration và grant permission.
3. Áp chính sách subject, tenant, audience và scope.
4. Quyết định granted scope phù hợp.

Không để một client tự ký JWT với bất kỳ `sub`/`role` nào, rồi cho phép quyền cao hơn chỉ vì chữ ký kiểm tra được theo khóa mà client tự đăng ký không giới hạn.

## 5. Quy trình xác minh assertion tại Authorization Server

Một AS đáng tin cậy cần xử lý nhiều điều kiện hơn chỉ có chữ ký.

```mermaid
flowchart TD
    REQ["POST /token, JWT Bearer Grant"]
    PARSE["Parse form và JWT có giới hạn kích thước"]
    T{"Grant type/issuer được phép?"}
    ALG{"JWS alg, kid, signature hợp lệ?"}
    CLAIM{"iss/sub/aud/exp/nbf/iat hợp lệ?"}
    REPLAY{"jti/TTL/replay policy thỏa?"}
    POLICY{"Client + subject + scopes<br/>+ tenant policy được phép?"}
    OK["Phát OAuth access token<br/>cho resource/scope phù hợp"]
    FAIL["OAuth error response"]

    REQ --> PARSE --> T
    T -->|"Không"| FAIL
    T -->|"Có"| ALG
    ALG -->|"Không"| FAIL
    ALG -->|"Có"| CLAIM
    CLAIM -->|"Không"| FAIL
    CLAIM -->|"Có"| REPLAY
    REPLAY -->|"Không"| FAIL
    REPLAY -->|"Có"| POLICY
    POLICY -->|"Không"| FAIL
    POLICY -->|"Có"| OK
```

### 5.1. Xác minh chữ ký đúng issuer

Khi assertion có `iss=https://broker.corp.example`, AS phải tra **khóa được đăng ký/tin cậy cho issuer đó**. Không lấy `kid` hoặc `jku` rồi tự động tải khóa từ URL tùy ý do JWT mang theo.

Nếu AS tin nhiều issuers, mỗi issuer phải có tập khóa/algorithms và quyền riêng. Không gộp tất cả khóa vào một danh sách rồi thử xác minh JWT của mọi issuer bằng mọi khóa mà không phân định trust boundary.

### 5.2. Không tin “alg: none”

Một payload JWT có thể tự nhận:

```json
{"alg":"none"}
```

Nếu profile cần signed assertion, việc chấp nhận unsigned JWT sẽ làm mất bằng chứng issuer. AS phải có allowlist algorithms và kiểm tra chữ ký phù hợp; không tự tin vào `alg` do token tự khai mà không có policy.

### 5.3. Kiểm soát thời gian

Thời hạn JWT nên **ngắn**. AS có thể chấp nhận clock skew nhỏ nhưng không cho một assertion dùng nhiều ngày nếu nghiệp vụ chỉ cần trao đổi trong vài chục giây.

Kiểm tra:

```text
now < exp + allowedSkew
now + allowedSkew >= nbf (nếu có)
iat không nằm quá xa tương lai
exp - iat nằm trong TTL policy
```

Đây là mô hình kiểm tra minh họa; ranh giới chính xác thuộc chính sách AS. Các client/servers cần đồng bộ đồng hồ đáng tin.

### 5.4. Replay detection

Một JWT còn hạn có thể bị kẻ tấn công lấy cắp rồi gửi lại. `jti` là ID riêng của assertion, thường kết hợp `iss` và TTL để phát hiện sử dụng lặp.

Một kho replay có thể đặt khóa:

```text
(issuer, jti) -> "consumed", expires after JWT validity + skew
```

Nhưng việc kiểm tra phải **atomic** khi có nhiều AS instances. Nếu hai nodes cùng thấy chưa có `jti` rồi cùng cho phép, replay detection không có tác dụng như mong muốn.

JWT `jti` không mã hóa payload và không ngăn đánh cắp assertion trước khi dùng. Vẫn cần TLS, TTL ngắn, client authentication và trust policy.

## 6. JWT Bearer Grant request tại Token Endpoint

### 6.1. Form fields bắt buộc

Một request cơ bản:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=eyJhbGciOiJSUzI1NiIs...
```

Trong HTTP thực tế, body là form-urlencoded trên một dòng; ở tài liệu dòng xuống để dễ đọc.

**`grant_type`**:

```text
urn:ietf:params:oauth:grant-type:jwt-bearer
```

**`assertion`**:

```text
JWT được cấp bởi issuer mà Authorization Server tin cậy
```

### 6.2. Scope trong request

Tùy AS và grant policy, client có thể xin:

```text
scope=orders.read
```

Đó là **scope yêu cầu**, không phải bảo đảm token mới sẽ có scope tương ứng. AS quyết định phạm vi cuối cùng dựa trên assertion, client, subject, audience và chính sách.

### 6.3. Client authentication nếu yêu cầu

JWT bearer grant **không tự thay thế mọi yêu cầu xác thực OAuth client**. Với confidential client, AS có thể yêu cầu `client_secret_basic`:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-authorization-assertion>
```

Một AS khác có thể dùng mTLS hoặc JWT client authentication. Phương thức nào được chấp nhận phải khớp client registration và security policy.

### 6.4. Token response

Ví dụ:

```json
{
  "access_token": "<new-oauth-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
```

AS có thể cấp token opaque hoặc JWT. **Không mặc định có refresh token**, ID token, hoặc quyền nào khác; các trường bổ sung phụ thuộc grant profile và AS.

OAuth client sẽ gửi **access_token trả về**, không phải JWT `assertion` ban đầu, khi gọi Orders API.

## 7. JWT Bearer Grant không đồng nghĩa private_key_jwt

Đây là phần dễ nhầm nhất khi cấu hình Spring Security Client.

### 7.1. private_key_jwt là Client Authentication

Trong `private_key_jwt`, client ký một JWT để chứng minh **quyền kiểm soát private key** đã đăng ký với AS. Ví dụ Token Endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=<signed-client-authentication-jwt>&
scope=reports.read
```

Ở đây **grant vẫn là `client_credentials`**. JWT ở tham số `client_assertion` chỉ là **client authentication credential**.

### 7.2. Claims của private_key_jwt

Payload thường có:

```json
{
  "iss": "reports-service-client",
  "sub": "reports-service-client",
  "aud": "https://auth.example.org/oauth2/token",
  "exp": 1794800090,
  "iat": 1794800000,
  "jti": "b8abfa56-5106-4118-8a34-7e1f165e7083"
}
```

Với JWT client authentication theo RFC 7523, `sub` phải xác định OAuth client ID, và `iss` nhận diện client theo profile. **Đó không phải yêu cầu user-delegation**.

Với JWT Bearer **authorization grant**, `iss` có thể là trusted token broker và `sub` là subject được broker đại diện, theo trust policy đã thiết lập.

### 7.3. So sánh trực tiếp

| Đặc điểm | JWT Bearer Grant | private_key_jwt Client Authentication |
|---|---|---|
| Mục đích | Trình assertion làm **authorization grant** | Xác thực **OAuth client** |
| Form field chính | `assertion` | `client_assertion` |
| Form URN | `urn:ietf:params:oauth:grant-type:jwt-bearer` | `urn:ietf:params:oauth:client-assertion-type:jwt-bearer` |
| `grant_type` | **JWT Bearer URN** | Có thể là `client_credentials`, `authorization_code`, `refresh_token`... |
| `iss` | Trusted assertion issuer | Client identity theo profile |
| `sub` | Subject theo assertion/delegation policy | **Client ID** |
| JWT chứng minh | Authorization assertion mà AS tin | Client sở hữu khóa được đăng ký |
| User impersonation có tự được phép? | **Không**; AS phải có delegation policy | **Không**; đây là client authentication |

### 7.4. Hai loại assertion có thể xuất hiện cùng request

Một AS có thể hỗ trợ **JWT bearer grant** và yêu cầu **private_key_jwt** để xác thực client trong cùng token request:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<authorization-assertion-for-subject>
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<client-authentication-assertion>
```

Hai JWT **có thể khác issuer, subject, audience policy và khóa ký**. Chúng không mặc định là cùng một chuỗi JWT. Có thể thiết kế sử dụng cùng một credential trong một số AS-specific profile, nhưng không nên giả định hoặc hoán đổi form fields mà chưa có contract.

## 8. JWT Bearer Grant khác OAuth Token Exchange RFC 8693

**OAuth 2.0 Token Exchange** (RFC 8693) là một grant mở rộng riêng dùng để trao đổi một token đã có lấy token khác, ví dụ từ một security domain/resource sang domain/resource khác hoặc theo delegation/impersonation policy.

### 8.1. Token Exchange request

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=<existing-security-token>&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Ajwt&
requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
resource=https%3A%2F%2Forders-api.example.org
```

Đây là ví dụ có `subject_token_type=urn:ietf:params:oauth:token-type:jwt`. Trong hệ thống khác, subject token có thể là access token, ID token hoặc token type khác nếu AS hỗ trợ và tin nguồn đó.

### 8.2. Hai dạng request đặt cạnh nhau

**JWT Bearer Grant (RFC 7523):**

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<jwt-assertion>
```

**Token Exchange (RFC 8693):**

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<input-token>
subject_token_type=urn:ietf:params:oauth:token-type:jwt
resource=...
```

Cả hai có thể chuyển từ một security credential sang OAuth access token nhưng **message format và validation contract khác nhau**.

### 8.3. Delegation và impersonation không tự xảy ra

Trong Token Exchange có thể xuất hiện ngữ nghĩa:

- **Impersonation:** token mới đại diện một subject theo policy, actor không nhất thiết được biểu diễn.
- **Delegation:** token mới có thể diễn đạt actor đang hành động thay subject, ví dụ các claims actor theo profile.

JWT Bearer Grant cũng có thể được dùng trong tình huống subject delegation theo contract, nhưng chỉ vì `sub` ghi người A không có nghĩa client được phép impersonate người A.

Authorization Server cần kiểm tra actor/client identity, subject, trust, tenant và quyền được cấp. Không chấp nhận `sub` từ input do browser gửi rồi tự biến thành delegated token.

### 8.4. Chọn cơ chế nào?

| Tình huống | Cơ chế cần xem xét |
|---|---|
| Có JWT assertion được issuer tin cậy phát cho grant | **RFC 7523 JWT Bearer Grant** |
| Có OAuth access token từ API A, cần token cho API B | **RFC 8693 Token Exchange**, nếu AS hỗ trợ |
| Client dùng RSA/EC key để xác thực tại Token Endpoint | **private_key_jwt** |
| Workload cần token của chính nó, không có End-User | **client_credentials**, có thể kèm private_key_jwt/mTLS |
| Browser user đăng nhập OIDC | **Authorization Code + PKCE** |
| RP đã có refresh token hợp lệ | **Refresh Token Grant** |
| Có OIDC ID Token muốn đổi thành token khác | Chỉ theo **contract trao đổi token** mà AS chấp nhận; không mặc định ID Token có thể dùng làm JWT grant |

## 9. JWT Bearer assertion không mặc nhiên là OIDC ID Token

Một sai lầm dễ gặp: “ID Token cũng là JWT được OP ký, vậy lấy nó làm `assertion` là được”.

ID Token có các thuộc tính khác:

```json
{
  "iss": "https://login.example.org",
  "sub": "user-725",
  "aud": "portal-client-id",
  "exp": 1794800090
}
```

Trong đó `aud=portal-client-id` là **Relying Party** đã đăng nhập. JWT Bearer Grant thường đòi audience nhận assertion là **Authorization Server/Token Endpoint theo policy**. AS không nên chấp nhận ID Token dành cho một client như bearer grant bất kỳ.

Điều kiện cần nếu AS muốn nhận một token đầu vào:

1. AS tuyên bố profile/trust contract nào được hỗ trợ.
2. Token type/purpose có đúng không?
3. Issuer/key đã được đăng ký chưa?
4. Audience có hướng tới AS hoặc request hợp lệ không?
5. Subject/actor có được ủy quyền không?
6. Replay, lifetime, scopes và tenant policy đã được kiểm tra chưa?

Nếu sản phẩm muốn chuyển OIDC ID Token hoặc OAuth access token thành access token khác, cơ chế **Token Exchange** có thể diễn đạt chính xác hơn, nhưng vẫn phụ thuộc AS hỗ trợ.

## 10. Sơ đồ trust boundary khi dùng assertion

```mermaid
flowchart LR
    subgraph Identity["Identity Domain"]
      User["User hoặc workload đã xác thực"]
      Broker["Trusted Token Broker"]
      IssuerKey["Issuer Signing Key"]
      User --> Broker
      IssuerKey --> Broker
    end

    subgraph OAuth["OAuth Authorization Domain"]
      Client["Spring OAuth2 Client"]
      AS["Authorization Server"]
      Trust["Trusted Issuers / Keys / Policies"]
      Client -->|"assertion + client authentication"| AS
      Trust --> AS
    end

    subgraph Resource["Resource Domain"]
      API["Orders API"]
      Domain["User / tenant / object authorization"]
      API --> Domain
    end

    Broker -->|"signed JWT assertion"| Client
    AS -->|"OAuth access token"| Client
    Client -->|"Bearer access token"| API
```

Những mối quan hệ bắt buộc:

- **Broker → AS:** AS tin khóa/issuer và các quyền phát assertion.
- **Client → AS:** Client được đăng ký và có phương thức authentication phù hợp khi cần.
- **AS → API:** API tin access tokens AS phát cho đúng resource.
- **Subject → API:** API/domain kiểm tra quyền thực tế theo user/workload và tài nguyên.

Không có đường tắt từ “JWT được ký” đến “API phải cho truy cập”.

## 11. Tạo JWT assertion bằng Java và Nimbus JOSE + JWT

Dưới đây là ví dụ tạo **signed assertion** mà **một issuer được AS tin cậy** có thể phát. Code ký JWT **không trao quyền phát cho một service tùy ý**: AS phải đăng ký issuer, public key, claim contract và chính sách.

### 11.1. Thư viện

Một lựa chọn là **Nimbus JOSE + JWT**:

```groovy
dependencies {
    implementation 'com.nimbusds:nimbus-jose-jwt'
}
```

Dự án Spring Boot có dependency management phù hợp có thể quản lý phiên bản. Nếu không, cần chỉ định một phiên bản đã được kiểm soát bởi build của dự án.

### 11.2. AssertionSigner dùng private key

```java
import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

public final class AssertionSigner {

    private final RSAPrivateKey privateKey;
    private final String keyId;
    private final String trustedIssuer;
    private final String tokenEndpointAudience;

    public AssertionSigner(
            RSAPrivateKey privateKey,
            String keyId,
            String trustedIssuer,
            String tokenEndpointAudience) {
        this.privateKey = privateKey;
        this.keyId = keyId;
        this.trustedIssuer = trustedIssuer;
        this.tokenEndpointAudience = tokenEndpointAudience;
    }

    public String signForSubject(String subject) throws Exception {
        Instant now = Instant.now();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .keyID(keyId)
            .build();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(trustedIssuer)
            .subject(subject)
            .audience(tokenEndpointAudience)
            .issueTime(Date.from(now))
            .notBeforeTime(Date.from(now.minusSeconds(5)))
            .expirationTime(Date.from(now.plusSeconds(90)))
            .jwtID(UUID.randomUUID().toString())
            .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(privateKey));
        return jwt.serialize();
    }
}
```

Ví dụ sử dụng:

```java
AssertionSigner signer = new AssertionSigner(
    issuerPrivateKey,                 // Lấy từ KMS/HSM hoặc nguồn bảo mật
    "broker-key-2026-11",
    "https://broker.corp.example",
    "https://auth.example.org/oauth2/token"
);

String assertion = signer.signForSubject("employee-725");
```

Các biến ví dụ phải được inject từ secret/key management, không tạo private key trong code hoặc commit vào Git.

### 11.3. Những điều code ký không tự bảo đảm

Mã trên chỉ tạo một JWT có chữ ký. Nó **không tự chứng minh**:

- Service có quyền phát assertion cho `employee-725`.
- Người dùng đã đồng ý ủy quyền cho OAuth client.
- AS tin issuer/key này.
- Claims phù hợp scope/tenant authorization policy.
- Assertion chưa bị dùng lại.
- Resource Server sẽ chấp nhận access token được cấp.

Những kiểm tra đó phải do Token Broker và AS thực thi theo hợp đồng đã thiết kế. Nếu client không được AS công nhận là assertion issuer, việc tự tạo JWT bằng private key của mình là **không đủ**.

### 11.4. Quản lý private key

Không hard-code PEM/private key literal trong source code, YAML, test fixtures production hoặc container image.

Nên:

- Giữ private key trong KMS/HSM hoặc secret manager đáng tin.
- Giới hạn service account có thể ký JWT.
- Phân quyền theo mục đích và subject namespace.
- Dùng thuật toán ký AS cho phép, không cho caller tự chọn `alg`.
- Đặt `kid` phù hợp key rotation.
- Quản lý public key/JWKS phía AS theo trust policy.
- Không log assertion vừa ký.
- Không ký payload có claims tùy ý từ request body mà chưa kiểm soát.

## 12. Ví dụ gọi Token Endpoint bằng RestClient

Trong một **Servlet/backend integration service**, có thể triển khai HTTP client gọi grant mở rộng. Đây là cách minh họa giao thức, **chưa phải provider được tích hợp tự động vào `OAuth2AuthorizedClientManager`**.

### 12.1. DTO token response

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OAuthTokenResponse(
    @JsonProperty("access_token") String accessToken,
    @JsonProperty("token_type") String tokenType,
    @JsonProperty("expires_in") Long expiresIn,
    @JsonProperty("scope") String scope,
    @JsonProperty("refresh_token") String refreshToken
) {}
```

Một token response thực tế còn có thể chứa các trường khác. Response handling phải kiểm tra `access_token`, `token_type`, `expires_in` và scope theo contract; không mặc định mọi trường luôn có hoặc luôn đúng kiểu.

### 12.2. JWT Bearer token client

```java
import java.util.Set;

import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

public final class JwtBearerTokenClient {

    public static final String JWT_BEARER_GRANT =
        "urn:ietf:params:oauth:grant-type:jwt-bearer";

    private final RestClient restClient;
    private final String tokenUri;
    private final String clientId;
    private final String clientSecret;

    public JwtBearerTokenClient(
            RestClient.Builder builder,
            String tokenUri,
            String clientId,
            String clientSecret) {

        this.restClient = builder.build();
        this.tokenUri = tokenUri;
        this.clientId = clientId;
        this.clientSecret = clientSecret;
    }

    public OAuthTokenResponse exchange(
            String signedAssertion,
            Set<String> requestedScopes) {

        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();

        form.add("grant_type", JWT_BEARER_GRANT);
        form.add("assertion", signedAssertion);

        if (requestedScopes != null && !requestedScopes.isEmpty()) {
            form.add("scope", String.join(" ", requestedScopes));
        }

        return restClient.post()
            .uri(tokenUri)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .headers(headers ->
                headers.setBasicAuth(clientId, clientSecret))
            .body(form)
            .retrieve()
            .body(OAuthTokenResponse.class);
    }
}
```

Ví dụ giả định:

- AS đã đăng ký confidential client với `client_secret_basic`.
- `tokenUri` là **HTTPS Token Endpoint cố định do server config cung cấp**.
- Assertion do một issuer được AS tin cậy tạo.
- Form request và response phù hợp AS-specific contract.

Không dùng `setBasicAuth(...)` nếu AS đăng ký client authentication bằng `private_key_jwt` hoặc mTLS; khi đó thay bằng implementation đúng. Không cho caller/browser truyền `tokenUri` tùy ý vì request có thể gửi client secret và assertion tới host không tin cậy.

### 12.3. Vì sao không nên tự log HTTP body?

Form body chứa `assertion` là một credential nhạy cảm. HTTP interceptor, proxy và wire logs có thể ghi nguyên request:

```text
grant_type=...
assertion=eyJhbGciOi...
```

Chỉ ghi metadata như registration ID, issuer alias, error code, thời lượng request, không ghi JWT/assertion hoặc raw client authentication.

### 12.4. Không giữ JWT assertion đã dùng để retry vô hạn

Một assertion ngắn hạn có thể đã được AS chấp nhận hoặc đánh dấu `jti` đã dùng. Nếu network timeout xảy ra sau khi AS xử lý request nhưng trước khi client nhận response, retry cùng assertion có thể bị từ chối do replay detection.

Nếu policy cho phép retry một lỗi transient, cần xác định có nên **tạo assertion mới** và cách bảo vệ idempotency/replay. Không làm vòng lặp vô hạn trên cùng `assertion`.

## 13. Lấy OAuth2AccessToken từ token response

Sau khi Token Endpoint cấp token, ứng dụng có thể biểu diễn kết quả bằng `OAuth2AccessToken` để đưa vào abstraction Spring Security.

```java
import java.time.Instant;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class AccessTokenFactory {

    public OAuth2AccessToken create(OAuthTokenResponse response) {
        if (response == null
                || response.accessToken() == null
                || response.accessToken().isBlank()) {
            throw new IllegalArgumentException("Missing access_token");
        }

        if (!"Bearer".equalsIgnoreCase(response.tokenType())) {
            throw new IllegalArgumentException("Unexpected token_type");
        }

        if (response.expiresIn() == null
                || response.expiresIn() <= 0) {
            throw new IllegalArgumentException("Invalid expires_in");
        }

        Set<String> scopes =
            response.scope() == null || response.scope().isBlank()
                ? Set.of()
                : Arrays.stream(response.scope().trim().split("\\s+"))
                    .filter(s -> !s.isBlank())
                    .collect(Collectors.toUnmodifiableSet());

        Instant issuedAt = Instant.now();
        Instant expiresAt =
            issuedAt.plusSeconds(response.expiresIn());

        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            response.accessToken(),
            issuedAt,
            expiresAt,
            scopes
        );
    }
}
```

Đây là **mã xử lý response minh họa**, không phải một `OAuth2AccessTokenResponseClient` đã đăng ký vào manager. Trên production, cần xử lý đúng trường hợp `scope` không xuất hiện theo OAuth contract (tùy AS, có thể dùng requested scopes hoặc grant policy đã biết), clock skew và lỗi deserialize.

**Không tự gắn scopes rộng hơn token response/AS policy** bằng cách lấy toàn bộ scopes yêu cầu và coi đó là scopes thực được cấp nếu AS đã trả scope hẹp hơn.

### 13.1. Không tự sửa expiresAt để token “sống lâu hơn”

`expires_in` và token lifetime do AS quyết định. Đổi giá trị ở client không khiến Resource Server tiếp tục chấp nhận access token sau khi hết hạn.

### 13.2. Access token không thay thế principal

`OAuth2AccessToken` mang credential gọi API. Nếu assertion đại diện cho subject cụ thể, hệ thống vẫn phải quản lý **chủ thể được ủy quyền, client identity và domain permissions**. Không coi việc token được cấp đồng nghĩa người dùng đang có Web Session đã đăng nhập OIDC.

## 14. Spring Security có hỗ trợ JWT Bearer Grant mặc định không?

Trong các cấu hình OAuth2 Client thông dụng, `OAuth2AuthorizedClientProviderBuilder` hỗ trợ các grant như:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

**Không nên giả định `JWT Bearer Grant` được hỗ trợ chỉ bằng cách thêm chuỗi grant type vào `application.yml`.**

Các grant mở rộng như RFC 7523 thường cần:

1. Một `ClientRegistration` mô tả grant type tùy chỉnh (nếu tích hợp vào client framework).
2. Một cách lấy assertion từ issuer đáng tin cậy.
3. Một token response client xây đúng form request.
4. Một `OAuth2AuthorizedClientProvider` tùy chỉnh, nếu muốn dùng `OAuth2AuthorizedClientManager`.
5. Thành phần persistence/authorization success/failure handling phù hợp.
6. Kiểm soát TTL/replay, client authentication và scopes.

Tính năng hỗ trợ sẵn, lớp API và tên builder phụ thuộc phiên bản Spring Security; cần xem documentation của **phiên bản dự án** trước khi chọn extension point. Không dùng API Servlet đồng bộ vào reactive stack theo quán tính.

## 15. Mô hình mở rộng OAuth2AuthorizedClientProvider

### 15.1. Các đối tượng liên quan

```text
ClientRegistration
      |
      v
OAuth2AuthorizedClientManager
      |
      v
OAuth2AuthorizedClientProvider (custom JWT Bearer)
      |
      v
TrustedAssertionSupplier
      |
      v
JWT Bearer Token Client
      |
      v
Authorization Server Token Endpoint
      |
      v
OAuth2AccessTokenResponse / OAuth2AuthorizedClient
      |
      v
OAuth2AuthorizedClientService / Repository
```

Nếu dùng manager, **provider chịu trách nhiệm grant logic**; manager chịu trách nhiệm nạp/lưu authorized client theo context và success/failure policy.

### 15.2. Grant type custom

Có thể biểu diễn grant type với:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

AuthorizationGrantType jwtBearerGrant =
    new AuthorizationGrantType(
        "urn:ietf:params:oauth:grant-type:jwt-bearer"
    );
```

Không nhầm với:

```java
AuthorizationGrantType.CLIENT_CREDENTIALS
```

Chúng là hai grant khác nhau, dù cùng được thực thi tại Token Endpoint.

### 15.3. ClientRegistration trong Java

Một registration ví dụ:

```java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration assertionRegistration =
    ClientRegistration.withRegistrationId("partner-assertion")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(new AuthorizationGrantType(
            "urn:ietf:params:oauth:grant-type:jwt-bearer"))
        .tokenUri("https://auth.example.org/oauth2/token")
        .scope("orders.read")
        .build();
```

Các biến `clientId`, `clientSecret` lấy từ cấu hình backend/secret manager. Tùy phiên bản Spring Security/metadata provider, builder có thêm ràng buộc hoặc fields cần khai báo; cần khớp API thực tế.

Đây là cách làm rõ `grantType` custom trong `ClientRegistration`. **Tự tạo registration không tự thực thi JWT Bearer Grant** nếu chưa có provider/token client hỗ trợ.

## 16. Pseudocode provider JWT Bearer custom

Một provider extension có thể có các bước:

1. Kiểm tra grant type của registration.
2. Xem authorized client cũ còn sử dụng được hay không.
3. Lấy **assertion mới** từ một trusted issuer/supplier.
4. Gọi Token Endpoint bằng JWT Bearer Grant.
5. Chuyển token response thành `OAuth2AccessToken`.
6. Trả `OAuth2AuthorizedClient` mới cho manager.
7. Để manager success handler lưu kết quả theo repository/service.

### 16.1. Interface khái niệm cho assertion supplier

```java
public interface TrustedAssertionSupplier {

    String issueAssertion(
        String registrationId,
        String principalName
    );
}
```

**Hợp đồng an toàn:** chỉ một trusted component được gọi supplier, chỉ được phát assertion cho principal/subject mà nó có quyền đại diện. Không truyền `principalName` lấy từ URL bất kỳ.

### 16.2. Provider code minh họa

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class JwtBearerAuthorizedClientProvider
        implements OAuth2AuthorizedClientProvider {

    private static final String GRANT =
        "urn:ietf:params:oauth:grant-type:jwt-bearer";

    private final TrustedAssertionSupplier assertions;
    private final JwtBearerTokenClient tokenClient;
    private final AccessTokenFactory tokenFactory;

    public JwtBearerAuthorizedClientProvider(
            TrustedAssertionSupplier assertions,
            JwtBearerTokenClient tokenClient,
            AccessTokenFactory tokenFactory) {
        this.assertions = assertions;
        this.tokenClient = tokenClient;
        this.tokenFactory = tokenFactory;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        var registration = context.getClientRegistration();

        if (!GRANT.equals(
                registration.getAuthorizationGrantType().getValue())) {
            return null;
        }

        OAuth2AuthorizedClient existing = context.getAuthorizedClient();

        if (existing != null
                && existing.getAccessToken().getExpiresAt() != null
                && existing.getAccessToken().getExpiresAt()
                    .isAfter(Instant.now().plusSeconds(60))) {
            // Theo provider contract: không cần reauthorize.
            return null;
        }

        String principalName = context.getPrincipal().getName();

        String assertion = assertions.issueAssertion(
            registration.getRegistrationId(), principalName);

        var response = tokenClient.exchange(
            assertion, registration.getScopes());

        OAuth2AccessToken accessToken = tokenFactory.create(response);

        return new OAuth2AuthorizedClient(
            registration,
            principalName,
            accessToken
        );
    }
}
```

Đây là **khung tích hợp minh họa**, chưa phải thư viện production-ready:

- `TrustedAssertionSupplier` phải được bảo vệ về identity/authorization.
- `JwtBearerTokenClient` trong ví dụ sử dụng đồng bộ `RestClient`.
- Logic không minh họa refresh token vì grant có thể yêu cầu cấp assertion mới.
- Provider cần policy về exception mapping, error classification, clock skew, scope response, token type, concurrency.
- Không có key cache, certificate validation hay distributed replay handling trong đoạn code.
- Nếu AS trả refresh token theo extension, việc hỗ trợ cần có contract và storage cụ thể, không mặc định.

Tuy nhiên, code thể hiện ranh giới chính xác: **JWT bearer grant là một provider tùy chỉnh**, không phải `clientCredentials()` hoặc `refreshToken()` tự có.

### 16.3. Manager tích hợp custom provider

Với scheduled/backend worker dùng service-based manager:

```java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientProvider provider =
    new JwtBearerAuthorizedClientProvider(
        assertionSupplier,
        jwtBearerTokenClient,
        accessTokenFactory
    );

var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
    registrationRepository,
    authorizedClientService
);

manager.setAuthorizedClientProvider(provider);

OAuth2AuthorizedClientManager authorizedClientManager = manager;
```

Các dependencies trên phải được cấu hình/inject trong application context; đây là code định hướng wiring.

Trong Servlet request, có thể dùng `DefaultOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientRepository` nếu token phải liên kết với user web session. Nhưng JWT assertion grant có hợp đồng riêng; chọn manager đúng context và **không tự giả mạo user session**.

### 16.4. Cần quan tâm manager success/failure handlers

Khi provider trả authorized client mới, manager có thể dùng authorization success handler để lưu token. Nếu tự thay handler bằng một lambda chỉ ghi log, token mới có thể không được persist, khiến client xin token lặp lại mỗi request.

Failure handler phải xử lý lỗi của grant phù hợp; không dùng `invalid_grant` của JWT assertion như lý do xóa mọi user tokens hoặc disable client registration toàn hệ thống.

## 17. Khác biệt giữa Servlet và Reactive khi tùy biến grant

`JwtBearerTokenClient` dùng `RestClient` là **blocking HTTP call**. Điều này có thể phù hợp với backend Servlet service đã quản lý thread pool, nhưng **không nên gọi trực tiếp trên Reactor Netty event loop** trong WebFlux authentication path.

### 17.1. Servlet

Có thể dùng:

```text
OAuth2AuthorizedClientManager (synchronous)
   -> custom OAuth2AuthorizedClientProvider
   -> RestClient Token Endpoint call
```

với timeout, connection pool và bảo vệ credentials.

### 17.2. Reactive

Cần thiết kế tương ứng:

```text
ReactiveOAuth2AuthorizedClientManager
   -> reactive provider/extension
   -> WebClient Token Endpoint call
   -> Mono<OAuth2AuthorizedClient>
```

Ví dụ ý tưởng gọi Token Endpoint bằng WebClient:

```java
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public Mono<OAuthTokenResponse> exchangeReactive(
        WebClient client,
        String tokenUri,
        String assertion) {

    var form = new LinkedMultiValueMap<String, String>();
    form.add("grant_type",
        "urn:ietf:params:oauth:grant-type:jwt-bearer");
    form.add("assertion", assertion);

    return client.post()
        .uri(tokenUri)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .bodyValue(form)
        .retrieve()
        .bodyToMono(OAuthTokenResponse.class);
}
```

Mã reactive trên minh họa **form body**; nó **chưa bao gồm client authentication**. Trong triển khai thật, phải thêm client authentication theo registration, HTTPS/timeout và error mapping. Không coi đây là toàn bộ implementation RFC 7523.

Không dùng `.block()` trong Reactive HTTP filter chỉ để lấy token đồng bộ. Nếu assertion được ký qua một HSM/SDK đồng bộ, cần offload có kiểm soát hoặc dùng API async của HSM phù hợp.

## 18. Chọn nguồn assertion an toàn

Có hai nhóm nguồn thường gặp.

### 18.1. Issuer phát assertion ngoài ứng dụng

Ví dụ một trusted broker trả JWT assertion cho Spring service sau khi đã xác thực và kiểm tra quyền.

```text
Trusted Broker
  -> signed assertion with iss/sub/aud/exp/jti
  -> Spring OAuth client
  -> AS Token Endpoint
```

Ứng dụng cần xác định broker nào được tin và cách lấy assertion an toàn. Không cho người dùng dán một JWT tùy ý vào request rồi để client exchange thành OAuth token có quyền cao hơn.

### 18.2. Ứng dụng tự là issuer theo contract

Một hệ thống có thể được AS công nhận là assertion issuer. Khi đó service ký JWT bằng private key của **issuer**, chứ không phải một khóa bất kỳ do developer tạo.

AS phải giới hạn subject/scope mà issuer được phát. Một issuer có quyền ký không có nghĩa được phát assertion cho mọi người dùng/tenant.

### 18.3. Không lấy assertion từ headers không được xác thực

Anti-pattern:

```java
@PostMapping("/exchange")
public String exchange(@RequestHeader("X-User-JWT") String assertion) {
    // Đưa thẳng assertion bất kỳ đến AS.
}
```

Ngay cả nếu AS sẽ xác minh JWT, việc expose endpoint này có thể biến app thành **token exchange proxy/confused deputy**, tạo cơ chế truy cập token không có kiểm soát cho caller.

Tốt hơn: xác thực caller, xác minh chính sách được phép trao đổi, giới hạn issuer/subject/audience, áp dụng rate limits và tránh đưa raw OAuth access token cho browser nếu kiến trúc backend không cho phép.

## 19. Kiểm soát quyền chủ thể và khả năng impersonation

JWT Bearer Grant có thể dùng để trình assertion về một subject. Nhưng **điền `sub=employee-725` không tự chứng minh quyền hành động thay người này**.

AS nên kiểm tra:

1. Issuer có được phép assert subject thuộc namespace này không?
2. Client hiện tại có được dùng JWT Bearer Grant với issuer đó không?
3. Subject có bị khóa/thu hồi quyền không?
4. Client có thể yêu cầu scope nào cho subject?
5. Có ràng buộc tenant/organization nào?
6. Có yêu cầu actor/delegation chain không?
7. Có cần consent hoặc authorization từ người dùng trước đó không?
8. Resource Server có object-level authorization riêng không?

Một assertion được ký bởi issuer tin cậy nhưng có `sub` ngoài quyền issuer vẫn phải bị từ chối.

### 19.1. Ví dụ tenant isolation

```text
assertion:
  iss = corporate-broker
  sub = employee-725
  tenant = tenant-A

client:
  allowed_tenants = [tenant-A]

request:
  scope = orders.read

AS:
  may issue access token limited to tenant-A

Orders API:
  must still verify order belongs to allowed tenant
```

Nếu Orders API bỏ tenant/object checks và chỉ kiểm tra `scope=orders.read`, nguy cơ broken object-level authorization vẫn tồn tại.

### 19.2. Role không tự đến từ scope

Scope của access token mô tả phạm vi được cấp cho token/client; role của user hoặc workload là chính sách domain. Không tự biến `scope=orders.read` thành `ROLE_ORDER_ADMIN`.

## 20. Request và response mẫu: theo dõi từng bước

### 20.1. Assertion được phát

Issuer tạo:

```json
{
  "iss": "https://broker.corp.example",
  "sub": "employee-725",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800090,
  "jti": "75d9bc73-afc0-43e0-9abf-d5f0a4210a4c"
}
```

Issuer ký JWT với khóa `kid=broker-key-2026-11` đã đăng ký với AS.

### 20.2. Spring Client gửi grant

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-jwt>&scope=orders.read
```

### 20.3. AS xác minh và cấp access token

```json
{
  "access_token": "<oauth-access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

### 20.4. Client gọi Resource Server

```http
GET /api/orders HTTP/1.1
Host: orders-api.example.org
Authorization: Bearer <oauth-access-token>
```

### 20.5. Resource Server kiểm tra quyền

```text
token signature/introspection valid
AND issuer authorized
AND audience = orders-api
AND token not expired
AND scope includes orders.read
AND subject can read requested orders
AND tenant policy holds
```

**Không có request nào gửi JWT `assertion` trực tiếp đến Orders API như một access token**, trừ khi hệ thống đã định nghĩa một profile API hoàn toàn khác. Trong OAuth2 JWT Bearer Grant này, token dùng cho API là **token do AS trả về**.

## 21. Kiểm thử hợp đồng với Authorization Server

Trước khi triển khai production, tích hợp cần có các kịch bản contract rõ ràng.

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Assertion được issuer tin cậy ký, claims hợp lệ | AS có thể cấp token theo policy |
| JWT bị sửa payload sau khi ký | Từ chối vì chữ ký không hợp lệ |
| `alg=none` | Từ chối nếu profile yêu cầu signed assertion |
| Issuer không được đăng ký | Từ chối |
| `aud` là Resource Server thay vì Token Endpoint theo policy | Từ chối |
| `exp` đã qua | Từ chối |
| `nbf` nằm trong tương lai quá skew | Từ chối |
| JWT có `jti` đã dùng và replay policy bật | Từ chối |
| Client xin scope ngoài allowed scopes | Từ chối hoặc thu hẹp scope theo AS policy |
| Client auth credential sai | Từ chối |
| `sub` ngoài quyền issuer/client | Từ chối |
| Tenant claim không phù hợp policy | Từ chối |
| AS trả access token cho audience khác | API từ chối |
| Assertion hợp lệ nhưng user không được đọc object | API từ chối |
| Hai requests dùng một assertion đồng thời | Replay handling nhất quán theo policy |
| Key rotation đang diễn ra | Khóa cũ/mới được chấp nhận có kiểm soát trong cửa sổ chuyển tiếp |

**Một test “JWT có chữ ký đúng” không đủ** để chứng minh bảo mật của JWT Bearer Grant.

## 22. Lỗi OAuth2 thường gặp

Token Endpoint có thể trả:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "JWT assertion rejected"
}
```

Hoặc:

```json
{
  "error": "invalid_client"
}
```

### 22.1. Phân biệt lỗi

| Lỗi / hiện tượng | Nguyên nhân có thể | Cần kiểm tra |
|---|---|---|
| `unsupported_grant_type` | AS chưa bật JWT Bearer Grant | AS capabilities/client policy |
| `invalid_grant` | Assertion hết hạn, chữ ký sai, audience sai, replay hoặc subject không được phép | Issuer/claims/key/replay/policy |
| `invalid_client` | Client ID/secret, mTLS hoặc private_key_jwt sai | Client authentication |
| `invalid_scope` | Scope không được phép | Registration/grant/subject rights |
| `invalid_request` | Thiếu `assertion`, sai form encoding hoặc nhiều tham số không hợp lệ | HTTP Token Endpoint request |
| `unauthorized_client` | Client không được dùng JWT Bearer Grant | Client registration tại AS |
| HTTP 429 | AS rate limit | Token reuse, throttling, backoff |
| HTTP 5xx/timeout | AS/network không ổn định | Connection/TLS/timeouts, không retry mù quáng |
| Token được cấp nhưng API trả 401 | Sai audience/issuer/expiry/token type | Resource Server validation |
| Token được cấp nhưng API trả 403 | Scope hoặc domain authorization thiếu | API permissions |
| Chỉ lỗi ở một node | Clock skew/keys/config khác nhau | Deployment configuration và time sync |
| Sau key rotation đột ngột invalid_grant | AS không biết `kid`/public key mới | Key distribution và rotation rollout |

Không ghi nguyên assertion hoặc private key vào log để debug lỗi. Nên ghi error code, issuer alias, client registration ID, correlation ID không bí mật và thời lượng request.

### 22.2. HTTP status code khác nhau

Token Endpoint trả `invalid_grant` không có nghĩa API sẽ trả 403. Đó là lỗi ở **bước xin token**, trước khi client có access token mới.

Khi client đã nhận access token nhưng API trả 401/403, cần chẩn đoán **Resource Server token validation và authorization**, không mặc định AS đã sai.

## 23. Xử lý assertion đã hết hạn hoặc bị dùng lại

JWT assertion thường chỉ sống một khoảng thời gian ngắn. Nếu code lưu assertion trong một biến singleton rồi dùng lại cho mọi request:

```java
// Không phù hợp cho assertion ngắn hạn/one-time.
private static String cachedAssertion;
```

AS có thể từ chối vì `exp` hoặc replay detection.

Một thiết kế thường phù hợp:

```text
Cần token mới
  -> lấy/phát assertion mới từ trusted issuer
  -> gửi Token Endpoint
  -> nhận OAuth access token
  -> tái sử dụng access token theo expiresAt
  -> khi token cần cấp lại: lấy assertion mới
```

Không nên **xin token mới trước mỗi API call** khi token hiện hành còn hợp lệ và có thể tái sử dụng theo policy. Điều đó gây tải lên issuer/AS và làm tăng rủi ro dùng lại assertion không đúng.

### 23.1. Đồng thời nhiều requests

Nếu nhiều threads cùng phát/assert JWT và trao đổi token, cần giới hạn concurrency/rate limit:

- Cùng một signed assertion không nên được nhiều callers gửi lặp nếu AS dùng one-time `jti`.
- Mỗi assertion mới cần `jti` thực sự duy nhất.
- Access token được lưu theo đúng principal/registration.
- Nếu AS phát token cho subject khác nhau, không cache chỉ theo registration ID.
- Nếu token exchange xảy ra sau một request timeout, không retry cùng assertion một cách mù quáng.

## 24. Cấp phát, lưu trữ và quản lý OAuth2AuthorizedClient

`OAuth2AuthorizedClient` chứa:

```text
ClientRegistration
principalName
OAuth2AccessToken
optional OAuth2RefreshToken
```

Với JWT Bearer Grant, sau khi có OAuth access token, ứng dụng có thể lưu authorized client theo principal/registration để sử dụng trong các API calls tiếp theo.

### 24.1. Principal và subject của assertion không mặc nhiên là một

`principalName` trong `OAuth2AuthorizedClient` là khóa Spring Security dùng để liên kết record với một principal. `sub` trong JWT assertion là subject được issuer khẳng định theo grant.

Chúng **có thể liên quan nhưng không bắt buộc là cùng một chuỗi**. Trong delegated access, ứng dụng phải định nghĩa rõ mapping và không làm mất subject/tenant identity.

Ví dụ:

```text
authorized client key:
  registrationId = partner-assertion
  principalName = broker-user-725

JWT assertion:
  iss = https://broker.corp.example
  sub = employee-725

OAuth access token:
  audience = orders-api
  permissions = scoped by AS policy
```

Không dùng principal name lấy từ query `?subject=...` để tùy ý truy xuất token của user khác.

### 24.2. Đừng lưu raw assertion cùng access token vô hạn

Sau khi assertion đã được đổi thành access token, không nhất thiết phải persist JWT assertion cũ trong authorized client store. Nó có TTL ngắn và có thể là credential one-time.

Nếu phải lưu assertion phục vụ audit hoặc protocol-specific workflow, cần threat model, retention và encryption rõ; thường tốt hơn chỉ lưu metadata/ID sự kiện thay vì raw signed JWT.

### 24.3. Khi nào lưu refresh token?

Grant type JWT Bearer không tự bảo đảm AS sẽ cấp refresh token. Nếu AS-specific policy có trả refresh token, phải kiểm tra contract và bảo vệ/persist theo quy trình refresh grant, nhưng không tự suy luận refresh token luôn có.

### 24.4. Quyền thu hồi

Access token đã cấp có thể tiếp tục hợp lệ đến expiration, ngay cả khi assertion ban đầu hết hạn. Vì vậy:

- Chọn access token TTL phù hợp.
- Xem xét revocation/introspection khi quyền thay đổi.
- Kiểm tra domain permissions ở API nếu cần hiệu lực thu hồi nhanh.
- Không nhầm `assertion.exp` với `accessToken.expiresAt`.

## 25. Spring OAuth2 Login và JWT Bearer Grant là hai luồng khác nhau

### 25.1. OAuth2/OIDC Login

Trong browser login:

```text
Browser
  -> /oauth2/authorization/company
  -> OP /authorize
  -> /login/oauth2/code/company
  -> Token Endpoint
  -> OIDC ID Token
  -> Authenticated principal/web session
```

Spring Security `oauth2Login()` xử lý browser authorization code flow và tạo principal.

### 25.2. JWT Bearer Grant

```text
Trusted assertion issuer
  -> signed JWT assertion
  -> Spring OAuth client
  -> Token Endpoint JWT bearer grant
  -> OAuth access token
  -> Resource Server
```

Không nhất thiết có browser, authorization redirect, login callback hoặc ID Token. Spring Security `oauth2Login()` **không tự động xử lý JWT Bearer Grant** chỉ vì app đã bật OIDC login.

Một ứng dụng có thể kết hợp cả hai, nhưng phải phân biệt principal/session và token lifecycle của từng flow.

### 25.3. Không tạo OidcUser giả từ assertion

Một JWT assertion mà AS chấp nhận không có nghĩa ứng dụng đã xác thực OIDC End-User thông qua `oauth2Login()`. Đừng tự tạo `OidcUser` hoặc đặt `SecurityContext` authenticated chỉ vì có assertion chưa được xử lý theo cơ chế xác thực phù hợp.

Nếu ứng dụng muốn liên kết assertion với một local user, phải có xác minh/authorization đầy đủ và thiết kế security context rõ ràng.

## 26. Khi JWT assertion là bằng chứng từ một hệ thống cũ

Một bài toán tích hợp phổ biến:

- Hệ thống A dùng JWT assertion được ký bởi STS cũ.
- Hệ thống B là Spring Boot client cần gọi API OAuth mới.
- AS mới hỗ trợ JWT Bearer Grant với trusted issuer A.

Quy trình migration:

1. Đăng ký trusted issuer A, các public keys/algorithms và allowed subject namespace tại AS.
2. Đăng ký OAuth client B và grant type JWT bearer, client authentication method.
3. Xác định audience Token Endpoint mà AS yêu cầu.
4. Tạo JWT assertions ngắn hạn, jti duy nhất và đúng claims.
5. Định nghĩa subject/tenant/role mapping, không chuyển claims tùy tiện.
6. Trao assertion lấy OAuth access token.
7. Resource Server chỉ nhận OAuth access token, không cần tin trực tiếp JWT legacy.
8. Lưu authorized client và theo dõi token expiry.
9. Thiết kế revocation, key rotation và audit.
10. Giảm dần dependency vào legacy assertion khi kiến trúc mới có grant phù hợp.

Điều có giá trị ở đây là **tách miền tin cậy**: Resource Server không cần chấp nhận mọi JWT từ hệ thống cũ; AS làm điểm policy/token issuance tập trung.

## 27. Multi-tenant và nhiều issuers

Trong hệ thống nhiều đối tác, AS có thể tin các assertion issuers khác nhau:

```text
issuer = https://sts.partner-a.example
  allowedClientIds = [client-a]
  allowedTenants = [tenant-a]
  allowedScopes = [orders.read]

issuer = https://sts.partner-b.example
  allowedClientIds = [client-b]
  allowedTenants = [tenant-b]
  allowedScopes = [orders.read, reports.read]
```

Không coi hai `sub=employee-725` ở hai issuers là cùng một người. External identity nên được biểu diễn theo:

```text
(issuer, subject)
```

Không chỉ theo `sub` hoặc email.

### 27.1. Nguy cơ issuer confusion

Nếu JWT tự khai `iss=partner-a` nhưng AS lại dùng public key của partner-b để xác minh vì cùng `kid=main`, trust policy bị nhầm.

`kid` chỉ là định danh khóa **trong ngữ cảnh issuer/key set**, không phải một định danh toàn cục có thể dùng giữa nhiều issuers.

### 27.2. Scope names có thể cùng chuỗi nhưng khác nghĩa

`orders.read` có thể được hai AS/provider định nghĩa khác nhau. Khi hệ thống đa issuer hoặc nhiều Resource Servers, policy phải xác định scope semantics và audience cụ thể, không chỉ so chuỗi scope.

### 27.3. Không nhận issuer từ URL tự do

Không cho browser gửi:

```text
POST /exchange?issuer=https://arbitrary.example
```

rồi tải JWKS/discovery từ đó và tin JWT. Đây là rủi ro SSRF và issuer trust bypass. Issuer phải có trong allowlist/trust registry phía server.

## 28. Ký JWT assertion và key rotation

### 28.1. Key ID

Header:

```json
{
  "alg": "RS256",
  "kid": "broker-key-2026-11",
  "typ": "JWT"
}
```

`kid` giúp AS chọn public key tương ứng trong tập khóa đã đăng ký cho issuer.

### 28.2. Rotation có kiểm soát

Một quy trình có thể là:

1. Tạo key pair mới trong KMS/HSM.
2. Cung cấp public key/JWKS mới cho AS theo trust policy.
3. Bắt đầu ký assertions mới bằng `kid` mới.
4. Duy trì khóa cũ trong cửa sổ đủ ngắn để xử lý assertion còn hiệu lực nếu policy cho phép.
5. Dừng sử dụng private key cũ.
6. Thu hồi public key cũ sau thời gian chuyển tiếp phù hợp.
7. Audit các lỗi `invalid_grant`/unknown `kid`.

Nếu issuer đổi `kid` trước khi AS nhận public key mới, mọi assertions mới có thể bị từ chối. Nếu AS giữ khóa cũ quá lâu, rủi ro khi key bị lộ có thể tăng.

### 28.3. Không cho JWT tự chọn verification URL

Các JWS headers như `jku`/`x5u` cần được xử lý cực kỳ thận trọng. AS không nên fetch tùy ý một URL do assertion attacker cung cấp và dùng khóa tại đó làm nguồn tin cậy.

Trust key origin phải được quản lý server-side.

## 29. Bảo vệ assertion và access token trong vận hành

### 29.1. Những giá trị bí mật

| Dữ liệu | Độ nhạy cảm | Biện pháp |
|---|---|---|
| Private signing key | Rất cao | KMS/HSM, ACL, rotation, không log |
| `client_secret` | Rất cao | Secret manager, TLS, rotation |
| Signed assertion | Cao khi còn hiệu lực | TTL ngắn, tránh logs, replay controls |
| OAuth access token | Cao | TLS, storage an toàn, audience/scopes |
| Refresh token nếu có | Rất cao | Mã hóa, rotation/revocation policy |
| `kid` | Metadata | Có thể log có kiểm soát, không thay key trust |
| `jti` | Correlation/replay identifier | Lưu ngắn hạn, không chứa PII nhạy cảm |
| Granted scopes | Metadata authorization | Không coi là dữ liệu công khai vô điều kiện |

### 29.2. Log an toàn

Ví dụ:

```text
event=jwt_bearer_grant
registrationId=partner-assertion
issuerAlias=corp-broker
subjectType=employee
grantType=jwt-bearer
outcome=invalid_grant
elapsedMs=180
correlationId=<non-secret-id>
```

Không ghi:

```text
assertion=eyJ...
Authorization: Basic <client-credentials>
client_assertion=eyJ...
access_token=eyJ...
refresh_token=...
private_key=-----BEGIN PRIVATE KEY-----
```

`jti` có thể giúp đối chiếu replay, nhưng tránh log raw PII trong `sub`/claims. Nếu log `jti`, kiểm soát retention và quyền truy cập.

### 29.3. HTTPS và token endpoint trust

Token Endpoint phải được cấu hình từ nguồn backend tin cậy, dùng HTTPS và certificate validation. Không tắt TLS verification để sửa lỗi môi trường phát triển rồi mang cấu hình đó lên production.

Nếu HTTP client follow redirect, phải bảo đảm nó **không gửi assertion/client secret sang host khác**. Token Endpoint thông thường không cần redirect sang domain bất kỳ.

## 30. Các anti-pattern cần tránh

### 30.1. Dùng một JWT tự ký rồi tự nhận mình là admin

```json
{
  "iss": "my-app",
  "sub": "ceo",
  "role": "ADMIN"
}
```

Nếu AS không công nhận issuer và quyền assert subject đó, phải từ chối. Không dùng chữ ký hợp lệ làm lý do cho phép impersonation.

### 30.2. Nhầm grant_type với client_assertion_type

Sai:

```text
grant_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
```

Đúng cho JWT Bearer Grant:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<JWT>
```

### 30.3. Đưa ID Token của RP vào assertion khi audience không khớp

OIDC ID Token thường dành cho RP client ID, không phải Token Endpoint. Không bỏ audience validation chỉ để nhận nó.

### 30.4. Gửi assertion tới API như access token

API thường nhận **access token AS cấp**, không phải JWT assertion dùng ở Token Endpoint.

### 30.5. Bỏ exp, aud hoặc chữ ký validation

Nếu profile yêu cầu JWT signed assertion, bỏ các kiểm tra này phá ranh giới tin cậy.

### 30.6. Giữ assertion trong cache vô thời hạn

Assertion có TTL ngắn và thường có replay policy. Khi cần xin OAuth access token mới, phải có cách lấy assertion mới an toàn.

### 30.7. Dùng một jti cho mọi assertion

`jti` nên riêng biệt; dùng một hằng số làm replay detector hoặc client bị từ chối ngay request thứ hai.

### 30.8. Đưa JWT vào URL

Không đặt assertion vào query params của Token Endpoint hoặc logs. Dùng HTTPS POST form body và redaction.

### 30.9. Cho phép input quyết định tokenUri

Client secret/assertion có thể rò rỉ qua endpoint không tin cậy. Token URI phải từ cấu hình server-side allowlist.

### 30.10. Chỉ cấu hình custom grant string mà bỏ custom provider

`ClientRegistration` biết grant type nhưng không tự thực thi Token Endpoint JWT assertion request.

### 30.11. Chạy RestClient blocking trong WebFlux event loop

Dùng reactive token response client hoặc cô lập blocking I/O có kiểm soát. Không gọi `block()` trong reactive request handler.

### 30.12. Dùng một cache token cho nhiều subjects

Nếu grant đại diện cho từng user/tenant, token cache phải giữ đúng principal/client/resource context.

### 30.13. Bỏ object-level authorization tại API

AS đã cấp scope không có nghĩa user được xem mọi đơn hàng. Resource Server phải kiểm tra dữ liệu cụ thể.

### 30.14. Retry invalid_grant vô hạn

Một assertion hết hạn hoặc bị replay sẽ không hợp lệ chỉ vì gửi lại nhiều lần.

### 30.15. Log assertion để debug

Signed JWT có thể chứa subject và là credential còn hiệu lực. Log raw assertion làm tăng khả năng đánh cắp hoặc lộ danh tính.

## 31. Quy trình triển khai có thể áp dụng

Khi dự án thật sự cần JWT Bearer Grant:

1. **Xác định đúng grant.** JWT là authorization assertion, không chỉ private_key_jwt hay Token Exchange.
2. **Xác nhận AS hỗ trợ RFC 7523** và client được phép dùng grant type này.
3. **Định nghĩa trust contract:** issuer, public keys, subject namespace, allowed clients, scopes, tenants, token endpoint audience.
4. **Định nghĩa client authentication:** client_secret_basic, private_key_jwt, mTLS hoặc phương thức AS chấp nhận.
5. **Thiết kế issuer/signer:** private key trong KMS/HSM, alg allowlist và rotation policy.
6. **Phát assertion ngắn hạn:** `iss`, `sub`, `aud`, `exp` và các claims cần thiết; `jti` duy nhất theo replay policy.
7. **Trao assertion qua POST form-urlencoded** với đúng `grant_type` và `assertion`.
8. **Xử lý token response:** kiểm tra token type, expiry, granted scopes; không coi assertion là API access token.
9. **Tích hợp Spring Security đúng mức:** client adapter trước, hoặc custom `OAuth2AuthorizedClientProvider`/manager nếu cần lifecycle thống nhất.
10. **Chọn Servlet hay Reactive đúng stack** và tránh blocking I/O trên event loop.
11. **Lưu authorized client theo đúng principal/registration/resource**; không trộn user/tenant/workload.
12. **Resource Server kiểm tra access token độc lập**, gồm issuer, audience, expiry, scope và domain permissions.
13. **Giới hạn retry/replay:** không dùng lại assertion sau khi đã tiêu thụ, xử lý timeout một cách có chính sách.
14. **Bảo vệ secrets và logs:** assertion, client assertion, access token và signing key không được lộ.
15. **Kiểm tra key rotation và lỗi âm:** issuer lạ, audience sai, token hết hạn, `jti` lặp, subject ngoài quyền, scope vượt chính sách.

**Ghi nhớ:** **JWT Bearer Grant (RFC 7523)** sử dụng một **JWT authorization assertion** tại Token Endpoint để xin OAuth access token. Nó khác **`private_key_jwt`** (JWT xác thực OAuth client) và khác **Token Exchange RFC 8693** (trao token qua `subject_token` với grant type riêng). Trong Spring Security OAuth2 Client, grant này thường cần **custom integration/provider**, không nên trông đợi `oauth2Login()` hay `clientCredentials()` tự xử lý. Chữ ký JWT chỉ là một phần của trust contract: issuer, subject, audience, TTL, replay protection và quyền được cấp tại AS/API mới quyết định khả năng truy cập an toàn.

## 32. Tài liệu tham khảo

- [RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7521): mô hình sử dụng assertion cho grant và client authentication.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT Bearer Grant, client assertion và validation requirements.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): `subject_token`, `actor_token`, token types và token exchange grant.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): grant, token endpoint, client authentication và access token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `iat`, `nbf`, `jti`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, algorithms và signature.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT algorithm, cross-JWT confusion, trust boundary và validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token protection và OAuth threat model.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu access token cho resource/audience cụ thể.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration`, `OAuth2AuthorizedClientManager` và providers.
- [Spring Security — Reactive OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive manager và token HTTP integrations.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): phân biệt OIDC browser login với assertion grants.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): thư viện JOSE/JWT cho Java.
