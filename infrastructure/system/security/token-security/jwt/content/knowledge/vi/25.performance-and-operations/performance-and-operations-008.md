# Quan sát sự kiện bằng mã tham chiếu an toàn thay vì token đầy đủ

Khi điều tra một request được xác thực bằng JWT, nhóm vận hành thường cần nối các sự kiện giữa client, gateway, resource server và hệ thống audit. Ghi toàn bộ access token vào log để tìm các request liên quan là cách làm nguy hiểm: bearer token là credential, có thể bị phát lại và thường được sao chép sang nhiều hệ thống quan sát. Cách an toàn hơn là dùng mã tham chiếu có phạm vi rõ ràng: request ID hoặc trace ID để nối các bước xử lý; event ID để nhận diện một sự kiện; và token reference dạng giả danh chỉ khi thật sự cần tương quan cùng một token qua nhiều sự kiện.

Bài học thuộc chương **Hiệu năng và vận hành** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào thiết kế mã tham chiếu an toàn, ghi nhận sự kiện xác thực/ủy quyền mà không lưu credential, lựa chọn HMAC fingerprint khi cần, truyền correlation context giữa các dịch vụ, giảm rủi ro riêng tư và kiểm thử toàn bộ pipeline logging. Các nguyên tắc áp dụng cho mọi ngôn ngữ, runtime và nền tảng.

## 1. Vì sao cần mã tham chiếu thay cho token đầy đủ?

JWT access token và refresh token là credential. Người sở hữu bearer token còn hiệu lực có thể thử sử dụng token trong phạm vi quyền được cấp. Khi raw token xuất hiện trong log hoặc trace, những người có quyền đọc hệ thống quan sát có thể có khả năng sử dụng lại credential đó.

Ghi raw token còn tạo ra các vấn đề vận hành:

- Log được sao chép, lập chỉ mục, backup và lưu lâu hơn token trong ứng dụng.
- Nhiều nhóm vận hành, nhà cung cấp APM hoặc hệ thống hỗ trợ có thể truy cập dữ liệu.
- Token có thể xuất hiện trong screenshot, ticket, HAR, diagnostic bundle hoặc bản export.
- Log chứa token làm tăng phạm vi ảnh hưởng khi một tài khoản log bị xâm nhập.
- Tìm kiếm theo token khiến credential bị lặp lại ở nhiều nơi.
- Payload JWT có thể chứa subject, tenant, role hoặc thông tin cá nhân.

Mục tiêu quan sát là trả lời các câu hỏi vận hành như:

- Request nào bị từ chối và ở bước xác minh nào?
- Gateway đã chuyển request tới service nào?
- Các service có cùng xử lý một request không?
- Những sự kiện nào liên quan đến cùng một phiên hoặc token?
- Quyết định authorization được đưa ra theo policy nào?
- Lỗi bắt đầu ở issuer, gateway, resource server hay hệ thống downstream?

Hầu hết câu hỏi này không cần raw JWT. Chúng cần một định danh tương quan an toàn và metadata tối thiểu.

## 2. Phân biệt các loại mã tham chiếu

Không nên dùng một ID duy nhất cho mọi mục đích. Mỗi loại mã cần phạm vi và vòng đời riêng.

| Loại mã | Nhận diện | Phạm vi phù hợp | Có nên chứa token hoặc PII? |
| --- | --- | --- | --- |
| Request ID | Một request HTTP/RPC | Một lần gọi từ điểm vào tới các hop liên quan | Không |
| Trace ID | Một distributed trace | Một luồng công việc có nhiều span/service | Không |
| Span ID | Một thao tác trong trace | Một đoạn xử lý cụ thể | Không |
| Event ID | Một bản ghi sự kiện | Một sự kiện audit/log | Không |
| Session reference | Một phiên đăng nhập | Các sự kiện trong vòng đời phiên | Không; dùng ID opaque hoặc pseudonymous |
| Token reference | Một credential cụ thể | Tương quan có kiểm soát giữa các sự kiện về cùng token | Không chứa raw token; phải được bảo vệ như dữ liệu giả danh |
| Subject reference | Một principal | Tương quan sự kiện của một người dùng/workload | Không chứa sub/email trực tiếp nếu không cần |
| Authorization decision ID | Một quyết định quyền | Request, policy evaluation và audit liên quan | Không |

### 2.1. Request ID

Request ID nhận diện một lần request. Gateway có thể tạo ID ngẫu nhiên nếu request chưa có ID tin cậy. ID này được ghi vào log và truyền tới các service downstream.

Ví dụ:

~~~text
request_id = req-01J8M4K7W6F2
~~~

Request ID không chứng minh request hợp lệ, không đại diện cho người dùng và không được dùng làm credential. Nó chỉ giúp nhóm vận hành tìm các log thuộc cùng một request.

