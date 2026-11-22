# Handler của JUL — Đích nhận và xử lý log trong Java Util Logging

## 1. Handler là gì?

Trong **Java Util Logging (JUL)**, `java.util.logging.Handler` là thành phần **nhận một `LogRecord` từ `Logger`, quyết định có xuất bản ghi đó hay không, định dạng khi cần và chuyển nó tới một đích ghi** như console, file hoặc kết nối mạng. JUL là hệ thống logging đi kèm JDK, không yêu cầu thêm thư viện để sử dụng các lớp cơ bản.

Một lời gọi như:

```java
import java.util.logging.Logger;

Logger logger = Logger.getLogger("com.example.orders");
logger.info("Order accepted");
```

tạo ra một bản ghi log theo cơ chế JUL. Nhưng **Logger và Handler có hai trách nhiệm khác nhau**:

- **Logger** là điểm ứng dụng phát sự kiện: tên logger, ngưỡng level, filter của logger, cây logger cha/con và danh sách handler gắn vào nó.
- **Handler** là điểm xử lý đầu ra: ngưỡng level và filter *riêng*, formatter, encoding, flush, close và nơi nhận bản ghi.

Một ứng dụng có thể gắn **nhiều handler vào cùng một logger**. Một `WARNING` có thể được gửi tới cả console và file, trong khi `INFO` chỉ được gửi tới file. Đây là tính năng phân phối sự kiện, không phải Java tự động “nâng cấp” mức INFO lên WARNING.

**Cần phân biệt:** Handler thuộc JUL không phải controller handler của HTTP, exception handler của Spring hay thread handler. Trong các framework logging khác, thành phần tương tự thường được gọi là *appender* (Logback, Log4j 2), nhưng API và quy tắc cấu hình không giống hoàn toàn.

## 2. Luồng LogRecord đi qua Logger và Handler

Một mô hình đơn giản:

```text
Java code
   |
   | logger.info(...) / logger.warning(...)
   v
Logger (cấp độ + filter của Logger)
   |
   +-- Không chấp nhận --> Không phát bản ghi
   |
   +-- Chấp nhận -------> LogRecord
                              |
                  +-----------+-----------+
                  |                       |
              Handler A               Handler B
            (level, filter)         (level, filter)
                  |                       |
              Formatter               Formatter
                  |                       |
             Console/file              Network
                  |
             Flush / close
                  |
          Collector / storage (nếu có)
```

Các bước cần hiểu:

1. **Ứng dụng tạo sự kiện:** mã Java gọi một phương thức logging. `LogRecord` thường chứa level, message, logger name, thời điểm, tham số và `Throwable` nếu được truyền.
2. **Logger kiểm tra level:** ví dụ logger cấu hình `Level.INFO` sẽ không chấp nhận bản ghi `FINE` nhưng có thể nhận `INFO`, `WARNING`, `SEVERE`.
3. **Logger áp dụng filter riêng** nếu có. Sự kiện bị loại ở đây không đi tới các handler.
4. **Logger chuyển bản ghi** tới các handler gắn với nó. Nếu bật `useParentHandlers`, bản ghi có thể tiếp tục tới handler của logger cha.
5. **Mỗi Handler tự xét** level và filter của mình. Handler A có thể xuất một record, còn Handler B bỏ record đó.
6. **Handler xuất bản ghi** bằng formatter/encoding phù hợp; đích ghi có thể là stdout/stderr, file hoặc socket. Bản ghi được gửi tới sink chưa chắc đã đến kho log trung tâm.

**Một chi tiết dễ nhầm của JUL:** khi bản ghi được truyền lên handler của logger cha, **ngưỡng level và filter của logger cha không được áp dụng lại cho bản ghi đã được logger con chấp nhận**; bộ lọc của chính handler ở logger cha vẫn có tác dụng. Vì vậy, không thể lấy level của root logger làm bằng chứng rằng mọi handler gắn ở root sẽ chỉ nhận các record từ level đó trở lên. Hãy kiểm tra đồng thời level của logger phát sự kiện, handler đích và propagation.

