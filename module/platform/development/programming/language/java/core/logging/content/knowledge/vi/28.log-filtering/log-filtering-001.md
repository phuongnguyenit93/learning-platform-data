# Filter log là gì? Cơ chế lọc sự kiện trong Java Logging

## 1. Khái niệm và mục đích

**Filter log** (lọc log) là cơ chế kiểm tra một lời gọi ghi log hoặc một sự kiện log theo điều kiện đã định, sau đó quyết định sự kiện đó có được tiếp tục xử lý, chuyển đến một đích xuất hoặc bị loại bỏ hay không.

Ví dụ, cùng một ứng dụng có thể ghi rất nhiều sự kiện:

~~~text
DEBUG  | SQL parameters for order 42
INFO   | Order 42 created
INFO   | healthcheck: ok
WARN   | Payment provider is slow
ERROR  | Payment failed
~~~

Chính sách mong muốn có thể là: console chỉ nhận WARN/ERROR; file nghiệp vụ nhận INFO trở lên nhưng bỏ healthcheck lặp lại; một kênh chẩn đoán chỉ nhận DEBUG của một package đang gặp lỗi. Các kết quả đó đòi hỏi chọn đúng **vị trí lọc** và **điều kiện lọc**.

Filtering có ba lợi ích chính:

1. **Giảm nhiễu:** ẩn những log có ít giá trị quan sát (ví dụ request healthcheck lặp liên tục).
2. **Giảm chi phí:** ít sự kiện hơn phải format, ghi ra file, truyền mạng, lập chỉ mục và lưu trữ.
3. **Điều khiển luồng log:** cho phép từng đích nhận loại sự kiện phù hợp, ví dụ console vận hành và file audit có chính sách riêng.

Tuy nhiên, lọc quá mạnh có thể che giấu lỗi; và **lọc log không tự bảo đảm bảo mật dữ liệu hoặc không mất log**. Đây là quyết định về khả năng quan sát, phải được kiểm thử theo nhu cầu của hệ thống.

## 2. Log đi qua những lớp nào?

Một luồng logging Java dùng facade như SLF4J và backend như Logback hoặc Log4j 2 thường có các quyết định sau:

~~~text
Ứng dụng gọi logger.debug/info/warn/error(...)
                         |
                         v
                Logger có bật level?
                         |
             +-----------+-----------+
             |                       |
           Không                    Có
             |                       |
         Bỏ qua                Kiểm tra filter
                                     |
                    +----------------+----------------+
                    |                                 |
                   DENY                           Cho đi tiếp
                    |                                 |
                 Bỏ qua                       Tạo/chuyển LogEvent
                                                      |
                                               Chọn appender
                                                      |
                                           Appender filter/threshold
                                                      |
                                          Encoder / writer / sink
                                                      |
                                        File, console, log collector
~~~

Đây là sơ đồ khái niệm. **Thứ tự thực tế khác nhau theo backend và nơi filter được gắn**: Logback có TurboFilter hoạt động trước khi tạo sự kiện, filter thông thường ở appender; Log4j 2 có filter tại context, logger, appender reference và appender; JUL có Filter ở logger hoặc Handler.

Không có quy tắc đơn giản rằng “mọi filter đều chạy sau kiểm tra level”. Một số filter chạy rất sớm và có thể ảnh hưởng việc chấp nhận sự kiện trước bước kiểm tra level thông thường. Khi gặp kết quả bất ngờ, cần đọc đúng pipeline của backend và phiên bản đang dùng.

## 3. Phân biệt level, filter, appender và sampling

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Logger level** | Lời gọi ở mức độ này có được bật tại logger phát không? | ROOT=INFO, package payment=DEBUG |
| **Filter** | Sự kiện có thỏa điều kiện cụ thể để đi tiếp không? | Bỏ thông điệp healthcheck; chỉ nhận log có marker AUDIT |
| **Appender/Handler** | Sự kiện đi tới đích nào? | Console, file, broker, HTTP sink |
| **Appender threshold** | Đích đó chấp nhận từ mức nào? | File chỉ nhận WARN và ERROR |
| **Sampling/rate limiting** | Giữ bao nhiêu sự kiện theo tỷ lệ hoặc giới hạn tốc độ? | Chỉ giữ 1% event chẩn đoán |
| **Masking/redaction** | Giá trị nhạy cảm được xử lý thế nào trước khi xuất? | Thay token bằng [REDACTED] |

