# Không cache quá lâu trạng thái active

Lúc **10:00:00**, Orders API gọi Authorization Server để introspect một **opaque access token**. Kết quả trả về **active=true**, token còn hạn một giờ và có scope **orders:read**. Orders API giữ kết quả này trong cache **30 phút** để giảm độ trễ. Đến **10:02:00**, quản trị viên phát hiện token bị lộ và **thu hồi chính access token ấy**. Authorization Server đã cập nhật trạng thái **active=false**, nhưng Orders API vẫn tin entry **active=true** trong cache cho tới **10:30:00**. Trong 28 phút ấy, người giữ token bị lộ có thể tiếp tục thử đọc dữ liệu.

Điểm sai không nhất thiết nằm ở endpoint introspection: Authorization Server đã trả trạng thái mới chính xác. Lỗi nằm ở **khoảng thời gian Resource Server tiếp tục dùng trạng thái active cũ mà không hỏi lại**.

**Không cache quá lâu trạng thái active** là nguyên tắc giới hạn độ trễ giữa **thay đổi hiệu lực token ở Authorization Server** và **thời điểm Resource Server ngừng chấp nhận token**. Cache giúp giảm chi phí gọi introspection, nhưng mỗi giây cache **active=true** là một phần của **cửa sổ stale authorization** cần được đánh giá và kiểm soát.

Bài thuộc chương **Introspection** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là RFC 7662, thời hạn cache, revocation, JWT/opaque access token, refresh token, issuer, audience, scope, xác thực giữa Resource Server và Authorization Server, cùng các biện pháp giảm thiểu token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

Sau bài học, bạn sẽ tính được **giới hạn thời gian sống của một kết quả active**, thiết kế cache key bảo mật, phân biệt positive/negative cache, xử lý AS outage theo nguyên tắc fail closed, dùng sự kiện thu hồi để xóa cache, và kiểm thử **không có stale active kéo dài quá policy**.

## 1. Introspection giải quyết bài toán tin cậy nào?

Trong OAuth 2.0, **Authorization Server (AS)** phát hành và quản lý trạng thái token; **Resource Server (RS)** bảo vệ API; **OAuth client** gửi access token để xin truy cập. Khi token có dạng **opaque** (không cho RS tự kiểm claims và trạng thái bằng cách đọc chuỗi), RS có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** để hỏi AS về token.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Orders API / Resource Server
    participant AS as Authorization Server
    C->>RS: GET /orders + Bearer access token
    RS->>AS: POST /introspect, xác thực RS + token
    AS->>AS: Kiểm token, trạng thái, policy và caller
    AS-->>RS: HTTP 200, active=true, scope/aud/exp...
    RS->>RS: Kiểm issuer, audience, scope và quyền đơn hàng
    RS-->>C: Dữ liệu được phép
~~~

| Vai trò | Điều được quyền làm | Điều không được suy diễn |
|---|---|---|
| **Authorization Server** | Phát hành, quản lý, thu hồi token; cung cấp introspection cho bên được phép | Không quyết định thay mọi chính sách quyền trên đối tượng ở API |
| **Resource Server** | Xác minh access token và áp dụng authorization cho request | Không được coi trạng thái active đã cache là sự thật vĩnh viễn |
| **OAuth client** | Dùng access token đúng resource/audience | Không được gửi refresh token hoặc ID token thay access token |
| **Resource Owner / user** | Có thể cấp/thu hồi quyền theo policy | Một phiên login đang tồn tại không tự duy trì hiệu lực token đã bị revoke |

**Introspection không phải token endpoint**: nó kiểm trạng thái của token đã được cấp, không phải nơi đổi authorization code hoặc refresh token lấy access token mới. **Introspection cũng không phải Resource Server authorization**: kết quả trả về giúp RS quyết định liệu token có thể được tin trong ngữ cảnh nhất định, nhưng quyền đọc **đơn hàng cụ thể** vẫn thuộc API/policy engine.

## 2. RFC 7662: active=true và active=false thực sự biểu thị gì?

Một introspection request cơ bản dùng **POST** qua TLS, **application/x-www-form-urlencoded**, và phải được AS bảo vệ bằng cơ chế xác thực/ủy quyền caller phù hợp.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=<opaque-access-token>&token_type_hint=access_token
~~~

**token_type_hint** là gợi ý để AS tìm token hiệu quả hơn, **không phải bằng chứng token đó thật sự là access token**. AS phải dùng dữ liệu/trạng thái tin cậy để xác định loại token và tính hợp lệ.

### Response active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "client_id": "shop-web",
  "sub": "user-42",
  "iss": "https://auth.example.org",
  "aud": "orders-api",
  "scope": "orders:read",
  "token_type": "Bearer",
  "iat": 1795400000,
  "exp": 1795403600
}
~~~

Ví dụ có **timestamp giả**, không phải token thực. RFC 7662 định nghĩa **active** là boolean; thông tin khác có thể xuất hiện tùy token, AS và hợp đồng. **active=true** cho biết AS coi token đang hoạt động theo chính sách của nó tại **thời điểm trả lời**. Nó **không bảo đảm** trạng thái ấy sẽ đúng sau vài phút và **không có nghĩa** RS được bỏ kiểm audience, scope hoặc quyền tài nguyên.

### Response inactive

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

**HTTP 200 kèm active=false là kết quả introspection hợp lệ**, không phải “token được cho phép” và cũng không phải lỗi hệ thống. Theo RFC 7662, với token không hoạt động hoặc không được biết đến/không được phép công bố thông tin cho caller, AS thường trả **active=false** mà không tiết lộ thêm metadata token.

**HTTP 401** từ introspection endpoint thường có ý nghĩa **Resource Server/introspection caller không xác thực được**, hoàn toàn khác việc token của người dùng có **active=false**. Không biến mọi lỗi HTTP 401/5xx từ introspection thành một positive cache entry.

**Đặc biệt:** metadata **token_type=Bearer** mô tả phương thức sử dụng token OAuth; riêng giá trị này **không đủ** để chứng minh token là **access token thay vì refresh token**. RS cần hợp đồng phân loại token đáng tin từ AS/profile và phải từ chối token sai mục đích, kể cả khi một endpoint nào đó coi nó active.

## 3. Vì sao cache active=true tạo ra cửa sổ bảo mật?

Introspection giúp AS biết token đã bị thu hồi, bị vô hiệu vì rủi ro hoặc mất điều kiện được cấp. Nhưng RS có thể chưa nhìn thấy thay đổi ấy nếu nó giữ một kết quả cũ trong cache.

~~~mermaid
sequenceDiagram
    participant X as Bên giữ token
    participant RS as Orders API + local cache
    participant AS as Authorization Server
    X->>RS: 10:00:00 Bearer AT1
    RS->>AS: Introspect AT1
    AS-->>RS: active=true, exp còn xa
    RS->>RS: Cache true với TTL 30 phút (không an toàn)
    Note over AS: 10:02:00 AT1 bị thu hồi
    X->>RS: 10:05:00 dùng lại AT1
    RS->>RS: Cache hit active=true (stale)
    RS-->>X: Có nguy cơ cho truy cập nếu policy khác cũng qua
    Note over RS: Chỉ đến 10:30:00 cache mới hết hạn
    RS->>AS: Introspect lại AT1
    AS-->>RS: active=false
    RS-->>X: Reject
~~~

Độ dài cửa sổ phụ thuộc vào **thời điểm AS đổi trạng thái** và **thời gian entry positive còn được RS tin**, cộng thêm các yếu tố như replication, clock skew, refresh-ahead và invalidation trễ. Với cache kiểu TTL không gia hạn khi hit, **cửa sổ stale tối đa do cache gây ra thường bị chặn bởi TTL còn lại**; nếu mỗi hit lại gia hạn TTL, nó có thể kéo dài hơn nhiều.

| Trường hợp | Cơ chế gây stale | Hậu quả |
|---|---|---|
| Token bị revoke lúc entry vẫn active | RS chưa hỏi lại AS | Token bị đánh cắp có thể tiếp tục được chấp nhận |
| Tài khoản bị disable | AS cập nhật trạng thái/grant nhưng RS giữ cache | Quyền bị cấm chưa được thực thi ngay |
| Scope/grant bị thu hẹp | Cached metadata còn scope rộng | RS có thể cho phép hành động theo scope cũ |
| AS khóa client vì vi phạm | Entry gắn client vẫn hợp lệ ở RS | Client có thể tiếp tục gọi API đến khi revalidate |
| RS dùng sliding TTL | Mỗi request gia hạn entry active | Traffic của attacker giữ trạng thái cũ rất lâu |
| Distributed cache không nhận invalidation | Một số RS nodes còn active cũ | Truy cập trái chính sách không đồng đều giữa nodes |

