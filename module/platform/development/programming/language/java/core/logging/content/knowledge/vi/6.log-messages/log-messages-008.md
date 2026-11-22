# Message nhiều dòng trong Java Logging

Một **log message nhiều dòng (multiline log message)** là thông điệp chứa ký tự xuống dòng, khiến **một sự kiện logging** có thể hiển thị thành **nhiều dòng văn bản** trên console hoặc trong file. Kiểu thông điệp này hữu ích khi cần trình bày nhiều chi tiết liên quan cùng một thao tác, nhưng cũng có thể làm khó việc tìm kiếm, phân tích tự động, liên kết sự kiện và bảo mật log.

Điều quan trọng nhất là phân biệt **một log event** với **một dòng vật lý** trong đầu ra. Trong Java, một lời gọi `logger.info(message)` thường tạo **một record/event**, ngay cả khi `message` chứa nhiều dấu xuống dòng. Tùy formatter, handler, backend và công cụ thu thập, một event ấy có thể chiếm nhiều dòng trong console/file hoặc được mã hóa thành một bản ghi có cấu trúc.

## 1. Một message nhiều dòng trông như thế nào?

Giả sử ứng dụng phát thông điệp:

```text
orderId=ORD-17 status=FAILED
stage=validate
reason=missing-address
```

Thông điệp trên có **ba dòng nội dung**, nhưng có thể được phát bởi **một** lời gọi logger. Nếu formatter đặt metadata ở đầu event, kết quả hiển thị kiểu text thường là:

```text
2026-11-09T08:20:10Z WARN OrderService - orderId=ORD-17 status=FAILED
stage=validate
reason=missing-address
```

Đây là dữ liệu **minh họa**, không phải kết quả chạy ví dụ Java phía dưới. Chỉ dòng đầu có timestamp, level và tên logger; hai dòng tiếp theo là phần nối dài của cùng message. Người đọc có thể hiểu, nhưng công cụ thu thập **mỗi dòng là một record** có thể nhầm hai dòng sau thành sự kiện độc lập.

### Phân biệt event, message và dòng hiển thị

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Log event / LogRecord** | Sự kiện do lời gọi logging phát ra, mang level, logger name, thời điểm, message, exception, ngữ cảnh... |
| **Log message** | Nội dung thông điệp của event; có thể không có, có một hoặc nhiều ký tự xuống dòng |
| **Dòng vật lý** | Đơn vị văn bản bị ngắt bởi ký tự xuống dòng trong đầu ra text |
| **Log entry trong hệ thống thu thập** | Đơn vị mà collector/backend đã phân tích và lưu; có thể khớp hoặc không khớp với event gốc nếu parser cấu hình sai |

Không có quy tắc chung rằng *một lời gọi logger bằng một dòng log trong file*. Khi formatter thêm một ký tự newline ở cuối record, message chứa hai newline nội bộ có thể tạo ra ba hoặc nhiều dòng vật lý.

## 2. Các ký tự xuống dòng thường gặp

Java dùng các escape sequence trong string literal:

| Biểu diễn trong source Java | Giá trị thực tế | Ý nghĩa |
| --- | --- | --- |
| `"\n"` | Ký tự LF, U+000A | Xuống dòng theo chuẩn LF |
| `"\r"` | Ký tự CR, U+000D | Carriage return; có thể thay đổi vị trí con trỏ trong một số môi trường |
| `"\r\n"` | CR rồi LF | Cặp kết thúc dòng thường gặp trong văn bản Windows |
| `System.lineSeparator()` | Chuỗi ngắt dòng của môi trường hiện tại | Phụ thuộc nền tảng; có thể là LF hoặc CRLF |
| `"\\n"` | Hai ký tự nhìn thấy: backslash và chữ `n` | Cách *hiển thị* một newline đã được escape, không phải ký tự LF |

Ví dụ:

```java
// Đây là fragment minh họa trong một phương thức Java.
String message = "first line\nsecond line";
LOGGER.info(message);
```