**Level** là một điều kiện lọc phổ biến, nhưng filter linh hoạt hơn: có thể xét marker, MDC/ThreadContext, nội dung thông điệp, nguồn phát, tenant, request path, hoặc thông tin ngữ cảnh. Tùy thư viện, điều kiện có thể đánh giá trước hoặc sau khi thông điệp được format.

**Không đồng nhất lọc với định tuyến.** Nếu một event bị từ chối ở appender CONSOLE, nó vẫn có thể được gửi tới appender FILE. Nhưng nếu event bị loại ngay tại logger hoặc filter toàn cục, mọi appender phía sau có thể không bao giờ nhận được.

## 4. Các điều kiện lọc thường gặp

### 4.1. Theo mức độ nghiêm trọng

Chỉ nhận WARN/ERROR cho console vận hành:

~~~text
DEBUG  -> bỏ
INFO   -> bỏ
WARN   -> nhận
ERROR  -> nhận
~~~

Đây là **lọc theo ngưỡng**. Nó khác với **lọc đúng một mức**:

~~~text
Chỉ nhận WARN:
DEBUG -> bỏ
INFO  -> bỏ
WARN  -> nhận
ERROR -> bỏ
~~~

Sự khác biệt này rất quan trọng khi dùng Logback: ThresholdFilter với mức WARN thường cho WARN trở lên; LevelFilter với mức WARN có thể được cấu hình để chỉ cho WARN và loại cả ERROR.

### 4.2. Theo logger name hoặc package

Ví dụ chỉ bật DEBUG cho com.example.payment, giữ package org.hibernate ở WARN. Trường hợp này có thể giải quyết gọn bằng cấu hình level theo logger, không nhất thiết phải viết một filter tùy chỉnh.

Tên logger thường được lấy theo tên đầy đủ của lớp, nhưng có thể là tên được lập trình viên đặt thủ công. Phải đối chiếu tên thực tế; tên package gần giống không tự động khớp.

### 4.3. Theo nội dung hoặc mã sự kiện

Ví dụ loại message bắt đầu bằng "healthcheck:", hoặc nhận các event có eventCode="PAYMENT_RETRY".

Lọc chuỗi dựa trên nội dung đã format dễ trở nên mong manh: thông điệp thay đổi, địa phương hóa, tham số khác định dạng hoặc case khác có thể làm filter sai. Khi ứng dụng hỗ trợ log có cấu trúc, ưu tiên filter trên **thuộc tính có nghĩa ổn định** như eventCode, marker và context field.

### 4.4. Theo ngữ cảnh: MDC/ThreadContext

Trong Logback, MDC là dữ liệu ngữ cảnh thường được gắn theo thread, ví dụ correlationId hoặc tenant. Log4j 2 có ThreadContext (context map) phục vụ mục đích tương tự.

Ví dụ có thể lọc riêng các event của một loại job:

~~~text
eventCode=IMPORT_PROGRESS, jobType=BULK -> có thể giảm hoặc sampling
eventCode=IMPORT_FAILED,   jobType=BULK -> vẫn giữ
~~~

Cần bảo đảm ngữ cảnh được truyền đúng qua thread pool hoặc xử lý async và được dọn sau request. Một filter phụ thuộc MDC rỗng hoặc bị rò sang request khác có thể loại sai sự kiện.

### 4.5. Theo marker, tần suất hoặc đích nhận

