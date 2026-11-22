# Logging facade, SLF4J và thư viện thực thi

Khi phát triển một ứng dụng Spring Boot, lập trình viên thường viết một dòng log rất đơn giản:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order {} was created", orderId);
~~~

Dòng code chỉ biết đến `Logger` và `LoggerFactory` của **SLF4J**, nhưng thông điệp thực tế được định dạng, lọc theo cấp độ và ghi ra console hoặc file bằng một **thư viện thực thi logging** như **Logback** hoặc **Log4j 2**. Sự tách biệt này là thiết kế có chủ đích: source code không cần phụ thuộc trực tiếp vào cơ chế ghi log cụ thể.

Trong Spring Boot, logging là một thành phần hạ tầng rất sớm của quá trình khởi động. Ứng dụng cần log cả khi ApplicationContext chưa được tạo, khi cấu hình bị lỗi và trong lúc shutdown. Spring Boot vì vậy chuẩn bị những mặc định giúp code có thể dùng logging ngay, đồng thời cung cấp điểm cấu hình để thay đổi cấp độ, định dạng và backend.

Bài học giải thích toàn bộ luồng **logging facade → SLF4J API → provider/binding → logging backend → output**, sự khác nhau giữa SLF4J, Logback, Log4j 2, Java Util Logging và Spring JCL; cách Spring Boot chọn mặc định; cách đổi backend; cách xử lý xung đột classpath; và những thực hành giúp log hữu ích mà không gây rủi ro về hiệu năng hoặc dữ liệu nhạy cảm.

## 1. Vì sao không dùng System.out.println để ghi log?

Java cho phép in trực tiếp:

~~~java
System.out.println("Order " + orderId + " created");
~~~

Cách này hợp lệ để thử nhanh một chương trình nhỏ, nhưng có hạn chế trong dịch vụ chạy lâu dài:

- Không có cấp độ chuẩn như `DEBUG`, `INFO`, `WARN`, `ERROR`.
- Không thể điều chỉnh riêng mức log cho package hoặc component mà không sửa code.
- Khó gắn timestamp, thread name, correlation ID và metadata nhất quán.
- Khó gửi output đến nhiều đích như console, file, log collector hoặc hệ thống quan sát.
- Dùng phép nối chuỗi ngay cả khi thông điệp không cần được phát ra.
- Khó áp dụng rolling, retention, asynchronous appenders và các quy tắc lọc.
- Dễ khiến thông tin nhạy cảm bị in không kiểm soát.

Ví dụ với logger:

~~~java
log.debug("Loading order {}", orderId);
log.info("Order {} created", orderId);
log.warn("Order {} is close to expiration", orderId);
log.error("Unable to finalize order {}", orderId, exception);
~~~

Bên vận hành có thể giữ `INFO` ở production và chỉ bật `DEBUG` cho package liên quan khi điều tra. Code nghiệp vụ không cần thay đổi.

### Logging không thay thế kết quả nghiệp vụ

Log là dữ liệu **quan sát hệ thống**, không phải nơi lưu trạng thái nghiệp vụ duy nhất. Một giao dịch thành công phải được phản ánh trong database hoặc nguồn sự thật phù hợp, không phải chỉ bằng một dòng `INFO`. Nếu hệ thống thu thập log tạm thời gián đoạn, dữ liệu nghiệp vụ vẫn phải được bảo toàn theo transaction của nó.

## 2. Logging facade là gì?

**Facade** là một giao diện chung đứng trước những implementation cụ thể. Người gọi tương tác với API ổn định mà không cần biết bên dưới sử dụng thư viện nào.

Ví dụ khái niệm:

~~~text
OrderService
    |
    v
Logger API (facade)
    |
    v
Logging backend
    |
    +--> Console
    +--> File
    +--> Remote collector
~~~

Nếu code import trực tiếp một logger API rất đặc thù của backend, việc đổi backend có thể khiến nhiều file source phải sửa. Nếu code dùng facade thống nhất, phần lớn thay đổi tập trung vào dependency và cấu hình runtime.

### Ba lớp thường gặp

| Lớp | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logging API / facade | Code gọi method nào để log? | SLF4J API, Commons Logging API |
| Provider / binding / adapter | API được nối với implementation nào? | SLF4J provider của Logback hoặc Log4j 2 |
| Logging backend | Ai lọc, format và ghi event? | Logback, Log4j 2, JUL |

Một ứng dụng có thể dùng nhiều API gốc từ các thư viện khác nhau. Khi đó, bridge/adaptor có thể đưa các lời gọi về một đường logging chung.

### Một logging facade không nhất thiết tự ghi log

SLF4J API xác định contract như `Logger.debug(...)` và `LoggerFactory.getLogger(...)`. Nó không yêu cầu mọi ứng dụng phải ghi file theo cách giống nhau. Tác vụ thực thi thuộc về provider/backend thực tế.

Vì thế, **có dependency `slf4j-api` không đồng nghĩa đã có một backend đang hoạt động**.

## 3. SLF4J là gì?

**SLF4J** (*Simple Logging Facade for Java*) là một abstraction logging phổ biến trong Java. Application code và nhiều thư viện có thể dùng cùng một API dù backend thực tế khác nhau.

Các class quan trọng:

~~~java
org.slf4j.Logger
org.slf4j.LoggerFactory
org.slf4j.MDC
org.slf4j.Marker
~~~

Ví dụ:

~~~java
package com.example.store.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderNumber) {
        log.info("Submitting order {}", orderNumber);

        // Nghiệp vụ đặt hàng.

        log.info("Order {} submitted", orderNumber);
    }
}
~~~

Code này không import trực tiếp `ch.qos.logback.*` hoặc `org.apache.logging.log4j.core.*`. Nó chỉ phụ thuộc facade.

### Vì sao các thư viện cũng nên phụ thuộc SLF4J API?

Một thư viện dùng SLF4J sẽ để **ứng dụng cuối cùng** quyết định output. Nếu thư viện tự ép người dùng cài một backend cụ thể, ứng dụng có thể có nhiều hệ thống logging đồng thời hoặc nhiều file cấu hình xung đột.

Nguyên tắc thông dụng:

- **Application:** chọn một SLF4J provider/backend rõ ràng và cấu hình nơi ghi log.
- **Reusable library:** ưu tiên chỉ phụ thuộc logging API; tránh ép backend lên ứng dụng tiêu thụ thư viện.

Điều này không có nghĩa mọi thư viện Java đều phải sử dụng SLF4J. Một số thư viện dùng JUL, Log4j API hoặc JCL; bridge giúp thống nhất trong những trường hợp phù hợp.

## 4. Logging backend là gì?

Backend chịu trách nhiệm biến lời gọi từ logger thành log event rồi quyết định có phát event hay không và ghi nó đi đâu.

Một backend điển hình có các thành phần:

~~~text
Logger call
    |
    v
Level check / filter
    |
    v
Log event
    |
    v
Appender / handler
    |
    +--> Console encoder
    +--> Rolling file appender
    +--> Async appender
    +--> Structured log encoder
    +--> Other supported sinks
~~~

Các khái niệm có thể có tên khác nhau giữa backend. Ví dụ, Logback và Log4j 2 thường dùng từ **appender**; Java Util Logging dùng **handler**.

### Những backend thường gặp

| Backend | Hệ sinh thái | Đặc điểm khái quát |
|---|---|---|
| **Logback** | SLF4J / QOS | Backend mặc định trong nhiều cấu hình Spring Boot starter thông dụng |
| **Log4j 2** | Apache Logging Services | Backend có hệ sinh thái cấu hình, appender, async và plugin riêng |
| **Java Util Logging (JUL)** | JDK | Logging API và implementation có sẵn trong JDK |
| **SLF4J Simple** | SLF4J | Implementation gọn nhẹ, thường dùng cho ví dụ hoặc công cụ nhỏ |
| **SLF4J NOP** | SLF4J | Bỏ qua log; hữu ích trong một số test đặc biệt nhưng nguy hiểm nếu vô tình dùng ở production |

