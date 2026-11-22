# Cấu hình mặc định của hệ thống logging trong Java

## 1. Cấu hình mặc định là gì?

**Cấu hình logging mặc định (default logging configuration)** là tập quy tắc mà môi trường chạy áp dụng khi chương trình không chỉ định cấu hình riêng, hoặc khi một framework chủ động cung cấp cấu hình khởi đầu. Tập quy tắc này quyết định những câu hỏi rất thực tế:

- **Log nào được nhận?** Mức INFO, DEBUG, WARN, ERROR, hay các mức tương đương của từng thư viện.
- **Log đi đâu?** Console, file, appender khác hoặc không đi đâu nếu không có logging provider.
- **Log trông thế nào?** Timestamp, mức độ, tên logger, thread, message, exception.
- **Ai quyết định?** JDK, backend logging, starter/framework, file cấu hình, tham số JVM hoặc mã thay đổi cấu hình lúc chạy.
- **Nếu không có file cấu hình thì sao?** Từng backend có chính sách khởi tạo riêng; không có một “mặc định của Java” áp dụng cho tất cả.

Bài học tập trung vào **cấu hình mặc định đang có hiệu lực** trong ứng dụng Java, cách nhận biết nó, lý do một dự án có thể thấy log khác dự án khác và cách thay đổi an toàn khi cần. Đừng mặc nhiên cho rằng mọi ứng dụng đều in INFO lên console hoặc đều tự ghi file.

### Phân biệt ba trường hợp

1. **Không viết file cấu hình riêng:** hệ thống vẫn có thể tự khởi tạo logging với cấu hình mặc định do JDK, backend hoặc framework cung cấp.
2. **Có file cấu hình nhưng không đặt mọi thuộc tính:** những giá trị không khai báo được lấy từ default của từng thành phần, hoặc từ cấu hình kế thừa.
3. **Thiếu implementation/provider của logging API:** lời gọi API có thể không được ghi ra đâu cả, như trường hợp dùng SLF4J mà không có provider tương thích.

Đây là ba tình huống khác nhau. Chỉ nhìn thấy một dòng log hay không thấy dòng nào chưa đủ để kết luận nguyên nhân.

## 2. Các lớp quyết định cấu hình logging

Trong Java, nên phân tích từ API đến đích ghi:

~~~text
Ứng dụng Java
  │
  ├── java.util.logging (JUL) của JDK ── LogManager / Handler
  │
  └── SLF4J API (nếu dùng)
       │
       └── provider/backend: Logback, Log4j2 adapter, JUL adapter, ...
                                      │
                                      ▼
                         Logger level / filter
                                      │
                                      ▼
                         Appender / Handler / Layout
                                      │
                                      ▼
                             Console / File / Sink
~~~

- **JUL** nằm trong module **java.logging** của JDK, có **LogManager**, **Logger**, **Handler** và **Formatter**.
- **SLF4J** chủ yếu là API/facade. Nó không tự áp đặt một bộ cấu hình backend chung cho mọi ứng dụng.
- **Logback** là backend logging thường kết hợp với SLF4J; có cơ chế nạp file hoặc cấu hình fallback khi không tìm thấy file.
- **Log4j2** gồm API và implementation (Log4j Core); cần kiểm tra cả implementation có trên runtime classpath và configuration thực tế.
- **Spring Boot** có lớp cấu hình logging riêng. Khi dùng starter mặc định, Boot thường khởi tạo Logback và cung cấp thiết lập console/level. Vì vậy hành vi mặc định của ứng dụng Boot khác hành vi fallback của Logback chạy độc lập.

Một ứng dụng có thể chứa nhiều API logging do dependency khác nhau kéo vào. Bridge/adapter có thể chuyển chúng về một backend, nhưng nếu có nhiều provider hoặc adapter không tương thích, kết quả không nhất quán hoặc xuất hiện cảnh báo. Xác định **backend cuối cùng** mới biết nơi áp dụng level, pattern và destination.

## 3. Bảng so sánh mặc định thường gặp

Các mục dưới đây áp dụng khi dùng đúng triển khai nêu tên, không đặt cấu hình tùy chỉnh hoặc biến môi trường đặc biệt. Phiên bản và framework tích hợp có thể thay đổi hành vi.

