# logback-spring.xml hoặc cấu hình tương ứng của logging system

Logging là một trong những thành phần đầu tiên được khởi tạo khi một ứng dụng Spring Boot bắt đầu chạy. Trước cả khi toàn bộ ApplicationContext được tạo xong, Spring Boot đã cần ghi thông tin startup, profile, lỗi đọc cấu hình và nguyên nhân ứng dụng khởi động thất bại. Khi ứng dụng chạy, logging tiếp tục hỗ trợ chẩn đoán request, sự kiện nghiệp vụ, cảnh báo và sự cố.

Spring Boot cho phép cấu hình logging ở hai mức:

- **Cấu hình đơn giản qua properties**: dùng các key như **logging.level.root**, **logging.level.com.example**, **logging.file.name** để điều chỉnh mức log và một số hành vi phổ biến.
- **Cấu hình chi tiết bằng file riêng của logging system**: với Logback thường là **logback-spring.xml**; với Log4j2 có cấu hình XML tương ứng như **log4j2-spring.xml**. Những file này kiểm soát appender, encoder, log pattern, logger hierarchy, file rotation và các quy tắc nâng cao.

Trọng tâm bài học là **logback-spring.xml** trong Spring Boot, đồng thời giải thích cách chuyển tư duy này sang logging system khác. Ta sẽ xây dựng cấu hình có console logging, file rotation, mức log theo package, cấu hình theo Spring profile và cách quan sát/chẩn đoán khi log không như mong đợi.

## 1. Ba tầng của logging trong Spring Boot

Để cấu hình đúng, cần phân biệt:

1. **Logging API**: code ứng dụng gọi logger để phát ra sự kiện log.
2. **Logging implementation**: thư viện thực sự xử lý log, ví dụ Logback hoặc Log4j2.
3. **Logging configuration**: quy tắc chọn mức log, trình bày, chuyển đến console/file và quản lý vòng đời output.

Một sơ đồ điển hình:

~~~text
OrderService / PaymentService / Controller
                 │
                 ▼
           SLF4J Logger
                 │
                 ▼
       Logging implementation
            (Logback)
                 │
                 ▼
        logback-spring.xml
                 │
        ┌────────┴────────┐
        ▼                 ▼
    ConsoleAppender    RollingFileAppender
        │                 │
        ▼                 ▼
     stdout/stderr      log files
~~~

**SLF4J** là API/facade mà code thường dùng; **Logback** là một implementation có khả năng thực thi. Spring Boot cung cấp một lớp **LoggingSystem** để khởi tạo và điều khiển logging implementation đang có trên classpath.

Nếu dùng đúng abstraction, phần lớn code nghiệp vụ không cần thay đổi khi chuyển backend từ Logback sang Log4j2.

### 1.1. Logging trong code Java

Ví dụ một service:

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void createOrder(String orderId) {
        log.info("Creating order {}", orderId);
        log.debug("Validating order {}", orderId);
        // Logic nghiệp vụ.
    }
}
~~~

Trong đoạn code trên:

- **LoggerFactory.getLogger(OrderService.class)** tạo/lấy logger theo tên class.
- **log.info** ghi thông tin hoạt động bình thường.
- **log.debug** cung cấp chi tiết để chẩn đoán.
- Placeholder **{}** giúp định dạng tham số theo API SLF4J thay vì phải nối chuỗi thủ công.

Code trên không quy định log đi đến file nào, màu gì hay có rotation hay không. Đó là trách nhiệm của logging configuration.

### 1.2. Spring Boot thường chọn Logback theo mặc định

Trong ứng dụng dùng các Spring Boot starters thông thường, dependency **spring-boot-starter-logging** thường đưa Logback và các thành phần bridging cần thiết vào ứng dụng.

Không nên kết luận rằng **mọi** ứng dụng Spring Boot đều dùng Logback: dự án có thể loại starter logging mặc định và dùng Log4j2, hoặc thay đổi dependency graph và logging implementation.

Nếu file logback-spring.xml không có tác dụng, bước đầu tiên là xác nhận **backend logging thực tế trên runtime classpath**. Một file Logback sẽ không cấu hình được Log4j2.

## 2. Khi nào chỉ cần application.yml?

Trước khi viết XML, thử xác định nhu cầu có giải quyết được bằng Spring Boot properties không.

Ví dụ application.yml:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
~~~

Ý nghĩa:

- Logger gốc mặc định dùng INFO.
- Những logger dưới com.example.orders được cho phép ghi DEBUG nếu không có mức gần hơn ghi đè.
- Logger dưới org.springframework.web chỉ ghi từ WARN trở lên trong tình huống tương ứng.

Với logging implementation và output mặc định của Spring Boot, cấu hình này có thể đủ cho nhiều dịch vụ.

### 2.1. File output bằng property

Ví dụ:

~~~yaml
logging:
  file:
    name: logs/my-application.log
~~~

Spring Boot có thể bật file logging theo tên file đã chỉ định. Tuy nhiên, nhu cầu **nhiều file theo package, rolling policy đặc biệt, encoder riêng, nhiều appenders, cấu hình theo profile** thường cần file cấu hình chuyên dụng.

### 2.2. Logging pattern bằng property

Các thuộc tính như:

~~~properties
logging.pattern.console=%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n
logging.pattern.file=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n
~~~

có thể tùy chỉnh pattern khi đang sử dụng cấu hình logging phù hợp với cơ chế hỗ trợ của Spring Boot.

**Lưu ý:** nếu bạn thay thế hoàn toàn cấu hình Logback bằng XML do mình viết, những pattern property này không nhất thiết tự động có tác dụng. File XML phải tham chiếu đến các property được Boot cung cấp hoặc tự khai báo pattern. Đừng giả định cấu hình XML tùy ý vẫn sử dụng pattern mặc định của Boot.

### 2.3. Khi nào chuyển sang logback-spring.xml?

Nên cân nhắc logback-spring.xml khi:

- Cần **ConsoleAppender và RollingFileAppender** với cấu hình độc lập.
- Cần tách logger riêng cho một package hoặc một loại sự kiện.
- Cần rolling theo ngày, dung lượng và chính sách retention.
- Cần sử dụng **springProfile** hoặc **springProperty** để chọn cấu hình theo Spring Environment.
- Cần cấu hình AsyncAppender, encoder hoặc filter đặc thù.
- Có quy tắc log riêng cho môi trường local và production.

Ngược lại, nếu mục đích chỉ là đổi log level một package từ INFO sang DEBUG, **logging.level** thường đơn giản và dễ vận hành hơn.

## 3. File logback-spring.xml nằm ở đâu?

Với một ứng dụng Spring Boot dùng Logback, vị trí thông thường là:

~~~text
src/
└── main/
    └── resources/
        ├── application.yml
        └── logback-spring.xml
~~~

Sau khi build, file nằm trên **runtime classpath** của ứng dụng. Khi chạy executable JAR, Spring Boot có thể tìm thấy resource này qua cơ chế cấu hình logging của nó.

Tên **logback-spring.xml** có ý nghĩa: đây là tên Spring Boot đề xuất để áp dụng các phần mở rộng tích hợp Spring khi Boot khởi tạo Logback.

### 3.1. Phân biệt logback.xml và logback-spring.xml

| Tiêu chí | logback.xml | logback-spring.xml |
|---|---|---|
| Ai có thể phát hiện sớm? | Logback tự phát hiện theo cơ chế native. | Spring Boot nhận diện và tải theo cơ chế hỗ trợ. |
| Cú pháp Logback chuẩn | Có | Có |
| Extension springProfile/springProperty | Không nên dựa vào trong quá trình native loading. | Được Spring Boot hỗ trợ khi Boot quản lý loading. |
| Tương tác Spring Environment | Không có trực tiếp trong native Logback parser. | Có thể dùng extension của Boot. |
| Lựa chọn phổ biến trong Spring Boot | Chỉ khi cần native semantics có chủ đích. | Thường được ưu tiên để tích hợp đầy đủ. |

**logback.xml** có thể được Logback tải rất sớm, trước khi Spring Boot có đủ Environment để xử lý các tag riêng của Spring. Vì thế một file logback.xml chứa springProfile có thể báo lỗi parser hoặc không hoạt động như kỳ vọng.

**logback-spring.xml** cho phép Boot kiểm soát quá trình loading tốt hơn và hỗ trợ các extension của nó. Đây là lựa chọn nên dùng nếu ứng dụng cần phân biệt profile hoặc bind một property Spring vào XML.

### 3.2. Không phải mọi file tên tùy ý đều tự được nạp

Ví dụ một file:

~~~text
src/main/resources/logging/my-logback.xml
~~~

sẽ không tự động được chọn chỉ vì tồn tại trên classpath. Nếu muốn dùng một file khác tên quy ước, chỉ định location qua **logging.config**.

### 3.3. Tách file logging khỏi application.yml

application.yml thường giữ các cấu hình Spring Boot mức cao như logging.level và application properties.

logback-spring.xml mô tả cấu trúc riêng của Logback: appenders, encoders, policies và logger hierarchy.

Hai file có thể cùng tồn tại. Điều quan trọng là không cấu hình trùng lặp, mâu thuẫn mà không xác định rõ nguồn kiểm soát cuối.

## 4. File logback-spring.xml tối thiểu

Ví dụ cấu hình console logging:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

</configuration>
~~~

Cấu hình này có một appender tên CONSOLE và một root logger ở mức INFO.

Ví dụ đầu ra:

~~~text
2026-11-13 09:15:23.104 INFO  [main] c.e.orders.OrderService - Creating order ORD-17
~~~

### 4.1. Các phần của XML

| Thành phần | Vai trò |
|---|---|
| **configuration** | Root của cấu hình Logback. |
| **appender** | Định nghĩa nơi log được ghi, ví dụ console hoặc file. |
| **encoder** | Chuyển logging event thành chuỗi/byte. |
| **charset** | Charset của dữ liệu text được encoder xuất ra. |
| **pattern** | Cách biểu diễn các trường của log event. |
| **root** | Root logger kế thừa bởi logger hierarchy, trừ khi có cấu hình đặc biệt. |
| **appender-ref** | Gắn một appender đã định nghĩa vào logger. |