Một backend không “tốt nhất” trong mọi trường hợp. Sự lựa chọn phụ thuộc nhu cầu, dependency hiện có, vận hành và cấu hình của tổ chức.

## 5. Spring Boot mặc định dùng gì?

Trong các dự án Spring Boot thông thường sử dụng starter như `spring-boot-starter-web`, dependency mặc định cho logging là **Spring Boot starter logging**, thường đưa **Logback** vào runtime classpath.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Nếu dự án có dependency management của Spring Boot và không loại trừ logging starter, thông thường đã có những thành phần logging cần thiết; không cần khai báo thêm Logback thủ công chỉ để dùng `LoggerFactory`.

Luồng khái quát:

~~~text
spring-boot-starter-web
           |
           v
spring-boot-starter
           |
           v
spring-boot-starter-logging
           |
           +--> SLF4J API
           +--> Logback backend/provider
           +--> Các bridge cần thiết
                    |
                    v
             Console logging
~~~

Sơ đồ có tính khái quát; cấu trúc dependency cụ thể thay đổi theo phiên bản Spring Boot hoặc những starter mà dự án sử dụng.

### Logback là mặc định, không phải API bắt buộc

Code nên viết:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

thay vì phụ thuộc vào class backend:

~~~java
import ch.qos.logback.classic.Logger;
~~~

Nếu app code chỉ sử dụng SLF4J, chuyển backend từ Logback sang Log4j 2 thường không đòi hỏi sửa hàng loạt lời gọi logger.

### Khi không dùng Spring Boot starter

Một ứng dụng Spring Boot được ghép dependency thủ công có thể không có logging starter. Khi đó cần xác minh `slf4j-api`, provider tương thích và backend đã hiện diện. Đừng giả định mọi ứng dụng Spring đều có Logback chỉ vì import thành công `LoggerFactory`.

## 6. Phân biệt SLF4J 1.7 binding và SLF4J 2.x provider

Điều này rất quan trọng khi nghiên cứu dependency tree và debug thông báo khởi động.

### Thế hệ SLF4J 1.7

Với SLF4J 1.7.x và thế hệ cũ, các implementation thường liên kết bằng cơ chế **binding**, gắn với class:

~~~text
org.slf4j.impl.StaticLoggerBinder
~~~

Những tài liệu cũ thường nói “SLF4J binding”. Ví dụ một thư viện cung cấp binding nối SLF4J API với backend.

### SLF4J 2.x

SLF4J 2.x dùng cơ chế **provider**, dựa trên Java `ServiceLoader` và contract:

~~~text
org.slf4j.spi.SLF4JServiceProvider
~~~

Một provider có thể xuất hiện trong runtime classpath và được SLF4J chọn để cung cấp logger factory.

Vì vậy:

- Với API 1.7, thông báo liên quan `StaticLoggerBinder` là quen thuộc.
- Với API 2.x, cần tìm **SLF4J providers**.
- Một binding chỉ dành cho SLF4J 1.7 không tự trở thành provider hợp lệ cho API 2.x.
- Provider/backend nên tương thích với major version của SLF4J API mà ứng dụng đang dùng.

Trong Spring Boot 3.x, hệ sinh thái thường sử dụng SLF4J 2.x. Với dự án cũ dùng Spring Boot 2.x, cần kiểm tra phiên bản thực tế trước khi áp dụng công thức provider của 2.x.

### Đừng sửa lỗi bằng cách thêm ngẫu nhiên một JAR

Nếu SLF4J báo không tìm thấy provider, giải pháp không phải thêm bất kỳ dependency tên có chữ `slf4j`. Cần chọn provider đúng phiên bản và backend mong muốn, đồng thời loại bỏ provider khác gây xung đột.

## 7. Dòng chảy khi SLF4J dùng Logback

Ví dụ code:

~~~java
log.info("Payment {} succeeded", paymentId);
~~~

Trong cấu hình SLF4J + Logback, có thể hình dung:

~~~text
PaymentService
    |
    | org.slf4j.Logger.info(...)
    v
SLF4J API
    |
    v
Logback SLF4J provider
    |
    v
Logback LoggerContext
    |
    v
Effective level / filters
    |
    v
LoggingEvent
    |
    v
Appenders + Encoder / Pattern
    |
    +--> stdout / stderr
    +--> rolling file
    +--> other destinations
~~~

Các bước chính:

1. Code gọi method trên SLF4J `Logger`.
2. Provider nối lời gọi tới Logback.
3. Logback xác định level và filter tương ứng.
4. Nếu event được chấp nhận, Logback tạo/định dạng log event.
5. Appender ghi thông điệp theo cấu hình.

Backend cũng có thể xử lý logging bất đồng bộ, rolling policy hoặc structured output. Những khả năng này thuộc về backend và cấu hình, không phải bảo đảm chung của mọi lời gọi SLF4J.

## 8. Logback và Log4j 2 khác SLF4J thế nào?

Một nhầm lẫn phổ biến là coi SLF4J, Logback và Log4j 2 là ba API cạnh tranh ngang hàng.

Thực tế:

- **SLF4J** chủ yếu là một **facade API**.
- **Logback** là một backend logging tích hợp gần với SLF4J.
- **Log4j 2** là cả một hệ sinh thái logging có API riêng, core/backend riêng và adapter/provider cho SLF4J.

Bảng minh họa:

| Thành phần | Vai trò |
|---|---|
| `slf4j-api` | API mà application/library code có thể gọi |
| `logback-classic` | Logback SLF4J implementation/provider |
| `logback-core` | Hạ tầng appender/encoder và phần lõi của Logback |
| `log4j-api` | Facade/API riêng của Log4j 2 |
| `log4j-core` | Backend thực thi của Log4j 2 |
| `log4j-slf4j2-impl` | Provider đưa SLF4J 2.x API vào Log4j 2 |
| `log4j-to-slf4j` | Bridge đưa các lời gọi Log4j API vào SLF4J |

Tên artifact cụ thể quan trọng khi debug classpath. Đặc biệt, **`log4j-slf4j2-impl` và `log4j-to-slf4j` di chuyển log theo hai hướng trái ngược**. Không nên đưa cả hai vào cùng một classpath để “hỗ trợ tất cả”.

## 9. Parameterized logging

SLF4J hỗ trợ placeholder `{}` để tách template khỏi argument:

~~~java
log.info("Order {} created for customer {}", orderId, customerId);
~~~

Khác với nối chuỗi:

~~~java
log.debug(
        "Order " + orderId
                + " has " + items.size()
                + " items"
);
~~~

Parameterized logging giúp tránh việc nối chuỗi không cần thiết khi log level bị tắt và để backend thực hiện formatting theo cách phù hợp.

### Cú pháp {} không phải String.format

Ví dụ đúng:

~~~java
log.info("User {} performed action {}", userId, action);
~~~

Ví dụ không đúng nếu muốn placeholder của SLF4J:

~~~java
log.info("User %s performed action %s", userId, action);
~~~

`%s` là cú pháp thường gặp trong `String.format`, không phải placeholder mặc định của SLF4J.

### Không truyền một mảng làm message template theo cách tùy tiện

Khi log list hoặc array, hãy dùng API phù hợp và tránh tạo chuỗi dump quá lớn. Cùng một lời gọi logger có thể sinh lượng dữ liệu rất lớn nếu argument là object có `toString()` nặng hoặc chứa graph dữ liệu rộng.

### Parameterized không ngăn mọi chi phí

Ví dụ:

~~~java
log.debug("Product snapshot: {}", buildExpensiveSnapshot());
~~~

Hàm `buildExpensiveSnapshot()` vẫn được gọi khi Java đánh giá argument, **trước khi Logger quyết định có log hay không**.

Cách an toàn:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Product snapshot: {}",
            buildExpensiveSnapshot()
    );
}
~~~

Với SLF4J 2.x, fluent API còn hỗ trợ cách cung cấp argument qua `Supplier` để trì hoãn tính toán.

