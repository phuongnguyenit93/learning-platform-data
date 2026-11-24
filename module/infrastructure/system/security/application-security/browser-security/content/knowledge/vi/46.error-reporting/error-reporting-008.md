# Không lộ thông tin nội bộ khi báo lỗi cho client

Ứng dụng web cần báo lỗi đủ rõ để người dùng biết request thất bại và đội vận hành tìm được nguyên nhân. Nhưng response lỗi cũng là một kênh xuất dữ liệu. Nếu trả nguyên exception, stack trace, SQL query, đường dẫn máy chủ, tên service, cấu hình hoặc dữ liệu request, ứng dụng có thể tiết lộ cách hệ thống được xây dựng và thông tin có thể giúp attacker chuẩn bị bước tấn công tiếp theo.

Nguyên tắc quan trọng là tách thông tin dành cho client khỏi dữ liệu chẩn đoán nội bộ. Client nhận status code, mã lỗi ổn định, thông điệp đã được duyệt và request ID để liên hệ hỗ trợ. Log/APM nội bộ giữ chi tiết kỹ thuật cần thiết, với quyền truy cập, redaction và thời gian lưu phù hợp.

Bài học này trình bày cách thiết kế error response an toàn, ánh xạ exception sang HTTP status, dùng Problem Details, bảo vệ dữ liệu nhạy cảm trong log, xử lý lỗi xác thực/validation, cấu hình middleware và kiểm thử để bảo đảm lỗi production không làm lộ thông tin nội bộ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao error response là một bề mặt rò rỉ thông tin.
- Nhận diện dữ liệu nội bộ không được gửi cho client.
- Phân biệt thông điệp public với exception, stack trace và log nội bộ.
- Ánh xạ lỗi nghiệp vụ sang HTTP status và error code ổn định.
- Thiết kế response theo RFC 9457 Problem Details.
- Tạo request/correlation ID để hỗ trợ điều tra mà không tiết lộ chi tiết hệ thống.
- Redact secret, PII và dữ liệu đầu vào khỏi log.
- Tránh account enumeration và lộ thông tin qua validation/authentication errors.
- Cấu hình error middleware an toàn trong backend và xử lý lỗi ở frontend.
- Kiểm thử lỗi 4xx/5xx, lỗi parser, timeout và lỗi từ dependency.
- Xây dựng quy trình điều tra sự cố mà không đưa log nhạy cảm vào ticket công khai.

## 1. Vì sao thông báo lỗi có thể trở thành lỗ hổng?

Một exception thường được tạo ra để giúp lập trình viên hiểu điều gì đã xảy ra. Nội dung của nó có thể chứa thông tin chỉ phù hợp với người vận hành.

Ví dụ response không an toàn:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/plain

TypeError: Cannot read properties of undefined (reading 'id')
    at /srv/app/src/controllers/account.js:84:17
    at processTicksAndRejections (node:internal/process/task_queues:95:5)
Database: postgres://app_user:secret@db-prod-03.internal:5432/customer
SQL: SELECT * FROM users WHERE email = 'person@example.test'
~~~

Response này tiết lộ:

- Ngôn ngữ/runtime và cấu trúc framework.
- Đường dẫn thư mục và tên file source.
- Tên database, host nội bộ, username và có thể cả password.
- Câu SQL và dữ liệu cá nhân.
- Chi tiết luồng xử lý có thể giúp attacker suy đoán kiến trúc.

Trong production, client chỉ cần biết request thất bại và cách tiếp tục hoặc liên hệ hỗ trợ. Stack trace và chi tiết dependency phải đi vào hệ thống chẩn đoán nội bộ được kiểm soát.

### 1.1 Những gì attacker có thể suy ra

Một lỗi quá chi tiết có thể hỗ trợ reconnaissance:

- Tên thư viện, framework và phiên bản.
- Đường dẫn file, tên class, method và module.
- Schema database, table, column và câu query.
- Tên bucket, hostname, IP hoặc service nội bộ.
- Cách cấu hình authentication, authorization và session.
- Loại dependency, queue, cache hoặc storage.
- Input nào làm parser hoặc code path thất bại.

Thông tin đơn lẻ có thể chưa đủ để khai thác, nhưng nhiều response kết hợp có thể giúp xây dựng bản đồ hệ thống.

### 1.2 Error disclosure có thể làm lộ secret và dữ liệu cá nhân

Exception message hoặc validation error đôi khi chứa:

- Password, OTP, reset token hoặc access token.
- Cookie, Authorization header và CSRF token.
- API key, connection string và private key.
- Email, số điện thoại, địa chỉ hoặc identifier khách hàng.
- Nội dung request body hoặc file upload.
- Signed URL, storage key và đường dẫn tài liệu.
- Dữ liệu từ dịch vụ bên thứ ba.

Không gửi những giá trị này trong response hoặc log mặc định. Nếu cần dùng một identifier để điều tra, hãy chọn ID nội bộ không mang quyền truy cập và không trực tiếp nhận diện cá nhân.

### 1.3 Phân biệt lỗi dự kiến và lỗi bất ngờ

| Nhóm lỗi | Ví dụ | Cách phản hồi |
|---|---|---|
| Input không hợp lệ | JSON sai cú pháp, thiếu field | 400 hoặc 422 với thông điệp đã duyệt |
| Chưa xác thực | Session thiếu/hết hạn | 401 với hướng xử lý phù hợp |
| Không đủ quyền | User không được truy cập tài nguyên | 403 hoặc 404 theo chính sách chống dò tìm |
| Không tồn tại | Resource ID không có | 404 |
| Xung đột nghiệp vụ | Email đã dùng, version conflict | 409 với mã lỗi nghiệp vụ an toàn |
| Quá tải/giới hạn | Rate limit, payload quá lớn | 429 hoặc 413 |
| Dependency lỗi | Database, queue hoặc upstream timeout | 502/503/504 tùy vai trò và nguyên nhân |
| Lỗi không dự kiến | Bug, invariant violation | 500 với thông điệp chung |