Với `Logger.setLevel(null)`, logger có thể **kế thừa level** từ logger tổ tiên theo quy tắc của JUL; `Handler.setLevel(...)` là ngưỡng riêng ở handler. Đây là hai chỗ cấu hình khác nhau.

## 3. Những Handler có sẵn trong JDK

JUL cung cấp nhiều loại handler. Các lớp thường gặp:

| Handler | Chức năng | Trường hợp phù hợp và giới hạn |
| --- | --- | --- |
| `ConsoleHandler` | Xuất bản ghi tới `System.err` theo mặc định. | Phù hợp log console; định dạng và ngưỡng chịu ảnh hưởng cấu hình JUL. Không tự biến log thành lưu trữ bền vững. |
| `FileHandler` | Ghi log vào tệp; hỗ trợ mẫu tên file, giới hạn kích thước và xoay vòng theo cấu hình. | Cần quản lý đường dẫn, quyền ghi, dung lượng, rotation/retention và việc thu thập file. |
| `StreamHandler` | Ghi qua `OutputStream` và `Formatter` được cung cấp. | Phù hợp khi muốn kiểm soát luồng ghi; cần xử lý flush và vòng đời stream cẩn thận. |
| `SocketHandler` | Gửi bản ghi qua kết nối socket tới đích từ xa. | Phụ thuộc mạng; không mặc định bảo đảm retry, phát đúng một lần hoặc lưu giữ bền vững. |
| `MemoryHandler` | Đệm một số record trong bộ nhớ và đẩy tới target handler khi đạt điều kiện push. | Giúp giữ ngữ cảnh trước sự kiện quan trọng; **không phải** queue bất đồng bộ đa luồng hoặc kho log bền vững. |

### ConsoleHandler

`ConsoleHandler` hữu ích khi ứng dụng chạy dưới supervisor/container có thể thu stderr. Nó thường xuất ra stderr, vì vậy khi hướng dẫn học tập yêu cầu **stdout chính xác** nên dùng `StreamHandler(System.out, formatter)`, như ví dụ ở mục 7, hoặc chỉ rõ luồng đầu ra đang quan sát.

Đừng mặc định “có `ConsoleHandler` thì log đã lưu vào file”. Việc thu thập stdout/stderr là trách nhiệm của runtime hoặc hệ thống collector bên ngoài.

### FileHandler

Ví dụ cấu hình file riêng trong ứng dụng (đoạn minh họa, không phải chương trình độc lập):

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

Logger logger = Logger.getLogger("com.example.batch");

// Thư mục "logs" phải tồn tại và tài khoản chạy phải được quyền ghi.
FileHandler file = new FileHandler("logs/service-%g.log",
        1_000_000, 3, true);
file.setLevel(Level.INFO);
file.setFormatter(new SimpleFormatter());
logger.addHandler(file);

// Khi chủ sở hữu kết thúc vòng đời logging:
// logger.removeHandler(file);
// file.flush();
// file.close();
```

Trong constructor trên:

- `"logs/service-%g.log"` là mẫu đường dẫn; `%g` đại diện số thế hệ file khi xoay vòng.
- `1_000_000` là giới hạn dung lượng tính bằng byte cho một file trước cơ chế rotation phù hợp.
- `3` là số file được dùng cho các thế hệ; không phải chính sách lưu giữ theo ngày.
- `true` yêu cầu chế độ append khi có thể. Cấu hình vận hành thực tế phải kiểm tra hành vi khi file đã tồn tại và khi nhiều tiến trình cùng ghi.
- `SimpleFormatter` là formatter dạng văn bản; không tự tạo JSON có cấu trúc.

Handler file cần được **đóng bởi thành phần sở hữu** khi không còn sử dụng, giúp giải phóng tài nguyên và lock. Trong ứng dụng dùng logging framework cấu hình tập trung, tránh tạo một `FileHandler` mới cho từng request.

### MemoryHandler

`MemoryHandler` đệm record trong bộ nhớ, có một *target Handler* để nhận khi push. Nó có thể giúp ghi lại các dấu vết trước lúc phát sinh lỗi nghiêm trọng, nhưng **sự kiện nằm trong buffer có thể bị mất nếu tiến trình kết thúc trước khi push**. Nó cũng không tự động biến thao tác xuất log thành background I/O. Nếu yêu cầu audit hoặc mức độ bền cao, cần giải pháp lưu trữ và xác nhận riêng.

## 4. Phương thức và thuộc tính quan trọng của Handler

`Handler` là lớp trừu tượng. Khi tự triển khai, ba phương thức nền tảng là:

```java
// Khung minh họa để hiểu hợp đồng Handler;
// các phương thức cần được triển khai trong một subclass thật.
@Override
public void publish(LogRecord record) {
    // Chọn bản ghi và đưa tới nơi nhận.
}

