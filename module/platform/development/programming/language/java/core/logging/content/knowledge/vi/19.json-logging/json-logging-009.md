# Escape JSON trong Java Logging: ghi log JSON an toàn, đúng cú pháp và dễ thu thập

## 1. Escape JSON là gì?

**Escape JSON** là quá trình biểu diễn những ký tự có ý nghĩa đặc biệt hoặc không được phép xuất hiện trực tiếp trong **chuỗi JSON** dưới dạng các chuỗi escape hợp lệ. Khi một ứng dụng Java ghi log theo JSON, dữ liệu động như message, exception message, URL, tên file, request ID hoặc nội dung nhập từ người dùng có thể chứa dấu ngoặc kép, dấu gạch chéo ngược, xuống dòng và ký tự điều khiển. Nếu các giá trị này được ghép trực tiếp vào JSON, bản ghi có thể **sai cú pháp**, bị tách thành nhiều dòng hoặc làm mất ranh giới giữa các field.

Ví dụ một message có dấu ngoặc kép và xuống dòng:

~~~text
Giá trị Java ở runtime:
user said "OK"
next line

Biểu diễn JSON string hợp lệ:
"user said \"OK\"\nnext line"
~~~

Trong biểu diễn JSON ở trên, `\"` biểu thị dấu ngoặc kép **thuộc nội dung chuỗi**, còn `\n` biểu thị ký tự newline **bên trong giá trị**. Khi đọc JSON, parser khôi phục đúng chuỗi gốc. Trên file log dạng JSON Lines, toàn bộ record có thể được đặt trên **một dòng vật lý**, mặc dù chuỗi gốc chứa xuống dòng.

**Điều quan trọng:** escape JSON **không** có nghĩa là xóa ký tự, mã hóa bí mật, đổi dữ liệu thành URL-encoded, hay biến text bất kỳ thành một JSON object an toàn. Escape là **quy tắc cú pháp cho string value và string key** của JSON.

Ví dụ log JSON có cấu trúc:

~~~json
{"level":"INFO","eventCode":"USER-1001","message":"user said \"OK\"\nnext line","requestId":"req-17"}
~~~

Parser sẽ hiểu đây là **một object** có bốn field; giá trị `message` có nội dung gồm hai dòng trong bộ nhớ sau khi giải mã JSON. Bộ thu thập được thiết kế cho NDJSON có thể xử lý một record trên một dòng vì ký tự newline trong message được escape, không nằm dưới dạng raw newline ở bên trong string.

## 2. Các ký tự bắt buộc phải escape theo JSON

Theo **RFC 8259, mục 7 (Strings)**, chuỗi JSON được đặt trong dấu ngoặc kép. Ba nhóm **bắt buộc** phải escape trong nội dung chuỗi là:

1. Dấu ngoặc kép `"` (U+0022).
2. Dấu gạch chéo ngược `\` (U+005C).
3. Các ký tự điều khiển từ **U+0000 đến U+001F**, bao gồm tab, LF và CR.

Các escape ngắn được JSON hỗ trợ:

| Ký tự trong dữ liệu | Chuỗi ký tự trong JSON text | Ý nghĩa |
| --- | --- | --- |
| `"` | `\"` | Dấu ngoặc kép |
| `\` | `\\` | Dấu backslash |
| Backspace U+0008 | `\b` | Backspace |
| Form feed U+000C | `\f` | Form feed |
| Line feed U+000A | `\n` | Xuống dòng LF |
| Carriage return U+000D | `\r` | Quay đầu dòng CR |
| Tab U+0009 | `\t` | Tab |
| Dấu slash `/` | `\/` nếu muốn | Escape slash là **tùy chọn**, không bắt buộc |
| Các control char còn lại U+0000–U+001F | `\u00XX` | Biểu diễn Unicode bằng bốn chữ số hex |

Ví dụ ký tự NUL (U+0000) có thể biểu diễn thành `\u0000`. Chuỗi JSON `"a\u0000b"` vẫn có thể được parser chuyển lại thành chuỗi chứa NUL; việc hệ thống downstream có chấp nhận hoặc hiển thị ký tự ấy như thế nào là vấn đề riêng.

**Không bắt buộc escape mọi ký tự Unicode.** Với một JSON text mã hóa UTF-8, các chữ tiếng Việt như “đ”, “ế”, “ộ” và ký tự emoji có thể tồn tại trực tiếp nếu được mã hóa đúng. Việc biểu diễn chúng bằng `\uXXXX` hoặc cặp surrogate `\uXXXX\uYYYY` cũng có thể hợp lệ. Hai cách biểu diễn khác nhau về **byte văn bản JSON**, nhưng có thể giải mã thành cùng **giá trị chuỗi**.

Một số encoder có lựa chọn escape thêm dấu `/`, các ký tự không phải ASCII hoặc U+2028/U+2029 vì lý do tương thích với một môi trường nhúng cụ thể. Đó là chính sách của encoder/ngữ cảnh, **không phải yêu cầu bắt buộc của RFC 8259 cho mọi JSON string**.

## 3. Ba lớp cú pháp dễ nhầm: Java source, JSON text và chuỗi sau parse

Khi viết ví dụ, cần tách ba góc nhìn:

1. **Java source literal:** đoạn mã có dấu backslash để tạo chuỗi ở runtime.
2. **Java String lúc runtime:** dãy ký tự thật, có thể gồm newline, tab hoặc quote.
3. **JSON text được serialize:** dãy byte/ký tự biểu diễn dữ liệu theo cú pháp JSON, thường gồm backslash để escape.

Ví dụ trong Java:

~~~java
String message = "first\nsecond";
~~~

Trong source, `\n` là hai ký tự của cách viết literal Java, nhưng giá trị của `message` ở runtime có **một ký tự LF thật** giữa `first` và `second`. Nếu logger xuất message qua JSON encoder, phần giá trị message trong JSON text thường xuất hiện là:

~~~json
{"message":"first\nsecond"}
~~~

Trong file JSON trên, hai ký tự `\` và `n` biểu diễn ký tự LF ở bên trong giá trị; người đọc không thấy một dòng vật lý mới chen giữa `first` và `second`. Khi dùng parser, `message` được trả lại thành chuỗi có LF thật.

### Backslash trong đường dẫn

Java string literal:

~~~java
String path = "C:\\logs\\app.log";
~~~

Giá trị runtime là đường dẫn Windows `C:\logs\app.log`. Khi serialize vào JSON string, backslash phải được escape:

~~~json
{"path":"C:\\logs\\app.log"}
~~~

Nếu viết raw `{"path":"C:\logs\app.log"}`, những đoạn như `\l` và `\a` không phải escape hợp lệ của JSON; parser có thể từ chối cả bản ghi. Không được chỉ thay dấu ngoặc kép mà quên backslash.

### Đừng escape hai lần

Một JSON encoder đã nhận **giá trị chuỗi Java gốc** sẽ escape đúng khi serialize. Nếu code ứng dụng tự thay newline bằng văn bản `\n` trước, rồi tiếp tục đưa vào encoder, có thể tạo ra `\\n` trong JSON text. Parser lúc này nhận lại hai ký tự backslash và “n”, **không phải newline gốc**.

**Đúng:** truyền giá trị thô theo API typed của encoder.

**Sai trong nhiều tình huống:** gọi một hàm escape tùy biến, sau đó đặt kết quả đã escape vào `ObjectMapper.writeValueAsString(...)` hoặc layout JSON như thể nó vẫn là dữ liệu thô.

## 4. Vì sao JSON escaping đặc biệt quan trọng với logging?

Một log thường chứa dữ liệu từ các **trust boundaries**: HTTP headers, URI, user agent, tên tệp, exception message, dữ liệu queue hoặc phản hồi từ dependency. Dữ liệu này có thể mang dấu `"`, dấu `\` hoặc CR/LF.

