# Self-contained token và giới hạn thu hồi tức thời

Một **self-contained access token** chứa đủ dữ liệu để Resource Server (RS) có thể tự kiểm tra chữ ký, issuer, audience, thời hạn và các quyền biểu diễn trong token mà **không phải hỏi Authorization Server (AS) ở mỗi request**. Trong OAuth 2.0, dạng phổ biến là **JWT access token được ký bằng JWS**. Cách này nhanh, dễ mở rộng và không tạo điểm nghẽn introspection ở mỗi API call. Tuy nhiên, chính ưu điểm **xác minh ngoại tuyến** cũng tạo ra giới hạn quan trọng: **RS có thể tiếp tục chấp nhận JWT đã phát hành dù tài khoản, phiên, grant hoặc token vừa bị thu hồi ở AS**.

Ví dụ, một nhân viên truy cập Orders API bằng JWT có `exp` còn 12 phút. Quản trị viên tắt tài khoản hoặc thu hồi quyền kết nối ở thời điểm hiện tại. Nếu Orders API chỉ kiểm tra **JWS signature, `iss`, `aud`, `exp` và `scope`**, token cũ vẫn có thể vượt qua các phép kiểm tra ấy cho tới khi hết hạn. **Xóa token khỏi trình duyệt hoặc revoke refresh token ở AS không khiến bản sao JWT đang nằm trên thiết bị khác tự biến mất**.

Bài **“Self-contained token và giới hạn thu hồi tức thời”** thuộc chương **Revocation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ mô hình tin cậy, vòng đời JWT/opaque access token và refresh token, OAuth 2.0/OIDC, issuer, claims, scope, audience, lưu trữ, revocation, token theft và replay. Tập trung đặc biệt vào câu hỏi: **“Khi nào thu hồi thực sự có hiệu lực ở tất cả Resource Servers, và chúng ta có thể chứng minh điều đó bằng kiến trúc nào?”**

> **Nguyên tắc quan trọng:** **Một JWT ký hợp lệ không đồng nghĩa grant vẫn còn hiệu lực.** Nếu Resource Server không kiểm tra trạng thái thu hồi mới hơn thông tin có trong token, nó **không thể biết** rằng AS vừa thu hồi token. “Thu hồi tức thì” đòi hỏi **kiểm tra trạng thái trực tuyến hoặc cơ chế phân phối trạng thái đủ mạnh với giới hạn trễ được chứng minh**, không chỉ gọi revocation endpoint.

## 1. Self-contained token là gì?

**Self-contained token** là credential chứa thông tin cần để bên nhận xác minh tính hợp lệ theo một tập tiêu chí mà không cần tra cứu một bản ghi token trung tâm cho từng request. Với **signed JWT access token**, các thông tin thường nằm trong payload claims và được bảo vệ tính toàn vẹn bởi JWS signature:

~~~text
BASE64URL(protected_header)
.
BASE64URL(payload_claims)
.
BASE64URL(signature)
~~~

Một JWT access token minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "client_id": "reports-web",
  "scope": "orders.read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900,
  "jti": "random-access-token-id"
}
~~~

**Đây là payload minh họa, không phải một JWT có chữ ký thực.** Các trường được yêu cầu phụ thuộc token profile; chẳng hạn **RFC 9068** định nghĩa profile riêng cho JWT OAuth access token. Trong hệ thống đa tenant có thể có custom claim `tenant_id`, nhưng đó **không phải claim chuẩn bắt buộc** của mọi issuer.

Resource Server thường kiểm tra:

- **`iss`** có phải issuer đã tin cậy hay không;
- **JWS signature** bằng public key/JWKS của issuer, với **algorithm allowlist** phù hợp;
- **`aud`** đúng API/resource đang nhận token;
- **`exp`, `nbf`, `iat`** và chính sách clock skew;
- Token type/profile và **`scope`** được cấp;
- Principal type (user-delegated hay app-only), tenant và quyền trên tài nguyên;
- **`cnf`/DPoP/mTLS binding** khi token sender-constrained.

**Dù tất cả các kiểm tra trên đúng, không có nghĩa AS chưa thu hồi grant sau thời điểm `iat`.**

### 1.1. Phân biệt self-contained và reference/opaque token

| Đặc điểm | Signed JWT self-contained | Opaque/reference token |
| --- | --- | --- |
| Dạng token | Có cấu trúc JWT, chứa claims được ký | Chuỗi không có claims mà RS phải tự hiểu |
| Xác minh thông thường | Chữ ký/issuer/audience/time tại RS | Introspection (RFC 7662) hoặc trusted lookup |
| Độ phụ thuộc AS ở mỗi request | Không bắt buộc | Thường cần trạng thái/metadata AS, trừ khi có cache |
| Khả năng phát hiện revoke ngay | **Không tự có** khi chỉ verify JWT offline | Phụ thuộc lookup thời gian thực và caching |
| Chi phí API | Thấp, phân tán | HTTP/DB lookup thêm và khả năng AS bottleneck |
| Thông tin nhúng | Claims có thể bị đọc nếu chỉ JWS, không mã hóa | Nội dung thường không lộ chỉ từ chuỗi |
| Rủi ro nếu Bearer bị sao chép | Replay cho đến hạn hoặc khi RS biết revoke | Replay nếu token vẫn active và RS không sender-constrained |

**Không nên đồng nhất “JWT” với “không thu hồi được”.** Một AS vẫn có thể phát JWT và RS vẫn có thể dùng denylist, introspection hoặc online policy check. Ngược lại, **opaque token cũng có thể bị chấp nhận sau revoke** nếu introspection cache giữ `active=true` quá lâu.

### 1.2. Self-contained không đồng nghĩa token mã hóa

JWS JWT thông thường **được ký, không được mã hóa**: ai có chuỗi token có thể giải mã phần payload Base64url và xem claims. Không nhúng dữ liệu nhạy cảm không cần thiết vào token (password, private key, full medical record). Nếu cần bảo mật nội dung có thể cân nhắc JWE/profile phù hợp, nhưng **JWE cũng không tự giải quyết revocation**.

### 1.3. OIDC ID token khác OAuth access token

**ID token** dành cho OIDC client xác minh kết quả đăng nhập và thường có `aud=client_id`. **Access token** dành cho Resource Server và được kiểm tra theo audience/scope của API. Một ID token có chữ ký hợp lệ **không được dùng thay access token tại Orders API**, bất kể nó là self-contained JWT.

## 2. Thu hồi những gì? Token, grant, phiên và quyền người dùng

“Đăng xuất” hoặc “Thu hồi quyền” là những hành động nghiệp vụ, nhưng hệ thống có thể cần vô hiệu **nhiều đối tượng khác nhau**:

| Đối tượng | Ý nghĩa | Hệ quả khi thu hồi |
| --- | --- | --- |
| **Một access token cụ thể** | Credential gọi API đang còn hạn | Bản sao token đó phải không còn được RS chấp nhận theo policy |
| **Refresh token** | Credential xin access token mới | Client không dùng refresh token đó để nhận token mới |
| **Refresh-token family** | Nhóm token trong rotation chain | Các bản sao/đường kế thừa được vô hiệu theo policy |
| **OAuth authorization grant/consent** | Quyền client đã được cho phép | AS không tiếp tục cấp quyền dựa trên grant đã revoke |
| **AS login/session cookie** | Session xác thực user tại AS/OP | Trình duyệt mất phiên đăng nhập, **không tự xóa JWT ở mọi RS** |
| **User account** | Danh tính và trạng thái đăng nhập | Cần policy ngăn truy cập; offline JWT có thể chưa biết trạng thái mới |
| **Role/tenant membership** | Quyền nghiệp vụ hiện tại | RS phải xét quyền mới hoặc chấp nhận độ trễ đã quy định |
| **Client credential/signing key** | Danh tính ứng dụng hoặc khóa ký token | Có thể ngăn issuance mới; token đã phát có cơ chế kiểm tra khác |

**Không thể suy một hiệu ứng thu hồi duy nhất từ tên thao tác UI.** Ví dụ “Logout khỏi hệ thống” có thể chỉ xóa cookie của BFF, hoặc còn yêu cầu AS revoke refresh token và RS denylist access token. Phải định nghĩa **hợp đồng hậu quả** và SLA cho từng hành động.

### 2.1. Thu hồi access token khác từ chối cấp token mới

Ví dụ:

~~~text
10:00  AS cấp access token A (exp=10:15)
10:05  Admin revoke refresh token R
10:06  Client không dùng R để xin access token mới
10:07  Kẻ giữ bản sao A vẫn gọi RS đang verify JWT offline
10:15  A tự hết hạn theo exp
~~~

**Revoke refresh token R cắt đường xin token mới; không nhất thiết vô hiệu JWT A đã phát**. Một AS có thể chủ động revoke các access tokens liên quan, nhưng RS phải **nhận và áp dụng** trạng thái đó. Cần phân biệt hành động ở AS với hiệu quả enforcement tại RS.

### 2.2. Thu hồi quyền tài nguyên có thể độc lập token

Giả sử user vẫn có token `orders.read` nhưng đã bị rút khỏi tenant Acme. Nếu Orders API mỗi request kiểm tra membership mới nhất trong nguồn đáng tin, nó có thể từ chối đọc đơn hàng Acme **dù JWT còn hạn**. Ngược lại, nếu API chỉ tin claim `tenant_id=acme` trong JWT cũ, quyền có thể tồn tại đến khi token hết hạn hoặc RS nhận tín hiệu revoke.

**Object-level authorization là một lớp riêng**: scope hợp lệ không tự cấp quyền đọc bản ghi bất kỳ.

## 3. Vì sao JWT self-contained không thể tự biết vừa bị revoke?

Giả sử tại thời điểm `t0`, hai trạng thái hệ thống:

- **Thế giới A:** JWT còn hạn, chữ ký hợp lệ, grant vẫn active.
- **Thế giới B:** cùng JWT đó, cùng public key, cùng thời gian, nhưng AS vừa revoke grant.

Nếu RS chỉ đọc **chuỗi JWT và cấu hình cục bộ không thay đổi**, đầu vào kiểm tra ở A và B **giống hệt nhau**. Không có dữ liệu nào cho RS biết sự kiện revoke mới. Vì vậy, cùng thuật toán verification sẽ cho **cùng một kết quả** trong hai thế giới.

Đây là giới hạn **thông tin**, không phải bug riêng của thư viện Java, Spring Security, JWT hoặc thuật toán RS256.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hoặc attacker có JWT A
    participant AS as Authorization Server
    participant RS as Resource Server verify offline
    AS-->>C: JWT A, exp còn 15 phút
    C->>RS: Bearer A
    RS->>RS: Signature, iss, aud, exp, scope OK
    RS-->>C: 200
    Note over AS,RS: Admin revoke A/grant tại AS
    C->>RS: Bearer A lần nữa
    RS->>RS: Chỉ có A + key cũ + clock, không biết revoke
    RS-->>C: Có thể vẫn 200 tới khi A hết hạn