| Môi trường | Mặc định thường gặp khi không cấu hình riêng | Điều quan trọng cần nhớ |
| --- | --- | --- |
| **JDK 17 – java.util.logging (JUL)** | Nạp thiết lập từ file **conf/logging.properties** của JDK; cấu hình JDK phổ biến có root logger và console handler, mức INFO. | File cấu hình JDK có thể được nhà phân phối/systems admin chỉnh. Handler cũng lọc level riêng. |
| **SLF4J 2.x chỉ có API, không provider** | Phát cảnh báo thiếu provider rồi dùng NOP logger, bỏ qua sự kiện log. | Không phải “SLF4J mặc định là console INFO”. |
| **Logback Classic độc lập, không tìm thấy cấu hình** | Fallback **BasicConfigurator**: ConsoleAppender ở root, root level **DEBUG**. | Khác default do Spring Boot cung cấp. |
| **Log4j Core không tìm thấy cấu hình** | Fallback **DefaultConfiguration**: console, root level thông thường **ERROR**. | Giá trị có thể thay đổi qua property **log4j2.level**. |
| **Spring Boot với logging starter mặc định** | Thường dùng Logback; in INFO, WARN, ERROR lên console, không tự ghi file nếu chưa cấu hình. | Boot áp dụng cấu hình của chính Boot; không suy ra từ BasicConfigurator. |

**Chú ý:** tên mức độ không hoàn toàn giống nhau. JUL dùng **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**; Logback dùng **ERROR, WARN, INFO, DEBUG, TRACE**; Log4j2 còn có **FATAL**. Khi xem bảng, đừng coi FINE và DEBUG hay WARNING và WARN là những class/enum giống hệt nhau.

## 4. Mặc định của java.util.logging (JUL) trong JDK

JUL có sẵn trong JDK nên ví dụ không cần Maven, Gradle hay thư viện ngoài. JDK đi kèm một file cấu hình chuẩn thường nằm tại:

~~~text
<JAVA_HOME>/conf/logging.properties
~~~

Với JDK 17 phổ biến, file này thiết lập một **ConsoleHandler** cho root logger và dùng mức INFO. **ConsoleHandler** ghi sang **System.err**, không phải System.out, và thông thường dùng **SimpleFormatter**. Các giá trị cụ thể vẫn là dữ liệu cấu hình của bản JDK đang chạy, không phải bất biến của ngôn ngữ Java.

### 4.1. Java 17: quan sát cấu hình thực tế đang có hiệu lực

Tạo file **DefaultLoggingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.Logger;

public class DefaultLoggingDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("course.logging.DefaultLoggingDemo");
        Logger root = LogManager.getLogManager().getLogger("");

        System.out.println("logger-level="
                + (log.getLevel() == null
                    ? "<inherited>" : log.getLevel().getName()));
        System.out.println("root-level="
                + (root.getLevel() == null
                    ? "<inherited>" : root.getLevel().getName()));
        System.out.println("INFO-enabled=" + log.isLoggable(Level.INFO));
        System.out.println("FINE-enabled=" + log.isLoggable(Level.FINE));

        for (Handler handler : root.getHandlers()) {
            System.out.println("root-handler="
                    + handler.getClass().getSimpleName()
                    + ", level=" + handler.getLevel().getName());
        }

        log.info("Order was accepted");
        log.fine("Detailed processing data");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DefaultLoggingDemo.java
java DefaultLoggingDemo
~~~

Trên **JDK 17 có cấu hình JUL mặc định thông dụng, không bị ghi đè bởi JVM options hoặc mã ứng dụng**, stdout là:

~~~text
logger-level=<inherited>
root-level=INFO
INFO-enabled=true
FINE-enabled=false
root-handler=ConsoleHandler, level=INFO
~~~

Ngoài ra có một bản ghi **INFO: Order was accepted** trên stderr với thông tin timestamp/logger theo **SimpleFormatter**. Thời gian, định dạng, locale và thứ tự khi gộp stdout/stderr có thể thay đổi nên phần đó không được coi là stdout cố định. Lệnh **log.fine** không tạo dòng log theo cấu hình INFO nói trên.

Nếu output của máy bạn khác, đó chính là điều cần kiểm tra: các default có thể đã bị override.

### 4.2. Logger level và Handler level là hai bộ lọc

Một record chỉ xuất hiện khi nó vượt qua **các tầng lọc liên quan**:

1. Logger phát ra record nếu mức record được cho phép theo effective level của logger.
2. Filter (nếu có) có thể từ chối record.
3. Handler nhận record và lại kiểm tra mức/Filter riêng trước khi xuất.
4. Formatter và stream quyết định biểu diễn, đích hiển thị.

