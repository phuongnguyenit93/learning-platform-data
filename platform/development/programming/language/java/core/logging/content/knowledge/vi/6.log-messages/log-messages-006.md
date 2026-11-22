# Parameter hóa message trong Java Logging

## 1. Parameter hóa message là gì?

**Parameter hóa message** (parameterized logging message) là cách khai báo một **mẫu thông điệp** có chỗ trống (placeholder), rồi cung cấp giá trị ở các đối số riêng thay vì tự nối mọi giá trị vào chuỗi trước khi gọi logger.

Ví dụ về ý tưởng:

~~~text
Template : orderId={} items={} status={}
Arguments: o-17, 3, accepted
Result   : orderId=o-17 items=3 status=accepted
~~~

Đây chỉ là dạng minh họa theo quy ước placeholder `{}` của SLF4J/Log4j 2; không phải mọi API Java đều hiểu mẫu này.

Parameter hóa giúp mã dễ đọc, giữ phần chữ ổn định giữa các sự kiện, giảm nhu cầu nối chuỗi thủ công và **có thể** tiết kiệm việc định dạng thông điệp khi mức log bị tắt. Nó cũng giúp phân biệt phần template với dữ liệu thay đổi, hữu ích cho việc nhóm các sự kiện giống nhau. Tuy vậy, parameter hóa **không tự động biến log thành JSON có cấu trúc**, **không bảo vệ dữ liệu nhạy cảm**, và **không bảo đảm mọi đối số đều được tính theo kiểu lazy**.

Mục tiêu của bài học là trả lời chính xác:

- Placeholder của từng logging API viết thế nào?
- Thông điệp được ghép khi nào; log level ảnh hưởng phần công việc nào?
- Cách ghi giá trị, exception, dữ liệu có ngữ cảnh một cách rõ ràng và an toàn?
- Khi nào dùng parameterized message, Supplier, structured logging hoặc kiểm tra level?

## 2. Ba cú pháp dễ nhầm

Các API có ngữ nghĩa khác nhau. Hãy xác định **loại logger** trước khi chọn placeholder.

| API / cơ chế | Mẫu thông điệp | Cách đưa giá trị | Lưu ý |
| --- | --- | --- | --- |
| `java.util.logging.Logger` (JUL) | `"orderId={0} items={1}"` | `logger.log(level, template, new Object[]{id, count})` | Chỉ số bắt đầu từ 0, định dạng qua `MessageFormat` ở formatter thông thường |
| SLF4J | `"orderId={} items={}"` | `logger.info(template, id, count)` | `{}` tiêu thụ đối số theo thứ tự; dùng backend/provider phù hợp |
| Log4j 2 với parameterized message | `"orderId={} items={}"` | `logger.info(template, id, count)` | Pattern kiểu `{}` thông dụng; cơ chế message factory có thể cấu hình |
| `String.format` / `"..." .formatted(...)` | `"orderId=%s items=%d"` | `String.format(template, id, count)` | Đây là định dạng chuỗi của Java, không phải quy ước mặc định của SLF4J hay JUL |

**Sai lầm rất phổ biến** là viết `LOG.info("userId={}", userId)` theo trí nhớ khi `LOG` thực chất là JUL `java.util.logging.Logger`. JUL không có overload `info(String, Object)` như SLF4J; mã đó không biên dịch. Với JUL, dùng `LOG.log(Level.INFO, "userId={0}", userId)` hoặc overload nhận mảng tham số.

Không tự thay `{0}` bằng `{}` khi chuyển framework. Nếu truyền `"id={0}"` vào SLF4J theo cách phổ biến, bạn sẽ không có placeholder `{}` để nó thay; ngược lại JUL không hiểu `{}` là chỉ số `MessageFormat`.

### Vì sao không gọi trực tiếp String.format trước khi log?

Đoạn mã:

~~~java
// Đoạn minh họa: logger là SLF4J, các biến đã tồn tại.
log.debug(String.format("orderId=%s items=%d", orderId, itemCount));
~~~

sẽ dựng chuỗi trước khi gọi `debug(...)`, kể cả khi DEBUG bị tắt. Cách phù hợp hơn trong SLF4J:

~~~java
log.debug("orderId={} items={}", orderId, itemCount);
~~~

SLF4J có thể trì hoãn bước format cuối cùng cho đến khi event được chấp nhận. **Nhưng các biểu thức tính giá trị đối số vẫn tuân theo quy tắc đánh giá của Java**; xem mục 6.

## 3. Ngữ nghĩa placeholder của JUL: {0}, {1}, ...

JUL là logging API có sẵn trong JDK. Khi dùng overload như:

~~~java
// Đoạn minh họa bên trong lớp có LOG, orderId và itemCount.
LOG.log(Level.INFO, "orderId={0} items={1}",
        new Object[] {orderId, itemCount});
~~~

logger có thể ghi template và các tham số vào một `LogRecord`. `Formatter.formatMessage(record)` theo cơ chế JUL sẽ xử lý tham số với `java.text.MessageFormat` khi thích hợp. Tùy formatter/handler, cách xuất thông điệp cuối cùng có thể khác. Để nhìn đúng mẫu đã parameter hóa, hãy chọn formatter có gọi `formatMessage(record)`.

Trong `MessageFormat`, `{0}` là giá trị tham số thứ nhất, `{1}` là tham số thứ hai. Một chỉ số có thể lặp lại, ví dụ `"orderId={0} confirmedId={0}"`. Nó không tự chuyển dấu `{}` không chỉ số thành placeholder. Các mẫu `{0,number}`, `{0,date}` có định dạng riêng của `MessageFormat`, thường phụ thuộc locale nên phải cẩn thận khi kỳ vọng đầu ra giống nhau ở mọi môi trường.

**Quy tắc dấu nháy đơn:** trong `MessageFormat`, dấu `'` có ý nghĩa đặc biệt. Muốn in một dấu nháy đơn bình thường trong chuỗi được xử lý bằng `MessageFormat`, thường phải viết `''` trong template. Ví dụ mẫu `"user=''{0}''"` với `{0} = alice` cho kết quả `user='alice'`. Mẫu `"user='{0}'"` có thể khiến phần `{0}` bị hiểu là chữ nguyên văn vì nằm trong vùng được quote. Vì vậy cần kiểm tra template có dấu nháy đơn, nhất là thông điệp tiếng Anh có `it's` hoặc dữ liệu văn bản.

Không nên nhúng nội dung không tin cậy làm **template** của `MessageFormat`. Giữ template là chuỗi do lập trình viên định nghĩa, truyền dữ liệu động trong tham số; tránh để người dùng điều khiển trực tiếp mẫu hoặc số thứ tự placeholder.

## 4. Ví dụ JDK 17 chạy độc lập và đầu ra xác định

Ví dụ dùng JUL, có formatter gọi `formatMessage(record)`. Handler riêng ghi ra stdout và flush ngay để kết quả bài tập ổn định; ứng dụng vận hành thực tế nên cấu hình handler qua hệ thống cấu hình logging của nó.

Lưu thành tệp **ParameterizedMessageDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ParameterizedMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(ParameterizedMessageDemo.class.getName());
    private static int diagnosticCalls = 0;

    private static String buildDiagnostic() {
        diagnosticCalls++;
        return "calculated";
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.INFO);
        LOG.addHandler(output);

        String orderId = "o-17";
        int itemCount = 3;

        LOG.log(Level.INFO, "orderId={0} items={1}",
                new Object[] {orderId, itemCount});
        LOG.log(Level.INFO, "orderId={0} status={1}",
                new Object[] {orderId, "accepted"});

        // FINE bị tắt, nhưng đối số của lời gọi vẫn được tính.
        LOG.log(Level.FINE, "diagnostic={0}",
                new Object[] {buildDiagnostic()});

        // Supplier không được thực thi khi FINE đang tắt.
        LOG.fine(() -> "lazyDiagnostic=" + buildDiagnostic());

        System.out.println("diagnosticCalls=" + diagnosticCalls);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ParameterizedMessageDemo.java
java ParameterizedMessageDemo
~~~

**stdout** dự kiến:

~~~text
INFO orderId=o-17 items=3
INFO orderId=o-17 status=accepted
diagnosticCalls=1
~~~

