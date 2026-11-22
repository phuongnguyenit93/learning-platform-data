# Mã lỗi công khai và thông tin chẩn đoán nội bộ trong Spring RSocket

## Mục tiêu

Khi một request thất bại, client cần biết điều gì đã xảy ra và nên làm gì tiếp theo. Đội vận hành cần thêm dữ liệu để tìm nguyên nhân thật trong hệ thống. Hai nhu cầu này có liên quan nhưng không giống nhau: phản hồi công khai phải ổn định, dễ xử lý và không làm lộ cấu trúc nội bộ; bản ghi chẩn đoán phải đủ chi tiết để điều tra, nhưng chỉ dành cho hệ thống và người có quyền truy cập.

Trong ứng dụng Spring Messaging dùng RSocket, hãy thiết kế rõ ba lớp thông tin:

1. **Mã lỗi ứng dụng công khai**: mã ổn định như `ORDER_ALREADY_EXISTS` hoặc `VALIDATION_FAILED`, được client dùng để rẽ nhánh xử lý.
2. **Mã lỗi giao thức RSocket**: mã số trong ERROR frame, mô tả loại lỗi ở tầng protocol.
3. **Thông tin chẩn đoán nội bộ**: exception, stack trace, nguyên nhân gốc, trace/span ID, route và ngữ cảnh vận hành được ghi vào log hoặc hệ thống quan sát.

Không dùng một trường để thay thế cả ba lớp. Đặc biệt, không gửi exception message hoặc stack trace nội bộ như thể đó là hợp đồng API.

## 1. Thiết kế hợp đồng lỗi công khai

Một lỗi công khai nên trả lời những câu hỏi mà client có thể hành động:

- Mã lỗi ổn định là gì?
- Người dùng hoặc chương trình có thể hiểu thông báo nào?
- Lỗi có thể thử lại hay không?
- Nếu dữ liệu đầu vào sai, trường nào cần sửa?
- Có mã tương quan nào để hỗ trợ tra cứu với đội vận hành?

Một cấu trúc JSON minh họa:

~~~json
{
  "status": "ERROR",
  "error": {
    "code": "ORDER_ALREADY_EXISTS",
    "message": "An order with this reference already exists.",
    "correlationId": "01J9Q4V8M5R6T7Y2",
    "retryable": false,
    "details": [
      {
        "field": "reference",
        "code": "DUPLICATE",
        "message": "This reference is already in use."
      }
    ]
  }
}
~~~

Các trường có ý nghĩa riêng:

| Trường | Quy ước |
| --- | --- |
| `status` | Trạng thái của envelope, ví dụ `OK` hoặc `ERROR` |
| `code` | Mã máy đọc được, ổn định qua các phiên bản |
| `message` | Thông báo ngắn, an toàn để hiển thị; không dùng làm khóa logic |
| `correlationId` | Mã opaque để người dùng gửi cho bộ phận hỗ trợ và tìm log liên quan |
| `retryable` | Gợi ý lỗi có khả năng hết khi thử lại hay không |
| `details` | Danh sách chi tiết đã được cho phép công khai, thường dùng cho lỗi validation |

Không bắt buộc mọi lỗi đều có `details`. Chỉ thêm dữ liệu thật sự hữu ích cho client. Không đưa tên class Java, tên bảng, câu SQL, đường dẫn file, hostname nội bộ hoặc thông tin xác thực vào envelope.

### Mã lỗi phải ổn định

Client nên dựa vào `code`, không phân tích nội dung `message`. Thông điệp có thể được chỉnh sửa, dịch hoặc cá nhân hóa; mã lỗi là một phần của hợp đồng tương thích.

Một tập mã ứng dụng thường gặp:

| Mã công khai | Ý nghĩa | Thử lại? |
| --- | --- | --- |
| `VALIDATION_FAILED` | Dữ liệu đầu vào vi phạm quy tắc | Không, cần sửa dữ liệu |
| `AUTHENTICATION_REQUIRED` | Thiếu hoặc thông tin xác thực không hợp lệ | Sau khi xác thực lại |
| `ACCESS_DENIED` | Danh tính hiện tại không có quyền | Không, trừ khi quyền thay đổi |
| `RESOURCE_NOT_FOUND` | Không tìm thấy tài nguyên theo hợp đồng | Thường không |
| `STATE_CONFLICT` | Trạng thái hiện tại không cho phép thao tác | Sau khi tải lại trạng thái hoặc giải quyết xung đột |
| `ORDER_ALREADY_EXISTS` | Mã tham chiếu đơn hàng đã được sử dụng | Không với cùng dữ liệu |
| `RATE_LIMITED` | Vượt giới hạn tốc độ | Có, sau khoảng chờ |
| `DEPENDENCY_UNAVAILABLE` | Dịch vụ phụ thuộc tạm thời không sẵn sàng | Có thể, nếu thao tác an toàn để thử lại |
| `INTERNAL_ERROR` | Lỗi không dự kiến, không có chi tiết công khai | Không tự động, trừ khi chính sách retry cho phép |

Không nên trả mã chung chung như `ERROR` cho mọi tình huống. Ngược lại, cũng không cần tạo một mã riêng cho mọi exception Java. Mã công khai mô tả một tình huống trong hợp đồng ứng dụng, không mô tả tên lớp triển khai.

Khi phát hành phiên bản mới:

- Giữ nguyên ý nghĩa của mã đã công bố.
- Có thể bổ sung mã mới; client phải có nhánh dự phòng cho mã chưa biết.
- Không đổi tên hoặc tái sử dụng mã cũ cho ý nghĩa khác.
- Chỉ thêm trường tùy chọn khi có thể tương thích với client cũ.
- Nếu cần thay đổi cấu trúc lớn, dùng versioning của hợp đồng message một cách rõ ràng.
- Có thể thay đổi câu thông báo mà không buộc client thay đổi logic.

## 2. Phân biệt mã lỗi ứng dụng và mã lỗi RSocket

RSocket có ERROR frame (frame type `0x0B`) để truyền lỗi ở cấp kết nối hoặc cấp stream. ERROR frame chứa Stream ID, mã lỗi protocol và Error Data. Error Data được đặc tả là nội dung UTF-8; đây không phải nơi để gửi toàn bộ đối tượng exception Java.

Các mã protocol chuẩn gồm:

| Mã protocol | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `INVALID_SETUP` | `0x00000001` | SETUP frame không hợp lệ |
| `UNSUPPORTED_SETUP` | `0x00000002` | Tham số SETUP không được hỗ trợ |
| `REJECTED_SETUP` | `0x00000003` | Responder từ chối thiết lập kết nối |
| `REJECTED_RESUME` | `0x00000004` | Không chấp nhận resume |
| `CONNECTION_ERROR` | `0x00000101` | Kết nối bị kết thúc ngay |
| `CONNECTION_CLOSE` | `0x00000102` | Kết nối sẽ đóng sau khi xử lý các stream đang hoạt động |
| `APPLICATION_ERROR` | `0x00000201` | Lỗi ở tầng ứng dụng tạo ra Reactive Streams `onError` |
| `REJECTED` | `0x00000202` | Request hợp lệ nhưng responder từ chối và đảm bảo chưa xử lý |
| `CANCELED` | `0x00000203` | Responder hủy request; xử lý có thể đã bắt đầu và có side effect |
| `INVALID` | `0x00000204` | Request không hợp lệ |

Cần phân biệt `CANCEL` frame với mã lỗi `CANCELED`:

- `CANCEL` là frame do requester gửi để hủy stream đang chờ.
- `CANCELED` là mã trong ERROR frame khi responder hủy request; nó không đảm bảo side effect chưa xảy ra.

`REJECTED` có cam kết mạnh: responder đảm bảo request chưa được xử lý. Chỉ dùng ý nghĩa này nếu ứng dụng thực sự có thể bảo đảm điều đó. Không dùng `REJECTED` cho một lỗi xảy ra sau khi đã ghi dữ liệu hoặc gọi hệ thống phụ thuộc. `CANCELED` cũng không có nghĩa là giao dịch đã rollback.

Protocol dành vùng `0x00000301` đến `0xFFFFFFFE` cho mã lỗi tầng ứng dụng do ứng dụng định nghĩa. Các giá trị protocol chuẩn không nên bị tái sử dụng cho mã nghiệp vụ riêng.

Ví dụ:

- `APPLICATION_ERROR` mô tả loại lỗi protocol.
- `ORDER_ALREADY_EXISTS` mô tả tình huống nghiệp vụ mà client hiểu.
- `correlationId` liên kết phản hồi với log.
- `errorId` hoặc trace ID giúp người vận hành tìm bản ghi chẩn đoán.

Đây là các định danh khác nhau. Nếu dùng mã protocol số tùy chỉnh, hãy lập registry, mô tả ý nghĩa và duy trì tính ổn định xuyên phiên bản. Nếu dùng mã dạng chuỗi trong error envelope, quy ước mã đó ở tầng hợp đồng ứng dụng và không nhầm nó với mã số của ERROR frame.

## 3. Chọn cách biểu diễn lỗi trong RSocket

Có hai cách thiết kế thường gặp. Chọn một quy ước nhất quán cho từng API.

### Cách A: Trả error envelope như payload

Với cách này, cả thành công và thất bại đều là payload theo cùng một schema. Ví dụ, handler thành công trả `ApiResult`; `@MessageExceptionHandler` cũng trả `ApiResult` với `status = ERROR`.

Ưu điểm là client luôn giải mã một kiểu response và đọc được mã lỗi cùng các trường chi tiết có cấu trúc. Nhược điểm là stream protocol hoàn tất bình thường; client phải kiểm tra `status` để nhận biết thất bại. Nếu client bỏ qua bước này, lỗi nghiệp vụ có thể bị hiểu nhầm là thành công.

### Cách B: Dùng RSocket error signal

Với cách này, handler phát sinh lỗi và lỗi đi theo luồng reactive `onError`/RSocket ERROR frame. Client nhận lỗi trong pipeline thay vì nhận một response payload thông thường. Đây là lựa chọn phù hợp khi muốn giữ semantics của Reactive Streams, đặc biệt với stream và channel.

Ưu điểm là lỗi kết thúc interaction theo protocol và được xử lý bằng `onError`. Nhược điểm là chi tiết công khai phụ thuộc vào cách exception được ánh xạ sang protocol error và cách client driver giải mã Error Data. Hãy xác minh hành vi trên đúng phiên bản Spring và RSocket client mà ứng dụng sử dụng.

Không trả một kiểu `ApiError` bất ngờ trong khi client đang chờ một kiểu thành công khác mà không định nghĩa envelope/union rõ ràng. Cũng không nên chuyển mọi exception thành giá trị mặc định hoặc bỏ qua `onError`; làm vậy có thể che giấu lỗi và phá vỡ semantics của stream.

### Quan hệ với @MessageExceptionHandler

Spring Messaging hỗ trợ `@MessageExceptionHandler` để xử lý exception phát sinh từ phương thức `@MessageMapping`. Có thể đặt handler trong cùng controller hoặc dùng `@ControllerAdvice` để áp dụng trên nhiều controller. Các phương thức này hỗ trợ kiểu đối số và giá trị trả về giống phương thức message handler.

Ví dụ dùng envelope:

~~~java
public record FieldIssue(
        String field,
        String code,
        String message) {}

public record ApiError(
        String code,
        String message,
        String correlationId,
        boolean retryable,
        List<FieldIssue> details) {}

public record ApiResult(
        String status,
        Object data,
        ApiError error) {

    public static ApiResult success(Object data) {
        return new ApiResult("OK", data, null);
    }

    public static ApiResult failure(ApiError error) {
        return new ApiResult("ERROR", null, error);
    }
}
~~~

Handler trả cùng envelope cho cả hai nhánh:

~~~java
@Controller
public class OrderResponder {

    private final OrderService orderService;
    private final CorrelationContext correlationContext;

    public OrderResponder(
            OrderService orderService,
            CorrelationContext correlationContext) {
        this.orderService = orderService;
        this.correlationContext = correlationContext;
    }

    @MessageMapping("orders.create")
    public Mono<ApiResult> create(CreateOrder command) {
        return orderService.create(command)
                .map(ApiResult::success);
    }

    @MessageExceptionHandler(OrderAlreadyExistsException.class)
    public Mono<ApiResult> handleDuplicate(
            OrderAlreadyExistsException exception) {

        ApiError error = new ApiError(
                "ORDER_ALREADY_EXISTS",
                "An order with this reference already exists.",
                correlationContext.currentId(),
                false,
                List.of());

        return Mono.just(ApiResult.failure(error));
    }
}
~~~