Một appender chỉ được khai báo mà **không được gắn vào logger/root** có thể không nhận event như mong muốn. Logback cần cả output destination và đường chuyển event đến destination.

### 4.2. Ý nghĩa một số token pattern

| Token | Ý nghĩa điển hình |
|---|---|
| **%d{...}** | Timestamp theo format chỉ định. |
| **%level** hoặc **%p** | Mức log như INFO/WARN/ERROR. |
| **%-5level** | In mức log căn trái trong vùng rộng ít nhất 5 ký tự. |
| **%thread** | Tên thread phát ra log. |
| **%logger{36}** | Tên logger rút gọn theo cấu hình độ dài. |
| **%msg** hoặc **%message** | Nội dung message sau định dạng. |
| **%n** | Ký tự xuống dòng phù hợp nền tảng. |
| **%ex** hoặc **%throwable** | Thông tin exception/stack trace. |
| **%X{requestId}** | Giá trị MDC dưới key requestId, nếu có. |

Pattern là ngôn ngữ của Logback, không phải cú pháp template của Spring. Mỗi logging system có thể có token, escape và layout syntax khác nhau.

### 4.3. Không tùy tiện bỏ stack trace

Nếu ứng dụng có:

~~~java
try {
    paymentClient.charge(orderId);
} catch (Exception ex) {
    log.error("Charge failed for order {}", orderId, ex);
}
~~~

log event có Throwable. Logback encoder có khả năng hiển thị stack trace; cách biểu diễn phụ thuộc pattern và converter cấu hình.

Trong cấu hình có yêu cầu chẩn đoán lỗi, nên xác định rõ stack trace có được giữ lại hay không. Một pattern custom chỉ giữ message và một encoder/filter tự viết có thể làm mất thông tin nguyên nhân mà vận hành cần.

## 5. Mức log và logger hierarchy

Các mức phổ biến từ chi tiết đến nghiêm trọng:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Khi ngưỡng là INFO, event INFO/WARN/ERROR thường được phép đi tiếp; TRACE/DEBUG thường bị lọc ở bước chọn mức.

Với class:

~~~java
package com.example.orders.service;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);
}
~~~

logger có tên tương ứng với class, thường là:

~~~text
com.example.orders.service.OrderService
~~~

Logger có thể kế thừa effective level từ package cha trong hierarchy:

~~~text
ROOT                 INFO
└── com
    └── example      DEBUG
        └── orders   (kế thừa DEBUG)
            └── service
                └── OrderService
~~~

### 5.1. Cấu hình logger theo package trong XML

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>
    <logger name="org.springframework.web" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Khi đó:

- com.example.orders và các logger con không có level riêng có thể ghi DEBUG.
- org.springframework.web có ngưỡng WARN.
- Các logger khác kế thừa INFO từ root nếu không có override gần hơn.

Các logger trong ví dụ không tự định nghĩa appender riêng. Event được truyền theo logger hierarchy đến appender của root.

### 5.2. Khác biệt giữa level và appender

**Level** trả lời: event này có được phép ghi không?

**Appender** trả lời: nếu event đi qua, nó được gửi đến đâu?

Một logger DEBUG vẫn có thể không xuất hiện trong file mong đợi nếu file appender không được gắn hoặc appender filter chặn nó. Ngược lại, một FileAppender hoạt động tốt cũng không thể in DEBUG của logger có effective level WARN.

Chẩn đoán cần kiểm tra **cả ngưỡng level lẫn đường đi của appenders**.

## 6. Additivity: vì sao một dòng log có thể xuất hiện hai lần?

Mặc định, Logback dùng **additivity** để truyền event từ logger con lên hierarchy cha. Điều này thường hữu ích vì logger theo package không phải gắn appender riêng.

Nhưng nó có thể tạo log trùng khi một logger vừa có appender riêng, vừa truyền lên root có cùng appender.

Ví dụ dễ gây trùng:

~~~xml
<logger name="com.example.orders" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Với một event thuộc com.example.orders, CONSOLE có thể được gọi tại logger con **và** tại root.

### 6.1. Giải pháp khi muốn appender riêng

~~~xml
<logger name="com.example.orders"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

**additivity="false"** chặn việc đẩy event lên ancestor loggers theo đường thông thường. Logger đó chỉ dùng những appenders được gắn trực tiếp theo cấu hình.

### 6.2. Cẩn thận khi tắt additivity

Nếu bạn đặt:

~~~xml
<logger name="com.example.orders"
        level="DEBUG"
        additivity="false"/>
~~~

mà không gắn appender phù hợp, event từ package này có thể biến mất vì không được đẩy về root và cũng không có output destination riêng.

Quy tắc thực hành:

- Chỉ đổi level cho package → thường không cần tắt additivity.
- Gắn appender riêng và không muốn ghi thêm ở root → cân nhắc additivity=false.
- Muốn log vừa vào console vừa vào file → có thể gắn hai appenders vào root hoặc logger đích một cách chủ động.

## 7. Dùng springProfile trong logback-spring.xml

Spring Boot bổ sung phần tử **springProfile** để các đoạn cấu hình Logback chỉ được áp dụng khi một biểu thức Spring profile phù hợp.

Ví dụ muốn:

- Local/dev: bật DEBUG để dễ tìm lỗi.
- Các profile khác: giữ INFO để giảm lượng log.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="local | dev">
        <logger name="com.example" level="DEBUG"/>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!local &amp; !dev">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

Trong XML, dấu **&** dùng trong biểu thức logic phải được escape thành **&amp;**. Đây là quy tắc cú pháp XML, không phải sự khác biệt của Spring profile expression.

Khi local hoặc dev active, logger com.example ở mức DEBUG. Trong các trường hợp còn lại, root INFO được sử dụng theo nhánh thứ hai.

### 7.1. springProfile là điều kiện, không phải lệnh bật profile

~~~xml
<springProfile name="prod">
    <!-- Nội dung chỉ được nạp nếu prod phù hợp. -->
</springProfile>
~~~

Điều này **không tự kích hoạt** prod. Spring Boot lấy trạng thái profile từ Environment đã được chuẩn bị trong startup.

Muốn bật profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Hoặc dùng environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

### 7.2. Không nhầm !prod với dev

~~~xml
<springProfile name="!prod">
    <!-- Có thể áp dụng cho local, test, staging... -->
</springProfile>
~~~

Điều kiện **!prod** phù hợp bất kỳ khi nào prod không active. Nó không có nghĩa chỉ dành cho dev.

Nếu logging DEBUG có thể làm lộ dữ liệu hoặc tạo tải lớn, hãy dùng tập profile cho phép như local/dev thay vì một điều kiện phủ định quá rộng.

### 7.3. Nhiều profile có thể cùng active

Nếu ứng dụng chạy:

~~~text
spring.profiles.active=dev,prod
~~~

thì cả điều kiện dev và prod đều có thể phù hợp. Đừng xây cấu hình Logback với hai khối được giả định “không bao giờ cùng match” nếu project chưa kiểm soát việc profile kết hợp.

Trong cấu hình phức tạp, nên đặt một root appender/level cơ bản, sau đó dùng springProfile để điều chỉnh đúng phần khác biệt. Cách này giảm rủi ro cấu hình trùng root hoặc gắn appender hai lần.

## 8. Dùng springProperty để lấy giá trị từ Spring Environment

**springProperty** là extension của Spring Boot cho phép trích một property từ Environment và gán nó thành một property có tên để sử dụng trong cấu hình Logback.

Ví dụ:

~~~yaml
spring:
  application:
    name: order-api

app:
  logging:
    directory: logs/order-api
~~~

