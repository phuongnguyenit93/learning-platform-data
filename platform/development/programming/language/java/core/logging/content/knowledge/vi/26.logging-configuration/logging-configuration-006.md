# Cấu hình theo logger trong Java Logging

## 1. Cấu hình theo logger là gì?

Trong ứng dụng Java, một **logger** là một đối tượng ghi log có tên (logger name). Tên thường là tên đầy đủ của lớp hoặc package, ví dụ:

- com.example.shop.payment.PaymentService
- com.example.shop.repository.OrderRepository
- org.springframework.web
- org.hibernate.SQL

**Cấu hình theo logger** nghĩa là đặt mức ghi log và, khi cần, đích xuất log riêng cho một tên logger hoặc một nhánh logger. Cách này giúp tăng độ chi tiết ở đúng khu vực đang điều tra mà vẫn giữ lượng log chung trong giới hạn hợp lý.

Ví dụ: hệ thống bán hàng đang gặp lỗi thanh toán. Ta có thể giữ **root = INFO**, bật **com.example.shop.payment = DEBUG**, còn **com.example.shop.repository = WARN**. Kết quả: mã xử lý thanh toán được ghi chi tiết để chẩn đoán, phần truy cập dữ liệu chỉ xuất cảnh báo và lỗi, các vùng khác tiếp tục theo chính sách chung.

Cấu hình theo logger đặc biệt hữu ích khi:

- Chỉ một lớp hoặc package cần log DEBUG/TRACE để kiểm tra sự cố.
- Thư viện bên thứ ba ghi quá nhiều INFO/DEBUG, cần giảm mức riêng.
- Một luồng log đặc thù, ví dụ audit, cần đi vào một appender/đích riêng.
- Cần thay đổi mức log tạm thời trong môi trường kiểm thử hoặc vận hành.

Không nhầm **logger name** với correlation ID, thread name hoặc tên file log. Một logger thường được tái sử dụng cho nhiều request; correlation ID là thuộc tính của luồng xử lý dùng để đối chiếu các dòng log.

## 2. Phân biệt logging API, logger và logging backend

Trong dự án Java thường gặp ba lớp khái niệm:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Logging API / facade | Cung cấp lời gọi ghi log trong code | SLF4J, java.util.logging (JUL) |
| Logger | Đối tượng có tên dùng để quyết định một sự kiện có được bật ở mức log đó hay không | com.example.shop.payment.PaymentService |
| Backend / implementation | Xử lý cấu hình, filter, appender, formatter và xuất log | Logback Classic, Log4j 2 Core, JUL |

Với SLF4J, code thường viết:

~~~java
// Đoạn minh họa trong lớp PaymentService,
// cần dependency SLF4J; không phải chương trình Java độc lập.
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

public void pay(String orderId) {
    log.info("Paying order {}", orderId);
    log.debug("Payment workflow entered for {}", orderId);
}
~~~

Tên logger ở đây mặc định là tên đầy đủ của lớp **PaymentService**, bao gồm package. SLF4J chuyển sự kiện tới backend đang được cấu hình; cú pháp XML/Properties để thiết lập mức và appender thuộc backend hoặc môi trường chạy, không nằm trong bản thân phương thức LoggerFactory.getLogger.

Nếu ứng dụng đã dùng SLF4J + Logback, hãy cấu hình Logback; nếu dùng SLF4J + Log4j 2, cấu hình Log4j 2 tương ứng. Tránh vô tình đưa nhiều logging provider/binding xung đột vào classpath. JUL là API và implementation có sẵn trong JDK, hữu ích để minh họa hành vi chung và chạy ví dụ độc lập.

## 3. Phân cấp tên logger và quy tắc kế thừa

Với Logback và Log4j 2, tên logger được tổ chức theo các đoạn phân cách bằng dấu chấm. **Root** là logger trên cùng. Ví dụ:

~~~text
ROOT
  └── com
      └── com.example
          └── com.example.shop
              ├── com.example.shop.payment
              │   └── com.example.shop.payment.PaymentService
              ├── com.example.shop.repository
              │   └── com.example.shop.repository.OrderRepository
              └── com.example.shop.audit
