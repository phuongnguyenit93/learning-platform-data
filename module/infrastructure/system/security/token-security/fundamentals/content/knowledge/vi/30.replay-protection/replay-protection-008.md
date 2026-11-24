# Short lifetime

Giả sử Invoice API chấp nhận một **bearer access token** dùng để đọc hóa đơn của An. Token có chữ ký hợp lệ, đúng `aud` và `scope`. Một kẻ tấn công đã lấy được **nguyên chuỗi token** từ log của proxy hoặc từ một máy khách bị xâm nhập. Kẻ này không cần biết mật khẩu của An để thử phát lại request:

~~~http
GET /api/invoices/INV-42 HTTP/1.1
Host: invoice.example.test
Authorization: Bearer <stolen-access-token>
~~~

Nếu token còn hiệu lực và không bị ràng buộc với người gửi, Resource Server (RS) **có thể chấp nhận bản sao token**. Khi token có **short lifetime** (thời gian hiệu lực ngắn), kẻ tấn công có **ít thời gian hơn để sử dụng bản sao**. Nhưng token sống 3 phút vẫn có thể bị replay **ngay sau khi bị đánh cắp**.

**Kết luận đầu tiên:** **Short lifetime là biện pháp *giảm thời gian khai thác* (exposure/replay window), không phải cơ chế chống replay tuyệt đối.** Để ngăn người khác sử dụng bản sao token trong thời hạn hiệu lực, cần thêm **sender-constrained tokens** (như DPoP/mTLS), authorization đúng đối tượng, bảo vệ kênh và storage, thu hồi token/grant khi thích hợp.

Bài **“Short lifetime”** thuộc chương **Replay protection** của module **Security Token Security Fundamentals**. Bài giải thích:

- Vì sao rút ngắn lifetime của access token giảm rủi ro **token theft/replay**.
- Cách hiểu `exp`, `nbf`, `iat`, clock skew và thời điểm RS từ chối JWT/opaque token.
- Vì sao thời hạn của **access token**, **refresh token**, **authorization code**, **session** và **DPoP proof** không đồng nhất.
- Cách phối hợp token TTL với **issuer, audience, scope, introspection, revocation, refresh token rotation, DPoP/mTLS**.
- Cách chọn chính sách TTL theo rủi ro, Java/Spring Security minh họa, bài kiểm thử âm tính và checklist vận hành.

## 1. Replay là gì và “short lifetime” chặn được đến đâu?

**Replay attack** xảy ra khi một thông điệp hoặc credential đã được dùng hay quan sát trước đó được **trình lại** để hệ thống chấp nhận như một yêu cầu hợp lệ. Với OAuth 2.0 Bearer token, attacker có thể đơn giản sao chép giá trị token rồi gửi tới API. Không cần sửa JWT claims, giả chữ ký hay giải mã JWE.

### Phân biệt các tình huống

| Tình huống | Điều attacker có | Short lifetime giúp gì? | Cần thêm gì? |
|---|---|---|---|
| Lộ access token Bearer qua log | Toàn bộ chuỗi token | Giảm thời gian token còn được RS chấp nhận | Redact log, revoke, audience/scope, sender binding |
| MITM thu được token do HTTP sai cấu hình | Token trên đường truyền | Token sớm hết hạn hơn | **TLS** với xác minh server, không truyền Bearer qua HTTP |
| Token bị copy ở máy khách | Access token trong memory/storage | Thu hẹp cửa sổ sử dụng bản sao | Storage hardening, BFF nếu phù hợp, DPoP/mTLS |
| Đánh cắp refresh token | Refresh token dài hạn | TTL ngắn của access token **không đủ** | Refresh rotation, reuse detection, sender binding, revoke family |
| Phát lại DPoP proof đã ký | Một JWT proof cho method/URI/token | Proof TTL ngắn giới hạn thời gian | `jti` replay store, `htm`/`htu`/`ath`, nonce policy |
| Lặp lại POST thanh toán | Access token + request cũ | Sau token expiry thì bị chặn | Idempotency key, transaction binding và business state |
| Authorization code bị lấy trước token exchange | Authorization code | Code TTL ngắn giảm thời gian sử dụng | **Single-use**, client binding và PKCE |

**Không nhầm hai loại replay:** (1) phát lại **credential/token** để vượt authentication/authorization, và (2) phát lại **business operation** như chuyển tiền để gây tác động lần hai. Một token mới hoàn toàn vẫn có thể gọi lại POST nếu API không có business idempotency.

### Threat model nền tảng

~~~text
Authorization Server (AS)
  |
  | issue access token A1, exp=T0+300s
  v
Client / BFF --- Authorization: Bearer A1 ---> Invoice API (RS)
     |
     +--- token leaked at T0+60s ---> Attacker
                                         |
                                         +-- replay at T0+65s  -> có thể thành công
                                         +-- replay at T0+299s -> có thể thành công
                                         +-- replay at T0+301s -> phải bị từ chối
                                             (trừ clock leeway hợp lệ đã cấu hình)
~~~

Lifetime không làm token “chỉ dùng một lần”. Nếu access token được thiết kế để gọi API nhiều lần, **cùng token hợp lệ có thể được dùng nhiều request hợp pháp**; một cơ chế đánh dấu `jti` đã nhìn thấy rồi cấm mọi request tiếp theo sẽ phá chức năng bình thường.

## 2. “Lifetime” của loại token nào?

Khi nói “giảm token lifetime”, trước tiên cần xác định **credential, chủ thể và bên kiểm thời hạn**.

| Đối tượng | Được phát/đặt bởi | Mục đích | Vì sao TTL phải khác? |
|---|---|---|---|
| **Access token** | AS theo client/resource/scope policy | Client gọi RS | Cần ngắn để giảm bearer replay window |
| **Refresh token** | AS khi grant/client được phép | Client xin access token mới | Có thể dài hơn nhưng phải bảo vệ mạnh; cần idle/absolute lifetime, rotation/reuse policy |
| **Authorization code** | AS trong OAuth Authorization Code Flow | Client đổi code một lần tại token endpoint | **Ngắn và single-use**, PKCE/client binding |
| **Device code / user code** | AS trong Device Authorization Grant | Cho thiết bị chờ user approve | `expires_in` phù hợp UX; không phải access token |
| **OIDC ID token** | OP | RP xác minh authentication event | `exp` bảo vệ việc chấp nhận ID token, **không** là TTL của API access token |
| **DPoP proof JWT** | Client sở hữu DPoP private key | Chứng minh request hiện tại gắn với key, method, URI và token | **Rất ngắn, có `jti`/replay detection**; không thay access-token lifetime |
| **RP/browser session** | Ứng dụng/RP | Duy trì phiên trình duyệt | Idle timeout/absolute timeout, logout khác token `exp` |
| **Introspection cache entry** | RS theo policy | Giảm cuộc gọi AS khi kiểm opaque/reference token | TTL phải ngắn hơn/không vượt token `exp` và phù hợp revoke SLO |

### Hai loại đồng hồ

Một hệ thống có thể có hai cơ chế đồng thời:

- **Protocol validity:** JWT `exp`, `nbf`, AS token status, `expires_in` tại issuance.
- **Application/session validity:** user session idle timeout, logout, account disable, grant revoke, risk reevaluation.

Token chưa tới `exp` **không đảm bảo** phiên ứng dụng vẫn active; và session còn active **không cho phép** RS bỏ qua `exp` của access token.

### Một API có nên tự quyết định token TTL?

**AS là nơi quyết định thời gian cấp token** theo registration, scope, resource, grant và policy. RS có trách nhiệm **kiểm** thời hạn, có thể áp thêm chính sách “chỉ chấp nhận access token có lifetime tối đa L” nếu AS/RS đã thỏa thuận.

Không cho một client tự truyền `expires_in=86400` lên token endpoint rồi coi đó là quyền được nhận token một ngày; AS phải thực thi policy của mình. Resource Server cũng không được tin tham số `ttl` do browser gửi để kéo dài JWT.

## 3. JWT `exp`, `nbf`, `iat`: ba mốc thời gian không thay thế nhau

Các JWT claims phổ biến theo **RFC 7519** dùng **NumericDate**, về cơ bản là số giây kể từ Unix epoch (UTC) cho giá trị thời điểm:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "client_id": "invoice-web",
  "scope": "invoice:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "jti": "access-token-id-example-01"
}
~~~

Đây là **payload minh họa**, chưa phải JWT đã ký. `exp - iat = 300 giây` trong ví dụ, **chỉ khi hai claim thực sự mô tả issuance và expiry của cùng token**. Không dùng payload tự decode mà chưa verify signature để ra quyết định.

| Claim | Ý nghĩa | Luật cơ bản |
|---|---|---|
| **`exp`** | Token expiration time | RS **không** chấp nhận khi current time **không còn trước `exp`** (với leeway nhỏ nếu policy cho phép) |
| **`nbf`** | Not-before time | RS không chấp nhận token trước mốc `nbf` (trừ leeway nhỏ) |
| **`iat`** | Issued-at time | Hữu ích cho tuổi token/kiểm sanity; **không thay `exp`** |
| `jti` | JWT identifier | Giúp audit/denylist/dedupe theo contract; **không mặc nhiên làm token single-use** |
| `auth_time` (OIDC) | User authentication time | **Không phải `iat`**; dùng cho reauthentication/step-up freshness theo OIDC policy |

### Các bất biến thời gian

Với trusted current time `now` và cho phép clock tolerance nhỏ `δ`:

~~~text
Valid timing (đơn giản hóa):
  exp exists under local profile
  now < exp + δ
  now + δ >= nbf     (khi nbf có mặt)
  iat <= now + δ     (khi iat có mặt/được policy yêu cầu)
  exp > iat          (nếu profile dùng cả hai cho token lifetime)

Optional stricter policy:
  exp - iat <= maximumIssuedLifetime
~~~

**Leeway làm cửa sổ chấp nhận có thể dài hơn thời hạn công bố**; bởi vậy không dùng `δ` quá lớn chỉ để che đồng hồ sai. Với endpoint yêu cầu giới hạn tuyệt đối, kiến trúc có thể đặt `δ=0` hoặc cho phép một mức nhỏ được review. RFC 7519 cho phép leeway nhỏ để xử lý clock skew nhưng **không quy định cố định “phải 60 giây”**.

### Timestamp là số giây, không phải mili giây