`CorrelationContext` trong ví dụ là thành phần do ứng dụng cung cấp; nó đọc correlation ID đã được xác thực/chuẩn hóa từ metadata hoặc tracing context. Không phải class có sẵn của Spring. Trong ứng dụng thật, hãy bảo đảm `ApiResult` là response contract chung cho route: client giải mã `ApiResult` cho cả thành công và thất bại rồi kiểm tra `status`.

Ví dụ này biến exception thành payload bình thường. Nếu muốn client nhận reactive error signal, đừng trả `ApiResult.failure(...)`; hãy để lỗi được truyền theo cơ chế RSocket đã chọn và ánh xạ nó ở tầng protocol phù hợp. `@MessageExceptionHandler` không tự biến object trả về thành HTTP status hoặc một mã RSocket protocol tùy chỉnh.

## 4. Ánh xạ exception sang mã công khai

Không nên để mỗi controller tự quyết định mã lỗi theo cách khác nhau. Đặt quy tắc phân loại ở một lớp rõ ràng, chẳng hạn error mapper hoặc exception advice dùng chung.

Ví dụ phân loại:

| Nhóm lỗi nội bộ | Mã công khai | Thông tin có thể trả về |
| --- | --- | --- |
| Constraint violation | `VALIDATION_FAILED` | Field, mã constraint và thông báo đã chuẩn hóa |
| Thiếu thông tin xác thực | `AUTHENTICATION_REQUIRED` | Hướng dẫn xác thực lại |
| Không đủ quyền | `ACCESS_DENIED` | Thông báo chung, không tiết lộ quyền/role nội bộ |
| Không tìm thấy entity | `RESOURCE_NOT_FOUND` | Loại tài nguyên và định danh công khai nếu an toàn |
| Trùng khóa hoặc sai trạng thái | `STATE_CONFLICT` | Hành động tiếp theo như tải lại trạng thái |
| Rate limit | `RATE_LIMITED` | Khoảng chờ nếu có thể cung cấp chính xác |
| Backend timeout/unavailable | `DEPENDENCY_UNAVAILABLE` | Thông báo dịch vụ tạm thời không sẵn sàng |
| Exception không dự kiến | `INTERNAL_ERROR` | Thông báo chung và correlation ID |

Một quy tắc quan trọng: phân loại theo ngữ nghĩa mà client cần, không theo package hoặc tên exception. Ví dụ, nhiều exception database khác nhau có thể cùng ánh xạ thành `STATE_CONFLICT`; client không cần biết hệ thống dùng PostgreSQL, MongoDB hay một dịch vụ khác.

Trình tự xử lý gợi ý:

1. Bắt các lỗi nghiệp vụ đã biết và ánh xạ sang mã công khai tương ứng.
2. Chuyển lỗi validation thành danh sách field issue đã được lọc.
3. Nhận diện lỗi tạm thời từ dependency và chỉ đánh dấu retryable khi có căn cứ.
4. Với exception không dự kiến, trả `INTERNAL_ERROR` cùng correlation ID.
5. Ghi nguyên nhân chi tiết vào log nội bộ với quyền truy cập phù hợp.

Không dùng `exception.getMessage()` làm `message` công khai. Message của exception thường được viết cho lập trình viên, có thể chứa dữ liệu đầu vào, tên bảng, URL nội bộ hoặc chi tiết hệ thống. Dùng thông điệp được định nghĩa sẵn cho từng mã công khai.

## 5. Retry, idempotency và hành vi client

Trường `retryable` chỉ là gợi ý chính sách, không phải lời hứa rằng retry sẽ thành công. Client nên kết hợp mã lỗi, loại interaction, tính idempotent và giới hạn retry.

- **Lỗi validation hoặc authorization:** sửa dữ liệu hoặc quyền trước khi gửi lại; không retry vô hạn.
- **Conflict:** tải lại trạng thái hoặc yêu cầu người dùng giải quyết xung đột; retry nguyên request cũ thường không giúp ích.
- **Rate limit hoặc dependency unavailable:** có thể retry sau khoảng chờ, với exponential backoff và jitter.
- **Internal error:** mặc định không retry tự động nếu chưa xác định thao tác an toàn và có chính sách retry.
- **Timeout hoặc mất kết nối:** kết quả xử lý có thể chưa rõ. Không được giả định server chưa thực hiện side effect.

