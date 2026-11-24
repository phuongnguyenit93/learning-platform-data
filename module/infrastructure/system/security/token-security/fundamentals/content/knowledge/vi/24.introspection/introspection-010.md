# Bảo vệ endpoint introspection

Một hệ thống đơn hàng sử dụng **opaque access token**. Khi ứng dụng gửi `Authorization: Bearer ...` đến Orders API, API cần hỏi authorization server (AS) xem token còn hoạt động không, dành cho resource nào và mang những scope gì. AS cung cấp **OAuth 2.0 Token Introspection Endpoint** theo **RFC 7662**.

Đây là một endpoint **nhạy cảm**: ai gọi được nó có thể tìm hiểu trạng thái của token và, tùy quyền truy cập, nhận metadata như `sub`, `client_id`, `scope`, `aud` và thời hạn. Nếu triển khai kiểu “bất kỳ ai gửi token đều được nhận thông tin người dùng”, introspection endpoint có thể trở thành **dịch vụ dò quét token, xác nhận token bị đánh cắp và rò rỉ dữ liệu danh tính**. Ngược lại, nếu một resource server xem `active=true` là đủ để cho phép request, token dành cho API khác cũng có nguy cơ bị chấp nhận.

**Bảo vệ introspection endpoint** nghĩa là bảo vệ **cả hai phía**:

- **Phía AS:** xác thực và phân quyền chính resource server/client gọi introspection; giới hạn token nào caller được tra cứu và claims nào được tiết lộ; dùng TLS, rate limiting, audit, chính sách chống enumeration.
- **Phía resource server (RS):** chỉ gọi endpoint của issuer đã tin cậy; bảo vệ credential introspection; kiểm `active` và các thuộc tính **issuer, audience, scope, token type, expiry, tenant và chính sách nghiệp vụ**; xử lý cache, outage và thu hồi theo mô hình tin cậy.

Bài thuộc chương **Introspection** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Chúng ta sẽ triển khai nguyên tắc RFC 7662 trong OAuth 2.0/OIDC, phân biệt JWT/opaque token, access/refresh/ID token, thiết kế Spring Security, ví dụ HTTP/Java, xử lý bảo mật mạng, quản lý cache–revocation, threat modeling và bộ kiểm thử.

## 1. Introspection là gì và tại sao endpoint cần được bảo vệ?

**Token introspection** là yêu cầu từ một thành phần được phép — thường là resource server — đến authorization server nhằm hỏi về **trạng thái và metadata của một token**.

Ví dụ:

```text
Ứng dụng gửi request:
  GET /api/orders/42
  Authorization: Bearer OPAQUE_ACCESS_TOKEN

Orders API:
  POST https://id.example.test/oauth2/introspect
  token=OPAQUE_ACCESS_TOKEN
  + credential riêng của Orders API để gọi introspection

Authorization Server:
  xác thực Orders API
  kiểm Orders API có được tra token này không
  trả { "active": true, ... } hoặc { "active": false }

Orders API:
  kiểm active, issuer/audience/scope, quyền đơn hàng/tenant
  PERMIT hoặc DENY
```

Introspection thường hữu ích với **opaque token**, vì RS không thể tự giải mã token thành claims có ý nghĩa. Một số hệ thống cũng introspect **JWT access token** khi muốn kiểm trạng thái revocation hoặc policy động. Nhưng **JWT được introspect không đồng nghĩa mọi JWT phải introspect**, và RFC 7662 không bắt buộc một RS dùng cách này thay kiểm chứng chữ ký.

### Vì sao đây là một endpoint nhạy cảm?

Một response cho token còn hoạt động có thể cung cấp:

| Dữ liệu | Giá trị sử dụng | Rủi ro nếu lộ |
|---|---|---|
| `active` | Token còn được AS công nhận không? | Xác nhận token bị đánh cắp có còn dùng được. |
| `sub` | Định danh subject. | Rò định danh/tương quan hoạt động. |
| `client_id` | OAuth client nhận token. | Tiết lộ quan hệ ứng dụng–người dùng. |
| `scope` | Quyền được cấp. | Lộ năng lực của credential và bề mặt tấn công. |
| `aud` | Resource server(s) dự kiến nhận. | Tiết lộ cấu trúc API hoặc xác nhận token dùng ở đâu. |
| `exp` / `iat` / `nbf` | Mốc thời gian. | Kẻ tấn công biết cửa sổ hiệu lực. |
| `iss` / `jti` | Issuer/token reference. | Tạo tương quan/token scanning nếu chính sách lỏng. |
| Claims tùy chỉnh | Tenant, organization, service role. | Rò dữ liệu nội bộ hoặc thông tin nhạy cảm. |

**Không cấp quyền đọc toàn bộ metadata token cho một caller chỉ vì caller biết chuỗi token.** Introspection caller phải có danh tính/quyền riêng, và metadata cần giới hạn theo nhu cầu.

## 2. Phân biệt token đang được tra với credential của caller

Đây là điểm quan trọng nhất trong bảo vệ endpoint.

Một request introspection thường có **hai loại thông tin độc lập**:

1. **`token` trong form body:** giá trị access token/refresh token mà RS muốn kiểm tra.
2. **Credential để xác thực caller với AS:** ví dụ client ID + client secret của RS, mTLS certificate hoặc client assertion do AS cho phép.

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic ORDERS_RS_AUTH_PLACEHOLDER

token=OPAQUE_ACCESS_TOKEN_PLACEHOLDER&token_type_hint=access_token
```

**Không dùng giá trị `token` được kiểm tra làm bằng chứng caller có quyền gọi introspection.** Nếu AS cho phép “ai biết token thì được introspect” mà không có kiểm soát khác, kẻ đánh cắp token có thể hỏi AS để biết token của ai, có quyền gì và còn hạn bao lâu.

| Credential | Nguồn | Mục đích | Có thể thay thế credential kia? |
|---|---|---|---|
| `token` (token under inspection) | Được client gửi đến resource API. | Đối tượng cần kiểm trạng thái/claims. | **Không.** |
| Client secret/private-key assertion/mTLS của RS | Do AS cấp hoặc tin theo đăng ký. | Xác thực **caller** đang yêu cầu introspection. | **Không.** |

Một AS có thể cho phép phương thức xác thực khác theo chính sách, như một **OAuth access token riêng** được cấp cho caller để truy cập introspection service. Điều cốt lõi không phải bắt buộc mọi hệ thống dùng HTTP Basic, mà là **AS phải xác thực/phân quyền việc truy cập introspection**.

## 3. Yêu cầu chuẩn từ RFC 7662 đối với endpoint

RFC 7662 định nghĩa token introspection tại một endpoint của AS. Những nguyên tắc nền tảng:

- RS/caller dùng **HTTP POST** với form body `application/x-www-form-urlencoded`.
- Form có tham số bắt buộc **`token`**; có thể có **`token_type_hint`** như gợi ý loại token.
- Introspection endpoint phải được **bảo vệ**, yêu cầu hình thức **authorization để truy cập endpoint** (ví dụ client authentication hoặc một access token dành cho việc gọi endpoint).
- AS xác minh token theo chính sách và trả JSON với top-level field **`active`**, một giá trị boolean.
- Token không hoạt động, không tồn tại hoặc caller không được phép introspect token cụ thể đó phải được xử lý theo ngữ nghĩa **`active=false`** và không tiết lộ các thuộc tính không cần thiết của token.
- AS có thể đưa các metadata bổ sung đối với token active, chẳng hạn `scope`, `client_id`, `sub`, `aud`, `iss`, `exp`; những trường này không mặc nhiên bắt buộc trong mọi response.
- Protected resource có thể cache dữ liệu introspection theo chính sách, nhưng phải cân nhắc độ trễ thu hồi và tính nhất quán.
- Giao tiếp cần dùng **TLS** và các kiểm soát mạng/credential an toàn.

**Hai loại thất bại phải được phân biệt:**

1. **Caller không được phép sử dụng endpoint** ⇒ endpoint từ chối truy cập, thường HTTP 401/403 theo authentication/authorization scheme.
2. **Caller đã được phép gọi endpoint, nhưng token không hoạt động hoặc không thuộc quyền tra cứu của caller** ⇒ response introspection có thể chỉ chứa `{"active":false}` theo RFC 7662.

Không đồng nhất mọi lỗi thành `{"active":false}`: nếu credential của RS sai, đó không phải kết luận đáng tin rằng token người dùng đã bị thu hồi.

## 4. Request RFC 7662: HTTP POST, encoding và tham số

Ví dụ một RS gửi request:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic INTROSPECTION_CLIENT_AUTH_PLACEHOLDER

token=OPAQUE_ACCESS_TOKEN_PLACEHOLDER&token_type_hint=access_token
```

