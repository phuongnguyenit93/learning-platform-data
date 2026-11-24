# Không log raw token

## 1. Vì sao không được ghi raw token vào log?

Access token, refresh token, ID token và token dùng trong các luồng exchange là dữ liệu xác thực có giá trị bảo mật. Với bearer token, bên nào lấy được bản sao token có thể thử sử dụng token trong thời gian hiệu lực. Nếu token xuất hiện trong application log, reverse proxy, API gateway, distributed trace, APM, crash dump hoặc ticket hỗ trợ, người đọc được dữ liệu đó có thể có khả năng mạo danh chủ thể hoặc dịch vụ.

**Không log raw token** nghĩa là không ghi toàn bộ token, một phần token có thể dùng lại, hay biểu diễn đã mã hóa của token vào bất kỳ hệ thống quan sát nào. Base64url decode JWT rồi log payload vẫn là làm lộ claim. Ghi `Authorization: Bearer ...`, cookie phiên, request body chứa `refresh_token` hoặc exception message có token cũng là rò rỉ.

Trong module bảo mật token, yêu cầu này áp dụng cho toàn bộ vòng đời token: phát hành, xác minh, sử dụng, exchange, refresh, introspection, thu hồi và xử lý lỗi. Mục tiêu vận hành là vẫn tìm được nguyên nhân lỗi, phát hiện hành vi bất thường và truy vết quyết định bảo mật mà không cần lưu credential.

Sau bài học, người học có thể:

- Nhận diện vị trí token có thể bị ghi ngoài ý muốn trong ứng dụng và hạ tầng.
- Thiết kế log có cấu trúc với trường dữ liệu allowlist, mã lý do và kết quả xác minh.
- Che hoặc loại bỏ header, cookie, body và exception có chứa token.
- Thiết kế metrics và distributed tracing không đưa token hoặc định danh nhạy cảm vào label/baggage.
- Phân biệt log vận hành với audit security event.
- Dùng fingerprint HMAC có kiểm soát khi thực sự cần đối chiếu sự kiện, không lưu raw token.
- Viết kiểm thử xác nhận token không xuất hiện trong log, trace, metric, response hay báo cáo lỗi.

## 2. Dữ liệu nào tuyệt đối không được log?

Các credential sau phải được loại khỏi log, trace, metric, event payload và hệ thống hỗ trợ:

| Dữ liệu | Ví dụ vị trí | Cách xử lý |
| --- | --- | --- |
| Access token | `Authorization: Bearer ...`, query hoặc body | Loại bỏ hoàn toàn |
| Refresh token | `refresh_token` trong token endpoint request/response | Loại bỏ hoàn toàn |
| ID token | `id_token` trong OIDC response | Loại bỏ hoàn toàn |
| Subject/actor token | `subject_token`, `actor_token` trong token exchange | Loại bỏ hoàn toàn |
| Session cookie | `Cookie`, `Set-Cookie` | Không ghi giá trị cookie |
| Client secret | Basic auth, form body, cấu hình hoặc exception | Loại bỏ và quản lý như secret |
| Client assertion | `client_assertion`, JWT assertion | Không ghi assertion |
| Authorization header | `Authorization`, proxy forwarded headers | Không ghi hoặc redact tại nguồn |
| Private key / signing material | File/key store, lỗi ký token | Không ghi key material |
| One-time code / device code | Authorization code, device code, reset code | Loại bỏ hoàn toàn |

Không log token dưới các dạng sau:

- Toàn bộ chuỗi JWT hoặc opaque token.
- JWT header/payload sau khi decode; payload có thể chứa subject, email, tenant, scope hoặc thông tin nhạy cảm.
- Prefix/suffix của bearer token với lý do “chỉ một phần”. Một phần token vẫn là dữ liệu credential và có thể giúp đối chiếu hoặc bị lạm dụng trong hệ thống yếu.
- Token đã Base64, URL encode, hex encode hoặc serialize.
- Toàn bộ request/response body của `/oauth2/token`, `/connect/token`, introspection, revocation hoặc callback OIDC.
- Exception message chứa input token, request URL hoặc header.
- Screenshot, trace export, crash report hay file đính kèm hỗ trợ có token.

**Redaction phải được thực hiện trước khi dữ liệu rời khỏi ranh giới tin cậy.** Xóa token sau khi đã gửi log tới collector không đủ, vì credential có thể đã được lưu trong buffer, queue, retry spool hoặc bản sao dự phòng.

