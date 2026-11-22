# Chọn phạm vi hạn mức theo người dùng, tenant, IP hoặc thao tác

## 1. Một con số requests/phút không giải quyết được mọi vấn đề

Giả sử REST API của nền tảng bán hàng giới hạn **100 request/phút**. Câu hỏi đầu tiên không phải chọn Redis hay thuật toán, mà là: **100 request của ai, tính cho những thao tác nào, trong khoảng thời gian nào?**

- Nếu đếm **theo IP**, hàng trăm người dùng chung mạng văn phòng/NAT có thể bị chặn lẫn nhau.
- Nếu đếm **theo tài khoản**, một khách hàng có thể tạo nhiều tài khoản để vượt hạn mức hạ tầng.
- Nếu đếm **theo tenant**, một tác vụ đồng bộ dữ liệu của tenant lớn có thể chiếm hết ngân sách của những người dùng khác trong chính tenant ấy.
- Nếu đếm **theo thao tác**, `POST /v1/reports` tốn vài giây CPU/DB không nên được đối xử hoàn toàn như `GET /v1/health`.

~~~http
GET /v1/orders?status=PAID&limit=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted-access-token>
Accept: application/json

HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 12
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "detail": "Đã vượt hạn mức của thao tác này; hãy thử lại sau."
}
~~~

`429 Too Many Requests` biểu thị request bị từ chối vì **hạn mức**, không phải vì JSON sai hoặc xác thực thất bại. `Retry-After` cho biết khoảng chờ do server gợi ý; client vẫn cần deadline, retry budget và idempotency. Không gửi token, thông tin quota của tenant khác hay khóa lưu trữ nội bộ trong error body.

Bài thuộc chương **Giới hạn và chống lỗi** của module **INTEGRATION_API_REST**: thiết kế REST theo resource/URI/method/status, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử Java/Spring. Trọng tâm là **chọn đúng đối tượng chịu hạn mức (scope) và khóa đếm (key)**; token bucket, Redis và HTTP response chỉ là phương tiện thực thi chính sách ấy.

## 2. Tách năm khái niệm trước khi thiết kế

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Scope** | Những request nào chia sẻ một ngân sách? | user, tenant, API client, IP, operation |
| **Identity/key** | Request thuộc “chủ ngân sách” nào? | `(tenantId, subjectId)` từ principal đã xác thực |
| **Policy** | Cho phép bao nhiêu, với tốc độ và burst ra sao? | 60 tokens/phút, burst tối đa 20 |
| **Cost** | Mỗi request tiêu mấy tokens? | GET rẻ = 1; tạo export = 10 |
| **Enforcement point** | Kiểm ở gateway, service hay cả hai? | IP ở ingress; user+tenant ở API |

**Scope không đồng nghĩa authorization.** User được phép xem order vẫn có thể hết quota; user có quota vẫn không được xem order của tenant khác. Rate limiting không thay authentication, resource ownership hay BOLA protection.

Một request có thể bị ràng buộc **đồng thời bởi nhiều policy**. Ví dụ một lần `POST /v1/reports` có thể chịu ngân sách toàn hệ thống, tenant, user và thao tác export. Việc không vượt hạn mức của *một* key không đảm bảo tất cả giới hạn còn lại đều cho phép.

### 2.1. Ba mục tiêu dễ bị trộn lẫn

1. **Fairness:** tránh một user/tenant chiếm hết tài nguyên của người khác.
2. **Abuse prevention:** hạn chế brute-force, enumeration, spam, scraping, tạo account hàng loạt.
3. **Resilience/cost control:** bảo vệ CPU, DB, queue, downstream API và chi phí thao tác.

Fairness có thể cần quota mềm và gói dịch vụ; brute-force cần identity kết hợp IP/device và phát hiện hành vi; resilience cần **concurrency limit**, queue backpressure, circuit breaker bên cạnh requests/time. Không kỳ vọng một token bucket theo IP giải quyết cả ba.

## 3. Chọn phạm vi theo user, tenant, IP và thao tác

### 3.1. Theo người dùng đã xác thực

**Phù hợp:** API làm việc tương tác, chống một tài khoản gọi quá nhiều, đảm bảo mỗi người có phần ngân sách. Key điển hình là `(issuer, subject, tenant)` hoặc internal user ID do hệ thống xác minh; **không** dùng `Authorization` nguyên văn, JWT `jti` hoặc access-token string làm khóa vì token có thể refresh và đổi liên tục.

~~~text
scope=USER
key=(trustedTenantId, trustedSubjectId)
policy=100 request / 60 giây; burst=20        # số minh họa
~~~

Tránh dùng email làm key: email có thể đổi, chứa PII và gây lộ trong metrics/Redis dumps. Nếu nhiều client OAuth cùng làm việc dưới một user, cân nhắc thêm `client_id` để chia ngân sách theo app **khi chính sách cần phân biệt**; không nên chia vô tình chỉ vì access token được cấp lại.

**Hạn chế:** attacker tạo nhiều tài khoản có thể phân tán tải. Vì thế user limit thường cần đi cùng tenant/global hoặc controls tại signup/login.

