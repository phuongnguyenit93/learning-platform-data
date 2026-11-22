# Ngăn lộ chi tiết kỹ thuật qua phản hồi lỗi

Khi một request thất bại, ứng dụng web cần cho người dùng biết điều gì đã xảy ra và họ có thể làm gì tiếp theo. Tuy nhiên, phản hồi lỗi cũng có thể vô tình tiết lộ cấu trúc bên trong của hệ thống: stack trace, câu SQL, tên bảng, đường dẫn máy chủ, tên lớp, phiên bản thư viện, thông tin cấu hình hoặc dữ liệu nhạy cảm.

Trong mô hình **Model–View–Controller (MVC)**, lỗi có thể phát sinh ở nhiều nơi: binding dữ liệu trong Controller, quy tắc nghiệp vụ trong Model, truy vấn ở repository, tích hợp dịch vụ bên ngoài hoặc quá trình render View. Một thiết kế tốt cần chuyển lỗi nội bộ thành phản hồi phù hợp với người dùng và giao thức, đồng thời giữ đủ thông tin chẩn đoán ở kênh nội bộ có kiểm soát.

Nguyên tắc quan trọng là **phản hồi công khai và chẩn đoán nội bộ phục vụ hai mục đích khác nhau**. Người dùng cần mã lỗi ổn định, thông điệp dễ hiểu và cách tiếp tục. Đội phát triển cần exception, stack trace, trace ID và ngữ cảnh kỹ thuật để điều tra. Không nên gửi toàn bộ dữ liệu chẩn đoán nội bộ cho trình duyệt hoặc API client.

## 1. Vì sao phản hồi lỗi có thể làm lộ hệ thống?

Một số ứng dụng trong quá trình phát triển trả trực tiếp thông tin exception về client:

~~~text
HTTP 500 Internal Server Error

org.hibernate.exception.SQLGrammarException:
could not execute statement

Caused by: java.sql.SQLSyntaxErrorException:
Table 'shop.customer_account' doesn't exist

at com.example.shop.persistence.CustomerRepository.findByEmail(...)
at com.example.shop.web.RegistrationController.submit(...)
...
~~~

Thông tin này có thể cho biết:

- Ứng dụng dùng Java, Hibernate và một loại cơ sở dữ liệu cụ thể.
- Tên schema hoặc bảng nội bộ.
- Tên package, lớp và phương thức trong mã nguồn.
- Đường dẫn thực thi và cấu trúc tầng của ứng dụng.
- Truy vấn hoặc dữ liệu liên quan đến thao tác thất bại.

Kẻ tấn công có thể dùng các chi tiết đó để thu hẹp phạm vi dò tìm, xác định công nghệ và tìm điểm yếu đã biết. Ngay cả khi không có lỗ hổng trực tiếp, thông tin nội bộ vẫn có thể hỗ trợ các cuộc tấn công tiếp theo.

Không chỉ lỗi 500 mới nguy hiểm. Thông báo validation, lỗi đăng nhập, lỗi không tìm thấy tài nguyên hoặc lỗi tích hợp cũng có thể tiết lộ dữ liệu nếu ứng dụng trả nguyên văn thông tin từ exception hoặc hệ thống bên ngoài.

## 2. Phân loại thông tin trước khi trả lỗi

Trước khi thiết kế error response, hãy phân biệt thông tin nào dành cho client và thông tin nào chỉ dành cho hệ thống nội bộ.

| Loại thông tin | Có thể trả cho client? | Ví dụ |
|---|---|---|
| HTTP status | Có | 400, 401, 403, 404, 409, 500 |
| Mã lỗi công khai ổn định | Có | ORDER_NOT_FOUND, VALIDATION_FAILED |
| Thông điệp hướng dẫn người dùng | Có | “Thông tin nhập chưa hợp lệ.” |
| Tên trường bị lỗi | Có, nếu an toàn | email, quantity |
| Stack trace | Không | Tên lớp, phương thức, số dòng |
| Câu SQL và tên bảng | Không | select từ customer_account |
| Đường dẫn file hoặc thư mục máy chủ | Không | Đường dẫn cấu hình nội bộ |
| Hostname, IP nội bộ, topology | Không | Tên node, địa chỉ database |
| Biến môi trường và cấu hình | Không | Database URL, secret key |
| Token, cookie, mật khẩu, OTP | Không | Authorization header, session ID |
| Dữ liệu cá nhân không liên quan | Không | Email người khác, thông tin thanh toán |
| Trace ID ngẫu nhiên | Có thể | Mã để tra cứu với bộ phận hỗ trợ |

