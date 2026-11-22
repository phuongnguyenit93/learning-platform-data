# Không lộ stack trace, path, SQL hoặc secret

## 1. Vì sao thông báo lỗi là một bề mặt tấn công?

API error response là dữ liệu đi ra ngoài trust boundary. Khi xử lý lỗi, framework, driver database, filesystem hoặc thư viện HTTP có thể tạo thông tin chi tiết hơn nhiều so với điều client cần biết.

Nếu trả nguyên exception message hoặc stack trace, response có thể tiết lộ:

- Tên package, class, framework, phiên bản thư viện và cấu trúc source code.
- Đường dẫn tuyệt đối, tên user hệ điều hành, thư mục deploy, mount point hoặc tên file nội bộ.
- SQL statement, table/column, constraint, schema, database vendor và dữ liệu truy vấn.
- Hostname, IP private, port, topology service, bucket hoặc endpoint nội bộ.
- Access token, API key, cookie, password, connection string, signed URL hoặc secret nằm trong exception.
- Dữ liệu cá nhân, payload, identifier hoặc thông tin tenant của người khác.

Thông tin này giúp attacker fingerprint công nghệ, điều chỉnh payload, dò cấu trúc hệ thống và tìm đường khai thác sâu hơn. Một stack trace có thể biến lỗi validation bình thường thành bản đồ source code; một lỗi SQL có thể tiết lộ tên bảng và cách query; một exception từ HTTP client có thể in nguyên URL chứa token.

Mục tiêu của xử lý lỗi an toàn là cung cấp cho client một kết quả ổn định, đủ để sửa request hoặc quyết định retry, đồng thời giữ chẩn đoán kỹ thuật trong hệ thống log/trace có kiểm soát. **Không đưa exception thô, dữ liệu nội bộ hoặc secret vào response công khai.**

## 2. Phân loại thông tin trong lỗi

Trước khi thiết kế error contract, phân loại dữ liệu có thể xuất hiện:

| Thông tin | Ví dụ | Có nên trả cho client? |
|---|---|---|
| Error code ổn định | INVALID_REQUEST, ORDER_CONFLICT | Có |
| HTTP status | 400, 401, 403, 404, 409, 429, 500 | Có |
| Hướng dẫn sửa input an toàn | Field items phải có ít nhất một phần tử | Có, nếu không tiết lộ dữ liệu |
| Request/correlation ID | ID ngẫu nhiên để tra log | Có |
| Tên exception/class | NullPointerException, SQLException | Không |
| Stack trace | File, method, line number | Không |
| SQL và DB metadata | SELECT..., tên bảng, constraint, SQLSTATE | Không |
| Filesystem path | C:\app\secrets\..., /srv/private/... | Không |
| Internal host/port | db-prod-03:5432 | Không |
| Credential/secret | Bearer token, API key, password | Không |
| Raw request/response body | Payload đầy đủ, dữ liệu khách hàng | Không trả nguyên văn |
| Internal policy detail | Tên role, rule, ACL hoặc allowlist | Thông thường không |

Một số dữ liệu có thể được trả trong ngữ cảnh quản trị đã xác thực, nhưng vẫn cần một contract riêng, quyền truy cập rõ và redaction. Không dùng một error handler chung để gửi cùng lượng thông tin cho public client, internal service và operator.

## 3. Nguyên tắc thiết kế error response

Một error response an toàn nên có các thuộc tính:

1. **Ổn định:** client dựa vào code và status, không dựa vào exception message.
2. **Tối thiểu:** chỉ chứa thông tin cần để xử lý lỗi.
3. **Không nhạy cảm:** không có stack, SQL, path, host nội bộ hoặc secret.
4. **Có thể truy vết:** có request ID/correlation ID để đội vận hành tìm log.
5. **Nhất quán:** cùng loại lỗi có cùng cấu trúc trên các endpoint.
6. **Có semantics HTTP đúng:** status và header phản ánh lỗi thực tế.
7. **Có giới hạn:** danh sách lỗi validation, message length và số field không thể bị lợi dụng để tạo response quá lớn.

