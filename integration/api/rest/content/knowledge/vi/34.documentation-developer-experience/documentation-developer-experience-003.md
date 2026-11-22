# Mô tả xác thực, phân quyền và môi trường thử nghiệm

Một đối tác đọc tài liệu **POST /v1/orders**, lấy được access token và gửi JSON đúng schema, nhưng API trả **403 Forbidden**. Đối tác không biết token thiếu scope, tài khoản không thuộc tenant hay đơn hàng đang ở trạng thái cấm sửa. Khi thử lại trên sandbox, token của production bị từ chối; đến lúc tích hợp thành công thì request vô tình gọi dịch vụ thanh toán thật. Đây là lỗi **trải nghiệm phát triển (developer experience)** và **hợp đồng bảo mật** không rõ ràng, không chỉ là lỗi authentication.

Bài thuộc chương **Tài liệu và trải nghiệm** của module **INTEGRATION_API_REST**. Chúng ta xây tài liệu giúp lập trình viên **tự xác thực, hiểu ranh giới quyền, sử dụng sandbox và kiểm thử được hợp đồng HTTP** trước khi phát hành. Ví dụ dựa trên REST resource/URI/method/status, OpenAPI 3.1, OAuth2/OIDC, Java/Spring Security, xử lý lỗi, idempotency và kiểm thử tích hợp.

## 1. Mục tiêu và tiêu chuẩn của tài liệu có thể thực thi

Sau bài này, bạn có thể:

1. Phân biệt **authentication (AuthN)**, **authorization (AuthZ)**, **OAuth2 scope**, **role**, quyền trên từng **resource** và **tenant isolation**.
2. Mô tả rõ **credential type, nơi lấy token, issuer, audience, expiry, scope, quy tắc gửi HTTP** cho từng client.
3. Biểu diễn chính sách bảo mật trong **OpenAPI securitySchemes/security** và phần mô tả nghiệp vụ không thể thể hiện hết bằng schema.
4. Tài liệu hóa **401, 403, 404, 429, WWW-Authenticate và Problem Details**, kèm ví dụ có thể tái hiện.
5. Xây **sandbox tách biệt production** về danh tính, dữ liệu, side effects, quota và vòng đời test account.
6. Tạo **quickstart HTTP/curl** và ví dụ **Spring Security** nhất quán với hợp đồng công khai.
7. Thiết kế test bảo vệ sự đồng bộ giữa **docs – OpenAPI – gateway – backend – sandbox**, gồm test phân quyền và luồng lỗi.

Một hướng dẫn API hoàn chỉnh phải trả lời được sáu câu hỏi trước request đầu tiên:

| Câu hỏi từ người tích hợp | Tài liệu phải có |
|---|---|
| Tôi gọi vào đâu? | Base URL theo môi trường, TLS, version/path và trạng thái sẵn có |
| Tôi là ai? | Loại client, quy trình cấp danh tính/credential, chủ thể token |
| Tôi lấy token như thế nào? | OAuth2/OIDC flow đúng, issuer/authorization/token endpoints, PKCE khi dùng |
| Token này được làm gì? | Scopes, tenant/resource ownership, trạng thái và policy ràng buộc |
| Khi thất bại thì sao? | Status, mã lỗi ổn định, challenge, retry, correlation ID và cách sửa |
| Làm sao thử an toàn? | Sandbox, test data, mock side effects, quota, reset, idempotency và giới hạn |

**Tài liệu là một phần của hợp đồng API**. Nếu code trả 404 để che resource của tenant khác nhưng docs hứa 403; hoặc gateway yêu cầu scope **orders:write** trong khi OpenAPI ghi **orders:create**, người học sẽ không thể viết integration test đáng tin và hỗ trợ kỹ thuật không thể phân loại lỗi.

## 2. Authentication và authorization không đồng nghĩa

**Authentication** xác minh danh tính caller và credential. **Authorization** quyết định hành động hiện tại có được thực hiện trên **resource cụ thể** hay không, với context tenant, owner, trạng thái, thời điểm và chính sách. Một token **đúng chữ ký và chưa hết hạn** vẫn có thể không có quyền sửa đơn của người khác.

~~~mermaid
flowchart TD
    C["Developer / client application"] --> I["OAuth2/OIDC identity provider"]
    I -->|Access token| C
    C -->|HTTPS + Authorization Bearer| G["API gateway"]
    G -->|Validate token / coarse scope| A["Orders API / Spring Security"]
    A -->|Tenant, owner, state, policy| D["Domain / database"]
    D -->|Authorized result| R["HTTP response"]
    D -->|Reject safely| E["401 / 403 / 404 / 409"]
~~~

**Không phải mọi client đều dùng cùng flow:**

| Client/use case | Mô hình thường phù hợp | Điều cần giải thích |
|---|---|---|
| Web app tương tác có người dùng | **Authorization Code + PKCE** với OAuth2/OIDC, hoặc **BFF + cookie session** | Redirect URI, PKCE, session/CSRF và logout |
| Mobile/native | Authorization Code + PKCE qua browser hệ thống | Không nhúng client secret trong ứng dụng phân phối |
| Backend-to-backend không có người dùng | **Client Credentials** với service principal | Được cấp quyền theo service, **không giả làm user** |
| Hệ thống ngoài gửi webhook | Chữ ký webhook/mTLS hoặc cơ chế service-to-service riêng | Verify signature, replay window, tenant mapping |
| Public API đọc tài nguyên công khai | Có thể không cần credential | Rate/abuse controls và giới hạn thông tin công khai |

**OAuth2** là khuôn khổ ủy quyền/cấp access token. Nếu cần xác nhận danh tính người dùng đăng nhập theo chuẩn, dùng **OpenID Connect (OIDC)** bên trên OAuth2. **ID token không thay access token** gửi tới resource server. Client credentials không chứng minh có một người dùng cụ thể đứng sau request; API yêu cầu user consent/owner không nên chấp nhận service token như user token mà không có chính sách delegation rõ ràng.

### 2.1. Access token là bearer credential

Ví dụ API yêu cầu access token trong header:

~~~http
GET /v1/orders/57337722-1111-4444-8888-999999999999 HTTP/1.1
Host: sandbox-api.example.test
Authorization: Bearer <sandbox-access-token>
Accept: application/json
~~~