~~~

Tên trên là mô hình logic; logger cha trung gian không nhất thiết phải được khởi tạo tường minh trong code. Việc phân cấp dựa vào **tên**, không dựa vào quan hệ kế thừa Java kiểu extends. Một tên tương tự nhưng khác đoạn hoặc khác chữ hoa/chữ thường có thể không thuộc nhánh dự định.

Nếu logger con **không được gán level riêng**, nó sử dụng **effective level** từ tổ tiên gần nhất có level được cấu hình. Ví dụ:

| Logger | Level khai báo | Effective level |
| --- | --- | --- |
| ROOT | INFO | INFO |
| com.example.shop | (kế thừa) | INFO |
| com.example.shop.payment | DEBUG | DEBUG |
| com.example.shop.payment.PaymentService | (kế thừa) | DEBUG |
| com.example.shop.repository | WARN | WARN |
| com.example.shop.repository.OrderRepository | (kế thừa) | WARN |
| com.example.shop.audit | ERROR | ERROR |

Một cấu hình ở cấp package thường ảnh hưởng tới nhiều lớp cùng nhánh; cấu hình tại tên lớp ảnh hưởng hẹp hơn. **Level tường minh ở logger con ưu tiên hơn level kế thừa từ logger cha**. Thay đổi root không thay thế level tường minh ở các nhánh con.

Ví dụ, nếu có cấu hình **com.example.shop = INFO** và **com.example.shop.payment = DEBUG**, lời gọi DEBUG của PaymentService được bật. Nếu đặt thêm **com.example.shop.payment.PaymentService = ERROR**, lớp này lại chỉ phát các sự kiện ERROR theo ngưỡng của chính nó; các lớp thanh toán khác vẫn theo DEBUG của package.

## 4. Mức log và hiệu lực của level

Với Logback hoặc Log4j 2, các mức phổ biến được sắp theo mức độ nghiêm trọng:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Một sự kiện được bật nếu mức sự kiện **bằng hoặc nghiêm trọng hơn** effective level của logger phát sự kiện.

| Effective level | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| TRACE | Có | Có | Có | Có | Có |
| DEBUG | Không | Có | Có | Có | Có |
| INFO | Không | Không | Có | Có | Có |
| WARN | Không | Không | Không | Có | Có |
| ERROR | Không | Không | Không | Không | Có |
| OFF | Không | Không | Không | Không | Không |

Lưu ý: bảng thể hiện **lọc ban đầu tại logger**. Một sự kiện vượt qua bước này vẫn có thể bị chặn bởi appender filter, threshold, sampling, lỗi I/O hoặc cấu hình đường xuất. Mức ALL/OFF, mức FATAL và các tên mức đặc thù có thể khác nhau giữa các framework; không sao chép bảng này nguyên xi cho JUL.

Một cách diễn giải rất quan trọng:

> **Việc log ở logger con đã được bật không bị logger cha lọc lần hai chỉ vì cha có level nghiêm ngặt hơn**, khi sự kiện được chuyển lên các appender tổ tiên theo cơ chế additivity của Logback/Log4j 2. Appender và filter ở đường nhận vẫn có thể lọc riêng.

Chẳng hạn ROOT=INFO, payment=DEBUG, console appender không có filter bổ sung: một dòng DEBUG phát từ PaymentService có thể tới console của ROOT qua additivity. Đặt ROOT=INFO không đủ để chặn dòng DEBUG của logger con đã được cấu hình DEBUG. Đây là khác biệt giữa **kế thừa effective level** và **truyền sự kiện tới appender cha**.

## 5. Level, appender, filter và additivity là các quyết định khác nhau

Thông thường một sự kiện trải qua các bước:

~~~text
Lời gọi logger.debug("...")
          |
          v
Xác định logger name và effective level
          |
          v
Logger có bật DEBUG không?
  ├── Không: bỏ qua
  └── Có: tạo sự kiện log
                    |
                    v
           Appender của logger
                    |
                    v
       Appender ở các tổ tiên (nếu additivity)
                    |
                    v
          Filter / threshold / encoder
                    |
                    v
            Console / file / sink