~~~

### 3.1. JWT `jti` không tự là revocation lookup

`jti` là JWT ID, hữu ích để phân biệt token và tra cứu trạng thái. Nhưng nếu RS chỉ kiểm tra `jti` **có mặt**, nó không biết `jti` nào đã bị revoke. Cần **denylist/allowlist hoặc online state check** tương ứng. `jti` cũng không mặc định là nonce chỉ dùng một lần cho access token; **một JWT Bearer access token hợp lệ thường được sử dụng nhiều requests**.

### 3.2. JWT signature không phản ánh trạng thái user sống

Chữ ký chứng minh issuer ký payload tại thời điểm issuance và payload chưa bị sửa. Nó **không** xác nhận:

- User vẫn còn active ngay hiện tại;
- Mọi role/tenant membership còn nguyên;
- Client vẫn được quản trị viên chấp thuận;
- Refresh token chưa bị revoke;
- Session vẫn đăng nhập;
- Token chưa bị đánh cắp hoặc nằm trong denylist mới.

Muốn kiểm tra các điều kiện động, **RS cần thông tin mới hơn JWT**, ví dụ online lookup, event-driven state hoặc hạn token đủ ngắn phù hợp yêu cầu.

## 4. Thời hạn JWT và cửa sổ không thể thu hồi tức thời

Giả sử token được cấp lúc `t_issued`, có `exp=t_issued+L` với `L` là access-token lifetime. Nếu AS ngừng cấp quyền tại `t_revoke` nhưng RS **chỉ xác minh offline**, token đã phát có thể tiếp tục được RS chấp nhận cho đến `exp`, cộng sai số clock skew nếu cấu hình leeway cho `exp`.

**Cửa sổ phơi nhiễm còn lại của một token cụ thể:**

\[
W_{\mathrm{offline}} \lesssim
\max(0,\; \mathrm{exp}-t_{\mathrm{revoke}})+\Delta_{\mathrm{clock}}
\]

Trong đó \(\Delta_{\mathrm{clock}}\) là leeway/clock behavior tại RS. Đây là **ước lượng bảo thủ** cho một RS vẫn tuân expiry mỗi lần kiểm tra; các session/cache xác thực tự thiết kế có thể tạo rủi ro khác nếu giữ quyền vượt `exp`.

### 4.1. Minh họa theo thời gian

~~~text
09:00:00  AS phát JWT A, exp=09:15:00
09:07:00  Admin disable tài khoản và revoke grant
09:07:01  Refresh token bị vô hiệu ở AS
09:07:02  RS offline chưa có revocation state
09:12:00  Kẻ giữ A vẫn có thể gọi API nếu token hợp lệ ở RS
09:15:00  Token hết hạn (cộng leeway đã cấu hình)
~~~

**Không được tuyên bố “đã revoke tức thì” chỉ vì bước 09:07:00 hoàn thành ở AS.** Tuyên bố chính xác hơn là “AS đã ngừng chấp nhận refresh/grant mới; access token đã cấp sẽ hết hạn hoặc bị RS chặn theo cơ chế revocation cụ thể”.

### 4.2. Token ngắn hạn giảm cửa sổ nhưng không xóa nó

| Access-token lifetime | Cửa sổ còn lại tối đa khi vừa phát token | Đổi lại |
| --- | --- | --- |
| 60 giây | Khoảng 1 phút (+ leeway) | Tải cấp token/refresh tăng, khả năng lỗi khi AS outage |
| 5 phút | Khoảng 5 phút (+ leeway) | Cân bằng hơn cho API thông thường |
| 15 phút | Khoảng 15 phút (+ leeway) | Ít refresh hơn, lâu hơn để ngăn token bị sao chép |
| 1 giờ | Khoảng 1 giờ (+ leeway) | Khó đáp ứng yêu cầu revoke khẩn |

Các mốc là **ví dụ lựa chọn kiến trúc, không phải chuẩn bắt buộc**. Cần xét threat model, AS capacity, rate limits, client retry/backoff, token storage, network availability và nghiệp vụ.

### 4.3. `exp`, `nbf` và clock skew

RS phải từ chối token sau khi hết hạn theo policy; chấp nhận một leeway nhỏ để xử lý lệch đồng hồ giữa AS/RS có thể phù hợp, nhưng **leeway quá lớn kéo dài cửa sổ tấn công**. Đồng bộ NTP/clock monitoring là một biện pháp bảo mật vận hành, không chỉ tối ưu logging.

**`iat` là thời điểm phát**, không phải “còn hiệu lực cho tới khi người dùng logout”. Nếu RS đặt `maxAge` dựa trên `iat`, chính sách đó cần nhất quán với `exp` và các refresh workflows.

## 5. Revocation API theo RFC 7009 và phạm vi tác động

**RFC 7009 — OAuth 2.0 Token Revocation** định nghĩa một revocation endpoint để OAuth client yêu cầu AS vô hiệu token phù hợp với quyền của mình.

Ví dụ request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic <registered-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<refresh-token>&token_type_hint=refresh_token
~~~

Body chỉ để minh họa; thực tế form cần URL-encode đúng. **`token_type_hint` là hint, không phải bằng chứng token thuộc loại đó**. AS cần xác thực confidential client theo policy và kiểm tra token thuộc/được client phép revoke đúng scope của endpoint.

### 5.1. RFC 7009 yêu cầu hỗ trợ loại token nào?

Theo RFC 7009, AS **MUST** hỗ trợ revocation của **refresh tokens**, và **SHOULD** hỗ trợ revocation của **access tokens**. Việc có endpoint không có nghĩa mọi JWT đã phát sẽ bị RS offline nhận ra sự kiện revoke ngay.

Nếu revoke refresh token, AS có thể ảnh hưởng các access tokens hoặc grant liên quan theo triển khai/chuẩn và policy. **Không tự suy rằng toàn bộ session/JWT trên mọi API đã được vô hiệu ngay**; phải xác định chính xác hệ quả issuer đã hỗ trợ.

### 5.2. Vì sao revocation endpoint thường trả 200 cho token không hợp lệ?

Với token đã bị revoke hoặc token mà client gửi không hợp lệ, endpoint thường trả **HTTP 200** để **không tiết lộ trạng thái token** cho kẻ cố đoán chuỗi credential. HTTP 200 của revocation request **không chứng minh mọi resource server đã nhận thông tin thu hồi**.

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Một số lỗi như client authentication sai hoặc token type không được hỗ trợ có response/error behavior khác theo RFC. **Không xây cơ chế audit “200 nghĩa là token chắc chắn tồn tại và đã bị xóa khỏi mọi RS”.**

### 5.3. Revocation endpoint khác introspection endpoint

| Endpoint | Câu hỏi | Ai thường gọi? | Hạn chế |
| --- | --- | --- | --- |
| **Revocation, RFC 7009** | “AS hãy vô hiệu token/grant theo quyền tôi có” | OAuth client có quyền revoke | Không tự bảo đảm RS đã cập nhật |
| **Introspection, RFC 7662** | “Token này có active và metadata gì trong ngữ cảnh của RS?” | Resource server với caller authentication riêng | Có thể bị cache/stale, AS availability |
| **Authorization/Token endpoint** | “Có cấp mới token không?” | Client/user theo grant | Không nói token cũ đã hết hiệu lực ở RS |
| **JWKS endpoint** | “Key nào dùng verify signature?” | RS verifier | Key rotation không đồng nghĩa revoke một token cụ thể |

### 5.4. Logout không mặc định thay token revocation

Xóa cookie session tại frontend/BFF hay OIDC logout khỏi OP có thể chấm dứt khả năng tương tác mới. Tuy nhiên JWT Bearer đã sao chép vẫn có thể dùng tiếp tới `exp` nếu RS chỉ verify offline. Nếu yêu cầu **logout-all-devices**, cần rõ ràng phạm vi phiên/grant/refresh family và cách RS ngăn access tokens đã phát.

## 6. Đánh giá yêu cầu “thu hồi ngay” theo mô hình bảo đảm

Trước khi chọn công nghệ, cần định nghĩa “ngay” nghĩa là:

| Mức bảo đảm | Cách diễn đạt kiểm chứng được | Kiến trúc gợi ý |
| --- | --- | --- |
| **Ngừng cấp mới tại AS** | Từ thời điểm revoke, refresh/grant mới bị từ chối | Revoke refresh token/grant tại AS |
| **Bounded window** | Access token cũ bị chặn sau không quá `L` (+ leeway) | JWT TTL ngắn, RS luôn kiểm `exp` |
| **Near-real-time** | RS nhận event trong vài giây khi mạng hoạt động | Denylist/version propagation, có metric lag |
| **Bounded stale state** | Mỗi RS tối đa `D` giây trạng thái cũ | Online lookup/caching TTL `D`, failure policy |
| **Strong per-request current state** | Mỗi API request kiểm tra state mới theo consistency contract | Online introspection/central policy lookup, fail closed |
| **No acceptance during partition** | RS không chấp nhận token khi không xác minh được state cần thiết | Fail closed, chấp nhận trade-off availability |

**“Tức thời tuyệt đối” trong mạng phân tán là tuyên bố rất mạnh.** Nếu một RS bị mất mạng ngay trước khi revoke, nó không thể vừa duy trì hoạt động offline với token cũ vừa biết sự kiện chưa nhận được. Với yêu cầu không chấp nhận token cũ khi partition, RS phải **dừng chấp nhận hoặc yêu cầu một online authority** trong thời gian không thể kiểm tra.

### 6.1. Đặt SLA với ngữ cảnh rủi ro

Ví dụ các lớp API:

~~~text
Public catalog:
  chấp nhận access-token TTL 5–15 phút nếu risk thấp.

Đọc đơn hàng riêng tư:
  TTL ngắn, policy tenant check thường xuyên,
  có thể denylist với revoke khẩn.

Hoàn tiền/đổi email bảo mật:
  yêu cầu online state check, step-up/re-auth
  và fail closed khi không xác minh được.
~~~

Đây là **các kịch bản gợi ý**, không phải thời gian chuẩn bắt buộc. Khi quy định yêu cầu “vô hiệu ngay”, phải viết thành kiểm thử được: **đường API nào, trong bao lâu, xử lý node mất kết nối ra sao**.

## 7. So sánh các chiến lược thu hồi JWT