Thông điệp dành cho người dùng nên mô tả vấn đề ở mức cần thiết. Ví dụ “Không thể hoàn tất thao tác lúc này. Vui lòng thử lại sau.” an toàn hơn việc hiển thị nguyên văn lỗi kết nối database.

Mã lỗi công khai cần ổn định và không chứa chi tiết triển khai. Không nên dùng tên exception Java làm mã lỗi API vì việc đổi framework hoặc refactor lớp nội bộ sẽ làm thay đổi hợp đồng bên ngoài.

## 3. Tách phản hồi công khai khỏi chẩn đoán nội bộ

Một xử lý lỗi thường có hai đầu ra:

1. **Phản hồi công khai:** HTTP status, mã lỗi, thông điệp an toàn, trường bị lỗi nếu phù hợp và trace ID.
2. **Chẩn đoán nội bộ:** exception gốc, stack trace, nguyên nhân sâu, thông tin truy vấn đã được làm sạch và ngữ cảnh request cần thiết.

~~~mermaid
flowchart TD
    R[Request] --> C[Controller / Use case]
    C -->|Exception| H[Exception Handler]
    H --> S[Phân loại và ánh xạ lỗi]
    S --> P[Phản hồi an toàn cho client]
    S --> L[Log / tracing nội bộ]
    P --> U[Trình duyệt hoặc API client]
    L --> O[Hệ thống quan sát có kiểm soát]
~~~

Exception handler là ranh giới phù hợp để chuyển exception thành phản hồi. Handler không nên đưa exception message, cause hoặc stack trace vào response chỉ vì chúng có sẵn.

Kênh log nội bộ cũng cần bảo vệ. Không phải cứ thông tin không trả cho client thì có thể ghi nguyên vẹn vào log. Stack trace hoặc câu SQL có thể chứa tham số, email, token hay dữ liệu cá nhân. Hãy giới hạn quyền truy cập, thời gian lưu và nội dung nhạy cảm được ghi.

## 4. Dùng HTTP status đúng với loại lỗi

Status code giúp client hiểu nhóm lỗi và chọn hành động tiếp theo. Không nên trả 200 cho mọi trường hợp chỉ vì server đã tạo được một trang thông báo lỗi.

| Status | Ý nghĩa thường dùng | Ví dụ trong MVC |
|---|---|---|
| 400 Bad Request | Request không hợp lệ hoặc sai cấu trúc | JSON sai định dạng, tham số không thể chuyển kiểu |
| 401 Unauthorized | Chưa xác thực hoặc thông tin xác thực không hợp lệ | Session hết hạn, thiếu credential |
| 403 Forbidden | Đã xác thực nhưng không được phép | Người dùng không có quyền thực hiện thao tác |
| 404 Not Found | Không tìm thấy tài nguyên hoặc route | Không có đơn hàng với định danh yêu cầu |
| 405 Method Not Allowed | Route tồn tại nhưng HTTP method không được hỗ trợ | Gửi POST đến endpoint chỉ cho GET |
| 409 Conflict | Xung đột với trạng thái hiện tại | Đơn đã giao nên không thể hủy |
| 422 Unprocessable Content | Nội dung hiểu được nhưng không đáp ứng điều kiện xử lý | Một số API dùng cho lỗi validation/nghiệp vụ |
| 429 Too Many Requests | Gửi quá nhiều request | Vượt giới hạn thử đăng nhập |
| 500 Internal Server Error | Lỗi không dự kiến ở máy chủ | Lỗi lập trình hoặc lỗi hạ tầng không được xử lý riêng |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng | Phụ thuộc quan trọng đang bảo trì hoặc quá tải |