## 3. Những nơi token thường lọt vào hệ thống quan sát

Token không chỉ xuất hiện trong câu lệnh logger. Nhiều thành phần tự thu thập request metadata hoặc lỗi.

| Thành phần | Nguy cơ | Kiểm soát cần có |
| --- | --- | --- |
| Application logger | Developer log request object, header hoặc exception | Logger allowlist; không log request/credential object |
| HTTP access log | Web server ghi toàn bộ header/query/body | Không capture Authorization, Cookie và query token |
| API gateway / reverse proxy | Access log ghi header được forward | Redact tại gateway và kiểm tra cấu hình log |
| APM agent | Auto-instrumentation capture request/response | Tắt capture header/body nhạy cảm; allowlist trường được phép |
| Distributed tracing | Span attributes, events hoặc baggage chứa token | Không gắn credential; scrub trước export |
| Metrics | Label chứa token, `jti`, subject hoặc email | Label có tập giá trị hữu hạn; không dùng credential làm label |
| Message broker | Payload event hoặc dead-letter message chứa token | Event chỉ mang metadata cần thiết; không phát tán token |
| Error tracker | Exception local variables, breadcrumbs, HTTP context | Scrub dữ liệu trước khi gửi; giới hạn local-variable capture |
| CI/CD và test report | Test thất bại in token fixture hoặc secret | Dùng token giả ngắn hạn; che output và bảo vệ artifact |
| Support ticket/chat | Người vận hành copy request lỗi | Cung cấp correlation ID và reason code, không yêu cầu gửi token |

Cần kiểm tra cả hệ thống phụ: log collector, SIEM, trace backend, object storage, backup, data lake, analytics export và quyền truy cập của nhà cung cấp APM. Một cấu hình an toàn ở ứng dụng có thể bị vô hiệu nếu proxy hoặc agent tự động ghi header.

## 4. Thiết kế log an toàn: allowlist thay vì blacklist

Cách an toàn là xác định **trường nào được phép ghi**, thay vì ghi mọi thứ rồi cố xóa các trường nguy hiểm. Blacklist thường bỏ sót tên trường mới, biến thể chữ hoa/thường, nested JSON hoặc dữ liệu trong exception.

Một security event phục vụ chẩn đoán có thể có cấu trúc:

```json
{
  "timestamp": "2026-11-23T10:30:00Z",
  "event": "access_token_validation",
  "outcome": "denied",
  "reason_code": "TOKEN_AUDIENCE_MISMATCH",
  "service": "orders-api",
  "environment": "staging",
  "route": "/api/orders/{orderId}",
  "issuer_alias": "corporate-idp",
  "audience_alias": "orders-api",
  "client_class": "backend-service",
  "correlation_id": "req-7f31c9",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "duration_ms": 4
}
```

Event trên có thể giúp tìm request và phân loại lỗi nhưng không chứa token. `issuer_alias` và `audience_alias` là tên cấu hình nội bộ đã được kiểm soát, không nhất thiết là giá trị tùy ý do token cung cấp. `route` dùng route template, không dùng URL đầy đủ nếu path/query có thể chứa dữ liệu nhạy cảm.

Các trường thường hữu ích nếu đã được duyệt:

- Thời điểm, service, môi trường và phiên bản ứng dụng.
- Tên event và kết quả `allowed`/`denied`/`error`.
- `reason_code` thuộc enum nội bộ.
- Route template, HTTP method và status code.
- Alias issuer/resource, loại token và phương thức xác thực.
- Client class hoặc client ID đã được phân loại theo chính sách.
- Correlation ID/trace ID do hệ thống tạo.
- Thời gian xử lý và phiên bản policy.
- Scope category hoặc permission decision nếu không làm lộ dữ liệu nhạy cảm.

Không ghi toàn bộ claim set. Chỉ ghi claim cụ thể nếu có nhu cầu vận hành rõ ràng, có đánh giá dữ liệu cá nhân và đã phê duyệt. `sub`, email, tenant, role, scope, `jti` và `client_id` có thể là dữ liệu nhạy cảm hoặc định danh có thể liên kết người dùng giữa nhiều hệ thống.

### 4.1. Mã lý do thay cho exception message

Thay vì ghi nguyên văn lỗi parser hoặc validator, chuyển lỗi sang mã nội bộ có tập giá trị hữu hạn:

| Reason code | Ý nghĩa |
| --- | --- |
| `TOKEN_MISSING` | Không có bearer credential |
| `TOKEN_MALFORMED` | Token không đúng định dạng |
| `TOKEN_SIGNATURE_INVALID` | Chữ ký không xác minh được |
| `TOKEN_ISSUER_UNTRUSTED` | Issuer không nằm trong trust configuration |
| `TOKEN_AUDIENCE_MISMATCH` | Audience không dành cho resource server |
| `TOKEN_EXPIRED` | Token đã hết hạn |
| `TOKEN_NOT_YET_VALID` | Token chưa tới thời điểm hiệu lực |
| `TOKEN_REVOKED` | Token/phiên đã bị thu hồi theo cơ chế đang dùng |
| `TOKEN_SCOPE_INSUFFICIENT` | Token hợp lệ nhưng thiếu quyền |
| `TOKEN_INTROSPECTION_UNAVAILABLE` | Không thể xác minh opaque token |
| `JWKS_UNAVAILABLE` | Không lấy được khóa xác minh |
| `TOKEN_TYPE_UNSUPPORTED` | Loại token không được endpoint chấp nhận |

Reason code không nên đưa nội dung đầu vào chưa kiểm tra vào tên event hoặc message. Có thể ghi exception class hoặc mã lỗi thư viện đã allowlist để hỗ trợ kỹ thuật; tránh ghi exception message nếu thư viện có thể nhúng token, URL, header hoặc claim vào đó.

## 5. Redact tại mọi lớp HTTP

### 5.1. Authorization header và cookie

Các header sau phải được loại bỏ hoặc thay bằng marker cố định trước khi log:

```text
Authorization
Proxy-Authorization
Cookie
Set-Cookie
X-Api-Key
X-Auth-Token
```

Không ghi header theo kiểu “chỉ che phần lớn” nếu phần còn lại vẫn là token. Marker an toàn có thể là `[REDACTED]`, hoặc bỏ hẳn trường. Không dùng một regex đơn giản làm lớp bảo vệ duy nhất: header có thể viết hoa/thường khác nhau, có nhiều giá trị, bị nối dòng hoặc được capture ở một tầng khác.

### 5.2. Query string và request body

Không đặt access token trong query string. URL thường được ghi vào browser history, proxy access log, analytics, referrer và monitoring. Nếu API cũ buộc phải nhận token trong query, cần loại tham số đó trước khi log và lập kế hoạch loại bỏ cách truyền này.

Không log form body của token endpoint. Các trường nhạy cảm thường gặp:

```text
access_token
refresh_token
id_token
subject_token
actor_token
client_secret
client_assertion
code
device_code
```

Không nên log toàn bộ body rồi dùng regex thay giá trị. JSON có thể nested, form encoding có thể biến đổi, và response có thể chứa nhiều loại token. Cách tốt là không bật body capture cho endpoint xác thực; nếu cần chẩn đoán, ghi metadata đã allowlist như grant type, client alias, kết quả và reason code.

### 5.3. Reverse proxy và API gateway

Ví dụ Nginx access log chỉ ghi thông tin request đã chọn, không ghi `$http_authorization`, `$http_cookie`, query string đầy đủ hoặc body:

```nginx
log_format safe_api
    '$time_iso8601 '
    'request_id=$request_id '
    'method=$request_method '
    'route_class=$uri '
    'status=$status '
    'request_time=$request_time';

access_log /var/log/nginx/safe_api.log safe_api;
```

`$uri` vẫn cần được đánh giá nếu ứng dụng có token hoặc dữ liệu nhạy cảm trong path. Không dùng `$request` hoặc `$request_uri` một cách mặc định khi query string có thể chứa credential. Cấu hình cụ thể phải được kiểm thử trên phiên bản proxy đang triển khai.

Ở API gateway, tạo policy redaction cho mọi header nhạy cảm trước khi ghi access log và trước khi export telemetry. Kiểm tra cả log của request vào lẫn response ra; token endpoint có thể trả access token trong response body.

## 6. Distributed tracing và APM không được mang token

Trace giúp nối request qua gateway, resource server, authorization server và các service downstream. Tuy nhiên, span attributes và baggage thường được export sang nhiều hệ thống và giữ lâu hơn log ứng dụng.

Quy tắc:

1. Không đưa raw token, refresh token, cookie, authorization header hoặc toàn bộ JWT payload vào span attribute, event hay baggage.
2. Không dùng token làm trace ID, span ID hoặc correlation ID.
3. Không capture request/response body của token endpoint.
4. Không bật auto-capture toàn bộ HTTP header; dùng allowlist header an toàn như `traceparent` và request ID.
5. Không đưa `sub`, email, `jti` hoặc `client_secret` vào baggage.
6. Kiểm tra exporter, collector processor, tail sampling và backend vì dữ liệu có thể bị thêm ở các tầng này.
7. Trước khi export, áp dụng scrubber như lớp phòng thủ bổ sung, nhưng vẫn chặn capture ngay từ nguồn.

Một span an toàn có thể ghi:

```json
{
  "name": "oauth.token.validation",
  "attributes": {
    "auth.token_type": "access_token",
    "auth.validation.outcome": "denied",
    "auth.validation.reason": "TOKEN_EXPIRED",
    "server.route": "/api/orders/{orderId}",
    "http.request.method": "GET"
  }
}
```

Tên attribute nên theo convention nội bộ hoặc semantic conventions đang sử dụng. Không thêm `enduser.id` hoặc định danh cá nhân nếu không có lý do và chính sách dữ liệu phù hợp. Nếu cần correlation giữa các service, dùng trace ID/correlation ID ngẫu nhiên do hệ thống tạo.

## 7. Metrics: đo hành vi, không định danh token

Metrics cần giúp trả lời các câu hỏi vận hành:

- Bao nhiêu lần xác minh token thành công/thất bại?
- Lý do từ chối nào tăng đột biến?
- Độ trễ xác minh JWT hoặc introspection thay đổi ra sao?
- JWKS endpoint có lỗi hoặc refresh bất thường không?
- Refresh/revocation/token exchange có tỷ lệ lỗi tăng không?

Ví dụ metric có label hữu hạn:

```text
token_validation_total{
  service="orders-api",
  token_type="jwt_access",
  outcome="denied",
  reason="audience_mismatch"
}

token_validation_duration_seconds{
  service="orders-api",
  token_type="jwt_access"
}

jwks_fetch_total{
  issuer_alias="corporate-idp",
  outcome="error"
}

token_exchange_total{
  client_class="backend_service",
  outcome="denied",
  reason="unauthorized_client"
}
```

Không đưa các giá trị sau vào metric label:

- Raw token, token fingerprint hoặc `jti`.
- `sub`, email, username hoặc session ID.
- Request ID, trace ID hoặc correlation ID.
- URL có path parameter chứa ID người dùng/tài nguyên.
- Claim hoặc reason text tùy ý do client gửi.

Các label có cardinality cao làm tăng chi phí lưu trữ và có thể khiến hệ thống monitoring mất ổn định. Với client, issuer hoặc audience, ưu tiên alias/nhóm đã giới hạn. Nếu cần xem một client cụ thể, dùng log/audit có kiểm soát thay vì biến mỗi định danh thành time series.

## 8. Có cần token fingerprint để đối chiếu sự kiện không?

Thông thường **không cần lưu bất kỳ phần nào của token**. Correlation ID và trace ID đủ để nối các sự kiện của cùng một request. Nếu có yêu cầu điều tra đặc biệt cần biết hai sự kiện có liên quan đến cùng một credential hay không, có thể cân nhắc fingerprint dẫn xuất bằng HMAC, nhưng đây là ngoại lệ cần được phê duyệt.

Không dùng hash thuần như `SHA-256(token)` làm mặc định. Với token entropy cao, hash không trực tiếp tiết lộ token, nhưng fingerprint ổn định có thể liên kết hành vi và trở thành định danh theo dõi. HMAC dùng khóa bí mật riêng giúp người không có khóa không tự tính fingerprint từ token đoán được.

Ví dụ Java minh họa:

```java
String tokenFingerprint(String token, SecretKey hmacKey) {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(hmacKey);

    byte[] digest = mac.doFinal(token.getBytes(StandardCharsets.UTF_8));
    byte[] shortDigest = Arrays.copyOf(digest, 8);

    return HexFormat.of().formatHex(shortDigest);
}
```

Nếu dùng fingerprint:

- Chỉ tạo trong bộ nhớ; không lưu token gốc hoặc digest đầy đủ nếu không cần.
- Dùng HMAC key riêng cho telemetry, không dùng signing key hoặc encryption key của token.
- Phân tách khóa theo môi trường và cân nhắc xoay khóa để giảm khả năng liên kết dài hạn.
- Chỉ giữ fingerprint rút gọn khi đánh giá va chạm và nhu cầu điều tra cho phép.
- Giới hạn quyền đọc trường này, thời gian lưu và mục đích sử dụng.
- Không dùng fingerprint làm metric label, user ID hoặc khóa tra cứu phổ biến.
- Không coi fingerprint là biện pháp xác thực hay bằng chứng token hợp lệ.

Nếu mục tiêu chỉ là tìm request, hãy dùng correlation ID. Không thêm fingerprint chỉ vì có thể làm được.

## 9. Audit security event khác application log

Application log hỗ trợ chẩn đoán lỗi và hiệu năng. Audit log ghi nhận quyết định hoặc hành động bảo mật có ý nghĩa, ví dụ:

- Token được cấp, refresh, exchange hoặc thu hồi.
- Client authentication thành công/thất bại.
- Resource server từ chối token do issuer, audience, chữ ký hoặc thời hạn.
- Quyền bị từ chối do thiếu scope hoặc tenant mismatch.
- Phát hiện refresh token reuse hoặc sender constraint thất bại.
- Thay đổi signing key, issuer trust configuration hoặc policy.

Audit event nên ghi ai/ứng dụng nào thực hiện hành động, hành động gì, trên resource nào, kết quả ra sao và theo policy version nào. Dùng định danh nội bộ hoặc pseudonym khi phù hợp; không ghi token.

Ví dụ:

```json
{
  "event": "oauth.token_revocation",
  "event_time": "2026-11-23T10:40:00Z",
  "actor_type": "oauth_client",
  "actor_alias": "mobile-backend",
  "subject_ref": "pseudonym:8f1c...",
  "action": "revoke_refresh_token",
  "decision": "success",
  "reason_code": "USER_LOGOUT",
  "policy_version": "revocation-policy-4",
  "correlation_id": "req-a902"
}
```

Audit pipeline nên có quyền ghi tách biệt, kiểm soát sửa/xóa, đồng bộ thời gian, retention và khả năng phát hiện chỉnh sửa. Không mặc định application log thông thường đáp ứng yêu cầu audit. Ngược lại, audit log cũng không nên chứa quá nhiều claim hoặc thông tin cá nhân chỉ để thuận tiện tra cứu.

## 10. Ví dụ triển khai log an toàn trong Java

### 10.1. Log event theo allowlist

Ví dụ sau dùng SLF4J để ghi các trường đã chọn. Hàm nhận kết quả xác minh và metadata đã chuẩn hóa; nó không nhận raw token:

```java
void logTokenDecision(
        String service,
        String routeTemplate,
        String issuerAlias,
        String outcome,
        TokenFailureReason reason,
        String correlationId,
        long durationMs) {

    log.info(
        "event=token_validation service={} route={} issuer={} " +
        "outcome={} reason={} correlation_id={} duration_ms={}",
        safeLabel(service),
        safeRoute(routeTemplate),
        safeLabel(issuerAlias),
        safeOutcome(outcome),
        reason.name(),
        safeCorrelationId(correlationId),
        durationMs
    );
}
```

`safeLabel`, `safeRoute` và `safeCorrelationId` cần giới hạn độ dài, ký tự và nguồn dữ liệu. `reason` là enum nội bộ, không phải chuỗi tùy ý từ token hoặc request. Không truyền `HttpServletRequest`, `Authentication`, `Jwt`, `OAuth2AuthenticationException` hay object request vào logger vì `toString()` có thể chứa dữ liệu nhạy cảm.

### 10.2. Không log exception message chứa token

Không làm như sau:

```java
catch (JwtException ex) {
    log.warn("JWT rejected: {}", ex.getMessage());
}
```

Nếu message hoặc nested cause chứa chuỗi token/claim, credential có thể bị ghi ra. Thay vào đó, ánh xạ sang reason code đã định nghĩa:

```java
catch (JwtException ex) {
    TokenFailureReason reason = classifyJwtFailure(ex);

    log.warn("event=token_validation outcome=denied reason={}",
             reason.name());

    throw new InvalidBearerTokenException("Invalid access token");
}
```

`classifyJwtFailure` chỉ nên đọc loại lỗi đã được kiểm soát và trả enum hữu hạn; không đưa message gốc vào log hoặc response. Không ghi stack trace nếu chưa đánh giá thư viện và exception chain có thể chứa token. Có thể gửi exception class hoặc mã lỗi an toàn tới metric để phân loại lỗi kỹ thuật.

