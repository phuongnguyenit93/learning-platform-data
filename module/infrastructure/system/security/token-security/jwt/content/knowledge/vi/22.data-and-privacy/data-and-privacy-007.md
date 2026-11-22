# Tránh sao chép token vào nhật ký, công cụ phân tích và báo cáo lỗi

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Dữ liệu và riêng tư. Bài viết áp dụng cho mọi hệ thống phát hành, truyền, xác minh hoặc lưu JWT; không phụ thuộc ngôn ngữ lập trình, nền tảng hay framework.

## 1. Vì sao không được ghi token vào log?

Access token, refresh token, ID Token và nhiều loại JWT khác có thể chứa thông tin xác thực hoặc hoạt động như credential. Nếu một bearer access token bị sao chép, người có token có thể sử dụng nó trong phạm vi quyền và thời hạn mà resource server chấp nhận. Refresh token còn có thể được dùng để xin access token mới. ID Token, authorization code, session cookie, JWT assertion và DPoP proof cũng có thể tiết lộ thông tin hoặc cho phép thực hiện hành động nếu bị lộ trong đúng ngữ cảnh.

Ghi token vào log, công cụ phân tích hoặc báo cáo lỗi tạo thêm bản sao credential ở những hệ thống vốn không được thiết kế để lưu bí mật xác thực. Các bản sao này có thể:

- được lưu lâu hơn thời hạn token gốc;
- được sao chép sang nhiều vùng lưu trữ, bản backup hoặc hệ thống SIEM;
- được đọc bởi nhiều nhân sự hoặc nhà cung cấp hơn hệ thống xác thực;
- xuất hiện trong kết quả tìm kiếm, dashboard, trace, alert hoặc ticket hỗ trợ;
- bị tải xuống máy cá nhân hoặc chia sẻ qua email/chat;
- tiếp tục tồn tại sau khi token đã hết hạn hoặc grant đã bị thu hồi.

**Nguyên tắc mặc định: không ghi giá trị credential vào bất kỳ log, trace, metric, analytics event, crash report hay báo cáo hỗ trợ nào.** Ghi nhận sự kiện xác thực và kết quả xử lý bằng metadata đã chọn lọc; không ghi token để “debug cho tiện”.

## 2. Những dữ liệu cần được xem là credential hoặc dữ liệu xác thực nhạy cảm

Không chỉ chuỗi JWT có ba segment mới cần bảo vệ. Opaque token, cookie và mã giao dịch cũng có thể có giá trị tương đương.

| Dữ liệu | Vì sao cần bảo vệ | Xử lý mặc định |
| --- | --- | --- |
| Access token | Có thể gọi API như bearer credential | Không log giá trị |
| Refresh token | Có thể xin access token mới | Không log; bảo vệ nghiêm ngặt |
| ID Token | Chứa thông tin xác thực, subject và ngữ cảnh đăng nhập | Không log nguyên token hoặc payload |
| JWT client assertion / bearer assertion | Có thể xác thực client hoặc đại diện grant | Không log |
| DPoP proof JWT | Có thể được phát lại trong cửa sổ hiệu lực và chứa thông tin khóa công khai | Không log nguyên proof |
| Session cookie | Có thể đại diện phiên đăng nhập | Không log giá trị cookie |
| Authorization code | Credential dùng một lần để đổi token | Không log |
| `code_verifier` | Bí mật PKCE dùng khi đổi authorization code | Không log |
| `state` và `nonce` | Liên kết giao dịch và bảo vệ luồng xác thực | Không log giá trị nguyên vẹn |
| Client secret / private key | Bí mật xác thực hoặc ký | Tuyệt đối không log |
| API key / password / recovery code | Credential có thể cấp quyền truy cập | Tuyệt đối không log |
| Token fingerprint | Có thể liên kết nhiều sự kiện với cùng credential | Chỉ dùng khi có mục đích, bảo vệ và giới hạn truy cập |

Các claim trong token cũng có thể là dữ liệu cá nhân hoặc dữ liệu nhạy cảm: `sub`, email, tên, tenant, nhóm, role, scope, địa chỉ, thiết bị, `auth_time`, `acr` và `amr`. Không log toàn bộ payload sau khi decode chỉ vì đã loại bỏ chữ ký.

