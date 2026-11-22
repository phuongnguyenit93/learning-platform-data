# LogManager trong Java Util Logging (JUL)

## 1. LogManager giải quyết vấn đề gì?

**java.util.logging.LogManager** là bộ quản lý cấu hình và danh mục Logger của **Java Util Logging (JUL)**, hệ thống logging có sẵn trong JDK. Khi ứng dụng có nhiều lớp, package và nơi ghi log, cần một nơi xác định level của từng Logger, cấu hình Handler, đọc cấu hình từ tệp, và quản lý các Logger đã đăng ký. Đó là vai trò của LogManager.

Ví dụ, ứng dụng bán hàng có các Logger **com.example.order**, **com.example.payment**, **com.example.inventory**. Khi muốn bật log chi tiết chỉ cho payment, ta có thể cấu hình theo tên thay vì sửa từng lời gọi logger.info hoặc logger.fine trong mã nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt **LogManager**, **Logger**, **LogRecord**, **Level**, **Handler**, **Filter** và **Formatter**.
- Hiểu LogManager như thành phần quản lý ở **phạm vi JVM**, cách lấy instance qua **getLogManager()** và tra cứu Logger bằng tên.
- Sử dụng các API **getProperty**, **getLogger**, **getLoggerNames**, hiểu vai trò **addLogger**, **readConfiguration**, **reset** và **updateConfiguration**.
- Biết đường đi của cấu hình **logging.properties**, tham số JVM **java.util.logging.config.file**, quan hệ giữa root Logger và Logger con.
- Biên dịch/chạy chương trình Java 17+ nạp cấu hình bằng InputStream và quan sát chính xác cách Logger/Handler lọc record.
- Nhận diện lỗi reload làm mất Handler, cấu hình FINE nhưng không thấy log, logging trùng và nhầm JUL với backend khác.

**Giới hạn nội dung:** Bài tập trung vào LogManager của JUL trong Java Core. Không triển khai hệ thống tập trung để lưu trữ log, không thay LogManager bằng framework riêng.

## 2. Vị trí trong kiến trúc logging

Các thành phần JUL phối hợp như sau:

~~~text
Application code
  |
  | Logger.getLogger("com.example.order")
  v
Logger  <------------------------- LogManager
  |                             - đăng ký/tra tên Logger
  |                             - cấu hình từ properties
  |                             - read/reload/reset
  |                             - level và Handler config
  v
LogRecord (Level, message, time, parameters, Throwable)
  |
  +--> Logger Filter (nếu có)
  |
  v
Handler(s): level + Filter
  |
  v
Formatter
  |
  v
stdout/stderr, file, output stream, collector...
~~~

Sơ đồ minh họa **vai trò**, không thể hiện từng lời gọi nội bộ của JDK theo thứ tự tuyệt đối. Trong JUL, Logger kiểm tra level và filter trước khi chuyển LogRecord tới các Handler; Handler cũng có mức lọc riêng. Formatter là thành phần được Handler dùng để tạo text output.

**LogManager không trực tiếp ghi ra console hoặc file.** Nó không thay thế Handler và không phải API để phát log. Nếu business code gọi **logger.info("order created")**, Logger phát sự kiện; cấu hình JUL/LogManager giúp xác định Logger nào được cho phép và record có thể đến Handler nào.

| Thành phần | Nhiệm vụ | API quen thuộc |
| --- | --- | --- |
| **LogManager** | Quản lý cấu hình JUL, registry Logger và vòng đời cấu hình | getLogManager, getProperty, readConfiguration |
| **Logger** | Phát record, level/filter, chuyển tới handler | getLogger, info, warning, log |
| **LogRecord** | Mang dữ liệu một sự kiện | getLevel, getMessage, getThrown |
| **Level** | Mức severity hoặc ngưỡng | SEVERE, WARNING, INFO, FINE, ALL, OFF |
| **Handler** | Chấp nhận record và ghi ra đích | publish, flush, close |
| **Filter** | Quyết định record có hợp lệ ở điểm kiểm tra | isLoggable |
| **Formatter** | Chuyển record thành text | format, formatMessage |

Chỉ dùng tên Logger chuẩn và cấu hình tập trung vẫn chưa đủ để đảm bảo log có thể quan sát được. Đường ghi thực tế phụ thuộc tất cả các lớp trên và cả pipeline sau JVM nếu có.

## 3. LogManager toàn cục của JVM

Trong phần lớn ứng dụng, LogManager được lấy qua:

~~~java
import java.util.logging.LogManager;

LogManager manager = LogManager.getLogManager();
~~~

Đây là đoạn mã minh họa nằm trong một phương thức Java, chưa phải chương trình độc lập có main(). **LogManager.getLogManager()** trả về LogManager mà JUL đang sử dụng trong JVM. Nó là đối tượng hạ tầng dùng chung, không phải dữ liệu riêng cho từng request.

Một ứng dụng nên giữ Logger theo lớp hoặc module:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void create(String orderId) {
        LOG.info("event=order.created orderId=" + orderId);
    }
}
~~~

