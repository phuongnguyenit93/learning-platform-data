# Không ghi token, API key, password hoặc payload nhạy cảm

API log giúp vận hành, điều tra lỗi và phát hiện hành vi bất thường. Nhưng log cũng là một bản sao dữ liệu được tạo ra ở nhiều nơi: ứng dụng, API gateway, reverse proxy, load balancer, tracing agent, APM, message broker và SIEM. Nếu một request chứa bearer token, API key, password, OTP, dữ liệu cá nhân hoặc nội dung nghiệp vụ nhạy cảm, việc ghi nguyên request/response có thể biến hệ thống logging thành một kênh rò rỉ dữ liệu có phạm vi truy cập rộng và thời gian lưu dài.

Nguyên tắc thiết kế là **log những gì cần để hiểu sự kiện, không log bí mật hoặc toàn bộ payload để phòng khi cần**. Mặc định không ghi credential và request/response body. Dùng allowlist các trường metadata có mục đích rõ ràng, redaction theo cấu trúc tại mọi điểm thu thập, giới hạn quyền truy cập và thời gian lưu. Khi cần điều tra, correlation ID, principal/client ID đã kiểm soát, route template, action, outcome và reason code thường hữu ích hơn một bản sao nguyên vẹn của request.

Trong bảo mật API, logging phải được thiết kế theo endpoint, loại dữ liệu và luồng nghiệp vụ. Một endpoint đăng nhập, thanh toán, reset password, upload file hoặc export dữ liệu có rủi ro log khác endpoint health check. Chính sách cần bao phủ cả log ứng dụng và các hệ thống trung gian.

## 1. Vì sao log có thể trở thành nơi rò rỉ dữ liệu?

Một request có thể đi qua nhiều thành phần trước khi tới service:

~~~mermaid
flowchart LR
    A[Client] --> B[CDN / Load balancer]
    B --> C[API Gateway / Reverse proxy]
    C --> D[Application]
    D --> E[Database / Object storage]
    D --> F[Tracing / APM agent]
    B --> G[Access log]
    C --> H[Gateway log]
    D --> I[Application log]
    F --> J[Observability platform / SIEM]
    G --> J
    H --> J
    I --> J
~~~

Mỗi thành phần có thể ghi URL, header, body, exception hoặc span attributes. Tắt body logging trong application không giúp ích nếu proxy vẫn ghi query string chứa reset token, APM tự động thu thập Authorization header hoặc CDN lưu full URL.

Log thường được tập trung để nhiều nhóm cùng truy cập, được sao chép sang nhiều vùng, giữ lâu để phân tích xu hướng và có thể được tải xuống phục vụ hỗ trợ. Vì vậy, một secret lọt vào log có thể có phạm vi phơi lộ lớn hơn dữ liệu trong hệ thống nghiệp vụ ban đầu.

### 1.1. Những tình huống thường gây rò rỉ

- Access log ghi toàn bộ URL, trong khi query string có access token, API key, signed URL hoặc password reset token.
- HTTP filter ghi header Authorization, Cookie hoặc Set-Cookie.
- Debug middleware ghi toàn bộ JSON request/response, bao gồm password, OTP, thông tin thẻ hoặc hồ sơ khách hàng.
- Exception message chứa SQL statement, request URL có credential hoặc giá trị đầu vào nhạy cảm.
- APM agent tự động capture request body, header, SQL parameter hoặc local variable.
- Reverse proxy ghi header do client gửi hoặc forwarded header chứa định danh nhạy cảm.
- Job xử lý file log toàn bộ filename, nội dung trích xuất, OCR text hoặc metadata tài liệu.
- Log bị xuất sang ticket, chat, email hoặc dashboard có quyền truy cập rộng hơn service gốc.

## 2. Phân loại dữ liệu trước khi quyết định log

Không thể dùng một quy tắc “log mọi thứ rồi che password” cho mọi endpoint. Trước tiên, lập data inventory theo header, query parameter, body field, response field và metadata.

| Nhóm dữ liệu | Ví dụ | Quy tắc logging |
|---|---|---|
| Authentication secret | Password, bearer/access token, refresh token, API key, client secret | Không ghi giá trị |
| Session/anti-forgery secret | Cookie session, CSRF token, reset token, OTP, magic link | Không ghi giá trị |
| Payment data | PAN, CVV/CVC, PIN, payment credential | Không ghi payload; tuân thủ phạm vi PCI |
| Personal data | Email, phone, địa chỉ, ngày sinh, số định danh | Chỉ ghi khi có mục đích, giảm thiểu và bảo vệ phù hợp |
| Health/legal data | Hồ sơ sức khỏe, tài liệu pháp lý, nội dung tư vấn | Không ghi body; metadata tối thiểu theo policy |
| Business confidential | Hợp đồng, giá, giao dịch, nội dung ticket, dữ liệu khách hàng | Không ghi nguyên payload |
| File content | Bytes, OCR, transcript, ảnh, tài liệu | Không ghi nội dung |
| Operational metadata | Route template, method, status, duration, request ID | Có thể ghi theo schema |
| Security outcome | Auth failure, policy decision, rate limit event, reason code | Ghi metadata đủ điều tra, không ghi credential |

