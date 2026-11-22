# Routing log trong Java: định tuyến và phân loại sự kiện

## 1. Routing log là gì?

**Routing log** (định tuyến log) là việc quyết định **một sự kiện logging sẽ được gửi đến đâu**, có thể qua một hoặc nhiều đích nhận: console, file, luồng `stdout`/`stderr`, hệ thống giám sát, collector, message broker hoặc một kênh lưu trữ chuyên biệt. Quyết định thường dựa trên **mức độ nghiêm trọng**, **tên logger/package**, **loại sự kiện**, **marker** hoặc **ngữ cảnh nghiệp vụ**.

Ví dụ, một dịch vụ đặt hàng có thể áp dụng các quy tắc:

- Log INFO/DEBUG phục vụ vận hành thông thường được gửi đến kênh **application**.
- Log WARN/ERROR được gửi thêm đến kênh **alert** để hệ thống giám sát chú ý.
- Sự kiện kiểm toán như thay đổi quyền hoặc hoàn tiền đi qua kênh **audit** riêng, bất kể được phát sinh từ thành phần nào.
- Log chứa dữ liệu nhạy cảm cần được loại bỏ hoặc che thông tin **trước khi phát ra** bất kỳ đích nào.

Luồng xử lý khái niệm:

```text
Code nghiệp vụ -> Logger -> kiểm tra mức/Filter -> Routing
                                                  |
                         +------------------------+-----------------------+
                         |                        |                       |
                    APPLICATION                 ALERT                   AUDIT
                    console/file              warn/error            audit sink
                         |                        |                       |
                         +------------------------+-----------------------+
                                                  |
                                            Log collector
```

Đây là sơ đồ ý tưởng; một kiến trúc thực tế có thể định tuyến ngay trong JVM, ở agent thu thập log hoặc trong hệ thống tập trung. **Routing không mặc nhiên là lọc bỏ:** một sự kiện có thể được gửi đến **nhiều đích** (fan-out), hoặc chỉ một đích (exclusive routing), tùy quy tắc thiết kế.

**Phân loại** trả lời “log này thuộc nhóm nào?”; **định tuyến** trả lời “log này đi đến kênh nào?”. Một sự kiện có thể được phân loại bằng level và tên logger nhưng vẫn cần cấu hình appender/handler để biết nơi nó được ghi.

## 2. Các thành phần tham gia routing

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Logger | Nơi code gửi sự kiện; thường có tên dạng phân cấp | `com.example.orders.PaymentService` |
| Level | Phân loại mức nghiêm trọng/chi tiết | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| Filter | Quyết định chấp nhận/từ chối một sự kiện theo luật | Chỉ nhận từ WARN trở lên |
| Handler / Appender | Đích xử lý sự kiện log | JUL `Handler`; Logback/Log4j 2 `Appender` |
| Formatter / Encoder / Layout | Mã hóa thông điệp cho đích nhận | Plain text, pattern, JSON |
| MDC / ThreadContext | Thuộc tính ngữ cảnh gắn với sự kiện | `requestId`, `service`, `operation` |
| Marker hoặc event type | Nhãn biểu đạt loại sự kiện độc lập với level | `SECURITY`, `AUDIT` |
| Collector/agent | Gom, phân tích hoặc chuyển tiếp log ra ngoài JVM | Dịch vụ thu thập và lưu trữ log |

Có hai tầng quyết định thường bị nhầm:

1. **Logger có tạo/cho qua sự kiện không?** Ví dụ logger có mức INFO thường không phát sự kiện DEBUG.
2. **Sự kiện đã tạo đi đến appender/handler nào?** Một appender có thể có filter riêng, đường ghi riêng và chính sách xử lý lỗi riêng.

Nếu sự kiện đã bị chặn ở tầng logger thì chỉ thêm appender bên dưới thường **không thể khôi phục nó**. Ngược lại, logger cho phép INFO không bảo đảm một handler nhận INFO nếu handler chỉ nhận WARN trở lên.

### 2.1. Routing theo level

Một quy tắc phổ biến là:

```text
INFO, DEBUG   -> application
WARN, ERROR   -> application + alert
AUDIT         -> audit (phân loại bằng logger/marker riêng)
```

Lưu ý: nếu WARN/ERROR được chuyển vào cả `application` và `alert`, hệ thống **cố ý có hai bản sao ở hai đích**. Đây là fan-out. Nếu yêu cầu chỉ một đích, phải xây **quy tắc loại trừ** cho các đích; không thể chỉ thêm một threshold filter cho `alert` rồi mặc định `application` không còn WARN/ERROR.

Level phù hợp để đánh giá mức nghiêm trọng, nhưng không đủ để phân biệt loại nghiệp vụ: một `INFO` có thể là log thông thường hoặc là sự kiện audit quan trọng.

### 2.2. Routing theo tên logger và package

Các logger Java thường có tên dạng `com.example.payment`, `com.example.security`. Backend có thể cấu hình riêng cho tên hoặc nhánh tên:

```text
com.example.audit.*       -> audit sink
com.example.integration.* -> integration sink
root / còn lại            -> application sink
```

Điểm mạnh là không cần thay đổi lời gọi `logger.info(...)` ở từng nơi nếu kiến trúc đã định nghĩa ranh giới package/logger hợp lý. Tuy nhiên, package Java không nhất thiết trùng ranh giới nghiệp vụ. Một class xử lý cả audit và hoạt động thông thường có thể cần **logger/marker tách riêng**, thay vì chuyển toàn bộ log của class đó sang audit.

### 2.3. Routing theo marker và context

**Marker** là nhãn sự kiện, ví dụ `SECURITY`. Trong API SLF4J có thể tạo marker và gắn vào lời gọi logging:

```java
import org.slf4j.Logger;
import org.slf4j.Marker;
import org.slf4j.MarkerFactory;

// Trong class có biến Logger log và dữ liệu event đã chuẩn bị:
Marker security = MarkerFactory.getMarker("SECURITY");
log.warn(security, "Authentication rejected for reason={}", reasonCode);
```

Đây là **đoạn tích hợp**, cần dependency SLF4J, biến `log` và `reasonCode`; không phải ứng dụng Java độc lập. Gắn marker **chưa tự động định tuyến**: backend phải có filter/rule nhận marker đó. Cũng cần kiểm tra provider có lưu hoặc xuất marker theo cách mong muốn hay không.

**MDC** (Mapped Diagnostic Context) hoặc **Log4j 2 ThreadContext** cung cấp các thuộc tính như `requestId` hoặc `tenantGroup`. Chúng giúp tìm kiếm và có thể hỗ trợ định tuyến theo ngữ cảnh, nhưng:

- Phải **truyền context** qua các ranh giới bất đồng bộ (executor, callback, reactive pipeline) theo cơ chế framework.
- Phải **dọn context** khi task kết thúc để worker thread tái sử dụng không mang nhầm giá trị.
- Không dùng giá trị tùy ý từ người dùng làm tên file, topic hoặc đường dẫn định tuyến; phải kiểm tra danh sách đích hợp lệ.
- Tránh tạo hàng nghìn appender/queue theo `requestId` hoặc mỗi tenant riêng nếu không có giới hạn và vòng đời xử lý.

## 3. Java 17: ví dụ định tuyến INFO và cảnh báo sang hai stream

`java.util.logging` (JUL) có sẵn trong JDK. Ta có thể cài đặt hai `Handler`: kênh `APP` nhận INFO, kênh `ALERT` nhận WARNING/SEVERE. Trong bài này, `APP` in ra `stdout`, còn `ALERT` in ra `stderr`.

Lưu tệp **`RoutingLogDemo.java`**:

```java
import java.io.PrintStream;
import java.util.function.Predicate;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RoutingLogDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler app = new LevelRouteHandler(
                System.out,
                "APP",
                level -> level.intValue() >= Level.INFO.intValue()
                        && level.intValue() < Level.WARNING.intValue());

        Handler alert = new LevelRouteHandler(
                System.err,
                "ALERT",
                level -> level.intValue() >= Level.WARNING.intValue());

        logger.addHandler(app);
        logger.addHandler(alert);
        try {
            logger.fine("hidden details");
            logger.info("Service started");
            logger.warning("Retry scheduled");
            logger.severe("Storage unavailable");
        } finally {
            logger.removeHandler(app);
            logger.removeHandler(alert);
            app.close();
            alert.close();
        }
    }

    private static final class LevelRouteHandler extends Handler {
        private final PrintStream destination;
        private final String channel;
        private final Predicate<Level> accepts;

        LevelRouteHandler(PrintStream destination,
                          String channel,
                          Predicate<Level> accepts) {
            this.destination = destination;
            this.channel = channel;
            this.accepts = accepts;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (record == null || !isLoggable(record)
                    || !accepts.test(record.getLevel())) {
                return;
            }

            destination.println(channel + " ["
                    + record.getLevel().getName() + "] "
                    + record.getMessage());
        }

        @Override
        public void flush() {
            destination.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac RoutingLogDemo.java
java RoutingLogDemo
```

Kết quả **`stdout`**:

```text
APP [INFO] Service started
```

Kết quả **`stderr`**:

```text
ALERT [WARNING] Retry scheduled
ALERT [SEVERE] Storage unavailable
```

Khi terminal hiển thị cả hai stream trên một màn hình, **thứ tự trộn `stdout`/`stderr` có thể khác nhau**; các khối trên mô tả nội dung mỗi stream, không bảo đảm thứ tự tổng thể. Ví dụ dùng thông điệp cố định để dễ đối chiếu.

Cơ chế thực thi:

1. `logger.setLevel(Level.INFO)` chặn sự kiện `FINE` trước khi đi đến handler.
2. `setUseParentHandlers(false)` ngăn truyền log qua handler của root JUL, tránh in trùng ngoài hai kênh do bài tự tạo.
3. Handler `APP` nhận các level từ INFO đến dưới WARNING; handler `ALERT` nhận WARNING trở lên. Cả hai dùng `Level.intValue()` để so sánh mức JUL.
4. Mỗi `Handler.publish(...)` kiểm tra trạng thái bằng `isLoggable(record)`, kiểm tra rule, rồi ghi ra stream đã được cấp. Đây là routing **exclusive** đối với các mức được dùng trong ví dụ.
5. `finally` gỡ handler tự tạo. `close()` ở ví dụ chỉ flush, **không đóng `System.out` hoặc `System.err`** là stream toàn tiến trình.

Trong hệ thống production, handler tùy chỉnh cần xem xét lỗi I/O, đồng bộ, hiệu năng, lifecycle và cách thông báo lỗi nội bộ mà không tạo vòng lặp log đệ quy. Ví dụ tập trung minh họa routing, không thay thế một backend logging hoàn chỉnh.

### 3.1. Tại sao không dùng đơn giản hai ConsoleHandler?

`ConsoleHandler` chuẩn của JUL mặc định xuất ra `System.err`. Hai `ConsoleHandler` thông thường có thể được lọc theo level nhưng vẫn cùng một stream. Muốn chuyển INFO sang `stdout` và cảnh báo sang `stderr` trong ví dụ độc lập, ta dùng handler rõ ràng về đích. Trong ứng dụng thực, Logback/Log4j 2 có appender console cấu hình trực tiếp từng stream, thường dễ sử dụng hơn.

## 4. Routing bằng Logback Classic

Khi ứng dụng dùng **SLF4J + Logback Classic**, ta có thể tách output bằng **appender** và **logger hierarchy**. Ví dụ sau là tệp `src/main/resources/logback.xml` của ứng dụng đã thêm dependency Logback tương thích:

```xml
<configuration>
    <appender name="APPLICATION"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>APP %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ALERT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>ALERT %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>AUDIT %d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit" level="INFO" additivity="false">
        <appender-ref ref="AUDIT"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
        <appender-ref ref="ALERT"/>
    </root>
</configuration>
```

**Diễn giải chính xác:**