## 10. SLF4J logging levels

Các mức phổ biến của SLF4J:

| Level | Khi nào dùng? | Ví dụ |
|---|---|---|
| `ERROR` | Thao tác thất bại, cần xử lý/điều tra | Không lưu được đơn hàng |
| `WARN` | Hành vi bất thường nhưng chưa thất bại hoàn toàn | Retry gần đạt giới hạn |
| `INFO` | Mốc vận hành/đời sống quan trọng | Job bắt đầu và hoàn tất |
| `DEBUG` | Chi tiết hỗ trợ lập trình và điều tra | Lựa chọn nhánh xử lý |
| `TRACE` | Chi tiết rất sâu, thường nhiều sự kiện | Theo dõi từng bước nhỏ |

Quy tắc level phổ biến khi cấu hình ngưỡng `INFO` là:

~~~text
ERROR -> Được ghi
WARN  -> Được ghi
INFO  -> Được ghi
DEBUG -> Bị loại
TRACE -> Bị loại
~~~

Không có level `FATAL` chung trong API SLF4J. Một số backend có hệ thống level riêng, nhưng application code qua SLF4J thường dùng năm cấp độ trên.

### Chọn mức log dựa trên ý nghĩa vận hành

Ví dụ:

~~~java
log.info(
        "Payment reconciliation started: batchId={}",
        batchId
);
~~~

Một sự kiện bắt đầu job có thể đáng ghi ở `INFO`.

~~~java
log.debug(
        "Using payment strategy {} for batch {}",
        strategyName,
        batchId
);
~~~

Chi tiết implementation phù hợp hơn với `DEBUG`.

~~~java
log.warn(
        "Payment gateway timed out; retry {} of {}",
        attempt,
        maxAttempts
);
~~~

Nếu lỗi cuối cùng dẫn tới thất bại nghiệp vụ:

~~~java
log.error(
        "Payment reconciliation failed: batchId={}",
        batchId,
        exception
);
~~~

Đừng log cùng một exception ở `ERROR` tại mọi tầng rồi ném lại; nó có thể tạo nhiều bản sao stack trace cho một sự cố. Thường nên log tại ranh giới có đủ ngữ cảnh và chịu trách nhiệm xử lý lỗi.

## 11. Ghi exception đúng cách

Logger có overload cho `Throwable`:

~~~java
try {
    paymentClient.capture(paymentId);
} catch (PaymentException ex) {
    log.error(
            "Failed to capture payment {}",
            paymentId,
            ex
    );
    throw ex;
}
~~~

Lời gọi có `ex` cuối giúp backend ghi stack trace theo cấu hình; khác với:

~~~java
log.error("Capture failed: {}", ex.getMessage());
~~~

Cách thứ hai chỉ ghi message, có thể mất stack trace khi cần điều tra.

### Không phải lúc nào cũng cần stack trace

Một input không hợp lệ do người dùng tạo ra thường không cần `ERROR` kèm full stack trace. Có thể ghi cảnh báo có chọn lọc hoặc dựa vào metrics và HTTP error response.

Ngược lại, lỗi bất ngờ từ hệ thống phụ trợ có thể cần stack trace để xác định vị trí phát sinh.

### Lưu ý khi log rồi ném lại

Nếu controller advice, scheduler hoặc message listener ở tầng ngoài đã ghi lỗi, service ở tầng trong không nhất thiết phải ghi thêm một log `ERROR` trùng lặp. Có thể thêm context vào exception hoặc log ở `DEBUG` tùy nhu cầu, rồi để ranh giới cao hơn ghi một lần.

## 12. Cấu hình logging bằng application.yml

Spring Boot hỗ trợ nhiều property logging chung.

Ví dụ:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store: DEBUG
    org.springframework.web: WARN
~~~

Ý nghĩa:

- Root logger có ngưỡng `INFO`.
- Logger thuộc package `com.example.store` có ngưỡng `DEBUG`.
- Logger thuộc `org.springframework.web` có ngưỡng `WARN`.

Với `application.properties`:

~~~properties
logging.level.root=INFO
logging.level.com.example.store=DEBUG
logging.level.org.springframework.web=WARN
~~~

Spring Boot xử lý các property này để cấu hình logging system được hỗ trợ.

### Logger name thường theo package/class

Khi viết:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

tên logger thường là fully-qualified class name, ví dụ:

~~~text
com.example.store.order.OrderService
~~~

Cấu hình `logging.level.com.example.store=DEBUG` có thể áp dụng cho logger này theo cơ chế phân cấp tên logger.

### Chọn phạm vi DEBUG hẹp

Đặt `logging.level.root=DEBUG` trong production có thể tạo lượng log lớn từ mọi thư viện. Thường nên bật theo package cần điều tra:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store.payment: DEBUG
~~~

Cần thêm giới hạn thời gian và giám sát dung lượng log khi bật `DEBUG` hoặc `TRACE` trong production.

## 13. Cấu hình file và format qua Spring Boot

Một số property thông thường:

~~~properties
logging.file.name=logs/store-service.log
logging.level.root=INFO
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss} %-5level [%thread] %logger{36} - %msg%n
~~~

Property `logging.file.name` có thể yêu cầu backend được Spring Boot hỗ trợ ghi file theo cấu hình của Boot. Pattern console cho phép chỉnh định dạng trong những phiên bản/backends hỗ trợ pattern property đó.

Tuy nhiên, **không phải mọi backend và mọi phiên bản Spring Boot đều có cùng tập property hoặc hỗ trợ cùng cú pháp pattern**. Nếu cấu hình cần rolling policy phức tạp, nhiều appenders hoặc filter chuyên biệt, file cấu hình native của backend thường phù hợp hơn.

### File logging và vận hành container

Trong container, thực hành phổ biến là ghi stdout/stderr rồi để hạ tầng thu thập log. Ghi file trong filesystem tạm của container có thể làm log biến mất khi container được thay thế, trừ khi có volume hoặc collector phù hợp.

Điều này không có nghĩa file appender luôn sai. Với môi trường cần tuân thủ, retention hoặc audit đặc biệt, file logging có thể là lựa chọn hợp lý nếu được vận hành có kiểm soát.

### Chú ý encoding, rotation và dung lượng

Khi ghi file, phải quan tâm:

- UTF-8 cho tiếng Việt và ký tự quốc tế.
- Rolling policy theo kích thước/thời gian.
- Giới hạn retention và tổng dung lượng.
- Quyền ghi file của process.
- Dọn dẹp khi ổ đĩa đầy.
- Backpressure khi log tăng đột biến.

Những cấu hình này phụ thuộc backend thực tế và môi trường triển khai, không được giải quyết chỉ bằng lời gọi `log.info(...)`.

## 14. Cấu hình Logback chuyên biệt

Khi dùng Logback, Spring Boot hỗ trợ cấu hình backend qua file như:

~~~text
src/main/resources/logback-spring.xml
~~~

Ví dụ đơn giản:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.store" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

File này minh họa một console appender cùng với package logger override. Khi cung cấp cấu hình native thay cho mặc định, **ứng dụng phải chủ động khai báo những appender và root logger cần thiết**; không nên giả định mọi chi tiết mặc định của Boot vẫn được tự thêm vào một file custom.

### logback.xml và logback-spring.xml

`logback.xml` có thể được Logback tải rất sớm theo cơ chế riêng. `logback-spring.xml` là tên được Spring Boot hỗ trợ để đưa các Spring-specific extensions vào cấu hình Logback ở thời điểm Boot quản lý thích hợp.

Ví dụ dùng profile:

~~~xml
<configuration>
    <springProfile name="dev">
        <logger name="com.example.store" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="com.example.store" level="INFO"/>
    </springProfile>

    <include resource="org/springframework/boot/logging/logback/base.xml"/>
</configuration>
~~~