**Trong request thật:**

- Phải gửi qua HTTPS với xác minh TLS server certificate và tên máy phù hợp.
- Body phải được form-encode đúng, đặc biệt token có ký tự `+`, `&` hoặc `=`.
- Không gắn token trong URL query, đường dẫn, access log hoặc trace attributes.
- Authorization header phải chứa credential của **caller**, không phải access token đang bị introspect (trừ một profile ủy quyền endpoint riêng đã được AS chấp nhận).
- `token_type_hint` là gợi ý để AS tối ưu tra cứu; nó **không phải một tuyên bố đáng tin về token type**, không được dùng để bỏ kiểm tra thật.
- Không gửi form chứa raw token tới endpoint được lấy trực tiếp từ input của user.

### `token_type_hint` không chứng minh token là access token

Một client có thể gửi:

```text
token_type_hint=access_token
```

nhưng giá trị `token` thực tế có thể là token không hợp lệ hoặc một loại credential khác. AS phải xác định token thật theo logic của mình. RS cũng không được coi hint là bằng chứng token có thể dùng để gọi API nghiệp vụ.

Với API chỉ chấp nhận access token, nếu metadata cho thấy token là refresh token hoặc ID token, **phải từ chối**. Không dùng token type hint thay type/profile validation.

## 5. Response `active=true`: vẫn chưa phải “cho phép truy cập”

Ví dụ AS trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "client_id": "invoice-companion",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1795410600,
  "iat": 1795410000,
  "iss": "https://id.example.test",
  "aud": "orders-api"
}
```

Dữ liệu ví dụ chỉ mô tả token được công nhận đang active theo chính sách AS. **Orders API chưa thể cho phép mọi request**.

Một resource server nghiêm ngặt cần hỏi:

| Kiểm tra | Câu hỏi |
|---|---|
| **AS/issuer tin cậy** | Response đến từ introspection endpoint đã được cấu hình/pin cho issuer này? |
| **`active`** | Giá trị là boolean `true` thật, không phải chuỗi `"true"`? |
| **Token purpose/type** | Đây là access token được dùng hợp lệ tại resource API? |
| **`aud`/resource** | Token được phát cho **Orders API** không? |
| **`scope`** | Có đúng các scope cho endpoint? |
| **`exp`/`nbf`** | Còn hạn theo hợp đồng và policy? |
| **`client_id`/subject** | Client và subject phù hợp loại principal được phép? |
| **Tenant/owner** | Chủ thể có quyền với đơn hàng cụ thể không? |
| **Revocation/cache** | Có trạng thái revoke mới hơn response cache không? |

**Khi metadata cần thiết không được trả về**, RS phải có một **nguồn xác minh đáng tin khác** hoặc **từ chối**. Không diễn giải thiếu `aud` thành “token dành cho mọi resource server”, cũng không diễn giải thiếu scope thành “toàn quyền”.

## 6. `active=false`: hạn chế tiết lộ thông tin

Response cho token không hoạt động:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
```

Các nguyên nhân có thể dẫn đến `active=false`:

- Token không tồn tại trong AS.
- Token đã hết hạn.
- Token bị thu hồi hoặc grant không còn hiệu lực.
- Token không phù hợp trạng thái/loại token đang được kiểm theo policy.
- Caller **không được phép introspect token cụ thể đó**.
- Các điều kiện hiệu lực khác do AS quyết định.

**RS không được dùng `active=false` để suy đoán chính xác nguyên nhân**, và AS không nên tiết lộ chi tiết “token này thuộc user X nhưng bạn không có quyền” cho caller không được phép xem.

Một response kiểu sau có thể làm lộ dữ liệu không cần thiết:

```json
{
  "active": false,
  "sub": "user-123",
  "client_id": "sensitive-partner",
  "reason": "revoked_by_admin",
  "last_used_ip": "203.0.113.40"
}
```

**Không dùng response như thế** trong thiết kế bảo mật chung: chỉ field `active=false` là đủ cho client ra quyết định từ chối. Nên tránh thêm chi tiết của token không hoạt động, theo yêu cầu bảo mật của RFC 7662.

## 7. Endpoint authentication và token authorization là hai lớp khác nhau

Một AS nên dùng **hai quyết định độc lập**:

1. **Caller có được phép sử dụng introspection endpoint không?**
2. **Caller này có được phép biết trạng thái/metadata của token đang yêu cầu không?**

```mermaid
flowchart TD
    REQ[POST /introspect] --> TLS{TLS và endpoint policy hợp lệ?}
    TLS -- Không --> TRANSPORT[Từ chối kết nối / request]
    TLS -- Có --> AUTH{Caller credential hợp lệ?}
    AUTH -- Không --> ERR[401/403 theo scheme]
    AUTH -- Có --> ALLOW{Caller được quyền introspect token này?}
    ALLOW -- Không --> FALSE[200: active=false]
    ALLOW -- Có --> STATUS{Token còn active theo AS?}
    STATUS -- Không --> FALSE
    STATUS -- Có --> META[200: active=true + metadata giới hạn]
```

**Ví dụ minh họa:**

- `orders-api` có credential riêng để introspect tokens cho Orders.
- `payments-api` có credential khác chỉ tra tokens của Payments.
- Một caller `analytics-job` không được đăng ký làm RS thì bị từ chối endpoint.
- `payments-api` hỏi về token chỉ dành cho Orders ⇒ AS có thể trả `active=false` để tránh tiết lộ token không thuộc phạm vi caller.
- `orders-api` hỏi đúng token dành cho Orders ⇒ AS có thể trả `active=true` với claims tối thiểu cần cho Orders API.

Ràng buộc này giúp chống việc một RS bị lộ credential dùng introspection để tra cứu tokens của **toàn bộ** hệ sinh thái.

## 8. Client authentication cho introspection endpoint

Các phương thức bảo vệ caller có thể dùng, tùy AS/profile:

| Phương thức | Cách chứng minh | Yêu cầu an toàn |
|---|---|---|
| `client_secret_basic` | Client ID/secret qua HTTP Basic trong TLS. | Secret manager, rotation, không log header. |
| `client_secret_post` | Secret trong form body khi AS hỗ trợ. | Rủi ro body logs; bảo vệ và redaction nghiêm ngặt. |
| `private_key_jwt` | Caller ký client assertion bằng private key được AS tin. | Xác minh `iss`, `sub`, `aud`, `exp`, `jti`/replay theo profile. |
| **mTLS client authentication** | Caller chứng minh nắm private key chứng thư. | Mutual TLS đúng end-to-end/proxy trust, cert lifecycle. |
| **Access token riêng cho introspection** | Bearer/sender-constrained token cho introspection service. | Token có audience/scope dành cho endpoint, TTL ngắn và policy caller. |

**Không khuyến nghị “một secret chung cho mọi resource server”.** Khi một RS bị xâm nhập, secret chung có thể làm lộ trạng thái token thuộc các RS khác.

### Credential phải ràng buộc với đúng caller

AS cần xác thực danh tính và map nó vào chính sách:

```text
Authenticated caller: orders-api-introspector
Allowed issuer: https://id.example.test
Allowed token usage: access_token
Allowed audience: orders-api
Allowed metadata: active, scope, client_id, sub, aud, exp
Rate/quota policy: orders-specific
```

Đây là **policy minh họa**, không phải bộ claims chuẩn bắt buộc của RFC 7662.

Nếu RS sử dụng `private_key_jwt` để xác thực, **client assertion JWT không phải access token** cho Orders API. Audience của assertion thường hướng đến token/introspection endpoint theo profile, trong khi audience của access token được kiểm là Orders API.

## 9. Mô hình least privilege cho từng resource server

Giả sử một AS phục vụ ba APIs:

| RS caller | Endpoint được phép | Tokens được introspect | Metadata cần thấy |
|---|---|---|---|
| Orders API | AS introspection endpoint | Token cho `orders-api` | `active`, `aud`, `scope`, `sub`, `client_id`, expiry. |
| Payments API | AS introspection endpoint | Token cho `payments-api` | Claims phù hợp chính sách thanh toán. |
| Inventory API | AS introspection endpoint | Token cho `inventory-api` | Scope/subject/resource tương ứng. |
| Public web app | Không mặc định | Không có quyền introspection mọi token. | Không có. |

