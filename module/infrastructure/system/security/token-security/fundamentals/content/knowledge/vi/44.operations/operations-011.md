# Rate limit token endpoint

Token Endpoint là một điểm nhạy cảm về bảo mật và khả năng sẵn sàng. Endpoint này có thể phát hành access token, xoay vòng refresh token và xử lý thông tin xác thực của client. Nếu không giới hạn tốc độ phù hợp, kẻ tấn công có thể dò credential, thử lại refresh token, làm cạn tài nguyên xác minh chữ ký hoặc tạo tải lớn lên Authorization Server.

Bài học thuộc chương **Operations** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là thiết kế, triển khai và vận hành rate limit cho OAuth 2.0 Token Endpoint theo từng loại grant và client; phản hồi đúng khi vượt ngưỡng; tránh account enumeration và khóa nhầm người dùng; đồng thời quan sát, kiểm thử và điều chỉnh chính sách theo tải thực tế.

## 1. Vì sao Token Endpoint cần rate limit?

Token Endpoint thường xử lý các thao tác có chi phí và tác động bảo mật cao:

- Xác thực confidential client bằng client secret, private key JWT, mTLS hoặc cơ chế client authentication khác.
- Kiểm tra authorization code, PKCE verifier, redirect/client binding và trạng thái code đã dùng.
- Xác minh refresh token, rotation, token family và trạng thái thu hồi.
- Cấp access token, ID token hoặc token khác theo grant và policy.
- Kiểm tra quyền, scope, tenant, audience và các điều kiện phát hành.

Một client lỗi có thể gửi hàng nghìn request do retry loop. Một kẻ tấn công có thể thử nhiều credential, client secret hoặc refresh token. Một đợt request lớn cũng có thể làm tăng tải lên database, cache, HSM/KMS, hệ thống introspection và dịch vụ phát hành khóa.

Rate limit giúp giới hạn chi phí của một nguồn request và bảo vệ năng lực phục vụ chung. Nó là một lớp phòng vệ bổ sung; không thay thế xác thực client, PKCE, refresh token rotation, phát hiện credential stuffing, account lockout theo chính sách hoặc cơ chế chống replay.

## 2. Xác định đúng bề mặt cần giới hạn

Không phải mọi endpoint trong Authorization Server đều có cùng đặc tính. Cần phân loại trước khi đặt ngưỡng:

| Endpoint / grant | Rủi ro chính | Khóa giới hạn phù hợp |
| --- | --- | --- |
| Token Endpoint — authorization code | Thử lại code, client lỗi, request burst | Client, nguồn mạng, code fingerprint và cửa sổ thời gian |
| Token Endpoint — refresh token | Credential theft, refresh token reuse, retry đồng thời | Client, subject, refresh token family fingerprint và nguồn mạng |
| Token Endpoint — client credentials | Client secret/private key bị lộ, workload phát request bất thường | Client identity, workload, tenant/resource và nguồn mạng |
| Token Endpoint — device code | Polling quá nhanh hoặc client không tuân thủ interval | Device code/session và client; tuân thủ interval của device flow |
| Token Endpoint — token exchange | Lạm dụng quyền đổi token, tạo tải xác minh và phát hành | Client, subject/actor, audience/resource và grant |
| Authorization endpoint / login | Credential stuffing và account enumeration | Nguồn mạng, tài khoản sau chuẩn hóa, client và risk signals |

Rate limit tại Token Endpoint không thay thế giới hạn riêng cho Authorization Endpoint, login, password reset, revocation, introspection hay API nghiệp vụ. Mỗi luồng có chi phí, ngữ nghĩa và mức rủi ro khác nhau.

## 3. Thiết kế nhiều chiều rate limit

Giới hạn chỉ theo IP thường không đủ. Một văn phòng, trường học hoặc nhà mạng có thể dùng chung NAT; ngược lại, attacker có thể đổi IP qua proxy. Nên kết hợp nhiều chiều và chọn khóa phù hợp với grant:

| Dimension | Dùng để giới hạn | Lưu ý |
| --- | --- | --- |
| `client_id` / authenticated client | Tốc độ request của một OAuth client | Với confidential client, xác thực client trước khi áp dụng quota riêng |
| `subject_ref` | Hành vi gắn với người dùng | Chỉ dùng khi subject đã được xác định đáng tin cậy; pseudonymize key |
| `source_ip` hoặc IP prefix | Burst và dò quét từ một nguồn | Xử lý NAT, IPv6 prefix, VPN, proxy và trusted ingress |
| `grant_type` | Ngân sách riêng cho từng loại grant | Tránh một grant chiếm hết ngân sách của grant khác |
| `refresh_family_ref` | Lặp refresh trên cùng token family | Fingerprint bảo vệ bằng HMAC; không dùng raw refresh token |
| `tenant_ref` / resource | Giới hạn client theo tenant hoặc tài nguyên | Chỉ dùng tenant/resource đã được xác minh |
| `workload_ref` | Giới hạn service-to-service | Gắn với workload identity hoặc client certificate đã xác minh |
| Global capacity | Bảo vệ tổng năng lực Authorization Server | Có thể áp dụng tại gateway và tầng ứng dụng |

Một policy thường có ít nhất ba lớp:

1. **Coarse limit:** giới hạn tổng request theo nguồn mạng và route, giúp chặn burst rất lớn trước khi tiêu tốn nhiều tài nguyên.
2. **Identity limit:** giới hạn theo client đã xác thực, subject hoặc workload để một identity không chiếm dụng hệ thống.
3. **Operation limit:** giới hạn riêng cho refresh, code exchange, device polling hoặc token exchange theo chi phí và rủi ro của thao tác.

Một request có thể phải vượt qua nhiều bucket. Chỉ khi tất cả bucket cần thiết còn quota thì mới tiếp tục xử lý. Việc trừ quota ở nhiều bucket cần có tính nguyên tử hoặc cơ chế bù trừ rõ ràng để tránh request bị trừ một bucket nhưng không trừ bucket còn lại.

## 4. Chính sách theo từng grant

### 4.1. Authorization code grant

Authorization code là credential ngắn hạn và chỉ dùng một lần. Token Endpoint cần xác minh code thuộc đúng client, redirect URI, issuer/session và PKCE verifier khi áp dụng. Rate limit có thể áp dụng theo:

- Client đã xác thực hoặc client ID trong request.
- IP/prefix tại ingress đáng tin cậy.
- Fingerprint của authorization code để giới hạn việc thử lại cùng code.
- Tần suất lỗi `invalid_grant` theo client và nguồn.

Không trả thông tin chi tiết cho biết code thuộc tài khoản nào hoặc đã được dùng bởi client nào. Khi code đã được sử dụng, request lặp phải bị từ chối theo quy tắc one-time use; rate limit không thay thế trạng thái chống replay của code.

### 4.2. Refresh token grant

Refresh token thường có thời gian sống dài và quyền xin access token mới. Nên giới hạn đồng thời theo client, subject/session, refresh token family và nguồn request. Nếu refresh token rotation được bật, việc dùng lại token cũ sau khi đã xoay vòng là tín hiệu bảo mật riêng và phải kích hoạt quy trình phát hiện reuse.

Không chỉ tăng quota để giải quyết retry storm. Client nên đồng bộ việc refresh, tránh nhiều thread cùng dùng một refresh token, cập nhật token mới một cách nguyên tử và không gửi lại token cũ sau khi đã nhận token mới.

### 4.3. Client credentials grant

Client credentials thường đại diện cho workload/service. Quota nên gắn với authenticated client hoặc workload identity, đồng thời có thể phân tách theo tenant và audience/resource. Nếu một service cần lưu lượng lớn, cấp quota theo hợp đồng và capacity plan; không dùng một quota rất cao chung cho mọi client.

Nếu client authentication thất bại liên tục, giới hạn theo client identifier và nguồn mạng ở lớp phù hợp. Tránh để request giả mạo một `client_id` có thể làm cạn quota của client hợp lệ; bucket trước xác thực nên độc lập với bucket của authenticated client.

### 4.4. Device authorization grant

Device client phải poll theo `interval` do Authorization Server trả về. Nếu poll quá nhanh, áp dụng ngữ nghĩa `slow_down` của device authorization flow và tăng interval theo quy định; không coi đây chỉ là lỗi 429 chung. Vẫn cần coarse rate limit theo client và nguồn để chống abuse.

### 4.5. Token exchange