@Override
public void flush() {
    // Đẩy dữ liệu đang đệm nếu sink hỗ trợ.
}

@Override
public void close() {
    // Giải phóng tài nguyên mà handler sở hữu.
}
```

| API | Tác dụng |
| --- | --- |
| `publish(LogRecord)` | Xuất bản ghi. Custom Handler nên kiểm tra `isLoggable(record)` trước khi xử lý. |
| `isLoggable(LogRecord)` | Kiểm tra bản ghi có thỏa mức `Level` và `Filter` của handler hay không. |
| `setLevel(Level)` / `getLevel()` | Đặt/đọc ngưỡng severity của handler. |
| `setFilter(Filter)` / `getFilter()` | Áp dụng chính sách lọc riêng tại handler. |
| `setFormatter(Formatter)` / `getFormatter()` | Chọn cách chuyển record sang text; không phải handler nào cũng cần định dạng văn bản. |
| `setEncoding(String)` / `getEncoding()` | Cấu hình encoding khi handler hỗ trợ; không phải tất cả sink dùng encoding kiểu text. |
| `setErrorManager(ErrorManager)` | Chỉ định cơ chế báo lỗi nội bộ của handler. |
| `flush()` | Đẩy buffer do handler quản lý sang tầng dưới; **không mặc định bảo đảm fsync hoặc lưu bền vững**. |
| `close()` | Giải phóng tài nguyên do handler sở hữu; sau khi đóng không nên tiếp tục sử dụng theo cách cũ. |

Mẫu cơ bản cho custom handler:

```java
// Minh họa bên trong một subclass của java.util.logging.Handler.
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }
    // Serialize an toàn và gửi tới sink theo hợp đồng của ứng dụng.
}
```

**Không coi `isLoggable` là cơ chế bảo mật dữ liệu.** Nó lọc theo level/filter, không tự redaction token hay che dữ liệu cá nhân. Việc định dạng và ghi phải bảo toàn cấu trúc record, escape ký tự điều khiển và tuân thủ chính sách dữ liệu từ trước khi gửi.

### Filter và Formatter là hai việc riêng

- `Filter` quyết định **có cho record đi tiếp hay không**; chữ ký chính là `boolean isLoggable(LogRecord record)`.
- `Formatter` quyết định **record được biểu diễn như thế nào**; thường cài đặt `String format(LogRecord record)`.
- `Formatter.formatMessage(record)` có thể xử lý message với tham số và resource bundle theo cơ chế JUL. Đừng nhầm quy tắc template kiểu `{0}` trong JUL với placeholder `{}` của SLF4J.

Ví dụ: một handler nhận tất cả WARNING nhưng có filter bỏ thông điệp cảnh báo trùng lặp thường gặp; handler thứ hai vẫn có thể nhận record đó nếu filter của nó khác. Trong môi trường thật, việc loại cảnh báo cần quyết định dựa trên rủi ro và giá trị vận hành.

## 5. Level của Logger và Handler phối hợp ra sao?

Giả sử:

- Logger tên `com.example.orders` có `Level.INFO`.
- Handler A nhận từ `Level.INFO` trở lên.
- Handler B chỉ nhận từ `Level.WARNING` trở lên.

Khi ấy, **nếu không có filter bổ sung**:

| LogRecord phát từ logger | Logger INFO | Handler A INFO | Handler B WARNING |
| --- | --- | --- | --- |
| `FINE` | Bị chặn | Không nhận | Không nhận |
| `INFO` | Chấp nhận | Xuất | Bị chặn |
| `WARNING` | Chấp nhận | Xuất | Xuất |
| `SEVERE` | Chấp nhận | Xuất | Xuất |

Điều này cho thấy **logger chấp nhận record không có nghĩa mọi handler đều xuất record**. Nếu gắn handler với logger có ngưỡng cao hơn (ví dụ logger SEVERE), handler dù đặt ALL cũng không thể “khôi phục” các INFO đã bị logger loại ngay từ đầu.

JUL có các level chuẩn như `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST` và `ALL`/`OFF`. Handler và logger cùng dùng `java.util.logging.Level`, song cấu hình nhận/loại là **độc lập**. Việc dùng tên ERROR/WARN/DEBUG của framework khác phải có ánh xạ phù hợp, không gửi trực tiếp `Level.ERROR` hoặc `Level.WARN` cho JUL vì không có hai hằng này.

### Parent handler và hiện tượng ghi trùng

Các logger JUL có quan hệ cây dựa trên tên. Bản ghi có thể được xử lý bởi handler gắn trực tiếp tại logger con **và** handler của logger cha nếu `useParentHandlers` đang bật. Điều này đôi khi có chủ ý (console chung + file theo module), nhưng dễ gây ghi trùng nếu cả hai cùng trỏ tới console.

```java
// Minh họa trong cấu hình ứng dụng.
Logger appLogger = Logger.getLogger("com.example.orders");
appLogger.setUseParentHandlers(false);
```

Gọi `setUseParentHandlers(false)` chỉ phù hợp khi biết chắc logger có handler thay thế; nếu không, log có thể không tới đích mong muốn. Không áp dụng tràn lan cho mọi logger chỉ để che triệu chứng log trùng mà chưa kiểm tra cấu hình root và handlers.

## 6. Cấu hình Handler bằng logging.properties

JUL có thể đọc cấu hình từ `logging.properties` thông qua `LogManager`. Ví dụ một cấu hình minh họa:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.orders.level = FINE
```

