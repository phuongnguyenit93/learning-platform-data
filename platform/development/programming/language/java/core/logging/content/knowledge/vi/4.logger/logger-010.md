# Đặt tên logger nhất quán trong Java

## 1. Tên logger là gì và vì sao cần nhất quán?

Trong ứng dụng Java, **logger** là đối tượng dùng để phát ra sự kiện log. Mỗi logger thường có một **tên định danh** (`logger name`) giúp xác định nguồn tạo sự kiện. Khi log được ghi ra console, file hoặc hệ thống tập trung, tên này thường xuất hiện cùng level, thời gian, message và các trường ngữ cảnh.

Ví dụ:

```text
INFO  com.example.orders.OrderService  event=order_accepted orderId=ORD-7
WARN  com.example.payments.PaymentClient  event=payment_retry paymentId=PAY-2
```

Các dòng trên là **minh họa**: có thể dùng level `WARNING` thay `WARN` nếu backend là `java.util.logging`. Phần `com.example.orders.OrderService` và `com.example.payments.PaymentClient` là **tên logger**, không phải message; chúng gợi ý log xuất phát từ thành phần nào.

Nếu mỗi lập trình viên tùy ý chọn tên `main`, `log1`, `payment`, `OrderSvc` hoặc tên chứa ID động, việc tìm, lọc và cấu hình log sẽ thiếu nhất quán. Một quy ước ổn định giúp:

1. **Tìm nguồn sự kiện:** nhìn tên logger để biết package/lớp phát log.
2. **Cấu hình theo nhóm:** bật chi tiết hơn cho `com.example.payments` mà không tăng lượng log của toàn hệ thống.
3. **Tra cứu tập trung:** dễ nhóm các bản ghi của cùng thành phần và tạo dashboard/truy vấn nhất quán.
4. **Bảo trì, refactor:** tên được sinh từ `Class` giảm lỗi gõ sai khi đổi tên hoặc di chuyển lớp.
5. **Giảm xung đột:** các package khác nhau có thể có lớp cùng tên `Service` mà vẫn có logger khác nhau.

Tên logger là **định danh nguồn phát sự kiện**, không phải nơi chứa dữ liệu giao dịch. `requestId`, `orderId`, `userId`, `traceId`, hostname, môi trường hoặc tên thread nên nằm ở trường ngữ cảnh thích hợp, không nằm trong tên logger.

## 2. Quy ước mặc định: tên logger theo tên đầy đủ của lớp

Với phần lớn mã Java nghiệp vụ, quy ước đơn giản và bền vững là:

**Mỗi lớp có một logger riêng, lấy tên từ fully qualified class name (FQCN) của chính lớp đó.**

Với một lớp ở `com.example.orders.OrderService`, tên logger mong đợi là:

```text
com.example.orders.OrderService
```

Trong `java.util.logging` (JUL, có sẵn trong JDK), khai báo:

```java
package com.example.orders;

import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId=" + orderId);
    }
}
```

Đoạn này minh họa một lớp Java độc lập nhưng **không chứa `main`**; ví dụ có thể chạy đầy đủ ở phần sau. `OrderService.class.getName()` trả về `com.example.orders.OrderService` khi lớp nằm trong package được nêu. Không cần viết thủ công chuỗi tên logger.

Khi dùng **SLF4J** cùng một provider/backend như Logback hoặc Log4j 2, quy ước tương đương:

```java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId={}", orderId);
    }
}
```

**Lưu ý:** đoạn SLF4J dùng thư viện bên ngoài JDK, nên **không thể biên dịch chỉ với `javac` mà không có dependency SLF4J**. Lời gọi `LoggerFactory.getLogger(OrderService.class)` đặt tên logger theo tên lớp; cú pháp placeholder `{}` thuộc API logging tương ứng. JUL sử dụng cơ chế format parameter khác; không áp dụng máy móc cú pháp `{}` của SLF4J cho JUL.

### Vì sao nên dùng `OrderService.class` thay vì gõ chuỗi?

So sánh:

```java
// Dễ sai sau khi đổi tên lớp hoặc di chuyển package:
private static final Logger LOG =
        Logger.getLogger("com.example.orders.OrderService");

// Ưu tiên: nguồn tên dựa trên chính lớp đang khai báo:
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

Khi refactor bằng IDE, lời gọi `OrderService.class` thường được cập nhật cùng tên lớp. Chuỗi tự viết có thể còn giữ tên cũ và khiến cấu hình, bộ lọc hoặc dashboard truy vấn sai. Tuy nhiên, **đổi tên hoặc chuyển package vẫn có thể đổi logger name trong log thực tế**: cần kiểm tra các truy vấn, alert và cấu hình mức log phụ thuộc tên cũ.

Đây là quy tắc ưu tiên, không phải yêu cầu ngôn ngữ Java: đôi khi một logger tên nghiệp vụ có chủ đích phù hợp hơn, sẽ xét ở mục 6.

## 3. Hiểu cấu trúc tên theo package và lớp

Với hệ thống được chia theo package:

```text
com.example
├── orders
│   ├── OrderService
│   ├── OrderRepository
│   └── validation
│       └── OrderValidator
└── payments
    ├── PaymentClient
    └── PaymentService
```

Các tên logger nhất quán tương ứng là:

```text
com.example.orders.OrderService
com.example.orders.OrderRepository
com.example.orders.validation.OrderValidator
com.example.payments.PaymentClient
com.example.payments.PaymentService
```

Trong những backend logging có cấu hình phân cấp theo dấu chấm, quy ước này giúp chọn phạm vi:

| Phạm vi logger | Phần chương trình được nhắm đến |
|---|---|
| `com.example` | Các thành phần của ứng dụng thuộc namespace chung |
| `com.example.orders` | Những logger con trong module/package đặt hàng |
| `com.example.payments` | Những logger con trong module/package thanh toán |
| `com.example.orders.OrderService` | Một lớp cụ thể |

**Phân cấp tên không đồng nghĩa với phụ thuộc mã nguồn:** package `com.example.orders` không cần gọi phương thức của package `com.example.payments` để hai logger cùng nằm dưới namespace `com.example`.

Tên package thông thường được viết chữ thường theo quy tắc Java, phân tách bằng dấu chấm. Tên lớp dùng cách viết `UpperCamelCase`. Hãy giữ nguyên chữ hoa/chữ thường; không trộn `com.example.OrderService` với `com.example.orders.orderservice` vì chúng là hai tên khác nhau.

### Cấp lớp hay cấp package?

- **Mặc định:** logger theo **lớp**, vì dễ xác định chính xác nguồn sự kiện và hỗ trợ cấu hình ở mức package.
- **Logger theo package hoặc category:** chỉ dùng khi nhiều thành phần thực sự chia sẻ một luồng sự kiện đã được quy ước, chẳng hạn `com.example.orders.events`. Cần đặt tên, phạm vi và mục đích bằng tài liệu rõ ràng.
- **Logger quá chung** như `app`, `logger` hoặc `main` dùng cho mọi lớp sẽ làm mất thông tin nguồn; nếu buộc dùng chung, phải ghi thêm trường component/source ổn định.

Không đặt tên logger bằng `Class.getSimpleName()` làm mặc định: `com.example.orders.Service` và `com.example.payments.Service` đều thành `Service`, gây khó phân biệt.

## 4. Tên logger và cơ chế cấu hình mức log

Nhiều hệ thống logging hỗ trợ bộ lọc và level theo tên logger. Điều này khiến quy tắc đặt tên ảnh hưởng trực tiếp tới vận hành.

Ví dụ yêu cầu:

- Mặc định chỉ ghi sự kiện từ mức `INFO` trở lên.
- Khi xử lý sự cố thanh toán, tăng chi tiết cho namespace `com.example.payments`.
- Không làm các thành phần xử lý đơn hàng ghi thêm lượng lớn debug log.

Với Logback, ý tưởng có thể được thể hiện bằng một cấu hình như sau:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payments" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là **ví dụ cấu hình Logback**, dành cho ứng dụng đã dùng Logback làm backend; không phải cú pháp XML dành cho JUL. Cấu hình trên có ý nghĩa: logger trong namespace thanh toán có thể phát mức `DEBUG`, còn phần còn lại kế thừa mức `INFO` của root. Appender console vẫn nhận các sự kiện đi qua root theo quy tắc kế thừa/additivity mặc định.

**Phân biệt hai việc:**

1. Logger và level quyết định một sự kiện có đủ điều kiện được phát hay không; quy tắc level/inheritance tùy backend.
2. Handler/appender và filter của chúng quyết định sự kiện được ghi tới đâu, có bị lọc tiếp hay không.

Việc đặt tên nhất quán **không đảm bảo** tự động nhận đúng cấu hình nếu backend hoạt động khác dự kiến. Khi đổi cấu hình, cần kiểm tra tên logger thực tế, level hiệu lực, filter, additivity và handler/appender đang gắn.

### Phân cấp trong JUL

Với `java.util.logging`, `Logger.getLogger("com.example")` tạo hoặc trả về logger theo tên đó. Một logger như `com.example.orders.OrderService` có thể kế thừa level từ logger cha gần nhất đã tồn tại theo phân cấp tên. Ví dụ:

```java
Logger group = Logger.getLogger("com.example");
group.setLevel(Level.INFO);

