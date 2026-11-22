# Định dạng logger trong Java Logging: Logger name, PatternLayout và Formatter

## 1. Định dạng logger là gì?

Khi một ứng dụng Java gọi `logger.info(...)` hoặc `logger.error(...)`, hệ thống logging cần quyết định **bản ghi sẽ được trình bày như thế nào**. Một dòng log tốt không chỉ chứa thông điệp mà còn cho biết **nguồn phát (tên logger), mức độ, thời điểm, thread, ngữ cảnh và kết quả**.

Cùng một sự kiện có thể được hiển thị theo nhiều định dạng:

```text
INFO Order accepted
```

```text
2026-01-12 09:30:12.347 INFO [http-1] com.example.checkout.OrderService - event=order.accepted orderId=ord-17
```

```json
{
  "timestamp": "2026-01-12T09:30:12.347Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "http-1",
  "event": "order.accepted",
  "orderId": "ord-17"
}
```

Đây là **các ví dụ minh họa**; timestamp và ID là dữ liệu giả định, không phải output mặc định của mọi backend.

Trong bài này, **“định dạng logger”** bao gồm việc chọn cách biểu diễn **tên Logger** và các thuộc tính của logging event. Cần phân biệt ba câu hỏi:

1. **Ai phát log?** Tên Logger thường dựa trên package/class hoặc một tên chức năng ổn định.
2. **Event được tạo như thế nào?** Code cung cấp level, message, tham số và throwable/ngữ cảnh.
3. **Event xuất ra sao?** `Formatter`, `Layout` và `Encoder` của backend quyết định chuỗi cuối cùng.

Không nhầm việc định dạng với điều kiện lọc: thay `%logger` hoặc `%msg` không làm Logger tự bật DEBUG. Level/filter và đường đi Handler/Appender vẫn quyết định một event có tới được nơi xuất không.

Mục tiêu học tập là dùng được **Logback PatternLayout**, hiểu `LoggerFactory.getLogger`, sự khác nhau giữa **message placeholder** và **layout pattern**, tên logger đầy đủ/rút gọn, UTC/timezone, MDC, throwable, structured logging và cách đối chiếu với **JUL SimpleFormatter**.

## 2. Luồng dữ liệu: từ Logger đến dòng log

Trong ứng dụng dùng SLF4J và Logback:

```text
Source code
    LoggerFactory.getLogger(PaymentService.class)
    logger.warn("event=retry attempt={}", 2)
                     |
                     v
               SLF4J API
                     |
                     v
              Logback Logger
              kiểm tra level
                     |
                     v
               LoggingEvent
       tên logger / level / thread / message
       timestamp / marker / MDC / throwable
                     |
                     v
          Appender + Filter
                     |
                     v
          Encoder + Layout
      PatternLayout hoặc JSON encoder
                     |
                     v
        stdout / stderr / file / collector
```

**Logger** cung cấp tên và tiếp nhận sự kiện. **Logging event** chứa dữ liệu của sự kiện. **Layout** biến các thuộc tính event thành text; **Encoder** chuyển text/sự kiện thành dữ liệu gửi tới đích ghi. Trong Logback, cấu hình `PatternLayoutEncoder` (thông thường qua khối `<encoder><pattern>...</pattern></encoder>`) là cách phổ biến tạo text log.

Một Appender có thể sử dụng định dạng khác Appender còn lại. Ví dụ console cần dòng ngắn gọn, còn file/collector cần nhiều field hơn. Nếu một event đi tới cả hai, **tên Logger và level trong event không đổi**, nhưng cách biểu diễn của chúng có thể khác.

Với **`java.util.logging` (JUL)**, các thành phần tương ứng là `Logger` → `LogRecord` → `Handler` → `Formatter`. Không đem cú pháp `%logger` của Logback đặt nguyên vào file `logging.properties` của JUL: mỗi hệ thống định dạng có API và cú pháp riêng.

## 3. Đặt tên Logger ổn định và có nghĩa

Một cách khai báo phổ biến là đặt Logger theo lớp:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
```

Đây là **mảnh mã đặt trong lớp `PaymentService`**. `getLogger(PaymentService.class)` thường dùng tên đầy đủ của lớp, chẳng hạn:

```text
com.example.payment.PaymentService
```

Bạn cũng có thể đặt tên rõ ràng theo subsystem:

```java
private static final org.slf4j.Logger AUDIT =
        org.slf4j.LoggerFactory.getLogger("com.example.audit");