Trong logback-spring.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="appName"
                    source="spring.application.name"
                    defaultValue="demo-service"/>

    <springProperty scope="context"
                    name="logDirectory"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [${appName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

</configuration>
~~~

Ý nghĩa:

- **source** là property key trong Spring Environment.
- **name** là tên property được tham chiếu trong Logback, ví dụ **${appName}**.
- **defaultValue** là giá trị dự phòng nếu không có Spring property.
- **scope="context"** làm property có phạm vi tương ứng với Logback context.

Ở ví dụ trên, logDirectory chưa được dùng để tạo file appender; nó minh họa cách đọc một đường dẫn từ Environment, sẽ được sử dụng trong phần rolling file.

### 8.1. Dùng canonical property name

Trong **springProperty source**, nên sử dụng property name theo kiểu canonical kebab-case. Ví dụ:

~~~xml
<springProperty name="logDir"
                source="app.logging.directory"
                defaultValue="logs"/>
~~~

Nếu property Java có dạng connectTimeout, trong cấu hình nên dùng **connect-timeout** chứ không cố dựa vào cách viết camelCase trong XML. Tên property đúng và nhất quán giúp các nguồn Environment có relaxed binding được xử lý thuận tiện hơn.

### 8.2. Không dùng @Value hoặc bean application trong XML

Logging system được khởi tạo rất sớm. Khi logback-spring.xml được xử lý, các bean @ConfigurationProperties, @Service hoặc @Value field của ứng dụng chưa chắc đã tồn tại.

Không nên thiết kế Logback config dựa vào việc phải inject một service Java đã được khởi tạo.

Nếu cần một cấu hình đơn giản, hãy đưa giá trị đó vào Environment đủ sớm và đọc bằng springProperty, hoặc dùng system property/environment variable do logging implementation hỗ trợ. Những property đến từ @PropertySource trên @Configuration được xử lý muộn có thể **không sẵn có khi logging system khởi tạo**.

### 8.3. Fallback để startup không thất bại do thiếu property

Ví dụ:

~~~xml
<springProperty name="appName"
                source="spring.application.name"
                defaultValue="unknown-application"/>
~~~

Fallback hợp lý cho tên ứng dụng giúp startup log vẫn rõ nghĩa.

Với file path hoặc appender cấu hình nhạy cảm, cần xem việc fallback có phù hợp không. Một fallback lặng lẽ sang thư mục không đúng có thể khiến người vận hành không tìm thấy log hoặc gây xung đột quyền ghi.

## 9. Kết hợp ConsoleAppender và RollingFileAppender

Một yêu cầu phổ biến là ghi log ra cả console và file.

Ví dụ đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <property name="LOG_DIR" value="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">

        <file>${LOG_DIR}/application.log</file>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{50} - %msg%n%ex</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${LOG_DIR}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>20MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>

</configuration>
~~~

Đây là cấu hình Logback mô tả:

- CONSOLE ghi sự kiện ra console.
- FILE ghi sự kiện vào **logs/application.log**.
- Khi cần, policy xoay vòng tạo file theo ngày và index.
- File lịch sử có hậu tố **.gz** để nén.
- Root logger gửi các event đủ mức tới cả hai appenders.

### 9.1. Vai trò của file và fileNamePattern

~~~xml
<file>${LOG_DIR}/application.log</file>
~~~

định nghĩa file log đang được ghi trong mẫu RollingFileAppender này.

~~~xml
<fileNamePattern>${LOG_DIR}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
~~~

định nghĩa tên file lưu trữ sau khi rollover. **%d** biểu diễn phân đoạn ngày, **%i** là index dùng khi có nhiều archive trong cùng kỳ do giới hạn kích thước.

Những token ở đây thuộc RollingPolicy, không phải pattern của một dòng log.

### 9.2. maxFileSize, maxHistory và totalSizeCap

| Thuộc tính | Mục đích |
|---|---|
| **maxFileSize** | Ngưỡng kích thước kích hoạt rollover theo size trong policy. |
| **maxHistory** | Số kỳ lịch sử được giữ lại, dựa theo chu kỳ thời gian của policy. |
| **totalSizeCap** | Giới hạn tổng dung lượng các archive theo cơ chế cleanup của Logback. |

Trong ví dụ, maxHistory=14 với chu kỳ theo ngày thường tương ứng giữ tối đa khoảng 14 kỳ archive; không có nghĩa nhất thiết đúng 14 file vì mỗi ngày có thể có nhiều file do size rollover.

Retention thực tế còn phụ thuộc policy, thời điểm cleanup, cách ứng dụng được khởi động và số lượng archive. Với hệ thống có yêu cầu lưu log phục vụ kiểm toán, nên thiết kế thêm giải pháp lưu trữ tập trung; đừng chỉ dựa vào disk local của một container.

### 9.3. Đường dẫn file tương đối phụ thuộc working directory

~~~xml
<property name="LOG_DIR" value="logs"/>
~~~

Đường dẫn tương đối thường được giải quyết theo working directory của process. Trong IDE, Docker, systemd và Kubernetes, working directory có thể khác.

Nếu ghi file là yêu cầu quan trọng, hãy dùng đường dẫn/volume được cấu hình rõ ràng, có quyền ghi và có chính sách xoay vòng/dọn dẹp.

### 9.4. Vì sao cần giới hạn dung lượng?

Nếu chỉ dùng FileAppender không rollover, một dịch vụ chạy dài ngày có thể:

- Ghi hàng trăm GB log.
- Làm đầy filesystem.
- Khiến request hoặc cả container thất bại vì không thể ghi dữ liệu.
- Kéo dài thời gian backup hoặc điều tra sự cố.

Rolling policy không thay thế việc giám sát disk usage, nhưng là một lớp kiểm soát quan trọng khi ghi log ra file cục bộ.

## 10. Cấu hình đường dẫn file theo Spring property

Ta có thể thay property Logback cố định bằng **springProperty**:

application.yml:

~~~yaml
app:
  logging:
    directory: logs
~~~

logback-spring.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="logDir"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">

        <file>${logDir}/application.log</file>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${logDir}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>

</configuration>
~~~

Chạy với:

~~~bash
java -jar app.jar --app.logging.directory=/var/log/my-app
~~~

nếu process có quyền ghi phù hợp, Logback có thể sử dụng thư mục được cung cấp.

### 10.1. Không nhầm app.logging.directory với logging.file.path

**app.logging.directory** trong ví dụ là property do dự án tự định nghĩa. Spring Boot không tự biết rằng nó điều khiển file logging. Chính thẻ springProperty trong XML và các tham chiếu **${logDir}** đã biến nó thành đường dẫn.

**logging.file.path** hoặc **logging.file.name** là property của Spring Boot dành cho cơ chế file logging được hỗ trợ. Nếu viết cấu hình XML riêng và không tham chiếu tới những giá trị tương ứng, thay đổi logging.file.path có thể không tác động đến FileAppender custom.

### 10.2. Ưu tiên cấu hình có thể triển khai

Nên tránh hard-code:

~~~xml
<file>C:\Users\developer\Desktop\application.log</file>
~~~

Trong code dùng chung giữa nhiều môi trường. Hãy để deployment cung cấp vị trí file hoặc ưu tiên stdout khi nền tảng đã thu thập container logs.

## 11. Chọn console ở container, file ở môi trường khác

Trong Docker và Kubernetes, phương pháp phổ biến là ghi ra **stdout/stderr** và để runtime/agent của nền tảng thu thập, luân chuyển, chuyển tiếp và lưu trữ.

Ghi cả file local trong container đôi khi gây:

- Log biến mất khi container bị thay thế.
- Hai cơ chế rotation cạnh tranh.
- Không có persistent volume.
- Vấn đề quyền ghi do container chạy non-root.
- Việc gom log từ nhiều replica khó khăn hơn.

Một cấu hình profile-specific minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/local-app.log</file>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/local-app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <springProfile name="local">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="FILE"/>
        </root>
    </springProfile>

    <springProfile name="!local">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

Trong ví dụ, FILE được định nghĩa trước nhưng chỉ được gắn vào root ở nhánh local. Với Logback, appender có thể được khởi tạo theo cấu hình ngay cả nếu chưa gắn vào logger, tùy cơ chế xử lý; nếu mục tiêu là **không chạm filesystem** ở môi trường container, nên đưa cả **định nghĩa FILE appender** vào springProfile local, không chỉ chuyển appender-ref.

### 11.1. Mẫu không tạo FILE khi profile không cần

~~~xml
<springProfile name="local">
    <appender name="LOCAL_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/local.log</file>
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.local"
            level="DEBUG"
            additivity="false">
        <appender-ref ref="LOCAL_FILE"/>
    </logger>
</springProfile>
~~~

Khi local không phù hợp, nhánh cấu hình không được áp dụng. Tùy mục tiêu, có thể gắn thêm LOCAL_FILE vào root trong nhánh đó nếu muốn thu toàn bộ log của ứng dụng.

### 11.2. Không dùng profile để thay thế quan sát runtime

Một process báo **prod** chưa chắc là container hoặc VM có volume log đúng. Chính sách logging phải đồng bộ với kiến trúc triển khai, không chỉ tên profile.

Đối với môi trường production có log pipeline tập trung, nhiều nhóm ưu tiên console JSON/structured logging hoặc pattern text thống nhất, rồi để hạ tầng định tuyến và retention.

## 12. Độ ưu tiên giữa logging.level và XML

Khi dùng Logback với Spring Boot, mức log có thể xuất hiện ở nhiều nguồn:

~~~yaml
logging:
  level:
    com.example.orders: DEBUG
~~~

và:

~~~xml
<logger name="com.example.orders" level="INFO"/>
~~~

Không nên duy trì hai nguồn mâu thuẫn để điều khiển cùng một logger. Spring Boot có quá trình khởi tạo và áp dụng log levels từ Environment; kết quả quan sát được còn phụ thuộc thứ tự xử lý, việc logging system reload cấu hình và những API thay đổi level ở runtime.

**Nguyên tắc dễ vận hành**:

- Cấu trúc appender, encoder, rolling policy → quản lý trong logback-spring.xml.
- Log level thường xuyên thay đổi theo deployment → ưu tiên logging.level trong application.yml/env/CLI nếu không cần hard-code riêng trong XML.
- Nếu XML chủ động chọn level theo springProfile → tránh đặt một logging.level cho cùng logger ở nhiều nguồn với ý định khác nhau.

### 12.1. Chỉ định một logger level bằng CLI

~~~bash
java -jar app.jar --logging.level.com.example.orders=DEBUG
~~~

Đây là cách hữu ích khi cần tăng chi tiết trong một lần chạy để điều tra lỗi, không cần sửa logback-spring.xml.

### 12.2. Thay level không bảo đảm appender sẽ xuất log

Nếu một logger có additivity=false nhưng không có appender, nâng level lên DEBUG vẫn không làm log xuất hiện. Nếu appender có filter riêng loại DEBUG, vấn đề cũng vẫn còn.

Hãy kiểm tra theo chuỗi:

~~~text
Logger name
    │
Effective level
    │
Appender route / additivity
    │
Appender filter / encoder
    │
Output destination
~~~

## 13. logging.config: sử dụng file cấu hình không nằm ở vị trí mặc định

Spring Boot hỗ trợ property **logging.config** để chỉ định một resource cấu hình logging.

Ví dụ:

~~~bash
java -jar app.jar --logging.config=classpath:logging/custom-logback.xml
~~~

Với file:

~~~text
src/main/resources/logging/custom-logback.xml
~~~

Hoặc một file ngoài JAR:

~~~bash
java -jar app.jar --logging.config=file:/etc/my-app/logback-spring.xml
~~~

Khi file nằm ngoài artifact, process cần quyền đọc và startup phải có cấu hình đường dẫn chính xác.

### 13.1. Không tự đọc file logging bằng @Bean để cấu hình quá muộn

Logging được khởi tạo sớm; một @Configuration class tạo bean sau khi context refresh không phải cách chính để chọn file Logback ban đầu.

Nếu muốn Bootstrap dùng một configuration file, hãy dùng tên quy ước logback-spring.xml hoặc cung cấp **logging.config** qua nguồn cấu hình sớm phù hợp.

### 13.2. Kiểm tra URL, đường dẫn và classpath

Một số lỗi thường gặp:

- Chỉ định classpath: nhưng file không được đóng gói vào JAR.
- Dùng đường dẫn tương đối không khớp working directory.
- Mount file dưới thư mục khác với logging.config.
- Container không có quyền đọc file.
- XML sai cú pháp.
- Backend thực tế là Log4j2 nhưng file chỉ cấu hình Logback.

Không nên đặt logging.config trỏ tới một resource không tồn tại rồi hy vọng Spring Boot tự bỏ qua mọi lỗi. Tùy logging system và đường dẫn, ứng dụng có thể khởi động thất bại hoặc rơi vào hành vi không như ý.

## 14. Spring Boot khởi tạo logging ở thời điểm nào?

Logging system được Spring Boot chuẩn bị **sớm trong vòng đời khởi động**, khi ApplicationContext chưa hoàn toàn sẵn sàng. Điều này là cần thiết vì chính lỗi đọc cấu hình hoặc lỗi tạo bean cũng phải được ghi log.

Một sơ đồ khái niệm:

~~~text
SpringApplication.run(...)
           │
           ▼
Khởi động logging và chuẩn bị Environment
           │
           ▼
Nạp Config Data / áp dụng cấu hình logging phù hợp
           │
           ▼
Tạo và refresh ApplicationContext
           │
           ▼
Khởi tạo bean, chạy runner, nhận request
           │
           ▼
Ứng dụng dừng / logging system giải phóng tài nguyên
~~~

Boot có nhiều mốc sự kiện chi tiết hơn, và một số bước logging initialization có thể diễn ra nhiều lần khi Environment đã đủ thông tin. Điểm cần nhớ là **logging không đợi tất cả application beans được tạo xong**.

### 14.1. Vì sao @PropertySource đôi khi không điều khiển được logging?

Ví dụ:

~~~java
@Configuration
@PropertySource("classpath:custom-logging.properties")
public class AdditionalPropertyConfiguration {
}
~~~

Class @Configuration thường được xử lý trong giai đoạn xây dựng ApplicationContext. Nếu custom-logging.properties đặt một key như logging.level.root hoặc logging.config, nó có thể được thêm vào Environment **quá muộn** đối với quá trình chọn cấu hình logging ban đầu.

Với những key điều khiển logging lúc startup, hãy sử dụng nguồn cấu hình được nạp sớm như:

- application.yml hoặc Config Data phù hợp.
- Environment variable.
- JVM system property.
- Command-line argument.

Không nên coi @PropertySource như một cách tương đương tuyệt đối với những nguồn đó cho logging initialization.

### 14.2. Không dùng Spring bean để tạo Logback appender lúc bootstrap

Một Logback appender được tạo từ cấu hình XML không nhất thiết là Spring bean và không tự tham gia dependency injection của ApplicationContext. Không nên mặc định rằng bạn có thể dùng @Autowired trong một Appender class do Logback tự khởi tạo.

Nếu cần custom appender sử dụng dependency phức tạp, cần thiết kế tích hợp rõ ràng giữa Logback lifecycle và Spring lifecycle, đặc biệt chú ý thứ tự khởi tạo, async queues và việc hủy tài nguyên.

Thông thường, appender có sẵn và logging pipeline bên ngoài là lựa chọn dễ bảo trì hơn custom appender phụ thuộc các service nghiệp vụ.

### 14.3. Tắt scan của Logback khi dùng Spring extensions

Native Logback hỗ trợ cơ chế quét lại cấu hình:

~~~xml
<configuration scan="true" scanPeriod="30 seconds">
    <!-- Native Logback configuration. -->
</configuration>
~~~

Tuy nhiên, **các extension của Spring Boot như springProfile/springProperty không tương thích với việc cấu hình được Logback tự quét lại bằng native configuration scanning**. Khi Logback tự reload, nó có thể không biết cách diễn giải những tag này và báo lỗi tương tự:

~~~text
no applicable action for [springProperty]
no applicable action for [springProfile]
~~~

Nếu dùng các extension của Spring Boot, đừng bật scan="true" như một giải pháp reload nóng đơn giản. Thay đổi logging configuration nên đi qua một quy trình deploy/restart hoặc cơ chế reload được thiết kế và kiểm chứng phù hợp.

## 15. Log exception đúng cách

Logging không chỉ là ghi một chuỗi message. Với exception, thông tin stack trace và nguyên nhân gốc là phần quan trọng để điều tra.

Ví dụ:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.error("Cannot save order {}", order.getId(), ex);
    throw ex;
}
~~~

Truyền exception làm tham số cuối giúp logging backend có cơ hội xuất stack trace.

### 15.1. Tránh log chỉ ex.getMessage()

Ví dụ nên tránh:

~~~java
log.error("Cannot save order: {}", ex.getMessage());
~~~

Cách này có thể làm mất stack trace và cause chain. Một số exception message còn chứa thông tin hệ thống hoặc dữ liệu nhạy cảm.

Nên:

~~~java
log.error("Cannot save order {}", orderId, ex);
~~~

và kiểm soát nơi lưu log theo chính sách bảo mật.

### 15.2. Tránh log cùng exception ở mọi tầng

Ví dụ:

~~~text
Repository: ERROR Save failed
Service:    ERROR Save failed
Controller: ERROR Save failed
Global:     ERROR Request failed
~~~

Nếu mỗi tầng bắt exception, log ERROR và ném lại, một lỗi duy nhất có thể tạo bốn stack traces trùng lặp.

Một quy ước thực hành:

- Tầng thấp ghi log khi có ngữ cảnh mới thực sự hữu ích hoặc khi nó **xử lý** lỗi tại chỗ.
- Nếu chỉ ném lại lỗi, nhiều trường hợp không cần log lần nữa.
- Tầng biên như global exception handler có thể ghi lỗi một lần với request ID và ngữ cảnh an toàn.

Quy tắc cụ thể tùy kiến trúc, nhưng nên tránh “log rồi throw” ở mọi method.

### 15.3. Log WARN hay ERROR?

Không có quy tắc cứng cho mọi ứng dụng:

- **DEBUG**: chi tiết phục vụ chẩn đoán, có thể tắt ở production.
- **INFO**: mốc nghiệp vụ/vận hành quan trọng trong điều kiện bình thường.
- **WARN**: tình huống bất thường nhưng hệ thống có thể tiếp tục hoặc đã fallback.
- **ERROR**: thao tác thất bại cần chú ý, thường ảnh hưởng chức năng hoặc điều kiện vận hành.

Không nên ghi ERROR cho mỗi retry tạm thời nếu retry cuối cùng thành công, vì điều đó gây nhiễu alert và khó phân biệt sự cố thật. Có thể ghi WARN/DEBUG cho lần thử trung gian và ERROR ở kết quả thất bại cuối cùng, theo chính sách của hệ thống.

## 16. Correlation ID và MDC trong log pattern

Khi một request đi qua controller, service và repository, nhiều dòng log xuất hiện trên cùng hoặc nhiều thread. Nếu không có mã tương quan, rất khó biết những dòng nào thuộc cùng request.

SLF4J hỗ trợ **MDC** (Mapped Diagnostic Context) để gắn các key-value vào ngữ cảnh logging. Logback pattern có thể đọc chúng bằng **%X{key}**.

Ví dụ pattern:

~~~xml
<pattern>%d{HH:mm:ss.SSS} %-5level [requestId=%X{requestId:-none}] %logger{36} - %msg%n</pattern>
~~~

Ở đây:

- **%X{requestId}** lấy giá trị MDC dưới key requestId.
- **:-none** là giá trị fallback của converter trong cú pháp pattern phù hợp.

Một dòng log có thể trông như:

~~~text
09:34:10.327 INFO  [requestId=41dd5a] c.e.OrderService - Creating order ORD-17
~~~

### 16.1. Filter gắn request ID với Spring MVC

Ví dụ dùng Spring Boot 3 và Servlet API jakarta:

~~~java
package com.example.demo.logging;

import java.io.IOException;
import java.util.UUID;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {

            response.setHeader("X-Request-Id", requestId);
            chain.doFilter(request, response);
        }
    }
}
~~~