Việc chọn 400 hay 422 cho validation phụ thuộc hợp đồng API. Với biểu mẫu HTML, máy chủ có thể trả lại trang form cùng status 400 hoặc status phù hợp với quy ước ứng dụng. Điều quan trọng là status và nội dung phản hồi phải nhất quán.

Đôi khi ứng dụng trả 404 cho một tài nguyên mà người dùng không được phép biết có tồn tại hay không, thay vì 403. Đây là quyết định chống dò tìm tài nguyên; cần áp dụng nhất quán và không để thông điệp khác nhau tiết lộ sự tồn tại.

## 5. Không trả trực tiếp exception message

Đoạn mã sau dễ gây rò rỉ:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<String> handle(Exception ex) {
    return ResponseEntity
            .status(500)
            .body(ex.getMessage());
}
~~~

Exception message có thể chứa SQL, tên file, URL nội bộ, dữ liệu request hoặc chi tiết từ dịch vụ bên ngoài. Một số thư viện đưa cả tham số truy vấn hoặc giá trị đầu vào vào thông báo lỗi.

Không nên sửa bằng cách chỉ cắt chuỗi hoặc thay một vài từ nhạy cảm. Cách an toàn hơn là ánh xạ loại lỗi sang thông điệp đã được định nghĩa trước:

~~~java
public record ApiError(String code, String message) {}

@ExceptionHandler(Exception.class)
public ResponseEntity<ApiError> handleUnexpected(
        Exception exception
) {
    return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(new ApiError(
                    "INTERNAL_ERROR",
                    "Đã xảy ra lỗi. Vui lòng thử lại sau."
            ));
}
~~~

Ví dụ trên minh họa nội dung công khai. Trong ứng dụng thật, handler cần ghi nhận lỗi nội bộ bằng trace ID và log an toàn; phần đó được trình bày ở các mục sau.

## 6. Dùng mã lỗi ổn định thay cho tên exception

Một ứng dụng có thể có nhiều exception nội bộ:

- OrderNotFoundException
- OrderAlreadyShippedException
- InventoryUnavailableException
- PaymentGatewayTimeoutException
- DataIntegrityViolationException

Không nên trả nguyên tên lớp hoặc package cho client. Thay vào đó, định nghĩa mã lỗi công khai theo ý nghĩa của hợp đồng:

| Exception nội bộ | Mã lỗi công khai | Thông điệp an toàn |
|---|---|---|
| OrderNotFoundException | ORDER_NOT_FOUND | Không tìm thấy đơn hàng. |
| OrderAlreadyShippedException | ORDER_CANNOT_BE_CANCELLED | Đơn hàng hiện không thể hủy. |
| InventoryUnavailableException | ITEM_UNAVAILABLE | Sản phẩm hiện không đủ số lượng. |
| PaymentGatewayTimeoutException | PAYMENT_TEMPORARILY_UNAVAILABLE | Chưa thể xác nhận thanh toán. Vui lòng kiểm tra lại trạng thái đơn trước khi thử lại. |
| Lỗi không dự kiến | INTERNAL_ERROR | Đã xảy ra lỗi. Vui lòng thử lại sau. |

Mã lỗi ổn định giúp client hiển thị thông điệp, ghi nhận analytics hoặc quyết định có cho phép thử lại mà không phụ thuộc vào exception class. Tránh mã hóa thông tin nhạy cảm hoặc ID người dùng vào error code.

## 7. Chuẩn hóa lỗi API bằng Problem Details

Với API HTTP, có thể dùng định dạng Problem Details theo RFC 9457 (kế thừa RFC 7807). Định dạng này cung cấp các trường chuẩn:

- type: URI định danh loại vấn đề.
- title: tiêu đề ngắn.
- status: HTTP status.
- detail: mô tả an toàn cho trường hợp cụ thể.
- instance: URI tham chiếu đến lần xảy ra vấn đề.

Ứng dụng có thể thêm extension fields như code hoặc traceId, miễn là không làm lộ thông tin nội bộ.

Ví dụ phản hồi:

~~~json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Đơn hàng không tồn tại hoặc bạn không có quyền truy cập.",
  "instance": "/api/orders/ORD-1001",
  "code": "ORDER_NOT_FOUND",
  "traceId": "8f1c4c2d9a6e"
}
~~~

Instance nên là đường dẫn đã được kiểm soát, không chứa query string có thể mang dữ liệu nhạy cảm. Không đưa stack trace, câu SQL, exception message hoặc request body vào extension fields.

### 7.1. Ví dụ với Spring Framework

Spring Framework 6 hỗ trợ ProblemDetail. Có thể dùng @RestControllerAdvice để ánh xạ exception:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException exception,
            HttpServletRequest request
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Đơn hàng không tồn tại hoặc bạn không có quyền truy cập."
        );
        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_NOT_FOUND");
        problem.setProperty("traceId", TraceIds.current());

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(problem);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> handleUnexpected(
            Exception exception
    ) {
        String traceId = TraceIds.current();
        logUnexpected(exception, traceId);

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Đã xảy ra lỗi. Vui lòng thử lại sau."
        );
        problem.setTitle("Lỗi máy chủ");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("traceId", traceId);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

TraceIds và logUnexpected là các thành phần minh họa cần được triển khai theo cơ chế tracing/logging của ứng dụng. Trong code thực tế, có thể dùng MDC hoặc tracing framework để lấy trace ID. Handler không dùng exception.getMessage() làm detail.

Nếu dùng Spring Boot hoặc Spring Framework phiên bản cũ hơn, cách tạo Problem Details và cấu hình hỗ trợ có thể khác. Hãy kiểm tra phiên bản đang dùng thay vì sao chép annotation hoặc API không tương thích.

## 8. Xử lý lỗi cho View HTML và API JSON

Một ứng dụng MVC có thể phục vụ cả HTML và JSON. Hai kênh cần phản hồi khác nhau:

- HTML thường trả một trang lỗi có bố cục, thông điệp và hướng dẫn quay lại.
- API trả JSON theo hợp đồng lỗi ổn định, kèm HTTP status.

Không nên trả trang HTML lỗi 500 cho client đang chờ JSON, hoặc trả nguyên JSON nội bộ vào trình duyệt như một trang không có ngữ cảnh.

### 8.1. Trang lỗi HTML

Với Spring MVC, có thể dùng @ControllerAdvice hoặc error controller để trả View:

~~~java
@ControllerAdvice(basePackages = "com.example.web.html")
public class HtmlExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ModelAndView orderNotFound() {
        ModelAndView view = new ModelAndView("errors/404");
        view.setStatus(HttpStatus.NOT_FOUND);
        view.addObject(
                "message",
                "Không tìm thấy nội dung bạn yêu cầu."
        );
        view.addObject("traceId", TraceIds.current());
        return view;
    }

    @ExceptionHandler(Exception.class)
    public ModelAndView unexpected(Exception exception) {
        String traceId = TraceIds.current();
        logUnexpected(exception, traceId);

        ModelAndView view = new ModelAndView("errors/500");
        view.setStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        view.addObject(
                "message",
                "Đã xảy ra lỗi. Vui lòng thử lại sau."
        );
        view.addObject("traceId", traceId);
        return view;
    }
}
~~~

Ví dụ này minh họa trang lỗi HTML. Nếu cùng ứng dụng có REST controller, nên tổ chức advice theo package hoặc loại controller để không vô tình chuyển lỗi API thành View. Có thể dùng các advice riêng cho HTML và API, hoặc một chiến lược xử lý có xét Accept header.

Template lỗi chỉ hiển thị thông điệp đã được kiểm soát:

~~~html
<main>
    <h1>Không thể hoàn tất yêu cầu</h1>
    <p th:text="${message}">
        Đã xảy ra lỗi. Vui lòng thử lại sau.
    </p>
    <p>
        Mã hỗ trợ:
        <code th:text="${traceId}">trace-id</code>
    </p>
</main>
~~~

Dùng cơ chế escape mặc định của template engine. Không đưa exception hoặc stack trace vào model của View.

### 8.2. Phản hồi JSON