**Không dựa trên một chuỗi tên RS do caller tự gửi trong body**, ví dụ `resource=orders-api`, để xác định quyền của caller. Ràng buộc phải dựa trên **danh tính đã xác thực của caller** và policy AS.

Đối với JWT multi-audience, AS có thể cho phép nhiều RS được introspect cùng token, nhưng phải cân nhắc metadata được trả. Token có `aud` chứa Payments không có nghĩa Orders cần nhìn thấy toàn bộ claims thanh toán nhạy cảm.

### Resource-specific metadata filtering

AS có thể giảm bề mặt tiết lộ bằng cách chỉ trả những claims mà RS cần:

```json
{
  "active": true,
  "client_id": "invoice-companion",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410600
}
```

Nếu RS cần `sub` để kiểm ownership, AS có thể cấp `sub` cho RS đó theo policy. Nếu không cần, đừng trả mọi profile/email/PII chỉ vì lưu trong token store.

**Privacy by design:** token metadata là dữ liệu có thể nhạy cảm, đặc biệt trong OIDC và hệ thống đa tenant.

## 10. Chống token scanning và enumeration

Một attacker có thể gửi lượng lớn token giả để tìm token thật:

```text
POST /introspect token=AAAA...
POST /introspect token=AAAB...
POST /introspect token=AAAC...
...
```

Với opaque token entropy cao, brute force toàn bộ không khả thi; nhưng các trường hợp sau vẫn đáng lo:

- Token có entropy thấp hoặc cấu trúc dễ đoán do AS triển khai lỗi.
- Attacker có một tập tokens lấy từ logs/traces/leak và muốn phân loại cái nào còn active.
- Caller credential của một RS bị đánh cắp.
- AS tiết lộ khác biệt giữa token tồn tại và token không tồn tại bằng response/latency.
- Endpoint không giới hạn request, khiến AS token database bị DoS.

**Biện pháp bảo vệ nhiều lớp:**

1. **Bearer/opaque token phải có entropy và cấu trúc an toàn**, phát từ CSPRNG.
2. **Xác thực caller** và giới hạn quyền theo audience/client/tenant.
3. **Rate limiting và quotas** theo client ID, RS identity, token reference/ASN/IP theo policy.
4. **Giới hạn kích thước request/body/token**, Content-Type, thời gian xử lý và concurrency.
5. **Không trả nguyên nhân token không active** cho caller không cần biết.
6. **Điều chỉnh timing để tránh side channel rõ ràng** khi truy vấn token tồn tại/không tồn tại.
7. **Audit và cảnh báo** lượng `active=false` lớn, tốc độ tra cứu bất thường, thay đổi phân phối audience.
8. **Tách tài nguyên hệ thống** giữa token issuance, user authentication và introspection để tránh cascade failure khi quá tải.

Rate limiting phải xét cả API gateway, load balancer, NAT và số lượng RS nodes hợp pháp. Một quota theo IP duy nhất có thể vô tình chặn toàn bộ fleet sau một egress NAT.

## 11. Tránh token type confusion

AS có thể quản lý nhiều loại credential:

- **Access token:** được trình đến RS.
- **Refresh token:** được trình đến token endpoint để lấy access token mới.
- **ID token (OIDC):** được RP kiểm tra authentication.
- **Authorization code/device code:** credential tạm trong grant flows; không phải access token.

Vì vậy, introspection endpoint không nên trở thành “dịch vụ xác minh mọi credential và cho phép dùng nó trong mọi API”.

| Credential được đưa vào `token` | Endpoint có thể xử lý? | RS nghiệp vụ được chấp nhận? |
|---|---|---|
| Opaque access token | Có, nếu AS hỗ trợ và caller được phép. | Chỉ khi `active=true`, đúng audience/scope/type. |
| JWT access token | Có thể, tùy AS và profile. | Vẫn cần validation/type/audience; introspection không tự mở quyền. |
| Refresh token | AS có thể hỗ trợ introspect cho caller được phép. | **Không.** Refresh token không dùng gọi business API. |
| OIDC ID token | Không mặc định thuộc profile introspection access token. | **Không.** ID token dành cho RP. |
| Authorization code/device code | Không được xem là access token. | **Không.** |

**Không tin `token_type_hint=access_token` nếu token thật là refresh token.** Nếu AS trả `active=true` cho refresh token mà RS không kiểm loại, đó là nguy cơ **credential confusion**.

Trong một hệ thống muốn RS chỉ truy cập tokens loại access, AS nên giới hạn introspection theo token class; RS có thể yêu cầu metadata phân loại từ nguồn tin cậy và fail closed nếu không xác định được.

## 12. Client credential bị lộ khác access token bị lộ

Nếu một attacker lấy được **access token** của user, họ có thể gọi API trong audience/scope cho phép khi token còn hợp lệ, trừ khi có sender constraint hoặc trạng thái chặn.

Nếu attacker lấy được **credential introspection của Orders API**, họ có thể:

- Gọi endpoint của AS dưới danh tính Orders RS, trong quyền đã cấp.
- Kiểm tra tính active và metadata của những token mà Orders RS được phép introspect.
- Gây quá tải hoặc mở rộng do thám khi rate limiting yếu.
- Kết hợp credential bị lộ với tập token lấy từ nơi khác để tối ưu tấn công.

**Credential introspection không nên trực tiếp cấp khả năng phát access token cho users**, trừ khi cùng client credential đã vô tình được cấp grant khác. Tốt nhất tách **RS introspection identity** khỏi **OAuth client credential dùng để xin access tokens** và chỉ cấp quyền cần thiết.

Khi sự cố xảy ra, cần **xoay/thu hồi credential introspection**, đánh giá token metadata đã bị hỏi, rate limits và logs, không chỉ invalidate access tokens.

## 13. TLS, mTLS, reverse proxy và network boundary

**Introspection endpoint phải được bảo vệ trên đường truyền.** Hơn nữa, chỉ bật HTTPS ở ingress không đủ nếu hệ thống không bảo đảm mạng nội bộ.

### Những câu hỏi vận hành cần trả lời

| Ranh giới | Kiểm soát |
|---|---|
| RS → AS public DNS | TLS certificate validation, hostname check, DNS/route allowlist. |
| Egress gateway | Chặn gọi hostname/IP tùy ý từ request user, kiểm redirect và proxy. |
| AS ingress | Caller authentication, rate limit, TLS policy, body size. |
| Load balancer → AS backend | TLS hoặc network trust được đánh giá, proxy identity binding đúng. |
| mTLS termination | Bảo đảm danh tính client certificate không bị giả qua header do Internet gửi vào. |
| Debug/observability | Redact form token và Authorization/client assertions. |
| Secrets store | Phân quyền đọc secret riêng cho workload, rotation và audit. |

**Không cấu hình token introspection URL từ JWT payload, `iss` do user nhập hoặc header bất kỳ của request.** AS phải được pin trong resource-server configuration hoặc khám phá qua metadata **issuer đã tin cậy** với kiểm soát SSRF/mix-up.

### mTLS không đồng nghĩa mạng riêng tự đủ an toàn

mTLS có thể xác thực caller bằng certificate, nhưng nếu gateway chấp nhận `X-Client-Cert` từ bên ngoài rồi tin nó, attacker có thể giả mạo client. Chỉ chấp nhận verified identity từ trusted TLS termination, xóa/ghi đè headers không tin cậy và bảo vệ kênh nội bộ.

## 14. URI introspection, AS discovery và chống SSRF

RFC 8414 có metadata mô tả AS capabilities, có thể công bố `introspection_endpoint` và các phương thức authentication hỗ trợ.

Ví dụ metadata minh họa:

```json
{
  "issuer": "https://id.example.test",
  "token_endpoint": "https://id.example.test/oauth2/token",
  "introspection_endpoint": "https://id.example.test/oauth2/introspect",
  "introspection_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
```

**Metadata là đầu vào cấu hình từ một issuer đã được tin**, không phải URL để client/user tự chọn.

- RS phải có **trust anchor** cho issuer và cho AS phục vụ resource.
- Nếu có nhiều issuer, phải có mapping rõ issuer → introspection URL → credential → allowed audience.
- Không cho caller dùng query như `?issuer=http://127.0.0.1:...` để khiến RS gửi token ra endpoint tùy ý.
- Không follow redirect cross-origin với body chứa raw access token.
- Bảo vệ DNS rebinding, địa chỉ private/link-local không hợp lệ và proxy settings theo threat model.
- Không cache nhầm metadata/credential giữa các tenants/issuers.