- `APPLICATION` nhận các sự kiện đi tới root appender, không có filter riêng để loại WARN/ERROR.
- `ALERT` chỉ chấp nhận mức WARN trở lên nhờ `ThresholdFilter`.
- `AUDIT` nhận sự kiện của logger `com.example.audit` và các logger con kế thừa đường này, tùy cấu hình cụ thể.
- `additivity="false"` tại `com.example.audit` dừng việc lan truyền sự kiện từ nhánh audit lên appender của root. Nhờ vậy các sự kiện audit ở nhánh này không mặc nhiên đi sang `APPLICATION` và `ALERT`.
- Với logger thường có effective level INFO, `INFO` đi tới `APPLICATION`; `WARN` và `ERROR` đi tới **cả `APPLICATION` và `ALERT`**. Hai bản ghi ở hai stream là **fan-out được thiết kế chủ ý**.
- `root level="INFO"` không nhất thiết lọc lại log DEBUG đã được một logger con có level DEBUG chấp nhận rồi truyền theo additivity; muốn giới hạn tại appender cần filter tương ứng.

Đây là cấu hình định tuyến **trong JVM**. Nếu `stdout` và `stderr` được một collector gom vào cùng index, cần thêm nhãn `channel`/stream hoặc trường structured log để phân biệt; hai stream không tự động đồng nghĩa với hai nơi lưu trữ bền vững khác nhau.

### 4.1. Ghi log nghiệp vụ với logger riêng

Trong một ứng dụng có SLF4J, code minh họa:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AuditEvents {
    private static final Logger AUDIT =
            LoggerFactory.getLogger("com.example.audit");

    public void permissionChanged(String operationId) {
        AUDIT.info("Permission changed, operationId={}", operationId);
    }
}
```

Đây là class Java có thể biên dịch **trong dự án đã có SLF4J API**; cần runtime backend và cấu hình để log đến đích dự định. Theo cấu hình Logback ở trên, logger `com.example.audit` đi vào `AUDIT`.

Dùng tên logger riêng là một cách phân loại; **không đưa raw token, mật khẩu hoặc dữ liệu nhạy cảm vào thông điệp audit**. Đối với bản ghi kiểm toán bắt buộc giữ, console appender ở ví dụ chỉ minh họa đường đi, không tạo bảo đảm lưu trữ bền vững.

### 4.2. Additivity: lý do phổ biến khiến log bị lặp

Trong Logback, một logger con có thể chuyển sự kiện lên các appender của tổ tiên. Khi gắn appender vào logger con mà vẫn giữ additivity mặc định, sự kiện có thể được ghi bởi appender của chính logger và của root. Điều này không phải do code gọi `log.info(...)` hai lần.

Ví dụ cấu hình:

```xml
<logger name="com.example.audit" level="INFO">
    <appender-ref ref="AUDIT"/>
