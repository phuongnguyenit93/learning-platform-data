# Phân biệt thông báo cho người dùng và thông tin chẩn đoán

## Mục tiêu

Khi một thao tác trong ứng dụng MVC thất bại, hệ thống thường cần truyền thông tin đến hai nhóm đối tượng. Người dùng cần biết điều gì đã xảy ra và có thể làm gì tiếp theo. Nhóm phát triển hoặc vận hành cần đủ dữ liệu kỹ thuật để tìm nguyên nhân, đánh giá ảnh hưởng và khắc phục sự cố.

Hai nhu cầu này có mục đích khác nhau. Nếu hiển thị nguyên exception, câu SQL hoặc stack trace cho người dùng, ứng dụng có thể làm lộ thông tin nội bộ và khiến thông báo khó hiểu. Nếu log chỉ ghi một câu chung chung như “Có lỗi xảy ra”, nhóm vận hành lại không có đủ bằng chứng để điều tra.

Bài học này trình bày cách tách thông báo hướng người dùng khỏi thông tin chẩn đoán, cách thiết kế mã lỗi, ghi log có cấu trúc, liên kết request với log bằng correlation ID, xử lý exception trong MVC và bảo vệ dữ liệu nhạy cảm. Ví dụ sử dụng Java và Spring.

Sau khi học, người học có thể:

- Giải thích mục đích và đối tượng nhận của hai loại thông tin lỗi.
- Viết thông báo ngắn gọn, an toàn và có hướng xử lý.
- Thiết kế error code ổn định, độc lập với nội dung đã dịch.
- Ghi thông tin chẩn đoán đủ để điều tra mà không làm lộ bí mật.
- Ánh xạ lỗi trong Controller và exception handler theo từng loại client.
- Dùng request ID hoặc trace ID để liên kết phản hồi với log.
- Kiểm thử nội dung hiển thị, log và chính sách bảo vệ dữ liệu.

## 1. Hai loại thông tin phục vụ hai mục đích

Một lỗi có thể cần hai cách diễn đạt khác nhau.

**Thông báo cho người dùng (user-facing message)** giúp người đang sử dụng ứng dụng hiểu kết quả của thao tác. Thông báo nên trả lời được những câu hỏi thực tế: thao tác có thành công không, điều gì cần sửa hoặc thử lại, và người dùng có cần liên hệ hỗ trợ hay không.

**Thông tin chẩn đoán (diagnostic information)** giúp người phát triển và vận hành xác định nguyên nhân kỹ thuật. Nó có thể gồm loại exception, stack trace, service hoặc dependency liên quan, request ID, trạng thái transaction, mã lỗi nội bộ và các thuộc tính có ích khác.

Ví dụ, khi dịch vụ thanh toán bên ngoài không phản hồi:

| Loại thông tin | Nội dung phù hợp |
|---|---|
| Thông báo cho người dùng | “Chưa thể xử lý thanh toán lúc này. Vui lòng thử lại sau ít phút. Mã tham chiếu: RQ-7F31.” |
| Thông tin chẩn đoán | Timeout khi gọi payment provider, endpoint nội bộ, thời lượng 5 giây, mã request, exception cause, phiên bản dịch vụ và trạng thái retry |

Người dùng không cần biết tên host nội bộ, cấu trúc package, câu lệnh SQL hoặc lớp Java đã ném exception. Nhóm vận hành cần những chi tiết đó khi chúng có ích cho điều tra.

### Không dùng một thông điệp cho mọi đối tượng

Một thông báo chung như “Lỗi hệ thống” có thể an toàn nhưng không giúp người dùng biết nên làm gì. Ngược lại, đưa toàn bộ nội dung exception vào giao diện có thể làm lộ cấu trúc nội bộ và khiến người dùng hiểu sai vấn đề.

Hãy tạo hai đầu ra từ cùng một lỗi đã được phân loại:

    Request
       |
       v
    Controller / Application
       |
       v
    Error classification
       |
       +----------------------+
       |                      |
       v                      v
    User response         Diagnostic event
       |                      |
       v                      v
    HTML / JSON           Log / Trace / Alert
    message + code        exception + context

Hai đầu ra có thể chia sẻ error code hoặc request ID để liên kết với nhau, nhưng nội dung và mức chi tiết phải phù hợp với người nhận.

## 2. Xác định thông báo hướng người dùng cần trả lời điều gì

Thông báo tốt không chỉ nói rằng đã xảy ra lỗi. Nó cần giúp người dùng quyết định bước tiếp theo.

Một thông báo thường có ba phần:

1. **Kết quả:** thao tác đã thất bại, chưa hoàn tất hoặc đang được xử lý.
2. **Hướng dẫn:** người dùng nên sửa dữ liệu, kiểm tra quyền, thử lại hay chờ kết quả.
3. **Mã tham chiếu:** nếu cần hỗ trợ, cung cấp một mã để đội vận hành tra cứu.

Ví dụ:

| Tình huống | Thông báo phù hợp |
|---|---|
| Email sai định dạng | “Vui lòng nhập địa chỉ email hợp lệ.” |
| Phiên đăng nhập hết hạn | “Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.” |
| Tài nguyên không tồn tại | “Không tìm thấy đơn hàng này hoặc bạn không thể truy cập đơn hàng.” |
| Xung đột trạng thái | “Đơn hàng đã thay đổi. Hãy tải lại trang để xem trạng thái mới.” |
| Dịch vụ tạm thời không khả dụng | “Dịch vụ đang bận. Vui lòng thử lại sau. Mã tham chiếu: RQ-7F31.” |
| Lỗi không dự kiến | “Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại hoặc liên hệ hỗ trợ với mã tham chiếu.” |

### Nói rõ hành động tiếp theo

Thông báo “Dữ liệu không hợp lệ” quá chung nếu ứng dụng có thể chỉ rõ trường cần sửa. Thông báo “Không thể thực hiện” cũng chưa đủ nếu người dùng có thể giải quyết bằng cách tải lại dữ liệu hoặc đăng nhập lại.

Tuy nhiên, không phải mọi lỗi đều có thể giải thích chi tiết. Nếu việc tiết lộ tài nguyên có tồn tại hay không tạo ra rủi ro bảo mật, có thể dùng cùng một thông báo cho cả trường hợp không tồn tại và không có quyền truy cập.

### Tránh đổ lỗi cho người dùng

Dùng câu mô tả trạng thái hoặc hướng dẫn cụ thể. Tránh thông báo như “Bạn đã làm sai” hoặc “Request của bạn bị lỗi”. Người dùng cần biết điều gì cần sửa, không cần bị quy trách nhiệm.

### Phân biệt lỗi với trạng thái bình thường

Không phải mọi kết quả không như mong muốn đều là lỗi kỹ thuật. Ví dụ:

- Khóa học đã đủ chỗ là một kết quả nghiệp vụ dự kiến.
- Tìm kiếm không có kết quả là một trạng thái rỗng hợp lệ.
- Người dùng chưa có quyền là một kết quả kiểm soát truy cập.
- Database mất kết nối ngoài dự kiến là lỗi hạ tầng.

Việc phân loại đúng giúp chọn thông điệp, status HTTP, log level và cơ chế cảnh báo phù hợp.

## 3. Thông tin chẩn đoán cần có gì?

Thông tin chẩn đoán cần giúp trả lời: lỗi xảy ra ở đâu, trong request nào, khi nào, ảnh hưởng đến thành phần nào và có thể tái hiện hay không.

Tùy loại lỗi, log có thể gồm:

- Thời điểm xảy ra và mức độ nghiêm trọng.
- Tên sự kiện hoặc error code nội bộ.
- Request ID, trace ID hoặc correlation ID.
- HTTP method và route template.
- Tên use case hoặc application service.
- Loại exception và stack trace.
- Dependency liên quan, chẳng hạn database hoặc payment provider.
- Thời gian xử lý và số lần retry.
- Trạng thái transaction hoặc kết quả thao tác nếu biết chắc.
- Phiên bản ứng dụng, môi trường triển khai và instance xử lý.

Không phải mọi log đều cần mọi trường. Một lỗi validation thường không cần stack trace. Một timeout ở dependency có thể cần thời lượng, tên dependency và số lần retry. Một lỗi không dự kiến có thể cần stack trace để xác định vị trí phát sinh.

### Ghi dữ kiện, không chỉ ghi kết luận

Log như “Lỗi thanh toán” không đủ để điều tra. Một bản ghi tốt có thể nêu sự kiện và các thuộc tính quan trọng:

    {
      "level": "ERROR",
      "event": "payment_provider_timeout",
      "requestId": "rq-7f31",
      "useCase": "CreatePayment",
      "dependency": "payment-provider",
      "durationMs": 5000,
      "attempt": 2,
      "exceptionType": "SocketTimeoutException"
    }

Đây là ví dụ về cấu trúc, không phải một log thực tế. Hãy dùng tên trường và mã sự kiện nhất quán để công cụ log có thể lọc, nhóm và thống kê.

### Không ghi log mọi exception ở mọi tầng

Nếu Controller, Application Service, Repository và global exception handler đều ghi cùng một exception, một lỗi sẽ tạo nhiều bản ghi trùng nhau. Điều này làm tăng chi phí và khiến việc đếm sự cố sai lệch.

Thông thường, tầng có đủ ngữ cảnh để quyết định lỗi cần được ghi nhận nên chịu trách nhiệm ghi log. Các tầng thấp hơn có thể bổ sung ngữ cảnh bằng cách ném exception có nguyên nhân gốc hoặc trả kết quả lỗi rõ ràng, thay vì log rồi ném tiếp cùng lỗi.

Không bắt exception rồi bỏ qua. Nếu xử lý được lỗi, hãy chuyển nó thành kết quả hoặc fallback có chủ đích; nếu không xử lý được, hãy để nó đi đến ranh giới xử lý phù hợp.

