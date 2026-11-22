# Để exception message trở thành định dạng dữ liệu mà mã khác phải phân tích — một sai lầm trong Java

> **Phạm vi:** Java Core → Exception → Sai lầm thường gặp. Bài học giải thích vì sao `Throwable.getMessage()` thường là nội dung dành cho người đọc chứ không phải giao thức ổn định dành cho phần mềm; cách chuyển từ `contains`/`startsWith`/regex trên message sang **kiểu ngoại lệ, error code, các trường có kiểu, nguyên nhân gốc và result type**. Bao gồm ví dụ Java 17 chạy được, hợp đồng API, kiểm thử và chiến lược migration.

## 1. Một câu chữ có thể làm thay đổi cả logic nghiệp vụ

Giả sử một dịch vụ thanh toán gặp lỗi từ chối giao dịch và caller xử lý:

~~~java
// Phản ví dụ; charge() và respond... là các hàm do ứng dụng định nghĩa.
try {
    charge();
} catch (RuntimeException ex) {
    if (ex.getMessage().contains("DECLINED")) {
        return respondPaymentDeclined();
    }
    return respondInternalError();
}
~~~

Với message `"Payment DECLINED for pay-17"`, caller xử lý “bị từ chối”. Nhưng cùng loại lỗi với message `"Thanh toán bị từ chối: pay-17"`, `"Payment was declined"` hoặc `"Card issuer rejected request"` lại có thể bị phân loại thành lỗi hệ thống. Một thay đổi **câu chữ chẩn đoán** đã trở thành thay đổi **hành vi chương trình**.

Đây là anti-pattern **exception message as data contract**: không có trường `errorCode` được công bố, không có schema hay policy tương thích; một tầng vô tình dùng `getMessage()` như định dạng dữ liệu của tầng khác. Lỗi có thể ảnh hưởng HTTP status, retry, UI, cảnh báo, idempotency hoặc quyết định có đảo ngược giao dịch hay không.

**Nguyên tắc:** message phục vụ diễn giải và chẩn đoán; dữ liệu chương trình phải được định nghĩa và tiêu thụ bằng hợp đồng **có cấu trúc và có kiểu**.

## 2. Vì sao getMessage không phải một error code?

`Throwable` là một đối tượng chứa thông tin về lỗi. Những phần của nó có mục đích khác nhau:

| Thuộc tính | Ý nghĩa | Cách sử dụng đúng |
|---|---|---|
| Kiểu Java của exception | Phân loại theo hợp đồng API | `catch (SpecificException ex)`, `instanceof` |
| `getMessage()` | Câu mô tả lỗi, thường hướng tới người đọc | Hiển thị/chẩn đoán sau khi kiểm soát dữ liệu |
| `getLocalizedMessage()` | Mô tả có thể tùy biến theo ngôn ngữ | Không dùng quyết định logic máy |
| `getCause()` | Liên kết lỗi nguyên nhân khi được bọc | Theo dõi nguyên nhân, phân loại kiểu cause khi hợp đồng cho phép |
| `getStackTrace()` | Dấu vết thực thi | Debug, log; không dùng số dòng/tên file làm business code |
| `getSuppressed()` | Lỗi phụ bị suppress, ví dụ lỗi đóng tài nguyên | Chẩn đoán và cleanup; không parse text thành code |
| Trường `code`/`id` do custom exception định nghĩa | Dữ liệu domain có contract | Phân loại, mapping API, correlation |

JDK không có quy tắc chung rằng message của mọi `IllegalArgumentException`, `SQLException` hay `NumberFormatException` giữ nguyên qua các phiên bản. Nếu nhà cung cấp chỉ tài liệu hóa **loại exception và điều kiện ném**, caller không nên tự nâng một câu message thành API contract.

Điều này **không có nghĩa message vô ích**. Message tốt vẫn mô tả thao tác, điều kiện thất bại và context an toàn để con người điều tra. Nó chỉ không phải nguồn chân lý cho nhánh máy đọc, trừ khi nhà cung cấp chính thức định nghĩa grammar ổn định.

## 3. Những cách parse text dễ hỏng

### Dùng contains hoặc startsWith

