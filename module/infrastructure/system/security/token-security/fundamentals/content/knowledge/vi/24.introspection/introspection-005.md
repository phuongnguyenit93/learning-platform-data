# Response claims từ introspection

Một **Invoice API** nhận request kèm chuỗi access token `Authorization: Bearer ...`. Token này có thể là **opaque token** mà API không tự đọc được. API gọi **introspection endpoint** của Authorization Server (AS) để hỏi: *“Token này có đang active không, nó được phát cho client/subject nào, dành cho tài nguyên nào, có scope gì và còn hạn tới khi nào?”* AS trả về **JSON chứa các claims của introspection response**. Resource Server (RS) phải hiểu từng claim đúng giao thức và **không cho phép thao tác chỉ vì thấy `active=true`**.

Chủ đề **“Response claims từ introspection”** thuộc chương **Introspection** trong module **Security Token Security Fundamentals**. Nội dung tập trung vào **RFC 7662 — OAuth 2.0 Token Introspection**: claim `active` bắt buộc, các claims tùy chọn `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss`, `jti`; ngữ nghĩa xác thực/phân quyền; JSON types; cache, revocation; xử lý JWT/opaque, bearer/sender-constrained token; và các kiểm tra cần thực hiện trước khi trả dữ liệu cho caller.

**Điểm cốt lõi:** Introspection là **AS cung cấp thông tin trạng thái token cho một bên được phép hỏi**, chứ không phải API “đọc token rồi tự nhận mọi claim đều đúng”. Một response `{"active":true}` chỉ xác nhận điều kiện active **theo AS tại thời điểm kiểm tra**. RS vẫn phải kiểm **issuer/trust context, audience, scope, thời hạn theo hợp đồng, loại token, subject/client binding và quyền trên từng tài nguyên**.

## 1. Introspection nằm ở đâu trong mô hình OAuth?

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **OAuth Client** | Invoice Web hoặc Billing Worker | Nhận access token rồi gửi đến Invoice API |
| **Authorization Server** | `https://auth.example.test` | Phát, quản lý trạng thái token và trả introspection response |
| **Resource Server** | Invoice API | Xác minh token và quyết định quyền truy cập API |
| **Người dùng/Resource Owner** | An, nếu là user-delegated grant | Có thể là chủ thể/nguồn phê duyệt grant; không hiện diện với mọi `client_credentials` |
| **Introspection endpoint** | `https://auth.example.test/oauth2/introspect` | Endpoint **được bảo vệ** để RS hoặc bên được ủy quyền hỏi thông tin token |

Một request tới Invoice API đi theo luồng:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant RS as Invoice API / Resource Server
    participant AS as Authorization Server
    C->>RS: GET /invoices/INV-42, Bearer token T1
    RS->>AS: POST /introspect với T1 + credential của RS
    AS->>AS: Xác thực/ủy quyền caller introspection
    AS->>AS: Xác định trạng thái và claims có thể tiết lộ
    AS-->>RS: JSON active, scope, client_id, sub, aud, iss, exp...
    RS->>RS: Kiểm active, audience, issuer, scope, thời gian
    RS->>RS: Kiểm tenant và chủ sở hữu INV-42
    alt Tất cả điều kiện đều đạt
        RS-->>C: 200 hóa đơn được phép xem
    else Token/quyền không phù hợp
        RS-->>C: 401 hoặc 403 theo loại lỗi
    end
~~~

Có **hai kênh tin cậy**:

1. **Client → RS:** Access token được trình bày để chứng minh quyền gọi API theo OAuth. RS không được tin các claims do caller tự chèn ngoài token.
2. **RS → AS:** RS dùng **credential/ủy quyền riêng** để gọi introspection endpoint, qua TLS với AS đã cấu hình. Access token T1 là **đối tượng được kiểm tra**, không phải mặc nhiên là credential cho RS truy cập introspection endpoint.

**Đừng nhầm:** `client_id` của **token được introspect** thường là OAuth client đã nhận token; `client_id`/credential dùng **xác thực RS khi gọi introspection** có thể là **một client registration khác**. Trộn hai định danh này dễ dẫn tới cấp quyền sai hoặc log sai chủ thể.

## 2. Request và response theo RFC 7662

