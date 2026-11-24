# 401 và 403 khác nhau thế nào?

Trong API bảo vệ bằng **OAuth 2.0 access token**, hai mã HTTP dễ bị nhầm nhất là **`401 Unauthorized`** và **`403 Forbidden`**. Tên “Unauthorized” của 401 khiến nhiều người nghĩ nó luôn nói về **thiếu quyền**, nhưng theo ngữ nghĩa HTTP, 401 chủ yếu liên quan **thiếu hoặc chưa có thông tin xác thực hợp lệ cho tài nguyên đích**. Trong khi đó, 403 nói rằng server **đã hiểu request nhưng từ chối thực hiện**; với OAuth Bearer, một trường hợp điển hình là **token hợp lệ nhưng thiếu scope cần thiết**.

Bài **“401 và 403 khác nhau thế nào?”** thuộc chương **Resource server** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Bài kết nối mô hình tin cậy và vòng đời token, JWT/opaque token, access/refresh/ID token, claims, scope, audience, xác thực và phân quyền OAuth 2.0/OIDC, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

> **Nhớ nhanh:** **401**: “Request này chưa được xác thực bằng credential có thể chấp nhận tại Resource Server”; **403**: “Request bị từ chối, thường vì principal/token đã xác thực không có đủ quyền”. Đây là **mô hình thực dụng**, không phải đồng nhất tuyệt đối: RFC 9110 cho phép 403 với nhiều lý do ngoài thiếu scope; lỗi phụ thuộc Authorization Server phải được phân biệt và **không tự chuyển thành 401 của người dùng**.

## 1. Quy tắc gốc trong HTTP

**RFC 9110** quy định:

- **`401 Unauthorized`:** request **không được áp dụng** vì thiếu **authentication credentials hợp lệ** cho target resource. Server tạo response 401 **MUST** gửi ít nhất một `WWW-Authenticate` challenge áp dụng cho tài nguyên đích.
- **`403 Forbidden`:** server đã hiểu request nhưng **từ chối thực hiện**. Nếu credentials đã được gửi, server xem chúng **không đủ để cấp quyền**; client không nên lặp request với **cùng credentials** và mong kết quả khác. Server có thể sử dụng 403 cho những trường hợp không đơn thuần là thiếu role.
- **`404 Not Found`:** trong một số chính sách bảo vệ thông tin, server **MAY** dùng 404 thay 403 để **che giấu sự tồn tại của tài nguyên bị cấm**.

Tên `401 Unauthorized` là tên lịch sử của HTTP status; đừng diễn dịch nó thành “authorization đã xác định user có ít quyền”. Cần hiểu `401` trong bối cảnh **authentication challenge**, `403` trong bối cảnh **refusal/authorization policy**.

| Tình huống | HTTP thường đúng | Ý nghĩa tại API |
|---|---:|---|
| Không gửi access token tới endpoint bắt buộc Bearer | **401** | Chưa có credentials đáp ứng yêu cầu |
| Token hỏng chữ ký, hết hạn, bị revoke, sai issuer/audience | **401** | Credential không được RS chấp nhận |
| Access token hợp lệ nhưng thiếu `orders:write` | **403** | Không đủ scope cho hành động |
| Token đúng scope nhưng user không sở hữu order | **403** hoặc **404** theo policy | Object-level authorization từ chối |
| API bị chặn bởi WAF/IP/geo/legal policy | **403** hoặc status khác theo policy | Không nhất thiết là lỗi OAuth token |
| AS introspection bị timeout/503 | **Không có token verdict** | Fail closed; thường là lỗi dependency/503 |
| Request dùng sai phương thức | **405** nếu method không được hỗ trợ | Không tự quy thành lỗi auth |
| Bearer request malformed, nhiều phương thức truyền token | **400** thường phù hợp theo RFC 6750 | `invalid_request`, không phải “thiếu quyền” |

**Không lấy câu “401 = chưa login, 403 = đã login” làm quy tắc duy nhất.** Một người **đã login trên UI** vẫn có thể gửi **access token hết hạn** và nhận 401 từ API.

## 2. Authorization Server và Resource Server có trách nhiệm khác nhau

Trong OAuth 2.0:

- **Authorization Server (AS):** xác thực/ủy quyền chủ thể trong flow, phát access token, quản lý grant/refresh token/revocation, có thể cung cấp introspection.
- **Client:** ứng dụng mang access token gọi API.
- **Resource Server (RS):** API nhận token, xác minh tính hợp lệ **cho chính API**, sau đó ra quyết định quyền đối với endpoint/tài nguyên cụ thể.
- **Resource owner/subject:** user hoặc principal mà quyền được đại diện trong token, tùy grant/profile.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    participant DB as Order authorization/data

    C->>RS: GET /orders/123 + Bearer token
    RS->>RS: Parse credential/transport
    opt Token opaque hoặc cần kiểm tra trạng thái
        RS->>AS: Introspection qua authenticated HTTPS
        AS-->>RS: active=true/false hoặc dependency error
    end
    RS->>RS: Verify issuer, audience, purpose, exp, binding
    alt Token thiếu/invalid/inactive
        RS-->>C: HTTP 401 + WWW-Authenticate: Bearer
    else Token valid, thiếu scope
        RS-->>C: HTTP 403 insufficient_scope
    else Token valid, scope đủ
        RS->>DB: Check order ownership/tenant/policy
        alt Forbidden object
            RS-->>C: HTTP 403 hoặc 404 có chủ đích
        else Authorized
            RS-->>C: HTTP 200 data
        end
    end
~~~

**Hai lần kiểm tra riêng**: trước tiên **token có phải credential hợp lệ cho RS không**, sau đó **request cụ thể có được cấp quyền không**. `active:true` hoặc chữ ký JWT hợp lệ **không tự** cho phép đọc/sửa mọi order.

## 3. Authentication và authorization khác nhau ở đâu?

**Authentication (AuthN)** hỏi: “Thông tin xác thực hiện tại có chứng minh được danh tính hoặc nguồn authority mà API chấp nhận không?” Với RS OAuth, điều này gồm **kiểm tra access token** và các ràng buộc của nó.

**Authorization (AuthZ)** hỏi: “Principal/client đã xác thực có được phép thực hiện **hành động này trên tài nguyên này, tại thời điểm này** không?”

Ví dụ:

~~~text
Request:
    DELETE /orders/123
    Authorization: Bearer <ACCESS_TOKEN>

Token verification:
    signature          OK
    iss                trusted AS
    aud                orders-api
    exp                future
    token purpose      access_token
    scope              orders:read

Decision:
    token authentication succeeded
    requested DELETE requires orders:delete
    => 403 Forbidden (insufficient_scope)
~~~

Ví dụ thứ hai:

~~~text
Request:
    GET /orders/123
    Authorization: Bearer <EXPIRED_ACCESS_TOKEN>

Token verification:
    exp <= now
    => credential invalid for RS
    => 401 Unauthorized, Bearer invalid_token
~~~

**Điểm thực tế:** một request có thể vừa sai token vừa thiếu quyền. RS nên **ưu tiên loại bỏ credential invalid** trước, không parse scope của token chưa được xác minh để trả 403.

## 4. RFC 6750: `WWW-Authenticate` của Bearer Resource Server

**RFC 6750** định nghĩa cách trình **OAuth 2.0 Bearer access token** tới RS và cách trả Bearer challenge. Khi request không đủ authentication credentials, RS đáp ứng 401 với header `WWW-Authenticate` chứa scheme `Bearer`.

### 4.1. Không có access token

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
Content-Type: application/json

{"message":"Authentication required"}
~~~

**`realm`** là thông tin realm dùng để diễn giải challenge theo RS, **không phải issuer URL hay audience tự động**. Khi request hoàn toàn **không có authentication information**, RFC 6750 khuyến nghị **không kèm `error`/`error_description`**, vì chưa có lỗi token cụ thể cần giải thích.

### 4.2. Token sai hoặc đã hết hạn

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <EXPIRED_ACCESS_TOKEN>
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{"message":"Access token is not valid"}
~~~

`invalid_token` có thể bao gồm **expired, revoked, malformed hoặc credential không hợp lệ vì lý do khác**. Không cần tiết lộ đó là token của user nào, token bị thu hồi lúc nào hoặc lý do nội bộ khiến verifier từ chối.

### 4.3. Token hợp lệ nhưng thiếu scope