**Cache active là tối ưu hiệu năng với chi phí về freshness; nó không được tự trở thành nguồn chân lý của việc thu hồi.**

## 4. Không có TTL đúng cho mọi hệ thống

Việc chọn TTL là quyết định **risk-based**, không thể áp một con số cho mọi token, API và tổ chức.

| Bối cảnh | Đặc tính rủi ro | Hướng lựa chọn |
|---|---|---|
| Đọc dữ liệu công khai ít nhạy cảm qua API nội bộ | Chi phí replay thấp hơn | TTL ngắn có thể được chấp nhận sau đánh giá |
| Xem dữ liệu cá nhân | Có nguy cơ lộ thông tin | TTL ngắn, kiểm scope/audience và quyền hiện hành |
| Thanh toán, đổi mật khẩu, thao tác admin | Hậu quả khi revoke trễ cao | Cân nhắc **không cache active** hoặc yêu cầu kiểm trạng thái mới |
| Access token rất ngắn hạn | Token gần exp | TTL không được vượt thời điểm hết hạn |
| AS có nguồn sự kiện revoke đáng tin | Có thể chủ động xóa entry | Kết hợp event invalidation **và** TTL làm giới hạn dự phòng |
| AS chưa có sự kiện invalidation | Chỉ dựa vào polling lại | TTL phải phản ánh tối đa độ trễ revoke chấp nhận được |

Ví dụ **policy minh họa**, không phải thời hạn RFC bắt buộc:

~~~yaml
introspectionCachePolicy:
  positiveMaxTtlSeconds: 20
  negativeMaxTtlSeconds: 0
  expiresAtSafetyMarginSeconds: 3
  highRiskOperationsBypassPositiveCache: true
  slidingExpiration: false
  staleWhileRevalidateForActive: false
~~~

Không hiểu **20 giây** là “chuẩn RFC 7662”; đó chỉ là một phương án vận hành cần thử nghiệm. Đội an ninh nên xác định **mục tiêu độ trễ thu hồi (revocation freshness SLO)**, ví dụ một thao tác có rủi ro cao phải nhận biết token đã revoke trong thời gian rất ngắn, rồi chọn TTL, invalidation và cách xử lý lỗi tương ứng.

**Không dùng thời hạn access token như TTL cache mặc định.** Một access token có **exp còn một giờ** không có nghĩa được cache **active=true một giờ**: token có thể bị thu hồi ngay ở giây tiếp theo.

## 5. Tính TTL an toàn: giới hạn bởi exp và chính sách riêng

Theo **RFC 7662**, nếu introspection response có **exp**, cache **không được giữ kết quả vượt thời điểm exp**. Nhưng **exp chỉ là trần cứng, không phải TTL nên sử dụng**.

Đối với một positive entry đã được xác minh đầy đủ, có thể xác định:

\[
TTL_{\mathrm{positive}} =
\max\left(0,\ \min\left(T_{\mathrm{policy}},\
T_{\mathrm{exp}} - T_{\mathrm{now}} - \Delta_{\mathrm{safety}}\right)\right)
\]

Trong đó:

- **T_policy:** TTL dương tối đa được phê duyệt, ví dụ 20 giây.
- **T_exp:** thời điểm hết hạn access token từ AS, thường ở dạng **NumericDate: số giây Unix epoch**.
- **T_now:** thời điểm hiện tại trên đồng hồ RS đã đồng bộ.
- **Δ_safety:** biên an toàn cho clock skew, xử lý request và làm tròn thời gian.

Ví dụ với **T_policy=20 giây, safety=3 giây**:

| Token còn đến exp | TTL cache active tối đa tính theo ví dụ | Lý do |
|---|---:|---|
| 1 giờ | **20 giây** | Trần riêng của chính sách quan trọng hơn exp |
| 15 giây | **12 giây** | Không cho entry sống quá sát exp |
| 6 giây | **3 giây** | Cửa sổ còn lại rất ngắn |
| 2 giây | **0 giây** | Không lưu positive entry |
| Đã quá hạn | **0 giây**, không cho truy cập | Token đã hết hiệu lực |

### Nếu introspection không trả exp?

RFC 7662 cho phép một số metadata là tùy chọn. Khi thiếu **exp**, RS **không thể lấy hết hạn token để tính trần**. Với chính sách nghiêm ngặt, nên **không cache positive** trừ khi hợp đồng AS–RS có nguồn hết hạn đáng tin và giới hạn cache riêng được phê duyệt. Không đặt TTL vô hạn, không dùng **“1 ngày nếu không biết exp”**.

### Đọc đúng thời gian

- NumericDate dùng **giây**, không mặc định mili giây.
- Không coi một timestamp nằm ở tương lai là thời hạn tồn tại mới nếu đồng hồ RS sai.
- Không làm tròn TTL thành một phút khi token còn 4 giây.
- Khi đã đưa entry vào cache, dùng **absolute/fixed expiration**, không gia hạn mỗi lần cache hit.
- Cần kiểm **exp của token trên mỗi request**, kể cả cache còn trả positive do race hoặc đồng hồ.
- Nếu AS gửi chỉ thị cache **no-store** hoặc hợp đồng không cho phép lưu, phải tuân thủ chính sách cache đó.

**Sai lầm cần loại bỏ:** dùng **min(exp, 24h)** rồi giữ active tới exp. Công thức đúng phải chứa **trần TTL ngắn riêng cho trạng thái active**.

## 6. Ba mức thời gian không được nhập nhằng

Trong vận hành thường có ít nhất ba thời gian khác nhau:

~~~text
Token lifetime:
  iat ----------------------------- exp

One introspection result lifetime:
            introspected -> cache expires

Authorization policy freshness:
              user/role/tenant permissions may change at any time
~~~

**Token lifetime**: access token được phát và có thời hạn. Dù chưa đến exp, token vẫn có thể bị revoke nếu AS/RS hỗ trợ trạng thái thu hồi.

**Introspection cache TTL**: thời gian RS dùng lại một kết quả **active và metadata** tại một thời điểm. TTL này phải **ngắn hơn hoặc bằng thời gian còn lại của token**, nhưng còn cần ngắn hơn theo risk policy.

**Business authorization freshness**: nếu user bị gỡ khỏi tenant hoặc quyền xem một đơn hàng bị hủy, policy có thể yêu cầu kiểm dữ liệu hiện hành **mỗi request**, kể cả access token và cached introspection vẫn active. Cache active không được dùng thay quyền **ownership/tenant membership** khi rủi ro yêu cầu kiểm lại.

Một thiết kế có thể **cache active 10 giây** nhưng vẫn **đọc quyền đối tượng mỗi request**, hoặc **không cache active** với thao tác chuyển tiền. Không cần biến mọi bài toán thành TTL thấp nhất, nhưng phải xác định đúng thứ cần fresh.

## 7. Positive cache và negative cache có rủi ro khác nhau

**Positive cache** lưu kết quả **active=true** và metadata liên quan. Rủi ro chính là **tiếp tục chấp nhận token đã bị revoke hoặc quyền đã bị thu hẹp**.

**Negative cache** lưu kết quả **active=false**. Nó không tạo quyền truy cập trái phép nếu được thực hiện đúng, nhưng có thể từ chối nhầm một token hợp lệ khi trạng thái vừa thay đổi, chẳng hạn do độ trễ đồng bộ, quá trình cấp phát mới hoặc sự nhất quán giữa các vùng.

| Kiểu kết quả | Có nên cache? | Hướng dẫn |
|---|---|---|
| **active=true**, đủ claims và AS/RS contract | Có thể cache **ngắn, fixed TTL**, không vượt exp | Cần đánh giá revoke freshness |
| **active=false** | Thường không cache hoặc TTL cực ngắn theo policy | Không làm trì hoãn việc token vừa mới trở nên hợp lệ khi hệ thống có tính eventual consistency |
| **401 invalid introspection client** | **Không** cache như inactive/active | Sửa xác thực giữa RS và AS |
| **5xx / timeout / network failure** | **Không** cache như active=true; không coi là token bị revoke | Xử lý dependency unavailable, thường fail closed |
| **Response thiếu active hoặc JSON sai schema** | Không đưa vào cache | Coi là lỗi giao thức/nguồn tin cậy |
| **active=true nhưng issuer/audience/type không hợp lệ** | Không lưu như positive credential được phép | Từ chối request và điều tra hợp đồng AS–RS |

