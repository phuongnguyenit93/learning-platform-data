# Không đặt token trong URL hoặc log

Access token, refresh token, API key và session identifier là thông tin xác thực. Bất kỳ ai có được một bearer token còn hiệu lực đều có thể sử dụng token đó trong phạm vi quyền được cấp. Vì vậy, token phải được truyền qua kênh phù hợp và không được xuất hiện trong URL, log, trace, báo cáo lỗi hoặc công cụ phân tích.

Đặt token trong query string hoặc path khiến bí mật dễ bị sao chép sang nhiều hệ thống: browser history, access log của reverse proxy, API gateway, CDN, APM, analytics, referrer, ảnh chụp màn hình và ticket hỗ trợ. Ghi token vào log còn tạo thêm bản sao tồn tại lâu hơn vòng đời của token, thường có nhiều người và hệ thống có thể truy cập.

HTTPS bảo vệ dữ liệu trên đường truyền giữa các điểm kết nối, nhưng không ngăn URL hoặc header bị ghi lại ở endpoint, proxy hay ứng dụng. API Security vì vậy phải kiểm soát cả cách truyền credential lẫn cách thu thập telemetry trong toàn bộ request lifecycle.

## 1. Vì sao URL là nơi không an toàn để chứa token?

URL được thiết kế để định danh tài nguyên và có thể được lưu, chia sẻ, ghi log hoặc chuyển tiếp. Token là bí mật cấp quyền. Khi đặt token vào URL, ta biến một chuỗi định danh thường xuyên được lưu trữ thành nơi chứa credential.

Ví dụ không an toàn:

```http
GET /api/orders?access_token=eyJhbGciOi... HTTP/1.1
Host: api.example.test
```

Hoặc:

```http
GET /api/downloads/eyJhbGciOi.../invoice.pdf HTTP/1.1
Host: api.example.test
```

Query string và path đều có thể xuất hiện trong URL log. Chuyển token từ query sang path không giải quyết vấn đề. Một số hệ thống chỉ che query parameter nhưng vẫn ghi toàn bộ path; ngược lại, có hệ thống log toàn bộ URL.

Các nơi URL có thể bị lưu hoặc lan truyền:

- Browser history, bookmark, đồng bộ lịch sử và danh sách URL gần đây.
- Reverse proxy, load balancer, API gateway, web server và CDN access log.
- APM, distributed tracing, error tracker và crash report.
- Analytics, session replay, telemetry của frontend và công cụ giám sát.
- Header `Referer` khi trang điều hướng hoặc tải tài nguyên từ origin khác.
- Link trong email, chat, ticket hỗ trợ, tài liệu và ảnh chụp màn hình.
- Cache của browser, proxy hoặc intermediary nếu response/request được lưu.
- Công cụ debug HTTP, HAR export và command history.

Một URL có thể bị sao chép sang nơi không cùng chính sách bảo vệ với hệ thống phát hành token. Khi đã bị lộ, người khác có thể dùng token cho đến khi token hết hạn hoặc bị thu hồi.

## 2. Phân biệt URL path, query và fragment

Không đặt credential vào bất kỳ phần nào của URL:

| Thành phần | Ví dụ | Rủi ro |
|---|---|---|
| Query string | `?access_token=...` | Thường được ghi cùng request target trong access log và có thể xuất hiện trong referrer hoặc analytics |
| Path segment | `/download/{token}` | Thường được ghi trong access log, trace và route diagnostics |
| URL user info | `https://user:secret@host/path` | Có thể bị parser, debug tool hoặc log lưu lại; nhiều client/proxy xử lý không nhất quán |
| Fragment | `https://app.example.test/callback#access_token=...` | Không gửi trong HTTP request thông thường nhưng vẫn có thể lưu trong browser history, đọc bởi JavaScript và lộ qua client telemetry |

Fragment không được gửi tới server trong request HTTP thông thường, nhưng điều đó không khiến nó trở thành nơi lưu token an toàn. JavaScript, browser extension, lịch sử trình duyệt hoặc mã analytics cùng trang vẫn có thể truy cập fragment. Với OAuth, ưu tiên Authorization Code Flow với PKCE và xử lý callback theo hướng dẫn của giao thức/thư viện hiện hành; không dùng implicit flow để đưa access token vào fragment.

## 3. Kênh truyền token phù hợp

