# Formatter của JUL: biến LogRecord thành nội dung xuất log

## 1. Formatter làm gì trong Java Util Logging?

Trong `java.util.logging` (JUL), **`Formatter`** là lớp trừu tượng chịu trách nhiệm biến một **`LogRecord`** thành chuỗi ký tự để một `Handler` có thể xuất ra console, file hoặc một luồng khác. Một bản ghi log có thông tin như mức nghiêm trọng, thông điệp, tham số, thời điểm, tên Logger, nguồn gọi và ngoại lệ; Formatter quyết định những thông tin nào sẽ xuất hiện và cách trình bày chúng.

Ví dụ, cùng một sự kiện `order.created` có thể được hiển thị theo các cách khác nhau:

```text
INFO: event=order.created orderId=O-18
```

```text
2026-01-12T10:15:00Z | INFO | checkout | order.created | orderId=O-18
```

```json
{"timestamp":"2026-01-12T10:15:00Z","level":"INFO","service":"checkout","event":"order.created","orderId":"O-18"}
```

Đây là ba **kiểu biểu diễn minh họa**, không phải output mặc định của một chương trình JUL cụ thể. Ý nghĩa là: **event không đổi, cách mã hóa của Formatter thay đổi**.

Formatter **không quyết định có ghi log hay không**; Logger và Handler/Filter thực hiện phần kiểm tra điều kiện. Formatter cũng không tự chọn nơi lưu log: đích ghi thuộc Handler. Một Formatter tốt phải xuất đúng dữ liệu, giữ thông tin lỗi quan trọng, mã hóa an toàn, đồng thời có hiệu năng phù hợp với khối lượng log.

Mục tiêu của bài này:

1. Phân biệt `Logger`, `LogRecord`, `Handler` và `Formatter`.
2. Hiểu `Formatter.format(LogRecord)`, `formatMessage(LogRecord)`, `getHead()` và `getTail()`.
3. Biết khi nào dùng `SimpleFormatter`, `XMLFormatter`, hoặc một Formatter tùy chỉnh.
4. Tự viết và cấu hình Formatter bằng Java 17, đối chiếu được stdout.
5. Tránh các lỗi mất stack trace, định dạng sai tham số, log injection và cấu hình không có hiệu lực.

## 2. Formatter nằm ở đâu trong logging pipeline?

Luồng khái niệm của JUL:

```text
Mã Java: logger.log(Level.INFO, "...")
                 |
                 v
              Logger
       kiểm tra level và Logger Filter
                 |
                 v
              LogRecord
                 |
                 v
         Handler / Handler của cha
       kiểm tra level và Handler Filter
                 |
                 v
             Formatter
          format(LogRecord)
                 |
                 v
         Handler ghi chuỗi đã format
                 |
                 v
       stdout/stderr/file/OutputStream
```

Một ứng dụng có thể gắn nhiều Handler và mỗi Handler có Formatter riêng. Ví dụ ConsoleHandler dùng text ngắn gọn để đọc nhanh, FileHandler dùng một định dạng khác để lưu trữ. Cùng một `LogRecord` có thể tạo hai chuỗi xuất khác nhau tùy Handler.

| Thành phần | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| `Logger` | Tiếp nhận lệnh ghi log, kiểm tra level và filter, chuyển bản ghi | Có chấp nhận sự kiện này không? |
| `LogRecord` | Chứa dữ liệu sự kiện trước khi xuất | Sự kiện mang những thuộc tính gì? |
| `Handler` | Kiểm tra điều kiện xuất và ghi ra đích | Ghi ở đâu? |
| `Formatter` | Chuyển `LogRecord` thành text | Ghi theo hình thức nào? |
| `Filter` | Chấp nhận hoặc loại bản ghi ở Logger/Handler | Bản ghi có đi tiếp không? |

**Thứ tự quan trọng:** nếu một Logger loại `FINE` theo level, hoặc Handler chỉ nhận từ `WARNING`, việc tạo Formatter có hỗ trợ `FINE` cũng không làm bản ghi xuất hiện. Khi Formatter không được gọi, phải lần ngược về level, filter, Handler và đường truyền tới Handler trước khi sửa formatter.

