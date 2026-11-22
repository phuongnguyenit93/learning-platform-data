# Tách log theo package trong Java: Logger hierarchy, routing và kiểm soát trùng lặp

## 1. Mục tiêu và phạm vi

Trong một ứng dụng Java, các package thường đại diện cho những nhóm chức năng như đặt hàng, thanh toán, tích hợp bên ngoài và tác vụ nền. **Tách log theo package** là cách dùng tên logger có cấu trúc để áp dụng **mức ghi log, bộ lọc hoặc đích ghi khác nhau** cho từng nhóm đó, giúp theo dõi đúng thành phần mà không làm tăng nhiễu trên toàn hệ thống.

Ví dụ, bạn có thể muốn:

- `com.acme.orders` ghi DEBUG khi điều tra nghiệp vụ đặt hàng, còn phần lớn ứng dụng chỉ ghi INFO.
- `com.acme.payments` ghi sang một file hoặc pipeline riêng để dễ kiểm soát quyền truy cập và thời gian lưu giữ.
- `com.acme.integration` có mức WARN nhằm giảm log từ các adapter nhiều lưu lượng.
- Các package còn lại vẫn đi qua appender chung để duy trì tín hiệu vận hành.

Sau bài này, bạn sẽ biết phân biệt **tách theo mức (level)** và **tách theo đích (routing)**; hiểu kế thừa logger, appender additivity, filter và phạm vi của từng cấu hình; làm được ví dụ Java 17 chỉ dùng JUL; cấu hình Logback, Log4j2 và Spring Boot; đồng thời kiểm thử để tránh log trùng, log mất hoặc bị gửi nhầm nơi.

> Trọng tâm là **tên logger tương ứng với package**, không phải phân vùng dữ liệu bằng cách đọc chuỗi tên package từ message rồi tự phân loại. Chọn tên logger phù hợp giúp framework định tuyến trước khi formatter/sink xử lý event.

## 2. Package và logger name liên hệ với nhau như thế nào?

Trong Java, package là không gian tên khai báo trong mã nguồn:

~~~java
package com.acme.orders;

public class OrderService {
    // ...
}
~~~

Với logger được đặt tên theo class đầy đủ, tên logger thường là `com.acme.orders.OrderService`. Ví dụ SLF4J:

~~~java
// Minh họa trong ứng dụng đã có SLF4J và backend.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

Cách đặt tên này cho phép cấu hình `com.acme.orders` áp dụng cho logger bên trong `com.acme.orders.OrderService` và các package con như `com.acme.orders.workflow`.

Hệ thống logging thường tổ chức logger theo **các đoạn tên phân tách bằng dấu chấm**, ví dụ:

~~~text
root
└── com
    └── com.acme
        ├── com.acme.orders
        │   ├── com.acme.orders.OrderService
        │   └── com.acme.orders.workflow.CheckoutFlow
        ├── com.acme.payments
        │   └── com.acme.payments.PaymentService
        └── com.acme.integration
            └── com.acme.integration.HttpAdapter
~~~

Sơ đồ thể hiện **quan hệ tên logic**. Backend không nhất thiết phải tạo một đối tượng Logger vật lý cho từng nút trung gian; cơ chế tìm cha hoặc cấu hình phù hợp có thể dùng logger/config gần nhất có tồn tại.

**Lưu ý:** `com.acme.order` và `com.acme.orders` không phải cùng package, và cấu hình `com.acme.order` không tự động có nghĩa “mọi logger có tiền tố ký tự com.acme.order”. Hãy kiểm tra đúng các đoạn tên theo dấu chấm. Ngoài ra, logger **có thể được đặt tên tùy ý**; nếu code dùng `getLogger("business")` thì cấu hình package `com.acme.orders` không điều khiển logger đó. Vì vậy nên có quy ước lấy logger theo class hoặc package.

## 3. Ba loại “tách log” phải phân biệt

| Mục đích | Thay đổi điều gì? | Ví dụ | Cần gì? |
| --- | --- | --- | --- |
| **Điều chỉnh mức theo package** | Sự kiện DEBUG/INFO/WARN nào đủ điều kiện phát ra. | DEBUG cho `com.acme.orders`, INFO cho phần còn lại. | Logger level; thường dùng property/YAML hoặc XML. |
| **Định tuyến theo package** | Event đủ điều kiện sẽ đến appender/handler nào. | Orders vào `orders.log`, Payments vào `payments.log`. | Cấu hình appender/handler, logger attachment, additivity. |
| **Phân loại ở nơi thu thập** | Gắn nhãn/filter/search sau khi event đã được gửi đi. | Dashboard lọc `logger_name` bắt đầu với `com.acme.orders`. | Structured log, collector và quy tắc truy vấn. |

