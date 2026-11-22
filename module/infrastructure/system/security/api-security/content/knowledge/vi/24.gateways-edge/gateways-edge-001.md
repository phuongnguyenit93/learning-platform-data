# API gateway authenticate và rate limit

## 1. Gateway đứng ở đâu trong bảo mật API?

API gateway là điểm tiếp nhận và điều phối request từ client đến các backend service. Ở edge, gateway có thể kết thúc TLS, định tuyến, xác thực credential, áp dụng rate limit, giới hạn kích thước request và ghi nhận telemetry. Một gateway được cấu hình đúng giúp áp dụng các chính sách chung nhất quán trước khi request đi sâu vào hệ thống.

Tuy nhiên, gateway không tự hiểu đầy đủ ngữ cảnh nghiệp vụ. Gateway có thể xác minh caller là user hoặc client nào, nhưng service thường mới biết user có phải chủ sở hữu invoice hay không, partner được cập nhật shipment nào, hoặc giao dịch có đang ở trạng thái được phép hoàn tiền không. Vì vậy cần phân biệt:

- **Authentication tại edge:** xác minh credential và thiết lập danh tính caller.
- **Authorization tại gateway:** giới hạn route hoặc chức năng tổng quát theo scope/role nếu policy phù hợp.
- **Authorization tại service:** kiểm tra quyền chức năng, đối tượng, thuộc tính, tenant và điều kiện nghiệp vụ trên dữ liệu thực tế.
- **Rate limiting tại edge và trong service:** kiểm soát tốc độ request và chi phí thực thi ở nhiều tầng.

Không xem việc request đi qua gateway là bằng chứng nó đã được xác thực hoặc được cấp quyền. Mọi đường truy cập backend phải được giới hạn để không thể bỏ qua edge policy, và service vẫn cần xác minh identity/delegation theo trust model của hệ thống.

## 2. Các nhiệm vụ bảo mật chính của gateway

| Nhiệm vụ | Gateway thường thực hiện | Service vẫn cần làm |
|---|---|---|
| TLS và kết nối | Kết thúc HTTPS, chọn TLS policy, có thể dùng mTLS tới upstream. | Bảo vệ kết nối nội bộ và kiểm tra danh tính proxy/workload theo kiến trúc. |
| Authentication | Xác minh JWT, introspect opaque token, API key hoặc client certificate. | Xác minh token/delegation nếu service không chỉ tin gateway; áp dụng chính sách theo nghiệp vụ. |
| Route policy | Chặn route hoặc nhóm chức năng theo scope/client. | Kiểm tra quyền trên object, field, tenant và trạng thái nghiệp vụ. |
| Rate limit/quota | Giới hạn theo IP, credential, principal, route hoặc tenant. | Giới hạn tác vụ đắt, concurrency, tài nguyên và side effect trong service. |
| Request limits | Giới hạn body, header, timeout, connection và method. | Validate schema, file content, query complexity và business limits. |
| Observability | Ghi request ID, principal đã xác minh, route, status, latency và quota decision. | Ghi audit nghiệp vụ, object ID và quyết định authorization phù hợp. |

Gateway nên có policy theo route và method, không chỉ theo hostname. Ví dụ `GET /api/orders/**` và `POST /api/orders/**` có thể có yêu cầu scope, quota và tác động nghiệp vụ khác nhau.

## 3. Authentication tại gateway

Authentication xác định credential đại diện cho ai hoặc cho workload nào. Gateway cần biết loại credential được chấp nhận, issuer/CA tin cậy, audience, thời hạn, cách thu hồi và cách chuyển danh tính đã xác minh đến backend.

### JWT access token

Với JWT, gateway phải xác minh chữ ký và claim theo policy. Chỉ decode payload không phải xác thực token.

Các kiểm tra thường cần có:

1. Chỉ chấp nhận thuật toán ký nằm trong allowlist cấu hình; không tin `alg` do token tự chọn để quyết định cách xác minh.
2. Chọn signing key từ JWKS/issuer đã cấu hình và xử lý `kid` đúng cách; không tải key từ URL tùy ý nằm trong token.
3. Xác minh chữ ký bằng key phù hợp.
4. Kiểm tra `iss` đúng issuer tin cậy và `aud` bao gồm API/gateway resource hiện tại.
5. Kiểm tra `exp`, `nbf` và thời gian phát hành theo clock skew được kiểm soát.
6. Kiểm tra token type/use case, scope/permission và các claim cần thiết; không dùng ID token thay access token để gọi API.
7. Có chính sách xử lý key rotation, issuer outage, token bị thu hồi và cache JWKS.

Không mặc định claim `role`, `scope` hay `tenant_id` có ý nghĩa giống nhau giữa mọi issuer. Chỉ tin claim do issuer có thẩm quyền phát hành và có contract rõ. Token còn chữ ký hợp lệ có thể vẫn chứa quyền cũ cho đến khi hết hạn; với hành động nhạy cảm, service có thể cần kiểm tra trạng thái quyền hiện tại hoặc cơ chế revoke phù hợp.

### Opaque token và introspection

Opaque token không tự chứa claim có thể xác minh cục bộ. Gateway gọi authorization server/introspection endpoint để biết token còn active và các thuộc tính liên quan. Điều này hỗ trợ revoke tập trung nhưng tạo phụ thuộc về latency và availability.

- Chỉ gọi introspection endpoint đã cấu hình, qua TLS và với client credential riêng.
- Cache kết quả trong thời gian ngắn phù hợp với rủi ro; cache quá lâu làm chậm hiệu lực thu hồi.
- Không cache kết quả `active=true` vượt quá expiry của token.
- Định nghĩa rõ hành vi khi authorization server không sẵn sàng: fail closed cho route nhạy cảm; mọi ngoại lệ phải được đánh giá rủi ro.
- Giới hạn timeout, concurrency và retry tới introspection endpoint để tránh tạo vòng lặp quá tải.

### API key

API key thường nhận diện một ứng dụng/client hoặc integration, không nhất thiết xác định user cuối. Gateway có thể kiểm tra key ID, trạng thái, scope, quota và ngày hết hạn.

- Cấp key riêng theo client/partner và môi trường; không dùng chung một key cho mọi consumer.
- Lưu hash của key nếu hệ thống chỉ cần so sánh key gửi lên; chỉ hiển thị secret đầy đủ lúc tạo.
- Có prefix/key ID không nhạy cảm để tra cứu và hỗ trợ rotation/revoke.
- Gắn key với scope, tenant/partner, quota và trạng thái; không coi biết key là quyền truy cập mọi object.
- Không nhận key trong query string nếu có thể dùng header vì URL thường xuất hiện trong access log, proxy log và browser history.

### mTLS client certificate

mTLS xác minh client certificate ở tầng TLS và chứng minh caller nắm private key tương ứng. Gateway kiểm tra chain, trust anchor, validity, EKU, SAN và chính sách issuer. Certificate có thể đại diện partner hoặc workload.

Sau handshake, gateway cần ánh xạ certificate sang principal rõ ràng. Không dùng CN tùy ý làm role quản trị. Nếu gateway kết thúc mTLS rồi chuyển request tới backend, backend thường chỉ nhìn thấy gateway ở tầng TLS; danh tính caller ban đầu phải được truyền qua cơ chế được bảo vệ và chỉ tin từ gateway xác thực.

### Kết hợp nhiều cơ chế

Một route có thể yêu cầu mTLS cho kết nối đối tác và OAuth access token để xác định client/scope. Hai cơ chế cần có mục đích riêng: certificate xác thực workload/kênh kết nối, token biểu diễn quyền gọi API. Không cộng dồn credential một cách hình thức nếu hệ thống không kiểm tra quan hệ giữa chúng.

## 4. Chuyển danh tính đã xác minh đến backend

Khi gateway xác thực caller, backend cần biết danh tính hoặc delegation context để thực thi authorization. Có hai cách phổ biến:

- **Forward token:** gateway chuyển tiếp access token đã xác minh; backend tự xác minh issuer, audience, signature, expiry và scope. Token cần có audience phù hợp với backend, không chỉ gateway.
- **Trusted identity assertion:** gateway tạo header/token nội bộ có chữ ký hoặc được bảo vệ qua mTLS, chứa principal và thuộc tính cần thiết. Backend chỉ tin assertion từ gateway được cấu hình rõ.

Nếu dùng header như `X-Authenticated-User`, `X-Client-ID`, `X-Partner-ID` hoặc `X-Tenant-ID`:

- Gateway phải xóa mọi giá trị cùng tên do client gửi trước khi tạo giá trị mới.
- Backend chỉ chấp nhận header từ gateway/proxy tin cậy; chặn truy cập trực tiếp vào backend bằng network policy và xác thực proxy.
- Kênh gateway-to-service cần được bảo vệ, tốt nhất bằng mTLS hoặc cơ chế workload identity tương đương.
- Header cần có schema rõ, không dùng giá trị tùy ý làm role hoặc permission.
- Nếu request đi qua nhiều proxy, xác định rõ hop nào được phép thêm/sửa header.

Không tin `X-Forwarded-For` hoặc header identity do client tự đặt. Chỉ lấy client IP từ proxy chain đã cấu hình tin cậy; nếu không, attacker có thể giả IP để né rate limit hoặc làm sai audit log.

## 5. Authentication không thay thế authorization

Sau khi gateway xác minh token, request vẫn có thể không được phép. Ví dụ token có scope `orders:read` nhưng user chỉ được đọc đơn hàng của mình; partner có scope `shipment:update` nhưng chỉ được cập nhật shipment được giao; service có identity hợp lệ nhưng không có quyền hoàn tiền.

Gateway có thể thực hiện kiểm tra coarse-grained theo route/scope:

```text
GET  /api/orders/**       requires orders:read
POST /api/orders          requires orders:create
POST /api/refunds/**      requires refunds:create
DELETE /api/admin/users/** requires users:disable
```

Service phải tiếp tục kiểm tra:

- Caller có quyền chức năng cho hành động cụ thể không?
- Object có thuộc user, partner hoặc tenant được phép không?
- Field nào được đọc/ghi? Client có đang gửi field server-owned như `role`, `ownerId`, `balance` hoặc `status` không?
- Trạng thái nghiệp vụ, hạn mức, approval và separation of duties có cho phép hành động không?

Mặc định từ chối khi thiếu policy hoặc không xác định được principal. Không dùng `permitAll` cho route nhạy cảm chỉ vì gateway đã có một filter authentication chung; cần chắc chắn filter đó thực sự chạy cho route/method đang xét.

## 6. Rate limit và quota khác nhau thế nào?

**Rate limit** giới hạn tốc độ request trong một khoảng thời gian hoặc mức burst. Nó bảo vệ availability và giảm khả năng một caller chiếm tài nguyên.

**Quota** giới hạn tổng mức sử dụng trong một chu kỳ hoặc ngân sách nghiệp vụ, ví dụ 100.000 request/ngày, 10.000 email/tháng hoặc 50 GB dữ liệu. Một caller có thể nằm dưới rate limit từng giây nhưng vẫn vượt quota tháng.

**Concurrency limit** giới hạn số tác vụ đang chạy đồng thời. Nó quan trọng với endpoint chờ lâu, query đắt, export, upload hoặc gọi dịch vụ ngoài.

Ba cơ chế thường cần phối hợp. Ví dụ API export có thể cho phép 2 job đồng thời mỗi tenant, tối đa 10 job mỗi giờ và quota 100 GB dữ liệu mỗi tháng.

