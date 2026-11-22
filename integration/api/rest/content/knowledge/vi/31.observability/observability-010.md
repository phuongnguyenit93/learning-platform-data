# Audit log khác access log và log chẩn đoán như thế nào

Một yêu cầu REST API có thể tạo ra nhiều loại log, nhưng mỗi loại trả lời một câu hỏi khác nhau. Khi quản trị viên đổi quyền thành viên của một tenant, **access log** cho biết có một HTTP request đi qua hệ thống, **audit log** ghi nhận ai đã thực hiện hành động nghiệp vụ nào và kết quả được xác nhận, còn **log chẩn đoán** giải thích vì sao xử lý thành công, chậm hoặc thất bại. Nếu dùng lẫn ba loại, hệ thống có thể vận hành bình thường khi không có sự cố nhưng lại không đủ bằng chứng để điều tra thay đổi quyền hoặc giải thích lỗi sản xuất.

Trong chương **Quan sát hệ thống** của module **INTEGRATION_API_REST**, bài học tập trung vào việc thiết kế log cho REST API theo resource, HTTP method, mã trạng thái và hợp đồng dữ liệu, đồng thời thực hành với Java/Spring. Mục tiêu là vừa phục vụ theo dõi hiệu năng và điều tra lỗi, vừa bảo vệ dữ liệu nhạy cảm và xây dựng lịch sử hoạt động nghiệp vụ có thể kiểm chứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt access log, audit log và log chẩn đoán theo **mục đích, thời điểm phát sinh, độ tin cậy, nội dung và thời gian lưu giữ**.
2. Trình bày vì sao một HTTP `200`, `204` hoặc `500` không tự chứng minh rằng một thay đổi nghiệp vụ đã hoặc chưa được commit.
3. Thiết kế audit event có chủ thể, tenant, hành động, đối tượng, quyết định quyền, kết quả, thời gian và mã tương quan.
4. Ghi audit sự kiện nghiệp vụ với ranh giới transaction rõ ràng; xử lý rollback, retry, idempotency, luồng bất đồng bộ và sự cố giao log.
5. Thực hiện access log và audit log ở ứng dụng Spring, dùng request ID/trace ID để liên kết với log chẩn đoán.
6. Viết ca kiểm thử chứng minh các log phản ánh đúng sự kiện, không làm lộ token/PII và không bị sai lệch do những lần retry.

## 2. Ba loại log, ba mục tiêu khác nhau

Hãy xem một yêu cầu đổi vai trò:

```http
PATCH /api/tenants/tenant-a/members/member-42/role HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: role-change-2026-11-18-01
X-Request-ID: 7f72d9b0-46c5-4a10-9997-4f2f27de764a

{"role":"EDITOR"}
```

Trong hệ thống mẫu, người gọi có quyền quản trị tenant, vai trò của `member-42` đổi từ `VIEWER` thành `EDITOR` và transaction commit thành công.

**Access log** trả lời: *Request nào đã đi vào API, đi theo route nào, trả status bao nhiêu, mất bao lâu?* Nó phục vụ lưu lượng, latency, lỗi HTTP, kiểm soát vận hành và điều tra truy cập.

**Audit log** trả lời: *Chủ thể nào đã làm gì lên đối tượng nghiệp vụ nào, thuộc tenant nào, có được cho phép không, và kết quả đã được xác nhận đến đâu?* Nó phục vụ truy trách nhiệm, điều tra hành vi, rà soát quyền và yêu cầu kiểm toán được xác định cho hệ thống.

**Log chẩn đoán** (application/diagnostic log) trả lời: *Code và các phụ thuộc đã đi qua những bước nào, tại sao operation chậm hoặc lỗi?* Nó phục vụ debugging, khắc phục sự cố, tối ưu và quan sát hoạt động nội bộ.

```mermaid
flowchart TD
    C["HTTP client"] --> G["API Gateway / Servlet filter"]
    G -->|"request kết thúc"| L1["Access log"]
    G --> A["Spring Controller + Service"]
    A -->|"business action + transaction"| L2["Audit event"]
    A -->|"exception, retry, timeout, state"| L3["Diagnostic log"]
    A --> DB["Database"]
    A --> EX["Dịch vụ ngoài"]
    L1 -.-> COR["request_id / trace_id / operation_id"]
    L2 -.-> COR
    L3 -.-> COR
```

Ba loại có thể nằm trong các hệ thống lưu trữ khác nhau. **Correlation ID liên kết chúng**; correlation không biến log vận hành thành bằng chứng audit đáng tin cậy.

### 2.1. Bảng so sánh

| Tiêu chí | Access log | Audit log | Log chẩn đoán |
|---|---|---|---|
| Đơn vị ghi | HTTP request/response hoặc network hop | Sự kiện bảo mật/nghiệp vụ và kết quả | Bước xử lý, trạng thái nội bộ, lỗi |
| Câu hỏi chính | Request nào, route nào, status/latency nào? | Ai, làm gì, trên đối tượng nào, vì sao được/từ chối, kết quả ra sao? | Vì sao lỗi/chậm, code hoặc dependency nào liên quan? |
| Nguồn phát sinh | Gateway, ingress, servlet filter, HTTP server | Thành phần ra quyết định quyền hoặc nghiệp vụ | Controller, service, client SDK, ORM, worker |
| Thường chứa | Method, route template, HTTP status, duration, bytes, trace ID | Actor, tenant, action, target, before/after đã kiểm soát, decision, outcome, operation ID | Exception class, stack trace an toàn, upstream code, retry, timing |
| Hành vi khi retry | Mỗi HTTP attempt có thể tạo một dòng | Có thể nhiều attempt nhưng một thay đổi đã commit; cần phân biệt | Có thể nhiều dòng cho từng attempt |
| Tính đầy đủ | Tùy sampling/chính sách hạ tầng | Phải đáp ứng độ bao phủ sự kiện audit đã cam kết | Tùy mức `INFO/WARN/ERROR/DEBUG` và sampling |
| Tính toàn vẹn | Thường phụ thuộc pipeline log vận hành | Thường cần quyền ghi hạn chế, chống sửa/xóa và khả năng kiểm chứng | Tối ưu để tìm lỗi; có thể luân chuyển/xóa theo chính sách |
| Retention | Theo nhu cầu vận hành, bảo mật và chính sách áp dụng | Theo yêu cầu nghiệp vụ/kiểm toán/quy định áp dụng | Theo nhu cầu debugging, chi phí và dữ liệu nhạy cảm |
| Dùng để chứng minh business commit? | Không | Có thể, nếu sinh đúng điểm commit và bảo vệ chuỗi ghi | Không |

Thời gian lưu không có một con số áp dụng cho mọi sản phẩm. Doanh nghiệp cần quy định riêng theo mục đích xử lý, rủi ro, hợp đồng và pháp luật liên quan; không nên mặc định mọi log đều giữ vĩnh viễn.

### 2.2. Ví dụ ba bản ghi cho cùng operation

Các dòng JSON dưới đây chỉ để minh họa định dạng cấu trúc và đã lược thông tin nhạy cảm.

**Access log:**

```json
{
  "timestamp": "2026-11-18T10:00:00.184Z",
  "kind": "http_access",
  "service": "membership-api",
  "http_method": "PATCH",
  "http_route": "/api/tenants/{tenantId}/members/{memberId}/role",
  "http_status": 204,
  "duration_ms": 46,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "7f72d9b0-46c5-4a10-9997-4f2f27de764a"
}
```