Logger payments = Logger.getLogger("com.example.payments");
payments.setLevel(Level.FINE);
```

Hai dòng khởi tạo này là **đoạn minh họa cấu hình**, không phải chương trình có thể chạy độc lập. Các logger con tương ứng có thể kế thừa level nếu không khai báo level riêng. `Level.FINE` của JUL gần với ý nghĩa debug nhưng không phải cùng tên hoặc một mapping bắt buộc với `DEBUG` của Logback. Handler có level riêng, vì vậy chỉ bật `FINE` ở logger chưa đủ nếu handler vẫn loại `FINE`.

Đặc biệt, **propagation của sự kiện lên handler cha** và **kế thừa mức log** là những cơ chế có liên quan nhưng khác nhau. `setUseParentHandlers(false)` thay đổi việc gửi sự kiện tới handler của logger cha; nó không tự biến tên logger thành một chuỗi khác.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai logger theo đúng lớp

Ví dụ sau chỉ sử dụng `java.util.logging` của JDK và cho thấy tên logger được sinh từ lớp, cách gom logger theo `com.example`, đồng thời xuất kết quả dễ kiểm chứng. Có ba tệp, mỗi tệp đặt đúng đường dẫn package.

### 5.1. Tệp `src/com/example/orders/OrderService.java`

```java
package com.example.orders;

import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void acceptOrder(String orderId) {
        LOG.info("event=order_accepted orderId=" + orderId);
    }
}
```

### 5.2. Tệp `src/com/example/payments/PaymentClient.java`

```java
package com.example.payments;

import java.util.logging.Logger;

public final class PaymentClient {
    private static final Logger LOG =
            Logger.getLogger(PaymentClient.class.getName());

    public void scheduleRetry(String paymentId) {
        LOG.warning("event=payment_retry_scheduled paymentId=" + paymentId);
    }
}
```

### 5.3. Tệp `src/com/example/app/LoggerNamingDemo.java`

```java
package com.example.app;

import com.example.orders.OrderService;
import com.example.payments.PaymentClient;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerNamingDemo {
    public static void main(String[] args) {
        // Cấu hình logger cha trước khi các lớp phát sự kiện.
        Logger application = Logger.getLogger("com.example");
        application.setLevel(Level.INFO);
        application.setUseParentHandlers(false);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + record.getLoggerName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        application.addHandler(console);

        new OrderService().acceptOrder("ORD-7");
        new PaymentClient().scheduleRetry("PAY-2");
        console.flush();
    }
}
```

Cấu trúc thư mục cần có:

```text
src/
└── com/
    └── example/
        ├── app/
        │   └── LoggerNamingDemo.java
        ├── orders/
        │   └── OrderService.java
        └── payments/
            └── PaymentClient.java
```

Tại thư mục chứa `src`, biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 -d out src/com/example/app/LoggerNamingDemo.java src/com/example/orders/OrderService.java src/com/example/payments/PaymentClient.java
java -cp out com.example.app.LoggerNamingDemo
```

Kết quả hiển thị trên console:

```text
INFO com.example.orders.OrderService | event=order_accepted orderId=ORD-7
WARNING com.example.payments.PaymentClient | event=payment_retry_scheduled paymentId=PAY-2
```

Đó là các dòng nội dung xác định; `ConsoleHandler` mặc định ghi ra **stderr**, không phải stdout. Nếu chuyển hướng riêng hai luồng đầu ra, cần đọc từ stderr để thấy hai dòng này.