Giải thích lần lượt:

1. Mẫu thứ nhất dùng `{0}` để lấy `orderId` và `{1}` để lấy số `3`, nên dòng INFO đầu tiên chứa đúng hai giá trị.
2. Mẫu thứ hai vẫn có phần chữ ổn định `orderId=... status=...` và chỉ đổi tham số.
3. Mức `FINE` thấp hơn `INFO` nên logger loại log chi tiết. Tuy nhiên `buildDiagnostic()` ở lời gọi tham số vẫn chạy trước khi `LOG.log(...)` được gọi, làm `diagnosticCalls` tăng lên 1.
4. Lambda `() -> ...` truyền vào `LOG.fine(...)` chỉ tạo thông điệp khi mức FINE được chấp nhận, do đó không tăng biến đếm trong lần chạy này.
5. Vì dùng formatter và handler tự thiết lập, các dòng mẫu không có timestamp hoặc tên logger. Cấu hình JUL mặc định của ứng dụng khác có thể in định dạng và đích xuất khác.

**Bài tập thay đổi:** đổi cả `LOG.setLevel(Level.INFO)` và `output.setLevel(Level.INFO)` thành `Level.FINE`. Khi đó dòng `diagnostic=calculated` và `lazyDiagnostic=calculated` sẽ xuất hiện; `diagnosticCalls` sẽ là 2. Nếu chỉ đổi logger sang FINE còn handler vẫn ở INFO, thông điệp chi tiết có thể được tạo nhưng vẫn không hiển thị: **cả logger và handler đều có mức lọc**.

## 5. Parameterized message với SLF4J

SLF4J là một **facade logging ngoài JDK**. Dự án phải có dependency `slf4j-api` và provider/backend tương thích, ví dụ Logback; bản thân ví dụ sau **không biên dịch độc lập chỉ với `javac` mặc định**.

Trong một lớp có SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    public void confirm(String orderId, int itemCount, String status) {
        LOG.info("orderId={} items={} status={}",
                orderId, itemCount, status);
    }
}
~~~

Với `orderId = "o-17"`, `itemCount = 3` và `status = "accepted"`, phần **message** được render thành:

~~~text
orderId=o-17 items=3 status=accepted
~~~

Output cuối cùng còn có thể có timestamp, thread, logger name và mức INFO do layout/appender cung cấp.

### Placeholder và số lượng đối số

- `LOG.info("id={}", id)`: một placeholder, một giá trị.
- `LOG.info("id={} count={}", id, count)`: hai placeholder theo thứ tự.
- `LOG.info("id={} idAgain={}", id, id)`: nếu muốn cùng giá trị hai lần, truyền giá trị hai lần.
- Số placeholder và số đối số **không nên lệch nhau**. Các trường hợp dư/thiếu có thể tạo message không như dự kiến; quy tắc xử lý chi tiết tùy API và trường hợp đặc biệt như Throwable cuối.
- Dấu `{0}`, `%s` và `{}` không tương đương. Đọc đúng tài liệu của backend khi cần ký tự dấu ngoặc nhọn literal hoặc escaping.

Đặt các thông tin ổn định ngay trong template giúp log dễ đọc:

~~~java
LOG.info("operation=checkout orderId={} itemCount={} outcome={}",
        orderId, itemCount, status);
~~~

Template tốt nêu rõ tên và đơn vị: `durationMs={}`, `bytesRead={}`, `retryAttempt={}`. Tránh message mơ hồ như `"value={} {}"` vì sau vài tuần rất khó hiểu giá trị thuộc đối tượng nào.

### SLF4J 2.x fluent API và giá trị tính theo yêu cầu

Nếu dự án dùng **SLF4J 2.x**, fluent API có thể nhận `Supplier<?>` để trì hoãn việc tạo argument:

~~~java
// Minh họa trong lớp có LOG và order, dùng SLF4J 2.x.
LOG.atDebug()
   .addArgument(() -> safeDescribe(order))
   .log("orderDetail={}");
~~~

Một cách tương thích với nhiều phiên bản SLF4J là guard:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderDetail={}", safeDescribe(order));
}
~~~