Với resource API, bearer access token thường được gửi trong HTTP `Authorization` header:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

Header giúp tránh việc token trở thành một phần của URL, nhưng không tự động bảo vệ token khỏi log. Proxy, middleware, APM hoặc debug interceptor vẫn có thể ghi header. Vì vậy phải cấu hình redaction cho `Authorization` ở mọi lớp quan sát request.

Các lựa chọn thường dùng:

- **Resource API:** gửi access token trong `Authorization: Bearer ...` qua HTTPS/TLS.
- **Browser với backend-for-frontend (BFF):** giữ OAuth token ở backend; browser dùng session cookie được cấu hình `HttpOnly`, `Secure` và `SameSite` phù hợp, kèm biện pháp CSRF.
- **Native/mobile client:** lưu credential trong secure storage của hệ điều hành và gửi qua header khi gọi API.
- **Service-to-service:** dùng workload identity, mTLS hoặc credential ngắn hạn; gửi token qua header và giới hạn quyền theo service/action.
- **OAuth token endpoint:** các tham số grant như refresh token có thể nằm trong POST form body theo giao thức; body vẫn là dữ liệu nhạy cảm và phải được bảo vệ khỏi access log, body logging, tracing và error report.

Không chuyển token sang POST body chỉ để né URL nếu API contract quy định `Authorization` header. Body cũng có thể bị ghi lại bởi middleware hoặc công cụ debug. Chọn kênh theo giao thức và bảo vệ dữ liệu ở mọi điểm xử lý.

## 4. Token trong cookie: cần thêm CSRF protection

Cookie có thể phù hợp với browser session hoặc BFF vì trình duyệt tự gửi cookie tới origin tương ứng và `HttpOnly` ngăn JavaScript đọc giá trị cookie. Ví dụ cấu hình khái niệm:

```http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Các thuộc tính cần cân nhắc:

- `Secure`: chỉ gửi cookie qua HTTPS.
- `HttpOnly`: không cho JavaScript đọc cookie qua API thông thường.
- `SameSite`: giảm một số kiểu cross-site request; chọn `Lax`, `Strict` hoặc `None` theo luồng đăng nhập và tích hợp.
- `Path=/` và prefix `__Host-`: giúp ràng buộc cookie với host, yêu cầu Secure và không có Domain attribute theo quy tắc của prefix.
- Thời hạn cookie và session server-side cần phù hợp chính sách idle/absolute timeout.

Cookie được browser tự động gửi kèm request nên có nguy cơ CSRF. `SameSite` là một lớp bảo vệ; với thao tác thay đổi trạng thái, vẫn cần CSRF token hoặc cơ chế kiểm tra origin phù hợp với kiến trúc. `HttpOnly` không ngăn XSS thực hiện hành động thay người dùng trong trang đang bị kiểm soát.

## 5. Không ghi token vào log ở bất kỳ lớp nào

Token có thể bị ghi trước khi request tới ứng dụng và sau khi ứng dụng đã xử lý. Chỉ che token trong application logger là chưa đủ.

| Lớp | Ví dụ dữ liệu có thể bị log | Kiểm soát cần có |
|---|---|---|
| CDN/load balancer | Full URL, query, request header | Không log query nhạy cảm; redact credential headers |
| API gateway/reverse proxy | Request target, `Authorization`, cookie | Redaction ở access/error log và trace exporter |
| Web server/framework | URI, header, form body, exception context | Tắt logging body/credential; dùng route template thay URL đầy đủ |
| Application logger | Request object, DTO, debug dump | Allow-list trường log; không log token, cookie hoặc raw request |
| APM/distributed tracing | URL đầy đủ, header, baggage, span attributes | Scrub `url.full`, query, auth/cookie headers và custom attributes |
| Error tracker/crash report | Local variables, HTTP client config, exception message | Loại credential khỏi context và stack metadata |
| Frontend analytics/session replay | Location URL, DOM, network event | Không gửi query/fragment nhạy cảm; mask input và network fields |
| SIEM/data lake | Log được tập trung và lưu lâu | Phân loại dữ liệu, kiểm soát truy cập, retention và phát hiện secret |

Các tên field cần xem xét redaction gồm `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `access_token`, `refresh_token`, `id_token`, `client_secret`, `api_key`, `code`, `state` và các header tùy biến chứa credential. Tên thực tế phụ thuộc giao thức và ứng dụng; hãy lập danh sách theo hệ thống thay vì chỉ dựa vào một regex.