Không biến mọi exception thành 200 kèm { "success": false }. HTTP status phải phản ánh kết quả để browser, proxy, monitoring và client xử lý đúng.

## 2. Phân loại thông tin: public và internal

Trước khi thiết kế error schema, xác định rõ trường nào được phép rời khỏi server.

| Thông tin | Gửi cho client? | Ghi log nội bộ? |
|---|---|---|
| HTTP status | Có | Có |
| Error code ổn định | Có | Có |
| Thông điệp đã được duyệt | Có | Có |
| Request ID ngẫu nhiên | Có | Có |
| Field validation allowlist | Có, khi an toàn | Có, sau khi lọc |
| Stack trace | Không | Có thể, trong sink hạn chế |
| Exception message nguyên bản | Không | Chỉ sau redaction và review |
| SQL query/connection string | Không | Tránh log; nếu bắt buộc phải lọc |
| Internal hostname/IP/path | Không | Chỉ khi cần và được bảo vệ |
| Cookie/token/password | Không | Không log giá trị |
| Request/response body đầy đủ | Không | Chỉ khi có nhu cầu rõ ràng và đã lọc |
| PII | Chỉ khi thật sự cần cho chức năng | Minimize, mask hoặc pseudonymize |

### 2.1 Thông điệp public phải do ứng dụng kiểm soát

Thông điệp public nên mô tả điều người dùng có thể làm tiếp theo:

- "Yêu cầu không hợp lệ. Hãy kiểm tra các trường được đánh dấu."
- "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại."
- "Bạn không có quyền thực hiện thao tác này."
- "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau."
- "Không thể hoàn tất yêu cầu. Hãy cung cấp mã tham chiếu khi liên hệ hỗ trợ."

Không đưa nguyên văn err.message vào response. Message có thể được tạo từ input, dependency hoặc runtime và chưa được duyệt để hiển thị.

### 2.2 Error code phải ổn định

Ví dụ:

~~~json
{
  "errorCode": "PROFILE_UPDATE_CONFLICT",
  "message": "Thông tin hồ sơ vừa được thay đổi. Hãy tải lại và thử lại."
}
~~~

Client có thể dựa vào errorCode để hiển thị UI hoặc quyết định retry. Không dùng nội dung message làm logic vì câu chữ có thể thay đổi, được dịch hoặc cần điều chỉnh.

Không đưa mã lỗi nội bộ như tên class, tên bảng, mã exception của database hoặc số dòng source vào public error code.

### 2.3 Không tiết lộ sự tồn tại của tài khoản/tài nguyên

Ở luồng đăng nhập, quên mật khẩu hoặc mời thành viên, response khác nhau quá rõ có thể cho attacker dò tài khoản.

Ví dụ thông báo nên thống nhất cho cả email không tồn tại và email đã nhận yêu cầu reset:

~~~text
Nếu địa chỉ này có tài khoản phù hợp, hướng dẫn tiếp theo sẽ được gửi.
~~~

Cần xem cả status code, response body, redirect và thời gian xử lý. Không tiết lộ account existence chỉ qua một kênh phụ như thông báo lỗi hoặc timing quá khác biệt rõ.

## 3. HTTP status và error contract

Error contract giúp frontend, mobile client, integration và monitoring hiểu cùng một cách.

### 3.1 Chọn status code theo ngữ nghĩa

| Status | Dùng khi | Ví dụ thông điệp public |
|---|---|---|
| 400 Bad Request | Request syntax/cấu trúc không hợp lệ | "Request không đúng định dạng." |
| 401 Unauthorized | Thiếu hoặc credential không hợp lệ | "Bạn cần đăng nhập để tiếp tục." |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền | "Bạn không có quyền thực hiện thao tác này." |
| 404 Not Found | Resource không tồn tại hoặc cần che việc tồn tại | "Không tìm thấy tài nguyên." |
| 409 Conflict | Xung đột trạng thái nghiệp vụ | "Dữ liệu đã thay đổi. Hãy tải lại." |
| 413 Content Too Large | Body vượt giới hạn | "Dữ liệu gửi lên quá lớn." |
| 415 Unsupported Media Type | Media type không hỗ trợ | "Định dạng nội dung không được hỗ trợ." |
| 422 Unprocessable Content | Cú pháp hợp lệ nhưng dữ liệu không đạt quy tắc | "Một số trường chưa hợp lệ." |
| 429 Too Many Requests | Vượt rate limit | "Bạn thao tác quá nhanh. Hãy thử lại sau." |
| 500 Internal Server Error | Lỗi không dự kiến trong ứng dụng | "Không thể hoàn tất yêu cầu." |
| 502 Bad Gateway | Upstream trả response không hợp lệ | "Dịch vụ phụ trợ gặp sự cố." |
| 503 Service Unavailable | Service tạm không sẵn sàng | "Dịch vụ đang bận. Hãy thử lại sau." |
| 504 Gateway Timeout | Upstream không phản hồi đúng hạn | "Dịch vụ phản hồi quá chậm." |

Status cụ thể phụ thuộc API contract và vai trò của service. Không dùng 500 cho lỗi validation hoặc 200 cho lỗi server.