**Không áp dụng cùng TTL cho cả positive và negative cache chỉ vì hai response đều HTTP 200.** Thông tin cache phải gắn với **giá trị active thật và các kiểm tra đã được thực hiện**, không chỉ status code.

Nếu tổ chức chọn cache **active=false** vài giây để giảm dò token hoặc giảm tải AS, cần kiểm thử rõ độ trễ cấp phát/replication và khả năng gây **denial of service** với người dùng hợp lệ. Khi không có lý do cụ thể, **không cache negative** là mặc định dễ giải thích.

## 8. Cache key phải đại diện đúng trust context

Một cache keyed chỉ bằng **user ID** hoặc **client_id** là sai: một user/client có thể giữ **nhiều access tokens** với audience, scope, thời hạn, grant và trạng thái khác nhau. Thu hồi token A không có nghĩa token B bị thu hồi, và **active của token A không chứng minh token B active**.

Một positive cache key logic có thể bao gồm:

~~~text
namespace / environment
trusted_authorization_server_id / issuer
introspection_client_id (identity của Resource Server đang hỏi)
resource_server_id / expected_audience
token_fingerprint
policy_or_contract_version (nếu ảnh hưởng metadata trả về)
~~~

**token_fingerprint** nên là giá trị dẫn xuất bằng **HMAC-SHA-256 với khóa bí mật của hệ thống** từ **nguyên chuỗi token chính xác**, không phải raw bearer token:

~~~text
cacheKey =
    "intro:v1:" +
    issuerId + ":" +
    introspectionCallerId + ":" +
    resourceServerId + ":" +
    HMAC_SHA256(cacheKeySecret, rawAccessToken)
~~~

Đây là thiết kế minh họa, không phải format bắt buộc của RFC 7662. HMAC làm giảm khả năng cache key trở thành bản sao bearer credential nếu key/metrics bị lộ; **khóa HMAC phải được bảo vệ**. Hash không có secret có thể vẫn là định danh liên kết người dùng/token, cần đánh giá theo threat model và retention.

### Vì sao context matters?

AS có thể **lọc hoặc điều chỉnh introspection response theo caller**. Cùng một token, RS-A có thể được phép nhìn metadata khác RS-B. Nếu cả hai dùng một cache entry chung theo token string, RS-B có thể nhận scope/subject không được phép công bố, hoặc dùng một kết quả active không hợp lệ cho chính audience của nó.

**Cache key không tự kiểm audience**. Dù khóa cache có chứa **resourceServerId**, RS vẫn phải **kiểm aud/resource binding** trong response hoặc theo hợp đồng đã được AS xác thực. Nếu AS không trả audience, cần **hợp đồng đáng tin rằng introspection authorization thực sự ràng buộc token với RS này**; không tự suy active=true có nghĩa token dùng được ở mọi API.

### Những điều không nên làm

- Không dùng toàn bộ bearer token làm **Redis key, log label, metric tag** hoặc URL.
- Không dùng một cached result cho **toàn hệ thống nhiều issuer** nếu cùng chuỗi token xuất hiện.
- Không dùng token_type_hint làm bằng chứng token là access token.
- Không mở cache chung giữa production và staging.
- Không serialize toàn bộ metadata nhạy cảm vào cache không được phân quyền/mã hóa phù hợp.
- Không biến mỗi request thành một cache entry khác nhau do thêm ngẫu nhiên request ID vào key; hãy cache theo **trust context ổn định** đã xác định.

## 9. JWT và opaque access token: cần cache gì?

**Opaque access token** thường buộc RS hỏi AS hoặc nguồn trạng thái tin cậy để biết token còn hoạt động và có quyền gì. Cache ngắn có thể giúp giảm latency, nhưng làm tăng độ trễ nhận biết revoke.

**JWT access token tự chứa** cho phép RS kiểm chữ ký, **iss, aud, exp, nbf** và các claims theo profile tại chỗ. RS có thể không gọi introspection cho mỗi JWT, nhưng khi hệ thống yêu cầu **thu hồi sớm**, có thể dùng introspection, revocation lookup, denylist hoặc token/grant epoch tùy thiết kế.

| Token | Điều có thể kiểm tại RS | Rủi ro freshness |
|---|---|---|
| **Opaque access token** | Introspection/nguồn trạng thái; scope/aud/policy | Positive cache stale sau AS revoke |
| **JWT access token** | Chữ ký, issuer, audience, thời hạn, claims | JWT có thể vẫn valid về chữ ký/exp sau revoke nếu không có trạng thái cập nhật |
| **Refresh token** | **Không** phải access token của RS | Phải gửi về AS/token endpoint; RS từ chối sai mục đích |
| **OIDC ID token** | Dành cho OIDC client xác minh đăng nhập | RS không nhận làm access token dù JWT ký hợp lệ |

**Không dùng TTL ngắn để chữa validation sai.** JWT đúng chữ ký nhưng **aud sai**, opaque token active nhưng không dành cho API, hoặc ID token bị gửi làm Bearer phải bị từ chối **ngay**, không phải “cache trong 5 giây rồi xem sao”.

Với self-contained JWT, **caching việc parse/chữ ký** và **caching trạng thái revoke/introspection** là hai loại tối ưu khác nhau. Nếu RS cache một kết quả “authorized=true” bao gồm cả policy tài nguyên, rủi ro stale còn lớn hơn và cache key cũng phải phản ánh resource/action/policy, thường không phù hợp. Ưu tiên cache **evidence của token** ngắn hạn và chạy **policy evaluation** riêng.

## 10. Mỗi request vẫn phải kiểm những gì khi cache hit?

Một cache hit active=true **không phải quyết định Allow cuối cùng**.

~~~mermaid
flowchart TD
    A["API nhận Bearer token"] --> B{"Token format/transport hợp lệ?"}
    B -->|Không| X["Reject"]
    B -->|Có| C["Tạo cache key theo issuer/RS/caller/token HMAC"]
    C --> D{"Có positive entry còn TTL?"}
    D -->|Có| E["Dùng metadata đã được xác minh"]
    D -->|Không| F["Introspect qua TLS tới AS tin cậy"]
    F --> G{"HTTP/giao thức/active hợp lệ?"}
    G -->|Không| X
    G -->|Có| H["Kiểm issuer, audience, loại token, exp, nbf"]
    H --> I["Có thể lưu positive ngắn, fixed TTL"]
    I --> E
    E --> J{"Token còn hạn, đúng scope/audience/client context?"}
    J -->|Không| X
    J -->|Có| K{"Current resource/tenant policy cho phép?"}
    K -->|Không| X
    K -->|Có| L["Allow request"]
~~~

Các bước **tối thiểu** tùy hợp đồng token:

1. Chỉ chấp nhận **access token** ở API; không thay bằng ID token, refresh token hay authorization code.
2. Xác định AS/issuer **từ cấu hình tin cậy**, không từ trường chưa xác minh trong token.
3. Chỉ dùng cached entry nếu **đúng token và đúng trust context** và TTL chưa hết.
4. Kiểm **exp/nbf** theo dữ liệu từ nguồn tin cậy hoặc profile; từ chối token hết hạn dù cache entry còn tồn tại do lỗi.
5. Kiểm **audience** đúng RS và **scope** đủ cho API method.
6. Kiểm **client/subject/tenant** và **object-level authorization** theo policy hiện hành khi cần.
7. Không trả một Allow được cache từ lần đọc **order-1** cho request đọc **order-2** chỉ vì cùng token.

**Active=true trả lời trạng thái token**, không trả lời “user có được xóa order-99?”.

## 11. Token revocation và cache invalidation phải đi cùng nhau

Khi một access token bị **thu hồi trực tiếp**, AS có thể cập nhật trạng thái introspection **active=false**. Nhưng trạng thái mới chỉ tới RS nếu RS hỏi lại hoặc có cơ chế thông báo đáng tin.

~~~mermaid
sequenceDiagram
    participant U as User/Admin
    participant AS as Authorization Server
    participant E as Event channel
    participant RS as Resource Server + Cache
    U->>AS: Revoke token AT1
    AS->>AS: Commit trạng thái revoked
    AS-->>U: Xác nhận theo nghiệp vụ
    AS->>E: Publish token/grant invalidation sau commit
    E-->>RS: Invalidate token fingerprint / grant epoch
    RS->>RS: Xóa entry active liên quan
    Note over RS: Entry hết TTL vẫn là safety bound nếu event mất
    RS->>AS: Request kế tiếp introspect lại
    AS-->>RS: active=false
    RS-->>U: Từ chối token bị revoke
~~~