</logger>
```

Nếu bỏ `additivity="false"` và logger audit tiếp tục truyền sự kiện tới root, sự kiện có thể vào `AUDIT`, `APPLICATION`, và nếu từ WARN trở lên thì vào cả `ALERT`.

Cần quyết định rõ: muốn fan-out sang nhiều đích hay muốn nhánh audit có một đường riêng? Sau đó cấu hình additivity và filter nhất quán. Đặt `additivity="false"` cho mọi logger mà không có appender riêng có thể khiến sự kiện không còn đích nhận.

### 4.3. Routing theo mức log hoàn toàn loại trừ

Cấu hình `ALERT` có `ThresholdFilter` chỉ giới hạn **đích ALERT**, không tự loại cảnh báo khỏi `APPLICATION`.

Nếu muốn chỉ ghi INFO vào `APPLICATION`, còn WARN/ERROR chỉ vào `ALERT`, phải đặt quy tắc loại trừ ở `APPLICATION`. Có thể dùng `LevelFilter` với mức INFO và hành động chấp nhận/từ chối tương ứng cho trường hợp chỉ cần INFO, nhưng cần tính cả DEBUG/TRACE nếu các logger khác bật mức thấp hơn. Với quy tắc phức tạp, lựa chọn filter/evaluator phù hợp phiên bản backend và kiểm thử chính xác các mức.

## 5. Routing trong Log4j 2

**Log4j 2** có cơ chế appender, filter và logger hierarchy riêng. Không dùng class `ch.qos.logback.*` để cấu hình Log4j 2; backend nào đang hoạt động thì dùng đúng API và cấu hình của backend đó.

Ví dụ `log4j2.xml` dưới đây thể hiện cùng **fan-out** theo severity và tuyến riêng cho logger audit:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="APP" target="SYSTEM_OUT">
            <PatternLayout pattern="APP %-5p %c - %m%n"/>
        </Console>

        <Console name="ALERT" target="SYSTEM_ERR">
            <ThresholdFilter level="WARN"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="ALERT %-5p %c - %m%n"/>
        </Console>

        <Console name="AUDIT" target="SYSTEM_OUT">
            <PatternLayout pattern="AUDIT %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.audit"
                level="info"
                additivity="false">
            <AppenderRef ref="AUDIT"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="APP"/>
            <AppenderRef ref="ALERT"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là cấu hình cho ứng dụng có **Log4j 2 Core** tương thích. Ứng dụng phải có dependency và cung cấp file ở vị trí backend nạp. Log4j 2 còn có `RoutingAppender` cho các đích động (ví dụ phân nhóm theo thuộc tính), nhưng thiết kế đó phức tạp hơn vì phải quản lý số đích, tên file/topic, thời gian tồn tại của appender và giá trị context không tin cậy.

**Không được suy luận** rằng mọi ứng dụng dùng SLF4J sẽ hiểu cả Logback XML và Log4j 2 XML. SLF4J chỉ là API ghi log; provider/backend thực tế quyết định cách định tuyến.

## 6. Routing theo context: marker, request ID, tenant và audit

### 6.1. Context phục vụ tương quan, nhưng có thể hỗ trợ chọn đường

Một sự kiện có thể mang các trường:

```json
{
  "level": "WARN",
  "logger": "com.example.checkout.CheckoutService",
  "service": "checkout",
  "requestId": "req-123",
  "category": "PAYMENT",
  "message": "Payment provider timeout"
}
```

Đây là dữ liệu minh họa; trong thực tế không nên xây thủ công JSON trong từng lời gọi logger nếu backend đã hỗ trợ structured logging.

Quy tắc router có thể là:

- `category=PAYMENT` → đưa bản sao sang index vận hành thanh toán.
- `level>=WARN` → kênh cảnh báo.
- `category=AUDIT` → pipeline audit.
- `service=checkout` → thêm thuộc tính phân nhóm khi tập hợp ở collector.

**`requestId` thường dùng để liên kết sự kiện**, không nên dùng làm tên của một file/appender riêng cho mỗi request. Nếu một hệ thống có hàng triệu request, tạo hàng triệu đích sẽ làm cạn file descriptor, bộ nhớ và tài nguyên thu thập.

### 6.2. Ví dụ SLF4J MDC (đoạn mã tích hợp)

```java
import org.slf4j.MDC;

MDC.put("category", "PAYMENT");
MDC.put("requestId", requestId);