Không dùng nội dung exception làm API contract. Exception là chi tiết triển khai và có thể thay đổi theo framework, driver, database hoặc phiên bản thư viện. API contract nên định nghĩa error code do ứng dụng sở hữu.

## 4. Cấu trúc response lỗi

Có thể dùng Problem Details theo RFC 9457 hoặc một envelope riêng được tài liệu hóa. Problem Details định nghĩa các trường phổ biến:

- type: URI định danh loại vấn đề.
- title: mô tả ngắn, ổn định cho loại vấn đề.
- status: HTTP status.
- detail: giải thích an toàn cho lần xảy ra cụ thể.
- instance: định danh occurrence.

Ứng dụng có thể thêm extension như code, traceId hoặc errors. Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường không đáp ứng yêu cầu.",
  "instance": "urn:request:01J8Q6F3P2",
  "code": "VALIDATION_FAILED",
  "traceId": "01J8Q6F3P2",
  "errors": [
    {
      "field": "items",
      "code": "MIN_ITEMS",
      "message": "Cần có ít nhất một phần tử."
    }
  ]
}
~~~

Đây là cấu trúc minh họa. Nếu API đã có envelope chuẩn thì tiếp tục dùng contract đó; không cần thay định dạng chỉ để theo ví dụ. Quan trọng là field có ý nghĩa rõ và không mang dữ liệu nội bộ.

Không đưa raw URL đầy đủ vào instance nếu query có thể chứa token hoặc dữ liệu cá nhân. Có thể dùng URI occurrence opaque như urn:request:<id> hoặc path đã loại query và thông tin nhạy cảm.

## 5. Mapping exception sang HTTP status

Không trả status 500 cho mọi lỗi, nhưng cũng không biến mọi exception thành 400. Hãy map theo nguyên nhân đã biết:

| Tình huống | Status thường dùng | Response an toàn |
|---|---:|---|
| Request syntax/framing sai | 400 | INVALID_REQUEST |
| Thiếu hoặc credential không hợp lệ | 401 | UNAUTHENTICATED và WWW-Authenticate phù hợp |
| Đã xác thực nhưng không có quyền | 403 | FORBIDDEN |
| Resource không tồn tại | 404 | RESOURCE_NOT_FOUND |
| Cố ý che giấu resource không được truy cập | 404 | Cùng response với trường hợp không tồn tại |
| Xung đột trạng thái/unique business rule | 409 | RESOURCE_CONFLICT |
| Body quá lớn | 413 | REQUEST_TOO_LARGE |
| Media type không hỗ trợ | 415 | UNSUPPORTED_MEDIA_TYPE |
| Nội dung đúng cú pháp nhưng sai semantic | 422 nếu contract chọn dùng | VALIDATION_FAILED |
| Rate/quota bị vượt | 429 | RATE_LIMITED và Retry-After nếu biết |
| Lỗi bất ngờ trong application | 500 | INTERNAL_ERROR |
| Upstream trả lời không hợp lệ | 502 | UPSTREAM_FAILURE |
| Dịch vụ tạm không sẵn sàng | 503 | SERVICE_UNAVAILABLE, Retry-After nếu có |
| Upstream timeout | 504 | UPSTREAM_TIMEOUT |

Status phải phản ánh semantics của endpoint và giao thức đang dùng. Ví dụ 422 không bắt buộc cho mọi API; một số contract dùng 400 cho validation. Hãy chọn một quy tắc nhất quán và ghi trong tài liệu.

### 5.1 401 và 403

401 dành cho request thiếu hoặc có credential không hợp lệ. Với HTTP authentication scheme, response cần có WWW-Authenticate challenge phù hợp. Không trả lý do chi tiết như token sai chữ ký, user bị khóa hay account không tồn tại nếu điều đó tạo user enumeration.