### 3.2 Retry-After và retry policy

Với 429 hoặc 503, server có thể gửi:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/problem+json
~~~

Client nên tôn trọng `Retry-After` và dùng backoff có jitter. Không retry vô hạn hoặc retry tự động request không idempotent nếu không có idempotency key và contract rõ ràng.

### 3.3 Không để status và body mâu thuẫn

Không trả HTTP 200 nhưng body nói `status: 500`. Monitoring, cache, browser và client thường dựa vào status line. Nếu dùng Problem Details, field `status` phải phản ánh status HTTP được gửi.

## 4. Problem Details với application/problem+json

RFC 9457 định nghĩa Problem Details cho HTTP APIs. Media type là `application/problem+json`. Nó cung cấp cấu trúc thống nhất để mô tả lỗi mà không phải đưa exception nội bộ vào response.

Ví dụ:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{
  "type": "https://api.example.test/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "detail": "Một số trường cần được kiểm tra lại.",
  "instance": "/requests/req-8f2c"
}
~~~

### 4.1 Các field chuẩn

| Field | Ý nghĩa | Lưu ý bảo mật |
|---|---|---|
| `type` | URI định danh loại problem | Dùng URI do ứng dụng kiểm soát, không chứa secret |
| `title` | Tóm tắt loại lỗi | Thông điệp public ổn định |
| `status` | HTTP status tương ứng | Phải khớp status line |
| `detail` | Giải thích instance cụ thể | Không chép exception hoặc input nhạy cảm |
| `instance` | URI tham chiếu instance lỗi | Dùng request ID/URI không tiết lộ đường dẫn nội bộ |

Có thể thêm extension như `errorCode` hoặc `requestId` nếu contract quy định rõ. Tránh đưa stack, SQL, hostname, tên class hoặc cấu hình vào extension.

### 4.2 Validation detail có giới hạn

Response validation có thể cho biết field nào sai nếu tên field và thông điệp đã được kiểm soát:

~~~json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "errorCode": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Địa chỉ email chưa đúng định dạng."
    }
  ]
}
~~~

Chỉ trả tên field nằm trong schema public và mã lỗi đã định nghĩa. Không trả giá trị field người dùng gửi, rule nội bộ, regex phức tạp, câu query hoặc exception từ validator.

### 4.3 Không dùng detail làm nơi debug

Sai:

~~~json
{
  "title": "Database error",
  "detail": "duplicate key value violates unique constraint users_email_key at /srv/app/db/users.js:91"
}
~~~

Đúng:

~~~json
{
  "title": "Không thể cập nhật thông tin",
  "detail": "Dữ liệu có thể đã được thay đổi. Hãy tải lại và thử lại.",
  "errorCode": "UPDATE_CONFLICT",
  "requestId": "req-8f2c"
}
~~~

Client nhận được thông tin hành động; đội vận hành dùng request ID để tìm event nội bộ tương ứng.

## 5. Những dữ liệu tuyệt đối không đưa vào error response

### 5.1 Stack trace và exception object

Không serialize trực tiếp:

~~~js
res.status(500).json({
  error: err,
  stack: err.stack
});
~~~

Exception object có thể chứa message, stack, cause, request context hoặc field do dependency thêm vào. Một số serializer còn gọi getter hoặc chuyển đổi object phức tạp ngoài dự kiến.

Không trả `err.stack`, `err.cause` hoặc object exception nguyên bản cho client production.

### 5.2 Database và hạ tầng

Không trả:

- SQL statement và bind parameter.
- Tên database, schema, table hoặc index.
- Connection string, username, password.
- Internal DNS, hostname, private IP và port.
- Cloud account ID, bucket name hoặc storage path.
- Queue/topic nội bộ, service discovery name.
- Đường dẫn file, thư mục deploy và process environment.
- Tên cluster, namespace hoặc topology.

Các chi tiết này có thể được giữ trong log nội bộ khi cần, nhưng phải hạn chế quyền và loại bỏ credential/PII.

### 5.3 Secret và credential

Không trả hoặc log giá trị:

- `Authorization`, `Cookie`, `Set-Cookie`.
- Password, OTP, access token, refresh token.
- API key, client secret, private key.
- OAuth authorization code, reset token, invitation token.
- Signed URL hoặc URL có capability token.
- CSRF token và session identifier.

Nếu lỗi liên quan credential, chỉ ghi loại credential, trạng thái xác minh hoặc fingerprint đã được thiết kế an toàn. Không dùng hash yếu của token ngắn làm bằng chứng công khai; token entropy thấp có thể bị dò từ hash.

### 5.4 PII và input do người dùng kiểm soát

Không đưa nguyên văn request body, form value, file name hoặc query vào error message. Dữ liệu có thể chứa PII, secret hoặc chuỗi điều khiển log.

Nếu cần xác định field lỗi, trả field name và error code. Nếu cần điều tra payload, dùng test fixture hoặc bản sao đã redact trong kho có kiểm soát.

## 6. Logging an toàn: giữ đủ bằng chứng nhưng không nhân bản secret

Log nội bộ là nơi đội vận hành điều tra. Nhưng log cũng là dữ liệu cần bảo vệ: có thể được chuyển qua agent, collector, SIEM, APM, cloud logging và nhiều nhóm người dùng.

### 6.1 Dùng structured logging

Ưu tiên event có schema:

~~~json
{
  "timestamp": "2026-11-22T09:30:00Z",
  "level": "error",
  "event": "http.request.failed",
  "requestId": "req-8f2c",
  "route": "/api/profile",
  "method": "PATCH",
  "status": 500,
  "errorCode": "UNEXPECTED_ERROR",
  "errorType": "TypeError",
  "durationMs": 84
}
~~~