| Chiến lược | Phát hiện revoke ở RS | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Chỉ `exp` ngắn** | Không kiểm revoke, hết hạn tự nhiên | Đơn giản, scale tốt | Không chặn token vừa bị trộm trong lifetime |
| **Denylist theo token ID** | RS kiểm denylist local/shared | Thu hồi chính xác từng token | Cần lưu state, đồng bộ, cache và outage policy |
| **Session/grant version hoặc `revoked_after`** | RS kiểm version/cutoff từ nguồn cập nhật | Thu hồi theo nhóm; quản lý logout-all | Cần lookup/event và claim/version đúng |
| **Introspection mỗi request** | RS hỏi AS hiện trạng | Quyết định cập nhật theo contract | Latency, AS availability/capacity, caller authentication |
| **Introspection có cache** | RS dùng metadata gần đây | Giảm tải online | Revocation lag bằng TTL hoặc lâu hơn nếu lỗi thiết kế |
| **Event-driven push/invalidation** | RS cập nhật state qua message bus | Nhanh, giảm lookup | Event loss/partition, eventual consistency, cần fallback |
| **Signing key withdrawal/rotation** | RS ngừng tin key | Có thể vô hiệu nhiều token | Quá rộng, JWKS cache/partition, không dùng cho một token |
| **Sender-constrained token (DPoP/mTLS)** | RS verify proof sender | Giảm replay nếu chỉ token bị sao chép | Không thay revoke; khóa/proof cùng bị lộ vẫn rủi ro |

**Không nhất thiết chọn đúng một chiến lược.** Ví dụ phổ biến là **JWT TTL ngắn + refresh token rotation + denylist khi incident + online check cho thao tác nhạy cảm**. Mỗi lớp có mục đích và độ trễ khác nhau.

## 8. Chiến lược 1: access token ngắn hạn và refresh token có kiểm soát

Đây là cách giảm tác động của việc **không có trạng thái revoke access token online**:

1. Access token có hạn đủ ngắn theo risk, audience và scope.
2. Refresh token được giữ trong nơi an toàn, không gửi đến RS.
3. Khi access token hết hạn, client dùng refresh token grant theo policy.
4. AS kiểm tra grant/session/account status khi refresh, từ chối nếu đã revoke.
5. Với public clients, áp **refresh token rotation hoặc sender constraint** theo yêu cầu security best practices.
6. Khi refresh token family bị đánh cắp/reuse, xử lý token family và reauthentication phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server offline JWT
    AS-->>C: Access token A (5 phút) + refresh R
    C->>RS: Bearer A
    RS-->>C: 200 khi JWT hợp lệ
    Note over AS: User revoke grant/refresh family
    C->>AS: refresh_token R
    AS-->>C: invalid_grant / revoke response
    C->>RS: Bearer A cũ còn hạn
    RS-->>C: Có thể vẫn 200 nếu không kiểm revoke
    Note over RS: Sau exp của A, RS từ chối
~~~

### 8.1. Vì sao không “refresh mỗi request”?

Refresh mỗi API request tăng tải AS/token endpoint, làm client giữ refresh token trong nhiều đường code và có thể tạo race/refresh-token reuse false positives. Nếu cần kiểm trạng thái mọi request, **dùng online authorization/introspection được thiết kế cho RS** thay vì ép OAuth client refresh vô hạn.

### 8.2. Refresh token rotation khác revoke JWT

Với rotation, AS phát refresh token mới và đánh dấu token cũ đã dùng. Nếu token cũ bị trình lại, AS có thể xem là **reuse signal** để thu hồi token family theo policy. Tuy nhiên, **access token JWT đã phát trước đó** vẫn cần `exp`/denylist/online check riêng. Không áp semantics “mỗi request dùng một token” cho access token Bearer.

### 8.3. Bảo vệ nơi lưu refresh token

Với BFF/backend, giữ refresh token server-side và browser chỉ nhận cookie session `Secure`, `HttpOnly`, `SameSite` phù hợp khi kiến trúc cho phép. Với native app, dùng secure OS storage/keystore. Public SPA có threat model XSS; không lưu refresh token dài hạn trong JavaScript-accessible storage chỉ vì dễ triển khai.

## 9. Chiến lược 2: denylist theo JWT ID hoặc token fingerprint

Để chặn **một JWT cụ thể trước `exp`**, AS hoặc security control plane có thể lưu trạng thái **“token ID này đã bị revoke”**. Resource Server phải kiểm tra danh sách ấy sau khi đã xác thực chữ ký/claims của token.

### 9.1. `jti` và khóa tra cứu

Một khóa logic có thể là:

~~~text
revocation_key =
  trusted_issuer
  + token_purpose
  + token_id_jti
~~~

**Không dùng `jti` như khóa toàn cục duy nhất** nếu nhiều issuers có thể tạo cùng ID. Nếu token không có `jti`, có thể dùng **HMAC fingerprint của raw token** với khóa riêng, tùy trust model và token length. Dù dùng cách nào, **RS phải verify signature/issuer/audience trước khi tin `jti` từ JWT**.

### 9.2. Không lưu raw Bearer token trong denylist

Thay vì:

~~~text
REVOKED_TOKEN = eyJhbGciOiJSUzI1NiIs...
~~~

Ưu tiên:

~~~text
fingerprint = HMAC_SHA256(K_revocation, token_identifier)

record:
  issuer_alias
  fingerprint
  revoked_at
  expires_at
  reason_category
~~~

`K_revocation` là **khóa HMAC riêng cho hệ thống revocation**, không phải JWT signing key, client secret hoặc refresh token. HMAC hữu ích khi identifier thấp entropy hoặc log/store có rủi ro lộ; cần quản lý key rotation và khả năng tra cứu trong cửa sổ chuyển đổi.

**Hash `jti` không tự làm token không thể phát lại.** RS cần kiểm tra denylist trên mỗi request hoặc theo SLA, và fail closed khi state bắt buộc không truy cập được.

### 9.3. Thời gian lưu denylist

Nếu JWT đã hết hạn, không cần giữ dấu revoke của token đó để ngăn nó được chấp nhận **nếu RS luôn kiểm `exp` đúng**. TTL bản ghi có thể dựa trên `exp`, cho thêm clock-skew margin và thời gian vận hành phù hợp.

~~~text
denylist_retention_until =
  token.exp + allowed_clock_leeway + controlled_safety_margin
~~~

**Không được xóa denylist quá sớm** khi một RS vẫn có leeway hoặc issuer key/cache khiến token có thể được xét còn hạn; **không giữ PII/token plaintext vô thời hạn** khi không cần.

### 9.4. Denylist còn là stateful validation

Thêm denylist khiến RS **không còn hoàn toàn offline về trạng thái revocation**. Nếu dùng Redis, database hay push-to-local-cache, phải giải quyết:

- Tính nhất quán và outage/failover của store;
- Event loss và propagation delay;
- Hiệu năng lookup;
- TTL và cache invalidation;
- Nhiều issuers/audiences/tenant;
- Ngăn stale negative result (đã kiểm “chưa revoke” trước sự kiện mới).

## 10. Chiến lược 3: token version, session version và `revoked_after`

Denylist theo từng `jti` phù hợp khi biết **token cụ thể nào** bị đánh cắp. Nhưng một tổ chức muốn “logout tất cả thiết bị”, thu hồi **mọi token của một phiên** hoặc vô hiệu **mọi token của một grant** có thể cần cách tiếp cận theo **nhóm**.

### 10.1. Version ở cấp user/session/grant

Authorization Server giữ trạng thái:

~~~text
principal=user-42
tenant=acme
current_session_version=7

JWT đã phát:
  sub=user-42
  tenant_id=acme
  session_version=6
~~~

Khi revoke session, AS tăng `current_session_version` từ 6 lên 7. Resource Server chỉ chấp nhận token nếu claim version **khớp giá trị hiện hành** trong nguồn trạng thái đã tin:

~~~text
if jwt.session_version != state.current_session_version:
    deny
~~~

**Vấn đề then chốt:** RS phải **biết `current_session_version=7`** bằng online check, event hoặc cache được cập nhật. Nếu RS chỉ đọc `session_version=6` bên trong JWT, sự hiện diện của claim **không tạo khả năng revoke tức thời**.

### 10.2. Chọn đúng mức áp dụng

| Version / cutoff key | Phạm vi vô hiệu | Thích hợp |
| --- | --- | --- |
| `user_version` | Toàn bộ token cũ của user | Khóa tài khoản, logout all |
| `session_version` hoặc `sid` state | Tokens thuộc một session | Logout một thiết bị |
| `grant_version` | Tokens thuộc một OAuth grant/client | Revoke ứng dụng được kết nối |
| `tenant_membership_version` | Quyền theo tổ chức | User rời tenant hoặc bị đổi quyền |
| `client_version` | Tokens cũ của workload/client | Compromise của service principal |

Các tên là **custom claims/metadata**, không phải claim chuẩn phải có trong JWT access token. Cần định nghĩa issuer/profile và RS semantics rõ ràng; không nhét một version toàn cục rồi vô hiệu tất cả tenants ngoài dự kiến.

### 10.3. Cutoff timestamp: `revoked_after`

Một biến thể lưu:

~~~text
revoke all tokens issued at/before 10:00:00 UTC

RS accepts only tokens whose trusted iat
is strictly newer than the revocation cutoff,
subject to issuer/profile/precision rules.
~~~

Cần thận trọng **độ chính xác timestamp** (giây/milliseconds), thứ tự giữa issuance và revoke, clock skew và race concurrent requests. Hai token được phát cùng một giây có thể có `iat` như nhau. Nếu yêu cầu semantics chặt, **monotonic version/counter do AS phát** thường ít mơ hồ hơn so sánh timestamp.

### 10.4. Vấn đề đồng thời giữa revoke và issuance

Nếu issuance đọc version=6, rồi admin revoke tăng lên 7, nhưng AS vẫn ký/phát token mang version=6 **sau khi trả revoke thành công**, token phải bị RS từ chối nếu state check thấy 7. Nếu hệ thống muốn bảo đảm “sau khi revoke commit thì không phát token cũ”, cần transaction/ordering tại issuer và tests concurrency, không chỉ tăng counter ở một service rồi để issuer dùng cache stale.

### 10.5. Version không thay kiểm tra quyền trên dữ liệu

Một token đúng session version và `scope=orders.read` vẫn có thể bị từ chối truy cập order của tenant khác. Version tracking chỉ là **một tín hiệu trạng thái**; scope/audience/tenant/ownership còn phải kiểm tra.

## 11. Chiến lược 4: introspection hoặc online authorization

Với **RFC 7662 Token Introspection**, Resource Server gọi AS để xác định token có `active` không và nhận metadata được phép. Nếu AS quản lý trạng thái revoke tập trung và **RS không dùng cache stale**, revocation có thể được enforce gần thời điểm AS commit hơn nhiều so với JWT offline.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client có access token T
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: API request Bearer T
    RS->>AS: POST introspect T + RS caller credential
    AS->>AS: Kiểm tra caller auth và token state
    AS-->>RS: active=true, aud/scope/exp
    RS-->>C: 200 nếu resource policy cũng đúng
    Note over AS: Admin revoke T/grant và commit
    C->>RS: API request Bearer T
    RS->>AS: POST introspect T
    AS-->>RS: active=false
    RS-->>C: 401 hoặc lỗi không tiết lộ chi tiết