**Event invalidation là tăng tốc freshness, không được dùng làm lý do đặt TTL vô hạn**. Event có thể mất, bị trễ, chạy sai thứ tự, bị queue redelivery hoặc không đến một RS node. TTL ngắn vẫn là **giới hạn dự phòng**; để có bảo đảm thu hồi tức thì ở thao tác nhạy cảm, RS phải có nguồn trạng thái nhất quán/phương án kiểm lại phù hợp.

### Phân biệt các loại thu hồi

| Sự kiện | Hệ quả lên token | Điều cache phải biết |
|---|---|---|
| Revoke **chính AT1** | AT1 không còn active theo AS policy | Xóa cache của **AT1**, không chỉ cache theo user |
| Revoke **refresh token RT1** | Không cho tiếp tục xin AT mới từ RT1/grant | **Không mặc nhiên** làm AT đã cấp thành inactive nếu AS chưa thu hồi AT ấy |
| Revoke **authorization grant** | Có thể vô hiệu hóa các token liên quan tùy AS | Phải hiểu lineage và invalidation policy |
| User logout khỏi browser | Kết thúc một login session | Không đồng nghĩa mọi OAuth access token/refresh token bị revoke |
| Client bị disable | AS có thể chặn token mới và token hiện hành theo policy | RS cần biết trạng thái token/grant nếu yêu cầu revoke sớm |
| Signing key AS bị xâm phạm | Mất gốc tin cậy với JWT do key đó ký | Cần xử lý issuer/key trust, không chỉ xóa một token cache entry |

**RFC 7009** nói về token revocation endpoint; **RFC 7662** nói về introspection. Đó là hai khả năng có liên quan nhưng không đồng nhất. Khi xét stale cache phải biết **AS thực sự đã làm token đó inactive hay chỉ vô hiệu khả năng refresh trong tương lai**.

## 12. Event invalidation trong cụm nhiều Resource Servers

Một cụm RS có thể gồm nhiều ứng dụng, nhiều instance và cache nhiều tầng:

~~~text
API gateway cache
    |
    +-- Orders API node A: in-memory cache
    +-- Orders API node B: in-memory cache
    +-- Orders API node C: in-memory cache
                |
                +-- Optional shared Redis cache
~~~

Khi AS phát sự kiện revoke, một instance xóa entry nhưng instance khác không nhận sự kiện vẫn có thể tiếp tục chấp nhận token trong TTL còn lại.

Biện pháp kỹ thuật:

- **Versioned invalidation / grant epoch**: nếu policy thay đổi theo grant, gắn thông tin phiên bản/trạng thái với cache và cập nhật theo nguồn đáng tin khi áp dụng.
- **Outbox pattern**: ghi event sau trạng thái revoke bằng cơ chế nhất quán để giảm nguy cơ commit revoke nhưng mất thông báo.
- **Idempotent handlers**: lặp sự kiện revoke không được làm trạng thái trở lại active.
- **Event ordering**: một event “active” cũ không được ghi đè trạng thái revoked mới; dùng revision/epoch tăng đơn điệu khi có.
- **Cache namespaces**: tránh gửi invalidation của staging sang production hoặc của issuer A sang issuer B.
- **Hard TTL**: entry active hết hạn dù event chưa tới.
- **No sliding renew**: một cache hit không kéo dài trạng thái active.

### Cẩn thận với stale repopulation

Một race tinh vi:

~~~text
T0: RS request R1 bắt đầu introspection cho AT1.
T1: AS revoke AT1 và gửi sự kiện xóa cache.
T2: RS nhận event, xóa entry AT1.
T3: Response active=true cũ của R1 tới muộn.
T4: RS ghi active=true trở lại cache.
~~~

Chỉ “xóa cache khi nhận event” chưa đủ nếu request introspection đang chạy có thể **repopulate bằng dữ liệu cũ**. Có thể dùng **generation/revision fence**, token/grant revoke epoch hoặc kiểm trạng thái mới trước khi chấp nhận response cũ. Nếu không có cơ chế phân biệt phiên bản, **TTL cứng ngắn** vẫn chặn một phần rủi ro, nhưng không đáp ứng yêu cầu **zero-stale after event**.

**Phân biệt sự kiện tin cậy với tín hiệu do client gửi.** Không cho một request HTTP tùy ý mang “invalidate token X” rồi xóa cache toàn hệ thống; kênh invalidation cần xác thực nguồn, phân quyền và chống abuse.

## 13. Bảo vệ chính introspection endpoint và dữ liệu cache

Một API có thể tính TTL rất ngắn nhưng vẫn không an toàn nếu nó hỏi **sai Authorization Server**, dùng introspection credentials bị lộ hoặc tin response do attacker giả mạo.

### Đường truyền và danh tính caller

1. RS dùng **URL introspection endpoint từ cấu hình issuer/metadata tin cậy**, không lấy URL chưa xác minh từ JWT hoặc request của client.
2. Gọi endpoint qua **TLS** và xác minh chứng thư/server identity.
3. RS **xác thực** với AS bằng phương thức được đăng ký và được phép; có thể là client credentials, mTLS hoặc cơ chế cụ thể của hệ thống.
4. AS kiểm **caller có quyền introspect loại token/tài nguyên ấy không**, không trả thông tin cho client bất kỳ chỉ vì người đó biết token.
5. Không đưa raw token vào **query string** hoặc header/log debug không được bảo vệ; request thông thường dùng **form body** theo RFC 7662.
6. Không trả metadata nhạy cảm quá mức cho caller; áp dụng nguyên tắc **least disclosure** nếu profile/AS hỗ trợ.

**Token introspection response có thể mang sub, client_id, scope, aud và timestamps**, tức là dữ liệu cần được bảo vệ về quyền riêng tư và truy cập. Cache lưu response đó cũng phải có ACL, mã hóa tại rest khi cần, TTL/retention và audit phù hợp. Không gửi các field này thành metric labels có cardinality cao hoặc chứa thông tin cá nhân.

### Bảo vệ nguồn khóa và danh tính issuer

Nếu hệ thống đồng thời chấp nhận JWT từ nhiều issuer, không được để metadata **iss** do token chưa verify tự định tuyến đến một introspection URL tùy ý. Cần có **issuer allowlist**, mapping resource/tenant tin cậy và lựa chọn AS theo hợp đồng. Tránh SSRF qua URL tự khai hoặc tải JWKS từ nguồn chưa xác minh.

### Lỗi quyền introspection khác lỗi access token

Ví dụ RS gửi credential introspection bị thu hồi:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

Đây là ví dụ; error schema có thể khác theo AS/profile. **Đừng biến HTTP 401 của endpoint introspection thành active=false để rồi cache âm hàng giờ**: cần ghi nhận **AS dependency authentication failure**, từ chối dựa trên token không thể xác minh và sửa cấu hình/credential. Cũng không được lấy cached positive entry cũ để “qua mặt” việc không còn được phép introspect.

## 14. Khi Authorization Server chậm hoặc không truy cập được

Đây là tình huống dễ sinh **fail-open**:

~~~text
if introspectionTimeout:
    allowBecauseTokenLookedActiveYesterday()
~~~

Đó là hành vi nguy hiểm: kẻ tấn công có thể duy trì token đã bị thu hồi bằng cách tận dụng lỗi hạ tầng, hoặc hệ thống tự kéo dài quyền vô thời hạn khi AS không khả dụng.

### Chính sách mặc định nên fail closed

Nếu RS **không có positive result còn hợp lệ theo TTL và đúng trust context**, nhưng không thể kiểm tra AS, **không cho phép truy cập chỉ dựa vào token chưa xác minh**. RS có thể trả phản hồi phù hợp như **503 Service Unavailable** khi phụ thuộc xác thực tạm lỗi, thay vì đánh đồng outage với credential sai. HTTP code chính xác tùy gateway/framework; điều quan trọng là **không thực hiện hành động được bảo vệ**.

| Trạng thái | Hành vi an toàn |
|---|---|
| Cache hit **active=true**, TTL chưa hết, policy cho dùng cache | Có thể tiếp tục kiểm claims/quyền nghiệp vụ, theo mức rủi ro đã duyệt |
| Cache miss, AS trả **active=true** hợp lệ | Kiểm audience/type/scope/exp; lưu positive ngắn nếu được phép |
| Cache miss, AS trả **active=false** | Từ chối; negative cache chỉ theo policy rất ngắn hoặc không cache |
| Cache miss, AS timeout/5xx | **Không cho request qua**; trả lỗi dependency phù hợp, có retry giới hạn |
| Cache positive đã hết TTL, AS timeout | **Không dùng stale entry** theo mặc định |
| AS trả response thiếu active hoặc metadata không đủ | Không tự đoán true; từ chối/ghi lỗi giao thức |
| AS/issuer certificate hoặc introspection credential không hợp lệ | Fail closed; không fallback sang endpoint không tin cậy |