RS gửi request HTTP **POST**, body mã hóa `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-rs-introspection-credential>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<percent-encoded-opaque-access-token>&token_type_hint=access_token
~~~

- `token`: **bắt buộc**, chính chuỗi token cần kiểm. Trong POST form thực tế phải **URL-encode** giá trị token đúng cách, không nối chuỗi thô vào URL.
- `token_type_hint`: **tùy chọn**, gợi ý loại token để AS tra cứu hiệu quả; giá trị thường gặp là `access_token` hoặc `refresh_token` theo registry/hợp đồng. **Hint không phải bằng chứng về token type**, và AS không được tin hint thay token thực.
- `Authorization: Basic ...`: trong ví dụ là cách **RS xác thực/được ủy quyền** truy cập introspection endpoint. Các AS khác có thể hỗ trợ mTLS/private key hoặc cơ chế được bảo vệ khác. Không gửi client secret trong URL hoặc hardcode trong source.

### Response khi token active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "invoice:read invoice:export",
  "client_id": "invoice-web",
  "username": "an@example.test",
  "token_type": "Bearer",
  "exp": 1800000900,
  "iat": 1800000000,
  "nbf": 1800000000,
  "sub": "user:an",
  "aud": ["invoice-api"],
  "iss": "https://auth.example.test",
  "jti": "illustrative-token-id-01"
}
~~~

Đây là **ví dụ đầy đủ để học claims**, không phải mọi AS đều trả đủ trường. Theo RFC 7662, **chỉ `active` bắt buộc**; các claim khác **tùy chọn** và AS có thể lọc theo quyền của RS. Chính vì vậy hệ thống production phải **đàm phán một response contract**: API cần claim nào, nếu thiếu thì từ chối hay sử dụng một nguồn tin cậy thay thế, và quyền tiết lộ thông tin của AS là gì.

### Response khi token inactive

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"active":false}
~~~

**HTTP 200 + `active=false` là một kết quả introspection hợp lệ**, không phải lỗi mạng. RFC 7662 khuyến nghị **không bổ sung claims khác ngoài `active`** khi token inactive, để tránh rò dữ liệu token không hợp lệ/đã thu hồi/không thể tiết lộ cho caller.

Khi nhận `active=false`, RS phải **không chấp nhận token đó để truy cập API**, bất kể client gửi `scope` hay `sub` gì trong request. Trạng thái inactive có thể bao gồm token không tồn tại, không còn active, hết hạn hoặc không được tiết lộ cho RS theo policy; **đừng dùng response để dò nguyên nhân chi tiết rồi tiết lộ cho caller không tin cậy**.

### HTTP 401 khác `active=false`

Nếu **RS không được phép gọi introspection** (ví dụ credential sai/hết hạn), AS có thể trả lỗi HTTP 401 theo cơ chế bảo vệ endpoint. Điều đó **không chứng minh access token của người dùng inactive**; nó chứng minh kiểm tra introspection **không thực hiện được một cách đáng tin**. RS không được “fail open” và cho request qua chỉ vì introspection unavailable.

## 3. Claim bắt buộc: `active` có nghĩa chính xác gì?

**`active`** là **JSON boolean bắt buộc**:

~~~json
{"active":true}
~~~

hoặc:

~~~json
{"active":false}
~~~

Không dùng dạng string `"true"`, số `1`, giá trị `null` hoặc trường vắng mặt để thay boolean. Một RS triển khai nghiêm ngặt nên **từ chối response sai schema** thay vì ép kiểu kiểu JavaScript/Python tùy tiện.

### Active dưới góc nhìn AS

Theo RFC 7662, `active=true` thường chỉ một token đã được AS phát, còn trong lifetime hợp lệ và chưa bị revoke; AS có thể áp dụng **thêm điều kiện của mình** khi xác định active, như trạng thái client hoặc quyền introspection của RS.

Nhưng active **không tự khẳng định**:

- Token thuộc **đúng issuer** mà Invoice API đã cấu hình tin cậy.
- Token có **audience dành cho Invoice API**.
- Token có `invoice:read` hoặc `invoice:approve`.
- Token là **access token** (không phải refresh token hoặc token loại khác).
- Token đã được sender-bound proof kiểm hợp lệ trong **request hiện tại**.
- User hoặc service có quyền đọc **hóa đơn cụ thể** hoặc truy cập tenant hiện tại.
- Introspection response sẽ mãi giữ trạng thái như vậy trong cache.

### Active false không phải một error code phân loại nguyên nhân

Không thêm logic:

~~~text
if active=false and "exp" absent:
    assume revoked
else if active=false and "sub" absent:
    assume token never existed
~~~

Các claims trên **không bắt buộc** ngay cả khi active, nên không thể suy trạng thái chi tiết từ việc thiếu chúng. RS nên biến `active=false` thành **token không chấp nhận được** và trả phản hồi thích hợp theo API security policy, không xây endpoint cho caller dò “token đã từng tồn tại hay chưa”.

## 4. Bảng tất cả response claims chuẩn của RFC 7662

| Claim | Kiểu JSON theo RFC 7662 | Ý nghĩa | Điều RS cần nhớ |
|---|---|---|---|
| **`active`** | **boolean, bắt buộc** | AS xác định token hiện có active không | `true` chưa đủ để cho phép API |
| `scope` | **string**, tùy chọn | Danh sách OAuth scope **cách nhau bằng dấu cách** | Phải kiểm scope từng giá trị, không substring |
| `client_id` | **string**, tùy chọn | Định danh OAuth client được cấp token | Không phải subject/end user hoặc bí mật |
| `username` | **string**, tùy chọn | Tên người dùng dạng dễ đọc cho Resource Owner đã ủy quyền | Không phù hợp làm khóa định danh/authorization bất biến |
| `token_type` | **string**, tùy chọn | Cách sử dụng token theo OAuth token type, ví dụ `Bearer` | `Bearer` không tự chứng minh token là access token đúng purpose |
| `exp` | **JSON number** mang NumericDate, tùy chọn | Thời điểm token không còn được chấp nhận theo expiry | Đơn vị **giây từ Unix epoch**, không phải milliseconds |
| `iat` | **JSON number** mang NumericDate, tùy chọn | Thời điểm token được phát hành | Không phải `auth_time` của OIDC |
| `nbf` | **JSON number** mang NumericDate, tùy chọn | Không được dùng token trước thời điểm này | Không chấp nhận quá sớm, xử lý clock skew có giới hạn |
| `sub` | **string**, tùy chọn | Subject mà token được phát trong ngữ cảnh issuer | Không mặc nhiên là end user với `client_credentials` |
| `aud` | **string hoặc mảng string**, tùy chọn | Intended audience/resource(s) của token | Check **đúng audience của RS**, không check host bằng contains |
| `iss` | **string**, tùy chọn | Issuer của token | Kiểm trusted issuer theo contract; không lấy từ input caller |
| `jti` | **string**, tùy chọn | Định danh token | Không phải bằng chứng code/token single-use tự động |

**Quan trọng:** Trong RFC 7662, các claims ngoài `active` **đều tùy chọn về mặt giao thức**. Một Invoice API production có thể yêu cầu `iss`, `aud`, `exp` và `scope` theo **hợp đồng nội bộ với AS**; đó là **policy nghiêm hơn RFC**, không phải kết luận rằng RFC buộc mọi AS trả chúng.

### Có thể có claims mở rộng

RFC 7662 cho phép sử dụng những trường bổ sung theo registry/profile/AS contract, ví dụ:

- `cnf` để biểu diễn token binding khi profile sender-constrained hỗ trợ.
- `authorization_details` trong hệ thống dùng Rich Authorization Requests (RFC 9396) theo contract.
- `tenant_id`, `roles` hoặc `permissions` do AS định nghĩa.
- Claim mô tả token class, grant hoặc session với tên riêng, nếu AS/RS có agreement.

**Không được tin claims mở rộng chỉ vì chúng có mặt.** Cần xác định issuer nào phát, schema/type, tính toàn vẹn/truyền qua TLS, thẩm quyền quyết định, thời hạn và ai được phép nhìn thấy. **`tenant_id` do AS phát đáng tin không tự thay kiểm ownership trên từng bản ghi**.

## 5. Đọc `scope`: string không phải array

Theo RFC 7662, `scope` **nếu được trả về** là một **JSON string** chứa danh sách scope cách nhau bởi **dấu cách**:

~~~json
{
  "active": true,
  "scope": "invoice:read invoice:export"
}
~~~

Không được tự giả định response sẽ là:

~~~json
{
  "active": true,
  "scope": ["invoice:read", "invoice:export"]
}
~~~

Mảng ở ví dụ thứ hai **không phải định dạng `scope` chuẩn RFC 7662**. Nếu một AS mở rộng schema với định dạng khác, cần adapter rõ hợp đồng; không âm thầm coerce mọi loại dữ liệu hoặc coi lỗi schema là “được cấp mọi scope”.

### So scope theo phần tử nguyên vẹn

~~~text
scope = "invoice:read invoice:export"

Need invoice:read    -> MATCH
Need invoice:approve -> NO MATCH
Need invoice         -> NO MATCH
Need read            -> NO MATCH
~~~

**Không dùng:**

~~~java
// SAI: match bằng substring, "invoice:read-all" cũng chứa "invoice:read".
boolean allowed = scopeString.contains("invoice:read");
~~~

**Dùng:** tách chuỗi theo space, loại phần tử rỗng theo parser hợp lệ rồi so **chính xác, case-sensitive** từng scope. `invoice:read` khác `Invoice:Read` trừ khi một profile riêng quy định normalization.

Scope là **điều kiện cần**, không phải mọi quyền dữ liệu: token có `invoice:read` nhưng subject ở tenant A vẫn không được đọc hóa đơn tenant B.

## 6. `client_id`, `sub` và `username`: ba danh tính khác nhau

Ví dụ user-delegated token:

~~~json
{
  "active": true,
  "client_id": "invoice-web",
  "sub": "user:an",
  "username": "an@example.test",
  "scope": "invoice:read",
  "aud": "invoice-api"
}
~~~

Đọc chính xác:

- **`client_id=invoice-web`:** OAuth client đã nhận token theo grant.
- **`sub=user:an`:** subject của token theo issuer/profile; có thể được dùng để ràng buộc identity trong API **sau khi xác minh đúng issuer và contract**.
- **`username=an@example.test`:** tên hiển thị/dễ đọc, có thể đổi hoặc không duy nhất; **không dùng làm khóa authorization ổn định**.

### Với `client_credentials` có khác không?

~~~json
{
  "active": true,
  "client_id": "billing-worker",
  "scope": "invoice:sync",
  "aud": ["invoice-api"],
  "iss": "https://auth.example.test",
  "exp": 1800000900
}
~~~

Đây là token minh họa cho **workload**, không đại diện một end user đang tương tác. `sub` hoặc `username` có thể **vắng**; trong một số profile, `sub` có thể là **service/client identity**, không phải người dùng. **Không tự tạo `user_id=client_id` hoặc gán quyền người dùng cho workload chỉ vì có claim `client_id`**.

Nếu API có hai chế độ **delegated user** và **service-to-service**, cần phân biệt token class/purpose theo hợp đồng AS/RS và phân quyền theo từng chế độ; không dùng sự hiện diện/thiếu vắng `sub` như phép phân loại đáng tin duy nhất.

## 7. `aud`, `iss` và `token_type`: đúng đích, đúng nguồn, đúng purpose

### Audience là nơi token được phép dùng

`aud` có thể là **string**:

~~~json
{"active":true,"aud":"invoice-api"}
~~~

hoặc **mảng string**:

~~~json
{"active":true,"aud":["invoice-api","reporting-api"]}
~~~

Invoice API chỉ chấp nhận token nếu **audience đúng với định danh RS đã cấu hình**. Không so `aud` bằng `contains("invoice")`, bằng suffix URL hoặc giả định vì token còn active tại AS thì token dùng được ở mọi API.

Nếu `aud` **vắng** nhưng API bắt buộc audience isolation, response đó **không đạt policy**. Không tự suy audience từ đường HTTP request, từ hostname proxy hoặc từ `client_id`.

### Issuer là trust boundary

`iss` mô tả issuer của token. RS phải nhận introspection response từ **AS được cấu hình tin cậy**, và nếu có `iss` theo contract, so **chính xác** với issuer dự kiến:

~~~text
Expected issuer: https://auth.example.test
Received iss:    https://other.example.test
Decision:        REJECT
~~~

Đừng chọn introspection URL một cách tùy ý dựa vào token/HTTP header do caller gửi. Một API hỗ trợ nhiều issuer cần mapping rõ **issuer → introspection endpoint → credential → audience/policy**, tránh OAuth mix-up/token substitution.

### `token_type` nói gì?

`token_type="Bearer"` cho biết kiểu **cách trình bày/sử dụng token** theo hợp đồng OAuth, không đủ để kết luận “đây chắc chắn là access token, không thể là refresh token”. `token_type_hint=access_token` trong request cũng chỉ là **gợi ý**.

Resource Server cần biết **token purpose** bằng profile/AS contract và điều kiện AS kiểm tra; không được chấp nhận refresh token như access token chỉ vì introspection trả `active=true` hoặc một caller tự khai token type. Nếu AS hỗ trợ introspection nhiều token classes, phải có **bảo vệ phân biệt loại token** và quyền introspection theo RS.

## 8. `exp`, `iat`, `nbf` và `jti`: thời gian và định danh

Trong introspection response, thời điểm như `exp`/`iat`/`nbf` là **NumericDate theo đơn vị giây Unix epoch**:

~~~json
{
  "active": true,
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900,
  "jti": "illustrative-token-id-01"
}
~~~

### Kiểm thời gian độc lập với `active`

| Điều kiện | Ý nghĩa |
|---|---|
| `now < nbf` | Token chưa tới thời điểm được phép sử dụng |
| `now >= exp` | Token đã hết hạn |
| `iat` xa trong tương lai bất hợp lý | Có thể sai clock/issuer hoặc dữ liệu không hợp lệ |
| `jti` trùng của token khác | Có thể dùng cho audit/dedupe theo profile, không tự ngăn replay |

AS thường đã tính thời gian khi trả `active`, nhưng RS có thể **kiểm thêm** dựa trên `exp`/`nbf` theo contract. Một thời hạn cache của RS **không được vượt `exp`** khi response chứa claim này. Lưu ý sự khác biệt giữa **epoch seconds** và **epoch milliseconds**: nhầm đơn vị có thể làm token được chấp nhận sai rất lâu hoặc bị loại sai.

### `jti` có chống replay không?

`jti` là **token identifier**, **không phải cơ chế proof-of-possession**. Một bearer token có `jti` cố định vẫn có thể bị sao chép; RS kiểm chữ ký/trạng thái và có thể dùng `jti` trong denylist/revocation/audit **nếu có thiết kế đồng bộ**, nhưng không mặc nhiên ép **mỗi API request** dùng token một lần vì như vậy có thể phá hành vi access token bình thường.

### `auth_time` không phải `iat`

Trong OIDC, `auth_time` (nếu được phát theo profile) mô tả **thời điểm end-user authentication**, còn `iat` của introspected access token là **thời điểm token được phát hành**. Nếu API cần authentication freshness/ACR cho thao tác nhạy cảm, phải có **claims hoặc trust contract** phù hợp (ví dụ RFC 9470 step-up), không tự suy “token mới cấp” nghĩa là “user vừa nhập lại mật khẩu/MFA”.

## 9. Quy trình xử lý của Resource Server: `active=true` chưa đủ

Một API an toàn cần biến introspection response thành **quyết định có nhiều tầng**, không chỉ kiểm một flag.

~~~mermaid
flowchart TD
    A["API nhận access token trong Authorization header"] --> B{"Có đúng một Bearer token, đúng scheme/profile?"}
    B -- "Không" --> X["401 theo OAuth Bearer policy"]
    B -- "Có" --> C["Gọi trusted introspection endpoint với RS authentication"]
    C --> D{"Kết nối và JSON response có được xác minh?"}
    D -- "Không" --> Y["Fail closed / 503 hoặc 401 theo policy"]
    D -- "Có" --> E{"active là boolean true?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Issuer, audience, token purpose hợp lệ?"}
    F -- "Không" --> X
    F -- "Có" --> G{"exp, nbf và sender proof hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H{"Scope và quyền nghiệp vụ phù hợp?"}
    H -- "Không" --> Z["403 hoặc response từ chối theo policy"]
    H -- "Có" --> I["Thực hiện API, chỉ trả dữ liệu được phép"]
~~~

Thứ tự cụ thể của một middleware có thể khác, nhưng các **bất biến** không đổi:

1. **Trích token đúng kênh**: dùng `Authorization: Bearer <token>` theo RFC 6750 khi hỗ trợ Bearer; không ưu tiên query string hoặc token từ header tự đặt không tin cậy.
2. **Gọi đúng AS**: endpoint/issuer được cấu hình trước hoặc chọn qua mapping tin cậy, TLS được kiểm và RS có quyền introspection.
3. **Xử lý response đúng type**: `active` phải là boolean; `active=false` hoặc sai schema không dẫn tới allow.
4. **Kiểm token purpose và binding**: response phải mô tả token được phép dùng tại chính RS, đúng audience, issuer và grant/profile dự kiến; nếu là sender-constrained thì cần proof ở request.
5. **Kiểm thời hạn**: `exp`/`nbf` và cache deadline (nếu áp dụng) đúng chính sách, không dùng dữ liệu stale ngoài hạn.
6. **Kiểm scope/role/tenant/object**: chỉ allow sau khi tất cả điều kiện nghiệp vụ phù hợp.

### Ví dụ hai request với cùng `active=true`

~~~text
Introspection response A:
  active = true
  aud = ["invoice-api"]
  scope = "invoice:read"
  sub = "user:an"

Call GET /invoices/INV-42 (thuộc user:an):
  có thể được allow sau khi kiểm issuer, expiry, ownership.

Introspection response B:
  active = true
  aud = ["payments-api"]
  scope = "invoice:read"
  sub = "user:an"

Call GET /invoices/INV-42:
  REJECT vì token không dành cho Invoice API.
~~~

Ngay cả response A không cho An đọc hóa đơn của Bình hoặc tenant khác. **Active = trạng thái token**, còn **authorization = quyền của request cụ thể**.

### Introspection không thay authentication của client gọi API

Với Bearer token, người giữ token có thể thử sử dụng nó. `active=true` không chứng minh caller hiện tại là chủ nhân ban đầu của token. Nếu threat model đòi proof-of-possession, cần sender constraint (DPoP/mTLS) và kiểm proof, không trông chờ `sub` hay `client_id` tự giải quyết vấn đề token theft.

## 10. JWT và opaque token khi dùng introspection

**Opaque token** thường chỉ là một chuỗi tham chiếu. RS không tự phân tích được claims mà cần hỏi AS. **JWT access token** có thể được RS kiểm offline qua chữ ký/JWKS và claims theo profile, nhưng vẫn có thể được thiết kế dùng **introspection** nếu cần trạng thái động (revoke/grant status).

| Đặc điểm | Opaque token + introspection | JWT access token offline | JWT + introspection |
|---|---|---|---|
| RS đọc nội dung token trực tiếp? | Không | Có, nhưng phải **xác minh chữ ký/claims** | Có thể, nhưng không thay kiểm response |
| Kiểm token active/revoke tại AS | Qua introspection | Không tự có nếu chỉ kiểm offline | Qua introspection theo policy |
| Phụ thuộc availability của AS lúc gọi | Có, trừ cache có kiểm soát | Không đối với local signature validation | Có, trừ cache có kiểm soát |
| Audience và scope | Dựa trên response AS + local policy | Dựa trên JWT đã xác minh + local policy | Cần nguồn dữ liệu nhất quán và quy tắc ưu tiên rõ |
| Revocation propagation | Phụ thuộc AS và cache introspection | Có thể trễ tới `exp` nếu không có denylist/version check | Phụ thuộc AS, cache và cơ chế kết hợp |

### Nếu JWT và introspection response khác nhau thì sao?

Một ví dụ:

~~~text
JWT đã xác minh:
  aud = invoice-api
  scope = invoice:read
  exp = 1800000900

Introspection response từ AS:
  active = true
  aud = ["payments-api"]
  scope = "payment:read"
~~~

Đây là **mâu thuẫn trust contract**. Không chọn tập quyền rộng hơn, không trộn `aud` từ JWT với `scope` từ response để “ghép” ra token có thêm quyền. Thiết kế phải định nghĩa **nguồn authority**, token profile và cách kiểm consistency; khi không thể xác minh nhất quán, **fail closed và cảnh báo**.

### Không gửi ID token/refresh token tới Resource Server

OIDC **ID token** dùng để RP xác minh end-user authentication, thường có `aud` dành cho client. **Refresh token** dùng ở token endpoint để xin access token mới. RS không dùng ID/refresh token thay access token chỉ vì AS có thể introspect chúng.

`token_type_hint` không quyết định việc sử dụng token; server phải kiểm chính **token class** theo thỏa thuận AS/RS. Nếu introspection response không có thông tin phân loại token đủ tin cậy cho một RS có nhiều loại token, phải thay đổi hợp đồng AS/RS hoặc từ chối trường hợp mơ hồ.

## 11. Introspection cache: tính toán TTL, hạn revoke và race

Gọi AS introspection cho **mỗi API request** cho trạng thái cập nhật hơn nhưng tốn network latency/AS capacity. Nhiều RS triển khai cache kết quả theo token và chính sách. Đây là một tối ưu hóa có **đánh đổi bảo mật**: token đã bị revoke có thể tiếp tục được chấp nhận trong cửa sổ cache.

### Mô hình thời gian

~~~text
T0  RS introspect T1 -> active=true, exp=T0+15 phút.
T1  RS cache kết quả tối đa 15 giây theo policy.
T2  AS revoke T1 vào giây thứ 3.
T3  RS vẫn có thể dùng active=true cũ tới khi TTL hết
    nếu chưa có invalidation/sự kiện revoke nào khác.
T4  RS introspect lại -> active=false và từ chối.
~~~

Nếu hệ thống cần thu hồi **gần như tức thì**, cache TTL dài sẽ không đáp ứng. Cần ngắn TTL hoặc cơ chế invalidation/introspection theo mọi request, cân đối SLO và capacity.

### Công thức TTL an toàn

Giả sử response active, có `exp`, RS biết `now` tin cậy và cấu hình `maxIntrospectionCacheAge`:

\[
TTL_{\mathrm{effective}} =
 \max\Bigl(0,\;\min(
    TTL_{\mathrm{configured}},
    \mathrm{exp}-\mathrm{now}-\Delta
 )\Bigr)
\]

Trong đó `Δ` là safety margin cho clock skew, response/network latency và request duration. **RFC 7662 yêu cầu không cache response vượt quá `exp` nếu claim `exp` có mặt.** TTL policy còn có thể ngắn hơn vì yêu cầu tốc độ revoke.

Ví dụ:

~~~text
Introspection: active=true, exp còn 9 phút.
RS configured max cache age: 20 giây.
Safety margin: 5 giây.

Usable cache TTL = min(20 s, khoảng 9 phút - 5 s)
                 = 20 giây.

Nếu exp chỉ còn 4 giây:
  TTL = max(0, min(20, 4-5)) = 0 giây.
  Không cache/không dùng dữ liệu cận hết hạn.
~~~

Nếu response `active=true` **không có `exp`**, RFC vẫn cho phép không có claim đó, nhưng hệ thống yêu cầu expiry assurance có thể **từ chối** hoặc chỉ dùng quyết định tại thời điểm truy vấn theo contract. **Không tự chọn cache TTL vô hạn** khi `exp` vắng.

### Cache key phải phân vùng theo quyền hỏi

AS có thể trả **nội dung introspection khác nhau cho các protected resources khác nhau**. Vì vậy không nên có cache global:

~~~text
BAD:
  cache[rawAccessToken] = introspectionResponseForInvoiceApi

Payment API:
  đọc lại response đó dù không có quyền thấy cùng claims.
~~~

Key nên chứa context:

~~~text
IntrospectionCacheKey {
  tokenDigest: HMAC-SHA256(token, server-side cache-key secret)
  trustedIssuer: "https://auth.example.test"
  resourceServerIdentity: "invoice-api"
  expectedAudience: "invoice-api"
  policyVersion: "v3"
}
~~~

Không lưu **raw bearer token** làm cache key có thể xuất hiện trong log/Redis UI/metrics. Hash/HMAC chỉ là biện pháp giảm lộ qua key; **cache value vẫn là thông tin nhạy cảm** và nếu thiết kế cần giữ token string thì phải bảo vệ nó theo cùng threat model. HMAC key phải được lưu an toàn và có rotation policy.

### Có nên cache `active=false`?

Negative caching có thể giảm tải khi attacker spam token không hợp lệ, nhưng có nguy cơ **làm quyết định sai/stale** trong những hệ thống eventual consistency và tạo kênh dò trạng thái. Nếu cần, áp dụng TTL **rất ngắn, giới hạn theo nguồn và policy**, hoặc không negative-cache. Không bao giờ diễn giải một entry `active=false` hết hạn thành `active=true`.

### Có được cache khi response có `Cache-Control: no-store`?

**Phải tôn trọng HTTP cache-control và hợp đồng của AS.** RFC 7662 cho phép RS sử dụng cache có kiểm soát, nhưng không cấp quyền bỏ qua response/cache policy cụ thể mà AS đã áp dụng. Không đưa raw introspection response ra CDN/shared public cache; application-level caching cần được phê duyệt trong trust contract, có TTL, quyền truy cập và invalidation.

### 401 muộn và cache versioning

Nếu RS lưu kết quả active của token theo phiên bản policy, khi policy đổi hoặc nhận sự kiện revoke phải **invalidate đúng entry/phiên bản**. Đừng để response introspection cũ từ request song song **ghi đè** trạng thái revoked mới trong cache. Có thể dùng version/CAS hoặc watermark thời điểm xử lý, thay vì “response đến cuối thì thắng”.

## 12. Lỗi introspection: 401, 403, 429, 5xx và fail closed

Một RS không nên chỉ xử lý `HTTP 200 + JSON` và coi mọi lỗi khác như “token inactive”. Hãy phân biệt:

| Tín hiệu từ AS/HTTP | Ý nghĩa | Hành vi RS |
|---|---|---|
| **`200 {"active":true,...}`** | Token đang active theo AS | Kiểm audience, issuer, scope, purpose, expiry, sender binding và business policy |
| **`200 {"active":false}`** | AS không chấp nhận/không tiết lộ token active cho caller | Không cấp quyền; thường trả `401 invalid_token` theo Bearer API policy |
| **`401` introspection** | RS credential/authorization để introspect không hợp lệ | **Không cho phép request**, cảnh báo cấu hình/credential; đây không phải kết luận token của user đã revoked |
| **`403` introspection** | RS không được phép truy vấn/token ngoài quyền theo triển khai | Fail closed, sửa AS/RS permissions |
| **`429`** | AS áp quota/rate limit | Backoff, circuit breaker, không flood introspection; fail closed khi không có cache được phép |
| **`500/502/503/504`** | AS/gateway/đường mạng lỗi | Không biến lỗi thành `active=true`; fallback chỉ với cache còn hợp lệ theo policy |
| **Timeout/TLS error** | Không xác thực được kết quả | Fail closed, không tắt TLS validation |
| **200 JSON sai schema** | Thiếu `active`, `"active":"true"`, sai claim types | Fail closed, cảnh báo AS contract/schema |

### RS nên trả status gì cho client API?

Không có một ánh xạ HTTP duy nhất bắt buộc cho **mọi lỗi nội bộ introspection**. Một policy thường dùng:

- **Token inactive/missing/invalid** → `401 Unauthorized` với Bearer challenge thích hợp.
- **Token active nhưng thiếu scope/quyền** → `403 Forbidden` hoặc phản hồi nghiệp vụ tương ứng; `insufficient_scope` khi đúng profile.
- **AS introspection không khả dụng** và không có cache hợp lệ → từ chối truy cập; tùy kiến trúc có thể dùng `503 Service Unavailable` để phân biệt outage với credential không hợp lệ, nhưng **không tiết lộ credential nội bộ**.

**Không gửi nguyên `401` từ introspection endpoint hoặc body chứa credential/metadata nội bộ tới caller của Invoice API.** RS cần trả lỗi tối thiểu, không phân biệt token tồn tại/hết hạn/revoked nếu điều đó tạo oracle.

### Circuit breaker chỉ là chống quá tải

Nếu AS liên tục timeout, RS có thể mở circuit breaker, dùng backoff/jitter và đo outage. Nhưng **circuit breaker không phải chính sách “bỏ qua authentication/authorization đến khi AS hồi phục”**. Có thể tiếp tục xử lý bằng **cache active đã được kiểm và còn trong TTL cho phép**, nếu business chấp nhận revoke lag; không dùng kết quả quá hạn hoặc kéo dài `exp`.

## 13. Sender-constrained token: `cnf` và proof ở request

Introspection có thể được dùng trong hệ thống **sender-constrained access tokens**. Khi đó, introspection response theo profile có thể chứa **confirmation information** (ví dụ `cnf`) để RS biết token bị ràng buộc với khóa/certificate nào.

### mTLS certificate-bound access token (RFC 8705)

~~~json
{
  "active": true,
  "client_id": "billing-worker",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "exp": 1800000900,
  "cnf": {
    "x5t#S256": "<base64url-sha256-thumbprint-of-certificate>"
  }
}
~~~

`x5t#S256` (theo profile) mô tả fingerprint của certificate dùng ràng buộc access token. RS **phải kiểm certificate thật** trong kết nối mTLS (và trust boundary nếu có reverse proxy) rồi so đúng thumbprint. Một caller sao chép chuỗi token nhưng không có private key/certificate tương ứng **không được dùng token** chỉ vì `active=true`.