403 dành cho principal đã xác thực nhưng không được phép thực hiện hành động. Không tiết lộ tên role, policy rule hoặc object owner nếu client không có quyền xem thông tin đó.

### 5.2 404 để che giấu resource

Trong một số API, trả 404 cho cả resource không tồn tại và resource mà caller không được phép biết là có tồn tại giúp giảm enumeration. Chỉ áp dụng khi phù hợp threat model và cần giữ response/status/timing tương đối nhất quán. Không biến mọi lỗi authorization thành 404 vì điều đó làm khó client và che khuất lỗi policy.

### 5.3 429 và lỗi tạm thời

429 có thể kèm Retry-After nếu hệ thống biết thời điểm retry phù hợp. Không trả quota nội bộ, thuật toán rate limiter hoặc ngưỡng của tenant khác. 503/504 chỉ nên được retry theo contract và tính idempotent; response không được chứa hostname hoặc stack của upstream.

## 6. Không trả stack trace hoặc exception message

Các response sau là không an toàn:

~~~json
{
  "error": "java.lang.NullPointerException at com.company.payment.PaymentService.java:184",
  "stackTrace": "at org.springframework..."
}
~~~

~~~json
{
  "message": "Connection refused to db-prod-03.internal:5432"
}
~~~

~~~json
{
  "error": "SQLSyntaxErrorException: select * from customer where..."
}
~~~

Response nên dùng thông báo trung tính:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Đã xảy ra lỗi khi xử lý yêu cầu.",
  "traceId": "01J8Q6F3P2"
}
~~~

Không gọi exception.getMessage() để tạo message cho client. Message của thư viện có thể chứa input attacker gửi, SQL, URL, path hoặc secret. Cũng không serialize toàn bộ exception object; một số framework tự xuất stack, cause chain, suppressed exception hoặc property nội bộ.

## 7. Không lộ filesystem path hoặc thông tin triển khai

Path tuyệt đối có thể tiết lộ:

- Tên user hoặc account chạy process.
- Cấu trúc thư mục deploy và source tree.
- Tên ứng dụng, module, container image hoặc mount.
- Vị trí file cấu hình, key, log, upload và backup.
- Hệ điều hành hoặc layout của runtime.

Ví dụ không an toàn:

~~~text
FileNotFoundException:
/srv/apps/payment-service/releases/2026-11/config/prod-secrets.yml
~~~

Client chỉ cần biết tài nguyên/file không được tìm thấy hoặc thao tác thất bại. Có thể trả code FILE_NOT_FOUND hoặc RESOURCE_NOT_AVAILABLE theo contract. Nếu tên file do user cung cấp và được phép hiển thị, trả tên đã validate/redact, không trả path thực tế.

Không đưa stack trace có source path hoặc line number vào HTML error page, JSON response, response header hay redirect. Kiểm tra cả trang lỗi do reverse proxy, ingress, load balancer và CDN sinh ra; ứng dụng có thể an toàn nhưng edge vẫn để lộ server banner hoặc internal upstream.

## 8. Không lộ SQL, database metadata hoặc dữ liệu truy vấn

Database exception có thể chứa:

- SQL statement hoặc fragment query.
- Table, column, index và constraint name.
- SQLSTATE, vendor error code và database version.
- Hostname, database name, schema hoặc port.
- Giá trị bind parameter hoặc dữ liệu đầu vào.
- Thông tin constraint cho biết một email/username đã tồn tại.

Không trả những chi tiết này cho client. Ví dụ lỗi unique constraint nên được chuyển thành code nghiệp vụ như EMAIL_ALREADY_REGISTERED hoặc RESOURCE_CONFLICT nếu có thể xác định an toàn; không trả tên constraint hoặc SQL.

Không dùng cách xử lý như sau:

~~~java
catch (SQLException ex) {
    return ResponseEntity.badRequest().body(ex.getMessage());
}
~~~

