# Cấu hình JUL (java.util.logging) trong Java

## 1. JUL là gì và “cấu hình JUL” nghĩa là gì?

**JUL** là viết tắt của **Java Util Logging** — hệ thống logging tích hợp trong JDK thông qua package **java.util.logging**. JUL cung cấp sẵn **Logger**, **Level**, **Handler**, **Formatter**, **Filter** và **LogManager**, nên một chương trình Java có thể ghi log mà không cần cài thêm thư viện bên ngoài.

**Cấu hình JUL** là việc quyết định:

- **Sự kiện nào được ghi:** đặt ngưỡng level cho logger và handler, thêm bộ lọc nếu cần.
- **Log đi đâu:** console, tệp hoặc đích khác thông qua Handler.
- **Log hiển thị thế nào:** Formatter, encoding, timestamp, tên logger, thông điệp và ngoại lệ.
- **Logger nào dùng quy tắc nào:** theo tên logger hoặc cây tên package.
- **Vòng đời log:** dung lượng file, số file luân phiên, quyền truy cập và cơ chế nạp cấu hình.

Ví dụ cùng một lời gọi:

~~~java
LOGGER.fine("Đã chọn nhánh xử lý dự phòng");
~~~

có thể **không tạo dòng output nào** nếu ngưỡng đang là INFO; có thể xuất vào console khi bật FINE; hoặc có thể đi vào một tệp debug nhưng không xuất ra console khi có hai handler với ngưỡng khác nhau.

Đây là ý nghĩa của việc **tách mã ứng dụng khỏi cấu hình quan sát vận hành**: mã chỉ mô tả sự kiện, còn cấu hình quyết định cách xử lý bản ghi.

## 2. Các thành phần tham gia cấu hình

Luồng phổ biến trong JUL:

~~~text
Mã ứng dụng: Logger.info(), fine(), log(...)
                     |
                     v
              Logger theo tên
       (effective level, Filter)
                     |
         sự kiện được chấp nhận
                     v
                 LogRecord
                     |
                     v
       Handler của logger và có thể
       Handler của các logger cha
                     |
          (Handler level, Filter)
                     |
                     v
                 Formatter
                     |
                     v
          Console / File / đích khác
~~~

| Thành phần | Vai trò khi cấu hình |
| --- | --- |
| **Logger** | Đặt tên nguồn phát log, ngưỡng level và filter; có thể có các handler trực tiếp |
| **Level** | Ngưỡng INFO, FINE, WARNING, SEVERE... |
| **Handler** | Nhận LogRecord và xuất tới đích; bản thân handler cũng có level/filter |
| **ConsoleHandler** | Ghi ra **stderr** theo mặc định của JUL |
| **FileHandler** | Ghi ra tệp, có thể giới hạn dung lượng và luân phiên tệp |
| **Formatter** | Biến LogRecord thành văn bản, ví dụ SimpleFormatter hoặc XMLFormatter |
| **Filter** | Quy tắc quyết định có chấp nhận bản ghi ngoài điều kiện level hay không |
| **LogManager** | Quản lý danh sách logger và cấu hình của JUL; đọc cấu hình từ tệp hoặc qua API |

**Logger không phải file log.** Một logger có thể phát sự kiện tới nhiều handler, hoặc không có handler nhận phù hợp nên không xuất gì cả. Việc ghi thành công ở logger cũng không tự bảo đảm dữ liệu đã được lưu bền vững ở hệ thống thu thập từ xa.

### Cây tên logger và logger gốc

Logger mang tên như **com.example.order.OrderService** thường có thể kế thừa ngưỡng từ logger cha **com.example.order**, **com.example**, **com**, rồi tới **root logger** (tên rỗng). Một logger có level bằng **null** nghĩa là dùng ngưỡng hiệu lực kế thừa; **Logger.getLevel() trả null không đồng nghĩa là tắt logging**.

Trong JUL, **root logger** có tên **""** (chuỗi rỗng); thuộc tính trong tệp cấu hình bắt đầu bằng dấu chấm như **.level = INFO** đặt level cho root.

Các handler gắn ở logger cha cũng có thể nhận LogRecord được chuyển từ logger con. Thuộc tính **useParentHandlers** kiểm soát việc chuyển tiếp đó.

## 3. Hai cách cấu hình JUL phổ biến

Có hai phương pháp chính:

1. **Qua tệp logging.properties:** thuận tiện khi muốn thay level, handler và formatter theo môi trường mà không sửa mã Java. Chỉ định tệp bằng JVM system property **java.util.logging.config.file**.
2. **Qua mã Java:** gọi **Logger.setLevel**, **Handler.setLevel**, **Logger.addHandler**, **Handler.setFormatter**, **Logger.setUseParentHandlers** để cấu hình trực tiếp.

Có thể kết hợp ở một số tình huống có kiểm soát, nhưng nên xác định rõ **nơi sở hữu cấu hình**. Nếu một framework hoặc thư viện đã thiết lập logging, tự thêm handler ở nhiều chỗ có thể làm xuất log trùng hoặc thay đổi cấu hình của thành phần khác.

