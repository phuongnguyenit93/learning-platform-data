# Revocation propagation

## 1. Thu hồi token chưa đủ nếu quyết định thu hồi không đến được nơi kiểm tra

Trong chương **Revocation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này đi sâu vào **revocation propagation**: cách truyền và thực thi trạng thái thu hồi từ Authorization Server (AS), hệ thống quản lý session/grant đến mọi Resource Server (RS), gateway, cache và dịch vụ downstream đang có thể chấp nhận credential.

Một thao tác **revoke thành công tại AS** chưa đồng nghĩa **tất cả API lập tức từ chối mọi bản sao access token đang lưu hành**. Điều đó phụ thuộc:

- Token là **opaque** hay **JWT tự xác minh**.
- RS gọi **introspection** ở mỗi request hay dùng **positive cache**.
- Có **denylist, grant version, session status, policy lookup** hoặc kênh sự kiện thu hồi không.
- AS, RS và cache trải trên **bao nhiêu node/region**, có mất kết nối, retry hoặc độ trễ lan truyền không.
- Token đã bị thu hồi là **refresh token, access token, toàn grant, phiên đăng nhập, client credential** hay khóa ký.
- Ranh giới bảo mật cần **thu hồi gần thời gian thực** hay chấp nhận token tự hết hạn trong một cửa sổ rủi ro đã phê duyệt.

### 1.1. Một tình huống rất thực tế

Alice kết nối ứng dụng **Shop Web** với **Orders API**. AS cấp JWT access token sống 15 phút và refresh token sống lâu hơn.

~~~text
10:00  AS cấp access token T1, exp=10:15.
10:03  Alice báo mất thiết bị, đội hỗ trợ thu hồi grant/refresh token.
10:03  AS lưu grant=REVOKED.
10:04  API Gateway và Orders API vẫn kiểm chữ ký JWT T1 offline.
10:05  Một bản sao T1 bị đánh cắp tiếp tục được dùng.
10:15  T1 tự hết hạn.
~~~

Nếu RS chỉ kiểm `iss`, `aud`, chữ ký và `exp`, JWT T1 vẫn có thể được chấp nhận trong khoảng từ **10:03 đến 10:15**. Bản ghi `grant=REVOKED` tại database AS **không tự biến thành một claim mới** trong JWT đã phát hành.

**Mấu chốt của revocation propagation:** phải có cơ chế để **nơi ra quyết định xác thực/ủy quyền tại request-time biết và cưỡng chế trạng thái thu hồi**, hoặc chủ động chấp nhận độ trễ tới khi token hết hạn.

### 1.2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **revocation request accepted**, **revocation state committed**, **propagation delivered**, và **resource access blocked**.
2. Giải thích vì sao thu hồi refresh token **không tự hủy** access token JWT đã phát hành.
3. So sánh **introspection, short-lived JWT, denylist, token/grant version, event-driven invalidation** và các mô hình hybrid.
4. Thiết kế propagation qua nhiều node/region với **cache TTL, outbox, idempotency, ordering, retry, replay và audit**.
5. Định nghĩa **propagation window, freshness SLO, fail-open/fail-closed**, và rủi ro khi kết nối AS/RS bị gián đoạn.
6. Xử lý **refresh rotation/reuse, device logout, user deactivation, quyền tenant bị thu hồi, key compromise** mà không đánh đồng các cơ chế.
7. Thiết kế Java/Spring Security resource-server checks và pseudocode state/event processing.
8. Kiểm thử rằng token bị thu hồi thực sự bị từ chối tại **mọi API có thể nhận token**, không chỉ ở AS.

## 2. Định nghĩa chính xác: thu hồi cái gì và ai phải biết?

### 2.1. Revocation là một trạng thái, propagation là một chuỗi phân phối và cưỡng chế

| Thuật ngữ | Ý nghĩa | Điều nó **không** bảo đảm |
|---|---|---|
| **Revocation request** | Client/user/admin yêu cầu vô hiệu hóa token/grant | Chưa chứng minh mọi API đã cập nhật |
| **Revocation committed** | AS/token store lưu quyết định thu hồi có hiệu lực | Không tự cập nhật cache ở các vùng |
| **Event published** | Hệ thống đưa sự kiện ra broker/outbox | Chưa chắc consumer xử lý xong |
| **Event delivered** | Consumer nhận sự kiện | Chưa chắc state/cache đã được cập nhật bền vững |
| **Revocation enforced** | RS từ chối credential chịu tác động tại request time | Không thể hoàn tác dữ liệu đã truy cập trước đó |
| **Revocation convergence** | Các thành phần liên quan đã phản ánh trạng thái mới | Có thể mất thời gian hoặc phụ thuộc connectivity |
| **Token expiry** | Token tới `exp` và không còn hợp lệ theo thời gian | Không đồng nghĩa đã thu hồi trước hạn |

**Không dùng `HTTP 200` từ endpoint revoke làm bằng chứng toàn hệ thống đã hội tụ.** Nếu cần cam kết thời gian chặn, phải đo ở các enforcement points thực tế.

### 2.2. Các cấp độ phạm vi thu hồi

| Đối tượng | Ví dụ | Thường cần tác động tới |
|---|---|---|
| **Một access token** | T1 bị lộ | RS chấp nhận T1, introspection/denylist/state |
| **Một refresh token** | R1 bị lộ | AS token endpoint, refresh rotation/family |
| **Token family / authorization grant** | Toàn phiên ủy quyền Shop Web | Refresh tokens và access tokens liên quan nếu kiến trúc hỗ trợ |
| **Một session đăng nhập** | Alice bấm logout trên browser | OP/RP sessions; token có thể cần bước revoke riêng |
| **Một thiết bị/client session** | Mất điện thoại Shop Mobile | Grant/session gắn với thiết bị đó, tránh ảnh hưởng thiết bị khác |
| **Một user toàn bộ sessions** | Account bị vô hiệu | Mọi grants/sessions phù hợp policy, RS trạng thái subject |
| **Một client registration** | Ứng dụng bị phát hiện độc hại | AS từ chối cấp token mới; RS có thể cần chặn tokens đã cấp |
| **Một khóa ký** | Private signing key bị lộ | Các verifier chấp nhận `kid`/key đó, phạm vi lớn và rủi ro outage |
| **Role/tenant membership** | Alice rời phòng ban A | Business authorization tại RS; không phải lúc nào cũng cần revoke mọi token |

Không đồng nhất **logout browser**, **OAuth revocation**, **role removal** và **client de-registration**. Các hành động có điểm phát sinh, định danh và tác động khác nhau.

### 2.3. Bốn ranh giới tin cậy cần đi qua

~~~text
User / Admin / Security Operation
               |
               v
  AS / Authorization Grant Store
      (ghi trạng thái REVOKED)
               |
         propagation path
               |
      +--------+---------+
      |                  |
      v                  v
Token Endpoint     Event / Introspection
 (refresh)          / Revalidation
                         |
             +-----------+----------+
             |                      |
             v                      v
        API Gateway            Resource Servers
         (PEP A)                (PEP B, C, ...)
             |                      |
             +-----> Business authorization
                       (user/action/resource/tenant)
~~~

AS thường có thể chặn **refresh** nhanh vì refresh token quay về token endpoint; điều khó hơn là chặn **access token đang được RS xác minh offline**. Gateway đã từ chối token cũng chưa đủ nếu có một đường nội bộ gọi thẳng RS bypass gateway.

## 3. RFC 7009: endpoint thu hồi là điểm bắt đầu, không phải hệ thống phân tán

**RFC 7009 — OAuth 2.0 Token Revocation** định nghĩa endpoint để client yêu cầu AS vô hiệu hóa một token, thường là refresh token và cũng có thể là access token khi AS hỗ trợ.

### 3.1. Yêu cầu HTTP

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_AUTHENTICATION>

token=<URL_ENCODED_TOKEN>&token_type_hint=refresh_token
~~~

Trong thực tế:

- Dùng **HTTPS** và form encoding đúng.
- Confidential client xác thực theo phương thức đã đăng ký; không coi `client_id` công khai là secret.
- `token_type_hint` **chỉ là hint** (ví dụ `refresh_token`, `access_token`), không phải bằng chứng token thuộc client hay được phép thu hồi.
- AS phải kiểm tra client binding và chính sách liên quan, tránh cho một client trái phép thu hồi credential của client khác.
- Không đưa raw token vào URL query, logs, telemetry hoặc error messages.

### 3.2. Phản hồi thành công không tiết lộ token có tồn tại không

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

Theo RFC 7009, server trả **HTTP 200** cho yêu cầu revoke thành công, **kể cả khi token được gửi là không hợp lệ** (với những điều kiện yêu cầu được xử lý hợp lệ), nhằm tránh biến endpoint thành công cụ dò xem một token có đang tồn tại hay không.

Vì vậy, không diễn giải:

~~~text
POST /revoke -> 200
=> "Tất cả RS đã từ chối T1"  (SAI)
~~~

mà cần hiểu:

~~~text
POST /revoke -> 200
=> "AS đã tiếp nhận/xử lý revocation theo contract"
=> Kiểm tra riêng trạng thái RS nếu có propagation SLO.
~~~

Nếu AS không hỗ trợ thu hồi loại token đó, hoặc gặp lỗi server, phải dùng error semantics theo giao thức; không giả định mọi token có thể thu hồi tức thì. RFC 7009 cũng cho phép lỗi `unsupported_token_type` trong trường hợp phù hợp.

### 3.3. Revocation có thể ảnh hưởng các token cùng grant

Tác động của thu hồi lên **token khác cùng authorization grant** phụ thuộc loại token và khả năng AS:

- Thu hồi **refresh token** làm mất khả năng dùng refresh token đó để xin access token mới, và AS có thể/được khuyến nghị vô hiệu hóa access tokens từ cùng grant nếu hỗ trợ.
- Thu hồi **access token** không nhất thiết hủy refresh token gắn với cùng grant; chính sách có thể khác.
- Thu hồi **grant/token family** là thao tác cấp cao hơn, đòi hỏi liên kết các token được phát hành với grant.
- Thu hồi token do AS thực hiện **không tự tạo tín hiệu cho RS** nếu RS không có lookup/state/propagation path.

Không khẳng định chỉ cần gọi `/revoke` với refresh token là **mọi JWT access token đã phát hành tự mất hiệu lực**.

### 3.4. Revoke request và logout cần các API/cơ chế khác nhau

**OIDC logout** có thể kết thúc phiên OP/RP bằng các cơ chế theo profile (ví dụ Back-Channel Logout), còn OAuth token revocation vô hiệu hóa token/grant. Một ứng dụng nên định nghĩa rõ việc logout sẽ:

1. Xóa session/cookie tại client hoặc BFF.
2. Thu hồi refresh token/grant nếu policy yêu cầu.
3. Gửi tín hiệu logout tới các RPs khi hệ thống áp dụng OIDC logout.
4. Chặn token đã phát hành tại RS khi yêu cầu bảo mật cần hiệu lực gần tức thì.

Không nhầm “đăng xuất UI” với “tất cả access tokens bị vô hiệu trên mọi API”.

## 4. Vì sao JWT access token khó bị thu hồi tức thì?

JWT là một định dạng token có thể chứa claims và chữ ký. Một RS kiểm JWT offline thường chỉ có:

~~~text
header: alg, kid, typ...
payload: iss, sub, aud, exp, nbf, scope, jti...
signature: do issuer ký
~~~

Nếu AS không đổi chữ ký hay payload của T1 sau phát hành, RS xác minh nó vẫn:

~~~text
Signature valid?  YES
Issuer trusted?   YES
Audience correct? YES
Not expired?      YES
Scope present?    YES
~~~

Mọi kiểm tra này có thể **đúng** sau khi grant tại AS đã bị thu hồi.

### 4.1. Thời hạn JWT là giới hạn trên tự nhiên khi không kiểm trạng thái

Trong thiết kế **chỉ xác minh offline**, thời điểm tự ngừng chấp nhận token thường dựa vào `exp` (kèm clock leeway theo validator), không phụ thuộc hành động thu hồi ở AS:

~~~text
T0               T_revoke                        T_exp
|--------------------|-----------------------------|
   Token hợp lệ         Có thể vẫn được RS chấp nhận
                       nếu không có trạng thái revoke
~~~

**JWT ngắn hạn giúp giới hạn cửa sổ rủi ro, không thực hiện thu hồi tức thì.** Nếu TTL 5 phút, một token vừa cấp có thể còn được dùng gần 5 phút (cộng leeway cấu hình phù hợp). Không nói “TTL 5 phút thì revoke dưới 5 giây”.

### 4.2. Chữ ký hợp lệ không phải business authorization hiện tại

Ngay cả khi token không bị revoke, thay đổi role, tenant membership hoặc quyền trên record phải được xem xét tại **resource server**. Một access token có `scope=orders:read` không cho Alice đọc đơn hàng của Bob nếu policy không cho phép.

Vì vậy có **hai quyết định độc lập**:

1. Credential này còn được chấp nhận (chữ ký, thời hạn, audience, trạng thái revoke)?
2. Principal có được phép action này trên resource/context hiện tại?

Propagation revocation không thay object-level authorization và ngược lại.

## 5. Những kiến trúc truyền trạng thái thu hồi phổ biến

Có nhiều lựa chọn, không có một cơ chế phù hợp mọi hệ thống. Chúng khác nhau về **latency, availability, chi phí truy vấn và phạm vi token có thể bị chặn**.

| Kiến trúc | Cách RS biết đã revoke | Độ trễ thường do | Lợi ích | Rủi ro chính |
|---|---|---|---|---|
| **Short-lived JWT + expiry** | Không có event; đợi `exp` | TTL và clock leeway | Offline nhanh, ít phụ thuộc AS | Không revoke ngay được |
| **Opaque token + introspection mỗi request** | AS/introspection trả `active=false` | Đồng bộ trạng thái AS, mạng | Có thể chặn nhanh khi store nhất quán | Availability và latency phụ thuộc introspection |
| **Introspection + positive cache** | Cache hết hạn hoặc bị invalidate | Cache TTL, stale reads | Giảm tải và latency | Cửa sổ chấp nhận token đã bị thu hồi |
| **JWT + denylist `jti`** | RS tra denylist đã cập nhật | Propagation và cache lookup | Chặn token cụ thể trước `exp` | Storage, lookup cost, consistency |
| **JWT + grant/session version** | RS tra trạng thái phiên/grant | Lookup/cache/event | Thu hồi theo grant, user, device | Cần stable grant ID và nhất quán version |
| **Event-driven invalidation** | AS phát event; RS xóa cache/cập nhật state | Broker, consumer lag, reconnect | Giảm gọi AS ở hot path | Mất event, out-of-order, multi-region |
| **Hybrid** | JWT offline + TTL ngắn + state check/event cho hành động nhạy cảm | Tùy đường thực thi | Cân bằng bảo mật/hiệu năng | Dễ có lỗ hổng nếu policy không thống nhất |

**Đừng coi “gửi event” là giải pháp hoàn chỉnh:** nếu một RS không được cấu hình lắng nghe, hoặc local cache không bị invalidated, token vẫn có thể được chấp nhận.

### 5.1. Chọn theo yêu cầu bảo mật thay vì xu hướng công nghệ

Ví dụ gợi ý, không phải bắt buộc:

- **Read-only dữ liệu ít nhạy cảm:** access token ngắn hạn, business authorization và TTL thích hợp có thể đáp ứng một cửa sổ rủi ro đã chấp thuận.
- **Thanh toán, duyệt giao dịch, dữ liệu quản trị:** cần kiểm trạng thái revoke/role gần thời gian thực tại RS hoặc PDP, kèm fail-closed có kiểm soát.
- **Nhiều API qua các region:** cần event propagation bền vững, introspection/state fallback và giám sát convergence.
- **BFF/backend giữ refresh token:** chặn refresh ngay tại AS, kết hợp chặn session và thiết kế cho access token đang lưu hành.
- **Đường request có SLA latency thấp:** cân nhắc cache trạng thái/epoch gần RS nhưng phải định nghĩa thời gian stale tối đa và xử lý outage.

Không nên tuyên bố “JWT stateless” và đồng thời hứa **instant revocation** mà không bổ sung một cơ chế stateful.

## 6. Opaque token và introspection: trạng thái tập trung nhưng cache vẫn có thể cũ

Với opaque access token, giá trị token thường là một chuỗi khó đoán; RS không tự giải mã claims như JWT. RS có thể hỏi **introspection endpoint** theo RFC 7662.

### 6.1. Introspection request/response

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <RESOURCE_SERVER_AUTHENTICATION>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

AS trả về metadata theo hợp đồng. Ví dụ token còn hiệu lực:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "client_id": "shop-web",
  "aud": "https://orders.example.com",
  "scope": "orders:read",
  "exp": 1893492900
}
~~~

Nếu token không hoạt động:

~~~json
{
  "active": false
}
~~~

Theo RFC 7662, introspection endpoint phải được bảo vệ, xác thực/ủy quyền resource servers phù hợp và hạn chế lộ token metadata cho bên không có quyền. `active=false` có thể bao phủ token không tồn tại, hết hạn hoặc đã thu hồi; không cần công bố nguyên nhân chi tiết.

### 6.2. `active=true` không phải quyết định ALLOW

Orders API vẫn phải kiểm:

~~~text
Introspection active=true
    AND issuer đúng
    AND audience là Orders API
    AND exp/nbf hợp lệ
    AND scope phù hợp
    AND subject/action/resource/tenant được policy cho phép
    => mới có thể ALLOW
~~~

Một bản introspection cho token của Billing API không được làm Orders API chấp nhận token. `active` chỉ cho biết trạng thái token theo contract AS, không tự thay quyền object.

### 6.3. Positive cache tạo một cửa sổ stale

Để giảm tải, RS có thể cache response `active=true`:

~~~text
12:00:00  RS introspect T1 -> active=true.
12:00:01  RS cache T1 active=true trong 60 giây.
12:00:05  AS revoke T1 thành công.
12:00:20  RS vẫn có cache active=true.
12:01:01  Cache hết hạn; RS introspect lại -> active=false.
~~~

Với cache TTL 60 giây, **thời gian RS còn chấp nhận sau revoke có thể gần TTL còn lại**, cộng độ trễ đồng bộ store/network và sai lệch thiết kế. Nếu có cơ chế event invalidation đáng tin, cửa sổ có thể ngắn hơn; nếu RS giữ stale cache khi AS outage, có thể dài hơn.

Không gọi introspection “online revocation ngay lập tức” khi đã bật caching mà không nói rõ TTL/invalidation.

### 6.4. Cache key và TTL phải đúng

Các nguyên tắc:

- Cache key phải gắn với **token thực tế** và **issuer/tenant context** phù hợp; tránh collision giữa hai issuer có token string trùng.
- Không lưu raw access token trong cache key quan sát được hoặc log metrics. Có thể dùng **HMAC có khóa** trên token và issuer làm key lookup; HMAC key cần được bảo vệ.
- Positive TTL phải **không vượt quá thời gian token còn hợp lệ** theo `exp` và chính sách freshness.
- Với dữ liệu chưa có expiry đáng tin, phải đặt TTL ngắn có chủ đích; đừng cache vô hạn.
- Negative cache có thể giảm dò token nhưng cũng phải có giới hạn tránh DoS, đồng thời phân biệt token `inactive` với lỗi introspection server.
- Xử lý clock leeway nhất quán giữa AS và RS, không “gia hạn” token chỉ vì cache còn sống.

**Không cache một HTTP 503 hoặc timeout thành `active=true`**; đây là lỗi fail-open rất nguy hiểm. Đồng thời không nhất thiết biến mọi lỗi mạng thành `active=false` trong audit, vì cần phân biệt **credential bị thu hồi** với **không thể xác minh trạng thái**.

### 6.5. Consistency của introspection store

Giả sử AS ghi grant REVOKED vào primary database, nhưng introspection node đọc một replica chậm:

~~~text
Primary: grant=REVOKED
Replica: grant=ACTIVE (replication lag)

RS -> Introspection qua replica -> active=true
~~~

Ngay cả gọi introspection **mỗi request** cũng không bảo đảm thu hồi tức thì nếu nguồn trạng thái trả về còn stale. Đối với revoke cần SLA chặt, cân nhắc đọc consistency cao, đồng bộ trạng thái theo version hoặc định tuyến tới nguồn dữ liệu có guarantee phù hợp.

## 7. JWT + denylist: chặn một token cụ thể

Một cách cho JWT stateless được chặn trước hạn là bổ sung **denylist** (revocation list). Khi phát token, AS cấp identifier `jti` khó trùng:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "scope": "orders:read",
  "jti": "at-7Qm4Jv",
  "iat": 1893492000,
  "exp": 1893492900
}
~~~

RS sau khi xác minh JWT kiểm thêm:

~~~text
verifySignatureIssuerAudienceTime(jwt)
    AND NOT denylist.contains(issuer, jti)
    AND resourcePolicyAllows(action, resource, subject)
~~~

### 7.1. Những điều kiện bắt buộc của denylist

1. `jti` phải có ngữ nghĩa duy nhất phù hợp, thường **duy nhất trong issuer**; đừng coi `jti=123` trùng ở mọi issuer là cùng token.
2. Denylist phải có **thời điểm hết hiệu lực** gắn với expiry của token, tránh tích lũy vô hạn.
3. RS phải tra denylist trước khi ALLOW, bao gồm mọi deployment/region có thể nhận token.
4. Trạng thái denylist/cache phải lan truyền với SLA được đo.
5. Nếu JWT không có `jti`, không thể coi một giá trị thiếu là khóa chung để revoke mọi token; cần token hash/HMAC hoặc chiến lược khác đã thiết kế.
6. Giám sát false negatives và trạng thái dịch vụ denylist khi mạng lỗi.

### 7.2. Mô hình lưu trữ

~~~sql
-- Schema minh họa; không phải schema chuẩn OAuth.
CREATE TABLE revoked_access_tokens (
    issuer_id VARCHAR(256) NOT NULL,
    token_id VARCHAR(256) NOT NULL,
    revoked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    reason_code VARCHAR(64),
    PRIMARY KEY (issuer_id, token_id)
);
~~~

Một entry cần được giữ **ít nhất tới khi token chắc chắn không thể được chấp nhận** theo validators và leeway. Cleanup phải xét đồng hồ/retention; không xóa denylist quá sớm làm T1 đột nhiên hoạt động trở lại.

### 7.3. Denylist không giải quyết được tất cả

- Mỗi access token phát hành có `jti` riêng. Thu hồi **cả grant/user** có thể đòi hỏi nhiều entries hoặc thêm grant/session-level control.
- Nếu RS cache `not revoked` quá lâu, vẫn có stale window.
- Nếu event bị mất, một số RS không có entry, dẫn đến policy không nhất quán.
- Lookup denylist có chi phí và có thể phụ thuộc availability; cần fail mode rõ.
- JWT được cấp với audience/scope quá rộng **vẫn sai** nếu không bị denylist; issuance và resource policy phải đúng ngay từ đầu.

## 8. Grant/session version: thu hồi nhiều token bằng một trạng thái

Thay vì lưu mọi `jti`, có thể liên kết access token với một **grant/session ID** và một **version/epoch** của trạng thái cấp quyền.

Ví dụ claim nội bộ minh họa, **không phải claim bắt buộc trong chuẩn JWT/OAuth**:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "scope": "orders:read",
  "grant_id": "g-947",
  "grant_ver": 4,
  "iat": 1893492000,
  "exp": 1893492900
}
~~~

Tại AS/policy store:

~~~text
grant g-947:
    status = ACTIVE
    current_version = 4

Khi revoke:
    status = REVOKED
    current_version = 5
~~~

RS chấp nhận chỉ khi:

~~~text
token.grant_id = g-947
AND currentGrant.status = ACTIVE
AND token.grant_ver = currentGrant.version
AND JWT issuer/audience/time/scope hợp lệ
AND resourcePolicyAllows(action, resource, subject)
~~~

### 8.1. Version và scope thu hồi

| Kiểu trạng thái | Công dụng | Lưu ý |
|---|---|---|
| **Token `jti`** | Vô hiệu một access token | Không thay thu hồi token family |
| **Grant version** | Vô hiệu tất cả token thuộc một authorization grant | Cần token gắn grant ID đáng tin |
| **Device/session version** | Vô hiệu credential của một thiết bị/session | Tránh ảnh hưởng sai thiết bị khác |
| **Subject security epoch** | Vô hiệu nhiều token của user sau thay đổi bảo mật lớn | Phạm vi rộng, cần mô hình client/grant rõ |
| **Client security epoch** | Chặn token phát cho một client đã bị vô hiệu | Có thể ảnh hưởng nhiều users; cần xử lý outage |
| **Tenant policy version** | Buộc re-evaluate khi quyền tenant thay đổi | Không thay quyết định object/action hiện tại |

Version phải **tăng đơn điệu** và có namespace (issuer + grant/client/tenant). Không sử dụng `iat` so với giờ revoke như cơ chế duy nhất khi clock skew và transaction ordering có thể không rõ; dùng monotonic version/sequence an toàn hơn.

### 8.2. Khi nào version vẫn bị stale?

Nếu RS cache `grant_ver=4, ACTIVE` trong 2 phút, việc AS đổi lên 5 **không ảnh hưởng đến cache đó ngay**. Grant version chỉ có tác dụng thu hồi sớm khi **RS biết current version mới**, qua lookup/invalidation/revalidation.

Versioning không làm hệ thống stateless; nó chỉ **nén phạm vi thu hồi** và đơn giản hóa so sánh nhiều token cùng grant.

## 9. Event-driven revocation propagation: truyền trạng thái, không chỉ gửi thông báo

Trong kiến trúc nhiều dịch vụ, AS có thể phát sự kiện **grant/token revoked** lên broker để API Gateway, Orders API, Billing API và cache invalidation workers nhận biết thay đổi.

~~~mermaid
sequenceDiagram
    actor U as Alice / Security Team
    participant AS as Authorization Server
    participant DB as Grant Store + Outbox
    participant P as Event Publisher
    participant B as Message Broker
    participant O as Orders API
    participant C as Checkout API
    participant S as Shared State
    U->>AS: Revoke grant g-947
    AS->>DB: Transaction: grant=REVOKED, version=5, outbox event
    DB-->>AS: COMMIT
    AS-->>U: Revocation accepted
    P->>DB: Read committed outbox events
    P->>B: Publish GrantRevoked(g-947, version=5)
    B-->>O: Deliver event
    B-->>C: Deliver event
    O->>O: Mark grant revoked / evict cache
    C->>C: Mark grant revoked / evict cache
    O->>S: Optional authoritative state recheck
    C->>S: Optional authoritative state recheck
    Note over O,C: Mỗi RS phải thực sự từ chối token chịu tác động
~~~

Sơ đồ trình bày **eventual convergence**, không khẳng định broker giao event tới mọi RS trước khi AS trả HTTP 200. Nếu yêu cầu **stronger acknowledgement**, kiến trúc cần một protocol/coordination riêng để xác minh enforcement ở các RS trước khi tuyên bố hoàn tất theo SLO.

### 9.1. Transactional outbox tránh mất sự kiện khi AS crash

Phương án dễ lỗi:

~~~text
1. AS UPDATE grant=REVOKED; COMMIT.
2. AS publish message.
3. Process crash giữa bước 1 và 2.
=> DB đã revoke, nhưng không có message.
~~~

Nếu RS chỉ biết revoke qua message, chúng có thể giữ `ACTIVE` tới hết cache/token TTL.

**Transactional outbox** lưu thay đổi grant và event trong **cùng transaction**:

~~~sql
BEGIN;

UPDATE authorization_grants
SET status = 'REVOKED',
    security_version = security_version + 1,
    revoked_at = CURRENT_TIMESTAMP
WHERE issuer_id = :issuer
  AND grant_id = :grant_id
  AND status = 'ACTIVE';

INSERT INTO security_outbox (
    event_id, issuer_id, aggregate_type, aggregate_id,
    event_type, version, created_at, delivery_status
) VALUES (
    :event_id, :issuer, 'GRANT', :grant_id,
    'GRANT_REVOKED', :new_version, CURRENT_TIMESTAMP, 'PENDING'
);

COMMIT;
~~~

SQL là **minh họa**: production phải đảm bảo UPDATE đúng grant, lấy `new_version` đã commit, tránh event thừa/thiếu khi điều kiện không khớp, dùng transaction và locking thích hợp. Publisher chỉ phát các outbox events đã commit, retry có kiểm soát tới khi broker xác nhận.

### 9.2. Event không nên mang bearer token thô

Ví dụ event schema **nội bộ, không phải chuẩn OAuth**:

~~~json
{
  "event_id": "evt-8j52",
  "event_type": "GRANT_REVOKED",
  "issuer_id": "login-prod",
  "grant_id": "g-947",
  "grant_version": 5,
  "occurred_at": "2030-01-01T10:03:00Z",
  "reason_code": "DEVICE_LOST",
  "affected_resource_set": [
    "orders-api",
    "checkout-api"
  ]
}
~~~

Event cần đủ thông tin để consumer xác định token/grant phải từ chối, nhưng không chứa:

~~~text
access_token
refresh_token
id_token
authorization_code
client_secret
private_key
raw user session cookie
~~~

Các trường `grant_id`, `issuer_id`, `subject_id`, reason và resource set vẫn có thể nhạy cảm: dùng broker ACL, encryption in transit/at rest, retention, schema validation và audit truy cập. Nếu event đi qua nhiều trust domains, cần **xác thực nguồn và bảo vệ tính toàn vẹn**; không tin bất kỳ producer nào có thể gửi `GRANT_REVOKED` hoặc `GRANT_ACTIVE` tùy ý.

### 9.3. Delivery semantics: at-least-once đòi idempotency

Broker thường có khả năng gửi lại event nếu consumer crash trước khi xác nhận. Consumer phải xử lý:

~~~text
GrantRevoked(g-947, version=5)
GrantRevoked(g-947, version=5)  <- duplicate
GrantRevoked(g-947, version=5)  <- replay sau reconnect
~~~

**Idempotent xử lý** nghĩa là lặp lại một event không làm sai trạng thái hoặc cấp lại quyền. Ví dụ consumer:

1. Xác minh event source/schema/issuer.
2. So version event với current version đã biết.
3. Nếu version mới hơn, chuyển local grant state sang REVOKED hoặc tăng security epoch.
4. Invalidate cache liên quan.
5. Ghi checkpoint/offset **sau khi** state/invalidation đã bền vững theo thiết kế.
6. Có cơ chế catch-up khi consumer offline.

Đừng `ack` event ngay khi nhận rồi mới xử lý nếu crash sau ack làm mất sự kiện mà không có cơ chế replay/reconciliation.

### 9.4. Out-of-order và sự kiện lỗi thời

Ví dụ:

~~~text
T0: Grant g-947 version 4 ACTIVE.
T1: Grant revoked => version 5 REVOKED.
T2: Một event "snapshot v4 ACTIVE" đến muộn.
~~~

Nếu consumer nhận snapshot v4 và ghi đè state v5, token cũ có thể được **tái chấp nhận**. Vì vậy:

- Dùng **monotonic version** hoặc sequence number theo aggregate/grant.
- Bỏ qua event version cũ hơn current; event cùng version xử lý idempotent.
- Không cho một event `ACTIVE` đến muộn ghi đè trạng thái `REVOKED`.
- Nếu có **re-authorization**, tạo grant mới hoặc version/generation mới rõ ràng, không tự “mở lại” grant bị revoke chỉ bởi trạng thái cũ.
- Nếu thiếu một version quan trọng, consumer nên fetch **authoritative state** hoặc kích hoạt reconciliation.

Trong distributed system, chỉ dựa vào timestamp để thứ tự hóa event giữa các node có clock skew là không an toàn bằng sequence/version do authoritative store quản lý.

### 9.5. Evict cache khác với lưu trạng thái revoke

Có hai kiểu event consumer:

**Invalidate-only:**

~~~text
On GRANT_REVOKED:
    evict positive introspection cache / JWT grant status cache.

Next request:
    query authoritative AS/state store -> REVOKED.
~~~

Nếu authoritative store còn stale hoặc unreachable, kết quả tùy fail policy.

**Local revocation state:**

~~~text
On GRANT_REVOKED:
    upsert local version/status=REVOKED.

Next request:
    compare token grant ID/version with local state.
~~~

Cách này giảm network calls nhưng phải bảo đảm consumer catch-up, durable snapshots và version freshness. Một cache chỉ nhận event mà **không kiểm tra đã kết nối đầy đủ từ lúc startup** có thể khởi động với state trống rồi chấp nhận token đã bị revoke từ trước.

### 9.6. Reconciliation chống mất event và khởi động lại

Một thiết kế bền vững cần:

- Snapshot current grant/security epochs từ authoritative store hoặc compacted event log.
- Checkpoint/offset bền vững cho consumer.
- Resume/catch-up sau mạng partition, service restart hoặc scale-out.
- Periodic reconciliation giữa local state với authoritative source.
- Cảnh báo nếu consumer lag quá giới hạn.
- Chính sách **readiness**: RS chưa biết trạng thái revoke tối thiểu thì không nhận request nhạy cảm hoặc phải fallback kiểm trạng thái.

Không giả định event bus có **exactly-once end-to-end** chỉ vì broker quảng cáo exactly-once delivery. Transaction giữa broker offset, local cache và business decision thường vẫn cần idempotency/version/reconciliation.

## 10. Cửa sổ thu hồi: đo propagation bằng các mốc thời gian

Muốn bảo vệ được một cam kết như “token bị vô hiệu trong vòng X giây”, hệ thống phải định nghĩa chính xác **mốc bắt đầu** và **mốc hoàn tất**.

### 10.1. Các mốc có thể quan sát

~~~text
t0  = user/admin gửi yêu cầu revoke
t1  = AS ghi trạng thái REVOKED và commit
t2  = outbox event được publish
t3  = RS nhận event hoặc cache bị invalidated
t4  = request đầu tiên tới RS bị từ chối vì revoke
t5  = mọi RS/region trong phạm vi xác nhận enforcement
~~~

Các đại lượng:

~~~text
Commit latency                = t1 - t0
Event publication lag         = t2 - t1
Consumer propagation lag      = t3 - t2
Observed enforcement lag      = t4 - t1
Convergence lag               = t5 - t1
~~~

**Lưu ý:** `t4` phụ thuộc có request kiểm thử ở thời điểm đó; không có request chưa chứng minh RS sẵn sàng từ chối. Để đo enforcement, có thể dùng synthetic probes an toàn hoặc kiểm state checkpoint với xác nhận có ý nghĩa, không dùng token production bị lộ.

### 10.2. SLO phải nói rõ phạm vi

Ví dụ SLO **minh họa**, không phải chuẩn bắt buộc:

> Sau khi AS commit thu hồi một grant nhạy cảm, 99,9% enforcement points thuộc phạm vi phải từ chối các access tokens chịu ảnh hưởng trong 10 giây; các trường hợp còn lại phải dùng fallback fail-closed hoặc được cảnh báo.

SLO tốt cần xác định:

- Loại token/grant nào được áp dụng?
- AS regions và RS deployments nào trong phạm vi?
- “Từ chối” đo bằng request thực tế hay checkpoint?
- Khi một region mất mạng, có fail-closed không?
- Độ trễ bao gồm AS store replication, broker, consumer, local cache hay không?
- Điều gì xảy ra khi một token tự hết hạn trước event tới nơi?

Nếu hệ thống chỉ dùng JWT offline đến `exp`, không thể hứa SLO 10 giây khi TTL 15 phút.

### 10.3. Cache TTL và propagation lag

