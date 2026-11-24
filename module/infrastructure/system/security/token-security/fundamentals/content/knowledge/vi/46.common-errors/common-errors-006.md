# Lỗi ghi log Authorization header

## 1. Vì sao không được ghi Authorization header?

HTTP request thường mang credential trong header `Authorization`. Với Bearer access token, giá trị có thể là:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.<claims>.<signature>
```

Bất kỳ ai lấy được Bearer token đều có thể sử dụng token trong phạm vi và thời hạn mà Resource Server chấp nhận. Nếu ứng dụng ghi toàn bộ header vào log, log aggregation, APM, trace, terminal CI hoặc ticket hỗ trợ có thể trở thành nơi lưu credential có thể tái sử dụng. Kẻ tấn công không cần phá chữ ký JWT; chỉ cần lấy token còn hiệu lực và gửi lại request.

Rủi ro không chỉ áp dụng cho `Bearer`. `Authorization: Basic ...` có thể chứa client ID và client secret hoặc thông tin xác thực khác. Một số hệ thống còn dùng scheme riêng hoặc cơ chế xác thực proxy. Vì vậy, quy tắc an toàn là **không ghi giá trị của Authorization header vào log**. Hãy xem toàn bộ giá trị header là dữ liệu nhạy cảm, bất kể scheme hay định dạng token.

Trong module token security, lỗi này liên quan trực tiếp đến lưu trữ và bảo vệ access token, refresh token, client credential và chống token bị đánh cắp hoặc phát lại. Token được bảo vệ tốt trong database nhưng bị ghi vào log vẫn có thể bị lộ qua một đường khác.

## 2. Những nơi Authorization header thường bị ghi ngoài ý muốn

Lỗi thường xuất hiện khi bật debug hoặc ghi toàn bộ request để tìm lỗi tích hợp. Cần rà soát tất cả tầng có thể nhìn thấy request, không chỉ logger trong controller.

| Thành phần | Cách credential có thể bị ghi | Biện pháp kiểm soát |
| --- | --- | --- |
| Application filter/interceptor | Ghi toàn bộ header hoặc serialize request object | Chỉ log metadata được allowlist; không đọc/ghi giá trị Authorization. |
| API Gateway / reverse proxy | Access log tùy biến chứa request header | Bỏ header nhạy cảm khỏi log format; kiểm tra cấu hình thực tế. |
| HTTP client logging | Wire logger ghi request/response header khi debug | Tắt header/body logging nhạy cảm hoặc dùng redaction có kiểm thử. |
| APM / distributed tracing | Agent tự thu thập HTTP headers hoặc span attributes | Cấu hình denylist/allowlist ở agent và backend; xác minh trace export. |
| Exception handler | Gắn request headers hoặc request dump vào exception | Chỉ ghi mã lỗi, route và correlation ID; không đính kèm request thô. |
| Audit/security event | Lưu toàn bộ context request để điều tra | Chỉ lưu quyết định, loại credential và định danh sự kiện cần thiết. |
| CI/CD và test report | In request khi test thất bại | Dùng credential giả; lọc output và artifact; không dump header. |
| Support bundle / diagnostic dump | Thu thập cấu hình và request gần nhất | Có bộ lọc trước khi export; giới hạn quyền và thời hạn lưu. |

Header name trong HTTP không phân biệt chữ hoa/chữ thường. Bộ lọc phải nhận diện `Authorization`, `authorization` và các biến thể casing tương đương. Cũng cần kiểm tra header có nhiều giá trị, wrapper request, proxy header và các tên credential khác như `Proxy-Authorization`.

## 3. Vì sao token trong log nguy hiểm?

### 3.1. Bearer token có thể bị replay

Bearer token được sử dụng bằng cách gửi token trong request. Người có token có thể gửi lại token tới Resource Server trước khi token hết hạn hoặc bị thu hồi. JWT có chữ ký hợp lệ không giúp ngăn replay nếu token bị đánh cắp; chữ ký chỉ xác minh nguồn phát hành và tính toàn vẹn của nội dung.

Ví dụ log không an toàn:

```text
2026-11-23 INFO Incoming request headers={
  "Authorization": "Bearer eyJ...sensitive-token-value..."
}
```

Log có thể được sao chép tới nhiều nơi: hệ thống tập trung, bản sao lưu, dashboard, email cảnh báo, công cụ tìm kiếm và máy của người vận hành. Xóa log ở ứng dụng không bảo đảm mọi bản sao đã biến mất.

### 3.2. Basic credentials cũng là bí mật

`Authorization: Basic ...` chứa chuỗi Base64 của thông tin xác thực; Base64 không phải mã hóa bảo mật. Nếu header bị log, người đọc log có thể giải mã thành credential gốc. Tùy hệ thống, credential này có thể là client secret hoặc username/password.

### 3.3. Log có thể có quyền truy cập rộng hơn hệ thống token

Một đội hỗ trợ hoặc developer có thể được cấp quyền đọc log để xử lý lỗi mà không được cấp quyền gọi API production. Khi log chứa token, quyền đọc log vô tình trở thành quyền sử dụng token. Thời gian lưu log dài cũng có thể vượt xa thời hạn access token, làm tăng bề mặt rủi ro nếu log chứa refresh token hoặc credential dài hạn.

### 3.4. Redaction muộn không xóa được bản sao cũ

Nếu APM đã nhận header trước khi áp dụng masking ở backend, token có thể đã được lưu trong raw event hoặc buffer. Redaction phải diễn ra càng sớm càng tốt, trước khi dữ liệu rời khỏi process/proxy có quyền nhìn thấy header. Cần kiểm tra cả raw ingestion, exporter, queue, retry buffer và bản sao lưu.

## 4. Nguyên tắc thiết kế log an toàn

Ưu tiên **allowlist**: chỉ ghi những trường đã được xác định là an toàn. Cách ghi toàn bộ header rồi cố che một số tên nhạy cảm dễ bỏ sót header mới, alias, casing khác hoặc dữ liệu nằm trong body/query.

Thông tin thường có thể log nếu chính sách nội bộ cho phép:

- HTTP method và route template, ví dụ `GET /v1/orders/{orderId}` thay vì URL chứa dữ liệu nhạy cảm.
- Status code, latency, tên service, environment và region.
- Correlation ID hoặc trace ID được tạo/kiểm soát, không lấy token làm ID.
- Kết quả xác thực ở dạng tổng quát như `authenticated=true/false` hoặc `auth_result=denied`.
- Loại scheme ở mức phân loại nếu thực sự cần, ví dụ `auth_scheme=bearer`; không ghi phần credential sau scheme.
- Mã lỗi đã chuẩn hóa như `invalid_token`, `insufficient_scope` hoặc `authentication_failed`, tránh thông báo lỗi tùy ý có thể chứa dữ liệu request.

Không log:

- Giá trị đầy đủ hoặc một phần của `Authorization` và `Proxy-Authorization`.
- Access token, refresh token, ID token, JWT, opaque token hoặc authorization code.
- Client secret, password, private key, client assertion hoặc credential của service account.
- Cookie phiên, session ID hoặc header có khả năng tái sử dụng để xác thực.
- Raw request/response body của token endpoint có chứa `client_secret`, `refresh_token`, `code_verifier`, `assertion` hoặc token.
- Query string nếu ứng dụng có thể nhận `access_token` hoặc dữ liệu xác thực trong URL.

Không log token dưới dạng prefix/suffix, ví dụ 8 ký tự đầu hoặc cuối. Phần token bị cắt vẫn có thể hỗ trợ tương quan, dò đoán hoặc tiết lộ cấu trúc. Nếu có yêu cầu nghiệp vụ đặc biệt cần tương quan token, phải có thiết kế riêng được security review; không tự ý thay token bằng SHA-256 không khóa vì giá trị hash vẫn có thể trở thành định danh ổn định. Thông thường correlation ID độc lập là đủ.

## 5. Ví dụ ghi log an toàn trong ứng dụng

### 5.1. Log metadata, không serialize request

Ví dụ Java/Spring theo phong cách `OncePerRequestFilter`:

```java
@Component
public class RequestAuditFilter extends OncePerRequestFilter {
    private static final Logger log =
        LoggerFactory.getLogger(RequestAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        long started = System.nanoTime();
        String route = safeRouteTemplate(request);
        String correlationId = validatedCorrelationId(request);

        try {
            filterChain.doFilter(request, response);
        } finally {
            long elapsedMs = (System.nanoTime() - started) / 1_000_000;
            log.info("http_request method={} route={} status={} duration_ms={} correlation_id={}",
                request.getMethod(), route, response.getStatus(),
                elapsedMs, correlationId);
        }
    }
}
```

Ví dụ này không đọc hoặc ghi `request.getHeader("Authorization")`. Các helper `safeRouteTemplate` và `validatedCorrelationId` phải bảo đảm không đưa raw URL, query string hoặc dữ liệu do client kiểm soát chưa lọc vào log. Đây là ví dụ minh họa, không phải cấu hình bảo mật hoàn chỉnh cho mọi ứng dụng.

### 5.2. Ví dụ log an toàn

```text
2026-11-23 INFO http_request method=GET route=/v1/orders/{orderId} \
status=200 duration_ms=42 correlation_id=7f4c2a...
```

Log vẫn giúp tìm request chậm hoặc lỗi bằng route, status, thời gian và correlation ID. Người vận hành có thể tra quyết định xác thực qua event an toàn liên quan mà không cần xem token.

### 5.3. Nếu cần biết scheme

Chỉ log scheme đã phân loại sau khi parse theo allowlist và không log phần còn lại:

```java
String authScheme = "none";
String authorization = request.getHeader("Authorization");
if (authorization != null) {
    int separator = authorization.indexOf(' ');
    String candidate = separator > 0
        ? authorization.substring(0, separator)
        : "unknown";
    authScheme = switch (candidate.toLowerCase(Locale.ROOT)) {
        case "bearer" -> "bearer";
        case "basic" -> "basic";
        default -> "other";
    };
}
log.debug("authentication_attempt scheme={}", authScheme);
```

Không ghi biến `authorization`, token substring, Basic payload hoặc exception có chứa header. Nếu scheme không cần thiết cho vận hành, bỏ hoàn toàn việc đọc header trong logging code.

## 6. Redaction ở gateway, proxy và APM

Không phải mọi request đều đi qua code logging của ứng dụng. Gateway, reverse proxy, service mesh, HTTP client và APM agent có thể tự động ghi header. Cần cấu hình và kiểm tra ở từng tầng.

### Checklist cấu hình

1. Rà soát access log format, debug log và tracing instrumentation ở ingress/gateway/proxy.
2. Loại `Authorization`, `Proxy-Authorization`, `Cookie` và các header credential khỏi field được export.
3. Tắt capture request/response body ở token endpoint hoặc chỉ capture các trường đã lọc theo schema an toàn.
4. Cấu hình APM agent không thu thập header nhạy cảm; nếu có danh sách redact, kiểm tra casing và alias.
5. Lọc dữ liệu trước khi gửi sang collector/backend, không chỉ che ở giao diện dashboard.
6. Kiểm tra log buffer, retry queue, crash dump, support bundle và CI artifact.
7. Khi nâng phiên bản agent/proxy, chạy lại test để xác nhận default capture không thay đổi.

Redaction là lớp phòng thủ bổ sung. Nếu nền tảng hỗ trợ, nên không thu thập header ngay từ đầu. Khi phải redact, thay toàn bộ giá trị bằng placeholder cố định như `[REDACTED]`; không giữ prefix/suffix của credential.

Ví dụ kết quả sau redaction nếu hệ thống bắt buộc ghi header name để debug:

```text
request_headers={
  "accept": "application/json",
  "authorization": "[REDACTED]",
  "content-type": "application/json"
}
```

Tốt hơn nữa là không log map header đầy đủ; chỉ ghi những header an toàn cần cho use case.

## 7. Những trường credential khác cũng phải bảo vệ

Chỉ che `Authorization` là chưa đủ nếu hệ thống có thể truyền token hoặc secret ở vị trí khác. Rà soát toàn bộ luồng OAuth/OIDC:

| Vị trí | Dữ liệu nhạy cảm | Kiểm soát |
| --- | --- | --- |
| Token endpoint request body | `client_secret`, `refresh_token`, `code`, `code_verifier`, `client_assertion` | Không log raw form body; redact theo schema trước khi export. |
| Token endpoint response body | `access_token`, `refresh_token`, `id_token` | Không log response body; `Cache-Control: no-store` không thay thế log hygiene. |
| URL query | `access_token` (nếu hệ thống legacy cho phép), authorization code, dữ liệu phiên | Không đặt bearer token trong URI; loại query nhạy cảm khỏi access log. |
| Cookie | Session cookie, refresh/session handle | Không log cookie value; áp dụng cookie flags phù hợp. |
| WebSocket/subprotocol hoặc custom header | Credential theo giao thức riêng | Xác định và phân loại như credential; không chỉ dựa trên tên `Authorization`. |
| Exception/validation error | Raw input hoặc request dump | Chuyển thành error code an toàn, không nối nguyên request vào message. |
| Test fixture | Token/secret giả hoặc vô tình dùng production | Chỉ dùng dữ liệu test; kiểm tra artifact và log CI. |

OAuth Bearer Token Usage (RFC 6750) khuyến nghị dùng Authorization request header cho bearer token và cảnh báo về rủi ro truyền token qua URI. Dù token được truyền theo cách nào, log không được lưu giá trị có thể dùng để xác thực.

## 8. Phát hiện và xử lý khi Authorization header đã bị log

Nếu phát hiện token hoặc credential thật trong log, hãy xem đây là sự cố lộ credential. Không chỉ xóa dòng log rồi đóng ticket, vì bản sao có thể đã được chuyển tới nhiều hệ thống.

Quy trình ứng phó:

1. **Khoanh vùng:** xác định loại credential, issuer/client, khoảng thời gian, hệ thống log/APM/trace và các bản sao/consumer có thể đã nhận dữ liệu.
2. **Hạn chế truy cập:** giảm quyền đọc log liên quan, dừng export/forward nếu cần và bảo toàn bằng chứng theo incident policy.
3. **Đánh giá khả năng sử dụng:** token còn hạn không, refresh token còn active không, client secret có bị lộ không, token có sender-constrained hay chỉ là Bearer.
4. **Thu hồi:** revoke refresh token family/session/grant liên quan; vô hiệu access token bằng introspection, denylist, account/token version hoặc cơ chế phù hợp. Với client secret bị lộ, rotate credential và kiểm tra client activity.
5. **Xử lý bản sao log:** xóa hoặc rút ngắn retention theo quy trình đã phê duyệt, kể cả index, export, attachment và backup có thể xử lý được. Không phá hủy bằng chứng cần thiết cho điều tra hoặc nghĩa vụ lưu giữ.
6. **Điều tra sử dụng trái phép:** rà soát request theo thời gian, client, resource và hành vi bất thường; không đưa token lộ vào công cụ công cộng để kiểm tra.
7. **Khắc phục nguồn:** tắt raw header/body capture, bổ sung allowlist/redaction sớm, cập nhật runbook và quyền truy cập log.
8. **Xác minh:** chạy test sentinel ở mọi tầng, chứng minh giá trị không xuất hiện trong log/trace/APM/CI artifact sau thay đổi.

Nếu log chứa Basic credential, cần đánh giá và rotate secret/password tương ứng. Nếu log chứa refresh token, nguy cơ kéo dài hơn access token vì refresh token có thể tạo access token mới cho tới khi bị thu hồi. Nếu log chứa ID token, xử lý dữ liệu cá nhân và session theo OIDC/client contract; không dùng ID token như access token để gọi API.

## 9. Kiểm thử để bảo đảm không rò rỉ log

Kiểm thử phải đi qua toàn bộ pipeline log trong môi trường test. Dùng một chuỗi sentinel giả có thể nhận diện, không dùng token production.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Bearer header | Gửi `Authorization: Bearer <SENTINEL>` | Sentinel không xuất hiện trong application log, gateway log, trace hoặc APM. |
| Basic header | Gửi Basic credential giả | Giá trị Base64 và credential sau decode đều không xuất hiện. |
| Header casing khác | Gửi `authorization`, `AUTHORIZATION` | Bộ lọc vẫn loại bỏ giá trị. |
| Proxy auth | Gửi `Proxy-Authorization` giả | Không có credential trong log proxy/gateway. |
| Nhiều header value | Gửi header trùng hoặc nhiều giá trị theo client/server hỗ trợ | Không có giá trị nhạy cảm nào bị serialize. |
| Token endpoint body | Gửi refresh token, client assertion và code verifier sentinel | Body không xuất hiện trong log hoặc trace. |
| Exception path | Kích hoạt lỗi parse/authentication | Exception message không chứa request/header/token. |
| APM/debug mode | Bật instrumentation trong test | Header nhạy cảm không được export kể cả khi debug. |
| URL query legacy | Gửi query chứa sentinel test | Access log không ghi giá trị nhạy cảm; ứng dụng từ chối hoặc xử lý theo policy. |
| CI artifact | Chạy test thất bại có chủ đích | Console, report và artifact không chứa sentinel. |

### Ví dụ kiểm thử log bằng sentinel

```java
@Test
void authorizationHeaderIsNeverWrittenToApplicationLogs() {
    String sentinel = "SENTINEL-BEARER-DO-NOT-LOG-9f31";

    mockMvc.perform(get("/v1/orders/123")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + sentinel))
        .andReturn();

    String capturedLogs = testLogAppender.contents();
    assertFalse(capturedLogs.contains(sentinel));
    assertFalse(capturedLogs.contains("Authorization: Bearer"));
}
```

Đây là ví dụ theo phong cách Spring MVC/JUnit; `testLogAppender` là fixture của test suite. Kiểm tra application log mới chỉ là một phần. Cần chạy test tương đương cho gateway, reverse proxy, APM exporter, trace collector và pipeline CI vì các tầng đó có thể ghi header độc lập.

## 10. Những cách khắc phục sai cần tránh

- **Chỉ che JWT trong controller:** gateway hoặc APM có thể đã ghi token trước khi request tới controller.
- **Chỉ che chữ `Bearer`:** phần token vẫn còn trong log và có thể tái sử dụng nếu ghép lại.
- **Chỉ che một vài ký tự:** token fragment vẫn là dữ liệu nhạy cảm và có thể hỗ trợ correlation hoặc dò đoán.
- **Dựa vào quyền truy cập log:** log có thể được export hoặc sao lưu; người đọc log không nên có credential.
- **Bật debug trong production không giới hạn:** debug có thể ghi header/body ở thư viện HTTP hoặc framework mà ứng dụng không kiểm soát trực tiếp.
- **Cho rằng HTTPS bảo vệ log:** TLS bảo vệ dữ liệu trên đường truyền, không bảo vệ bản ghi sau khi endpoint nhận request.
- **Cho rằng JWT đã ký không thể bị lạm dụng:** chữ ký không ngăn người khác replay Bearer token hợp lệ.
- **Xóa log nhưng không revoke token:** credential bị lộ vẫn có thể được dùng từ bản sao khác hoặc trước khi hết hạn.
- **Ghi hash token làm giải pháp mặc định:** hash ổn định vẫn có thể trở thành định danh theo dõi; chỉ dùng cơ chế tương quan riêng khi được phê duyệt.

## 11. Checklist triển khai

- [ ] Application không log giá trị `Authorization` hoặc `Proxy-Authorization`.
- [ ] Gateway, reverse proxy, service mesh và HTTP client không capture credential header.
- [ ] APM/tracing redact hoặc loại header trước khi export; không chỉ che ở giao diện.
- [ ] Token endpoint request/response body không chứa secret/token trong log.
- [ ] Cookie, query string, exception và diagnostic dump được rà soát.
- [ ] Logging dùng allowlist trường an toàn và route template, không serialize toàn bộ request.
- [ ] Redaction nhận diện header name không phân biệt hoa thường và giá trị nhiều phần.
- [ ] Không log token fragment, refresh token, client secret hoặc private key.
- [ ] Log access, retention, export và backup có kiểm soát.
- [ ] Có runbook revoke token/rotate client credential nếu log bị lộ.
- [ ] Sentinel tests chạy qua app, gateway, APM, trace và CI pipeline.

**Điểm cốt lõi:** Authorization header mang credential có thể được dùng để xác thực. Ghi header vào log biến hệ thống quan sát thành một kho token thứ hai, thường có nhiều người và hệ thống truy cập hơn. Hãy không thu thập giá trị header, chỉ log metadata allowlist, kiểm thử toàn bộ pipeline và thu hồi credential nếu đã bị lộ.

## Tài liệu tham khảo

- IETF, **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage**: cách truyền bearer token và rủi ro khi token bị tiết lộ. <https://www.rfc-editor.org/rfc/rfc6750>
- IETF, **RFC 6749 — The OAuth 2.0 Authorization Framework**: access token, refresh token và client authentication. <https://www.rfc-editor.org/rfc/rfc6749>
- IETF, **RFC 7009 — OAuth 2.0 Token Revocation**: thu hồi access token và refresh token. <https://www.rfc-editor.org/rfc/rfc7009>
- IETF, **RFC 9110 — HTTP Semantics**: ngữ nghĩa HTTP field và header. <https://www.rfc-editor.org/rfc/rfc9110>
- OWASP, **Logging Cheat Sheet**: dữ liệu không nên ghi log, kiểm soát log và xử lý thông tin nhạy cảm. <https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html>
- OWASP, **Secrets Management Cheat Sheet**: quản lý và bảo vệ secret trong hệ thống. <https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html>