Mẫu này tạo ID mới cho mỗi request, gắn vào MDC trong phạm vi filter và dọn key khi kết thúc.

Với hệ thống phân tán, một request có thể đã có trace ID từ tracing infrastructure. Khi đó không nhất thiết tự tạo một ID khác. Nên dùng cơ chế correlation/tracing thống nhất và kiểm tra dữ liệu từ header không tin cậy trước khi đưa vào log.

### 16.2. Vì sao phải dọn MDC?

MDC trong logging setup truyền thống thường có liên hệ với thread. Servlet thread có thể được tái sử dụng để xử lý request khác.

Nếu code:

~~~java
MDC.put("requestId", requestId);
// Xử lý request nhưng không remove/clear.
~~~

thì request tiếp theo trên cùng thread có thể thấy một requestId cũ, khiến việc truy vết sai.

Sử dụng try-finally hoặc MDC.putCloseable giúp giới hạn phạm vi của key được đặt.

### 16.3. MDC và async/reactive context

MDC không tự động được truyền đúng qua mọi executor, CompletableFuture hoặc Reactor pipeline. Khi chuyển thread, context logging có thể mất hoặc bị nhiễm nếu không có cơ chế propagation/cleanup.

Trong Spring Boot hiện đại, Micrometer Tracing/Observation có thể bổ sung traceId/spanId vào log tùy stack và cấu hình. Hãy ưu tiên cơ chế propagation được framework hỗ trợ thay vì tự copy MDC thủ công giữa các thread mà không xử lý cleanup.

### 16.4. MDC không phải chỗ lưu dữ liệu bí mật

