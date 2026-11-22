# File log theo module trong Java: tách luồng log có kiểm soát

## 1. File log theo module là gì?

**File log theo module** là cách tổ chức logging để sự kiện phát ra từ các thành phần chức năng khác nhau của ứng dụng được ghi vào **các file log riêng**. “Module” trong bài này thường là **nhóm package, subsystem hoặc bounded context nghiệp vụ**, ví dụ `payment`, `inventory`, `notification`, `authentication`. Nó **không nhất thiết** là một Java Platform Module System (JPMS) có `module-info.java`.

Thay vì mọi sự kiện đều đi vào một file:

```text
logs/application.log
  INFO  event=payment.started requestId=req-17
  WARN  event=stock.low sku=sku-2
  ERROR event=payment.failed code=UPSTREAM_TIMEOUT
  INFO  event=email.sent notificationId=n-8
```

ứng dụng có thể chia:

```text
logs/
  payment.log
    INFO  event=payment.started requestId=req-17
    ERROR event=payment.failed code=UPSTREAM_TIMEOUT

  inventory.log
    WARN  event=stock.low sku=sku-2

  notification.log
    INFO  event=email.sent notificationId=n-8
```

Các dòng trên là **minh họa**. File thực tế có thể ghi timestamp, level, tên logger, thread, trace ID và stack trace theo formatter/encoder của hệ thống.

### Khi nào tách file có ích?

- Nhóm vận hành cần xem nhanh lỗi của một subsystem mà không phải lọc hàng triệu dòng chung.
- Các module có yêu cầu **retention**, quyền truy cập hoặc tần suất lưu khác nhau.
- Log của một module rất ồn, gây khó đọc hoặc làm tăng chi phí lưu cho những module khác.
- Một nhóm log có thể được chuyển qua pipeline/collector chuyên trách.
- Ứng dụng lớn chạy **một process** nhưng có nhiều nhóm chức năng và thực sự cần file vật lý riêng.

Tuy vậy, **tách file không tự động làm log an toàn hơn hoặc hiệu quả hơn**. Trong nhiều môi trường container và cloud, một stream JSON ra stdout kết hợp trường `module`/`logger` để truy vấn ở collector thường đơn giản và đáng tin cậy hơn tạo nhiều file cục bộ. Quyết định phải dựa trên nhu cầu vận hành, không phải mặc định cứ có nhiều package thì phải có nhiều file.

### Mục tiêu học tập

Sau bài này, bạn cần:

1. Hiểu quan hệ giữa **Logger name**, Logger hierarchy và **Handler/Appender**.
2. Phân biệt **lọc log theo module** và **ghi file theo module**.
3. Biết dùng JUL `FileHandler` và Logback `RollingFileAppender` để tạo tuyến ghi riêng.
4. Hiểu `useParentHandlers` trong JUL và `additivity` trong Logback, tránh log bị nhân đôi hoặc biến mất.
5. Thiết kế file naming, rotation, retention, quyền ghi, charset và thu thập log an toàn.
6. Chạy chương trình Java 17 có output file theo module và xác minh chính xác.

## 2. Phân biệt Logger, Handler, Appender và file log

Một Logger **không phải** một file log. Logger nhận lệnh ghi, quyết định level/filter, rồi chuyển bản ghi tới một hay nhiều đích.

Trong **JUL** (`java.util.logging`):

```text
Logger.getLogger("demo.payment")
           |
           v
     Logger / LogRecord
           |
           v
     FileHandler (payment)
           |
           v
  Formatter + payment.log
```

Trong **SLF4J + Logback**:

```text
LoggerFactory.getLogger("com.example.payment.PaymentService")
           |
           v
   SLF4J API + Logback Logger
           |
           v
   RollingFileAppender "PAYMENT"
           |
           v
    Encoder + payment.log
```

| Thành phần | JUL | SLF4J + Logback |
| --- | --- | --- |
| Lời gọi logging | `java.util.logging.Logger` | `org.slf4j.Logger` |
| Tên nhóm Logger | `demo.payment`, `demo.inventory` | `com.example.payment`, `com.example.inventory` |
| Đích ghi | `Handler`, ví dụ `FileHandler` | `Appender`, ví dụ `RollingFileAppender` |
| Định dạng | `Formatter` / `LogRecord` | `Encoder` / `Layout` / logging event |
| Level thường dùng | `INFO`, `WARNING`, `SEVERE`, `FINE`... | `INFO`, `WARN`, `ERROR`, `DEBUG`... |
| Kế thừa/lan truyền đích ghi | `useParentHandlers` | `additivity` |

**Không pha trộn cấu hình:** thêm `FileHandler` vào JUL Logger không làm đổi Appender của Logback, trừ khi có bridge/routing được cấu hình riêng. Tương tự, file `logback.xml` không điều khiển một JUL Handler thuần túy chỉ vì ứng dụng cũng có SLF4J trên classpath.

### 2.1. Phân loại theo module, không theo từng request

Nên chọn định danh module **hữu hạn và ổn định**:

```text
com.example.payment
com.example.inventory
com.example.notification
```

Không nên tạo FileHandler hoặc Appender mới với đường dẫn `logs/request-<id>.log` cho từng request. Cách đó có thể tạo vô số file, giữ quá nhiều file handle, làm tăng lock, ảnh hưởng hiệu năng và khó áp dụng rotation/retention. Trường `requestId` hoặc `traceId` nên nằm trong **nội dung log hoặc MDC**, còn file vật lý được chia theo nhóm module tương đối ổn định.