**Audit event sau khi nghiệp vụ đã commit:**

```json
{
  "schema_version": 1,
  "event_id": "4d84d7b1-36e2-47de-9f1d-6f93ce1b5bf6",
  "kind": "security_audit",
  "occurred_at": "2026-11-18T10:00:00.170Z",
  "actor": {"type": "USER", "subject": "admin-17"},
  "tenant_id": "tenant-a",
  "action": "MEMBERSHIP_ROLE_CHANGED",
  "target": {"type": "TENANT_MEMBER", "id": "member-42"},
  "decision": "ALLOW",
  "outcome": "SUCCEEDED",
  "change": {"role": {"from": "VIEWER", "to": "EDITOR"}},
  "operation_id": "role-change-2026-11-18-01",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "7f72d9b0-46c5-4a10-9997-4f2f27de764a"
}
```

**Log chẩn đoán:**

```json
{
  "timestamp": "2026-11-18T10:00:00.155Z",
  "level": "INFO",
  "service": "membership-api",
  "logger": "RoleChangeService",
  "message": "Role change validation completed",
  "duration_ms": 8,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Access log nói HTTP thành công; audit event nói **đã đổi role từ VIEWER sang EDITOR**; diagnostic log ghi một bước xử lý để tìm nguyên nhân khi có sự cố. Không nên đẩy nguyên request body, access token hoặc dữ liệu cá nhân vào ba bản ghi để đạt được mục tiêu này.

## 3. Vì sao HTTP status và application log không thay thế audit log?

Một request `PATCH /members/{id}/role` có thể gặp các tình huống:

| Tình huống | HTTP response nhìn thấy | Sự kiện audit phù hợp |
|---|---|---|
| Đổi role, DB commit, response gửi thành công | `204 No Content` | `ROLE_CHANGED / SUCCEEDED` |
| Thiếu quyền, bị chặn trước khi cập nhật | `403 Forbidden` | `ROLE_CHANGE_DENIED / DENIED` nếu thuộc phạm vi audit |
| Đã commit nhưng kết nối rớt trước response | Caller thấy timeout hoặc lỗi transport | Vẫn ghi nhận `ROLE_CHANGED / SUCCEEDED`, vì commit đã xảy ra |
| Validator thành công nhưng transaction rollback | Thường `4xx/5xx` | Không ghi sự kiện **đã thay đổi thành công**; có thể ghi sự kiện attempt thất bại riêng |
| Request hợp lệ nhưng giá trị role không thay đổi | `200/204` tùy hợp đồng | `NO_CHANGE` hoặc không phát sinh event thay đổi, theo chính sách đã định |
| Tạo job async và trả `202 Accepted` | `202 Accepted` | `REQUEST_ACCEPTED`; event `SUCCEEDED` chỉ khi worker hoàn thành |
| Retry sau timeout của request đã commit | Có thể thêm `200/204` hoặc replay kết quả | Không nhân bản sự kiện business change; từng HTTP attempt vẫn có access log |

HTTP status mô tả **phản hồi của request**, không là bản sao trạng thái transaction hay hệ thống bên ngoài. Kết nối rớt có thể khiến client không bao giờ nhận `204` dù commit đã thành công. Ngược lại, response `202` chỉ xác nhận tiếp nhận xử lý, không chứng minh kết quả cuối.

Log chẩn đoán kiểu:

```java
log.info("Role changed for member {}", memberId);
repository.save(member);
```

có thể sai lệch nếu transaction rollback sau câu log, hoặc lệnh `save` chưa flush/commit. Nếu viết audit thành công như một thông báo `INFO` trước commit, điều tra viên có thể kết luận rằng role đã đổi dù database chưa từng lưu thay đổi đó.

**Phân biệt ba khái niệm:** hành động **được yêu cầu** (attempt), **được cho phép** (decision), và **đã hoàn tất** (outcome). Một event audit chất lượng phải thể hiện rõ nó đang ghi nhận khái niệm nào.

## 4. Thiết kế audit event có ngữ nghĩa rõ ràng

Audit event nên là **sự kiện có cấu trúc** với schema/version, thay vì một chuỗi văn bản tùy hứng như `"admin updated user"`. Một mẫu trường dữ liệu:

| Trường | Ý nghĩa | Lưu ý |
|---|---|---|
| `event_id` | ID duy nhất cho event audit | Sinh và giữ cố định qua quá trình giao event lại |
| `schema_version` | Phiên bản schema audit | Giúp consumer đọc được dữ liệu qua các lần đổi cấu trúc |
| `occurred_at` | Thời điểm hành động/decision diễn ra | Dùng timestamp UTC có offset rõ ràng |
| `recorded_at` | Thời điểm event được nơi lưu ghi nhận | Hữu ích khi pipeline giao chậm; không thay thế event time |
| `actor.subject` | Định danh chủ thể đã xác thực | Lấy từ security context đã kiểm chứng; không tin header/body do client tự ghi |
| `actor.type` | USER, SERVICE, SYSTEM, API_CLIENT… | Phân biệt hành động người dùng và tác vụ tự động |
| `on_behalf_of` / `impersonator` | Ngữ cảnh ủy quyền/giả danh, nếu có | Không gộp người thực hiện với người được đại diện |
| `tenant_id` | Phạm vi tenant liên quan | Cần có với hành động đa tenant; không tự tin tenant ID ở URL |
| `action` | Động từ nghiệp vụ chuẩn hóa | Ví dụ `MEMBERSHIP_ROLE_CHANGED`, `DATA_EXPORTED` |
| `target.type` và `target.id` | Loại và ID đối tượng chịu tác động | Có thể là nhiều target; không lưu bản sao dữ liệu nhạy cảm |
| `decision` | `ALLOW` hoặc `DENY` khi có kiểm tra quyền | Tách quyết định quyền khỏi kết quả nghiệp vụ |
| `outcome` | `SUCCEEDED`, `FAILED`, `DENIED`, `UNKNOWN`… | Không gộp timeout với thất bại chắc chắn |
| `change` / `reason_code` | Tóm tắt thay đổi/nhóm lý do đã cho phép | Dùng allowlist; không dump nguyên entity |
| `request_id`, `trace_id` | Liên kết request với trace và log khác | Không coi chúng là danh tính người dùng |
| `operation_id` | ID ổn định cho một ý định nghiệp vụ | Dùng để nối các retry và job async |

Những trường này là **mô hình tham khảo**, không phải một tiêu chuẩn bắt buộc về tên field. Cần chọn ngữ nghĩa ổn định, document trong hợp đồng nội bộ và không thay đổi tự do giữa các service.

### 4.1. Actor, subject và tenant phải do server xác thực

Ví dụ request do một người dùng thực hiện:

```http
PATCH /api/tenants/tenant-b/members/member-7/role HTTP/1.1
Authorization: Bearer <signed-token>
X-Actor-Id: super-admin
X-Tenant-Id: tenant-a
Content-Type: application/json

