# Log injection trong Java: ngăn giả mạo và thao túng bản ghi logging

## 1. Mục tiêu của bài học

**Log injection** xảy ra khi dữ liệu từ nguồn không đáng tin cậy được đưa vào log mà không được xử lý phù hợp với định dạng đầu ra, khiến kẻ tấn công có thể làm thay đổi cách người hoặc công cụ đọc log hiểu bản ghi. Dạng phổ biến nhất là **log forging qua ký tự xuống dòng**: một giá trị username, URL, header hoặc exception message chứa CR/LF được ghi nguyên văn, tạo ra các dòng trông giống sự kiện hợp lệ do ứng dụng sinh ra.

Trong Java, lỗi này không chỉ có ở System.out.println. Nó có thể xuất hiện khi dùng JUL, SLF4J/Logback, Log4j 2, custom Formatter/Appender hoặc trong collector/viewer ở phía sau. Logging framework thread-safe và việc viết log bằng placeholder **không tự động bảo đảm chống log injection**.

Sau khi hoàn thành, người học có thể:

1. Giải thích log injection, log forging và lỗ hổng **CWE-117 – Improper Output Neutralization for Logs**.
2. Nhận diện dữ liệu ngoài biên tin cậy: request parameter, username, HTTP header, User-Agent, URL, message từ queue, nội dung file, exception message và trường MDC.
3. Phân biệt tấn công phá ranh giới record bằng CR/LF, chuỗi điều khiển terminal/ANSI, thao túng cấu trúc JSON/CSV, ký tự Unicode gây nhầm lẫn và metadata giả.
4. Chọn biện pháp đúng với sink: validate giá trị, giới hạn độ dài, **encode/escape tại lúc ghi**, dùng structured logging với encoder chuẩn và không để input điều khiển event schema.
5. Viết ví dụ Java 17 độc lập chứng minh input độc hại vẫn nằm trong **một log event và một dòng hiển thị**.
6. Thiết kế kiểm thử từ mã ứng dụng tới collector/dashboard, bao gồm khả năng phát hiện tấn công, mất log và sai lệch cảnh báo.

Đây là bài thuộc nhóm **Bảo mật logging**. Mục tiêu là bảo vệ **tính toàn vẹn, khả năng truy vết và khả năng diễn giải log**; không nhầm với kỹ thuật tấn công vào cơ sở dữ liệu hay cơ chế xác thực.

## 2. Cơ chế tấn công: dữ liệu thành một “dòng log mới”

Giả sử ứng dụng ghi một lần đăng nhập thất bại bằng text:

~~~java
// Ví dụ không an toàn: một giá trị do client nhập được ghi nguyên văn.
logger.warning("LOGIN_FAILED username=" + username);
~~~

Với username bình thường, bản ghi có thể là:

~~~text
WARNING LOGIN_FAILED username=alice
~~~

Nhưng username có thể chứa các ký tự carriage return (CR, U+000D) và line feed (LF, U+000A), kèm văn bản giả:

~~~text
alice\r\nINFO LOGIN_SUCCESS username=admin
~~~

Trong khối trên, \r và \n biểu diễn hai ký tự điều khiển thực sự, không phải hai dấu gạch chéo hiển thị khi lưu text. Nếu formatter/sink xuất nguyên dữ liệu vào một log theo dòng, nội dung thực tế có thể bị tách:

~~~text
WARNING LOGIN_FAILED username=alice
INFO LOGIN_SUCCESS username=admin
~~~

Dòng thứ hai **không hề là một event LOGIN_SUCCESS thật**, nhưng có thể được dashboard, bộ phân tích hoặc người điều tra hiểu sai. Kẻ tấn công có thể giả timestamp, level, actor, host, transaction ID hoặc những trường mà bộ đọc log dùng để phân loại.

Đây là **log forging**: giả mạo bản ghi hoặc thay đổi ngữ nghĩa bản ghi. Nó là một biểu hiện thường gặp của **log injection**. Không phải mọi lần log có ký tự xuống dòng đều là khai thác thành công: mức độ ảnh hưởng phụ thuộc định dạng, encoder, collector, schema và cách downstream phân tích.

### Vì sao đây là vấn đề bảo mật?

Một bản ghi giả có thể:

- Che giấu một chuỗi đăng nhập thất bại bằng cách chèn thông điệp “đăng nhập thành công”.
- Tạo cảnh báo giả, làm nhiễu quy trình incident response hoặc kết quả phân tích rủi ro.
- Gắn hành vi vào một người dùng, dịch vụ hoặc IP không liên quan.
- Làm parser bỏ qua, gộp sai hoặc đánh dấu nhầm các dòng sau.
- Ảnh hưởng thống kê, phát hiện gian lận, truy vấn audit và quyết định tự động dựa trên log.
- Lợi dụng lỗ hổng thứ cấp của log viewer/terminal hoặc hệ thống xử lý log nếu chúng không xử lý input đúng cách.

Log là **dữ liệu có thể chứa input từ attacker**, dù file được tạo bên trong server. Không được coi log message là chứng cứ không thể giả mạo chỉ vì nó do một ứng dụng tin cậy ghi ra.

## 3. Biên tin cậy trong pipeline logging Java

Một log event thường đi qua các lớp:

~~~text
HTTP request / message queue / external service / imported file
                 │
                 ▼
    Dữ liệu bên ngoài không đáng tin
                 │
                 ▼
    Java business code / exception / MDC
                 │
                 ▼
    Logger API: JUL, SLF4J, Log4j 2 API
                 │
                 ▼
    Formatter / Layout / Encoder / Appender
                 │
                 ▼
    stdout / stderr / file / syslog / broker
                 │
                 ▼
    container runtime / log collector / parser
                 │
                 ▼
    log database / SIEM / dashboard / alert
~~~

Tại **mỗi ranh giới**, dữ liệu có thể được biểu diễn theo cách khác:

- HTTP request được URL-decode và chuyển thành String Java.
- Một String chứa CR/LF hoặc escape code được formatter gắn vào text log.
- Một encoder JSON đổi newline thành escape sequence trong chuỗi JSON.
- Collector có thể chia log theo newline, parse JSON, bỏ trường không hợp lệ hoặc cắt message quá dài.
- Dashboard có thể render nội dung bằng HTML, terminal có thể diễn giải escape sequence ANSI.