~~~http
POST /orders/123/cancel HTTP/1.1
Host: api.example.test
Authorization: Bearer <VALID_ORDERS_READ_TOKEN>
Content-Type: application/json

{"reason":"user-request"}
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:cancel"
Cache-Control: no-store
Content-Type: application/json

{"message":"Insufficient permission"}
~~~

`scope` trong challenge là **thông tin scope cần thiết** mà RS có thể cung cấp theo policy, **không phải quyền được tự động cấp** cho client. Nếu việc công bố required scope có thể lộ endpoint nội bộ hoặc logic nhạy cảm, cân nhắc không đưa chi tiết scope trong response công khai.

**Đừng gộp `HTTP status` và `OAuth error code` thành một trường.** `401`/`403` là status HTTP; `invalid_token`/`insufficient_scope` là giá trị tham số trong **Bearer challenge**, không phải status code riêng.

## 5. Ba lỗi Bearer tiêu biểu của RFC 6750

| Bearer `error` | Ý nghĩa trong OAuth Bearer | HTTP được khuyến nghị |
|---|---|---|
| **`invalid_request`** | Request sai cú pháp/định dạng, truyền token qua nhiều phương thức, tham số không được hỗ trợ v.v. | **400 Bad Request** |
| **`invalid_token`** | Token expired, revoked, malformed hoặc không hợp lệ vì lý do khác | **401 Unauthorized** |
| **`insufficient_scope`** | Request yêu cầu quyền cao hơn quyền access token cung cấp | **403 Forbidden** |

RFC 6750 sử dụng các từ **SHOULD** cho status ở nhiều tình huống tương ứng; đừng diễn giải bảng thành “mọi implementation bắt buộc trả đúng một mã mà không có ngoại lệ”. **HTTP semantics, security policy và provider profile** vẫn cần được xem xét.

### Token không phải Bearer?

Nếu RS hỗ trợ **DPoP** hoặc cơ chế sender-constrained token, error/challenge có thể theo **profile DPoP/mTLS** với các yêu cầu bổ sung. Không nên dùng `Bearer` challenge như một cách tự động bỏ qua proof-of-possession. Nội dung chính của bài dùng Bearer để minh họa `401/403`; với DPoP phải tham khảo RFC 9449.

## 6. 401 khi hoàn toàn không gửi token

Một endpoint chỉ nhận Bearer access token có thể nhận:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
~~~

Nếu không có phương thức xác thực khác được hỗ trợ, RS **không thể xác thực request**. Trả `401` kèm Bearer challenge là phù hợp.

**Không nên**:

- Trả `403 insufficient_scope` dù chưa có token để đọc scope.
- Trả body chứa danh sách user/session nội bộ.
- Redirect API JSON sang login HTML bằng `302` chỉ vì trình duyệt gọi endpoint; nếu là OAuth RS, response 401/Bearer challenge thường dễ hiểu và chuẩn hơn.
- Thử lấy **ID token** trong cookie của frontend rồi tự coi là API access token khi contract không cho phép.

Một SPA/BFF có thể chuyển người dùng sang login **ở tầng ứng dụng**, nhưng **API RS** vẫn nên truyền đạt lỗi authentication theo giao thức đã chọn.

## 7. 401 khi access token sai chữ ký, issuer hoặc algorithm

Với JWT access token, RS chỉ nên tin claims **sau khi verify mật mã và profile đúng**:

| Kiểm tra | Ví dụ lỗi | Kết luận tại RS |
|---|---|---|
| **JWS signature** | Signature bị sửa hoặc key lạ | **401** |
| **Allowed `alg`** | Token `alg=none` trong profile yêu cầu JWS | **401** |
| **Trusted `iss`** | Token từ issuer/tenant khác | **401** |
| **`aud`** | Token cấp cho Billing, gửi Orders | **401** |
| **`typ`/purpose** | ID token dùng như API access token | **401** |
| **`exp`/`nbf`** | Token hết hạn/chưa hiệu lực | **401** |
| **Revocation/`jti`** | Token đã bị revoke theo policy | **401** |
| **Sender proof** | DPoP/mTLS binding/proof không đạt | Từ chối theo token/profile; không cấp access |

Một JWT **được ký đúng bởi AS**, nhưng `aud=billing-api`, **không phải credential hợp lệ cho Orders API**. Vì vậy lỗi audience là **401 invalid_token** thường phù hợp; **không** coi đây là 403 thiếu scope của Orders.

**`client_id` hay `sub` khớp user không thay `aud`**. Token của RS khác không được dùng để chạy thử authorization rule cho RS hiện tại.

## 8. 401 khi token hết hạn, bị thu hồi hoặc không có hiệu lực

Access token có thể invalid dù trước đó từng hợp lệ:

- **`exp` đã đến/qua**; không chấp nhận tại `now >= exp`.
- **`nbf` còn trong tương lai**, token chưa có hiệu lực.
- Token bị AS/incident handler **revoke** và RS có cơ chế nhìn thấy revocation.
- **Opaque token introspection** trả `{"active":false}`.
- Token có chữ ký hợp lệ nhưng **token family/grant/session version** đã bị policy invalidated và RS thực thi version check.
- Token sender-constrained không đi kèm proof hợp lệ theo profile.

~~~json
{
  "active": false
}
~~~

Đó là một introspection verdict hợp lệ của AS, thường khiến RS từ chối token và trả 401 cho client nếu endpoint cần Bearer. Tuy nhiên, **`active:false` không nhất thiết cho biết token đã hết hạn**; AS có thể trả false khi token không tồn tại, bị revoke hoặc RS không được phép biết trạng thái token.

### Độ trễ thu hồi

Nếu RS verify **JWT offline** và không kiểm tra denylist/epoch, việc revoke refresh-token family tại AS **không tự khiến access token JWT đã cấp ngừng hoạt động** trước `exp`. Nếu RS cache kết quả introspection `active:true`, có thể tồn tại **cửa sổ stale token** cho tới khi TTL/invalidation có hiệu lực.

Khi đã xác định token invalid, RS trả 401. Nhưng **đừng tuyên bố mọi RT/AT đã ngừng có hiệu lực ngay** nếu hệ thống phân tán chưa bảo đảm propagation.

## 9. 403 khi token hợp lệ nhưng thiếu scope

Giả sử AS cấp token cho Orders API:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read profile",
  "client_id": "orders-web",
  "exp": 1800003600
}
~~~

*JSON chỉ là payload minh họa, không phải JWT ký thật; các mốc thời gian phải so với clock tại request.*

| Request | Scope cần | Quyết định nếu token hợp lệ |
|---|---|---|
| `GET /orders/123` | `orders:read` | Qua scope check, **vẫn cần ACL object** |
| `POST /orders` | `orders:write` | **403 insufficient_scope** |
| `POST /orders/123/cancel` | `orders:cancel` | **403 insufficient_scope** |
| `GET /account/profile` | `profile` và đúng audience/API | Có thể qua scope nếu audience/policy phù hợp |
| `GET /admin/orders` | Admin policy riêng | Không được suy từ `orders:read` |

**Scope không tự là authorization hoàn chỉnh.** Nó thường biểu diễn quyền được AS cấp cho client/token; API còn phải kiểm tra **tenant, ownership, roles, ABAC/policy động**.

### So scope chính xác

~~~java
// SAI: "orders:read:any" chứa "orders:read".
boolean allowed = scopeText.contains("orders:read");
~~~

Tách scope thành các phần tử **phân cách theo dấu cách** theo contract, rồi so sánh **chính xác**. Framework Spring Security thường map `scope`/`scp` sang authority như `SCOPE_orders:read`; phải xác minh cách AS phát claims và converter của ứng dụng.

## 10. 403 khi object-level authorization từ chối

Một access token có `scope=orders:read` và `aud=orders-api` vẫn không đồng nghĩa được đọc **mọi đơn hàng**.

~~~text
Authenticated subject: user-42
Token audience:       orders-api
Token scope:          orders:read
Request:              GET /orders/987
Order 987 owner:      user-99
------------------------------------------------
Token valid?          YES
Scope valid?          YES
Object authorized?    NO
Result:               403 hoặc 404 theo privacy policy
~~~

Đây là **Broken Object Level Authorization (BOLA/IDOR)** nếu API chỉ kiểm tra scope rồi bỏ qua **ownership/tenant/relationship**.

**Mẫu kiểm tra theo lớp**:

1. Token có hợp lệ cho RS không? Nếu không → 401.
2. Scope đủ cho hành động trên API không? Nếu không → 403 `insufficient_scope`.
3. Principal có quyền với **object đang truy vấn** không? Nếu không → 403 hoặc 404 được định nghĩa.
4. Dữ liệu có đáp ứng trạng thái nghiệp vụ không (order locked, archived, conflict)? Có thể có status khác như 409.
5. Nếu tất cả đạt → xử lý và trả response thành công.

**Không đồng nhất 403 object ACL với OAuth `insufficient_scope`.** Nếu token có scope đúng nhưng owner sai, `WWW-Authenticate: Bearer error="insufficient_scope"` có thể đánh lạc hướng client, khiến client xin thêm scope dù lỗi thực là **object policy**.

## 11. Khi nào dùng 404 thay vì 403?

RFC 9110 cho phép server trả **404 Not Found** để **che giấu sự tồn tại của tài nguyên bị cấm**. Ví dụ:

- User A gọi `GET /private-documents/doc-of-user-B`.
- Nếu trả 403 cho tài liệu tồn tại nhưng 404 cho tài liệu không tồn tại, attacker có thể **liệt kê ID tồn tại**.
- API có thể trả **404 cho cả tài liệu không tồn tại lẫn tài liệu mà A không được phép biết**.

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store

{"message":"Resource not found"}
~~~

**Đây là lựa chọn privacy policy, không phải quy tắc “mọi thiếu quyền đều 404”.**

- Với endpoint admin, 403 có thể giúp người quản trị hiểu thiếu quyền.
- Với tài nguyên bí mật, 404 che thông tin tồn tại có thể tốt hơn.
- Policy phải nhất quán về **status, message, thời gian xử lý và metadata** để không tạo leak mới.
- 404 chỉ ẩn existence; **không thay quyền truy cập** hoặc cho phép server bỏ check authentication.
- Với request chưa có token, RS có thể cần 401 challenge trước khi biết được authorization; thiết kế “concealment” phải cân nhắc endpoint/security requirements.

## 12. Phân biệt 400, 401, 403, 404, 405, 429 và 503

| Status | Mô tả phổ biến | Ví dụ trong OAuth RS |
|---|---|---|
| **400 Bad Request** | Request không đúng cú pháp/contract | Bearer token gửi đồng thời header và query; `invalid_request` |
| **401 Unauthorized** | Authentication credentials thiếu/không được chấp nhận | Missing, invalid, expired, wrong-audience token |
| **403 Forbidden** | Request bị từ chối sau hiểu yêu cầu | Valid token thiếu scope; object ACL deny; business access policy |
| **404 Not Found** | Tài nguyên không tồn tại hoặc cố ý che existence | Document thuộc tenant khác được ẩn |
| **405 Method Not Allowed** | Method không được hỗ trợ | POST endpoint chỉ hỗ trợ GET, kèm `Allow` theo HTTP |
| **409 Conflict** | Trạng thái tài nguyên xung đột yêu cầu | Order đã cancel, không còn chuyển trạng thái được |
| **429 Too Many Requests** | Đang bị rate limit | Client/API quá quota, thường có chính sách retry |
| **500 Internal Server Error** | Server xử lý lỗi không dự kiến | Exception trong policy service |
| **503 Service Unavailable** | Dịch vụ/phụ thuộc tạm không khả dụng | Không truy cập được AS introspection theo policy |

**Không ép mọi lỗi API thành 401/403**. Một AS outage không tự chứng minh token của người dùng invalid; một bug database không có nghĩa user thiếu scope. Phân loại chính xác giúp **không che giấu sự cố bảo mật hoặc vận hành**.

### HTTP status của AS không phải status của client

Nếu RS gọi introspection endpoint và AS trả **401 vì RS credential sai**, đó là **lỗi authentication giữa RS và AS**. RS không nên chuyển nguyên xi thành “user credential sai” rồi buộc user đăng nhập lại. Đây là **sự cố integration/dependency**, cần fail closed, log an toàn và phản hồi cho client theo availability policy.

## 13. Opaque token và RFC 7662: active khác authorization

Với **opaque token**, RS không tự đọc JWT payload mà có thể gọi AS qua **RFC 7662 Token Introspection**.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <RS_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

**AS trả 200 với inactive**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"active":false}
~~~

RS coi token inactive và với Bearer-protected endpoint trả **401** cho client.

**AS trả 200 với active**:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "token_type": "Bearer",
  "exp": 1800003600,
  "client_id": "orders-web",
  "sub": "user-42"
}
~~~

RS phải kiểm tra token purpose, issuer, audience, expiry, scope/claims và quyền object. Chỉ **`active:true`** chưa đủ để cho phép.

### Introspection failure không phải inactive token

| Kết quả từ AS | Điều RS biết | Cách xử lý |
|---|---|---|
| HTTP 200 + `{"active":false}` | AS nói token không active/RS không được biết | Deny token; 401 thường phù hợp |
| HTTP 200 + `{"active":true,...}` | AS nói active trong context | Tiếp tục kiểm tra policy; có thể 403 |
| HTTP 401 từ AS | RS credentials sai/thiếu | Fail closed, **dependency failure**, không suy user token invalid |
| HTTP 500/503, timeout/TLS error | **Không có verdict** | Fail closed; thường 503/500 phía RS |
| HTTP 200 nhưng thiếu `active`, kiểu string | Response không hợp lệ | Fail closed; protocol error, không ép boolean |

**`token_type_hint=access_token` chỉ là gợi ý lookup**; không chứng minh credential là access token. RS cần hợp đồng AS về token-purpose (không nhận refresh/ID token tại API).

## 14. JWT access token: tối thiểu cần xác minh gì trước khi trả 403?

Với JWT access token, ví dụ profile **RFC 9068**, trước khi đọc scope để quyết định thiếu quyền, RS phải xác minh:

1. **Header `typ`** đúng access-token profile được hỗ trợ; không chấp nhận ID token/refresh token như API AT.
2. **`alg`** nằm trong allowlist phù hợp và không cho `none`/algorithm confusion.
3. **Chữ ký** đúng key từ JWKS của **issuer tin cậy**; không lấy `jku`/`x5u` từ JWT untrusted để tìm khóa.
4. **`iss`** match issuer cấu hình; dùng cache/JWKS theo issuer và tenant, không chỉ `kid`.
5. **`aud`** chứa **audience Resource Server hiện tại**, exact string.
6. **`exp`**, `nbf` và các điều kiện thời gian theo profile; kiểm tra mốc chính xác.
7. **`sub`**, `client_id`, `iat`, `jti` và các claims bắt buộc theo profile/AS–RS contract.
8. **Revocation/epoch** khi hệ thống yêu cầu chặn trước `exp`.
9. **`cnf`/DPoP/mTLS proof** nếu token được ràng buộc sender.
10. **Scope/authorization details** và object/tenant policy cho request cụ thể.

~~~mermaid
flowchart TD
    A["HTTP request tới Orders API"] --> B{"Bearer credential có mặt/hợp lệ cú pháp?"}
    B -->|"Không"| U["401 + Bearer challenge"]
    B -->|"Có"| C{"JWT verify / opaque introspect thành công?"}
    C -->|"Không: token invalid"| U
    C -->|"Không: AS dependency/timeout"| S["Fail closed: 503/500 theo policy"]
    C -->|"Có"| D{"iss, aud, token use, exp/nbf, binding đạt?"}
    D -->|"Không"| U
    D -->|"Có"| E{"Scope/route permission đủ?"}
    E -->|"Không"| F["403 insufficient_scope"]
    E -->|"Có"| G{"Tenant/object ACL cho phép?"}
    G -->|"Không"| H["403 hoặc 404 conceal"]
    G -->|"Có"| OK["2xx / tiếp tục business processing"]
~~~

**Quan trọng:** một JWT có chữ ký đúng nhưng **sai audience**, không được “coi như đã xác thực” rồi trả 403 vì thiếu scope; token đó **không phải credential hợp lệ dành cho RS này**.

## 15. Access token, ID token, refresh token và token purpose confusion

Một lỗi dễ dẫn đến phân loại status sai là cố gắng authorize bằng **token không đúng mục đích**.