{"role":"ADMIN"}
```

Không được lấy `X-Actor-Id` làm `actor.subject` hoặc chấp nhận `X-Tenant-Id` làm tenant đã được cấp quyền nếu đó là header do client công khai tự đặt. Server phải lấy danh tính từ security context đã xác thực, kiểm tra membership của tenant thực và quyền trên target. Nếu gateway truyền identity nội bộ, phải có ranh giới tin cậy riêng (mTLS/header bị gateway tái ghi và chặn spoofing, xác minh chữ ký/ủy quyền theo kiến trúc).

Đối với service-to-service, ghi cả `client_id/service identity` và `on_behalf_of` nếu hệ thống có delegation đáng tin cậy. Đối với job scheduler, không bịa một "người dùng thực hiện" khi thực tế là `SYSTEM`; có thể tham chiếu `initiated_by` của request gốc bằng ID đã lưu.

### 4.2. Tránh audit quá nhiều hoặc thiếu sự kiện trọng yếu

Không phải mọi `GET` đều phải có business audit event; tùy yêu cầu sản phẩm, truy cập dữ liệu nhạy cảm, export tài liệu hoặc tra cứu tài khoản có thể cần audit **ngay cả khi chỉ đọc**. Ngược lại, các request health check thường chỉ cần access/metrics.

Một catalog sự kiện có thể gồm:

| Nhóm | Audit event nên cân nhắc | Ý nghĩa |
|---|---|---|
| Xác thực và phiên | `LOGIN_SUCCEEDED`, `LOGIN_DENIED`, `SESSION_REVOKED` | Rà soát truy cập và hành vi bất thường |
| Phân quyền | `ROLE_CHANGED`, `MEMBERSHIP_REVOKED`, `PERMISSION_DENIED` | Phát hiện nâng quyền và truy cập trái phép |
| Dữ liệu nhạy cảm | `CUSTOMER_DATA_EXPORTED`, `RESTRICTED_RECORD_VIEWED` | Truy ra ai đã xem/xuất dữ liệu |
| Tác vụ tài chính | `PAYMENT_APPROVED`, `REFUND_REQUESTED`, `REFUND_COMPLETED` | Theo dõi chuỗi thao tác có tác động nghiệp vụ |
| Cấu hình | `API_KEY_ROTATED`, `WEBHOOK_TARGET_CHANGED` | Điều tra thay đổi tích hợp và thông tin truy cập |
| Hệ thống | `AUDIT_EXPORT_FAILED`, `POLICY_UPDATED` | Phát hiện suy giảm khả năng kiểm toán |

Event catalog phải định nghĩa **trạng thái, mức độ quan trọng, dữ liệu tối thiểu và policy lưu trữ**. Tránh ghi cả request body hoặc entity snapshot chỉ vì "có thể cần về sau". Dữ liệu nhạy cảm được sao chép thêm vào audit sẽ tăng diện tích rủi ro bảo mật.

## 5. Access log: quan sát ranh giới HTTP

Access log thường được tạo tại reverse proxy, gateway, ingress hoặc web server. Một request đi qua ba hop có thể có ba access log, mỗi log đo thời gian và status tại hop đó. Nếu đếm số dòng từ nhiều hop như một tập request duy nhất sẽ làm sai các chỉ số.

Các thuộc tính nên có:

- `service` / `instance` / `deployment_environment` để biết thành phần xử lý.
- `http.method`, **route template** như `/orders/{id}`, `http.response.status_code`.
- `duration_ms` hoặc metric duration với đơn vị xác định.
- `request_id`, `trace_id` và các identifier đã được kiểm soát.
- Kích thước request/response khi cần, user agent hoặc nguồn kết nối nếu có cơ sở và đã áp dụng quy tắc bảo vệ dữ liệu.

**Không mặc định log raw URL/query string.** Ví dụ `GET /reset-password?token=...` hoặc `GET /customers?email=...` có thể làm lọt secret/PII vào pipeline. Nếu cần phân tích đường dẫn động, thay ID thật bằng route template, hoặc có bộ lọc/sanitizer theo allowlist. Nên tránh logging `Authorization`, `Cookie`, `Set-Cookie` và credential ở bất kỳ tầng nào.

### 5.1. Access log với Spring Web MVC

Ví dụ minh họa sử dụng servlet filter. Mã bỏ imports và cấu hình log encoder để tập trung vào cách chọn trường; khi đưa vào dự án, thêm imports từ Servlet API, Spring MVC và SLF4J tương ứng với phiên bản Spring Boot.

```java
@Component
public class ApiAccessLogFilter extends OncePerRequestFilter {
    private static final Logger ACCESS =
            LoggerFactory.getLogger("http.access");

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS
                    .toMillis(System.nanoTime() - start);

            Object matchedRoute = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

            String route = matchedRoute instanceof String
                    ? (String) matchedRoute
                    : "(unmatched)";

            // Trace ID lấy từ ngữ cảnh tracing do server quản lý.
            String traceId = MDC.get("traceId");