Ý nghĩa:

1. `handlers` ở mức gốc nêu class handler sẽ được cấu hình.
2. `.level = INFO` đặt mức mặc định cho root logger.
3. `java.util.logging.ConsoleHandler.level = WARNING` khiến console handler chỉ xuất WARNING/SEVERE (trừ trường hợp bị filter khác).
4. `com.example.orders.level = FINE` cho phép logger ứng dụng tạo FINE, nhưng FINE **không nhất thiết xuất ra console** vì ngưỡng của handler là WARNING.
5. `SimpleFormatter` tạo text thông thường theo format JUL; không mặc định là JSON.

Chỉ định tệp cấu hình khi khởi động JVM:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties com.example.Main
```

Đường dẫn và tên lớp main ở trên là ví dụ cách dùng, **không phải một lệnh chạy cho demo ở mục 7**. Khi dùng thực tế, cung cấp đúng file và lớp main của ứng dụng; cấu hình cần được tải trước khi LogManager được khởi tạo lần đầu. Nếu dự án có container/Spring hoặc logging bridge khác, cần xác định JUL có đang được xử lý trực tiếp hay đã chuyển tiếp tới một backend khác.

**Không trộn** cấu hình `logging.properties` của JUL với XML của Logback/Log4j 2. Tên class, API và cách điều khiển formatter khác nhau.

## 7. Ví dụ Java 17 chạy độc lập: hai Handler, hai chính sách

Ví dụ sau minh họa đầy đủ:

- Logger chỉ cho phép mức INFO trở lên.
- Một `Handler` nhận INFO trở lên và ghi tiền tố `MAIN`.
- Handler thứ hai nhận WARNING trở lên, có `Filter` riêng bỏ thông điệp bắt đầu bằng `RETRY`, ghi tiền tố `ALERT`.
- Cả hai dùng `StreamHandler` hướng tới `System.out`; tự `flush()` sau mỗi lần ghi để kết quả được nhìn thấy ngay.
- Tắt parent handler để không in thêm dòng từ cấu hình JUL của máy đang chạy.

Tạo file **`JulHandlersDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class JulHandlersDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.jul.handlers");
        logger.setUseParentHandlers(false);

        // Demo tự quản lý handler để kết quả ổn định.
        for (Handler old : logger.getHandlers()) {
            logger.removeHandler(old);
        }

        logger.setLevel(Level.INFO);
        logger.setFilter(record ->
                !String.valueOf(record.getMessage())
                        .startsWith("NOISY"));

        Handler main = stdoutHandler("MAIN", Level.INFO);
        Handler alert = stdoutHandler("ALERT", Level.WARNING);

        // Filter tại ALERT không ảnh hưởng tới MAIN.
        alert.setFilter(record ->
                !String.valueOf(record.getMessage())
                        .startsWith("RETRY"));

        logger.addHandler(main);
        logger.addHandler(alert);

        logger.fine("Internal detail");
        logger.info("Order O-17 accepted");
        logger.warning("RETRY scheduled");
        logger.warning("Queue capacity nearing limit");
        logger.warning("NOISY repeated signal");
        logger.severe("Payment failed");

        main.flush();
        alert.flush();

        // Không close các StreamHandler này vì chúng dùng System.out.
        // Trong ứng dụng thật, vòng đời handler do hệ thống sở hữu.
    }

    private static Handler stdoutHandler(String name, Level minimum) {
        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return name + " | "
                        + record.getLevel().getName() + " | "
                        + formatMessage(record) + "\n";
            }
        };

        StreamHandler handler =
                new StreamHandler(System.out, formatter) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };

        handler.setLevel(minimum);
        return handler;
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên** trong thư mục chứa file:

```bash
javac -encoding UTF-8 JulHandlersDemo.java
java JulHandlersDemo
```

**Stdout chính xác** với chương trình trên:

```text
MAIN | INFO | Order O-17 accepted
MAIN | WARNING | RETRY scheduled
MAIN | WARNING | Queue capacity nearing limit
ALERT | WARNING | Queue capacity nearing limit
MAIN | SEVERE | Payment failed
ALERT | SEVERE | Payment failed
```

### Đọc kết quả qua từng bước

1. `logger.fine("Internal detail")` bị loại ở logger vì mức `FINE` thấp hơn `INFO`, nên không có dòng nào được xuất.
2. `logger.info("Order O-17 accepted")` được logger chấp nhận; handler `MAIN` mức INFO ghi một dòng; handler `ALERT` mức WARNING loại record.
3. `logger.warning("RETRY scheduled")` đủ mức để đến cả hai handler; filter của `ALERT` loại nó nên chỉ `MAIN` ghi.
4. `logger.warning("Queue capacity nearing limit")` đi qua logger, hai mức handler và filter nên xuất **hai dòng**: một dòng MAIN, một dòng ALERT. Đây là hai đích logic khác nhau trong demo, không phải bản ghi bị nhân đôi ngoài ý muốn.
5. `logger.warning("NOISY repeated signal")` bị loại ngay bởi filter ở logger, không tới handler nào.
6. `logger.severe("Payment failed")` đi qua tất cả chính sách nên xuất một dòng ở mỗi handler.

Đoạn `Formatter.format` cố ý **không in timestamp, thread hoặc vị trí code** để stdout tất định. Trong hệ thống thật nên thêm timestamp có offset/UTC, tên service, logger name, correlation/trace ID và trường sự kiện cần thiết. `Formatter.formatMessage(record)` xử lý message theo cơ chế JUL; việc tạo chuỗi JSON có cấu trúc phải dùng serializer/encoder bảo đảm escaping nếu muốn một dòng JSON hợp lệ.

**Tại sao không dùng `ConsoleHandler`?** `ConsoleHandler` thường ghi stderr và có formatter mặc định phụ thuộc cấu hình, khó trình bày stdout giống hệt trên mọi máy. Ở đây `StreamHandler(System.out, ...)` cho phép đặt tên đích và giữ output dễ kiểm chứng. Hai handler cùng dùng một stdout để học về routing; trong sản phẩm thật, các đích có thể là console, file hoặc hệ thống tập trung khác nhau.

