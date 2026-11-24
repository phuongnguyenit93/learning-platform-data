# Phân biệt introspection với local signature validation

## 1. Hai cách trả lời câu hỏi “access token này có đáng tin không?”

Trong chương **Introspection** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài này phân biệt hai phương thức thường được resource server (RS) sử dụng để quyết định có chấp nhận một **OAuth 2.0 access token** hay không:

1. **Token introspection:** RS gọi endpoint đáng tin của authorization server (AS) theo **RFC 7662**, gửi token cần kiểm tra và nhận trạng thái cùng metadata được phép công bố, nổi bật là `active`.
2. **Local signature validation:** RS tự xác minh **chữ ký của token dạng JWT ký số (JWS)** bằng khóa đã được tin cậy, rồi kiểm tra các claims, chính sách về thời hạn, issuer, audience, scope và loại token.

Hai cơ chế có **trust boundary khác nhau**. Introspection dựa vào một **quyết định từ AS tại thời điểm truy vấn** (có thể bị trễ do cache). Local verification dựa vào **chữ ký mật mã và dữ liệu trong token** tại RS, nên thường không cần gọi AS trong từng API request.

Giả sử `orders-api` nhận bearer token từ `sales-dashboard`:

~~~text
Client                 orders-api / RS                    Authorization Server
  | Bearer AT                 |                                  |
  |-------------------------->|                                  |
  |                           |-- Introspection approach ------>|
  |                           |   token=<opaque-or-JWT>          |
  |                           |<-- active + permitted metadata --|
  |                           |                                  |
  |                           |-- Local JWT approach ---------->|
  |                           |   Fetch/cache trusted JWKS      |
  |                           |<-- Public signing keys ---------|
  |                           |   Verify JWS + claims LOCALLY    |
  |<--------------------------|                                  |
~~~

Đường phía dưới chỉ cần tải/cập nhật **JWKS khi cần**, không phải hỏi AS cho từng token. Đường introspection trả lời trạng thái token theo AS, nhưng RS phải tự xác minh **response đến từ endpoint tin cậy và được phép áp vào chính API này**.

> **Kết luận nền tảng:** **`active=true` không tự đồng nghĩa “cho phép mọi thao tác”**. **Chữ ký JWT hợp lệ cũng không tự đồng nghĩa “đúng audience, scope, thời hạn hoặc chưa bị thu hồi”**. Cả hai chỉ là một phần của xác minh token; quyết định cuối cùng cần có **resource authorization và quyền nghiệp vụ**.

### Mục tiêu sau bài học

Sau bài, bạn có thể:

- Mô tả chính xác request/response **RFC 7662**, vai trò của `active` và các trường metadata tùy chọn.
- Giải thích local JWT **JWS signature verification** khác thế nào với **JWT claim validation** và kiểm tra quyền tại RS.
- Xác định vì sao **JWT vẫn có thể được introspect** và **opaque token không nhất thiết là JWT không ký**.
- So sánh **độ mới trạng thái thu hồi, độ trễ, phụ thuộc AS, caching, key rotation, outage và khả năng mở rộng** của từng cách.
- Cấu hình hai phương thức với **Java/Spring Security Resource Server**, kiểm soát expected issuer/audience/scope và tránh token confusion.
- Xây dựng test case phân biệt lỗi xác thực token, lỗi authorization, lỗi mạng, sai audience và stale cache.

Trong ví dụ, các địa chỉ `example.test`, mã token, secret và thời gian chỉ phục vụ học tập; không phải địa chỉ hay credential production.

## 2. Ai tin ai? Mô hình tin cậy giữa Client, AS và RS

Một request OAuth thường có các thành phần:

| Thành phần | Vai trò | Điều không được giả định |
| --- | --- | --- |
| **Client** | Xin access token, gửi nó đến resource API | Client có thể tự khai scope/audience hoặc tự xác nhận token hợp lệ |
| **Authorization Server (AS)** | Phát hành token, ràng buộc scope, audience, subject/client, thời hạn và trạng thái | Mọi token do AS cấp đều hợp lệ tại **mọi** RS |
| **Resource Server (RS)** | Kiểm tra token và quyết định truy cập tài nguyên | Chữ ký hợp lệ hoặc `active=true` đủ để cho truy cập object bất kỳ |
| **JWKS endpoint** | Cung cấp public signing keys đáng tin cho JWT validation | URL lấy từ token chưa xác minh có thể được tự động tin |
| **Introspection endpoint** | Trả trạng thái/metadata token cho caller được phép | Endpoint là công khai hoặc response cho mọi RS đều giống nhau |

### 2.1. Đường tin cậy của local JWT

Với JWT access token ký JWS:

~~~mermaid
flowchart LR
    C["Client"] -->|"Authorization: Bearer JWT"| RS["orders-api / RS"]
    CFG["Trusted issuer + JWKS config"] --> RS
    JWKS["AS JWKS endpoint"] -->|"Public key fetched/cached"| RS
    RS -->|"Verify signature + alg/kid"| SIG["Cryptographic trust"]
    SIG -->|"Validate iss, aud, exp, nbf, typ, scope"| POL["Token policy"]
    POL -->|"Tenant + object ACL"| DATA["Allowed resource"]
~~~

RS **không** tin public key chỉ vì token đưa một `kid`, `jku` hoặc `x5u`. RS phải có **issuer/key trust configuration độc lập với token**. `kid` chỉ giúp chọn khóa trong **trusted key set** theo thiết kế.

### 2.2. Đường tin cậy của introspection

~~~mermaid
flowchart LR
    C["Client"] -->|"Authorization: Bearer AT"| RS["orders-api / RS"]
    CFG["Configured AS + RS credentials + TLS"] --> RS
    RS -->|"POST /introspect, token"| AS["Trusted AS"]
    AS -->|"Authenticated/authorized RS?"| CHECK["Introspection access policy"]
    CHECK -->|"active + authorized metadata"| RS
    RS -->|"Check active + aud/scope/time + ACL"| DATA["Allowed resource"]
~~~

AS biết caller nào được phép introspect và có thể **chỉ trả metadata đúng quyền của RS**. RFC 7662 cho phép response token inactive có **chỉ `active=false`**, không cần tiết lộ chủ thể hay nguyên nhân. RS không được suy từ response thiếu metadata rằng token “có lẽ đúng”.

### 2.3. Introspection không thay việc xác thực RS

AS nên bảo vệ introspection endpoint bằng TLS và **RS authentication/authorization**. Một resource server thường có client ID/secret, private-key JWT, mTLS hoặc phương thức AS cho phép. Chúng dùng để **RS chứng minh mình là caller được phép**; chúng không phải OAuth credential của end-user.

Nếu attacker gọi introspection endpoint để dò token của Alice, AS không được vô tình trả đầy đủ `sub`, scope, audience, client_id và trạng thái nhạy cảm cho caller không được phép.

### 2.4. Tương quan với JWT, opaque, AT và RT

| Loại | Introspection có phù hợp? | Local signature validation có phù hợp? |
| --- | --- | --- |
| **Opaque access token** | Thường là lựa chọn tự nhiên khi RS không có state riêng để tra token | Không thể xác minh **JWT/JWS signature** nếu token không chứa JWS; có thể có scheme riêng nhưng không gọi nó là JWT validation |
| **JWT access token ký JWS** | **Có**, nếu AS hỗ trợ nhận token đó và trả trạng thái | **Có**, nếu RS tin đúng issuer/keys và kiểm tra claims đầy đủ |
| **JWT mã hóa JWE** | Có thể introspect nếu AS hỗ trợ | Không thể “verify signature JWS” đơn giản trên ciphertext; cần decrypt và kiểm tra layer chữ ký/claims theo profile |
| **ID token OIDC** | Endpoint có thể trả dữ liệu theo chính sách riêng, **không phải cách RS tự nhận ID token làm AT** | RP xác minh ID token theo OIDC, nhưng RS API phải từ chối khi nó không phải access token |
| **Refresh token** | Có thể có trạng thái tại AS, nhưng không gửi RT tới resource API | RT không phải access token cho API dù trông như JWT |

**Không có quy tắc “introspection chỉ cho opaque” hoặc “JWT luôn không cần introspection”.** Hai trục cần quyết định riêng là **định dạng token** và **chiến lược xác thực trạng thái ở RS**.

## 3. Token introspection theo RFC 7662: request và response

### 3.1. Endpoint và request contract

AS có thể công bố introspection endpoint qua metadata đáng tin, hoặc RS được cấu hình URL tĩnh. Theo RFC 7662, RS gửi **HTTP POST**, body `application/x-www-form-urlencoded` và trường `token` bắt buộc:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <resource-server-client-credential>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-access-token>&token_type_hint=access_token
~~~

**Ý nghĩa các trường:**

- `token` (**REQUIRED**): credential mà RS đang đánh giá. Phải được xử lý như **secret** và không ghi raw vào logs/traces.
- `token_type_hint` (**OPTIONAL**): gợi ý để AS tìm token hiệu quả hơn; theo RFC 7009/RFC 7662 phổ biến có `access_token`, `refresh_token`. **Không phải bằng chứng loại token**, AS phải xác định thực chất.
- `Authorization: Basic ...` minh họa **RS authentication**. AS có thể đăng ký mTLS, private-key JWT hoặc cơ chế tương đương; không mặc định endpoint chấp nhận mọi caller có token.
- `HTTPS` với certificate/hostname validation là bắt buộc theo trust boundary. Không follow redirect đem theo token sang host lạ.

`token_type_hint=access_token` không làm một refresh token trở thành access token, cũng không ép AS cho RS introspect RT. Nếu hint sai, AS có thể vẫn tìm được token bằng cách khác theo đặc tả và policy, nhưng RS **không được tự sửa token purpose dựa vào hint**.

### 3.2. Response khi active

Một response minh họa khi AS xác nhận token active và cho RS truy cập metadata:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "alice-742",
  "client_id": "sales-dashboard",
  "token_type": "Bearer",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893455700,
  "nbf": 1893455700,
  "jti": "at-example-3091"
}
~~~

Đây là **JSON ví dụ**, không phải response thực tế hiện tại. `exp`, `iat`, `nbf` dùng **NumericDate giây kể từ Unix epoch**, không phải milliseconds. RFC 7662 quy định **`active` bắt buộc**; các trường khác **đều tùy chọn** hoặc phụ thuộc AS/token profile. Tên `sub`, `scope`, `aud` hữu ích nhưng **không được giả định luôn hiện diện** nếu chưa có hợp đồng.

Ý nghĩa metadata:

| Trường | Ý nghĩa và cách dùng đúng |
| --- | --- |
| `active` | AS cho biết token đang active theo định nghĩa/trạng thái và quyền caller được phép biết |
| `scope` | Các scopes được cấp, dạng string phân tách bởi dấu cách theo RFC |
| `client_id` | Client OAuth được phát token, khác identity người dùng |
| `username` | Tên hiển thị/đăng nhập nếu AS cung cấp; **không dùng làm immutable identity key** |
| `sub` | Subject của token theo contract AS, có thể là user hoặc principal phù hợp |
| `token_type` | Ví dụ `Bearer`; không thay phân biệt access token với ID/refresh token |
| `exp` | Hạn token ở dạng NumericDate, cần kiểm tra khi AS cung cấp và theo contract |
| `iat` | Thời điểm token được phát hành |
| `nbf` | Thời điểm token bắt đầu được sử dụng |
| `aud` | Audience mà token dành cho; RS cần chứng minh token đúng API mình |
| `iss` | Issuer phát hành, phải gắn với AS đã tin cậy |
| `jti` | ID token nếu có, dùng trong audit/replay/revocation theo policy |