### 3.2. Theo tenant/tổ chức

**Phù hợp:** SaaS đa tenant, gói thuê bao, ngân sách downstream, bảo vệ “noisy neighbor”. Key là **tenant ID được gắn với principal qua policy server-side**, không lấy `X-Tenant-Id` hoặc `?tenantId=...` do client tự khai mà chưa xác minh membership.

~~~text
scope=TENANT
key=trustedTenantId
policy=1.200 request / 60 giây
~~~

Một tenant có 200 nhân viên có thể dùng hết ngân sách chung; kết hợp per-tenant với **per-user** sẽ cân bằng công bằng giữa các tenant và trong cùng tenant. Nếu tenant mua gói cao hơn, policy resolver lấy entitlement từ dữ liệu đáng tin có cache/version và TTL rõ ràng; request header tự khai “plan=premium” không được cấp quota cao hơn.

Khi người dùng có quyền chuyển giữa nhiều tenant, cần xác định **active tenant** theo cơ chế đã xác thực/ủy quyền. Key phải ổn định theo tenant; không vô tình cộng traffic tenant A vào tenant B hoặc để user đổi tenant ID giả để né quota.

### 3.3. Theo địa chỉ IP

**Phù hợp:** request vô danh, bảo vệ login/signup, lớp đầu tiên ở edge để giảm abuse. IP có thể là tín hiệu bổ sung, nhưng **không phải identity người dùng**: NAT, CGNAT, proxy, mạng di động và IPv6 privacy addresses gây chia sẻ/đổi IP.

~~~text
scope=IP
key=canonicalClientIpFromTrustedEdge
policy=30 request / 60 giây cho login anonymous  # số minh họa
~~~

Nếu đi qua reverse proxy/CDN, địa chỉ TCP peer có thể chỉ là proxy. Chỉ đọc `Forwarded`, `X-Forwarded-For` hoặc provider-specific header từ **proxy nằm trong trusted chain**, sau khi ingress đã **xóa/ghi lại header client tự gửi**. Không lấy IP đầu tiên của `X-Forwarded-For` một cách mù quáng; attacker có thể giả mỗi request một IP để né quota hoặc khóa nạn nhân.

Chuẩn hóa IPv4/IPv6, tránh hostname reverse lookup tốn chi phí; chính sách IPv6 prefix (`/64` chẳng hạn) là quyết định vận hành cần cân nhắc vì có thể gộp nhiều thiết bị vô tội. Không lưu IP nguyên vẹn vô hạn trong log/metric label; bảo vệ quyền truy cập và retention theo chính sách dữ liệu cá nhân.

### 3.4. Theo thao tác (operation/route group)

**Phù hợp:** API có chi phí và rủi ro không đồng đều. `POST /v1/exports` sinh tệp lớn, `POST /v1/auth/login` có rủi ro brute-force, `GET /v1/orders/{id}` thường nhẹ hơn. **Định nghĩa operation theo route template và HTTP method**, không theo raw URL có ID thay đổi.

~~~text
operation=orders.read
route=GET /v1/orders/{id}

operation=reports.export.create
route=POST /v1/exports
cost=10 tokens
~~~

Không dùng raw `/v1/orders/o-42` làm một key operation riêng: mỗi ID sẽ có một ngân sách mới và attacker chỉ việc đổi ID. Không gộp mọi `POST` thành một operation vì login, export và checkout cần policy khác. Với GraphQL hay batch endpoint, cost cần dựa vào **hành vi thực** (độ phức tạp query, số items), không chỉ một URI.

### 3.5. Bảng quyết định nhanh

| Tình huống | Scope chính | Scope phụ / lý do |
|---|---|---|
| GET order của user đăng nhập | USER + TENANT | Operation read nếu query đắt |
| Export báo cáo lớn | TENANT + USER + OPERATION | Global concurrency, weighted cost |
| Public search không login | IP + OPERATION | Global cap, bot detection; chấp nhận NAT trade-off |
| Login bằng username/password | IP + ACCOUNT identifier đã chuẩn hóa | Tăng dần chậm, chống enumeration, thêm risk detection |
| OAuth client credentials (machine-to-machine) | CLIENT_ID + TENANT | Không có `sub` của con người; scope/audience theo client |
| Webhook nhận từ đối tác | PARTNER_ID + OPERATION | Xác minh chữ ký trước khi tin identity, IP chỉ hỗ trợ |
| Health/readiness probes | Hạ tầng riêng | Không để user public quota làm chết health check |

**Nguyên tắc:** scope phải phản ánh ai gây tải, ai trả chi phí và ai cần được bảo vệ; thiết kế khác nhau giữa endpoint và threat model, không có “một key chuẩn” cho tất cả.

## 4. Ghép nhiều phạm vi thành chính sách phân tầng

### 4.1. Tại sao chỉ tenant limit hoặc chỉ user limit chưa đủ?

Xét tenant T có hai user: U1 chạy script 1.000 request/phút, U2 đang checkout. Nếu chỉ giới hạn T ở 1.200/phút, U1 có thể ăn gần hết quota; nếu chỉ giới hạn từng user ở 100/phút, 100 user có thể cùng tạo 10.000 request/phút khiến DB quá tải.

