# Nội dung message trong Java Logging

**Log message** là nội dung do ứng dụng cung cấp khi phát một sự kiện log. Một message có ích giúp trả lời: **điều gì xảy ra, kết quả là gì, xảy ra ở đâu, liên quan đến yêu cầu/đối tượng nào và điều gì khiến người vận hành cần quan tâm?**

Trong Java, log event có thể bao gồm **message template**, tham số, level, tên logger, timestamp, thread, exception và các trường ngữ cảnh. **Message chỉ là một phần của log event**: các thành phần khác có thể được logging framework hoặc backend bổ sung. Chất lượng message do tác giả mã nghiệp vụ quyết định; backend không thể tự bổ sung thông tin nghiệp vụ mà ứng dụng chưa ghi.

## 1. Nội dung message tốt cần trả lời điều gì?

Thông tin quan trọng tùy sự kiện, nhưng thường nằm trong năm nhóm:

1. **Sự kiện/hành động:** yêu cầu được tiếp nhận, đơn hàng được chấp nhận, job đồng bộ bắt đầu, gọi dịch vụ ngoài thất bại.
2. **Kết quả:** completed, accepted, rejected, retrying, failed. Không mô tả một bước đã "completed" khi công việc mới bắt đầu.
3. **Định danh liên quan:** requestId, orderId, jobId, messageId hoặc traceId nếu được phép ghi.
4. **Lý do thực tế:** invalid_quantity, upstream_timeout, configuration_missing hoặc reason code có ý nghĩa. Không suy đoán nguyên nhân không có bằng chứng.
5. **Số liệu hữu ích:** attempt, processedCount, durationMs, retryDelayMs; dùng đơn vị rõ ràng.

Không buộc mọi message có đủ năm nhóm. Một service startup có thể chỉ cần `event=service_ready` và tên component; một lỗi retry cần thêm dependency, attempt, reason và kết quả.

| Message thiếu thông tin | Message rõ nghĩa hơn | Tác dụng |
| --- | --- | --- |
| `"Done"` | `"event=inventory_sync_completed jobId=job-42 processedCount=180 durationMs=560"` | Xác định tác vụ, số lượng và thời gian |
| `"Error calling service"` | `"event=pricing_call_failed dependency=pricing-api requestId=req-14 reason=upstream_timeout"` | Biết hệ thống nào, request nào, vì sao |
| `"Invalid data"` | `"event=order_rejected orderId=ord-7 reason=invalid_quantity"` | Biết quy tắc bị vi phạm, không ghi raw payload |
| `"Retry"` | `"event=inventory_sync_retry_scheduled jobId=job-42 attempt=2 delayMs=500 reason=timeout"` | Phân biệt retry với lỗi cuối cùng |
| `"Started"` | `"event=batch_import_started jobId=job-42 sourceType=csv"` | Biết công việc nào đã bắt đầu |

Các dòng ở cột thứ hai là ví dụ text có quy ước `key=value`. Để truy vấn theo trường một cách đáng tin cậy, nên đưa các giá trị thành **structured fields** khi API/backend hỗ trợ, thay vì chỉ ghép thành chuỗi.

### Log message khác thông báo cho người dùng

Thông báo trên giao diện có thể là `"Thanh toán chưa thành công. Vui lòng thử lại."` vì mục tiêu là hướng dẫn người dùng. Log dành cho vận hành nên có thông tin kỹ thuật có kiểm soát, chẳng hạn `payment_authorization_failed`, `requestId`, `dependency`, `attempt`, `reason` và exception liên quan.

Cũng không nên dựa vào log text làm bằng chứng duy nhất rằng giao dịch đã thành công; trạng thái nghiệp vụ cần được ghi nhận bằng cơ chế dữ liệu phù hợp, có độ tin cậy được thiết kế riêng.

## 2. Phân biệt message, metadata và context

Hãy xem một bản ghi log minh họa:

~~~text
2026-11-09T10:15:30Z INFO com.example.OrderService
event=order_accepted outcome=accepted requestId=req-101 orderId=ord-7 quantity=3
~~~