Database error không mặc định là lỗi request. Connection pool cạn, database unavailable hoặc SQL bug thường là lỗi server/dependency; map sai thành 400 có thể che giấu sự cố và khiến client không biết cách retry.

Chỉ map constraint đã biết sang business error. Các lỗi database không nhận diện phải đi qua generic internal error handler và log nội bộ có kiểm soát.

## 9. Không lộ secret trong error path

Secret có thể xuất hiện trong exception dù ứng dụng không chủ ý trả chúng:

- URL có userinfo hoặc query token.
- Authorization header, cookie hoặc API key.
- Connection string có username/password.
- Signed URL có signature và expiry.
- OAuth authorization code, refresh token hoặc reset token.
- Request body chứa password, payment data hoặc private key.
- Cloud SDK exception chứa credential/provider metadata.

Redaction phải được thực hiện ở nhiều lớp:

1. Response mapper không serialize exception/context thô.
2. Logger filter che header và field nhạy cảm.
3. HTTP client không ghi full URL nếu query có secret.
4. Tracing instrumentation không capture Authorization/Cookie/body mặc định.
5. Error reporting/APM áp dụng scrub trước khi gửi dữ liệu ra ngoài.
6. Log storage có access control, encryption và retention.

Không chỉ thay chuỗi token đã biết. Dùng allowlist field được phép log hoặc schema-based redaction cho Authorization, Cookie, Set-Cookie, password, secret, token, client_secret, api_key và các field nhạy cảm của domain. Tên field có thể khác nhau giữa API.

Nếu exception message có thể chứa secret, tránh log message nguyên văn. Ghi exception class, error category, correlation ID và stack trace vào sink được kiểm soát; nếu cần stack trace đầy đủ, bảo đảm log pipeline redaction có hiệu lực trước khi dữ liệu rời process.

## 10. Phân biệt client response và internal diagnostic

Nên có hai mô hình riêng:

| Client-facing error | Internal diagnostic |
|---|---|
| Stable error code | Exception class và cause chain |
| HTTP status | Stack trace có kiểm soát |
| Safe message | SQLSTATE/vendor code đã phân loại |
| Field-level validation code | Internal service/host/operation |
| Opaque request ID | Trace/span ID và deployment version |
| Không có secret | Dữ liệu đã redact, không lưu secret thô |
| Không phụ thuộc framework | Có thể chứa chi tiết framework phục vụ điều tra |

Không dùng cùng một object exception làm response DTO và log payload. Tạo một error response model riêng, chỉ chứa field được phép công khai. Internal diagnostics có thể phong phú hơn nhưng phải tuân thủ chính sách bảo vệ log và quyền truy cập.

## 11. Xử lý lỗi tập trung trong Java/Spring

Với Spring MVC, có thể dùng @RestControllerAdvice để chuẩn hóa lỗi. Ví dụ dưới đây minh họa cấu trúc:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> handleConflict(
            OrderConflictException ex,
            HttpServletRequest request) {

        String requestId = requestIdOf(request);
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Trạng thái tài nguyên không cho phép thao tác này."
        );
        problem.setType(URI.create(
                "https://api.example.com/problems/resource-conflict"
        ));
        problem.setTitle("Xung đột tài nguyên");
        problem.setProperty("code", "RESOURCE_CONFLICT");
        problem.setProperty("traceId", requestId);
        problem.setInstance(URI.create("urn:request:" + requestId));

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .body(problem);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(
            Exception ex,
            HttpServletRequest request) {

        String requestId = requestIdOf(request);
        logInternalFailure(requestId, ex);

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Đã xảy ra lỗi khi xử lý yêu cầu."
        );
        problem.setType(URI.create(
                "https://api.example.com/problems/internal-error"
        ));
        problem.setTitle("Lỗi nội bộ");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("traceId", requestId);
        problem.setInstance(URI.create("urn:request:" + requestId));

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .body(problem);
    }
}
~~~