Một chính sách phân tầng cho `GET /v1/orders` có thể là:

~~~text
Global API:               20.000 requests/min
Tenant T:                   1.200 requests/min
Mỗi user thuộc tenant T:      100 requests/min
Operation orders.search:       30 requests/min/user
Export create:                  5 requests/10 min/tenant
Export đang chạy:              tối đa 2 jobs/tenant
~~~

Các số **chỉ là ví dụ để giải thích**, không phải benchmark/khuyến nghị chung. Chọn từ SLO, baseline traffic, p95/p99 latency, năng lực DB, số tenant, burst hợp lệ, đặc tính endpoint và yêu cầu chống lạm dụng.

### 4.2. Quy tắc chọn identity và policy

~~~mermaid
flowchart TD
    A["HTTP request đến edge"] --> B["Xác định client IP qua trusted proxy"]
    B --> C["IP/global admission chống abuse thô"]
    C --> D["Authentication & xác minh JWT/API key"]
    D --> E["Principal + tenant membership đáng tin"]
    E --> F["Match HTTP method + route template"]
    F --> G["Lấy policy plan, user, tenant, operation"]
    G --> H{"Tất cả quota còn đủ?"}
    H -->|Không| I["429 + Retry-After + Problem Details"]
    H -->|Có| J["Reserve quota và chạy authorization/domain"]
    J --> K["Response theo REST contract"]
~~~

**Authentication và quota có thể nằm ở các tầng khác nhau:** edge IP policy chạy trước khi nhận diện user để chặn bot; quota theo user/tenant chạy **sau khi identity được xác minh**. Nếu login thất bại thì chưa có principal, chỉ có IP và account string *chưa xác thực* để phục vụ abuse detection; account string cần chuẩn hóa và bảo vệ PII, không dùng nó cấp quyền.

Không dùng `sub` một mình nếu nhiều issuer có thể phát cùng subject ID; nên đưa **issuer/tenant/realm** vào key theo threat model. Với OAuth machine-to-machine, phân biệt `client_id` đã được IdP xác minh với chuỗi client ID tự đưa trong query. Nếu API key cần phân quyền, resolve key ID/version thành account/tenant **sau khi đã kiểm tra secret**, không dùng vài ký tự token làm key người dùng.

### 4.3. Quy tắc nhiều quota: phải rõ semantics “all-or-nothing”

Nếu một request tiêu 1 token của tenant rồi phát hiện user hết quota, request bị từ chối nhưng tenant đã mất quota. Đây là **partial reservation** không mong muốn; có thể tạo thêm denial-of-service giữa user cùng tenant.

Có ba cách triển khai, phải ghi rõ trade-off:

1. **Atomic reserve all:** tính và trừ các bucket trong một transaction/script cùng nơi lưu; thất bại ở bất kỳ policy nào thì **không trừ bucket nào**. Hợp lý nếu tất cả keys cùng shard/được hỗ trợ atomically.
2. **Hai lớp admission độc lập:** edge IP limit và app user/tenant limit kiểm ở hai nơi. Có thể có request bị chặn ở app dù edge đã tiêu quota; cần chấp nhận và đo overhead này như chi phí bảo vệ tầng trước, **không gọi nó là atomic end-to-end**.
3. **Reservation/refund:** nếu không đạt bước sau, hoàn lại token ở bước trước nhưng phải xử lý race, timeout và double-refund; phức tạp hơn và không bảo đảm chính xác trong mọi failure mode.

Với Redis Cluster, script/transaction đa key thường yêu cầu các key nằm ở **cùng hash slot**. Cố gộp mọi tenant vào một hash tag để có atomicity có thể tạo điểm nóng và mất khả năng scale; nếu yêu cầu global fairness nghiêm ngặt, cân nhắc một admission service hoặc thiết kế partition rõ ràng.

## 5. Policy thiết kế bằng token bucket, fixed/sliding window và cost

Thuật toán trả lời **khi nào được tiêu quota**, còn scope trả lời **quota của ai**:

| Thuật toán | Ưu điểm | Lưu ý |
|---|---|---|
| **Fixed window counter** | Đơn giản, rẻ | Có burst sát ranh giới hai cửa sổ |
| **Sliding window log** | Gần đúng số request trong cửa sổ rolling | Lưu nhiều timestamp, tốn memory ở traffic cao |
| **Sliding window counter** | Tương đối mượt, rẻ hơn log | Xấp xỉ và cần định nghĩa độ chính xác |
| **Token bucket** | Hỗ trợ burst có giới hạn và refill liên tục | Phải dùng thời gian/bucket state atomically |
| **Leaky bucket / queue** | Làm phẳng tốc độ xử lý | Có thể tăng latency/hàng đợi; cần capacity và timeout |
| **Concurrency limit** | Bảo vệ công việc đang chạy | Không phải requests/min; cần release lease khi xong/hủy |

### 5.1. Token bucket: công thức đủ dùng

Gọi `B` là capacity tokens, `r` là refill rate (tokens/giây), `t` là thời điểm tính:

\[
T_{\text{new}}=\min(B,\ T_{\text{old}}+r\cdot(t-t_{\text{last}}))
\]

Request chi phí `c` chỉ được chấp nhận nếu `T_new >= c`; sau đó còn `T_new - c` tokens. Nếu thiếu, thời gian chờ lý thuyết tối thiểu là:

\[
\operatorname{wait}\approx \frac{c-T_{\text{new}}}{r}
\]

Ví dụ `B=20`, `r=1 token/giây`: có thể nhận burst 20 request chi phí 1 khi bucket đầy, rồi trung bình 1 request/giây. **Burst capacity không nhất thiết bằng “60 request/phút”**; phải ghi riêng capacity và refill. Dùng đồng hồ monotonic hoặc thời gian thống nhất ở storage để tránh lệch đồng hồ giữa các node.

### 5.2. Weighted cost tránh biến API đắt thành loophole

Ví dụ:

~~~text
GET /v1/orders/{id}           cost = 1
GET /v1/orders?limit=100      cost = 3
POST /v1/exports              cost = 10
POST /v1/exports/{id}/cancel  cost = 1
~~~

Cost là **chính sách cấp tài nguyên**, không phải giá tiền. Cần cap query complexity/`limit`/upload size ngay cả khi có quota; nếu query tự khai cost=1 từ client thì attacker có thể lấy kết quả lớn. Tốt hơn tính cost server-side từ route, request đã validate và ước lượng thực; với việc tạo job, còn phải giới hạn **số job đang chạy**.

Đếm theo request hay theo kết quả là quyết định riêng: đa số request đã được server tiếp nhận **tiêu ngân sách**, kể cả nếu kết thúc bằng 4xx, để tránh abuse; nhưng không nên để attacker tự tạo lỗi `401` vào key của nạn nhân. Response từ cache có thể có policy khác request tới DB, cần chọn theo điểm bảo vệ. Nếu có refund sau lỗi 5xx, phải chống double-refund và tránh khuyến khích retry storms.

## 6. HTTP contract khi chạm hạn mức

### 6.1. 429 và Retry-After

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 8
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "detail": "Yêu cầu vượt hạn mức hiện tại."
}
~~~

`Retry-After` có thể là **delay-seconds** không âm hoặc **HTTP-date** (RFC 9110). Nếu dùng token bucket, có thể tính gần đúng thời gian hồi quota; nếu còn global/tenant/operation policy khác, giá trị trả về phải phù hợp với **điều kiện chặn thực sự**, không hứa quá mức. Client cần xử lý clock skew, áp max backoff, jitter và deadline, không retry vô hạn chỉ vì server gợi ý.

Một số hệ dùng các header như `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` hoặc `RateLimit` theo contract cụ thể; tên/semantics và tình trạng chuẩn hóa phụ thuộc gateway, phiên bản và thỏa thuận API. **Không mặc định các header này luôn tồn tại hoặc mọi sản phẩm có cùng ngữ nghĩa.** Có thể không công bố con số còn lại nếu nó tiết lộ tenant plan, quota của user khác hoặc giúp attacker tối ưu dò giới hạn.

### 6.2. Phân biệt 429 với các lỗi khác

| HTTP status | Khi phù hợp | Không nên nhầm |
|---|---|---|
| **401 Unauthorized** | Chưa có/không có credential hợp lệ | Không dùng 429 thay cho authentication |
| **403 Forbidden** | Credential hợp lệ nhưng không có quyền | Quota không cấp thêm quyền |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ | Không phải request-rate |
| **429 Too Many Requests** | Chủ thể chạm rate/quota policy | Không nhất thiết server đang chết |
| **503 Service Unavailable** | Hệ thống tạm không thể phục vụ do quá tải/bảo trì | Có thể dùng `Retry-After`; không tự nhận là per-user quota |
| **504 Gateway Timeout** | Gateway không nhận response upstream đúng hạn | Không phải quota |

**Không trả 200 với body `{"error":"rate_limit"}`**, vì client, cache, monitoring và retry middleware sẽ hiểu sai trạng thái HTTP. Đồng thời, nếu load balancer/ingress trả 429 trước khi request vào ứng dụng, handler Spring sẽ **không được gọi**; phải chuẩn hóa response contract ở đúng enforcement point.

### 6.3. Tránh quota enumeration trong body lỗi

Không xuất `tenantId`, internal Redis key, username victim, số lượng user trong tổ chức hoặc `maxAllowedForPremiumAccount` của tenant khác. Nếu muốn cho khách hàng tự xem quota của mình, thiết kế API quản trị quota có **authorization và scoped projection riêng**. Public 429 có thể chỉ chứa status/code/Retry-After/request ID đã chuẩn hóa.

## 7. Java/Spring MVC: áp policy tại đúng điểm trong request pipeline

Một API Spring Boot 3 / Java 17 có thể áp hạn mức qua gateway và một `HandlerInterceptor` của Spring MVC. Interceptor chạy **sau handler mapping**, nên lấy được route template; trong cấu hình điển hình, Spring Security filter chain đã xác thực người gọi trước khi MVC nhận request.

### 7.1. Định nghĩa cổng quota và chính sách độc lập thuật toán