Cả hai đều thích hợp khi `safeDescribe(order)` thực sự đắt và không có tác dụng phụ. Trong trường hợp DEBUG tắt, tránh gọi hàm mô tả dữ liệu. Nếu DEBUG bật, việc dựng mô tả vẫn tốn tài nguyên. Không lấy dữ liệu nhạy cảm hoặc truy vấn hệ thống bên ngoài chỉ để phục vụ message.

**Lưu ý:** Java phải đánh giá `orderId`, `itemCount` hay mọi biểu thức làm đối số trước khi gọi API logging bình thường. SLF4J có thể trì hoãn *formatting*, nhưng không tự làm lazy mọi biểu thức đối số. Với giá trị đã có sẵn và rẻ, gọi parameterized message trực tiếp là cách dễ đọc và thường phù hợp.

## 6. So sánh chi phí: nối chuỗi, placeholder và Supplier

Xét ba lệnh ở mức DEBUG:

~~~java
// Minh họa SLF4J, chưa phải chương trình hoàn chỉnh.
LOG.debug("customer=" + expensiveDescription(customer));
LOG.debug("customer={}", expensiveDescription(customer));
LOG.atDebug().addArgument(() -> expensiveDescription(customer))
        .log("customer={}");
~~~

| Cách | Nếu DEBUG bị tắt | Nhận xét |
| --- | --- | --- |
| Nối chuỗi | `expensiveDescription` vẫn chạy, chuỗi được tạo trước lời gọi | Tránh trên đường xử lý nóng nếu dữ liệu đắt |
| Placeholder `{}` bình thường | `expensiveDescription` vẫn chạy; việc formatter ghép message có thể được bỏ qua | Tốt hơn nối chuỗi với đối số đã sẵn, nhưng không giúp lazy phép tính đắt |
| SLF4J 2.x Supplier | Hàm mô tả không cần chạy nếu event không được chấp nhận | Thích hợp khi hàm tạo dữ liệu log thuần túy, chi phí cao |

**Không hiểu “parameterized = zero allocation”.** Java có thể boxing số nguyên, tạo mảng varargs, giữ tham chiếu đối tượng hoặc tạo log record tùy overload và framework. Kể cả khi log level tắt, một số chi phí gọi phương thức/đánh giá đối số vẫn có thể còn. Đối với thông điệp quá nhiều argument hoặc log tại hot path, hãy kiểm tra implementation thực tế và profiler thay vì dựa vào một khẳng định chung.

Không dùng phép tính nghiệp vụ bên trong `Supplier`. Ví dụ sai:

~~~java
// Sai về thiết kế: nếu DEBUG tắt, cập nhật trạng thái có thể không xảy ra.
LOG.atDebug().addArgument(() -> inventory.reserve(order))
        .log("reserved={}");
~~~

`reserve` là nghiệp vụ và có side effect; phải gọi độc lập trước, sau đó chỉ log kết quả an toàn. Khi logger bị tắt, hành vi nghiệp vụ vẫn phải đúng như khi logger bật.

## 7. Parameterized message khi ghi exception

Exception cần giữ **stack trace** và nguyên nhân, không chỉ tên hoặc message. Cách truyền Throwable khác nhau giữa API.

### Với JUL

~~~java
// Đoạn minh họa trong catch; orderId và LOG đã tồn tại.
catch (java.io.IOException e) {
    LOG.log(Level.SEVERE, "operation=loadOrder orderId=" + orderId
            + " outcome=failed", e);
    throw e;
}
~~~

`LOG.log(Level.SEVERE, String, Throwable)` dùng overload dành cho Throwable; formatter/handler phù hợp sẽ đưa stack trace vào bản ghi. Đây là **mã trong khối xử lý exception**, không thể chạy độc lập khi thiếu ngữ cảnh. Việc nối một ID ngắn vào thông điệp lỗi ở đây dễ hiểu; không biến exception thành `e.getMessage()` rồi làm mất stack trace.

Nếu muốn vừa parameter hóa phần message JUL vừa giữ Throwable, có thể dùng `LogRecord` và đặt `parameters`, `thrown` trước khi xuất qua `Logger.log(LogRecord)`, nhưng với hầu hết tình huống thông thường, API đơn giản và log ngữ cảnh ở ranh giới xử lý là lựa chọn rõ ràng hơn. Chỉ nên dùng `LogRecord` thủ công khi có yêu cầu cụ thể.

