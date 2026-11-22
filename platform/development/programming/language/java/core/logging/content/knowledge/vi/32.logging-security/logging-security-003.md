# Log forging trong Java Logging

## 1. Khái niệm và mục tiêu bảo mật

**Log forging** (giả mạo bản ghi log), thường được xem là một dạng **log injection**, xảy ra khi dữ liệu không đáng tin cậy được đưa vào log mà không được xử lý phù hợp với định dạng đầu ra. Kẻ tấn công có thể chèn ký tự xuống dòng, dấu phân cách, ký tự điều khiển hoặc cấu trúc giả để tạo cảm giác như ứng dụng đã phát thêm sự kiện, thay đổi trường dữ liệu, che giấu lỗi hoặc gây sai lệch quá trình thu thập và phân tích log.

Ví dụ: một ứng dụng ghi tên người dùng trong log thất bại đăng nhập. Nếu tên người dùng chứa **CR/LF**, một chuỗi đầu vào có thể hiển thị thành **hai dòng log vật lý**, trong đó dòng thứ hai bắt chước timestamp, level hoặc nội dung của một sự kiện khác.

Lỗ hổng này gắn với **CWE-117: Improper Output Neutralization for Logs**. Điểm cốt lõi không phải vì Java có một API nguy hiểm duy nhất, mà vì **ranh giới tin cậy** bị vượt qua: nội dung do người ngoài kiểm soát được đối xử như cú pháp của log.

Log forging có thể làm:

- **Sai bằng chứng sự cố:** tạo bản ghi INFO hoặc ERROR giả để đánh lạc hướng điều tra.
- **Che giấu hành vi:** chèn dòng “authentication succeeded”, “access granted” hoặc thông điệp gây nhiễu sau một lỗi thật.
- **Làm sai bộ phân tích:** đánh lừa parser dựa vào timestamp, level, dấu phân cách hoặc nhiều dòng stack trace.
- **Kích hoạt hoặc triệt tiêu cảnh báo sai:** nếu hệ cảnh báo dựa vào regex của message hoặc đếm dòng thay vì cấu trúc sự kiện.
- **Gây nhiễu audit:** ảnh hưởng khả năng quy trách nhiệm khi audit log và diagnostic log chưa được bảo vệ riêng.

**Không nhầm log forging với việc sửa trực tiếp file log.** Kẻ tấn công không nhất thiết có quyền ghi file; họ có thể chỉ cần kiểm soát một giá trị được ứng dụng ghi log. Đó là lý do log forging đặc biệt đáng chú ý trong ứng dụng web, API, message consumer và background workers.

## 2. Dữ liệu đầu vào nào có thể trở thành log injection?

Bất cứ giá trị nào đi từ vùng ít tin cậy hơn vào logger đều cần xem xét:

| Nguồn | Ví dụ thường được log | Rủi ro |
| --- | --- | --- |
| HTTP request | URL path, query string, User-Agent, Referer | CR/LF, chuỗi giả timestamp/level, ký tự điều khiển |
| Form hoặc JSON body | username, email, search term, message text | Chèn dòng hoặc phá cấu trúc field |
| HTTP headers | X-Request-ID, X-Correlation-ID, forwarded metadata | Giả mạo ID, giá trị dài, ký tự không hợp lệ |
| Message broker | message key, header, payload field | Ký tự điều khiển và nhiều lần redelivery gây nhiễu |
| Tên file và đường dẫn | Uploaded filename, path segment | Ký tự xuống dòng, dấu phân cách, ký tự Unicode khó thấy |
| Thông báo lỗi | Exception message, response từ dependency | Nội dung ngoài kiểm soát có thể được nhúng vào log |
| Cơ sở dữ liệu | Dữ liệu được user tạo, tên hiển thị | Stored log injection: dữ liệu độc hại được ghi sau khi đọc từ DB |

Một giá trị lấy từ cơ sở dữ liệu **không tự trở thành đáng tin** chỉ vì đã qua lưu trữ. Nếu user tạo ra dữ liệu, đến lúc đọc rồi ghi log nó vẫn có thể mang payload gây nhiễu.

Với **MDC (Mapped Diagnostic Context)**, nguy cơ tương tự: nếu ứng dụng lấy nguyên văn **requestId** từ một header bên ngoài rồi đưa vào MDC, tất cả log trong request có thể chứa cùng payload gây giả mạo khi pattern/encoder xuất giá trị đó.

Hãy xác định đầy đủ đường đi:

~~~text
Untrusted request/message/database value
        |
        v
Java String / exception message / MDC
        |
        v