**Giới hạn:** Ví dụ không tạo file, không chứng minh tính bền vững, không chạy background logging và không cung cấp retry. Các lời gọi chạy trên một thread để kết quả theo thứ tự rõ ràng. Khi nhiều thread/process dùng sink, cần kiểm tra cách backend đồng bộ ghi và bảo toàn ranh giới từng bản ghi.

## 8. Tự viết Handler: khi nào cần và cần tránh gì?

Chỉ nên viết subclass `Handler` nếu các handler có sẵn không đáp ứng yêu cầu: một sink đặc thù, cơ chế lọc/ghi đích đặc biệt hoặc adapter tích hợp hệ thống quan sát. Với log file, console hay socket thông thường, ưu tiên cấu hình handler đã có hoặc logging backend dự án đang dùng.

Một custom handler cần trả lời được:

- **Dữ liệu đầu vào:** dùng `LogRecord` nào, xử lý `null` ra sao và gọi `isLoggable(record)` ở đâu?
- **Format/encoding:** dùng `Formatter` nào, escape ký tự xuống dòng/dấu nháy và thông tin nhạy cảm ra sao?
- **I/O và lỗi:** nếu sink thất bại thì log bị bỏ, buffer, retry, cảnh báo hay xử lý theo hợp đồng nào? Không được làm hỏng luồng nghiệp vụ chỉ vì exception ghi log không được kiểm soát.
- **Đồng thời:** có nhiều thread gọi `publish` không? Writer có thể bị ghi xen kẽ không? Nếu async có queue, queue đầy xử lý như thế nào?
- **Lifecycle:** ai tạo, gắn, gỡ, flush và close handler? Khi shutdown thì drain bao lâu, dữ liệu có thể mất ở đâu?
- **Quyền truy cập:** sink có thể chứa dữ liệu nhạy cảm, yêu cầu TLS, lưu giữ, phân quyền và audit riêng hay không?

Mẫu thiết kế tối thiểu:

```java
// Minh họa cách tổ chức trong một Handler tùy chỉnh;
// chưa có lớp và sink cụ thể nên không phải ví dụ chạy độc lập.
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }
    try {
        // Định dạng, ghi bản ghi an toàn tới sink đã chọn.
    } catch (RuntimeException ex) {
        // Báo lỗi bằng ErrorManager theo hợp đồng handler;
        // tránh để lỗi logging tạo vòng lặp ghi log vô tận.
        reportError("Failed to write log", ex,
                java.util.logging.ErrorManager.WRITE_FAILURE);
    }
}
```

Trong mã thật, nên bắt loại lỗi đúng theo API của sink, xác định rõ bảo đảm gửi/nhận và tránh vô hạn bộ nhớ. Đừng cho handler tự log lỗi qua **chính logger mà handler đang phục vụ**, vì dễ đệ quy cho đến khi quá tải.

### Flush không phải cam kết dữ liệu đã bền vững

`flush()` có thể giúp đẩy dữ liệu đang nằm trong bộ đệm của handler tới stream, nhưng **không tự đồng nghĩa với fsync, xác nhận nhận từ server, đã index hoặc đã sao lưu**. Nếu cần chứng cứ kiểm toán, cần cơ chế xác nhận, ghi bền vững và phát hiện mất/trùng riêng; không dựa duy nhất vào việc gọi `flush()`.

### Close phải thuộc người sở hữu

Khi đóng `StreamHandler` gắn với `System.out`, có nguy cơ đóng luồng stdout dùng chung. Trong demo không gọi `close()`. Với handler sở hữu file/socket riêng, chủ sở hữu cần thực hiện `flush()`/`close()` ở thời điểm phù hợp và bỏ handler khỏi logger nếu không còn dùng. Khi cấu hình do `LogManager` hoặc framework quản lý, tránh tự tiện đóng handler do thành phần khác sở hữu.

## 9. Handler, xử lý bất đồng bộ và hiệu năng