            ACCESS.info(
                "method={} route={} status={} duration_ms={} trace_id={}",
                request.getMethod(),
                route,
                response.getStatus(),
                elapsedMs,
                traceId == null ? "-" : traceId);
        }
    }
}
```

Code này minh họa một **request đồng bộ**. Với Spring MVC xử lý bất đồng bộ (`Callable`, `DeferredResult`, async dispatch), block `finally` có thể chạy khi async request chưa hoàn tất và log status/latency chưa phải kết quả cuối. Trong production cần dùng cơ chế đo hoàn tất async phù hợp, hỗ trợ Spring Observation/Micrometer hoặc cấu hình access log của server/gateway. Tương tự, gắn filter đúng thứ tự với Spring Security để không bỏ mất `401/403` khi request bị chặn trước controller.

Trong ví dụ, `MDC.get("traceId")` chỉ có giá trị nếu tracing đã đưa trace ID vào MDC đúng thời điểm; không có trace context thì phải để trống hoặc ký hiệu rõ, không bịa ID. Muốn log JSON chuẩn hóa, cấu hình structured log encoder hoặc tracing integration thay vì nối thủ công các giá trị do client nhập vào.

### 5.2. Access log không phải authorization log

`403 Forbidden` trong access log cho biết server từ chối một HTTP request. Nó không nhất thiết cho biết:

- Chính sách nào đã từ chối: thiếu scope, tenant khác, thiếu ACL hay chức năng không được cấp.
- Request cố gắng thay đổi đối tượng nào; ID trong URL có thể đã bị ẩn/anonymize.
- User nào đứng sau token hoặc proxy; trường `client_ip` không đủ định danh.
- Có thực sự ngăn được mọi side effect hay không.

Nếu những dữ kiện này cần phục vụ điều tra, phát **audit event phân quyền** ở điểm có ngữ cảnh đáng tin cậy, với `reason_code` an toàn và chính sách tránh lộ đối tượng ngoài quyền.

## 6. Diagnostic log: phục vụ tìm lỗi, không tạo bản ghi nghiệp vụ giả

Log chẩn đoán thường xuất hiện trong controller, service, repository, HTTP client và worker. Các mức phổ biến `DEBUG`, `INFO`, `WARN`, `ERROR` dùng để điều chỉnh độ chi tiết và mức độ nghiêm trọng.

Ví dụ lỗi provider timeout:

```json
{
  "timestamp": "2026-11-18T10:03:12.192Z",
  "level": "WARN",
  "service": "billing-api",
  "event": "payment_provider_timeout",
  "upstream": "payment-provider",
  "timeout_ms": 800,
  "attempt": 1,
  "retryable": false,
  "trace_id": "9af2e76bff7b40dea2bb21638ad7f2e6"
}
```

Thông tin cần tìm là downstream nào bị chậm, timeout bao nhiêu, retry được hay không, kết nối với trace nào. Không cần log nguyên payload chứa thông tin thanh toán hoặc token. Stack trace nên đi kèm lỗi có ích và được xử lý để không lộ secret ở exception message; không log lặp cả stack trace ở từng tầng chỉ vì cùng một exception được truyền qua.

Ví dụ sử dụng SLF4J:

```java
try {
    PaymentResult result = provider.charge(command);
    return result;
} catch (ProviderTimeoutException ex) {
    log.warn(
        "Payment provider timeout upstream={} timeout_ms={} operation_id={}",
        "payment-provider",
        configuredTimeoutMs,
        safeOperationId,
        ex);
    throw ex;
}
```

`safeOperationId` là ID nội bộ được phép log. Đoạn này cố ý không đưa số thẻ, `Authorization`, body của provider hoặc secret vào message. Với lượng request lớn, cân nhắc tránh stack trace ở mọi retry: metric/counter và trace có thể phù hợp hơn, còn error cuối cùng mới có chi tiết chẩn đoán.

**Mức `INFO` không biến một dòng thành audit:** log chẩn đoán có thể bị giảm mức, lọc, sampling, đổi định dạng hoặc xóa theo rotation. Nếu workflow đòi lịch sử sự kiện đầy đủ, phải có pipeline audit riêng với tiêu chuẩn bao phủ và giao nhận đã xác định.

## 7. Ghi audit đúng ranh giới transaction database

Đây là khác biệt quan trọng nhất khi hiện thực: audit event loại `SUCCEEDED` của một thay đổi trong DB phải liên kết chặt với **commit thực sự**, không gắn tùy tiện với một dòng log `INFO` xuất hiện trước commit.

### 7.1. Anti-pattern: log thành công trước commit

```java
@Transactional
public void changeRole(UUID tenantId, UUID memberId, Role newRole) {
    Member member = members.findByIdAndTenantId(memberId, tenantId)
            .orElseThrow();
    member.setRole(newRole);

    log.info("AUDIT role changed member={} newRole={}",
             memberId, newRole);
    // Nếu commit sau method này lỗi, dòng log vẫn tồn tại.
}
```

Nếu DB bị deadlock, vi phạm constraint, không kết nối được lúc commit hoặc transaction ngoài đánh dấu rollback-only, dòng "role changed" đã phát đi vẫn tồn tại. Chỉ đợi tới `repository.save()` cũng chưa đủ vì `save` không đồng nghĩa `COMMIT`.

### 7.2. Cùng transaction cho dữ liệu nghiệp vụ và audit row

Ví dụ thiết kế bảng PostgreSQL:

```sql
CREATE TABLE audit_events (
    event_id        uuid PRIMARY KEY,
    schema_version  smallint NOT NULL,
    occurred_at     timestamptz NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    tenant_id       text,
    actor_subject   text NOT NULL,
    actor_type      text NOT NULL,
    action          text NOT NULL,
    target_type     text NOT NULL,
    target_id       text,
    decision        text NOT NULL,
    outcome         text NOT NULL,
    operation_id    text,
    request_id      text,
    trace_id        text,
    change_summary  jsonb,
    CONSTRAINT ck_audit_decision
        CHECK (decision IN ('ALLOW', 'DENY', 'NOT_APPLICABLE')),
    CONSTRAINT ck_audit_outcome
        CHECK (outcome IN ('SUCCEEDED', 'DENIED',
                          'FAILED', 'UNKNOWN', 'NO_CHANGE'))
);

CREATE INDEX idx_audit_tenant_time
    ON audit_events (tenant_id, occurred_at DESC);

CREATE INDEX idx_audit_operation
    ON audit_events (operation_id);
```

Các chỉ mục tùy workload và chính sách dữ liệu. Nếu `change_summary` dùng JSONB, chỉ cho phép các cặp trước/sau ít nhạy cảm như `VIEWER → EDITOR`; không lưu dữ liệu tài chính, mật khẩu, token hoặc nguyên entity.

Spring service minh họa:

```java
@Service
public class MemberRoleService {
    private final MemberRepository members;
    private final TenantAuthorization authorization;
    private final AuditEventRepository audits;

    public MemberRoleService(MemberRepository members,
                             TenantAuthorization authorization,
                             AuditEventRepository audits) {
        this.members = members;
        this.authorization = authorization;
        this.audits = audits;
    }

    @Transactional
    public void changeRole(RoleChangeCommand command,
                           AuthenticatedActor actor) {
        authorization.requireTenantAdmin(
                actor.subject(), command.tenantId());

        Member member = members.findByIdAndTenantId(
                command.memberId(), command.tenantId())
            .orElseThrow(() -> new ResourceNotFoundException());

        Role before = member.getRole();
        if (before == command.newRole()) {
            return; // NO_CHANGE theo hợp đồng: không tạo ROLE_CHANGED.
        }

        member.setRole(command.newRole());

        // audits.save() dùng CÙNG transaction manager/DB
        // với members; nếu một trong hai write lỗi, cùng rollback.
        audits.save(AuditEvent.roleChanged(
                UUID.randomUUID(),
                actor.subject(),
                command.tenantId(),
                member.getId(),
                before,
                command.newRole(),
                command.operationId()));
    }
}
```

`RoleChangeCommand`, `AuthenticatedActor`, `AuditEvent.roleChanged(...)`, repository và exception là các kiểu miền minh họa phải được hiện thực trong ứng dụng. Actor phải lấy từ security context đã xác thực. Method cần chạy qua Spring transaction proxy (chú ý tự gọi `this.changeRole(...)` có thể bỏ qua `@Transactional`).

Ở đây **cùng database và cùng transaction** bảo đảm nếu thay đổi role được commit thì audit row tương ứng cũng được commit, và nếu rollback thì cả hai cùng rollback. Nó không bảo đảm audit đã được chuyển sang kho lưu trữ bên ngoài, cũng không ngăn admin DB sửa trực tiếp bảng nếu chưa có lớp bảo vệ.

Trường hợp role thay đổi đồng thời nên dùng optimistic locking (`@Version`) hoặc khóa/cập nhật có điều kiện, đồng thời bảo đảm event `before → after` phản ánh đúng dữ liệu đã commit. Nếu không xử lý concurrency, hai transaction có thể cùng đọc role cũ, ghi sai chuỗi lịch sử hoặc ghi đè thay đổi nhau.

### 7.3. Audit các yêu cầu bị từ chối và các lần thử thất bại

Một `ACCESS_DENIED` xảy ra trước khi thay đổi nghiệp vụ, thường chưa có transaction ghi DB. Có thể ghi event `DENIED` bằng một sink bảo mật riêng hoặc transaction tách biệt, miễn là đó là **sự kiện bị từ chối**, không được gắn `SUCCEEDED`.

Nếu ghi event từ chối bên trong transaction sẽ rollback khi exception bảo mật được ném ra, event cũng biến mất; muốn giữ lại cần ranh giới giao dịch/sink riêng được kiểm soát, chẳng hạn một service audit độc lập sau khi đã quyết định `DENY`. Tránh lạm dụng `REQUIRES_NEW` bên trong giao dịch lớn mà không cân nhắc lock, lỗi và tính nguyên tử mong muốn.

Với thao tác thất bại do lỗi kỹ thuật:

- Audit **attempt** nếu policy cần: `ROLE_CHANGE_ATTEMPTED / FAILED` với `reason_code=DB_UNAVAILABLE`.
- Không phát `ROLE_CHANGED / SUCCEEDED` nếu transaction chưa commit.
- Nếu outcome chưa xác định (ví dụ gateway timeout sau khi server gửi yêu cầu thanh toán ngoài), dùng `UNKNOWN` và cập nhật/ghi sự kiện giải quyết khi đã xác minh; không tự quy timeout thành giao dịch thất bại.

**Không nhất thiết mọi denial phải lưu trọn ID resource được đoán.** Khi attacker thử hàng triệu ID, log audit cần chống bão, kiểm soát retention và không tiết lộ chi tiết nội bộ trong output cho client. Chính sách bảo toàn bằng chứng phải phân loại denial quan trọng, khả năng rate limit và tác động chi phí.

## 8. Khi audit cần lưu bên ngoài: Transactional outbox

Ghi cùng transaction DB chỉ bảo đảm tính nguyên tử **nội bộ**. Nếu yêu cầu đưa audit tới SIEM, hệ thống lưu giữ chuyên biệt, WORM hoặc dịch vụ phân tích, sẽ xuất hiện vấn đề "dual write": ghi DB thành công nhưng gửi audit lên hệ thống ngoài thất bại.

Một cách phổ biến là transactional outbox:

```mermaid
sequenceDiagram
    autonumber
    participant API as Spring REST API
    participant DB as Database
    participant W as Audit exporter
    participant S as Audit store / SIEM
    API->>DB: BEGIN
    API->>DB: UPDATE member role
    API->>DB: INSERT audit_event + audit_outbox
    API->>DB: COMMIT
    DB-->>API: Committed
    API-->>API: Trả HTTP 204
    W->>DB: Claim audit_outbox (transaction ngắn)
    DB-->>W: Event data
    W->>S: Gửi event_id cố định
    S-->>W: ACK
    W->>DB: Mark delivered