JWT JWS thường chỉ được ký, không được mã hóa. Header và payload được Base64URL encode nên người có token có thể đọc nội dung. JWE có thể mã hóa payload nhưng vẫn là credential nhạy cảm và không nên được ghi vào log. Không xem Base64URL hoặc chữ ký là biện pháp ẩn dữ liệu.

## 3. Token có thể rò rỉ qua những đâu?

Một request đi qua nhiều thành phần. Chỉ chặn log ở ứng dụng chính là chưa đủ.

| Bề mặt | Ví dụ dữ liệu có thể bị ghi |
| --- | --- |
| Application log | Authorization header, cookie, request object, exception message |
| Reverse proxy / load balancer | Header, URL, query string, upstream request |
| API gateway / WAF / CDN | Request/response header, body mẫu, security event |
| APM / distributed tracing | Span attributes, HTTP header capture, baggage |
| Error monitoring | Breadcrumbs, request context, local variables, stack context |
| Browser analytics | URL, form fields, event properties, session replay |
| Crash reporting | Memory snapshot, request object, local variable, console output |
| Audit log | Token claim hoặc credential bị copy vào nội dung event |
| Message broker / queue | Payload hoặc metadata của message chứa token |
| Database query log | Giá trị bind parameter hoặc nội dung truy vấn |
| SIEM / log search | Bản sao được chuyển tiếp từ các nguồn khác |
| Support ticket | Token dán vào nội dung, ảnh chụp, HAR hoặc file debug |
| CI/CD và test report | Token môi trường test hoặc secret từ pipeline |
| Chat/email | Token được gửi để nhờ người khác kiểm tra lỗi |

Một credential có thể bị ghi ở gateway trước khi request tới ứng dụng. Nếu chỉ redaction trong application logger, bản sao ở proxy hoặc WAF vẫn tồn tại.

Cần lập bản đồ đường đi dữ liệu từ client đến resource server, authorization server, telemetry, kho log, backup, nhà cung cấp và quy trình hỗ trợ.

## 4. Các vị trí thường bị bỏ sót

### 4.1. HTTP headers

Các header cần kiểm soát bao gồm:

- `Authorization`;
- `Proxy-Authorization`;
- `Cookie`;
- `Set-Cookie`;
- header tùy chỉnh như `X-Access-Token`, `X-Api-Key`, `X-Session-Token`;
- `DPoP` và header chứa assertion/proof theo profile;
- header được middleware hoặc gateway thêm vào để chuyển credential.

Tên HTTP header không phân biệt chữ hoa/chữ thường. Redaction phải chuẩn hóa tên header trước khi so khớp, tránh chỉ che `Authorization` nhưng bỏ sót `authorization` hoặc biến thể viết hoa khác.

Với `Cookie`, cách an toàn mặc định là không ghi toàn bộ header. Nếu thật sự cần ghi một phần cookie không nhạy cảm, parser phải hiểu đúng cú pháp cookie và allowlist tên cookie được phép. Không dùng thao tác cắt chuỗi đơn giản vì có thể che sai giá trị hoặc để lộ cookie đứng sau dấu phân cách.

`Set-Cookie` là response header; nó có thể chứa session credential mới. Cần redaction cả request lẫn response.

### 4.2. URL và query string

Không đưa bearer token vào URL. URL có thể xuất hiện trong browser history, reverse proxy log, analytics, referrer, cache, error page và hệ thống giám sát.

Nếu hệ thống cũ đã nhận token qua query string, cần che các tham số như:

- `access_token`;
- `refresh_token`;
- `id_token`;
- `token`;
- `code`;
- `code_verifier`;
- `client_secret`;
- `assertion`;
- `session`;
- `state` và `nonce` nếu chúng gắn với transaction xác thực.

Tên tham số có thể khác chữ hoa/chữ thường hoặc được mã hóa URL. Redaction cần parse query đúng cách, giải mã tên tham số theo quy tắc phù hợp rồi so với allowlist tên nhạy cảm. Không chỉ tìm một chuỗi cố định trong URL.

### 4.3. Request và response body

Token có thể xuất hiện trong JSON, form-urlencoded, multipart, GraphQL variables, RPC metadata hoặc response body. Ví dụ endpoint token trả access token và refresh token trong JSON; nếu HTTP client tự log response body khi lỗi, credential sẽ được lưu lại.