~~~

### 11.1. Online check giải quyết điều gì và không giải quyết điều gì?

**Có thể giải quyết:** RS nhận quyết định trạng thái mới theo trust contract với AS; không cần chờ JWT hết hạn. **Không tự giải quyết:** latency/availability, AS cache stale, race giữa state check và business action, token audience/scope/ownership và sender constraint.

Một request có thể introspect `active=true` **trước** khi revoke commit rồi thực hiện thao tác **sau** commit. Nếu nghiệp vụ yêu cầu không cho thao tác nào hoàn thành sau revoke, cần **authorization check gần thời điểm commit business transaction**, có thể cùng một nguồn consistency/authorization service, và xác định semantics “in-flight requests”.

### 11.2. Bắt buộc xác thực bên gọi introspection

Theo RFC 7662, introspection endpoint phải bảo vệ bằng **caller authentication** và **permission disclosure**; không cho browser public giữ secret rồi trực tiếp hỏi token. RS có thể dùng client secret Basic, JWT assertion, mTLS hoặc method được AS hỗ trợ, kèm access control theo resource/audience/token type.

**Token đang được introspect** nằm trong form body `token=T`; **credential của RS** dùng xác thực caller là một giá trị **riêng**. Không dùng Bearer token T làm chính authentication credential cho introspection trừ khi AS profile có cơ chế minh bạch tương ứng.

### 11.3. `active=false` khác AS lỗi 401/503

| Kết quả | Ý nghĩa | RS nên làm |
| --- | --- | --- |
| HTTP 200, `active=true` | Token được AS chấp nhận trong ngữ cảnh | Kiểm audience/scope/time/business policy |
| HTTP 200, `active=false` | Token inactive, invalid hoặc caller không được tiết lộ metadata | Từ chối token |
| HTTP 401 từ introspection | RS credential sai/đã revoke | **Không coi là T inactive**; xử lý lỗi caller/ops, fail closed |
| HTTP 403 từ introspection | RS không có quyền gọi/nhìn token | Fail closed, sửa registration/policy |
| HTTP 429/5xx/timeout | AS chưa trả quyết định đáng tin | Fail closed hoặc dùng cache còn hạn **theo policy**, không tự allow |

Với dependency outage, RS có thể trả **503 Service Unavailable** cho API thay vì 401 “token invalid”, tùy contract, nhưng **không được cấp quyền khi chưa xác minh được trạng thái bắt buộc**.

### 11.4. Cache introspection làm thay đổi SLA revoke

~~~text
10:00:00  RS introspect JWT T: active=true, cache TTL 60s
10:00:20  Token T bị revoke tại AS
10:00:45  RS dùng cached active=true cho T
10:01:00  Cache hết hạn; AS trả active=false
~~~

Các mốc minh họa một cửa sổ trễ trong vòng một phút. Nếu RS cache `active=true` trong 60 giây thì “thu hồi dưới 1 giây” không được bảo đảm bởi kiến trúc đó.

TTL phù hợp:

\[
\mathrm{TTL}_{\mathrm{cache}}
\leq \min(\mathrm{TTL}_{\mathrm{policy}},
           \max(0,\mathrm{exp}-\mathrm{now}))
\]

Cần gắn cache key với **trusted issuer, caller/resource policy và token fingerprint**; không dùng cached metadata từ Payments RS cho Orders RS. Nếu `exp` thiếu, không tự cho cache vô hạn. **Đừng kéo dài stale cache khi AS down** để bảo đảm uptime.

## 12. Chiến lược 5: phát sự kiện revoke tới Resource Servers

Thay vì gọi AS mỗi request, một control plane có thể **phát sự kiện khi revoke** để các Resource Servers cập nhật denylist/session versions hoặc invalidate caches.

~~~mermaid
flowchart TD
    A["Admin/user revoke grant"] --> B["AS commit authoritative revocation state"]
    B --> O["Transactional outbox / durable event"]
    O --> MB["Message broker / security event stream"]
    MB --> R1["Orders RS cập nhật denylist"]
    MB --> R2["Payments RS cập nhật version cache"]
    MB --> R3["Gateway cập nhật invalidation"]
    R1 --> C["API checks + resource policy"]
    R2 --> C
    R3 --> C
~~~

### 12.1. Event push giảm độ trễ, không tạo phép màu

Khi mạng hoạt động bình thường, một sự kiện có thể tới nhiều RS nhanh. Nhưng với **network partition, consumer restart, queue backlog, event loss hoặc replay out-of-order**, một RS có thể không biết revoke mới.

**Phải đo và định nghĩa**:

- Thời điểm revocation state được **commit** tại authority;
- Thời điểm event được ghi vào outbox/broker bền vững;
- Thời điểm từng RS nhận, xác thực và **apply** event;
- Có ACK/watermark xác định consumer đã theo kịp hay không;
- Hành vi RS nếu lag vượt ngưỡng SLA;
- Snapshot/resync khi consumer mất sự kiện.

### 12.2. Outbox và idempotent consumers

Nếu AS cập nhật database rồi phát event ở một thao tác tách biệt, process crash giữa hai bước có thể khiến state đã revoke nhưng **không có event**. **Transactional outbox** giúp commit state và bản ghi event trong cùng transaction, rồi giao event cho broker sau.

Consumer nên **idempotent**, dùng event ID/version monotonic và không để event `GRANT_ACTIVE` cũ khôi phục grant đã `REVOKED` mới hơn.

~~~text
grant_id = G123
event_version = 14
status = REVOKED

if event_version > local_version[G123]:
    apply status/version
else:
    ignore duplicate or stale event
~~~

### 12.3. Recovery khi node offline

Node RS bị ngắt khỏi broker một giờ có thể giữ state cũ. Trước khi nhận lại traffic, nó cần **replay events hoặc tải snapshot/checkpoint đáng tin**. Nếu chính sách đòi revocation nhanh, node stale phải **fail closed/không phục vụ route nhạy cảm** cho đến khi đồng bộ.

### 12.4. Event không nên mang raw tokens

Thay vì gửi JWT nguyên vẹn trên broker, sự kiện có thể chứa **grant ID, session ID, token-ID fingerprint và version** theo access control của hệ thống. Protect topic ACL, encryption, integrity, retention, và không đưa event payload vào logs/metrics công khai.

### 12.5. Event ordering theo issuer và phạm vi

Nếu các AS nodes phát event cho cùng grant, cần có **authoritative monotonic version**; timestamps từ các máy có clock skew không đủ để giải quyết ordering. Với revoke rồi re-authorize cùng client, cấp một **grant ID/version mới** hoặc định nghĩa lifecycle để grant cũ không hồi sinh.

## 13. Chiến lược 6: thay signing key có phải revocation?

**Key rotation** thường dùng để thay khóa định kỳ, xử lý compromise và vận hành crypto agility. Nhưng **thu hồi một JWT cụ thể bằng cách rút signing key** có thể vô hiệu **mọi JWT được ký bằng key đó**, không chỉ token bị đánh cắp.

### 13.1. JWT được xác minh bằng JWKS

~~~text
AS signs:
  JWT A header: kid=key-1, alg=RS256
  JWT B header: kid=key-1, alg=RS256

RS trusts JWKS key-1:
  both A and B can verify.

AS removes/revokes key-1:
  RS chỉ ngừng chấp nhận A/B khi key trust state
  đã cập nhật theo policy.
~~~

Nếu RS vẫn cache public key `key-1` và không biết key đó đã bị distrust, nó có thể tiếp tục xác minh JWT cho đến cache expiry hoặc trạng thái mới. Vì vậy **rút key khỏi JWKS không bảo đảm tất cả RS dừng ngay**.

### 13.2. Những sai lầm về key rotation

- **Xóa key** khỏi JWKS mà không có chiến lược cache invalidation có thể không hiệu quả ngay.
- **Đổi `kid`** trên token mới không làm token cũ tự invalid.
- **Đổi cùng `kid` nhưng thay key content** gây key confusion/cache inconsistency; cần kế hoạch rotation rõ.
- **Thu hồi private signing key bị lộ** phải kết hợp phân phối trust update, denylist/cutover và có thể tạm dừng API nếu không bảo đảm an toàn.
- Không tắt signature verification hoặc chấp nhận `alg=none` để “tránh lỗi trong lúc rotate”.

### 13.3. Emergency key compromise

Nếu attacker có private key ký JWT, họ có thể tạo token mới cho tới khi RS ngừng tin key, bất kể token revocation denylist trước đó có ghi ID nào. Do đó incident response phải:

1. Vô hiệu việc ký bằng compromised key tại AS;
2. Cập nhật trusted keys/algorithms và ép RS refresh trust state;
3. Có cơ chế **invalidate all tokens signed by compromised key**;
4. Xử lý RS chưa nhận cập nhật bằng fail closed/traffic isolation khi rủi ro đòi hỏi;
5. Audit token issuance/trust changes và phục hồi keys.

**Kỹ thuật này là thu hồi ở cấp key, không phải giải pháp bình thường để revoke một session riêng lẻ.**

## 14. Sender-constrained token giúp gì khi JWT bị sao chép?

**Bearer token** cho phép người giữ chuỗi token trình token đến RS trong thời hạn; nếu bị lấy, attacker có thể replay. **Sender-constrained tokens** yêu cầu thêm bằng chứng về khóa/chứng chỉ của bên gửi:

| Cơ chế | Proof | Lợi ích | Không giải quyết |
| --- | --- | --- | --- |
| **DPoP (RFC 9449)** | Proof JWT theo request, key binding `cnf.jkt` | Token copy **một mình** khó replay | Nếu khóa + token đều bị lấy; revocation trạng thái |
| **mTLS-bound token (RFC 8705)** | Client certificate + `cnf.x5t#S256` | Yêu cầu sở hữu cert key | Key compromise, RS/AS không kiểm binding |
| **Bearer access token** | Chuỗi token | Đơn giản | Token bị copy có thể replay nếu còn active |

### 14.1. DPoP không làm JWT vô hiệu ngay khi revoke

DPoP có các kiểm tra như `htm`, `htu`, `iat`, `jti`, `ath` và key binding. Nó giúp từ chối proof phát lại và yêu cầu sender nắm private key. Nhưng khi user/admin revoke grant, RS vẫn cần **biết grant đã revoke** hoặc chờ JWT hết hạn. **DPoP không phải revocation signal**.

### 14.2. Certificate-bound JWT cũng không phải trạng thái quyền

Một JWT ràng buộc mTLS certificate vẫn có thể còn hạn và client vẫn giữ certificate sau khi quyền tenant bị thu hồi. RS phải kiểm tra business authorization hoặc revocation state. **Sender proof chỉ trả lời “ai đang trình token”, không trả lời “quyền đã được rút chưa”.**

### 14.3. Thu hồi certificate khác thu hồi JWT