### 2.2. Trace ID và Span ID

Distributed tracing biểu diễn một request hoặc workflow qua nhiều service bằng trace ID và các span ID. Trace context giúp nối thứ tự và quan hệ giữa các thao tác.

- Trace ID nhận diện toàn bộ trace.
- Span ID nhận diện một thao tác.
- Parent/span relationship biểu diễn luồng gọi giữa các thành phần.

Trace context không phải nơi truyền access token, refresh token, session cookie hoặc claims nhạy cảm. Không đặt credential trong trace baggage hoặc span attribute.

### 2.3. Event ID

Event ID nhận diện một bản ghi audit hoặc security event. Nếu cùng một sự kiện được gửi lại do retry, event ID có thể giúp hệ thống downstream nhận ra bản ghi trùng.

Event ID nên được sinh bằng nguồn ngẫu nhiên đủ mạnh hoặc cơ chế ID phù hợp với hệ thống phân tán. Không tạo ID bằng cách nối email, subject, token hoặc timestamp có thể nhận diện người dùng.

### 2.4. Token reference

Token reference dùng khi cần biết nhiều sự kiện có liên quan đến cùng một token, nhưng không muốn lưu token gốc. Đây là mã giả danh, không phải token xác thực mới.

Ví dụ:

~~~text
token_ref = tref:v2:<128-bit-or-longer-digest>
~~~

Giá trị trên chỉ là placeholder minh họa. Digest triển khai thực tế phải có độ dài được chọn theo quy mô và xác suất collision; nếu rút gọn HMAC-SHA-256 thì giữ ít nhất 128 bit sau khi đánh giá rủi ro. Token reference cần được tạo bằng quy trình được kiểm soát, có giới hạn truy cập và retention. Không chấp nhận token reference trong Authorization header hoặc coi nó là bằng chứng người gọi sở hữu JWT.

## 3. Chọn mã tham chiếu theo câu hỏi cần điều tra

Không phải sự kiện nào cũng cần token reference. Ưu tiên ID có phạm vi ngắn và ít khả năng liên kết dữ liệu.

| Câu hỏi | Mã tham chiếu nên dùng | Lý do |
| --- | --- | --- |
| Vì sao request này bị 401? | Request ID | Đủ để tìm các log trong cùng request |
| Gateway đã gọi những service nào? | Trace ID và Span ID | Thể hiện chuỗi hop và thời gian |
| Một audit event có bị ghi lặp? | Event ID | Nhận diện cùng một bản ghi |
| Một phiên bị kết thúc ở đâu? | Session reference | Nối các sự kiện vòng đời phiên |
| Cùng một token có xuất hiện trong nhiều request không? | Token reference có khóa | Chỉ dùng nếu điều tra thực sự cần |
| Một người dùng có nhiều lần bị từ chối? | Subject reference được kiểm soát | Tránh ghi subject/email trực tiếp |
| Quyết định policy nào đã chặn request? | Authorization decision ID | Nối request với policy evaluation |

Một quy tắc hữu ích: dùng request/trace ID cho luồng xử lý; chỉ dùng token reference khi cần tương quan ở cấp credential. Không tạo token reference mặc định cho mọi request nếu không có use case rõ ràng.

## 4. Không ghi raw token trong bất kỳ trường quan sát nào

Các trường sau phải được loại bỏ hoặc redact trước khi log/export:

- Authorization và Proxy-Authorization.
- Cookie và Set-Cookie.
- access_token, refresh_token, id_token.
- JWT compact string hoặc decoded token object.
- Authorization code, client assertion và client secret.
- Private key, signing secret và encryption key.
- Request/response body có chứa credential.
- Exception, debug dump hoặc trace baggage chứa token.

Không chỉ tìm field có tên token. Credential có thể bị nhúng trong message text, URL, query string, nested JSON, form body hoặc object được serialize tự động.

### 4.1. Log không an toàn

~~~json
{
  "event": "jwt.validation.failed",
  "request_id": "req-01J8M4K7W6F2",
  "authorization": "Bearer <RAW_ACCESS_TOKEN>",
  "decoded_payload": {
    "sub": "person-42",
    "email": "person@example.com",
    "tenant": "customer-17"
  }
}
~~~

Log này chứa credential và dữ liệu nhận diện không cần thiết. Chỉ che token ở dashboard cũng chưa đủ nếu raw event đã được gửi tới collector hoặc lưu trong index.

### 4.2. Log an toàn hơn

~~~json
{
  "event": "jwt.validation.failed",
  "event_id": "evt-01J8M4N0B7C9",
  "request_id": "req-01J8M4K7W6F2",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "issuer_profile": "corporate",
  "validation_stage": "audience",
  "failure_code": "wrong_audience",
  "resource": "billing-api",
  "duration_ms": 3
}
~~~