**Không đặt access token trong query string**, URL, log, screenshot hay mã nguồn commit lên Git. Thực hành dùng **HTTPS**, storage bảo vệ credential và chỉ cấp quyền tối thiểu. Refresh token, nếu provider phát, có thời hạn và chính sách xoay/thu hồi riêng; không giả định mọi client đều nhận refresh token hoặc có thể dùng mãi.

Với **JWT**, resource server cần xác minh **signature, issuer (iss), audience (aud), thời gian exp/nbf, thuật toán/khóa được tin, scope/authority**. **Decode payload JWT chỉ là đọc JSON, không phải xác thực chữ ký**. Với **opaque token**, API/gateway thường dùng introspection theo kênh tin cậy hoặc một cơ chế xác thực do issuer cung cấp; client không được dựa vào khả năng decode token để quyết định quyền. Token có audience cho Service A không mặc nhiên hợp lệ với Orders API.

### 2.2. Scope, role và quyền tài nguyên

**Scope** mô tả mức ủy quyền token được cấp, ví dụ **orders:read, orders:write, reports:export**; **role** là nhóm quyền nội bộ như **viewer, operator, admin**, thường gắn với organization/tenant. Chúng không tự đồng nhất. Trong tài liệu, hãy ghi rõ scope nào cho phép gọi route và **điều kiện domain bổ sung**.

| Hành động | Scope tối thiểu | Quy tắc domain cần kiểm tra |
|---|---|---|
| GET /v1/orders | orders:read | Chỉ liệt kê đơn trong tenant và phạm vi được giao |
| GET /v1/orders/{id} | orders:read | Tenant + owner hoặc quyền đọc được ủy quyền |
| POST /v1/orders | orders:write | Cart thuộc principal/tenant, eligible và chưa checkout |
| PATCH /v1/orders/{id} | orders:write | Tenant/owner, state cho phép đổi, If-Match/version |
| POST /v1/reports | reports:export | Tenant có entitlement, quota và giới hạn dữ liệu |

**BOLA/IDOR:** API trả 200 khi caller biết UUID resource của tenant khác là lỗi phân quyền, cho dù token hợp lệ và có **orders:read**. Trong tài liệu, không chỉ viết “requires authentication”; cần phân biệt **route-level scope** với **object-level checks**. Không tin tenantId/actorId do client tự gửi trong body/query thay vì principal đã được xác minh.

**Trạng thái nghiệp vụ** cũng là điều kiện: khách có quyền sửa đơn nhưng đơn đã **SHIPPED** có thể nhận **409 Conflict**; nếu If-Match cũ, dùng **412 Precondition Failed**; chúng không tự động là lỗi 403. Mã lỗi giúp client phân biệt “cần xin quyền” với “cần tải lại trạng thái”.

### 2.3. 401, 403 và 404 cần có quy tắc rõ

| Tình huống | Status thường phù hợp | Ý nghĩa dành cho developer |
|---|---|---|
| Thiếu/không hợp lệ/hết hạn bearer token | **401 Unauthorized** | Lấy token hợp lệ, kiểm issuer/audience/time |
| Token hợp lệ, thiếu scope/permission | **403 Forbidden** | Cần quyền khác; lặp lại y nguyên không giải quyết |
| Resource không tồn tại hoặc không được tiết lộ | **404 Not Found** | Không xác nhận sự tồn tại của resource ngoài scope |
| Body không qua validation | **400 Bad Request** | Sửa request theo schema |
| Business state conflict | **409 Conflict** | Đối soát trạng thái, không xin token mới vô ích |
| Conditional update If-Match không thỏa | **412 Precondition Failed** | Đọc representation mới và xử lý xung đột |
| Rate limit tạm thời | **429 Too Many Requests** | Chờ theo Retry-After và retry budget |
| Dependency/gateway tạm lỗi | **502/503/504** tùy tầng | Backoff, giữ idempotency/tra operation trước retry |

**401** theo HTTP semantics cần challenge **WWW-Authenticate** phù hợp với scheme; với OAuth2 Bearer, **RFC 6750** định nghĩa các giá trị như **invalid_token** và **insufficient_scope**. **403 không phải lời yêu cầu đăng nhập lại** nếu principal đã xác thực, và **404 có thể được dùng để không công bố resource bị cấm** theo chính sách nhất quán. API không nên trả về danh sách scope của người dùng khác hoặc mô tả chính xác policy nội bộ nhạy cảm.

## 3. Đưa bảo mật vào OpenAPI 3.1 và phần mô tả nghiệp vụ

OpenAPI mô tả **cơ chế nhận credential** và **yêu cầu bảo mật theo operation**. Nó **không tự thực thi JWT validation** và không thể biểu diễn đầy đủ mọi quan hệ owner, tenant hay trạng thái dữ liệu. Vì vậy cần kết hợp **schema máy đọc được** với diễn giải/ma trận quyền cho nhà phát triển.

### 3.1. Ví dụ OpenAPI dành cho người tích hợp

Đây là một trích đoạn **OpenAPI 3.1.0** minh họa. Các host **example.test** là địa chỉ giả để trình bày, **không phải môi trường có thể gọi thật**. Khi publish, thay bằng endpoints thực đã được cấp và kiểm thử.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
  description: >
    APIs for tenant-scoped orders. Use an OAuth2 access token;
    ID tokens are not accepted as API credentials.
servers:
  - url: https://sandbox-api.example.test
    description: Sandbox; test data only
  - url: https://api.example.test
    description: Production; real business effects
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      description: >
        Use Authorization Code + PKCE for user-driven clients.
        Use Client Credentials only for permitted service actions.
      flows:
        authorizationCode:
          authorizationUrl: https://sandbox-id.example.test/oauth2/authorize
          tokenUrl: https://sandbox-id.example.test/oauth2/token
          scopes:
            orders:read: Read orders in authorized tenant scope
            orders:write: Create or update permitted orders
        clientCredentials:
          tokenUrl: https://sandbox-id.example.test/oauth2/token
          scopes:
            orders:read: Read orders assigned to service principal
  schemas:
    Problem:
      type: object
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        code: { type: string }
      required: [type, title, status]