Cert revocation có thể có CRL/OCSP hoặc cơ chế PKI khác, với caching và latency riêng. Không tự giả định tất cả RS thực hiện online certificate revocation nếu kiến trúc chỉ kiểm certificate thumbprint trong JWT. Thử nghiệm phải bao gồm certificate compromise, key rotation và sender-binding enforcement thực tế.

## 15. Session logout, OIDC và grant revocation

Trong OIDC, user đăng nhập với OpenID Provider (OP); ứng dụng có thể có **local session cookie**, OP có **SSO session**, và RS có **access token**. Đây là các đối tượng khác nhau.

### 15.1. Những thứ cần tách rõ

~~~text
Browser cookie của BFF
   ≠ OP login session
   ≠ OAuth refresh token/grant
   ≠ JWT access token đã phát
   ≠ quyền tenant/resource tại RS
~~~

Ví dụ BFF logout:

1. Server vô hiệu local session và xóa session cookie;
2. BFF revoke refresh token/grant ở AS nếu policy yêu cầu;
3. Nếu có JWT access token đã phát, áp denylist/version/online state theo security SLA;
4. Có thể kích hoạt OP logout/back-channel logout tùy OIDC profile;
5. Resource server vẫn enforce token status và business rights.

### 15.2. OIDC logout signals không tự thay JWT access-token revocation

Các cơ chế Front-Channel/Back-Channel Logout có thể thông báo việc kết thúc **client/OP session** theo profile, nhưng **không mặc nhiên xóa hoặc vô hiệu JWT Bearer đã tới các resource servers**. Cần định nghĩa ràng buộc giữa session ID `sid`, grant và access-token revocation state.

### 15.3. “Logout all devices” phải chỉ rõ tác động

Một chức năng logout all có thể:

- Invalidate mọi local sessions của ứng dụng;
- Revoke refresh token families;
- Tăng `user_version`/session generations;
- Phát events tới RS hoặc yêu cầu online checks;
- Thu hồi device grants;
- Từ chối future logins khi account disabled.

Nếu không có bước RS nhận state và access tokens còn `exp`, **không hứa người dùng sẽ bị ngắt ngay mọi nơi**. Trình bày rõ thời hạn tối đa/giới hạn kỹ thuật của từng hệ thống.

## 16. Thiết kế denylist có tính nhất quán trong nhiều Resource Servers

### 16.1. Bản ghi SQL tham khảo

Một schema PostgreSQL **mang tính minh họa**:

~~~sql
CREATE TABLE revoked_access_tokens (
    issuer_id       VARCHAR(200) NOT NULL,
    token_id_mac    VARCHAR(64) NOT NULL,
    revoked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    reason_category VARCHAR(64) NOT NULL,
    PRIMARY KEY (issuer_id, token_id_mac)
);

CREATE INDEX idx_revoked_access_tokens_expiry
    ON revoked_access_tokens (expires_at);

-- Cleanup chạy sau khi đã tính policy leeway phù hợp:
DELETE FROM revoked_access_tokens
WHERE expires_at < NOW();
~~~

`token_id_mac` có thể lưu hex HMAC-SHA256 (64 hex chars) trên **issuer+token ID** hoặc raw JWT theo strategy được thiết kế; **không phải JWS signature**, không thay token verification. Khóa HMAC được quản lý bên ngoài database.

### 16.2. Không cho revoke bị ghi đè bởi token issuance đồng thời

Nếu AS phát token trong một transaction khác với revoke, cần có **authoritative grant version/issuance policy** để token mới được phát sau revoke không lấy quyền stale. Có thể:

- Đánh dấu grant `REVOKED` trong transaction và phát event cùng outbox;
- Issuer kiểm tra trạng thái grant vừa được commit trước lúc ký token;
- Thử concurrency giữa refresh, revoke và JWT issuance;
- Với quyết định revoke một token theo `jti`, đảm bảo ID được ghi đúng và không xuất hiện duplicate issuances.

**Đừng chỉ cập nhật một cache best-effort** rồi trả 200 “revocation complete” khi authoritative store chưa commit.

### 16.3. Reader consistency và outage

Nếu RS kiểm tra Redis replica có độ trễ, nó có thể chưa thấy denylist entry dù primary đã ghi. Với endpoint cần guarantee chặt:

- Đọc state từ nguồn consistency đáp ứng SLA;
- Hoặc dùng signed/versioned event state đã đồng bộ với watermark;
- Hoặc fail closed nếu node không chứng minh được trạng thái đủ mới.

Một Redis `GET` nhanh không tự có nghĩa **linearizable revocation**. Network partition, failover và replication delay phải được đưa vào test.

### 16.4. Liveness vs safety

**Safety:** RS không chấp nhận một token đã bị policy từ chối theo bảo đảm cam kết.

**Liveness/availability:** RS vẫn phục vụ các request khi AS/store không sẵn sàng.

Một hệ thống muốn cả hai trong tình huống mất kết nối toàn phần sẽ gặp giới hạn thông tin: RS không thể biết revoke mới nếu không liên lạc được nguồn trạng thái. **Phải chọn trade-off rõ ràng theo risk** thay vì ngầm “allow cached active mãi”.

## 17. Spring Security 6: kiểm tra denylist bên cạnh JWT verification

Trong **Spring Boot 3 / Spring Security 6**, một Resource Server có thể dùng `NimbusJwtDecoder` để verify JWT. Nếu muốn kiểm tra thêm trạng thái thu hồi, ta có thể gắn một **`OAuth2TokenValidator<Jwt>`** sau bước xác minh chữ ký.

**Quan trọng:** Đoạn code dưới đây là **mẫu tích hợp bảo mật** minh họa. Nó giả định issuer luôn phát JWT access token có `jti` duy nhất đủ tin cậy và `RevocationLookup` được hiện thực bởi nguồn trạng thái đáng tin, không phải một `HashSet` local tự khởi tạo.

### 17.1. Interface cho revocation state

~~~java
public interface RevocationLookup {
    /**
     * Lookup authoritative denylist hoặc state có consistency
     * đáp ứng chính sách. Không trả false khi backend bị lỗi.
     */
    boolean isRevoked(String trustedIssuer, String jwtId);
}
~~~

Lớp triển khai phải dùng khóa HMAC/lookup namespace phù hợp issuer và token purpose, TTL, failure semantics; **không thể tự tạo một boolean `false` mặc định khi database timeout**.

### 17.2. Validator JWT `jti`

~~~java
import java.net.URI;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RevocationValidator
        implements OAuth2TokenValidator<Jwt> {

    private final RevocationLookup lookup;

    public RevocationValidator(RevocationLookup lookup) {
        this.lookup = lookup;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        URI issuer = jwt.getIssuer();
        String jti = jwt.getId();

        // Profile cụ thể của AS yêu cầu jti cho access tokens.
        if (issuer == null || jti == null || jti.isBlank()) {
            return reject("Required issuer or JWT ID is missing");
        }

        // Lookup phải fail closed khi backend không sẵn sàng:
        // đừng catch lỗi rồi coi token chưa bị revoke.
        if (lookup.isRevoked(issuer.toString(), jti)) {
            return reject("Access token revoked");
        }
        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult reject(String detail) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", detail, null));
    }
}
~~~

**Không nên trả detail nhạy cảm cho client API** nếu thư viện chuyển lỗi validator ra response. Production cần error translation phù hợp; response client-facing thường chỉ cần `invalid_token`. Nếu revocation store **unavailable**, exception phải được xử lý ở lớp infrastructure/authentication để **không allow request** và có thể phân biệt dependency outage với invalid token.

### 17.3. Kiểm tra audience + issuer + signature + revocation

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {
    private static final String EXPECTED =
        "https://api.example.com/orders";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience() != null
                && jwt.getAudience().contains(EXPECTED)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));
    }
}

@Configuration
public class JwtRevocationConfiguration {
    @Bean
    JwtDecoder jwtDecoder(RevocationLookup lookup) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/oauth2/jwks")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(
                "https://auth.example.com"),
            new AudienceValidator(),
            new RevocationValidator(lookup)
        ));
        return decoder;
    }
}
~~~

Trong kiến trúc này:

- **Signature/JWS algorithm** được decoder kiểm tra trước khi validator phụ xử lý claims;
- **Issuer/time validation** phải được giữ bằng `JwtValidators.createDefaultWithIssuer` hoặc validator tương đương;
- **Audience** được kiểm tra cho Orders API;
- **Denylist** được hỏi dựa trên `iss` và `jti` đã qua validation trust;
- **Scope, principal type, tenant và object-level permission** vẫn phải được Spring Security filters/business layer kiểm tra.

**Chú ý phiên bản:** API của Spring Security và cách cấu hình decoder có thể thay đổi; cần xác minh version thực tế và integration test tại ứng dụng. JWKS endpoint trong ví dụ là giả định; URL thật phải tới từ **trusted issuer configuration**, không dựng từ JWT header `jku`.

### 17.4. Failure semantics phải rõ

Nếu `RevocationLookup` trả `false` vì **Redis timeout nhưng code bắt lỗi và “tạm coi chưa revoke”**, lớp kiểm tra trở thành fail-open. Thay bằng:

~~~text
lookup result = REVOKED       -> deny token
lookup result = NOT_REVOKED   -> tiếp tục các policy khác
lookup result = UNAVAILABLE   -> fail closed / dependency error
~~~

Không viết:

~~~java
// SAI: outage bị biến thành bằng chứng token hợp lệ.
try {
    return lookup.isRevoked(issuer, jti);
} catch (Exception ignored) {
    return false;
}
~~~

Nếu API yêu cầu trả **503** khi revocation store unavailable, cần tùy chỉnh exception handling để không báo sai thành “token signature invalid”; nhưng **safety là từ chối truy cập khi thiếu trạng thái bắt buộc**, không nhất thiết status 401.

### 17.5. Không lấy tất cả trạng thái từ JWT

Một claim `revoked=false` bên trong JWT được ký lúc phát hành chỉ mô tả trạng thái **thời điểm phát**. Admin revoke ở phút sau không thay đổi chữ ký/claims của JWT. Do đó RS không được đọc `revoked=false` rồi bỏ qua denylist hoặc online policy.

## 18. Java 17: tạo fingerprint không lưu Bearer token plaintext

Khi hệ thống cần lưu dấu revoke theo token, nên hạn chế lưu token raw. Ví dụ Java sau tạo **HMAC-SHA256** trên identifier đã được verify, với domain separation để tránh lẫn token types/issuers:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RevocationFingerprint {
    private RevocationFingerprint() {}

    public static String of(
            byte[] dedicatedHmacKey,
            String trustedIssuer,
            String verifiedJwtId) {

        if (dedicatedHmacKey == null
                || dedicatedHmacKey.length < 32
                || trustedIssuer == null
                || trustedIssuer.isBlank()
                || verifiedJwtId == null
                || verifiedJwtId.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid revocation fingerprint input");
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                dedicatedHmacKey, "HmacSHA256"));

            // Domain separation: không dùng chung MAC với loại khác.
            String message = "access-token-jti"
                + "\0" + trustedIssuer
                + "\0" + verifiedJwtId;

            byte[] digest = mac.doFinal(
                message.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HMAC-SHA256 unavailable", ex);
        }
    }
}
~~~