```

Với cách này, **thay đổi nghiệp vụ, audit row và outbox intent cùng commit**. Worker xuất audit có thể retry khi sink lỗi, giới hạn backoff, giám sát backlog và đánh dấu đã giao sau khi nhận xác nhận. Vì worker có thể crash sau khi sink đã nhận nhưng trước khi đánh dấu `delivered`, event có thể được gửi **hơn một lần**. Sink phải deduplicate bằng `event_id` hoặc xử lý idempotent; không khẳng định outbox mặc định cho "exactly once".

Nếu audit store bên ngoài bất khả dụng nhiều giờ, transaction nghiệp vụ có thể vẫn thành công theo policy vì outbox bền vững và có giám sát backlog. Nhưng với tác vụ cực kỳ nhạy cảm yêu cầu phải ghi audit bền vững trước khi chấp nhận, hệ thống có thể chọn **fail closed** khi ngay cả thao tác ghi audit tại chỗ không thành công. Đây là quyết định theo phân loại rủi ro và yêu cầu vận hành; không được âm thầm nuốt lỗi audit nhưng vẫn tuyên bố kiểm toán đầy đủ.

### 8.1. Giao event đúng ở các thời điểm khó

| Thời điểm sự cố | Thứ còn lưu | Cách diễn giải/phục hồi |
|---|---|---|
| Trước `COMMIT` | Cả business change/audit/outbox rollback | Không có audit `SUCCEEDED`; có thể giữ audit attempt riêng |
| Sau `COMMIT`, trước HTTP response | Business + audit + outbox đã có | Event thành công hợp lệ dù client timeout |
| Sau `COMMIT`, trước worker gửi | Outbox pending | Worker khác gửi sau |
| Sau sink nhận event, trước worker ACK | Sink đã có event, outbox chưa hoàn thành | Retry với cùng `event_id`; sink deduplicate |
| Sink audit không sẵn sàng | Backlog outbox tăng | Cảnh báo theo tuổi backlog, retry có kiểm soát |
| Client gửi lại cùng idempotency key | Có thêm HTTP attempt | Không tạo thêm business change/event `SUCCEEDED` nếu kết quả cũ được replay |

Nếu nghiệp vụ liên quan nhiều hệ thống, **event "request accepted" khác event "external action completed"**. Ví dụ `POST /exports` trả `202` khi tạo job; khi worker xuất file xong mới phát `DATA_EXPORT_COMPLETED`, còn request từ chối phát `DATA_EXPORT_DENIED` nếu thuộc chính sách audit.

## 9. Liên kết access log, audit log và diagnostic log

Trong môi trường microservice, mỗi service có log riêng. Có thể dùng:

- **Trace ID:** liên kết các span của cùng luồng xử lý phân tán; do tracer điều phối, không chứa dữ liệu bí mật.
- **Span ID:** xác định bước/hop hiện tại trong trace.
- **Request ID:** nhận diện một HTTP request/hop theo định nghĩa gateway hoặc service; nhiều request do retry thường có request ID khác nhau.
- **Operation ID:** nhận diện **một ý định nghiệp vụ** xuyên nhiều request, retry và job; có thể xuất phát từ idempotency key sau khi server đã ràng buộc theo tenant/payload hoặc từ một ID nội bộ ổn định.
- **Event ID:** định danh **bản ghi audit cụ thể** để xử lý dedup và kiểm chứng giao nhận.

```text
Operation O-17: đổi quyền cho member-42
  ├─ Request R-1: PATCH /role  → server COMMIT, response bị mất
  │    ├─ Access log: R-1, status tại server=204
  │    ├─ Audit: event E-9, ROLE_CHANGED / SUCCEEDED
  │    └─ Diagnostic: commit completed, trace T-1
  └─ Request R-2: retry cùng operation key
       ├─ Access log: R-2, status=204
       ├─ Audit: không tạo ROLE_CHANGED thứ hai
       └─ Diagnostic: idempotency replay, trace T-2