Phân loại nên được gắn với endpoint và schema, ví dụ POST /auth/login có password, POST /payments có payment data, POST /files có metadata và file bytes. Khi API thêm field mới, schema review phải đánh giá liệu field đó có được phép xuất hiện trong log hay không.

### 2.1. Secret có thể nằm ở nhiều vị trí

Đừng chỉ tìm field tên password. Secret thường xuất hiện trong:

- Header Authorization, Proxy-Authorization, Cookie, Set-Cookie.
- Query parameter như access_token, api_key, signature, code, token, reset, invite hoặc X-Amz-Signature.
- JSON field như password, secret, clientSecret, refreshToken, otp, verificationCode.
- Form field, multipart part, filename hoặc custom metadata.
- URL path chứa reset code hoặc invitation token.
- Exception, SQL bind parameter, tracing baggage hoặc message payload.
- Header do proxy/gateway thêm vào để mang identity hoặc credential nội bộ.

Đặt quy ước đặt tên cho secret fields và phân loại ngay từ schema. Tuy nhiên, không thể chỉ dựa vào tên field vì dữ liệu nhạy cảm có thể được đặt tên tùy ý hoặc nằm trong object lồng nhau.

## 3. Nguyên tắc logging an toàn

### 3.1. Data minimization

Chỉ ghi trường cần cho một mục đích đã xác định. Với một request API thông thường, các trường sau thường đủ:

- Timestamp.
- Request/correlation ID do server tạo hoặc đã xác thực định dạng.
- Service, environment và version.
- Route template và HTTP method.
- Status code, duration và response size.
- Principal ID hoặc client ID dạng định danh nội bộ đã được kiểm soát.
- Tenant ID nếu cần cho điều tra và được phép lưu.
- Action, policy result và reason code.
- Error category hoặc exception class.

Không ghi full URL nếu query string có thể chứa secret. Ưu tiên route template như /api/orders/{orderId} thay cho path cụ thể nếu ID có thể nhạy cảm. Không ghi toàn bộ body để có thể “replay request”; replay nên dùng test fixture hoặc một cơ chế capture riêng được phê duyệt, có kiểm soát và đã loại bỏ dữ liệu nhạy cảm.

### 3.2. Allowlist tốt hơn denylist

Một denylist kiểu “che field password, token, secret” dễ bỏ sót tên mới như credential, auth, key, otpValue, field lồng nhau hoặc dữ liệu nằm trong multipart. Với log body, nên mặc định không capture và chỉ cho phép một tập field metadata được định nghĩa rõ theo endpoint.

Ví dụ, endpoint tạo đơn hàng có thể chỉ log:

~~~json
{
  "event": "api.request.completed",
  "route": "/api/orders",
  "method": "POST",
  "status": 201,
  "requestId": "req_7f2d...",
  "principalId": "usr_42",
  "tenantId": "tenant_8",
  "itemCount": 3,
  "durationMs": 84
}
~~~

Không cần log địa chỉ giao hàng, nội dung ghi chú, thông tin thanh toán hoặc toàn bộ JSON order để hiểu rằng request tạo đơn thành công.

### 3.3. Redact trước khi dữ liệu rời khỏi process

Nếu có trường hợp ngoại lệ cần ghi một phần dữ liệu, redaction phải xảy ra trước khi gửi event sang console, file, agent, collector hoặc network sink. Không dựa vào một dashboard downstream để che dữ liệu sau khi log gốc đã được ghi.

Redaction cần được áp dụng ở mọi nơi có thể capture:

- Application logger và HTTP logging filter.
- API gateway, ingress, reverse proxy và CDN.
- APM/tracing agent và error reporting SDK.
- ORM/SQL logging và database proxy.
- Message broker, event consumer và job worker.
- Audit exporter, SIEM pipeline và support tooling.

Mỗi tầng có cấu hình riêng; phải kiểm tra log thực tế từ đầu đến cuối.

## 4. Không ghi credential trong header và cookie

### 4.1. Authorization

Không log giá trị của:

- Authorization: Bearer ...
- Authorization: Basic ...
- Proxy-Authorization.
- Custom header mang API key hoặc service token.