paths:
  /v1/orders:
    get:
      operationId: listOrders
      summary: List authorized orders
      description: >
        Reads only orders visible to the caller's tenant and
        business permissions. Scope alone does not grant access
        to another tenant's resources.
      security:
        - ordersOAuth: [orders:read]
      parameters:
        - in: query
          name: limit
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
      responses:
        '200':
          description: Authorized list; obey pagination contract
        '401':
          description: Missing, expired or invalid access token
          headers:
            WWW-Authenticate:
              schema: { type: string }
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
        '403':
          description: Authenticated but not permitted
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
    post:
      operationId: createOrder
      summary: Create an order
      description: >
        Requires access to the cart in the caller's tenant.
        A service token cannot impersonate an end user without
        an explicitly supported delegation policy.
      security:
        - ordersOAuth: [orders:write]
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema: { type: string, minLength: 8, maxLength: 128 }
          description: Stable per logical order, scoped to tenant and caller
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                cartId: { type: string, format: uuid }
              required: [cartId]
              additionalProperties: false
      responses:
        '201':
          description: Order committed; Location identifies new resource
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
        '400':
          description: Invalid request or missing idempotency key
        '401':
          description: Bearer credential is missing or invalid
        '403':
          description: Valid credential but required permission missing
        '409':
          description: Cart conflict or idempotency key reused with new input
        '429':
          description: Request rate limit reached
          headers:
            Retry-After:
              schema: { type: string }
  /v1/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Read an order in authorized scope
      security:
        - ordersOAuth: [orders:read]
      parameters:
        - in: path
          name: orderId
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200': { description: Visible order representation }
        '401': { description: Authentication required }
        '403': { description: Missing authorization }
        '404': { description: Not found or not visible }
~~~

**Giới hạn quan trọng của ví dụ:** các **authorizationUrl/tokenUrl** đang trỏ tới sandbox. Trong tài liệu production, phải cung cấp **spec/metadata issuer tương ứng** hoặc cơ chế chọn server+security metadata chính xác; việc đổi mỗi **servers.url** trong OpenAPI **không tự đổi token endpoint**. Mỗi môi trường phải dùng access token có **issuer/audience** của môi trường đó, không copy token sandbox sang production.

Khi dùng nhiều credential loại khác nhau, OpenAPI cho phép định nghĩa thêm:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
~~~

**Đây là trích đoạn độc lập**, không nối nguyên văn vào một file đã có **components** nếu chưa merge đúng cấu trúc. **bearerFormat: JWT** là gợi ý định dạng, không bắt validator kiểm chữ ký hay audience. Một **API key** nếu được hỗ trợ phải có quy tắc tạo/xoay/thu hồi, phạm vi và lưu trữ riêng; không coi key là người dùng hay dùng chung cho mọi tenant. Đừng công bố phương thức không thật sự được backend hỗ trợ.

### 3.2. Logic của security requirement trong OpenAPI

~~~yaml
# Ở mức operation: cần scope orders:read.
security:
  - ordersOAuth: [orders:read]

# Hai phương án độc lập: credential A HOẶC credential B.
security:
  - ordersOAuth: [orders:read]
  - bearerAuth: []

# Trong cùng một object là điều kiện AND (nếu hệ thống hỗ trợ).
security:
  - partnerApiKey: []
    ordersOAuth: [orders:read]

# Override bảo mật root: operation này không yêu cầu credential.
security: []
~~~

**Mỗi phần tử mảng security là OR; nhiều scheme trong một object là AND**. Với OAuth2/OpenID Connect, danh sách scope trong object mô tả **các scope bắt buộc đồng thời** (tùy mô hình quyền thực tế), không nên tùy tiện đặt nhiều scope nếu backend chỉ yêu cầu một. **security: []** trong operation **ghi đè security cấp root**, nên việc dùng sai có thể công bố một endpoint nhạy cảm là public. Test spec và thực thi để tránh nhầm.

### 3.3. Những gì OpenAPI cần bổ sung bằng prose

- **Ai được cấp credential:** cách đăng ký ứng dụng, phê duyệt scope, client secret rotation, người liên hệ và thời gian hiệu lực.
- **Ranh giới quyền:** actor và tenant rút từ token đã xác minh, các role được phép, owner/beneficiary và trạng thái hợp lệ.
- **Môi trường:** base URL, issuer/audience, JWKS/discovery, certificate/TLS, quota, test accounts và sandbox data.
- **HTTP errors:** Problem Details ổn định, ví dụ 401/403/404, Retry-After, correlation ID, idempotency khi retry.
- **Vòng đời quyền:** revoke scope/token, đổi vai trò, khóa account, quyền theo tenant thay đổi thì truy vấn hiện tại được cập nhật thế nào.
- **Độ tin cậy:** 201/202, Location, trạng thái bất đồng bộ, retry và đối soát sau timeout.

Quyền đọc qua **GET** không có nghĩa quyền cập nhật qua **PATCH**. Một SDK sinh tự động từ OpenAPI có thể gắn header Authorization đúng, nhưng **không thể suy ra tất cả điều kiện truy cập row** nếu docs chỉ mô tả bearerAuth. Tài liệu quyền phải chứa cả ví dụ **được phép** và **bị từ chối**.

## 4. Viết response lỗi đủ để developer tự sửa

Ví dụ không có access token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://sandbox-api.example.test/problems/unauthorized",
  "title": "Authentication required",
  "status": 401,
  "code": "UNAUTHENTICATED"
}
~~~

Ví dụ token có mặt nhưng **không hợp lệ hoặc đã hết hạn**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://sandbox-api.example.test/problems/invalid-token",
  "title": "Invalid access token",
  "status": 401,
  "code": "INVALID_TOKEN"
}
~~~

Token hợp lệ nhưng thiếu scope có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders:write"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://sandbox-api.example.test/problems/forbidden",
  "title": "Insufficient permission",
  "status": 403,
  "code": "INSUFFICIENT_SCOPE"
}
~~~

Các challenge nêu trên là ví dụ theo **RFC 6750** cho bearer token; error descriptions chỉ nên cho thông tin **an toàn**, không tiết lộ nội bộ. Nếu lệnh bị từ chối do **BOLA**, tài liệu có thể quy định **404** để che sự tồn tại, thay vì công bố rằng order ID thật nhưng thuộc tenant khác. Tuyệt đối không trả **JWT, user profile nhạy cảm, policy engine internals hoặc stack trace** trong Problem Details.

