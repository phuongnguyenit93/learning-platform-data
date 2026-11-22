# Ghi authentication và authorization decision

Trong chương **API logging** của module `SECURITY_API_SECURITY`, log bảo mật cần ghi nhận được hệ thống đã xác thực ai, đánh giá quyền gì và đưa ra quyết định nào đối với một request. Khi có truy cập trái phép, việc chỉ lưu HTTP access log với method, URL và status code thường không đủ để trả lời: token được chấp nhận hay từ chối vì lý do nào, principal thuộc tenant nào, policy nào được áp dụng, người gọi có quyền trên đối tượng dữ liệu hay không và quyết định đó xảy ra ở service nào.

**Authentication decision** là kết quả xác minh danh tính hoặc credential. **Authorization decision** là kết quả đánh giá principal có được phép thực hiện một action trên một resource trong một context cụ thể hay không. Ghi nhận hai loại quyết định này giúp điều tra sự cố, phát hiện lạm dụng, chứng minh kiểm soát và tìm lỗi cấu hình phân quyền.

Log quyết định bảo mật cũng là dữ liệu nhạy cảm. Nếu ghi toàn bộ token, cookie, request body, thông tin cá nhân hoặc chi tiết policy nội bộ, chính hệ thống giám sát có thể trở thành nguồn rò rỉ mới. Mục tiêu là ghi đủ bằng chứng để truy vết và phân tích, đồng thời giới hạn dữ liệu, quyền truy cập và thời hạn lưu.

## Vì sao cần ghi decision thay vì chỉ ghi HTTP request?

Một access log thông thường có thể cho biết `POST /api/transfers` trả `403`, nhưng không thể hiện rõ:

- Credential không hợp lệ, hết hạn hay đã bị thu hồi?
- Principal đã được xác thực nhưng thiếu permission chức năng nào?
- Người gọi có quyền `transfer:create` nhưng không sở hữu tài khoản nguồn?
- Request bị từ chối do tenant mismatch, policy deny hay trạng thái resource không cho phép?
- Policy version nào được dùng và service nào đưa ra quyết định?
- Có nhiều lần từ chối bất thường trên cùng một principal, client hoặc resource không?

Ví dụ, một API đọc tài khoản có thể xác thực JWT thành công nhưng từ chối truy cập vì tài khoản thuộc tenant khác. Nếu log chỉ ghi `403`, đội vận hành khó phân biệt lỗi cấu hình tenant với hành vi dò tìm tài nguyên. Một decision event có cấu trúc giúp ghi nhận loại quyết định và mã lý do mà không cần lưu token hoặc dữ liệu tài khoản đầy đủ.

Ghi decision còn giúp kiểm tra các lớp bảo vệ theo phạm vi module: xác thực, phân quyền chức năng, phân quyền mức đối tượng, validation, bảo vệ dữ liệu và giám sát. Nó không thay thế log nghiệp vụ, access log hay metric; mỗi loại phục vụ một câu hỏi khác nhau.

## Phân biệt các loại log

| Loại log | Câu hỏi chính | Ví dụ trường dữ liệu |
|---|---|---|
| HTTP access log | Request đi tới đâu và kết thúc thế nào? | Method, route template, status, latency, request ID |
| Authentication event | Credential/principal được xác minh ra sao? | Principal type, issuer ID, kết quả, failure code, auth method |
| Authorization decision | Principal có được phép thực hiện action trên resource không? | Subject reference, action, resource type, decision, policy ID/version |
| Business audit event | Thao tác nghiệp vụ nào đã xảy ra? | Transfer created, actor, transaction ID, trạng thái trước/sau |
| Application diagnostic log | Service gặp lỗi hoặc trạng thái kỹ thuật nào? | Error code, component, exception class đã lọc |
| Security alert/metric | Có xu hướng hoặc hành vi bất thường không? | Denial rate, login failures, policy deny count |

Không nên nhồi mọi thông tin vào một chuỗi text tự do. Dùng event có schema ổn định để dễ lọc, truy vấn, đối chiếu và kiểm soát dữ liệu. Access log có thể chứa URL và IP; decision log cần bổ sung context xác thực/phân quyền; business audit ghi nhận side effect đã xảy ra. Tránh ghi trùng payload hoặc dữ liệu nhạy cảm ở nhiều pipeline.

## Ghi nhận authentication decision