### 3.3. Response khi inactive hoặc không được phép biết

AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

Theo RFC 7662, response này dùng cho token **không active** (có thể chưa từng tồn tại, hết hạn, revoked, không thuộc phạm vi introspection caller...) hoặc caller không được phép biết token đó. Không cần trả thêm `sub` hoặc chi tiết “token của Alice vừa bị khóa”.

**HTTP 200 + `active=false` là một kết quả introspection thành công về mặt giao thức nhưng token **không hợp lệ cho quyền truy cập**.** Không nhầm với `401` tại introspection endpoint khi chính credentials của RS không hợp lệ.

### 3.4. Các loại lỗi cần phân biệt

| Kết quả | Diễn giải | Quyết định của RS |
| --- | --- | --- |
| HTTP 200, `active=true`, metadata hợp lệ | AS xác nhận trạng thái token, cần kiểm tra policy còn lại | Chỉ tiếp tục authorization nếu aud/scope/type/ACL đúng |
| HTTP 200, `active=false` | Không xác thực được token như active cho caller này | **401 invalid_token** ở resource API khi phù hợp |
| HTTP 401/403 tại introspection | RS credentials/permission không đủ | **Fail closed**, alert cấu hình/trust; không coi token active |
| Timeout/DNS/TLS handshake error | Không liên lạc được AS đáng tin | **Fail closed** hoặc cache đã được phê duyệt trong giới hạn freshness/SLA; không tự cho truy cập |
| HTTP 5xx/429 | AS lỗi/rate limiting | Circuit breaker/backoff, bounded concurrency, không flood endpoint |
| JSON malformed/thiếu `active` | Protocol/contract error | Không tự mặc định `active=true` |
| `active=true` nhưng thiếu audience theo policy | Không đủ bằng chứng token dành cho API | Từ chối hoặc dùng một nguồn trust contract khác đã được thiết kế rõ |

**Không truyền raw introspection error body cho người dùng** nếu chứa thông tin nhạy cảm hoặc config. Resource API nên trả lỗi OAuth theo RFC 6750 và hạn chế thông tin lộ ra ngoài.

### 3.5. `active` phụ thuộc trạng thái và caller

AS có thể coi token inactive vì expiry, not-before, revocation, trạng thái grant/client/user, hoặc vì RS caller không được quyền introspect token đó. RFC 7662 không yêu cầu AS tiết lộ lý do cụ thể. Do vậy, **RS không được suy rằng active=false chỉ có nghĩa token hết hạn**, và không thử introspect ở một AS khác/RS credential mạnh hơn để “tìm active=true”.

## 4. Local JWT signature verification: chính xác phải làm những bước nào?

Với **JWS compact JWT access token**, một verifier đúng cần nhiều lớp:

~~~text
Untrusted Authorization header
  ↓ giới hạn kích thước, loại token, syntax
Parse JWS protected header và payload bằng parser an toàn
  ↓
Select algorithm/key từ AS issuer config đã tin
  ↓
Verify digital signature trên đúng JWS signing input
  ↓
Validate token profile/typ, iss, aud, exp, nbf, iat, scope
  ↓
Map verified subject/client/actor và granted scopes
  ↓
Check route authorization + tenant/object ACL
  ↓
ALLOW / DENY
~~~

**“Signature valid” chỉ chứng minh bytes đã được ký bằng một khóa tương ứng** nếu key/algorithm trust đúng. Nó **không chứng minh** token dành cho API này, vẫn active tại AS, user chưa bị khóa, hay scope cho phép hành động đang yêu cầu.

### 4.1. JWS không phải mọi loại JWT

Một JWT có thể được ký (JWS), mã hóa (JWE), hoặc theo các cấu trúc profile khác. Không phân loại mọi chuỗi “có ba dấu chấm” là JWT AT hợp lệ. Một JWT mã hóa không thể được xác minh trực tiếp như một JWS compact ba đoạn khi chưa giải mã lớp phù hợp; việc JWE decrypt thành công cũng không tự chứng minh issuer/audience/scope.

OAuth AT theo JWT Profile RFC 9068 có các yêu cầu riêng về header/claims. OIDC ID token cũng là JWT nhưng có mục đích **xác thực end-user tại RP**, không phải AT cho RS. RS phải phân biệt **token purpose**, không chỉ nhìn `iss` và `sub`.

### 4.2. Trusted keys, algorithm và `kid`

RS cần cấu hình **expected issuer** và nguồn JWKS đã được xác minh. Khi token header:

~~~json
{"alg":"RS256","typ":"at+jwt","kid":"key-2026-11"}
~~~

RS chọn `kid` **trong key set của issuer được tin**, rồi verify bằng thuật toán được allowlist. Không:

- Cho token tự chọn `alg=none` hoặc thuật toán không được policy cho phép.
- Dùng nhầm symmetric secret làm public verification key vì algorithm confusion.
- Follow `jku`/`x5u` tùy ý trong header chưa được verify.
- Chấp nhận key mới chỉ vì key ID trùng một `kid` từng dùng ở issuer khác.
- Tin token của issuer B chỉ vì cùng kiểu khóa hoặc `kid` với issuer A.

### 4.3. Validate registered claims và profile

| Kiểm tra | Tại sao cần |
| --- | --- |
| **`iss`** | Token từ **đúng AS** được resource server phê duyệt |
| **`aud`** | Token được cấp cho **đúng RS/resource**; chống cross-resource token substitution |
| **`exp`** | Token chưa hết hạn, với clock skew policy được giới hạn |
| **`nbf`** | Token đã đến thời điểm bắt đầu hợp lệ |
| **`iat`** | Hợp lý theo thời gian/TTL policy khi có và profile yêu cầu |
| **`typ`/token profile** | Không nhận OIDC ID token, JWT client assertion, RT làm AT |
| **`scope`/`scp`** | Granted permissions theo profile AS; parse chính xác, không substring |
| **`sub`/`client_id`/`act`** | Phân biệt user-delegated, app-only và actor token; không giả danh end-user |
| **Tenant/object policy** | Scope đúng vẫn không cho đọc mọi record |

Không có `aud`, sai `typ` hoặc thiếu claims mà profile yêu cầu phải **fail closed**. Không tự cấp quyền vì token “đúng chữ ký” khi audience absent. Kiểm tra claims phải dựa trên **cấu hình issuer/resource và profile đã được phê duyệt**, không tin claims tự khai về nơi phát hành.

### 4.4. `exp` không phải revocation thời gian thực

Ví dụ:

~~~text
10:00 AS cấp JWT AT, exp=10:15, aud=orders-api
10:03 Admin revoke grant của Alice
10:04 orders-api verify JWT offline: signature/exp vẫn đúng
10:15 JWT hết hạn
~~~

Nếu RS chỉ kiểm signature và claims trong JWT, việc grant bị revoke lúc 10:03 **không tự xuất hiện trong JWT đã ký**. Nếu yêu cầu chặn từ 10:03, cần denylist/session/user status check, introspection hoặc một hệ thống authorization state khác có SLA phù hợp.

### 4.5. JWKS caching không đồng nghĩa token status caching

RS có thể cache **public signing keys** lâu hơn một request để tránh truy vấn JWKS liên tục. Điều này **không** cho biết token đã bị revoke. Key cache giúp kiểm tra chữ ký, còn token-status cache (introspection/denylist) là lớp riêng; hai TTL không được đánh đồng.

Khi AS rotate signing key, RS cần cơ chế cập nhật JWKS đúng cách và thời gian giữ khóa cũ phù hợp với token còn sống. Khi private key bị compromise, chỉ chờ JWT hết hạn có thể không đáp ứng incident SLA; cần đánh giá key revocation/denylist và rollback.

## 5. So sánh trực tiếp: introspection vs local signature validation

| Tiêu chí | Introspection (RFC 7662) | Local JWS/JWT validation |
| --- | --- | --- |
| **Đầu vào RS** | Opaque AT **hoặc JWT AT** nếu AS hỗ trợ | JWT access token **ký số** với profile phù hợp |
| **Nguồn bằng chứng** | Response từ AS được RS tin cậy và được phép gọi | Chữ ký JWS + claims + trusted issuer/JWKS |
| **Ý nghĩa active/revocation** | AS có thể phản ánh trạng thái hiện tại **tại thời điểm kiểm tra** | Không biết revocation sau issuance nếu không thêm state check |
| **Network mỗi API call** | Thường có nếu không dùng cache | Thường không; chỉ JWKS refresh theo nhu cầu |
| **Độ trễ** | Thêm RTT/network/AS processing, có thể được giảm bởi cache | Chủ yếu crypto/parse/claims locally |
| **Availability phụ thuộc AS** | Phụ thuộc trực tiếp khi không có cache hợp lệ | Có thể tiếp tục khi AS outage nếu có trusted keys và token chưa hết hạn |
| **Khả năng AS kiểm soát metadata** | AS có thể trả metadata đã lọc cho RS caller | Claims đã nằm trong token; RS đọc các trường token |
| **Token payload tiết lộ cho client** | Opaque che claims khỏi client | JWT claims thường có thể decode dù chữ ký không đổi |
| **Quota/rate limit** | Cần giới hạn lưu lượng introspection và backoff | Hạn chế JWKS fetch/key refresh và CPU DoS |
| **Cache** | Cache token state có rủi ro stale revocation | Cache JWKS/key khác cache trạng thái token |
| **Key rotation** | Thường do AS xử lý bên trong; RS cần bảo vệ RS credentials/TLS | RS phải cập nhật đúng trusted JWKS/key set |
| **Lỗi mạng** | Phải quyết định fail-closed và SLA/độ mới của cache | Không mất khả năng offline verify chỉ vì introspection outage |
| **Mục tiêu authorization** | RS vẫn kiểm audience/scope/tenant/ACL | RS vẫn kiểm audience/scope/tenant/ACL |
| **Complexity tại RS** | Cấu hình endpoint, RS authentication, timeout, cache và mapping claims | JWS parser, trusted keys, algorithms, claims validators, JWKS lifecycle |

### 5.1. Không có “phương thức luôn tốt hơn”

Nếu hệ thống ưu tiên **thu hồi nhanh** hoặc tokens có nội dung không muốn phơi cho client, opaque + introspection là lựa chọn đáng đánh giá. Nếu hệ thống có **lưu lượng cực lớn, cần độ trễ thấp** và chấp nhận AT TTL ngắn cùng chiến lược revocation riêng, JWT verify offline có thể hợp lý hơn.

Không tự kết luận “opaque luôn an toàn” hoặc “JWT luôn nhanh và đơn giản”. Một RS introspection cấu hình sai audience có thể chấp nhận token của API khác. Một RS JWT verify đúng signature nhưng bỏ `aud` có thể bị confused deputy. **Security policy quan trọng hơn format.**

## 6. Caching và độ trễ thu hồi: điểm đánh đổi quan trọng nhất

Một API có thể phục vụ hàng nghìn request mỗi giây. Gọi introspection **cho mọi request** có chi phí mạng và gây tải cho AS. Cache kết quả introspection giảm tải nhưng kéo dài khoảng thời gian RS có thể tin một `active=true` **đã trở nên lỗi thời**.

### 6.1. Thời điểm AS revoke khác thời điểm RS biết revoke

Giả sử:

~~~text
T0       RS introspect AT -> active=true.
T0+1s    AS revoke AT/grant.
T0+2s    RS đọc cache active=true.
T0+30s   Cache hết hạn, RS introspect lại -> active=false.
~~~