Không log toàn bộ URL nếu chỉ cần route. Dùng route template như `/api/orders/{orderId}` thay vì path có giá trị thật, và chỉ ghi query parameter đã được allow-list. Nếu query filter có thể chứa email, mã định danh hoặc thông tin cá nhân, chúng cũng cần được phân loại và che phù hợp.

## 6. Thiết kế log theo allow-list

Một cách an toàn là chọn trước những trường cần ghi thay vì ghi toàn bộ request rồi cố xóa bí mật sau đó.

Ví dụ access log phù hợp:

```json
{
  "timestamp": "2026-11-18T12:00:00Z",
  "request_id": "req-8c12",
  "method": "GET",
  "route": "/api/orders/{orderId}",
  "status": 200,
  "duration_ms": 42,
  "principal_ref": "user-123",
  "tenant_ref": "tenant-A"
}
```

Ví dụ không an toàn:

```json
{
  "url": "https://api.example.test/api/orders?access_token=eyJhbGciOi...",
  "authorization": "Bearer eyJhbGciOi...",
  "cookie": "session=opaque-secret",
  "request_body": "{...sensitive payload...}"
}
```

Log nên tập trung vào metadata cần cho vận hành và bảo mật: request ID, route template, method, status, duration, principal reference, tenant reference, permission decision và error code. Không ghi credential hoặc toàn bộ payload chỉ để tiện debug.

Nếu cần tương quan các lần sử dụng một token, ưu tiên token ID (`jti`) hoặc fingerprint không thể đảo ngược được tạo bằng HMAC với khóa logging riêng. Không dùng raw token. Với API key entropy thấp hoặc có định dạng dễ đoán, plain hash có thể hỗ trợ dò ngược; HMAC với khóa riêng giúp giảm rủi ro này. Fingerprint vẫn là dữ liệu nhạy cảm và cần kiểm soát quyền truy cập.

## 7. Redaction phải xảy ra trước khi dữ liệu rời khỏi process

Không nên dựa vào việc SIEM hoặc người vận hành sẽ xóa token sau khi log đã được gửi đi. Redaction cần được áp dụng ở nguồn phát sinh log và mọi collector trung gian.

Một quy trình cấu hình tốt:

1. Xác định trường credential trong header, URL, body, cookie và exception.
2. Tắt capture toàn bộ request/response body mặc định; chỉ bật có chọn lọc trong môi trường test với dữ liệu giả lập.
3. Redact `Authorization`, cookie và custom secret headers ở gateway, application, HTTP client và APM agent.
4. Loại query string/fragment khỏi telemetry URL hoặc chỉ giữ query key đã allow-list và không chứa dữ liệu nhạy cảm.
5. Kiểm tra log ở collector, trace backend, error tracker và SIEM để xác nhận redaction không bị mất ở pipeline sau.
6. Thiết lập retention, quyền đọc, audit truy cập và quy trình xử lý log chứa bí mật ngoài ý muốn.

Redaction ở một lớp không bảo đảm mọi lớp khác đã được bảo vệ. Ví dụ gateway có thể che `Authorization` trong access log nhưng tracing agent trong ứng dụng vẫn ghi header đó vào span attribute.

## 8. Ví dụ Spring: không log request credential

Trong ứng dụng Spring, tránh các interceptor/filter ghi toàn bộ header, query string hoặc body. Nếu cần access log, hãy tạo record từ allow-list:

```java
@Component
class SafeRequestAuditFilter extends OncePerRequestFilter {
    private final RequestAuditWriter auditWriter;

    SafeRequestAuditFilter(RequestAuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - started) / 1_000_000;
            auditWriter.write(new RequestAuditEvent(
                    request.getMethod(),
                    routeTemplateOrSafePath(request),
                    response.getStatus(),
                    durationMs,
                    request.getHeader("X-Request-Id")));
        }
    }
}
```

Đây là ví dụ minh họa; `routeTemplateOrSafePath` cần lấy route template đã được framework/router xác định hoặc dùng giá trị đã loại bỏ path parameter nhạy cảm. Không thay nó bằng `request.getRequestURI()` một cách máy móc nếu path có thể chứa token. `RequestAuditEvent` cũng không nên chứa toàn bộ header, query string, cookie hoặc body.

