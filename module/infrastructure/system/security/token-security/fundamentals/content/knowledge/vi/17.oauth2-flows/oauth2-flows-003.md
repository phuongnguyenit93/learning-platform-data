# Client Credentials flow

## Mục tiêu học tập

Trong chương **OAuth2 flows** của học phần bảo mật token, **Client Credentials flow** là luồng OAuth 2.0 cho phép một ứng dụng/dịch vụ đã được đăng ký và xác thực với **Authorization Server (AS)** xin **access token dựa trên quyền của chính client**, thay vì dựa trên một người dùng đang đăng nhập. Luồng này đặc biệt quan trọng trong hệ thống backend, batch job, microservice và tác vụ tự động.

Sau bài này, bạn có thể:

1. Giải thích điều kiện sử dụng **grant type `client_credentials`** và phân biệt **client/service principal** với **end-user**.
2. Mô tả chính xác các vai trò **Client**, **Authorization Server** và **Resource Server**, cùng bước xin token tại **token endpoint**.
3. Hiểu **client authentication**, `client_id`, `client_secret_basic`, `private_key_jwt` và mTLS; phân biệt xác thực client với phạm vi quyền được cấp.
4. Thiết kế **scope**, **resource indicator** và **audience** theo từng API, không dùng một service token làm quyền toàn cục.
5. Triển khai cách xin/caching access token trong Java/Spring Security ở mức minh họa, xử lý thời hạn, lỗi và luân chuyển credential.
6. Nhận diện lỗi **confused deputy**, vượt quyền giữa tenant, nhầm service token với delegated user token, và rủi ro bearer token bị đánh cắp/phát lại.

## 1. Client Credentials flow là gì?

**Client Credentials** là một **authorization grant** trong OAuth 2.0, được định nghĩa ở **RFC 6749, mục 4.4**. Client dùng thông tin xác thực của chính mình để yêu cầu access token từ AS. Theo đặc tả OAuth 2.0, grant này **chỉ được dùng bởi confidential client** — ứng dụng có khả năng bảo vệ credential phù hợp trong môi trường triển khai.

Ví dụ thực tế:

- **Billing Worker** chạy mỗi giờ, lấy các hóa đơn được hệ thống cho phép để đối soát.
- **Orders Service** gọi Billing API để lấy trạng thái thanh toán cho một quy trình nội bộ đã được ủy quyền.
- **Job xuất báo cáo** gọi Reports API dựa trên quyền của service account do tổ chức phê duyệt.
- **Monitoring Agent** đọc một endpoint chẩn đoán được bảo vệ bằng access token dành riêng cho monitoring.

Trong các tình huống này, máy có thể hoạt động khi **không có người dùng cuối đang mở trình duyệt**. AS không cần chuyển người dùng tới trang đăng nhập và màn hình consent cho **mỗi lần xin token**.

### Những điều luồng này không đồng nghĩa

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| “Client dùng danh tính của chính ứng dụng để xin token.” | **Đúng**. | AS xác thực client và xét quyền ứng dụng/service đã được cho phép. |
| “Không có bước redirect trình duyệt trong grant này.” | **Đúng**. | Giao dịch chính là request từ client tới token endpoint. |
| “Không có user nào cần đăng nhập mỗi lần worker xin token.” | **Đúng**. | Không phải delegated end-user grant. |
| “Token mặc nhiên có quyền của mọi người dùng.” | **Sai**. | Service permission không tự trở thành user permission. |
| “Có `client_id` là đủ để xác thực một confidential client.” | **Sai**. | `client_id` là định danh, không phải bí mật. |
| “Client Credentials yêu cầu access token phải là JWT.” | **Sai**. | AS có thể phát JWT access token hoặc opaque token. |
| “Đã có token thì mọi Resource Server cùng AS phải nhận.” | **Sai**. | Mỗi RS kiểm tra audience, scope và policy của mình. |
| “Grant này luôn có refresh token.” | **Sai**. | RFC 6749 nói refresh token **SHOULD NOT** được cấp trong phản hồi Client Credentials. |

> **Ý chính:** Client Credentials flow là **ủy quyền cho một ứng dụng/dịch vụ** theo chính sách AS, không phải cách bỏ qua việc kiểm tra quyền hoặc “đăng nhập hộ một người dùng”.

## 2. Ai làm gì trong giao dịch này?

### Các vai trò

| Vai trò OAuth | Trong ví dụ đối soát | Trách nhiệm |
|---|---|---|
| **Client** | `billing-worker` | Tự xác thực với AS, đề nghị scope/resource, giữ token và gọi API. |
| **Authorization Server** | `https://auth.example.test` | Xác thực client, kiểm tra grant/policy, quyết định cấp token, audience, scope và thời hạn. |
| **Resource Server** | `billing-api` | Nhận access token, xác minh token, kiểm tra quyền service và dữ liệu. |
| **Resource Owner** | Tổ chức hoặc chủ thể đã sắp đặt quyền phù hợp | Việc cho phép client dùng grant này cần được xác lập trước qua chính sách/quản trị, không thông qua user consent mỗi request. |

Theo RFC 6749, Client Credentials phù hợp khi Client truy cập tài nguyên **do chính client kiểm soát**, hoặc tài nguyên của Resource Owner khác mà quyền đã được **sắp đặt trước** với AS. Trong một hệ thống doanh nghiệp, điều này thường được thể hiện bằng **client registration**, service account, admin approval và policy theo tenant.

### Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant Worker as Billing Worker (confidential client)
    participant AS as Authorization Server
    participant API as Billing API (Resource Server)
    Worker->>AS: POST /token: client authentication + grant_type=client_credentials + scope
    AS->>AS: Xác thực client, kiểm tra grant, scope, resource và policy
    alt Client không đủ điều kiện
        AS-->>Worker: OAuth error, không cấp token
    else Được phép
        AS-->>Worker: Access token, token_type, expires_in, scope nếu cần
        Worker->>API: GET /invoices + access token
        API->>API: Kiểm tra token, audience, scope, principal, tenant và quyền dữ liệu
        API-->>Worker: Dữ liệu được phép hoặc từ chối
    end
~~~

**Điểm cần nhớ:** Luồng trên **không có authorization code**, **không có PKCE redirect**, **không có user login/session** hay OIDC ID token cho người dùng theo mặc định. Tuy nhiên, AS vẫn phải có **quyết định ủy quyền dựa trên chính sách**, và RS vẫn thực thi quyền trên dữ liệu.

## 3. Điều kiện trước khi Client xin token

Không thể chỉ gửi `grant_type=client_credentials` tới bất kỳ AS nào rồi nhận token. Cần có **hợp đồng đăng ký và tin cậy**.

### Ví dụ đăng ký client

~~~yaml
# Metadata minh họa, KHÔNG phải định dạng chuẩn của một nhà cung cấp AS.
client_id: billing-worker
client_type: confidential
allowed_grants:
  - client_credentials
client_authentication:
  method: private_key_jwt
allowed_resources:
  - billing-api
allowed_scopes:
  - billing:read
token_policy:
  access_token_ttl_seconds: 600
  sender_constrained_required: false