try {
    log.warn("Payment provider timed out, code={}", errorCode);
} finally {
    MDC.remove("category");
    MDC.remove("requestId");
}
```

Đoạn mã cần `log`, `requestId`, `errorCode` từ ứng dụng và một provider SLF4J hỗ trợ MDC. **Chỉ đặt MDC không tự tạo router**: Logback/Log4j 2 hay collector phải có rule sử dụng trường tương ứng.

Trong Java thread pool, dùng `finally` để dọn context giúp tránh để request mới thừa hưởng context cũ. Với `CompletableFuture`, executor hoặc reactive streams, context có thể không tự động xuất hiện tại thread khác. Cần sử dụng propagation phù hợp framework để log không bị phân loại sai.

### 6.3. Audit cần phân loại dựa trên ngữ nghĩa

Một audit event thường cần những trường như **ai**, **hành động gì**, **tài nguyên nào**, **thời gian**, **kết quả** và **mã tương quan**, nhưng phải tránh phát tán thông tin nhạy cảm không cần thiết. Đừng coi việc gọi `log.info(...)` trong class có tên `Audit` là đủ để đáp ứng yêu cầu kiểm toán.

Nếu hệ thống cần bằng chứng chống mất hoặc sửa log, cần thêm yêu cầu lưu bền vững, phân quyền đọc/ghi, retention, chứng thực tính toàn vẹn và kiểm tra đường nhận. Routing bằng console/file appender thông thường không tự đáp ứng các bảo đảm đó.

## 7. Routing trong JVM và routing tại collector

Định tuyến có thể xảy ra tại hai nơi hoặc phối hợp:

| Tiêu chí | Trong ứng dụng JVM | Ở collector/agent |
| --- | --- | --- |
| Thông tin sẵn có | Logger, level, marker, exception, MDC tại lúc tạo event | Các trường đã được serialize và truyền sang collector |
| Khả năng bỏ bớt log tại nguồn | Có, giúp giảm chi phí truyền log | Không khôi phục được CPU/băng thông đã dùng trước khi collector nhận |
| Quản lý quy tắc tập trung | Cần triển khai/cấu hình giữa nhiều instance | Dễ áp dụng chính sách chung cho nhiều dịch vụ |
| Tác động đến request | Handler/appender đồng bộ hoặc queue đầy có thể chặn producer | Thường gián tiếp qua agent/sink và cơ chế backpressure |
| Rủi ro mất thông tin | Filter tại nguồn loại vĩnh viễn event | Collector không thể phân loại bằng trường chưa được gửi hoặc đã bị xóa |

Một lựa chọn thực tế là **giữ cấu trúc log đầy đủ tại nguồn**, chỉ lọc những dữ liệu cần bỏ ngay, xuất log có schema ổn định và cho collector định tuyến tiếp tới từng index/sink. Tuy nhiên, các bản ghi yêu cầu bảo mật hoặc audit có thể cần đường riêng ngay từ ứng dụng.

Không dựa vào text parsing mơ hồ như “message chứa `error` thì chuyển sang alert” nếu đã có `level` và `category` dạng trường cấu trúc. Trích xuất bằng regex trên thông điệp dễ hỏng khi định dạng hoặc ngôn ngữ thay đổi.

## 8. Routing và logging bất đồng bộ

Khi appender/handler sử dụng queue để ghi log bất đồng bộ, routing cũng phải xét **tốc độ và sức chứa**:

```text
many producers -> routing / filters -> bounded queues -> sinks
                                   +-> queue A: application
                                   +-> queue B: alert
                                   +-> queue C: audit