**Tên mã lỗi là contract có version:** client có thể dựa vào **code** để xử lý ổn định, còn **detail** là thông điệp hỗ trợ có thể bản địa hóa và thay đổi. Với 429, chỉ gửi Retry-After khi có chính sách chờ hợp lý; với 503, Retry-After là gợi ý khi tạm không phục vụ, không bảo đảm retry sẽ thành công. Thêm request/trace ID đã được tạo/kiểm soát tại trusted edge để hỗ trợ đối soát, không dùng token làm correlation ID.

## 5. Thiết kế môi trường thử nghiệm tách biệt production

**Sandbox** là môi trường để người tích hợp học, phát hiện lỗi và kiểm thử theo contract **mà không gây tác động nghiệp vụ thật**. Nó không phải bản production được bật thêm một cờ **test=true** trong JSON, trừ khi hệ thống có thiết kế cô lập được chứng minh. Một sandbox đáng tin phải tách **identity, credentials, data, downstream side effects, quota và quyền vận hành**.

| Đặc tính | Sandbox | Staging nội bộ | Production |
|---|---|---|---|
| Base URL minh họa | https://sandbox-api.example.test | https://staging-api.example.test | https://api.example.test |
| Identity provider | **Sandbox issuer**, test accounts | Staging issuer/test federation | Production issuer |
| Audience | **orders-api-sandbox** | orders-api-staging | orders-api |
| Credential | Test client, test scopes, TTL rõ | CI/internal credentials | Approved live client credentials |
| Dữ liệu | Synthetic, có reset/seed | Dữ liệu kiểm thử nội bộ | Dữ liệu khách hàng thật |
| Payment/SMS/email | Stub hoặc test mode **không phát thật** | Integration sandbox của đối tác | Side effects thật |
| Quota | Giới hạn test được công bố | Capacity theo load test | Contract/billing/quota thật |
| Độ ổn định | Có lịch reset/maintenance | Release-candidate validation | SLO đã cam kết |
| Khả năng truy cập | Developer được cấp quyền | Team/CI nội bộ | Theo quy trình production |

**Những URL, issuer và audience trong bảng là giả định minh họa.** Tài liệu đã phát hành phải cung cấp thông số **đang hoạt động** của nhà cung cấp, không để developer đoán hay tái sử dụng endpoint từ ví dụ. Nếu JWT sandbox có thể dùng được tại production, ranh giới môi trường đã bị phá; resource server production phải từ chối token sai **iss/aud/key/trust policy**, ngay cả khi scope name trùng.

### 5.1. Danh tính và quyền thử nghiệm

Nhà phát triển cần quy trình cụ thể: đăng ký ứng dụng, nhận **test client ID**, cấp **client secret chỉ cho confidential client**, đăng ký redirect URIs cho flow user, chọn test tenant và scopes, kích hoạt/hủy ứng dụng. Không gửi client secret qua email/chat public hoặc tài liệu markdown. Một sandbox hỗ trợ OAuth2 nên công bố:

- **Authorization endpoint, token endpoint, issuer, JWKS/discovery URL**, danh sách grant types, scopes được cấp và token lifetime.
- **PKCE S256** cho public clients và user-driven flow; các redirect URI được allowlist và test với exact URI policy của provider.
- Có/không hỗ trợ **refresh token**, refresh token rotation, revoke/introspection, logout và token reuse detection.
- **Test personas** có quyền phân biệt: viewer, editor, admin của tenant A; user bị khóa/không có scope; tenant B để thử BOLA.
- Quy trình **approval scope**: cách xin thêm quyền, ai phê duyệt, thời gian cập nhật token; đổi permission không nhất thiết làm token cũ tự có thêm scope.

**Authorization Code + PKCE**: client tạo **code_verifier** có entropy cao, gửi **code_challenge** được tính bằng **BASE64URL(SHA256(code_verifier))**, rồi chứng minh verifier khi đổi authorization code lấy token. **PKCE không thay client authentication** của confidential client; nó giúp bảo vệ authorization code. Mobile/SPA không được nhúng shared client secret rồi gọi đó là bảo mật. Nếu dùng BFF cookie, docs phải mô tả session/CSRF/SameSite/HttpOnly/Secure và ranh giới token được giữ ở backend.

### 5.2. Dữ liệu, side effects và fixture tái lập

Một bộ fixture tối thiểu có thể gồm:

| Đối tượng thử | Trạng thái fixture | Mục đích |
|---|---|---|
| Tenant A, viewer | Có scope orders:read | GET được phép, POST bị 403 |
| Tenant A, editor | Có scope orders:write và owner hợp lệ | POST/GET trong tenant |
| Tenant B, editor | Quyền hợp lệ ở tenant B | Thử cross-tenant 404/403 |
| Cart A1 | OPEN, thuộc editor A | POST tạo order trả 201 |
| Cart A2 | CHECKED_OUT | POST trả 409 |
| Order A3 | SHIPPED, version=4 | PATCH bị conflict hoặc precondition |
| Payment test | success, decline, timeout có thể kích hoạt | Test 202/async reconciliation |

Cung cấp **test data seed/reset** có cơ chế điều khiển và idempotency: reset tenant A không xóa dữ liệu test của tenant B, không làm mất cùng lúc kết quả của team khác. Nêu rõ fixture IDs có ổn định không, TTL dữ liệu, lịch xóa định kỳ và rủi ro khi chạy test song song. Với webhook, docs phải cho biết test event types, delivery/retry, test signing secret, cách xác minh chữ ký và replay; không gửi webhook thử tới URL nhận thanh toán production.

**Không dùng dữ liệu khách hàng production đã sao chép nguyên vẹn** để “giống thật”. Khi cần dữ liệu thực tế hóa, dùng tổng hợp/anonymization được đánh giá, kiểm tra không thể tái nhận dạng và giới hạn quyền truy cập. Test environment không được có đường đi lặng lẽ tới **payment charge, email/SMS thật, kho thật hoặc tài khoản người dùng thật**. Nếu tích hợp payment provider có chế độ test, phải mô tả rõ chỉ chấp nhận test credentials/methods và cách xác minh không thu tiền.

### 5.3. Giới hạn và các lỗi có chủ đích