```

Hai cách đều hợp lệ nếu có quy ước. Tuy nhiên, tên Logger nên **ổn định, không đổi với từng request**. Tránh:

```java
// KHÔNG NÊN tạo tên Logger riêng cho mỗi request.
LoggerFactory.getLogger("payment.request." + requestId);
```

Đây là đoạn minh họa anti-pattern, giả sử `requestId` có sẵn. Cách đó làm số lượng Logger tăng theo dữ liệu động, khó cấu hình cây Logger và tăng độ phức tạp vận hành. ID request nên là field trong log hoặc MDC, không nằm trong tên Logger.

### 3.1. Tên Logger khác vị trí gọi code

- **Logger name**: giá trị do `LoggerFactory.getLogger(...)` lựa chọn, ví dụ `com.example.payment.PaymentService`.
- **Source class/method/line**: vị trí mã gọi logger thực tế, nếu backend có cơ chế tìm caller.
- **Thread name**: thread phát event, không phải tên lớp.
- **Message**: nội dung event sau khi tham số được định dạng.

Đặc biệt, một lớp `LoggingHelper` có thể sử dụng Logger được đặt tên theo subsystem, nên **logger name không nhất thiết là class của dòng code vừa gọi log**. Nếu muốn caller data chính xác, phải kiểm tra API/backend/wrapper và cân nhắc chi phí truy stack; không suy ra chỉ từ tên Logger.

### 3.2. Tên Logger đầy đủ và tên rút gọn

Logback PatternLayout hỗ trợ:

```text
%logger       -> Tên Logger đầy đủ
%logger{0}    -> Phần tên bên phải dấu chấm cuối cùng
%logger{36}   -> Cố gắng rút gọn Logger name theo giới hạn ký tự
```

Ví dụ với tên Logger:

```text
com.example.payment.PaymentService
```

`%logger` cho tên đầy đủ; `%logger{0}` cho `PaymentService`.

Với `%logger{36}`, Logback có thuật toán rút ngắn các thành phần package để giữ lại phần nhận diện quan trọng. **Độ dài không phải phép cắt chuỗi tùy tiện**; tùy tên thực tế, kết quả có thể không đạt chính xác số ký tự mục tiêu nếu không thể rút gọn thêm mà vẫn bảo toàn thành phần cuối. Đừng khẳng định một kết quả rút gọn duy nhất cho mọi tên Logger.

**Lưu ý quan trọng:** `%logger{0}` hay `%logger{36}` chỉ thay **cách hiển thị**, không đổi `ILoggerFactory`, đối tượng Logger, quan hệ kế thừa level hoặc tên Logger gốc trong event. Khi điều tra hệ thống lớn, tên quá ngắn có thể làm trùng các lớp cùng tên ở package khác nhau; chọn độ rút gọn đủ để phân biệt nguồn.

## 4. PatternLayout của Logback: ngôn ngữ trình bày

**PatternLayout** là công cụ định dạng text log theo một chuỗi pattern. Mỗi conversion specifier bắt đầu bằng dấu `%` và lấy một phần dữ liệu từ logging event.

Ví dụ:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

Kết quả minh họa:

```text
09:30:12.347 INFO  [main] c.e.payment.PaymentService - event=payment.completed
```

Đầu ra minh họa này phụ thuộc tên Logger và timestamp; không phải output cố định cho mọi ứng dụng.

### 4.1. Các conversion word quan trọng

| Pattern | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `%d{pattern}`, `%date{pattern}` | Thời gian sự kiện | Có thể cấu hình timezone theo cú pháp Logback |
| `%level`, `%p` | Level của event | TRACE/DEBUG/INFO/WARN/ERROR |
| `%-5level` | Level canh trái, độ rộng tối thiểu 5 | INFO có một dấu cách đệm |
| `%logger`, `%c` | Tên Logger | Mặc định tên đầy đủ |
| `%logger{0}` | Thành phần cuối tên Logger | Dễ đọc nhưng có thể trùng |
| `%logger{36}` | Tên Logger rút gọn | Giữ được nhiều thông tin package hơn |
| `%thread`, `%t` | Tên thread tạo event | Không dùng thay request/trace ID |
| `%msg`, `%message` | Message đã được định dạng | Đối số SLF4J được đưa vào message |
| `%X{requestId}` | Giá trị MDC theo khóa | Có thể rỗng khi context chưa được gắn |
| `%ex`, `%exception`, `%throwable` | Throwable/stack trace | Hình thức theo tùy chọn, có thể nhiều dòng |
| `%class`, `%method`, `%line` | Thông tin caller | Thường tốn chi phí xác định stack |
| `%n` | Ký tự xuống dòng theo nền tảng | Nên dùng thay ký tự xuống dòng viết cứng |

Trong `%logger{36}`, số trong ngoặc nhọn là **tùy chọn của conversion word**. Trong `%-5level`, `-5` là **format modifier** canh trái và độ rộng. Hai loại tùy chọn có vai trò khác nhau.

### 4.2. Canh cột, độ rộng và dấu phân cách

```text
%-5level [%thread] %logger{36} - %msg%n
```

`%-5level` cho ví dụ:

```text
INFO  [main] ...
WARN  [main] ...
ERROR [main] ...
```

Có **hai dấu cách** sau INFO/WARN trong ví dụ vì một dấu đệm của `%-5level` và một dấu cách literal trong pattern. ERROR dài 5 ký tự nên chỉ còn dấu cách literal.

Độ rộng giúp dễ quét mắt khi đọc text log, nhưng không phải schema cố định để máy phân tích theo vị trí: tên thread, tên logger và message có độ dài biến đổi. Nếu cần query/aggregation tự động, dùng trường cấu trúc thay vì parser dựa trên cột.

### 4.3. Chèn literal và quy tắc parse

Pattern có thể chứa chữ tự do để đặt nhãn:

```text
level=%level logger=%logger thread=%thread message=%msg%n
```

Kết quả sẽ có các nhãn `level=`, `logger=` thay vì chỉ giá trị. Điều này tốt cho người đọc nhưng **không tự giải quyết escape** với message có dấu cách, newline hoặc dữ liệu bên ngoài.

Khi một literal đi ngay sau conversion word mà không có dấu phân tách, parser có thể hiểu nhầm literal là phần của tên conversion. Hãy dùng dấu cách/ký tự phân tách hoặc cú pháp option phù hợp, và thử thực tế pattern. Không đưa biểu thức shell kiểu `$\{...\}` hoặc placeholder của SLF4J trực tiếp vào pattern khi chưa hiểu engine nạp biến của backend.

## 5. Phân biệt định dạng message và định dạng dòng log

Hai tầng này rất dễ nhầm:

**Tầng 1 — Message template trong source code:**

```java
logger.info("event=order.created orderId={} items={}", "ord-17", 3);
```

Đây là đoạn minh họa khi đã có `logger` SLF4J. Dấu `{}` là **placeholder tham số hóa message** của SLF4J. Message sau khi xử lý là:

```text
event=order.created orderId=ord-17 items=3
```

**Tầng 2 — Pattern của backend:**

```text
%-5level %logger{0} - %msg%n
```

Nếu Logger là `com.example.order.OrderService` và level INFO, dòng xuất theo pattern:

```text
INFO  OrderService - event=order.created orderId=ord-17 items=3
```

Cùng một bản ghi có thể trình bày khác nếu Appender sử dụng pattern khác, **nhưng message gốc/sự kiện vẫn là sự kiện đó**.

Không nhầm `{}` của SLF4J với `{0}`, `{1}` của JUL/`java.text.MessageFormat`, và cũng không nhầm với `%msg`, `%logger` của Logback PatternLayout. Đây là ba cú pháp ở những tầng khác nhau.

### 5.1. Giữ message ngắn, event name ổn định

Nên log các event theo cách dễ phân loại:

```java
logger.warn("event=payment.retry errorCode={} attempt={}",
        "GATEWAY_TIMEOUT", 2);