## 4. Thiết kế error code ổn định

Error code là định danh máy đọc được cho một loại lỗi. Nó giúp client và nhóm vận hành nhận diện lỗi mà không phụ thuộc câu chữ hoặc ngôn ngữ hiển thị.

Ví dụ:

| Error code | Ý nghĩa | Thông báo tiếng Việt có thể dùng |
|---|---|---|
| VALIDATION_FAILED | Dữ liệu đầu vào không đáp ứng hợp đồng | “Vui lòng kiểm tra lại các trường được đánh dấu.” |
| RESOURCE_NOT_FOUND | Không tìm thấy hoặc không thể tiết lộ tài nguyên | “Không tìm thấy nội dung được yêu cầu.” |
| ACCESS_DENIED | Người dùng không được phép thực hiện thao tác | “Bạn không có quyền thực hiện thao tác này.” |
| STATE_CONFLICT | Trạng thái hiện tại không cho phép thao tác | “Dữ liệu đã thay đổi. Vui lòng tải lại và thử lại.” |
| DEPENDENCY_UNAVAILABLE | Dịch vụ phụ thuộc tạm thời không khả dụng | “Dịch vụ đang bận. Vui lòng thử lại sau.” |
| INTERNAL_ERROR | Lỗi không dự kiến | “Đã xảy ra lỗi. Vui lòng liên hệ hỗ trợ nếu vấn đề tiếp tục.” |

Error code nên:

- Ổn định qua các lần thay đổi câu chữ.
- Có ý nghĩa rõ ràng và không trùng lặp.
- Được tài liệu hóa cho client nếu client cần xử lý theo mã.
- Không chứa thông tin nhạy cảm hoặc chi tiết triển khai.
- Được ánh xạ nhất quán sang status HTTP và thông báo phù hợp.

Không dùng tên class exception làm error code công khai. Việc đổi tên class nội bộ không nên buộc client thay đổi. Có thể có mã lỗi nội bộ chi tiết hơn mã công khai; hai mã này không nhất thiết giống nhau.

### Tách mã lỗi và bản dịch

Không nên dùng câu thông báo tiếng Việt làm khóa điều kiện trong frontend. Cùng một error code có thể được hiển thị bằng nhiều ngôn ngữ:

    errorCode = "VALIDATION_FAILED"
    message.vi = "Vui lòng kiểm tra lại dữ liệu."
    message.en = "Please review the submitted information."

Với server-side rendering, message có thể được lấy từ message bundle theo locale. Với API, có thể trả error code và một thông điệp mặc định, hoặc để client dịch theo catalog đã công bố. Hãy chọn một quy ước và giữ nhất quán.

## 5. Ánh xạ lỗi trong kiến trúc MVC

Lỗi có thể xuất hiện ở nhiều tầng:

- Binding hoặc validation khi đọc request.
- Application Service khi điều phối use case.
- Domain Model khi một hành vi vi phạm bất biến.
- Repository khi truy vấn hoặc lưu dữ liệu thất bại.
- Adapter khi gọi dịch vụ bên ngoài.
- View rendering hoặc serialization khi tạo response.

Mỗi tầng nên diễn đạt lỗi ở mức phù hợp với trách nhiệm của nó. Controller hoặc exception handler tại ranh giới web chuyển lỗi thành HTTP response và thông báo cho người dùng.

### Luồng xử lý lỗi

    HTTP request
         |
         v
    Controller
         |
         v
    Application Service
         |
         +----> Domain / Repository / Adapter
         |                  |
         |                  v
         |              Exception
         |                  |
         +<-----------------+
         |
         v
    Web exception handler
         |
         +-------------------------+
         |                         |
         v                         v
    User-facing response      Diagnostic log
    status + code + message   exception + context
         |                         |
         v                         v
    HTML / JSON               Log / Trace system

Application layer không nên trả trực tiếp HttpStatus hoặc ResponseEntity. Nó có thể ném exception chuyên biệt hoặc trả một result type. Web adapter chịu trách nhiệm ánh xạ sang HTTP.

### Ví dụ exception nghiệp vụ

    public class CourseFullException extends RuntimeException {
        public CourseFullException() {
            super("Course capacity reached");
        }
    }

Application Service hoặc domain có thể ném exception này khi điều kiện sức chứa không được đáp ứng. Chuỗi message trong exception ở đây phục vụ nội bộ; Controller không nên mặc định trả nguyên chuỗi đó cho client.

### Xử lý tập trung bằng Spring