Ví dụ root logger được đặt INFO và ConsoleHandler cũng INFO. Nếu một logger con gọi:

~~~java
// Đoạn minh họa thêm vào ứng dụng đang dùng JUL.
log.setLevel(Level.FINE);
log.fine("Debug detail");
~~~

Logger con đã chấp nhận FINE, nhưng **ConsoleHandler vẫn có thể loại** vì handler đang ở INFO. Sửa mỗi logger level chưa bảo đảm FINE xuất hiện: phải xem cả mức handler và các filter. Ngược lại, đổi handler sang FINE trong khi logger vẫn kế thừa INFO cũng chưa đủ.

### 4.3. Kế thừa mức log

Tên logger JUL thường phân cấp theo dấu chấm, chẳng hạn **course**, **course.orders**, **course.orders.OrderService**. Nếu logger con không được đặt level riêng, **getLevel() trả null** (theo nghĩa không gán mức trực tiếp), và nó lấy effective level từ logger cha thích hợp. Đây không đồng nghĩa việc logger đang bị tắt.

**Root logger** có tên chuỗi rỗng. Đừng dùng **getLevel() == null** để kết luận hệ thống không có default; kiểm tra **isLoggable(level)** và cấu hình cha/handler.

### 4.4. Cách override JUL bằng properties file

Tạo file **logging.properties** riêng cho ứng dụng:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=WARNING
java.util.logging.ConsoleHandler.level=WARNING
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
course.logging.level=FINE
~~~

Chạy từ thư mục chứa file:

~~~bash
java -Djava.util.logging.config.file=logging.properties DefaultLoggingDemo
~~~

File này **thay thế nguồn cấu hình JUL khởi tạo** mà LogManager đọc trong tình huống thông thường. Với ví dụ trên, logger **course.logging** được đặt FINE, nhưng handler root vẫn WARNING; vì vậy log INFO/FINE của chương trình không xuất hiện tại ConsoleHandler. Bạn có thể thay **java.util.logging.ConsoleHandler.level=FINE** để thấy tác động của mức handler; lưu ý root và logger cha vẫn có quy tắc kế thừa riêng.

Vị trí file phải là đường dẫn mà JVM chạy có thể đọc được. Nếu đổi JVM option sau khi JUL đã khởi tạo, điều đó không tự làm toàn hệ thống nạp lại cấu hình; việc reload cần cơ chế của LogManager hoặc lifecycle phù hợp.

## 5. SLF4J: chưa có provider thì không có cấu hình ghi log hữu ích

Giả sử mã ứng dụng sử dụng:

~~~java
// Minh họa cho dự án đã có SLF4J:
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("Order created: {}", orderId);
~~~

Đoạn này là mã minh họa, **không phải một class Java tự biên dịch độc lập**: nó cần SLF4J, class **OrderService** và biến **orderId**.

Với **SLF4J 2.x**, nếu runtime chỉ có **slf4j-api** nhưng không có provider được ServiceLoader nhận diện, SLF4J phát cảnh báo thiếu provider và sử dụng **NOP logger**. Không có dòng INFO nào được xử lý bởi backend dù mã gọi LOG.info thành công. Các provider có thể là Logback Classic, SLF4J Simple hoặc adapter sang JUL/Log4j2; hành vi mặc định phụ thuộc provider được chọn.

Phân biệt:

- **SLF4J API** quyết định cú pháp gọi logger và giao diện chung.
- **Provider/backend** quyết định mức log, appender, encoder, output và cách nạp cấu hình.
- **Bridge** chuyển log từ API khác về backend được chọn khi được cấu hình đúng.
- Một dự án nên kiểm soát số provider/binding tương thích trên runtime classpath; nhiều provider có thể gây cảnh báo hoặc lựa chọn backend không như dự đoán.
- SLF4J 1.7 và SLF4J 2.x có cơ chế tìm backend khác nhau; tránh kết hợp provider cũ với API mới mà không kiểm tra phiên bản.

Cách kiểm tra: xem dependency tree và cảnh báo khởi động, sau đó xác định **backend thực sự đang được sử dụng**. Không cố thay pattern Logback khi ứng dụng chỉ có JUL provider.

## 6. Logback Classic độc lập: khi không có file cấu hình

