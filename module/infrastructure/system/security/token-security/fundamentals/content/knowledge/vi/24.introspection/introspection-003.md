# Active và inactive response

Trong **OAuth 2.0 Token Introspection (RFC 7662)**, **Resource Server (RS)** gửi một token tới **Authorization Server (AS)** qua introspection endpoint để hỏi token đó **đang hoạt động hay không** và, nếu được phép, nhận metadata phục vụ quyết định truy cập API. Kết quả trả về là JSON có trường **`active` kiểu boolean**: `true` hoặc `false`.

Hai kết quả này trông đơn giản, nhưng dễ bị hiểu sai. **`active: true` không có nghĩa mọi API đều phải chấp nhận token**; **`active: false` không nhất thiết chỉ có nghĩa token hết hạn**. AS có thể trả `false` khi token bị thu hồi, chưa/không còn hiệu lực, không tồn tại, hoặc bên hỏi **không được phép biết trạng thái token đó**. Còn khi AS không thể trả lời do lỗi mạng, HTTP 500 hay credential RS sai, đó là **lỗi introspection**, không phải một response `active:false` hợp lệ.

Bài học **“Active và inactive response”** nằm trong chương **Introspection** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối mô hình tin cậy, JWT/opaque token, access/refresh token, claims, scope, audience, phát hành, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại trong OAuth 2.0/OIDC.

> **Nguyên tắc cốt lõi:** chỉ tin introspection response nhận **trực tiếp từ AS tin cậy trên kênh được bảo vệ và đã xác thực RS**; `active:true` chỉ mở đầu việc kiểm tra **token type/usage, issuer, audience, expiry, scope và object-level authorization**. `active:false` là từ chối truy cập; lỗi introspection cũng phải **fail closed**, không được tự biến thành `active:true`.

## 1. Introspection giải quyết bài toán gì?

Một access token có thể là:

- **Opaque token:** chuỗi khó đoán không chứa claims mà API có thể tự xác minh. RS thường cần hỏi AS qua introspection hoặc một hệ thống trạng thái tin cậy.
- **JWT access token:** mang chữ ký và claims, cho phép RS xác minh cục bộ theo profile phù hợp. Tuy nhiên, nếu cần biết **revoke/grant state gần thời gian thực**, có thể bổ sung introspection hoặc cơ chế trạng thái được thiết kế riêng.
- **Sender-constrained token:** token có thể gắn với khóa DPoP/chứng chỉ mTLS, cần cả trạng thái token **và proof-of-possession tại request**.

`active` là **kết quả kiểm tra trạng thái** trong ngữ cảnh AS và yêu cầu introspection, **không mô tả định dạng token**. Cùng một endpoint có thể hỗ trợ kiểm tra opaque token, JWT hoặc token của các loại khác theo chính sách AS; RS không được suy từ JSON hay chuỗi token rằng nó mặc định hợp lệ cho API.

### Ba câu hỏi khác nhau

| Câu hỏi | Ai chịu trách nhiệm chính? | Ví dụ |
|---|---|---|
| **Token có đang hoạt động không?** | AS qua introspection | `"active": true` |
| **Token này có dành cho API/hành động này không?** | RS, kết hợp policy AS | `aud=orders-api`, scope `orders:read` |
| **Người gọi có quyền với tài nguyên cụ thể không?** | RS/application policy | User thuộc tenant và có quyền đọc order `123` |

Không được gộp ba câu thành một lệnh `if (active) allow();`.

## 2. Mô hình tin cậy và đường đi của một request

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User/Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    participant DATA as Orders service/data

    U->>RS: GET /orders/123 + Authorization: Bearer AT
    RS->>AS: POST /introspect + AT, xác thực RS
    AS->>AS: Check token state, expiry, revoke, RS permission
    alt Token inactive/không được RS biết
        AS-->>RS: HTTP 200 {"active":false}
        RS-->>U: 401 hoặc xử lý deny theo profile
    else Token active và RS được xem metadata
        AS-->>RS: HTTP 200 {"active":true,...claims}
        RS->>RS: Check type/usage, iss, aud, exp, scope, proof
        alt Policy/token context không đạt
            RS-->>U: 401 hoặc 403 theo lý do
        else Policy đạt
            RS->>DATA: Check owner, tenant, object permission
            DATA-->>RS: Dữ liệu được phép
            RS-->>U: 200 OK
        end
    else AS unavailable / auth error
        AS-->>RS: 401 / 5xx / timeout
        RS-->>U: Deny/fail closed theo availability policy
    end
~~~

**Lưu ý:** HTTP response của introspection endpoint **không phải** HTTP response mà API bắt buộc phải gửi cho người gọi cuối. RS diễn giải nội bộ, rồi trả lỗi API phù hợp mà không làm lộ details introspection.

### RS là ai tại introspection endpoint?

RS thường có **credential riêng** để xác thực khi gọi AS, chẳng hạn client authentication, mTLS hoặc một cơ chế đã đăng ký. Nó không nên tự lấy access token của user làm **bằng chứng duy nhất rằng RS được quyền introspect mọi token**.

AS phải bảo vệ endpoint để kẻ lạ không dùng introspection thành một công cụ **kiểm tra token có tồn tại, thuộc user nào và còn hạn bao lâu**.

## 3. HTTP request chuẩn theo RFC 7662

Introspection endpoint hỗ trợ **HTTP POST** với body `application/x-www-form-urlencoded`. Ví dụ khi RS xác thực bằng HTTP Basic theo cấu hình được cấp:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <ENCODED_RS_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN_TO_CHECK>&token_type_hint=access_token
~~~

Đây là ví dụ **giả**, không dùng giá trị production. `Authorization: Basic` chỉ Base64-encode thông tin định danh/mật khẩu RS; **Base64 không mã hóa bí mật**. TLS bắt buộc để bảo vệ cả RS credential và token trong request.

| Thành phần | Ý nghĩa | Lưu ý |
|---|---|---|
| **`token`** | Credential RS muốn kiểm tra | **REQUIRED**; bí mật, không log/body dump |
| **`token_type_hint`** | Gợi ý kiểu token, ví dụ `access_token` | **OPTIONAL**; chỉ tối ưu lookup, không phải bằng chứng loại token |
| **RS authentication** | Xác định bên được phép gọi introspection | Theo chính sách AS; không nhúng secret vào frontend |
| **Introspection URL** | Endpoint từ issuer/metadata/cấu hình tin cậy | Không lấy từ JWT header hay input không đáng tin |
| **TLS + timeout** | Bảo vệ credential, giới hạn chờ | Không hạ cấp HTTP hoặc tắt xác minh chứng chỉ |

RFC 7662 yêu cầu server hỗ trợ POST; một số triển khai có thể hỗ trợ thêm GET, nhưng **không nên gửi token trên query string** vì dễ lọt vào log, browser history, proxy analytics và header `Referer`.

