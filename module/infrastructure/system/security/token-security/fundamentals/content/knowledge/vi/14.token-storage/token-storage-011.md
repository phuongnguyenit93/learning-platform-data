# Không lưu token trong log hoặc analytics

Một lỗi xác thực xảy ra khi gọi API. Để điều tra, lập trình viên bật chế độ ghi toàn bộ HTTP request, bao gồm header **Authorization**. Ngay lập tức access token trong từng request được chuyển vào log tập trung; từ đây nó có thể tiếp tục được sao chép sang APM, tracing, công cụ tìm kiếm log và hệ thống phân tích. Dù API dùng HTTPS và JWT có chữ ký hợp lệ, **một bearer token bị lộ qua log vẫn có thể bị phát lại** khi còn hiệu lực.

Điều đáng ngại hơn: nếu vô tình ghi **refresh token** trong request đến token endpoint, kẻ có được bản sao có thể cố xin **access token mới** trong tương lai. Nếu ghi **OIDC ID token**, payload JWT có thể bộc lộ claims danh tính. Nếu ghi token đã hết hạn, bản sao đó tuy không còn dùng để gọi API nhưng vẫn có thể chứa thông tin nhạy cảm và được lưu trong hệ thống quan sát lâu hơn dự kiến.

**Nguyên tắc của bài học: không lưu giá trị token hoặc những credential có thể tái sử dụng trong log, telemetry, tracing, crash report hay analytics.** Thay vào đó, chỉ thu thập **metadata tối thiểu, đã kiểm chứng hoặc đã tổng hợp**, đủ để vận hành mà không trở thành một kho credential thứ hai.

Bài thuộc chương **Token storage** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối vòng đời JWT/opaque token, access token/refresh token, OAuth 2.0/OIDC, các claims như **iss**, **aud**, **scope**, cơ chế phát hành, xác minh, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài này, bạn có thể nhận diện những đường rò token ngoài ý muốn, thiết kế chính sách log/analytics dạng **allowlist**, hiểu giới hạn của redaction, chọn dữ liệu audit an toàn, kiểm thử chống rò rỉ và ứng cứu khi log đã chứa credential thật.

## 1. Vì sao log có token là một sự cố bảo mật?

Trong hệ thống OAuth 2.0, **client** dùng access token để truy cập **Resource Server**, còn refresh token được dùng tại **token endpoint của Authorization Server**. Một bearer token là bằng chứng có giá trị: bên giữ chuỗi token có thể thử sử dụng nó trong phạm vi quyền và thời hạn hợp lệ, trừ khi có cơ chế sender-constraining hoặc điều kiện bổ sung.

Hệ thống log có phạm vi truy cập khác hẳn nơi token được thiết kế để xuất hiện:

| Nơi dữ liệu xuất hiện | Ai hoặc thành phần nào có thể tiếp cận? | Vấn đề nếu có token |
|---|---|---|
| **Ứng dụng và API trong lúc xử lý** | Thành phần được giao xử lý yêu cầu | Token có thể cần tồn tại tạm thời để xác minh |
| **Log của API hoặc gateway** | Nhân sự vận hành, hệ thống log tập trung, công cụ tìm kiếm | Credential bị giữ ngoài vòng đời xử lý request |
| **Distributed tracing/APM** | Collector, tracing backend, bên cung cấp giám sát | Token có thể đi qua nhiều dịch vụ hoặc tổ chức |
| **Analytics và session replay** | SDK phía client, dịch vụ phân tích hành vi, dashboard | Credential và claims có thể lẫn với sự kiện sản phẩm |
| **Crash report, debug dump, ticket hỗ trợ** | Công cụ chẩn đoán và người hỗ trợ | Bản sao token có thể tồn tại lâu, khó kiểm soát phạm vi |
| **Backup và bản sao log** | Kho lưu trữ dài hạn, bản sao đa vùng | Xóa log chính không đảm bảo đã xóa mọi bản sao |

**Mã hóa TLS bảo vệ đường truyền giữa các điểm kết nối, không ngăn token bị ghi ra log sau khi giải mã tại client, proxy hoặc server.** Chữ ký JWT cũng không mã hóa payload: người có token JWS thông thường có thể Base64url-decode để đọc claims mà không cần private signing key.

Do đó, rủi ro gồm **hai lớp**:

1. **Credential exposure:** token đang hoạt động có thể bị phát lại để gọi API hoặc xin token mới.
2. **Information disclosure:** claims, metadata và thông tin cá nhân vẫn có thể bị đọc sau khi token hết hạn.

Đừng chỉ đặt mục tiêu “log được mã hóa trong database”. Trước hết cần **không đưa credential vào dòng dữ liệu quan sát** nếu hoạt động vận hành không cần đến nó.

## 2. Bản đồ những nơi token dễ lọt vào quan sát

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"access/refresh/ID token"| C["Client / BFF"]
    C -->|"Bearer access token"| G["API gateway"]
    G -->|"Bearer access token"| RS["Resource Server"]
    C -->|"refresh grant"| AS
    C -.->|"Console, RUM, analytics"| A["Event collector"]
    G -.->|"HTTP access/debug log"| L["Log pipeline"]
    RS -.->|"Exception, APM, tracing"| L
    AS -.->|"Token endpoint body/response log"| L
    L --> S["Search, alert, retention, backup"]
    A --> S