### 10.3. Redaction filter là lớp phòng thủ bổ sung

Có thể cấu hình logging framework hoặc telemetry processor để xóa header nhạy cảm. Tuy nhiên, đây không phải lý do để application code log toàn bộ request. Filter có thể bị bỏ qua bởi logger khác, async appender, proxy hoặc agent.

Thiết kế đúng là:

1. Application chỉ ghi trường allowlist.
2. HTTP server/gateway không capture credential headers/body.
3. APM agent chỉ capture header được phép.
4. Collector áp dụng redaction lần cuối trước khi export/lưu.
5. Test kiểm tra cả dữ liệu ở nguồn lẫn dữ liệu cuối cùng tại backend telemetry.

## 11. Kiểm thử xác nhận không rò rỉ token

Một yêu cầu “không log raw token” phải có test tự động. Đừng chỉ review code và tin rằng developer sẽ không thêm log nguy hiểm sau này.

### 11.1. Test application log

Tạo một token test có marker dễ tìm, ví dụ `TEST-RAW-TOKEN-DO-NOT-LOG-...`, gửi qua request hợp lệ và request bị từ chối. Thu thập log output của ứng dụng rồi xác nhận:

- Raw token không xuất hiện.
- Không có prefix/suffix hoặc encoded representation của token.
- Không có `Authorization` header hay cookie.
- Không có payload claim nhạy cảm nếu policy cấm log.
- Reason code, correlation ID và outcome vẫn có thể dùng để chẩn đoán.

Pseudocode JUnit:

```java
@Test
void neverWritesRawBearerTokenToApplicationLogs() throws Exception {
    String rawToken = "TEST-RAW-TOKEN-DO-NOT-LOG-7f31";
    logCapture.clear();

    performRequestWithBearer(rawToken);

    String output = logCapture.formattedMessages();

    assertThat(output).doesNotContain(rawToken);
    assertThat(output).doesNotContain("Authorization");
    assertThat(output).contains("event=token_validation");
    assertThat(output).contains("correlation_id=");
}
```

Đây là ví dụ về cách tổ chức test; `logCapture` và `performRequestWithBearer` là fixture của dự án. Dùng token giả có marker, không dùng credential thật. Nếu hệ thống encode hoặc transform token, test nên kiểm tra các dạng chuyển đổi đã biết và không chỉ tìm một chuỗi duy nhất.

### 11.2. Test proxy, APM và trace export

Ở tầng tích hợp, gửi marker token qua gateway và xác minh marker không xuất hiện trong:

- Access log proxy/API gateway.
- Application log.
- Span attributes, span events và baggage.
- APM error report/breadcrumb.
- Metric label hoặc exemplar.
- Dead-letter queue hoặc event payload nếu request có phát sinh message.

Nên kiểm tra cả đường thành công lẫn thất bại, token endpoint request/response, exception và retry. Dữ liệu phải được kiểm tra tại nơi lưu cuối cùng, vì redaction ở ứng dụng có thể bị tầng khác ghi lại.

### 11.3. Kiểm thử redaction và field-name biến thể

Bổ sung các trường hợp header viết hoa/thường khác nhau và nested body:

```json
{
  "request": {
    "headers": {
      "authorization": "Bearer TEST-RAW-TOKEN"
    },
    "body": {
      "refresh_token": "TEST-REFRESH-TOKEN",
      "client_assertion": "TEST-ASSERTION"
    }
  }
}
```

Redaction phải xử lý tên trường theo quy tắc không phân biệt hoa/thường nếu giao thức cho phép, và không phụ thuộc vào một tên JSON duy nhất. Đồng thời, test phải chứng minh các trường không nhạy cảm cần cho vận hành vẫn còn, tránh scrub toàn bộ event làm mất khả năng chẩn đoán.

## 12. Phản ứng khi phát hiện token đã lọt vào log

Nếu raw token xuất hiện trong log hoặc trace, coi đó là một sự cố lộ credential, không chỉ là lỗi format log.

Các bước xử lý cần phối hợp theo incident response policy:

1. Xác định loại token, issuer, audience, subject/client liên quan và khoảng thời gian bị lộ mà không copy token sang thêm hệ thống.
2. Hạn chế quyền truy cập log/trace chứa token và ngăn export hoặc chia sẻ tiếp.
3. Đánh giá khả năng token còn hiệu lực, nơi lưu, bản sao, retention, backup và ai có quyền đọc.
4. Thu hồi token/refresh token hoặc phiên liên quan theo khả năng của authorization server; cân nhắc revoke token family khi refresh token reuse/lộ.
5. Nếu token không thể thu hồi tức thời, áp dụng biện pháp giảm thiểu theo risk policy, ví dụ vô hiệu phiên, denylist hoặc rút ngắn trust window.
6. Xử lý bản sao trong log backend, index, queue, export và backup theo quy trình xóa/retention có kiểm soát; không tự xóa bằng cách làm mất bằng chứng điều tra.
7. Vá nguồn phát sinh, bổ sung test chống tái diễn và xác minh redaction trên toàn pipeline.
8. Ghi audit incident bằng metadata an toàn, không đính kèm raw token.

Không dán token bị lộ vào ticket, chat hoặc công cụ phân tích để nhờ người khác xác minh. Dùng correlation ID, timestamp, service, reason code và token reference đã được bảo vệ theo quy trình.

## 13. Checklist review observability cho token

- [ ] Không ghi raw access token, refresh token, ID token, subject token hoặc actor token.
- [ ] Không ghi Authorization, Proxy-Authorization, Cookie hoặc Set-Cookie.
- [ ] Token endpoint không capture form body hoặc response body.
- [ ] Query string và URL path được kiểm soát, không mang credential.
- [ ] Exception message, stack trace và error tracker không chứa token/claim nhạy cảm.
- [ ] APM/tracing chỉ capture header allowlist; không có token trong span/baggage.
- [ ] Metrics không dùng token, `jti`, subject, email, request ID hoặc trace ID làm label.
- [ ] Log dùng field allowlist, reason code hữu hạn và route template.
- [ ] Audit event tách biệt, có quyền truy cập/retention phù hợp và không lưu credential.
- [ ] Fingerprint HMAC chỉ dùng khi có yêu cầu được duyệt; không dùng hash thuần hoặc metric label.
- [ ] Test marker token trên application log, gateway, trace, APM và backend telemetry.
- [ ] Có quy trình xử lý credential exposure và thu hồi token khi phát hiện rò rỉ.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao không được log JWT payload dù payload không phải phần chữ ký?**

Payload chứa claim và thông tin định danh; nó có thể tiết lộ dữ liệu người dùng, tenant, scope hoặc ngữ cảnh xác thực. Việc decode không loại bỏ tính nhạy cảm của dữ liệu.

**2. Có thể log 8 ký tự cuối của access token để debug không?**

Không nên. Phần token vẫn là dữ liệu credential và có thể hỗ trợ đối chiếu hoặc bị lạm dụng. Hãy dùng correlation ID; nếu thật sự cần nhận diện cùng credential, đánh giá fingerprint HMAC có kiểm soát.

**3. Vì sao cần redaction ở gateway và APM nếu ứng dụng đã không log token?**

Gateway và APM có thể tự động capture HTTP header/body trước hoặc sau khi request vào ứng dụng. Kiểm soát chỉ ở application logger không bảo vệ các bản sao đó.

**4. Có nên đưa `sub` hoặc `jti` vào metric label không?**

Không. Chúng tạo cardinality cao và có thể liên kết hành vi với người dùng hoặc token. Metrics nên dùng nhóm hữu hạn như outcome, reason code, token type và issuer alias.

**5. Khi phát hiện raw token trong log, chỉ cần xóa dòng log có đủ không?**

Không. Cần đánh giá bản sao, quyền truy cập, khả năng token còn hiệu lực, thu hồi credential, xử lý backup/export và sửa nguồn phát sinh.

**6. Application log và audit log khác nhau thế nào?**

Application log phục vụ vận hành và chẩn đoán. Audit log ghi lại hành động/quyết định bảo mật có ý nghĩa, có kiểm soát tính toàn vẹn, quyền truy cập và retention riêng. Cả hai đều không được chứa raw token.

## Tài liệu chuẩn tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi log, bảo vệ log và kiểm soát truy cập.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý, truy cập và vòng đời secret.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token, cách truyền token và rủi ro lộ credential.
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và các claim.
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo mật OAuth 2.0 hiện đại.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): truyền trace context giữa các hệ thống.
- [OpenTelemetry – Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): quản lý dữ liệu nhạy cảm trong telemetry pipeline.