Tên module dùng để tạo đường dẫn không được lấy trực tiếp từ đầu vào không tin cậy. Một giá trị người dùng như `../../secrets` có thể gây **path traversal** nếu được ghép thành file path mà không có allowlist.

## 3. Thiết kế tuyến ghi theo module

Giả sử một hệ thống có ba nhóm:

```text
                    Root logger
                     /       \
        Payment Logger     Inventory Logger
             |                  |
             v                  v
       PAYMENT_FILE       INVENTORY_FILE
       logs/payment.log   logs/inventory.log
```

Có hai chính sách chính.

**Chính sách A — Tách biệt:** Log của `payment` chỉ vào `payment.log`, log của `inventory` chỉ vào `inventory.log`. Một Appender/Handler chung vẫn có thể phục vụ các module khác. Khi module Logger đã có đích ghi riêng, phải kiểm soát sự lan truyền lên root/parent để tránh ghi thêm vào đích chung.

**Chính sách B — Vừa riêng vừa chung:** Log payment vào `payment.log` **và** `application.log`. Đây là thiết kế có chủ đích nếu cần một stream tổng hợp cho mọi sự kiện và file chuyên sâu cho subsystem. Nhưng nếu collector cùng ingest cả hai file rồi đếm như hai event độc lập, số lượng lỗi có thể **bị nhân đôi**.

Trước khi viết config, hãy quyết định:

- Mỗi module ghi **một file hay nhiều file**?
- File tổng hợp có giữ log của những module đã tách riêng không?
- Một sự kiện được phép xuất ở **bao nhiêu đích**?
- Cần level nào, cần exception/trace ID hay không?
- Ai vận hành rotation, retention và cleanup?
- Collector có nhận diện event trùng hoặc phân loại bằng field `module` không?

Khi không trả lời được những câu hỏi này, tách file theo module rất dễ trở thành mạng lưới Appender khó kiểm soát.

## 4. JUL: dùng FileHandler riêng cho từng Logger module

JDK có sẵn `java.util.logging.FileHandler`, không cần thư viện ngoài. Có thể tạo một `Logger` cho từng module, gắn `FileHandler` tương ứng rồi cấu hình cách lan truyền.

Ví dụ ý tưởng:

```java
Logger payment = Logger.getLogger("demo.payment");
Logger inventory = Logger.getLogger("demo.inventory");

payment.setUseParentHandlers(false);
inventory.setUseParentHandlers(false);

// Mỗi Logger sẽ được gắn FileHandler riêng,
// thiết lập Formatter, Level, Encoding và close đúng cách.
```

Đây là **mảnh mã minh họa**, không phải chương trình đầy đủ. `setUseParentHandlers(false)` ngăn các record của Logger này tiếp tục được chuyển tới Handler của parent. Nó **không** thay đổi kế thừa level từ parent. Để level rõ ràng, nên cấu hình Level của Logger nguồn và Level của Handler.

### 4.1. JUL Logger hierarchy

Tên Logger được tổ chức theo dấu chấm: `demo.payment`, `demo.payment.gateway` có quan hệ tên phân cấp. Một Logger con có thể kế thừa level khi `setLevel(null)` và có thể chuyển record lên Handler của Logger cha nếu cho phép.

Cần phân biệt hai cơ chế:

- **Level inheritance**: khi Logger không đặt level riêng, nó dùng effective level từ ancestor thích hợp.
- **Handler propagation**: record có thể được chuyển tới Handler của ancestor, theo `useParentHandlers`.

Nếu một Logger con bật `FINE` và parent chỉ cấu hình level `INFO`, record mà Logger con chấp nhận vẫn có thể được chuyển tới Handler của parent; **level của parent Logger không tự được áp lại để lọc record đang chuyển tiếp**. Handler của parent vẫn áp dụng level và Filter riêng của nó.

### 4.2. Những phương thức FileHandler quan trọng

| API / tùy chọn | Ý nghĩa |
| --- | --- |
| `new FileHandler(pattern, append)` | Tạo Handler ghi theo pattern tên file, cho phép nối tiếp hoặc ghi phiên mới |
| `new FileHandler(pattern, limit, count, append)` | Giới hạn dung lượng từng file và số generation khi rotation theo kích thước |
| `setFormatter(Formatter)` | Quyết định format của record |
| `setEncoding("UTF-8")` | Chọn charset cho output |
| `setLevel(Level)` | Ngưỡng level tối thiểu ở Handler |
| `setFilter(Filter)` | Bộ lọc bổ sung theo quy tắc riêng |
| `close()` | Flush/đóng Handler, giải phóng tài nguyên/lock file |

**FileHandler mặc định sử dụng XMLFormatter nếu không thay cấu hình**, vì vậy có thể tạo file XML thay vì text mà bạn mong đợi. Nếu muốn mỗi record một dòng, phải gắn `Formatter` thích hợp như `SimpleFormatter` hoặc custom Formatter.

Trong `FileHandler`, pattern hỗ trợ các thành phần như `%h`, `%t`, `%g`, `%u` theo quy tắc của JDK. Ở đây:

- `%g`: generation number cho rotation.
- `%u`: số phân biệt khi cần xử lý xung đột tên file.
- `%h`, `%t`: thư mục home hoặc temporary directory theo môi trường.

Không nhầm các ký hiệu **tên file của JUL** này với pattern `%d`, `%msg` của Logback. Trước khi dựa vào tên file/rotation, cần kiểm tra đường dẫn thực sự được tạo và chính sách của constructor hoặc `logging.properties`.

### 4.3. Level ở Logger và Handler

Nếu muốn file payment ghi `INFO` và các mức nặng hơn:

```java
payment.setLevel(Level.INFO);
paymentFile.setLevel(Level.INFO);
```