Nếu cần biết phương thức xác thực, log loại credential hoặc auth scheme, ví dụ authScheme=Bearer, clientId=service-billing, authResult=success. Không ghi token, kể cả token đã hết hạn.

Không ghi một phần token để “dễ debug” nếu phần đó vẫn có thể giúp nhận diện hoặc khôi phục credential. Dùng token ID (jti) hoặc internal credential record ID nếu hệ thống đã thiết kế chúng là identifier không bí mật và cho phép log.

### 4.2. Cookie và Set-Cookie

Không log raw Cookie hoặc Set-Cookie. Cookie session, remember-me, refresh cookie và CSRF cookie có thể là credential hoặc thông tin bảo mật. Nếu cần debug thuộc tính cookie, log metadata không chứa giá trị như cookie name, Secure, HttpOnly, SameSite, Path, Domain theo mức cần thiết.

Không ghi session ID. Nếu cần tương quan session, dùng một identifier nội bộ đã được pseudonymize bằng HMAC với secret quản lý riêng; không dùng hash thường của giá trị session làm giải pháp mặc định.

### 4.3. API key

API key thường được gửi qua header hoặc query string. Không log raw key, không log URL chứa key. Nếu key có public identifier và secret component riêng, chỉ log public key ID được thiết kế để nhận diện; không log secret component.

Nếu không có key ID riêng, tạo credential record ID trong hệ thống quản lý key. Khi key bị lộ qua log, phải coi như credential đã compromise: revoke/rotate, xác định log copies và giới hạn truy cập.

## 5. Không ghi secret trong URL và query string

URL thường được ghi tự động bởi access log, browser history, proxy, CDN và analytics. Vì vậy không truyền credential qua query string nếu có thể tránh.

Các ví dụ không an toàn:

~~~http
GET /api/report?access_token=eyJ...
GET /reset-password?token=one-time-secret
GET /download?signature=...
~~~

Dùng Authorization header hoặc cơ chế POST body phù hợp cho credential, nhưng vẫn không log header/body. Với signed URL bắt buộc dùng query signature, phải cấu hình access log, CDN, APM và referrer handling để loại bỏ query string hoặc redact đúng các tham số ký.

### 5.1. Log route thay cho full URL

Thay vì:

~~~text
GET /api/reset-password?token=abc123&email=person@example.test
~~~

Ghi:

~~~json
{
  "method": "GET",
  "route": "/api/reset-password",
  "status": 200,
  "requestId": "req_123"
}
~~~

Nếu cần biết loại flow, log event code như password_reset.page_requested, không ghi token hoặc email thô.

### 5.2. Path parameter cũng có thể chứa secret

Không phải chỉ query string mới nguy hiểm. Một số hệ thống đặt invitation token, reset code hoặc signed identifier trong path. Access log route template, không log raw path khi path segment có thể là secret hoặc dữ liệu cá nhân. Thiết kế API nên tránh đưa secret vào URL vì URL dễ bị lưu ở nhiều lớp.

## 6. Không ghi toàn bộ request/response payload

### 6.1. Body logging mặc định phải tắt

Request body có thể chứa password, OTP, dữ liệu thẻ, PII, thông tin hợp đồng, hồ sơ sức khỏe hoặc dữ liệu tenant. Response body có thể chứa dữ liệu riêng tư, token mới, signed URL hoặc kết quả export.

Không bật chế độ “log request and response body” ở production để debug tạm thời rồi quên tắt. Nếu thật sự cần payload capture cho một sự cố cụ thể, cần phê duyệt, giới hạn endpoint/user/time window, masking theo schema, mã hóa, quyền truy cập riêng và thời hạn xóa ngắn. Tắt capture ngay khi kết thúc.

### 6.2. Không dùng regex làm lớp bảo vệ duy nhất

Regex có thể bỏ sót:

- Field lồng nhau hoặc array.
- JSON với tên field viết hoa/thường khác nhau.
- Multipart form và file part.
- XML, GraphQL variables, protobuf hoặc định dạng custom.
- URL-encoded body và encoding bất thường.
- Nội dung nén, binary hoặc payload quá lớn.
- Secret nằm trong error message hoặc string tự do.

Nếu có nhu cầu log một phần payload, parse theo content type và schema cụ thể, chỉ trích xuất field được allowlist. Nếu parser không hiểu định dạng hoặc schema không rõ, bỏ payload khỏi log. Không fallback sang ghi raw body.

### 6.3. Multipart và file upload

Không ghi file bytes, base64, OCR text hoặc nội dung tài liệu. Filename có thể chứa tên khách hàng, mã hồ sơ hoặc dữ liệu nhạy cảm; chỉ log file ID nội bộ, loại file đã xác minh, kích thước, trạng thái scan và kết quả xử lý nếu cần.