Log an toàn ghi giai đoạn, mã lỗi và mã tương quan. Nó không cần lưu token hoặc toàn bộ claims. Các ID và metadata ví dụ là dữ liệu giả.

## 5. Token reference bằng HMAC fingerprint

Khi cần xác định nhiều sự kiện có cùng một raw token hay không, có thể tạo fingerprint bằng HMAC-SHA-256 với khóa dành riêng cho logging:

~~~text
token_ref = HMAC-SHA-256(logging_key, domain || issuer_id || raw_token)
~~~

Trong đó:

- logging_key là khóa bí mật chỉ dùng cho mục đích tạo reference.
- domain là chuỗi phân tách mục đích, ví dụ jwt-log-token-ref:v1.
- issuer_id là định danh issuer đã được cấu hình; không dùng URL tùy ý từ token chưa xác minh làm nguồn trust.
- raw_token là byte sequence của token nhận được, chỉ dùng trong bộ nhớ để tính HMAC.

HMAC tạo ra mã tham chiếu có tính ổn định với cùng đầu vào và cùng khóa, nhưng người không có logging_key không thể tự tính fingerprint cho một token ứng viên.

### 5.1. Vì sao không dùng hash thường?

Hash không khóa như SHA-256(raw_token) có thể cho phép bên có log và một tập token ứng viên tính lại hash rồi so sánh. JWT thường có entropy cao, nhưng không nên dựa vào điều đó như một biện pháp bảo vệ log.

HMAC thêm một khóa bí mật riêng. Người chỉ đọc log không thể tự tạo fingerprint cho token ứng viên nếu không có khóa.

Không dùng:

~~~text
token_ref = SHA-256(raw_token)
~~~

Ưu tiên HMAC với khóa logging được quản lý riêng nếu fingerprint thực sự cần thiết.

### 5.2. Tách khóa logging khỏi khóa ký và khóa mã hóa

Không tái sử dụng:

- Private key ký JWT.
- HMAC secret dùng ký token.
- Khóa mã hóa JWE.
- Client secret OAuth.
- Khóa database hoặc khóa mã hóa backup.

Khóa logging có mục đích, vòng đời và quyền truy cập khác. Nếu khóa này bị lộ, kẻ tấn công có thể tạo fingerprint cho token ứng viên và liên kết sự kiện trong log; nhưng không được phép có khả năng ký JWT hoặc giải mã dữ liệu.

### 5.3. Domain separation và namespace issuer

Đầu vào HMAC nên có domain separation để cùng một khóa không tạo cùng fingerprint cho các mục đích khác nhau. Nên namespace theo issuer để tránh trùng token bytes hoặc nhầm ngữ cảnh giữa các miền phát hành.

Ví dụ biểu diễn đầu vào:

~~~text
message =
    UTF8("jwt-log-token-ref:v1")
    || 0x00
    || UTF8(configured_issuer_id)
    || 0x00
    || raw_token_bytes
~~~

Đây là định dạng minh họa; cần cố định encoding, delimiter và version để tránh ambiguity. Không đưa sub, email hoặc tenant vào chuỗi đầu vào trừ khi có lý do và policy riêng.

### 5.4. Độ dài fingerprint và nguy cơ collision

HMAC-SHA-256 tạo digest 256 bit. Có thể lưu toàn bộ digest hoặc cắt còn ít nhất 128 bit nếu đã đánh giá quy mô và xác suất va chạm.

Nếu rút ngắn:

- Cố định số bit giữ lại và version format.
- Không cắt tùy tiện theo số ký tự không nhất quán.
- Tính xác suất collision theo số lượng token dự kiến.
- Không dùng reference rút ngắn làm khóa bảo mật hoặc bằng chứng xác thực.
- Khi có collision suspicion, không gộp hai principal hoặc hai credential thành một.

Token reference chỉ phục vụ tương quan log. Nó không được dùng làm primary key của người dùng, không thay thế jti trong protocol và không cấp quyền.

### 5.5. Key rotation và phạm vi tương quan

Nếu logging_key thay đổi, cùng một token sẽ có fingerprint khác. Đây thường là đặc tính có lợi vì nó giới hạn khả năng liên kết dữ liệu qua thời gian.

Thiết kế nên:

- Gắn key version vào token reference, ví dụ tref:v2:....
- Chỉ giữ khóa cũ trong khoảng điều tra/retention cần thiết.
- Không lưu khóa trong log hoặc cùng kho dữ liệu với fingerprint.
- Giới hạn ai có thể yêu cầu tính lại fingerprint.
- Có quy trình thu hồi và rotation khi khóa logging bị lộ.
- Không cố duy trì một fingerprint vĩnh viễn nếu không có nhu cầu nghiệp vụ rõ ràng.

## 6. Token reference không thay thế jti hoặc session ID