Event này giúp lọc theo request, route, status và error type mà không cần ghi request body hay credential.

### 6.2 Allowlist trường log

Không serialize toàn bộ `req`, `res` hoặc `err`. Chọn các field cần thiết:

- Request ID do server tạo.
- Route template, method, status và duration.
- Error category/code và dependency name đã được chuẩn hóa.
- Tenant/user pseudonymous ID khi thực sự cần.
- Release/build version không nhạy cảm.
- Trace ID hợp lệ nếu hệ thống tracing đã cấu hình.

Tránh log raw URL khi query có token; dùng route template hoặc URL đã lọc.

### 6.3 Redaction trước khi ghi

Redaction phải diễn ra ở điểm phát log và tiếp tục ở collector như lớp phòng vệ thứ hai. Các tên thường cần lọc gồm authorization, cookie, set-cookie, password, token, secret, api_key, client_secret và các alias của hệ thống.

Đừng chỉ dựa vào regex cho một vài key: secret có thể nằm trong nested JSON, URL, header tùy biến, form data, exception cause hoặc chuỗi log ghép. Allowlist là lựa chọn mặc định an toàn hơn.

### 6.4 Stack trace chỉ ở sink nội bộ có kiểm soát

Stack trace hữu ích cho điều tra nhưng có thể chứa source path, module, query và giá trị input. Chỉ gửi đến error tracker/log sink đã được phê duyệt, có:

- Authentication và role-based access.
- Encryption khi truyền và khi lưu.
- Redaction/scrubbing trước ingestion.
- Retention và deletion policy.
- Audit truy cập.
- Phân tách môi trường và tenant.
- Quy trình xử lý export/download.

Không gửi stack trace tới analytics hoặc frontend telemetry chung nếu không có kiểm soát tương đương.

### 6.5 Không log exception message một cách mù quáng

Exception message có thể được tạo từ dữ liệu người dùng hoặc upstream. Log error type và error code trước; chỉ ghi message/stack đã scrub trong sink nội bộ khi có nhu cầu điều tra rõ ràng. Không để logger tự động serialize request context chứa credential.

### 6.6 Bảo vệ log khỏi log injection

Attacker có thể gửi newline, ký tự điều khiển hoặc chuỗi giả mạo để tạo log entry trông như sự kiện khác. Khi ghi input do user kiểm soát:

- Dùng structured logger thay nối chuỗi.
- Encode/escape control characters.
- Giới hạn độ dài field.
- Không tin `X-Request-ID` do client tùy ý cung cấp.
- Không ghi raw body hoặc header chưa lọc.
- Giữ nguyên metadata nguồn để phân biệt event do server tạo và dữ liệu user.

## 7. Request ID, correlation ID và tracing

Request ID cho phép người dùng báo một mã tham chiếu để đội hỗ trợ tìm đúng request. Nó không cần chứa thông tin về user, server hoặc cấu trúc hệ thống.

### 7.1 Tạo ID ở server

Ví dụ Express:

~~~js
import { randomUUID } from "node:crypto";

app.use((req, res, next) => {
  req.requestId = randomUUID();
  res.setHeader("X-Request-ID", req.requestId);
  next();
});
~~~

ID ngẫu nhiên giúp tránh việc client đoán hoặc tự chọn ID trùng với event khác. Nếu hệ thống dùng gateway tạo request ID, hãy xác thực ranh giới tin cậy và quy định rõ thành phần nào được phép đặt giá trị.

### 7.2 Không tin header do client gửi một cách mù quáng

Client có thể gửi `X-Request-ID` tùy ý. Nếu dùng trực tiếp, attacker có thể tạo collision, giả mạo correlation hoặc chèn nội dung gây log injection.

Có thể giữ client request ID đã validate trong field riêng, nhưng nên tạo internal request ID do server kiểm soát và log cả hai với tên rõ ràng. Với distributed tracing, validate định dạng W3C `traceparent` tại trust boundary; không coi trace ID là credential hoặc bằng chứng xác thực.

### 7.3 Trả request ID trong error response

Ví dụ:

~~~http
HTTP/1.1 500 Internal Server Error
X-Request-ID: 8f2c7b1e-...
Content-Type: application/problem+json
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.test/problems/internal",
  "title": "Không thể hoàn tất yêu cầu",
  "status": 500,
  "detail": "Đã xảy ra lỗi. Hãy thử lại sau hoặc liên hệ hỗ trợ.",
  "requestId": "8f2c7b1e-..."
}
~~~

Request ID chỉ là mã tham chiếu. Không cho phép người dùng tra cứu log tùy ý chỉ bằng cách cung cấp ID; hệ thống hỗ trợ phải xác thực và kiểm tra quyền.

### 7.4 Trace ID và span ID

Trong hệ thống nhiều service, trace ID liên kết các span qua gateway, API, queue và dependency. Không gửi toàn bộ trace hoặc internal span detail cho client. Chỉ trả ID tham chiếu đã được thiết kế public; giữ topology và span attributes trong tracing backend được bảo vệ.

## 8. Authentication, authorization và validation errors

Lỗi xác thực và phân quyền cần cân bằng giữa usability và khả năng chống dò tìm.

### 8.1 Đăng nhập và account enumeration

Không trả message khác nhau cho "email không tồn tại" và "password sai" nếu threat model yêu cầu chống enumeration. Dùng response thống nhất, giới hạn rate và giám sát thử nhiều account.

