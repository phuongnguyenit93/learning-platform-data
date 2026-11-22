# Ứng dụng phát log trong kiến trúc Java Logging

Trong kiến trúc logging, **ứng dụng là nơi phát sinh sự kiện** (log producer): mã nguồn quan sát một điều vừa xảy ra, chọn có nên ghi log hay không, đặt mức độ, thông điệp và ngữ cảnh rồi gọi logging API. Các thành phần phía sau tiếp tục quyết định lọc, định dạng, chuyển và lưu bản ghi.

Thiết kế tốt bắt đầu từ **ngữ nghĩa sự kiện ở ứng dụng**. Một backend mạnh không thể tự sửa thông điệp thiếu ngữ cảnh, log sai mức, lộ dữ liệu nhạy cảm hoặc ghi cùng một lỗi tại năm tầng gọi hàm.

## 1. Vai trò và ranh giới của ứng dụng phát log

Luồng logic thường gặp:

~~~text
Người dùng / scheduler / message / hệ thống khác
                     |
                     v
          Ứng dụng xử lý nghiệp vụ
                     |
       Điểm quan sát sự kiện có ý nghĩa
                     |
      Gọi Logger với level, message, context
                     |
                     v
        Logging API / facade (nếu có)
                     |
                     v
   Backend -> filter -> handler/appender -> đích
                     |
          stdout / stderr / file / collector
~~~

Ứng dụng chủ động chọn **điều gì đáng ghi** và **dữ kiện nào được phép ghi**. Phần phía sau có thể tự thêm timestamp, logger name, thread name, định dạng JSON, đổi đích xuất hoặc loại sự kiện theo cấu hình.

Một **lệnh gọi logger** chưa đồng nghĩa với **log đã được lưu thành công**. Bản ghi còn có thể bị loại do level/filter, bị lỗi khi ghi file, hoặc không được chuyển đi bởi pipeline thu thập. Vì vậy không dùng sự thành công của logging làm điều kiện xác nhận giao dịch nghiệp vụ.

Ba lớp trách nhiệm nên được phân biệt:

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Mã ứng dụng | Quyết định thời điểm và nội dung sự kiện | Ghi INFO sau khi đơn hàng được chấp nhận, WARN khi đầu vào bị từ chối |
| Logging API và backend | Nhận log event, lọc, định dạng, phân phối | JUL, SLF4J với Logback, Log4j 2 |
| Hạ tầng thu thập và lưu trữ | Chuyển tiếp, lập chỉ mục, tìm kiếm, giữ lại bản ghi | Container stdout → collector → hệ thống tìm kiếm log |

Không phải ứng dụng nào cũng có đủ ba tầng riêng biệt. Chương trình nhỏ có thể ghi trực tiếp ra console qua JUL; ứng dụng triển khai nhiều instance thường gửi stdout đến hệ thống thu thập tập trung.

## 2. Phát log ở đâu trong luồng nghiệp vụ?

Log có giá trị khi nó trả lời một câu hỏi vận hành hoặc chẩn đoán cụ thể: **đã xảy ra chuyện gì, ở thành phần nào, liên quan yêu cầu nào và kết quả là gì?**

Các điểm phát log thường hữu ích:

1. **Ranh giới vào/ra:** yêu cầu được tiếp nhận, tác vụ theo lịch bắt đầu/kết thúc, message được xử lý. Với lưu lượng lớn, cân nhắc mức DEBUG, lấy mẫu hoặc ghi bản tổng hợp thay vì một dòng cho mọi thao tác.
2. **Chuyển trạng thái quan trọng:** tạo đơn hàng thành công, tác vụ chuyển sang trạng thái chờ, hoạt động bị từ chối do quy tắc nghiệp vụ.
3. **Giao tiếp với hệ thống bên ngoài:** gọi service, database, hàng đợi hoặc storage thất bại, timeout, retry, fallback và kết quả cuối cùng.
4. **Bất thường đáng điều tra:** dữ liệu không hợp lệ ngoài dự kiến, tài nguyên sắp cạn, circuit breaker mở, lỗi không thể khôi phục.
5. **Sự kiện vòng đời:** dịch vụ sẵn sàng phục vụ, cấu hình liên quan được nạp, shutdown hoàn tất.