Các định danh trong JWT và hệ thống phiên có ngữ nghĩa riêng. Không dùng lẫn chúng.

| Giá trị | Nguồn | Ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| jti | JWT issuer | JWT ID, định danh token theo issuer | Chỉ tin sau khi xác minh; namespace theo iss |
| sid | Profile/session issuer | Định danh phiên trong một số profile | Không phải mọi JWT đều có sid |
| sub | Issuer | Subject của token | Có thể là user hoặc workload; là dữ liệu liên kết |
| request ID | Gateway/server | Một request | Không đại diện cho token hay user |
| trace ID | Tracing system | Một trace | Không phải credential |
| token reference | Logging pipeline | Mã giả danh để tương quan cùng credential | Không dùng trong giao thức xác thực |

### 6.1. Khi dùng jti trong audit

RFC 7519 định nghĩa jti là JWT ID và yêu cầu issuer bảo đảm xác suất va chạm không đáng kể. Tuy vậy, jti không nhất thiết duy nhất giữa các issuer và có thể là dữ liệu liên kết.

Nếu cần dùng jti:

- Chỉ đọc và tin jti sau khi token đã được xác minh.
- Namespace bằng issuer ID.
- Không giả định jti luôn tồn tại nếu profile không yêu cầu.
- Cân nhắc pseudonymize trước khi ghi log.
- Không coi jti đơn lẻ là bằng chứng token hợp lệ.

### 6.2. Khi dùng session reference

Session reference nhận diện phiên đăng nhập chứ không phải từng access token. Một phiên có thể phát hành nhiều access token trong suốt vòng đời.

Nếu cần điều tra đăng xuất, refresh rotation hoặc thiết bị bị mất, session reference thường hữu ích hơn token reference. Nó cũng cần được bảo vệ vì có thể liên kết hành vi của một người dùng qua thời gian.

## 7. Sinh và truyền request/trace ID an toàn

Request ID và trace ID có thể được tạo ở edge hoặc nhận từ caller. Không nên tin mù quáng mọi giá trị bên ngoài.

### 7.1. Request ID từ client

Client có thể gửi một correlation ID để hỗ trợ debug. Gateway nên:

1. Kiểm tra độ dài, charset và format.
2. Từ chối giá trị quá dài hoặc chứa control character.
3. Không cho phép ID chứa token, email hoặc dữ liệu cá nhân.
4. Có thể lưu incoming ID như external_correlation_id riêng biệt.
5. Tạo internal request ID do hệ thống kiểm soát.
6. Ghi mapping giữa internal ID và external ID nếu cần.

Không dùng external request ID để xác thực, phân quyền hoặc chọn tenant.

### 7.2. Truyền qua các service

Gateway có thể truyền request ID và trace context qua các hop nội bộ. Mỗi service cần:

- Giữ nguyên trace context hợp lệ theo chuẩn tracing.
- Tạo span mới cho thao tác của chính nó.
- Không tự thay trace ID để che giấu lỗi liên kết.
- Không thêm Authorization, Cookie hoặc claims vào baggage.
- Không dùng trace context làm bằng chứng user identity.
- Không chấp nhận giá trị context quá lớn hoặc malformed.

Nếu một service xử lý công việc bất đồng bộ, event/message nên mang trace context đã được lọc cùng event ID. Credential không được đưa vào message metadata chỉ để tương quan.

### 7.3. Trace context không phải security context

Trace context trả lời câu hỏi “các thao tác này thuộc cùng một luồng xử lý nào?”. Security context trả lời “principal nào đã được xác thực và có quyền gì?”.

Không đặt subject, role, access token hoặc session secret trong traceparent/tracestate/baggage. Nếu cần liên kết audit với trace, chỉ ghi trace ID trong audit event và lưu security decision trong trường riêng có quyền truy cập phù hợp.

## 8. Thiết kế event schema cho quan sát JWT

Structured event giúp tìm kiếm và tổng hợp mà không cần ghi token.

### 8.1. Trường cơ bản

Một security event có thể chứa:

| Trường | Mục đích | Ghi chú |
| --- | --- | --- |
| timestamp | Thời điểm sự kiện | UTC |
| event_id | Định danh bản ghi | Opaque, không chứa PII |
| event_type | Loại sự kiện | Ví dụ jwt.validation |
| request_id | Liên kết request | Internal ID |
| trace_id/span_id | Liên kết tracing | Theo chuẩn tracing |
| service_name | Thành phần phát sự kiện | Tên service |
| issuer_profile | Trust profile đã chọn | Chỉ sau khi resolve an toàn |
| token_profile | Loại token được kỳ vọng | Ví dụ oauth_access_token |
| validation_stage | Giai đoạn xử lý | parse, signature, claims, authorization |
| result/failure_code | Kết quả chuẩn hóa | Không chứa raw exception |
| audience_profile | Resource profile | Có thể dùng tên cấu hình thay URL nhạy cảm |
| policy_version | Phiên bản policy | Hữu ích khi điều tra |
| duration_ms | Thời gian xử lý | Phục vụ hiệu năng |
| token_ref | Mã giả danh tùy chọn | Chỉ khi có use case |