Đặt `logging.level.com.acme.orders=DEBUG` **không tự tạo** `orders.log`. Cấu hình appender riêng cũng **không bảo đảm** có dòng DEBUG nếu level hiện hành vẫn là INFO. Ngược lại, collector có thể tạo nhiều index từ cùng stream log; đó là **routing ở tầng collector**, khác với phân luồng ngay trong JVM.

### Một luồng xử lý event điển hình

~~~text
Lời gọi logger (theo tên class / package)
                 │
                 ▼
     Level của logger có cho phép?
                 │
          ┌──────┴──────┐
         Không          Có
          │             │
        Bỏ qua      Event được tạo
                        │
                        ▼
             Logger filter / backend rules
                        │
                        ▼
             Appender/Handler được chọn
                        │
                        ▼
           Appender filter, encoder, sink
                        │
                        ▼
           Console / file / collector
~~~

Đây là mô hình khái niệm: Logback, Log4j2 và JUL có trình tự và thuật ngữ riêng. **Không giả định level ở logger cha luôn được kiểm tra lại lần nữa trên mọi bước chuyển lên cha.** Trong Logback/Log4j2, quy tắc kế thừa appender và quy tắc xác định effective level là những cơ chế khác nhau.

## 4. Logger hierarchy và kế thừa mức log

Một ví dụ cấp độ:

~~~text
root                         INFO
com.acme.orders              DEBUG
com.acme.payments            WARN
com.acme.integration         (không đặt, kế thừa INFO)
~~~

Dự kiến khi không có bộ lọc khác:

| Logger phát sự kiện | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- |
| `com.acme.orders.OrderService` | Có | Có | Có | Có |
| `com.acme.payments.PaymentService` | Không | Không | Có | Có |
| `com.acme.integration.HttpAdapter` | Không | Có | Có | Có |

**Effective level** là mức được áp dụng cho logger sau khi xét cấu hình trực tiếp và kế thừa từ tổ tiên phù hợp. Một logger con không có level riêng thường dùng level của cha gần nhất đã được cấu hình.

Một package chứa nhiều class **không cần** mỗi class có một dòng cấu hình riêng. Đó là lý do quy tắc cấp package dễ duy trì hơn cấu hình chi tiết từng class, trừ khi cần điều tra một thành phần rất cụ thể.

Điểm cần nhớ:

- Kế thừa **level** quyết định log event có được tạo/chấp nhận ở logger nguồn.
- Kế thừa **appender** quyết định event đã được chấp nhận sẽ được gửi đến những đích nào.
- **Appender filter/threshold** có thể tiếp tục loại event, nên việc `DEBUG` được logger chấp nhận không đồng nghĩa tất cả sink đều ghi dòng DEBUG.
- Logger tên package rộng như `com.acme` có thể ảnh hưởng hàng trăm class; ưu tiên phạm vi hẹp khi tăng verbosity.

## 5. Additivity: nguyên nhân phổ biến của log trùng

Trong Logback và Log4j2, **additivity** là việc event của logger con được gửi tới appender của chính nó **và** các appender trên nhánh cha. Mặc định của các logger thông dụng là `true`.

Giả sử:

~~~text
root                          -> CONSOLE
com.acme.orders               -> ORDERS_FILE, additivity=true
com.acme.orders.OrderService  -> ghi INFO
~~~

Event từ `OrderService` sẽ đi tới `ORDERS_FILE` **và** `CONSOLE`, vì event còn đi qua root. Đây có thể là chủ ý nếu muốn log orders xuất hiện trong log tổng và file chuyên biệt.

Nếu mục tiêu là **chỉ ghi orders vào file riêng**, ta đặt:

~~~text
root                          -> CONSOLE
com.acme.orders               -> ORDERS_FILE, additivity=false
com.acme.orders.OrderService  -> ORDERS_FILE
~~~

Event đi đến appenders thuộc nhánh orders rồi **dừng trước root**. `additivity=false` trên một logger có **không có appender thích hợp** có thể khiến sự kiện không tới đích nào; phải kiểm tra appender trước khi chặn kế thừa.

### Khi nào log thật sự bị trùng?