Đây là ví dụ khung; import, logger, request ID filter và cách xử lý validation cần được triển khai theo phiên bản Spring đang dùng. Điểm cần giữ:

- Response được tạo từ code/title/detail do ứng dụng kiểm soát.
- Không trả ex.getMessage(), ex.toString() hoặc stack trace.
- Request ID được tạo/validate tại middleware tin cậy.
- Log nội bộ được redacted và phân quyền.
- Error response có Cache-Control phù hợp.

Không bắt Exception quá sớm ở controller rồi tự trả 200 với object chứa lỗi. Hãy để status HTTP đúng với outcome và có một exception mapping nhất quán ở biên API.

## 12. Xử lý lỗi validation mà không phản chiếu input nguy hiểm

Validation error nên chỉ ra field và rule bị vi phạm:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Địa chỉ email không đúng định dạng."
    },
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "Số lượng phải nằm trong giới hạn cho phép."
    }
  ],
  "traceId": "01J8Q6F3P2"
}
~~~

Không trả rejectedValue mặc định từ binding error. Giá trị có thể là password, token, email cá nhân, HTML/script dài hoặc payload được chế tạo để gây log/response injection.

Các quy tắc:

- Chỉ trả tên field thuộc public API schema, không trả tên property nội bộ.
- Dùng validation code ổn định, không dùng tên class validator làm contract.
- Giới hạn số lỗi trả về và độ dài message.
- Không echo raw input hoặc toàn bộ JSON path nếu có thể chứa dữ liệu nhạy cảm.
- Không trả expected secret, regex nội bộ hoặc policy threshold nhạy cảm.
- Không phân biệt quá chi tiết lỗi đăng nhập để tránh user enumeration.

Với nested field, có thể trả đường dẫn JSON đã chuẩn hóa như items[0].quantity. Đảm bảo path không lấy từ expression/property nội bộ do attacker điều khiển.

## 13. Không lộ thông tin trong lỗi authentication và authorization

Các response như user không tồn tại, password đúng nhưng account bị khóa, token ký bởi key không hợp lệ hoặc tenant có 3 admin có thể giúp attacker dò danh tính và quyền.

Nên dùng thông báo tổng quát theo contract:

- Login thất bại: thông báo credential không hợp lệ, không xác nhận user có tồn tại.
- Token không hợp lệ: trả 401 với challenge phù hợp, không nói key ID nội bộ hoặc thuật toán ký.
- Không đủ quyền: trả 403 hoặc 404 theo chính sách resource concealment.
- Tenant không hợp lệ: không tiết lộ tenant có tồn tại hay không nếu caller không được biết.
- Account bị khóa: chỉ tiết lộ qua kênh hỗ trợ hoặc luồng xác minh phù hợp.

Không tiết lộ role name, group membership, policy expression hoặc quyền của user khác. Security audit vẫn cần ghi lý do chính xác ở phía server, nhưng response công khai chỉ chứa code đã được phê duyệt.

## 14. Lỗi từ upstream và API Gateway

Gateway có thể nhận lỗi từ service nội bộ, reverse proxy, DNS, TLS hoặc dependency. Không forward nguyên response body của upstream ra public client vì nó có thể chứa stack trace, hostname, framework banner hoặc thông tin nhạy cảm.

Gateway nên:

1. Phân loại lỗi upstream thành nhóm public contract đã định nghĩa.
2. Gán status phù hợp như 502, 503 hoặc 504.
3. Tạo error code và request ID ở biên.
4. Lưu upstream status/diagnostic trong log nội bộ đã redact.
5. Không forward Server, Via, internal trace header hoặc debug header nếu không cần.
6. Giữ nguyên Retry-After chỉ khi đã xác minh semantics và không làm lộ policy nội bộ.
7. Không biến lỗi authentication/authorization của upstream thành 500 một cách tùy tiện.

Nếu service trả Problem Details, gateway chỉ nên forward những field thuộc public contract và đã được kiểm tra. Không tin response body từ upstream chưa xác thực hoặc service ngoài trust boundary.

