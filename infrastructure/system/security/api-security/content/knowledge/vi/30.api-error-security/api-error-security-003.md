# Phân biệt 401, 403, 404 và 429 đúng ngữ nghĩa

HTTP status code là một phần của API contract. Client dùng nó để quyết định có cần đăng nhập lại, yêu cầu quyền, dừng truy cập tài nguyên hay chờ trước khi gửi request tiếp theo. Monitoring, gateway, SDK và hệ thống hỗ trợ cũng dựa vào status để phân loại sự cố. Nếu API dùng sai 401, 403, 404 hoặc 429, client có thể retry sai cách, thông tin tài nguyên bị lộ hoặc lỗi bảo mật bị che khuất trong log.

Trong thiết kế bảo mật API theo endpoint, object và workflow, bốn status này đại diện cho bốn câu hỏi khác nhau:

- **401 Unauthorized:** request chưa có credential hợp lệ để xác thực caller.
- **403 Forbidden:** server hiểu request nhưng từ chối thực hiện theo chính sách truy cập.
- **404 Not Found:** không tìm thấy route/tài nguyên, hoặc server chủ động không tiết lộ tài nguyên có tồn tại hay không.
- **429 Too Many Requests:** client đã gửi quá nhiều request trong một khoảng thời gian hoặc vượt giới hạn tần suất được áp dụng.

Status code phải phản ánh nguyên nhân thực tế ở tầng HTTP/API. Không dùng một mã chung cho mọi lỗi và không đưa chi tiết nội bộ vào response chỉ để giải thích chính xác hơn.

## 1. Nhìn nhanh sự khác nhau

| Status | Câu hỏi cần trả lời | Tình huống điển hình | Client thường nên làm gì |
|---|---|---|---|
| 401 | Credential có xác thực được caller không? | Thiếu token, token hết hạn, chữ ký credential sai | Đăng nhập/xác thực lại hoặc lấy credential mới |
| 403 | Caller có được phép thực hiện action này không? | Đã xác thực nhưng thiếu function permission hoặc scope | Dừng action; yêu cầu cấp quyền qua quy trình hợp lệ |
| 404 | Route hoặc tài nguyên có được cung cấp trong ngữ cảnh này không? | Sai route, object không tồn tại, object được che giấu vì caller không có quyền | Kiểm tra URL/reference; không dò ID để tìm object |
| 429 | Caller có vượt giới hạn tần suất/quota không? | Vượt rate limit theo user, token, tenant, API client hoặc IP | Chờ theo Retry-After nếu có rồi retry có kiểm soát |

Tên tiếng Anh của 401 là “Unauthorized”, nhưng trong ngữ nghĩa HTTP, nó thường biểu thị vấn đề xác thực (authentication). 403 mới thường biểu thị caller đã được nhận diện nhưng bị từ chối theo quyền hoặc policy. Đây là điểm dễ nhầm nhất khi thiết kế API.

## 2. Cây quyết định chọn status

Trước khi trả lỗi, xác định request đã đi đến đâu trong pipeline:

~~~mermaid
flowchart TD
    A[Receive API request] --> B{Route and method exist?}
    B -->|No| N[404 Not Found]
    B -->|Yes| C{Credential valid?}
    C -->|No or missing| U[401 + WWW-Authenticate]
    C -->|Yes| D{Rate limit exceeded?}
    D -->|Yes| R[429 + optional Retry-After]
    D -->|No| E{Function permission granted?}
    E -->|No| F[403 Forbidden]
    E -->|Yes| G{Object visible and accessible?}
    G -->|Not found or concealed| N
    G -->|Exists but visible, action denied| F
    G -->|Allowed| H[Validate workflow and execute]
~~~

Đây là thứ tự tham khảo, không phải thứ tự bắt buộc cho mọi gateway. Ví dụ, rate limit chống credential stuffing có thể chạy trước authentication; rate limit theo tenant thường cần xác định principal/tenant trước. Việc tra cứu object cũng có thể được thực hiện bằng query đã giới hạn tenant để không tiết lộ object ngoài phạm vi. Điều quan trọng là mọi nhánh đều có quy tắc nhất quán và không tạo side channel tiết lộ dữ liệu.

## 3. 401 Unauthorized: chưa xác thực được caller

Trả 401 khi request cần authentication nhưng credential không có, không hợp lệ hoặc không còn hiệu lực. Server chưa có cơ sở tin cậy để xác định principal theo yêu cầu của endpoint.

Các tình huống thường gặp:

- Request không gửi access token hoặc credential bắt buộc.
- Bearer token sai chữ ký, issuer hoặc audience.
- Token đã hết hạn hoặc chưa đến thời điểm hiệu lực.
- API key không tồn tại, bị thu hồi hoặc không hợp lệ.
- Session đã hết hạn hoặc credential không còn được chấp nhận.
- Chữ ký request hoặc identity ở tầng HTTP không được chấp nhận. Nếu mTLS bị từ chối ngay trong TLS handshake, kết nối có thể bị đóng trước khi server gửi được HTTP status.

Không trả 401 chỉ vì caller thiếu quyền trên một action. Nếu credential đã xác thực thành công nhưng permission không đủ, hãy xem xét 403 hoặc 404 theo chính sách che giấu object.

### 3.1. 401 phải có WWW-Authenticate

Theo HTTP semantics, response 401 phải có ít nhất một header WWW-Authenticate chứa challenge áp dụng cho tài nguyên. Với API dùng Bearer token, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Cache-Control: no-store
Content-Type: application/problem+json
~~~

Khi token không hợp lệ, API dùng OAuth 2.0 Bearer Token Usage có thể trả error phù hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json
~~~

Không đưa token, chữ ký, secret hoặc chi tiết xác minh nội bộ vào header. Client cần biết credential không được chấp nhận và cơ chế authentication liên quan, không cần biết khóa nào hoặc bước kiểm tra nào thất bại.

### 3.2. Phân biệt credential thiếu, hết hạn và sai

API có thể dùng cùng status 401 cho các trường hợp này, nhưng error code trong Problem Details cần ổn định và không làm lộ thông tin nhạy cảm. Ví dụ:

| Tình huống | Status | Error code công khai gợi ý |
|---|---:|---|
| Thiếu credential | 401 | authentication_required |
| Credential hết hạn | 401 | invalid_token hoặc credential_expired nếu contract cho phép |
| Chữ ký token sai | 401 | invalid_token |
| API key bị thu hồi | 401 | invalid_credential |

Không trả thông báo phân biệt quá chi tiết nếu điều đó giúp attacker dò credential. Với đăng nhập, có thể dùng thông báo chung như “Thông tin xác thực không hợp lệ” cho username không tồn tại và mật khẩu sai. Việc giới hạn tốc độ đăng nhập là một kiểm soát riêng và có thể trả 429 khi caller vượt ngưỡng.

### 3.3. 401 không phải cách yêu cầu nâng quyền

Nếu access token hợp lệ nhưng thiếu scope, RFC 6750 định nghĩa tình huống insufficient_scope thường dùng 403. Không yêu cầu client đăng nhập liên tục nếu tài khoản vốn không được cấp quyền. Client cần biết action bị từ chối theo policy để dừng hoặc đi qua quy trình xin quyền.

### 3.4. Ví dụ response 401

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required.",
  "code": "authentication_required",
  "traceId": "tr_7f2a91"
}
~~~

traceId là extension do API định nghĩa, dùng để tra cứu log nội bộ. Không đưa token nhận được, raw JWT claims hoặc lý do cryptographic chi tiết vào response.

## 4. 403 Forbidden: caller đã xác thực nhưng action bị từ chối

403 biểu thị server hiểu request nhưng từ chối thực hiện. Trong API, tình huống phổ biến là principal đã xác thực nhưng không đáp ứng permission hoặc policy cần thiết.

Ví dụ:

- User không có function permission USER_ROLE_MANAGE.
- API client có scope đọc nhưng gọi endpoint ghi.
- Nhân viên đã đăng nhập nhưng không được phê duyệt refund.
- Principal bị policy chặn vì trạng thái tài khoản hoặc workflow.
- Caller được phép truy cập hệ thống nhưng không được dùng chức năng quản trị.

### 4.1. Phân biệt function authorization và object authorization

Function authorization trả lời: “Principal có được gọi loại action này không?”

Object authorization trả lời: “Principal có được thực hiện action này trên object cụ thể không?”

Ví dụ:

| Kiểm tra | Kết quả | Status thường dùng |
|---|---|---:|
| User không có quyền INVOICE_EXPORT | Không được gọi chức năng export | 403 |
| User có quyền export nhưng invoice thuộc tenant khác | Không được truy cập object; có thể che giấu tồn tại | 404 hoặc 403 theo policy |
| User có quyền đọc invoice nhưng không có quyền sửa | Được đọc, không được cập nhật | 403 |
| User có quyền gọi refund nhưng giao dịch không ở trạng thái cho phép | Điều kiện workflow không đạt | Thường 409 hoặc mã phù hợp contract, không mặc định 403 |

Không biến mọi lỗi nghiệp vụ thành 403. Ví dụ, invoice đã khóa hoặc payment đã capture có thể là xung đột trạng thái (409 Conflict), dù caller có đủ quyền. Authorization và business state là hai câu hỏi khác nhau.

