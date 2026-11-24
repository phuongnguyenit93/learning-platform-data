# Token revocation phản ánh qua introspection

**Token revocation** là hành động làm một token hoặc authorization grant **không còn được phép sử dụng**, trong khi **token introspection** là cách một resource server (RS) hỏi authorization server (AS) về **trạng thái và metadata của token** tại thời điểm kiểm tra. Trong hệ sinh thái OAuth 2.0, **RFC 7009** mô tả token revocation endpoint; **RFC 7662** mô tả token introspection endpoint. Hai giao thức có chức năng khác nhau nhưng kết hợp để RS có thể nhận biết token đã bị thu hồi.

Giả sử dịch vụ `orders-api` nhận opaque access token đã cấp cho một ứng dụng. Người dùng rút quyền truy cập của ứng dụng lúc 10:00. Sau khi AS lưu trạng thái revoke, RS gọi introspection:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_RS_INTROSPECTION_CREDENTIALS_TEST
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN_TEST_ONLY&token_type_hint=access_token
```

Kết quả mong đợi khi token **không còn active đối với RS**:

```json
{
  "active": false
}
```

**`active: false` không có nghĩa mọi sự cố đều là “user vừa bấm revoke”.** AS có thể trả trạng thái không active vì token đã hết hạn, không tồn tại, không đúng loại, không còn grant hoặc RS không được phép biết về token. Ngược lại, **`active: true` chỉ cho biết token hiện được AS coi là active theo ngữ cảnh introspection**; RS vẫn phải kiểm **audience, scope, loại token, tenant và quyền đối với tài nguyên cụ thể**.

```text
                 OAuth client / User / Admin
                           |
                           | Revoke token hoặc grant
                           v
                  Authorization Server
                  token/grant state: REVOKED
                           |
                 RS hỏi introspection qua TLS
                           |
                           v
                POST /introspect(token)
                           |
                           v
                 {"active": false}
                           |
                           v
                 RS DENY API request

Điểm nhạy cảm:
    [1] AS đã lưu revoke chưa?
    [2] Introspection có đọc đúng trạng thái mới nhất?
    [3] RS có cache kết quả "active=true" cũ không?
    [4] RS có fail closed khi AS không phản hồi không?
```

Bài thuộc chương **Introspection** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi module bao gồm mô hình tin cậy và vòng đời JWT/opaque token, access/refresh token trong authentication, authorization và OAuth 2.0/OIDC; phát hành, xác minh claims, scope/audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại. Trọng tâm ở đây là **token revocation được phản ánh như thế nào qua introspection**, những điểm có thể tạo độ trễ và cách triển khai RS/AS an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **token revocation** (RFC 7009), **token introspection** (RFC 7662), **JWT local validation** và **resource authorization**.
2. Mô tả đường đi từ một yêu cầu revoke tới trạng thái `active=false` trong introspection, rồi tới quyết định từ chối tại RS.
3. Giải thích yêu cầu HTTP của introspection: **POST, form-urlencoded, token, token_type_hint tùy chọn và xác thực RS**.
4. Đọc đúng `active` và các response fields `scope`, `client_id`, `sub`, `aud`, `iss`, `exp`, `nbf`, `iat`, `token_type`, `jti` khi AS trả về.
5. Tránh suy luận sai: **`active=false` không luôn đồng nghĩa revoke**, **`active=true` không tự cấp quyền**, **HTTP 401 từ introspection không phải response inactive**.
6. Giải thích khác biệt giữa revoke **opaque token** và revoke **JWT self-contained**, nhất là RS validation offline và cache.
7. Thiết kế caching/consistency/TTL và mục tiêu **revocation propagation** có thể đo lường.
8. Triển khai resource server introspection và kiểm audience/scope qua **Java/Spring Security**, xử lý lỗi fail closed.
9. Phòng chống token scanning, leakage, replay, SSRF, confused deputy, nhầm token type và cross-tenant authorization.
10. Viết ma trận test cho revoke, race, cache stale, outage, expiry, multi-region và incident response.

## 2. Các vai trò và ranh giới tin cậy

| Vai trò/thành phần | Trách nhiệm chính | Không được nhầm |
| --- | --- | --- |
| **Authorization Server (AS)** | Phát hành token, quản lý grant, token status, revocation/introspection endpoints | AS không tự quyết định mọi resource-level permission thay RS |
| **OAuth Client** | Nhận và sử dụng access token; có thể gọi revocation endpoint theo điều kiện AS | Client không tự tạo trạng thái `active=false` bằng cách sửa JWT |
| **Resource Server (RS)** | Nhận access token, kiểm token active/issuer/audience/scope và policy API | RS không coi một response JSON bất kỳ là introspection đáng tin |
| **End user / resource owner** | Có thể rút consent/grant qua giao diện OP/AS | User logout không tự đồng nghĩa mọi token hết hạn ngay |
| **Administrator** | Có thể disable client, revoke grant, khóa account/khóa ký theo policy | Admin approval và user consent là hai loại authority khác |
| **Token/grant store** | Lưu trạng thái, expiry, revoke marker, metadata có kiểm soát | Không nhất thiết lưu raw token hay đồng bộ giữa mọi vùng tức thì |
| **Cache/CDN/API gateway** | Có thể cache introspection/authorization decision | Cache không được vô tình giữ `active=true` lâu hơn mục tiêu bảo mật |

**Luồng dữ liệu đáng tin:**

1. RS lấy token từ request đến API; **token do caller cung cấp là dữ liệu chưa tin cậy**.
2. RS gọi **AS introspection endpoint đã cấu hình**, qua TLS và với bằng chứng xác thực/ủy quyền được AS chấp nhận.
3. AS xác minh RS và quyền được introspect token này, đọc token/grant state, trả metadata phù hợp.
4. RS hiểu response theo **RFC 7662 và hợp đồng AS/RS**, rồi áp dụng API policy riêng.

RS không được cho caller **chỉ định introspection URI, issuer hoặc JWKS URL** qua token/query để tránh SSRF, token exfiltration và issuer confusion.

## 3. Token lifecycle: “đã phát” khác “vẫn được phép”

Một token có thể tồn tại như một chuỗi byte từ lúc phát hành đến lúc hết hạn, nhưng **quyền sử dụng** có thể đổi trước `exp`. Hình dung:

```mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> ACTIVE: Token becomes usable
    ISSUED --> NOT_YET_VALID: nbf in future
    NOT_YET_VALID --> ACTIVE: Reaches nbf
    ACTIVE --> REVOKED: Explicit revocation / grant invalidation
    ACTIVE --> EXPIRED: Reaches exp
    ACTIVE --> DISABLED: Client/account/policy invalidated
    REVOKED --> [*]
    EXPIRED --> [*]
    DISABLED --> [*]
```

Đây là mô hình khái niệm, không phải state machine bắt buộc của mọi AS. Một token có thể không có `nbf`, và việc user bị khóa/account bị disable có thể hoặc không **ngay lập tức** vô hiệu mọi token đã cấp tùy policy. Cần định nghĩa thực tế của hệ thống.

### 3.1. “Revoked” không phải “expired”

- **Expired:** thời hạn `exp` đã qua; AS có thể trả `active=false` dù không có sự kiện revoke.
- **Revoked:** AS/authority đã đánh dấu token/grant không còn được dùng **trước khi hết hạn**.
- **Not yet valid:** chưa đến `nbf`; không được chấp nhận tại thời điểm hiện tại.
- **Unknown token:** AS không tìm thấy/không nhận dạng được.
- **Wrong context:** token có thể valid ở một nơi nhưng không dành cho RS hiện tại.

Các nguyên nhân trên có thể cùng dẫn tới `active=false` hoặc quyết định deny, nhưng **audit và cách khắc phục khác nhau**. Không kết luận “user đã thu hồi” chỉ từ response inactive.

### 3.2. Token material không tự thay đổi khi bị revoke

Một JWT đã được ký có thể vẫn còn chữ ký mật mã hợp lệ sau revoke. Một opaque bearer string cũng không đổi byte khi AS đánh dấu revoke. Điều thay đổi là **authorization state** tại AS và chính sách mà RS phải kiểm.

```text
JWT bytes before revoke == JWT bytes after revoke
JWT signature before revoke == signature after revoke

BUT:
  AS grant/token status changes ACTIVE -> REVOKED
  Introspection: active=true -> active=false
  RS with live introspection: allow candidate -> deny
```

Nếu RS chỉ kiểm chữ ký JWT và `exp` **mà không hỏi AS/trạng thái revoke**, nó có thể tiếp tục chấp nhận JWT cũ tới `exp`. Đó không phải lỗi chữ ký mà là hệ quả của mô hình **stateless validation**.

## 4. RFC 7662: yêu cầu token introspection

Introspection endpoint cho phép một **protected resource**/RS yêu cầu thông tin về token. AS phải bảo vệ endpoint, xác thực/ủy quyền caller theo chính sách và **tránh trả metadata nhạy cảm cho client không được phép**.

### 4.1. HTTP request chuẩn

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_RS_SECRET_TEST_ONLY
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_TOKEN_TEST_ONLY&token_type_hint=access_token
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `POST` | Gửi token trong body, không phải URL query |
| `Content-Type` | `application/x-www-form-urlencoded` |
| `token` | Token cần introspect; **bắt buộc** |
| `token_type_hint` | Gợi ý loại token, **tùy chọn** |
| RS authentication | Basic hoặc mTLS/private-key/client auth theo AS/profile |
| TLS | Bảo vệ token và introspection credentials trên đường truyền |

`token_type_hint=access_token` giúp AS tra cứu đúng kho/token type nếu hỗ trợ; **không có tính ràng buộc tuyệt đối**. Theo RFC 7662, AS có thể bỏ qua hint; nếu token không tìm thấy trong loại được gợi ý, nó cần xem xét khả năng token thuộc loại khác theo triển khai/chuẩn. **RS phải tự xác minh loại token phù hợp với API**, không coi token trở thành access token chỉ vì caller gửi hint `access_token`.

### 4.2. RS phải được quyền introspect

Introspection credential **không phải** client secret mà ứng dụng frontend dùng để đăng nhập. Nó là bằng chứng RS/service được AS cho quyền introspection trong phạm vi phù hợp.

Ví dụ cấu hình registration logic:

```text
introspection_client_id = orders-api-introspector
introspection_endpoint = https://id.example.test/oauth2/introspect
allowed_resources = [orders-api]
allowed_token_types = [access_token]
authentication_method = client_secret_basic or mTLS
```

AS có thể hạn chế response theo token audience, ownership hoặc client quyền truy vấn. **Không mở introspection endpoint công khai** cho bất kỳ ai cầm một chuỗi token, vì điều đó tạo cơ hội thử hàng loạt token và thu thập subject/scope/metadata.

### 4.3. Không gọi introspection bằng browser tùy ý

Một SPA/public client chứa introspection client secret trong JavaScript sẽ lộ bí mật. Introspection thường là trao đổi **back-channel giữa RS và AS**, phù hợp confidential server-to-server authentication. Không đưa endpoint trực tiếp ra frontend rồi dựa vào CORS làm xác thực.

## 5. Introspection response: `active` là tín hiệu trọng tâm

### 5.1. Token active

Ví dụ response mô phỏng token còn hiệu lực cho `orders-api`:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders:read",
  "client_id": "storefront-web",
  "username": "user-42",
  "token_type": "Bearer",
  "exp": 1800000600,
  "iat": 1800000000,
  "nbf": 1800000000,
  "sub": "opaque-stable-subject-42",
  "aud": ["orders-api"],
  "iss": "https://id.example.test",
  "jti": "example-token-id"
}
```