Logger API
        |
        v
Formatter / encoder / appender
        |
        v
Console / file / collector / SIEM / dashboard
~~~

Mỗi bước có thể có quy tắc parse riêng. Một giá trị an toàn ở dạng JSON được mã hóa đúng chưa chắc an toàn nếu sau đó bị decode và chèn thẳng vào một template HTML hoặc text-based alert.

## 3. Cơ chế đơn giản nhất: CRLF injection

CR là carriage return (**\r**, U+000D), LF là line feed (**\n**, U+000A). Chúng là ký tự điều khiển dùng để kết thúc hoặc di chuyển dòng. Trong môi trường ghi log dạng text line-oriented, nếu message chứa CRLF và formatter không trung hòa các ký tự đó, một event có thể trông giống nhiều dòng.

Ví dụ dữ liệu đầu vào minh họa:

~~~text
guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success
~~~

Trong đoạn hiển thị trên, cặp **\r\n** biểu thị CR và LF; khi payload thật chứa hai ký tự điều khiển đó, log raw có thể bị tách thành:

~~~text
2026-11-10T02:41:59Z WARN event=login_rejected user=guest
2026-11-10T02:42:00Z INFO user=admin action=login_success
~~~

Dòng thứ hai không nhất thiết do ứng dụng phát; nó có thể chỉ là **phần còn lại của một giá trị user**. Nếu collector tách event bằng newline rồi bộ tìm kiếm diễn giải dòng thứ hai như sự kiện độc lập, người điều tra có thể hiểu sai.

Phân biệt **log event** và **physical line**:

- Một event có thể có message chứa nhiều dòng hợp lệ, như stack trace.
- Một dòng vật lý không luôn tương đương một event nghiệp vụ.
- Kẻ tấn công lợi dụng sự nhầm lẫn giữa hai khái niệm và parser không có cấu trúc tin cậy.

**Không dựa vào việc logger “đã có timestamp” để bảo vệ.** Timestamp do formatter thêm ở đầu event; payload user có thể tự chèn một chuỗi timestamp giả ở giữa message.

## 4. Không chỉ có CR/LF: field và format injection

Một hệ thống log có thể dùng text theo dạng:

~~~text
level=WARN user=guest status=denied event=login_failed
~~~

Nếu ứng dụng ghép trực tiếp userInput, attacker có thể đưa vào các chuỗi như:

~~~text
guest status=success role=admin
~~~

Đoạn này không có xuống dòng nhưng chứa **dấu phân cách và cặp key=value**. Nếu hệ tìm kiếm hoặc parser tách theo khoảng trắng và lấy field cuối cùng, bản ghi có thể bị diễn giải sai.

Các dạng khác:

1. **Quotation/delimiter injection:** thêm dấu ngoặc kép, dấu phẩy, dấu pipe, tab hoặc dấu bằng để thoát khỏi trường text hoặc CSV.
2. **JSON injection:** ứng dụng tự nối chuỗi JSON mà không dùng serializer, tạo JSON sai hoặc cho phép nội dung dữ liệu thay đổi cấu trúc object.
3. **Terminal control injection:** ký tự ESC/ANSI có thể thay màu, xóa dòng hoặc gây hiển thị đánh lừa khi một công cụ terminal thực thi control sequence.
4. **Unicode visual spoofing:** ký tự điều hướng viết hai chiều, ký tự vô hình hoặc Unicode line/paragraph separator có thể làm người xem và parser hiểu khác nhau.
5. **Multiline framing confusion:** dữ liệu user hoặc exception message được collector gom/tách sai thành nhiều log event.
6. **Log viewer injection:** dữ liệu độc hại được hiển thị trong dashboard HTML mà không escape. Đây là rủi ro ở lớp hiển thị, có thể dẫn đến XSS; không mặc định đồng nhất nó với CRLF forging ở lớp lưu trữ.

**Không thể bảo vệ mọi định dạng bằng cùng một phép thay thế chuỗi.** Ghi text key=value, JSON, CSV, syslog và HTML đòi hỏi quy tắc encoding phù hợp với định dạng đích.

## 5. Tại sao parameterized logging không phải giải pháp đầy đủ?

Trong SLF4J, lập trình viên thường viết:

~~~java
logger.warn("Login rejected for user={}", username);
~~~

Thay vì:

~~~java
logger.warn("Login rejected for user=" + username);
~~~