### 4.2. 403 nên giải thích đến mức nào?

Response nên cho biết action bị từ chối ở mức đủ để client xử lý, nhưng không tiết lộ:

- Danh sách role hoặc permission nội bộ.
- Tên người có quyền phê duyệt.
- Cấu trúc tenant hoặc object khác.
- Rule chống gian lận và ngưỡng risk.
- Chính sách bảo vệ hệ thống chưa công khai.

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not allowed to perform this action.",
  "code": "action_not_permitted",
  "traceId": "tr_2d0c51"
}
~~~

Nếu dùng OAuth Bearer và token hợp lệ nhưng scope không đủ, API có thể dùng challenge/error phù hợp như insufficient_scope theo contract và RFC 6750. Không trả danh sách scope quản trị hoặc quyền của user khác.

### 4.3. Không dùng 401 để che lỗi phân quyền

Nếu mọi request thiếu quyền đều trả 401, client có thể xóa session, yêu cầu đăng nhập lại hoặc refresh token vô ích. Điều này tạo trải nghiệm sai và che khuất lỗi authorization trong monitoring. Hãy dùng 401 cho authentication failure; dùng 403 cho permission/policy denial khi không áp dụng chính sách 404 concealment.

## 5. 404 Not Found: không tìm thấy hoặc chủ động che giấu tài nguyên

404 thường được dùng khi route hoặc tài nguyên không tồn tại. HTTP cũng cho phép server dùng 404 khi không muốn tiết lộ rằng một tài nguyên bị từ chối truy cập có tồn tại hay không.

Các tình huống:

- Path hoặc endpoint không tồn tại.
- Object ID không ánh xạ đến tài nguyên.
- Tài nguyên đã bị xóa hoặc không còn được cung cấp.
- Object tồn tại nhưng policy yêu cầu che giấu với caller không có quyền.
- Object nằm ngoài tenant scope và API không muốn tiết lộ sự tồn tại.

### 5.1. 403 hay 404 cho object không được phép truy cập?

Đây là quyết định security policy, không phải quy tắc chỉ dựa vào database.

**Trả 403** khi API có thể công khai sự tồn tại của object và cần nói rõ caller bị từ chối quyền. Ví dụ, một quản trị viên biết invoice tồn tại nhưng không có quyền approve invoice đó.

**Trả 404** khi tiết lộ object có tồn tại hay không tạo rủi ro enumeration hoặc lộ dữ liệu. Ví dụ, user của tenant A gửi ID invoice thuộc tenant B. API có thể trả cùng một 404 như trường hợp ID không tồn tại.

Chọn chính sách nhất quán cho từng loại tài nguyên và action. Không để endpoint GET che giấu bằng 404 nhưng endpoint DELETE trả 403 cho cùng một object nếu khác biệt đó tiết lộ sự tồn tại ngoài chủ đích.

### 5.2. Tránh IDOR/BOLA khi dùng 404

Trả 404 không tự động sửa lỗi Broken Object Level Authorization. Server vẫn phải kiểm tra object theo principal và tenant đã xác thực.

Một cách an toàn là giới hạn truy vấn ngay từ đầu:

~~~java
Invoice invoice = invoiceRepository
    .findByIdAndTenantId(invoiceId, principal.tenantId())
    .orElseThrow(ResourceNotFoundException::new);

if (!invoicePolicy.canRead(principal, invoice)) {
    // Nếu policy yêu cầu concealment, trả cùng loại 404.
    throw new ResourceNotFoundException();
}
~~~

Đây là ví dụ rút gọn. Trong hệ thống thực tế, tenantId phải đến từ security context/membership đã xác minh; không lấy trực tiếp từ query hoặc body. Nếu policy chọn 403 cho object tồn tại và được phép tiết lộ, có thể ném exception tương ứng. Query có tenant scope giúp tránh vô tình lấy object ngoài tenant trước khi kiểm tra.

### 5.3. Giảm khả năng dò tìm qua response

Khi dùng 404 để che giấu object:

- Dùng cùng status và error code cho object không tồn tại và object bị conceal.
- Không ghi object_exists_but_forbidden trong response công khai.
- Không đưa owner, tenant hoặc metadata của object vào body.
- Tránh khác biệt rõ rệt về header, content length hoặc cache behavior.
- Xem xét timing side channel nếu truy vấn object tồn tại và không tồn tại có đường xử lý rất khác nhau.
- Không cho phép bulk lookup trả kết quả từng ID theo cách tiết lộ object ngoài phạm vi.

Không thể đảm bảo mọi request có thời gian xử lý giống hệt nhau trong hệ thống thực tế. Mục tiêu là tránh khác biệt dễ khai thác và không tiết lộ thông tin không cần thiết.