~~~text
iat = 1800000000   // Unix seconds
exp = 1800000300   // Unix seconds (sau 300 s)

Sai:
  Instant.ofEpochMilli(exp)

Đúng:
  Instant.ofEpochSecond(exp)
~~~

Một lỗi chuyển đổi mili giây/giây có thể làm token bị coi hết hạn ngay hoặc được cho phép sai rất lâu.

### `exp` hợp lệ nhưng `iss`/`aud` sai vẫn phải từ chối

~~~text
Token A:
  exp = future
  aud = invoice-api
  scope = invoice:read

Token B:
  exp = future
  aud = payroll-api
  scope = invoice:read

Invoice API:
  A -> có thể tiếp tục kiểm các điều kiện khác.
  B -> REJECT: wrong audience, dù chưa hết hạn.
~~~

Token **còn hạn** không có nghĩa nó được dùng ở **mọi API**. Mỗi RS cần kiểm issuer, audience, token type/profile, scopes, client/subject, signature hoặc introspection và quyền object.

## 4. Replay window và vì sao lifetime ngắn chỉ “giảm xác suất”

Giả sử AS phát Bearer access token tại `T_issue`, expiry tại `T_exp`; attacker sao chép token ở `T_leak`.

Nếu không có sender-binding, revocation hoặc kiểm soát bổ sung, thời gian còn lại attacker **có thể thử** sử dụng bản sao là:

\[
W_{\mathrm{replay}}=\max(0,T_{\mathrm{exp}}-T_{\mathrm{leak}})
\]

Nếu RS áp clock leeway `δ`, cửa sổ chấp nhận trong tình huống xấu có thể kéo dài thêm `δ`. Nếu AS/RS revoke sớm và mọi RS biết trạng thái revoke, cửa sổ thực tế có thể ngắn hơn; **công thức chỉ là mô hình đơn giản**.

### Ví dụ trực quan

Token được phát tại T=0; attacker đánh cắp token sau 60 giây:

| Token lifetime | Thời điểm expiry | Thời gian còn để replay nếu không bị chặn |
|---|---:|---:|
| 1 giờ | T+3.600 s | 3.540 s |
| 15 phút | T+900 s | 840 s |
| 5 phút | T+300 s | 240 s |
| 2 phút | T+120 s | 60 s |

Các giá trị là **phép tính minh họa**, không phải xác suất hoặc khuyến nghị TTL chung. Nếu kẻ tấn công replay ngay ở `T+61s`, cả bốn token **đều còn hiệu lực** trong kịch bản này.

### Đồ thị timeline replay

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant C as Client
    participant X as Attacker
    participant RS as Resource Server
    AS-->>C: T0: cấp Bearer A1 (exp=T0+300s)
    C->>RS: T0+10s: request hợp lệ
    Note over C,X: T0+60s: A1 bị lộ từ log
    X->>RS: T0+65s: replay A1
    RS-->>X: Có thể 200 nếu token/quyền còn hợp lệ
    X->>RS: T0+301s: replay A1
    RS-->>X: 401 invalid_token (đã hết hạn, nếu không leeway)
~~~

**Không suy từ thời hạn ngắn rằng nguy cơ mất dữ liệu nhỏ:** Trong 60 giây, attacker có thể thực hiện **nhiều request song song**. Vì vậy vẫn cần rate limiting, least privilege, object-level authorization, monitoring, token binding hoặc transaction approval theo độ nhạy.

### Giảm quyền song song với giảm thời gian

Một token có `aud=invoice-api` và `scope=invoice:read` sẽ có **phạm vi khai thác nhỏ hơn** token dùng được ở mọi API với quyền admin, dù chúng có cùng TTL. Một token được mã hóa bằng JWE vẫn có thể **replay nguyên ciphertext** nếu là Bearer.

Do đó, chiến lược thường là kết hợp **TTL ngắn + audience hẹp + scope tối thiểu + transport/storage an toàn + revocation/sender binding**.

## 5. Chọn access-token lifetime theo rủi ro và nhu cầu vận hành

Không tồn tại một thời hạn **phổ quát bắt buộc** cho mọi OAuth access token. AS/RS phải cân nhắc rủi ro replay, thiết bị/client, độ nhạy API, khả năng renew, SLA của AS, đồng bộ đồng hồ và chi phí validation.

| Nhóm hệ thống minh họa | TTL ví dụ để thảo luận | Các điều kiện bổ sung quan trọng |
|---|---|---|
| API đọc dữ liệu ít nhạy cảm trong BFF | 10–15 phút | TLS, server-side storage, scope/audience hẹp |
| API nhạy cảm có khách hàng dùng browser | 2–5 phút | BFF hoặc sender-binding, refresh bảo vệ mạnh, revocation SLO |
| Server-to-server workload nội bộ | 5–15 phút | Workload identity, client authentication, mTLS/DPoP và rotation |
| Hành động phê duyệt tài chính một lần | Access token vài phút **chưa đủ** | Transaction binding, fresh authentication, idempotency và anti-fraud |
| Offline/batch job chạy lâu | Token ngắn và renew có kiểm soát | Không tạo “token sống nhiều ngày” chỉ vì job dài; checkpoint/retry |

**Tất cả con số trong bảng chỉ là ví dụ thiết kế**, **không phải normative TTL từ RFC**. Có hệ thống cần thời hạn khác; phải lượng hóa dữ liệu, latency, outage, số lượng token issue/refresh và rủi ro lộ credential trước khi chọn.

### Chính sách có thể phụ thuộc ngữ cảnh

Một AS có thể dùng các biến:

~~~text
token_lifetime_policy(
  registered_client,
  grant_type,
  requested_resource,
  granted_scopes,
  sender_constrained_or_bearer,
  risk_class,
  session_policy
) -> approved_lifetime
~~~

Quyết định cuối phải do **AS tin cậy** thực thi. RS có thể kiểm thêm **maximum token lifetime** theo hợp đồng để phòng một issuer phát nhầm token dài hoặc client nhận nhầm profile.

### Tránh việc có token “ngắn” chỉ trên giấy

~~~text
AS trả:
  expires_in = 300

JWT thực tế:
  iat = 1800000000
  exp = 1800086400   // 24 giờ

BAD:
  Client tin mỗi expires_in để biết token sống 5 phút.
  Resource Server chỉ kiểm exp nên token được nhận cả ngày.
~~~

Đây là lỗi **phát token không nhất quán**. AS cần tự kiểm issuance policy, RS kiểm đúng `exp`/max lifetime, và integration test so metadata `expires_in` với claims/trạng thái token khi profile cung cấp cả hai.

### Token TTL không nên phụ thuộc đồng hồ client

Client có thể dùng `expires_in` để **chủ động renew trước khi hết hạn**, nhưng **không quyết định quyền chấp nhận token tại RS**. Browser bị chỉnh clock, sleep hoặc resume không được làm API bỏ kiểm expiry.

## 6. AS phát token: ràng buộc `iat`, `nbf`, `exp` và `expires_in`

Khi phát token JWT, AS phải tạo thời gian bằng nguồn clock tin cậy và đồng bộ:

~~~text
now = trusted AS clock
lifetime = policyFor(client, scope, audience, grant)   // ví dụ 300s

iat = now
nbf = now                          // hoặc theo profile
exp = now + lifetime

OAuth token response:
  access_token = signed JWT or opaque reference
  token_type = Bearer / profile
  expires_in = lifetime (nếu được cung cấp)
~~~

### OAuth token response minh họa

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<redacted-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "invoice:read",
  "refresh_token": "<redacted-refresh-token>"
}
~~~

`refresh_token` là **tùy chọn**, phụ thuộc grant/client/policy. Không suy rằng mọi token response luôn có refresh token hoặc refresh token cũng hết hạn sau 300 giây. **`expires_in` trong token response mô tả lifetime của access token**, không có nghĩa thời hạn refresh token hay OIDC browser session.

### Bảo vệ issuance ở nhiều node

- **Đồng bộ clock AS** giữa các region/node; không phát token có `exp` ở quá khứ hoặc lifetime ngoài policy.
- Áp **client registration, audience/resource indicator, scope, grant type** trước khi chọn TTL.
- Không để client chỉ định `exp` bằng input chưa được tin.
- Nếu phát **opaque token**, AS lưu/đảm bảo expiry trong token state và trả trạng thái `active=false` qua introspection khi hết hạn theo contract.
- Sử dụng ký JWT đúng **alg/key/issuer profile**; chỉ tạo `iat`/`exp` đẹp không thể thay chữ ký.
- Nếu dùng JWT access token profile **RFC 9068**, tuân thủ cả các claims/token type và validation requirements tương ứng.

### Authorization code cũng “short lifetime” nhưng không giống access token

Authorization code trong Authorization Code Flow thường có hiệu lực rất ngắn và phải **single-use**, ràng buộc với client, redirect URI và PKCE verifier theo thiết kế. **TTL ngắn một mình không chặn attacker đổi code bị đánh cắp trước client**. Tương tự, device code và user code có `expires_in` để giới hạn phiên user authorization, nhưng không thể thay kiểm code binding, user approval và polling policy.

## 7. JWT offline và opaque token: expiry cùng mục tiêu, cách thực thi khác nhau

**JWT access token** có thể chứa `exp` ngay trong payload; sau khi kiểm chữ ký và profile, RS tự quyết định có chấp nhận token. **Opaque access token** thường chỉ là một reference, nên RS phải hỏi AS qua introspection hoặc cơ chế validation đã thỏa thuận.

| Khía cạnh | JWT access token được RS kiểm offline | Opaque/reference token qua introspection |
|---|---|---|
| **Expiry nằm ở đâu?** | `exp` trong JWT đã ký | Token state/metadata tại AS; introspection có thể trả `exp` |
| **Ai xác nhận còn hiệu lực?** | RS kiểm chữ ký, `exp`, `nbf` và claims | AS trả `active`; RS kiểm response/trust contract và claims |
| **Revoke trước expiry** | Không tự có khi chỉ kiểm offline; cần denylist/event/introspection | AS có thể trả `active=false`, phụ thuộc cache/availability |
| **Thay đổi scope/audience sau issuance** | Token cũ không tự thay claims; RS cần policy bổ sung hoặc token mới | AS có thể phản ánh trạng thái động theo introspection contract |
| **Khi AS outage** | RS vẫn có thể kiểm JWT đã phát còn hạn | Không thể introspect mới nếu không có cache hợp lệ |
| **Rủi ro replay** | Bản sao Bearer token còn hạn có thể dùng | Tương tự, nếu active và Bearer token còn được chấp nhận |