Token exchange có thể liên quan đến actor token, subject token, audience và resource. Rate limit cần gắn với client đã xác thực, grant, actor/subject đã được kiểm tra và resource đích. Không dùng giá trị actor hoặc subject do request tự khai làm identity key trước khi xác minh token tương ứng.

## 5. Chọn thuật toán rate limiter

### Token bucket

Token bucket duy trì một số token quota và tốc độ refill. Mỗi request tiêu thụ một đơn vị (hoặc chi phí tương ứng); nếu bucket không đủ, request bị trì hoãn hoặc từ chối.

- Ưu điểm: cho phép burst ngắn trong khi giữ tốc độ trung bình.
- Nhược điểm: cần xác định capacity và refill rate; cấu hình sai có thể cho burst lớn hơn khả năng xử lý.
- Phù hợp: API token có tải biến động nhưng cần giới hạn tốc độ trung bình.

### Fixed window counter

Đếm request trong một cửa sổ cố định, ví dụ 60 giây. Thuật toán đơn giản và ít tốn bộ nhớ, nhưng có thể cho phép burst ở ranh giới hai cửa sổ: client gửi gần đủ quota ở cuối cửa sổ và tiếp tục ngay đầu cửa sổ kế tiếp.

### Sliding window

Sliding log hoặc sliding counter đánh giá request trong cửa sổ trượt. Nó giảm hiện tượng burst ở ranh giới cửa sổ nhưng có thể tốn bộ nhớ hoặc cần xấp xỉ. Dùng khi quota cần công bằng hơn theo thời gian thực.

### Leaky bucket / queue

Leaky bucket làm phẳng tốc độ xử lý bằng cách xếp request vào hàng đợi. Phù hợp với một số tác vụ có thể chờ, nhưng Token Endpoint thường cần phản hồi nhanh và không nên giữ hàng đợi dài cho request xác thực. Khi quá tải, từ chối sớm thường an toàn hơn.

| Thuật toán | Burst | Độ phức tạp | Khi phù hợp |
| --- | --- | --- | --- |
| Token bucket | Có kiểm soát | Thấp | API có burst ngắn và tốc độ trung bình xác định |
| Fixed window | Có thể burst ở biên | Thấp | Quota đơn giản, chấp nhận sai số biên |
| Sliding window | Hạn chế burst biên | Trung bình/cao | Cần quota công bằng trong cửa sổ trượt |
| Leaky bucket | Làm phẳng | Trung bình | Có thể xếp hàng và xử lý đều |

Không có thuật toán tốt nhất cho mọi grant. Có thể dùng token bucket cho quota client, sliding counter cho chống brute force và global concurrency limit để bảo vệ database/HSM.

## 6. Triển khai phân tán và tính nguyên tử

Trong môi trường nhiều instance, rate limit chỉ lưu trong memory của từng process sẽ không phản ánh tổng lưu lượng. Nếu có 10 instance và mỗi instance cho phép 100 request/phút, client có thể đạt gần 1.000 request/phút khi traffic được phân phối đều.

Một bộ giới hạn phân tán thường dùng Redis hoặc một quota service chuyên dụng:

1. Chuẩn hóa identity key và operation.
2. Tính bucket key từ các dimension đã xác minh.
3. Thực hiện đọc trạng thái, refill và trừ quota trong một thao tác nguyên tử.
4. Trả về `allowed`, `remaining` và thời gian có thể thử lại.
5. Ghi metric/event mà không làm lộ identity key gốc.

Ví dụ key được pseudonymize:

~~~text
rl:v2:token:client:<HMAC(client_id)>:refresh
rl:v2:token:source:<HMAC(ip_prefix)>:all
rl:v2:token:family:<HMAC(refresh_family_id)>:refresh
rl:v2:token:global:issue
~~~

Không đưa raw IP, email, subject hoặc refresh token vào tên Redis key. HMAC key phải được quản lý như secret, có version để xoay vòng và không dùng chung với key ký token.

Pseudo-code cho token bucket:

~~~text
function allow(key, capacity, refill_per_second, cost, now):
    state = atomic_read(key)
    elapsed = max(0, now - state.updated_at)
    tokens = min(capacity,
                 state.tokens + elapsed * refill_per_second)

    if tokens < cost:
        retry_after = (cost - tokens) / refill_per_second
        atomic_write(key, tokens, now)
        return DENY(retry_after)

    tokens = tokens - cost
    atomic_write(key, tokens, now)
    return ALLOW(tokens)