- **Timestamp**, **level**, **logger name** và đôi khi **thread** thường được logger/backend thêm ở lớp định dạng. Không cần tự chèn chúng vào từng message.
- **Message** nói sự kiện và kết quả, ví dụ `order_accepted`.
- **Context** là dữ kiện giúp tìm bản ghi liên quan, ví dụ requestId, orderId, traceId. Nó có thể nằm trong text, tham số, MDC hoặc field cấu trúc.
- **Throwable** mang ngữ cảnh lỗi và stack trace nếu được truyền cho logging API. Không coi tên exception hoặc `ex.getMessage()` là thay thế cho toàn bộ exception.

Message không nên lặp cả timestamp, level và tên lớp nếu chúng đã được backend xuất nhất quán. Nếu ứng dụng tự ghi giờ bằng `LocalDateTime.now()` nhưng backend ghi thời điểm với múi giờ khác, hai giá trị có thể làm người điều tra hiểu sai.

### Message template và giá trị biến động

Để dễ nhóm sự kiện, giữ nguyên một template có ý nghĩa và truyền giá trị động bằng tham số:

~~~text
Template: event=order_accepted orderId={0} quantity={1}
Values:   ord-7, 3
Rendered: event=order_accepted orderId=ord-7 quantity=3
~~~

Ở đây `order_accepted` là **tên sự kiện ổn định**, còn `ord-7` và `3` là giá trị của lần thực thi. Tham số hóa thường giúp mã dễ đọc và tránh nối chuỗi ngay tại lời gọi; tuy nhiên cách format, độ trễ đánh giá tham số và khả năng giữ cấu trúc phụ thuộc từng API/backend.

## 3. Quy ước đặt nội dung message

Một quy ước text dễ nhận diện là:

~~~text
event=<stable_name> outcome=<state> requestId=<id> entityId=<id> reason=<code>
~~~

Đây là **khuôn mẫu gợi ý**, không buộc mỗi bản ghi chứa mọi key. Khi xây dựng quy ước cho dự án:

- **Tên event ổn định:** dùng một kiểu như `snake_case`: `order_accepted`, `payment_failed`, `inventory_sync_completed`. Đừng đổi tên event chỉ vì đổi câu diễn đạt cho người đọc.
- **Outcome là trạng thái đã biết tại thời điểm ghi:** `retrying` khác `failed`; `rejected` khác lỗi hạ tầng.
- **Reason code nhất quán:** `invalid_quantity` khác `upstream_unavailable`. Không biến message exception động thành danh sách reason code vô hạn.
- **Tên key thống nhất:** tránh cùng request ID lúc được gọi `req`, lúc `correlation_id`, lúc `requestId`.
- **Số liệu có đơn vị:** `durationMs=250`, `delayMs=500`; không ghi `duration=250` khi người đọc không biết đơn vị.
- **Đủ ngữ cảnh, ít nhiễu:** một log event thường chỉ cần vài giá trị hữu ích, không cần toàn bộ request body hay `toString()` của object.
- **Ngôn ngữ nhất quán:** event name, field key và reason code nên ổn định giữa các bản triển khai. Message cho con người có thể chọn ngôn ngữ chung của nhóm, nhưng đừng dịch tên key một cách không thống nhất.

Trong plain-text logs, dạng `key=value` không tự bảo đảm parser xử lý đúng khi giá trị có dấu cách, xuống dòng hoặc dấu bằng. Với dữ liệu tùy ý, structured fields và encoder có escaping đúng định dạng đáng tin hơn.

## 4. Message template trong Java: JUL và SLF4J

Các hệ logging Java không có một kiểu placeholder dùng chung. Phải biết mã nguồn đang dùng API nào.

### java.util.logging (JUL)

JUL có thể định dạng message template với chỉ số `{0}`, `{1}`, ... qua `Formatter.formatMessage(LogRecord)`:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

// Đoạn mã minh họa bên trong một phương thức.
Logger logger = Logger.getLogger("com.example.orders");
String orderId = "ord-7";
int quantity = 3;

