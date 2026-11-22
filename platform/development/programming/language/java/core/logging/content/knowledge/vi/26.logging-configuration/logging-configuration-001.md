# Cấu hình logging bằng file trong Java

## 1. Vì sao nên đưa cấu hình logging ra file?

Trong ứng dụng Java, lệnh ghi log thuộc mã nguồn, còn **cách xử lý log** thường thay đổi theo môi trường. Khi phát triển, có thể cần log `DEBUG`/`FINE` để chẩn đoán; trên production, có thể chỉ ghi `INFO` trở lên, xuất JSON ra stdout hoặc chuyển log đến hệ thống thu thập tập trung.

**Cấu hình logging bằng file** là khai báo các quy tắc đó trong tệp cấu hình thay vì sửa và biên dịch lại từng lời gọi log. Tệp thường quyết định:

- **Logger và log level:** lớp/package nào được phép phát ra sự kiện ở mức nào.
- **Handler/Appender:** sự kiện log được gửi đến console, tệp, socket hoặc hệ thống trung gian nào.
- **Formatter/Layout:** trình bày timestamp, level, tên logger, thread, thông điệp và stack trace ra sao.
- **Filter:** chọn hoặc bỏ sự kiện dựa trên mức độ hay điều kiện khác.
- **File rolling/retention:** tên tệp, dung lượng/ngày xoay vòng, số bản giữ lại; khả năng này phụ thuộc backend.
- **Async/buffer:** có dùng queue hay không và xử lý như thế nào khi queue đầy; cũng phụ thuộc backend.

Việc tách cấu hình khỏi code giúp dùng cùng một ứng dụng ở nhiều môi trường. Tuy nhiên, **file cấu hình thuộc hệ logging nào thì chỉ có hiệu lực với hệ đó**. `java.util.logging` (JUL) không tự đọc `logback.xml`, còn SLF4J chỉ là API/facade: backend thực tế mới quyết định cú pháp và tệp cấu hình.

## 2. Những thư viện thường gặp và tệp cấu hình tương ứng

| Hệ logging | File thường gặp | Cách nạp cấu hình |
| --- | --- | --- |
| Java Util Logging (JUL, có sẵn trong JDK) | `logging.properties` | Truyền JVM property `-Djava.util.logging.config.file=...` hoặc dùng cấu hình mặc định của JDK |
| Logback Classic | `logback.xml`, `logback-test.xml` | Logback tìm file trên classpath hoặc dùng cơ chế chỉ định file ngoài |
| Log4j 2 | `log4j2.xml` (còn có các định dạng được hỗ trợ khác) | Log4j 2 nạp cấu hình qua cơ chế discovery hoặc thuộc tính cấu hình riêng |
| Spring Boot dùng Logback | `logback-spring.xml` hoặc cấu hình `logging.*` của Boot | Spring Boot tích hợp với backend và cung cấp một số khả năng cấu hình bổ sung |

Tên file không có tính “toàn Java”: mỗi backend có convention riêng. Nếu ứng dụng dùng `org.slf4j.Logger`, cần biết **SLF4J đang kết nối với backend nào** rồi cấu hình backend đó. Tránh đưa đồng thời nhiều binding/provider gây hành vi khó đoán hoặc xung đột cấu hình.

Với ứng dụng Java Core chỉ sử dụng JDK, **JUL và `logging.properties`** là lựa chọn đơn giản để hiểu cơ chế trước khi dùng framework bên ngoài.

## 3. Ví dụ hoàn chỉnh với `java.util.logging` trên JDK 17+

Ví dụ này không cần Maven, Gradle hay dependency bên ngoài. Chúng ta sẽ đặt level `FINE` cho một logger cụ thể, để root logger ở `INFO` và cấu hình `ConsoleHandler` đủ rộng để nhận sự kiện `FINE`.

Tạo hai tệp trong cùng một thư mục:

~~~text
demo/
├── FileConfigDemo.java
└── logging.properties
~~~

**Tệp `FileConfigDemo.java`:**

~~~java
import java.util.logging.Logger;

public class FileConfigDemo {
    private static final Logger LOGGER = Logger.getLogger("demo.order");

    public static void main(String[] args) {
        LOGGER.fine("validate orderId=42");
        LOGGER.info("order created");
        LOGGER.warning("retry needed");
    }
}
~~~

Logger tên `demo.order` có ba sự kiện lần lượt ở mức `FINE`, `INFO` và `WARNING`. Mã nguồn không cần biết log sẽ đi vào console hay file; quyết định đó nằm trong cấu hình.

**Tệp `logging.properties`:**

~~~properties
# Root logger: mac dinh INFO cho cac logger khong override.
.level = INFO

# Chi tiet hon cho logger demo.order.
demo.order.level = FINE

# Gan ConsoleHandler cho root logger.
handlers = java.util.logging.ConsoleHandler

# Handler phai chap nhan FINE thi FINE moi hien thi.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Chi hien level va thong diep; bo timestamp de de kiem tra.
java.util.logging.SimpleFormatter.format = %4$s: %5$s%n
~~~

Biên dịch và chạy từ thư mục chứa cả hai tệp:

~~~bash
javac FileConfigDemo.java
java -Djava.util.logging.config.file=logging.properties FileConfigDemo
~~~

Với file được nạp đúng, **stderr** của `ConsoleHandler` chứa chính xác ba dòng dưới đây (đây không phải stdout):

~~~text
FINE: validate orderId=42
INFO: order created
WARNING: retry needed
~~~

`java.util.logging.ConsoleHandler` mặc định ghi ra **`System.err`**. Vì ví dụ không gọi `System.out`, stdout không có nội dung. Thuộc tính `java.util.logging.SimpleFormatter.format` quy định định dạng: `%4$s` là tên level, `%5$s` là message, `%n` là dấu xuống dòng theo nền tảng. Vì không ghi thời gian nên nội dung có thể kiểm tra ổn định.

**Điều kiện quan trọng:** cờ `-Djava.util.logging.config.file=...` là **JVM system property**, phải đứng **trước tên lớp main** trong lệnh `java`. Nếu bỏ cờ này, cấu hình mặc định của JDK sẽ được dùng; thông thường `FINE` bị lọc và formatter mặc định hiển thị thêm thông tin thời gian/nguồn.

## 4. Hiểu đúng hai lớp lọc: Logger và Handler

Trong JUL, một sự kiện phải vượt qua các điều kiện phù hợp trước khi được ghi ra nơi nhận:

~~~text
LOGGER.fine("...")
        |
        v
Level/Filter cua logger nguon (demo.order)
        |
        v
Handler gan tren logger hoac logger cha
        |
        v
Level/Filter cua Handler
        |
        v
Formatter -> stderr, file, ...
~~~

Với cấu hình ở mục 3:

- `demo.order.level = FINE`: logger nguồn có thể phát sự kiện `FINE`, `INFO`, `WARNING` và cao hơn.
- `.level = INFO`: level mặc định của root; logger khác không được cấu hình riêng thường kế thừa level phù hợp từ cây logger.
- `handlers = java.util.logging.ConsoleHandler`: handler nằm trên root. Logger con mặc định chuyển sự kiện đến handler của cha qua cơ chế `useParentHandlers`.
- `java.util.logging.ConsoleHandler.level = FINE`: handler không bỏ sự kiện `FINE` đã vượt qua logger nguồn.

Nếu chỉ đổi logger nguồn thành `FINE` nhưng handler vẫn ở `INFO`, dòng `FINE` sẽ không được in. Nếu chỉ đổi handler thành `FINE` nhưng logger nguồn vẫn ở `INFO`, sự kiện `FINE` có thể đã bị bỏ trước khi đến handler.