### 5.4. Cẩn thận với caching của 404

404 có thể được cache theo HTTP caching rules. Với response phụ thuộc vào principal, tenant hoặc quyền hiện tại, cache dùng chung có thể khiến kết quả của một người dùng bị trả cho người khác hoặc giữ lại kết quả cũ sau khi quyền thay đổi.

Với lỗi xác thực/phân quyền hoặc 404 concealment cho tài nguyên nhạy cảm, cân nhắc Cache-Control: no-store. Nếu có nhu cầu cache, phải xác định cache key, private/shared behavior, Vary và thời hạn theo đúng authorization context. Không để CDN cache 404 động theo URL mà bỏ qua identity.

### 5.5. Không dùng 404 cho mọi lỗi backend

Database timeout, service unavailable hoặc lỗi truy vấn không có nghĩa object không tồn tại. Ánh xạ lỗi hạ tầng thành 404 sẽ làm client hiểu sai và khiến monitoring che mất outage. Dùng 500, 502, 503 hoặc 504 tùy nguyên nhân và contract.

## 6. 429 Too Many Requests: vượt giới hạn tần suất

429 được dùng khi client gửi quá nhiều request trong một khoảng thời gian hoặc vượt giới hạn tần suất áp dụng. Giới hạn có thể dựa trên IP, API key, user, tenant, subscription, endpoint, action hoặc tài nguyên dùng chung.

Ví dụ:

- Gửi OTP vượt số lần cho phép.
- Gọi API tìm kiếm quá nhanh.
- Tạo export job vượt quota đồng thời.
- Gọi endpoint đăng nhập với tần suất bất thường.
- Một API client vượt quota theo plan.
- Gửi quá nhiều request đến endpoint có chi phí CPU cao.

### 6.1. 429 khác 403 và 503

| Tình huống | Status phù hợp | Giải thích |
|---|---:|---|
| Caller không có permission gọi endpoint | 403 | Vấn đề quyền, không phải tần suất |
| Caller vượt rate limit theo user/token/tenant | 429 | Caller vượt giới hạn request |
| Toàn bộ service quá tải hoặc maintenance | 503 | Khả năng phục vụ của service không sẵn sàng |
| Upstream không phản hồi đúng hạn | 504 | Gateway/proxy timeout khi chờ upstream |
| Upstream trả response không hợp lệ | 502 | Gateway nhận response lỗi từ upstream |

Không trả 429 cho mọi lỗi overload. Nếu hệ thống đang thiếu capacity toàn cục và không thể phục vụ request của nhiều caller, 503 thường mô tả đúng hơn. Ngược lại, nếu một tenant vượt quota trong khi service vẫn hoạt động bình thường, 429 phù hợp hơn.

### 6.2. Retry-After

Response 429 có thể chứa Retry-After để chỉ thời điểm client nên thử lại. Giá trị có thể là số giây chờ hoặc HTTP-date theo HTTP semantics.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too many requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "rate_limit_exceeded",
  "traceId": "tr_81b4f0"
}
~~~

Retry-After không bắt buộc trong mọi response 429. Nếu hệ thống không thể dự đoán thời điểm reset, có thể không gửi header này hoặc cung cấp một thời gian chờ bảo thủ. Không đưa ngưỡng nội bộ, key phân loại hoặc thông tin về caller khác vào response.

### 6.3. Thiết kế rate limit theo nhiều chiều

Một rate limiter chỉ dựa vào IP thường không đủ:

- Nhiều user hợp lệ có thể dùng chung NAT hoặc proxy doanh nghiệp.
- Attacker có thể phân tán request qua nhiều IP.
- API key bị lộ có thể được sử dụng từ nhiều nguồn.
- Một tenant có thể tạo tải lớn dù mỗi user riêng lẻ chưa vượt ngưỡng.
- Endpoint có chi phí khác nhau cần quota khác nhau.

Kết hợp giới hạn theo principal, tenant, API client, endpoint/action, IP/network và global capacity. Với anonymous endpoint, có thể dùng IP/network signal cùng các kiểm soát bổ sung. Không để IP đơn lẻ có thể khóa vĩnh viễn tài khoản nạn nhân bằng cách gửi request thay họ.

### 6.4. Burst, sustained rate và concurrency

Rate limit có thể kiểm soát nhiều đặc tính:

- **Burst:** số request được phép trong khoảng thời gian rất ngắn.
- **Sustained rate:** tốc độ trung bình theo cửa sổ dài hơn.
- **Concurrency:** số operation đang chạy cùng lúc.
- **Quota:** tổng lượng sử dụng trong chu kỳ billing hoặc thời hạn.
- **Cost budget:** chi phí tương đối của endpoint hoặc query.