~~~

Một request có thể tạo nhiều bản sao mà người phát triển không nhận ra. Các đường thường gặp:

**HTTP headers:** **Authorization**, **Cookie**, **Set-Cookie**, đôi khi một header tùy biến chứa API key hoặc session token.

**HTTP body:** request **grant_type=refresh_token**, response **access_token**, **refresh_token**, **id_token**, body của login/OAuth callback và các payload debug được ghi nguyên.

**URL và query:** access token trong query string là cách truyền nên tránh. Authorization code, state, session identifier hoặc tham số nhạy cảm cũng có thể bị sao chép vào access log, browser history, analytics và referer nếu thiết kế kém.

**Exception/debug:** đoạn code ghi toàn bộ request object, error response, HTTP client interceptor, stack context, thông tin phiên hoặc đối tượng JSON có chứa token.

**Trình duyệt:** console.log, network instrumentation, session replay, analytics SDK tự thu thập URL, form fields, DOM hoặc error breadcrumbs.

**Hạ tầng:** reverse proxy, WAF, service mesh, load balancer, APM agent, OpenTelemetry collector, message broker, job worker, công cụ thử API và hệ thống hỗ trợ. Một số chỉ ghi metadata mặc định, nhưng chế độ **verbose/debug/record body** có thể thay đổi hành vi; phải kiểm chứng cấu hình thực tế.

## 3. Access, refresh, ID token và opaque token: hậu quả khác nhau

| Loại credential | Nếu bị ghi vào log, nguy cơ gì? | Quy tắc lưu log |
|---|---|---|
| **Bearer access token** | Có thể gọi Resource Server đúng audience/scope khi còn hiệu lực; có thể bị phát lại | Không ghi nguyên chuỗi hoặc header Authorization |
| **Refresh token** | Có thể xin access token mới tại AS nếu chưa thu hồi và không bị ràng buộc chặn | Không ghi trong token request/response, kể cả chế độ debug |
| **OIDC ID token** | JWT có thể chứa claims danh tính; bị dùng sai ngữ cảnh hoặc lộ thông tin | Không ghi toàn bộ ID token |
| **Opaque access token** | Chuỗi không cho biết claims, nhưng vẫn là credential dùng được nếu còn hiệu lực | Không coi chuỗi ngẫu nhiên là vô hại |
| **JWT access token** | Credential có thể bị phát lại; payload JWS thường đọc được dù đã ký | Không log JWT; không log toàn bộ payload đã decode |
| **Session cookie / API key** | Có thể tái sử dụng phiên hoặc quyền truy cập tương ứng | Xem là credential và loại khỏi telemetry |
| **Authorization code / PKCE verifier** | Có thể ảnh hưởng khả năng đổi code lấy token khi đủ điều kiện | Không ghi raw giá trị; code là credential ngắn hạn |

**Access token, refresh token, ID token** là phân loại theo mục đích; **JWT/opaque** mô tả hình thức và cách bên nhận kiểm tra. Không được suy rằng opaque token an toàn để log chỉ vì không đọc được claims. Ngược lại, một JWT có chữ ký hợp lệ vẫn phải được xem là **bí mật bearer** khi nó dùng để truy cập tài nguyên.

Khi token bị đánh cắp, **audience** và **scope** có thể giới hạn nơi và quyền nó được sử dụng, nhưng không ngăn người có token phát lại tại **đúng** Resource Server. Với refresh token, client binding, rotation, phát hiện reuse và sender-constraining giúp giảm rủi ro; chúng **không phải lý do để cho phép log token**.

## 4. Không dùng blacklist chuỗi đơn giản làm chiến lược duy nhất

Một cách triển khai thường gặp là ghi toàn bộ request rồi xóa các trường có tên **password** hoặc **token**. Cách làm này dễ bỏ sót:

- Header **Authorization** không chứa từ token trong tên field.
- Token có thể nằm trong **Cookie**, **Set-Cookie**, custom headers, query, JSON lồng nhau hoặc chuỗi lỗi.
- Một SDK có thể đổi tên **accessToken** thành **credential**, **auth**, **session** hoặc **jwt**.
- Exception có thể ghép token vào câu thông báo tự do.
- URL và raw response được ghi ở tầng proxy **trước khi** code ứng dụng thực hiện redaction.
- Token bị tách qua nhiều field hoặc được encode trước khi collector tiếp nhận.

Vì vậy nên ưu tiên **allowlist**: chỉ cho phép thu thập **những trường không nhạy cảm được xác định trước**, thay vì gửi mọi thứ rồi cố xóa những gì nguy hiểm.

### Allowlist metadata thay vì log request thô

Ví dụ log có thể chấp nhận khi đã thiết kế các trường:

~~~json
{
  "event": "authz_decision",
  "request_id": "req-example-104",
  "route_template": "GET /orders/{orderId}",
  "result": "denied",
  "reason_code": "INVALID_AUDIENCE",
  "token_kind": "access_token",
  "http_status": 401
}
~~~