Không phải event nào cũng cần tất cả trường. Dùng schema theo từng loại event và chỉ thêm trường cần thiết.

### 8.2. Ví dụ event xác minh thất bại

~~~json
{
  "timestamp": "2026-11-16T14:20:31.120Z",
  "event_id": "evt-01J8M4N0B7C9",
  "event_type": "jwt.validation",
  "request_id": "req-01J8M4K7W6F2",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "service_name": "billing-api",
  "issuer_profile": "corporate",
  "token_profile": "oauth_access_token",
  "validation_stage": "claims",
  "result": "rejected",
  "failure_code": "expired",
  "policy_version": "jwt-policy-12",
  "duration_ms": 2
}
~~~

### 8.3. Ví dụ event có token reference

~~~json
{
  "timestamp": "2026-11-16T14:20:31.120Z",
  "event_id": "evt-01J8M4N0B7C9",
  "event_type": "jwt.validation",
  "request_id": "req-01J8M4K7W6F2",
  "issuer_profile": "corporate",
  "token_ref": "tref:v2:<128-bit-or-longer-digest>",
  "validation_stage": "signature",
  "result": "rejected",
  "failure_code": "invalid_signature"
}
~~~

Chỉ bật token_ref khi có yêu cầu điều tra rõ ràng, chẳng hạn phát hiện cùng một credential bị sử dụng ở nhiều request. Không mặc định thêm nó vào mọi event hoặc mọi metric.

## 9. Quan sát quyết định authorization

Khi API từ chối một request, nhóm vận hành thường cần biết vì sao. Có thể ghi policy outcome thay vì ghi claims đầy đủ.

Ví dụ:

~~~json
{
  "event_type": "authorization.decision",
  "event_id": "evt-01J8M4P2D8A1",
  "request_id": "req-01J8M4K7W6F2",
  "decision_id": "dec-01J8M4P1Q9X2",
  "resource_type": "invoice",
  "action": "read",
  "permission_check": "invoice:read",
  "tenant_check": "passed",
  "object_policy": "denied",
  "result": "denied",
  "reason_code": "not_resource_owner"
}
~~~

Không cần ghi invoice payload, email, toàn bộ subject claims hoặc raw token. Nếu cần nhận diện tài nguyên, dùng resource reference giả danh hoặc ID nội bộ có kiểm soát, không đưa dữ liệu cá nhân vào message.

### 9.1. Không biến log thành bản sao của authorization database

Log chỉ nên ghi quyết định và metadata cần điều tra. Không sao chép:

- Toàn bộ user profile.
- Danh sách role/group dài.
- Toàn bộ policy document.
- Nội dung resource.
- Claims chưa được xác minh.

Nếu cần điều tra sâu, dùng decision ID để truy vấn hệ thống audit/policy chuyên biệt có kiểm soát quyền truy cập.

## 10. Metrics: tránh dùng token reference làm label

Metrics cần nhãn có cardinality thấp. Không đưa token_ref, request ID, trace ID, sub, email hoặc session ID vào metric labels.

Ví dụ metrics phù hợp:

~~~text
jwt_validation_total{issuer_profile="corporate",result="rejected",reason="expired"}
jwt_validation_duration_seconds{issuer_profile="corporate"}
authorization_decisions_total{service="billing-api",result="denied",reason="wrong_scope"}
~~~

Metrics không phù hợp:

~~~text
jwt_validation_total{token_ref="tref:...",subject="person-42"}
~~~

Cardinality cao làm tăng chi phí storage/query và có thể khiến dữ liệu nhận diện xuất hiện trong hệ thống metrics có quyền truy cập rộng. Dùng log/trace có kiểm soát để tương quan từng request; dùng metrics để xem xu hướng tổng hợp.

## 11. Quyền truy cập, retention và privacy

Mã tham chiếu an toàn hơn raw token nhưng không mặc nhiên là dữ liệu công khai. Request ID, trace ID, session reference và token reference có thể được liên kết với hành vi hoặc tài khoản khi kết hợp dữ liệu khác.

### 11.1. Phân quyền theo mục đích

- Nhóm vận hành có thể xem request ID và failure code.
- Nhóm bảo mật có thể được cấp quyền xem token reference trong điều tra đã phê duyệt.
- Nhóm phát triển không mặc nhiên cần truy cập raw audit data chứa PII.
- Nhà cung cấp APM chỉ nhận các trường đã được lọc theo hợp đồng và policy.
- Quyền truy cập log cần audit và định kỳ rà soát.