Nếu cache entry `active=true` có TTL 30 giây, RS có thể tiếp tục nhận token bị revoke **đến khi cache hết hạn** (và đôi khi thêm độ trễ đồng bộ giữa AS nodes). Đừng quảng bá “opaque token revoke tức thì” nếu thực tế RS cache active status hàng phút.

Một mô hình upper bound mang tính thiết kế:

\[
\text{revocation visibility delay}
\lesssim \text{positive cache TTL} +
\text{AS propagation delay} +
\text{clock/scheduling effects}
\]

Đây là **ước lượng**, không phải bảo đảm toán học tuyệt đối: lỗi mạng, CDN/proxy caching, retry, request đang xử lý, dữ liệu AS phân tán và middleware khác có thể làm thay đổi kết quả. Cần đo SLA end-to-end.

### 6.2. Cách tính TTL cache dương

Đối với token còn hạn `exp`, policy có thể giới hạn:

~~~text
remaining = max(0, exp - now - safetyMargin)
effectivePositiveCacheTtl = min(
    configuredMaxPositiveTtl,
    remaining,
    revocationFreshnessBudget
)
~~~

Nếu AS không cung cấp `exp`, RS **không thể tự suy token còn hạn bao lâu**; chỉ cache khi có contract hoặc TTL cực ngắn được policy xác nhận. Không cache `active=true` vô thời hạn vì response thiếu `exp`. Nếu `exp` đã qua, từ chối, kể cả cache entry chưa hết TTL.

Một bộ số **minh họa, không phải khuyến nghị chuẩn**:

| API | Mục tiêu độ mới khi revoke | Cache positive introspection ví dụ |
| --- | --- | --- |
| Tài nguyên nhạy cảm, yêu cầu revoke trong vài giây | Rất chặt | Cache vài giây hoặc không cache; AS chịu tải tương ứng |
| API nghiệp vụ thông thường chấp nhận delay ngắn | Trung bình | 10–30 giây nếu SLA/throughput cho phép |
| Read-only resource rủi ro thấp, AS rate limited | Linh hoạt hơn | TTL dài hơn nhưng không vượt `exp`/SLA |

Không lấy các con số này làm mặc định production: rủi ro, regulatory controls, số lượng requests, AS latency, cache invalidation và yêu cầu bảo mật quyết định TTL.

### 6.3. Positive và negative caching có rủi ro khác nhau

| Response | Cache được không? | Nguy cơ |
| --- | --- | --- |
| `active=true` | Chỉ cache trong giới hạn đã duyệt, không vượt expiry | Token revoked nhưng RS còn cấp quyền |
| `active=false` | Có thể cache rất ngắn theo policy để giảm dò token | Token vừa được kích hoạt/phân quyền lại nhưng vẫn bị từ chối; dễ gây DoS nếu cache key thiếu ngữ cảnh |
| HTTP 401/403 của introspection endpoint | **Không** cache như kết quả inactive hợp lệ của token | Che giấu lỗi RS credentials/authorization |
| HTTP 429/5xx hoặc timeout | **Không** cache thành active | Tránh fail-open và cache poisoning trạng thái |
| Response sai schema/missing `active` | Không cache như một validation success | Tránh parser bug/unknown response |

Một số hệ thống chọn **không cache active=false** để tránh tăng thời gian từ chối token mới; lựa chọn này cũng cần rate limiting chống thăm dò token.

### 6.4. Cache key không thể chỉ theo chuỗi token tùy tiện

Nếu một RS A có quyền introspect token còn RS B không có quyền, cache chung:

~~~text
cache[token] = {"active": true, "scope": "...", "aud": ["A"]}
~~~

có thể chuyển kết quả đã được xác thực trong ngữ cảnh A sang B. Cache nên ràng buộc:

~~~text
issuer / AS configuration
introspection endpoint / authorized RS identity
token fingerprint or protected token reference
expected token purpose and resource/audience
policy or validator version where relevant
~~~

Không đặt **raw bearer token** làm key hiển thị trực tiếp trong cache metrics/logs, key monitoring hoặc exceptions. Có thể dùng hash/HMAC có khóa phù hợp để lập chỉ mục, nhưng phải bảo vệ khỏi inference/replay, tránh đưa token ra hệ thống cache không được mã hóa/bảo vệ. Cache value chứa `sub`, scope và metadata cũng là dữ liệu nhạy cảm cần access control.

### 6.5. Cache stampede và single-flight

Khi một token phổ biến hết cache TTL, hàng trăm requests cùng gọi introspection có thể gây **thundering herd**. RS có thể dùng:

- **Single-flight** theo token fingerprint và trust context: một introspection request cho nhiều API requests đang chờ.
- Bounded concurrency/semaphore để tránh saturate AS.
- Timeout + backoff/circuit breaker có giới hạn; không retry vô hạn.
- Jitter có cân nhắc để tránh đồng loạt hết hạn cache.
- Negative caching ngắn/rate-limiting cho invalid tokens theo policy.

Không chia sẻ **kết quả authorization của user/route A** cho request khác chỉ vì cùng token. Introspection chỉ xác minh **credential**; route/resource ACL cần đánh giá cho từng request hoặc có cache domain riêng được quản lý.

### 6.6. JWKS cache và introspection cache không giống nhau

| Cache | Lưu gì? | Rủi ro chính |
| --- | --- | --- |
| **JWKS public key cache** | Những khóa RS dùng xác minh chữ ký JWT | Khóa rotate/compromise chưa được cập nhật |
| **Introspection response cache** | Trạng thái `active` và claims/metadata của **một token** | Quyền đã revoke nhưng positive result còn sống |
| **Authorization decision cache** | Quyết định có quyền đọc/sửa object/tenant | ACL/role/ownership đã thay đổi nhưng vẫn allow |

Đừng lấy JWT `exp` làm TTL cho policy decision cache. Một token còn hạn 15 phút không có nghĩa người dùng giữ quyền sở hữu hồ sơ trong 15 phút nếu domain yêu cầu cập nhật tức thì.

## 7. Các cách thu hồi và giới hạn của mỗi mô hình

### 7.1. Revoke refresh token không mặc định revoke access token

Khi user logout, AS có thể thu hồi **refresh token (RT)** để chặn xin AT mới. Nhưng bearer access token đã cấp có thể còn hạn:

~~~text
RT revoked at 10:03 → Cannot mint future AT via that RT.
JWT AT exp 10:10     → May remain valid until exp if RS checks only JWT.
Opaque AT             → Can become inactive if AS revokes AT/grant;
                        RS sees it upon next trusted introspection.
~~~

Nếu AS nội bộ coi revoke grant là làm mọi opaque AT inactive, introspection có thể phản ánh điều đó. Nếu AS chỉ revoke RT, opaque AT có thể vẫn active. **Không suy behavior AS từ format token**; phải kiểm thử theo contract.

### 7.2. Cần chặn ngay: các lựa chọn

Với yêu cầu chặn trong vài giây sau compromise hoặc disable user:

1. **Opaque AT + introspection** với cache nhỏ/freshness policy đủ chặt.
2. **JWT AT + denylist/session state check** ở RS hoặc gateway.
3. **JWT AT + introspection thêm** cho các routes nhạy cảm, nếu AS hỗ trợ.
4. **AT TTL rất ngắn** và refresh-token controls, chấp nhận một cửa sổ sống tối đa phù hợp.
5. **Domain-level authorization state**, ví dụ đọc trạng thái user/tenant/object trước hành động nhạy cảm.

Không có phương án nào miễn phí: introspection/denylist có latency và availability dependency; TTL ngắn tăng tải token issuance/refresh; state invalidation cần đồng bộ distributed systems.

### 7.3. JWT được ký không “tự bị hủy” khi rotate key

Nếu AS thêm signing key mới nhưng **vẫn giữ khóa cũ** trong JWKS để verify tokens chưa hết hạn, JWT ký bằng khóa cũ có thể tiếp tục hợp lệ. Nếu loại bỏ key cũ đột ngột, nhiều token hợp lệ có thể bị từ chối. Khi key **bị lộ**, RS có thể cần ngừng tin key nhanh và áp incident policy, ngay cả khi mất khả năng verify token cũ.

Đừng dùng key rotation như cơ chế revoke user token thường ngày nếu không có threat model và blast-radius analysis. Nó có thể ảnh hưởng toàn bộ client/tenants dùng cùng key.

### 7.4. Clock skew và expiry policy

Jwt signature validation local và introspection đều liên quan thời gian, nhưng **nguồn phán quyết khác nhau**:

- Local JWT: RS dùng clock của mình để kiểm tra `exp`, `nbf`, `iat` theo policy và leeway nhỏ.
- Introspection: AS có thể đã áp thời gian khi tính `active`, nhưng RS cần kiểm `exp`/`nbf` nếu response/profile cung cấp hoặc policy yêu cầu.

Một leeway quá rộng làm token hết hạn được chấp nhận lâu hơn. Ví dụ 60 giây clock skew chỉ là **con số để minh họa**, không phải tiêu chuẩn bắt buộc. Sync clocks bằng NTP và kiểm thử các mốc ranh giới.

### 7.5. Logout, consent withdrawal và token status

| Sự kiện | Cần kiểm tra |
| --- | --- |
| User logout local session | App đã xóa session/token cache, AS RT/grant đã revoke nếu policy yêu cầu? |
| User rút consent | AS có chặn issuance/refresh mới và làm AT inactive theo contract không? |
| Admin disable client | AS có ngừng cấp token mới; introspection có coi AT cũ inactive không? |
| Admin disable user | RS có status/ACL checks đủ mới, không chỉ chữ ký token? |
| Key compromise | JWKS trust update, token invalidation/denylist, rotating creds và incident response? |

Mỗi tình huống cần SLA cụ thể; đừng hứa “revoke tức thì” khi cache còn giữ `active=true` hoặc JWT offline verify đến `exp`.

## 8. Bảo vệ introspection endpoint và metadata của người dùng

### 8.1. RS authentication/authorization là một ranh giới riêng

Introspection là API phục vụ **resource servers hoặc authorized protected resources**, không phải endpoint để bất kỳ client nào thử đoán bearer token. AS nên:

1. Bắt buộc TLS và client authentication hoặc phương thức bảo vệ tương đương theo RFC/policy.
2. Chỉ cho caller đã đăng ký truy vấn loại token, resource và metadata cần thiết.
3. Trả `active=false` với token không thuộc phạm vi caller khi cần chống thông tin rò rỉ.
4. Giới hạn số lượng attempts, request size, concurrency và rate.
5. Log audit an toàn theo caller/client/token fingerprint, không raw token.

Một AS có thể dùng response filters tùy resource, chẳng hạn chỉ công bố scope và principal references cần thiết để RS hoạt động. RS không được tin metadata từ một endpoint không được AS phê duyệt, dù JSON có `active=true`.

### 8.2. CREDENTIALS của RS và Bearer AT là hai secret khác nhau

Request tới introspection endpoint có thể mang:

~~~text
Authorization: Basic <rs-client-id-and-secret>
Body: token=<alice-access-token>
~~~

Cả hai cần bảo vệ:

- **RS client secret** xác thực RS với AS; không gửi đến API client/browser.
- **Access token** là credential mà Alice/client gửi tới RS; RS không in token vào log và không chuyển đến host bất kỳ.
- Introspection response có thể chứa thông tin cá nhân/scope/tenant; chỉ cung cấp cho service tin cậy và retention giới hạn.

Không dùng access token của Alice để xác thực **RS** tại introspection endpoint nếu AS yêu cầu RS credentials riêng; cũng không dùng RS client secret làm bearer AT cho API.

### 8.3. Tránh SSRF thông qua token hoặc issuer động

Một API nhận JWT có payload `iss=https://attacker.example.test` rồi tự tạo URL:

~~~text
https://attacker.example.test/oauth2/introspect
~~~

Nếu RS gửi token hoặc client secret sang URL này, kẻ tấn công có thể thu được credential. Do đó **introspection endpoint phải đến từ trusted configuration/discovery metadata đã xác minh**, không từ unverified token claims, request headers hoặc một tenant string chưa được allowlist.

Trong hệ thống multi-issuer, RS chỉ chọn **từ danh sách issuer đã được phê duyệt**, với resource-specific settings. Nếu không tìm được issuer hợp lệ, fail closed.

### 8.4. Không trộn cache metadata giữa các caller

AS có thể trả khác nhau cho `orders-api` và `payments-api` dù cùng token. Một cache proxy chung không hiểu RS identity có thể đưa `active=true`/claims của orders sang payments. Sử dụng:

- Cache nội bộ theo authorization context/caller hoặc service-local cache.
- `Cache-Control`/proxy configuration phù hợp với security contract.
- Không cache response chứa PII ở shared CDN không kiểm soát.
- Response encryption in transit và logs redaction.

### 8.5. Không rò nguyên nhân token inactive

Nếu token Alice bị thu hồi vì user bị khóa, RS không cần báo:

~~~json
{"error":"invalid_token","reason":"alice account disabled by HR"}
~~~

Phản hồi API nên giới hạn như `401 invalid_token` theo RFC 6750. Thông tin chi tiết để debugging thuộc **trusted audit/monitoring**, không gửi cho caller không xác thực hoặc attacker đang thử token.

## 9. Chọn kiến trúc theo rủi ro và lưu lượng

### 9.1. Ba mô hình triển khai

**Mô hình A — Pure opaque introspection**

~~~text
Client → RS (opaque AT)
         RS → AS /introspect (có/không cache ngắn)
         RS → ACL/route policy → response
~~~

Ưu điểm: AS có thể trực tiếp điều khiển trạng thái; token opaque không công khai claims cho client. Hạn chế: latency, rate, AS availability, RS credential và cache consistency.

**Mô hình B — Pure local JWT verification**

~~~text
Client → RS (signed JWT AT)
         RS verifies JWS + claims using trusted cached JWKS
         RS → ACL/route policy → response
~~~

Ưu điểm: ít round-trip tới AS, mở rộng phù hợp tải cao. Hạn chế: JWT còn hạn **không biết revocation mới** trừ khi thêm state check; key rotation/compromise cần xử lý; claims có thể đọc được bởi người cầm token.

**Mô hình C — Hybrid theo route/token policy**

~~~text
Low-risk read requests:
    verify JWT offline + domain ACL
Sensitive payouts/admin actions:
    verify JWT + trusted AS state/introspection or denylist + step-up ACL
Opaque tokens:
    trusted introspection with strict freshness
~~~

Hybrid giúp đánh đổi hiệu năng và độ mới theo mức rủi ro, nhưng yêu cầu **policy rõ và kiểm thử bypass**; attacker không được tự chọn “offline-only route” bằng header hoặc token type mà RS không kiểm chứng.

### 9.2. Bảng quyết định kiến trúc

| Yêu cầu | Ưu tiên xem xét | Điều kiện kiểm chứng |
| --- | --- | --- |
| API cần revoke nhanh sau user disable | Introspection/denylist/state check | Đo thực tế propagation + positive-cache TTL |
| Lưu lượng lớn, latency thấp, token TTL ngắn | Local JWT verification | RS xác minh issuer/aud/typ/expiry/scope đầy đủ |
| Client không nên thấy user claims trong token | Opaque AT + AS metadata qua introspection | RS auth/TLS, metadata exposure control |
| AS có thể outage nhưng API đọc vẫn phải chạy | Local JWT với trusted keys cached | Rủi ro accept AT còn hạn và policy chấp nhận |
| Giao dịch tài chính nhạy cảm | State-aware validation hoặc hybrid | Không chỉ dựa signature hoặc `active`; có domain approval/step-up |
| Nhiều AS/tenants | Explicit issuer routing + per-issuer validation config | Không lấy URL AS từ token chưa xác minh |
| API có nhiều clients public/confidential | Cả hai đều dùng AT được RS verify | Không dùng client_secret để suy user authorization |

### 9.3. Không trộn lựa chọn format với lựa chọn grant

Authorization Code + PKCE, Client Credentials, Device Authorization Grant hay Token Exchange đều có thể dẫn đến AT được phát hành dưới dạng JWT hoặc opaque theo AS. `grant_type` **không quyết định** RS phải introspect hay local verify, và `scope=openid` không phải chỉ thị dùng JWT.

Ví dụ:

~~~text
Authorization Code + PKCE → JWT AT → local verification.
Authorization Code + PKCE → opaque AT → introspection.
Client Credentials        → opaque AT → introspection.
Client Credentials        → JWT AT → local verification.
Device Authorization      → JWT/opaque AT theo AS policy.
~~~

### 9.4. Đừng nhận token sai format bằng auto fallback

Một API có thể hỗ trợ cả opaque và JWT, nhưng không nên:

~~~text
Try local JWT validation.
If invalid signature/audience -> call introspection.
If introspection active=true -> accept anyway.
~~~

Nếu token **lẽ ra là JWT cho API đó nhưng sai chữ ký/audience**, fallback không có điều kiện có thể làm mất tác dụng validator. Cần **routing strategy theo trusted token issuer/profile/registration**; introspection success vẫn phải qua **đúng audience, token purpose và authorization policy**. Không để attacker quyết định đường kiểm tra nhẹ hơn bằng cách đổi header/length.

### 9.5. Mô hình hiệu năng định lượng

Giả sử một API có `Q=10_000 requests/s` và local signature verify mất thời gian CPU nhỏ so với network. Nếu introspection không cache, AS có thể phải chịu gần **10.000 token-status requests/s** bên cạnh các chức năng phát hành token. Với cache hit rate `h=95%`, tải introspection lý thuyết giảm còn khoảng:

\[
Q_\text{introspection} \approx Q(1-h)
= 10\,000 \times 0.05 = 500\ \text{requests/s}.
\]

Đây là **phép tính minh họa**, không phải benchmark; concurrency, cache key cardinality, token diversity, ttl churn, burst traffic và retry có thể làm tải thực khác xa. Một cache hit rate cao vẫn chưa chắc đạt revocation SLA. Cần đo **P95/P99 latency, error rate, AS QPS, cache freshness, revocation lag và false-allow/false-deny**.

## 10. Spring Security Resource Server: JWT local validation

Trong Java/Spring Boot, **OAuth2 Resource Server JWT** sử dụng decoder và validators để xác minh JWS và token claims. Ví dụ sau là API `orders-api` tin đúng issuer `https://auth.example.test` và chấp nhận AT `aud=orders-api` có scope `orders.read`.

### 10.1. Cấu hình issuer đáng tin

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Khi có `issuer-uri`, Spring có thể sử dụng metadata của issuer để phát hiện JWKS URI và kiểm tra issuer theo framework/version. **Không** nhận issuer trực tiếp từ JWT chưa xác minh rồi cấu hình decoder động không giới hạn; issuer phải được kiểm soát.

### 10.2. Thêm expected audience validator

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
class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder ordersJwtDecoder() {
        String issuer = "https://auth.example.test";
        String expectedAudience = "orders-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(issuer)
                .build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Access token audience mismatch",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audienceValidator));
        return decoder;
    }
}
~~~

**Điều code minh họa làm được:**

- Fetch/verify JWS bằng trusted issuer/JWKS theo decoder configuration.
- Áp validator chuẩn issuer/time của Spring cùng **audience của chính API**.
- Từ chối JWT có `aud` không chứa `orders-api`, dù cùng issuer và signature đúng.

**Điều vẫn phải cấu hình/kiểm tra ở production:**

- Access token **type/profile**, chẳng hạn JWT AT theo RFC 9068 có `typ=at+jwt`, không nhầm ID token OIDC.
- Allowed JWS algorithms theo AS contract, chống algorithm/key confusion.
- Cache JWKS/key rotation, decoder timeouts và nguồn metadata đáng tin.
- Không tin `scope` do request header/query tự khai; chỉ dùng granted scopes trong token đã verify.
- User-vs-service principal, tenant/actor binding và object-level authorization.
- Nếu AS yêu cầu denylist/revocation SLA chặt, bổ sung state check **sau JWT verify**; đoạn decoder không tự làm điều đó.

Spring APIs và mặc định header `typ`/alg thay đổi theo phiên bản; luôn kiểm tra **đúng tài liệu Spring Security phiên bản triển khai** thay vì coi snippet là toàn bộ RFC 9068 validator.

### 10.3. Route-level và domain authorization

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain ordersApiChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Đây là route skeleton cho resource API, cần thêm CSRF/session policy phù hợp kiến trúc, security configuration và exception handling theo Spring version. Một token có `SCOPE_orders.read` **không** cho phép xem tất cả đơn hàng:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderPolicy.canRead(authentication, #orderId)")
public OrderView getOrder(String orderId) {
    Order order = repository.findById(orderId)
            .orElseThrow();
    return OrderView.from(order);
}
~~~

`orderPolicy` là abstraction cần kiểm tra tenant/ownership/role/actor từ **trusted principal** và dữ liệu order. Cần bật method security và cấu hình bind tên tham số theo phiên bản. Nếu app-only service AT không có end-user, policy phải xác minh service identity thích hợp thay vì tự tạo Alice từ `client_id`.

### 10.4. Local verification không thể tự hỏi AS “token có còn active?”

Nếu `sales-dashboard` đã logout tại 10:03 còn AT JWT `exp=10:10`, decoder trên vẫn có thể chấp nhận signature/exp cho tới khi TTL kết thúc. Để có **revoke nhanh**, hãy:

- Thiết kế domain/state validator hoặc denylist, hoặc
- Bổ sung introspection theo route/risk policy nếu AS hỗ trợ, hoặc
- Sử dụng AT TTL nhỏ và xác định rõ cửa sổ chấp nhận, hoặc
- Chuyển sang opaque/introspection nếu phù hợp latency/SLA.

**Không thêm một claim `revoked=false` vào JWT** rồi mong nó tự thay đổi khi AS revoke sau issuance. JWT đã ký là dữ liệu bất biến nếu không phát lại token mới.

## 11. Spring Security Resource Server: opaque token introspection

Spring Security hỗ trợ xác minh bearer token bằng **Opaque Token Introspection**. Tên `opaqueToken` là tên của nhánh framework; **không có nghĩa implementation không thể introspect một JWT** nếu AS hỗ trợ. Với cấu hình bên dưới, RS gửi bearer token tới introspection endpoint và xây principal/authorities theo response được framework/AS chấp nhận.

### 11.1. Cấu hình introspection endpoint và RS credentials

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: INJECTED_RS_INTROSPECTION_SECRET
~~~

`INJECTED_RS_INTROSPECTION_SECRET` là placeholder; cần inject từ secret manager, **không đưa secret thật vào repository**. `orders-resource-server` là client/identity để RS được AS authorize introspection; không đồng nhất với `sales-dashboard` là OAuth client xin AT của Alice.

### 11.2. Bật opaque-token mode

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain opaqueResourceChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/v1/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth ->
            oauth.opaqueToken(Customizer.withDefaults()));
    return http.build();
}
~~~

Trong một application, chọn **đúng security filter chain và token strategy** theo kiến trúc. Các code fragments JWT và opaque ở hai mục trên là **hai cấu hình minh họa thay thế**, không phải hai filter chains nên copy đồng thời và cho tranh nhau xử lý cùng endpoints.