Vì thế, biện pháp bảo vệ phải tương ứng **định dạng thật của sink và consumer**. Không đủ khi chỉ dùng trim() hoặc replace() một lần tại controller rồi cho rằng mọi đường đi sau đó đều an toàn.

### Các nguồn dữ liệu thường bị bỏ sót

| Nguồn | Ví dụ bị ghi log | Vấn đề |
| --- | --- | --- |
| Username, email, display name | “Login failed for …” | Có thể chứa CR/LF, quote, delimiter, Unicode |
| Request URL và query string | “Request failed: …” | Có thể chứa dữ liệu đã percent-encode, secret, chuỗi rất dài |
| User-Agent, Referer, X-Forwarded-For | Access log / security log | Có thể do client hoặc proxy không đáng tin điều khiển |
| HTTP header tùy ý | “header=value” | Có thể đã decode hoặc chuẩn hóa khác nhau ở proxy/parser |
| Message từ broker | “Payload rejected: …” | Producer ngoài hệ thống có thể cố tình chèn ký tự định dạng |
| Exception.getMessage() | “Remote error: …” | Exception có thể chứa dữ liệu người dùng hoặc bên thứ ba |
| MDC/ThreadContext | trace_id, request_id, tenant | Không phải field nào cũng do server sinh; context có thể bị giả |
| Tên file/đường dẫn | “Could not open …” | Có thể chứa delimiter, ký tự điều khiển hoặc PII |
| Đối tượng toString() | “Order: …” | Có thể phát ra dữ liệu ngoài biên, field quá dài hoặc bí mật |

Thông điệp log do lập trình viên tự viết là nguồn tin cậy hơn về **tên event**, nhưng những giá trị chen vào log vẫn cần được đánh giá theo nguồn gốc của chúng.

## 4. Những dạng log injection cần phân biệt

### 4.1. CR/LF và separator: phá ranh giới record

CR (\r) và LF (\n) là hai ký tự thường gặp nhất. Trên hệ thống Unix, LF thường phân cách dòng; trên nhiều môi trường Windows là CRLF. Cả CR đơn lẻ, LF đơn lẻ hoặc Unicode line separator U+2028/U+2029 đều cần xem xét theo parser/renderer thực tế.

Một chuỗi độc hại có thể là:

~~~text
attacker\n2026-11-10T02:00:00Z INFO AUTHORIZED user=admin
~~~

Nếu encoder text cho phép xuống dòng vật lý, consumer dựa vào “mỗi dòng = một event” có thể tạo một bản ghi mới. Một bộ phân tích khác dùng timestamp prefix có thể còn nhầm lẫn nghiêm trọng hơn.

**Biện pháp:** dùng structured event với encoder JSON phù hợp hoặc encode các separator trong giá trị không đáng tin khi tạo text log theo dòng; không để input quyết định prefix, timestamp, level hoặc tên event.

### 4.2. Ký tự điều khiển terminal và ANSI

Ký tự ESC (U+001B) thường mở đầu một ANSI control sequence. Nếu log được hiển thị qua terminal có diễn giải escape, nội dung có thể đổi màu, di chuyển con trỏ, xóa vùng hiển thị hoặc gây sai lệch khi người vận hành xem. NUL, backspace, tab và các control khác cũng có thể ảnh hưởng parser hoặc cách hiển thị.

Một chuỗi ví dụ ở dạng đã biểu diễn an toàn:

~~~text
alice\u001B[31m
~~~

Tùy môi trường, \u001B trong ví dụ biểu diễn ký tự ESC; khi được escape thật sự, nó phải hiện thành ký tự backslash và chữ u, không còn tác dụng điều khiển terminal.

**Biện pháp:** bảo đảm những trường untrusted không chứa control sequence tác động đến terminal; encode hoặc loại bỏ theo policy cho text console, và kiểm thử công cụ xem log. Với JSON, JSON escaping xử lý ký tự điều khiển trong chuỗi; nhưng một viewer vẫn phải render dữ liệu như text, không như mã HTML hoặc nội dung điều khiển tin cậy.

### 4.3. Ký tự Unicode định hướng/ẩn

Một số ký tự Unicode có thể làm thứ tự hiển thị trông khác thứ tự code point: các ký tự bidi override/isolate như U+202E hoặc U+2066–U+2069, zero-width space U+200B, định dạng U+200E/U+200F. Kẻ tấn công có thể lợi dụng chúng để khiến tên người dùng, nhãn hoặc thông điệp khó đọc/so sánh.

**Biện pháp:** chuẩn hóa quy tắc hiển thị trong dashboard và escape các ký tự điều khiển/định hướng có nguy cơ tại output, theo đúng chính sách của trường. Không áp dụng một bộ lọc “chỉ ASCII” cho mọi tên người Việt hoặc văn bản đa ngôn ngữ; Unicode hợp lệ cần được hỗ trợ.

### 4.4. JSON, CSV, key-value và delimiter

Một collector có thể kỳ vọng:

~~~json
{"level":"WARN","event":"LOGIN_FAILED","username":"alice"}
~~~

Nếu lập trình viên tự ghép JSON bằng chuỗi:

~~~java
// Sai: username chưa được JSON-escape.
String line = "{\"level\":\"WARN\",\"username\":\"" + username + "\"}";
~~~

thì dấu quote, backslash, control character hoặc newline trong username có thể khiến JSON không hợp lệ hoặc khiến một số parser diễn giải sai. Với CSV, dấu phẩy, quote và newline có quy tắc escaping riêng; với định dạng key=value, dấu cách và dấu bằng có thể tạo thêm “field” giả nếu bộ phân tích quá đơn giản.

**Biện pháp:** dùng serializer/encoder đã được kiểm thử và cung cấp dữ liệu qua field riêng; đừng tạo JSON, CSV hay syslog message bằng phép nối chuỗi tự phát. Một JSON encoder đúng phải serialize String sao cho dấu quote, backslash và các ký tự điều khiển không thoát ra khỏi **giá trị chuỗi**.

### 4.5. Giả metadata và thay đổi cấu hình đích

Kẻ tấn công không nhất thiết phải phá dòng. Nếu ứng dụng cho phép client gửi “log level”, “role”, “user_id”, “trace_id”, “severity” hoặc tên logger rồi ghi chúng như **metadata do server xác nhận**, downstream có thể bị đánh lừa dù JSON hợp lệ.

Ví dụ, field actor trong audit event cần lấy từ principal đã được xác thực và policy của server, không phải client-supplied username. Event type, level, logger name, index/route và source service nên lấy từ code hoặc cấu hình tin cậy; dữ liệu chưa xác thực chỉ là **field dữ liệu** được đánh dấu nguồn gốc phù hợp.

**Quan trọng:** log injection có thể gây hại cả khi toàn bộ event vẫn nằm trên một dòng: giả trường nguồn tin cậy cũng là một cách làm sai dữ liệu quan sát.

## 5. Những điều KHÔNG tự động ngăn được log injection

### 5.1. Placeholder logging không phải escape đầu ra

Cú pháp SLF4J:

~~~java
// Snippet; SLF4J/Logback hoặc SLF4J provider khác.
log.warn("LOGIN_FAILED username={}", username);
~~~

giúp giữ message template cố định và có thể giảm chi phí định dạng khi level tắt. Tuy nhiên, **nếu appender dùng text pattern và chèn username chứa CR/LF nguyên văn, vẫn có nguy cơ log forging**.

So sánh hai vấn đề:

- Placeholder giúp tránh việc input bị gộp vào **message template** trước lúc logger xử lý.
- Encoding/neutralization ở formatter/encoder giúp bảo vệ **định dạng bản ghi được xuất ra**.

Cần cả hai ở đúng nơi, chứ không chọn một rồi bỏ qua cái còn lại.

### 5.2. “Đã validate username ở form” chưa chắc đủ

Log có nhiều nguồn: URL, header, bên thứ ba, exception message, giá trị import, dữ liệu cũ trong DB. Quy tắc validation của một form có thể không áp dụng cho mọi đường đi đến logger. Hơn nữa, ký tự có thể được percent-decode, HTML-decode hoặc Unicode-normalize ở những bước khác nhau.

Nên validate theo **ngữ nghĩa field** và encode theo **ngữ cảnh output**, với hợp đồng chung cho logging. Tránh double decode sau khi validation, vì điều đó có thể đưa ký tự nguy hiểm trở lại.

### 5.3. Log event object không đồng nghĩa JSON hợp lệ

Structured logging API có thể giữ dữ liệu ở dạng field, nhưng nếu cuối cùng đi qua text layout không escape hoặc custom appender tự ghép JSON, kết quả vẫn có thể bị injection. Phải xem **bytes thật ở sink**, không chỉ nhìn kiểu dữ liệu ở call site.

### 5.4. Logger thread-safe không giải quyết nội dung không đáng tin

Thread safety bảo vệ trạng thái nội bộ và các thao tác đồng thời; nó không bảo đảm string chứa CR/LF không trở thành nhiều dòng. Đừng nhầm log forging với race condition: đây là hai lớp lỗi khác nhau.

## 6. Nguyên tắc phòng thủ nhiều lớp

| Lớp | Biện pháp | Vì sao |
| --- | --- | --- |
| Tại đầu vào | Validate theo schema/allowlist, chiều dài, loại dữ liệu; từ chối input không hợp lệ khi hợp lý | Giảm dữ liệu nguy hiểm trước khi đi sâu vào ứng dụng |
| Khi xây event | Dùng tên event/level/key do server kiểm soát, các field có kiểu | Không cho client quyết định cấu trúc/độ nghiêm trọng |
| Khi xuất log text | Escape CR/LF, control, delimiter của format; giới hạn độ dài từng field | Một input không được phá ranh giới record |
| Khi xuất JSON | Dùng JSON encoder chuẩn, ghi mỗi event một JSON object/line | Giữ cấu trúc và ký tự escape hợp lệ |
| Trên collector | Parse đúng định dạng, theo dõi sự kiện lỗi, giới hạn kích thước, không tự tin tin chuỗi hiển thị | Giảm sai sót khi ingestion |
| Trên viewer | Escape HTML, không diễn giải nội dung log thành script/HTML; xử lý ANSI an toàn | Tránh injection ở tầng hiển thị |
| Trên lưu trữ | Phân quyền, chống sửa đổi, retention, theo dõi truy cập | Bảo vệ tính toàn vẹn và bảo mật của bằng chứng |
| Trong kiểm thử | Fuzz ký tự điều khiển, JSON delimiter, Unicode, kích thước lớn | Phát hiện lỗi format và bypass |

**Chọn “encode” thay vì “xóa hết” khi cần điều tra bảo mật.** Việc biến CR thành chuỗi nhìn thấy được \r và LF thành \n vừa giữ ý nghĩa dữ liệu ban đầu, vừa ngăn chúng điều khiển ranh giới dòng. Nếu hệ thống cần lưu raw input để phân tích chuyên sâu, hãy đặt nó trong kho riêng được bảo vệ và có chính sách dữ liệu phù hợp, không gắn nguyên vẹn vào log chung.

### Thứ tự xử lý

Một thứ tự hợp lý cho text single-line event:

~~~text
Input được decode và hiểu đúng kiểu
      ↓
Validation theo field và giới hạn kích thước
      ↓
Chọn metadata tin cậy từ server
      ↓
Neutralize/escape giá trị theo format log đầu ra
      ↓
Formatter/encoder tạo một record
      ↓
Appender → collector → backend
~~~

Với JSON encoder chuẩn, **không cần tự escape JSON hai lần**. Thay vì tạo chuỗi có backslash escape sẵn rồi serialize như giá trị JSON, hãy truyền giá trị String cho encoder; nếu cần chính sách riêng về các ký tự không được phép/độ dài/PII thì áp dụng policy đó trước khi serialize. Encoder chịu trách nhiệm escaping đúng cho JSON.

## 7. Ví dụ hoàn chỉnh Java 17: neutralize đầu vào trước khi ghi text log

Ví dụ dùng **java.util.logging (JUL)** có sẵn trong JDK, không cần thư viện ngoài. Ta chủ động tạo input chứa CR, LF, ESC và ký tự bidi override; sau đó ghi qua một formatter đơn giản ra System.out để xem giá trị đã được biểu diễn an toàn.

**Tệp: LogInjectionDemo.java**

~~~java
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class LogInjectionDemo {
    private static final int MAX_CODE_POINTS = 80;

    // Quy tắc của ví dụ cho một trường text dùng trong log một dòng.
    private static boolean needsEscaping(int codePoint) {
        return Character.isISOControl(codePoint)
                || codePoint == 0x200B
                || codePoint == 0x200E
                || codePoint == 0x200F
                || codePoint == 0x2028
                || codePoint == 0x2029
                || (codePoint >= 0x202A && codePoint <= 0x202E)
                || (codePoint >= 0x2066 && codePoint <= 0x2069);
    }

    private static String safeLogValue(String input) {
        if (input == null) {
            return "<null>";
        }

        StringBuilder out = new StringBuilder();
        int processed = 0;
        for (int offset = 0; offset < input.length();) {
            if (processed >= MAX_CODE_POINTS) {
                out.append("[truncated]");
                break;
            }

            int codePoint = input.codePointAt(offset);
            offset += Character.charCount(codePoint);
            processed++;

            switch (codePoint) {
                case '\r' -> out.append("\\r");
                case '\n' -> out.append("\\n");
                case '\t' -> out.append("\\t");
                default -> {
                    if (needsEscaping(codePoint)) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04X", codePoint));
                    } else {
                        out.appendCodePoint(codePoint);
                    }
                }
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("example.security.LogInjectionDemo");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        StreamHandler console = new StreamHandler(
                System.out, new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName() + " "
                                + formatMessage(record)
                                + System.lineSeparator();
                    }
                });
        console.setLevel(Level.ALL);
        log.addHandler(console);

        // Chỉ dùng để minh họa: input có CR/LF và ký tự điều khiển.
        String untrustedUsername =
                "alice\r\nINFO LOGIN_SUCCESS actor=admin"
                + (char) 27 + "[31m"
                + Character.toString(0x202E);

        try {
            log.log(Level.WARNING,
                    "LOGIN_FAILED user={0} reason=BAD_PASSWORD",
                    safeLogValue(untrustedUsername));
            log.info("LOGGER_READY");
        } finally {
            console.flush();
            log.removeHandler(console);
            // Không close handler ở đây để tránh đóng System.out.
        }
    }
}
~~~

