# Error code ổn định và message tối thiểu

Error response là một phần của API contract và cũng là một kênh có thể làm lộ thông tin. Khi request thất bại, client cần nhận biết lỗi thuộc nhóm nào để sửa dữ liệu, đăng nhập lại, xử lý xung đột hoặc thử lại sau. Nhưng response không nên tiết lộ stack trace, câu SQL, hostname nội bộ, trạng thái tài khoản nhạy cảm hay chi tiết policy mà attacker có thể dùng để dò hệ thống.

Thiết kế an toàn cần tách hai mục tiêu: **error code ổn định cho máy xử lý** và **message tối thiểu, an toàn cho người đọc**. Error code là định danh công khai có chủ đích, được quản lý như một phần hợp đồng API. Message giải thích ngắn gọn điều caller cần biết và hành động phù hợp, không kể lại exception nội bộ. Thông tin kỹ thuật để điều tra được ghi vào log/audit có kiểm soát và nối với response bằng correlation ID.

## 1. Vì sao error code cần ổn định?

Client thường cần phân biệt nhiều lỗi có cùng HTTP status. Ví dụ, `409 Conflict` có thể xảy ra khi đơn hàng đã đóng, mã tham chiếu bị trùng hoặc phiên bản object đã thay đổi. Nếu client phải phân tích chuỗi message, một thay đổi câu chữ hoặc ngôn ngữ có thể làm hỏng logic.

Một error code ổn định giúp:

- SDK và frontend xử lý lỗi bằng nhánh logic rõ ràng.
- Client không phụ thuộc vào câu chữ hoặc ngôn ngữ hiển thị.
- Server có thể cải thiện message mà không thay đổi semantics của code.
- Monitoring nhóm lỗi chính xác qua nhiều phiên bản.
- Support và vận hành đối chiếu mã lỗi với tài liệu, log và quy trình xử lý.
- API có thể thay đổi implementation hoặc framework mà không làm lộ exception class.

Ví dụ:

```json
{
  "status": 409,
  "code": "ORDER_STATE_CONFLICT",
  "message": "The order cannot be changed in its current state."
}
```

Client nên dùng `code` để quyết định hiển thị hướng dẫn hoặc tải lại trạng thái đơn hàng. `message` chỉ phục vụ hiển thị và có thể được bản địa hóa.

## 2. Phân biệt HTTP status, error code và message

Ba thành phần này có vai trò riêng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| HTTP status | Mô tả kết quả ở mức giao thức | `401`, `403`, `409`, `422`, `429`, `500` |
| Error code | Định danh nguyên nhân công khai theo API contract | `AUTHENTICATION_REQUIRED`, `ORDER_STATE_CONFLICT` |
| Message/detail | Giải thích ngắn gọn cho con người | `The order cannot be changed in its current state.` |

Không dùng message làm mã lỗi, ví dụ `"Invalid password"`, `"User does not exist"` hoặc `"Database timeout at db-prod-02"`. Câu chữ có thể thay đổi; hostname và nguyên nhân kỹ thuật có thể nhạy cảm.

Không trả mọi lỗi với HTTP `200 OK` rồi đặt `{ "success": false }` trong body. Proxy, browser, SDK, monitoring và retry policy dựa vào status HTTP. Error code bổ sung chi tiết cho status, không thay thế status.

## 3. Quy ước đặt tên error code

Một error code nên có dạng máy đọc được, dễ tìm kiếm và độc lập với implementation. Có thể dùng `UPPER_SNAKE_CASE` với namespace theo domain:

```text
AUTHENTICATION_REQUIRED
ACCESS_DENIED
RESOURCE_NOT_FOUND
VALIDATION_FAILED
ORDER_STATE_CONFLICT
IDEMPOTENCY_KEY_CONFLICT
QUOTA_EXCEEDED
INTERNAL_ERROR
```

Quy ước nên xác định:

- Chỉ dùng ký tự ASCII và format thống nhất.
- Không chứa tên class, package, SQL state, tên bảng hoặc tên server.
- Không nhúng dữ liệu động như user ID, email, tenant ID hay request value.
- Không tái sử dụng một code cũ cho ý nghĩa khác.
- Không tạo code riêng cho mọi câu message nhỏ nếu client không cần phân biệt.
- Có owner và tài liệu mô tả cho mỗi code được công bố.