Không viết filter để log `request.getHeader("Authorization")`, `request.getQueryString()` hoặc `request.getRequestURL()` đầy đủ. Nếu cần biết caller, lấy subject/tenant reference từ security context đã xác minh và chỉ ghi định danh phù hợp với chính sách dữ liệu.

## 9. HTTP client và outbound request logging

Token cũng có thể bị lộ khi service gọi API khác. HTTP client interceptor, retry logger hoặc exception có thể in toàn bộ request configuration.

Khi cấu hình outbound client:

- Không log toàn bộ request headers hoặc `HttpRequest` object.
- Redact `Authorization`, cookie, client secret và signed headers trong wire log.
- Không nối token vào URL hoặc query khi xây dựng request.
- Không đưa token vào trace baggage hoặc MDC/context propagation.
- Không đưa credential vào exception message hoặc retry metadata.
- Nếu debug HTTP cần bật tạm thời, dùng credential giả lập, thời gian ngắn và quyền truy cập log hạn chế.

Ví dụ request service-to-service:

```http
POST /internal/invoices/reconcile HTTP/1.1
Host: billing.internal.example.test
Authorization: Bearer <short-lived-service-token>
Content-Type: application/json
X-Request-Id: req-8c12
```

Log outbound chỉ cần route, status, latency, dependency name và request ID. Không ghi bearer token hoặc body nhạy cảm. Khi dùng mTLS, không log private key hoặc material dùng để truy cập certificate store.

## 10. OAuth callback và authorization code

OAuth redirect URI là một trường hợp đặc biệt cần chú ý. Authorization code và `state` có thể xuất hiện trong query string ở callback theo response mode. Authorization code là credential ngắn hạn và có thể bị dùng để đổi token nếu không được bảo vệ.

Các biện pháp:

- Dùng Authorization Code Flow với PKCE cho public client và các ứng dụng phù hợp.
- Kiểm tra `state` để chống CSRF/login injection; kiểm tra issuer/response theo giao thức và thư viện sử dụng.
- Đổi authorization code ngay tại token endpoint qua kết nối TLS; không ghi code, `state`, verifier hoặc token vào log.
- Sau khi xử lý callback, chuyển hướng sang URL sạch không còn query chứa code/state nếu phù hợp với flow.
- Đặt referrer policy nghiêm ngặt cho trang callback và tránh tải tài nguyên bên thứ ba trước khi URL được làm sạch.
- Không lưu callback URL đầy đủ trong analytics, session replay hoặc error tracker.
- Authorization code phải ngắn hạn, dùng một lần và ràng buộc đúng client/redirect URI/PKCE verifier.

Nếu callback URL được web server ghi access log trước khi ứng dụng xử lý, việc redirect sang URL sạch không xóa bản ghi đã phát sinh. Cần redaction ở proxy/web server cho các callback route hoặc query key nhạy cảm ngay từ đầu.

## 11. Referrer, cache và frontend telemetry

Nếu trang có URL chứa token hoặc authorization code, browser có thể gửi URL đó trong `Referer` khi tải tài nguyên hoặc điều hướng. Chính sách referrer hiện đại có thể giới hạn một số thông tin cross-origin, nhưng hành vi phụ thuộc browser, policy và cùng/khác origin. Đừng dùng `Referrer-Policy` như lý do để đặt token trong URL.

Các biện pháp bổ sung:

- Không đưa token vào URL ngay từ đầu.
- Đặt `Referrer-Policy: no-referrer` hoặc policy phù hợp nghiêm ngặt cho trang xử lý callback/credential.
- Tránh third-party script, analytics hoặc pixel trên trang xử lý authorization callback.
- Không capture full location, query hoặc fragment trong session replay.
- Dùng `Cache-Control: no-store` cho response token và trang chứa dữ liệu xác thực nhạy cảm khi phù hợp.
- Không cache response API chứa token hoặc dữ liệu riêng tư ở CDN/shared proxy.
- Xóa URL callback nhạy cảm khỏi thanh địa chỉ sau khi xử lý, nhưng vẫn redaction ở server log.

`Referrer-Policy` và `Cache-Control` là lớp giảm rủi ro bổ sung. Chúng không sửa được việc token đã nằm trong URL, browser history hoặc log trước đó.