~~~

Đây là mô tả thuật toán; triển khai phân tán phải đặt toàn bộ phép đọc, tính refill và ghi trong một script/transaction nguyên tử. Cần xử lý đồng hồ, key TTL, precision, burst capacity, retry-after rounding và trường hợp nhiều bucket được kiểm tra cùng lúc.

### Chọn fail-open hay fail-closed

Nếu Redis/quota service lỗi, hệ thống phải có chính sách được xác định trước:

- **Fail-closed:** từ chối hoặc trả lỗi tạm thời khi không thể xác minh quota. Bảo vệ tốt hơn trước abuse nhưng có thể làm Token Endpoint ngừng hoạt động khi limiter gặp sự cố.
- **Fail-open có giới hạn:** tiếp tục cho phép trong một ngân sách khẩn cấp nhỏ, kết hợp coarse limit tại gateway và giới hạn concurrency. Tăng availability nhưng có thể giảm khả năng chống abuse.

Không nên mặc định fail-open toàn bộ khi Redis lỗi. Cũng không nên fail-closed mọi request mà không có dự phòng, vì rate limiter trở thành điểm lỗi đơn. Chọn policy theo grant, client và mức độ rủi ro; có circuit breaker, local emergency budget và alert cho tình trạng degraded mode.

## 7. Thứ tự áp dụng limiter trong request pipeline

~~~mermaid
flowchart TD
    A["Nhận HTTPS request tại ingress"] --> B["Coarse limit theo route và nguồn"]
    B -->|Vượt ngưỡng| R["429 Too Many Requests"]
    B -->|Cho phép| C["Kiểm tra cấu trúc request và grant_type"]
    C --> D["Xác thực OAuth client nếu grant yêu cầu"]
    D --> E["Identity limit theo client/workload đã xác minh"]
    E -->|Vượt ngưỡng| R
    E --> F["Kiểm tra code/refresh token/grant và quyền"]
    F --> G["Operation limit theo subject/family/resource"]
    G -->|Vượt ngưỡng| R
    G --> H["Phát hành hoặc xoay vòng token"]
    H --> I["Ghi audit/security event và metrics"]
    I --> J["Trả token response"]
~~~

Đây là thứ tự tham khảo, không phải mọi grant đều có đủ mọi bước. Coarse limit cần chạy sớm để bảo vệ parser và xác minh mật mã. Identity limit cần dùng identity đã xác thực; không được tin `client_id`, subject hoặc tenant do request tự khai khi chưa xác minh. Một số limiter có thể được kiểm tra trước và sau authentication với key khác nhau.

Nếu phát hành token thất bại sau khi đã tiêu quota, cần quyết định rõ có hoàn lại quota hay không. Với chống brute force, request thất bại vẫn nên tính vào quota. Với quota tính theo token phát hành thành công, có thể dùng một bucket riêng cho successful issuance. Không trộn hai mục đích trong cùng counter.

## 8. Phản hồi khi vượt rate limit

HTTP `429 Too Many Requests` là status phù hợp để báo client gửi quá nhiều request trong một khoảng thời gian. Có thể gửi `Retry-After` để hướng dẫn thời điểm thử lại. RFC 9331 định nghĩa các HTTP RateLimit fields như `RateLimit-Limit`, `RateLimit-Remaining` và `RateLimit-Reset`; chỉ công bố khi policy cho phép và giá trị phản ánh đúng bucket liên quan.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Cache-Control: no-store
Content-Type: application/json

{
  "error": "rate_limited",
  "error_description": "Too many token requests. Retry later."
}
~~~

`rate_limited` trong ví dụ là mã lỗi mở rộng do hệ thống định nghĩa; OAuth 2.0 không quy định đây là một error code chuẩn cho mọi Token Endpoint. Hãy mô tả rõ trong hợp đồng API. Không dùng `invalid_grant` hoặc `invalid_client` để che lỗi quota, vì client có thể xử lý sai và đội vận hành mất khả năng phân biệt.

Một số nguyên tắc:

- Không trả số lần thử còn lại theo tài khoản chưa xác thực nếu điều đó giúp attacker suy luận trạng thái tài khoản.
- Không tiết lộ quota nội bộ, client khác hoặc subject khác.
- Dùng `Cache-Control: no-store` cho response liên quan đến token và lỗi có thể chứa thông tin nhạy cảm.
- Giá trị `Retry-After` nên dựa trên thời điểm quota được phục hồi, có giới hạn hợp lý.
- Nếu limiter đang degraded, trả lỗi tạm thời phù hợp và phát alert nội bộ; không giả vờ request đã bị rate limit khi thực tế là lỗi dependency.

### Client nên retry thế nào?

Client phải tôn trọng `Retry-After`, áp dụng exponential backoff có jitter và giới hạn số lần retry. Không retry liên tục ngay lập tức khi nhận 429. Không retry vô hạn với `invalid_client`, `invalid_grant`, `invalid_scope` hoặc request sai cấu trúc.

Với refresh token rotation, client cần bảo đảm chỉ một luồng refresh đang chạy cho mỗi phiên/token family. Nếu hai request đồng thời gửi cùng refresh token, request thứ hai có thể bị coi là reuse. Dùng cơ chế single-flight/lock cục bộ và lưu token mới một cách nguyên tử trước khi phát sinh request tiếp theo.

## 9. Tránh account enumeration và khóa nhầm người dùng

Rate limit là một công cụ chống abuse nhưng có thể bị dùng để gây từ chối dịch vụ nếu attacker cố tình làm cạn quota của nạn nhân. Một chính sách chỉ giới hạn theo username/email có thể cho phép attacker khóa tài khoản người khác.

Giảm rủi ro bằng cách:

- Kết hợp IP/prefix, client, device/risk signal và identity đã xác thực thay vì chỉ khóa theo account identifier.
- Chuẩn hóa identifier trước khi tạo key để tránh bypass bằng chữ hoa/thường hoặc Unicode normalization.
- Với identifier chưa xác thực, dùng bucket riêng và không công khai trạng thái khóa hoặc quota của tài khoản.
- Dùng step-up authentication hoặc challenge khi rủi ro tăng, thay vì khóa cứng ngay với tín hiệu yếu.
- Có giới hạn tổng theo IP/client để chống phân tán, nhưng xử lý thận trọng với NAT/VPN.
- Tách quota cho thao tác đăng nhập, token issuance và refresh để một hoạt động không chặn toàn bộ luồng của người dùng.
- Có cơ chế hỗ trợ khôi phục và audit khi policy tự động chặn nhầm.

Không dùng một thông báo khác nhau cho “tài khoản không tồn tại” và “tài khoản bị giới hạn” trong các luồng mà attacker có thể dò danh tính. Với client đã xác thực, có thể trả quota contract riêng nhưng vẫn tránh tiết lộ dữ liệu của user khác.

## 10. Cấu hình policy mẫu

Ví dụ dưới đây minh họa cấu trúc cấu hình; các ngưỡng cần được hiệu chỉnh theo tải, loại client và yêu cầu dịch vụ:

~~~yaml
tokenEndpoint:
  enabled: true
  global:
    capacity: 1200
    refillPerSecond: 20
  coarseBySource:
    capacity: 60
    refillPerSecond: 1
    key: trusted-ip-prefix
  perClient:
    capacity: 300
    refillPerSecond: 5
  grants:
    authorization_code:
      capacity: 30
      refillPerSecond: 0.5
    refresh_token:
      capacity: 20
      refillPerSecond: 0.2
      keyBy: client-subject-family
    client_credentials:
      capacity: 600
      refillPerSecond: 10
      keyBy: authenticated-client
    device_code:
      enforcePollInterval: true
  response:
    status: 429
    includeRetryAfter: true
    cacheControl: no-store
  degradedMode:
    strategy: bounded-fail-open
    emergencyCapacity: 10
~~~

Các con số chỉ là giá trị minh họa, không phải baseline production. Cần load test, capacity planning, đánh giá mức tiêu thụ HSM/KMS/database và phân loại client trước khi áp dụng. Policy nên được quản lý bằng cấu hình có version, audit thay đổi và khả năng rollback.

## 11. Observability cho rate limit

