# Escape dữ liệu đầu vào khi ghi log trong Java

## 1. Mục tiêu bài học

**Escape dữ liệu đầu vào trong logging** là chuyển đổi những ký tự có ý nghĩa đặc biệt đối với **định dạng log đích** thành biểu diễn an toàn, để giá trị không đáng tin cậy không thể tự tạo bản ghi giả, phá vỡ cấu trúc, làm nhiễu hệ thống phân tích hoặc đánh lừa người đọc log.

Ví dụ, nếu username do client gửi chứa ký tự xuống dòng (CR/LF), câu lệnh ghi text log có thể vô tình tạo thêm một dòng trông như thông báo ERROR của hệ thống. Khi đó kẻ tấn công không nhất thiết cần quyền ghi file: họ chỉ cần điều khiển **một giá trị được ứng dụng đưa vào log**.

Sau bài này, bạn có thể:

- Nhận diện **log injection / log forging** và các nguồn dữ liệu không đáng tin cậy.
- Phân biệt **validation**, **sanitization**, **output escaping/encoding**, **redaction** và **structured logging**.
- Hiểu vì sao dùng placeholder trong SLF4J/Log4j2 là tốt nhưng **không đủ** để ngăn CRLF injection.
- Viết ví dụ **Java 17 độc lập** dùng JUL, minh họa dòng log giả và cách biến dữ liệu thành một dòng an toàn.
- Chọn chiến lược escape phù hợp với text log, CSV/TSV, JSON và giao diện xem log.
- Kiểm thử Unicode control characters, chuỗi dài, dữ liệu cá nhân, MDC/trace context và các đường xuất log nhiều tầng.

## 2. Vấn đề gốc: dữ liệu bên ngoài trở thành cú pháp của log

Xét dòng ghi log dự định:

~~~text
WARNING Authentication rejected for user=alice
~~~

Ứng dụng cho phép client cung cấp username. Nếu client gửi chuỗi chứa hai ký tự điều khiển **CR** (carriage return, U+000D) và **LF** (line feed, U+000A), đồng thời kèm nội dung trông giống một thông báo hệ thống, log thô có thể biến thành:

~~~text
WARNING Authentication rejected for user=alice
ERROR authentication granted user="root"
~~~

Một sự kiện bị từ chối đăng nhập nay được hiển thị như **hai dòng**. Dòng thứ hai không phải do ứng dụng thực hiện hành vi cấp quyền; nó chỉ là nội dung attacker điều khiển. Tuy vậy người vận hành hoặc máy phân tích dựa trên từng dòng có thể nhầm đó là một event độc lập.

**Tên vấn đề:** **log forging / log injection**, thường được phân loại theo **CWE-117: Improper Output Neutralization for Logs**. Cách tấn công này có thể ảnh hưởng tính toàn vẹn của dữ liệu quan sát, làm nhiễu điều tra, che dấu dấu vết hoặc gây lỗi cho parser.

### 2.1. Bốn thành phần của một log event

Một event có thể gồm:

~~~text
timestamp | severity | logger | event_type | user_input | request_id
~~~

Trong đó:

- **timestamp, severity, logger, event_type** nên đến từ hệ thống logging hoặc cấu trúc event có kiểm soát.
- **user_input** thường là dữ liệu từ bên ngoài: username, user-agent, header, URL, form, message body.
- **request_id / trace_id** đôi khi cũng đến từ header không đáng tin cậy; không phải cứ gọi là “metadata” thì đã an toàn.

Nếu toàn bộ chuỗi được nối lại thành text mà không có quy tắc encode, các giá trị bên ngoài có thể **thoát khỏi ranh giới một trường**, chèn dấu phân cách hoặc tạo dòng mới.

### 2.2. Escape không đồng nghĩa cấm mọi dấu xuống dòng

Một stack trace thật sự có nhiều dòng là điều bình thường. Log message do ứng dụng tự định nghĩa cũng có thể cần giữ cấu trúc nhiều dòng trong một số trường hợp. Mục tiêu của escape là **bảo vệ ranh giới record và field**; không nhất thiết xóa mọi ký tự điều khiển khỏi tất cả dữ liệu gốc.

Ví dụ, một JSON event có thể giữ nội dung chứa newline dưới dạng một **JSON string được encode hợp lệ**, còn một log text định nghĩa mỗi dòng là một event nên phải chuyển newline trong **dữ liệu đầu vào** thành ký tự biểu diễn (như dấu gạch chéo ngược + n).

## 3. Những đầu vào nào phải coi là không đáng tin?

Một nguyên tắc thực tế: **bất kỳ giá trị nào không được ứng dụng tự sinh theo hợp đồng chặt chẽ đều có thể mang ký tự điều khiển hoặc delimiter đặc biệt**.

| Nguồn | Ví dụ | Vì sao cần kiểm soát? |
| --- | --- | --- |
| HTTP query / form / JSON body | username, search term, address, comment | Client có thể chèn newline, quote, dấu phân cách hoặc payload rất dài. |
| HTTP header | User-Agent, Referer, X-Request-ID | Một số header do client kiểm soát; proxy có thể thay đổi nhưng không làm mọi giá trị thành đáng tin cậy. |
| URL và request path | encoded path, query string | Có thể chứa percent-encoded sequence và nhiều lớp decode. |
| Database record | tên hiển thị, ghi chú từ DB | Dữ liệu đã được lưu **không có nghĩa đã an toàn cho log**; có thể là stored log injection. |
| Message queue / webhook | payload, correlation ID | Producer bên ngoài hoặc dịch vụ upstream có thể lỗi hoặc bị xâm nhập. |
| Exception message | thông điệp lỗi SDK/DB/HTTP client | Có thể chứa lại URL, hostname, user input hoặc thông tin nhạy cảm. |
| MDC / ThreadContext | userId, tenantId, requestId, traceId | Khi lấy từ request hoặc header vẫn phải validate/encode; context không tự khử độc. |
| File name/path | upload filename, object key | Có thể chứa ký tự điều khiển hoặc chuỗi trông như log header. |
| Giá trị từ config ngoài | tenant label, endpoint, service name | Có thể sai định dạng; cần hợp đồng và kiểm soát quyền sửa. |