### JWT signature không ngăn replay

~~~text
JWT token A1:
  signed by AS, valid iss/aud/scope/exp

First legitimate request:
  GET /invoices/INV-42 with A1
  -> 200

Attacker copies exact A1:
  GET /invoices/INV-42 with A1
  -> may also be 200 before exp

RS verifies signature both times:
  signature == valid for both requests.
~~~

Chữ ký chứng minh token **chưa bị thay đổi bởi bên không có signing key**, nhưng không chứng minh **request hiện tại thực sự do client ban đầu gửi**. Nếu muốn ràng buộc token với người gửi, cần proof-of-possession.

### Opaque introspection cũng không tự chống replay

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-rs-introspection-credential>
Content-Type: application/x-www-form-urlencoded

token=<percent-encoded-access-token>&token_type_hint=access_token
~~~

Response khi AS vẫn chấp nhận token:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "invoice-api",
  "scope": "invoice:read",
  "exp": 1800000300,
  "client_id": "invoice-web",
  "sub": "user:an"
}
~~~

**`active=true` không phải bằng chứng token chưa từng bị sao chép.** Nó chỉ nói AS coi token active theo contract tại thời điểm kiểm. RS vẫn cần đúng audience, issuer, token type/purpose, scope, subject/tenant/object và proof sender nếu có.

Nếu AS trả `{"active":false}`, RS **không** tiếp tục cho phép API. Nếu introspection lỗi HTTP/TLS/timeout, không được coi lỗi đó như `active=true`.

## 8. Cache introspection và revocation làm thay đổi cửa sổ replay

Một access token có TTL 5 phút nhưng RS cache `active=true` **sai cách** trong 1 giờ có thể tạo lỗ hổng: RS đang dùng **quyết định cũ** thay vì kiểm expiry/revocation.

### Trục thời gian một token bị revoke

~~~text
T0=10:00:00  AS phát opaque A1, expires at 10:05:00.
T1=10:00:30  RS introspect -> active=true; cache TTL 30s.
T2=10:00:35  User/security team revoke A1 tại AS.
T3=10:00:40  Attacker replay A1.
              RS còn cache active=true -> có thể vẫn nhận.
T4=10:01:01  Cache expired, RS introspect lại -> active=false.
              Attacker bị từ chối.
~~~

**Nếu hệ thống yêu cầu chặn token đã revoke trong 10 giây, cache active 30 giây không có invalidation là không đủ**, dù token gốc có TTL 5 phút. Phải chọn TTL theo **revoke propagation SLO**, khả năng AS và rủi ro replay.

### Hai deadline khác nhau

Khi cache `active=true`:

1. **Token expiration deadline:** `exp` do AS xác nhận (nếu response cung cấp) hoặc thời hạn tin cậy của token state.
2. **Introspection response cache deadline:** `now + cacheTtl`, nhưng không được vượt token expiry và phải tuân HTTP cache-control/AS contract.

Một công thức thiết kế conservative khi có `exp`:

\[
TTL_{\text{usable}}
=\max\left(0,\min\left(
TTL_{\text{configured}},
T_{\text{exp}}-T_{\text{now}}-\Delta
\right)\right)
\]

Trong đó `Δ` là safety margin được review cho clock skew, thời gian network và operation. **RFC 7662 không cho cache introspection response qua mốc `exp` nếu `exp` có mặt.** Nếu response không có `exp`, hệ thống cần contract rõ; không tự chọn cache vô hạn.

### Cache decision theo token và RS context

Không dùng một cache global chỉ bởi `token` khi **AS có thể trả claims khác nhau tùy quyền của RS**. Key nên gắn:

~~~text
CacheKey {
  tokenDigest: HMAC(serverCacheKey, accessTokenBytes)
  trustedIssuer: "https://auth.example.test"
  rsIdentity: "invoice-api"
  expectedAudience: "invoice-api"
  policyVersion: "v3"
}
~~~

Đừng đưa **raw bearer token vào cache key bị log**. Kết quả cache vẫn là dữ liệu nhạy cảm, cần ACL, TTL và eviction. Khi AS revoke và RS nhận event, phải **invalidate/mark terminal** để response introspection cũ đến muộn không ghi đè trạng thái mới.

### Có được dùng cache khi AS outage?

**Chỉ dùng nếu policy cho phép và cache chưa hết hạn**, không kéo dài `active=true` vượt `exp` hoặc revoke-lag SLO. Với API cực nhạy cảm, nếu không kiểm được trạng thái mới, nên fail closed. Điều này là tradeoff availability vs security, không phải lỗi để “fix” bằng cho mọi request qua.

## 9. Refresh token: hỗ trợ UX dài hơn nhưng tạo bề mặt tấn công mới

Access token sống 3–5 phút sẽ hết hạn thường xuyên. Để không yêu cầu user đăng nhập lại liên tục, một số OAuth clients có thể nhận **refresh token** rồi xin access token mới theo chính sách AS.

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as Client / BFF
    participant AS as Authorization Server
    participant RS as Resource Server
    Client->>AS: Auth code + PKCE hoặc grant thích hợp
    AS-->>Client: Access A1 (TTL=300s) + Refresh R1 nếu được phép
    Client->>RS: Dùng A1 gọi API
    RS-->>Client: 200 nếu A1 và quyền còn hợp lệ
    Note over Client: Gần expiry, renew chủ động
    Client->>AS: POST /token grant_type=refresh_token, R1
    AS->>AS: Kiểm client, grant, expiry và rotation/reuse policy
    AS-->>Client: Access A2 ngắn hạn + Refresh R2 (nếu rotation)
    Client->>RS: Dùng A2 cho request mới
~~~

**Lưu ý:** Không phải mọi client/grant được cấp refresh token, và response rotation phụ thuộc AS. Một **public client** không thể dựa vào client secret nhúng trong app để bảo vệ refresh token như confidential backend.

### Access token ngắn và refresh token dài phải được quản lý khác

| Thuộc tính | Access token | Refresh token |
|---|---|---|
| Thời hạn thông thường | Cố gắng ngắn để giảm replay window | Có thể dài hơn theo policy, nhưng không vô hạn |
| Đích sử dụng | Resource Server | **Token endpoint**, không gửi tới API |
| Giới hạn quyền | Audience, scope, resource, subject/client | Bound to client/grant/family, AS policy |
| Replay threat | Stolen Bearer gọi API đến `exp`/revoke | Stolen refresh token có thể xin **nhiều access tokens** |
| Bảo vệ bổ sung | DPoP/mTLS, audience, scope, revoke | Rotation, reuse detection, sender binding, secure storage và family revoke |
| Thu hồi | Revoke token/denylist/introspection | Revoke refresh token, family hoặc grant theo policy |

### Refresh token rotation và reuse detection

Giả sử:

~~~text
AS phát refresh token R1.
Client dùng R1 -> AS phát R2 và đánh dấu R1 đã tiêu thụ.

Attacker dùng lại R1:
  AS phát hiện reuse của token đã tiêu thụ theo family policy.
  AS có thể revoke cả family/grant, buộc reauthorization.
~~~

Phát hiện reuse giúp giảm nguy cơ **kẻ sở hữu refresh token bị đánh cắp tiếp tục xin token mới**, nhưng cần transaction/atomic family state để tránh race khi nhiều requests refresh đồng thời.

**Rotation không ngăn việc replay access token A1 còn hiệu lực**. Nếu attacker đã sao chép A1, họ không cần R1 để gọi Invoice API trước khi A1 hết hạn.

### Idle timeout và absolute lifetime

Một chính sách refresh token có thể áp:

- **Idle lifetime:** Không được dùng refresh token/grant nếu không có hoạt động hợp lệ quá một khoảng thời gian.
- **Absolute lifetime:** Grant/refresh credential hết hạn tuyệt đối dù client refresh liên tục.
- **Rotation:** Đổi refresh token theo lần dùng và phát hiện reuse.
- **Scope/consent/session constraints:** Không refresh nếu user logout, account disable, grant revoke hoặc policy yêu cầu reauthentication.

**Không để refresh rotation kéo dài grant vô hạn chỉ vì access token ngắn.** Phải tách **access TTL**, **refresh idle/absolute limits** và **RP/OP session lifetime**.

### Refresh token bị đánh cắp cần khẩn cấp hơn “đợi access token hết hạn”

Khi nghi refresh token bị lộ, cần xử lý AS grant/refresh family và thu hồi access tokens liên quan theo khả năng RS. Chỉ giảm access TTL xuống 60 giây nhưng để refresh token lộ vẫn hoạt động hàng tháng **không giảm được nguy cơ khai thác kéo dài**.

## 10. DPoP/mTLS: khi muốn chặn bản sao token ngay trong lifetime

**Short lifetime làm ngắn cửa sổ sử dụng; sender-constrained token ngăn token bị dùng bởi bên không chứng minh được quyền sở hữu khóa.**

### DPoP (RFC 9449)

DPoP cho phép client chứng minh **proof-of-possession của private key** bằng một JWT proof gắn với HTTP request và access token.

Một proof JWT payload minh họa:

~~~json
{
  "jti": "proof-unique-random-001",
  "htm": "GET",
  "htu": "https://invoice.example.test/api/invoices/INV-42",
  "iat": 1800000010,
  "ath": "<base64url-sha256-of-access-token>",
  "nonce": "<server-provided-nonce-if-required>"
}
~~~

`nonce` xuất hiện khi server đã cung cấp/yêu cầu theo DPoP nonce mechanism; không phải mọi DPoP proof đều luôn có nonce.

DPoP-bound access token có thể mang key thumbprint `cnf.jkt` (JWT access token/introspection response tùy profile). RS cần:

1. Xác minh **chữ ký proof** bằng public key phù hợp và kiểm thumbprint trùng token binding.
2. Kiểm `htm` đúng HTTP method thực.
3. Kiểm `htu` đúng target URI theo normalization rules của DPoP.
4. Kiểm `iat` trong **cửa sổ proof freshness** và nonce khi policy yêu cầu.
5. Kiểm `jti` không bị sử dụng lại trong cửa sổ áp dụng.
6. Kiểm `ath` khớp hash của **access token đang được dùng**, khi proof được trình tại Resource Server.
7. Vẫn kiểm access token `exp`, `iss`, `aud`, `scope` và quyền nghiệp vụ.