Ví dụ chỉ chứa **giá trị giả, không phải token thật**. Các trường như **token_kind** và **reason_code** chỉ được lấy từ kết quả phân loại/kiểm tra đáng tin hoặc enum do code server kiểm soát; không lấy trực tiếp trường tự khai từ JWT chưa xác minh rồi coi là sự thật.

Những thứ **không** có trong log:

~~~text
Authorization: Bearer <redacted>
Cookie: <redacted>
refresh_token=<redacted>
access_token=<redacted>
id_token=<redacted>
code_verifier=<redacted>
client_secret=<redacted>
~~~

Chuỗi **<redacted>** ở ví dụ chỉ có tác dụng mô tả. Trong thực tế, giải pháp ưu tiên là **không đưa field chứa credential vào event ngay từ đầu**; redaction bổ sung là lớp phòng thủ khi hệ thống đã cần xử lý một cấu trúc chứa dữ liệu nhạy cảm.

### Không phải mọi metadata đều vô hại

**sub**, email, username, tenant ID, **jti**, IP, user agent và trace ID có thể cho phép liên kết hoạt động hoặc nhận diện người dùng. Không tự động log toàn bộ claims sau khi validate chỉ vì claims đó “đã được xác minh”.

Đối với audit có nhu cầu truy vết người dùng thật, phải có chính sách mục đích, phân quyền xem, thời gian lưu và hạn chế xuất dữ liệu. Đối với metrics thông thường, số đếm theo **route template + result + reason_code** thường đủ; tránh gắn user ID, token ID hoặc request ID làm **metric label** vì nhạy cảm và có độ phân biệt quá cao.

## 5. Thiết kế bảo vệ ở từng lớp trước khi log được xuất

| Lớp | Kiểm soát cần triển khai | Lưu ý |
|---|---|---|
| **Browser/client** | Không console.log token; tắt tự thu thập thông tin nhạy cảm của analytics/RUM | Kiểm tra SDK tự bắt request, URL, DOM, lỗi |
| **API Gateway / reverse proxy** | Tắt log raw Authorization/Cookie; chỉ ghi route, method, status và request ID được phép | Cấu hình access log có thể khác debug/error log |
| **Authorization Server** | Không ghi body token endpoint, response cấp token, code, verifier, secret | Refresh token thường đi qua form body thay vì Bearer header |
| **Resource Server** | Audit bằng metadata và kết quả kiểm tra; không log raw token hay payload JWT | Chỉ dùng claims sau khi xác minh, vẫn tối thiểu hóa dữ liệu |
| **HTTP client/interceptor** | Mask sensitive headers và bodies, tránh in request.toString hoặc response dumps | Lưu ý đường retry, exception, timeout |
| **APM/OpenTelemetry** | Allowlist span attributes/baggage/events; không ghi token trong span, trace, breadcrumbs | Sampling chỉ giảm số bản sao, không loại bỏ rủi ro |
| **Log collector/pipeline** | Redaction/giám sát bổ sung trước khi lưu/index/export | Không xem là lớp bảo vệ duy nhất |
| **Analytics provider** | Schema event giới hạn dữ liệu, tắt session replay/autocapture nhạy cảm | Kiểm tra SDK và điều khoản xử lý dữ liệu |
| **Kho lưu/backup** | RBAC, retention ngắn hợp lý, encryption, audit truy cập và xóa theo chính sách | Phòng thủ bổ sung cho dữ liệu vẫn cần lưu |

**Giới hạn đầu nguồn** quan trọng vì một khi raw token đã rời tiến trình và tới collector, việc xóa trong UI dashboard **không đảm bảo** các bản sao ở queue, cache, archive, export và backup đã biến mất.

### 5.1. Access log và body capture

Một log dạng:

~~~text
2026-11-23 INFO POST /oauth2/token body=grant_type=refresh_token&refresh_token=<actual-value>
~~~

là thiết kế không an toàn nếu **<actual-value>** thực sự là credential. Đặc biệt với token endpoint, không được chỉ redaction header Authorization mà quên **form body** hoặc **JSON response** chứa access_token/refresh_token/id_token.

Thay vào đó, hãy ghi:

~~~text
2026-11-23 INFO auth.token_exchange result=denied grant_type=refresh_token reason=INVALID_GRANT request_id=req-example-81
~~~

Thậm chí **grant_type** cũng cần lấy/chuẩn hóa theo danh sách giá trị được phép và không ghi nguyên request nếu bị hỏng. Không đưa refresh token, authorization code hay client secret vào message của exception.

### 5.2. Bảo vệ cả đường lỗi

Lỗi xác thực thường khiến đội phát triển bật debug chi tiết. Đây là lúc dễ phát tán credential nhất. Các handler nên tạo **mã lỗi an toàn** như INVALID_TOKEN, EXPIRED_TOKEN, INVALID_AUDIENCE, INSUFFICIENT_SCOPE, INTROSPECTION_UNAVAILABLE; không in toàn bộ request, token, URL có query nhạy cảm hoặc thông điệp trả về từ thư viện có chứa credential.

Resource Server phải **fail closed** khi không xác minh được token, nhưng log chỉ cần lý do đủ phục vụ vận hành. Ví dụ 401 do token sai issuer không cần ghi chính JWT hoặc mọi claims của token đó.

## 6. Analytics sản phẩm không phải nơi nhận credential