**Trust boundary** có thể xuất hiện nhiều lần. Ví dụ client gửi header request ID, ứng dụng chép vào MDC, Logback format thành text, collector lại parse thành JSON. Nếu không có bước validate/encode phù hợp, một ký tự đặc biệt có thể phá cấu trúc tại **bất kỳ tầng nào sử dụng nó như cú pháp**.

Đừng coi mọi giá trị đi qua framework là đã được escape. Một framework HTTP giúp parse request không có nghĩa nó đã chuẩn hóa message để an toàn cho mọi layout logging.

## 4. Các kiểu ký tự cần chú ý

### 4.1. CR/LF: ký tự nguy hiểm điển hình với log một dòng

- **CR**, ký hiệu CR hoặc U+000D: đưa con trỏ về đầu dòng trong nhiều môi trường.
- **LF**, ký hiệu LF hoặc U+000A: xuống dòng.
- **CRLF**, hai ký tự liên tiếp: thường dùng làm line ending trong nhiều protocol và hệ thống.

Nếu log consumer xem mỗi dòng là một event, một input chứa CR/LF thô có thể làm event bị chia. Cách chuyển đổi cho định dạng text một dòng thường là:

~~~text
Dữ liệu gốc:     alice + CR + LF + ERROR fake
Dữ liệu log:     alice\r\nERROR fake
~~~

Ở dòng thứ hai, **\r** và **\n** là các ký tự hiển thị gồm dấu gạch chéo ngược và chữ cái, **không phải CR và LF thật**. Dòng text vẫn chỉ có một record.

### 4.2. Tab và delimiter

Nếu log dùng dấu **|**, dấu phẩy, tab, dấu bằng hoặc dấu nháy để phân chia field, input chứa những dấu đó có thể làm parser hiểu nhầm số cột hoặc giá trị field.

Ví dụ định dạng tự tạo:

~~~text
event=login|user=alice|outcome=DENIED
~~~

Input user do client gửi có thêm ký tự pipe và chuỗi outcome có thể khiến parser ngây thơ tạo field khác:

~~~text
event=login|user=alice|outcome=APPROVED|outcome=DENIED
~~~

Ngay cả khi không có CRLF, đây vẫn là **field injection**. Muốn giữ format này phải có cơ chế encode/delimit **được parser hiểu**, hoặc dùng structured logging thay vì tự ghép chuỗi.

Dùng dấu nháy kép quanh user cũng chỉ an toàn nếu đã có quy tắc escape dấu nháy, dấu gạch chéo ngược và ký tự phân tách record; parser phải tuân theo quy tắc đó. Không thể lấy cách escape cho JSON rồi mặc nhiên dùng như escape CSV hoặc format pipe-delimited.

### 4.3. Terminal escape và các ký tự điều khiển Unicode

Một số dữ liệu có thể chứa:

- **TAB**, **NUL**, **ESC** và các ký tự C0/C1 control.
- **U+0085** (next line), **U+2028** (line separator), **U+2029** (paragraph separator).
- **ANSI escape sequences** bắt đầu với ESC, có thể khiến terminal tô màu, dịch con trỏ hoặc xóa hiển thị.
- **Bidirectional formatting controls** như U+202E và các kí tự thuộc nhóm directional embedding/isolate, có thể làm người đọc nhìn thứ tự ký tự khác với thứ tự lưu trong dữ liệu.
- Chuỗi cực dài hoặc ký tự Unicode bất thường khiến hệ thu thập/renderer giới hạn hoặc xử lý không nhất quán.

Không phải mọi ký tự Unicode đặc biệt đều nguy hiểm trong mọi format. Nhưng với **text log một dòng** và terminal/dashboard phải tính đến chúng khi định nghĩa boundary, encoding và UI. Với những trường dạng ID chuẩn (ví dụ traceId) nên **validate theo grammar cụ thể**, không chỉ escape.

## 5. Phân biệt validation, escaping, sanitization và redaction

| Kỹ thuật | Mục đích | Ví dụ |
| --- | --- | --- |
| **Input validation** | Xác định dữ liệu có đúng miền giá trị hay không. | Request ID chỉ gồm chữ, số, dấu gạch và giới hạn độ dài; traceId đúng số ký tự hex. |
| **Output escaping/encoding** | Bảo đảm dữ liệu vẫn là **data** trong định dạng xuất. | Newline trong text → chuỗi hiển thị \\n; chuỗi trong JSON → JSON string hợp lệ. |
| **Sanitization** | Làm sạch/chuyển đổi theo policy, có thể làm mất thông tin. | Loại bỏ control characters nếu field không được phép có chúng. |
| **Redaction / masking** | Ngăn lưu dữ liệu nhạy cảm ngoài ý muốn. | Không ghi password, access token; thay bằng [REDACTED] khi cần. |
| **Truncation / size limit** | Giới hạn tài nguyên và payload. | Giới hạn kích thước field, thêm dấu báo truncated. |
| **Structured logging** | Giữ field riêng và để encoder sinh cú pháp đích. | JSON object với event, username, outcome. |

Các kỹ thuật **bổ trợ nhau**, không thay thế lẫn nhau.

- Chỉ validate alphanumeric phù hợp với **traceId** nhưng không áp dụng máy móc cho tên người dùng đa ngôn ngữ.
- Chỉ escape CRLF không tự xử lý token/password hay nội dung HTML nguy hiểm khi hiển thị trong browser.
- Chỉ redact dữ liệu nhạy cảm không ngăn dấu xuống dòng trong một username hợp lệ.
- Chỉ chuyển sang JSON string không tự kiểm soát payload dài hàng megabyte hay nội dung chứa secret.
- Chỉ ghi log bằng placeholder không tự thay đổi cách layout xuất text.