Ví dụ metadata phù hợp:

~~~json
{
  "event": "file.upload.scanned",
  "fileId": "file_8f1...",
  "verifiedType": "application/pdf",
  "sizeBytes": 245812,
  "scanResult": "clean",
  "status": "AVAILABLE"
}
~~~

Không log storage path, signed URL, bucket credential hoặc file content. Với lỗi parser, log error code và file ID, không đưa đoạn trích nội dung vào exception log.

## 7. PII, payment data và dữ liệu nghiệp vụ

### 7.1. Personal data

Email, phone, địa chỉ, ngày sinh, IP address, device identifier và user identifier có thể là dữ liệu cá nhân tùy bối cảnh và luật áp dụng. Không phải trường nào cũng luôn bị cấm log, nhưng cần mục đích rõ, tối thiểu hóa, kiểm soát truy cập, retention và cơ sở xử lý phù hợp.

Khi cần tương quan user, ưu tiên internal user ID hoặc pseudonymous ID thay vì email/phone. Pseudonymization không biến dữ liệu thành vô danh tuyệt đối; vẫn phải bảo vệ và giới hạn sử dụng.

### 7.2. Payment data

Không ghi CVV/CVC, PIN, track data hoặc dữ liệu xác thực thanh toán nhạy cảm vào log. Với card number, áp dụng yêu cầu PCI DSS và chỉ lưu/hiển thị theo phạm vi được phép; không tự ý log PAN đầy đủ. Dùng payment transaction ID hoặc provider reference để điều tra thay cho dữ liệu thẻ.

### 7.3. Health, legal và business-confidential data

Không ghi nội dung hồ sơ sức khỏe, hợp đồng, ticket, chat, ghi chú khách hàng hoặc tài liệu pháp lý vào log vận hành. Log event metadata như document.uploaded, case.updated, payment.declined và reason code đã chuẩn hóa thường đủ để điều tra luồng.

Không tạo một trường details tự do rồi cho mọi service nhét dữ liệu vào. Trường tự do rất dễ trở thành nơi chứa payload hoặc secret mà schema không kiểm soát.

## 8. Thiết kế structured logging an toàn

Structured logging giúp định nghĩa schema và kiểm tra field rõ ràng hơn log text tự do. Một event có thể dùng các trường:

| Trường | Nội dung | Ghi chú |
|---|---|---|
| timestamp | Thời điểm UTC | Đồng bộ thời gian giữa service |
| service | Tên service | Không chứa secret |
| environment | dev/staging/prod | Tránh nhầm dữ liệu |
| event | Event name ổn định | Ví dụ api.request.completed |
| requestId | Correlation ID | Server sinh hoặc validate |
| traceId | Trace identifier | Không nhét token vào baggage |
| route | Route template | Không dùng full URL có query |
| method | HTTP method | Metadata |
| status | HTTP status | Metadata |
| durationMs | Thời gian xử lý | Metadata |
| principalId | Internal ID/pseudonymous ID | Chỉ ghi khi cần |
| clientId | OAuth/API client ID | Không phải client secret |
| tenantId | Tenant identifier | Theo policy dữ liệu |
| action | Business/security action | Ví dụ invoice.read |
| decision | allow/deny | Kết quả policy |
| reasonCode | Mã lý do chuẩn hóa | Không nhúng input thô |
| errorCode | Mã lỗi | Tránh exception message chứa payload |

Ví dụ event deny:

~~~json
{
  "timestamp": "2026-11-18T09:15:22Z",
  "service": "security-api",
  "environment": "production",
  "event": "authorization.denied",
  "requestId": "req_7f2d",
  "traceId": "4bf92f...",
  "route": "/api/files/{fileId}/content",
  "method": "GET",
  "status": 404,
  "principalId": "usr_42",
  "tenantId": "tenant_8",
  "action": "file.download",
  "decision": "deny",
  "reasonCode": "OBJECT_NOT_ACCESSIBLE",
  "durationMs": 12
}
~~~

Event này hỗ trợ điều tra mà không cần ghi file bytes, file name, access token hoặc raw ACL. Chọn 404 hay 403 theo chính sách chống enumeration; log nội bộ vẫn có thể lưu reason code chính xác hơn response công khai.

### 8.1. Dùng route template

Route template giảm việc ghi ID và tránh cardinality cao. Ví dụ /api/users/123456/orders/98765 nên được log là /api/users/{userId}/orders/{orderId}. Nếu ID là dữ liệu nhạy cảm hoặc cần điều tra object cụ thể, dùng internal resource ID đã được phê duyệt và chỉ trong security audit log có quyền truy cập chặt.

### 8.2. Correlation ID an toàn