Các handler JUL thông thường không tự tạo một hàng đợi background cho mọi record. Với sink chậm, đường `Logger → Handler.publish → I/O` có thể khiến thread nghiệp vụ phải chờ.

```text
Request thread
  |
  +-> Logger -> Handler đồng bộ -> file/network chậm
                                      |
                                  Tăng latency

Hoặc trong kiến trúc có async queue riêng:

Request thread -> enqueue LogRecord/snapshot -> worker -> handler/sink
                     |
                 Queue full?
                 block / drop / fail / spool theo chính sách
```

Để thiết kế async cần:

1. Xác định phần nào còn chạy ở request thread: tạo event, capture context, serialize hay chỉ enqueue?
2. Chọn queue có giới hạn để tránh tăng bộ nhớ không kiểm soát.
3. Xác định hành vi khi queue đầy: block, drop có đếm, fallback đồng bộ, hoặc spool bền vững.
4. Giữ ngữ cảnh quan trọng tại **thời điểm sự kiện**, đặc biệt khi object mutable hoặc thread-local thay đổi.
5. Quản lý shutdown/drain, retry, trùng, thứ tự và sự cố sink.
6. Theo dõi queue depth, số record bị loại, thời gian ghi, lỗi I/O và độ trễ ingestion.

**MemoryHandler không thay thế hàng đợi async**: nó là buffer trong bộ nhớ với điều kiện push tới handler khác, không cam kết non-blocking publication hay recovery sau crash.

Nếu một handler ghi tới network trực tiếp, kiểm tra timeout và chính sách ngoại lệ, bởi sink chậm có thể làm giảm throughput của ứng dụng. Với môi trường container, giải pháp đơn giản thường là xuất log cấu trúc ra console và để collector chuyên dụng xử lý transport/retention; chọn kiến trúc theo yêu cầu thực tế.

## 10. Bảo mật và chất lượng bản ghi qua Handler

Các nguy cơ không biến mất khi đã chia logger thành nhiều handler:

- **Rò bí mật:** mật khẩu, cookie, access token, refresh token, private key, PII có thể xuất ở nhiều sink nếu message hoặc exception được tạo thiếu kiểm soát. Cần allowlist/redaction ngay từ nguồn hoặc điểm trước mọi sink không được phép.
- **Log injection:** message chứa newline hoặc ký tự điều khiển có thể giả mạo dòng log khác. Pattern text không tự xử lý mọi trường hợp; JSON Lines cần encoder escape đúng chuẩn.
- **Ghi trùng:** cùng event được đưa qua logger con và logger cha, hoặc qua hai handler cùng đích. Cần hiểu routing thay vì xóa ngẫu nhiên handler.
- **Mất log:** logger/handler level, filter, hàng đợi, lỗi sink, collector hoặc retention có thể khiến sự kiện không còn trong kho tìm kiếm.
- **Không có context:** chỉ ghi message nhưng không có service, correlation ID hoặc mã sự kiện thì khó đối chiếu nhiều dịch vụ.
- **Quyền truy cập:** hai handler xuất tới các kho khác nhau có thể yêu cầu quyền đọc, thời gian lưu và tính toàn vẹn khác nhau.
- **Định dạng không nhất quán:** các sink dùng timezone, charset hoặc tên trường khác nhau khiến việc ghép sự kiện khó hơn.

Một `Handler Filter` chặn prefix của message không phải cơ chế bảo vệ dữ liệu hoàn chỉnh. Nếu dữ liệu bí mật đã đi vào record, một handler khác hoặc logger cha vẫn có thể phát nó. Bảo mật nên được thiết kế từ chính dữ liệu được phép đưa vào sự kiện.

## 11. Kiểm thử Handler và điều tra lỗi