Các giá trị là **fixture**, không phải credential thật; timestamps chỉ minh họa. Trường `active` bắt buộc theo RFC 7662, nhiều trường còn lại là **tùy chọn**. AS có thể không gửi `username`, `aud`, `jti` hoặc một số metadata khác khi không cần hoặc vì policy riêng tư.

### 5.2. Token inactive

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
```

Đây là phản hồi hợp lệ của RFC 7662 cho token không active hoặc trường hợp AS không cho caller biết metadata. Theo RFC 7662, response inactive thông thường **không thêm thông tin gì ngoài `active`**; điều này tránh oracle phân biệt token tồn tại, từng thuộc user nào hoặc vì sao bị vô hiệu.

**Cấm suy từ `active=false` ra “token đã bị revoke bởi Alice”** trừ khi có audit channel đáng tin khác cung cấp lý do. Từ góc nhìn RS, điều cần thiết là **không cho token đi qua**.

### 5.3. Ý nghĩa các trường

| Trường | Nội dung | RS cần làm gì |
| --- | --- | --- |
| **`active`** | Boolean trạng thái token ở AS theo ngữ cảnh | `false`/thiếu/không hợp lệ → deny; `true` chưa đủ để allow |
| `scope` | Scope được cấp, thường là chuỗi phân cách bằng dấu cách | Kiểm đúng quyền endpoint; không dùng requested scope |
| `client_id` | Client liên quan token | Áp dụng client allowlist/policy khi cần |
| `username` | Tên user theo AS nếu có | Không dùng làm immutable subject key hoặc mặc định có |
| `token_type` | Ví dụ Bearer | Không thay thế token-type/profile policy của RS |
| `exp` | Expiry ở epoch seconds | Không chấp nhận token hết hạn; cân nhắc clock skew |
| `iat` | Thời điểm phát hành | Có thể áp giới hạn tuổi theo policy |
| `nbf` | Not-before | Không dùng trước thời điểm có hiệu lực |
| `sub` | Subject theo grant/profile | Phân biệt user vs service principal |
| `aud` | Các audience có thể nhận token | Phải chứa chính xác RS hiện tại |
| `iss` | Issuer | So khớp AS cấu hình tin cậy |
| `jti` | Token identifier khi có | Dùng cho audit/revocation state nếu profile xác định; không tự cho chống replay |

Không tự động coi mọi field optional **bắt buộc trong RFC 7662**. Nhưng với một API yêu cầu audience/issuer/scope cụ thể, **thiếu metadata cần thiết** có thể dẫn đến **deny** hoặc đòi một hợp đồng AS/RS đáng tin cung cấp kiểm tra tương đương tại AS. Không hạ yêu cầu bảo mật chỉ vì response không trả field.

### 5.4. HTTP 200 với `active=false` khác HTTP 401

| Kết quả introspection | Ý nghĩa chính | Quyết định RS |
| --- | --- | --- |
| **200 + `active=true`** | AS coi token active theo ngữ cảnh | Còn phải kiểm issuer/aud/type/scope/policy |
| **200 + `active=false`** | Token không active hoặc không tiết lộ metadata | Deny token |
| **401/403** từ introspection endpoint | RS introspection credentials/quyền truy vấn không được chấp nhận hoặc AS policy từ chối | **Fail closed**; cảnh báo misconfiguration, không tự allow |
| **400** | Request introspection sai cú pháp/thiếu token | Fail closed, sửa tích hợp |
| **429/5xx/timeout/network failure** | Không có phản hồi introspection đáng tin | Fail closed hoặc cơ chế dự phòng **đã được chính sách bảo mật cho phép**, không tự accept |
| **200 JSON sai cú pháp/thiếu `active`** | Response không hợp lệ | Fail closed, không giả định true |

Một endpoint có thể trả lỗi OAuth khác nhau theo cách AS triển khai; **đừng viết logic “mọi HTTP 200 đều active”**.

## 6. RFC 7009: revocation được gửi như thế nào?

Token revocation endpoint cho **client đã được phép** yêu cầu AS thu hồi token, thường là access token hoặc refresh token. Bên dùng giao diện user/admin có thể thông qua dịch vụ backend của AS để revoke grant; không nhất thiết browser gọi trực tiếp endpoint RFC 7009.

### 6.1. Request minh họa

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_REGISTERED_CLIENT_CREDENTIALS_TEST
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_TEST_ONLY&token_type_hint=refresh_token
```

**Đừng gửi raw token trong URL query.** `token_type_hint` chỉ là gợi ý; client không được dùng nó để đổi bản chất/grant ownership của token. AS phải xác minh client/authority và token affiliation theo chính sách.

### 6.2. Revocation trả 200 chưa chứng minh token từng tồn tại

RFC 7009 định nghĩa thành công thường là **HTTP 200**, kể cả khi client gửi một token không hợp lệ/không nhận dạng được (khi điều kiện xác thực request đáp ứng), nhằm giảm rò rỉ thông tin về token existence.

```http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Length: 0
```

Không suy rằng **HTTP 200 = AS xác nhận token trước đó active**. Và **200 không tự chứng minh mọi resource server đã nhìn thấy trạng thái mới nhất**: có thể còn caching, replication delay và JWT offline validation.

### 6.3. Revoke refresh token có thể ảnh hưởng access token

Quan hệ giữa token:

```text
Authorization grant G1
   |
   +-- Refresh token R1
   |
   +-- Access token A1 (aud=orders-api)
   |
   +-- Access token A2 (aud=profile-api)
```

Khi revoke `R1`, AS có thể vô hiệu grant và các access token cùng authorization grant theo chính sách/khả năng hỗ trợ. RFC 7009 khuyến nghị **nếu revoke refresh token và AS hỗ trợ access-token revocation**, nên vô hiệu các access token dựa trên cùng authorization grant. Revoke một access token **có thể** đồng thời ảnh hưởng refresh token tùy chính sách.

**Không giả định quan hệ cascade là giống nhau ở mọi provider.** Cần kiểm hợp đồng AS, token family/rotation và quy tắc revoke của dịch vụ thực tế.

### 6.4. Các đường revoke khác

Token/grant cũng có thể bị vô hiệu do:

- User rút consent của một OAuth client.
- Admin disable client hoặc thu hồi quyền tenant.
- Security system phát hiện refresh-token reuse, credential theft.
- Account/session bị khóa theo policy.
- Grant/token family hết hạn hoặc bị thay phiên bản.
- Thay đổi chính sách cấp quyền hoặc khóa ký trong sự cố.

Đây có thể là **sự kiện nội bộ AS** chứ không phải request trực tiếp tới `/revoke`. Nhưng RS vẫn cần được bảo vệ trước token trở nên không active bằng introspection hoặc cơ chế tương đương.

## 7. Từ revoke đến `active=false`: chuỗi điều kiện

```mermaid
sequenceDiagram
    actor U as User / Admin
    participant C as OAuth Client
    participant AS as Authorization Server
    participant S as Token/Grant Store
    participant RS as Resource Server
    U->>AS: Revoke consent/grant (hoặc C POST /revoke)
    AS->>AS: Xác thực caller, kiểm authority và token/grant
    AS->>S: Ghi trạng thái REVOKED / increment grant version
    S-->>AS: Commit result
    AS-->>U: Confirm theo user/admin flow
    C->>RS: API request với access token cũ
    RS->>AS: POST /introspect token + RS authentication
    AS->>S: Đọc token/grant status
    S-->>AS: REVOKED
    AS-->>RS: 200 {"active": false}
    RS-->>C: 401 invalid_token (theo profile)
```

Để có kết quả này, cần:

1. **Revoke được xác thực/ủy quyền:** người yêu cầu thực sự được phép thu hồi token/grant.
2. **Trạng thái được persist:** AS hoặc authoritative store đã ghi revoke; không chỉ thay giao diện user.
3. **Introspection tra authoritative state:** không lấy một bản snapshot vĩnh viễn tại thời điểm token issuance.
4. **Dữ liệu nhất quán đủ nhanh:** mọi AS nodes/regions phục vụ introspection nhìn thấy revoke theo security objective.
5. **RS không dùng mãi `active=true` cũ:** cache có TTL/invalidations được quản trị.
6. **RS thực thi deny:** không rơi về “JWT signature valid => allow” nếu chính sách yêu cầu revocation-aware validation.

### 7.1. Hai thành công khác nhau

```text
Revoke API returns 200
    => AS đã nhận/xử lý request theo hợp đồng RFC 7009.

Introspection returns {"active": false}
    => AS hiện không coi token active cho RS/caller này.

RS rejects API request
    => Token không còn đem lại quyền sử dụng endpoint đó.
```

Ba bước khác nhau về **giao thức, thời điểm và hệ thống chịu trách nhiệm**. Phải test cả ba nếu yêu cầu "revoke xong dừng truy cập".

### 7.2. Không biến revoke thành tác vụ “best effort” im lặng