### DPoP-bound access token (RFC 9449)

~~~json
{
  "active": true,
  "client_id": "mobile-client",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "exp": 1800000900,
  "cnf": {
    "jkt": "<base64url-thumbprint-of-DPoP-public-key>"
  }
}
~~~

Theo DPoP profile, RS cần kiểm proof JWT **của request hiện tại**: chữ ký bằng public key phù hợp `jkt`, HTTP method (`htm`), target URI (`htu`), `iat`, `jti`, access-token hash (`ath`) và nonce/replay policy nếu áp dụng.

**Không cache một kết quả introspection `active=true` rồi bỏ kiểm DPoP proof/mTLS certificate trên mỗi request.** Cache có thể giúp giảm introspection calls; **sender proof là điều kiện riêng gắn với request** và phải được kiểm lại.

### `token_type` không thay `cnf`

Một chuỗi `token_type` chỉ mô tả token presentation type theo profile. Nó không mang đầy đủ proof of possession. Với token bị ràng buộc, RS cần **binding claim/profile và proof hợp lệ**, không suy an toàn chỉ từ tên `Bearer` hoặc `DPoP`.

## 14. Java 17: đọc introspection response và ra quyết định an toàn

Ví dụ dưới đây minh họa **bước parse và đánh giá authorization context** khi RS đã nhận **JSON từ trusted introspection client**. Nó sử dụng Jackson `JsonNode` để kiểm **đúng kiểu dữ liệu**, không dùng cách đọc text rồi ép kiểu ngầm.