Cách dùng placeholder có lợi: tránh nối chuỗi trước khi biết log có bật không, giữ message template ổn định trong một số cấu hình và giảm lỗi format. Tuy nhiên **placeholder không mặc nhiên trung hòa CR/LF, dấu phân cách hoặc ký tự điều khiển**. Khi formatter xuất dữ liệu username vào text, ký tự nguy hiểm vẫn có thể được giữ nguyên nếu encoder không xử lý.

**Parameterized logging khác prepared statement của SQL.** SQL parameter binding giải quyết cách biểu diễn giá trị trong ngôn ngữ truy vấn; SLF4J placeholders không phải cơ chế ràng buộc an toàn về cú pháp cho mọi log sink.

Cũng không thể chỉ dựa vào **logger API**: việc một giá trị có được escape hay không phụ thuộc **formatter/encoder, schema, collector và ứng dụng hiển thị**. Nên áp dụng phòng vệ ở ranh giới nhận dữ liệu hoặc ranh giới tạo log event tùy loại trường và định dạng đã thiết kế.

## 6. Ví dụ Java 17 chạy độc lập: log raw và log đã trung hòa

Ví dụ sau cố ý mô phỏng một payload CRLF để chứng minh sự khác biệt giữa **hai dòng vật lý** và **một giá trị được escape**. Chương trình chỉ dùng Java SE 17, không cần SLF4J hay Logback.

Tạo file **LogForgingDemo.java**:

~~~java
import java.util.Locale;

public class LogForgingDemo {
    private static String escapeField(String input) {
        if (input == null) {
            return "<null>";
        }

        StringBuilder output = new StringBuilder();
        for (int i = 0; i < input.length();) {
            int cp = input.codePointAt(i);
            i += Character.charCount(cp);

            switch (cp) {
                case '\\' -> output.append("\\\\");
                case '"'  -> output.append("\\\"");
                case '\r' -> output.append("\\r");
                case '\n' -> output.append("\\n");
                case '\t' -> output.append("\\t");
                default -> {
                    boolean risky =
                            Character.isISOControl(cp)
                            || cp == 0x2028
                            || cp == 0x2029
                            || Character.getType(cp) == Character.FORMAT;
                    if (risky) {
                        output.append("\\u{")
                              .append(Integer.toHexString(cp)
                                      .toUpperCase(Locale.ROOT))
                              .append("}");
                    } else {
                        output.appendCodePoint(cp);
                    }
                }
            }
        }
        return output.toString();
    }

