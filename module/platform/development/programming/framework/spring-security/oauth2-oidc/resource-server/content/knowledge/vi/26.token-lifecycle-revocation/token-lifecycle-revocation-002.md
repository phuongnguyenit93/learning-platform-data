# Token tự chứa và giới hạn thu hồi tức thời khi xác minh cục bộ

**Self-contained access token** cho phép Resource Server xác minh token bằng dữ liệu nằm trong token và khóa tin cậy, thay vì hỏi Authorization Server về trạng thái của từng token trên mỗi request. Một signed JWT có thể mang issuer, audience, subject, scope và thời hạn; Resource Server kiểm chữ ký, kiểm claims rồi tạo Authentication tại chỗ.

Đổi lại, có một giới hạn quan trọng: **xác minh cục bộ không tự biết Authorization Server vừa thu hồi token**. Nếu không có một nguồn trạng thái bổ sung, JWT đã phát hành thường tiếp tục hợp lệ tới khi hết hạn, kể cả khi người dùng logout, tài khoản bị khóa hoặc quản trị viên yêu cầu revoke.

Đây là sự đánh đổi giữa độ độc lập, latency và khả năng thu hồi:

- **Local JWT validation** giảm network round trip và phụ thuộc runtime vào Authorization Server.
- **Online introspection** có thể phản ánh trạng thái token mới hơn, nhưng tăng latency và phụ thuộc availability của AS.
- **jti denylist, token version và revocation events** rút ngắn thời gian vô hiệu hóa JWT, nhưng đưa trạng thái dùng chung trở lại hệ thống.
- **Access token TTL ngắn và refresh token rotation** giới hạn thời gian quyền cũ còn hiệu lực, nhưng không phải thu hồi tức thời.

Bài học này giải thích giới hạn của token tự chứa, các cách thiết kế vòng đời và revocation, cấu hình Spring Security xác minh JWT cục bộ và lựa chọn phù hợp khi nghiệp vụ đòi hỏi thu hồi nhanh.

## 1. Token tự chứa là gì?

Một **self-contained token** mang đủ dữ liệu để Resource Server xác minh và diễn giải token mà không cần gọi Authorization Server để hỏi trạng thái active của từng token.

JWT là định dạng phổ biến. Một JWT thường có ba phần Base64URL:

~~~text
header.payload.signature
~~~

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "token-8f21"
}
~~~

| Claim | Ý nghĩa |
|---|---|
| **iss** | Issuer phát hành token |
| **sub** | Subject, chủ thể mà token đại diện |
| **aud** | Audience/resource được phép nhận token |
| **iat** | Thời điểm token được phát hành |
| **nbf** | Thời điểm token bắt đầu có hiệu lực |
| **exp** | Thời điểm token hết hiệu lực |
| **jti** | JWT ID, định danh token |
| **scope** | Phạm vi quyền được cấp theo contract của issuer |
| **client_id** | Client được cấp token nếu profile sử dụng |

Các claim thời gian dùng NumericDate, tính bằng giây kể từ Unix epoch.

### 1.1. JWT không đồng nghĩa với dữ liệu được mã hóa

JWT có thể được bảo vệ bằng các dạng:

- **JWS**: ký hoặc xác thực tính toàn vẹn. Payload thường vẫn đọc được sau Base64URL decoding.
- **JWE**: mã hóa nội dung để người không có khóa không đọc được.
- Nested JWT: kết hợp các lớp ký và mã hóa theo thiết kế.

Resource Server phổ biến thường nhận signed JWT access token và xác minh JWS signature. **Chữ ký chứng minh nội dung không bị sửa trái phép và được ký bởi khóa được tin cậy; nó không chứng minh token chưa bị thu hồi.**

Không đưa thông tin bí mật vào payload JWT chỉ vì token được ký. Nếu không mã hóa, người nắm giữ token có thể đọc claims.

### 1.2. Self-contained không bắt buộc phải verify offline

JWT có thể được xác minh cục bộ, nhưng hệ thống vẫn có thể gọi introspection endpoint để kiểm tra trạng thái hoặc policy động. Ngược lại, opaque token thường cần introspection nhưng có thể cache kết quả.

Cần phân biệt:

- **Token format**: JWT hay opaque.
- **Validation strategy**: local verification hay online introspection.
- **Revocation strategy**: cách thông báo token đã bị vô hiệu hóa.
- **Authorization strategy**: cách kiểm quyền endpoint và tài nguyên.

Các khái niệm này liên quan nhưng không thay thế nhau.

## 2. Local JWT validation hoạt động ra sao?

Với signed JWT, Resource Server thường:

1. Nhận Authorization Bearer token.
2. Đọc header để xác định key identifier như kid.
3. Chọn khóa từ nguồn tin cậy đã cấu hình, thường là JWKS.
4. Xác minh chữ ký bằng thuật toán được phép.
5. Kiểm issuer, audience, exp, nbf và các validators khác.
6. Chuyển claims đã xác minh thành Authentication và authorities.
7. Áp dụng authorization policy cho request.

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant R as Resource Server
    participant K as JWKS / Key Cache
    C->>R: Authorization: Bearer signed JWT
    R->>R: Parse header và claims
    R->>K: Lấy public key theo kid nếu cần
    K-->>R: Trusted verification key
    R->>R: Verify signature và claims
    R->>R: Map scope thành authorities
    R-->>C: Cho phép hoặc từ chối request
~~~

Khi public key đã có trong cache, việc xác minh từng request có thể diễn ra **không cần introspection request tới AS**.

Local validation không có nghĩa ứng dụng không bao giờ truy cập mạng: discovery, JWKS retrieval, key rotation và cache refresh vẫn có thể cần kết nối tới issuer. Điểm khác biệt là **không hỏi trạng thái active/revoked của từng token trên mỗi request**.