~~~java
// Kiểu dữ liệu ứng dụng; key đã được hash/chuẩn hóa ở lớp resolver.
record QuotaRule(
    String storageKey,
    int capacity,
    double refillTokensPerSecond,
    int cost
) {}

record Admission(boolean allowed, Duration retryAfter) {}

interface QuotaGate {
    // Hợp đồng: với các rules cùng nơi lưu, reserve all-or-nothing.
    Admission reserveAll(List<QuotaRule> rules);
}

interface RequestQuotaPolicy {
    List<QuotaRule> resolve(
        Authentication auth, String httpMethod, String routeTemplate);
}
~~~

`QuotaGate` là interface **giả định**, không phải lớp có sẵn của Spring/Bucket4j. Thực thi production cần bảo đảm atomicity hoặc công bố semantics gần đúng, clock, key TTL, xử lý Redis outage và metrics. `storageKey` phải ổn định, có namespace/version policy, không chứa token hay PII thô. Nếu không có quota cần áp, `reserveAll(emptyList)` được quy ước là allowed.

### 7.2. Một policy resolver minh họa với identity từ Spring Security

~~~java
@Component
class OrderQuotaPolicy implements RequestQuotaPolicy {
    @Override
    public List<QuotaRule> resolve(
            Authentication auth, String method, String route) {
        String operation = method + " " + route;

        // Public/anonymous endpoint có policy riêng ở edge/IP.
        if (auth == null || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            return List.of();
        }
        // Principal khác JWT phải có resolver riêng, không bypass quota.
        if (!(auth instanceof JwtAuthenticationToken jwt)) {
            throw new AccessDeniedException("Unsupported principal for quota");
        }

        String subject = jwt.getToken().getSubject();
        URI issuerUri = jwt.getToken().getIssuer();
        String tenant = jwt.getToken().getClaimAsString("tenant_id");
        if (issuerUri == null || subject == null
                || tenant == null || tenant.isBlank()) {
            throw new AccessDeniedException("Missing trusted identity scope");
        }
        String issuer = issuerUri.toString();

        // stableOpaqueKey là HMAC hoặc mapping nội bộ;
        // tuyệt đối không đưa raw JWT, email, API key vào Redis key.
        String userKey = stableOpaqueKey(issuer, tenant, subject);
        String tenantKey = stableOpaqueKey(issuer, tenant);

        var rules = new ArrayList<QuotaRule>();
        rules.add(new QuotaRule("tenant:" + tenantKey, 1200, 20.0, 1));
        rules.add(new QuotaRule("user:" + userKey, 100, 100.0 / 60, 1));

        if (operation.equals("GET /v1/orders")) {
            rules.add(new QuotaRule(
                "search:" + userKey, 30, 0.5, 1));
        }
        if (operation.equals("POST /v1/exports")) {
            rules.add(new QuotaRule(
                "export:" + tenantKey, 5, 5.0 / 600, 1));
        }
        return rules;
    }
}
~~~

**Đây là ví dụ về chọn scope, không phải policy production hoàn chỉnh.** `stableOpaqueKey(...)` là helper cần hiện thực bằng HMAC với secret riêng được bảo vệ hoặc ID vô danh ổn định; các imports/DTO bảo mật thông thường được lược. `issuer` là claim từ token **đã được resource server xác minh**; cần validate audience, tenant membership/entitlement. `tenant_id` không thể tin cậy nếu chỉ lấy từ JWT client tự decode. Với session hoặc API key, phải xây resolver tương ứng thay vì bỏ qua quota cho một loại principal.

Chú ý: bản demo thêm riêng quota search và export, nhưng chưa minh họa global cap hay IP edge cap. Đối với `POST /v1/exports`, cost=1 ở bucket export vì bucket **đếm job**, không phải chi phí CPU 10 tokens của policy chung; số lượng concurrent job phải có limiter khác. Policy production nên lấy từ cấu hình/version kiểm soát được, không hard-code tất cả số trong Java.

### 7.3. HandlerInterceptor tạo 429 an toàn

~~~java
@Component
class RateLimitInterceptor implements HandlerInterceptor {
    private final RequestQuotaPolicy policies;
    private final QuotaGate quota;
    private final ObjectMapper json;

    RateLimitInterceptor(
            RequestQuotaPolicy policies,
            QuotaGate quota, ObjectMapper json) {
        this.policies = policies;
        this.quota = quota;
        this.json = json;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest req,
            HttpServletResponse res,
            Object handler) throws IOException {
        Object matched = req.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        if (!(matched instanceof String route)) {
            // Unknown route: edge/global controls vẫn bảo vệ;
            // không tạo key từ raw URI.
            return true;
        }

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        Admission admission = quota.reserveAll(
            policies.resolve(auth, req.getMethod(), route));
        if (admission.allowed()) return true;

        long seconds = Math.max(1,
            (admission.retryAfter().toMillis() + 999L) / 1000L);
        res.setStatus(429);
        res.setContentType("application/problem+json");
        res.setHeader("Retry-After", Long.toString(seconds));
        res.setHeader("Cache-Control", "no-store");
        json.writeValue(res.getOutputStream(), Map.of(
            "type", "https://api.example.com/problems/rate-limit",
            "title", "Too Many Requests",
            "status", 429,
            "code", "RATE_LIMIT_EXCEEDED"));
        return false;
    }
}
~~~