Analytics thường muốn biết người dùng đăng nhập thành công bao nhiêu lần, API gặp lỗi ra sao, tỷ lệ refresh thất bại hay có bao nhiêu phiên gặp sự cố. **Những câu hỏi này đều có thể trả lời mà không cần access token hoặc refresh token.**

### Event schema không an toàn

~~~json
{
  "event": "login_completed",
  "access_token": "<access-token-value>",
  "refresh_token": "<refresh-token-value>",
  "id_token": "<id-token-value>",
  "authorization_header": "Bearer <access-token-value>",
  "user_profile": "<entire-profile-object>"
}
~~~

Không dùng schema trên trong production. Token là credential, còn hồ sơ nguyên vẹn có thể chứa dữ liệu cá nhân không cần thiết.

### Event schema an toàn hơn

~~~json
{
  "event": "login_completed",
  "auth_flow": "authorization_code",
  "client_type": "browser_bff",
  "result": "success",
  "elapsed_bucket": "500-1000ms"
}
~~~

Đối với refresh:

~~~json
{
  "event": "token_refresh_result",
  "result": "failure",
  "reason_code": "INVALID_GRANT",
  "client_type": "public",
  "attempt_bucket": "first"
}
~~~

Không cần gửi raw **scope**, raw **iss**, raw **aud**, **sub** hoặc **jti** vào analytics phổ thông chỉ để đếm thành công/thất bại. Nếu phân tích theo ứng dụng hoặc issuer là nhu cầu thực tế, dùng **nhóm định danh đã được allowlist**, cân nhắc tác động đến quyền riêng tư và giới hạn quyền truy cập.

### Session replay và auto-capture

Một số SDK có khả năng ghi DOM, network metadata, URL, form input hoặc các breadcrumbs. Cần:

1. Xem chính xác SDK **thu thập mặc định** những gì trong phiên bản đang dùng.
2. Tắt auto-capture hoặc mask trường nhạy cảm; không quay màn hình chứa token, mã OTP hay dữ liệu xác thực.
3. Không gửi **Authorization**, **Cookie**, **Set-Cookie**, request/response của token endpoint hoặc nội dung error object có credential.
4. Không truyền token làm **user_id**, analytics identifier, event property hoặc parameter của URL.
5. Kiểm tra luồng dữ liệu sang dịch vụ bên thứ ba, khu vực lưu trữ, quyền truy cập và retention.

Mask ở DOM có thể không đủ nếu SDK còn thu thập URL, network request hoặc console message. Cần kiểm chứng **payload thực sự chuẩn bị gửi tới analytics**, không chỉ nhìn dashboard sau khi dữ liệu đã được xử lý.

## 7. Tracing, APM và OpenTelemetry: quan sát không đồng nghĩa giữ payload

**Trace** mô tả chuỗi xử lý một request qua nhiều service. Nó có ích khi kiểm tra latency của token validation hoặc xác định sự cố introspection/JWKS, nhưng không cần lưu chính token.

### Span attributes nên và không nên thu thập

| Có thể hữu ích, sau khi đánh giá | Không nên đưa vào span/baggage |
|---|---|
| Tên route template, HTTP method, status code | Header Authorization, Cookie, Set-Cookie |
| Tên component/operation, elapsed time | Access token, refresh token, ID token |
| Mã lỗi chuẩn hóa từ validator | Authorization code, PKCE verifier, client secret |
| Tên issuer logic đã allowlist nếu thực sự cần | Toàn bộ JWT, payload đã decode, JWKS private key |
| Kết quả policy permit/deny ở mức thích hợp | Raw request/response body của token endpoint |
| Trace ID và request ID không chứa bí mật | Token trong baggage được truyền giữa các service |

**Baggage** trong distributed tracing có thể được lan truyền qua nhiều tiến trình và request. Không sử dụng nó để chuyển access token, refresh token hoặc claims nhạy cảm giữa các service. Tương tự, **span events** và error stack có thể chứa raw HTTP object nếu instrumentation được cấu hình thiếu kiểm soát.

**Sampling không phải redaction.** Giảm tỷ lệ lấy mẫu từ 100% xuống 1% vẫn có khả năng lưu credential trong 1% request đó. Muốn an toàn phải loại bỏ trường nhạy cảm **trước khi xuất trace**, sau đó mới cân nhắc sampling, retention và quyền xem.

Một ví dụ log/span có mục tiêu:

~~~text
span: orders.get
http.route: /orders/{orderId}
http.status_code: 401
auth.validation.result: denied
auth.validation.reason: invalid_audience
~~~

Đây là minh họa về **schema nội bộ**, không phải tên thuộc tính bắt buộc của một phiên bản OpenTelemetry. Không xuất raw URL query hoặc token vào thuộc tính span. Kiểm tra các thư viện tự động instrument HTTP client/server, vì khả năng capture header/body tùy cấu hình.

## 8. Ví dụ Java: audit kết quả, không audit credential

Trong Java, đừng viết code dạng:

~~~java
// SAI: ví dụ cố ý, tuyệt đối không dùng trong ứng dụng thật.
log.info("Incoming Authorization header: {}", request.getHeader("Authorization"));
log.debug("Request body: {}", rawBody);
log.error("Auth failure, full request={}", request);
~~~