### 2.1. Lợi ích

- Giảm network round trip trên đường đi xác thực.
- Ít phụ thuộc latency/availability của AS khi khóa đã được cache.
- Public keys có thể được dùng bởi nhiều Resource Server instances.
- Giảm tải introspection endpoint.
- Xác minh chữ ký độc lập tại từng Resource Server.

### 2.2. Những gì chữ ký không thể cho biết

Một JWT có signature đúng vẫn có thể:

- Đã bị user logout hoặc token bị revoke.
- Thuộc về user vừa bị khóa.
- Có scope cũ trước khi quyền thay đổi.
- Được phát hành cho audience khác.
- Thuộc tenant khác.
- Bị đánh cắp và đang được replay trước exp.
- Được ký bằng key vẫn còn trong cache nhưng đã bị thu hồi khẩn cấp.

Chữ ký xác minh nội dung token với khóa được tin cậy. Nó không tự cập nhật những sự kiện xảy ra **sau khi token được phát hành**.

## 3. Giới hạn thu hồi tức thời

Giả sử Authorization Server phát hành:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "token-8f21"
}
~~~

Resource Server xác minh chữ ký và claims lúc 10:00. Lúc 10:02, quản trị viên revoke token hoặc khóa tài khoản. Nếu Resource Server chỉ dùng public key và dữ liệu trong JWT, nó không có thông tin về sự kiện mới đó.

~~~mermaid
sequenceDiagram
    participant U as User
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>AS: Xin access token
    AS-->>U: JWT exp=10:30
    U->>RS: Request với JWT
    RS->>RS: Verify signature và exp
    RS-->>U: 200 OK
    Note over AS: 10:02: Admin revoke token
    U->>RS: Request lại JWT cũ
    RS->>RS: Signature đúng, exp chưa tới
    RS-->>U: Có thể vẫn 200 OK
~~~

### 3.1. Không thể suy ra revoke từ chữ ký

Token đã ký là một thông điệp bất biến. Thay đổi trạng thái ở AS không sửa được payload hoặc chữ ký đã phát hành.

Local validator có thể kiểm signature, issuer, audience, exp, nbf và claims. Nhưng nếu chữ ký vẫn đúng, exp chưa tới và claims không đổi, **validator không thể tự biết một sự kiện revoke chưa được truyền tới nó**.

Đây là giới hạn thông tin, không phải lỗi riêng của Spring Security.

### 3.2. Stateless là một trade-off

JWT local verification giúp Resource Server không cần lưu trạng thái cho từng token. Nhưng nếu nghiệp vụ yêu cầu:

- Logout phải vô hiệu hóa access token ngay.
- Khóa user phải ảnh hưởng mọi token hiện tại.
- Thu hồi quyền quản trị phải có hiệu lực rất nhanh.
- Thiết bị bị mất phải bị ngắt quyền trên mọi API.
- Token bị lộ phải không thể tiếp tục sử dụng.

thì **local validation hoàn toàn stateless không đáp ứng yêu cầu đó**.

Muốn biết sự kiện revoke, Resource Server phải nhận thêm thông tin: truy vấn trạng thái, nhận sự kiện, kiểm version hoặc dùng một cơ chế proof/state khác.

## 4. Expiration giới hạn thời gian, không phải revoke tức thời

Claim **exp** xác định thời điểm token không còn được chấp nhận theo policy.