Đăng ký qua `WebMvcConfigurer.addInterceptors(...)` cho các route muốn kiểm; tránh tự áp policy user lên endpoint login trước khi có identity. Với Spring MVC, interceptor là lựa chọn dễ thấy route template, nhưng **không thay thế web security filter**. Với Spring WebFlux, dùng `WebFilter`/handler filter phù hợp, không chặn event-loop bằng Redis client đồng bộ.

**Giới hạn của ví dụ:** không xử lý giá trị `retryAfter` âm/null hoặc cực lớn, tiêu thụ response body do servlet/container, hash-tag shard, configuration cache hay phân loại exception của quota store. Production phải validate policy, upper-bound Retry-After và chọn hành vi khi storage lỗi. Nếu muốn chuẩn hóa mọi 429 qua `ProblemDetail`, có thể tái sử dụng một error renderer; không trả exception thô chứa storage key/tenant.

### 7.4. Phải phân biệt rate limit với authorization khi trả response

Nếu endpoint yêu cầu `orders.read` nhưng token không có quyền, policy có thể chặn trước controller và phát 429 thay vì 403 khi quota đã hết. Quyết định **thứ tự xử lý** cần nhất quán theo threat model:

- Edge chặn **IP/global** trước authentication để giảm chi phí tấn công vô danh.
- Security filters xác thực/kiểm quyền cấp route, sau đó MVC quota **theo verified user/tenant**.
- Service vẫn kiểm **object-level authorization** và business invariant; quota không chứng minh quyền.

Nếu muốn 403 luôn được ưu tiên hơn 429 khi thiếu quyền resource, service phải kiểm visibility trước hoặc orchestration có policy rõ; nhưng việc query DB trước rate limit có thể mở đường abuse. Không hứa một thứ tự tuyệt đối cho tất cả endpoint; ghi rõ semantics và test không tiết lộ resource trong từng nhánh.

## 8. Distributed quota: nhiều instance phải cùng nhìn một ngân sách

Nếu dùng `ConcurrentHashMap<key, counter>` trong mỗi Pod, ba Pod có thể cho mỗi user dùng gấp ba lần quota dự kiến; sau autoscaling quota còn thay đổi. In-memory limiter vẫn hữu ích cho **local protection** (giới hạn mỗi instance), nhưng **không đủ để công bố quota toàn cụm chính xác**.

Một shared store như Redis có thể giữ bucket state và cập nhật bằng **atomic command/Lua/function**. Với một bucket, store phải đọc tokens, tính refill, kiểm cost, ghi lại state và TTL như **một thao tác nguyên tử** để hai request đồng thời không cùng tiêu token cuối. Với multi-policy reserve, xem giới hạn shard/hash-slot ở Mục 4.

~~~text
quota:v3:{tenantHash}:user:{userHash}:orders.search
  tokens = 4.5
  lastRefill = timestamp
  policyVersion = 3
  expireAfterIdle = bounded TTL
~~~

**Key mẫu chỉ minh họa cách nhóm; không tự copy hash-tag này vào mọi cluster.** TTL phải đủ giữ bucket state khi còn refill, nhưng có giới hạn để key của user/IP không tồn tại mãi. Hạn chế cardinality cho IP attacker, tránh key chứa email/raw bearer token và kiểm tra Redis memory/eviction policy. Nếu state bị evict, quota có thể được reset sớm: đánh giá tác động đến fairness.

### 8.1. Lỗi kho quota: fail-open hay fail-closed?

| Operation | Khi Redis/quota service lỗi | Lý do |
|---|---|---|
| Đọc catalog giá rẻ | Có thể **fail-open có giám sát** + local emergency cap | Giữ availability, nhưng vẫn bảo vệ hạ tầng |
| Login, password reset, OTP | Thường **fail-closed** hoặc fallback chặt chẽ | Tránh brute force nếu mất lớp bảo vệ |
| Export tốn kém, payment-like action | Thường fail-closed/fallback bounded | Tránh quá tải, chi phí và lạm dụng |
| Internal health check | Policy riêng | Không làm mất tín hiệu readiness vì quota user |

Đây là **trade-off thiết kế**, không có quy tắc bắt buộc cho mọi tổ chức. Fail-open không có giới hạn có thể tạo overload cascade; fail-closed không có fallback có thể gây outage diện rộng. Metric cần phân biệt `allowed`, `denied`, `store_error`, `fallback_used` và `quota_latency` theo **scope/route group**, không theo raw user ID/token.

### 8.2. Kết hợp concurrency limit, queue và circuit breaker

Nếu `POST /v1/exports` nhận 5 request/phút nhưng mỗi job chạy 30 phút, chỉ rate limit vẫn có thể để 150 job tồn đọng. Cần thêm **max queued/running jobs**, queue capacity, cancellation, deadline và xử lý `202 Accepted` với operation status. Circuit breaker bảo vệ khi downstream lỗi; bulkhead/concurrency limit bảo vệ thread/connection pool; rate limit bảo vệ lưu lượng đến. Chúng giải quyết **các trục khác nhau**.