**Giới hạn và lưu ý:**

- `trustedIssuer` và `verifiedJwtId` phải lấy **sau khi JWT signature, issuer và token type được kiểm tra**, không đọc từ JWT chưa verify rồi coi là authority.
- Key HMAC phải lấy từ **KMS/secret manager**, không hard-code, không dùng lại client secret hoặc JWS signing key.
- **Key rotation** cần versioned fingerprints/dual lookup trong cửa sổ chuyển đổi nếu các denylist entries cũ vẫn còn hiệu lực.
- `Mac` được tạo mới theo call, tránh chia sẻ một instance không thread-safe qua nhiều threads.
- Không in token, `jti`, HMAC key hoặc fingerprint liên kết được với user vào public logs.
- Dùng `HexFormat` yêu cầu Java 17; nếu runtime thấp hơn, cần encoding khác được test.
- Với **opaque token**, có thể MAC trên raw token theo một đường xử lý riêng, nhưng cần phân biệt namespace và lookup semantics.

### 18.1. Bản ghi trạng thái cần TTL đúng

~~~sql
INSERT INTO revoked_access_tokens (
    issuer_id, token_id_mac, revoked_at,
    expires_at, reason_category
) VALUES (
    :trusted_issuer,
    :token_id_mac,
    NOW(),
    :expires_at_with_leeway,
    'SECURITY_INCIDENT'
)
ON CONFLICT (issuer_id, token_id_mac)
DO UPDATE SET
    expires_at = GREATEST(
        revoked_access_tokens.expires_at,
        EXCLUDED.expires_at
    );
~~~

Pseudocode/SQL trên chỉ mô tả **idempotent upsert**. Trong hệ thống thật cần kiểm tra quyền thực hiện revoke, kiểu dữ liệu, clock, transaction, audit và consistency giữa DB/event broker. Một token không có `exp` hợp lệ theo profile không nên được cấp nhận ở RS; không tự tạo TTL vô hạn.

### 18.2. `jti` collision và issuer namespaces

AS cần tạo `jti` có tính duy nhất theo profile. Nếu hai issuers cùng tạo `jti=123`, một denylist chỉ có `123` sẽ chặn sai. Với multi-issuer, namespace phải gồm **issuer đã tin** và token purpose, có thể thêm audience/tenant khi contract cần.

## 19. Security event, cache và độ trễ hữu hạn

Một triển khai có cả **short JWT TTL + event-driven denylist + online fallback** cần định nghĩa rõ trạng thái RS:

~~~text
UP_TO_DATE:
  đã áp event đến watermark yêu cầu
  -> có thể dùng cache theo policy.

LAGGING:
  chưa nhận event trong giới hạn trễ cho phép
  -> route nhạy cảm yêu cầu online check hoặc fail closed.

DISCONNECTED:
  không thể chứng minh state hiện hành
  -> không cho operations yêu cầu strong revocation guarantee.
~~~

### 19.1. Ước lượng propagation latency

Nếu yêu cầu thu hồi được commit ở `t0`, một RS chỉ bắt đầu từ chối khi nó **áp dụng** event ở `t1`:

\[
\Delta_{\mathrm{propagation}} = t_1 - t_0
\]

**Không chỉ đo thời gian producer gửi event.** Cần đo khoảng thời gian từ authoritative DB commit đến **request path RS thực sự áp policy mới**. Metrics nên có p50/p95/p99/max và tỷ lệ consumers lag vượt SLA.

### 19.2. Trạng thái cache denylist

Nếu RS cache cả kết luận “`jti` không nằm trong denylist”, một sự kiện revoke mới có thể bị giữ ngoài decision tới lúc negative cache hết TTL. Với critical routes:

- Không cache negative revocation state quá SLA;
- Hoặc invalidate theo event/counter;
- Hoặc truy vấn online authoritative store;
- Hoặc fail closed khi event stream lag.

**Cache hit nhanh không đồng nghĩa thông tin mới.** Trạng thái cache phải gắn với validity window/version.

### 19.3. Quản lý TTL ở nhiều lớp

Một API có thể có:

1. JWT `exp` validation leeway;
2. RS in-process authentication cache;
3. Redis denylist cache;
4. Introspection response cache;
5. API gateway decision cache;
6. Policy/tenant membership cache.

Nếu có **nhiều lớp** và một lớp không invalidation, độ trễ hiệu lực có thể **lớn hơn dự đoán**. Không tự cộng/trừ các TTL mà không vẽ data flow; đánh giá đường quyết định **dài nhất cho request vẫn được chấp nhận**.

### 19.4. Không cho token sống lâu hơn `exp` qua cache

Ngay cả khi introspection hoặc policy được cache, RS phải **kiểm thời hạn token mỗi request** hoặc bảo đảm cache entry không thể sống vượt `exp` cộng leeway được cho phép. Tránh biến một xác thực JWT thành **server-side session vô hạn** mà không có TTL độc lập.

## 20. Phân biệt revoke token và thay đổi quyền nghiệp vụ

Một hệ thống có thể muốn thu hồi **quyền** ngay cả khi không biết JWT nào đang lưu ngoài client.

### 20.1. Các ví dụ

| Sự kiện | Token có thể vẫn hợp lệ cryptographically? | Kiểm soát cần cập nhật |
| --- | --- | --- |
| User rời tenant Acme | Có | Tenant membership/authorization state |
| Role manager bị bỏ | Có | Role/permission policy ở RS |
| Admin thu hồi consent client | Có | OAuth grant/refresh, nếu cần AT revoke |
| Thiết bị bị mất | Có | Device session/grant, refresh family, AT compromise window |
| Client secret bị lộ | Có | Client credential rotation và tokens do client đã xin |
| User đổi password | Có | Session policy, account version và revocation theo security contract |
| User logout browser | Có | Local/OP session và token lifecycle riêng |

**Không dùng một phương thức duy nhất cho mọi thay đổi quyền.** Một quy tắc object ownership trong database thường cần kiểm tra tại business service; ngược lại một access token bị đánh cắp có thể cần denylist/revoke cho tất cả routes liên quan.

### 20.2. Scope không chứa mọi điều kiện truy cập

JWT có `scope=orders.read` có thể được sử dụng nhiều lần trong lifetime, nhưng RS vẫn phải kiểm tra **order thuộc tenant mà principal hiện được phép xem**. Claim scope không tự ràng buộc record ownership nếu API không có policy cụ thể.

~~~sql
SELECT *
FROM orders
WHERE id = :order_id
  AND tenant_id = :trusted_authorized_tenant;
~~~

`:trusted_authorized_tenant` đến từ token/grant đã verify và authoritative permission context; không tin `X-Tenant-Id` do client tự khai làm quyền truy cập.

### 20.3. Step-up/reauthentication cho thao tác rủi ro cao

Khi user vẫn có access token hợp lệ nhưng muốn **hoàn tiền** hoặc **đổi email bảo mật**, hệ thống có thể yêu cầu authentication gần đây/MFA với `auth_time`/`acr` theo OIDC policy hoặc central approval. Đây là lớp bổ sung, không thay token validation, revocation và quyền nghiệp vụ.

## 21. Ứng phó khi JWT access token bị đánh cắp

**Kịch bản:** Một service vô tình log Bearer token của user. Attacker có bản sao JWT còn 10 phút, trong khi user hoặc admin yêu cầu “đăng xuất ngay mọi nơi”.

### 21.1. Quy trình xử lý sự cố theo từng lớp

1. **Xác định phạm vi:** issuer, audience, client, principal, tenant, scopes, `jti`, thời gian phát/expiry, đường rò credential, API chịu ảnh hưởng. Không dán raw token vào ticket/chat/log.
2. **Cắt nguồn rò:** tắt logging raw `Authorization`, sửa APM/proxy, quyền truy cập secret store và kênh exfiltration.
3. **Thu hồi quyền cấp token mới:** revoke refresh token/token family/grant và session theo policy; vô hiệu compromised client credential nếu liên quan.
4. **Vô hiệu access token đã phát:** nếu có denylist `jti`/fingerprint, ghi trạng thái authoritative và publish event; nếu dùng introspection, đảm bảo token bị trả `active=false` theo contract.
5. **Đánh giá RS có thực sự nhận revoke:** theo dõi event lag, cache state, timeout và kiểm thử request đến **từng API/region/instance** có thể bị tác động.
6. **Kiểm tra dữ liệu:** audit các thao tác đã thực hiện bằng token ở thời gian compromise, đặc biệt export/ghi/xóa/hoàn tiền.
7. **Bảo vệ sau sự cố:** cân nhắc password reset/step-up/reauth theo threat model, nhưng đừng nghĩ đổi password tự chặn JWT cũ.
8. **Thông báo và khôi phục:** cung cấp user/admin thông tin đúng về trạng thái thu hồi, cửa sổ tiếp tục chấp nhận và hướng xử lý.
9. **Kiểm thử regression:** không còn raw tokens trong logs và cơ chế revoke/propagation có metrics chứng minh.

### 21.2. Nếu chưa có denylist hay online check?

**Không thể hứa thu hồi JWT A ngay bằng một lệnh ở AS khi mọi RS chỉ verify offline.** Các lựa chọn thực tế:

- Chặn client/session ở gateway nếu có một ingress chung đáng tin;
- Hạn chế hoặc tạm dừng endpoint nhạy cảm để ngăn khai thác;
- Rút signing key theo phương án emergency nếu phạm vi tác động cho phép (rất rộng và cần cập nhật trust ở RS);
- Đợi token hết `exp` trong khi ngăn cấp token mới;
- Khẩn trương bổ sung online state/denylist cho các trường hợp cần SLA cao.

Đây là **quyết định vận hành có rủi ro và đánh đổi rõ ràng**, không phải phím tắt trong thư viện JWT.

### 21.3. Đừng chỉ revoke một `jti` nếu credential gốc cũng bị lộ

Nếu attacker chiếm cả **refresh token** hoặc **client private key/secret**, họ có thể xin token mới với `jti` khác; chỉ denylist JWT đã thấy không đủ. Cần xử lý **nguồn cấp quyền** (refresh token family, grant, client credential, signing key) và các tokens đã phát từ nguồn đó.

### 21.4. Token theft và token replay là hai tín hiệu khác nhau