Với API, có thể dùng @RestControllerAdvice để chuyển lỗi thành response thống nhất:

    public record ApiError(
            String code,
            String message,
            String requestId) {
    }

    @RestControllerAdvice
    public class ApiExceptionHandler {
        private static final Logger log =
                LoggerFactory.getLogger(ApiExceptionHandler.class);

        @ExceptionHandler(CourseFullException.class)
        ResponseEntity<ApiError> handleCourseFull(
                CourseFullException exception,
                HttpServletRequest request) {

            String requestId = request.getAttribute("requestId") == null
                    ? "unknown"
                    : request.getAttribute("requestId").toString();

            ApiError body = new ApiError(
                    "STATE_CONFLICT",
                    "Khóa học đã đủ chỗ. Vui lòng chọn khóa học khác.",
                    requestId);

            return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
        }

        @ExceptionHandler(Exception.class)
        ResponseEntity<ApiError> handleUnexpected(
                Exception exception,
                HttpServletRequest request) {

            String requestId = request.getAttribute("requestId") == null
                    ? "unknown"
                    : request.getAttribute("requestId").toString();

            log.error(
                    "Unhandled request failure requestId={}",
                    requestId,
                    exception);

            ApiError body = new ApiError(
                    "INTERNAL_ERROR",
                    "Đã xảy ra lỗi khi xử lý yêu cầu. Mã tham chiếu: "
                            + requestId,
                    requestId);

            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(body);
        }
    }

Đây là ví dụ minh họa. Trong ứng dụng thật, request ID nên được tạo và lưu ở một filter/interceptor dùng chung, thay vì tự tạo trong từng handler. Cần tránh xử lý lại exception đã được framework ánh xạ hoặc ghi log trùng lặp. Các lỗi validation, không tìm thấy và không có quyền nên có handler hoặc cơ chế ánh xạ riêng phù hợp với hợp đồng.

### HTML và JSON cần cách trình bày khác nhau

Một lỗi validation trong form HTML thường trả lại cùng template, kèm lỗi cạnh trường. API JSON trả status và error representation để client tự hiển thị. Cùng một loại lỗi nghiệp vụ có thể được trình bày theo hai cách khác nhau tùy client.

Không nên để một exception handler toàn cục luôn trả JSON cho mọi request nếu ứng dụng cũng phục vụ HTML. Có thể tách advice theo package, controller type hoặc media type, hoặc để handler trả representation phù hợp với loại endpoint.

## 6. Dùng request ID và correlation ID để nối hai đầu thông tin

Thông báo hướng người dùng có thể cung cấp một mã tham chiếu. Nhóm vận hành dùng mã đó để tìm log liên quan mà không cần người dùng gửi stack trace hoặc dữ liệu nhạy cảm.

Một request ID thường định danh một request đơn lẻ. Correlation ID có thể được dùng để liên kết nhiều thao tác thuộc cùng một luồng nghiệp vụ. Trace ID thường được hệ thống tracing phân phối dùng để liên kết các span qua nhiều service.

Các khái niệm này có thể được triển khai cùng nhau nhưng không nên tùy tiện coi chúng là một giá trị duy nhất:

| Định danh | Phạm vi thường gặp | Mục đích |
|---|---|---|
| Request ID | Một request đến một service | Tìm log của request đó |
| Correlation ID | Một luồng nghiệp vụ qua nhiều request/service | Liên kết các hoạt động liên quan |
| Trace ID | Một distributed trace | Xem quan hệ và thời gian của các span |

### Luồng sử dụng request ID

1. Filter nhận request và kiểm tra header định danh theo chính sách.
2. Nếu không có ID hợp lệ, server tạo một ID mới.
3. ID được đặt vào request context và logging context.
4. Mọi log trong quá trình xử lý có thể ghi cùng ID.
5. Response trả ID trong header hoặc error body.
6. Người dùng có thể cung cấp mã đó khi liên hệ hỗ trợ.

Không nên tin tưởng mù quáng một header do client gửi. Nếu cho phép client cung cấp correlation ID, cần giới hạn độ dài, ký tự và tránh dùng nó làm dữ liệu xác thực. Một request ID do server tạo sẽ dễ kiểm soát hơn.

### Ví dụ filter đơn giản

    public class RequestIdFilter extends OncePerRequestFilter {
        private static final String HEADER = "X-Request-Id";

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String requestId = UUID.randomUUID().toString();

            try {
                MDC.put("requestId", requestId);
                request.setAttribute("requestId", requestId);
                response.setHeader(HEADER, requestId);
                chain.doFilter(request, response);
            } finally {
                MDC.remove("requestId");
            }
        }
    }

Ví dụ này luôn tạo ID mới để đơn giản hóa. Nếu hệ thống cần tiếp nhận ID từ gateway, hãy xác thực và chuẩn hóa header đó theo một quy tắc rõ ràng. MDC phải được dọn trong finally vì thread có thể được tái sử dụng cho request khác. Với tác vụ bất đồng bộ, logging context cần được truyền qua executor theo cơ chế phù hợp; không giả định MDC tự động đi theo mọi thread.

### Không đưa mã tham chiếu vào làm lộ thông tin

Request ID nên là giá trị ngẫu nhiên hoặc không thể đoán theo cách có thể truy cập tài nguyên. Nó chỉ giúp tìm log, không phải token truy cập, mã xác nhận danh tính hoặc bằng chứng người dùng có quyền xem dữ liệu.

## 7. Ghi log có cấu trúc và chọn log level