**`token_type_hint` không bắt AS chỉ kiểm tra đúng một loại token.** RFC 7662 cho phép AS dùng hint để tìm nhanh; nếu không tìm được trong loại được gợi ý, AS có thể tìm nơi khác. Do đó **không** được viết: “gửi `token_type_hint=access_token` thì chắc chắn response chỉ có access token”.

## 4. JSON response: trường active bắt buộc

RFC 7662 quy định introspection response là một JSON object, trong đó **`active` là trường REQUIRED với giá trị boolean**.

~~~json
{
  "active": true
}
~~~

~~~json
{
  "active": false
}
~~~

**Ba điều không được nhầm:**

1. `"active": true` là boolean JSON, **khác** `"active": "true"` (string), `"active": 1` (number) hoặc trường `active` bị thiếu.
2. HTTP **`200 OK` không đồng nghĩa `active:true`**. Ngay cả khi token không tồn tại, AS vẫn thường trả **200 với `{"active":false}`**.
3. Nếu AS trả JSON hỏng, thiếu `active`, hoặc trả boolean dưới dạng string, RS phải coi response **không hợp lệ theo contract**, không âm thầm ép kiểu rồi cấp quyền.

`active` mô tả AS xem token có đang active trong ngữ cảnh request hay không. Các trường metadata khác là tùy chọn và chỉ có ý nghĩa khi AS quyết định cung cấp cho bên hỏi.

## 5. Active response: ví dụ nhiều metadata

Khi token đang hoạt động và RS được phép nhận metadata, AS có thể trả thêm các trường chuẩn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
~~~

~~~json
{
  "active": true,
  "scope": "orders:read profile",
  "client_id": "orders-web",
  "username": "user-demo",
  "token_type": "Bearer",
  "exp": 1800003600,
  "iat": 1800000000,
  "nbf": 1800000000,
  "sub": "user-pseudonym-42",
  "aud": "https://orders-api.example.test",
  "iss": "https://auth.example.test",
  "jti": "opaque-token-reference-001"
}
~~~

Mọi token, user, issuer và timestamp ở đây đều là **giá trị minh họa**. Không coi `exp=1800003600` là còn hạn khi chạy trên một thời điểm bất kỳ; `exp` phải được kiểm tra với clock thực.

### Ý nghĩa những trường phổ biến

| Trường | Ý nghĩa | Cách RS sử dụng an toàn |
|---|---|---|
| **`active`** | Token còn hoạt động theo AS | **Cần**, nhưng **chưa đủ** để cho phép API |
| `scope` | Các scope thực sự gắn với token, thường chuỗi phân cách bằng khoảng trắng | So token scope **chính xác**, không kiểm tra substring |
| `client_id` | Client đã được cấp token | Policy client/tenant và phân loại chủ thể |
| `username` | Tên user dễ đọc nếu AS cung cấp | Không dùng làm authorization key ổn định |
| `token_type` | Kiểu trình token, ví dụ `Bearer` | Không chứng minh token là **access token** thay vì refresh/ID |
| `exp` | Thời điểm hết hạn, thường NumericDate/Unix seconds | Từ chối tại và sau deadline |
| `iat` | Thời điểm phát hành | Phân tích TTL và bất thường timestamp |
| `nbf` | Không hợp lệ trước thời điểm này | Từ chối khi chưa tới hiệu lực |
| `sub` | Subject liên quan đến token | Phân biệt user/service client và issuer/tenant |
| `aud` | Audience/token recipient | Bắt buộc theo policy API; không chấp nhận token của API khác |
| `iss` | Issuer của token | So khớp đúng AS tin cậy |
| `jti` | Token identifier | Phục vụ correlation/revocation theo profile; **không phải credential** |

**Không phải mọi trường đều bắt buộc theo RFC 7662.** AS có thể chỉ trả `active` và một số field; RS cần **hợp đồng introspection** đủ rõ để thực thi quyền. Nếu API yêu cầu `aud`/`scope` mà response không cung cấp và AS không đảm bảo policy tương đương bằng một cơ chế tin cậy khác, **không đoán là được phép**.

`scope` thường có dạng một **chuỗi scope phân cách bằng dấu cách**, không phải mảng JSON. Một provider có thể có extension khác, nhưng RS chỉ parse theo hợp đồng đã xác minh.

## 6. Active=true nói được gì — và không nói được gì?

Khi AS trả `"active": true`, RS có thể biết AS hiện xem token là **đang hoạt động trong ngữ cảnh introspection đó**. Một AS thường xét token tồn tại, được phát hành, chưa hết hạn và chưa bị thu hồi; AS còn có thể xét client, grant, audience, quyền của RS được hỏi hoặc trạng thái policy.

**Không thể suy ra chỉ từ `active:true` rằng:**

- Token là **access token** dành cho API này.
- Token có đúng **`aud`** hoặc audience/resource indicator.
- Token có scope phù hợp với endpoint, ví dụ `orders:read`.
- Chủ thể sở hữu object/tenant đang yêu cầu.
- Bearer token không bị đánh cắp hoặc đang được trình bởi chính người được cấp.
- DPoP proof hoặc mTLS certificate binding đã được kiểm tra tại HTTP request.
- Token được cấp cho **cùng issuer/tenant** mà API đang tin.
- User vẫn có quyền nghiệp vụ nếu role/ACL đã thay đổi kể từ lúc phát token.

**Ví dụ sai:**

~~~java
// Chống chỉ định: "active" một mình không đủ để authorize.
if (introspection.active()) {
    return orderRepository.findById(orderId);
}
~~~

**Ví dụ đúng về luồng quyết định (pseudocode):**

~~~text
introspectionResponse = authenticatedIntrospection(accessToken)
require introspectionResponse.active is strictly JSON true
require token purpose/usage is access_token according to AS-RS contract
require issuer == configured issuer
require audience includes this Resource Server
require not expired and not before nbf
require granted scopes contain required scope (exact scope match)
require sender proof matches cnf binding, if sender constrained
require subject/client/tenant allowed to act on requested object
ONLY THEN return authorized resource
~~~

Kết quả introspection là **dữ liệu để ra quyết định**, không phải quyết định authorization cuối cùng.

## 7. Inactive response: chỉ một trường cũng là hợp lệ

Một token inactive thường nhận response tối giản:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
~~~

~~~json
{
  "active": false
}
~~~

AS **không cần giải thích** vì sao inactive. Theo RFC 7662, AS trả inactive khi:

- Token **không tồn tại** trên AS đó hoặc không thể nhận diện.
- Token đã **hết hạn**, bị vô hiệu hoặc bị thu hồi.
- Token có thể chưa có hiệu lực hoặc không đáp ứng các điều kiện trạng thái của AS.
- **Protected resource không được phép introspect token cụ thể đó**, nên AS chủ ý không tiết lộ trạng thái.

### Vì sao không trả thêm user hoặc lý do?

Nếu AS trả:

~~~json
{
  "active": false,
  "sub": "sensitive-user",
  "reason": "token_revoked_at_10_05",
  "client_id": "another-company-client"
}
~~~

một attacker kiểm soát RS credential hoặc một bên có thể tiếp cận endpoint có thể dùng nó để **liệt kê token, người dùng, client, trạng thái thu hồi hoặc thời gian hoạt động**. Vì vậy, RFC 7662 khuyến nghị AS **không kèm thông tin khác về token inactive**.

**Phản hồi inactive nên đồng nhất, tối giản** cho các trường hợp không tồn tại, expired, revoked và token RS không được xem. Hệ thống vẫn có thể ghi reason code trong **audit nội bộ bảo vệ**, không đẩy reason đó ra mọi introspection client.

## 8. Active=false không phải lúc nào cũng nghĩa token hết hạn

Xét bốn trường hợp:

| Token | Trạng thái thực | AS trả cho RS A | Cách hiểu đúng |
|---|---|---|---|
| **K1** | Hết hạn | `active:false` | Không được dùng, có thể vì expiry |
| **K2** | Bị user/AS revoke | `active:false` | Không được dùng, có thể vì revocation |
| **K3** | Chưa từng được AS phát hành | `active:false` | Không được dùng, có thể không tồn tại |
| **K4** | Đang active cho API B, RS A không được xem | `active:false` | RS A không có quyền tin token; không chứng minh token chết toàn cục |

**K4 là điểm khó nhất.** Một AS triển khai introspection theo **ngữ cảnh protected resource** có thể không tiết lộ token của resource B cho resource A. Nếu A thấy `false`, A chỉ biết **không được chấp nhận token đó trong context này**, không được khẳng định token đã bị thu hồi trên toàn hệ thống.

Vì vậy, đừng xây chức năng quản trị kiểu “một RS hỏi active:false rồi thông báo user token đã hết hạn toàn bộ”. API trả generic `invalid_token`; hệ thống hỗ trợ/giám sát dùng kênh quản trị AS tin cậy khi cần nguyên nhân.

## 9. Phân biệt HTTP 200 inactive với lỗi HTTP/authentication

Một trong những lỗi triển khai phổ biến nhất là gộp mọi response thất bại thành `active:false`, hoặc nguy hiểm hơn là **cho phép truy cập khi introspection unreachable**.

| Kết quả từ AS/introspection endpoint | Có phải introspection verdict? | RS nên làm gì? |
|---|---|---|
| **HTTP 200, `{"active":true,...}`** | Có, token active | Tiếp tục kiểm tra mục đích/audience/scope/authorization |
| **HTTP 200, `{"active":false}`** | Có, token inactive/không được xem | Từ chối token |
| **HTTP 200, thiếu `active`** | **Không hợp lệ** | Fail closed, log lỗi giao thức an toàn |
| **HTTP 200, `"active":"true"`** | **Không hợp lệ** | Không ép string thành boolean rồi cấp quyền |
| **HTTP 400, `invalid_request`** | Lỗi request | Sửa request; không cho access |
| **HTTP 401, RS credentials sai/thiếu** | Lỗi xác thực RS tại AS | Dừng/fail closed, cảnh báo vận hành; không tự xóa client auth |
| **HTTP 403, AS không cho RS dùng endpoint** | Lỗi quyền của caller | Fail closed, kiểm tra registration/policy |
| **HTTP 429, rate limited** | Lỗi khả dụng/chính sách | Backoff và fail closed |
| **HTTP 500/503, timeout, TLS failure** | **Không có verdict** | Không suy là active hoặc tự tái sử dụng stale allow |
| **HTTP 302 đến site lạ** | Redirect không đáng tin | Chặn/validate theo policy; không gửi token sang host lạ |

**HTTP 200 không tự làm response hợp lệ**; nó vẫn cần body đúng JSON schema, transport tin cậy, RS authentication và token-policy checks.

**Phân biệt audit:** `TOKEN_INACTIVE` khác `INTROSPECTION_UNAVAILABLE` và `RS_CREDENTIAL_INVALID`. Người dùng cuối có thể thấy lỗi đơn giản, nhưng kỹ sư vận hành phải biết đây là **sự cố auth dependency** chứ không nhất thiết user cần đăng nhập lại.

## 10. State machine quyết định của Resource Server

~~~mermaid
flowchart TD
    A["Request API có Bearer access token"] --> B{"Token phù hợp cú pháp transport?"}
    B -->|"Không"| DENY1["401 invalid_token"]
    B -->|"Có"| C["POST introspection + RS client auth"]
    C --> D{"AS response đáng tin, HTTP 200, JSON hợp lệ?"}
    D -->|"Không"| FAIL["Fail closed, báo lỗi dependency/policy"]
    D -->|"Có"| E{"active là boolean true?"}
    E -->|"Không: false"| DENY2["401 invalid_token"]
    E -->|"Không: missing/wrong type"| FAIL
    E -->|"Có"| F{"Access token usage + iss/aud/time hợp lệ?"}
    F -->|"Không"| DENY1
    F -->|"Có"| G{"Scope đúng endpoint?"}
    G -->|"Không"| DENY3["403 insufficient_scope"]
    G -->|"Có"| H{"Sender proof và object/tenant ACL đúng?"}
    H -->|"Không"| DENY4["403 hoặc 401 theo loại lỗi"]
    H -->|"Có"| OK["Cho phép truy cập tài nguyên"]
~~~

**Mã phản hồi API tùy failure class**:

- Token không hợp lệ/inactive: thường **401 Unauthorized** và Bearer challenge theo RFC 6750.
- Token còn hiệu lực nhưng thiếu scope: thường **403 Forbidden**, có thể dùng `insufficient_scope`.
- API mất kết nối introspection AS: cần **fail closed**; một số hệ thống trả **503 Service Unavailable** thay vì 401 để phân biệt dependency outage, nhưng không được tiết lộ secrets hoặc chấp nhận token.
- Khi proof-of-possession sai, xử lý theo **DPoP/mTLS profile** và status/challenge phù hợp, không mặc định mọi lỗi đều 403.

Đây là gợi ý kiến trúc; code/response cụ thể phụ thuộc Resource Server stack và authorization profile.

## 11. Active=true nhưng audience sai

Một API gọi introspection và nhận:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://billing-api.example.test",
  "scope": "billing:read",
  "exp": 1800003600,
  "token_type": "Bearer"
}
~~~

Token này **có thể active tại AS** nhưng **không phải token dành cho Orders API**. Nếu Orders API chỉ hỏi `active` rồi cho đọc order, hệ thống đã mắc lỗi **cross-resource token substitution**.

Chính sách đúng của Orders API:

~~~text
expected_issuer   = "https://auth.example.test"
expected_audience = "https://orders-api.example.test"
required_scope    = "orders:read"

Introspection:
    active = true
    aud = "https://billing-api.example.test"