- **Một dòng ở console và một dòng trong file riêng:** có thể là phân phối **một event đến hai đích mong muốn**.
- **Hai dòng giống hệt trong cùng console/file:** thường là gắn cùng đích ở nhiều cấp logger, additivity hoặc hai pipeline cùng thu thập/ghi một bản ghi.
- **Nhiều record cùng message từ hai lời gọi thực sự:** đây không nhất thiết là lỗi routing; cần kiểm tra mã gọi logger và trace/correlation ID.

Đừng sửa tình huống log trùng bằng cách tắt root logger toàn hệ thống. Hãy vẽ sơ đồ appender và kiểm tra đường đi của **một event cụ thể**.

## 6. Java 17 chạy độc lập: định tuyến package vào hai file bằng JUL

`java.util.logging` (JUL) có sẵn trong JDK 17, nên có thể học cơ chế ngay mà không cài Logback/Log4j2. JUL dùng các **Logger** có tên phân cấp theo dấu chấm và **Handler** để ghi log. Khi một logger có `setUseParentHandlers(false)`, record của nó sẽ không tiếp tục được chuyển tới handler của logger cha.

Chương trình sau:

1. Tạo logger cấp package `academy.orders` và `academy.payments`.
2. Gắn `FileHandler` riêng cho mỗi package.
3. Cho phép `FINE` ở orders, nhưng chỉ từ `INFO` ở payments.
4. Dùng `setUseParentHandlers(false)` để không gửi thêm một bản sao lên root handler.
5. Đóng handler trước khi đọc file để kết quả có thể kiểm chứng.
6. Ghi message ASCII và định dạng cố định để stdout không bị ảnh hưởng bởi timestamp/locale.