Nếu workflow user nhấn “Disconnect app” nhưng backend chỉ đánh dấu UI `disconnected=true`, không hủy grant/refresh token và RS vẫn accept access token vô thời hạn, UX tạo **cam kết bảo mật sai**. Phải xác định rõ hành động disable grant/refresh, access-token revocation propagation và trạng thái đã hoàn tất.

## 8. Opaque vs JWT: khả năng nhìn thấy revoke

| Khía cạnh | Opaque access token với introspection | JWT access token chỉ validate offline | JWT được RS introspect/kiểm revoke |
| --- | --- | --- | --- |
| Dạng token | Reference string khó đọc claims | Self-contained signed JWT | JWT, nhưng RS còn hỏi trạng thái |
| Cách RS kiểm | Hỏi AS/token store | Kiểm chữ ký, issuer, audience, expiry, scope tại RS | Kiểm JWT theo profile + trạng thái AS |
| Thấy revoke trước `exp` | Thường có nếu AS/introspection state cập nhật | **Không tự biết** nếu không có denylist/events/state check | Có thể, phụ thuộc introspection và cache |
| Độ trễ phụ thuộc | Network, AS, replica, positive cache | TTL JWT và local revocation mechanisms nếu có | Network, AS state, cache và local validation |
| Khi AS outage | Nếu không có dữ liệu đáng tin, **fail closed** | Vẫn có thể validate JWT nhưng có thể bỏ lỡ revoke | Policy quyết định; mặc định fail closed nếu trạng thái là bắt buộc |
| Khả năng log rò secret | Opaque vẫn là bearer credential | JWT cũng là bearer credential, claims có thể đọc | Không thay đổi độ nhạy cảm token |

**JWT vs opaque không quyết định “có revoke được hay không” theo tên định dạng.** Câu hỏi đúng là: *RS dùng thông tin nào để xác định token vẫn active và cập nhật thông tin đó nhanh đến mức nào?*

### 8.1. JWT còn chữ ký hợp lệ sau revoke

Ví dụ một JWT có `exp` sau 15 phút. Client bị disable sau 2 phút:

```text
T=00  AS issues JWT, exp at T=15
T=02  Admin revokes grant
T=03  RS local validation:
        signature OK, exp OK, aud OK, scope OK
        => có thể ALLOW nếu RS không có revocation state

T=03  RS revocation-aware introspection:
        AS active=false
        => DENY
```

Không gọi đây là "JWT bị bẻ chữ ký". Nó là **thỏa hiệp kiến trúc về tính sẵn sàng/latency và độ trễ thu hồi**. Nếu mục tiêu là revoke sớm, phải bổ sung denylist, introspection, grant-version check, event invalidation hoặc token TTL ngắn phù hợp.

### 8.2. Opaque cũng có cache stale

Opaque token thường được RS introspect, nhưng nếu RS cache `active=true` 5 phút thì **vẫn có thể tiếp tục chấp nhận token đã bị revoke** trong khoảng cache còn hiệu lực. Opaque **không tự bảo đảm revoke tức thì**.

### 8.3. AS introspection JWT cần trạng thái đủ tin cậy

Một AS có thể introspect JWT bằng cách kiểm chữ ký và `exp` **rồi trả `active=true` mà không tra revoke store**. Trong trường hợp đó, introspection **không phản ánh revoke như mong muốn**. Cần xem AS có lưu `jti`/grant version/session version/denylist và dùng trạng thái đó để tính `active` hay không.

### 8.4. Access token và refresh token khác vai trò

Refresh token dùng để **xin token mới tại AS**, không được RS chấp nhận làm access token. RFC 7662 có thể mô tả introspection cho các loại token AS hỗ trợ, nhưng **RS phải từ chối refresh token** khi gọi API, kể cả nếu một endpoint introspection nào đó báo token vẫn active ở ngữ cảnh refresh.

## 9. `active=true` không thay thế audience, scope và authorization

Khi introspection trả:

```json
{
  "active": true,
  "iss": "https://id.example.test",
  "aud": ["profile-api"],
  "scope": "profile:read",
  "client_id": "profile-viewer",
  "sub": "subject-42"
}
```

Token **không dành cho `orders-api`**. RS orders phải từ chối, không vì AS nói active mà accept.

### 9.1. Công thức quyết định an toàn

```text
allow(request, token, introspection) =
    introspection_is_authenticated_and_trusted
    AND introspection.active == true
    AND token_type_matches_resource_policy
    AND issuer_matches_expected_authority
    AND audience_contains_this_resource
    AND token_time_policy_is_satisfied
    AND token_scope_contains_required_permission
    AND client/subject/tenant_policy_allows
    AND resource_level_authorization_allows
    AND sender_binding_valid_if_required
```

Một số điều kiện có thể được AS bảo đảm và **ràng buộc riêng cho RS** trong giao thức tin cậy. Tuy nhiên nếu RS cần chứng minh audience/issuer và response không cung cấp field hoặc bảo đảm tương đương, **không đoán**. Một `active=true` “chung chung” không là giấy phép gọi mọi API.

### 9.2. Không nhầm authentication với authorization

- **Introspection active:** token còn dùng được theo AS.
- **Authentication tại RS:** có bearer credential hợp lệ và principal theo token profile.
- **Authorization:** principal/client có được phép truy cập endpoint, tenant, object này không?

Ví dụ `scope=orders:read` nhưng truy cập order thuộc tenant khác:

```text
active=true
aud=orders-api
scope=orders:read
subject=user-A
requested_order.tenant=tenant-B
user-A belongs only tenant-A

=> 403 FORBIDDEN despite active token.
```

### 9.3. Service principal không thành end user

Với `grant_type=client_credentials`, token có thể phản ánh **service principal** mà không có end user tham gia. Nếu RS tự đọc `sub` rồi tạo user session, nó có thể tạo identity confusion. Hãy dùng client/grant/profile semantics và policy dành riêng **SERVICE** so với **USER**.

### 9.4. OIDC ID token không phải access token

OIDC ID token có `aud` là RP/client, không dành cho RS nghiệp vụ. Một ID token hợp lệ vẫn phải bị từ chối khi caller gửi như access token tới API không hỗ trợ profile đó. Introspection response không cho phép bỏ kiểm token type.

## 10. Revocation propagation: mạnh/yếu tùy kiến trúc

**Propagation time** là thời gian từ khi revoke được AS chấp nhận/commit đến khi các RS không còn chấp nhận token trong mọi đường thực thi được bảo vệ.

```text
T0      AS commits REVOKED
T0+5ms  AS primary introspection reads REVOKED
T0+2s   Replica in region B receives revoke
T0+30s  RS X positive introspection cache expires
T0+60s  RS Y cache expires

Effective worst observed rejection time:
    depends on replication delay + RS cache expiry + other paths
```

Các con số **chỉ minh họa**, không phải SLA hay thời gian thực của mọi hệ thống. Nếu đường đi cache ở RS và replica cùng cũ, khả năng nhận lại token active có thể kéo dài theo nhiều thành phần.

### 10.1. Synchronous revocation state

Một hệ thống có primary authoritative store và introspection truy cập trạng thái vừa commit có thể phản ánh revoke gần như ngay cho request tiếp theo, nếu không có cache cũ. Nhưng còn lỗi mạng, failover, race và request đã được authorized từ trước; không nên hứa **“0 ms sau revoke không còn request nào hoàn tất”** nếu architecture không hỗ trợ.

### 10.2. Eventual consistency và multi-region

AS có thể replicate token status qua nhiều vùng:

- Region A nhận revoke và trả `active=false`.
- Region B đang dùng replica trễ, vẫn trả `active=true`.
- RS có load balancer lần lượt gọi A/B, tạo **kết quả không đơn điệu** nếu không có versioning/consistency constraints.

Mitigations:

1. Ghi **revocation epoch/grant version** vào store và bảo đảm reads đủ nhất quán theo yêu cầu.
2. Chuyển introspection của token nhạy cảm tới nguồn authoritative hoặc replica đạt staleness bound.
3. Phân phối **invalidate events** tới caches/RS, có retry, ordering và replay recovery.
4. Dùng **short-lived access token** để giới hạn cửa sổ cuối cùng.
5. Đo **time-to-deny**, không chỉ time-to-revoke API response.

### 10.3. Thực thi “đã revoke thì không hồi sinh”

Một node sau khi biết token revoked không nên bị replica cũ khiến nó chuyển ngược sang active nếu chính sách yêu cầu monotonic rejection. Có thể duy trì một **revoked marker/version** đủ tin cậy và không xóa nó quá sớm. Cơ chế cụ thể tùy storage, nhưng invariant cần kiểm:

```text
Once token/grant is terminally revoked,
no stale replication/update may legitimately restore ACTIVE
without a new, separately authorized grant/token.
```

### 10.4. Request đã qua check trước revoke

Một API request có thể được RS introspect và authorize lúc T0-1ms, rồi admin revoke tại T0 khi nghiệp vụ đang chạy. Revocation thông thường **không rollback một transaction nghiệp vụ đã qua authorization**. Với giao dịch rủi ro cao (chuyển tiền, xóa dữ liệu lớn), có thể cần **re-check authority tại commit**, transaction lock hoặc step-up/approval riêng. Không dùng introspection như cơ chế rollback chung.

## 11. Cache introspection: performance đổi lấy revocation freshness

Introspection mỗi API request có thể tăng latency/throughput load lên AS, nên nhiều RS hoặc API gateway dùng cache. **Cache một quyết định `active=true` cũng là cache một quyền truy cập**.

### 11.1. Positive caching

Ví dụ RS cache response active trong 60 giây:

```text
T=00   RS introspects token -> active=true, caches for 60s
T=05   AS revokes token -> active=false centrally
T=10   RS cache hit -> active=true (STALE)
T=60   cache expires; RS introspects -> active=false; DENY
```

**Trong trường hợp này revoke có thể chậm đến hết TTL cache** (cộng độ trễ replication/clock/race). Không đặt TTL cache vượt `exp-now`. TTL nên phản ánh security objective và độ nhạy quyền, không chỉ tối ưu performance.

### 11.2. Negative caching

Cache `active=false` có thể giảm tải AS trước token giả/replay, nhưng cần chú ý:

- Attacker có thể gửi hàng triệu chuỗi khác nhau gây **cache pollution/DoS**.
- Token từ trạng thái chưa có hiệu lực/replication chưa tới có thể trở nên active hợp lệ sau đó; **negative TTL** quá dài gây false deny.
- Không cache raw token vào log/key dump/diagnostics không bảo vệ.
- Không cache network/auth errors như một response AS `active=false` có ý nghĩa nghiệp vụ; cần phân biệt để alert.

### 11.3. Khóa cache phải cô lập ngữ cảnh

Tối thiểu cache result cần gắn **issuer/AS, RS/audience/policy context, token reference, token type khi áp dụng**. Không dùng một response active từ `orders-api` để authorize `payments-api`.

```text
Possible cache key conceptual fields:
    trusted_issuer
    resource_server_identifier
    token_kind_or_profile
    high_entropy_token_lookup_digest

Cache value:
    introspection response (minimized)
    insertion/expires timestamp
    issuer/token/grant version if supported
```

Một hash thường của token có thể lộ mối liên hệ hoặc cho phép brute-force nếu token yếu. Khi cần cache key không chứa raw token, có thể dùng **HMAC với khóa cache nội bộ được bảo vệ** theo review; đây không phải nghĩa vụ RFC 7662. Dù dùng HMAC, cache value/metrics vẫn cần quyền đọc và retention hợp lý.

### 11.4. Cache invalidation qua event

AS có thể gửi sự kiện token/grant revoked tới RS hoặc cache layer. Điều này giúp giảm latency, nhưng **event có thể mất, trễ, lặp hoặc đảo thứ tự**, nên vẫn cần TTL, reconcile và policy fail closed. Đừng để hệ thống chỉ dựa vào một webhook không xác thực để invalidation (hoặc tệ hơn, để webhook giả tạo trạng thái active).

### 11.5. Tách SLA performance và security

Một API rủi ro thấp có thể cho phép short positive cache nếu đã đánh giá; API thanh toán/admin có thể yêu cầu stronger freshness. Hãy định nghĩa:

- **Maximum acceptable stale allow interval** khi revoke.
- **Maximum introspection endpoint latency**/timeout.
- **Expected AS outage behavior**.
- **Cache TTL** theo issuer/token type/scope/resource.
- **How to force emergency deny** khi sự cố nghiêm trọng.

Không công bố “revocation effective immediately” khi vận hành thực tế có `active=true` cache 5 phút.

## 12. Mô hình dữ liệu AS: trạng thái revocation là nguồn sự thật

Một AS phát opaque tokens có thể lưu trạng thái token trong database/KV store. Với JWT, AS muốn hỗ trợ revoke trước expiry có thể lưu **grant state, token IDs, denylist hoặc security version**, tùy thiết kế.

### 12.1. Bảng token/grant minh họa

```text
AuthorizationGrant:
    grant_id                 server-generated identifier
    subject_or_client_ref    verified principal
    oauth_client_id          registered client
    resource_audience        approved resource server(s)
    approved_scope_set       only authorized scopes
    tenant_ref               policy-bound tenant
    grant_status             ACTIVE | REVOKED | EXPIRED | DISABLED
    grant_version            monotonically increasing version
    revoked_at               optional trusted timestamp

AccessTokenRecord:
    token_lookup_digest      non-reversible keyed reference/hash
    grant_id                 foreign key to AuthorizationGrant
    token_type               ACCESS
    token_status             ACTIVE | REVOKED | EXPIRED
    issued_at                trusted issuance time
    not_before               optional effective time
    expires_at               bounded expiry time
    audience                 approved audience
    scope                    approved token scope
    token_identifier         jti or opaque record key
```

**Đây là mô hình logic**, không phải schema tiêu chuẩn bắt buộc của RFC 7662. Các hệ thống có thể lưu token hash, reference ID, security version hoặc event log thay vì lưu raw bearer token. Cần bảo vệ dữ liệu liên kết subject/client/scopes/tenant và quyền truy vấn.

### 12.2. Tính `active` trên server

Pseudocode:

```text
introspect(token, verifiedIntrospectionCaller):
    require callerAuthenticated(verifiedIntrospectionCaller)
    require callerAuthorizedForIntrospection()

    record = tokenStore.lookupByProtectedTokenReference(token)

    if record missing or record.kind not allowed:
        return {"active": false}

    grant = grantStore.load(record.grantId)

    if caller not allowed to know/use this token for this resource:
        return {"active": false}

    active =
        record.status == ACTIVE
        AND grant.status == ACTIVE
        AND now >= record.notBefore, if present
        AND now < record.expiresAt
        AND clientRegistrationNotDisabledUnderPolicy
        AND requiredAccountOrTenantStateStillValid

    if not active:
        return {"active": false}

    return minimalMetadataAllowedToCaller(record, grant,
                                          active=true)
```

**Đây không phải RFC-mandated code**; AS phải định nghĩa rõ chính sách với client disable, account lock, scope changes, token family và audience. Cần tránh rò token existence hoặc subject metadata tới caller không có quyền.

### 12.3. Vì sao cần kiểm grant state?

Một token record riêng có thể vẫn đánh dấu `ACTIVE`, nhưng **parent grant bị thu hồi** vì user đã rút consent. Nếu introspection chỉ kiểm token row, nó có thể trả `active=true` sai:

```text
token_record.status  = ACTIVE
authorization_grant.status = REVOKED

Result must reflect intended revocation model:
    active=false
```

Trong một số kiến trúc, AS cập nhật trực tiếp mọi token con; kiến trúc khác kiểm `grant_version` hoặc parent grant khi introspect. Điều bắt buộc từ security objective là **không sử dụng state đã hết quyền**, không phải cứng nhắc cách thiết kế schema.

### 12.4. Không khôi phục token cũ bằng cách “unrevoke”

Nếu user muốn cho ứng dụng quyền trở lại sau khi revoke, thông thường nên có **authorization grant/token issuance mới**. Không âm thầm chuyển một refresh token bị revoke về active, vì attacker có thể vẫn giữ bản sao. Việc restore account/client policy là quyết định khác với hồi sinh token material cũ.

## 13. Java/Spring Security: RS sử dụng opaque token introspection

Spring Security Resource Server có hỗ trợ **opaque token introspection**, giúp bảo vệ API bằng response của AS. Bản cấu hình cơ bản:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: PLACEHOLDER_FROM_SECRET_MANAGER_AT_RUNTIME
```

**Cảnh báo:** `client-secret` ở trên là placeholder **không dùng được**. Trong production, đưa secret từ secret manager/managed configuration, bảo vệ quyền đọc, audit và rotation; không commit credential vào source. URI phải được tin cậy, cố định theo AS đã đăng ký; cần TLS truststore/timeout và xử lý outage.

**Các phiên bản Spring Boot/Spring Security có API, properties và options có thể khác nhau.** Kiểm tra compatibility khi dùng framework thật. Không tự suy rằng chỉ cấu hình `opaquetoken` đã kiểm tenant/audience đúng hoặc chặn mọi token type confusion.

### 13.1. Filter chain cho Orders API

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerSecurity {
    @Bean
    SecurityFilterChain ordersSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.opaqueToken(
                Customizer.withDefaults()
            ));

        return http.build();
    }
}
```

**Ý nghĩa:**

- Request với Bearer token được resource server đưa qua **`OpaqueTokenIntrospector`**.
- Nếu AS trả `active=false`, token không được chấp nhận để thiết lập authenticated principal.
- Khi token active và introspection response có `scope`, Spring có thể ánh xạ scope thành authorities `SCOPE_...` theo configuration.
- Endpoint còn phải **kiểm audience/issuer/token type/client và tenant/resource policy** như phần tiếp theo.
- Không tắt CSRF/cookie/session security máy móc: API thuần Bearer và ứng dụng đồng thời dùng cookie/browser có threat model khác nhau.

### 13.2. Kiểm audience và issuer sau introspection