| Credential được gửi tới Orders API | Ý nghĩa thật | Xử lý |
|---|---|---|
| Access token dành Orders | Credential API hợp lệ **nếu các checks khác đạt** | 200/403 tùy authorization |
| Access token dành Billing | Credential dành Resource Server khác | **401 invalid_token** |
| OIDC ID token `aud=orders-web` | Xác thực user với OIDC client/RP, **không** gọi API | **401 invalid_token** |
| Refresh token | Dùng tại AS `/token` để xin AT mới | **401 invalid_token** |
| Authorization code / device code | Dùng ở OAuth grant endpoint | **401 invalid_token** |
| JWT bị sửa header/payload | Không bảo đảm integrity/signature | **401 invalid_token** |
| Token active đúng RS nhưng không có scope | Principal/token hợp lệ nhưng không đủ hành động | **403 insufficient_scope** |

**`token_type=Bearer` trong OAuth token response không chứng minh credential là access token đúng RS.** Opaque introspection `active:true` với refresh token còn sống cũng không cho phép dùng refresh token gọi API.

## 16. DPoP/mTLS: status phải theo credential và proof

Với **sender-constrained access token**:

- **DPoP (RFC 9449):** client gửi proof JWT và token; RS kiểm tra binding/`ath`, `htu`, `htm`, thời gian, `jti` và các điều kiện profile. Proof sai → credential presentation không hợp lệ; xử lý challenge/error theo DPoP profile.
- **mTLS-bound AT (RFC 8705):** RS kiểm tra certificate binding với token; bearer string không đủ nếu thiếu certificate phù hợp.
- **Audience/scope vẫn phải kiểm tra**; proof đúng không biến token Billing thành token Orders.

~~~text
Token:
    aud = billing-api
    cnf = thumbprint of client's public key

Request to Orders:
    DPoP proof cryptographically valid for HTTP target
    BUT aud != orders-api

Result:
    deny invalid token for this RS;
    valid proof does not grant cross-resource access.
~~~

Không áp dụng mù quáng `WWW-Authenticate: Bearer` cho mọi DPoP response. Với PoP, resource server nên thực hiện đúng profile/nonce/challenge đã thống nhất, tránh tạo bypass bằng fallback sang Bearer.

## 17. Scope, role, policy và object ACL không phải một thứ

**Scope** thường là quyền cấp cho **client/token** ở AS. **Role** có thể là thuộc tính user hay service. **Object-level ACL/ABAC** là quyết định quyền ở RS theo resource cụ thể.

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Token validation | Credential có hợp lệ cho RS? | `aud=orders-api` |
| Scope enforcement | Token được phép hành động gì? | `orders:read` |
| Role/RBAC | Principal có vai trò phù hợp? | `ROLE_SUPPORT` |
| Tenant context | Token/subject có thuộc tenant đang xử lý? | `tenant=shop-42` |
| Object ACL/ABAC | Có quyền với object cụ thể? | User là owner của order 123 |
| Business state | Tài nguyên có cho phép thao tác lúc này? | Order đã ship, không cancel được |

Một token đúng scope nhưng user khác chủ sở hữu vẫn **403/404**, không phải 401. Một user có role admin nhưng đưa **token sai audience** vẫn **401**.

**Không tin `roles`/`scope` lấy từ payload JWT chưa xác minh**. Không dùng `contains("orders:read")` trên scope string thay vì tách exact token. Không tự xem mọi `403` là cơ hội xin thêm OAuth scope: object/tenant policy có thể không thay đổi dù grant thêm scope.

## 18. Spring Security 6: cấu hình Resource Server JWT và scope

Spring Security thường tách **authentication failure** và **authorization failure**. Ví dụ cho một Orders API dùng **JWT Bearer**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMethodSecurity
public class OrdersApiSecurity {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        http
            // Filter chain RIÊNG cho API chỉ nhận Bearer token,
            // không xác thực request bằng cookie session.
            .securityMatcher("/orders/**")
            .csrf(csrf -> csrf.disable())
            .cors(withDefaults())
            .authorizeHttpRequests(auth -> auth
                // CORS preflight không mang Bearer token.
                .requestMatchers(HttpMethod.OPTIONS, "/orders/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(withDefaults())
            );

        return http.build();
    }
}
~~~

**Giả định:** đây là **filter chain riêng cho `/orders/**` chỉ nhận Bearer token trong `Authorization` header, không hỗ trợ cookie-authenticated requests**. Vì thế, chỉ trong chain này mới tắt CSRF; **không được vô hiệu CSRF toàn ứng dụng nếu còn session cookie/browser endpoints**. Cấu hình CORS cho origins/methods/headers được phép phải được thiết lập riêng; `permitAll` với `OPTIONS` không có nghĩa chấp nhận mọi origin. Những URL ngoài `/orders/**` cần chain/policy riêng. App cũng phải có `JwtDecoder` đáng tin (issuer, audience, key/alg/profile); Spring authorities được map từ `scope` của AS thành `SCOPE_orders:read`/`SCOPE_orders:write` theo converter phù hợp.

### Hành vi mong muốn

- **Không token/invalid token:** Spring Resource Server có thể dùng **Bearer authentication entry point**, trả **401** và challenge.
- **Token valid nhưng thiếu authority:** **access denied**, thường **403** và trong Bearer flow có thể dùng `insufficient_scope`.
- **Token valid, đủ scope nhưng order thuộc user khác:** application/method authorization **từ chối** 403 hoặc 404 theo policy.

**Framework chỉ có thể làm đúng nếu bạn cấu hình validation đúng**. Một decoder chỉ kiểm tra signature/issuer/time nhưng không validate audience để mặc định sẽ tạo lỗ hổng cross-resource, dù API trả 401/403 đúng về mặt hình thức.

## 19. Spring Security: validate issuer, audience và thời gian

Ví dụ Spring Security 6.x dùng `NimbusJwtDecoder` và `OAuth2TokenValidator` để kiểm tra audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String AUDIENCE =
            "https://orders-api.example.test";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Token audience mismatch",
                                null
                        )
                );

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(ISSUER),
                        audienceValidator
                )
        );

        return decoder;
    }
}
~~~

**Ranh giới ví dụ:**

1. Decoder phải **verify chữ ký bằng key của issuer tin cậy**, chỉ chấp nhận alg/key type được cho phép và có xử lý key rotation.
2. `createDefaultWithIssuer` giữ checks theo framework; khi thêm custom validator **không được bỏ** issuer/expiry verification.
3. **Kiểm tra token purpose/`typ`** (ví dụ `at+jwt` theo RFC 9068) bằng đúng API của phiên bản thư viện/AS profile đang dùng. Ví dụ chưa tự bổ sung mọi kiểm tra này.
4. `aud` phải là **Orders API**, không phải OAuth `client_id`/frontend origin. Với multi-issuer, phải pin issuer-audience relationship.
5. Không lấy issuer hoặc URL JWKS từ untrusted token/header/query string.
6. Code này **không kiểm tra scope/role/object permission**, việc đó nằm ở filter/method security như ví dụ trước.

**Không sửa lỗi sai audience bằng cách tắt audience validation**; hãy sửa **AS-issued audience, resource registration hoặc trusted RS configuration**.

## 20. Spring Security: object-level authorization trong service

Scope enforcement ở URL chỉ là một lớp. Một endpoint có thể dùng method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrdersController {
    private final OrderService orderService;

    public OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders:read') and " +
        "@orderAccess.canRead(authentication, #orderId)"
    )
    @GetMapping("/{orderId}")
    public OrderView getOrder(@PathVariable String orderId) {
        return orderService.findView(orderId);
    }
}
~~~

**Giả định** `@EnableMethodSecurity` đã được bật và `orderAccess` là bean đáng tin, tự tra object/tenant/ACL từ dữ liệu server thay vì lấy `ownerId` do caller khai. `OrderService`/`OrderView` là type ứng dụng minh họa, **không phải class Spring có sẵn**.

**Đừng đánh lừa 403 thành 401:** khi `@orderAccess.canRead` trả false vì user không có quyền với đơn hàng, đó là **authorization denial**, không phải lỗi mật mã của token. Nếu cần chống lộ existence, service/controller có thể áp 404 theo policy thay vì mặc định 403.

**Không dùng URL rule `/orders/**` làm bằng chứng đã chặn mọi đường khác**: xét method, internal endpoints, GraphQL resolvers, batch operations và admin APIs. Deny-by-default ở application layer vẫn quan trọng.

## 21. Spring Security opaque token: introspection và chính sách

