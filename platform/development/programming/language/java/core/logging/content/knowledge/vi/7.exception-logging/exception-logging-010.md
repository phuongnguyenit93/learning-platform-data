# Kiểm tra log lỗi (Exception logging) trong Java

## 1. Kiểm tra log lỗi để làm gì?

Khi một ứng dụng Java gặp ngoại lệ, việc xử lý ngoại lệ và việc ghi log là hai trách nhiệm có liên quan nhưng khác nhau. Một phương thức có thể ném `Exception` đúng, trong khi log lại thiếu nguyên nhân, ghi sai mức độ, lộ dữ liệu nhạy cảm, xuất hiện nhiều lần hoặc không tới hệ thống thu thập. Vì vậy, **kiểm tra log lỗi** là xác minh rằng một tình huống thất bại tạo ra **bản ghi đúng ý nghĩa, đúng nội dung chẩn đoán và đúng nơi nhận**.

Hãy hình dung tình huống cổng thanh toán không phản hồi. Yêu cầu cuối cùng thất bại và API trả mã lỗi phù hợp. Nếu log chỉ ghi `"Payment failed"`, người trực vận hành không biết request nào, dịch vụ phụ thuộc nào, mã lỗi nào và stack trace ở đâu. Nếu mọi tầng đều ghi `ERROR` rồi ném lại cùng ngoại lệ, một giao dịch có thể tạo năm bản ghi giống nhau. Nếu logger đã ghi chính xác nhưng appender không chuyển được dữ liệu, hệ thống giám sát vẫn không thấy sự cố.

Kiểm tra cần trả lời hai nhóm câu hỏi:

- **Ngay trong mã ứng dụng:** đúng sự kiện nào được phát, mức gì, từ logger nào, có ngoại lệ gốc hay không, các trường cần thiết có đủ không, và khi thành công có phát log lỗi nhầm không?
- **Trên đường vận hành:** bản ghi đã được formatter/encoder xuất đúng chưa, có tới file/console/collector không, có bị lọc hoặc ghi trùng không, có thể truy tìm theo `trace_id` không, và có dữ liệu nhạy cảm bị lộ không?

Cả hai nhóm đều cần thiết. Unit test bắt được `LogRecord` chứng minh ứng dụng đã tạo bản ghi; nó **không tự chứng minh** JSON đã được encode đúng hoặc hệ thống tập trung thực sự nhận được log.

## 2. Một bản ghi exception log đạt yêu cầu gồm gì?

Ví dụ về một bản ghi ERROR có cấu trúc:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "logger": "com.example.payment.PaymentService",
  "event_code": "payment.failed",
  "error_code": "GATEWAY_UNAVAILABLE",
  "request_id": "req-7",
  "trace_id": "trace-42",
  "outcome": "failed",
  "exception_type": "java.lang.IllegalStateException",
  "message": "Không thể hoàn tất thanh toán"
}
```

Đây là **minh họa cấu trúc log**, không phải đầu ra mặc định của JUL hay SLF4J. Stack trace có thể được lưu ở trường riêng, trong nội dung bản ghi hoặc như một đối tượng ngoại lệ tùy backend.

Các khía cạnh cần kiểm tra:

| Khía cạnh | Câu hỏi kiểm tra | Lỗi thường gặp |
| --- | --- | --- |
| Sự kiện | `event_code` có diễn đạt đúng loại thất bại? | Mã quá chung như `unknown.error` hoặc mã “failed” trước khi hết retry. |
| Mức độ | Có dùng `ERROR`/`SEVERE` cho thất bại cuối theo chính sách? | Ghi ERROR cho hành vi từ chối hợp lệ, hoặc chỉ ghi DEBUG khi thao tác thật sự thất bại. |
| Nguồn | Logger name và service có đúng thành phần xử lý? | Dùng một tên logger không rõ nguồn cho toàn bộ ứng dụng. |
| Ngữ cảnh | Có `request_id`/`trace_id`, mã lỗi, đối tượng thao tác nếu được phép? | Không liên kết được log với request hoặc job. |
| Ngoại lệ | Có `Throwable` và chuỗi nguyên nhân khi cần? | Chỉ ghi `ex.getMessage()`, làm mất loại lỗi và vị trí phát sinh. |
| Số lượng | Một thất bại logic có bị log lặp qua nhiều tầng? | Cùng một exception được log ở repository, service và controller. |
| Đầu ra | Formatter, handler và collector có giữ đủ thông tin? | Ghi bản ghi có Throwable nhưng encoder bỏ stack trace. |
| Dữ liệu nhạy cảm | Có token, mật khẩu, thông tin thanh toán, dữ liệu riêng tư? | Ghi toàn bộ request body hoặc exception message chứa secret. |
| Hành vi | Log có làm thay đổi kết quả xử lý ngoại lệ? | Nuốt lỗi sau khi log, hoặc throw lỗi mới làm mất cause. |

**Tiêu chí phải gắn với ngữ nghĩa của tác vụ.** Một lần thử lại thất bại nhưng đã được phục hồi có thể đáng ghi `WARN`; thất bại cuối khiến giao dịch không thể hoàn tất thường đáng ghi `ERROR`. Trong `java.util.logging` (JUL), hằng có ý nghĩa gần mức ERROR là **`Level.SEVERE`**; JUL không có `Level.ERROR`. SLF4J/Logback và `System.Logger` có tên mức `ERROR`.

## 3. Chọn đúng điểm ghi để kiểm tra đúng điều

Một mẫu phổ biến khi exception đi qua nhiều tầng:

```text
Repository: gọi database -> ném SQLException
    |
    v