Nếu tạo JSON bằng nối chuỗi:

~~~java
// SAI: mã minh họa, không phải chương trình độc lập.
String json = "{\"level\":\"INFO\",\"username\":\""
        + username + "\"}";
~~~

với `username` chứa:

~~~text
alice","level":"ERROR","fake":"1
~~~

đoạn nối chuỗi có thể làm dữ liệu người dùng thoát ra khỏi **string value** và tạo ra các field JSON ngoài dự định (hoặc gây trùng key, khiến parser/downstream diễn giải khác nhau). Đó là dạng **JSON injection** trong log. Một số parser có thể chấp nhận object có key trùng hoặc chọn giá trị cuối; ứng dụng không nên dựa vào quy tắc khi gặp log không tin cậy.

Với JSON string escaping đúng, giá trị trở thành một string duy nhất:

~~~json
{"level":"INFO","username":"alice\",\"level\":\"ERROR\",\"fake\":\"1"}
~~~

Dữ liệu chứa text trông giống key JSON, nhưng parser không coi nó là những field bổ sung.

**Có escape không đồng nghĩa có thể log mọi dữ liệu.** Những chuỗi như token, password và thông tin cá nhân vẫn phải được loại, masked hoặc hạn chế theo chính sách trước khi xuất. JSON escaping chỉ bảo vệ **cấu trúc biểu diễn**, không tự bảo vệ **nội dung nhạy cảm**.

## 5. JSON Lines / NDJSON: một log event trên một dòng vật lý

Đối với log vận hành, một dạng phổ biến là **NDJSON/JSON Lines**, trong đó mỗi dòng kết thúc bằng newline và chứa **một JSON object hoàn chỉnh**:

~~~text
{"level":"INFO","eventCode":"ORD-1001","message":"Checkout started"}
{"level":"WARN","eventCode":"ORD-1501","message":"Retry after timeout\nsecond attempt"}
{"level":"ERROR","eventCode":"ORD-1500","message":"Checkout failed"}
~~~

Có **ba dòng vật lý**, tương ứng ba event; ký tự `\n` trong message thứ hai là escape JSON, không tạo thêm event. Đặc tính một-event-một-dòng thuận tiện cho agent đọc file/stream, indexer và công cụ dòng lệnh.

Để cấu hình NDJSON đúng:

- Encoder/layout phải xuất **một object JSON hợp lệ** cho mỗi event, không chèn một đoạn log text tự do giữa các object.
- Mỗi event kết thúc bằng **đúng ranh giới dòng** mà pipeline mong đợi; newline ở **bên trong string** phải được escape.
- Không bật pretty-print đa dòng nếu collector giả định một event trên một dòng. Pretty-print có thể vẫn tạo JSON hợp lệ nhưng phá giả định NDJSON.
- Không ghi thêm banner/debug/status message không thuộc JSON vào cùng một stream mà collector đang parse cứng như NDJSON, trừ khi pipeline có cách xử lý.
- Một JSON object có thể có field chứa stack trace dài, nhưng stack trace phải được encode thành một string hoặc cấu trúc hợp lệ.
- Khi log vượt giới hạn kích thước, encoder/collector có thể cắt record; file có thể chứa JSON không hoàn chỉnh. Phải giám sát độ dài event và cấu hình giới hạn có chủ đích.

**NDJSON không có nghĩa JSON array.** Nội dung ba dòng ở ví dụ không phải một JSON document duy nhất có dấu `[`/`]`, mà là ba JSON document độc lập, mỗi document là một dòng.

## 6. Java 17: ví dụ chạy được với JUL và JSON escaping

Ví dụ sau dùng **chỉ JDK 17**, không cần Maven. Mục tiêu là chứng minh:

1. Dấu quote, backslash, LF, tab và control char được escape trong JSON string.
2. Sự kiện có field cố định và dữ liệu có kiểu (ví dụ `attempt` là number).
3. Exception message chứa newline không làm record bị tách dòng.
4. Unicode ngoài ASCII có thể được biểu diễn bằng `\uXXXX` hoặc **cặp surrogate hợp lệ**.
5. Dữ liệu trông giống cú pháp JSON khi đã escape vẫn chỉ nằm trong một string value.

**Lưu ý phạm vi:** ta tự viết một hàm escape nhỏ để học cơ chế, không khuyến nghị dùng serializer thủ công này cho production. Trong ứng dụng thực, chọn JSON encoder/serializer đã được duy trì, kiểm thử và có chính sách với dữ liệu không tin cậy.