Decision:
    REJECT — wrong audience
~~~

**Audience không phải tên UI hoặc `client_id`.** Client `orders-web` có thể nhận access token dành cho nhiều RS khác nhau; mỗi RS chỉ nhận token được cấp cho mình. Nếu `aud` không xuất hiện trong introspection response, cần chính sách đã xác định từ trước: ví dụ AS đảm bảo **chỉ trả `active:true` cho RS được phép** hoặc có contract riêng, không tự coi absence là wildcard audience.

## 12. Active=true nhưng scope hoặc quyền dữ liệu không đủ

Ví dụ:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "sub": "user-42",
  "exp": 1800003600
}
~~~

| API endpoint | Quyền yêu cầu | Quyết định |
|---|---|---|
| `GET /orders/123` | `orders:read` + ownership/tenant | **Chỉ cho phép** nếu object policy đạt |
| `POST /orders` | `orders:write` | **403**, thiếu scope |
| `DELETE /orders/123` | `orders:delete` hoặc role/policy tương ứng | **403**, thiếu quyền |
| `GET /admin/orders` | Admin role + permission | **Không tự suy ra** từ `orders:read` |

**Không dùng substring search**:

~~~java
// Sai: "orders:read:any" cũng chứa chuỗi "orders:read".
boolean hasRead = scopeString.contains("orders:read");
~~~

Cần tách các scope theo dấu cách và so **token chính xác**. Scope cũng không thay thế **object-level authorization**: user `42` có thể có scope đọc đơn hàng nhưng không được đọc đơn của user `99`.

## 13. Token type confusion: active refresh token không phải access token

**Introspection có thể được AS triển khai cho nhiều loại OAuth token.** Một refresh token còn hiệu lực tại AS **không trở thành access token API** chỉ vì AS có thể đánh giá nó active.

| Credential | Hợp lệ cho tác vụ nào? | Có nên chấp nhận tại Orders API? |
|---|---|---|
| **Access token dành Orders API** | HTTP request tới Orders API trong scope/audience | Có, **sau mọi kiểm tra** |
| **Access token dành Billing API** | Gọi Billing API | **Không** |
| **Refresh token** | `grant_type=refresh_token` tại AS token endpoint | **Không** |
| **OIDC ID token** | RP xác minh user authentication | **Không** |
| **Authorization code** | AS token endpoint (PKCE) | **Không** |
| **Device code** | AS token endpoint trong RFC 8628 polling | **Không** |

**`token_type_hint=access_token` chỉ là hint lookup.** `token_type=Bearer` nếu xuất hiện trong response mô tả kiểu token presentation, **không phải một “bằng chứng đây là access token”**. Một AS có thể hỗ trợ introspect refresh token theo policy; RS phải nhận diện **token usage** qua hợp đồng đáng tin với AS.

### Thiết kế chống type confusion

Một trong những cách sau cần được **AS và RS quy định rõ**:

1. AS **chỉ trả `active:true` cho access token hợp lệ với chính RS này**, các loại khác trả `false` khi RS introspect.
2. AS trả một **trường purpose/usage mở rộng**, chẳng hạn `"token_use": "access_token"`, mà RS kiểm tra chính xác. **`token_use` không phải trường REQUIRED của RFC 7662**, tên và semantics phải theo provider profile.
3. Với JWT access token, RS áp dụng profile chuyên biệt như **RFC 9068 `typ=at+jwt`**, issuer/audience/signature và không nhầm với ID token; nếu introspection được bổ sung, vẫn giữ ràng buộc mục đích.

**Không lấy một trường thiếu hoặc không chuẩn rồi tự đoán ý nghĩa.** Nếu AS không có cơ chế phân biệt purpose, không triển khai policy `if(active)`; phối hợp với AS để thiết lập contract an toàn.

## 14. Những trường không bắt buộc: xử lý thiếu dữ liệu

RFC 7662 **chỉ yêu cầu `active`**; các metadata khác là tùy chọn. Vì vậy, một response như:

~~~json
{
  "active": true,
  "client_id": "orders-web"
}
~~~

là **có thể đúng về dạng cơ bản**, nhưng chưa chắc **đủ cho Orders API** nếu RS cần biết audience/scope/expiry. Đây là khác biệt giữa **“JSON hợp lệ theo RFC”** và **“đủ thông tin để cấp quyền”**.

| Trường thiếu | Nguy cơ nếu RS tự mặc định allow | Giải pháp |
|---|---|---|
| `aud` | Cho phép token của API khác | Yêu cầu aud hoặc resource-bound introspection contract |
| `scope` | Cấp quyền endpoint cần scope mà chưa chứng minh token có scope | Reject cho protected endpoint, hoặc policy đã được AS đảm bảo ngoài response |
| `exp` | Cache active mãi mãi, dùng token hết hạn | Cần AS đảm bảo expiry và cache TTL cực ngắn/no cache |
| `iss` | Nhầm issuer khi multi-tenant | Pin endpoint/issuer + contract ràng buộc issuer; yêu cầu field nếu cần |
| `sub` | Gán nhầm user hoặc không biết identity | Không tự chọn user từ `username`/`client_id` tùy tiện |
| Purpose/token usage | Accept refresh/ID token như API token | RS-specific AS contract hoặc field rõ semantics |
| `cnf` khi sender-constrained | Bỏ qua proof binding | Provider/profile phải cung cấp binding cho RS kiểm tra |

Không có quy tắc “trường optional thiếu thì luôn phải reject” **trong RFC 7662**. Nhưng **chính sách bảo mật của RS** có thể và thường phải đặt các trường đó làm **bắt buộc trong hợp đồng tích hợp**.

## 15. NumericDate, expires_at và clock skew

Các trường `exp`, `iat`, `nbf` thường dùng **NumericDate** (giây Unix) trong JSON. Không được xem `exp` là thời lượng `expires_in` hoặc lấy mili-giây nhầm với giây.

~~~text
exp = 1800003600     // epoch seconds, ví dụ
now = current_utc_epoch_seconds

if now >= exp:
    deny

if nbf exists and now < nbf:
    deny

if exp missing:
    rely only on explicit AS-RS agreement and bounded cache,
    otherwise do not assume infinite validity.
~~~

### Phân biệt `exp` với `expires_in`

- **`exp`** trong introspection là **thời điểm tuyệt đối**.
- **`expires_in`** trong OAuth token response thông thường là **số giây còn hiệu lực tại thời điểm trả response**.
- **`iat`** là issued-at timestamp, **không tự làm token active**.
- **`nbf`** có thể ngăn token được dùng trước thời điểm hiệu lực.

Dùng clock hệ thống được đồng bộ. Nếu cần skew tolerance, đặt **giới hạn nhỏ theo policy**, không mở “grace period 10 phút” tùy tiện cho token hết hạn. AS vẫn giữ vai trò nguồn trạng thái `active`; RS kiểm tra mốc thời gian bổ sung để không accept kết quả cache sau expiry.