### Có bao giờ được dùng stale khi outage?

Một số hệ thống có thể đặt yêu cầu availability đặc biệt, chẳng hạn một chức năng ít nhạy cảm phục vụ nội dung đã cache, nhưng việc **cho phép truy cập bằng stale active** là **ngoại lệ an ninh**, không phải mặc định. Nếu tổ chức thật sự chấp thuận, phải ghi rõ **phạm vi API**, **TTL stale tối đa**, **điều kiện bật/tắt**, **đánh giá replay/revocation**, **nguồn quyết định** và **kiểm thử sự cố**. Không áp dụng tùy tiện cho thanh toán, đổi quyền, dữ liệu cá nhân hoặc thao tác quản trị.

**Circuit breaker** có thể giảm tải khi AS lỗi, nhưng không được biến thành **“AS down ⇒ allow”**. Bulkhead, timeout ngắn và backoff giúp bảo vệ tài nguyên hệ thống; **chúng không thay thế trạng thái token**.

## 15. Chống cache stampede mà không kéo dài quyền

Nếu một access token được dùng với tần suất cao, TTL 10–20 giây có thể làm nhiều request đồng thời phát hiện cache miss và cùng gọi introspection. Đây là **thundering herd/cache stampede**.

Một phương án:

~~~text
request A --> cache miss ---+
request B --> cache miss ----> single-flight theo cache key --> AS introspect
request C --> cache miss ---+                                 |
                                                             v
                                                Một response verified
                                                             |
                        +------------------------------------+
                        |            |            |
                      A dùng       B dùng        C dùng
                      cùng result trong ngữ cảnh trust hợp lệ
~~~

**Single-flight** chỉ gộp các yêu cầu **đang kiểm cùng token và cùng trust context**. Nó **không** có nghĩa cache response vô hạn hoặc cho phép các request chờ vì một token mới gửi vào thành request đã xác thực của token khác.

Các kỹ thuật hiệu năng có thể kết hợp:

- **Bounded in-flight coalescing**: giới hạn số request đang chờ mỗi key và tổng số key, tránh dùng memory không kiểm soát.
- **Connection pooling** và TLS session reuse phù hợp.
- **Short, bounded cache** với trần memory và eviction.
- **Throttling/rate limiting** cho token sai/ngẫu nhiên để tránh AS bị dùng làm oracle.
- **Backpressure** và giới hạn concurrent introspection khi AS chậm.
- **Per-RS local cache** thay vì shared cache quá rộng nếu cần cô lập security context.
- **Batching** chỉ khi endpoint/profile có hợp đồng rõ; không tự gửi nhiều token trong một request RFC 7662 chuẩn đơn token.

### Vì sao refresh-ahead/stale-while-revalidate cần cẩn trọng?

Một thư viện cache thường hỗ trợ **stale-while-revalidate**: trả ngay dữ liệu cũ và gọi AS làm mới trong nền. Với nội dung công khai, hành vi này có thể chấp nhận. Với **active=true**, nó có thể **tiếp tục cho phép token đã bị thu hồi** trong lúc revalidate.

Không bật stale-while-revalidate cho trạng thái **active** chỉ vì tùy chọn ấy tốt cho CDN. Nếu muốn **prefetch trước khi TTL hết**, hãy cập nhật từ **response mới đã xác minh**, giữ một **hard maximum age** và không gia hạn entry từ chính cache hit. Nếu việc kiểm tra mới thất bại, không được “refresh TTL” cho dữ liệu cũ.

**Độ trễ AS tăng không phải lý do tự động tăng TTL active.** Tối ưu kiến trúc introspection, kết nối, cache coalescing hoặc kiến trúc token phù hợp thay vì nới cửa sổ lạm dụng credential.

## 16. Java: hàm tính TTL đúng exp và policy

Ví dụ dưới đây minh họa **tính thời gian sống dương cho cache**, giả định introspection response đã được kiểm tra schema, nguồn AS, loại token, audience và scope theo hợp đồng. Dùng **Java 17+**, thời gian được cung cấp từ clock testable.

~~~java
import java.time.Duration;
import java.time.Instant;

public final class IntrospectionCacheTtl {
    private IntrospectionCacheTtl() {}

    public static Duration positiveTtl(
            boolean active,
            Long expEpochSeconds,
            Instant now,
            Duration policyMaximum,
            Duration safetyMargin
    ) {
        // Không cache inactive, response không có exp hoặc policy vô hiệu.
        if (!active || expEpochSeconds == null
                || policyMaximum.isZero() || policyMaximum.isNegative()) {
            return Duration.ZERO;
        }
        if (safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Negative safety margin");
        }

        Instant expiresAt;
        try {
            expiresAt = Instant.ofEpochSecond(expEpochSeconds);
        } catch (RuntimeException invalidTimestamp) {
            return Duration.ZERO;
        }

        // Trừ trước safety margin: không nhận kết quả quá gần exp.
        Duration remaining = Duration.between(now.plus(safetyMargin), expiresAt);
        if (remaining.isZero() || remaining.isNegative()) {
            return Duration.ZERO;
        }
        return remaining.compareTo(policyMaximum) < 0
                ? remaining
                : policyMaximum;
    }
}
~~~

### Kiểm thử hàm TTL

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class IntrospectionCacheTtlTest {
    private final Instant now = Instant.ofEpochSecond(1_800_000_000L);
    private final Duration policyMax = Duration.ofSeconds(20);
    private final Duration margin = Duration.ofSeconds(3);

    @Test
    void longLivedTokenStillUsesShortPolicyTtl() {
        assertEquals(Duration.ofSeconds(20),
            IntrospectionCacheTtl.positiveTtl(
                true, now.getEpochSecond() + 3600,
                now, policyMax, margin));
    }

    @Test
    void expBeforePolicyLimitTightensTtl() {
        assertEquals(Duration.ofSeconds(12),
            IntrospectionCacheTtl.positiveTtl(
                true, now.getEpochSecond() + 15,
                now, policyMax, margin));
    }

    @Test
    void tooCloseToExpirationDoesNotCache() {
        assertEquals(Duration.ZERO,
            IntrospectionCacheTtl.positiveTtl(
                true, now.getEpochSecond() + 2,
                now, policyMax, margin));
    }

    @Test
    void inactiveOrNoExpiryIsNotPositiveCached() {
        assertEquals(Duration.ZERO,
            IntrospectionCacheTtl.positiveTtl(
                false, now.getEpochSecond() + 3600,
                now, policyMax, margin));
        assertEquals(Duration.ZERO,
            IntrospectionCacheTtl.positiveTtl(
                true, null, now, policyMax, margin));
    }
}
~~~

Đây là **unit test của phép tính TTL**, không phải test kiểm chứng AS đã revoke token. Hãy chạy thêm integration tests với **introspection endpoint thật trong môi trường test** để chứng minh RS bỏ entry stale đúng thời hạn và không nâng quyền từ positive cache.

### Chi tiết triển khai cần nhớ

- **expEpochSeconds** phải lấy từ **introspection response đáng tin** và được parse đúng kiểu số, không lấy từ phần payload JWT do client tự decode.
- Hàm không tự kiểm issuer, audience, token purpose hay scope; các điều kiện ấy phải được kiểm trước khi tạo positive cache entry.
- Nếu **exp thiếu**, ví dụ chọn không cache. Một hệ thống khác có thể có hợp đồng riêng nhưng phải giữ hard TTL ngắn và đủ nguồn tin cậy.
- Khi lưu vào cache, dùng TTL như **fixed expiration từ lúc response được xác minh**. Nếu thư viện có chính sách **expireAfterAccess**, không dùng nó thay cho **expireAfterWrite/absolute expiration** ở active cache.
- Phép tính thời gian có thể dùng đồng hồ hệ thống lúc tạo TTL rồi triển khai **monotonic clock** để đo tuổi entry; tránh gia hạn vì wall clock bị điều chỉnh.
- Cache TTL ở Redis có thể làm tròn theo giây; khi token sắp exp, ưu tiên **không cache** hơn là làm tròn lên vượt trần.

## 17. Java: không trả Allow trực tiếp từ cached active

Pseudocode Java kiểu service cho Resource Server:

~~~java
// PSEUDOCODE: interfaces và các kiểu được giả định tồn tại.
// Chỉ minh họa trật tự kiểm tra, không phải thư viện OAuth hoàn chỉnh.