### 5.4. Giải thích kết quả

- `OrderService.class.getName()` trả về `com.example.orders.OrderService`; `PaymentClient.class.getName()` trả về `com.example.payments.PaymentClient`. Hai logger có tên riêng, không cần gõ chuỗi.
- Logger ứng dụng `com.example` được cấu hình trước, cho phép hai logger con kế thừa mức `INFO`. `WARNING` cao hơn `INFO` theo thứ tự mức độ của JUL nên cả hai sự kiện đều có thể xuất hiện.
- `console.setLevel(Level.ALL)` bảo đảm handler trong ví dụ không loại thêm các mức log đã được logger chấp nhận.
- `application.setUseParentHandlers(false)` ngăn gửi tiếp bản ghi tới các handler bên trên `com.example` trong demo, tránh lặp output từ root logger mặc định.
- Formatter đọc `record.getLoggerName()`, tức **tên logger trên sự kiện**, chứ không suy luận nguồn từ message.
- Phần output được cố tình giản lược timestamp để dễ tái hiện. Khi vận hành thực tế, cần bổ sung thời gian, timezone, request/trace ID và throwable khi có lỗi.

Ví dụ cũng cho thấy **tên logger và message làm hai nhiệm vụ khác nhau**: `com.example.orders.OrderService` nói ai phát sự kiện, còn `event=order_accepted orderId=ORD-7` nói sự kiện nào và dữ liệu nào liên quan.

## 6. Khi nào dùng tên logger theo nhóm chức năng thay vì theo lớp?

Không phải mọi logger bắt buộc mang tên lớp. Ví dụ, một hệ thống có luồng sự kiện thống nhất `com.example.audit` hoặc `com.example.security.events`. Một nhóm có thể chủ động đưa các sự kiện vào logger category ổn định:

```java
// Ví dụ JUL, giả định logger này dành riêng cho sự kiện audit.
private static final Logger AUDIT =
        Logger.getLogger("com.example.audit");
```

Lúc này, tên `com.example.audit` thể hiện **loại sự kiện**, không nói chính xác lớp nào phát log. Cần có quy ước phân biệt logger chẩn đoán theo lớp và logger category chung; nếu muốn vẫn tra cứu chính xác nguồn thì bổ sung trường `component`/`source` phù hợp.

Nhưng **tên có chữ “audit” không tự tạo ra một audit trail đáng tin cậy**. Nhật ký kiểm toán có thể cần kiểm soát ghi, quyền truy cập, tính toàn vẹn, thời hạn lưu, khả năng truy vết và yêu cầu tuân thủ riêng. Đừng đánh đồng việc đặt tên với các bảo đảm này.

Nếu một sản phẩm dùng nhiều module hoặc service, có thể thêm namespace đủ đặc trưng, ví dụ `com.example.billing.invoice` và `com.example.shipping.delivery`. Cố gắng duy trì cấu trúc ổn định trong phạm vi một ứng dụng, tránh đặt tên đè lên package của thư viện bên thứ ba.

## 7. Những tên không nên dùng

### 7.1. Tên quá ngắn hoặc không mô tả nguồn

```java
// Không nên: mỗi lớp dùng một tên khác nhau theo cảm tính.
Logger.getLogger("log");
Logger.getLogger("main");
Logger.getLogger("payment-debug");
```

Nếu tên mang tính tùy tiện, việc nhận diện thành phần và cấu hình theo package mất đi lợi thế. Giữ tên từ lớp hoặc namespace chức năng đã được thống nhất.

### 7.2. Tên logger biến đổi theo mỗi request

```java
// Không nên tạo logger mới theo dữ liệu giao dịch:
Logger.getLogger("orders." + orderId);
Logger.getLogger("user." + userId);
Logger.getLogger("request." + requestId);
```

Dữ liệu thay đổi theo request làm số lượng tên logger tăng mạnh, khiến việc cấu hình, tìm kiếm, thu thập và quản lý các logger trở nên khó khăn. Ngoài ra, nó có thể làm lộ định danh nhạy cảm trong trường logger name.

Hướng phù hợp là giữ **tên logger ổn định** và đưa giá trị biến đổi vào message hay trường có cấu trúc:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());