REST controller có thể dùng @RestControllerAdvice riêng để trả Problem Details. Nếu framework hỗ trợ content negotiation, cần kiểm tra cả request có Accept: application/json, Accept: text/html và trường hợp client không gửi Accept.

## 9. Ánh xạ các lỗi đã biết một cách cụ thể

Không nên dùng một handler tổng quát cho mọi exception nếu ứng dụng có thể phân biệt các trường hợp phổ biến. Ánh xạ cụ thể giúp status và thông điệp chính xác hơn.

| Tình huống | Xử lý phù hợp |
|---|---|
| Không tìm thấy đơn hàng | 404 và mã ORDER_NOT_FOUND |
| Đơn không thể hủy do đã giao | 409 và mã ORDER_CANNOT_BE_CANCELLED |
| Form thiếu email | Trả form với lỗi trường hoặc 400/422 cho API |
| Chưa đăng nhập | 401 hoặc redirect đến trang đăng nhập theo kênh |
| Không có quyền | 403 hoặc 404 theo chính sách chống dò tìm |
| Dịch vụ thanh toán tạm thời lỗi | 503 hoặc lỗi nghiệp vụ được định nghĩa rõ; không tiết lộ endpoint nội bộ |
| Lỗi không dự kiến | 500 với thông điệp chung và trace ID |

Đối với timeout thanh toán, không nên mặc định cho client thử lại ngay nếu không biết giao dịch đã được xử lý hay chưa. Phản hồi cần hướng dẫn kiểm tra trạng thái giao dịch hoặc dùng cơ chế idempotency phù hợp để tránh tạo thanh toán trùng.

## 10. Validation error không được phản chiếu dữ liệu nhạy cảm

Lỗi validation thường cần chỉ ra trường nào cần sửa. Tuy nhiên, không nên trả lại toàn bộ rejected value một cách vô điều kiện.

Ví dụ response an toàn:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Dữ liệu chưa hợp lệ",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "email",
      "code": "EMAIL_INVALID",
      "message": "Vui lòng nhập địa chỉ email hợp lệ."
    },
    {
      "field": "password",
      "code": "PASSWORD_POLICY",
      "message": "Mật khẩu chưa đáp ứng yêu cầu."
    }
  ]
}
~~~

Không cần gửi lại giá trị mật khẩu, OTP, token hoặc dữ liệu thanh toán. Với trường văn bản thông thường, nếu cần giữ dữ liệu đã nhập, hãy cân nhắc việc render lại qua form object và escape đầu ra. Với các trường bí mật, yêu cầu người dùng nhập lại.

Thông điệp validation nên được định nghĩa trước hoặc tạo từ mã lỗi ổn định. Không nên đưa nội dung exception binding hoặc giá trị client tự gửi trực tiếp vào thông điệp mà chưa kiểm soát.

## 11. Logging nội bộ an toàn

Không trả stack trace cho client không có nghĩa là bỏ qua lỗi. Đội phát triển cần đủ thông tin để điều tra mà không ghi thừa dữ liệu nhạy cảm.

Một bản ghi lỗi có cấu trúc có thể gồm:

- Timestamp.
- Trace ID hoặc correlation ID.
- Mã lỗi nội bộ hoặc công khai.
- Exception class.
- Tên use case hoặc route đã chuẩn hóa.
- HTTP method và status.
- Thời gian xử lý.
- Thông tin định danh đã được giảm thiểu hoặc giả danh hóa nếu cần.

Không nên ghi:

- Password, OTP, session ID, access token, refresh token.
- Cookie hoặc Authorization header.
- Toàn bộ request body nếu có dữ liệu cá nhân hoặc thanh toán.
- Secret, connection string hoặc biến môi trường.
- SQL parameter có chứa dữ liệu người dùng mà không được làm sạch.

### 11.1. Ví dụ ghi log với trace ID

~~~java
private static final Logger log =
        LoggerFactory.getLogger(ApiExceptionHandler.class);

private void logUnexpected(Exception exception, String traceId) {
    log.error(
            "Unhandled request failure traceId={} exceptionType={}",
            traceId,
            exception.getClass().getName(),
            exception
    );
}
~~~