public AuthorizationDecision authorize(
        HttpRequest request,
        ProtectedResource resource
) {
    String bearer = extractBearerWithoutLogging(request);
    TrustedIssuerConfig issuer = issuerRouter.resolveFromTrustedConfiguration(
        request, resource
    );

    CacheKey key = cacheKeyFactory.hmacKey(
        issuer.id(),
        introspectionCaller.identity(),
        resource.expectedAudience(),
        bearer
    );

    VerifiedTokenMetadata token = positiveCache.getIfFresh(key);
    if (token == null) {
        IntrospectionResponse response =
            introspectionClient.postToTrustedEndpoint(issuer, bearer);

        if (!response.isValidProtocolResponse() || !response.isActive()) {
            return AuthorizationDecision.reject();
        }
        token = tokenVerifier.verifyTrustedIntrospectionResult(
            issuer, resource.expectedAudience(), response
        );

        Duration ttl = ttlPolicy.positiveTtl(
            token.isActive(),
            token.expEpochSeconds(),
            clock.instant(),
            Duration.ofSeconds(20),
            Duration.ofSeconds(3)
        );
        if (!ttl.isZero()) {
            positiveCache.putFixedTtl(key, token, ttl);
        }
    }

    // Bắt buộc cả trên cache hit:
    if (!token.isAccessTokenFor(resource)
            || token.isExpired(clock.instant())
            || !token.hasRequiredScope(request.operation())) {
        return AuthorizationDecision.reject();
    }
    if (!currentAuthorizationPolicy.mayAccess(
            token.subject(), token.clientId(),
            resource.tenant(), resource.objectId(),
            request.operation())) {
        return AuthorizationDecision.reject();
    }
    return AuthorizationDecision.allow();
}
~~~

**Các kiểu và API trong ví dụ không tồn tại sẵn**: cần dùng OAuth/RS framework được duy trì. Đặc biệt, **isAccessTokenFor(resource)** đòi AS–RS contract để phân biệt token purpose và audience; **isActive()** là dữ liệu nguồn AS đã kiểm, không phải boolean do client gửi. **introspectionClient** phải xử lý mạng 401/5xx/timeout tách biệt với response **active=false**; không tự gọi **reject()** theo cách khiến operation bị coi là thiếu quyền vĩnh viễn khi AS chỉ đang outage.

### HMAC cache fingerprint bằng Java

~~~java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public static String tokenFingerprint(byte[] hmacKey, String rawToken)
        throws Exception {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
    byte[] digest = mac.doFinal(
        rawToken.getBytes(StandardCharsets.UTF_8)
    );
    return HexFormat.of().formatHex(digest);
}
~~~

Đoạn hàm độc lập ở trên **cần đặt trong class** khi sử dụng. **hmacKey** phải được cấp từ secret/key management an toàn, không hard-code trong source code, không đặt trong cache key. Fingerprint chỉ là **một thành phần** của cache key; cần namespace issuer, environment, caller và resource context. Dữ liệu cache vẫn có thể nhạy cảm ngay cả khi không lưu raw bearer token.

### Khi AS trả active=false

Hãy từ chối token và xóa positive entry liên quan nếu có. **Không giữ một entry active=true cũ vì AS chỉ vừa trả active=false.** Với invalidation event đáng tin, cũng phải ngăn request introspection cũ đến muộn ghi lại true.

## 18. Đừng cache toàn bộ quyền nghiệp vụ cùng active

Một lỗi thường gặp trong API:

~~~text
cache[token] = {
  active: true,
  canReadAnyOrder: true
}
~~~

Nếu user được cho đọc **order-1** tại thời điểm 10:00, điều đó **không chứng minh** họ được xem **order-2**, hoặc vẫn thuộc tenant-A tại 10:05. Dùng một cached **authorization result** không có resource/action/tenant context có thể tạo lỗi **Broken Object Level Authorization (BOLA)**.

### Tách hai loại cache

| Cache | Nội dung | Khuyến nghị |
|---|---|---|
| **Token introspection cache** | Trạng thái active và metadata token từ AS | TTL ngắn, issuer/RS-bound, không vượt exp |
| **Business data cache** | Dữ liệu đơn hàng hoặc nội dung response API | TTL và quyền phân phối độc lập; không dùng active để vượt authorization |
| **Authorization decision cache** | Kết quả policy theo subject, tenant, action, resource | Chỉ khi có key và invalidation đầy đủ; thường cần TTL rất ngắn hoặc không cache |
| **JWT verification key cache (JWKS)** | Public keys của AS | Quản lý theo key rotation/trust policy; **không** suy cache key TTL là token active TTL |

Một access token có **aud=orders-api, scope=orders:read** vẫn không cho phép xem đơn của tenant khác. Trong hệ thống nhạy cảm, kiểm **current membership**, trạng thái resource và ABAC/RBAC policy theo request; cache introspection chỉ cung cấp **identity/token evidence**.

**Không gia hạn cache active khi hoạt động nghiệp vụ thành công.** Việc API đọc đơn hàng 100 lần không làm token thêm thời gian hiệu lực.

## 19. Rate limiting và chi phí của TTL quá ngắn

Không cache hoặc TTL vài giây có thể tạo tải lớn lên AS. Đó là **bài toán hiệu năng thật**, không nên bỏ qua — nhưng phải giải bằng cách đo đạc thay vì kéo TTL lên 30 phút mà không có đánh giá.

### Ước lượng đơn giản

Giả sử 2.000 requests/giây vào RS, trung bình có 100 access tokens thường xuyên được sử dụng; với TTL 20 giây và cache coalescing hiệu quả, số lần introspection cho những token ấy có thể nhỏ hơn rất nhiều tổng số API requests. Nhưng nếu mỗi request mang một token **mới/ngẫu nhiên**, gần như mọi request đều cache miss.

Vì vậy:

- Theo dõi **tỷ lệ cache hit** và **số distinct token fingerprints** theo thời gian, không thu thập raw token.
- Có **rate limit** cho introspection theo caller/tenant/client và hành vi bất thường.
- Giới hạn response size, connection pool, timeout và concurrency.
- Chặn quá tải bằng **backpressure**, không bằng **allow stale**.
- Nếu AS không đáp ứng được nhu cầu, đánh giá lại kiến trúc như JWT TTL ngắn + cơ chế revocation phù hợp, hoặc một dịch vụ trạng thái tập trung có SLO xác định.

### Cẩn thận cardinality và cache eviction

Một attacker có thể gửi hàng triệu chuỗi bearer giả. Nếu RS tạo negative cache entries không giới hạn hoặc metric labels theo token, hệ thống có thể cạn bộ nhớ. **Cache size cap**, key HMAC, negative cache policy và giới hạn đầu vào là yêu cầu bảo vệ hạ tầng.

**Đừng bỏ cache validation để lấy hit rate cao.** Giá trị của cache là giảm chi phí kiểm tra lặp lại trong **cửa sổ tươi được phê duyệt**, không phải làm đẹp chỉ số cache hit.

## 20. Quan sát độ trễ thu hồi mà không log credential

Để kiểm soát “không cache quá lâu”, vận hành cần đo **freshness thực tế** chứ không chỉ cấu hình TTL:

| Chỉ số | Điều nó cho biết | Lưu ý |
|---|---|---|
| **positive_cache_ttl_configured** | Trần TTL policy đang áp dụng | Phân tách theo môi trường/API risk tier |
| **introspection_cache_hit_ratio** | Hiệu quả cache | Không phải chỉ số an ninh duy nhất |
| **active_result_age_at_use** | Tuổi kết quả active khi RS dùng nó | Theo histogram, không log token |
| **revocation_detection_latency** | Từ lúc AS commit revoke đến lúc RS từ chối | Đo trong kiểm thử/canary an toàn |
| **introspection_latency** | Độ trễ AS/đường mạng | Tách p50/p95/p99 |
| **introspection_error_rate** | 401/403/5xx/timeouts/schema errors | Không gộp active=false thành lỗi hạ tầng |
| **invalidation_delivery_lag** | Độ trễ sự kiện revoke đến các RS nodes | Phân biệt event lost và event delayed |
| **stale_repopulation_prevented** | Số response cũ bị chặn sau invalidate | Giúp phát hiện race |
| **positive_cache_entries_without_exp** | Token thiếu trần expiry | Nên không cache theo ví dụ policy |

Một sự kiện audit an toàn:

~~~json
{
  "event": "introspection_cache_entry_rejected",
  "resource_server": "orders-api",
  "issuer_ref": "auth-main",
  "reason": "POSITIVE_TTL_EXPIRED",
  "decision": "REVALIDATE_REQUIRED",
  "request_id": "req-example-331",
  "cache_entry_age_ms_bucket": "10000-20000"
}
~~~