## 7. Các thuật toán rate limiting phổ biến

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Fixed window counter | Đếm request trong cửa sổ cố định, ví dụ mỗi phút. | Dễ triển khai, ít trạng thái. | Có thể burst gấp đôi quanh ranh giới hai cửa sổ. |
| Sliding window log | Lưu thời điểm từng request trong khoảng trượt. | Chính xác theo cửa sổ. | Tốn bộ nhớ và thao tác khi traffic lớn. |
| Sliding window counter | Kết hợp counter cửa sổ trước và hiện tại theo trọng số. | Cân bằng chi phí và độ chính xác. | Là phép xấp xỉ, không chính xác tuyệt đối. |
| Token bucket | Token được nạp đều đến mức tối đa; request tiêu thụ token. | Cho phép burst có giới hạn và tốc độ trung bình ổn định. | Cần đồng bộ trạng thái khi có nhiều gateway instance. |
| Leaky bucket | Request được xử lý/đưa ra theo tốc độ đều; hàng đợi có giới hạn. | Làm phẳng burst. | Có thể tăng latency; cần giới hạn queue để tránh tích tụ. |

### Token bucket

Giả sử bucket có dung lượng (B) token và tốc độ nạp (r) token/giây. Khi có request, gateway tiêu thụ (c) token (thường (c=1), nhưng request đắt có thể có cost cao hơn). Nếu không đủ token, request bị trì hoãn hoặc từ chối.

```text
tokens = min(B, tokens + elapsed_seconds * r)

if tokens >= request_cost:
    tokens = tokens - request_cost
    allow request
else:
    reject with 429
```

Ví dụ bucket chứa tối đa 20 token và nạp 5 token/giây: caller có thể gửi burst tối đa 20 request nếu bucket đang đầy, sau đó duy trì trung bình khoảng 5 request/giây. Đây là ví dụ đơn giản; cấu hình thực tế cần xét cost, burst và concurrency.

## 8. Chọn rate-limit key đúng

Rate limit chỉ có ý nghĩa khi key phản ánh đúng đối tượng cần bảo vệ. Không dùng một key duy nhất cho mọi route và mọi caller.

| Key | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| IP/client network | Chống flood trước authentication hoặc cho endpoint anonymous. | NAT/proxy khiến nhiều user dùng chung IP; IP spoofing/header giả có thể né policy. |
| API key/client ID | Public developer API hoặc partner integration. | Key bị chia sẻ/đánh cắp; cần revoke và quota riêng. |
| User/principal ID | User-facing API đã xác thực. | Một user có thể dùng nhiều token; key nên lấy từ principal đã xác minh. |
| Tenant/partner ID | Giới hạn tài nguyên theo tổ chức. | Tenant phải được suy ra từ identity/policy, không tin header do caller tự chọn. |
| Route + method | Endpoint có chi phí hoặc rủi ro khác nhau. | Tránh một quota chung khiến endpoint rẻ bị ảnh hưởng bởi endpoint đắt. |
| Credential + route | Giới hạn từng client theo từng nhóm chức năng. | Cần quản lý cardinality và thời hạn trạng thái. |
| Global/service budget | Bảo vệ downstream hoặc ngân sách toàn hệ thống. | Cần phân bổ công bằng và tránh một tenant chiếm hết budget. |

Thực tế thường kết hợp nhiều lớp: giới hạn theo IP trước auth, sau đó theo principal/client/tenant, tiếp theo theo route và cuối cùng là global concurrency/budget. Dùng identity đã xác minh cho quota theo user/tenant. Nếu request không có identity, áp dụng pre-auth limit theo IP/network signal và các tín hiệu edge khác.

Không để client tự gửi `X-RateLimit-Key`, `X-Tenant-ID` hoặc `X-Client-ID` làm key. Nếu gateway dùng forwarded IP, chỉ tin proxy chain được khai báo rõ và loại bỏ header do Internet client tự cung cấp.

## 9. Phân tầng giới hạn để bảo vệ cả gateway và backend

Rate limiting chỉ sau authentication có thể không bảo vệ được chính bước xác thực nếu attacker gửi lượng lớn token rác hoặc làm quá tải introspection/JWKS. Ngược lại, chỉ rate limit theo IP sẽ không đủ để kiểm soát một user hợp lệ lạm dụng API.

Một thiết kế nhiều tầng có thể gồm:

1. **Edge/pre-auth:** connection limit, request size, header size, handshake rate và IP/network rate limit cho endpoint công khai.
2. **Authentication service:** timeout/concurrency/rate limit riêng cho JWKS, introspection hoặc credential lookup; cache key an toàn.
3. **Authenticated caller:** limit theo client/user/partner/tenant đã xác minh.
4. **Route/method:** limit khác nhau cho login, search, export, upload, report và payment.
5. **Backend operation:** concurrency, query cost, downstream budget và business quota.
6. **Global protection:** circuit breaker, queue limit, connection pool và giới hạn tài nguyên toàn service.

Ví dụ, `/login` cần chống credential stuffing theo IP và account; `/search` cần giới hạn query complexity/page size; `/export` cần concurrency và quota theo tenant; `/payments` cần idempotency và business control để retry không tạo giao dịch lặp.

## 10. Rate limiting trong môi trường nhiều gateway instance

Nếu mỗi gateway instance giữ counter riêng trong bộ nhớ, tổng mức cho phép có thể nhân lên theo số instance. Với 5 instance, limit 100 request/phút trên mỗi instance có thể cho phép gần 500 request/phút cho cùng một caller.

Các lựa chọn:

- **Local limiter:** rất nhanh, không phụ thuộc kho trạng thái chung; phù hợp bảo vệ từng instance hoặc pre-auth defense, nhưng tổng limit không chính xác khi scale ngang.
- **Distributed store:** Redis hoặc datastore dùng thao tác atomic/Lua/script để cập nhật counter/bucket chung; cần xử lý latency, failover, eviction và hot key.
- **Gateway control plane:** nền tảng gateway cung cấp distributed rate limiting; cần hiểu consistency, replication delay và hành vi khi node mất kết nối.
- **Hierarchical limits:** kết hợp local burst protection với global/tenant quota phân tán.

Định nghĩa rõ consistency cần thiết. Một giới hạn chống DoS có thể chấp nhận sai số nhỏ; quota tính phí hoặc giới hạn giao dịch cần mức chính xác và audit cao hơn. Tránh dùng read-then-write không nguyên tử vì nhiều request đồng thời có thể cùng vượt hạn mức.

### Khi kho rate-limit không sẵn sàng

Không có một lựa chọn fail-open/fail-closed đúng cho mọi route:

- Route đọc dữ liệu công khai có thể dùng local emergency limit để duy trì availability.
- Route tốn tài nguyên hoặc có tác dụng phụ tài chính thường cần fail closed hoặc hạn mức dự phòng rất chặt.
- Endpoint login/introspection cần policy riêng để lỗi datastore không tạo điều kiện cho brute force hoặc làm toàn bộ xác thực ngừng hoạt động.

Quyết định phải được ghi trong policy theo mức rủi ro, có metric và alert. Không để lỗi Redis âm thầm bỏ qua mọi rate limit.

## 11. Response khi vượt giới hạn

Khi caller vượt rate limit, gateway thường trả `429 Too Many Requests`. Có thể kèm `Retry-After` để hướng dẫn thời điểm thử lại. Các header `RateLimit-*` hoặc `X-RateLimit-*` tùy contract của nền tảng; hãy chọn một chuẩn nhất quán và tránh tiết lộ thông tin nội bộ nhạy cảm.

Ví dụ response:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 12