**Biên dịch và chạy với JDK 17 trở lên:**

~~~bash
javac -encoding UTF-8 LogInjectionDemo.java
java LogInjectionDemo
~~~

**Stdout kỳ vọng, đúng hai dòng:**

~~~text
WARNING LOGIN_FAILED user=alice\r\nINFO LOGIN_SUCCESS actor=admin\u001B[31m\u202E reason=BAD_PASSWORD
INFO LOGGER_READY
~~~

Trong output, \r, \n, \u001B và \u202E đều là **các ký tự hiển thị theo dạng escape**, không phải các ký tự điều khiển thực. Chúng không tạo dòng LOGIN_SUCCESS mới; chỉ có hai LogRecord do chương trình phát ra.

### Tại sao đoạn code an toàn hơn ví dụ ban đầu?

1. Dữ liệu username vẫn có thể mang thông tin cần điều tra, nhưng CR/LF không thể tự chia một text event thành hai dòng.
2. ESC và các ký tự định hướng đã chọn được biểu diễn theo mã code point, hạn chế hiệu ứng khi xem bằng terminal.
3. MAX_CODE_POINTS chặn một trường quá dài trên đường ghi log; marker [truncated] giúp người điều tra biết dữ liệu đã được giới hạn.
4. Logger, level và message template là hằng số do server xác định. Input không thể chọn level INFO hoặc tự tạo event LOGIN_SUCCESS.
5. setUseParentHandlers(false) tránh việc log bị gửi trùng lên root handler của JUL, không liên quan trực tiếp đến injection nhưng giúp kết quả minh họa xác định.
6. Formatter.formatMessage(record) dùng template JUL với {0}; tham số đã được neutralize thành giá trị hiển thị an toàn trước khi formatter ghi ra sink.
7. StreamHandler được flush trong finally trước khi xem stdout. Demo không dùng thread hay async logger nên không có yếu tố xen kẽ làm nhiễu kết quả.

### Giới hạn có chủ đích của ví dụ

- safeLogValue là **bộ escape cho text log theo dòng**, không phải JSON encoder, HTML encoder, sanitizer URL hay bộ lọc bảo mật áp dụng được cho mọi định dạng.
- Giới hạn 80 **code point**, không phải 80 byte UTF-8 hay 80 ký tự UTF-16. Sau escape, số byte đầu ra có thể dài hơn. Sink vẫn cần giới hạn kích thước event tổng thể.
- Hàm minh họa không phát hiện mọi ký tự Unicode có thể gây nhầm lẫn thị giác; nên dùng chính sách/renderer nhất quán, kiểm thử với ngôn ngữ và dữ liệu thực tế.
- Không nên copy hàm này vào hàng trăm call site. Trong ứng dụng thật, đặt logic neutralize/encode tại một logging wrapper hoặc formatter/encoder chuẩn để tránh chỗ làm, chỗ quên.
- Với structured JSON, ưu tiên serializer chuẩn cho từng field để tránh double escape; chỉ áp dụng kiểm tra chính sách dữ liệu và giới hạn riêng của field trước đó.
- Không dùng cơ chế escape để thay thế xác thực: việc tên “admin” được in an toàn không có nghĩa người gửi input đã được xác thực là admin.

## 8. SLF4J và Logback: placeholder, MDC và encoder

### 8.1. Template cố định, field không đáng tin

Trong ứng dụng dùng SLF4J + Logback:

~~~java
// Snippet; cần slf4j-api và provider Logback phù hợp.
log.warn("Login rejected for username={}", username);
~~~

Việc sử dụng placeholder là **nên làm**, nhưng chưa đủ nếu Logback ConsoleAppender dùng một PatternLayout ghi %msg nguyên văn. Input chứa CR/LF vẫn có thể xuất hiện dưới dạng nhiều dòng vật lý.

Nếu ứng dụng cần format text line, hãy encode giá trị không đáng tin theo chính sách tại điểm chuẩn trước khi gửi vào log hoặc sử dụng encoder/layout có cơ chế neutralization phù hợp, được kiểm thử. Nếu ứng dụng đã áp dụng policy field-level trong wrapper, tránh gọi trực tiếp log.warn với raw header/username ở những đường đi khác.

### 8.2. Structured logging

Ví dụ snippet SLF4J 2.x:

~~~java
// Snippet SLF4J 2.x; output phụ thuộc provider và encoder.
log.atWarn()
        .addKeyValue("event_type", "LOGIN_FAILED")
        .addKeyValue("username", username)
        .addKeyValue("reason_code", "BAD_PASSWORD")
        .log("Login rejected");
~~~

Ở đây event_type và reason_code do server xác định, còn username là dữ liệu. **Một API lưu key-value không tự bảo đảm an toàn** nếu provider sau đó xuất ra text không escape hoặc key-value không được đưa vào cấu hình formatter. Cần xác nhận Logback encoder thực tế ghi event dưới dạng JSON hợp lệ và escape đúng các trường.

Nếu hệ thống sử dụng API structured logging của phiên bản framework khác, hãy dùng API tương ứng thay vì giả định cú pháp SLF4J 2 có sẵn ở SLF4J 1.7.

### 8.3. Không đặt dữ liệu tùy ý vào MDC như metadata tin cậy

MDC/ThreadLocal thường mang request_id, trace_id, tenant và context khác. Nhưng MDC chỉ là cơ chế lưu context; nếu client cung cấp request_id chứa CR/LF mà ứng dụng đưa thẳng vào %X{request_id}, rủi ro injection vẫn tồn tại.

Tốt hơn:

- Sinh hoặc validate ID theo một quy tắc rõ ràng (ví dụ ký tự hex/UUID) trước khi gắn vào MDC.
- Chọn các khóa context có tập cố định; không nhận arbitrary MDC key từ client.
- Đặt/clear hoặc restore MDC trong try/finally để tránh request sau nhận nhầm context từ thread pool.
- Không lưu access token, cookie hay toàn bộ header trong MDC.
- Kiểm tra cách layout/encoder của backend xuất MDC vào text/JSON.

**Chú ý:** việc truyền trace context qua HTTP không tự biến một ID thành chứng cứ về danh tính. Phân quyền và actor phải lấy từ auth context đã được xác thực.

## 9. Log4j 2: chọn layout và xử lý lookup/format riêng biệt

Log4j 2 cũng có API parameterized logging và các layout cho text/JSON. Trong hệ thống có untrusted input, nên:

1. Giữ message template, logger name, level và routing policy dưới quyền kiểm soát của code/cấu hình.
2. Dùng layout/encoder structured phù hợp, ví dụ JSON Template Layout khi dependency/version hỗ trợ.
3. Không tạo JSON hoặc một pattern động bằng phép nối chuỗi từ client.
4. Kiểm tra serialized output khi có CR/LF, quote, backslash, ESC và các ký tự Unicode đặc biệt.
5. Giới hạn kích thước giá trị cùng dung lượng toàn event; một giới hạn số ký tự string không nhất thiết là giới hạn tổng số byte được tạo ra.

**Phân biệt log injection và Log4Shell:** hai chủ đề có thể cùng xuất hiện trong logging nhưng không đồng nhất. Log injection/CWE-117 chủ yếu nói về **cách dữ liệu untrusted được biểu diễn trong log** làm giả/corrupt bản ghi. Các lỗ hổng lookup/JNDI lịch sử liên quan hành vi xử lý đặc biệt của một số phiên bản thư viện. Việc “đã nâng Log4j 2” không phải lý do bỏ qua escaping/structured logging; và việc escape CR/LF không thay thế quản lý phiên bản/phụ thuộc bảo mật.

Không tự tạo lỗ hổng bằng việc đưa input người dùng vào đường dẫn file appender, tên logger động, tên route hoặc template expression mà chưa có quy định allowlist. Nếu cần nhiều loại event, dùng enum/tập tên cố định và field được kiểm soát.

## 10. JUL: Handler, Formatter và bất biến của một sự kiện

Trong java.util.logging, Logger nhận LogRecord; Formatter.format(LogRecord) quyết định chuỗi đầu ra, Handler xuất tới sink. JUL có cơ chế truyền handler qua parent logger và lọc level, nhưng **không có một sanitizer mặc định bảo đảm mọi untrusted String trở thành một text line an toàn**.

Các điểm cần kiểm soát:

- Input từ user phải được validate hoặc encode trước khi Formatter ghi vào định dạng cuối.
- Dùng một Formatter có hợp đồng rõ (ví dụ one-line text với giá trị được neutralize, hoặc JSON formatter dùng JSON serializer).
- Không ghép log event bằng nhiều lần write rời rạc vào stream dùng chung; vừa gây khó đọc vừa làm tăng nguy cơ xen dòng ở ứng dụng đa luồng.
- Không dùng untrusted value làm java.util.logging.Level, logger hierarchy hay tên file handler một cách tùy ý.
- ConsoleHandler mặc định ghi System.err; StreamHandler(System.out, formatter) trong ví dụ mục 7 chủ động ghi System.out để có stdout dễ kiểm tra.
- Đừng nhầm formatMessage() thay placeholder JUL với cơ chế escape CR/LF. Đây là hai trách nhiệm khác nhau.

Với framework có sẵn, thông thường nên dùng encoder đã được bảo trì thay vì tự xây lại một Formatter bảo mật phức tạp. Ví dụ Java 17 giúp người học hiểu cơ chế, không phải khuyến nghị tự viết một logging stack thay thế.

## 11. JSON Lines và lựa chọn encoder đúng

Nếu collector kỳ vọng **mỗi dòng là một JSON object**, dữ liệu nằm trong String phải được JSON-escape. Ví dụ giá trị thực của username gồm dấu quote và newline:

~~~text
alice"\nadmin
~~~

Một JSON line đúng sẽ có dạng:

~~~json
{"event_type":"LOGIN_FAILED","username":"alice\"\nadmin","level":"WARN"}
~~~

Trong dòng JSON trên, dấu quote bên trong username được biểu diễn bằng \", newline bằng \n; toàn bộ event vẫn là **một dòng văn bản JSON hợp lệ**. Chỉ khi parser JSON giải mã trường username thành String thì newline mới là ký tự dữ liệu, không phải dòng log mới.

### Ví dụ với thư viện JSON serializer

Đoạn sau chỉ là snippet trong dự án có Jackson; cần dependency tương ứng, **không** chạy độc lập với JDK 17:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();
Map<String, Object> event = new LinkedHashMap<>();
event.put("event_type", "LOGIN_FAILED");  // trusted constant
event.put("username", username);         // untrusted string as DATA
event.put("level", "WARN");              // trusted constant

String jsonLine = mapper.writeValueAsString(event);
logWriter.write(jsonLine);
logWriter.write("\n");
~~~

Jackson xử lý escaping trong field String, nhưng ví dụ vẫn cần quản lý vòng đời Writer, encoding, concurrency, lỗi I/O và appender. Không lấy riêng đoạn write này làm custom production logger khi backend đã có JSON encoder. Nếu tự dùng Map, phải bảo đảm key từ client không được trộn vào các key đặc quyền như actor, severity, timestamp hay event_type.

**Khuyến nghị:** dùng structured JSON encoder của logging backend và để framework quyết định một event được ghi thành bao nhiêu byte/dòng. Đọc lại output thực của encoder trong test; một cấu hình JSON không hợp lệ hoặc parser lỗi vẫn có thể làm collector mất record.

### Cẩn trọng với double escape

Nếu tự đổi CR thành chuỗi hai ký tự \r rồi đưa vào JSON serializer, trong JSON sẽ xuất hiện biểu diễn có thêm dấu backslash. Điều đó không sai cú pháp nhưng consumer nhận giá trị đã neutralize, không phải String gốc. Hãy thống nhất hợp đồng: raw value được JSON encoder escape đúng; text-line value được text encoder neutralize; data policy như length/redaction áp dụng nhất quán trước serialization.

### Một event có stack trace nhiều dòng

Exception thật có thể có stack trace nhiều dòng. Đây không phải lúc nào cũng là injection. Đối với logging text truyền theo dòng, cần cấu hình multiline aggregation hoặc JSON encoder đặt stack trace vào field đã escape phù hợp, thay vì cấm toàn bộ thông tin exception. Quan trọng là phân biệt **ranh giới event do logger tạo** với **ký tự newline do dữ liệu untrusted tạo ra**.

## 12. Giới hạn kích thước: chống log flooding và cạn tài nguyên

Ngoài giả mạo sự kiện, dữ liệu log quá dài có thể gây:

- Tăng CPU khi encode, escape, format hoặc parse.
- Gây áp lực GC và bộ nhớ, làm chậm hot path.
- Làm đầy stdout buffer, queue, disk hoặc storage backend.
- Gây log ingestion timeout, truncate giữa chừng hoặc mất một phần record.
- Làm tăng chi phí và cản trở truy tìm các sự kiện có giá trị.

Thiết kế giới hạn theo **field** và theo **event tổng**:

| Thành phần | Gợi ý |
| --- | --- |
| username / device name | Theo giới hạn dữ liệu thực tế; không cần ghi toàn bộ giá trị rất dài |
| URL / User-Agent | Giới hạn chiều dài; loại query secret hoặc dùng path template |
| Exception message từ remote | Ghi mã lỗi/loại exception và summary an toàn |
| JSON log event | Giới hạn số field, kích thước String và tổng bytes sau encoding |
| Log rate | Rate limiting/sampling có kiểm soát, không bỏ mù security events |
| Pipeline | Cấu hình buffer, retention, alert dropped/invalid events |

Giới hạn ở cấp độ code point khác giới hạn **byte UTF-8**, và escape có thể làm kích thước đầu ra tăng. Nếu giới hạn downstream đo theo bytes, cần đo trên nội dung đã encode.

Nếu cắt bớt dữ liệu, nên gắn thông tin truncated=true hoặc suffix đã được chuẩn hóa. Đừng cắt giữa UTF-8 sequence, JSON escape hoặc record delimiter khiến event không parse được.

Security log quan trọng có thể cần chính sách giữ riêng; không xóa mọi authentication failure chỉ vì số lượng lớn. Có thể kết hợp metrics, alert và giới hạn dữ liệu chi tiết một cách có chủ đích.

## 13. Bảo đảm tính toàn vẹn của metadata

Một bản ghi an toàn nên có metadata do hệ thống xác định:

~~~json
{
  "event_type": "AUTHENTICATION_FAILED",
  "severity": "WARN",
  "actor_id": null,
  "attempted_username": "alice",
  "request_id": "req-b39c",
  "source": "auth-service",
  "outcome": "REJECTED"
}
~~~

Bản JSON trên chỉ minh họa thiết kế schema. Trong trường hợp chưa xác thực thành công, **actor_id không được đặt thành một tài khoản tin cậy chỉ vì client cung cấp username**. Dùng attempted_username cho giá trị mà client khai báo. Chỉ khi principal được xác thực mới dùng actor_id theo danh tính server đã kiểm tra.

Những field như event_type, severity, actor_id, source, outcome, access-control decision phải xuất phát từ logic/cấu hình tin cậy. Nếu client gửi giá trị có tên trùng key “severity” hoặc “actor_id”, hãy đặt nó ở một field dữ liệu khác theo allowlist; không merge mù Map untrusted vào root event.

### Trace ID và correlation ID

Nếu hệ thống nhận W3C traceparent từ request, trace ID có thể là dữ liệu đến từ upstream và cần validation theo tiêu chuẩn. Nó giúp liên kết log theo một trace, **không có ý nghĩa chứng minh người dùng đã xác thực**. Với các quyết định bảo mật, actor và privilege phải lấy từ auth context đã được kiểm chứng.

MDC đặt sai hoặc không clear trong thread pool có thể dẫn đến một dạng sai lệch log khác: request B có request_id của A. Đây là vấn đề context lifecycle, cũng cần kiểm tra cùng với injection để tránh dẫn người điều tra tới sai request.

## 14. Rendering và injection sau khi log đã được lưu

Một event JSON có thể được ghi đúng nhưng trở thành nguy hiểm khi viewer sử dụng dữ liệu sai ngữ cảnh:

- Nếu giao diện HTML đưa message vào innerHTML mà không escape, nội dung log có thể dẫn tới XSS trong viewer. Dùng textContent hoặc framework escaping đúng.
- Nếu mở log bằng terminal diễn giải ANSI, control sequences có thể làm rối màn hình; hiển thị escaped/plain-text khi xem dữ liệu không tin cậy.
- Nếu export sang CSV, các ô bắt đầu bằng công thức có thể gây **CSV/formula injection** trong phần mềm bảng tính; cần áp dụng biện pháp phù hợp tại bước export, không chỉ JSON encode ở bước ghi.
- Nếu chuyển log message vào shell command, SQL query, template engine hoặc system prompt rồi thực thi, đó là một **biên tin cậy mới**. Không bao giờ coi nội dung log là lệnh đáng tin.
- Nếu collector chọn “một dòng có timestamp = một record”, phải kiểm tra trường hợp message nhiều dòng và các quy tắc multiline aggregation.

Đừng cho rằng một lần encode ở Java đủ cho mọi consumer. Mỗi điểm chuyển dữ liệu sang ngữ cảnh mới (HTML, CSV, terminal, shell) phải bảo vệ theo ngữ cảnh đó.

## 15. Kiểm thử log injection bằng dữ liệu có kiểm soát

Không chỉ test hàm safeLogValue trả về chuỗi đẹp. Cần xem **output thật từ formatter/appender và collector**.

### 15.1. Test matrix

| Input/thao tác | Rủi ro chính | Kỳ vọng |
| --- | --- | --- |
| Username thông thường: alice | Baseline | Ghi đúng một event với giá trị nguyên nghĩa |
| CRLF: alice + CR + LF + fake INFO | Log forging | Không có một event/dòng INFO giả |
| Chỉ LF hoặc chỉ CR | Tách record tùy parser | Không tạo ranh giới sự kiện mới |
| Tab, NUL, ESC/ANSI | Terminal/parser control | Hiển thị escape hoặc xử lý an toàn |
| U+2028, U+2029, U+202E | Ngắt dòng/đảo chiều hiển thị | Đầu ra an toàn, không thay ngữ nghĩa |
| Quote và backslash trong JSON | JSON syntax injection | JSON parse thành một object đúng, field giữ dữ liệu |
| Dấu phẩy/quote/newline trong CSV export | Sai cấu trúc CSV | Escape đúng theo CSV exporter |
| Chuỗi rất dài | Log flood/resource exhaustion | Truncate theo chính sách; event vẫn hợp lệ |
| Username là Unicode tiếng Việt | Over-sanitization | Không làm hỏng dữ liệu hợp lệ |
| Input chứa token/PII | Lộ dữ liệu | Redact/omit trước khi lưu |
| Header giả actor_id/admin | Metadata spoofing | actor_id lấy từ auth context, không từ header |
| Exception chứa input | Kênh injection gián tiếp | Message/stack trace đi qua encoder an toàn |
| Nhiều request đồng thời | Rối context hoặc trộn record | Mỗi event có request_id đúng, không ghép nhầm |
| Backend/collector bị ngắt | Mất/đánh đổi log | Có metric, retry/buffer policy, không báo thành công giả |

### 15.2. Những assert nên có

1. Với mỗi lời gọi logger tạo event, collector nhận đúng cấu trúc đã thiết kế (không sinh event giả từ input).
2. Với text một dòng, số dòng vật lý tăng đúng theo số event; các giá trị có newline phải hiện escape, không tạo dòng mới.
3. Với JSON Lines, từng dòng parse được thành một JSON object và các field có type đúng.
4. Event type, level, actor và source không bị thay bởi input do client gửi.
5. Trường hợp overlong input vẫn có marker/trạng thái truncated và không gây lỗi encoder hoặc mất toàn bộ log.
6. Không có secret hoặc PII không được phép trong cả log chính, error log, debug log và output khi appender lỗi.
7. Các log security-critical vẫn được ghi theo chính sách dù có invalid input; có thể bỏ/neutralize **field không hợp lệ** nhưng đừng vô cớ bỏ cả event bảo mật.

### 15.3. Fuzzing và integration test

Dùng tập ký tự điều khiển, Unicode và chuỗi ngẫu nhiên trong unit test cho sanitizer/encoder. Sau đó kiểm tra integration với đúng logger backend, layout, container collector và dashboard sẽ triển khai. Khi thay phiên bản Logback/Log4j 2 hoặc cấu hình layout, chạy lại test; bảo đảm chỉ dựa vào API mock không đủ để chứng minh output cuối an toàn.

Không dùng log production làm nơi thử payload số lượng lớn. Các phép thử log storm, kích thước tối đa và collector chậm nên thực hiện ở môi trường được phép, có giới hạn tài nguyên.

## 16. Những sai lầm phổ biến

**Sai 1 – Chỉ thay CR/LF bằng một dấu cách rồi dừng.**  
Cách này có thể chặn một biến thể đơn giản của log forging text, nhưng còn các ký tự điều khiển, định dạng delimiter, Unicode và viewer. Với định dạng JSON, cần JSON escaping chuẩn chứ không chỉ replace newline.

**Sai 2 – Cho rằng SLF4J placeholder tự chống injection.**  
Placeholder không ép một PatternLayout text thoát CR/LF. Cần formatter/encoder và chính sách field phù hợp.

**Sai 3 – Ghi raw request để có “bằng chứng đầy đủ”.**  
Raw URL/header/body có thể chứa secret, PII, payload dài và ký tự gây rối. Chọn field allowlist; nếu thực sự phải lưu raw evidence, dùng kho riêng có quyền/retention phù hợp.

**Sai 4 – Tự tạo JSON bằng String concatenation.**  
JSON trở nên không hợp lệ hoặc có thể bị thao túng khi quote/newline không được escape đúng. Dùng serializer hoặc structured encoder đã kiểm chứng.

**Sai 5 – Dùng dữ liệu client làm event_type, severity, actor.**  
Sự kiện có cấu trúc vẫn có thể bị giả metadata. Event classification và principal phải do server xác định.

**Sai 6 – Sanitize ở controller nhưng quên exception/MDC.**  
Dữ liệu có thể đi qua nhiều đường gián tiếp trước khi vào logger. Đặt chính sách ở một lớp chung gần event/encoder, thêm validation theo field.

**Sai 7 – Xóa toàn bộ log khi input không hợp lệ.**  
Chính hoạt động injection có thể là một tín hiệu security event quan trọng. Ghi một security event an toàn, loại/escape field độc hại và không để input điều khiển mức log hay kết quả auth.

**Sai 8 – Log viewer xử lý dữ liệu như HTML đáng tin.**  
Ngay cả JSON log đã parse thành công vẫn chứa nội dung người dùng; renderer phải text-escape theo ngữ cảnh.

**Sai 9 – Chỉ kiểm thử sanitizer, không xem collector.**  
Collector có thể tách multiline, reformat hoặc export lại. Cần test từ appender đến dashboard và bất kỳ workflow phân tích tự động nào.

**Sai 10 – Trộn bảo mật định dạng với bảo mật thư viện.**  
Sửa log forging không thay thế cập nhật dependency, quản lý quyền ghi log, kiểm soát retention và lỗ hổng parser/lookup độc lập.

## 17. Áp dụng vào dự án Java thật

Một thiết kế có thể triển khai theo các bước sau:

1. **Lập danh sách trường log:** event_type, severity, service, trace_id, actor_id, attempted_username, result, error_code. Định nghĩa rõ trường nào do server sinh, trường nào do client cung cấp.
2. **Thiết kế logging API dùng chung:** module phát event với tên và schema ổn định; các lớp nghiệp vụ không tự ghép text tùy ý từ HTTP header.
3. **Chọn encoding:** với service container, structured JSON console thường đơn giản cho collector; nếu dùng text line, yêu cầu neutralize trên mọi untrusted field.
4. **Giới hạn input:** đo chiều dài từng trường và tổng bytes sau encoding; dùng allowlist field, không ghi payload bí mật.
5. **Đặt policy tại output boundary:** encoder kiểm soát record delimiter và encoding, không để input ghi trực tiếp vào file sink hay route.
6. **Kiểm tra context:** MDC/ThreadContext được gắn trong scope đúng và không cho client ghi đè principal/level.
7. **Cấu hình collector và viewer:** parse JSON theo schema, quarantine event không hợp lệ, hiển thị như text, kiểm soát quyền và retention.
8. **Kiểm thử:** CRLF, ANSI, Unicode, JSON/CSV delimiter, dài quá mức, concurrency, exception messages, lỗi downstream và security-event continuity.
9. **Theo dõi sau triển khai:** số event lỗi parse, sự kiện bị truncate/drop, bất thường log rate, thay đổi policy, truy cập audit và thời gian trễ từ event tới backend.

### Kiến trúc phân chia trách nhiệm

~~~text
Controller / Consumer
   ├── Validate input theo nghiệp vụ
   └── Truyền dữ liệu, không định dạng log tùy ý
             │
             ▼
      SecurityEvent API
   ├── Tên event và mức log là hằng số được duyệt
   ├── Metadata lấy từ authentication/context tin cậy
   ├── Policy độ dài, dữ liệu nhạy cảm, schema
   └── Field untrusted được đánh dấu nguồn
             │
             ▼
       Logging backend
   ├── JSON encoder chuẩn hoặc text encoder có escaping
   └── Appender/Handler được kiểm thử
             │
             ▼
        Collector / SIEM
   ├── Parse, kiểm soát schema và event size
   ├── Quarantine/metric cho dữ liệu lỗi
   └── Access control và safe rendering
~~~

Không có nghĩa phải tự tạo nhiều framework trong code. Có thể tận dụng logging backend và thư viện encoder sẵn có; quan trọng là **hợp đồng dữ liệu và kiểm thử biên tin cậy**.

## 18. Bài tập thực hành

### Bài 1 – Tái hiện log forging trong test

Từ LogInjectionDemo.java, dùng input bình thường và input chứa CR/LF. So sánh một Formatter ghi raw username với safeLogValue, trong **môi trường test không kết nối hệ thống giám sát thực**. Kiểm tra số dòng vật lý và giải thích dòng LOGIN_SUCCESS giả có thể đánh lừa consumer nào.

### Bài 2 – Mở rộng chính sách Unicode

Bổ sung ca kiểm thử có U+200B, U+202E, U+2028, U+2029 và tiếng Việt có dấu. Đảm bảo ký tự điều khiển được escape mà chữ tiếng Việt hợp lệ vẫn được giữ nguyên. Phân biệt độ dài theo code point và byte UTF-8.

### Bài 3 – JSON serializer

Trong dự án có Jackson, tạo event LOGIN_FAILED với username chứa dấu quote, backslash và newline. Serialize bằng ObjectMapper, parse lại bằng ObjectMapper rồi assert giá trị username được khôi phục đúng; **event_type** không thay đổi và output vẫn là một JSON line.

### Bài 4 – Bảo vệ metadata

Giả sử client gửi header actor_id=admin và event_type=LOGIN_SUCCESS. Thiết kế SecurityEvent API để authentication status, actor_id và event_type được suy ra từ phía server; lưu header không đáng tin chỉ ở field riêng nếu cần điều tra và theo chính sách bảo mật.

### Bài 5 – End-to-end với collector

Dùng cấu hình logging thật của dự án (JUL/Logback/Log4j 2) và collector trong môi trường test. Gửi các trường hợp CR/LF, ANSI, payload dài và exception chứa untrusted input. Xác minh số event, schema, retention và cách hiển thị dashboard; ghi nhận sự kiện invalid/truncated mà không đánh rơi toàn bộ tín hiệu bảo mật.

## 19. Ghi nhớ

**Log injection không phải chỉ là “một chuỗi có newline”.** Nó là vấn đề đưa dữ liệu ngoài biên tin cậy vào một định dạng log hoặc trường metadata theo cách khiến người đọc, parser hay pipeline hiểu sai sự kiện. CWE-117 bao quát lỗi xử lý không đúng các ký tự đặc biệt trong log; log forging là hậu quả phổ biến.

Với Java, bảo vệ theo nguyên tắc: **tên event và metadata đáng tin do server quyết định; giá trị không đáng tin được validate, giới hạn và encode đúng định dạng output; structured JSON dùng serializer/encoder chuẩn; log viewer/collector tiếp tục xử lý dữ liệu như untrusted input**. Placeholder của SLF4J hữu ích, nhưng không thay thế escaping. Luôn kiểm thử bytes và số record cuối cùng, đặc biệt khi cấu hình logging backend, collector hoặc viewer thay đổi.

### Tài liệu tham khảo

- MITRE CWE-117 – Improper Output Neutralization for Logs: https://cwe.mitre.org/data/definitions/117.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Log Injection: https://owasp.org/www-community/attacks/Log_Injection
- SEI CERT IDS03-J – Do not log unsanitized user input: https://wiki.sei.cmu.edu/confluence/display/java/IDS03-J.+Do+not+log+unsanitized+user+input
- Oracle Java 17 – java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – java.util.logging.Formatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java 17 – java.util.logging.StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J User Manual: https://www.slf4j.org/manual.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j 2 – Layouts: https://logging.apache.org/log4j/2.x/manual/layouts.html