Không đưa **raw access token**, refresh token, authorization header, introspection request body hoặc response chứa đầy đủ claims vào log/metric. Nếu cần tương quan, dùng **request ID** hoặc token fingerprint HMAC được bảo vệ, tránh đưa fingerprint vào metric label công khai.

### Khi đo freshness

Mốc **revoke committed** từ AS và **first rejected by RS** cần được đo trong điều kiện kiểm thử có thể xác nhận trạng thái. Không lấy một timestamp do browser tự khai làm bằng chứng. Đo cả tình huống **cache hit liên tục, RS đa node, event đến muộn, AS timeout và clock skew**.

## 21. Tình huống thực tế: Orders API có ba lớp kiểm tra

Giả sử:

~~~text
Authorization Server:
  issuer = https://auth.example.org

Resource Server:
  orders-api
  yêu cầu scope orders:read

Access token opaque AT1:
  sub = user-42
  aud = orders-api
  scope = orders:read
  exp = 11:00:00

Cache policy:
  positive TTL tối đa = 20 giây
  safety margin = 3 giây
  không sliding expiration
~~~

### A. Token hợp lệ, người dùng đọc đơn của mình

10:00:00, RS introspect AT1; AS trả **active=true** và metadata đủ tin cậy. RS tạo entry tối đa 20 giây. Khi client xin đọc order-17, RS kiểm **tenant/ownership** và cho truy cập nếu policy hiện hành cho phép.

### B. AT1 bị revoke lúc 10:00:07

Nếu không có invalidation, entry active ở RS còn tối đa khoảng 13 giây. **Đó là cửa sổ stale đã được thiết kế**, không phải “revocation tức thời”. Nếu nghiệp vụ yêu cầu nhận biết revoke trong 5 giây, TTL 20 giây **không đạt yêu cầu**. Cần TTL thấp hơn, invalidation có cam kết hoặc kiểm real-time tại API nhạy cảm.

### C. User mất quyền tenant lúc 10:00:09

Kể cả token vẫn **active=true**, RS nên kiểm **current tenant policy** nếu quyền tenant phải được phản ánh ngay. Cached introspection không thể tự phát hiện mọi thay đổi quyền nghiệp vụ.

### D. Token gần hết hạn

10:59:50, token còn 10 giây. Với safety=3 giây, positive TTL tối đa chỉ **7 giây**, không phải 20 giây. Nếu exp được tính sai từ seconds thành milliseconds, cache có thể tồn tại hàng nghìn năm — đây là lỗi cần test.

### E. AS lỗi tại 11:00:01

AT1 đã quá exp và entry active cũng phải hết hạn. RS **không được** cho gọi API dựa vào kết quả 10:59:50. Nếu một token khác cache miss và AS tạm lỗi, xử lý theo **fail-closed policy**, không tự cấp quyền.

### F. Attacker gửi refresh token RT1 vào Orders API

RS phải từ chối vì RT1 là credential để gọi **token endpoint**, không phải access token của API. **active=true** nếu AS từng trả cho loại token nào đó không cho phép RS bỏ kiểm token purpose.

## 22. Ma trận kiểm thử cache active và introspection

| ID | Trường hợp | Kết quả mong đợi |
|---|---|---|
| **S01** | AS trả active=true, exp còn xa, đúng issuer/aud/type/scope | RS có thể cache positive không quá policyMaxTTL |
| **S02** | Cache hit trước hard TTL, quyền đối tượng còn hợp lệ | RS tiếp tục kiểm policy và cho phép nếu đủ quyền |
| **S03** | Cache miss sau TTL, AS trả active=false | RS từ chối |
| **S04** | Event revoke đáng tin đến đúng node | Cache entry liên quan bị xóa |
| **S05** | JWT access token hợp lệ và RS dùng kiểm signature/claims | JWT path vẫn tuân thủ revocation policy riêng |
| **F01** | Token còn exp 1 giờ, cache policy 20 giây | Không cache active 1 giờ |
| **F02** | Token chỉ còn 5 giây, safety 3 giây | TTL positive không vượt 2 giây |
| **F03** | Token đã hết hạn nhưng cache chưa bị evict do race | RS từ chối dựa trên exp |
| **F04** | Introspection không có exp, policy yêu cầu exp mới cache | Không tạo positive cache entry |
| **F05** | Introspection exp sai kiểu/giây thành mili giây | Không chấp nhận TTL không hợp lệ |
| **F06** | 100 cache hits liên tục | **Không gia hạn hard TTL** của active entry |
| **F07** | AS revoke chính AT1, cache còn active | RS ngừng chấp nhận chậm nhất theo freshness policy/TTL cam kết |
| **F08** | AS revoke RT1 nhưng AT1 vẫn còn hợp lệ theo AS | Không giả định RT revoke tự khiến AT1 inactive; tuân đúng AS token state |
| **F09** | AS trả active=false với HTTP 200 | RS từ chối; không đọc 200 thành Allow |
| **F10** | AS introspection trả HTTP 401 do RS credentials sai | Fail closed, không cache như inactive hoặc reuse stale active |
| **F11** | AS trả 5xx hoặc timeout khi cache miss | Không cấp quyền; báo dependency failure phù hợp |
| **F12** | Positive cache hết hạn đúng lúc AS timeout | Không dùng stale entry theo mặc định |
| **F13** | Introspection response thiếu active hoặc active không phải boolean | Từ chối/ghi lỗi giao thức |
| **F14** | Token active nhưng sai aud=payments-api | Orders API từ chối |
| **F15** | Token active nhưng issuer không được tin | Từ chối |
| **F16** | Token active, đúng aud nhưng thiếu orders:read | Từ chối thiếu scope |
| **F17** | Token active, đúng scope nhưng order thuộc tenant khác | Từ chối theo object-level policy |
| **F18** | Refresh token/ID token đưa làm Bearer tới RS | Từ chối sai mục đích |
| **F19** | token_type_hint=access_token nhưng token thực chất không phải access token | Không dùng hint thay token purpose verification |
| **F20** | Same token string được thử dưới hai issuer/trust contexts | Cache entries tách biệt, không chuyển trạng thái cross issuer |
| **F21** | RS-A và RS-B có audience/caller identity khác nhau | Không dùng chung metadata/active entry không đúng context |
| **F22** | User/client có hai access tokens, một token bị revoke | Không dùng cache keyed theo user/client khiến token còn lại bị nhầm |
| **F23** | Raw bearer token vô tình dùng làm Redis key | Kiểm thử phải phát hiện và cấm logging/storage đó |
| **F24** | Attacker gửi hàng nghìn token random | Cache bounded; negative cache không làm cạn memory |
| **F25** | Hai requests cache miss cùng token, cùng context | Single-flight giảm introspection trùng, không tạo Allow khi AS trả inactive |
| **F26** | Invalidation event đến khi request introspection cũ đang chạy | Không repopulate true sau event nếu thiết kế yêu cầu bảo đảm ngay |
| **F27** | Một RS node bỏ lỡ event revoke | Entry bị hết hard TTL, không kéo dài vô hạn |
| **F28** | Event cùng revision bị gửi lại nhiều lần | Handler idempotent, không tái kích hoạt token |
| **F29** | Event cũ đến sau event mới | Revision/epoch bảo vệ trạng thái; không ghi đè revoked bằng active |
| **F30** | JWKS/client registry/introspection endpoint không xác minh được | Fail closed, không dùng nguồn URL/key do caller tự khai |
| **F31** | Cache entry có active=true nhưng policy phiên bản mới cấm thao tác | Current authorization policy vẫn từ chối |
| **F32** | AS trả no-store hoặc hợp đồng không cho cache | Không lưu positive response trái chính sách |
| **F33** | Token gần exp và cache TTL được làm tròn lên | Không tồn tại entry vượt exp |
| **F34** | User sign-out nhưng OAuth token chưa bị AS revoke | RS hành xử theo trạng thái token/policy thật; không tự suy mọi logout = revoke |
| **F35** | Negative cache TTL quá dài khi backend đồng bộ token mới chậm | Test phát hiện từ chối nhầm, TTL negative được điều chỉnh theo policy |
| **F36** | API nhạy cảm cấu hình bypass positive cache | Mỗi request có kiểm trạng thái tươi theo hợp đồng |
| **F37** | Đo revocation detection latency đa node | Độ trễ trong SLO đã cam kết, không chỉ kiểm thông số config |
| **F38** | Gateway/APM/debug bật khi introspection | Không log raw token/Authorization/body/claims nhạy cảm |

### Integration test bắt buộc: revoke giữa hai cache hits

