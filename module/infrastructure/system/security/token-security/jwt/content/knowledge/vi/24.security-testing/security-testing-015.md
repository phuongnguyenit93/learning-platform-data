# Kiểm tra không lộ token trong nhật ký và phản hồi lỗi

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Kiểm thử bảo mật  
> **Phạm vi:** Kiểm thử việc bảo vệ access token, refresh token, JWT và credential liên quan khỏi bị lộ qua log, tracing, hệ thống quan sát, phản hồi HTTP và kênh hỗ trợ; áp dụng ở mức giao thức/hệ thống, không phụ thuộc Java, Spring hay framework cụ thể.

Token là credential. Nếu access token, refresh token hoặc session credential xuất hiện trong log hay phản hồi lỗi, người có quyền đọc những dữ liệu đó có thể sử dụng token trong thời gian nó còn hiệu lực. Một JWT có chữ ký hợp lệ vẫn có thể bị phát lại khi bị sao chép; việc token chỉ xuất hiện trong môi trường vận hành nội bộ không làm nó trở nên vô hại.

Rò rỉ thường xảy ra ngoài đoạn code xác minh JWT: gateway ghi nguyên Authorization header, tracing tự thu thập request headers, exception đính kèm request body, APM chụp biến cục bộ hoặc nhân viên hỗ trợ sao chép request thật vào ticket. Vì vậy, kiểm thử cần đi theo toàn bộ đường đi của request và credential.

Nguyên tắc thiết kế an toàn là **không ghi credential vào log nếu không có nhu cầu nghiệp vụ bắt buộc**. Khi cần tương quan sự kiện, hãy dùng request ID hoặc một fingerprint có kiểm soát thay vì raw token. Phản hồi gửi cho client cũng chỉ nên chứa mã lỗi và thông tin xử lý cần thiết; không trả token, payload nhạy cảm, khóa, chữ ký hay chi tiết nội bộ của verifier.

## 1. Xác định dữ liệu nào phải được bảo vệ

### 1.1. Token và credential cần che giấu

Danh sách cần đưa vào threat model và kiểm thử:

- Access token dạng JWT hoặc opaque token.
- Refresh token và refresh-token family identifier nếu có thể dùng để suy ra credential.
- ID token trong OpenID Connect.
- Session cookie, session identifier và bearer credential của ứng dụng.
- JWT ký hoặc mã hóa dùng cho mục đích nghiệp vụ.
- DPoP proof JWT trong cửa sổ còn có thể phát lại.
- Authorization code và các credential OAuth trong quá trình callback/token exchange.
- Client secret, API key, private key, HMAC secret và credential dùng để gọi dịch vụ khác.
- Password reset token, email verification token và transaction/action token.

Không phải mọi định danh đều là bí mật tương đương nhau. Tuy nhiên, dữ liệu có thể dùng để tiếp quản phiên, xin token mới hoặc xác nhận một hành động phải được xử lý như credential.

### 1.2. JWT có thể lộ dữ liệu ngay cả khi không lộ private key

JWS JWT thường có header và payload được Base64url encode, không được mã hóa. Người có token có thể decode để đọc claims như:

- Subject, client, tenant hoặc session reference.
- Issuer, audience và scope.
- Thời điểm phát hành/hết hạn.
- Email, role hoặc dữ liệu nghiệp vụ nếu issuer đưa vào payload.

Vì vậy, việc log riêng payload đã decode vẫn có thể làm lộ dữ liệu cá nhân, quyền và thông tin phiên. Không được cho rằng chỉ raw compact token mới nhạy cảm.

JWE bảo vệ tính bí mật của nội dung khi được cấu hình đúng, nhưng chính compact JWE vẫn là credential có thể bị phát lại nếu hệ thống dùng nó như bearer token. Không ghi ciphertext token vào log với giả định “không đọc được nên không sao”.

### 1.3. Những biểu diễn cần tìm

Kiểm thử không chỉ tìm một chuỗi JWT có ba segment. Cần tìm:

- Authorization header với scheme Bearer hoặc DPoP.
- Cookie header và Set-Cookie response.
- Form/body field như access_token, refresh_token, id_token, code hoặc client_secret.
- Query parameter và fragment có tên token/credential.
- JWT compact serialization, JWE compact serialization và opaque token.
- Token đã URL-encode, JSON-escaped hoặc Base64-encoded.
- Claims đã decode, DPoP proof, token fingerprint hoặc token prefix nếu policy cấm.
- Exception, stack trace, debug dump hoặc serialized request object chứa credential.

Regex nhận diện JWT chỉ là một tín hiệu. Opaque token không có cấu trúc JWT, token bị chia nhỏ hoặc credential được đặt dưới tên field tùy biến có thể không khớp regex. Cần kết hợp kiểm tra theo vị trí dữ liệu, tên header/field và canary test.