## 9. Bảo mật của khóa hạn mức và chống né quota

- **Trusted IP:** proxy/CDN phải xác định chain tin cậy, strip header giả, xử lý IPv4/IPv6. Nếu trusted proxy config sai, attacker tự thay IP qua `X-Forwarded-For` mỗi request.
- **Trusted identity:** xác minh JWT signature, issuer, audience, expiry và tenant membership; không tin `sub`/`tenant` ở payload chưa verify. Cần scope riêng cho OAuth client credentials.
- **Không tạo quota key từ raw URL:** `/orders/o-1` và `/orders/o-2` phải chia operation budget; query filter mới có thể tăng cost theo giá trị đã validate.
- **Không tiết lộ PII:** Redis key và metric label dùng stable pseudonymous ID/HMAC theo quản trị; log 429 chỉ ghi request ID, scope class, route template, reason code, không raw token.
- **Không khóa oan account:** login fail policy có thể kết hợp IP, account hash và phát hiện abuse; attacker biết username không được dễ dàng tiêu hết quota của nạn nhân trong thời gian dài. Có cap theo IP và cơ chế khôi phục/cảnh báo.
- **Không dùng hạn mức làm authorization:** khi caller ngoài tenant, endpoint vẫn cần 404/403 trung tính theo visibility policy; thông báo 429 không được công bố nội dung/resource/plan của tenant khác.

**Rate limiting là một quyết định bảo mật/kinh doanh có thể thay đổi.** Version policy và ghi lại lý do thay đổi, dùng feature flag/canary cho thay đổi quota lớn, xem tỷ lệ 429 ở khách hợp lệ, hỗ trợ emergency override có quyền/audit/TTL. Đừng tạo “whitelist VIP” vô thời hạn bỏ mọi defense.

## 10. Kiểm thử phạm vi hạn mức và HTTP response

### 10.1. Ma trận bắt buộc

| Test | Thiết lập | Cần chứng minh |
|---|---|---|
| R01 | User A gửi quá `orders.search` limit | **429** + `Retry-After`, controller/service không chạy |
| R02 | User A hết quota, user B còn | User B vẫn được phục vụ nếu tenant quota còn |
| R03 | Nhiều user thuộc tenant A cùng gọi | Đụng tenant cap thì bị chặn dù user cap còn |
| R04 | Tenant A hết quota, tenant B còn | B không bị khóa nhầm |
| R05 | Cùng user đổi access token/JWT `jti` | Không reset user quota |
| R06 | Request vô danh đổi `X-Forwarded-For` giả | Không tạo key IP mới từ header không tin cậy |
| R07 | Hai order IDs khác nhau cùng route template | Tiêu chung operation bucket, không chia quota theo raw ID |
| R08 | `POST /exports` so với `GET /orders` | Áp cost và burst theo operation; job concurrency riêng |
| R09 | Hai request đồng thời còn đúng một token | Tối đa một request được chấp nhận |
| R10 | Multi-scope check: user hết, tenant còn | Không tiêu tenant token nếu hứa all-or-nothing |
| R11 | Redis/quota store timeout | Fail-open/fail-closed và fallback đúng theo policy |
| R12 | 429 body và header | Problem Details an toàn, không lộ user/tenant/token/key |
| R13 | `401/403` + quota | Auth không bypass; không biến mọi lỗi security thành 429 |
| R14 | Burst hợp lệ rồi refill qua thời gian | Nhận burst trong giới hạn, refill đúng clock và TTL |

### 10.2. Unit test Spring MVC interceptor

~~~java
@ExtendWith(MockitoExtension.class)
class RateLimitInterceptorTest {
    @Mock RequestQuotaPolicy policies;
    @Mock QuotaGate quota;
    RateLimitInterceptor interceptor;

    @BeforeEach
    void setup() {
        interceptor = new RateLimitInterceptor(
            policies, quota, new ObjectMapper());
    }

    @Test
    void overQuotaReturns429AndRetryAfter() throws Exception {
        var req = new MockHttpServletRequest(
            "GET", "/v1/orders/o-42");
        req.setAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,
            "/v1/orders/{id}");
        var res = new MockHttpServletResponse();
        var rules = List.of(new QuotaRule(
            "user:opaque", 100, 100.0 / 60, 1));
        when(policies.resolve(
            any(), eq("GET"), eq("/v1/orders/{id}")))
            .thenReturn(rules);
        when(quota.reserveAll(rules))
            .thenReturn(new Admission(false, Duration.ofSeconds(7)));

        boolean proceed = interceptor.preHandle(req, res, new Object());

        assertFalse(proceed);
        assertEquals(429, res.getStatus());
        assertEquals("7", res.getHeader("Retry-After"));
        assertTrue(res.getContentAsString()
            .contains("RATE_LIMIT_EXCEEDED"));
        assertFalse(res.getContentAsString().contains("user:opaque"));
        verify(quota).reserveAll(rules);
    }
}
~~~