Một điểm dễ nhầm trong JUL: **root có level `INFO` không có nghĩa mọi event phát từ logger con `FINE` sẽ bị root chặn lại lần nữa**. Level được kiểm tra khi logger nguồn quyết định có tạo event hay không; khi sự kiện được chuyển tới handler của logger cha, các handler tiếp tục áp dụng level/filter của **chúng**, chứ level của mọi logger cha không được áp dụng lại như một bộ lọc riêng. Vì vậy ví dụ ở trên có thể in `FINE` dù root được cấu hình `INFO`.

Tên logger cũng phải khớp: `demo.order.level` áp dụng cho logger tên `demo.order`; nếu code dùng `Logger.getLogger("demo.payment")`, cần xác định level hiệu lực từ cấu hình tương ứng. Trong ứng dụng thực tế, logger thường được đặt tên theo class hoặc package để cấu hình từng nhóm dễ hơn.

## 5. Ghi ra file và xoay vòng file với JUL

Để bổ sung file output, có thể dùng `java.util.logging.FileHandler`. Ví dụ sau là **phiên bản mở rộng của `logging.properties`** ở mục 3, không cần thay đổi code Java:

~~~properties
.level = INFO
demo.order.level = FINE

handlers = java.util.logging.ConsoleHandler, java.util.logging.FileHandler

java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

java.util.logging.FileHandler.level = FINE
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = logs/application-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true

java.util.logging.SimpleFormatter.format = %4$s: %5$s%n
~~~

Ý nghĩa:

- `handlers`: cùng một log event có thể đến **console** và **file** (nếu cả hai handler chấp nhận).
- `pattern`: `logs/application-%g.log` đặt file trong thư mục `logs`; `%g` biểu thị chỉ số generation khi quay vòng.
- `limit = 1048576`: giới hạn xấp xỉ **1 MiB** cho một file trước khi rotation theo cơ chế FileHandler.
- `count = 5`: giữ vòng xoay gồm tối đa năm generation.
- `append = true`: cố gắng nối thêm vào file đang có khi mở handler, thay vì chủ động ghi đè mỗi lần khởi chạy.

Trước khi chạy, phải **tạo thư mục `logs`** và bảo đảm tiến trình Java có quyền ghi tại đó. Ví dụ trên dùng đường dẫn tương đối; nó được giải quyết theo **working directory của tiến trình**, không nhất thiết là thư mục chứa JAR hoặc mã nguồn. Nếu ứng dụng đóng gói thành JAR, vẫn phải kiểm tra working directory khi chạy dưới service, IDE, Docker hoặc scheduler.

`FileHandler` có cơ chế lock file để hạn chế xung đột giữa các instance handler, nhưng không nên từ đó suy ra nhiều tiến trình độc lập có thể an toàn ghi vào **cùng một file tùy ý**. Với nhiều process/container, thường xuất log ra stdout/stderr và để hệ thống thu thập log gom lại, hoặc cấu hình nơi nhận file riêng cho từng instance.

Rotation của JUL theo `limit/count` khác với chính sách quay theo ngày, nén file và retention nâng cao của các backend khác. Nếu có yêu cầu rolling theo thời gian hoặc giới hạn lưu trữ chi tiết, hãy chọn appender/backend phù hợp thay vì giả định JUL `FileHandler` hỗ trợ tất cả kiểu rotation.

## 6. Ví dụ file `logback.xml` khi ứng dụng dùng SLF4J + Logback

Một chương trình Java dùng SLF4J có thể khai báo:

~~~java
// Doan ma tich hop: can SLF4J API va Logback runtime.
private static final org.slf4j.Logger LOGGER =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOGGER.debug("Validating orderId={}", orderId);
LOGGER.info("Created orderId={}", orderId);
~~~

Đây chỉ là đoạn mã **tích hợp** trong một class có sẵn `OrderService` và `orderId`, không phải chương trình chạy độc lập. Với Logback làm backend, một cấu hình cơ bản trên classpath là:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.order" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