Trong kiến trúc introspection **không có event invalidation**, cửa sổ stale tối đa theo thiết kế thường bị chi phối bởi:

~~~text
remaining_positive_cache_ttl
    + authoritative_store_visibility_delay
    + clock/network/operational_margin
~~~

Khi có event invalidation, cửa sổ thực tế còn phụ thuộc:

~~~text
AS_commit_lag
    + outbox_publish_lag
    + broker_delivery_lag
    + consumer_process_lag
    + local_cache_visibility_lag
~~~

Đây là **các thành phần độ trễ cần đo**, không phải công thức bound toán học áp dụng máy móc. Nếu hệ thống cho phép **serve stale on error**, token bị revoke có thể được chấp nhận lâu hơn mọi TTL dự kiến; cần một **hard upper bound** rõ trong policy, hoặc fail closed.

### 10.4. Token expiry vẫn là chặn cuối khi propagation lỗi

Nếu access token hết hạn sau 5 phút, expiry có thể giới hạn mức exposure khi event không tới được, miễn RS kiểm `exp` đúng và không cho stale/cache vượt expiry.

Nhưng với **refresh token còn hoạt động**, attacker có thể liên tục lấy access token mới. Vì thế cần bảo đảm thu hồi ở **AS token endpoint** và xử lý refresh-token rotation/reuse, không chỉ tập trung chặn JWT hiện hữu.

### 10.5. Đừng che độ trễ bằng chỉ số trung bình

Một hệ thống có average propagation 100 ms nhưng thỉnh thoảng một RS bị mất kết nối **20 phút** có thể không phù hợp dịch vụ thanh toán. Cần theo dõi:

- P50/P95/P99/P99.9 propagation lag và outliers.
- Max observed lag hoặc số RS đang vượt freshness budget.
- Consumer lag/last successful sync age theo region.
- Số request RS ALLOW sau `revoked_at` đối với token nằm trong phạm vi test.
- Thời điểm JWT expiry và cache TTL thực tế.

Đừng suy “broker khỏe” từ một dashboard aggregate mà bỏ qua consumer instance đang không nhận event.

## 11. Network partition, fail-closed và fail-open: quyết định theo rủi ro

Một RS ở region B có thể mất kết nối tới introspection endpoint, event broker hoặc state database. Phải xác định **API có còn được phép chấp nhận token khi không thể kiểm trạng thái revoke mới nhất không**.

### 11.1. Các lựa chọn khi không xác minh được trạng thái

| Chính sách | Hành vi | Phù hợp/không phù hợp |
|---|---|---|
| **Fail closed** | Từ chối request hoặc trả lỗi tạm thời khi không đủ bằng chứng token còn hợp lệ | Giao dịch tài chính, quản trị, dữ liệu nhạy cảm; ảnh hưởng availability |
| **Serve last-known state có hard TTL** | Dùng trạng thái cache đã xác minh gần đây đến một ngưỡng cố định, sau đó từ chối | Khi risk review chấp nhận cửa sổ stale rõ ràng |
| **Fail open** | Cho qua vì introspection/denylist không khả dụng | Có thể làm token bị thu hồi được sử dụng; không mặc định cho endpoint nhạy cảm |
| **Offline JWT đến `exp`** | Không kiểm trạng thái revoke ngoài chữ ký/thời hạn | Hợp lý nếu thiết kế chấp nhận cửa sổ đến expiry |
| **Fallback authoritative lookup** | RS hỏi kho trạng thái đáng tin khác hoặc local durable security snapshot | Tốt nếu consistency/availability của fallback thực sự được bảo đảm |

**Không có hành vi mặc định tối ưu cho mọi hệ thống**, nhưng phải chỉ ra rõ **security impact** của policy. Nếu chọn availability cao và cho phép stale, không hứa revocation tức thì.

### 11.2. Ví dụ mâu thuẫn bảo mật

~~~text
Region A:
    AS grant g-947 = REVOKED, version 5.

Region B:
    Không thấy event mới do broker partition.
    Local state = ACTIVE, version 4.

Request:
    T1.grant_ver = 4, còn hạn và chữ ký hợp lệ.
~~~

Nếu region B `ALLOW` chỉ vì local state có version 4, token đã revoke được chấp nhận. Để đáp ứng SLO chặt, RS cần:

1. Biết **last-sync age** của revocation state.
2. Biết freshness budget của API/action.
3. Nếu last-sync age vượt budget, chuyển sang **revalidation/fail-closed**.
4. Có hệ thống cảnh báo tình trạng vượt ngưỡng.

Không nên ẩn tình trạng partition bằng cache `ACTIVE` dài hạn và chỉ ghi một log debug.

### 11.3. Readiness và rollout của một RS mới

Khi deploy một Orders API instance mới:

~~~text
Node mới chưa load revocation snapshot.
Consumer event đã kết nối nhưng offset bắt đầu từ "latest".
Token T1 từng bị revoke trước lúc node khởi động.
~~~

Node mới sẽ **không bao giờ thấy event cũ** nếu chỉ subscribe từ thời điểm hiện tại. Cần một bước bootstrap:

- Load snapshot/compacted state hiện tại hoặc replay event đủ lịch sử.
- Xác định high-watermark/offset bảo đảm không có gap giữa snapshot và streaming.
- Chỉ đánh dấu **ready** khi state đủ mới theo policy.
- Nếu chưa ready, dùng authoritative introspection/state check hoặc từ chối action nhạy cảm.
- Định kỳ reconcile để phát hiện mất event/khác version.

Không dùng “cache rỗng” làm bằng chứng “không có token nào bị revoke”.

### 11.4. Multi-region và quyền ghi

Nếu AS có nhiều vùng đều nhận revoke requests, phải có quy tắc **single source of truth hoặc conflict resolution** cho security state.

Ví dụ hai region cùng thay grant:

~~~text
Region A: revoke g-947 => version 5 REVOKED.
Region B: một thao tác cũ muốn ghi g-947 ACTIVE version 4.
~~~

Hệ thống không được dùng **last write wins theo timestamp local** khiến lệnh ACTIVE cũ ghi đè REVOKED. Có thể dùng version từ store authoritative, quy tắc tombstone/monotonic revocation hoặc transaction consensus tùy kiến trúc.

Nếu cần cho phép user **ủy quyền lại**, hãy tạo authorization grant/generation mới sau quy trình hợp lệ, không tái hoạt hóa một grant bị revoke bằng một stale event.

### 11.5. Cân bằng availability và security phải công khai

Ví dụ ma trận:

| Endpoint | Trạng thái revoke quá cũ | Hành vi gợi ý |
|---|---|---|
| `GET /public/catalog` (không cần token) | Không liên quan | Có thể phục vụ public |
| `GET /orders/{id}` | Không xác minh được token/grant freshness | Theo policy dữ liệu; cân nhắc fail closed |
| `POST /payments/transfer` | Không bảo đảm token chưa bị revoke | **Fail closed** với response retryable thích hợp |
| `POST /admin/roles` | Không xác minh được security state | **Fail closed** |
| `GET /health` | Không chứa dữ liệu user | Có thể trả readiness degraded |

Lỗi khi không xác minh được trạng thái không nhất thiết là `invalid_token`: cần phân biệt **token đã bị chứng minh không hợp lệ** với **dịch vụ xác thực tạm không khả dụng**. HTTP 503 có thể phù hợp với outage; đừng tiết lộ internals nhạy cảm trong body.

## 12. Refresh token rotation, token family và replay detection

Refresh token là credential được đưa tới **AS token endpoint**, không nên được RS dùng để gọi API nghiệp vụ. Vì refresh có thể sống lâu hơn access token, thu hồi và chống replay cần được thiết kế nghiêm ngặt.

### 12.1. Rotation trong một family

~~~text
Grant g-947 / token family F1:

R1 ACTIVE
   |
   | refresh thành công
   v
R1 USED -----> R2 ACTIVE
                 |
                 | refresh thành công
                 v
              R2 USED -----> R3 ACTIVE
~~~

Trong cơ chế **refresh token rotation**, token mới thay thế token trước và token trước không còn hợp lệ để tiếp tục refresh. Với public clients được phát refresh token, RFC 9700 yêu cầu **refresh-token rotation hoặc sender-constrained refresh tokens** để giảm/phát hiện replay.

### 12.2. Reuse detection và revocation propagation

Tình huống:

~~~text
T0: Alice có R1.
T1: Attacker đánh cắp bản sao R1.
T2: Alice dùng R1 -> AS phát R2, đánh dấu R1 USED.
T3: Attacker dùng R1 cũ -> AS phát hiện reuse.
~~~

Theo chính sách bảo mật, AS có thể **thu hồi token family/grant** để ngăn tiếp tục cấp token mới. Từ đó cần:

1. Cập nhật family/grant state bền vững và nguyên tử.
2. Từ chối refresh tiếp theo từ những token chịu ảnh hưởng.
3. Phát event thu hồi và/hoặc cập nhật state được RS tra.
4. Chặn access tokens đã cấp nếu kiến trúc yêu cầu/supported, không chỉ chặn refresh.
5. Ghi audit và kích hoạt UX login lại/incident response theo risk policy.

**Không tự kết luận request reuse nào thuộc attacker:** cả client hợp lệ và attacker có thể có bản sao, và ai dùng trước không đủ phân biệt. Xử lý phải coi token family có khả năng bị xâm phạm.

### 12.3. Race giữa hai refresh requests

~~~text
Node A đọc R1 ACTIVE.
Node B đọc R1 ACTIVE.
Node A phát R2.
Node B phát R3.
~~~

Nếu không có atomic transition, cả hai request có thể thành công, tạo nhiều nhánh active trong family. AS phải dùng transaction/conditional update để tiêu thụ R1 một lần; replay handling phải tính tới retry/network timeout mà vẫn **không hồi sinh** R1.

Không nên tự thêm “grace window cho R1 reuse” mà không phân tích replay risk, nhất là public clients; nếu product cần xử lý mất response, phải thiết kế recovery riêng có bảo mật tương đương.

### 12.4. Phát hiện refresh reuse không chặn JWT đã đánh cắp

Nếu attacker đã giữ access token T1, thu hồi family F1 giúp chặn **cấp token mới**, nhưng T1 có thể tiếp tục hoạt động ở RS kiểm JWT offline cho đến `exp`.

Vì vậy, reuse detection cần gắn với **revocation propagation strategy** (denylist/grant epoch/introspection) nếu yêu cầu chặn T1 trước expiry.

### 12.5. Sender-constrained refresh/access tokens

Các cơ chế như **DPoP (RFC 9449)** hoặc **mTLS-bound tokens (RFC 8705)** có thể ràng buộc việc sử dụng token với một khóa/certificate:

~~~text
Attacker chỉ có token string
    nhưng không có private key/cert tương ứng
    => không dễ dùng token ở endpoint kiểm proof đúng.
~~~

Sender constraint **giảm khả năng replay của token bị đánh cắp**, **không thay thu hồi**: nếu private key bị lộ, thiết bị bị chiếm hoặc grant cần kết thúc, hệ thống vẫn cần policy và propagation. Ngoài ra, không phải mọi RS/framework tự hỗ trợ DPoP/mTLS; phải kiểm sender proof tại các endpoint có liên quan.

## 13. Logout, account disable và thay đổi quyền: những tín hiệu khác token revoke

Trong hệ thống OIDC, có thể cùng xảy ra:

~~~text
User logout khỏi Shop Web.
OpenID Provider session bị kết thúc.
Refresh token của Shop Web bị revoke.
Access token T1 còn trong một app khác.
Orders API vẫn kiểm JWT offline.
~~~

Mỗi trạng thái cần được phân biệt; không suy luận rằng user bấm Logout ở một app thì **mọi grant trên tất cả thiết bị** đã bị hủy.

### 13.1. Logout OIDC và OAuth revocation

Một số profile OIDC có **Back-Channel Logout**, trong đó OP gửi logout token/sự kiện tới Relying Party để chấm dứt session của RP tương ứng. Điều này khác với **RFC 7009 Token Revocation**:

| Cơ chế | Chủ thể/tác động | Không tự bảo đảm |
|---|---|---|
| App logout | Xóa session của app đang dùng | AS/RS đã revoke mọi token |
| OIDC Back-Channel Logout | RP session được thông báo/chấm dứt theo profile | Mọi OAuth access token offline vô hiệu |
| OAuth refresh token revocation | AS không cho refresh token/grant tiếp tục theo policy | JWT access token cũ bị chặn tại mọi RS |
| Global user disable/security epoch | Chặn nhiều sessions/grants của user | Mọi RS biết epoch mới ngay |

Nếu yêu cầu “đăng xuất khỏi mọi thiết bị”, phải mô tả phạm vi tokens, sessions, clients, regions và thời gian propagation có thể đạt được.

### 13.2. User bị khóa tài khoản

Khi user bị khóa do nguy cơ bảo mật:

1. AS chặn authorization/token issuance mới cho subject.
2. Thu hồi grants/refresh tokens liên quan theo policy.
3. Cập nhật subject security epoch/revocation state.
4. Phát event hoặc cho RS introspect/revalidate.
5. Với dữ liệu nhạy cảm, RS có thể cần **user-active check** ở request time.
6. Kiểm tra các background jobs, API keys/service accounts có liên kết thật với user hay không.

Không chỉ đổi một cờ `users.disabled=true` trong database của app nếu các RS khác không đọc cờ đó.

### 13.3. Role/tenant membership thay đổi

Một user có thể mất role `FINANCE_APPROVER` nhưng vẫn cần xem dữ liệu cá nhân. **Không nhất thiết** thu hồi tất cả access tokens nếu RS kiểm business policy tại runtime; điều quan trọng là **không cho approve vượt quyền**.

Nếu role được nhúng vào JWT và RS tin claim cho tới expiry, hệ thống cần:

- TTL đủ ngắn theo risk budget, hoặc
- policy/session version được tra lại/invalidate, hoặc
- stateful authorization check tại RS cho action nhạy cảm.

Token revocation là một cách giảm rủi ro stale role, **không thay** business authorization theo action/resource/tenant.

### 13.4. Client bị thu hồi registration

AS có thể vô hiệu client và ngừng cấp token mới. RS vẫn có thể nhận JWT đã phát cho client trước đó.

Nếu policy yêu cầu chặn ngay **mọi access token có `client_id` tương ứng**, cần một **client security epoch/denylist** được RS kiểm. Chỉ xóa client registration ở AS không bắt buộc khiến RS biết ngay.

## 14. Key rotation và key compromise không giống token revocation

JWT thường có header `kid` xác định public key để RS xác minh chữ ký. **Đổi signing key** là hoạt động quản lý khóa, không tự thu hồi riêng một access token.

### 14.1. Rotation bình thường

Trong key rotation bình thường:

~~~text
K1 là khóa cũ, đã ký token còn hạn.
K2 là khóa mới cho token phát hành sau thời điểm chuyển.
JWKS có thể còn K1 để RS xác minh token hợp lệ chưa hết hạn.
~~~

Xóa K1 khỏi JWKS **quá sớm** có thể làm lỗi hàng loạt token còn hạn của người dùng hợp lệ. Giữ K1 quá lâu sau khi private key đã bị compromise cũng nguy hiểm. Cần phân biệt:

- **Planned rotation**: chuyển phát hành sang K2, giữ K1 xác minh theo chiến lược TTL/cache.
- **Emergency key compromise**: thu hồi trust của K1 và chặn token đã ký bằng K1 nhanh nhất có thể, chấp nhận blast radius.

### 14.2. JWKS cache cũng có propagation lag

RS có thể cache JWKS trong vài phút:

~~~text
AS remove compromised K1 from JWKS.
RS cache vẫn chứa K1.
RS tiếp tục verify chữ ký từ K1.
~~~

Do đó, một kế hoạch key compromise cần **invalidate/update JWKS caches**, restart/reconfigure verifier khi cần, giới hạn thuật toán/issuer/key source và theo dõi rollout. Không giả định publish JWKS mới làm mọi RS ngừng tin K1 ngay.

**Cảnh báo:** loại bỏ một khóa có thể vô hiệu hóa **nhiều token hợp lệ** và tạo outage. Với một access token bị lộ, không nên “rotate toàn bộ signing key” thay cho một chiến lược revoke cụ thể nếu không có lý do compromise key.

### 14.3. Signing key không thay tenant/ownership checks

Token T1 có chữ ký K2 mới nhất không chứng minh subject có quyền đọc mọi resource. Kể cả sau key rotation đúng, RS vẫn cần issuer/audience/scope và business authorization.

## 15. Java/Spring Security: thêm revocation checks sau JWT validation

Một **Spring Security OAuth2 Resource Server** có thể kiểm JWT access token bằng issuer/JWKS. Nếu cần thu hồi sớm, phải **thêm state validation** tương ứng, không chỉ dựa vào `exp`.

### 15.1. Cấu hình khởi điểm cho Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Cấu hình này giúp thiết lập issuer/JWT validation theo khả năng framework, nhưng **không tự bảo đảm audience đúng Orders API, token type/profile, grant state hay business authorization**. Với opaque token, Spring Security còn có chế độ introspection riêng; đừng cấu hình JWT decoder cho một token opaque không có JWT.

### 15.2. Thêm validator audience và grant status

Ví dụ dưới đây sử dụng **custom JWT validators** cho Resource Server. API/phiên bản Spring Security phải được xác minh theo môi trường thực tế; đây là ví dụ diễn đạt cách thiết kế, không phải toàn bộ cấu hình production:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtConfig {
    private static final String ISSUER = "https://login.example.com";
    private static final String AUDIENCE = "https://orders.example.com";

    @Bean
    JwtDecoder jwtDecoder(GrantStateProvider grantStateProvider) {
        NimbusJwtDecoder decoder =
            (NimbusJwtDecoder) JwtDecoders.fromIssuerLocation(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = token -> {
            if (token.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));
        };

        OAuth2TokenValidator<Jwt> revocationValidator =
            new GrantStateValidator(grantStateProvider);

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator,
            revocationValidator
        ));
        return decoder;
    }
}
~~~

`GrantStateProvider` và `GrantStateValidator` là **thành phần ứng dụng tự xây**, không phải type Spring sẵn có. Cần thêm token type/profile validation (ví dụ theo JWT access token profile), scope authority mapping và object-level authorization.

**Chú ý:** validator không nên tin `grant_id`/`version` cho đến khi JWT đã được xác minh chữ ký và issuer/audience/time. Trong `NimbusJwtDecoder`, token được parse/verify rồi mới áp validators; nhưng hãy kiểm thử cách framework kết hợp các validators và tránh dùng claims từ JWT chưa xác minh ở một bước HTTP filter độc lập.

### 15.3. GrantStateValidator: fail closed khi trạng thái quá cũ

Pseudocode Java theo interface Spring:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class GrantStateValidator
        implements OAuth2TokenValidator<Jwt> {

    private final GrantStateProvider store;
    private final Clock clock = Clock.systemUTC();

    public GrantStateValidator(GrantStateProvider store) {
        this.store = store;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getIssuer() == null) {
            return fail("Issuer missing");
        }
        String issuer = jwt.getIssuer().toString();
        String grantId = jwt.getClaimAsString("grant_id");
        Object rawVersion = jwt.getClaim("grant_ver");

        if (grantId == null || !(rawVersion instanceof Number)) {
            return fail("Grant binding missing");
        }

        long presentedVersion = ((Number) rawVersion).longValue();
        GrantState state;
        try {
            state = store.currentState(issuer, grantId);
        } catch (Exception unavailable) {
            // Policy minh họa: fail closed nếu không xác minh được.
            return fail("Grant state unavailable");
        }

        if (state == null || !state.active()
                || state.version() != presentedVersion
                || state.freshUntil().isBefore(clock.instant())) {
            return fail("Grant revoked or state stale");
        }
        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult fail(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null));
    }
}
~~~

Trong đoạn mã:

- `GrantState` được giả định có `active()`, `version()`, `freshUntil()`.
- `GrantStateProvider` phải lấy được **authoritative/cached security state** có freshness guarantee, không chỉ một cache `ACTIVE` sống vô hạn.
- Không có `grant_id`/`grant_ver` theo profile nội bộ thì cần chiến lược khác như denylist `jti`, introspection hoặc subject epoch; không tự đổi mọi JWT thành grant token.
- Pseudocode trả `invalid_token` khi state unavailable để **fail closed**, nhưng production có thể cần tách lỗi vận hành 503 khỏi token thật sự bị thu hồi. Quan trọng là **không ALLOW** khi không thể xác minh trạng thái.
- `freshUntil` phải do cơ chế đồng bộ state đáng tin xác định; không để caller tự tạo bằng `now + 24h`.

**Không copy đoạn code này mà coi đó là một cơ chế instant revocation hoàn chỉnh.** Chính `store.currentState` và cách cache/invalidation hoạt động mới quyết định propagation latency.

### 15.4. Bảo vệ action/resource sau khi token đã qua kiểm tra

~~~java
// Pseudocode Spring MVC; cần cấu hình Method Security nếu dùng @PreAuthorize.
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        Authentication authentication) {

    VerifiedActor actor = actorFactory.fromValidatedAuthentication(
        authentication);

    return ordersService.readForAuthorizedActor(actor, orderId);
}
~~~

`VerifiedActor` phải được ánh xạ từ **principal/token đã xác minh**. `ordersService.readForAuthorizedActor` phải kiểm owner/tenant/sharing. Revocation check trả `active` không có nghĩa actor được đọc đơn hàng bất kỳ.

### 15.5. Spring opaque token introspection

Với opaque token, RS có thể cấu hình introspection endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-rs
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

**Ví dụ cấu hình** phụ thuộc phiên bản Spring Security và hợp đồng AS. Client credential dành cho introspection phải giữ ở server/secret manager. Cần giới hạn audience/issuer/scope và policy sau introspection; **không bảo đảm không có cache** nếu ứng dụng/customizer tự thêm caching.

Nếu introspection call thất bại, không được tự trả `active=true`. Cần thiết kế timeout, retry/backoff, circuit breaker và error semantics theo rủi ro, tránh để outage tạo một fail-open.

## 16. Java pseudocode: AS revoke, transactional outbox và event consumer

Ở AS, nên biểu diễn revoke bằng **thay đổi state có phiên bản và event bền vững**, thay vì chỉ phát message rồi hy vọng consumer ghi DB.

### 16.1. AS cập nhật grant và outbox cùng một transaction

~~~java
// Pseudocode, không phải API có sẵn của Spring Authorization Server.
RevocationReceipt revokeGrant(
        VerifiedRevocationActor actor,
        String grantId,
        String reasonCode) {

    return transaction.run(() -> {
        Grant grant = grantStore.lockAndRead(grantId);
        revocationPolicy.requireAuthorized(actor, grant);

        if (grant.isRevoked()) {
            return RevocationReceipt.alreadyRevoked(
                grant.id(), grant.securityVersion());
        }

        long nextVersion = grant.securityVersion() + 1;
        grantStore.markRevoked(
            grant.id(), nextVersion, clock.instant());

        outboxStore.insert(new SecurityEvent(
            newEventId(),
            "GRANT_REVOKED",
            grant.issuer(),
            grant.id(),
            nextVersion,
            reasonCode));

        return RevocationReceipt.committed(
            grant.id(), nextVersion);
    });
}
~~~

Pseudocode chỉ mô tả quyết định. Production cần kiểm actor có quyền revoke grant, nhất quán idempotency, concurrency, indexes, token family mapping và error semantics RFC 7009. Một request `/revoke` có thể chứa token chứ không trực tiếp `grantId`; AS phải tìm đúng grant/token theo client binding mà không lộ raw token.

### 16.2. Consumer idempotent và version-aware