Authentication event nên phản ánh kết quả xác minh credential, không lưu credential được xác minh.

### 1. Những thông tin nên ghi

Tùy cơ chế xác thực, một event có thể chứa:

- Thời điểm UTC và event ID duy nhất.
- Kết quả `SUCCESS` hoặc `FAILURE`.
- Loại principal: user, service account, workload identity, API client hoặc anonymous.
- Subject/client reference dạng opaque hoặc pseudonymous phù hợp.
- Authentication method: password, client credentials, mTLS, passkey, API key hoặc cơ chế đã định nghĩa.
- Issuer/key ID hoặc identity provider ID đã đăng ký, không phải secret.
- Failure code đã chuẩn hóa, ví dụ `TOKEN_EXPIRED`, `INVALID_ISSUER`, `SIGNATURE_INVALID`, `MFA_REQUIRED`.
- Request ID, trace ID và service/endpoint đã xử lý.
- Context vận hành tối thiểu như environment và source network metadata khi thật sự cần.

Không ghi access token, refresh token, session cookie, password, private key, client secret, mã OTP hoặc toàn bộ JWT. Không log nguyên header `Authorization` để tiện debug. Nếu cần liên kết các lần sử dụng cùng một credential, dùng credential ID hoặc fingerprint được tạo bằng cơ chế phù hợp; không dùng token thô làm correlation key.

### 2. Ghi cả thành công và thất bại theo mức độ phù hợp

Các lần authentication thất bại thường hữu ích cho phát hiện brute force, credential stuffing, token misuse hoặc cấu hình sai; cần ghi nhận có giới hạn để tránh log flood. Authentication thành công cũng quan trọng khi đăng nhập mới, đổi yếu tố xác thực, cấp token, sử dụng service identity hoặc truy cập hệ thống nhạy cảm.

Với workload có lượng request rất lớn, không nhất thiết tạo một bản ghi chi tiết cho mọi lần kiểm tra token nếu điều đó làm log quá tải. Có thể ghi đầy đủ các sự kiện vòng đời danh tính và các lần xác thực nhạy cảm, đồng thời dùng metric/aggregation cho traffic thông thường. Chính sách sampling phải bảo đảm không làm mất các sự kiện bắt buộc theo yêu cầu audit hoặc điều tra.

### 3. Chuẩn hóa failure reason

Không đưa exception message tùy ý từ thư viện JWT, identity provider hoặc parser vào event. Các message này có thể chứa token fragment, claim, cấu hình nội bộ hoặc dữ liệu do attacker kiểm soát. Thay vào đó, ánh xạ lỗi sang mã ổn định:

| Failure code | Ý nghĩa nội bộ |
|---|---|
| `CREDENTIAL_MISSING` | Không có credential theo yêu cầu endpoint |
| `CREDENTIAL_MALFORMED` | Cấu trúc credential không hợp lệ |
| `SIGNATURE_INVALID` | Chữ ký không xác minh được |
| `TOKEN_EXPIRED` | Token đã hết hạn |
| `INVALID_ISSUER` | Issuer không nằm trong cấu hình tin cậy |
| `INVALID_AUDIENCE` | Audience không dành cho API này |
| `TOKEN_REVOKED` | Credential/token đã bị thu hồi |
| `MFA_REQUIRED` | Chính sách yêu cầu xác thực bổ sung |
| `IDENTITY_PROVIDER_UNAVAILABLE` | Không thể hoàn tất xác minh do dependency lỗi |

Không nhất thiết trả các mã nội bộ này cho client. Response bên ngoài nên tuân theo hợp đồng API, tránh tiết lộ chi tiết giúp attacker phân biệt user tồn tại, key nào hợp lệ hoặc cấu hình xác thực cụ thể.

## Ghi nhận authorization decision

Authorization phải được đánh giá theo principal, action, resource và context. Event cần phản ánh các thành phần đó để điều tra được lý do allow/deny.

### 1. Schema cho decision event

Một authorization event nên có các trường:

| Trường | Mục đích | Lưu ý |
|---|---|---|
| `eventId` | Định danh event | Duy nhất để truy vết và chống ingest trùng |
| `occurredAt` | Thời điểm quyết định | UTC, định dạng thống nhất |
| `decision` | `ALLOW` hoặc `DENY` | Không suy ra từ HTTP status duy nhất |
| `subjectType` | User/service/client | Không lưu tên hiển thị nếu không cần |
| `subjectRef` | Principal được đánh giá | Opaque/pseudonymous ID, có kiểm soát khả năng liên kết |
| `tenantRef` | Tenant context | Chỉ ghi nếu cần điều tra cross-tenant |
| `action` | Hành động được yêu cầu | Ví dụ `invoice:read`, `transfer:create` |
| `resourceType` | Loại đối tượng | Ví dụ `invoice`, `account`, `document` |
| `resourceRef` | Đối tượng cụ thể | Dùng ID nội bộ hoặc fingerprint phù hợp; không ghi dữ liệu object |
| `policyId` / `policyVersion` | Quy tắc được áp dụng | Không đưa policy expression hoặc secret vào log |
| `reasonCode` | Nhóm lý do quyết định | Mã ổn định, không dùng exception text tự do |
| `service` / `routeTemplate` | Thành phần và endpoint | Dùng route template, tránh URL có ID/PII |
| `requestId` / `traceId` | Liên kết các log | Sinh hoặc xác thực theo chuẩn tracing |

Ví dụ event JSON:

```json
{
  "eventType": "authorization.decision",
  "eventId": "01J9Z8D5H4J4W0X7Y6N3A2B1C0",
  "occurredAt": "2026-11-18T13:30:00Z",
  "decision": "DENY",
  "subjectType": "user",
  "subjectRef": "usr_ref_7f21",
  "tenantRef": "tenant_ref_a12c",
  "action": "invoice:read",
  "resourceType": "invoice",
  "resourceRef": "inv_ref_9021",
  "policyId": "invoice-tenant-access",
  "policyVersion": "12",
  "reasonCode": "TENANT_MISMATCH",
  "service": "billing-api",
  "routeTemplate": "GET /api/invoices/{invoiceId}",
  "requestId": "req_01J9Z8D5H4J4W0X7",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là schema minh họa. ID trong ví dụ không đại diện danh tính thật. Hãy xác định rõ ý nghĩa từng trường, kiểu dữ liệu, giới hạn độ dài, danh sách enum và phiên bản schema trước khi đưa vào pipeline.

### 2. Ghi rõ decision và reason code

Ví dụ một số reason code:

| Reason code | Tình huống |
|---|---|
| `ROLE_OR_SCOPE_MISSING` | Principal thiếu role/scope cần thiết |
| `FUNCTION_NOT_ALLOWED` | Không có quyền gọi chức năng |
| `RESOURCE_NOT_FOUND_OR_HIDDEN` | Resource không tồn tại hoặc được che theo chính sách |
| `TENANT_MISMATCH` | Resource không thuộc tenant context của principal |
| `OWNER_MISMATCH` | Principal không phải chủ sở hữu hoặc không có quan hệ được phép |
| `RESOURCE_STATE_BLOCKED` | Trạng thái nghiệp vụ không cho phép hành động |
| `POLICY_EXPLICIT_DENY` | Policy đưa ra deny rõ ràng |
| `POLICY_EVALUATION_ERROR` | Không thể đánh giá policy an toàn |

Reason code nội bộ cần đủ chi tiết cho đội vận hành, nhưng không nhất thiết được đưa nguyên vẹn vào response client. Ví dụ, API có thể trả cùng một response `404` cho resource không tồn tại và resource mà caller không được phép biết, trong khi audit log nội bộ phân biệt hai tình huống theo chính sách.

### 3. Ghi decision ở đúng điểm trong luồng

Authorization event cần được phát ra sau khi policy engine hoặc lớp kiểm soát đã đưa ra quyết định. Không ghi `ALLOW` chỉ vì request đã qua authentication; xác thực danh tính không đồng nghĩa được phép thao tác.

Với thao tác nhạy cảm, cần liên kết decision với kết quả nghiệp vụ. Một quyết định `ALLOW` có thể được theo sau bởi lỗi database hoặc conflict; decision log không có nghĩa thao tác đã thành công. Hãy dùng business audit event riêng để ghi nhận side effect thực sự, ví dụ transfer được tạo hoặc quyền được thay đổi.

Đối với policy evaluation error hoặc dependency phân quyền không khả dụng, quyết định cần theo nguyên tắc fail closed cho thao tác nhạy cảm. Ghi `DENY` hoặc trạng thái đánh giá lỗi với reason code riêng; không ghi `ALLOW` mặc định chỉ để request tiếp tục.

## Ghi decision trong ứng dụng Java/Spring

Ví dụ dưới đây minh họa cách phát structured event sau khi có kết quả authorization. Dùng logging API hỗ trợ key-value để hệ thống log thu nhận trường riêng, thay vì nối chuỗi thủ công.

```java
public record AuthorizationDecisionEvent(
        String eventId,
        Instant occurredAt,
        String decision,
        String subjectType,
        String subjectRef,
        String tenantRef,
        String action,
        String resourceType,
        String resourceRef,
        String policyId,
        String policyVersion,
        String reasonCode,
        String service,
        String routeTemplate,
        String requestId,
        String traceId
) {}
```

Một publisher có thể ghi event bằng SLF4J 2.x:

```java
private static final Logger auditLog =
        LoggerFactory.getLogger("SECURITY_AUDIT");