    public static void main(String[] args) {
        String input = "guest\r\n"
                + "2026-11-10T02:42:00Z INFO user=admin action=login_success";

        String raw = "WARN event=login_rejected user=\"" + input + "\"";
        String safe = "WARN event=login_rejected user=\""
                + escapeField(input) + "\"";

        System.out.println("rawPhysicalLines=" + raw.lines().count());
        System.out.println("safePhysicalLines=" + safe.lines().count());
        System.out.println("safeRecord=" + safe);
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac LogForgingDemo.java
java LogForgingDemo
~~~

Stdout chính xác của chương trình:

~~~text
rawPhysicalLines=2
safePhysicalLines=1
safeRecord=WARN event=login_rejected user="guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success"
~~~

Ý nghĩa:

1. Chuỗi **input** trong Java thực sự chứa CRLF vì mã nguồn dùng escape sequence **\r\n**.
2. **String.lines()** xem CRLF là một dấu ngắt dòng, nên bản ghi raw có hai dòng vật lý.
3. **escapeField** biến CR/LF thành các ký tự dấu gạch chéo ngược và chữ **r/n**, không tạo ngắt dòng mới. Vì vậy safeRecord là một dòng vật lý.
4. Hàm còn escape dấu ngoặc kép, dấu gạch chéo ngược, tab, control characters, Unicode U+2028/U+2029 và ký tự thuộc nhóm Unicode FORMAT để hạn chế spoofing hiển thị.
5. Hàm hoạt động theo **code point** để không cắt đôi surrogate pair hợp lệ của Unicode.
6. **\u{HEX}** là biểu diễn text minh họa do chương trình tự định nghĩa cho ký tự điều khiển/format ít gặp; **không phải cú pháp escape JSON tiêu chuẩn**. Không dùng hàm này thay cho JSON serializer.
7. Việc quote trường user trong log text chỉ an toàn nếu bộ phân tích downstream **hiểu và tôn trọng quy ước quote/escape**. Parser tách đơn giản theo whitespace vẫn có thể nhìn thấy các cụm key=value nằm bên trong chuỗi quoted.

**Giới hạn của ví dụ:** đây là hàm trung hòa cho một định dạng log text giả lập, không phải thư viện chống log forging dùng chung cho mọi sink. Trong production, ưu tiên các encoder và serializer đã được kiểm thử, dùng allowlist cho trường định danh, và viết test ở lớp collector/parser. Bản ghi “safe” trong ví dụ chỉ chứng minh không bị tách bằng CRLF; không chứng minh mọi parser đều không thể nhầm lẫn.

## 7. Vì sao escape output đúng định dạng quan trọng?

Phòng vệ nên dựa trên **ngữ cảnh xuất dữ liệu**:

| Đầu ra | Cách tiếp cận phù hợp | Lưu ý |
| --- | --- | --- |
| Log text line-oriented | Escape CR, LF, delimiter, control chars theo grammar | Kiểm tra parser hiểu đúng escape |
| Log JSON | Dùng JSON encoder/serializer đúng chuẩn | Không tự nối dấu ngoặc kép và key từ input |
| CSV | Dùng CSV writer xử lý quote/delimiter/newline | CSV có thể hợp lệ dù field multiline; cân nhắc pipeline |
| Syslog hoặc protocol riêng | Tuân thủ framing/escaping của protocol | Tránh nhúng CR/LF vào khung bản ghi ngoài contract |
| HTML log viewer | HTML-escape theo ngữ cảnh và cấu hình CSP phù hợp | Đây là lớp presentation, không chỉ lớp logger |
| Alert message/chat webhook | Escape/neutralize theo Markdown/HTML/JSON đích | Không lấy text user làm syntax hệ thống cảnh báo |

**JSON encoder** thường là lựa chọn tốt vì mỗi log event được đóng gói thành một object, field string được escape bởi serializer. Tuy nhiên “dùng JSON” **không tự bảo đảm toàn pipeline an toàn** nếu ứng dụng tự ghép JSON bằng nối chuỗi, collector parse sai, hoặc dashboard render nội dung như HTML không qua escaping.

Ví dụ JSON event hợp lệ:

~~~json
{
  "timestamp": "2026-11-10T02:41:59Z",
  "level": "WARN",
  "event": "login_rejected",
  "userInput": "guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success"
}
~~~

Trong JSON text trên, **\r\n** là các escape sequence ở giá trị chuỗi JSON; một JSON serializer đúng chuẩn sẽ không chèn literal CR/LF chưa escape vào string. Một parser JSON đọc ra giá trị có newline logic trong dữ liệu, nhưng cấu trúc event vẫn là một object; khi xuất lại thành text cần escape theo sink mới.

Nếu collector dùng line-based framing, cần xác minh encoder phát **một object JSON trên một dòng** theo hợp đồng ingestion. Nếu stack trace và pretty-printed JSON tạo nhiều dòng, collector phải hỗ trợ framing phù hợp hoặc pipeline sẽ có nguy cơ chia sai event.

## 8. Validation ở đầu vào khác với encoding ở đầu ra

Một hệ thống an toàn thường cần cả **kiểm tra dữ liệu theo hợp đồng** và **escape theo nơi xuất**.

### 8.1. Trường có grammar cố định: validate hoặc từ chối

Nếu requestId do ứng dụng cấp phải là chuỗi chữ/số, dấu gạch ngang hoặc gạch dưới dài tối đa 64 ký tự, dùng allowlist:

~~~java
private static boolean validRequestId(String value) {
    return value != null
            && value.matches("[A-Za-z0-9_-]{1,64}");
}
~~~

Đây là **đoạn mã minh họa** để gắn vào class ứng dụng, không phải chương trình độc lập. Regex cố tình giới hạn một contract ví dụ; không dùng nguyên xi nếu hệ thống có ID format khác như UUID với dấu gạch ngang đã được chấp nhận (UUID vẫn nằm trong ví dụ regex này).

Nếu header requestId không hợp lệ, có thể từ chối request theo policy hoặc cấp **correlationId mới do server tạo**. Không để chuỗi bên ngoài tùy ý trở thành một trường log dùng trong mọi event hoặc một phần của tên file/index.

### 8.2. Trường văn bản tự do: escape khi xuất

Tên hiển thị hoặc phản hồi lỗi có thể hợp lệ khi chứa Unicode và dấu cách. Không phải lúc nào cũng phù hợp để từ chối chúng. Thay vào đó:

- Không lưu raw payload không cần thiết.
- Giới hạn kích thước và loại ký tự được phép theo nghiệp vụ.
- Escape chính xác theo format sink khi ghi.
- Nếu cần phân tích dữ liệu, dùng field có cấu trúc và JSON serializer.
- Nếu cần giữ nguyên thông tin làm bằng chứng, lưu trong vùng dữ liệu tin cậy với quyền và chính sách riêng, không lạm dụng text log.

**Validation không thay thế encoding**, vì giá trị hợp lệ trong nghiệp vụ có thể phá cấu trúc log; **encoding không thay thế validation**, vì một requestId quá dài hoặc có ký tự lạ có thể vẫn gây rối hoặc tăng chi phí vận hành dù đã escape.

### 8.3. Tránh chuẩn hóa sai thứ tự

Các hệ thống có thể decode URL, JSON escape hoặc Unicode trước khi log. Một kiểm tra chỉ nhìn chuỗi chưa decode có thể bỏ qua newline xuất hiện sau khi decode. Xác định rõ **giá trị thực sự được đưa vào logger sau các bước decode/normalization** và áp dụng quy tắc ở đúng boundary.

Không decode lặp tùy ý với dữ liệu attacker cung cấp; vừa dễ gây sai contract, vừa tạo khả năng parser ở hai tầng hiểu khác nhau. Tập trung vào validation theo domain và output encoding theo sink thực tế.

## 9. Cách sử dụng SLF4J, Logback và MDC an toàn hơn

### 9.1. Đặt event code cố định

Một thực hành tốt là dùng **eventName/errorCode do code định nghĩa**, không dùng chuỗi đầu vào làm tên sự kiện hoặc level:

~~~java
logger.warn("event=login_rejected requestId={} reason={}",
        requestId, "invalid_credentials");
~~~

Đây là mã tích hợp, giả sử **logger** là SLF4J Logger. Các giá trị động vẫn cần được kiểm soát theo sink; nhưng eventName và reasonCode đã có miền giá trị hữu hạn giúp hạn chế việc nhầm cú pháp.

### 9.2. Gắn context đúng phạm vi

Với MDC:

~~~java
import org.slf4j.MDC;

void withRequestContext(String verifiedRequestId, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", verifiedRequestId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Đây là **trích đoạn tích hợp**, cần SLF4J provider. **verifiedRequestId** phải được validate hoặc do server tạo trước khi vào phương thức. Việc đặt tên biến không tự khiến giá trị đáng tin; mã ở boundary phải bảo đảm điều đó.

Trong thread pool, dọn/khôi phục MDC ở **finally** tránh rò context từ request trước sang request sau. Với CompletableFuture/ExecutorService, MDC thường không tự propagate sang thread mới; cần cơ chế context propagation được stack/framework hỗ trợ.

### 9.3. Cấu hình encoder thay vì sửa message thủ công

Ví dụ pattern Logback:

~~~xml
<pattern>%d{ISO8601} %-5level request=%X{requestId} %logger - %msg%n</pattern>
~~~

Pattern này **không tự bảo vệ khỏi forging** nếu requestId hoặc message chứa CR/LF và encoder in nguyên nội dung. Cần chọn encoder/formatter với quy tắc escaping rõ ràng hoặc validate ID và kiểm soát message trước khi xuất.

Với JSON appender, dùng encoder/serializer thực sự có khả năng escaping JSON; bảo đảm mỗi event có trường level, event, requestId, traceId và errorCode rõ ràng thay vì một chuỗi “key=value” ghép tay.

Không trộn bừa nhiều tầng escaping: một field đã encode cho JSON, rồi tiếp tục escape như text hoặc HTML không đúng ngữ cảnh có thể làm hỏng giá trị hoặc gây double-escaping. Quy định một contract cụ thể cho mỗi ranh giới xuất dữ liệu.

## 10. Exception, stack trace và log nhiều dòng hợp lệ

Một Java exception thường có stack trace nhiều dòng. Việc thấy newline trong log không tự chứng minh có tấn công. Nhưng cần phân biệt **multiline do formatter tạo có kiểm soát** và **newline từ nội dung không tin cậy**.

Ví dụ:

~~~text
ERROR event=payment_failed exception=java.io.IOException
    at com.example.PaymentService.pay(PaymentService.java:42)
    at com.example.ApiHandler.handle(ApiHandler.java:18)
~~~

Một collector line-based có thể đọc các dòng bắt đầu bằng “at ...” như record khác nếu không có multiline parser hoặc structured exception field.

Giải pháp:

1. **Ghi Throwable bằng logging API** để provider biết đó là exception, không tự nối stack trace và userInput thành một String dài.
2. **Dùng structured exception fields** hoặc framing được collector hỗ trợ, khi thích hợp.
3. **Thiết kế multiline parser có quy tắc chặt** nếu dùng text log truyền thống.
4. **Không dùng regex mơ hồ** như “dòng nào bắt đầu bằng ngày tháng thì là event mới” khi một field không tin cậy có thể chứa timestamp giả.
5. **Không xóa hết stack trace** chỉ vì muốn mọi event một dòng; cần giữ dữ kiện điều tra qua định dạng an toàn.

Exception message có thể chứa dữ liệu từ dependency, SQL driver hoặc request; nó cũng phải được xem xét như dữ liệu không đáng tin khi được đưa vào log text hoặc dashboard.

## 11. Ký tự Unicode và hành vi hiển thị

Bên cạnh CR/LF, một số ký tự làm người đọc hiểu sai log:

| Nhóm | Ví dụ | Vấn đề |
| --- | --- | --- |
| ASCII control | NUL, TAB, CR, LF, ESC | Ngắt dòng, thay hiển thị, phá parser |
| C1 control | U+0085 và các mã điều khiển khác | Một số bộ đọc có cách diễn giải đặc biệt |
| Unicode separators | U+2028, U+2029 | Có thể được hiển thị hoặc xử lý như ngắt dòng |
| Directionality/format | U+202E, U+200E, các isolate marks | Đảo/thay thứ tự hiển thị của chuỗi |
| Dấu phân cách | Dấu ngoặc kép, pipe, comma, tab | Thay cách parser chia field |
| Chuỗi rất dài | Nhiều KB/MB giá trị user | Tràn giới hạn event, tăng ingestion và chi phí |

Không phải tất cả Unicode vô hình đều độc hại: zero-width joiner có thể cần thiết trong văn bản tự nhiên hoặc emoji. Với **ID kỹ thuật**, thường hợp lý để đặt grammar nghiêm ngặt. Với **nội dung người dùng tự do**, cần chính sách encoding và hiển thị vừa bảo toàn thông tin hợp lệ vừa tránh gây nhầm lẫn.

Ký tự ESC có thể tạo ANSI control sequences trên một số terminal; nếu cần lưu raw để điều tra, dùng biểu diễn đã escape trong log thông thường và nơi lưu bằng chứng riêng được kiểm soát.

## 12. Log forging, data exposure và denial-of-service liên quan thế nào?

Các lỗi này có thể cùng xuất hiện nhưng không phải một:

- **Log forging:** làm giả ngữ nghĩa hoặc cấu trúc của bản ghi.
- **Sensitive-data exposure:** ghi token, mật khẩu, thông tin cá nhân vào log.
- **Log flooding:** tạo lượng log lớn để tăng chi phí, lấp các sự kiện quan trọng hoặc gây quá tải.
- **Log viewer XSS:** đưa dữ liệu vào UI mà không escape theo ngữ cảnh HTML/JavaScript.
- **Unauthorized log modification:** sửa/xóa log sau khi được ghi, đòi hỏi quyền hoặc lỗ hổng truy cập riêng.

Một phòng vệ hiệu quả phải kết hợp:

- Validation và output encoding cho dữ liệu bên ngoài.
- Giới hạn độ dài field, kích thước event, số sự kiện và cơ chế rate limiting phù hợp.
- Không log credential, raw Authorization header hoặc payload nhạy cảm.
- Kiểm soát quyền truy cập file, collector, index và dashboard.
- Chính sách rotation, retention, audit log và kiểm toán thay đổi cấu hình.
- Cảnh báo dựa trên trường cấu trúc, thay vì regex đọc một message text tự do.

**Trung hòa CR/LF không sửa được log flooding**, cũng không ngăn một attacker nhập hàng triệu request hợp lệ. Ngược lại, rate limit không ngăn một payload CRLF lọt qua khi một event vẫn được ghi raw.

## 13. Tầng bảo vệ ở ứng dụng, collector và kho log

Một cấu trúc nhiều lớp thường đáng tin cậy hơn một regex riêng lẻ:

~~~text
[Input boundary]
  validate ID / giới hạn độ dài / phân loại untrusted data
            |
            v
[Application log event]
  event code ổn định + trường có cấu trúc + context đúng scope
            |
            v
[Encoder]
  escape theo JSON/text/protocol + kích thước event phù hợp
            |
            v
[Collector]
  parse theo schema, giữ một event có ID rõ ràng, cảnh báo parse errors
            |
            v
[Storage / SIEM / dashboard]
  phân quyền, retention, render an toàn, correlation và alert rules
~~~

Nếu ứng dụng xuất JSON một dòng, collector nên parse JSON trước khi route theo **level** hoặc **event**, thay vì quét chuỗi message để tìm một từ khóa. Nếu parse thất bại, có thể đưa event vào quarantine/dead-letter trong pipeline thay vì mặc định coi mọi dòng rời rạc là sự kiện hợp lệ.

**Không tự tin vào một lớp duy nhất.** Chẳng hạn file log không cho user ghi trực tiếp, nhưng user vẫn có thể điều khiển nội dung được ứng dụng ghi vào file. Một dashboard có HTML escaping tốt giúp giảm XSS ở UI nhưng không sửa được sai lệch cảnh báo nếu collector đã chia payload thành event giả.

Đối với audit, các biện pháp chống sửa log, quyền truy cập, retention và chuỗi bằng chứng cần được thiết kế theo yêu cầu pháp lý/nội bộ. Output encoding là cần thiết nhưng không đảm bảo tính toàn vẹn của audit trail.

## 14. Kiểm thử chống log forging

Nên thực hiện kiểm thử có dữ liệu đầu vào được kiểm soát trên **cả logger và pipeline thu thập**. Bộ test tối thiểu:

| Dữ liệu thử | Kỳ vọng |
| --- | --- |
| Tên bình thường: alice | Một event, field đúng giá trị |
| LF đơn: alice + U+000A + fake log | Không tạo event mới |
| CR đơn: alice + U+000D + fake log | Không phá hiển thị/record |
| CRLF: alice + U+000D/U+000A + fake log | Số event không tăng |
| Tab, NUL, ESC hoặc ANSI sequence | Không điều khiển terminal/parser |
| U+2028, U+2029 | Không tạo record giả theo framing |
| Bidi/format controls | Không gây hiển thị đánh lừa trong ID và UI |
| Dấu ngoặc kép, backslash, pipe, dấu bằng | Field không thoát khỏi cấu trúc dự kiến |
| Chuỗi có từ ERROR/INFO và timestamp giả | Không thành event có level/timestamp do attacker định nghĩa |
| Chuỗi rỗng/null | Không gây exception hoặc missing required field |
| Giá trị rất dài | Bị giới hạn hoặc xử lý theo policy; collector không quá tải |
| Unicode tiếng Việt/emoji hợp lệ | Bảo toàn nội dung theo schema |
| Exception message chứa CRLF | Stack trace/ngữ cảnh không bị tách sai |
| MDC requestId đến từ header | Được validate/tạo lại; không lan payload gây forging sang mọi dòng |
| Async/worker threads | Context không bị lẫn và event framing vẫn đúng |

Có thể viết **unit test** cho sanitizer/validator, nhưng **integration test** cần xác minh collector đọc bao nhiêu event thực sự. Một hàm escape có thể tạo một physical line nhưng parser downstream vẫn hiểu sai dấu phân cách; vì vậy test không nên dừng ở việc đếm newline.

Các phép kiểm tra mạnh hơn:

- Phát một request có payload CRLF; xác nhận ở backend vẫn là **một sự kiện log nghiệp vụ** chứa giá trị đã encode.
- Xác nhận **level, timestamp, eventCode** ở backend đến từ logger/encoder, không bị thay đổi do nội dung message.
- Xác nhận không có **alert giả** phát từ chuỗi attacker tự chèn.
- Thử log text lẫn JSON, các môi trường stdout/stderr và file nếu hệ thống dùng nhiều sink.
- Kiểm thử encoding/decoding của dashboard và công cụ xuất báo cáo, không chỉ index lưu trữ.
- Thử lỗi parser và giới hạn event size để biết cách pipeline xử lý dữ liệu không hợp lệ.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Tại sao chưa đủ an toàn? | Hướng xử lý |
| --- | --- | --- |
| Chỉ chuyển sang logger.warn("{}", value) | Placeholder không tự escape CR/LF ở mọi sink | Validate trường + encoder có escaping phù hợp |
| Chỉ replace("\\n", " ") | Có thể bỏ sót CR, tab, ESC, U+2028 hoặc delimiter | Kiểm tra mọi ký tự điều khiển liên quan và grammar đích |
| Tự ghép JSON bằng dấu ngoặc kép | Dấu quote/backslash/control có thể phá cấu trúc JSON | Dùng JSON serializer đáng tin |
| Ghi raw requestId vào MDC | Một payload có thể lây vào nhiều event | Validate ID trước khi gắn MDC |
| Regex tìm "ERROR" trong message | Chuỗi giả có thể kích hoạt cảnh báo | Dùng field level/event chuẩn hóa |
| Dựa vào một dòng = một event | Stack trace/pretty JSON/malicious CRLF phá framing | Dùng one-line JSON hoặc framing/multiline policy rõ |
| Strip hết Unicode ngoài ASCII | Làm mất nội dung tiếng Việt/đa ngôn ngữ hợp lệ | Validate ID kỹ thuật, encode văn bản tự do theo sink |
| Chỉ xử lý trước khi ghi file | Có thể có nhiều sink khác nhau | Kiểm thử theo toàn bộ output pipeline |
| Log mọi request body để điều tra | Tăng rủi ro privacy, injection, flooding | Chỉ log trường tối thiểu và error code |
| Giả định collector tự bảo vệ | Parser/route có thể hoạt động sai khi đầu vào malformed | Kiểm tra end-to-end và có parse-error monitoring |
| Cho phép user quyết định level/event | Thao túng alert hoặc dashboard | Event/level phải do application logic xác định |

Trong các đoạn code minh họa, dấu **\\n** trong bảng là ký tự backslash + n khi được viết như text. Một bộ lọc chỉ tìm chuỗi literal **\n** sẽ không phát hiện **LF byte thực** nếu đầu vào đã được decode thành ký tự xuống dòng. Cần phân biệt literal escape sequence và ký tự điều khiển thực tế trong từng giai đoạn xử lý.

## 16. Ứng phó khi phát hiện log forging trong production

Khi thấy log có timestamp/level lạ hoặc những dòng không khớp với luồng xử lý:

1. **Xác minh nguồn dữ liệu gốc:** đối chiếu request ID, trace ID, ingress logs, message broker metadata và sự kiện trong hệ thống ngoài log nghi vấn.
2. **Phân biệt event thật với dòng bị tách:** kiểm tra bản ghi từ ứng dụng nếu còn, log collector metadata, framing và phương thức parse.
3. **Không dùng dòng nghi vấn làm chứng cứ xác thực duy nhất:** một dòng hiển thị như “login_success” có thể xuất phát từ giá trị do attacker cung cấp.
4. **Khoanh vùng entry point:** query/header/body, exception message, stored data hoặc MDC.
5. **Áp dụng biện pháp giảm thiểu:** validate các ID có grammar cố định, encoder phù hợp, giới hạn input và log volume; triển khai có kiểm thử.
6. **Kiểm tra dashboard/alert đã bị ảnh hưởng:** xem có false alert hoặc bỏ sót incident do parser đã nhận event giả hay không.
7. **Lưu giữ dữ kiện phục vụ điều tra theo chính sách bảo mật:** hạn chế truy cập raw logs, không đưa payload nhạy cảm vào báo cáo công khai.
8. **Bổ sung regression tests:** tái hiện payload CR/LF và delimiter vào kiểm thử CI để giảm khả năng tái phát.

Không phải mọi dòng log bất thường đều là cuộc tấn công. Có thể là stack trace nhiều dòng, framework formatter hoặc lỗi collector. Chỉ kết luận khi đã xác minh ranh giới dữ liệu và cách log được phát/parse.

## 17. Checklist triển khai an toàn

Trước khi đưa Java service vào production, kiểm tra:

| Hạng mục | Tiêu chí |
| --- | --- |
| Input trust | Biết trường nào từ HTTP, broker, database hoặc dependency không đáng tin |
| Identity fields | requestId, traceId, jobId được validate hoặc tạo phía server theo contract |
| Event metadata | level, event code và timestamp không lấy từ message tùy ý |
| Text formatting | CR/LF, control chars, quote/delimiter được neutralize theo grammar |
| Structured encoding | Dùng JSON encoder/serializer thực thay vì tự nối chuỗi |
| MDC | Không chứa raw payload; gắn scope và dọn/khôi phục khi kết thúc task |
| Exception | Throwable được xử lý có cấu trúc; multiline có framing hợp lệ |
| Collector | Parse và route theo field, phát hiện event malformed |
| Alert rules | Không dựa duy nhất vào regex trên message attacker-controlled |
| Security | Không log secrets, quyền truy cập/retention được kiểm soát |
| Capacity | Có limit cho field/event và log rate |
| Tests | CR, LF, CRLF, Unicode, ANSI, delimiter, very long values và end-to-end được kiểm chứng |

**Ghi nhớ:** log forging xuất hiện khi **dữ liệu không tin cậy bị đối xử như cú pháp log**. Trong Java, hãy xác thực những trường có contract cố định, dùng encoder/serializer phù hợp với output, không coi SLF4J placeholders là sanitizer, giữ MDC sạch và kiểm thử trọn đường **ứng dụng → collector → dashboard/alert**. Mục tiêu là giữ log có giá trị điều tra mà không cho nội dung do bên ngoài kiểm soát tạo ra “sự kiện” giả.