~~~java
// Pseudocode: source trust, ordering, durability, checkpoint cần có.
void onSecurityEvent(SecurityEvent event) {
    eventVerifier.requireFromTrustedIssuer(event);
    schemaValidator.requireKnownEvent(event);

    securityStateStore.transaction(() -> {
        SecurityState state =
            securityStateStore.lockAndRead(
                event.issuer(), event.aggregateId());

        if (state != null && state.version() >= event.version()) {
            return; // duplicate hoặc stale event
        }

        if ("GRANT_REVOKED".equals(event.type())) {
            securityStateStore.upsertRevoked(
                event.issuer(), event.aggregateId(), event.version());
            introspectionCache.evictGrant(
                event.issuer(), event.aggregateId());
        } else {
            throw new UnsupportedSecurityEventException(event.type());
        }
    });

    brokerCheckpoint.ackAfterStateApplied(event.eventId());
}
~~~

**Không dùng đoạn này như contract “exactly once”.** Các thành phần cần phối hợp bền vững: commit state/cache invalidation, offset ack, retry và reconciliation. Nếu cache eviction không giao dịch cùng security store, phải bảo đảm **sự kiện đến cuối cùng vẫn làm cache stale bị xóa** hoặc RS tra security version trước khi ALLOW.

### 16.3. Race giữa cache fill và invalidate

Tình huống:

~~~text
T0: RS query grant v4 ACTIVE (đang pending network).
T1: Consumer nhận revoke v5, evict cache.
T2: Request T0 trả v4 ACTIVE.
T3: RS ghi v4 ACTIVE vào cache lần nữa.
~~~

Đây là **cache fill race**. Chỉ `evict` ở T1 có thể chưa đủ; cần:

- Cache entry mang **security version**.
- Write path không ghi đè version cũ lên version mới hơn.
- Revalidation khi phát hiện epoch mismatch.
- Không cache positive state quá freshness budget.
- Với nguồn authoritative, bảo đảm read không trả snapshot stale trái SLO.

### 16.4. Quy tắc thẩm quyền và event auth

Security events phải có:

- Producer được xác thực (mTLS/broker identity/signature theo trust boundary).
- Authorization cho loại event/issuer/aggregate.
- Schema version và kiểm dữ liệu.
- Event ID để dedup, aggregate version để chặn out-of-order.
- Timestamp để đo lag, **không** làm khóa thứ tự duy nhất.
- Audit trail và dead-letter handling có kiểm soát.

Một attacker không nên có khả năng publish `GRANT_ACTIVE` giả để hồi sinh grant bị thu hồi. Event types và state transitions phải được whitelist, định nghĩa **monotonic tombstones** cho revocation.

## 17. Token storage, revocation state và quyền riêng tư

Revocation propagation có thể tạo thêm dữ liệu nhạy cảm (grant IDs, subject IDs, token fingerprints, client IDs, lý do khóa tài khoản). Hệ thống không nên đổi **lợi ích bảo mật** lấy việc phát tán secrets qua broker/log.

### 17.1. Những gì không được đưa vào event/log

~~~text
Authorization: Bearer <ACCESS_TOKEN>
refresh_token=<REFRESH_TOKEN>
id_token=<SIGNED_ID_TOKEN>
client_secret=<CLIENT_SECRET>
private_key=<PRIVATE_KEY>
cookie=<SESSION_COOKIE>
authorization_code=<CODE>
code_verifier=<VERIFIER>
~~~

Nếu cần định danh token cho denylist, ưu tiên `iss+jti` sau khi JWT đã được xác minh hoặc một **HMAC fingerprint** cho token opaque; không lưu token thô làm key trong metrics dashboard.

### 17.2. Metadata vận hành có thể lưu

~~~text
traceId
issuerId
grantId (internal opaque reference)
eventId
securityVersion
eventType
reasonCategory
resourceServerId / region
commitTimestamp
publishTimestamp
consumerAppliedTimestamp
cacheFreshUntil
enforcementDecisionCategory
~~~

Mỗi trường vẫn cần data classification và retention. `grantId` hay subject reference có thể liên kết hành vi cá nhân; không xem identifier đã đổi tên là anonymous hoàn toàn.

### 17.3. Bảo vệ revocation store

Chỉ các dịch vụ có nhu cầu chính đáng mới được đọc hoặc thay đổi trạng thái grant/denylist. Các thao tác `UNREVOKE` hoặc chuyển `ACTIVE` từ trạng thái REVOKED cần bị chặn theo policy; một cấp quyền mới nên là **grant mới**. Dùng backup/restore có kiểm soát: restore database từ snapshot cũ không được làm grant đã revoke **hoạt động trở lại**.

Khi failover/restore, cần đối chiếu **security high-watermarks** và replay events sau snapshot; nếu không, hệ thống có thể “quên” các lệnh revoke gần nhất.

## 18. Threat model: những đường mà revocation không lan tới

| Lỗ hổng/sai sót | Điều xảy ra | Kiểm soát cần có |
|---|---|---|
| **JWT offline không tra state** | Access token đã revoke vẫn dùng tới `exp` | TTL hoặc online state/denylist/grant epoch |
| **Introspection positive cache dài** | `active=true` cũ sống sau AS revoke | TTL ngắn, event invalidation, freshness checks |
| **Replica stale** | Introspection trả ACTIVE từ read replica sau revoke | Consistency/authoritative reads phù hợp SLO |
| **Outbox thiếu transaction** | DB revoke xong nhưng event không publish | Transactional outbox và retry |
| **Consumer ack quá sớm** | Event bị mất trước khi update state | Ack sau durable apply hoặc reconciliation |
| **Consumer offline khi event phát** | Một RS giữ state cũ | Durable replay/checkpoint, bootstrap snapshot |
| **Out-of-order event** | Snapshot ACTIVE ghi đè REVOKED | Monotonic version, idempotency |
| **Cache fill race** | Entry ACTIVE v4 được ghi lại sau invalidation v5 | Version-aware cache writes |
| **Multi-region LWW sai** | Region khác phục hồi grant bị revoke | Authoritative ordering/tombstone |
| **Fail-open do outage** | Broker/AS không có mạng, RS vẫn ALLOW | Fail policy, freshness deadline, observability |
| **Bỏ qua RS nội bộ** | Gateway chặn nhưng downstream nhận token thẳng | Enforcement trên mọi trust boundary |
| **Refresh family chưa revoke** | Attacker xin access token mới dù T1 bị chặn | Family/grant revoke tại AS, reuse detection |
| **Subject disable không propagate** | User bị khóa vẫn gọi API bằng JWT cũ | Subject epoch hoặc policy lookup |
| **Client de-registration chỉ tại AS** | JWT cũ của app độc hại vẫn được chấp nhận | Client epoch/denylist theo policy |
| **JWKS cache giữ key bị lộ** | Token giả ký bằng K1 vẫn được xác minh | Emergency key trust invalidation |
| **Long-lived denylist cache** | RS không thấy revoked `jti` | Invalidation/TTL và versioned state |
| **Denylist entry bị xóa quá sớm** | T1 còn hợp lệ lại được ALLOW | Retention qua expiry + leeway |
| **Event không được xác thực** | Attacker publish state giả | Producer auth, ACL, schema + version checks |
| **Restore snapshot cũ** | Grant đã revoke được ACTIVE trở lại | Reconciliation/replay security events sau restore |
| **Business policy bị bỏ qua** | Token còn hiệu lực đọc dữ liệu tenant khác | Object/action/tenant authorization ở RS |

### 18.1. Tách “thất bại bảo mật” và “thất bại vận hành”

Có hai trường hợp phải phân biệt:

**A. Token thật sự đã bị revoke nhưng RS tiếp tục ALLOW.** Đây là vi phạm enforcement policy/propagation SLO nếu kiến trúc cam kết chặn sớm.

**B. RS không xác minh được trạng thái vì introspection outage.** Đây là trạng thái không chắc chắn. Hệ thống có thể fail closed, trả lỗi tạm thời, dùng snapshot được phép trong hard TTL hoặc chấp nhận rủi ro rõ ràng. Không tự biến “không biết” thành “token chắc chắn ACTIVE”.

### 18.2. Revocation event bị giả mạo cũng là rủi ro availability

Một attacker phát event `USER_REVOKED` giả có thể làm nhiều người bị khóa. Vì vậy authentication/integrity của event vừa phòng **bypass** vừa phòng **denial of service**. Một hệ thống chỉ cho phép event thu hồi cũng vẫn phải kiểm producer có thẩm quyền đối với issuer/tenant/user tương ứng.

### 18.3. Cấp token mới trong khi grant đã bị revoke

Một lỗi race nguy hiểm:

~~~text
T0: Refresh request đọc grant g-947 ACTIVE.
T1: Admin revoke g-947, commit REVOKED.
T2: Refresh request phát access token mới từ grant cũ.
~~~

AS phải ràng buộc **refresh/token issuance và revoke** bằng transaction/version check hoặc cơ chế nhất quán phù hợp. Chỉ ngăn RS dùng T1 chưa đủ nếu AS vẫn phát T2 sau khi grant bị revoke.

### 18.4. Không để replay revocation event hồi sinh grant

Event `GRANT_REVOKED` lặp lại phải idempotent. Event `GRANT_ACTIVE` cũ đến muộn không được ghi đè revocation. Việc ủy quyền lại phải tạo **new grant/generation** theo workflow, không dùng event cũ để chuyển trạng thái ngược.

## 19. Ma trận kiểm thử revocation propagation end-to-end

Test chỉ gọi `/revoke` rồi thấy HTTP 200 là **chưa kiểm thử propagation**. Cần tạo test credential, revoke, sau đó chứng minh nó bị từ chối tại các RS đúng phạm vi.

### 19.1. RFC 7009 và trạng thái AS

| Kịch bản | Kết quả mong muốn |
|---|---|
| Client hợp lệ revoke refresh token thuộc mình | AS xử lý revoke theo contract |
| Revoke token không tồn tại | HTTP 200 trong trường hợp hợp lệ theo RFC 7009, không lộ tồn tại |
| Client không xác thực đúng method | AS từ chối theo client authentication policy |
| Client A cố revoke token của B | AS không cho thực hiện trái client binding |
| `token_type_hint` sai | Không tin hint như quyền hay token type thực |
| Revoke R1 nhưng R1 vừa được rotation thành R2 | Policy family/reuse xử lý nhất quán |
| Revoke grant và refresh đồng thời | Không phát access/refresh token mới trái policy |
| AS crash sau revoke commit trước publish | Outbox retry vẫn truyền event |
| AS nhận hai revoke requests cùng grant | Idempotent, không tạo trạng thái sai |
| R1 đã revoke rồi lại refresh | Từ chối cấp token mới |
| Scope/audience thay đổi ở request refresh | Không tăng quyền ngoài grant |

### 19.2. JWT/opaque tại Resource Server

| Kịch bản | Kết quả mong muốn |
|---|---|
| JWT chữ ký đúng, còn hạn, grant đã revoke | RS từ chối nếu hệ thống cam kết early revocation |
| JWT hết hạn, denylist không có entry | Vẫn từ chối bằng exp |
| JWT sai issuer hoặc audience | Từ chối dù grant state ACTIVE |
| JWT thiếu grant version trong profile yêu cầu | Từ chối, không fallback ngầm |
| `jti` trùng giữa hai issuer khác nhau | Không revoke nhầm nhờ issuer namespace |
| Denylist entry cho T1 ở Orders API | T1 bị chặn cả ở mọi Orders API instance |
| Opaque token introspection `active=false` | RS từ chối |
| Opaque token `active=true` nhưng aud dành API khác | RS từ chối |
| JWT có scope read nhưng order thuộc Bob | Từ chối theo resource policy |
| ID token gửi như access token | RS từ chối sai type/audience |
| Refresh token gửi Bearer tới RS | RS từ chối sai credential |
| JWT offline không có state checks | Test **xác nhận cửa sổ tới exp** đúng thiết kế, không giả định instant revoke |

### 19.3. Cache và propagation