## 15. Lỗi từ filesystem, object storage và file processing

Các exception khi upload/download/export có thể lộ path hoặc storage key:

- FileNotFoundException và NoSuchFileException.
- AccessDeniedException.
- Object storage SDK error.
- Archive extraction hoặc image/document parser exception.
- Temporary directory và container mount.

Client chỉ cần biết file không tồn tại, không được phép truy cập, định dạng không hỗ trợ hoặc thao tác tạm thời thất bại. Không trả bucket name, object key nội bộ, filesystem path, mount path, container ID hoặc tên user OS.

Nếu file ID không thuộc user/tenant, dùng cùng cách phản hồi như policy resource concealment đã chọn. Không trả file tồn tại nhưng nằm trong path nội bộ của tenant khác vì điều đó tiết lộ sự hiện diện và vị trí dữ liệu.

Với lỗi archive/parser, không trả stack hoặc tên thư viện/version. Có thể trả UNSUPPORTED_FILE hoặc INVALID_ARCHIVE; log nội bộ giữ loại parser và request ID sau khi redaction.

## 16. Không lộ thông tin qua response header hoặc HTML error page

Kiểm tra ngoài JSON body:

- Server/version banner.
- X-Powered-By.
- Debug/error detail header.
- Reverse proxy upstream header.
- Redirect Location chứa internal host hoặc token.
- Cookie được tạo sai khi lỗi.
- HTML error page có stack trace, path hoặc environment detail.

Tắt debug page và detailed error endpoint trong production. Cấu hình lỗi riêng cho CDN, gateway, ingress, load balancer và application. Một response do edge sinh ra cũng là public API response.

Với lỗi có dữ liệu nhạy cảm hoặc phụ thuộc principal, cân nhắc Cache-Control: no-store để tránh shared cache lưu response rồi phục vụ cho người khác. Không để CDN cache 401/403/404 theo một key thiếu tenant hoặc authorization context.

## 17. Correlation ID và khả năng truy vết

Client cần một mã để báo sự cố; operator cần mã để tìm đúng log. Tạo request ID ngẫu nhiên tại edge/application và trả nó trong response:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: 01J8Q6F3P2
~~~

Quy tắc:

- Không dùng session ID, token hoặc user ID làm request ID.
- Nếu client gửi correlation ID, validate format/length và lưu riêng; không để client chọn ID nội bộ dùng làm khóa bảo mật.
- Tạo ID nội bộ mới nếu thiếu hoặc sai format.
- Propagate qua service bằng header/tracing context được allowlist.
- Ghi request ID, route ID, service, status và policy decision vào structured log.
- Không đưa PII hoặc secret vào trace baggage.

Request ID không phải bí mật và không cấp quyền truy cập log. Người có ID vẫn phải qua authentication/authorization nếu muốn tra cứu incident.

## 18. Logging exception an toàn

Stack trace có thể cần cho debugging, nhưng log cũng là nơi lưu dữ liệu nhạy cảm. Không phải mọi log sink đều đáng tin hoặc có cùng quyền truy cập.

Thiết kế:

- Log trong server-side sink được kiểm soát; không nhúng stack vào response.
- Dùng structured logging với error category, exception class, request ID, route và deployment version.
- Chỉ ghi stack trace đầy đủ ở sink có quyền truy cập hạn chế và retention phù hợp.
- Redact Authorization, Cookie, Set-Cookie, API key, password, token, signed URL và connection string.
- Không log raw request body theo mặc định.
- Với exception có thể chứa input, ưu tiên log error category và fingerprint an toàn thay vì message nguyên văn.
- Tránh log cùng exception nhiều lần ở controller, service, gateway và global handler.
- Giới hạn log volume để lỗi lặp không gây log flooding hoặc chi phí bất thường.

Không ghi SQL bind parameter hoặc toàn bộ query chỉ để debug production. Nếu cần query diagnostics, dùng cơ chế database tracing có quyền hạn và redaction rõ ràng.