```

Một log được router gửi tới ba đích **không có nghĩa cả ba đích sẽ nhận thành công**. Có thể một queue chấp nhận, queue khác đầy; một sink chậm nhưng các sink còn lại vẫn hoạt động. Nếu cần bảo đảm nhất quán giữa nhiều đích, đây là bài toán delivery semantics phức tạp hơn việc gắn nhiều appender.

Các quyết định quan trọng:

1. Queue có giới hạn bao nhiêu sự kiện/bộ nhớ, và khi đầy thì **block, timeout hay drop**?
2. Có chấp nhận WARN/ERROR bị bỏ khi sink quá tải không? Nếu không, cần đường bền vững, ngân sách độ trễ và chính sách lỗi cụ thể.
3. Ghi audit có phụ thuộc cùng queue với DEBUG/INFO không? Tách đường quan trọng có thể tránh log nhiễu ảnh hưởng audit, nhưng chưa bảo đảm chống mất khi process crash.
4. Khi shutdown, sự kiện tồn đọng được flush bao lâu, và nếu không kịp thì báo động thế nào?
5. Có metric đếm **accepted, dropped, written, delivery failed** riêng theo route không?

Cần phân biệt **đã nhận vào queue** với **đã lưu bền vững**. Bộ nhớ JVM, `stdout`, file system cache và collector có thể hỏng độc lập. Dữ liệu bắt buộc phải giữ cần pipeline phù hợp yêu cầu nghiệp vụ.

## 9. Thiết kế route để tránh rò rỉ thông tin

Định tuyến là một điểm kiểm soát **dòng chảy dữ liệu**. Nếu log gửi sang kênh cảnh báo hoặc hệ thống bên thứ ba, cần xác định dữ liệu nào được phép rời ứng dụng.

Nguyên tắc:

- Không ghi password, access token, secret hay dữ liệu cá nhân không cần thiết vào log ngay từ đầu; che/mask ở nguồn khi phù hợp.
- Không chọn file path, Kafka topic hoặc index trực tiếp từ chuỗi `tenantId`, `userId` hoặc HTTP header chưa kiểm tra.
- Không dùng `requestId` tùy ý làm nhãn metric hoặc tên appender vì cardinality cao.
- Áp dụng quyền truy cập, retention và xóa dữ liệu theo từng sink; `audit` và `application` có thể có yêu cầu khác nhau.
- Tránh tạo vòng lặp: appender lỗi rồi lại phát lỗi vào chính appender đó hoặc collector gửi lại log đã ingest.
- Giới hạn lượng log gửi đến kênh cảnh báo để tránh “alert storm”; cân nhắc aggregation/rate limiting nhưng vẫn bảo toàn tín hiệu quan trọng.

Một filter regex để che dữ liệu sau khi thông điệp được tạo có thể hữu ích nhưng không thay thế việc **không tạo log chứa secret** ngay từ đầu; exception, tham số và trường context cũng cần được xem xét.

## 10. Test routing có hệ thống

Kiểm thử nên xác định **đầu vào, số bản sao và đích nhận**. Một ma trận đơn giản:

| Event | APPLICATION | ALERT | AUDIT |
| --- | --- | --- | --- |
| Logger thường, INFO | Có | Không | Không |
| Logger thường, WARN | Có | Có | Không |
| Logger thường, ERROR | Có | Có | Không |
| Logger `com.example.audit`, INFO | Không | Không | Có |
| Logger `com.example.audit`, ERROR | Không | Không | Có |

Bảng trên đúng với cấu hình **Logback/Log4j 2 fan-out** đã minh họa (giả sử không có filter khác và các logger có level tương ứng). Ví dụ JUL ở mục 3 là **exclusive routing**, nên không dùng bảng này để dự đoán kết quả JUL.

Khi viết test integration, có thể:

1. Phát một event cho mỗi level và mỗi logger chính, rồi thu thập sự kiện tại từng appender/sink.
2. Đếm chính xác số bản sao và so sánh với ma trận. Không chỉ kiểm tra “có log” mà bỏ qua log trùng.
3. Kiểm tra logger con, root, `additivity=false` hoặc `setUseParentHandlers(false)` trong JUL.
4. Kiểm tra route theo marker/MDC với cả context **có giá trị**, **thiếu giá trị** và **giá trị không hợp lệ**.
5. Kiểm tra propagation qua executor và việc dọn context sau khi worker thread được tái sử dụng.
6. Giả lập sink chậm/không sẵn sàng để xác nhận timeout/drop/fallback theo từng route.
7. Kiểm tra graceful shutdown, flush, collector và retention ở mức mà hệ thống thực sự cam kết.
8. Chạy thử với log có dữ liệu nhạy cảm để xác nhận dữ liệu không xuất hiện ở kênh bị cấm.

Với log bất đồng bộ, test cần chờ cơ chế drain/flush đúng cách, không dùng `Thread.sleep(...)` một khoảng tùy ý rồi mặc định log đã đến đích.

### 10.1. Metrics vận hành gợi ý

Nếu framework/collector có hỗ trợ hoặc ứng dụng tự instrument, các chỉ số hữu ích gồm:

- `log_route_events_total{route,level}`: số sự kiện được định tuyến.
- `log_route_dropped_total{route,reason}`: số sự kiện bị loại hoặc bỏ do quá tải.
- `log_route_delivery_errors_total{route}`: lỗi ghi/gửi đến đích.
- `log_route_queue_depth{route}`: mức hàng đợi từng tuyến.
- `log_route_enqueue_latency_seconds{route}`: chi phí chờ để gửi vào queue.

Đây là **tên metric gợi ý**, không phải các metric tự có trong mọi logging backend. Không đưa thông điệp, request ID hay user ID vào label metric. Kiểm tra cả metrics và số log thực tế tại các đích vì một số lỗi truyền/ghi chỉ xuất hiện ở tầng sau.

## 11. Lỗi thường gặp

### Lỗi 1: “Đã gắn ALERT thì WARN không còn ở APPLICATION”

Sai nếu cả APP và ALERT đều nhận event và APP không có filter loại WARN. Đây là **fan-out**; cần filter loại trừ nếu muốn routing độc quyền.

### Lỗi 2: “Đặt root level INFO sẽ chặn DEBUG từ mọi logger con”

Trong Logback/Log4j 2, logger con có level DEBUG có thể tạo sự kiện DEBUG, và đường additivity có thể chuyển sự kiện đến appender ở root. Muốn giới hạn chắc chắn tại sink, kiểm tra filter/threshold của appender đó theo backend đang dùng. Trong JUL cũng cần hiểu logger-level và handler-level là hai bước riêng.

### Lỗi 3: “Log bị lặp là do gọi logger hai lần”

Có thể do appender gắn vào cả logger con và root, additivity, hoặc pipeline collector nạp một nguồn hai lần. Trước khi sửa code, kiểm tra sơ đồ tuyến và số appender thực sự nhận sự kiện.

### Lỗi 4: “Đặt MDC rồi thì router tự hiểu”

MDC là dữ liệu context; rule routing phải được cấu hình riêng. Trong async flow, context có thể không được truyền. Một tuyến dựa trên `category` thiếu giá trị cần có **default route** hoặc chính sách từ chối rõ ràng, tránh âm thầm làm mất log.

### Lỗi 5: “Đưa mỗi tenant vào file riêng chắc chắn an toàn hơn”

Nếu không giới hạn số file, đối tượng appender và kích thước dữ liệu, giải pháp có thể cạn tài nguyên hoặc cho phép path injection. Dùng các route hữu hạn đã được phê duyệt và enforce quyền truy cập tại nơi lưu.

### Lỗi 6: “Audit log đã đi console nên đủ tin cậy”

Không đúng với yêu cầu durable audit. Collector có thể ngừng, queue có thể đầy, tiến trình có thể bị kill và dữ liệu có thể bị sửa; yêu cầu audit thực sự cần thiết kế lưu trữ/chứng thực/kiểm soát quyền phù hợp.

### Lỗi 7: “Định tuyến càng nhiều sink càng tốt”

Fan-out tăng số lần serialize/write, băng thông, chi phí lưu trữ và điểm thất bại. Chỉ tạo những route có mục đích quan sát hoặc nghiệp vụ rõ ràng; lập ma trận event → sink để biết chi phí và chính sách retention.

## 12. Checklist trước khi triển khai

- Xác định **danh mục log**: application, alert, audit, security, integration… và tiêu chí phân loại rõ ràng.
- Vẽ ma trận **logger/level/marker/context → appender/sink**, ghi rõ tuyến độc quyền hay fan-out.
- Kiểm tra đúng backend đang hoạt động: JUL, Logback, Log4j 2 hay pipeline framework khác.
- Xác định cơ chế lọc ở **logger và appender**, cùng additivity/parent handler.
- Dùng schema structured log ổn định, gồm timestamp, level, logger, service và correlation ID khi phù hợp.
- Thiết lập quyền truy cập, mask dữ liệu, retention, bandwidth, queue và chính sách lỗi cho từng sink.
- Kiểm thử log trùng, log thiếu, context sai, sink lỗi, quá tải và shutdown.
- Giám sát lượng log bị drop, latency, queue và lỗi delivery theo route.

**Điểm cần nhớ:** Routing log quyết định **sự kiện nào đến đích nào**, còn phân loại cung cấp thông tin để ra quyết định. Trong Java, cần hiểu logger level, filter, handler/appender và cây logger. Một rule tốt phải mô tả rõ cả **đường đi thành công, khả năng ghi trùng, trường hợp thiếu context và hậu quả khi đích nhận bị lỗi**.