tenant_policy:
  allowed_tenants:
    - tenant-a
~~~

Các thông tin quan trọng:

1. **`client_id`:** định danh của ứng dụng, **không phải secret**; AS biết client nào đang được đề nghị.
2. **Client authentication method:** cách client chứng minh danh tính, ví dụ secret, private-key assertion hoặc TLS client certificate.
3. **`allowed_grants`:** AS phải cho client dùng `client_credentials`; việc tồn tại client registration không tự cấp mọi grant.
4. **Resource/audience được phép:** Billing Worker có thể chỉ được xin token cho Billing API.
5. **Scope tối đa:** service chỉ được xin những thao tác cần cho nhiệm vụ, ví dụ `billing:read`.
6. **Tenant/quyền nghiệp vụ:** client chỉ được phép truy cập tài nguyên của tổ chức/tenant đã được sắp đặt.
7. **Thời hạn và ràng buộc token:** AS quyết định TTL, bearer hay sender-constrained theo rủi ro.

Không coi file YAML minh họa là đủ để hệ thống tự bảo mật. Quyền phải được **thực thi ở AS và RS**, khóa/secret phải được quản lý bên ngoài dữ liệu công khai.

### Confidential client không đồng nghĩa “chỉ chạy nội bộ là an toàn”

Backend/service có thể bảo vệ credential **nếu được triển khai đúng**: secret manager, quyền máy chủ giới hạn, TLS, rotation, cấu hình log và kiểm soát người có quyền sử dụng khóa.

Ngược lại, **SPA JavaScript hoặc ứng dụng mobile phân phối cho người dùng không thể bảo vệ một client secret chung như bí mật thật**. Không dùng Client Credentials trực tiếp từ frontend để né đăng nhập người dùng; đó là sai mô hình grant và làm lộ quyền service.

## 4. Các bước cấp token chi tiết

Giả sử Billing Worker muốn đọc hóa đơn thông qua `billing-api`.

### Bước 1 — Client chuẩn bị request

Client xác định:

~~~text
Token endpoint: https://auth.example.test/token
Client ID:      billing-worker
Grant type:     client_credentials
Target API:     billing-api
Requested scope: billing:read
~~~

Nếu AS hỗ trợ **Resource Indicators (RFC 8707)**, client có thể thêm `resource` mô tả URI tài nguyên đích:

~~~text
resource=https://api.example.test/billing
~~~

Không phải AS nào cũng hỗ trợ `resource`. Khi AS không hỗ trợ, cách ràng buộc audience phải được **AS/RS cấu hình rõ** qua client registration hoặc cơ chế được hệ thống hỗ trợ; không suy audience từ tên scope một cách tùy tiện.

### Bước 2 — Client tự xác thực với AS

Client gửi request tới **token endpoint qua HTTPS**, sử dụng phương thức xác thực đã đăng ký. Ví dụ với `client_secret_basic`, Authorization header mang HTTP Basic credentials được biểu diễn bằng placeholder:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=billing%3Aread
~~~

**Lưu ý kỹ thuật:** HTTP Basic dùng **Base64 chuẩn**, không phải Base64URL. Giá trị trong ngoặc nhọn chỉ là placeholder, không phải credential thật. Khi tạo HTTP Basic theo RFC 6749 `2.3.1`, client ID và client secret được form-encode trước khi ghép thành username/password; **tránh tự lắp header thủ công**, hãy dùng thư viện OAuth/HTTP có hỗ trợ phù hợp.

Ví dụ một request có tham số `resource` khi AS hỗ trợ:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Authorization: Basic <BASE64_STANDARD_ENCODED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=billing%3Aread&resource=https%3A%2F%2Fapi.example.test%2Fbilling
~~~

**Không** đặt `client_secret` vào query URL, source code, ticket, log hoặc analytics. RFC 6749 yêu cầu client **không truyền client ID/client secret bằng nhiều phương thức xác thực trong cùng request**; nên cấu hình một phương thức rõ ràng cho mỗi client.

### Bước 3 — AS xác minh và xét policy

AS cần kiểm tra tối thiểu:

- **Client authentication:** secret/assertion/certificate đúng với registration và chưa bị thu hồi.
- **Grant được phép:** `client_credentials` có nằm trong grant types đã đăng ký không?
- **Audience/resource:** Billing Worker được phép xin token cho API nào?
- **Scope được phép:** `billing:read` có thực sự thuộc tập quyền của client và tài nguyên đó không?
- **Tenant/service identity:** client có quyền truy cập tenant được đề nghị hay không, theo nguồn đáng tin?
- **Chính sách vận hành:** token lifetime, proof-of-possession, trạng thái service account và rủi ro của thao tác.

Không nên lấy toàn bộ `scope`/`aud` từ request rồi chép thẳng vào JWT. **Client yêu cầu quyền; AS mới quyết định quyền thực sự cấp.**

### Bước 4 — AS trả access token

Phản hồi thành công minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<OPAQUE_ACCESS_TOKEN_PLACEHOLDER>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "billing:read"
}
~~~

`access_token` có thể là **opaque string** hoặc JWT tùy AS. `expires_in` là thời gian sống được báo trong **giây**. `token_type=Bearer` nghĩa là trình token bằng scheme bearer; khi AS phát token DPoP-bound có profile tương ứng, token type và cách sử dụng sẽ khác.

Trong OAuth 2.0, nếu scope đã cấp **khác** scope request, trường `scope` trong token response phải phản ánh sự khác biệt theo đặc tả; khi giống nhau, phản hồi **có thể lược bỏ** `scope`. Client phải biết phạm vi thực sự có hiệu lực từ response/hợp đồng, không tự giả định mọi requested scope đã được cấp.

**RFC 6749 `4.4.3`: refresh token SHOULD NOT được bao gồm trong phản hồi Client Credentials.** Thông thường, khi access token sắp hết hạn, client dùng **client credential** để xin token mới; không cần giữ refresh token dài hạn. Nếu AS có profile đặc thù khác, phải xác minh chính sách cụ thể, không mặc định hành vi đó.

### Bước 5 — Client gọi Resource Server

~~~http
GET /invoices HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_BILLING>
Accept: application/json
~~~

Resource Server kiểm tra token theo mô hình được cấu hình, sau đó mới áp dụng **scope và policy trên hóa đơn thực tế**. Việc có token do AS cấp **không** đồng nghĩa client được xem mọi invoice.

## 5. Token cấp cho ứng dụng mang danh tính gì?

Trong delegated grant có user, token thường liên hệ với **người dùng và client**. Trong Client Credentials, không có end-user đang giao quyền theo từng lần gọi; token thường mô tả **service/client principal** theo quy tắc của AS.

### JWT access token minh họa

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "billing-worker",
  "client_id": "billing-worker",
  "aud": "billing-api",
  "scope": "billing:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456600,
  "jti": "sample-access-token-id"
}
~~~

**Đây là payload giả lập, không phải JWT đã ký.** Ví dụ sử dụng cùng giá trị `sub` và `client_id` theo mô hình service principal của AS. **Không phải mọi token format/provider đều biểu diễn các claim theo cách này**; RS phải dựa trên profile tin cậy. Trong **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, khi grant là Client Credentials, `sub` có thể dùng để xác định client application theo quy định profile, không được diễn giải tự động thành ID người dùng.