~~~json
{
  "sub": "user-123",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

Token có tuổi thọ 5 phút trong ví dụ. Sau exp, validator từ chối token, có thể áp dụng clock skew theo cấu hình.

**Access token TTL ngắn** làm giảm khoảng thời gian token cũ tiếp tục được dùng sau revoke, nhưng không xóa khoảng thời gian đó.

| TTL access token | Lợi ích | Chi phí |
|---|---|---|
| Ngắn | Giảm thời gian quyền cũ còn hiệu lực | Refresh thường xuyên, tăng tải AS |
| Trung bình | Cân bằng latency và revocation window | Cần thiết kế refresh/logout |
| Dài | Ít refresh, giảm số lần cấp token | Token bị lộ hoặc revoke có thể còn dùng lâu |

Không có một TTL đúng cho mọi hệ thống. Cần xét độ nhạy cảm dữ liệu, loại thao tác, tải AS, UX, refresh token security và yêu cầu logout.

### 4.1. Clock skew có thể kéo dài cửa sổ chấp nhận

Resource Server thường cho phép một khoảng lệch đồng hồ nhỏ để tránh từ chối token hợp lệ do clock drift. Khoảng lệch này có thể làm token được chấp nhận trong biên thời gian gần exp/nbf.

Đồng bộ clock giữa AS, Resource Server và hạ tầng. Đừng đặt clock skew quá rộng để che lỗi đồng hồ, vì nó cũng mở rộng thời gian chấp nhận token.

### 4.2. TTL không thay thế audience và scope validation

Token chỉ sống hai phút nhưng audience sai vẫn phải bị từ chối. Token còn hạn nhưng thiếu scope write vẫn phải bị từ chối.

**Expiration là một điều kiện cần, không phải toàn bộ authorization policy.**

## 5. Refresh token và access token có vòng đời khác nhau

Một kiến trúc phổ biến:

~~~mermaid
flowchart TD
    L[User đăng nhập] --> AS[Authorization Server]
    AS --> AT[Short-lived access token]
    AS --> RT[Refresh token]
    AT --> API[Resource Server]
    RT --> REF[Token endpoint / refresh]
    REF --> NEW[Access token mới]
    NEW --> API
    RV[Logout hoặc revoke refresh token] --> REF
~~~

Access token được gửi tới Resource Server để truy cập API. Refresh token được gửi tới Authorization Server để lấy access token mới và thường có vòng đời/bảo vệ riêng.

### 5.1. Revoke refresh token không tự xóa access JWT cũ

Giả sử access token còn hạn 10 phút và refresh token có thời hạn dài hơn. User logout lúc phút thứ hai.

AS có thể revoke refresh token để client không lấy access token mới. Nhưng JWT access token đã phát hành vẫn có chữ ký hợp lệ và có thể tiếp tục được Resource Server chấp nhận tới exp nếu không có cơ chế revocation khác.

**Ngừng cấp token mới khác với vô hiệu hóa token đã cấp.**

### 5.2. Refresh token rotation

Một quy trình rotation điển hình:

1. Client gửi refresh token hiện tại.
2. AS kiểm tra token.
3. Server cấp access token mới và refresh token mới.
4. Refresh token cũ bị vô hiệu hóa.
5. Nếu token cũ bị dùng lại, AS có thể phát hiện reuse và revoke token family theo policy.

Rotation giảm rủi ro replay refresh token bị đánh cắp, nhưng không tự thu hồi mọi access JWT đã cấp trước đó.

### 5.3. Logout ở client không đồng nghĩa revoke ở server

Xóa token khỏi memory, storage hoặc cookie giúp client ngừng sử dụng token. Một bản sao token bị đánh cắp vẫn có thể được dùng ở nơi khác đến khi exp hoặc Resource Server từ chối bằng cơ chế revocation.

OIDC logout chủ yếu xử lý session tại OP/RP theo giao thức và cấu hình. **Không mặc định mọi Resource Server lập tức biết access JWT đã bị logout.**

## 6. Các chiến lược rút ngắn cửa sổ revocation

| Chiến lược | Cách hoạt động | Độ mới của revoke | Chi phí/chú ý |
|---|---|---|---|
| **Short-lived access token** | Chờ token hết exp | Gần TTL còn lại | Không tức thời |
| **Opaque token + introspection** | Hỏi AS trạng thái active | Gần realtime theo request/cache | Network latency và availability |
| **JWT denylist theo jti** | Kiểm token ID bị revoke | Theo tốc độ cập nhật store | Cần state lookup |
| **User/session token version** | So version trong JWT với state hiện tại | Theo độ mới của state | Cần lookup/cache |
| **Revocation event push** | AS phát sự kiện cho Resource Servers | Theo propagation delay | Event loss/replay/consistency |
| **Signing-key removal** | Bỏ trust key đã ký token | Sau khi JWKS cache cập nhật | Ảnh hưởng nhiều token |
| **Online introspection không cache** | Hỏi AS mỗi request | Gần trạng thái AS hiện tại | Tăng phụ thuộc AS |

Không có phương pháp nào vừa hoàn toàn offline, vừa không có state, vừa biết mọi sự kiện revoke ngay lập tức. **Thông tin revoke phải đến được nơi quyết định access.**

## 7. Opaque token và introspection khi cần trạng thái mới

Opaque token thường không mang claims để Resource Server tự xác minh. Resource Server gọi introspection endpoint theo RFC 7662:

~~~http
POST /oauth2/introspect
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

Authorization Server có thể trả:

~~~json
{
  "active": false
}
~~~

Nếu AS đã cập nhật trạng thái revoke, lần introspection tiếp theo có thể thấy active=false.

### 7.1. Introspection giảm revocation lag nhưng thêm dependency

Ưu điểm:

- AS là nguồn trạng thái tập trung.
- Có thể phát hiện token revoked/inactive.
- Quyền/trạng thái thay đổi không cần chờ JWT exp.
- Resource Server không phải tự quản lý denylist từng token nếu AS cung cấp trạng thái authoritative.

Chi phí:

- Mỗi request có thể tạo một HTTP round trip.
- AS trở thành dependency trên đường đi authentication.
- Network failure ảnh hưởng khả năng xác minh.
- Cần timeout, connection pool, retry policy và monitoring.
- Introspection cache có thể làm chậm phát hiện revocation.

### 7.2. Cache introspection tạo cửa sổ chấp nhận cũ

Ví dụ cache active=true trong 60 giây:

~~~text
10:00:00  introspection -> active=true, cache 60s
10:00:10  AS revoke token
10:00:20  Resource Server cache hit active=true
10:01:00  cache hết hạn
10:01:01  introspection -> active=false
~~~

Revocation lag có thể xấp xỉ TTL cache cộng propagation/network delays, tùy invalidation strategy.

**Cache không chỉ tối ưu performance; nó thay đổi security semantics.**

## 8. Denylist theo jti: thu hồi một token cụ thể

JWT có thể chứa claim **jti** làm identifier. Khi revoke token, AS hoặc hệ thống quản trị ghi nhận cặp issuer/token ID trong revocation store.

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "jti": "token-8f21",
  "exp": 1893456000
}
~~~

Resource Server sau khi verify chữ ký có thể kiểm:

~~~text
(iss, jti) có nằm trong revocation store không?
Có     -> từ chối
Không  -> tiếp tục authorization
~~~

### 8.1. Dùng issuer cùng jti

Dùng **issuer + jti** làm key giúp phân biệt token IDs giữa nhiều issuers. Không dùng raw JWT làm Redis key, metric tag hoặc log entry vì token là Bearer credential.

### 8.2. TTL của denylist entry

Entry thường chỉ cần tồn tại đến exp cộng biên clock skew/chính sách cleanup:

~~~text
revocation key: issuer-id + jti
expires at: token exp + allowed clock-skew margin
~~~

Giữ denylist vô thời hạn làm dữ liệu tăng không giới hạn; xóa quá sớm có thể khiến một node có clock drift hoặc cache khác vẫn chấp nhận token.