**Một attacker chỉ có bản sao access token** nhưng không có private DPoP key khó thể tự tạo proof hợp lệ cho request mới. Tuy nhiên, nếu attacker lấy cả token và DPoP private key, hoặc lạm dụng một signing oracle/endpoint đã chiếm, sender-binding có thể không chặn được.

### Phát lại DPoP proof cũng cần được chặn

~~~text
Attacker captures both:
  access_token = A1
  DPoP proof   = P1 for GET /invoices/INV-42

P1 has:
  jti = J1
  iat = T

If RS accepts identical proof repeatedly within its time window:
  replay of P1 may succeed.

Correct RS:
  verify proof signature/binding/time
  reject duplicate jti according to replay-store policy
  optionally enforce nonce/challenge
~~~

**DPoP proof TTL ngắn mà không kiểm `jti`/nonce theo profile có thể vẫn cho replay cùng proof trong cửa sổ.** Ngược lại, replay store chỉ cần áp **proof `jti`**, không đánh dấu toàn bộ **access-token `jti`** là single-use.

### mTLS certificate-bound token (RFC 8705)

Với mTLS, AS có thể cấp access token ràng buộc vào **client certificate**, thường được mô tả bằng `cnf.x5t#S256`. RS kiểm chứng chỉ TLS của client request có thumbprint khớp binding trong access token.

~~~text
Stolen token string A1:
  no matching mTLS client private key/certificate
  -> RS rejects request despite A1 not yet expired.

Legitimate client:
  A1 + matching mTLS client certificate
  -> may proceed to issuer/audience/scope/authorization.
~~~

**TLS giữa proxy và RS có thể làm thay đổi trust boundary**: nếu TLS terminate ở gateway, RS chỉ được tin certificate information qua kênh proxy-to-backend được bảo vệ, header từ internet bị strip/overwrite. Đừng nhận `X-Client-Cert` tự do từ caller làm proof.

### DPoP/mTLS không thay access-token expiry

Sender-constrained token vẫn cần **`exp` ngắn hợp lý**, revoke và scope/audience tối thiểu. Khóa client có thể bị lộ hoặc bị sử dụng trái phép; proof-of-possession giảm một lớp replay, không cấp quyền vô hạn.

## 11. Short lifetime trên authorization code, nonce và giao dịch một lần

Một số credential có thể được **tiêu thụ đúng một lần**; chúng cần ngắn hạn nhưng cách chống replay **khác** access token dùng nhiều request.

### Authorization code

~~~text
AS issues authorization code C1:
  expires_at = T0 + short window
  bound_to = client_id, redirect_uri, PKCE challenge, grant context

Token exchange #1:
  C1 + correct client auth/PKCE -> success; C1 becomes consumed.

Token exchange #2 (same C1):
  MUST reject reuse, even if expires_at not reached.
~~~

RFC 6749 khuyến nghị authorization code lifetime **ngắn, tối đa 10 phút**; nhiều AS chọn ngắn hơn. **PKCE (RFC 7636)** thêm ràng buộc code với `code_verifier`. Chỉ TTL ngắn mà không single-use/PKCE vẫn dễ bị code interception.

### OAuth `state` và OIDC `nonce`

`state` giúp client liên kết authorization response với request gốc và chống CSRF/login mix-up theo thiết kế. `nonce` trong OIDC giúp ràng buộc ID token với authentication request theo flow/profile.

- Sinh bằng CSPRNG, khó đoán và gắn với **một transaction**.
- Có **TTL** và được **consume** đúng cách khi callback hoàn tất.
- Không chấp nhận callback cũ hoặc state/nonce của một tab/session khác.
- Không dùng cùng một static nonce/state cho mọi login request.
- Cần issuer binding/PKCE/redirect URI validation song song, không xem state/nonce là thay thế.

### Business idempotency khác token single-use

~~~http
POST /api/payments HTTP/1.1
Host: payments.example.test
Authorization: DPoP <redacted-access-token>
DPoP: <redacted-proof-jwt>
Idempotency-Key: payment-intent-unique-42
Content-Type: application/json

{"amount":1200000,"currency":"VND","beneficiary":"approved-account"}
~~~

Một access token ngắn hạn và proof hợp lệ **không tự chặn hai lệnh thanh toán giống nhau**. Server cần **idempotency key**, trạng thái payment intent, ràng buộc số tiền/người thụ hưởng và chính sách ngăn double-spend/retry. Ngược lại, idempotency key **không phải cơ chế chặn attacker dùng access token bị đánh cắp để xem dữ liệu khác**.

### Step-up authentication và freshness

Với thao tác nhạy cảm, RP có thể yêu cầu OIDC `max_age` hoặc ACR phù hợp và kiểm **`auth_time`**. **Access token `iat` mới không chứng minh user vừa xác thực lại**; refresh token có thể cấp access token mới dù authentication event đã cũ.

Lifetime ngắn và user reauthentication freshness là **hai chính sách riêng**:

~~~text
Access token expiry:
  "Credential gọi API còn sống đến khi nào?"

OIDC auth_time/max_age:
  "User xác thực lần gần nhất lúc nào?"

Transaction approval:
  "User có chủ động phê duyệt thao tác cụ thể này không?"
~~~

## 12. Clock skew, leap, drift và yêu cầu đồng bộ thời gian

Nếu AS và RS lệch đồng hồ, một token ngắn hạn dễ bị **false reject** hoặc **bị chấp nhận quá hạn**. Đây là lý do triển khai cần **đồng bộ thời gian**, nhưng không được tạo một clock leeway quá lớn.

### Tình huống sai lệch

~~~text
AS correct clock:  T0 = 12:00:00
Token iat:         12:00:00
Token exp:         12:02:00

RS clock ahead +35s:
  Token bị coi hết hạn sớm hơn so với AS.

RS clock behind -35s:
  Token có thể được chấp nhận muộn hơn 35s.

If RS adds 60s leeway:
  Worst-case replay window can be further extended.
~~~

**Không mặc định “skew=60 giây” là an toàn với access token TTL=60 giây.** Leeway có thể làm cửa sổ chấp nhận tăng đáng kể so với lifetime chính sách. Hãy quan sát drift thực tế, dùng NTP/time sync an toàn, và chọn leeway nhỏ nhất hợp lý.

### Kiểm `exp` tại thời điểm xử lý nào?

RS thường xác minh access token **khi bắt đầu HTTP request**. Nếu request đã được chấp nhận, xử lý dài hơn `exp` có thể hoàn tất theo kiến trúc; JWT expiry không tự làm database transaction bị rollback đúng giây hết hạn.

Với thao tác kéo dài hoặc có tác động lớn:

- Kiểm lại **quyền và trạng thái giao dịch** trước commit khi threat model yêu cầu.
- Không cho bắt đầu **request mới** bằng token hết hạn.
- Thiết kế **max request processing time**, cancellation và transaction timeout.
- Tránh “token được nhận lúc T0 nên cho phép streaming dữ liệu vô hạn” nếu nghiệp vụ yêu cầu reassessment/authorization liên tục.

### Đồng hồ đơn điệu và wall clock

JWT `exp` được biểu diễn bằng **UTC wall-clock timestamp**, nên cần một đồng hồ hệ thống được đồng bộ. **Monotonic clock** hữu ích khi đo elapsed time, timeout hoặc refresh backoff; không trực tiếp thay JWT NumericDate.

Client có thể tính deadline renew dựa vào `expires_in` và monotonic elapsed time để chống system clock jump, nhưng **RS vẫn tự kiểm token expiry** bằng trusted server clock. Không để client chỉnh Date header, request timestamp hoặc local timezone quyết định `now` của RS.

### Khi thời gian server bất thường

Nếu drift lớn hoặc clock lùi/bật nhanh bất thường:

1. Đánh dấu node unhealthy hoặc hạn chế issuance/validation theo policy.
2. Cảnh báo time synchronization service, kiểm NTP/time source đáng tin.
3. Không nới clock skew tự động thành nhiều phút/giờ để “khỏi báo lỗi”.
4. Kiểm acceptance trên tất cả RS replicas/regions, không chỉ node trong test.

**Short lifetime chỉ có ý nghĩa nếu mọi bên thực thi cùng quy tắc thời gian có kiểm soát.**

## 13. Java 17: kiểm lifetime trên token **đã được xác minh**

Ví dụ dưới đây minh họa **policy của Invoice Resource Server**, không phải JWT parser. Object `VerifiedAccessToken` **chỉ được tạo sau khi** thư viện JWT/JOSE đã kiểm chữ ký, issuer/key/algorithm/token profile, hoặc sau khi RS dùng một introspection adapter tin cậy đã xác thực AS và kiểm response.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

record VerifiedAccessToken(
    String issuer,
    String subject,
    String clientId,
    Set<String> audiences,
    Set<String> scopes,
    Instant issuedAt,
    Instant notBefore,
    Instant expiresAt,
    String tokenType,
    String tokenId
) {}

record AccessTokenPolicy(
    String expectedIssuer,
    String expectedAudience,
    String requiredScope,
    String expectedTokenType,
    Duration maximumIssuedLifetime,
    Duration allowedClockSkew
) {}

final class AccessTokenLifetimeEvaluator {

    static boolean permitsInvoiceRead(
            VerifiedAccessToken token,
            AccessTokenPolicy policy,
            String expectedSubject,
            Clock clock) {

        Objects.requireNonNull(token);
        Objects.requireNonNull(policy);
        Objects.requireNonNull(clock);

        Instant now = clock.instant();
        Duration skew = policy.allowedClockSkew();

        // Claims đã qua bước xác minh cryptographic/trust contract.
        if (!policy.expectedIssuer().equals(token.issuer())) {
            return false;
        }
        if (token.audiences() == null ||
            !token.audiences().contains(policy.expectedAudience())) {
            return false;
        }
        if (token.scopes() == null ||
            !token.scopes().contains(policy.requiredScope())) {
            return false;
        }
        if (!policy.expectedTokenType().equals(token.tokenType())) {
            return false;
        }
        if (!Objects.equals(expectedSubject, token.subject())) {
            return false;
        }

        // Ví dụ policy này yêu cầu cả iat và exp.
        if (token.issuedAt() == null || token.expiresAt() == null) {
            return false;
        }
        if (!token.expiresAt().isAfter(token.issuedAt())) {
            return false;
        }

        Duration issuedLifetime =
            Duration.between(token.issuedAt(), token.expiresAt());
        if (issuedLifetime.compareTo(
                policy.maximumIssuedLifetime()) > 0) {
            return false;  // AS không được phát token quá dài.
        }

        if (token.issuedAt().isAfter(now.plus(skew))) {
            return false;  // iat nằm quá xa trong tương lai.
        }

        // Khi skew = 0: now >= exp => expired.
        // Với skew > 0, acceptance có thể kéo dài thêm skew.
        if (!now.minus(skew).isBefore(token.expiresAt())) {
            return false;
        }
        if (token.notBefore() != null &&
            token.notBefore().isAfter(now.plus(skew))) {
            return false;
        }

        // Quyền ownership/tenant của invoice vẫn phải kiểm riêng.
        // Sender proof/revoke state không được kiểm bởi hàm này.
        return true;
    }