### 11.2. Retention theo loại dữ liệu

Không dùng một retention period cho mọi dữ liệu:

- Request/trace ID có thể được giữ theo thời gian phục vụ vận hành.
- Security audit event có thể có retention theo yêu cầu quản trị/pháp lý.
- Token reference nên có thời hạn tương ứng với mục đích điều tra và được xóa/ẩn danh khi hết nhu cầu.
- HMAC logging key chỉ được giữ trong thời gian cần để tạo/tái tạo reference theo policy.
- Raw token không nên được lưu trong log ngay từ đầu.

### 11.3. Giảm khả năng liên kết dài hạn

Một token reference ổn định trong nhiều tháng có thể giúp liên kết hành vi giữa các dịch vụ và thời điểm. Để giảm rủi ro:

- Dùng key rotation theo chu kỳ.
- Có thể phân tách khóa theo môi trường hoặc miền dữ liệu.
- Giới hạn token reference vào security audit thay vì analytics tổng quát.
- Không chia sẻ reference xuyên tenant nếu không có lý do.
- Tránh kết hợp token_ref với sub/email/IP trong cùng một bản ghi.
- Xóa hoặc chuyển sang thống kê tổng hợp khi hết mục đích điều tra.

## 12. Hiệu năng và độ tin cậy

Mã tham chiếu giúp giảm kích thước log và chi phí lưu trữ so với raw token hoặc toàn bộ claims. Tuy nhiên, việc tạo ID, HMAC và export event vẫn cần được thiết kế phù hợp tải.

### 12.1. Chi phí tính toán

- Request ID và event ID có thể được tạo bằng generator nhẹ.
- Trace context được tạo/truyền bởi instrumentation.
- HMAC-SHA-256 trên token có chi phí nhỏ so với nhiều thao tác mạng/cryptographic validation, nhưng không nên thực hiện nếu không có nhu cầu.
- Không parse lại toàn bộ JWT chỉ để ghi log.
- Không giải mã JWE chỉ để tạo token reference; fingerprint raw bytes là đủ nếu policy yêu cầu.

### 12.2. Không để logging làm hỏng request path

- Dùng structured event nhỏ và giới hạn kích thước.
- Có queue/buffer có giới hạn.
- Đặt timeout cho exporter.
- Không block xác minh JWT chỉ để gửi log đồng bộ.
- Có backpressure và drop policy được quan sát.
- Không drop security audit quan trọng một cách âm thầm; có metric/alert khi event không được ghi.

Phân biệt telemetry thông thường với audit event bắt buộc. Tracing có thể sampling; audit security quan trọng có thể cần ghi bền vững theo policy. Không dùng sampling để vô tình bỏ mất sự kiện bảo mật phải lưu.

### 12.3. Khi logging pipeline bị lỗi

Hệ thống cần quyết định theo loại sự kiện:

| Loại dữ liệu | Khi exporter lỗi |
| --- | --- |
| Debug trace | Có thể retry/drop theo sampling và policy |
| Operational metrics | Buffer/retry có giới hạn |
| Security audit bắt buộc | Dùng durable queue/outbox hoặc cơ chế lưu bền vững |
| Token reference | Không được fallback sang ghi raw token |
| Diagnostic payload | Không gửi sang nơi khác để né lỗi exporter |

Không bao giờ tắt redaction chỉ để khôi phục log khi pipeline gặp sự cố.

## 13. Quy trình điều tra sự kiện JWT

Một quy trình điều tra có thể bắt đầu bằng request ID và chỉ mở rộng sang token reference nếu cần:

1. Nhận request ID hoặc event ID từ báo cáo lỗi.
2. Tìm security event tương ứng trong log đã được redact.
3. Dùng trace ID để xem các hop gateway/resource service.
4. Xem validation stage và failure code.
5. Xem policy version, issuer profile và audience profile.
6. Nếu nghi ngờ cùng token được phát lại, tìm token_ref trong security audit có quyền truy cập hạn chế.
7. Đối chiếu thời điểm, service, network context và authorization outcome.
8. Nếu cần hành động thu hồi, dùng session/grant/token registry chính thức; không dùng log reference làm credential.
9. Ghi kết quả điều tra bằng event ID và reference an toàn.

~~~mermaid
flowchart TD
    A["Báo cáo sự cố / request ID"] --> B["Tìm event đã redact"]
    B --> C["Mở trace theo trace ID"]
    C --> D["Xem validation stage và failure code"]
    D --> E{"Cần tương quan cùng token?"}
    E -- "Không" --> H["Kết luận theo request/policy"]
    E -- "Có" --> F["Tra token_ref trong security audit hạn chế"]
    F --> G["Đối chiếu sự kiện và session state"]
    G --> H
    H --> I["Ghi kết quả bằng event ID/reference an toàn"]