`logback.xml` thường đặt dưới `src/main/resources/` trong dự án Maven/Gradle để có mặt trên classpath khi chạy. `logger name="com.example.order"` áp dụng cho logger/package phù hợp; nếu tên thực tế khác, cần chỉnh cho khớp. Root `INFO` là mặc định cho những logger không có level cụ thể hơn. Appender `STDOUT` định nghĩa đích và pattern hiển thị.

**Không áp dụng nguyên cú pháp của JUL vào Logback.** `handlers` và `.level` là cách khai báo quen thuộc của JUL; Logback dùng `<appender>`, `<logger>`, `<root>` và các thành phần XML tương ứng. SLF4J là giao diện gọi log, còn Logback chịu trách nhiệm đọc `logback.xml`.

Khi dùng Logback, file theo môi trường có thể được chọn bằng cơ chế hỗ trợ của framework/backend. Riêng Spring Boot còn hỗ trợ `logback-spring.xml` và cấu hình `logging.*`; các chức năng dành cho Boot không mặc nhiên hoạt động trong chương trình Java SE thuần.

## 7. Ví dụ file `log4j2.xml` khi ứng dụng dùng Log4j 2

Một backend phổ biến khác là Log4j 2. File `log4j2.xml` tối giản có thể như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p [%t] %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.order" level="debug"/>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Ở ví dụ này, logger `com.example.order` được phép tạo `debug` event, còn root có mức mặc định `info`. Logger con mặc định có tính kế thừa/appender additivity, nên sự kiện có thể được xử lý bởi appender gắn ở root; cần cân nhắc cấu hình `additivity` nếu có nhiều appender để tránh lặp log. Việc cấu hình tệp chỉ có hiệu lực khi ứng dụng thực sự chạy Log4j 2.

**Chọn một backend logging đang được ứng dụng sử dụng** và đặt đúng tệp cấu hình cho backend đó. Không cố làm cho JUL, Logback và Log4j 2 cùng đọc một tệp, cũng không kết luận rằng file đã có trong repository thì chắc chắn runtime đã nạp file đó.

## 8. Vị trí file, môi trường và vòng đời cấu hình

Có hai kiểu triển khai chính:

1. **Đóng gói cùng ứng dụng:** đặt file phù hợp trên classpath. Dễ phân phối, ổn định theo version, nhưng muốn đổi thường phải xây dựng hoặc phân phối lại artifact.
2. **Cấu hình ngoài ứng dụng:** mount hoặc đặt file trên host/container rồi trỏ runtime/backend đến đúng path. Dễ thay đổi giữa dev/test/prod, nhưng cần quản lý quyền đọc, working directory, version và cách cập nhật.

Riêng JUL, ví dụ lệnh dùng file ngoài là:

~~~bash
java -Djava.util.logging.config.file=/etc/my-app/logging.properties -jar app.jar
~~~

Đường dẫn này chỉ minh họa khi ứng dụng và file tồn tại, **không phải lệnh để chạy ví dụ `FileConfigDemo`** ở mục 3. `-D...` được truyền cho JVM trước `-jar`/tên main class. Trong Windows, có thể dùng đường dẫn có dấu gạch chéo xuôi được Java chấp nhận và bao dấu nháy nếu chứa khoảng trắng, ví dụ `-Djava.util.logging.config.file="C:/my app/logging.properties"`. Trong file `.properties`, dấu gạch chéo ngược có ý nghĩa escape; ưu tiên đường dẫn không cần escape hoặc escape đúng cách.

Nhiều backend có khả năng **reload/reconfiguration**, nhưng thời điểm và cách phát hiện thay đổi khác nhau. Đừng mặc định rằng sửa file trên đĩa sẽ lập tức đổi level đang chạy. Với JUL có API `LogManager.readConfiguration(...)` để đọc lại cấu hình, nhưng thay đổi runtime có thể ảnh hưởng handlers và logger đang tồn tại; cần quản lý và kiểm tra theo vòng đời ứng dụng. Trong môi trường production, nên có quy trình thay đổi cấu hình và rollback rõ ràng.

