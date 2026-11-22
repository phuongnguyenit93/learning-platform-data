# java.util.logging là gì? — Tổng quan Java Util Logging (JUL)

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích **java.util.logging** (JUL) là gì, tại sao cần logging trong Java, phân biệt Logger với Handler, biết Level, LogRecord, Filter, Formatter, LogManager phối hợp ra sao, và tự tạo log có ngữ cảnh, tham số, ngoại lệ trong một chương trình **Java 17+** chạy độc lập. Bạn cũng sẽ biết cấu hình JUL qua file properties, điều tra log không xuất hiện, phân biệt JUL với các hệ thống logging phổ biến khác và áp dụng những lưu ý về bảo mật/hiệu năng.

Bài thuộc nhóm **Java Util Logging** trong **Java Core Logging**. Phần thực hành chỉ dùng thư viện có sẵn trong JDK, không yêu cầu thêm dependency Maven hay Gradle.

## 1. Java Util Logging (JUL) là gì?

**java.util.logging** là package logging chuẩn của nền tảng Java, thường viết tắt là **JUL**. Nó cung cấp các API để ứng dụng và thư viện Java **tạo, phân loại, lọc, định dạng và xuất log**. JUL cho phép ghi nhận những sự kiện có ích trong lúc chạy ứng dụng: service khởi động, request được xử lý, lựa chọn nhánh nghiệp vụ, một dependency timeout hoặc một ngoại lệ xuất hiện.

Ví dụ một dòng log được trình bày để con người đọc:

~~~text
INFO | event=order.created orderId=OD-42 items=2
~~~

Dòng này mô tả sự kiện order.created với orderId và số lượng sản phẩm. INFO là mức log. Nhưng **một bản ghi JUL không chỉ là chuỗi hiển thị**: bên trong còn có thể có timestamp, tên logger, message gốc, các tham số, Throwable và metadata khác. Định dạng chính xác của văn bản là quyết định của Formatter/Handler. Dòng ví dụ ở trên không phải định dạng bắt buộc hoặc mặc định của JUL.

JUL **không tự ghi lại mọi thứ xảy ra trong ứng dụng**. Mã ứng dụng hoặc thư viện phải gọi API logging; record có thể bị loại ở logger, handler hoặc filter; đích xuất cũng có thể gặp sự cố. Vì vậy, không tìm thấy một dòng log không chứng minh chắc chắn rằng sự kiện chưa từng xảy ra.

### Logging khác System.out.println như thế nào?

| System.out.println | java.util.logging |
| --- | --- |
| Ghi giá trị trực tiếp ra stdout | Tạo bản ghi có level, logger name, message và metadata |
| Không tự có các severity | Có SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST |
| Khó thay đổi số lượng thông báo theo package | Cho phép cấu hình level và filter theo logger |
| Không có cơ chế handler tích hợp | Có ConsoleHandler, FileHandler và các handler khác |
| Muốn định dạng hoặc log exception phải tự xử lý | Có Formatter và overload nhận Throwable |
| Hợp lý với kết quả của CLI hoặc thử nghiệm rất nhỏ | Phù hợp để ghi thông tin chẩn đoán/quan sát dài hạn |

Không có nghĩa mọi lệnh System.out.println đều sai. Đối với một chương trình CLI, stdout có thể là **dữ liệu đầu ra chính thức**. Nhưng thông tin chẩn đoán cần cơ chế điều chỉnh level, nguồn phát, format và đích xuất. Đó là lý do nên dùng logging API thống nhất.

**JUL được tích hợp sẵn trong JDK**. Với mã Java chạy trên classpath như các ví dụ bên dưới, không cần cài đặt một logging framework bên ngoài để dùng JUL. Trong ứng dụng named module, module java.logging cần được khai báo phụ thuộc rõ ràng; phần này sẽ được giải thích ở mục 10.

## 2. Kiến trúc logging cơ bản của JUL

Đường đi khái niệm của một record được mô tả như sau:

~~~mermaid
flowchart LR
    A["Mã ứng dụng gọi Logger"] --> B["Logger: level và filter"]
    B --> C["LogRecord"]
    C --> D["Handler: level và filter"]
    D --> E["Formatter"]
    E --> F["Console, file hoặc đích khác"]
~~~

Đây là mô hình rút gọn, không thể hiện toàn bộ quy tắc về logger cha/con hoặc mọi chiến lược handler.

Các thành phần cốt lõi:

| Thành phần | Vai trò | API hoặc lớp minh họa |
| --- | --- | --- |
| **Logger** | Điểm tiếp nhận các yêu cầu ghi log từ ứng dụng | Logger.getLogger, Logger.info, Logger.log |
| **Level** | Biểu thị mức nghiêm trọng hoặc độ chi tiết của record | Level.INFO, Level.WARNING, Level.FINE |
| **LogRecord** | Đối tượng chứa nội dung và metadata của một lần ghi log | getLevel, getMessage, getInstant, getThrown |
| **Filter** | Quy tắc bổ sung quyết định có chấp nhận record không | Filter.isLoggable |
| **Handler** | Xử lý và đưa record đến đích | ConsoleHandler, FileHandler, StreamHandler |
| **Formatter** | Biến record thành biểu diễn văn bản/XML | SimpleFormatter, XMLFormatter, Formatter tùy chỉnh |
| **LogManager** | Quản lý logger và cấu hình JUL | LogManager.getLogManager |

Từ code, bạn gọi **Logger**. Logger có thể bỏ record ngay nếu level không phù hợp, hoặc kiểm tra thêm Filter. Nếu record được chấp nhận, các **Handler** có thể nhận nó; mỗi Handler còn có level và Filter riêng. Formatter của Handler quyết định nội dung thực sự được xuất ra.

Một logger có thể gắn nhiều Handler: chẳng hạn console hiển thị INFO trở lên, trong khi tệp diagnostic nhận cả FINE. Đồng thời JUL có hệ thống logger cha/con, nên các Handler của parent logger cũng có thể nhận record tùy cấu hình truyền lên.

### Logger không đồng nghĩa file log

Việc khởi tạo Logger **không tự tạo file log**. Logger là nơi phát record; Handler mới quyết định nơi xuất. Nếu ứng dụng không có Handler phù hợp hoặc cấu hình bị lọc, bạn có thể không thấy gì trên console/file dù mã đã gọi phương thức logging.

## 3. Logger: cách tạo và dùng trong một lớp Java

Trong Java, cách phổ biến là tạo logger theo tên lớp và giữ tham chiếu dùng lại:

~~~java
// Đoạn minh họa bên trong lớp MyService.
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(MyService.class.getName());
~~~

MyService là tên lớp ví dụ; đoạn trên cần đặt trong một lớp thực, không phải chương trình chạy độc lập. Tên đầy đủ theo package giúp truy nguồn: log xuất từ com.example.payment.PaymentClient khác log xuất từ com.example.order.OrderService.

Các phương thức tiện lợi:

~~~java
// Minh họa: đã có đối tượng LOG ở trên.
LOG.info("event=service.started");
LOG.warning("event=dependency.retry attempt=2");
LOG.fine("event=cache.lookup result=miss");
LOG.log(java.util.logging.Level.SEVERE, "event=storage.failed");
~~~

**Logger.getLogger(name)** lấy logger theo tên. Việc đặt logger ở trường static final giúp dùng lại logger và giữ tham chiếu ổn định trong suốt vòng đời lớp. Không tạo một logger mới cho từng request.

### Tên logger và quan hệ cha/con

Tên logger thường theo phân cấp dấu chấm:

~~~text
com.example
com.example.order
com.example.order.OrderService
~~~

Nếu logger con có level bằng null, nó thường **kế thừa effective level** từ parent phù hợp. JUL có khả năng chuyển record từ logger con đến các Handler của parent. Cơ chế này giúp cấu hình logging theo package hoặc root thay vì gắn handler tại từng lớp.

Một số phương thức thường gặp:

~~~java
// Minh họa: logger và handler đã được khai báo.
logger.setLevel(java.util.logging.Level.FINE);
logger.setUseParentHandlers(false);
logger.addHandler(handler);
~~~