Với opaque access token, Spring Resource Server có thể được cấu hình (tùy Spring Boot version) qua `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: "INJECT_FROM_SECRET_MANAGER"
~~~

**Placeholder không phải secret thật.** Credential RS phải được quản lý bởi secret manager/environment và không commit vào repo.

### Luồng xử lý

- AS trả `active:false` → introspector từ chối token → RS **401**.
- AS trả `active:true` nhưng token không có `SCOPE_orders:write` → authorization filter → **403**.
- AS trả `active:true` nhưng `aud` sai hoặc token purpose là refresh/ID → adapter/validator phải reject như token không hợp lệ → **401**.
- Introspection AS trả 401 vì credential **RS** sai, hoặc TLS timeout → đây là lỗi kết nối/xác thực giữa RS và AS, phải **fail closed** và cần vận hành xử lý; **không tự khẳng định token của user invalid**.

**Spring default introspection không tự biết tất cả audience/purpose policy của sản phẩm.** Bổ sung validator/introspector wrapper theo contract để kiểm tra issuer, audience, usage, exp và metadata cần thiết, hoặc bảo đảm tương đương từ AS theo resource-specific introspection.

## 22. Java 17: decision table như một hàm thuần

Để không lẫn authentication và authorization, có thể tách verdict **token trust** khỏi verdict **scope/object policy**. Đoạn Java 17 dùng `Clock` và immutable records làm ví dụ **decision model**, không tự verify JWT hay gọi introspection endpoint.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class ResourceServerDecision {
    public enum TokenVerdict {
        MISSING, INVALID, ACTIVE, DEPENDENCY_UNAVAILABLE
    }

    public enum ApiDecision {
        UNAUTHORIZED_401,
        FORBIDDEN_403_SCOPE,
        FORBIDDEN_403_OBJECT,
        SERVICE_UNAVAILABLE_503,
        ALLOW
    }

    public record VerifiedToken(
            String issuer,
            Set<String> audiences,
            Set<String> scopes,
            Instant expiresAt,
            String purpose
    ) {}

    public record Input(
            TokenVerdict verdict,
            VerifiedToken token,
            String expectedIssuer,
            String expectedAudience,
            String requiredScope,
            boolean objectPermissionGranted
    ) {
        public Input {
            Objects.requireNonNull(verdict);
            Objects.requireNonNull(expectedIssuer);
            Objects.requireNonNull(expectedAudience);
            Objects.requireNonNull(requiredScope);
        }
    }

    public static ApiDecision decide(Input in, Clock clock) {
        if (in.verdict() == TokenVerdict.DEPENDENCY_UNAVAILABLE) {
            return ApiDecision.SERVICE_UNAVAILABLE_503;
        }
        if (in.verdict() != TokenVerdict.ACTIVE) {
            return ApiDecision.UNAUTHORIZED_401;
        }

        VerifiedToken t = in.token();
        if (t == null
                || !in.expectedIssuer().equals(t.issuer())
                || t.audiences() == null
                || !t.audiences().contains(in.expectedAudience())
                || !"access_token".equals(t.purpose())
                || t.expiresAt() == null
                || !clock.instant().isBefore(t.expiresAt())) {
            return ApiDecision.UNAUTHORIZED_401;
        }

        if (t.scopes() == null
                || !t.scopes().contains(in.requiredScope())) {
            return ApiDecision.FORBIDDEN_403_SCOPE;
        }

        if (!in.objectPermissionGranted()) {
            return ApiDecision.FORBIDDEN_403_OBJECT;
        }
        return ApiDecision.ALLOW;
    }

    public static void main(String[] args) {
        Clock now = Clock.fixed(
                Instant.parse("2026-11-23T10:00:00Z"),
                java.time.ZoneOffset.UTC
        );
        VerifiedToken readOnly = new VerifiedToken(
                "https://auth.example.test",
                Set.of("https://orders-api.example.test"),
                Set.of("orders:read"),
                Instant.parse("2026-11-23T10:15:00Z"),
                "access_token"
        );

        Input input = new Input(
                TokenVerdict.ACTIVE,
                readOnly,
                "https://auth.example.test",
                "https://orders-api.example.test",
                "orders:write",
                true
        );

        System.out.println(decide(input, now));
        // FORBIDDEN_403_SCOPE
    }

    private ResourceServerDecision() {}
}
~~~

### Đừng dùng decision model làm thư viện authentication

- `VerifiedToken` **chỉ được tạo từ adapter tin cậy** sau JWT signature/profile validation hoặc authenticated introspection. Nếu tạo trực tiếp từ JSON body do client gửi, **không có bảo mật**.
- `purpose="access_token"` là **kết quả phân loại đáng tin**, không phải claim do browser tự đặt.
- Ví dụ chưa check `nbf`, `iat`, sender proof, signature, revocation, tenant identity, network errors, scope mapping; những bước đó thuộc verifier/adapter.
- `objectPermissionGranted` phải đến từ **RS policy/DB**, không từ HTTP request payload.
- `DEPENDENCY_UNAVAILABLE` minh họa fail-closed 503; không bảo rằng mọi mạng outage luôn là 503 trong mọi framework.
- `403_SCOPE` khác `403_OBJECT` để sinh **Bearer insufficient_scope** chỉ cho đúng trường hợp, tránh lộ ACL nội bộ.

## 23. Frontend SPA/BFF nên phản ứng thế nào với 401 và 403?

Một client thường cần hành vi khác nhau:

| Status | Cách hiểu ở client | Hành động phù hợp |
|---|---|---|
| **401** | Access token thiếu/hết hạn/không được RS chấp nhận | Có thể thử **refresh một lần** nếu có RT/session và flow cho phép; nếu vẫn 401 → login lại |
| **403** | Request bị từ chối theo authorization policy | Không retry access token vô hạn; hiển thị thiếu quyền/không được truy cập |
| **404** | Không tìm thấy tài nguyên hoặc bị ẩn | Hiển thị thông điệp generic, không đoán quyền |
| **429** | Quota/rate limit | Backoff theo policy/`Retry-After` nếu có |
| **503** | API/auth dependency tạm unavailable | Retry có giới hạn khi phù hợp; không reset credentials của user vô cớ |

### JavaScript fetch ví dụ

~~~javascript
async function fetchOrder(orderId, accessToken, refreshOnce) {
  const url = "/api/orders/" + encodeURIComponent(orderId);

  const request = (token) => fetch(url, {
    method: "GET",
    headers: { Authorization: "Bearer " + token }
  });

  let response = await request(accessToken);

  if (response.status === 401) {
    // Chỉ refresh khi client/session thực sự có flow hợp lệ.
    // refreshOnce phải single-flight để tránh RT reuse races.
    const freshToken = await refreshOnce();
    if (freshToken) {
      response = await request(freshToken);
    }
    if (response.status === 401) {
      throw new Error("Please authenticate again");
    }
  }

  if (response.status === 403) {
    throw new Error("You do not have permission");
  }
  if (response.status === 404) {
    throw new Error("Order not found");
  }
  if (response.status === 503) {
    throw new Error("Service temporarily unavailable");
  }
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}
~~~

**Giới hạn ví dụ:** không xử lý toàn bộ refresh failure, retries, rate limits, cancellation hoặc body cloning. `refreshOnce` phải do một **auth/session module** đáng tin quản lý, không gửi raw refresh token vào frontend nếu kiến trúc dùng BFF.

### Không tự động refresh vô hạn

Nếu 401 vì **wrong issuer/audience**, refresh cùng sai resource sẽ tạo token mới **vẫn sai**; cần sửa cấu hình AS/client. Nếu 401 vì revoke/compromise, refresh có thể trả `invalid_grant`; client cần **reauthenticate** thay vì chạy vòng vô hạn. 403 do thiếu scope có thể cần **consent mới/step-up/quy trình yêu cầu quyền**, không phải luôn gọi refresh token cũ.

## 24. OAuth token endpoint `invalid_grant` khác 401 tại Resource Server

Dễ nhầm ba nơi:

| Nơi | Request | Kết quả thường gặp |
|---|---|---|
| **AS authorization endpoint** | Browser login/consent | Redirect, user interaction, OAuth errors |
| **AS token endpoint** | `grant_type=refresh_token` với RT hết hạn | Thường **400** + JSON `invalid_grant` |
| **AS introspection endpoint** | RS xác thực bằng credential sai | **401** từ AS tới **RS**, không phải user API |
| **Resource Server API** | Bearer AT hết hạn/invalid | **401** + Bearer `invalid_token` |
| **Resource Server API** | Bearer AT valid nhưng thiếu scope | **403** + Bearer `insufficient_scope` |

Ví dụ token endpoint failure không được nhầm với Bearer challenge:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_grant"}
~~~

`invalid_grant` ở AS thường báo refresh/authorization grant không hợp lệ, hết hạn hoặc bị revoke theo policy. Nó **không thay thế** `WWW-Authenticate: Bearer` tại RS.

## 25. Browser cookies, CORS, CSRF và status không tự nói rõ nguyên nhân

Một app dùng **session cookie** thay vì Bearer access token có thể trả 401/403 qua cơ chế khác:

- Session cookie thiếu/hết hạn → web backend có thể trả 401 hoặc redirect login (tùy contract browser UI/API).
- Session hợp lệ nhưng thiếu quyền → 403/404.
- **CSRF token sai hoặc thiếu** → Spring Security thường trả **403**, dù user có session hợp lệ. Đó không phải `insufficient_scope` của OAuth.
- **CORS preflight** bị chặn → browser có thể chỉ hiện **CORS error**, JavaScript không luôn nhận status/body của response; đừng kết luận access token invalid.
- Browser gửi fetch tới khác origin nhưng quên `credentials:"include"` → session cookie có thể không được gửi, dẫn tới 401.
- Cookie `SameSite=Lax/Strict` bị loại ở cross-site fetch/POST → browser không gửi cookie; API có thể nhìn request như anonymous và trả 401.

### `OPTIONS` preflight không phải bearer-protected business request

Với API dùng CORS, request `OPTIONS` preflight thường **không mang Bearer token** của actual request. Gateway/security filter cần xử lý preflight theo policy CORS, **không vô tình yêu cầu access token cho mọi OPTIONS** khiến legitimate browser requests thất bại trước bước auth.

**CSRF 403 và OAuth scope 403 cần phân biệt trong telemetry/exception handlers**. Không trả `WWW-Authenticate: Bearer error="insufficient_scope"` nếu nguyên nhân thật là thiếu CSRF token.

## 26. API Gateway, service mesh và status mapping

Trong hệ microservices:

~~~text
Browser/App
   |
   v
API Gateway (JWT check, route policy)
   |
   +--> Orders API (object authorization)
   |
   +--> Billing API (resource riêng)
   |
   +--> Admin API (role/tenant policy)
~~~

Gateway có thể trả:

- **401** khi Bearer token thiếu, sai signature, issuer, audience cho route hoặc hết hạn.
- **403** khi route yêu cầu scope client không có.
- **403** khi WAF/IP block, **không liên quan OAuth scope**.
- **503/502/504** khi backend/auth dependency lỗi, theo hạ tầng; không chuyển thành `invalid_token` không có căn cứ.

Downstream service có thể trả **403/404** vì object ACL ngay cả khi gateway đã xác minh JWT.

### Những lỗi mapping cần tránh

1. Gateway kiểm tra chữ ký nhưng **quên audience theo từng route**; token Billing có thể lọt sang Orders.
2. Gateway biến mọi downstream `403` thành `401` khiến frontend refresh token không cần thiết.
3. Backend trả 401 vì bị mất trusted auth headers do proxy, nhưng UI hiểu “user logout”.
4. Gateway thêm `WWW-Authenticate` ở response 403 bất kể nguyên nhân WAF hay business ACL.
5. Browser có thể gọi backend trực tiếp bypass gateway; backend không enforce trust boundary.
6. Mỗi node cache JWKS chỉ theo `kid` mà không theo issuer/tenant.

**Quyết định token invalid ở đúng ranh giới xác minh**, quyết định authorization ở RS/service; truyền **reason categories** nội bộ bảo vệ, không lộ claims/credentials thô ra ngoài.

## 27. Security information disclosure: trả lỗi đủ dùng, không tiết lộ bí mật

Lỗi 401/403 là một phần **API contract và attack surface**:

- Không trả raw access token, refresh token, session cookie, `Authorization` header, JWT payload đầy đủ, `jti` nhạy cảm hoặc PII.
- Không tiết lộ liệu user B có order nào thông qua sự khác biệt thông báo/status có thể dò.
- Không công bố policy nội bộ quá chi tiết, ví dụ “user 42 không thuộc nhóm fraud-investigation-vip”.
- Nếu cung cấp `scope` trong `insufficient_scope`, chỉ công bố scope mà client được phép biết, không rò tên quyền nội bộ cao cấp.
- Dùng thông điệp generic và correlation ID không chứa credential.

### 401 có nhất thiết cần `WWW-Authenticate`?

**Theo RFC 9110, một server phát 401 MUST kèm ít nhất một challenge phù hợp**. Trong RS Bearer, điều đó thường là `WWW-Authenticate: Bearer ...`. Nếu 401 được trả bởi reverse proxy/framework, kiểm tra **header thực tế** và khả năng proxy đã xóa/ghi đè challenge.

### 403 có cần `WWW-Authenticate`?

Không phải **mọi 403** đều cần Bearer challenge. Với **`insufficient_scope` theo RFC 6750**, dùng challenge có `error="insufficient_scope"` thường hữu ích; với object/tenant ACL deny hoặc WAF, một response 403 generic có thể phù hợp hơn.

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You cannot access this resource."
}
~~~

**`application/problem+json`** là format Problem Details theo **RFC 9457**, không phải yêu cầu bắt buộc của RFC 6750. Nếu body định dạng khác, status và Bearer challenge vẫn phải đúng theo contract.

## 28. Case study: bốn request tới Orders API

Giả định:

- Trusted issuer: `https://auth.example.test`.
- Expected audience: `https://orders-api.example.test`.
- Read scope: `orders:read`; cancel scope: `orders:cancel`.
- User `U42` có quyền đọc Order `123` nhưng không được đọc Order `987` của user khác.