logger.log(Level.INFO,
        "event=order_accepted orderId={0} quantity={1}",
        new Object[]{orderId, quantity});
~~~

Đoạn này không phải một chương trình độc lập. Kết quả cuối cùng do formatter/handler của JUL quyết định. Mẫu `{0}` là chỉ số tham số, **không phải** cú pháp `{}` của SLF4J.

Một lợi ích của việc truyền parameter array là ứng dụng không tự nối chuỗi trước lời gọi `logger.log`; việc các tham số được định dạng khi nào thuộc cơ chế formatter. Nhưng các biểu thức dùng để tạo phần tử `new Object[]{...}` vẫn được đánh giá ngay trong Java. Đừng giả định mọi tính toán trở nên lazy.

### SLF4J

Với `org.slf4j.Logger` và backend/provider tương thích, mẫu message thường dùng dấu `{}`:

~~~java
// Trong một phương thức có sẵn logger, orderId, quantity.
logger.info("event=order_accepted orderId={} quantity={}", orderId, quantity);
~~~

Hai API có kiểu Logger khác nhau. Gọi `logger.info("orderId={}", orderId)` trên JUL Logger không hoạt động như SLF4J, vì JUL không dùng mẫu `{}` và overload khác nhau.

Đối số của hàm Java vẫn được **đánh giá trước** lời gọi; khi muốn tạo dữ liệu debug đắt tiền, có thể kiểm tra level:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("event=cache_inspection details={}", buildExpensiveSummary());
}
~~~

Đây là đoạn mã minh họa SLF4J: `buildExpensiveSummary()` là phương thức giả định của ứng dụng. Nếu giá trị đã sẵn có và rẻ để truy xuất, placeholder thường đủ; không nhất thiết bao mọi câu lệnh log trong `if`. SLF4J 2.x cũng có fluent/lazy API, nhưng phải dùng đúng các overload hỗ trợ trì hoãn.

Một cách không phù hợp ở đường xử lý nhiều lần:

~~~java
logger.debug("Debug dump: " + buildExpensiveSummary());
~~~

Việc tính summary và nối chuỗi xảy ra ngay cả khi DEBUG bị tắt. Tham số hóa hoặc kiểm tra level sẽ phù hợp hơn tùy trường hợp.

## 5. Ví dụ hoàn chỉnh Java 17+: nội dung cho ba loại kết quả

Ví dụ dưới đây chỉ dùng thư viện `java.util.logging` có sẵn trong JDK, không cần Gradle hoặc Maven. Chương trình phát ba sự kiện: một đơn hàng được chấp nhận, một đơn hàng bị từ chối và một bước thanh toán thất bại. Nội dung message gồm **tên event, outcome, mã liên hệ và reason code khi cần**, đồng thời minh họa cách gắn exception.