- **Marker:** tag có cấu trúc gắn vào lời gọi log, ví dụ SECURITY_ALERT; filter so khớp marker theo API của backend.
- **Burst/rate:** giới hạn số event thuộc nhóm có thể bỏ trong khoảng thời gian, nhưng cần biết phần nào bị mất.
- **Per-appender:** console chỉ nhận WARN+, file chuyên dụng nhận toàn bộ sự kiện phù hợp. Nếu event đã bị loại ở một tầng trước appender, appender chuyên dụng cũng không thể lấy lại nó.

## 5. Kết quả filter: nhị phân và ba trạng thái

Ở JUL, interface java.util.logging.Filter có phương thức isLoggable(LogRecord) trả về **boolean**:

- **true:** filter này cho phép record đi tiếp tới bước xử lý tương ứng;
- **false:** record bị filter từ chối ở vị trí đó.

Logback và Log4j 2 dùng cơ chế phổ biến có ba kết quả:

| Kết quả | Ý nghĩa cơ bản |
| --- | --- |
| **DENY** | Loại sự kiện tại tầng đang kiểm tra |
| **NEUTRAL** | Không quyết định; tiếp tục xét các điều kiện/filter kế tiếp |
| **ACCEPT** | Chấp nhận ở giai đoạn filter hiện tại theo quy tắc của backend |

**NEUTRAL không có nghĩa là DENY.** Nếu filter không khớp và trả về NEUTRAL, quyết định thường được chuyển cho filter tiếp theo hoặc quy tắc mặc định. Ngược lại, **ACCEPT không phải lời hứa rằng event chắc chắn đã được ghi bền vững**: một tầng sau hoặc chính appender vẫn có thể từ chối/lỗi.

Với Logback appender filter, các filter chạy theo thứ tự: DENY dừng và bỏ; ACCEPT dừng chuỗi filter của appender đó và cho đi tiếp; NEUTRAL xét tiếp. Với Log4j 2, ngữ nghĩa chi tiết tùy giai đoạn. Ví dụ filter toàn cục trả ACCEPT có thể ảnh hưởng bước kiểm tra level ban đầu, nhưng các filter và đích xuất phía sau vẫn có quyền quyết định. Vì vậy không dùng ACCEPT một cách tùy tiện để “bắt buộc” ghi mọi thông điệp.

## 6. Ví dụ Java 17+ chạy độc lập: lọc bằng java.util.logging

Ví dụ sau dùng **JUL**, API logging có sẵn trong JDK. Nó minh họa hai tầng độc lập: logger cho phép mọi level; handler chỉ nhận INFO trở lên và dùng một filter để bỏ thông điệp healthcheck.