Class trên là một thành phần có thể biên dịch; nó không có main(). Trường **static final** giữ tham chiếu Logger ổn định; Logger được đặt tên theo class. Trong môi trường thực, cần kiểm soát dữ liệu đưa vào message để không ghi thông tin nhạy cảm.

**Không tạo Logger theo từng request ID hoặc từng khách hàng.** Ví dụ **Logger.getLogger("request-" + requestId)** tạo namespace động khó quản lý, tăng số Logger và khiến properties không dễ áp dụng. Correlation ID nên là dữ liệu của event, thay vì tên Logger.

### 3.1. Root Logger

Root Logger trong JUL có **tên là chuỗi rỗng**:

~~~java
Logger root = LogManager.getLogManager().getLogger("");
~~~

Vì thế cấu hình level cho root thường là:

~~~properties
.level = INFO
~~~

Logger có tên chấm phân cấp theo namespace:

~~~text
"" (root)
  |
  +--- com
         |
         +--- com.example
                   |
                   +--- com.example.order
                   +--- com.example.payment
~~~

Một số node cha có thể được tạo bởi hệ thống để duy trì cây Logger. Tên được đăng ký và cách tham chiếu Logger có thể thay đổi trong vòng đời JVM.

### 3.2. Level riêng và level kế thừa

Một Logger có thể có level cụ thể hoặc **getLevel() == null**. **Null** nghĩa là Logger không có level riêng, nên lấy effective level từ ancestor gần nhất được cấu hình. Null **không đồng nghĩa ALL**.

Ví dụ:

~~~text
root: INFO
  com.example: WARNING
    com.example.order: null => kế thừa WARNING
    com.example.payment: FINE => dùng FINE riêng
~~~

**Kế thừa level** khác với **chuyển record tới Handler của cha**. Một record đã được Logger con chấp nhận có thể chuyển lên Handler của Logger cha nếu useParentHandlers cho phép; mức level của từng Logger cha không được áp dụng lại như khi record phát sinh ở Logger con. Nhưng Handler của cha vẫn dùng ngưỡng và filter riêng.

## 4. Các phương thức quan trọng của LogManager

### 4.1. getLogManager()

Lấy LogManager đang được JUL sử dụng:

~~~java
LogManager manager = LogManager.getLogManager();
~~~

Đây là điểm truy cập chuẩn để làm việc với cấu hình chung; không cần tự tạo một LogManager cho mỗi package hay request.

### 4.2. getProperty(String key)

Trả về **String** từ tập properties đã nạp:

~~~java
String level = manager.getProperty("com.example.payment.level");
~~~

Nếu key không tồn tại, kết quả có thể là **null**. Giá trị **"FINE"** là nội dung cấu hình, không phải bằng chứng chắc chắn rằng console đang in FINE. Có thể Handler vẫn ở INFO, Filter đang chặn hoặc Logger dùng tên khác.

**Phân biệt:** getProperty trả text cấu hình; logger.getLevel() trả Level đã đặt trực tiếp trên Logger; logger.isLoggable(Level.FINE) kiểm tra việc Logger có nhận level đó ở thời điểm gọi hay không.

### 4.3. getLogger(String name)

Tra cứu một Logger đã được LogManager đăng ký:

~~~java
Logger candidate = manager.getLogger("com.example.payment");
~~~

Phương thức này **có thể trả null** khi Logger chưa được đăng ký hoặc không còn tham chiếu phù hợp. Để lấy/tạo Logger cho mã ứng dụng, nên dùng:

~~~java
Logger logger = Logger.getLogger("com.example.payment");
~~~

**Không nhầm LogManager.getLogger với Logger.getLogger.** Một cái là tra cứu registry, cái còn lại là API thuận tiện để lấy hoặc tạo Logger tên tương ứng.

### 4.4. getLoggerNames()

Liệt kê tên Logger hiện đang được quản lý:

~~~java
import java.util.Enumeration;
import java.util.logging.LogManager;

Enumeration<String> names = LogManager.getLogManager().getLoggerNames();
while (names.hasMoreElements()) {
    System.out.println(names.nextElement());
}
~~~

Đây là đoạn mã trong một phương thức, chưa có main. Kết quả có thể gồm root với tên rỗng và các Logger do JDK/thư viện/ứng dụng tạo. Registry không phải danh sách bất biến mọi class trong project: một số Logger có thể được giải phóng nếu không còn được giữ tham chiếu mạnh. Không dùng số lượng tên Logger để suy ra số request hay số business service.

### 4.5. addLogger(Logger)

Đăng ký một Logger được tạo thủ công vào LogManager. Nếu đã có Logger khác cùng tên trong registry, addLogger có thể **trả false**. Đa số code ứng dụng không cần gọi phương thức này vì **Logger.getLogger(name)** đã thực hiện quy trình thông thường.

Việc tự tạo nhiều Logger cùng tên có thể gây ra quan hệ registry/cấu hình khó hiểu. Chỉ dùng addLogger khi có nhu cầu quản lý Logger chuyên biệt và hiểu hợp đồng của API.

### 4.6. readConfiguration và reset

Các phương thức đáng chú ý:

- **readConfiguration()**: đọc lại cấu hình qua cơ chế nguồn cấu hình được LogManager lựa chọn.
- **readConfiguration(InputStream)**: đọc cấu hình properties từ luồng do ứng dụng cung cấp.
- **reset()**: đặt lại trạng thái logging, bao gồm việc loại và đóng các Handler đang có, đồng thời đưa level về trạng thái reset theo quy tắc của JUL.

Các thao tác này có ảnh hưởng **toàn hệ thống JUL của JVM**. Không gọi trong mỗi request nghiệp vụ để thử “làm mới logging”.

### 4.7. updateConfiguration và listener

Các JDK hiện đại có **updateConfiguration(...)** để áp dụng cấu hình mới thông qua quy tắc hợp nhất/ánh xạ giá trị property. LogManager cũng cung cấp **addConfigurationListener** và **removeConfigurationListener** cho thành phần cần biết lúc cấu hình thay đổi.

Những API đó hữu ích cho quản trị cấu hình động nhưng cần hiểu chính xác hợp đồng của JDK đang chạy. **Listener không tự biến file thành một nguồn được watch liên tục.** Ứng dụng vẫn phải quyết định khi nào update/reload và xử lý lỗi. Nếu ứng dụng nhỏ chỉ cần console/file và level cố định, một file cấu hình khởi động thường là đủ.

## 5. Cấu hình JUL được nạp từ đâu?

### 5.1. File mặc định của JDK

Trong JDK hiện đại (Java 9+), cấu hình mặc định thường nằm ở:

~~~text
<JAVA_HOME>/conf/logging.properties
~~~

Các JDK cũ có cách tổ chức thư mục khác. Ứng dụng không cần sửa file cấu hình của chính JDK để thay đổi logging; có thể cung cấp một file riêng cho ứng dụng.

### 5.2. java.util.logging.config.file

Khi khởi động JVM, có thể chỉ định file logging của ứng dụng:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Lệnh minh họa này giả định đã có class **com.example.Main** trong thư mục **out** và một file **logging.properties** được tìm thấy theo working directory tương ứng. Nó không phải lệnh chạy chương trình LogManagerDemo ở mục 7.

**Cần đặt property lúc khởi động**, trước khi LogManager được khởi tạo. Nếu một thư viện dùng Logger trong giai đoạn bootstrap, việc set property muộn hơn không có nghĩa tất cả thành phần tự động đọc lại file. Sử dụng đường dẫn tuyệt đối hoặc working directory được kiểm soát để tránh đọc nhầm file.

### 5.3. java.util.logging.config.class

JUL cũng hỗ trợ chỉ định một class cấu hình chuyên biệt qua **java.util.logging.config.class** trong quá trình khởi tạo. Cơ chế này dành cho cấu hình nâng cao, có quy tắc ưu tiên với cách nạp từ file. Không giả định config.file và config.class sẽ tự hợp nhất không điều kiện; hãy chọn một nguồn bootstrap rõ ràng.

### 5.4. Đọc trực tiếp InputStream

Bên trong chương trình có thể gọi:

~~~java
LogManager manager = LogManager.getLogManager();
manager.readConfiguration(inputStream);
~~~

Mảnh code này giả định **inputStream** là luồng đang mở chứa nội dung Java properties; không phải chương trình chạy độc lập. Ví dụ mục 7 dùng ByteArrayInputStream để người học không cần chuẩn bị file.

Cẩn thận: **readConfiguration** có thể đặt lại cấu hình cũ và đóng Handler đang hoạt động. Nó phù hợp cho bootstrap được kiểm soát hoặc một cơ chế reload đã được thiết kế, không phải thay một setting đơn lẻ tùy hứng.

## 6. Nội dung của logging.properties

Ví dụ:

~~~properties
# Root logger level
.level = INFO

# Output destination for root
handlers = java.util.logging.ConsoleHandler

# Console handler settings
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# A named logger can be more verbose
com.example.payment.level = FINE
~~~

Ý nghĩa:

- **.level = INFO**: root Logger có level INFO.
- **handlers = ...ConsoleHandler**: cấu hình Handler cho root.
- **ConsoleHandler.level = INFO**: ConsoleHandler có ngưỡng INFO.
- **ConsoleHandler.formatter = ...SimpleFormatter**: định dạng output.
- **com.example.payment.level = FINE**: Logger có tên đó được cấu hình FINE; Logger con kế thừa nếu không đặt level riêng.

**Bẫy rất phổ biến:** payment Logger nhận FINE nhưng ConsoleHandler ở INFO nên **record FINE vẫn không hiển thị ở console**. Nếu muốn xuất FINE trên Handler này (và không có filter chặn), phải đổi:

~~~properties
java.util.logging.ConsoleHandler.level = FINE
~~~

Không nhất thiết phải đặt root thành FINE nếu Logger con có level FINE riêng và chuyển record đến Handler của root; JUL không thực hiện kiểm tra lại level của từng Logger cha trên đường truyền record. Tuy nhiên Handler/Filter và useParentHandlers vẫn quyết định đầu ra thực tế.