Cho phép request ID do client gửi chỉ khi validate độ dài, ký tự và format; nếu không hợp lệ, tạo ID mới. Không dùng giá trị tùy ý của client làm log line hoặc MDC key mà không sanitize. Correlation ID không nên chứa email, token, session ID hoặc thông tin cá nhân.

Dùng traceId/spanId chuẩn để nối log và trace. Không đặt credential hoặc dữ liệu cá nhân vào tracing baggage vì baggage có thể được truyền qua nhiều service và exporter.

## 9. Exception, SQL và debug logging

Exception không tự động an toàn. Message có thể chứa URL đầy đủ, SQL bind values, request parameter, file path, email hoặc nội dung payload.

### 9.1. Ghi exception có kiểm soát

Ưu tiên ghi:

- Error code ổn định.
- Exception class.
- Service/operation và request ID.
- Policy decision hoặc dependency category.
- Stack trace trong log nội bộ có kiểm soát khi thực sự cần.

Tránh trả stack trace cho client. Tránh đưa raw exception message vào response hoặc log tập trung nếu message có thể chứa input nhạy cảm. Có thể map exception sang reason code và lưu chi tiết kỹ thuật đã sanitize ở sink hạn chế hơn.

### 9.2. SQL và ORM

Không bật SQL parameter logging trong production nếu parameter có thể chứa PII, password reset token hoặc dữ liệu nghiệp vụ. SQL statement có thể an toàn hơn parameter values nhưng vẫn có thể lộ schema, tenant ID hoặc query data. Dùng query ID, duration, row count và database error category.

Khi điều tra một query cụ thể, dùng trace/query identifier và môi trường test với dữ liệu giả. Nếu cần capture bind values trong tình huống ngoại lệ, phải có phạm vi, quyền và thời hạn rõ ràng.

### 9.3. Debug mode và verbose logging

Không bật debug/trace logging toàn cục trong production để điều tra nhanh. Một số thư viện ghi header/body hoặc internal object khi mức log tăng. Dùng cấu hình theo package/endpoint có thời hạn, kiểm tra nội dung thực tế và tự động hết hạn. Ghi nhận ai bật, lý do và thời điểm tắt.

## 10. Ví dụ Spring Boot: log metadata, không log body/header

Một filter có thể ghi nhận request metadata và response status/duration mà không đọc body hoặc dump header:

~~~java
@Component
public class SafeRequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        String requestId = requestIdFromTrustedContextOrGenerate(request);

        try {
            chain.doFilter(request, response);
        } finally {
            long durationMs =
                    (System.nanoTime() - started) / 1_000_000;

            log.info(
                    "api_request_completed requestId={} method={} route={} status={} durationMs={}",
                    requestId,
                    request.getMethod(),
                    routeTemplateFromHandler(request),
                    response.getStatus(),
                    durationMs
            );
        }
    }
}
~~~

Các hàm requestIdFromTrustedContextOrGenerate và routeTemplateFromHandler là phần tích hợp của ứng dụng; chúng phải validate input và trả route template, không trả raw URL/query. Ví dụ này cố ý không ghi Authorization, Cookie, header tùy ý hoặc request/response body.

### 10.1. Không để logging filter làm lộ body qua wrapper

Spring có các request/response wrapper hỗ trợ đọc lại body. Dùng wrapper không có nghĩa payload an toàn để log. Nếu filter cache body rồi ghi dump ở cuối request, secret vẫn bị lộ. Tránh capture body theo mặc định; nếu có use case cụ thể, phải trích xuất field theo schema allowlist và kiểm thử mọi content type.

### 10.2. MDC và context cleanup

MDC hữu ích để gắn request ID, trace ID hoặc principal ID vào log. Nhưng phải:

- Chỉ thêm giá trị đã validate và được phép log.
- Không thêm Authorization, cookie, raw email hoặc payload.
- Xóa MDC trong finally để tránh thread pool reuse làm lẫn context giữa request.
- Với async execution, truyền context qua cơ chế được kiểm soát và loại bỏ khi hoàn tất.
- Không copy toàn bộ request headers vào MDC.

Ví dụ:

~~~java
try {
    MDC.put("requestId", safeRequestId);
    MDC.put("principalId", safePrincipalId);
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
    MDC.remove("principalId");
}
~~~

Tên field và pseudonymous ID cần thống nhất giữa service; không đặt tenant/user metadata vào baggage hoặc MDC nếu log sink không được phép xử lý dữ liệu đó.

## 11. Redaction và kiểm tra schema

### 11.1. Xây dựng policy theo endpoint

Có thể quản lý policy theo operation:

| Endpoint | Dữ liệu có rủi ro | Log được phép |
|---|---|---|
| POST /auth/login | Password, username, MFA code | Client ID, auth result, reason code, request ID |
| POST /auth/token | Authorization code, client secret, access/refresh token | Client ID, grant type, outcome |
| POST /payments | PAN, CVV, payment token, billing details | Transaction ID, provider, amount band nếu được phép, outcome |
| POST /files | File bytes, filename, metadata | File ID, verified type, size, scan result |
| POST /password/reset | Reset token, email, new password | Flow ID, outcome, reason code |
| GET /users/{id} | PII và profile | Route, principal, policy outcome, response size |
| POST /exports | Query/filter và dữ liệu xuất | Export ID, requester, row count, status |

Bảng là ví dụ. Mỗi API cần được rà soát theo schema thật và data classification của tổ chức.

### 11.2. Redact theo cấu trúc

Nếu bắt buộc xử lý payload, parse theo định dạng và schema. Với JSON, cần xử lý key case-insensitive nếu contract cho phép, nested object, array và field alias. Với form/XML/GraphQL/protobuf, dùng parser tương ứng. Không parse thất bại rồi ghi raw payload như fallback.

Nếu schema không rõ, payload quá lớn, content type không hỗ trợ hoặc parser lỗi, bỏ payload khỏi log và ghi reason code như PAYLOAD_NOT_CAPTURED. Không ghi một phần bytes chưa được kiểm tra.

### 11.3. Không che bằng giá trị giả nhưng vẫn giữ secret gốc

Redaction phải thay giá trị trước khi serialize/log. Không tạo object log chứa raw secret rồi hy vọng encoder hoặc dashboard che sau. Tránh đưa secret vào exception hoặc diagnostic string trước khi redaction.

Có thể log authorizationPresent=true hoặc credentialType=Bearer thay vì token. Có thể log passwordFieldPresent=true nếu cần thống kê lỗi validation, nhưng không log giá trị hoặc độ dài password nếu không có mục đích bảo mật cụ thể.

## 12. Log injection và dữ liệu do client kiểm soát

Log injection xảy ra khi input do client kiểm soát chứa newline, ký tự điều khiển hoặc chuỗi được diễn giải như field/log record mới. Ví dụ username chứa ký tự xuống dòng và text giả admin login success có thể làm sai lệch điều tra nếu logger ghi raw string.

- Dùng structured logger với field encoding đúng.
- Không nối chuỗi input vào log line thủ công.
- Giới hạn độ dài và sanitize control characters cho các field được phép log.
- Không tin User-Agent, Referer, forwarded headers hoặc custom header.
- Không log raw query/path nếu có thể chứa control characters hoặc secret.
- Dùng enum/reason code thay cho free-form user input.
- Giữ escaping khi export JSON/CSV; kiểm soát CSV formula injection nếu log được mở bằng spreadsheet.

Sanitize không thay thế data minimization. Một email đã escape vẫn là email; một token đã URL-encode vẫn là token. Trước tiên quyết định có cần ghi field đó không.

## 13. Logging ở gateway, proxy, APM và tracing

Một chính sách chỉ có hiệu lực khi mọi lớp thu thập cùng tuân thủ.

### 13.1. API gateway và reverse proxy

Access log thường ghi method, path, query string, status, client IP, User-Agent và upstream timing. Cấu hình để:

- Ghi route template hoặc path đã bỏ query string.
- Không ghi Authorization, Cookie, API key hoặc request body.
- Redact query parameter có thể mang token/signature.
- Giới hạn header được ghi theo allowlist.
- Kiểm tra format log của error/denied request, không chỉ success.
- Không đưa header nội bộ chưa được xác minh vào log.

Nếu gateway có khả năng ghi toàn bộ request, tắt hoặc giới hạn theo policy. Kiểm tra cả log CDN/load balancer vì chúng có thể ghi URL trước khi request tới gateway.

### 13.2. APM và tracing agent

Nhiều agent có tính năng auto-instrumentation và capture request/response header, body, SQL statement, exception hoặc local variable. Kiểm tra cấu hình:

- Header capture chỉ allowlist metadata an toàn; loại bỏ Authorization, Cookie, Set-Cookie và API key.
- Tắt body capture cho endpoint nhạy cảm.
- SQL parameter capture tắt mặc định.
- Không thu thập local variables chứa secret.
- Không đưa token/PII vào span name, attributes, baggage hoặc event.
- Đặt sampling có chủ đích; sampling không làm payload an toàn.
- Kiểm tra exporter và vendor destination, quyền truy cập và retention.

### 13.3. Message broker và background worker