### Các claim cần phân biệt

| Trường | Trong ví dụ | Cần hiểu đúng |
|---|---|---|
| **`iss`** | `https://auth.example.test` | Bên phát hành phải thuộc issuer được RS tin cậy. |
| **`sub`** | `billing-worker` | Service/client principal theo hợp đồng, **không phải user mặc định**. |
| **`client_id`** | `billing-worker` | Client được AS gắn với token; là **định danh**, không phải mật khẩu. |
| **`aud`** | `billing-api` | RS nào được phép nhận token. |
| **`scope`** | `billing:read` | Action nào client được phép yêu cầu trên API. |
| **`exp`, `nbf`, `iat`** | NumericDate | Thời gian hợp lệ/phát hành theo giây Unix. |
| **`jti`** | ID token minh họa | Có thể hỗ trợ theo dõi/thu hồi nếu hệ thống quản lý; không tự chống replay. |

Với **opaque token**, RS có thể nhận metadata đáng tin từ **token introspection (RFC 7662)**:

~~~json
{
  "active": true,
  "client_id": "billing-worker",
  "sub": "billing-worker",
  "aud": "billing-api",
  "scope": "billing:read",
  "exp": 1893456600
}
~~~

`active=true` chỉ hỗ trợ xác định trạng thái; RS còn phải kiểm tra **audience, scope, service identity và quyền trên dữ liệu**. Nếu introspection thiếu metadata mà RS cần theo hợp đồng, **không mặc định chấp nhận**.

### Không sử dụng ID token để gọi API

**OIDC ID token** dùng cho **Relying Party/Client** để xác minh kết quả xác thực người dùng theo OIDC. Client Credentials không phải một luồng user login và thông thường **không phát ID token cho user**. Không “mượn” ID token từ luồng khác để làm access token service, hay gửi refresh token đến Billing API.

## 6. Scope và audience phải giới hạn quyền dịch vụ

### Vì sao `scope` không phải quyền toàn cục?

Giả sử hệ thống có:

| Resource Server | Audience | Scope liên quan | Ý nghĩa trong ví dụ |
|---|---|---|---|
| Billing API | `billing-api` | `billing:read` | Đọc những hóa đơn service được phép. |
| Billing API | `billing-api` | `payments:refund` | Yêu cầu hoàn tiền theo chính sách riêng. |
| Orders API | `orders-api` | `orders:read` | Đọc những đơn được phép. |
| Reports API | `reports-api` | `reports:export` | Xuất báo cáo đã được cho phép. |

Access token của Billing Worker với `aud=billing-api` và `scope=billing:read`:

- **Không** được dùng tại Orders API dù hai API tin cùng issuer.
- **Không** được gọi endpoint hoàn tiền chỉ vì đã có quyền đọc hóa đơn.
- **Không** được đọc invoice thuộc tenant khác nếu policy không cho phép.
- **Không** tự hợp lệ tại API khác có scope tên `read` giống nhau.

`resource` của RFC 8707 cho phép client chỉ rõ tài nguyên đích khi AS hỗ trợ. **`resource` không bắt buộc bằng chuỗi `aud`**; ví dụ AS có thể ánh xạ `https://api.example.test/billing` thành `billing-api`.

### Nên cấp token riêng theo API

Với nhiều RS khác nhau, một thực hành giúp giảm rủi ro là xin access token **đúng audience và scope của API cần gọi**, hạn chế token đa audience nếu không có lý do kiến trúc rõ ràng. Một token đa audience có thể hợp lệ khi AS cấp có chủ đích và từng RS chấp nhận theo policy, nhưng mở rộng nơi token bị lộ có thể sử dụng.

Không để một worker chỉ làm đối soát giữ token với `scope=payments:refund reports:export admin` “cho tiện”; điều này tăng thiệt hại nếu credential/token bị chiếm.

## 7. Authorization Server phải áp dụng chính sách gì?

Việc Client tự xác thực thành công **không đủ** để AS cấp token bất kỳ. Xác thực client chỉ trả lời **“ứng dụng nào đang yêu cầu?”**, còn authorization policy trả lời **“ứng dụng được phép làm gì và ở đâu?”**.

### Quyết định minh họa

~~~text
authenticated_client = billing-worker
grant_type           = client_credentials
requested_resource   = billing-api
requested_scopes     = {billing:read, payments:refund}

client_allowed       = {billing:read}
resource_supported   = {billing:read, payments:refund}
tenant_policy        = {billing:read}
service_entitlement  = {billing:read}

=> Có thể cấp billing:read nếu policy cho phép partial grant;
   hoặc từ chối toàn bộ yêu cầu theo chính sách AS.
=> KHÔNG tự cấp payments:refund.
~~~

Phép giao các tập quyền chỉ là **cách trực quan hóa**. Chính sách thực tế còn xét trạng thái client, tenant, loại dữ liệu, điều kiện thời gian, sự phê duyệt cấp tổ chức, loại credential và mức độ bảo đảm.

### Mã giả phía AS

~~~text
issueClientCredentialsToken(request):
    client = authenticateConfidentialClient(request)
    if not client:
        deny invalid_client

    if "client_credentials" not in client.allowedGrants:
        deny unauthorized_client

    requestedResource = parseResourceIndicatorIfSupported(request)
    resource = resolveTrustedAudience(requestedResource, client)
    if resource not allowedFor client:
        deny invalid_target_or_policy_error

    requestedScopes = parseScope(request.scope)
    decision = issuePolicy.evaluate(
        client, resource, requestedScopes, tenantEntitlement, risk
    )
    if decision.deny or decision.grantedScopes empty:
        deny accordingToOAuthProfile

    return newAccessToken(
        issuer=configuredIssuer,
        principal=servicePrincipalFor(client),
        clientId=client.id,
        audience=configuredAudience(resource),
        scope=decision.grantedScopes,
        expiresIn=decision.accessTokenTtl,
        senderBinding=decision.bindingIfRequired
    )
~~~

Đây là **pseudocode giảng giải, không phải triển khai OAuth đầy đủ**. Tên `invalid_target` đến từ ngữ cảnh Resource Indicators khi AS áp dụng RFC 8707; hệ thống cần chọn mã lỗi đúng đặc tả/profile đang hỗ trợ.

AS không được tạo một token có quyền vượt mức chỉ vì client đã gửi `scope=admin` trong form. Khi nguồn policy/entitlement không thể xác minh, nguyên tắc an toàn là **không tự cấp quyền mặc định**.

## 8. Resource Server xác minh access token thế nào?

Billing API chỉ nên tiếp nhận access token **đúng issuer, audience, loại token, trạng thái và phạm vi được cấp**.