**Quan trọng:** Không giả định AS introspection mặc định trả `iss`/`aud`, cũng không tin `active=true` là đủ. Nếu resource server cần audience (gần như luôn có trong multi-resource design), phải **thỏa thuận metadata introspection** và cấu hình validator riêng hoặc AS phải đảm bảo RS chỉ nhận status active đối với token dành cho RS này. Một API với **cùng issuer nhưng nhiều audiences** không được dùng `active=true` làm giấy phép truy cập bất kỳ API.

### 11.3. Kiểm tra metadata introspection với policy cụ thể

Đoạn sau minh họa **decorator** kiểm tra expected issuer và audience, dựa trên contract AS **bắt buộc trả `iss` và `aud` trong response active**. Nếu AS không có những fields đó, phải sửa **AS contract/policy** hoặc dùng nguồn metadata đáng tin thay thế, chứ không tự bỏ audience validation.

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class AudienceAwareIntrospector
        implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;

    AudienceAwareIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedIssuer = expectedIssuer;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate được tin để verify active và authenticate RS.
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        Object audience = principal.getAttribute("aud");
        if (!expectedIssuer.equals(issuer)
                || !matchesAudience(audience, expectedAudience)) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(
                            "invalid_token",
                            "Token metadata does not match resource",
                            null));
        }
        return principal;
    }

    private static boolean matchesAudience(
            Object raw, String expected) {
        if (raw instanceof String value) {
            return expected.equals(value);
        }
        if (raw instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }
}
~~~

Sau đó kết nối với delegate introspector do AS cấu hình:

~~~java
@Bean
OpaqueTokenIntrospector ordersOpaqueIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
        String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
        String rsClientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
        String rsSecret) {

    OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                    uri, rsClientId, rsSecret);

    return new AudienceAwareIntrospector(
            delegate,
            "https://auth.example.test",
            "orders-api");
}
~~~

Đoạn trên minh họa API thông dụng của Spring Security 6.x; ở những bản mới, implementation class/builder cho introspector có thể thay đổi, hãy kiểm tra dependency version. Cần imports cho `@Value`, `@Bean` và `NimbusOpaqueTokenIntrospector`. Không dùng constructor/decorator nếu library hoặc OP không đáp ứng metadata contract.

**Lưu ý sâu hơn:**

1. `active=false` phải được delegate từ chối, không xây principal như active.
2. `iss` và `aud` là **optional theo RFC 7662**, nên kiểm tra bắt buộc ở đây là **policy riêng của orders-api**, không phải khẳng định mọi server phải trả chúng.
3. String `aud` hoặc collection là hai representation phổ biến; thực tế cần parse/chống kiểu dữ liệu sai/duplicate keys theo contract.
4. `client_id` trong metadata là OAuth client đã xin token, **không phải bearer principal user** hoặc chứng minh quyền object.
5. `SCOPE_orders.read` có thể được framework map từ `scope`; phải xác minh nó không chỉ là requested scope do attacker gửi.
6. Access token có thể là JWT hoặc opaque; AS quyết định introspection status, **không phải decoder JWS**.

### 11.4. Khi không thể lấy issuer/audience trong introspection response

Một nhà cung cấp có thể không trả `aud` nhưng có logic **introspection response binding với RS identity**: ví dụ caller `orders-resource-server` chỉ nhận `active=true` với tokens dành cho orders. Điều này chỉ có thể sử dụng nếu **AS contract rõ, đã kiểm thử** và RS credentials không thể dùng để introspect token cho API khác.

Nếu AS trả `active=true` cho mọi token cùng issuer mà bỏ `aud`, và RS cũng không có phương án ràng buộc audience đáng tin, hệ thống có lỗ hổng **token substitution**. Không “làm cho chạy” bằng cách bỏ qua điều kiện này.

## 12. Cấu hình hybrid: quyết định bằng policy tin cậy, không bằng lỗi JWT

Một ứng dụng có thể cần:

- JWT access token từ AS-A để verify offline cho endpoints đọc.
- Opaque token từ AS-B để introspect trên endpoints nhạy cảm.
- JWT AT hợp lệ nhưng cần kiểm tra revoke tại routes có yêu cầu freshness chặt.

### 12.1. Chiến lược phân luồng

~~~text
Registered bearer token trust profiles:

Profile orders-jwt:
  trusted issuer = https://auth-a.example.test
  expected audience = orders-api
  format = signed-JWT access token
  validation = trusted JWKS + JWT validators
  sensitive route = optional grant/status check

Profile payments-opaque:
  trusted issuer = https://auth-b.example.test
  expected audience = payments-api
  format = opaque access token
  validation = authenticated introspection at AS-B
~~~

Đây là **khái niệm cấu hình**, không phải một schema chuẩn. RS phải biết route/resource nào chấp nhận profile nào **từ configuration**, không tự chọn endpoint introspection bởi `iss` chưa xác minh hoặc client header tự khai.

### 12.2. Bad fallback tạo lỗ hổng

~~~text
JWT parser returns "wrong audience".
Code catches any exception:
    try introspection with generic admin RS credentials.
Generic AS returns active=true for token aud=other-api.
Code accepts token without checking aud.
~~~

**Lỗ hổng:** token sai audience đã được **launder** qua fallback. Cách đúng:

1. Nếu token thuộc JWT profile, **signature hoặc claims sai là từ chối**, không cứu bằng introspection không đúng policy.
2. Nếu profile cho phép introspection bổ sung, kiểm tra `active=true` **và** đúng audience/issuer/type/scope.
3. Nếu token thuộc opaque profile, introspect từ **trusted AS cụ thể**, không thử tuần tự nhiều endpoints bằng credential quyền rộng.
4. Route-level policy và domain ACL luôn áp độc lập.

### 12.3. Có thể introspect JWT khi cần trạng thái mới

~~~text
Step 1: Verify JWT signature + expected iss/aud/exp/typ.
Step 2: For sensitive route, query AS token status by introspection
        or another approved revocation/state mechanism.
Step 3: Reject unless AS confirms active and metadata consistent.
Step 4: Check SCOPE_orders.write + object/tenant permission.
~~~

Introspection ở bước 2 chỉ có ý nghĩa nếu AS hỗ trợ RFC 7662 cho JWT đó và cấp quyền RS truy vấn. Không gửi JWT đến một introspection endpoint bất kỳ chỉ để “đo độ tin cậy”.

### 12.4. Đặc tính fail-closed của hybrid

Một lỗi hay gặp:

~~~text
Introspection unavailable on high-risk route.
Application falls back to local signature only.
Request is allowed despite declared revoke SLA.
~~~

Nếu high-risk route **bắt buộc có live status**, fallback local-only làm mất chính policy đã thiết kế. Cần fail closed hoặc giới hạn theo cache freshness **đã được phê duyệt**, không đổi chính sách trong runtime chỉ vì outage.

## 13. Resilience: khi AS, JWKS hoặc mạng gặp sự cố

### 13.1. Introspection endpoint chậm hoặc lỗi

Giả sử `orders-api` cần introspection cho mỗi lần đọc orders. AS có p99 latency tăng từ 25 ms lên 2 giây. Nếu API không giới hạn timeout và concurrency:

~~~text
Incoming API requests
  → Each waits for /introspect
  → Thread pool fills with blocked requests
  → Queue grows
  → Gateway retries
  → AS gets even more requests
  → Cascading failure
~~~

Biện pháp phòng vệ:

- Timeout có giới hạn phù hợp SLO và network budget.
- Bounded concurrency/bulkhead cho các request introspection.
- Single-flight khi nhiều requests chung token và cùng trust context.
- Circuit breaker/backoff khi AS outage; không retry storm.
- Positive-cache TTL đã được security team phê duyệt, không dùng stale forever.
- Giám sát AS latency, error rate, 429/5xx, cache hit ratio và revocation freshness.

**Fail closed** nghĩa là không cấp quyền khi **thiếu bằng chứng hợp lệ**. Không nhất thiết phải trả HTTP 401 cho mọi outage; có thể trả `503 Service Unavailable` nếu RS không thể kiểm tra token do AS tạm thời lỗi, để phân biệt “token sai” và “infrastructure unavailable”. Nhưng **không trả dữ liệu**.

### 13.2. Local JWT khi JWKS endpoint outage

Nếu RS đã cache trusted key của issuer, JWT có đúng `kid`/chữ ký/claims vẫn có thể được xác minh trong khoảng key-cache policy cho phép. Nếu gặp token có `kid` mới mà RS chưa có trusted key:

1. Thử refresh JWKS **từ issuer đã cấu hình** với giới hạn retry/rate.
2. Nếu không lấy được khóa tin cậy, **không chấp nhận token mới** chỉ vì `kid` có vẻ hợp lý.
3. Không follow `jku` trong token đến host lạ.
4. Giám sát key refresh failures và phối hợp key rotation giữa AS/RS.

Khi AS rotate key có kế hoạch, nên có giai đoạn publish key mới trước khi dùng ký token, giữ old keys đủ để verify token còn hạn theo policy, rồi retire. Khi key compromise, thời điểm retire có thể phải **sớm hơn** và chấp nhận chặn tokens cũ để giảm rủi ro.

### 13.3. Stale-if-error cần được phê duyệt, không bật tùy hứng

Một cache layer có thể hỗ trợ phục vụ kết quả introspection quá TTL khi AS lỗi. Với API nhạy cảm, điều này tương đương **cố tình kéo dài thời gian chấp nhận token có thể đã revoke**. Nếu product/SLA không chấp nhận, phải tắt stale-if-error.

Nếu business quyết định cho phép stale **trong một cửa sổ giới hạn** cho low-risk reads, cần:

- Có giới hạn thời gian tuyệt đối và không vượt `exp`.
- Không áp cho high-risk routes.
- Có monitoring/audit, security sign-off và threat model.
- Fail closed khi quá stale budget hoặc metadata bị thiếu/mâu thuẫn.

Một câu lệnh `return cachedActive ?? true` là **fail-open bug**, không phải resilience.

### 13.4. RS credentials bị lộ hoặc bị thu hồi

RS authentication secret/private key dùng introspection có thể bị compromise. AS cần hỗ trợ revoke/rotate RS credentials, giới hạn caller chỉ introspect resources của mình và audit các truy vấn bất thường. Một RS dùng credential quyền cao chung cho mọi API làm tăng blast radius.

Nếu AS trả 401 vì secret hết hiệu lực, RS không nên đổi sang anonymous introspection hoặc dùng một client secret khác không được cấp quyền. Sửa cấu hình qua quy trình secret rotation, giữ service fail closed trong khoảng chuyển đổi.

### 13.5. Nhiều AS hoặc regional AS nodes

Nếu AS multi-region replicate revocation state không đồng bộ:

~~~text
Region A: token revoked at 10:03:00.
Region B: introspection active=true until replication 10:03:08.
RS: region B + cache TTL 20 seconds.
~~~

Thời gian token còn được chấp nhận có thể dài hơn 8 giây replicate delay và còn phụ thuộc cache. Để cam kết revoke SLA, cần đo **AS region consistency + RS cache behavior**, không chỉ đo latency của `POST /introspect`.

### 13.6. Ngữ nghĩa HTTP 401 và 403 ở resource API

Một mapping thường gặp:

| Tình huống | HTTP tại API | Ghi chú |
| --- | --- | --- |
| Không có Bearer AT khi endpoint yêu cầu | 401 | `WWW-Authenticate: Bearer` phù hợp |
| AT hết hạn, revoked, `active=false` hoặc sai token purpose | 401 `invalid_token` | Không tiết lộ nguyên nhân nhạy cảm |
| JWT sai signature/issuer/aud/typ hoặc không validate được | 401 `invalid_token` | Không fallback sang weaker validation |
| AT hợp lệ nhưng thiếu scope | 403 `insufficient_scope` | Theo RFC 6750, có thể cung cấp scope hint theo policy |
| AT và scope đúng nhưng object của tenant khác | 403 hoặc 404 theo product anti-enumeration policy | Không dựa vào token verification để bỏ domain ACL |
| Introspection infrastructure outage | 503 hoặc lỗi service phù hợp | **Không cho phép truy cập**; phân biệt lỗi AS và credential khi vận hành |

Không cố “sửa 403” bằng việc đổi AT sang client credentials admin. Một token có `scope=orders.read` không thể tự nâng lên `orders.write` nhờ introspection.

## 14. Mười lỗi bảo mật thường gặp

### 14.1. Coi `active=true` là authorization hoàn chỉnh

~~~text
Introspection:
  active=true, aud=["reports-api"], scope="reports.read"

Incoming request:
  GET /orders/123 at orders-api

BAD:
  if active then allow

GOOD:
  require aud contains "orders-api" and scope "orders.read"
  require caller can read order 123
~~~

AS xác nhận token sống không đồng nghĩa token dành cho **API này**. Bỏ audience là đường **cross-resource token substitution**.

### 14.2. Verify JWS rồi bỏ expiry/audience

Một JWT ký đúng nhưng `exp` đã qua hoặc `aud=payments-api` vẫn phải bị orders từ chối. Signature-only validation không phải JWT access-token validation.

### 14.3. Tự tin `kid` và `jku`

Attacker gửi:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example.test/keys"
}
~~~

Nếu RS fetch keys từ `jku` chưa xác minh, attacker có thể điều khiển verification trust. Cần key/algorithm trust từ issuer config, không từ token header.

### 14.4. Cho phép JWT có `alg=none` hoặc algorithm confusion

Parser phải áp allowed algorithms theo profile. Không để attacker đổi `alg` và nhờ thư viện dùng sai kiểu khóa. Với signed JWT AT, `alg=none` không được chấp nhận làm chữ ký hợp lệ.

### 14.5. Lấy URL introspection từ `iss` chưa verify

Token đưa `iss=https://attacker.example.test`; RS gọi introspection endpoint ở domain đó, mang theo raw AT và RS client secret. Đây là **SSRF/credential exfiltration**. Chọn AS từ trusted allowlist trước khi gửi credential; không tin issuer do caller tự tuyên bố.

### 14.6. Cache `active=true` qua expiry và revocation

RS cache kết quả 15 phút trong khi `exp` chỉ 5 phút hoặc revoke SLA 10 giây. Cache làm token hết hạn/thu hồi được nhận quá lâu. Cache TTL phải bị chặn bởi `exp` và freshness budget.

### 14.7. Coi `active=false` là dấu hiệu AS outage

AS trả HTTP 200 với `{"active":false}`. Một wrapper sai biến nó thành “AS không hoạt động, tiếp tục dùng cache”. Phải phân biệt **token inactive** với **introspection infrastructure error**; inactive là lý do từ chối.

### 14.8. Dùng ID token thay OAuth AT

RP nhận OIDC ID token `aud=sales-dashboard`, gửi tới `orders-api`. Nếu RS introspect ra active=true và bỏ token purpose, hoặc JWT chỉ check signature, API có thể nhận sai loại token. Resource API phải yêu cầu **access token profile** và expected audience.

### 14.9. Bỏ client/user context khi authorize

`client_id` trong introspection metadata chỉ ra client đã được phát token. Nó không chứng minh user Alice có quyền thao tác. Client Credentials AT có thể biểu diễn service principal chứ không có Alice làm end-user; cần phân biệt delegated vs app-only và actor/subject khi Token Exchange.

### 14.10. Fail open khi AS/JWKS lỗi

~~~java
// Anti-pattern: NEVER use.
try {
    return validateToken(token);
} catch (Exception e) {
    return authenticatedPrincipalWithAllPermissions();
}
~~~

Khi token không thể xác minh, **không được tự cấp quyền**. Dùng bounded timeout và lỗi service phù hợp, không trả một principal giả. Cũng không biến mọi lỗi parse thành “khách hàng nội bộ được tin”.

## 15. Bốn bài toán kiến trúc có lời giải

### Bài toán A: Logout cần hiệu lực trong 5 giây

Một hệ thống quản lý thuốc có yêu cầu: sau khi user bị disable, API phải chặn token trong tối đa 5 giây. Đội phát triển đề xuất JWT AT TTL 15 phút, RS chỉ verify signature/`exp`.

**Phân tích:** JWT offline không biết trạng thái disable mới. TTL 15 phút có thể khiến user tiếp tục truy cập tới khi `exp`. Thay bằng TTL 5 giây sẽ làm token endpoint chịu tải lớn và có thể không phù hợp UX/availability.

**Hướng giải:** Dùng introspection hoặc state/denylist check có freshness đủ cho SLA, tính cả AS replication và RS cache; yêu cầu object/domain authorization cho operations nhạy cảm. Nếu chọn JWT, bổ sung live state check ở RS. **Không hứa 5 giây chỉ bằng `exp` của JWT 15 phút**.

### Bài toán B: API lượng lớn, AS bị quá tải

Một API đọc sản phẩm có 20.000 requests/s, nhận opaque AT và introspect mọi request. AS báo 429, gateway tự retry, gây outage dây chuyền.

**Phân tích:** Introspection có network per request; retry không kiểm soát khuếch đại tải. Không phải mọi route đều cần same revocation freshness.

**Hướng giải:** Tính SLO, cache `active=true` trong TTL theo security budget, single-flight, bounded concurrency, timeout/backoff; đánh giá JWT local verification nếu AS/clients/resource profile cho phép. Khi AS chưa xác minh được token, **không bật bypass auth để giải quyết latency**.

### Bài toán C: JWT đúng chữ ký nhưng sai API

`orders-api` nhận JWT:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["payments-api"],
  "scope": "payments.read",
  "exp": 1893456000
}
~~~

RS verify signature và thấy token chưa hết hạn, rồi cho GET `/orders`.

**Phân tích:** Token được AS phát hành cho **payments**, không phải orders. Đây là token substitution; signature validation là một bước nhưng **audience validation thất bại**.

**Hướng giải:** RS từ chối dù signature đúng. AS cấp một AT khác `aud=orders-api` và `scope=orders.read` theo authorized grant. Nếu dùng introspection, cũng phải kiểm metadata/contract audience, không chỉ active.

### Bài toán D: Introspection trả `active=true` nhưng thiếu `aud`

`orders-api` dùng opaque AT và Spring Security opaque mode. Provider chỉ trả `active`, `scope`, `client_id`, `sub`, không có `aud`. RS chia sẻ issuer với `payments-api` và dùng cùng introspection credentials quyền rộng.

**Phân tích:** RS chưa có bằng chứng token được phát hành cho orders; `active=true` và `scope=orders.read` có thể không đủ nếu scope không được ràng buộc resource rõ ràng. Nguy cơ cross-resource acceptance tồn tại.

**Hướng giải:** Sửa AS introspection contract trả audience/resource metadata; hoặc AS bảo đảm chỉ trả active=true cho tokens đúng resource của từng RS identity và kiểm chứng ranh giới bằng tests. Nếu không thể, **không bỏ qua audience check để hệ thống “chạy được”**.

## 16. Ma trận kiểm thử introspection và local JWT validation (55 ca)

Thiết lập test environment với:

- AS test có **introspection endpoint**, JWT signing keys/JWKS và revoke capability.
- Ít nhất hai RS: `orders-api`, `payments-api`; một RS có quyền introspect orders, caller khác không có.
- JWT AT ký bằng trusted/untrusted keys, opaque AT đang active/revoked, ID token và RT không dùng được tại RS.
- Fake clock/time control, programmable AS responses (delay, 429, 500, malformed JSON), key rotation và cache.
- Một API route cần `orders.read` và domain ACL kiểm tra tenant/owner.

Không đưa credential production vào test, không log raw tokens/RS introspection secret. Bảng dưới là test contract tham khảo; một số cases (như kiểu `aud`/`iss` introspection) phụ thuộc **AS metadata contract được tổ chức chấp nhận**.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| I01 | Opaque AT active, caller RS được phép, metadata `aud=orders-api`, scope đúng | `orders-api` xác thực token và tiếp tục domain ACL |
| I02 | Introspection trả `{"active":false}` | RS từ chối token, không cấp quyền |
| I03 | Introspection HTTP 200 nhưng thiếu `active` | RS từ chối response sai schema |
| I04 | `active` là string `"true"` thay boolean | RS từ chối schema/token-status ambiguity |
| I05 | Introspection HTTP 401 do RS client secret sai | RS fail closed, alert cấu hình, không tự chuyển sang anonymous |
| I06 | Introspection HTTP 403 vì RS không có quyền hỏi token | Không chấp nhận token |
| I07 | Token introspection HTTP 500 | Fail closed hoặc bounded previously approved cache còn hợp lệ; không default allow |
| I08 | Introspection network timeout | Không dùng stale-unbounded status, có timeout/backoff |
| I09 | TLS certificate/hostname của AS sai | RS từ chối kết nối, không trust-all |
| I10 | RS bị dụ follow redirect của introspection tới attacker host | Không chuyển bearer AT hoặc RS secret qua redirect |
| I11 | `token_type_hint=access_token` nhưng token thực là RT | AS/RS không coi hint là bằng chứng AT |
| I12 | RT được gửi trong Authorization Bearer tới orders API | Từ chối sai token purpose, bất kể RT còn active tại AS |
| I13 | OIDC ID token còn hạn được gửi tới RS | Từ chối token type/audience, dù chữ ký hợp lệ |
| I14 | Introspection active=true nhưng `aud=payments-api` | Orders từ chối sai audience |
| I15 | Introspection active=true nhưng thiếu `aud` theo contract orders yêu cầu | RS từ chối thiếu bằng chứng resource binding |
| I16 | Introspection active=true, scope không chứa `orders.read` | RS từ chối 403 `insufficient_scope` khi phù hợp |
| I17 | Introspection active=true, scope `myorders.read` | Không substring-match thành `orders.read` |
| I18 | Introspection active=true, `sub` Alice nhưng object tenant Bob | RS từ chối domain ACL |
| I19 | Token bị revoke ngay sau khi RS cache `active=true` | Cache chỉ chấp nhận tới freshness budget, không vô hạn |
| I20 | `exp` của token trước cache TTL | Cache không chấp nhận vượt expiry |
| I21 | Introspection response thiếu `exp` | Không tự cache positive vô thời hạn; áp contract/TLL hẹp |
| I22 | Cache key không phân biệt RS/orders/payments | Integration test phát hiện và từ chối cross-context reuse |
| I23 | 100 requests cùng token khi cache miss | Single-flight/bounded introspection concurrency |
| I24 | Token unknown được introspect hàng loạt | AS rate-limit, RS giới hạn tài nguyên, không raw-log tokens |
| I25 | `active=false` response bị cache như `active=true` do boolean parsing | Test phát hiện và chặn |
| I26 | Metadata `iss` của AS khác expected issuer | RS từ chối theo profile nếu issuer claim được yêu cầu |
| I27 | Introspection có `aud` dạng string | Validator so exact expected audience |
| I28 | Introspection có `aud` dạng array | Validator so membership exact, không substring |
| I29 | Metadata `aud` kiểu number/object sai contract | RS từ chối/không cho phép mặc định |
| I30 | AS revoke RT nhưng không revoke AT | Test xác nhận AT status theo **AS contract**, không suy hai loại bị revoke cùng |
| I31 | AS revoke AT/consent, cache TTL=5 giây | Đo revocation visibility delay, phải đạt SLA đã công bố |
| I32 | JWT AT JWS ký đúng khóa, `iss`/`aud`/`exp`/scope/profile hợp lệ | Local JWT path cho phép qua authn và tiếp tục ACL |
| I33 | JWT AT bị sửa một byte payload, chữ ký cũ | Reject invalid signature |
| I34 | JWT dùng `alg=none` | Reject theo signed AT policy |
| I35 | JWT có `alg` không nằm allowlist | Reject, không algorithm downgrade |
| I36 | JWT có `kid` không có trong trusted issuer JWKS | Không tự tin key khác; reject nếu fetch trusted JWKS không giải quyết được |
| I37 | JWT header `jku` tới attacker domain | RS không fetch untrusted URL |
| I38 | JWT ký bởi AS-B nhưng `iss` khai AS-A | Reject trust/signature/issuer mismatch |
| I39 | JWT ký đúng issuer nhưng `aud=payments-api` | Orders từ chối sai audience |
| I40 | JWT đúng issuer, không có `aud` bắt buộc theo AT profile | Reject |
| I41 | JWT hết hạn `exp` | Reject, có test sát clock skew boundary |
| I42 | JWT `nbf` ở tương lai | Reject trước thời gian hợp lệ |
| I43 | JWT có `iat`/TTL bất thường theo AS profile | Reject khi vi phạm configured token policy |
| I44 | JWT là ID token `aud=sales-dashboard`, không phải AT | RS từ chối token-purpose confusion |
| I45 | JWT đúng signature/aud/exp nhưng không có `orders.read` | RS trả 403/insufficient_scope |
| I46 | JWT hợp lệ nhưng user tenant khác | RS từ chối object-level ACL |
| I47 | JWT local valid sau AS revoke grant, chưa hết `exp` | Test chứng minh **offline verification không biết revoke** nếu không thêm state check |
| I48 | Rotation JWKS: token cũ ký bởi key còn được phép | RS verify theo key-lifecycle policy |
| I49 | Rotation JWKS: token mới `kid` chưa cache, JWKS tạm outage | Không chấp nhận thiếu trusted key |
| I50 | Signing key compromise và AS rút key | RS áp trust update/incident policy, không lặng lẽ accept |
| I51 | JWT sai audience được hybrid code gửi introspection, AS `active=true` | Hybrid vẫn từ chối; không token-laundering qua fallback |
| I52 | High-risk route yêu cầu live status nhưng introspection down | Không fallback local-only trái security policy |
| I53 | Token loại opaque bị parser JWT báo lỗi | Chỉ route qua opaque profile đã cấu hình, không tùy ý retry tất cả AS |
| I54 | Multi-issuer: `iss` từ token chưa verified chứa URL attacker | Không gửi token/RS secret tới URL lạ, không SSRF |
| I55 | Logs/metrics có raw `Authorization`/`token`/RS client secret | Redaction test phải phát hiện và sửa |