Cả header, body và phép chuyển request thành chuỗi đều có thể chứa credential. Thay vào đó, tạo **API logging chấp nhận trường có kiểm soát**, không nhận token:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AuthAuditLogger {
    private static final Logger LOG =
            LoggerFactory.getLogger(AuthAuditLogger.class);

    public enum Outcome { ALLOWED, DENIED }
    public enum Reason {
        NONE, INVALID_TOKEN, EXPIRED_TOKEN,
        INVALID_AUDIENCE, INSUFFICIENT_SCOPE
    }

    public void record(
            String requestId,
            String routeTemplate,
            Outcome outcome,
            Reason reason
    ) {
        // Cả requestId và routeTemplate phải được server tạo
        // hoặc chuẩn hóa/kiểm soát để không chứa input tùy ý.
        LOG.info("authz request_id={} route={} outcome={} reason={}",
                requestId, routeTemplate, outcome, reason);
    }
}
~~~

Trong ví dụ, đối tượng logging **không nhận access token, refresh token, JWT payload, request body hoặc HTTP headers** nên khó bị gọi nhầm theo cách làm lộ credential. **Outcome/Reason** là enum hạn chế giá trị. Dù vậy, **requestId** và **routeTemplate** vẫn phải được tạo hoặc kiểm soát phía server; không lấy raw request URL với query, chuỗi lỗi hoặc giá trị client tự cung cấp chứa token để làm request ID.

Nếu ghi thông tin principal để đáp ứng audit pháp lý, chỉ dùng **principal đã được token validation xác lập**, kiểm soát mục đích lưu trữ, quyền đọc và retention. Tránh log tất cả claims hoặc đối tượng Authentication/SecurityContext thô vì thư viện có thể giữ credential bên trong.

### Phân biệt hai điểm logging

- **Token validation failure:** token chưa đáng tin, nên log **reason code** và thông tin hạ tầng tối thiểu. Không ghi raw iss, sub, scope lấy từ JWT chưa xác minh như sự thật.
- **Authorization decision:** principal đã được xác minh; có thể log thông tin định danh nội bộ đã được phê duyệt và policy version nếu audit thực sự cần. Không cần token gốc.

Đừng dùng chuỗi thông báo lỗi của thư viện làm log line nếu chưa biết nội dung có chứa token hay không. Tốt hơn là ánh xạ ngoại lệ sang **mã lỗi do ứng dụng định nghĩa**.

## 9. Có nên log hash, jti hoặc vài ký tự cuối token?

Đôi khi đội vận hành muốn biết hai request có sử dụng cùng access token không. Đây là một nhu cầu có thể có, nhưng cần tránh biến nó thành một lý do lưu token biến tướng.

**Không mặc định sử dụng các phương án sau:**

- **Vài ký tự đầu/cuối:** vẫn tiết lộ một phần credential; không chứng minh tính duy nhất, có thể bị thu thập để hỗ trợ tấn công hoặc liên kết phiên.
- **JWT payload đã decode:** không còn là bearer token nguyên chuỗi nhưng vẫn có thể tiết lộ thông tin cá nhân, role, audience, tenant và metadata nghiệp vụ.
- **jti raw:** không phải credential tự nó trong thiết kế thông thường, nhưng có thể là mã định danh liên kết nhiều request hoặc người dùng, cần kiểm soát bảo mật/quyền riêng tư.
- **SHA-256(token) rồi đưa vào mọi log:** hash không cho phép dùng trực tiếp như token, nhưng tạo ra định danh có tính liên kết; đối với token entropy thấp hoặc có thể dự đoán, hash đơn thuần còn có thể bị dò. Không mặc định coi “hash” là vô hại.

Nếu bắt buộc phải tương quan những sự kiện theo token, một thiết kế được đánh giá kỹ có thể dùng **HMAC fingerprint với khóa server bí mật được quản lý riêng**, giới hạn thời gian/công cụ tiếp cận, tránh lưu raw token và không dùng fingerprint làm credential. Cần hiểu rằng fingerprint vẫn là dữ liệu có thể liên kết hoạt động, có yêu cầu retention và quyền riêng tư, và khóa HMAC cũng cần bảo vệ.

Phương án **ưu tiên** cho đa số tình huống vận hành là **request ID/trace ID an toàn, correlation theo phiên nội bộ được kiểm soát, thống kê kết quả validation**, thay vì theo dõi raw token hay dấu vân tay token qua mọi dịch vụ.

## 10. Kiểm thử để chứng minh credential không xuất hiện trong log

Không thể chỉ dựa vào quy ước “dev sẽ không log token”. Cần **kiểm thử đường đi thực tế của telemetry**, nhất là khi thêm gateway, APM agent hoặc SDK analytics mới.

### Ma trận negative tests