## 16. Sender-constrained token: active=true chưa xác minh proof

Khi AS phát **DPoP-bound access token** hoặc token ràng buộc với **mTLS certificate**, RS cần kiểm tra thông tin binding (thường trong claim/metadata `cnf` theo profile) cùng bằng chứng tại **request hiện tại**.

~~~json
{
  "active": true,
  "scope": "orders:read",
  "aud": "https://orders-api.example.test",
  "iss": "https://auth.example.test",
  "exp": 1800003600,
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT_PLACEHOLDER"
  }
}
~~~

`cnf.jkt` là minh họa DPoP key thumbprint, không phải chữ ký/thẻ dùng được thật. Với DPoP, RS còn phải kiểm tra proof JWT ở HTTP request, ví dụ `htm`/`htu`/`iat`/`jti`/`ath` và key binding theo RFC 9449. Với mTLS, kiểm tra chứng chỉ TLS và `cnf` thumbprint theo RFC 8705.

**Không được**:

- Nhìn `active:true` rồi bỏ kiểm tra DPoP/mTLS proof.
- Tự nhận `token_type=DPoP` hoặc Bearer trong JSON là đủ bằng chứng khóa.
- Chấp nhận `cnf` do client tự thêm vào HTTP request thay vì từ AS/verified token.

Proof-of-possession là **lớp riêng** bên cạnh active state, audience và scope.

## 17. Bảo vệ introspection endpoint khỏi lộ bí mật/oracle

Introspection endpoint nhận **credential nhạy cảm** và có thể trả **metadata nhận dạng user/client**. Vì vậy nó phải được vận hành như một security-sensitive service.

### Các biện pháp phía AS

- **Xác thực RS/introspection client** bằng phương thức đã đăng ký (ví dụ `client_secret_basic`, `private_key_jwt`, mTLS), chỉ cấp quyền introspect những token mà RS cần biết.
- **Authorization per RS/audience**: có thể trả inactive cho token không thuộc tài nguyên đang hỏi để giảm tiết lộ.
- **TLS và chứng chỉ hợp lệ**; không công khai credentials trong URL.
- **Rate limiting**, quota và chống DoS cho token lookup.
- **Generic inactive response** cho token không tồn tại/hết hạn/bị thu hồi/không được xem; tránh tiết lộ reason trực tiếp.
- **Hạn chế response fields** theo nhu cầu RS; không phát tán email/PII hoặc grant metadata không cần thiết.
- **Audit nội bộ an toàn**, phân biệt lý do mà không log token raw.
- **Kiểm soát cache headers**: dùng `no-store` khi policy yêu cầu không cache metadata nhạy cảm.

### Các biện pháp phía RS

- Endpoint chỉ từ **issuer/cấu hình tin cậy**, không tin URL trong token/request.
- RS credential lấy từ **secret manager/OS-protected store**, không hardcode vào SPA/mobile.
- **Không log** token introspection, response chứa PII, HTTP Authorization header hay Basic credentials.
- Giới hạn HTTP timeouts, redirect, response size; xác minh JSON schema và status.
- Phân loại AS outage khác inactive token; fail closed.
- Không đưa introspection response thô về browser/client gọi API; chỉ trả status và dữ liệu ứng dụng cần thiết.

**Một RS credential bị lộ có thể biến introspection thành endpoint dò token**. Hạn quyền và rotation RS credential quan trọng tương tự bảo vệ API token.

## 18. Lưu cache active response và khoảng trễ thu hồi

Introspection mỗi request giúp RS thấy trạng thái gần AS hơn nhưng có chi phí mạng/độ trễ. RFC 7662 cho phép các RS áp dụng **caching** theo quyết định bảo mật; quan trọng là **trade-off giữa hiệu năng và độ trễ nhìn thấy revocation**.

~~~mermaid
sequenceDiagram
    autonumber
    participant Client
    participant RS as Resource Server + cache
    participant AS as Authorization Server

    Client->>RS: Request với token T
    RS->>AS: Introspect T
    AS-->>RS: active=true, exp=...
    RS->>RS: Cache verdict TTL ngắn theo policy
    RS-->>Client: Cho phép nếu aud/scope/object policy đạt
    Client->>AS: User/admin thu hồi token T
    AS->>AS: Đánh dấu T revoked
    Client->>RS: Gửi lại token T trong TTL cache
    RS->>RS: Có thể dùng active=true cache cũ
    RS-->>Client: Có thể còn cho phép trong độ trễ TTL
    Note over RS,AS: Cache hết hạn hoặc nhận revocation signal
    Client->>RS: Gửi lại T
    RS->>AS: Introspect lại
    AS-->>RS: active=false
    RS-->>Client: 401 / từ chối
~~~

### Quy tắc cache an toàn

- Nếu AS trả `Cache-Control: no-store` hoặc hợp đồng cấm cache, **không cache**.
- Nếu cache được phép, **TTL ngắn có giới hạn** theo nhu cầu bảo mật/SLA thu hồi.
- Với `exp` đáng tin, không cache kết quả active **vượt quá `exp - now`**.
- Nếu thiếu `exp`, cần chính sách TTL chặt hơn hoặc không cache; không mặc định “active vô hạn”.
- Cache key phải tách **issuer, token reference/HMAC, RS identity/audience và policy context**. Không dùng raw bearer token làm key được log hoặc dễ trích xuất.
- **Negative cache** cho inactive nếu dùng cũng cần TTL ngắn và policy cụ thể; tránh lộ trạng thái hoặc ngăn nhận dạng thay đổi do replication.
- Khi logout/revocation khẩn cấp, cân nhắc **push invalidation/event/denylist**, introspect lại hoặc không cache ở endpoint nhạy cảm.
- Cache introspection **không được cache quyết định object ACL** nếu quyền dữ liệu thay đổi theo từng order/tenant/request.

**Không hứa “revoke token lập tức” nếu RS đang cache `active:true`.** Phải công bố và kiểm thử **revocation visibility SLA**: ví dụ “không quá 30 giây” chỉ khi kiến trúc/caches có cơ chế bảo đảm thực tế; đây là **ví dụ SLA**, không phải điều RFC bắt buộc.

## 19. Chọn fail-closed khi AS không truy cập được

Khi kết nối AS bị lỗi, RS có thể đứng trước yêu cầu availability. Nhưng **không được tự biến token chưa được xác minh thành active** để giữ API hoạt động.

### Mẫu hành vi sai

~~~text
try:
    result = introspect(token)
catch timeout:
    result.active = true    # NGUY HIỂM: fail-open
~~~

### Mẫu hành vi an toàn

~~~text
try:
    result = introspectViaTrustedEndpoint(token)
catch timeout / TLS failure / 5xx / malformed response:
    log SECURE_DEPENDENCY_FAILURE without raw token
    deny this request (service error as appropriate)
    do not create a new active token decision

