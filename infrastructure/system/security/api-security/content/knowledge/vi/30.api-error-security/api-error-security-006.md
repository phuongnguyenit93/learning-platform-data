# Log server-side đủ chi tiết để điều tra

## 1. Vì sao API cần server-side log có thể điều tra?

Khi API gặp sự cố hoặc bị tấn công, response mà client nhìn thấy thường không đủ để xác định chuyện gì đã xảy ra. Một `401`, `403`, `500` hoặc thông báo “request failed” không cho biết credential nào đã được xác minh, policy nào từ chối, service nào xử lý, object nào bị tác động hay request có tạo side effect trước khi lỗi hay không.

Server-side logging ghi lại sự kiện quan trọng từ góc nhìn của hệ thống: request đi qua route nào, principal nào đã được xác minh, quyết định authorization ra sao, service phụ thuộc có lỗi không, dữ liệu nào bị thay đổi ở mức định danh phù hợp và kết quả cuối cùng là gì. Khi các log được liên kết bằng request/correlation ID và timestamp nhất quán, đội vận hành có thể tái dựng chuỗi sự kiện, khoanh vùng ảnh hưởng và xử lý sự cố.

Log hữu ích cần cân bằng hai yêu cầu:

- **Đủ ngữ cảnh để điều tra:** xác định actor, action, resource, decision, thời gian, nơi xử lý và kết quả.
- **Không tạo thêm rủi ro dữ liệu:** không làm lộ password, token, API key, cookie, private key, dữ liệu cá nhân hoặc payload nhạy cảm.

Ghi toàn bộ request/response body không đồng nghĩa với khả năng điều tra tốt. Nó thường làm tăng chi phí, nhiễu, rủi ro lộ dữ liệu và khối lượng cần bảo vệ. Hãy log có cấu trúc theo sự kiện và chọn field có mục đích rõ.

## 2. Phân biệt application log, security event và audit log

Ba loại log có mục đích khác nhau và có thể được lưu ở các pipeline riêng:

| Loại | Mục đích | Ví dụ | Yêu cầu nổi bật |
|---|---|---|---|
| Application/operational log | Vận hành, debug lỗi, theo dõi hiệu năng và dependency. | Timeout khi gọi payment provider, lỗi deserialize, database pool cạn. | Có service/version, severity, trace/request ID, error class và latency. |
| Security event log | Phát hiện hành vi đáng ngờ và điều tra sự kiện bảo mật. | Token validation fail, brute force, rate limit, authorization deny, SSRF destination bị chặn. | Có actor/source, decision, policy, route và tín hiệu bảo mật phù hợp. |
| Audit log | Ghi lại hành động quan trọng và ai đã thực hiện để đáp ứng trách nhiệm giải trình. | Thay đổi role, tạo API key, tải file nhạy cảm, hoàn tiền, thay webhook URL. | Có actor, action, target, thời điểm, kết quả và nguồn; cần bảo vệ integrity/retention. |

Một sự kiện có thể xuất hiện ở nhiều loại log với mức chi tiết khác nhau. Ví dụ, khi admin thu hồi API key, audit log ghi ai thu hồi key nào và kết quả; security event có thể ghi credential bị thu hồi vẫn tiếp tục được sử dụng; application log ghi lỗi xác thực ở route tương ứng. Tránh nhân bản payload nhạy cảm ở mọi pipeline.

Không dùng debug log thay audit log. Debug level thường bị tắt, sampling hoặc xoay vòng ngắn; audit record của hành động quan trọng cần có chính sách lưu giữ và kiểm soát truy cập riêng.

## 3. Thiết kế event schema có cấu trúc

Log dạng JSON hoặc định dạng structured tương đương giúp tìm kiếm và tổng hợp chính xác hơn log văn bản tự do. Mỗi event nên có schema ổn định, tên field nhất quán và version khi cần thay đổi.

Một event server-side có thể gồm các nhóm field:

| Nhóm | Field gợi ý | Ý nghĩa |
|---|---|---|
| Thời gian | `timestamp`, `observed_at` | Thời điểm event xảy ra và thời điểm collector nhận event nếu cần. Dùng UTC và định dạng nhất quán. |
| Nguồn phát | `service.name`, `service.version`, `environment`, `instance.id` | Xác định service, phiên bản và instance phát log. |
| Correlation | `request.id`, `trace.id`, `span.id`, `correlation.id` | Liên kết request qua gateway, service và dependency. |
| HTTP | `http.method`, `http.route`, `http.status_code`, `duration_ms` | Mô tả route và kết quả; ưu tiên route template thay vì raw path có ID nhạy cảm. |
| Actor | `actor.type`, `actor.id`, `client.id`, `tenant.id` | Principal đã được xác minh hoặc service account; dùng ID nội bộ/pseudonymous khi phù hợp. |
| Network | `source.ip`, `client.address`, `user_agent` | Tín hiệu nguồn; chỉ tin forwarded header từ proxy đã cấu hình. |
| Authentication | `auth.mechanism`, `auth.issuer`, `auth.result`, `auth.failure_reason` | Cơ chế và kết quả xác thực, không ghi credential/token. |
| Authorization | `authorization.action`, `authorization.resource_type`, `authorization.decision`, `authorization.policy_id` | Hành động, loại resource, quyết định và policy áp dụng. |
| Outcome | `event.name`, `event.category`, `outcome`, `error.code` | Sự kiện nghiệp vụ/bảo mật và kết quả chuẩn hóa. |
| Dependency | `dependency.name`, `dependency.operation`, `dependency.status`, `dependency.duration_ms` | Lỗi/độ trễ từ database, queue hoặc provider. |

Không phải mọi event đều cần mọi field. Hãy định nghĩa schema theo loại event và chỉ ghi dữ liệu thực sự có sẵn. Tránh tạo field có giá trị tùy ý hoặc đưa toàn bộ object vào một chuỗi `message` khó phân tích.

Ví dụ event JSON rút gọn:

```json
{
  "timestamp": "2026-11-18T09:15:30.482Z",
  "event.name": "api.authorization.denied",
  "event.category": "security",
  "service.name": "orders-api",
  "service.version": "2.8.1",
  "environment": "production",
  "request.id": "req_01JCV4R7X9",
  "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.method": "GET",
  "http.route": "/api/orders/{orderId}",
  "http.status_code": 403,
  "actor.type": "user",
  "actor.id": "usr_8d2f",
  "tenant.id": "ten_42",
  "authorization.action": "order.read",
  "authorization.resource_type": "order",
  "authorization.decision": "deny",
  "authorization.policy_id": "order-owner-or-support-v3",
  "outcome": "denied"
}
```

Ví dụ dùng ID giả để minh họa. Production nên xác định mức độ nhạy cảm của actor/tenant/resource ID; có thể dùng mã nội bộ, tokenized ID hoặc pseudonymous identifier thay vì email, số điện thoại hay dữ liệu định danh trực tiếp.

## 4. Correlation ID, request ID và distributed trace

Một request có thể đi qua CDN, API gateway, authentication service, nhiều backend, queue worker và provider bên ngoài. Nếu mỗi service tạo một ID riêng mà không giữ liên kết, việc điều tra chuỗi sự kiện sẽ khó.

Nên phân biệt:

- **Request ID:** định danh một lần tiếp nhận request tại một service/edge. Có thể tạo mới ở mỗi hop và lưu ID upstream riêng.
- **Correlation ID:** định danh một luồng nghiệp vụ qua nhiều request hoặc service, ví dụ một lần checkout.
- **Trace ID:** định danh distributed trace; span ID xác định một đoạn xử lý trong trace.
- **Provider event/request ID:** ID do hệ thống ngoài cấp, hữu ích khi đối soát với nhà cung cấp.

Một cách triển khai là gateway tạo request ID nếu chưa có, ghi lại giá trị client cung cấp như `external_request_id` sau khi giới hạn/kiểm tra, rồi truyền request ID nội bộ qua header được kiểm soát. Trace context có thể theo W3C Trace Context (`traceparent`, `tracestate`) qua thư viện tracing.