~~~java
// Chỉ minh họa anti-pattern.
if (ex.getMessage().startsWith("ORDER_NOT_FOUND")) {
    // ...
}
~~~

Các thay đổi prefix, chữ hoa-thường, dấu cách, locale hoặc tầng wrapper đều có thể làm lệch kết quả. Nếu message null, lời gọi `contains` còn có thể ném `NullPointerException` và che lỗi ban đầu.

### Dùng split để lấy business ID

~~~java
// Không nên làm nguồn dữ liệu chính.
String paymentId = ex.getMessage().split(":")[1];
~~~

Message có thể thêm dấu hai chấm, xuống dòng, ID chứa delimiter hoặc thiếu phần tử; parser có thể tạo ID sai, `ArrayIndexOutOfBoundsException` hoặc dữ liệu không an toàn.

### Dùng regex để lấy một con số

~~~java
// Mã minh họa: regex phụ thuộc câu chữ.
java.util.regex.Matcher m =
        java.util.regex.Pattern.compile("row (\d+)").matcher(ex.getMessage());
~~~

Kể cả regex hợp lệ, câu `"row 12 invalid"` có thể trở thành `"invalid record at line 12"`. Nếu vị trí hàng quan trọng, API nên có `rowNumber()` hoặc một `ValidationError` có field `position`, không bắt caller phân tích message.

### Dựa vào lời mô tả của dependency

Bản mới của thư viện có thể đổi `"Connection refused"` thành `"Failed to connect"` hoặc bọc ngoại lệ bằng message khác. Không nên dùng từ `"refused"` trong text để quyết định retry. Nếu SDK có HTTP status, vendor error code hoặc subtype chính thức, dùng những thuộc tính đó.

## 4. Ví dụ Java 17 hoàn chỉnh: bad vs good khi đổi message

Ví dụ sau mô phỏng cùng lỗi thanh toán bị từ chối nhưng hai câu message khác nhau. Cách sai đọc text, còn cách đúng đọc `FailureCode` và giữ `cause` của lỗi kỹ thuật.

Lưu thành **`ExceptionMessageContractDemo.java`**:

~~~java
import java.util.Objects;

public class ExceptionMessageContractDemo {
    enum FailureCode {
        PAYMENT_DECLINED,
        PROVIDER_UNAVAILABLE
    }

    static final class PaymentFailure extends RuntimeException {
        private final FailureCode code;
        private final String paymentId;

        PaymentFailure(FailureCode code, String paymentId,
                       String description, Throwable cause) {
            super(description, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.paymentId = Objects.requireNonNull(paymentId, "paymentId");
        }

        FailureCode code() {
            return code;
        }

        String paymentId() {
            return paymentId;
        }
    }

    static int fragileHttpStatus(RuntimeException error) {
        // Sai: dựa vào thông điệp thay vì phân loại có cấu trúc.
        return error.getMessage().contains("DECLINED") ? 402 : 500;
    }

    static int stableHttpStatus(PaymentFailure error) {
        return switch (error.code()) {
            case PAYMENT_DECLINED -> 402;
            case PROVIDER_UNAVAILABLE -> 503;
        };
    }

    static String publicCode(PaymentFailure error) {
        return switch (error.code()) {
            case PAYMENT_DECLINED -> "payment_declined";
            case PROVIDER_UNAVAILABLE -> "provider_unavailable";
        };
    }