Một Bearer access token bình thường có thể xuất hiện trong nhiều API calls của cùng client; **reuse tự thân không chứng minh bị trộm**. Có thể phát hiện bất thường qua network/device/ASN, rủi ro địa lý, user agent, hành vi xuất dữ liệu và concurrent use từ ngữ cảnh không tương thích. Tránh dựa duy nhất vào IP thay đổi (mobile networks/NAT) để revoke user hàng loạt gây false positives.

**Phát hiện bất thường chỉ hữu ích khi gắn với cơ chế revoke thực thi được**. Nếu alert nói “token đã bị vô hiệu” trong khi RS offline vẫn cho phép, hệ thống tạo cảm giác an toàn giả.

## 22. Kiến trúc tham khảo cho nhiều mức rủi ro

Một module bảo mật có nhiều endpoints không nhất thiết dùng chung một chính sách:

~~~mermaid
flowchart TD
    C["Request có JWT access token"] --> V["RS verify signature, iss, aud,\nexp, nbf, token type"]
    V --> R{"Phân loại request theo risk"}
    R -->|Thấp| L["TTL ngắn + scope check\nvà quyền resource"]
    R -->|Trung bình| M["Denylist/version cache\nvới TTL có giới hạn"]
    R -->|Cao| H["Online authoritative check\nhoặc deny khi unavailable"]
    L --> P["Business authorization:\ntenant, owner, entitlement"]
    M --> P
    H --> P
    P --> D{"Tất cả policy đạt?"}
    D -->|Có| A["Thực hiện request"]
    D -->|Không| E["Từ chối"]
~~~

### 22.1. Ví dụ policy phân tầng

| API | Token policy | Revocation policy | Cần lưu ý |
| --- | --- | --- | --- |
| Xem dữ liệu công khai có định danh | JWT TTL ngắn | Có thể chỉ kiểm expiry nếu chấp nhận window | Không dùng cho PII nhạy cảm |
| Xem đơn hàng riêng | JWT + RS scope/tenant check | Denylist/session version với lag giới hạn | Membership thay đổi có thể cần online lookup |
| Tạo đơn hàng | JWT + quyền ghi | Denylist hoặc online state theo SLA | Idempotency, ownership và business rules |
| Hoàn tiền | JWT + step-up | Online grant/account state, fail closed | Phải xác minh hạn mức/approval khi giao dịch |
| Khóa tài khoản | Quản trị viên xác thực mạnh | Publish state revoke + audit propagation | Không báo thành công end-to-end trước khi đạt guarantee |

Các giá trị trong bảng là **gợi ý threat-model**, không phải chính sách bắt buộc cho mọi sản phẩm.

### 22.2. Một API có thể có nhiều cửa sổ chấp nhận

Khi áp JWT TTL ngắn và denylist, request có thể bị từ chối:

- Vì chữ ký/issuer/audience sai;
- Vì quá `exp`;
- Vì denylist đã cập nhật;
- Vì session/grant version stale;
- Vì user mất quyền tenant;
- Vì thiếu scope/step-up.

**Kết quả từ chối có thể đạt trước expiry**, nhưng nếu một lớp bắt buộc bị lỗi và code fail open thì thiết kế sẽ mất guarantee. Logging phải phân biệt **reason category** mà không lộ secrets.

### 22.3. “Tức thời” khi có request đang chạy

Một request đã được RS authorize ở `t1`, rồi admin revoke ở `t2` trước khi transaction business commit ở `t3`. Nếu requirement là “không có **bất kỳ commit nào** sau `t2`”, kiểm access token lúc `t1` chưa đủ. Cần liên kết authorization state với **điểm commit** hoặc cơ chế transaction/consistency phù hợp.

Điều này đặc biệt quan trọng với thanh toán, chuyển tiền, xóa tài nguyên và thay đổi quyền quản trị. Cần viết rõ **in-flight behavior** trong security requirements.

## 23. Các sai lầm thường gặp

### 23.1. “JWT có chữ ký hợp lệ nghĩa là user vẫn active”

**Sai.** Chữ ký xác minh phát hành/tính toàn vẹn, không phản ánh account/session/grant state mới hơn token.

### 23.2. “Gọi RFC 7009 và nhận HTTP 200 thì mọi RS đã chặn token”

**Sai.** 200 không phải ACK của từng RS; token không hợp lệ cũng có thể dẫn đến 200 nhằm tránh token enumeration. Độ trễ enforcement phụ thuộc thiết kế RS.

### 23.3. “Revoke refresh token là revoke tất cả access tokens đang cầm”

**Không mặc định.** Nó thường chặn phát token mới; access tokens đã cấp cần cơ chế riêng hoặc chờ expiry.

### 23.4. “Có `jti` là JWT được revoke tức thì”

**Sai.** `jti` chỉ là identifier; phải có denylist/online state và lookup được thực thi.

### 23.5. “RS chỉ cần kiểm `session_version` trong JWT”

**Sai.** Claim version phải được so với **authoritative current version** từ nguồn cập nhật; claim nằm trong JWT cũ không tự thay.

### 23.6. “Thay JWKS `kid` là token cũ hết hiệu lực”

**Sai.** Token đã ký bằng key cũ có thể tiếp tục được verify khi RS còn trust/cached key. Key revocation có tác động rộng và cần phối hợp trust rollout.

### 23.7. “Opaque token luôn được revoke ngay”

**Sai khi RS cache `active=true`** quá lâu hoặc AS/introspection replica chưa nhìn thấy revocation commit.

### 23.8. “Redis có TTL nên denylist bảo đảm nhất quán mạnh”

**Sai.** TTL chỉ quản lý tuổi bản ghi; replica lag, failover, lost events và stale negative caches vẫn có thể khiến RS chấp nhận token cũ.

### 23.9. “AS timeout thì cho request qua tạm”

**Nguy hiểm.** Đó là fail-open. Khi state check bắt buộc không sẵn sàng, route nhạy cảm phải fail closed theo contract.

### 23.10. “Logout browser tự xóa Bearer token ở thiết bị attacker”

**Sai.** Xóa cookie/local token không xóa bản sao token đã bị exfiltrate; phải xử lý grant/token tại AS/RS.

### 23.11. “DPoP hoặc mTLS đã thay revocation”

**Sai.** Sender constraint hạn chế token-only replay, nhưng không thay quyết định revoke và business authorization mới.

### 23.12. “Access token `jti` chỉ được dùng một lần”

**Sai với Bearer access tokens thông thường**: client hợp lệ gọi nhiều requests bằng cùng access token. One-time semantics thuộc những credentials/proofs khác như authorization code, rotated refresh token hoặc DPoP proof `jti` trong replay window.

### 23.13. “Một user bị xóa khỏi tenant sẽ tự mất mọi quyền vì JWT có tenant claim”

**Sai.** Claim được ký là snapshot; cần membership state mới hoặc chờ token hết hạn. RS phải kiểm data ownership chứ không tin header tenant do caller tự đặt.

### 23.14. “Dùng một denylist chung theo `jti` cho mọi issuer”

**Rủi ro.** Token IDs có thể va chạm giữa issuers/token profiles. Ràng buộc key với trusted issuer/purpose và định nghĩa policies rõ.

## 24. Các tình huống thực tế

**Tình huống A — User nhấn Logout, JWT vẫn dùng được.**

Frontend xóa access token khỏi memory nhưng attacker đã sao chép JWT trước đó. Orders RS chỉ verify signature/`exp`; token tiếp tục hoạt động 8 phút.

**Phân tích:** logout local không thu hồi bản sao. Nếu SLA yêu cầu ngăn ngay, cần denylist, online state hoặc các biện pháp khác; nếu không, giải thích rõ cửa sổ expiry.

**Tình huống B — Admin disable tài khoản nhân viên đã nghỉ.**

AS ngừng đăng nhập và refresh, nhưng microservice với cached JWT vẫn trả dữ liệu.

**Phân tích:** phải xác định disable account có bắt buộc online account check/propagation hay không. Với tài nguyên nhạy cảm, fail closed nếu state không cập nhật.

**Tình huống C — Refresh token rotation phát hiện reuse.**

Client A dùng refresh token cũ do attacker copy sau khi token đã rotate. AS thu hồi family.

**Phân tích:** đây là cơ chế tốt để ngăn access token **mới**, nhưng JWT đã phát theo family có thể tồn tại đến `exp` nếu RS không denylist/check grant.

**Tình huống D — RS đọc JWT version claim nhưng không truy vấn version store.**

JWT ghi `session_version=5`, AS tăng current version lên 6; RS chỉ kiểm version có tồn tại.

**Phân tích:** không tạo revocation enforcement; cần so sánh với state đáng tin được cập nhật.

**Tình huống E — AS ghi revoke và broker mất event.**

DB có trạng thái REVOKED, nhưng producer crash trước publish, một RS ở region khác vẫn chấp nhận token.

**Phân tích:** transactional outbox, replay/snapshot, consumer watermark và xử lý node lag/partition.

**Tình huống F — RS cache `active=true` 30 phút, JWT hết hạn sau 5 phút.**

Middleware tái sử dụng cached Authentication mà không kiểm lại token `exp`.

**Phân tích:** lỗi nghiêm trọng; cache không được kéo dài token lifetime. TTL thực tế phải không vượt thời hạn token theo policy.

**Tình huống G — Xóa signing key cũ khỏi JWKS và tưởng mọi JWT cũ vô hiệu.**

Một node RS vẫn cache key 10 phút, còn chấp nhận token ký bằng key cũ.

**Phân tích:** JWKS trust update/cache invalidation là quá trình phân tán; key revocation emergency phải kiểm chứng từng RS.

**Tình huống H — Access token của Payments được dùng ở Orders.**

JWT có signature/expiry hợp lệ và không nằm denylist, nhưng `aud=payments`.

**Phân tích:** Orders phải từ chối vì audience. Revocation state không thay audience validation.

**Tình huống I — Token có `orders.read` nhưng user rời tenant.**

RS đọc tenant claim cũ và cho xem đơn hàng của tổ chức cũ.

**Phân tích:** business entitlement/membership state cần cập nhật; denylist user/grant hoặc online authorization tùy SLA.

**Tình huống J — Redis revocation store lỗi, Java fallback `false`.**

Code catch exception và cho qua.

**Phân tích:** chính kiểm soát được thiết kế để chống token theft bị tắt khi tấn công hoặc outage. Phải fail closed, quan sát latency và phản hồi dependency error phù hợp.

**Tình huống K — User có DPoP-bound token bị copy.**

Attacker chỉ có chuỗi token, không có private key; RS yêu cầu DPoP proof đúng.

**Phân tích:** token-only replay bị hạn chế, nhưng nếu user bị revoke, RS vẫn cần state check hoặc expiry. Nếu attacker chiếm cả khóa và token, sender binding không đủ.

**Tình huống L — Hai authorization nodes phát JWT lúc admin revoke.**

Một issuer đọc grant active trước commit, phát token ngay sau revoke.

**Phân tích:** cần ordering/version transaction và kiểm ở RS; không coi “AS đã trả success” là chứng minh không có issuance race.