Log có cấu trúc lưu sự kiện dưới dạng các trường riêng biệt thay vì chỉ một chuỗi tự do. Công cụ log có thể lọc theo event, request ID, service, exception type hoặc dependency.

Ví dụ với SLF4J:

    private static final Logger log =
            LoggerFactory.getLogger(PaymentService.class);

    log.warn(
            "Payment provider returned a retryable response requestId={} providerCode={}",
            requestId,
            providerCode);

    log.error(
            "Payment provider call failed requestId={} durationMs={}",
            requestId,
            durationMs,
            exception);

Khi dùng backend hỗ trợ JSON logging, các placeholder và thuộc tính có thể được xuất thành field riêng. Không cần tự nối một JSON string bằng tay.

### Chọn mức độ log

| Level | Dùng khi | Ví dụ |
|---|---|---|
| TRACE | Cần chi tiết rất sâu trong điều tra tạm thời | Dòng xử lý nội bộ có chọn lọc |
| DEBUG | Thông tin phát triển hoặc chẩn đoán chi tiết | Nhánh xử lý được chọn, tham số không nhạy cảm |
| INFO | Sự kiện vận hành bình thường có ý nghĩa | Use case hoàn tất, tác vụ nền bắt đầu |
| WARN | Bất thường có thể xử lý hoặc chưa gây gián đoạn nghiêm trọng | Retry thành công, dependency tạm thời chậm |
| ERROR | Thao tác thất bại cần điều tra hoặc can thiệp | Transaction thất bại, request không hoàn thành do lỗi không dự kiến |

Không nên log mọi lỗi validation ở mức ERROR. Người dùng nhập sai dữ liệu là tình huống thường gặp và thường được phản hồi bằng 4xx. Có thể thống kê bằng metric hoặc log mức DEBUG/INFO có chọn lọc nếu cần phân tích xu hướng.

Lỗi hạ tầng lặp lại có thể cần cảnh báo dựa trên tỷ lệ, thời lượng hoặc số lần thất bại, thay vì chỉ dựa vào một bản ghi ERROR đơn lẻ.

### Ghi log một lần ở nơi có đủ ngữ cảnh

Một exception có thể đi qua nhiều tầng. Nếu mỗi tầng log stack trace rồi ném tiếp, cùng một lỗi sẽ xuất hiện nhiều lần. Hãy chọn một ranh giới chịu trách nhiệm ghi nhận lỗi cuối cùng, thường là exception handler hoặc nơi xử lý tác vụ nền. Tầng thấp hơn chỉ log khi nó xử lý một tình huống riêng và không ném tiếp cùng lỗi theo cách gây trùng.

Với lỗi được chuyển thành kết quả dự kiến, không cần ghi stack trace như lỗi không dự kiến. Có thể ghi một event nghiệp vụ ở mức phù hợp.

## 8. Bảo vệ dữ liệu cá nhân và bí mật trong log

Diagnostic information không đồng nghĩa với việc ghi mọi thứ hệ thống biết. Log thường được lưu lâu, tập trung ở nền tảng dùng chung và có nhiều người truy cập. Vì vậy, dữ liệu log cần được giảm thiểu và bảo vệ.

Không ghi:

- Mật khẩu hoặc mã PIN.
- Access token, refresh token, session ID hoặc cookie xác thực.
- Khóa API, private key hoặc secret.
- Toàn bộ thông tin thẻ thanh toán.
- Request body chứa dữ liệu cá nhân nếu không thực sự cần.
- Nội dung tệp tải lên.
- Stack trace hoặc cấu hình nội bộ vào response công khai.

Cẩn trọng với email, số điện thoại, địa chỉ, mã định danh cá nhân, thông tin sức khỏe và dữ liệu tài chính. Nếu cần đối chiếu, hãy cân nhắc dùng ID nội bộ, dữ liệu đã che bớt hoặc giá trị giả danh hóa theo chính sách.

Ví dụ:

| Dữ liệu đầu vào | Ghi log phù hợp hơn |
|---|---|
| Email đầy đủ | User ID hoặc email đã che bớt nếu thực sự cần |
| Authorization header | Không ghi giá trị header |
| Thông tin thẻ | Payment reference do hệ thống tạo |
| Nội dung tìm kiếm | Chỉ ghi nếu cần cho vận hành và đã đánh giá quyền riêng tư |
| Request body lớn | Ghi kích thước, loại request và request ID |

### Che dữ liệu không phải giải pháp cho mọi trường hợp

Masking như thay một phần email bằng dấu sao có thể giảm rủi ro nhưng vẫn có thể nhận diện người dùng. Hãy ưu tiên không thu thập dữ liệu không cần thiết. Nếu log cần chứa dữ liệu cá nhân, xác định mục đích, thời hạn lưu, quyền truy cập và quy trình xóa theo chính sách tổ chức.

### Giới hạn quyền truy cập log

Log có thể chứa thông tin nội bộ có giá trị cao. Cần:

- Chỉ cấp quyền cho người cần điều tra hoặc vận hành.
- Bảo vệ log khi truyền và khi lưu.
- Có audit trail cho truy cập dữ liệu log nhạy cảm.
- Đặt thời hạn lưu và cơ chế xóa.
- Ngăn log injection bằng cách xử lý ký tự xuống dòng và dữ liệu không tin cậy phù hợp với logger/format.
- Không để log công khai qua endpoint hoặc file tĩnh.

## 9. Không tiết lộ chi tiết kỹ thuật trong response

Thông tin phản hồi gửi ra ngoài cần được kiểm soát. Một response lỗi không nên chứa:

- Tên lớp Java hoặc package nội bộ.
- Stack trace.
- Câu SQL và tên bảng.
- Đường dẫn file hệ thống.
- Host, IP hoặc tên dịch vụ nội bộ không cần thiết.
- Nội dung exception thô từ thư viện bên ngoài.
- Thông tin cấu hình hoặc secret.
- Giá trị dữ liệu nhạy cảm của người dùng khác.

Ví dụ response không an toàn:

    {
      "error": "org.hibernate.exception.SQLGrammarException",
      "message": "select * from customer where email='...'",
      "stackTrace": "com.example.internal.CustomerRepository..."
    }

Response an toàn hơn:

    {
      "code": "INTERNAL_ERROR",
      "message": "Đã xảy ra lỗi khi xử lý yêu cầu.",
      "requestId": "rq-7f31"
    }

Thông tin kỹ thuật chi tiết được giữ trong hệ thống chẩn đoán với quyền truy cập phù hợp. Người dùng có thể cung cấp request ID để đội hỗ trợ tìm đúng bản ghi.

### Không xác nhận sự tồn tại của tài nguyên nhạy cảm

Trong một số hệ thống, trả “Tài khoản này tồn tại nhưng bạn không có quyền” có thể giúp kẻ tấn công dò danh sách tài khoản. Có thể dùng thông báo chung và status phù hợp theo chính sách bảo mật. Quyết định này phụ thuộc threat model và hợp đồng sản phẩm.

### Không hiển thị thông điệp exception từ nhà cung cấp

Thông điệp từ database, payment provider hoặc thư viện có thể chứa URL nội bộ, tên bảng, mã tài khoản hoặc dữ liệu request. Hãy ánh xạ sang error code và câu chữ do ứng dụng kiểm soát.

## 10. Phân loại lỗi để chọn cách phản hồi và chẩn đoán

Một phân loại rõ ràng giúp ứng dụng tránh dùng cùng một cách xử lý cho mọi lỗi.

| Nhóm lỗi | Ví dụ | Phản hồi người dùng | Chẩn đoán |
|---|---|---|---|
| Validation | Email sai định dạng | Nêu trường cần sửa | Field, constraint, request ID; thường không cần stack trace |
| Authentication | Token hết hạn | Yêu cầu đăng nhập lại | Loại xác thực thất bại, không ghi token |
| Authorization | Không có quyền sửa tài nguyên | Thông báo không có quyền hoặc không tìm thấy theo chính sách | Actor ID nội bộ, resource ID nếu an toàn, policy bị từ chối |
| Business conflict | Đơn hàng đã được xử lý | Nêu trạng thái hiện tại và bước tiếp theo | Use case, aggregate/version, error code |
| Dependency failure | Database hoặc API ngoài không khả dụng | Thông báo tạm thời, có thể thử lại | Dependency, timeout, retry count, exception cause |
| Unexpected defect | Null pointer hoặc lỗi lập trình | Thông báo chung và request ID | Stack trace, release version, trace ID |
| Client cancellation | Người dùng đóng kết nối | Thường không cần thông báo lỗi mới | Ghi nhận có chọn lọc nếu ảnh hưởng vận hành |

Không phải lỗi nào cũng cần log ở mức ERROR. Một request bị client hủy có thể là hành vi bình thường. Một lần retry thành công có thể là WARN hoặc metric tùy mức độ. Hãy chọn theo tác động thực tế và chính sách vận hành.

## 11. Liên kết lỗi với tracing và monitoring

Log giúp xem sự kiện riêng lẻ. Metrics cho thấy xu hướng và tỷ lệ. Distributed tracing cho biết một request đi qua các thành phần nào và mất thời gian ở đâu. Ba loại dữ liệu bổ sung cho nhau.

### Logs

Dùng để xem chi tiết một lần xảy ra lỗi: exception, request ID, tham số an toàn và hành động đã thực hiện.

### Metrics

Dùng để theo dõi số lượng hoặc tỷ lệ, ví dụ:

- Số request trả 5xx theo phút.
- Tỷ lệ timeout của payment provider.
- Số lần retry.
- Thời gian phản hồi p95/p99.
- Số lỗi validation theo endpoint.

Không gắn ID người dùng, request ID hoặc dữ liệu có cardinality cao vào metric label. Điều đó có thể làm hệ thống metrics tăng số chuỗi thời gian rất lớn. Dùng metric label có tập giá trị giới hạn như service, route template, status class hoặc error category.