Có thể tổ chức code theo domain như `AUTH_*`, `ORDER_*`, `PAYMENT_*` hoặc `FILE_*`. Prefix là quy ước, không phải cơ chế phân quyền. Không đưa thông tin bí mật vào code chỉ vì code được xem là máy đọc được.

### Code nên mô tả điều client có thể hành động

Một code hữu ích phân biệt các hành động khác nhau. Ví dụ:

| Code | Client có thể làm gì? |
|---|---|
| `VALIDATION_FAILED` | Sửa request theo lỗi field được công bố |
| `AUTHENTICATION_REQUIRED` | Đăng nhập hoặc cung cấp credential hợp lệ |
| `ACCESS_DENIED` | Dừng thao tác hoặc yêu cầu quyền qua quy trình hợp lệ |
| `ORDER_STATE_CONFLICT` | Tải trạng thái mới và xử lý xung đột |
| `QUOTA_EXCEEDED` | Chờ reset hoặc điều chỉnh plan theo hợp đồng |
| `DEPENDENCY_UNAVAILABLE` | Có thể retry có backoff nếu thao tác an toàn |

Không tạo code quá chi tiết làm lộ trạng thái nội bộ, ví dụ `USER_EXISTS_BUT_DISABLED_AND_MFA_PENDING`, nếu client không cần biết các trạng thái đó. Dùng một code tổng quát khi phân biệt chi tiết có thể hỗ trợ enumeration.

## 4. Error code là một phần của public API contract

Khi code được client sử dụng, nó trở thành hợp đồng. Thay đổi code có thể làm SDK, ứng dụng di động, tích hợp đối tác và dashboard xử lý sai.

Hãy quản lý error code giống như field API:

- Có catalog chính thức gồm code, HTTP status, ý nghĩa và hướng xử lý.
- Ghi rõ code áp dụng cho endpoint hoặc nhóm chức năng nào.
- Ghi rõ client có nên retry hay cần sửa request.
- Giữ semantics của code qua các lần refactor.
- Dùng OpenAPI extension hoặc tài liệu API để công bố các lỗi quan trọng.
- Có contract test để phát hiện code không được đăng ký hoặc status thay đổi ngoài ý muốn.
- Có quy trình deprecate nếu buộc phải thay thế code.

Không lấy tên exception Java làm code công khai. `AccessDeniedException` có thể được dùng ở nhiều tình huống, nhưng API có thể cần code `ACCESS_DENIED` chung; một exception database cũng có thể đại diện cho nhiều nguyên nhân nghiệp vụ khác nhau.

## 5. Message tối thiểu là gì?

Message tối thiểu cung cấp đúng thông tin caller cần để hiểu kết quả và chọn bước tiếp theo. Nó không chứa mọi chi tiết mà server biết.