Cũng cần phân biệt:

- **System property** của JVM: ví dụ **-Djava.util.logging.config.file=...**, cho biết nơi nạp cấu hình.
- **Property trong logging.properties**: ví dụ **.level = INFO**, **handlers = ...**, xác định quy tắc logging cụ thể.
- **Biến môi trường**: JUL không tự hiểu một biến như LOG_LEVEL=DEBUG chỉ vì biến đó tồn tại; ứng dụng hoặc framework phải chủ động ánh xạ nó sang cấu hình JUL.

## 4. Cấu hình bằng logging.properties: ví dụ Java 17+ chạy được

Đây là cách dễ học nhất vì bạn có thể chỉnh tệp cấu hình và chạy lại cùng một chương trình để xem hiệu ứng.

### 4.1. Tạo tệp Java

Tạo tệp **JulConfigDemo.java** trong thư mục thực hành:

~~~java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.orders");

    public static void main(String[] args) {
        LOGGER.fine("Đã chọn chiến lược xử lý=standard");
        LOGGER.info("Dịch vụ đơn hàng sẵn sàng");
        LOGGER.warning("Sử dụng cấu hình dự phòng");
    }
}
~~~

Tên logger được chọn cố định là **demo.orders** để minh họa cấu hình theo tên. Trong dự án thực, tên theo lớp như **Logger.getLogger(JulConfigDemo.class.getName())** thường là quy ước hữu ích.

### 4.2. Tạo tệp logging.properties

Tạo tệp **logging.properties** ở cùng thư mục, nội dung chính xác như sau:

~~~properties
# Handler gắn với root logger.
handlers = java.util.logging.ConsoleHandler

# Root mặc định nhận từ INFO trở lên.
.level = INFO

# Logger riêng cho thao tác đơn hàng nhận cả FINE.
demo.orders.level = FINE

# Console handler cũng cần chấp nhận FINE.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

# Định dạng cố định để ví dụ không phụ thuộc ngày/giờ.
java.util.logging.SimpleFormatter.format = %4$s | %5$s%6$s%n
~~~

Giải thích từng cấu hình:

- **handlers = java.util.logging.ConsoleHandler**: khai báo handler của root logger; các logger con thường truyền bản ghi đến handler này nếu không tắt chuyển tiếp.
- **.level = INFO**: đặt ngưỡng cho root. Nếu logger con không có level riêng, nó thường kế thừa ngưỡng này.
- **demo.orders.level = FINE**: logger **demo.orders** chấp nhận các sự kiện từ FINE trở lên, gồm FINE, INFO, WARNING, SEVERE.
- **java.util.logging.ConsoleHandler.level = FINE**: handler console được phép nhận FINE. Nếu handler đặt INFO, bản ghi FINE đã được logger chấp nhận vẫn có thể bị chặn ở handler.
- **java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter**: sử dụng formatter văn bản có sẵn trong JDK.
- **java.util.logging.ConsoleHandler.encoding = UTF-8**: chỉ định encoding để hiển thị tiếng Việt đúng khi môi trường nhận hỗ trợ.
- **java.util.logging.SimpleFormatter.format**: tùy chỉnh chuỗi hiển thị. Trong SimpleFormatter, **%4$s** là level, **%5$s** là message sau định dạng, **%6$s** là phần ngoại lệ, **%n** là xuống dòng theo nền tảng.

**Lưu ý về level cha:** khi bản ghi FINE của logger **demo.orders** đã được chấp nhận và chuyển tới handler root, **ngưỡng INFO của root không được áp lại như một bộ lọc thứ hai cho LogRecord đó**; ngưỡng của **handler** mới là điều kiện quan trọng ở đích xuất. Vì vậy cấu hình trên cho phép nhìn thấy FINE dù root đang là INFO.

### 4.3. Biên dịch và chạy

Dùng **JDK 17 trở lên**, tại thư mục chứa cả hai tệp:

~~~bash
javac -encoding UTF-8 JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulConfigDemo
~~~

**Stderr chính xác** của chương trình khi chạy với đúng tệp ở trên:

~~~text
FINE | Đã chọn chiến lược xử lý=standard
INFO | Dịch vụ đơn hàng sẵn sàng
WARNING | Sử dụng cấu hình dự phòng
~~~

**Stdout trống**, vì **ConsoleHandler của JUL mặc định ghi vào stderr**. Nếu terminal gộp hai luồng, bạn vẫn nhìn thấy các dòng log như trên. Mỗi dòng kết thúc bằng ký tự xuống dòng theo hệ điều hành.

Tham số **-Djava.util.logging.config.file=...** là một **JVM option**, cần đặt **trước tên lớp chính**. Nó phải được cung cấp từ lúc khởi động JVM để LogManager đọc đúng cấu hình khi hệ thống logging lần đầu được khởi tạo.

