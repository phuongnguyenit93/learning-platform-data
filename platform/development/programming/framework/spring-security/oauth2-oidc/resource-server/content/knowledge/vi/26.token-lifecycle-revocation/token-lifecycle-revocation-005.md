# Đăng xuất ở client không tự làm mọi access token đã phát hành mất hiệu lực

Trong một hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, người dùng nhấn nút **Đăng xuất** ở web hoặc mobile app thường mong muốn mọi quyền truy cập của phiên đó chấm dứt ngay lập tức. Nhưng trong OAuth 2.0/OIDC, “logout” có thể chỉ xóa session tại một client, kết thúc phiên SSO tại OpenID Provider (OP), thông báo cho các Relying Party (RP), thu hồi refresh token, thu hồi access token hoặc hủy toàn bộ authorization grant. Đây là những hành động khác nhau, do những thành phần khác nhau quản lý.

**Đăng xuất ở client không tự động làm mọi access token đã phát hành mất hiệu lực.** Nếu client chỉ xóa cookie/session hoặc xóa token khỏi bộ nhớ, một bản sao access token đã bị lấy cắp vẫn có thể được Resource Server chấp nhận cho đến khi token hết hạn hoặc có cơ chế thu hồi được Resource Server thực sự kiểm tra. Việc OP kết thúc SSO session cũng không đồng nghĩa mọi access token đã cấp cho mọi API, mọi client và mọi thiết bị đều bị vô hiệu hóa.

Điều cần thiết là thiết kế một **logout lifecycle** có chủ đích: xóa phiên cục bộ, đăng xuất OP khi cần, gọi token revocation endpoint cho token phù hợp, xử lý refresh-token family, cập nhật trạng thái tại Resource Server và hiểu rõ độ trễ của cache/JWT validation.

> **Phải tách ba câu hỏi:** client đã xóa phiên của mình chưa; Authorization Server đã thu hồi credential/grant nào; Resource Server có nhận biết và từ chối token đó chưa?

Bài học thuộc chương **Vòng đời và thu hồi**. Nội dung tập trung vào sự khác nhau giữa client logout, OIDC logout và OAuth token revocation; access token/refresh token; RFC 7009, introspection, JWT tự xác minh; cách tích hợp logout trong Spring Security Servlet/WebFlux; các lựa chọn thu hồi và kiểm thử để chứng minh token cũ thực sự không còn được chấp nhận.

## 1. “Logout” không phải một thao tác duy nhất

Một ứng dụng có thể chứa nhiều session và credential độc lập:

| Thành phần | Trạng thái được quản lý | Hành động logout thường tác động |
|---|---|---|
| **Browser/mobile client** | Cookie, app session, token cache | Xóa dữ liệu cục bộ hoặc hủy session tại app |
| **Relying Party (RP)** | Session đăng nhập của ứng dụng | Hủy session của RP, xóa SecurityContext/cookie |
| **OpenID Provider (OP)** | SSO session của người dùng | Kết thúc phiên đăng nhập tại OP theo OIDC logout |
| **Authorization Server (AS)** | Access token, refresh token, authorization grant | Thu hồi token/grant theo endpoint và chính sách hỗ trợ |
| **Resource Server (RS)** | Trạng thái xác thực token, cache, denylist, session | Ngừng chấp nhận token khi biết token đã bị thu hồi hoặc hết hạn |
| **Downstream service** | Session riêng, token riêng, job hoặc cache riêng | Cần nhận sự kiện/thu hồi theo hợp đồng của hệ thống |

Ví dụ: user đăng nhập vào `orders-web`, nhận ID token và access token, sau đó gọi `orders-api`. Khi user bấm logout, ứng dụng có thể xóa `JSESSIONID` và điều hướng tới OP. Nhưng nếu `orders-api` đang xác minh JWT chỉ bằng chữ ký và thời hạn, nó không tự biết browser vừa logout.

### 1.1. Sơ đồ các vòng đời

~~~mermaid
flowchart TD
    A["User chọn Logout"] --> B["RP xóa local session / SecurityContext"]
    B --> C["Xóa token cache phía client"]
    C --> D{"Có yêu cầu OP SSO logout?"}
    D -->|"Có"| E["RP-Initiated Logout tới end_session_endpoint"]
    D -->|"Không"| F["Kết thúc local logout"]
    E --> G["OP kết thúc SSO session theo chính sách"]
    G --> H["Có thể gửi Front/Back-Channel Logout"]
    H --> I["Các RP hủy session liên quan"]
    F --> J["Access token đã phát hành vẫn có thể còn hiệu lực"]
    I --> J
    J --> K{"Có gọi RFC 7009 revocation?"}
    K -->|"Không"| L["Token có thể dùng đến exp hoặc tới khi RS tự phát hiện"]
    K -->|"Có"| M["AS thu hồi token / grant theo contract"]
    M --> N{"RS kiểm tra trạng thái thu hồi?"}
    N -->|"Có"| O["RS từ chối token khi cập nhật có hiệu lực"]
    N -->|"Không, JWT offline"| P["JWT có thể vẫn qua signature validation đến exp"]
~~~

Sơ đồ cho thấy **OIDC logout** và **OAuth token revocation** là hai luồng khác nhau. Back-channel logout có thể giúp các RP hủy session, còn RFC 7009 yêu cầu AS xử lý việc thu hồi token. Resource Server chỉ từ chối sớm nếu cách xác minh token của nó nhận biết trạng thái thu hồi.

### 1.2. Một ví dụ cụ thể

Giả sử:

~~~text
10:00  User đăng nhập orders-web.
10:01  OP cấp access token A, exp = 11:00.
10:02  RP tạo session S1.
10:10  User bấm Logout.
10:10  RP xóa session S1 và cookie.
10:10  Browser không còn token A trong storage.
10:11  Kẻ tấn công dùng bản sao token A đã lấy từ trước.
~~~

Nếu `orders-api` chỉ xác minh chữ ký JWT, `iss`, `aud` và `exp`, token A vẫn có thể hợp lệ lúc 10:11. Logout đã thành công ở RP, nhưng **không có sự kiện nào trong luồng đó bắt buộc RS biết token A đã bị sao chép hoặc người dùng đã logout**.

Đây là lý do không nên hứa “Logout ngay lập tức vô hiệu hóa mọi access token” nếu hệ thống chưa có cơ chế thu hồi và truyền trạng thái tới tất cả Resource Server.

## 2. Phân biệt client logout, RP logout và OP logout

### 2.1. Client logout: xóa phiên tại chính ứng dụng

Client logout thường thực hiện:

- Xóa cookie/session của ứng dụng.
- Xóa access token/refresh token khỏi token cache hoặc storage mà client quản lý.
- Xóa thông tin người dùng đang hiển thị.
- Dừng các tác vụ cục bộ gắn với session.
- Xóa dữ liệu tạm theo chính sách ứng dụng.

Việc xóa bản sao token trong browser **không làm token đã được gửi tới client khác hoặc bị sao chép ở nơi khác biến mất**. Access token là một bearer credential: ai giữ token và được RS chấp nhận có thể dùng token đó trong phạm vi quyền được cấp.

### 2.2. RP logout: hủy session của ứng dụng

Relying Party (ví dụ `orders-web`) có thể giữ:

~~~text
JSESSIONID -> server-side session
                  |
                  +-- SecurityContext
                  +-- principal
                  +-- authorized client references
                  +-- CSRF state
~~~

Khi logout, RP cần invalidate server-side session, xóa cookie đúng `Path`/`Domain`, dọn SecurityContext và loại bỏ dữ liệu authorized-client cục bộ nếu phù hợp. Với stateless API, có thể không có HTTP session; khi đó logout của web client không tác động đến JWT mà API đã nhận.

### 2.3. OP logout: kết thúc SSO session

OpenID Connect có **RP-Initiated Logout** để RP điều hướng user tới OP logout endpoint, thường được công bố trong discovery metadata bằng `end_session_endpoint`. RP có thể gửi `id_token_hint`, `post_logout_redirect_uri` và `state` theo đặc tả/khả năng OP.

Luồng này giúp kết thúc phiên SSO tại OP và cho phép OP xử lý các RP sessions liên quan. Nhưng nó **không phải OAuth token revocation endpoint**. Đừng giả định kết thúc SSO session tự động làm mọi access token đã phát hành trước đó bị RS từ chối.