## 2. Các bề mặt có thể làm lộ token

### 2.1. Log ứng dụng

Các điểm rủi ro:

- Log toàn bộ request/response object.
- Log header khi bắt đầu hoặc kết thúc request.
- Ghi Authorization header khi xác minh thất bại.
- Log body của token endpoint hoặc callback.
- Debug claims bằng cách serialize toàn bộ payload.
- Exception message chứa token đầu vào.
- Ghi request/response khi retry hoặc timeout.

### 2.2. Gateway, reverse proxy, WAF và load balancer

Hạ tầng biên có thể ghi:

- Request headers, đặc biệt Authorization và Cookie.
- Query string và URL đầy đủ.
- Request/response body.
- WAF sample hoặc forensic capture.
- Upstream request khi retry.
- Header được thêm bởi proxy như forwarded metadata.

Chính sách redaction tại ứng dụng không tự bảo vệ log do gateway hoặc WAF tạo ra. Mỗi sản phẩm hạ tầng cần được cấu hình và kiểm thử riêng.

### 2.3. Tracing, APM và telemetry

Agent quan sát có thể tự thu thập:

- HTTP headers và body.
- Span attributes.
- Exception và stack trace.
- Request context hoặc baggage.
- Local variables và breadcrumbs.
- Error snapshot hoặc session replay.

Không giả định APM chỉ lưu metadata. Hãy kiểm tra cấu hình capture mặc định, custom instrumentation và dữ liệu được gửi tới nhà cung cấp bên ngoài.

### 2.4. Audit log, SIEM và event stream

Audit log thường có thời gian lưu dài và được sao chép sang SIEM, data lake hoặc queue. Nếu event chứa raw token, bản sao có thể tồn tại ở nhiều nơi sau khi log gốc đã bị xóa.

Audit event nên mô tả **ai, hành động gì, trên tài nguyên nào, kết quả ra sao và khi nào** bằng định danh phù hợp. Không cần đính kèm credential đã dùng để thực hiện hành động.

### 2.5. Error reporting và crash dump

Token có thể xuất hiện trong:

- Exception context.
- Crash dump hoặc memory snapshot.
- Breadcrumb trước khi lỗi xảy ra.
- Form data và request metadata.
- Error tracking attachment.
- Support bundle được người dùng tải lên.

Crash dump có thể chứa nhiều dữ liệu runtime hơn log thông thường. Cần kiểm soát quyền truy cập, thời gian lưu và quy trình xuất dữ liệu.

### 2.6. Phản hồi HTTP và giao diện người dùng

Các vị trí cần kiểm tra:

- Response body và error details.
- Header như WWW-Authenticate, Location, Set-Cookie và custom debug headers.
- Redirect URL và query string.
- HTML error page.
- GraphQL error extensions hoặc RPC metadata.
- Thông báo hiển thị trong giao diện và thông tin copy-to-clipboard.

Phản hồi lỗi không được echo token hoặc trả payload đã decode chỉ để giúp debug.

### 2.7. Kênh hỗ trợ và công cụ phát triển

Token có thể bị sao chép vào:

- Ticket hỗ trợ, chat nội bộ, email.
- Screenshot hoặc HAR file.
- Browser developer tools export.
- Bug report, issue tracker và tài liệu hướng dẫn.
- Test fixture hoặc file mẫu trong repository.

Quy trình hỗ trợ phải yêu cầu redaction trước khi người dùng gửi request capture. Không dùng token production trong ví dụ hoặc test fixture.

## 3. Threat model và đường đi dữ liệu

### 3.1. Luồng dữ liệu điển hình

~~~mermaid
flowchart TD
    A[Client gửi token] --> B[Gateway / WAF]
    B --> C[Application / JWT verifier]
    C --> D[Downstream services]
    B --> E[Gateway logs]
    C --> F[Application logs]
    C --> G[Tracing / APM]
    D --> H[Service logs / event stream]
    C --> I[HTTP error response]
    E --> J[SIEM / log storage]
    F --> J
    G --> K[Observability provider]
    H --> J
    I --> L[Client / support capture]
~~~

Credential có thể bị sao chép ở bất kỳ điểm nào. Cần xác định mọi nơi có thể đọc header/body và mọi sink lưu dữ liệu sau đó.

### 3.2. Tài sản, threat actor và tác động

| Thành phần | Nguy cơ | Tác động |
|---|---|---|
| Access token | Người có quyền đọc log lấy token còn hạn | Gọi API trái phép |
| Refresh token | Token xuất hiện trong log token endpoint | Duy trì phiên hoặc xin access token mới |
| ID token | Claims định danh bị lộ hoặc bị dùng sai flow | Lộ dữ liệu và nhầm lẫn xác thực |
| DPoP proof | Proof bị sao chép trong replay window | Replay request nếu kiểm soát proof không đủ |
| Session cookie | Cookie bị log ở gateway/APM | Chiếm phiên |
| Error response | Token/claims/stack trace bị trả cho client | Rò rỉ credential và thông tin nội bộ |
| Log/SIEM | Quyền truy cập quá rộng hoặc retention dài | Mở rộng phạm vi sự cố |