Nếu tên tệp hoặc đường dẫn có dấu cách, hãy quote phần tham số cho phù hợp với shell, ví dụ:

~~~bash
java "-Djava.util.logging.config.file=conf/logging dev.properties" JulConfigDemo
~~~

Lệnh có dấu cách chỉ minh họa cách quote: tệp được trỏ tới phải thực sự tồn tại.

### 4.4. Thử thay đổi level

Thay dòng:

~~~properties
demo.orders.level = FINE
~~~

thành:

~~~properties
demo.orders.level = INFO
~~~

rồi chạy lại chương trình. Khi đó, trong các cấu hình và điều kiện giống ví dụ, dòng **FINE** không còn được phát; hai dòng còn lại vẫn xuất:

~~~text
INFO | Dịch vụ đơn hàng sẵn sàng
WARNING | Sử dụng cấu hình dự phòng
~~~

Bạn đã thay đổi khả năng quan sát mà không sửa mã Java. Nếu chỉ đổi **ConsoleHandler.level = INFO** trong khi logger vẫn FINE, kết quả cũng không có dòng FINE vì handler loại nó.

## 5. Phân biệt ngưỡng Logger và ngưỡng Handler

Điều kiện để một sự kiện xuất hiện phụ thuộc **cả nơi phát và nơi nhận**.

Giả sử logger không có filter bổ sung và chỉ có một handler:

| Logger level | Handler level | Gọi fine(...) | Gọi info(...) | Gọi warning(...) |
| --- | --- | --- | --- | --- |
| INFO | INFO | Không xuất | Có thể xuất | Có thể xuất |
| FINE | INFO | Không xuất ở handler | Có thể xuất | Có thể xuất |
| INFO | FINE | Không phát từ logger | Có thể xuất | Có thể xuất |
| FINE | FINE | Có thể xuất | Có thể xuất | Có thể xuất |
| OFF | ALL | Không phát | Không phát | Không phát |

“**Có thể xuất**” có nghĩa còn tùy filter, trạng thái handler, cấu hình chuyển tiếp và đích cuối. **ALL** và **OFF** thường là giá trị ngưỡng để cho phép tất cả hoặc vô hiệu hóa ghi log, không phải mức sự kiện nghiệp vụ thường dùng.

Các level JUL từ nghiêm trọng cao xuống chi tiết thấp gồm:

~~~text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
~~~

Trong các thư viện như SLF4J/Logback thường có ERROR, WARN, INFO, DEBUG, TRACE. **JUL không có Level.DEBUG hoặc Level.ERROR**; khi dùng JUL thuần, các mức gần tương đương là FINE và SEVERE. Đây là liên hệ về mục đích sử dụng, không phải ánh xạ hoàn toàn giữa mọi framework.

## 6. Ghi vào tệp bằng FileHandler

Đối với ứng dụng muốn lưu log cục bộ, JUL cung cấp **java.util.logging.FileHandler**. Có thể gắn cả console và file handler cho root logger.

Ví dụ tệp **logging.properties** phục vụ phát triển/kiểm tra:

~~~properties
handlers = java.util.logging.ConsoleHandler, java.util.logging.FileHandler

.level = INFO
demo.orders.level = FINE

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

java.util.logging.FileHandler.level = FINE
java.util.logging.FileHandler.pattern = logs/app-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter

java.util.logging.SimpleFormatter.format = %4$s | %5$s%6$s%n
~~~

Với cấu hình này:

- **ConsoleHandler** chỉ xuất INFO, WARNING, SEVERE và các mức nghiêm trọng hơn INFO.
- **FileHandler** có ngưỡng FINE, nên có thể ghi thêm các chi tiết FINE của **demo.orders**.
- **pattern = logs/app-%g.log** đặt mẫu đường dẫn; **%g** biểu diễn số thứ tự tệp trong chu kỳ rotation.
- **limit = 1048576** đặt giới hạn kích thước mỗi tệp (xấp xỉ 1 MiB); khi đạt ngưỡng, FileHandler có thể chuyển sang tệp tiếp theo.
- **count = 3** đặt số lượng tệp trong nhóm luân phiên.
- **append = true** yêu cầu nối tiếp dữ liệu vào tệp hiện có khi phù hợp với trạng thái rotation/locking; không bảo đảm mọi lần khởi động sẽ nối chính xác vào một đường dẫn cố định.
- Các handler có thể chọn formatter riêng; đây chỉ là ví dụ dùng cùng SimpleFormatter để dễ so sánh.

**Quan trọng:** thư mục **logs** phải tồn tại và tiến trình phải có quyền ghi; FileHandler không phải cơ chế đảm bảo tạo mọi thư mục cha. Trước khi chạy trên Linux/macOS có thể tạo thư mục bằng:

~~~bash
mkdir -p logs
~~~

Trên PowerShell có thể tạo thư mục nếu chưa có:

~~~powershell
New-Item -ItemType Directory -Force -Path logs
~~~