**setUseParentHandlers(false)** ngăn record truyền lên handler của logger cha. Nó không tự tạo handler mới, không thay đổi level của handler và cũng không đảm bảo record được xuất. Nếu tắt parent handlers nhưng không gắn handler trực tiếp, có thể mất log ở đích cần quan sát.

Ngược lại, nếu gắn handler ở logger con nhưng vẫn cho phép truyền lên parent, cùng một record có thể xuất nhiều lần nếu nhiều handler nhận record đó.

## 4. Level: phân loại sự kiện theo mức độ

JUL cung cấp các Level chuẩn:

| Level | Ý nghĩa điển hình | Ví dụ |
| --- | --- | --- |
| **SEVERE** | Lỗi nghiêm trọng khiến thao tác hoặc thành phần không thể hoàn thành đúng | Ghi dữ liệu thiết yếu thất bại, dịch vụ không phục vụ được |
| **WARNING** | Bất thường đáng quan tâm, có thể vẫn phục hồi | Timeout và retry, fallback bất thường |
| **INFO** | Mốc vận hành hoặc nghiệp vụ có giá trị theo dõi | Ứng dụng khởi động, đơn hàng được tạo |
| **CONFIG** | Thông tin cấu hình | Chế độ chạy, cờ tính năng không nhạy cảm |
| **FINE** | Chi tiết phục vụ debug | Cache miss, nhánh xử lý được chọn |
| **FINER** | Chi tiết sâu hơn | Diễn biến của một bước xử lý phức tạp |
| **FINEST** | Cực chi tiết và thường có tần suất cao | Từng bước parser, biến đổi nội bộ |
| **OFF** | Ngưỡng dùng để tắt logging | Thiết lập cấu hình |
| **ALL** | Ngưỡng cho phép mọi mức | Thiết lập cấu hình quan sát tối đa |

Không chọn Level chỉ dựa vào tên exception. Một lỗi validation được xử lý đúng có thể là một kết quả nghiệp vụ bình thường. Một lần retry có WARNING chưa chắc là request thất bại; cần đọc kết quả cuối.

Trong JUL, ngưỡng INFO thông thường cho phép INFO, WARNING, SEVERE; FINE/FINER/FINEST bị loại. Ngưỡng FINE cho phép thêm CONFIG và FINE nhưng chưa cho phép FINER/FINEST. Ngưỡng ALL cho phép mọi mức qua phép kiểm tra level, song record vẫn có thể bị Filter hoặc Handler loại.

### Logger và Handler đều lọc theo Level

| Effective level Logger | Level Handler | Record FINE được Handler xuất? |
| --- | --- | --- |
| INFO | FINE | Không: Logger loại |
| FINE | INFO | Không: Handler loại |
| FINE | FINE | Có nếu các bộ lọc khác không loại và đích xuất hoạt động |
| FINEST | FINE | Có |
| OFF | ALL | Không: Logger tắt |

Đây là một trong những lỗi thường gặp nhất: đặt Logger ở FINE nhưng ConsoleHandler còn ở INFO thì không thể quan sát FINE trên console đó.

## 5. LogRecord: một bản ghi chứa những gì?

Một lần gọi logger có thể tạo **LogRecord**. Record giữ các thông tin như:

- Level tại thời điểm ghi.
- Tên Logger.
- Message gốc và các tham số truyền kèm.
- Thời điểm record được tạo, có thể truy cập dưới dạng Instant trong Java hiện đại.
- Throwable khi dùng overload log có nhận exception.
- Một số metadata giúp truy nguồn bản ghi.

**Event** là điều đã xảy ra, ví dụ order.created. **Message** là nội dung mô tả event. **LogRecord** là cấu trúc mà hệ thống logging dùng để giữ message cùng metadata. **Formatter** là thành phần quyết định cách xuất record; **Handler** là nơi phân phối nó đến đích.

Nếu gọi JUL với message có tham số:

~~~java
// Minh họa: LOG và orderId đã được khai báo.
LOG.log(java.util.logging.Level.INFO,
        "event=order.created orderId={0} items={1}",
        new Object[] {orderId, 2});