Không đặt access token, password, số thẻ hoặc payload cá nhân vào MDC chỉ để xuất chúng trên mọi dòng log. Một giá trị MDC có thể bị nhiều logger/appenders ghi vào những nơi bạn không kiểm soát.

Các key thích hợp thường là:

- requestId.
- correlationId.
- traceId/spanId do tracing infrastructure quản lý.
- business operation ID không nhạy cảm.

## 17. AsyncAppender và logging bất đồng bộ

Một appender ghi file hoặc mạng có thể mất thời gian. Logback hỗ trợ **AsyncAppender** để đưa logging events vào hàng đợi trước khi ghi qua appender đích.

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC_CONSOLE"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC_CONSOLE"/>
    </root>

</configuration>
~~~

Khi logger phát event, AsyncAppender có thể enqueue event để worker khác chuyển tới CONSOLE. Điều này giảm một phần chi phí ghi tại thread nghiệp vụ, nhưng không có nghĩa logging đã hoàn toàn “miễn phí”.

### 17.1. Các trade-off khi dùng AsyncAppender

- Hàng đợi tiêu thụ bộ nhớ.
- Khi ứng dụng ghi log nhanh hơn output destination, queue có thể đầy.
- Chính sách discarding/blocking ảnh hưởng việc mất log hoặc độ trễ.
- Trong shutdown đột ngột, event còn trong queue có thể chưa được ghi ra ngoài.
- Một số dữ liệu phải được capture trước khi thread phát event hoàn tất.

Không nên bật async rồi mặc định mọi ERROR sẽ được lưu bền vững. Hãy kiểm tra chính sách queue, discarding threshold và thời gian flush/stop của appender thực tế.

### 17.2. Không dùng AsyncAppender như message queue nghiệp vụ

Log không phải hệ thống bảo đảm giao hàng cho business events. Nếu nghiệp vụ yêu cầu một event “đã thanh toán” không được mất, hãy dùng transaction/outbox/message broker phù hợp. Một dòng log INFO, dù qua AsyncAppender, không thay thế event store hoặc audit ledger có yêu cầu bền vững.

### 17.3. Cẩn thận với output chậm

Nếu ConsoleAppender ghi ra một stdout pipe đang bị backpressure hoặc một remote appender không phản hồi, logging có thể ảnh hưởng hiệu năng chung.

Theo dõi log volume, queue depth (nếu có instrumentation), tốc độ collector và chính sách khi output destination không sẵn sàng.

## 18. Structured logging và XML pattern

Pattern text là cách đơn giản, dễ đọc bằng mắt. Nhưng ở hệ thống có nhiều replica và truy vấn log tập trung, **structured logging** (ví dụ JSON mỗi dòng) có thể giúp truy vấn bằng trường.

Ví dụ một event ở dạng cấu trúc:

~~~json
{
  "timestamp": "2026-11-13T09:34:10.327Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Creating order ORD-17",
  "service": "order-api",
  "requestId": "41dd5a"
}
~~~

Đây là hình minh họa dữ liệu, không phải cam kết tất cả Boot versions có sẵn đúng JSON schema này.

Có nhiều cách triển khai structured logging:

- Tính năng structured logging do phiên bản Spring Boot đang dùng hỗ trợ.
- Encoder/layout JSON của một thư viện phù hợp với Logback.
- Custom logging integration được tổ chức triển khai quản lý.

Khi dùng **logback-spring.xml**, việc định nghĩa encoder tùy chỉnh có thể thay thế encoder/pattern mặc định. Cần bảo đảm các field quan trọng như timestamp, severity, logger, thread và trace/correlation ID vẫn được ghi.

### 18.1. Chọn text hay JSON theo hệ thống thu thập log

| Đầu ra | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| Text pattern | Dễ đọc trong terminal, cấu hình tối giản. | Công cụ phân tích phải parse chuỗi nếu cần trường. |
| JSON structured | Truy vấn theo field thuận tiện, thích hợp log pipeline. | Cần encoder, schema và xử lý escaping/field privacy. |

Nếu hệ thống thu thập log đã parse text theo một format chuẩn, không nhất thiết phải tự chuyển sang JSON. Quan trọng là định dạng nhất quán và có thể phân tích bằng công cụ quan sát thực tế.

### 18.2. Đừng tự nối JSON bằng String

Ví dụ không nên:

~~~java
log.info("{\"user\":\"" + userInput + "\"}");
~~~

Input có dấu ngoặc kép, xuống dòng hoặc dữ liệu đặc biệt có thể làm chuỗi JSON không hợp lệ. Dữ liệu không tin cậy còn có thể gây log injection hoặc khiến một event trông như nhiều event.

Hãy dùng encoder structured logging phù hợp hoặc API structured arguments được thư viện hỗ trợ, đồng thời kiểm soát trường dữ liệu được phép ghi.

## 19. Chuyển từ Logback sang Log4j2

Một ứng dụng Spring Boot có thể dùng Log4j2 thay Logback. Trong trường hợp đó, **logback-spring.xml không còn là file cấu hình chính của logging backend**.

Với Gradle, ví dụ dependency management theo một starter:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
~~~

Đoạn này minh họa cách loại logging starter mặc định và thêm Log4j2. Trong dự án nhiều starters, cần xem dependency graph thật để bảo đảm không còn binding/provider xung đột hoặc logging implementation ngoài ý định. Phiên bản dependency thường do Spring Boot dependency management quản lý.

### 19.1. File log4j2-spring.xml

Vị trí tương ứng:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Ví dụ tối thiểu với Log4j2:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">

    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                    pattern="%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="debug"/>

        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>

</Configuration>
~~~

Đây là **cú pháp Log4j2**, không phải Logback XML. Các tag Configuration, Appenders, Loggers, Root và AppenderRef khác cấu trúc Logback.

### 19.2. Giữ SLF4J trong code nghiệp vụ

Nếu các service viết:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

thì phần lớn code không cần sửa khi đổi logging backend, miễn runtime có SLF4J provider/bridge đúng và dependencies nhất quán.

Không nên đưa API riêng của Logback vào mọi class nghiệp vụ chỉ vì hiện tại dự án dùng Logback. Các API riêng nên giới hạn ở phần cấu hình/hạ tầng thật sự cần chúng.

### 19.3. Spring Boot extensions của Log4j2

Spring Boot hỗ trợ cơ chế tích hợp cấu hình phù hợp với Log4j2, gồm việc sử dụng file tên **log4j2-spring.xml** để Boot có thể tham gia quá trình cấu hình. Tuy nhiên, **không sao chép nguyên các tag springProfile/springProperty của Logback** sang Log4j2.

Mỗi backend có mô hình cấu hình và phần mở rộng riêng. Khi thay backend:

- Đổi XML syntax đúng logging system.
- Xác minh Spring profile/environment lookup theo cơ chế Log4j2 được Boot hỗ trợ.
- Kiểm tra dependency providers và bridges.
- Kiểm tra console/file output, rotation và JSON encoder nếu có.
- Kiểm tra pattern và throwable output vì converters có thể khác.

### 19.4. Java Util Logging và các bridge

Một số thư viện dùng java.util.logging (JUL), Commons Logging hoặc API khác. Spring Boot starters thường mang các bridge phù hợp để đưa log về backend chính.

Tránh cấu hình đồng thời nhiều backend/bridges không tương thích hoặc tạo vòng lặp bridge. Khi thấy log mất hoặc bị nhân đôi, kiểm tra dependency tree và những logging implementations thực sự được nạp.

## 20. Filter trong appender: không phải mọi output đều cần cùng level

Giả sử ứng dụng muốn:

- Console ghi từ INFO trở lên.
- File cảnh báo chỉ ghi WARN và ERROR.

Có thể dùng **ThresholdFilter** của Logback cho từng appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARN_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/warnings.log</file>

        <filter
                class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/warnings.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="WARN_FILE"/>
    </root>

</configuration>
~~~

Với cấu hình này:

- INFO có thể xuất hiện ở console.
- WARN và ERROR có thể xuất hiện cả console và file warnings.
- DEBUG thường bị loại tại root INFO và không được appender nào xử lý.

### 20.1. Level và filter là hai tầng kiểm tra

Một appender filter **không thể khôi phục** event đã bị logger chặn từ trước.

Ví dụ:

~~~text
Logger effective level = WARN
             │
      Event DEBUG
             │
             ▼
      Bị loại sớm
             │
             X
Không đi tới ConsoleAppender dù filter ở đó cho phép DEBUG
~~~

Khi muốn lưu DEBUG cho package riêng:

~~~xml
<logger name="com.example.orders" level="DEBUG"/>
~~~

đồng thời cần xác định appender route và filters có cho phép DEBUG hay không.

### 20.2. Sử dụng filter để hạn chế thông tin

Filter có thể giảm số lượng event lưu vào một destination, nhưng không phải công cụ thay thế hoàn toàn cho bảo mật và phân loại dữ liệu. Không nên mặc định một regex filter có thể loại bỏ tất cả secret hoặc PII trong mọi log message.

Với dữ liệu nhạy cảm, tốt nhất **không tạo nội dung log nguy hiểm ngay từ code** hoặc áp dụng cơ chế masking/redaction đã được thiết kế và kiểm thử ở tầng phù hợp.

## 21. Thay đổi log level khi ứng dụng đang chạy

Trong nhiều hệ thống, bạn không muốn restart một service production chỉ để bật DEBUG tạm thời cho một package.

Spring Boot Actuator có thể cung cấp endpoint **loggers** để quan sát và thay đổi mức log tại runtime, tùy logging system có hỗ trợ.

Ví dụ endpoint:

~~~text
GET /actuator/loggers
GET /actuator/loggers/com.example.orders
POST /actuator/loggers/com.example.orders
~~~

Request body khi đặt mức DEBUG:

~~~json
{
  "configuredLevel": "DEBUG"
}
~~~