Không cần ghi mọi lần vào/ra của mọi phương thức ở mức INFO. Mật độ quá cao khiến sự kiện quan trọng bị chìm, tăng chi phí lưu trữ và gây tác động lên hiệu năng.

### Chọn vị trí ghi và tránh lặp

Giả sử tầng repository gặp lỗi timeout, tầng service retry được hai lần rồi HTTP controller trả về lỗi. Nếu repository, service và controller đều gọi logger.error với cùng stack trace, một lần thất bại trở thành ba bản ghi ERROR gây nhiễu.

Một nguyên tắc thực dụng là **ghi sự kiện tại nơi có đủ ngữ cảnh để giải thích quyết định**:

- Tầng thấp có thể ghi DEBUG cho lần thử tạm thời, hoặc chỉ ném exception kèm nguyên nhân.
- Tầng sở hữu retry có thể ghi WARN cho số lần thử thất bại đáng chú ý và kết quả fallback.
- Tầng quyết định kết quả cuối cùng ghi ERROR **một lần** nếu yêu cầu thực sự thất bại.

Đây là hướng dẫn thiết kế, không phải cấm log ở nhiều tầng. Mỗi tầng vẫn có thể ghi sự kiện riêng nếu chúng mang **thông tin khác nhau**, chẳng hạn thời gian gọi database và trạng thái HTTP cuối cùng.

Một lỗi được xử lý hoàn toàn theo đường đi bình thường có thể không cần ERROR. Ví dụ, người dùng nhập số lượng không hợp lệ thường là **từ chối nghiệp vụ có kiểm soát**, không phải sự cố hạ tầng.

## 3. Một log event nên chứa gì?

Một log event tốt có **ý nghĩa ổn định** và **ngữ cảnh vừa đủ**. Mẫu trường dữ liệu:

| Trường | Ý nghĩa |
| --- | --- |
| timestamp | Thời điểm sự kiện, thường do hệ thống logging ghi bằng UTC hoặc thời gian có múi giờ rõ ràng |
| level / severity | Mức quan trọng: INFO, WARN, ERROR… |
| logger / component | Lớp, package hoặc thành phần phát sự kiện |
| event | Tên sự kiện ổn định, ví dụ order_accepted hoặc payment_retry_exhausted |
| message | Câu ngắn mô tả sự kiện có thể đọc được |
| requestId / correlationId | Mã liên hệ các bản ghi thuộc cùng một yêu cầu hoặc luồng xử lý |
| traceId / spanId | Liên kết đến distributed tracing nếu hệ thống có tích hợp |
| orderId / jobId | Định danh đối tượng nghiệp vụ liên quan, nếu được phép ghi |
| durationMs / attempt / outcome | Số liệu và kết quả giúp điều tra |
| exception | Kiểu exception và stack trace khi có ích để xử lý lỗi |

**Không phải sự kiện nào cũng cần đủ mọi trường.** Chọn tập trường có ý nghĩa, tên nhất quán và kiểu dữ liệu ổn định. Ví dụ INFO ghi nhận đơn hàng thành công thường cần event, orderId và requestId; ERROR do kết nối lỗi có thể cần service, attempt, timeout và exception.

Có thể hình dung một bản ghi cấu trúc như sau; đây là **minh họa định dạng**, không phải output mặc định của JUL hay SLF4J:

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.OrderService",
  "event": "order_accepted",
  "message": "Order accepted",
  "requestId": "req-101",
  "orderId": "ord-7",
  "units": 3
}
~~~

Một event name như **order_accepted** dễ lọc và tổng hợp hơn thông điệp thay đổi tùy từng nhánh mã. Mã đơn hàng, request ID và số liệu nên là các trường riêng khi backend hỗ trợ structured logging; việc nhét tất cả vào một chuỗi vẫn đọc được nhưng khó truy vấn chính xác hơn.

### Phân biệt message, event và context

