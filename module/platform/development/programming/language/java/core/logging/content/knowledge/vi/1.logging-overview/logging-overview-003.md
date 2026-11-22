# Log message và sự kiện trong Java Logging

## Mục tiêu học tập

Sau bài này, bạn có thể: phân biệt **sự kiện xảy ra** với **thông điệp log mô tả sự kiện**; nhận diện thông tin của một bản ghi log; chọn mức độ nghiêm trọng phù hợp; thiết kế thông điệp dễ tìm kiếm, đủ ngữ cảnh và an toàn; tạo, đọc và kiểm chứng log trong Java bằng API chuẩn **java.util.logging (JUL)**.

Bài học nằm trong phần **Tổng quan Java Logging**. Trọng tâm là ý nghĩa và cách tạo *log message* cho một *event*, chưa đi sâu vào kiến trúc hoặc cấu hình chuyên biệt của Logback, Log4j 2 hay các hệ thống thu thập log tập trung.

## 1. Sự kiện (event), thông điệp (message) và bản ghi log (record)

**Sự kiện** là một điều đã xảy ra tại một thời điểm trong ứng dụng hoặc hệ thống: người dùng gửi yêu cầu, đơn hàng được tạo, kết nối cơ sở dữ liệu bị ngắt, xác thực thất bại, hoặc tác vụ chạy nền hoàn thành.

**Log message** là nội dung dùng để **diễn đạt sự kiện hoặc trạng thái đáng quan sát**. Nó có thể là chuỗi văn bản cố định, mẫu thông điệp có tham số, hoặc phần mô tả trong một bản ghi có cấu trúc.

**Log record / log entry** là đơn vị dữ liệu mà hệ thống logging tạo ra. Ngoài message, record thường chứa mức log, thời điểm, tên logger, thông tin nguồn, tham số, exception và các trường ngữ cảnh khác. Cách lưu và hiển thị phụ thuộc API, handler/appender và formatter.

Ví dụ, khi một đơn hàng được tạo thành công:

- **Sự kiện thực tế:** đơn hàng OD-42 đã được tạo với hai sản phẩm.
- **Thông điệp:** “order.created orderId=OD-42 items=2”.
- **Bản ghi:** thông điệp trên cùng level INFO, timestamp, logger của lớp xử lý đơn hàng và các trường ngữ cảnh.
- **Đích xuất:** console, tệp, hoặc hệ thống thu thập log; nơi lưu không làm thay đổi ý nghĩa sự kiện.

Một sự kiện có thể tạo ra **không, một hoặc nhiều** bản ghi log tùy chính sách quan sát. Ngược lại, một message như “Starting scheduler” có thể chỉ thông báo trạng thái vận hành, không phải sự kiện nghiệp vụ. *Event* trong chủ đề logging cũng không mặc nhiên là *domain event* hoặc message gửi vào Kafka/RabbitMQ: phát log không đồng nghĩa phát sự kiện cho hệ thống khác xử lý.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Event | Điều gì thực sự xảy ra? | Yêu cầu thanh toán bị từ chối |
| Message | Con người nên đọc mô tả gì? | “payment.declined orderId=OD-42 reason=insufficient_funds” |
| Level | Mức độ chú ý cần thiết? | WARNING cho một vấn đề cần quan tâm, tùy ngữ cảnh |
| Context | Sự kiện thuộc yêu cầu/thực thể nào? | requestId, orderId, service |
| Record | Dữ liệu logging ghi nhận cụ thể? | Timestamp + level + logger + message + metadata |
| Output | Bản ghi được chuyển tới đâu? | Console, file, hệ thống tập trung |

Sự kiện **không tự xuất hiện trong log**. Mã ứng dụng hoặc thư viện phải tạo log record; cấu hình mức log, filter, handler, tình trạng hệ thống xuất log và chính sách lấy mẫu có thể quyết định record có được xuất hay không. Vì vậy, **không tìm thấy log không chứng minh rằng sự kiện chưa từng xảy ra**.