```

Các giá trị biến động nên nằm trong parameter hoặc structured fields để ít tạo string thủ công và giữ khả năng truy vấn. Không ghép tên Logger hoặc event động kiểu `"event=payment.retry." + requestId`; hãy dùng `requestId` riêng.

### 5.2. Placeholder không làm phép tính đắt trở nên lazy

```java
logger.debug("state={}", calculateExpensiveSnapshot());
```

Đây là đoạn minh họa; `calculateExpensiveSnapshot()` vẫn được Java đánh giá **trước** khi gọi `logger.debug`, dù DEBUG bị tắt. Khi biểu thức đắt, cân nhắc:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", calculateExpensiveSnapshot());
}
```

Placeholder trì hoãn việc ghép/format message bên trong logging framework theo thiết kế, không trì hoãn việc tính toán đối số trong ngôn ngữ Java.

## 6. Chọn trường nào để định dạng?

Một dòng log phục vụ vận hành thường nên có:

1. **Timestamp** và timezone rõ (khuyến nghị UTC nếu log tập trung từ nhiều host).
2. **Level** để ưu tiên xử lý.
3. **Service/instance** từ cấu hình nếu các log tập trung nhiều dịch vụ.
4. **Logger name** đủ dài để nhận diện lớp/module.
5. **Thread** khi có ích cho chẩn đoán đồng thời, nhưng không thay correlation ID.
6. **Request/trace/span ID** khi có ngữ cảnh theo request.
7. **Message/event name** ngắn, nhất quán.
8. **Exception** có stack trace theo chính sách đối với lỗi cần điều tra.

Một pattern text thường dùng trong ứng dụng Logback:

```xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n</pattern>
```

Đây là **mảnh XML nằm trong khối `<encoder>` của một Appender**, không phải file cấu hình đầy đủ. Nó dùng timezone UTC, canh level, hiển thị thread, tên logger rút gọn, ID từ MDC và message.

**Kết quả minh họa:**

```text
2026-01-12 09:30:12.347 WARN  [http-2] c.e.payment.PaymentService requestId=req-42 - event=provider.timeout
```

Đồng hồ, tên thread và tên Logger khác nhau giữa các lần chạy. Nếu cần format dễ parse máy, nên dùng **JSON encoder** hỗ trợ các trường có kiểu thay vì quy ước text này.

### 6.1. Timestamp: thời điểm event, không phải lúc đọc file

Pattern `%d` của Logback biểu diễn timestamp gắn với logging event. Để kết nối log từ nhiều node, cần chuẩn hóa timezone và định dạng; thứ tự timestamp có thể bị ảnh hưởng bởi lệch đồng hồ giữa host. Với hệ phân tán, đừng chỉ dựa vào timestamp để suy ra quan hệ nhân quả: `traceId` và span relationships có ý nghĩa hơn.