**Lỗi SSRF vào introspection endpoint thường đồng thời là lỗi rò access token**, vì RS gửi raw token của user tới nơi attacker kiểm soát.

## 15. Resource server nên xử lý introspection response như thế nào?

Một quyết định an toàn có thể mô tả:

```mermaid
flowchart TD
    API[HTTP request + Bearer access token] --> AS{Introspection caller được AS xác thực?}
    AS -- Không / timeout --> UN[Reject hoặc dùng cache còn hợp lệ theo policy]
    AS -- Có --> ACT{active đúng boolean true?}
    ACT -- Không --> U[401 invalid_token]
    ACT -- Có --> ISS{Issuer / endpoint tin cậy?}
    ISS -- Không --> U
    ISS -- Có --> TYPE{Token type / profile đúng access token?}
    TYPE -- Không --> U
    TYPE -- Có --> AUD{Audience dành cho RS?}
    AUD -- Không --> U
    AUD -- Có --> TIME{Expiry / nbf hợp lệ?}
    TIME -- Không --> U
    TIME -- Có --> SCOPE{Scope đáp ứng operation?}
    SCOPE -- Không --> F[403 insufficient_scope]
    SCOPE -- Có --> RES{Service/user tenant/owner policy?}
    RES -- Không --> F
    RES -- Có --> OK[PERMIT]
```

Lưu ý **AS trả `active=true` không chứng minh RS đã kiểm audience**. Việc AS không tiết lộ token cho caller không có quyền giúp giảm rủi ro, nhưng RS vẫn phải tự enforce các thuộc tính được yêu cầu.

### Kiểm kiểu dữ liệu

Một server trả:

```json
{"active": "true"}
```

không giống:

```json
{"active": true}
```

RS không nên ép kiểu một cách dễ dãi khiến `"false"` hoặc `1` trở thành boolean `true`. Claims `aud` có thể là chuỗi hoặc danh sách, tùy profile; cần kiểm type an toàn. `scope` là chuỗi scope phân cách bởi khoảng trắng theo OAuth 2.0, không phải chuỗi để tìm substring.

## 16. Spring Security Resource Server: cấu hình opaque token introspection

Spring Security 6.x hỗ trợ OAuth 2.0 Resource Server sử dụng introspection cho opaque bearer tokens.

Một mẫu cấu hình Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://id.example.test/oauth2/introspect"
          client-id: "ORDERS_INTROSPECTION_CLIENT_ID"
          client-secret: "INTROSPECTION_SECRET_FROM_SECRET_MANAGER"