## 12. Signed URL là ngoại lệ có chủ đích, không phải cách truyền access token thông thường

Một số dịch vụ lưu trữ dùng pre-signed URL để cấp quyền truy cập một object trong thời gian ngắn. URL này thường chứa signature hoặc query parameter có quyền bearer. Đây là capability URL được thiết kế có chủ đích, không phải cách gửi access token của API.

Nếu cần dùng signed URL:

- Chỉ cấp quyền cho đúng object và đúng thao tác, thường chỉ `GET` hoặc `PUT`.
- Đặt TTL ngắn nhất phù hợp và giới hạn kích thước/content type nếu provider hỗ trợ.
- Không ghi URL đầy đủ vào log, analytics, ticket hoặc thông báo không được bảo vệ.
- Không cho redirect hoặc proxy tùy ý làm lộ URL sang origin khác.
- Cân nhắc download proxy nếu cần thu hồi tức thời hoặc kiểm tra tenant state mỗi lần tải.
- Có quy trình revoke/rotate signing key hoặc thay đổi object policy nếu URL bị lộ.
- Coi URL như credential: bất kỳ ai có URL còn hiệu lực có thể sử dụng quyền được nhúng trong đó.

Signed URL không thay thế authorization khi cấp URL. Server phải xác minh caller có quyền trên object trước khi tạo capability. Không dùng URL ký dài hạn hoặc quyền rộng để giải quyết việc truyền token trong ứng dụng.

## 13. Xử lý hệ thống legacy đang nhận token trong query string

Nếu API cũ đang hỗ trợ `?access_token=...`, cần có kế hoạch loại bỏ có kiểm soát:

1. Inventory endpoint/client đang sử dụng query token; không ghi giá trị token khi đo usage.
2. Cập nhật client để gửi `Authorization: Bearer` theo contract.
3. Bật telemetry chỉ đếm số request có tên parameter nhạy cảm, không capture giá trị.
4. Phát cảnh báo/deprecation và thời hạn chuyển đổi cho client tích hợp.
5. Từ chối query token sau thời hạn; không âm thầm chấp nhận cả header và query nếu hai token khác nhau.
6. Xóa hỗ trợ query token khỏi code và contract; thêm regression test để bảo đảm request bị từ chối.
7. Kiểm tra log pipeline đã redaction query nhạy cảm trước khi rollout, vì client cũ có thể tiếp tục gửi token trong giai đoạn chuyển tiếp.

Không tạo fallback kiểu “nếu header thiếu thì đọc `access_token` từ query”. Fallback này duy trì đường truyền credential không an toàn và có thể bị quên trong thời gian dài. Nếu buộc phải có thời gian chuyển tiếp, giới hạn rõ client, endpoint và deadline; tuyệt đối không log giá trị parameter.

## 14. Nếu token đã xuất hiện trong URL hoặc log

Hãy xử lý token bị lộ như credential có khả năng đã bị sao chép. Xóa chuỗi khỏi một dashboard không làm token mất hiệu lực.

Các bước ứng phó thường gồm:

1. Xác định loại token, subject/client/tenant, scope, thời hạn và hệ thống nơi token xuất hiện.
2. Thu hồi access/refresh token, session, API key hoặc OAuth grant tương ứng; với refresh token rotation, cân nhắc revoke toàn bộ token family.
3. Nếu là signed URL, vô hiệu hóa object access/key hoặc chờ TTL ngắn theo kế hoạch đã xác định; kiểm tra download log.
4. Kiểm tra audit/usage để tìm request bất thường từ thời điểm có khả năng lộ.
5. Redact hoặc hạn chế truy cập log, trace, ticket và artifact bị ảnh hưởng; xử lý retention/immutable storage theo quy trình sự cố.
6. Phát hành credential mới qua kênh an toàn và cập nhật client/secret manager.
7. Sửa nguồn phát sinh: query token, access log, APM capture, debug interceptor hoặc analytics.
8. Thêm test ngăn tái diễn và ghi nhận incident/evidence.

Không thể giả định mọi bản sao đã biến mất sau khi xóa log ở một nơi. Log đã replicate, backup hoặc export có thể còn tồn tại theo retention. Ưu tiên thu hồi credential và giới hạn quyền truy cập các bản sao, sau đó xử lý xóa theo chính sách dữ liệu.

## 15. Kiểm thử để chứng minh token không bị lộ