| Đầu vào thử nghiệm | Nơi cần kiểm tra | Điều kiện đạt |
|---|---|---|
| Bearer access token giả trong header Authorization | API logs, gateway logs, tracing | Không chứa giá trị token hoặc nguyên header |
| Refresh token giả trong form body token endpoint | AS logs, HTTP interceptor, APM | Không chứa refresh token |
| JSON response cấp access_token/refresh_token/id_token | Response debugging/tracing | Không ghi raw token response |
| Token trong Cookie hoặc Set-Cookie | Proxy, server và browser telemetry | Không ghi cookie nhạy cảm |
| Token giả trong query parameter | Access logs, analytics, span attributes | Không đưa giá trị raw URL nhạy cảm ra collector |
| Token giả trong exception message | Error logs, crash reports | Error mapping không xuất credential |
| JWT payload chứa thông tin cá nhân giả | Debug decode, audit logs | Không ghi toàn payload hoặc PII không cần |
| Client SDK tự gửi request data | Analytics collector và session replay | Không chứa token hoặc auth secrets |
| 401 invalid_token / 403 insufficient_scope | Audit/metrics | Có mã lỗi an toàn và đủ điều tra, không kèm token |
| Bật chế độ debug tạm thời | Toàn bộ pipeline | Chế độ debug không vô hiệu hóa redaction/allowlist |

### Cách thiết kế một bài kiểm thử tự động

Sử dụng các **sentinel giả** chỉ dành cho test, ví dụ:

~~~text
SYNTHETIC_ACCESS_TOKEN_NEVER_EXPORT_01
SYNTHETIC_REFRESH_TOKEN_NEVER_EXPORT_02
SYNTHETIC_ID_TOKEN_NEVER_EXPORT_03
~~~

Gửi chúng qua các đường code có thể nhận credential, đồng thời dùng mock collector hoặc output sink thử nghiệm để bắt sự kiện log, trace, analytics. Sau khi xử lý, kiểm tra cả **giá trị sentinel thô** và các biến thể mà công cụ có thể tự chuyển đổi, thay vì chỉ kiểm tra message hiển thị trên màn hình.

~~~text
testNoCredentialInTelemetry():
    configureTestLogTraceAndAnalyticsCollectors()

    sendApiRequest(Authorization = "Bearer " + SYNTHETIC_ACCESS)
    sendRefreshRequest(refresh_token = SYNTHETIC_REFRESH)
    emitHandledErrorWithSyntheticCredential()

    exported = collectAllTestTelemetryPayloads()
    assertNoRawOrEncodedSyntheticToken(exported)
    assertExpectedSafeAuthResultEventsExist(exported)
~~~

Đây là **pseudocode kiểm thử**, không phải kiểm thử mã hóa/chữ ký token. Mục tiêu là phát hiện đường rò qua **hạ tầng thu thập**. Test cần dùng credential giả và hệ thống thử nghiệm, không dùng token production. Nếu có nhiều môi trường/region, kiểm tra mọi tuyến xuất dữ liệu mà request có thể đi qua.

Một bộ kiểm thử tốt còn xác nhận log vẫn có **request ID, route template, kết quả và reason code** để chẩn đoán; ngăn token lộ không có nghĩa phải tắt toàn bộ khả năng quan sát.

## 11. Ứng cứu khi phát hiện token đã được ghi vào log hoặc analytics

Giả sử hệ thống phát hiện một HTTP logging interceptor đã ghi nguyên **Authorization** vào log tập trung trong nhiều ngày. Đây là sự cố có **khả năng lộ credential**, không chỉ là lỗi định dạng log.

### Bước 1. Chặn phát tán mới

- Ngừng hoặc sửa cấu hình log raw request/header/body tại nguồn phát sinh.
- Tắt collector/session replay hoặc rule có nguy cơ tiếp tục xuất token nếu cần.
- Không dán thêm token thật vào ticket hoặc chat khi điều tra; dùng request ID và bằng chứng đã được xử lý an toàn.

### Bước 2. Xác định phạm vi và mức độ ảnh hưởng

- Token loại nào bị ghi: access, refresh, ID token, session cookie, authorization code hay client secret?
- Những ngày, API, client, tenant, người dùng nào có thể bị ảnh hưởng?
- Dữ liệu đã đến gateway logs, application logs, SIEM, APM, analytics vendor, export, archive và backup nào?
- Ai đã có quyền đọc, tải xuống hoặc chuyển tiếp log? Có dấu hiệu sử dụng token bất thường không?
- Token có sender-constraining, TTL hoặc trạng thái thu hồi giúp giới hạn tác động không?

### Bước 3. Xử lý credential còn khả năng sử dụng

Nếu **refresh token** có thể đã lộ, đánh giá thu hồi refresh token/token family và buộc xác thực lại theo chính sách. Nếu **access token** đang còn hiệu lực, có thể cần revoke/denylist/kiểm trạng thái hoặc chờ hết hạn khi rủi ro cho phép; không mặc định access token tự biến mất chỉ vì đã sửa log. Với **session cookie/client secret**, quy trình vô hiệu hóa/xoay credential phù hợp có thể khác.

Nếu chỉ có một bearer token bị log, **không tự động kết luận signing key của issuer đã lộ**; thay đổi signing key là hành động tác động rộng, chỉ nên làm khi bằng chứng hoặc chính sách ứng cứu yêu cầu. Ngược lại, khi **issuer hoặc private signing key thật sự bị xâm phạm**, phải xử lý ở mức gốc tin cậy và cập nhật mọi Resource Server, kể cả nơi cache JWKS.

### Bước 4. Kiểm soát và xử lý dữ liệu đã lưu