void logDecision(AuthorizationDecisionEvent event) {
    auditLog.atInfo()
        .addKeyValue("eventType", "authorization.decision")
        .addKeyValue("eventId", event.eventId())
        .addKeyValue("occurredAt", event.occurredAt().toString())
        .addKeyValue("decision", event.decision())
        .addKeyValue("subjectType", event.subjectType())
        .addKeyValue("subjectRef", event.subjectRef())
        .addKeyValue("tenantRef", event.tenantRef())
        .addKeyValue("action", event.action())
        .addKeyValue("resourceType", event.resourceType())
        .addKeyValue("resourceRef", event.resourceRef())
        .addKeyValue("policyId", event.policyId())
        .addKeyValue("policyVersion", event.policyVersion())
        .addKeyValue("reasonCode", event.reasonCode())
        .addKeyValue("service", event.service())
        .addKeyValue("routeTemplate", event.routeTemplate())
        .addKeyValue("requestId", event.requestId())
        .addKeyValue("traceId", event.traceId())
        .log("Authorization decision recorded");
}
```

Đây là ví dụ minh họa, cần SLF4J 2.x và provider logging được cấu hình để xuất key-value theo định dạng có cấu trúc. Với phiên bản cũ, dùng encoder JSON hoặc logging adapter phù hợp. Không đưa toàn bộ `Authentication`, `SecurityContext`, JWT claims hoặc request object vào logger.

Ở nơi gọi, chỉ tạo event sau khi đã có decision:

```java
AuthorizationResult result = authorizationService.evaluate(
    principal, "invoice:read", invoice, requestContext
);

auditPublisher.publish(toDecisionEvent(result, principal, invoice, requestContext));