if result.active == false:
    deny as invalid token (generic)
else:
    validate token purpose + issuer + aud + time + scope + proof
    enforce object-level access policy
~~~

**Ngoại lệ vận hành cần thiết kế rất kỹ:** một số hệ thống cân nhắc dùng **cache `active:true` chưa hết TTL theo policy** trong outage để giảm downtime. Cách này tạo cửa sổ chấp nhận token đã bị revoke; nó chỉ có thể chấp nhận nếu đã có **quyết định rủi ro rõ ràng, TTL nhỏ, `exp` không vượt và monitoring**. Không được coi đây là mặc định của OAuth/RFC 7662.

Nếu hệ thống yêu cầu revoke tức thời ở endpoint cực nhạy cảm, có thể phải **không cache active**, hoặc dùng kiến trúc token state/revocation sự kiện thay vì dựa trên cache lâu.

## 20. Java 17 + Jackson: đánh giá active nghiêm ngặt

Mã Java dưới đây minh họa **chỉ tầng quyết định trên JSON introspection đã nhận từ AS tin cậy**, không tự gọi mạng hoặc xác thực RS. Nó dùng Jackson Databind để parse JSON, **không ép kiểu `active`**, kiểm tra `iss`, `aud`, `scope`, `exp` và `nbf` theo policy.