### 14.1. Hợp đồng nghiêm hơn RFC 7662 của Invoice API

Trong ví dụ, Invoice API yêu cầu:

~~~text
Trusted issuer:        https://auth.example.test
Expected audience:     invoice-api
Required scope:        invoice:read
Accepted token type:   Bearer
Required exp:          yes (policy riêng của API)
Required iss/aud/scope:yes (policy riêng của API)
Optional subject:      present for delegated-user routes;
                       absent may be allowed for authorized M2M routes
~~~

**Phải nói rõ:** RFC 7662 **không bắt buộc `iss`, `aud`, `exp` hoặc `scope` xuất hiện**. Ví dụ Java chủ động **fail closed khi thiếu chúng**, vì Invoice API đã thống nhất response contract nghiêm với AS. Một hệ thống khác có thể dùng kiểu policy khác nếu nó có nguồn thông tin tin cậy tương đương.

### 14.2. Parse JSON thành cấu trúc typed

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

record IntrospectionClaims(
    boolean active,
    String issuer,
    String clientId,
    String subject,
    String tokenType,
    Set<String> audiences,
    Set<String> scopes,
    Instant expiresAt,
    Instant notBefore
) {}

final class IntrospectionClaimsParser {

    static IntrospectionClaims parse(JsonNode root) {
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Invalid introspection JSON");
        }