Đội vận hành cần biết limiter đang chặn ai, ở route nào, do bucket nào và có ảnh hưởng đến người dùng hợp lệ hay không. Nên theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| `token_endpoint_requests_total` | Tổng request theo grant và kết quả |
| `token_endpoint_rate_limited_total` | Số request bị từ chối do quota |
| `token_rate_limit_decision_seconds` | Độ trễ của bước kiểm tra quota |
| `token_rate_limiter_errors_total` | Lỗi Redis/quota service hoặc script |
| `token_endpoint_issuance_total` | Số token phát hành thành công |
| `refresh_token_reuse_total` | Số lần phát hiện reuse sau rotation |
| `token_endpoint_client_auth_failures_total` | Lỗi xác thực client |
| `token_endpoint_degraded_mode` | Trạng thái limiter fail-open/fail-closed |

Label nên có cardinality thấp: `grant_type`, `result`, `reason`, `service`, `client_class` hoặc `region` đã chuẩn hóa. Không đưa raw client secret, access token, refresh token, email, subject ID, IP hoặc refresh family ID vào metric labels. Dùng security event có kiểm soát để điều tra từng trường hợp.

Dashboard nên thể hiện:

- Request rate và tỷ lệ 429 theo grant/client class.
- Tỷ lệ token issuance thành công và lỗi client authentication.
- Số refresh token reuse và token family bị revoke.
- Limiter latency, dependency error, Redis saturation và degraded mode.
- Tác động lên client hợp lệ, retry storm và request bị chặn theo source.

Alert gợi ý:

- Tỷ lệ 429 tăng nhanh so với baseline hoặc tập trung ở một grant.
- Redis/quota service timeout hoặc latency vượt SLO.
- Một client có request burst bất thường hoặc client authentication failure tăng đột biến.
- Refresh token reuse tăng, đặc biệt khi đi cùng client/source mới.
- Limiter chuyển sang degraded mode hoặc global bucket gần cạn.

Không cảnh báo chỉ dựa vào tổng số 429; một đợt tải hợp lệ hoặc một client retry lỗi cũng có thể tạo spike. Cần phân nhóm theo grant, client class và reason.

## 12. Kiểm thử và diễn tập vận hành

Trước khi bật policy production, kiểm thử cả logic quota và ảnh hưởng lên hệ thống phân tán:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Request dưới quota | Token Endpoint xử lý bình thường |
| Request vượt quota trong một bucket | Trả 429 và `Retry-After` phù hợp |
| Client chờ đủ thời gian rồi retry | Request được phép nếu bucket đã phục hồi |
| Hai instance nhận request đồng thời | Tổng quota được thực thi nhất quán, không nhân đôi theo số instance |
| Hai bucket cùng áp dụng | Quyết định quota có tính nguyên tử hoặc xử lý bù trừ đúng |
| IP chung của nhiều người dùng hợp lệ | Không khóa toàn bộ chỉ vì một user vượt quota |
| Attacker thay đổi IP nhưng giữ cùng authenticated client | Per-client quota vẫn giới hạn được |
| Client giả mạo `client_id` của client khác | Không làm cạn bucket authenticated client đó |
| Redis timeout hoặc failover | Hành vi theo degraded-mode policy và có alert |
| Đồng hồ node lệch | Không tạo quota reset bất thường |
| Refresh token bị gửi đồng thời | Client single-flight; server phát hiện/reject reuse theo rotation policy |
| Device client poll nhanh hơn interval | Trả `slow_down` theo device flow |
| Log nhận Authorization header | Token và secret được redact |
| Response 429 đi qua proxy/CDN | Không bị cache hoặc biến đổi sai `Retry-After` |

### Load test và capacity test

Tăng tải theo từng grant và client class, đo:

- Request/second và concurrency tại Token Endpoint.
- CPU, memory, thread pool, connection pool và garbage collection.
- Latency p50/p95/p99 của authentication, database, HSM/KMS và limiter.
- Redis command latency, key cardinality, hot key và replication/failover.
- Tỷ lệ 429, lỗi xác thực, issuance success và retry amplification.

Thử cả burst ngắn và tải ổn định kéo dài. Mục tiêu là chứng minh quota bảo vệ capacity mà vẫn đáp ứng SLO cho traffic hợp lệ. Kiểm tra hot key khi một client rất lớn dùng chung một bucket; có thể cần shard hoặc quota theo workload/tenant nhưng phải giữ được global ceiling.

## 13. Runbook khi Token Endpoint tăng 429 hoặc bị quá tải