Không tin một `X-Request-ID` do client gửi như định danh duy nhất và đáng tin. Client có thể cố tình gửi ID trùng, chứa ký tự điều khiển hoặc tạo log confusion. Server có thể:

1. Tạo ID nội bộ có entropy đủ lớn ở edge.
2. Giữ giá trị correlation do caller cung cấp trong field riêng, có giới hạn độ dài và ký tự.
3. Ghi lại quan hệ upstream/downstream khi chuyển request.
4. Không cho phép ID từ client ghi đè MDC/context nội bộ.

Trace ID hữu ích để điều tra latency và đường đi request nhưng không thay audit log. Sampling có thể bỏ một số trace; audit event quan trọng không nên phụ thuộc vào việc trace có được sample hay không.

## 5. Log những gì cho một API request?

Với mỗi request, có thể ghi một event access summary ở cuối xử lý:

- Thời điểm, service/version/environment và request ID.
- HTTP method, route template, status code và duration.
- Principal/client/tenant đã xác minh ở dạng phù hợp với chính sách dữ liệu.
- Authentication result và authorization outcome ở mức tổng quát.
- Kích thước request/response nếu cần cho abuse/capacity monitoring; không ghi body.
- Upstream/dependency status và error code đã chuẩn hóa.
- Retry count, rate-limit decision hoặc quota class nếu liên quan.

Không nhất thiết log mỗi header hoặc mọi query parameter. Path thực tế có thể chứa email, token hoặc ID nhạy cảm; ưu tiên route template như `/api/users/{userId}`. Nếu cần resource ID để điều tra, ghi riêng theo classification và retention policy.

Với request thành công thông thường, access summary có thể ở mức `INFO` hoặc được xử lý bằng telemetry phù hợp. Với request bị từ chối, xác thực thất bại hoặc hành vi bất thường, tạo security event riêng có field chuyên biệt. Tránh ghi cùng một lỗi ở gateway, filter, controller và exception handler với stack trace lặp lại; chọn nơi chịu trách nhiệm ghi event để log không bị nhân bản.

## 6. Authentication và authorization event

Các sự kiện bảo mật cần ghi đủ ngữ cảnh để phân biệt lỗi người dùng bình thường với hành vi tấn công.

### Authentication

Nên ghi:

- Cơ chế: session, OAuth/JWT, API key, mTLS, workload identity.
- Kết quả: success/failure/revoked/expired/invalid audience.
- Issuer hoặc client ID đã xác minh nếu phù hợp.
- Route hoặc auth operation, source network signal và request ID.
- Lý do thất bại đã chuẩn hóa, ví dụ `token_expired`, `invalid_signature`, `unknown_key_id`.

Không ghi password, raw JWT, API key, session cookie, refresh token, Authorization header hoặc private key. Không ghi toàn bộ JWT payload để “xem claim”; nếu cần claim phục vụ điều tra, chọn một số claim không nhạy cảm đã được duyệt như issuer, audience label, client ID hoặc token ID đã hash/pseudonymize.

### Authorization

Khi policy từ chối, nên ghi:

- Actor đã được xác minh (user/client/service) và tenant context nếu có.
- Action/function đang yêu cầu.
- Resource type và ID ở dạng được phép ghi log.
- Policy/permission ID và quyết định allow/deny.
- Lý do tổng quát: thiếu scope, không phải owner, sai tenant, trạng thái không hợp lệ.
- Request/trace ID để liên kết với access log.

Không log toàn bộ object hoặc dữ liệu field để giải thích vì sao bị từ chối. Ví dụ, ghi `resource_type=invoice`, `resource_id=inv_...`, `decision=deny`, `reason=tenant_mismatch` thường hữu ích hơn ghi toàn bộ invoice payload.

Với hành động đặc quyền như đổi role, tạo key, thay policy hoặc truy cập dữ liệu nhạy cảm, cần audit event ngay cả khi thao tác thành công. Ghi cả actor, target, before/after ở dạng đã giới hạn hoặc diff field được duyệt, approval/reference ID và outcome.