Nếu hệ thống logging viết message ra text nguyên dạng, nội dung sẽ hiển thị thành hai dòng. Ngược lại:

```java
String message = "first line\\nsecond line";
LOGGER.info(message);
```

Thông điệp thứ hai chứa các ký tự `\` và `n`, nên thông thường sẽ hiển thị **một dòng**, có chuỗi `\n` ở giữa. Hai đoạn trên là fragment, yêu cầu logger `LOGGER` đã được khai báo trong lớp.

**Lưu ý về tính di động:** Khi tự ghép nội dung cho cấu trúc trao đổi có quy định LF, hãy dùng `"\n"` theo giao thức. Khi chỉ muốn xuống dòng phù hợp nền tảng hiện tại, `System.lineSeparator()` là một lựa chọn. Không mặc định rằng mọi file và hệ thống thu thập log chạy cùng hệ điều hành.

## 3. Tạo message nhiều dòng bằng Java

### Cách 1: nối các chuỗi

```java
String message = "operation=import\n"
        + "fileId=file-42\n"
        + "status=FAILED";
LOGGER.warning(message);
```

Giải pháp dễ hiểu với số dòng ít và cố định. Tuy nhiên, nếu liên tục ghép chuỗi từ input lớn hoặc tính toán tốn tài nguyên, cần cân nhắc độ dài log và mức log đang được bật.

### Cách 2: `String.join`

```java
String message = String.join("\n",
        "operation=import",
        "fileId=file-42",
        "status=FAILED");
LOGGER.warning(message);
```

`String.join` đặc biệt phù hợp khi muốn ghép một tập các dòng có cấu trúc đồng nhất. Kết quả **không tự thêm newline ở cuối**, vì separator chỉ nằm giữa các phần tử. Có thể dùng `System.lineSeparator()` thay `"\n"` khi phù hợp mục đích.

### Cách 3: Java text block (Java 15+, dùng được ở Java 17)

```java
String message = """
        operation=import
        fileId=file-42
        status=FAILED
        """.stripTrailing();