if (!result.allowed()) {
    throw new AccessDeniedException("Access denied");
}
```

`toDecisionEvent` phải chỉ ánh xạ các trường đã được duyệt. Không serialize nguyên object `principal`, `invoice` hoặc `requestContext`; các object này thường chứa PII, claim, dữ liệu nghiệp vụ và có thể thay đổi cấu trúc theo phiên bản.

## Chọn mức độ ghi ALLOW và DENY

Ghi mọi decision thành công có thể tạo lượng log rất lớn, nhưng chỉ ghi deny lại làm mất bối cảnh của các thao tác được phép mà sau đó gây thiệt hại. Cần phân loại theo rủi ro và mục đích audit.

| Loại quyết định | Cách ghi gợi ý |
|---|---|
| Authentication failure | Ghi event đã chuẩn hóa; rate limit và aggregation để tránh log flood |
| Authentication success thông thường | Ghi các mốc đăng nhập/đổi credential; request xác thực lặp lại có thể dùng metric theo policy |
| Authorization deny | Ghi đầy đủ metadata tối thiểu và reason code; phát hiện burst hoặc pattern bất thường |
| Authorization allow cho thao tác nhạy cảm | Ghi chi tiết vì có ý nghĩa audit, ví dụ đọc dữ liệu nhạy cảm, chuyển tiền, thay đổi quyền |
| Authorization allow cho thao tác tần suất cao, rủi ro thấp | Có thể aggregate/sample theo policy đã phê duyệt; giữ metric tổng và khả năng truy vết cần thiết |
| Policy evaluation error | Ghi riêng như lỗi kiểm soát; cảnh báo khi tăng bất thường |

Không để sampling loại bỏ các sự kiện mà nghĩa vụ audit yêu cầu phải ghi đầy đủ. Nếu dùng sampling, ghi rõ tỷ lệ, điều kiện và giới hạn của bằng chứng trong tài liệu vận hành.

## Bảo vệ dữ liệu trong security log

Decision log có thể tiết lộ quan hệ giữa user, tenant, resource và quyền. Cần áp dụng data minimization và access control ngay từ lúc thiết kế schema.

### 1. Không ghi secret hoặc payload nhạy cảm

Không ghi các dữ liệu sau vào authentication/authorization log:

- Password, password hash, OTP, recovery code hoặc câu trả lời bảo mật.
- Access token, refresh token, session ID, cookie, API key, client secret hoặc private key.
- Toàn bộ JWT, SAML assertion hoặc certificate private material.
- Request/response body chứa dữ liệu cá nhân, thanh toán hoặc hồ sơ nhạy cảm.
- Toàn bộ header map, query string hoặc exception message chưa được lọc.
- Policy expression, secret/configuration nội bộ hoặc nội dung giúp attacker dò cấu trúc bảo vệ.

Nếu cần biết token nào được dùng, lưu `credentialId`, `keyId` hoặc fingerprint một chiều có khóa. Không dùng hash không khóa của token ngắn hoặc giá trị dễ đoán nếu có thể dò từ điển. Với resource ID, cân nhắc dùng opaque reference hoặc HMAC fingerprint nếu người đọc log không cần biết ID gốc.

### 2. Giảm thiểu PII và context

Chỉ ghi user ID/tenant ID khi cần cho điều tra và đã xác định quyền truy cập. Có thể dùng pseudonymous reference trong pipeline chung và chỉ cho nhóm có thẩm quyền ánh xạ lại. IP address, user agent và device metadata cũng có thể là dữ liệu cá nhân; chỉ thu thập khi có mục đích, retention và quyền truy cập phù hợp.

Không ghi URL đầy đủ nếu path chứa ID nhạy cảm hoặc query string có token. Dùng route template như `/api/invoices/{invoiceId}`. Tránh ghi tên, email hoặc số điện thoại nếu một subject reference đã đủ cho mục đích điều tra.

### 3. Chống log injection

Một số giá trị như username, user agent, client-supplied correlation ID hoặc resource name có thể do attacker kiểm soát. Nếu ghi trực tiếp vào log text, ký tự xuống dòng hoặc delimiter có thể làm giả event mới, phá cấu trúc hoặc gây lỗi parser.

- Ưu tiên structured logging với JSON encoder đã kiểm thử.
- Validate kiểu, độ dài và charset của field; giới hạn kích thước trước khi ghi.
- Escape control character và ký tự đặc biệt theo định dạng output.
- Không nối chuỗi log từ dữ liệu request chưa kiểm tra.
- Không cho client tự đặt `reasonCode`, `decision`, `subjectRef` hoặc `policyId` trong security event.

Ví dụ không an toàn:

```java
// Không an toàn: dữ liệu do caller kiểm soát có thể chèn dòng log giả.
logger.info("Login failed for user=" + username);
```

Ưu tiên event có trường riêng:

```java
logger.atWarn()
    .addKeyValue("eventType", "authentication.failure")
    .addKeyValue("reasonCode", "CREDENTIAL_INVALID")
    .addKeyValue("subjectRef", safeSubjectRef)
    .log("Authentication failed");