| Kịch bản | Kết quả mong muốn |
|---|---|
| RS cache introspection ACTIVE, sau đó revoke | Cache hết/invalidate trong freshness budget |
| AS revoke, broker chậm 30 giây | Hệ thống cảnh báo vượt SLO hoặc fallback fail closed |
| Consumer nhận duplicate revoke event | Idempotent, version không giảm |
| Consumer nhận v4 ACTIVE sau v5 REVOKED | Không hồi sinh grant |
| Event có version lớn hơn local | Cập nhật state/evict cache bền vững |
| Cache fill v4 trả sau invalidation v5 | Version-aware cache không ghi ACTIVE cũ |
| RS restart khi grant đã revoke trước đó | Bootstrap snapshot/replay, không chấp nhận grant vì cache trống |
| RS mới scale-out từ image sạch | Không nhận traffic nhạy cảm trước khi đủ freshness |
| Broker mất mạng 10 phút | Fail behavior đúng risk policy và giám sát rõ |
| Introspection đọc stale replica | Test phát hiện consistency lag và kiểm giải pháp |
| Nhiều RS ở hai region | Mỗi instance/region từ chối credential trong SLO |
| Region failover/DB restore | Không mất revocation tombstones/checkpoint |
| Outbox event chưa publish | Publisher retry, không coi event “done” |
| Consumer crash sau cập nhật nhưng trước ack | Replay an toàn, không sai trạng thái |

### 19.4. Refresh token, OIDC và key rotation

| Kịch bản | Kết quả mong muốn |
|---|---|
| R1 rotation sang R2 | R1 USED, chỉ token đúng policy còn active |
| Attacker dùng lại R1 | Phát hiện reuse và xử lý token family/grant |
| Hai refresh requests đồng thời từ R1 | Không tạo hai nhánh refresh hợp lệ trái chính sách |
| Revoke refresh family nhưng JWT T1 còn hạn | T1 chỉ bị chặn sớm nếu RS có propagation control |
| User logout ở RP | Session tương ứng bị hủy; các tokens xử lý đúng policy |
| OIDC Back-Channel Logout | RP session xử lý, không suy RS đã revoke mọi JWT |
| User bị disable | Không phát token mới; RS đáp ứng subject epoch/policy |
| Client registration bị disable | AS chặn issuance; RS xử lý token cũ theo kế hoạch |
| Signing key rotate bình thường | Token ký bằng K1 còn hạn có thể tiếp tục hợp lệ theo rotation policy |
| K1 bị compromise | Emergency key invalidation cập nhật mọi verifiers trong thời gian mục tiêu |

### 19.5. Kiểm thử chaos và SLO

Một bài test có thể:

1. Phát test JWT T1 cho grant g-947, xác minh Orders API chấp nhận đúng resource test.
2. Revoke g-947, ghi timestamp **commit** từ AS.
3. Gửi request test an toàn qua từng RS instance/region theo cơ chế đo (không dùng production token).
4. Đo thời gian API đầu tiên từ chối T1 tại mỗi enforcement point.
5. Tiêm lỗi: broker pause, consumer crash, stale cache, replica lag, rolling restart.
6. Xác minh không nơi nào vượt freshness hard limit mà vẫn ALLOW nếu policy yêu cầu.
7. Kiểm tra token không bị **hồi sinh** sau event replay/restore.
8. Kiểm tra các token/grants khác **không bị revoke nhầm**.
9. Đảm bảo business authorization vẫn chặn cross-tenant/object access kể cả khi token state ACTIVE.
10. Kiểm tra log/test reports không chứa raw tokens, refresh tokens hoặc client secrets.

**Không thể chứng minh hệ thống luôn từ chối trong X giây bằng một lần thử ở một node.** Cần kiểm tra phân tán, thời điểm rìa và error paths có thể xảy ra.

## 20. Tình huống suy luận

### Tình huống A — AS báo revoke 200, JWT vẫn còn hạn

Alice revoke refresh token lúc 10:03. Orders API chỉ kiểm JWT signature/audience/exp, T1 còn hạn tới 10:15.

**Câu hỏi:** API nhận T1 lúc 10:05 có thể trả 200 không?

**Trả lời:** Có thể, trong thiết kế chỉ kiểm JWT offline. HTTP 200 từ RFC 7009 không có nghĩa mọi RS biết revoke. Nếu yêu cầu chặn trước expiry, cần grant state/denylist/introspection hoặc cơ chế tương đương.

### Tình huống B — Opaque token có introspection cache

AS trả `active=false` ngay sau revoke, nhưng Orders API đã cache response `active=true` trong 60 giây.

**Câu hỏi:** Tại sao RS có thể tiếp tục chấp nhận?

**Trả lời:** RS đang tin **positive cache stale**, chưa gọi lại introspection hoặc chưa nhận invalidation. Thiết kế phải giới hạn TTL, event invalidate và freshness policy đúng SLO.

### Tình huống C — Broker báo publish thành công

AS publish `GRANT_REVOKED` thành công; Orders API nhận event, Billing API offline chưa nhận.

**Câu hỏi:** Có thể báo “revoked everywhere” không?

**Trả lời:** Không. Publish success khác enforcement acknowledgement. Cần đo consumer apply và token rejection ở mọi RS/region trong phạm vi, hoặc fail closed khi không hội tụ.

### Tình huống D — Event ACTIVE đến sau REVOKED

Consumer đã lưu g-947 `REVOKED, version=5`, nhưng nhận snapshot `ACTIVE, version=4` đến muộn.

**Câu hỏi:** Có được trở lại ACTIVE không?

**Trả lời:** Không. Event stale phải bị bỏ qua nhờ monotonic version; grant đã revoke không được hồi sinh từ snapshot cũ.

### Tình huống E — Cache invalidation gặp race

Event revoke v5 xóa cache, nhưng một request đang xử lý trước đó vừa nhận v4 ACTIVE từ DB replica và ghi lại.

**Câu hỏi:** Vì sao chỉ `cache.evict()` chưa đủ?

**Trả lời:** Cache fill race cho phép dữ liệu cũ được ghi lại sau invalidation. Dùng version-aware writes, authoritative state và freshness checks để chặn stale overwrite.

### Tình huống F — Tắt introspection khi outage

Introspection endpoint tạm không truy cập được; API fallback “nếu signature JWT đúng thì ALLOW”.

**Câu hỏi:** Điều này có rủi ro gì?

**Trả lời:** Đây là một **fail-open path** có thể cho token đã revoke hoạt động. Với action nhạy cảm cần fail closed/revalidation hoặc stale cache hard TTL đã được risk review phê duyệt; không bật fallback im lặng.

### Tình huống G — Thu hồi R1 nhưng không revoke R2

R1 đã rotation thành R2, attacker dùng lại R1. Hệ thống chỉ từ chối R1 nhưng vẫn cho R2 tiếp tục hoạt động.

**Câu hỏi:** Có đạt mục tiêu reuse detection không?

**Trả lời:** Tùy policy nhưng với reuse nghi xâm phạm family, chỉ chặn R1 có thể không đủ. AS cần nhận biết family/grant, đánh giá revoke R2 và các token liên quan, không thể biết chắc bên nào là attacker.

### Tình huống H — Một device bị mất

Alice mất điện thoại, còn laptop được tin cậy vẫn đang làm việc.

**Câu hỏi:** Có bắt buộc revoke toàn bộ user không?

**Trả lời:** Không nhất thiết. Nếu có binding grant/device/session đáng tin, có thể thu hồi chỉ thiết bị bị mất; nếu không phân biệt được hoặc mức rủi ro cao, có thể cần thu hồi rộng hơn. Cần xác định phạm vi theo threat model.

### Tình huống I — User bị gỡ role

Alice mất quyền FINANCE_APPROVER; access token còn sống và có claim `roles=["FINANCE_APPROVER"]`.

**Câu hỏi:** Có nên tin claim đó cho thao tác duyệt?

**Trả lời:** Không nếu policy yêu cầu role hiện thời. RS phải recheck role/epoch hoặc dùng TTL đủ ngắn theo risk budget; consent/login cũ không thay current authorization.

### Tình huống J — JWT của Billing API gửi tới Orders API

T1 đúng chữ ký và chưa bị revoke, nhưng `aud` chỉ dành cho Billing API.

**Câu hỏi:** Orders API có thể ALLOW vì T1 active không?

**Trả lời:** Không. Audience là kiểm tra độc lập. Token không bị revoke không chứng minh đúng API; RS phải kiểm `iss`, `aud`, scope, thời gian và resource policy.

### Tình huống K — Token hết hạn, denylist entry đã dọn

T1 đã qua `exp` và bị xóa khỏi denylist theo retention đúng.

**Câu hỏi:** T1 có thể được chấp nhận lại vì không còn denylist entry?

**Trả lời:** Không nếu RS vẫn kiểm `exp` đúng và không chấp nhận token hết hạn. Denylist là lớp bổ sung, không thay expiry. Cleanup phải xét leeway để tránh xóa khi validator còn có thể chấp nhận.

### Tình huống L — RS mới khởi động từ cache rỗng

Orders API mới được scale-out và subscribe từ latest broker offset; grant g-947 bị revoke hôm qua.

**Câu hỏi:** Vì sao đây là lỗ hổng?

**Trả lời:** Node mới không biết event quá khứ. Nếu cache rỗng được hiểu là ACTIVE thì token cũ có thể được chấp nhận. Cần snapshot/replay/checkpoint và readiness/fallback trước khi nhận traffic.

### Tình huống M — Signing key rotation

AS phát token bằng K2 mới nhưng vẫn công bố K1 trong JWKS để xác minh token cũ chưa hết hạn.

**Câu hỏi:** Có đồng nghĩa K1 bị compromise hoặc mọi token K1 bị revoke không?

**Trả lời:** Không. Đây có thể là planned rotation bình thường. Emergency key compromise có yêu cầu vô hiệu trust và propagation khác, với blast radius đáng kể.

### Tình huống N — Key bị lộ, JWKS cache chưa refresh

Private key K1 bị lộ; AS xóa K1 khỏi JWKS. Một RS vẫn giữ K1 trong cache và tiếp tục chấp nhận chữ ký K1.

**Câu hỏi:** Cần làm gì?

**Trả lời:** Thiết kế emergency invalidate/update JWKS trust trên mọi verifiers, theo dõi completion và cân nhắc fail-closed, không chỉ publish file JWKS mới rồi giả định hội tụ.

### Tình huống O — Multi-region ghi đè

Region A revoke grant version 7. Region B có bản copy ACTIVE version 6 và restore DB snapshot; replication last-write-wins theo timestamp khiến version 6 ghi đè.

**Câu hỏi:** Nguyên nhân gốc?

**Trả lời:** State revocation thiếu monotonic authority/version conflict resolution. Cần tombstones/version ordering và replay/reconcile sau restore, không dựa vào local timestamps.

### Tình huống P — Admin disable client

AS xóa client registration `third-party-99`. RS tiếp tục nhận access token do client đó đã được phát từ hôm trước.

**Câu hỏi:** Vì sao?

**Trả lời:** RS không tự đọc client registry ở AS cho mỗi request. Muốn chặn token cũ trước `exp`, phải có client revocation epoch/state/denylist hoặc chính sách tương đương.

### Tình huống Q — Downstream bypass gateway

API Gateway đã kiểm revoke, nhưng một microservice nội bộ cho phép gọi Orders API trực tiếp bằng JWT T1.

**Câu hỏi:** Kiểm gateway đủ chưa?

**Trả lời:** Không nếu có đường bypass. Orders API hoặc tầng enforcement đáng tin của nó phải kiểm token revocation/resource policy; cần bảo vệ topology/mTLS/service trust và chặn bypass.

### Tình huống R — Token theft trước khi revoke

Attacker đã dùng T1 để tải dữ liệu lúc 10:02; Alice revoke lúc 10:03 và mọi RS chặn sau 2 giây.

**Câu hỏi:** Đã thu hồi toàn bộ tác động chưa?

**Trả lời:** Không thể hoàn tác dữ liệu đã bị đọc. Revocation giảm truy cập tiếp theo, còn incident response cần xem logs, xuất dữ liệu, hành động đã thực hiện và quyền downstream.

### Tình huống S — Positive cache trong lúc AS outage