Logback thường tự tìm cấu hình từ classpath, nổi bật là **logback-test.xml** cho thử nghiệm và **logback.xml** cho ứng dụng. Khi không tìm được cấu hình phù hợp và không có cơ chế khác can thiệp, Logback Classic có fallback **BasicConfigurator** với **ConsoleAppender** gắn vào root và root ở **DEBUG**.

Điều này giải thích vì sao ứng dụng Java thuần dùng SLF4J + Logback có thể thấy DEBUG ngay cả khi bạn chưa viết cấu hình riêng. Tuy nhiên một ứng dụng **Spring Boot** có thể tải cấu hình logging riêng trước đó, nên không nên áp dụng kết luận root DEBUG cho mọi dự án Logback.

Một ví dụ cấu hình tối thiểu, đặt tại **src/main/resources/logback.xml** trong dự án sử dụng Logback:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Từ khi có file này và được nạp đúng, root level được **đặt rõ INFO**; đó là **cấu hình tùy chỉnh**, không còn là fallback BasicConfigurator. Nó có thể khác mặc định cả về level lẫn pattern. Các logger con chưa định nghĩa mức riêng có thể kế thừa level từ root.

Cần nhớ:

- **logback.xml** là tài nguyên trên runtime classpath, không đơn thuần là file nằm đâu đó trong repository.
- Một file **logback-test.xml** trong test runtime classpath có thể làm log khi chạy test khác với chạy ứng dụng.
- Root appender và logger appender có thể gây **log trùng** nếu additivity/kế thừa khiến cùng event đi qua nhiều appender.
- Có thể có nhiều cơ chế cấu hình Logback hơn các tên file phổ biến; nếu hành vi khác kỳ vọng, xem status/configuration được backend thực sự nạp.

## 7. Log4j2: fallback của Log4j Core không giống Logback

Ứng dụng dùng Log4j2 cần phân biệt **Log4j API** với **Log4j Core** hoặc implementation phù hợp. Khi dùng Log4j Core và không có file cấu hình được phát hiện, Core dùng **DefaultConfiguration** và phát thông báo từ status logger. Mức root mặc định thông thường là **ERROR**; console hiển thị các log đạt ngưỡng đó. Thuộc tính **log4j2.level** có thể điều chỉnh mức root của default configuration.

Log4j2 thường tìm những tên cấu hình như **log4j2-test.xml**, **log4j2.xml** và các định dạng/biến thể khác được hỗ trợ. Khi có file cấu hình cụ thể, nội dung file quyết định appender, level, filter và layout; đừng áp dụng quy tắc ERROR fallback một cách máy móc.

Ví dụ **log4j2.xml** tối thiểu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đây là **cấu hình tùy chỉnh** chuyển root sang INFO, chứ không phải đoạn mô tả nguyên trạng DefaultConfiguration. Tên file, vị trí classpath và dependency **log4j-core** phải phù hợp runtime. Tài liệu Log4j2 cho phép chỉ định vị trí file bằng **log4j2.configurationFile**; file mặc định khác nhau theo cơ chế nhận diện và phiên bản.

**Ví dụ so sánh:** cùng lời gọi **logger.info("Started")** có thể xuất hiện trong Logback fallback DEBUG, nhưng không xuất hiện khi Log4j Core đang dùng fallback ERROR. Đó là lý do đầu tiên phải kiểm tra backend trước khi đổi code.

## 8. Spring Boot: “không có logback.xml” vẫn có logging mặc định của Boot

Khi dự án Spring Boot sử dụng logging starter thông thường, Boot thường chọn Logback và tự đưa cấu hình logging vào lúc khởi động. Các đặc điểm mặc định thường thấy:

- Ghi log lên **console**.
- Hiển thị **INFO**, **WARN** và **ERROR**.
- Không tự tạo file log nếu chưa bật thiết lập file output.
- Định dạng console có timestamp, level, process ID, thread name, logger name và message theo phiên bản Boot/cấu hình đang chạy.
- Có thể ghi log từ các thư viện khác qua những bridge được starter thiết lập phù hợp.

Vì vậy một dự án Boot dùng Logback nhưng **không có logback.xml** vẫn có thể chỉ hiện INFO trở lên; nó đang dùng thiết lập mặc định của Boot, không phải fallback DEBUG của Logback độc lập.

### 8.1. Thay đổi ít nhất bằng application.properties

Đặt các dòng sau tại **src/main/resources/application.properties**:

~~~properties
# Muc mac dinh cho phan lon logger
logging.level.root=INFO

# Mo DEBUG cho package cua ung dung khi can dieu tra
logging.level.com.example.orders=DEBUG

# Vi du tuy chon: bat ghi file ben canh console
logging.file.name=logs/application.log
~~~

Đây là **cấu hình tự đặt**, không phải mọi giá trị đều được Boot áp dụng khi dự án chưa cấu hình. Đường dẫn **logs/application.log** là tương đối với working directory hiện hành, nên phải kiểm tra quyền ghi, volume và nơi chạy container. Nếu bỏ dòng **logging.file.name** thì Boot thông thường chỉ ghi console. Tên thuộc tính file output của Boot là **logging.file.name** hoặc **logging.file.path** trong các phiên bản hiện đại; tránh sao chép thuộc tính lỗi thời từ bài hướng dẫn cũ.

Có thể dùng **application.yaml** tương đương:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
  file:
    name: logs/application.log
~~~

Trong các ví dụ, chỉ chọn một hình thức cấu hình chính phù hợp dự án, tránh khai báo cùng khóa với giá trị mâu thuẫn ở nhiều file/profile mà không biết thứ tự ưu tiên.

### 8.2. Spring Boot debug mode không đồng nghĩa root DEBUG

Tham số **--debug** hoặc **debug=true** khiến Boot bật thêm log cho một số nhóm logger của framework, **không tự làm mọi logger của toàn ứng dụng chuyển sang DEBUG**. Nếu muốn DEBUG cho mã thuộc package cụ thể, đặt **logging.level.<package>=DEBUG**; muốn thay đổi root, dùng **logging.level.root=DEBUG**.

Chú ý ứng dụng có thể thay đổi logging theo **profile**, environment variable, command line và file cấu hình riêng. Vì vậy việc tìm thấy một dòng trong application.properties chưa chứng minh nó là giá trị được áp dụng cuối cùng.

### 8.3. File cấu hình nâng cao

Khi cần điều khiển nhiều appender, rolling policy, filter và layout theo kiểu Logback, Boot khuyến nghị dùng **logback-spring.xml** khi có thể để tận dụng tích hợp của Boot; còn với Log4j2 dùng **log4j2-spring.xml** trong trường hợp phù hợp. Tên **logging.config** có thể được dùng để chỉ định đường dẫn cấu hình.

Logging khởi tạo rất sớm, trước khi application context hoàn tất. Không nên trông chờ một **@PropertySource** trong một bean cấu hình được đọc đủ sớm để quyết định toàn bộ logging bootstrap.

## 9. Config mặc định, kế thừa và thứ tự ưu tiên

Không có một danh sách ưu tiên thống nhất áp dụng cho JUL, Logback, Log4j2 và Spring Boot. Mỗi hệ có thuật toán nhận diện file, default, system properties và thời điểm khởi tạo riêng. Hãy dùng quy trình sau thay vì đoán thứ tự:

1. **Xác định API và backend:** mã gọi JUL hay SLF4J? Nếu là SLF4J, provider thực sự là Logback, Log4j2 hay thứ khác?
2. **Xác định môi trường:** ứng dụng Java SE độc lập, Spring Boot, servlet container, test runner hoặc host do bên khác quản lý?
3. **Tìm nguồn cấu hình được nạp:** JDK **conf/logging.properties**, file XML/properties trên classpath, tham số JVM, **logging.config**, profile hoặc cấu hình lập trình.
4. **Tìm mức hiệu lực:** level ở logger có thể kế thừa từ cha; handler/appender và filter có thể tiếp tục loại sự kiện.
5. **Xác định output:** console stdout hay stderr, file ở thư mục làm việc nào, hoặc appender/collector tập trung nào?
6. **Kiểm tra thực tế:** chạy một logger kiểm thử có INFO và DEBUG/FINE, xem bản ghi ở đúng môi trường runtime và logger backend status nếu có.