### Với SLF4J

~~~java
// Minh họa trong catch; LOG là SLF4J Logger.
catch (java.io.IOException e) {
    LOG.error("operation=loadOrder orderId={} outcome=failed",
            orderId, e);
    throw e;
}
~~~

SLF4J thường nhận diện `Throwable` cuối trong lời gọi parameterized logging là exception của sự kiện. Do đó nó có thể ghi stack trace mà không yêu cầu thêm một `{}` cho `e`. Cũng có overload `error(String, Throwable)`. Hãy dùng đúng overload và kiểm tra log format để tránh vô tình biến Throwable thành chuỗi hoặc ghi lỗi thiếu stack trace.

**Không ghi cùng một exception thành ERROR ở mọi tầng** nếu mỗi tầng chỉ ném tiếp mà không thêm thông tin cần thiết: gây trùng bản ghi, tăng chi phí và làm nhiễu quá trình điều tra. Nên chọn ranh giới chịu trách nhiệm báo cáo lỗi.

## 8. Parameterized message khác gì structured logging?

Parameterized message là **mẫu văn bản cộng với đối số**; sau khi render, nó thường trở thành chuỗi để con người đọc:

~~~text
operation=checkout orderId=o-17 durationMs=35 outcome=success
~~~

Structured logging biểu diễn các trường như các cặp khóa/giá trị riêng (thường xuất dưới JSON). Ví dụ dữ liệu minh họa:

~~~json
{
  "level": "INFO",
  "operation": "checkout",
  "orderId": "o-17",
  "durationMs": 35,
  "outcome": "success"
}
~~~

Các hệ thống thu log có thể truy vấn trường số `durationMs` hoặc lọc `outcome` dễ hơn nếu encoder và pipeline **thực sự bảo toàn kiểu dữ liệu/field**. Chỉ viết `durationMs={}` vào chuỗi không tự bảo đảm log sẽ có trường JSON `durationMs`. Một backend có thể chỉ xuất message text.

Trong SLF4J 2.x, fluent API còn hỗ trợ cặp key/value:

~~~java
// Minh họa trong lớp SLF4J 2.x, cần encoder phù hợp để xuất field.
LOG.atInfo()
   .addKeyValue("operation", "checkout")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
~~~

Việc field xuất hiện ở dạng text, JSON hay bị bỏ qua phụ thuộc provider và encoder/layout. Không giả định gọi `addKeyValue` sẽ tự khiến console hiện JSON.

**MDC (Mapped Diagnostic Context)** của một số framework thường giúp đính kèm request ID hoặc trace ID vào nhiều log trong cùng luồng xử lý. Với async/task thread, context cần được truyền hoặc quản lý đúng; không chắc mọi giá trị thread-local tự di chuyển qua thread. MDC không thay thế nội dung message có ý nghĩa, và không cho phép ghi secret.

## 9. Thiết kế template ổn định, dễ tìm kiếm

Khi xây dựng thông điệp cho một loại sự kiện, cố gắng giữ phần chữ cố định và đặt các giá trị biến động vào placeholder. Ví dụ tốt:

~~~java
LOG.info("order accepted orderId={} itemCount={}", orderId, count);
~~~

Nếu message tự xây bằng chuỗi thay đổi thứ tự hoặc dùng nhiều kiểu diễn đạt, việc tìm kiếm các sự kiện cùng loại trở nên khó hơn. Template ổn định hỗ trợ nhóm các bản ghi và theo dõi tần suất lỗi, dù việc nhóm cụ thể phụ thuộc pipeline.

Các khuyến nghị thực hành:

1. **Nêu hành động trước:** `"payment validation failed"`, `"cache entry expired"`, `"job completed"` thay vì `"Problem"` hoặc `"Done"`.
2. **Tên trường rõ:** dùng `orderId`, `itemCount`, `durationMs`, `attempt`; tránh nhãn `x`, `data` hoặc chuỗi không chú thích.
3. **Nhất quán về đơn vị:** `durationMs` khác `durationNs`; `amountCents` khác một số tiền đã format.
4. **Bảo đảm ngữ cảnh:** ID tương quan an toàn, operation, outcome, mã lỗi và trạng thái. Không nhất thiết lặp mọi field vào mọi log; chọn thông tin phục vụ chẩn đoán.
5. **Tách dữ liệu biến động khỏi mẫu:** không đưa nội dung user input thành template logger; truyền nó như đối số sau khi đã đánh giá tính an toàn.
6. **Không lạm dụng message động:** một request có hàng nghìn trường không nên đổ toàn bộ vào chuỗi chỉ vì có placeholder; kiểm soát số lượng và độ dài.

Ví dụ một dòng dễ giải thích:

~~~text
INFO operation=sendEmail templateId=welcome recipientCount=120 outcome=success durationMs=84
~~~

Không cần ghi danh sách 120 địa chỉ email hay toàn bộ nội dung thư để biết thao tác đã thành công và mất bao lâu.

## 10. Bảo mật: parameterization không tự làm dữ liệu an toàn

Một số người nhầm parameterized logging với prepared statement của SQL. **Hai cơ chế phục vụ mục đích khác nhau.** Prepared statement cho phép gửi câu lệnh và dữ liệu theo giao thức truy vấn của database; parameterized logging nhằm biểu diễn/định dạng message. Nó không tự chống mọi nguy cơ rò rỉ hoặc giả mạo log.

- Không ghi token, mật khẩu, OTP, cookie, khóa riêng, số thẻ hoặc dữ liệu cá nhân không cần thiết dưới bất kỳ log level nào.
- User input có thể chứa xuống dòng, ký tự điều khiển hoặc chuỗi giống tiền tố log, gây **log forging/log injection** nếu xuất trực tiếp dưới dạng text. Dùng encoder có escaping đúng đích, làm sạch/giới hạn trường và truy vấn theo field đã được chuẩn hóa.
- Giới hạn độ dài message và số lượng bản ghi cho input bất thường; tránh cho payload lớn làm phình log hoặc tăng allocation.
- Đặt quyền truy cập và thời gian lưu thích hợp cho hệ thống log. Dù chỉ bật TRACE/DEBUG tạm thời, bản ghi vẫn có thể được gửi tới nhiều collector và backup.
- Nếu cần ẩn danh hoặc che dữ liệu, ưu tiên chỉ lấy các trường an toàn từ đầu. Dựng chuỗi đầy đủ rồi che bằng regex có thể vừa tốn chi phí vừa bỏ sót trường mới.

Ví dụ **không nên**:

~~~java
// Minh họa SLF4J: password không được ghi dù dùng placeholder.
LOG.info("login user={} password={}", username, password);
~~~

Ví dụ **phù hợp hơn**:

~~~java
LOG.info("login attempt userId={} result={}",
        safeUserId, authenticationResult);
~~~

Dùng `safeUserId` đã qua chính sách bảo vệ dữ liệu của hệ thống, không mặc định mọi user ID đều có thể đưa vào log không hạn chế.

## 11. Checklist chọn cách viết trong một dự án

| Nhu cầu | Cách phù hợp |
| --- | --- |
| JUL, message có 1–n giá trị | `Logger.log(Level, "...{0}...{1}", params)` |
| SLF4J/Log4j 2, đối số đã có sẵn | Placeholder `{}` đúng API |
| Dựng chuỗi đắt mà log có thể bị tắt | `isLoggable`/`isDebugEnabled`, `Supplier` nếu API hỗ trợ |
| Cần log Throwable | Overload hoặc quy ước truyền `Throwable` đúng logging API |
| Cần lọc/truy vấn bằng field có kiểu dữ liệu | Structured logging và encoder phù hợp |
| Cần ràng buộc nhiều sự kiện cùng request | Correlation ID/MDC được quản lý đúng |
| Tần suất rất cao | Hạn chế event, sampling/rate limit khi phù hợp; đo CPU/GC, bytes/s, latency |
| Input không tin cậy | Chọn trường an toàn, escape/encode, giới hạn độ dài, không dùng input làm template |