## 2. Một bản ghi log hữu ích cần có gì?

Một record dễ phân tích thường trả lời được “**khi nào, ở đâu, chuyện gì, ảnh hưởng đến ai/cái gì và kết quả ra sao**”:

1. **Timestamp:** thời điểm phát sinh bản ghi. Khi tổng hợp nhiều hệ thống, nên dùng định dạng rõ múi giờ, phổ biến là ISO 8601/UTC.
2. **Severity/level:** mức nghiêm trọng hoặc mức chi tiết cần quan sát. Level là tín hiệu do lập trình viên chọn theo ngữ cảnh, không phải phép đo khách quan về tác động.
3. **Logger/source:** tên lớp, module hoặc thành phần phát log, ví dụ com.example.order.OrderService.
4. **Message/event name:** hành động, trạng thái và kết quả, ví dụ order.created hay order.validation_failed.
5. **Context:** định danh phù hợp như requestId, traceId, orderId, operation, thời lượng xử lý và nguyên nhân thất bại.
6. **Throwable (khi có):** loại lỗi, thông điệp lỗi và stack trace để xác định vị trí nguyên nhân.
7. **Các trường có cấu trúc:** service, environment, statusCode, durationMs… nếu hệ thống logging hỗ trợ.

Một bản ghi JSON minh họa (không phải định dạng JUL tự động xuất ra):

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.order.OrderService",
  "event": "order.created",
  "message": "Order created",
  "service": "checkout",
  "requestId": "req-8f2",
  "orderId": "OD-42",
  "itemCount": 2,
  "durationMs": 31
}
~~~

Trong log văn bản thông thường, không phải mọi trường đều có thuộc tính riêng; có thể phải nhúng một số thông tin vào message. **Structured logging** giúp tìm, lọc và tổng hợp theo trường mà không cần phân tích câu văn tự do. Không đồng nhất “message dài” với “nhiều thông tin hữu ích”: nếu thiếu định danh liên kết hoặc tên hành động thì đoạn log dài vẫn khó chẩn đoán.

## 3. Những sự kiện nào đáng ghi log?

Ưu tiên các điểm giúp truy vết luồng xử lý, phát hiện bất thường hoặc giải thích kết quả:

- **Vòng đời tác vụ:** bắt đầu/kết thúc một job quan trọng, kết quả xử lý, số lượng bản ghi, thời gian thực hiện.
- **Thay đổi trạng thái có ý nghĩa:** đơn hàng tạo thành công, yêu cầu bị từ chối, giao dịch chuyển trạng thái (không ghi dư thừa ở mọi setter).
- **Ranh giới tích hợp:** gọi dịch vụ ngoài thất bại, timeout, retry và kết quả retry; kèm tên dependency, operation và số lần thử.
- **Bất thường vận hành:** cấu hình thiếu, tài nguyên sắp cạn, dữ liệu sai bất thường, mất kết nối không mong đợi.
- **Đường xử lý lỗi:** nơi lỗi được xử lý hoặc nơi hệ thống quyết định trả về kết quả thất bại; giữ exception gốc khi cần.

Tránh ghi log cho mọi phép gán, mọi vòng lặp hoặc dữ liệu thô của mọi request: quá nhiều bản ghi tạo nhiễu, chi phí và có thể làm lộ dữ liệu. Với nghiệp vụ cần dấu vết pháp lý/kiểm toán, **audit trail** có yêu cầu riêng về tính đầy đủ, toàn vẹn, kiểm soát truy cập và lưu giữ; không nên mặc định log chẩn đoán thông thường đáp ứng được các yêu cầu đó.

**Phân biệt nguyên nhân và hậu quả:** một request HTTP trả 500 có thể là hậu quả của lỗi timeout tới dependency. Bản ghi hữu ích phải cho biết timeout ở lời gọi nào, thay vì lặp nhiều lần “request failed” ở từng lớp mà không bổ sung thông tin. Nên xác định điểm ghi log chịu trách nhiệm cho mỗi lỗi, tránh cùng một stack trace được ghi lại ở mọi tầng.