Threat actor có thể là người ngoài xâm nhập hệ thống log, tài khoản nhân viên bị chiếm, nhân viên có quyền vượt nhu cầu, nhà cung cấp observability hoặc một service downstream bị xâm phạm.

### 3.3. Trust boundary

Phân biệt:

- Dữ liệu request do client kiểm soát.
- Dữ liệu đã được verifier xác minh.
- Dữ liệu log được ghi bởi application.
- Dữ liệu log được thu thập bởi agent/gateway độc lập.
- Dữ liệu được export tới hệ thống bên ngoài.

Một thành phần đã xác minh token không có nghĩa mọi thành phần downstream được phép nhận raw token. Hãy truyền kết quả xác thực tối thiểu cần thiết, không chuyển credential chỉ để tiện logging hoặc tracing.

## 4. Nguyên tắc thiết kế log an toàn

### 4.1. Không log credential theo mặc định

Không ghi:

- Raw Authorization header.
- Cookie header hoặc session cookie value.
- Raw JWT/JWE/opaque token.
- Refresh token hoặc authorization code.
- DPoP proof đầy đủ.
- Client secret, API key hoặc private key.
- Toàn bộ claims/payload chỉ để debug.

Nếu một use case đặc biệt thực sự cần giữ credential, phải có phê duyệt, mục đích rõ, thời hạn rất ngắn, quyền truy cập tối thiểu và cơ chế bảo vệ riêng. Đây không nên là lựa chọn mặc định.

### 4.2. Ưu tiên allowlist trường log

Tạo log event từ danh sách trường cho phép thay vì serialize toàn bộ request/context rồi cố xóa một số field nhạy cảm.

Ví dụ event an toàn:

~~~json
{
  "event": "token_validation",
  "request_id": "req-8f2a",
  "issuer_id": "identity-provider-main",
  "token_profile": "oauth2-jwt-access",
  "resource": "orders-api",
  "decision": "rejected",
  "reason_code": "invalid_audience",
  "timestamp": "2026-11-16T12:00:00Z"
}
~~~

Đây là ví dụ dữ liệu vận hành. Không đưa raw token, payload, Authorization header hoặc secret vào event.

Allowlist giúp giảm rủi ro khi request object có thêm field mới trong tương lai. Nếu một trường không nằm trong schema log được duyệt, mặc định không ghi nó.

### 4.3. Redaction là lớp phòng vệ bổ sung

Nếu một thành phần buộc phải ghi request metadata, redaction cần diễn ra trước khi dữ liệu rời khỏi thành phần đó:

- Loại bỏ Authorization và Proxy-Authorization.
- Loại bỏ Cookie/Set-Cookie hoặc chỉ giữ thuộc tính không nhạy cảm đã được duyệt.
- Loại bỏ token/code/secret fields trong body và query.
- Che giá trị nhạy cảm trong nested object.
- Redact exception context và tracing attributes.
- Áp dụng cho cả log success, warning, error và debug.

Không chỉ thay token bằng chuỗi che một phần như ba ký tự đầu/cuối nếu chính sách yêu cầu không lộ token. Prefix/suffix có thể hỗ trợ nhận diện credential và tạo khả năng liên kết giữa các sự kiện.

### 4.4. Không dựa duy nhất vào regex

Regex có thể nhận diện compact JWT, nhưng có thể bỏ sót:

- Opaque token.
- JWT trong JSON-escaped string.
- Token URL-encoded hoặc Base64-encoded.
- Credential có tên field tùy biến.
- Token bị chia thành nhiều mảnh.
- Dữ liệu được log dưới dạng object hoặc binary attachment.

Redaction phải hiểu cấu trúc HTTP/header/body và schema của ứng dụng. Với dữ liệu nhạy cảm, allowlist logging thường an toàn hơn denylist pattern.

### 4.5. Hạn chế quyền và retention

Ngay cả log đã redacted vẫn có thể chứa subject, client ID, IP, request path hoặc thông tin nghiệp vụ. Cần:

- Quyền đọc log theo least privilege.
- Phân tách môi trường production/non-production.
- Audit truy cập và export log.
- Mã hóa log khi truyền và khi lưu.
- Retention theo mục đích và nghĩa vụ lưu giữ.
- Hạn chế tải xuống hoặc sao chép log.
- Kiểm soát nhà cung cấp và region lưu dữ liệu.

Redaction không thay thế kiểm soát truy cập; kiểm soát truy cập không thay thế redaction.

## 5. Thiết kế phản hồi lỗi không làm lộ token

### 5.1. Phản hồi nên chứa gì?