        JsonNode activeNode = root.get("active");
        if (activeNode == null || !activeNode.isBoolean()) {
            throw new IllegalArgumentException(
                "active must be a JSON boolean");
        }

        if (!activeNode.booleanValue()) {
            // Không đọc thêm claims ở một inactive response.
            return new IntrospectionClaims(
                false, null, null, null, null,
                Set.of(), Set.of(), null, null);
        }

        // Các fields sau được yêu cầu bởi contract của Invoice API,
        // dù RFC 7662 chỉ yêu cầu active.
        String issuer = requireText(root, "iss");
        String clientId = requireText(root, "client_id");
        String tokenType = requireText(root, "token_type");
        Set<String> audiences = requireAudiences(root.get("aud"));
        Set<String> scopes = requireScopes(root.get("scope"));

        JsonNode subjectNode = root.get("sub");
        String subject = null;
        if (subjectNode != null && !subjectNode.isNull()) {
            if (!subjectNode.isTextual()) {
                throw new IllegalArgumentException("Invalid subject type");
            }
            subject = subjectNode.textValue();
        }

        Instant expiry = requireEpochSeconds(root, "exp");
        Instant notBefore = optionalEpochSeconds(root, "nbf");

        return new IntrospectionClaims(
            true, issuer, clientId, subject, tokenType,
            audiences, scopes, expiry, notBefore);
    }

    private static String requireText(JsonNode root, String field) {
        JsonNode node = root.get(field);
        if (node == null || !node.isTextual() ||
            node.textValue().isBlank()) {
            throw new IllegalArgumentException(
                "Missing or invalid claim: " + field);
        }
        return node.textValue();
    }

    private static Set<String> requireAudiences(JsonNode aud) {
        if (aud == null || aud.isNull()) {
            throw new IllegalArgumentException("Missing aud");
        }
        Set<String> audiences = new HashSet<>();
        if (aud.isTextual()) {
            if (aud.textValue().isBlank()) {
                throw new IllegalArgumentException("Invalid aud");
            }
            audiences.add(aud.textValue());
        } else if (aud.isArray()) {
            for (JsonNode value : aud) {
                if (!value.isTextual() || value.textValue().isBlank()) {
                    throw new IllegalArgumentException("Invalid aud item");
                }
                audiences.add(value.textValue());
            }
        } else {
            throw new IllegalArgumentException("Invalid aud type");
        }
        if (audiences.isEmpty()) {
            throw new IllegalArgumentException("Empty aud");
        }
        return Collections.unmodifiableSet(audiences);
    }

    private static Set<String> requireScopes(JsonNode scope) {
        if (scope == null || !scope.isTextual()) {
            throw new IllegalArgumentException("Missing or invalid scope");
        }
        String s = scope.textValue();
        if (s.isBlank()) {
            return Set.of();
        }
        Set<String> values = new HashSet<>();
        for (String value : s.trim().split(" +")) {
            if (value.isBlank()) {
                throw new IllegalArgumentException("Invalid scope");
            }
            values.add(value);
        }
        return Collections.unmodifiableSet(values);
    }

    private static Instant requireEpochSeconds(
            JsonNode root, String field) {
        Instant time = optionalEpochSeconds(root, field);
        if (time == null) {
            throw new IllegalArgumentException("Missing " + field);
        }
        return time;
    }

    private static Instant optionalEpochSeconds(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || value.isNull()) {
            return null;
        }
        if (!value.isIntegralNumber() || !value.canConvertToLong()) {
            throw new IllegalArgumentException("Invalid " + field);
        }
        try {
            return Instant.ofEpochSecond(value.longValue());
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("Out-of-range " + field, ex);
        }
    }

    private IntrospectionClaimsParser() {}
}
~~~

**Lưu ý về NumericDate:** RFC 7662 tham chiếu NumericDate kiểu JSON number cho `exp`/`iat`/`nbf`, và NumericDate nói chung có thể bao gồm giá trị không nguyên. Parser **cố ý chỉ nhận số nguyên giây** theo contract của ví dụ Invoice API; đó là giới hạn ứng dụng, **không phải quy định mọi introspection response hợp lệ phải dùng integer**.

### 14.3. Đánh giá claims sau khi parse

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Set;

record IntrospectionPolicy(
    String trustedIssuer,
    String expectedAudience,
    String expectedClientId,
    Set<String> acceptedTokenTypes,
    String requiredScope
) {}

final class IntrospectionAuthorizer {