```

Không ép `request_id == operation_id` hoặc giả định một trace là một nghiệp vụ duy nhất: queue, callback, background worker và retry có thể tạo trace mới. Nên lưu liên kết `parent_operation_id` hoặc idempotency/causation key phù hợp trong payload nội bộ.

### 9.1. Trace propagation

Các service có thể truyền trace context qua các header theo chuẩn W3C như `traceparent` và `tracestate`. OpenTelemetry/Micrometer Tracing có thể giúp tạo span và bổ sung trace/span ID cho log, tùy cấu hình và phiên bản thư viện.

Không cho phép giá trị do client gửi trong `X-Request-ID` trở thành một chuỗi tùy ý chứa CR/LF hay dữ liệu quá dài trong log. Validate/normalize ở ingress, giới hạn kích thước và có quy tắc cấp lại ID. Trace context cũng đi qua ranh giới tin cậy; không dùng trace ID làm bằng chứng xác thực hay quyền truy cập.

### 9.2. Tránh metric cardinality nổ

Nếu muốn tạo dashboard:

```text
http_server_requests_total{
  service="membership-api",
  route="/api/tenants/{tenantId}/members/{memberId}/role",
  method="PATCH",
  status="204"
}
```

Các nhãn `service`, `route template`, `method` và nhóm `status` có số lượng hữu hạn hơn `memberId`, `requestId`, `traceId` hoặc `operationId`. Không đưa ID duy nhất vào metric label; để chúng trong trace/log được kiểm soát. Audit log cũng cần chỉ mục phù hợp để tra cứu, tránh dùng pipeline metrics cardinality cao thay thế audit database.

Số request `5xx` tăng, p95 latency tăng hoặc outbox backlog tăng là **tín hiệu giám sát**, không phải bằng chứng rằng một tài nguyên đã bị truy cập trái quyền. Khi điều tra, dùng metric khoanh vùng và tra audit event theo thời gian, actor, tenant, target, operation ID.

## 10. Toàn vẹn, bảo mật và vòng đời log

Audit log thường liên quan quyền truy cập và hành vi nhạy cảm; cần thiết kế bảo vệ nghiêm túc.

### 10.1. Phân quyền truy cập kho log

- Ứng dụng ghi audit bằng tài khoản có quyền **INSERT tối thiểu**, hạn chế UPDATE/DELETE trên bản ghi đã được ghi.
- Nhân sự vận hành không mặc nhiên được đọc toàn bộ audit của mọi tenant; áp dụng quyền truy vấn riêng và ghi nhận các lần export/đọc audit nhạy cảm nếu policy yêu cầu.
- Tách quyền vận hành ứng dụng khỏi quyền quản lý hệ thống lưu giữ audit khi có thể. Người bị điều tra không nên có toàn quyền sửa/xóa dấu vết của chính họ.
- Sao lưu, kiểm thử khôi phục, mã hóa khi truyền/lưu và quản lý khóa phù hợp với phân loại dữ liệu.

Chỉ đặt bảng ở chế độ append-only **chưa bảo đảm không thể sửa**: DB administrator hoặc tiến trình có đặc quyền vẫn có thể thay đổi/tái tạo dữ liệu. Nếu cần bằng chứng chống sửa đổi, dùng cơ chế **tamper-evident** như hash chaining/chữ ký số, định kỳ neo hash/checkpoint vào nơi độc lập, hoặc lưu trữ immutable/WORM có chính sách giữ dữ liệu. Một chuỗi hash chỉ đặt trong cùng database mà người quản trị toàn quyền có thể viết lại từ đầu thì khả năng chống giả mạo rất hạn chế.

### 10.2. Không làm lộ bí mật trong log

Không đưa vào log:

- `Authorization: Bearer ...`, `Cookie`, `Set-Cookie`, API key, refresh token, private key, password hoặc OTP.
- Toàn bộ request/response body chứa thông tin cá nhân, địa chỉ, tài chính hoặc tài liệu nhạy cảm nếu không có nhu cầu được xác định và xử lý bảo mật phù hợp.
- Full SQL bind parameter nhạy cảm, raw header do client điều khiển, stack trace chứa token, hoặc exception message với credential.
- Dữ liệu trước/sau của các field không cần thiết cho audit.

Thay bằng action và **danh sách field được cho phép** (ví dụ `role: VIEWER → EDITOR`); với dữ liệu nhạy cảm như số tài khoản, lưu sự kiện "billing account changed" kèm reference nội bộ và phiên bản, không lưu giá trị gốc. Hạn chế người có quyền đọc log có thể ghép dữ liệu từ nhiều nguồn để suy ra thông tin cá nhân.

### 10.3. Retention, xóa dữ liệu và khả năng kiểm chứng

Access/diagnostic log có thể hết hạn sớm hoặc thay đổi mức chi tiết theo nhu cầu vận hành. Audit thường có yêu cầu lưu lâu hơn, nhưng không mặc định vô hạn. Khi có yêu cầu sửa/xóa dữ liệu cá nhân, phải cân đối với cơ sở pháp lý lưu audit và áp dụng chính sách dữ liệu được phê duyệt; có thể cần pseudonymization, hạn chế truy cập hoặc retention khác nhau theo loại event.

Dùng timestamp UTC/ISO 8601, đồng bộ đồng hồ, ghi nhận `occurred_at` và `recorded_at` để phát hiện trễ. Tránh giả định mọi event sẽ đến đúng thứ tự từ nhiều service/region. Nếu tính đúng thứ tự có ý nghĩa nghiệp vụ, thêm version hoặc sequence cho resource; timestamp đơn lẻ không đủ chứng minh trình tự khi các node lệch giờ.

### 10.4. Khi pipeline log hỏng

Một hệ thống phải xác định chính sách rõ ràng:

| Sự cố | Hành vi cần thiết kế |
|---|---|
| Log chẩn đoán không xuất ra collector | Ứng dụng vẫn có thể tiếp tục; cảnh báo giảm khả năng debug, bảo đảm không nghẽn vì log sync |
| Access log không được thu thập | Giảm khả năng điều tra HTTP; theo dõi sức khỏe agent, buffer/drop policy và metric |
| Ghi audit row cùng transaction thất bại | Với sự kiện bắt buộc, transaction nghiệp vụ rollback/fail closed |
| Audit outbox đầy hoặc không giao được | Báo lỗi/cảnh báo, giới hạn backlog; policy quyết định có tiếp tục nhận nghiệp vụ hay không |
| Event giao trùng | Dedup bằng `event_id`; không biến thành hai thay đổi đã xảy ra |
| Audit store bị chỉnh sửa | Cần cảnh báo integrity, đối chiếu checkpoint, điều tra quyền truy cập |

Không nên để một pipeline `INFO` theo best-effort là **nguồn duy nhất** cho các audit event mà tổ chức khẳng định phải đầy đủ. Ngược lại, không nên buộc mọi debug log đi qua một đường lưu giữ đồng bộ chặt chẽ vì điều đó có thể làm tăng latency đáng kể.

## 11. Kiểm thử access log, audit log và diagnostic log

Kiểm thử log nên bao gồm **nội dung, thời điểm, tính bền vững, quyền và khả năng phục hồi**, thay vì chỉ kiểm tra `log.info()` đã được gọi.

### 11.1. Ma trận kiểm thử HTTP và nghiệp vụ

| Case | Access log mong đợi | Audit log mong đợi | Diagnostic log mong đợi |
|---|---|---|---|
| `PATCH role` hợp lệ, commit thành công | Một dòng cho request, status `204` | `ROLE_CHANGED / SUCCEEDED` với actor, tenant, target, old/new role | Không cần error; có thể có trace/timing |
| Token thiếu, bị chặn | Một dòng `401` | `AUTHENTICATION_DENIED` nếu catalog yêu cầu | Không log token; chỉ security signal an toàn |
| Token hợp lệ, thiếu quyền tenant | Một dòng `403` hoặc `404` theo hợp đồng | `ROLE_CHANGE_DENIED / DENIED` nếu thuộc phạm vi | Không ghi stack trace lỗi nghiệp vụ mỗi request |
| DB rollback khi cập nhật | Một dòng `5xx` hoặc lỗi phù hợp | Không có `ROLE_CHANGED / SUCCEEDED`; có thể có `FAILED` attempt | Lỗi DB an toàn, có trace |
| Request đã commit rồi client timeout | Gateway có thể thấy lỗi transport; server access có status đã ghi | Một event thành công bền vững | Có thể log lỗi gửi response |
| Retry với cùng operation key | Hai access records cho hai HTTP attempts | Một business change; không nhân đôi event `SUCCEEDED` | Diagnostic có thể ghi replay |
| `POST /exports` trả `202`, job chưa xong | Access `202` | `EXPORT_REQUEST_ACCEPTED`, chưa `EXPORT_COMPLETED` | Worker có log chẩn đoán riêng |
| Worker hoàn thành export | Không nhất thiết có HTTP access mới | `EXPORT_COMPLETED` với actor/initiator và job ID | Ghi duration, file processing trace |
| Collector audit không sẵn sàng | Request vẫn được log theo điều kiện hạ tầng | Event trong outbox, retry/alert; hoặc fail-closed theo policy | Diagnostic về sink/backlog |

### 11.2. Kiểm thử Spring transaction để tránh false audit

Mã minh họa dưới đây dùng các service/repository của mục 7, giả định test đã seed người quản trị tenant và thành viên cần đổi role. Kỹ thuật kiểm thử thực tế có thể dùng Spring Boot Test, MockMvc và database test phù hợp với production.

```java
@SpringBootTest
class RoleAuditIntegrationTest {
    @Autowired MemberRoleService roleService;
    @Autowired MemberRepository members;
    @Autowired AuditEventRepository audits;