429 thường phù hợp với giới hạn tần suất hoặc quota request. Nếu một workflow bị xung đột trạng thái vì operation trước chưa hoàn tất, 409 có thể phù hợp hơn. Nếu một request quá đắt do payload/query vượt giới hạn, 413 hoặc 400/422 có thể phù hợp theo nguyên nhân; đừng dùng 429 thay cho validation.

### 6.5. Retry phía client phải có kiểm soát

Client nên:

- Tôn trọng Retry-After nếu có.
- Dùng exponential backoff và jitter khi retry.
- Đặt số lần retry tối đa và tổng deadline.
- Không retry liên tục trong vòng lặp không giới hạn.
- Không retry 401 bằng cùng credential sai.
- Không retry 403/404 như lỗi tạm thời.
- Với request ghi, dùng idempotency key nếu API hỗ trợ trước khi tự động retry sau timeout/429.

Nếu server trả 429 trước khi thực hiện operation, client vẫn cần dựa vào contract để biết request có được nhận hay không. Với thao tác ghi, response cần làm rõ trạng thái và idempotency để tránh tạo side effect trùng.

## 7. Các status liên quan để không dùng nhầm bốn mã

401, 403, 404 và 429 không bao phủ mọi lỗi API. Một số status khác thường cần phân biệt:

| Status | Ý nghĩa | Ví dụ |
|---|---|---|
| 400 Bad Request | Request không hợp lệ về cú pháp/cấu trúc | JSON hỏng, query parameter sai định dạng |
| 405 Method Not Allowed | Method không được hỗ trợ cho resource | Gọi DELETE trên endpoint chỉ hỗ trợ GET |
| 409 Conflict | Xung đột với trạng thái hiện tại | Payment đã capture nhưng client gửi capture lần nữa |
| 413 Content Too Large | Request body vượt giới hạn | Upload body lớn hơn cấu hình |
| 415 Unsupported Media Type | Content-Type không được hỗ trợ | Gửi XML đến endpoint chỉ nhận JSON |
| 422 Unprocessable Content | Nội dung đúng cú pháp nhưng không xử lý được theo ngữ nghĩa | Trường ngày tháng hoặc quy tắc domain không hợp lệ |
| 500 Internal Server Error | Lỗi không dự kiến trong server | Exception chưa được xử lý |
| 502 Bad Gateway | Gateway nhận response không hợp lệ từ upstream | Upstream trả payload/protocol sai |
| 503 Service Unavailable | Service tạm thời không thể phục vụ | Maintenance hoặc quá tải toàn cục |
| 504 Gateway Timeout | Gateway không nhận response kịp thời từ upstream | Provider không phản hồi trước deadline |

Status phải được chọn theo nguyên nhân và HTTP semantics, không theo cách dễ nhất để viết exception handler.

## 8. Chuẩn hóa error response

Status code cho biết loại kết quả ở tầng HTTP. Response body cung cấp mã lỗi ổn định và thông tin vừa đủ cho client. Có thể dùng Problem Details theo RFC 9457 với media type application/problem+json.

Các field chuẩn thường dùng:

- type: URI định danh loại problem.
- title: mô tả ngắn loại lỗi.
- status: HTTP status tương ứng.
- detail: giải thích cụ thể cho lần xảy ra này ở mức an toàn.
- instance: URI/reference nhận diện lần xảy ra nếu cần.

Có thể thêm extension như code, traceId hoặc retryable nếu contract quy định. Không đưa stack trace, SQL, secret, access token, tên class, hostname nội bộ hoặc rule chống abuse vào body.

### 8.1. Một envelope thống nhất, nội dung theo status

Ví dụ 403:

~~~json
{
  "type": "https://api.example.test/problems/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not allowed to perform this action.",
  "code": "action_not_permitted",
  "traceId": "tr_2d0c51"
}
~~~

Ví dụ 404 concealment:

~~~json
{
  "type": "https://api.example.test/problems/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "The requested resource was not found.",
  "code": "resource_not_found",
  "traceId": "tr_4a0b17"
}
~~~

Ví dụ 429:

~~~json
{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too many requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "rate_limit_exceeded",
  "traceId": "tr_81b4f0"
}
~~~

code nên ổn định qua các phiên bản; không dùng message tự do làm logic điều khiển của client. detail có thể được bản địa hóa, nhưng client nên dựa vào status và code.

### 8.2. Không để body và status mâu thuẫn

Không trả HTTP 200 với body status 401, hoặc trả HTTP 403 nhưng body nói status 404. Proxy, cache, SDK và monitoring dựa vào status thật. Body cần phản ánh cùng status; nếu dùng Problem Details, field status phải khớp với HTTP response.