Ví dụ này ghi stack trace vào log nội bộ. Chỉ dùng khi hệ thống logging có quyền truy cập và thời hạn lưu phù hợp; cần kiểm tra exception và thư viện có đưa dữ liệu nhạy cảm vào message hay SQL hay không. Với một số lỗi chứa thông tin nhạy cảm, cần log đã làm sạch hoặc chỉ ghi metadata cùng trace ID.

### 11.2. Dùng MDC hoặc tracing context

MDC (Mapped Diagnostic Context) giúp gắn trace ID vào các log trong cùng ngữ cảnh xử lý:

~~~java
try {
    MDC.put("traceId", traceId);
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("traceId");
}
~~~

Đây là ví dụ rút gọn cho Servlet filter đồng bộ. Với async request hoặc reactive stack, context có thể không tự truyền qua thread; nên dùng cơ chế context propagation của framework hoặc tracing library. Luôn xóa MDC trong finally để tránh dữ liệu request này rò sang request khác khi thread được tái sử dụng.

Nếu nhận correlation ID từ header client gửi lên, cần kiểm tra định dạng và giới hạn độ dài; không tin một giá trị tùy ý để đưa vào log vì có thể gây log injection hoặc làm sai lệch truy vết. Có thể tạo ID mới ở gateway hoặc ứng dụng và chỉ chấp nhận ID upstream từ nguồn đáng tin cậy.

## 12. Không để cấu hình development xuất hiện ở production

Framework thường có chế độ hiển thị lỗi chi tiết phục vụ phát triển. Cấu hình đó có thể hữu ích trên máy lập trình nhưng nguy hiểm nếu triển khai ra môi trường thật.

Với Spring Boot, cần xem xét các thuộc tính:

~~~properties
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

Các thuộc tính này giúp hạn chế nội dung lỗi mặc định mà Spring Boot đưa vào error response. Tên và hành vi chính xác có thể khác theo phiên bản; hãy kiểm tra tài liệu của phiên bản dự án. Chúng cũng không thay thế exception handler tùy chỉnh: handler tự tạo vẫn có thể vô tình trả stack trace hoặc exception message.

Một số nguyên tắc cấu hình:

- Production không bật trang lỗi developer hoặc debug endpoint công khai.
- Không hiển thị stack trace qua error page, actuator hoặc endpoint nội bộ chưa được bảo vệ.
- Không đưa secret vào cấu hình có thể bị serialize ra error response.
- Reverse proxy và API gateway cũng cần cấu hình trang lỗi an toàn.
- Không gửi header tiết lộ phiên bản server/framework nếu không cần thiết.
- Dùng cấu hình môi trường rõ ràng và kiểm tra cấu hình hiệu lực khi deploy.

## 13. Error page của Jakarta Servlet

Với ứng dụng Servlet truyền thống, có thể khai báo trang lỗi trong web.xml:

~~~xml
<error-page>
    <error-code>404</error-code>
    <location>/WEB-INF/views/errors/404.jsp</location>
</error-page>

<error-page>
    <error-code>500</error-code>
    <location>/WEB-INF/views/errors/500.jsp</location>
</error-page>
~~~

Servlet container có thể cung cấp các error attributes như:

- jakarta.servlet.error.status_code
- jakarta.servlet.error.request_uri
- jakarta.servlet.error.exception
- jakarta.servlet.error.exception_type
- jakarta.servlet.error.message

Các thuộc tính này hữu ích cho xử lý nội bộ, nhưng không nên đưa nguyên văn vào JSP. Trang lỗi chỉ nên dùng status và thông điệp đã được kiểm soát. Đường dẫn request cũng cần tránh query string nhạy cảm.

Nếu ứng dụng gọi sendError, container có thể chuyển đến error page đã cấu hình. Hãy kiểm tra response status thực tế và bảo đảm error page không ghi đè status thành 200.

## 14. Tránh lỗi thứ cấp trong quá trình xử lý lỗi

Error handler cũng là mã ứng dụng và có thể tự phát sinh lỗi. Một số tình huống cần chú ý:

- Error template truy cập database hoặc lazy entity rồi lại lỗi.
- Handler gọi dịch vụ ngoài để lấy thông điệp nhưng dịch vụ đó cũng đang lỗi.
- Log appender không hoạt động hoặc làm request chậm đáng kể.
- Response đã được commit một phần nên không thể thay status hoặc body.
- Handler bắt Exception rồi trả 200, khiến monitoring không nhận ra thất bại.
- Handler trả lại chính exception message trong một trường detail.

Trang lỗi nên phụ thuộc tối thiểu vào database và các dịch vụ ngoài. Hãy giữ template lỗi đơn giản, dữ liệu đầu vào ít và cơ chế fallback tối thiểu nếu chính error handler thất bại.

Nếu response đã được gửi một phần, ứng dụng có thể không thể thay bằng JSON hoặc trang lỗi mới. Trong trường hợp đó, ghi log với trace ID và kết thúc xử lý phù hợp; không cố ghi nối một error document vào body đã bắt đầu.

## 15. Bảo vệ thông tin trong URL, header và metadata

Ngay cả khi body lỗi an toàn, các phần khác của HTTP response có thể làm lộ dữ liệu:

- URL redirect có thể chứa token hoặc dữ liệu người dùng.
- Location header có thể trỏ đến hostname nội bộ.
- Header debug có thể chứa tên node, phiên bản hoặc đường dẫn.
- Cookie có thể bị phản hồi lại trong log hoặc error report.
- instance trong Problem Details có thể chứa query string nhạy cảm.

Hãy dùng URL tương đối hoặc hostname công khai đã được cấu hình, không lấy host tùy ý từ header request để xây dựng link lỗi. Chỉ đưa các header cần thiết vào phản hồi và tránh phản chiếu dữ liệu client không được kiểm soát.

## 16. Kiểm thử để xác nhận không lộ chi tiết kỹ thuật

Một trang lỗi có thể trông đúng khi xem bằng mắt nhưng response vẫn chứa stack trace trong HTML comment, script, JSON metadata hoặc header. Vì vậy, cần kiểm tra nội dung phản hồi thực tế.

### 16.1. Kiểm thử status và hợp đồng lỗi

- Lỗi không tìm thấy trả đúng 404.
- Lỗi xung đột nghiệp vụ trả đúng 409.
- Lỗi không dự kiến trả 500.
- API trả đúng content type và cấu trúc Problem Details.
- Mã lỗi công khai ổn định và không phụ thuộc tên exception.

### 16.2. Kiểm thử không rò rỉ thông tin

Tạo một exception có thông điệp giả lập chứa dấu hiệu nội bộ, ví dụ:

~~~text
SECRET_MARKER database.internal.local /srv/app/config/password
~~~

Gửi request gây lỗi và xác minh response không chứa:

- SECRET_MARKER.
- database.internal.local.
- Đường dẫn /srv/app/config/password.
- Stack trace hoặc tên package nội bộ.
- SQL, tên bảng hoặc thông tin cấu hình.

Đồng thời xác minh thông điệp công khai và trace ID vẫn xuất hiện đúng.

### 16.3. Ví dụ với MockMvc

~~~java
@WebMvcTest(OrderApiController.class)
@Import(ApiExceptionHandler.class)
class ApiErrorResponseTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderQueryService orderQueryService;

    @Test
    void unexpectedErrorDoesNotExposeInternalDetails() throws Exception {
        given(orderQueryService.getDetail("ORD-1"))
                .willThrow(new IllegalStateException(
                        "SECRET_MARKER database.internal.local"
                ));

        mockMvc.perform(get("/api/orders/ORD-1")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isInternalServerError())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON
                ))
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.detail")
                        .value("Đã xảy ra lỗi. Vui lòng thử lại sau."))
                .andExpect(content().string(
                        not(containsString("SECRET_MARKER"))
                ))
                .andExpect(content().string(
                        not(containsString("database.internal.local"))
                ));
    }
}
~~~

Đây là ví dụ kiểm thử minh họa; tên endpoint, service và cấu hình content type cần khớp dự án. Ngoài body, nên kiểm tra header, redirect location và HTML response nếu ứng dụng có nhiều kênh.