    @Test
    void committedRoleChangeHasOneMatchingAuditEvent() {
        // Fixture: tenant A, member M, role VIEWER.
        UUID memberId = fixtureMemberId();
        RoleChangeCommand command = new RoleChangeCommand(
                fixtureTenantId(), memberId, Role.EDITOR, "op-100");

        roleService.changeRole(command, fixtureTenantAdmin());

        assertThat(members.findById(memberId).orElseThrow().getRole())
                .isEqualTo(Role.EDITOR);
        assertThat(audits.countByOperationIdAndAction(
                "op-100", "MEMBERSHIP_ROLE_CHANGED"))
                .isEqualTo(1);
    }
}
```

Đây là **khung tích hợp**, không phải file Java có thể chạy độc lập: cần viết fixture và domain types phù hợp. Không bao `@Transactional` quanh chính test khi muốn quan sát **trạng thái đã commit sau lời gọi service**; transaction của test có thể làm thay đổi hành vi commit/rollback và khiến assertion đánh giá sai.

Để thử rollback, ép câu lệnh audit insert lỗi hoặc ràng buộc DB thất bại **trong cùng transaction**, rồi xác minh role trong DB không đổi và không có event `SUCCEEDED`. Không kiểm thử rollback bằng cách mock toàn bộ repository rồi chỉ xác nhận `verify(auditRepo).save(...)`: lời gọi method không chứng minh tính nguyên tử với database.

### 11.3. Kiểm thử idempotency, retry và outbox

Với một operation ID:

1. Gửi request lần đầu và cố tình làm rơi response **sau commit**.
2. Gửi lại cùng idempotency key và payload.
3. Xác nhận DB thay đổi đúng một lần, số event `ROLE_CHANGED / SUCCEEDED` đúng một, nhưng access log có thể có hai dòng.
4. Dừng worker audit exporter sau khi sink nhận event nhưng trước ACK, khởi động lại; xác minh sink không tạo bản ghi audit trùng với cùng `event_id`.
5. Mô phỏng sink chậm hoặc lỗi; kiểm tra outbox backlog, retry có backoff, giới hạn attempts và alert.

Nếu idempotency key chỉ được scope theo URL mà không theo tenant/actor/payload, có thể tạo xung đột hoặc trả kết quả của người khác. Bản ghi audit không nên chứa raw client-supplied key nếu đó là dữ liệu không tin cậy hoặc chứa thông tin nhạy cảm; ưu tiên một `operation_id` nội bộ được chuẩn hóa.

### 11.4. Kiểm thử log không lộ secret và PII

Tạo request test chứa:

```http
GET /api/customers?email=private%40example.invalid HTTP/1.1
Authorization: Bearer test-secret-do-not-log
Cookie: session=test-cookie-do-not-log
X-Request-ID: injected%0AFAKE-AUDIT-ENTRY
```

Dùng appender/sink test để thu output và assert:

- Không chứa `test-secret-do-not-log`, `test-cookie-do-not-log` hoặc giá trị email nếu policy cấm.
- Không có raw query string trong access log; route được chuẩn hóa như `/api/customers`.
- Không tạo thêm dòng giả từ `X-Request-ID` có CR/LF hoặc ký tự điều khiển; giá trị đã được kiểm tra và chuẩn hóa.
- Audit event lấy `actor` từ security context, không từ header tự khai.
- Exception handler không đưa secret/stack trace nhạy cảm vào response body hoặc diagnostic output.

Đây là test cho toàn pipeline: log của gateway, servlet container, HTTP client, ORM, security framework và agent cũng có thể vô tình ghi dữ liệu. Không chỉ xét logger do lập trình viên tự gọi.

## 12. Quy trình xử lý sự cố bằng ba loại log

Giả sử lúc 14:05 người dùng phát hiện quyền của một thành viên bị đổi mà họ không thực hiện:

1. **Từ audit log:** tra `target.type=TENANT_MEMBER`, `target.id`, tenant và khoảng thời gian. Lấy `actor.subject`, `action`, `before/after`, `outcome` và `operation_id` của sự kiện đã commit.
2. **Sang access log:** dùng `request_id`/`trace_id` tìm request ứng với sự kiện và các lần thử lại. Xem route, status, thời gian, nguồn truy cập hợp lệ theo chính sách, có nhiều request lặp hay không.
3. **Sang diagnostic log/tracing:** theo trace thấy service nào đã kiểm tra quyền, câu SQL/transaction nào gặp lỗi, có retry hay timeout không; tìm bug hoặc sai cấu hình.
4. **Đối chiếu trạng thái hiện tại:** xác nhận database và lịch sử thay đổi liên quan; phân biệt hành động thứ hai, retry cùng operation hay event giao trùng.
5. **Kiểm chứng bằng chứng:** xem pipeline audit có backlog, mất event, sai đồng hồ, log bị sửa hoặc retention hết hạn không; nếu có, phải nêu giới hạn kết luận.

Sơ đồ tra cứu:

```mermaid
flowchart LR
    AUD["Audit: actor + target + action + outcome"] -->|"request_id / trace_id"| ACC["Access: method + route + status + latency"]
    ACC -->|"trace_id / span_id"| DIA["Diagnostic: code + dependency + exception"]
    AUD -->|"operation_id"| BIZ["DB state / idempotency / job"]
    DIA --> BIZ