### 8.3. Không trả lỗi quá chi tiết

Không trả:

- “User tồn tại nhưng không thuộc tenant này.”
- “Invoice ID này thuộc merchant ABC.”
- “Token signature sai vì key version K3 đã bị revoke.”
- “Rate limit bị kích hoạt do 17 request trong 4 giây từ IP X.”
- “Role admin đang có permission Y.”

Các chi tiết này có thể giúp attacker enumeration, dò policy hoặc điều chỉnh automation. Dùng reason code nội bộ trong log/audit với quyền truy cập phù hợp.

## 9. Cache, header và rò rỉ thông tin qua lỗi

Error response cũng là dữ liệu có thể bị cache, log, đo đạc hoặc hiển thị cho người khác.

### 9.1. Cache-Control

Với 401, 403 và 404 phụ thuộc authentication/authorization, cân nhắc Cache-Control: no-store để tránh lưu response nhạy cảm ở browser/proxy/CDN. Đặc biệt, 404 concealment có thể phụ thuộc principal hoặc tenant; shared cache không được dùng kết quả của caller trước cho caller sau.

Với 429, quyết định cache phải xét rate-limit key. Một response 429 cho token A không nên bị cache và trả cho token B chỉ vì URL giống nhau. Thông thường, no-store là lựa chọn đơn giản cho lỗi rate limit cá nhân hóa.

### 9.2. Header bảo mật

Giữ các header cần thiết như WWW-Authenticate cho 401 và Retry-After cho 429 khi có thể xác định thời điểm retry. Không để reverse proxy xóa challenge hoặc ghi đè status. Với response chứa thông tin nhạy cảm, dùng cache policy phù hợp và tránh đưa credential vào URL.

### 9.3. CORS và error response

Nếu browser client cần đọc error body, CORS policy phải cho phép origin hợp lệ và expose header cần thiết như Retry-After nếu client cần đọc. CORS không thay thế authorization; không phản chiếu Origin tùy ý chỉ để client nhìn thấy lỗi.

### 9.4. Log và trace

Log nên ghi:

- HTTP status và error code nội bộ.
- Route template, method và request/trace ID.
- Principal/tenant reference đã giả danh hóa khi cần.
- Quyết định authentication/authorization/rate limit.
- Policy version và node/region nếu có ý nghĩa.

Không log raw token, cookie, API key, password, body nhạy cảm hoặc thông tin tài nguyên bị conceal. Kiểm soát quyền đọc log và thời hạn lưu như dữ liệu bảo mật.

## 10. Ánh xạ status trong Spring Security

Trong ứng dụng Spring, nên tách xử lý authentication failure, authorization denial, object concealment và rate limit thay vì gom tất cả vào một exception handler.

### 10.1. AuthenticationEntryPoint cho 401

Ví dụ minh họa:

~~~java
http.exceptionHandling(config -> config
    .authenticationEntryPoint((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer realm=\"api\"");
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setContentType("application/problem+json");
        objectMapper.writeValue(
            response.getOutputStream(),
            problemBody(401, "authentication_required"));
    })
);
~~~

Đoạn code chỉ minh họa cách ánh xạ. Cần dùng challenge đúng với authentication scheme đang triển khai, xử lý error response không làm lộ exception và kiểm tra filter chain thực tế. Nếu dùng OAuth Bearer resource server, tận dụng cơ chế entry point/handler phù hợp của Spring Security để giữ đúng semantics của Bearer token.

### 10.2. AccessDeniedHandler cho 403

~~~java
http.exceptionHandling(config -> config
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setContentType("application/problem+json");
        objectMapper.writeValue(
            response.getOutputStream(),
            problemBody(403, "action_not_permitted"));
    })
);
~~~

Handler này xử lý function/policy denial ở security layer. Object-level policy có thể nằm trong service/domain layer và cần ánh xạ riêng sang 403 hoặc 404 theo concealment policy.

### 10.3. ResourceNotFound cho 404

Không bắt mọi AccessDeniedException rồi đổi thành 404. Chỉ dùng 404 concealment ở nơi policy yêu cầu che giấu sự tồn tại và áp dụng nhất quán cho tài nguyên đó.