Tệp sẽ được tạo theo pattern và có thể xuất hiện hậu tố bổ sung nhằm tránh đụng độ giữa các FileHandler/tiến trình. **Không khẳng định tên tệp thực tế luôn là app-0.log** ở mọi lần chạy hoặc mọi cấu hình. FileHandler có cơ chế khóa tệp; nhiều instance ghi chung một đường dẫn cần được thiết kế cẩn thận.

Một số token pattern thường gặp:

| Token | Ý nghĩa |
| --- | --- |
| **%g** | Chỉ số thế hệ tệp trong vòng rotation |
| **%u** | Số duy nhất để giải quyết một số trường hợp trùng tệp/khóa |
| **%t** | Thư mục tạm hệ thống |
| **%h** | Thư mục home của người dùng |
| **%%** | Một ký tự phần trăm thực |

Trong môi trường container, hướng dẫn vận hành thường ưu tiên ghi console và để hạ tầng thu thập, luân phiên và lưu trữ log. Ghi cả console lẫn file có thể phù hợp, nhưng cũng làm tăng chi phí và cần chính sách retention rõ ràng.

## 7. Tùy chỉnh định dạng log với SimpleFormatter

SimpleFormatter hỗ trợ chuỗi định dạng theo **java.util.Formatter** với các đối số được quy định. Ví dụ:

~~~properties
java.util.logging.SimpleFormatter.format = %1$tFT%1$tTZ %4$s %3$s - %5$s%6$s%n
~~~

Ý tưởng của mẫu này là in thời gian, level, tên logger, thông điệp và phần ngoại lệ. Cú pháp cụ thể dựa trên quy ước định dạng của **SimpleFormatter**, không phải placeholder **{0}** dùng trong log message.

Một số đối số:

| Vị trí | Nội dung trong SimpleFormatter |
| --- | --- |
| **%1$** | Ngày/giờ từ bản ghi, có thể dùng chuyển đổi ngày giờ như tF và tT |
| **%2$s** | Nguồn phát log (source), theo cách JUL xác định |
| **%3$s** | Tên logger |
| **%4$s** | Mức log |
| **%5$s** | Message đã định dạng |
| **%6$s** | Chuỗi ngoại lệ/stack trace nếu có |

**Chú ý múi giờ:** phần hiển thị thời gian phụ thuộc formatter và múi giờ môi trường; nếu cần UTC và định dạng chặt chẽ để tập trung log từ nhiều máy, hãy cấu hình/triển khai encoder phù hợp và kiểm chứng output trong hệ thống thật. Không giả định một pattern ngày giờ bất kỳ đã bảo đảm UTC.

### Ghi ngoại lệ để có stack trace

Với JUL, nên truyền **Throwable** khi một lỗi cần chẩn đoán:

~~~java
try {
    Integer.parseInt("invalid-number");
} catch (NumberFormatException ex) {
    LOGGER.log(java.util.logging.Level.WARNING,
            "event=validation.failed field=count", ex);
}
~~~

Đây là **đoạn minh họa** cần biến LOGGER trong lớp bao quanh, chưa phải chương trình chạy độc lập. **LOGGER.log(Level, message, ex)** giữ exception trong LogRecord. SimpleFormatter thông thường có thể hiển thị stack trace thông qua đối số ngoại lệ; một formatter tùy biến chỉ in message thì sẽ **không tự động in stack trace** nếu không xử lý record.getThrown().

Tránh ghi mỗi ex.getMessage() rồi mất nguyên nhân. Đồng thời không ghi cùng Throwable tại nhiều tầng nếu chỉ dẫn đến stack trace trùng lặp; nên quyết định ranh giới chịu trách nhiệm logging.

## 8. Cấu hình JUL bằng mã Java

Khi cần thiết lập một logger riêng trong ví dụ, công cụ hoặc ứng dụng nhỏ, có thể dùng API thay vì tệp properties.

Tạo tệp **ProgrammaticJulDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ProgrammaticJulDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.runtime");

    public static void main(String[] args) {
        // Logger này chỉ dùng handler gắn trực tiếp.
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.FINE);

        // Dùng stdout thay vì stderr để minh họa output rõ ràng.
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        output.setLevel(Level.FINE);
        LOGGER.addHandler(output);

        LOGGER.fine("event=order.validate outcome=passed");
        LOGGER.info("event=order.created outcome=success");

        // StreamHandler có bộ đệm.
        output.flush();
    }
}
~~~

Biên dịch và chạy chỉ bằng JDK 17+:

~~~bash
javac -encoding UTF-8 ProgrammaticJulDemo.java
java ProgrammaticJulDemo
~~~

**Stdout chính xác**:

~~~text
FINE | event=order.validate outcome=passed
INFO | event=order.created outcome=success
~~~

Giải thích:

1. **Logger.getLogger("demo.runtime")** lấy logger theo tên.
2. **setUseParentHandlers(false)** không chuyển bản ghi tới handler của logger cha; tránh các dòng trùng hoặc định dạng khác trong ví dụ.
3. **setLevel(Level.FINE)** cho logger chấp nhận FINE.
4. **output.setLevel(Level.FINE)** cho handler cũng chấp nhận FINE.
5. **StreamHandler(System.out, Formatter)** xuất log ra stdout, khác với ConsoleHandler mặc định ghi stderr.
6. **output.flush()** đẩy phần đã đệm ra stdout để chương trình ngắn kết thúc với output đầy đủ.

Ví dụ này chủ động tạo handler đúng một lần. Trong ứng dụng thực, không nên tạo và gắn handler trong mỗi lời gọi request hoặc mỗi lần tạo đối tượng; làm vậy có thể gây bản ghi trùng, tăng tài nguyên và khó dọn dẹp.

### Cấu hình trực tiếp logger theo class

Quy ước phổ biến:

~~~java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger(MyService.class.getName());
~~~

Đây là **đoạn minh họa** bên trong lớp MyService. Tên logger có thể được cấu hình theo lớp/package trong logging.properties. Không bắt buộc dùng tên lớp, nhưng sự ổn định của tên giúp phân nhóm và chọn level.

## 9. Quan hệ cha–con và useParentHandlers

Một Logger có thể nhận handler gắn trực tiếp và chuyển bản ghi lên handler của cha. Mặc định, JUL thường cho phép chuyển tới handler của các logger cha.

Ví dụ minh họa (không phải chương trình độc lập):

~~~java
java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("com.example.payment");

logger.setUseParentHandlers(false);
logger.addHandler(customHandler);
~~~

Đoạn này giả định **customHandler** đã được tạo. Khi **useParentHandlers=false**, chỉ các handler được gắn phù hợp ở logger đang xét nhận bản ghi từ logger đó; handler root không nhận nhờ đường chuyển tiếp này.

Điều cần nhớ:

- Nếu tắt parent handlers nhưng **quên gắn handler**, bản ghi có thể không đi đến đích mong đợi.
- Nếu vừa gắn handler ở logger con vừa dùng handler của root, một sự kiện có thể được xuất **hai lần**; điều đó không nhất thiết là hai sự cố khác nhau.
- Đừng dùng **setUseParentHandlers(false)** một cách máy móc cho mọi lớp: cấu hình tập trung thường **dựa vào handler ở root** để thu log của toàn ứng dụng.
- Logger có level **null** thì kế thừa level hiệu lực từ cha; điều này **khác** với việc handler có được kế thừa/chuyển tiếp hay không.

Thông thường, cách dễ quản lý là **gắn handler tại root**, giữ các logger con kế thừa và chỉ cấu hình mức log riêng theo package hoặc thành phần cần điều tra.

## 10. LogManager nạp cấu hình khi nào?

JUL dùng **LogManager** để quản lý cấu hình. Khi hệ thống logging lần đầu được khởi tạo, LogManager đọc cấu hình theo cơ chế của JDK. Cách phổ biến là chỉ định một tệp trước khi Java chạy:

~~~bash
java -Djava.util.logging.config.file=/path/to/logging.properties JulConfigDemo
~~~

Nếu không chỉ định tệp tùy biến, JUL có cơ chế cấu hình mặc định của JDK; nội dung/đường dẫn cụ thể có thể thay đổi giữa bản phân phối và phiên bản JDK. Không nên dựa vào định dạng output mặc định làm hợp đồng ổn định.

**Lỗi thường gặp:** đặt System.setProperty("java.util.logging.config.file", "...") trong main **sau khi logger tĩnh đã được tạo**. Lúc đó LogManager có thể đã nạp cấu hình, nên chỉ thay system property không tự bảo đảm cấu hình được đọc lại. Cách đơn giản và đáng tin trong ví dụ là **-D đặt trước tên lớp khi khởi động**.

### Nạp lại cấu hình trong lúc chạy

JUL có API **LogManager.readConfiguration(...)** để đọc lại cấu hình, và các phiên bản Java hiện đại còn có cơ chế cập nhật cấu hình. Tuy nhiên, **đọc lại cấu hình có thể đặt lại trạng thái level/handler hoặc đóng và thay thế handler tùy API và bối cảnh**. Không tự động gọi để “refresh” trong mỗi request hay giữa lúc nhiều thư viện cùng dùng JUL.

Ví dụ ý tưởng nạp tệp qua API (đoạn minh họa cần xử lý IOException và chính sách runtime của ứng dụng):

~~~java
try (java.io.InputStream input =
        java.nio.file.Files.newInputStream(
                java.nio.file.Path.of("logging.properties"))) {
    java.util.logging.LogManager.getLogManager()
            .readConfiguration(input);
}
~~~

Đoạn này **không phải một chương trình độc lập**. Trong ứng dụng đang chạy, tác dụng thay đổi cấu hình là toàn cục đối với JUL của JVM; cần bảo đảm không ảnh hưởng logger và handler mà framework khác quản lý.