Không bật body capture toàn cục cho endpoint xác thực. Với các endpoint cần quan sát, chỉ ghi metadata an toàn như status code, content type, kích thước response và thời gian xử lý. Nếu cần ghi body để điều tra dữ liệu nghiệp vụ, phải dùng schema allowlist và loại bỏ trường credential trước khi phát ra khỏi tiến trình.

### 4.4. Exception và thông báo lỗi

Một exception có thể chứa toàn bộ request, URL, header hoặc response body. Không nối token vào message để dễ debug. Không serialize nguyên đối tượng request/response khi bắt lỗi.

Thông báo an toàn nên mô tả loại lỗi và vị trí xử lý, ví dụ `token_signature_invalid`, `token_expired` hoặc `refresh_grant_revoked`; không đưa giá trị token, claim nhạy cảm hay request dump vào message.

## 5. Thiết kế log theo allowlist

Cách an toàn nhất là định nghĩa schema log chỉ chứa những trường cần cho vận hành và điều tra. Mặc định loại bỏ credential, sau đó chủ động thêm metadata đã được phê duyệt.

Ví dụ event an toàn:

~~~json
{
  "event_type": "jwt_validation",
  "request_id": "req-7f31",
  "issuer_alias": "primary-identity-provider",
  "client_alias": "customer-portal",
  "resource_alias": "orders-api",
  "token_profile": "access",
  "validation_result": "rejected",
  "reason_code": "token_expired",
  "http_status": 401,
  "duration_ms": 8,
  "token_size_bucket": "1-2kb",
  "timestamp": "2026-11-16T10:20:30Z"
}
~~~

Event này cung cấp thông tin để phân tích lỗi mà không cần token. Tên issuer/client/resource được thay bằng alias cấu hình nếu URL hoặc định danh thật có thể tiết lộ topology hoặc tenant.

Một schema log có thể cho phép:

- event type và reason code;
- request/correlation ID không chứa credential;
- tên dịch vụ hoặc alias issuer/resource;
- loại token profile;
- kết quả xác minh;
- status code và latency;
- bucket kích thước token;
- phiên bản policy hoặc key set;
- thời điểm và vùng xử lý;
- subject/client reference đã giả danh hóa khi thực sự cần.

Không ghi mặc định:

- raw JWT hoặc opaque token;
- Authorization/Cookie/Set-Cookie header;
- toàn bộ claims payload;
- private key, client secret hoặc password;
- authorization code, PKCE verifier;
- toàn bộ request/response body;
- `sub`, email, tên hoặc tenant ID nguyên bản nếu không cần;
- nonce, `jti`, DPoP proof nguyên vẹn.

## 6. Redaction phải diễn ra trước khi dữ liệu rời khỏi nguồn

Redaction ở hệ thống log trung tâm có ích như lớp phòng thủ bổ sung, nhưng nếu gateway hoặc APM đã nhận và lưu token trước đó thì việc che ở SIEM không xóa được bản sao ban đầu.

Nên áp dụng theo thứ tự:

1. **Tại ứng dụng/client:** không đưa token vào log statement, exception, analytics event hoặc crash context.
2. **Tại middleware và HTTP client/server:** loại bỏ credential header, cookie, body field và query parameter trước khi ghi log.
3. **Tại proxy/gateway/WAF:** tắt capture credential; cấu hình redact header, cookie, URL và body theo endpoint.
4. **Tại APM/error SDK:** tắt tự động thu thập header/body nhạy cảm; chỉ bật các trường allowlist.
5. **Tại collector và SIEM:** áp dụng redaction bổ sung để bắt lỗi cấu hình ở upstream.
6. **Tại kho lưu trữ:** giới hạn truy cập, retention, export và backup.

Không xem redaction downstream là lý do để tiếp tục phát raw token ở upstream. Mỗi thành phần cần có cấu hình và kiểm thử riêng.

### 6.1. Ưu tiên schema-aware redaction

Redaction nên hiểu cấu trúc dữ liệu:

- nhận diện tên header không phân biệt hoa thường;
- parse cookie và query parameter đúng cú pháp;
- parse JSON/form theo schema cho phép;
- che toàn bộ giá trị của trường nhạy cảm;
- xử lý object lồng nhau và mảng;
- xử lý tên trường alias theo allowlist;
- không serialize đối tượng chứa credential trước khi redaction.