    private AccessTokenLifetimeEvaluator() {}
}
~~~

### Policy ví dụ

~~~java
AccessTokenPolicy invoicePolicy = new AccessTokenPolicy(
    "https://auth.example.test",
    "invoice-api",
    "invoice:read",
    "Bearer",
    Duration.ofMinutes(5),
    Duration.ofSeconds(10)
);

boolean tokenAcceptable =
    AccessTokenLifetimeEvaluator.permitsInvoiceRead(
        verifiedAccessToken,    // Chỉ đến từ verified JWT / introspection.
        invoicePolicy,
        expectedUserSubject,
        Clock.systemUTC()
    );
~~~

`verifiedAccessToken` và `expectedUserSubject` là các biến **được hệ thống đã xác thực cung cấp trước**, không phải input lấy từ body/header do caller tự khai.

### Cần hiểu giới hạn của code

1. **Không có JWS verification trong snippet.** Nếu attacker có thể tự tạo `VerifiedAccessToken` từ JWT payload chưa ký hoặc từ HTTP JSON, toàn bộ phép kiểm thời gian vô nghĩa.
2. **`expectedTokenType` phải được định nghĩa rõ theo token profile.** String `Bearer` chỉ mô tả cách sử dụng token, không tự chứng minh token là OAuth access token thay vì refresh/ID token; adapter cần kiểm purpose/`typ`/contract ở tầng tin cậy.
3. **`expectedSubject` được dùng cho user-delegated invoice route.** Với `client_credentials`, không mặc định tạo end-user subject; cần **M2M policy** và client/workload authorization riêng.
4. **Policy constructor phải validate** maximum lifetime và skew là giá trị không âm, issuer/audience/scope không rỗng; tránh cấu hình skew âm hoặc vô hạn.
5. **Duration.between(iat, exp)** chỉ có ý nghĩa nếu `iat` và `exp` lấy từ token đã được AS tin cậy phát; kiểm thêm clock source và format.
6. **Phép kiểm `exp` với leeway** có thể nhận token qua đúng thời điểm `exp` một khoảng tối đa `skew`. Với hệ thống cần strict expiry, chọn `Duration.ZERO` theo policy.
7. Hàm không kiểm **DPoP/mTLS**, trạng thái revoke, business idempotency, rate limit hay quyền trên hóa đơn cụ thể.
8. Trên request dài, cần xem thời điểm bắt đầu/commit và transaction policy; hàm không tự dừng một operation khi `exp` đến giữa xử lý.

### Ví dụ kết quả với clock giả

~~~text
Issued:   T0
Expires:  T0 + 300s
Skew:     10s
Lifetime policy: max 300s

now = T0 + 100s => timing passes
now = T0 + 300s => có thể passes do configured skew
now = T0 + 310s => rejects (boundary now == exp+skew)
now = T0 + 500s => rejects

Issuer, audience, scope, subject và token purpose vẫn phải hợp lệ.
~~~

**Đừng dùng configured leeway làm “grace period để client kịp refresh” ngoài policy.** Client nên chủ động xin token mới **trước** expiry; RS không cần cố chấp nhận token cũ để che lỗi refresh.

## 14. Spring Security Resource Server: cấu hình validation và maximum lifetime

Với **Spring Security 6.x**, ứng dụng có thể dùng JWT decoder được cấu hình từ **issuer/JWKS URI tin cậy**. Thư viện xử lý chữ ký và thời gian theo validator; ứng dụng thêm **audience** và **maximum issued lifetime** theo local contract.

### Ví dụ Java Spring Security (minh họa)

~~~java
import java.time.Duration;
import java.time.Instant;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class InvoiceJwtValidationConfig {
    private static final String ISSUER =
        "https://auth.example.test";
    private static final String JWKS =
        "https://auth.example.test/.well-known/jwks.json";
    private static final String AUDIENCE = "invoice-api";

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        // Issuer/JWKS ở đây phải là trusted config, KHÔNG phải
        // URL lấy từ token unverified hoặc request của client.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> audienceAndLifetime = jwt -> {
            Instant iat = jwt.getIssuedAt();
            Instant exp = jwt.getExpiresAt();

            if (jwt.getAudience() == null ||
                !jwt.getAudience().contains(AUDIENCE) ||
                iat == null || exp == null ||
                !exp.isAfter(iat) ||
                Duration.between(iat, exp)
                    .compareTo(Duration.ofMinutes(5)) > 0) {

                return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token profile/lifetime not accepted",
                        null));
            }
            return OAuth2TokenValidatorResult.success();
        };

        // Chọn skew CỤ THỂ theo policy; không mặc định nới rất dài.
        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ofSeconds(10)),
                new JwtIssuerValidator(ISSUER),
                audienceAndLifetime
            ));

        return decoder;
    }
}
~~~

### Những việc phải có thêm trong production

- **Token type/profile:** Nếu dùng RFC 9068 JWT access token, kiểm `typ=at+jwt` và các yêu cầu profile/algorithm/key của issuer; không chấp nhận ID token làm bearer access token.
- **Algorithm allowlist:** Cấu hình decoder/chữ ký theo alg được AS đăng ký, chống algorithm confusion, key confusion; header `kid` chưa xác thực chỉ được tra **trusted JWKS/keyring**.
- **Authorization:** Filter kiểm JWT thành công chưa đủ; controller/service/repository phải kiểm scope, role, `aud`, tenant và object ownership.
- **Client/subject:** Phân biệt `client_credentials` với user-delegated grant, kiểm binding khi API yêu cầu.
- **Revocation:** Offline JWT validation **không tự cập nhật revoke**, cần TTL phù hợp và denylist/introspection/event policy khi yêu cầu.
- **DoS và availability:** Giới hạn JWKS fetch, parser size, timeouts, key rotation; không fetch key từ URL tùy ý do token chứa.
- **Nếu dùng OAuth2 Resource Server auto-configuration**, tránh cấu hình validator mới làm mất những validator cần thiết của profile. Ví dụ trên chủ động khai timestamp/issuer/custom; team phải review toàn bộ production policy.

### Một lỗi cấu hình thời gian rất thường gặp

~~~text
AS:
  access token lifetime: 2 minutes

RS:
  default JWT timestamp tolerance: 60 seconds

Consequence:
  Token may be accepted for almost 3 minutes,
  undermining part of the 2-minute replay-window target.
~~~

Đây là **cảnh báo thiết kế**: framework có thể có default tolerance không giống nhu cầu. Kiểm **giá trị thực của thư viện/phiên bản đang dùng** và dùng test tại các mốc `exp-1s`, `exp`, `exp+δ`.

## 15. Khi kết hợp short lifetime với key rotation, logout và revoke

Một token hết hạn và một token bị thu hồi là hai trạng thái khác nhau:

~~~text
Expiry:
  token reaches exp;
  RS must reject based on time validation.

Revocation:
  AS/issuer marks token/grant invalid before exp;
  RS must become aware through its enforcement mechanism.

Logout:
  RP/OP session is terminated;
  existing access token may still be valid unless separately rejected.

Key rotation:
  signing/encryption keys change;
  old tokens may remain valid under retained verification keys
  unless revoked/expired by policy.
~~~

### Logout có chặn token được đánh cắp ngay không?

**Không mặc nhiên.** Xóa cookie và kết thúc RP session không thể thu hồi bản sao access token attacker đã lấy. Nếu app revoke refresh token, attacker đang giữ **access token cũ** vẫn có thể replay trong phần lifetime còn lại, trừ khi RS biết token đã revoked hoặc token sender-constrained.

Một access token 2 phút giúp giới hạn rủi ro, nhưng nếu yêu cầu “logout toàn bộ thiết bị và chặn API trong 5 giây”, chỉ TTL 2 phút **không đạt** SLA. Cần phối hợp revocation propagation, RS denylist/introspection và session/grant invalidation.

### Key rotation cũng không phải expiry hay revoke

RS có thể tiếp tục dùng public signing key cũ để verify JWT chưa hết hạn; đây là hành vi bình thường trong **staged key rotation**. Nếu signing key bị compromise, có thể phải ngừng tin key đó sớm, revoke token liên quan và kích hoạt quy trình khẩn cấp — không chỉ “đợi token tự hết `exp`”.

Với JWE, key cũ có thể phải giữ **decrypt-only** cho token chưa hết hạn. Xóa decryption key sớm gây outage chứ không tạo một cơ chế revocation bảo đảm theo OAuth.

### Đừng dùng token lifetime để bù thiếu object-level authorization

Một token chỉ sống 60 giây nhưng có `admin:*` và `aud` rộng vẫn nguy hiểm. Bản sao có thể được attacker dùng trong **vài giây** để đọc/xóa dữ liệu hàng loạt. Bảo vệ quan trọng:

- Audience hẹp theo RS.
- Scope theo chức năng tối thiểu.
- Kiểm subject/client/grant/tenant.
- Object ownership và business rules tại API.
- Rate limit/abuse monitoring theo account/client/resource.
- Sender-binding và transaction-specific approval khi phù hợp.

### Multi-region và JWT expiry nhất quán

Giả sử RS A clock đúng, RS B chậm 90 giây. Một JWT access token đã hết hạn ở RS A có thể được RS B nhận sai. Đó là **configuration/time-drift incident**, không phải thuộc tính hợp lệ của OAuth.

Thiết kế cần NTP/time monitoring, cấu hình leeway giống security policy ở các RS, test failover region và alert drift trước khi nó làm rộng replay window.

