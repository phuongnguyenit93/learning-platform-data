# Filter theo logger trong Java

## 1. Mục tiêu học tập

Trong ứng dụng Java, các thành phần khác nhau cùng phát sinh log: controller, service, repository, HTTP client, JDBC, scheduler và thư viện ngoài. Khi chỉ quan tâm log của một nhóm như `com.example.orders`, bạn cần **chọn, loại bỏ hoặc định tuyến sự kiện dựa vào tên logger** đang phát sinh record. Đây là ý nghĩa của **filter theo logger**.

Sau bài này, bạn có thể phân biệt logger name với class name và thread name; hiểu cách tên logger tạo thành một hệ phân cấp; chọn vị trí áp dụng filter phù hợp; viết ví dụ JUL chạy bằng Java 17; và cấu hình Logback/Log4j 2 để ghi log theo namespace mà không vô tình lọc nhầm hoặc làm mất log quan trọng.

Cần phân biệt ngay ba việc:

- **Lọc theo tên logger:** dựa vào `loggerName` của sự kiện, ví dụ chỉ nhận `com.example.orders.OrderService` và các logger khác trong nhóm orders.
- **Điều chỉnh level theo logger:** đặt mức DEBUG cho orders, WARN cho HTTP client. Đây là cách giới hạn mức chi tiết của event ngay từ nguồn.
- **Định tuyến tới appender/handler:** để toàn bộ log xuất console nhưng chỉ log của orders đi vào `orders.log`.

Ba việc có thể phối hợp, nhưng không tương đương nhau.

## 2. Logger name và cây namespace

Các API logging cho phép đặt tên logger. Khi dùng SLF4J, cách thường gặp là:

```java
// Đoạn minh họa, cần SLF4J và class OrderService trong ứng dụng.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

// Có thể dùng tên nghiệp vụ thay cho tên class.
org.slf4j.Logger audit =
        org.slf4j.LoggerFactory.getLogger("business.audit.orders");
```

Với `OrderService` trong package `com.example.orders`, logger theo class thường mang tên `com.example.orders.OrderService`. Một tập tên có thể là:

```text
com.example
├── com.example.orders
│   ├── com.example.orders.OrderService
│   └── com.example.orders.audit.AuditWriter
├── com.example.payments
│   └── com.example.payments.PaymentService
└── com.example.orders2
    └── com.example.orders2.LegacyService
```

Trong ví dụ này, `com.example.orders` là một namespace có các tên con phân tách bằng dấu chấm. Khi viết filter bằng chuỗi, cần phân biệt:

| Cách khớp | Kết quả |
| --- | --- |
| `name.equals("com.example.orders")` | Chỉ logger đúng tên đó |
| `name.startsWith("com.example.orders.")` | Chọn các logger con trong namespace orders |
| Ghép hai điều kiện trên | Chọn chính namespace và descendants |
| `name.startsWith("com.example.orders")` | **Sai nếu cần namespace chính xác**: còn chọn cả `orders2` |

Hàm kiểm tra tên tương ứng:

```java
static boolean belongsTo(String loggerName, String namespace) {
    return loggerName != null
            && (loggerName.equals(namespace)
                || loggerName.startsWith(namespace + "."));
}
```

Tên logger không bắt buộc trùng với class hay package. Ứng dụng có thể đặt `business.audit.orders` trong mã ở package khác. Khi đó filter theo tên vẫn hoạt động, còn giả định “filter theo package của class” có thể sai. Luôn kiểm tra tên đang ghi trong log thực tế.

Không nhầm **logger name** với **thread name**. Một logger `com.example.orders.OrderService` có thể được hàng chục thread gọi; ngược lại, một thread xử lý request có thể ghi qua nhiều logger.

## 3. Sự kiện bị lọc ở đâu?

```text
logger.info("Order accepted")
           |
           v
  Kiểm tra level của logger
           |  Có thể từ chối event trước khi tạo/ghi
           v
  Filter tại logger/context (nếu có)
           |
           v
  Chuyển đến handler/appender qua logger hierarchy
           |
           +---- CONSOLE: nhận nhiều namespace
           |
           +---- ORDERS_FILE: filter theo logger name
           |
           v
  Formatter/Encoder -> stdout, file hoặc collector
```