Kiểm thử cần quan sát nhiều lớp, không chỉ assert rằng controller không log token. Dùng token giả lập có marker duy nhất, ví dụ `TEST_TOKEN_CANARY_7f31`, để tìm trong log test và artifact.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Gửi access token trong Authorization header | API hoạt động; token không xuất hiện trong access/app/APM log |
| Gửi `access_token` trong query | Request bị từ chối theo contract; giá trị không bị ghi vào log |
| Gửi token trong path | Endpoint không dùng path token; log route không lưu secret |
| Gửi token trong fragment phía browser | Frontend telemetry/session replay không thu thập fragment |
| Request lỗi 4xx/5xx | Exception/error tracker không chứa header, query hoặc token |
| HTTP client gọi downstream | Wire log và trace không chứa outbound credential |
| OAuth callback có `code` và `state` | Proxy/app/analytics không lưu giá trị; callback được làm sạch sau xử lý |
| Cookie session | Log không ghi `Cookie` hoặc `Set-Cookie`; CSRF protection hoạt động |
| Signed URL | Log và analytics không chứa URL ký đầy đủ; TTL và object scope được kiểm tra |
| APM/tracing | Không có `Authorization`, cookie, query token hoặc raw body trong span |
| Secret rotation/revocation | Token cũ bị từ chối; log chỉ chứa ID/fingerprint an toàn |
| Log aggregation/backup | Quyền truy cập và retention đúng; không có bản sao canary trong pipeline |

Test có thể thực hiện theo các bước:

1. Tạo token giả lập không có quyền truy cập môi trường thật.
2. Gửi request qua gateway và ứng dụng test với marker duy nhất.
3. Kích hoạt cả success, validation error, authentication failure và server error.
4. Thu thập access log, application log, trace, APM event và error report.
5. Tìm marker/token trong toàn bộ artifact; kết quả phải không có match.
6. Xác minh route template và metadata cần thiết vẫn có mặt để hỗ trợ điều tra.

Không dùng token production để kiểm tra redaction. Artifact kiểm thử cần được xử lý như dữ liệu nhạy cảm nếu vô tình chứa marker hoặc credential.

## 16. Checklist thiết kế và vận hành

- [ ] Không đặt access token, refresh token, API key, session ID hoặc authorization code trong query, path, URL user info hay fragment.
- [ ] Resource API dùng `Authorization` header qua HTTPS theo đúng giao thức.
- [ ] Cookie session có `Secure`, `HttpOnly`, `SameSite` phù hợp và CSRF protection.
- [ ] OAuth callback dùng flow phù hợp, kiểm tra `state`/PKCE và không log code/token.
- [ ] Token endpoint POST body được bảo vệ khỏi body logging và telemetry capture.
- [ ] Access log dùng route template; không ghi full URL/query nhạy cảm.
- [ ] `Authorization`, `Cookie`, `Set-Cookie`, API key và custom secret headers được redact ở gateway, app, APM và collector.
- [ ] Không log raw request/response body hoặc HTTP client object theo mặc định.
- [ ] Trace, baggage, error tracker, analytics và session replay không thu thập credential.
- [ ] Signed URL được coi là bearer capability, có scope hẹp, TTL ngắn và không bị log.
- [ ] Legacy query-token support có kế hoạch deprecation và bị loại bỏ.
- [ ] Có quy trình revoke/rotate khi token bị lộ và kiểm tra log/usage bất thường.
- [ ] Có canary test tìm token trong toàn bộ log/trace/error pipeline.
- [ ] Log được phân quyền, audit và retention phù hợp; immutable copy được xử lý theo incident policy.

## Kết luận

Token không thuộc URL hoặc log vì cả hai đều có thể được lưu, sao chép và chuyển tiếp qua nhiều hệ thống ngoài phạm vi kiểm soát của ứng dụng. Resource API nên nhận bearer token qua `Authorization` header; browser session có thể dùng cookie được bảo vệ cùng CSRF control; OAuth token endpoint và các body nhạy cảm cần được redaction tương tự. Hãy dùng logging allow-list, che credential tại gateway, application, HTTP client, APM và SIEM, đồng thời kiểm thử bằng canary token. Nếu token đã lộ, thu hồi hoặc xoay vòng credential trước, rồi xử lý các bản log và artifact theo quy trình sự cố.