### 8.3. jti không tự tạo revocation

jti chỉ là định danh. Nếu Resource Server không kiểm nó với denylist hoặc trạng thái tương ứng, việc có jti trong JWT **không làm token tự bị revoke**.

Phải xác minh token trước khi tin jti. Không lấy claim từ raw JWT chưa verify làm căn cứ cấp quyền hoặc quyết định danh tính.

### 8.4. Denylist cục bộ và phân tán

| Store | Đặc điểm |
|---|---|
| In-memory per instance | Nhanh, nhưng chỉ biết entries của node đó và mất khi restart |
| Shared Redis/database | Nhiều instances thấy cùng state, nhưng cần lookup hoặc cache |
| Local cache + revocation events | Giảm remote lookup, có propagation lag |
| Distributed cache với invalidation | Có thể giảm lag, cần delivery/consistency |

Nếu chỉ lưu denylist trong RAM của một instance, replicas khác vẫn có thể chấp nhận token. Đây không phải revoke toàn cụm.

## 9. Token version và revoke theo user/session

Một JWT có thể chứa version:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "ver": 7,
  "exp": 1893456000
}
~~~

Hệ thống lưu version hiện tại:

~~~text
user-123 currentVersion = 7
~~~

Khi muốn revoke toàn bộ token hiện tại của user:

~~~text
user-123 currentVersion = 8
~~~

Resource Server so claim ver với version hiện tại. Nếu không bằng nhau, token bị từ chối.

### 9.1. Ưu điểm và chi phí

Một lần update có thể vô hiệu hóa nhiều token cùng user/session mà không cần ghi một entry cho từng jti.

Đổi lại:

- Cần state lookup hoặc cache.
- Version update phải lan tới Resource Servers.
- Phải phân biệt version toàn user, per-device session hoặc per-client.
- Node chưa nhận version mới có thể vẫn chấp nhận token cũ.
- Cache không thể giữ vô hạn nếu yêu cầu revoke nhanh.

Một claim version trong JWT mà không có nơi so sánh version hiện tại **không tạo ra khả năng thu hồi**.

### 9.2. Revoke theo iat cutoff

Một biến thể lưu thời điểm revoke:

~~~text
user-123 revokedAfter = 1893452500
~~~

Resource Server từ chối token nếu iat nhỏ hơn hoặc bằng revokedAfter.

Điều này có thể revoke tất cả token phát hành trước một thời điểm. Cần xác định clock skew, precision timestamp, issuer scope và việc token có iat bắt buộc hay không.

## 10. Revocation events: đẩy trạng thái tới Resource Servers

Một mô hình event-driven:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|TokenRevoked event| BUS[Message broker]
    BUS --> R1[Resource Server A local denylist]
    BUS --> R2[Resource Server B local denylist]
    BUS --> R3[Resource Server C local denylist]
    R1 --> API1[Local JWT validation]
    R2 --> API2[Local JWT validation]
    R3 --> API3[Local JWT validation]
~~~

Mỗi Resource Server cập nhật local denylist/cache. Request mới có thể được xác minh chữ ký và kiểm local state mà không gọi AS trực tiếp.

### 10.1. Event-driven không tự tức thời

Cửa sổ revoke phụ thuộc:

- Thời gian AS phát event sau khi commit.
- Broker delivery latency.
- Consumer processing delay.
- Cache update/invalidation.
- Node restart hoặc mất kết nối.
- Event duplicate, out-of-order hoặc mất.
- Replay/snapshot sau reconnect.

**Event push thường tạo eventual consistency** nếu không có cơ chế đồng bộ mạnh hơn. Đừng quảng cáo instant revocation nếu chưa định nghĩa và đo SLA propagation.

### 10.2. Event cần replay và idempotency

Ví dụ payload:

~~~json
{
  "eventType": "ACCESS_TOKEN_REVOKED",
  "issuer": "https://identity.example.com",
  "jti": "token-8f21",
  "expiresAt": 1893456000,
  "eventId": "evt-00421",
  "occurredAt": "2030-01-01T10:02:00Z"
}
~~~

Một triển khai thật cần:

- Xác thực nguồn event và bảo vệ transport.
- Event ID để xử lý idempotent.
- Ordering/key theo issuer, user hoặc session nếu cần.
- Replay hoặc snapshot sau reconnect.
- Deduplication và xử lý event cũ.
- TTL cleanup theo exp.
- Consumer lag metrics.
- Reconciliation khi local cache bị mất.

Không để event không xác thực có thể thêm hoặc xóa revocation entries tùy ý.

### 10.3. Khi event stream bị gián đoạn

Phải có policy:

- Fail closed với thao tác nhạy cảm nếu local revocation state không đủ mới.
- Hoặc tiếp tục local validation trong cửa sổ được chấp nhận và ghi nhận revocation lag.
- Hoặc chuyển sang online introspection khi local state không đáng tin, nếu AS còn khả dụng.
- Khi consumer reconnect, đồng bộ snapshot/offset trước khi tuyên bố node đã bắt kịp.

## 11. Signing-key rotation không phải cách revoke một token thông thường

JWT được ký bằng private key; Resource Server dùng public key tương ứng. Nếu AS bỏ public key cũ khỏi JWKS, token ký bằng key cũ có thể bị từ chối **sau khi Resource Server cập nhật key set**.

### 11.1. Rotation bình thường

1. Publish public key mới trong JWKS với kid mới.
2. Chờ Resource Servers có thể tải key mới.
3. Bắt đầu ký token bằng private key mới.
4. Giữ key cũ đủ lâu cho token cũ hết hạn cộng clock-skew/cache margin.
5. Bỏ key cũ sau thời gian chuyển tiếp.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant J as JWKS endpoint
    participant RS as Resource Server
    AS->>J: Publish public key K2
    RS->>J: Refresh JWKS
    J-->>RS: K1 và K2
    AS->>AS: Ký token mới bằng K2
    RS->>RS: Verify token kid=K2
    Note over AS,J: Token K1 hết hạn
    AS->>J: Remove public key K1
    RS->>J: Refresh JWKS
    J-->>RS: Chỉ còn K2