{
  "type": "https://api.example.com/problems/rate-limit-exceeded",
  "title": "Too many requests",
  "status": 429,
  "detail": "Request limit exceeded. Retry after the indicated interval."
}
```

Client nên tôn trọng `Retry-After`, dùng exponential backoff và jitter, giới hạn số lần retry và giữ cùng idempotency key cho cùng logical operation nếu endpoint hỗ trợ. Không retry liên tục ngay khi nhận `429`; hành vi đó làm hệ thống quá tải hơn.

Phân biệt các lỗi:

- `401 Unauthorized`: thiếu hoặc credential không hợp lệ; client cần xác thực lại theo contract.
- `403 Forbidden`: danh tính đã được xác minh nhưng không có quyền.
- `429 Too Many Requests`: vượt rate limit/quota áp dụng.
- `503 Service Unavailable`: gateway/backend không sẵn sàng; có thể có `Retry-After` theo policy.

Không dùng `403` thay `429` cho mọi trường hợp vì client và hệ thống quan sát sẽ khó phân biệt lỗi quyền với lỗi hạn mức. Có thể dùng `404` thay `403` trong một số chính sách che giấu tài nguyên, nhưng đó là quyết định authorization riêng.

## 12. Ví dụ cấu hình policy ở gateway

Ví dụ YAML dưới đây mô tả policy trung lập theo ý tưởng, không phải schema cấu hình của một vendor cụ thể:

```yaml
routes:
  - id: public-search
    match:
      method: GET
      path: /api/search
    authentication:
      mode: oauth-jwt
      issuer: https://identity.example.com/
      audience: catalog-api
      required_scopes: [catalog:read]
    rate_limits:
      - key: client_id
        requests: 60
        window: 60s
      - key: global
        requests: 2000
        window: 1s

  - id: partner-shipment-update
    match:
      method: PATCH
      path: /partner/shipments/{id}
    authentication:
      mode: mtls-and-oauth
      audience: logistics-api
      required_scopes: [shipment:status:update]
    rate_limits:
      - key: verified_partner_id
        requests: 300
        window: 60s
      - key: route_concurrency
        maximum: 40

  - id: internal-report-export
    match:
      method: POST
      path: /internal/reports/export
    authentication:
      mode: workload-jwt
      audience: reporting-api
      required_scopes: [report:export]
    rate_limits:
      - key: verified_service_identity
        requests: 5
        window: 60s
      - key: tenant_concurrency
        maximum: 2
```

Trong cấu hình thực tế cần bổ sung chính sách khi token thiếu/sai, JWKS refresh, introspection, client identity mapping, route priority, burst, cost, distributed store và failure mode. `verified_partner_id`/`verified_service_identity` phải được tạo từ credential đã xác minh, không lấy từ header tự do. Gateway vẫn không thể kết luận partner được sửa shipment ID cụ thể nếu không có dữ liệu quan hệ; service phải kiểm tra object-level authorization.

### Ví dụ Spring Cloud Gateway và Redis RateLimiter

Với Spring Cloud Gateway, có thể dùng `RequestRateLimiter` kết hợp Redis để chia sẻ trạng thái giữa các instance. Cấu hình minh họa:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-search
          uri: http://catalog-service:8080
          predicates:
            - Path=/api/search
            - Method=GET
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@principalKeyResolver}"
                redis-rate-limiter.replenishRate: 10
                redis-rate-limiter.burstCapacity: 20
                redis-rate-limiter.requestedTokens: 1
```

`principalKeyResolver` cần trả key dựa trên principal đã xác thực, chẳng hạn client/user ID trong security context. Với request anonymous hoặc trước authentication, dùng limiter riêng theo IP/network signal đã được xác minh. Cấu hình Redis connection, authentication, TLS, timeout và failure behavior theo môi trường; không expose Redis ra Internet.

Đây là ví dụ theo Spring Cloud Gateway phiên bản có Redis RateLimiter; tên property và cách cấu hình có thể khác giữa các phiên bản. Cần kiểm tra tài liệu của phiên bản dự án và bảo đảm authentication filter chạy trước resolver dùng principal. Nếu key resolver trả `null` hoặc giá trị chung cho mọi caller, policy có thể không hoạt động như mong muốn.