Để trả logger về trạng thái không có level được cấu hình tường minh, Actuator hỗ trợ cách đặt configuredLevel về null trong cơ chế endpoint tương ứng:

~~~json
{
  "configuredLevel": null
}
~~~

### 21.1. Chỉ expose khi có kiểm soát truy cập

Ví dụ cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers
~~~

Đây **không phải cấu hình bảo mật đầy đủ**. Endpoint thay đổi mức log có thể làm lộ thông tin debug, tăng tải hệ thống và tạo lượng log lớn.

Hãy giới hạn quyền truy cập bằng security configuration, network policies và quy trình vận hành phù hợp. Không expose khả năng điều khiển log level cho người dùng không được cấp quyền.

### 21.2. Thay đổi runtime có được lưu qua restart không?

Thông thường, một thay đổi log level qua Actuator tác động tới logging system của **process hiện tại**. Nó không tự sửa application.yml hoặc logback-spring.xml trong repository.

Khi instance restart, hệ thống sẽ khởi tạo logging theo configuration/deployment hiện có. Vì vậy:

- Dùng Actuator cho chẩn đoán ngắn hạn có kiểm soát.
- Dùng configuration management/CI/CD nếu muốn thay đổi lâu dài.
- Ghi nhận ai đã thay đổi level và thời điểm khôi phục.

Trong một cluster nhiều replica, thay đổi logger level trên một instance không tự đảm bảo tất cả instance khác cũng thay đổi. Công cụ vận hành phải chọn đúng phạm vi áp dụng.

### 21.3. Không để DEBUG ở production quá lâu

DEBUG/TRACE có thể:

- Tăng chi phí format và ghi log.
- Tăng lưu lượng của log pipeline.
- Làm đầy disk hoặc retention quota nhanh hơn.
- Ghi ra những field dữ liệu mà hệ thống chưa được thiết kế để xử lý ở production.

Khi sử dụng để điều tra, xác định thời gian, package và điều kiện kết thúc rõ ràng.

## 22. Kiểm thử logging bằng OutputCaptureExtension

Spring Boot hỗ trợ công cụ test bắt output console, thường dùng qua **OutputCaptureExtension** trong spring-boot-test.

Ví dụ JUnit 5:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class OrderLoggingTests {

    private static final Logger log =
            LoggerFactory.getLogger(OrderLoggingTests.class);

    @Test
    void writesExpectedMessage(CapturedOutput output) {
        log.info("Order {} accepted", "ORD-42");

        assertThat(output.getAll())
                .contains("Order ORD-42 accepted");
    }
}
~~~

Test này kiểm tra việc message được ghi tới output mà extension bắt được, với điều kiện logger có level phù hợp và logging backend đang dùng console appender.

### 22.1. Test không cần so sánh toàn bộ dòng log

Timestamp, thread name, PID và pattern có thể thay đổi giữa môi trường chạy. Vì vậy không nên khóa unit test vào toàn bộ dòng log một cách mong manh nếu mục tiêu chỉ là xác nhận message cần thiết.

Nếu mục tiêu kiểm tra chính pattern/correlation ID, lúc đó mới cần test chính xác hơn với cấu hình test được kiểm soát.

### 22.2. OutputCaptureExtension không chứng minh file rotation

Test console output không xác nhận:

- RollingFileAppender đã ghi đúng file.
- Archive được xoay theo size/date.
- Filesystem có quyền ghi.
- totalSizeCap thực sự giới hạn archive.
- AsyncAppender đã flush hết queue.

Những yêu cầu này cần integration tests hoặc kiểm chứng vận hành riêng với thư mục tạm và cấu hình logging tương ứng.

Trong phạm vi một test đơn giản, đừng thêm một bộ kiểm thử phức tạp chỉ để chứng minh log.info có thể in một String.

### 22.3. @SpringBootTest và profile dành cho logging

Nếu logging configuration phụ thuộc Spring profile, có thể dùng:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class LoggingConfigurationIntegrationTests {
    // Test hành vi logging theo profile test.
}
~~~

Nhưng test context và logging system có vòng đời khác nhau trong một số tình huống, đặc biệt khi test suite dùng nhiều contexts và hệ thống logging là cấu hình cấp JVM. Đừng giả định các thay đổi global logging của một test được cô lập tuyệt đối khỏi các test khác.

Khi cần kiểm tra riêng các nhánh logback-spring.xml, hãy xây test có scope rõ ràng và tránh thay đổi global logger levels rồi không khôi phục.

## 23. Kiểm tra logger level từ code và Actuator

Trong code ứng dụng, với SLF4J:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Complex diagnostic value: {}",
            buildExpensiveDiagnostic());
}
~~~

Tại sao cần kiểm tra isDebugEnabled ở đây? Vì buildExpensiveDiagnostic() có thể tiêu tốn CPU ngay cả khi DEBUG bị chặn, nếu bạn tính toán nó trước khi truyền vào lời gọi log.

Với các giá trị đã sẵn có, thường không cần bọc từng log.debug trong if:

~~~java
log.debug("Order {} has status {}", orderId, status);
~~~

SLF4J placeholder giúp tránh nối chuỗi message thủ công theo cách thông thường.

### 23.1. Khi nào cần API riêng của Logback?

Nếu ứng dụng phải kiểm tra cấu hình appender hoặc thay level bằng API Logback, có thể cần downcast tới kiểu ch.qos.logback.classic.Logger. Nhưng đây là hành vi phụ thuộc implementation.

Trong code nghiệp vụ, nên ưu tiên SLF4J để giữ khả năng thay logging backend. Với thao tác vận hành, ưu tiên cơ chế logging.level hoặc Actuator loggers nếu đáp ứng được yêu cầu.

### 23.2. Level không phải output format

Một hệ thống có:

~~~properties
logging.level.com.example.orders=DEBUG
~~~

không có nghĩa log sẽ mang thêm requestId, JSON field hoặc exception stack. Những field đó do code event, MDC/tracing và encoder/pattern quyết định.

Ngược lại, một pattern rất chi tiết vẫn không thể hiện DEBUG nếu logger level chặn.

## 24. Logging và bảo mật dữ liệu

Logging hữu ích cho vận hành nhưng cũng là nơi dễ lưu dữ liệu nhạy cảm ngoài ý muốn.

Không nên ghi trực tiếp:

- Password, token, API key hoặc session cookie.
- Toàn bộ Authorization header.
- Dữ liệu thẻ thanh toán.
- Payload chứa thông tin cá nhân nhạy cảm.
- Secret đọc từ Environment hoặc configuration properties.
- JDBC connection string có credential.
- Những mã định danh nhạy cảm không cần thiết cho mục đích chẩn đoán.

Ví dụ nên tránh:

~~~java
log.info("Login request: {}", loginRequest);
~~~

Nếu toString() của LoginRequest in cả password, secret sẽ đi vào log.

Nên ghi những trường được phê duyệt:

~~~java
log.info("Login attempt accepted for requestId={}",
        requestId);
~~~

Hoặc ghi kết quả và mã trạng thái an toàn thay vì toàn bộ request/response body.

### 24.1. Không bật TRACE toàn hệ thống vô thời hạn

Các logging levels chi tiết có thể khiến framework hoặc HTTP client ghi nhiều metadata hơn. Một số thư viện hỗ trợ wire logging, có thể bao gồm request headers hoặc body tùy cấu hình.

Vì thế không nên đặt:

~~~yaml
logging:
  level:
    root: TRACE
~~~

trong production như một “cách dễ nhất để tìm lỗi”. Nếu cần, bật đúng logger trong thời gian giới hạn, kiểm tra khả năng lộ dữ liệu và xác định cách tắt lại.

### 24.2. Log injection và dữ liệu không tin cậy

User input có thể chứa newline hoặc ký tự điều khiển. Nếu in trực tiếp vào text log, một message có thể bị tách thành nhiều dòng trông như những event khác nhau.

Ví dụ:

~~~java
log.info("Display name: {}", untrustedDisplayName);
~~~

Với hệ thống có log ingestion/parser nhạy cảm, nên dùng structured logging encoder đúng cách hoặc escape/normalize input theo quy tắc của pipeline. Đừng xem mọi chuỗi người dùng gửi lên là metadata an toàn.

### 24.3. Quyền truy cập, retention và rotation

Một cấu hình logging production cần xác định:

- Ai được đọc logs và vì mục đích gì?
- Log được lưu tại console pipeline hay file?
- Thời hạn lưu trữ bao lâu?
- Có mã hóa trong lúc truyền/lưu không?
- Cần audit access vào logs không?
- Dữ liệu cần xóa hoặc ẩn theo chính sách nào?

logback-spring.xml có thể cấu hình file rotation, nhưng **retention policy của hệ thống log tập trung** là trách nhiệm hạ tầng/vận hành rộng hơn. Không thể chỉ dựa vào maxHistory trong file XML để kết luận toàn bộ dữ liệu đã được xóa khỏi mọi nơi.

## 25. Logging trong production: vài nguyên tắc thực hành

1. **Ưu tiên một đường thu thập log rõ ràng.** Với container, thường là console → collector → storage/analysis.
2. **Dùng level hợp lý.** INFO cho mốc vận hành chính; WARN/ERROR cho tình huống cần chú ý; DEBUG/TRACE có kiểm soát.
3. **Đặt tên logger theo class/package.** Dễ điều chỉnh riêng từng phần qua logging.level.
4. **Gắn correlation/trace ID khi cần.** Tránh truy vết thủ công qua timestamp đơn thuần.
5. **Giới hạn dung lượng và lưu trữ.** Nếu ghi file, có rotation; nếu dùng collector, quản lý retention/quotas.
6. **Giữ secret khỏi log.** Không log nguyên payload không tin cậy hoặc cấu hình nhạy cảm.
7. **Tránh log trùng.** Kiểm tra additivity và các appenders được gắn.
8. **Theo dõi chi phí logging.** Logging volume, blocking output và async queue đều ảnh hưởng hiệu năng.
9. **Đồng bộ cấu hình giữa replica.** Một pod DEBUG và pod khác INFO có thể làm kết quả điều tra không nhất quán.
10. **Đặt trách nhiệm rõ ràng.** Code phát sự kiện log; XML/Boot properties quyết định cách ghi; hạ tầng đảm nhiệm thu thập và lưu trữ dài hạn.