RS có introspection cache ACTIVE từ 8 phút trước; AS outage. Dev bật `serve-stale=true` vô thời hạn để không làm gián đoạn người dùng.

**Câu hỏi:** Điều gì sai?

**Trả lời:** Token có thể bị revoke nhưng RS vẫn dùng trạng thái cũ vô hạn, phá revocation SLO. Cần hard freshness bound và fail mode được định nghĩa rõ.

### Tình huống T — `jti` tái sử dụng giữa hai issuer

AS A và AS B đều cấp token với `jti=42`. Orders API revoke A/42 nhưng denylist chỉ dùng key `42`.

**Câu hỏi:** Hệ quả?

**Trả lời:** Có thể revoke nhầm B/42 hoặc trộn trạng thái. Cần namespace ít nhất theo issuer + jti (và ngữ cảnh token/profile khi cần).

### Tình huống U — Đo propagation bằng last request

Một RS không có request nào sau khi revoke. Dashboard báo 100% RS đã chặn chỉ vì consumer đã ack event.

**Câu hỏi:** Kết luận có chắc chắn không?

**Trả lời:** Consumer ack không nhất thiết chứng minh enforcement. Nếu cần độ tin cậy cao, dùng durable applied checkpoint, readiness/health + synthetic request theo test token, và chứng minh mọi request path kiểm state.

### Tình huống V — Token family bị revoke nhưng RS vẫn có `active=true`

AS đã phát event revoke family, nhưng Orders API cache opaque introspection `active=true` 120 giây.

**Câu hỏi:** Thiết kế cần tối ưu điểm nào?

**Trả lời:** Kết nối grant/family revocation tới cache entries của token liên quan, invalidate theo version, giới hạn positive TTL và revalidate theo freshness. Chặn refresh không đủ để chặn access tokens đang cache.

## 21. Playbook ứng cứu khi token hoặc khóa bị lộ

Một lệnh revoke đúng giao thức là **một thao tác trong incident response**, không phải điểm kết thúc. Mục tiêu là giảm truy cập tiếp theo và biết chính xác phạm vi tác động.

### 21.1. Bước 1 — Xác định loại sự cố

| Tín hiệu | Hành động đầu tiên cần xem xét |
|---|---|
| Refresh token của một thiết bị bị lộ | Thu hồi family/grant thiết bị, kiểm rotation/reuse |
| Access token T1 bị lộ | Thu hồi T1/denylist hoặc grant theo policy, kiểm RS nào nhận T1 |
| User account compromise | Thu hồi sessions/grants theo phạm vi, yêu cầu reauthentication |
| Client secret/private key của OAuth client bị lộ | Rotate/revoke client credentials, chặn issuance và đánh giá token cũ |
| JWT signing key của AS bị lộ | Emergency key trust invalidation, đánh giá tất cả RS/regions |
| Quyền admin bị cấp nhầm | Sửa grant/policy, chặn access và kiểm business actions |

Đầu tiên phải phân biệt **raw access token**, **refresh token**, **OAuth client credential**, **signing key** và **browser session cookie**; chúng có propagation paths khác nhau.

### 21.2. Bước 2 — Khoanh vùng tokens/grants và enforcement points

Thu thập metadata bảo vệ:

~~~text
issuerId
clientId
grantId / tokenFamilyId
subjectReference
resourceAudiences
affectedTokenIds hoặc HMAC fingerprints
issuedAt / expiresAt
revokedAt / securityVersion
knownResourceServers / regions
~~~

Không ghi raw token vào ticket điều tra. Cần liên kết **AS issuance → grant → RS access logs** bằng ID/audit metadata phù hợp.

### 21.3. Bước 3 — Commit thu hồi và chặn phát hành mới

- AS lưu revoke state nguyên tử, chặn refresh và cấp token mới theo grant bị thu hồi.
- Với client/key compromise, thay credential/trust và xác định scope của các access token cũ.
- Ghi **outbox/security event** cùng transaction hoặc cơ chế nhất quán tương đương.
- Tránh tạo trạng thái ACTIVE từ retry hoặc rollback lỗi.
- Với user account compromise, kích hoạt step-up/reauthentication và quản lý session.

### 21.4. Bước 4 — Truyền quyết định tới RS và quan sát convergence

1. Publish events/replay outbox.
2. Kiểm consumer checkpoints, current version và cache invalidation ở mọi region.
3. Nếu một RS vượt freshness budget, dùng fail closed hoặc cô lập traffic theo kế hoạch.
4. Đo enforcement bằng test token/canary an toàn, không phát lại credential lộ trên môi trường production không được phép.
5. Ghi thời điểm commit/propagate/enforce theo scope incident.
6. Xác minh không còn đường bypass qua internal services/batch/export.

**Không tuyên bố “đã khóa hoàn toàn” chỉ vì dashboard AS hiển thị REVOKED.** Báo cáo phải tách mức chắc chắn ở AS và tại các RS.

### 21.5. Bước 5 — Đánh giá tác động nghiệp vụ

Thu hồi không hoàn tác:

- Dữ liệu đã tải hoặc sao chép ra ngoài.
- Giao dịch đã được duyệt/thanh toán.
- Các tác vụ nền được xếp hàng.
- Token downstream đã được token exchange trước sự cố.
- Sessions/service credentials khác không liên kết với grant vừa thu hồi.

Cần điều tra quyền và hành động đã sử dụng, có thể phải hủy jobs, xử lý dữ liệu đã xuất, thông báo bảo mật hoặc thủ tục pháp lý theo chính sách.

### 21.6. Bước 6 — Hậu kiểm

Một incident review nên trả lời:

- Vì sao credential bị lộ hoặc grant bị cấp sai?
- Revoke commit lúc nào và RS cuối cùng từ chối lúc nào?
- Có request nào được ALLOW sau `revoked_at` ngoài budget?
- Broker/cache/replica/region nào tạo độ trễ lớn?
- Có event nào bị mất, stale overwrite, restore hồi sinh grant hoặc cache fill race?
- Có thể giảm TTL, cải thiện sender constraint, hard freshness bound hay object policy không?
- Những tests nào phải bổ sung trong CI/chaos suite?

Không dùng kết quả “không thấy thêm request” làm bằng chứng mạnh rằng mọi RS đều có cơ chế enforce đúng; hãy kiểm tra kiến trúc và probes.

## 22. Checklist thiết kế revocation propagation

1. **Định nghĩa phạm vi:** muốn revoke access token, refresh token, grant, token family, session, user, device hay client?
2. **Sở hữu quyết định:** nguồn authoritative nào ghi trạng thái, ai có quyền thay đổi, có audit/idempotency không?
3. **RFC 7009:** endpoint dùng HTTPS, client binding đúng, token_type_hint chỉ là hint và HTTP 200 không chứng minh enforcement toàn hệ thống.
4. **AS token endpoint:** chặn refresh/token issuance khi grant/family REVOKED; xử lý rotation/reuse/transaction race.
5. **Token format:** JWT offline có cửa sổ tới `exp`; opaque introspection có phụ thuộc cache/replica.
6. **Expected audience:** RS xác minh issuer, audience, token type, thời gian, scope và quyền resource/action/tenant.
7. **Early revocation:** nếu cần, dùng introspection/state check, denylist `jti`, grant/session epoch hoặc mô hình hybrid.
8. **Cache:** positive TTL có hard upper bound, không vượt `exp`, invalidation đúng token/grant, không cache network failure như ACTIVE.
9. **Event durability:** transactional outbox, retry, producer auth, event ID, aggregate version và replay.
10. **Ordering:** xử lý duplicate/out-of-order bằng monotonic version, không hồi sinh REVOKED từ ACTIVE snapshot cũ.
11. **Bootstrap:** RS mới có snapshot/catch-up/ready checks; không coi cache trống là chưa revoke.
12. **Multi-region:** chọn consistency/conflict resolution phù hợp, quản lý stale replicas và DB restore.
13. **Failure mode:** định nghĩa fail-closed/fail-open/serve-stale theo action, có freshness deadline và báo lỗi phù hợp.
14. **SLO:** đặt mốc t1 commit và t5 enforcement, đo lag P99/outliers theo RS/region.
15. **Refresh family:** rotation hoặc sender constraint theo profile, reuse detection và family revocation.
16. **Logout/disable:** OIDC RP session, OAuth grant, account disabled, role/tenant change được xử lý theo ranh giới riêng.
17. **Key compromise:** có playbook invalidation JWKS/verifier caches, không nhầm với planned key rotation.
18. **Data minimization:** event/log không chứa raw token, client secret, private key hoặc session cookie.
19. **Test:** revoke lúc token còn hạn; thử RS nhiều region, chaos broker, cache fill race, restore và replay.
20. **Incident response:** xác minh token bị chặn tại enforcement points, điều tra API access đã xảy ra, không dừng ở AS HTTP 200.

### 22.1. Sơ đồ lựa chọn nhanh

~~~mermaid
flowchart TD
    A[Cần revoke token trước exp?] --> B{Không}
    B -- Có thể chờ exp --> C[JWT ngắn hạn + kiểm exp đúng]
    A --> D{Có}
    D --> E{RS có thể kiểm trạng thái online?}
    E -- Có --> F[Introspection hoặc authoritative grant state]
    E -- Không / cần giảm latency --> G[Local denylist/epoch + event propagation]
    F --> H[Cache TTL và fail policy]
    G --> I[Outbox, durable events, version, snapshot]
    H --> J[Kiểm enforcement mọi RS / region]
    I --> J
    J --> K[Đo propagation SLO và chaos tests]
~~~

Sơ đồ chỉ giúp bắt đầu chọn kiến trúc; một hệ thống có thể kết hợp nhiều cơ chế. Điều quyết định là **RS thực sự từ chối token đã bị thu hồi trong cửa sổ bảo mật được chấp thuận**, kể cả khi có cache, mạng partition hoặc deployment mới.

### 22.2. Tóm tắt trong một phút

~~~text
Revocation request accepted
         ≠
AS revocation state committed
         ≠
Event delivered to RS
         ≠
RS enforced revocation.

Refresh token revoke:
    chặn xin token mới ở AS.

JWT access token offline:
    có thể vẫn sống tới exp nếu không tra revoke state.

Opaque + introspection:
    có thể chặn sớm, nhưng cache/replica có thể stale.

Event-driven propagation:
    cần outbox + idempotency + version + replay + freshness.

Resource Server:
    token valid + not revoked + audience/scope
    + principal/action/resource/tenant policy.
~~~

**Kết luận:** Revocation propagation là bài toán **đưa quyết định thu hồi từ nguồn đáng tin tới mọi nơi có thể chấp nhận credential, với độ trễ đo được và hành vi an toàn khi hệ thống phân tán gặp lỗi**. RFC 7009 định nghĩa cách yêu cầu AS thu hồi token, nhưng **không thay việc RS cưỡng chế trạng thái mới**. JWT tự xác minh, opaque introspection, denylist, grant version và event-driven cache invalidation đều có cửa sổ rủi ro riêng. Hệ thống cần chọn kiến trúc theo **thời gian chặn mong muốn, khả năng chịu lỗi, latency, privacy và đặc tính tài nguyên**, đồng thời kiểm tra quyền theo **resource/action** ngay cả khi token còn hợp lệ.

## Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, response semantics, token_type_hint và tác động lên các token cùng grant.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active state, bảo vệ introspection endpoint và cân nhắc caching.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, grant, client authentication và token endpoint.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh rotation/sender-constrained tokens, token theft và security policy.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `nbf`, `iat`, `jti` và validation semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims, issuer, audience và token type.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential và resource server error semantics.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained tokens bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender constraint với proof-of-possession.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegated/downstream tokens, subject và actor.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): thông báo logout tới Relying Parties, khác OAuth token revocation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, login session và OIDC.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, validators và issuer/audience.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và resource server integration.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): token issuance, client registration, refresh token và các điểm mở rộng.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): token storage, refresh/revocation và bảo vệ OAuth.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): default deny, least privilege và authorization trên tài nguyên.