Không trả username/email đã tồn tại trong exception từ database constraint. Ánh xạ lỗi unique constraint sang mã nghiệp vụ public nếu sản phẩm cần báo xung đột, và đánh giá xem việc tiết lộ trạng thái account có phù hợp với luồng đó không.

### 8.2 Quên mật khẩu và OTP

Response nên không xác nhận email/phone có tồn tại. Không trả reset token, OTP hoặc link đặt lại mật khẩu trong error response hay log. Rate-limit theo account, IP và các chiều phù hợp; tránh để response timing tiết lộ account existence.

### 8.3 401, 403 và 404

- 401: credential thiếu, hết hạn hoặc không hợp lệ; có thể kèm challenge theo authentication scheme.
- 403: user đã xác thực nhưng không đủ quyền.
- 404: có thể dùng khi cần tránh tiết lộ resource có tồn tại hay không.

Chọn policy nhất quán. Không trả tên role nội bộ, ACL, policy expression hoặc lý do chi tiết khiến user biết cách vượt kiểm soát.

### 8.4 Validation errors

Trả lỗi field-level khi cần cho UX, nhưng chỉ dùng field public và rule đã duyệt. Không trả raw input hoặc toàn bộ validator context.

Ví dụ:

~~~json
{
  "errorCode": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "phone",
      "code": "INVALID_FORMAT",
      "message": "Số điện thoại chưa đúng định dạng."
    }
  ]
}
~~~

Nếu trường chứa password, token hoặc thông tin nhạy cảm, không echo lại giá trị. Không trả regex nội bộ hoặc danh sách account đã đăng ký.

### 8.5 CSRF, CORS và security policy errors

Thông báo CSRF/CORS không nên tiết lộ cookie value, token expected/received hoặc danh sách origin nội bộ. Có thể trả "Request không được chấp nhận" và log mã policy/error category nội bộ. CORS browser errors đôi khi không cung cấp chi tiết cho JavaScript; dùng server logs và request ID để điều tra.

## 9. Xử lý lỗi ở backend: ví dụ Express

Một error middleware tập trung giúp chuẩn hóa response. Ví dụ dưới đây minh họa ánh xạ một số lỗi đã biết và dùng thông điệp public cố định cho lỗi không dự kiến.

~~~js
function mapPublicError(err) {
  if (err?.code === "VALIDATION_FAILED") {
    return {
      status: 422,
      type: "https://api.example.test/problems/validation",
      title: "Dữ liệu không hợp lệ",
      detail: "Hãy kiểm tra các trường được đánh dấu.",
      errorCode: "VALIDATION_FAILED"
    };
  }

  if (err?.code === "NOT_FOUND") {
    return {
      status: 404,
      type: "https://api.example.test/problems/not-found",
      title: "Không tìm thấy tài nguyên",
      detail: "Tài nguyên không tồn tại hoặc bạn không thể truy cập.",
      errorCode: "NOT_FOUND"
    };
  }

  if (err?.code === "RATE_LIMITED") {
    return {
      status: 429,
      type: "https://api.example.test/problems/rate-limit",
      title: "Quá nhiều yêu cầu",
      detail: "Hãy chờ một lúc rồi thử lại.",
      errorCode: "RATE_LIMITED"
    };
  }

  return {
    status: 500,
    type: "https://api.example.test/problems/internal",
    title: "Không thể hoàn tất yêu cầu",
    detail: "Đã xảy ra lỗi. Hãy thử lại sau.",
    errorCode: "UNEXPECTED_ERROR"
  };
}

app.use((err, req, res, next) => {
  if (res.headersSent) {
    return next(err);
  }

  const problem = mapPublicError(err);
  const requestId = req.requestId;

  logger.error({
    event: "http.request.failed",
    requestId,
    method: req.method,
    route: req.route?.path ?? "unmatched",
    status: problem.status,
    errorCode: problem.errorCode,
    errorType: err?.constructor?.name ?? "UnknownError"
  });

  res
    .status(problem.status)
    .type("application/problem+json")
    .set("Cache-Control", "no-store")
    .set("X-Content-Type-Options", "nosniff")
    .json({
      type: problem.type,
      title: problem.title,
      status: problem.status,
      detail: problem.detail,
      errorCode: problem.errorCode,
      requestId
    });
});
~~~

Ví dụ chỉ log metadata đã chọn; hệ thống thực tế có thể gửi stack đã scrub tới error tracker riêng với quyền hạn phù hợp. Không thêm `err` hoặc `err.message` vào log payload nếu chưa lọc.

### 9.1 Thứ tự middleware

- Request ID middleware chạy đủ sớm để request lỗi parser cũng có ID.
- Authentication/authorization middleware ánh xạ lỗi theo contract.
- Body parser có giới hạn kích thước và error handler cho malformed JSON.
- Route handler không tự trả stack trace.
- Error middleware cuối cùng chuẩn hóa response.
- Error từ background job/queue phải có cùng nguyên tắc, dù không có HTTP response.

### 9.2 Không nuốt lỗi

Không viết catch rỗng hoặc trả success giả khi dependency thất bại. Ghi nhận event nội bộ đã lọc, chuyển lỗi tới error handler phù hợp và trả status đúng. Nếu đã gửi response headers/body, không cố gửi thêm JSON error response; đóng/ủy quyền xử lý theo framework.

### 9.3 Timeout và lỗi dependency

Không trả raw error từ database, payment provider hoặc identity provider. Map lỗi upstream thành 502/503/504 hoặc mã nghiệp vụ phù hợp. Giữ provider response, internal URL và credential trong log được kiểm soát, sau khi scrub.