## 16. Những anti-pattern làm “short lifetime” mất tác dụng

| Anti-pattern | Vì sao nguy hiểm? | Thay bằng |
|---|---|---|
| **Access token TTL 5 phút nhưng RS bỏ kiểm `exp`** | Token có thể dùng mãi | JWT/inrospection validation và test expiry |
| **RS lấy `now` từ request client** | Attacker tự chỉnh thời gian | Trusted RS clock |
| **Clock leeway lớn bằng lifetime** | Replay window thực tế tăng đáng kể | Đồng bộ thời gian và skew nhỏ đã review |
| **Client gửi `expires_in` rồi AS tin ngay** | Client tự kéo dài token | AS chọn TTL theo registration/risk policy |
| **AS trả `expires_in=300` nhưng JWT `exp` một ngày** | Không nhất quán và dễ bị khai thác | Issuance integration tests và max lifetime RS |
| **JWT được decode nhưng không verify chữ ký** | Attacker tự đặt `exp`/`scope`/`sub` | JOSE SDK kiểm signature/alg/issuer/key |
| **JWT đúng exp nhưng audience không được kiểm** | Token dùng chéo API | Exact audience validation |
| **Scope chỉ kiểm bằng substring** | `read-all` có thể khớp `read` sai | Tokenize scope và so từng giá trị |
| **JWE encrypted nên cho qua** | Mã hóa không thay issuer/aud/authz | Decrypt + verify profile + claims |
| **Cache introspection `active=true` quá expiry** | Token revoked/expired vẫn được nhận | TTL không vượt `exp`, cache policy/AS contract |
| **AS outage → “tạm bỏ check”** | Fail open trong thời gian tấn công | Fail closed hoặc cache còn hợp lệ theo policy |
| **Refresh token không có idle/absolute limit** | Stolen refresh credential tồn tại kéo dài | Rotation/reuse detection/revoke và giới hạn |
| **Refresh token lưu trong JavaScript storage dễ bị XSS** | Đánh cắp credential sống dài | BFF/secure storage, XSS mitigation theo kiến trúc |
| **DPoP proof có TTL ngắn nhưng không kiểm `jti`** | Proof đã ký có thể bị replay trong window | Replay cache, nonce, `htm`/`htu`/`ath` |
| **Cấm dùng lại access-token `jti` ở request thứ hai** | Phá token được thiết kế đa lần | Phân biệt access token và proof/authorization code single-use |
| **Thấy access token mới ⇒ user vừa MFA** | Nhầm `iat` với OIDC `auth_time` | Check `auth_time`/ACR và step-up |
| **Mở rộng lifetime mỗi khi AS timeout** | Tăng rủi ro đúng lúc validation yếu | AS HA/backoff/circuit breaker, fail closed |
| **Refresh đồng thời không kiểm rotation race** | Reuse detection nhầm, token family bị revoke | Single-flight/atomic rotation và retry policy |
| **Phát token dài để batch job không gián đoạn** | Bề mặt theft kéo dài hàng giờ/ngày | Renewal theo workload và checkpoint |
| **Logout xóa cookie nhưng không revoke token** | Bản sao bearer còn dùng | Phối hợp AS/RS revoke theo SLA |
| **Dùng token mới cho mọi retry POST thanh toán** | Giao dịch có thể bị xử lý hai lần | Idempotency/transaction binding |
| **Không ghi nhận drift ở RS replicas** | Một số node nhận expired token | Multi-region time synchronization/metrics |

**Short lifetime là một tham số trong policy, không phải lá chắn độc lập.** Hệ thống thiếu audience/scope/object authorization hoặc lộ refresh token vẫn không an toàn chỉ vì đổi TTL từ 15 phút còn 5 phút.

## 17. Triển khai TTL chính sách mới: rollout, quan sát và xử lý sự cố

Giảm access-token TTL từ 30 phút xuống 5 phút có thể tăng số cuộc gọi token endpoint, số refresh token rotations và tần suất các lỗi `401 invalid_token` do client không renew đúng thời điểm. Một policy bảo mật tốt cần **triển khai có quan sát**, không chỉnh một biến config rồi cho rằng đã hoàn thành.

### Quy trình rollout minh họa

1. **Inventory token consumers:** Browser SPA/BFF, mobile, CLI, server-to-server jobs, API gateways, SDKs và RS offline JWT/opaque introspection.
2. **Xác định security objective:** “Sau khi token bị lộ, attacker không thể replay quá N phút **nếu không có credential khác**”, hoặc “sau revoke, mọi RS từ chối trong M giây”. Hai mục tiêu không đồng nhất.
3. **Khóa issuance contract:** Với từng client/resource/scope/grant, AS cấu hình TTL tối đa và định nghĩa refresh policy.
4. **Kiểm client refresh behavior:** Proactive refresh trước expiry, giới hạn refresh concurrency, không đưa refresh token vào browser storage không cần thiết.
5. **Kiểm RS validation:** Signature/introspection, issuer, audience, token purpose, `exp`/`nbf`, clock tolerance, token-lifetime cap.
6. **Kiểm clock drift:** AS và RS ở tất cả regions đã đồng bộ; không có node nhận token quá hạn.
7. **Canary theo client class:** Giảm TTL cho nhóm nhỏ, đo 401, token endpoint load, latency, refresh errors, session churn.
8. **Roll out có giám sát:** Đảm bảo RS đã hỗ trợ policy mới trước khi AS phát token; làm rõ số token cũ còn `exp` dài đang tồn tại.
9. **Đánh giá token cũ:** Thay issuance TTL **không thu hồi JWT cũ** đã phát trước thay đổi; nếu cần nhanh, revoke/denylist/rotate theo policy.
10. **Chốt runbook:** Cho AS outage, refresh race, clock drift, revoke lag và incident lộ access/refresh token.

### Metrics không được chứa raw token

| Metric/signal | Ý nghĩa vận hành | Hành động nếu bất thường |
|---|---|---|
| `access_token_issued_lifetime_seconds` (histogram) | Phân bố TTL được AS phát | Alert nếu vượt policy từng client/resource |
| `jwt_invalid_expired_total` | Số request bị từ chối vì expired | Kiểm client refresh timing, clock skew |
| `jwt_invalid_nbf_total` | Token not-before ở tương lai | Kiểm AS/RS time drift |
| `jwt_issued_lifetime_exceeded_total` | JWT `exp-iat` dài hơn policy | Điều tra AS issuance misconfiguration |
| `refresh_token_exchange_total` | Tần suất refresh khi TTL giảm | Capacity planning và monitoring abuse |
| `refresh_token_reuse_detected_total` | Refresh token đã consumed bị dùng lại | Phân biệt client race và stolen token |
| `dpop_proof_replay_rejected_total` | Replay `jti`/proof | Alert abuse và kiểm replay-store consistency |
| `introspection_cache_hit_total` | Tỷ lệ dùng cached active result | Đối chiếu revoke lag và AS load |
| `token_revocation_lag_seconds` | Thời gian RS ngừng nhận token revoked | So với security SLO |
| `server_clock_offset_seconds` | Drift AS/RS | Alert trước khi vượt allowed skew |
| `api_request_token_age_seconds` | Tuổi access token tại thời điểm sử dụng | Điều tra token có tuổi quá lớn/AS phát sai |
| `jwt_audience_mismatch_total` | Token bị dùng sai RS | Điều tra token substitution hoặc client routing |

**Không đưa token string, `jti`, user ID, subject, raw `client_id` không kiểm soát hay session ID vào high-cardinality metrics labels.** Nếu cần tương quan incident, sử dụng một **HMAC digest hoặc audit ID trong kho có phân quyền**, không xuất credential vào logs.

### Token endpoint quá tải sau giảm TTL

~~~text
Before rollout:
  10,000 active clients
  access token TTL = 60 min
  roughly 167 renewals/minute if uniformly distributed

After rollout:
  10,000 active clients
  access token TTL = 5 min
  roughly 2,000 renewals/minute if uniformly distributed

Difference: ~12x under the simplified model.
~~~

Các phép tính **minh họa** giả định tất cả clients đều duy trì phiên và renew một lần mỗi lifetime, phân bố đều; thực tế phụ thuộc idle clients, caching, proactive renewal, grants và traffic. Vấn đề không chỉ là tăng CPU AS mà còn **refresh burst** khi hàng nghìn client cùng được phát token một thời điểm.

### Thiết kế refresh không tạo thác lũ

- Client renew gần expiry nhưng **không quá sớm liên tục**, có jitter và bảo vệ concurrent refresh (single-flight).
- Backend có thể cache access token trong một khoảng phù hợp **trong phạm vi client/resource trust**, không cache shared bearer token xuyên tenant.
- Khi refresh token rotation tạo R2, lưu R2 an toàn/atomic để tránh workers tiếp tục dùng R1 và kích hoạt reuse detection sai.
- Khi AS downtime, backoff, circuit breaker và UI thông báo rõ; **không kéo dài exp của token ở RS**.
- Jobs chạy lâu có thể **checkpoint, pause, renew** rồi tiếp tục; không cấp token dài nhiều ngày chỉ để tránh renewal logic.

## 18. Ma trận kiểm thử short lifetime và token replay

Giả định:

~~~text
Trusted AS:        https://auth.example.test
Resource Server:   Invoice API, aud=invoice-api
Access token:      Bearer JWT hoặc opaque theo test
Required scope:    invoice:read
Expected subject:  user:an (delegated user route)
AS access TTL:     300 giây (ví dụ)
Max issued TTL RS: 300 giây
Clock skew:        10 giây (ví dụ policy)
Refresh rotation:  ON
DPoP proof age:    theo policy RS/AS nếu dùng DPoP
~~~