Ví dụ an toàn:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid. Review the errors and try again."
}
```

Ví dụ không an toàn:

```json
{
  "code": "DB_ERROR",
  "message": "SQLState 23505 at db-prod-03, table users, constraint users_email_key; query was INSERT INTO ..."
}
```

Message công khai không nên chứa:

- Stack trace, tên class/package, tên framework hoặc đường dẫn file.
- SQL query, tên bảng/cột, constraint hoặc cấu trúc database.
- Hostname, IP private, port, tên cluster, queue, topic hoặc service nội bộ.
- Token, API key, cookie, session ID, secret hoặc nội dung header xác thực.
- Password, MFA code, reset token hoặc rejected value nhạy cảm.
- Payload đầy đủ, dữ liệu cá nhân không cần thiết hoặc thông tin của tenant khác.
- Chi tiết rule phát hiện gian lận, risk score hoặc logic chống lạm dụng.

Chi tiết nội bộ có thể được ghi vào log an toàn với quyền truy cập và retention phù hợp. Không chuyển chúng vào response chỉ để giúp người dùng tự debug.

## 6. Không làm lộ sự tồn tại của tài khoản hoặc resource

Một lỗi phổ biến là trả message khác nhau cho từng trạng thái tài khoản trong luồng đăng nhập, đăng ký hoặc khôi phục mật khẩu:

```text
Email không tồn tại.
Mật khẩu sai.
Tài khoản đã bị khóa.
Tài khoản đang chờ xác minh MFA.
```

Attacker có thể dùng các khác biệt này để dò tài khoản hợp lệ hoặc xác định trạng thái bảo mật của người dùng. Với các luồng nhạy cảm, hãy dùng phản hồi tổng quát có cùng status, code và message cho những trường hợp cần che giấu:

```json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "The supplied credentials could not be verified."
}
```

Với yêu cầu gửi email khôi phục mật khẩu, có thể trả thông báo không xác nhận tài khoản có tồn tại hay không:

```json
{
  "code": "RECOVERY_REQUEST_ACCEPTED",
  "message": "If an eligible account exists, instructions will be sent."
}
```

Không phải mọi endpoint đều cần che giấu sự tồn tại của resource. Ví dụ API quản trị nội bộ có thể cần phân biệt `RESOURCE_NOT_FOUND` và `ACCESS_DENIED` cho operator được cấp quyền. Hãy chọn mức thông tin theo threat model, audience và rủi ro enumeration; không dùng một quy tắc chung thiếu ngữ cảnh.

### Đồng nhất cả status, code, message và hành vi phụ

Chỉ dùng cùng message nhưng trả status khác nhau vẫn có thể tạo side channel. Hãy xem xét cả:

- HTTP status và error code.
- Body length, header và redirect.
- Thời gian phản hồi có khác biệt rõ rệt không.
- Có gửi email/SMS hoặc tạo side effect chỉ ở một trường hợp không.
- Rate limit và lockout có khác nhau theo việc account tồn tại không.

Không cần làm thời gian phản hồi giống hệt tuyệt đối trong mọi hệ thống, nhưng tránh khác biệt dễ đo lường mà không có lý do. Rate limit và monitoring giúp giảm khả năng dò hàng loạt.

## 7. Chọn mức chi tiết phù hợp với từng nhóm lỗi

Không phải message nào cũng cần chung chung như nhau. Lỗi validation thường cần chỉ rõ field để client sửa; lỗi xác thực và trạng thái tài khoản có thể cần ít chi tiết hơn; lỗi server phải tối thiểu.

| Nhóm lỗi | Thông tin công khai phù hợp | Thông tin giữ nội bộ |
|---|---|---|
| Validation | Field path, code và hướng sửa an toàn | Rejected value nhạy cảm, parser internals |
| Authentication | Cần credential hợp lệ hoặc thông tin xác thực không được chấp nhận | Token validation detail, account state nhạy cảm |
| Authorization | Hành động không được phép | Policy expression, role mapping nội bộ, object tồn tại nếu cần che |
| Not found | Resource không được tìm thấy trong phạm vi công khai | Khác biệt nội bộ giữa không tồn tại và không có quyền nếu cần che |
| Business conflict | Trạng thái không cho phép thao tác | Ghi chú nội bộ hoặc trạng thái fraud/risk |
| Rate/quota | Giới hạn đã đạt và thời điểm thử lại nếu được công bố | Ngưỡng chống lạm dụng nội bộ, risk score |
| Dependency/system | Dịch vụ tạm thời không thể hoàn tất request | Hostname, IP, stack trace, dependency topology |

## 8. HTTP status và error code nên đi cùng nhau

Một mapping tham khảo:

| HTTP status | Error code ví dụ | Message tối thiểu |
|---:|---|---|
| `400` | `MALFORMED_REQUEST` | `The request could not be parsed.` |
| `401` | `AUTHENTICATION_REQUIRED` | `Valid authentication is required.` |
| `403` | `ACCESS_DENIED` | `You are not allowed to perform this action.` |
| `404` | `RESOURCE_NOT_FOUND` | `The requested resource was not found.` |
| `409` | `RESOURCE_STATE_CONFLICT` | `The resource cannot be changed in its current state.` |
| `412` | `PRECONDITION_FAILED` | `The resource has changed. Retrieve the latest version and retry.` |
| `413` | `REQUEST_TOO_LARGE` | `The request exceeds the allowed size.` |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | `The request media type is not supported.` |
| `422` | `VALIDATION_FAILED` | `One or more fields are invalid.` |
| `429` | `RATE_LIMIT_EXCEEDED` | `Too many requests. Try again later.` |
| `500` | `INTERNAL_ERROR` | `The request could not be completed.` |
| `503` | `SERVICE_UNAVAILABLE` | `The service is temporarily unavailable.` |

Mapping thực tế phải theo contract của API. Ví dụ validation có thể dùng `400` hoặc `422` tùy quy ước. Không đổi status chỉ để làm cho error code có vẻ hợp lý; status cần giữ ngữ nghĩa HTTP.

`401` thường cần header `WWW-Authenticate` phù hợp với authentication scheme. `405` cần `Allow`. `429` hoặc `503` có thể dùng `Retry-After` khi server biết thời điểm có thể thử lại. Các header giao thức không nên bị thay bằng field JSON.

## 9. Validation message không phản chiếu dữ liệu nhạy cảm

Validation response nên cho client biết field nào sai và loại lỗi nào xảy ra, nhưng không cần trả lại giá trị người dùng đã gửi.

Ví dụ:

```json
{
  "status": 422,
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid.",
  "errors": [
    {
      "field": "quantity",
      "code": "MUST_BE_POSITIVE",
      "message": "Quantity must be greater than zero."
    }
  ]
}
```

Tránh trả:

```json
{
  "field": "password",
  "rejectedValue": "P@ssw0rd-secret",
  "message": "Password P@ssw0rd-secret failed policy check"
}
```

Các nguyên tắc:

- Không trả `rejectedValue` cho password, token, secret, payment data hoặc PII nhạy cảm.
- Không phản chiếu toàn bộ request body vào message.
- Giới hạn số lượng lỗi trả về và độ dài từng message.
- Dùng error code theo field/rule thay vì exception text từ validator.
- Không tiết lộ regex, policy nội bộ hoặc ngưỡng chống gian lận nếu việc đó giúp né kiểm soát.
- Với field không được phép cập nhật, cân nhắc trả lỗi chung thay vì liệt kê các thuộc tính nội bộ có thể sửa.

## 10. Error response theo RFC 9457 Problem Details

Với HTTP API, có thể dùng RFC 9457 Problem Details làm định dạng nền. Các member chuẩn gồm `type`, `title`, `status`, `detail` và `instance`; API có thể thêm extension như `code`, `traceId` hoặc `errors`.

Ví dụ:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be changed in its current state.",
  "code": "ORDER_STATE_CONFLICT",
  "traceId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V"
}
```