1. **Xác định phạm vi:** xem 429 theo grant, client class, route và region; xác định đây là abuse, client retry storm hay policy đặt quá thấp.
2. **Kiểm tra limiter:** đo latency/error của Redis hoặc quota service, trạng thái replication, hot key và degraded mode.
3. **Bảo vệ hệ thống:** giữ global ceiling; nếu cần, điều chỉnh quota cho client đã xác minh theo change procedure và capacity còn lại.
4. **Giảm retry storm:** thông báo cho owner client qua kênh vận hành đã được phê duyệt; kiểm tra `Retry-After`, exponential backoff và refresh single-flight.
5. **Xử lý dấu hiệu compromise:** nếu có credential stuffing hoặc refresh reuse, kích hoạt playbook security tương ứng, revoke token family theo policy và bảo toàn evidence.
6. **Khôi phục:** theo dõi tỷ lệ 429, issuance success và latency sau điều chỉnh; rollback policy nếu gây ảnh hưởng ngoài dự kiến.
7. **Rà soát:** cập nhật baseline, quota theo client class, alert và capacity plan.

Không tăng quota toàn cục ngay khi thấy 429 tăng. Nếu nguyên nhân là abuse, tăng quota có thể làm sự cố nặng hơn; nếu nguyên nhân là client bug, cần sửa retry behavior và quota riêng cho client đó.

## 14. Checklist trước khi đưa policy vào production

- [ ] Phân loại endpoint và grant; có quota riêng theo rủi ro.
- [ ] Có coarse limit trước các thao tác tốn tài nguyên và identity limit sau xác thực.
- [ ] Không tin `client_id`, subject hoặc tenant chưa được xác minh khi tạo bucket có thẩm quyền.
- [ ] Kết hợp client, subject/family, nguồn mạng và global capacity; tránh chỉ dựa vào IP.
- [ ] Limiter phân tán có thao tác nguyên tử và TTL phù hợp.
- [ ] Có policy fail-open/fail-closed và bounded emergency budget.
- [ ] Refresh token rotation/reuse detection được giữ nguyên; rate limit không thay thế chúng.
- [ ] Device flow tuân thủ polling interval và `slow_down`.
- [ ] HTTP 429 và `Retry-After` được xử lý nhất quán; response không bị cache.
- [ ] Không làm lộ trạng thái tài khoản, quota của user khác hoặc thông tin client nhạy cảm.
- [ ] Client áp dụng backoff/jitter và single-flight cho refresh.
- [ ] Metrics, dashboard và alert có cardinality thấp, không chứa token/PII.
- [ ] Đã test concurrency, multi-instance, Redis failure, NAT, spoofed client ID và retry storm.
- [ ] Có runbook, owner, audit thay đổi policy và quy trình rollback.

## 15. Tình huống tổng hợp

Một mobile client bị lỗi triển khai, gửi cùng refresh request nhiều lần đồng thời. Authorization Server bắt đầu trả 429 cho bucket refresh theo client và token family. Cùng lúc, một nguồn IP lạ thử nhiều refresh token khác nhau trên cùng client ID.

Đội vận hành cần phân biệt hai luồng: request burst từ phiên hợp lệ có thể do race condition ở client; các lần thử refresh token từ nguồn lạ có thể là abuse. Dựa trên client authentication, subject/family fingerprint đã bảo vệ, source network, kết quả grant và lịch sử rotation, hệ thống có thể giới hạn riêng từng dimension. Client cần được sửa để single-flight refresh và lưu token mới nguyên tử; nguồn lạ bị chặn theo coarse limit và các refresh token reuse được xử lý theo security policy.

**Điều cần nhớ:** rate limit tốt bảo vệ Token Endpoint mà vẫn giữ được luồng cấp token hợp lệ. Chính sách phải dựa trên identity đã xác minh, nhiều dimension, thuật toán phân tán có tính nguyên tử, phản hồi retry rõ ràng và telemetry đủ để phân biệt lỗi client với hành vi tấn công.

## 16. Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): Token Endpoint, token request và error response.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): khuyến nghị bảo mật OAuth 2.0 hiện đại, gồm bảo vệ refresh token.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585.html): định nghĩa HTTP 429 Too Many Requests.
- [RFC 9331 — The RateLimit Fields for HTTP](https://www.rfc-editor.org/rfc/rfc9331.html): các HTTP fields công bố quota và trạng thái rate limit.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628.html): polling interval và phản hồi `slow_down` trong device flow.