## 26. Chẩn đoán khi file logback-spring.xml không có tác dụng

Khi một cấu hình XML được thêm vào nhưng ứng dụng vẫn log theo pattern cũ, hãy kiểm tra theo lớp:

### Bước 1: Xác nhận runtime logging system

Spring Boot application có đang dùng Logback không? Có bị chuyển sang Log4j2 bởi starter khác hoặc dependency exclusions không?

Không thể dùng một Logback XML để điều khiển Log4j2.

### Bước 2: Kiểm tra file có trên classpath không

Đúng vị trí:

~~~text
src/main/resources/logback-spring.xml
~~~

Sau khi build, resource phải hiện diện trong JAR hoặc classpath. Tên file phải chính xác; một file chỉ có trong src/test/resources sẽ không nhất thiết được đóng gói cùng runtime artifact.

### Bước 3: Kiểm tra logging.config có ghi đè không

Nếu:

~~~text
logging.config=classpath:logging/custom.xml
~~~

được đặt trong process, Boot có thể dùng location đó thay vì file mặc định. Cần xem command line, environment và Config Data thực tế.

### Bước 4: Xác nhận XML hợp lệ

Lỗi phổ biến:

- Thiếu tag đóng.
- Đặt tên class appender/encoder không tồn tại.
- Thiếu appender-ref tương ứng.
- Dùng XML syntax của Log4j2 trong Logback.
- Dùng ký tự **&** chưa escape trong XML attribute.
- Tạo hai appender cùng tên với cấu hình mâu thuẫn.

Một XML file hợp lệ về cú pháp chưa chắc hợp lệ về cấu hình Logback; cả cấu trúc và loại component đều cần đúng.

### Bước 5: Xác minh Spring extensions được xử lý

Nếu dùng springProperty hoặc springProfile:

- File có được Boot load theo đường hỗ trợ không?
- Có dùng logback.xml được Logback tự load quá sớm không?
- Có bật scan="true" dẫn tới reload bằng native parser không?
- Profile active thực tế có phù hợp với biểu thức?
- Property source đã có trong Environment đủ sớm chưa?

### Bước 6: Xem logger effective level

Logger đang ghi có tên gì? Effective level có cho phép DEBUG hoặc INFO không? Có một logging.level property hoặc runtime Actuator override không?

### Bước 7: Xem appender route

Root/logger có gắn appender không? Có additivity=false mà quên appender-ref không? Có filter làm event bị loại không?

### Bước 8: Xem output destination

Console có được thu thập không? File path có đúng working directory không? Process có quyền tạo thư mục/file không? Volume còn dung lượng không?

### Bước 9: Xem rollover và lifecycle

File có bị rotate sang tên khác không? Async queue có event chưa flush không? Process có bị kill đột ngột làm mất phần output chưa ghi không?

Chẩn đoán theo trình tự này thường hiệu quả hơn việc tăng root level lên TRACE ngay lập tức.

## 27. Những lỗi thường gặp và cách xử lý

### 27.1. Dùng logback.xml nhưng viết springProfile

**Dấu hiệu:** khởi động báo lỗi parser hoặc Spring profile branch không có hiệu lực.

**Nguyên nhân:** Logback native loading xử lý logback.xml trước hoặc độc lập với các extension của Spring Boot.

**Cách xử lý:** ưu tiên **logback-spring.xml** khi sử dụng springProfile hoặc springProperty. Không bật native configuration scanning cho file có Spring extensions.

### 27.2. Chỉnh logging.level nhưng DEBUG không xuất hiện

**Dấu hiệu:** đã đặt logging.level.com.example=DEBUG nhưng không thấy dòng log.debug mong đợi.

**Nguyên nhân có thể:** logger name không khớp package, property bị ghi đè, appender route thiếu, additivity=false, appender filter chặn hoặc code không chạy qua nhánh log.

**Cách xử lý:** đọc effective level bằng Actuator loggers, xác nhận logger name thực tế và kiểm tra appender route.

### 27.3. Một sự kiện xuất hiện hai lần

**Dấu hiệu:** hai dòng có timestamp/message giống nhau xuất hiện trong cùng output.

**Nguyên nhân:** logger con có appender riêng nhưng vẫn additivity=true và root cũng gắn appender đó; cũng có thể có nhiều log bridges hoặc collector thu thập hai lần.

**Cách xử lý:** kiểm tra logger hierarchy, appender-ref, additivity và log collection pipeline. Chỉ dùng additivity=false khi logger đã có đường output chủ động.

### 27.4. Log biến mất khi thêm additivity=false

**Dấu hiệu:** một package trước đó có log, sau khi cấu hình logger riêng thì không còn dòng nào.

**Nguyên nhân:** logger bị chặn truyền lên root nhưng không có appender riêng.

**Cách xử lý:** gắn appender-ref đúng hoặc bỏ additivity=false nếu chỉ cần đổi level.

### 27.5. File log không được tạo

**Dấu hiệu:** console vẫn có log, file không xuất hiện.

**Nguyên nhân:** FileAppender không được gắn vào root/logger, đường dẫn sai, thư mục không ghi được, thiếu dung lượng hoặc appender không được tạo do profile condition không match.

**Cách xử lý:** kiểm tra appender-ref, working directory, permissions, profile, logback status và filesystem.

### 27.6. File log nằm ở thư mục không ngờ tới

**Dấu hiệu:** tìm log trong thư mục dự án nhưng file nằm tại vị trí khác.

**Nguyên nhân:** đường dẫn tương đối như logs/application.log được giải quyết theo working directory của process.

**Cách xử lý:** dùng location tường minh, biến cấu hình do deployment cấp và xác nhận path khi khởi động.

### 27.7. logback-spring.xml không được đóng gói

**Dấu hiệu:** IDE dùng pattern tùy chỉnh, executable JAR lại dùng cấu hình khác.

**Nguyên nhân:** file nằm sai thư mục, ví dụ src/test/resources thay vì src/main/resources, hoặc build process không đưa resource vào artifact.

**Cách xử lý:** xác nhận classpath của artifact đang chạy và tên file thực tế.

### 27.8. springProperty không nhận giá trị từ @PropertySource

**Dấu hiệu:** property có thể đọc được sau khi context khởi tạo, nhưng logging XML lại dùng defaultValue.

**Nguyên nhân:** @PropertySource trên configuration class được thêm quá muộn so với logging initialization.

**Cách xử lý:** đưa property logging vào nguồn cấu hình sớm như Config Data, environment variable hoặc command line.

### 27.9. File logging được reload nhưng Spring tags báo lỗi

**Dấu hiệu:** ứng dụng khởi động ổn nhưng sau một khoảng thời gian log báo **no applicable action for springProperty/springProfile**.

**Nguyên nhân:** native Logback scan tự reload cấu hình không qua Spring Boot extensions.

**Cách xử lý:** tắt scan và quản lý thay đổi cấu hình qua cơ chế được Boot hỗ trợ và quy trình vận hành.

### 27.10. Có file log nhưng rotation không hoạt động

**Dấu hiệu:** một file tăng mãi; không thấy archive hoặc policy không như mong đợi.

**Nguyên nhân:** dùng FileAppender thay RollingFileAppender, khai báo RollingPolicy sai, fileNamePattern không phù hợp hoặc kích thước/ngày chưa đạt điều kiện rollover.

**Cách xử lý:** kiểm tra loại appender, policy, fileNamePattern, maxFileSize/maxHistory và logback status. Đừng coi maxHistory là một giới hạn kích thước cho file hiện tại.

### 27.11. Chỉnh logback-spring.xml trong JAR mà process không đổi

**Dấu hiệu:** file trên source hoặc image đã thay đổi nhưng JVM đang chạy vẫn dùng cấu hình cũ.

**Nguyên nhân:** logging system đã khởi tạo lúc startup; thay file trong source không tự cập nhật process đã chạy.

**Cách xử lý:** build/redeploy hoặc restart có kiểm soát; không dựa vào native scan khi dùng Spring extensions.

### 27.12. Log INFO nhưng mất stack trace

**Dấu hiệu:** chỉ thấy message lỗi, không thấy nguyên nhân hay dòng code.

**Nguyên nhân:** chỉ log ex.getMessage(), bỏ Throwable, hoặc encoder/filter custom không xuất exception data.

**Cách xử lý:** truyền Throwable vào logger ở vị trí phù hợp và xác nhận throwable conversion trong encoder.

### 27.13. Ghi log quá nhiều làm chậm ứng dụng

**Dấu hiệu:** throughput giảm khi bật DEBUG hoặc TRACE, CPU/disk/network tăng.

**Nguyên nhân:** nhiều log events, format message đắt, appender đồng bộ, collector chậm hoặc async queue đầy.

**Cách xử lý:** giảm level/phạm vi, tối ưu nội dung log, kiểm soát appenders và thiết kế pipeline phù hợp.

### 27.14. Request ID sai giữa các request

**Dấu hiệu:** hai request không liên quan có cùng MDC requestId.

**Nguyên nhân:** không remove MDC khi thread được tái sử dụng, hoặc context được propagate sai qua executor.

**Cách xử lý:** dùng try-finally/MDC.putCloseable và cơ chế trace propagation chính thức theo stack.

### 27.15. Có JSON log nhưng collector parse sai

**Dấu hiệu:** hệ thống log tập trung không đọc được field hoặc một event bị tách làm nhiều bản ghi.

**Nguyên nhân:** tự nối JSON bằng String, thiếu escaping, stack trace multiline không được encoder xử lý theo schema.

**Cách xử lý:** dùng encoder phù hợp, thống nhất schema và cấu hình ingestion tương ứng.