~~~

- **Level:** quyết định lời gọi ghi log có đủ mức để được xử lý ngay tại logger phát sự kiện.
- **Appender/Handler:** đưa log đến đích cụ thể như console, file, network.
- **Filter/Threshold:** có thể loại hoặc hạn chế sự kiện ở các điểm của đường xuất.
- **Additivity:** quyết định có truyền sự kiện đã được bật đến các appender ở nhánh cha hay không. Trong Logback/Log4j 2, additivity mặc định là true; JUL có cơ chế tương tự qua useParentHandlers.

Ví dụ ROOT có appender CONSOLE và logger com.example.shop.audit cũng có appender AUDIT_FILE:

- Nếu audit **additivity=true**, event audit đi đến AUDIT_FILE và có thể đồng thời đi đến CONSOLE qua ROOT.
- Nếu audit **additivity=false**, event audit dừng ở nhánh audit và chỉ đi đến các appender gắn tại nhánh này hoặc các logger con theo đường truyền đến điểm dừng.
- Nếu audit **additivity=false** nhưng không có appender thích hợp, log có thể không xuất ra đâu dù level cho phép.

Một nguyên nhân log bị in hai lần là cùng một appender được gắn ở logger con và tổ tiên trong khi additivity vẫn bật. Để tránh nhân đôi, chỉ định appender ở một nơi hợp lý hoặc chủ động đặt additivity=false cho nhánh có đích riêng.

## 6. Ví dụ Java 17+ chạy độc lập bằng java.util.logging

Để quan sát trực tiếp **level con ghi đè level cha**, ví dụ sau dùng JUL (có sẵn trong JDK), không cần Maven/Gradle hay thư viện logging ngoài.