| Vị trí | Ví dụ | Phạm vi |
| --- | --- | --- |
| Level trên logger | DEBUG cho `com.example.orders` | Điều chỉnh mức sự kiện do logger/descendants tạo theo cơ chế kế thừa |
| Filter tại logger | JUL `Logger.setFilter(Filter)` | Có thể loại record trực tiếp khi logger được gọi |
| Filter sớm ở logging context | Logback `TurboFilter` | Can thiệp ở mức context trước khi event được xuất ra appender |
| Filter tại handler/appender | JUL `Handler.setFilter`, Logback `Filter<ILoggingEvent>` | Chỉ tác động lên một đường ghi; appender khác có thể vẫn ghi |
| Định tuyến cấu hình | Log4j 2 `LoggerConfig`, Logback logger/appender refs | Chọn sink nhận event theo logger name/hierarchy |
| Truy vấn sau thu thập | Tìm theo trường `logger_name` | Chỉ lọc các bản ghi đã lưu; không giảm log tạo tại ứng dụng |

Một filter ở appender **không hồi sinh** log đã bị logger level loại. Ngược lại, một logger cho phép INFO cũng không có nghĩa INFO chắc chắn tới file: appender có thể đặt threshold WARN, từ chối bằng filter hoặc gặp lỗi I/O.

Khi thiết kế, hãy hỏi: “Tôi muốn **ngăn sinh event**, **chỉ thay đổi đích ghi**, hay **tìm kiếm sau khi thu thập**?” Câu trả lời xác định vị trí phù hợp để đặt điều kiện.

## 4. Ví dụ Java 17 độc lập với java.util.logging

Ví dụ sau sử dụng JUL có sẵn trong JDK. Ta gắn một `Handler` tự viết lên logger cha `lesson` rồi dùng `Handler.setFilter` để **chỉ in event có logger name là `lesson.orders` hoặc thuộc namespace `lesson.orders.`**.

Ngoài ra, ta đặt một filter trực tiếp lên logger `lesson.orders` để thấy rõ sự khác nhau giữa filter tại logger phát sinh và filter tại handler chung. Ví dụ không cần Maven, Gradle hoặc thư viện ngoài.

Tạo tệp `LoggerNameFilterDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerNameFilterDemo {
    private static boolean belongsTo(String name, String namespace) {
        return name != null
                && (name.equals(namespace)
                    || name.startsWith(namespace + "."));
    }

    public static void main(String[] args) {
        Logger group = Logger.getLogger("lesson");
        group.setLevel(Level.ALL);
        group.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.printf("%s | %s | %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        record.getMessage());
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        output.setFilter(record ->
                belongsTo(record.getLoggerName(), "lesson.orders"));
        group.addHandler(output);

        try {
            Logger orders = Logger.getLogger("lesson.orders");
            Logger audit = Logger.getLogger("lesson.orders.audit");
            Logger orders2 = Logger.getLogger("lesson.orders2");
            Logger payments = Logger.getLogger("lesson.payments");

            orders.setLevel(null);
            audit.setLevel(null);
            orders2.setLevel(null);
            payments.setLevel(null);

            orders.setFilter(record ->
                    !"DROP_AT_LOGGER".equals(record.getMessage()));

            orders.info("order-accepted");
            orders.info("DROP_AT_LOGGER");
            audit.warning("audit-recorded");
            orders2.severe("wrong-prefix");
            payments.info("payment-approved");
        } finally {
            group.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

```bash
javac LoggerNameFilterDemo.java
java LoggerNameFilterDemo
```

Stdout **chính xác** khi chạy trong một JVM mới, không có cấu hình ngoài can thiệp vào namespace `lesson`:

```text
INFO | lesson.orders | order-accepted
WARNING | lesson.orders.audit | audit-recorded
```

### Vì sao chỉ có hai dòng?

1. `group.setLevel(Level.ALL)` cho phép các logger con kế thừa mức không chặn sự kiện. `group.setUseParentHandlers(false)` tránh chuyển record lên root handler mặc định và tạo thêm log có timestamp trên `stderr`.
2. `orders.info("order-accepted")` được logger chấp nhận. Tên `lesson.orders` khớp điều kiện ở handler nên được in.
3. `orders.info("DROP_AT_LOGGER")` bị filter **đặt trên chính logger orders** từ chối. Record không tới handler.
4. `audit.warning("audit-recorded")` xuất phát từ logger con `lesson.orders.audit`. Handler xét tên và cho phép. Filter ở logger cha `lesson.orders` **không tự được gọi lại** khi event do logger con phát ra chuyển tiếp qua handlers cha.
5. `orders2.severe("wrong-prefix")` bị handler loại dù level SEVERE cao, vì `lesson.orders2` **không** khớp namespace `lesson.orders.`.
6. `payments.info("payment-approved")` bị handler loại do tên ở namespace khác.
7. `output.publish` gọi `isLoggable(record)`, kiểm tra level và filter của handler. `finally` gỡ/đóng handler do ví dụ tự tạo.

JUL `ConsoleHandler` mặc định thường dùng formatter kèm thời gian và in ra `stderr`. Ví dụ chủ động dùng handler in `System.out`, không thêm timestamp, để kết quả chạy có thể đối chiếu chính xác.

**Giới hạn:** ví dụ dùng handler đồng bộ, xử lý log từng event. Nó minh họa filter và route, không thay thế hệ thống logging đầy đủ với rotation, async queue hoặc collector. Nếu chạy trong ứng dụng đã có logger/handler được cấu hình trên cùng namespace, kết quả có thể khác; hãy kiểm tra trạng thái runtime.

## 5. Hai loại Filter của JUL có hành vi khác nhau

### Filter trên logger

```java
// Đoạn tích hợp trong ứng dụng có biến logger.
logger.setFilter(record ->
        !record.getMessage().startsWith("internal-"));