### Tracing

Trace liên kết các span của một request qua gateway, web service, database và dịch vụ ngoài. Trace ID có thể được ghi cùng log để chuyển từ dashboard sang log hoặc ngược lại.

Không phải mọi ứng dụng MVC đơn giản đều cần một hệ thống tracing phân tán. Có thể bắt đầu bằng request ID và structured logging; thêm tracing khi ứng dụng có nhiều service hoặc cần điều tra latency xuyên hệ thống.

### Alert theo tác động

Cảnh báo nên phản ánh ảnh hưởng đến người dùng hoặc mục tiêu vận hành, chẳng hạn tỷ lệ 5xx vượt ngưỡng trong một khoảng thời gian, latency tăng kéo dài hoặc dependency quan trọng không khả dụng. Một exception đơn lẻ không phải lúc nào cũng cần đánh thức người trực vận hành.

## 12. Thiết kế thông báo cho HTML và API

Cùng một lỗi có thể được trình bày khác nhau tùy loại client.

### Form HTML

Với lỗi validation, trả lại template và gắn lỗi với trường. Với lỗi nghiệp vụ như khóa học đã đóng, có thể hiển thị thông báo ở đầu form hoặc trang chi tiết. Với lỗi không dự kiến, render trang lỗi thân thiện có request ID.

Thông báo nên được đặt ở vị trí dễ nhận biết, có ngữ nghĩa HTML phù hợp và không chỉ dựa vào màu sắc. Nếu lỗi xuất hiện cạnh trường, liên kết nó với input bằng label và thuộc tính hỗ trợ accessibility.

### REST API

API nên trả status, error code và body có cấu trúc. Có thể dùng Problem Details theo RFC 9457 hoặc một error DTO riêng đã được công bố. Nếu dùng request ID, hãy nhất quán giữa header và body.

Ví dụ Problem Details có phần mở rộng:

    {
      "type": "https://api.example.test/problems/internal-error",
      "title": "Request failed",
      "status": 500,
      "detail": "Đã xảy ra lỗi khi xử lý yêu cầu.",
      "requestId": "rq-7f31"
    }

Không nên đưa stack trace vào extension field. API có thể cung cấp đường dẫn tài liệu lỗi công khai nếu điều đó giúp client hiểu cách xử lý.

### Đồng nhất giữa nhiều kênh

Nếu cùng một use case được gọi từ HTML Controller và REST Controller, hãy dùng cùng error code nội bộ hoặc application error type. Mỗi adapter chịu trách nhiệm chuyển thành message và representation phù hợp. Điều này tránh việc cùng một lỗi có ý nghĩa khác nhau chỉ vì client gọi endpoint khác.

## 13. Kiểm thử thông báo và thông tin chẩn đoán

Kiểm thử cần xác nhận cả hai đầu ra: người dùng nhận đúng thông tin, còn log có đủ ngữ cảnh mà không làm lộ dữ liệu nhạy cảm.

| Tình huống | Kiểm tra thông báo | Kiểm tra chẩn đoán |
|---|---|---|
| Validation thất bại | Hiển thị đúng trường và hướng sửa | Không log stack trace như lỗi hệ thống |
| Không có quyền | Không tiết lộ tài nguyên nếu chính sách yêu cầu | Ghi nhận loại từ chối và request ID an toàn |
| Dependency timeout | Thông báo tạm thời và mã tham chiếu | Có dependency, duration, retry và exception |
| Lỗi không dự kiến | Message chung, không có chi tiết nội bộ | Stack trace và trace/request ID được ghi |
| Lỗi lặp | Không tạo thông báo gây hoang mang liên tục | Metrics/alert thể hiện tỷ lệ và xu hướng |
| Request chứa token | Không trả lại token | Log không chứa token hoặc cookie |

### Unit test cho error mapping

Có thể kiểm tra mapper chuyển application error thành error code và thông báo:

    @Test
    void mapsCourseFullToPublicConflictMessage() {
        ApiError error = errorMapper.toApiError(
                new CourseFullException(),
                "rq-7f31");

        assertEquals("STATE_CONFLICT", error.code());
        assertEquals("rq-7f31", error.requestId());
        assertFalse(error.message().contains("CourseFullException"));
    }

### Controller test

Với MockMvc, kiểm tra status, body và header:

    mockMvc.perform(post("/api/courses/{id}/registrations", courseId))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("STATE_CONFLICT"))
        .andExpect(jsonPath("$.requestId").exists())
        .andExpect(jsonPath("$.message").exists())
        .andExpect(content().string(
                not(containsString("stackTrace"))));

Tên field và status trong test phải khớp hợp đồng thực tế của ứng dụng.

### Kiểm thử log

Có thể dùng appender kiểm thử hoặc log capture để xác nhận:

- Event có request ID.
- Exception không bị mất khi cần điều tra.
- Không có authorization header, password hoặc token trong log.
- Một exception không bị ghi stack trace lặp ở nhiều tầng.
- Log level phù hợp với nhóm lỗi.