~~~text
Given:
    Access token AT1 hợp lệ cho orders-api.
    AS introspection trả active=true, exp còn 15 phút.
    RS cache positive với policyMax=20 giây.

When:
    t0: gọi Orders API, RS introspect và cache active.
    t0+5s: revoke CHÍNH AT1 tại AS; verify AS đã active=false.
    t0+6s: gọi Orders API lại với AT1.
    t0+21s: gọi Orders API lại với AT1.

Then:
    Request t0+6s có thể chịu cửa sổ stale nếu policy cho phép.
    Request t0+21s phải bị từ chối khi cache TTL đã hết và AS inactive,
        hoặc bị từ chối sớm hơn nhờ invalidation.
    Không cache/refresh active vô hạn do các request hit liên tục.
    Không có dữ liệu API bị lộ vượt độ trễ policy cho phép.
~~~

**Thời điểm kỳ vọng phải đo theo clock và giới hạn triển khai thực tế**: trong ví dụ, entry tạo tại t0 và TTL 20 giây; cần tránh test flaky vì scheduler hoặc mạng, nhưng không được sửa test bằng cách tăng TTL bảo mật. Nếu yêu cầu hệ thống là **revoke nhận biết trong tối đa 5 giây**, test tại t0+6s **phải từ chối**, và thiết kế TTL/invalidation phải đạt SLO ấy.

### Integration test concurrency khi revoke event tới

~~~text
Given:
    AT1 active tại t0, RS bắt đầu introspection request R1.
When:
    AS revoke AT1 và publish event có generation G2.
    RS nhận event G2, invalidate cache.
    Response cũ của R1 (generation G1) tới muộn, active=true.
Then:
    R1 không được ghi positive entry G1 trở lại nếu
        cơ chế yêu cầu invalidation ngay theo generation.
    Request sau event phải không dựa vào entry cũ.
~~~

Nếu triển khai chưa có generation fencing, hãy ghi nhận **giới hạn bảo đảm** và TTL hard bound thực tế; không tuyên bố “real-time revocation” chỉ vì đã thêm Kafka/Redis pubsub.

## 23. Checklist trước khi cho cache active vào production

1. **Định nghĩa:** Có hiểu **active=true** là trạng thái AS tại thời điểm kiểm, không phải cấp quyền vĩnh viễn?
2. **Nguồn tin cậy:** RS chỉ gọi introspection endpoint thuộc issuer được cấu hình/metadata tin cậy, qua TLS?
3. **Caller auth:** RS có credential/phương thức được AS cho phép và AS có kiểm quyền introspect?
4. **HTTP semantics:** Có xử lý **200 active=false** là inactive, không nhầm với lỗi 401/5xx?
5. **Token kind:** API có từ chối refresh token, ID token, code và chỉ nhận access token đúng hợp đồng?
6. **Audience/scope:** Cache hit vẫn kiểm aud, scope, exp, nbf, issuer, client context?
7. **Object-level authorization:** Tenant, resource ownership, role và policy hiện hành có được kiểm phù hợp?
8. **Positive TTL:** Có hard max theo risk policy và **không vượt exp** sau khi trừ safety margin?
9. **Missing exp:** Có chính sách rõ, mặc định không cache positive khi thiếu trần thời hạn đáng tin?
10. **Negative cache:** Có tách TTL inactive khỏi active; không cache lỗi network/401 như token state?
11. **Fixed expiry:** Cache hits không kéo dài lifetime của positive entry; không stale-while-revalidate mặc định?
12. **Cache key:** Bao gồm trusted issuer/environment, introspection caller, resource context và HMAC fingerprint token?
13. **Cache storage:** Không lưu raw bearer token làm key/log; metadata cache có ACL/retention phù hợp?
14. **Revoke:** Có mapping token/grant, xử lý đúng hậu quả revoke AT so với RT/session?
15. **Invalidation:** Event trusted, idempotent, có hard TTL dự phòng và xử lý stale repopulation nếu cần?
16. **Distributed nodes:** Mọi RS/cache tầng đều có giới hạn freshness; test node miss event?
17. **AS outage:** Cache miss/expired entry khi AS unavailable có fail closed, không tự Allow?
18. **Availability:** Có single-flight, timeout, bulkhead, rate limits và cache bounded để giảm tải AS?
19. **High-risk endpoints:** Có bypass cache hoặc TTL nghiêm ngặt theo nguy cơ?
20. **Metrics:** Đo tuổi active khi dùng, introspection errors và thời gian nhận biết revocation, không log credential?
21. **Tests:** Có positive, negative, time boundary, stale after revoke, concurrent invalidate, multi-issuer và tenant tests?
22. **Operations:** Có rollback cấu hình TTL, kế hoạch response khi key/AS bị xâm phạm và dashboard SLO?
23. **Governance:** TTL/ngoại lệ stale được phê duyệt, ghi rõ mức độ đảm bảo; không suy diễn một TTL chung cho mọi sản phẩm?

## 24. Câu hỏi tự đánh giá

**1. HTTP 200 từ introspection có đủ cho phép API request không?** Không. Response có thể là **active=false**; ngay cả active=true cũng cần kiểm audience, scope, token type, thời hạn và policy tài nguyên.

**2. Token exp còn một giờ thì cache active=true một giờ có an toàn không?** Không mặc định. Token có thể bị revoke trước exp; TTL active cần trần riêng ngắn theo risk policy.

**3. Theo RFC 7662, nếu introspection có exp thì cache được giữ quá exp không?** Không. Exp là giới hạn cứng; TTL theo policy thường phải ngắn hơn nhiều.

**4. Nếu AS không trả exp, giải pháp thận trọng là gì?** Không cache positive trừ khi có trần thời hạn đáng tin và policy rõ; tuyệt đối không cache vô thời hạn.

**5. Vì sao không dùng sliding expiration cho active=true?** Vì mỗi request có thể gia hạn kết quả cũ và cho token bị revoke tiếp tục được chấp nhận rất lâu.

**6. active=false có thể trả với HTTP 200 không?** Có. Đây là response introspection hợp lệ, không phải bằng chứng token active.

**7. Một introspection HTTP 401 có nghĩa user token bị revoke không?** Không. Đó có thể là lỗi xác thực RS/introspection caller; cần phân biệt với **active=false**.

**8. Có nên cache active bằng key user_id hoặc client_id không?** Không. Mỗi token có trạng thái khác nhau; cần key gắn đúng token và issuer/RS trust context.

**9. Event revoke xóa cache có đủ bảo đảm thu hồi tức thì không?** Không mặc định. Event có thể mất/trễ, và response introspection cũ đến muộn có thể ghi lại active=true; cần hard TTL và cơ chế fencing khi yêu cầu.

**10. Nếu AS timeout và cache active đã hết TTL, RS có nên cho qua request không?** Theo mặc định fail closed: **không**. Sự cố AS cần phản hồi dependency phù hợp, không tự gia hạn credential.

**11. Thu hồi refresh token có khiến mọi access token cũ active=false ngay không?** Không mặc định. Phải biết AS đã thu hồi **access token** nào và RS có cơ chế nhận biết revoke sớm hay không.

**12. Resource Server có thể dùng cached active=true thay kiểm quyền trên từng order không?** Không. Active là trạng thái token; quyền xem order cụ thể cần policy/ownership/tenant checks.

**13. Bearer access token bị đánh cắp có thể được phát lại trong TTL cache không?** Có thể. Cache stale có thể tăng cửa sổ lạm dụng; ngoài TTL còn cần lưu trữ an toàn, scope/audience/TTL giới hạn, sender-constrained token như DPoP/mTLS khi phù hợp và revocation policy.

**14. Kiểm thử nào chứng minh rõ nhất active cache không kéo dài quá lâu?** Revoke token ở giữa hai lần cache hit, đo thời gian đến lần RS từ chối trên nhiều nodes và xác nhận không có sliding expiration hay stale repopulation trái policy.

**Ghi nhớ:** **active=true trong introspection là một nhận định có thời điểm, không phải giấy phép truy cập vĩnh viễn.** Khi dùng cache, Resource Server phải giới hạn thời gian lưu bằng **hard positive TTL ngắn theo rủi ro**, **không vượt exp**, không tự gia hạn khi hit, cách ly cache theo **issuer/caller/resource/token**, và kết hợp **revocation invalidation** với TTL dự phòng. Phân biệt **active=false, lỗi AS, token sai mục đích và quyền tài nguyên**; mặc định **fail closed** khi không có bằng chứng còn hợp lệ. Cache giảm tải, nhưng chính sách độ tươi và kiểm tra quyền mới quyết định token bị thu hồi ngừng truy cập nhanh đến đâu.