~~~mermaid
flowchart TD
    A["Billing Worker gửi access token"] --> B{"Đúng dạng và token được chấp nhận?"}
    B -- Không --> E1["401 / Từ chối token"]
    B -- Có --> C{"Xác minh nguồn issuer và toàn vẹn/trạng thái?"}
    C -- Không --> E1
    C -- Có --> D{"aud có billing-api, exp/nbf đúng, đúng access token?"}
    D -- Không --> E1
    D -- Có --> S{"Sender proof hợp lệ nếu yêu cầu?"}
    S -- Không --> E1
    S -- Có --> F{"scope đủ cho action?"}
    F -- Không --> E2["403 / Thiếu quyền"]
    F -- Có --> G{"Service được phép trên tenant, invoice và trạng thái?"}
    G -- Không --> E2
    G -- Có --> OK["Thực hiện action trong giới hạn"]
~~~

### JWT access token

RS dùng thư viện JOSE/JWT đáng tin để:

1. Chỉ tin **issuer** đã cấu hình; dùng đúng JWKS/khóa và thuật toán được cho phép, kiểm tra signature/MAC.
2. Kiểm tra **`aud`** khớp định danh API, không so chuỗi con.
3. Kiểm tra `exp`, `nbf` và yêu cầu profile; không chấp nhận OIDC ID token chỉ vì có chữ ký hợp lệ.
4. Kiểm tra trạng thái/thu hồi/loại token và proof-of-possession nếu chính sách đòi hỏi.
5. Chỉ sau đó mới lấy `client_id`, `sub`, `scope` và thông tin tenant từ nguồn đã được AS/RS chấp thuận để phân quyền.

**Decode Base64URL của JWT không phải verify chữ ký.** Không tạo service authority từ claims chưa xác minh.

### Opaque access token

RS dùng **introspection** hoặc nguồn tra cứu trạng thái đã được xác thực. Xác thực kênh và bên trả lời, rồi kiểm tra `active`, audience, scope, principal và metadata bắt buộc. Introspection cache có thể làm chậm hiệu lực thu hồi; TTL cache cần phù hợp mức rủi ro.

### Phân quyền theo đối tượng vẫn cần

Ví dụ token xác thực:

~~~text
client_id = billing-worker
aud       = billing-api
scope     = billing:read
allowed_tenant = tenant-a  (chỉ khi đã được xác minh theo policy)
~~~

Trong khi invoice:

~~~text
invoice_id = inv-999
tenant_id  = tenant-b
status     = CONFIDENTIAL
~~~

Billing API **phải từ chối** khi service không có quyền liên tenant cụ thể. Có `billing:read` không tự cho phép đọc mọi invoice; `client_id` hợp lệ không bỏ qua tenant, owner và độ nhạy cảm của dữ liệu.

## 9. Java/Spring Security: gọi token endpoint và API an toàn

Với Spring Security, một **confidential service** có thể dùng **OAuth2 Client** hỗ trợ grant `client_credentials` thay vì tự tạo JSON, mã hóa Basic header và quản lý token thủ công.

### Cấu hình client registration minh họa

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing-service:
            provider: company-auth
            client-id: billing-worker
            client-secret: "<INJECT_FROM_SECRET_MANAGER>"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - billing:read
        provider:
          company-auth:
            token-uri: https://auth.example.test/token
~~~

**Bảo mật cấu hình:** `<INJECT_FROM_SECRET_MANAGER>` chỉ là placeholder. Không commit client secret thật vào source control; nên sử dụng secret manager/credential injection có kiểm soát. Ví dụ dùng `client_secret_basic` để dễ giảng giải, không ngụ ý luôn tốt hơn private-key JWT hoặc mTLS.

`resource` theo RFC 8707 **không được bảo đảm tự động truyền** chỉ bằng cấu hình trên. Nếu AS yêu cầu resource indicator hoặc một tham số profile riêng, phải cấu hình **token request customization được Spring/provider hỗ trợ**, không tự suy token có đúng audience.

### AuthorizedClientManager cho backend không có user