Lưu thành file **PackageRoutingDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PackageRoutingDemo {

    private static FileHandler createFileHandler(String file)
            throws IOException {
        FileHandler handler = new FileHandler(file, false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + record.getLoggerName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        return handler;
    }

    private static void configurePackage(
            Logger packageLogger, Level level, Handler handler) {
        packageLogger.setLevel(level);
        packageLogger.setUseParentHandlers(false);
        packageLogger.addHandler(handler);
    }

    private static void printFile(String file) throws IOException {
        System.out.println(file + ":");
        for (String line : Files.readAllLines(
                Path.of(file), StandardCharsets.UTF_8)) {
            System.out.println(line);
        }
    }

    public static void main(String[] args) throws Exception {
        // Giu strong reference den hai logger package trong main.
        Logger ordersPackage = Logger.getLogger("academy.orders");
        Logger paymentsPackage = Logger.getLogger("academy.payments");

        FileHandler ordersFile = createFileHandler("orders.log");
        FileHandler paymentsFile = createFileHandler("payments.log");

        try {
            configurePackage(ordersPackage, Level.FINE, ordersFile);
            configurePackage(paymentsPackage, Level.INFO, paymentsFile);

            // Logger theo ten class duoc tao ben duoi hai package.
            Logger orders = Logger.getLogger(
                    "academy.orders.OrderService");
            Logger payments = Logger.getLogger(
                    "academy.payments.PaymentService");

            orders.fine("order-debug");
            orders.info("order-created");
            payments.fine("payment-debug");
            payments.warning("payment-delayed");
        } finally {
            ordersPackage.removeHandler(ordersFile);
            paymentsPackage.removeHandler(paymentsFile);
            ordersFile.close();
            paymentsFile.close();
        }

        printFile("orders.log");
        printFile("payments.log");
    }
}
~~~

Biên dịch và chạy trong thư mục **có quyền ghi file**, với JDK 17 trở lên:

~~~bash
javac PackageRoutingDemo.java
java PackageRoutingDemo
~~~

**stdout dự kiến**, khi chạy một instance độc lập và các đường dẫn file không bị process khác chiếm:

~~~text
orders.log:
FINE academy.orders.OrderService order-debug
INFO academy.orders.OrderService order-created
payments.log:
WARNING academy.payments.PaymentService payment-delayed
~~~

Các file được tạo sau khi chạy chứa tương ứng:

**orders.log**

~~~text
FINE academy.orders.OrderService order-debug
INFO academy.orders.OrderService order-created
~~~

**payments.log**

~~~text
WARNING academy.payments.PaymentService payment-delayed
~~~

Dòng `payment-debug` không xuất hiện vì logger `academy.payments` chặn `FINE` trước khi nó tới FileHandler. Các logger con kế thừa mức từ logger package tương ứng. `setUseParentHandlers(false)` ngăn việc tiếp tục chuyển record lên root handler; nhờ đó demo không tự in thêm log qua console handler mặc định của JUL.

**Những điều cần lưu ý khi áp dụng:**

- `FileHandler` cần quyền ghi thư mục và có thể tạo file `.lck` trong lúc chạy. Chương trình trên dùng `append=false` để kết quả mỗi lần chạy không trộn với log cũ; **không dùng cách này cho production log cần giữ lịch sử**.
- FileHandler có thể dùng quy tắc đặt tên khác khi tên file bị khóa bởi instance khác. Vì vậy đầu ra mẫu giả định không có tiến trình khác đang giữ cùng file.
- Ví dụ cấu hình logging bằng code lúc khởi tạo để dễ học. Production nên dùng cơ chế cấu hình của framework/backend, không thay đổi logger toàn cục tùy tiện khi các request đang chạy.
- JUL có **Logger level** và **Handler level**. Nếu handler được đặt ngưỡng `WARNING`, thì dù logger đã nhận `FINE`, handler vẫn không xuất sự kiện `FINE`. Ở demo handler đặt `ALL` để ngưỡng do package logger quyết định.
- `FileHandler` đóng ở `finally` để giải phóng tài nguyên. Nếu một sink lỗi I/O, phải quan sát cơ chế `ErrorManager`/hạ tầng và cân nhắc khả năng thất lạc sự kiện; ví dụ không nhằm bảo đảm độ bền dữ liệu.
- Trong ứng dụng thực, logger tên theo class `academy.orders.OrderService` là **quy ước**, không phải yêu cầu Java compiler phải có class/package tên đó trong chính file demo.

## 7. Cấu hình Logback: package riêng một file

Logback Classic thường được dùng phía sau SLF4J. Một cấu hình `logback.xml` có thể đặt logger theo package và gắn appender tương ứng.

Ví dụ đặt tại **src/main/resources/logback.xml** trong ứng dụng sử dụng Logback:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDERS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="PAYMENTS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/payments.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.acme.orders" level="DEBUG" additivity="false">
        <appender-ref ref="ORDERS_FILE"/>
    </logger>

    <logger name="com.acme.payments" level="INFO" additivity="false">
        <appender-ref ref="PAYMENTS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Kết quả định tuyến theo cấu hình trên:**

| Logger | Đường đi | Mức |
| --- | --- | --- |
| `com.acme.orders.OrderService` | Chỉ `ORDERS_FILE` → `logs/orders.log` | DEBUG trở lên |
| `com.acme.payments.PaymentService` | Chỉ `PAYMENTS_FILE` → `logs/payments.log` | INFO trở lên |
| `com.acme.inventory.StockService` | Kế thừa root → `CONSOLE` | INFO trở lên |

Vì hai logger package đặt `additivity=false`, log từ nhánh orders và payments không còn tiếp tục đi lên `CONSOLE` ở root. Điều này **có thể làm mất khả năng quan sát trên stdout của container** nếu hệ thống chỉ thu log từ stdout/stderr.

Nếu yêu cầu vận hành là **vừa có log tổng ở console vừa có file riêng**, có thể thêm `<appender-ref ref="CONSOLE"/>` vào mỗi logger package đang `additivity="false"`. Như vậy mỗi event sẽ tới console và file riêng **mỗi nơi một bản**, không cần mở lại additivity. Một cách khác là dùng `additivity=true` với file appender riêng và root console, miễn là không gắn trùng console appender ở logger con.

Đây là **mẫu học tập**, chưa có rolling policy. Production cần xem xét **RollingFileAppender**, rollover, retention, disk quota, quyền ghi và chiến lược collector. Đường dẫn `logs/` là tương đối với working directory hiện hành; trong container/Kubernetes hãy xác định volume, persistence và cách thu thập log trước khi dùng file riêng.

### 7.1. Khi chỉ cần mức DEBUG theo package

Nếu toàn bộ log vẫn phải đi tới một appender console chung, cấu hình tối thiểu chỉ cần:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.acme.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Logger orders kế thừa appender CONSOLE từ root nhờ additivity mặc định `true`, nhưng dùng ngưỡng DEBUG. Các package khác kế thừa INFO từ root. **Đây là chỉnh level theo package, chưa tách sink theo package.**

### 7.2. Root INFO có ngăn DEBUG từ orders ghi lên root appender không?

Trong cấu hình Logback, một event DEBUG đã được **logger `com.acme.orders` cho phép** có thể đến appender của root nếu additivity cho phép. Mức root INFO **không được xem như một bộ lọc ngưỡng thứ hai** chỉ vì appender gắn ở root. Nếu muốn appender chỉ nhận INFO trở lên, đặt filter/threshold phù hợp **trên chính appender**. Đây là điểm thường gây nhầm lẫn khi bật DEBUG cho package con.

## 8. Log4j2: định tuyến bằng LoggerConfig và AppenderRef

Log4j2 sử dụng `LoggerConfig` có tên phân cấp, level, additivity và tham chiếu đến appender. Ví dụ **log4j2.xml** dành cho ứng dụng đã có Log4j Core:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>

        <File name="ORDERS_FILE" fileName="logs/orders.log" append="true">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </File>

        <File name="PAYMENTS_FILE" fileName="logs/payments.log" append="true">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="com.acme.orders" level="DEBUG" additivity="false">
            <AppenderRef ref="ORDERS_FILE"/>
        </Logger>

        <Logger name="com.acme.payments" level="INFO" additivity="false">
            <AppenderRef ref="PAYMENTS_FILE"/>
        </Logger>

        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Ý nghĩa tương tự Logback: logger khớp package orders và các class con sẽ dùng ORDERS_FILE, logger nhánh payments dùng PAYMENTS_FILE; những logger khác dùng root CONSOLE. Từng LoggerConfig có thể dùng nhiều AppenderRef; `additivity=false` ngăn gửi event lên appender ở cấu hình cha.

**Lưu ý khi chuyển thư viện:** Log4j 1.x và Log4j2 có cú pháp/configuration khác; đừng sao chép config Logback hoặc Log4j 1.x rồi kỳ vọng Log4j2 tự hiểu. Cần đảm bảo backend thực tế, dependency và đường dẫn config đã được nạp.

Muốn log orders xuất hiện ở cả file riêng và console chung, cần thiết kế rõ appender references và additivity như với Logback. Với Log4j2, filter có thể nằm ở logger, appender hoặc AppenderRef; phải xem **tất cả bộ lọc** khi thấy mức log không đúng dự kiến.

## 9. Spring Boot: mức theo package khác với routing theo package

Trong ứng dụng Spring Boot dùng starter logging mặc định, các mức logger thường được điều khiển trực tiếp qua **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.acme.orders=DEBUG
logging.level.com.acme.payments=WARN
logging.level.com.acme.integration=ERROR
~~~

Hoặc **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.acme.orders: DEBUG
    com.acme.payments: WARN
    com.acme.integration: ERROR
~~~

Đây là cách thay **verbosity theo package**. Nó **không tự sinh** ba file hay ba collector khác nhau. Nếu muốn routing theo appender, cấu hình backend Logback/Log4j2, hoặc phân luồng theo trường logger name tại collector.

Khi sử dụng Logback trong Boot và cần kiểm soát routing sâu, đặt cấu hình ở **logback-spring.xml** để dùng cơ chế tích hợp Boot phù hợp. Nếu đã có nhiều file `application-{profile}.yml`, cần xác định các override đang active. Với Log4j2 dùng `log4j2-spring.xml` khi cần tích hợp Boot.

### Tách level theo môi trường mà không lẫn policy

Ví dụ cấu hình nền:

~~~properties
# application.properties
logging.level.root=INFO
logging.level.com.acme.orders=INFO
~~~

Cấu hình riêng cho dev:

~~~properties
# application-dev.properties
logging.level.com.acme.orders=DEBUG
~~~

Cấu hình riêng cho prod:

~~~properties
# application-prod.properties
logging.level.com.acme.orders=INFO
~~~

Đặt profile khi khởi động từ nguồn cấu hình triển khai phù hợp. Nếu process production nhận `LOGGING_LEVEL_COM_ACME_ORDERS=DEBUG` hoặc override có ưu tiên cao hơn, giá trị có hiệu lực có thể khác file prod. Hãy kiểm tra **effective config**, thay vì kết luận chỉ từ file trong repository.

Tránh bật root DEBUG trên production khi chỉ cần điều tra package orders. Bật một nhánh hẹp, giới hạn thời gian, theo dõi volume và đảm bảo message không chứa secret/PII.

### Khi một số log không tuân theo package dự kiến

- Ứng dụng dùng `LoggerFactory.getLogger("business")` thay vì tên class.
- Một thư viện bên thứ ba có logger name riêng, ví dụ `org.hibernate.SQL`, `io.netty`, `org.springframework`; nó không nằm trong package `com.acme`.
- Logging được chuyển qua bridge/provider khác với backend bạn đang chỉnh.
- Logger con hoặc package trung gian có level/additivity khác.
- Collector thay đổi hoặc rút gọn tên trường `logger_name`, nhưng backend gốc vẫn phân luồng theo tên logger thật.
- Một số framework dùng logger category có tên không trùng hoàn toàn với Java package.

Điều tra bằng **logger name thực sự được in ra ở event**, rồi đối chiếu tên trong cấu hình.

## 10. Tách theo package trong JUL bằng properties

Ngoài cấu hình programmatic, JUL có thể nhận config file với các mức cho tên logger. Ví dụ **logging.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

com.acme.orders.level=FINE
com.acme.payments.level=WARNING
~~~

Khởi động JVM với:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.acme.Main
~~~

Đây là **cú pháp minh họa cho ứng dụng đã biên dịch** `com.acme.Main` nằm trong `out`, không phải lệnh chạy riêng ví dụ phần 6.

Với cấu hình trên, mức của orders có thể nhận FINE, payments nhận từ WARNING, còn root mặc định là INFO. ConsoleHandler đặt ALL để không vô tình chặn log FINE từ orders. Nếu đặt handler tại INFO thì ngay cả logger orders có effective level FINE, record FINE vẫn có thể bị chặn tại handler.

**Định tuyến hoàn toàn riêng file theo package trong JUL** thường cần tạo/đăng ký handler và quản lý **useParentHandlers** một cách cẩn thận, hoặc dùng cơ chế cấu hình tương thích với LogManager/ứng dụng. Ví dụ phần 6 minh họa đường đi này rõ hơn việc tưởng rằng chỉ thêm `com.acme.orders.level=FINE` sẽ tự tạo `orders.log`.

## 11. Các chiến lược routing phổ biến

| Chiến lược | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| **Một console, level khác nhau theo package** | Ứng dụng container, logs tập trung, nhu cầu chủ yếu là giảm nhiễu. | Dễ vận hành; mức theo package vẫn cần điều khiển cẩn thận. |
| **Một console chung + file riêng cho package quan trọng** | Cần truy cập nhanh log cụ thể nhưng vẫn giữ log tổng. | Một event có thể ở hai sink; cần thiết kế additivity và tính phí lưu trữ. |
| **File/appender riêng hoàn toàn** | Yêu cầu access control, retention hoặc pipeline chuyên biệt. | Tắt additivity có thể làm mất log khỏi console tập trung; phải có collector riêng. |
| **Một structured stream + tách tại collector** | Nhiều package, muốn routing/retention linh hoạt ngoài JVM. | Gắn logger_name, service, environment, traceId nhất quán và bảo vệ tuyến truyền. |
| **Filter dựa trên marker/MDC ngoài package** | Nhiều loại event cắt ngang package (audit, security, business type). | Package đơn thuần có thể không đủ; cần schema và rule rõ ràng. |

Không mặc định tách file là tốt hơn. Trong hệ có container logging và collector tập trung, **một stream JSON có logger name đầy đủ** thường đơn giản hơn nhiều file bên trong container. Còn khi một nhóm event có chính sách retention/quyền truy cập đặc biệt, routing riêng có thể cần thiết. Chọn theo yêu cầu quan sát và lưu giữ, không chọn chỉ vì code có nhiều package.

### Có nên dùng package để phân luồng audit/security?

Package là cách phân vùng theo **nơi code được viết**, còn audit/security là phân loại theo **ý nghĩa sự kiện**. Một event audit có thể đến từ nhiều package; ngược lại một package có thể chứa cả log debug và audit. Nếu cần đảm bảo mọi audit event được xử lý theo chính sách riêng, thiết kế **marker, logger category chuyên dụng, structured field hoặc event pipeline riêng** sẽ đáng tin cậy hơn là chỉ dựa vào package.

## 12. Kiểm thử định tuyến để tránh log mất và log trùng

Một bảng kiểm thử hữu ích:

| Test | Bài kiểm tra | Kỳ vọng |
| --- | --- | --- |
| **Package A và B** | Ghi một event INFO ở mỗi nhánh. | Mỗi event đến đúng sink theo cấu hình, không ghi nhầm. |
| **Package con** | Ghi ở `com.acme.orders.workflow.CheckoutFlow`. | Kế thừa rule của `com.acme.orders` nếu không có override riêng. |
| **Package gần giống tên** | Ghi ở `com.acme.order` và `com.acme.orders`. | Không nhầm hai nhánh khi cấu hình theo namespace. |
| **Level thấp hơn ngưỡng** | Ghi DEBUG ở payments với ngưỡng WARN. | Event bị lọc theo policy, không xuất hiện như INFO/WARN. |
| **Additivity=true** | Gắn file ở nhánh con, console ở root. | Event có mặt ở file và console nếu đó là thiết kế chủ ý. |
| **Additivity=false** | Chặn chuyển lên root. | Event không đi tới appender root, nhưng vẫn tới appender của nhánh con. |
| **Appender không có sink** | Tắt additivity nhưng quên appender con. | Test phát hiện mất log và fail cấu hình. |
| **Sink lỗi** | File read-only, disk full hoặc collector unreachable. | Có tín hiệu lỗi và chính sách xử lý được quan sát, không âm thầm mất dữ liệu. |
| **Nhiều thread** | Log từ thread pool, nhiều request. | Level/routing theo logger name vẫn đúng; MDC/trace context phải được xử lý riêng. |
| **Thay đổi config runtime** | Reload hoặc thay level bằng API quản trị. | Effective config sau reload đúng, không thêm appender trùng. |

Khi test cần so sánh số event, dùng một **message hoặc event ID duy nhất** và xác minh cả hai phía: đúng sink có một bản, sink không liên quan có không bản. Log dạng JSON có `logger_name`, `level`, `event_id`, `trace_id` giúp kiểm tra và truy vấn rõ hơn.

### Chẩn đoán một event bị trùng hoặc mất

~~~text
Lời gọi log thật sự có chạy?
       │
       ▼
Logger name thực sự là gì?
       │
       ▼
Effective level có cho phép event?
       │
       ▼
LoggerConfig / cha gần nhất là ai?
       │
       ▼
Appender/Handler nào được gắn?
       │
       ▼
Additivity / useParentHandlers có chuyển lên root?
       │
       ▼
Filter, threshold, encoder và sink có cho qua?
       │
       ▼
Collector có nhận, đổi tên, nhân bản hoặc bỏ record?
~~~

Cần kiểm tra **cả cấu hình JVM/backend lẫn pipeline bên ngoài**. Một record bị nhân đôi tại collector có thể không phải do additivity; ngược lại Logback đã gửi hai lần cùng appender có thể làm collector trông như nhận hai event riêng.

## 13. Tương tác với MDC, trace context và async logging

**Tách theo package** dựa vào **logger name**. **MDC và trace context** chứa thông tin gắn với request hoặc luồng xử lý, dùng để tương quan log giữa các package/dịch vụ. Hai cơ chế hỗ trợ nhau nhưng không thay thế nhau:

- Một request có thể đi qua orders, inventory và payments; các record mang **cùng traceId** nhưng đi vào nhiều sink khác nhau theo logger name.
- Tách log theo package không tự propagation MDC qua `CompletableFuture`, `ExecutorService` hoặc message consumer. Nếu logger ghi từ callback không có traceId, phải sửa propagation/context.
- Nếu backend dùng **AsyncAppender/AsyncLogger**, event có thể được enqueue rồi mới được worker xuất. Hãy kiểm tra cơ chế snapshot MDC/thread name trong backend; đừng suy ra tên worker từ logger name.
- Routing một record đến nhiều sink không có nghĩa mỗi sink đã lưu record bền vững. Lỗi queue, disk hoặc collector vẫn có thể làm mất log.
- Với các event nhạy cảm, hạn chế message/fields từ đầu. Chuyển chúng sang file riêng không tự làm nội dung được mã hóa hay bảo vệ.

Ví dụ event structured sau dùng logger name để phân luồng và traceId để truy vết:

~~~json
{
  "level": "INFO",
  "logger_name": "com.acme.orders.OrderService",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "event": "order.created",
  "message": "Order created"
}
~~~

Đây là **mẫu dữ liệu**, không phải output của chương trình Java phần 6. `trace_id` phải được lấy từ tracing context hợp lệ khi có, không tự điền một giá trị cố định để làm log trông đầy đủ.

## 14. Những lỗi thường gặp

**1. Chỉ đặt level rồi nghĩ đã tách file.** Level quyết định event có được chấp nhận; muốn chia file/sink phải cấu hình appender/handler hoặc collector routing.

**2. Dùng additivity=false mà không gắn appender con.** Record có thể không tới root và cũng không có sink ở nhánh con.

**3. Gắn cùng CONSOLE appender ở nhánh con lẫn root nhưng vẫn để additivity=true.** Một event có thể được ghi hai lần qua cùng đích. Hãy chọn một đường đi rõ ràng.

**4. Hiểu sai root INFO.** Trong Logback/Log4j2, một event DEBUG được logger con cho phép có thể được appender ở root xử lý nếu additivity cho phép. Nếu cần lọc riêng ở appender, phải cấu hình threshold/filter tại appender hoặc AppenderRef thích hợp.

**5. Đặt rule package quá rộng.** Bật DEBUG cho `com.acme` trong production chỉ để chẩn đoán `com.acme.orders.payment` có thể làm tăng khối lượng log và rủi ro thông tin.

**6. Tưởng mọi logger name trùng tên package.** API cho phép tên tùy ý; logger của thư viện thứ ba có thể dùng namespace khác. Hãy quan sát tên thật trong log.

**7. Chỉ nhìn tên file mà quên quyền ghi.** Đường dẫn `logs/orders.log` phụ thuộc working directory, quyền filesystem và container volume; cấu hình đúng XML vẫn có thể không ghi được.

**8. Dùng nhiều file trong container nhưng collector chỉ đọc stdout.** Khi tắt additivity để tách file, ứng dụng có thể mất log trong dashboard trung tâm. Kiểm tra đường thu thập.

**9. Không có rotation/retention.** File riêng theo package tăng số lượng file và chi phí. Production cần quota, rotation, retention và kiểm tra disk.

**10. Dùng package để quyết định dữ liệu nào là audit.** Security/audit event có thể xuất hiện ở nhiều package, nên classification theo ý nghĩa thường cần marker/field riêng.

**11. Trộn backend.** Thay `logback.xml` không giúp gì nếu runtime thực sự dùng Log4j2, JUL hoặc SLF4J provider khác. Kiểm tra runtime classpath và bootstrap logging.

**12. Thiếu kiểm thử với package con và package tương tự.** Test một class duy nhất có thể bỏ sót logger con kế thừa sai mức hoặc nhánh khác đi nhầm sink.

## 15. Bài tập thực hành

1. Chạy `PackageRoutingDemo.java`, mở **orders.log** và **payments.log**. Giải thích tại sao `payment-debug` bị lọc trong khi `order-debug` được ghi.
2. Đổi `ordersPackage.setUseParentHandlers(false)` thành `true` trong demo. Quan sát `orders` có thể tiếp tục đi tới handler của cha/root nếu root đã có handler. So sánh stdout/stderr và file; hiểu rõ đường đi thay vì chỉ nhìn số dòng.
3. Đổi mức của `ordersPackage` từ `FINE` sang `WARNING`. Xác nhận file orders không còn `FINE` và `INFO`.
4. Trong Logback, đặt root INFO + CONSOLE và logger `com.acme.orders` DEBUG + ORDERS_FILE. Thử hai cấu hình additivity `true` và `false`, dự đoán mỗi event xuất hiện ở đích nào trước khi chạy.
5. Nếu dùng Spring Boot, đặt `logging.level.com.acme.orders=DEBUG` trong profile dev và INFO trong prod; chạy mỗi profile trong môi trường thử nghiệm, kiểm tra effective level và bảo đảm không dùng DEBUG ngoài ý muốn.
6. Bổ sung một logger `com.acme.orders.workflow.CheckoutFlow` và một logger `com.acme.order.OrderService`. Kiểm tra nhánh nào được định tuyến như orders và vì sao.
7. Thiết kế test bắt lỗi **trùng event trong một sink** bằng `event_id` duy nhất và test bắt lỗi **mất event** khi additivity=false nhưng không có appender.

## 16. Ghi nhớ

Tách log theo package là một kỹ thuật **routing và phân loại theo logger name**. Có hai quyết định khác nhau: **event nào được phát** (level/filter) và **event được chuyển đến đâu** (appender/handler, additivity, collector). Tên logger theo class giúp các quy tắc ở package bao phủ nhiều class con; additivity giúp kế thừa đích hoặc chặn tại ranh giới package. Khi thiết kế, hãy vẽ đường đi của một event, xác định số bản ghi mong muốn ở từng sink, rồi kiểm chứng cả trường hợp ngược lại: log không bị mất hay đi nhầm nơi.

### Tài liệu tham khảo chính thức

- Java SE 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Logback Architecture — Logger hierarchy và appender additivity: https://logback.qos.ch/manual/architecture.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 Architecture và appender additivity: https://logging.apache.org/log4j/2.x/manual/architecture.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html