Một `active=true` từ AS không đủ nếu client/RS không có audience contract rõ. Có thể bọc một introspector đã cấu hình để bổ sung policy. Ví dụ Java **minh họa** với attribute types thực tế từ Spring/AS:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PolicyCheckingIntrospector implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;

    public PolicyCheckingIntrospector(
        OpaqueTokenIntrospector delegate,
        String expectedIssuer,
        String expectedAudience
    ) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedIssuer = Objects.requireNonNull(expectedIssuer);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // delegate đã thực hiện authenticated POST tới AS và yêu cầu active=true.
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        if (!expectedIssuer.equals(issuer)) {
            throw new BadOpaqueTokenException("Invalid token issuer");
        }

        Object audience = principal.getAttribute("aud");
        boolean matchesAudience =
            (audience instanceof String s && expectedAudience.equals(s))
            || (audience instanceof Collection<?> values
                 && values.contains(expectedAudience));

        if (!matchesAudience) {
            throw new BadOpaqueTokenException("Invalid token audience");
        }

        return principal;
    }
}
```

Ví dụ dùng Java 16+ vì pattern matching `instanceof`. Đây là **lớp minh họa** chứ chưa có bean wiring cho delegate, và chỉ kiểm hai trường để dễ thấy security boundary. Triển khai thực tế cần:

1. Đăng ký **delegate introspector được Spring/SDK cấu hình đúng URI, TLS, client authentication**.
2. Bảo đảm `active=false`/bad JSON/HTTP error/timeout từ delegate **không được coi là principal hợp lệ**.
3. Chỉ nhận **token type/access token profile** được RS cho phép; không nhận refresh/ID/client assertion.
4. Validate `exp`/`nbf`/required scope/client/tenant/sender proof theo mô hình AS/RS.
5. Nếu AS không cung cấp `aud` hoặc `iss` trong metadata, **đòi hợp đồng xác minh tương đương tại AS** hoặc deny, không tùy tiện comment-out guard.
6. Không log `token` trong exception hoặc debug `principal` đầy đủ.

### 13.3. Đăng ký bean cần tránh tự tham chiếu

Nếu tạo một `@Bean OpaqueTokenIntrospector` nhận `OpaqueTokenIntrospector` làm argument trong cùng context, có nguy cơ circular dependency hoặc override auto-config không mong muốn. Cách tích hợp tùy phiên bản framework: tạo delegate riêng (bằng `SpringOpaqueTokenIntrospector` hoặc builder tương ứng) rồi **bọc** nó trong policy checker, hoặc cấu hình introspector qua DSL được hỗ trợ. Đừng dùng một bean trả lại chính nó.

### 13.4. Token inactive và HTTP response RS

Với token sai/hết hạn/revoked, resource server thường trả **401 Unauthorized** cùng OAuth Bearer error `invalid_token` theo RFC 6750 khi phù hợp. Với token active nhưng thiếu `orders:write`, thường trả **403 Forbidden** / `insufficient_scope`.

**Đừng để một network outage của introspection chuyển thành “anonymous request được xem như authenticated”**. Một outage có thể được trình bày thành 503 ở tầng service nếu muốn phân biệt lỗi khả dụng với credential invalid, nhưng **không cấp quyền** khi không có bằng chứng active đáng tin.

### 13.5. Không tự đặt `active=true` trong unit test rồi xem như production

Một test mock `OpaqueTokenIntrospector` có thể bỏ qua lỗi TLS/Basic/AS/JSON. Cần **integration test thật** với một AS test có hỗ trợ token revoke và introspection; riêng unit test để xác nhận controller/authorization policy không được dùng thay kiểm tra end-to-end.

## 14. Java: mô hình client introspection độc lập

Để hiểu request/response, có thể hình dung một RS gọi AS bằng Java `HttpClient`. Trong production, **ưu tiên Spring Security/resource-server SDK** thay vì tự viết introspection client không đầy đủ.

### 14.1. Bộ dựng POST và phân loại response

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

public final class EducationalIntrospectionClient {
    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private final URI trustedEndpoint =
        URI.create("https://id.example.test/oauth2/introspect");

    // Values phải đến từ secret manager, không hardcode.
    public HttpRequest newRequest(
        String accessToken,
        String introspectorClientId,
        char[] introspectorClientSecret
    ) {
        if (accessToken == null || accessToken.isBlank()) {
            throw new IllegalArgumentException("Access token is required");
        }

        // Form-encode cả client ID và client secret theo OAuth 2.0
        // trước khi ghép thành HTTP Basic credentials.
        String body = "token="
            + URLEncoder.encode(accessToken, StandardCharsets.UTF_8)
            + "&token_type_hint=access_token";

        String encodedId = URLEncoder.encode(
            introspectorClientId, StandardCharsets.UTF_8);
        String encodedSecret = URLEncoder.encode(
            new String(introspectorClientSecret), StandardCharsets.UTF_8);
        String basicParts = encodedId + ":" + encodedSecret;
        String basic = Base64.getEncoder().encodeToString(
            basicParts.getBytes(StandardCharsets.UTF_8));

        return HttpRequest.newBuilder(trustedEndpoint)
            .timeout(Duration.ofSeconds(5))
            .header("Content-Type",
                "application/x-www-form-urlencoded")
            .header("Accept", "application/json")
            .header("Authorization", "Basic " + basic)
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();
    }
}
```

**Cảnh báo:** đây là **mã học thuật về HTTP transport**, **không phải client production hoàn chỉnh**. Theo RFC 6749 `2.3.1, client ID/secret cần form-encode trước khi ghép vào Basic; ví dụ đã minh họa bước này nhưng vẫn tạo `String` chứa secret không thể xóa đáng tin cậy, và chưa triển khai structured error parsing, issuer/audience policy, cache/retry, key rotation hoặc TLS tuning của hệ thống thực. Trong production nên dùng thư viện OAuth client được kiểm thử, secret manager và resource-server framework; không sao chép mẫu này nguyên trạng cho hệ thống thật.

### 14.2. Kiểm response ở tầng JSON

Pseudocode kiểm response:

```text
response = executeAuthenticatedIntrospectionRequest()

if HTTP status != 200:
    raise IntrospectionUnavailableOrUnauthorized

json = strictParseJsonObject(response.body)
if json.active is not Boolean:
    raise InvalidIntrospectionResponse

if json.active == false:
    raise InvalidAccessToken

require issuer/audience/token_type/exp/nbf/scope/client policy
require resource/tenant authorization separately