Log của producer/consumer có thể ghi message payload hoặc serialized object. Thay bằng event ID, message type, schema version, correlation ID, tenant reference đã được phê duyệt và outcome. Không ghi raw message nếu event chứa credential, PII hoặc dữ liệu nghiệp vụ.

Với dead-letter queue, tránh dump toàn bộ payload vào log khi xử lý lỗi. Lưu message trong vùng bảo vệ theo retention riêng nếu cần retry/forensics; log chỉ nên ghi message ID và error category.

## 14. Phân biệt operational log và security audit log

Operational log giúp theo dõi sức khỏe và lỗi của service. Security audit log ghi lại hành động quan trọng để trả lời ai đã làm gì, trên resource nào và kết quả ra sao. Hai loại log có mục đích, schema, quyền truy cập và retention khác nhau.

| Loại | Ví dụ | Nội dung nên có |
|---|---|---|
| Operational | Request hoàn tất, timeout, dependency lỗi | Route, status, duration, dependency, request ID |
| Security event | Login fail, permission denied, key revoked | Principal/client ID, action, outcome, reason code |
| Audit trail | Đổi role, đọc hồ sơ nhạy cảm, export, xóa file | Actor, resource ID, action, timestamp, approval/context |
| Diagnostic | Stack trace hoặc dependency details | Thông tin kỹ thuật đã sanitize, quyền hạn chế |

Audit log không cần chứa token hoặc payload để chứng minh hành động. Ví dụ một audit event file.download có thể ghi actor ID, file ID, tenant, policy decision, timestamp và request ID; không cần ghi bytes hoặc signed URL.

Đối với hành động trọng yếu, cần bảo đảm audit event được ghi bền vững và khó bị sửa/xóa bởi service account thông thường. Có thể dùng append-only storage, access separation, integrity control hoặc pipeline chuyên dụng. Không biến operational log thành audit trail duy nhất nếu nó có thể bị rotate, drop hoặc sửa bởi cùng workload.

## 15. Quyền truy cập, retention và bảo vệ log

Log không phải dữ liệu vô hại. Quản lý chúng như một tài sản có phân loại:

- Chỉ cấp quyền đọc theo vai trò và mục đích; developer không mặc nhiên cần đọc mọi production log.
- Tách quyền quản trị log, tìm kiếm, export và xóa.
- Mã hóa khi truyền và khi lưu.
- Audit việc truy vấn/export log, đặc biệt với security audit và dữ liệu nhạy cảm.
- Giới hạn retention theo mục đích, quy định và nhu cầu điều tra.
- Xóa/ẩn danh dữ liệu hết hạn trên cả bản sao, archive và downstream sink theo chính sách.
- Không gửi production log sang môi trường dev hoặc tài khoản cá nhân.
- Không đưa log vào ticket/chat công khai; nếu cần chia sẻ, tạo bản trích đã redact.
- Kiểm tra quyền nhà cung cấp APM/SIEM và vị trí lưu trữ dữ liệu.

Không giữ log vô thời hạn “phòng khi cần”. Retention quá dài làm tăng tác động nếu tài khoản log bị compromise. Retention quá ngắn lại làm mất khả năng điều tra; chọn thời hạn theo loại log, rủi ro và yêu cầu áp dụng.

### 15.1. Hash và pseudonymization

Hash email hoặc user ID không tự động làm dữ liệu vô danh. Hash không khóa có thể bị dò bằng dictionary. Nếu cần correlation mà không ghi định danh trực tiếp, cân nhắc HMAC với key riêng, quản lý trong secret manager, giới hạn người có quyền giải mã/tương quan và có kế hoạch rotation. Không dùng HMAC để tạo fingerprint cho password hoặc bearer token nếu không có yêu cầu được đánh giá cụ thể; ưu tiên credential ID/jti.

## 16. Xử lý khi phát hiện secret đã lọt vào log

Coi secret trong log là một sự cố credential/data exposure, không chỉ là lỗi formatting.

1. Xác định loại secret, endpoint, khoảng thời gian và các sink có thể đã nhận log.
2. Revoke/rotate credential còn hiệu lực: API key, access/refresh token, client secret, session hoặc reset token.
3. Xác định log index, archive, replica, export, APM trace, ticket và bản tải xuống bị ảnh hưởng.
4. Hạn chế quyền truy cập ngay; giữ bằng chứng cần thiết theo quy trình incident.
5. Xóa hoặc redact bản log theo chính sách retention/legal hold và khả năng của từng hệ thống.
6. Kiểm tra truy cập log bất thường, truy vấn/export và hành vi sử dụng credential sau thời điểm lộ.
7. Sửa nguồn ghi log ở application, gateway, proxy, APM hoặc worker; kiểm thử lại toàn tuyến.
8. Ghi nhận phạm vi, quyết định rotate, thời điểm thu hồi và kết quả khắc phục.