## 19. Timing và side channel qua lỗi

Ngay cả khi response body đã được làm sạch, sự khác biệt về status, message, kích thước và thời gian có thể tiết lộ thông tin:

- User tồn tại có thể trả nhanh hơn user không tồn tại.
- Email đã đăng ký có thể trả message khác email chưa đăng ký.
- Resource bị cấm có thể trả 403 còn resource không tồn tại trả 404.
- Database constraint có thể làm thời gian phản hồi khác rõ rệt.

Đánh giá theo threat model. Với login, password reset và account recovery, dùng response tổng quát và hạn chế rate để giảm enumeration. Với resource concealment, cân nhắc thống nhất response cho inaccessible và nonexistent resource. Không cố làm mọi endpoint có timing hoàn toàn giống nhau nếu chi phí không hợp lý; ưu tiên giảm tín hiệu rõ rệt và giới hạn số lần thử.

Không trả số lượng kết quả, tên constraint hoặc dữ liệu thống kê nội bộ trong lỗi nếu caller không có quyền.

## 20. Error response, cache và content negotiation

Lỗi có thể chứa thông tin phụ thuộc principal hoặc tenant. Đảm bảo cache không chia sẻ response giữa người dùng:

- Dùng Cache-Control: no-store cho auth error, validation có dữ liệu nhạy cảm và lỗi nội bộ.
- Không cache lỗi theo URL đơn thuần nếu response phụ thuộc Authorization, cookie hoặc tenant.
- Nếu có cache hợp lệ cho lỗi công khai, xác định cache key và Vary theo đúng header ảnh hưởng response.
- Không phản chiếu Accept hoặc Content-Type tùy ý vào response header.
- Chọn media type lỗi theo contract; không trả HTML debug page cho API client.
- Đảm bảo response compression không làm lộ nội dung bí mật qua kênh có thể bị quan sát chung nếu endpoint có rủi ro compression side channel.

CDN/API gateway cần có policy cache riêng cho 4xx/5xx. Không mặc định cache lỗi 404 hoặc 500 trong thời gian dài nếu trạng thái có thể thay đổi hoặc lỗi phụ thuộc người gọi.

## 21. Kiểm thử không rò rỉ thông tin

Test error response cần tìm các pattern nhạy cảm, không chỉ so sánh status:

| Nhóm test | Kích hoạt | Điều phải xác minh |
|---|---|---|
| Unexpected exception | Ném exception không dự kiến | Response chỉ có code/message chung và request ID |
| Stack trace | Lỗi ở controller/service/database | Không có class, package, line number hoặc stack frame |
| Filesystem | File thiếu/permission denied | Không có absolute path, mount hoặc OS user |
| SQL | Syntax/constraint/connection error | Không có SQL, table, column, constraint hoặc DB host |
| Secret | Exception chứa token/password/API key giả lập | Không xuất hiện trong body/header/log sink công khai |
| URL | HTTP client lỗi với signed URL/query token | Không echo URL hoặc query nhạy cảm |
| Auth enumeration | User tồn tại/không tồn tại, account locked | Response không tiết lộ trạng thái ngoài contract |
| Authorization concealment | Object thiếu và object inaccessible | Hành vi nhất quán theo policy |
| Validation | Password/token/HTML dài ở field sai | Không echo rejected value; số lỗi có giới hạn |
| Upstream | Service trả stack/debug body | Gateway không forward nội dung nội bộ |
| Proxy/edge | Lỗi do CDN, ingress, load balancer | Error page không có banner/path/host nội bộ |
| Cache | Hai principal gọi cùng URL gây lỗi khác nhau | Không nhận response đã cache của principal khác |
| Header | Error header/redirect chứa CRLF hoặc secret | Không có header injection hoặc lộ secret |
| Log | Kiểm tra log/APM/trace test | Redaction hoạt động trước khi dữ liệu rời process |