```

`Logger.setFilter` nhận một `java.util.logging.Filter`. Hàm `isLoggable(LogRecord)` của filter trả về `true` để cho record tiếp tục hoặc `false` để loại. Logger level cũng được kiểm tra: nếu level đã từ chối, filter không làm event được ghi lại.

Điểm cần nhớ: filter gắn ở logger **không phải một luật kế thừa tự động cho mọi logger con**. Theo cơ chế JUL, khi logger con phát event và chuyển event lên handler của tổ tiên, parent logger filter không được đánh giá lại chỉ vì event đi qua. Vì vậy, để lọc một nhóm logger trên cùng đích xuất, thường dùng filter của **handler chung**.

Ngoài ra, `setFilter` là thao tác thay đổi trạng thái runtime. Nếu hai thành phần cùng gọi phương thức này trên cùng logger, lời gọi sau có thể thay thế filter trước. Không ghi đè filter mà framework/thư viện đã quản lý nếu chưa xác định ownership.

### Filter trên handler

```java
// Đoạn tích hợp: handler do ứng dụng sở hữu.
handler.setFilter(record -> {
    String name = record.getLoggerName();
    return name != null
            && (name.equals("com.example.orders")
                || name.startsWith("com.example.orders."));
});
```

Một handler có thể nhận record từ nhiều logger thông qua hệ phân cấp và cờ `useParentHandlers`. Filter trên handler xét mọi record mà handler thực sự nhận, giúp tạo file chỉ chứa một namespace mà không bắt các logger khác ngừng phát sự kiện.

Tuy nhiên, cần đủ ba điều kiện:
- Logger cho phép tạo record theo effective level và filter tại nguồn.
- Record có đường đi tới handler (không bị cắt bởi `useParentHandlers=false` ở một điểm liên quan).
- Handler cho phép record theo level và filter của chính nó.

Với JUL, `Logger.isLoggable(Level.INFO)` chỉ phản ánh khả năng chấp nhận ở logger; nó không xác nhận handler hoặc hệ thống ghi cuối đã chấp nhận record.

## 6. Logback: filter theo tên tại appender

Khi dùng **SLF4J + Logback Classic**, ứng dụng thường có một logger theo tên class, level kế thừa và nhiều appender. Nếu mục tiêu là **console nhận mọi module nhưng `orders.log` chỉ chứa orders**, có thể đặt filter theo logger name trực tiếp trên file appender.

Ví dụ phần cấu hình `logback.xml`, yêu cầu class `com.example.logging.OrdersOnlyFilter` được biên dịch và nằm trên classpath:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDERS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <filter class="com.example.logging.OrdersOnlyFilter"/>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="ORDERS_FILE"/>
    </root>
</configuration>
```