Đây là hình minh họa về extension `<springProfile>`. Các resource include cung cấp sẵn của Spring Boot có thể khác nhau giữa phiên bản; cần chọn resource được tài liệu của phiên bản đang dùng hỗ trợ, không sao chép mù một đường dẫn từ bản cũ.

Điểm cần nhớ là **extension của Spring Boot không nên đặt tùy tiện trong một file được backend tự nạp quá sớm**, vì lúc đó Spring Environment có thể chưa sẵn sàng.

### Không hard-code secret vào log config

Appender gửi log ra ngoài có thể yêu cầu credential. Không ghi token thẳng trong file XML được commit. Dùng nguồn cấu hình bảo mật và cơ chế tích hợp backend phù hợp.

## 15. Cấu hình mức log bằng profile

Cấu hình chung:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store: INFO
~~~

Trong `application-dev.yml`:

~~~yaml
logging:
  level:
    com.example.store: DEBUG
~~~

Trong `application-prod.yml`:

~~~yaml
logging:
  level:
    com.example.store: INFO
    org.springframework: WARN
~~~

Khi active profile phù hợp, Config Data có thể đưa những property logging tương ứng vào Environment. Spring Boot cấu hình logging dựa trên giá trị có hiệu lực trong giai đoạn bootstrap.

Nếu chạy với:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

thì giá trị logging của profile `prod` có thể được áp dụng, trừ khi nguồn cấu hình có precedence cao hơn ghi đè.

### Vì sao @PropertySource có thể quá muộn?

Một `@PropertySource` trên `@Configuration` được xử lý trong quá trình refresh ApplicationContext, trong khi Spring Boot đã cần khởi tạo logging từ sớm. Vì vậy, không nên dựa vào `@PropertySource` để cấu hình các thuộc tính logging cần ở bước bootstrap.

Đặt chúng trong `application.yml`, profile-specific Config Data, biến môi trường hoặc command-line arguments là lựa chọn thông thường.

## 16. Đổi backend Spring Boot từ Logback sang Log4j 2

Một lý do có thể đổi backend là yêu cầu cụ thể về appender, asynchronous logging, format hoặc chính sách vận hành đã chuẩn hóa trên Log4j 2.

Điều quan trọng là **không giữ cùng lúc hai SLF4J providers chính**. Chuyển backend cần thay runtime classpath, không phải chỉ thêm một dependency.

### Maven với spring-boot-starter-web

Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-logging</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-log4j2</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ giả định dự án đang dùng dependency management của Spring Boot nên không khai báo version trên starter.

Nếu dự án còn nhiều starter khác cũng kéo `spring-boot-starter-logging` vào classpath, cần loại trừ logging starter từ các đường dependency đó hoặc cấu hình exclusions phù hợp. Chỉ loại trừ từ một starter chưa chắc đủ.

### Gradle Kotlin DSL

Ví dụ một cách chuyển backend:

~~~kotlin
configurations.configureEach {
    exclude(
        group = "org.springframework.boot",
        module = "spring-boot-starter-logging"
    )
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-log4j2")
}
~~~

Cách exclude trên được áp dụng rộng cho configurations trong ví dụ; trong dự án thực tế, cần xem dependency graph để quyết định scope exclusion phù hợp.

### Sau khi chuyển backend

Application code vẫn có thể viết:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

Chính runtime provider chuyển lời gọi SLF4J tới Log4j 2.

Nên kiểm tra classpath có:

- SLF4J API phiên bản tương thích.
- Provider `log4j-slf4j2-impl` cho SLF4J 2.x nếu tương ứng với thế hệ Spring Boot.
- Backend `log4j-core`.
- Không còn provider Logback gây cạnh tranh.
- Không có bridge ngược gây vòng lặp.

### Cấu hình Log4j 2

Một tên file thường dùng trong Spring Boot là:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Ví dụ tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{HH:mm:ss.SSS} %-5p %c{1} - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.store"
                level="debug"
                additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đây là cấu hình minh họa cú pháp Log4j 2. Khi dùng backend cụ thể, cần tham khảo schema và version của backend đó.

## 17. Java Util Logging (JUL)

JDK cung cấp logging qua package:

~~~java
java.util.logging
~~~

Ví dụ:

~~~java
import java.util.logging.Logger;

public class LegacyImporter {

    private static final Logger log =
            Logger.getLogger(LegacyImporter.class.getName());

    public void importData() {
        log.info("Starting import");
    }
}
~~~

JUL có hệ thống logger, handler, formatter và level riêng. Nó không sử dụng SLF4J API một cách tự nhiên chỉ vì dự án có `slf4j-api` trên classpath.

Nếu ứng dụng muốn thống nhất log JUL vào backend sử dụng SLF4J, có thể dùng **bridge JUL-to-SLF4J** như `jul-to-slf4j` kèm cấu hình handler phù hợp.

### Có bridge không nghĩa mọi JUL log tự chuyển

Với JUL, việc bridge yêu cầu cài đặt handler/định tuyến tương ứng. Chỉ có một JAR mà handler chưa được áp dụng có thể chưa đủ cho mọi đường log.

Spring Boot starter logging thông thường đưa vào những bridge/hạ tầng liên quan, nhưng nếu dự án tự quản lý dependency hoặc khởi động logging theo cách đặc biệt, cần kiểm tra cấu hình runtime.

### Không cấu hình vòng lặp

Nếu vừa chuyển JUL → SLF4J, vừa đặt SLF4J → JUL làm provider, một event có thể đi vòng ngược lại và tiếp tục lặp. Không sử dụng đồng thời những bridge có hướng trái nhau trên cùng đường đi.

## 18. Commons Logging, Spring JCL và SLF4J

Một số thư viện Java truyền thống dùng **Apache Commons Logging API**, thường gọi là JCL. Spring Framework cung cấp `spring-jcl` để hỗ trợ logging facade tương thích với cách Spring sử dụng.

Ví dụ code theo Commons Logging style:

~~~java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

public class LegacyService {

    private final Log log =
            LogFactory.getLog(LegacyService.class);

    public void execute() {
        log.info("Executing task");
    }
}
~~~

Trong ứng dụng Spring Boot, bản thân Spring Framework có đường logging qua Spring JCL. Spring JCL có thể thích ứng với những API/backend logging có sẵn.

### Vì sao cần phân biệt spring-jcl và jcl-over-slf4j?

`spring-jcl` là facade/adapter do Spring cung cấp. `jcl-over-slf4j` là một bridge khác do hệ sinh thái SLF4J cung cấp để thay thế đường Commons Logging bằng SLF4J.

Các artifact này có thể cung cấp những class có cùng tên package `org.apache.commons.logging`. Nếu vô tình cùng tồn tại hoặc bị kéo bởi thư viện cũ, có thể xuất hiện warning, xung đột thứ tự classpath hoặc hành vi logging khó dự đoán.

Trong ứng dụng Spring Boot, nên ưu tiên mô hình dependency do Spring Boot quản lý, kiểm tra trước khi tự thêm Commons Logging bridge.

### Spring JCL khác SLF4J API

Spring có thể sử dụng Commons Logging-style API thông qua `spring-jcl`, trong khi application code chủ động dùng SLF4J API. Hai việc này không mâu thuẫn. Chúng có thể cùng dẫn tới một backend, nhưng không phải cùng một interface Java.

## 19. Bridge logging để thống nhất nhiều API

Một ứng dụng thực tế có thể sử dụng thư viện A gọi SLF4J, thư viện B gọi JUL và thư viện C gọi Log4j API. Nếu muốn log ra cùng một hệ thống, cần một thiết kế định tuyến có hướng rõ ràng.

Ví dụ đích là Logback:

~~~text
Ứng dụng gọi SLF4J -----------+
                              |
Thư viện gọi Log4j API -------+--[bridge Log4j API -> SLF4J]--+
                              |                               |
Thư viện gọi JUL -------------+--[bridge JUL -> SLF4J]--------+--> SLF4J
                                                              |
                                                              v
                                                        Logback provider
                                                              |
                                                              v
                                                            Output
~~~

Ngược lại, nếu backend là Log4j 2:

~~~text
Ứng dụng gọi SLF4J
        |
        v
SLF4J provider -> Log4j 2
        |
        v
Log4j 2 Core -> appenders
~~~

Các lời gọi Log4j API có thể đi trực tiếp tới Log4j 2; không cần bridge từ Log4j API về SLF4J rồi lại tới Log4j 2.

### Bridge là hướng chuyển sự kiện, không phải chỉ một dependency

Hãy đọc tên artifact như một mũi tên:

| Artifact | Hướng khái quát |
|---|---|
| `log4j-to-slf4j` | Log4j API → SLF4J |
| `log4j-slf4j2-impl` | SLF4J 2.x API → Log4j 2 |
| `jul-to-slf4j` | JUL → SLF4J |
| `slf4j-jdk14` | SLF4J → JUL |
| `jcl-over-slf4j` | Commons Logging API → SLF4J |

Điều cần tránh là cấu hình hai chiều cùng lúc:

~~~text
SLF4J --> Log4j 2 --> SLF4J --> Log4j 2 ...
~~~

hoặc:

~~~text
SLF4J --> JUL --> SLF4J --> JUL ...
~~~

Một số implementation có cơ chế phát hiện cấu hình nguy hiểm và báo lỗi thay vì lặp mãi, nhưng không nên dựa vào đó. Hãy chủ động thiết kế **một hướng chính về một backend cuối cùng**.

## 20. Vì sao multiple SLF4J providers gây rắc rối?

Giả sử runtime classpath có:

~~~text
slf4j-api-2.x.jar
logback-classic-1.x.jar
log4j-slf4j2-impl-2.x.jar
~~~

Hai backend có thể đồng thời cung cấp SLF4J provider. SLF4J 2.x thường phát warning về nhiều provider và chọn một provider thực tế, nhưng kết quả dựa vào cách service provider được phát hiện; không nên dựa vào thứ tự classpath ngẫu nhiên để quyết định backend.

Những triệu chứng:

- Log có format không như kỳ vọng.
- File `logback-spring.xml` không tác dụng vì Logback không phải backend được chọn.
- File `log4j2-spring.xml` không tác dụng vì Log4j 2 không được chọn.
- Startup warning liên quan SLF4J.
- Hành vi khác nhau giữa IDE, test runtime và executable JAR.

### Cách giải quyết đúng

1. Quyết định **một backend** cho ứng dụng.
2. Xác định starter hoặc thư viện đang kéo từng provider.
3. Loại dependency thừa từ nguồn kéo vào, không chỉ tắt warning.
4. Dùng version provider tương thích với SLF4J API.
5. Đảm bảo bridge chỉ đưa event một chiều tới backend đã chọn.
6. Xác nhận cấu hình backend thực tế được tải.

Trong một ứng dụng Spring Boot dùng dependency management, cách dễ bảo trì thường là dùng starter logging mặc định hoặc starter Log4j 2 của Boot, tránh tự pin phiên bản của từng JAR logging trừ khi có lý do và đã quản lý tương thích.

## 21. Khi không có SLF4J provider

Ví dụ classpath chỉ có:

~~~text
slf4j-api-2.x.jar
~~~

Với SLF4J 2.x, nếu không tìm thấy provider, SLF4J có thể cảnh báo rồi sử dụng NOP logger mặc định. Ứng dụng vẫn có thể khởi động, nhưng log qua SLF4J **không được xuất như mong đợi**.

Đây là lỗi nguy hiểm trong production: dịch vụ có thể chạy nhưng thiếu log để điều tra.

### Phân biệt thiếu provider và level bị tắt

Nếu `DEBUG` không xuất hiện còn `INFO` vẫn xuất hiện, có thể chỉ là ngưỡng logging. Nếu không có bất kỳ event nào, cần kiểm tra:

- Provider có mặt trong runtime classpath không?
- Có warning SLF4J về provider không?
- Backend có appender phù hợp không?
- Root level hoặc filter có loại bỏ event không?
- Output đang ở stdout, stderr hay file khác?
- Logger có được định tuyến vào backend khác không?

### Old binding bị bỏ qua bởi SLF4J 2.x

Một JAR chỉ cung cấp cơ chế `StaticLoggerBinder` cho SLF4J 1.7 không phải provider đúng cho API 2.x. SLF4J 2.x có thể báo rằng binding kiểu cũ bị bỏ qua. Giải pháp là dùng provider tương thích, không phải bổ sung thêm binding cũ.

## 22. Kiểm tra dependency tree

Xung đột logging thường là **bài toán dependency graph**, không phải một lỗi ở dòng `log.info`.

Với Maven, có thể xem cây dependency:

~~~bash
mvn dependency:tree
~~~

Có thể lọc theo artifact liên quan:

~~~bash
mvn dependency:tree -Dincludes=org.slf4j:slf4j-api
mvn dependency:tree -Dincludes=ch.qos.logback:logback-classic
mvn dependency:tree -Dincludes=org.apache.logging.log4j:log4j-slf4j2-impl
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm đường kéo vào một artifact:

~~~bash
./gradlew dependencyInsight \
  --dependency logback-classic \
  --configuration runtimeClasspath
~~~

Tương tự:

~~~bash
./gradlew dependencyInsight \
  --dependency slf4j-api \
  --configuration runtimeClasspath
~~~

Đây là những lệnh gợi ý để sử dụng khi chẩn đoán trong một dự án thật, không phải các bước cần thực thi khi viết tài liệu này.

### Runtime classpath quan trọng hơn compile classpath

Một module có thể compile thành công vì `slf4j-api` tồn tại, nhưng runtime lại không có provider hoặc có hai providers. Vì vậy, khi log hoạt động sai, cần xem **runtimeClasspath** hoặc dependency của executable artifact thật.

### Dependency management của Spring Boot

Nếu dùng parent/BOM của Spring Boot, framework quản lý phiên bản nhiều thư viện logging đồng bộ. Việc tự đặt version SLF4J, Logback hoặc Log4j 2 không phù hợp có thể tạo lỗi tương thích hoặc hành vi không dự đoán.

Chỉ override version khi thực sự cần và hiểu ảnh hưởng đến các thành phần còn lại.

## 23. Logging facade giúp thư viện độc lập backend

Một thư viện nội bộ:

~~~java
public class DiscountCalculator {

    private static final Logger log =
            LoggerFactory.getLogger(DiscountCalculator.class);

    public BigDecimal apply(
            BigDecimal original,
            BigDecimal discount
    ) {
        log.debug(
                "Applying discount {} to amount {}",
                discount,
                original
        );

        return original.subtract(discount);
    }
}
~~~

Thư viện này có thể được dùng bởi:

- Ứng dụng Spring Boot dùng Logback.
- Ứng dụng dùng Log4j 2.
- Một CLI tool dùng provider đơn giản phù hợp.
- Một ứng dụng test có logging backend riêng.

Khi build thư viện, nó thường chỉ cần compile/runtime dependency tới `slf4j-api` theo thiết kế đóng gói. Ứng dụng tiêu thụ thư viện chịu trách nhiệm chọn provider.

### Tại sao không nên include Logback trong library?

Nếu một library tự kéo Logback như dependency bắt buộc, ứng dụng muốn dùng Log4j 2 có thể nhận nhiều provider. Điều đó làm giảm khả năng tái sử dụng library và tăng gánh nặng exclusion.

Nếu library cung cấp starter cho Spring Boot, nên cân nhắc rất kỹ những dependency backend được kéo vào, tôn trọng lựa chọn của ứng dụng chủ.

## 24. SLF4J 2.x fluent API

Bên cạnh các method quen thuộc `debug/info/warn/error`, SLF4J 2.x hỗ trợ fluent logging:

~~~java
log.atInfo()
        .addKeyValue("orderId", orderId)
        .addKeyValue("customerId", customerId)
        .log("Order created");
~~~