Tạo tệp **JsonEscapeLoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JsonEscapeLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(JsonEscapeLoggingDemo.class.getName());
    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private JsonEscapeLoggingDemo() {
    }

    private static void appendUnicodeEscape(StringBuilder out, char value) {
        out.append("\\u");
        for (int shift = 12; shift >= 0; shift -= 4) {
            out.append(HEX[(value >>> shift) & 0x0f]);
        }
    }

    private static String quoteJson(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Expected non-null text");
        }

        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (Character.isHighSurrogate(ch)) {
                        if (i + 1 == value.length()
                                || !Character.isLowSurrogate(
                                        value.charAt(i + 1))) {
                            throw new IllegalArgumentException(
                                    "Unpaired high surrogate");
                        }
                        appendUnicodeEscape(out, ch);
                        appendUnicodeEscape(out, value.charAt(++i));
                    } else if (Character.isLowSurrogate(ch)) {
                        throw new IllegalArgumentException(
                                "Unpaired low surrogate");
                    } else if (ch < 0x20 || ch > 0x7e) {
                        appendUnicodeEscape(out, ch);
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] p = record.getParameters();
            String eventCode = (String) p[0];
            String requestId = (String) p[1];
            int attempt = (Integer) p[2];

            StringBuilder out = new StringBuilder("{\"level\":");
            out.append(quoteJson(record.getLevel().getName()));
            out.append(",\"eventCode\":").append(quoteJson(eventCode));
            out.append(",\"requestId\":").append(quoteJson(requestId));
            out.append(",\"attempt\":").append(attempt);
            out.append(",\"message\":").append(quoteJson(record.getMessage()));

            Throwable error = record.getThrown();
            if (error != null) {
                out.append(",\"errorType\":")
                   .append(quoteJson(error.getClass().getSimpleName()));
                out.append(",\"errorMessage\":")
                   .append(quoteJson(error.getMessage()));
            }

            return out.append("}\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler stdout = new StreamHandler(
                System.out, new JsonLineFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
    }

    private static void emit(
            Level level, String eventCode, String requestId,
            int attempt, String message, Throwable error) {
        LogRecord record = new LogRecord(level, message);
        record.setParameters(new Object[] {
                eventCode, requestId, attempt
        });
        record.setThrown(error);
        LOG.log(record);
    }

    public static void main(String[] args) {
        configureLogger();

        emit(Level.INFO, "AUD-1001", "req-1", 2,
                "user said \"OK\"\nnext line", null);

        emit(Level.SEVERE, "AUD-9001", "req-2", 3,
                "path=C:\\temp\\logs\tfailed",
                new IllegalStateException("bad\nstep"));

        System.out.println("unicode=" + quoteJson("café🚀"));
        System.out.println(
                "payload=" + quoteJson("X\"},\"level\":\"ERROR"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 JsonEscapeLoggingDemo.java
java JsonEscapeLoggingDemo
~~~

**Stdout dự kiến chính xác** (các sequence `\n` và `\t` dưới đây là **ký tự escape hiển thị**, không phải ngắt dòng/tab thật):

~~~text
{"level":"INFO","eventCode":"AUD-1001","requestId":"req-1","attempt":2,"message":"user said \"OK\"\nnext line"}
{"level":"SEVERE","eventCode":"AUD-9001","requestId":"req-2","attempt":3,"message":"path=C:\\temp\\logs\tfailed","errorType":"IllegalStateException","errorMessage":"bad\nstep"}
unicode="caf\u00e9\ud83d\ude80"
payload="X\"},\"level\":\"ERROR"
~~~

**Tại sao có đúng bốn dòng vật lý?**

- Hai lần gọi `emit(...)` tạo hai `LogRecord`. Formatter xuất mỗi record thành một object JSON rồi thêm một newline ở **ngoài object**.
- Newline và tab **trong** giá trị `message` hoặc `errorMessage` được `quoteJson(...)` chuyển thành `\n` và `\t`; chúng không chen thêm dòng vật lý.
- `attempt` được append như số nguyên không có dấu ngoặc kép, vì vậy JSON field có kiểu number.
- `errorType` và `errorMessage` chỉ xuất khi `record.getThrown()` không null.
- `quoteJson("café🚀")` tạo `\u00e9` cho chữ “é” và `\ud83d\ude80` cho rocket U+1F680. Đây là cách biểu diễn hợp lệ bằng Unicode escapes trong JSON, không mất ký tự sau khi parser giải mã.
- Payload giả `X"}, "level":"ERROR` (trong mã không có khoảng trắng) được escape khi coi là một string; không thể tự chen field `level` vào object đã được formatter tạo.
- Logger dùng một `StreamHandler` ghi stdout, tắt parent handlers và flush sau từng record. Ví dụ không có timestamp động để expected stdout ổn định.

**Đây là một demo cố ý tối giản.** Nó không in stack trace đầy đủ, không bảo đảm tương thích với mọi đầu vào Unicode không hợp lệ, không có schema quản lý bên ngoài và không giới hạn độ dài. Với `errorMessage`, nếu exception message là null thì helper sẽ ném lỗi; trong production phải dùng chính sách null rõ và encoder có khả năng xử lý trường hợp đó. Không sao chép formatter này vào hệ thống chạy thật mà không bổ sung test và cơ chế phục hồi logging.

### 6.1. Vì sao kiểm tra surrogate pair?

Java `String` lưu dữ liệu theo **UTF-16 code units**. Ký tự ngoài BMP, ví dụ rocket U+1F680, chiếm **hai code units**: high surrogate `D83D` và low surrogate `DE80`. JSON có thể biểu diễn nó bằng cặp escapes `\ud83d\ude80`.

Một high surrogate đứng một mình, hoặc low surrogate không có high surrogate trước đó, không biểu diễn một Unicode scalar value hợp lệ. RFC 8259 chỉ ra các chuỗi chứa surrogate đứng lẻ có thể dẫn tới **hành vi không nhất quán** giữa parser/ứng dụng. Demo chủ động ném `IllegalArgumentException` nếu gặp cặp không hợp lệ, thay vì âm thầm tạo output khó tương tác.

**Cần phân biệt** “kí tự nằm trong BMP” với “mỗi kí tự người dùng nhìn thấy chiếm đúng một Java char”: Unicode có combining marks và các chuỗi emoji nhiều code point. Nếu cần giới hạn độ dài log theo ký tự người dùng, số `String.length()` không đồng nghĩa với số grapheme clusters.

### 6.2. Có bắt buộc biến mọi chữ có dấu thành \uXXXX không?

Không. Demo dùng policy **ASCII-only output** để thấy rõ Unicode escapes và có expected stdout ổn định trên nhiều console. JSON UTF-8 hợp lệ có thể giữ nguyên “café🚀” thành các byte UTF-8 phù hợp; serializer đã được kiểm chứng có thể tùy chỉnh để giữ hoặc escape các ký tự này.

**Đừng dùng `\uXXXX` như một cách giấu dữ liệu nhạy cảm.** Người đọc có thể decode lại chính xác. Đây vẫn là dữ liệu gốc, chỉ đổi hình thức thể hiện.

## 7. Dùng JSON serializer/encoder thay vì nối chuỗi thủ công

Trong ứng dụng thật, lựa chọn tốt là đưa **giá trị đã có kiểu** vào một JSON serializer hoặc structured logging encoder. Ví dụ API của Jackson trong một dự án **đã khai báo dependency phù hợp**:

~~~java
// Snippet minh họa, KHÔNG chạy độc lập chỉ với JDK 17.
// Cần com.fasterxml.jackson.databind.ObjectMapper và dependency Jackson.
com.fasterxml.jackson.databind.ObjectMapper mapper =
        new com.fasterxml.jackson.databind.ObjectMapper();

java.util.Map<String, Object> event =
        new java.util.LinkedHashMap<>();

event.put("level", "INFO");
event.put("eventCode", "ORD-1001");
event.put("message", "user said \"OK\"\nnext line");
event.put("attempt", 2);
event.put("requestId", "req-17");

String json = mapper.writeValueAsString(event);
// JSON serializer bảo vệ ranh giới của từng string value.
~~~

Trong trường hợp hợp lệ, serializer xử lý escape cho `"`, `\`, control chars và Unicode theo cấu hình. Nó cũng phân biệt `attempt=2` là **number** chứ không phải `"2"`, và có thể serialize `true`, `false`, `null`, array/object đúng schema.

Không dùng `Map.toString()`, `Object.toString()` hoặc `String.format("{...}")` để thay cho JSON serializer: chúng không được thiết kế để bảo đảm JSON hợp lệ với dữ liệu bất kỳ.

### 7.1. Tránh double escaping

~~~java
// Sai về mặt dữ liệu khi serializer cũng sẽ escape:
String preEscaped = userMessage.replace("\n", "\\n");
event.put("message", preEscaped);
String json = mapper.writeValueAsString(event);
~~~

Nếu `userMessage` có newline thật, `preEscaped` chứa hai ký tự `\` và `n`. Serializer tiếp tục escape backslash, khiến parser nhận lại **dấu backslash và chữ “n”**, không phải newline gốc.

**Đúng:** đưa thẳng `userMessage` vào field, để **một thành phần cuối cùng** chịu trách nhiệm serialize cho ngữ cảnh JSON.

### 7.2. Không đưa “JSON đã dựng sẵn” vào field string như một object

Một giá trị `"{\"status\":\"ok\"}"` là **string chứa text trông giống JSON**, không phải object. Khi serializer ghi nó vào field `details`, kết quả sẽ có dạng:

~~~json
{"details":"{\"status\":\"ok\"}"}
~~~

Nếu muốn `details` là object có field `status`, hãy parse/validate dữ liệu theo schema và đưa object/map đã được xác thực vào serializer. **Không bỏ dấu ngoặc kép bằng replace** để “đổi string thành object”, vì có thể mở đường cho injection hoặc làm JSON sai cú pháp.

### 7.3. Giá trị không phải string

Một record hợp lệ:

~~~json
{"attempt":2,"success":false,"durationMs":12.5,"error":null,"tags":["backend","retry"]}
~~~

Nếu ghép mọi giá trị trong dấu ngoặc kép, `2` thành `"2"`, `false` thành `"false"`, làm sai kiểu dữ liệu và ảnh hưởng truy vấn. Ngược lại, không cho input bất kỳ chảy thẳng vào vị trí value **không có dấu ngoặc**.

JSON không cho phép `NaN`, `Infinity` hoặc `-Infinity` làm number literal theo RFC 8259. Nếu nguồn Java có `Double.NaN` hay vô cực, encoder cần chính sách như reject, convert thành null hoặc string theo schema; không tự xuất token không hợp lệ rồi coi là JSON chuẩn.

## 8. Escaping stack trace và exception message

Exception có thể chứa đường dẫn Windows, quote, newline, tab, SQL text hoặc phản hồi của dependency. Nếu layout ghi JSON Lines với `error.stack_trace` là một string, mọi newline của stack trace phải được **escape trong chuỗi JSON** để collector không hiểu các dòng `at ...` như những event mới.

Ví dụ **minh họa**:

~~~json
{"level":"ERROR","eventCode":"DB-9001","message":"Database read failed","error":{"type":"java.io.IOException","message":"read failed","stack_trace":"java.io.IOException: read failed\n\tat example.Store.read(Store.java:42)\nCaused by: java.net.SocketException: reset"}}
~~~

Trong file NDJSON, đây vẫn là **một dòng vật lý**. JSON parser khôi phục `stack_trace` với các dấu xuống dòng và tab ở đúng vị trí trong chuỗi.

Có hai quyết định khác nhau:

1. **Giữ Throwable**: ở Java, truyền exception đúng overload để backend có thể lấy stack trace, cause và suppressed.
2. **Serialize Throwable**: encoder quyết định render thành một chuỗi, tách thành object/array có cấu trúc hay rút gọn theo chính sách.

Với JUL, `LogRecord.getThrown()` giữ Throwable nếu được đặt bằng `Logger.log(Level, String, Throwable)` hoặc `LogRecord.setThrown(...)`. Trong demo mục 6, formatter cố ý chỉ đưa `errorType` và `errorMessage`; nó **không in full trace**. Đối với logging lỗi production, dùng formatter/encoder hỗ trợ Throwable đầy đủ hoặc cấu hình rõ schema để giữ cause/suppressed khi cần.

### 8.1. Logging API không tự bảo đảm JSON-safe output

Code:

~~~java
// Minh họa trong một service có logger SLF4J và Throwable e.
LOG.error("operation=load path={} failed", path, e);
~~~

là cách truyền dữ liệu có tham số và Throwable thích hợp. Tuy nhiên **parameterized message không tự escape JSON** nếu backend đang dùng PatternLayout text. Muốn output JSON, cần **JSON encoder/layout** ở bước cuối.

**Tránh tự encode field rồi truyền vào log API**: nếu appender đã có JSON encoder, bạn có thể tạo double escaping, làm dữ liệu parser nhận lại sai và khó tìm kiếm.

### 8.2. Stack trace có thể rất lớn

Một cause chain dài hoặc nhiều suppressed exceptions có thể tạo hàng chục kilobyte hay hơn. Escape newline thành `\n` cũng làm byte output tăng một chút. Cần:

- Giới hạn log volume, tránh ghi full stack trùng ở mọi tầng.
- Đặt độ dài tối đa cho message/field theo chính sách an toàn; đánh dấu khi bị cắt.
- Nếu cắt chuỗi Unicode, không cắt ở giữa surrogate pair hoặc làm encoder phát string không hợp lệ.
- Kiểm tra limit của agent/collector, có thể cắt record ngay cả khi encoder tạo JSON đúng.
- Đo sự gia tăng bytes/s, CPU/allocations và p95/p99 dưới tải.

Không khẳng định mọi log JSON có stack trace luôn được lưu nguyên vẹn chỉ vì encoder chạy thành công; pipeline sau encoder vẫn có thể truncate/drop.

## 9. JSON logging trong SLF4J, Logback và Log4j2

### 9.1. SLF4J là API; encoder thuộc backend

SLF4J cung cấp cách gọi logger, placeholder và trong phiên bản 2.x có fluent key/value API:

~~~java
// Snippet minh họa trong ứng dụng có SLF4J 2.x Logger LOG.
LOG.atInfo()
   .addKeyValue("eventCode", "ORD-1001")
   .addKeyValue("requestId", requestId)
   .addKeyValue("messageSource", source)
   .log("Order accepted");
~~~

Đây là API phát event có key/value; **không tự biến output thành JSON**. Provider/backend cần có layout/encoder hỗ trợ đưa các trường này ra các field thực sự. Không lấy một dòng text như `eventCode=...` rồi khẳng định collector đã có trường `eventCode` nếu chưa parse.

### 9.2. Logback: chọn encoder JSON phù hợp

Với Logback, một lựa chọn phổ biến là encoder JSON chuyên dụng, chẳng hạn từ thư viện `logstash-logback-encoder` khi dự án đã khai báo dependency và chọn phiên bản tương thích. Ví dụ **đoạn cấu hình minh họa, không chạy độc lập khi thiếu dependency**:

~~~xml
<!-- Đoạn thuộc logback.xml; cần module encoder phù hợp. -->
<appender name="JSON_STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
</appender>
~~~

Nội dung chính xác và cách xuất MDC, marker, Throwable hay structured arguments phụ thuộc encoder/version/configuration. **Không tự thay `<pattern>` của text encoder bằng một chuỗi giả JSON** chứa `%msg` không escape, vì message chứa quote/newline có thể phá JSON.

Trong Logback hiện đại còn có các khả năng và encoder khác tùy phiên bản. Chọn một encoder có tài liệu về JSON string escaping, charset, newline separation, Throwable và field names, sau đó chạy test bằng dữ liệu khó như mục 6.

### 9.3. Log4j2: JSON Template Layout

Apache Log4j 2 khuyến nghị dùng **JSON Template Layout** cho structured logging. Cấu hình plugin phụ thuộc module phù hợp, ví dụ `log4j-layout-template-json` cùng các dependency tương thích. Đoạn XML minh họa trong `log4j2.xml`:

~~~xml
<!-- Snippet trong <Appenders>; cần JSON Template Layout module. -->
<Console name="JSON_STDOUT" target="SYSTEM_OUT">
    <JsonTemplateLayout/>
</Console>
~~~

Layout JSON template có các template/resolver để tạo JSON theo schema. Encoder xử lý string quoting/escaping cho trường message và các trường khác theo cấu hình. Nếu muốn field tùy biến, cần kiểm tra resolver, loại dữ liệu, sự hiện diện của field và hợp đồng của collector.

**Không nhầm:** Log4j2 `PatternLayout` dùng các converter như `%msg` cho text. Việc đặt pattern thủ công:

~~~xml
<!-- CẢNH BÁO: không dùng làm JSON encoder production. -->
<PatternLayout pattern='{"message":"%msg"}%n'/>
~~~

không tự bảo đảm JSON hợp lệ nếu message chứa `"`, `\` hoặc raw newline. Dùng JSON layout/template hoặc encoder có escaping đúng thay vì kỳ vọng `%msg` tự escape theo ngữ cảnh JSON.

### 9.4. JUL Formatter tùy biến

JUL có `java.util.logging.Formatter` và `LogRecord`. Nó không có JSON serializer trong Java SE 17 standard library. Bạn có thể dùng serializer đáng tin trong custom Formatter hoặc backend phù hợp. Demo mục 6 chủ yếu chỉ ra cách quote một string, **không thay thế thư viện JSON trong hệ thống thật**.

## 10. JSON escaping và log injection: một số tình huống

### 10.1. Tấn công CRLF giả một bản ghi mới

Payload từ request:

~~~text
guest
ERROR eventCode=SEC-9000 accessGranted=true
~~~

Nếu logger ghi thẳng raw message vào file text theo từng dòng, attacker có thể khiến một message bình thường tạo ra dòng bắt đầu bằng `ERROR` giống như một sự kiện khác. Đây là một kiểu **log forging / log injection**.

Với JSON encoder đúng trong NDJSON, payload được đặt trong một trường string và newline bị escape:

~~~json
{"level":"INFO","username":"guest\nERROR eventCode=SEC-9000 accessGranted=true"}
~~~

Parser thấy một event INFO; đoạn text sau `\n` vẫn là giá trị của `username`, không phải một event độc lập. Tuy nhiên giao diện hiển thị khi giải mã có thể render xuống dòng; UI/alert cần xử lý dữ liệu như **dữ liệu** chứ không được parse lại thành log records bằng regex trên text đã decode.

### 10.2. Payload chứa dấu quote và dấu ngoặc

Payload:

~~~text
x","admin":true,"role":"root
~~~

Trong JSON encoder chuẩn, các dấu quote nội bộ sẽ trở thành `\"`, không tạo field `admin` hoặc `role` trên object. Nhưng nếu encoder bỏ escaping trong một “raw JSON mode” hoặc app tự ghép chuỗi, cấu trúc có thể bị phá.

**Quy tắc:** untrusted string luôn là **string value**; đừng dùng nó làm một đoạn JSON có cú pháp được tin tưởng. Nếu cần nhận dữ liệu JSON từ client, parse và validate theo schema trước khi đưa phần được phép vào log.

### 10.3. Payload quá dài

Một request header dài hàng megabyte dù đã escape đúng vẫn có thể tạo log event quá lớn, gây tăng CPU/memory, đầy hàng đợi, cắt record hoặc chi phí ingest cao.

Cần giới hạn **độ dài nguồn**, số field, số lượng event và các trường được phép log. Khi cắt giá trị, cần tránh làm mất dấu hiệu điều tra; có thể giữ chiều dài gốc, mã lỗi validation và một phần mẫu an toàn đã được giới hạn.

### 10.4. Dữ liệu nhạy cảm vẫn lộ dù JSON hợp lệ

Một log:

~~~json
{"level":"INFO","accessToken":"secret-value"}
~~~

có cú pháp JSON đúng, nhưng vẫn là cách ghi log không an toàn. Escape không che token. Không coi việc bọc dữ liệu vào JSON string là redaction; phải giảm dữ liệu từ nguồn, phân quyền, retention và giám sát truy cập.

## 11. Unicode, surrogate pair, charset và tính tương thích

### 11.1. JSON Unicode và UTF-8

RFC 8259 quy định JSON text trao đổi giữa các hệ thống không thuộc cùng một hệ sinh thái khép kín phải dùng **UTF-8**. Encoder nên khai báo và xuất byte theo charset phù hợp, thường là UTF-8, để chữ tiếng Việt và các ký tự ngoài ASCII không bị mojibake.

Ví dụ JSON text UTF-8:

~~~json
{"message":"Đơn hàng đã hoàn tất","emoji":"🚀"}
~~~

Cũng có thể xuất theo kiểu escape các ký tự không ASCII:

~~~json
{"message":"\u0110\u01a1n h\u00e0ng \u0111\u00e3 ho\u00e0n t\u1ea5t","emoji":"\ud83d\ude80"}
~~~

Hai cách thể hiện được thiết kế để giải mã thành cùng giá trị chuỗi. Bản thứ hai nhiều byte hơn ở nhiều trường hợp, nhưng có thể hữu ích cho output ASCII-only hoặc test xác định.

### 11.2. Surrogate không ghép cặp

Java `String` có thể chứa `char` high surrogate hoặc low surrogate đứng một mình. Chúng không tạo thành Unicode scalar value hợp lệ. RFC 8259 cảnh báo về cách xử lý **unpaired surrogate** giữa các triển khai. Nếu tự viết serializer, cần chính sách rõ ràng: **reject**, thay thế bằng ký tự thay thế U+FFFD với ghi nhận lỗi phù hợp, hoặc dựa vào encoder đã được kiểm chứng.

Không âm thầm cắt UTF-16 string tại giới hạn ký tự mà có thể cắt giữa hai code units của một emoji. Nếu log pipeline giới hạn byte hoặc code points, cần thực hiện giới hạn theo chính sách mà vẫn giữ output JSON hợp lệ.

### 11.3. Dấu slash và ký tự dùng khi nhúng JSON trong HTML

`/` không bắt buộc escape trong JSON. Tuy nhiên, nếu bạn **nhúng JSON trực tiếp vào HTML hoặc JavaScript source**, có thêm các quy tắc theo ngữ cảnh HTML/JavaScript (ví dụ `<`, `&`, chuỗi đóng script, U+2028/U+2029 trong một số môi trường). **JSON escaping đơn thuần không phải HTML escaping hay JavaScript-source escaping**.

Trong log file NDJSON thuần túy, không cần tự escape dấu slash chỉ để “đúng JSON”. Nếu xuất lên giao diện HTML, hãy escape ở **ngữ cảnh render HTML** hoặc dùng API DOM an toàn của UI, không tái sử dụng raw JSON text như HTML markup.

## 12. Kiểm thử JSON escaping đúng cách

### 12.1. Test nên có

| Case | Dữ liệu đầu vào | Kết quả cần có |
| --- | --- | --- |
| Quote | `a"b` | `a\"b` bên trong JSON string |
| Backslash | `C:\logs` | `C:\\logs` trong JSON text |
| LF | Chuỗi có newline thật | `\n` trong JSON text; không phát sinh dòng vật lý |
| CRLF | `\r\n` thật | `\r\n` được encode |
| Tab | Ký tự tab thật | `\t` |
| NUL/control | U+0000–U+001F | Escape ngắn hoặc `\u00XX` |
| Unicode BMP | `é` hoặc `ế` | Raw UTF-8 hoặc Unicode escape hợp lệ |
| Unicode ngoài BMP | `🚀` | Raw UTF-8 hoặc cặp `\ud83d\ude80` |
| Unpaired surrogate | Chỉ high/low surrogate | Theo chính sách reject/replace được kiểm thử |
| Injection quote | `x","admin":true` | Toàn bộ vẫn nằm trong một string value |
| Text giống JSON | `{"admin":true}` | Không tự biến thành nested object |
| Null Java value | `null` | Field null, omit hoặc reject theo schema, không NPE vô tình |
| Number/boolean | `2`, `false` | Giữ kiểu phù hợp, không quote bừa |
| Non-finite number | `NaN`, `Infinity` | Không xuất token JSON number sai chuẩn |
| Exception message | Có quote/newline/backslash | Một event hợp lệ, Throwable theo schema |
| Very long input | Nhiều KB/MB | Giới hạn an toàn, không bị truncate thành JSON sai |

**Đừng chỉ so sánh chuỗi output bằng mắt.** Một bài test mạnh nên:

1. Phát ra JSON log qua backend/encoder thật.
2. Dùng một **JSON parser độc lập** để parse từng dòng.
3. Kiểm tra số dòng/event, field names, field types và giá trị **sau khi decode**.
4. So sánh giá trị đã parse với chuỗi Java ban đầu (bao gồm newline/tab/Unicode).
5. Chạy cả trường hợp attacker-controlled input, error message và stack trace.
6. Kiểm tra collector thật sự lưu một event, không bị cắt hoặc nhân đôi.

### 12.2. Với NDJSON, validate từng dòng

Giả sử file `events.jsonl` chứa mỗi event một JSON object độc lập. Khi có `jq`:

~~~bash
jq -c . events.jsonl
~~~

Lệnh sẽ parse lần lượt các JSON text trong file và phát ra bản compact nếu dữ liệu hợp lệ. Với một file JSON array/JSON document duy nhất, cách xử lý khác; **NDJSON không phải một array**.

Nếu có Python 3, có thể kiểm tra từng dòng:

~~~python
import json
from pathlib import Path

lines = Path("events.jsonl").read_text(encoding="utf-8").splitlines()
parsed = [json.loads(line) for line in lines]
print("events=", len(parsed))
~~~

Đây là đoạn mã minh họa công cụ kiểm thử, **không phải thành phần bắt buộc của Java 17**. Không dùng `python -m json.tool events.jsonl` như phép kiểm chuẩn cho toàn bộ NDJSON nếu công cụ mong một JSON document duy nhất.

### 12.3. Sự khác nhau giữa “JSON hợp lệ” và “log đúng nghiệp vụ”

Một log có thể parse JSON thành công nhưng vẫn sai:

- `level` bị biến thành field do attacker kiểm soát.
- `eventCode` được ghép từ request ID, khiến cardinality tăng vô hạn.
- `durationMs` là string thay vì number.
- Stack trace bị cắt, không còn cause gốc.
- Request ID trong MDC từ request trước bị giữ lại trên thread pool.
- Log đã được ghi nhưng rơi trong hàng đợi/collector.

Do đó cần kiểm tra **cú pháp, schema, dữ liệu, nghĩa của event và đường thu thập**. Escape JSON chỉ giải quyết phần cú pháp, dù đây là một phần bắt buộc.

## 13. Hiệu năng và vận hành

Một JSON encoder thông thường phải tạo các field, encode chuỗi, escape các ký tự đặc biệt và ghi byte ra output. Với log volume lớn, tổng chi phí có thể ảnh hưởng CPU/GC và disk/network I/O.

Các yếu tố đáng quan tâm:

- **Parameterized logging:** dùng template và tham số thay vì nối message tùy ý; nhớ Java vẫn đánh giá biểu thức đối số trước khi gọi logger.
- **Structured field:** giữ message text ngắn, đặt field có tên và kiểu rõ ràng để tránh parse regex tốn kém.
- **Giới hạn size:** giới hạn số field, độ dài message, stack trace và event bytes theo chính sách; cắt sau khi encode không khéo có thể phá JSON.
- **UTF-8:** ghi nhất quán charset từ JVM/encoder tới collector.
- **NDJSON:** một JSON object trên một dòng, newline trong string phải escape.
- **Async logging:** có thể giảm blocking trên thread request nhưng phải theo dõi queue, drop, flush/shutdown và durability.
- **Validation:** encoder là một phần pipeline; nếu logging data không hợp lệ, cần cách xử lý rõ mà không gây vòng lặp log lỗi trong chính formatter.
- **Observability:** đo bytes/s, events/s, queue depth, dropped/truncated events, CPU, allocations/GC, p95/p99 latency và số lỗi parse JSON ở collector.

Không cần tự viết hàm escape “tối ưu” khi đã có encoder được kiểm chứng. Sai một ký tự trong serializer có thể phá ingest trên hàng triệu bản ghi; độ an toàn và khả năng duy trì quan trọng hơn một benchmark nhỏ của StringBuilder.

## 14. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghép user input trực tiếp vào `{"message":"..."}` | Injection hoặc JSON hỏng | Serializer/structured encoder cho string value |
| Chỉ escape `"` mà quên `\` | Đường dẫn `C:\logs` làm JSON sai | Escape cả quote, backslash và control |
| Ghi raw newline trong string JSON | NDJSON bị tách dòng, JSON không hợp lệ | Escape newline thành `\n` |
| Tự thay `\n` rồi đưa tiếp vào JSON encoder | Double escaping, giá trị đã parse sai | Chỉ serialize một lần ở boundary cuối |
| Dùng `Map.toString()` làm JSON | Không bảo đảm JSON hợp lệ | Dùng JSON serializer |
| Dùng `PatternLayout` tự ghép JSON với `%msg` | Message có thể phá cấu trúc | JSON Template Layout/encoder phù hợp |
| Nghĩ SLF4J `addKeyValue` tự cho ra JSON | Output có thể chỉ là text | Chọn backend/encoder hỗ trợ |
| Bỏ sót control U+0000–U+001F | Parser từ chối log | Thực thi đầy đủ JSON string rules |
| Tự thay `'` bằng `\'` | `\'` không phải escape JSON hợp lệ | JSON dùng `\"` cho double quote; apostrophe không cần escape |
| Biến mọi Unicode thành `?` | Mất dữ liệu tiếng Việt/emoji | Ghi UTF-8 hoặc Unicode escape đúng |
| Cắt giữa surrogate pair | Chuỗi Unicode lỗi, parser khác nhau | Cắt theo ranh giới hợp lệ/để encoder xử lý |
| Quote cả số/boolean | Schema sai kiểu | Serialize typed values |
| Ghi raw `NaN` hay `Infinity` | Không phải JSON chuẩn RFC 8259 | Reject/convert theo schema |
| Escape đúng nhưng vẫn log token | Rò rỉ bí mật | Không phát/mask trường nhạy cảm |
| Parser cho phép duplicate keys | Có thể diễn giải level/metadata sai | Không ghép raw JSON từ input; schema kiểm tra key |
| Để raw stack trace đa dòng ngoài object | Collector tách event, mất ngữ cảnh | Escape trong field hoặc structured throwable |
| Formatter custom ném lỗi trên null | Mất log và rối pipeline | Xử lý null/invalid data có chủ đích |
| Quá nhiều field/string lớn | Tốn CPU, disk, queue, ingest | Giới hạn và đo throughput |
| Tin JSON hợp lệ đồng nghĩa log đã tới collector | Có thể bị drop/rotate/truncate | Theo dõi pipeline end-to-end |

## 15. Checklist triển khai JSON logging

1. **Xác định định dạng đích:** một JSON document hay NDJSON một-event-một-dòng? Cấu hình collector tương ứng.
2. **Dùng encoder đáng tin:** Logback/Log4j2/JUL hoặc thư viện JSON được bảo trì; không nối JSON bằng chuỗi.
3. **Giữ field typed:** timestamp, level, eventCode, requestId, durationMs, error type; không tự quote mọi giá trị.
4. **Escape string đầy đủ:** quote, backslash, control U+0000–U+001F; hỗ trợ Unicode/cặp surrogate đúng.
5. **Không double escape:** đưa string gốc vào encoder; encode một lần ở bước serialize.
6. **Giữ Throwable khi cần:** truyền exception vào logging API, encode stack/cause/suppressed phù hợp.
7. **Giới hạn dữ liệu:** tránh log secret/PII, payload khổng lồ hoặc đối tượng quá lớn.
8. **Truyền context đúng:** requestId/traceId/MDC không tự qua mọi executor; dọn context ở cuối scope.
9. **Kiểm tra parser:** parse từng dòng với JSON parser độc lập và so sánh giá trị sau decode.
10. **Kiểm tra ingest:** collector, index, alert, retention và display UI có còn giữ các trường đúng nghĩa không.
11. **Kiểm tra hiệu năng:** load test với quote/newline/Unicode/exception dài, đo log bytes/s, CPU, GC, queue.
12. **Bảo mật:** phân quyền log, chống log forging, bảo vệ archive/backup và tránh lộ stack trace nội bộ ở response.
13. **Kiểm tra tương thích:** nâng version encoder/framework phải có test schema và escaping, đặc biệt với trường Throwable.
14. **Theo dõi sự cố:** cảnh báo số bản ghi JSON không parse được, event bị cắt, lỗi encoding và log bị drop.

## 16. Bài tập tự kiểm tra

1. **RFC 8259:** liệt kê các ký tự phải escape trong JSON string. Dấu slash có bắt buộc dùng `\/` không? Apostrophe `'` có phải escape không?
2. **Phân biệt các lớp cú pháp:** giải thích khác nhau giữa Java literal `"a\nb"`, giá trị runtime và JSON text biểu diễn cùng giá trị.
3. **Chạy Java 17:** tạo `JsonEscapeLoggingDemo.java`, chạy hai lệnh `javac`/`java` và đối chiếu bốn dòng stdout. Tại sao message có newline nhưng JSON log không bị chia?
4. **JSON injection:** một người dùng gửi username `x","role":"admin`. Nếu code ghép vào chuỗi JSON thủ công thì nguy cơ gì? Với encoder chuẩn, giá trị ấy còn tạo field `role` được không?
5. **Backslash:** cho đường dẫn Windows `C:\temp\logs`; viết JSON string hợp lệ chứa đường dẫn đó. Vì sao `\t` tạo nghĩa khác nếu không được escape đúng?
6. **Unicode:** phân biệt JSON text chứa “café🚀” trực tiếp với `"caf\u00e9\ud83d\ude80"`. Cả hai có thể cùng giải mã thành một Java String không?
7. **Surrogate:** nếu một chuỗi Java chỉ chứa high surrogate không có low surrogate, vì sao nên reject/replace có chủ đích thay vì âm thầm xuất?
8. **Double escaping:** giải thích vì sao pre-escape `\n` rồi đưa vào Jackson có thể khiến parser nhận lại hai ký tự `\` và `n`.
9. **Schema:** một event có `attempt=2` và `success=false`. Khi serialize bằng Map/object, làm sao giữ đúng number và boolean thay vì string?
10. **Throwable:** nếu exception message chứa LF và stack trace nhiều dòng, có thể lưu chúng trong một JSON Lines record bằng cách nào?
11. **Structured logging:** SLF4J 2.x `addKeyValue` đã đủ để collector thấy field JSON độc lập chưa? Điều kiện nào ở backend vẫn cần?
12. **Validation:** xây một bộ test với quote, backslash, tab, CRLF, NUL, emoji, input rất dài và dữ liệu nhạy cảm. Nêu assertion cho parser, số dòng, schema và privacy.

## 17. Tài liệu tham khảo chính thức

- RFC 8259 — JSON Data Interchange Format, mục 7 và 8: https://www.rfc-editor.org/rfc/rfc8259.html
- OWASP — Logging Cheat Sheet, log injection và dữ liệu cần loại: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Apache Log4j 2 — Layouts/structured logging: https://logging.apache.org/log4j/2.x/manual/layouts.html
- Apache Log4j 2 — JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- SLF4J Manual — Fluent logging API: https://slf4j.org/manual.html
- Java SE 17 — `java.util.logging.Formatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html

**Ghi nhớ:** **Escape JSON là điều kiện để string trong log JSON đúng cú pháp**, đặc biệt với `"`, `\` và các ký tự điều khiển U+0000–U+001F. Trong Java logging, hãy dùng encoder/serializer đáng tin thay vì ghép JSON bằng chuỗi; giữ **một event trên một dòng** nếu pipeline dùng NDJSON; không double escape; xử lý Unicode, Throwable và field types đúng schema; đồng thời nhớ rằng **JSON escaping không thay thế kiểm soát dữ liệu nhạy cảm, chống quá tải và giám sát quá trình thu thập log**.