Bảo mật và vận hành:

- Không nhúng password, token hoặc dữ liệu bí mật vào mẫu log, đường dẫn cấu hình hoặc message mẫu.
- Đặt file cấu hình ở vị trí được bảo vệ; người không có quyền không nên sửa level/đích log để tắt giám sát hoặc chuyển log đến nơi lạ.
- Quy định nơi lưu log, quyền ghi, dung lượng đĩa, rotation và retention phù hợp môi trường.
- Với container, cân nhắc stdout/stderr và log collector thay vì giả định ổ đĩa container là nơi lưu trữ lâu dài.
- Khi đổi `DEBUG`/`FINE`, chú ý khối lượng dữ liệu, chi phí I/O và thông tin nhạy cảm có thể xuất hiện nhiều hơn.

## 9. Các lỗi thường gặp và cách xác minh

| Hiện tượng | Nguyên nhân hay gặp | Kiểm tra / cách xử lý |
| --- | --- | --- |
| Chỉnh file nhưng log không đổi | Runtime không nạp đúng file, đường dẫn sai hoặc không hỗ trợ reload | Kiểm tra JVM option, classpath, tên backend và khởi động lại khi cần |
| `FINE`/`DEBUG` không xuất hiện | Logger nguồn **hoặc** Handler/Appender/Filter bỏ event | Kiểm tra level hiệu lực và từng bộ lọc trên đường đi |
| Cùng một log xuất hiện hai lần | Nhiều handler hoặc appender additivity gây ghi lặp | Kiểm tra cấu trúc kế thừa và số đích nhận |
| File log không được tạo | Thư mục chưa có, thiếu quyền, sai working directory hoặc backend chưa khởi tạo file appender | Kiểm tra path thực và lỗi lúc khởi động |
| Cấu hình JUL không tác động SLF4J | Ứng dụng đang chạy Logback/Log4j 2 | Xác định provider/backend thực tế và dùng file tương ứng |
| Lệnh cấu hình không có hiệu lực | Đặt `-D...` sau tên class/JAR | Đặt JVM option trước class hoặc `-jar` |
| Log quá nhiều, đầy ổ | Level quá chi tiết, không có rotation/retention phù hợp | Giảm verbosity, cấu hình rolling/retention và giám sát dung lượng |
| Log thiếu trace/request ID | Formatter/pattern chưa gắn MDC/context hoặc context không được propagate | Cấu hình correlation và kiểm tra scope qua thread/async |

**Bài kiểm tra nhanh trên ví dụ JUL:**

1. Chạy với file ở mục 3: phải thấy cả `FINE`, `INFO`, `WARNING` trên stderr.
2. Đổi `demo.order.level = WARNING` rồi khởi chạy lại: chỉ còn `WARNING`, vì logger nguồn đã lọc mức thấp.
3. Khôi phục logger về `FINE`, đổi `ConsoleHandler.level = INFO` rồi khởi chạy lại: `FINE` không còn được in, dù logger vẫn cho phép tạo sự kiện đó.
4. Đổi lại `ConsoleHandler.level = FINE`: ba dòng xuất hiện như ban đầu.

Những thao tác này phân biệt rõ **file đã được nạp hay chưa**, **logger có tạo event hay không** và **handler có xuất event hay không**.

**Ghi nhớ:** Cấu hình logging bằng file tách chính sách log khỏi mã nguồn. Với Java Core, hãy bắt đầu từ `logging.properties` của JUL, xác minh cả mức của logger và handler, rồi mở rộng sang file output/rotation. Khi chuyển sang SLF4J + Logback hoặc Log4j 2, phải dùng đúng file và cú pháp của backend đang hoạt động.