Trong JUL, Handler thường nhận các bản ghi do Logger con chuyển lên Handler của Logger cha khi `useParentHandlers=true`. Formatter gắn với Handler cha xử lý các bản ghi đó; nó không chỉ nhận sự kiện do chính Logger cha phát ra.

## 3. API cốt lõi của `java.util.logging.Formatter`

`Formatter` là lớp trừu tượng. Khi viết subclass, phương thức bắt buộc là:

```java
@Override
public String format(LogRecord record) {
    return record.getLevel().getName()
            + " " + formatMessage(record)
            + System.lineSeparator();
}
```

Đây là **mảnh mã đặt bên trong một subclass của `Formatter`**, chưa phải chương trình hoàn chỉnh. Nó chuyển level và message thành một dòng text.

### 3.1. `format(LogRecord)`: quyết định bản ghi xuất trông thế nào

Phương thức `format` nhận `LogRecord` và trả về một `String`. Tại đây, bạn có thể chọn trường, thứ tự, timestamp, ký tự phân cách, biểu diễn lỗi và cách kết thúc dòng. Ví dụ:

```text
[WARNING] event=payment.retry attempt=2
```

Một số phương thức lấy dữ liệu hữu ích của `LogRecord`:

| Phương thức | Dữ liệu nhận được | Lưu ý |
| --- | --- | --- |
| `getLevel()` | Level của bản ghi | Có thể dùng `getName()` hoặc tên địa phương hóa |
| `getMessage()` | Message gốc hoặc khóa tra ResourceBundle | Chưa chắc đã thế tham số |
| `getParameters()` | Mảng tham số khi có | Có thể `null` |
| `getLoggerName()` | Tên Logger phát bản ghi | Có thể `null` với record tạo thủ công |
| `getInstant()` | Thời điểm bản ghi dưới dạng `Instant` | Có từ các JDK hiện đại, có trong Java 17 |
| `getSourceClassName()`, `getSourceMethodName()` | Nguồn phát khi biết | Có thể thiếu hoặc tốn chi phí xác định |
| `getThrown()` | Ngoại lệ gắn với bản ghi | Formatter phải quyết định cách thể hiện |
| `getResourceBundle()` | ResourceBundle phục vụ địa phương hóa | Không phải record nào cũng có |

Thông tin về **thời điểm phát record** nên lấy từ record. Nếu formatter tự gọi `Instant.now()`, timestamp đó phản ánh lúc format, có thể trễ hơn sự kiện thật trong hệ thống logging bất đồng bộ.

### 3.2. `formatMessage(LogRecord)`: xử lý localization và tham số

`formatMessage(record)` là phương thức có sẵn của `Formatter`. Nó cung cấp quy trình chuẩn của JUL để tạo text hiển thị từ message:

1. Xem ResourceBundle trong record, nếu có, để tra message theo khóa.
2. Xử lý tham số phù hợp theo quy ước JUL/`MessageFormat`.
3. Trả về message đã xử lý; nếu không có resource/parameter thích hợp, có thể giữ nguyên nội dung.

Ví dụ lời gọi logger:

```java
logger.log(
        Level.INFO,
        "event=order.created orderId={0} items={1}",
        new Object[] {"ord-17", "3"}
);
```

Formatter gọi `formatMessage(record)` sẽ có nội dung:

```text
event=order.created orderId=ord-17 items=3
```

Trong JUL, mẫu tham số dùng `{0}`, `{1}` theo cách dùng `java.text.MessageFormat`; đừng nhầm với placeholder `{}` phổ biến trong SLF4J. Nếu gọi `record.getMessage()` thay vì `formatMessage(record)`, bản ghi có tham số có thể vẫn hiện `{0}` và `{1}`.

**Lưu ý về locale:** `MessageFormat` có thể định dạng số/ngày theo locale của môi trường. Khi cần dữ liệu có kiểu và định dạng máy đọc ổn định, hãy dùng các field riêng và encoder có schema rõ, thay vì trông chờ việc phân tích text đã địa phương hóa.

### 3.3. `getHead(Handler)` và `getTail(Handler)`: nội dung bao một luồng

`Formatter` còn có:

```java
public String getHead(Handler handler)
public String getTail(Handler handler)
```