~~~

### 11.2. Emergency rotation khi private key bị compromise

Nếu private key bị lộ, AS phải ngừng ký bằng key đó, loại public key cũ khỏi nguồn trust và chuyển sang key mới. Tuy nhiên:

- Resource Servers có thể cache public key cũ.
- JWKS refresh không nhất thiết xảy ra ngay ở mọi node.
- Decoder có thể tiếp tục verify bằng cache cho tới khi refresh.
- Mọi token ký bằng key đó có thể bị ảnh hưởng, không chỉ token của một user.

Key removal có **blast radius lớn** và revocation lag do cache/propagation.

### 11.3. Không rotate key cho mỗi lần logout

Signing key thường phục vụ nhiều users/clients. Rotate key để revoke một token có thể làm invalid hàng loạt token khác và gây outage.

Dùng key rotation cho key lifecycle/compromise. Dùng jti, token version, introspection hoặc short TTL cho revoke hẹp hơn.

## 12. Spring Security xác minh JWT cục bộ

Spring Security Resource Server sử dụng **JwtDecoder** để verify signed JWT và các validators để kiểm claims.

Ví dụ Servlet configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://identity.example.com";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The required audience is missing",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );

        return decoder;
    }
}
~~~

Gắn vào Resource Server:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

Ví dụ giả định dependency Resource Server và phần cấu hình còn lại đã có.

### 12.1. Validator mặc định và custom policy

**JwtValidators.createDefaultWithIssuer(issuer)** kết hợp các validators mặc định của Spring Security, gồm timestamp validation và issuer validation theo release line. Audience validator ở ví dụ bổ sung kiểm tra token dành cho orders-api.

Tùy token profile, cần kiểm thêm:

- JWS algorithm allowlist.
- Audience/resource.
- Token type/profile, access token thay vì ID Token.
- Client/resource binding.
- Tenant và permission contract.
- Các claims bắt buộc khác.

Không đọc claim alg từ JWT header rồi tin nó như chính sách thuật toán. Key source và thuật toán phải được giới hạn bởi cấu hình tin cậy.

### 12.2. Local validation vẫn phụ thuộc key lifecycle

Khi dùng issuer discovery/JWKS, decoder có thể tải metadata hoặc public key từ endpoint tin cậy. Sau khi key đã cache, việc verify từng token không cần introspection. Khi gặp kid mới hoặc cache refresh, có thể vẫn có network activity.

Đó là **key distribution**, khác với việc hỏi trạng thái active của từng token.

## 13. jti denylist trong Spring Security

Một OAuth2TokenValidator có thể kiểm tra jti đã bị revoke sau khi JWT qua signature/claim validation.

Ví dụ đơn giản hóa cho Servlet:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

class LocalJtiRevocationValidator implements OAuth2TokenValidator<Jwt> {

    private final Set<String> revokedIds =
        ConcurrentHashMap.newKeySet();

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String tokenId = jwt.getId();
        String key = issuer + ":" + tokenId;

        if (tokenId != null && revokedIds.contains(key)) {
            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The access token has been revoked",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        }

        return OAuth2TokenValidatorResult.success();
    }

    public void revoke(String issuer, String tokenId) {
        revokedIds.add(issuer + ":" + tokenId);
    }
}
~~~

Đây là **in-memory demo**, không phải giải pháp production phân tán:

- Mỗi instance có set riêng.
- Restart làm mất entries.
- Không có event propagation.
- Không có TTL cleanup theo exp.
- Không revoke toàn user/session.
- Cần policy nếu token thiếu jti.

Production cần revocation store có lifecycle, TTL, namespace và consistency policy rõ.

### 13.1. Gắn validator vào decoder

~~~java
LocalJtiRevocationValidator revocationValidator =
    new LocalJtiRevocationValidator();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator,
        revocationValidator
    )
);
~~~

Validator chỉ phát hiện token revoked nếu entry đã được cập nhật tới instance đang xử lý request.

### 13.2. Synchronous validator và remote lookup

OAuth2TokenValidator trong Servlet là đồng bộ. Nếu mỗi request gọi Redis/database remote blocking, bạn đưa network lookup vào request path và có thể chiếm servlet threads.

- Local cache nhanh nhưng có propagation lag.
- Shared synchronous lookup có state mới hơn nhưng cần timeout, bulkhead và availability policy.
- Không gọi reactive Redis/WebClient rồi block() trong validator.

Nếu WebFlux cần revocation store reactive, hãy đặt check trong reactive authentication/conversion pipeline sau khi ReactiveJwtDecoder xác minh token, không ép publisher thành synchronous result.

## 14. WebFlux và revocation lookup bất đồng bộ

WebFlux dùng **ReactiveJwtDecoder** và **ReactiveAuthenticationManager**. Nếu revocation check cần truy vấn shared reactive store, không đặt blocking lookup trong event loop.

Mô hình:

~~~text
Bearer token
  -> ReactiveJwtDecoder
       -> verify signature, issuer, audience, timestamps
  -> Reactive revocation lookup
       -> revoked: reject authentication
       -> not revoked: build Authentication
  -> AuthorizationWebFilter
       -> scope/role/domain policy
~~~

Có thể dùng **JwtReactiveAuthenticationManager** với reactive converter hoặc custom ReactiveAuthenticationManager:

- Chỉ lookup revocation **sau khi JWT đã được decoder xác minh**.
- Key theo issuer + jti hoặc user/session version.
- Trả Mono lỗi nếu revoked.
- Propagate timeout/cancellation, không fail-open.
- Có bounded concurrency/cache/timeout cho state store.
- Không gọi block() hoặc subscribe() thủ công.

WebFlux không tự làm revocation nhanh hơn. Consistency của store và event propagation vẫn quyết định độ mới của trạng thái.

## 15. Token version và trạng thái user

Một JWT có thể chứa version:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "ver": 12,
  "exp": 1893456000
}
~~~

State hiện tại:

~~~json
{
  "subject": "user-123",
  "currentTokenVersion": 13,
  "enabled": false
}
~~~

Sau khi verify JWT, Resource Server có thể kiểm version và trạng thái user. Nếu version không khớp hoặc user disabled, từ chối.

Đây là **stateful check**. Nó có thể revoke nhiều tokens cùng user/session, nhưng cần:

- State lookup/cache.
- Propagation update tới mọi nodes.
- Phân biệt version toàn user, per-device session hoặc per-client.
- Cache TTL phù hợp revocation SLA.
- Policy khi store unavailable.

Một claim version trong JWT mà không có nơi so sánh version hiện tại **không tạo ra khả năng thu hồi**.

### 15.1. Revoke theo iat cutoff

Một biến thể lưu revokedAfter cho user:

~~~text
user-123 revokedAfter = 1893452500
~~~

Resource Server từ chối token nếu iat nhỏ hơn hoặc bằng thời điểm đó. Cần xử lý clock skew, timestamp precision, issuer scope và yêu cầu iat có mặt.

### 15.2. Revoke token khác revoke session

- **Single token**: một jti.
- **Single device/session**: mọi token của session/device.
- **All user sessions**: tất cả tokens của user.
- **Client/application**: tokens cấp cho client.
- **Issuer/key**: tất cả token ký bởi key hoặc issuer bị ảnh hưởng.

Chọn đúng phạm vi state. User-level version có thể logout tất cả thiết bị; jti denylist cần quản lý nhiều entries nếu revoke toàn bộ user.

## 16. Revocation events: đẩy trạng thái tới Resource Servers

Authorization Server có thể phát sự kiện khi token, user hoặc session bị revoke:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|TokenRevoked event| BUS[Message broker]
    BUS --> R1[Resource Server A local denylist]
    BUS --> R2[Resource Server B local denylist]
    BUS --> R3[Resource Server C local denylist]
    R1 --> API1[Local JWT validation]
    R2 --> API2[Local JWT validation]
    R3 --> API3[Local JWT validation]
~~~

Các nodes cập nhật local cache/denylist. Request mới có thể được xác minh chữ ký và kiểm local state mà không gọi AS trực tiếp.

### 16.1. Event push không tự tức thời

Cửa sổ revoke phụ thuộc:

- Thời gian phát event sau khi AS commit.
- Broker delivery latency.
- Consumer processing delay.
- Cache update/invalidation.
- Node restart hoặc mất kết nối.
- Event duplicate, out-of-order hoặc mất.
- Replay/snapshot sau reconnect.

Event push thường tạo **eventual consistency**. Đừng quảng cáo instant revocation nếu chưa đo propagation SLA.

### 16.2. Event cần xác thực, replay và idempotency

Payload minh họa:

~~~json
{
  "eventType": "ACCESS_TOKEN_REVOKED",
  "issuer": "https://identity.example.com",
  "jti": "token-8f21",
  "expiresAt": 1893456000,
  "eventId": "evt-00421",
  "occurredAt": "2030-01-01T10:02:00Z"
}
~~~

Một triển khai thật cần:

- Xác thực nguồn event và bảo vệ transport.
- Event ID để xử lý idempotent.
- Ordering theo issuer/user/session nếu cần.
- Replay hoặc snapshot sau reconnect.
- Deduplication và xử lý event cũ.
- TTL cleanup theo exp.
- Consumer lag metrics.
- Reconciliation khi local cache bị mất.

Nếu event stream bị gián đoạn, phải có policy: fail closed cho thao tác nhạy cảm, chấp nhận một cửa sổ stale có đo lường, hoặc chuyển sang online introspection. Khi consumer reconnect, đồng bộ state trước khi tuyên bố node đã bắt kịp.

## 17. Signing-key rotation và JWKS cache

JWT được ký bằng private key; Resource Server dùng public key tương ứng. Claim/header kid giúp chọn key trong JWKS, nhưng **kid không tự chứng minh key đáng tin**. JWKS URI phải thuộc issuer đã cấu hình.

### 17.1. Rotation bình thường

1. Publish public key mới trong JWKS.
2. Chờ Resource Servers có thể tải key.
3. AS bắt đầu ký token bằng private key mới.
4. Giữ key cũ đủ lâu cho token cũ hết hạn cộng clock-skew/cache margin.
5. Bỏ key cũ sau thời gian chuyển tiếp.

### 17.2. Emergency rotation

Nếu private key bị compromise, AS phải ngừng ký bằng key đó, loại public key khỏi trust source và chuyển sang key mới. Nhưng Resource Servers có thể cache key cũ, nên việc từ chối không nhất thiết xảy ra ngay.

Bỏ key có thể ảnh hưởng **mọi token** ký bằng key đó, không chỉ một user. Đây là blast radius lớn và cần phối hợp cache refresh/propagation.

### 17.3. Không rotate key để revoke một token

Signing key thường phục vụ nhiều users/clients. Rotate key mỗi lần logout có thể làm invalid hàng loạt tokens và gây outage. Dùng key rotation cho key lifecycle/compromise; dùng jti, token version, introspection hoặc short TTL cho revoke hẹp hơn.

## 18. RFC 7009 Token Revocation Endpoint