Class filter cần thêm vào dự án Java đang sử dụng Logback Classic:

```java
package com.example.logging;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class OrdersOnlyFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        String name = event.getLoggerName();
        boolean matches = name != null
                && (name.equals("com.example.orders")
                    || name.startsWith("com.example.orders."));
        return matches ? FilterReply.NEUTRAL : FilterReply.DENY;
    }
}
```

Đây là **đoạn tích hợp** cần Logback, không phải chương trình chỉ dùng JDK. Phần XML và lớp filter phải được đặt ở đúng tài nguyên/source của ứng dụng, và đường dẫn file cần có quyền ghi thích hợp.

**Cách hoạt động:**
- `DENY` loại event **ở ORDERS_FILE**. Event đó vẫn có thể được ghi ở CONSOLE.
- `NEUTRAL` không chủ động chặn; các filter khác và logic appender tiếp tục quyết định. Không tùy tiện thay bằng `ACCEPT`, vì ACCEPT có thể khiến các filter tiếp theo không còn được hỏi.
- Logger `com.example.orders` có mức DEBUG. Logger trong namespace này nếu không tự khai báo level khác sẽ dùng mức kế thừa tương ứng.
- Root INFO không có nghĩa DEBUG phát sinh từ logger orders sẽ bị từ chối lần hai lúc event đi qua root appender. Trong Logback, event đã được logger con tạo có thể truyền tới appender tổ tiên qua **additivity**.
- File appender không thấy event bị từ chối ngay ở logger level, dù filter ở file sẽ cho phép tên đó.

### Khi nào nên dùng TurboFilter?

Logback có `TurboFilter` để quyết định sớm hơn, trước khi tạo đầy đủ log event, dựa trên logger name, level, marker hoặc nội dung. Nó có phạm vi **context-wide**, nên phù hợp khi cần áp một luật xuyên các logger, nhưng có thể chặn cả console và file. Chỉ chọn TurboFilter khi cần loại từ nguồn và đã đánh giá ảnh hưởng tới những log quan trọng.

Để **lọc riêng một sink**, appender-level filter như `OrdersOnlyFilter` thường dễ kiểm soát hơn. Để **giảm mức chi tiết** từ một thư viện ồn, cấu hình logger level theo tên thường đơn giản hơn.

### Additivity và log trùng

Nếu vừa gắn CONSOLE vào `com.example.orders` vừa gắn nó vào root trong khi `additivity=true`, có thể ghi cùng event hai lần. Khi thiết kế routing chuyên biệt, cân nhắc:

```xml
<!-- Mảnh cấu hình; ORDERS_FILE đã được khai báo ở nơi khác. -->
<logger name="com.example.orders" level="DEBUG" additivity="false">
    <appender-ref ref="ORDERS_FILE"/>
</logger>
```

Đoạn này chặn chuyển event orders lên root appender. Nếu cũng muốn ghi orders ra console, phải gắn thêm CONSOLE ngay tại logger orders hoặc tổ chức lại các appender. `additivity=false` thay đổi tuyến chuyển event, **không** phải một filter theo message.

## 7. Log4j 2: routing theo LoggerConfig

Log4j 2 cho cấu hình logger theo namespace cùng appender refs. Ví dụ `log4j2.xml` dưới đây định tuyến orders tới file và console, còn các module khác chỉ tới console:

```xml
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>

        <File name="ORDERS_FILE" fileName="logs/orders.log">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %level %logger - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders"
                level="debug" additivity="false">
            <AppenderRef ref="ORDERS_FILE"/>
            <AppenderRef ref="CONSOLE"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Khi có một `LoggerConfig` phù hợp với `com.example.orders`, logger trong namespace đó có thể dùng mức DEBUG và appender refs đã nêu; `additivity=false` không chuyển event tiếp lên root. Logger khác theo root INFO và CONSOLE, trừ khi có cấu hình cụ thể hơn.

Ví dụ này dùng **routing** theo tên logger trong cấu hình hierarchy. Nếu cần một predicate phức tạp hơn trên các event của một appender, Log4j 2 cũng có các điểm gắn `Filter` vào logger configuration, appender reference hoặc appender. Filter theo message/regex không mặc nhiên xét `loggerName`; phải chọn đúng dữ liệu và API.

Khi log không xuất theo XML, kiểm tra backend thực tế. Một ứng dụng gọi SLF4J có thể đang dùng Logback và **không đọc** `log4j2.xml`. Ngược lại, Log4j 2 có thể nhận event qua bridge khi được cấu hình đúng; không suy luận backend chỉ từ câu lệnh `logger.info(...)` trong source.

## 8. SLF4J và Spring Boot: đặt level theo logger name

SLF4J là một facade/API thống nhất; nó không định nghĩa API `setFilter` phổ quát cho mọi backend. Muốn filter theo logger, cần dùng API hoặc cấu hình của backend đang thực thi.

Trong Spring Boot, có thể đặt level theo tên logger bằng properties:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    com.example.payments: WARN
```

Kết quả mong đợi là những logger trong namespace orders có thể tạo DEBUG (nếu không bị override khác), còn payments có ngưỡng WARN. Đây là **điều chỉnh level theo logger**, chưa đủ để tạo file chỉ chứa orders. Việc định tuyến cần cấu hình Logback/Log4j 2 hoặc hệ thống log downstream.

Level thực tế có thể bị ảnh hưởng bởi profile, environment, file ngoài, command-line property và thay đổi ở runtime. Nếu ứng dụng có Spring Boot Actuator và endpoint được cấu hình/cấp quyền, `/actuator/loggers` có thể giúp xem configured level và effective level. Tuy nhiên, API đó **không chứng minh** một log đã vượt filter của appender và được ghi xuống file.

## 9. So sánh các kiểu filter thường bị nhầm

Giả sử một record có thông tin:

```text
logger_name = com.example.orders.OrderService
thread_name = http-worker-7
level       = INFO
message     = Order created
request_id  = req-42
trace_id    = 4bf92f3577b34da6a3ce929d0e0e4736
```

| Lọc theo | Câu hỏi trả lời | Ví dụ sử dụng |
| --- | --- | --- |
| Logger name | Thành phần nào phát sự kiện? | Chỉ xem log của orders |
| Level | Mức nghiêm trọng/chi tiết ra sao? | Chỉ WARN trở lên |
| Thread name | Thread nào đang thực thi? | Chẩn đoán worker bị treo |
| Message/exception | Sự kiện cụ thể nào xảy ra? | Tìm timeout hoặc exception |
| Marker | Nhãn sự kiện nào được gắn? | Nhóm log SECURITY/AUDIT |
| MDC/context | Request, tenant, user flow nào? | Tra cứu request_id |
| Trace ID | Tác vụ liên dịch vụ nào? | Liên kết log cùng distributed trace |
| Truy vấn ở log backend | Bản ghi nào đã được lưu? | Tìm record trong một khoảng thời gian |

Không dùng logger name để thay cho trace ID. Tất cả request có thể sử dụng cùng một `OrderService` logger; một request cũng có thể ghi qua nhiều logger. Thay vì lọc bỏ dữ liệu để phục vụ một lần điều tra, thường nên giữ dữ liệu phù hợp và dùng truy vấn theo trace/context khi cần.

## 10. Kiểm chứng filter ở môi trường thực

Đừng kết luận filter hoạt động chỉ từ việc tệp cấu hình có dòng `<logger>` hoặc một class filter tồn tại trong source. Hãy kiểm tra hành vi đang chạy theo các bước sau.

**Bước 1 — Xác nhận process/backend.** Ghi nhận bản build, JVM, profile, logging provider thực tế và nguồn cấu hình được nạp. Nếu dùng SLF4J, có thể quan sát class của factory:

```java
// Đoạn tích hợp cần SLF4J trong classpath ứng dụng.
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName());
```

**Bước 2 — Xem effective level, routing và filter.** Với JUL, xem `getLevel`, `getParent`, `getUseParentHandlers`, `getFilter` và `getHandlers`, cùng level/filter của handler. Với Logback, xem configured/effective level, `isAdditive`, các appender gắn trực tiếp và cấu hình filter. Với Log4j 2, xem `LoggerConfig` đang được dùng, appender refs và filters theo API đúng phiên bản.

**Bước 3 — Phát log probe tại bốn tên logger:**

1. Tên chính xác `com.example.orders`.
2. Tên con `com.example.orders.OrderService`.
3. Tên trông giống nhưng nằm ngoài namespace `com.example.orders2.LegacyService`.
4. Tên ngoài nhóm `com.example.payments.PaymentService`.

Gắn một ID probe duy nhất trong thông điệp hoặc structured field, ví dụ `LOGGER_FILTER_PROBE_2026_11`, rồi kiểm tra cả console và file/collector đích. Không bật DEBUG trên toàn bộ ứng dụng production chỉ để thử filter.

**Bước 4 — Đối chiếu expected và observed tại từng sink.** Nếu mục tiêu là “orders.log chỉ có orders”, có thể console vẫn hiển thị các module khác. Nếu mục tiêu là “chặn log noisy trên tất cả các đích”, appender filter đơn lẻ không đủ.

**Bước 5 — Kiểm tra các trường hợp âm tính.** Namespace gần giống `orders2` không được chọn. Logger con `orders.api` phải được chọn nếu chủ ý bao gồm descendants. Event DEBUG phải được nhận khi logger và appender đều cho phép. Không xuất hiện bản ghi lặp do additivity.

Bảng ghi lại kết quả thử:

| Nguồn event | Console | Orders file |
| --- | --- | --- |
| `com.example.orders` | Có, nếu level cho phép | Có |
| `com.example.orders.api` | Có, nếu level cho phép | Có |
| `com.example.orders2` | Có, nếu level cho phép | Không |
| `com.example.payments` | Có, nếu level cho phép | Không |

Bảng trên mô tả **kỳ vọng** của cấu hình Logback tại mục 6, không phải bằng chứng hệ thống đã thực sự chạy. Kết quả thực tế phải đến từ log probe và đọc đúng các đích ghi.

## 11. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `orders2` xuất trong file orders | Dùng `startsWith("...orders")` thiếu ranh giới namespace | Khớp chính xác hoặc thêm `"."` vào prefix |
| Filter trên JUL parent không chặn log từ logger con | Parent logger Filter không được áp lại khi event đi tới handler | Gắn Filter trên handler chung hoặc logger phát sinh |
| Appender cho phép DEBUG nhưng không thấy event | Logger effective level từ chối trước khi appender nhận | Đọc effective level của logger |
| Logback root INFO nhưng vẫn thấy DEBUG của logger con | Event con đã được tạo và truyền qua root appender | Nếu muốn lọc tại sink, đặt threshold/filter trên appender |
| Log bị lặp | Một appender gắn ở nhiều tầng và additivity vẫn bật | Kiểm tra appender refs, tổ chức lại hoặc đặt additivity phù hợp |
| Chỉ file riêng thiếu log | Appender filter, path, quyền ghi hoặc lifecycle sai | Xem appender status và chạy log probe |
| Logger name khác tên class | Logger được đặt tên thủ công/wrapper tạo logger khác | Kiểm tra tên trong event tại runtime |
| Đổi XML nhưng không thay đổi | Sai backend, sai file config, profile hoặc chưa reload | Xác định resource được nạp từ startup diagnostics |
| Cần lọc theo request nhưng filter theo package | Một package xử lý nhiều request đồng thời | Dùng MDC/trace ID đúng cơ chế |
| Chặn cả log lỗi quan trọng | Rule loại cả ERROR/WARN hoặc namespace quá rộng | Xác định ngoại lệ, test đường lỗi/audit |

## 12. Lưu ý vận hành và bảo mật