Nếu chỉ gọi `payment.setLevel(Level.FINE)` nhưng FileHandler vẫn ở `INFO`, record FINE có thể được Logger tạo nhưng Handler không xuất. Nếu ngược lại Handler ở `FINE` và Logger ở `INFO`, record FINE bị loại trước Handler.

Không nên cấu hình Logger một cách tùy tiện chỉ để “đủ số file”. Hãy xác định module nào cần DEBUG/FINE, ai chịu trách nhiệm bật/tắt và lượng log có thể tạo ra.

## 5. Ví dụ Java 17 chạy độc lập: mỗi module một file

Ví dụ dưới đây sử dụng **chỉ JDK 17**, không cần SLF4J, Logback, Gradle hay Maven. Chương trình:

1. Tạo thư mục `logs`.
2. Tạo hai Logger chức năng là `demo.payment` và `demo.inventory`.
3. Gắn `FileHandler` riêng: `logs/payment.log` và `logs/inventory.log`.
4. Dùng một `Formatter` tùy chỉnh để mỗi record chỉ có level và message, không chứa timestamp biến động.
5. Ghi ba sự kiện: payment INFO, inventory WARNING, payment SEVERE.
6. Tháo Handler và `close()` trong `finally` trước khi đọc file.
7. Đọc file bằng `Files.readAllLines` rồi in ra console để xác nhận sự kiện đã đi vào đúng file.