## 7. Log lỗi server đủ chi tiết nhưng response vẫn an toàn

Server-side log có thể chứa stack trace, exception class, dependency name, SQL state hoặc error code nội bộ khi cần điều tra. Client-facing response nên ổn định và không tiết lộ chi tiết triển khai.

Ví dụ:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed.",
  "requestId": "req_01JCV4R7X9"
}
```

Server log tương ứng có thể ghi:

```json
{
  "event.name": "api.request.failed",
  "request.id": "req_01JCV4R7X9",
  "http.route": "/api/orders/{orderId}",
  "http.status_code": 500,
  "error.type": "org.springframework.dao.DataAccessResourceFailureException",
  "error.code": "DB_CONNECTION_TIMEOUT",
  "dependency.name": "orders-db",
  "duration_ms": 3000,
  "outcome": "failure"
}
```

Stack trace có thể được đính kèm trong application log có quyền truy cập hạn chế, nhưng cần kiểm soát để exception message không chứa connection string, SQL bind value, credential hoặc dữ liệu người dùng. Không trả stack trace, class name, hostname nội bộ, SQL hoặc filesystem path cho caller.

Không bắt exception rồi chỉ log `e.getMessage()` nếu message có thể rỗng hoặc thiếu stack context; cũng không log cả exception ở nhiều tầng. Chọn boundary xử lý lỗi có đủ context để log một lần, gắn request ID và trả error response đã chuẩn hóa.

## 8. Những dữ liệu không nên ghi vào log

Log thường được chuyển tới nhiều hệ thống, lưu lâu và được nhiều nhóm truy cập hơn database nghiệp vụ. Do đó phải coi log là một data store cần phân loại và bảo vệ.

| Dữ liệu | Cách xử lý |
|---|---|
| Password, PIN, OTP, recovery code | Không ghi. Ghi event result/reason thay thế. |
| Access/refresh token, JWT, API key, session cookie | Không ghi raw value; redaction ở logger/collector và không log header chứa credential. |
| Private key, signing secret, webhook secret | Không ghi. Chỉ ghi key ID/version không nhạy cảm nếu cần. |
| Authorization/Cookie/Set-Cookie headers | Loại bỏ khỏi request/response logging. |
| Số thẻ, CVV, bank account, payment payload | Không ghi; dùng reference/tokenized ID và trạng thái nghiệp vụ. |
| PII như email, số điện thoại, địa chỉ, ngày sinh | Chỉ ghi khi có mục đích hợp lệ; ưu tiên pseudonymization/masking hoặc ID nội bộ. |
| Request/response body | Mặc định không ghi; chỉ chọn field allowlist đã đánh giá và giới hạn kích thước. |
| Query string | Không ghi toàn bộ nếu có thể chứa token, reset code, email hoặc dữ liệu nhạy cảm. |
| File content, signed URL, presigned query | Không ghi nội dung hoặc URL bearer capability; log file ID/operation. |
| SQL statement và bind values | Tránh bind values nhạy cảm; dùng error code/query fingerprint khi điều tra. |

Redaction nên được thực hiện ở nhiều tầng: ứng dụng không tạo log chứa secret, logging encoder/filter loại bỏ field nhạy cảm, collector có policy bổ sung và quyền truy cập log được giới hạn. Redaction ở collector không thể cứu dữ liệu đã được ghi ra file local hoặc console trước đó.

Không dựa vào regex tổng quát để xóa mọi secret khỏi một chuỗi JSON tùy ý. Dùng structured logging, allowlist field, serializer có kiểm soát và data classification. Nếu không biết field có nhạy cảm hay không, mặc định không log.

## 9. Chống log injection và dữ liệu giả mạo

Attacker có thể gửi username, filename, header, query parameter hoặc error string chứa newline, tab, delimiter hay ký tự điều khiển để tạo log entry giả hoặc làm hỏng parser.

Ví dụ input:

```text
alice\n2026-11-18 INFO admin login successful
```

Nếu ghi nguyên chuỗi vào log text, một input có thể trông như hai event. Structured JSON logger thường escape ký tự điều khiển đúng cách, nhưng vẫn cần giới hạn độ dài và tránh đưa raw input vào field có cấu trúc.

Nguyên tắc:

- Dùng logging framework với parameterized message/structured fields, không nối chuỗi thủ công.
- Chuẩn hóa hoặc encode dữ liệu không tin cậy theo format log.
- Giới hạn độ dài username, filename, user-agent, external request ID và error details.
- Không cho input tự chọn `level`, `timestamp`, `service.name`, `actor.id` hoặc tên event.
- Dùng field riêng như `input.user_agent` thay vì ghép vào message có cấu trúc.
- Tránh log raw URL có query string hoặc header tùy ý.
- Xem mọi dữ liệu từ client/provider là untrusted, kể cả giá trị xuất hiện trong exception message.

## 10. Ví dụ structured logging với Spring Boot

### Gắn request ID và MDC

Với Servlet stack, filter có thể tạo request ID nội bộ và đặt vào MDC trong suốt request. Cần xóa MDC trong `finally` vì thread pool tái sử dụng thread.

```java
@Component
public class RequestContextFilter extends OncePerRequestFilter {
    private static final String REQUEST_ID = "request.id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        MDC.put(REQUEST_ID, requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(REQUEST_ID);
            // Nếu filter quản lý nhiều MDC key, dùng MDC.clear()
            // hoặc khôi phục context trước đó theo framework convention.
        }
    }
}
```

Ví dụ này luôn tạo request ID mới ở service. Trong hệ thống có gateway, có thể truyền request ID nội bộ đã được gateway xác thực qua trusted header; nếu nhận ID từ client, giữ riêng thành `external_request_id` và không dùng nó để ghi đè context nội bộ. Nếu dùng OpenTelemetry, lấy trace/span context từ SDK thay vì tự parse và tin header tùy ý.

### Ghi access summary

Một filter/interceptor có thể ghi thời gian và kết quả sau khi xử lý:

```java
long started = System.nanoTime();
try {
    filterChain.doFilter(request, response);
} finally {
    long durationMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - started);

    log.atInfo()
        .addKeyValue("http.method", request.getMethod())
        .addKeyValue("http.route", routeTemplate(request))
        .addKeyValue("http.status_code", response.getStatus())
        .addKeyValue("duration_ms", durationMs)
        .addKeyValue("request.id", MDC.get("request.id"))
        .log("api.request.completed");
}
```

`routeTemplate(request)` là hàm minh họa cần lấy route pattern từ framework sau khi mapping; không dùng raw URI nếu path có thể chứa dữ liệu nhạy cảm. Chọn log level và event name theo policy. Nếu exception được xử lý ở exception handler, cần tránh ghi thêm một access error duplicate với stack trace không cần thiết.

### Ghi authorization denial

```java
public void logAccessDenied(
        String actorId,
        String action,
        String resourceType,
        String resourceId,
        String policyId,
        String reason) {

    securityLog.atWarn()
        .addKeyValue("event.name", "api.authorization.denied")
        .addKeyValue("actor.id", actorId)
        .addKeyValue("authorization.action", action)
        .addKeyValue("authorization.resource_type", resourceType)
        .addKeyValue("authorization.resource_id", resourceId)
        .addKeyValue("authorization.policy_id", policyId)
        .addKeyValue("authorization.reason", reason)
        .log("Authorization denied");
}
```

Chỉ truyền actor/resource ID đã được phân loại và cho phép ghi. Không truyền entity hoặc request DTO vào logger vì `toString()` có thể in toàn bộ field, kể cả secret hoặc PII. Tránh đưa nội dung exception do client kiểm soát vào `reason`; dùng enum/error code đã chuẩn hóa.

## 11. Context propagation qua async và message queue

Request có thể tạo background job hoặc message xử lý sau khi HTTP response đã trả. MDC/ThreadLocal không tự động truyền an toàn qua executor, reactive pipeline hoặc queue.

- Propagate trace context bằng thư viện tracing/instrumentation được hỗ trợ.
- Truyền correlation ID và event ID tường minh trong message metadata nếu cần liên kết nghiệp vụ.
- Chỉ truyền actor/tenant context đã xác minh và tối thiểu cần thiết; consumer vẫn phải xác minh producer và authorization policy của workload.
- Không serialize toàn bộ SecurityContext, token hoặc session vào message.
- Khi worker bắt đầu xử lý, tạo context cho task và cleanup sau khi hoàn tất để tránh rò context sang task kế tiếp.
- Giữ provider request ID hoặc webhook event ID riêng để đối soát.

Với reactive stack, dùng Reactor Context hoặc cơ chế context propagation của framework thay vì dựa vào ThreadLocal. Kiểm thử context qua thread switch, retry và scheduler boundary.

## 12. Bảo vệ log storage và pipeline

Log có thể chứa thông tin giúp attacker hiểu kiến trúc, user, endpoint và hoạt động nội bộ. Hệ thống log cần được bảo vệ như một tài sản quan trọng.

### Truyền và lưu trữ

- Gửi log qua kênh TLS hoặc agent/collector có xác thực.
- Giới hạn quyền ghi theo workload identity; service không được tùy ý sửa/xóa log của service khác.
- Dùng storage tập trung với phân quyền theo team, environment và loại log.
- Mã hóa at rest và quản lý key riêng theo tiêu chuẩn tổ chức.
- Tách security/audit log khỏi log debug thông thường nếu cần mức integrity/retention khác.
- Giới hạn quyền export/download và audit hoạt động truy cập log.

### Integrity và retention

- Dùng append-only/immutable storage hoặc cơ chế tamper-evident cho audit log quan trọng khi yêu cầu rủi ro/compliance cần.
- Đồng bộ thời gian bằng nguồn đáng tin cậy; ghi UTC và theo dõi clock drift.
- Định nghĩa retention theo mục đích, loại dữ liệu, pháp lý và nhu cầu điều tra; không giữ vô hạn “phòng khi cần”.
- Có chính sách xóa/ẩn danh khi hết hạn và kiểm tra backup/replica.
- Giám sát việc log pipeline bị gián đoạn, backlog tăng hoặc agent ngừng gửi.

Không phải mọi application log đều cần immutable storage. Hãy dành mức bảo vệ cao cho audit/security event quan trọng, đồng thời giữ application log theo retention phù hợp để kiểm soát chi phí và dữ liệu cá nhân.

## 13. Sampling, volume và tránh log storm

Ghi mọi request ở mức chi tiết cao có thể làm tăng chi phí và khiến sự kiện quan trọng bị chìm trong nhiễu. Tuy nhiên, sampling sai có thể bỏ mất dấu hiệu tấn công hoặc hành động đặc quyền.

- Access log thành công có thể sampling hoặc aggregate theo traffic nếu vẫn giữ metrics cần thiết.
- Authentication failure, authorization denial nhạy cảm, key/role change và audit event quan trọng cần policy ghi nhận riêng; không để sampling trace vô tình bỏ qua chúng.
- Khi một client tạo hàng triệu lỗi, aggregate theo time bucket/actor/reason và giữ mẫu có kiểm soát để tránh log storm.
- Dùng rate limit cho security event logging nhưng phải có metric cho số event bị suppress/drop.
- Đặt giới hạn kích thước event, queue và disk; có backpressure và cảnh báo khi log pipeline chậm.
- Không để logging failure làm API nhạy cảm âm thầm bỏ qua audit bắt buộc; quyết định fail-open/fail-closed theo loại operation và yêu cầu kiểm soát.

Ví dụ, nếu không thể ghi audit event cho thao tác thay đổi quyền admin, có thể phải từ chối thao tác để bảo đảm trách nhiệm giải trình. Với endpoint đọc công khai, log collector tạm thời lỗi có thể không cần làm ngừng toàn bộ API nếu local buffer và monitoring đã được thiết kế.

## 14. Alert và điều tra trong SIEM/observability

Log chỉ có giá trị khi có thể tìm, liên kết và phát hiện tín hiệu bất thường. Các rule nên dựa trên nhiều sự kiện và baseline thay vì cảnh báo cho mọi lỗi đơn lẻ.

Ví dụ tín hiệu:

- Nhiều lần `invalid_signature` hoặc `unknown_key_id` từ một source/client.
- Một principal nhận nhiều `403` trên nhiều object/tenant trong thời gian ngắn.
- API key đã revoke vẫn được sử dụng.
- Một workload gọi endpoint admin hoặc service không nằm trong dependency graph được duyệt.
- Thay đổi role, policy, webhook destination hoặc CORS allowlist ngoài lịch/approval.
- Tăng đột biến `429`, `5xx`, timeout, request body size hoặc export volume.
- Một user tải nhiều file nhạy cảm hoặc truy cập hàng loạt object không thuộc quan hệ thông thường.
- Log pipeline ngừng nhận event từ service quan trọng hoặc timestamp lệch bất thường.

Khi alert kích hoạt, analyst cần có dashboard/truy vấn theo request ID, trace ID, actor, tenant, route, resource, policy và time range. Dùng runbook quy định cách xác minh, phạm vi ảnh hưởng, thu hồi credential, chặn route, bảo toàn evidence và thông báo nội bộ.

Không đưa raw secret hoặc payload vào SIEM rule. Alert message nên có event ID, loại tín hiệu, actor pseudonymous, service, severity và link truy vấn có kiểm soát.

## 15. Những anti-pattern logging thường gặp

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Log toàn bộ request/response body | Lộ token, PII, payment data và file content. | Structured event với allowlist field; body mặc định không log. |
| Log `Authorization`/Cookie header | Credential bị sao chép vào nhiều hệ thống. | Redact ở app và collector; loại bỏ header khỏi log. |
| Chỉ log `e.getMessage()` | Thiếu stack context hoặc message chứa dữ liệu nhạy cảm. | Log error type/code và stack ở nơi phù hợp, có redaction. |
| Trả stack trace cho client | Lộ class, path, SQL, hostname và cấu hình. | Response lỗi chuẩn hóa; chi tiết giữ ở server log có kiểm soát. |
| Dùng raw URL/path | Query/path có thể chứa PII, token hoặc secret. | Route template và field resource ID được duyệt. |
| Tin X-Forwarded-For từ mọi caller | Attacker giả IP và làm sai điều tra/rate limit. | Chỉ tin proxy chain cấu hình rõ. |
| Dùng ID client gửi làm request ID | Log spoofing, trùng ID và correlation giả. | Tạo internal ID; giữ external ID riêng. |
| Log tự do bằng nối chuỗi | Log injection và khó parse. | Structured logging, escaping và length limits. |
| Dùng debug log làm audit | Log có thể bị tắt, sampling hoặc xóa sớm. | Audit event riêng với retention/integrity phù hợp. |
| Sampling mọi security event | Bỏ lỡ dấu hiệu hiếm hoặc hành động đặc quyền. | Chính sách sampling theo loại event và severity. |
| Không cleanup MDC | Request sau có thể mang actor/request ID của request trước. | Cleanup trong `finally` và test thread reuse. |
| Log pipeline lỗi nhưng không alert | Mất dấu vết đúng lúc xảy ra sự cố. | Metric cho dropped event, backlog, agent health và fallback policy. |

## 16. Kiểm thử chất lượng log

Kiểm thử phải xác minh event được tạo đúng, có thể liên kết và không chứa dữ liệu bị cấm. Nên dùng test tự động cho các security-critical event và kiểm tra cấu hình logging trong staging.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Request correlation | Gửi request qua gateway và nhiều service. | Có request/trace/correlation context liên kết đúng; mỗi service nhận diện nguồn phát. |
| Client ID spoofing | Gửi `X-Request-ID` chứa newline/giá trị trùng. | Internal request ID được tạo riêng; input được giới hạn và lưu field riêng nếu cần. |
| Authentication failure | Gửi token hết hạn/sai chữ ký. | Security event có reason code; không log token/header. |
| Authorization denial | Truy cập object/tenant ngoài quyền. | Event ghi actor, action, resource type, decision và policy; không ghi full object. |
| Privileged action | Admin đổi role hoặc revoke API key. | Audit event ghi actor, target, outcome và approval/reference. |
| Secret redaction | Gửi request có bearer token, cookie, API key và password. | Không có raw secret trong app log, collector, trace hoặc error log. |
| PII policy | Gửi email/số điện thoại/địa chỉ trong request. | Chỉ field được duyệt được ghi; masking/pseudonymization đúng policy. |
| Log injection | Gửi CR/LF, tab, delimiter và Unicode control trong filename/user-agent. | Event vẫn là một record hợp lệ; parser không bị giả mạo. |
| Exception safety | Gây database timeout/exception có message chứa thông tin nhạy cảm. | Server log có error class/code/context cần thiết; client không thấy chi tiết nội bộ. |
| Async propagation | Chuyển request thành job/queue message. | Trace/correlation được truyền tường minh; không có token/session trong message. |
| MDC thread reuse | Xử lý hai request liên tiếp trên cùng thread. | Request thứ hai không mang actor/request ID từ request thứ nhất. |
| Sampling/volume | Tạo burst event lặp và event audit quan trọng. | Log volume được kiểm soát; audit event không bị sampling mất; dropped counter tăng nếu suppress. |
| Pipeline outage | Làm collector/log agent không sẵn sàng. | Buffer/failure policy hoạt động; alert phát hiện backlog/dropped event. |
| Access control | User không có quyền truy cập log query/export. | Bị từ chối và thao tác truy cập log được audit. |
| Retention | Đưa event qua mốc retention trong môi trường test. | Dữ liệu được xóa/ẩn danh theo policy; audit cần thiết được giữ đúng hạn. |

Kiểm tra cả nơi lưu cuối cùng, không chỉ mock logger invocation. Có thể tạo test assertion để quét log output tìm các pattern token, cookie, password, private key và dữ liệu test nhạy cảm. Không đưa secret production vào test fixture.

## 17. Checklist log server-side phục vụ điều tra

- [ ] Có phân biệt application log, security event và audit log?
- [ ] Event có timestamp UTC, service/version/environment và schema ổn định?
- [ ] Có request ID, trace ID hoặc correlation ID để nối các service?
- [ ] Request ID do server/trusted gateway tạo; external ID được giữ riêng?
- [ ] Log có actor, tenant, action, resource type, decision và outcome ở mức phù hợp?
- [ ] Route template được dùng thay raw path/query có thể chứa dữ liệu nhạy cảm?
- [ ] Authentication/authorization failure có reason code chuẩn hóa?
- [ ] Không ghi password, token, cookie, API key, private key, secret hoặc full payload?
- [ ] PII/payment data được loại bỏ, mask hoặc pseudonymize theo policy?
- [ ] Structured logger escape dữ liệu không tin cậy và giới hạn độ dài?
- [ ] Exception detail chỉ ở server log có quyền hạn; response client không lộ internals?
- [ ] MDC/trace context được cleanup/propagate đúng qua async và queue?
- [ ] Log pipeline có TLS/authentication, encryption, RBAC và audit truy cập?
- [ ] Audit event quan trọng có integrity/retention phù hợp và không bị sampling bỏ?
- [ ] Có alert cho auth failure, privilege change, cross-tenant access, abuse và log pipeline outage?
- [ ] Có test secret redaction, log injection, correlation, thread reuse và retention?

Log server-side đủ chi tiết để điều tra không phải là ghi càng nhiều dữ liệu càng tốt. Hãy ghi sự kiện có cấu trúc, liên kết được qua request/trace ID, xác định actor/action/resource/decision/outcome và giữ đủ ngữ cảnh lỗi ở phía server. Đồng thời phải loại bỏ credential và payload nhạy cảm, chống log injection, bảo vệ integrity/access/retention và kiểm thử cả đường đi tới nơi lưu cuối cùng. Khi thiết kế logging theo mục đích như vậy, đội vận hành có thể tái dựng sự cố mà không biến hệ thống log thành một nguồn rò rỉ dữ liệu mới.