Tạo file **LogFilterDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogFilterDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.orders");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        // Handler này in ra stdout để kết quả dễ kiểm tra.
        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        console.setLevel(Level.INFO);
        console.setFilter(record ->
                !record.getMessage().startsWith("healthcheck:"));

        logger.addHandler(console);

        try {
            logger.fine("debug details");      // handler loại: dưới INFO
            logger.info("order=42 created");  // được nhận
            logger.info("healthcheck: ok");   // filter từ chối
            logger.warning("payment delayed");// được nhận
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LogFilterDemo.java
java LogFilterDemo
~~~

Stdout:

~~~text
INFO | order=42 created
WARNING | payment delayed
~~~

Tại sao kết quả có đúng hai dòng?

1. logger đặt Level.ALL nên các lời gọi FINE, INFO, WARNING đều đủ điều kiện ở **tầng logger**.
2. Handler đặt Level.INFO. Vì thế FINE không được in ngay cả khi logger cho phép.
3. Filter trên Handler xét LogRecord, loại thông điệp bắt đầu bằng healthcheck:.
4. WARNING không khớp điều kiện loại nên đi qua Handler.
5. setUseParentHandlers(false) tắt việc chuyển tiếp lên handler của root, tránh một số dòng vô tình in thêm với định dạng mặc định.

**Chi tiết kỹ thuật quan trọng:** Handler.publish() do ta tự viết nên phải gọi isLoggable(record). Đây là phương thức của Handler xét cả level và Filter được gắn vào Handler. Nếu custom handler bỏ qua bước này, việc setLevel/setFilter có thể không tạo tác dụng như mong muốn. Với handler có sẵn của JDK, thư viện tự xử lý theo implementation của handler.

Ví dụ cố ý dùng **filter trên Handler**. JUL cũng hỗ trợ Logger.setFilter(Filter). Nếu một sự kiện bị loại ngay tại logger, các handler không có cơ hội nhận nó; còn filter trên một handler chỉ kiểm soát đầu ra của handler đó.

## 7. Ví dụ đổi chính sách mà không đổi lời gọi log

Giả sử yêu cầu mới là nhận **mọi log INFO trở lên**, không muốn loại healthcheck nữa:

~~~java
// Đoạn minh họa dùng các biến trong ví dụ bên trên.
console.setFilter(null);       // Bỏ filter nội dung.
console.setLevel(Level.INFO);  // Vẫn giữ ngưỡng INFO.
~~~

Nếu muốn kiểm tra **chỉ các sự kiện WARNING trở lên** tại handler:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
console.setLevel(Level.WARNING);
~~~

Nếu muốn loại các message bắt đầu "healthcheck:" ở **mọi handler** thuộc một logger JUL, có thể đặt filter tại logger thay vì từng handler:

~~~java
// Đoạn minh họa, trong nơi đang cấu hình logger.
logger.setFilter(record ->
        !record.getMessage().startsWith("healthcheck:"));
~~~

Tuy nhiên phương án filter chuỗi trên LogRecord.getMessage() phù hợp để học và thử nghiệm đơn giản. Trong hệ thống thực, getMessage() có thể là **template chưa format** với tham số kèm theo; không nên dùng phép so khớp này để xác nhận đã che mọi dữ liệu nhạy cảm hoặc mọi biến thể thông điệp.

## 8. Logback: filter ở appender và TurboFilter

Logback Classic thường làm backend cho ứng dụng gọi SLF4J. Logback có hai nhóm chính:

- **Appender filter thông thường:** hoạt động trên ILoggingEvent đã tạo, gắn với một appender cụ thể. Nếu appender CONSOLE loại event, một appender FILE khác vẫn có thể nhận event đó.
- **TurboFilter:** được gắn ở LoggerContext và có thể đánh giá lời gọi log rất sớm, với các tham số như logger, level, marker, format và arguments. TurboFilter hữu ích khi cần quyết định sớm, trước khi tạo LoggingEvent; kết quả ACCEPT/DENY/NEUTRAL có thể tương tác với kiểm tra level theo cơ chế Logback.

### 8.1. ThresholdFilter: lấy WARN trở lên

Ví dụ file **logback.xml**:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
      <level>WARN</level>
    </filter>
    <encoder>
      <pattern>%-5level %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

ROOT=DEBUG cho phép logger tạo sự kiện DEBUG trở lên theo chính sách thông thường. Tuy nhiên **Appender CONSOLE** có ThresholdFilter WARN nên bỏ DEBUG/INFO, cho WARN/ERROR đi tiếp. Nhờ đặt filter tại appender, một appender khác không có filter này có thể vẫn nhận INFO/DEBUG.

Bảng kết quả ở CONSOLE khi không có filter khác:

| Event | Kết quả |
| --- | --- |
| DEBUG | Bỏ |
| INFO | Bỏ |
| WARN | Nhận |
| ERROR | Nhận |

Để chỉ thay ngưỡng chung cho mọi đích, đặt ROOT=WARN thường đơn giản hơn. Filter ở appender phù hợp khi **các đích cần ngưỡng khác nhau**.

### 8.2. LevelFilter: chỉ nhận đúng một level

Nếu yêu cầu là chỉ xuất WARN và **không xuất ERROR** ở một appender, dùng LevelFilter:

~~~xml
<!-- Đặt bên trong phần tử <appender> của Logback. -->
<filter class="ch.qos.logback.classic.filter.LevelFilter">
  <level>WARN</level>
  <onMatch>ACCEPT</onMatch>
  <onMismatch>DENY</onMismatch>
</filter>
~~~

Đoạn trên là một fragment của **logback.xml**, cần được đặt đúng bên trong appender; không phải file XML độc lập. Khi event có level WARN, filter trả ACCEPT. Các level khác, gồm ERROR, trả DENY. Không thay LevelFilter cho ThresholdFilter nếu muốn giữ mọi cảnh báo và lỗi.

### 8.3. Kết hợp nhiều filter

Logback appender filters dùng cơ chế ba trạng thái. Nếu filter A trả NEUTRAL thì filter B có thể tiếp tục xét event; nếu A trả DENY thì event dừng; nếu A trả ACCEPT thì không cần xét tiếp các filter của cùng appender.

Ví dụ: filter A chỉ từ chối healthcheck và trả NEUTRAL với event khác; filter B chặn mọi mức dưới WARN. Kết quả: healthcheck bị loại, các sự kiện còn lại chỉ được in nếu WARN trở lên.

Cần đọc quy tắc từng loại filter: một filter trả ACCEPT quá sớm có thể khiến filter đặt sau không được áp dụng. Thứ tự các filter là một phần của chính sách.

## 9. Log4j 2: filter ở nhiều vị trí

Log4j 2 Core hỗ trợ filter tại:

1. **Context/global:** kiểm tra sớm trước khi xử lý cấu hình logger.
2. **LoggerConfig:** áp dụng điều kiện trên logger hoặc nhóm logger tương ứng.
3. **AppenderRef:** áp dụng khi chuyển event từ logger tới một appender tham chiếu.
4. **Appender:** áp dụng ở chính đích xuất.

Đặt filter càng sớm thường càng có khả năng tránh chi phí tạo event, lấy context, format và chuyển vào async queue; nhưng cũng có thể làm event biến mất khỏi **mọi đích**. Đặt filter ở appender cho phép chính sách riêng từng đích, đổi lại một số công việc logging đã xảy ra trước khi event tới đó.

Ví dụ **log4j2.xml** để CONSOLE chỉ nhận WARN trở lên:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <ThresholdFilter level="warn"
                       onMatch="NEUTRAL"
                       onMismatch="DENY"/>
      <PatternLayout pattern="%-5p %c - %m%n"/>
    </Console>
  </Appenders>

  <Loggers>
    <Root level="debug">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

ThresholdFilter tại appender trả DENY với mức dưới WARN; với WARN trở lên, NEUTRAL cho sự kiện tiếp tục quy trình appender. Trong cấu hình này, chỉ có một filter tại appender nên các event WARN/ERROR đủ điều kiện đi ra console.

Cũng có thể dùng **MarkerFilter**, **ThreadContextMapFilter**, **RegexFilter** và các filter khác của Log4j 2, tùy loại dữ liệu cần kiểm tra. Với các bộ lọc có onMatch/onMismatch, phải chú ý giá trị mặc định của **đúng loại filter** và sự khác nhau giữa ACCEPT/NEUTRAL; đừng suy luận rằng không viết onMismatch có nghĩa là event sẽ luôn đi tiếp.

**Không áp dụng trực tiếp XML của Logback sang Log4j 2** hoặc ngược lại. Ví dụ Logback dùng lớp ch.qos.logback.classic.filter.ThresholdFilter trong phần tử filter class; Log4j 2 dùng plugin XML ThresholdFilter với các thuộc tính riêng.

## 10. Spring Boot: logging.level có phải filter không?

Trong ứng dụng Spring Boot, có thể kiểm soát mức log theo package/logger qua **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.org.springframework.web=WARN
~~~

Hoặc qua **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
~~~

Các thuộc tính logging.level điều chỉnh **ngưỡng ở logger**. Chúng không tự tạo điều kiện kiểu “loại healthcheck nhưng giữ mọi INFO khác”. Muốn lọc theo nội dung, marker hoặc MDC ở appender, sử dụng **cấu hình backend** (thường là logback-spring.xml khi Spring Boot dùng Logback), hoặc code tích hợp có kiểm soát.

Cũng không nên bật DEBUG toàn bộ ROOT chỉ vì cần một package. Bật riêng logger cần điều tra giúp tránh tạo lưu lượng log lớn và vô tình xuất thông tin nhạy cảm từ các thư viện khác.

## 11. Khi một sự kiện có nhiều đích xuất

Xét hệ thống có:

~~~text
                    +--> CONSOLE (chỉ WARN+)
Logger INFO --------|
                    +--> APP_FILE (INFO+)
                    |
                    +--> AUDIT_FILE (event có marker AUDIT)
~~~

Event INFO nghiệp vụ có thể không xuất CONSOLE nhưng vẫn có trong APP_FILE. Event có marker AUDIT có thể được gửi thêm đến AUDIT_FILE nếu logger, filter và additivity/appenderRef được cấu hình phù hợp.

Vì vậy, cần tách ba câu hỏi khi nói “log bị filter”:

- **Không được tạo từ lời gọi log?** Xem logger level và filter sớm.
- **Đã tạo nhưng không tới một appender?** Xem appender reference, additivity và filter của appender đó.
- **Appender nhận rồi nhưng không thấy ở hệ thống tập trung?** Xem lỗi ghi, queue bất đồng bộ, file rotation, agent/collector, ingestion delay và truy vấn tìm kiếm.

Filter được cấu hình ở CONSOLE không bảo đảm event biến mất khỏi FILE. Ngược lại, filter sớm loại một sự kiện có thể khiến mọi appender mất cơ hội nhận event đó. Với hệ thống nhiều đường xuất, mô tả rõ **phạm vi áp dụng của mỗi filter**.

## 12. Khi nào nên viết filter tùy chỉnh?

Dùng logger level hoặc filter có sẵn nếu chỉ cần:

- Ngưỡng WARN/ERROR;
- Chỉ đúng một mức;
- So khớp marker hoặc trường context theo tính năng có sẵn;
- Lọc đơn giản theo một package hoặc đích appender.

Viết filter tùy chỉnh nếu quy tắc đòi hỏi biểu thức nghiệp vụ thật sự ổn định mà các cơ chế có sẵn chưa diễn đạt được, chẳng hạn giảm sự kiện tiến độ khi status=RUNNING nhưng luôn giữ khi status=FAILED.

Một custom filter nên có các đặc điểm:

- **Xử lý nhanh:** tránh gọi database/network, khóa lâu, format nặng hoặc truy xuất dữ liệu ngoài mỗi lần log.
- **An toàn khi đồng thời:** có thể được gọi từ nhiều thread, đặc biệt với logging hiệu năng cao và async.
- **Dễ kiểm chứng:** điều kiện rõ ràng, bao gồm trường hợp thiếu context, null hoặc định dạng không hợp lệ.
- **Có hành vi khi lỗi:** quyết định trước sẽ cho đi tiếp hay chặn khi filter gặp exception. Đừng âm thầm loại sự kiện quan trọng.
- **Không đệ quy logging:** viết log bên trong filter bằng cùng logger/backend có thể gây vòng lặp hoặc deadlock.
- **Có metric độc lập:** khi loại nhiều event, đếm số sự kiện đã bỏ, tránh chỉ báo bằng chính pipeline đang bị lọc.

Không nên nhét toàn bộ logic kinh doanh hoặc quyền truy cập vào filter logging: filter quyết định tính hiển thị của log, không phải công cụ kiểm soát quyền thực thi nghiệp vụ.

## 13. Filtering, sampling và dữ liệu cần lưu bền vững

Với lượng lớn sự kiện lặp, filter có thể kết hợp sampling hoặc rate limiting để giảm chi phí. Tuy nhiên:

- Sampling bỏ có chủ đích một phần event; không còn đủ số log để đếm chính xác từng nghiệp vụ bằng cách đếm dòng.
- Nếu cần đo số request hoặc số lỗi, dùng metrics/counters chuyên dụng và tracing có thiết kế phù hợp.
- Với audit, giao dịch tài chính hoặc bằng chứng bắt buộc phải lưu, **không dùng một filter có khả năng loại sự kiện hoặc queue logging trong RAM như nguồn dữ liệu duy nhất**. Cần kênh lưu bền vững có xác nhận, xử lý retry/duplicate và chính sách truy cập.
- Nếu filter theo tenant/user, bảo đảm không biến metadata chứa dữ liệu định danh nhạy cảm thành label metric có số lượng giá trị quá lớn hoặc làm lộ thông tin trong báo cáo.

Trong môi trường production, nên quy định rõ event nào được phép loại và event nào cần lưu đầy đủ. Bỏ mọi log dưới WARN có thể giảm chi phí tức thời nhưng cũng làm mất chuỗi sự kiện giúp điều tra nguyên nhân của một ERROR.

## 14. Filter không phải cơ chế che dữ liệu bí mật

Một hiểu nhầm nguy hiểm là: “Có filter loại log chứa chữ password nên có thể log toàn bộ request body”.

Không đúng. Filter chỉ kiểm tra những mẫu được lập trình viên dự đoán; dữ liệu bí mật có thể nằm ở trường khác, được viết bằng tên khác, xuất từ thư viện khác, hoặc tới appender khác trước khi filter chạy.

Để bảo vệ dữ liệu:

1. **Không đưa secret vào LogEvent ngay từ nguồn.** Tránh log password, token xác thực, API key, session cookie, dữ liệu thanh toán đầy đủ.
2. Với dữ liệu cần ghi nhưng phải bảo vệ, dùng quy trình **masking/redaction có cấu trúc** ở vị trí đáng tin cậy và test các trường hợp biên.
3. Kiểm tra mọi đích log, including console, file, lỗi ứng dụng, collector và bản ghi debug tạm thời.
4. Giới hạn quyền truy cập, thời gian lưu và khả năng tìm kiếm log theo chính sách dữ liệu.

Filter có thể hỗ trợ chính sách bảo vệ thông tin, nhưng **không thể thay thế quy tắc không ghi dữ liệu nhạy cảm ngay từ đầu**.

## 15. Kiểm thử filter bằng ma trận sự kiện

Không chỉ kiểm tra rằng một dòng bị bỏ; phải xác nhận các dòng **cần giữ** không bị loại nhầm.

Với chính sách mẫu “logger INFO+, console WARN+, file INFO+ nhưng không nhận healthcheck”, ma trận kỳ vọng:

| Sự kiện | Logger | Console | File |
| --- | --- | --- | --- |
| DEBUG, order detail | Không tạo | Không | Không |
| INFO, order created | Cho qua | Không | Có |
| INFO, healthcheck: ok | Cho qua | Không | Không |
| WARN, payment slow | Cho qua | Có | Có |
| ERROR, payment failed | Cho qua | Có | Có |

Đây là chính sách minh họa; backend phải cấu hình level và filter tại các tầng phù hợp mới cho kết quả như bảng.

Cách kiểm thử:

1. Phát các event có **eventCode và testRunId duy nhất**, tại TRACE/DEBUG/INFO/WARN/ERROR theo phiên bản backend.
2. Gắn cùng một bộ ngữ cảnh (MDC/ThreadContext) hợp lệ, thử cả trường hợp thiếu context và context sai.
3. Quan sát từng đích: console, file hoặc mock appender; không chỉ kiểm tra một nơi rồi kết luận toàn pipeline.
4. Kiểm tra ngưỡng chính xác (WARN so với ERROR), điều kiện match/mismatch, thứ tự nhiều filter và ảnh hưởng additivity.
5. Với async appender, chờ drain/flush hoặc đóng context đúng cách trước khi so sánh số event.
6. Đo chi phí dưới tải: nếu filter regex hoặc kiểm tra phức tạp chạy trên mọi event, so sánh latency và throughput trước/sau.
7. Kiểm tra mất context qua thread pool/async, filter trả về khi giá trị null, và thay đổi cấu hình trong các instance khác nhau.

Nên đối chiếu bằng ID sự kiện và loại event thay vì so khớp nguyên dòng chứa timestamp/thread name thay đổi liên tục.

## 16. Lỗi thường gặp khi cấu hình filter

### Bật DEBUG nhưng không thấy dòng DEBUG

Kiểm tra logger name, effective level, filter toàn cục, logger filter, appenderRef, appender filter/threshold và đích. Nếu một tầng sớm loại event, tăng level ở appender sau không thể khôi phục lại nó.

### WARN xuất hiện, ERROR lại biến mất

Có thể dùng **LevelFilter khớp chính xác WARN** với onMismatch=DENY thay vì **ThresholdFilter WARN**. Thử độc lập một WARN và một ERROR để xác nhận.

### Filter healthcheck ở console nhưng file vẫn có

Filter nằm trên appender CONSOLE, trong khi FILE là appender khác. Muốn điều chỉnh nhiều đích cần đặt policy tại đúng tầng, cẩn thận đừng loại các sự kiện cần cho audit hoặc điều tra.

### Viết custom handler nhưng setFilter không có tác dụng

Với JUL, nếu handler tự cài publish() mà không gọi isLoggable(record), handler có thể bỏ qua cả filter lẫn ngưỡng. Xem lại implementation của handler và so sánh với ví dụ Java ở trên.

### Log có vẻ đã bị loại nhưng thực ra chỉ đến muộn

Với logging bất đồng bộ, event có thể đang nằm trong queue, chưa flush, hoặc chưa được collector index. Không kết luận filter đã loại event khi chưa đo cả trạng thái queue và đích nhận.

### Có filter nhưng vẫn tốn CPU

Nếu filter chỉ đặt cuối pipeline tại appender, quá trình tạo event, tính toán tham số, context capture hoặc mã hóa có thể đã xảy ra. Với chi phí lớn, cân nhắc level phù hợp hoặc filtering sớm theo khả năng backend. Nhưng tối ưu sớm phải giữ đúng chính sách quan sát ở các đích.

### Filter theo message nhưng regex không khớp

Thông điệp có thể là template chưa format, chứa ký tự xuống dòng hoặc đã bị thay đổi bởi layout; tùy vị trí API có thể nhận raw format và arguments thay vì chuỗi cuối cùng. Ưu tiên marker/eventCode hoặc field có cấu trúc, và kiểm tra bằng dữ liệu thực ở đúng tầng.

## 17. Checklist khi đưa filter vào vận hành

- [ ] Mục tiêu lọc rõ: giảm nhiễu, giảm chi phí hay chia log theo đích?
- [ ] Xác định chính xác phạm vi: logger, toàn context, appenderRef hay một appender?
- [ ] Biết thứ tự level, filter và additivity của backend/version đang dùng.
- [ ] Hiểu khác biệt giữa **đúng một level** và **ngưỡng level trở lên**.
- [ ] Định nghĩa rõ hành vi match, mismatch, NEUTRAL và thứ tự filter.
- [ ] Có test giữ WARN/ERROR, test điều kiện ngược và test thiếu context.
- [ ] Không dùng log đã lọc để suy ra số giao dịch chính xác; có metrics khi cần.
- [ ] Không phụ thuộc filter để bảo vệ secret; đã tránh log dữ liệu bí mật ở nguồn.
- [ ] Có cách quan sát số event bị loại và hoàn nguyên cấu hình khi điều tra sự cố.

**Ghi nhớ:** Filter log là một **quy tắc chấp nhận hoặc loại sự kiện tại một vị trí cụ thể trong pipeline logging**. Muốn sử dụng đúng, cần hiểu đồng thời **điều kiện lọc, tầng áp dụng và đích xuất**; một event bị loại ở một đích không nhất thiết bị loại ở mọi đích.

## Tài liệu tham khảo

- [Oracle Java SE 17 — java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html): Filter.isLoggable(LogRecord).
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): Handler level, setFilter và isLoggable.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html): Appender filter, TurboFilter, ACCEPT/DENY/NEUTRAL.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): vị trí áp dụng filter, kết quả ba trạng thái và thứ tự xử lý.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging.level và cấu hình logging backend.