**Không gọi LogManager.reset() tùy tiện** chỉ để dọn logger riêng: thao tác đó có thể tháo/đóng handler và đặt lại cấu hình của nhiều logger trong cả JVM.

## 11. Phạm vi cấu hình và hệ thống framework

Một ứng dụng Java thuần dùng **java.util.logging** có thể làm theo các ví dụ ở trên. Nhưng nhiều dự án sử dụng **SLF4J**, **Logback** hoặc **Log4j 2** làm API/backend logging chính.

| Hệ thống | Điểm cấu hình điển hình |
| --- | --- |
| JUL thuần | logging.properties, java.util.logging.config.file, Logger/Handler/LogManager |
| SLF4J | Facade API; provider/backend thực tế quyết định nơi nạp và áp dụng cấu hình |
| Logback | Cấu hình backend như logback.xml, appender, encoder, logger level |
| Log4j 2 | Cấu hình theo hệ thống Log4j 2, có handler tương ứng gọi là appender |
| Spring Boot | Cung cấp thuộc tính và cấu hình logging riêng, tùy backend được lựa chọn |

Không mặc định **logging.properties của JUL** sẽ điều khiển toàn bộ log của ứng dụng dùng Logback hoặc Log4j 2. Trong hệ thống có **bridge/adapter**, một số bản ghi có thể được chuyển giữa API, nhưng chiều chuyển và hành vi phụ thuộc thiết lập thực tế.

Nếu ứng dụng dùng một framework đã quản lý logging, hãy theo **nguồn cấu hình thống nhất của dự án**. Kết hợp quá nhiều backend, provider hoặc bridge có thể gây log trùng, thất lạc hoặc vòng chuyển tiếp.

## 12. Tùy chỉnh formatter và Filter

Khi SimpleFormatter không đủ, có thể viết lớp kế thừa **java.util.logging.Formatter** để tạo định dạng phù hợp:

~~~java
// Đoạn minh họa trong một lớp đã có Handler handler.
handler.setFormatter(new java.util.logging.Formatter() {
    @Override
    public String format(java.util.logging.LogRecord record) {
        return record.getLevel().getName() + " "
                + formatMessage(record)
                + System.lineSeparator();
    }
});
~~~

Đoạn này in mức log và message, nhưng **không in exception stack trace** vì không truy cập **record.getThrown()**. Trong ứng dụng thật, formatter nên đưa thêm timestamp có timezone rõ ràng, logger name, event code, correlation ID và Throwable khi cần.

Filter cho phép thêm điều kiện ngoài level:

~~~java
// Đoạn minh họa: handler đã được tạo.
handler.setFilter(record ->
        record.getMessage() != null
                && record.getMessage().startsWith("event="));
~~~

Ví dụ trên chỉ cho qua các bản ghi có **message template** bắt đầu bằng event=. Nó chỉ mang tính học tập: nếu message dùng placeholder hoặc được cấu trúc khác, kiểm tra **record.getMessage()** có thể không tương đương việc tìm trong chuỗi đã format. Không nên dựa vào filter thủ công quá đơn giản khi log production phức tạp.

Với log có cấu trúc, **đừng chỉ ghép JSON bằng String.format mà không escape**. Nên dùng encoder/serializer phù hợp và kiểm soát số trường, kiểu dữ liệu, cũng như việc giữ stack trace. JUL có thể viết Formatter tùy biến, nhưng không tự biến mọi log thành JSON parse được.

## 13. Bảo mật và vận hành khi cấu hình

Cấu hình JUL ảnh hưởng trực tiếp tới chi phí, rủi ro và khả năng điều tra sự cố.

### 13.1. Không ghi dữ liệu nhạy cảm

Không đưa **mật khẩu, token, API key, cookie phiên, private key, thông tin thẻ hoặc dữ liệu cá nhân nhạy cảm** vào thông điệp/stack trace ở dạng thô. Bật FINE/FINER/FINEST có thể làm lộ dữ liệu vốn không được xuất ở ngưỡng INFO.

Nếu phải có một định danh để đối chiếu, chọn mã tương quan thích hợp, che/mã hóa theo chính sách và cấp quyền truy cập phù hợp. Đừng mặc định log nguyên HTTP request body hay object.toString() để “dễ debug”.

### 13.2. Giữ lượng log ở mức hữu ích

- **INFO:** cột mốc vận hành đáng chú ý.
- **WARNING:** bất thường cần theo dõi nhưng hệ thống có thể phục hồi.
- **SEVERE:** lỗi quan trọng cần điều tra và phản ứng.
- **FINE/FINER/FINEST:** chi tiết khi cần chẩn đoán, bật có chọn lọc và theo thời gian kiểm soát.

Nếu có hàng triệu sự kiện trong vòng lặp, phát một dòng INFO cho mỗi phần tử có thể làm file/console quá tải. Với việc đếm/tỷ lệ, metric thường phù hợp hơn.

### 13.3. Hiệu năng và đánh giá thông điệp