### Bảng nguyên nhân khi cùng mã cho kết quả khác nhau

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Ứng dụng Java SE dùng JUL in INFO nhưng không in FINE | Root hoặc ConsoleHandler đang ở INFO, hoặc cả hai. |
| Ứng dụng SLF4J không in log dù gọi logger | Không có provider tương thích; provider là NOP; filter/level tắt; sink lỗi. |
| Logback độc lập in DEBUG dù không có logback.xml | BasicConfigurator fallback root DEBUG. |
| Dự án dùng Logback nhưng chỉ in INFO trở lên | Spring Boot cấu hình mặc định, hoặc file/properties đã đổi root level. |
| Log4j Core chỉ in ERROR khi không cấu hình | DefaultConfiguration thường đặt root ERROR. |
| Test in nhiều log hơn lúc chạy production | Test classpath có file cấu hình riêng, profile khác hoặc dependency khác. |
| INFO vẫn không xuất hiện sau khi đặt logger level INFO | Handler/appender filter có ngưỡng cao hơn, logger bị tắt ở nơi khác hoặc provider/sink không phù hợp. |
| Log xuất hiện hai lần | Nhiều appender nhận cùng event hoặc additivity/kế thừa appender gây ghi trùng. |

**Phân biệt chính xác:** mức **logger** quyết định record được phát ở tầng logger; mức **handler/appender** và filter có thể lọc tiếp. Còn việc console hiển thị màu, timestamp và tên thread là nhiệm vụ của formatter/layout, không quyết định riêng mức log có được nhận hay không.

## 10. Cách tự kiểm chứng trên dự án đang chạy

Một quy trình chẩn đoán ngắn, tái lập được:

### Bước 1: quan sát classpath và dependency

Với Gradle hoặc Maven, kiểm tra dependencies ở runtime. Tìm **slf4j-api**, **logback-classic**, **log4j-core**, adapter/bridge và các logging starter. Hãy dùng dependency report của project để biết provider hiện diện thực sự. Không thay đổi ngẫu nhiên thư viện chỉ để “thử xem có log không”.

### Bước 2: bật một log kiểm thử có chủ đích

Trong một lớp thuộc package bạn đang muốn kiểm tra, ghi một dòng INFO và một dòng DEBUG/FINE. Với JUL, bạn có thể dùng chương trình standalone ở mục 4. Với SLF4J, dùng chương trình của ứng dụng đã có dependency. Log thông điệp thử nghiệm đơn giản, không dùng tài khoản người dùng, secret, token hoặc dữ liệu thực.

### Bước 3: phân biệt ba tình huống

- **Không có event:** level/filter, NOP provider, sai logger, sai điểm code hoặc event chưa được gọi.
- **Event được phát nhưng không thấy tại đích:** appender/handler, đường dẫn file, quyền ghi, lỗi sink, pipeline collector hoặc async buffer.
- **Event có nhưng không đúng format:** layout/formatter, timezone, logger name, MDC hoặc structured logging mapping.

### Bước 4: kiểm tra môi trường thực chạy

Một ứng dụng mở bằng IDE có working directory khác container hoặc CI. Biến môi trường, JVM system properties, profile và runtime classpath có thể khác. Với container, log console thường được hệ thống chạy container thu thập, nhưng điều đó không đồng nghĩa ứng dụng tự ghi thêm file. Xác nhận output thực sự qua stdout/stderr và log agent.

### Bước 5: ghi nhận default và phần đã override

Khi tìm được cấu hình đúng, lưu lại trong tài liệu vận hành: backend/version, nguồn config, root level, các logger ngoại lệ, appender, retention/rotation nếu có, và hành vi khi lỗi. Việc “không có file trong repository” tự nó không phải đủ bằng chứng của một default.

## 11. Những sai lầm phổ biến

**Nhầm lẫn default của các framework.** “Logback root mặc định DEBUG” chỉ mô tả fallback BasicConfigurator trong điều kiện phù hợp; Boot thường đặt mặc định INFO cho ứng dụng của nó. Tương tự, JUL, Log4j Core và SLF4J không chia sẻ một cấu hình duy nhất.

**Cho rằng SLF4J tự ghi ra console.** SLF4J là abstraction; cần provider/backend. Với SLF4J 2.x không provider, cảnh báo kèm NOP logger là dấu hiệu cần xử lý.

**Đặt mỗi level của logger rồi kết luận backend hỏng.** Đặc biệt với JUL, ConsoleHandler cũng có level riêng. Với các backend khác, appender filter, threshold và routing có thể loại event.

**Tắt log quá nhiều bằng root level ERROR.** Lúc vận hành có thể thiếu thông tin INFO/WARN hữu ích. Ngược lại, root DEBUG/TRACE trong production có thể tăng I/O, chi phí lưu trữ và nguy cơ lộ dữ liệu nhạy cảm. Chọn level theo môi trường và mục đích, bật chi tiết ở package cụ thể khi cần.