| Ca kiểm thử | Input/trạng thái | Kết quả kỳ vọng |
|---|---|---|
| **Token còn hạn** | `now=iat+60s`, `exp=iat+300s` | Timing pass; tiếp tục các kiểm soát khác |
| **Ngay trước expiry** | `now=exp-1s` | Pass nếu các điều kiện khác đạt |
| **Đúng expiry, skew=0** | `now=exp` | Từ chối |
| **Sau expiry, skew=0** | `now=exp+1s` | Từ chối |
| **Đúng expiry, skew=10s** | `now=exp` | Có thể được chấp nhận theo leeway đã cấu hình |
| **Hết leeway** | `now=exp+10s` | Từ chối tại boundary `now >= exp+δ` |
| **Thiếu `exp`** | JWT không có expiry, RS profile yêu cầu | Từ chối |
| **`exp` sai kiểu** | `"exp":"1800000300"` string | Từ chối schema, không ép kiểu tự do |
| **`exp` tính bằng milliseconds** | 13-digit epoch value không theo profile | Từ chối hoặc phát hiện max lifetime/issuer anomaly |
| **`iat` tương lai** | `iat=now+5min`, allowed skew 10s | Từ chối |
| **`iat` vắng** | RS yêu cầu `exp-iat` max lifetime | Từ chối theo local contract |
| **`exp <= iat`** | Exp không sau issued-at | Từ chối |
| **`exp-iat` quá dài** | AS phát 2h thay vì 5min | Từ chối theo max issued lifetime |
| **`nbf` ở tương lai** | `nbf=now+60s` | Từ chối tới khi nbf hợp lệ |
| **Thiếu `nbf`** | Profile cho optional nbf | Vẫn kiểm exp và các claims bắt buộc khác |
| **Clock AS nhanh** | Token phát `iat` quá xa trong tương lai | Alert time sync và từ chối theo policy |
| **Clock RS chậm** | Node nhận expired token | Time-drift test phải phát hiện |
| **Clock leeway quá lớn** | RS cho ±90s với TTL 60s | Security validation fail so với design requirement |
| **Chữ ký JWT sai** | Attacker sửa `exp` nhưng không ký được | Reject trước timing-based authorization |
| **`alg=none`** | Unsigned token | Reject |
| **`kid` lạ** | JWT header yêu cầu key ngoài trusted JWKS | Reject, không fetch URL attacker |
| **Issuer sai** | `iss` trỏ OP khác | Reject dù expiry hợp lệ |
| **Audience sai** | `aud=payroll-api` | Invoice API từ chối |
| **Scope không đủ** | `scope=invoice:export` nhưng cần read | Từ chối authorization |
| **Scope substring trap** | `invoice:read-all` nhưng cần `invoice:read` | Không match substring |
| **Subject sai** | `sub=user:binh` trong request cho An | Từ chối hoặc kiểm object authorization thích hợp |
| **Client credentials token** | Token workload không có end-user subject | Chỉ M2M route/policy phù hợp, không gán user giả |
| **JWT dài hạn còn lưu** | AS vừa giảm TTL, token cũ `exp=tomorrow` | RS max lifetime/denylist policy xử lý; thay issuance không tự xóa token cũ |
| **Bearer replay trước expiry** | Attacker copy token 1 phút trước exp | Có thể thành công nếu không sender-bound/revoked; test chứng minh giới hạn TTL |
| **Bearer replay sau expiry** | Attacker copy token rồi đợi hết hạn | RS từ chối đúng boundary |
| **Bearer được mã hóa JWE** | Attacker có ciphertext nguyên token | Có thể replay trước exp nếu RS nhận Bearer; encryption không thay sender binding |
| **`jti` đã thấy lần trước** | Access token hợp pháp dùng API hai lần | Không từ chối chỉ vì token `jti` trùng, trừ token profile single-use |
| **DPoP proof hợp lệ** | `htm`/`htu`/`ath`/`iat`/`jti`/signature đúng | Proof validation pass rồi kiểm access token |
| **DPoP proof trùng `jti`** | Lặp proof P1 trong window | Reject theo replay-store policy |
| **DPoP proof sai method** | Proof GET dùng cho POST | Reject |
| **DPoP proof sai target URI** | Proof ký cho API A dùng API B | Reject |
| **DPoP proof sai `ath`** | Proof cho A1 được gửi với A2 | Reject |
| **DPoP proof cũ** | Proof `iat` vượt accepted window | Reject |
| **DPoP nonce sai/thiếu** | RS đang yêu cầu server nonce | Challenge/reject theo profile |
| **DPoP key không khớp `cnf.jkt`** | Attacker có token nhưng key khác | Reject |
| **mTLS client cert sai** | Bearer-like token bound với cert A, request dùng cert B | Reject |
| **Refresh token được rotate** | R1 đổi thành R2 | R1 không dùng lại hợp lệ |
| **Refresh token replay** | Attacker gửi R1 sau rotation | AS phát hiện reuse và áp family policy |
| **Refresh race nhiều threads** | Hai refresh request cùng R1 | Không phát nhiều descendants sai; policy/idempotency rõ |
| **Refresh expired** | Idle/absolute deadline đã qua | Không cấp access token mới |
| **Access token hết hạn, refresh còn hạn** | Client renew thành công | Chỉ **A2** mới được dùng; RS vẫn reject A1 expired |
| **Refresh bị revoke** | AS revoke grant, client vẫn thử refresh | AS từ chối, không silently issue new token |
| **Introspection active=true** | Opaque token chưa hết hạn, đúng claims | RS tiếp tục issuer/aud/scope/ownership checks |
| **Introspection active=false** | Token expired hoặc revoked | RS từ chối |
| **Cache quá exp** | RS giữ active=true sau token expiration | Reject, vi phạm cache policy |
| **Cache trong cửa sổ revoke** | Token revoked nhưng cache còn TTL | Đo revoke propagation lag, không hứa tức thì |
| **Response cache từ RS khác** | Shared cache không phân vùng RS/audience | Không nhận metadata sai authority |
| **AS introspection 503** | Không có cache còn hợp lệ | Fail closed/503 theo service policy |
| **Access token TTL ngắn nhưng không TLS** | Token dễ bị bắt qua mạng | Security test fail, áp HTTPS |
| **Authorization code replay** | C1 được đổi hai lần trước expiry | Lần thứ hai bị từ chối do single-use |
| **PKCE verifier sai** | Code còn hạn nhưng verifier không hợp lệ | Token endpoint từ chối |
| **OIDC authentication cũ** | Access token `iat` mới, `auth_time` cũ | Step-up freshness không tự được đáp ứng |
| **Payment POST duplicate** | Hai POST cùng access token | Business idempotency ngăn xử lý hai lần |
| **Request bắt đầu sát `exp`** | Token hợp lệ lúc start nhưng hết hạn lúc commit | Thực thi processing/transaction policy riêng |
| **Client refresh burst** | 1000 clients renew cùng thời điểm | Rate limit/capacity/jitter, không mở rộng token TTL tùy tiện |
| **Multi-region skew** | RS A nhận, RS B từ chối cùng token ngoài policy | Test phát hiện cấu hình/time inconsistency |
| **Token lộ trong log** | Proxy ghi Authorization header | Redaction test fail, áp storage/log policy |
| **Logout nhưng access token chưa revoke** | RP session invalidated, A1 vẫn còn hạn | Nhận diện cửa sổ replay còn lại; không hứa global revoke |

### Fake-clock test case tại chính boundary

~~~text
Token:
  iat = T0
  nbf = T0
  exp = T0 + 300 seconds
Policy:
  skew = 10 seconds
  maxIssuedLifetime = 300 seconds

Test 1: now = T0 + 299s -> ACCEPT timing
Test 2: now = T0 + 300s -> ACCEPT timing only because skew=10s
Test 3: now = T0 + 309s -> ACCEPT timing only because skew=10s
Test 4: now = T0 + 310s -> REJECT timing
Test 5: now = T0 + 311s -> REJECT timing

Repeat with skew=0:
  now = T0 + 300s -> REJECT timing
~~~

**Test cần kiểm cả các điều kiện security khác**, không coi pass timing là API access allowed. Với chính sách không cho phép leeway sau `exp`, test phải đặt `skew=0` và yêu cầu reject ở `now=exp`.

### Race: refresh token rotation và access expiry

~~~text
T0: Client has A1 (exp=T0+300s), R1.
T1: Worker A requests refresh with R1.
T2: Worker B concurrently requests refresh with R1.
T3: AS atomically consumes R1, issues A2/R2 to one request.
T4: Other request gets error or contract-defined safe response.
T5: Client persists R2 safely; old R1 cannot be reused.

Assert:
  No unauthorized refresh descendant survives rotation conflict.
  A1 expires when its own exp is reached.
  R2/refresh state is not silently overwritten by an older response.
~~~

Những test này cần chạy với **AS multi-node/transaction store** nếu production có nhiều replica; `synchronized` trong một JVM không chứng minh race đã được chặn ở toàn hệ thống.

## 19. Bài tập tình huống: Invoice API, refresh rotation và token bị sao chép

Hệ thống có những thành phần:

~~~text
Issuer/AS:    https://auth.example.test
Client:       invoice-web (BFF)
Resource:     invoice-api
Scope:        invoice:read
User:         user:an
Access token: JWT Bearer A1
Access TTL:   300 giây
Refresh:      R1, rotation on
RS skew:      10 giây
RS validation: signed JWT offline, no denylist

T0=10:00:00  AS phát A1, exp=T0+300s.
T0+60s       A1 bị lộ trong proxy log.
T0+65s       Attacker dùng A1 gọi Invoice API.
T0+120s      User bấm local logout tại BFF.
T0+121s      BFF revoke R1; AS ngừng chấp nhận R1.
T0+180s      Attacker gửi lại A1.
T0+311s      Attacker tiếp tục gửi A1.
~~~

**Câu 1. Tại T0+65s, chữ ký A1 đúng thì attacker có thể gọi API không?**

**Có thể.** Chữ ký đúng không chứng minh caller là BFF nguyên bản. Nếu A1 là Bearer, chưa revoked, đúng issuer/audience/scope và endpoint không đòi sender proof, bản sao token có thể được RS chấp nhận. Object authorization vẫn giới hạn dữ liệu attacker đọc được.

**Câu 2. Nếu giảm TTL từ 5 phút xuống 2 phút, attacker còn dùng A1 tại T0+180s không?**

**Không**, nếu token mới thực sự được phát với `exp=T0+120s`, RS thực thi expiry và allowed skew không kéo dài tới T0+180s. Tuy nhiên, **token A1 đã phát trước thay đổi TTL** vẫn giữ `exp` ban đầu trừ khi AS/RS revoke/denylist hoặc áp validation policy mới.

**Câu 3. User bấm logout tại T0+120s và BFF revoke refresh token R1. A1 đã bị RS từ chối ngay chưa?**