### 16.1. Test đối chứng chứng minh introspection `active` thật sự được dùng

~~~text
Setup:
  AS test tin cậy, RS credentials hợp lệ.
  Opaque token T1 active, aud=orders-api, scope=orders.read.
  Opaque token T2 revoked, metadata tương tự.

Positive:
  GET /orders/1 with T1 -> passes token validation.
  Object ACL có thể allow theo fixture.

Negative:
  GET /orders/1 with T2 -> 401 invalid_token.

Infrastructure negative:
  AS introspection URL invalid or client secret wrong -> fails closed,
  but DO NOT count it as proof that T2 was checked as inactive.
~~~

Nếu cả T1 và T2 đều 401 vì AS cert không hợp lệ, hệ thống **chưa chứng minh** introspection parser xử lý `active` đúng.

### 16.2. Test đối chứng JWT signature và audience

Tạo JWT test với signing key được RS trust (không dùng production key):

~~~text
J1: valid signature, iss=trusted, aud=orders-api,
    exp valid, typ=AT, scope=orders.read
    -> accepted at token layer.

J2: same fields, modified payload but old signature
    -> reject SIGNATURE.

J3: valid signature, aud=payments-api, all else same
    -> reject AUDIENCE.

J4: valid signature, correct audience, exp in past
    -> reject EXPIRY.

J5: OIDC ID token with aud=client-id, valid OP signature
    -> reject TOKEN PURPOSE / AUDIENCE at orders-api.
~~~

Nếu JWT parser luôn từ chối do `kid` thiếu trusted key, không kết luận audience/time/profile validators đúng. Mỗi negative test cần một đối chứng positive cùng issuer/key/profile.

### 16.3. Test cache freshness bằng fake clock

~~~text
T0:
  AS introspection T -> active=true, exp=T0+300s
  RS cache TTL=10s

T0+1s:
  AS revokes T

T0+5s:
  RS may still rely on cached result IF policy allows this delay

T0+10s:
  Cache expires
  Next request introspects T -> active=false
  RS rejects
~~~

Đây là timeline thiết kế, không bảo đảm **mọi** request đúng T0+10 đều nhìn thấy AS revoke nếu replication/network/cache layers chưa nhất quán. Test phải đo thực tế từ thời điểm revoke commit đến **lần request đầu tiên được RS từ chối** và xác nhận SLA.

Test thêm khi `exp` chỉ còn 3 giây mà cache positive TTL 30 giây: effective cache TTL **không được vượt 3 giây** (trừ khi policy clock skew/contract có quy tắc nghiêm ngặt hơn). Test với cached response không có `exp` để ngăn vô hạn.

### 16.4. Test network partition và key rotation

Hai harness riêng:

**Introspection path:**

~~~text
AS available → T1 active, T2 inactive.
AS unavailable → RS returns service error or approved still-fresh cache.
Cache expired → RS must not grant new access.
AS recovers → RS introspects again, updates status.
~~~

**JWT path:**

~~~text
Trusted old key cached → token signed by old key can verify per policy.
JWKS unavailable + unknown kid → token cannot be verified.
JWKS rotates → RS eventually sees new key via trusted JWKS.
Compromised key retired → RS rejects according to incident policy.
~~~

Không test bằng cách tắt validation để “giữ service sống”; đó là thay đổi security requirements.

### 16.5. Test authorization sau xác minh token

Một AT có `active=true` hoặc JWS signature valid, `aud=orders-api` và `scope=orders.read` vẫn phải qua:

~~~text
Order 1 belongs to Alice, tenant A → May allow.
Order 2 belongs to Bob, tenant A   → Deny unless domain policy grants.
Order 3 belongs to tenant B        → Deny cross-tenant.
Write /orders/1 with read scope    → Deny insufficient authorization.
~~~

Không dùng cùng kết quả token validation làm bằng chứng authorization cho nhiều object nếu domain policy khác nhau. Khi cache domain decision, cần TTL/invalidation riêng và test quyền thay đổi trong lúc token còn hạn.

## 17. Metrics và quy trình đưa hệ thống vào production

### 17.1. Metrics cho introspection

| Metric minh họa | Cần đo gì? | Tại sao quan trọng |
| --- | --- | --- |
| `introspection_requests_total` | QPS theo AS/RS/status | Phát hiện retry storm, tải không cân đối |
| `introspection_latency_seconds` | p50/p95/p99 của introspection HTTP | Biết network/AS đang ảnh hưởng API latency |
| `introspection_active_false_total` | Số token inactive theo RS/route | Phát hiện replay/expired/revoked patterns; tránh tiết lộ token |
| `introspection_transport_errors_total` | TLS, timeout, DNS, 429/5xx | Tách network outage khỏi token invalid |
| `introspection_cache_hit_ratio` | Cache hits/misses và TTL hiệu lực | Đánh đổi AS load với freshness |
| `introspection_cache_staleness_seconds` | Tuổi kết quả `active=true` khi được sử dụng | Xác minh không vượt revocation budget |
| `introspection_rs_auth_fail_total` | 401/403 từ endpoint | Secret rotation, trust config hoặc lạm dụng |
| `token_revocation_visibility_seconds` | Thời gian revoke tại AS → RS reject | Kiểm chứng SLA end-to-end |

Tên metrics là **ví dụ thiết kế**, không phải chuẩn Spring/RFC. Không đưa raw token, `sub`, email, client secret hoặc các giá trị PII vào metrics labels có cardinality cao.

### 17.2. Metrics cho JWT local verification

| Metric minh họa | Ý nghĩa |
| --- | --- |
| `jwt_signature_invalid_total` | Token bị sai chữ ký hoặc key/algorithm không hợp lệ |
| `jwt_claims_invalid_total` theo reason | Token sai issuer, audience, expiry, not-before, type |
| `jwks_refresh_success_total` / `jwks_refresh_failure_total` | Key lifecycle và metadata availability |
| `jwks_cache_age_seconds` | Độ cũ của trusted key material theo policy |
| `token_wrong_audience_total` | Cross-resource token forwarding hoặc cấp sai audience |
| `token_type_confusion_total` | ID/RT/client assertion bị dùng như API AT |
| `domain_authorization_denied_total` | Object/tenant ACL từ chối dù token hợp lệ |
| `revocation_status_lookup_total` (nếu có) | Phụ thuộc state bổ sung trong hybrid |

Đừng log JWT payload đầy đủ chỉ để phân loại `invalid_token`. Có thể dùng error reason code, issuer registration ID, correlation ID không bí mật và sampling.

### 17.3. Quy trình chuyển từ opaque introspection sang JWT local

Không thay đổi decoder production một lần rồi hy vọng API behavior giữ nguyên. Một migration có kiểm soát:

1. Ghi lại **token contract** hiện tại: issuer, RS identity, audience, scopes, token type, expiry, revocation SLA.
2. Xác định profile JWT mới: ký JWS nào, `typ`/claims/alg/JWKS nào, key rotation và expected audiences.
3. Giữ nguyên domain authorization, phân biệt OAuth scopes/roles và principal types.
4. Dựng bộ **positive/negative tests song song** cho opaque và JWT: happy path, wrong aud, wrong issuer, revoked, expired, ID token confusion.
5. Ước lượng tác động bỏ live AS state: user disable/consent withdrawal và key compromise.
6. Nếu cần, thêm denylist/state-check cho high-risk routes trước rollout.
7. Canary theo client/route, giám sát auth failures, AS QPS, latency và unauthorized access signals.
8. Rollback **không được** mở đường fallback chấp nhận token sai signature/audience.

Nếu lý do migration chỉ là giảm latency, hãy đánh giá **introspection caching/single-flight** và AS capacity trước, thay vì mặc định JWT là cách duy nhất.

### 17.4. Quy trình chuyển JWT local sang introspection

Ngược lại, nếu muốn revoke nhanh hơn bằng introspection:

1. Xác nhận AS hỗ trợ introspect JWT đang phát hành hoặc sẽ chuyển sang opaque AT.
2. Đăng ký **resource-server client** có quyền introspect đúng audience/token class.
3. Xác định metadata bắt buộc: `active`, issuer, audience, scope, principal, expiry; kiểm chứng schema thực tế.
4. Đặt timeouts, circuit breaker, concurrency và cache TTL theo security budget.
5. Đo AS load và p99 latency khi cache misses/revocation.
6. Đảm bảo fail closed khi AS lỗi hoặc thiếu metadata, không chấp nhận `active=true` vô điều kiện.
7. Kiểm thử user/client disable, grant revoke, key compromise và token replay.

Một giải pháp introspection an toàn cần **nguồn identity/authorization đáng tin**, không chỉ một đường HTTP hoạt động.