Với lệnh tạo đơn hàng, thanh toán hoặc cập nhật trạng thái, dùng idempotency key hoặc mã yêu cầu duy nhất để server nhận biết lần gửi lặp. Ghi nhận idempotency key và kết quả trong cùng ranh giới transaction phù hợp. Nếu client retry sau timeout, server có thể trả lại kết quả của lần xử lý trước thay vì thực hiện lại thao tác.

Trong RSocket:

- Request-Response có thể trả một response hoặc kết thúc bằng error.
- Request-Stream và Channel có thể đã phát ra một số payload trước khi lỗi kết thúc stream; các payload đó không tự động bị thu hồi.
- Fire-and-Forget không có response payload để client nhận lỗi nghiệp vụ đồng bộ. Nếu client cần biết request được chấp nhận, dùng Request-Response hoặc thiết kế một acknowledgement/receipt rõ ràng.
- Hủy subscription không đồng nghĩa nghiệp vụ đã rollback. Hãy thiết kế transaction và idempotency độc lập với vòng đời stream.

Client Spring có thể quan sát lỗi trong reactive pipeline:

~~~java
return requester.route("orders.create")
        .data(command)
        .retrieveMono(OrderAccepted.class)
        .doOnError(error ->
                log.warn("RSocket request failed; route=orders.create"));
~~~

Đoạn code chỉ minh họa điểm quan sát `onError`; trong thực tế cần log correlation/trace ID và phân loại lỗi theo exception mà client driver thực sự phát ra. Không log raw payload hoặc access token. Nếu API dùng envelope, client phải đọc kiểu envelope đã thỏa thuận và kiểm tra `status` trước khi lấy dữ liệu thành công.

## 6. Ghi thông tin chẩn đoán nội bộ

Thông tin nội bộ giúp trả lời các câu hỏi: lỗi xảy ra ở route nào, khi nào, trong trace nào, exception nào là nguyên nhân gốc, dependency nào liên quan và request đã đi đến bước nào.

Một bản ghi có cấu trúc thường có:

| Trường nội bộ | Mục đích |
| --- | --- |
| `timestamp` | Thời điểm sự kiện |
| `level` | Mức độ nghiêm trọng |
| `event` | Tên sự kiện ổn định, ví dụ `rsocket_request_failed` |
| `route` | Route RSocket đã xử lý |
| `interactionType` | Request-Response, Stream, Channel hoặc Fire-and-Forget |
| `correlationId` | Liên kết log giữa các thành phần |
| `traceId`, `spanId` | Truy vết distributed trace |
| `errorId` | ID của sự cố hoặc bản ghi lỗi nếu hệ thống dùng riêng |
| `exceptionType` | Loại exception nội bộ |
| `causeChain` | Nguyên nhân gốc và các lớp bọc exception |
| `dependency` | Tên dịch vụ phụ thuộc nếu có |
| `durationMs` | Thời gian xử lý |
| `outcome` | Thành công, lỗi, timeout, cancellation hoặc rejection |

Dùng structured logging thay cho ghép chuỗi tự do. Ví dụ với SLF4J:

~~~java
log.error(
        "rsocket_request_failed errorId={} route={} publicCode={} traceId={}",
        errorId,
        route,
        "INTERNAL_ERROR",
        traceId,
        exception);
~~~

Truyền exception ở đối số cuối giúp logger ghi stack trace vào log nội bộ. Chỉ ghi nó vào sink được kiểm soát quyền truy cập, retention và quy trình bảo vệ dữ liệu phù hợp. Với lỗi nghiệp vụ dự kiến như duplicate hoặc validation, có thể ghi ở mức phù hợp mà không cần stack trace cho từng request; tránh tạo log noise.