## 13. Các lỗi cấu hình gateway thường gặp

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Decode JWT nhưng không verify signature | Attacker tự tạo claim role/scope. | Xác minh chữ ký, issuer, audience, expiry và token type. |
| Chỉ xác thực ở gateway rồi backend mở public | Attacker bypass gateway và gọi thẳng service. | Private networking, mTLS/workload identity và kiểm soát ingress backend. |
| Tin identity header từ client | Giả mạo user, partner hoặc tenant. | Strip header đầu vào và tạo assertion chỉ sau xác minh. |
| Rate limit chỉ theo IP | NAT gây ảnh hưởng user khác; attacker phân tán IP hoặc spoof forwarded header. | Kết hợp principal/client/tenant và trusted proxy chain. |
| Rate limit trước auth duy nhất | Không phân biệt client hợp lệ và không hợp lệ; credential abuse vẫn khó kiểm soát. | Pre-auth limit cộng authenticated identity limits. |
| Counter local trên nhiều instance | Tổng mức cho phép tăng theo số node. | Distributed store hoặc hierarchical limit có tính toán. |
| Một limit cho mọi route | Endpoint rẻ và đắt có cùng quota; route nhạy cảm không được bảo vệ đủ. | Policy theo route/method/cost. |
| Gateway trả 429 nhưng backend đã chạy tác vụ | Limit được áp dụng quá muộn hoặc side effect xảy ra trước decision. | Đặt filter trước upstream; service cũng enforce business/concurrency limit. |
| Fail-open khi Redis lỗi mà không giám sát | Rate limit bị vô hiệu hóa âm thầm. | Failure mode theo route, fallback chặt và alert. |
| Tin scope thay cho object authorization | User có scope rộng có thể truy cập object của người khác. | Service kiểm tra ownership, tenant và property. |
| Cache JWKS/introspection vô hạn | Key revoke/rotation hoặc token revoke không có hiệu lực kịp. | TTL có giới hạn, refresh và xử lý stale cache rõ. |
| Retry mọi lỗi xác thực/introspection | Tạo request storm đến identity provider. | Timeout, backoff, retry có giới hạn và circuit breaker. |

## 14. Kiểm thử authentication và rate limit

Kiểm thử phải bao gồm cả trường hợp cho phép và từ chối, cũng như hành vi khi gateway có nhiều instance hoặc dependency bị lỗi.

| Nhóm test | Thao tác | Kết quả mong đợi |
|---|---|---|
| JWT signature | Gửi token sai chữ ký, thuật toán không được phép hoặc `kid` không hợp lệ. | Bị từ chối; không chuyển request tới backend. |
| Issuer/audience | Token đúng chữ ký nhưng sai issuer hoặc audience. | Bị từ chối. |
| Expiry/type/scope | Token hết hạn, sai loại hoặc thiếu scope. | Trả lỗi auth phù hợp; không tạo side effect. |
| Key rotation | Provider xoay JWKS key và phát token bằng key mới. | Gateway refresh/cache hoạt động; key cũ được xử lý theo policy. |
| Opaque token revoke | Thu hồi token rồi gọi lại sau thời hạn cache dự kiến. | Token bị từ chối trong SLA thu hồi. |
| API key | Dùng key sai, hết hạn, revoked hoặc sai môi trường. | Bị từ chối và có audit event phù hợp. |
| mTLS | Certificate không tin cậy, hết hạn, sai SAN/EKU hoặc bị revoke. | Handshake/request bị từ chối theo policy. |
| Header spoofing | Gửi giả `X-Authenticated-User`, `X-Forwarded-For`, `X-Tenant-ID`. | Gateway strip/overwrite; backend chỉ nhận identity từ nguồn tin cậy. |
| Backend bypass | Thử gọi service trực tiếp ngoài gateway. | Network/workload policy chặn hoặc service tự xác minh caller. |
| Rate boundary | Gửi dưới, đúng và vượt limit; thử burst quanh ranh giới window. | Hành vi khớp thuật toán, burst và quota được công bố. |
| Identity fairness | Nhiều user sau cùng NAT; một user có nhiều token; nhiều tenant. | Limit theo key thiết kế; không gộp nhầm caller hoặc cho vượt quota. |
| Distributed limit | Gửi traffic qua nhiều gateway instance. | Tổng mức giới hạn nằm trong sai số đã chấp nhận. |
| Dependency outage | Làm Redis/introspection/JWKS endpoint không sẵn sàng trong test. | Failure mode đúng policy; có timeout/alert; không fail-open ngoài ý muốn. |
| Retry behavior | Client nhận 429/503 và retry. | Tôn trọng `Retry-After`, backoff/jitter và idempotency. |