### 21.1 Canary secret test

Trong môi trường kiểm thử, tạo một chuỗi canary giả làm token hoặc password, cố ý đưa nó vào exception message và request header. Gọi endpoint gây lỗi rồi quét response body, response header, application log, trace và error reporting để xác minh canary không xuất hiện ở nơi công khai hoặc sink không được phép.

Không dùng credential thật cho test redaction. Canary phải là dữ liệu giả và có thể thu hồi/xóa sau test.

### 21.2 Test qua toàn bộ đường đi

Gọi qua CDN, WAF, gateway, ingress và application như production. Test trực tiếp upstream trong môi trường được phép để xác minh nó cũng không lộ stack/path/SQL. Một controller test pass chưa chứng minh trang lỗi do proxy hoặc container runtime tạo ra cũng an toàn.

## 22. Quy trình xử lý exception an toàn

Với mỗi API:

1. Định nghĩa error contract và bộ error code ổn định.
2. Phân loại lỗi expected, validation, authentication, authorization, business conflict và unexpected.
3. Map từng nhóm sang HTTP status/header đúng semantics.
4. Tạo response DTO riêng; không serialize exception.
5. Dùng message và detail do ứng dụng kiểm soát; không dùng exception.getMessage().
6. Loại stack trace, SQL, filesystem path, hostname, secret và dữ liệu nhạy cảm khỏi response.
7. Redact log, trace, APM và upstream diagnostic trước khi lưu/chuyển tiếp.
8. Tạo request ID nội bộ và propagate qua các hop.
9. Cấu hình lỗi production cho framework, proxy, CDN và load balancer.
10. Đặt Cache-Control phù hợp với lỗi phụ thuộc principal/tenant.
11. Test expected và unexpected error, canary secret và response header.
12. Theo dõi error rate, error code, redaction failure và thay đổi sau deploy.

## 23. Checklist rà soát

- [ ] Có error contract ổn định với code, status, safe message và request ID.
- [ ] Không serialize exception, cause chain, stack trace hoặc debug object ra client.
- [ ] Không trả exception.getMessage() trực tiếp.
- [ ] Không lộ filesystem path, source path, class/package, line number hoặc server banner.
- [ ] Không lộ SQL, bind parameter, table/column, constraint, database host hoặc schema nội bộ.
- [ ] Không lộ Authorization, cookie, API key, password, signed URL, connection string hoặc token.
- [ ] Validation response không echo rejected value hoặc payload nhạy cảm.
- [ ] Authentication error không cho phép user/account enumeration ngoài contract.
- [ ] 401/403/404 được dùng nhất quán; resource concealment có chủ đích.
- [ ] Upstream/gateway không forward error body hoặc debug header chưa được kiểm tra.
- [ ] HTML error page và lỗi do CDN/ingress/load balancer cũng đã được harden.
- [ ] Log/trace/APM có redaction, access control, encryption và retention.
- [ ] Request ID được tạo/validate an toàn và không dùng làm credential.
- [ ] Error response nhạy cảm có Cache-Control phù hợp; shared cache không trộn principal/tenant.
- [ ] Có test stack trace, path, SQL, secret, URL, auth enumeration và upstream leakage.
- [ ] Có canary test quét response, header, log và trace.
- [ ] Có monitoring và quy trình xử lý khi phát hiện secret đã xuất hiện trong log/response.

Thông báo lỗi an toàn không có nghĩa là che giấu mọi lỗi bằng một response vô nghĩa. Client vẫn cần status, error code và hướng dẫn đủ dùng; operator cần diagnostic có thể truy vết trong hệ thống được bảo vệ. Tách hai mục đích này, chuẩn hóa exception mapping và kiểm thử rò rỉ trên toàn bộ đường đi giúp API cung cấp trải nghiệm lỗi rõ ràng mà không biến lỗi vận hành thành nguồn tiết lộ stack trace, path, SQL hoặc secret.