### Case A — Không có token

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không có credential. Không gắn `insufficient_scope`.

### Case B — Token hết hạn

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "sub": "U42",
  "scope": "orders:read",
  "exp": 1800000000
}
~~~

Giả sử `now=1800000001`, token đã hết hạn. RS **401 invalid_token**, dù scope và audience đúng. Đừng trả 403 chỉ vì cuối cùng endpoint cũng cần quyền.

### Case C — Token valid nhưng thiếu scope

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "sub": "U42",
  "scope": "orders:read",
  "exp": 1800003600
}
~~~

Giả sử `now=1800000100` và request là `POST /orders/123/cancel`. Token hợp lệ, nhưng thiếu `orders:cancel` → **403 insufficient_scope**.

### Case D — Token valid, đúng scope, sai owner

Cùng token ở Case C, request `GET /orders/987`:

~~~text
Access token valid                 YES
Audience orders-api               YES
Scope orders:read                 YES
Order 987 belongs to U42          NO
Result                            403 or 404 based on privacy policy
~~~

Không nên trả `insufficient_scope` vì token đã có `orders:read`. **Lý do là quyền trên object**.

### Case E — Token cấp Billing gửi Orders

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "https://billing-api.example.test",
  "sub": "U42",
  "scope": "orders:read",
  "exp": 1800003600
}
~~~

Chữ ký AS có thể hợp lệ, scope có vẻ đủ, nhưng audience **không phải Orders RS** → **401 invalid_token**.

### Case F — AS outage khi introspect

Token opaque chưa được RS xác thực. RS gọi introspection, AS timeout. Đó là **không có verdict**, không phải `active:false`. RS **không cho truy cập**, thường **503** theo availability policy, và cảnh báo đội vận hành. Client không nên xóa toàn bộ phiên chỉ vì có outage.

**Kết luận case:** thứ tự xác minh có ý nghĩa: **credential validity → scope → object authorization → business operation**. Status giúp client xử lý đúng nhưng không thay kiểm tra bảo mật.

## 29. Observability: theo dõi đúng nguyên nhân bên trong

Không nên ghi mọi request bị từ chối với một event `AUTH_FAILED` duy nhất.