Fluent API có thể bổ sung metadata key-value, markers, exception và arguments theo cách có cấu trúc. Nhưng backend phải hỗ trợ/định dạng phù hợp để key-value hiển thị như mong đợi.

### Deferred argument với Supplier

Ví dụ:

~~~java
log.atDebug()
        .addArgument(() -> buildExpensiveSnapshot())
        .log("Current snapshot: {}");
~~~

Với kiểu API này, argument supplier có thể chỉ được tính khi event thực sự được xử lý theo contract SLF4J 2.x. Đây là cách tránh chi phí tạo snapshot khi `DEBUG` bị tắt.

Cách cũ vẫn hợp lệ:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Current snapshot: {}", buildExpensiveSnapshot());
}
~~~

Không bắt buộc chuyển toàn bộ logging code sang fluent API. Dùng cú pháp mà đội phát triển có thể đọc và vận hành nhất quán.

### Key-value không tự động biến mọi output thành JSON

Ví dụ:

~~~java
log.atInfo()
        .addKeyValue("event", "order-created")
        .addKeyValue("orderId", orderId)
        .log("Order created");
~~~

SLF4J cung cấp thông tin cho backend. Việc output là JSON có các field tách biệt hay chỉ là text phụ thuộc backend, encoder và cấu hình structured logging. Không nên hứa rằng dùng `addKeyValue(...)` sẽ tự tạo một schema JSON chuẩn cho mọi hệ thống.

## 25. MDC: gắn ngữ cảnh cho log

**Mapped Diagnostic Context (MDC)** là cơ chế mang một tập thông tin key-value thường gắn với ngữ cảnh thực thi, ví dụ:

- `traceId` hoặc `correlationId`.
- `requestId`.
- `jobId`.
- `tenantId` nếu phù hợp với chính sách dữ liệu.
- `batchId`.

Ví dụ:

~~~java
import org.slf4j.MDC;

String previous = MDC.get("correlationId");
MDC.put("correlationId", correlationId);

try {
    orderService.process(orderId);
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
~~~

Khôi phục giá trị trước trong `finally` giúp tránh làm bẩn MDC của thread được tái sử dụng. Với request-thread pool, quên cleanup có thể khiến request sau mang nhầm correlation ID của request trước.

### Logback pattern có thể tham chiếu MDC

Ví dụ pattern:

~~~text
%d{HH:mm:ss.SSS} %-5level [%X{correlationId}] %logger - %msg%n
~~~

`%X{correlationId}` là cú pháp pattern thông dụng của Logback cho một MDC value. Với backend khác, cú pháp layout có thể khác.

### MDC và async không tự được truyền qua thread mới

Nhiều MDC implementation gắn ngữ cảnh với thread. Khi chuyển việc sang `@Async`, executor hoặc thread mới, thông tin MDC không nhất thiết được mang theo.

Nếu cần correlation ID ở task async, có thể:

- Truyền giá trị qua tham số/event payload.
- Sử dụng TaskDecorator hoặc context propagation được framework hỗ trợ.
- Khôi phục/cleanup MDC đúng khi task kết thúc.
- Tích hợp với tracing/observation infrastructure phù hợp.

Không dùng việc MDC tình cờ xuất hiện trên một thread làm hợp đồng nghiệp vụ.

## 26. Structured logging

Log text có ích khi đọc trực tiếp, nhưng hệ thống thu thập log thường muốn field có cấu trúc:

~~~json
{
  "timestamp": "2026-11-13T09:00:00Z",
  "level": "INFO",
  "logger": "com.example.store.OrderService",
  "message": "Order created",
  "orderId": "O-1024",
  "correlationId": "req-7f9a"
}
~~~

Đây là ví dụ hình dạng dữ liệu, không phải cấu trúc JSON bắt buộc của Spring Boot, SLF4J hoặc bất kỳ backend nào.

Structured logging có lợi:

- Lọc log theo field mà không cần parse text thủ công.
- Tìm các event cùng correlation ID.
- Tạo dashboard theo event name và level.
- Chuẩn hóa output từ nhiều service.

Spring Boot ở các phiên bản gần đây có hỗ trợ những lựa chọn cấu hình structured logging; phạm vi và property chính xác phụ thuộc phiên bản. Ngoài ra, Logback/Log4j 2 có encoder/layout hoặc thư viện bổ sung cho structured output.

### Giữ message và field có ý nghĩa

Nếu có cấu trúc, nên đặt giá trị như `orderId` vào field riêng; message vẫn mô tả sự kiện ngắn gọn:

~~~text
message = "Order created"
orderId = "O-1024"
customerId = "C-83"
~~~

Không cần nhét toàn bộ object hoặc một chuỗi JSON thô vào `message` nếu backend có khả năng xuất field cấu trúc.

### Không coi structured log là kho dữ liệu nghiệp vụ

Structured logs có thể bị sampling, retention ngắn hoặc mất khi collector gặp sự cố. Với dữ liệu bắt buộc lưu, dùng database/event store/audit store phù hợp.

## 27. Logging sớm trong startup

Spring Boot cần logging trước khi ApplicationContext hoàn toàn sẵn sàng để báo lỗi cấu hình, dependency hoặc quá trình khởi động.

Luồng khái quát:

~~~text
JVM khởi chạy main
       |
       v
SpringApplication bắt đầu
       |
       +--> Chuẩn bị logging system
       |
       +--> Chuẩn bị Environment/Config Data
       |
       +--> Áp dụng logging properties cần thiết
       |
       v
Tạo ApplicationContext
       |
       v
Tạo beans và chạy ứng dụng
~~~

Cách Spring Boot sử dụng logging listeners và Environment có thể khác giữa các phiên bản, nhưng điểm cốt lõi là cấu hình logging thuộc nhóm **bootstrap configuration**.

### Tại sao không chờ @Configuration bean mới cấu hình logger?

Một lỗi BeanCreationException có thể xảy ra trước khi bean cấu hình logging tùy chỉnh được tạo. Nếu logging chỉ khởi tạo lúc đó, lỗi bootstrap sẽ khó quan sát.

Vì vậy, property logging quan trọng nên ở nguồn cấu hình được Boot đọc sớm, như Config Data hoặc system/environment properties. Không nên đặt toàn bộ logging setup bên trong một `@Bean` được tạo muộn mà mong nó kiểm soát mọi log startup.

### System property và environment variable

Ví dụ:

~~~bash
java -jar store.jar --logging.level.com.example.store=DEBUG
~~~

Hoặc:

~~~bash
java -Dlogging.level.root=DEBUG -jar store.jar
~~~

Mức log thực tế phụ thuộc property source precedence và cách Spring Boot điều phối logging. Khi cần debug startup, dòng lệnh là một cách hữu ích để bật level mà không sửa file được đóng gói.

## 28. Điều chỉnh log level lúc chạy bằng Actuator

Nếu có Spring Boot Actuator và được cấu hình để expose endpoint phù hợp, endpoint **loggers** có thể cung cấp khả năng xem hoặc thay đổi logging level tại runtime.

Khái niệm:

~~~text
GET  /actuator/loggers
GET  /actuator/loggers/com.example.store
POST /actuator/loggers/com.example.store
~~~

Ví dụ request body cho một logger:

~~~json
{
  "configuredLevel": "DEBUG"
}
~~~

Khả năng và endpoint chính xác phụ thuộc phiên bản Spring Boot/Actuator và cấu hình security/exposure. Endpoint quản trị có thể điều chỉnh hành vi log của dịch vụ đang chạy, vì vậy **không công khai endpoint này không kiểm soát**.

### Thay level tại runtime không phải thay cấu hình bền vững

Nếu administrator đổi log level qua endpoint, thay đổi đó có thể mất khi ứng dụng restart hoặc được triển khai lại. Khi muốn thay đổi bền vững, cập nhật config source được quản lý.

### Kế hoạch bật DEBUG nên có điểm kết thúc

DEBUG/TRACE có thể tăng đáng kể log volume, CPU và chi phí lưu trữ. Nên có quy định khoảng thời gian điều tra, package cụ thể, quyền thao tác và thời điểm đưa level về mặc định.

## 29. Performance của logging

Logging có chi phí ở nhiều bước:

~~~text
Tạo argument
    |
    v
Kiểm tra level
    |
    v
Tạo log event
    |
    v
Format message / stack trace
    |
    v
Encoder / serialization
    |
    v
I/O (console, file, network)
~~~

Khi level bị tắt, nhiều bước phía sau có thể không chạy; nhưng **Java vẫn đánh giá argument trước khi gọi method**.

Ví dụ tốn chi phí:

~~~java
log.debug(
        "Repository state = {}",
        repository.loadAllForDebug()
);
~~~

Ngay cả khi DEBUG bị tắt, `repository.loadAllForDebug()` vẫn chạy vì đó là argument Java.

Cách phù hợp:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Repository state = {}",
            repository.loadAllForDebug()
    );
}
~~~