Thông thường, client chỉ cần:

- HTTP status hoặc protocol status phù hợp.
- Error code ổn định, không chứa bí mật.
- Mô tả ngắn, không tiết lộ chi tiết xác minh nội bộ.
- Request/correlation ID để tra cứu ở kênh hỗ trợ.
- Hướng xử lý tiếp theo nếu an toàn và cần thiết.

Ví dụ Problem Details:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Authentication required",
  "status": 401,
  "detail": "The supplied credential is invalid or cannot be used for this request.",
  "instance": "urn:request:req-8f2a"
}
~~~

Ví dụ minh họa theo cấu trúc Problem Details. Không echo token, JWT claims, signature, key material hoặc raw parser exception.

### 5.2. Phản hồi không nên chứa gì?

- Raw token hoặc một phần token nếu không được policy cho phép.
- Decoded header/payload hoặc toàn bộ claims.
- Chữ ký, MAC hoặc ciphertext.
- Private key, HMAC secret, client secret.
- JWKS URI nội bộ, filesystem path hoặc secret store location.
- Stack trace, exception class/message chi tiết hoặc parser offset nhạy cảm.
- Thông tin cho biết chính xác token có tồn tại trong hệ thống hay không nếu điều đó tạo oracle.
- Nội dung request body hoặc header đã nhận.

### 5.3. Error code ổn định, chi tiết nội bộ nằm trong log an toàn

Có thể phân biệt nội bộ các nguyên nhân như:

- malformed_token
- invalid_signature
- unsupported_algorithm
- unknown_key
- invalid_issuer
- invalid_audience
- expired_token
- revoked_token
- invalid_dpop_proof

Nhưng phản hồi công khai nên chỉ tiết lộ mức thông tin cần thiết cho client. Ví dụ, với API thông thường, một lỗi xác thực chung có thể phù hợp hơn việc tiết lộ token bị sai chữ ký hay không tồn tại. Nếu giao thức OAuth yêu cầu mã lỗi cụ thể, hãy tuân thủ chuẩn nhưng không thêm raw token hoặc dữ liệu nội bộ vào error_description.

### 5.4. WWW-Authenticate

Với Bearer token, RFC 6750 định nghĩa cách resource server trả challenge và error attributes như error, error_description, error_uri. Giá trị mô tả phải được kiểm soát:

- Không chứa token đã nhận.
- Không đưa claims hoặc chữ ký vào error_description.
- Không trả stack trace hoặc chi tiết key resolver.
- Không echo nguyên header Authorization.
- Không đưa URL debug nội bộ vào error_uri.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Không phải mọi lỗi đều cần error_description. Khi có, mô tả nên ngắn và không nhạy cảm.

### 5.5. Không echo request trong lỗi

Một số API validation trả lại field/value gây lỗi. Với token endpoint hoặc Authorization header, hành vi echo có thể làm lộ credential. Kiểm tra:

- Validation error có trả lại giá trị field không?
- Error handler có đính kèm request body không?
- GraphQL extensions có chứa arguments/context không?
- RPC metadata có bị copy vào trailers không?
- Redirect có giữ query string chứa token/code không?

Thông báo có thể chỉ nêu tên field hoặc error code; không cần trả giá trị bí mật người dùng đã gửi.

## 6. Chuẩn bị bộ test bằng synthetic canary credential

### 6.1. Vì sao cần canary?

Canary là token/credential giả được tạo riêng cho kiểm thử, có chuỗi nhận diện duy nhất. Nó không cấp quyền vào hệ thống thật và không được dùng trong production.

Canary giúp tìm dữ liệu bị sao chép qua nhiều sink mà không phải đưa token thật vào test. Mỗi loại credential nên có marker riêng để biết nguồn rò rỉ:

- CANARY_ACCESS_...
- CANARY_REFRESH_...
- CANARY_SESSION_...
- CANARY_DPOP_PROOF_...
- CANARY_CLIENT_SECRET_...

Nếu test dùng JWT compact, tạo token giả theo cấu trúc hợp lệ cho test fixture nhưng không ký bằng production key. Với opaque token, dùng chuỗi giả đủ giống format mà ứng dụng nhận.

### 6.2. Đặc tính của test fixture

- Chỉ dùng trong môi trường test/staging cô lập.
- Không có quyền truy cập tài nguyên thật.
- Không tái sử dụng credential production.
- Có marker đủ duy nhất để tìm trong log và response.
- Có biến thể URL-encoded/JSON-escaped nếu cần kiểm tra redaction.
- Được vô hiệu hóa hoặc xóa sau test.
- Không commit canary có thể bị nhầm với secret thật vào repository công khai.

### 6.3. Token fixture và vị trí gửi

Gửi canary qua các vị trí ứng dụng thực sự hỗ trợ:

- Authorization: Bearer.
- Authorization: DPoP và DPoP proof header.
- Cookie session.
- JSON field access_token/refresh_token.
- Form body hoặc token exchange request.
- Query parameter trong test âm tính để xác nhận hệ thống không echo/ghi log.

Không thử mọi vị trí tùy tiện trên production. Mục tiêu là bao phủ đúng parser và middleware mà hệ thống đang sử dụng.

## 7. Kiểm thử toàn bộ log và telemetry pipeline

### 7.1. Các sink cần thu thập

Lập inventory và xác định người quản lý:

| Sink | Dữ liệu cần kiểm tra |
|---|---|
| Application logs | Structured fields, exception và debug messages |
| Gateway/proxy logs | Headers, URL, query, body capture |
| WAF/load balancer | Request sample, security event |
| Tracing/APM | Span attributes, headers, body, breadcrumbs |
| Audit log | Event payload và principal metadata |
| SIEM/log aggregator | Dữ liệu sau transform/export |
| Queue/event bus | Event message và retry/dead-letter |
| Crash/error reporting | Stack trace, context, attachment |
| Support bundle | HAR, request dump, diagnostic archive |
| Browser/client telemetry | Frontend error, analytics và session replay |

Một hệ thống có thể redacted ở application log nhưng vẫn lộ token trong gateway access log hoặc APM agent.

### 7.2. Kiểm thử theo từng chặng

1. Gửi request có canary token.
2. Xác nhận request đi qua gateway, application và downstream path như thiết kế.
3. Tạo cả response thành công và response lỗi.
4. Thu thập log/traces/events từ từng sink.
5. Tìm marker canary nguyên bản và các biểu diễn đã encode.
6. Kiểm tra trường nested, exception, attachment và retry.
7. Xác nhận event an toàn vẫn đủ request ID/error code để điều tra.
8. Lặp lại với các loại token và middleware khác nhau.

Không chỉ tìm trong file log thô. Hãy kiểm tra dữ liệu sau khi được agent xử lý, export, transform và lưu ở hệ thống đích.

### 7.3. Kiểm tra dữ liệu bị encode hoặc biến đổi

Canary có thể bị:

- URL encode.
- JSON escape.
- Base64/Base64url encode.
- Chuyển chữ hoa/thường hoặc thêm prefix.
- Tách thành nhiều trường.
- Decode thành JWT payload hoặc claim.

Test harness nên tìm các biểu diễn được dự đoán từ fixture và kiểm tra field names nhạy cảm. Không thể chứng minh không rò rỉ bằng một lần grep chuỗi nguyên bản nếu hệ thống có encoding hoặc serialization.

### 7.4. Kiểm tra cả success và failure path

Các nhánh lỗi thường log nhiều dữ liệu hơn:

- Token malformed.
- Chữ ký sai.
- Hết hạn hoặc chưa đến nbf.
- Issuer/audience sai.
- kid không tồn tại hoặc JWKS timeout.
- JWE decryption/authentication tag thất bại.
- DPoP proof sai hoặc bị replay.
- Status/introspection service không khả dụng.
- Downstream timeout sau khi request đã xác thực.

Kiểm tra cả retry, circuit breaker, dead-letter và fallback. Lỗi phát sinh ở bước sau xác minh cũng không được làm lộ token đã nhận.

## 8. Kiểm thử phản hồi lỗi và kênh client

### 8.1. Kiểm tra response body

Với từng error scenario:

- Kiểm tra body không chứa raw canary.
- Kiểm tra không có decoded JWT header/payload.
- Kiểm tra không echo Authorization/Cookie/body field.
- Kiểm tra không có stack trace hoặc exception message nội bộ.
- Kiểm tra error detail không tiết lộ key material hoặc trust configuration.
- Kiểm tra request ID có thể dùng để tra cứu log an toàn.

### 8.2. Kiểm tra response headers

Kiểm tra:

- WWW-Authenticate không chứa token hoặc raw parser detail.
- Location không redirect token/code tới host ngoài ý muốn.
- Set-Cookie không vô tình đặt credential vào cookie không an toàn.
- Debug/custom headers không chứa token, claims hoặc internal path.
- Cache-Control phù hợp với response chứa thông tin xác thực/lỗi nhạy cảm.

### 8.3. Kiểm tra redirect

OAuth redirect và error redirect cần được xem xét riêng:

- Không đưa access token vào URL.
- Authorization code chỉ xuất hiện theo flow chuẩn và không bị ghi vào access log/referrer không cần thiết.
- State/nonce không bị echo vào trang lỗi hoặc log công khai.
- Redirect URI phải được kiểm soát.
- Error page không copy nguyên query string.
- Referrer policy phù hợp để giảm rò rỉ URL nhạy cảm.

### 8.4. Kiểm tra giao thức ngoài HTTP JSON

Nếu hệ thống dùng GraphQL, gRPC, WebSocket hoặc message broker:

- GraphQL errors không trả lại authorization context.
- gRPC status/trailers không chứa token hoặc metadata nhạy cảm.
- WebSocket close/error message không echo credential.
- Queue dead-letter không chứa raw token nếu không cần.
- Retry metadata và diagnostic event không serialize request headers.

## 9. Tạo correlation mà không ghi token

### 9.1. Dùng request ID

Request ID/correlation ID thường đủ để liên kết:

- Request từ gateway tới application.
- Validation decision.
- Audit event.
- Downstream call.
- Error response.

ID này nên do hệ thống tạo hoặc xác minh format/độ dài, không dùng token làm request ID. Nếu nhận correlation ID từ client, cần giới hạn ký tự và tránh để nó điều khiển log injection.

### 9.2. Token fingerprint có kiểm soát

Nếu thực sự cần nhận diện cùng một token giữa các sự kiện mà không ghi raw token, có thể dùng keyed HMAC với một logging key riêng:

~~~text
fingerprint = truncate(HMAC-SHA-256(logging_key, token))
~~~

Yêu cầu:

- logging_key tách biệt với issuer signing key, HMAC token secret và encryption key.
- Key được bảo vệ trong secret manager/KMS.
- Fingerprint chỉ dùng để tương quan, không được chấp nhận như credential.
- Giới hạn quyền truy cập và thời gian lưu fingerprint.
- Có kế hoạch rotate logging_key.
- Không dùng fingerprint làm nhãn metric có cardinality cao.

Fingerprint vẫn là dữ liệu có thể liên kết hoạt động của một credential và có thể mang tính nhạy cảm. Không tạo fingerprint nếu request ID hoặc event ID đã đủ.

### 9.3. Không dùng jti tùy tiện

jti là claim định danh token, không phải secret theo mặc định nhưng có thể giúp liên kết các request của cùng token. Nếu log jti:

- Xác định mục đích và retention.
- Đánh giá khả năng liên kết hoạt động người dùng.
- Namespace theo issuer.
- Không coi jti là thay thế raw-token redaction.
- Không dùng jti từ token chưa xác minh làm định danh đáng tin cậy.

### 9.4. Trường log đề xuất

Một schema có thể cho phép:

| Trường | Mục đích |
|---|---|
| event_name | Loại sự kiện |
| request_id | Tương quan request |
| issuer_id | Tên định danh issuer đã cấu hình |
| client_id | Client đã được xác minh, nếu cần |
| subject_ref | Định danh đã pseudonymize nếu cần |
| token_profile | Access token, ID token hoặc token nghiệp vụ |
| decision | accepted/rejected |
| reason_code | Mã lý do không chứa credential |
| resource/action | Tài nguyên và hành động |
| timestamp | Thời điểm sự kiện |

Không đưa token, cookie, signature, raw claims hoặc private key vào schema mặc định.

## 10. Quy trình kiểm thử tự động

### 10.1. Test harness khái niệm

~~~text
for each credential_fixture:
    response = send_request_through_full_stack(credential_fixture)

    collect:
        application_logs
        gateway_logs
        traces_and_spans
        audit_events
        error_reports
        downstream_events

    assert response_body does_not_contain(credential_fixture)
    assert response_headers do_not_contain(credential_fixture)

    for each sink in collected_sinks:
        assert sink does_not_contain(raw_fixture)
        assert sink does_not_contain(encoded_variants)
        assert sink does_not_contain(decoded_sensitive_claims)

    assert safe_correlation_fields_are_present(response, collected_sinks)
~~~

Đây là pseudocode mô tả mục tiêu kiểm thử. Việc thu thập log phải dùng API/test export được tổ chức cho phép; không cần cấp quyền production rộng cho test runner.

### 10.2. Test ở cấp middleware

Kiểm tra:

- Redaction middleware chạy trước logger/tracer.
- Logger không serialize toàn bộ request.
- Exception handler không thêm request object vào response.
- Gateway và APM có filter riêng.
- Redaction áp dụng cho cả nested headers/body.
- Field allowlist không tự mở rộng khi schema request thay đổi.

### 10.3. Test regression

Mỗi khi nâng cấp:

- JWT/JOSE library.
- HTTP client/server framework.
- Gateway, WAF hoặc reverse proxy.
- APM/tracing agent.
- Logging SDK/formatter.
- Error reporting SDK.

Hãy chạy lại canary tests. Một bản nâng cấp observability có thể thay đổi default capture và làm lộ header trước đó đã được bỏ qua.

### 10.4. Kiểm tra cấu hình production

Staging không luôn giống production. Xác minh:

- Production log level và debug flag.
- Gateway/WAF capture policy.
- APM header/body capture settings.
- Sampling và error snapshot settings.
- SIEM export transformation.
- Retention và quyền truy cập.
- Các feature flag bật riêng ở production.