Một thứ tự xử lý dễ quản trị là:

~~~text
Dữ liệu từ nguồn không tin cậy
       │
       ▼
Validate kiểu, cú pháp và giới hạn hợp đồng
       │
       ▼
Chọn field thật sự cần log (data minimization)
       │
       ▼
Redact/mask dữ liệu nhạy cảm
       │
       ▼
Structured event / constant message template
       │
       ▼
Encode cho định dạng sink bằng encoder đáng tin cậy
       │
       ▼
Collector, index, viewer có kiểm tra riêng
~~~

**Không encode JSON ở đầu vào rồi lại đưa chuỗi JSON-encoded vào encoder JSON một lần nữa** trừ khi hệ thống cố ý lưu *chuỗi đã escape*. Double escaping làm dữ liệu bị thay đổi và gây khó truy vấn. Nên lưu/luân chuyển value theo kiểu dữ liệu ban đầu, chỉ encode ở **ranh giới tuần tự hóa sang định dạng cụ thể**.

## 6. Ví dụ Java 17 độc lập: log forging và escape về một dòng

Chương trình dùng **java.util.logging** (JUL) sẵn trong JDK 17. Để dễ xác minh stdout, ta dùng một **Handler** demo ghi thẳng ra stdout và một **Formatter** xử lý tất cả text message trước khi xuất. Phần đầu minh họa **output không an toàn**, phần sau dùng formatter giữ event ở một dòng.

Hàm **escapeOneLine** có chính sách minh họa:

1. CR, LF, TAB, backslash và dấu nháy kép được biểu diễn bằng escape sequence có thể đọc.
2. Các ký tự điều khiển khác, U+2028/U+2029, một số directional controls và surrogate không ghép hợp lệ được biểu diễn dạng **\\uXXXX**.
3. Các ký tự văn bản Unicode còn lại được giữ nguyên, tránh phá hỏng dấu tiếng Việt.
4. Logger sử dụng **constant template** và tham số tách biệt, thay vì lấy input làm template.