`code` và `traceId` là extension do API định nghĩa. Giữ schema nhất quán và công bố trong OpenAPI. `detail` phải an toàn; không đưa exception message nguyên bản vào đây. `instance` không nên chứa query string có token hoặc thông tin nhạy cảm.

Không bắt buộc mọi lỗi phải có danh sách `errors`. Với lỗi `500`, một message tổng quát là đủ; chi tiết nguyên nhân ở log nội bộ.

## 11. Ánh xạ exception nội bộ sang code công khai

Không để framework hoặc thư viện tự quyết định error response. Tạo một lớp mapping rõ ràng từ exception đã biết sang status, code và message đã đăng ký.

Ví dụ:

```java
public record PublicApiError(
    HttpStatus status,
    String code,
    String message
) {}

public final class ApiErrorCatalog {
    private ApiErrorCatalog() {}

    public static PublicApiError map(Exception ex) {
        if (ex instanceof OrderStateConflictException) {
            return new PublicApiError(
                HttpStatus.CONFLICT,
                "ORDER_STATE_CONFLICT",
                "The order cannot be changed in its current state."
            );
        }

        if (ex instanceof AccessDeniedException) {
            return new PublicApiError(
                HttpStatus.FORBIDDEN,
                "ACCESS_DENIED",
                "You are not allowed to perform this action."
            );
        }

        return new PublicApiError(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "The request could not be completed."
        );
    }
}
```

Đây là ví dụ minh họa. Trong ứng dụng thật, cần phân biệt exception nghiệp vụ, validation, authentication, authorization và dependency; không ánh xạ mọi exception thành `500` hoặc mọi exception database thành `409`. Không dùng `ex.getMessage()` làm message công khai trừ khi exception được thiết kế rõ là an toàn cho caller.