Khi đo latency, dùng đồng hồ đơn điệu như `System.nanoTime()`/công cụ tương đương; không lấy hiệu hai timestamp wall-clock nếu môi trường có thể điều chỉnh đồng hồ.

### 6.2. Thread name: hữu ích nhưng không là định danh request

`%thread` giúp thấy các task chạy trên `main`, thread pool hoặc HTTP worker. Nhưng một thread có thể xử lý nhiều request, và một request có thể chuyển thread. Vì vậy `requestId`/`traceId` cần được gắn riêng, không suy từ tên thread.

### 6.3. Logger name và mã sự kiện

`%logger` cho biết nguồn do mã đặt Logger. `event=payment.failed` trong message hoặc field cấu trúc cho biết **loại sự kiện**. Logger tên `PaymentService` có thể phát nhiều event; event `payment.failed` có thể đến từ nhiều lớp. Hai thông tin bổ sung cho nhau, không nên thay thế hoàn toàn.

## 7. MDC: đưa ngữ cảnh vào layout

**MDC (Mapped Diagnostic Context)** thường được cung cấp qua `org.slf4j.MDC` và backend hỗ trợ. Ví dụ:

```java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", "req-42");
    logger.info("event=request.received");
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đây là **mảnh mã**; giả sử `logger` và `processRequest()` đã có, đồng thời code import `org.slf4j.MDC`. Với pattern:

```text
%level requestId=%X{requestId} %logger{0} - %msg%n
```

sự kiện sẽ có `requestId` được lấy từ MDC thay vì người viết phải nối tay vào mỗi message.

**Phạm vi rất quan trọng:** nếu không xóa/khôi phục MDC trong `finally`, thread pool có thể giữ context của request trước và gắn nhầm cho request sau. MDC không tự động đi qua mọi `ExecutorService`, `CompletableFuture` hay reactive pipeline; khi đổi thread phải capture/propagate/restore context bằng cơ chế phù hợp.

Nếu `requestId` được lấy từ HTTP header không đáng tin cậy, cần kiểm tra độ dài, bộ ký tự và nguồn gốc trước khi đưa vào MDC. MDC không phải bộ bảo mật: dữ liệu client chứa newline, token hoặc payload nhạy cảm vẫn có thể phá cấu trúc/vi phạm chính sách nếu xuất nguyên văn.

## 8. Ví dụ Java 17 chạy độc lập: format tên Logger đầy đủ và rút gọn

Chúng ta dùng **Java 17 + SLF4J API + Logback Classic** qua Gradle. Ví dụ có hai Logger tên khác nhau:

- `demo.payments.PaymentService`, đặt level DEBUG riêng.
- `demo.shipping.ShippingService`, kế thừa root INFO.

Cấu hình `PatternLayoutEncoder` in **tên logger đầy đủ (`%logger`) và phần cuối (`%logger{0}`) trên cùng một dòng**, kèm level, thread, MDC `requestId` và message. Không in timestamp để stdout tái lập chính xác.

### 8.1. Cấu trúc thư mục

```text
logger-format-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggerFormatDemo.java
        └── resources/
            └── logback.xml