### 17.5. Quy trình xử lý sự cố

Khi phát hiện token giả hoặc bị phát lại:

1. Khoanh vùng token type (JWT/opaque), issuer, audience, client, grants và routes liên quan.
2. Revoke RT/AT/grant hoặc khóa account/client theo policy.
3. Nếu JWT signing key bị lộ, xử lý rotation và key-trust emergency theo incident plan.
4. Đánh giá cache `active=true` còn sống, JWKS cache, authorization decision cache và regional propagation.
5. Thực thi denylist/state controls nếu revoke SLA yêu cầu chặn ngay.
6. Xem audit bằng **token fingerprint/correlation ID**, không copy raw bearer token vào tickets/chat.
7. Cập nhật tests và monitoring để phát hiện các đường fail-open/cross-audience sau sự cố.

Không giả định đổi client secret của RS introspection sẽ tự revoke mọi access token đã phát hành: đây là những credential và trust relationships khác nhau.

## 18. Checklist quyết định và cấu hình an toàn

### 18.1. Xác định token và trust model

1. **Đúng loại token:** RS chỉ chấp nhận OAuth access token; ID token/RT/client assertion không được dùng như bearer AT?
2. **Đúng format:** Token là signed JWT JWS, opaque, JWE hay một profile đặc biệt? Parser/validator có đúng loại?
3. **Expected issuer:** AS nào được RS tin, có allowlist/discovery metadata đáng tin và TLS?
4. **Expected audience:** Mỗi RS xác minh token đúng resource của mình, kể cả cùng issuer với API khác?
5. **Scope/subject:** Granted scopes, user-vs-service identity, actor/tenant context được mapping đúng?
6. **Domain ACL:** Object ownership/tenant/role được kiểm ở route/service layer, không chỉ từ token active?

### 18.2. Nếu dùng RFC 7662 introspection

7. **Endpoint trust:** Introspection URL đến từ AS cấu hình tin cậy, không từ token/header do client cung cấp?
8. **RS authentication:** RS có identity/credential đã được cấp quyền, TLS và secret management?
9. **Request:** HTTPS POST form có `token`, optional `token_type_hint`; không tin hint là proof?
10. **Response:** `active` boolean bắt buộc được kiểm tra; `active=false` luôn dẫn đến từ chối?
11. **Metadata:** Issuer, audience, scope, token purpose, expiry được AS trả/đảm bảo theo contract đủ cho RS?
12. **AS caller restriction:** RS orders không thể dùng metadata/caching của payments trái quyền?
13. **Cache TTL:** Positive cache giới hạn bởi `exp`/revocation SLA; không stale-unbounded?
14. **Cache key:** Có issuer/RS identity/resource policy và không làm lộ raw token?
15. **Failure semantics:** 401/403 RS auth, 429/5xx, timeout, TLS lỗi được fail closed và không biến thành `active=true`?
16. **Load control:** Timeout, bounded concurrency, retry/backoff, single-flight và monitoring?

### 18.3. Nếu dùng JWT local validation

17. **Signature:** Verify JWS trên raw signing input với allowed algorithms, đúng trusted keys?
18. **Key trust:** JWKS URL và issuer được cấu hình; không follow untrusted `jku`/`x5u`?
19. **Claims:** `iss`, `aud`, `exp`, `nbf`, `iat`/TTL và scope theo token profile?
20. **Type:** Không chấp nhận OIDC ID token, RT, client assertion hoặc JWT sai `typ`?
21. **Clock skew:** Leeway nhỏ, clocks được sync và có boundary tests?
22. **Rotation:** Key rollovers, unknown `kid`, JWKS outage/compromise được xử lý có kiểm soát?
23. **Revocation:** Có chấp nhận AT còn hạn sau grant revoke? Nếu không, đã thêm state check/denylist hoặc TTL ngắn?
24. **Resource ACL:** Signature/claims đúng vẫn không thay owner/tenant object authorization?

### 18.4. Nếu dùng hybrid

25. **Đường xử lý tin cậy:** Token profile nào đi JWT, token nào introspect, decision đến từ config/issuer registration?
26. **Không fallback yếu:** JWT wrong signature/aud/typ không được cứu bởi `active=true` không kiểm profile?
27. **High-risk freshness:** Khi cần live status, AS outage không kích hoạt local-only fallback trái SLA?
28. **Hai validator độc lập:** Introspection state và local JWT claims/authorization được kết hợp bằng policy rõ, không phủ định nhau?
29. **Cache consistency:** JWKS cache, token-status cache và domain authorization cache có TTL/invalidation riêng?
30. **Tests:** Có đối chứng dương/âm cho mọi đường, key rotation, revocation, AS outage, multi-issuer và cross-tenant access?

## 19. Câu hỏi tự kiểm tra

**Câu 1. Token introspection là gì?**

RS gửi token qua HTTPS POST đến endpoint của AS được tin cậy và được cấp quyền gọi, nhận `active` cùng metadata được phép. Introspection có thể áp cho opaque AT và cả JWT AT nếu AS hỗ trợ.

**Câu 2. Vì sao `active=true` chưa đủ để cho phép truy cập API?**

Vì token có thể dành cho **resource khác**, thiếu scope hoặc principal không có quyền trên object. RS còn phải xác minh purpose, expected issuer/audience và domain ACL theo contract.

**Câu 3. HTTP 200 với `{"active":false}` có nghĩa AS bị lỗi không?**

Không. Đây có thể là một **introspection response hợp lệ** nhưng token không active/không được phép introspect. RS phải từ chối AT. Lỗi RS authentication thường có HTTP 401/403, infrastructure outage là loại lỗi khác.

**Câu 4. RFC 7662 có buộc response active phải chứa `aud`, `iss` và `exp` không?**

Không. `active` là trường bắt buộc; các metadata khác tùy chọn/theo policy. Nếu RS cần audience để bảo mật, phải có **contract** trả metadata hoặc AS ràng buộc caller với resource theo cách đã kiểm chứng.

**Câu 5. `token_type_hint=access_token` có chứng minh request mang access token không?**

Không. Đây chỉ là gợi ý để AS tìm token hiệu quả hơn. RS/AS phải xác định token purpose thực tế; không chấp nhận refresh token hoặc ID token làm API AT chỉ dựa vào hint.

**Câu 6. Local JWT signature verification và JWT validation có phải một việc không?**

Không. Chữ ký chỉ xác nhận tính toàn vẹn/nguồn khóa. JWT validation còn cần expected issuer, audience, expiry/not-before, token type/profile, scope và domain authorization.

**Câu 7. JWT có thể được introspect không?**

Có, nếu AS hỗ trợ RFC 7662 cho token đó và cho RS gọi. JWT format không bắt buộc phải verify offline; policy có thể yêu cầu live revocation status.

**Câu 8. Nếu AS revoke grant, local JWT đã ký còn hạn tự mất hiệu lực không?**

Không. RS verify offline chỉ thấy thông tin cũ trong JWT; cần denylist/state check/introspection hoặc chờ `exp` theo policy.

**Câu 9. Opaque token introspection có luôn revoke tức thì không?**

Không. AS có thể propagate state chậm, RS cache `active=true` và request đang xử lý. Phải đo revocation visibility SLA cùng cache TTL.

**Câu 10. Khi AS introspection down, RS có nên tin token vì nó vừa được chấp nhận 10 phút trước?**

Chỉ khi **bounded cached result** còn trong thời hạn freshness được bảo mật/phân quyền phê duyệt và chưa vượt `exp`; không default allow hoặc stale vô hạn. Với route cần live state, phải fail closed.

**Câu 11. Khi JWKS URL tạm unreachable, local RS có thể tiếp tục hoạt động không?**

Có thể nếu RS đã có **trusted cached keys** còn hợp lệ theo policy và JWT verify đúng. Với unknown `kid` không có trusted key, phải từ chối, không tin key URL từ token.

**Câu 12. `kid` hoặc `jku` của JWT có thể xác định nơi RS tải khóa không?**

`kid` chỉ hỗ trợ chọn key **trong trusted key set**. Không được tự follow `jku`/`x5u` do attacker cung cấp để thay issuer/JWKS trust configuration.

**Câu 13. Tại sao RS cần client authentication ở introspection endpoint?**

Để AS xác định **caller nào** được xem trạng thái và metadata của token, giới hạn token probing và leakage. Đây là RS identity, không thay end-user authentication.

**Câu 14. Nếu token gửi đến orders có scope `orders.read` nhưng `aud=payments-api`, có thể allow không?**

Không. Scope không thay audience. Orders phải từ chối token dành cho payments, bất kể nó active hay signature đúng.

**Câu 15. Một RS có thể dùng cả JWT local và opaque introspection không?**

Có, nhưng cần trusted routing/profile rõ, không fallback từ JWT sai signature/audience sang `active=true` rồi bỏ checks. High-risk routes vẫn phải đáp ứng live-state policy.

**Câu 16. Vì sao cache introspection theo raw token trên một shared cache là rủi ro?**

Có thể lộ bearer token qua cache keys/logging, và có thể tái sử dụng kết quả `active=true` giữa RS identities/audiences khác nhau. Cache phải được bảo vệ, key phân vùng trust context và TTL giới hạn.

**Câu 17. Một JWT AT `exp` còn 10 phút có chứng minh quyền trên order không thay đổi trong 10 phút không?**

Không. Domain ACL/tenant/role có thể thay đổi độc lập với token expiry. Object-level authorization cần state phù hợp nghiệp vụ và chính sách freshness riêng.

## 20. Tài liệu chuẩn và nguồn tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `POST /introspect`, `token`, `token_type_hint`, `active`, metadata và security/privacy considerations.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization grants, client/AS/RS roles, access token, refresh token, scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization header, `401 invalid_token`, `403 insufficient_scope` và rủi ro token theft.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): RT/AT revocation, grant lifecycle và hạn chế của revocation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): access-token audience restriction, refresh token protection, replay và OAuth security BCP.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims `iss`, `sub`, `aud`, `exp`, `nbf` và `iat`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký và JWS signing input.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, public signing keys.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): phân biệt JWT mã hóa với JWT ký.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key trust, token confusion, issuer/audience/type validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT AT `typ`, claims, audience và resource server validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata/trusted endpoints, bao gồm introspection endpoint metadata khi AS công bố.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): scope token theo resource, audience restriction.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject/actor và downstream audience trong delegation.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens sau issuance.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token cho RP, khác OAuth AT dùng tại RS.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, trusted issuer/JWK, validation.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, authenticated introspection, authorities mapping.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token introspection endpoint và AS customization.

**Điểm cần ghi nhớ:** **Token introspection theo RFC 7662** hỏi AS đáng tin về **trạng thái và metadata của một token**; `active=true` là tín hiệu token đang active **cho ngữ cảnh introspection**, không tự cấp phép API. **Local signature validation** xác minh JWS/JWT ngay tại RS bằng issuer/JWKS tin cậy rồi kiểm tra **`iss`, `aud`, `exp`, token type/profile, scope**; nó có thể nhanh và ít phụ thuộc AS hơn nhưng **không tự phát hiện token đã bị revoke sau issuance**. **JWT cũng có thể introspect**, còn opaque token thường cần một trạng thái/metadata nguồn tin cậy. Mọi phương án đều phải bảo vệ RS credentials, TLS, cache freshness, key rotation, fail-closed behavior và **object/tenant authorization**. Quyết định chọn introspection, local JWT hay hybrid phải dựa trên **revocation SLA, latency, availability, token purpose và trust boundaries**, không chỉ dựa trên định dạng token.