- **Event**: loại sự kiện để phân nhóm, ví dụ order_rejected.
- **Message**: diễn giải cho con người, ví dụ Order rejected because units are invalid.
- **Context**: dữ kiện giải thích trường hợp cụ thể, ví dụ requestId, orderId, outcome.

Giữ event name và key ổn định giúp dashboard, câu truy vấn và cảnh báo ít bị hỏng khi câu chữ message được cải thiện.

## 4. Chọn mức log từ góc nhìn của ứng dụng

Với API kiểu SLF4J, năm mức thường gặp là TRACE, DEBUG, INFO, WARN, ERROR. Tên mức và ánh xạ có thể khác ở JUL; ví dụ JUL dùng FINE và WARNING thay vì DEBUG và WARN.

| Mức | Khi nào ứng dụng nên phát? | Ví dụ |
| --- | --- | --- |
| TRACE | Theo dõi rất chi tiết, chỉ bật khi điều tra chuyên sâu | Các bước nội bộ của một phép tính hoặc luồng xử lý |
| DEBUG | Thông tin hỗ trợ phát triển/chẩn đoán, thường tắt trên môi trường sản xuất | Giá trị quyết định một nhánh, trạng thái retry nội bộ đã lọc dữ liệu nhạy cảm |
| INFO | Mốc hoạt động bình thường có ý nghĩa | Service ready, import completed, job finished |
| WARN | Bất thường cần chú ý nhưng ứng dụng vẫn xử lý hoặc phục hồi được | Dùng fallback, retry tiếp tục, dữ liệu đầu vào bị từ chối với tần suất bất thường |
| ERROR | Thao tác hoặc thành phần đã thất bại và cần xử lý | Không hoàn tất giao dịch do dependency unavailable, job thất bại sau mọi retry |

Không gắn mức ERROR cho mọi exception hoặc WARN cho mọi dữ liệu người dùng không hợp lệ. Quan trọng là **tác động thực tế và khả năng phục hồi**, không chỉ tên exception.

Hãy nhớ rằng mức log ứng dụng yêu cầu không phải mức log cuối cùng được xuất. Nếu ứng dụng gọi DEBUG nhưng backend đang lọc từ INFO, sự kiện sẽ không xuất hiện. Khi thiếu log, cần kiểm tra cả mã phát và cấu hình runtime.

## 5. Ví dụ Java 17+: ứng dụng chủ động phát log với JUL

Để quan sát chính xác phía ứng dụng, dùng java.util.logging (JUL) có sẵn trong JDK. Ví dụ sau tạo hai kết quả nghiệp vụ khác nhau, phát sự kiện ở nhánh quyết định, mang theo correlation ID và tránh ghi dữ liệu đầu vào thô.