### 16.4. Kiểm thử theo môi trường

Chạy kiểm thử với cấu hình production hoặc cấu hình tương đương để xác minh:

- Stack trace không xuất hiện.
- Message và binding details không bị đưa ra ngoài ngoài chủ đích.
- Whitelabel/developer error page bị tắt nếu không phù hợp.
- Logging nội bộ vẫn ghi nhận được lỗi và trace ID.
- Error handler hoạt động khi database hoặc dịch vụ ngoài không khả dụng.

## 17. Quy trình thiết kế và xử lý lỗi an toàn

Khi bổ sung một luồng lỗi mới, có thể làm theo trình tự:

1. **Xác định nguyên nhân:** lỗi binding, validation, nghiệp vụ, phân quyền, không tìm thấy hay lỗi kỹ thuật.
2. **Chọn status code:** theo ý nghĩa HTTP và hợp đồng của endpoint.
3. **Định nghĩa mã lỗi công khai:** ổn định, không chứa tên lớp hoặc thông tin nội bộ.
4. **Viết thông điệp an toàn:** nói đủ để người dùng hiểu bước tiếp theo.
5. **Chọn kênh phản hồi:** View HTML, redirect, JSON hoặc Problem Details.
6. **Ghi chẩn đoán nội bộ:** trace ID, exception và ngữ cảnh đã làm sạch.
7. **Kiểm tra dữ liệu nhạy cảm:** body, header, URL, cookie, log và error metadata.
8. **Kiểm thử phản hồi:** status, content type, schema và các chuỗi không được phép xuất hiện.
9. **Kiểm tra cấu hình production:** tắt debug detail và xác minh gateway/error page.

Đối với thao tác có thể tạo tác dụng phụ như thanh toán hoặc tạo đơn, cần thêm idempotency và cơ chế kiểm tra trạng thái trước khi hướng dẫn client thử lại.

## 18. Checklist review phản hồi lỗi

- [ ] Client chỉ nhận status, mã lỗi và thông điệp đã được kiểm soát.
- [ ] Không trả stack trace, exception message hoặc cause chain.
- [ ] Không trả SQL, tên bảng, đường dẫn máy chủ, hostname hoặc cấu hình.
- [ ] Không trả password, OTP, cookie, token hoặc dữ liệu cá nhân không cần thiết.
- [ ] HTML và JSON có chiến lược xử lý lỗi phù hợp từng kênh.
- [ ] Mã lỗi công khai không phụ thuộc tên exception nội bộ.
- [ ] Status code phản ánh đúng loại lỗi.
- [ ] Validation response không phản chiếu trường bí mật hoặc rejected value nhạy cảm.
- [ ] Trace ID được tạo/xác thực an toàn và có thể dùng để tra log.
- [ ] Log nội bộ có quyền truy cập, retention và redaction phù hợp.
- [ ] Error page không phụ thuộc database hoặc dịch vụ dễ lỗi.
- [ ] Cấu hình production không hiển thị debug details.
- [ ] Reverse proxy và gateway không trả trang lỗi chi tiết.
- [ ] Test xác minh cả thông tin cần có và thông tin không được phép xuất hiện.

## Kết luận

Ngăn lộ chi tiết kỹ thuật qua phản hồi lỗi là việc giữ ranh giới giữa thông tin công khai và chẩn đoán nội bộ. Trong MVC, Controller hoặc exception handler cần phân loại lỗi, chọn HTTP status, mã lỗi và View/JSON phù hợp; log nội bộ giữ thông tin điều tra với quyền truy cập và redaction thích hợp. Không trả stack trace, SQL, đường dẫn máy chủ, cấu hình, token hoặc exception message cho client. Hãy dùng mã lỗi ổn định, trace ID, Problem Details cho API khi phù hợp, cấu hình production an toàn và kiểm thử nội dung response thực tế. Cách tổ chức này giúp người dùng nhận được hướng dẫn rõ ràng trong khi đội phát triển vẫn có dữ liệu cần thiết để tìm nguyên nhân.