return authenticatedPrincipalWithVerifiedClaims
```

Không convert `"false"` (string) thành boolean theo parser permissive; không dùng `json.get("active") != null` để coi giá trị true; không default `active=true` khi field thiếu.

### 14.3. Tại sao token response 200 cần parse nghiêm?

Một lỗi kiểu:

```java
// SAI: response bất kỳ từ endpoint được xem là allow.
if (response.statusCode() == 200) {
    return allow();
}
```

sẽ **chấp nhận cả `{"active":false}`**. Lỗi này có thể làm vô hiệu toàn bộ thiết kế revoke. Phải parse và kiểm **boolean true chính xác**, sau đó chạy policy checks.

## 15. Revocation tại AS: ví dụ Java/pseudocode theo grant state

Khi xử lý revoke, AS không nên tự “xóa access token string khỏi log” mà phải thay **authorization state** ở nguồn tin cậy.

```java
// PSEUDOCODE: không là API Spring Authorization Server built-in.
@org.springframework.transaction.annotation.Transactional
public void revokeGrant(
    String grantRef,
    VerifiedAuthority caller
) {
    var grant = grantRepository.lockById(grantRef);
    if (grant == null) {
        return; // Tùy endpoint/profile, tránh lộ existence.
    }

    policy.requireCallerCanRevoke(caller, grant);

    if (!grant.isRevoked()) {
        grant.markRevoked();
        grant.incrementVersion();
        grantRepository.save(grant);
    }

    // Nếu tokenStore nằm cùng database, cập nhật trạng thái cần thiết
    // trong một transaction phù hợp.
    // Nếu event bus khác hệ thống, dùng outbox/retry/reconcile.
    outbox.enqueueGrantRevoked(grantRef, grant.version());
}
```

`VerifiedAuthority`, `grantRepository`, `outbox` và các method là abstractions minh họa, không phải class có sẵn. **Không trả 200 vô điều kiện cho caller chưa được xác thực/ủy quyền**; khả năng che token existence của RFC 7009 không làm mất nghĩa vụ client authentication.

### 15.1. Không publish event trước trạng thái bền vững

Nếu AS gửi `revoked` event nhưng DB transaction rollback, RS có thể deny token đáng lẽ còn hợp lệ; ngược lại DB commit nhưng event mất khiến cache vẫn active. **Transactional outbox** hoặc thiết kế consistency tương đương cho phép publish sau commit và retry/reconcile. Dù có outbox, RS vẫn cần TTL/freshness bound.

### 15.2. Không viết lại JWT signature khi revoke

Một JWT đã phát không thể sửa byte/claims mà vẫn giữ chữ ký cũ. Revocation-aware AS có thể tra `jti`, grant ID, session/security version hoặc denylist để trả `active=false`. Nếu muốn phát token thay thế, đó là **issuance mới**, không phải sửa JWT cũ.

### 15.3. Spring Authorization Server

Spring Authorization Server có các khái niệm như `OAuth2AuthorizationService`, token metadata/invalidation và các endpoint của AS. Tùy phiên bản và storage adapter, cần kiểm:

- Revocation endpoint xử lý đúng client authentication/ownership/token hint.
- Access/refresh tokens được gắn đúng authorization grant.
- Introspection lookup đọc **trạng thái invalidated** và consent/grant policy cần thiết.
- Multi-instance persistence có consistency phù hợp.
- Revoked token không được “active lại” sau restart/cache miss/replication.

Không suy từ việc framework có endpoint `/oauth2/introspect` rằng toàn bộ hệ thống đã bảo đảm revoke tức thì: response cache, resource server behavior và replication vẫn do kiến trúc vận hành quyết định.

## 16. Bảo mật introspection endpoint

### 16.1. Introspection là điểm tiết lộ metadata

Response active có thể chứa `sub`, `client_id`, `scope`, `aud`, thời hạn và thông tin nhận diện chủ thể. Nếu một client bất kỳ có thể quét token qua endpoint, nó có thể:

- Xác định một chuỗi token có tồn tại/đang active không.
- Dò dịch vụ/user đang được cấp quyền gì.
- Đoán tenant hoặc account.
- Tăng tải AS qua brute-force token lookup.

Biện pháp:

1. **Authenticate/authorize** caller; scopes/roles phù hợp introspection.
2. Bảo vệ bằng TLS, giới hạn IP/mTLS khi threat model cần.
3. Trả **tối thiểu metadata** cần cho RS, nhất là khi caller không được biết subject.
4. Trả inactive dạng `{"active":false}` khi không muốn tiết lộ token details theo RFC.
5. Rate limit, quotas, anomaly detection và bảo vệ store khỏi token scans.
6. Không log raw token hoặc Basic header.

### 16.2. Không cho phép token tự định tuyến AS

Một resource server multi-issuer nếu nhìn token rồi tải URL từ claim `iss` chưa verify có thể làm SSRF/token exfiltration:

```text
Attacker sends opaque string or JWT with untrusted iss URL
RS chooses introspection endpoint from that URL
RS sends bearer token to attacker's server
```

**Đúng:** issuer/endpoint được lựa chọn từ **registration/trust configuration** đáng tin và request routing đã xác minh, không từ URL bên trong token chưa xác thực.

### 16.3. Không log token dù response inactive

Bearer token không trở nên “an toàn để log” sau khi introspection trả false:

- Token có thể được đồng bộ sai/AS tạm lỗi.
- Client có thể đang gửi refresh/client assertion nhầm loại.
- Một bản log có thể lưu credential còn active của một môi trường khác.
- Kết hợp token với session/user metadata tăng rủi ro truy dấu.

Log reason code và request ID; không in token prefix/suffix theo mặc định.

### 16.4. Client authentication credential riêng cho RS

Introspection Basic secret/private key phải:

- Không nhúng trong SPA/native app.
- Không dùng chung với resource-owner password.
- Được lưu trong secret manager/PKI, có rotate và quyền tối thiểu.
- Không bị outbound proxy/HTTP interceptor dump headers.
- Không được gửi qua redirect tới host khác.

AS nên audit việc RS gọi introspection theo **registered introspector identity**, nhưng không bao gồm raw token.

### 16.5. Phân biệt caller authorization với token authorization

AS xác thực `orders-api-introspector` nghĩa là **RS có quyền hỏi**; không nghĩa token của `user-42` active. Ngược lại một token active không nghĩa bất cứ caller nào được xem metadata của nó. Hai lớp authorization phải độc lập.

## 17. Xử lý lỗi và fail-closed dưới tải cao

### 17.1. Hỏng AS không tạo quyền

Mô hình nguy hiểm:

```java
// SAI: biến outage introspection thành bypass.
try {
    return introspectAndAuthorize(token);
} catch (Exception e) {
    return allowBecauseInternalNetwork();
}
```

Nếu mục tiêu security là **mọi request cần active state mới nhất**, endpoint không được cho qua khi AS timeout. Tùy user experience, RS có thể trả **503 Service Unavailable** thay vì 401 để mô tả dependency outage, nhưng không tạo authenticated principal từ sự im lặng.

### 17.2. Retry phải có giới hạn

- Retry network/transient `5xx` có **timeout, backoff, jitter, max attempts**.
- Không retry vô hạn mỗi request, tạo cascading failure lên AS.
- Không retry `invalid_client` bằng cùng secret hàng nghìn lần; đây là lỗi cấu hình/rotation.
- Không retry `active=false` để “tìm” một node chưa biết revoke.
- Circuit breaker chỉ được dùng theo chính sách đã định; không mở đường allow khi circuit open.

### 17.3. Fallback bằng cache chỉ khi security contract cho phép

Một số hệ thống chấp nhận **bounded stale introspection** trong outage cho API rủi ro thấp. Nếu làm vậy, phải định nghĩa:

- Tối đa stale interval và loại resource được phép.
- Không dùng stale positive cache sau **đã biết** token/grant revoked.
- Không dùng stale cache cho admin/payment API nếu mục tiêu revoke tức thì.
- Monitoring, audit, emergency deny và backpressure.

Đây là **ngoại lệ đánh đổi có chủ đích**, không phải mặc định được khuyến nghị. Nếu không có yêu cầu cụ thể, **fail closed** là cách bảo thủ.

### 17.4. Error mapping

Ví dụ quy tắc phân loại:

| Sự kiện nội bộ | HTTP với API caller (minh họa) | Audit code |
| --- | --- | --- |
| Token inactive | 401 / `invalid_token` | `INTROSPECTION_INACTIVE` |
| Token active, audience sai | 401 / `invalid_token` | `AUDIENCE_MISMATCH` |
| Token active, scope thiếu | 403 / `insufficient_scope` | `SCOPE_DENIED` |
| Token active, policy tenant deny | 403 | `RESOURCE_POLICY_DENIED` |
| AS introspection 401 | 503/5xx tùy service contract; **không allow** | `INTROSPECTION_CLIENT_AUTH_FAILED` |
| Introspection timeout | 503 tùy service contract; **không allow** | `INTROSPECTION_UNAVAILABLE` |
| JSON thiếu `active` | 503/401 tùy parser/error contract; **không allow** | `INTROSPECTION_INVALID_RESPONSE` |

RS nên tránh trả thông tin nhạy cảm về token/subject cho caller lỗi. Có thể ghi **mã lý do đã kiểm soát** cho người vận hành mà không lộ raw token.

## 18. Introspection trong OAuth/OIDC và các grant khác

### 18.1. Authorization Code + PKCE

User được OP/AS xác thực và consent, AS phát code, client đổi code với `code_verifier` qua token endpoint, nhận access token dành API. **Introspection không thay PKCE**: nó chỉ kiểm token sau khi phát hành. Nếu authorization code bị chặn, PKCE vẫn cần để chống đổi code trái phép.

### 18.2. Client Credentials

Một service dùng `client_credentials` có thể nhận access token M2M. Introspection trả `client_id`, scope/audience và có thể `sub` theo token profile. **Không tự tạo end-user identity** chỉ vì có `sub`. Revoke client registration hoặc credential không nhất thiết làm mọi JWT access token cũ bị RS offline từ chối ngay.

### 18.3. Refresh-token rotation

Một client dùng refresh token để xin access token mới. Khi AS phát hiện **reuse một refresh token đã rotate**, nó có thể thu hồi token family/authorization grant theo security policy. Sau đó introspection cho access token liên quan **có thể phản ánh `active=false`** nếu AS/store được thiết kế liên kết token family và grant.

Đừng mặc định mọi provider có cùng family revoke semantics; phải kiểm hợp đồng/triển khai.

### 18.4. OIDC logout

User logout RP hay OP **không tự bằng** revoke mọi access token. Nếu hệ thống có logout-triggered grant revoke, AS có thể cập nhật state và introspection phản ánh inactive. Nếu không, access token vẫn có thể active. Cần phân biệt **OP SSO session**, **RP application session**, **refresh token** và **access token**.

### 18.5. Sender-constrained tokens

Với mTLS-bound token (RFC 8705) hoặc DPoP-bound token (RFC 9449), introspection có thể trả confirmation metadata như `cnf` theo profile. Nhưng **AS trả active=true không thay việc RS kiểm client certificate hoặc DPoP proof** trên request. Nếu RS bỏ sender proof, token đã bị sao chép có thể dùng trái mục đích.

## 19. Kiểm thử: revocation phải làm thay đổi kết quả thực tế

Test quan trọng nhất là **E2E revoke → introspection inactive → RS deny**, không chỉ test AS trả 200 ở revocation endpoint.

### 19.1. Ma trận test chức năng

| # | Kịch bản | Introspection/RS kỳ vọng |
| --- | --- | --- |
| 1 | Opaque access token active, audience/scope đúng | `active=true`, RS có thể allow sau policy |
| 2 | Opaque token chưa được cấp | `active=false`, RS deny |
| 3 | Token hết hạn `exp` | `active=false` hoặc RS time-check deny |
| 4 | Token chưa tới `nbf` | RS deny / AS không active theo policy |
| 5 | Token vừa revoke qua RFC 7009 | Introspection trạng thái mới `active=false` |
| 6 | Revoke token không tồn tại với client authenticated | Endpoint xử lý theo RFC 7009, không lộ tồn tại |
| 7 | Revocation request client secret sai | Không revoke trái phép; lỗi client authentication |
| 8 | Client khác thử revoke token không thuộc quyền | AS từ chối/che token existence theo policy |
| 9 | Revoke refresh token, có cascade configured | Access token liên quan chuyển inactive theo policy |
| 10 | Revoke access token, refresh vẫn active theo policy | Test semantics AS riêng, không tự đoán cascade |
| 11 | User revoke consent | Grant không dùng để mint token mới, token cũ theo policy |
| 12 | Admin disable OAuth client | Token issuance bị chặn; access token state theo policy |
| 13 | Revoke token family do refresh reuse | Các token liên quan bị vô hiệu theo policy |
| 14 | JWT revoke, RS chỉ offline validation | Nhận diện **không phản ánh revoke tự động** |
| 15 | JWT revoke, AS tracks `jti`/grant | Introspection phản ánh inactive |
| 16 | Token active có wrong audience | `active=true` có thể xảy ra, RS **vẫn deny** |
| 17 | Token active thiếu scope | RS 403, không tăng quyền |
| 18 | Token active thuộc tenant khác | RS policy deny |
| 19 | Client Credentials token gửi endpoint chỉ nhận user | RS deny theo principal type |
| 20 | OIDC ID token gửi làm access token | RS deny token type/aud |
| 21 | Refresh token gửi RS | RS deny, dù refresh còn active ở AS |
| 22 | Introspection hint sai | AS xử lý theo RFC; RS không tin hint là token type |
| 23 | Introspection no `token` | 400/lỗi chuẩn, không allow |
| 24 | Introspection không có RS authentication | AS không tiết lộ protected metadata |
| 25 | Introspection caller không có quyền token đó | `active=false` hoặc lỗi theo AS policy, không metadata leak |
| 26 | Introspection trả `{"active":false}` | RS deny dù HTTP 200 |
| 27 | Response `{"active":"true"}` | Deny vì kiểu string không phải Boolean |
| 28 | Response thiếu `active` | Fail closed |
| 29 | Response `{"active":true}` nhưng `aud` thiếu | Deny nếu không có AS contract tương đương |
| 30 | HTTP 401 từ introspection | Misconfigured RS auth, fail closed |
| 31 | HTTP 5xx/timeout | Fail closed hoặc fallback đã được đánh giá rõ |
| 32 | Basic introspection secret rotate | Secret cũ bị từ chối, mới hoạt động |
| 33 | Token đã revoke nhưng RS positive cache còn | Đo stale-allow window, so với security SLA |
| 34 | Cache hết TTL sau revoke | RS introspect lại → inactive → deny |
| 35 | Cache theo audience sai | Response của API A không được dùng cho API B |
| 36 | Multi-region replication trễ | Không có token được active lại trái chính sách |
| 37 | Revoke và API request đồng thời | Xác định ordering/authorization boundary |
| 38 | AS startup sau revoke | Token cũ không tự trở lại active |
| 39 | Introspection rate limit | Không tạo bypass, hành vi lỗi rõ |
| 40 | Token trong URL/logs/APM | Test security thất bại |
| 41 | DPoP/mTLS token thiếu proof | RS deny dù introspection active |
| 42 | Wrong introspection issuer host | RS không gửi token tới untrusted endpoint |
| 43 | Revoked grant nhưng token row active | Introspection phải xét parent grant state |
| 44 | Malformed form-urlencoded/duplicate `token` fields | AS không parse ambiguity thành quyền |

### 19.2. Test cho `active=false`

Pseudocode:

```java
// Java test pseudocode; các helper không là API có sẵn.
@Test
void revokedTokenDoesNotAuthorizeOrdersApi() {
    var accessToken = testAuthorizationServer.issueOpaqueAccessToken(
        "orders-api", "orders:read");

    assertTrue(testAuthorizationServer.introspect(accessToken).active());

    testAuthorizationServer.revoke(accessToken);

    assertFalse(testAuthorizationServer.introspect(accessToken).active());
    assertEquals(401, ordersApi.getOrders(accessToken).statusCode());
}
```

Các method `testAuthorizationServer.issueOpaqueAccessToken`, `revoke`, `ordersApi.getOrders` là **test fixtures giả**. Test thật phải gọi HTTP endpoints đã cấu hình; không chỉ fake boolean để coi integration hoạt động.

### 19.3. Test cache stale và boundary

```text
Given:
  introspection positive TTL = 30 s
  token exp = T+120 s
  AS revokes token at T+5 s