Ngay cả khi level bị tắt, đối số của phương thức Java vẫn được tính trước khi lời gọi diễn ra. Ví dụ minh họa:

~~~java
LOGGER.fine("state=" + expensiveDescription());
~~~

**expensiveDescription()** vẫn được gọi để tạo String trước khi logger biết có bỏ FINE hay không.

JUL hỗ trợ logging bằng supplier để hoãn tính toán:

~~~java
LOGGER.log(java.util.logging.Level.FINE,
        () -> "state=" + expensiveDescription());
~~~

Đây là **các đoạn minh họa**, cần LOGGER và phương thức expensiveDescription() trong lớp thực. Supplier có thể không được thực thi khi level bị loại; không đặt logic nghiệp vụ hay tác dụng phụ bắt buộc trong supplier.

### 13.4. Rotation, encoding và retention

- **FileHandler.limit/count** giúp luân phiên một nhóm tệp, nhưng không thay thế hoàn toàn chính sách retention và archive ở hạ tầng.
- Thiết lập **encoding** thống nhất (ví dụ UTF-8) để tránh thông điệp tiếng Việt bị lỗi ký tự.
- Nếu chạy nhiều instance, quản lý đường dẫn và quyền ghi của từng instance rõ ràng; không để các tiến trình tranh chấp cùng một file log.
- Với container, cân nhắc xuất stdout/stderr và giao trách nhiệm thu thập/luân phiên cho hạ tầng.
- Timestamp nên có múi giờ rõ ràng, thường dùng UTC trong hệ thống phân tán, và tránh suy đoán thứ tự toàn cục từ các dòng log ở nhiều máy.

### 13.5. Không xem log là kho dữ liệu giao dịch

Handler có thể đệm và ghi bất đồng bộ theo cơ chế khác nhau; lỗi I/O hoặc quá tải thu thập có thể khiến bản ghi không tới đích cuối. **Việc chương trình gọi Logger không bảo đảm mọi log sẽ tồn tại mãi hoặc được lưu thành công ở nơi tập trung.** Với các sự kiện kiểm toán/giao dịch có yêu cầu bảo toàn riêng, dùng cơ chế lưu trữ phù hợp hơn.

## 14. Chẩn đoán khi cấu hình JUL không có tác dụng

Một checklist hữu ích theo thứ tự:

1. **Đúng JVM option chưa?** Tham số phải là **-Djava.util.logging.config.file=...** và đứng trước class/JAR ở lệnh java.
2. **Tệp có thực sự tồn tại không?** Đường dẫn tương đối dựa theo thư mục làm việc của tiến trình, không mặc định là thư mục chứa tệp .class hoặc .jar.
3. **Đặt property sớm chưa?** LogManager có thể đã khởi tạo trước khi ứng dụng thay property trong main.
4. **Tên logger có khớp không?** **demo.orders.level** chỉ nhắm tới logger tên demo.orders và các logger kế thừa phù hợp; một logger tên khác có thể vẫn theo ngưỡng root.
5. **Ngưỡng của logger và handler thế nào?** Cả hai phải cho phép level dự định.
6. **Có handler nhận không?** Kiểm tra root **handlers**, handler trực tiếp và **useParentHandlers**.
7. **Log đang ở stdout hay stderr?** **ConsoleHandler mặc định ghi stderr**. Lệnh redirect **> file** thường chỉ thu stdout, nên có thể không thấy log JUL.
8. **Formatter nào đang hoạt động?** Custom formatter có thể không in Throwable dù record vẫn có Throwable.
9. **FileHandler có mở được tệp không?** Kiểm tra thư mục tồn tại, quyền ghi, khóa file và đường dẫn pattern.
10. **Có framework/bridge khác can thiệp không?** Dự án dùng Logback/Log4j 2 có thể không sử dụng trực tiếp cấu hình JUL cho mọi thành phần.
11. **Bản ghi có bị filter hoặc đệm không?** Xem handler/filter, cơ chế flush, đích thu thập và retention.

### Ví dụ chuyển hướng stderr khi học JUL

Trên bash:

~~~bash
java -Djava.util.logging.config.file=logging.properties JulConfigDemo 2> jul-stderr.log
~~~

Dấu **2>** chuyển **stderr** ra tệp; **>** đơn lẻ thường chỉ chuyển stdout. FileHandler là cách lưu log qua cơ chế JUL, khác với việc shell redirect output.

Trong PowerShell, cú pháp redirection cũng hỗ trợ **2>**, nhưng cách mã hóa và biểu diễn lỗi có thể khác giữa các phiên bản; khi cần giữ byte/chữ tiếng Việt chính xác nên kiểm tra encoding và cơ chế thu thập thực tế.