**Đặt file cấu hình sai classpath.** Tên **logback.xml** hoặc **log4j2.xml** tồn tại trong thư mục dự án chưa chắc đã được đóng gói vào runtime. Kiểm tra tài nguyên thực trong JAR/CLASSPATH và các giá trị cấu hình từ môi trường.

**Dùng câu lệnh --debug của Boot rồi mong toàn hệ thống DEBUG.** Tham số này có ý nghĩa riêng trong Boot, không thay cho logging.level.root=DEBUG hay logging.level.<package>=DEBUG.

**Quên sự khác biệt stdout và stderr.** JUL ConsoleHandler mặc định ghi stderr; nhiều console appender khác có thể ghi stdout theo cấu hình. Việc công cụ thu thập phân tách stream đôi khi làm bạn tưởng log đã mất.

**Nhầm logging mặc định với độ bền dữ liệu.** Console logging không bảo đảm log đã được lưu trữ lâu dài. Trong production cần kết hợp cơ chế collector, retention, rotation và cảnh báo lỗi.

**Đưa dữ liệu nhạy cảm vào log thử nghiệm.** Cấu hình mặc định có thể làm lộ message ngay trên console và nơi thu thập. Giữ bí mật bằng nguyên tắc lọc/redact dữ liệu từ đầu.

## 12. Bài tập tự kiểm tra

1. Chạy **DefaultLoggingDemo.java** trên một JDK 17 chưa tùy chỉnh. Ghi lại root level, số handler, nơi INFO xuất hiện, lý do FINE không xuất hiện và các dòng in ra stdout/stderr.
2. Tạo **logging.properties** từ mục 4.4 rồi chạy lại. Dự đoán trước kết quả lọc INFO/FINE; kiểm tra logger level, effective level và handler level riêng.
3. Trong một ứng dụng SLF4J + Logback độc lập, không có config file, xem root level và appender. Thêm logback.xml đặt root INFO, xác nhận thay đổi.
4. Nếu có dự án Spring Boot, bỏ file cấu hình logging tùy chỉnh trong môi trường thử nghiệm có kiểm soát, quan sát console. Thử chỉ thay logging.level của một package và xác nhận DEBUG của package đó thay đổi mà root không cần đổi.
5. Với Log4j Core, so sánh khi dùng DefaultConfiguration với khi bổ sung log4j2.xml đặt root INFO. Ghi rõ điểm khác với Logback và Boot.

Câu hỏi kiểm tra hiểu bài:

- Vì sao **getLevel() == null** không có nghĩa logger đang OFF?
- Vì sao JUL Logger ở FINE vẫn có thể không thấy dòng FINE?
- Tại sao thiếu SLF4J provider khác với thiếu logback.xml?
- Vì sao không thể nói “mặc định Java logging là INFO” mà không nêu framework?
- Những giá trị nào của logging phải kiểm tra tại runtime trước khi kết luận cấu hình đang hiệu lực?

## 13. Ghi nhớ

**Cấu hình logging mặc định là hành vi của một stack cụ thể, không phải quy tắc chung của cú pháp Java.** JUL lấy thiết lập khởi tạo của LogManager/JDK; SLF4J cần provider; Logback và Log4j Core có fallback riêng; Spring Boot lại có logging auto-configuration của framework. Muốn hiểu log nào xuất hiện và đi đâu, luôn truy từ **runtime dependency → config được nạp → logger effective level → handler/appender/filter → formatter/output**. Hãy giữ các default hữu ích khi mới học, nhưng trong ứng dụng thật cần cấu hình rõ những yếu tố vận hành quan trọng và kiểm tra trên môi trường chạy đích.

### Tài liệu chính thức

- Oracle Java 17 – Java Logging Overview: https://docs.oracle.com/en/java/javase/17/core/java-logging-overview.html
- Oracle Java 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- SLF4J – Manual và lỗi thiếu provider: https://www.slf4j.org/manual.html và https://www.slf4j.org/codes.html
- Logback – Configuration, BasicConfigurator fallback: https://logback.qos.ch/manual/configuration.html
- Apache Log4j2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Apache Log4j2 – Configuration properties: https://logging.apache.org/log4j/2.x/manual/systemproperties.html
- Spring Boot – Logging reference: https://docs.spring.io/spring-boot/reference/features/logging.html