Tạo file **LoggerConfigDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerConfigDemo {
    public static void main(String[] args) {
        // Khởi tạo logger cha trước, rồi lấy các logger con.
        Logger app = Logger.getLogger("com.example.shop");
        Logger payment =
                Logger.getLogger("com.example.shop.payment.PaymentService");
        Logger stock =
                Logger.getLogger("com.example.shop.stock.StockService");

        // Handler chỉ in mức, tên logger và message để output ổn định.
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLoggerName()
                            + " | " + record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        app.setUseParentHandlers(false);
        app.addHandler(handler);

        app.setLevel(Level.WARNING);
        payment.setLevel(Level.FINE);

        try {
            payment.fine("payment-debug");
            payment.info("payment-info");
            stock.info("stock-info");
            stock.warning("stock-warning");
        } finally {
            app.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac LoggerConfigDemo.java
java LoggerConfigDemo
~~~

**Stdout xác định:**

~~~text
com.example.shop.payment.PaymentService | FINE | payment-debug
com.example.shop.payment.PaymentService | INFO | payment-info
com.example.shop.stock.StockService | WARNING | stock-warning
~~~

Giải thích:

1. Logger cha **com.example.shop** nhận mức **WARNING**.
2. Logger **payment** gán riêng mức **FINE**, cho phép cả FINE và INFO. Trong JUL, FINE dùng cho chẩn đoán chi tiết tương tự mục đích DEBUG ở nhiều backend khác.
3. Logger **stock** không đặt level riêng nên kế thừa WARNING: lời gọi INFO bị loại, WARNING được phát.
4. Handler của nhánh app đặt **Level.ALL** để không lọc thêm các sự kiện FINE đã hợp lệ.
5. useParentHandlers(false) ngăn ví dụ in tiếp qua handler của ROOT, giúp stdout dễ xác minh. Cuối chương trình, handler được tháo khỏi logger và đóng.

Ví dụ này cấu hình logger bằng API tại runtime. Trong ứng dụng lớn, thường ưu tiên tập trung cấu hình ở file hoặc hệ thống quản trị, tránh đặt setLevel rải rác trong code nghiệp vụ.

## 7. Cấu hình tên logger bằng JUL logging.properties

JUL hỗ trợ thiết lập logger theo tên qua file properties. Ví dụ file **logging.properties**:

~~~properties
# Ngưỡng mặc định trên root logger.
.level = INFO

# Handler trên root: nhận cả FINE nếu logger con cho phép.
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Các logger theo package.
com.example.shop.payment.level = FINE
com.example.shop.repository.level = WARNING
~~~

Khởi động một chương trình Java có dùng JUL bằng tùy chọn JVM (thay tên MainClass và classpath theo ứng dụng thực tế):

~~~bash
java -Djava.util.logging.config.file=logging.properties MainClass
~~~

JUL có các mức **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST** (cùng ALL/OFF). Không cấu hình JUL bằng các từ DEBUG hoặc WARN như thể đây là Logback. Đừng coi tương quan FINE≈DEBUG, SEVERE≈ERROR là ánh xạ đầy đủ của mọi mức ở mọi hệ thống.

Cần tách hai ngưỡng:

- **Logger level:** quyết định có tạo và chuyển LogRecord hay không.
- **Handler level:** quyết định handler có chấp nhận LogRecord nhận được hay không.

Nếu logger payment bật FINE nhưng ConsoleHandler chỉ chấp nhận INFO, lời gọi FINE vẫn không xuất console. Tương tự, khi **useParentHandlers=false**, logger cần có handler riêng; nếu không, bản ghi hợp lệ ở mức logger vẫn có thể không xuất ra đâu.

Các thuộc tính đặc thù của JUL và cách cập nhật LogManager có thể phụ thuộc phiên bản JDK; đối chiếu JavaDoc khi thay đổi cấu hình động.

## 8. Cấu hình theo logger với SLF4J + Logback

Khi backend là Logback Classic, có thể sử dụng **logback.xml**. Ví dụ sau đặt INFO chung, bật DEBUG cho package thanh toán, giới hạn WARN ở package repository và đưa audit sang file riêng.

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} %-5level %logger{50} - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="AUDIT_FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/audit.log</file>
    <append>true</append>
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.shop.payment" level="DEBUG"/>
  <logger name="com.example.shop.repository" level="WARN"/>

  <logger name="com.example.shop.audit" level="INFO"
          additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

**Kết quả mong đợi với cấu hình này:**

| Nơi phát event | Event | Nơi nhận |
| --- | --- | --- |
| com.example.shop.payment.PaymentService | DEBUG | CONSOLE |
| com.example.shop.repository.OrderRepository | INFO | Không phát vì ngưỡng WARN |
| com.example.shop.repository.OrderRepository | ERROR | CONSOLE |
| com.example.shop.audit.AuditService | INFO | AUDIT_FILE |
| com.example.shop.stock.StockService | DEBUG | Không phát vì ROOT=INFO |
| com.example.shop.stock.StockService | INFO | CONSOLE |

Thứ tự các phần tử XML và cấu hình appender theo quy tắc Logback. File logs/audit.log cần được ghi vào nơi có quyền truy cập; khi dùng Docker/Kubernetes phải tính đến việc lưu file và vòng đời container. Ví dụ này chỉ minh họa phân nhánh log; nếu log audit là bằng chứng pháp lý hoặc giao dịch bắt buộc lưu, cần cơ chế bền vững có xác nhận riêng.

**Điểm cần nhớ:**

- Logger **com.example.shop.payment** không có appender riêng nên kế thừa đường xuất CONSOLE nhờ additivity=true mặc định. Dòng DEBUG đã bật ở nhánh con có thể được đưa tới appender ROOT.
- Logger **com.example.shop.audit** có additivity=false và tham chiếu AUDIT_FILE, nên không tự chuyển tiếp sang CONSOLE của ROOT.
- Thêm appender CONSOLE một lần nữa vào payment mà vẫn để additivity=true có thể khiến sự kiện bị xuất trùng tới cùng đích.
- Level không quyết định định dạng. Pattern thuộc encoder/layout của appender, không thuộc tính mức log của logger.
- Cấu hình Logback yêu cầu các dependency thích hợp; đoạn XML không thể chạy riêng bằng javac.

Trong ứng dụng Spring Boot dùng Logback mặc định, thường đặt cấu hình mở rộng ở **logback-spring.xml** để sử dụng tích hợp cấu hình của Spring Boot; cấu hình mức log đơn thuần có thể đặt ở application.properties.

## 9. Cấu hình theo logger với Log4j 2

Log4j 2 có cú pháp XML khác. Ví dụ ý nghĩa tương đương trong **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
    </Console>
    <File name="AUDIT_FILE" fileName="logs/audit.log" append="true">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>
  </Appenders>

  <Loggers>
    <Logger name="com.example.shop.payment" level="debug"/>
    <Logger name="com.example.shop.repository" level="warn"/>

    <Logger name="com.example.shop.audit"
            level="info" additivity="false">
      <AppenderRef ref="AUDIT_FILE"/>
    </Logger>

    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Ở đây, **Logger** là cấu hình logger theo tên, **Root** là mặc định, **AppenderRef** chọn đích và **additivity** điều khiển truyền tới logger cha. Khi dùng Log4j 2, cần có Log4j API/Core (và binding/provider SLF4J phù hợp nếu code gọi SLF4J). Không trộn cú pháp lớp **ch.qos.logback...** của Logback với cú pháp plugin XML của Log4j 2.

Log4j 2 còn hỗ trợ filter tại logger và AppenderRef, nghĩa là một sự kiện có thể được logger chấp nhận nhưng không đến một appender cụ thể. Nên kiểm tra logger level, appender reference, additivity và filter riêng khi truy tìm lý do không thấy log.

## 10. Cấu hình theo logger trong Spring Boot

Spring Boot cho phép đặt level theo tên logger bằng **application.properties** hoặc **application.yml**, bất kể backend logging được hỗ trợ đang sử dụng:

~~~properties
logging.level.root=INFO
logging.level.com.example.shop.payment=DEBUG
logging.level.com.example.shop.repository=WARN
logging.level.org.springframework.web=INFO
logging.level.org.hibernate.SQL=WARN
~~~

Dạng YAML tương ứng:

~~~yaml
logging:
  level:
    root: INFO
    com.example.shop.payment: DEBUG
    com.example.shop.repository: WARN
    org.springframework.web: INFO
    org.hibernate.SQL: WARN
~~~

Các thuộc tính **logging.level** điều chỉnh ngưỡng logger. Chúng **không thay thế** cấu hình appender, additivity, định dạng, rolling policy hoặc filter nâng cao. Khi cần chia luồng xuất console/file, hãy dùng file cấu hình backend phù hợp.

Một số điểm vận hành:

- Với package logger, có thể cấu hình qua biến môi trường, ví dụ **LOGGING_LEVEL_COM_EXAMPLE_SHOP_PAYMENT=DEBUG** (quy tắc chuyển tên thuộc tính phụ thuộc cơ chế binding của Spring Boot).
- Cấu hình một **tên lớp chứa chữ hoa/chữ thường** bằng biến môi trường dạng thông thường có thể không đúng do relaxed binding đổi tên thành chữ thường. Dùng application.properties/YAML hoặc cơ chế cung cấp cấu hình giữ đúng tên, chẳng hạn SPRING_APPLICATION_JSON, khi cần cấu hình theo tên lớp chính xác.
- Khi có nhiều nguồn cấu hình, cần xác minh giá trị hiệu lực sau khi Spring Boot áp dụng thứ tự ưu tiên cấu hình. Không mặc định rằng logback.xml sẽ luôn ưu tiên hơn mọi thuộc tính logging.level.
- Có thể điều chỉnh level tại runtime bằng công cụ quản trị được hỗ trợ, chẳng hạn endpoint quản trị loggers của Spring Boot Actuator khi đã được cấu hình và bảo vệ phù hợp. Thay đổi động có thể chỉ tồn tại trong vòng đời tiến trình, tùy cách triển khai; phải có cơ chế hoàn nguyên và đồng bộ các instance nếu cần.

**Ví dụ tình huống:** Khi điều tra thanh toán chậm, bật DEBUG riêng com.example.shop.payment trong một khoảng thời gian ngắn; giữ package framework ở INFO hoặc WARN và không bật toàn bộ ROOT=DEBUG trên production. Kết thúc điều tra, hoàn nguyên level và kiểm tra log có thể chứa dữ liệu nhạy cảm.

## 11. Chọn mức cho từng nhánh logger

Không có một mức cố định đúng cho mọi ứng dụng. Một bảng định hướng:

| Nhánh logger | Mức nền gợi ý | Khi cần thay đổi |
| --- | --- | --- |
| ROOT | INFO | WARN nếu lưu lượng log quá lớn và có cơ chế quan sát thay thế phù hợp |
| Business service | INFO | DEBUG tạm thời để truy vết nhánh lỗi |
| Repository/SQL | INFO hoặc WARN | DEBUG theo đúng logger của thư viện để chẩn đoán truy vấn |
| Framework/library ồn ào | WARN | INFO/DEBUG khi điều tra lỗi tích hợp |
| Audit | Chính sách riêng | Bảo đảm đích và tính bền vững phù hợp yêu cầu nghiệp vụ |
| Security/Authentication | INFO/WARN theo chính sách | Tăng chi tiết có kiểm soát, tránh log token, mật khẩu, thông tin nhạy cảm |

Các mức này là ví dụ thảo luận, **không phải cấu hình bắt buộc**. Với một số ứng dụng, INFO của repository vẫn quan trọng; với thư viện SQL, tên logger cần bật có thể khác nhau theo phiên bản. Đọc tài liệu framework và kiểm tra tên logger thực xuất trước khi áp dụng.

Một lỗi phổ biến là cố sửa vấn đề hiệu năng bằng cách hạ mọi level về ERROR, từ đó đánh mất thông tin cần thiết khi xảy ra sự cố. Ngược lại, bật TRACE cho toàn bộ package rộng có thể gây tăng CPU, I/O, kích thước log và lộ dữ liệu. Chọn đúng nhánh logger thường giải quyết được cả hai vấn đề.

## 12. Kiểm tra tính đúng của cấu hình

Dùng bài test có ít nhất hai nhánh logger và các sự kiện tại nhiều level. Với cấu hình ROOT=INFO, payment=DEBUG, repository=WARN, audit=INFO + additivity=false, kiểm tra:

1. **Khớp tên:** tên logger lấy từ code có đúng package/class đã khai báo trong cấu hình không? Tên có phân biệt chữ hoa/chữ thường.
2. **Kế thừa:** một lớp chưa cấu hình riêng nhận mức của tổ tiên gần nhất, không tự bật DEBUG chỉ vì có một lớp cùng package khác bật DEBUG.
3. **Ghi đè:** lớp hoặc package con khai báo level riêng phải có effective level tương ứng.
4. **Đường xuất:** payment DEBUG được phép đến CONSOLE nếu appender không có filter riêng ngăn lại.
5. **Chặn theo level:** repository INFO không phát; repository WARN/ERROR được phép.
6. **Additivity:** audit chỉ tới AUDIT_FILE; không đồng thời ra CONSOLE, và không bị mất hoàn toàn do thiếu appender.
7. **Handler/Appender threshold:** test mức log phù hợp nhưng vẫn không xuất khi sink được chủ động cấu hình filter — điều này chứng minh kết quả phụ thuộc cả hai lớp.
8. **Reload/Deployment:** kiểm tra cấu hình đang thực sự được nạp trong tiến trình và trên từng instance, không chỉ file trong source repository.

Khi kiểm thử log có timestamp, thread ID hay asynchronous appender, tránh so sánh toàn bộ stdout một cách cứng nhắc. Ưu tiên xác minh **mức, logger name, nội dung, số lần xuất và đích**. Nếu có appender async, chờ flush hoàn tất hoặc dừng context sạch trước khi đối chiếu số bản ghi.

## 13. Các lỗi thường gặp và cách điều tra

### Bật DEBUG nhưng không thấy log

Kiểm tra theo thứ tự:

- Logger name thực tế có đúng nhánh khai báo không? Ví dụ com.example.shop.payment khác com.example.shop.paymentx.
- Có một cấu hình level cụ thể hơn ở tên lớp con đang ghi đè cấu hình package không?
- Cấu hình file nào được nạp, có profile hoặc nguồn thuộc tính nào ghi đè giá trị không?
- Có filter, appender threshold, JUL Handler level hoặc chức năng sampling nào loại sự kiện không?
- Logger có additivity=false nhưng thiếu appender/handler riêng không?
- Log đã enqueue nhưng chưa flush, hoặc sink bị lỗi ghi/thu thập không?

### Một dòng log xuất hiện hai lần

Kiểm tra các appender được gắn ở logger con và các tổ tiên, additivity mặc định và việc route cùng sự kiện đến nhiều sink rồi lại gom về một hệ thống log tập trung. Lỗi có thể là cấu hình trùng appender hoặc duplicate ở collector; không kết luận ngay rằng hàm nghiệp vụ chạy hai lần.

### Đặt level cho package nhưng không ảnh hưởng mọi class

Kiểm tra tên logger. Nếu code tạo logger bằng tên tùy biến, chẳng hạn LoggerFactory.getLogger("paymentFlow"), cấu hình com.example.shop.payment sẽ không tác động. Cũng cần xem có override trực tiếp tại logger con và cấu hình runtime khác không.

### Tắt log nhưng vẫn thấy một số dòng

Có thể các dòng đó đến từ logger khác, logging bridge khác, System.out/System.err, framework khởi động trước khi logging được thiết lập hoặc đích collector riêng. Phân biệt logging API đang dùng và backend thực tế. Không giả định mọi dữ liệu stdout đều đi qua logger của ứng dụng.

### Cấu hình đồng loạt làm hệ thống chậm

Bật DEBUG/TRACE ở nhánh rộng tạo thêm việc định dạng, I/O, lưu trữ và chi phí thu thập. Với tham số tính toán đắt, có thể kiểm tra trước:

~~~java
// Đoạn minh họa dùng SLF4J trong một phương thức:
if (log.isDebugEnabled()) {
    log.debug("Diagnostic state: {}", buildExpensiveDiagnosticState());
}
~~~

Dùng guard khi việc tạo tham số log thực sự tốn chi phí; tránh đưa logic có side effect vào biểu thức chỉ phục vụ log. Đừng dùng DEBUG hoặc TRACE để ghi thông tin bí mật.

## 14. Cách tổ chức cấu hình dễ bảo trì

- Chọn cách đặt tên logger nhất quán: ưu tiên tên class/package để cấu hình dễ dự đoán; dùng tên đặc biệt chỉ khi có lý do rõ.
- Thiết lập chính sách root tương đối ổn định. Ghi đè có phạm vi nhỏ ở những package cần khác biệt.
- Tách chính sách mức log khỏi đường xuất: dùng logger level cho verbosity, appender + additivity/filter cho định tuyến.
- Khi định tuyến riêng như audit, khai báo appender rõ ràng và kiểm tra dữ liệu không bị thất lạc khi additivity=false.
- Ghi chú lý do và thời hạn của các cấu hình DEBUG/TRACE tạm thời; hoàn nguyên sau điều tra.
- Bảo vệ cấu hình runtime và endpoint đổi level, tránh người không có quyền bật logging nhạy cảm hoặc làm nghẽn hạ tầng.
- Dùng metric/trace độc lập cho tín hiệu vận hành quan trọng; logging có thể bị lọc, trễ hoặc không khả dụng.

**Quy tắc cần nhớ:** đặt **level** tại logger để chọn độ chi tiết, dùng **kế thừa** để áp dụng theo package, dùng **additivity và appender** để định tuyến đầu ra. Khi log thiếu hoặc trùng, hãy kiểm tra cả ba thay vì chỉ nhìn vào ROOT level.

## 15. Tài liệu tham khảo

- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, effective level, basic selection rule, appender additivity.
- [Logback Manual — XML Configuration](https://logback.qos.ch/manual/configuration-xml.html): cú pháp logger, root và appender.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): Logger, Root, AppenderRef, additivity và filter.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): parent, setLevel, isLoggable, useParentHandlers.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging.level, cấu hình theo package/class và môi trường chạy.