```

`safeSubjectRef` phải được tạo từ nguồn danh tính nội bộ đã xác minh hoặc được chuẩn hóa trước khi ghi. Structured logging giảm nguy cơ phá cấu trúc, nhưng không thay thế validation, giới hạn độ dài và kiểm tra encoder.

## Correlation giữa request, decision và business event

Để điều tra một request xuyên nhiều service, cần một cơ chế correlation nhất quán:

- `requestId`: định danh request tại biên nhận request; nếu client gửi ID, kiểm tra định dạng/độ dài rồi tạo ID nội bộ mới hoặc lưu giá trị ngoài ở trường riêng.
- `traceId`: liên kết span giữa gateway, API và downstream theo chuẩn tracing đang dùng, ví dụ W3C Trace Context.
- `eventId`: định danh riêng của authentication/authorization event.
- `businessTransactionId`: liên kết decision với thao tác nghiệp vụ nếu đã có ID tin cậy.

Không dùng một ID cho tất cả mục đích. Request ID không thay event ID; trace ID không phải bằng chứng xác thực; transaction ID không được lấy trực tiếp từ input chưa kiểm tra rồi coi là đáng tin.

Khi một request qua API gateway và nhiều microservice, mỗi service có thể đưa ra authorization decision riêng. Log cần thể hiện `service` và `routeTemplate` để xác định nơi quyết định được đưa ra. Không mặc định decision của gateway đủ thay thế object-level authorization ở service sở hữu dữ liệu.

## Tính toàn vẹn, vận chuyển và quyền truy cập log

Security log là bằng chứng phục vụ điều tra. Nếu principal có quyền thay đổi log của chính mình, hoặc ứng dụng bị xâm nhập có thể xóa dấu vết, giá trị audit giảm đáng kể.

Các biện pháp nên có:

- Gửi log tới hệ thống tập trung qua kênh mã hóa; xác thực workload/service identity của producer.
- Tách quyền ghi, đọc, export, cấu hình retention và xóa log. Người có quyền triển khai ứng dụng không mặc nhiên được xóa audit log.
- Hạn chế quyền truy cập theo service, tenant, môi trường và vai trò điều tra.
- Dùng storage append-only/immutable hoặc cơ chế phát hiện sửa đổi cho audit stream quan trọng.
- Có sequence, timestamp, event ID hoặc checksum phù hợp để phát hiện thiếu/trùng event; không tự coi hash chain đơn lẻ là bằng chứng chống sửa đổi nếu key và storage cùng bị kiểm soát.
- Mã hóa dữ liệu khi lưu, quản lý key riêng và ghi audit cho thao tác tìm kiếm/export.
- Đặt retention theo loại log; xóa hoặc ẩn danh khi hết mục đích, có xử lý legal hold được phê duyệt.
- Theo dõi queue lag, dropped event, collector outage và lỗi ghi log.

### Logging failure phải có chính sách rõ ràng

Nếu hệ thống log tạm thời không khả dụng, không phải mọi endpoint đều cần hành vi giống nhau:

- Với thao tác có yêu cầu audit bắt buộc, có thể cần ghi decision/audit event vào outbox hoặc store bền vững trong cùng transaction trước khi thực hiện side effect.
- Với request thông thường, có thể dùng queue bền vững và retry có giới hạn, đồng thời phát cảnh báo khi mất log.
- Không âm thầm bỏ toàn bộ security event trong thời gian dài.
- Không làm sập toàn bộ API chỉ vì một log sink phụ trợ lỗi nếu policy không yêu cầu điều đó; xác định rõ ngưỡng, fallback và runbook.
- Không để attacker cố tình làm đầy log hoặc gây lỗi collector để biến logging thành denial-of-service.

Với thao tác nhạy cảm, transactional outbox là một lựa chọn: ghi business change và audit event vào cùng database transaction; publisher gửi event sau commit. Cách này giúp tránh tình trạng thao tác đã thành công nhưng audit event bị mất do network failure. Consumer log vẫn cần idempotency và monitoring.

## Alerting và phát hiện hành vi bất thường

Decision event hữu ích hơn khi kết hợp với metric và rule phát hiện:

- Tỷ lệ authentication failure tăng đột biến theo account, client, IP range hoặc ASN.
- Một principal liên tục bị deny trên nhiều resource ID khác nhau, dấu hiệu dò tài nguyên.
- Nhiều `TENANT_MISMATCH` từ cùng client hoặc service.
- Một service account gọi action ngoài baseline hoặc truy cập resource type bất thường.
- Tỷ lệ policy evaluation error tăng, có thể báo hiệu dependency hoặc cấu hình policy lỗi.
- Một user thực hiện nhiều thao tác nhạy cảm trong thời gian ngắn hoặc ngoài khung hành vi thông thường.
- Security log pipeline bị trễ, mất event hoặc có producer không xác thực.

Không nên tạo alert cho mọi deny đơn lẻ; điều đó gây nhiễu. Dùng ngưỡng, cửa sổ thời gian, mức độ rủi ro và baseline phù hợp. Alert cần có mã rule, phạm vi, thời điểm và link tới truy vấn log đã phân quyền, không đính kèm token hoặc raw payload.

## Kiểm thử authentication và authorization logging

Kiểm thử phải xác nhận cả decision lẫn dữ liệu được ghi, đồng thời chứng minh không có secret/PII ngoài chính sách lọt vào log.

| Tình huống | Kết quả mong đợi |
|---|---|
| Token hợp lệ | Ghi authentication success theo mức độ policy yêu cầu; không log token |
| Token hết hạn/sai issuer/sai audience | Ghi failure code chuẩn hóa; không log JWT hoặc claim nhạy cảm |
| User thiếu role/scope | Ghi authorization deny với action và reason code |
| User có quyền chức năng nhưng khác tenant | Ghi object-level deny phù hợp; không log dữ liệu resource đầy đủ |
| Policy evaluation dependency lỗi | Ghi trạng thái lỗi riêng; thao tác nhạy cảm fail closed |
| Authorization allow cho transfer/admin action | Có decision event và business audit event tương ứng khi side effect thành công |
| Client gửi username chứa newline/control character | Log không bị chèn dòng hoặc phá cấu trúc |
| Client gửi request ID quá dài hoặc giả mạo | Bị giới hạn/chuẩn hóa; không ghi đè correlation nội bộ |
| Logging sink tạm thời lỗi | Fallback/retry/alert theo policy; không mất audit event bắt buộc |
| Hai service cùng ghi decision | Event có service, route và trace context để phân biệt |
| User không có quyền đọc audit log | Truy vấn/export bị từ chối và được audit |
| Retention hết hạn | Log được xóa/ẩn danh theo policy và có bằng chứng tối thiểu |

Nên có test kiểm tra nội dung log bằng cách đưa token giả, cookie giả, email và chuỗi chứa CR/LF vào request rồi xác nhận chúng không xuất hiện trong output. Đồng thời kiểm tra schema event, enum, giới hạn độ dài, timestamp UTC, event ID và correlation fields.

## Những sai lầm thường gặp

- Chỉ ghi HTTP status mà không ghi loại authentication/authorization decision.
- Coi authentication success là authorization allow.
- Chỉ ghi DENY, bỏ qua các thao tác ALLOW nhạy cảm cần audit.
- Ghi nguyên JWT, Authorization header, cookie, password hoặc request body.
- Ghi exception message và policy expression tùy ý vào log.
- Dùng URL đầy đủ hoặc route chứa ID/PII thay vì route template.
- Cho client kiểm soát `decision`, `reasonCode`, `subjectRef` hoặc request ID nội bộ.
- Dùng text log nối chuỗi, không chống log injection.
- Gửi audit event vào cùng log file mà ứng dụng có quyền xóa/sửa không kiểm soát.
- Không giám sát log drop, collector lag hoặc queue đầy.
- Nhầm decision `ALLOW` với business operation đã commit thành công.
- Sampling mất các event thuộc yêu cầu audit bắt buộc.

## Checklist triển khai

- [ ] Có schema riêng cho authentication event và authorization decision event.
- [ ] Event có thời điểm UTC, event ID, service, route template và correlation ID.
- [ ] Authentication event ghi principal type, auth method và failure code chuẩn hóa.
- [ ] Authorization event ghi subject, action, resource type/reference, decision và reason code.
- [ ] Policy ID/version được ghi khi cần điều tra; không log policy expression hoặc secret.
- [ ] Phân biệt authentication, authorization decision và business audit event.
- [ ] Quy định rõ sự kiện ALLOW/DENY nào phải ghi đầy đủ và trường hợp nào được aggregate/sample.
- [ ] Không log token, cookie, password, key, raw payload hoặc PII ngoài nhu cầu được duyệt.
- [ ] Structured logging, validation và escaping ngăn log injection.
- [ ] Correlation ID được chuẩn hóa; trace ID và request ID không bị coi là credential.
- [ ] Security log được gửi an toàn, có access control, integrity protection và retention policy.
- [ ] Logging failure có fallback, retry, alert và chính sách cho thao tác audit-critical.
- [ ] Có alert cho brute force, resource enumeration, tenant mismatch và policy evaluation error.
- [ ] Có test cho allow/deny, log redaction, injection, pipeline failure, access control và retention.

Ghi authentication và authorization decision giúp API giải thích được ai đã được xác thực, ai được phép làm gì trên đối tượng nào và vì sao hệ thống cho phép hoặc từ chối. Khi event có schema ổn định, dữ liệu được tối thiểu hóa, log được bảo vệ và pipeline được giám sát, đội ngũ có thể điều tra sự cố và đánh giá hiệu quả phân quyền mà không biến hệ thống logging thành nơi lưu trữ credential hoặc dữ liệu nhạy cảm mới.