### Ví dụ `@RestControllerAdvice`

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> handleConflict(
            OrderStateConflictException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The order cannot be changed in its current state."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/order-state-conflict"));
        problem.setTitle("Order state conflict");
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        problem.setProperty("traceId", currentTraceId());

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception ex) {
        String traceId = currentTraceId();
        log.error("Unhandled API error; traceId={}", traceId, ex);

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "The request could not be completed."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/internal-error"));
        problem.setTitle("Internal Server Error");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("traceId", traceId);

        return ResponseEntity.internalServerError()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

Code dùng Spring Framework 6/Spring Boot 3 có hỗ trợ `ProblemDetail`; cần các import và dependency tương ứng. `currentTraceId()` phải lấy từ tracing/MDC do server quản lý. Không lấy trace ID từ request body hoặc dùng nó làm credential. Lỗi do Spring Security filter xảy ra trước controller cần được xử lý thêm bằng `AuthenticationEntryPoint` và `AccessDeniedHandler` để giữ contract.

## 12. Không trả exception message từ downstream

Một service có thể gọi database, payment provider, identity provider hoặc service nội bộ. Exception từ dependency có thể chứa thông tin không dành cho caller:

```text
Connection refused to payment-db-02.internal:5432
SQLState 08001
TLS certificate subject mismatch
Retry exhausted after 5 attempts
```

Không forward nguyên văn lỗi downstream. Service hiện tại phải phân loại lỗi theo contract của chính nó:

| Lỗi nội bộ | Public code có thể dùng | Message công khai |
|---|---|---|
| Dependency timeout | `DEPENDENCY_TIMEOUT` | `The request could not be completed in time.` |
| Dependency unavailable | `SERVICE_UNAVAILABLE` | `The service is temporarily unavailable.` |
| Invalid upstream response | `UPSTREAM_RESPONSE_INVALID` | `The request could not be completed.` |
| Internal database error | `INTERNAL_ERROR` | `The request could not be completed.` |

Tên service, hostname, IP, endpoint nội bộ và body lỗi upstream được giữ trong log/trace có kiểm soát. Không để caller dùng error response để lập bản đồ topology hoặc phiên bản dependency.

## 13. Tách public message khỏi internal diagnostic

Một exception có thể cần đầy đủ chi tiết để developer điều tra, nhưng response chỉ cần thông tin tối thiểu. Hãy tách các kênh:

| Kênh | Nội dung |
|---|---|
| HTTP response | Status, error code, message an toàn, trace/request ID |
| Application log | Exception, stack trace, dependency và nguyên nhân kỹ thuật đã lọc secret |
| Security audit | Actor, action, resource, tenant, decision và thời điểm |
| Metrics | Error code, status, route template, service và latency |
| Distributed trace | Span/error attributes đã chuẩn hóa, không chứa token/payload nhạy cảm |

Không ghi raw `Authorization`, cookie, API key, password, MFA code hoặc request body đầy đủ vào log. Nếu cần dữ liệu phục vụ điều tra, hãy redact trước khi ghi, giới hạn quyền đọc và đặt retention phù hợp.

Log nội bộ cũng có thể bị lộ hoặc bị truy cập trái phép. “Không trả cho client” không có nghĩa “có thể ghi mọi thứ vào log”.

## 14. Correlation ID để tra cứu mà không tiết lộ nội bộ

Client cần một mã tham chiếu để gửi cho support. Server có thể trả `traceId` hoặc `requestId` trong body/header:

```http
HTTP/1.1 500 Internal Server Error
X-Request-Id: 01JQ7N8W6M5Y4K3P2R1S0T9U8V
Content-Type: application/problem+json

{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "message": "The request could not be completed.",
  "traceId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V"
}
```

Correlation ID nên:

- Opaque, không mã hóa user ID, email, tenant secret hoặc thông tin nghiệp vụ.
- Được server tạo hoặc validate độ dài/ký tự nếu chấp nhận ID từ client.
- Không thể dùng để truy cập log hoặc dữ liệu nội bộ nếu không có quyền.
- Được ghi vào log/trace để support tra cứu.
- Không thay thế session ID, access token hoặc authorization context.

Khi nhận request ID do client gửi, tránh log trực tiếp chuỗi tùy ý có ký tự điều khiển hoặc nội dung log injection. Có thể tạo ID nội bộ riêng và lưu liên kết với external correlation value đã được chuẩn hóa.

## 15. Bản địa hóa message nhưng giữ code không đổi

Error code hướng tới máy, message hướng tới con người. Nếu API hỗ trợ nhiều ngôn ngữ, có thể trả message theo `Accept-Language`:

```json
{
  "code": "ORDER_STATE_CONFLICT",
  "message": "Đơn hàng không thể thay đổi ở trạng thái hiện tại."
}
```

Ở ngôn ngữ khác, message có thể được dịch nhưng code vẫn là `ORDER_STATE_CONFLICT`. Client không nên so sánh chuỗi message để quyết định luồng xử lý.

Quy tắc bản địa hóa:

- Code và semantics không đổi theo ngôn ngữ.
- Message ngắn, không chứa dữ liệu bí mật và không đưa nội dung do attacker kiểm soát vào HTML.
- Có fallback language nếu không có bản dịch.
- Nếu cache response theo ngôn ngữ, xử lý `Vary: Accept-Language` và cache policy phù hợp.
- Không dùng message bản địa hóa làm khóa metric; dùng code ổn định.

## 16. Client nên xử lý error code như thế nào?

Client nên ưu tiên HTTP status và error code, sau đó hiển thị message. Không nên retry mọi lỗi hoặc hiển thị toàn bộ body thô.

| Nhóm | Hành vi client thường phù hợp |
|---|---|
| `VALIDATION_FAILED` | Hiển thị lỗi field và yêu cầu sửa input |
| `AUTHENTICATION_REQUIRED` | Làm mới credential hoặc yêu cầu đăng nhập |
| `ACCESS_DENIED` | Dừng thao tác; không retry tự động |
| `RESOURCE_NOT_FOUND` | Hiển thị trạng thái không tìm thấy theo contract |
| `*_CONFLICT` | Tải lại trạng thái và yêu cầu người dùng xử lý xung đột |
| `RATE_LIMIT_EXCEEDED` | Tôn trọng `Retry-After`, dùng backoff |
| `SERVICE_UNAVAILABLE` | Retry có giới hạn nếu thao tác idempotent/an toàn |
| `INTERNAL_ERROR` | Hiển thị thông báo chung và cung cấp trace ID cho support |

Không dùng `message.includes("timeout")` hoặc `message.includes("invalid")` để quyết định retry. Message có thể được dịch hoặc thay đổi. Client cũng nên xử lý code chưa biết bằng fallback an toàn: hiển thị message đã lọc hoặc thông báo chung, không crash vì code mới.

Với thao tác ghi, retry cần idempotency key hoặc cơ chế bảo đảm không tạo side effect trùng. `503` không tự động có nghĩa request trước chưa được xử lý; client phải dựa vào semantics endpoint và idempotency contract.

## 17. Versioning và vòng đời error code

Một catalog có thể quản lý theo bảng:

| Field | Ví dụ |
|---|---|
| Code | `ORDER_STATE_CONFLICT` |
| HTTP status | `409` |
| Domain/owner | Orders API / Commerce team |
| Meaning | Thao tác không hợp lệ với trạng thái đơn hiện tại |
| Retryable | Không retry nguyên request; tải trạng thái mới |
| Public message key | `errors.order.stateConflict` |
| Since | API version hoặc release đầu tiên |
| Lifecycle | Active / Deprecated |

Khi cần đổi semantics, hãy tạo code mới hoặc version contract theo quy tắc tương thích. Không âm thầm đổi `ACCESS_DENIED` từ lỗi quyền thành lỗi token hết hạn nếu client có hành vi khác nhau cho hai trường hợp.

Thêm code mới thường dễ tương thích hơn đổi/xóa code cũ nếu client được yêu cầu xử lý unknown code. Nhưng vẫn cần đánh giá thay đổi status, retry behavior và message schema. Có thể công bố catalog dưới dạng OpenAPI response examples hoặc tài liệu riêng.

## 18. Rate limit và error message chống dò quét

Error response có thể bị dùng để dò endpoint, user, tenant, object ID hoặc trạng thái policy. Bên cạnh message tối thiểu, cần kết hợp:

- Rate limit theo principal, tenant, API key và endpoint phù hợp.
- Giới hạn số lần đăng nhập, recovery và kiểm tra identifier.
- Response tổng quát cho các trạng thái cần chống account/resource enumeration.
- Audit các lần dò nhiều ID hoặc gửi request thất bại theo pattern.
- Không tiết lộ policy threshold, fraud score hoặc rule engine detail.
- Giữ hành vi status/body nhất quán ở các trường hợp cần che thông tin.

Không chỉ dựa vào IP vì nhiều người dùng có thể chung IP và attacker có thể đổi IP. Rate limit cần kết hợp identity đã xác minh, tenant, endpoint và risk signal.

## 19. Kiểm thử error code và message tối thiểu

Test nên xác nhận hợp đồng công khai và bảo đảm thông tin nội bộ không xuất hiện:

| Nhóm test | Ca kiểm thử |
|---|---|
| Stable code | Cùng lỗi nghiệp vụ trả cùng code qua các phiên bản tương thích |
| Status mapping | HTTP status khớp error code catalog và body |
| Unknown code | Client xử lý an toàn khi server thêm code mới |
| No stack trace | Response không có stack trace, class/package hoặc đường dẫn file |
| No infrastructure leak | Không có SQL, hostname, IP private, queue/topic hoặc topology |
| No secrets | Không có token, cookie, API key, password hoặc rejected secret |
| Enumeration | Account/resource tồn tại và không tồn tại có phản hồi phù hợp threat model |
| Timing | Không có chênh lệch dễ khai thác giữa các nhánh cần che giấu |
| Validation | Field path/code rõ nhưng không phản chiếu rejected value nhạy cảm |
| Localization | Message đổi theo ngôn ngữ nhưng code không đổi |
| Correlation | Trace ID nối được log nhưng không cấp quyền truy cập log |
| Retry | `Retry-After` và error code phù hợp; client không retry lỗi permanent |
| Downstream | Lỗi dependency không bị forward nguyên văn |
| Security filters | `401`/`403` từ filter dùng cùng contract với controller |
| Logging | Log có diagnostic cần thiết nhưng redact secret và PII |

Ví dụ kiểm tra response bằng Spring MockMvc:

```java
mockMvc.perform(get("/api/v1/orders/{id}", orderId))
    .andExpect(status().isConflict())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.code").value("ORDER_STATE_CONFLICT"))
    .andExpect(jsonPath("$.message").value(
        "The order cannot be changed in its current state."))
    .andExpect(jsonPath("$.stackTrace").doesNotExist())
    .andExpect(jsonPath("$.sql").doesNotExist());
```

Test ví dụ cần khớp schema Problem Details thực tế của ứng dụng; nếu dùng `detail` thay vì `message`, hãy kiểm tra field đúng theo contract. Ngoài test đơn vị, nên có integration/contract test qua gateway và security filter.

## 20. Checklist error code ổn định và message tối thiểu

- [ ] HTTP status được dùng đúng ngữ nghĩa và không thay bằng `200` cho lỗi.
- [ ] Mỗi lỗi công khai quan trọng có error code ổn định, có owner và tài liệu.
- [ ] Code không chứa tên exception, SQL state, hostname hoặc dữ liệu động nhạy cảm.
- [ ] Không tái sử dụng code cũ cho semantics khác.
- [ ] Message chỉ chứa thông tin caller cần để hiểu và hành động.
- [ ] Không trả stack trace, SQL, topology, token, cookie, secret hoặc rejected value nhạy cảm.
- [ ] Luồng login/recovery/resource lookup chống enumeration theo threat model.
- [ ] Status, code, message, header và side effect không tạo khác biệt tiết lộ ngoài ý muốn.
- [ ] Validation response chỉ nêu field/code cần thiết, giới hạn số lỗi và độ dài.
- [ ] Exception nội bộ được ánh xạ qua catalog; không forward message từ dependency.
- [ ] Log/audit/trace tách khỏi public response và được redact/kiểm soát quyền.
- [ ] Correlation ID opaque, có thể tra cứu nội bộ nhưng không phải credential.
- [ ] Message có thể bản địa hóa mà code không thay đổi.
- [ ] Client xử lý unknown code và retry theo status/code/idempotency contract.
- [ ] Error catalog được version hóa, mô tả trong API contract và có contract test.

## Kết luận

Error code ổn định giúp client và hệ thống vận hành phân loại lỗi mà không phụ thuộc câu chữ hoặc exception nội bộ. Message tối thiểu giúp caller hiểu bước tiếp theo mà không tiết lộ stack trace, cấu trúc database, topology hay trạng thái nhạy cảm của tài khoản và resource. Hãy quản lý code như một phần public API contract, ánh xạ exception qua catalog rõ ràng, giữ diagnostic trong log/audit có kiểm soát và dùng correlation ID để nối hai phía. Khi kết hợp status HTTP đúng ngữ nghĩa, chống enumeration, validation response an toàn và kiểm thử contract, API vừa dễ tích hợp vừa giảm nguy cơ rò rỉ thông tin.