Ví dụ dùng JUnit 5, Mockito, Spring MockHttpServletRequest/Response và Jackson; cần thêm imports/lifecycle của Spring Test. Test kiểm **đường 429 của interceptor**, chưa kiểm chính sách JWT/tenant thực sự. Bổ sung `@SpringBootTest + @AutoConfigureMockMvc` để xác minh security filter và interceptor registration qua HTTP, `jwt()` từ Spring Security Test chỉ **giả lập principal** chứ không test chữ ký JWT.

### 10.3. Concurrency và bảo vệ người dùng thật

Unit test mock quota store không chứng minh Redis atomicity. Hãy chạy integration test với Redis tương tự production: cho N request cùng lúc khi bucket chỉ có một token, assert đúng một success, số token không âm, không refund đôi; test đa instance/shard và key TTL. Với fail-open/fail-closed, mô phỏng timeout quota store, không chỉ ném exception trong controller.

Test thêm NAT (nhiều user cùng IP), IPv6, proxy header giả, anonymous login, cache và tenant upgrade/downgrade policy. Khi đo false-positive 429, quan sát theo **route group/scope/plan** đã được ẩn danh, không ghi bearer token hoặc PII làm metric label.

## 11. Bài tập: thiết kế quota cho SaaS nhiều tenant

**Đề bài:** API có các route `GET /v1/orders/{id}`, `GET /v1/orders`, `POST /v1/exports` và `POST /v1/auth/login`. Có tenant A gồm 200 nhân viên và tenant B gồm 5 nhân viên; cả hai sử dụng NAT công ty. Nhiều worker chạy trên 3 Pod. Hãy chọn scope, key, phương pháp enforcement và status khi chạm hạn mức.

**Phương án tham khảo:**

| Route | Scope/identity | Enforcement |
|---|---|---|
| GET detail | USER + TENANT, cùng operation read | Security verified principal, quota store shared, scope query |
| GET collection | USER + TENANT + `orders.search` | Cost theo query/limit đã validate; sort/page giới hạn |
| POST export | TENANT + USER + `exports.create` | Bucket weighted/job quota + max concurrent jobs; server trả 202 nếu accepted |
| POST login | IP tin cậy + account hash; global edge | Chặn brute force trước authentication; response không tiết lộ account tồn tại |

Không chỉ giới hạn IP cho nhân viên vì NAT gây khóa oan. Mỗi user có quota riêng nhưng tenant còn có trần chung. Redis/limiter distributed cho quota toàn cụm; cache local chỉ là lớp bảo vệ phụ. `429` kèm `Retry-After` khi vượt quota, còn downstream quá tải có thể dùng `503`. Thử lại lệnh export chỉ khi hợp đồng idempotency bảo vệ tránh tạo job trùng.

**Câu hỏi nâng cao:** U1 hết quota user nhưng tenant còn quota. Nếu code trừ tenant bucket trước rồi mới kiểm user, có vi phạm công bằng không? **Có** nếu hợp đồng hứa request bị từ chối không tiêu quota tenant; cần atomic reserve-all hoặc chọn semantics nhiều tầng và công khai trade-off.

## 12. Checklist thiết kế và nguồn tham khảo

- [ ] Mỗi route có **scope/key/quota/cost/burst** được định nghĩa theo mục tiêu fairness, abuse hoặc resilience.
- [ ] Identity user, tenant và OAuth client đến từ xác thực tin cậy; IP từ trusted proxy chain, không từ header tự khai.
- [ ] Operation là **method + route template/group**, không phải raw URI/ID.
- [ ] Có cả user và tenant/global controls để tránh noisy neighbor và multi-account bypass.
- [ ] Multi-bucket reservation có semantics rõ; không trừ quota oan khi nhánh khác từ chối.
- [ ] Distributed store cập nhật atomic, có TTL/cardinality limits, metrics, và fail-open/fail-closed policy.
- [ ] Rate limit khác concurrency limit, queue capacity, circuit breaker và authorization.
- [ ] 429 trả HTTP status đúng, `Retry-After` hợp lệ, Problem Details không lộ thông tin nội bộ.
- [ ] Retry client có deadline/jitter/budget; POST chỉ retry an toàn khi có idempotency bảo đảm.
- [ ] Test MockMvc/security, Redis concurrency, NAT/IP spoofing, multiple tenants, policy change và store outage.

**Tham khảo:** [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585), [RFC 9110 — HTTP Semantics/Retry-After](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [Spring MVC HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html), [Spring Security Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html), [OWASP API Security Top 10](https://owasp.org/API-Security/).

**Kết luận:** câu hỏi quan trọng nhất của rate limiting là **“ngân sách thuộc về ai và bảo vệ điều gì?”** User limit tạo công bằng cá nhân, tenant limit bảo vệ tổ chức và hệ thống, IP limit hỗ trợ chống abuse vô danh, operation limit bảo vệ tuyến tốn kém. Ghép các phạm vi theo identity **đã xác thực**, định nghĩa atomicity/failure mode, trả HTTP 429 đúng hợp đồng và kiểm thử đa tenant/concurrency sẽ giúp REST API vừa công bằng vừa chống lỗi.