Khi chạy batch hoặc service backend, `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp để quản lý authorized client **không phụ thuộc HTTP servlet request**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
class ServiceOAuthClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Manager có thể **sử dụng lại access token còn hiệu lực và lấy token mới khi cần** theo cách Spring Security quản lý authorized client. Cơ chế lưu token, độ lệch thời gian, bảo mật kho lưu, concurrency và phương thức cache phải phù hợp với môi trường triển khai.

### Client service gọi Billing API

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class BillingApiCaller {
    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final RestClient http = RestClient.create();

    BillingApiCaller(OAuth2AuthorizedClientManager authorizedClientManager) {
        this.authorizedClientManager = authorizedClientManager;
    }

    String readInvoices() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("billing-service")
                .principal("billing-worker-service")
                .build();

        OAuth2AuthorizedClient client = authorizedClientManager.authorize(request);
        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException("Unable to obtain service access token");
        }

        String tokenValue = client.getAccessToken().getTokenValue();
        return http.get()
                .uri("https://api.example.test/invoices")
                .headers(headers -> headers.setBearerAuth(tokenValue))
                .retrieve()
                .body(String.class);
    }
}
~~~

Ví dụ sử dụng các API Spring hiện đại; nó **không phải ứng dụng đầy đủ có thể chạy độc lập** nếu chưa thêm dependency và cấu hình Spring Boot phù hợp. Chuỗi `principal("billing-worker-service")` ở đây là **khóa định danh cho authorized-client management**, **không biến grant thành token của người dùng** và không có quyền tự đặt claim `sub` ở AS.

Khi triển khai thật, cần:

- Cấu hình HTTP client timeout, TLS, giới hạn retry và cách xử lý 401/403 từ API.
- Không log giá trị `tokenValue`; không chuyển nó cho UI/browser.
- Kiểm tra token được cấp **đúng audience**, scope và kiểu token; ví dụ trên giả sử AS trả **Bearer token**.
- Nếu AS bắt buộc DPoP hoặc certificate-bound token, thay cách gắn Bearer header và cấu hình sender proof/TLS theo profile; **không dùng ví dụ bearer này nguyên xi**.
- Tránh gửi cùng token sang nhiều API chỉ vì dùng chung OAuth client registration.

### Resource Server với Spring Security

Billing API có thể áp dụng method security sau khi middleware đã xác minh access token:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class InvoiceReadService {

    @PreAuthorize("hasAuthority('SCOPE_billing:read')")
    public InvoiceDto readInvoice(String invoiceId) {
        // Phải kiểm tra principal dịch vụ, tenant và invoice cụ thể
        // ở policy/service/repository trước khi trả dữ liệu.
        return loadAuthorizedInvoice(invoiceId);
    }
}
~~~

Với converter JWT mặc định thông dụng, Spring Security map OAuth scope thành authority có tiền tố `SCOPE_`. **`hasRole("billing:read")` không tương đương** với `hasAuthority("SCOPE_billing:read")`. Phải cấu hình và xác minh **audience validator riêng cho Billing API**; chỉ cấu hình `issuer-uri` không nên được coi là tự bảo đảm audience chính xác.

## 10. Caching, hạn dùng và xin access token mới

Client Credentials không đòi một round trip tới AS **cho mỗi API call** nếu access token đã cấp còn hợp lệ và chính sách cho phép tái sử dụng.

### Vòng đời điển hình

~~~mermaid
flowchart TD
    A["Cần gọi Billing API"] --> B{"Có access token được cache cho đúng audience/scope/key?"}
    B -- Không --> C["Xác thực client và xin token tại AS"]
    B -- Có --> D{"Token còn hạn đủ cho request?"}
    D -- Không --> C
    D -- Có --> E["Dùng token đã xác minh metadata"]
    C --> F{"AS cấp token hợp lệ?"}
    F -- Không --> X["Xử lý lỗi an toàn, không dùng token cũ quá hạn"]
    F -- Có --> G["Lưu token trong cache bảo vệ đúng phạm vi"]
    G --> E
    E --> H["Gọi API qua TLS với token phù hợp"]
    H --> I{"Kết quả"}
    I -- 401 --> J["Đánh giá token, thu hồi, cấu hình và retry có giới hạn"]
    I -- 403 --> K["Thiếu quyền/policy, không xin scope rộng tự động"]
    I -- 2xx --> L["Hoàn tất xử lý"]
~~~

### Không cache chỉ theo `client_id`

Nếu cùng một client có quyền xin token cho nhiều RS/scope, cache token phải phân biệt **audience/resource, scope, token type/binding và các ràng buộc khác**. Một cache chỉ có key `billing-worker` có thể trả nhầm token `aud=orders-api` khi worker cần Billing.

Ví dụ khóa cache ở mức khái niệm:

~~~text
cache_key = (
    configured_issuer,
    client_registration_id,
    resource_or_audience,
    granted_scope_set,
    sender_key_or_certificate_binding_if_any
)
~~~

Không phải mọi thư viện dùng đúng cấu trúc này; cần hiểu **cách cache thực tế** của thư viện đang dùng. Nếu token chỉ được cấp theo một registration cố định, thư viện có thể quản lý đủ bằng registration/principal; khi mở rộng nhiều audience, phải kiểm tra cấu hình không xảy ra token substitution.

### Làm mới sớm một khoảng nhỏ

`expires_in=600` không có nghĩa nên chờ đến đúng giây thứ 600 rồi mới xin token mới. Tránh race giữa **thời điểm kiểm tra ở client** và **thời điểm RS xác minh**. Thư viện thường hỗ trợ độ lệch hết hạn hoặc cơ chế tương đương.

### Tránh token request storm

Khi 100 worker thread cùng thấy token sắp hết hạn, không nên đồng loạt gọi AS bằng cùng credential:

- Dùng cache/thread coordination và single-flight nếu cần.
- Có backoff hợp lý cho 429/503 hoặc lỗi AS tạm thời.
- Giới hạn retry và áp dụng timeout/circuit breaker phù hợp.
- Không tự fallback sang một token hết hạn, issuer khác, scope rộng hơn hoặc bypass authorization để duy trì chức năng.

### 401 khác 403

Một **401 từ RS** có thể do token hết hạn, bị thu hồi, sai issuer/audience hoặc lỗi proof. Client có thể đánh giá và xin token mới **một cách có giới hạn** nếu nguyên nhân hợp lý; xin lại mãi mãi không chữa được sai audience.

Một **403** thường biểu thị token hợp lệ nhưng thiếu scope/permission hoặc không có quyền trên tài nguyên. Không thử xin token `admin` hoặc tăng scope tự động chỉ để “sửa” 403.

## 11. Bảo vệ client credential và access token

### Hai credential khác nhau

1. **Client credential** (secret/private key/certificate): dùng để xác thực client với AS.
2. **Access token**: AS phát hành để client trình cho RS trong một khoảng thời gian và phạm vi quyền cụ thể.

Lộ client secret/khóa có thể cho attacker **xin access token mới liên tục** trong quyền của client, nghiêm trọng hơn việc chỉ lộ một access token ngắn hạn. Cần quản lý hai vòng đời khác nhau.

| Đối tượng | Rủi ro | Biện pháp phù hợp |
|---|---|---|
| **Client secret** | Bị lộ qua source, CI/CD, config, log. | Secret manager, least privilege, rotation, hạn chế đọc/hiển thị secret. |
| **Private key `private_key_jwt`** | Key bị xuất hoặc bị sử dụng trái phép. | Keystore/HSM khi phù hợp, kiểm soát quyền ký, key rotation và xác minh assertion. |
| **mTLS certificate/key** | Cert/key bị lộ, sai cấu hình TLS/proxy. | Bảo vệ key, xác thực TLS, luân chuyển cert, trust boundary rõ. |
| **Access token** | Bị sao chép từ log/trace/cache. | TLS, no-store logs, TTL, audience/scope hẹp, thu hồi, sender proof nếu cần. |
| **Cache token** | Dùng nhầm audience, lộ qua memory dump hoặc backup. | Khóa cache đúng ngữ cảnh, bảo vệ memory/store, hạn mức lưu và xóa khi thu hồi. |

### HTTPS là bắt buộc cho credential

Không gửi client secret, client assertion hoặc access token qua HTTP không an toàn. Cần xác minh TLS certificate của AS và RS; không tắt certificate verification khi gặp lỗi môi trường.

Nếu reverse proxy hoặc service mesh kết thúc TLS, kiểm tra **toàn bộ đường đi** của credential và forwarded headers. Đừng cho backend tin metadata xác thực do caller Internet có thể giả mạo.

### Đừng dùng Bearer token khi có thể bị đánh cắp mà không đánh giá rủi ro

Bearer access token còn hạn có thể được trình lại bởi người sở hữu bản sao. Việc AS xác thực client lúc cấp token **không chứng minh người đang gọi RS sau đó vẫn là client đó**.

Đối với workload nhạy cảm, AS/RS có thể hỗ trợ **sender-constrained access token**:

- **DPoP (RFC 9449):** client ký proof cho request bằng private key; token ràng buộc với JWK thumbprint `cnf.jkt`. RS xác minh proof, `htm`, `htu`, `iat`, `jti`, `ath` và nonce khi cần.
- **mTLS certificate-bound token (RFC 8705):** AS ràng buộc token với client certificate thumbprint `cnf["x5t#S256"]`; RS kiểm tra certificate thật của kết nối TLS có khớp không.

**Client authentication bằng mTLS ở AS không tự bảo đảm token đã certificate-bound khi gọi RS.** Phải có ràng buộc khi cấp token **và** enforcement ở nơi nhận. Sender constraint giảm rủi ro khi attacker chỉ lấy được token, nhưng không tự ngăn attacker đã kiểm soát khóa hoặc máy đang chạy service.

## 12. Multi-tenant và nguy cơ confused deputy

**Confused deputy** xảy ra khi một service có quyền mạnh thực hiện hành động cho một caller không có quyền thực hiện hành động đó, vì service không kiểm tra đúng quan hệ người gọi–tài nguyên–quyền.

### Kịch bản cần tránh

~~~text
Billing Worker có service token:
  aud   = billing-api
  scope = billing:read
  service is allowed for tenant-a

Một caller ở tenant-b truyền:
  GET /billing-proxy?tenant=tenant-a&invoice=inv-001

Nếu Billing Proxy dùng quyền service để đọc inv-001
và trả dữ liệu ngay cho caller tenant-b:
  => lộ dữ liệu do confused deputy.
~~~

Ngay cả khi token service và TLS đều hợp lệ, endpoint trung gian **phải xác minh quyền caller** và quan hệ caller với tenant/invoice trước khi dùng quyền service cho request.

### Ba mô hình cần phân biệt

| Nghiệp vụ | Token nên thể hiện | Điều kiện bảo mật |
|---|---|---|
| **Job nội bộ tự làm việc** | Service principal với scope/tenant phù hợp. | AS/RS kiểm tra quyền service và đối tượng. |
| **Service được user gọi yêu cầu truy cập dữ liệu user** | Delegated user token hoặc cơ chế on-behalf-of/token exchange nếu được AS hỗ trợ, **hoặc** service kiểm soát cả caller và dữ liệu trước khi dùng token service. | Không dựa chỉ vào quyền service để bỏ qua quyền user. |
| **Service A gọi Service B vì chức năng nội bộ** | Token cho audience của B với quyền service A được cấp. | Không forward token `aud=A` sang B; phải xác minh B audience/scope/policy. |

**Token Exchange (RFC 8693)** có thể cấp token downstream đúng audience, scope và ngữ cảnh subject/actor khi AS hỗ trợ. **Đó là một grant/giao dịch khác**, không phải thao tác tự sửa claim `sub` hoặc `aud` của token Client Credentials.

### Tenant nằm trong request không phải bằng chứng quyền

Header `X-Tenant-Id` hoặc query `tenant_id=tenant-a` là **đầu vào do caller có thể thao túng**. Nếu dùng chúng để chọn dữ liệu, RS phải kiểm tra giá trị ấy có được **gắn với service principal và quyền hiện hành** không.

Một service có `billing:read` ở tenant A không đương nhiên được đọc tenant B. Một service được tổ chức cấp quyền cross-tenant cần chính sách cụ thể, phạm vi và audit phù hợp; không nên dùng role `SYSTEM_ADMIN` toàn cục làm mặc định.

## 13. Java: chính sách dữ liệu sau khi token đã được xác minh

Đoạn mã dưới đây chỉ minh họa **quyền nghiệp vụ**. `VerifiedServiceAccess` phải được dựng bởi middleware sau khi RS kiểm tra issuer, chữ ký/introspection, audience, thời hạn, token type và sender proof khi cần.

~~~java
import java.util.Objects;
import java.util.Set;

record VerifiedServiceAccess(
    String clientId,
    Set<String> audiences,
    Set<String> grantedScopes,
    Set<String> entitledTenants,
    boolean active
) {}

record Invoice(String id, String tenantId, boolean confidential) {}

final class BillingAuthorizationPolicy {
    static boolean canRead(
            VerifiedServiceAccess token,
            Invoice invoice) {
        if (token == null || invoice == null || !token.active()) {
            return false;
        }
        if (!Objects.equals("billing-worker", token.clientId())) {
            return false;
        }
        if (token.audiences() == null
                || !token.audiences().contains("billing-api")) {
            return false;
        }
        if (token.grantedScopes() == null
                || !token.grantedScopes().contains("billing:read")) {
            return false;
        }
        if (invoice.tenantId() == null
                || token.entitledTenants() == null
                || !token.entitledTenants().contains(invoice.tenantId())) {
            return false;
        }
        // Hóa đơn confidential cần một quyền khác trong policy minh họa.
        return !invoice.confidential();
    }
}
~~~

Điều kiện `!invoice.confidential()` chỉ là **policy của ví dụ**; thực tế có thể có permission riêng hoặc đánh giá classification dữ liệu. **Entitled tenants phải đến từ nguồn tin cậy và còn phù hợp chính sách**, không phải tập được tạo từ header do caller tự gửi.

### Vì sao vẫn phải kiểm tra dữ liệu ở RS?

Access token do AS cấp có thể chứa scope và client ID, nhưng **AS không nhất thiết biết invoice mới tạo thuộc tenant nào hoặc trạng thái hiện tại ra sao**. Những thuộc tính ấy do Billing API hoặc hệ thống dữ liệu đáng tin kiểm soát. RS phải xác minh ngay khi xử lý request, đặc biệt khi quyền hoặc trạng thái bản ghi thay đổi.

## 14. Lỗi giao thức và cách phản ứng

### Lỗi tại Authorization Server

| Trường hợp | Mã lỗi OAuth thường gặp | Hướng xử lý |
|---|---|---|
| Client secret/assertion không hợp lệ | `invalid_client` | Không fallback sang anonymous/bearer; kiểm tra credential/rotation. |
| Client chưa được phép dùng grant này | `unauthorized_client` | Sửa registration/policy qua quản trị, không tự đổi grant. |
| `grant_type` không được AS hỗ trợ | `unsupported_grant_type` | Kiểm tra khả năng/profile AS. |
| Scope yêu cầu không hợp lệ hoặc không được phép | `invalid_scope` | Không tăng scope bừa bãi; cập nhật hợp đồng quyền. |
| Resource indicator không hợp lệ hoặc không được phép | `invalid_target` khi dùng RFC 8707 | Kiểm tra resource/audience được đăng ký. |
| AS tạm thời không sẵn sàng hoặc giới hạn tốc độ | Có thể là HTTP 429/5xx theo triển khai | Retry có backoff và hạn mức, không dùng token không hợp lệ. |

Ví dụ phản hồi lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_scope",
  "error_description": "Requested scope is not permitted for this client"
}
~~~

`invalid_client` có quy tắc HTTP status/header riêng tùy phương thức client authentication theo RFC 6749; đừng cố định mọi lỗi token endpoint thành HTTP 400. **Không trả client secret, private key, access token hoặc policy nhạy cảm trong error description**.

### Lỗi tại Resource Server

| Trường hợp | HTTP thường dùng | Ghi chú |
|---|---|---|
| Không có token, token sai issuer/signature, hết hạn, bị thu hồi hoặc sai audience | **401 Unauthorized** | Có thể dùng `WWW-Authenticate: Bearer` và `invalid_token` phù hợp. |
| Token hợp lệ nhưng thiếu scope/action | **403 Forbidden** | Có thể phản hồi `insufficient_scope` theo RFC 6750. |
| Token hợp lệ, scope đủ nhưng không được phép trên invoice/tenant | **403** hoặc **404** | Có thể dùng 404 để giảm lộ sự tồn tại tài nguyên. |
| Không thể xác minh token vì AS/JWKS/introspection lỗi | **Không cấp quyền** | Có thể trả lỗi tạm thời phù hợp, không fail-open. |

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="billing", error="insufficient_scope", scope="billing:read"
~~~

Client gặp **403** không nên tự thử Client Credentials với một client ID có quyền rộng hơn. Một thay đổi quyền cần có phê duyệt/policy hợp lệ, không phải chiến thuật retry.

## 15. Audit, vận hành và ứng phó sự cố

### Những gì nên có trong audit

- **Client identity đã xác minh**: client ID, registration/policy version.
- **Token issuer/audience** và grant type, theo metadata tin cậy.
- **Action/Resource Server/tenant** cùng kết quả cho phép/từ chối.
- **Reason code**: sai audience, thiếu scope, client không được phép, resource không thuộc tenant, token đã thu hồi.
- **Thời điểm và correlation ID** theo chính sách logging, không phơi định danh nhạy cảm quá mức.

Không ghi **nguyên client secret, access token, private key, refresh token, Authorization header** hoặc session cookie vào log, trace, exception, ticket hỗ trợ.

### Khi secret bị lộ

1. Xác định client/secret bị ảnh hưởng, vô hiệu hóa hoặc **rotate credential** theo quy trình.
2. Kiểm tra các token/grant liên quan, đánh giá phạm vi bị dùng trái phép.
3. Thu hồi access token hoặc giảm TTL/áp dụng trạng thái theo khả năng AS/RS; **token JWT còn hạn có thể vẫn được chấp nhận nếu RS chỉ verify chữ ký và thời gian**.
4. Rà soát log hành vi, tenant, dữ liệu bị truy cập và các hệ thống dùng credential cũ.
5. Cập nhật kho secret/CI/CD, quyền đọc secret, cảnh báo và kế hoạch thay thế credential.

### Không sử dụng user credential làm đường tắt

Không cất mật khẩu người dùng để worker đăng nhập mỗi giờ nhằm xin token; Client Credentials giải quyết một nhu cầu **machine-to-machine được ủy quyền trước**. Nếu nghiệp vụ thực sự cần hành động theo quyền user, phải dùng một mô hình **delegation** phù hợp, không tự biến service principal thành user.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Client Credentials là user login không cần trình duyệt.” | Không có user delegation trong grant này. | Đây là app/service authorization. |
| “`client_id` là secret nên chỉ cần gửi client_id.” | Client ID là định danh công khai. | Confidential client phải xác thực theo method đăng ký. |
| “SPA có thể dùng Client Credentials nếu giấu secret bằng minify.” | Mã browser có thể bị xem/giải mã. | Không phát credential service cho public frontend. |
| “Client authentication thành công nghĩa là được mọi scope.” | Xác thực client khác policy cấp quyền. | AS kiểm tra resource/scope/tenant/entitlement. |
| “Một service token có `sub` nên `sub` là user ID.” | Service principal có thể là subject của token. | Diễn giải theo grant và token profile. |
| “Có `billing:read` là xem mọi hóa đơn.” | Scope không thay object authorization. | RS kiểm tra tenant/owner/classification. |
| “Refresh token bắt buộc phải cấp với Client Credentials.” | RFC 6749 quy định SHOULD NOT. | Thường xin access token mới bằng client credential. |
| “Access token cần luôn luôn là JWT.” | OAuth không bắt buộc token dạng JWT. | Hỗ trợ JWT hoặc opaque theo AS/RS. |
| “Client secret chứng minh holder của bearer token tại API.” | Client auth chỉ diễn ra với AS khi xin token. | Dùng sender proof nếu cần ràng buộc holder. |
| “Token Billing được forwarding sang Orders vì cùng AS.” | Sai audience. | Xin token đúng API và scope. |
| “Service có quyền gọi Billing nên được trả dữ liệu cho mọi user.” | Confused deputy/cross-tenant leakage. | Kiểm tra quyền caller và dữ liệu trước khi ủy nhiệm. |
| “Token chưa hết hạn thì permission chưa đổi.” | Policy/tenant/secret có thể đã bị thu hồi. | TTL, revocation, kiểm tra quyền hiện hành. |
| “401/403 đều chỉ cần xin token mới.” | Thiếu scope/permission không sửa bằng refresh. | Phân loại lỗi và xử lý policy đúng. |
| “Để tăng tốc, khi AS lỗi thì tạm bỏ xác minh token.” | Fail-open tạo lỗ hổng truy cập. | Fail closed; xử lý sự cố availability riêng. |

## 17. Ma trận kiểm thử Client Credentials flow

Giả sử `billing-worker` là confidential client, được AS cho phép `client_credentials`, audience `billing-api`, scope `billing:read` và quyền trên tenant A. Billing API yêu cầu access token còn hiệu lực và permission theo invoice.

| Tình huống | Kỳ vọng | Lý do |
|---|---|---|
| Client xác thực đúng, xin `billing:read` cho Billing | **Có thể cấp token**. | Registration và policy phù hợp. |
| Client không có credential hợp lệ | **AS từ chối**, thường `invalid_client`. | Không xác thực được client. |
| Client public SPA gửi secret nhúng trong bundle | **Không được coi là confidential**. | Secret có thể bị trích xuất. |
| Client không được phép dùng `client_credentials` | **AS từ chối**. | Grant không thuộc policy đăng ký. |
| Billing Worker xin `payments:refund` | **Không tự cấp**. | Vượt allowed scopes. |
| Billing Worker xin token cho Orders API | **Từ chối hoặc không cấp đích đó**. | Resource/audience không được phép. |
| Client Credentials request có `username=user-123` tự khai | **Không đổi principal thành user đó**. | Không có end-user delegation. |
| AS cấp token Bearer `aud=billing-api`, `scope=billing:read` | **Billing có thể xem xét** sau xác minh. | Đúng nơi nhận và action được cấp. |
| Cùng token gửi Orders API | **Orders từ chối**. | Sai audience. |
| Token có chữ ký đúng nhưng hết hạn | **RS từ chối**. | Thời hạn token không hợp lệ. |
| Token có `scope=billing:read` nhưng yêu cầu refund | **RS từ chối**, thường 403. | Thiếu scope/action. |
| Service đúng scope nhưng đọc invoice tenant B | **RS từ chối**. | Không có tenant entitlement. |
| Token opaque introspection `active=false` | **RS từ chối**. | Token không còn hoạt động. |
| Opaque `active=true` nhưng thiếu audience bắt buộc | **RS từ chối**. | Không chứng minh token dành cho Billing. |
| JWT có claim `client_id` do caller decode mà chưa verify chữ ký | **Không tin claim**. | Claims chưa được xác minh. |
| Access token bị sao chép nhưng còn hạn, Bearer thuần | **Có nguy cơ dùng lại**. | Không có sender proof. |
| Token DPoP-bound nhưng request không có proof hoặc sai khóa | **RS từ chối**. | Sender constraint bắt buộc. |
| Secret bị rotate, worker dùng secret cũ | **AS từ chối theo trạng thái credential**. | Credential đã hết hiệu lực. |
| Worker cache token Orders rồi dùng cho Billing | **Billing từ chối**; phát hiện sai cache key. | Audience không khớp. |
| AS tạm lỗi 503, nhiều worker gọi token endpoint đồng loạt | **Giới hạn retry/backoff**, không fail-open. | Tránh request storm và bypass. |
| Billing Worker trả invoice tenant A cho caller tenant B | **Từ chối ở API trung gian/RS**. | Chặn confused deputy. |
| Token hợp lệ nhưng policy service bị thu hồi | **Từ chối theo cơ chế trạng thái/quyền hiện hành**. | Chữ ký không thay policy. |

Kiểm thử cần bao gồm **token endpoint và Resource Server**, phân biệt **401/403**, lỗi network, rotation secret, expiry/skew, nhiều audience, scope gần giống, multi-tenant, sender proof và hành vi khi cache token hoạt động. Một unit test chỉ xác nhận “request có header Bearer” **chưa chứng minh hệ thống OAuth an toàn**.

## 18. Tình huống tự luyện

**Tình huống A — Worker không có user.** Một cron job phải đọc báo cáo mỗi đêm mà không có nhân viên đăng nhập. Client Credentials có phù hợp không?

**Giải thích:** Có thể, nếu cron job là confidential client được AS đăng ký/ủy quyền trước và Reports API hỗ trợ service principal với scope/audience phù hợp. **Không** tự cho nó quyền xem mọi dữ liệu chỉ vì là job nội bộ.

**Tình huống B — SPA muốn dùng service secret.** Frontend JavaScript giữ client secret trong bundle để xin token `client_credentials`. Có nên làm không?

**Giải thích:** Không. Frontend công khai không bảo vệ secret như confidential client; kẻ khác có thể dùng nó xin token service. Hãy đặt quyền service ở backend/BFF nếu nghiệp vụ phù hợp, hoặc dùng luồng có người dùng như Authorization Code + PKCE.

**Tình huống C — Nhầm service principal với user.** Token service có `sub=billing-worker`. Billing API tra `sub` như customer ID rồi trả hóa đơn. Sai chỗ nào?

**Giải thích:** `sub` trong ngữ cảnh grant này thường mô tả principal của service theo profile, không phải customer. API phải phân quyền dựa trên service entitlement và bản ghi thật, không dùng `sub` làm user ID.

**Tình huống D — Scope quá rộng.** AS được yêu cầu `billing:read payments:refund`, còn client chỉ được `billing:read`. AS có thể cấp cả hai vì secret đúng?

**Giải thích:** Không. Client authentication chỉ chứng minh danh tính. AS phải từ chối hoặc cấp phạm vi hợp lệ theo policy, không vượt giới hạn.

**Tình huống E — Nhầm audience.** Orders Service dùng token `aud=orders-api` để gọi Billing. Cả hai API tin cùng AS. Billing có nhận?

**Giải thích:** Không. Billing phải kiểm tra audience của chính mình. Orders cần token được AS phát cho Billing theo mô hình client credentials/token exchange/delegation được cho phép.

**Tình huống F — Có service token nhưng caller không có quyền.** API trung gian có token Billing quyền đọc hóa đơn tenant A. Một caller tenant B yêu cầu API trung gian trả hóa đơn tenant A. Nên xử lý ra sao?

**Giải thích:** Từ chối nếu caller không được phép. Quyền service không tự tạo quyền tiết lộ dữ liệu cho caller; đây là nguy cơ confused deputy.

**Tình huống G — Không thấy refresh token.** AS trả `access_token` và `expires_in` nhưng không có `refresh_token`. Có phải lỗi?

**Giải thích:** Không. Với Client Credentials, RFC 6749 nói refresh token **SHOULD NOT** được cấp. Client thường dùng credential của chính nó để xin access token mới khi cần.

**Tình huống H — Lộ access token.** Attacker lấy được bearer access token còn hạn trong log nhưng không biết client secret. Họ có dùng được ở Billing API không?

**Giải thích:** Có thể, trong giới hạn audience/scope nếu không có sender-constraining/thu hồi. Client secret chỉ dùng để xác thực ở AS; bearer token bị lộ có thể bị phát lại ở RS.

**Tình huống I — Lộ secret.** Attacker lấy được client secret của Billing Worker, nhưng chưa có access token. Vì sao sự cố này vẫn nghiêm trọng?

**Giải thích:** Attacker có thể thử **xin access token mới** cho đến khi credential bị vô hiệu hóa, trong giới hạn quyền client. Cần rotate/revoke credential, rà soát token đã phát hành và sự kiện truy cập.

**Tình huống J — 403 lặp lại.** Worker được cấp `billing:read` và API từ chối hoàn tiền 403. Worker xin token lại 50 lần. Điều gì sai?

**Giải thích:** Quyền đọc không đủ để hoàn tiền. Cần luồng cấp quyền hợp lệ và policy cho thao tác refund; retry không tự tạo permission.

## Checklist triển khai Client Credentials flow

1. **Chọn đúng grant:** Client Credentials cho workload/app-only đã được ủy quyền trước; không giả lập người dùng hay dùng client secret trong frontend.
2. **Đăng ký confidential client:** client ID, phương thức client authentication, grant types, resource/audience, scope tối đa và tenant entitlement.
3. **Bảo vệ credential:** secret manager/private key/certificate, TLS, rotation, quyền đọc/sử dụng tối thiểu, không ghi secret vào log.
4. **Xin token đúng giao thức:** `POST` token endpoint qua HTTPS, `grant_type=client_credentials`, client authentication hợp lệ, scope/resource chính xác.
5. **AS cấp quyền theo policy:** không tự copy requested scope/audience; tách client authentication khỏi quyết định authorization.
6. **Hiểu token response:** `access_token`, `token_type`, `expires_in`, `scope` nếu cần; không trông chờ refresh token mặc định.
7. **RS xác minh token:** issuer, chữ ký/introspection, audience, time, loại token, trạng thái, sender proof khi bắt buộc.
8. **RS phân quyền service:** scope đúng action, principal service, tenant/resource/owner/classification, tránh confused deputy.
9. **Cache và hết hạn có kiểm soát:** token cache theo audience/resource/scope/binding; refresh sớm một khoảng, tránh token request storm.
10. **Xử lý lỗi đúng:** phân biệt invalid_client/unauthorized_client/invalid_scope/invalid_target, 401/403, retry/backoff giới hạn.
11. **Giảm replay:** TLS, TTL ngắn, scope/audience hẹp, bảo vệ access token và cân nhắc DPoP/mTLS-bound token khi rủi ro cao.
12. **Audit an toàn:** client/grant/action/tenant/decision reason; lọc token, credentials, HTTP Authorization và thông tin nhạy cảm.
13. **Kiểm thử phủ định:** public client, grant sai, scope rộng, audience sai, expired/revoked, multi-tenant, credential rotation, token substitution và attacker có bản sao token.

## Ghi nhớ

**Client Credentials flow** cho phép **confidential client** xin access token **dựa trên quyền của chính ứng dụng/dịch vụ**, không phải bằng quyền của một end-user vừa đăng nhập. Client tự xác thực ở **token endpoint**, AS kiểm tra **grant/resource/scope/policy** rồi phát token đúng phạm vi; Resource Server vẫn xác minh **issuer, audience, thời hạn, scope, trạng thái và quyền trên từng tài nguyên**. `client_id` là định danh, không phải secret; **client authentication không đồng nghĩa authorization**, và service token **không tự cho phép hành động thay một user**. Luồng này thông thường **không cần refresh token**; cần quản lý client credential, access token, cache, rotation, thu hồi và biện pháp chống replay tương xứng rủi ro.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework (mục 4.4, Client Credentials)](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