Đặt tên tệp **SecureLoggingDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SecureLoggingDemo {

    private static String escapeOneLine(String value) {
        StringBuilder out = new StringBuilder(value.length());
        for (int i = 0; i < value.length();) {
            int cp = value.codePointAt(i);
            i += Character.charCount(cp);

            switch (cp) {
                case '\r' -> out.append("\\r");
                case '\n' -> out.append("\\n");
                case '\t' -> out.append("\\t");
                case '\\' -> out.append("\\\\");
                case '"' -> out.append("\\\"");
                default -> {
                    boolean unsafeControl = Character.isISOControl(cp)
                            || cp == 0x2028 || cp == 0x2029
                            || (cp >= 0x202A && cp <= 0x202E)
                            || (cp >= 0x2066 && cp <= 0x2069)
                            || (cp >= 0xD800 && cp <= 0xDFFF);
                    if (unsafeControl) {
                        out.append(String.format(Locale.ROOT, "\\u%04X", cp));
                    } else {
                        out.appendCodePoint(cp);
                    }
                }
            }
        }
        return out.toString();
    }

    private static Handler safeStdoutHandler() {
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.print(getFormatter().format(record));
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                // formatMessage ap dung template/parameters JUL.
                String body = formatMessage(record);
                return record.getLevel().getName() + " "
                        + escapeOneLine(body)
                        + System.lineSeparator();
            }
        });
        return handler;
    }

    public static void main(String[] args) {
        String userInput =
                "alice\r\nERROR authentication granted user=\"root\"";

        // Chi de minh hoa tac hai: noi chuoi raw va in ra terminal.
        System.out.println("RAW:");
        System.out.println(
                "WARNING Authentication rejected for user=" + userInput);

        Logger logger = Logger.getLogger("demo.auth");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = safeStdoutHandler();
        logger.addHandler(handler);
        try {
            System.out.println("SAFE:");
            logger.log(Level.WARNING,
                    "Authentication rejected for user={0}", userInput);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy, không cần dependency ngoài JDK:

~~~bash
javac SecureLoggingDemo.java
java SecureLoggingDemo
~~~

**stdout dự kiến**:

~~~text
RAW:
WARNING Authentication rejected for user=alice
ERROR authentication granted user="root"
SAFE:
WARNING Authentication rejected for user=alice\r\nERROR authentication granted user=\"root\"
~~~

Ở phần **RAW**, hai ký tự CR/LF thực sự khiến người đọc thấy hai dòng. Ở phần **SAFE**, ký tự CR/LF được chuyển thành chuỗi hiển thị **\\r\\n**, và dấu nháy trong dữ liệu thành **\\"**. Kết quả chỉ còn **một physical log line** cho sự kiện WARNING (ngoài nhãn SAFE). Dòng ERROR giả không còn xuất hiện như một record độc lập.

Một số terminal có hành vi con trỏ hơi khác với ký tự CR thô; bản chất quan trọng là CR/LF có thể chia hoặc ghi đè cách hiển thị một dòng. Output trên là biểu diễn từng dòng khi xem thông thường.

### Tại sao code có thể chạy và đầu ra xác định?

- Chương trình chỉ dùng các class **java.util.logging** và **java.lang** trong JDK 17.
- JUL **logger.log(Level, String, Object)** nhận tham số riêng. **Formatter.formatMessage** áp dụng template chứa **{0}** rồi mới qua **escapeOneLine**.
- Handler được gắn riêng, **setUseParentHandlers(false)** ngăn record đi tiếp qua ConsoleHandler mặc định của root; không phát sinh thêm dòng console.
- Handler định dạng không thêm timestamp/thread, nên stdout không phụ thuộc thời gian hay locale.
- Demo chạy đồng bộ một thread; không có race về thứ tự.
- Hàm escape không cắt đôi surrogate pair hợp lệ và không bỏ dấu tiếng Việt bình thường.
- **safeStdoutHandler** chỉ để minh họa. Production không nên tự viết handler tối giản này: thiếu chính sách concurrency, batching, retry, error handling, giới hạn bộ nhớ và nhiều metadata hữu ích.

### Điều gì chưa được demo bảo đảm?

Hàm **escapeOneLine** phù hợp với **message text xuất ra một dòng ở stdout**. Nó không phải universal sanitizer:

- Nếu đưa kết quả vào **JSON string**, phải dùng JSON encoder; tự chèn escape theo cú pháp text rồi lại encode JSON sẽ gây double escaping.
- Nếu đưa kết quả vào **HTML dashboard**, phải render bằng text node hoặc escape HTML ở tầng UI. Các ký tự HTML như dấu nhỏ hơn/lớn hơn trong text log không được hàm này encode.
- Nếu format log có dấu **|** hoặc CSV delimiter, phải định nghĩa escape riêng cho field grammar đó.
- Nếu log có **stack trace nhiều dòng hợp lệ**, cần quy ước event framing riêng, không ép xóa ngữ nghĩa lỗi.
- Demo không có giới hạn độ dài. Production phải giới hạn input/log event để tránh làm cạn RAM/disk.

## 7. Dùng SLF4J và Logback đúng cách

Trong dự án Java đã dùng **SLF4J**, mẫu thường gặp là:

~~~java
// Minh hoa: can SLF4J API, provider va class/variables trong ung dung.
logger.warn("Login rejected for user {}", userInput);
~~~

**Tốt hơn nối chuỗi trực tiếp** vì message template là hằng, framework có thể trì hoãn format và tối ưu khi mức log bị tắt. Tuy nhiên **tham số userInput vẫn có thể chứa CR/LF**. Nếu backend format với pattern text kiểu **%msg%n** và không escape, log forging vẫn có thể xảy ra.

Mẫu rủi ro:

~~~java
// BAD: dung input tao mot phan format/template.
logger.warn("Login rejected for " + userInput + " with role {}",
        role);
~~~

Cách tốt hơn là giữ template hằng và mọi dữ liệu bên ngoài ở parameter/structured field:

~~~java
// Prefer: message template khong do user quyet dinh.
logger.warn("Login rejected for user {} with role {}",
        userInput, role);
~~~

**Nhưng vẫn phải cấu hình encoder/layout đúng.** Placeholder giải quyết nhiều vấn đề của API và template, không tự thực hiện output encoding cho text log.

### 7.1. Với plain text Logback

Một cấu hình pattern phổ biến:

~~~xml
<encoder>
    <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
</encoder>
~~~

Pattern trên **không tự chứng minh** rằng input trong message được khử CRLF. Nếu cần tương thích với log text một dòng:

- Ưu tiên một **encoder đã được kiểm chứng** có chức năng escaping các field không tin cậy.
- Hoặc tạo một **central formatting policy** theo grammar đích (ví dụ custom converter/formatter đã được test), thay vì mỗi module tự gọi replace một kiểu.
- Kiểm thử cả message, MDC, markers, exception message và mọi field được đưa vào pattern.
- Xác minh log **tại file/stdout sau khi encoder chạy** và **sau collector**, không chỉ kiểm tra chuỗi Java ban đầu.

Đừng chọn đại một chuỗi regex trong cấu hình rồi cho rằng đã xử lý mọi CR, LF, Unicode separators, delimiter và ký tự điều khiển. Có thể dùng cơ chế replace của backend cho một số trường hợp, nhưng đó phải là giải pháp có phạm vi rõ, được kiểm thử với phiên bản thực chạy.

### 7.2. Structured logging với SLF4J 2.x

SLF4J 2.x hỗ trợ fluent API và key-value pairs. Ví dụ **minh họa trong project đã có logger và backend tương thích**:

~~~java
logger.atWarn()
      .addKeyValue("event", "auth.reject")
      .addKeyValue("username", userInput)
      .addKeyValue("outcome", "DENIED")
      .log("Authentication rejected");
~~~

Ý nghĩa: các giá trị được mô hình hóa thành **fields** thay vì ép vào một message text. Tuy nhiên API không tự buộc mọi backend xuất JSON. **Phải cấu hình provider và encoder/layout thực sự serializes key-value pairs an toàn**. Nếu backend bỏ qua field hoặc ghép lại thành text không escape, rủi ro vẫn tồn tại.

Không dùng API như bằng chứng rằng log đã an toàn; hãy kiểm tra output thực tế.

## 8. JSON structured logging: giải pháp nên ưu tiên

OWASP khuyến nghị **structured log format**, ví dụ JSON, thay vì định dạng text tùy ý dễ bị tiêm dòng. Trong một JSON Lines stream đúng thiết kế, mỗi physical line là một JSON object; bên trong mỗi string, newline phải được biểu diễn thành escape sequence theo luật JSON.

Một event minh họa:

~~~json
{
  "event": "auth.reject",
  "severity": "WARN",
  "username": "alice\r\nERROR fake-event",
  "outcome": "DENIED"
}
~~~

Đây là **JSON trình bày nhiều dòng để học**. Khi viết thành **JSON Lines** cho collector, encoder sẽ ghi object trên một dòng vật lý:

~~~json
{"event":"auth.reject","severity":"WARN","username":"alice\r\nERROR fake-event","outcome":"DENIED"}
~~~

Trong ví dụ JSON, chuỗi **\\r\\n** là các escape sequence trong JSON string. Khi parser JSON đọc lại, giá trị field **username** có thể chứa CR/LF thực tế trong bộ nhớ; nhưng **dòng JSON nguyên bản** không bị ngắt thành một record mới.

**Dùng JSON serializer/encoder đúng chuẩn**, đừng tự dựng JSON bằng cách nối:

~~~java
// BAD: neu userInput co dau nhay kep, backslash hoac newline,
// JSON sinh ra co the bi sai cu phap va tai hien log injection.
String badJson = "{\"user\":\"" + userInput + "\"}";
~~~

Ví dụ với **Jackson** (minh họa, cần dependency jackson-databind và xử lý exception phù hợp):

~~~java
// Illustrative fragment in a project with Jackson dependency.
ObjectMapper mapper = new ObjectMapper();
Map<String, Object> event = Map.of(
        "event", "auth.reject",
        "username", userInput,
        "outcome", "DENIED");
String json = mapper.writeValueAsString(event);
~~~

Đoạn Jackson **không phải chương trình độc lập**; phải import class, có dependency và xử lý JsonProcessingException. JSON serializer xử lý quoting/control characters cho **string values**, nhưng không thay thế redaction hoặc size limits. Nếu lại đưa biến **json** vào một pattern logger có prefix/suffix, toàn bộ dòng output có thể **không còn là JSON Lines**; tốt hơn dùng structured encoder tích hợp logging backend và xuất **một event = một object**.

### Cấu hình backend cần được kiểm chứng

- **Log4j2**: có **JSON Template Layout** để tạo structured output theo template. Tài liệu Log4j2 khuyến nghị nó thay cho PatternLayout khi cần JSON có cấu trúc.
- **Logback**: chọn JSON/structured encoder tương thích với đúng phiên bản Logback, SLF4J và các ứng dụng framework đang dùng; kiểm tra có thật sự ghi fields, exceptions và MDC đúng schema.
- **Spring Boot**: khả năng structured logging phụ thuộc phiên bản Boot và backend. Không suy ra mọi starter logging đều xuất JSON theo mặc định.
- **JUL**: cần formatter/handler hoặc bridge phù hợp nếu muốn JSON; SimpleFormatter mặc định không phải JSON Lines.
- **Collector**: phải giữ framing JSON object, không parse bằng split thô trên dấu phẩy hoặc dấu nháy.

**Không coi JSON như thuốc chữa mọi thứ**: bản ghi JSON có thể hợp lệ nhưng chứa secret, bị truncation, bị gửi sang tenant sai hoặc khi xem trên web bị render bằng innerHTML không an toàn.

## 9. Log4j2: encode theo mục tiêu xuất

Log4j2 **Pattern Layout** có converter **enc / encode** hỗ trợ các dạng **HTML, XML, JSON và CRLF**. Với text log mà mục tiêu trước mắt là chặn CR/LF trong message, một ví dụ PatternLayout là:

~~~xml
<PatternLayout pattern="%d{ISO8601} %-5level %logger - %enc{%m}{CRLF}%n"/>
~~~

**Ý nghĩa:** phần **%m** được chuyển CR/LF thành chuỗi hiển thị trước khi được nối vào pattern. Đây là cơ chế **CRLF encoding cho message**, không phải bảo vệ toàn bộ event. Nếu pattern còn chứa **%X{requestId}**, exception, marker hoặc các trường không tin cậy khác, chúng cũng cần encoding phù hợp theo cùng định dạng.

Nếu cần **JSON object đúng nghĩa**, tài liệu Log4j2 khuyến nghị **JSON Template Layout** thay vì cố xây JSON từ PatternLayout và nhiều converter %enc. Chọn đúng layout, template, output charset, schema và tính tương thích với pipeline.

Các điểm cần nhớ:

- **%enc{%m}{CRLF}** không có nghĩa các delimiter khác, mọi Unicode control hoặc nội dung HTML đều đã được xử lý.
- Escape **JSON** chỉ phù hợp khi xây đúng JSON string context; chèn nó một cách tùy tiện vào log text không tự tạo structured logging.
- Không để input của user quyết định **pattern**, appender configuration, lookup expression hoặc logging template.
- Kiểm tra cả **message** và **metadata** từ ThreadContext/MDC. Một request ID không được validate có thể xuất ở nhiều pattern vị trí khác nhau.
- Chính xác converter và hành vi phải được kiểm tra trên **phiên bản Log4j2** dùng trong hệ thống.

## 10. CSV/TSV và định dạng phân cách riêng

Đôi khi tổ chức xuất log sang CSV, TSV hoặc text có delimiter để nạp bảng. Đây là **ngữ cảnh escape khác JSON**.

### 10.1. CSV

Theo quy tắc CSV thông dụng:

- Field chứa dấu phẩy, dấu nháy hoặc line break cần được quote phù hợp.
- Dấu nháy kép bên trong quoted field thường được biểu diễn bằng **hai dấu nháy kép**.
- Một CSV record hợp lệ có thể kéo dài nhiều dòng vật lý nếu field chứa newline; vì thế **CSV không tự bảo đảm one event = one line**.
- Nếu xuất CSV sang spreadsheet, dữ liệu bắt đầu bằng **=, +, -, @** hoặc control/whitespace liên quan có thể gây **formula injection** khi ứng dụng bảng tính diễn giải. Đây là một mối nguy *khác* log forging, cần biện pháp riêng ở bước xuất bảng tính.

Đừng lấy CSV quoting và coi đó là JSON escaping. Với mục tiêu logging có machine-readable records và stream trên từng dòng, **JSON Lines** thường dễ kiểm soát hơn CSV multiline.

### 10.2. TSV và pipe-delimited

Tab hoặc ký tự **|** trong dữ liệu có thể phá cấu trúc. Phải có grammar/encoder rõ ràng và parser tương ứng, hoặc chuyển sang JSON. Đơn giản gọi **replace("|", "")** làm mất thông tin và có thể còn những đường phá cấu trúc khác như CR/LF, quote hoặc control.

### 10.3. Log đưa lên giao diện web

Một chuỗi đã được escape cho JSON/text **chưa chắc an toàn để chèn vào HTML**. Viewer nên hiển thị nội dung bằng **textContent/text node** hoặc cơ chế template tự escape, không dùng innerHTML với dữ liệu log không tin cậy.

Nếu giao diện có syntax highlighting, linkifier hoặc Markdown renderer, chúng có thể mở thêm một tầng diễn giải. Cần thử input chứa tag, markup, URL bất thường và đảm bảo không có execution trong browser. Không dùng chung một hàm escape cho HTML, JSON và plain text vì mỗi format có grammar khác nhau.

## 11. Những điểm dễ bị bỏ sót khi escape

### 11.1. MDC, requestId và traceId

Một ứng dụng có thể ghi:

~~~java
// Minh hoa, yeu cau backend/SLF4J dependency.
org.slf4j.MDC.put("requestId", requestIdFromHeader);
logger.info("Received request");
~~~

Nếu pattern chứa **%X{requestId}**, input này xuất hiện dù message không chứa gì độc hại. Do đó cần **validate** requestId tại ranh giới HTTP, giới hạn độ dài và allowed character set, rồi **encode** ở output khi cần.

Đối với traceId theo W3C, có định dạng hex và kích thước rõ; kiểm tra đúng định dạng hơn là chấp nhận bất kỳ chuỗi nào. Không nên tin rằng một header tên "trace-id" là đã được chuẩn hóa bởi framework.

### 11.2. Exception và stack trace

Exception message có thể chứa URL, file path hoặc input do bên khác cung cấp. Ngoài ra, stack trace thường gồm nhiều dòng **hợp lệ**. Có hai lựa chọn phổ biến:

1. Structured logging lưu **exception.type, exception.message, exception.stacktrace** thành các trường riêng, mỗi trường được encode đúng.
2. Text logging vẫn cho phép stack trace nhiều dòng nhưng có **record framing/correlation** được xác định rõ (ví dụ collector hỗ trợ multiline), đồng thời không để **untrusted message** chèn thêm dòng giống header.

Không nên xóa toàn bộ stack trace chỉ vì muốn bảo vệ CRLF. Cũng không nên ghi toàn bộ exception raw nếu chứa credential, secret hoặc body nhạy cảm.

### 11.3. Encoding nhiều lần hoặc decode không nhất quán

Giả sử chuỗi gửi qua HTTP có percent-encoded CR/LF. Tầng HTTP có thể decode nó trước khi ứng dụng nhận được. Nếu một lớp xử lý chỉ kiểm tra chuỗi **%0D%0A** nhưng lớp khác đã decode thành CRLF, kiểm tra có thể bị qua mặt.

Nguyên tắc:

- Xác định **biểu diễn chuẩn** của dữ liệu tại điểm validation.
- Không decode/normalize nhiều lần không kiểm soát.
- Khi xuất, encoder phải nhận đúng dữ liệu chuẩn và escape **ký tự thực tế**.
- Không tự động tin một chuỗi đã được escape sẵn từ upstream; có thể xảy ra double escaping hoặc dữ liệu bị decode lại ở downstream.

Với Java Unicode string, hãy test cả surrogate pair hợp lệ, ký tự không ghép hợp lệ, dấu tiếng Việt, emoji và separators đặc biệt. Chỉ xử lý từng **char** khi bạn hiểu tác động lên Unicode; đối với dữ liệu cần giới hạn theo ký tự, cân nhắc **code points** thay vì cắt tùy tiện giữa cặp surrogate.

### 11.4. Log input dài và tài nguyên

Một chuỗi vài megabyte không chứa CRLF vẫn có thể khiến hệ logging mất nhiều CPU/RAM, tăng GC, làm đầy queue/disk hoặc bị collector cắt bớt. Cần:

- Giới hạn độ dài **theo loại field**, không nhất thiết dùng một giới hạn cho mọi event.
- Quyết định rõ số đo giới hạn: code points, UTF-16 code units hay byte UTF-8.
- Không cắt giữa surrogate pair hoặc cắt một JSON output tùy tiện làm record không hợp lệ.
- Nếu cắt, thêm metadata **truncated=true**, original length (nếu không nhạy cảm) và event ID; không tạo record có cú pháp hỏng.
- Giới hạn số event và tốc độ ghi đối với input có thể bị gửi liên tục, tránh log flooding.

**Lưu ý**: một số encoder áp dụng giới hạn theo **giá trị field**, không theo toàn bộ event hoặc số byte mã hóa. Khi tính dung lượng collector cần phân biệt các mức này.

### 11.5. Redaction phải diễn ra trước khi dữ liệu rời trust zone

Đừng chỉ dựa vào collector để xóa secret nếu raw stdout/file đã được thu thập, được lưu tạm hoặc hiển thị nơi khác. Ưu tiên **không log secret từ đầu**. Khi cần ghi nhận sự kiện bảo mật, log **loại sự kiện, đối tượng đã được phép ghi, kết quả và correlation ID**, thay vì nguyên token, cookie, password hay personal data.

Escape không làm cho secret trở nên ít bí mật hơn. Ví dụ password không có CRLF thì escape sẽ giữ nguyên password: đó vẫn là vi phạm chính sách.

## 12. Mẫu thiết kế khuyến nghị cho Java service

Một thiết kế có thể vận hành tốt gồm:

1. **Logger API nhất quán**: SLF4J với một backend/provider tương thích hoặc JUL nếu phù hợp.
2. **Constant event name và message template**: không để user input xây log template, layout hoặc logger configuration.
3. **Field schema rõ ràng**: event, severity, service, environment, traceId, requestId, outcome và các field nghiệp vụ được phép.
4. **Validation theo field**: ví dụ UUID/traceId/requestId theo pattern; username có Unicode thì không ép ASCII toàn bộ.
5. **Data minimization + masking**: không log secret/PII ngoài phạm vi được phép.
6. **Structured encoder**: JSON Lines hoặc schema tương đương đã kiểm chứng, một event được tuần tự hóa thành một record đầy đủ.
7. **Size limits và rate controls**: tránh một input gây tràn log pipeline.
8. **Collector/parser cùng hợp đồng**: không dùng regex tách theo delimiter chưa escape; thống nhất charset (thường UTF-8) và behavior với oversized record.
9. **Safe viewer**: text rendering/HTML escaping và quyền truy cập đúng.
10. **Regression tests**: tập payload injection xuyên từ controller/consumer đến file, collector và dashboard.

### Sơ đồ ranh giới an toàn

~~~text
HTTP / Queue / DB (untrusted field values)
            │
            ▼
    Typed validation (domain grammar)
            │
            ▼
  Structured event + redact + limit
            │
            ▼
    Logging API + trusted template
            │
            ▼
  JSON encoder / text encoder theo sink
            │
            ▼
  Console/File → Collector → Storage
            │
            ▼
    Viewer render dưới dạng data
~~~

Nếu **mỗi tầng tự nối chuỗi rồi decode/encode không thống nhất**, càng nhiều bước biến đổi càng dễ sinh lỗi. Cách tốt hơn là giữ fields có cấu trúc càng lâu càng tốt và chỉ serialize tại ranh giới đầu ra tương ứng.

## 13. Kiểm thử an toàn với dữ liệu giả

Chạy test với một **message ID riêng**; kiểm tra số record được ghi, nội dung field sau parse và không có record giả. Dữ liệu thử chỉ là chuỗi do nhóm kiểm thử tự tạo, không chứa password hay token thật.

| Test input | Mục tiêu | Kỳ vọng an toàn |
| --- | --- | --- |
| **alice** | Baseline | Đúng một record; value giữ nguyên. |
| **alice + LF + ERROR fake** | Newline injection | Text one-line hiển thị LF dạng escape; JSON vẫn là một object. |
| **alice + CRLF + WARN fake** | Log forging Windows-style | Không tạo record severity WARN giả. |
| **alice + CR** | Carriage return đơn lẻ | Không ghi đè đầu dòng trên terminal. |
| **TAB, pipe, comma, quote** | Field/delimiter injection | Parser khôi phục đúng số field/giá trị. |
| **Backslash nhiều lần** | Double escape/parser mismatch | Một vòng serialize/deserialize khôi phục đúng value. |
| **NUL, ESC, U+0085** | Control chars / terminal | Không điều khiển terminal hoặc phá log boundary. |
| **U+2028, U+2029** | Unicode line/paragraph separators | Không chia record ngoài ý muốn ở viewer/collector. |
| **U+202E và bidi controls** | Gây hiểu nhầm hiển thị | Có policy encode/hiển thị nhất quán. |
| **Dấu tiếng Việt và emoji** | Unicode correctness | Không mất ký tự hợp lệ, không tạo encoding error. |
| **Input lớn hơn max field** | Log flooding / truncation | Event bounded, truncated flag hợp lệ, JSON không hỏng. |
| **String chứa HTML markup** | Viewer injection | Browser hiển thị như text, không render thành DOM/JS. |
| **requestId từ header** | MDC injection | ID được validate và encoder xử lý cả context fields. |
| **Exception chứa input** | Stack trace + message | Không tạo event giả, vẫn giữ thông tin lỗi phù hợp. |

### Assertion nên thực hiện

- **Một lời gọi log được chấp nhận → một logical event** tại điểm đã quy định, không bị tách thành nhiều record bởi input. Lưu ý collector có thể retry gây duplicate; kiểm thử có thể phải tách vấn đề framing khỏi delivery.
- **Severity/logger/timestamp của event không bị input chi phối**. Các field hệ thống đến từ logging API hoặc schema đã kiểm soát.
- **JSON parse thành công**, value có thể được khôi phục đúng (trừ những trường bị redaction/truncation có chủ đích).
- **Không có secret** trong output thô lẫn sau ingest.
- **Giới hạn kích thước** vẫn hoạt động với ký tự nhiều byte.
- **Viewer** không thực thi HTML/JS hoặc ANSI escape từ field.
- **MDC và nested fields** được xử lý, không chỉ message.
- **Log khi lỗi hệ thống** (disk full, appender error, collector offline) không biến việc ghi log thành lỗi bảo mật khác hoặc làm lộ dữ liệu trong thông báo lỗi.

Đối với payload có control characters vô hình, khi viết test có thể xây bằng biểu thức Unicode code point hoặc escape literal rõ ràng; tránh sao chép chuỗi control vô hình trực tiếp vào tài liệu rồi khó review.

## 14. Kiểm tra Logback/Log4j2/Spring Boot trong ứng dụng thật

### Bước 1: xác định backend

Ứng dụng dùng SLF4J hay JUL? Provider thực sự là Logback, Log4j2 hay backend khác? Cùng lời gọi logger có thể được serialize khác hẳn tùy cấu hình. Một file logback.xml tồn tại trong repository không chứng minh runtime đã nạp nó.

### Bước 2: xác định format thực được ghi

- Logback với pattern **%msg%n** là text layout; phải kiểm tra xử lý CRLF.
- Log4j2 PatternLayout có thể dùng converter **%enc{%m}{CRLF}**, nhưng vẫn cần encode các trường khác.
- Structured encoder có xuất **một object có schema** hay chỉ một message JSON nằm trong dòng text?
- Exception stack trace có thuộc cùng event hay collector đang chia thành nhiều bản ghi?
- Có parser cũ ở downstream không hỗ trợ quoting/escaping mới?

### Bước 3: kiểm thử toàn pipeline

Dùng payload thử vô hại chứa CRLF, quote và Unicode controls. Gửi qua API hoặc message consumer, kiểm tra:

~~~text
source input
  → application event
  → console/file bytes
  → collector parsed event
  → indexed event
  → dashboard rendering
~~~

Một unit test trên **escapeOneLine** chỉ chứng minh một hàm. Muốn kết luận hệ thống không bị log injection, phải kiểm tra end-to-end, nhất là nơi collector tách theo dòng và nơi dashboard render các field.

### Bước 4: bảo vệ mã và cấu hình

- Không nhận input làm layout pattern, file path, logger name hoặc template từ endpoint công khai.
- Giữ backend được cập nhật phù hợp chính sách; xử lý cảnh báo liên quan đến configuration lookups, plugins và dependencies.
- Review cấu hình log ở production khác test/dev thế nào; bảo đảm file test không vô tình được đóng gói.
- Bảo vệ log storage khỏi sửa/xóa trái phép; có retention và access control.
- Nếu cần bằng chứng audit có độ tin cậy cao, triển khai cơ chế lưu bền vững và tamper detection phù hợp, không chỉ dựa vào escape.

## 15. Các hiểu lầm phổ biến

**1. “Dùng dấu ngoặc nhọn của SLF4J là hết log injection.”** Sai. Nó giữ template ổn định, nhưng dữ liệu parameter vẫn có thể chứa CR/LF nếu layout không encode.

**2. “Chỉ replace newline là đủ.”** Sai. Còn CR đơn lẻ, quote/delimiter, ANSI control, Unicode separators và các field khác ngoài message.

**3. “Escape mọi ký tự đặc biệt ngay lúc nhận HTTP.”** Không nên. Hành vi này thay đổi dữ liệu nghiệp vụ và dễ gây double encoding; hãy validate theo domain và encode cho output context.

**4. “JSON format luôn an toàn tuyệt đối.”** JSON encoder đúng ngữ pháp giúp bảo vệ cấu trúc, nhưng không ngăn ghi secret, oversize, log flooding hoặc XSS ở viewer render sai.

**5. “Chỉ message là dữ liệu không tin cậy.”** Sai. requestId, MDC, filename, exception message, service metadata và fields khác đều có thể chứa input bên ngoài.

**6. “Đã escape để ghi file thì có thể hiển thị bằng innerHTML.”** Sai. HTML là một output context khác.

**7. “Sanitize bằng cách xóa toàn bộ CR/LF không có đánh đổi.”** Sai. Bạn có thể làm mất dữ liệu phục vụ điều tra, nhất là exception hoặc comment. Dùng escape có quy tắc thường tốt hơn xóa mù.

**8. “Một regex trong config đủ bảo vệ mọi định dạng.”** Sai. Cần biết grammar, backend, phiên bản, mọi field và consumer.

**9. “Có thể đưa raw request body vào DEBUG vì dev ít rủi ro.”** Sai. Secret/PII và payload injection vẫn có thể vào log dev/CI và bị gửi tới hệ thống chung.

**10. “Hạn chế độ dài không liên quan bảo mật.”** Sai. Log flooding có thể làm cạn tài nguyên và khiến sự kiện quan trọng bị bỏ trong overload.

**11. “Có thể chỉ kiểm tra output của unit test trên một máy.”** Chưa đủ. Terminal, container, collector và viewer có thể xử lý control characters khác nhau.

**12. “Escape cho JSON và CSV có thể hoán đổi.”** Sai. Quy tắc quoting, delimiter và record framing khác nhau, CSV còn có rủi ro formula injection khi xuất sang spreadsheet.

## 16. Bài tập tự luyện

1. Chạy **SecureLoggingDemo.java** rồi giải thích vì sao ở phần RAW có một dòng ERROR không phải event thực và phần SAFE chỉ xuất một dòng WARNING.
2. Sửa input thêm TAB, dấu nháy và backslash; dự đoán escapeOneLine trả về chuỗi nào, so sánh stdout.
3. Thêm U+2028 và U+202E vào input bằng code point (không paste control vô hình). Kiểm chứng kết quả dạng \\u2028 và \\u202E.
4. Thử lập một text log dùng dấu pipe làm delimiter. Đưa input chứa pipe và dấu bằng vào field user; định nghĩa grammar escaping đúng trước khi viết parser. Sau đó so với JSON Lines.
5. Trong ứng dụng SLF4J + Logback đang có, tạo một log với username chứa CRLF. Kiểm tra output cuối ở file/collector. Mô tả vì sao chỉ chuyển từ nối chuỗi sang placeholder chưa giải quyết hoàn toàn.
6. Với Log4j2, so sánh PatternLayout **%m%n** và **%enc{%m}{CRLF}%n** trên dữ liệu thử. Xác định các field MDC/exception vẫn cần cơ chế riêng.
7. Thêm giới hạn độ dài field trong hệ structured logging. Kiểm thử đầu vào có emoji gần ranh giới, đảm bảo không cắt hỏng surrogate/UTF-8 và JSON vẫn parse được.
8. Mô phỏng dashboard render một trường log chứa HTML markup. Chỉ ra vì sao phải dùng textContent hoặc HTML escaping dù log đã là JSON.
9. Thiết kế một test end-to-end: một HTTP request mang input CRLF phải tạo **một logical security event**, không có event giả, không lộ token và không sinh duplicate do collector parsing.

## 17. Kết luận

**Escape dữ liệu đầu vào trong logging là bảo vệ ranh giới giữa dữ liệu không tin cậy và cú pháp log.** Muốn chống log forging, phải kiểm soát cả CR/LF, delimiter, control characters, metadata và cách các tầng phía sau diễn giải output. Với ứng dụng Java hiện đại, ưu tiên **constant templates + typed fields + redaction + structured encoder (JSON) + size limits + end-to-end tests**. Khi còn dùng plain text, escape phải được thiết kế cho **đúng format và consumer**, không dựa vào một replace ngẫu nhiên.

**Thông điệp cần nhớ:** validation là cho *giá trị có hợp lệ không*; escaping là cho *giá trị được biểu diễn an toàn trong output như thế nào*; redaction là cho *dữ liệu nào không được xuất hiện trong log*. Một hệ thống an toàn cần cả ba.

### Tài liệu tham khảo kỹ thuật

- OWASP Logging Cheat Sheet, phần Event Data và Log Injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Log Injection: https://owasp.org/www-community/attacks/Log_Injection
- MITRE CWE-117 — Improper Output Neutralization for Logs: https://cwe.mitre.org/data/definitions/117.html
- Apache Log4j2 Pattern Layout, Encode converter và khuyến nghị structured logging: https://logging.apache.org/log4j/2.x/manual/pattern-layout.html
- Apache Log4j2 JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- SLF4J Manual / fluent API: https://www.slf4j.org/manual.html
- Oracle Java 17 — java.util.logging.Formatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java 17 — Character/codePoint utilities: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html