| Event category nội bộ | HTTP có thể trả | Ý nghĩa cho vận hành |
|---|---|---|
| `AUTH_MISSING_CREDENTIAL` | 401 | Anonymous request tới protected route |
| `AUTH_INVALID_SIGNATURE` | 401 | Token hỏng hoặc key/issuer sai |
| `AUTH_EXPIRED_TOKEN` | 401 | TTL hết hạn, client refresh issue |
| `AUTH_WRONG_AUDIENCE` | 401 | Token dành API khác, có thể token substitution |
| `AUTH_REVOKED_TOKEN` | 401 | Grant/session/token revoke đã nhìn thấy |
| `AUTH_TOKEN_PURPOSE_MISMATCH` | 401 | ID/refresh token dùng sai |
| `AUTH_INSUFFICIENT_SCOPE` | 403 | Client/token chưa được cấp quyền endpoint |
| `AUTH_OBJECT_FORBIDDEN` | 403/404 | Tenant/ownership/ABAC deny |
| `AUTH_CSRF_REJECTED` | 403 | Browser cookie auth request fail CSRF |
| `AUTH_INTROSPECTION_UNAVAILABLE` | 503/5xx | AS dependency bị lỗi |
| `AUTH_RS_CREDENTIAL_INVALID` | 503/5xx | RS→AS authentication misconfig |
| `AUTH_GATEWAY_POLICY_BLOCK` | 403/429/... | WAF, quota hoặc network policy |

Ví dụ JSON audit **không chứa token**:

~~~json
{
  "event_type": "resource.authorization.denied",
  "occurred_at": "2026-11-23T10:15:00Z",
  "resource_server": "orders-api",
  "issuer": "https://auth.example.test",
  "request_route": "POST /orders/{id}/cancel",
  "http_status": 403,
  "reason_category": "AUTH_INSUFFICIENT_SCOPE",
  "client_id": "orders-web",
  "token_ref": "hmac-pseudonym-not-raw-token",
  "raw_token_logged": false,
  "correlation_ref": "req-pseudo-42"
}
~~~

`raw_token_logged=false` chỉ là kỳ vọng; phải kiểm tra reverse proxy, gateway, APM, tracing, exception logging và support screenshots.

### Metric nên theo dõi

- 401/403/404/503 theo **route, client, issuer, region, deployment version**.
- Tỉ lệ `invalid_token` vs `insufficient_scope` vs object ACL denies.
- Unexpected spikes **wrong audience** sau deploy AS/gateway hoặc token substitution.
- Introspection timeout/failures và RS credential rotation issues.
- Số refresh retries hoặc login loops sau 401.
- 403 CSRF vs 403 scope để không nhầm bug browser với thiếu OAuth grant.
- Revocation propagation delay của JWT denylist/introspection cache.

**Không log raw Bearer token để phân tích 401.** Nếu cần correlation, dùng HMAC fingerprint nội bộ/key rotation/retention controls thay vì dán nguyên JWT vào log.

## 30. Các hiểu lầm thường gặp

**“401 nghĩa là chưa đăng nhập.”** Chưa đầy đủ. Một user đã login vẫn có thể gửi token hết hạn, sai audience hoặc bị revoke và nhận 401.

**“403 nghĩa là account không tồn tại.”** Sai. 403 là từ chối xử lý theo policy; existence có thể được ẩn bằng 404.

**“Token được AS ký hợp lệ thì không thể trả 401.”** Sai. Sai `aud`/`iss`/`typ`/`exp` vẫn là token invalid cho RS.

**“Token thiếu scope nên trả 401 để client tự login lại.”** Không đúng với Bearer `insufficient_scope`: token hợp lệ mà thiếu scope thường là **403**, client có thể cần consent/permission mới.

**“403 luôn là OAuth `insufficient_scope`.”** Sai. 403 còn có thể do object ACL, tenant, CSRF, WAF hoặc chính sách khác.

**“401/403 nào cũng retry refresh token được.”** Sai. 403 scope/ACL thường không đổi nếu refresh cùng grant; 401 wrong audience cũng không được sửa bằng refresh vô hạn.

**“Cứ introspection 401 là user phải đăng nhập lại.”** Sai. Introspection 401 có thể do **RS client credentials sai** với AS; đó là lỗi dịch vụ.

**“Thiếu `WWW-Authenticate` trong 401 Bearer cũng không sao.”** Theo HTTP RFC 9110, 401 **phải** có challenge phù hợp; RFC 6750 quy định Bearer challenge.

**“Không có token thì trả 403 để tránh lộ endpoint.”** Không có rule chung như vậy: protected RS yêu cầu authentication thường trả 401 challenge; 404 conceal dùng theo policy cụ thể.

**“401 từ backend nghĩa CORS bị sai.”** Không luôn. Browser có thể hiển thị CORS failure mà không cho JS đọc response; cần phân biệt network/cookie/preflight/authorization.

**“Nếu user là admin thì token sai audience vẫn nên được dùng.”** Sai. Admin role không bù cho token được phát cho API khác.

**“403 nghĩa frontend có thể tự thêm scope vào token.”** Sai. Scope do AS cấp trong grant/consent hợp lệ và RS chỉ tin token/metadata đã xác minh.

**“403 ở GET order khác user là hết hạn token.”** Sai. Đó là object-level authorization; có thể che bằng 404.

**“Mọi lỗi token do Key rotation phải chấp nhận token tạm thời.”** Sai. Nếu JWKS retrieval không khả dụng và không thể verify một token mới, phải **fail closed**; phân biệt invalid token với dependency outage.

## 31. Ma trận kiểm thử 401/403 cho Resource Server