Không chỉ xóa một dòng log ở dashboard trong khi raw event vẫn còn trong archive hoặc SIEM. Cần kiểm tra mọi bản sao và downstream connector. Với dữ liệu cá nhân hoặc payment data, đánh giá nghĩa vụ thông báo và xử lý theo quy trình pháp lý/compliance của tổ chức.

## 17. Kiểm thử logging và redaction

Kiểm thử bằng secret giả có marker dễ tìm, ví dụ TEST_SECRET_DO_NOT_LOG_9f31. Gửi qua header, query, JSON, nested object, form, multipart và exception path. Sau đó tìm marker trong tất cả log sink.

| Nhóm test | Dữ liệu đưa vào | Kết quả mong đợi |
|---|---|---|
| Authorization header | Bearer test token | Không xuất hiện raw token |
| API key | Key giả trong header/query | Không có secret trong access/app/APM log |
| Cookie | Session và refresh cookie giả | Không log cookie value |
| Password | Login/reset payload | Không log password hoặc confirmation |
| OTP/reset | OTP, reset code, magic link | Không log code/token |
| Query signature | Signed URL query | Query bị loại hoặc signature được redact ở mọi proxy |
| Nested JSON | credentials.password, tokens.refresh | Không có giá trị nhạy cảm |
| Multipart | File bytes và filename nhạy cảm | Không log bytes; filename được bỏ/che theo policy |
| Exception | Exception message chứa test marker | Marker không xuất hiện trong log rộng |
| SQL parameter | Parameter chứa marker | Không capture bind value |
| APM/tracing | Header/body/baggage marker | Agent/exporter không thu thập marker |
| Log injection | CR/LF và JSON-like text trong input | Không tạo record giả hoặc phá cấu trúc |
| Unsupported content type | Binary/unknown payload | Bỏ payload, không fallback raw |
| Oversized body | Payload lớn | Không cache/log toàn bộ body |
| Async worker | Message có secret marker | Chỉ log message ID/type/outcome |
| Redaction failure | Parser/schema lỗi | Fail closed: bỏ payload, log reason code |
| Retention/access | User không có quyền tìm kiếm log | Truy vấn/export bị từ chối và được audit |

### 17.1. Kiểm tra cả log thành công và thất bại

Secret thường lọt vào log ở nhánh lỗi: validation exception, auth failure, downstream timeout, retry hoặc dead-letter. Chạy test cho success, 4xx, 5xx, timeout, retry và exception. Kiểm tra cả log trước/sau gateway và trace/APM, không chỉ file log của application.

### 17.2. Kiểm tra cấu hình thực tế

Đừng chỉ assert rằng một class redactor đã được đăng ký. Gửi request test qua đường triển khai tương tự production, rồi kiểm tra output ở từng sink. Cấu hình ở CDN, gateway, agent hoặc vendor có thể ghi dữ liệu trước khi redactor của application chạy.

## 18. Checklist trước khi phát hành

- [ ] Có data classification cho endpoint, header, query, body, response và file.
- [ ] Body logging tắt mặc định ở production.
- [ ] Authorization, API key, password, cookie, OTP, reset token và client secret không được ghi.
- [ ] Query string được bỏ hoặc redact; không đặt secret trong URL nếu có thể tránh.
- [ ] Không log file bytes, base64, OCR, transcript hoặc raw multipart payload.
- [ ] Dùng structured logging và allowlist field; không dựa riêng vào denylist/regex.
- [ ] Redaction chạy trước mọi sink và fail closed khi parse/schema lỗi.
- [ ] Route template được dùng thay raw path/full URL khi ID có thể nhạy cảm.
- [ ] Exception, SQL, APM, tracing, gateway, proxy và worker không capture secret.
- [ ] Input do client kiểm soát được encode/validate để chống log injection.
- [ ] Operational log và security audit log có schema, quyền và retention riêng.
- [ ] Log được mã hóa, giới hạn truy cập, audit truy vấn/export và có retention rõ.
- [ ] Có quy trình rotate/revoke và xử lý mọi bản sao khi secret lọt vào log.
- [ ] Có test marker qua success, failure, proxy, APM, async và mọi sink.

Logging an toàn không có nghĩa là bỏ hết thông tin quan sát. Hãy ghi event, route, principal/client đã kiểm soát, action, outcome, reason code, request ID và thời gian xử lý; giữ token, password, API key và payload nhạy cảm ngoài log. Khi mỗi endpoint có schema logging rõ ràng và mọi tầng thu thập cùng thực thi redaction, đội vận hành vẫn có thể theo dõi và điều tra API mà không tạo thêm một kho bí mật dễ bị khai thác.