Mặc định hai phương thức này trả chuỗi rỗng. Một Formatter có thể ghi phần đầu/phần cuối cho cả luồng dữ liệu, ví dụ khai báo XML và thẻ đóng tương ứng. Các Handler hỗ trợ định dạng luồng, như `StreamHandler`, có thể dùng chúng khi mở/đóng luồng.

**Head/tail không phải phần được gọi cho mỗi record.** Đừng đặt timestamp, thông tin request hoặc thông điệp xử lý cho từng event trong `getHead`/`getTail`. Cũng đừng dựa vào `getTail` để bảo đảm có dấu kết thúc khi tiến trình crash hoặc bị `SIGKILL`: trong những trường hợp đó Handler có thể không được đóng có kiểm soát.

## 4. Các Formatter có sẵn trong JUL

### 4.1. `SimpleFormatter`: text để con người đọc

`java.util.logging.SimpleFormatter` chuyển record thành text gồm thông tin như thời điểm, source, level, message và throwable khi có. Đây là lựa chọn phổ biến của ConsoleHandler mặc định. Cách trình bày cụ thể có thể chịu ảnh hưởng bởi phiên bản JDK và thuộc tính cấu hình, nên không nên viết parser phụ thuộc vào định dạng mặc định của nó.

Có thể thay mẫu định dạng bằng thuộc tính:

```properties
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
```

Ý nghĩa một số đối số của mẫu theo `String.format`:

| Mã trong pattern | Ý nghĩa |
| --- | --- |
| `%1$` | Ngày/giờ của bản ghi (đối số date) |
| `%2$s` | Source class/method hoặc logger name |
| `%3$s` | Logger name |
| `%4$s` | Level name được trình bày |
| `%5$s` | Message đã được định dạng |
| `%6$s` | Phần throwable được format, nếu có |
| `%n` | Xuống dòng theo hệ điều hành |

Trong pattern, phần ngày/giờ thường dùng như `%1$tF %1$tT`; ký hiệu `%1$` đứng một mình **không phải pattern hợp lệ để xuất ngày giờ**.

Với `SimpleFormatter.format`, các placeholder là **cú pháp của `String.format`**, chẳng hạn `%4$s`, trong khi placeholder của message bên trong record vẫn theo JUL/`MessageFormat` (`{0}`, `{1}`). Đây là hai tầng định dạng khác nhau:

```text
LogRecord message: "orderId={0}" + parameter "ord-17"
    → formatMessage → "orderId=ord-17"
    → SimpleFormatter.format "%4$s: %5$s%n"
    → "INFO: orderId=ord-17"
```

### 4.2. `XMLFormatter`: XML cho dữ liệu máy xử lý

`java.util.logging.XMLFormatter` xuất record theo cấu trúc XML; nó có cách xử lý head/tail phù hợp để tạo tài liệu XML cho một stream được đóng đúng cách. `FileHandler` của JUL có mặc định liên quan đến XMLFormatter khi không bị cấu hình khác ghi đè.

XMLFormatter giúp bảo toàn những trường của record dưới dạng XML, thuận tiện cho các công cụ hiểu định dạng đó. Nó **không tự biến log thành JSON**, và không bảo đảm file XML luôn hoàn chỉnh nếu tiến trình chết trước khi Handler ghi phần kết thúc. Không nên trộn các dòng text từ một Formatter khác vào cùng file XML rồi kỳ vọng parser XML vẫn đọc được.

### 4.3. Khi nào nên tự viết Formatter?

Formatter tùy chỉnh phù hợp khi cần log text theo schema cố định hoặc tích hợp với một hệ thống đầu ra có hợp đồng rõ ràng. Chẳng hạn:

- Mỗi dòng chứa `level`, `logger`, `event` và vài trường kiểm soát.
- Timestamp theo UTC ở định dạng ISO 8601.
- Đưa ngoại lệ/stack trace theo quy ước vận hành.
- Che dữ liệu nhạy cảm trong một số trường trước khi xuất.

Nếu ứng dụng đã dùng SLF4J + Logback, Log4j 2 hoặc hệ thống structured logging chính thức, hãy ưu tiên encoder/layout được hỗ trợ của backend đó. Không nhất thiết phải tự viết bộ mã hóa JSON hoặc một bộ Formatter toàn diện bằng chuỗi nối tay.