| Test | Dữ liệu/hành vi | Kết quả mong đợi |
|---|---|---|
| **T1 — Missing token** | GET protected endpoint không Authorization | **401** với `WWW-Authenticate: Bearer` |
| **T2 — Empty bearer** | `Authorization: Bearer` rỗng | Reject authentication; không cấp quyền |
| **T3 — Malformed header** | Cú pháp Authorization sai | 400/401 theo error profile, không allow |
| **T4 — Multiple token transports** | Token cùng lúc ở header và query | `invalid_request`, thường **400** |
| **T5 — Invalid signature** | JWT payload bị sửa | **401 invalid_token** |
| **T6 — alg none** | JWT unsigned, policy yêu cầu JWS | **401** |
| **T7 — Unknown kid** | Không có trusted key matching | Fail closed; không fetch attacker URL |
| **T8 — Wrong issuer** | Token cùng format từ tenant/issuer khác | **401** |
| **T9 — Wrong audience** | Billing AT gửi Orders | **401 invalid_token** |
| **T10 — Missing audience** | JWT RFC 9068 không có `aud` | **401** |
| **T11 — ID token** | `aud=client_id` dùng gọi API | **401** |
| **T12 — Refresh token** | Refresh token gửi Bearer tới RS | **401** |
| **T13 — Auth code** | Authorization code dùng làm access token | **401** |
| **T14 — Expired AT** | `now >= exp` | **401 invalid_token** |
| **T15 — Future nbf** | Token chưa hiệu lực | **401** |
| **T16 — Revoked AT** | Introspection `active:false` | **401** |
| **T17 — Revoked grant JWT** | RS có denylist/epoch check | **401** sau revocation visibility |
| **T18 — Offline JWT** | AS revoke RT, JWT AT còn exp | Quan sát RS vẫn có thể nhận tới `exp` nếu không check revoke |
| **T19 — Active introspection** | `active:true` nhưng thiếu scope | **403** sau token validation |
| **T20 — Introspection missing active** | JSON malformed/`"active":"true"` | Fail closed; protocol failure |
| **T21 — Introspection RS auth fails** | AS HTTP 401 với RS credentials sai | Dependency error, không buộc user login |
| **T22 — Introspection AS timeout** | AS không phản hồi | Fail closed, thường 503/5xx |
| **T23 — Scope valid** | Token Orders có `orders:read` | Qua scope, phải check object |
| **T24 — Scope insufficient** | GET cần `orders:read` nhưng token không có | **403 insufficient_scope** |
| **T25 — Write needs scope** | POST cần `orders:write`, token chỉ read | **403 insufficient_scope** |
| **T26 — Scope substring** | Token `orders:read:any` thay `orders:read` | **403**, không match substring |
| **T27 — Multi-scope exact** | `orders:read profile` | Check chính xác từng scope |
| **T28 — Scope challenge privacy** | 403 với required scope nhạy cảm | Không lộ scope nội bộ quá mức |
| **T29 — Object owner mismatch** | User A đọc order B | **403/404** theo privacy |
| **T30 — Cross-tenant object** | Token đúng scope, tenant sai | **403/404** |
| **T31 — Object not found** | ID không tồn tại | **404** |
| **T32 — Hidden resource** | Tài liệu tồn tại nhưng private | 404 conceal nhất quán |
| **T33 — Role mismatch** | Token hợp lệ nhưng thiếu role admin | **403** |
| **T34 — ABAC policy** | User role đúng nhưng điều kiện kinh doanh sai | **403** hoặc status thích hợp |
| **T35 — Resource state conflict** | Order đã cancel, yêu cầu cancel lại | **409** khi đúng business conflict |
| **T36 — Unsupported HTTP method** | DELETE vào GET-only endpoint | **405**, `Allow` header |
| **T37 — Rate limit** | Vượt quota | **429**, không tự gán token invalid |
| **T38 — WAF forbidden** | IP blocked | 403 WAF; không khai là insufficient_scope |
| **T39 — DPoP missing proof** | Access token DPoP-bound, thiếu proof | Từ chối theo RFC 9449 |
| **T40 — DPoP wrong proof** | Proof ký bằng key khác token binding | Từ chối; không fallback Bearer |
| **T41 — mTLS binding** | Certificate không khớp `cnf` | Từ chối |
| **T42 — Gateway valid** | Gateway/RS cùng kiểm tra đúng aud và scope | Không lộ cross-RS token |
| **T43 — Gateway wrong aud** | Billing token route Orders | **401** ở gate hoặc RS |
| **T44 — Downstream ACL** | Gateway token PASS, backend owner FAIL | **403/404**, không chuyển thành 401 |
| **T45 — API without WWW challenge** | 401 Bearer thiếu header | Test fail theo HTTP/Bearer contract |
| **T46 — Invalid_token header** | JWT expired | Challenge `error="invalid_token"` hợp lệ |
| **T47 — Insufficient_scope header** | Scope thiếu | `403`, challenge scope chỉ khi policy cho |
| **T48 — No token error detail** | Chưa có Authorization | Không tiết lộ `invalid_token` tùy tiện |
| **T49 — Browser CSRF** | POST cookie-auth thiếu CSRF | **403** CSRF, không phải OAuth scope |
| **T50 — Browser CORS preflight** | OPTIONS từ trusted origin | CORS policy đúng, không buộc Bearer cho preflight |
| **T51 — Cross-origin no credentials** | Fetch quên cookie | Browser backend có thể 401; nguyên nhân cookie, không phải scope |
| **T52 — SPA refresh once** | AT hết hạn lần đầu | Single-flight refresh tối đa policy |
| **T53 — No infinite refresh** | 401 liên tiếp sau refresh | Chuyển login/error, không loop |
| **T54 — No refresh on 403 ACL** | User không sở hữu order | Không refresh/token spam |
| **T55 — OAuth token endpoint grant error** | RT invalid tại AS | `400 invalid_grant`, không nhầm RS 401 |
| **T56 — AS JWKS retrieval down** | RS không có key tin cậy để verify | Fail closed, dependency handling |
| **T57 — Double denial** | JWT expired và scope thiếu | Trả token invalid 401 trước scope evaluation |
| **T58 — PII logging** | Canary token qua gateway/APM | Không log raw AT/RT/JWT/cookie |
| **T59 — Problem details** | 403 object ACL with RFC9457 body | Body generic, không leak object existence |
| **T60 — Metrics categories** | Hàng loạt 401 wrong-audience sau release | Phân biệt issuer/audience/scope/AS outage |
| **T61 — JWT correct all checks** | Token đúng issuer/aud/type/exp/scope, owner OK | **2xx** theo business response |
| **T62 — Concurrent revoked token** | Token revoke trong khi cache active | Quan sát revocation SLA, không hứa chặn ngay khi không bảo đảm |

**Kiểm thử với AS mock/staging và token canary, không dùng raw credential production**. Một test chỉ dùng token chữ ký sai không kiểm tra được audience validation; phải có **JWT ký hợp lệ nhưng `aud` sai** để bắt lỗi token substitution. Một test chỉ có valid token cho object của user A cũng chưa bắt được BOLA; phải thử **same-scope token truy cập object của user B**.

## 32. Checklist triển khai và tài liệu chuẩn

### Checklist cho Resource Server

1. **Phân biệt authentication và authorization**; token invalid/missing → thường 401; valid token thiếu scope/permission → thường 403.
2. Với 401, trả **`WWW-Authenticate` challenge** phù hợp theo RFC 9110/6750.
3. Đối với Bearer token không có thông tin xác thực, **không tự kèm error detail không cần thiết**.
4. Với invalid/expired/revoked/wrong-audience/wrong-issuer token, trả **401 `invalid_token`** theo Bearer contract.
5. Với valid token thiếu scope, trả **403 `insufficient_scope`** và chỉ công bố required scope khi phù hợp.
6. Với object/tenant ACL deny, trả **403** hoặc **404 conceal** theo privacy policy; không tự coi là insufficient scope.
7. **Verify JWS/JWT đúng profile**, allowed alg, trusted key, issuer, audience, token purpose/`typ`, exp/nbf và claims cần thiết.
8. Với opaque token, **introspect qua authenticated HTTPS**, validate `active` boolean và AS–RS metadata contract.
9. **Không coi lỗi introspection network/RS credentials là user token invalid**; fail closed và báo dependency failure.
10. **Không dùng ID/refresh/authorization/device token làm API access token**.
11. **So scope chính xác**, không substring, và thực thi endpoint + object-level policy.
12. Nếu dùng DPoP/mTLS, **kiểm tra sender proof/binding** ngoài token validity, không fallback sang Bearer không được phép.
13. **Cấu hình audience theo từng RS/gateway route**, không dùng `client_id` làm RS audience.
14. **Tách authn/authz ở Spring Security**, đừng override exception handler để trả một status cho mọi failure.
15. **Bật method/object-level authorization** cho tenant/owner/admin; chống BOLA/IDOR.
16. **Không mutation bằng GET**; phân biệt CSRF 403 với insufficient scope 403.
17. **Xử lý CORS preflight OPTIONS** đúng browser contract, không yêu cầu token cho preflight không có Bearer.
18. **Không chuyển mọi 403 thành 401** ở gateway/BFF/frontend, tránh refresh loops.
19. **Thiết kế client ứng xử**: 401 có thể refresh một lần theo flow; 403 báo permission; 503 là availability.
20. **Không lộ token/PII** trong error description, body, URL, logs, APM hoặc audit.
21. **Phân loại event nội bộ** theo missing, expired, wrong audience, scope, object ACL, CSRF, AS outage.
22. **Kiểm thử status và challenge header thực tế** bằng integration tests qua proxy/gateway, không chỉ unit test service.
23. **Kiểm tra revocation visibility SLA** của JWT offline, introspection cache/denylist, không hứa revoke tức thì nếu kiến trúc chưa có.
24. **Test token hợp lệ nhưng sai audience, token valid thiếu scope, token valid sai object** để xác nhận ba lớp quyết định.
25. **Duy trì quy tắc deny-by-default** với unknown routes, ambiguous token types, invalid metadata và policy errors.

### Tài liệu chuẩn và tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `401`/`403`/`404`, `WWW-Authenticate` và HTTP response semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer challenge, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS/RS roles, token endpoint và `invalid_grant`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active:true/false` và bảo vệ introspection.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token type, issuer/audience/claims validation tại RS.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token misuse/replay, AS/RS security và OAuth hardening.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm, cross-JWT confusion và validation.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained proof/challenge.
- [RFC 8705 — OAuth mTLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access token.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): `application/problem+json` khi cần error body chuẩn hóa.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/audience JWT validation và Spring.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và resource server.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): route authorities và authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và object-level authorization.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object/tenant access denial.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): bảo vệ token và OAuth flows.

**Kết luận:** Tại **OAuth 2.0 Resource Server**, **401** thường có nghĩa **credential thiếu/không hợp lệ cho chính API này** và cần Bearer challenge; **403** thường có nghĩa **request bị từ chối dù token đã xác thực**, chẳng hạn thiếu scope, role hoặc quyền trên object. **404** có thể che tài nguyên bị cấm, còn **503** có thể phù hợp khi RS không thể kiểm tra token vì AS outage. Triển khai đúng không chỉ chọn mã HTTP đẹp: phải **xác minh token issuer, audience, purpose, signature/active state, expiry**, kiểm tra scope và object policy, xử lý introspection/PoP đúng profile, hạn chế rò thông tin và giúp client phản ứng **401/403** khác nhau mà không tạo refresh loop hay bypass bảo mật.