    static boolean permitsRead(
            IntrospectionClaims claims,
            IntrospectionPolicy policy,
            Clock clock) {

        if (claims == null || !claims.active()) return false;
        if (!policy.trustedIssuer().equals(claims.issuer())) return false;
        if (!claims.audiences().contains(
                policy.expectedAudience())) return false;
        if (!policy.expectedClientId().equals(claims.clientId())) {
            return false;
        }
        if (!policy.acceptedTokenTypes().contains(
                claims.tokenType())) return false;
        if (!claims.scopes().contains(
                policy.requiredScope())) return false;

        Instant now = clock.instant();
        if (claims.expiresAt() == null ||
            !now.isBefore(claims.expiresAt())) {
            return false;
        }
        if (claims.notBefore() != null &&
            now.isBefore(claims.notBefore())) {
            return false;
        }

        // Tại đây vẫn phải kiểm subject/tenant/object ownership
        // theo quyền của API. Chưa được xem đây là toàn bộ authz.
        return true;
    }
    private IntrospectionAuthorizer() {}
}
~~~

`expectedClientId` là yêu cầu minh họa khi Invoice API **chỉ** chấp nhận token từ một client nhất định. Trong các hệ thống phục vụ nhiều clients, policy sẽ là tập client registrations được phép với điều kiện scope/tenant riêng, không ép mọi token phải cùng client ID.

**Không đưa toàn bộ ví dụ Java vào production nguyên xi**. Nó thiếu HTTP/TLS/client authentication, cache, DPoP/mTLS proof, clock-skew policy, rate limiting và object-level authorization; những phần đó cần được triển khai bằng framework đã được bảo trì. Để minh họa chuỗi kiểm tra, code chỉ xét claims đã parse từ **response tin cậy**, không tự cung cấp giao thức introspection.

### 14.4. Tách token introspection khỏi quyền trên object

~~~text
Introspection claims hợp lệ:
  active=true
  iss=https://auth.example.test
  aud=invoice-api
  client_id=invoice-web
  sub=user:an
  scope=invoice:read

Request:
  GET /invoices/INV-42

Authorization ở Invoice API:
  load invoice INV-42 using tenant-scoped query
  check invoice.tenant == authenticated.tenant
  check invoice.owner == authenticated.subject
  apply organization-specific rules
  only then return invoice
~~~

Nếu `sub` thiếu và endpoint yêu cầu **delegated user token**, phải từ chối hoặc dùng một nguồn subject tin cậy khác **theo contract**. Không coi `client_id=invoice-web` là đồng nghĩa user An.

## 15. Spring Security Resource Server: opaque token introspection

Trong Spring Security 6.x với Spring Boot 3.x, một cách cấu hình **opaque token introspection** là:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://auth.example.test/oauth2/introspect"
          client-id: "invoice-api-introspection"
          client-secret: "<inject-from-secret-manager-at-runtime>"
~~~

Đây là **cấu hình minh họa**, không phải setup production hoàn chỉnh:

- `client-id`/`client-secret` ở đây được dùng để **RS xác thực với introspection endpoint**; chúng **không nhất thiết trùng `client_id` được trả về trong response** (ví dụ `invoice-web`).
- Không commit plaintext secret vào Git/container image; dùng secret manager hoặc client authentication method bảo mật được AS hỗ trợ.
- Thiết lập TLS hostname verification, timeouts, connection pool, retry/backoff có kiểm soát và chính sách cache/invalidation theo yêu cầu revoke SLA.
- Spring có thể map scope của introspection thành authorities (thường dạng `SCOPE_...`); **đừng coi đó là toàn bộ phân quyền** cho tenant/object.
- Xem cơ chế extension/opaque token introspector của phiên bản Spring Security đang chạy để thêm kiểm issuer, audience, token purpose, sender binding và custom claims. **Mặc định của framework không thay một policy validation riêng cho API**.
- Nếu ứng dụng dùng JWT Resource Server validation thay vì introspection, nó có trust/cache/revocation tradeoff khác. Không bật cả hai mode mà không có quy tắc rõ token nào được xử lý bằng mode nào.

### Ba lớp trong một service an toàn

~~~text
HTTP Security Filter Chain:
  1. Trích bearer token, gọi introspector tin cậy.
  2. Kiểm active/schema/issuer/audience/expiry/token purpose.
  3. Tạo Authentication/Principal có quyền đã chuẩn hóa.

Controller/Application Service:
  4. Kiểm scope/role phù hợp hành động.

Domain/Repository:
  5. Kiểm tenant/owner/resource-level policy tại nguồn dữ liệu.
~~~

**Không truyền JSON introspection thô vào mọi controller rồi để mỗi nơi tự quyết định `active`**. Nên có một middleware/adaptor tập trung, dễ test và có contract rõ, để tránh endpoint A kiểm `aud` còn endpoint B quên kiểm.

## 16. Bảo vệ quyền truy cập introspection và dữ liệu trả về

Introspection có thể trả những dữ liệu nhạy cảm hơn một API business cần: `sub`, `username`, client identifier, scope, token lifetime, audience, session context. Vì vậy **không biến introspection endpoint thành endpoint public để bất kỳ ai hỏi “token này có tồn tại không?”**.

### Bảo vệ endpoint phía AS

1. **Xác thực/ủy quyền RS hoặc caller được phép:** Hợp đồng phải xác định ai được introspect token nào, vào loại thông tin gì.
2. **TLS và credential an toàn:** Kết nối đến AS qua HTTPS xác minh hostname/certificate, client credential dùng secret manager, private key JWT hoặc mTLS tùy cấu hình.
3. **Giới hạn nội dung:** Không trả claims không cần thiết cho RS ngoài phạm vi; khi token inactive, trả tối thiểu `{"active":false}`.
4. **Rate limit và chống abuse:** Không cho introspection trở thành oracle để brute force token, enumeration user hoặc DoS AS.
5. **Phân quyền theo resource:** Một RS không được mặc nhiên nhìn thông tin token dành riêng cho RS khác hoặc tenant khác.
6. **Giám sát/audit:** Ghi token inspection event ở dạng metadata an toàn, không raw token.

RFC 7662 cho phép AS lựa chọn thông tin tiết lộ theo **quyền của bên gọi**. Do đó, hai RS có thể nhận kết quả/claims khác nhau cho cùng một chuỗi token. **Không chia sẻ introspection cache response giữa các RS khi chưa xác định tương đương quyền truy cập và contract**.

### Bảo vệ phía RS

| Rủi ro | Biện pháp |
|---|---|
| Token bị đưa vào URL introspection | Chỉ dùng POST form; token không nằm trong query string |
| Basic credential bị log | Redact `Authorization`, không đưa vào error response |
| Raw introspection JSON chứa PII trong trace | Redact `sub`/`username`/token metadata theo policy; audit tối thiểu |
| Token của issuer khác dẫn tới SSRF | Token endpoint/issuer được cấu hình tin cậy, không phát sinh URL từ token/caller |
| AS trả claim mở rộng không hiểu | Parse strict profile, bỏ qua/deny theo policy thay vì tự cấp quyền |
| Cross-tenant lookup | Ràng buộc token context và kiểm tenant/object ở database/API |
| Introspection cache bị đọc ngoài quyền | ACL, TLS, encryption/storage policy và key partitioning |
| Response stale sau revoke | TTL ngắn, event invalidation, revoke SLA được đo |

### Không nên ghi log gì?

~~~text
NEVER:
  token=eyJ... hoặc opaque-access-token-thật
  Authorization: Bearer <raw-access-token>
  Authorization: Basic <raw-introspection-client-credential>
  refresh_token=<raw-secret>
  "username":"an@example.test" trong log public không có lý do
  raw full introspection JSON kèm claims nhạy cảm

BETTER:
  event=introspection_decision
  target_resource=invoice-api
  trusted_issuer=auth-prod
  result=inactive
  reason_class=token_not_accepted
  cache_hit=false
  latency_ms=42
  correlation_id=<random-trace-id>
~~~

`jti` hoặc HMAC digest có thể dùng trong **kho audit được phân quyền** khi thật sự cần điều tra, nhưng đừng làm metric label có cardinality cao hay công khai danh tính/cấu trúc token.

### Privacy: `username` không nên là khóa domain

`username` có thể là email/username có thể thay đổi, tái sử dụng hoặc hiển thị khác nhau theo ứng dụng. Muốn xác định subject, dùng **issuer + subject theo hợp đồng**, cộng tenant/context nếu thiết kế yêu cầu. Không biến `username` trong introspection thành bằng chứng user đã qua MFA, có role admin hoặc vẫn sở hữu tài khoản tại thời điểm hiện tại.