Regex có thể là lớp phát hiện bổ sung nhưng không đủ làm cơ chế duy nhất. Token opaque không nhất thiết có dấu chấm; JWT có thể bị encode, escape hoặc nằm trong trường mang tên khác. Regex nhận diện chuỗi ba segment có thể bỏ sót token và cũng có thể che nhầm dữ liệu không phải credential.

### 6.2. Redact toàn bộ giá trị

Không che một phần token rồi giữ phần còn lại, ví dụ chỉ ẩn vài ký tự đầu/cuối, trừ khi có nhu cầu đã được đánh giá và chính sách rõ. Một phần token vẫn có thể giúp tương quan, nhận diện hoặc vô tình để lộ cấu trúc.

Giá trị thay thế nên đơn giản, ví dụ `[REDACTED]`. Không ghi token đã decode, payload đã bỏ chữ ký hoặc token đã mã hóa lại. Các biến thể này vẫn có thể chứa dữ liệu nhạy cảm hoặc credential còn sử dụng được.

### 6.3. Fail closed khi không thể redact

Nếu logger không thể parse một trường có khả năng chứa credential, lựa chọn an toàn là bỏ trường hoặc bỏ toàn bộ body/header khỏi log. Không ghi raw dữ liệu vì “redaction lỗi”.

Với endpoint token, endpoint callback OIDC và endpoint refresh, nên tắt body logging mặc định. Có thể ghi metadata kỹ thuật riêng đã được allowlist.

## 7. Cấu hình APM và distributed tracing

APM thường tự động thu thập HTTP request/response để giúp chẩn đoán. Điều này có thể vô tình lưu token trong span.

Cần kiểm soát:

- không capture `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `DPoP` hoặc custom credential headers;
- không capture body của token endpoint, callback, login, refresh hoặc endpoint chứa credential;
- không đưa token vào span name, attributes, events hoặc exception details;
- không đưa token, authorization code, nonce hoặc session ID vào trace baggage;
- không tạo URL span có query string nhạy cảm;
- kiểm tra agent/instrumentation tự động thêm thuộc tính trước khi export;
- giới hạn quyền đọc trace và thời gian lưu.

Trace context/baggage có thể được truyền qua nhiều dịch vụ. Một token bị thêm vào baggage có thể lan rộng tới toàn bộ service graph. Chỉ truyền correlation ID hoặc metadata an toàn; không dùng baggage như kho credential.

## 8. Công cụ phân tích, session replay và analytics

Browser analytics và session replay có thể ghi nhận URL, click, form input, DOM text hoặc network request. Không cho các công cụ này thu thập:

- access/refresh/ID token;
- session cookie;
- authorization code;
- password, OTP và code verifier;
- nội dung form xác thực;
- response body từ token endpoint;
- dữ liệu claim hoặc hồ sơ cá nhân không cần cho phân tích.

Cấu hình masking ở cả phía client và collector. Nếu công cụ có chế độ allowlist, chỉ gửi event và thuộc tính đã định nghĩa. Không chỉ dựa vào việc che input field vì token có thể nằm trong URL, JavaScript state, network payload hoặc DOM attribute.

Một event analytics phù hợp có thể là `login_completed`, `token_refresh_failed` hoặc `authentication_step_up_required`, kèm outcome, loại client và reason code đã chuẩn hóa. Không gửi token, email, `sub` hoặc toàn bộ claim làm event property.

## 9. Báo cáo lỗi, crash dump và hỗ trợ kỹ thuật

### 9.1. Error monitoring

SDK báo lỗi có thể tự thu thập breadcrumb, request context, local variables và network metadata. Trước khi gửi dữ liệu ra ngoài:

- tắt capture header/body nhạy cảm;
- scrub request URL và query;
- loại bỏ credential khỏi breadcrumb;
- không đính kèm token vào exception message;
- không gửi local variable chứa token nếu SDK hỗ trợ variable capture;
- giới hạn dữ liệu context được phép đính kèm;
- kiểm tra payload thực tế được gửi tới nhà cung cấp.

### 9.2. Crash dump và memory snapshot

Memory dump có thể chứa token dù ứng dụng không chủ động ghi log. Cần cân nhắc có thực sự cần dump đầy đủ hay không; nếu cần, bảo vệ quyền truy cập, mã hóa khi lưu/truyền, giới hạn thời gian lưu và kiểm soát tải xuống.

Không đưa request object hoặc toàn bộ authentication context vào crash report nếu chỉ cần stack trace, build version và reason code. Dữ liệu dump cần được xử lý như dữ liệu nhạy cảm.

### 9.3. Ticket hỗ trợ và file chẩn đoán

Không yêu cầu người dùng gửi JWT thật, refresh token, cookie hoặc authorization code để điều tra. Hướng dẫn họ cung cấp:

- request ID/correlation ID;
- timestamp và timezone;
- endpoint alias;
- HTTP status và reason code;
- loại client và phiên bản ứng dụng;
- token profile và bucket kích thước;
- thông tin đã giả danh hóa theo quy trình.

Nếu cần tái hiện lỗi, dùng token giả lập ở môi trường test với khóa test riêng. HAR, network trace, screenshot và console export phải được kiểm tra/redact trước khi chia sẻ.

## 10. Correlation khi không lưu raw token

Đội vận hành đôi khi cần biết nhiều sự kiện có liên quan đến cùng một credential hay không, ví dụ điều tra refresh token reuse. Không cần lưu raw token để làm điều đó.

Một lựa chọn là tạo fingerprint bằng HMAC với khóa bí mật dành riêng cho mục đích correlation:

~~~text
fingerprint = truncate(
    HMAC_SHA256(correlationKey, rawToken),
    128_bits
)
~~~

Cần áp dụng các điều kiện:

- dùng khóa HMAC riêng, không tái sử dụng signing key hoặc encryption key;
- quản lý version và rotation của correlation key;
- giới hạn ai có thể đọc fingerprint;
- chỉ tạo fingerprint khi có mục đích điều tra được phê duyệt;
- không đưa fingerprint vào metric label có cardinality cao;
- không dùng fingerprint thay cho token validation hoặc authorization;
- giới hạn retention và khả năng liên kết giữa các hệ thống.

Fingerprint vẫn là dữ liệu giả danh hóa có thể liên kết sự kiện với cùng credential. Nó không phải dữ liệu hoàn toàn vô danh. Nếu không cần correlation theo token, không tạo fingerprint.

Không dùng raw SHA-256 token như một mặc định không cần đánh giá. HMAC giúp người chỉ có log khó kiểm tra candidate token offline nếu không có khóa HMAC, nhưng khóa HMAC vẫn phải được bảo vệ.

## 11. Giảm dữ liệu claim trong audit và telemetry

Ngay cả khi token được redact, log có thể vẫn chứa claims được copy ra ngoài. Ví dụ ghi toàn bộ `sub`, `email`, `groups`, `roles`, `tenant_id`, `acr` và `amr` có thể tạo hồ sơ hoạt động nhạy cảm.

Hãy phân biệt:

- **Authentication event:** ai/ứng dụng nào đã xác thực, kết quả và thời điểm theo mức cần thiết.
- **Authorization event:** quyết định cho phép/từ chối, resource class, action và reason code.
- **Token lifecycle event:** phát hành, refresh, revoke, expiry hoặc reuse detection.
- **Security incident event:** credential nghi bị lộ, proof thất bại hoặc replay.

Dùng subject reference giả danh hóa hoặc mã nội bộ được kiểm soát khi cần điều tra. Không dùng email hoặc tên làm định danh log mặc định. Nếu cần biết role/scope, log policy category hoặc quyền đã chuẩn hóa thay vì toàn bộ claim.

Cũng cần giới hạn cardinality metric. Không dùng token, `sub`, `jti`, email hoặc session ID làm nhãn metric; chúng tạo dữ liệu lớn và có thể làm lộ danh tính. Metric nên dùng reason code, token profile, client class, resource alias và bucket.

## 12. Quyền truy cập, retention và chia sẻ dữ liệu log

Redaction là bước đầu; dữ liệu log sau đó vẫn cần được quản lý.

- Phân quyền theo vai trò và nhu cầu công việc.
- Tách quyền quản trị log khỏi quyền truy cập hệ thống xác thực khi có thể.
- Mã hóa log khi truyền và khi lưu.
- Ghi audit cho thao tác tìm kiếm, export và chia sẻ dữ liệu nhạy cảm.
- Giới hạn retention theo mục đích và yêu cầu pháp lý.
- Kiểm soát backup, snapshot, archive và bản sao của nhà cung cấp.
- Hạn chế tải log về máy cá nhân.
- Xóa hoặc hết hạn dữ liệu theo lịch đã định, bao gồm các bản sao có thể quản lý.
- Đánh giá vị trí lưu trữ, nhà cung cấp và quyền truy cập xuyên biên giới.
- Không gửi log có dữ liệu nhạy cảm vào workspace công cộng hoặc công cụ AI chưa được phê duyệt.

Nếu phát hiện token đã vào kho log, cần xem xét toàn bộ bản sao, quyền truy cập, retention và backup; không giả định xóa một bản ghi ở dashboard sẽ xóa mọi bản sao.

## 13. Ví dụ trước và sau khi redact

### 13.1. Log không an toàn

~~~text
POST /oauth/token?client_id=portal
Authorization: Basic [CLIENT-CREDENTIAL]
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=[REFRESH-TOKEN]

Response:
{
  "access_token": "[ACCESS-TOKEN]",
  "refresh_token": "[ROTATED-REFRESH-TOKEN]",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

Nếu HTTP logger ghi request/response như trên, nó lưu cả client credential, refresh token cũ và token mới.

### 13.2. Log an toàn hơn

~~~json
{
  "event_type": "oauth_token_refresh",
  "request_id": "req-a81c",
  "client_alias": "portal",
  "grant_reference": "grant-9d2f",
  "result": "success",
  "access_token_ttl_seconds": 300,
  "refresh_rotation": "performed",
  "http_status": 200,
  "duration_ms": 42,
  "timestamp": "2026-11-16T10:20:30Z"
}
~~~

Event thứ hai ghi kết quả và metadata cần thiết. Không cần ghi token response, request body hoặc Authorization header.

### 13.3. Exception không nên chứa response body

Không an toàn:

~~~text
Refresh failed. Response was: [FULL TOKEN RESPONSE]
~~~

An toàn hơn:

~~~text
Token refresh rejected: reason=refresh_grant_revoked request_id=req-a81c
~~~

Reason code nên đến từ tập giá trị đã chuẩn hóa. Không đưa nội dung server tùy ý hoặc dữ liệu đầu vào của attacker vào log mà không xử lý, vì chúng cũng có thể gây log injection.

## 14. Quy trình triển khai redaction

Một quy trình có thể áp dụng:

1. **Lập inventory credential:** xác định tất cả token, cookie, code, key và header nhạy cảm.
2. **Vẽ data flow:** liệt kê client, gateway, proxy, service, APM, analytics, crash reporting, SIEM, backup và support.
3. **Định nghĩa schema log allowlist:** xác định trường được phép ghi theo từng event.
4. **Tắt capture mặc định:** đặc biệt với Authorization, Cookie, Set-Cookie, body endpoint xác thực và query string.
5. **Cài redaction tại nguồn:** xử lý header, cookie, URL, body, exception và telemetry trước khi export.
6. **Thêm defense-in-depth:** collector và SIEM có lớp phát hiện/redaction bổ sung.
7. **Giới hạn dữ liệu cá nhân:** giả danh hóa subject, alias issuer/client và bỏ claim không cần.
8. **Bảo vệ log store:** RBAC, encryption, audit, retention và kiểm soát export.
9. **Kiểm thử mọi sink:** dùng canary credential giả để xác minh không xuất hiện trong log/trace/report.
10. **Giám sát cấu hình:** kiểm tra sau mỗi lần nâng cấp agent, gateway, SDK hoặc thêm dịch vụ mới.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Request / Response có credential"] --> B["Application và middleware"]
    B --> C["Allowlist event schema"]
    C --> D["Redact header, cookie, URL, body, exception"]
    D --> E["APM / Proxy / Analytics / Error SDK"]
    E --> F["Collector redaction bổ sung"]
    F --> G["Log store / SIEM"]
    G --> H["RBAC, encryption, audit, retention"]
    D --> I["Safe operational metadata"]
    I --> G
    J["Canary tests và config audit"] --> D
    J --> E
    J --> F
~~~

Redaction ở collector là lớp bổ sung. Các thành phần đầu nguồn vẫn phải tránh thu thập credential trước khi gửi dữ liệu.

## 15. Kiểm thử để phát hiện rò rỉ

Kiểm thử phải bao phủ toàn bộ pipeline, không chỉ unit test của logger.

| Nhóm | Kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Authorization header | Gửi canary bearer token | Không xuất hiện raw token trong log |
| Header casing | Dùng authorization, AUTHORIZATION | Đều được redact |
| Cookie | Gửi session cookie trong request | Giá trị cookie không xuất hiện |
| Set-Cookie | Server phát session cookie | Response cookie không bị log |
| Custom header | Gửi X-Access-Token hoặc header đã đăng ký | Được redact |
| Query | Đặt token/code trong query string | URL log không còn giá trị nhạy cảm |
| JSON body | Token nằm trong object lồng nhau/mảng | Trường nhạy cảm bị loại bỏ |
| Form body | Refresh token và code verifier | Body không bị capture |
| Token endpoint response | Response có access/refresh token | Không có response body trong telemetry |
| Exception | Lỗi chứa request/response object | Message và context không chứa credential |
| APM | HTTP auto instrumentation | Span không chứa credential header/body |
| Analytics | Session replay/form capture | Không thu thập token và trường xác thực |
| Crash report | Local context có token | Token không được đính kèm |
| Support export | HAR và screenshot | Có bước redact trước chia sẻ |
| Log injection | Giá trị chứa newline/control characters | Không thể giả mạo log record |
| Correlation | Bật fingerprint theo policy | Chỉ HMAC fingerprint được phép; raw token vắng mặt |
| Retention | Hết thời hạn lưu | Dữ liệu hết hạn theo policy ở các bản sao được quản lý |
| Config drift | Nâng cấp SDK/agent | Kiểm thử xác nhận redaction vẫn hoạt động |

### 15.1. Dùng canary credential giả

Trong môi trường test, tạo chuỗi canary riêng không có quyền truy cập thật, sau đó đưa nó qua các đường xử lý:

- Authorization header;
- cookie;
- query parameter;
- request/response body;
- exception;
- trace attribute;
- analytics event;
- crash report giả lập.

Sau đó tìm canary trong mọi sink test. Nếu xuất hiện ở bất kỳ nơi nào, pipeline chưa đạt. Không dùng token production làm dữ liệu kiểm thử redaction.

### 15.2. Kiểm thử sau thay đổi cấu hình

Redaction có thể bị vô hiệu hóa khi:

- thêm agent APM mới;
- nâng cấp gateway;
- bật debug mode;
- thêm middleware HTTP;
- thay đổi schema event;
- bật session replay;
- thay đổi nhà cung cấp error monitoring.

Đưa kiểm thử canary vào CI/CD và kiểm tra cấu hình production định kỳ. Một cấu hình đã đúng ở phiên bản trước không bảo đảm vẫn đúng sau khi thay đổi instrumentation.

## 16. Xử lý khi token đã bị ghi vào log

Nếu phát hiện raw token hoặc credential trong log, xem đó là sự cố lộ credential và đánh giá mức độ sử dụng được của dữ liệu.

1. Xác định loại credential, issuer, client, subject, audience và thời điểm bị ghi.
2. Xác định log sink, index, trace, analytics, crash report, export, backup và nhà cung cấp đã nhận bản sao.
3. Xác định ai có quyền đọc hoặc đã truy cập dữ liệu.
4. Đánh giá token còn hiệu lực không; kiểm tra log truy cập và dấu hiệu sử dụng bất thường.
5. Thu hồi refresh token/grant hoặc session liên quan khi phù hợp.
6. Với access token JWT, áp dụng cơ chế revoke/introspection/denylist nếu có; nếu không, đánh giá cửa sổ còn hiệu lực và giảm thiểu theo policy.
7. Nếu client secret hoặc private signing key bị lộ, xoay credential/key theo quy trình quản lý khóa.
8. Với authorization code hoặc PKCE verifier, kiểm tra transaction và vô hiệu hóa giao dịch còn hiệu lực.
9. Hạn chế truy cập log và phối hợp xóa/redact bản sao có thể quản lý theo quy trình retention/incident.
10. Sửa nguồn ghi log và thêm test hồi quy trước khi đóng sự cố.

Không chỉ xóa token khỏi một dashboard. Cần xem cả bản sao downstream, export, backup và dữ liệu đã tải về. Nếu không thể xóa backup ngay, giới hạn truy cập và để dữ liệu hết hạn theo lịch an toàn đã được phê duyệt.

## 17. Những sai lầm cần tránh

- Ghi raw JWT vào log để tiện debug.
- Nghĩ JWT đã ký hoặc Base64URL nên không cần bảo vệ.
- Redact Authorization nhưng quên Cookie, Set-Cookie, DPoP hoặc custom headers.
- Chỉ che token trong application log mà bỏ qua gateway, proxy và APM.
- Tắt redaction ở debug mode hoặc môi trường staging có dữ liệu thật.
- Log toàn bộ request/response body từ token endpoint.
- Ghi exception kèm request object hoặc response body.
- Gửi token vào analytics, session replay, crash report hoặc support ticket.
- Decode JWT rồi log toàn bộ claims thay vì raw token.
- Dùng regex nhận diện JWT làm lớp bảo vệ duy nhất.
- Chỉ che vài ký tự đầu/cuối và giữ phần còn lại.
- Dùng token fingerprint trong metric label hoặc mở rộng quyền đọc fingerprint.
- Dùng hash không khóa mà không đánh giá khả năng tương quan và tấn công dò.
- Giữ log vô thời hạn hoặc không quản lý backup/export.
- Dùng credential production làm canary test.
- Cho phép redaction lỗi rồi ghi raw dữ liệu làm fallback.

## 18. Checklist triển khai

**Credential inventory:**

- [ ] Liệt kê access token, refresh token, ID Token, assertion, DPoP proof, session cookie và authorization code.
- [ ] Đưa password, client secret, private key, API key, PKCE verifier và recovery code vào danh sách cấm log.
- [ ] Xác định claim/PII cần hạn chế trong audit và telemetry.

**Nguồn phát sinh log:**

- [ ] Application, HTTP client/server và middleware không log credential.
- [ ] Proxy, gateway, CDN và WAF đã tắt hoặc redact header/body/query nhạy cảm.
- [ ] APM/tracing không capture auth headers, cookies, body hoặc baggage chứa credential.
- [ ] Analytics/session replay và crash SDK có masking phù hợp.
- [ ] Support/HAR/screenshot có quy trình redact trước chia sẻ.

**Redaction và schema:**

- [ ] Log event dùng allowlist schema.
- [ ] Redaction nhận diện header không phân biệt hoa thường.
- [ ] Cookie, Set-Cookie, URL, JSON/form body và exception được xử lý.
- [ ] Redaction diễn ra trước khi dữ liệu rời khỏi nguồn.
- [ ] Nếu không thể redact, trường hoặc payload bị loại bỏ.
- [ ] Regex chỉ là lớp bổ sung, không phải cơ chế duy nhất.

**Vận hành và kiểm thử:**

- [ ] Log store có RBAC, encryption, audit và retention.
- [ ] Subject/client/issuer được alias hoặc giả danh hóa khi phù hợp.
- [ ] Token fingerprint chỉ dùng khi cần và được bảo vệ.
- [ ] Canary test tìm kiếm mọi sink và chạy lại sau nâng cấp SDK/agent.
- [ ] Có quy trình xử lý credential đã bị ghi hoặc export.
- [ ] Không sử dụng token production trong kiểm thử.

## 19. Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách truyền bearer token và rủi ro khi credential bị lộ.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và authorization code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token và giảm rủi ro rò rỉ credential.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof và token binding.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi log, kiểm soát log và bảo vệ log.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý secret, vòng đời và kiểm soát truy cập.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): kiểm soát quyền truy cập và nguyên tắc least privilege.

**Ghi nhớ:** Token là credential, không phải dữ liệu debug. Hãy thiết kế log theo allowlist, redact header/cookie/URL/body ngay tại nguồn, tắt capture tự động trong APM và analytics, không đưa token vào exception hoặc support report, đồng thời kiểm thử mọi sink bằng canary giả. Khi token đã bị ghi, đánh giá và xử lý như sự cố lộ credential.