Không nên chỉ kiểm tra rằng “có một log”. Hãy kiểm tra các trường chẩn đoán quan trọng và việc dữ liệu nhạy cảm đã được loại bỏ.

## 14. Các sai lầm thường gặp

### Trả nguyên exception cho client

Điều này có thể làm lộ cấu trúc nội bộ và dữ liệu nhạy cảm. Hãy dùng error code và thông điệp công khai do ứng dụng kiểm soát.

### Chỉ trả một thông báo chung

“Có lỗi xảy ra” không giúp người dùng sửa dữ liệu hoặc biết có nên thử lại. Hãy nêu hướng hành động phù hợp và mã tham chiếu khi cần.

### Log thiếu ngữ cảnh

Một dòng “Database error” không cho biết request nào, thao tác nào hoặc dependency nào gặp lỗi. Hãy thêm request ID, use case và tên dependency an toàn.

### Ghi toàn bộ request body

Request body có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc nội dung tệp. Chỉ ghi những trường đã được đánh giá là cần thiết và an toàn.

### Ghi exception ở mọi tầng

Log trùng làm nhiễu điều tra và tăng chi phí. Chọn một nơi chịu trách nhiệm ghi nhận lỗi cuối cùng; bổ sung ngữ cảnh qua exception hoặc structured fields.

### Dùng message làm logic

Frontend không nên so sánh chuỗi “Khóa học đã đủ chỗ” để quyết định hành vi. Hãy dùng error code ổn định và để message phục vụ hiển thị.

### Hiển thị thông tin khác nhau gây lộ dữ liệu

Thông báo “tài khoản không tồn tại” khác với “mật khẩu sai” có thể hỗ trợ dò tài khoản. Cần xem xét chính sách thông báo theo rủi ro của endpoint.

### Không dọn logging context

MDC hoặc context gắn với thread có thể bị giữ lại khi thread được tái sử dụng. Luôn dọn context trong finally và truyền context có chủ đích qua tác vụ bất đồng bộ.

## 15. Quy trình thiết kế một luồng xử lý lỗi

Khi bổ sung xử lý lỗi cho endpoint hoặc use case, có thể đi theo trình tự:

1. Liệt kê các lỗi có thể xảy ra ở binding, validation, domain, persistence và dependency.
2. Phân biệt kết quả nghiệp vụ dự kiến với lỗi kỹ thuật không dự kiến.
3. Đặt error code ổn định cho các loại lỗi cần công khai hoặc giám sát.
4. Viết thông báo hướng người dùng với bước tiếp theo phù hợp.
5. Xác định diagnostic fields cần ghi và nơi chịu trách nhiệm ghi log.
6. Tạo request ID hoặc sử dụng trace ID để liên kết response với log.
7. Ánh xạ lỗi ở Controller hoặc exception advice theo loại client.
8. Loại bỏ secret và dữ liệu cá nhân không cần thiết khỏi response và log.
9. Chọn log level, metric và alert theo tác động thực tế.
10. Kiểm thử thông báo, status, error code, log context và dữ liệu bị che/loại bỏ.

## 16. Checklist trước khi đưa xử lý lỗi vào sử dụng

- Thông báo hướng người dùng dễ hiểu và có bước tiếp theo.
- Error code ổn định, độc lập với câu chữ và ngôn ngữ.
- Không trả stack trace, câu SQL hoặc exception message thô.
- Diagnostic log có request ID hoặc trace ID khi phù hợp.
- Log có đủ ngữ cảnh để xác định use case và dependency.
- Exception không bị ghi trùng ở nhiều tầng.
- Password, token, cookie và dữ liệu nhạy cảm không xuất hiện trong log.
- Log level phản ánh đúng tính chất lỗi.
- HTML và API nhận representation phù hợp.
- Request ID không được dùng làm token xác thực hoặc quyền truy cập.
- Logging context được dọn sau request và truyền đúng qua tác vụ bất đồng bộ.
- Test xác nhận cả thông báo công khai lẫn thông tin chẩn đoán.

## Kết luận

Thông báo cho người dùng và thông tin chẩn đoán là hai đầu ra khác nhau của cùng một tình huống lỗi. Thông báo hướng người dùng cần rõ ràng, an toàn và giúp họ biết bước tiếp theo. Thông tin chẩn đoán cần đủ ngữ cảnh để nhóm phát triển và vận hành tìm nguyên nhân, nhưng phải giảm thiểu dữ liệu cá nhân và bí mật.

Trong MVC, application/domain layer diễn đạt lỗi theo ý nghĩa của use case; Controller hoặc exception handler ánh xạ lỗi thành HTML hoặc API response; logging và tracing lưu thông tin kỹ thuật ở kênh nội bộ. Error code ổn định cùng request ID giúp liên kết hai đầu ra mà không phải tiết lộ stack trace cho người dùng. Khi các trách nhiệm này được tách rõ, ứng dụng vừa dễ sử dụng vừa dễ vận hành và điều tra sự cố.