## 17. Ma trận kiểm thử response claims từ introspection

Giả định:

~~~text
Trusted AS issuer:  https://auth.example.test
Introspection URL: https://auth.example.test/oauth2/introspect
RS identity:       invoice-api-introspection
Expected aud:      invoice-api
Required scope:    invoice:read
Expected token:    access token for Invoice API
Acceptable type:   Bearer per local contract
User route:        must have verified subject and matching tenant
~~~

| Test case | Response/đầu vào | Kỳ vọng ở Resource Server |
|---|---|---|
| **Active hợp lệ** | `active=true` và tất cả claims policy yêu cầu hợp lệ | Qua token-validation, tiếp tục kiểm quyền dữ liệu |
| **Inactive tối thiểu** | `{"active":false}` | Không chấp nhận token; không yêu cầu AS trả thêm lý do |
| **Inactive kèm claims dư** | `active=false, sub=user:an` | Vẫn từ chối; không dùng claims dư để tạo user context |
| **Thiếu `active`** | JSON có `scope` nhưng không có active | Từ chối response sai schema |
| **`active` là string** | `"active":"true"` | Từ chối; không ép string thành boolean |
| **`active` là số** | `"active":1` | Từ chối; không coi 1 là true |
| **`active` là null** | `"active":null` | Từ chối |
| **Response không phải JSON** | HTML proxy/login page | Fail closed, cảnh báo endpoint/integration |
| **JSON bị cắt giữa chừng** | Parser lỗi | Fail closed, không reuse kết quả cũ ngoài TTL |
| **Active nhưng `aud` sai** | `aud=payments-api` | Không chấp nhận trên Invoice API |
| **`aud` dạng string** | `aud="invoice-api"` | Parse đúng dạng string, so khớp chính xác |
| **`aud` dạng array** | `aud=["invoice-api","reporting-api"]` | Parse đúng mảng string, không bỏ các phần tử bất hợp lệ |
| **`aud` thiếu** | Response active không có aud | Từ chối theo contract API yêu cầu audience |
| **`aud` sai type** | `aud=123` | Từ chối |
| **`aud` substring trap** | `aud=invoice-api-attacker` | Không khớp `invoice-api` |
| **`iss` sai** | `iss=https://other.example.test` | Từ chối |
| **`iss` thiếu** | AS không trả iss | Từ chối theo local contract, không khẳng định RFC yêu cầu |
| **Scope phù hợp** | `scope="invoice:read invoice:export"` | Match `invoice:read` như phần tử độc lập |
| **Scope thiếu quyền** | `scope="invoice:export"` | `403`/insufficient_scope theo API policy |
| **Scope substring trap** | `scope="invoice:read-all"` | Không cấp quyền `invoice:read` |
| **Scope sai case** | `scope="Invoice:Read"` | Không khớp nếu policy là `invoice:read` |
| **Scope sai type** | `scope=["invoice:read"]` | Từ chối theo RFC 7662 schema chuẩn |
| **Scope thiếu** | active true, không có scope | Không cấp action yêu cầu scope, dù claim RFC là optional |
| **`exp` theo giây** | NumericDate `exp=1800000900` | So với epoch seconds đúng cách |
| **`exp` theo mili giây** | Caller/AS gửi 13-digit value không đúng profile | Từ chối theo expiry/schema policy, không lặng lẽ kéo dài tuổi token |
| **`exp` ở quá khứ** | active true nhưng exp đã qua | Từ chối theo RS policy; cảnh báo AS inconsistency |
| **`nbf` trong tương lai** | active true nhưng nbf sau now | Từ chối hoặc áp skew rất hạn chế theo contract |
| **`iat` trong tương lai bất thường** | iat vượt allowed skew | Cảnh báo/từ chối theo policy thời gian |
| **`username` đổi** | `username` mới, `sub` không đổi | Quyền dữ liệu không thay vì tên hiển thị |
| **`client_id` là workload** | `client_id=billing-worker`, không có username | Không tạo user giả; dùng M2M policy |
| **`sub` thiếu ở user route** | Access token không có subject | Từ chối user-specific authorization hoặc áp trusted mapping |
| **Cross-client** | Token cấp cho client không được allow | Từ chối nếu client allowlist là điều kiện của API |
| **Token type khác** | RS nhận refresh token hoặc ID token | Từ chối theo token-purpose contract |
| **Hint sai** | `token_type_hint=refresh_token` nhưng token là access token | AS không dựa hint làm proof; RS dùng thông tin chính xác |
| **Response `jti` lạ** | Có jti nhưng không có sender proof | Không mặc định chống replay; dùng đúng audit/denylist policy |
| **Opaque token** | Không có JWT segments, introspection active=true | RS dùng claims từ AS, không cần decode JWT |
| **JWT nhưng AS revoke** | JWT chữ ký hợp lệ, introspection active=false | Từ chối khi policy yêu cầu introspection/revocation |
| **JWT/response mâu thuẫn** | Aud/scope khác nhau | Fail closed, không ghép claims để nâng quyền |
| **DPoP `cnf.jkt` đúng** | Proof ký đúng key, method, URI, `ath` | Cho qua binding check rồi tiếp tục authz |
| **DPoP proof thiếu** | active=true, token DPoP-bound | Từ chối |
| **mTLS binding sai** | `cnf.x5t#S256` khác certificate caller | Từ chối |
| **Cache `active=true` chưa hết TTL** | Response cache hợp lệ và đúng RS context | Có thể sử dụng theo revoke SLA và policy |
| **Cache đã quá `exp`** | Local TTL dài hơn token exp | Không dùng response, không cho phép truy cập |
| **Revoke trong cửa sổ cache** | AS revoke token, RS chưa invalidate | Kiểm/review revoke propagation SLA, giảm TTL nếu không đáp ứng |
| **Cache chung giữa hai RS** | Token response Invoice API đem dùng cho Payment API | Từ chối, phân vùng cache đúng RS/issuer/aud |
| **Introspection RS credential sai** | AS trả HTTP 401 | Fail closed, báo lỗi tích hợp; không coi là token active |
| **AS 503/timeout** | Không có cache còn hợp lệ | Fail closed; có thể trả 503, không cho qua |
| **AS bị rate limit** | HTTP 429 | Backoff/circuit breaker, không bypass token checks |
| **TLS certificate sai** | Introspection URL trả cert không tin cậy | Chặn request, không tắt verification |
| **Token xuất hiện trong log** | Gateway/trace chứa `token=...` | Test phải fail; bật redaction và kiểm retention |
| **Cross-tenant object** | scope/active đúng nhưng invoice thuộc tenant khác | `403`/`404` theo policy, không trả dữ liệu |
| **Role claim chưa được thỏa thuận** | `"roles":["admin"]` từ AS không đúng trust contract | Không dùng để nâng quyền, cần policy/issuer authority |

### Kiểm thử thời gian và race

**Đừng chỉ test parser bằng JSON tĩnh**. Nên sử dụng fake clock/AS stub để kiểm:

~~~text
T0:    AS trả active=true, exp=T0+60s.
T0+10: RS lưu cache theo policy 15s.
T0+12: AS revoke token.
T0+20: RS có thể còn cache; cần đo revoke lag theo SLA.
T0+26: Cache expired; RS introspect -> active=false.
T0+61: Mọi code path đều từ chối nếu exp đã qua.

Concurrency test:
  request A introspection -> active=true, response chậm
  event revoke invalidates token at RS
  request B introspection -> active=false, response nhanh
  response A về muộn

Assert:
  stale true từ A không được ghi đè revoked/false mới hơn.
~~~

Muốn đáp ứng thu hồi gần tức thì, chỉ thay TTL bằng 15 giây **không đủ**; phải có invalidation/chính sách và điều kiện AS/RS bảo đảm. Tests cần đo thực tế dưới network delay, multi-instance, clock skew và failover.

## 18. Bài tập tình huống: một token, ba API và hai nguồn danh tính

Hệ thống gồm:

~~~text
Issuer AS: https://auth.example.test

Invoice API:
  audience = invoice-api
  required scope = invoice:read

Payment API:
  audience = payments-api
  required scope = payment:approve

Billing Worker:
  client_id = billing-worker
  sử dụng client_credentials