Không ghi nguyên payload theo mặc định. Payload có thể chứa mật khẩu, token, thông tin cá nhân, dữ liệu thanh toán hoặc nội dung do người dùng kiểm soát. Nếu cần dữ liệu để chẩn đoán, hãy ghi các thuộc tính allow-list đã được chuẩn hóa, che hoặc băm định danh phù hợp. Loại bỏ secret, access token, session ID, connection string, encryption key và dữ liệu nhạy cảm. Chuẩn hóa ký tự điều khiển như CR/LF để tránh log injection.

Không ghi stack trace hoặc exception message nội bộ vào error envelope, RSocket Error Data hay message hiển thị cho người dùng. Chỉ công khai correlation ID opaque và thông điệp đã được kiểm duyệt. Người dùng cung cấp correlation ID cho support; nhân viên được cấp quyền dùng nó để tìm log, trace và errorId tương ứng.

## 7. Correlation ID và distributed tracing

Correlation ID liên kết một thao tác từ client qua nhiều thành phần. Trace ID và span ID thuộc mô hình distributed tracing; chúng có thể bổ sung cho correlation ID nhưng không nhất thiết thay thế nó.

Một luồng triển khai:

1. Client tạo hoặc nhận một request ID duy nhất cho thao tác.
2. Client gửi ID qua metadata theo quy ước của ứng dụng; nếu dùng W3C Trace Context, truyền trace context theo instrumentation tương thích.
3. Server kiểm tra định dạng, giới hạn chiều dài và ký tự cho phép. Metadata từ client là dữ liệu không tin cậy; không dùng nó để xác thực hoặc cấp quyền.
4. Nếu thiếu hoặc sai định dạng, server tạo correlation ID mới.
5. Đưa ID vào context được truyền qua reactive pipeline và các lời gọi downstream.
6. Gắn ID vào log, trace và error envelope công khai.
7. Client gửi ID này cho support để tra cứu.

Không dùng một ThreadLocal tùy tiện để truyền context qua Reactor; execution có thể chuyển thread. Ưu tiên cơ chế context propagation/tracing được framework và instrumentation hỗ trợ. Không để client tự chọn giá trị tùy ý làm trace identity hoặc ghi đè thông tin trace tin cậy.

Correlation ID không phải secret và không phải credential. Người biết ID không được có thêm quyền đọc log hoặc truy cập tài nguyên. Hệ thống quan sát vẫn phải kiểm tra quyền truy cập độc lập.

## 8. Bảo mật và quyền riêng tư khi trả lỗi

Lỗi công khai là một phần bề mặt tấn công. Thông báo quá chi tiết có thể giúp người gọi dò tìm tài nguyên, cấu trúc hạ tầng, tên bảng hoặc cách triển khai.

Áp dụng các nguyên tắc:

- Trả cùng một thông báo an toàn cho những tình huống mà việc phân biệt sẽ tiết lộ sự tồn tại của tài nguyên hoặc danh tính.
- Không trả stack trace, exception class, SQL, câu lệnh nội bộ, file path, hostname, địa chỉ IP riêng hoặc cấu hình.
- Không phản chiếu nguyên văn input không tin cậy vào response hoặc log.
- Giới hạn số lượng field errors và độ dài message để tránh response/log quá lớn.
- Không đưa token, mật khẩu, cookie, session identifier hoặc secret vào log.
- Kiểm soát quyền truy cập, thời hạn lưu và khả năng xuất dữ liệu của log/tracing.
- Ghi nhận các lỗi xác thực, phân quyền, deserialization và hành vi bất thường theo chính sách giám sát.
- Bảo đảm nội dung lỗi có thể được localize mà không thay đổi mã lỗi.

Với validation, chỉ trả tên field thuộc hợp đồng công khai và mã constraint đã chuẩn hóa. Tránh trả message mặc định chứa thông tin do validator hoặc framework tạo ra nếu nó chưa được rà soát.

## 9. Kiểm thử hợp đồng lỗi

Kiểm thử cả nội dung trả về và hành vi của interaction:

1. **Mapping unit test:** mỗi exception nghiệp vụ được ánh xạ đúng public code, message, retryable và details.
2. **Fallback test:** exception không dự kiến luôn trả `INTERNAL_ERROR`; response không chứa exception message, stack trace hoặc dữ liệu nhạy cảm.
3. **Controller test:** `@MessageExceptionHandler` hoặc `@ControllerAdvice` được gọi và tạo đúng envelope.
4. **RSocket integration test:** client dùng `RSocketRequester` gửi request qua route thật và kiểm tra payload envelope hoặc error signal theo contract đã chọn.
5. **Stream test:** lỗi giữa stream kết thúc stream theo quy ước; client không giả định các phần tử đã nhận sẽ được thu hồi.
6. **Retry test:** retry chỉ diễn ra với lỗi được đánh dấu phù hợp; lệnh không idempotent không tạo side effect lặp.
7. **Observability test:** correlation ID xuất hiện trong log/trace liên quan và có thể dùng để tra cứu; payload bí mật không xuất hiện trong log.
8. **Compatibility test:** client cũ xử lý được mã lỗi chưa biết và các trường tùy chọn mới.

Đừng chỉ kiểm tra rằng client nhận được một exception. Hãy kiểm tra chính xác mã công khai, schema, mức độ lộ thông tin, hành vi retry và việc chẩn đoán nội bộ vẫn tìm được nguyên nhân.

## 10. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng exception message làm mã lỗi | Mã thay đổi theo code hoặc phiên bản thư viện | Dùng public code ổn định |
| Trả stack trace cho client | Lộ cấu trúc và dữ liệu nội bộ | Chỉ log stack trace ở sink được bảo vệ |
| Dùng mã RSocket protocol làm mã nghiệp vụ | Trộn tầng transport và domain | Tách protocol code khỏi application code |
| Dùng `REJECTED` sau khi đã xử lý một phần | Client hiểu nhầm rằng không có side effect | Chỉ dùng REJECTED khi bảo đảm chưa xử lý |
| Retry mọi `onError` | Tạo tải lặp hoặc side effect trùng | Phân loại lỗi và dùng idempotency key |
| Chuyển lỗi thành payload nhưng client không kiểm tra `status` | Thất bại bị hiểu là thành công | Dùng envelope thống nhất và kiểm tra trạng thái |
| Log toàn bộ request | Lộ token, PII và dữ liệu bí mật | Structured logging với allow-list và redaction |
| Dùng correlation ID làm cơ chế bảo mật | Có thể bị giả mạo hoặc lạm dụng | Dùng xác thực/phân quyền riêng |
| Dùng một mã `INTERNAL_ERROR` cho mọi lỗi nhưng không lưu context | Khó tìm nguyên nhân thực | Gắn errorId, traceId, route và cause trong log nội bộ |

## 11. Checklist triển khai

- [ ] Public error code có tên ổn định, ý nghĩa được tài liệu hóa và không tái sử dụng.
- [ ] Protocol error code được phân biệt với application/domain code.
- [ ] Error envelope có schema nhất quán cho thành công và thất bại nếu chọn payload envelope.
- [ ] `@MessageExceptionHandler` hoặc `@ControllerAdvice` ánh xạ lỗi tại tầng Spring Messaging.
- [ ] Exception không dự kiến được chuyển thành thông báo chung, an toàn.
- [ ] Retryable phản ánh đúng tính tạm thời và tính idempotent của thao tác.
- [ ] Correlation ID được kiểm tra, tạo mới khi cần và truyền qua reactive context.
- [ ] Trace/span ID và errorId được ghi vào log/tracing phù hợp.
- [ ] Stack trace và nguyên nhân gốc chỉ nằm trong hệ thống chẩn đoán nội bộ được bảo vệ.
- [ ] Không log payload, token, PII hoặc secret theo mặc định.
- [ ] Đã kiểm thử Request-Response, Stream, Channel và Fire-and-Forget theo đúng hợp đồng.
- [ ] Client xử lý mã lỗi chưa biết và không phụ thuộc vào message text.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): mô hình interaction và hỗ trợ RSocket của Spring Messaging.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration của `RSocketMessageHandler`, `@ControllerAdvice` và `RSocketRequester`.
- [Spring Framework — Annotated Controllers: @MessageExceptionHandler](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): phạm vi exception handler, giá trị trả về và `@ControllerAdvice` trong Spring Messaging.
- [RSocket Protocol — ERROR frame](https://rsocket.io/about/protocol/): error frame, mã protocol chuẩn, Error Data và semantics của REJECTED/CANCELED/INVALID.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại bỏ, che hoặc bảo vệ trong log.