```

### 8.2. File `settings.gradle`

```groovy
rootProject.name = 'logger-format-demo'
```

### 8.3. File `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LoggerFormatDemo'
}
```

Hai version trên là **mốc xác định cho ví dụ**, không được hiểu là bản mới nhất. Trong ứng dụng thật cần dùng phiên bản được hỗ trợ, cập nhật bản vá bảo mật và dependency management nhất quán; chỉ nên có **một SLF4J provider** tại runtime.

### 8.4. File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level logger=%logger short=%logger{0} thread=%thread requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.payments.PaymentService" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

**Phân tích XML:**

- `STDOUT` là ConsoleAppender xuất vào `System.out`, thay vì mặc định phụ thuộc thiết lập console của backend.
- `%-5level` tạo cột level rộng tối thiểu 5 ký tự.
- `%logger` lấy tên đầy đủ; `%logger{0}` lấy phần cuối.
- `%thread` lấy tên thread lúc event được tạo.
- `%X{requestId}` lấy MDC của thread xử lý.
- `%msg` lấy message sau khi tham số `{}` của SLF4J được xử lý.
- `%n` kết thúc dòng.
- Root chỉ có một Appender; Logger payment có level riêng DEBUG nhưng không có Appender riêng. Log từ nhánh này vẫn truyền đến root Appender qua additivity.

### 8.5. File `src/main/java/demo/LoggerFormatDemo.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class LoggerFormatDemo {
    private static final Logger PAYMENT =
            LoggerFactory.getLogger("demo.payments.PaymentService");

    private static final Logger SHIPPING =
            LoggerFactory.getLogger("demo.shipping.ShippingService");

    public static void main(String[] args) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            PAYMENT.info("event=payment.started orderId={}", "ord-17");
            PAYMENT.debug("event=provider.request attempt={}", 2);
            SHIPPING.debug("event=shipping.diagnostic.hidden");
            SHIPPING.warn("event=inventory.low sku={}", "sku-9");
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
```

Mã Java chỉ import SLF4J, không phụ thuộc trực tiếp vào lớp Logback. Tên Logger đặt tường minh để thử `%logger` và `%logger{0}`; trong ứng dụng thật thường khai báo theo class với `getLogger(MyClass.class)`.

### 8.6. Biên dịch và chạy

Ở thư mục `logger-format-demo` với JDK 17 và Gradle hỗ trợ Java 17, chạy:

```bash
gradle run --quiet
```

Nếu dự án có sẵn Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Bộ file trên **không kèm Wrapper**; khi chạy lần đầu cần có Gradle/JDK và quyền tải thư viện từ repository.

**stdout chính xác do chương trình phát ra với đúng cấu hình:**

```text
INFO  logger=demo.payments.PaymentService short=PaymentService thread=main requestId=req-42 - event=payment.started orderId=ord-17
DEBUG logger=demo.payments.PaymentService short=PaymentService thread=main requestId=req-42 - event=provider.request attempt=2
WARN  logger=demo.shipping.ShippingService short=ShippingService thread=main requestId=req-42 - event=inventory.low sku=sku-9
```

**Giải thích kết quả:**

1. Logger `PAYMENT` được đặt DEBUG riêng, vì vậy cả INFO và DEBUG được chấp nhận.
2. Logger `SHIPPING` chưa đặt level riêng, kế thừa root INFO. Sự kiện `SHIPPING.debug` bị loại trước khi tới Appender.
3. `INFO` và `WARN` là level bốn chữ cái, được `%-5level` đệm một dấu cách, cộng thêm dấu cách literal trong pattern thành hai dấu.
4. `%logger` và `%logger{0}` lấy dữ liệu từ **cùng event**, nhưng hiển thị đầy đủ/rút gọn theo hai cách.
5. `%thread` là `main` khi chương trình gọi tuần tự từ main method.
6. `%X{requestId}` cho `req-42` ở cả ba dòng vì chương trình thiết lập MDC trước khi ghi.
7. Placeholder `{}` trong message được thay bằng `ord-17`, `2` hoặc `sku-9`; đó là chức năng định dạng message, **không phải** của `%logger`.
8. Không có timestamp nên các dòng từ mã ứng dụng có thể đối chiếu chính xác; thông báo tải dependency/build do Gradle phát ra nếu có không thuộc stdout được mô tả.

### 8.7. Thay đổi thử nghiệm để tự quan sát

- **Đổi `%logger{0}` thành `%logger{36}`:** xem tên được rút gọn theo thuật toán package thay vì chỉ lấy phần cuối. Đừng giả định output là một phép cắt từ trái sang phải.
- **Đổi `<root level="INFO">` thành `DEBUG`:** dòng `SHIPPING.debug` bắt đầu xuất. Đây là thay đổi level, không phải định dạng.
- **Bỏ cấu hình `<logger name="demo.payments.PaymentService" level="DEBUG"/>`:** Logger payment trở lại kế thừa INFO; dòng PAYMENT DEBUG bị loại.
- **Bỏ `%X{requestId}` khỏi pattern:** Java vẫn gắn MDC nhưng **dòng text không hiển thị** ID đó; context và phần trình bày là hai lớp độc lập.
- **Đổi `%msg` thành `%message`:** đây là alias trong Logback, cùng mục tiêu hiển thị message.
- **Đổi tên Logger ở Java nhưng không sửa cấu hình level theo tên:** level override có thể không còn áp dụng do tên Logger không khớp. Layout không phải nơi sửa quy tắc chọn level.

## 9. Hiển thị exception và stack trace

Một log lỗi thường cần nguyên nhân có cấu trúc:

```java
try {
    paymentGateway.call();
} catch (RuntimeException ex) {
    logger.error("event=payment.failed orderId={}", orderId, ex);
}
```

Đây là **mảnh minh họa** với các biến và `paymentGateway` đã tồn tại. Trong SLF4J, throwable được truyền ở vị trí phù hợp để backend lưu vào event thay vì nối thủ công `ex.getMessage()` vào message. Một số overload khác nhau có hành vi khác nhau, nên cần dùng đúng API đang sử dụng.

Logback PatternLayout hỗ trợ các conversion word cho exception, ví dụ:

```text
%level %logger - %msg%n%ex
```

`%ex` có thể xuất stack trace **nhiều dòng**, gồm exception type, message và các frame. Một số pattern có tùy chọn giới hạn độ sâu, nhưng rút quá ngắn có thể làm mất vị trí lỗi. Nếu pattern không chứa conversion word xử lý throwable, Logback PatternLayout có cơ chế mặc định bổ sung thông tin exception trong nhiều cấu hình; **không nên dựa vào suy đoán** rằng mọi custom pattern tự động làm mất stack trace. Nếu cần chính sách cố ý suppress, `%nopex` là cơ chế riêng trong Logback, nhưng không nên dùng trong sản xuất khi vẫn cần stack trace để điều tra.

Với hệ thống collector nhận một event mỗi dòng, stack trace nhiều dòng có thể bị phân tách thành các event rời rạc. Giải pháp thường tốt hơn là dùng encoder structured JSON có trường exception riêng hoặc cấu hình multiline parsing phù hợp. Cũng cần hạn chế dữ liệu nhạy cảm trong exception messages vì stack trace có thể chứa URL, tên người dùng hoặc tham số được đưa vào thông báo lỗi.

**Quy tắc log ngoại lệ:** ghi stack trace ở ranh giới xử lý phù hợp; không in cùng một exception ở mọi tầng nếu không tạo thêm giá trị chẩn đoán. Một event ERROR thiếu `Throwable` có thể khó điều tra, nhưng một pipeline in stack trace trùng nhiều nơi sẽ tốn tài nguyên và gây nhiễu.

## 10. Có nên in class, method và line number?

Trong Logback, các conversion word như `%class`, `%method` và `%line` có thể cho thông tin call site:

```text
%class.%method:%line - %msg%n
```

Tuy nhiên, chúng có thể đòi hỏi backend xác định caller data từ stack trace, tốn chi phí hơn việc lấy `%logger`. Trong ứng dụng logging nhiều và nhạy cảm về độ trễ, **tránh bật caller data toàn cục** nếu không thật sự cần.

Trường hợp dùng wrapper/helper, caller data có thể chỉ về helper nếu framework hoặc wrapper không cung cấp thông tin đúng cách. Không khẳng định cứ thêm `%method` là sẽ thu được caller nghiệp vụ mong muốn.

Một cấu hình thực tế thường dùng **logger name + event code + traceId** để truy vết trước; chỉ thêm caller class/method/line ở môi trường hoặc phạm vi debug cần thiết, sau khi benchmark.

## 11. Structured JSON khác text PatternLayout như thế nào?

Một pattern text:

```text
level=%level logger=%logger requestId=%X{requestId} message=%msg%n
```

giúp người đọc thấy nhãn. Nhưng nếu message hoặc request ID chứa dấu cách, dấu ngoặc kép hay ký tự xuống dòng, hệ thống parse bằng regex có thể sai. Text pattern vẫn chỉ là **một chuỗi**.

Structured JSON dùng schema và escaping:

```json
{
  "timestamp": "2026-01-12T09:30:12.347Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "thread": "http-2",
  "service": "checkout",
  "requestId": "req-42",
  "event": "payment.failed",
  "errorCode": "GATEWAY_TIMEOUT",
  "durationMs": 1200
}
```

Đây là ví dụ minh họa; Logback không tự tạo JSON này chỉ vì bạn viết `<pattern>%msg</pattern>`. Với hệ thống observability, nên dùng **encoder JSON được backend/framework hỗ trợ** và có khả năng xuất các field có kiểu dữ liệu đúng. Tùy phiên bản, giải pháp có thể là structured logging tích hợp của framework hoặc encoder bên thứ ba. Đừng tự ghép JSON bằng string concatenation rồi mong mọi dấu nháy, Unicode và ký tự điều khiển được mã hóa an toàn.

### 11.1. Chọn schema ổn định

Nên thống nhất `timestamp`, `level`, `logger`, `service`, `traceId`, `spanId`, `requestId`, `event`, `errorCode`, `durationMs` theo nhu cầu. Không cần đưa mọi trường vào mọi event, nhưng **cùng một trường phải có kiểu và ý nghĩa nhất quán**.

Ví dụ `durationMs` trong JSON nên là số, không lúc là `1200` lúc là chuỗi `"1.2s"`. Một số hệ thống tracing dùng `trace_id`/ `span_id`; nếu đã có schema chuẩn nội bộ, nên theo chuẩn đó thay vì tự đặt biến thể.

### 11.2. Không dùng logger name làm dimension có cardinality vô hạn

Tên Logger theo package/class tương đối ổn định, phù hợp chẩn đoán nguồn. Không tạo tên Logger động chứa request ID, user ID hoặc order ID. Các field này có cardinality cao, thích hợp hơn với log/tracing có chính sách lưu trữ và truy vấn, không dùng bừa làm label metric.

## 12. So sánh với JUL SimpleFormatter

Với JUL (`java.util.logging`), định dạng bản ghi dựa trên `Formatter` gắn vào `Handler`. `SimpleFormatter` có thuộc tính cấu hình:

```properties
java.util.logging.SimpleFormatter.format = %1$tF %1$tT %4$s logger=%3$s - %5$s%6$s%n
```

Đây là **một dòng thuộc file `logging.properties`**; nó dùng cú pháp `java.util.Formatter`/`String.format`, không phải các conversion word của Logback. Các đối số quan trọng:

| Chỉ số `String.format` | Nội dung do SimpleFormatter cung cấp |
| --- | --- |
| `%1$tF`, `%1$tT` | Date/time của event ở timezone hệ thống |
| `%2$s` | Source class/method nếu biết, nếu không thì tên logger |
| `%3$s` | Tên logger |
| `%4$s` | Level |
| `%5$s` | Message sau `formatMessage(LogRecord)` |
| `%6$s` | Throwable/stack trace đã format nếu có |
| `%n` | Newline theo nền tảng |

Ví dụ **mảnh mã JUL**:

```java
java.util.logging.Logger julLogger =
        java.util.logging.Logger.getLogger("com.example.payment.PaymentService");
julLogger.log(java.util.logging.Level.INFO, "orderId={0}", "ord-17");
```

JUL dùng cú pháp tham số `{0}`, không phải `{}` của SLF4J. Trong Logback, cú pháp `%logger` lấy tên logger từ logging event; trong JUL SimpleFormatter, `%3$s` lấy tên logger qua đối số thứ ba do `SimpleFormatter` cung cấp. Hai ngôn ngữ format không tương đương, dù mục tiêu trình bày khá giống nhau.

**ConsoleHandler của JUL thường ghi ra stderr**. Muốn stdout ổn định hoặc custom JSON, cần Handler/Formatter phù hợp; không đơn giản đổi `SimpleFormatter.format` rồi mong nó biến ConsoleHandler thành stdout hay thay level của Logger.

## 13. Khi thay backend, điều gì được giữ và điều gì phải đổi?

SLF4J giữ API nghiệp vụ tương đối độc lập với backend, nhưng phần định dạng nằm ở implementation. Ví dụ chuyển từ Logback sang Log4j 2:

- Code `org.slf4j.Logger` và message `{}` thường giữ được nếu provider mới tương thích.
- File `logback.xml` không còn điều khiển backend mới; phải cấu hình theo hệ Log4j 2 (`log4j2.xml` hoặc cơ chế tương đương).
- Log4j 2 cũng có PatternLayout, nhưng không giả định **mọi conversion word, quy tắc exception, option và filter** giống hệt Logback.
- MDC/ThreadContext và structured fields cần được kiểm tra theo backend/provider cụ thể.
- Chỉ giữ một provider SLF4J phù hợp trong runtime classpath; tránh bridge hai chiều tạo vòng chuyển tiếp.

Định dạng logger tốt nên được xác định bằng **hợp đồng output**: các field bắt buộc, timezone, độ dài tên logger, newline/exception, escaping, schema của collector, retention và yêu cầu phân quyền; không chỉ bằng một dòng pattern được sao chép.

## 14. Những lỗi thường gặp khi định dạng logger

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Log chỉ có message, không biết lớp phát | Pattern thiếu `%logger` hoặc tên Logger quá ngắn | Thêm tên đầy đủ hoặc `%logger{36}` phù hợp |
| Hai lớp khác package đều hiển thị cùng tên | Dùng `%logger{0}` khiến tên rút gọn trùng | Dùng tên dài hơn, tránh mất thông tin package |
| `{ }` còn xuất nguyên văn trong message | Dùng sai API/placeholder, truyền tham số không đúng | Kiểm tra cú pháp SLF4J `{}` và overload |
| Không thấy `requestId` dù đã `MDC.put` | Pattern/encoder không lấy MDC, context bị mất khi đổi thread | Kiểm tra `%X{requestId}` và propagation |
| `DEBUG` không xuất sau khi thay pattern | Logger level hoặc filter chặn | Kiểm tra level trước Formatter/Encoder |
| Đặt `%logger` trong `logging.properties` JUL | Dùng nhầm ngôn ngữ PatternLayout | Dùng `SimpleFormatter.format` với `%3$s` hoặc custom Formatter |
| File log thiếu stack trace | Throwable chưa được truyền đúng, layout/encoder xử lý không phù hợp | Kiểm tra `getThrown`/Throwable, `%ex`, chính sách exception |
| Stack trace bị tách thành nhiều record | Pattern text nhiều dòng, collector không hiểu multiline | Dùng JSON encoder hoặc multiline parser |
| Pattern có `%class`/`%line` làm ứng dụng chậm | Thu caller data tốn chi phí | Hạn chế caller conversion; ưu tiên `%logger` |
| Log có timestamp lệch giữa các host | Timezone/cấu hình đồng hồ không nhất quán | Ghi timezone rõ, thường UTC; đồng bộ đồng hồ |
| Chỉnh `logback.xml` mà output không đổi | Backend runtime không phải Logback, file không được load | Kiểm tra provider, classpath và cấu hình framework |
| JSON log không parse được | Dùng text pattern nối JSON thủ công, escape không đầy đủ | Chuyển sang encoder JSON đáng tin cậy |
| Có nhiều dòng log trùng | Appender gắn nhiều vị trí hoặc additivity | Kiểm tra Logger hierarchy và appender-ref |
| Dữ liệu nhạy cảm bị lộ | Message/Throwable/MDC chứa secret | Không ghi secret ngay từ đầu; lọc/allowlist và kiểm soát truy cập |

### Quy trình gỡ lỗi

1. Xác định lời gọi logger thật sự được thực hiện và tên Logger thực tế.
2. Kiểm tra level/filters của Logger để biết event có được chấp nhận không.
3. Xác định backend runtime (Logback, JUL, Log4j 2...) và Appender/Handler đang nhận event.
4. Xác định Formatter/Encoder của chính Appender đó và pattern/file cấu hình thực sự được nạp.
5. Kiểm tra message parameters, MDC, thread, time zone và Throwable riêng từng mục.
6. So sánh output thực với hợp đồng field, sau đó kiểm tra stdout/stderr/file/collector.
7. Nếu có nhiều Appender hoặc async, kiểm tra trùng event, thứ tự, buffer và flush.

## 15. Hiệu năng, bảo mật và khả năng vận hành

**Hiệu năng:** rút gọn logger name bằng `%logger{n}` là thao tác trình bày; nó không chữa được một pipeline logging quá tải. Những chi phí đáng kể thường nằm ở việc tạo đối số đắt, thu caller stack, format exception, I/O, queue, encoder và collector. Chọn pattern phù hợp mục tiêu thay vì in càng nhiều dữ liệu càng tốt.

**Log injection:** giá trị từ người dùng có thể chứa newline (`\\n`), carriage return (`\\r`) hoặc ký tự điều khiển để tạo log giả. Pattern text như `message=%msg%n` không tự bảo đảm input đã được escape đúng. Trước khi ghi, cần kiểm tra/giới hạn dữ liệu được nhận, hoặc sử dụng JSON encoder chuẩn và phương án xử lý control characters theo hệ thống đích.

**Dữ liệu nhạy cảm:** không đưa password, bearer token, cookie, private key, CVV, payload nhạy cảm hoặc nội dung nhận dạng cá nhân không cần thiết vào message/MDC/Throwable. Một cấu hình che dữ liệu ở layout không bảo đảm nhận diện mọi secret; tốt nhất là loại bỏ ngay từ bước tạo event.

**Khả năng vận hành:** nếu dùng stdout trong container, định dạng nên phù hợp hệ thống thu thập. Nếu ghi file, cần rolling/retention và quyền ghi. Formatter/Encoder không bảo đảm bản ghi đã được lưu bền vững: async queue, crash, hệ thống file đầy hoặc collector lỗi vẫn có thể gây mất event. Sự kiện audit quan trọng cần thiết kế cơ chế lưu trữ riêng theo yêu cầu.

## 16. Checklist thiết kế định dạng logger

- [ ] Logger name ổn định, theo class/package hoặc subsystem; không chứa request ID động.
- [ ] Có level và message/event code rõ ràng; xác định Logger/Appender filtering độc lập với format.
- [ ] Cân nhắc `%logger`, `%logger{0}` và `%logger{n}` theo nhu cầu phân biệt package.
- [ ] Phân biệt placeholder `{}` của SLF4J, `{0}` của JUL và `%...` của Logback PatternLayout.
- [ ] Timestamp có format/timezone rõ, thường UTC nếu nhiều host.
- [ ] Có thread name và request/trace ID khi cần, không lấy thread làm request ID.
- [ ] MDC được truyền và khôi phục đúng qua các phạm vi xử lý, nhất là thread pool/async.
- [ ] Throwable có chính sách xuất stack trace, không mất thông tin lỗi cần điều tra.
- [ ] Nếu cần structured log, dùng JSON encoder/schema phù hợp thay vì giả JSON bằng nối chuỗi.
- [ ] Không ghi dữ liệu bí mật, kiểm soát ký tự nguy hiểm và retention/access control.
- [ ] Test output với INFO, DEBUG, WARN, ERROR, event có MDC, event có exception và nhiều Logger khác tên.
- [ ] Kiểm tra đúng backend, Appender/Handler, stdout/stderr và collector thực tế.

### Tài liệu chính thức

- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): `PatternLayout`, conversion words, formatter modifiers, MDC và caller data.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): Logger hierarchy và cách nạp cấu hình.
- [SLF4J Manual](https://www.slf4j.org/manual.html): API facade, parameterized logging, logger naming.
- [JDK 17 — SimpleFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html): `String.format` arguments và thuộc tính `SimpleFormatter.format`.
- [Apache Log4j — Layouts](https://logging.apache.org/log4j/2.x/manual/layouts.html): phân biệt PatternLayout và các lựa chọn structured layout.

**Kết luận:** Định dạng logger tốt giúp người đọc nhìn ra **nguồn phát, mức độ, thời gian, ngữ cảnh và bản chất sự kiện** mà không sửa logic nghiệp vụ. Trong Logback, `%logger` hiển thị tên đầy đủ, `%logger{0}` hiển thị phần cuối, còn `%logger{n}` rút gọn tên để giữ log gọn. Kết hợp đúng với `%level`, `%thread`, `%X`, `%msg`, timestamp và Throwable sẽ tạo các bản ghi dễ điều tra; khi cần phân tích máy ở quy mô lớn, ưu tiên một schema JSON và encoder đúng chuẩn.