### 6.1. Các level chuẩn

| Level | Cách dùng thường gặp |
| --- | --- |
| SEVERE | Sự cố nghiêm trọng |
| WARNING | Bất thường cần chú ý |
| INFO | Sự kiện vận hành |
| CONFIG | Thông tin cấu hình |
| FINE, FINER, FINEST | Chi tiết chẩn đoán |
| OFF | Chặn record thông thường ở điểm ngưỡng được đặt |
| ALL | Cho phép mọi mức thông thường ở điểm ngưỡng được đặt |

OFF ở Logger cha **không nhất thiết tắt** Logger con đã có level riêng; ALL ở Logger **không ép** Handler INFO in record FINE.

### 6.2. Ví dụ cấu hình FileHandler

~~~properties
java.util.logging.FileHandler.pattern = logs/app-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

Những property này **chỉ mô tả cách FileHandler hoạt động nếu Handler được tạo/gắn**. Chúng không tự tạo file khi pipeline không sử dụng FileHandler. Hãy chuẩn bị thư mục **logs/** và quyền ghi, kiểm soát file rotation, retention và xử lý khi disk đầy.

### 6.3. Định dạng properties

File cấu hình JUL dùng cú pháp Java properties, có key/value, dòng comment mở đầu bằng **#** hoặc **!**. Nội dung được nạp theo cơ chế Properties truyền thống. Đặc biệt, luồng **InputStream** có quy tắc giải mã dữ liệu khác với việc đọc text UTF-8 tùy ý; các property kỹ thuật trong ví dụ chỉ dùng ASCII. Khi có Unicode trong config, hãy kiểm chứng cách escape/đọc theo đúng API và JDK.

Encoding của cấu hình và encoding của **message log** là hai mối quan tâm khác nhau. Console, file và collector còn có charset/encoder riêng để bảo toàn tiếng Việt hoặc ký tự Unicode.

## 7. Ví dụ Java 17+ chạy độc lập: nạp cấu hình bằng LogManager

Chương trình có thể chạy chỉ với JDK. Ta sẽ:

1. Tạo cấu hình trong bộ nhớ: root **WARNING**, Logger **demo.billing** ở **FINE**.
2. Nạp vào **LogManager.readConfiguration(InputStream)**.
3. Lấy Logger, dùng Handler riêng chỉ nhận INFO trở lên.
4. Quan sát **getProperty**, **getLogger**, **getLevel**, **isLoggable** và đầu ra.
5. Dọn Handler đã gắn khi kết thúc demo.

Tạo tệp **LogManagerDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogManagerDemo {
    public static void main(String[] args) throws Exception {
        String config = ".level=WARNING\n"
                + "demo.billing.level=FINE\n";

        LogManager manager = LogManager.getLogManager();
        try (ByteArrayInputStream in =
                     new ByteArrayInputStream(config.getBytes(StandardCharsets.ISO_8859_1))) {
            manager.readConfiguration(in);
        }

        Logger logger = Logger.getLogger("demo.billing");
        logger.setUseParentHandlers(false);
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName() + " " + record.getMessage());
                }
            }
            @Override public void flush() { System.out.flush(); }
            @Override public void close() { flush(); }
        };
        handler.setLevel(Level.INFO);
        logger.addHandler(handler);

        try {
            System.out.println("manager-property=" + manager.getProperty("demo.billing.level"));
            System.out.println("logger-level=" + logger.getLevel().getName());
            System.out.println("root-level=" + manager.getLogger("").getLevel().getName());
            System.out.println("same-logger=" + (manager.getLogger("demo.billing") == logger));
            System.out.println("fine-allowed-by-logger=" + logger.isLoggable(Level.FINE));
            logger.fine("billing.debug");
            logger.info("billing.started");
            logger.warning("billing.retry");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 LogManagerDemo.java
java LogManagerDemo
~~~

**stdout đã kiểm chứng bằng biên dịch và chạy:**

~~~text
manager-property=FINE
logger-level=FINE
root-level=WARNING
same-logger=true
fine-allowed-by-logger=true
INFO billing.started
WARNING billing.retry
~~~

### 7.1. Vì sao có đúng các dòng đó?

- **manager-property=FINE**: property demo.billing.level được nạp thành công.
- **logger-level=FINE**: Logger được cấu hình theo tên.
- **root-level=WARNING**: root mang level WARNING từ cấu hình .level.
- **same-logger=true**: manager.getLogger tra ra cùng đối tượng Logger đang được giữ tham chiếu.
- **fine-allowed-by-logger=true**: Logger ở FINE cho phép mức FINE ở tầng của nó.
- **billing.debug không xuất hiện**: Handler ở INFO loại FINE.
- **billing.started** và **billing.retry** xuất hiện vì INFO/WARNING qua được cả Logger và Handler.

Đừng kết luận Manager làm mất FINE: trong trường hợp này Logger đã cho phép, nhưng Handler lọc tại điểm xuất.

### 7.2. Vì sao dùng Handler minh họa?

**ConsoleHandler** mặc định của JUL thường dùng **stderr** và formatter có timestamp/nội dung phụ thuộc môi trường. Handler nhỏ trong demo cố ý in **stdout** với format cố định để kiểm chứng output. **setUseParentHandlers(false)** tránh một record bị xuất thêm qua root Handler.

Handler ở đây chỉ dùng để học, không phải một sink hoàn chỉnh cho sản xuất: chưa có chính sách xử lý lỗi I/O, concurrency hay backpressure. Trong ứng dụng thực, dùng Handler được cung cấp sẵn hoặc backend phù hợp.

## 8. Nạp lại cấu hình, cập nhật cấu hình và reset

Cần phân biệt ba thao tác khác nhau.

### 8.1. Nạp lần đầu

Khi JVM lần đầu khởi tạo logging, LogManager đọc cấu hình theo nguồn đã chọn. Nếu cần file riêng, nên đặt **java.util.logging.config.file** khi khởi động. Những thư viện tạo Logger trước main() có thể khiến logging khởi tạo sớm, vì vậy đừng trông chờ set system property ở cuối bootstrap.

### 8.2. readConfiguration(...) thay cấu hình hiện hành

Khi gọi **readConfiguration(InputStream)**, JUL áp dụng tập cấu hình mới, và theo hợp đồng của nó có thể **reset cấu hình trước đó**, bao gồm loại/đóng Handler đã đăng ký.

Một hệ thống có thể đang ở trạng thái:

~~~text
Logger demo.billing
  +-- Console Handler
  +-- File Handler
~~~

Sau reload, danh sách Handler có thể không còn như trước. Nếu file mới không tạo/gắn lại đúng đích, log có thể biến mất dù Logger vẫn tồn tại.

**Đã kiểm chứng trên chương trình Java:** Một Logger đã được gắn ConsoleHandler và đặt FINE, sau readConfiguration với property **demo.reload.level=SEVERE**, có **logger.getLevel() == SEVERE** và **logger.getHandlers().length == 0**. Điều này chứng minh việc reload ảnh hưởng cả cấp độ lẫn Handler ở ví dụ được kiểm thử.

Không chỉ sửa file và gọi readConfiguration mỗi request; phải thiết kế quy trình reload có kiểm chứng và kiểm soát thời điểm thao tác.

### 8.3. updateConfiguration(...) hợp nhất theo chính sách

**updateConfiguration** trong các JDK hiện đại cho phép cập nhật properties dựa trên hàm ánh xạ/merge do bên gọi cung cấp. Nó thích hợp hơn khi cần quản lý cấu hình động phức tạp, nhưng không phải một lời hứa rằng thay đổi sẽ không ảnh hưởng Handler hoặc trạng thái hiện tại.

Cần xác định rõ ý nghĩa khi key xuất hiện, biến mất hoặc bị thay đổi; thử cả level, handler, formatter, file path và các record đang được ghi. Kiểm tra hợp đồng API của JDK mục tiêu trước khi triển khai.

### 8.4. reset()

**LogManager.reset()** dùng để đưa trạng thái logging về trạng thái reset theo quy tắc JUL, loại và đóng những Handler đã có. Nó ảnh hưởng logging trên phạm vi JVM. Không dùng reset để tạm tắt log của một package duy nhất.

Nếu chỉ muốn bật chi tiết cho một module, có thể thay level của Logger đó hoặc cấu hình theo package. Nếu muốn tắt một đích xuất, phải kiểm soát Handler/routing tương ứng.

### 8.5. Sửa file không bằng thay Logger đang chạy

Hai thao tác sau khác nhau:

~~~java
Logger.getLogger("com.example").setLevel(Level.WARNING);
~~~

và sửa dòng trong file:

~~~properties
com.example.level = WARNING
~~~

Thao tác thứ nhất thay trạng thái runtime của Logger. Thao tác thứ hai chỉ thay nội dung file; muốn ứng dụng nhận thay đổi, phải có bước nạp lại hoặc khởi động theo chính sách. Lệnh setLevel trong code cũng có thể bị ghi đè bởi một lần nạp lại cấu hình sau đó.

## 9. Logger, registry và tính ổn định của tên

LogManager quản lý Logger bằng **tên**, vì thế tên cần chính xác. Nếu cấu hình:

~~~properties
com.example.payment.level = FINE
~~~

nhưng code gọi Logger có tên **com.example.payments** thì property không tác động đúng đối tượng dự định.

Đề xuất đặt tên:

- Dùng **Class.getName()** cho Logger của một class.
- Dùng tên package/module ổn định nếu muốn điều khiển cả nhóm.
- Không nhét requestId, userId, transactionId hoặc thời gian chạy vào tên Logger.
- Đưa correlation metadata vào event hoặc logging context phù hợp.

Một Logger không có level riêng có thể kế thừa mức từ ancestor, nhưng **getLevel() == null** không cho biết trực tiếp effective level là gì. Dùng **isLoggable(level)** để hỏi liệu Logger hiện tại có nhận một level cụ thể không; sau đó vẫn cần kiểm tra Handler/filter để biết record có ra đích.

### 9.1. Registry không phải nhật ký lịch sử

**getLoggerNames()** phản ánh các Logger đang được LogManager theo dõi. Nó không liệt kê mọi Logger từng được tạo trong quá khứ và không đại diện danh sách toàn bộ file Java. LogManager có thể chỉ giữ tham chiếu yếu tới một số Logger; code nên giữ tham chiếu Logger mà nó thực sự cần.

### 9.2. Parent handlers và log trùng

Ví dụ Logger con được gắn ConsoleHandler riêng nhưng **useParentHandlers=true**; record cũng đi đến Handler của cha, có thể tạo hai dòng. Muốn có pipeline riêng, có thể đặt:

~~~java
logger.setUseParentHandlers(false);
~~~

Nhưng **chỉ tắt parent handlers khi có một đích khác đã được cấu hình**. Nếu Logger không có Handler nào và cũng không forward lên cha, có thể không còn output. Cần kiểm tra **logger.getHandlers()**, **getUseParentHandlers()** và Handler của ancestor trước khi chỉnh.

## 10. Mức logging và khả năng quan sát

Các mức như SEVERE, WARNING, INFO, FINE được so với ngưỡng của Logger. Sau đó Handler cũng có level/filter.

Ví dụ:

| Logger level | Handler level | Record INFO | Record FINE |
| --- | --- | --- | --- |
| INFO | INFO | Có thể xuất | Bị Logger loại |
| FINE | INFO | Có thể xuất | Bị Handler loại |
| FINE | FINE | Có thể xuất | Có thể xuất |
| OFF | ALL | Không qua Logger | Không qua Logger |
| ALL | OFF | Bị Handler loại | Bị Handler loại |

Bảng giả định không có Filter bổ sung, Logger/Handler được nối đúng và đích ghi hoạt động. Trong hệ thực tế, file, console hoặc collector còn có thể lỗi, bị giới hạn lưu lượng hoặc bị mất dữ liệu ở pipeline sau JVM.

**Một log không xuất hiện không có nghĩa LogManager chưa nạp file.** Cần chứng minh từng bước: property, Logger, level, Filter, Handler, Formatter, destination.

## 11. Tùy chỉnh LogManager của hệ thống

Một tình huống nâng cao là thay implementation LogManager qua JVM system property:

~~~text
-Djava.util.logging.manager=com.example.logging.CustomLogManager
~~~

Đây là ví dụ về hình thức tham số. Nó không chạy được nếu thiếu class hợp lệ, cơ chế nạp class và implementation đúng hợp đồng JDK. Việc chọn custom LogManager thường phải xảy ra **trước khi logging khởi tạo**.

Chỉ cân nhắc custom LogManager nếu nền tảng/framework/container có yêu cầu đặc biệt về quản lý logging ở phạm vi JVM. Nó **không phải** lựa chọn mặc định để đổi format JSON, thêm timestamp, ghi file hoặc đổi đích gửi. Những thay đổi đó thường thuộc Handler/Formatter/encoder/collector.

Các vấn đề cần cân nhắc khi tùy biến:
- Thứ tự khởi tạo LogManager và các lớp logging khác.
- Class loader/module path của custom implementation.
- Sự tương thích với thư viện đang sử dụng JUL.
- Cách xử lý reload, reset, Handler và shutdown.
- Kiểm thử riêng biệt để tránh làm ảnh hưởng logger của môi trường test.

## 12. LogManager có điều khiển mọi framework logging không?

Không. **LogManager** thuộc **java.util.logging**. Những hệ thống khác có cơ chế cấu hình riêng.

| API/stack phát log | Điều nên kiểm tra |
| --- | --- |
| java.util.logging.Logger | LogManager, JUL Logger, Handler, Filter |
| org.slf4j.Logger | SLF4J provider và backend thực tế |
| Logback | Logger context, appender/encoder/filter của Logback |
| Log4j 2 | Cấu hình Log4j 2, logger config, appender |
| System.Logger của JDK | LoggerFinder/provider hiện hành |

**SLF4J** là facade; nó thường định tuyến tới một provider/backend như Logback hoặc giải pháp khác. Sửa file JUL logging.properties không mặc nhiên thay level của Logback. **Log4j 2** có API và implementation khác JUL.

JDK còn có **System.Logger** và cơ chế **System.LoggerFinder**. Tùy runtime/provider, việc định tuyến có thể liên quan JUL, nhưng không nên giả định LogManager luôn chi phối mọi System.Logger khi có provider tùy biến.

Nếu một thư viện dùng JUL và ứng dụng chính dùng SLF4J, có thể cần **bridge**. Phải kiểm soát hướng bridge để không tạo vòng lặp như JUL → SLF4J → JUL, và kiểm tra có bị xuất trùng record hay không. Không cài nhiều adapter chỉ để “chắc chắn mọi log được gom”.

## 13. Những rủi ro khi thao tác cấu hình

### 13.1. Thời điểm khởi tạo

Một thư viện có thể sử dụng Logger trong static initializer hoặc giai đoạn framework bootstrap. Nếu đặt **java.util.logging.config.file** sau đó, LogManager có thể đã đọc nguồn cũ. Chính sách tốt là thiết lập cấu hình ngay ở JVM startup, rồi kiểm chứng giá trị trên Logger thật.

### 13.2. Vòng đời Handler

**readConfiguration/reset** có thể tháo và đóng Handler đang tồn tại. Khi ứng dụng tạo FileHandler hoặc handler mạng, reload cần xử lý:

- Handler cũ đã flush/close đúng cách chưa?
- Handler mới có được tạo và gắn đúng Logger?
- File path có quyền ghi và thư mục tồn tại?
- Có khoảng thời gian mất output giữa hai cấu hình?
- Có bị trùng record nếu hai Handler được gắn đồng thời?
- Nếu sink lỗi hoặc đầy, có cơ chế báo lỗi/backpressure phù hợp?

Không triển khai hot reload thiếu test rồi dựa vào may mắn.

### 13.3. Đồng thời và cấu hình toàn cục

LogManager là trạng thái chung. Các thread có thể đang ghi record khi cấu hình thay đổi. Việc thay level/Handler giữa lúc chạy làm output chịu ảnh hưởng theo thời điểm xử lý; không nên đòi một “ảnh chụp cấu hình nguyên tử” tùy ý nếu backend không bảo đảm điều đó.

Một test gọi **reset()** hoặc **readConfiguration** có thể làm ảnh hưởng test khác nếu chạy song song cùng JVM. Bài test thay cấu hình toàn cục nên được chạy tách JVM hoặc quản lý lifecycle thật rõ ràng.

### 13.4. Hiệu năng và chi phí

Bật FINE/FINER/FINEST rộng có thể tăng lượng log rất lớn, kéo theo CPU, I/O, bộ nhớ, network, dung lượng lưu trữ và độ trễ. Handler đồng bộ có thể chặn luồng nghiệp vụ nếu đích ghi chậm. Collector/async pipeline có thể drop record nếu quá tải.

Chọn level theo môi trường và phạm vi package. Đừng dùng LogManager như kho lưu thông tin nghiệp vụ hoặc thay chính sách tracing/metrics.

### 13.5. Dữ liệu nhạy cảm

Một record ở mức FINE có thể chứa tham số truy vấn, request body hoặc exception message có thông tin riêng tư. Bật level chi tiết có thể làm lộ dữ liệu trước đó chưa được xuất. Không ghi token, password, API key, session cookie, private key hoặc payload nhạy cảm ở bất kỳ level nào. Kiểm soát ngay từ nơi tạo message và tất cả sink.

## 14. Chẩn đoán lỗi cấu hình LogManager

### Trường hợp A: Sửa logging.properties nhưng level không đổi

Kiểm tra lần lượt:

1. **java.util.logging.config.file** được đặt ở JVM startup chưa?
2. Đường dẫn file có đúng working directory và quyền đọc không?
3. Có **java.util.logging.config.class** hoặc custom manager ảnh hưởng nguồn nạp?
4. Property key có đúng tên Logger không, ví dụ **com.example.payment** hay **com.example.payments**?
5. Có code gọi **setLevel** sau khi nạp file?
6. Có đoạn **readConfiguration** khác đang thay cấu hình?
7. Ứng dụng thật sự dùng JUL hay dùng SLF4J/Logback/Log4j 2?

Có thể đối chiếu **manager.getProperty(key)**, **logger.getLevel()** và **logger.isLoggable(Level.FINE)** trong môi trường chẩn đoán có kiểm soát.

### Trường hợp B: getProperty trả FINE nhưng không thấy FINE

Kiểm tra tiếp **Handler level**, Logger Filter, Handler Filter, parent handlers, danh sách Handler thực sự gắn với Logger và đích đầu ra. **getProperty** không phải bằng chứng record đã được in.

### Trường hợp C: Sau reload không còn log

Nếu ứng dụng dùng **readConfiguration**, có thể Handler cũ bị tháo/đóng. Kiểm tra số Handler trước/sau trong môi trường test và cơ chế tạo lại Handler theo cấu hình. Đừng gọi reload lặp lại khi chưa biết liệu pipeline đã được khôi phục.

### Trường hợp D: Log xuất hai lần

Thường do Handler gắn ở cả logger con và cha, **useParentHandlers=true**, hoặc có hai bridge/provider cùng ghi. Xác định đúng các Handler và namespace; không tắt parent handlers bừa bãi.

### Trường hợp E: manager.getLogger trả null

Điều này hợp lệ nếu Logger chưa được đăng ký hoặc không còn tham chiếu phù hợp. Mã ứng dụng cần Logger nên gọi **Logger.getLogger(name)** và giữ tham chiếu; công cụ kiểm kê phải xử lý null.

### Trường hợp F: Custom class không được nạp

Kiểm tra classpath/module path, tên class đầy đủ, hợp đồng khởi tạo, quyền truy cập, thời điểm JVM khởi tạo logging và thư viện hỗ trợ. Không tự suy ra lỗi quyền ghi file khi chưa có thông báo lỗi cụ thể.

## 15. Kiểm thử LogManager

Một bộ kiểm thử tập trung vào **hành vi** hơn là chỉ đọc chuỗi properties:

| Điều cần test | Kiểm tra hữu ích |
| --- | --- |
| Nạp properties | manager.getProperty(key) trả giá trị kỳ vọng |
| Đăng ký Logger | manager.getLogger(name) tìm đúng instance đã tạo |
| Cấu hình level | logger.getLevel(), isLoggable(level) |
| Kế thừa level | Logger con level null có effective level phù hợp |
| Chuyển tiếp đến parent | getUseParentHandlers và output thực tế |
| Handler filtering | Handler INFO loại record FINE dù Logger FINE |
| Format output | Dòng log đúng level/message/Throwable cần thiết |
| Reload cấu hình | Logger/Handler thay đổi đúng, sink vẫn còn hoạt động |
| File/network failure | Error handling và fallback phù hợp, không recursion |
| Shutdown | Flush/close tài nguyên đúng và không mất dữ liệu ngoài policy |

**Không dùng stdout của ConsoleHandler làm tiêu chí tuyệt đối**: ConsoleHandler JUL mặc định thường xuất stderr và SimpleFormatter có timestamp, class/source, exception. Trong ví dụ mục 7, Handler kiểm soát stdout để output có thể so sánh chính xác.

Khi test cấu hình chung, tránh chạy các test reset/reload trong cùng JVM đồng thời với các test nghiệp vụ đang dùng Logger toàn cục.

## 16. Thực hành tự đánh giá

**Bài thực hành 1 — Đổi Logger level.** Trong demo, đổi property **demo.billing.level=FINE** thành **demo.billing.level=WARNING**. Chạy lại. INFO có bị chặn không? WARNING có còn xuất? Giải thích ngưỡng Logger và Handler.

**Bài thực hành 2 — Đổi Handler level.** Giữ Logger FINE nhưng đặt Handler FINE. Quan sát **billing.debug** xuất hiện; đổi Handler trở lại INFO thì nó biến mất. Kết quả thể hiện rõ hai ngưỡng độc lập.

**Bài thực hành 3 — Dùng file ngoài.** Tạo logging.properties và chạy một class Java có Logger cùng tên bằng **-Djava.util.logging.config.file=...**. So sánh nội dung LogManager property với file đã nạp.

**Bài thực hành 4 — Reload trong JVM test.** Gắn Handler vào Logger, ghi lại **getHandlers().length**, gọi readConfiguration với mức khác, rồi xem danh sách Handler và level sau reload. Giải thích tại sao chương trình production phải quan tâm vòng đời sink.

**Bài thực hành 5 — Phân biệt framework.** Trong một ứng dụng có thư viện dùng JUL và thành phần dùng SLF4J, mô tả LogManager quản lý phần nào; xác định nhu cầu bridge và nguy cơ vòng lặp.

### Câu hỏi và đáp án

**1. LogManager có phải Handler không?** Không. Nó quản lý cấu hình và Logger registry; Handler xử lý và ghi record tới destination.

**2. getLogger(name) có luôn tạo Logger mới?** Không. LogManager.getLogger là tra cứu Logger đang đăng ký; mã ứng dụng thường dùng Logger.getLogger.

**3. Root Logger được cấu hình bằng property nào?** **.level**, vì root Logger có tên rỗng.

**4. getProperty trả FINE có đồng nghĩa console xuất FINE?** Không. Handler, Filter và route tới output cũng phải cho phép.

**5. Tại sao Logger con level null vẫn log được?** Vì nó kế thừa effective level của ancestor; null không có nghĩa OFF.

**6. Sửa file properties có tự reload?** Không mặc định. Cần khởi động hoặc gọi cơ chế nạp lại có chủ đích.

**7. Tại sao readConfiguration có thể làm mất log?** Vì có thể reset cấu hình và loại/đóng Handler cũ mà đích mới chưa được gắn.

**8. Có nên gọi reset cho mỗi request?** Không. Nó tác động logging toàn JVM, kể cả request khác.

**9. Muốn đổi formatter sang JSON có cần thay LogManager?** Thường không; hãy cấu hình Formatter/encoder, Handler hoặc backend thích hợp.

**10. LogManager kiểm soát mọi logger của SLF4J hay Log4j 2?** Không mặc nhiên. Cần kiểm tra provider/backend và bridge thực tế.

## 17. Những điều cần nhớ

**LogManager là điểm quản lý cấu hình của JUL ở phạm vi JVM**, còn Logger phát bản ghi và Handler xuất ra đích. Một file **logging.properties** giúp cấu hình tập trung theo tên Logger, root Logger và các Handler. **getProperty** giúp xem giá trị cấu hình; **getLogger** tra registry; **readConfiguration** nạp cấu hình và có thể ảnh hưởng vòng đời Handler.

Để chẩn đoán log thiếu, hãy đi theo đường **property → logger name/level → filter → handler/parent handlers → output**. Để reload an toàn, hãy kiểm chứng cả level lẫn các tài nguyên ghi log được tạo lại đúng, và tránh thay cấu hình toàn cục khi các luồng khác đang xử lý nếu chưa thiết kế hợp đồng vận hành rõ ràng.