~~~

Message gốc có thể chứa các placeholder **{0}**, **{1}** và mảng tham số. Khi Formatter dùng formatMessage(record), chúng được thay theo cú pháp của JUL. Một số thư viện khác dùng placeholder **{}**, nhưng không nên dùng lẫn cú pháp API này cho API khác.

Các chuỗi như requestId=req-7, event=payment.retry, durationMs=125 thường là **quy ước do lập trình viên ghi trong message**. JUL không mặc định biến chúng thành field cấu trúc riêng. Nếu cần tìm kiếm theo field với hệ thống thu thập log, phải thống nhất schema/format hoặc dùng giải pháp structured logging phù hợp.

## 6. Handler, Formatter và Filter

### Handler xuất record đi đâu?

Một vài Handler thông dụng:

- **ConsoleHandler:** xuất log ra console, mặc định là luồng stderr. Hữu ích trong terminal, IDE, container khi cấu hình thu stderr chính xác.
- **FileHandler:** ghi log vào tệp; hỗ trợ cấu hình tên file, kích thước/rotation và số tệp qua constructor/config phù hợp. Cần chú ý quyền ghi, disk, lock và retention.
- **StreamHandler:** ghi record lên một OutputStream với Formatter phù hợp.
- **SocketHandler:** truyền log qua socket tới nơi nhận được cấu hình; cần tính đến lỗi mạng và độ tin cậy.
- **MemoryHandler:** giữ một số record trong bộ nhớ, rồi chuyển tới Handler đích khi cần. Không phải kho lưu trữ bền vững.

Một record có thể đến nhiều Handler với cấu hình riêng. Khi debug “thấy log trong file nhưng không thấy trên console”, hãy kiểm tra level/filter của từng Handler và cấu hình parent handlers.

### Formatter trình bày LogRecord

**SimpleFormatter** tạo text dễ đọc; **XMLFormatter** xuất XML; ngoài ra bạn có thể kế thừa Formatter và định nghĩa cách thể hiện riêng. Dạng hiển thị phụ thuộc formatter và có thể phụ thuộc phiên bản JDK/cấu hình.

Ví dụ một Throwable có thể làm record text dài nhiều dòng với stack trace. Không nên đếm **mỗi dòng văn bản là một event**. Với FileHandler, nếu không chỉ định Formatter, định dạng thường là XML, không phải text một dòng giống demo tùy chỉnh.

### Filter để làm gì?

Filter cho phép thêm điều kiện ngoài Level, chẳng hạn chỉ lấy những record liên quan một module hoặc loại bản ghi không có giá trị. **Logger** và **Handler** có thể có Filter. Level đã đủ chưa chắc record được ghi nếu Filter từ chối nó.

Không nên dùng Filter hoặc Formatter để thực thi business logic. Việc logging được bật/tắt hoặc bị lọc không được làm thay đổi kết quả của ứng dụng.

### LogManager

**LogManager** quản lý Logger và cấu hình của JUL. Trong ứng dụng thực tế, nên có cấu hình logging rõ ràng để tránh việc từng lớp tự đặt handler/level khác nhau, dẫn tới log trùng, thiếu hoặc không nhất quán.

## 7. Chương trình Java 17+ sử dụng JUL

Ví dụ này dùng JUL thuần JDK, tạo một Logger theo tên lớp, cấu hình ConsoleHandler và Formatter, ghi INFO, FINE, WARNING, truyền tham số qua mẫu message, đồng thời gắn Throwable.