Invoice Web:
  client_id = invoice-web
  đại diện người dùng An bằng authorization_code
~~~

Invoice Web gọi Invoice API với opaque access token T1; introspection trả:

~~~json
{
  "active": true,
  "client_id": "invoice-web",
  "sub": "user:an",
  "username": "an@example.test",
  "scope": "invoice:read",
  "aud": ["invoice-api"],
  "iss": "https://auth.example.test",
  "exp": 1800000900
}
~~~

**Câu 1. Chỉ vì `active=true`, Invoice API có được trả mọi hóa đơn không?**

**Không.** API cần kiểm issuer/audience/scope/expiry và quyền trên **hóa đơn được yêu cầu**. Nếu `INV-99` thuộc tenant khác, phải từ chối dù token còn active.

**Câu 2. Có được gửi T1 tới Payment API để phê duyệt giao dịch không?**

**Không.** T1 có `aud=["invoice-api"]` và `scope="invoice:read"`, không dành cho Payment API và không có quyền phê duyệt.

**Câu 3. `username=an@example.test` có phải khóa user bất biến không?**

**Không.** Username/email có thể đổi hoặc tái sử dụng; sử dụng issuer + stable subject theo contract và kiểm tenant/identity mapping của ứng dụng.

**Câu 4. Nếu Billing Worker nhận token M2M không có `sub`, có phải AS lỗi?**

**Không nhất thiết.** RFC 7662 làm `sub` tùy chọn. Token `client_credentials` có thể mô tả service identity khác user; RS phải dùng **M2M authorization policy**, không tự gán quyền user từ `client_id`.

**Câu 5. T1 bị revoke tại AS nhưng RS cache kết quả active trong 30 giây. Có thể còn truy cập không?**

**Có thể**, trong cửa sổ cache nếu RS chưa nhận thông tin revoke. Đây là **revoke propagation lag** cần đánh giá SLA; yêu cầu thu hồi tức thì cần cơ chế kiểm/invalidation mạnh hơn.

**Câu 6. Introspection endpoint trả HTTP 401 vì client secret của RS hết hạn. Có thể fallback sang `active=true` không?**

**Không.** Credential của RS bị lỗi làm introspection **không đáng tin/không khả dụng**. Có thể dùng cache còn hợp lệ nếu contract cho phép; nếu không phải fail closed, không cho qua.

**Câu 7. AS trả `{"active":"true"}` (string). RS có được ép kiểu để tiếp tục không?**

**Không.** `active` phải là JSON boolean; response sai schema là lỗi tích hợp cần chặn, không tự “sửa” cho qua.

**Câu 8. Token introspection báo `token_type="Bearer"`. Có đủ chứng minh nó là access token không?**

**Không.** `Bearer` mô tả cách trình bày token, không tự chứng minh token purpose. RS cần hợp đồng AS và kiểm loại/grant phù hợp; không chấp nhận refresh token như access token.

**Câu 9. T1 có `jti`. Kẻ khác sao chép token thì `jti` có tự ngăn replay không?**

**Không.** Bearer token có thể bị tái sử dụng trong lifetime. Muốn chống token theft/replay cần TTL, revoke, sender constraint, risk checks và có thể denylist theo `jti` nếu thiết kế.

**Câu 10. RS nhận token DPoP-bound với `cnf.jkt` đúng nhưng HTTP request không có DPoP proof. Có được phép không?**

**Không.** Introspection trả binding metadata chưa chứng minh caller sở hữu private key. RS phải xác minh proof tương ứng với request.

## 19. Checklist triển khai introspection response trước production

1. **Endpoint đáng tin:** RS gọi đúng AS/introspection URI cố định, qua HTTPS được kiểm, có authorization/credential riêng?
2. **Không lẫn token và introspection auth:** Bearer token từ caller chỉ là đối tượng kiểm; RS credential dùng hỏi AS được quản trị riêng?
3. **`active` đúng kiểu:** Chỉ chấp nhận JSON boolean, fail closed khi sai/missing?
4. **Inactive tối thiểu:** `active=false` dẫn tới reject; không dò nguyên nhân chi tiết từ claims có/không?
5. **Optional claims có contract:** `scope`, `client_id`, `sub`, `aud`, `iss`, `exp` được xử lý với type/policy rõ, không nói RFC bắt buộc ngoài active?
6. **Scope parse đúng:** `scope` là string space-delimited, kiểm từng giá trị chính xác, không substring?
7. **Audience check:** `aud` string/array được kiểm với định danh RS đã cấu hình, không suy từ hostname hoặc client_id?
8. **Issuer check:** `iss` khớp expected issuer khi profile yêu cầu; multi-AS có mapping tin cậy, không issuer injection?
9. **Token purpose:** RS nhận đúng access token, không chấp nhận ID/refresh token vì chỉ thấy `active=true` hoặc `Bearer`?
10. **Phân biệt danh tính:** `client_id` là OAuth client, `sub` theo issuer/profile, `username` chỉ dễ đọc; M2M không bị gán user giả?
11. **Thời hạn chuẩn:** `exp`/`iat`/`nbf` theo Unix seconds/NumericDate, clock skew giới hạn, không dùng token hết hạn?
12. **Không ủy quyền bằng `jti`:** Token ID phục vụ audit/denylist theo policy, không thay replay protection?
13. **Sender binding:** Nếu có `cnf.jkt` hoặc `cnf.x5t#S256`, RS xác minh proof/certificate mỗi request?
14. **JWT/opaque nhất quán:** Không trộn claims từ các nguồn mâu thuẫn để tăng quyền, hiểu revocation lag của từng mode?
15. **Cache đúng ngữ cảnh:** Key gồm token digest và RS/issuer/policy context, TTL không vượt `exp`, cache-control/AS contract được tôn trọng?
16. **Thu hồi có SLA:** Revoked token được RS từ chối trong thời gian chấp nhận, có invalidation/denylist nếu cần?
17. **Lỗi AS fail closed:** 401 introspection auth, 429, 5xx, timeout, TLS error hoặc JSON lỗi không mở quyền?
18. **Quyền đối tượng luôn kiểm:** Scope, tenant, owner, object, role và dữ liệu được xác định tại API/domain layer?
19. **Giám sát và log an toàn:** Cache hit/miss, introspection latency/error, active false, revoke lag; không raw token, Basic secret, PII dư thừa?
20. **Kiểm thử âm tính đủ:** Wrong audience/issuer/token type, bad JSON types, missing fields theo contract, cross-tenant, stale cache, concurrency và sender proof?

**Ghi nhớ:** **Response introspection theo RFC 7662 bắt buộc có `active` kiểu boolean, còn `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss` và `jti` là claims tùy chọn.** `active=false` nghĩa là RS không được chấp nhận token; `active=true` mới chỉ là **bước kiểm trạng thái tại AS**. Resource Server phải xác minh **đúng issuer, audience, loại token, thời gian, scope, sender binding và quyền dữ liệu**, dựa trên hợp đồng với AS. Caching giúp hiệu năng nhưng tạo độ trễ thu hồi; cache không được vượt expiry hoặc dẫn tới fail-open.

### Chuẩn và tài liệu tham khảo

- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, standard response claims, endpoint protection, metadata visibility, caching và security considerations.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, client authorization, token type và các grants OAuth.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách đưa Bearer access token vào API request và lỗi `invalid_token`/`insufficient_scope`.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `sub`, `exp`, `iat`, `nbf`, `jti` và NumericDate.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token và yêu cầu kiểm tại Resource Server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** phân biệt thu hồi token/grant tại AS với xóa cache tại RS.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** phát access token hướng tới đúng resource/audience.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** sender binding bằng certificate và `cnf.x5t#S256`.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof theo từng request và ràng buộc `cnf.jkt`.
- **RFC 9396 — OAuth 2.0 Rich Authorization Requests:** `authorization_details` trong profile có hợp đồng tương ứng.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft, replay, authorization và bảo vệ OAuth deployment.
- **OpenID Connect Core 1.0:** phân biệt ID token, access token, authentication claims và relying party.
- **Spring Security Reference — OAuth2 Resource Server / Opaque Token:** tích hợp introspection, mapping authority và extension policy tại RS.
- **OWASP OAuth 2.0 Cheat Sheet và Authorization Cheat Sheet:** scope, audience, object-level authorization, token handling, least privilege và logging.