### 27.16. Thấy nhiều provider hoặc backend trên classpath

**Dấu hiệu:** cảnh báo nhiều SLF4J providers/bindings, logger không dùng cấu hình mong muốn hoặc log bị nhân đôi.

**Nguyên nhân:** dependency graph đồng thời đưa nhiều logging implementations và bridges xung đột.

**Cách xử lý:** chọn một backend chính, loại dependency không cần thiết và xác nhận runtime classpath sau build.

## 28. Ví dụ tổng hợp: order-api có console logging và file riêng ở local

Giả sử một ứng dụng Spring Boot tên **order-api** với các yêu cầu:

- Cùng một artifact chạy được ở local và production.
- Cả hai môi trường đều có console logging.
- Ở local: log DEBUG cho code nghiệp vụ và ghi file xoay vòng.
- Ở các profile khác: console INFO, không chủ động tạo file local.
- Các dòng log có tên service và hỗ trợ MDC request ID.
- Thư mục log local có thể cấu hình từ Environment.

### 28.1. application.yml

~~~yaml
spring:
  application:
    name: order-api

app:
  logging:
    directory: logs

logging:
  level:
    root: INFO
~~~

Ví dụ có thể được bổ sung các properties deployment-specific ở bên ngoài hoặc file profile-specific. Giá trị app.logging.directory là property tự định nghĩa và sẽ được logback-spring.xml đọc qua springProperty.

### 28.2. logback-spring.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="unknown-service"/>

    <springProperty scope="context"
                    name="logDir"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [${serviceName}] [requestId=%X{requestId:-none}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="local">

        <appender name="LOCAL_FILE"
                  class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>${logDir}/order-api.log</file>

            <encoder>
                <charset>UTF-8</charset>
                <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [${serviceName}] %logger{50} - %msg%n%ex</pattern>
            </encoder>

            <rollingPolicy
                    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
                <fileNamePattern>${logDir}/order-api.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
                <maxFileSize>10MB</maxFileSize>
                <maxHistory>7</maxHistory>
                <totalSizeCap>500MB</totalSizeCap>
            </rollingPolicy>
        </appender>

        <logger name="com.example.orders" level="DEBUG"/>

        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="LOCAL_FILE"/>
        </root>
    </springProfile>

    <springProfile name="!local">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

Tư duy triển khai:

1. springProperty lấy serviceName và logDir từ Environment.
2. ConsoleAppender luôn được khai báo để có output.
3. Nhánh local mới khai báo và gắn LOCAL_FILE.
4. com.example.orders được nâng lên DEBUG ở local, các logger khác giữ mức kế thừa phù hợp.
5. Nhánh không local dùng console INFO.
6. Không có logger riêng gắn CONSOLE trùng với root, tránh nhân đôi event do additivity.

### 28.3. Chạy trên máy local

~~~bash
java -jar order-api.jar --spring.profiles.active=local
~~~

Kết quả mong đợi ở mức thiết kế:

- Các log INFO của root đi console và LOCAL_FILE.
- Logger trong com.example.orders được phép ghi DEBUG.
- File log local được rollover theo chính sách đã khai báo.

Điều này giả định process có quyền tạo/ghi thư mục logs và không có các override khác làm thay đổi logging system.

### 28.4. Chạy môi trường production

~~~bash
java -jar order-api.jar --spring.profiles.active=prod
~~~

Khi chỉ prod active, nhánh **!local** áp dụng:

- Root INFO gắn CONSOLE.
- Không khai báo LOCAL_FILE qua nhánh local.
- Log được gửi tới console để hệ thống triển khai có thể thu thập.

Trong hệ thống thực tế, cần bảo đảm profile active đúng, backend là Logback và logger levels cuối không bị property runtime khác ghi đè.

### 28.5. Chạy với tăng log level tạm thời

~~~bash
java -jar order-api.jar --spring.profiles.active=prod --logging.level.com.example.orders=DEBUG
~~~

Lệnh trên minh họa việc dùng property để bật DEBUG cho package trong một lần chạy. Khi không có Logback filters khác chặn, debug events có thể được gửi tới CONSOLE.

Nếu hệ thống có policy không cho phép DEBUG ở production, phải thực hiện kiểm soát đó ở quy trình deploy và security; một XML đơn giản không tự ngăn mọi lệnh ghi đè cấu hình.

## 29. Chọn cách cấu hình logging theo nhu cầu

| Nhu cầu | Cách phù hợp thường gặp |
|---|---|
| Thay log level của root hoặc một package | logging.level trong application.yml hoặc CLI. |
| Đổi pattern console mặc định | logging.pattern.console khi cấu hình hiện tại hỗ trợ. |
| Ghi log file cơ bản | logging.file.name/path nếu cơ chế mặc định đáp ứng. |
| File rotation phức tạp, nhiều appenders | logback-spring.xml với RollingFileAppender/filters. |
| Điều kiện theo Spring profile | springProfile trong logback-spring.xml. |
| Lấy app name hoặc đường dẫn từ Environment | springProperty trong logback-spring.xml. |
| Bật DEBUG tạm thời khi runtime | Actuator loggers có bảo mật, nếu hỗ trợ. |
| Dùng Log4j2 | Chọn đúng starter/backend và log4j2-spring.xml. |
| Truy vấn log theo trường trong nhiều replica | Structured logging/encoder thống nhất với collector. |
| Truy vết một request qua nhiều service | Micrometer Tracing/MDC với context propagation đúng. |
| Audit event không được mất | Hệ thống audit/outbox bền vững, không chỉ một logger thông thường. |

Không có một mẫu XML tốt nhất cho tất cả ứng dụng. Lựa chọn phụ thuộc vào logging backend, cách triển khai, hạ tầng quan sát và yêu cầu bảo mật/retention.

## 30. Những hiểu nhầm thường gặp

**“Spring Boot luôn dùng Logback.”**  
Không. Logback là lựa chọn mặc định phổ biến qua starter logging, nhưng ứng dụng có thể chọn backend khác.

**“SLF4J và Logback là cùng một thư viện.”**  
Không. SLF4J là API/facade; Logback là một implementation.

**“Có logback-spring.xml là mọi mức logging.level sẽ bị bỏ qua.”**  
Không nhất thiết. Spring Boot còn áp dụng log levels từ Environment tùy quá trình khởi tạo. Tốt nhất tránh cấu hình mâu thuẫn và kiểm tra effective level.

**“logback.xml và logback-spring.xml tương đương tuyệt đối.”**  
Không. logback-spring.xml được Boot hỗ trợ tích hợp Spring extensions; logback.xml có thể được Logback native parser tải sớm.

**“springProfile trong XML sẽ kích hoạt profile.”**  
Không. Nó chỉ áp dụng một nhánh khi profile đã phù hợp.

**“springProperty có thể inject bất kỳ Spring bean.”**  
Không. Nó đọc property từ Spring Environment trong giai đoạn logging initialization, không phải dependency injection như @Autowired.

**“Gắn hai appenders vào root luôn gây log trùng.”**  
Không. Root ghi event tới hai destination là hành vi chủ động. Log trùng trong cùng destination thường liên quan appender được gọi qua nhiều đường hoặc pipeline thu thập trùng.

**“Tắt additivity luôn là cách tốt nhất.”**  
Không. Nếu logger không có appender riêng, event có thể không còn đi đến output nào.

**“FileAppender tự xoay vòng.”**  
Không. Muốn rolling cần appender/policy phù hợp.

**“maxHistory=14 nghĩa chắc chắn có đúng 14 file.”**  
Không. Nó quản lý các kỳ lịch sử theo policy; một ngày có thể có nhiều archive do size-based rollover.

**“AsyncAppender bảo đảm không mất log.”**  
Không. Queue overflow, discard policy hoặc shutdown đột ngột vẫn có thể làm mất event.

**“Đổi log level qua Actuator sẽ sửa file cấu hình trong Git.”**  
Không. Runtime change thường chỉ áp dụng cho process hiện tại.

**“Logback configuration là Spring bean nên có thể @Autowired trong XML.”**  
Không. Logging system được khởi tạo sớm, không đồng nghĩa các Logback components tham gia IoC theo cách của application beans.

**“Đặt scan=true là luôn tự reload được springProfile.”**  
Không. Native Logback scanning không tương thích với Spring Boot Logback extensions.

**“Có TRACE sẽ luôn dễ chẩn đoán hơn.”**  
Không. TRACE toàn hệ thống có thể gây nhiễu, tăng tải và lộ dữ liệu.

**“Log text là audit record có bảo đảm lưu giữ.”**  
Không. Audit có yêu cầu không mất dữ liệu cần thiết kế một cơ chế bền vững hơn.

## Ghi nhớ cốt lõi

Trong ứng dụng Spring Boot dùng Logback, **logback-spring.xml** là file cấu hình phù hợp khi cần điều khiển sâu appenders, encoders, patterns, logger hierarchy, rolling policy và cấu hình theo Spring Environment. **springProfile** chọn nhánh cấu hình theo active profiles; **springProperty** đọc giá trị từ Environment. Hai phần mở rộng này là lý do quan trọng để ưu tiên logback-spring.xml thay cho logback.xml trong ứng dụng Boot.

Khi nhu cầu chỉ là chỉnh mức log, hãy bắt đầu từ **logging.level**. Khi cần nhiều destination, rotation, filter hoặc format đặc thù, hãy dùng XML phù hợp với **logging system thực tế**. Logback XML không thể thay thế Log4j2 XML; code nghiệp vụ nên dùng SLF4J để ít phụ thuộc backend.

Cuối cùng, logging đúng không chỉ là “in được một dòng”. Cần xác minh effective logger level, appender route/additivity, destination, charset, retention, correlation ID và dữ liệu được phép ghi. Với hệ thống production, hãy bảo vệ quyền truy cập logs và Actuator, kiểm soát DEBUG/TRACE, và để logging pipeline phù hợp với cách ứng dụng được triển khai.