    public static void main(String[] args) {
        RuntimeException english =
                new IllegalStateException("Payment DECLINED for pay-17");
        RuntimeException vietnamese =
                new IllegalStateException("Thanh toán bị từ chối: pay-17");

        System.out.println("bad English: " + fragileHttpStatus(english));
        System.out.println("bad Vietnamese: " + fragileHttpStatus(vietnamese));

        PaymentFailure typed = new PaymentFailure(
                FailureCode.PAYMENT_DECLINED,
                "pay-17",
                "Thanh toán bị từ chối: pay-17",
                new IllegalStateException("gateway response 05"));

        System.out.println("good status: " + stableHttpStatus(typed));
        System.out.println("good code: " + publicCode(typed));
        System.out.println("good paymentId: " + typed.paymentId());

        Throwable cause = typed.getCause();
        System.out.println("good cause: "
                + cause.getClass().getSimpleName()
                + ": " + cause.getMessage());
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac ExceptionMessageContractDemo.java
java ExceptionMessageContractDemo
~~~

**Stdout chính xác:**

~~~text
bad English: 402
bad Vietnamese: 500
good status: 402
good code: payment_declined
good paymentId: pay-17
good cause: IllegalStateException: gateway response 05
~~~

Diễn giải:

1. `fragileHttpStatus` chỉ nhận diện chữ `DECLINED` tiếng Anh viết hoa. Bản tiếng Việt dẫn đến `500`, dù sự kiện nghiệp vụ không thay đổi.
2. `PaymentFailure` chứa mã lỗi ở enum `FailureCode` và định danh `paymentId` trong hai trường typed.
3. `stableHttpStatus` đọc `error.code()`. Khi cải thiện hoặc bản địa hóa message, quyết định không thay đổi.
4. `publicCode` ánh xạ enum nội bộ thành mã lỗi public có contract rõ nghĩa.
5. `getCause()` giữ exception kỹ thuật gốc mà tầng logging có thể dùng để điều tra; tầng HTTP không cần parse `"gateway response 05"`.
6. Mã trạng thái `402` chỉ minh họa **chính sách của API trong ví dụ**, không khẳng định mọi hệ thống thanh toán đều phải dùng HTTP 402. Ứng dụng thật chọn status dựa trên hợp đồng HTTP/domain đã công bố.
7. Không có framework hoặc thread nền trong chương trình; output ổn định, giúp tập trung vào thiết kế lỗi.

## 5. Typed exception: loại lỗi, mã và context riêng

Khi API vẫn cần ném exception, có thể mô hình hóa thông tin máy đọc bằng một lớp có trường riêng:

~~~java
// Trích đoạn khai báo Java 17; có thể đặt trong một lớp/top-level file.
enum OrderErrorCode {
    NOT_FOUND, ALREADY_PAID, STORAGE_UNAVAILABLE
}

final class OrderOperationException extends RuntimeException {
    private final OrderErrorCode code;
    private final String orderId;

    OrderOperationException(
            OrderErrorCode code, String orderId, Throwable cause) {
        super("order operation failed", cause);
        this.code = java.util.Objects.requireNonNull(code);
        this.orderId = orderId;
    }

    OrderErrorCode code() { return code; }
    String orderId() { return orderId; }
}
~~~

Ở đây `getMessage()` có thể đổi từ `"order operation failed"` sang `"unable to process order"` mà không phá việc đọc `code()` hoặc `orderId()`. Dùng constructor có `cause` đảm bảo trace của lỗi gốc không bị cắt bỏ.

Tuy nhiên, thêm quá nhiều subclass cho mọi error code cũng làm hierarchy khó quản lý. Có thể dùng một số exception type có ý nghĩa abstraction, kèm enum `code` cho phân loại chi tiết. Với API public giữa nhiều dịch vụ, mã lỗi dạng string có schema/version và khả năng xử lý mã chưa biết thường linh hoạt hơn một enum đồng bộ cứng.

### Bảo toàn ngữ nghĩa ở đúng tầng

- Repository biết lỗi kỹ thuật: `SQLException`, I/O exception, driver code.
- Service biết ngữ nghĩa domain: đơn hàng không tồn tại, thanh toán bị từ chối, nguồn phụ thuộc không khả dụng.
- Boundary biết cách map sang HTTP/queue/job outcome và thông điệp public an toàn.

Đừng buộc controller phân tích `SQLException.getMessage()` để quyết định trạng thái HTTP. Repository/service nên chuyển lỗi vào abstraction có cấu trúc, giữ `cause` và thông tin cần điều tra.

## 6. Có phải luôn nên dùng catch theo subtype?

`catch (SpecificException ex)` là cách có kiểu rõ ràng, phù hợp khi thư viện công bố subtype để phân biệt lỗi. Ví dụ:

~~~java
// Trích đoạn minh họa; các lớp/hàm thuộc ứng dụng giả định.
try {
    repository.load(orderId);
} catch (OrderNotFoundException ex) {
    return respondNotFound();
} catch (StorageUnavailableException ex) {
    return respondUnavailable();
}
~~~

Nếu nhiều mã lỗi nằm trong cùng loại domain exception, dùng `switch (ex.code())` có thể tốt hơn tạo nhiều class rỗng:

~~~java
// Trích đoạn; OrderOperationException đã được khai báo ở trên.
switch (ex.code()) {
    case NOT_FOUND -> respondNotFound();
    case ALREADY_PAID -> respondConflict();
    case STORAGE_UNAVAILABLE -> respondUnavailable();
}
~~~

Cần phân biệt **nguyên nhân thật** và **quyết định xử lý**. Một `TimeoutException` không tự bảo đảm tác vụ phía ngoài chưa commit; chính sách retry còn tùy idempotency, attempt budget và trạng thái hệ thống bên ngoài. Một message có chữ “timeout” càng không đủ để quyết định điều đó.

## 7. Result type cho tình huống bị từ chối thường xuyên

Với các kết quả dự kiến của UI/validation/import, exception đôi khi không phải kênh tốt nhất. Dùng sealed result type của Java 17:

~~~java
// Các khai báo kiểu minh họa trong một chương trình Java 17.
sealed interface ParseResult permits Accepted, Rejected { }

record Accepted(int value) implements ParseResult { }

enum RejectReason {
    EMPTY, NOT_A_NUMBER, OUT_OF_RANGE
}

record Rejected(RejectReason reason) implements ParseResult { }
~~~

Caller có thể xử lý theo `Rejected.reason()` thay vì ném `NumberFormatException` rồi parse message để biết “ký tự thứ 7 không hợp lệ”. Nếu cần vị trí, thêm một record field `int position`. Với kết quả chỉ cần có/không, `OptionalInt` hoặc `Optional<T>` có thể đơn giản hơn.

Đừng thay exception bằng `null` hoặc một string chung `"error"` và xem là đã giải quyết: điều đó thường tạo một hợp đồng còn mơ hồ. Mục tiêu là **biểu diễn chính xác thông tin caller cần xử lý**.

## 8. Message có thể thay đổi vì bản địa hóa

Một mã lỗi nên ổn định bất kể locale:

~~~text
code=payment_declined
vi-VN: "Phương thức thanh toán bị từ chối."
en-US: "The payment method was declined."
~~~

Việc thay bản dịch không được khiến `retryable`, HTTP status hay loại outcome đổi theo. Không viết:

~~~java
// Phản ví dụ.
if (ex.getLocalizedMessage().contains("từ chối")) {
    // Quyết định chính sách dựa trên ngôn ngữ hiển thị.
}
~~~

Thay vào đó, định nghĩa catalog `errorCode + locale → displayMessage` hoặc dùng `ResourceBundle`/i18n service ở boundary. Message hiển thị cho người dùng và message nội bộ có thể khác nhau. Đừng trả nguyên message của lỗi SQL, token hay path nội bộ ra API response.

## 9. Đừng parse message của JDK và thư viện

Ví dụ `Integer.parseInt(input)` ném `NumberFormatException` nếu chuỗi sai. Nếu cần biết chính input để hiển thị lỗi, bạn **đã có input**; không cần regex trích lại từ `ex.getMessage()`.

Với JDBC, `SQLException` có `getSQLState()` và `getErrorCode()` ngoài `getMessage()`. Các mã này cần được diễn giải theo contract SQLState/vendor và cấu hình triển khai, nhưng chúng có chủ đích hơn việc regex vào lời mô tả của driver.

Với HTTP client/SDK, dùng response status, provider error code hoặc typed error body khi được hỗ trợ. Một số thư viện không công bố mã máy đọc; trong trường hợp đó, hãy tìm API thích hợp hoặc đặt một adapter giới hạn rủi ro thay vì cho cả ứng dụng phụ thuộc vào wording.

**Không tự suy ra mã ổn định chỉ vì có chuỗi hoặc số.** Error code cũng cần tài liệu, mapping, version và policy đối với code mới.

## 10. Tạo response API với code ổn định và message có thể thay đổi

Một response JSON có cấu trúc nên tách:

~~~json
{
  "code": "payment_declined",
  "message": "Không thể thanh toán bằng phương thức đã chọn.",
  "requestId": "req-42",
  "details": {
    "paymentId": "pay-17"
  }
}
~~~

Đây là schema **minh họa** với ID giả. `code` dành cho client phân loại; `message` dành cho hiển thị; `requestId` giúp hỗ trợ điều tra; `details` là các trường có schema được phép công khai.

**Không ghép JSON bằng string từ `ex.getMessage()`**: câu chữ có thể chứa dấu nháy, newline, ký tự điều khiển hoặc thông tin nhạy cảm. Dùng serializer/JSON library hỗ trợ escape và schema versioning. Không công bố Throwable, stack trace, cause hay SQL nguyên văn cho client.

Phân biệt lỗi nội bộ với response public: mã public có thể đủ ổn định cho hệ sinh thái client, còn exception class/stack trace phục vụ chẩn đoán phía server.

## 11. Khi nào được phép parse một chuỗi lỗi?

Một chuỗi **có thể** là giao thức nếu nhà cung cấp **công bố grammar máy đọc rõ ràng**. Ví dụ một tool có output protocol versioned, một CSV lỗi với escaping chính thức hoặc một `message` mà contract nói rõ nó chứa structured encoding.

Điều kiện tối thiểu:

- Có tài liệu schema, version và cách mã hóa/escape.
- Có kiểm thử malformed input và unknown fields.
- Có chính sách tương thích khi thêm/sửa trường.
- Không thay grammar theo locale ngoài điều đã công bố.
- Có giới hạn kích thước và kiểm tra dữ liệu không đáng tin.
- Không có API typed tốt hơn bị bỏ qua.

Nếu một thư viện chỉ mô tả message là “một chuỗi mô tả exception”, không được tự suy ra đó là contract có thể parse. Nếu bắt buộc tích hợp một thư viện legacy chỉ trả text, hãy cô lập parser ở **một adapter** cùng test hồi quy theo phiên bản, không cho mọi service parse riêng. Không dùng parser mỏng manh này cho quyết định thanh toán/rollback quan trọng khi có thể tránh.

## 12. Logging: đọc structured fields, không regex trên message

Một sự kiện log có thể mang:

~~~json
{
  "event": "payment_failed",
  "operation": "authorize_payment",
  "requestId": "req-42",
  "paymentId": "pay-17",
  "errorCode": "payment_declined",
  "exceptionType": "PaymentFailure",
  "causeType": "IllegalStateException"
}
~~~

Log trên là **mẫu**, không phải stdout chương trình. Một structured logger nên xuất `errorCode`, operation và ID thành các trường độc lập, đồng thời ghi `Throwable` để giữ stack/cause. Không cần gửi nguyên exception vào text field rồi dùng regex lấy lại error code.

Không tạo label metric theo `getMessage()`: message có ID động, URL và dữ liệu thay đổi, gây cardinality cao và có thể lộ thông tin. Metric nên nhóm theo `operation`, `errorCode`, `dependency` hoặc nhóm ổn định; request ID thuộc log/tracing.

Nếu lỗi đi qua nhiều tầng, tránh ghi cùng stack trace ở repository, service và controller nếu mỗi tầng chỉ log rồi throw. Tầng dưới nên chuyển loại lỗi có cause; tầng sở hữu kết quả cuối log sự kiện đủ context. Các sự kiện retry/compensation riêng vẫn có thể có log độc lập khi cần.

## 13. Bảo mật: thông điệp exception không phải dữ liệu public an toàn

`Throwable.getMessage()` đôi khi chứa:

- API key hoặc access token nằm trong URL.
- Connection string, SQL có tham số nhạy cảm.
- Đường dẫn file nội bộ, hostname, tên cấu hình.
- Email, điện thoại, định danh khách hàng hoặc nội dung request.
- Raw error body do provider ngoài kiểm soát.

Không đưa message thẳng vào HTML/API response hoặc metric. Chỉ xuất `code` và message public an toàn do chính ứng dụng kiểm soát. Nếu giữ business ID trong typed exception, nó vẫn phải được xem xét quyền truy cập, redaction và dữ liệu nhạy cảm. **Typed không đồng nghĩa safe-to-log**.

Input dùng làm ID từ client có thể chứa dấu xuống dòng hoặc control chars; validate và giới hạn độ dài trước khi đưa vào logging fields để giảm rủi ro log injection.

## 14. Retry, timeout và cancellation không thể dựa vào từ khóa

Một đoạn code như `getMessage().toLowerCase().contains("timeout")` không trả lời được:

1. Timeout xảy ra ở caller, DB, queue hay HTTP transport?
2. Request đã commit phía server hay chưa?
3. Thao tác có idempotent không?
4. Tác vụ đã bị hủy hay chỉ hết thời gian chờ?
5. Retry budget và backoff còn không?
6. Exception có bị bọc bởi lỗi khác không?

Hãy phân loại dựa trên **loại exception/mã lỗi chính thức**, policy dependency và **trạng thái nghiệp vụ**. `CancellationException` và `InterruptedException` có ý nghĩa về hủy hợp tác, cần được xử lý theo contract của chúng; không thay thế bằng tìm chuỗi “cancelled”.

Nếu một request mạng timeout, không mặc định rằng nó chưa gây side effect; có thể cần idempotency key hoặc inquiry trạng thái trước khi retry. Error code typed giúp phân loại tốt hơn nhưng cũng không tự đem lại rollback.

## 15. Tương thích khi thêm error code vào API cũ

Giả sử code cũ chỉ ném `RuntimeException("ORDER_MISSING: id")` và client đã parse prefix. Đổi message ngay có thể phá client cũ. Migration nên gồm:

1. Khảo sát các nơi dùng `getMessage()` để làm logic, kể cả service, tests, alert, SDK và web client.
2. Thêm typed field hoặc error code vào API/server response, giữ cause.
3. Công bố tập code và ý nghĩa, định nghĩa policy với code chưa biết.
4. Chuyển caller sang field mới theo giai đoạn, viết test cho hai ngôn ngữ/thông điệp.
5. Giữ cơ chế legacy trong thời gian tương thích nếu contract thực tế đang có người dùng, nhưng không khuyến khích consumer mới.
6. Đo sự sử dụng, thông báo deprecation và xóa parser legacy theo quy trình versioning.
7. Không thay đổi semantics của success/failure hoặc retry chỉ vì chuyển định dạng.

Một client phân tán có thể nhận code mới không nằm trong enum của phiên bản cũ. Khi public protocol là string code, cần fallback an toàn như “unknown_error” và ghi request ID để điều tra; **không đoán code từ message**. Java `switch` trên enum nội bộ có thể là exhaustive, nhưng giao thức nhiều phiên bản vẫn phải tính khả năng mở rộng.

## 16. Bộ kiểm thử cần có

| Kịch bản | Kết quả cần kiểm chứng |
|---|---|
| Cùng error code, message tiếng Anh/Việt | Cùng branch, status và retry policy |
| Message thêm prefix, suffix, request ID | Logic vẫn đúng |
| Message null/rỗng | Không NPE vì parse message |
| Hai lỗi khác nhau có cùng một từ khóa | Không bị phân loại nhầm |
| Wrapper nhiều tầng | Cause và error code còn đúng |
| Error code mới chưa biết | Fallback an toàn, không phụ thuộc wording |
| Response JSON có dấu nháy/newline/Unicode | Serializer escape đúng |
| Lỗi chứa thông tin nhạy cảm | Public response/log redaction đúng chính sách |
| Timeout/cancel/thất bại thường | Phân biệt bằng contract, không regex |
| Monitoring | Trường code ổn định, không dùng toàn bộ message làm label |
| Refactor/thay bản dịch | Các test máy đọc không thay đổi |
| Legacy adapter | Parser bị cô lập, có test đặc tả và version |

Ví dụ JUnit 5 kiểm tra độc lập với câu chữ (cần dependency JUnit và đặt test trong cùng package của lớp demo):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PaymentCodeTest {
    @Test
    void localizationDoesNotChangeStatus() {
        var en = new ExceptionMessageContractDemo.PaymentFailure(
                ExceptionMessageContractDemo.FailureCode.PAYMENT_DECLINED,
                "pay-17", "Payment declined", null);
        var vi = new ExceptionMessageContractDemo.PaymentFailure(
                ExceptionMessageContractDemo.FailureCode.PAYMENT_DECLINED,
                "pay-17", "Thanh toán bị từ chối", null);

        assertEquals(402, ExceptionMessageContractDemo.stableHttpStatus(en));
        assertEquals(402, ExceptionMessageContractDemo.stableHttpStatus(vi));
        assertEquals(en.code(), vi.code());
    }
}
~~~

Bài test **không chạy chỉ bằng `javac` JDK thuần** vì dùng JUnit 5. Kiểm thử nên assert `code`/status/typed fields, không assert toàn bộ câu message trừ trường hợp đang chủ động kiểm tra bản dịch hoặc wording dành cho người đọc.

## 17. Những sai lầm đặc biệt dễ bỏ qua

1. Dùng `contains("not found")` thay subtype `NoSuchFileException` hoặc error code.
2. Parse `SQLException.getMessage()` dù API có `getSQLState()`/`getErrorCode()`.
3. Trích `orderId` từ message thay vì truyền ID/context đi cùng request.
4. Dùng `getLocalizedMessage()` để điều khiển workflow; đổi locale làm đổi logic.
5. Bọc exception rồi bỏ `cause`, khiến adapter phải dò chuỗi ở tầng dưới.
6. Tạo error code bằng toàn bộ message, làm dashboard/metric có cardinality cao.
7. Trả message thô của exception làm JSON/HTTP response, làm lộ dữ liệu nội bộ.
8. Coi mọi `"timeout"` trong text là một lỗi có thể retry an toàn.
9. Đổi public contract từ throw sang future/result hoặc đổi error code không có kế hoạch tương thích.
10. Chấp nhận bất kỳ string code mới như enum code đã biết, không có fallback.
11. Dùng regex phức tạp không giới hạn trên message do bên ngoài điều khiển.
12. Quên trường hợp `getMessage()==null` hoặc message chứa delimiter/control characters.
13. Coi cause sâu nhất là toàn bộ ý nghĩa lỗi; lớp wrapper có thể mang business ID và error code quan trọng.
14. Ghi cả message nhạy cảm vào nhiều tầng log khi chỉ cần một failure event có code và context an toàn.

## 18. Checklist code review

Khi gặp đoạn code phân loại exception:

1. Có chỗ nào quyết định nhánh bằng `getMessage().contains`, `startsWith`, `split`, regex hay substring không?
2. Message có được API công bố là giao thức có schema chính thức không? Nếu không, thay bằng gì?
3. Kiểu exception/subtype và trường `code` có đủ biểu đạt điều caller cần không?
4. Có giữ `cause` khi chuyển lỗi qua tầng không?
5. Business ID, request ID và vị trí nhập liệu có được truyền qua field/context riêng không?
6. Mã public có policy version/unknown code và message localization riêng không?
7. Retry có xét idempotency/side effect thực tế không?
8. Logs và metrics phân nhóm theo code/operation thay vì message động chưa?
9. Message có thể chứa bí mật/PII không? Public response có redaction/escaping không?
10. Test có chứng minh đổi câu chữ **không đổi nhánh** không?

## 19. Tổng kết

**Không dùng exception message làm định dạng dữ liệu mà mã khác phải phân tích.** `Throwable.getMessage()` mô tả lỗi cho con người và có thể thay đổi vì wording, localization, context hay dependency version. Dùng nó như error code làm logic dễ hỏng và khó kiểm thử.

Tách rõ **message** (để đọc), **error code/exception type** (để máy phân loại), **typed fields** (để lấy dữ liệu), **cause** (để điều tra) và **public error response** (để client tiêu thụ theo schema). Một test đơn giản nhưng rất hiệu quả là thay message tiếng Anh thành tiếng Việt, giữ nguyên error code và yêu cầu kết quả xử lý **không đổi**.

### Tham khảo

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html)
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java Language Specification `11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