Sandbox thường có capacity thấp hơn production. Hãy công bố **RPS/burst, quota theo test tenant/client, max payload, pagination limit, timeout, giới hạn jobs đang chạy, lịch maintenance và thời gian reset**. Request vượt nhịp trả **429** đúng Retry-After; hệ thống sandbox đang maintenance nên trả **503**, không gán đó là lạm dụng của developer.

Cho phép **fault simulation** có kiểm soát như payment decline, upstream timeout hoặc webhook retry bằng fixture/endpoint test **được phân quyền riêng**. Không dùng query **forceSuccess=true** trên endpoint production như cách thử lỗi; không cho caller bật debug để lộ stack trace/token. Sandbox cần có log/trace correlation giúp developer gửi request ID cho support mà không gửi bí mật.

### 5.4. Quản trị nhiều phiên bản môi trường

Sandbox có thể dùng release mới sớm hơn production để thử tính tương thích, nhưng tài liệu phải ghi **OpenAPI version, API version, deploy/version notice, danh sách breaking changes và lịch deprecation**. Khác biệt có chủ đích cần nằm trong bảng capability, không ẩn trong lỗi 404. Nếu thay đổi issuer, JWKS/algorithm, OAuth flow, cookie hay scope name, phải có migration guide và test chạy trước ngày chuyển đổi.

## 6. Quickstart cho đối tác: từ credential đến request đầu tiên

Mục tiêu của quickstart là developer làm được một **happy path và một failure path** trong sandbox mà không cần nhờ support cấp dữ liệu giả thủ công. Các lệnh sau là ví dụ **Bash/curl**, địa chỉ **example.test** không gọi được nếu chưa có sandbox thật, và các biến môi trường phải được cấp từ hệ thống credential phù hợp.

### Bước 1 — Nhận quyền và chọn đúng môi trường

Đăng ký **sandbox client**, xác nhận flow theo loại ứng dụng, test tenant, scope được cấp và endpoint OAuth2. Kiểm tra tài liệu **OIDC discovery / issuer metadata** do provider công bố; đừng suy token URL từ API base URL. Không bỏ qua TLS certificate validation, không copy production client secret sang shell sandbox.

### Bước 2 — Lấy access token cho service client

Ví dụ **client_credentials** chỉ được cấp **orders:read** theo OpenAPI minh họa. Confidential client giữ secret ở máy/secret manager an toàn; code bên dưới không in token ra terminal:

~~~bash
export SANDBOX_API="https://sandbox-api.example.test"
export SANDBOX_TOKEN_URL="https://sandbox-id.example.test/oauth2/token"

# SANDBOX_CLIENT_ID và SANDBOX_CLIENT_SECRET do hệ thống test cấp riêng.
# Không đưa hai giá trị này vào Git, lịch sử shell hoặc ảnh chụp.
TOKEN_RESPONSE="$(curl --fail-with-body --silent --show-error \
  --request POST "$SANDBOX_TOKEN_URL" \
  --user "$SANDBOX_CLIENT_ID:$SANDBOX_CLIENT_SECRET" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders:read")"
SANDBOX_ACCESS_TOKEN="$(printf '%s' "$TOKEN_RESPONSE" | jq -r '.access_token')"
unset TOKEN_RESPONSE
~~~

Ví dụ giả định máy có **curl/jq** và issuer hỗ trợ HTTP Basic client authentication cho confidential client. Trong thực tế phải tuân cơ chế client authentication provider công bố; **không** dùng client_credentials trong browser/mobile app để cất secret. Token trong process memory và môi trường shell vẫn là bí mật: không bật shell tracing **set -x**, không paste full command có secret vào ticket/chat, giới hạn thời gian session, và xóa biến sau thử nghiệm.

### Bước 3 — Gọi GET bằng token vừa cấp

~~~bash
curl --include --silent --show-error \
  -H "Authorization: Bearer $SANDBOX_ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "$SANDBOX_API/v1/orders?limit=20"
~~~

Kỳ vọng **200 OK** với các order mà **service principal** thực sự được cấp quyền đọc, hoặc **403** nếu scope/entitlement chưa có. **Không mặc định client_credentials đại diện một user** và không bảo đảm mọi endpoint/orders thuộc mọi tenant được liệt kê. Khi hết hạn, lấy token mới theo grant được hỗ trợ; khi sai audience/issuer, phải lấy token ở đúng issuer/môi trường chứ không sửa JWT bằng tay.

### Bước 4 — Tạo order với user-driven token

Vì ví dụ OpenAPI chỉ cấp **orders:write** cho flow Authorization Code, trước tiên đăng nhập một **test persona editor** bằng **Authorization Code + PKCE** theo hướng dẫn issuer, rồi dùng **access token dành cho Orders API**. Không dùng ID token. Request tạo order cần **Idempotency-Key** ổn định trong lần retry:

~~~bash
export SANDBOX_CART_ID="11111111-2222-4333-8444-555555555555"
export IDEM_KEY="sandbox-order-5eb24ca7-c2e4-4bd1"

curl --include --silent --show-error \
  -X POST "$SANDBOX_API/v1/orders" \
  -H "Authorization: Bearer $SANDBOX_USER_ACCESS_TOKEN" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -H "Content-Type: application/json" \
  --data "{\"cartId\":\"$SANDBOX_CART_ID\"}"
~~~

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/57337722-1111-4444-8888-999999999999
Cache-Control: no-store
Content-Type: application/json

{"id":"57337722-1111-4444-8888-999999999999","status":"PENDING"}
~~~

**Chỉ trả 201 sau commit** nếu resource order đã được tạo. Với xử lý chỉ mới nhận bền vững, trả **202 Accepted** cùng URI operation/job và cách polling; 202 không hứa payment thành công. Nếu request timeout sau khi server commit, client retry **cùng key và payload**, không tạo key mới hay thanh toán hai lần. Để đối soát có thể dùng GET theo Location hoặc operation ID. Với idempotency replay, status/headers/body được trả theo hợp đồng công bố, không tự sinh order mới.

### Bước 5 — Thử failure path và dọn môi trường

Gọi POST bằng persona chỉ có **orders:read** để thấy **403/INSUFFICIENT_SCOPE**; gọi order thuộc tenant khác để thấy **404/403 che thông tin** theo policy; thử token sai môi trường để thấy **401/INVALID_TOKEN**. Khi nhận **429**, giảm nhịp và tôn trọng Retry-After; không spam để “kiểm chứng API đang an toàn”. Sau thử nghiệm, reset fixtures đúng tenant qua chức năng được cấp, thu hồi test token/secret bị lộ, dọn biến shell.