~~~

## 14. Khi token reference bị lộ hoặc lạm dụng

Token reference không phải bearer credential, nhưng vẫn có thể tiết lộ khả năng liên kết sự kiện. Nếu HMAC logging key bị lộ, kẻ tấn công có thể tạo fingerprint cho token ứng viên và tìm sự kiện tương ứng trong log.

Khi có sự cố:

1. Xác định loại reference bị lộ: request ID, session reference hay token reference.
2. Kiểm tra có raw token hoặc logging key đi kèm hay không.
3. Nếu chỉ lộ reference, đánh giá khả năng liên kết và dữ liệu có thể suy ra.
4. Nếu logging key bị lộ, rotate key và chuyển sang key version mới.
5. Hạn chế truy cập log có reference bị ảnh hưởng.
6. Kiểm tra các hệ thống đã nhận reference và bản export.
7. Nếu raw token cũng bị lộ, xử lý như credential exposure: thu hồi token/grant hoặc session theo khả năng.
8. Rà soát quyền truy cập và nguyên nhân dữ liệu bị phát tán.

Không nhầm việc rotate logging key với thu hồi JWT. Hai khóa có mục đích khác nhau; đổi khóa fingerprint không làm access token mất hiệu lực.

## 15. Checklist triển khai mã tham chiếu an toàn

### Thiết kế định danh

- [ ] Mỗi ID có mục đích và phạm vi rõ: request, trace, event, session, token hoặc decision.
- [ ] ID không chứa raw token, subject, email, tenant hoặc dữ liệu cá nhân.
- [ ] Request ID bên ngoài được kiểm tra và tách khỏi internal request ID.
- [ ] Trace ID/Span ID không được dùng làm credential hoặc security context.
- [ ] Token reference chỉ được bật khi có use case cụ thể.
- [ ] Token reference không được chấp nhận trong Authorization header.

### Token reference và khóa

- [ ] Dùng HMAC-SHA-256 thay vì hash thường khi cần fingerprint token.
- [ ] Logging key tách biệt với signing/encryption/client secrets.
- [ ] Có domain separation và issuer namespace.
- [ ] Có key version, rotation và retention.
- [ ] Không ghi logging key hoặc raw token.
- [ ] Giới hạn người có quyền tra cứu hoặc tính fingerprint.
- [ ] Không dùng token_ref làm user ID, revocation proof hoặc authorization credential.

### Logging và tracing

- [ ] Redact Authorization, Cookie, token field và credential ở nguồn.
- [ ] Structured logging dùng allowlist.
- [ ] Event ghi request ID, trace ID, failure code và policy metadata cần thiết.
- [ ] Không ghi toàn bộ claims hoặc exception chứa token.
- [ ] Không đưa token/PII vào baggage hoặc span attribute.
- [ ] Metrics không dùng token_ref/request ID/subject làm label.
- [ ] Audit event quan trọng có durable delivery theo policy.

### Privacy và vận hành

- [ ] Quyền đọc log/reference theo nguyên tắc least privilege.
- [ ] Retention phù hợp mục đích và yêu cầu quản trị.
- [ ] Có key rotation và incident response cho logging key.
- [ ] Có canary test để phát hiện raw token trong pipeline.
- [ ] Không tắt redaction khi exporter lỗi.
- [ ] Có hướng dẫn điều tra bắt đầu từ request ID, chỉ dùng token_ref khi cần.

## 16. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Request có Authorization Bearer | Raw header không xuất hiện trong log/trace |
| Nhiều service xử lý cùng request | Internal request ID và trace ID nối được các event |
| Client gửi request ID quá dài hoặc chứa control chars | Gateway từ chối hoặc tạo internal ID mới theo policy |
| Client gửi request ID có email/token | Giá trị bị từ chối hoặc không đưa vào log |
| Cùng token được ghi ở nhiều event và token_ref được bật | Reference giống nhau trong cùng key version/issuer namespace |
| Token giống bytes nhưng issuer namespace khác | Reference khác nhau |
| Logging key được rotate | Reference có version mới; không giả định fingerprint cũ và mới bằng nhau |
| Logging key bị lộ | Có thể rotate và hạn chế tra cứu; không ảnh hưởng signing key |
| Token reference được gửi như bearer credential | Resource server từ chối |
| jti bị thiếu trong token profile tùy chọn | Không làm parser tự tạo jti; event dùng request/event ID |
| jti trùng giữa hai issuer | Namespace issuer giữ hai định danh riêng |
| Trace baggage chứa Authorization | Redaction/test phát hiện và loại bỏ trước export |
| Token_ref được dùng làm metric label | Kiểm thử schema/metric policy từ chối |
| Logging exporter bị lỗi | Không fallback sang ghi raw token |
| Raw token canary xuất hiện trong log backend | Kiểm thử thất bại và phát cảnh báo |
| Security audit event bị retry | Event ID giúp nhận diện duplicate mà không cần token |