## 4. Chọn level theo ý nghĩa của sự kiện

JUL cung cấp các level chuẩn theo thứ tự mức độ từ cao xuống thấp: **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. **OFF** tắt logging; **ALL** cho phép mọi mức tại ngưỡng tương ứng. Không phải framework logging nào cũng đặt tên hoặc ánh xạ mức log giống hệt JUL.

| Level JUL | Cách dùng điển hình | Ví dụ |
| --- | --- | --- |
| SEVERE | Lỗi nghiêm trọng, thao tác hoặc thành phần không thể hoàn thành đúng chức năng | Kết nối phụ thuộc thiết yếu thất bại khiến request không thể xử lý |
| WARNING | Trạng thái bất thường cần chú ý, nhưng hệ thống có thể tiếp tục hoặc có phương án dự phòng | Retry do timeout, sử dụng cấu hình fallback |
| INFO | Mốc vận hành hoặc nghiệp vụ bình thường nhưng có giá trị theo dõi | Batch completed, order created |
| CONFIG | Thông tin cấu hình hữu ích khi khởi động/chẩn đoán | Chế độ xử lý hoặc feature flag được bật (không ghi secret) |
| FINE | Chi tiết hỗ trợ debug thông thường | Cache miss, chọn nhánh xử lý |
| FINER/ FINEST | Chi tiết rất sâu, thường có tần suất cao | Bước nội bộ của thuật toán, giá trị trung gian an toàn |

Các quy tắc thực hành:

- **Không suy level chỉ từ tên exception.** Ngoại lệ được bắt và xử lý đúng như một nhánh nghiệp vụ dự kiến có thể không cần WARNING/SEVERE.
- **Không dùng SEVERE cho kết quả từ chối hợp lệ**, chẳng hạn mật khẩu sai, nếu đó là hành vi thường gặp đã được xử lý.
- **Cảnh báo có khả năng phục hồi** nên nêu cách phục hồi (retry/fallback), kết quả cuối cùng và số lần thử nếu phù hợp.
- **Lỗi mất chức năng** nên mô tả thao tác thất bại, thành phần liên quan và exception gốc; tránh đưa thông tin nhạy cảm vào thông điệp.
- Mức log là một **ngưỡng lọc**, chưa đủ đảm bảo record xuất hiện: JUL logger và từng handler có thể có level/filter riêng.

Ví dụ: một lần gọi API timeout nhưng retry lần hai thành công có thể ghi FINE cho lần timeout nếu tình huống này là bình thường, hoặc WARNING khi độ trễ/độ bất thường cần theo dõi. Nếu các lần thử cuối cùng đều thất bại, sự kiện thất bại ở ranh giới xử lý có thể là SEVERE. Level cuối cùng phải phù hợp kỳ vọng vận hành của ứng dụng.

## 5. Thiết kế log message dễ tìm kiếm và đủ ngữ cảnh

Một thông điệp tốt thường có **tên hành động + kết quả + trường nhận diện + dữ liệu chẩn đoán vừa đủ**. Ví dụ:

| Kém hữu ích | Tốt hơn | Lý do |
| --- | --- | --- |
| “Error!” | “payment.authorization_failed orderId=OD-42 provider=bankA reason=timeout” | Biết thao tác, đối tượng, dependency và nguyên nhân |
| “Done” | “report.generated reportId=R-7 rows=125 durationMs=84” | Có kết quả đo được |
| “User data: ...” | “profile.update_rejected requestId=req-8f2 reason=invalid_email” | Không lộ dữ liệu hồ sơ |
| “Retrying” | “inventory.lookup_retry skuRef=SKU-8 attempt=2 maxAttempts=3 reason=timeout” | Có thao tác và trạng thái retry |

Các nguyên tắc:

1. **Gọi đúng tên hành động và kết quả.** Dùng từ nhất quán: created, started, completed, rejected, failed, retrying… Có thể chọn danh mục tên sự kiện ổn định như order.created.
2. **Đính kèm identifier hữu ích**, không dùng chuỗi diễn giải mơ hồ. Định danh phải được xử lý theo chính sách bảo mật; requestId/traceId giúp nối các log của một yêu cầu.
3. **Nêu đơn vị rõ ràng:** durationMs, bytes, itemCount; không để “time=40” khiến người đọc không biết đơn vị.
4. **Ưu tiên tham số hóa** thay vì nối chuỗi tốn kém hoặc lặp định dạng. Trong JUL, placeholder theo cú pháp **{0}, {1}, ...** khi truyền parameters; một số thư viện khác dùng **{}**, không được nhầm lẫn giữa các API.
5. **Giữ message gọn nhưng có ý nghĩa.** Thông điệp và trường riêng nên bổ trợ nhau; tránh dump toàn bộ object, SQL có dữ liệu thật, token hoặc payload.
6. **Dùng cấu trúc ổn định:** đổi tên event/field tùy tiện khiến truy vấn giám sát, dashboard và alert khó duy trì. Tên thông điệp chỉ là một phần của hợp đồng quan sát, không tự nó là API nghiệp vụ chính thức.

Thông điệp nên mô tả **điều được biết tại thời điểm ghi log**. Đừng ghi “order.completed” trước khi việc lưu đơn hàng thực sự thành công. Khi hệ thống bất đồng bộ, log “message.published” chỉ chứng minh bước publish đã hoàn tất theo ngữ nghĩa API tương ứng, không chứng minh consumer đã xử lý xong.

## 6. Thực hành Java 17+: ghi log sự kiện với java.util.logging