**Checklist quickstart đạt** khi người mới có thể: lấy token theo flow hợp lệ, thấy 200 trong tenant của mình, tạo resource theo quyền, hiểu 401/403/404, xử lý retry an toàn và biết nơi gửi request ID khi cần hỗ trợ.

## 7. Java/Spring Security phải thực thi đúng những gì tài liệu hứa

Các ví dụ dưới đây nhắm **Java 17, Spring Boot 3, Spring Security 6** với một **resource server dùng OAuth2 Bearer token**. Mẫu chỉ cho thấy ranh giới cần kiểm chứng: project thật phải có Spring Web, Validation, Spring Security, OAuth2 Resource Server, repository và cấu hình CORS/exception response nhất quán. Không coi trích đoạn là hệ thống có thể chạy độc lập.

### 7.1. Route-level authentication và scopes

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class OrdersApiSecurity {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/v1/orders", "/v1/orders/*")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/v1/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                    session.sessionCreationPolicy(
                            SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Spring Resource Server thường chuyển OAuth2 **scope** của JWT thành authority có tiền tố **SCOPE_**; phải kiểm tra claim thực tế của issuer và mapping converter nếu issuer dùng **scp, roles, permissions** theo cách khác. **Tắt CSRF** trong ví dụ **chỉ hợp lý với API bearer-only thực sự không xác thực write bằng cookie**. Nếu có browser session/BFF, phải bật CSRF protection cho write routes và cấu hình CORS/cookie riêng; không sao chép cấu hình này áp cho mọi app.

**anyRequest().denyAll()** là deny-by-default trong ví dụ; ứng dụng thật cần khai báo có chủ đích các route khác, actuator/probe riêng và method PATCH/DELETE nếu hỗ trợ. Cấm mặc định tốt hơn để một endpoint mới vô tình chỉ cần token bất kỳ là truy cập được.

### 7.2. Cố định issuer và audience theo môi trường

~~~properties
# Giá trị minh họa cho profile sandbox, KHÔNG dùng khi chạy production.
security.jwt.issuer=https://sandbox-id.example.test
security.jwt.audience=orders-api-sandbox
~~~

Ví dụ decoder xác minh issuer và audience:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfig {
    @Bean
    NimbusJwtDecoder jwtDecoder(Environment environment) {
        String issuer =
                environment.getRequiredProperty("security.jwt.issuer");
        String expectedAudience =
                environment.getRequiredProperty("security.jwt.audience");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(issuer).build();
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                        "aud",
                        values -> values != null
                                && values.contains(expectedAudience));
        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));
        return decoder;
    }
}
~~~

**Lưu ý:** decoder lấy metadata/JWKS từ issuer tin cậy nên môi trường phải cấu hình network, certificate, cache/rotation và giới hạn trust rõ ràng. JWT validation còn cần chính sách **accepted algorithms/keys**, scope và nbf/exp/skew phù hợp; không cho phép token dùng **alg=none** hoặc issuer URL do client gửi. Sandbox/prod phải có **configuration tách biệt**, không bật đa issuer chỉ vì muốn “tiện test”. Nếu hệ thống dùng opaque token, dùng introspection thích hợp thay cho decoder này.

### 7.3. Service kiểm tra quyền trên từng order

Route GET có scope **orders:read** là điều kiện cần, chưa đủ. Backend vẫn phải giới hạn theo **tenant/owner** và policy domain:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

record VerifiedActor(UUID tenantId, String subject) {}
record OrderSummary(UUID id, String status) {}

interface VerifiedActorResolver {
    // Chỉ nhận Jwt đã được resource server xác minh.
    VerifiedActor fromJwt(Jwt jwt);
}

interface OrderViewRepository {
    // Truy vấn SQL bắt buộc lọc tenant + principal hoặc quyền được ủy quyền.
    Optional<OrderSummary> findVisible(
            UUID tenantId, String subject, UUID orderId);
}

@RestController
@RequestMapping("/v1/orders")
class OrderReadController {
    private final VerifiedActorResolver actors;
    private final OrderViewRepository orders;

    OrderReadController(
            VerifiedActorResolver actors, OrderViewRepository orders) {
        this.actors = actors;
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    OrderSummary read(@PathVariable UUID orderId,
                      @AuthenticationPrincipal Jwt jwt) {
        VerifiedActor actor = actors.fromJwt(jwt);
        return orders.findVisible(
                    actor.tenantId(), actor.subject(), orderId)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"));
    }
}
~~~

**VerifiedActorResolver** phải tra **tenant membership, loại principal và quyền delegation** theo hợp đồng, không chỉ parse header **X-Tenant-Id** hoặc tin claim tự khai. Nếu service token không đại diện owner user, repository cần policy service principal riêng; không lấy **subject** của service token và giả định đó là userId. Khi triển khai **tenant administrator** đọc order thành viên, cần mô tả và kiểm tra role/permission trong tenant, không bỏ điều kiện tenant khỏi query.

Trả **404** cho order không nhìn thấy là một lựa chọn tránh tiết lộ sự tồn tại; **scope bị thiếu vẫn thường do security filter trả 403**. Tài liệu cần công bố điều này nhất quán. Trạng thái **409/412** dành cho conflict/version, không bị thay bằng 403 chỉ vì business không cho sửa.

### 7.4. Spring và proxy phải thống nhất lỗi bảo mật

Khi gateway cũng kiểm JWT, backend và gateway phải thống nhất **issuer/audience/scope**. Tránh trường hợp gateway cho qua nhưng Spring trả 403 vì tên authority khác, hoặc gateway trả HTML 401 còn Spring trả JSON 401. Với API public, định nghĩa một schema **application/problem+json** có mã lỗi ổn định cho các lỗi do từng tầng tạo, trong khi giữ **WWW-Authenticate** đúng với bearer challenge. Không forward token tới service không tin cậy, và không dùng header giả identity của browser làm thông tin xác thực nội bộ.

## 8. Kiểm thử docs và sandbox như một sản phẩm

**Tài liệu OpenAPI xanh không có nghĩa authorization an toàn**. Cần test cả **schema, response thật, quyền từng resource, môi trường thử và side effects**. Một ma trận test tối thiểu:

| Test | Request/fixture | Kỳ vọng |
|---|---|---|
| Không Authorization | GET order | **401** + WWW-Authenticate phù hợp |
| JWT sai chữ ký/issuer/audience | GET sandbox với token khác issuer | **401**, không trả dữ liệu |
| JWT hết hạn/nbf tương lai | GET với token không hợp lệ thời gian | **401**, không “nhẹ tay” trong sandbox |
| Đúng issuer/aud, thiếu orders:read | GET order | **403** hoặc insufficient scope challenge |
| Tenant A đọc order B | GET orderId B bằng persona A | **404/403** theo policy, không rò owner/tenant B |
| Persona viewer tạo order | POST /v1/orders | **403**, không tạo order |
| Persona editor tạo order A | POST hợp lệ + key mới | **201 + Location**, row đã commit |
| POST timeout rồi retry cùng key | Hai HTTP attempts cùng payload | Một logical order, không tạo side effect mới |
| Cùng key, body khác | Hai POST khác cartId | Conflict theo contract, không ghi đè kết quả cũ |
| Cart đã checkout | POST với cart fixture đã đóng | **409**, không tạo đơn thứ hai |
| 429/quota | Vượt ngưỡng sandbox công bố | **429 + Retry-After**, không ngụy trang lỗi hạ tầng |
| Web browser + cookie route | Preflight/cookie POST trong BFF | CORS/CSRF/SameSite phù hợp |
| Sandbox payment | Trigger success/decline/timeout | **Không thu tiền thật**, status/webhook như contract |
| Token sandbox tại production | Dùng sandbox JWT trên prod test boundary | Từ chối **401**; không chia sẻ key/issuer |
| Quyền bị thu hồi | Revoke/đổi role khi test | Hành vi đúng với token TTL/permission refresh policy |

Đối với **OpenAPI contract tests**, lint cấu trúc YAML/security schemes, kiểm tra operationId không trùng, schema response và các status được định nghĩa. Với **MockMvc + spring-security-test**, kiểm tra route filter và domain authz. Nhưng **jwt() test postprocessor tạo authentication giả**, không thực sự xác minh chữ ký, expiry, issuer hay audience; cần thêm integration test với **JWKS/IdP test**, token ký sai và token thuộc môi trường khác.

### 8.1. MockMvc cho scope và quyền tài nguyên

Ví dụ test skeleton giả định **OrderReadController**, JWT security chain ở trên, các bean resolver/repository và Spring Boot context:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAccessContractTest {
    @Autowired MockMvc mvc;
    private static final String URL = "/v1/orders/"
            + "57337722-1111-4444-8888-999999999999";

    @Test
    void missingTokenReturns401() throws Exception {
        mvc.perform(get(URL))
                .andExpect(status().isUnauthorized())
                .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void tokenWithoutReadScopeReturns403() throws Exception {
        mvc.perform(get(URL).with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:write"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Test trên **cần dependency spring-security-test và context triển khai các bean cần thiết**; JWKS test hoặc **test override của JwtDecoder** có thể cần để context khởi động mà không gọi issuer giả. Chưa kiểm tra tenant isolation vì route không đi vào service khi thiếu scope. Test tenant A/B phải dùng **token có orders:read hợp lệ** rồi cố đọc order B có fixture thực tế; xác minh **không có record B trong response, log hoặc Problem Details**. Kiểm thử ở **database thật hoặc Testcontainers** để phát hiện query vô tình thiếu điều kiện tenant.

### 8.2. Test ranh giới production và môi trường giả lập

Thử phân biệt issuer/audience bằng các token test: token được ký hợp lệ cho sandbox **không được** chạy qua production; token có đúng scope nhưng audience sai vẫn phải **401**. Đảm bảo production không dùng nhầm issuer profile sandbox hoặc bỏ validation để làm demo. Với tests qua gateway/reverse proxy, kiểm tra **public HTTPS URL, CORS, Location, WWW-Authenticate, Retry-After**, không chỉ controller trực tiếp.

Một test sandbox trả payment success phải đồng thời kiểm tra **payment provider sandbox/test mode**, không có callback tới production, không phát SMS/email thật, dữ liệu được dọn đúng tenant. Gắn **test run identifier** và lưu kết quả/trace ID an toàn để phân tích failure; test chạy song song không được reset fixture của nhau. Khi test fail, developer phải có đủ thông tin để lặp lại mà không gửi access token cho support.

## 9. Troubleshooting và vòng đời tài liệu

Đừng kết thúc hướng dẫn ở “nếu lỗi hãy liên hệ hỗ trợ”. Một bảng tự xử lý thường giúp giảm nhiều vòng trao đổi:

| Developer thấy | Kiểm tra trước | Không nên làm |
|---|---|---|
| **401 invalid_token** | Token còn hạn? Issuer đúng env? aud=Orders API? JWT ký/khóa đúng? | Tắt JWT validation hoặc sửa claim bằng tay |
| **403 insufficient_scope** | Client đã được grant scope? Token mới đã chứa scope? Route có quyền domain bổ sung? | Retry liên tục cùng token |
| **404 dù ID tồn tại** | Có phải tenant/owner khác? Resource đã xóa? API có che sự tồn tại? | Dùng admin token để bỏ qua isolation |
| **POST 409** | Cart đã checkout? Idempotency-Key trùng nhưng khác payload? | Đổi key vô tội vạ để tạo trùng |
| **429** | Hạn mức theo tenant/client/route? Retry-After? | Tăng retry song song gây burst |
| **502/503/504** | Gateway/upstream/status; operation có thể đã commit? | Kết luận payment chưa chạy từ timeout |
| **CORS blocked** | Origin/credentials/preflight/allowlist; auth route của browser? | Dùng wildcard CORS + credentials hoặc bỏ CSRF |
| Sandbox không có dữ liệu | Seed đã reset? Persona/tenant đúng? Cursor/filter có hợp lệ? | Copy dữ liệu production sang sandbox |

Khi gửi ticket hỗ trợ, cung cấp **time UTC, environment, route template, HTTP status, code, request/trace ID, operation ID đã che phù hợp và bước tái hiện**. Không gửi bearer token, client secret, refresh token, Authorization/Cookie header, dữ liệu thẻ hoặc toàn bộ payload cá nhân. Support cần quyền tra cứu log theo trace ID với retention/audit phù hợp, không yêu cầu developer công bố bí mật.

### 9.1. Giữ OpenAPI, SDK và sandbox đồng bộ

Một thay đổi API nên đi theo luồng:

~~~text
Business/security policy change
    -> update OpenAPI + authz prose + examples
    -> validate spec and generated SDK
    -> negative auth and cross-tenant tests
    -> sandbox deploy + executable quickstart
    -> staging contract checks through gateway
    -> version/deprecation notice for production
    -> monitoring and support/runbook updates
~~~

**CI gate** nên phát hiện: endpoint thiếu security requirement, docs tuyên bố public nhưng backend đòi JWT, scope đổi tên, auth endpoint sai môi trường, 401 không có challenge, response 403/404 khác policy và sample curl lỗi. Phân biệt sự thay đổi **breaking** như bỏ scope, đổi token audience/issuer, thay đổi tenant visibility hoặc đổi base URL với thay đổi chỉ thêm ví dụ. Không hứa sandbox “giống hệt production” nếu dependency, quota và lịch deploy khác biệt; công bố những khác biệt này.

Mỗi ví dụ nên có **owner, version, expected status, fixture dependency và cách chạy trong sandbox**. SDK examples nên xử lý idempotency, timeout, retries/backoff và phân trang đúng hợp đồng. Với deprecation, cung cấp **thời điểm, hướng dẫn migration, đường dẫn tài liệu và thời gian hỗ trợ**, tránh buộc client đoán từ một lỗi 404 đột ngột.

## 10. Bài tập: viết hướng dẫn tích hợp Orders API

Một nhà cung cấp muốn cho ba nhóm client gọi Orders API: **web BFF**, **mobile app** và **backend đối tác**. Tài nguyên /v1/orders có tenant isolation; GET cần scope **orders:read**, POST cần **orders:write**, nhưng khách chỉ được sửa đơn của chính mình trước trạng thái SHIPPED. Sandbox phải cho thử thanh toán thành công/thất bại mà không chuyển tiền thật. API dùng **Idempotency-Key** khi tạo order và trả **201 sau commit**.

Hãy nộp:

1. **Ma trận client – flow – credential:** Authorization Code + PKCE, client credentials và trường hợp BFF cookie/CSRF; giải thích vì sao mobile không chứa client secret.
2. **OpenAPI 3.1:** securitySchemes, security trên GET/POST, 201 Location và 401/403/404/409/429; chỉ rõ quyền theo tenant mà spec không tự diễn đạt.
3. **Bảng môi trường:** sandbox/prod base URL, issuer/audience riêng, test users, token TTL, limit và side effects giả.
4. **Hai HTTP examples:** GET 200 với đúng scope, POST 201 kèm Idempotency-Key; thêm một response **403 insufficient_scope** và **404 che resource khác tenant**.
5. **Quickstart 5 bước:** đăng ký test client, lấy token theo flow, gọi endpoint, xử lý lỗi, reset/cleanup.
6. **Java/Spring Security:** kiểm scope route, JWT issuer/audience và query giới hạn tenant/owner; nêu chính sách CSRF của BFF.
7. **Tám test:** sai issuer/audience, thiếu scope, cross-tenant, POST retry, cart conflict, 429, payment sandbox và credential leak prevention.

**Gợi ý kiểm tra:** giả lập persona **viewer A**, **editor A**, **editor B**. Viewer A có token đúng nhưng POST phải 403; editor A GET order B không thấy thông tin B; sandbox token không chạy ở prod; payment test phải không có side effect thật. POST timeout sau commit cần đối soát operation hoặc retry cùng key, không tạo order mới. Nếu Swagger UI có nút “Authorize”, flow và redirect URI phải được cấu hình đúng, không mời người dùng dán client secret production vào browser.

## 11. Checklist và tham khảo

- [ ] Tài liệu phân biệt **AuthN, AuthZ, OAuth2 scope, role và tenant/owner policy**.
- [ ] Mỗi client biết **grant type, token endpoint, issuer, audience, expiry, scope, storage** và cách cấp/thu hồi.
- [ ] OpenAPI operation có **security** đúng; hiểu **OR/AND**, không dùng security: [] nhầm cho endpoint nhạy cảm.
- [ ] HTTP **401 + WWW-Authenticate, 403, 404, 409, 412, 429/Retry-After** có ví dụ và mã lỗi ổn định.
- [ ] Sandbox/prod tách **issuer, credentials, dữ liệu, payment/webhook, quota và reset**; không dùng PII/side effect thật.
- [ ] Quickstart có success/failure paths, fixture, idempotency và cách nhận hỗ trợ không cần gửi secret.
- [ ] Spring Security kiểm tra **issuer/audience/scope**; domain service kiểm **tenant/owner/state**.
- [ ] CI có **OpenAPI lint, security contract, JWT integration, BOLA, CORS/CSRF và sandbox safety tests**.
- [ ] Docs/SDK/spec/version/migration notice được cập nhật cùng release, có owner và ngày rà soát.

Tham khảo: **OpenAPI Specification 3.1**, https://spec.openapis.org/oas/v3.1.0.html; **OAuth 2.0 Framework RFC 6749**, https://www.rfc-editor.org/rfc/rfc6749.html; **OAuth 2.0 Bearer RFC 6750**, https://www.rfc-editor.org/rfc/rfc6750.html; **PKCE RFC 7636**, https://www.rfc-editor.org/rfc/rfc7636.html; **OAuth 2.0 Authorization Server Metadata RFC 8414**, https://www.rfc-editor.org/rfc/rfc8414.html; **OpenID Connect Core**, https://openid.net/specs/openid-connect-core-1_0.html; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring Security OAuth2 Resource Server**, https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html; **OWASP API Security Top 10**, https://owasp.org/API-Security/.

**Kết luận:** Tài liệu API có ích không dừng ở một nút **Authorize** trong Swagger. Nó phải nối đúng **client identity → token được cấp theo môi trường → scope → quyền trên resource → HTTP response → cách thử an toàn**. Khi OpenAPI, Spring Security, gateway, sandbox và quickstart cùng mô tả **một hợp đồng có thể kiểm thử**, developer tích hợp nhanh hơn mà không phải đánh đổi tenant isolation, secret safety hay tính đúng đắn của nghiệp vụ.