When:
  RS receives request at T+6 s and T+31 s

Then:
  T+6 s may be stale-allowed under this explicit cache policy
  T+31 s must revalidate and deny if AS state visible
  Observed time-to-deny must meet defined security objective
```

Nếu security SLA là **revoke trong 2 giây**, một cache 30 giây **không đạt** trừ khi có invalidation và các bảo đảm khác. Không test bằng `Thread.sleep` tùy tiện trong production; dùng controlled clock/test fixtures và kiểm consistency.

### 19.4. Negative path phải kiểm side effects

Khi AS trả inactive hoặc RS chưa kiểm được token:

1. Không chạy business write, DB update, money transfer, message publish trái quyền.
2. Không tự tạo session authenticated hoặc user principal giả.
3. Không gọi downstream API bằng credential đó.
4. Không giữ stale-positive cache sau khi đã nhận revoked marker.
5. Không log raw bearer token hay introspection credentials.
6. Không tự fallback bỏ audience/scope.

### 19.5. Metrics để xác minh vận hành

Không đưa token ID hoặc raw token vào metric labels vì cardinality, privacy và security. Dùng metrics tổng hợp:

```text
introspection_requests_total{result="active|inactive|error"}
introspection_request_duration_seconds
introspection_cache_hits_total{kind="positive|negative"}
introspection_fail_closed_total{reason="timeout|bad_response|auth"}
revocation_requests_total{result="accepted|error"}
revocation_propagation_delay_seconds
resource_access_denied_total{reason="inactive|audience|scope|policy"}
```

Để đo `revocation_propagation_delay_seconds` phải có test/telemetry correlation **không làm lộ bearer token** và định nghĩa rõ thời điểm revoke commit/RS reject. Không suy đoán từ metric tổng số `active=false` rằng revoke luôn nhanh.

## 20. Tình huống thực tế

### Tình huống A — User rút quyền ứng dụng, API vẫn trả 200

User đã revoke calendar access, nhưng `calendar-api` vẫn trả dữ liệu:

1. AS đã ghi grant `REVOKED` chưa?
2. Introspection trực tiếp của AS trả `active=false` chưa?
3. RS đang dùng positive cache TTL bao lâu?
4. Token là JWT offline hay opaque introspected?
5. API request đã qua authorization trước thời điểm revoke?

Không chỉ nhìn UI “Disconnected” và kết luận hệ thống đã chặn tất cả requests.

### Tình huống B — Opaque token bị revoke nhưng gateway chỉ check `exp`

Gateway đưa opaque token vào cache với metadata `active=true` và `exp` 30 phút, không có TTL ngắn. Khi user revoke sau 1 phút, API tiếp tục allow trong 29 phút.

**Sửa:** đặt cache TTL theo revocation objective, event invalidation/short-lived tokens hoặc introspection per request cho endpoint nhạy cảm. `exp` không thay grant state.

### Tình huống C — JWT bị thu hồi nhưng RS không có denylist

JWT đã ký, còn 15 phút. AS có denylist nhưng RS chỉ validate offline. **Không có cách tự nhiên để RS biết thay đổi đó**. Cần thêm introspection/denylist check/event feed/TTL ngắn. Không cần sửa chữ ký JWT; cần sửa enforcement architecture.

### Tình huống D — Introspection HTTP 200, API vẫn nên từ chối

AS trả:

```json
{
  "active": false
}
```

Một custom client chỉ kiểm HTTP status == 200 rồi cho phép. **Đây là lỗi nghiêm trọng:** `active` boolean là điều kiện bắt buộc, không thể bỏ. Cần test âm tính và dùng framework introspector đã được kiểm thử.

### Tình huống E — Token active nhưng sai audience

`profile-api` có token active `aud=profile-api`. Attacker gửi tới `payments-api` cùng issuer. Nếu RS payments chỉ kiểm `active=true` và scope tên trùng, token bị sử dụng chéo. **Cần audience/client/resource binding**.

### Tình huống F — AS introspection outage

AS mất kết nối DB. RS không xác minh được trạng thái revoke. Nếu code catch exception rồi allow vì “đang ở mạng nội bộ”, một sự cố availability biến thành security bypass. **Fail closed** hoặc fallback đã đánh giá rõ rủi ro và giới hạn staleness.

### Tình huống G — Refresh token còn active sau revoke consent

Người dùng thu hồi consent, UI báo thành công, nhưng client vẫn dùng refresh token xin access token mới. Vấn đề là **AS grant/token family state** và issuance gate, không chỉ introspection RS. Cần revoke/đánh giá refresh grant và test refresh flow.

### Tình huống H — Two-region inconsistency

AS region A trả inactive, region B trả active cho cùng token sau revoke. Có thể do replica lag, cache hoặc thiếu shared versioning. **Sửa consistency/invalidation**, test monotonic state và đo time-to-deny ở tất cả region.

### Tình huống I — RS introspection credential bị lộ

Một CI job log `orders-api-introspector` Basic credential. Attacker có thể gọi introspection để dò metadata hoặc gây tải lên AS tùy policy. Cần rotate/disable introspection credential, đánh giá endpoint access logs và giới hạn allowed audience/clients. **Không chờ access token expiry để xử lý RS credential leak.**

## 21. Ứng phó sự cố token theft và revocation delay

### 21.1. Phân biệt leak access token và leak client secret

- **Leak bearer access token:** attacker có thể replay token còn active đến RS phù hợp audience/scope; revoke token/đổi grant/denylist/TTL tùy architecture.
- **Leak refresh token:** attacker có thể xin access token mới; revoke refresh family, kiểm reuse/rotation, đánh giá access tokens đã phát.
- **Leak OAuth client secret/private key:** attacker có thể xin token mới hoặc gọi introspection/revocation tùy client privileges; rotate/disable credential nguồn.
- **Leak introspection credential của RS:** attacker có thể lạm dụng truy vấn metadata; rotate và hạn chế quyền endpoint.

Không dùng một thao tác “logout user” như cách khắc phục đầy đủ cho mọi loại leak.

### 21.2. Quy trình kiểm soát

1. **Ngăn nguồn lộ:** tắt header/body dumps, revoke quyền đọc log không cần thiết, cô lập crash reports/APM.
2. **Khoanh phạm vi:** issuer, token type, audience, scope, grant/client, thời điểm và RS nhận token.
3. **Revoke đúng lớp:** access token, refresh token family, grant/consent hoặc client credentials theo threat model.
4. **Xác minh AS state:** introspection trả inactive trên các paths/regions cần thiết.
5. **Xác minh RS enforcement:** API requests dùng fixture tương ứng bị deny; đo cache/replication lag.
6. **Rà soát business impact:** calls trái phép, tenant/resource access, writes đã hoàn tất trước revoke.
7. **Kiểm tra logs/backup:** xử lý credential copies theo retention/forensic policy, không paste token vào ticket.
8. **Cải thiện phòng ngừa:** TTL, sender constraint, scope/audience minimization, monitor, integration tests.

### 21.3. “Revoked” nhưng token vẫn được chấp nhận

Một incident report hữu ích cần tách:

```text
revocation_requested_at:
revocation_committed_at:
first_introspection_inactive_at:
last_observed_rs_allow_at:
first_observed_rs_deny_at:
cache_ttl_and_replication_context:
token_audience_and_scope:
affected_resources:
corrective_action:
```

Đây là **các trường điều tra**, không được điền raw access token vào báo cáo. Nếu không có dữ liệu đo, phải ghi rõ **unknown** thay vì invent latency.

## 22. Bài thực hành

### Bài A — Diễn giải trạng thái

Ba token:

```text
Token A: exp còn 10 phút, bị revoke 2 phút trước.
Token B: không có sự kiện revoke, exp đã qua 1 phút.
Token C: active ở AS, aud=profile-api, caller đang gọi orders-api.
```

Hãy xác định phản hồi introspection/RS phù hợp, và nêu tại sao `active=false` không thể tự tiết lộ A hay B thuộc loại nào.

### Bài B — Dùng đúng RFC

Cho hai endpoint:

```text
POST /revoke
POST /introspect
```

Hãy giải thích **ai gọi, input, output và mục đích**. Vì sao `/revoke` trả HTTP 200 không chứng minh một token đang active trước đó? Vì sao `/introspect` trả HTTP 200 không chứng minh token active?

### Bài C — Đo revocation propagation

Hệ thống có:

```text
AS replica lag: up to 3 s
RS positive cache TTL: 45 s
Token exp: in 10 min
```

Thảo luận *stale-allow window* có thể xuất hiện. Nếu SLA revoke là 5 giây, cần thay đổi gì ở AS replication, cache TTL, invalidation và RS behavior? **Không khẳng định chính xác worst-case nếu chưa biết tương tác giữa các lớp cache, clock và network.**

### Bài D — Viết policy RS

Introspection trả:

```json
{
  "active": true,
  "iss": "https://id.example.test",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "client_id": "shop-web",
  "sub": "user-42"
}
```

Request:

```text
POST /v1/orders/99/cancel
Order 99 belongs to tenant-B
User 42 belongs only tenant-A
```

Hãy viết điều kiện kiểm method/action scope, tenant membership và resource ownership khiến RS deny dù token active.

### Bài E — Sửa mã Java sai

```java
// SAI: response 200 không chứng minh active=true.
if (introspectionResponse.statusCode() == 200) {
    return true;
}
```

Hãy mô tả parser/validation đúng: HTTP 200 + JSON object + Boolean `active=true` + issuer/aud/type/scope/expiry/policy; error hoặc inactive thì fail closed.

### Bài F — JWT bị revoke

Một JWT access token `aud=orders-api` còn 20 phút. AS gắn grant `REVOKED` nhưng RS chỉ dùng JWKS và `exp` để validate. Hãy vẽ sơ đồ lý do RS vẫn allow và ba chiến lược để giảm độ trễ: introspection/denylist check, event invalidation/grant version, hoặc short TTL.

### Bài G — Refresh token family

Client dùng refresh token `R1` để lấy `A1`; sau rotation, attacker reuse `R1`. AS quyết định revoke family. Hãy xác định token/grant nào cần invalidate theo AS policy và viết test:

1. Refresh token cũ không thể xin token mới.
2. Refresh token hiện tại thuộc family bị revoke theo policy.
3. Access token liên quan chuyển inactive qua introspection nếu AS đã đặt mục tiêu đó.
4. RS deny theo chính sách revocation propagation.

### Bài H — Outage và fail closed

AS introspection timeout 5 giây. App có code:

```text
try introspect
catch timeout -> allow if request from private subnet
```

Giải thích rủi ro. Thiết kế timeout/retry/circuit breaker/HTTP 503 và alert mà không cấp quyền khi không có trạng thái active đáng tin.

### Bài I — Introspection là oracle

Một endpoint công khai cho mọi người gửi `token` rồi trả `sub`, `scope` và `active`. Hãy mô tả token scanning, metadata privacy, rate limiting, authenticated RS identities, audience restrictions và response `active=false` tối thiểu.

### Bài J — Cache key isolation

Hai RS `orders-api` và `payments-api` dùng chung Redis cache kết quả introspection; key chỉ là token string. Hãy xác định vấn đề cross-audience response reuse, raw token trong cache key/diagnostics, nguy cơ TTL stale và thiết kế cache key/context bảo vệ.

### Bài K — Consent revoke và logout

User chọn “Disconnect app” nhưng vẫn đăng nhập OP và RP. Access JWT còn hạn 8 phút. Hãy phân biệt **revoke grant**, **revoke refresh family**, **access JWT deny**, **logout RP**, **logout OP**, và nêu điều gì cần introspection để phản ánh revoke kịp thời.

## 23. Checklist triển khai production

- [ ] Hiểu **RFC 7009 revoke** khác **RFC 7662 introspection**; API revoke HTTP 200 không tự chứng minh token inactive tại mọi RS.
- [ ] AS có authoritative token/grant state và liên kết đúng client, subject/service, resource/audience, scopes, expiry, revocation.
- [ ] Introspection của token đã revoke trả **`active=false`** trong ngữ cảnh RS theo policy.
- [ ] Introspection inactive response không tiết lộ subject/scope/expiry không cần thiết.
- [ ] RS gọi endpoint **POST form-urlencoded**, có `token` và `token_type_hint` tùy chọn, qua HTTPS.
- [ ] Introspection endpoint có **caller authentication/authorization**, rate limit và privacy controls.
- [ ] RS không cho caller tự chọn introspection URL/issuer; trust config cố định/allowlist.
- [ ] RS chỉ chấp nhận `active` là Boolean true chính xác; 200/JSON thiếu `active` không đủ.
- [ ] HTTP 401/403/5xx/timeout/JSON lỗi introspection không tạo authenticated principal; **fail closed** theo policy.
- [ ] RS kiểm token type, issuer, audience, expiry/not-before, scope, client/subject/tenant và resource policy.
- [ ] RS từ chối ID token, refresh token và client assertion khi endpoint đòi access token.
- [ ] RS có policy khi introspection response thiếu `aud`/`iss`; không bỏ kiểm bảo mật mà không có hợp đồng AS tương đương.
- [ ] Access token JWT offline có cơ chế revocation-aware nếu cần revoke trước expiry; không coi chữ ký hợp lệ là trạng thái grant mới nhất.
- [ ] Positive introspection cache TTL và invalidation phù hợp security objective, không vượt token expiry.
- [ ] Cache key cô lập issuer, audience/RS, token type/policy; không ghi raw token trong cache dumps/log.
- [ ] Negative caching, rate limits và circuit breaker không mở bypass hay làm AS/RS mất khả dụng vì token scanning.
- [ ] Multi-instance/region dùng consistency/versioning/replication phù hợp; không hồi sinh token terminally revoked.
- [ ] Test revoke token vs revoke refresh/parent grant, token family và client disable theo semantics đã công bố.
- [ ] Có đo **revocation commit → first introspection inactive → RS deny** trên các paths/regions cần thiết.
- [ ] API rủi ro cao xem xét re-check tại business commit nếu muốn ngăn request đã qua auth trước thời điểm revoke.
- [ ] mTLS/DPoP-bound token được RS kiểm sender proof, không chỉ introspection `cnf`.
- [ ] Introspection credentials nằm trong secret manager/PKI, có least privilege/rotation và không đi qua redirect.
- [ ] Không log raw token, Basic header, client secret, UserInfo/PII vượt nhu cầu, form body, client assertion.
- [ ] Có integration tests cho `active=false`, wrong aud/scope/issuer/type, outage, stale cache, revocation cascade, multi-region và concurrency.
- [ ] Có incident plan phân biệt access token theft, refresh theft, client credential theft và introspection credential theft.

## 24. Câu hỏi tự kiểm tra

**1. Revocation và introspection khác nhau thế nào?** Revocation thay trạng thái quyền sử dụng token/grant; introspection hỏi trạng thái và metadata đó.

**2. RFC nào định nghĩa token revocation endpoint?** RFC 7009.

**3. RFC nào định nghĩa introspection endpoint?** RFC 7662.

**4. Introspection request phải có trường nào?** `token`; `token_type_hint` là tùy chọn.

**5. Introspection request dùng HTTP method/encoding gì?** POST, `application/x-www-form-urlencoded`, qua TLS.

**6. AS trả `{"active":false}` có phải token chắc chắn bị user revoke không?** Không; có thể expired, unknown, sai ngữ cảnh hoặc không tiết lộ status cho caller.

**7. AS trả HTTP 200 có đồng nghĩa token active?** Không. HTTP 200 cùng `active=false` vẫn là response hợp lệ.

**8. RS nhận HTTP 401 từ introspection có được cho token đi qua không?** Không. Đây là lỗi introspection caller authentication/authorization hoặc service integration; fail closed.

**9. `active=true` có cho phép mọi API không?** Không. RS còn kiểm audience, scope, type, issuer, tenant và resource policy.

**10. Vì sao JWT signed vẫn dùng được sau revoke nếu RS offline?** Signature/expiry không phản ánh grant status mới nếu không có revocation-aware mechanism.

**11. Opaque token có tự bảo đảm revoke ngay tức thì không?** Không nếu RS cache active result hoặc AS replica chậm.

**12. `token_type_hint=access_token` có biến refresh token thành access token không?** Không. Đây chỉ là hint cho AS, RS vẫn xác minh token type.

**13. Revoke refresh token có luôn revoke access token liên quan ở mọi provider không?** Không thể giả định; kiểm RFC/provider semantics và implementation.

**14. Có nên cache introspection response trong 1 giờ nếu token còn sống 1 giờ?** Chỉ nếu security objective chấp nhận độ trễ revoke đó; thường quá dài cho quyền nhạy cảm.

**15. `active=false` có được log raw bearer token để debug không?** Không. Token vẫn là dữ liệu credential nhạy cảm.

**16. Một token `aud=profile-api` được introspect active, có dùng ở orders API không?** Không; wrong audience.

**17. Nếu token active, `scope=orders:read`, có thể xóa order không?** Không, cần scope/quyền write/delete và resource policy tương ứng.

**18. Revocation API trả 200 thì có chắc mọi RS đã deny không?** Không. Còn introspection, caches, replicas và offline JWT validation.

**19. Tại sao introspection endpoint phải xác thực RS?** Vì có thể tiết lộ trạng thái và claims nhạy cảm, tạo token enumeration oracle nếu công khai.

**20. RS có được introspect ở URI đọc từ JWT `iss` chưa verify không?** Không. Có nguy cơ SSRF/token exfiltration và issuer confusion.

**21. AS timeout, RS nên làm gì?** Không tự cho phép; fail closed hoặc fallback được bảo mật đánh giá rõ, theo service contract.

**22. User logout RP có tự revoke access token không?** Không nhất thiết. Session và token/grant revoke là những vòng đời khác nhau.

**23. Lộ client secret khác lộ access token điểm nào?** Client credential có thể cho attacker xin token mới; access token thường chỉ có phạm vi/thời hạn đã cấp.

**24. Test revoke cần chứng minh điều gì cuối cùng?** Token/grant bị vô hiệu ở AS, introspection phản ánh inactive và RS từ chối API requests theo freshness objective.

## 25. Tài liệu tiêu chuẩn tham khảo

- **RFC 7662 — OAuth 2.0 Token Introspection:** POST request, `active` semantics, optional response members, caller authorization và protected metadata.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint, token hint, client authentication và quan hệ revoke access/refresh token.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** OAuth clients/grants, token endpoint, client authentication và scopes.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer token transport, `invalid_token`/`insufficient_scope` và bảo vệ token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** issuer, audience, expiry, client ID, scope và resource-server JWT validation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay, refresh token rotation, sender constraints và các best practices.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** audience/resource indicators và token separation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client auth và certificate-bound access tokens.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession, `cnf` và token replay protection.
- **RFC 8693 — OAuth 2.0 Token Exchange:** token types, subject/actor và delegation theo policy khi áp dụng.
- **OpenID Connect Core 1.0:** ID token, UserInfo và vòng đời OIDC authentication; phân biệt với access token introspection.
- **OWASP OAuth 2.0 Security Cheat Sheet:** least privilege, token handling, redirects, client authentication và bảo vệ bearer tokens.
- **Spring Security OAuth2 Resource Server documentation:** opaque token introspection, `OpaqueTokenIntrospector`, authority mapping và authorization rules.
- **Spring Authorization Server documentation:** token grant storage, token revocation/introspection endpoints và các extension points.

**Kết luận:** **Token revocation chỉ có ý nghĩa thực thi khi resource server ngừng chấp nhận token đã bị vô hiệu.** RFC 7009 cung cấp cách yêu cầu revoke; RFC 7662 cho RS hỏi AS về trạng thái token qua `active`. Với **opaque token**, introspection thường là đường kiểm tra chính; với **JWT self-contained**, cần bổ sung revocation-aware checks nếu muốn chặn trước `exp`. Trong mọi trường hợp, **`active=false` phải dẫn tới deny**, còn **`active=true` vẫn phải qua kiểm token type, issuer, audience, scope, tenant và resource policy**. Caching, replication, outage và đường JWT offline quyết định độ trễ revoke thực tế; hãy **đo từ revoke commit đến RS deny**, bảo vệ introspection endpoint/credentials và thiết kế fail closed để token bị đánh cắp hoặc phát lại không tiếp tục có quyền ngoài giới hạn đã công bố.