Tạo tệp **AppLogDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AppLogDemo {
    private static final Logger LOG =
            Logger.getLogger(AppLogDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        acceptOrder("req-101", "ord-7", 3);
        acceptOrder("req-102", "ord-8", 0);
    }

    private static void acceptOrder(String requestId,
                                    String orderId, int units) {
        LOG.fine(() -> "event=validation_started requestId=" + requestId);

        if (units <= 0) {
            LOG.log(Level.WARNING,
                    "event=order_rejected requestId={0} orderId={1} reason=invalid_units",
                    new Object[]{requestId, orderId});
            return;
        }

        LOG.log(Level.INFO,
                "event=order_accepted requestId={0} orderId={1} units={2}",
                new Object[]{requestId, orderId, units});
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AppLogDemo.java
java AppLogDemo
~~~

Đầu ra chính xác từ **ConsoleHandler tới stderr**:

~~~text
INFO event=order_accepted requestId=req-101 orderId=ord-7 units=3
WARNING event=order_rejected requestId=req-102 orderId=ord-8 reason=invalid_units
~~~

Giải thích:

1. **acceptOrder** là chỗ nắm kết quả chấp nhận hoặc từ chối. Vì vậy sự kiện log được phát ở nhánh có quyết định, không phải ngay khi vào phương thức.
2. Mỗi event có tên ổn định và requestId để liên hệ với yêu cầu. Mã đơn hàng, số lượng và lý do là dữ kiện có ích; ví dụ không ghi thông tin thanh toán hay payload đầy đủ.
3. LOG.fine nhận **Supplier**: nếu mức FINE không được bật thì nội dung message đó không cần được tạo. Ở đây Logger đặt INFO nên bản ghi FINE không xuất hiện.
4. LOG.log với tham số **{0}, {1}, {2}** dùng cơ chế format message của JUL. Đây không phải cú pháp **{}** của SLF4J.
5. ConsoleHandler được cấu hình mức ALL và formatter cố định để dễ kiểm tra, đồng thời tắt parent handlers để tránh bản ghi bị in thêm qua root logger. Trong ứng dụng thực tế, cấu hình này thường nằm ở tầng khởi động/backend thay vì được lặp lại trong từng lớp nghiệp vụ.

Ví dụ được kiểm tra với javac/java. Mức **WARNING** được chọn để minh họa tình huống bất thường; trong API hoặc dịch vụ production, một yêu cầu nhập sai thông thường có thể chỉ cần DEBUG hoặc không ghi riêng, tùy tần suất và chính sách vận hành.

## 6. Phát log qua SLF4J trong ứng dụng nhiều thư viện

Trong ứng dụng thực tế, mã nghiệp vụ thường dùng một facade như SLF4J. Điều này cho phép tác giả mã phát log mà không gắn trực tiếp từng lớp với Logback hoặc Log4j Core.

Đoạn sau minh họa **một phần của lớp dùng SLF4J 2.x**; cần slf4j-api và provider/backend phù hợp để chạy độc lập:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    void accept(String requestId, String orderId, int units) {
        LOG.atInfo()
                .addKeyValue("event", "order_accepted")
                .addKeyValue("requestId", requestId)
                .addKeyValue("orderId", orderId)
                .addKeyValue("units", units)
                .log("Order accepted");
    }
}
~~~

Phương thức fluent **atInfo().addKeyValue(...).log(...)** tạo thông điệp kèm cặp khóa/giá trị khi được hỗ trợ. **Không mặc định suy ra output JSON**: backend và layout/encoder phải được cấu hình để thể hiện các key/value. Ví dụ với Logback, pattern có thể cần thành phần dành cho key/value; định dạng thực tế phụ thuộc cấu hình.

Với phương thức SLF4J thông thường, tham số hóa như:

~~~java
LOG.info("Order {} accepted, units={}", orderId, units);
~~~

giúp tránh ghép chuỗi trong mã gọi và thuận tiện cho logging implementation. Nhưng dạng trên thường đưa giá trị vào message đã format, còn structured key/value hỗ trợ truy vấn theo trường rõ ràng hơn khi backend giữ cấu trúc.

Nếu cần ghi exception, truyền exception cho API ở vị trí đúng:

~~~java
try {
    callExternalService();
} catch (RuntimeException ex) {
    LOG.error("event=external_call_failed requestId={}", requestId, ex);
    throw ex;
}
~~~

Đây là **đoạn minh họa**, giả định các biến/phương thức được khai báo ở ngữ cảnh bên ngoài. Hãy chỉ log rồi ném lại khi tầng đó thực sự cần ghi ngữ cảnh riêng; nếu tầng bên ngoài còn ghi cùng lỗi, cần thống nhất nơi chịu trách nhiệm để tránh lặp stack trace.

## 7. Ngữ cảnh theo request, thread và tác vụ bất đồng bộ

Trong ứng dụng xử lý nhiều request, các dòng log của nhiều người dùng có thể xen kẽ. Correlation ID/trace ID cho phép ghép lại chuỗi sự kiện liên quan mà không dựa vào thứ tự dòng log.

Để ứng dụng thực sự phát log có ích, nên xác định ngữ cảnh tại **điểm vào** rồi truyền tới nơi xử lý:

- HTTP: nhận hoặc tạo requestId; dùng cùng ID trong các tầng xử lý và phản hồi nếu chính sách cho phép.
- Message queue: gắn correlation ID với message/consumer để liên hệ bước publish và consume.
- Scheduled/background job: dùng jobId hoặc executionId, ngay cả khi không tồn tại HTTP request.
- Distributed tracing: khi đã có traceId/spanId từ hệ thống tracing, đưa vào ngữ cảnh log để liên kết log với trace; không tự xem requestId và traceId là một trường giống nhau.

Một số facade/backend hỗ trợ **MDC (Mapped Diagnostic Context)**: lưu key/value theo ngữ cảnh thực thi để layout tự gắn vào log event. Ví dụ một đoạn mã **trong phương thức đã có biến requestId và logger**:

~~~java
org.slf4j.MDC.put("requestId", requestId);
try {
    logger.info("Processing request");
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Nếu sử dụng thread pool, luồng có thể được **tái sử dụng**. Thiếu phần finally có thể khiến request tiếp theo mang nhầm context cũ. MDC thường gắn với thread; khi chuyển việc sang ExecutorService, CompletableFuture hoặc luồng bất đồng bộ, **không mặc định giả định MDC sẽ được truyền đúng**. Cần cơ chế truyền/khôi phục context do framework hoặc chính ứng dụng cung cấp, đồng thời dọn context khi kết thúc tác vụ.

Khi sử dụng log structured và MDC cùng lúc, nên thống nhất tên field để tránh xuất hai requestId với giá trị khác nhau.

## 8. Tác vụ bất đồng bộ, nhiều instance và ý nghĩa của thứ tự log

Khi nhiều thread hoặc nhiều instance cùng phát log:

- Sự kiện của các luồng có thể xen kẽ; không suy ra trình tự nghiệp vụ chỉ bằng vị trí dòng trong file.
- Timestamp của máy phát có thể bị lệch đồng hồ; thời gian collector nhận log có thể khác thời điểm phát log.
- Retry có thể tạo nhiều sự kiện cùng loại; dùng requestId, attempt hoặc eventId nếu cần phân biệt từng lần thử.
- Backend có thể ghi đồng bộ hoặc đẩy vào hàng đợi bất đồng bộ; cấu hình hàng đợi, backpressure, mức ưu tiên và cơ chế shutdown ảnh hưởng đến độ trễ và khả năng mất log.
- Một câu lệnh logger được gọi trước khi process chết **không đảm bảo** sự kiện đã kịp tới hệ thống lưu trữ tập trung.

Vì vậy log phù hợp để chẩn đoán và quan sát, còn hệ thống cần **cam kết không mất sự kiện nghiệp vụ** phải sử dụng cơ chế nghiệp vụ chuyên dụng như lưu transaction/outbox hoặc audit trail có quy tắc rõ ràng. Không biến chuỗi console log thành nguồn dữ liệu duy nhất để xác nhận đã thu tiền hoặc đã ghi nhận đơn hàng.

## 9. Hiệu năng khi ứng dụng phát log

Chi phí log đến từ nhiều việc: tạo thông điệp, serialize dữ liệu, lấy stack trace, ghi vào appender và chuyển tới hệ thống khác. Ứng dụng nên hạn chế tạo công việc không cần thiết, đặc biệt trong hot path.

### Viết message có điều kiện

Ví dụ cần tránh khi DEBUG đang tắt:

~~~java
logger.debug("expensive state: " + buildLargeDebugDump());
~~~

Hàm **buildLargeDebugDump()** vẫn được gọi trước khi logger kiểm tra level. Với SLF4J, có thể dùng:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("expensive state: {}", buildLargeDebugDump());
}
~~~

Đây là đoạn mã minh họa; hàm buildLargeDebugDump giả định đã được định nghĩa. Nếu giá trị đã có sẵn và rẻ để tính, dùng placeholder thường đủ; không cần bọc mọi lệnh log trong kiểm tra level.

### Kiểm soát lưu lượng

- INFO cho mốc vận hành; DEBUG/TRACE cho dữ liệu chi tiết khi cần.
- Log một lần cho sự kiện kết quả, thay vì một dòng cho mỗi vòng lặp.
- Với sự kiện tần suất cao, cân nhắc rate limit, sampling hoặc tổng hợp count; đừng bỏ ngẫu nhiên lỗi hiếm quan trọng.
- Giới hạn độ dài message/payload và số lượng field; tránh log object có phương thức toString() tốn kém hoặc vô tình kéo toàn bộ object graph vào bản ghi.
- Quan sát cả CPU, I/O, tốc độ tăng dung lượng và các trường hợp hàng đợi async đầy. Chính sách bỏ log hoặc chặn tác vụ khi đầy phải là lựa chọn chủ động.

## 10. Bảo vệ dữ liệu tại nơi phát log

**Ứng dụng là nơi thuận tiện nhất để ngăn dữ liệu nhạy cảm lọt vào pipeline.** Khi một thông điệp đã được ghi vào collector, thao tác xóa khỏi mọi bản sao lưu và hệ thống phụ trợ có thể rất khó.

Không đưa trực tiếp vào log:

- Mật khẩu, token, API key, session cookie, Authorization header.
- Thông tin thẻ thanh toán, bí mật cá nhân và payload chứa dữ liệu nhạy cảm.
- Toàn bộ request/response hoặc SQL parameters khi chưa xác định trường nào được phép ghi.
- Nội dung exception hoặc giá trị do người dùng cung cấp nếu nó có thể chứa bí mật, dữ liệu nhạy cảm hay chuỗi quá dài.

Ưu tiên **allowlist các field cần thiết** hơn là ghi cả object rồi cố che sau. Với định danh, cân nhắc dùng ID nội bộ hoặc giá trị đã rút gọn thay vì nội dung riêng tư.

Giá trị đầu vào không tin cậy có thể chứa ký tự xuống dòng hoặc điều khiển. Nếu ghép thẳng thành text, kẻ tấn công có thể tạo bản ghi giả hoặc làm hỏng định dạng hiển thị. Dùng structured fields và encoder phù hợp; với text logs, chuẩn hóa/escape dữ liệu không tin cậy trước khi phát.

Dù dùng backend nào, chính sách phân quyền xem log và retention vẫn cần được cấu hình ở tầng hạ tầng.

## 11. Log, metric, trace và audit khác nhau thế nào?

| Loại dữ liệu | Câu hỏi chính | Khi nào dùng? |
| --- | --- | --- |
| **Log** | Sự kiện cụ thể nào đã diễn ra và ở ngữ cảnh gì? | Điều tra lỗi, phân tích nguyên nhân, theo dõi kết quả tác vụ |
| **Metric** | Có bao nhiêu sự kiện, tỉ lệ bao nhiêu, thời gian bao lâu? | Dashboard, cảnh báo ngưỡng, quan sát xu hướng |
| **Trace** | Một yêu cầu đi qua các service/span nào và mất thời gian ở đâu? | Phân tích luồng phân tán và độ trễ |
| **Audit record** | Ai thực hiện hành động được quản lý, khi nào và thay đổi gì? | Trách nhiệm giải trình, kiểm toán, lịch sử hành động cần độ tin cậy |

Một dòng log có thể mang durationMs, nhưng không thay thế metric đo latency theo phân phối. Một requestId giúp liên hệ log, nhưng không thay thế cây span của distributed tracing. Một bản ghi INFO nói payment_success không tự có bảo đảm durability, integrity và phân quyền như hệ thống audit chuyên dụng.

Các tín hiệu này bổ sung cho nhau; log event có eventId/traceId nhất quán giúp đối chiếu giữa các nguồn.

## 12. Các lỗi thiết kế thường gặp ở phía ứng dụng

| Hiện tượng | Nguyên nhân ở nguồn phát | Cách cải thiện |
| --- | --- | --- |
| Hàng nghìn dòng INFO cho một request | Ghi mỗi lần vào/ra phương thức và mỗi vòng lặp | Chọn các mốc quyết định; chuyển chi tiết sang DEBUG/TRACE |
| Không biết log thuộc request nào | Thiếu correlation ID, job ID hoặc trace context | Gắn context ở điểm vào, truyền đúng qua các tầng và qua async |
| WARN/ERROR liên tục dù ứng dụng bình thường | Gắn level theo exception thay vì tác động thực tế | Phân loại theo kết quả và yêu cầu hành động |
| Một lỗi có nhiều stack trace giống hệt nhau | Nhiều tầng log rồi rethrow cùng một lỗi | Chỉ rõ tầng sở hữu log kết quả cuối và ngữ cảnh khác biệt ở từng tầng |
| Log chứa dữ liệu nhạy cảm | Ghi nguyên payload, header, object.toString() | Allowlist field, mask/redact trước khi gọi logger |
| DEBUG làm chương trình chậm dù bị tắt | Tạo chuỗi lớn hoặc tính debug dump trước lời gọi | Lazy supplier, placeholder, isDebugEnabled khi tính toán đắt |
| Context của request A xuất hiện ở request B | Không dọn MDC trên thread pool hoặc truyền sai qua async | try/finally dọn context, propagation có kiểm soát |
| Không thấy bản ghi tại nơi mong đợi | Level, backend, filter hoặc đích output không đúng | Kiểm tra đường đi runtime từ logger tới appender/collector |
| Dùng log để quyết định giao dịch đã thành công | Nhầm diagnostic log với sự kiện được lưu bền vững | Dựa vào transaction/state và cơ chế audit/outbox phù hợp |

### Quy trình điều tra khi thiếu hoặc sai log

1. **Xác định điều kiện nghiệp vụ:** nhánh mã có thật sự được thực thi không? Có return hoặc exception trước câu lệnh log không?
2. **Kiểm tra mức phát:** logger có được bật cho mức đó ở runtime không?
3. **Kiểm tra context/message:** trường hợp đang tìm có ID đúng, tên event ổn định và dữ liệu đã được chuẩn hóa không?
4. **Kiểm tra tuyến xử lý phía sau:** API, provider/backend, filter, appender và đích nhận có khớp không?
5. **Đối chiếu môi trường:** log có xuất vào stderr thay vì stdout, container khác hoặc hệ thống khác không?
6. **Với async:** xem xét queue, shutdown, sampling và context propagation.

Bước 1–3 thuộc trách nhiệm nguồn phát; các bước sau thuộc cấu hình logging và hạ tầng. Tách rõ giúp không sửa mức log hoặc chèn thêm log vô tội vạ khi vấn đề thực chất nằm ở pipeline.

## 13. Bài tập áp dụng

Xét tác vụ đồng bộ tồn kho: worker nhận jobId, gọi API bên ngoài, retry tối đa ba lần và cuối cùng hoàn thành hoặc thất bại. Hãy xác định:

- **INFO:** một sự kiện job_completed sau khi tác vụ hoàn thành, gồm jobId, processedCount, durationMs.
- **WARN:** một sự kiện retry_scheduled khi có lỗi tạm thời đáng chú ý, gồm jobId, attempt, category và thời gian chờ, không ghi bí mật từ request.
- **ERROR:** một sự kiện job_failed khi mọi lần retry đều thất bại, chứa jobId, exception phù hợp và trạng thái cuối.
- **DEBUG:** thông tin nội bộ hỗ trợ điều tra khi chủ động bật mức chi tiết.

Tự kiểm tra: mỗi event có tên ổn định không; có phân biệt lỗi đã phục hồi và lỗi cuối không; có ghi lặp cùng stack trace không; jobId có được truyền qua worker thread không; câu lệnh log có khiến mỗi lần thử phải serialize payload lớn không?

## 14. Nguyên tắc cần ghi nhớ

Ứng dụng phát log tốt khi xác định **sự kiện có ý nghĩa**, đặt **level đúng tác động**, ghi **ngữ cảnh có thể truy vết**, giữ **schema nhất quán** và **lọc dữ liệu nhạy cảm ngay tại nguồn**. Logger chỉ là điểm phát; sự kiện còn phụ thuộc backend, bộ lọc và pipeline thu thập trước khi có thể được tìm thấy.

Khi thiết kế, hãy bắt đầu từ câu hỏi mà người vận hành cần trả lời, rồi mới quyết định vị trí gọi Logger và trường dữ liệu cần ghi. Một số ít sự kiện đúng chỗ, giàu ngữ cảnh thường hữu ích hơn lượng lớn log không có cấu trúc.