### 2.4. Những thứ logout không tự động làm

Nếu không có cơ chế bổ sung, logout tại một client không nhất thiết:

- Thu hồi mọi access token của user.
- Thu hồi mọi refresh token trên mọi thiết bị.
- Hủy authorization grant/consent của mọi client.
- Kết thúc session tại tất cả RP khác.
- Xóa cache principal ở mọi Resource Server.
- Dừng job đã được khởi chạy bằng access token trước đó.
- Thu hồi token đã được đổi sang một resource/audience khác.

Các hành động này cần được định nghĩa rõ trong chính sách logout và contract với AS/OP.

## 3. Access token và refresh token có vòng đời riêng

### 3.1. Access token

Access token là credential được client trình cho Resource Server. Nó có thể là:

- **JWT/self-contained token:** RS có thể xác minh chữ ký và claims cục bộ mà không gọi AS mỗi request.
- **Opaque/reference token:** RS thường gọi introspection endpoint để biết token có active hay không và lấy metadata.

Token thường có thời hạn tương đối ngắn, nhưng việc hết hạn là một mốc độc lập với thời điểm client logout. Nếu token chưa hết hạn, cách RS kiểm tra quyết định liệu nó có còn được chấp nhận sau revocation hay không.

### 3.2. Refresh token

Refresh token được client dùng với token endpoint để lấy access token mới. Nó thường có vòng đời dài hơn access token và không phải credential gửi tới Resource Server.

Khi refresh token còn hiệu lực, một client đã logout cục bộ nhưng vẫn giữ được refresh token (ví dụ bản sao bị đánh cắp) có thể tiếp tục lấy access token mới, tùy chính sách AS. Vì vậy logout cần cân nhắc **thu hồi refresh token** hoặc authorization grant, đặc biệt khi user logout vì nghi ngờ credential bị lộ.

### 3.3. Token family và nhiều access token

Một grant có thể dẫn tới nhiều credential:

~~~text
Authorization Grant G
  |
  +-- Access token A1 -> orders-api
  +-- Access token A2 -> billing-api
  +-- Access token A3 -> profile-api
  +-- Refresh token R1
        |
        +-- rotated refresh token R2
              |
              +-- Access token A4
~~~

Thu hồi một token không có nghĩa mọi token liên quan đều bị thu hồi theo cùng một semantics ở mọi AS. RFC 7009 khuyến nghị AS vô hiệu hóa các token khác dựa trên cùng grant khi có thể; chi tiết cụ thể phụ thuộc loại token, khả năng AS và chính sách grant.

### 3.4. Bảng hành động và tác động

| Hành động | Local session | OP SSO session | Access token đã phát hành | Refresh token |
|---|---|---|---|---|
| Xóa cookie tại RP | Có | Không | Không tự thu hồi | Không tự thu hồi |
| Xóa token trong browser storage | Có thể | Không | Chỉ xóa bản sao tại client | Chỉ xóa bản sao tại client |
| RP-Initiated Logout | RP có thể xóa | OP xử lý logout | Không mặc định thu hồi | Không mặc định thu hồi |
| Front/Back-Channel Logout | Các RP nhận thông báo có thể hủy session | Thông báo liên quan OP session | Không mặc định thu hồi | Không mặc định thu hồi |
| RFC 7009 revoke access token | Không tự hủy RP session | Không tự kết thúc SSO | AS thu hồi token; RS phải nhận biết | AS có thể thu hồi token liên quan theo policy |
| RFC 7009 revoke refresh token | Không tự hủy RP session | Không tự kết thúc SSO | AS nên thu hồi access token liên quan nếu hỗ trợ | Refresh token bị thu hồi |
| Revoke authorization grant / consent | Không nhất thiết | Không nhất thiết | Có thể thu hồi token gắn với grant | Có thể thu hồi refresh token liên quan |

“Có thể” và “nên” ở bảng phản ánh sự khác nhau giữa protocol, provider và enforcement ở RS. Không được quảng cáo một nút logout là “revoke all tokens” nếu chưa chứng minh toàn bộ chuỗi đó.

## 4. OAuth 2.0 Token Revocation theo RFC 7009

**RFC 7009 — OAuth 2.0 Token Revocation** định nghĩa endpoint để client yêu cầu Authorization Server thu hồi token. Đây là bước riêng với OIDC logout.