Tạo file **MessageContentDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageContentDemo {
    private static final Logger LOG =
            Logger.getLogger(MessageContentDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String exception = record.getThrown() == null
                        ? ""
                        : " | exception="
                        + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + exception + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        LOG.log(Level.INFO,
                "event=order_accepted outcome=accepted requestId={0} orderId={1} quantity={2}",
                new Object[]{"req-101", "ord-7", 3});

        LOG.log(Level.WARNING,
                "event=order_rejected outcome=rejected requestId={0} orderId={1} reason=invalid_quantity",
                new Object[]{"req-102", "ord-8"});

        LogRecord failure = new LogRecord(Level.SEVERE,
                "event=payment_failed outcome=failed requestId={0} orderId={1} reason=upstream_unavailable");
        failure.setParameters(new Object[]{"req-103", "ord-9"});
        failure.setThrown(new IllegalStateException("gateway unavailable"));
        LOG.log(failure);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac MessageContentDemo.java
java MessageContentDemo
~~~

**Ba dòng kết quả chính xác** do `ConsoleHandler` ghi ra **stderr**:

~~~text
INFO | event=order_accepted outcome=accepted requestId=req-101 orderId=ord-7 quantity=3
WARNING | event=order_rejected outcome=rejected requestId=req-102 orderId=ord-8 reason=invalid_quantity
SEVERE | event=payment_failed outcome=failed requestId=req-103 orderId=ord-9 reason=upstream_unavailable | exception=IllegalStateException
~~~

Phân tích:

1. Các lời gọi `LOG.log(Level, String, Object[])` truyền **message template và tham số**; `Formatter.formatMessage(record)` ghép giá trị vào vị trí `{0}`, `{1}`, `{2}`.
2. Ba tên event mô tả ba sự kiện riêng; `outcome` và `reason` giúp phân biệt thành công, từ chối hợp lệ và lỗi hệ thống.
3. `LogRecord` cuối giữ cả `parameters` và `Throwable`, nên mã có thể tách văn bản thông báo khỏi nguyên nhân exception.
4. Formatter mẫu **chỉ in tên lớp exception** để đầu ra ngắn, xác định. Trong production, formatter của lỗi nghiêm trọng thường cần ghi **stack trace có kiểm soát**; ví dụ này không có mục đích ẩn stack trace của ứng dụng thực.
5. Handler có level ALL và logger có level INFO. `setUseParentHandlers(false)` tránh in trùng bản ghi từ handler của logger cha. `ConsoleHandler` mặc định xuất ra stderr, không phải stdout.
6. Mức WARNING cho dữ liệu nhập sai là lựa chọn minh họa. Với đầu vào sai thường xuyên nhưng đã xử lý đúng, môi trường thực có thể dùng mức thấp hơn hoặc không ghi log riêng; chọn level theo tác động vận hành.

Lưu ý: cấu hình handler trong main để ví dụ độc lập. Trong ứng dụng lớn, formatter, handler/appender và level thường được cấu hình tập trung, không khởi tạo lại trong mọi lớp nghiệp vụ.

## 6. Nội dung khi có lỗi và exception

Khi có exception, message cần mô tả **công việc bị ảnh hưởng**, không chỉ sao chép tên exception. Một sự kiện lỗi tốt có thể chứa:

- **Operation**: bước gọi payment gateway, truy xuất dữ liệu, nhập file, xử lý message.
- **Outcome**: đang retry hay đã thất bại cuối cùng.
- **Dependency và scope**: dịch vụ ngoài nào, requestId/jobId nào.
- **Reason code**: loại lỗi đã xác định được, ví dụ `upstream_timeout`.
- **Throwable**: truyền cho logging API khi cần stack trace để xác định đường đi lỗi.

Ví dụ SLF4J bên trong phương thức có logger, requestId, orderId, exception:

~~~java
logger.error(
        "event=payment_authorization_failed requestId={} orderId={} reason=upstream_timeout",
        requestId, orderId, exception);
~~~

Ở các overload thích hợp của SLF4J, `Throwable` là đối số cuối được hiểu là nguyên nhân để backend có thể ghi stack trace. Đây chỉ là đoạn minh họa, không phải class Java hoàn chỉnh.

Nên tránh:

~~~java
logger.error("Error: " + exception.getMessage());
~~~

Cách này có thể làm mất stack trace và ngữ cảnh nghiệp vụ. Ngoài ra `exception.getMessage()` có thể chứa URL, SQL parameters hoặc thông tin nhạy cảm. Cần xem xét dữ liệu thực sự được đưa vào log và chính sách phân quyền xem log.

Nếu tầng thấp bắt exception rồi ném lại, và tầng cao cũng log cùng stack trace, kết quả có thể là nhiều ERROR giống nhau cho một thất bại. Nên thống nhất **tầng sở hữu log kết quả cuối**; các tầng khác chỉ log sự kiện riêng khi thực sự mang thông tin bổ sung (retry, fallback, timing).

Không phải mọi exception đều là ERROR. Một yêu cầu nghiệp vụ bị từ chối có kiểm soát khác với job thất bại sau tất cả retry.

## 7. Structured logging: message và field là hai thành phần có thể tách rời

Một event có thể được biểu diễn dạng JSON như sau (minh họa; **không phải output mặc định của JUL**):

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Order accepted",
  "event": "order_accepted",
  "outcome": "accepted",
  "requestId": "req-101",
  "orderId": "ord-7",
  "quantity": 3
}
~~~

Ở đây `message` là câu đọc được; `event`, `orderId`, `quantity` là field riêng có thể query, nhóm hoặc đếm. Nếu message thay đổi câu chữ nhưng event code giữ nguyên, truy vấn theo event vẫn hoạt động ổn định.

Trong **SLF4J 2.x**, API fluent hỗ trợ gửi key/value cùng thông điệp:

~~~java
// Đoạn mã minh họa trong phương thức có logger kiểu org.slf4j.Logger.
logger.atInfo()
        .addKeyValue("event", "order_accepted")
        .addKeyValue("outcome", "accepted")
        .addKeyValue("requestId", requestId)
        .addKeyValue("orderId", orderId)
        .addKeyValue("quantity", quantity)
        .log("Order accepted");
~~~

Khả năng hiển thị các field ở dạng JSON hoặc trong console phụ thuộc backend/provider, encoder và layout. **Việc gọi `addKeyValue` không tự biến mọi backend thành JSON logger.**

Khi chỉ dùng text log, cách viết `event=...` ngay trong message vẫn hữu ích nhưng có giới hạn: parser không tự phân biệt kiểu số và chuỗi, dấu cách hoặc xuống dòng trong giá trị có thể làm mất cấu trúc. Khi cần phân tích theo field, hãy dùng đường truyền dữ liệu có cấu trúc nhất quán.

## 8. Context: nội dung giúp truy vết giữa các lớp và service

Một request đi qua controller, service và HTTP client có thể tạo log từ các tên logger khác nhau. Message `"Failed"` không thể hiện chúng thuộc cùng một request. Một số định danh nên được gắn vào **log event**:

- `requestId` hoặc `correlationId` cho một chuỗi xử lý.
- `traceId`/`spanId` nếu tích hợp tracing; không mặc nhiên đồng nhất requestId với traceId.
- `jobId` hoặc `messageId` cho batch/background task.
- `orderId`, `batchId` hoặc mã đối tượng nghiệp vụ khi được phép ghi.
- `attempt`, `outcome` và `dependency` cho các bước retry hoặc giao tiếp hệ thống ngoài.

Có thể truyền các giá trị này qua method arguments, structured fields hoặc ngữ cảnh như MDC. Với MDC, cần truyền/khôi phục/dọn context đúng cách, đặc biệt khi thread pool hoặc công việc bất đồng bộ tái sử dụng thread. Nếu thiếu dọn context, message của request sau có thể mang requestId của request trước.

**Đừng tạo logger name động theo request ID.** Logger name nên theo package/lớp; requestId là dữ kiện của từng sự kiện.

## 9. Bảo vệ dữ liệu ngay tại nội dung message

Message có thể đi tới console, file, collector, hệ thống tìm kiếm, bản sao lưu và công cụ giám sát. Khi thông tin bí mật đã lọt vào pipeline, việc xóa khỏi tất cả nơi lưu có thể rất khó. **Ứng dụng nên loại bỏ dữ liệu nhạy cảm ngay từ nơi phát log.**

Không đưa trực tiếp vào message:

- Password, access token, API key, session cookie, Authorization header hoặc mã xác thực.
- Thông tin thẻ thanh toán, khóa riêng, dữ liệu cá nhân hoặc thông tin tài khoản không cần thiết.
- Toàn bộ HTTP request/response body, SQL parameters hay message payload nếu chưa được kiểm soát.
- `toString()` của object có thể chứa các field riêng tư hoặc thay đổi theo phiên bản.
- Exception message chứa dữ liệu người dùng, URL nhạy cảm hoặc nội dung từ hệ thống ngoài chưa được kiểm tra.

Ưu tiên một **allowlist field**: chọn các giá trị thật sự cần như `event`, `reason`, `requestId` nội bộ, `attempt`, `durationMs`. Nếu phải ghi định danh nhạy cảm, dùng phương án ẩn/rút gọn/phân quyền theo quy định của dự án.

### Tránh log injection

Dữ liệu không tin cậy có thể chứa `\\n`, dấu xuống dòng thực, ký tự điều khiển hoặc chuỗi giống tiền tố bản ghi log. Nếu ghép trực tiếp vào plain text, người xem có thể thấy một sự kiện giả hoặc mất ranh giới giữa các bản ghi.

- Chọn trường cần ghi, đặt giới hạn độ dài và tránh raw input không cần thiết.
- Với structured logging, dùng encoder có escaping đúng định dạng; với text, chuẩn hóa/escape các ký tự điều khiển theo quy ước ứng dụng.
- Không xem placeholder JUL `{0}` hoặc SLF4J `{}` là biện pháp tự động che bí mật hay bảo vệ trước mọi log injection.
- Kiểm soát cả exception và stack trace trước khi quyết định quyền truy cập log.

Việc định dạng đúng không thay thế chính sách lưu trữ, retention hoặc phân quyền.

## 10. Message ổn định giúp điều tra và cảnh báo

Nếu mỗi lần phát log ứng dụng tạo một câu khác nhau như `"Could not call API"`, `"External service failed"`, `"Remote server unavailable"`, công cụ giám sát khó biết ba câu có cùng loại sự kiện không.

Nên tách:

- **Event code**: `external_call_failed` — phân loại sự kiện ổn định.
- **Reason code**: `upstream_timeout`, `upstream_5xx`, `invalid_response` — phân loại nguyên nhân.
- **Message**: câu rõ nghĩa cho người vận hành như `"Pricing request failed"`.
- **Fields**: requestId, dependency, attempt, durationMs — dữ kiện có thể biến động.

Không xây một cảnh báo quan trọng chỉ bằng việc so khớp toàn bộ một câu message tự do nếu hệ thống đã cung cấp trường `event`, `reason`, `level`. Với logs dạng text chưa có structured fields, có thể đặt tiền tố sự kiện có quy ước ổn định, nhưng cần biết parser sẽ xử lý escape/quoting như thế nào.

Tên event, key và reason code có thể được coi là **hợp đồng quan sát** giữa ứng dụng và dashboard. Nếu thay tên, cập nhật truy vấn và kiểm tra các hệ thống tiêu thụ log.

## 11. Độ dài, tần suất và chi phí của message

Nội dung message ảnh hưởng tới CPU, memory, I/O, tốc độ mạng và chi phí lưu log. Một vài quy tắc:

1. Ghi **sự kiện có ý nghĩa**, tránh INFO ở mọi lần gọi phương thức và vòng lặp.
2. Truyền những field cần thiết, không serialize toàn bộ object graph để "dự phòng".
3. Dùng tham số hóa hoặc lazy computation khi có thể; kiểm tra level trước khi tính một debug dump đắt tiền.
4. Cân nhắc sampling, rate limiting hoặc aggregation cho sự kiện rất nhiều; không che mất các sự kiện lỗi hiếm quan trọng.
5. Giới hạn field text có thể quá dài; tránh giá trị từ hệ thống ngoài làm log chiếm nhiều megabyte.
6. Chọn `durationMs`, `processedCount` hoặc các số liệu thực sự hữu ích thay vì các mô tả dài nhưng không đo được.

Message ngắn không đồng nghĩa với message tốt: `"Error"` cực ngắn nhưng không phục vụ điều tra. Tìm độ chi tiết vừa đủ để một bản ghi độc lập có thể liên hệ với sự kiện và dữ kiện quan trọng.

## 12. Lỗi thường gặp khi viết nội dung log

| Cách viết/cách làm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| `"Error"`, `"Done"`, `"Start"` | Không rõ thao tác, kết quả, đối tượng | Tên event ổn định và outcome đúng |
| `"Request: " + requestObject` | Dài, khó tìm và có nguy cơ lộ dữ liệu | Allowlist field phù hợp |
| Chỉ ghi `ex.getMessage()` | Mất stack trace, thiếu ngữ cảnh | Truyền Throwable đúng API |
| Ghi `retry_exhausted` ở lần retry đầu | Tường thuật sai trạng thái | Phân biệt retry_scheduled và failed cuối |
| Message chứa full user input | Lộ dữ liệu, log injection | Kiểm tra nguồn, escape/encode và giới hạn độ dài |
| Message luôn thay đổi câu chữ | Query/dashboard theo text dễ vỡ | Giữ event và reason code ổn định |
| Nối chuỗi có hàm nặng ở DEBUG | Tốn công dù DEBUG tắt | isDebugEnabled hoặc lazy API |
| Mọi tầng đều log/rethrow cùng exception | Nhiều stack trace trùng | Ghi lỗi cuối ở tầng đủ ngữ cảnh |
| Tự chèn timestamp và level vào message | Dư thừa, có thể khác backend | Để framework xuất metadata |
| Tên logger chứa requestId động | Khó cấu hình và quản lý logger | Đặt ID vào context/structured field |
| Giá trị text không quote/escape | Parser tách sai trường hoặc dòng | Structured encoder hợp lệ |

## 13. Tình huống thực hành: job đồng bộ tồn kho

Giả sử worker xử lý job đồng bộ tồn kho và có tối đa ba lần thử gọi API. Đặt nội dung message theo các bước:

~~~text
event=inventory_sync_started outcome=running jobId=job-42 source=warehouse
event=inventory_sync_retry_scheduled outcome=retrying jobId=job-42 attempt=2 delayMs=500 reason=upstream_timeout
event=inventory_sync_completed outcome=completed jobId=job-42 processedCount=180 durationMs=560
~~~

Nếu tất cả lần thử đều thất bại, **thay dòng completed** bằng một kết quả khác:

~~~text
event=inventory_sync_failed outcome=failed jobId=job-42 attempts=3 reason=upstream_unavailable
~~~

Hai dòng `completed` và `failed` là **hai kết quả thay thế**, không phải hai trạng thái cuối của cùng một job. Ứng dụng có thể chọn level, field, timestamp và Throwable phù hợp ở log event; phần trên chỉ mô tả nội dung.

Hãy tự kiểm tra: với mỗi sự kiện, người đọc có xác định được job, trạng thái, reason và lần thử không? Có tránh đưa thông tin đăng nhập API và toàn bộ response body vào log không? Tên sự kiện và field đã thống nhất để truy vấn chưa?

## 14. Checklist review một message

Trước khi thêm hoặc sửa câu lệnh log:

1. Sự kiện này có cần log ở điểm và mức được chọn không?
2. Message có nói đúng **điều đã xảy ra** và **kết quả thật** không?
3. Có tên event ổn định và reason code có ý nghĩa không?
4. Có requestId/jobId/traceId hoặc định danh cần thiết để tìm log liên quan không?
5. Field có tên, kiểu và đơn vị nhất quán với toàn hệ thống không?
6. Có sử dụng đúng cú pháp tham số theo JUL hay SLF4J không?
7. Khi có exception, đã truyền Throwable để backend có thể ghi stack trace khi cần chưa?
8. Đã tránh secret, dữ liệu cá nhân không cần thiết, payload lớn và dữ liệu đầu vào nguy hiểm chưa?
9. Chi phí tạo message khi level bị tắt có hợp lý không?
10. Nếu copy riêng một bản ghi, người vận hành có thể hiểu nó và tìm bản ghi tiếp theo không?

**Ghi nhớ:** Nội dung log message tốt diễn đạt **sự kiện đúng, kết quả rõ, ngữ cảnh vừa đủ, cấu trúc ổn định và dữ liệu an toàn**. Logging API/backend quyết định định dạng và nơi xuất; ứng dụng chịu trách nhiệm về ý nghĩa của thông điệp ngay tại nơi phát.