Khi thiết lập JUL, nên có các kiểm tra sau:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Logger mức INFO, handler mức INFO | INFO, WARNING, SEVERE qua handler khi filter chấp nhận. |
| Logger mức INFO, handler mức WARNING | INFO bị loại tại handler, WARNING/SEVERE có thể được xuất. |
| Logger mức WARNING, handler mức ALL | FINE/INFO đã bị logger loại không thể được handler phục hồi. |
| Có filter ở logger | Sự kiện bị loại không tới bất kỳ handler downstream nào. |
| Có filter riêng của một handler | Chỉ handler đó bỏ sự kiện; handler khác vẫn có thể nhận. |
| Hai handler và parent propagation | Số bản ghi đúng như thiết kế, không nhân đôi ngoài mong đợi. |
| Formatter chứa timestamp/parameters/exception | Text/JSON hợp lệ và đủ ngữ cảnh; stack trace không bị thất lạc. |
| Message chứa newline, dấu nháy và Unicode | Encoding/escaping đúng; không tạo record giả hoặc lỗi parse. |
| File rotate, thiếu quyền ghi, đầy ổ đĩa | Có tín hiệu báo lỗi, không im lặng bỏ dữ liệu quan trọng. |
| Sink remote lỗi và khôi phục | Hành vi timeout/retry/drop đúng theo chính sách, không làm chậm vô hạn request. |
| Shutdown | Handler do ứng dụng sở hữu được flush/close; biết rõ giới hạn mất log. |

**Quy trình tìm vì sao không thấy log:**

1. Xác nhận code thực sự gọi logger cần kiểm tra.
2. Xác nhận tên logger và level hiệu lực (kể cả kế thừa).
3. Kiểm tra filter tại logger.
4. Xem handler nào gắn trực tiếp, `useParentHandlers` và các handler ở logger cha.
5. Kiểm tra level và filter của từng handler.
6. Xác nhận formatter/encoding, nơi xuất (stdout hay stderr, file path, socket), quyền ghi và lỗi I/O.
7. Nếu có collector, kiểm tra transport, ingest/index, quyền truy vấn và retention.

**Vì sao có hai dòng giống nhau?** Có thể do hai handler cùng đích, hoặc handler ở cả logger con và root với `useParentHandlers=true`. Hãy thống kê handler routing trước khi sửa.

**Vì sao chỉ có WARNING mà không có INFO?** Logger có thể nhận INFO nhưng handler cấu hình mức WARNING. Đặt logger INFO không ép handler ghi INFO.

**Vì sao logger không có handler riêng vẫn có log?** Nó có thể chuyển LogRecord lên handler ở logger cha; đây là hành vi JUL bình thường khi parent handlers được bật.

## 12. Checklist áp dụng Handler trong dự án Java

1. **Chọn API:** đang dùng JUL trực tiếp, hay JUL đã bridge sang SLF4J/Logback/Log4j 2?
2. **Quy định routing:** logger nào tạo record, handler nào nhận, có parent propagation hay không?
3. **Thiết lập level/filter từng tầng:** có kiểm thử INFO, WARNING, SEVERE và các record bị loại?
4. **Chọn đích:** stderr/stdout, file, remote hay collector; ai giữ và tìm log sau khi ghi?
5. **Định dạng:** timestamp và offset, service, correlation ID, level, event name, message, exception, encoding.
6. **Kiểm soát rủi ro:** redaction, log injection, phân quyền, log trùng và sự kiện quan trọng bị drop.
7. **Hiệu năng:** sink đồng bộ có ảnh hưởng latency không; có cần queue/spool với chính sách đầy và shutdown rõ ràng không?
8. **Vòng đời:** thành phần nào sở hữu handler, ai flush/close, có tránh đóng stdout chung không?
9. **Xác minh đầu cuối:** một event thử nghiệm có đi qua logger, handler, collector đến nơi truy vấn theo đúng kỳ vọng không?

**Ghi nhớ:** trong JUL, `Logger` quyết định nơi sự kiện được phát và việc lọc ở cấp logger; `Handler` quyết định **cách và nơi từng LogRecord được xuất**. Muốn kiểm soát logging, cần hiểu đồng thời level, filter, formatter, tập handler, cây logger và vòng đời tài nguyên. Gọi `logger.warning(...)` chỉ là điểm khởi đầu, chưa phải bảo đảm đã lưu được một bản ghi ở đích cuối.