Để kiểm tra hiệu năng, đừng chỉ đo thời gian gọi `logger.info(...)`. Nên xem lượng object tạo ra, formatter, I/O, queue async, p95/p99 latency, storage và số dòng log/giây với workload giống thực tế. Parameter hóa có thể giảm một phần chi phí, nhưng không thay thế việc chọn **đúng sự kiện, đúng log level và đúng lượng dữ liệu**.

## 12. Lỗi phổ biến và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Dùng `{}` trong JUL | Không đúng cú pháp parameter hóa của JUL | Dùng `{0}`, `{1}` và `Logger.log` |
| Dùng `{0}` hoặc `%s` trong SLF4J | Không đúng placeholder thông thường | Dùng `{}`; chỉ dùng formatting khác khi API hỗ trợ rõ |
| Nối chuỗi hoặc `String.format` trước lời gọi DEBUG | Chi phí dựng message xảy ra dù log bị tắt | Dùng template và Supplier/guard khi biểu thức đắt |
| Coi placeholder là lazy cho mọi tham số | Java vẫn tính biểu thức đối số | Đưa tính toán đắt vào Supplier hoặc guard nếu an toàn |
| Có ít/nhiều argument hơn placeholder | Log khó đọc, giá trị lệch vị trí | Khớp số lượng/thứ tự, kiểm tra exception cuối |
| Nhầm dấu `'` trong MessageFormat | `{0}` có thể bị in nguyên văn | Escape dấu nháy đơn đúng quy tắc |
| Chỉ ghi `e.getMessage()` khi lỗi | Mất stack trace và nơi lỗi phát sinh | Ghi `Throwable` theo overload đúng |
| Ghi object hoặc thông tin đăng nhập đầy đủ | Lộ dữ liệu, nhiều byte và allocations | Whitelist trường an toàn, giới hạn kích thước |
| Tưởng parameterized text là JSON field | Hệ thống lưu một chuỗi duy nhất | Dùng structured logging cùng encoder hỗ trợ |
| Dồn mọi log vào DEBUG/TRACE | Khối lượng log lớn, khó tra cứu | Phân loại theo sự kiện, mức và nhu cầu quan sát |

## 13. Bài tập tự kiểm tra

1. **JUL:** sửa template `"orderId={1} count={0}"` với các tham số `new Object[]{3, "o-17"}`, dự đoán message sau khi `formatMessage` áp dụng, sau đó thử đổi thứ tự hai tham số và giải thích hậu quả.
2. **DEBUG bị tắt:** từ `LOG.debug("details={}", expensiveDescription(order))`, viết lại theo hai cách: guard `isDebugEnabled()` và SLF4J 2.x `addArgument(Supplier)`. Giải thích điều kiện nào khiến hàm đắt thực sự không chạy.
3. **Exception:** viết hai đoạn log exception cho JUL và SLF4J, đảm bảo stack trace vẫn có mặt; chỉ ra vì sao `LOG.error("failed {}", e.getMessage())` không tương đương truyền Throwable.
4. **Structured logging:** với các trường `operation`, `orderId`, `durationMs`, `outcome`, viết một parameterized message và một dạng JSON tương ứng. Giải thích vì sao không thể tự động suy ra kiểu số của `durationMs` chỉ từ chuỗi text.
5. **An toàn:** nhận input người dùng có xuống dòng hoặc dấu ngoặc nhọn. Chỉ ra nguy cơ log forging và vì sao dùng placeholder không thay thế escaping ở encoder.
6. **Đo hiệu năng:** so sánh log nối chuỗi với template parameterized trong workload có DEBUG tắt, sau đó với DEBUG bật. Theo dõi CPU, allocation và byte/s; phân biệt thời gian dựng argument với thời gian format/ghi log.

**Ghi nhớ:** parameter hóa message giúp mẫu log rõ ràng, nhất quán và có thể giảm chi phí định dạng. Hãy chọn **đúng cú pháp của logger**, hiểu rằng **đối số Java vẫn được đánh giá**, dùng **Supplier/guard khi có tính toán đắt**, truyền **Throwable đúng cách**, và xử lý **dữ liệu nhạy cảm** trước khi ghi.