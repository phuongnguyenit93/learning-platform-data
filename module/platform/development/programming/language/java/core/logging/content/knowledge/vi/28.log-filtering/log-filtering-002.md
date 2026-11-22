# Filter theo level trong Java Logging

## 1. Khái niệm và mục đích

**Filter theo level** là cơ chế quyết định sự kiện log có được tiếp tục xử lý hoặc xuất ra đích ghi dựa trên **mức độ quan trọng (severity/level)** của sự kiện. Ví dụ, trong môi trường production, ứng dụng thường muốn lưu `INFO`, `WARN` và `ERROR`; khi điều tra lỗi, kỹ sư có thể mở `DEBUG` cho một package cụ thể mà không bật DEBUG cho tất cả thư viện.

Một lệnh ghi log đi qua nhiều chặng, thường được biểu diễn như sau:

```text
Mã nghiệp vụ
  │
  ├─ logger.debug("...") / logger.info("...")
  ▼
Kiểm tra mức hiệu lực ở logger
  │
  ├─ Bị chặn: không chuyển sự kiện xuống appender
  ▼
Bộ lọc bổ sung (nếu cấu hình)
  │
  ▼
Appender / handler / destination
  │
  ├─ Bộ lọc theo level dành riêng cho đích ghi
  ├─ Bộ lọc điều kiện khác (nếu có)
  ▼
Formatter / encoder / I/O → console, file, collector
```

**Hai quyết định khác nhau cần phân biệt:**

1. **Logger có cho phép phát sự kiện ở level đó không?** Đây thường là kiểm tra sớm và rẻ, dựa vào *effective logger level*.
2. **Đích ghi cụ thể có chấp nhận sự kiện đã qua logger không?** Một file appender có thể chỉ giữ WARN trở lên trong khi console giữ INFO trở lên. Mức của appender/handler và các filter của nó quản lý bước này.

Tên API, thời điểm kiểm tra và khả năng filter cho phép vượt qua mức logger có thể khác giữa Logback, Log4j2 và `java.util.logging` (JUL). Không coi mọi thư viện là một pipeline giống hệt nhau: ví dụ Log4j2 có global filter có thể ảnh hưởng cả quyết định theo logger level; Logback có TurboFilter ở tầng sớm.

## 2. Các mức log và nguyên tắc ngưỡng

Trong SLF4J với backend như Logback, các mức thường gặp tăng theo mức nghiêm trọng:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

Ví dụ khi **logger có ngưỡng INFO** và không có filter đặc biệt can thiệp:

| Event level | Được logger cho qua? | Giải thích |
| --- | --- | --- |
| TRACE | Không | Thấp hơn INFO |
| DEBUG | Không | Thấp hơn INFO |
| INFO | Có | Đúng ngưỡng |
| WARN | Có | Nghiêm trọng hơn INFO |
| ERROR | Có | Nghiêm trọng hơn INFO |

Khi đặt `WARN`, thông thường chỉ WARN và ERROR đi qua. Khi đặt `DEBUG`, DEBUG/INFO/WARN/ERROR đi qua; TRACE vẫn bị chặn. Điều này là **so sánh ngưỡng**, không có nghĩa “chỉ nhận đúng sự kiện mang tên INFO”.

**Filter chính xác theo level** là quy tắc khác: cấu hình “chỉ INFO” có thể cho phép INFO, nhưng từ chối cả DEBUG, WARN và ERROR ở vị trí filter đó. Không được nhầm *exact match* với *threshold*.

Các mức đặc biệt:

- `ALL`: thường đại diện cho việc cho phép mọi mức có thể ghi trong cơ chế tương ứng.
- `OFF`: thường đại diện cho việc tắt ghi log tại ngưỡng/đối tượng tương ứng.
- Log4j2 có thêm `FATAL`, thường nghiêm trọng hơn ERROR. Logback-classic không có một mức FATAL chuẩn riêng trong tập mức trên.
- JUL dùng các tên `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, cùng `OFF` và `ALL`. Thứ tự severity giữa các framework **không được so sánh trực tiếp bằng tên hay con số nội bộ**.

Các framework hoặc plugin có thể hỗ trợ level tùy chỉnh. Khi đó cần đối chiếu thứ tự ưu tiên theo tài liệu của backend đang chạy, không tự suy từ tên chuỗi.

## 3. Level ở logger và effective level

Logger thường có tên phân cấp, chẳng hạn:

```text
ROOT
└── com.example
    └── com.example.payment
        └── com.example.payment.gateway
```

Giả sử:

- Root logger đặt `WARN`.
- `com.example.payment` đặt `DEBUG`.
- `com.example.payment.gateway` không đặt mức riêng.

Khi sử dụng cơ chế kế thừa level thông thường, logger gateway có **effective level DEBUG**, vì nó kế thừa từ logger payment gần nhất có mức được định nghĩa. Logger khác dưới root không có mức riêng sẽ kế thừa WARN.

Trong Logback, *basic selection rule* được áp dụng tại logger thực sự nhận lời gọi ghi log, dựa trên level hiệu lực của logger đó. Nếu logger con có DEBUG và gọi `debug(...)`, việc sự kiện lan lên appender của root theo `additivity` **không làm root áp dụng lại ngưỡng WARN để loại sự kiện ấy**. Muốn appender root chỉ nhận WARN trở lên, cần filter tại chính appender hoặc có bố trí appender phù hợp.

Ví dụ:

```text
com.example.payment = DEBUG
ROOT                = WARN

payment.debug(...) ─► được logger payment cho qua
                    └─► appender kế thừa từ ROOT
                        ├─ không có filter WARN: có thể ghi DEBUG
                        └─ có ThresholdFilter WARN: chặn DEBUG
```

Hiểu nhầm phổ biến là nghĩ “root WARN luôn loại mọi DEBUG ở mọi logger con”. Điều đó không đúng cho trường hợp kế thừa appender ở Logback như ví dụ.

## 4. Lọc level ở appender hoặc handler

Appender/handler kiểm soát việc xuất dữ liệu. Đây là nơi phù hợp khi các đích ghi có mục đích khác nhau, ví dụ:

- Console giữ từ `INFO` trở lên để quan sát tiến trình chạy.
- File lưu trữ sự cố giữ từ `WARN` trở lên.
- File phục vụ phân tích ngắn hạn cho riêng package payment có thể mở `DEBUG`.
- Một appender chuyên thu log nghiệp vụ định dạng riêng có thể chỉ nhận một loại event, nhưng nên cân nhắc thêm marker hoặc trường cấu trúc nếu chỉ level chưa diễn đạt đủ ý nghĩa.

**Lưu ý thứ tự chặn:** nếu logger đã chặn DEBUG, thêm filter DEBUG ở appender thường không thể “khôi phục” DEBUG đó. Muốn ghi DEBUG vào một đích, phải kiểm tra cả quyết định ban đầu của logger và các bộ lọc trên đường tới đích.

Ví dụ theo ngưỡng:

| Logger hiệu lực | Đích ghi | Ngưỡng đích | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- | --- |
| DEBUG | Console | INFO | Bị chặn ở đích | Ghi | Ghi | Ghi |
| DEBUG | File cảnh báo | WARN | Bị chặn ở đích | Bị chặn ở đích | Ghi | Ghi |
| INFO | File debug | DEBUG | Bị chặn ở logger | Ghi | Ghi | Ghi |

Bảng giả định appender/handler chỉ có threshold nêu trên, không có filter khác, sink hoạt động bình thường. “Ghi” ở đây nghĩa là **đủ điều kiện được gửi tới sink**; nó không bảo đảm dữ liệu đã bền vững trên đĩa hay được collector lập chỉ mục.

## 5. Logback: ThresholdFilter theo ngưỡng

Ví dụ cấu hình `logback.xml` sau dùng Logback-classic, với **một console appender giữ WARN trở lên**, trong khi logger của package payment mở DEBUG để có thể dùng một appender khác khi cần.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Với log gọi từ `com.example.payment.CheckoutService`:

```java
// Trích đoạn minh họa cho ứng dụng có SLF4J và Logback, không phải file Java độc lập.
private static final org.slf4j.Logger LOG =
    org.slf4j.LoggerFactory.getLogger(CheckoutService.class);