- Hạn chế ngay quyền truy cập log/analytics liên quan; bảo toàn chứng cứ cần thiết theo quy trình ứng cứu.
- Làm việc với các nhóm và nhà cung cấp liên quan để xác định **bản sao trong index, queue, cache, export, archive và backup**.
- Áp dụng quy trình xóa/giảm thời gian giữ và yêu cầu xử lý dữ liệu theo chính sách pháp lý, bảo mật và quyền riêng tư.
- Không tuyên bố “đã xóa hết” nếu chưa có bằng chứng về các bản sao độc lập hoặc retention của đối tác.

### Bước 5. Kiểm chứng và ngăn tái diễn

Chạy lại test bằng token giả qua **tất cả tuyến log/tracing/analytics**, kiểm tra redaction/allowlist, hạn chế debug, thay đổi quyền xem log và theo dõi sự kiện tái xuất hiện token. Bổ sung kiểm tra cấu hình vào quy trình review và triển khai.

**Thu hồi token không xóa dữ liệu cá nhân đã được sao chép từ JWT vào log.** Tác động về credential và tác động về thông tin phải được xử lý như **hai vấn đề liên quan nhưng riêng biệt**.

## 12. Ví dụ xuyên suốt: đơn hàng, refresh token và hệ thống analytics

Giả sử:

- **Authorization Server:** https://auth.example.org.
- **Orders API:** audience **orders-api**, scope **orders:read**.
- **Client web:** dùng Authorization Code + PKCE, có thể nhận access token và refresh token khi chính sách cho phép.
- **Hệ thống quan sát:** API gateway logs, application logs, tracing và dashboard analytics.

### Diễn biến thiết kế không an toàn

1. Người dùng đăng nhập; SDK analytics ghi toàn bộ response token endpoint, gồm refresh token.
2. Client gọi Orders API, gateway ghi nguyên header Authorization.
3. Khi access token hết hạn, interceptor ghi raw request body của refresh grant để debug.
4. Resource Server trả 401 và exception handler ghi cả JWT payload đã decode.
5. Những dữ liệu đó được gom vào nền tảng log tập trung, có retention và người xem rộng hơn so với các thành phần xử lý token.

**Kết quả:** Một access token ngắn hạn bị lộ qua log, refresh token có thể bị lộ trong thời gian dài hơn, và claims danh tính có thể tồn tại cả sau khi credential hết hạn.

### Diễn biến thiết kế an toàn hơn

1. Token response được xử lý trong thành phần được ủy quyền; analytics chỉ nhận event **login_completed** với kết quả và loại flow.
2. Gateway log **route template, status, request ID, latency**, không log Authorization/Cookie.
3. Client làm mới token tại Authorization Server; chỉ gửi event **token_refresh_result** với enum kết quả, không có refresh token.
4. Resource Server xác minh issuer, audience, thời hạn và scope; audit trả **INVALID_TOKEN** hoặc **DENIED_POLICY** mà không có JWT/raw claims.
5. Collector và dashboard dùng thêm allowlist/kiểm soát truy cập/retention, không để dữ liệu credential tự do đi qua tracing hay analytics.

### Metric có ích nhưng không cần token

| Câu hỏi vận hành | Metric/event có thể dùng |
|---|---|
| API đang gặp nhiều lỗi xác thực không? | Tỷ lệ **401** theo route template và nhóm reason code |
| Refresh token có hay thất bại không? | Đếm **refresh_success**, **refresh_invalid_grant** theo loại client đã allowlist |
| JWKS hoặc introspection đang chậm? | Latency histogram, availability và error code của dependency |
| Một policy có từ chối quá nhiều? | Tổng **permit/deny** theo policy identifier ít cardinality |
| Có sự cố refresh token reuse? | Sự kiện bảo mật riêng, có quyền truy cập giới hạn, không chứa token gốc |

Các event security nhạy cảm có thể được xử lý trong hệ thống audit có phân quyền chặt thay vì gửi nguyên dữ liệu đến analytics thương mại. **Tập trung vào mục tiêu quan sát**, không thu thập credential chỉ vì “có thể sẽ cần debug”.

## 13. Chính sách lưu giữ, phân quyền xem và trách nhiệm với nhà cung cấp

Ngay cả khi chỉ thu metadata an toàn, hệ thống quan sát vẫn có thể chứa dữ liệu cá nhân hoặc hành vi người dùng. Cần xác định:

1. **Purpose limitation:** mỗi trường phục vụ sự kiện/điều tra nào?
2. **Minimization:** có thể thay raw URL bằng route template, raw user ID bằng nhóm thống kê, raw error bằng reason code không?
3. **Access control:** ai được đọc audit nhạy cảm, xuất log, sửa sampling hoặc bật body capture?
4. **Retention:** dữ liệu nào phải giữ bao lâu cho vận hành, bảo mật hoặc nghĩa vụ khác?
5. **Vendor/export:** SDK, collector và analytics có gửi dữ liệu ra ngoài phạm vi dự kiến không?
6. **Incident response:** có thể dừng thu thập, thu hẹp quyền và yêu cầu xử lý bản sao khi phát hiện rò rỉ không?
7. **Change review:** khi thêm SDK hoặc bật debug, ai kiểm tra rằng token không bị đưa vào nguồn dữ liệu mới?