**Chưa chắc.** Với JWT offline không có denylist/introspection, A1 có thể tiếp tục được RS chấp nhận đến expiry cộng leeway cấu hình. Revoke refresh ngăn xin access token mới bằng R1 nhưng **không tự xóa bản sao A1**.

**Câu 4. Nếu attacker thử A1 tại T0+311s thì sao?**

Theo policy expiry `exp=T0+300s`, `skew=10s`, boundary `now=exp+10s` là **reject**. T0+311s chắc chắn phải bị từ chối theo timing, nếu clock RS chính xác và chính sách được thực thi.

**Câu 5. Nếu AS phát JWT A2 mới tại T0+119s từ R1 trước lúc revoke, attacker có thể dùng A2 bị lộ đến khi nào?**

Phụ thuộc `exp` **của chính A2**, cùng với RS revoke/denylist policy. Không có chuyện thu hồi R1 sau đó tự bảo đảm mọi A2 đã cấp đều inactive ở RS offline. Mỗi token có vòng đời riêng.

**Câu 6. Nếu thay JWT A1 bằng opaque token và RS introspect mỗi request, có ngăn replay ngay lúc T0+65s không?**

**Không mặc nhiên.** AS còn coi token active và attacker có cùng chuỗi Bearer, nên vẫn có thể được chấp nhận. Nhưng sau khi AS revoke access token, RS introspect mới có thể trả `active=false` để chặn sớm, tùy cache/propagation.

**Câu 7. DPoP giúp gì khi attacker chỉ lấy được chuỗi access token?**

Nếu A1 được cấp **DPoP-bound** và RS kiểm proof đúng, attacker thiếu private key không thể tự tạo DPoP proof hợp lệ cho request mới. Dù vậy token vẫn cần `exp`, scope/audience và revoke policy; mất cả token lẫn private key là một threat khác.

**Câu 8. Nếu attacker có bản sao một DPoP proof P1 chưa quá 5 giây, RS chỉ kiểm `iat` mà không kiểm `jti` thì sao?**

P1 có thể bị replay trong cửa sổ mà proof còn được nhận, nếu các binding khác cũng phù hợp. RS phải thực hiện replay detection/nonce policy theo RFC 9449, không chỉ rút ngắn proof TTL.

**Câu 9. Nếu client A được phép đọc hóa đơn của An, token sống 5 giây nhưng scope vô tình là `invoice:admin` thì có an toàn không?**

**Không.** Attacker có thể thực hiện request gây hậu quả ngay lập tức trong 5 giây. Cần least privilege, audience isolation, object-level authorization, risk policy và theo dõi abuse.

**Câu 10. User xác thực MFA từ sáng, đến tối BFF refresh lấy access token mới có `iat` mới. Điều đó chứng minh user vừa MFA lại không?**

**Không.** `iat` của access token là thời điểm phát token; OIDC **`auth_time`** và ACR/AMR theo contract mô tả authentication event. Các hành động nhạy cảm cần chính sách step-up/freshness riêng.

**Câu 11. Kéo dài `exp` cho request thanh toán đang chạy 10 phút có phải giải pháp tốt?**

Không nên sửa/gia hạn token do client tự quyết. Thiết kế tốt hơn là token renew trước khi gửi request, transaction timeout/idempotency, server-side state machine và authorization check tại các bước cần thiết. Request đã bắt đầu có thể có policy xử lý riêng; không biến một token cũ thành credential bất tử.

**Câu 12. Nếu giảm TTL xuống 60 giây gây bùng nổ refresh requests, có nên tự động tăng RS skew lên 120 giây để “tránh lỗi” không?**

**Không.** Như vậy có thể làm token 60 giây được nhận lâu hơn nhiều so với mục tiêu. Cần sửa refresh scheduling, jitter, AS capacity, time sync, token caching trong phạm vi an toàn và policy vận hành.

**Câu 13. Một worker M2M không có refresh token, token 5 phút nhưng job 2 giờ. Phải cấp token 2 giờ?**

**Không bắt buộc.** Worker có thể dùng **client_credentials** để xin token ngắn hạn mới khi cần, với client authentication đáng tin, rate limit, checkpoint và error handling phù hợp. Không lưu client private key/secret trong log hoặc container image.

**Câu 14. `jti` xuất hiện trong A1 thì một API request thứ hai với A1 phải bị reject ngay không?**

**Không** với access token được thiết kế để dùng nhiều request. `jti` có thể phục vụ audit/denylist; cơ chế replay detection per-request thường áp cho **DPoP proof `jti`** hoặc one-time artifact như authorization code, chứ không cấm toàn bộ reuse hợp pháp của A1.

## 20. Checklist short lifetime chống token replay

1. **Threat model rõ:** Hệ thống đang giảm replay của Bearer access token, refresh credential, DPoP proof hay authorization code?
2. **Không hứa chống replay tuyệt đối:** TTL ngắn chỉ thu hẹp thời gian khai thác; attacker có thể dùng token ngay lập tức?
3. **AS quyết định TTL:** Lifetime theo client/grant/resource/scope/risk được AS áp, client không tự đặt `exp`?
4. **JWT thời gian đúng:** `iat`, `nbf`, `exp` là NumericDate, đúng Unix seconds; `exp` được kiểm tại RS?
5. **Chặn token quá hạn:** Với skew=0, `now>=exp` luôn reject; với skew > 0, boundary đã được review/test?
6. **Clock skew giới hạn:** AS/RS đồng bộ thời gian ở mọi region; leeway nhỏ hơn nhiều so với TTL cần bảo vệ?
7. **Maximum issued lifetime:** RS có policy kiểm `exp-iat` và issuer signature khi profile yêu cầu, tránh JWT phát quá dài?
8. **Issuer và audience:** `iss` trusted và `aud` khớp exact Resource Server; không nhận token sai resource dù còn hạn?
9. **Token purpose/typ:** Không chấp nhận OIDC ID token/refresh token như access token; JWT profile/alg/key được verify?
10. **Scope và object authorization:** `scope` tối thiểu và kiểm tenant/owner/role/business policy trên từng API request?
11. **HTTPS và storage:** Không truyền Bearer token qua HTTP, URL query, logs, APM hoặc browser storage không cần thiết?
12. **JWT vs opaque hợp đồng rõ:** RS biết mình kiểm offline hay introspect; `active=true` chưa đủ cho authorization?
13. **Introspection cache đúng deadline:** Không vượt `exp`, cache-control/AS contract và revocation SLO; không fail open khi AS lỗi?
14. **Revocation propagation đo được:** Nếu cần chặn token trước expiry, dùng introspection/denylist/events theo policy và đo độ trễ?
15. **Refresh token bảo vệ mạnh:** Rotation/reuse detection, idle/absolute lifetime, revoke family/grant, secret storage và sender constraint khi cần?
16. **Không tái dùng refresh cũ:** Concurrent refresh xử lý atomic/single-flight; không phát descendant sai sau revoke?
17. **DPoP đúng profile:** Kiểm proof signature/key binding, `htm`, `htu`, `ath`, `iat`, `jti` và nonce khi áp dụng?
18. **mTLS sender binding:** Certificate client ở request khớp `cnf.x5t#S256`; proxy headers không được caller tự khai?
19. **Authorization code single-use:** Lifetime ngắn đi cùng PKCE/client/redirect binding và atomic consumption?
20. **OIDC freshness tách biệt:** `auth_time`/ACR dùng cho reauthentication/step-up, không lấy access-token `iat` thay thế?
21. **Business idempotency:** Payments/orders có idempotency key, transaction binding và duplicate-processing defense riêng?
22. **Long-running jobs:** Renew token qua grant hợp lệ, checkpoint/retry, không kéo access TTL vô hạn?
23. **Multi-device/session scope:** Logout tại RP/OP khác AS token revoke; không hứa global logout nếu chỉ xóa cookie?
24. **Observability an toàn:** Theo dõi TTL histogram, expired rejects, refresh rates, DPoP replay, clock offset và revoke lag; không log raw token?
25. **Canary và negative tests:** Boundary exp/nbf/skew, token cũ, wrong iss/aud/scope, JWT signature sai, opaque inactive, DPoP replay và concurrent refresh?
26. **Incident plan:** Khi token lộ, revoke/contain, kiểm RS enforcement và log, giảm blast radius; không chỉ đợi token hết hạn?

**Ghi nhớ:** **Short lifetime giảm khoảng thời gian mà một access token bị đánh cắp có thể bị phát lại, nhưng không ngăn được replay tức thì.** Access-token `exp` phải được RS kiểm với clock đáng tin; `expires_in` không phải quyền cho client tự gia hạn. JWT offline, opaque introspection, cache và revocation có các độ trễ khác nhau. Refresh token dài hạn phải được bảo vệ bằng rotation/reuse policy; token sender-constrained như DPoP/mTLS giúp chặn **bản sao token không có khóa tương ứng**. Cuối cùng, **issuer, audience, scope, object-level authorization và business idempotency** vẫn là những ranh giới bảo mật riêng — TTL ngắn không thay thế chúng.

### Chuẩn và tài liệu tham khảo

- **RFC 7519 — JSON Web Token (JWT):** `exp`, `nbf`, `iat`, `jti`, NumericDate và token validation time semantics.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token JWT type, expiry, issuer/audience và validation ở Resource Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay mitigations, refresh token rotation/sender constraint, audience/resource binding và security best practices.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** tính chất Bearer token, cách truyền trong Authorization header và lỗi `invalid_token`.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** `expires_in` access token, grant types, authorization code lifetime và refresh token.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** ràng buộc authorization code với code verifier, chống code interception.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, `exp`, introspection caching và security considerations.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant trước expiration và giới hạn propagation.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** token cấp đúng resource/audience.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** `jti`, `iat`, `htm`, `htu`, `ath`, nonce và sender-constrained access tokens.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc access token với client certificate.
- **RFC 8725 — JSON Web Token Best Current Practices:** thuật toán, key confusion, token substitution và validation.
- **OpenID Connect Core 1.0:** `auth_time`, `max_age`, `acr`, `amr` và ID-token validation; khác access-token lifetime.
- **Spring Security Reference — OAuth2 Resource Server/JWT:** JWT decoder, issuer/audience/expiry validators và clock skew policy.
- **OWASP OAuth 2.0 Cheat Sheet, Authentication Cheat Sheet và Session Management Cheat Sheet:** token TTL, revocation, session/reauthentication, replay và secure storage.