JUL có sẵn trong JDK nên ví dụ không cần thư viện bên ngoài. Tạo tệp **LogEventDemo.java** với nội dung đầy đủ sau:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogEventDemo {
    private static final Logger LOG =
            Logger.getLogger(LogEventDemo.class.getName());

    public static void main(String[] args) {
        // Tránh nhận thêm output từ handler mặc định của root logger.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + formatMessage(record);
                if (record.getThrown() != null) {
                    line += " | cause="
                            + record.getThrown().getClass().getSimpleName();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        String orderId = "OD-42";
        LOG.log(Level.INFO, "order.created orderId={0} items={1}",
                new Object[] {orderId, 2});

        try {
            Integer.parseInt("two");
        } catch (NumberFormatException ex) {
            LOG.log(Level.WARNING,
                    "order.invalid_quantity orderId=" + orderId, ex);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac LogEventDemo.java
java LogEventDemo
~~~

Kết quả của formatter minh họa (hai dòng được **ConsoleHandler ghi ra stderr**):

~~~text
INFO | order.created orderId=OD-42 items=2
WARNING | order.invalid_quantity orderId=OD-42 | cause=NumberFormatException
~~~

Giải thích:

- **Logger.getLogger(...)** tạo/lấy logger có tên lớp. Tên logger giúp truy nguồn record.
- **LOG.setLevel(Level.ALL)** cho phép các level qua ngưỡng của logger trong ví dụ; **handler.setLevel(Level.ALL)** cho phép chúng qua ngưỡng handler.
- **setUseParentHandlers(false)** tránh việc root logger cũng xuất bản ghi khiến console hiển thị trùng trong minh họa.
- **LOG.log(Level.INFO, ..., new Object[] {...})** giữ message template và parameters riêng trong LogRecord; **Formatter.formatMessage(record)** áp dụng tham số vào các placeholder {0}, {1}.
- **LOG.log(Level.WARNING, message, ex)** gắn Throwable vào record thay vì chỉ lưu ex.getMessage(). Điều này giữ được thông tin exception cho handler/formatter.
- Formatter tự viết ở đây **cố tình chỉ hiển thị loại Throwable** và bỏ timestamp/stack trace để đầu ra dễ đối chiếu. Trong ứng dụng thật, nên giữ timestamp, nguồn, trace context và stack trace phù hợp; **SimpleFormatter mặc định** có thể hiển thị stack trace và timestamp biến đổi theo lần chạy.
- **ConsoleHandler** thường ghi ra stderr, dù người dùng nhìn thấy ở cùng cửa sổ terminal. Đây không phải hành vi System.out.println().

Điểm quan trọng: **cùng một event** “đơn hàng OD-42 được tạo” đã được thể hiện thành message và record cấp INFO; tình huống parse số không hợp lệ tạo **event khác**, được ghi thành record WARNING với Throwable. Trong ứng dụng thật, chọn level cho nhập liệu không hợp lệ theo ngữ cảnh: nếu đây là lỗi nhập liệu thông thường được trả về hợp lệ, có thể không cần WARNING.

## 7. Tham số hóa, xử lý ngoại lệ và chi phí log

**Tham số hóa trong JUL**:

~~~java
// Đoạn minh họa, giả sử LOG và orderId đã được khai báo.
LOG.log(Level.INFO, "order.created orderId={0}", orderId);
~~~

Khi cần nhiều tham số, truyền một mảng Object[] theo đúng thứ tự placeholder. Cú pháp **{0}** là của JUL với MessageFormat, khác cú pháp placeholder của nhiều logging facade. Nên dùng tên trường ổn định trong message hoặc trường structured nếu backend hỗ trợ, thay vì chỉ đặt một danh sách giá trị không nhãn.

**Exception:** ghi Throwable bằng overload nhận Throwable khi thật sự cần chẩn đoán; chỉ nối ex.getMessage() vào chuỗi thường làm mất loại lỗi, chuỗi nguyên nhân và stack trace. Tránh bắt rồi ghi log nhiều lần khi cùng một exception được ném tiếp qua các tầng; tốt hơn là log tại nơi có đủ ngữ cảnh hoặc nơi lỗi được chuyển thành kết quả cuối.

**Hiệu năng:** record mức thấp có thể bị lọc trước khi xuất, nhưng biểu thức Java dùng để xây dựng tham số vẫn được đánh giá trước khi gọi method. Với thông điệp cần tính toán tốn kém, JUL hỗ trợ Supplier để trì hoãn dựng chuỗi:

~~~java
// Đoạn minh họa; expensiveSummary() là tác vụ tốn chi phí.
LOG.log(Level.FINE, () -> "cache.snapshot " + expensiveSummary());
~~~

Supplier được gọi khi logger xác định level loggable; không nên dùng Supplier có tác dụng phụ nghiệp vụ vì có thể không được gọi. Cũng có thể dùng **LOG.isLoggable(Level.FINE)** để bảo vệ việc chuẩn bị dữ liệu đắt đỏ. Logger-level check không thay thế mọi filter của handler, nên đừng dựa vào logging để thực thi logic chính.

Trong hệ thống chịu tải lớn, log ở mỗi vòng lặp hoặc mỗi request có thể tăng I/O và chi phí lưu trữ. Hãy cân nhắc level, số lượng record, sampling/rate limiting khi thích hợp, và dùng **metrics** cho các giá trị tổng hợp theo thời gian thay vì log mọi lần tăng bộ đếm.

## 8. Ngữ cảnh liên kết: theo một yêu cầu qua nhiều thành phần

Xét quy trình: API nhận request → OrderService → PaymentClient → database. Một dòng “timeout” từ PaymentClient thiếu context khó nối với request ban đầu. Các dòng có **requestId/traceId chung**, service name, operation và entity ID phù hợp sẽ dễ lần theo hành trình hơn:

~~~text
INFO  checkout.request_received requestId=req-8f2 orderId=OD-42
WARNING payment.call_timeout requestId=req-8f2 orderId=OD-42 attempt=1
INFO  payment.call_succeeded requestId=req-8f2 orderId=OD-42 attempt=2
INFO  checkout.completed requestId=req-8f2 orderId=OD-42 durationMs=310
~~~

Những dòng này là **ví dụ tình huống**, không phải stdout của chương trình ở mục 6. Trong code thực tế, có thể truyền context trực tiếp như tham số hoặc dùng cơ chế context theo thread/request của thư viện logging. Đối với xử lý bất đồng bộ hoặc thread pool, context cần được **truyền qua ranh giới thực thi và xóa khi kết thúc phạm vi** theo cơ chế đang dùng; không giả định thông tin trong ThreadLocal tự đi theo mọi tác vụ.

Nhớ rằng **thứ tự log từ nhiều máy không luôn phản ánh chính xác quan hệ nhân quả** do đồng hồ, buffer, mạng hoặc ghi bất đồng bộ. Trace và span cung cấp mô hình quan hệ các bước xử lý; logs bổ sung chi tiết. Một thiết kế quan sát tốt thường kết hợp **logs** (ngữ cảnh sự kiện), **metrics** (xu hướng/đếm/độ trễ tổng hợp) và **traces** (đường đi của một yêu cầu).

## 9. Bảo mật, chất lượng và những lỗi phổ biến

**Không đưa bí mật hoặc dữ liệu cá nhân nhạy cảm vào log.** Ví dụ tránh password, access token, session cookie, số thẻ, payload chứa dữ liệu cá nhân, hoặc connection string có credentials. Chỉ ghi định danh đã được chính sách cho phép; nếu cần, che/mã hóa băm có kiểm soát theo yêu cầu sản phẩm. Mức FINE/DEBUG **không phải vùng an toàn**: log debug có thể được bật trong môi trường thật.

**Chuẩn hóa dữ liệu không tin cậy.** Chuỗi đến từ request có thể chứa xuống dòng, ký tự điều khiển hoặc nội dung giả dạng log khác. Bộ ghi log có cấu trúc/escaping phù hợp giúp giảm rủi ro **log injection**. Không nối tùy ý payload nguyên bản vào record; lọc và giới hạn độ dài dữ liệu đầu vào trước khi logging theo chính sách của ứng dụng.

**Một số lỗi hay gặp và cách sửa:**

1. **Thông điệp chung chung:** “Something went wrong”. Sửa bằng thao tác, thành phần, identifier và nguyên nhân có thể biết.
2. **Sai mức nghiêm trọng:** mọi lỗi nhập liệu đều SEVERE. Sửa bằng cách phân loại tác động thực tế và đường xử lý.
3. **Mất exception:** chỉ ghi ex.getMessage(). Sửa bằng overload nhận Throwable khi cần phân tích lỗi.
4. **Log trùng ở nhiều tầng:** mỗi catch log rồi rethrow. Chọn điểm log chịu trách nhiệm, bổ sung ngữ cảnh thay vì sao chép cùng stack trace.
5. **Log thành công quá sớm:** ghi completed trước khi transaction/IO hoàn tất. Chuyển log tới sau bước xác nhận thực sự.
6. **Thiếu correlation ID:** các dòng không thể nối với request. Truyền identifier xuyên các bước đồng bộ/bất đồng bộ.
7. **Spam log hoặc tính message quá đắt:** dùng level phù hợp, Supplier, guard, metrics, hoặc sampling.
8. **Ghi dữ liệu nhạy cảm:** loại bỏ hoặc che dữ liệu; kiểm tra cả exception message và nội dung object tự động in ra.
9. **Nhầm log với bảo đảm nghiệp vụ:** một record đã ghi không đảm bảo event được gửi, xử lý, lưu bền hoặc chỉ xảy ra một lần. Độ tin cậy nghiệp vụ phải do thiết kế giao dịch, queue/outbox/audit tương ứng đảm bảo.

Đối với exception, **stack trace hữu ích nhưng không thay thế message đủ ngữ cảnh**: stack trace cho biết lỗi nảy sinh ở đâu, còn thông điệp nên cho biết thao tác nào thất bại và thực thể/yêu cầu nào bị ảnh hưởng (khi định danh đó được phép ghi).

## 10. Quy trình chọn và viết log message

Khi thêm một log vào code, tự hỏi theo thứ tự:

1. **Điều gì đã xảy ra?** Xác định rõ event và thời điểm được xem là thành công/thất bại.
2. **Ai cần đọc bản ghi?** Người debug, vận hành, hoặc công cụ cảnh báo; thông tin nào giúp họ hành động?
3. **Level nào đúng?** Ưu tiên tác động và kỳ vọng vận hành, tránh biến mọi kết quả nghiệp vụ thành lỗi hệ thống.
4. **Ngữ cảnh nào tối thiểu đủ?** Action/result, service/logger, requestId/traceId, entity ID phù hợp, reason và duration có đơn vị.
5. **Exception có cần thiết không?** Nếu cần điều tra nguyên nhân, truyền Throwable đúng overload và tránh log trùng.
6. **Log có an toàn và chịu tải được không?** Không chứa secrets/PII, tránh multiline injection, message đắt đỏ và các record tần suất cao.
7. **Có kiểm chứng được không?** Thực hiện một luồng thành công và một luồng thất bại; kiểm tra level, ngữ cảnh, tham số, exception và không có dòng trùng.

Ví dụ kiểm tra tư duy:

- Trường hợp A: user nhập số lượng “two”, ứng dụng trả lỗi validation hợp lệ. **Event:** order.validation_rejected. **Message:** tên event + field=quantity + requestId; thường không cần log ERROR/SEVERE và không ghi toàn bộ dữ liệu nhập.
- Trường hợp B: PaymentClient timeout một lần, sau đó retry thành công. **Events:** payment.call_timeout và payment.call_succeeded. **Messages:** có attempt và correlation ID; severity tùy mức độ bất thường. Không được ghi payment.failed cuối cùng nếu giao dịch đã thành công.
- Trường hợp C: tác vụ lưu đơn hàng thất bại sau mọi retry. **Event:** order.persist_failed. **Message:** orderId, operation, mã nguyên nhân an toàn; giữ Throwable để phân tích; ghi tại tầng có trách nhiệm xử lý lỗi.

## Tự kiểm tra

**Câu 1.** Một message “job completed” có đủ làm bằng chứng job nào đã chạy, bao nhiêu item được xử lý và mất bao lâu?  
**Đáp án:** Chưa. Cần jobId, outcome, itemCount, durationMs và ngữ cảnh vận hành tương ứng.

**Câu 2.** Gọi **LOG.log(Level.INFO, "order={0}", orderId)** trong JUL có giống cú pháp **"order={}"** của một số thư viện khác?  
**Đáp án:** Không. JUL dùng placeholder đánh chỉ số theo MessageFormat khi truyền parameters.

**Câu 3.** Khi đã gọi logger.log với một Throwable nhưng formatter mẫu chỉ in tên class, có nghĩa Throwable đã bị mất?  
**Đáp án:** Không. Throwable vẫn nằm trong LogRecord; formatter ví dụ cố tình rút gọn phần hiển thị. Formatter/handler khác có thể xuất stack trace.

**Câu 4.** Không thấy dòng WARNING trong console có chứng minh không có bất thường?  
**Đáp án:** Không. Record có thể không được tạo, bị lọc theo logger/handler, bị sampling hoặc gặp sự cố trên đường xuất log.

**Ghi nhớ:** **Event** là điều xảy ra; **message** diễn đạt nó; **record** chứa message cùng level/ngữ cảnh/metadata; **handler/appender** đưa record tới đích. Ghi log đúng thời điểm, với mức độ và ngữ cảnh phù hợp, tạo dữ liệu hữu ích cho chẩn đoán mà không đánh đổi bảo mật, hiệu năng hoặc tính chính xác của nghiệp vụ.