LOG.debug("payment gateway selected");  // logger cho qua, console chặn
LOG.info("checkout accepted");          // logger cho qua, console chặn
LOG.warn("payment is slow");            // console nhận
LOG.error("payment failed");            // console nhận
```

**Kết quả dự kiến trên console** là WARN và ERROR, khi không có filter khác. Các timestamp, tên logger và vị trí thực của output phụ thuộc môi trường nên không gán một stdout cứng cho đoạn tích hợp này.

`ThresholdFilter` của Logback chặn sự kiện **thấp hơn** ngưỡng; với sự kiện tại hoặc cao hơn ngưỡng, nó trả về `NEUTRAL` để cho các bộ lọc tiếp theo tiếp tục quyết định. Đây là điểm cần chú ý: “qua threshold filter” chưa phải giấy phép bỏ qua toàn bộ filter còn lại.

Nếu không đặt appender threshold, root appender ở ví dụ trên có thể nhận cả DEBUG từ logger con nhờ additivity dù root có level INFO. Cần kiểm tra thực tế nếu vừa có filter vừa có cấu hình logger con đặc biệt.

## 6. Logback: LevelFilter chỉ đúng một mức

Khi yêu cầu **chỉ ghi INFO** vào appender, thay bằng `LevelFilter`:

```xml
<configuration>
    <appender name="INFO_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>[%level] %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="INFO_ONLY"/>
    </root>
</configuration>
```

Với root DEBUG, các lời gọi DEBUG, INFO, WARN, ERROR đủ điều kiện qua logger; **chỉ sự kiện đúng INFO** được appender trên chấp nhận. Vì `onMismatch=DENY`, WARN và ERROR cũng bị loại khỏi **appender này**. Nếu cần lưu WARN/ERROR vào một đích riêng, phải cấu hình appender bổ sung.

### ACCEPT, DENY và NEUTRAL có nghĩa gì?

- `DENY`: từ chối event tại tầng filter đó; event không tiếp tục đi theo tuyến đó.
- `NEUTRAL`: filter không quyết định; chuyển cho các filter tiếp theo hoặc quy tắc mặc định của tầng hiện tại.
- `ACCEPT`: chấp nhận theo quy tắc xử lý của filter/tầng hiện tại, thường kết thúc đánh giá các filter tiếp theo trong cùng chuỗi hoặc vị trí áp dụng.

Từng framework và tầng lọc có cơ chế khác nhau. **ACCEPT ở appender không đảo ngược việc event đã bị chặn ở logger trước đó**; đồng thời không bảo đảm sink ghi thành công. Không nên dùng ACCEPT/NEUTRAL như từ đồng nghĩa với “đã in ra console”.

Logback còn có **TurboFilter** đánh giá sớm hơn bộ lọc trên appender. Một số chính sách TurboFilter trả ACCEPT có thể ảnh hưởng cách lựa chọn theo logger level, nên quy tắc “logger level là cổng bất khả vượt qua” không đúng cho mọi cấu hình Logback nâng cao.

## 7. Log4j2: ThresholdFilter, LevelMatchFilter và các vị trí đặt filter

Trong Log4j2 Core, có thể đặt filter ở **toàn cục**, **LoggerConfig**, **AppenderRef** hoặc **Appender**. Kết quả cuối phụ thuộc vị trí và các filter đi trước. Tài liệu Log4j2 mô tả rõ global filter được áp dụng trước; tùy kết quả, nó có thể làm quyết định sau đó khác so với chỉ nhìn logger level.

Ví dụ `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <ThresholdFilter level="WARN"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.payment" level="DEBUG"/>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Với các event từ package payment và không có filter khác:

- DEBUG, INFO: không qua threshold WARN của console.
- WARN, ERROR, FATAL: đủ điều kiện qua console.
- Level của package payment khác root và quyết định kích hoạt logging ban đầu của package đó theo cấu hình Log4j2.

Ở Log4j2, `ThresholdFilter` cho khớp khi event có độ nghiêm trọng **bằng hoặc cao hơn** ngưỡng đã chọn; `LevelMatchFilter` khớp **chính xác một level**. Ví dụ chỉ INFO:

```xml
<!-- Đặt bên trong một Appender tương thích -->
<LevelMatchFilter level="INFO"
                  onMatch="ACCEPT"
                  onMismatch="DENY"/>
```

Đây chỉ là **trích đoạn cấu hình filter**, không phải một file `log4j2.xml` đầy đủ. Muốn dùng phải đặt trong appender/tầng phù hợp.

**Khác với Logback:** mặc dù cùng chữ `ThresholdFilter` và cùng tên các level phổ biến, cấu hình, vị trí filter, mặc định `onMatch`/`onMismatch` và đường đi sự kiện của Log4j2 là hợp đồng riêng. Không sao chép một cấu hình XML của Logback sang Log4j2.

## 8. Java Util Logging (JUL): Logger level và Handler level

JUL là hệ thống `java.util.logging` đi kèm JDK. Thay vì `Appender`, JUL dùng `Handler`. Logger có level hiệu lực, và mỗi Handler có level/Filter riêng.