Service: bổ sung ngữ cảnh, chuyển thành PaymentStorageException
    |
    v
API boundary: quyết định request thất bại -> ghi một ERROR có cause
    |
    v
Trả response lỗi theo hợp đồng API
```

Không có quy tắc cứng là “chỉ được ghi log một lần cho mỗi exception”. Một tầng thấp có thể cần một sự kiện kỹ thuật riêng, và một tầng cao cần sự kiện nghiệp vụ cuối; hai sự kiện khác nghĩa vẫn hợp lệ. Tuy nhiên, **log + rethrow cùng một lỗi với cùng nội dung ở mọi tầng** dễ gây trùng và làm sai phép đếm.

Với retry:

```text
payment.attempt_failed, attempt=1 -> WARN
payment.attempt_failed, attempt=2 -> WARN
payment.failed, attempts=3         -> ERROR
```

Nếu lần thử cuối thành công, sự kiện `payment.failed` với nghĩa “thao tác logic thất bại cuối cùng” **không nên xuất hiện**. Khi test, hãy kiểm tra cả đường thành công, đường retry phục hồi và đường thất bại cuối; đừng chỉ tạo một ngoại lệ rồi khẳng định “có dòng ERROR”.

Đối với HTTP, `400` hoặc `404` hợp lệ thường không là lỗi hệ thống cần ERROR. Một response `500` cũng không đảm bảo có đúng một dòng ERROR vì proxy hoặc hạ tầng có thể tạo response trước khi ứng dụng ghi log. Vì vậy, **số bản ghi ERROR không mặc nhiên bằng số request thất bại**; đo tỷ lệ lỗi phục vụ cần metric hoặc sự kiện hoàn tất request có định nghĩa riêng.

## 4. Hai tầng kiểm tra: bản ghi trong JVM và đầu ra sau formatter

### 4.1. Kiểm tra bản ghi trong JVM

Trong JUL, `LogRecord` lưu nhiều thông tin có thể kiểm tra trực tiếp:

- `getLevel()`: mức ghi.
- `getLoggerName()`: tên logger nguồn.
- `getMessage()`: thông điệp gốc, có thể là mẫu kèm tham số.
- `getParameters()`: tham số dùng khi format message, nếu có.
- `getThrown()`: ngoại lệ được gắn vào bản ghi, nếu có.
- `getInstant()`: mốc thời gian của bản ghi.
- `getThreadID()` là API cũ; với Java hiện đại có thể quan tâm thông tin luồng nhưng không dựa vào giá trị cố định khi test.

Kiểm tra `record.getThrown()` đáng tin hơn việc tìm dòng chữ `Exception` trong một output tùy định dạng. Nếu mã truyền một đối tượng Throwable vào `Logger.log(Level.SEVERE, message, throwable)`, JUL giữ nó trong `LogRecord` để formatter có thể xuất stack trace. **Việc có Throwable trong LogRecord không đảm bảo mọi formatter sẽ in stack trace**.

### 4.2. Kiểm tra bản ghi đã được định dạng

Bộ định dạng tạo ra văn bản hoặc JSON mà hệ thống thu thập nhìn thấy. Cần kiểm tra bổ sung rằng:

1. Level, mã sự kiện và các trường ngữ cảnh xuất đúng kiểu, đúng tên.
2. Throwable, stack trace và chuỗi cause được thể hiện theo hợp đồng cần có.
3. Các giá trị có dấu ngoặc kép, dấu xuống dòng và ký tự Unicode được escape đúng, không làm hỏng JSON hoặc tạo log injection.
4. Dữ liệu nhạy cảm được che hoặc loại bỏ trước khi rời khỏi ứng dụng.
5. Một sự kiện không bị xuất hai lần vào **cùng một đích** vì handler/appender cha và con cùng hoạt động.

Các bước này thường là **integration test của encoder/appender/collector**. Việc test chuỗi đầu ra nguyên văn đến từng timestamp, thread hay vị trí stack trace thường dễ vỡ. Hãy kiểm tra các trường ổn định hoặc parse JSON, rồi assert từng thuộc tính; chỉ so sánh chuỗi đầy đủ khi định dạng là một hợp đồng cần được giữ nguyên.

## 5. Ví dụ Java 17 chạy được: bắt và kiểm tra log lỗi bằng Handler

Ví dụ dùng **JUL có sẵn trong JDK**, không cần JUnit hay thư viện ngoài. Ta tạo một handler lưu `LogRecord` vào bộ nhớ, chạy một tình huống thành công và một tình huống thất bại, sau đó tự kiểm tra những điều quan trọng.

Mục đích của ví dụ:

- Không có ERROR/SEVERE khi xử lý thành công.
- Khi thất bại cuối cùng, có **đúng một** `SEVERE`.
- Logger name, mã sự kiện, mã lỗi và request ID đúng.
- `LogRecord` giữ ngoại lệ gốc `IllegalStateException`.
- Cấu hình logger được khôi phục sau khi kiểm tra, tránh ảnh hưởng mã khác cùng JVM.

Lưu thành `ErrorLogCheckDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ErrorLogCheckDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.payment");

    private static final String ERROR_MESSAGE =
            "event_code=payment.failed "
            + "error_code=GATEWAY_UNAVAILABLE "
            + "request_id=req-7";

    static final class CapturingHandler extends Handler {
        private final List<LogRecord> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record);
            }
        }

        List<LogRecord> snapshot() {
            return List.copyOf(events);
        }

        @Override
        public void flush() {
            // Bộ nhớ, không có luồng xuất cần flush.
        }

        @Override
        public void close() {
            // Không sở hữu tài nguyên ngoài.
        }
    }

    private static boolean processPayment(boolean gatewayFails) {
        try {
            if (gatewayFails) {
                throw new IllegalStateException("gateway unavailable");
            }
            return true;
        } catch (IllegalStateException failure) {
            LOG.log(Level.SEVERE, ERROR_MESSAGE, failure);
            return false;
        }
    }

    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) {
        Level previousLevel = LOG.getLevel();
        boolean previousUseParentHandlers = LOG.getUseParentHandlers();

        CapturingHandler capture = new CapturingHandler();
        capture.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            require(processPayment(false), "success should return true");
            require(capture.snapshot().isEmpty(),
                    "success must not produce an error log");

            require(!processPayment(true),
                    "failure should return false");

            List<LogRecord> records = capture.snapshot();
            require(records.size() == 1, "expected exactly one error");

            LogRecord error = records.get(0);
            require(error.getLevel() == Level.SEVERE, "wrong level");
            require("demo.payment".equals(error.getLoggerName()),
                    "wrong logger");
            require(ERROR_MESSAGE.equals(error.getMessage()),
                    "missing event metadata");
            require(error.getThrown() instanceof IllegalStateException,
                    "missing original exception");
            require("gateway unavailable".equals(
                    error.getThrown().getMessage()), "wrong cause");

            System.out.println("PASS success_without_error");
            System.out.println("PASS error_count=1");
            System.out.println("PASS level=SEVERE");
            System.out.println("PASS event_code=payment.failed");
            System.out.println("PASS throwable=IllegalStateException");
        } finally {
            LOG.removeHandler(capture);
            LOG.setLevel(previousLevel);
            LOG.setUseParentHandlers(previousUseParentHandlers);
            capture.close();
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ErrorLogCheckDemo.java
java ErrorLogCheckDemo
```

**Stdout dự kiến (chính xác):**

```text
PASS success_without_error
PASS error_count=1
PASS level=SEVERE
PASS event_code=payment.failed
PASS throwable=IllegalStateException
```

### Phân tích ví dụ

- `CapturingHandler.publish` nhận `LogRecord` khi mức và filter của handler cho phép. Trong ứng dụng test, handler không cần ghi file hoặc nối mạng.
- `LOG.setLevel(Level.ALL)` bật mọi mức tại logger nguồn, `capture.setLevel(Level.ALL)` không lọc thêm. Nếu logger đang ở `OFF` hoặc handler không nhận mức đó thì test bắt được log sẽ không có dữ liệu.
- `LOG.setUseParentHandlers(false)` ngăn bản ghi đi tới handler của logger cha, tránh console tự in thêm dòng gây sai đầu ra. Đây chỉ là cấu hình cô lập khi test.
- `processPayment(false)` không phát ERROR; `processPayment(true)` mô phỏng kết quả cuối cùng thất bại và phát đúng một `SEVERE` cùng ngoại lệ. `catch` đã xử lý và trả về `false` nên ngoại lệ không thoát khỏi phương thức; test xác minh hành vi và log cùng lúc.
- Kiểm tra `records.size() == 1` phát hiện trường hợp mã vô tình log lặp. Tuy nhiên, với hệ thống có nhiều loại log trong cùng quá trình, nên **lọc theo `event_code` và level cụ thể**, tránh giả định tổng số log phải bằng 1.
- `getThrown()` xác minh ngoại lệ vẫn hiện diện. Handler chỉ thu bản ghi trong bộ nhớ nên **không in stack trace**; bài kiểm tra formatter cần được thực hiện riêng nếu tiêu chí là “người vận hành nhìn thấy stack trace”.
- Khối `finally` gỡ handler và khôi phục mức cùng cấu hình lan truyền. Logger JUL là đối tượng dùng chung theo tên trong JVM, vì vậy test không nên để thay đổi cấu hình tồn tại sau khi chạy.

**Lưu ý:** mã chạy tuần tự để test dễ dự đoán. `ArrayList` trong handler ví dụ **không an toàn cho ghi đồng thời từ nhiều luồng**. Nếu ứng dụng ghi log song song, dùng bộ thu thập phù hợp cho concurrency và đồng bộ hóa việc đợi nhận bản ghi; không sao chép handler minh họa này vào production.

## 6. Khi dùng SLF4J, Logback và JUnit: kiểm tra thế nào?

Nhiều ứng dụng Spring hoặc Java server dùng SLF4J làm API và Logback làm backend. Một lời gọi thường thấy:

```java
try {
    paymentGateway.charge(orderId);
} catch (GatewayException exception) {
    log.error("event_code=payment.failed order_id={}", orderId, exception);
    throw exception;
}
```

Đoạn trên là **minh họa**, không phải chương trình độc lập: `paymentGateway`, `GatewayException`, `orderId` và `log` thuộc ứng dụng cụ thể. Trong SLF4J, truyền `Throwable` ở vị trí cuối thích hợp cho overload định dạng giúp backend lưu nguyên nhân và xuất stack trace. Trong thiết kế thực, cần quyết định tầng nào chịu trách nhiệm ghi lỗi cuối để tránh lớp ngoài log lại cùng lỗi.

Cách kiểm tra phổ biến với Logback là gắn một **`ListAppender<ILoggingEvent>`** vào logger dưới test; sau khi chạy tình huống thì đọc danh sách sự kiện và kiểm tra:

- `ILoggingEvent.getLevel()` có bằng `ch.qos.logback.classic.Level.ERROR` không.
- `getLoggerName()` có khớp logger/class cần kiểm tra không.
- `getFormattedMessage()` có mã sự kiện và trường ổn định không.
- `getThrowableProxy()` có chứa loại ngoại lệ và nguyên nhân mong đợi không.
- Với logging có cấu trúc, backend có giữ các cặp khóa–giá trị (`key-value pairs`) như `event_code`, `request_id` không.

Nếu dùng JUnit 5, các kiểm tra tương ứng có thể viết bằng `assertEquals`, `assertNotNull`, `assertTrue` hoặc thư viện assertion có sẵn của dự án. Các ví dụ kiểu này **cần dependency SLF4J/Logback/JUnit và cấu hình backend đúng**, khác với chương trình JUL độc lập ở phần 5.

Một quy trình test an toàn với appender tạm thời:

1. Tạo appender riêng và `start()` trước khi gắn.
2. Gắn vào đúng logger cần quan sát.
3. Chạy tình huống kiểm thử và đọc sự kiện; đối với backend bất đồng bộ phải có cách chờ nhận có giới hạn và điều kiện rõ ràng.
4. Trong `finally`, gỡ appender và `stop()`; hoàn nguyên mức logger, additivity và cấu hình đã sửa.
5. Tránh chạy song song các test thay đổi cùng logger/configuration toàn cục mà không cô lập, vì bản ghi của test khác có thể lọt vào danh sách.

Không nên assert nguyên văn một stack trace có số dòng source và tên thread cố định. Sau refactor, thông tin vị trí có thể đổi dù hành vi vẫn đúng. Hãy kiểm tra **loại exception, thông điệp có nghĩa, cause chain và event code**. Nếu format log là một hợp đồng chính thức, dùng integration test riêng để xác minh định dạng.

## 7. Kiểm tra stack trace và chuỗi nguyên nhân

Ngoại lệ có thể được bọc bởi các tầng xử lý:

```text
PaymentException: Không thể hoàn tất thanh toán
    caused by GatewayTimeoutException: timeout
        caused by SocketTimeoutException: read timed out
```

Khi điều tra, **exception ngoài cùng** mô tả thất bại nghiệp vụ, còn **cause bên trong** thường chỉ ra nguyên nhân kỹ thuật. Nếu mã chỉ ghi:

```java
log.severe(exception.getMessage());
```

thì log có thể chỉ chứa một câu và không còn chuỗi nguyên nhân. Đây là một **đoạn minh họa** với biến `log` và `exception` đã tồn tại; không phải chương trình độc lập.

Với JUL, nên chuyển cả `Throwable` vào lời gọi:

```java
log.log(java.util.logging.Level.SEVERE,
        "event_code=payment.failed", exception);
```

Trong test, `LogRecord.getThrown()` cho phép lấy Throwable và đi qua `getCause()` để kiểm tra quan hệ nhân quả. Với Logback, exception có thể được biểu diễn dưới dạng `IThrowableProxy` thay vì đối tượng Throwable gốc tại nơi đọc sự kiện.

Một vài lưu ý quan trọng:

- **Có Throwable khác có stack trace được hiển thị:** formatter có quyền chọn cách trình bày. Test `getThrown() != null` chỉ chứng minh bản ghi giữ ngoại lệ.
- **Có stack trace không đồng nghĩa với đủ ngữ cảnh:** stack trace không tự chỉ ra request nào, tác vụ nào hay mức ảnh hưởng. Cần thêm mã sự kiện, mã lỗi và ID liên kết.
- **Không tạo exception mới mà bỏ cause:** nếu bắt một lỗi thấp rồi chuyển thành lỗi nghiệp vụ, hãy giữ exception gốc làm cause khi constructor/API cho phép.
- **Không log stack trace mọi lần retry:** số bản ghi rất lớn có thể làm tăng chi phí, gây nhiễu và che khuất thất bại cuối. Cân đối theo chính sách và mức độ điều tra.
- **Exception message có thể chứa dữ liệu nhạy cảm:** không log bừa các chuỗi connection, URL có credential, token hoặc dữ liệu cá nhân; kiểm soát nội dung trước khi xuất.

## 8. Kiểm tra log lỗi trên hệ thống đang chạy

Unit test chỉ quan sát bên trong JVM. Để biết log có ích trong vận hành, cần thử trên môi trường phát triển hoặc staging với **tình huống lỗi mô phỏng an toàn**:

1. **Chọn kịch bản xác định được kết quả:** ví dụ một dependency giả trả timeout và request được trả lỗi đã dự kiến. Tránh gây lỗi trên production chỉ để tạo log.
2. **Gắn mã liên kết:** một `request_id` hoặc `trace_id` duy nhất cho bài thử, cùng service, environment và thời điểm rõ ràng.
3. **Kích hoạt đúng một thao tác và ghi lại mốc thời gian:** nếu có retry, xác nhận số lượt thử và kết quả cuối.
4. **Xem ở nguồn:** console/file của dịch vụ có log ở mức phù hợp không? JSON hoặc text có `event_code`, `error_code`, logger và exception không?
5. **Xem ở bộ thu thập:** tìm theo `service`, `environment`, `event_code`, `trace_id` trong khoảng thời gian đủ rộng cho độ trễ truyền. So sánh các trường sau khi parse.
6. **Kiểm tra số bản ghi theo mục đích:** có đúng một `payment.failed` cho thất bại cuối không, hay có bản ghi trùng ở cùng kênh? Nếu có nhiều bản vì fan-out sang các kênh khác nhau, phải phân biệt với trùng ngoài ý muốn.
7. **Kiểm tra bảo mật và khả năng xử lý:** không chứa secret, log có đủ thông tin để tìm nguyên nhân, và người vận hành có quyền truy cập đúng kênh.
8. **Kiểm tra thành công và phục hồi:** khi dependency hoạt động trở lại hoặc fallback thành công, không còn sự kiện “thất bại cuối cùng” giả.

Ví dụ một truy vấn **mang tính minh họa** trong công cụ có cú pháp lọc trường:

```text
service = "checkout"
AND environment = "staging"
AND event_code = "payment.failed"
AND trace_id = "trace-test-42"
```

Cú pháp thực tế khác nhau giữa Elastic, Loki, Splunk, dịch vụ đám mây và hệ thống tự xây dựng. Điều cốt lõi là **lọc theo trường đã được parse**, không phụ thuộc vào việc toàn bộ dòng text chứa đúng các khoảng trắng đã giả định.

### Khi không tìm thấy log, kiểm tra theo đường đi

```text
Mã đã gọi logger?
   |
   +-- Không -> Kiểm tra nhánh điều kiện, exception có được catch hay throw không
   |
   +-- Có -> Logger có chấp nhận level/filter?
                |
                +-- Không -> Kiểm tra mức hiệu lực và filter ở logger
                |
                +-- Có -> Handler/appender có nhận và encode đúng?
                             |
                             +-- Không -> Kiểm tra level, filter, formatter, additivity
                             |
                             +-- Có -> Collector có nhận, parse và lưu không?
                                          |
                                          +-- Không -> Kiểm tra buffer, drop, cấu hình thu thập, quyền truy cập
                                          |
                                          +-- Có -> Truy vấn đúng trường, môi trường, thời gian, index?
```

**Đừng lập tức kết luận “code không log” chỉ vì giao diện tìm kiếm trống.** Bộ thu thập có thể gửi chậm, bỏ dữ liệu khi buffer đầy, không đọc đúng stdout/file, parse sai JSON hoặc thay đổi nhãn môi trường. Ngược lại, thấy dữ liệu trong collector không có nghĩa mọi sự kiện đều được giao nhận đúng một lần. Nếu cần bảo đảm đầy đủ để đo SLI/SLO hoặc audit, phải có cơ chế đo và đối soát phù hợp.

## 9. Kiểm tra lỗi log lặp, bị mất và sai mức

### 9.1. Log trùng do nhiều tầng bắt cùng exception

```java
try {
    repository.save(order);
} catch (StorageException exception) {
    log.error("Cannot save order", exception);
    throw exception;
}
```

Đây là **minh họa** với các biến và lớp giả định, chưa phải mã độc lập. Nếu service và controller phía ngoài cũng log ERROR cho cùng thất bại, một thao tác có thể có ba dòng ERROR.

Giải pháp là định rõ các sự kiện theo trách nhiệm: tầng trong có thể chỉ **bổ sung ngữ cảnh rồi ném tiếp**, còn ranh giới xử lý biết kết quả cuối sẽ log `order.save_failed`. Nếu cần log sự kiện kỹ thuật riêng tại tầng trong, đặt mã khác và phân biệt rõ “lỗi lượt thử” với “thất bại cuối”.

### 9.2. Log trùng do cấu hình

Trong JUL, bản ghi từ logger con có thể đi qua handler của chính nó và handler của cha khi `useParentHandlers=true`. Với Logback, quy tắc tương tự là `additivity`. Một exception chỉ được log một lần trong code nhưng console vẫn có hai dòng nếu cùng một đích được gắn ở nhiều tầng.

Kiểm thử bằng một sự kiện có `event_code` và `trace_id` giả định duy nhất; xác nhận số lượng ở từng đích. Không tự động “sửa” bằng cách tắt toàn bộ lan truyền, vì có thể vô tình làm mất kênh thu thập chung.

### 9.3. Sai mức log

Các tình huống nên có test khác nhau:

| Tình huống | Kỳ vọng thường hợp lý |
| --- | --- |
| Đầu vào không hợp lệ, ứng dụng trả phản hồi đúng hợp đồng | Không phát lỗi hệ thống ở ERROR; có thể INFO/DEBUG nếu cần. |
| Một lần timeout nhưng retry sau đó thành công | WARN/DEBUG cho attempt, không phát sự kiện `payment.failed` cuối cùng. |
| Mất dependency sau mọi đường phục hồi và request thất bại | ERROR trong SLF4J/Logback, `SEVERE` trong JUL. |
| Một exception được xử lý bằng fallback vẫn đáp ứng cam kết | Không xem là thất bại cuối; mức tùy ảnh hưởng thật. |
| Tiến trình không thể khởi động vì cấu hình quan trọng sai | ERROR/SEVERE tại ranh giới khởi động, giữ nguyên nhân. |

Mức log không thay thế cho HTTP status, hành vi rollback hoặc cơ chế thử lại. Test nên xác minh **kết quả trả về hoặc ngoại lệ** cùng với **log** để phát hiện mã chỉ ghi lỗi nhưng không xử lý đúng.

### 9.4. Không thể so sánh một timestamp hoặc stack trace cố định

Các trường `timestamp`, `thread`, thứ tự log từ nhiều luồng và vị trí dòng trong stack trace có thể thay đổi giữa các lần chạy. Khi test:

- So sánh level, event code, mã lỗi và phần ngữ nghĩa ổn định.
- Kiểm tra timestamp hợp lệ hoặc trong một khoảng thời gian hợp lý, không assert một mốc cụ thể.
- Với sự kiện bất đồng bộ, có cơ chế đồng bộ hoặc chờ có giới hạn thay vì dùng `Thread.sleep(...)` tùy tiện.
- Với các bản ghi song song, so sánh tập sự kiện hoặc nhóm theo correlation ID thay vì đòi thứ tự toàn cục cố định.

### 9.5. Chỉ kiểm tra message mà bỏ Throwable

Dòng `"payment failed: timeout"` có thể trông đúng, nhưng không giữ exception type, cause chain và stack trace. Cần kiểm tra `LogRecord.getThrown()` hoặc cấu trúc exception của backend; sau đó có integration test đảm bảo formatter thực sự hiển thị những gì người trực vận hành cần.

## 10. Kiểm tra an toàn thông tin trong log lỗi

Đường exception đặc biệt dễ làm rò rỉ dữ liệu: exception message có thể chứa câu lệnh SQL kèm giá trị, endpoint với token, thông tin xác thực hoặc dữ liệu đầu vào.

Hãy thêm ca kiểm thử dùng **giá trị bí mật giả** như `SECRET_TEST_TOKEN_123` rồi xác nhận **đầu ra cuối cùng** không chứa chuỗi đó, đồng thời vẫn chứa mã lỗi và trace ID đủ để điều tra. Cần kiểm tra cả message, các trường có cấu trúc, stack trace và dữ liệu được thu thập, vì một trường được che nhưng exception message vẫn có thể lộ dữ liệu.

Các nguyên tắc:

- Chỉ ghi những trường cần cho mục tiêu điều tra; không tự động ghi toàn bộ request/response hoặc đối tượng domain qua `toString()`.
- Kiểm soát thông điệp ngoại lệ từ thư viện ngoài và dependency; có thể cần chuyển thành mã lỗi an toàn ở ranh giới ghi log.
- Tránh log injection: đầu vào chứa xuống dòng hoặc ký tự điều khiển có thể tạo “dòng log giả” nếu nối chuỗi thẳng vào text; dùng formatter/encoder an toàn và trường dữ liệu có kiểu.
- Áp dụng quyền đọc, chính sách giữ và xóa phù hợp với từng loại log; ERROR không có nghĩa dữ liệu được phép lưu vô hạn.
- Đối với audit hoặc sự kiện bắt buộc bảo đảm giao nhận, không chỉ dựa vào logger thông thường vì buffer và mạng có thể làm mất dữ liệu.

Đừng đặt giá trị bí mật thật vào bài test để xem có bị ghi ra hay không. Dùng dữ liệu giả nhưng cùng hình dạng đầu vào để kiểm tra cơ chế che và loại bỏ.

## 11. Danh sách lỗi thường gặp và hướng sửa

| Vấn đề | Dấu hiệu | Kiểm tra và sửa |
| --- | --- | --- |
| Ghi `ex.getMessage()` thay cho Throwable | Không có stack trace hoặc cause | Truyền Throwable vào overload logging; test `getThrown()` và formatter. |
| Ghi ERROR cho mọi catch | Nhiều cảnh báo không có ảnh hưởng thật | Phân biệt retry được phục hồi với thất bại cuối. |
| Log rồi ném lại ở mọi tầng | Một lỗi có nhiều stack trace | Quy định ranh giới phát sự kiện và mã sự kiện riêng nếu khác ngữ nghĩa. |
| Unit test chỉ tìm từ “error” | Đổi câu chữ làm test gãy | Kiểm tra level, mã sự kiện và trường cấu trúc. |
| Bắt `LogRecord` rồi cho rằng stack trace đã in | Unit test PASS nhưng console thiếu ngoại lệ | Kiểm tra riêng formatter/encoder. |
| Level logger và handler khác nhau | Có gọi logger nhưng không thấy output | Kiểm tra mức và filter ở cả hai tầng. |
| Gắn handler rồi quên gỡ | Test sau nhận thêm bản ghi, log trùng | Dọn handler/appender, hoàn nguyên cấu hình trong `finally`. |
| Test logging song song bằng `ArrayList` | Lỗi dữ liệu hoặc kết quả không ổn định | Dùng sink an toàn luồng và cách chờ có giới hạn. |
| Collector không parse `event_code` | Không lọc được theo mã sự kiện | Kiểm tra JSON/encoder và mapping đầu nhận. |
| So sánh toàn bộ stack trace | Test hỏng sau refactor vô hại | Assert Throwable type, cause và trường ổn định. |
| Log chứa mật khẩu/token | Rủi ro lộ dữ liệu | Kiểm tra đầu ra với secret giả; kiểm soát dữ liệu trước ghi. |
| Đếm ERROR làm tỷ lệ request lỗi | Số liệu tăng vì log trùng hoặc thiếu | Dùng metric hoặc sự kiện hoàn tất với mẫu số và quy tắc rõ. |

## 12. Bài tập tự kiểm tra

Giả sử một dịch vụ đơn hàng có ba tình huống:

**A.** Request thiếu trường bắt buộc, được trả HTTP 400 đúng thiết kế.  
**B.** Gọi database lần đầu timeout, retry thành công.  
**C.** Gọi database thất bại sau tất cả lượt retry, request cuối cùng bị lỗi.

Hãy trả lời:

1. Tình huống nào thường cần `ERROR`/`SEVERE`? Mức cho các tình huống còn lại nên được cân nhắc theo tiêu chí gì?
2. Nếu lớp repository, service và controller đều `log.error(...)` rồi ném lại cùng lỗi C, một request có thể tạo bao nhiêu dòng ERROR? Kiểm tra thế nào để phân biệt việc log trùng với fan-out hợp lệ?
3. Bản ghi của C có `event_code=order.save_failed`, `request_id=req-7` nhưng chỉ lưu chuỗi `exception.getMessage()`. Những dữ liệu chẩn đoán nào có thể bị mất?
4. Unit test bắt được một `LogRecord` với `getThrown() != null`. Đã chứng minh được stack trace xuất hiện trong kho log tập trung chưa?
5. Khi tìm theo `trace_id` trong hệ thống log nhưng không có kết quả, bạn sẽ kiểm tra lần lượt những tầng nào?

**Gợi ý đáp án:**

- Với chính sách phổ biến, C cần ERROR/SEVERE vì thao tác logic cuối cùng thất bại. A thường không cần mức lỗi máy chủ. B có thể WARN/DEBUG cho một lần thử lỗi rồi INFO cho kết quả thành công, tùy mức ảnh hưởng và nhu cầu vận hành.
- Nếu cả ba tầng đều log một lần, có thể xuất hiện ba bản ghi cho một thao tác; mỗi bản ghi còn có thể được xuất tới nhiều đích. Kiểm tra mã sự kiện, logger, request ID, vị trí code phát log và nơi gắn handler/appender; đếm **trong từng đích**.
- Chỉ ghi message có thể làm mất loại ngoại lệ, stack trace và chuỗi nguyên nhân; cần truyền Throwable và đảm bảo formatter xử lý phù hợp.
- Chưa. Unit test chứng minh bản ghi trong JVM giữ Throwable. Cần kiểm tra formatter, appender và đường thu thập để khẳng định kho log thực sự có stack trace.
- Kiểm tra nhánh xử lý có gọi logger không; mức/filter của logger; handler/appender và định dạng; buffer/collector và parse; cuối cùng kiểm tra service, môi trường, khoảng thời gian, index, quyền truy cập và truy vấn.

**Tiêu chí hoàn thành bài:** Bạn có thể viết một ca kiểm tra xác nhận “không có log lỗi khi thành công, có đúng một log thất bại cuối khi lỗi”, kiểm tra `level`, `event_code`, `Throwable` và các trường liên kết; sau đó diễn giải vì sao còn cần kiểm thử formatter và collector trước khi tin rằng người vận hành sẽ thấy log lỗi đầy đủ.