OAuth 2.0 Token Revocation theo RFC 7009 định nghĩa endpoint để client yêu cầu AS revoke token.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<token-to-revoke>&token_type_hint=access_token
~~~

Endpoint có thể nhận access token hoặc refresh token theo policy của AS.

### 18.1. Response thành công không chứng minh mọi Resource Server đã biết revoke

RFC 7009 được thiết kế để client không dễ dò xem token có hợp lệ hay không; server thường phản hồi thành công cả khi token đã invalid hoặc không được nhận diện theo semantics của RFC.

Ngay cả khi AS đã xử lý revoke:

- Resource Server dùng online introspection có thể thấy active=false ở lần kiểm tiếp theo.
- Resource Server local JWT verification thuần có thể tiếp tục chấp nhận token tới exp.
- Resource Server có denylist/event integration có thể từ chối sau khi state truyền tới.
- Resource Server dùng cache có thể còn kết quả cũ.

**Gọi revocation endpoint không tự tạo cơ chế truyền trạng thái tới mọi Resource Server.**

### 18.2. Revoke refresh token và access token liên quan

AS có thể quản lý token family và quan hệ refresh/access tokens. Revoke refresh token ngăn cấp mới; AS cũng có thể revoke access tokens liên quan theo policy. Nhưng client/Resource Server không được giả định mọi AS có cùng hành vi. Cần kiểm tài liệu AS và cách Resource Server nhận biết trạng thái.

## 19. OIDC logout không tự vô hiệu hóa mọi access JWT

OIDC có RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout tùy hỗ trợ.

Những cơ chế này chủ yếu xử lý session tại OP/RP. Một API chỉ xác minh JWT offline **không tự nhận thông báo logout** trừ khi được tích hợp thêm.

Nếu yêu cầu logout từ portal phải làm API từ chối token cũ nhanh, cần thiết kế một trong các cách:

- Opaque token + introspection.
- jti denylist/shared revocation store.
- User/session version check.
- Back-channel hoặc event propagation tới Resource Servers.
- Access token TTL ngắn nếu chấp nhận cửa sổ còn lại.

Không nhầm **RP session logout** với **access token revocation ở mọi Resource Server**.

## 20. Proof-of-possession giảm replay nhưng không thay thế revocation

Bearer token có thể được sử dụng bởi bất kỳ bên nào nắm giữ token. Nếu token bị đánh cắp, attacker có thể replay tới khi token hết hạn hoặc bị từ chối.

Các biện pháp giảm replay:

- **DPoP**: proof-of-possession gắn request/token với khóa client theo RFC 9449.
- **Mutual TLS-bound access token**: gắn token với certificate theo RFC 8705.
- TLS, secure token storage và chống XSS.
- Sender-constrained token validation.

Proof-of-possession trả lời: “request có bằng chứng sở hữu khóa/certificate liên quan không?”. Revocation trả lời: “token hoặc session này còn được phép sử dụng không?”.

Token đã revoke vẫn phải bị từ chối dù proof-of-possession hợp lệ. Token chưa revoke nhưng bị đánh cắp sẽ khó replay hơn nếu sender constraint được triển khai đúng.

## 21. Claims và quyền có thể trở nên cũ

JWT có thể chứa:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "department": "finance",
  "role": "APPROVER",
  "exp": 1893456000
}
~~~

Sau khi phát hành, user có thể chuyển phòng ban, role bị thu hồi, account bị khóa, tenant bị disable hoặc policy thay đổi. Nếu Resource Server chỉ kiểm claims trong token, nó có thể dùng authorization data cũ đến exp.

### 21.1. Tách quyền tĩnh và quyền động

- Quyền ít thay đổi, token TTL ngắn: có thể đưa vào access token.
- Quyền cần cập nhật nhanh: kiểm policy/entitlement service.
- Quyền trên bản ghi cụ thể: kiểm trong domain/service layer.
- User/session cần revoke: kiểm version/status store hoặc introspection.

Không đưa mọi dữ liệu nghiệp vụ vào JWT chỉ để tránh database lookup. Token càng chứa nhiều quyền động, nguy cơ stale authorization càng lớn.

### 21.2. Kiểm lại quyền cho thao tác nhạy cảm

Với chuyển tiền, phê duyệt hoặc xóa tài nguyên, JWT còn hạn và có scope rộng chưa chắc đủ. Service có thể cần kiểm user active, tenant, transaction limit, approval state, ownership và MFA freshness.

Authentication token là một bằng chứng, không thay thế mọi domain rule.

## 22. Kiểm thử local validation và revocation

### 22.1. Test JWT validation

Dùng JWT ký bằng test key để kiểm:

- Signature đúng, issuer/audience đúng, exp còn hạn: có thể authenticate.
- Signature sai: từ chối.
- Issuer sai: từ chối.
- Audience sai: từ chối.
- exp đã qua ngoài clock skew: từ chối.
- nbf ở tương lai ngoài clock skew: từ chối.
- Algorithm không được phép: từ chối.

### 22.2. Chứng minh giới hạn local revocation

Một integration test hữu ích:

1. Phát JWT có exp còn xa.
2. Gửi request tới Resource Server chỉ local-verify và xác nhận thành công.
3. Revoke token ở AS nhưng không cập nhật Resource Server.
4. Gửi lại token cũ.
5. Quan sát Resource Server vẫn có thể chấp nhận vì signature/claims chưa đổi.
6. Cập nhật denylist hoặc chuyển sang introspection.
7. Gửi lại token và xác nhận bị từ chối.

Test này cho thấy **revocation ở issuer và revocation visibility tại Resource Server là hai việc khác nhau**.

### 22.3. Test denylist propagation

Với nhiều instances:

- Gửi token hợp lệ qua node A và B.
- Revoke jti trong store.
- Xác nhận cả hai nodes thấy state mới theo SLA.
- Mô phỏng broker disconnect/node restart.
- Kiểm replay/snapshot reconciliation.
- Kiểm TTL cleanup theo exp và clock skew.
- Đảm bảo event duplicate idempotent.
- Đảm bảo event không xác thực không thay đổi denylist.

### 22.4. Test cache lag

Nếu introspection/revocation state được cache:

- Revoke ngay sau cache hit.
- Đo thời gian token cũ còn được chấp nhận.
- Kiểm invalidation event.
- Kiểm cache backend outage.
- Kiểm fail-open/fail-closed.
- Kiểm TTL không vượt exp.

### 22.5. Test key rotation

- Token K1 được chấp nhận khi K1 còn trong JWKS.
- K2 được publish trước khi AS dùng K2.
- Token kid=K2 được xác minh sau refresh.
- Token K1 tiếp tục hoạt động trong overlap window bình thường.
- Sau khi K1 bị remove và Resource Server refresh key set, token K1 bị từ chối.
- Với emergency rotation, đo cache invalidation/propagation và blast radius.

Dùng test private/public keys và JWKS server; không dùng decoder mock để kết luận key cache production hoạt động đúng.

## 23. Những hiểu lầm thường gặp

**“JWT đã ký thì không thể bị revoke.”** Có thể revoke bằng state, introspection, event hoặc key policy; local verification thuần không tự thấy sự kiện.

**“Logout xóa token khỏi browser nên token đã chết.”** Bản sao token ở nơi khác có thể tiếp tục dùng đến exp nếu không có revocation mechanism.

**“Revoke refresh token làm access JWT cũ mất hiệu lực ngay.”** Không nhất thiết; refresh revoke chủ yếu ngăn cấp token mới.

**“Có jti là tự động revoke được.”** jti chỉ định danh; cần store/check.

**“Bỏ key khỏi JWKS là revoke đúng một user.”** Có thể ảnh hưởng mọi token ký bằng key đó và phụ thuộc cache propagation.

**“Introspection luôn tức thời.”** Cache, network, AS replication và propagation có thể làm kết quả cũ.

**“Short TTL là instant revoke.”** TTL giới hạn cửa sổ theo exp/clock skew, không phải zero lag.

**“Event bus phát revoke là mọi node đã biết.”** Phải kiểm consumer lag, missed events, replay và reconnect.

**“DPoP/mTLS thay thế revocation.”** Chúng giảm replay, không tự cung cấp trạng thái revoke.

**“Stateless nghĩa không thể kiểm quyền động.”** Có thể lookup state, nhưng khi đó quyết định không còn hoàn toàn stateless.

**“Request đang chạy tự rollback khi token bị revoke.”** Revocation thường ảnh hưởng quyết định tiếp theo; tác vụ đang chạy cần cancellation/transaction policy riêng.

## 24. Quy trình thiết kế vòng đời và revocation

**Bước 1 — Phân loại token.** JWT signed access token, opaque access token, ID Token, refresh token hay token nội bộ? Không dùng ID Token như access token.

**Bước 2 — Chọn validation strategy.** Local JWT validation, online introspection hay local validation kết hợp state lookup/event.

**Bước 3 — Định nghĩa revocation SLA.** Revoke một token, một session, một user, một client hay một signing key? Chấp nhận lag bao nhiêu?

**Bước 4 — Chọn access token TTL.** Cân bằng thời gian quyền cũ còn hiệu lực với refresh traffic và UX.

**Bước 5 — Thiết kế refresh lifecycle.** Bảo vệ refresh token, rotation, reuse detection, revoke token family và logout.

**Bước 6 — Chọn cơ chế revoke.** jti denylist, user/session version, introspection, revocation events hoặc emergency key rotation.

**Bước 7 — Thiết kế consistency.** Shared store, cache TTL, event replay, node restart, broker outage và fail-open/fail-closed.

**Bước 8 — Kiểm claims và key lifecycle.** iss, aud, exp, nbf, iat, jti, token type, algorithm allowlist và JWKS rotation.

**Bước 9 — Tách authentication khỏi domain authorization.** Recheck tenant/ownership/entitlements cho thao tác nhạy cảm.

**Bước 10 — Kiểm thử failure modes.** Revoke giữa hai requests, stale cache, AS outage, key compromise, event loss, multi-node propagation và request đang chạy.

## Kết luận

**JWT tự chứa cho phép Resource Server xác minh chữ ký và claims cục bộ, nhưng không tự nhận biết một sự kiện thu hồi mới xảy ra tại Authorization Server.** Nếu chỉ dùng local validation và không có state/event bổ sung, token thường tiếp tục được chấp nhận tới exp, cộng biên clock skew theo cấu hình.

Có thể giảm cửa sổ đó bằng **access token TTL ngắn**, nhưng nếu cần thu hồi nhanh hơn phải truyền trạng thái tới Resource Server qua **introspection, jti denylist, token version, revocation events hoặc emergency key rotation**. Mỗi lựa chọn có chi phí về network, state, consistency, cache và blast radius.

Trong Spring Security, **JwtDecoder** cùng validators xác minh signature, issuer, audience và thời hạn. Chúng không tự thay thế revocation store. Với WebFlux, giữ lookup reactive và không block event loop.

**Thiết kế tốt phải nói rõ token còn có thể được chấp nhận bao lâu sau revoke, Resource Server nhận thông tin revoke bằng cách nào, và hệ thống phản ứng ra sao khi cơ chế truyền trạng thái bị lỗi.** Nếu chưa trả lời được ba câu hỏi đó, “instant revocation” chưa có một bảo đảm kỹ thuật cụ thể.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html)