Không bật debug logging production chỉ để kiểm thử redaction. Dùng canary và test configuration an toàn hoặc môi trường tương đương.

## 11. Ma trận kiểm thử không rò rỉ token

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| S01 | Access token trong Authorization header, request thành công | Không có raw token trong bất kỳ log/tracing sink nào |
| S02 | Access token sai chữ ký | Error log không ghi token hoặc signature |
| S03 | Access token hết hạn | Response và log chỉ chứa reason code/request ID |
| S04 | Refresh token gửi tới token endpoint | Không ghi body field hoặc raw refresh token |
| S05 | ID token trong OIDC callback | Không log token/payload nhạy cảm |
| S06 | Session cookie trong Cookie header | Không xuất hiện trong access log/APM |
| S07 | DPoP proof header | Không log proof JWT có thể replay |
| S08 | Token dạng opaque | Redaction không phụ thuộc regex JWT |
| S09 | Token URL-encoded hoặc JSON-escaped | Không xuất hiện ở dạng biến đổi trong sink |
| S10 | Token trong query string ở request test âm tính | Không echo và không ghi raw query credential |
| S11 | JWKS timeout/kid không tồn tại | Exception không chứa token hoặc key response nhạy cảm |
| S12 | JWE decryption/tag thất bại | Không log ciphertext/plaintext hoặc key material |
| S13 | Downstream timeout sau xác minh | Retry/tracing không sao chép Authorization header |
| S14 | Gateway/WAF capture | Header/body nhạy cảm bị loại bỏ theo policy |
| S15 | APM exception snapshot | Không thu thập token, cookie hoặc request body nhạy cảm |
| S16 | Audit event | Có actor/action/request ID nhưng không có credential |
| S17 | Error response theo Problem Details | Không có token, claims hoặc stack trace |
| S18 | WWW-Authenticate error response | Không có raw token hoặc parser internals |
| S19 | Redirect/error page | Không echo query string chứa token/code/state |
| S20 | GraphQL/gRPC/WebSocket error | Metadata và error detail không lộ credential |
| S21 | Token xuất hiện trong nested object | Allowlist/redaction xử lý đúng |
| S22 | Exception serialization | Không serialize request/credential object |
| S23 | Log export sang SIEM | Token vẫn được redacted sau transform |
| S24 | Support bundle/HAR capture | Có cảnh báo/redaction trước khi chia sẻ |
| S25 | Logging SDK được nâng cấp | Canary regression test vẫn PASS |
| S26 | Logging key fingerprint bị rotate | Không ảnh hưởng verify token; fingerprint policy được duy trì |
| S27 | Request có token giả với marker duy nhất | Canary không xuất hiện ở bất kỳ sink nào |
| S28 | Raw token không xuất hiện nhưng decoded claims có trong log | Test phải FAIL nếu claims thuộc dữ liệu bị cấm |

## 12. Ứng phó khi phát hiện token trong log hoặc phản hồi

### 12.1. Xác định mức độ phơi nhiễm

1. Xác định credential type: access, refresh, ID, session, DPoP proof hay secret khác.
2. Xác định sink và thời gian bắt đầu/kết thúc có thể chứa dữ liệu.
3. Xác định ai/các hệ thống nào có quyền đọc, export hoặc replicate sink đó.
4. Kiểm tra credential còn hiệu lực hay đã bị thu hồi/hết hạn.
5. Tìm dấu hiệu sử dụng credential từ nguồn bất thường.
6. Xác định bản sao ở SIEM, backup, queue, support ticket và nhà cung cấp.

Không sao chép raw credential sang ticket mới để báo cáo. Dùng request ID, fingerprint được phê duyệt hoặc bản ghi đã redacted.

### 12.2. Chặn khả năng sử dụng

Tùy credential:

- Thu hồi access token/session/grant theo policy.
- Thu hồi refresh token family và yêu cầu xác thực lại.
- Chặn DPoP key hoặc certificate binding nếu key cũng bị lộ.
- Thu hồi client secret/API key nếu đó là credential bị ghi.
- Nếu signing private key hoặc HMAC secret bị lộ, kích hoạt quy trình compromise khóa.
- Phát trạng thái revoke tới verifier/cache và xác minh hiệu lực trên mọi region.

Không mặc định phải rotate issuer signing key chỉ vì một access token bị log. Chọn hành động theo loại credential thực sự bị phơi nhiễm.

### 12.3. Bảo toàn bằng chứng và xử lý bản sao

- Giới hạn quyền đọc sink ngay khi cần.
- Bảo toàn bằng chứng phục vụ điều tra theo quy trình.
- Xác định log/trace/export/backup có chứa credential.
- Áp dụng retention, legal hold và quy trình xóa an toàn phù hợp.
- Không xóa bằng chứng điều tra trước khi có quyết định của người phụ trách.
- Xác minh downstream replica đã được xử lý.