## 10. Cấu hình production và development

Development có thể hiển thị stack trace cho lập trình viên, nhưng cấu hình đó không được vô tình bật trong production.

### 10.1 Tắt debug page public

Kiểm tra các cấu hình tương ứng framework:

- Node/Express: không dùng development error handler trong production.
- Django: `DEBUG = False` trong production.
- ASP.NET Core: không bật Developer Exception Page cho public production traffic.
- Spring Boot: không expose stacktrace/message/binding errors nhạy cảm trong error response.
- Reverse proxy/API gateway: không trả default error page chứa upstream hostname, path hoặc version.

Tên cấu hình cụ thể phụ thuộc phiên bản. Xác minh bằng request thực tế tới endpoint lỗi trong production-like environment.

### 10.2 Cấu hình error detail

Không bật tùy chọn include exception message, stack trace, binding errors hoặc environment variables trong response public. Nếu framework cung cấp `include-message` hay `include-stacktrace`, đặt theo hướng không tiết lộ trong production và test lại sau nâng cấp.

### 10.3 Phân tách môi trường

- Dùng dữ liệu và credential riêng giữa dev/staging/production.
- Không đưa secret production vào staging log.
- Không để debug endpoint public.
- Giới hạn truy cập admin/diagnostic endpoint.
- Không expose health detail hoặc dependency topology cho mọi client.
- Đảm bảo CDN/gateway không cache error response user-specific.

### 10.4 Security headers cho error response

Error response cũng cần policy phù hợp. Với API nhạy cảm, cân nhắc `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` và media type chính xác. Nếu error page là HTML, áp dụng CSP/frame policy như các trang khác. Không giả định response lỗi không cần security headers.

## 11. Frontend: hiển thị lỗi mà không làm lộ thêm dữ liệu

Frontend thường nhận response lỗi rồi hiển thị toast, dialog hoặc inline validation. Không render raw response hoặc exception object trực tiếp vào DOM.

### 11.1 Hiển thị thông điệp public bằng text

Ví dụ:

~~~js
async function submitProfile(payload) {
  const response = await fetch("/api/profile", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/problem+json, application/json"
    },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });

  if (response.ok) {
    return response.json();
  }

  const contentType = response.headers.get("content-type") || "";
  let problem = null;

  if (contentType.includes("application/problem+json")) {
    problem = await response.json().catch(() => null);
  }

  const message =
    typeof problem?.detail === "string"
      ? problem.detail
      : "Không thể hoàn tất yêu cầu.";

  document.querySelector("#error-message").textContent = message;

  const requestId = problem?.requestId;
  if (typeof requestId === "string") {
    console.info("Support reference:", requestId);
  }

  throw new Error(problem?.errorCode || "REQUEST_FAILED");
}
~~~

Trong production, không log toàn bộ `problem` hoặc payload. `textContent` giúp hiển thị text mà không diễn giải message thành HTML. Client nên kiểm tra kiểu dữ liệu và giới hạn độ dài trước khi hiển thị.

### 11.2 Không render raw HTML từ lỗi

Không làm:

~~~js
errorContainer.innerHTML = responseText;
~~~

Nếu response chứa HTML hoặc nội dung attacker kiểm soát, có thể tạo DOM XSS. Dùng textContent hoặc component binding có escaping; nếu cần rich text, dùng allowlist sanitizer được duy trì.

### 11.3 Không đưa error detail vào URL

Không redirect tới:

~~~text
/error?message=database-password-or-token
~~~

URL có thể vào history, log, analytics và Referer. Dùng error code/request ID ngắn, không nhạy cảm, hoặc state trong memory phù hợp.

### 11.4 Không để telemetry frontend thu thập response thô

Error monitoring ở browser không nên tự động gửi toàn bộ request headers, response body, form values hoặc DOM snapshot nếu chưa có redaction và consent/policy phù hợp. Chọn event và field cụ thể, scrub trước khi gửi.

## 12. Error reporting, monitoring và alerting

Một response public an toàn không có nghĩa đội vận hành mất khả năng điều tra. Tách hai luồng:

- **Client response:** status, public error code, thông điệp an toàn, request ID.
- **Internal telemetry:** exception category, stack đã scrub, trace, dependency timing, release version và context tối thiểu cần thiết.

### 12.1 Group lỗi bằng fingerprint an toàn

Error tracker có thể nhóm theo exception type, normalized stack frame hoặc application error code. Tránh fingerprint chứa user input, token hoặc URL query. Kiểm tra các tag tự động như username, email, request URL và database statement.

### 12.2 Alert theo hành vi, không theo secret

Alert nên dựa trên:

- Tỷ lệ 5xx theo route/service.
- Tăng đột biến 401/403/429.
- Dependency timeout/error rate.
- Error budget và latency.
- Release/build version.
- Trace/request ID để điều tra.

Không gửi token, password hoặc full request body qua Slack/email notification. Alert chỉ nên có summary và link tới dashboard có xác thực.

### 12.3 Phân quyền và retention

Log và error tracker có thể chứa stack path, tenant ID và dữ liệu vận hành. Áp dụng least privilege, audit access, retention ngắn phù hợp, encryption và quy trình xóa/export. Không cấp quyền truy cập log production rộng chỉ để thuận tiện debug.

### 12.4 Error spike có thể là tín hiệu tấn công

Một loạt malformed JSON, parser errors, 401/403, 404 enumeration hoặc 5xx có thể phản ánh bug, deploy lỗi hoặc hoạt động dò quét. Giữ thông tin cần thiết để phân biệt, nhưng tránh ghi raw payload attacker gửi vào log không giới hạn. Rate limit và sampling có kiểm soát giúp tránh log flooding.