~~~java
@GetMapping("/invoices/{id}")
InvoiceResponse getInvoice(
        @PathVariable UUID id,
        CurrentPrincipal principal) {

    Invoice invoice = repository
        .findByIdAndTenantId(id, principal.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    if (!invoicePolicy.canRead(principal, invoice)) {
        throw new ResourceNotFoundException();
    }

    return mapper.toResponse(invoice);
}
~~~

Ví dụ này minh họa chính sách concealment. Nếu API được phép công khai rằng object tồn tại, có thể trả 403 khi policy từ chối. Tenant trong principal phải được xác minh từ authentication/membership, không lấy từ request.

### 10.4. RateLimitExceeded cho 429

~~~java
@ExceptionHandler(RateLimitExceededException.class)
ResponseEntity<ProblemDetail> handleRateLimit(
        RateLimitExceededException exception) {

    ProblemDetail body = ProblemDetail.forStatusAndDetail(
        HttpStatus.TOO_MANY_REQUESTS,
        "The request limit has been reached. Try again later.");
    body.setType(URI.create(
        "https://api.example.test/problems/rate-limit-exceeded"));
    body.setProperty("code", "rate_limit_exceeded");

    return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
        .header(HttpHeaders.RETRY_AFTER,
            Long.toString(exception.retryAfterSeconds()))
        .header(HttpHeaders.CACHE_CONTROL, "no-store")
        .body(body);
}
~~~

Chỉ gửi Retry-After nếu có thời gian chờ hợp lý. Không trả counter hoặc bucket key nội bộ. Rate limiter phải quyết định atomically và có chiến lược phù hợp khi chạy nhiều instance.

## 11. Kiểm thử status code và security behavior

Kiểm thử không chỉ xác nhận status đúng mà còn cần kiểm tra header, body, cache và việc không có side effect khi request bị từ chối.

| Nhóm test | Request/tình huống | Kết quả mong đợi |
|---|---|---|
| Missing credential | Gọi endpoint cần auth không có token | 401 và WWW-Authenticate |
| Invalid token | Token sai chữ ký/audience hoặc hết hạn | 401; không lộ chi tiết xác minh |
| Insufficient scope | Token hợp lệ nhưng thiếu scope | 403 theo contract; không yêu cầu login lại |
| Function denial | User thiếu permission cho action | 403 và không có side effect |
| Object hidden | ID không tồn tại và ID ngoài tenant | Cùng 404/body policy nếu concealment được bật |
| Object visible denial | Object tồn tại và policy cho phép tiết lộ nhưng action bị cấm | 403 |
| BOLA | Thay ID object sang tenant khác | Không đọc/sửa/xóa object ngoài phạm vi |
| Rate limit | Gửi vượt ngưỡng | 429; Retry-After đúng nếu có |
| Service overload | Toàn service không đủ capacity | 503 thay vì giả thành quota riêng của caller |
| Business conflict | Payment đã ở trạng thái không thể capture | 409 hoặc contract tương ứng, không gán nhầm 403 |
| Cache | Gọi cùng URL với hai principal khác nhau | Không dùng cache chéo quyền |
| Error body | So sánh body status và HTTP status | Luôn nhất quán |
| Side effect | Request bị 401/403/404/429 | Không thực hiện thao tác nghiệp vụ bị từ chối |
| Client retry | Client nhận 429 và Retry-After | Chờ đúng, có backoff và không retry vô hạn |
| Logging | Request chứa token/PII | Log không chứa credential hoặc payload nhạy cảm |

### 11.1. Test 404 concealment

Tạo hai trường hợp:

1. Object ID không tồn tại.
2. Object tồn tại nhưng caller không có quyền biết hoặc truy cập.

So sánh status, error code, response schema, header và cache behavior. Nếu chính sách yêu cầu concealment, hai trường hợp cần tương đương ở những thuộc tính quan sát được của API. Kiểm tra thêm list/search/bulk endpoint vì attacker có thể dùng các endpoint khác để suy ra object tồn tại.

### 11.2. Test 429 và concurrency

Gửi request đồng thời từ nhiều instance hoặc nhiều client dùng chung tenant để xác minh limiter không cấp vượt quota ngoài dung sai. Kiểm tra reset window, clock skew, failover của rate-limit store và behavior khi store timeout. Một limiter local có thể vượt ngưỡng khi traffic phân tán; cần test theo topology triển khai thực tế.

### 11.3. Test 401 challenge và SDK behavior

Xác minh gateway không xóa WWW-Authenticate, client SDK phân biệt 401 với 403 và chỉ refresh token khi phù hợp. Một SDK không nên lặp refresh vô hạn nếu refresh token đã bị thu hồi.

## 12. Monitoring và phân tích lỗi

Theo dõi tỷ lệ status theo endpoint template, tenant/client tier và thời gian:

- 401 tăng đột biến có thể chỉ ra credential hết hạn, cấu hình issuer sai hoặc credential stuffing.
- 403 tăng có thể phản ánh policy thay đổi, permission drift hoặc client gọi sai chức năng.
- 404 tăng trên endpoint object có thể chỉ ra enumeration, ID sai hoặc lỗi routing.
- 429 tăng có thể phản ánh abuse, quota cấu hình quá thấp hoặc client retry không đúng.

Không gộp tất cả 4xx thành một metric duy nhất. Cũng không coi mọi 401/403 là tấn công; cần kết hợp route, reason code nội bộ, deployment version và thay đổi cấu hình.

Metric nên dùng endpoint template thay vì path chứa ID thực để tránh cardinality cao và rò rỉ dữ liệu. Log có thể chứa request ID, principal reference giả danh hóa, tenant reference, status và policy reason. Không đưa token, password, API key hoặc object data nhạy cảm vào label/metric.

Alert hữu ích:

- 401 tăng mạnh sau khi rotate signing key.
- 403 tăng sau thay đổi permission policy.
- 404 tăng trên endpoint có object ID tuần tự.
- 429 tăng ở một tenant hoặc API client vượt baseline.
- Response 401 thiếu WWW-Authenticate.
- 429 không có Retry-After trong endpoint có thể dự đoán thời gian chờ.
- Error body status không khớp HTTP status.

## 13. Những sai lầm thường gặp

- **Dùng 401 cho mọi lỗi:** client không phân biệt được authentication và authorization.
- **Dùng 403 khi token hết hạn:** che giấu lỗi credential và khiến client không refresh đúng cách.
- **Dùng 401 khi thiếu scope:** tạo vòng đăng nhập lại không cần thiết.
- **Dùng 404 như cách thay authorization:** object vẫn có thể bị truy cập qua endpoint khác nếu thiếu object policy.
- **Trả 403 cho object ngoài tenant trong khi muốn conceal:** tiết lộ tài nguyên tồn tại.
- **Trả 404 cho lỗi database:** che giấu outage và khiến client hiểu sai.
- **Dùng 429 cho service overload toàn cục:** nhầm lỗi capacity của service với rate limit của caller.
- **Không có Retry-After hoặc client retry vô hạn:** làm tăng tải trong lúc limiter đang bảo vệ hệ thống.
- **Trả lỗi chi tiết:** tiết lộ role, tenant, object, token hoặc rule chống abuse.
- **Cache lỗi theo URL mà bỏ qua principal:** gây rò rỉ hoặc giữ lại quyết định cũ.
- **HTTP status và body status khác nhau:** proxy/SDK/monitoring diễn giải không thống nhất.
- **Không test side effect:** request bị từ chối nhưng nghiệp vụ đã cập nhật trước đó.
- **Dùng một error handler cho tất cả exception:** business conflict, validation và infrastructure failure bị ánh xạ sai.

## 14. Checklist trước khi phát hành

- [ ] 401 chỉ dùng khi credential thiếu hoặc không xác thực được theo contract.
- [ ] Mọi response 401 có WWW-Authenticate challenge phù hợp.
- [ ] 403 dùng cho function/policy denial khi API có thể công khai việc từ chối.
- [ ] Insufficient scope không bị xử lý như yêu cầu đăng nhập lại.
- [ ] Chính sách 403/404 cho object được xác định theo loại tài nguyên và threat model.
- [ ] 404 concealment áp dụng nhất quán cho read, update, delete, search và bulk endpoint.
- [ ] Object query được giới hạn theo tenant/principal context đã xác minh.
- [ ] Response 404 không tiết lộ object, owner hoặc tenant khi cần conceal.
- [ ] Cache policy không chia sẻ error response cá nhân hóa giữa các principal.
- [ ] 429 chỉ dùng cho rate limit/quota phù hợp; service overload toàn cục được phân biệt với 503.
- [ ] Retry-After được gửi khi có thể xác định thời gian chờ.
- [ ] Rate limit xét tenant, principal, client, endpoint/action và global capacity phù hợp.
- [ ] Client retry có backoff, jitter, deadline và idempotency cho thao tác ghi.
- [ ] Error body dùng schema ổn định, HTTP status và body status khớp nhau.
- [ ] Response không chứa stack trace, secret, token hoặc policy nội bộ.
- [ ] Log/metric phân biệt 401, 403, 404 và 429 mà không lưu dữ liệu nhạy cảm.
- [ ] Có test authentication, scope, BOLA, concealment, cache, rate limit và side effect.
- [ ] SDK/gateway giữ nguyên challenge header và Retry-After.

401, 403, 404 và 429 có ý nghĩa khác nhau và dẫn đến hành vi client khác nhau. Khi API phân biệt rõ authentication, authorization, object visibility và rate limiting, đồng thời kiểm soát cache, response body và side effect, status code trở thành một phần đáng tin cậy của security contract thay vì chỉ là con số trả về khi có lỗi.