```

Những chuỗi chứa `CLIENT_ID`/`SECRET_MANAGER` là **placeholders**, không phải credential thực. Production phải inject secret bằng secret manager hoặc cơ chế cấu hình an toàn, không commit secret vào repository. Cấu hình này chỉ mô tả cách tìm endpoint và xác thực caller; nó **không tự chứng minh token đúng Orders audience** hay thỏa tenant policy.

Một SecurityFilterChain minh họa:

```java
@Configuration
@EnableMethodSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/*/approve")
                .hasAuthority("SCOPE_orders.approve")
            .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
```

Trong Spring Security, introspected scopes thường được ánh xạ thành `GrantedAuthority` có prefix `SCOPE_`. Tuy nhiên, **scope mapping không thay audience validator**. Một token của Payments có scope tên giống `orders.read` vẫn không được chấp nhận ở Orders API nếu audience sai.

**Giới hạn ví dụ:** imports, CSRF/CORS/session policy, exceptions, secret rotation, timeouts, multi issuer và business authorization được lược bỏ. Không tắt CSRF đại trà trên app vẫn dùng browser cookies; đánh giá riêng nếu API chỉ xác thực Bearer không dùng ambient credentials.

## 17. Spring Security: thêm kiểm tra audience vào introspection

Có thể bọc `OpaqueTokenIntrospector` để kiểm audience **trước khi tạo authenticated principal**.

Ví dụ Java/Spring Security 6.x (API constructor có thể thay đổi theo phiên bản; kiểm tài liệu của bản đang dùng):

```java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionPolicyConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            IntrospectionSettings settings) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                settings.uri(),
                settings.clientId(),
                settings.clientSecret());

        String requiredAudience = "orders-api";
        String expectedIssuer = "https://id.example.test";

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token); // rejects inactive/invalid token

            Object aud = principal.getAttribute("aud");
            Object iss = principal.getAttribute("iss");

            if (!matchesAudience(aud, requiredAudience)
                    || !expectedIssuer.equals(iss)) {
                throw new OAuth2IntrospectionException(
                    "Introspection metadata policy mismatch");
            }

            return principal;
        };
    }

    private static boolean matchesAudience(Object value, String expected) {
        if (value instanceof String single) {
            return Objects.equals(single, expected);
        }
        if (value instanceof Collection<?> many) {
            return many.stream().anyMatch(expected::equals);
        }
        return false; // missing/malformed aud -> reject
    }
}
```

`IntrospectionSettings` là **configuration record/class do ứng dụng định nghĩa** có các field `uri/clientId/clientSecret`. Không phải class Spring có sẵn. Ở môi trường production, cần validate settings từ issuer tin cậy và bảo vệ credentials.

**Điểm quan trọng:**

- Delegate gọi AS và chỉ tạo principal khi token được coi là active theo implementation.
- Wrapper kiểm `aud` và `iss` từ metadata **đáng tin**, từ chối trường thiếu/sai kiểu.
- Nếu AS không trả `iss` hoặc `aud` mà hợp đồng yêu cầu, **không mặc định bỏ validator**. Cần điều chỉnh policy/mapping AS–RS hoặc có nguồn bảo đảm khác.
- Khi support nhiều issuer, dùng mapping credential/endpoint/policy riêng, không cho token tự chọn introspection endpoint.
- Cần thêm **token-type/client-policy/tenant checks** theo profile; ví dụ không chứng minh đủ production.
- Tránh ghi chuỗi token vào exception messages/metrics.

## 18. Java: kiểm scope và metadata một cách fail-closed

Để quyết định operation, RS có thể dùng authorities đã được framework tạo từ introspection response:

```java
// Minh họa business authorization sau khi principal đã được xác minh.
boolean canReadOrders(VerifiedCaller caller, Order order) {
    return caller.authorities().contains("SCOPE_orders.read")
        && caller.issuer().equals("https://id.example.test")
        && caller.audiences().contains("orders-api")
        && order.tenantId().equals(caller.permittedTenantId())
        && orderServicePolicy.clientAllowed(caller.clientId());
}
```

`VerifiedCaller` và các APIs này là **pseudocode của ứng dụng**, không phải class Spring Security chuẩn.

Sai lầm:

```java
// SAI: chỉ có active=true là đủ, không kiểm aud/scope/tenant.
if (introspectionResponse.isActive()) {
    return allOrders;
}
```

Đúng hướng:

1. Xác minh caller/metadata từ AS tin cậy.
2. Kiểm `active`, loại token, audience và thời hạn.
3. Kiểm scopes với **so khớp giá trị chính xác**.
4. Kiểm user/service principal, tenant, object ownership.
5. Ghi audit quyết định mà không lưu raw token.

## 19. Phía AS: authorization cho introspection endpoint

Nếu sử dụng **Spring Authorization Server**, nên tận dụng cấu phần token introspection có sẵn và cơ chế client authentication/authorization của AS thay vì tự mở một REST controller public trả mọi claims.

Một chính sách AS khái niệm:

```text
on POST /oauth2/introspect:

  require TLS, valid form Content-Type and bounded request size

  caller = authenticateIntrospectionCaller(request)
  if caller not authenticated or not permitted endpoint use:
      return scheme-specific 401/403

  token = request.form["token"]
  if missing/invalid token shape:
      return protocol error or active=false per policy

  record = lookupTokenWithSafeIndex(token)
  if record missing/inactive:
      return {"active": false}

  if !policy.mayIntrospect(caller, record):
      return {"active": false}

  metadata = policy.filterClaimsForCaller(caller, record)
  return {"active": true, ...metadata}
```

Đây là **pseudocode**, không phải hướng dẫn thay thế framework bảo mật bằng một custom endpoint thiếu các bảo vệ RFC.

### Điểm cần lưu ý trong persistence

- Token reference có thể được lưu dưới dạng hash/HMAC/digest phù hợp thay vì plaintext để giảm tác động database leak.
- Database lookup phải có index và giới hạn tài nguyên để chống DoS.
- Kiểm `exp`, `nbf`, grant state, revocation, client status và token class.
- **Không trả thông tin token inactive**.
- Không cho caller chọn metadata tối đa tùy ý qua tham số query/form.
- Scope/resource của token phải lấy từ **record đã cấp**, không từ request introspection.
- Việc tra cứu và cấp response phải xét concurrency và revocation timing.

**AS thực thi phân quyền cho caller không thay quyền nghiệp vụ của RS**. AS có thể nói token active và đúng audience, còn Orders API vẫn có thể từ chối nếu order không thuộc tenant/user được phép.

## 20. Response shaping và quyền riêng tư

Một response introspection có thể chứa claims ngoài tập RFC 7662 chuẩn. Vì vậy, AS cần quản trị schema như một API dữ liệu nhạy cảm.

| Caller | Metadata cần | Metadata nên hạn chế |
|---|---|---|
| Orders API | `active`, `sub` hoặc service principal, `aud`, `scope`, `exp`. | Email, số điện thoại, roles thuộc Payments nếu không cần. |
| Payments API | Claims thanh toán và risk context theo policy. | Hồ sơ Orders không liên quan. |
| Gateway | `active`, `aud`, `scope` và route auth context cần thiết. | PII chi tiết nếu business service tự kiểm. |
| Monitoring | Metrics tổng hợp/correlation ID. | Raw access/refresh tokens, subject details khi không cần. |

Nếu AS trả thông tin nhận diện cá nhân, hãy đánh giá thời hạn lưu, log retention, quyền truy cập và hợp đồng chia sẻ dữ liệu. **Introspection không nên trở thành API lấy profile người dùng ngoài phạm vi consent/authorization**.

**ID token dành cho RP** trong OIDC; đừng dùng introspection endpoint như cách thay thế UserInfo endpoint hoặc chuyển toàn bộ OIDC claims cho mọi RS.

## 21. Caching introspection: hiệu năng và revocation latency

Không có cache, mỗi request vào API có thể tạo thêm một request từ RS đến AS. Với tải lớn, điều đó ảnh hưởng latency, chi phí và khả năng chịu lỗi. Nhưng cache `active=true` quá lâu làm **trễ việc phát hiện revoke**.

### Ví dụ

```text
T=00s: AS introspection trả active=true, exp còn 10 phút
T=01s: RS cache kết quả trong 60 giây
T=15s: User revoke grant/token ở AS
T=20s: RS dùng active=true trong cache -> có thể tiếp tục cho phép
T=61s: Cache hết hạn; RS hỏi lại AS -> active=false
```

**Revoke tại AS ≠ RS lập tức từ chối nếu RS còn cache hợp lệ theo chính sách.** Tương tự, một JWT tự chứa chỉ kiểm signature/exp cũng có thể không thấy revocation trước expiry.

### Những yếu tố xác định cache TTL

| Yếu tố | Ảnh hưởng |
|---|---|
| Access token expiry | Không cache active vượt thời hạn token. |
| Revocation latency mục tiêu | TTL cần tương thích cam kết bảo mật. |
| Độ nhạy API | Payments/PII có thể cần TTL ngắn hơn Orders read. |
| Độ trễ/introspection load | TTL ngắn tăng số request AS. |
| Outage policy | Không kéo dài cache vô hạn để “giữ dịch vụ chạy”. |
| Permission changes | Roles, scope, tenant hoặc policy có thể bị thay đổi giữa các lần cache. |
| Sender-constrained tokens | Cache trạng thái token **không thay xác minh proof mỗi request**. |

Công thức khái niệm:

```text
cacheTtl <= min(
    tokenRemainingLifetime,
    configuredMaximumCacheDuration,
    securityRevocationLatencyBudget
)
```

Đây là **nguyên tắc thiết kế**, không phải một công thức TTL cứng được RFC 7662 quy định. Cần điều chỉnh clock skew, AS response time, cache jitter và policy yêu cầu trạng thái tức thời.

### Cache key và partitioning

Không cache đơn giản theo **mỗi raw token** mà bỏ issuer/caller/resource:

```text
SAI:
  cacheKey = token

ĐÚNG HƯỚNG:
  cacheKey = HMAC(token) + trustedIssuer + introspectionCallerId
             + policyVersion + audienceContext
```

Dùng HMAC/digest bảo vệ để tránh đưa raw token vào metrics/cache key/logs dễ đọc. Chọn key chính xác theo trust model: **cùng token có thể active=true với Orders RS nhưng active=false với Payments RS** do caller-specific disclosure. Không chia sẻ cache giữa tenants/issuers chỉ vì token string tình cờ giống nhau.

### Negative caching

Response `active=false` có thể cache ngắn để giảm scanning, nhưng cần cân nhắc một token đang chờ trạng thái hoặc token data propagation. Không biến một lỗi **network/401 của caller** thành negative cache token invalid một cách sai lệch.

## 22. AS outage, timeout và fail-open/fail-closed

Khi RS không gọi được introspection endpoint, có nhiều khả năng:

- AS hoặc mạng lỗi.
- Credential introspection hết hạn hoặc bị revoke.
- DNS/TLS trust bị lỗi.
- Caller bị rate limit.
- Endpoint trả response không đúng schema.
- Token thật sự invalid/active=false.

**Những trạng thái này không giống nhau**.

| Tình huống | Xử lý an toàn |
|---|---|
| AS trả `active=false` | RS từ chối token. |
| Credential RS bị trả 401/403 | RS không coi đây là token valid; alert và sửa auth/config. |
| Timeout và không có cache còn hợp lệ | Fail closed theo security policy; có thể trả 503/5xx phù hợp để phân biệt outage. |
| Timeout và cache positive còn hợp lệ | Có thể dùng cache trong TTL đã được policy phê duyệt. |
| 5xx từ AS | Không retry đồng loạt vô hạn; circuit breaker/backoff. |
| Response malformed, thiếu `active` hoặc sai kiểu | Từ chối, audit lỗi schema. |
| Token có sai audience/scope | Từ chối dù AS đang khỏe. |

**Không thiết kế:**

```java
// SAI nghiêm trọng:
try {
    return introspect(token);
} catch (Exception error) {
    return permitEverything();
}
```

Có thể chọn HTTP **503 Service Unavailable** với client khi hệ thống không thể xác minh một token trong outage (thay vì khẳng định token sai bằng 401), nhưng **không được cấp quyền truy cập dữ liệu dựa trên phỏng đoán**. Chọn mã HTTP theo contract/UX/rate limiting mà vẫn bảo đảm DENY khi trust chưa xác minh.

## 23. Rate limiting, bulkheads và chống thác lũ

Khi API nhận 20.000 requests/s và mỗi request gọi AS, AS có thể trở thành bottleneck.

Các lớp giảm tải:

1. **Connection pools và timeouts** có giới hạn.
2. **Per-caller quotas** tại introspection endpoint.
3. **Cache ngắn hạn** có partition key đúng và revoke budget rõ.
4. **Request coalescing/singleflight** cho cùng token/caller, tránh 1000 introspections trùng lặp đồng thời.
5. **Circuit breaker và bounded queue** ở RS, không fail-open.
6. **Backoff có jitter** cho lỗi kết nối/5xx; không generic retry cho mọi 4xx.
7. **Bulkhead** tách pool introspection khỏi các upstream quan trọng khác.
8. **Monitoring** token-check latency, active=false ratio, caller auth failures, cache hit rate.
9. **Protection against oversized input** và AS database lookup abuse.

Rate limiting không nên dựa duy nhất vào IP nguồn khi nhiều RS instances cùng dùng NAT. Đồng thời, quotas theo client ID phải dựa vào **định danh đã xác thực**, không nhận `client_id` do caller tự ghi một cách vô điều kiện.

## 24. Multi-issuer, multi-tenant và nhầm lẫn metadata

Một RS hỗ trợ nhiều AS cần phân biệt **nguồn tin cậy**.

Giả sử Orders API chấp nhận:

```text
Issuer A: https://id-a.example.test
Introspection A: https://id-a.example.test/introspect

Issuer B: https://id-b.example.test
Introspection B: https://id-b.example.test/introspect
```

**Không chọn endpoint dựa trên một trường issuer do opaque token tự hiển thị**, vì opaque token không có cấu trúc đáng tin cậy. Cũng không cho request user chọn issuer bằng header tùy ý rồi RS gửi raw bearer token đi khắp nơi.

Một số phương án:

- Mỗi API/tenant được cấu hình **duy nhất một issuer**.
- Có routing tin cậy theo hostname/resource/tenant configuration đã được xác minh.
- Dùng token format/namespace đã được AS–RS thống nhất và phân tách đủ để chọn provider mà không tin dữ liệu chưa xác minh.
- Tách introspection clients, credential stores và caches cho từng issuer/tenant.
- Từ chối token khi không xác định được trust domain một cách an toàn.

### Cross-issuer token confusion

Token được AS B công nhận không tự hợp lệ cho RS vốn chỉ tin AS A. Dù hai AS đều trả `active=true`, RS phải xác minh **issuer đúng policy** và audience của resource.

**Introspection endpoint là một trust oracle do chính RS chọn**, không phải “gọi bất kỳ server nào trả active=true rồi tin”.

## 25. Introspection và JWT tự chứa: khi nào dùng cái nào?

| Tiêu chí | JWT local validation | RFC 7662 introspection |
|---|---|---|
| Nguồn trạng thái | Chữ ký/claims JWT và key tin cậy tại RS. | AS trả trạng thái/metadata tại thời điểm tra. |
| Hỗ trợ opaque token | Không. | Có, điển hình. |
| Phụ thuộc mạng AS từng request | Không nếu JWKS/cache đã có. | Có thể, trừ khi RS cache. |
| Revocation trước `exp` | Cần denylist/tra trạng thái riêng. | AS có thể trả inactive, nhưng bị ảnh hưởng cache. |
| Bảo mật endpoint kiểm tra | JWKS/issuer, key rotation. | Caller authentication/authorization, TLS, rate limit, privacy. |
| Exposure metadata | JWT claims có thể được bearer đọc nếu token không mã hóa. | AS kiểm soát claims tiết lộ cho từng caller. |
| Độ trễ/availability | Thấp hơn tại RS nhưng key retrieval/policy có thể ảnh hưởng. | Bị chi phối bởi AS/network/cache. |

**Không cần chọn duy nhất một mô hình cho mọi API.** Ví dụ hệ thống dùng JWT cho API read có lifetime ngắn, opaque/introspection cho API cần revoke nhanh hoặc metadata động. Quan trọng là mô tả rõ **độ trễ thu hồi, trust boundary và trách nhiệm RS**.

### JWT introspection có làm bỏ chữ ký JWT được không?

Nếu RS quyết định dựa hoàn toàn vào **AS introspection qua kênh tin cậy** và AS chịu trách nhiệm xác minh token theo profile, RS có thể không tự parse/verify chữ ký JWT như trong mô hình opaque. Nhưng nếu RS cũng xử lý JWT cục bộ, nó **phải kiểm chữ ký và claims phù hợp**. Không dùng việc “JWT trông như cấu trúc đúng” thay cả hai cơ chế.

Đặc biệt, một AS chỉ trả `active=true` nhưng không bảo đảm audience, token type hoặc issuer theo contract vẫn không đủ để RS cấp quyền.

## 26. DPoP/mTLS-bound tokens: introspection không thay proof-of-possession

Một token có thể được **sender-constrained**:

- **mTLS certificate-bound token** (RFC 8705) có thể dùng `cnf` chứa thumbprint certificate.
- **DPoP-bound access token** (RFC 9449) có thể dùng `cnf.jkt` ràng buộc với khóa của client.

Một introspection response có thể cung cấp thông tin ràng buộc nếu AS/profile hỗ trợ:

```json
{
  "active": true,
  "scope": "orders.read",
  "aud": "orders-api",
  "cnf": {
    "jkt": "PUBLIC_KEY_THUMBPRINT_PLACEHOLDER"
  }
}
```

**Có `cnf` không làm bearer token tự an toàn.** RS phải xác minh **DPoP proof cho từng HTTP request** hoặc TLS client certificate phù hợp theo profile, bao gồm method/URL, timestamp, replay nonce/jti khi áp dụng.

| Nếu RS chỉ kiểm... | Lỗ hổng |
|---|---|
| `active=true` | Chấp nhận token của caller không giữ khóa. |
| `cnf.jkt` tồn tại | Không xác minh DPoP proof tương ứng. |
| DPoP proof có chữ ký | Không kiểm `htu`, `htm`, thời gian, replay và binding token. |
| TLS HTTPS một chiều | Không chứng minh client giữ mTLS private key. |

**Caller authentication để sử dụng introspection endpoint** khác với **proof-of-possession của client gửi access token tới RS**. Không nhầm hai bộ credential.

## 27. Audit endpoint introspection mà không làm lộ token

Những sự kiện cần quan sát:

| Sự kiện | Dữ liệu phù hợp |
|---|---|
| `INTROSPECTION_REQUESTED` | Caller identity đã xác thực, issuer, trace ID, timestamp. |
| `INTROSPECTION_CALLER_AUTH_FAILED` | Client reference (khi có), method, reason category. |
| `INTROSPECTION_TOKEN_ACTIVE` | Token HMAC/reference, caller, audience và metadata class tối thiểu. |
| `INTROSPECTION_TOKEN_INACTIVE` | Caller, token reference an toàn, decision code không tiết lộ chi tiết cho client. |
| `INTROSPECTION_SCOPE_DENIED` | RS, requested operation, required/granted scope references. |
| `INTROSPECTION_AUDIENCE_DENIED` | Caller/RS, expected audience, policy version. |
| `INTROSPECTION_RATE_LIMITED` | Caller ID, quota window, counters. |
| `INTROSPECTION_TIMEOUT` | Endpoint ID, latency, retry/circuit state. |
| `GRANT_OR_TOKEN_REVOKED` | Grant/token reference, propagation outcome. |

**Không ghi raw `token`, client secret, Authorization Basic header, private-key client assertions, refresh token, ID token hoặc PII không cần thiết.**

Đừng đưa token vào:

- URL query, structured log fields, trace/span attributes.
- Metrics label cardinality lớn, exception messages, stack trace contexts.
- Cache keys hiển thị nguyên văn, distributed queue payload không mã hóa.
- Support tickets hoặc ảnh chụp màn hình troubleshooting.

Dùng trace IDs và HMAC(token) với khóa quản lý riêng khi cần tương quan. **HMAC reference không phải license để giữ token vĩnh viễn**; vẫn phải áp retention, access control và secret rotation.

## 28. Quy trình xử lý sự cố introspection credential bị lộ

Giả sử credential `orders-api-introspector` bị commit vào Git hoặc lộ trong observability logs.

**Không chỉ xóa một dòng log rồi coi là xong.**

1. **Giới hạn ngay quyền truy cập** secret bị lộ và đầu ra logs/backup.
2. **Thu hồi hoặc xoay** credential tại AS, đổi secret/certificate/key của RS theo plan không gây gián đoạn quá mức.
3. **Rà soát endpoint permissions:** caller có thể introspect những audience/token classes nào?
4. **Truy vấn audit** các introspection calls bất thường, tỷ lệ active=false/true, volume/timestamps/nguồn request.
5. **Đánh giá metadata/PII đã lộ**; một credential introspection có thể rò trạng thái token dù không phát token mới.
6. **Kiểm soát egress và rate limits**; giới hạn client IP/network khi phù hợp.
7. **Xem có token bearer/refresh token nào cũng lộ không**; nếu có, xử lý revoke và incident response theo grant.
8. **Tách credential từng resource server**, đặt privilege tối thiểu, sửa logging/supply-chain/secret policy.
9. **Kiểm tra cache/rollout** sau rotation và các RS instances còn dùng credential cũ.
10. **Review threat model, alerts và postmortem** không chứa raw credential.

Nếu kẻ tấn công chỉ có introspection credential mà không có token, **không khẳng định họ đã có quyền gọi API business**; nhưng vẫn có rủi ro enumeration và metadata leakage. Nếu họ có cả bearer tokens, mức độ ảnh hưởng lớn hơn.

## 29. Các sai lầm phổ biến

| Sai lầm | Rủi ro | Khắc phục |
|---|---|---|
| Endpoint công khai không cần caller auth. | Dò quét token/metadata. | Require caller authentication/authorization. |
| Ai biết token cũng được xem toàn bộ claims. | Token leakage thành profile leakage. | Caller-specific introspection policy và response minimization. |
| Dùng cùng secret introspection cho mọi RS. | Một breach ảnh hưởng toàn hệ thống. | Credential riêng, least privilege. |
| Sai caller credentials mà AS vẫn trả `active=false`. | Che giấu lỗi auth, khó phát hiện RS bị tấn công. | Tách endpoint auth error và token state response. |
| Token sai audience vẫn trả active=true cho mọi caller. | Token cross-resource exposure. | AS caller-specific policy; RS validate aud. |
| RS cho phép khi `active=true` mà không kiểm scope. | Leo thang quyền endpoint. | Scope exact match và business authorization. |
| RS không kiểm `aud`. | Nhận token dành cho API khác. | Expected audience validator. |
| Introspection trả claims của inactive token. | Information leakage. | Chỉ trả `active=false`. |
| RS dùng `token_type_hint` để chấp nhận refresh token. | Token type confusion. | Validate token purpose/profile. |
| AS trả thông tin email/PII không cần thiết. | Privacy leakage. | Filter claims per caller/resource. |
| Cho user chỉ định introspection endpoint. | SSRF và raw token exfiltration. | Pin issuer/endpoint, egress allowlist. |
| Follow HTTP redirect đến host attacker với token body. | Rò bearer token. | Hạn chế redirects, strict host validation. |
| Ghi raw token/Basic credentials vào logs. | Credential theft và replay. | Redaction, HMAC references, access control. |
| Cache `active=true` vượt `exp`. | Nhận token hết hạn. | Cap TTL theo expiry và policy. |
| Cache chung giữa issuers/RS callers. | Cross-tenant/cross-resource trust leak. | Partition key. |
| Timeout AS rồi permit. | Fail-open security hole. | Fail closed hoặc valid cache policy. |
| Retry mọi 401/403/429 vô hạn. | Credential abuse và DoS. | Phân loại lỗi, backoff/circuit policy. |
| DPoP cnf có nhưng không kiểm proof. | Sender-constrained token bị dùng như Bearer. | Proof validation tại RS. |
| Introspection 200 được xem là token active. | Nhận `active=false` vì chỉ nhìn HTTP code. | Kiểm boolean `active`. |
| AS token store lookup không giới hạn. | Database DoS. | Bounded input/index/rate limit. |
| Có `sub` service nhưng xử lý như user. | Impersonation và sai audit. | Principal type/client policy. |
| Đóng UI consent/logout được coi là token revoke tức thì. | Revocation latency bị bỏ qua. | Grant/token state và cache strategy. |

## 30. Ma trận kiểm thử bảo vệ introspection endpoint

Giả sử AS `https://id.example.test` hỗ trợ RFC 7662. Orders API là caller có credential riêng; chỉ được introspect access tokens dành cho `orders-api`. RS yêu cầu `orders.read` cho GET Orders và có tenant isolation.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| I01 | Orders RS có credential hợp lệ, token active đúng Orders audience. | AS trả active true với metadata được phép. |
| I02 | Không có caller authentication. | Endpoint từ chối (401/403 theo scheme). |
| I03 | Caller secret sai. | Endpoint từ chối; không giả làm token inactive. |
| I04 | Caller đã revoke/suspended. | Endpoint từ chối. |
| I05 | Caller Payments cố introspect token chỉ cho Orders. | AS không lộ metadata; active=false theo quyền token. |
| I06 | Caller lạ không có introspection privilege. | Từ chối endpoint. |
| I07 | Token không tồn tại. | `active=false`, không tiết lộ claims. |
| I08 | Token hết hạn. | `active=false`. |
| I09 | Token đã revoke. | `active=false` theo trạng thái AS. |
| I10 | Token grant bị revoke. | Introspection phản ánh inactivity theo policy. |
| I11 | `active=false` nhưng response chứa `sub`/email. | Security test phát hiện metadata leakage. |
| I12 | RS nhận HTTP 200 có `active=false`. | Từ chối request API. |
| I13 | Response có `active="true"` dạng string. | Reject malformed schema. |
| I14 | Response thiếu `active`. | Fail closed; alert schema error. |
| I15 | Response `active=true` nhưng thiếu `aud` theo contract. | RS từ chối. |
| I16 | Response audience Payments tại Orders. | RS từ chối token. |
| I17 | Response `scope=orders.read-all` nhưng route cần `orders.read`. | Không match substring; từ chối. |
| I18 | Response `scope=orders.read`, route cần `orders.approve`. | 403 insufficient_scope. |
| I19 | Token đúng scope/audience nhưng order tenant khác. | RS từ chối theo object policy. |
| I20 | `client_id` không thuộc allowlist endpoint nhạy cảm. | RS từ chối theo policy. |
| I21 | Refresh token được gửi vào Orders API. | RS từ chối token sai mục đích dù AS có thể biết token. |
| I22 | ID token OIDC được gửi thay access token. | RS từ chối token purpose/audience. |
| I23 | `token_type_hint=access_token` nhưng token thật khác loại. | Không dựa vào hint để bypass. |
| I24 | Multipart/GET introspection request thay POST form khi không được hỗ trợ. | AS từ chối request không hợp đồng. |
| I25 | Token chứa ký tự `+` và `&`. | Form encoding đúng, lookup đúng giá trị. |
| I26 | Request oversized token hàng MB. | AS giới hạn size và tài nguyên. |
| I27 | Caller gửi hàng nghìn token giả. | Quota/rate limiting, không token scanning vô hạn. |
| I28 | Nhiều RS nodes cùng NAT egress. | Rate limit theo caller identity không khóa nhầm fleet. |
| I29 | AS trả claims PII dư thừa cho RS không cần. | Response-minimization test thất bại. |
| I30 | Caller đổi header xưng danh RS khác. | AS dựa trên identity đã xác thực, không header tùy ý. |
| I31 | mTLS proxy nhận fake certificate header từ Internet. | Gateway xóa header, reject giả mạo. |
| I32 | RSA/private_key_jwt client assertion sai `aud`/chữ ký/hạn. | Từ chối caller authentication. |
| I33 | User cung cấp URL issuer/introspection tùy ý. | RS không gửi token ra URL đó; SSRF blocked. |
| I34 | AS trả HTTP redirect cross-origin. | RS không follow kèm token body/credentials. |
| I35 | TLS hostname/cert sai. | RS từ chối kết nối. |
| I36 | AS timeout, không có valid cache. | RS fail closed, không permit. |
| I37 | AS 401 vì RS credential hết hạn. | RS không phân loại là `active=false`; alert auth/config. |
| I38 | AS 5xx, hàng nghìn concurrent requests. | Circuit breaker/backoff/bulkhead; không retry storm. |
| I39 | 100 requests đồng thời cho cùng token. | Coalescing/cache theo policy, không bỏ validation. |
| I40 | Cache positive lâu hơn token `exp`. | Test phát hiện; cap TTL theo token lifetime. |
| I41 | Revoke token ở T=15, cache active còn tới T=60. | Kiểm revocation latency phù hợp policy. |
| I42 | Cache dùng chung giữa Orders/Payments callers. | Test phát hiện cross-resource contamination. |
| I43 | Cache dùng chung giữa hai issuers. | Partition theo trust domain, không cross-use. |
| I44 | Negative cache lưu lỗi caller 401 như token inactive. | Test fail; không nhầm outage/auth với token state. |
| I45 | DPoP-bound token thiếu proof khi gọi API. | RS từ chối dù introspection active. |
| I46 | mTLS-bound token có cert không khớp. | RS từ chối. |
| I47 | ID token từ OIDC có `aud` client RP gửi vào API. | RS từ chối, không coi introspection as universal auth. |
| I48 | Spring opaque token client config đúng nhưng thiếu audience wrapper. | Integration test phát hiện. |
| I49 | RS route mới không có policy. | Default deny. |
| I50 | Logs/traces chứa raw token hoặc caller credentials. | Redaction/security test báo lỗi. |
| I51 | AS quản lý grant cho hai tenants, caller tenant A tra token B. | Active=false hoặc từ chối theo policy không lộ metadata. |
| I52 | User revoke consent nhưng refresh family vẫn cấp tokens. | Grant/revocation integration test phát hiện. |
| I53 | Token type/class bị map sang user principal sai. | Authorization test từ chối hoặc dùng service policy đúng. |
| I54 | AS trả invalid/malformed JSON hoặc quá lớn. | RS xử lý lỗi schema, fail closed, không unbounded memory. |

### Test theo lớp

- **Unit tests:** boolean `active`, scope parsing exact, audience string/array, metadata missing, TTL/cache key, error classification.
- **AS integration tests:** caller client authentication (secret/private_key_jwt/mTLS), per-token authorization, inactive response privacy, revocation và rate limits.
- **RS integration tests:** opaque token với introspection stub ký/cấu hình đáng tin, issuer/audience/scope/owner/tenant, 401/403.
- **Security tests:** SSRF, redirect exfiltration, TLS/mTLS termination, token scanning, credential leakage và claim minimization.
- **Resilience tests:** AS timeout/5xx/401, circuit breakers, coalescing, cache revocation latency, race giữa revoke/requests.
- **Sender constraint tests:** DPoP proof, mTLS certificate matching, replay/nondisclosure theo profile.

Spring Security Test `jwt()` hoặc mock principal có thể kiểm endpoint matcher nhưng **không chứng minh RS đã thực sự gọi introspection với credential đúng hoặc AS bảo vệ endpoint đúng**. Muốn bảo đảm end-to-end, cần integration tests với AS và token lifecycle thật.

## 31. Bài tập tình huống

### Tình huống A — endpoint trả active=true cho mọi resource server

Payments API được cấp credential introspection. Nó có thể gửi bất kỳ access token nào đến AS, kể cả token chỉ dành cho Orders; AS luôn trả `active=true` kèm `sub`, `scope`.

**Vấn đề:** Payments nhìn thấy metadata token không thuộc quyền mình; nếu RS bỏ audience validation còn có thể nhận nhầm token. **Khắc phục:** AS áp caller-specific introspection authorization và metadata filtering; RS kiểm audience độc lập.

### Tình huống B — lỗi xác thực caller bị ghi như token inactive

Orders API vừa rotate introspection secret nhưng một node còn dùng secret cũ. AS trả 401. Ứng dụng biến mọi non-200 response thành `active=false` và trả `401 invalid_token` cho toàn bộ người dùng.

**Vấn đề:** Nhiều token hợp lệ bị báo là invalid; cảnh báo credential/config bị che giấu. **Khắc phục:** phân loại AS caller authentication failure riêng, fail closed nhưng phản ánh outage/config, không làm negative token cache.

### Tình huống C — revoked token nhưng cache positive 5 phút

User revoke refresh/access grant. Orders RS có introspection cache `active=true` còn 4 phút.

**Vấn đề:** Một bearer token bị lộ có thể được chấp nhận đến khi cache hết hạn. **Khắc phục:** thiết kế revocation latency budget, cap cache TTL, invalidation/denylist cho tác vụ nhạy cảm.

### Tình huống D — opaque token gửi nhầm nơi

Một endpoint user-provided `issuer` được RS dùng để xây introspection URL. Attacker gửi `https://attacker.example.test/introspect`. RS POST raw access token đến host đó.

**Vấn đề:** SSRF dẫn tới **token exfiltration**. **Khắc phục:** pin issuer/URL theo cấu hình đáng tin, restrict redirects/egress và không lấy endpoint từ request chưa xác minh.

### Tình huống E — `active=true` nhưng thiếu audience

AS chỉ trả `active=true`, `sub`, `scope` cho mọi token. Orders API được cấu hình yêu cầu `aud=orders-api` nhưng vẫn cho qua khi claim `aud` thiếu.

**Vấn đề:** Không chứng minh token dành cho Orders. **Khắc phục:** yêu cầu AS trả metadata audience hoặc có ràng buộc tương đương đáng tin; thiếu thông tin phải fail closed.

### Tình huống F — DPoP-bound token chỉ introspect

AS trả `active=true` cùng `cnf.jkt`. Orders API không kiểm DPoP proof của request mà chấp nhận token như Bearer.

**Vấn đề:** Token bị sao chép có thể bị dùng bởi người không giữ private key. **Khắc phục:** xác minh DPoP proof/token binding trên từng request theo RFC 9449.

### Tình huống G — token chưa active, attacker muốn biết của ai

Attacker có thể gọi introspection với token hết hạn và nhận `active=false, sub=user-123, reason=revoked`.

**Vấn đề:** Metadata leak dù token không active. **Khắc phục:** chỉ trả `active=false`; không tiết lộ claims/lý do của token inactive và bắt buộc caller authorization.

### Tình huống H — một secret cho cả hai API

Orders và Payments cùng dùng một secret introspection. Secret của Orders bị lộ, attacker truy vấn token Payments.

**Vấn đề:** Blast radius xuyên resource. **Khắc phục:** danh tính/credential riêng cho từng RS, AS caller-specific token authorization và audit/rate limits.

### Tự đánh giá

1. Introspection token trong form body khác credential của caller như thế nào?
2. Tại sao RFC 7662 cần bảo vệ quyền truy cập endpoint, không chỉ dùng TLS?
3. Khi nào AS trả `active=false` thay vì lỗi xác thực caller?
4. Vì sao không trả `sub`, `client_id` và lý do revoke của inactive token?
5. `token_type_hint` có chứng minh token là access token không?
6. RS phải kiểm những thuộc tính nào sau khi thấy `active=true`?
7. Tại sao scope và audience vẫn cần validate trong mô hình opaque token?
8. Một RS đã bị xâm nhập credential introspection có thể gây những rủi ro gì?
9. JWT local validation và opaque introspection khác nhau về revocation latency thế nào?
10. Cache TTL cần bị giới hạn bởi expiry và chính sách revoke ra sao?
11. Vì sao cache key phải tách theo caller, issuer và resource?
12. Khi AS outage, vì sao không được “tạm cho qua” mọi token?
13. CORS, mTLS, DNS và redirect policy có giúp chặn SSRF/token exfiltration thế nào?
14. Introspection `cnf.jkt` có tự thay DPoP proof validation không?
15. Vì sao logs không được chứa raw token dù chỉ để debug?
16. Những integration tests nào chứng minh caller authentication, inactive response privacy và audience enforcement thật?

## 32. Ghi nhớ

- **RFC 7662 introspection là một protected endpoint**, không phải dịch vụ public xác minh token cho bất kỳ ai cầm token.
- **Phân biệt token được kiểm với credential của caller**; AS phải xác thực/phân quyền chính RS/client gọi introspection.
- **Authorization ở AS phải có tính resource-specific**, giảm token scanning và metadata leakage. Caller không được tự chọn token nào cũng xem được.
- **`active=false` chỉ là kết luận không thể dùng token**, không phải thông báo chính xác token sai ở đâu; không lộ claims của token inactive.
- **`active=true` không có nghĩa API được phép**. RS cần issuer, token type, audience, scope, time, client/principal, tenant/owner và policy.
- **`token_type_hint` chỉ là gợi ý**, không phải chứng minh access-token type.
- **TLS, endpoint pinning, credential isolation, mTLS/private_key_jwt khi phù hợp, rate limit và audit** bảo vệ kênh introspection.
- **Đừng để request untrusted chọn introspection URL**: SSRF có thể trực tiếp làm lộ raw access token.
- **Cache introspection cần trade-off minh bạch giữa latency và revoke**; không dùng cache vượt `exp` hoặc chia sẻ giữa trust domains.
- **AS outage không được dẫn đến fail-open**; phân biệt 401 caller credential, inactive token, 5xx/timeout và malformed response.
- **Opaque token cần metadata tin cậy từ AS**, còn JWT có thể local-validate; cả hai vẫn cần scope/audience/owner authorization.
- **Sender-constrained access tokens cần kiểm proof tại RS**, có `cnf` trong response không tự ngăn token replay.
- **Bảo vệ logs và credential introspection** là một phần của vòng đời token, không phải chi tiết vận hành phụ.

### Tài liệu chuẩn tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): endpoint, `active`, protected resource authentication, metadata, security và caching.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, access/refresh tokens, scope và client authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bảo vệ truyền access token và lỗi `invalid_token`/`insufficient_scope`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token và giới hạn propagation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `introspection_endpoint` và metadata authentication methods.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, token type, scope và JWT security.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token leakage, refresh security, policy và sender constraints.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh token confusion, thuật toán và validation.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): client authentication và sender-constrained access tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt ID token dành cho RP với access token dành cho resource API.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection integration, authorization, scope mapping.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization server endpoint security/configuration.