Hoặc dùng `Supplier` với fluent API của SLF4J 2.x.

### Async logging: khi nào hữu ích?

Backend có thể hỗ trợ async appender hoặc async logger. Việc tách I/O khỏi thread nghiệp vụ có thể giảm độ trễ, nhưng cần cân nhắc:

- Kích thước hàng đợi và giới hạn bộ nhớ.
- Điều gì xảy ra khi queue đầy.
- Mất log khi process crash.
- Thời gian flush khi shutdown.
- Thứ tự event và cách log timestamp được tạo.
- Việc giữ correlation context qua thread.

Async logging không tự bảo đảm không mất log. Với audit bắt buộc, nên dùng cơ chế dữ liệu bền vững thay vì coi async log là giao dịch.

### Logging quá mức cũng là lỗi vận hành

Ghi từng record xử lý vào `INFO` trong một job hàng triệu bản ghi có thể chiếm nhiều CPU, disk và ngân sách log collector. Có thể log batch summary, counters, metrics và những trường hợp lỗi thay vì mỗi item.

## 30. Log nhạy cảm và bảo mật

Một hệ thống logging có ích phải không làm lộ dữ liệu cá nhân hoặc thông tin xác thực.

**Không nên log:**

- Password, API key, bearer token, session cookie.
- Private keys, database credential hoặc connection string có mật khẩu.
- Toàn bộ request/response body chứa thông tin nhạy cảm.
- Thông tin thanh toán đầy đủ.
- Dữ liệu cá nhân không cần thiết để điều tra.
- Nội dung của exception nếu nó có thể chứa secret mà chưa được lọc.

Ví dụ nguy hiểm:

~~~java
log.info("Login request: {}", loginRequest);
~~~

Nếu `loginRequest.toString()` chứa password, thông tin này có thể xuất hiện trong log và được sao chép tới collector.

An toàn hơn:

~~~java
log.info(
        "Login attempt for accountId={}",
        accountId
);
~~~

Chỉ ghi identifier đủ phục vụ vận hành và tuân thủ chính sách dữ liệu.

### Cẩn thận với log injection

Dữ liệu do người dùng cung cấp có thể chứa ký tự xuống dòng hoặc control characters. Nếu ghi trực tiếp vào text logs, dữ liệu đó có thể tạo log entry giả hoặc làm hỏng phân tích.

Nên dùng structured logging/encoder có escaping phù hợp, giới hạn độ dài field và sanitize những dữ liệu có nguy cơ cao.

### Đừng hiển thị toàn bộ Environment

Spring Environment có thể chứa secret từ variables, config tree hoặc secret store. Việc log toàn bộ property sources để debug có thể tiết lộ credential. Khi cần chẩn đoán, ưu tiên log **tên nguồn cấu hình**, không in toàn bộ key-value.

## 31. Thư viện Log4j 1.x và Log4j 2 không giống nhau

Tên “Log4j” có thể gây nhầm giữa các thế hệ.

- **Log4j 1.x** là thế hệ cũ, đã kết thúc vòng đời hỗ trợ từ lâu và không nên được dùng cho dự án mới.
- **Log4j 2** là hệ sinh thái hiện đại với `log4j-api`, `log4j-core` và các adapter phù hợp.
- **Logback** là backend khác, không phải “Log4j 1.x được đổi tên”.

Khi thấy dependency chứa `log4j`, hãy kiểm tra **artifact và major version**, không chỉ nhìn tên.

### Cập nhật security cũng là một phần quản lý logging

Backend logging nằm trên đường xử lý rất nhiều dữ liệu, bao gồm dữ liệu có thể do người dùng kiểm soát. Nếu backend có lỗ hổng bảo mật, mức ảnh hưởng có thể rộng.

Nên để dependency management/BOM phù hợp quản lý version, theo dõi advisory và cập nhật theo quy trình bảo mật của tổ chức. Không giữ thư viện logging lỗi thời chỉ vì “log vẫn chạy”.

## 32. Test logging trong Spring Boot

Có nhiều mức kiểm thử logging.

### Kiểm thử nghiệp vụ không nên quá phụ thuộc text log

Ví dụ một service đặt đơn hàng cần lưu dữ liệu đúng thì unit test nên kiểm tra database interaction hoặc output nghiệp vụ, không chỉ assert đã có dòng `"Order created"`.

Log message có thể thay đổi theo nhu cầu vận hành. Nếu coi text log là hợp đồng nghiệp vụ, mỗi lần chỉnh wording có thể làm test không cần thiết thất bại.

### Kiểm tra log output bằng OutputCaptureExtension

Spring Boot Test có tiện ích để capture output trong test. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class LoggingExampleTest {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingExampleTest.class);

    @Test
    void writesInfoLog(CapturedOutput output) {
        log.info("Inventory refresh completed");

        assertThat(output)
                .contains("Inventory refresh completed");
    }
}
~~~

Để dùng test này, dự án cần dependency `spring-boot-starter-test` và các import `Logger`/`LoggerFactory`. Kết quả capture còn phụ thuộc cấu hình logging trong test runtime; nếu level bị tắt hoặc output đi đến destination khác, assertion có thể không match.

### Kiểm thử appender cụ thể

Khi cần kiểm tra field, level hoặc sự kiện chính xác, có thể gắn test appender vào backend trong phạm vi test. Ví dụ Logback có `ListAppender`, nhưng test như vậy phụ thuộc vào Logback API và cần cleanup appender sau test để không ảnh hưởng test khác.

Nếu mục tiêu chỉ là kiểm tra business logic, tránh viết test phụ thuộc vào backend không cần thiết.

### Kiểm thử cấu hình khi chuyển backend

Với thay đổi từ Logback sang Log4j 2, có thể có một smoke test hoặc integration test khởi động ứng dụng và xác nhận:

- SLF4J có provider.
- Provider/backend đúng như thiết kế.
- Không có warning multiple providers.
- Console/file appender hoạt động.
- Những MDC/structured fields cần thiết có mặt.

Đây là loại kiểm thử hạ tầng phù hợp khi hệ thống yêu cầu chuẩn log nhất quán.

## 33. Xác định backend thật tại runtime

Khi sự cố xảy ra, việc nhìn file cấu hình chưa đủ. Cần biết provider được chọn **thực tế**.

Trong một công cụ chẩn đoán cục bộ hoặc test, có thể in class logger factory:

~~~java
Object factory = LoggerFactory.getILoggerFactory();

System.out.println(
        "SLF4J logger factory: "
                + factory.getClass().getName()
);
~~~

Ví dụ, với Logback, factory thường là một class thuộc `ch.qos.logback.classic`. Với Log4j 2 provider, nó thuộc implementation tương ứng.

Không nên biến đoạn này thành một log startup bắt buộc trong mọi ứng dụng; nó là công cụ chẩn đoán khi cần.

### Xác nhận JAR thực tế

Khi chạy từ IDE, test hoặc packaged JAR, dependency graph có thể khác nhau. Một provider có thể nằm trong test scope nhưng không có trong production artifact; ngược lại, một starter khác có thể đưa thêm backend vào runtime.