```

Không chỉ tìm `ERROR` rồi kết luận hành động không xảy ra. Có thể có `ERROR` khi gửi response hoặc gửi log ra collector **sau khi business transaction đã commit thành công**.

## 13. Các hiểu nhầm thường gặp

| Khẳng định | Vì sao không đúng / thiếu | Cách thiết kế |
|---|---|---|
| "Có access log `200` nghĩa là nghiệp vụ đã hoàn tất." | `202` có thể chỉ là tiếp nhận, response có thể xảy ra trước side effect hoặc hợp đồng không đại diện cho commit. | Dựa vào DB state/event kết quả; phân biệt accepted/completed. |
| "Ghi `log.info('updated')` là đã có audit." | Có thể ghi trước commit, bị sampling/rotation, không đủ actor/action/target. | Audit event có schema và bền vững đúng ranh giới transaction. |
| "Chỉ cần log IP để biết người làm." | IP có thể thuộc NAT/proxy/shared host; không chứng minh authenticated principal. | Lưu actor subject đã xác thực, tenant/delegation; IP chỉ là ngữ cảnh phụ. |
| "Muốn điều tra tốt thì log toàn bộ body." | Có thể lộ token, dữ liệu cá nhân và bí mật. | Allowlist field, phân loại dữ liệu, masking và kiểm soát retention. |
| "Audit thành công có thể gửi bằng HTTP sau commit, lỗi thì bỏ qua." | Crash giữa commit và gửi làm mất audit. | Transactional outbox hoặc cơ chế bền vững tương đương. |
| "Outbox bảo đảm exactly-once delivery." | Worker crash trước ACK có thể gửi lại. | Dedup theo event ID, delivery ít nhất một lần. |
| "Không có audit row là chắc chắn không có hành động." | Pipeline có thể mất event, event ngoài DB hoặc transaction không được instrument. | Kiểm tra coverage, health, backlog và lớp bằng chứng khác. |
| "Audit phải là một log text không bao giờ xóa." | Không bảo đảm tính toàn vẹn, vi phạm nguyên tắc tối thiểu hóa dữ liệu và có thể mâu thuẫn retention policy. | Event có cấu trúc, kiểm chứng integrity, retention có căn cứ. |
| "Trace ID chính là user ID." | Trace ID là ID chẩn đoán, không mang ý nghĩa xác thực. | Audit actor lấy từ identity đã xác minh. |
| "Nếu user gửi lại request thì phải có hai audit success." | Retry cùng operation có thể chỉ có một thay đổi đã commit. | Tách attempts khỏi business events; dùng operation ID và idempotency. |

## 14. Bài tập thực hành

### Bài tập 1 — Phân loại log theo tình huống

Cho 6 yêu cầu: `GET /health`, `GET /orders/{id}`, `PATCH /members/{id}/role`, `POST /exports` trả `202`, worker hoàn thành export và request bị `403` vì thiếu quyền. Với mỗi trường hợp, hãy xác định nên có access log, audit event hay diagnostic log nào; giải thích vì sao worker hoàn thành export có thể không tạo thêm HTTP access log ở service API.

*Gợi ý:* audit riêng khi có ý nghĩa nghiệp vụ/bảo mật, bao gồm đọc dữ liệu nhạy cảm theo policy; log lỗi chỉ khi có dữ kiện chẩn đoán cần thiết, không tự sinh mọi cấp log cho mọi hành động.

### Bài tập 2 — Tìm lỗi ghi audit trước commit

Xem code:

```java
@Transactional
public void refund(UUID paymentId) {
    Payment p = payments.findById(paymentId).orElseThrow();
    log.info("AUDIT refund completed id={}", paymentId);
    p.setStatus(PaymentStatus.REFUNDED);
    paymentProvider.refund(paymentId); // HTTP trong transaction
}
```

Hãy chỉ ra ba vấn đề: thời điểm phát log, HTTP ngoài trong transaction và kết quả refund tại provider có thể không khớp DB. Thiết kế trạng thái `REFUND_PENDING`, `REFUND_UNKNOWN`, `REFUNDED` cùng outbox, idempotency và audit events phù hợp. Đảm bảo event hoàn tất chỉ được ghi sau khi biết kết quả thực sự.

### Bài tập 3 — Thiết kế schema và retention

Thiết kế bảng audit cho các event `LOGIN_DENIED`, `MEMBERSHIP_ROLE_CHANGED`, `EXPORT_COMPLETED`. Chỉ định bắt buộc/nullable field, cách nhận dạng actor/tenant, version, timestamp, event ID, operation ID, field nào được lưu trước/sau, cơ chế toàn vẹn và retention theo mức nhạy cảm. Giải thích vì sao không nên đưa access token và dữ liệu raw export vào `change_summary`.

### Bài tập 4 — Viết kiểm thử lỗi và retry

Dùng Spring Boot với database test, thiết lập một transaction cố ý rollback sau khi đổi role; assert DB không đổi và không có `ROLE_CHANGED / SUCCEEDED`. Sau đó mô phỏng commit thành công nhưng client mất response, retry cùng idempotency key. Xác minh một business change, một audit success, hai access attempts. Cuối cùng làm audit exporter gửi lặp cùng event ID, xác minh sink deduplicate.

### Bài tập 5 — Truy vết sự cố

Tạo một bộ mẫu gồm access log `PATCH` status `204`, audit `ROLE_CHANGED` và diagnostic log `timeout while writing response`. Dùng `trace_id`, `request_id` và `operation_id` để giải thích vì sao client tưởng thất bại nhưng database đã commit. Đề xuất cách UI nên hiển thị kết quả khi người dùng retry.

## 15. Checklist trước khi triển khai

- [ ] Có danh mục rõ những HTTP requests, security decisions và business actions cần access/audit/diagnostic log.
- [ ] Mỗi loại log có schema, chủ sở hữu, pipeline, retention, quyền truy cập và chính sách bảo vệ riêng.
- [ ] Access log ghi route template, status và duration; không ghi raw secret/query/body.
- [ ] Audit event có actor đã xác thực, tenant, action, target, decision, outcome, timestamp và ID tương quan.
- [ ] Audit `SUCCEEDED` của database write được commit atomically với business change; rollback không tạo false success.
- [ ] Đối với event bảo mật thất bại hoặc bị từ chối, có đường lưu riêng phù hợp để không bị rollback làm mất dấu vết.
- [ ] Luồng async phân biệt `ACCEPTED` và `COMPLETED`; request retry không nhân đôi business audit.
- [ ] Nếu chuyển audit ra external store, có outbox/retry, dedup theo event ID, kiểm soát backlog và failure policy.
- [ ] Có cơ chế chống chỉnh sửa/kiểm chứng toàn vẹn audit phù hợp với rủi ro; hạn chế quyền đọc/ghi/xóa.
- [ ] Có correlation giữa log, trace và operation; ID duy nhất không được đưa vào metric labels cardinality cao.
- [ ] Kiểm thử log không chứa token/PII, xử lý `401/403`, commit/rollback, retry, exporter crash và pipeline lỗi.
- [ ] Quy trình điều tra phân biệt phản hồi HTTP, trạng thái business thực tế và bằng chứng log chưa đầy đủ.

**Nguyên tắc cần nhớ:** Access log ghi **dấu vết truy cập HTTP**; log chẩn đoán ghi **dữ kiện để tìm nguyên nhân**; audit log ghi **sự kiện và quyết định nghiệp vụ/bảo mật cần truy trách nhiệm**. Ba loại bổ sung cho nhau nhưng có yêu cầu khác nhau về ngữ nghĩa, ranh giới transaction, tính đầy đủ, toàn vẹn và quyền truy cập. Một hệ thống REST API quan sát được tốt phải cho phép nối các dấu vết với nhau mà vẫn chứng minh được **điều gì đã thực sự xảy ra**, kể cả khi client timeout, request bị retry hoặc pipeline log gặp lỗi.