## 15. Những lỗi phổ biến khi cấu hình JUL

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Dùng Level.DEBUG hoặc Level.ERROR với JUL | Lỗi biên dịch | Dùng Level.FINE hoặc Level.SEVERE theo ngữ nghĩa |
| Chỉ chỉnh logger FINE, handler INFO | Không thấy chi tiết FINE | Điều chỉnh cả ngưỡng handler |
| Chỉ chỉnh handler FINE, logger INFO | Logger loại sự kiện trước | Đặt logger/package level phù hợp |
| Tắt useParentHandlers nhưng không thêm handler | Không có output | Gắn handler riêng hoặc bật chuyển tiếp lên cha |
| Gắn thêm handler mỗi lần xử lý request | Log bị lặp, tăng tài nguyên | Cấu hình một lần ở điểm khởi tạo |
| Dùng System.setProperty sau khi JUL đã khởi tạo | Cấu hình mới không được nạp như mong đợi | Truyền JVM -D từ lúc chạy hoặc reload có kiểm soát |
| Nhầm stdout với stderr | Redirect sai luồng nên tưởng không có log | Biết ConsoleHandler mặc định dùng stderr |
| FileHandler.pattern trỏ tới thư mục không tồn tại | Không mở được file | Tạo thư mục, kiểm tra đường dẫn và quyền |
| Cấu hình SimpleFormatter nhưng mong output luôn cố định | Timezone, thời gian và nguồn có thể thay đổi | Tùy chỉnh format và kiểm chứng ở môi trường chạy |
| Chỉ log ex.getMessage() | Không có stack trace/cause | Truyền Throwable cho API và kiểm tra formatter |
| Bật FINE trên toàn production quá lâu | Log nhiều, tốn chi phí và có rủi ro lộ dữ liệu | Bật có chọn lọc, đặt ngưỡng/retention phù hợp |
| Reset LogManager từ thư viện bất kỳ | Ảnh hưởng logging toàn JVM | Để ứng dụng/framework quản lý cấu hình chung |
| Cài nhiều bridge/backend không kiểm soát | Log trùng, mất log hoặc vòng chuyển tiếp | Chọn một kiến trúc logging nhất quán |

## 16. Tự kiểm tra kiến thức

**Câu 1.** Logger **demo.orders** đặt FINE, ConsoleHandler đặt INFO. Lệnh fine(...) có xuất ra console không?

**Đáp án:** Không. Logger chấp nhận nhưng ConsoleHandler loại bản ghi FINE theo level của handler.

**Câu 2.** Root đặt INFO, logger demo.orders đặt FINE, ConsoleHandler ở root đặt FINE. Sự kiện FINE có thể xuất không?

**Đáp án:** Có, nếu không có filter khác cản và quá trình chuyển tiếp tới root handler được bật. Level INFO ở root không tự lọc lại bản ghi đã được logger con chấp nhận.

**Câu 3.** Muốn cấu hình từ tệp trước khi chạy main, dùng gì?

**Đáp án:** Dùng JVM option **-Djava.util.logging.config.file=đường-dẫn**, đặt trước tên lớp/JAR. Tệp chứa các property như **handlers**, **.level** và **java.util.logging.ConsoleHandler.level**.

**Câu 4.** Vì sao **java JulConfigDemo > out.log** có thể tạo tệp trống dù terminal vẫn có log JUL?

**Đáp án:** **ConsoleHandler mặc định xuất stderr**, còn **>** thường chuyển stdout. Dùng **2>** nếu muốn chuyển stderr, hoặc cấu hình handler phù hợp.

**Câu 5.** Cần một dòng FINE vào file nhưng không muốn nó xuất trên console. Có thể làm gì?

**Đáp án:** Logger phải chấp nhận FINE, FileHandler đặt FINE, ConsoleHandler đặt INFO. Ví dụ ở mục FileHandler minh họa đúng cách phân tách này.

**Câu 6.** **Logger.getLevel() == null** có phải logger đã tắt không?

**Đáp án:** Không. Logger có thể kế thừa ngưỡng hiệu lực từ cha. Nếu muốn tắt theo level, giá trị ngưỡng là **Level.OFF**.

**Câu 7.** Dùng SimpleFormatter mà không thấy stack trace của Throwable thì nên kiểm tra gì?

**Đáp án:** Kiểm tra có truyền đúng Throwable vào LogRecord không, handler/formatter nào đang xuất sự kiện và pattern có giữ phần ngoại lệ không. Formatter tùy biến phải chủ động xử lý phần này nếu muốn hiển thị.

**Câu 8.** Vì sao không nên gọi LogManager.reset() từ một thư viện chỉ để đổi logger của thư viện đó?

**Đáp án:** Vì LogManager quản lý logging chung của JVM; reset có thể tháo/đóng handler và thay đổi cấu hình của các logger khác.

**Ghi nhớ:** Cấu hình JUL quyết định **logger nào phát log, level nào được chấp nhận, handler nào nhận và Formatter hiển thị ra sao**. Với Java thuần, bắt đầu bằng **logging.properties + -Djava.util.logging.config.file**, kiểm tra **cả logger level và handler level**, rồi bổ sung **FileHandler, formatter, rotation và bảo vệ dữ liệu** theo nhu cầu vận hành.