- **Lọc sớm có chi phí và tác động khác lọc muộn.** Bỏ event ngay tại logger có thể giảm công việc tạo/ghi log, nhưng làm mất sự kiện ở tất cả sink. Lọc tại appender giữ các đích khác nguyên vẹn; lọc lúc truy vấn chỉ ảnh hưởng cách xem dữ liệu đã lưu.
- **Không đặt predicate đắt tiền trên mọi event.** Tránh I/O, network call hoặc regex không cần thiết trong filter. So khớp tên chính xác và prefix phân cách bằng dấu chấm thường dễ đọc, nhanh và kiểm thử được.
- **Đảm bảo không bỏ mất audit/security logs.** Nếu cần bảo toàn sự kiện quan trọng, không vô tình dùng một rule rộng chặn cả ERROR hay AUDIT. Logging best-effort không thay thế hệ thống ghi sự kiện bền vững.
- **Kiểm tra async logging.** Record có thể nằm trong queue trước khi đến sink; cần xét queue overflow, drop policy và flush khi shutdown. “Chưa thấy ngay” không đồng nghĩa filter đã loại.
- **Không đưa dữ liệu nhạy cảm vào probe.** Không ghi mật khẩu, token, PII hoặc payload thật. Logger filtering không phải cơ chế phân quyền truy cập bản ghi.
- **Cẩn trọng với thay đổi runtime.** `setFilter`, `setLevel`, reload/reset context là các thao tác thay đổi hành vi process. Phép kiểm tra chỉ đọc nên tập trung vào trạng thái và probe phù hợp môi trường.
- **Đúng backend, đúng phiên bản.** JUL, Logback và Log4j 2 có điểm gắn filter và semantics khác nhau; đọc API tài liệu của backend đang chạy trước khi áp dụng cấu hình.

## 13. Bài luyện tập có đáp án

**Câu 1.** Điều kiện nào chọn `app.orders` và `app.orders.api` nhưng không chọn `app.orders2`?

Đáp án: `name != null && (name.equals("app.orders") || name.startsWith("app.orders."))`.

**Câu 2.** Với JUL, có phải filter trên logger cha luôn chạy khi một logger con gửi event đến handler của cha?

Đáp án: **Không**. Filter của logger cha không được mặc nhiên gọi lại trên record phát sinh từ logger con. Filter đặt ở handler là cách áp điều kiện chung cho những event tới handler đó.

**Câu 3.** Nếu Logback root INFO nhưng logger `app.orders` có level DEBUG, một DEBUG event của orders có thể đến appender ở root không?

Đáp án: **Có**, nếu event được tạo và additivity dẫn nó đến appender đó. Level của root không nhất thiết được áp lại tại appender; muốn chặn DEBUG ở sink, dùng appender-level threshold/filter.

**Câu 4.** Toàn bộ log cần ra console, file `orders.log` chỉ chứa orders. Nên đặt filter ở đâu?

Đáp án: **Trên appender ghi orders.log**, hoặc định tuyến logger namespace tới một appender riêng. Tránh đặt context-wide filter loại những event của module khác nếu chúng vẫn cần xuất console.

## 14. Checklist hoàn thành

Một giải pháp filter theo logger được xem là đúng khi:

1. Tên logger thực tế và quy ước namespace đã được xác nhận.
2. Điều kiện khớp tên phân biệt chính xác logger, descendants và namespace gần giống.
3. Mục tiêu rõ ràng: giảm log ở nguồn, lọc một appender hay tìm kiếm tại backend.
4. Level kế thừa, Filter, handler/appender và additivity đều được xem xét.
5. Có kiểm tra log probe từ logger chính, logger con, logger gần giống và logger khác.
6. Kết quả được đối chiếu tại từng destination cần kiểm tra, không chỉ đọc file cấu hình.
7. Các log lỗi/audit và chính sách async shutdown được cân nhắc trước khi triển khai.

**Ghi nhớ:** Filter theo logger là chọn sự kiện bằng **định danh thành phần phát log**. Hiểu đúng nơi ra quyết định — logger, context, handler/appender hay hệ thống thu thập — giúp định tuyến có chủ đích, giảm nhiễu và vẫn giữ những log quan trọng cho chẩn đoán.