### 5.1. Tạo file ModuleFileLoggingDemo.java

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ModuleFileLoggingDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        Files.createDirectories(directory);

        Logger payment = Logger.getLogger("demo.payment");
        Logger inventory = Logger.getLogger("demo.inventory");

        payment.setUseParentHandlers(false);
        inventory.setUseParentHandlers(false);
        payment.setLevel(Level.ALL);
        inventory.setLevel(Level.ALL);

        Formatter lineFormatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        FileHandler paymentFile =
                new FileHandler("logs/payment.log", false);
        FileHandler inventoryFile =
                new FileHandler("logs/inventory.log", false);

        paymentFile.setEncoding(StandardCharsets.UTF_8.name());
        inventoryFile.setEncoding(StandardCharsets.UTF_8.name());
        paymentFile.setLevel(Level.INFO);
        inventoryFile.setLevel(Level.INFO);
        paymentFile.setFormatter(lineFormatter);
        inventoryFile.setFormatter(lineFormatter);

        payment.addHandler(paymentFile);
        inventory.addHandler(inventoryFile);

        try {
            payment.log(
                    Level.INFO,
                    "event=payment.started requestId={0}",
                    "req-17");

            inventory.warning("event=stock.low sku=sku-2");

            payment.severe(
                    "event=payment.failed code=UPSTREAM_TIMEOUT");
        } finally {
            payment.removeHandler(paymentFile);
            inventory.removeHandler(inventoryFile);
            paymentFile.close();
            inventoryFile.close();
        }

        printFile("payment.log", Path.of("logs/payment.log"));
        printFile("inventory.log", Path.of("logs/inventory.log"));
    }

    private static void printFile(
            String label,
            Path file) throws IOException {
        System.out.println(label + ":");
        List<String> lines = Files.readAllLines(
                file, StandardCharsets.UTF_8);
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
```

### 5.2. Biên dịch và chạy

Trong thư mục chứa `ModuleFileLoggingDemo.java`, với **JDK 17 trở lên**:

```bash
javac ModuleFileLoggingDemo.java
java ModuleFileLoggingDemo
```

**stdout chính xác của chương trình trên khi các file được tạo thành công:**

```text
payment.log:
INFO event=payment.started requestId=req-17
SEVERE event=payment.failed code=UPSTREAM_TIMEOUT
inventory.log:
WARNING event=stock.low sku=sku-2
```

Nội dung file **`logs/payment.log`**:

```text
INFO event=payment.started requestId=req-17
SEVERE event=payment.failed code=UPSTREAM_TIMEOUT
```

Nội dung file **`logs/inventory.log`**:

```text
WARNING event=stock.low sku=sku-2
```

Ví dụ dùng `append=false`, nên mỗi lần chạy thành công sẽ tạo phiên ghi mới thay vì giữ record từ lần chạy trước. Trước khi đọc nội dung file, chương trình đóng hai FileHandler để flush và giải phóng tài nguyên. FileHandler có thể tạo các file lock phụ trợ trong lúc chạy; chúng không phải file nội dung của bài.

### 5.3. Phân tích những chỗ quan trọng

- **Tên Logger:** `demo.payment` và `demo.inventory` phân loại event theo module. Tên này cố định, không chứa request ID.
- **Handler riêng:** `payment.addHandler(paymentFile)` đảm bảo các record payment đi qua Handler dành cho payment; inventory có Handler riêng.
- **`setUseParentHandlers(false)`:** tránh ConsoleHandler mặc định của parent/root in thêm bản ghi (và tránh parent file nếu có). Nếu chương trình vẫn muốn một file tổng hợp, phải thiết kế đường ghi chung có chủ đích.
- **`setLevel(Level.ALL)`:** cho Logger chấp nhận các event thông thường; Handler `INFO` mới quyết định chỉ nhận INFO trở lên. Đây là lựa chọn để làm rõ hai tầng lọc, không phải khuyến nghị bật mọi level trên mọi Logger production.
- **`formatMessage(record)`:** JUL xử lý placeholder kiểu `{0}`; vì vậy `requestId={0}` biến thành `requestId=req-17`.
- **`close()`:** bảo đảm các stream được flush/đóng khi chương trình kết thúc bình thường, thay vì đọc file đang đệm chưa xả. Trong ví dụ `FileHandler` không được dùng trong try-with-resources; ta tháo và đóng tường minh ở `finally`.
- **Thứ tự:** mã chạy tuần tự, Formatter không in clock/thread, nên output xác định. Nếu nhiều thread cùng phát log, thứ tự event giữa các module không được bảo đảm đồng bộ theo một chuỗi chung.

### 5.4. Điều chỉnh và thử nghiệm

**Thử 1 — bật DEBUG/FINE:** thêm một dòng `payment.fine("event=payment.debug")`. Với paymentFile vẫn ở INFO, dòng này **không** xuất trong file, dù Logger đặt ALL. Đổi Handler thành `FINE` để thấy nó.

**Thử 2 — bật parent Handler:** đặt `payment.setUseParentHandlers(true)`. Với root có ConsoleHandler theo cấu hình môi trường, một log payment có thể vừa vào file vừa in console. Không khẳng định luôn có đúng hai bản ghi vì phụ thuộc các Handler đang gắn trên ancestor.

**Thử 3 — thêm module:** tạo `Logger` và `FileHandler` thứ ba cho `demo.notification`, nhớ định cấu hình Formatter/Level và đóng Handler. Không nên sao chép tùy tiện đoạn khởi tạo này trong từng request; thực tế tạo Handler khi ứng dụng khởi động.

**Thử 4 — chuyển file sang append:** thay constructor thành `new FileHandler("logs/payment.log", true)`. Nếu file đã tồn tại, các bản ghi mới có thể được nối tiếp. Phải quyết định chính sách rotation/cleanup, nếu không file có thể tăng mãi.

## 6. Cấu hình JUL bằng logging.properties

Khi không muốn khởi tạo Handler trong mã nghiệp vụ, có thể dùng cấu hình JUL. Ví dụ ý tưởng cho module payment và inventory:

```properties
.level = INFO
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = logs/application.%u.%g.log
java.util.logging.FileHandler.limit = 1000000
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
```

Đây là **mảnh cấu hình minh họa các thuộc tính FileHandler**, không phải cấu hình đầy đủ để tự động tạo **hai FileHandler độc lập theo module**. Cần chú ý: JUL `LogManager` quản lý Handler theo cơ chế tên lớp và cách khai báo Handler; không mặc định chỉ cần ghi hai property tùy ý như `demo.payment.file=payment.log` là đã có hai FileHandler riêng.

Nếu muốn cấu hình nhiều đích theo module chỉ qua file properties, phải dựa trên hỗ trợ thực tế của JUL, thiết lập Handler phù hợp, hoặc viết custom Handler/subclass có thể được cấu hình. Một số framework và hệ thống cấu hình mở rộng JUL hỗ trợ cách khai báo khác; **không giả định thuộc tính mở rộng là chuẩn JDK**.

Trong chương trình nhỏ, giải pháp code như mục 5 có thể rõ ràng hơn. Với ứng dụng production có Logback, mô hình Appender định danh trong `logback.xml` thường trực quan hơn khi cần nhiều file riêng.

**Đường dẫn tương đối:** `logs/application.%u.%g.log` phụ thuộc working directory của process. Khi chạy như service, container hoặc từ IDE, working directory có thể khác bạn dự tính. Nếu cần, dùng đường dẫn tuyệt đối từ cấu hình deploy hoặc một thư mục được kiểm soát và ghi rõ chính sách quyền truy cập.

## 7. Logback: RollingFileAppender theo package/module

Với ứng dụng dùng **SLF4J + Logback**, bạn có thể cấu hình một `RollingFileAppender` riêng cho mỗi module. Điểm mạnh là mỗi Appender có **file path, encoder, filter, rolling policy và retention** riêng, được tham chiếu bằng `<appender-ref>` từ logger của module.

Giả sử package code:

```text
com.example.payment.*
com.example.inventory.*
com.example.notification.*
```

Một cấu hình Logback có thể thiết lập:

- `PAYMENT_FILE` cho `com.example.payment`.
- `INVENTORY_FILE` cho `com.example.inventory`.
- `APPLICATION_FILE` tại root cho những package khác.

### 7.1. File logback.xml hoàn chỉnh

Ví dụ dưới đây minh họa **hai module có file riêng** và một file chung cho các logger khác. Đặt `logback.xml` trên runtime classpath, ví dụ `src/main/resources/logback.xml`, khi dùng Logback Classic. Các thư mục `logs` phải có quyền ghi; triển khai thực tế cần xác minh đường dẫn và filesystem.

```xml
<configuration>
    <!-- File của module payment -->
    <appender name="PAYMENT_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/payment.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/payment.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- File của module inventory -->
    <appender name="INVENTORY_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/inventory.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/inventory.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>200MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- File chung cho các logger khác -->
    <appender name="APPLICATION_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment"
            level="INFO" additivity="false">
        <appender-ref ref="PAYMENT_FILE"/>
    </logger>

    <logger name="com.example.inventory"
            level="INFO" additivity="false">
        <appender-ref ref="INVENTORY_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION_FILE"/>
    </root>
</configuration>
```

**Ý nghĩa của XML:**

1. `RollingFileAppender` giữ đường dẫn file hiện tại, còn `TimeBasedRollingPolicy` tạo archive theo ngày và nén `.gz` khi rollover.
2. `maxHistory` và `totalSizeCap` giúp giới hạn lịch sử và tổng kích thước archive theo chính sách, nhưng cleanup phụ thuộc lifecycle và cấu hình thực tế; không bảo đảm tuyệt đối dữ liệu không mất.
3. Logger `com.example.payment` gom các Logger con có cùng tiền tố package theo hierarchy.
4. `additivity="false"` ngăn bản ghi của payment tiếp tục tới Appender ở root, nên không bị chép thêm vào `application.log`.
5. Inventory tương tự, với file và retention riêng.
6. Các logger không thuộc hai nhánh trên vẫn được root xử lý và ghi vào `application.log` nếu level/filter cho phép.
7. Mỗi module vẫn cần chính sách bảo mật: **tách file không thay thế việc kiểm soát nội dung message/MDC**.
8. Pattern `%d`, `%logger`, `%msg`, `%X` là cú pháp **Logback**, không áp dụng cho `java.util.logging.FileHandler`.

### 7.2. Khi nào dùng additivity=false?

Trong Logback, Logger có quan hệ tên phân cấp và **additivity** thường bật mặc định. Khi một Logger có Appender riêng, event có thể được gửi tiếp tới Appender của ancestor/root.

```text
com.example.payment.PaymentService
          |
          +--> PAYMENT_FILE
          |
          +--> root -> APPLICATION_FILE   (nếu additivity=true)
```

Nếu muốn payment **chỉ nằm trong payment.log**, `additivity="false"` tại logger module là lựa chọn hợp lý. Nhưng nếu bật `false` mà **không gắn Appender cho nhánh đó**, log có thể không còn đích ghi. Vì vậy phải thiết kế tuyến đầy đủ rồi mới tắt additivity.

`additivity="false"` **không có nghĩa Logger không kế thừa level**. Nó điều khiển việc chuyển event tới Appender của ancestor. Một Logger con có level riêng có thể cho phát DEBUG và gửi tới Appender root theo additivity; level root không nhất thiết được dùng để lọc lại event đã được Logger con chấp nhận. Appender filter vẫn có thể loại event.

### 7.3. Khi muốn vừa file module vừa file tổng

Nếu chính sách yêu cầu payment trong cả `payment.log` và `application.log`, giữ **additivity mặc định** hoặc cấu hình appender chung theo cách chủ động. Đừng coi việc một event có ở hai file là lỗi nếu đó là thiết kế, nhưng cần:

- Ghi rõ **đích nào là nguồn sự thật** khi lập dashboard/alert.
- Tránh ingest trùng hai bản ghi như hai lỗi riêng biệt.
- Kiểm tra retention khác nhau giữa file riêng và file chung.
- Tránh gắn **chính một Appender** ở cả logger con và root rồi để additivity gây xuất hai lần vào cùng đích.

Bảng tình huống:

| Cấu hình | Payment event tới đâu? | Diễn giải |
| --- | --- | --- |
| `PAYMENT_FILE` tại payment, additivity false | Chỉ `payment.log` | Tách biệt module |
| `PAYMENT_FILE` tại payment, additivity true, root có `APPLICATION_FILE` | `payment.log` và `application.log` | Vừa riêng vừa chung |
| Payment không có appender, additivity false | Không có đích từ ancestor | Dễ mất log |
| Cùng `PAYMENT_FILE` gắn ở payment và root, additivity true | Có thể gọi cùng Appender hai lần | Nguy cơ log trùng trong một file |

Cần thử bằng event có `requestId` dễ nhận diện, đồng thời kiểm tra cả file riêng lẫn file chung trước khi đưa vào production.

## 8. Chỉ tách file không đủ: thiết kế level, format và context

Một hệ thống tách theo module không nên mất thông tin giúp truy vết liên module. Ví dụ request đi qua payment và inventory:

```text
payment.log:
INFO event=payment.started requestId=req-17 orderId=ord-8

inventory.log:
INFO event=stock.reserved requestId=req-17 orderId=ord-8

payment.log:
ERROR event=payment.failed requestId=req-17 code=UPSTREAM_TIMEOUT
```

**Điểm chung là `requestId=req-17`**, không phải file path. Khi sự cố kéo dài qua nhiều module, hệ thống thu thập cần có thể tìm cùng correlation ID trên các file/stream.

Với SLF4J/Logback, MDC có thể giúp đưa context vào pattern:

```java
String old = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    processPayment();
} finally {
    if (old == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", old);
    }
}
```

Đây là **mảnh mã**, giả sử đã import `org.slf4j.MDC` và có `requestId`/ `processPayment()`. Trong Logback pattern `%X{requestId}` sẽ lấy giá trị MDC tương ứng.

**Thận trọng với async:** MDC/ThreadLocal không tự đi qua mọi `ExecutorService`, `CompletableFuture`, queue hoặc reactive pipeline. Khi chuyển thread, dùng cơ chế context propagation được hỗ trợ và bảo đảm xóa/khôi phục context để tránh gán log của request này sang request khác.

Phân biệt thêm:

- **Module name**: phân loại nguồn ổn định, phù hợp tên Logger/file.
- **`requestId`**: nối các event của một request, có thể xuất hiện ở nhiều module.
- **`traceId`, `spanId`**: phục vụ distributed tracing nếu stack có tracing.
- **`event`, `errorCode`, `outcome`**: phân loại loại sự kiện và kết quả.
- **`level`**: mức severity, có thể khác nhau giữa JUL và Logback.

Không tạo file theo `requestId` để thay việc thiết kế correlation ID và truy vấn log tập trung.

## 9. File naming và cấu trúc thư mục

Một quy ước đơn giản:

```text
/var/log/my-app/
  payment.log
  payment.2026-01-12.log.gz
  inventory.log
  inventory.2026-01-12.log.gz
  application.log