// Bên trong phương thức có biến orderId:
LOG.info("event=order_accepted orderId=" + orderId);
```

Các đoạn ở mục này chỉ minh họa cách đặt tên; không phải tệp Java hoàn chỉnh. Trong hệ thống thực tế, cần kiểm soát cả dữ liệu đầu vào của message để tránh lộ thông tin nhạy cảm hoặc log injection.

### 7.3. Dùng `getClass()` sai ngữ cảnh

```java
// Cẩn trọng trong constructor hoặc lớp cơ sở:
Logger.getLogger(getClass().getName());
```

`getClass()` trả về lớp runtime của đối tượng. Với lớp có kế thừa hoặc proxy, tên này có thể là lớp con, proxy do framework sinh ra hoặc kiểu khác với lớp nơi mã logging được viết. Nếu muốn logger theo **lớp khai báo**, dùng `MyClass.class`. Nếu có chủ đích log theo lớp runtime, hãy giải thích lý do và kiểm soát tính ổn định của tên.

### 7.4. Logger của lớp tiện ích bị dùng thay lớp nghiệp vụ

Nếu mọi service đều gọi một wrapper mà wrapper chỉ ghi log với logger `LoggingUtils`, hệ thống sẽ thấy phần lớn event xuất phát từ `LoggingUtils`, khiến việc tìm component thực sự khó khăn. Hãy cân nhắc wrapper có thể nhận hoặc bảo toàn định danh nguồn gọi, hoặc để từng lớp khai báo logger riêng.

### 7.5. Đưa level, môi trường hoặc phiên bản vào tên

Các tên `orders-prod`, `orders-staging`, `orders-v17` hoặc `orders-debug` làm việc chuyển môi trường/triển khai thay đổi luôn nhóm logger. Môi trường, version và service nên là metadata riêng ở hệ thống ghi/thu thập log; level là thuộc tính của từng sự kiện và cấu hình, không phải một phần tên logger mặc định.

## 8. Tên logger khác với các định danh truy vết

Tên logger trả lời **“thành phần nào phát log?”**; còn các trường như `requestId`, `traceId`, `orderId` trả lời **“sự kiện thuộc yêu cầu/giao dịch nào?”**

Ví dụ:

```text
level=INFO logger=com.example.orders.OrderService requestId=req-42 event=order_accepted orderId=ORD-7
level=INFO logger=com.example.payments.PaymentClient requestId=req-42 event=payment_requested paymentId=PAY-2
```

Hai dòng có **hai tên logger khác nhau**, nhưng cùng `requestId=req-42` nên có thể liên kết thành một hành trình xử lý.

Trong ứng dụng dùng SLF4J/Logback/Log4j 2, correlation ID thường được lưu trong MDC hoặc các trường structured logging. Nếu dùng MDC trên thread pool, phải đưa đúng ngữ cảnh vào và dọn đúng lúc để tránh dữ liệu request trước bị gắn sang request sau. Trong JUL mặc định, MDC **không phải thuộc tính tích hợp sẵn của `LogRecord`**; có thể đưa ngữ cảnh qua message, parameters hoặc một cơ chế bổ sung đã thiết kế.

Tên logger cũng khác với **event name**: `com.example.orders.OrderService` là nguồn, còn `event=order_accepted` là loại sự kiện. Một lớp có thể phát nhiều loại sự kiện khác nhau mà vẫn dùng cùng logger.

## 9. Các tình huống cần quyết định rõ quy ước

### 9.1. Đổi tên hoặc di chuyển lớp

Đổi `com.example.orders.OrderService` thành `com.example.orders.OrderApplicationService` làm thay đổi tên logger nếu dùng `Class.getName()`. Điều đó phù hợp với quy ước phản ánh mã hiện tại, nhưng các alert/query hay cấu hình riêng theo logger name cũ cần được cập nhật cùng đợt refactor. Không chuyển sang chuỗi hardcode cũ chỉ để “giữ yên” tên mà thiếu quyết định của nhóm.

Nếu một category nghiệp vụ được nhiều hệ thống bên ngoài phụ thuộc lâu dài, có thể cân nhắc tên category được quản lý ổn định; đây là ngoại lệ cần ghi thành quy ước riêng.

### 9.2. Lớp lồng nhau

`NestedClass.class.getName()` có thể trả về tên nhị phân chứa ký tự `$`, chẳng hạn `com.example.Outer$NestedClass`. Đây là cách đặt tên của Java với lớp lồng; nó khác tên package hay một chuỗi bị viết sai. Thống nhất xem lớp lồng cần logger riêng hay dùng logger lớp ngoài theo mục đích chẩn đoán.

### 9.3. Tên trùng ở các module

Hai package có thể có `Service` hoặc `Controller` giống nhau. Vì vậy `OrderService.class.getSimpleName()` và `PaymentService.class.getSimpleName()` khó mở rộng về lâu dài; tên đầy đủ có namespace giúp phân biệt. Nếu các module dùng cùng tên package/class nhưng triển khai vào nhiều service độc lập, thêm `service.name` ở metadata tập trung để phân biệt deployment; không nhất thiết đưa hostname hoặc instance ID vào logger name.

### 9.4. Framework hoặc thư viện bên thứ ba

Các thư viện thường dùng namespace của riêng mình, chẳng hạn `org.example.library`. Ứng dụng có thể điều chỉnh level cho thư viện đó bằng cấu hình, nhưng **không nên lấy logger của thư viện để ghi event nghiệp vụ**. Tên logger phải phản ánh mã nguồn hoặc category phát sinh sự kiện.

### 9.5. Chính sách riêng theo backend

SLF4J là facade; Logback và Log4j 2 có các cơ chế cấu hình logger, appender và additivity riêng. JUL cũng có hierarchy và handler riêng. Dùng một quy ước **tên** chung giữa các hệ sinh thái giúp con người dễ nhận diện, nhưng file cấu hình và semantics không thể tự động thay thế cho nhau.

## 10. Checklist thực hành và lỗi thường gặp

| Dấu hiệu | Khả năng sai | Hướng xử lý |
|---|---|---|
| Log của nhiều lớp đều mang tên `main` | Dùng logger chung không có namespace | Mỗi lớp tạo logger theo `MyClass.class` |
| Không điều chỉnh được log package thanh toán | Tên logger không bắt đầu bằng namespace mong muốn | Kiểm tra `logger.getName()`, package và quy tắc cấu hình backend |
| Sau refactor, alert không thấy sự kiện | Logger đổi tên theo tên lớp mới | Cập nhật alert, query và level config gắn với tên cũ |
| Logger name xuất hiện hàng nghìn biến thể | Có ID hoặc dữ liệu động trong tên | Dùng tên ổn định, đưa ID sang context/message |
| Cùng event xuất hiện hai lần | Trùng handler/appender hoặc additivity | Kiểm tra propagation, không kết luận do đặt tên |
| Thiếu request ID dù logger name đúng | Nhầm logger name với correlation ID | Thiết kế truyền request/trace context riêng |
| Log gắn nhầm lớp proxy/derived class | Lấy `getClass()` từ runtime | Dùng literal `MyClass.class` khi muốn tên lớp khai báo |
| Tên log nhạy cảm lộ ID cá nhân | Mã hóa user/tenant vào logger name | Giữ namespace ổn định và áp dụng quy tắc bảo vệ dữ liệu |

Khi review code, có thể dùng bộ câu hỏi sau:

1. Logger có được khai báo một lần như `private static final` trong lớp sử dụng hay không?
2. Tên mặc định có lấy từ `ThisClass.class` hoặc một category nghiệp vụ được phê duyệt không?
3. Tên có ổn định qua request, thread, môi trường và lần chạy không?
4. Package và chữ hoa/chữ thường có theo quy ước Java không?
5. Có thể cấu hình mức log theo namespace mà không ảnh hưởng nhầm thành phần khác không?
6. Message và trường ngữ cảnh có giữ tách biệt với tên logger không?
7. Khi thay tên/package, các rule và dashboard phụ thuộc logger name có được rà soát không?

**Nguyên tắc áp dụng:** với hầu hết lớp Java, khai báo logger riêng bằng `Logger.getLogger(ThisClass.class.getName())` (JUL) hoặc `LoggerFactory.getLogger(ThisClass.class)` (SLF4J), nhất quán theo package và lớp. Chỉ dùng category riêng khi có chủ đích và tài liệu rõ ràng. Như vậy, tên logger hỗ trợ xác định nguồn và cấu hình theo nhóm, còn message cùng các trường ngữ cảnh giữ chi tiết của từng sự kiện.