## 13. Kiểm thử error disclosure

Kiểm thử phải xác nhận cả response và log. Chỉ nhìn status code chưa đủ.

### 13.1 Test matrix

| Tình huống | Kỳ vọng public | Điều cần xác nhận nội bộ |
|---|---|---|
| JSON malformed | 400, thông điệp chung | Error category và request ID |
| Field validation fail | 422, field/code allowlist | Không log raw secret input |
| Chưa đăng nhập | 401, message ổn định | Auth failure event đã lọc |
| Không đủ quyền | 403 hoặc 404 theo policy | Authorization decision |
| Account không tồn tại | Message không xác nhận account | Không tạo timing/status khác biệt rõ |
| Unique constraint | 409 hoặc 422 theo contract | Không lộ SQL/index name |
| Database unavailable | 503/500 theo vai trò | Dependency health, scrubbed exception |
| Upstream timeout | 504 hoặc 503 | Trace và upstream category |
| Unhandled exception | 500 generic | Stack chỉ ở sink nội bộ |
| Rate limit | 429, Retry-After nếu có | Counter/rule nội bộ không public |

### 13.2 Kiểm tra response body

Dùng curl trên môi trường test:

~~~bash
curl -i https://api.example.test/api/debug-error
~~~

Xác nhận response không chứa các chuỗi như `at /srv/`, `SELECT * FROM`, hostname nội bộ, connection string, stack trace hoặc secret marker giả lập.

Không gọi endpoint phá hoại trên production. Tạo route test chỉ trong lab hoặc dùng lỗi validation không gây side effect.

### 13.3 Kiểm tra log

Dùng marker giả:

~~~text
TEST_SECRET_DO_NOT_USE
TEST_PASSWORD_DO_NOT_USE
person@example.test
~~~

Gửi marker trong field được kiểm soát, sau đó kiểm tra log/telemetry đã scrub đúng chưa. Đừng dùng credential thật làm marker. Xác nhận request ID liên kết được event mà không cần ghi body.

### 13.4 Kiểm tra account enumeration

Với luồng login/reset test, so sánh:

- Status code.
- Response schema và message.
- Redirect.
- Kích thước response.
- Thời gian xử lý trong nhiều lần chạy.

Mục tiêu là tránh khác biệt không cần thiết giúp suy đoán account tồn tại. Đánh giá timing thống kê trong môi trường test; một phép đo đơn lẻ không chứng minh an toàn.

### 13.5 Kiểm tra frontend rendering

Dùng message test có chuỗi HTML giả lập như `<img src=x onerror=alert(1)>`. Xác nhận UI hiển thị text và không tạo element hoặc thực thi script. Không cần dùng payload độc hại trên tài khoản production.

## 14. Lỗi triển khai thường gặp

### 14.1 Trả err.message trực tiếp

Message có thể chứa input hoặc chi tiết dependency. Map lỗi sang public code/message đã duyệt.

### 14.2 Trả stack trace để hỗ trợ người dùng

Stack trace là dữ liệu nội bộ. Trả request ID để support tìm log thay vì trả stack.

### 14.3 Dùng cùng một error handler cho dev và production

Development page có thể hiển thị source path và environment. Cấu hình production riêng và test response lỗi sau deploy.

### 14.4 Ghi toàn bộ request vào log khi có lỗi

Request có thể chứa password, token và PII. Dùng allowlist, redaction và request ID.

### 14.5 Log raw exception từ upstream

Upstream error có thể chứa URL, credential hoặc response body. Chuẩn hóa error category và scrub trước khi ghi.

### 14.6 Trả lỗi khác nhau cho account tồn tại và không tồn tại

Điều này hỗ trợ account enumeration. Dùng message/status/flow nhất quán theo threat model và rate limit.

### 14.7 Dùng 200 cho mọi response

Client và monitoring không nhận biết lỗi đúng. Chọn status code HTTP phù hợp.

### 14.8 Trả error object cho frontend rồi render bằng innerHTML

Response có thể chứa HTML hoặc nội dung không tin cậy. Validate schema và render bằng text.

### 14.9 Request ID do client kiểm soát

Attacker có thể gây collision hoặc log injection. Tạo ID server-side; chỉ giữ client ID đã validate trong field riêng.

### 14.10 Error tracker thu thập quá nhiều context

DOM, form, headers và response có thể chứa secret. Tắt capture mặc định không cần thiết, cấu hình scrub và kiểm tra artifact gửi đi.

### 14.11 Cache error response cá nhân

Proxy/CDN có thể phục vụ lỗi user-specific cho request khác. Dùng cache policy phù hợp, thường no-store cho response nhạy cảm.

### 14.12 Health endpoint tiết lộ topology

Health check public không nên trả database host, queue name, dependency version hoặc config. Tách liveness/readiness public tối thiểu khỏi diagnostic endpoint nội bộ đã xác thực.

## 15. Checklist review trước production