Nếu cần xác định nguyên nhân, kiểm tra đúng runtime classpath thay vì chỉ file POM/build.gradle.

## 34. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SLF4J báo không có provider | Chỉ có `slf4j-api` hoặc provider sai version | Thêm đúng provider/backend tương thích |
| SLF4J báo nhiều providers | Logback và Log4j 2 cùng có provider | Chọn một backend và loại dependency thừa |
| Log4j 2 backend không hoạt động | Vẫn còn Logback provider hoặc bridge ngược | Kiểm tra starter logging và runtimeClasspath |
| Log bị lặp hoặc vòng lặp | Hai bridge định tuyến ngược chiều | Chỉ giữ một hướng về backend chính |
| `logback-spring.xml` không có tác dụng | Backend được chọn không phải Logback, file không được tải hoặc sai cấu hình | Xác nhận provider và log config |
| `DEBUG` không xuất hiện | Logger level, filter hoặc package name sai | Kiểm tra effective level và logger name |
| Log vẫn xuất hiện dù set level ở YAML | Nguồn config có precedence cao hơn, file native backend override | Kiểm tra property sources/config |
| Không thấy log từ JUL | Chưa có bridge handler hoặc output riêng | Kiểm tra JUL-to-SLF4J integration |
| Thiếu log sau khi app thoát | Async queue chưa flush hoặc collector gặp sự cố | Thiết kế shutdown/flush/collector phù hợp |
| Log bị tràn ổ đĩa | Không có rolling/retention hoặc INFO quá nhiều | Cấu hình size/time limits và sampling |
| Log không có correlation ID | MDC chưa được đặt, chưa đưa vào pattern hoặc mất qua async | Kiểm tra MDC/TaskDecorator |
| Thời gian response tăng | Logging I/O hoặc tính argument quá đắt | Giảm volume, parameterize, lazy evaluation |
| Secret xuất hiện trong log | Dump toàn object/request, thiếu redaction | Chỉ log field cần thiết và lọc secret |
| Warning Commons Logging | JCL artifacts/bridges cùng cung cấp class | Xem `spring-jcl` và dependency tree |
| Code compile nhưng runtime NOP | SLF4J API có nhưng provider không có | Kiểm tra runtime artifact |
| Test log khác production | Test dependencies/provider/level khác | So sánh runtimeClasspath theo scope |

### Khi gặp sự cố, xác định lớp nào bị lỗi

Đừng sửa mọi thứ cùng lúc. Hãy hỏi:

1. Dòng log có được gọi không?
2. Logger level có bật không?
3. SLF4J provider được phát hiện chưa?
4. Backend nào thực sự được chọn?
5. Bridge đang hướng về đâu?
6. Appender/handler nào được cấu hình?
7. Output được ghi tới file, console hay collector nào?
8. Có filter, async queue hoặc retention nào làm event không xuất hiện không?

Trả lời theo thứ tự này giúp phân biệt lỗi code, dependency, cấu hình và hạ tầng thu thập log.

## 35. Kịch bản thực tế: ứng dụng có thư viện dùng nhiều API

Giả sử một Spring Boot service dùng:

- Business code gọi SLF4J.
- Một thư viện cũ gọi JUL.
- Một thư viện khác gọi Log4j 2 API.
- Spring Framework dùng Spring JCL.

Nếu chọn Logback làm backend, luồng mong muốn là:

~~~text
Business code --------> SLF4J API -----+
                                        |
JUL library -- JUL-to-SLF4J bridge ----+
                                        |
Log4j API library -- log4j-to-slf4j ----+----> Logback
                                        |
Spring JCL ------- adapter thích hợp ---+
                                              |
                                              v
                                     Console / file / collector
~~~

Việc kết nối cụ thể của Spring JCL tùy classpath và cấu hình, nhưng mục tiêu là để những nguồn logging khác nhau hội tụ về một backend cuối cùng.

Nếu sau đó tổ chức chuyển sang Log4j 2:

- Loại Logback provider.
- Thêm Spring Boot Log4j 2 starter.
- Dùng provider SLF4J → Log4j 2 phù hợp phiên bản.
- Không giữ Log4j API → SLF4J bridge ngược có nguy cơ loop.
- Xác minh JUL và Spring JCL tiếp tục được định tuyến theo cấu hình mới.
- Chuyển file cấu hình native sang backend mới hoặc dùng properties do Boot hỗ trợ.

Business code vẫn dùng:

~~~java
log.info("Order {} created", orderId);
~~~

Đây là lợi ích thực tế của facade: **mã nghiệp vụ ít phải thay đổi khi hạ tầng logging thay đổi**.

## 36. Chọn một kiến trúc logging dễ vận hành

Với một Spring Boot application thông thường, có thể áp dụng những nguyên tắc sau:

1. **Dùng SLF4J API trong business code.** Không tạo dependency trực tiếp lên appender/backend nếu không cần.
2. **Chỉ chọn một SLF4J provider chính.** Không để Logback và Log4j 2 cùng tranh quyền.
3. **Để Spring Boot quản lý version và starter logging** khi có thể.
4. **Dùng cấu hình property cho nhu cầu đơn giản.** Ví dụ level theo package và output căn bản.
5. **Dùng file native backend khi cần nhiều appenders/filter/rolling policy.**
6. **Hiểu SLF4J 1.7 binding khác SLF4J 2.x provider.**
7. **Cấu hình bridges một chiều.** Tránh vòng lặp giữa SLF4J, JUL và Log4j API.
8. **Sử dụng parameterized logging.** Tránh nối chuỗi và tính dữ liệu đắt khi level tắt.
9. **Dùng INFO cho mốc vận hành, DEBUG/TRACE cho chẩn đoán chi tiết.**
10. **Ghi exception với Throwable khi cần stack trace**, nhưng tránh log lặp nhiều tầng.
11. **Bảo vệ dữ liệu nhạy cảm.** Không log token, password hoặc full object chứa dữ liệu cá nhân.
12. **Gắn correlation ID hoặc trace context** theo cơ chế có cleanup/propagation rõ.
13. **Đo volume, retention và ảnh hưởng hiệu năng của logging.**
14. **Kiểm tra runtime classpath** khi provider, bridge hoặc backend có dấu hiệu bất thường.
15. **Kiểm thử cấu hình logging hạ tầng riêng**, không làm mọi test nghiệp vụ phụ thuộc text log.
16. **Không dùng log làm nguồn sự thật nghiệp vụ.** Audit bắt buộc cần dữ liệu bền vững và quyền truy cập phù hợp.

## Kết luận

**Logging facade** tách API mà application code sử dụng khỏi thư viện thực sự xử lý log. **SLF4J** cung cấp API thống nhất như `Logger` và `LoggerFactory`; **provider** nối API này đến backend; **Logback**, **Log4j 2** hoặc một implementation khác quyết định level, format và destination. Trong các ứng dụng Spring Boot dùng starter mặc định thông thường, Logback là backend phổ biến; Spring Boot cũng hỗ trợ chuyển sang Log4j 2 khi dependency được cấu hình đúng.

Điểm khó nhất không phải gọi `log.info(...)` mà là hiểu **classpath và hướng định tuyến**. SLF4J 1.7 dùng binding kiểu cũ; SLF4J 2.x dùng provider. Thêm nhiều provider hoặc kết hợp bridge hai chiều có thể gây warning, cấu hình bị bỏ qua hoặc vòng lặp logging. Vì vậy, khi log không hoạt động như mong muốn, hãy xác định API nào được gọi, provider nào thực sự được chọn, backend nào đang chạy và appender nào nhận output.

Một hệ thống logging tốt có API ổn định, cấu hình dễ vận hành, đủ ngữ cảnh để điều tra, chi phí hợp lý và không để lộ dữ liệu nhạy cảm. Khi giữ những nguyên tắc đó, ứng dụng Spring Boot có thể thay đổi hạ tầng logging mà vẫn giữ mã nghiệp vụ rõ ràng và đáng tin cậy.