**Dữ liệu đã được ghi vào log không được “hợp pháp hóa” chỉ bằng cách hạn chế quyền đọc.** Kiểm soát truy cập và mã hóa khi lưu là lớp bảo vệ quan trọng, nhưng không thay thế việc **không thu thập credential** ở lớp đầu vào.

## 14. Checklist trước khi triển khai

1. **Token handling:** client có dùng access token cho Resource Server và refresh token chỉ cho Authorization Server không?
2. **HTTP logging:** có log nguyên Authorization, Cookie, Set-Cookie, query, token endpoint body hoặc response không?
3. **JWT processing:** có in payload đã decode, claims nhạy cảm, exception chứa JWT hoặc SecurityContext nguyên object không?
4. **Gateway/proxy:** access log, debug log, WAF, service mesh và traffic capture có mask dữ liệu đúng không?
5. **Analytics/RUM:** SDK có auto-capture URL, network request, session replay, DOM và console không? Token có bị gửi theo event property không?
6. **Tracing/APM:** span, baggage, attribute và error breadcrumbs có nằm trong allowlist không?
7. **Audit schema:** log có request ID, route template, result, reason code cần thiết mà không chứa credential không?
8. **Metadata privacy:** có giới hạn việc ghi sub, email, tenant, jti, IP hoặc identifier có thể liên kết người dùng không?
9. **Token fingerprint:** có thực sự cần tương quan theo token; nếu có đã đánh giá rủi ro, khóa/retention và phạm vi xem chưa?
10. **Access control:** ai có quyền xem log, tải export, truy cập collector, bật debug hoặc sửa pipeline?
11. **Retention:** log, tracing, analytics, backup và dữ liệu của vendor có quy trình lưu/xóa hợp lý không?
12. **Tests:** có dùng sentinel giả để kiểm tất cả tuyến export, kể cả lỗi 401, refresh grant, exception và chế độ debug không?
13. **Incident response:** có quy trình chặn log mới, xác định phạm vi, revoke token và xử lý bản sao không?
14. **Review:** thay đổi SDK, framework hoặc log configuration có bắt buộc kiểm tra nguy cơ rò token trước khi triển khai không?

## 15. Câu hỏi tự đánh giá

**1. Vì sao không nên log bearer access token nếu đã dùng HTTPS?** HTTPS bảo vệ token trên đường truyền, nhưng log nằm sau điểm giải mã và có thể được xem hoặc sao chép bởi nhiều thành phần. Bearer token còn hiệu lực có thể bị phát lại.

**2. Opaque token không đọc được claims thì có thể gửi vào analytics không?** Không. Opaque token vẫn là credential có giá trị; không thấy nội dung không có nghĩa an toàn để chia sẻ.

**3. Refresh token bị log nguy hiểm hơn access token ngắn hạn ở điểm nào?** Nó có thể được dùng để xin access token mới khi còn hiệu lực, khiến khả năng tiếp tục truy cập kéo dài. Client binding, rotation hoặc sender-constraining giúp giảm rủi ro nhưng không biến log thành nơi lưu hợp lệ.

**4. Nếu đã xóa token khỏi dashboard, có thể kết luận không còn bản sao nào không?** Không. Queue, index, cache, export, archive, backup hoặc bên cung cấp có thể vẫn giữ bản sao. Cần xác minh theo quy trình.

**5. Sampling tracing 1% có thay thế redaction được không?** Không. Một token vẫn có thể lọt vào 1% trace được lấy mẫu. Phải giới hạn hoặc loại bỏ credential trước khi xuất dữ liệu.

**6. Có thể log toàn bộ claims của JWT sau verify vì chúng đã đáng tin không?** Không nên. Verified claims có thể chứa thông tin cá nhân và quyền nghiệp vụ; chỉ ghi metadata thật sự cần, theo quyền truy cập và retention đã định.

**7. Metrics đánh giá tỷ lệ lỗi xác thực có cần raw token không?** Không. HTTP status, route template, reason code và số đếm/histogram thường đã đủ.

**8. Khi thấy raw refresh token trong log, chỉ cần sửa cấu hình log là đủ chưa?** Chưa. Cần đánh giá phạm vi bản sao đã lộ, quyền truy cập, khả năng credential còn dùng được, thu hồi khi cần và xử lý dữ liệu trong kho lưu/nhà cung cấp.

**9. Có nên ghi hash của token vào tất cả log không?** Không mặc định. Hash vẫn tạo khả năng liên kết các request và có rủi ro tùy entropy token. Nếu có nhu cầu đặc biệt phải thiết kế cơ chế tương quan được kiểm soát; ưu tiên request ID và các metadata an toàn.

**Ghi nhớ:** **Log và analytics dùng để quan sát hệ thống, không phải kho lưu credential.** Không ghi access token, refresh token, ID token, session cookie, authorization code hay bí mật xác thực vào log/tracing/analytics. Hãy thiết kế **allowlist ngay tại nguồn**, sử dụng request ID, route template, mã lỗi và các thống kê tối thiểu; kiểm thử toàn bộ đường export và có quy trình ứng cứu khi dữ liệu đã lộ. Việc token hết hạn hoặc được thu hồi **không tự xóa** những bản sao đã lưu trong hệ thống quan sát.