## 17. Tình huống thực tế

### Tình huống A — Nhóm vận hành tìm request bằng raw JWT

Một nhóm ghi token vào log để tìm mọi request dùng cùng credential. Log được gửi sang APM và nhiều nhóm có quyền truy cập.

**Bài học:** dùng request ID/trace ID cho luồng xử lý; token_ref HMAC chỉ khi thực sự cần tương quan credential.

### Tình huống B — Request ID do client kiểm soát

Client gửi một chuỗi dài chứa email và token vào header correlation. Gateway ghi nguyên giá trị vào log.

**Bài học:** validate external ID, giới hạn độ dài/charset và tạo internal request ID do hệ thống kiểm soát.

### Tình huống C — Dùng SHA-256(raw token) làm token reference

Log lưu hash token. Một người có tập token ứng viên có thể tính lại hash và tìm các sự kiện tương ứng.

**Bài học:** dùng HMAC với logging key riêng nếu fingerprint cần thiết; hash thường không có khóa không bảo vệ tốt trước phép so sánh ứng viên.

### Tình huống D — Token reference dùng chung quá lâu

Một fingerprint ổn định được ghi trong mọi hệ thống suốt nhiều năm. Người đọc dữ liệu có thể liên kết hoạt động của cùng credential qua nhiều dịch vụ.

**Bài học:** key rotation, giới hạn phạm vi và retention; không bật token_ref trên mọi event.

### Tình huống E — Trace baggage mang access token

Một service đưa Authorization vào baggage để downstream service có thể đọc. Trace được export tới vendor và archive.

**Bài học:** trace context chỉ mang correlation metadata; credential phải đi trong kênh request được bảo vệ và không xuất hiện trong telemetry.

### Tình huống F — Logging pipeline lỗi nên raw request được dump

Exporter không khả dụng. Một nhánh fallback ghi toàn bộ request object để không mất thông tin.

**Bài học:** fallback không bao giờ được tắt redaction; dùng buffer/durable queue cho audit theo policy.

## 18. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Có cần raw JWT để nối log giữa gateway và resource service không? | **Không.** Request ID và trace ID thường đủ. |
| Token reference có phải credential thay thế không? | **Không.** Nó chỉ là mã giả danh để tương quan log. |
| Khi nào nên tạo token reference? | Chỉ khi có nhu cầu điều tra cùng một token qua nhiều sự kiện và request/trace ID không đủ. |
| Vì sao HMAC phù hợp hơn hash thường cho fingerprint? | HMAC cần khóa bí mật riêng nên người chỉ đọc log không thể tự tính reference cho token ứng viên. |
| Có nên dùng signing key để tạo token reference không? | **Không.** Dùng logging key riêng. |
| Có thể dùng jti thay request ID không? | **Không.** jti nhận diện token; request ID nhận diện một request. |
| Có nên đặt token_ref trong metrics label không? | **Không.** Cardinality cao và rủi ro liên kết dữ liệu. |
| Trace baggage có nên chứa access token không? | **Không.** Trace context không phải security context. |
| Rotate logging key có thu hồi JWT không? | **Không.** Hai loại khóa có mục đích khác nhau. |
| Token reference có thể dùng làm bằng chứng authorization không? | **Không.** Authorization phải dựa trên credential đã xác minh và policy. |

## 19. Ghi nhớ

- Không ghi raw JWT hoặc bearer credential để phục vụ quan sát.
- Dùng request ID, trace ID, span ID và event ID cho tương quan theo request/workflow/sự kiện.
- Chỉ dùng token reference khi cần tương quan cùng credential; coi nó là dữ liệu giả danh cần kiểm soát.
- Nếu cần fingerprint, dùng HMAC-SHA-256 với logging key riêng, domain separation và issuer namespace.
- Không dùng hash thường, signing key hoặc encryption key để tạo token reference.
- Phân biệt token reference với jti, sid, sub, request ID và session reference.
- Không đưa token hoặc PII vào trace baggage, span attributes hoặc metric labels.
- Structured logging nên dùng allowlist, failure code và policy metadata tối thiểu.
- Key rotation của logging không thay thế token revocation; raw token bị lộ vẫn cần quy trình credential incident.
- Kiểm thử toàn bộ pipeline từ ứng dụng, gateway, collector, APM đến archive để bảo đảm raw token không xuất hiện.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT), jti Claim](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 2104 – HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104)
- [FIPS 198-1 – The Keyed-Hash Message Authentication Code (HMAC)](https://csrc.nist.gov/pubs/fips/198-1/final)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)
- [OpenTelemetry – Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