- [ ] Không trả exception object, stack trace hoặc raw exception message.
- [ ] Error response có status HTTP đúng ngữ nghĩa.
- [ ] Public error code ổn định và không chứa chi tiết nội bộ.
- [ ] Message được duyệt, dễ hiểu và không echo raw input.
- [ ] Dùng application/problem+json nếu API contract chọn RFC 9457.
- [ ] Field validation chỉ dùng schema public và thông điệp allowlist.
- [ ] Không lộ SQL, schema, connection string, hostname, IP hoặc filesystem path.
- [ ] Không lộ password, cookie, token, API key, private key hoặc signed URL.
- [ ] Không lộ PII trong message hoặc request dump.
- [ ] Request ID được tạo/validate tại trust boundary và không mang secret.
- [ ] Client có thể cung cấp request ID cho support mà không tra cứu log tùy ý.
- [ ] Structured logs dùng allowlist và redaction.
- [ ] Stack trace chỉ tới sink nội bộ có quyền hạn và retention phù hợp.
- [ ] Log không thể bị giả mạo bằng newline/control character.
- [ ] Authentication/reset flow hạn chế account enumeration.
- [ ] Backend map dependency errors sang response public an toàn.
- [ ] Frontend hiển thị message bằng text, không innerHTML.
- [ ] Frontend telemetry không gửi raw body/header/DOM ngoài policy.
- [ ] Debug page và verbose error settings đã tắt ở production.
- [ ] Error response có security/cache headers phù hợp.
- [ ] Health/diagnostic endpoint không public topology.
- [ ] Có test cho 400/401/403/404/409/413/415/422/429/5xx.
- [ ] Có test marker để kiểm tra response và log không lộ secret.
- [ ] Có quy trình revoke/rotate và incident response khi phát hiện lộ.

## 16. Bài thực hành

Thực hiện trên ứng dụng lab hoặc staging với credential giả. Không tạo endpoint debug công khai trong production.

### Bài 1: So sánh error response

Tạo một endpoint test cố ý phát sinh lỗi. So sánh response development và production. Xác nhận production chỉ trả Problem Details generic, còn stack được giữ trong log nội bộ đã kiểm soát.

### Bài 2: Error mapping

Tạo các lỗi validation, not found, conflict và rate limit. Map chúng sang 422, 404, 409 và 429 với error code ổn định. Xác nhận exception không được serialize trực tiếp.

### Bài 3: Request ID

Tạo request ID bằng randomUUID ở middleware. Gửi request lỗi, lấy ID từ response header/body và tìm event tương ứng trong log. Thử gửi header X-Request-ID giả để xác nhận server không tin nó như internal ID.

### Bài 4: Redaction

Gửi marker giả TEST_SECRET_DO_NOT_USE trong header và body lab. Kiểm tra logger không ghi giá trị, kể cả trong nested field hoặc exception context.

### Bài 5: Account enumeration

Tạo luồng reset mật khẩu giả. So sánh response cho account có và không có trong fixture. Giữ status, message và redirect nhất quán; kiểm tra rate limit.

### Bài 6: Frontend error rendering

Trả detail test chứa chuỗi HTML. Xác nhận frontend dùng textContent và chuỗi chỉ hiển thị dưới dạng văn bản.

### Bài 7: Dependency failure

Giả lập database hoặc upstream timeout trong môi trường test. Server trả 503/504 phù hợp, không trả connection string, hostname hoặc raw provider response.

### Bài 8: Error tracker review

Gửi một lỗi test với dữ liệu giả, kiểm tra event sau khi scrub. Xác nhận headers, URL query, form values, stack và breadcrumbs không giữ marker nhạy cảm.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao không trả stack trace trong production response?**

Vì stack có thể tiết lộ source path, framework, dependency, cấu trúc hệ thống và dữ liệu trong exception.

**2. Client cần nhận những gì khi có lỗi 500?**

HTTP status, public error code, thông điệp chung và request ID để liên hệ hỗ trợ.

**3. application/problem+json dùng để làm gì?**

Định dạng response Problem Details theo RFC 9457, cung cấp cấu trúc thống nhất cho lỗi HTTP.

**4. Vì sao không nên trả err.message trực tiếp?**

Message có thể chứa input, SQL, hostname, secret hoặc thông tin dependency chưa được duyệt để public.

**5. Request ID có phải credential không?**

Không. Nó là mã tham chiếu để tìm event nội bộ và không được dùng để cấp quyền truy cập log.

**6. Vì sao cần tạo request ID ở server?**

Để tránh client giả mạo/collision và giúp correlation đáng tin cậy qua response và log.

**7. Có nên log toàn bộ request khi xảy ra lỗi không?**

Không. Request có thể chứa password, cookie, token và PII; nên log allowlist và redact.

**8. Làm sao hạn chế account enumeration?**

Dùng response và flow nhất quán cho account tồn tại/không tồn tại, kết hợp rate limit và kiểm soát timing.

**9. Vì sao frontend không nên render error bằng innerHTML?**

Error content có thể chứa HTML hoặc input attacker kiểm soát, dẫn đến DOM XSS. Dùng textContent hoặc binding có escaping.

**10. Khi phát hiện log/error response chứa secret, bước nào cần ưu tiên?**

Xác định loại credential và phạm vi lộ, revoke/rotate hoặc vô hiệu hóa credential, kiểm tra audit và xử lý các bản sao theo incident policy.

## Ghi nhớ

Error response là một phần của security boundary. Client chỉ nhận thông tin đã được duyệt: status, error code, thông điệp an toàn và request ID. Stack trace, exception, SQL, hostname, path, secret và PII phải được giữ ngoài public response; log nội bộ cũng cần allowlist, redaction, phân quyền và retention. Hãy kiểm thử cả response lẫn telemetry để lỗi không trở thành kênh tiết lộ cấu trúc hoặc dữ liệu của hệ thống.

## Tài liệu tham khảo

- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [OWASP: Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [MDN: HTTP response status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status)
- [Express: Error handling](https://expressjs.com/en/guide/error-handling.html)
- [W3C: Trace Context](https://www.w3.org/TR/trace-context/)