```

Các đường dẫn là **minh họa**; nhiều container không dùng `/var/log` cho ứng dụng, và đường dẫn tương đối `logs/payment.log` sẽ theo working directory.

Khi đặt tên, nên:

1. Chọn tên module theo **allowlist cố định**, không nối trực tiếp dữ liệu người dùng.
2. Đảm bảo mỗi Appender quản lý **một đường dẫn chủ đích**; tránh nhiều writer độc lập ghi cùng file.
3. Nếu chạy nhiều instance trên chung máy, bổ sung quy tắc **instance/process namespace** phù hợp, thay vì cho nhiều JVM mở cùng một file.
4. Chọn nơi lưu có quyền ghi và dung lượng đủ.
5. Định nghĩa rõ **charset UTF-8** và timezone trong format.
6. Kiểm soát quyền đọc, vì file của module xác thực có thể nhạy cảm hơn file hoạt động chung.
7. Phân biệt **file đang mở** với **archive sau rotation** để collector đọc đúng.

Với collector tail file, chuyển tên/rename/nén khi rotate có thể làm **lặp hoặc mất event** nếu agent không xử lý đúng vị trí đọc. Cần kiểm tra collector thực tế, không chỉ thử một `logger.info()` rồi kết luận pipeline đúng.

## 10. Rotation, retention và giới hạn dung lượng

Nếu tạo file riêng cho năm module mà không có rotation/retention, tổng log có thể tăng nhanh hơn cả file chung vì một số event được sao chép ở nhiều đích.

### 10.1. Hai nhóm chính sách

- **Size-based**: rollover khi file đạt một kích thước quy định.
- **Time-based**: rollover theo lịch, ví dụ mỗi ngày.
- **Size-and-time based**: phối hợp cả hai cho file có lưu lượng lớn.

Trong JUL, `FileHandler(pattern, limit, count, append)` hỗ trợ nhóm file xoay vòng theo dung lượng. `limit` là ngưỡng kích thước, `count` là số generation. Cần kiểm tra tên file thực tế nếu dùng `%g` hoặc không có `%g`.

Trong Logback, `TimeBasedRollingPolicy` có thể đặt `fileNamePattern`, `maxHistory`, `totalSizeCap`; `SizeAndTimeBasedRollingPolicy` là lựa chọn khi thực sự muốn cả ngày và giới hạn kích thước từng file archive.

### 10.2. Retention không chỉ là số ngày

Ví dụ giữ payment 14 ngày, inventory 7 ngày. Cần trả lời:

- File payment có dữ liệu nào phải được xóa sớm vì nhạy cảm không?
- Có bắt buộc giữ event kiểm toán lâu hơn log chẩn đoán thông thường không?
- Archive có được nén, mã hóa khi lưu và phân quyền đọc không?
- Có hệ thống backup/collector cũng đang giữ bản sao với retention riêng không?
- Khi xóa archive ở filesystem, bản sao ở collector có còn theo chính sách nào?

**Retention của Appender không tự xóa bản sao đã gửi ra nơi khác.** Phải quản lý đồng bộ các tầng lưu trữ theo chính sách tổ chức.

### 10.3. Khi file tăng nhanh bất thường

Đừng mặc định nâng giới hạn file. Hãy xem:

1. Logger module có đang bật DEBUG/TRACE vô tình không?
2. Có retry loop in stack trace ở mỗi lần lặp không?
3. Một event có bị nhân bản bởi additivity hoặc bridge không?
4. Một DTO hoặc request body lớn có bị log toàn bộ không?
5. Có cấu hình sampling/rate limiting phù hợp cho sự kiện quá dày không?
6. Collector có ingest cả file riêng và file chung dẫn đến tốn chi phí gấp đôi không?

Tránh dùng log là nơi duy nhất ghi sự kiện giao dịch quan trọng. Nếu dữ liệu có yêu cầu audit bền vững, hãy dùng cơ chế audit/storage có hợp đồng phù hợp thay vì trông chờ rotation của logger.

## 11. Đồng thời, nhiều JVM và lỗi file I/O

### 11.1. Nhiều thread trong một process

Các Logger và Handler/Appender được xây dựng cho nhu cầu logging nhiều thread, nhưng event từ các thread có thể xen kẽ; **không nên suy ra thứ tự toàn cục từ hai file module khác nhau**. Một `payment.log` và `inventory.log` có timestamp gần nhau chưa đủ kết luận event nào gây ra event nào, đặc biệt trên nhiều host. Dùng correlation ID/trace.

Nếu custom Formatter sử dụng trạng thái mutable dùng chung, cần xem tính thread-safety của nó. Nên ưu tiên Formatter bất biến, không dùng một `SimpleDateFormat` mutable chia sẻ không bảo vệ.

### 11.2. Nhiều process ghi cùng đường dẫn

Hai JVM chạy chung ứng dụng mà cùng ghi `logs/payment.log` có thể dẫn đến tranh chấp lock, ghi lẫn nội dung, xung đột rotation và dữ liệu không ổn định. JUL `FileHandler` có cơ chế khóa và `%u` để phân biệt một số xung đột tên file, nhưng **không nên xem đó là giải pháp bảo đảm atomic/durable multi-process logging**. Với Logback RollingFileAppender, cũng không mặc định nhiều process ghi cùng một file và cùng rotate là an toàn.

Phương án thường tốt hơn:

- Mỗi instance ghi stdout/stderr và để platform/collector gom log.
- Hoặc mỗi instance có đường dẫn riêng được đặt từ cấu hình deploy tin cậy.
- Nếu bắt buộc ghi chung, chọn kiến trúc thu thập tập trung có cơ chế đồng bộ và bảo đảm rõ ràng, không tự ghép các file handle.

### 11.3. Lỗi I/O và vòng đời Handler/Appender

Những lỗi thường gặp:

- Thư mục không tồn tại hoặc process không có quyền ghi.
- Hết dung lượng, hết inode hoặc filesystem bị chuyển read-only.
- File handle quá nhiều do tạo Appender mỗi request.
- Quá trình rotation bị lỗi hoặc collector không theo được file mới.
- Hệ thống dừng đột ngột khi buffer/async queue chưa flush.
- Appender được khai báo nhưng không được Logger tham chiếu.

Hãy khởi tạo Handler/Appender theo vòng đời ứng dụng, có đường dẫn lỗi rõ ràng và **đóng/stop có kiểm soát** khi shutdown bình thường. `logger.info(...)` trả về **không đồng nghĩa event đã nằm bền vững trên đĩa**.

Không để cơ chế logging làm crash đường nghiệp vụ chỉ vì một file log không ghi được mà không có phương án xử lý lỗi; đồng thời phải có cảnh báo vận hành khi logging bị hỏng, vì “nuốt lỗi” file log cũng nguy hiểm.

## 12. Dùng file riêng trong container hay tập trung trên stdout?

Trong Kubernetes hoặc môi trường container hiện đại, một quy tắc thường hiệu quả là **ứng dụng xuất stdout/stderr**; platform/agent đọc từ stream và gắn metadata như pod, namespace, instance, container, rồi chuyển sang hệ thống log tập trung.

| Thiết kế | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Mỗi module một file cục bộ | Dễ tail theo module trên máy chủ cố định | Quản lý path, quyền, rotation, collector, ephemeral storage |
| Một file application.log có field module | Ít file, dễ quản lý | Muốn xem từng module cần filter trong công cụ |
| Một JSON stream qua stdout | Hợp container và centralized observability | Phụ thuộc collector/parser/schema |
| File riêng + file chung | Chuyên sâu và tổng hợp | Dễ double-ingest, chi phí tăng, retention phức tạp |

Nếu hạ tầng đã có Elasticsearch/OpenSearch/Loki hoặc nền tảng tương tự, bạn thường có thể truy vấn theo `logger`, `module`, `service`, `requestId` mà **không cần tách file vật lý**. File theo module vẫn có giá trị khi cần đáp ứng ràng buộc lưu trữ, phân quyền hay pipeline đặc biệt và đã chấp nhận chi phí vận hành.

**Quy tắc chọn:** thiết kế logic **phân loại bằng field** trước, quyết định có cần **tách file vật lý** sau. Điều này giúp kiến trúc ít lệ thuộc backend và dễ đổi môi trường triển khai.

## 13. Bảo mật: tránh file log trở thành kho dữ liệu nhạy cảm

Tách file chỉ tách **đường lưu**; nó không tự loại dữ liệu khỏi message. Đặc biệt các module authentication, payment và account có thể vô tình đưa thông tin nhạy cảm vào log.

- Không ghi password, bearer token, cookie, khóa riêng, CVV hoặc payload thanh toán nhạy cảm.
- Dùng allowlist field: `requestId`, `operation`, `errorCode`, `outcome`, `durationMs`, một số ID nội bộ được phép.
- Tránh log `toString()` của object có trường không kiểm soát.
- Dữ liệu người dùng có thể chứa newline, carriage return và ký tự điều khiển để tạo **log injection**. Dùng encoder an toàn/structured JSON hoặc escape khi xuất text.
- Không dùng input của client để quyết định tên file/path.
- Phân quyền thư mục log và archive theo nguyên tắc quyền tối thiểu.
- Rà retention, mã hóa lưu trữ/backup và quyền đọc trong hệ thống log tập trung.

Ví dụ một đầu vào xấu:

```text
comment=normal
ERROR event=admin.login outcome=success
```

Nếu ghép thẳng `comment` có newline vào text log, dòng `ERROR` có thể là **giả mạo do người dùng nhập**, không phải record thật. File payment riêng không giải quyết vấn đề này; cần encode/escape dữ liệu ở nguồn hoặc format cuối.

### 13.1. Stack trace và dữ liệu lỗi

Một exception có thể chứa URL, username hoặc payload trong message. Chỉ log Throwable ở những ranh giới cần điều tra, không in cùng lỗi ở nhiều tầng. Nếu dùng JSON encoder, biểu diễn exception thành field được escaping đúng; nếu dùng stack trace text nhiều dòng, collector phải hiểu cách ghép multiline.

## 14. Quan sát vấn đề từ hai góc: log nghiệp vụ và log vận hành

**Đọc theo module** hữu ích khi một nhóm chỉ cần các sự kiện của subsystem mình. Nhưng **điều tra end-to-end** lại cần nối log giữa module và service. Vì vậy:

- Mỗi module có tên Logger ổn định và event code nhất quán.
- Một request dùng correlation ID xuyên các bước.
- Timestamp cần timezone thống nhất (thường UTC).
- Mức severity có quy tắc nhất quán dù Logback dùng WARN/ERROR còn JUL dùng WARNING/SEVERE.
- Metrics cho tỷ lệ lỗi, latency, throughput; trace cho hành trình phân tán; log cho chi tiết từng event.
- Khi collector ingest nhiều file, kèm metadata `source_file`, `service`, `module` để biết event đến từ đâu và tránh double-count.

File theo module là **một quyết định phân tuyến lưu trữ**, không phải cách thay thế tracing. Đừng tách file đến mức mỗi bước của một request nằm rải rác mà không có khóa truy vết.

## 15. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Payment log có trong cả payment.log và application.log | Parent handler/additivity đang bật | Xác định muốn tách biệt hay vừa riêng vừa chung; cấu hình nhất quán |
| payment.log trống dù có `logger.info` | Level/filter chặn, Appender chưa gắn/start, path lỗi | Kiểm tra Logger, Handler/Appender, file system và status |
| Log con không đến file module | Logger name không khớp nhánh hoặc additivity bị chặn ở vị trí khác | Kiểm tra tên Logger, hierarchy, appender-ref |
| Tắt additivity rồi không còn log nào | Module Logger không có Appender của riêng nó | Gắn đích đúng hoặc khôi phục propagation |
| `FileHandler` tạo XML thay vì text | Đang dùng XMLFormatter mặc định | Chọn `SimpleFormatter` hoặc custom Formatter |
| File nằm sai thư mục | Path tương đối theo working directory khác | In/kiểm tra working directory và cấu hình path |
| File tăng không giới hạn | Không có rolling/retention, DEBUG quá nhiều | Đặt chính sách, kiểm tra volume |
| Nhiều file bị ghi lẫn giữa các JVM | Nhiều process dùng cùng path | Tách namespace theo instance hoặc dùng collector |
| File không có tiếng Việt đúng | Charset và encoding ở collector không thống nhất | Dùng UTF-8 từ writer đến parser |
| File bị mất event sau shutdown | Async buffer/queue chưa flush hoặc process chết đột ngột | Kiểm tra shutdown lifecycle và độ bền của pipeline |
| Collector đếm lỗi gấp đôi | Ingest cả file riêng và file chung | Định nghĩa nguồn dữ liệu chính và de-duplication |
| Chỉ thấy lỗi ở console, không ở file | File Handler thiếu, level/filter/path khác | Kiểm tra Logger propagation và cấu hình Handler |
| Không tìm được request xuyên module | Thiếu `requestId`/`traceId` | Chuẩn hóa context và truyền qua async |
| Log chứa secret dù đã chia module | Code ghi nhầm field/Throwable nhạy cảm | Giảm dữ liệu tại nguồn, kiểm tra format và phân quyền |
| JUL config không áp dụng cho Logback | Hai backend khác API/config | Xác định provider runtime, dùng đúng config |

### Cách điều tra có hệ thống

1. **Ghi một event thử** ở mỗi module với event code và ID dễ nhận.
2. Xác định **Logger name** chính xác và effective level.
3. Kiểm tra Handler/Appender nào thực sự gắn với Logger đó.
4. Kiểm tra `useParentHandlers` hoặc `additivity` — bản ghi có đi tiếp tới root không?
5. Kiểm tra level/filter của từng Handler/Appender và đường dẫn file thực tế.
6. Xác minh Formatter/Encoder, charset, quyền ghi và lifecycle.
7. Đọc file riêng + file tổng hợp (nếu có), đếm số bản ghi dự kiến và số bản ghi thực.
8. Thử rotation/retention, nhiều request, shutdown, disk đầy trong môi trường test phù hợp.
9. Xác minh collector ingest đúng file/stream, không tạo alert/metric trùng.

Không chỉnh nhiều thứ cùng lúc: việc thay Logger name, Appender, additivity và rolling policy đồng thời làm khó xác định nguyên nhân.

## 16. Checklist trước khi triển khai

- [ ] Đã quyết định **có thật sự cần nhiều file vật lý** hay một JSON stream có field module là đủ.
- [ ] Đã thống nhất danh sách module hữu hạn, tên Logger và đường dẫn file cố định.
- [ ] Mỗi module có đúng Handler/Appender và Formatter/Encoder theo thiết kế.
- [ ] Đã xác định event có đi tới file chung hay không; kiểm soát `useParentHandlers`/`additivity`.
- [ ] Có chính sách level và Filter, không làm mất sự kiện quan trọng.
- [ ] File name, working directory, charset, timezone và quyền ghi được kiểm tra ở runtime thực.
- [ ] Có rolling, retention, dung lượng archive và giám sát filesystem.
- [ ] Không để hai JVM/instance ghi một file path không được thiết kế cho concurrency.
- [ ] Có correlation ID/trace ID để truy vết xuyên các module.
- [ ] Xử lý context khi qua executor, async pipeline và dọn MDC/ThreadLocal.
- [ ] Không đưa secret và payload nhạy cảm vào log; có escape và kiểm soát truy cập.
- [ ] Collector đọc đúng đường dẫn, không bỏ sót archive hoặc double-ingest.
- [ ] Có kiểm thử file output, missing/duplicate log, shutdown, rotation và lỗi disk.
- [ ] Có kế hoạch thay đổi cấu hình/rollback khi tách module làm mất tín hiệu giám sát.

### Nguồn tham khảo kỹ thuật

- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): pattern tên file, limit/count, append và lock.
- [Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): hierarchy, level và `useParentHandlers`.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): logger hierarchy, Appender và additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): RollingFileAppender, rolling policy và encoder.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade và parameterized logging.

**Kết luận:** **File log theo module** giúp tách luồng thông tin theo chức năng khi có nhu cầu vận hành rõ ràng. Trong JUL, dùng Logger + FileHandler + `useParentHandlers`; trong Logback, dùng Logger theo package + RollingFileAppender + `additivity`. Điều quan trọng không chỉ là tạo được nhiều file, mà còn giữ **đúng số bản ghi, đúng level, đúng đường dẫn, đủ context, có rotation/retention và không lộ dữ liệu**. Nếu hệ thống đã có centralized logging, hãy cân nhắc phân loại bằng field module trong JSON trước khi mở rộng số file vật lý.