## 5. Cấu hình Handler dùng Formatter

Trong JUL, Formatter thường được gắn qua `Handler.setFormatter(formatter)`, hoặc qua file `logging.properties` cho Handler được hỗ trợ.

Ví dụ cấu hình text ngắn gọn cho console:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
```

Trong ứng dụng JUL phù hợp, có thể yêu cầu JVM nạp file này từ sớm:

```bash
java -Djava.util.logging.config.file=logging.properties YourMainClass
```

`YourMainClass` là **tên lớp main của ứng dụng cần chạy**, không phải lớp mẫu có sẵn ở phần dưới. ConsoleHandler thường ghi vào **stderr**, vì vậy đầu ra có thể xuất hiện ở stderr chứ không phải stdout. Nếu chương trình tự tạo Handler và Formatter bằng code, thiết lập trực tiếp có thể ghi đè hoặc làm cho một số tùy chọn trong file cấu hình không còn là nguồn quyết định.

Một cấu hình đầy đủ còn liên quan tới level của Logger, level/filter của Handler, parent handlers và đích xuất. Đổi Formatter chỉ thay cách biến record thành chuỗi; nó không bật các event đã bị chặn bởi level/filter.

## 6. Ví dụ Java 17 chạy độc lập: viết Formatter tùy chỉnh

Ví dụ sau chỉ dùng JDK 17+. Nó tạo `Logger`, gắn `StreamHandler` ra `System.out` và cung cấp Formatter tự xây dựng. Chúng ta quan sát ba ý:

1. Message chứa `{0}` được thay tham số bởi `formatMessage(record)`.
2. Level `FINE` bị Handler đặt `INFO` loại, dù Logger có level `ALL`.
3. Một bản ghi có `Throwable` được Formatter tự trình bày loại lỗi và message; thông tin stack trace vẫn nằm trong record, nhưng Formatter này cố ý không in toàn bộ stack để stdout ngắn và xác định.

Tạo file **`JulFormatterDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JulFormatterDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.jul.formatter");

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" logger=")
                        .append(record.getLoggerName())
                        .append(" message=")
                        .append(formatMessage(record));

                if (record.getThrown() != null) {
                    Throwable error = record.getThrown();
                    line.append(" | cause=")
                            .append(error.getClass().getSimpleName())
                            .append(": ")
                            .append(error.getMessage());
                }

                return line.append(System.lineSeparator()).toString();
            }
        };

        Handler output = new StreamHandler(System.out, formatter) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.INFO);
        log.setLevel(Level.ALL);
        log.setUseParentHandlers(false);
        log.addHandler(output);

        try {
            log.log(Level.INFO,
                    "event=order.created orderId={0}",
                    "ord-17");

            log.fine("event=debug.details");

            log.log(Level.WARNING,
                    "event=payment.retry attempt={0}",
                    "2");

            log.log(Level.SEVERE,
                    "event=payment.failed",
                    new IllegalStateException("gateway unreachable"));
        } finally {
            output.flush();
            log.removeHandler(output);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac JulFormatterDemo.java
java JulFormatterDemo
```

**stdout chính xác của chương trình:**

```text
INFO logger=demo.jul.formatter message=event=order.created orderId=ord-17
WARNING logger=demo.jul.formatter message=event=payment.retry attempt=2
SEVERE logger=demo.jul.formatter message=event=payment.failed | cause=IllegalStateException: gateway unreachable
```

Giải thích:

- `log.log(Level.INFO, ...)` tạo record có message pattern và tham số. `formatMessage(record)` tạo `orderId=ord-17`.
- `log.fine(...)` vượt qua ngưỡng `ALL` của Logger nhưng bị `output.setLevel(INFO)` chặn. Vì vậy không có dòng `FINE`.
- `WARNING` có tham số chuỗi `"2"`, được chèn vào `{0}` mà không phụ thuộc định dạng số của locale.
- `SEVERE` đi kèm `IllegalStateException`; Formatter viết `cause=IllegalStateException: gateway unreachable` vì đó là quy tắc do ta thiết kế.
- `setUseParentHandlers(false)` ngăn bản ghi được chuyển tiếp lên ConsoleHandler của Logger cha, tránh log trùng.
- `StreamHandler` có thể đệm dữ liệu. Trong ví dụ, `publish()` gọi `flush()` sau mỗi record; cuối chương trình còn gọi `flush()`. Không dùng `close()` ở đây vì handler gắn với `System.out`: việc đóng StreamHandler có thể đóng cả luồng stdout dùng chung.
- Thứ tự stdout xác định vì chương trình chạy tuần tự, formatter không in timestamp hoặc thread ID. Ứng dụng đa luồng/bất đồng bộ không nên suy diễn luôn có thứ tự phát và xuất tuyệt đối như trong ví dụ.

### 6.1. Cách bổ sung timestamp từ LogRecord

Trong một Formatter thực tế, có thể viết **đoạn mã bên trong `format(record)`**:

```java
String timestamp = java.time.format.DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
```

`record.getInstant()` mang thời điểm event được tạo. Format `ISO_INSTANT` cho timestamp UTC phù hợp khi cần đối chiếu giữa nhiều host; không nên dùng `LocalDateTime.now()` ở thời điểm format như thể đó là thời điểm sự kiện.

Nếu muốn định dạng ngày theo múi giờ riêng, dùng `DateTimeFormatter` với `ZoneId` rõ ràng. Tránh một `SimpleDateFormat` dùng chung, có trạng thái không an toàn trong môi trường đồng thời; `DateTimeFormatter` là lựa chọn bất biến thuận tiện hơn.

### 6.2. Cách đưa stack trace vào Formatter tùy chỉnh

Nếu muốn giữ thông tin điều tra, một mảnh mã **chèn vào `format(record)`** có thể là:

```java
if (record.getThrown() != null) {
    java.io.StringWriter writer = new java.io.StringWriter();
    java.io.PrintWriter printer = new java.io.PrintWriter(writer);
    record.getThrown().printStackTrace(printer);
    printer.flush();
    line.append(System.lineSeparator()).append(writer);
}
```

Ở đây `line` là `StringBuilder` của Formatter đã có. Khi bổ sung stack trace, kết quả log có thể nhiều dòng; cần cấu hình collector để nhóm các dòng của cùng một record, hoặc dùng định dạng structured log có trường exception riêng. Nên giới hạn volume, che bí mật trong exception message nếu cần và không log stack trace giống nhau ở mọi tầng.

## 7. Locale và tham số message: hai tầng định dạng khác nhau

Một nguồn lỗi phổ biến là nhầm format pattern của **message** và pattern của **SimpleFormatter**.

### 7.1. Message pattern theo JUL

```java
logger.log(Level.INFO, "item={0} count={1}", new Object[]{"book", "3"});
```

Đây là mảnh minh họa, giả sử Logger `logger` đã khai báo. `formatMessage(record)` có thể cho kết quả:

```text
item=book count=3
```

Nếu message là khóa tra `ResourceBundle`, `formatMessage` thử lấy chuỗi được địa phương hóa trước khi thay tham số. Khi locale ảnh hưởng tới số/ngày hoặc cách viết câu, nội dung **cho người đọc** có thể thay đổi theo môi trường.

### 7.2. SimpleFormatter pattern theo Java Formatter

```properties
java.util.logging.SimpleFormatter.format = %1$tF %1$tT %4$s %5$s%6$s%n
```

Ở đây `%1$tF` là ngày từ đối số date, `%1$tT` là giờ; `%4$s` là level; `%5$s` là message đã được tạo; `%6$s` là phần throwable; `%n` là xuống dòng. Cú pháp `%1$tF` thuộc `String.format`, không phải `MessageFormat`.

Nếu lỗi `IllegalFormatException` xuất hiện từ một pattern không hợp lệ, kiểm tra cú pháp và số thứ tự đối số của `SimpleFormatter.format`. Đừng đổi `{0}` của message thành `%1$s` trừ khi thiết kế API message riêng và Formatter hiểu rõ cú pháp mới.

### 7.3. Khi cần schema máy đọc ổn định

Thông điệp bản địa hóa hữu ích cho con người; nhưng hệ thống cảnh báo và dashboard không nên dựa hoàn toàn vào so khớp chuỗi message có thể đổi theo locale hoặc ngôn ngữ. Duy trì mã sự kiện và trường cấu trúc ổn định (`event`, `errorCode`, `requestId`) để truy vấn; Formatter chịu trách nhiệm đưa chúng ra định dạng được hệ thống thu thập hiểu.

## 8. Chất lượng, hiệu năng và an toàn của Formatter

### 8.1. Giữ mỗi event độc lập, đúng cấu trúc

Với text log, thêm newline cuối record giúp không dính hai sự kiện. Nhưng nếu giá trị từ người dùng có `\\n` hoặc `\\r`, một log có thể bị giả thành nhiều dòng nếu không được escape. Ví dụ đầu vào:

```text
name=visitor
ERROR event=admin.login outcome=success
```

Dòng thứ hai có thể chỉ là nội dung độc hại được chèn vào trường `name`, chứ không phải sự kiện thực. Dùng encoder JSON chuẩn khi cần structured output; với text, escape ký tự điều khiển và thống nhất cách quote các giá trị. `formatMessage(record)` chỉ thực hiện xử lý message của JUL, **không phải bộ lọc bảo mật dữ liệu**.

Không tự nối JSON bằng các `StringBuilder.append` tùy tiện khi dữ liệu có dấu ngoặc kép, backslash, Unicode và ký tự điều khiển; ưu tiên thư viện serializer đáng tin cậy nếu kiến trúc ứng dụng cần JSON.

### 8.2. Không đánh mất Throwable

`record.getMessage()` không chứa stack trace theo quy tắc bắt buộc. `record.getThrown()` lưu ngoại lệ nếu caller đã truyền bằng overload phù hợp. Formatter tùy chỉnh phải tự quyết định có xuất loại lỗi, thông điệp, cause chain và stack trace không. Việc xuất rất ít có thể tiết kiệm dung lượng, nhưng mất call stack sẽ khó chẩn đoán lỗi bất thường.

Phân biệt lỗi được mong đợi có mã nghiệp vụ (có thể chỉ cần `errorCode`) với lỗi hệ thống cần stack trace. Chỉ format stack trace khi thực sự có ý nghĩa; đừng in cùng exception ở mọi ranh giới gọi.

### 8.3. Không đặt nghiệp vụ vào Formatter

Formatter nên là tầng trình bày. Đừng:

- Gửi HTTP request hoặc ghi database trong `format()`.
- Thay đổi trạng thái thanh toán hoặc tăng bộ đếm nghiệp vụ khi một record được format.
- Gọi `logger.log()` từ chính `format()` trên cùng pipeline, tạo nguy cơ đệ quy.
- Đọc thêm bí mật hoặc toàn bộ object chỉ để “bổ sung thông tin”.
- Gọi clock hiện tại để thay thế sai thời điểm trong `LogRecord`.

Một Formatter được gọi trên đường I/O đồng bộ có thể làm chậm request nếu serialization, stack trace hoặc lookup quá nặng. Với backend bất đồng bộ, formatting có thể chạy ở thread khác; muốn tránh race, chụp dữ liệu ngữ cảnh thành snapshot khi tạo event.

### 8.4. Cẩn thận với trạng thái dùng chung và thứ tự log

Nếu Formatter có field đếm số dòng hoặc đối tượng định dạng mutable, phải xem cách Handler sử dụng Formatter qua nhiều thread. Cách an toàn thường là để Formatter **không giữ trạng thái thay đổi** và dùng đối tượng immutable (ví dụ `DateTimeFormatter`). JUL hỗ trợ nhiều thread ghi log nhưng đừng giả định mọi Formatter tùy chỉnh hoặc mọi Handler bên ngoài đều tự đồng bộ như nhau.

Formatter cũng không đảm bảo log đã được lưu bền vững. Handler có thể buffer, file có thể đầy, collector có thể lỗi và crash có thể làm mất các record cuối. Khi cần bảo đảm kiểm toán, phải thiết kế cơ chế audit/storage phù hợp riêng.

### 8.5. Bảo vệ thông tin nhạy cảm trước khi xuất

Một Formatter có thể áp dụng che/mask dữ liệu nhất quán, nhưng điểm bảo vệ đầu tiên vẫn phải là quyết định **không đưa password, token, cookie, số thẻ và dữ liệu cá nhân không cần thiết vào `LogRecord`**. Formatter không thể đảm bảo loại bỏ mọi secret đã vô tình nằm trong một message tự do hoặc throwable text. Cần allowlist trường an toàn, giới hạn độ dài, kiểm soát quyền đọc log và retention.

## 9. Chẩn đoán các lỗi liên quan Formatter

| Biểu hiện | Cách kiểm tra |
| --- | --- |
| Log có `{0}` nguyên văn | Formatter có gọi `formatMessage(record)` không; record có parameters không |
| Message đã định dạng nhưng thiếu stack trace | Formatter có xử lý `getThrown()` không; caller đã truyền `Throwable` đúng overload chưa |
| Level `FINE` không xuất hiện | Kiểm tra level/filter của Logger, Handler và đường parent handlers trước Formatter |
| Formatter mới không có hiệu lực | Kiểm tra Handler thực sự sở hữu Formatter, cấu hình runtime có bị code ghi đè không |
| Log bị in hai lần | Có Handler ở cả Logger con và Logger cha; kiểm tra `useParentHandlers` |
| Đặt Formatter JSON nhưng file không parse được | Kiểm tra escape, framing, đầu/cuối stream, dữ liệu không tin cậy và nhiều Handler trộn output |
| Thời điểm log lệch với trace | Formatter dùng `Instant.now()` thay vì thời điểm từ record, hoặc chậm do async |
| Ký tự tiếng Việt/language bị lỗi | Charset ở Handler/stream, encoding của collector và terminal; locale/resource bundle |
| File XML thiếu thẻ kết thúc | Handler chưa đóng sạch, tiến trình crash hoặc file bị cắt |
| Log nhiều dòng bị tách thành nhiều sự kiện | Stack trace và text value chưa escape; cấu hình multiline parser ở collector |
| Logging gây chậm request | Formatter làm serialization hoặc xử lý stack trace quá nặng trên đường đồng bộ |
| Dữ liệu nhạy cảm xuất ra dù đã mask | Bản ghi chứa secret ở trường khác, throwable hoặc một Handler khác có Formatter riêng |

Quy trình điều tra nên đi từ lúc tạo record đến nơi xuất: **Logger có chấp nhận level? → Handler có nhận record? → Formatter nào đang gắn? → Formatter có tạo đúng text? → stream/collector có ghi đúng không?** Không nên thay đổi nhiều thứ cùng lúc nếu mục tiêu chỉ là sửa cách trình bày.

## 10. Checklist áp dụng

- Xác định hệ thống dùng JUL thật hay một facade/backend khác; Formatter của JUL không tự cấu hình layout của Logback/Log4j 2.
- Dùng `SimpleFormatter` cho log text thông thường, `XMLFormatter` khi pipeline thực sự cần XML, hoặc Formatter tùy chỉnh khi có schema rõ ràng.
- Trong custom `format(LogRecord)`, dùng `formatMessage(record)` nếu muốn xử lý ResourceBundle và message parameters theo quy tắc JUL.
- Lấy timestamp từ record, xuất level/source/logger khi cần, ghi rõ event và context cần thiết.
- Xử lý `record.getThrown()` có chủ đích; không vô tình bỏ thông tin chẩn đoán.
- Đặt Formatter ở đúng Handler, kiểm tra level/filter và parent propagation.
- Đảm bảo một record có cấu trúc rõ ràng, escape dữ liệu không tin cậy và hỗ trợ Unicode đúng encoding.
- Giữ Formatter gọn, an toàn với nhiều thread và tránh side effect hoặc logging đệ quy.
- Thử tối thiểu bốn trường hợp: log có tham số, log có Throwable, log bị Handler lọc, và nhiều Handler có Formatter khác nhau.
- Kiểm tra thực tế stdout/stderr/file, buffer/flush, log collector, độ an toàn thông tin và chính sách lưu trữ.

**Kết luận:** Trong JUL, `Formatter` quyết định **cách một `LogRecord` được biểu diễn**, còn `Logger` và `Handler` quyết định event có được nhận và xuất ra đích nào. Sử dụng `formatMessage(record)`, xử lý Throwable, đặt timestamp từ record và cấu hình Formatter trên đúng Handler giúp log dễ đọc, truy vấn được và ít gây hiểu lầm khi chẩn đoán sự cố.