Kiểm tra cả request thực sự tới backend, số tác vụ được tạo, query chạy, downstream call và side effect. Một response `401` hoặc `429` không đủ chứng minh backend chưa xử lý request nếu gateway filter chạy sai thứ tự.

## 15. Giám sát và vận hành

Gateway là nguồn telemetry quan trọng nhưng log cần tránh lưu credential. Có thể ghi principal/client ID đã xác minh, route, method, auth decision, policy version, rate-limit key dạng đã bảo vệ, quota decision, status, latency, request ID và upstream. Không log access token, API key, cookie, private key hoặc toàn bộ Authorization header.

Theo dõi các metric:

- Authentication success/failure theo route, issuer, client và loại credential.
- JWT validation failure theo signature, issuer, audience, expiry hoặc key lookup.
- Introspection latency/error, JWKS refresh failure và cache age.
- Request allowed/rejected/throttled theo route, principal/client/tenant và status.
- Rate-limit store latency, Redis error, counter cardinality, hot key và eviction.
- Upstream request rate, concurrency, timeout, 5xx và connection pool saturation.
- Tỷ lệ request bị từ chối ở gateway nhưng vẫn xuất hiện tại backend (nếu có thể đối chiếu bằng request ID).
- Credential revoked nhưng vẫn được sử dụng, route mới chưa có policy và backend ingress ngoài gateway.

Đặt alert cho auth failure tăng đột biến, một client vượt quota liên tục, rate-limit datastore lỗi, JWKS/introspection không sẵn sàng, backend bị truy cập trực tiếp và thay đổi policy ngoài quy trình. Có runbook để revoke credential, disable route, giảm quota, bật emergency limit hoặc chuyển traffic theo mức ảnh hưởng.

Thay đổi gateway policy cần review như thay đổi code: quản lý version, peer review, test trên staging, rollout canary, metric so sánh trước/sau và rollback có kiểm soát. Một rule quá rộng hoặc thứ tự route/filter sai có thể ảnh hưởng toàn bộ API.

## 16. Checklist triển khai gateway authentication và rate limit

- [ ] Mỗi route/method có audience, authentication mode và policy rõ ràng?
- [ ] JWT được verify chữ ký, issuer, audience, expiry, token type và scope?
- [ ] JWKS/introspection có timeout, cache TTL, rotation và failure policy?
- [ ] API key/certificate được gắn với client/partner/workload riêng và có revoke?
- [ ] Gateway strip header identity do client gửi và chỉ tạo assertion sau xác minh?
- [ ] Backend không thể bị truy cập trực tiếp ngoài trust boundary dự kiến?
- [ ] Service vẫn kiểm tra function, object, property, tenant và business state?
- [ ] Có pre-auth limit và authenticated limit theo IP/principal/client/tenant?
- [ ] Route đắt có quota, concurrency và cost limit riêng?
- [ ] Thuật toán, burst, window, distributed consistency và failure mode được định nghĩa?
- [ ] 429/Retry-After và client backoff/idempotency có contract rõ?
- [ ] Có test JWT, API key, mTLS, header spoofing, backend bypass và nhiều gateway instance?
- [ ] Log/metric không làm lộ credential nhưng đủ điều tra auth/rate-limit decision?
- [ ] Gateway policy được version, review, rollout canary và có rollback plan?

API gateway là lớp kiểm soát edge quan trọng: xác minh caller, áp dụng policy route, giới hạn request và bảo vệ backend trước traffic bất thường. Hiệu quả của nó phụ thuộc vào cách xác minh credential, truyền danh tính qua trust boundary, chọn rate-limit key và đồng bộ trạng thái giữa các instance. Service vẫn phải thực thi authorization theo object/tenant và giới hạn nghiệp vụ; gateway không thể thay thế các quyết định cần hiểu dữ liệu và trạng thái bên trong ứng dụng.