Các level JUL thông dụng theo mức từ cao xuống thấp:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
```

`OFF` thường tắt logger; `ALL` cho phép các mức khả dụng. Khi gọi `logger.setLevel(null)`, logger kế thừa level hiệu lực của cha gần nhất có mức cụ thể.

Một điểm khác biệt về tên là **JUL FINE gần với mục đích ghi chi tiết như DEBUG**, nhưng không có quy tắc ánh xạ 1:1 cho mọi event khi dùng logging bridge. Nếu dùng SLF4J/JUL bridge, hãy kiểm tra phần nào làm bộ lọc thực tế và backend nào xuất log.

Ngoài kiểm tra level, JUL cho phép gắn `java.util.logging.Filter` vào Logger hoặc Handler để lọc dựa trên `LogRecord`. Đó là bước bổ sung; Handler filter không thể làm hiển thị một event đã bị logger bỏ qua vì level.

## 9. Ví dụ Java 17 hoàn chỉnh: lọc ở logger và handler

Chương trình sau dùng **JDK thuần**, không cần Maven/Gradle hay thư viện ngoài. Handler ghi thẳng ra `System.out` để kết quả ổn định và dễ so sánh. Ví dụ lần lượt minh họa:

1. Logger chấp nhận từ `FINE`, nhưng handler chỉ nhận từ `WARNING`.
2. Hạ ngưỡng handler xuống `INFO` để nhận thêm INFO.
3. Nâng ngưỡng logger lên `WARNING`: INFO lại bị chặn ngay tại logger.
4. Gắn Filter chỉ nhận đúng `WARNING`, khác với threshold.

Lưu tệp **`LevelFilteringDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LevelFilteringDemo {
    private static final Logger LOG = Logger.getLogger("demo.payment");

    private static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.WARNING);
        }

        @Override
        public void publish(LogRecord record) {
            // Handler tự bảo vệ điều kiện nhận event.
            if (isLoggable(record)) {
                System.out.println(
                    record.getLevel().getName() + " | " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false); // Không in trùng qua root handlers.
        StdoutHandler handler = new StdoutHandler();
        LOG.addHandler(handler);

        try {
            System.out.println("A: logger=FINE, handler=WARNING");
            LOG.setLevel(Level.FINE);
            LOG.fine("detail A");            // Handler chặn.
            LOG.info("order created A");     // Handler chặn.
            LOG.warning("slow partner A");   // Được ghi.
            LOG.severe("failed A");          // Được ghi.

            System.out.println("B: logger=FINE, handler=INFO");
            handler.setLevel(Level.INFO);
            LOG.fine("detail B");            // Handler vẫn chặn.
            LOG.info("order created B");     // Được ghi.
            LOG.warning("slow partner B");   // Được ghi.

            System.out.println("C: logger=WARNING, handler=INFO");
            LOG.setLevel(Level.WARNING);
            LOG.info("order created C");     // Logger chặn.
            LOG.warning("slow partner C");   // Được ghi.

            System.out.println("D: exact WARNING filter");
            LOG.setLevel(Level.ALL);
            handler.setLevel(Level.ALL);
            LOG.setFilter(record -> record.getLevel() == Level.WARNING);
            LOG.info("order created D");     // Filter chặn.
            LOG.warning("slow partner D");   // Được ghi.
            LOG.severe("failed D");          // Filter chặn.
        } finally {
            LOG.setFilter(null);
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 LevelFilteringDemo.java
java LevelFilteringDemo
```

Kết quả stdout **chính xác**:

```text
A: logger=FINE, handler=WARNING
WARNING | slow partner A
SEVERE | failed A
B: logger=FINE, handler=INFO
INFO | order created B
WARNING | slow partner B
C: logger=WARNING, handler=INFO
WARNING | slow partner C
D: exact WARNING filter
WARNING | slow partner D
```

Giải thích:

- Ở **A**, logger chấp nhận FINE/INFO/WARNING/SEVERE nhưng handler ở ngưỡng WARNING chặn hai event đầu.
- Ở **B**, việc đổi ngưỡng handler sang INFO làm INFO xuất hiện; FINE vẫn không đủ ngưỡng của handler.
- Ở **C**, dù handler cho INFO, logger đã nâng ngưỡng lên WARNING nên INFO không tới handler.
- Ở **D**, logger và handler đều cho phép mọi level, nhưng `Logger#setFilter(...)` chỉ cho sự kiện có `Level.WARNING` đi qua. Vì vậy SEVERE cũng bị chặn, chứng minh **exact match khác threshold**.
- `setUseParentHandlers(false)` tắt chuyển tiếp sang các handler cha, tránh dòng ngoài dự kiến. Handler tự định dạng message nên output không có timestamp bất định.

Ví dụ chạy trên JDK thuần, **không** chứng minh Logback/Log4j2 có cùng API hay cùng thứ tự filter nội bộ. Trong ứng dụng thật, nên cấu hình logging framework đang dùng và thử đúng backend.

## 10. Chọn ngưỡng phù hợp theo môi trường và mục tiêu

Một chính sách thường dùng, không phải chuẩn bắt buộc:

| Môi trường | Ngưỡng thường gặp | Ý nghĩa |
| --- | --- | --- |
| Local development | DEBUG hoặc INFO | Quan sát luồng xử lý khi phát triển |
| CI/test | INFO hoặc WARN với log theo test | Giữ tín hiệu lỗi mà không gây quá nhiều nhiễu |
| Production thông thường | INFO | Ghi trạng thái vận hành và cảnh báo/lỗi |
| Production khi điều tra có thời hạn | DEBUG cho package cụ thể | Thu thêm dữ liệu cho một nhóm chức năng |
| Production sink dành cho cảnh báo | WARN hoặc ERROR | Chỉ giữ các sự kiện mức cao tại sink này |

Lựa chọn không chỉ dựa vào “production = WARN”. Nếu loại toàn bộ INFO, hệ thống có thể mất sự kiện quan trọng để điều tra như “request accepted”, “job completed”, version triển khai hoặc audit event được thiết kế ở INFO.

Ngược lại, giữ mọi DEBUG trong production có thể làm tăng I/O, dung lượng, chi phí lưu trữ, độ trễ ứng dụng và rủi ro đưa dữ liệu nhạy cảm vào log. Nên phân biệt **log nghiệp vụ/audit** với log chẩn đoán thông thường, không dựa duy nhất vào mức để bảo đảm lưu trữ bắt buộc.

## 11. Thay đổi level trong ứng dụng Spring Boot

Với Spring Boot dùng Logback hoặc Log4j2 qua starter tương ứng, có thể đặt cấu hình mức logger như:

```properties
# application.properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
logging.level.org.springframework.web=WARN
```

Các khóa này điều chỉnh level ở phạm vi logger. Nếu appender của backend có filter riêng, việc đặt DEBUG cho package payment vẫn **chưa chắc** khiến DEBUG xuất hiện ở mọi sink.

Với Spring Boot Actuator và endpoint `loggers` được bật, phân quyền và bảo vệ, người vận hành có thể đọc/đổi level khi JVM đang chạy:

```http
GET /actuator/loggers/com.example.payment
```

Phản hồi thường thể hiện:

- `configuredLevel`: level khai báo trực tiếp cho logger, có thể `null`.
- `effectiveLevel`: level thực tế sau kế thừa.

Đặt DEBUG tạm thời:

```http
POST /actuator/loggers/com.example.payment
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Gửi `{"configuredLevel":null}` để xóa level gán trực tiếp theo hợp đồng endpoint, cho phép áp dụng mức kế thừa tương ứng. Đây là thay đổi **runtime**, không tự động sửa file cấu hình startup.

Cần kiểm soát quyền truy cập endpoint ghi cấu hình, ghi nhận thời gian và người thực hiện, đặt lịch hoàn nguyên và tránh bật DEBUG trên root nếu không cần. Trong hệ thống nhiều instance, thay đổi trên một instance không mặc định áp dụng sang tất cả instance.

## 12. Hiệu năng: lọc sớm và chi phí tạo log

### Filter ở logger và filter ở sink không tương đương về chi phí

Khi logger loại một sự kiện ngay từ kiểm tra mức ban đầu, framework thường tránh tạo hoặc chuyển log event đầy đủ. Nếu logger đã cho qua nhưng appender sau đó mới chặn, hệ thống có thể đã tốn chi phí tạo event, chụp context, định dạng một phần, xếp hàng và đi qua filter.

Vì thế:

- Dùng logger level để giới hạn lượng log tổng thể khi không cần sự kiện ở mức thấp.
- Dùng appender/handler level khi **các đích ghi cần chính sách khác nhau**.
- Đo CPU, allocation, queue depth, dropped events và sink I/O trước khi tăng lượng DEBUG/TRACE.
- Đừng giả định việc đặt ngưỡng WARN ở file appender sẽ làm mọi lời gọi DEBUG “miễn phí” nếu logger vẫn bật DEBUG.

### Tham số hóa chưa bảo đảm lời gọi tốn kém bị hoãn

Trong SLF4J, cú pháp có placeholder giúp framework trì hoãn một phần định dạng message:

```java
// Trích đoạn SLF4J: đối số đắt tiền vẫn được tính trước khi gọi method.
logger.debug("Snapshot: {}", buildExpensiveSnapshot());
```

Java sẽ tính `buildExpensiveSnapshot()` **trước** khi gọi `debug(...)`, ngay cả khi DEBUG bị tắt. Với phép tính thực sự đắt:

```java
// Trích đoạn SLF4J: chỉ tạo dữ liệu khi DEBUG được bật ở logger.
if (logger.isDebugEnabled()) {
    logger.debug("Snapshot: {}", buildExpensiveSnapshot());
}
```

`isDebugEnabled()` phản ánh khả năng ghi ở tầng logger theo hợp đồng API/backend; filter bổ sung ở appender vẫn có thể bỏ event. Đừng dùng cờ này như bằng chứng rằng file hoặc collector chắc chắn nhận sự kiện.

Trong JUL, có thể dùng overload nhận `Supplier<String>` để chỉ tạo message khi level cần thiết theo cơ chế của JUL:

```java
// Trích đoạn JUL cho Java 17+; logger là java.util.logging.Logger.
logger.fine(() -> buildExpensiveSnapshot());
```

Các ví dụ trên minh họa chi phí tính dữ liệu; chúng không phải ba chương trình độc lập. Chú ý dữ liệu capture trong lambda và thread safety nếu code thực tế sử dụng async logging.

## 13. Không dùng level làm chính sách bảo mật hoặc lưu trữ duy nhất

Level chỉ diễn tả **mức ưu tiên quan sát**, không xác thực tính nhạy cảm của dữ liệu hay độ tin cậy pháp lý. Các lưu ý:

- `DEBUG` có thể vô tình chứa token, cookie, mật khẩu hoặc dữ liệu cá nhân. Bật DEBUG để điều tra phải đi cùng quy tắc che/redact dữ liệu.
- `ERROR` không phải bằng chứng tự động có sự cố nghiêm trọng: một lỗi dự kiến trong nghiệp vụ có thể được ghi ERROR do lựa chọn chưa hợp lý.
- `INFO` không mặc định là log audit đáng tin. Audit event có thể cần cơ chế lưu bền vững, phân quyền, kiểm toàn vẹn và retention riêng.
- Một alert dựa trên số lượng `ERROR` có thể mất tín hiệu nếu logger/appender đang chặn hoặc sai cấu hình; nên đối chiếu metric, trace và kiểm thử cảnh báo.
- Các sự kiện bị lọc ở nguồn **không thể phục hồi** chỉ bằng thay filter của collector phía sau.

Nếu yêu cầu là “chỉ lưu sự kiện giao dịch thất bại”, level có thể không đủ: cần event type/status có cấu trúc hoặc marker/attribute phù hợp. Đừng ép mọi log lỗi nghiệp vụ phải mang ERROR để đáp ứng điều kiện lọc.

## 14. Các lỗi thường gặp khi lọc theo level

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy DEBUG dù đã đặt logger DEBUG | Appender threshold INFO/WARN; filter khác chặn; cấu hình chưa reload | Kiểm tra effective level và toàn bộ tuyến logger → appender |
| Đặt root WARN nhưng vẫn thấy DEBUG | Logger con có DEBUG và kế thừa appender không có threshold (ví dụ Logback) | Kiểm tra logger con, additivity và appender filters |
| Chỉ INFO, mất cả ERROR | Dùng exact `LevelFilter` thay vì threshold | Đổi thành threshold nếu mục tiêu là INFO trở lên |
| Đổi filter ở sink nhưng throughput không cải thiện | Event vẫn được tạo/xếp hàng trước bước lọc | Đo allocation/queue, cân nhắc lọc sớm ở logger |
| Có log INFO trong console nhưng file không có | Console và file dùng threshold/filter khác nhau | So cấu hình từng appender |
| Logger level hiển thị null | Đang kế thừa từ cha | Xem effective level |
| Đặt WARN nhưng vẫn không thấy ERROR | Filter DENY khác, sink lỗi, log không được tạo, appender chưa gắn | Kiểm tra internal status, appender và test event |
| Sau restart lại bật INFO thay cho DEBUG | Đổi runtime level nhưng không đổi nguồn startup | Kiểm tra file cấu hình và cơ chế khởi tạo |
| Tăng DEBUG gây chậm ứng dụng | I/O/queue quá tải, producer bị block hoặc format nặng | Đo CPU, queue, latency, sink throughput |
| Log xuất ra trùng dòng | Nhiều appender được gắn hoặc additivity | Kiểm tra tuyến appender và `additivity=false` khi phù hợp |
| Log từ thư viện không đổi mức như mong đợi | Logging bridge/backend khác hoặc tên logger sai | Xác định backend thực, logger name và cấu hình |
| Sau khi lọc level, mất dữ liệu để điều tra | Ngưỡng quá cao hoặc retention không phù hợp | Đánh giá lại nhu cầu INFO/WARN và đường thu thập metric/trace |

## 15. Cách kiểm thử cấu hình filter đúng yêu cầu

Một kiểm thử đáng tin phải kiểm tra đủ tổ hợp **logger level × appender/handler level × filter bổ sung**.

1. **Tạo dữ liệu thử có đủ level.** Phát TRACE/DEBUG/INFO/WARN/ERROR hoặc bộ mức tương ứng của JUL, mỗi event có ID riêng; biết rõ logger nào phát.
2. **Kiểm tra ngưỡng bằng một bảng kỳ vọng.** Với INFO, INFO/WARN/ERROR đủ điều kiện; với WARN, WARN/ERROR đủ điều kiện. Nếu có exact-match, chỉ mức được nêu nên xuất hiện ở sink đó.
3. **Kiểm tra kế thừa.** Đặt root WARN, logger con DEBUG; xem mức hiệu lực của con và đường appender/handler để tránh kết luận sai.
4. **Kiểm tra nhiều sink độc lập.** Console và file có thể có quy tắc khác nhau; xác nhận event đến đúng sink thay vì chỉ “có xuất hiện ở đâu đó”.
5. **Kiểm tra thay đổi runtime/reload.** Thay INFO→DEBUG rồi hoàn nguyên, xem trạng thái hiệu lực và event thực tế; xác nhận cả restart nếu yêu cầu cấu hình lưu lâu dài.
6. **Kiểm tra overload.** Khi DEBUG tăng mạnh, đo độ trễ, queue depth, số log bị drop và I/O; với async logging, không coi đã enqueue là đã lưu bền vững.
7. **Kiểm tra chặn dữ liệu nhạy cảm.** Phát log thử không chứa secret thật; xác nhận masking và quyền truy cập sink được áp dụng kể cả khi mở DEBUG.

Một ca kiểm thử có thể viết kỳ vọng ngắn:

```text
Logger package = DEBUG
Appender console threshold = INFO
Appender file threshold = WARN

DEBUG -> không ra console/file
INFO  -> chỉ ra console
WARN  -> ra console và file
ERROR -> ra console và file
```

Nếu kết quả không khớp, lần lượt xác định event có được tạo, logger có cho qua, appender được gắn đúng, filter có chặn hay không, rồi sink có ghi thành công không.

## 16. Nguyên tắc ghi nhớ

- **Threshold** nghĩa là “từ mức này trở lên”; **exact match** nghĩa là “chỉ đúng mức này” tại filter đó.
- **Effective logger level** kiểm soát phát sinh/đi tiếp ở tầng logger; appender/handler filter kiểm soát từng đích ghi.
- **Root logger level không đồng nghĩa một ngưỡng áp lại trên mọi event từ logger con**, nhất là khi có additivity và level override.
- Logback, Log4j2 và JUL có API/mặc định/tầng lọc khác nhau; phải đối chiếu theo **backend thực tế**.
- Filter chỉ quyết định đường đi của event; không bảo đảm sink đã ghi, không bù cho retention, không thay thế chính sách bảo mật.
- Khi debug production, mở level ở phạm vi nhỏ, có thời hạn, quan sát chi phí và hoàn nguyên.

**Ghi nhớ:** muốn hiểu vì sao một dòng log có hay không có mặt, hãy kiểm tra cả **mức phát sinh của logger**, **các filter trên tuyến tới appender/handler**, và **tình trạng thực tế của sink**. Ba lớp này giải thích hầu hết sự cố “đã bật log nhưng không thấy log”.

### Tài liệu kỹ thuật

- [Logback — Filters, LevelFilter, ThresholdFilter](https://logback.qos.ch/manual/filters.html)
- [Logback — Logger level, basic selection và additivity](https://logback.qos.ch/manual/architecture.html)
- [Apache Log4j2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html)
- [Oracle Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