Request thường là HTTP POST với `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_OR_REFRESH_TOKEN&token_type_hint=refresh_token
~~~

Đây là request minh họa. Endpoint, phương thức client authentication và token type phải theo metadata/documentation của AS. Client phải dùng TLS và không đưa token vào query string.

### 4.1. `token` và `token_type_hint`

- `token` là token cần thu hồi.
- `token_type_hint` là gợi ý loại token (ví dụ `access_token` hoặc `refresh_token`) để AS tối ưu việc tra cứu.
- Hint **không phải bằng chứng** token thuộc loại đó; AS vẫn phải xác định token thực tế theo implementation.
- Client authentication được áp dụng theo registration/policy của AS. Public client không có secret; confidential client thường phải xác thực.

### 4.2. Phản hồi 200 không nhất thiết chứng minh token trước đó active

RFC 7009 quy định khi token đã được thu hồi hoặc token không hợp lệ, endpoint trả HTTP 200. Điều này tránh tiết lộ cho caller liệu một token cụ thể có tồn tại/đang active hay không. Vì vậy:

~~~text
HTTP 200 từ revocation endpoint
  => yêu cầu revocation được xử lý theo contract
  != bằng chứng token trước đó chắc chắn còn active
  != bằng chứng mọi Resource Server đã cập nhật cache
~~~

Nếu AS không thể xử lý yêu cầu revocation vì lỗi tạm thời, endpoint có thể trả lỗi server (ví dụ 503); client cần xử lý theo chính sách retry/incident và không tuyên bố revoke thành công.

### 4.3. Thu hồi token liên quan cùng grant

RFC 7009 khuyến nghị AS vô hiệu hóa các token khác dựa trên cùng authorization grant khi có thể. Cụ thể, nếu thu hồi refresh token và AS hỗ trợ thu hồi access token, AS nên vô hiệu hóa access tokens được tạo từ cùng grant. Nếu request thu hồi một access token, AS có thể thu hồi refresh token liên quan.

Đây là hành vi AS cần hỗ trợ và triển khai; client không thể tự suy ra tất cả token liên quan đã bị thu hồi chỉ từ một response 200 nếu contract/provider không xác định phạm vi. Khi cần “logout mọi thiết bị” hoặc “revoke toàn bộ grant”, hãy dùng tính năng quản lý session/grant của AS nếu được hỗ trợ.

### 4.4. Revocation endpoint không phải UserInfo hoặc end_session_endpoint

| Endpoint | Dùng cho | Không thay thế |
|---|---|---|
| `/userinfo` | Lấy claims End-User theo OIDC | Không phải token revocation |
| `end_session_endpoint` | RP-Initiated Logout/OP session logout | Không mặc định thu hồi access token |
| `/oauth2/revoke` | Thu hồi access/refresh token theo RFC 7009 | Không tự hủy session RP hoặc mọi cookie |
| `/oauth2/introspect` | RS hỏi trạng thái token theo RFC 7662 | Không phải client logout endpoint |
| `/oauth2/token` | Cấp/refresh/exchange token | Không phải revoke endpoint |

Không dùng nhầm URL vì tất cả đều thuộc cùng một nhà phát hành.

## 5. Tại sao JWT đã revoke vẫn có thể được Resource Server chấp nhận?

Đây là phần quan trọng nhất khi thiết kế vòng đời token.

### 5.1. JWT offline validation

Một JWT access token có thể được xác minh tại RS bằng:

~~~text
compact JWT
   |
   v
verify signature with trusted JWKS
   |
   v
validate iss, aud, exp, nbf, token profile
   |
   v
create Authentication
~~~

Nếu RS không gọi AS và không kiểm tra revocation state bên ngoài, nó chỉ biết những claims trong JWT và chữ ký. **Một JWT đã bị AS đánh dấu revoked trong database vẫn có chữ ký toán học hợp lệ**. Decoder offline có thể tiếp tục chấp nhận nó đến khi `exp`, trừ khi RS có thêm cơ chế phát hiện revocation.

Ví dụ:

~~~text
10:00  JWT access token A được cấp, exp = 11:00.
10:10  Client gọi RFC 7009 revoke(A), AS đánh dấu A revoked.
10:11  RS xác minh signature/iss/aud/exp offline.
       Nếu RS không có denylist/event/introspection check,
       A có thể vẫn được chấp nhận.
~~~

Không có mâu thuẫn ở đây: AS đã thay đổi trạng thái trong hệ thống của mình; RS chưa được thông báo và không tra trạng thái đó.

### 5.2. Opaque token introspection

Với opaque token, RS thường hỏi AS:

~~~http
POST /oauth2/introspect
Authorization: Basic ...
Content-Type: application/x-www-form-urlencoded

token=opaque-token
~~~

AS trả:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "aud": ["orders-api"]
}
~~~

Sau khi revoke, một introspection mới có thể trả:

~~~json
{"active": false}
~~~

Nếu RS gọi introspection cho mỗi request (hoặc có cache đã được invalidated), nó có thể nhận biết trạng thái thu hồi nhanh hơn. Nhưng nếu RS cache `active=true` trong 5 phút, token đã revoked vẫn có thể được chấp nhận cho tới khi cache hết hạn hoặc bị invalidated.

### 5.3. So sánh hai mô hình

| Đặc điểm | JWT offline validation | Opaque + introspection |
|---|---|---|
| Kiểm tra mỗi request | Thường cục bộ | Thường có network call hoặc cache |
| Biết token revoked ngay? | Không, trừ khi có cơ chế bổ sung | Có thể, nếu hỏi AS và cache không stale |
| Phụ thuộc AS availability mỗi request | Ít hơn | Cao hơn nếu không cache |
| Độ trễ thu hồi | Thường đến `exp` nếu không có denylist/event | Theo introspection/cache/propagation |
| Chi phí | CPU crypto + JWKS refresh | Network, AS capacity, cache |
| Hỗ trợ hoạt động khi AS tạm ngưng | Có thể tiếp tục xác minh token đã cấp | Có thể fail closed nếu không có cache hợp lệ |
| Rủi ro chính | Revocation chậm | AS outage, cache stale, latency |

Không có một lựa chọn luôn tốt hơn. Hãy chọn theo yêu cầu **thời gian thu hồi tối đa chấp nhận được**, mức độ nhạy cảm của API, quy mô traffic và khả năng vận hành AS.

## 6. Các chiến lược làm access token mất hiệu lực sớm

### 6.1. Access token có thời hạn ngắn

Một cách đơn giản là đặt `exp` ngắn, ví dụ 5–10 phút theo risk/UX/AS capacity. Khi client logout và ngừng refresh, token sẽ tự hết hạn sớm.

Ưu điểm:

- RS không cần gọi AS mỗi request.
- Ít state revocation hơn.
- Giảm thời gian một access token bị đánh cắp có thể được dùng.

Giới hạn:

- Không phải thu hồi tức thì.
- Một token bị lộ vẫn dùng được tới `exp` nếu RS chỉ xác minh offline.
- Nếu refresh token còn sống, attacker có thể xin token mới; cần thu hồi refresh token/grant.
- TTL quá ngắn làm tăng refresh/token endpoint traffic và có thể gây lỗi UX khi AS chậm.

**Short TTL là giới hạn cửa sổ rủi ro, không phải cơ chế revoke ngay lập tức.**

### 6.2. Opaque token + introspection

RS hỏi AS trạng thái token. Khi revoke, AS trả `active=false` cho lần introspection kế tiếp theo contract.

Ưu điểm:

- Trạng thái token tập trung tại AS.
- Thu hồi có thể có hiệu lực nhanh mà không phải chờ `exp`.
- Có thể cập nhật permissions/active state mà không phát hành JWT mới, tùy AS.

Giới hạn:

- Network call và tải lên AS.
- Timeout/outage cần fail-closed policy.
- Cache introspection có thể làm chậm thu hồi.
- Một AS multi-tenant cần ràng buộc đúng issuer/resource/audience.

### 6.3. JWT denylist/revocation store

RS có thể kiểm tra `jti` (JWT ID) hoặc fingerprint của token trong một kho thu hồi trước khi xử lý request:

~~~text
JWT signature/claims valid
        |
        v
extract (iss, jti, exp)
        |
        v
lookup revocation store
        |
        +-- revoked -> reject
        |
        +-- not revoked -> continue authorization
~~~

Các yêu cầu:

- JWT cần `jti` duy nhất theo issuer/token issuance policy.
- Key phải namespace theo **issuer** (và tenant/resource nếu cần), vì hai issuer có thể trùng `jti`.
- Entry chỉ cần tồn tại tới `exp` + clock-skew allowance; sau đó token tự hết hạn.
- Store phải có tính nhất quán phù hợp giữa các RS instances.
- Không lưu raw bearer token nếu có thể dùng hash/fingerprint an toàn.
- Mọi request cần kiểm tra store trước khi chấp nhận; cache cục bộ phải có invalidation/TTL được tính vào SLA thu hồi.

Ví dụ khóa logic:

~~~text
revocation-key = hash(verified-issuer || ":" || jti)
value = revoked
ttl = max(0, exp + allowedClockSkew - now)
~~~

Đây là một thiết kế ứng dụng, không phải cơ chế tự động của JWT/Spring Security. Nếu token không có `jti`, có thể dùng hash của token, nhưng cần cân nhắc privacy, memory và tính nhất quán.

### 6.4. Event-driven revocation

AS có thể phát sự kiện khi token/grant/session bị revoke:

~~~text
Authorization Server
  |
  +-- TokenRevoked(issuer, jti, exp, grantId)
  +-- GrantRevoked(issuer, grantId)
  +-- SessionLoggedOut(issuer, sid, sub)
          |
          v
Resource Server / revocation service
  |
  +-- update denylist
  +-- invalidate introspection cache
  +-- clear related session/cache if any
~~~

Ưu điểm là giảm polling và có thể đạt thời gian thu hồi thấp. Nhưng cần xử lý:

- Event authentication/signature và authorization giữa AS với consumer.
- Delivery ít nhất một lần, duplicate và idempotency.
- Ordering, retry, dead-letter queue và event loss.
- Replica lag và cache invalidation trên mọi node.
- Phân biệt event token revoked với event RP session logout.
- Event có đủ định danh `iss`, `jti`, `sid`, grant/session ID theo contract hay không.

Không được tin một header/message tự khai `userId` để xóa hoặc tạo quyền cho principal. Sự kiện logout/revocation cũng là dữ liệu bảo mật cần xác minh nguồn.

### 6.5. Introspection cache có invalidation

Một cache có thể dùng TTL ngắn và chủ động xóa entry khi nhận revoke event. Nếu cache TTL 60 giây và event invalidation hoạt động, thời gian thu hồi có thể gần 60 giây hoặc nhanh hơn; nếu event bị mất, TTL là giới hạn fallback.

Cần xác định rõ:

~~~text
Maximum revocation delay
  <= event propagation delay
     + cache invalidation delay
     + request processing delay
~~~

Nếu không có event:

~~~text
Maximum revocation delay ~= introspection cache TTL
~~~

Đây là mục tiêu vận hành cần đo, không phải lời hứa mặc định của Spring Security.

## 7. Refresh token rotation và reuse detection

Refresh token thường có giá trị lâu dài hơn access token. Chỉ thu hồi access token hiện tại nhưng để refresh token còn hiệu lực có thể khiến client hoặc attacker xin access token mới.

### 7.1. Rotation

Với refresh-token rotation:

1. Client gửi refresh token `R1` tới token endpoint.
2. AS chấp nhận `R1`, cấp access token mới và refresh token `R2`.
3. AS đánh dấu `R1` không còn được sử dụng.
4. Client lưu `R2`, xóa `R1`.
5. Nếu `R1` bị dùng lại, AS có thể phát hiện reuse và revoke token family/grant theo policy.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: refresh_token=R1
    AS->>AS: Validate R1, rotate family
    AS-->>C: access_token=A2, refresh_token=R2
    C->>API: Bearer A2
    API-->>C: Resource response
    Note over C,AS: Logout hoặc phát hiện R1 bị reuse
    C->>AS: Revoke R2 / grant theo policy
    AS->>AS: Revoke refresh family và token liên quan
    Note over API: RS phải nhận biết access token bị revoke
~~~

### 7.2. Logout phải dọn refresh token

Nếu client chỉ xóa `R2` khỏi storage, một bản sao đã bị đánh cắp vẫn có thể được dùng. Khi logout cần gọi revocation endpoint bằng refresh token nếu AS hỗ trợ và client có quyền thực hiện. Với public client, việc revoke token phải tuân thủ cơ chế mà AS cung cấp; không nhúng client secret vào SPA/mobile binary.

### 7.3. Reuse detection không phải logout mọi session mặc định

AS có thể revoke token family khi refresh token cũ bị dùng lại vì đó là dấu hiệu có thể token đã bị sao chép. Nhưng semantics về việc thu hồi tất cả thiết bị/grants phụ thuộc provider. Không giả định một refresh-token family đồng nghĩa mọi session của user trên mọi client.

### 7.4. Concurrency khi nhiều tab/thiết bị refresh

Nếu hai tab dùng cùng refresh token đồng thời, rotation có thể làm một request bị xem là reuse tùy AS và grace policy. Client cần một cơ chế phối hợp refresh (single-flight/locking) và xử lý `invalid_grant` đúng cách. Logout giữa lúc refresh đang chạy cần ngăn access token mới được lưu/đưa vào request sau khi session đã kết thúc.

## 8. OIDC RP-Initiated Logout không phải token revocation

OIDC RP-Initiated Logout cho phép RP yêu cầu OP kết thúc phiên đăng nhập. Metadata OP có thể công bố `end_session_endpoint`.

Một request khái niệm:

~~~text
GET https://identity.example.com/logout
  ?id_token_hint=<ID_TOKEN>
  &post_logout_redirect_uri=https%3A%2F%2Forders.example.com%2Flogged-out
  &state=<random-state>
~~~

Các tham số thực tế phải theo OIDC RP-Initiated Logout và implementation của OP:

- `id_token_hint`: ID token liên quan tới phiên RP/OP; giúp OP xác định session phù hợp.
- `post_logout_redirect_uri`: URI đã được đăng ký/cho phép tại OP.
- `state`: giá trị chống request/response mix-up và liên kết luồng logout với client session.

**ID token ở đây được dùng làm hint cho logout endpoint, không phải token để API xác thực request.** Việc gửi `id_token_hint` không thay cho việc gọi RFC 7009 revoke access/refresh token.

### 8.1. Kết thúc OP session có thể ảnh hưởng những RP khác

OP có thể áp dụng logout cho phiên SSO và phát thông báo Front-Channel/Back-Channel tới các RP đã đăng ký. Nhưng mỗi RP phải triển khai đúng protocol để hủy session tương ứng. Không có nghĩa mọi access token cho mọi Resource Server đều bị vô hiệu hóa ngay.

### 8.2. RP cần kiểm tra redirect URI

Không chuyển user tới URL tùy ý từ request parameter:

~~~java
// Không an toàn: open redirect
handler.setPostLogoutRedirectUri(request.getParameter("returnTo"));
~~~

Hãy dùng URI đã đăng ký/allowlist và `state` được kiểm tra. Logout redirect là một bề mặt có thể bị lạm dụng để phishing hoặc open redirect.

### 8.3. Local logout vẫn cần thực hiện

Redirect tới OP không nên là thao tác duy nhất. RP cần invalidate local session và dọn SecurityContext/cookie theo đúng lifecycle, để user không còn dùng app session cũ ngay cả khi OP logout endpoint tạm thời không khả dụng. Tổ chức thứ tự sao cho việc gọi revocation còn giữ được token cần revoke, rồi mới xóa dữ liệu local.

## 9. Front-Channel Logout và Back-Channel Logout

OIDC có các cơ chế thông báo logout từ OP tới RP. Chúng giải quyết **session logout propagation**, không tự thay OAuth token revocation.

### 9.1. Front-Channel Logout

OP có thể mở/nhúng các logout URLs của RP trong browser (ví dụ iframe) để RP hủy session. RP dựa vào cookie/session browser để tìm phiên cần kết thúc.

Hạn chế:

- Browser có thể chặn third-party cookies hoặc iframe tracking.
- Một số trình duyệt chặn cookie cross-site, làm RP không tìm được session.
- Người dùng đóng tab hoặc network lỗi có thể khiến một số RP không nhận notification.
- Không phù hợp làm cơ chế đảm bảo revoke access token tại API.

### 9.2. Back-Channel Logout

OP gửi một **Logout Token** tới RP qua back-channel. RP xác minh token theo OIDC Back-Channel Logout và tìm session cần hủy. Logout Token là một JWT protocol message có contract riêng, gồm các kiểm tra như issuer, audience, thời điểm phát hành, `jti`, claim `events`, và `sid` hoặc `sub` phù hợp; không được chấp nhận chỉ vì nó có chữ ký JWT.

Một Logout Token **không phải access token** và không được dùng làm Bearer credential cho Orders API. Nó là thông điệp báo logout.

### 9.3. `sid` và `sub`

- `sid` có thể xác định một phiên OP cụ thể; RP có thể map nó tới các local sessions liên quan.
- `sub` xác định subject trong phạm vi issuer; nếu không có `sid`, chính sách có thể áp dụng logout cho các session của subject theo đặc tả và ứng dụng.
- Khóa map nên namespace theo issuer, vì `sid`/`sub` không nhất thiết duy nhất toàn hệ thống.

### 9.4. Sơ đồ Back-Channel Logout

~~~mermaid
sequenceDiagram
    participant U as User
    participant OP as OpenID Provider
    participant RP1 as orders-web
    participant RP2 as billing-web
    participant API as orders-api
    U->>OP: Logout tại OP
    OP->>RP1: POST Logout Token (back-channel)
    OP->>RP2: POST Logout Token (back-channel)
    RP1->>RP1: Verify Logout Token + tìm sid/sub
    RP2->>RP2: Verify Logout Token + tìm sid/sub
    RP1->>RP1: Invalidate local session
    RP2->>RP2: Invalidate local session
    Note over API: Access token đã cấp cần revocation/introspection/denylist riêng
~~~

### 9.5. Vì sao logout notification không tự thu hồi access token?

Back-channel logout message nói rằng một OP session cần được đăng xuất tại RP. Resource Server có thể không phải là RP, không lưu browser session và không nhận logout token. Nếu RS chỉ xác minh JWT offline, nó không biết OP vừa gửi message cho `orders-web`.

Nếu muốn event logout làm access token mất hiệu lực, hệ thống cần một **bridge có kiểm soát**: map OP session/grant tới token IDs hoặc principal/session state, phát revoke event tới RS/denylist/introspection store và xác định phạm vi token bị thu hồi. Không dùng logout notification để xóa mọi token cùng `sub` một cách mù quáng nếu user có nhiều client/thiết bị/grants độc lập.

## 10. Tích hợp logout trong Spring Security Servlet

Một ứng dụng có thể vừa là OAuth2/OIDC client (`oauth2Login`) vừa là Resource Server. Cần phân biệt **local web session logout**, **OP logout redirect** và **access-token revocation**.

### 10.1. OIDC client-initiated logout

Spring Security có `OidcClientInitiatedLogoutSuccessHandler` cho Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class WebLogoutConfiguration {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {
        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        // URI phải được đăng ký/cho phép ở OP.
        handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
        return handler;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/logged-out").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> {})
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

Đây là ví dụ cho **RP-Initiated Logout** trong Spring Security Servlet. `ClientRegistrationRepository` cung cấp metadata/registration, và handler có thể sử dụng ID token hint khi phù hợp. URI `{baseUrl}/logged-out` phải phù hợp đăng ký tại OP và cấu hình reverse proxy/base URL. Tùy phiên bản Spring Security, API/package có thể khác; kiểm tra reference của dependency đang dùng.

Handler trên xử lý OP logout redirect. Nó **không tự chứng minh** mọi access token đã bị thu hồi. Nếu ứng dụng cần revoke refresh/access token, phải bổ sung bước gọi revocation endpoint trước hoặc trong logout workflow, với token còn được lưu tại server.

### 10.2. Local logout và authorized-client cleanup

Spring Security OAuth2 Client có thể lưu `OAuth2AuthorizedClient` trong `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService`. Xóa authorized client khỏi kho local giúp ứng dụng không tiếp tục lấy token từ kho đó:

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId,
    principalName
);
~~~

Lệnh này là **local cleanup**. Nó không tự gửi RFC 7009 revocation request tới Authorization Server. Nếu muốn revoke, cần lấy access/refresh token còn có sẵn, gọi đúng endpoint AS, xử lý response, sau đó xóa local copy/session theo policy.

Không giữ token trong logs hoặc đưa vào URL. Với confidential client, revocation request thường phải được xác thực server-side; không gửi client secret từ browser.

### 10.3. Một service revocation minh họa

Ứng dụng có thể dùng `WebClient` hoặc HTTP client phù hợp để gọi revocation endpoint theo provider contract. Ví dụ conceptual với `WebClient`:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class TokenRevocationClient {

    private final WebClient webClient;
    private final String revocationUri;

    public TokenRevocationClient(
            WebClient webClient,
            String revocationUri) {
        this.webClient = webClient;
        this.revocationUri = revocationUri;
    }

    public Mono<Void> revokeRefreshToken(String refreshToken) {
        return webClient.post()
            .uri(revocationUri)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                    "token", refreshToken)
                .with("token_type_hint", "refresh_token"))
            .retrieve()
            .toBodilessEntity()
            .then();
    }
}
~~~

Đây chỉ là phần HTTP form minh họa. Production cần cấu hình client authentication theo AS (ví dụ HTTP Basic hoặc phương thức khác), TLS, timeout, retry có giới hạn và cách xử lý status 400/401/429/5xx. Không giả định mọi provider đều cho phép unauthenticated revocation. Không log form body vì nó chứa refresh token.

Nếu dùng `WebClient` trong Servlet app, việc revoke có thể được compose bất đồng bộ trong service/handler thích hợp; không gọi `block()` tùy tiện trên request thread. Nếu logout handler cần API đồng bộ, chọn một integration phù hợp với execution model và giới hạn timeout.

### 10.4. Thứ tự logout đề xuất

~~~text
POST /logout (CSRF-protected for browser session)
  |
  +-- Lấy authorized client/tokens từ server-side store
  |
  +-- Gửi RFC 7009 revoke(refresh token) nếu policy yêu cầu
  |
  +-- Gửi revoke(access token) nếu AS hỗ trợ/được yêu cầu
  |
  +-- Invalidate local session + SecurityContext
  |
  +-- Xóa cookie và local authorized-client record
  |
  +-- RP-Initiated Logout redirect tới OP nếu cần
  |
  +-- Hiển thị logged-out page
~~~

Thứ tự cụ thể phụ thuộc việc token còn lấy được sau khi session bị invalidate. Nếu cần gọi revocation, phải giữ credential trong một server-side logout context an toàn đủ lâu để gửi request. Nếu AS không khả dụng, ứng dụng cần quyết định: local logout vẫn hoàn tất ngay nhưng báo trạng thái revoke chưa xác nhận, hay chờ một khoảng timeout ngắn. **Không giữ user đăng nhập chỉ để chờ AS vô hạn.**

### 10.5. Logout endpoint phải chống CSRF

Với browser session/cookie, logout là một state-changing operation. Dùng POST và CSRF protection theo cấu hình ứng dụng; không tạo một GET `/logout?user=...` cho phép website khác ép user đăng xuất hoặc trigger revoke. RP logout redirect phải kiểm tra `state`/redirect URI theo flow.

## 11. Spring Security WebFlux: logout và token cleanup

WebFlux dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và reactive logout handlers. Khi app là OIDC client, Spring Security cung cấp `OidcClientInitiatedServerLogoutSuccessHandler` cho RP-Initiated Logout trong reactive stack ở các phiên bản hỗ trợ.

### 11.1. Reactive OIDC logout handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout
    .OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout
    .ServerLogoutSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveWebLogoutConfiguration {

    @Bean
    ServerLogoutSuccessHandler oidcLogoutSuccessHandler(
            ReactiveClientRegistrationRepository registrations) {
        OidcClientInitiatedServerLogoutSuccessHandler handler =
            new OidcClientInitiatedServerLogoutSuccessHandler(
                registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
        return handler;
    }

    @Bean
    SecurityWebFilterChain webChain(
            ServerHttpSecurity http,
            ServerLogoutSuccessHandler oidcLogoutSuccessHandler) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/logged-out").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> {})
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

Đây là mẫu cho WebFlux/OIDC client; kiểm tra class/package và builder theo phiên bản Spring Security cụ thể. Handler xử lý logout redirect tới OP, không tự động revoke mọi access/refresh token đã phát hành.

### 11.2. Xóa reactive authorized client local

Trong reactive OAuth2 Client, `ReactiveOAuth2AuthorizedClientService` có thể xóa authorized client:

~~~java
return authorizedClientService
    .removeAuthorizedClient(registrationId, principalName);
~~~

Đây là thao tác xóa bản ghi authorized-client cục bộ. Nó không tự gọi revocation endpoint. Nếu cần revoke, phải lấy token trước khi xóa và compose một HTTP POST reactive tới endpoint của AS.

### 11.3. Không blocking trong WebFlux logout

Không gọi:

~~~java
revocationClient.revoke(token).block();
~~~

trên Netty event loop. Hãy kết hợp `Mono`/`then`/`flatMap` trong logout workflow hoặc dùng một boundary blocking có chủ đích khi bắt buộc. Không tự gọi `subscribe()` rồi kết thúc response trước khi biết request revocation có được gửi hay không.

### 11.4. WebFlux API thuần Resource Server có thể không có logout session

Một API stateless chỉ nhận Bearer token có thể không cần endpoint `/logout` vì API không sở hữu client session. Việc logout/revoke thường do OAuth client thực hiện tại AS. Resource Server vẫn cần có cách nhận biết token đã bị revoke nếu SLA yêu cầu trước `exp` (opaque introspection, denylist, events).

Đừng thêm logout endpoint vào API chỉ để xóa một SecurityContext theo request: SecurityContext của request stateless không phải kho token trung tâm và việc xóa nó không thu hồi token ở nơi khác.

## 12. Client-side logout: SPA, mobile và BFF

### 12.1. SPA giữ token trong memory

Nếu SPA giữ access token trong memory, reload/đóng tab có thể làm mất bản sao. Nhưng token đã gửi tới API vẫn có thể còn hiệu lực. Logout nên:

- Xóa token khỏi memory/state.
- Hủy timer refresh và request đang chờ.
- Xóa dữ liệu người dùng/session local.
- Gọi revocation endpoint qua một luồng được AS hỗ trợ nếu cần.
- Điều hướng tới OP logout nếu ứng dụng cần kết thúc SSO.

Không đưa client secret vào JavaScript bundle. Public SPA không thể giữ bí mật dài hạn; việc xác thực revocation endpoint phải theo public-client policy của AS.

### 12.2. Token trong localStorage/sessionStorage

Xóa token trong storage chỉ xóa **bản sao của browser origin hiện tại**. Nó không xóa bản sao trong logs, extensions, malware, tab khác, backend cache hoặc nơi attacker đã lấy được. XSS có thể đọc token lưu trong JavaScript-accessible storage.

Không dùng việc “localStorage đã empty” làm bằng chứng token đã bị revoke. Cần cân nhắc BFF, memory storage, CSP, cookie flags và giảm thời gian access-token lifetime.

### 12.3. BFF giữ token server-side

Một Backend-for-Frontend có thể giữ access/refresh token ở server-side authorized-client store, browser chỉ giữ session cookie:

~~~text
Browser -- HttpOnly session cookie --> BFF
BFF -- access token --> Orders API
~~~

Logout:

1. BFF lấy token/authorized client từ server-side session.
2. BFF gọi revocation endpoint theo policy.
3. BFF xóa authorized-client record.
4. BFF invalidate session/cookie.
5. BFF có thể khởi tạo OP logout.

BFF giảm việc token xuất hiện trong browser JavaScript, nhưng **không tự thu hồi token**. Nếu refresh token hoặc access token bị lộ từ backend, cần revocation/resource-server enforcement tương ứng.

### 12.4. Mobile app

Mobile app có thể lưu token trong OS secure storage. Logout nên xóa local credential, gọi revocation nếu provider hỗ trợ, và xử lý OP session/SSO theo SDK. Gỡ app hoặc xóa keychain không thu hồi token đã được copy trước đó.

### 12.5. Nhiều tab và nhiều thiết bị

Một user có thể có:

~~~text
Phone session A -> refresh family A
Laptop session B -> refresh family B
Tablet session C -> refresh family C
~~~

Logout tại laptop không nhất thiết phải logout phone/tablet. Ngược lại, “Sign out everywhere” cần một cơ chế cấp user/session/grant tại OP/AS để xác định phạm vi và phát sự kiện tương ứng. Không chỉ revoke access token hiện tại rồi tuyên bố mọi thiết bị đã logout.

## 13. Logout, revocation và quyền riêng tư/độ trễ

### 13.1. Logout cục bộ nên nhanh

Người dùng cần thoát khỏi app ngay cả khi AS đang tạm thời không khả dụng. Một UX thường hợp lý:

- Xóa local session/cookie ngay sau khi đã lưu an toàn thông tin token cần revoke.
- Thực hiện revocation với timeout hữu hạn.
- Nếu revocation được xác nhận, ghi trạng thái thành công.
- Nếu AS unavailable, vẫn giữ local logout và báo rằng server-side revocation chưa xác nhận; retry qua một cơ chế server-side an toàn nếu policy cho phép.

Không giữ session sống chỉ vì một endpoint revoke bị treo. Nhưng cũng không nói “mọi token đã vô hiệu” khi revocation chưa được xác nhận.

### 13.2. Không lưu raw token để retry tùy tiện

Nếu cần retry revocation sau khi logout, việc lưu token để gửi lại là một rủi ro bảo mật. Ưu tiên thực hiện trong cùng workflow server-side với timeout và idempotency theo contract. Nếu phải queue, bảo vệ payload như credential, mã hóa, giới hạn retention, access control và xóa sau khi hoàn thành.

Không ghi token vào dead-letter queue/logs hoặc telemetry. Với một số thiết kế, có thể lưu reference/grant ID để yêu cầu AS revoke grant thay vì giữ raw token, nếu AS cung cấp API quản trị an toàn.

### 13.3. Revocation và quyền riêng tư

Logout/revocation events có thể mang `sub`, `sid`, grant ID, token ID hoặc tenant. Đây là dữ liệu định danh/nhạy cảm. Chỉ chia sẻ tối thiểu cần thiết, bảo vệ event transport và giới hạn retention. Không phát một event “logout user 842” toàn cục nếu semantics thực tế chỉ là logout một session của một client.

## 14. Cache, replica và giới hạn thời gian thu hồi

Một API phân tán có thể có nhiều instance và cache khác nhau:

~~~text
AS revocation DB
    |
    +--> Introspection node A
    +--> Introspection node B

Resource Server:
    +--> RS instance 1 / cache 1
    +--> RS instance 2 / cache 2
    +--> RS instance 3 / cache 3
~~~

Khi revoke:

- AS database có thể cập nhật ngay.
- Introspection replicas có thể có replication lag.
- RS caches có thể giữ `active=true`.
- Denylist event có thể đến chậm/mất.
- Một downstream service có thể cache Authentication riêng.

### 14.1. Xác định SLA revocation

Đừng dùng từ “immediate” nếu chưa định nghĩa:

| Cơ chế | Giới hạn thường gặp |
|---|---|
JWT offline, không denylist/event | Đến `exp` (cộng clock skew) |
JWT + denylist đồng bộ mỗi request | Theo consistency/availability của store |
JWT + event-driven denylist | Theo event propagation/cache invalidation |
Opaque introspection không cache | Theo thời gian AS phản ánh revoke + request latency |
Opaque introspection cache TTL 60s | Có thể tới gần 60s nếu không có invalidation |
Opaque introspection + event invalidation | Theo delivery/invalidation SLA, TTL là fallback |

Ví dụ policy:

~~~text
Sensitive payment API:
  max revocation delay <= 5 seconds
  -> requires online status or strongly propagated denylist

General read API:
  max revocation delay <= remaining short access-token TTL
  -> short-lived JWT may be acceptable
~~~

Các con số là ví dụ lựa chọn sản phẩm, không phải giá trị mặc định của Spring Security.

### 14.2. Clock skew và `exp`

Nếu validator cho phép clock skew 60 giây, một token có thể được chấp nhận lâu hơn timestamp `exp` một khoảng. Khi đặt short TTL để giới hạn cửa sổ logout, phải tính cả clock skew và sai lệch đồng hồ giữa AS/RS.

### 14.3. JWKS cache không phải token revocation cache

Xóa key khỏi JWKS có thể làm RS không còn xác minh chữ ký của nhiều token được ký bằng key đó, nhưng đây là **key rotation/compromise response** có phạm vi rộng, không phải cách thu hồi một access token cụ thể. JWKS cache TTL có thể làm thay đổi thời gian có hiệu lực. Không xoay khóa signing cho mỗi logout user.

## 15. Spring Security Resource Server: cách RS nhận biết revocation

### 15.1. JWT decoder mặc định không tự hỏi AS mỗi request

Cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
~~~

cho phép Resource Server xác minh JWT theo issuer/audience và các validators tương ứng. Nó không tự gọi RFC 7009 endpoint sau khi user logout. Nếu yêu cầu token bị revoke phải bị từ chối ngay, cần thêm một cơ chế như:

- `jti` denylist/revocation store.
- Introspection thay vì offline JWT (nếu AS hỗ trợ token type/profile tương ứng).
- Revocation events từ AS.
- Access token lifetime rất ngắn kết hợp revoke refresh token.
- Một gateway/policy service tập trung kiểm tra trạng thái.

### 15.2. Opaque token introspection

Cấu hình Servlet:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Khi AS trả `active=false` sau revoke, Resource Server có thể từ chối token ở lần introspection tiếp theo. Nhưng phải kiểm tra cache/timeout và implementation thật; đừng giả định chỉ vì cấu hình opaque là mọi cache đã bị vô hiệu.

### 15.3. Không dùng ID token/UserInfo để kiểm revocation

Một ID token còn hợp lệ hoặc UserInfo trả 200 không chứng minh access token đang dùng cho Orders API còn active. Ngược lại, một access token bị revoke không có nghĩa OP đã hủy mọi profile claims hay ID token trong client session. Các endpoints có contract khác nhau.

## 16. Mẫu JWT denylist theo `jti`

Nếu cần thu hồi JWT trước `exp` mà không gọi introspection mỗi request, một denylist có thể được thêm ở lớp authentication/authorization. Mô hình:

~~~java
public interface RevokedTokenStore {
    Mono<Boolean> isRevoked(String issuer, String jwtId);
}
~~~

Với Servlet code đồng bộ, interface có thể trả `boolean`; với WebFlux, nên trả `Mono<Boolean>` và dùng storage reactive. Đừng dùng một blocking Redis/DB call trên event loop.

### 16.1. Policy khái niệm

~~~java
public Mono<Authentication> authenticateWithRevocationCheck(
        Mono<Authentication> authentication) {
    return authentication.flatMap(auth -> {
        if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
            return Mono.error(
                new BadCredentialsException("JWT authentication required"));
        }

        Jwt jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer().toString();
        String jti = jwt.getId();

        if (jti == null || jti.isBlank()) {
            return Mono.error(
                new BadCredentialsException("JWT ID is required"));
        }

        return revokedTokenStore.isRevoked(issuer, jti)
            .flatMap(revoked -> revoked
                ? Mono.error(new BadCredentialsException(
                    "Access token is revoked"))
                : Mono.just(auth));
    });
}
~~~

Đây là **mẫu policy**, không phải một filter/manager hoàn chỉnh có thể dán trực tiếp vào mọi Spring Security version. Cần tích hợp nó vào authentication pipeline thích hợp và xử lý error mapping. Trong Servlet, dùng API đồng bộ tương ứng hoặc một filter/provider extension có chủ đích; trong WebFlux, compose reactive chain.

### 16.2. Cập nhật denylist khi logout/revoke

Một revocation service đáng tin có thể:

1. Xác minh request logout và lấy `iss`, `jti`, `exp` từ Authentication đã xác thực.
2. Gọi AS revocation endpoint theo policy nếu cần.
3. Ghi denylist key `(issuer, jti)` với TTL đến hết token.
4. Phát event invalidation tới mọi RS/cache.
5. Ghi audit outcome không chứa raw token.

**Không nhận `jti` từ request body làm đối tượng thu hồi** nếu chưa ràng buộc nó với Authentication/grant mà caller được phép quản lý. Nếu client được phép revoke token của chính mình, AS thường là nơi có quyền và metadata đầy đủ nhất.

### 16.3. Store không khả dụng thì sao?

Nếu policy yêu cầu revoke ngay, denylist store unavailable nghĩa là RS không thể chứng minh token chưa bị revoke. Một lựa chọn fail-closed là từ chối hoặc trả lỗi service-unavailable cho protected operation. Fail-open sẽ giữ availability nhưng phá SLA thu hồi; quyết định phải được ghi trong threat model, không âm thầm chọn.

## 17. Kiểm thử logout và token revocation

Một test `logout returns 302` chỉ chứng minh redirect/session behavior. Nó không chứng minh access token đã bị thu hồi.

Nên tách các lớp:

1. **RP local logout:** session invalidated, cookie cleared, SecurityContext không còn.
2. **OIDC RP-Initiated Logout:** OP logout redirect có endpoint/parameters đúng.
3. **RFC 7009 client behavior:** client gửi đúng token, token type hint và client authentication.
4. **AS behavior:** access/refresh token bị revoke theo provider contract.
5. **RS enforcement:** request với token cũ bị từ chối theo SLA đã chọn.
6. **Propagation:** caches/events/replicas nhận trạng thái thu hồi.

### 17.1. Ma trận kiểm thử

| Test | Kỳ vọng |
|---|---|
RP logout local | Session cũ không còn sử dụng được |
Cookie cũ gửi lại | Không khôi phục Authentication từ session đã invalidated |
RP-Initiated Logout | Redirect tới `end_session_endpoint` đúng; redirect URI đã đăng ký |
Logout request bị CSRF | Bị từ chối theo CSRF policy |
Revoke refresh token | AS xác nhận request theo RFC 7009; refresh token cũ không cấp token mới |
Revoke access token opaque | Introspection sau revoke trả inactive |
Revoke JWT offline | RS có thể vẫn chấp nhận tới `exp` nếu không có denylist/event; test phải thể hiện giới hạn này |
JWT denylist update | Token `jti` bị từ chối trên mọi RS instance sau propagation |
Introspection cache | Token bị từ chối sau invalidation hoặc TTL tối đa đã công bố |
AS timeout trong logout | Local logout vẫn hoàn tất theo policy; revoke status không bị báo sai là thành công |
Refresh token reuse | AS áp dụng family/reuse policy; token family bị xử lý đúng |
Back-channel logout | Logout Token được verify, đúng `iss`/`aud`/`events`, session theo `sid`/`sub` bị hủy |
User có nhiều thiết bị | Logout một session không vô tình xóa hoặc giữ tất cả session ngoài policy |
Service/client credentials | Không yêu cầu UserInfo/ID token để xử lý access token M2M |

### 17.2. Kiểm tra token trước và sau revoke

Integration test với opaque token:

~~~text
1. Lấy access token T từ test AS.
2. Gửi T tới /api/orders -> 200.
3. Gọi RFC 7009 revoke(T) bằng client hợp lệ.
4. Gửi lại đúng T tới /api/orders.
5. Kỳ vọng 401 sau khi introspection/cache propagation có hiệu lực.
~~~

Với JWT offline:

~~~text
1. Lấy JWT T có exp còn xa.
2. Gửi T tới /api/orders -> 200.
3. Gọi revoke(T) tại AS.
4. Gửi lại T tới RS chỉ dùng signature/claims offline.
5. Có thể vẫn 200 đến exp (nếu không có denylist/event).
6. Nếu thiết kế có jti denylist, sau khi cập nhật denylist -> 401.
~~~

Test này rất quan trọng vì nó ngăn nhóm phát triển tuyên bố rằng RFC 7009 tự làm một JWT offline biến mất khỏi mọi Resource Server.

### 17.3. MockMvc/WebTestClient chỉ với mock Authentication chưa đủ

`mockJwt()` hoặc `jwt()` có thể tạo Authentication giả lập, bỏ qua decoder/opaque introspection và revocation lookup thực. Chúng phù hợp để test HTTP authorization, nhưng muốn chứng minh token cũ bị từ chối phải gửi Bearer token thực qua filter chain và dùng decoder/introspector/revocation store đúng như production (với test keys/test AS).

### 17.4. Test Back-Channel Logout Token

Các trường hợp cần có:

- Logout Token ký bởi OP tin cậy, issuer/audience đúng, `events` có back-channel logout event và `jti` hợp lệ → xử lý session.
- Sai chữ ký/issuer/audience → từ chối.
- Có `nonce` không hợp lệ theo đặc tả logout token → từ chối.
- `sid` không tồn tại → xử lý idempotently.
- Duplicate `jti`/notification → không tạo tác dụng phụ lặp nguy hiểm.
- `sid` thuộc issuer khác nhưng cùng chuỗi → không xóa session sai issuer.
- Logout event chỉ hủy RP session; test riêng access-token revocation nếu hệ thống yêu cầu.

## 18. Các lỗi phổ biến

| Nhận định sai / anti-pattern | Vì sao sai | Hướng đúng |
|---|---|---|
“Xóa cookie là token hết hạn” | Chỉ xóa local session | Thu hồi token/grant nếu cần và RS phải nhận biết |
“OP logout tự revoke mọi access token” | SSO session và token là lifecycle khác | Kết hợp RP logout với RFC 7009/resource-server strategy |
“200 ở revoke endpoint chứng minh token active đã bị xóa” | RFC 7009 trả 200 cả khi token invalid | Hiểu response semantics, test RS enforcement |
“JWT revoked sẽ fail signature” | Signature vẫn hợp lệ đến khi key/token validation thay đổi | Denylist/event/introspection hoặc short TTL |
“Revoke refresh token là đủ tức thì” | Access token cũ có thể còn sống | Revoke related access tokens hoặc RS enforcement |
“UserInfo trả 200 nghĩa access token API còn active” | UserInfo và API resource khác nhau | Dùng introspection hoặc JWT access-token validation |
“ID token hint là token revoke” | `id_token_hint` phục vụ OIDC logout | Gọi RFC 7009 riêng |
“Back-channel logout tự xóa JWT khỏi mọi API” | Thường hủy RP sessions, không tự cập nhật RS | Bridge event/denylist/introspection nếu yêu cầu |
“Logout một thiết bị đồng nghĩa logout mọi thiết bị” | Session/grant/token family có thể độc lập | Định nghĩa phạm vi session/grant |
“Xóa authorized client local là revoke tại AS” | Chỉ xóa local store | Gọi revocation endpoint riêng |
“Nếu AS down thì cho token qua để user logout được” | Fail-open tạo quyền cho token chưa xác minh trạng thái | Local logout nhanh, nhưng API vẫn fail closed |
“Dùng `sub` để revoke tất cả token của user” | Có thể xóa token của clients/thiết bị/grants khác | Dùng grant/session/token identifiers và policy chính xác |
“Xoay JWKS key cho mỗi logout” | Ảnh hưởng nhiều token/client, không phải per-token revoke | Denylist hoặc introspection |
“Logout endpoint dùng GET không cần CSRF” | Có thể bị ép logout/revoke từ site khác | POST + CSRF/session policy |
“Giữ raw token trong logs để debug” | Bearer token là credential replay được | Log ID/trạng thái đã lọc |

## 19. Thiết kế logout theo mức độ yêu cầu

Không phải mọi ứng dụng cần cùng độ phức tạp. Hãy xác định **mức bảo đảm** trước khi chọn kỹ thuật.

### Mức 1 — Đăng xuất khỏi app

Phù hợp khi yêu cầu chỉ là user không tiếp tục dùng session của ứng dụng:

- Invalidate RP session.
- Xóa cookie/token cache.
- Điều hướng tới trang logged-out.
- Chấp nhận access token có thể còn hiệu lực đến `exp`.

Không được tuyên bố revoke token ngay lập tức.

### Mức 2 — Đăng xuất SSO và ngăn cấp access token mới

Phù hợp khi cần kết thúc phiên OP và ngăn refresh tiếp tục:

- Local RP logout.
- RP-Initiated Logout tới OP.
- Revoke refresh token hoặc grant theo provider support.
- Xử lý front/back-channel logout cho RP sessions liên quan.
- Access token cũ có thể còn sống tới `exp` nếu RS offline.

### Mức 3 — Thu hồi access token trong thời gian ngắn

Phù hợp API có dữ liệu/operation nhạy cảm:

- RFC 7009 revoke access/refresh token hoặc grant.
- Opaque introspection với TTL/cache policy rõ, hoặc JWT denylist.
- Revoke events/invalidation để giảm độ trễ.
- Resource Server fail closed khi không thể xác định trạng thái theo SLA.
- Integration tests đo thời gian từ revoke tới request bị từ chối.

### Mức 4 — Logout mọi session/thiết bị và incident response

Phù hợp trường hợp account compromise hoặc quản trị viên disable user:

- AS quản lý session/grant/token family và revoke theo subject/client/device.
- Back-channel logout tới mọi RP.
- Revoke refresh token families và access tokens liên quan.
- Propagate token revocation tới các Resource Servers.
- Clear BFF/session/authorized-client caches.
- Audit, rate-limit, idempotency, event delivery và recovery.
- Phân biệt “logout một session”, “logout mọi client” và “disable account”.

Một nút UI có thể hiển thị cùng chữ “Logout”, nhưng backend cần biết người dùng đang yêu cầu **mức nào**.

## 20. Checklist triển khai

### 20.1. Phía client/RP

- [ ] Invalidate local server-side session.
- [ ] Clear `SecurityContext` và cookie đúng domain/path.
- [ ] Xóa access/refresh token khỏi local storage/cache.
- [ ] Ngăn refresh request đang chạy lưu token mới sau logout.
- [ ] Gọi RFC 7009 cho refresh token/access token theo policy và AS support.
- [ ] Không expose client secret trong SPA/mobile.
- [ ] Khởi tạo RP-Initiated Logout nếu cần SSO logout.
- [ ] Validate `state`/registered post-logout redirect URI.
- [ ] Dùng POST/CSRF protection cho logout browser.
- [ ] Không báo “all tokens revoked” nếu chỉ xóa local session.

### 20.2. Phía Authorization Server

- [ ] Công bố revocation endpoint và client authentication requirements.
- [ ] Xác định semantics thu hồi access token/refresh token/grant.
- [ ] Có refresh-token rotation/reuse detection nếu phù hợp.
- [ ] Hỗ trợ quản lý session/grant để “sign out everywhere” nếu cần.
- [ ] Có back-channel logout endpoint registration khi cần RP session propagation.
- [ ] Phát revoke events có xác thực nếu RS cần cập nhật denylist/cache.
- [ ] Bảo đảm response 200/503 và lỗi theo RFC/provider contract.

### 20.3. Phía Resource Server

- [ ] JWT validation kiểm signature, issuer, audience, thời gian và token profile.
- [ ] Xác định JWT offline có chấp nhận cửa sổ tới `exp` hay cần revoke sớm.
- [ ] Nếu opaque, introspection `active` và cache TTL được xác định.
- [ ] Nếu denylist, dùng issuer-scoped `jti`/fingerprint và TTL.
- [ ] Nếu event-driven, xác minh nguồn event, idempotency và propagation.
- [ ] Khi trạng thái revocation không xác định, có fail-closed policy cho API nhạy cảm.
- [ ] Kiểm scope, tenant, owner và object-level authorization độc lập.
- [ ] Không coi ID token/UserInfo/OP logout event là access-token validation.
- [ ] Không log raw access/refresh/ID tokens.

### 20.4. Vận hành và kiểm thử

- [ ] Đo max revocation delay, không chỉ thời gian endpoint trả 200.
- [ ] Test nhiều RS instances/cache nodes.
- [ ] Test AS timeout/5xx và retry.
- [ ] Test refresh-token reuse và concurrent refresh.
- [ ] Test logout một session và logout mọi session.
- [ ] Test JWT bị revoke vẫn có thể pass offline nếu thiết kế không có denylist.
- [ ] Test opaque token bị revoke chuyển `active=false`.
- [ ] Test Back-Channel Logout Token và duplicate events.
- [ ] Theo dõi 401/403, introspection latency, cache hit, revoke propagation.

## 21. Sơ đồ quyết định: chọn chiến lược revoke

~~~mermaid
flowchart TD
    A["Yêu cầu logout"] --> B{"Chỉ cần kết thúc app session?"}
    B -->|"Có"| C["RP local logout + clear cookie/token cache"]
    B -->|"Không"| D{"Cần kết thúc SSO session?"}
    D -->|"Có"| E["RP-Initiated Logout / Front-Back Channel"]
    D -->|"Không"| F["Giữ OP session theo policy"]
    E --> G{"Cần ngăn cấp access token mới?"}
    F --> G
    G -->|"Có"| H["Revoke refresh token / grant theo RFC 7009"]
    G -->|"Không"| I["Access token còn tới exp theo contract"]
    H --> J{"RS cần từ chối access token cũ trước exp?"}
    J -->|"Không"| K["Short TTL + ngừng refresh"]
    J -->|"Có"| L{"Token type"}
    L -->|"Opaque"| M["Introspection + cache/invalidation"]
    L -->|"JWT"| N["jti denylist / revoke events / online state"]
    M --> O["Đo propagation và fail-closed"]
    N --> O
    K --> P["Test cửa sổ còn hiệu lực"]
    C --> Q["Không tuyên bố token đã revoke"]
~~~

## 22. Kết luận

~~~text
LOGOUT LIFECYCLE

CLIENT / RP LOGOUT
  invalidate local session
  clear cookie / local token copy
  optionally redirect to OP logout
          |
          v
OIDC OP LOGOUT
  end_session_endpoint
  front-channel / back-channel notifications
  primarily terminate SSO / RP sessions
          |
          v
OAUTH TOKEN REVOCATION (RFC 7009)
  revoke access token / refresh token / grant
          |
          v
RESOURCE SERVER ENFORCEMENT
  opaque introspection active=false
  JWT denylist / revoke event / online state
  or wait until short exp

LOCAL LOGOUT != TOKEN REVOCATION
OP SESSION LOGOUT != ACCESS TOKEN INVALIDATION
REVOCATION REQUEST != INSTANT RS ENFORCEMENT
~~~

**Đăng xuất ở client chỉ bảo đảm client/RP kết thúc phiên cục bộ nếu đó là những gì ứng dụng thực hiện.** RP-Initiated Logout kết thúc phiên SSO theo OIDC; Front/Back-Channel Logout giúp các RP nhận thông báo và hủy session. OAuth 2.0 Token Revocation theo RFC 7009 mới là cơ chế yêu cầu AS thu hồi access/refresh token. Và ngay cả khi AS đã revoke, Resource Server dùng JWT offline vẫn có thể chấp nhận token tới `exp` nếu không có denylist, event propagation hoặc kiểm tra trạng thái online.

Vì vậy, một logout lifecycle đáng tin phải định nghĩa rõ **phạm vi token/grant/session**, thu hồi refresh token để ngăn cấp token mới, và chọn cách Resource Server nhận biết revocation theo SLA. Hãy kiểm thử token cũ **sau** logout qua đúng filter chain/decoder/introspector production; một redirect thành công hoặc cookie đã bị xóa chưa chứng minh access token đã mất hiệu lực.

## Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, `token_type_hint`, client authentication và semantics response.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, grant và token endpoint.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` và metadata cho Resource Server.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` và `state`.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): thông báo logout qua browser/front-channel.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token, `sid`, `sub`, event claim và RP session invalidation.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `jti` và JWT claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): token validation, issuer/audience và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC client login.
- [Spring Security Reference — Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout, logout handlers và success handlers.
- [Spring Security API — OidcClientInitiatedLogoutSuccessHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html): Servlet RP-Initiated Logout handler.
- [Spring Security Reference — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): WebFlux OIDC client login.
- [Spring Security Reference — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): reactive local logout.
- [Spring Security API — OidcClientInitiatedServerLogoutSuccessHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/server/logout/OidcClientInitiatedServerLogoutSuccessHandler.html): WebFlux RP-Initiated Logout handler.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer/audience validation.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và principal.
- [Spring Security Reference — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): WebFlux JWT/opaque token resource server.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation, cookie và logout.