### 12.4. Khắc phục nguồn rò rỉ

- Tắt log header/body hoặc cấu hình allowlist.
- Sửa exception/error handler.
- Cấu hình redaction ở gateway, APM và tracing.
- Cập nhật runbook hỗ trợ và hướng dẫn HAR.
- Thêm canary regression test vào CI/CD.
- Đặt owner cho từng sink và lịch rà soát cấu hình.

## 13. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách làm đúng |
|---|---|---|
| Chỉ redaction ở application logger | Gateway/APM vẫn có thể lưu token | Kiểm thử mọi sink |
| Chỉ tìm chuỗi JWT ba segment | Bỏ sót opaque token và encoded values | Canary + schema-aware inspection |
| Che token một phần | Vẫn lộ credential fragment và khả năng liên kết | Không log credential |
| Log decoded claims thay raw token | Có thể lộ PII, scope và session metadata | Allowlist event fields |
| Chỉ kiểm tra response body | Token có thể nằm trong headers/redirect | Kiểm tra toàn bộ response |
| Chỉ test lỗi xác minh | Success path/tracing vẫn có thể log token | Test cả success và failure |
| Dựa vào log level INFO | Error/APM snapshot vẫn có thể chứa token | Redaction trước mọi sink |
| Echo request để debug | Error response có thể trả credential | Trả error code và request ID |
| Cho rằng log nội bộ không nhạy cảm | Nhân viên/vendor có thể đọc hoặc export | Least privilege và retention |
| Dùng raw token làm correlation ID | Log trở thành kho bearer credential | Request ID hoặc fingerprint có kiểm soát |
| Chỉ purge log gốc | Replica/backup/SIEM còn bản sao | Inventory và xử lý toàn bộ pipeline |
| Rotate mọi signing key sau mọi log leak | Gây gián đoạn mà không đúng nguyên nhân | Xác định credential bị lộ trước khi chọn response |

## 14. Checklist kiểm thử và vận hành

**Phạm vi dữ liệu**

- [ ] Inventory access/refresh/ID/session/DPoP/action token và secret liên quan.
- [ ] Kiểm tra raw token, claims đã decode và mọi dạng encode.
- [ ] Bao gồm opaque token, JWS, JWE và credential trong body/header/cookie.

**Log và observability**

- [ ] Application logs không ghi Authorization, Cookie hoặc raw token.
- [ ] Gateway, proxy, WAF và load balancer có redaction riêng.
- [ ] Tracing/APM/error reporting không capture credential.
- [ ] Audit/event/queue/SIEM không nhận raw token.
- [ ] Exception và crash dump không serialize request credential.
- [ ] Log schema dùng allowlist.

**Phản hồi lỗi**

- [ ] Response body không echo token, claims, signature hoặc stack trace.
- [ ] WWW-Authenticate/error_description không chứa dữ liệu nhạy cảm.
- [ ] Redirect, response headers và error page không làm lộ query/credential.
- [ ] Có request ID/error code để điều tra an toàn.
- [ ] GraphQL/gRPC/WebSocket errors được kiểm tra nếu có.

**Kiểm thử**

- [ ] Có synthetic canary riêng cho từng loại credential.
- [ ] Test success, failure, retry, timeout và downstream errors.
- [ ] Tìm raw, URL-encoded, JSON-escaped và decoded variants.
- [ ] Kiểm tra tất cả sink sau export/transform.
- [ ] Có regression test sau nâng cấp logging/APM/gateway SDK.
- [ ] Test không dùng token production.

**Quản trị và ứng phó**

- [ ] Có owner, access control, encryption và retention cho từng sink.
- [ ] Có quy trình thu hồi credential bị lộ.
- [ ] Có quy trình bảo toàn bằng chứng và xử lý replica/backup.
- [ ] Có runbook và người chịu trách nhiệm kiểm tra lại sau khắc phục.

**Điều cần nhớ:** Token không được phép xuất hiện trong log hoặc phản hồi lỗi chỉ vì request thất bại hay đang chạy ở môi trường nội bộ. Dùng allowlist cho dữ liệu log, redaction ở mọi lớp, response chỉ chứa mã lỗi an toàn và request ID. Kiểm thử bằng canary credential xuyên suốt gateway, application, tracing, audit, SIEM và client response; nếu chỉ kiểm tra một logger hoặc một response body thì chưa đủ.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Cách truyền bearer token và error response/challenge.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth token endpoint và error response.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): Cấu trúc phản hồi lỗi HTTP.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Bảo vệ OAuth credentials và token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và cấu trúc token.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): Dữ liệu nhạy cảm cần loại khỏi log và thực hành quản lý log.
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): Thiết kế lỗi an toàn và tránh tiết lộ thông tin nội bộ.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): Bảo vệ và quản lý credential/secret.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/): Các yêu cầu kiểm chứng bảo mật ứng dụng.