**Tình huống M — API hoàn tiền đang xử lý lúc revoke.**

Access check xảy ra trước khi admin disable user; business commit xảy ra sau.

**Phân tích:** chính sách “revoke tức thời” cần quy định in-flight requests/commit boundary, không thể dựa duy nhất vào JWT expiry.

## 25. Bộ kiểm thử bảo mật bắt buộc

| Test case | Kết quả kỳ vọng |
| --- | --- |
| JWT hợp lệ, còn hạn, issuer/audience đúng | Được xét theo scope/resource policy |
| JWT sai signature hoặc JWS algorithm ngoài allowlist | RS từ chối dù không có denylist |
| JWT sai `iss` hoặc `aud` | RS từ chối |
| JWT quá `exp` | RS từ chối dù cache/introspection cũ active |
| JWT `nbf` trong tương lai | RS từ chối theo clock policy |
| JWT `jti` nằm denylist | RS từ chối trước `exp` |
| JWT không có `jti` khi profile bắt buộc | RS từ chối |
| JWT có `jti` trùng issuer khác | Không làm lẫn revocation namespaces |
| JWT `jti` được đọc trước signature verification | Security test fail, không tin unverified claims |
| Denylist HMAC key bị rotate | Cửa sổ dual-lookup/version hỗ trợ revoke entries còn hiệu lực |
| Denylist record bị xóa trước `exp`+leeway | Test fail do revocation mất hiệu lực sớm |
| Revoke access token T tại AS | RS từ chối theo SLA đã cam kết |
| Revoke refresh token R nhưng access token A chưa hết hạn | Test thể hiện rõ guarantee (không tự giả A revoked) |
| RFC 7009 revoke token không hợp lệ | Client không suy đoán trạng thái từ HTTP 200 |
| Client không được phép revoke token người khác | AS từ chối hoặc response bảo vệ thông tin theo contract |
| `session_version` JWT nhỏ hơn current version | RS từ chối nếu online/version policy bắt buộc |
| RS không truy cập được version store | Fail closed, không tự coi phiên còn active |
| JWT phát đồng thời với revoke grant | Không có cấp quyền vượt ordering/version policy |
| User disable account | RS enforcement đúng SLA và route risk |
| User rời tenant Acme | Không đọc bản ghi Acme theo authority mới |
| Token đúng scope nhưng record tenant khác | RS từ chối object authorization |
| Access token Bearer dùng lặp nhiều requests bình thường | Không nhầm với replay của rotated refresh token |
| Refresh token cũ reuse sau rotation | AS xử lý token family theo policy |
| DPoP proof `jti` reuse | RS áp replay defense riêng của DPoP |
| DPoP-bound token thiếu proof/key đúng | RS từ chối sender constraint |
| mTLS-bound token thiếu certificate phù hợp | RS từ chối |
| Introspection trả `active=false` | RS từ chối token |
| Introspection trả HTTP 401 do caller secret sai | Không coi token active; xử lý lỗi caller và fail closed |
| Introspection trả 5xx/timeout | Fail closed/circuit breaker, không bỏ kiểm tra revoke |
| Introspection cache còn hạn nhưng grant bị revoke | Độ trễ nằm trong SLA đã nêu hoặc event invalidation hoạt động |
| Cache active sống lâu hơn token `exp` | Test fail, không cho phép |
| Redis replica lag sau revoke | RS không vi phạm consistency guarantee đã công bố |
| Hai RS nhận revoke event không cùng lúc | Lag/alert/fallback đúng policy |
| RS mất broker connection | Fail closed trên routes đòi state mới |
| Duplicate/out-of-order revocation events | Idempotent consumer, version monotonic |
| AS DB commit revoke nhưng producer crash | Outbox/recovery cuối cùng phát event |
| JWKS key bị thu hồi khẩn | RS ngừng chấp nhận token ký bằng key theo incident plan |
| RS vẫn cache compromised signing key | Node bị đánh dấu stale hoặc fail closed theo policy |
| Client nhận 200 revocation endpoint | Không mặc định tuyên bố mọi RS đã chặn |
| API gateway được bypass | Backend vẫn enforce trust/resource policy |
| OIDC logout chỉ xóa SSO cookie | Test chứng minh access token lifecycle riêng |
| User/admin bấm logout all | Phạm vi session/grant/token và SLA đo được |
| Secret/JWT raw bị log trong request/revoke event | Security test thất bại |
| Token của issuer khác bị gửi tới AS bất kỳ | Không fan-out, không exfiltrate token |
| High-risk refund đã authorize trước revoke nhưng commit sau | Hành vi in-flight đúng contract |

### 25.1. Test theo các tầng

**Unit:** JWT validator với `iss`, `aud`, `exp`, `jti`, negative cache TTL, version comparison, HMAC encoding.

**Integration với AS:** RFC 7009 revocation, refresh-token family rotation, introspection `active` và caller authentication.

**Resource Server:** Spring Security filter chain, denylist lookup, token purpose, DPoP/mTLS binding, scope/tenant/object ownership.

**Distributed systems:** nhiều RS/AS instances, database/Redis failover, event outbox/broker, event ordering, JWKS cache refresh, partitions.

**Incident drills:** revoke thật một JWT test còn hạn, đo từ AS commit đến **request cuối cùng bị từ chối ở từng region**, thử lỗi network và store.

**Business transaction:** race giữa revoke và commit nghiệp vụ nhạy cảm; bảo đảm luật về hành động in-flight.

### 25.2. Không chỉ kiểm tra endpoint revoke trả 200

Một test yếu:

~~~text
POST /revoke -> 200 => PASS
~~~

Một test có ích hơn:

~~~text
1. Phát JWT A, TTL còn dài hơn 5 phút.
2. Gọi RS bằng A trước revoke -> behavior hợp lệ theo scope.
3. Gửi revoke, đợi authoritative commit.
4. Gọi lại từng RS/region bằng A trước exp.
5. Ghi chính xác thời điểm bắt đầu bị chặn.
6. Mất broker/AS/store và thử lại theo fail-closed policy.
7. Kiểm cache expiry, key rotation và token loại khác.
8. So thời gian thực tế với revocation SLA đã ký.
~~~

Không dùng production tokens làm fixtures; giữ test credentials trong môi trường cô lập và redact test logs.

## 26. Checklist production cho self-contained token revocation

1. **Định nghĩa đối tượng revoke:** access token, refresh token/family, OAuth grant, session, user/client hay quyền tenant.
2. **Định nghĩa guarantee:** ngừng phát mới, bounded expiry window, gần real-time, hay online per-request; nêu rõ tối đa độ trễ và in-flight semantics.
3. **JWT validation đầy đủ:** signature/algorithm allowlist, trusted `iss`, đúng `aud`, `exp`, `nbf`, token profile/type.
4. **Access token TTL phù hợp risk:** không dùng token sống lâu chỉ để tránh refresh; đo tải AS/latency và clock skew.
5. **Refresh token an toàn:** secure storage, rotation hoặc sender constraint cho public clients theo policy, revoke family khi reuse.
6. **Biết giới hạn RFC 7009:** HTTP 200 không chứng minh RS chặn ngay; xác định access-token revocation support của AS.
7. **Denylist có danh tính an toàn:** trusted issuer + `jti`/fingerprint, HMAC key riêng, TTL đến khi token không còn được chấp nhận.
8. **Không đọc `jti` trước verify JWT:** tránh nhầm issuer, token purpose và key space.
9. **Session/grant versions có authority:** RS phải tra current version hoặc nhận event; claim đơn độc không tự thay đổi.
10. **Event-driven được thiết kế bền vững:** outbox, idempotence, ordering/version, consumer watermark, resync.
11. **Introspection được bảo vệ:** RS caller auth, per-RS disclosure policy, đúng audience/token type, no token oracle.
12. **Cache có upper bound:** cache TTL không vượt `exp`, revocation SLA; không tái sử dụng stale `active=true` vô hạn.
13. **Fail closed khi state bắt buộc thiếu:** AS timeout/Redis failover/broker partition không chuyển thành allow.
14. **Key rotation với runbook:** JWKS caching, alg/key trust, emergency compromise và blast radius.
15. **Sender binding theo nhu cầu:** DPoP/mTLS giảm replay của bản sao token nhưng không thay revoke.
16. **Bảo vệ object-level authorization:** scope/tenant/ownership và entitlement tại thời điểm truy cập.
17. **Tách OIDC logout và token revoke:** browser session, OP SSO, BFF cookie, refresh grant và JWT RS có vòng đời riêng.
18. **Phân vùng trust domains:** per issuer/RS/token type; không chia một danh sách `jti` thiếu namespace.
19. **Credential/telemetry an toàn:** không log raw bearer/refresh tokens hoặc JWS assertions; audit event có ID không dùng làm secret.
20. **Đo được hiệu lực revoke:** metrics từ AS commit → RS deny, p95/p99/max, alert khi state lag.
21. **Kiểm thử trong lúc mất kết nối:** cache invalidation, network partition, version lookup failure, key withdrawal.
22. **Runbook sự cố:** token theft, signing-key compromise, client credential compromise, account/tenant breach.
23. **Không hứa quá mức:** tài liệu kỹ thuật và UI mô tả chính xác thời gian và phạm vi vô hiệu token đã cấp.

## 27. Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint thu hồi token, refresh/access-token support và response semantics.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký bảo vệ JWT, `alg`, `kid` và protected headers.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token type/profile, issuer/audience/time/scope validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, caller authentication, token metadata và caching considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth grants, access token, refresh token và client roles.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token replay, refresh token protection, sender constraints và security guidance.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer access tokens, transport, `invalid_token` và `insufficient_scope`.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP-bound tokens, proof `jti` và anti-replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens và client authentication.
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): trusted issuer/discovery metadata.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource audience và scope.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và OP/client authentication/session distinctions.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): session logout signaling, không tự thay access token revocation.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature/claims validators và cấu hình Spring.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection integration.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): access-token scope không thay quyền trên record.

**Ghi nhớ:** **Self-contained JWT cho phép Resource Server xác minh token độc lập, nhưng không thể tự biết một sự kiện thu hồi xảy ra sau lúc token được ký.** Thu hồi refresh token/grant ở AS **ngăn cấp token mới**, không tự làm mọi JWT access token đang lưu trong client/attacker hết hiệu lực. Muốn giới hạn cửa sổ rủi ro, cần **`exp` ngắn** và khi nghiệp vụ đòi hỏi phải bổ sung **denylist theo token ID, session/grant version, introspection online hoặc event propagation có kiểm soát**, đồng thời xử lý **cache, clock skew, mất kết nối và tính nhất quán phân tán**. DPoP/mTLS giúp giảm replay nhưng không thay revocation; RS luôn phải kiểm **issuer, audience, token type, scope, tenant và quyền trên tài nguyên**.
