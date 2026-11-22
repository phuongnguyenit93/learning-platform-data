# Introspection, trạng thái active và độ trễ phản ánh thu hồi

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, câu hỏi “Access Token đã bị thu hồi chưa?” không chỉ là việc nhìn một cờ trong database. Một Authorization Server có thể đã ghi nhận yêu cầu thu hồi, nhưng một Resource Server vẫn tạm chấp nhận token do **cache introspection**, **sự chậm trễ đồng bộ trạng thái**, **nhiều replica** hoặc **request đã đi qua bước xác thực trước thời điểm revoke**.

Đối với **opaque Access Token**, Resource Server thường hỏi Authorization Server thông qua **OAuth 2.0 Token Introspection** theo **RFC 7662**. Trong response, trường **`active`** có kiểu JSON boolean:

- **`active: true`**: Authorization Server cho biết token đang hoạt động trong ngữ cảnh introspection hiện tại. Resource Server vẫn cần kiểm tra issuer, audience/resource, scope và quyền trên từng dữ liệu.
- **`active: false`**: Resource Server **không được dùng token để tạo Authentication thành công**. Không thể tự kết luận token hết hạn, bị revoke, không tồn tại hay bên introspect không được phép biết thông tin.
- **Không nhận được phản hồi hợp lệ** vì timeout, lỗi TLS, HTTP 5xx hay schema sai: không đủ chứng cứ token active. **Fail closed**, không tự cấp quyền.

Điểm quan trọng của chương **Vòng đời và thu hồi** là **độ trễ phản ánh thu hồi**: khoảng thời gian từ lúc trạng thái bị thu hồi tại nguồn đến lúc Resource Server thật sự ngừng chấp nhận những request mới mang token đó. Không thể tuyên bố “revoke là chặn ngay” nếu còn positive cache hoặc chưa xác định tính nhất quán của Authorization Server.

Bài học sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x**, chủ yếu với **Servlet Resource Server** và có phần mở rộng **WebFlux**. Chúng ta đi từ RFC 7009/RFC 7662, sơ đồ thời gian và nguyên nhân staleness đến cấu hình Spring Security, cache, SLA thu hồi, xử lý lỗi và kiểm thử thực tế. URL/token trong ví dụ đều là giá trị minh họa.

## 1. Ba vòng đời phải được nhìn cùng lúc

Một hệ thống có ít nhất ba vòng đời:

1. **Vòng đời token ở Authorization Server (AS):** cấp phát, active, hết hạn, bị revoke, hoặc mất hiệu lực theo grant/session/issuer policy.
2. **Vòng đời kết quả xác thực ở Resource Server (RS):** tìm Bearer token, introspect, tạo principal/authorities, cache, hết TTL, introspect lại.
3. **Vòng đời request và nghiệp vụ:** security filter kiểm tra token, endpoint kiểm tra scope, service kiểm tra owner/tenant, database transaction thực hiện rồi phản hồi.

~~~text
Client                     Resource Server                  Authorization Server
  |                               |                                   |
  | Authorization: Bearer T       |                                   |
  |------------------------------>|                                   |
  |                               | POST /oauth2/introspect           |
  |                               |---------------------------------->|
  |                               |                                   |
  |                               | 200 {"active":true,...}           |
  |                               |<----------------------------------|
  |                               |                                   |
  |                               | Authentication + authorization    |
  | 200 OK                        |                                   |
  |<------------------------------|                                   |
  |                               |                                   |
  |         AS nhận yêu cầu revoke(T) và cập nhật trạng thái          |
  |                               |                                   |
  | Authorization: Bearer T       |                                   |
  |------------------------------>|                                   |
  |                               | Cache hit hay introspect lại?     |
  |                               |                                   |
  |                               | 200 {"active":false} nếu thấy revoke
  |                               |<----------------------------------|
  | 401 Unauthorized              |                                   |
  |<------------------------------|                                   |
~~~

Sơ đồ mô tả đường đi lý tưởng khi RS **đã quan sát trạng thái mới**. Nếu có cache active cũ, request cuối **có thể vẫn qua authentication tạm thời**.

### 1.1. Active token chưa chắc đủ quyền

Ví dụ introspection:

~~~json
{
  "active": true,
  "sub": "person-42",
  "client_id": "orders-web",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

Token này không tự cho phép:

- Gọi `POST /api/orders` khi endpoint yêu cầu `orders.write`.
- Xem đơn của tenant khác dù có `orders.read`.
- Dùng token dành cho `billing-api` tại `orders-api`.
- Thao tác khi tài khoản/tenant nội bộ đã bị khóa.

**Introspection trả trạng thái credential; authorization quyết định request/tài nguyên có được truy cập không.**

## 2. RFC 7662: trạng thái active có nghĩa chính xác là gì?

**RFC 7662 — OAuth 2.0 Token Introspection** cho phép bên được phép truy vấn trạng thái token và metadata liên quan.

### 2.1. Request introspection qua HTTPS

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json
Authorization: Basic BASE64_OF_RESOURCE_SERVER_CREDENTIALS

token=OPAQUE_ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| Form parameter `token` | Token do API client gửi đến RS, là **Bearer secret**. |
| `token_type_hint` | Gợi ý optional để AS tìm token, không phải bằng chứng token active. |
| Authorization Basic | Credential **của RS khi gọi AS**, khác Access Token của user. |
| Introspection URI | Endpoint được cấu hình đáng tin cậy, không lấy từ request/token chưa xác thực. |

Introspection cần **HTTPS**, TLS certificate/hostname verification, giới hạn timeout và bảo vệ credentials. AS có thể yêu cầu mTLS hoặc hình thức client authentication khác Basic; dùng phương thức đúng hợp đồng. Không log form body chứa Access Token hoặc header Basic.

### 2.2. HTTP 200 với active=true

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "orders-web",
  "token_type": "Bearer",
  "sub": "person-42",
  "iss": "https://identity.example.test/realms/demo",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

`active: true` biểu thị AS xem token active **trong ngữ cảnh introspection hiện tại**. Các trường khác tùy token profile và AS contract:

- `scope`: các phạm vi được cấp; với Spring Security thường được chuyển thành authorities có tiền tố `SCOPE_`.
- `sub`: subject, không tự đồng nghĩa local user có quyền trên mọi tenant.
- `client_id`: OAuth client nhận token, không tự là user ID.
- `aud`: resource mà token dành tới. Nếu API yêu cầu `orders-api`, cần xác minh audience khi contract có trường này.
- `iss`: issuer/token provider theo hợp đồng; không được tự tin một issuer mới từ token.
- `exp`, `iat`, `nbf`: metadata thời gian, thông thường theo NumericDate (giây Unix epoch).

Không giả định mọi AS đều trả đủ các trường ngoài `active`. **Nếu API cần một field để kiểm tra resource binding nhưng AS không cung cấp, không được âm thầm bỏ qua validator**; phải thống nhất contract hoặc thay đổi mô hình xác thực.

### 2.3. HTTP 200 với active=false

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

Điểm rất dễ nhầm: **HTTP 200 từ introspection chỉ có nghĩa request introspection được xử lý thành công**, không có nghĩa token hợp lệ. Khi `active:false`, RS phải từ chối credential.

RFC 7662 cho phép một phản hồi dạng này khi token:

- Hết hạn hoặc bị thu hồi.
- Không tồn tại/không được nhận diện.
- Chưa được phép dùng theo điều kiện của AS.
- Không được bên gọi introspection biết thông tin.

Do đó RS **không thể suy lý do cụ thể** chỉ từ `active:false`. Không tự trả chi tiết người thu hồi, thời điểm hoặc chủ sở hữu token nếu AS không công bố.

### 2.4. active bắt buộc là JSON boolean

| JSON response | Đúng kiểu? | Xử lý |
| --- | --- | --- |
| `{"active":true}` | Có | Có thể tiếp tục kiểm tra metadata và quyền. |
| `{"active":false}` | Có | Không tạo Authentication thành công. |
| `{"active":"true"}` | Không: string | Từ chối, coi là lỗi contract/protocol. |
| `{"active":"false"}` | Không: string | Không ép kiểu thành boolean. |
| `{"active":1}` | Không: number | Không chấp nhận. |
| `{"active":null}` | Không | Không chấp nhận. |
| `{}` | Không: thiếu field bắt buộc | Không chấp nhận. |
| Body rỗng/JSON lỗi | Không | Không chấp nhận, ghi lỗi tích hợp. |

Nếu tự parse JSON, không nên dùng:

~~~java
// KHÔNG LÀM: ép kiểu mơ hồ.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active")));
~~~

**Ưu tiên introspector chuẩn của Spring Security**. Nếu tự triển khai adapter, phải giữ semantics: chỉ boolean `true` mới cho phép tiếp tục, còn response sai kiểu không được tạo principal.

### 2.5. HTTP 401/503 của AS không phải active=false

| Upstream response | Giải thích | Hành động RS |
| --- | --- | --- |
| 200 + `active:true` | Token active theo AS. | Xác minh metadata/authorization. |
| 200 + `active:false` | Token không được chấp nhận. | Authentication thất bại, thường 401 tại API. |
| HTTP 401 từ AS introspection | Credentials **của RS** không hợp lệ/không được chấp nhận. | Không kết luận mọi user token hết hạn; điều tra client authentication. |
| HTTP 403 từ AS | Quyền truy vấn introspection bị hạn chế. | Fail closed và điều tra chính sách. |
| HTTP 429/5xx | AS rate limited/quá tải/sự cố. | Fail closed, retry transient có giới hạn. |
| Timeout, DNS, TLS | Không có kết quả xác minh. | Fail closed, không tự suy token active. |
| 200 với `active` sai schema | Vi phạm contract. | Không chấp nhận và báo protocol error. |

Lỗi tích hợp AS phải có metrics/logs **riêng với token inactive**. Nếu toàn bộ lỗi upstream bị ghi là “expired token”, đội vận hành sẽ không phát hiện xoay client secret sai hoặc AS outage.

## 3. RFC 7009: yêu cầu revoke không đồng nghĩa mọi API đã từ chối

**RFC 7009 — OAuth 2.0 Token Revocation** mô tả endpoint nhận yêu cầu thu hồi token. Ví dụ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_AUTHORIZED_CLIENT_CREDENTIALS

token=ACCESS_OR_REFRESH_TOKEN_VALUE&token_type_hint=access_token
~~~

| Endpoint | Mục đích |
| --- | --- |
| **Revocation** | Yêu cầu AS thu hồi một token/grant theo quyền được cấp. |
| **Introspection** | Hỏi AS token hiện được chấp nhận hay không. |

RFC 7009 thiết kế HTTP success của revocation nhằm hạn chế tiết lộ token có tồn tại hay không. Một request revocation có thể nhận **HTTP 200 ngay cả khi token không tồn tại/đã không hợp lệ**. Vì vậy HTTP 200 từ revoke endpoint **không phải biên bản chứng minh mọi RS đã ngừng dùng token**.

### 3.1. Phân biệt Access Token, Refresh Token và session

- **Access Token**: credential client gửi tới RS để truy cập tài nguyên.
- **Refresh Token**: credential client dùng với AS để xin Access Token mới.
- **Authorization grant**: quan hệ cấp quyền có thể sinh nhiều tokens.
- **OIDC Login session**: phiên đăng nhập tại OpenID Provider/Relying Party, có lifecycle khác.

Thu hồi Refresh Token có **thể** kéo theo Access Token hoặc grant liên quan, nhưng mức độ cascade tùy AS và chính sách. **Không mặc định “revoke refresh token” tự chặn tức thời mọi Access Token đã phát**. Logout một OIDC session cũng không bảo đảm tất cả Access Tokens đang nằm ở client/RS đã bị AS revoke.

### 3.2. Bốn mốc của một lần revoke

~~~text
R0: Client/Admin gửi revoke request
    |
R1: AS trả HTTP success cho revoke request
    |
R2: Revocation được commit vào nguồn sự thật
    |
R3: Mọi introspection backend nhìn thấy active=false
    |
R4: Mọi serving Resource Server ngừng chấp nhận requests mới
~~~

Trong hệ thống có đồng bộ bất đồng bộ và cache, các mốc trên **không bắt buộc trùng nhau**. Cần đo và định nghĩa rõ mình đang hứa với người dùng **R1, R3 hay R4**.

## 4. Mô hình thời gian phản ánh thu hồi

Đặt:

- **`t_request`**: lúc gửi revoke request.
- **`t_commit`**: lúc trạng thái revocation được AS commit.
- **`t_visible`**: lúc introspection trên **mọi backend liên quan** trả inactive nhất quán.
- **`t_cache_expiry(node)`**: lúc positive result của mỗi RS node không còn được sử dụng.
- **`t_last_accept(node)`**: lần cuối node chấp nhận một request mới với token đã revoke.
- **`t_first_deny(node)`**: lần đầu quan sát node đó từ chối token sau revoke.

~~~text
AS commit revoke
       |
       |  L_visibility / replication delay
       v
Introspection thấy inactive nhất quán
       |
       |  L_positive_cache / invalidation delay
       v
RS không còn trả cached active=true
       |
       |  L_request_in_flight
       v
Work đang chạy được xử lý theo policy riêng
~~~

Định nghĩa thực tế:

> **Độ trễ phản ánh thu hồi cho request mới** là khoảng thời gian từ mốc AS đã commit revocation đến lúc Resource Servers đang phục vụ traffic đều ngừng xác thực thành công token đó theo chính sách.

**Request đã qua authentication trước revoke** không nằm trong cùng phạm vi đo trừ khi hợp đồng nói rõ phải ngắt cả hoạt động đang chạy.

### 4.1. Công thức ước lượng có điều kiện

Giả sử:

1. AS cam kết tối đa **`L_AS`** từ commit đến khi mọi introspection nodes thấy revocation.
2. RS positive cache TTL tối đa **`T_cache`**, không dùng stale-on-error quá TTL.
3. Mỗi request mới đều đi qua cơ chế authentication thích hợp.
4. Không có gateway hoặc replica khác phục vụ stale state lâu hơn.

Một ước lượng bảo thủ:

~~~text
L_new_requests ≲ L_AS + T_cache + margin_for_network_and_scheduling
~~~

Đây **không phải bảo đảm của RFC** và không phải giới hạn đúng trong mọi hạ tầng. Nếu AS replication không có bound, gateway cache 10 phút hoặc một node bỏ qua introspection, công thức không đủ để dự báo revocation latency.

Đối với request đang xử lý, cần thêm một chính sách **in-flight transaction/side-effect revalidation** độc lập.

## 5. Timeline: vì sao revoke lúc 10:00 vẫn có request 200?

Giả sử AS phản ánh revoke ở introspection sau tối đa 300 ms; RS cache active trong 30 giây; token còn `exp` sau 15 phút.

~~~text
09:59:59.900  RS introspect T -> active=true
              Cache positive result cho T trong 30s

10:00:00.000  AS commit revoke(T)
10:00:00.300  Tất cả introspection backends trả active=false

10:00:05.000  Client dùng T -> RS cache hit
              -> request có thể vẫn authenticated

10:00:29.901  Cache hết TTL; RS introspect lại
              -> active=false -> từ chối
~~~

**Điểm mấu chốt:** AS đã biết token revoked nhưng RS dùng một kết quả `active:true` được xác minh **trước khi revoke**.

Kịch bản có thể chậm hơn một lần cache TTL tính từ lúc revoke:

~~~text
10:00:00.000  AS commit revoke T
10:00:00.050  Một AS introspection replica còn trả active=true
10:00:00.051  RS vừa refresh positive cache 30s
10:00:00.300  AS đã đồng bộ xong, introspection mới trả false
10:00:30.052  RS cache mới hết hạn và bắt đầu reject
~~~

Vì thế, cần xét **cả AS visibility lag và thời điểm làm mới positive cache**. Không chỉ nhìn một cấu hình TTL rồi khẳng định mọi token revoked bị chặn trong đúng TTL giây.

### 5.1. Một node đã 401 chưa nghĩa toàn cụm đã 401

~~~text
RS Node A: từ chối token T sau 1s
RS Node B: tiếp tục chấp nhận T thêm 18s
RS Node C: từ chối token T sau 4s
~~~

Một request qua load balancer gặp A và nhận 401 **không chứng minh B/C đã hội tụ**. Muốn đo SLA toàn cluster, cần probe từng serving node/zone hoặc có telemetry/acknowledgement đáng tin cậy về trạng thái cache/decision của tất cả replicas.

## 6. Những nguồn tạo độ trễ sau revoke

| Nguồn | Triệu chứng | Hướng kiểm soát |
| --- | --- | --- |
| AS replication lag | Introspection ở các AS nodes trả trạng thái khác nhau. | Thống nhất datastore/consistency policy, đo `t_visible`. |
| Positive cache ở RS | AS trả false nhưng API vẫn 200. | TTL ngắn, invalidation, cache key đúng. |
| Token cache ở gateway | Spring không thấy mọi request hoặc gateway đã chấp nhận trước. | Kiểm tra gateway auth/cache lifecycle. |
| Distributed cache | Nhiều RS dùng một cached principal cũ. | TTL/invalidation toàn cụm, namespace theo issuer/resource. |
| JWT local validation | API chỉ kiểm chữ ký/`exp`, không introspect. | Denylist/epoch/token ngắn hạn/online check. |
| Web session đã tồn tại | Sau OIDC logout, cookie session còn hiệu lực ở RP. | Session invalidation/revalidation. |
| Streaming/WebSocket | Xác thực lúc bắt đầu, không kiểm lại giữa phiên. | Periodic revalidation hoặc event-driven disconnect. |
| Request đã vào transaction | Revoke xảy ra sau authentication. | Kiểm tra trạng thái tại domain boundary/commit nếu cần. |
| Local user/tenant status | AS active nhưng nội bộ đã khóa. | Domain/account/tenant authorization gate. |
| Stale-on-error | AS outage, RS phục vụ cache `active:true` đã quá TTL. | Mặc định fail closed, bounded exceptions nếu được duyệt. |
| Revoke không cascade | Refresh Token bị revoke nhưng Access Token cũ vẫn active. | Xác định semantics ở AS và test. |
| Lệch đồng hồ | TTL hoặc `exp` không đúng. | Đồng bộ/giám sát clock, safety margin. |

Tối ưu một tầng **không đủ** nếu tầng khác còn chấp nhận stale token.

## 7. Viết revocation SLO/SLA có thể kiểm thử

Yêu cầu “token phải revoke tức thời” không có nghĩa định lượng. Một tiêu chí tốt:

> “Kể từ thời điểm AS xác nhận **commit** revocation, tối đa N giây sau, **mọi request mới bắt đầu xác thực** tại tất cả Resource Server production còn phục vụ traffic phải từ chối Access Token đó. Các requests đang chạy được xử lý theo chính sách nghiệp vụ riêng.”

Trong tài liệu SLA cần định nghĩa:

- **Mốc bắt đầu:** user bấm Logout, revocation HTTP 200 hay AS commit?
- **Mốc kết thúc:** introspection first false, một API 401, hay mọi serving nodes không còn accept?
- **Loại token:** opaque Access Token, JWT, Refresh Token, token exchange, service credentials?
- **Phạm vi:** một cluster/region, đa vùng, gateway, API, session/websocket?
- **Điều kiện lỗi:** AS unavailable, node network partition, cache invalidation bị mất?
- **Phân vị và giới hạn:** p50/p95/p99, worst-case scenario, ngưỡng cảnh báo.
- **In-flight work:** có bắt buộc dừng các transactions đang chạy không?

### 7.1. Risk-based policy

| Loại thao tác | Chính sách minh họa |
| --- | --- |
| Đọc dữ liệu ít nhạy cảm | Có thể cache positive ngắn theo revocation SLO. |
| Profile user | TTL thấp hơn, kiểm tra local account/tenant. |
| Thanh toán và quản trị quyền | Introspection sát request hoặc domain revocation gate mạnh hơn, có thể bỏ positive cache. |
| WebSocket/SSE | Revalidation trong phiên dài, hoặc close stream theo revoke event. |
| Background jobs | Kiểm tra quyền/user/tenant ở thời điểm job thực thi. |

Không có một TTL chuẩn do RFC 7662 hoặc Spring Security áp cho mọi hệ thống; số giây là quyết định bảo mật và hiệu năng.

## 8. JWT và opaque token phản ánh revoke khác nhau

### 8.1. Opaque token introspection mỗi request

~~~text
Bearer opaque T
  -> RS
  -> POST introspection(T)
  -> active true/false
  -> Authentication hoặc reject
~~~

Ưu điểm: khi AS đã nhìn thấy revoke và không có positive cache, request tiếp theo có thể nhận trạng thái mới. Nhược điểm: phụ thuộc network/AS QPS/latency/availability mỗi lần authentication.

### 8.2. Opaque token với cache

~~~text
Bearer opaque T
  -> Result cache lookup
      hit: dùng result active được xác minh trước
      miss: POST introspection(T)
~~~

Ưu điểm: giảm QPS/latency. Nhược điểm: **revocation stale window** do cache. Cần TTL giới hạn bởi `exp`, SLO và invalidation.

### 8.3. JWT được validate offline

~~~text
Bearer JWT
  -> JWKS trusted public key
  -> Signature / issuer / audience / exp / nbf
  -> Authentication
~~~

Nếu RS chỉ decode JWT, một lần revoke ở AS **không tự thông báo cho JWT decoder** rằng một token cụ thể đã mất hiệu lực trước `exp`. Nếu cần revoke trước hạn, có thể thiết kế:

- Access Tokens ngắn hạn.
- Denylist theo `jti`/fingerprint (có TTL).
- Minimum issuance epoch/token version theo user/tenant.
- Introspection JWT hoặc online revocation check nếu AS hỗ trợ.
- Vô hiệu hóa tenant/client/service principal ở domain gate.
- Sender-constrained tokens (mTLS/DPoP) giúp hạn chế replay, **không thay thế revoke**.

### 8.4. Introspection không bắt buộc chỉ cho opaque format

RFC 7662 là giao thức truy vấn trạng thái. Một AS có thể cho phép introspect **JWT Access Token**. Trong Spring Security, RS chọn đường xác thực **JWT decode** hay **opaque introspection** qua cấu hình; không dựa vào việc token “có dấu chấm” để tự thay đổi trust policy.

| Cách xác thực | Khả năng thấy revoke sớm |
| --- | --- |
| JWT local decode | Cần cơ chế bổ sung nếu muốn revoke trước `exp`. |
| Opaque introspection không cache result | Khi AS đã phản ánh revoke ở introspection. |
| Opaque introspection có positive cache | Khi cache hết TTL/invalidate và AS phản ánh revoke. |
| JWT + online check | Cùng các rủi ro visibility, cache và outage của online check. |

## 9. Cấu hình Servlet Spring Security Opaque Resource Server

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 9.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

`introspection-uri` phải là HTTPS endpoint được cấu hình tin cậy. `client-id` và `client-secret` là credential **Resource Server dùng để gọi introspection**, không phải token của user. Đọc secret từ environment/secret manager, không commit vào source code hay log.

### 9.3. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong chuỗi:

1. Spring Security lấy Bearer token từ request.
2. `OpaqueTokenIntrospector` gọi AS, kiểm tra `active`.
3. Inactive token không thể tạo Authentication thành công.
4. Active token với metadata hợp lệ tạo principal/authorities.
5. `authorizeHttpRequests` kiểm tra scope cho endpoint.
6. Domain service kiểm tra owner, tenant, trạng thái tài khoản và business permissions.

`STATELESS` và tắt CSRF chỉ là ví dụ cho API thuần Bearer Authorization header; **không áp nguyên xi cho web OIDC Login sử dụng session cookie**. `securityMatcher("/api/**")` chỉ bảo vệ path trong chain đó; nếu ứng dụng có routes khác phải có fallback/chain riêng.

### 9.4. Scope khác trạng thái active

~~~json
{"active":true,"sub":"person-42","scope":"orders.read"}
~~~

Khi caller gửi:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
~~~

token có thể bị **403 insufficient_scope** vì thiếu `orders.write` dù `active:true`. Đây không phải dấu hiệu token bị revoke.

## 10. Các thành phần Spring Security tham gia introspection

~~~text
HTTP Authorization: Bearer T
                 |
                 v
BearerTokenAuthenticationFilter
                 |
                 v
BearerTokenAuthenticationToken
                 |
                 v
OpaqueTokenAuthenticationProvider
                 |
                 v
OpaqueTokenIntrospector.introspect(T)
                 |
                 +-- active=false -> authentication failure
                 |
                 +-- upstream/schema error
                 |      -> không tạo Authentication thành công
                 |
                 +-- active=true + metadata hợp lệ
                             |
                             v
                  OAuth2AuthenticatedPrincipal
                             |
                             v
                  BearerTokenAuthentication
                             |
                             v
                  AuthorizationFilter
                             |
                             v
                  Controller / Domain authorization
~~~

Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal` và Authentication là `BearerTokenAuthentication`, không nhất thiết là `Jwt` hoặc `JwtAuthenticationToken`. Không ép dữ liệu opaque principal thành JWT chỉ vì một issuer nội bộ lưu token dưới dạng JWT.

Spring Security không cam kết **result cache introspection với TTL cố định cho mọi phiên bản/cấu hình**. Nếu ứng dụng tự thêm cache decorator, proxy hoặc gateway token cache, chính kiến trúc đó quyết định phần lớn độ trễ revoke.

## 11. Cache positive introspection cần có TTL an toàn

Với token có `exp` tin cậy:

~~~text
effectivePositiveTtl = min(
    approvedMaxTtl,
    exp - now - safetyMargin
)
~~~

Nếu TTL tính được không dương, **không giữ positive result**. Nếu AS không trả `exp` mà hệ thống có yêu cầu revoke gần thời gian thực, lựa chọn bảo thủ là **không cache completed active result**. Vẫn có thể coalesce các HTTP introspection calls **đang diễn ra** cùng token để tránh thundering herd.

### 11.1. Ví dụ đánh đổi

| Policy | Token còn hạn | Max positive TTL | Ý nghĩa |
| --- | --- | --- | --- |
| No positive cache | 15 phút | 0 giây | Hỏi AS mỗi authentication; vẫn có AS lag. |
| Cache ngắn | 15 phút | 5 giây | Chấp nhận revocation stale window ngắn. |
| Cache ngắn sát exp | 2 giây | 5 giây | Không cache vượt expiration. |
| Cache dài | 30 phút | 10 phút | Cửa sổ token revoked còn được nhận có thể rất lớn. |
| Thiếu exp | Không xác định | 0 theo policy bảo thủ | Tránh TTL không có expiration bound. |

Các con số chỉ minh họa. **Không có quy định chung của RFC 7662 rằng mọi Resource Server phải cache 5 hoặc 60 giây.** Tổ chức phải chọn theo revocation SLO và giới hạn tải của AS.

### 11.2. Không cache theo sub hoặc email

Hai Access Tokens của cùng một người:

~~~text
T1: sub=person-42, scope=orders.read, exp=10:10
T2: sub=person-42, scope=orders.write, exp=10:30
~~~

có thể bị revoke khác nhau. Cache theo `sub` sẽ làm token T1 vô tình nhận metadata/quyền của T2. **Cache key phải phân biệt token cụ thể** và context tin cậy (issuer/introspection client/resource) khi cần.

Không dùng raw Access Token trong logs, metrics hoặc URL. Một phương án dùng **HMAC-SHA256 fingerprint có secret key riêng** làm key nội bộ và namespace theo issuer/resource:

~~~text
cacheKey = HMAC-SHA256(
    secret,
    trustedIssuerId + "\0" +
    resourceId + "\0" +
    rawAccessToken
)
~~~

Secret phải được quản lý an toàn. HMAC key không xóa mọi raw token khỏi heap nếu cache giữ một closure chứa token; cần TTL/memory limits và kiểm soát heap dumps.

### 11.3. Positive, negative và lỗi hạ tầng là ba trạng thái khác nhau

| Kết quả | Chính sách cache |
| --- | --- |
| `active:true` | Cache ngắn, TTL không vượt `exp` và revocation SLO. |
| `active:false` | Có thể negative-cache rất ngắn nếu được duyệt; hạn chế DoS token rác. |
| AS timeout/503/429 | **Không cache như inactive hoặc active.** |
| Introspection client credentials HTTP 401 | Lỗi tích hợp, không suy mọi token user inactive. |
| JSON không hợp lệ | Protocol error, không tạo principal. |
| Active nhưng sai audience | Không cấp quyền resource hiện tại, không dùng cached result cho API khác. |

Negative caching lâu có thể gây hiệu ứng khác nếu trạng thái token sẽ thay đổi theo AS policy (ví dụ `nbf`). Quan trọng nhất: **không giữ một lỗi AS outage như kết luận token đã revoke**.

## 12. Ví dụ Java tính positive-cache TTL

Ví dụ utility tính TTL từ một principal **đã được introspector chuẩn xác minh**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public final class PositiveIntrospectionTtl {

    private final Clock clock;
    private final Duration maxTtl;
    private final Duration safetyMargin;

    public PositiveIntrospectionTtl(
            Clock clock,
            Duration maxTtl,
            Duration safetyMargin) {
        if (maxTtl.isNegative() || safetyMargin.isNegative()) {
            throw new IllegalArgumentException(
                "TTL and margin must be nonnegative");
        }
        this.clock = clock;
        this.maxTtl = maxTtl;
        this.safetyMargin = safetyMargin;
    }

    public Duration calculate(
            OAuth2AuthenticatedPrincipal principal) {
        Object raw = principal.getAttribute("exp");
        Instant expiresAt;

        if (raw instanceof Instant instant) {
            expiresAt = instant;
        } else if (raw instanceof Number seconds) {
            expiresAt = Instant.ofEpochSecond(
                seconds.longValue());
        } else {
            // Không có exp theo contract: không cache.
            return Duration.ZERO;
        }

        Duration remaining = Duration.between(
            clock.instant().plus(safetyMargin),
            expiresAt);

        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }

        return remaining.compareTo(maxTtl) < 0
            ? remaining : maxTtl;
    }
}
~~~

Khởi tạo:

~~~java
PositiveIntrospectionTtl ttl =
    new PositiveIntrospectionTtl(
        Clock.systemUTC(),
        Duration.ofSeconds(5),
        Duration.ofSeconds(1));
~~~

**Đây chỉ là hàm tính TTL, không phải cache hoàn chỉnh.** Khi triển khai caching decorator, vẫn phải xử lý bounded entries, đồng thời cache misses, single-flight, invalidation, token secrecy, error policy và expiry. Không áp dụng utility cho claims do caller tự khai chưa được xác minh.

Một số introspection adapters biểu diễn `exp` dưới dạng `Instant`, adapter khác có thể trả `Number`. Cần căn cứ contract thực tế; không biến string tùy ý thành expiration bằng ép kiểu mơ hồ. Đồng bộ đồng hồ và margin an toàn là cần thiết, nhưng không cộng clock skew theo cách kéo dài quyền sau thời hạn token.

## 13. Invalidation và single-flight có thể cải thiện latency

### 13.1. Push invalidation sau revoke

Nếu AS có **revocation event** đáng tin:

~~~text
AS commits revoke(T)
      |
      v
Authenticated revocation event
      |
      v
Resource Server nodes invalidate cache(T)
      |
      v
Next request introspects T -> active=false
~~~

Một hệ thống event cần:

- Xác thực nguồn sự kiện, không tin payload public.
- Xử lý event lặp, đến muộn, mất event hoặc thứ tự đảo.
- Invalidation tới **mọi serving replicas/gateways**.
- Cache key theo token fingerprint/namespace được kiểm soát.
- Quan sát AS visibility: nếu event đến **trước** khi introspection backends hội tụ, introspection mới có thể vẫn trả `active:true`.
- Khi sự kiện revoke là authoritative, có thể cần **deny tombstone** tạm thời để tránh tái cache `active:true` từ một AS replica chưa thấy revoke.

Chỉ broadcast “evict key” không bảo đảm revoke tức thời nếu AS vẫn báo active trên một backend.

### 13.2. Single-flight khi nhiều callers cùng token

~~~text
50 requests cùng token T, cùng lúc cache miss
          |
          v
One in-flight introspection(T) per instance
          |
          v
50 callers nhận chung kết quả hoặc lỗi
~~~

Single-flight giảm QPS và tránh cache stampede. Nhưng nó **không thay trạng thái token** hoặc yêu cầu TTL:

- Có thể chỉ gộp trong một JVM, không gộp toàn cluster.
- Shared task cần timeout/concurrency bounds.
- Lỗi AS 503 không được biến thành principal mặc định.
- Sau completion, positive cache vẫn phải hết TTL đúng revocation policy.
- Không cache `SecurityContext` của request A để dùng cho request B.

Trong WebFlux có thể dùng một shared `Mono` theo token key cùng chính sách TTL; trong Servlet dùng registry/cache/future phù hợp. **Không tự gọi subscribe/block trên event loop** để cố lấy kết quả nhanh.

## 14. AS outage phải fail closed

~~~text
Client -> Resource Server: Bearer T
Resource Server -> AS: introspect(T)
AS: timeout / HTTP 503

Resource Server không có kết quả mới chứng minh T active.
Resource Server không được tạo authenticated principal tùy ý.
~~~

Ví dụ nguy hiểm:

~~~java
// KHÔNG LÀM.
try {
    return introspector.introspect(token);
} catch (Exception failure) {
    return privilegedDefaultPrincipal();
}
~~~

Thay vào đó:

1. Đặt connect/read/total timeout.
2. Retry chỉ **lỗi transient** được phân loại, có backoff và tổng thời gian tối đa.
3. Không retry vô hạn `active:false` hoặc HTTP 401 do RS client secret sai.
4. Giới hạn đồng thời gọi AS, rate limit và circuit breaker/bulkhead khi cần.
5. Khi không xác thực được, **không cho request đi qua như authenticated**.
6. Ghi metrics `introspection_unavailable` riêng với `token_inactive`.
7. HTTP response phía API có thể map thành lỗi dịch vụ 5xx/503 theo hợp đồng, nhưng không mặc định mọi phiên bản Spring luôn trả cùng một mã.

### 14.1. Stale-on-error cần chính sách được duyệt riêng

Nếu cache active đã hết TTL nhưng AS outage, **tiếp tục phục vụ kết quả `active:true` vô thời hạn** là một hình thức fail-open theo thời gian. Nó làm revocation không được áp dụng đúng SLO.

Một tổ chức có thể chọn bounded stale validation cho endpoint ít nhạy cảm vì yêu cầu availability, nhưng cần **phê duyệt rủi ro, tuổi tối đa tuyệt đối, metrics, audit và kịch bản khôi phục**. Với API nhạy cảm, không chấp nhận token khi AS không thể xác minh thường là quyết định an toàn hơn.

### 14.2. Sai credential introspection khác token user bị revoke

Nếu secret/mTLS certificate của RS hết hạn, AS có thể trả HTTP 401 cho mọi introspection calls. Điều đó **không chứng minh tất cả user tokens inactive**. Phải phân loại đúng upstream client authentication error và điều tra secret rotation/TLS trust/configuration.

## 15. Nhiều lớp cache và nhiều Resource Server replicas

~~~text
Client
  |
  v
API Gateway (có thể cache token validation)
  |
  v
Load Balancer
  |
  +-- RS A (local cache T còn 1s)
  +-- RS B (local cache T còn 20s)
  +-- RS C (không positive cache)
  |
  v
Authorization Server cluster
  +-- introspection node 1
  +-- introspection node 2
  +-- revocation datastore
~~~

Một token T bị revoke có thể được xử lý khác nhau:

- RS A sắp introspect lại.
- RS B còn giữ active cache.
- RS C nhìn thấy AS replication lag.
- Gateway có thể đang accept token trước cả khi request vào Spring.

**Độ trễ toàn cụm phụ thuộc node chậm nhất còn phục vụ traffic**, không phải node đầu tiên trả 401.

### 15.1. Local cache vs distributed cache

| Thiết kế | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Local in-memory cache | Lookup nhanh, không thêm cache network dependency. | Mỗi node có TTL/invalidation riêng. |
| Redis/distributed cache | Chia sẻ result, có thể tăng hit rate. | Stale metadata lan rộng; cần ACL, TTL, namespace, invalidation. |
| Không positive cache | Không stale do RS result cache. | Tăng AS load/latency/availability dependency. |
| Push revocation invalidation | Có thể chặn sớm hơn TTL. | Event authenticity, ordering, delivery và AS visibility. |
| Centralized status gate | Có thể tăng consistency. | Thêm network dependency, phải fail closed. |

Đừng quên **gateway hoặc service mesh** cũng có thể xác thực/caching trước RS. Tối ưu TTL ở Spring không giải quyết được một gateway giữ active cache lâu hơn.

### 15.2. Trust namespace của cache

Một kết quả introspection phải được hiểu trong ngữ cảnh:

~~~text
trusted issuer / introspection endpoint
Resource Server client identity
expected audience/resource
token identity
~~~

AS có thể trả `active:false` khi caller không được phép introspect token, dù token còn hợp lệ tại resource khác. Không dùng result active của `orders-api` để cấp quyền cho `billing-api` chỉ vì raw token string giống nhau.

## 16. Request đã xác thực trước revoke không tự bị rollback

Ví dụ:

~~~text
10:00:00.000  POST /api/transfers bắt đầu
10:00:00.020  introspect T -> active=true
10:00:00.050  Scope/tenant checks pass
10:00:00.100  Domain service mở transaction
10:00:00.200  AS revoke T
10:00:00.300  Introspection mới trả active=false
10:00:01.000  Transaction ban đầu commit
~~~

Revocation có thể chặn **request mới** nhưng không tự biến Authentication đã dùng tại T+0.020s thành một rollback transaction. Tùy loại nghiệp vụ, phải thiết kế:

- Kiểm tra local user/tenant/token revocation epoch gần điểm ghi/commit.
- Transaction consistency và isolation phù hợp.
- Idempotency key cho thao tác có side effects.
- Audit và cách truy vấn trạng thái sau client timeout.
- Cơ chế ngắt WebSocket/SSE hoặc background jobs nếu yêu cầu.
- Saga/outbox/compensation cho thao tác ngoài database transaction.

**Client disconnect cũng không phải revoke.** Browser đóng tab hoặc hủy fetch không tự gửi OAuth revocation request tới AS, và không chứng minh remote side effect đã rollback.

### 16.1. exp hết trong lúc xử lý

JWT/opaque token có thể được kiểm tra expiration lúc request authentication. Nếu `exp` đến trong lúc một operation dài chạy, operation đó **không nhất thiết tự dừng**. Với tác vụ dài, cần chính sách reauthorization ở các bước nhạy cảm.

## 17. Logout, disable account và tenant suspension khác token revoke

Giả sử:

~~~text
Introspection của T: active=true
Local account: SUSPENDED
Tenant membership: REMOVED
~~~

API **vẫn phải từ chối theo domain authorization**, không đợi AS đổi `active`. Ngược lại, Logout ở frontend không tự cập nhật revocation state của AS nếu không thực hiện workflow tương ứng.

| Sự kiện | Thay đổi | Cần lưu ý |
| --- | --- | --- |
| Access Token revoked | Token cụ thể không còn được AS chấp nhận. | RS phải quan sát state mới qua introspection/online gate. |
| Refresh Token revoked | Client không dùng Refresh Token đó nữa. | AT cũ có thể còn active theo AS policy. |
| OIDC logout | OP/RP session kết thúc theo logout mechanism. | Không suy tất cả AT ở mọi RS bị revoke. |
| Local user disabled | Account không được sử dụng theo hệ thống nội bộ. | Domain gate phải chặn dù AT còn active. |
| Tenant suspended/revoked | Quyền truy cập của tenant trong SaaS bị dừng. | Per-request tenant gate/cache invalidation và cluster consistency. |

Nếu một ứng dụng có cả **OIDC Login session cookie** và **Bearer Resource Server API**, cần kiểm thử riêng logout/session invalidation và revocation; không dùng một flag frontend để đại diện toàn bộ lifecycle credentials.

## 18. HTTP 401, 403 và lỗi introspection

### 18.1. Token inactive

Response theo Bearer semantics có thể:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Đây là lỗi **authentication**; Spring Security header/body chính xác có thể khác theo exception handler/version.

### 18.2. Token active nhưng thiếu scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Đây là lỗi **authorization**, không phải dấu hiệu token bị revoke. Refresh một Access Token cùng grant không tự tạo scope mới.

### 18.3. Introspection outage

~~~text
AS -> RS: HTTP 503, timeout hoặc TLS failure
RS: không xác minh được token
~~~

RS phải **fail closed**. Có thể trả 5xx/503 theo API contract khi dependency xác thực không sẵn sàng, nhưng không khẳng định mọi lỗi introspection mặc định map cùng một HTTP status trong mọi phiên bản Spring.

### 18.4. Không tiết lộ nguyên nhân nội bộ

Không trả raw token, `sub`, email, người revoke, private key, client secret, upstream stack trace hoặc JWKS details cho unauthenticated caller. Body lỗi nên ngắn gọn, thông tin kỹ thuật chi tiết nằm trong audit/log có phân quyền.

## 19. Kiểm thử trạng thái active chuyển thành revoked

Một test chỉ stub:

~~~text
Introspection -> {"active":false}
API -> 401
~~~

là cần thiết nhưng **không chứng minh độ trễ thu hồi**. Phải kiểm thử **state transition, cache TTL, AS propagation và nhiều nodes**.

### 19.1. Ma trận

| Test | Kết quả cần kiểm chứng |
| --- | --- |
| T active, scope đủ | API qua auth và HTTP rule. |
| T active=false ngay từ đầu | API 401, controller không chạy. |
| T active rồi revoke | API từ chối sau cửa sổ latency đã cam kết. |
| Positive cache được warm | Cache hit trước TTL; introspect lại sau TTL. |
| Revoke ngay trước cache refresh | Bound tính cả AS visibility + TTL. |
| AS trả `active:"false"` string | Không tạo principal. |
| AS introspection HTTP 401 | Lỗi Resource Server credentials, không coi mọi token revoked. |
| AS timeout/503 | Fail closed, không dùng fallback principal. |
| T active thiếu write scope | 403, không nhầm inactive. |
| T active nhưng local account bị khóa | Domain policy từ chối. |
| Revoke Refresh Token | Xác nhận cascade Access Token theo AS thực tế. |
| JWT local decode, AS revoke T | Không hứa tự detect nếu thiếu online check. |
| Gateway có cached active | Kiểm tra TTL ngoài Spring. |
| Multiple RS replicas | Mọi serving node đạt revocation deadline. |
| Request đã qua auth rồi revoke | Kết quả theo in-flight/transaction policy. |

## 20. Ví dụ fake OpaqueTokenIntrospector để kiểm tra HTTP transition

Một fake test introspector giúp xác minh Spring Security **nhận kết quả inactive và từ chối token** trong ứng dụng cục bộ:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class SwitchableTestIntrospector
        implements OpaqueTokenIntrospector {

    private final AtomicBoolean active = new AtomicBoolean(true);

    public void setActive(boolean value) {
        active.set(value);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (!"test-access-token".equals(token)
                || !active.get()) {
            throw new BadOpaqueTokenException(
                "Token is inactive in this test");
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            "person-42",
            Map.of("sub", "person-42", "scope", "orders.read"),
            List.of(new SimpleGrantedAuthority(
                "SCOPE_orders.read")));
    }
}
~~~

Đưa fake thành một bean `OpaqueTokenIntrospector` **chỉ trong test context**, giữ API security filter chain đã định nghĩa. Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(RevocationTransitionTest.FakeConfig.class)
class RevocationTransitionTest {

    @Autowired MockMvc mvc;
    @Autowired SwitchableTestIntrospector fake;

    @TestConfiguration
    static class FakeConfig {
        @Bean
        SwitchableTestIntrospector fakeIntrospector() {
            return new SwitchableTestIntrospector();
        }
    }

    @Test
    void tokenFailsAfterStateChanges() throws Exception {
        fake.setActive(true);

        mvc.perform(get("/api/orders/42")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer test-access-token"))
            .andExpect(status().isOk());

        fake.setActive(false);

        mvc.perform(get("/api/orders/42")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer test-access-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Điều kiện chạy ví dụ:** test application context có controller cho `GET /api/orders/42` trả 200, sử dụng security chain nhận opaque token và **không có bean introspector khác gây mơ hồ**. Không đưa fake này vào production.

**Giới hạn:** fake chỉ mô phỏng cờ active **trong process**, không gửi HTTP introspection, không test cache/AS replication và không đo revocation latency thực tế.

## 21. Integration test qua HTTP introspection server

Muốn test thật, dựng **WireMock/MockWebServer** hoặc HTTP test server giả lập Authorization Server:

~~~text
POST /oauth2/introspect, token=reader
  -> HTTP 200
     {"active":true,"scope":"orders.read",
      "sub":"person-42","aud":["orders-api"],"exp":...}

POST /oauth2/introspect, token=revoked
  -> HTTP 200 {"active":false}

POST /oauth2/introspect, token=bad-schema
  -> HTTP 200 {"active":"true"}

POST /oauth2/introspect, token=down
  -> HTTP 503 Service Unavailable
~~~

### 21.1. Kịch bản transition

1. Dựng AS fixture có token state có thể đổi.
2. Cấu hình Resource Server thực sự dùng HTTP introspection endpoint của fixture.
3. Cho token T trả `active:true` với `exp` còn xa và scope phù hợp.
4. Gửi Bearer T qua Spring Security filters, **không dùng `opaqueToken()` helper**.
5. Kiểm tra API qua authentication, fixture nhận POST và cache được warm nếu có.
6. Tại mốc `t_commit`, đổi fixture thành `active:false`.
7. Tiếp tục gửi Bearer T theo chu kỳ; ghi status và timestamps từng node.
8. Xác nhận sau TTL/invalidation, API phải 401 và controller không chạy.
9. Lặp lại khi AS visibility bị làm chậm, 503, timeout và nhiều replicas.

**Test thời điểm xấu nhất:** AS replica vẫn trả active=true gần trước khi trạng thái revoke hội tụ, RS vừa cache lại. Tình huống này có thể tạo delay gần bằng **AS visibility lag + một full cache TTL**.

### 21.2. MockMvc opaqueToken() không gọi introspection

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`opaqueToken()` của `spring-security-test` tạo Authentication test đã xác thực. Nó phù hợp kiểm tra HTTP authorization nhưng **không chứng minh `active:false`, cache TTL hay revocation propagation**. Để đo revocation, phải gửi raw Bearer token qua introspector thật/test server.

## 22. Đo revocation latency theo thời gian

Một test đo nên ghi:

~~~text
experiment_id
token_fingerprint (nội bộ, không raw token)
issuer/resource/token_type
time_revoke_requested
time_revoke_committed_at_AS (nếu AS cho phép quan sát)
time_introspection_first_false
time_last_accepted_request_per_node
time_first_denied_request_per_node
cache_hit/miss, TTL, node, region, gateway
error_category
~~~

### 22.1. Lịch probe minh họa

~~~text
T-2s  Issue test Access Token T; exp > test window
T-1s  Warm Resource Server cache
T0    Commit revoke(T) ở test AS
T+.1s Probe every RS node with Bearer T
T+.5s Probe every RS node with Bearer T
T+1s  Probe every RS node with Bearer T
T+2s  Probe every RS node with Bearer T
T+5s  Probe every RS node with Bearer T
T+6s  Probe every RS node with Bearer T
T+10s Probe every RS node with Bearer T
~~~

Khi probe định kỳ, **thời điểm chuyển trạng thái thật nằm giữa lần accept cuối và lần deny đầu**. Giá trị `t_first_deny - t_commit` là một **cận trên quan sát** theo lịch test, không phải timestamp chính xác. Ghi rõ sampling interval, clock synchronization và network/processing delays.

Một probe qua load balancer không thể tự xác nhận từng replica nếu không biết request thực sự đến node nào.

### 22.2. Metrics cần có

~~~text
introspection_requests_total{outcome=active|inactive|error}
introspection_latency_seconds
introspection_upstream_errors_total{category=...}
introspection_cache_hit_total
introspection_cache_miss_total
introspection_cache_entries
authentication_failures_total{category=...}
authorization_denied_total{category=...}
revocation_visibility_lag_seconds
revocation_effective_denial_lag_seconds
~~~

Không đưa raw token, HMAC fingerprint, email, `sub` hoặc toàn bộ claims vào labels; chúng nhạy cảm và có cardinality cao. Dùng request ID, issuer cấu hình và error categories khi phù hợp với bảo mật dữ liệu.

## 23. Một runbook khi token đã revoke vẫn gọi được API

1. **Xác định đúng token/issuer/resource** bằng thông tin nội bộ an toàn; không chia sẻ raw credential.
2. **Xác minh revoke workflow:** revoke Access Token hay Refresh Token? AS commit lúc nào? Có cascade không?
3. **Truy vấn introspection theo quyền được cấp** từ context RS/test an toàn để xác nhận AS hiện trả `active` gì.
4. Nếu AS vẫn `active:true`, điều tra AS datastore replication, request revoke sai token hoặc chính sách grant.
5. Nếu AS đã `active:false` nhưng API vẫn thành công, điều tra **positive cache, gateway, security chains** và replica cụ thể.
6. Xác định request đã qua authentication **trước hay sau** revoke.
7. Kiểm tra local account/tenant status và domain authorization.
8. Kiểm tra sự cố AS upstream có bị biến thành fail-open không.
9. Ghi timestamps, TTL, last accepted request, first denied request trên từng node.
10. Đưa nguyên nhân vào SLO/test suite và điều chỉnh cache/invalidation policy.

### 23.1. Bảng troubleshooting

| Triệu chứng | Câu hỏi ưu tiên |
| --- | --- |
| Revoke endpoint 200 nhưng introspection active=true | Revoke đúng token? AS replication/cascade policy thế nào? |
| Introspection active=false nhưng API 200 | Positive cache ở RS/gateway còn TTL? Request vào chain nào? |
| Chỉ một số requests 200 sau revoke | Có nhiều replicas/regions với cache khác nhau? |
| JWT vẫn hoạt động sau AS revoke | API có online revocation check hay chỉ local decode? |
| Logout xong token còn active | Có gọi token revocation không, hay chỉ xóa session/frontend state? |
| Account disabled nhưng token active | Có local/domain account gate không? |
| API 403 sau revoke | Có phải thiếu scope/domain permission thay vì inactive? |
| Mọi token 401 cùng lúc | RS introspection credentials/AS outage có vấn đề? |
| API treo khi AS chậm | Connect/read timeout, retry budget và bounded concurrency? |
| Cache active tồn tại quá `exp` | TTL tính sai NumericDate, clock skew hoặc stale-on-error? |
| Revoke mới nhưng có active gần 1 TTL sau | AS visible lag khiến cache vừa refresh trước khi AS hội tụ? |

## 24. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Xem introspection HTTP 200 nghĩa token hợp lệ. | 200 vẫn có thể `active:false`. | Kiểm tra boolean `active`. |
| Coi `active:false` luôn là expired. | Che revocation/unknown/not permitted. | Không suy nguyên nhân ngoài thông tin AS trả. |
| Coi HTTP 200 revoke nghĩa mọi RS đã cập nhật. | Cache/replica chưa hội tụ. | Đo effective denial end-to-end. |
| Cache `active:true` đến `exp` dài hàng giờ. | Token revoked vẫn truy cập lâu. | TTL giới hạn theo revocation SLO, không chỉ exp. |
| Cache theo user `sub` thay token. | Trộn scope/revocation của các tokens khác nhau. | Key theo token identity và trust namespace. |
| Cache 503 như inactive. | Lẫn outage với state, hồi phục kém. | Tách errors khỏi token state. |
| Khi AS timeout tự chấp nhận token. | Fail-open authentication. | Fail closed, xử lý lỗi dịch vụ. |
| Chỉ test một node. | Node khác vẫn accept. | Probe mọi serving replicas/regions. |
| Chỉ dùng MockMvc `opaqueToken()` để test revoke. | Bỏ qua HTTP introspection. | Test server với `active` chuyển trạng thái. |
| Quên gateway có token cache riêng. | Backend TTL không quyết định toàn hệ thống. | Audit toàn bộ authentication layers. |
| Revoke Refresh Token rồi coi AT cũ invalid. | Cascade khác nhau theo AS. | Kiểm thử đúng token lifecycle. |
| OIDC Logout đồng nghĩa revoke mọi AT. | Login session và AT có lifecycle khác. | Thiết kế session/logout/token revoke riêng. |
| JWT local decoder tự biết token bị revoke. | JWT còn chữ ký và `exp`. | Denylist/epoch/online check khi cần. |
| Chỉ giảm cache TTL mà không đo AS visibility. | Lag upstream vẫn tồn tại. | Đo `t_visible` và `t_cache_expiry`. |
| Active token được phép đọc mọi tenant. | BOLA/cross-tenant leak. | Tenant/owner/domain authorization. |
| Client ngắt kết nối nghĩa token revoked. | Transport không thay credential state. | Thực hiện revoke ở AS theo flow. |
| Log token để debug. | Rò rỉ Bearer secret. | Error category, request ID và audit an toàn. |

## 25. Lộ trình triển khai trong dự án

1. **Thống nhất token contract:** Access/Refresh/ID Tokens, issuer, audience, scope, exp, revocation và logout semantics.
2. **Thiết kế introspection:** HTTPS URI đáng tin, Resource Server client authentication, `active` JSON boolean, metadata cần thiết.
3. **Xác định mốc trạng thái ở AS:** revocation commit và độ trễ để mọi introspection backend trả inactive.
4. **Đặt revocation SLO có thể đo:** mốc bắt đầu/kết thúc, toàn cluster, loại token, xử lý in-flight requests.
5. **Cấu hình Spring Security:** `OpaqueTokenIntrospector` chuẩn và Bearer security chain; authentication không thay authorization.
6. **Giới hạn cache:** positive TTL ngắn và không vượt `exp`, negative cache có chủ đích, không cache outage như state.
7. **Kiểm soát phụ thuộc:** timeout, retry transient có giới hạn, single-flight/rate limit/bulkhead khi tải cao.
8. **Thiết kế invalidation:** event authenticity, ordering và toàn bộ RS/gateway replicas khi SLA yêu cầu.
9. **Đánh giá JWT/web session paths:** offline JWT, OIDC sessions, tenant disable và streams cần chính sách riêng.
10. **Test transitions/worst-case:** active → revoke → AS false → cache expiry → API deny; bao gồm 503 và nhiều replicas.
11. **Đo và giám sát:** cache hit/miss, introspection errors, last accept, first deny, revocation lag.
12. **Chuẩn bị emergency response:** disable user/tenant, invalidate caches/sessions, drain stale nodes và audit transactions.

**Ghi nhớ:** `active:false` có nghĩa **Resource Server không được chấp nhận token tại thời điểm introspection**, nhưng **AS đã commit revoke không có nghĩa mọi Resource Servers đều biết ngay**. Độ trễ giữa hai sự kiện đến từ **AS visibility, positive-cache TTL, nhiều lớp gateway/replica và request đang chạy**. Trong Spring Security, cần giữ ranh giới **introspection → Authentication → scope/domain authorization**, **fail closed** khi không xác minh được token, và biến revocation latency thành **một SLO có thể đo, kiểm thử và giám sát** thay vì lời hứa không có cơ sở.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — OpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html).
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html).
- [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