Đây là một **RS policy cụ thể**: Orders API yêu cầu có issuer, audience, scope, `exp` và một hợp đồng AS bảo đảm introspection cho RS này chỉ trả **`active:true` đối với access token đúng usage**. Nếu provider không có bảo đảm đó, cần thêm **token purpose check** (ví dụ field extension) trước khi cho phép.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class IntrospectionDecision {
    private static final ObjectMapper JSON = new ObjectMapper();

    // Cấu hình từ issuer/client registration đáng tin cậy.
    private static final String EXPECTED_ISSUER =
            "https://auth.example.test";
    private static final String EXPECTED_AUDIENCE =
            "https://orders-api.example.test";
    private static final String REQUIRED_SCOPE = "orders:read";

    public enum Result {
        ACTIVE_AUTHORIZED_BY_TOKEN_POLICY,
        INACTIVE,
        WRONG_CONTEXT_OR_SCOPE,
        MALFORMED_RESPONSE
    }

    public static Result assess(String responseBody, Clock clock)
            throws IOException {
        JsonNode root = JSON.readTree(responseBody);
        if (root == null || !root.isObject()) {
            return Result.MALFORMED_RESPONSE;
        }

        JsonNode active = root.get("active");
        if (active == null || !active.isBoolean()) {
            return Result.MALFORMED_RESPONSE;
        }
        if (!active.booleanValue()) {
            return Result.INACTIVE;
        }

        if (!EXPECTED_ISSUER.equals(textField(root, "iss"))
                || !hasAudience(root.path("aud"), EXPECTED_AUDIENCE)
                || !hasExactScope(root.path("scope"), REQUIRED_SCOPE)) {
            return Result.WRONG_CONTEXT_OR_SCOPE;
        }

        JsonNode exp = root.path("exp");
        if (!exp.isIntegralNumber() || !exp.canConvertToLong()) {
            return Result.WRONG_CONTEXT_OR_SCOPE;
        }

        long now = clock.instant().getEpochSecond();
        if (now >= exp.longValue()) {
            return Result.WRONG_CONTEXT_OR_SCOPE;
        }

        JsonNode nbf = root.get("nbf");
        if (nbf != null) {
            if (!nbf.isIntegralNumber()
                    || !nbf.canConvertToLong()
                    || now < nbf.longValue()) {
                return Result.WRONG_CONTEXT_OR_SCOPE;
            }
        }

        // BẮT BUỘC thêm contract kiểm tra token usage:
        // AS-RS contract chỉ cho access token của Orders API active=true,
        // hoặc kiểm tra extension purpose = access_token.
        // Ngoài ra còn cần PoP proof + object-level authorization.
        return Result.ACTIVE_AUTHORIZED_BY_TOKEN_POLICY;
    }

    private static String textField(JsonNode root, String key) {
        JsonNode v = root.get(key);
        return v != null && v.isTextual() ? v.asText() : "";
    }

    private static boolean hasAudience(
            JsonNode audience, String expected
    ) {
        if (audience.isTextual()) {
            return expected.equals(audience.asText());
        }
        if (audience.isArray()) {
            for (JsonNode item : audience) {
                if (item.isTextual()
                        && expected.equals(item.asText())) {
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean hasExactScope(
            JsonNode value, String required
    ) {
        if (!value.isTextual()) {
            return false;
        }
        String scopeString = value.asText().trim();
        if (scopeString.isEmpty()) {
            return false;
        }
        Set<String> scopes =
                new HashSet<>(Arrays.asList(
                        scopeString.split("\\s+")
                ));
        return scopes.contains(required);
    }

    public static void main(String[] args) throws IOException {
        String activeResponse = """
                {
                  "active": true,
                  "iss": "https://auth.example.test",
                  "aud": "https://orders-api.example.test",
                  "scope": "orders:read",
                  "exp": 1800003600
                }
                """;
        Clock exampleClock = Clock.fixed(
                Instant.ofEpochSecond(1800000000),
                java.time.ZoneOffset.UTC
        );
        System.out.println(assess(activeResponse, exampleClock));
        System.out.println(assess(
                "{\"active\": false}", exampleClock
        ));
        // ACTIVE_AUTHORIZED_BY_TOKEN_POLICY
        // INACTIVE
    }

    private IntrospectionDecision() {}
}
~~~

### Ranh giới của ví dụ Java

1. **`assess` nhận JSON đã được adapter tin cậy thu từ AS.** Chưa có HTTP POST, RS client authentication, TLS, retry, size limits hoặc xác thực endpoint.
2. **`Result.ACTIVE_AUTHORIZED_BY_TOKEN_POLICY` chỉ có nghĩa qua các điều kiện token mà hàm đã kiểm tra**; chưa authorize một order cụ thể. Tên enum cố ý nhấn mạnh phạm vi.
3. **Token usage** bắt buộc có **AS–RS contract** (hoặc field extension đã kiểm tra). `token_type=Bearer` **không** thể thay token-purpose validation.
4. Code yêu cầu `exp`, `iss`, `aud` và `scope` theo chính sách Orders API dù RFC 7662 chỉ REQUIRED `active`. Đây là policy bảo thủ hợp lý cho ví dụ.
5. `aud` có thể biểu diễn dạng string hoặc array theo contract provider; thư viện cần kiểm tra đúng profile. Không nhận audience thiếu làm match.
6. `JsonNode` parsing không thay JSON size/depth/duplicate-key validation ở HTTP adapter. Production cần parse giới hạn, timeout, telemetry privacy.
7. Nếu `assess` trả `MALFORMED_RESPONSE`, HTTP adapter phải phân loại đó là **introspection protocol failure**, không tự biến thành `inactive` hoặc `active`.
8. Cần kiểm tra DPoP/mTLS proof nếu token sender-constrained, quyền object/tenant và policy thay đổi theo request.

## 21. Spring Security: cấu hình opaque token introspection

Trong ứng dụng Spring Boot/Spring Security có Resource Server support, có thể cấu hình opaque token introspection qua một issuer/endpoint **đã được xác nhận**. Ví dụ `application.yml` minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: "INJECT_FROM_SECRET_MANAGER_AT_DEPLOYMENT"
~~~

**Giá trị `client-secret` ở đây chỉ là placeholder, không phải mật khẩu thật.** Trong deployment, lấy từ secret manager/env injection/OS secret store theo policy; tuyệt đối không commit credential thật vào source control.

Ví dụ security rule ở Java/Spring Security 6, giả định introspector tạo `SCOPE_...` authorities từ `scope`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(requests -> requests
                .requestMatchers("/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
        );
        http.oauth2ResourceServer(oauth -> oauth
                .opaqueToken(withDefaults())
        );
        return http.build();
    }
}
~~~

**Phải bổ sung chính sách riêng:**

- Xác minh **issuer, audience, token usage và exp** theo contract AS; default framework introspector thường không biết tất cả audience/usage đặc thù của hệ thống.
- Kiểm tra **quyền trên order/tenant** trong service/method security, không chỉ `SCOPE_orders:read`.
- Bảo vệ introspection client credential và tránh log body.
- Thiết kế timeout/retry/fail-closed/caching theo nhu cầu revoke và phiên bản Spring đang dùng.
- Nếu token DPoP/mTLS-bound, cần kiểm tra **proof/certificate** tương ứng; không chỉ gọi opaqueToken().

**Spring Resource Server hỗ trợ introspection không có nghĩa OP/AS tự bảo đảm token đúng mục đích**. Test negative case refresh token/ID token substitution trong chính hệ thống của bạn.

## 22. Case study: ba token cùng AS nhưng khác trạng thái và mục đích

Giả sử AS `https://auth.example.test` cấp token cho Orders API và Billing API. RS `orders-api` gọi introspection bằng credential riêng; scope bắt buộc cho endpoint `GET /orders/123` là `orders:read`.

### Ba request chính

**Tình huống 1 — Token K1 đã bị revoke.**

~~~json
{
  "active": false
}
~~~

RS từ chối token. AS không cần tiết lộ K1 bị revoke hay expired.

**Tình huống 2 — Token K2 vẫn active nhưng dành cho Billing API.**

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://billing-api.example.test",
  "scope": "billing:read",
  "exp": 1800003600
}
~~~

Orders API **từ chối dù `active:true`**, vì audience và scope không đúng.

**Tình huống 3 — Token K3 active, đúng Orders audience và scope.**

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "sub": "user-42",
  "exp": 1800003600
}
~~~

RS còn phải kiểm tra thời gian, access-token usage, proof nếu có và **user-42 có thực sự được đọc order 123**. Nếu order thuộc user-99/tenant khác, vẫn trả `403` hoặc status phù hợp privacy policy.

### Một biến thể quan trọng: refresh token

Nếu RS gửi nhầm refresh token và AS trả `active:true` vì token còn hiệu lực để refresh, **Orders API không được coi nó là bearer access token**. Cần contract AS bảo đảm refresh token nhận `active:false` tại introspection context này hoặc mục đích token được trả rõ và kiểm tra.

### Một biến thể vận hành: AS timeout

Nếu AS không trả response, đó không phải `active:false`. RS **fail closed**, có thể trả 503 và cảnh báo hệ thống. Không báo “token expired” chỉ vì AS outage — user có thể không sửa được vấn đề bằng cách đăng nhập lại.

## 23. Audit và telemetry không lộ credential

Introspection có thể làm lộ token nếu app/gateway log **request body**:

~~~text
POST /introspect
token=<RAW_BEARER_TOKEN>    // KHÔNG GHI VÀO LOG
Authorization: Basic ...   // KHÔNG GHI VÀO LOG
~~~

Thay bằng event chỉ gồm định danh đã được pseudonymize và metadata tối thiểu:

~~~json
{
  "event_type": "security.introspection.checked",
  "occurred_at": "2026-11-23T10:15:00Z",
  "issuer": "https://auth.example.test",
  "resource_server": "orders-api",
  "token_ref": "hmac-reference-not-bearer-token",
  "result_category": "ACTIVE_POLICY_DENIED",
  "reason_category": "AUDIENCE_MISMATCH",
  "latency_ms": 18,
  "raw_token_logged": false
}
~~~

`raw_token_logged=false` trong ví dụ không chứng minh toàn bộ pipeline logs sạch; phải kiểm thử CDN, reverse proxy, APM, tracing, exception handlers và HTTP debug libraries.

### Các metric nên đo

- Tỷ lệ **`active:true`**, **`active:false`**, protocol failures, 401/403 introspection auth errors.
- Latency p50/p95/p99 và AS timeout.
- Cache hit ratio, TTL còn lại và thời gian revoke visibility.
- Wrong audience/issuer/scope/purpose denies (không log raw token).
- Tần suất RS credentials sai hoặc introspection unauthorized.
- Mức tăng abnormal introspection QPS/`kid`/token probing.

**Không gửi raw introspection response có user PII vào analytics** chỉ để tính tỷ lệ active. Giới hạn truy cập audit, retention, encryption và cơ chế xóa theo policy.

## 24. Ma trận kiểm thử active và inactive response

| Test | Dữ liệu/hành vi | Kết quả mong đợi |
|---|---|---|
| **T1 — Active boolean** | `{"active":true}` | Chỉ chuyển sang bước validate policy |
| **T2 — Inactive boolean** | `{"active":false}` | Từ chối token |
| **T3 — Active string** | `{"active":"true"}` | Reject malformed response |
| **T4 — Active number** | `{"active":1}` | Reject malformed response |
| **T5 — Missing active** | JSON có `scope` nhưng thiếu `active` | Reject malformed response |
| **T6 — Null active** | `{"active":null}` | Reject malformed response |
| **T7 — Invalid JSON** | AS trả HTML/JSON lỗi | Fail closed, protocol failure |
| **T8 — Unknown token** | AS không nhận biết token | `active:false`, không trả user metadata |
| **T9 — Expired token** | Token đã hết hạn | `active:false` hoặc reject theo policy; RS không allow |
| **T10 — Revoked token** | AS đã revoke | `active:false` tại context phù hợp |
| **T11 — Unauthorized RS** | RS hỏi token không thuộc quyền xem | AS không tiết lộ status/claims; `active:false` theo RFC 7662 |
| **T12 — Invalid RS credential** | Basic/mTLS credential sai | 401/403 phù hợp, **không** coi là active:false verdict |
| **T13 — AS 503** | Introspection unavailable | Fail closed, báo dependency outage |
| **T14 — Timeout** | AS không phản hồi đúng hạn | Fail closed, không tự allow |
| **T15 — Wrong issuer** | `active:true` nhưng `iss` sai | Từ chối |
| **T16 — Wrong audience** | `active:true` của Billing API tại Orders API | Từ chối |
| **T17 — Missing audience** | Response không `aud`, policy cần aud | Từ chối hoặc AS contract thay thế minh bạch |
| **T18 — Scope mismatch** | Token chỉ có `orders:read`, POST cần `orders:write` | 403 insufficient_scope |
| **T19 — Scope substring** | `orders:read:any` thay vì `orders:read` | Không được coi là scope match |
| **T20 — Object ACL** | Scope đúng nhưng order thuộc user khác | Từ chối |
| **T21 — Refresh token substitution** | RS introspect RT active | Không chấp nhận RT ở API |
| **T22 — ID token substitution** | OIDC ID token có signature hợp lệ | Không dùng làm API access token |
| **T23 — Token type hint** | `token_type_hint=access_token` nhưng token khác loại | Không tự tin là access token; AS/RS validate purpose |
| **T24 — exp boundary** | `now==exp` | Từ chối |
| **T25 — nbf future** | `nbf > now` | Từ chối |
| **T26 — DPoP/mTLS proof missing** | Active token có `cnf` nhưng không có proof hợp lệ | Từ chối |
| **T27 — Cached active after revoke** | AS revoke khi RS cache chưa hết TTL | Quan sát giới hạn revoke SLA; không tuyên bố thu hồi tức thời |
| **T28 — Cache past exp** | Cached verdict active, token `exp` đã qua | Từ chối, không cache vượt exp |
| **T29 — Cache context confusion** | Hai RS hoặc hai issuer dùng cùng token ref/key | Không dùng cache verdict chéo |
| **T30 — Introspection log privacy** | Canary token qua staging/proxy/APM | Không có raw token/credentials/PII trong logs |
| **T31 — HTTP GET leak** | Client cố gửi token trong query | Thiết kế không sử dụng GET cho bearer token |
| **T32 — Untrusted introspection URL** | JWT/header/user input chứa endpoint ngoài issuer | Không fetch, không leak token sang attacker |
| **T33 — Duplicate claim/type** | Response có trường active trùng hoặc sai schema | Parser policy từ chối ambiguous response |
| **T34 — No-store** | AS trả Cache-Control no-store | RS không cache response |
| **T35 — Provider-specific purpose** | `token_use` extension thiếu/sai trong profile bắt buộc | Từ chối, không đoán loại token |
| **T36 — Client credential expiry** | RS auth secret hết hạn/rotate | Cảnh báo và fail closed, không chấp nhận token “tạm” |

Thực hiện test bằng **AS mock/staging và token giả**, không dùng raw credential production trong HAR, bug report, CI logs hay screenshot.

## 25. Checklist triển khai Active và inactive response

1. **Dùng RFC 7662 introspection** trên endpoint AS/issuer tin cậy và **POST form-urlencoded**, không gửi token trong URL.
2. **Xác thực Resource Server/introspection client** với AS, hạn quyền per RS/audience và bảo vệ credential trong secret store.
3. **Dùng TLS/HTTPS**, xác minh certificate, chặn redirect lạ, timeout và giới hạn response body/JSON parser.
4. **Kiểm tra HTTP status độc lập `active`**: 200 JSON verdict khác 401 RS credentials, 400 malformed, 5xx/timeout.
5. **Yêu cầu `active` đúng boolean**; missing, string, number, null hoặc JSON lỗi đều fail closed.
6. **Với `active:false`, deny**; không đòi lý do, không để AS rò token metadata.
7. **Với `active:true`, tiếp tục validate** issuer, audience, expiry/nbf, scope, token purpose và context.
8. **Ngăn refresh/ID/code/device token substitution**; `token_type_hint` và `token_type=Bearer` không đủ chứng minh usage.
9. **So khớp scope chính xác**, không dùng substring; không tự suy scope nếu thiếu.
10. **Kiểm tra audience/resource** theo RS policy; active token dành API khác vẫn phải reject.
11. **Kiểm tra quyền object/tenant/user** trên mỗi request; active + scope không tự cấp quyền đọc mọi object.
12. **Sender-constrained token cần PoP proof** DPoP/mTLS và `cnf` binding; active không thay proof.
13. **Không log raw token, Basic/mTLS credentials, introspection body hoặc PII không cần thiết**.
14. **Nếu cache response được cho phép**, dùng TTL ngắn, partition theo issuer/RS context, tôn trọng `exp` và `no-store`, không cache vượt revocation SLA.
15. **Fail closed khi AS unavailable**, phân biệt outage với token inactive trong telemetry/user experience.
16. **Theo dõi audit** active/denied/error rate, latency, cache hit, revocation visibility, audience/purpose mismatch.
17. **Kiểm thử trường hợp âm tính**: token revoked/expired/unknown, RS unauthorized, bad JSON, wrong issuer/audience/scope, RT substitution, DPoP proof, cache stale.
18. **Thực hiện theo contract AS–RS rõ ràng** cho các field RFC optional và extension purpose, không tự tạo default cấp quyền.
19. **Đừng nhầm access token JWT và opaque**: cả hai có thể introspect tùy AS; JWT vẫn cần signature/profile validation nếu dùng local verification.
20. **Giữ tách biệt trách nhiệm**: AS quyết định trạng thái/grant, RS quyết định access token có đúng audience/scope/usage và quyền resource hay không.

**Kết luận:** trong Token Introspection, **`{"active":true}` có nghĩa token được AS xem đang hoạt động**, không phải toàn bộ quyết định phân quyền; **`{"active":false}` có nghĩa RS không được dựa vào token đó**, nhưng không tiết lộ lý do cụ thể. Chỉ khi **endpoint/RS authentication, JSON schema, type/usage, issuer, audience, thời hạn, scope, sender proof và quyền dữ liệu** đều phù hợp mới được cho phép request. Mọi lỗi mạng, AS outage, response không hợp lệ và cache quá hạn đều phải **fail closed** thay vì vô tình chuyển thành quyền truy cập.

### Tài liệu chuẩn và tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request/response `active`, metadata, bảo vệ endpoint và cache.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token/client/grant semantics và lỗi token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token transport, `invalid_token`, `insufficient_scope` và `WWW-Authenticate`.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token misuse, revocation/replay và OAuth security.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): AS revoke token/grant và hiệu ứng liên quan.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `introspection_endpoint` và discovery metadata.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): audience/resource targeting.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, `typ` và claims.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token và proof binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS/certificate-bound tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token được xác minh ở client, không dùng thay API access token.
- [Spring Security — OAuth2 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình introspection client và API authorization.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): token validation, security boundaries và best practices.