LOGGER.warning(message);
```

Text block `"""` giúp viết nội dung nhiều dòng dài dễ đọc hơn so với nối chuỗi. Java xử lý phần thụt lề chung và chuẩn hóa dấu ngắt dòng trong text block; text block ở ví dụ thường có newline cuối trước dấu đóng, nên `.stripTrailing()` loại bỏ khoảng trắng cuối, bao gồm newline đó. Nếu khoảng trắng cuối là dữ liệu có ý nghĩa, **không dùng `stripTrailing()` một cách tùy tiện**.

Cú pháp text block yêu cầu phiên bản Java hỗ trợ (đã chính thức từ Java 15). Các fragment trên giả định đã có `LOGGER` thuộc `java.util.logging.Logger` và không phải ba chương trình `main` độc lập.

### Cách 4: tạo chuỗi từ danh sách

```java
List<String> issues = List.of(
        "missing address",
        "invalid postal code",
        "unsupported region");
String message = "Validation errors:\n- "
        + String.join("\n- ", issues);
LOGGER.warning(message);
```

Đoạn này yêu cầu `import java.util.List;`. Dùng một record cho một bản tóm tắt có các dòng liên quan có thể giúp người đọc nhìn thấy toàn cảnh. Khi danh sách có thể có hàng nghìn phần tử, nên đặt giới hạn số phần tử và độ dài message để tránh làm đầy log.

## 4. Ví dụ Java 17 độc lập: một record, nhiều dòng và cách escape

Chương trình dưới đây chỉ dùng JDK. Nó minh họa ba trường hợp:

1. **Message nhiều dòng gốc:** xuống dòng trong message được giữ nguyên.
2. **Message một dòng đã escape:** biến các ký tự CR/LF thành chữ `\r`/`\n` để dễ thu thập theo từng dòng.
3. **Dữ liệu không tin cậy:** ngăn nội dung đầu vào tự tạo ra một dòng giả giống thông báo `SEVERE`.

Lưu file **`MultilineMessageDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultilineMessageDemo {
    private static final Logger LOGGER =
            Logger.getLogger(MultilineMessageDemo.class.getName());

    private static String escapeLineBreaks(String text) {
        return text.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOGGER.addHandler(console);

        try {
            String details = String.join("\n",
                    "requestId=req-7 status=FAILED",
                    "stage=validate",
                    "reason=missing-field");

            LOGGER.info("multi:\n" + details);
            LOGGER.info("single=" + escapeLineBreaks(details));

            String untrusted = "ok\r\nSEVERE | forged";
            LOGGER.info("userInput=" + escapeLineBreaks(untrusted));
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 MultilineMessageDemo.java
java MultilineMessageDemo
```

**Kết quả chính xác trên `stderr`:**

```text
INFO | multi:
requestId=req-7 status=FAILED
stage=validate
reason=missing-field
INFO | single=requestId=req-7 status=FAILED\nstage=validate\nreason=missing-field
INFO | userInput=ok\r\nSEVERE | forged
```

Chương trình không chủ động ghi ra `stdout`. `ConsoleHandler` của JUL ghi ra **stderr**, còn `System.lineSeparator()` sử dụng ngắt dòng theo hệ điều hành, nên bytes kết thúc mỗi record có thể là LF hoặc CRLF. Các dòng văn bản hiển thị ở trên vẫn có cùng nội dung.

**Cách phân tích:**

- Chương trình gọi `LOGGER.info` **ba lần**, tạo ba `LogRecord`. Tuy nhiên, đầu ra của handler có **sáu dòng vật lý**: bốn dòng của event thứ nhất và một dòng cho mỗi event còn lại.
- `multi:\n` được Java hiểu là nhãn `multi:` rồi một ký tự newline. `String.join("\n", ...)` tạo thêm hai newline nội bộ.
- `escapeLineBreaks` thay backslash gốc trước, sau đó thay CR và LF bằng cách biểu diễn nhìn thấy được `\r` và `\n`. Thứ tự này tránh nhập nhằng khi input vốn đã chứa backslash.
- Event thứ ba có đầu vào chứa `CRLF` và một dòng giả trông giống log `SEVERE`. Hàm escape giữ toàn bộ nội dung trong **một dòng**, nên không tạo một bản ghi mức `SEVERE` giả ở console.
- `LOGGER.setUseParentHandlers(false)` và formatter tự định nghĩa giúp output có thể kiểm chứng, không thêm dòng do root logger hay timestamp. Trong ứng dụng thực, cần dùng formatter có metadata đầy đủ.

**Giới hạn của demo:** Hàm `escapeLineBreaks` chỉ xử lý backslash và CR/LF. Trong hệ thống production, còn cần cân nhắc tab, ký tự điều khiển, escape ANSI, các dấu phân cách Unicode, độ dài message, bộ ký tự và phương pháp mã hóa chuẩn của hệ thống thu thập. Chọn formatter/encoder có xử lý dữ liệu đầu vào nhất quán, thay vì xem hàm nhỏ này là một bộ lọc bảo mật hoàn chỉnh.

## 5. Một sự kiện nhiều dòng khác gì nhiều lời gọi logger?

Hai cách sau không tương đương.

**Cách A – một lời gọi, một event chứa nhiều dòng:**

```java
LOGGER.warning("requestId=req-7\n"
        + "stage=validate\n"
        + "reason=missing-field");
```

**Cách B – nhiều lời gọi, nhiều event:**

```java
LOGGER.warning("requestId=req-7");
LOGGER.warning("stage=validate");
LOGGER.warning("reason=missing-field");
```

Cách A thông thường tạo **một record** có một level, thời điểm, logger name, exception/context và message nhiều dòng. Cách B tạo **ba record**, mỗi record có metadata/thời điểm riêng và có thể bị xen kẽ với event từ các thread khác. Nếu hệ thống có filter theo mức, rate limit hoặc sampling, các event riêng biệt còn có thể đi tới đích khác nhau.

Bởi vậy, **tách một message nhiều dòng thành nhiều lời gọi log** chỉ để console dễ nhìn thường làm mất tính nguyên tử ở mức sự kiện và khó gom lại theo ngữ cảnh. Nếu các dòng là **những sự kiện nghiệp vụ thực sự độc lập**, nhiều lời gọi là hợp lý; nếu chỉ là các chi tiết của cùng một sự kiện, nên giữ chúng trong một event (tốt nhất là các trường có cấu trúc khi hệ thống hỗ trợ).

Trong môi trường nhiều luồng, không được giả định ba lần gọi log liên tiếp từ một thread sẽ luôn nằm cạnh nhau trong file tổng hợp. Cần có correlation ID và cơ chế thu thập phù hợp.

## 6. Multiline message và stack trace của exception

**Stack trace** là trường hợp phổ biến của dữ liệu log nhiều dòng. Một exception có thể đi qua nhiều lớp; thông tin hữu ích nằm ở message, các stack frame và chuỗi `Caused by`.

Với JUL, tại ranh giới xử lý lỗi có thể viết:

```java
try {
    process();
} catch (IllegalArgumentException e) {
    LOGGER.log(Level.SEVERE,
            "requestId=req-7 operation=process outcome=failed", e);
}
```

Đây là **fragment**: `process()` và `LOGGER` là thành phần do ứng dụng cung cấp. `LOGGER.log(Level.SEVERE, String, Throwable)` truyền cả đối tượng exception vào `LogRecord`; một formatter hỗ trợ throwable, chẳng hạn `SimpleFormatter` mặc định trong JUL, có thể ghi stack trace dưới nhiều dòng. **Formatter tùy chỉnh của ví dụ ở mục 4 chỉ ghi message và không ghi throwable**, nên không được dùng nguyên trạng nếu muốn giữ stack trace.

Ví dụ hình thức (line number thay đổi theo source/build):

```text
SEVERE requestId=req-7 operation=process outcome=failed
java.lang.IllegalArgumentException: invalid quantity
    at com.example.OrderService.validate(OrderService.java:42)
    at com.example.OrderService.process(OrderService.java:19)
Caused by: java.lang.NumberFormatException: For input string: "x"
    ...
```

**Không gọi `e.printStackTrace()` như cách ghi log chính trong ứng dụng:** lời gọi đó thường ghi ra `System.err` và bỏ qua level, logger name, correlation ID cũng như pipeline logging đang cấu hình. Hãy truyền `Throwable` cho API logging thích hợp và để backend/formatter xử lý.

Với SLF4J trong ứng dụng đã có provider/backend:

```java
// Fragment: log là org.slf4j.Logger; requestId và e đã có.
log.error("requestId={} operation=process failed", requestId, e);
```

Backend sẽ xử lý throwable theo cấu hình. **Đừng lấy `e.getMessage()` làm dữ liệu duy nhất** vì cách đó đánh mất stack trace, các frame và cause. Để logger có thể hiển thị toàn bộ exception, encoder/formatter phải hỗ trợ trường throwable, không chỉ trường message.

Điểm mấu chốt: stack trace nhiều dòng là dữ liệu **có ích và thường không nên bị xóa sạch**. Nếu hệ thống lưu log cần một record trên một dòng, hãy đưa exception vào trường có cấu trúc và để encoder escape newline trong chuỗi, hoặc cấu hình collector gom multiline đúng cách.

## 7. Khi nào nên giữ nhiều dòng, khi nào nên dùng một dòng?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Debug cục bộ, người đọc trực tiếp trên console | Multiline có cấu trúc rõ | Dễ nhìn chuỗi bước và nội dung chi tiết |
| Batch job cần in tóm tắt các bước | Một event chứa nhiều dòng hoặc dữ liệu có cấu trúc | Các chi tiết cùng thuộc một lần chạy |
| Hệ thống thu thập log theo từng dòng stdout/stderr | **Một event trên một dòng** hoặc multiline parser được cấu hình đúng | Tránh tách một event thành nhiều record thiếu metadata |
| Log trung tâm cần lọc theo `requestId`, `errorCode`, `stage` | Structured logging, thường dạng JSON một dòng | Mỗi trường có tên, dễ tìm kiếm/truy vấn |
| Exception / stack trace dài | Giữ throwable, dùng encoder có cấu trúc hoặc multiline parser | Không đánh mất chứng cứ lỗi |
| Input không tin cậy như header, query parameter, tên người dùng | Escape hoặc mã hóa khi đưa vào log | Giảm nguy cơ giả mạo dòng log và nhiễu parser |
| Danh sách nhiều nghìn phần tử | Tóm tắt + số lượng + giới hạn phần tử được ghi | Tránh log quá lớn, rò rỉ dữ liệu và tốn I/O |

Không phải mọi log nhiều dòng đều sai. Lựa chọn phụ thuộc việc log được đọc bởi **con người** hay **hệ thống tự động**, yêu cầu truy vấn, độ dài cho phép, cách lưu trữ và mức độ tin cậy.

## 8. Thu thập multiline trong console, file và hệ thống tập trung

Với logging dạng text, formatter thường thêm một newline ở cuối bản ghi. Nếu message hoặc exception cũng có newline, một event Java có thể trở thành nhiều dòng đầu ra.

**Hệ quả khi collector đọc từng dòng:**

1. Dòng đầu có timestamp, level, logger và correlation ID.
2. Dòng tiếp theo của cùng message có thể thiếu các trường đó.
3. Parser có thể coi dòng tiếp là một event độc lập, báo sai level hoặc không nối được với request.
4. Số lượng “log entries” được thống kê tăng dù số lời gọi logger thực tế không đổi.

Có hai hướng xử lý thường gặp:

**Hướng A – định dạng mỗi event thành một record có cấu trúc trên một dòng.**

Ví dụ minh họa:

```json
{"timestamp":"2026-11-09T08:20:10Z","level":"WARN","logger":"OrderService","requestId":"req-7","message":"stage=validate\nreason=missing-field"}
```

Đây là **một dòng JSON hợp lệ**: nội dung message có dấu xuống dòng ở giá trị đã được escape bằng `\n`. JSON serializer đúng chuẩn sẽ escape các ký tự điều khiển trong chuỗi; đừng tự nối JSON bằng những chuỗi đầu vào không tin cậy. Để đạt mỗi event một dòng, bộ encoder phải **không pretty-print** toàn bộ object thành nhiều dòng.

Với Logback hoặc Log4j 2, khả năng và cú pháp cấu hình structured encoder/layout phụ thuộc phiên bản, dependency và backend cụ thể. Không thể chỉ thêm `%n` vào pattern là mọi newline trong message đều biến thành `\n`: token kết thúc record thường chỉ thêm newline vào cuối event.

**Hướng B – giữ text multiline nhưng cấu hình bộ thu thập để ghép đúng một event.**

Collector có thể dựa vào timestamp/level ở dòng bắt đầu, trạng thái parser hoặc quy tắc bắt đầu/kết thúc. Khi làm vậy, cần thử ít nhất: message chứa newline nội bộ; stack trace có `Caused by`; log xen kẽ từ nhiều thread; sự kiện không có timestamp ở một dòng; và record dài vượt giới hạn của collector. Cần biết điểm ghép diễn ra ở agent, pipeline hay backend để không tạo ra record hỏng.

Không có một regex multiline chung phù hợp mọi định dạng log. Quy tắc quá rộng có thể nối nhầm hai sự kiện thật, nhất là khi thông điệp chứa text trông giống timestamp hoặc level.

## 9. Bảo mật: CRLF injection và giả mạo dòng log

Một message nhiều dòng do **ứng dụng chủ động định dạng** khác với dấu xuống dòng đến từ **input bên ngoài**. Nếu đầu vào không tin cậy được ghi nguyên xi, kẻ tấn công có thể thêm `\r`/`\n` và những từ như `ERROR`, `SEVERE`, tên logger hoặc timestamp để tạo dòng **trông giống sự kiện khác**.

Ví dụ dữ liệu đầu vào giả định:

```text
guest
2026-11-09T08:20:11Z SEVERE AuthService - access granted
```

Nếu ghi trực tiếp bằng `LOGGER.info("username=" + username)`, log text có thể hiện thành hai dòng, trong đó dòng sau giả dạng một sự kiện độc lập. Việc này được gọi là **log forging / log injection**. Không phải mọi newline do người dùng nhập đều là tấn công, nhưng hệ thống cần phân biệt dữ liệu với cấu trúc log do ứng dụng tạo.

Cách giảm rủi ro:

- Ưu tiên trường có cấu trúc và encoder chuẩn có escaping; giữ dữ liệu người dùng trong **giá trị của trường**, không cho nó điều khiển định dạng record.
- Với hệ thống log text một dòng, escape CR/LF và các ký tự điều khiển có liên quan trước khi phát ra đích.
- Giới hạn độ dài input được log và bỏ/che dữ liệu nhạy cảm. **Không log mật khẩu, token, cookie phiên, khóa bí mật, dữ liệu cá nhân nhạy cảm**.
- Tại bước phân tích, tránh tin rằng mọi dòng bắt đầu bằng chữ `ERROR` hoặc timestamp đều là một event thật khi log chưa được xử lý escaping đúng.
- Nếu log thật sự cần nội dung nhiều dòng do ứng dụng tạo, truyền riêng correlation ID và dùng định dạng/pipeline có khả năng giữ nguyên ranh giới event.

Escaping ở ví dụ Java giúp minh họa nguyên tắc, nhưng **không đủ để tuyên bố an toàn cho mọi dữ liệu đầu vào**. Với format JSON, dùng serializer. Với log text, áp dụng chính sách escaping và giới hạn dữ liệu của chính hệ thống.

## 10. Định dạng log nhiều dòng dễ đọc mà vẫn có ngữ cảnh

Nếu mục tiêu là hiển thị multiline trực tiếp cho người vận hành, nên dùng một phần **header ngắn** nêu loại thao tác/correlation ID, tiếp theo là danh sách các dòng được thụt lề, giữ cùng tên trường:

```text
INFO requestId=req-7 operation=validate result=FAILED
  errorCount=2
  - missing-address
  - invalid-phone
```

Đây vẫn là nhiều dòng vật lý của một event, nhưng người đọc dễ nhận ra phần đầu và phần tiếp nối. Khi chạy qua collector chỉ thu từng dòng, cần cấu hình ghép hoặc chuyển sang structured logging.

Một lựa chọn khác là chỉ log **một dòng summary** kèm các trường định danh:

```text
WARN requestId=req-7 operation=validate result=FAILED errorCount=2 errorCodes=MISSING_ADDRESS,INVALID_PHONE
```

Cách này thường tốt hơn cho truy vấn tập trung nếu không cần văn bản chi tiết. Đối với hệ thống có điều kiện bảo mật cao, dữ liệu chi tiết có thể lưu ở nơi thích hợp với quyền truy cập riêng, còn log chỉ chứa định danh tham chiếu được phép.

**Lưu ý về newline cuối:** Nếu message đã kết thúc bằng `\n` và formatter lại thêm một newline sau record, console/file có thể có **một dòng trống**. Đừng tùy tiện `trim()` toàn bộ message nếu khoảng trắng là dữ liệu có nghĩa; thay vào đó, kiểm soát quy tắc xuất message ở formatter hoặc tạo chuỗi không có newline cuối khi phù hợp.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi mỗi dòng console là một log event | Đếm sự kiện sai, đứt ngữ cảnh | Phân biệt record và dòng vật lý |
| Chỉ thấy dòng đầu có timestamp/level | Dòng tiếp nối mất metadata trong file text | Dùng JSON one-line hoặc parser multiline |
| Chia một sự kiện thành nhiều lời gọi log để in đẹp | Các dòng xen kẽ, có timestamp/level riêng | Giữ một event cho một ngữ cảnh logic |
| Ghi trực tiếp CRLF từ input người dùng | Có thể giả mạo log và làm hỏng parser | Escape và kiểm soát dữ liệu không tin cậy |
| Chỉ dùng `logger.error(e.getMessage())` | Mất stack trace và cause | Truyền `Throwable` cho API logging |
| Gọi `printStackTrace()` ngoài logging | Lỗi thiếu correlation ID, level, pipeline | Log exception qua backend |
| Dùng formatter chỉ ghi message | Exception được truyền vào record nhưng không xuất hiện | Dùng formatter/encoder hỗ trợ throwable |
| Pretty-print JSON trong pipeline dựa trên từng dòng | Một object bị chia thành nhiều entries | Dùng compact JSON encoder |
| Log toàn bộ payload hoặc danh sách cực lớn | Tốn I/O, tràn bộ đệm, bị cắt và lộ dữ liệu | Giới hạn độ dài, lọc trường và log summary |
| Giả định log stdout và stderr hiển thị đúng thứ tự hợp nhất | Tái dựng trình tự sai | Thu thập đủ cả hai luồng, dùng timestamp và correlation ID |
| Dùng `System.lineSeparator()` trong dữ liệu cần định dạng cố định | Khác byte trên các hệ điều hành | Chọn newline theo hợp đồng trao đổi |
| Chỉ escape `\n` mà bỏ `\r` | Vẫn còn ký tự điều khiển có thể phá cấu trúc | Xử lý cả CR, LF và các control chars liên quan |

## 12. Checklist khi thiết kế một message nhiều dòng

1. **Xác định mục đích.** Dùng cho đọc trực tiếp, debug, stack trace hay hệ thống tìm kiếm log tập trung?
2. **Xác định ranh giới event.** Những dòng này có cùng level, logger, timestamp và correlation ID không? Nếu có, nên ở chung một event.
3. **Quyết định định dạng.** Multiline text có parser hỗ trợ, hoặc structured event một dòng với newline trong field được escape?
4. **Chọn cách tạo chuỗi phù hợp.** `"\n"`, `String.join`, text block hay danh sách; tránh newline cuối không cần thiết.
5. **Giữ thông tin exception.** Truyền `Throwable` và bảo đảm formatter có thể hiển thị hoặc mã hóa stack trace.
6. **Kiểm tra input bên ngoài.** Escape/serialize đúng, giới hạn độ dài, che dữ liệu nhạy cảm.
7. **Kiểm thử với collector thực tế.** Kiểm tra một record nhiều dòng, một stack trace, CRLF từ input, nhiều thread cùng ghi và giới hạn kích thước log.
8. **Đối chiếu dữ liệu cuối cùng.** Một event nguồn vẫn được lưu thành một đơn vị truy vấn mong đợi, có đủ `requestId`, level, timestamp, logger và thông điệp.

**Kết quả cần nắm vững:** Một message có thể chứa nhiều dòng mà vẫn thuộc **một log event**. Multiline giúp diễn giải chi tiết nhưng cần kiểm soát định dạng, ranh giới record và dữ liệu không tin cậy. Với hệ thống thu thập tự động, nên ưu tiên **một event có cấu trúc trên một dòng** hoặc cấu hình multiline parser có kiểm chứng, đồng thời giữ đầy đủ exception và ngữ cảnh để điều tra.