Tạo tệp **JulOverviewDemo.java** có toàn bộ nội dung sau:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulOverviewDemo {
    private static final Logger LOG =
            Logger.getLogger(JulOverviewDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.FINE);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + formatMessage(record);
                if (record.getThrown() != null) {
                    line += " | exception="
                            + record.getThrown().getClass().getSimpleName();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            LOG.info("event=request.started requestId=req-7");
            LOG.fine("event=cache.lookup requestId=req-7 result=miss");
            LOG.log(Level.INFO,
                    "event=order.created orderId={0} items={1}",
                    new Object[] {"OD-42", 2});
            LOG.warning("event=payment.retry requestId=req-7 attempt=2");
            LOG.info("event=request.finished requestId=req-7 status=200");
            try {
                Integer.parseInt("two");
            } catch (NumberFormatException ex) {
                LOG.log(Level.WARNING,
                        "event=quantity.invalid requestId=req-8", ex);
            }
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac JulOverviewDemo.java
java JulOverviewDemo
~~~

**Kết quả chính xác trên stderr** do ConsoleHandler xuất (chương trình không viết dòng nào vào stdout):

~~~text
INFO | event=request.started requestId=req-7
FINE | event=cache.lookup requestId=req-7 result=miss
INFO | event=order.created orderId=OD-42 items=2
WARNING | event=payment.retry requestId=req-7 attempt=2
INFO | event=request.finished requestId=req-7 status=200
WARNING | event=quantity.invalid requestId=req-8 | exception=NumberFormatException
~~~

Đây là output của Formatter trong code, cố tình **không in timestamp** để kết quả ổn định. Với SimpleFormatter, format và timestamp có thể khác.

### Giải thích hoạt động

1. **Logger.getLogger(...)** trả logger mang tên JulOverviewDemo.
2. **LOG.setUseParentHandlers(false)** tránh chuyển record cho Handler ở root logger trong demo, nhờ đó hạn chế xuất trùng.
3. **LOG.setLevel(FINE)** và **console.setLevel(FINE)** cho phép record FINE qua cả hai ngưỡng.
4. **console.setFormatter(...)** đặt formatter chỉ xuất Level, message đã xử lý tham số, và tên lớp Throwable (nếu có).
5. Lời gọi LOG.log(Level.INFO, mẫu, Object[]) giữ message template và tham số, khi Formatter gọi formatMessage(record) sẽ có orderId=OD-42 items=2.
6. WARNING của payment.retry mô tả một bước bất thường; request req-7 vẫn có log kết thúc status=200. Không suy ra request thất bại chỉ từ WARNING.
7. Lỗi parse dữ liệu thuộc requestId req-8, một event riêng. Overload log nhận Throwable giúp LogRecord giữ exception; Formatter demo chỉ rút gọn hiển thị thành tên lớp.
8. Trong khối finally, Handler được gỡ khỏi Logger rồi đóng; ứng dụng thực thường quản lý Handler theo vòng đời hệ thống thay vì tạo một Handler cho từng request.

### Bài thử nhỏ sau khi chạy

Đổi cả **LOG.setLevel(Level.FINE)** và **console.setLevel(Level.FINE)** thành **Level.INFO**, rồi chạy lại. Dòng FINE của cache.lookup sẽ biến mất nhưng các dòng INFO và WARNING vẫn còn. Nếu chỉ đổi một nơi, record FINE có thể bị loại tại nơi còn dùng INFO. Nghiệp vụ mô phỏng vẫn chạy đầy đủ dù dòng FINE không được xuất.

## 8. Tham số hóa, ghi exception và trì hoãn tạo message

**Tham số hóa** giúp tạo thông điệp nhất quán. Trong JUL, khi truyền parameters, các chỗ đánh số {0}, {1} được diễn giải theo quy tắc của MessageFormat thông qua Formatter.formatMessage. Đừng nhầm với placeholder {} của SLF4J.

Với Throwable, dùng overload nhận Throwable khi cần giữ stack trace và nguyên nhân:

~~~java
// Đoạn mã minh họa; giả sử LOG và ex đã tồn tại.
LOG.log(java.util.logging.Level.SEVERE,
        "event=storage.failed operation=save", ex);
~~~

Chỉ nối ex.getMessage() vào chuỗi thông thường sẽ không giữ toàn bộ Throwable trong record; có thể làm mất cause chain và stack trace cần thiết để điều tra.

Với nội dung log tạo ra bằng phép tính tốn chi phí, JUL hỗ trợ Supplier:

~~~java
// Đoạn minh họa; expensiveSummary() được định nghĩa trong ứng dụng.
LOG.log(java.util.logging.Level.FINE,
        () -> "event=debug.snapshot summary=" + expensiveSummary());
~~~

Supplier cho phép trì hoãn việc tạo nội dung message khi logger loại level. Không đặt side effect nghiệp vụ trong Supplier: có thể Supplier không được gọi. Có thể dùng LOG.isLoggable(Level.FINE) để bảo vệ phần chuẩn bị dữ liệu tốn chi phí. Việc logger chấp nhận record không có nghĩa handler nhất định sẽ xuất nó; Filter và Handler còn có thể loại về sau.

Trong ứng dụng nhiều request, ưu tiên event name ổn định, requestId/traceId được phép ghi, đơn vị đo rõ ràng (durationMs, bytes) và mức độ thích hợp, thay vì nối toàn bộ object hoặc payload vào message.

## 9. Cấu hình JUL ngoài code với logging.properties

Để thay đổi Level/Handler mà không sửa logic, ứng dụng thực tế thường dùng cấu hình bên ngoài. Một tệp **logging.properties** minh họa:

~~~properties
# Mức log root: INFO trở lên.
.level = INFO

# Gắn một ConsoleHandler vào root.
handlers = java.util.logging.ConsoleHandler

# Handler phải nhận FINE nếu package con bật mức này.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Chỉ tăng mức chi tiết của một package cần điều tra.
com.example.order.level = FINE
~~~

Nếu một ứng dụng khác có lớp com.example.Main đã biên dịch trong thư mục classpath out và **không tự ghi đè logger/handler bằng code**, có thể chạy:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Đây là **lệnh minh họa cho ứng dụng có cấu trúc tương ứng**, không phải lệnh chạy JulOverviewDemo ở mục 7. Demo đã tự tạo Formatter và setLevel, nên kết quả có thể không phụ thuộc hoàn toàn vào file properties.

Cách đọc cấu hình:

- **.level = INFO** đặt mức của root logger.
- **handlers = ...ConsoleHandler** gắn ConsoleHandler theo cấu hình chung của JUL.
- **ConsoleHandler.level = FINE** cho phép handler nhận FINE từ các logger con đã bật.
- **com.example.order.level = FINE** thay đổi độ chi tiết cho logger/package được chỉ định; các logger khác có thể tiếp tục kế thừa INFO.
- **java.util.logging.config.file** là JVM system property trỏ tới tệp cấu hình, đặt trước tên lớp chính trong lệnh java.

Nếu logging không hiển thị như ý, cần kiểm tra file được nạp hay chưa, logger name thực tế, parent logger, Handler, Filter và có mã/framework nào ghi đè cấu hình sau đó hay không. Đối với FileHandler, cần chú ý đường dẫn file, quyền truy cập, cấu hình rotation, retention và formatter.

## 10. JUL trong Java Platform Module System

Từ Java 9, JUL nằm trong module chuẩn **java.logging**. Với một ứng dụng dùng **named module** và module-info.java, khai báo:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Đoạn này là **nội dung module-info.java**, không phải mã chèn vào JulOverviewDemo.java. Với ví dụ đơn giản chạy trên classpath và runtime Java đầy đủ, bạn không cần tạo module-info.java.

Khi xây dựng runtime image tối giản bằng jlink, phải bảo đảm các module phụ thuộc cần thiết, trong đó có java.logging nếu ứng dụng dùng JUL, được đưa vào image. Module java.base có sẵn nhưng không thay thế java.logging.

Đừng nhầm **java.util.logging.Logger** với **System.Logger** trong java.lang hoặc **org.slf4j.Logger** của SLF4J; chúng khác nhau về API và cơ chế cấu hình/provider.

## 11. JUL so với SLF4J, Logback, Log4j 2

| Tên | Vai trò | Phân biệt |
| --- | --- | --- |
| **java.util.logging** / JUL | API và cơ chế logging tích hợp Java | Có Logger, LogRecord, Handler, Formatter, LogManager |
| **SLF4J** | Logging facade, giao diện chung cho mã ứng dụng | Không phải lớp JUL Logger; thường cần provider/backend thích hợp |
| **Logback** | Backend logging phổ biến, thường kết hợp SLF4J | Có appender/encoder/configuration riêng |
| **Log4j 2** | Framework logging với API, core và hệ cấu hình riêng | Không đồng nhất với file JUL logging.properties |
| **System.Logger** | API logging trong java.lang | Không phải alias trực tiếp của JUL Logger |

JUL tích hợp trong JDK và đáp ứng nhiều nhu cầu logging cơ bản. Những dự án lớn có thể chọn framework khác theo yêu cầu structured logging, tích hợp và chính sách của nhóm. Bridge/adapter có thể giúp tích hợp nhiều hệ thống nhưng mức mapping và đường xuất phụ thuộc cấu hình cụ thể. Thiết lập sai có thể tạo record trùng hoặc làm tưởng mất log.

Điều quan trọng khi bảo trì dự án là **xác định API mà code dùng và backend thực tế xử lý record**. Chỉnh một JUL ConsoleHandler không đương nhiên thay đổi mức DEBUG của một logger Logback nếu không có bridge tương ứng.

## 12. Sai lầm phổ biến và cách xử lý

| Vấn đề | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy FINE | Logger hoặc Handler còn ở INFO | Kiểm tra cả hai level và Filter |
| Log bị nhân đôi | Logger con và cha cùng có Handler | Kiểm tra parent handlers và số Handler gắn vào |
| Không thấy log sau khi tắt parent | Không còn Handler trực tiếp | Gắn Handler phù hợp hoặc dùng parent có chủ đích |
| File log khác định dạng console | Formatter khác, chẳng hạn XMLFormatter | Kiểm tra Formatter và parser đọc log |
| Cú pháp orderId={} không được thay | Nhầm placeholder với thư viện khác | Dùng {0}, {1} với JUL khi truyền parameters |
| Chỉ có message của exception | Không truyền Throwable hoặc Formatter bỏ stack trace | Dùng overload nhận Throwable và Formatter phù hợp |
| Mọi exception đều SEVERE | Chọn level máy móc | Căn cứ tác động và việc lỗi có được xử lý hay không |
| Log tràn khi debug | Bật ALL/FINEST ở quá nhiều package | Bật chi tiết có chọn lọc, dừng khi có bằng chứng |
| Log có secret hoặc dữ liệu cá nhân | Dump nguyên request hoặc object | Chỉ ghi field cần thiết, dùng masking/redaction và policy |
| Không tìm thấy log trên CI | Xem sai stdout/stderr hoặc backend, filter, sampling | Kiểm tra đích xuất và pipeline thu thập |
| Ghi log thành công trước commit | Event không đúng thời điểm | Chỉ xác nhận completed sau khi có bằng chứng hoàn tất |
| Log mỗi dòng trong vòng lặp | Tốn CPU/I/O và nhiều dữ liệu vô ích | Chuyển thông tin tổng hợp sang metrics hoặc giảm mức chi tiết |

**Bảo mật:** Không ghi password, access token, API key, session cookie, thông tin thẻ hoặc payload riêng tư vào log; cả log FINEST trên máy phát triển cũng có thể được đồng bộ hoặc chia sẻ. Dữ liệu đầu vào không tin cậy có thể chứa newline, ký tự điều khiển nhằm giả mạo record (**log injection**); hãy giới hạn, escape hoặc dùng structured logging và các biện pháp làm sạch phù hợp.

**Hiệu năng:** Log không miễn phí. Ngay cả khi không xuất, việc chuẩn bị tham số phức tạp có thể vẫn tốn CPU trước lời gọi logger. Khi xuất thật, Formatter, I/O, buffering và shipping đều tốn tài nguyên. Đừng ghi mọi vòng lặp hoặc toàn bộ đối tượng lớn ở INFO.

**Độ tin cậy:** Log chẩn đoán không mặc nhiên là audit trail bền vững hoặc bằng chứng transaction đã commit. Khi cần dấu vết kiểm toán, yêu cầu toàn vẹn, truy cập, lưu giữ và khả năng truy xuất phải được thiết kế riêng.

## 13. Quy trình áp dụng JUL cho một lớp mới

1. **Chọn tên Logger** theo tên lớp hoặc package, và giữ tham chiếu lâu dài.
2. **Xác định event quan trọng**: bắt đầu, kết thúc, lỗi, retry hoặc quyết định cần chẩn đoán.
3. **Chọn Level hợp lý** dựa trên tác động/độ chi tiết, không theo việc có exception hay không.
4. **Thiết kế message có ngữ cảnh**: event name, requestId/traceId được phép ghi, entity ID phù hợp, kết quả và đơn vị đo rõ ràng.
5. **Truyền Throwable nếu cần** để giữ cause chain/stack trace; tránh log trùng exception tại nhiều tầng.
6. **Chọn Handler/Formatter**, đảm bảo level ở logger và handler không chặn record cần quan sát.
7. **Kiểm thử thực tế** một case thành công, một case lỗi, rồi xem log ở console/file hoặc backend mong muốn.
8. **Quản lý cấu hình và dữ liệu an toàn** theo môi trường; tránh giữ mức cực chi tiết lâu dài.

Trong ứng dụng bất đồng bộ, các record từ nhiều thread có thể xen kẽ. Hãy dùng identifier và context được truyền đúng qua ranh giới xử lý để liên kết. Không kết luận các dòng có timestamp sát nhau chắc chắn thuộc cùng một request.

## 14. Tự kiểm tra kiến thức

**Câu 1:** java.util.logging có phải dependency ngoài JDK?

**Đáp án:** Không. JUL là API logging tích hợp Java. Với named module, khai báo requires java.logging trong module-info.java.

**Câu 2:** Vì sao Logger đã ở FINE nhưng không thấy FINE trên console?

**Đáp án:** ConsoleHandler có thể còn ở INFO hoặc có Filter loại record. Phải kiểm tra effective level của Logger, level/Filter của Handler và đường xuất.

**Câu 3:** Logger khác Handler ở đâu?

**Đáp án:** Logger nhận yêu cầu logging từ code và kiểm tra level/filter; Handler xử lý/xuất record đến đích, có thể dùng Formatter và level/filter riêng.

**Câu 4:** Sự khác nhau giữa LogRecord và text hiển thị?

**Đáp án:** LogRecord là đối tượng có message, Level, tham số, Throwable và metadata; Formatter quyết định text/XML đầu ra nên có thể lược bớt hoặc biểu diễn khác nhau.

**Câu 5:** Vì sao chương trình JulOverviewDemo hiển thị orderId=OD-42 dù code dùng {0}?

**Đáp án:** API log nhận mảng tham số và Formatter.formatMessage(record) thay các placeholder được đánh số của JUL.

**Câu 6:** Log của req-7 có WARNING nhưng request.finished status=200. Có thể kết luận request thất bại không?

**Đáp án:** Không. WARNING có thể mô tả retry đã phục hồi; kết quả cuối của cùng requestId cần được xem riêng.

**Câu 7:** Tắt useParentHandlers rồi không gắn handler riêng sẽ thế nào?

**Đáp án:** Log có thể không tới đích xuất, vì đã ngăn truyền lên Handler của parent logger.

**Câu 8:** Tại sao không ghi token hoặc raw payload ở FINEST?

**Đáp án:** Level không phải cơ chế bảo vệ dữ liệu. Log có thể được lưu, thu thập, đính kèm issue hoặc chia sẻ ngoài ý muốn.

## Ghi nhớ

**java.util.logging (JUL)** là hệ logging có sẵn trong Java. **Logger** là nơi code phát record; **Level** phân loại mức độ; **LogRecord** chứa thông tin; **Filter** xét điều kiện bổ sung; **Handler** chọn nơi xuất; **Formatter** chọn cách trình bày; **LogManager** quản lý cấu hình. Muốn log hữu ích, cần hiểu đồng thời đường đi của record, ngưỡng logger/handler, thời điểm ghi và ngữ cảnh sự kiện, trong khi vẫn kiểm soát bảo mật, chi phí và định dạng.
