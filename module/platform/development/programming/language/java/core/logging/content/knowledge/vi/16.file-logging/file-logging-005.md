# File log theo ứng dụng trong Java

## 1. File log theo ứng dụng là gì?

**File log theo ứng dụng** là cách tổ chức logging để sự kiện của một **ứng dụng, service hoặc tiến trình** được ghi vào file (hoặc nhóm file xoay vòng) có tên và đường dẫn riêng. Ví dụ trên một máy chạy ba dịch vụ:

```text
logs/
├── orders-service.log
├── billing-service.log
└── inventory-service.log
```

Trong đó `orders-service.log` chứa log của ứng dụng xử lý đơn hàng, còn `billing-service.log` thuộc hệ thống thanh toán. Tách đích lưu như vậy giúp điều tra sự cố nhanh hơn, dễ quản lý quyền truy cập, dung lượng và thời hạn giữ log.

**Không đồng nhất “mỗi ứng dụng một file” với “mỗi class một file”.** Java có thể có hàng trăm logger theo class hoặc package, nhưng chúng cùng gửi event tới **một appender/handler file**. Đây là quyết định cấu hình của logging backend, không phải chức năng đặc biệt tự phát sinh khi gọi `Logger.getLogger(...)`.

Ví dụ cùng một service có các logger:

- `com.example.orders.OrderController`
- `com.example.orders.OrderService`
- `com.example.orders.OrderRepository`

Cả ba có thể ghi chung vào `logs/orders-service.log`, được phân biệt bên trong từng dòng bằng trường `loggerName`.

Một cách tổ chức file theo request hoặc người dùng như `REQ-123.log` là bài toán khác. Nó tạo số lượng file khó kiểm soát và dễ dẫn đến vấn đề đường dẫn, dữ liệu riêng tư, retention; không nên là lựa chọn mặc định.

## 2. Khi nào nên tách file theo ứng dụng?

Giả sử nhiều JVM trên cùng máy chủ ghi vào `logs/application.log` chung. Các dòng từ nhiều ứng dụng có thể xen kẽ, gây khó tìm nguyên nhân và tranh chấp khi ghi hoặc xoay file. Tách ra từng file giúp:

1. **Khoanh vùng lỗi:** biết service nào cần đọc log mà không lọc toàn bộ file.
2. **Chọn mức chi tiết:** service cần debug có thể được phép ghi `DEBUG` vào file mà không ảnh hưởng service khác.
3. **Quản lý vận hành:** từng service có rotation, retention, quota và permission riêng.
4. **Tối ưu thu thập:** log collector dễ gắn các nhãn như `service`, `environment`, `instance`.
5. **Hạn chế đụng file:** các JVM độc lập không phải cùng nắm giữ một đường dẫn ghi.

Bù lại, nhiều file đồng nghĩa có thêm cấu hình, chi phí lưu trữ và việc theo dõi. Trên Kubernetes hoặc hạ tầng đã gom stdout/stderr theo container, **phân tách theo metadata trong collector** có thể hiệu quả hơn việc bắt buộc mỗi ứng dụng tự tạo file bên trong container.

### Quy tắc lựa chọn

| Cách phân tách | Tên minh họa | Mục đích |
| --- | --- | --- |
| Theo service | `orders-service.log` | Đầu ra của một ứng dụng riêng |
| Theo môi trường | `orders-prod.log` | Phân biệt dev/test/prod nếu dùng chung hệ thống file |
| Theo instance | `orders-instance-a.log` | Tránh nhiều JVM ghi cùng file |
| Theo nhóm sự kiện | `orders-errors.log` | Có thể lưu WARN/ERROR khác với INFO |
| Theo module/package | `orders-payment.log` | Phân tách nếu một module cần chính sách riêng |
| Theo từng user/request | `user-42.log` | **Thường không phù hợp** vì rủi ro bảo mật và bùng nổ file |

Nếu hệ thống có một service trên một JVM riêng, thường chọn một **file chính có rotation** cho mỗi service, sau đó lưu request ID, logger name và instance ID **trong nội dung bản ghi**, thay vì tạo file mới cho từng request.

## 3. Đường đi của log trong một ứng dụng

Một kiến trúc logging phổ biến:

```text
OrdersApp
   ├── OrderController ─┐
   ├── OrderService ────┼──> Logger API
   └── OrderRepository ┘           │
                                   ▼
                       Logger config: level/filter
                                   │
                                   ▼
                         File/RollingFile Appender
                                   │
                              Layout/Formatter
                                   │
                                   ▼
                          logs/orders-service.log
```

Các thành phần có nhiệm vụ khác nhau:

- **Logger:** nhận lệnh `info`, `warn`, `error`, có tên theo class/package.
- **Level/filter của logger:** loại những sự kiện không cần tạo hoặc chuyển tiếp.
- **Appender (Log4j2/Logback):** kết nối logger với file, console hoặc đích xuất khác.
- **Handler (JUL):** khái niệm gần với appender trong `java.util.logging`.
- **Layout/Formatter:** quyết định timestamp, logger name, message và exception hiển thị ra sao.
- **Rolling policy:** kiểm soát việc xoay và lưu các file archive.

**Tên file không tự theo tên class.** Có `Logger` tên `OrderService` không đồng nghĩa hệ thống sẽ tạo `OrderService.log`; đường dẫn file phải do backend hoặc chương trình chỉ định.

Khi code sử dụng SLF4J facade, `org.slf4j.Logger` chỉ phát sự kiện. Việc tạo file do **provider/backend**, chẳng hạn Logback hoặc Log4j2, quyết định. Tài liệu cấu hình của JUL không thể dùng nguyên xi để điều khiển Logback, và ngược lại.

## 4. Đặt tên file và cấu trúc thư mục

Tên file lý tưởng phải dễ hiểu, ổn định và không bị trùng với ứng dụng khác:

```text
/var/log/example/
├── orders/
│   ├── orders-service.log
│   └── archive/
├── billing/
│   ├── billing-service.log
│   └── archive/
└── inventory/
    ├── inventory-service.log
    └── archive/
```

Đây là đường dẫn **minh họa trên Linux**, không phải vị trí bắt buộc. Mỗi deployment có thể chọn thư mục log được cấp quyền riêng.

**Nên dùng:**

- Tên service từ cấu hình đã được kiểm soát: `orders-service`.
- Môi trường hoặc instance khi thực sự cần phân biệt file dùng chung.
- Thư mục archive riêng cho các file đã rollover.
- Đường dẫn đã xác định cùng quyền tạo/ghi/đổi tên file.

**Không nên dùng:**

- Giá trị raw từ URL, user input hoặc request header để đặt tên file.
- Một tên file cố định `application.log` cho tất cả JVM trên cùng filesystem mà không kiểm soát việc dùng chung.
- Tên file chứa mật khẩu, token, email hoặc dữ liệu cá nhân nhạy cảm.
- Tạo handler/file mới mỗi request chỉ vì cần lọc log theo request ID.

Nếu ứng dụng được chạy từ working directory khác, đường dẫn tương đối `logs/orders-service.log` có thể được resolve tới vị trí khác. Cần ghi rõ working directory trong script/service manager, hoặc dùng đường dẫn tuyệt đối được cấu hình lúc triển khai.

## 5. Ví dụ đầy đủ: Java 17 + Maven + Log4j2

Để thấy rõ file log của ứng dụng hoạt động thế nào, ta tạo ứng dụng **Orders Service** với Log4j2 API và Log4j2 Core.

Yêu cầu demo:

- Logger dưới namespace `demo.orders`.
- Event `INFO`, `WARN`, `ERROR` hiển thị trên console.
- File `logs/orders-service.log` nhận từ mức `DEBUG` trở lên.
- File dùng **RollingFile** để có thể xoay theo kích thước và thời gian.
- Không tạo log trùng do logger con và root cùng xử lý.

### 5.1. Cấu trúc dự án

```text
orders-service/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── orders/
        │           └── OrdersApp.java
        └── resources/
            └── log4j2.xml
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Những version trong demo là **một tổ hợp cố định để minh họa**, không có nghĩa đó là bản mới nhất hay lựa chọn phù hợp cho mọi production. Khi triển khai thật, dùng phiên bản được duy trì, cập nhật bản vá bảo mật và đồng bộ giữa `log4j-api`, `log4j-core` cùng bridge/backend nếu có.

### 5.3. Tệp src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <RollingFile name="OrdersFile"
                     fileName="logs/orders-service.log"
                     filePattern="logs/archive/orders-service-%d{yyyy-MM-dd}-%i.log.gz"
                     append="true">
            <PatternLayout pattern="%level | %msg%n"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="1 MB"/>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
            </Policies>
            <DefaultRolloverStrategy max="3"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Logger name="demo.orders" level="debug" additivity="false">
            <AppenderRef ref="Console" level="info"/>
            <AppenderRef ref="OrdersFile" level="debug"/>
        </Logger>

        <Root level="warn">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Phân tích cấu hình:

1. **`OrdersFile` là tên appender**, còn `fileName` mới là vị trí file hiện tại.
2. `filePattern` đặt tên file archive khi có rollover; `%d` là ngày, `%i` là chỉ số.
3. `append="true"` nối thêm vào file đang có sau restart, không mặc định ghi đè file cũ.
4. `SizeBasedTriggeringPolicy` và `TimeBasedTriggeringPolicy` cung cấp điều kiện xoay file. Một lượt demo ít dòng có thể **chưa hề tạo file archive**.
5. `DefaultRolloverStrategy max="3"` liên quan cửa sổ/chỉ số archive theo chiến lược; **không đồng nghĩa giữ đúng ba ngày**.
6. Logger có tên `demo.orders` nhận các sự kiện từ code trong namespace này; level DEBUG cho phép ghi message debug.
7. Console AppenderRef ở INFO nên không in DEBUG.
8. OrdersFile AppenderRef ở DEBUG nên file nhận nhiều chi tiết hơn console.
9. `additivity="false"` ngăn event của Orders đi tiếp tới root Console, giảm nguy cơ in một event hai lần.
10. Root WARN chỉ để xử lý logger không thuộc namespace đã cấu hình. **Trong ví dụ này file riêng chỉ nhận sự kiện của namespace Orders**.

Nếu một dự án muốn file ứng dụng chứa **tất cả** logger trong JVM, có thể gắn file appender ở root. Nếu chỉ muốn chứa module riêng, gắn nó ở logger namespace phù hợp. Đó là hai chính sách khác nhau, cần chọn có chủ đích.

### 5.4. Tệp src/main/java/demo/orders/OrdersApp.java

```java
package demo.orders;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class OrdersApp {
    private static final Logger LOG =
            LogManager.getLogger(OrdersApp.class);

    public static void main(String[] args) {
        String orderId = "ORD-42";

        LOG.debug("Checking inventory for {}", orderId);
        LOG.info("Order {} accepted", orderId);
        LOG.warn("Low stock for {}", orderId);

        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException exception) {
            LOG.error("Invalid numeric configuration", exception);
        }

        System.out.println("business-finished");
    }
}
```

Mã dùng một logger theo class nhưng cấu hình định tuyến các bản ghi tới **file của cả ứng dụng Orders**. Ví dụ cố tình tạo `NumberFormatException` để kiểm tra việc giữ nguyên `Throwable` cho backend logging.

### 5.5. Chạy chương trình

Từ thư mục `orders-service` với Maven và JDK 17 trở lên:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.orders.OrdersApp
```

**Những dòng message chính trên stdout**, bỏ qua output riêng của Maven:

```text
INFO | Order ORD-42 accepted
WARN | Low stock for ORD-42
ERROR | Invalid numeric configuration
business-finished
```

Vì event ERROR có Throwable, Log4j2 PatternLayout có thể **tự in thêm stack trace** sau dòng ERROR. Do đó, đây là danh sách các **dòng thông điệp chính**, không phải toàn bộ output byte-for-byte của console.

**Những dòng message chính trong `logs/orders-service.log` sau một lần chạy từ thư mục sạch:**

```text
DEBUG | Checking inventory for ORD-42
INFO | Order ORD-42 accepted
WARN | Low stock for ORD-42
ERROR | Invalid numeric configuration
```

File cũng có thể có **stack trace nhiều dòng** của `NumberFormatException`. Số dòng và nội dung frame phụ thuộc phiên bản JDK. Nếu chạy lại, `append="true"` khiến các record mới được thêm sau record cũ.

Xem file:

```bash
cat logs/orders-service.log
```

Trên PowerShell:

```powershell
Get-Content logs/orders-service.log
```

**Vì sao DEBUG vào file nhưng không vào console?** Mức DEBUG được logger `demo.orders` chấp nhận, nhưng mỗi AppenderRef có ngưỡng riêng. `OrdersFile` nhận DEBUG, còn `Console` chỉ nhận INFO+. Không phải vì mã gọi hai logger hay mở file trong từng method.

### 5.6. Những việc cần kiểm tra sau khi chạy

- File `log4j2.xml` thực sự nằm trên runtime classpath.
- Log4j2 API/Core hiện diện đúng version, không bị một backend khác thay thế.
- Working directory đúng như dự kiến.
- Thư mục log/archived file có thể được tạo và có quyền ghi.
- File có ít nhất các thông điệp INFO/WARN/ERROR.
- Console không lặp event do additivity.
- Event ERROR giữ được exception/stack trace nếu layout được cấu hình hỗ trợ.
- Khi tăng lượng event để test rollover, tên file archive tuân theo pattern.

Không nên dựa vào việc `mvn compile` thành công để kết luận file logging đã hoạt động: cấu hình và quyền filesystem chủ yếu được kiểm tra lúc runtime.

## 6. Tạo file riêng cho nhiều ứng dụng trên cùng máy

Với **hai JVM độc lập**, cách phổ biến nhất là **mỗi JVM nạp cấu hình của chính mình**:

```text
JVM Orders:
  logs/orders-service.log

JVM Billing:
  logs/billing-service.log
```

Nếu hai service được build từ cùng template, có thể truyền tên service và thư mục log qua cấu hình triển khai an toàn. Không để cả hai ghi vào `logs/application.log` chỉ vì template dùng chung một literal.

Một ví dụ về việc chọn path theo quy tắc triển khai:

| Ứng dụng | Log file hiện tại | Thư mục archive |
| --- | --- | --- |
| Orders | `/var/log/example/orders/orders-service.log` | `/var/log/example/orders/archive` |
| Billing | `/var/log/example/billing/billing-service.log` | `/var/log/example/billing/archive` |
| Inventory | `/var/log/example/inventory/inventory-service.log` | `/var/log/example/inventory/archive` |

Đường dẫn POSIX trên chỉ là **minh họa**; filesystem thực tế cần được tạo, bảo vệ và gắn vào tiến trình. Trong môi trường Windows, nên dùng đường dẫn tương ứng của nền tảng, không sao chép đường dẫn Linux.

### Nếu một JVM chứa hai module

Trường hợp một JVM có cả `com.example.orders` và `com.example.billing`, có thể tách theo logger namespace:

```xml
<Loggers>
    <Logger name="com.example.orders" level="info"
            additivity="false">
        <AppenderRef ref="OrdersFile"/>
    </Logger>

    <Logger name="com.example.billing" level="info"
            additivity="false">
        <AppenderRef ref="BillingFile"/>
    </Logger>

    <Root level="warn">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

Đây là **mảnh cấu hình**: `OrdersFile`, `BillingFile` và `Console` phải được định nghĩa trong `<Appenders>`. Phân loại theo package ở cùng một JVM là **tách theo module**, không phải tách hai tiến trình có lifecycle độc lập.

Nếu muốn sự kiện module cũng ra console, hãy tham chiếu thêm console tại logger module hoặc thay đổi đường propagation cho đúng. Với `additivity="false"`, logger con không tự động đưa event lên root Console.

## 7. Ngăn log trùng do additivity

Khi cấu hình nhiều logger và appender, sự kiện có thể xuất nhiều lần nếu cùng một appender được tham chiếu từ logger con lẫn logger cha/root.

Ví dụ dễ gây trùng:

```xml
<Loggers>
    <Logger name="demo.orders" level="info">
        <AppenderRef ref="Console"/>
    </Logger>

    <Root level="info">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

Ở đây giả sử `Console` đã được khai báo. Logger con có thể xuất event qua Console, sau đó do additivity tiếp tục xử lý qua root và xuất lần nữa.

Hai cách phổ biến để tránh:

1. Để `Console` **chỉ tại root**; logger con có thể đặt level riêng mà không gắn trùng appender.
2. Logger con có **đủ appender riêng**, đặt `additivity="false"` để ngăn event đi lên root.

**Quan trọng:** tắt additivity có thể làm **mất đích** từng chỉ có ở root. Ví dụ logger con có file appender nhưng không có console; nếu đặt additivity false, sự kiện có thể chỉ còn đi file. Điều này đúng hay sai tùy nhu cầu, không được coi là mặc định.

Một WARN xuất **một lần trên console và một lần trong file** là fan-out bình thường. Một WARN xuất **hai lần ở cùng file** mới thường cho thấy cấu hình trùng, hoặc mã nguồn log cùng lỗi ở nhiều tầng.

## 8. Logback: file theo ứng dụng với SLF4J

Nếu dự án dùng `org.slf4j.Logger` và backend là **Logback**, cấu hình file thường đặt trong `logback.xml`. Ví dụ đầy đủ ở mức minh họa:

```xml
<configuration>
    <appender name="ORDERS"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders-service.log</file>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/orders-service.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%-5level %logger{1} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ORDERS"/>
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong cấu hình này, root đưa các log phù hợp mức INFO trở lên tới file của **tiến trình**, gồm cả log của thư viện khác nếu chúng đi vào cùng Logback backend.

**Khác với Log4j2:** Logback dùng các class `RollingFileAppender`, `SizeAndTimeBasedRollingPolicy` và thẻ `<appender-ref>`, còn Log4j2 dùng `RollingFile`, `Policies`, `AppenderRef`. Không copy hai cấu hình XML qua lại rồi mong hoạt động.

`maxHistory` và `totalSizeCap` phục vụ chính sách lưu/giới hạn archive của Logback, nhưng vẫn phải kiểm tra hành vi retention thực tế lúc rollover và lúc khởi động. Logback cần dependency backend tương thích với phiên bản SLF4J API của ứng dụng.

Một thư viện Java tái sử dụng thường chỉ nên dùng facade `slf4j-api` và để ứng dụng cuối chọn provider/đường dẫn log; đừng buộc mọi ứng dụng tiêu thụ phải ghi vào file do thư viện tự đặt tên.

## 9. JUL: FileHandler ghi file ứng dụng mà không cần dependency

JDK cung cấp `java.util.logging.FileHandler`. Nó có thể ghi vào file theo pattern và xoay dựa trên kích thước/số thế hệ.

Tạo file độc lập `JulApplicationFileDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulApplicationFileDemo {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        Logger logger = Logger.getLogger("demo.orders");
        Level oldLevel = logger.getLevel();
        boolean oldUseParents = logger.getUseParentHandlers();
        Handler[] oldHandlers = logger.getHandlers();

        Formatter concise = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(concise);

        FileHandler file = new FileHandler(
                "logs/orders-service-%g.log",
                1_048_576, 3, true);
        file.setLevel(Level.FINE);
        file.setFormatter(concise);

        for (Handler h : oldHandlers) {
            logger.removeHandler(h);
        }
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);
        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.fine("Preparing order cache");
            logger.info("Order accepted");
            logger.warning("Low stock");
            System.out.println("jul-finished");
        } finally {
            logger.removeHandler(file);
            logger.removeHandler(console);
            file.close();
            console.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldUseParents);
            for (Handler h : oldHandlers) {
                logger.addHandler(h);
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac JulApplicationFileDemo.java
java JulApplicationFileDemo
```

**Stdout do chương trình tạo:**

```text
jul-finished
```

**Các dòng ConsoleHandler ghi vào stderr:**

```text
INFO | Order accepted
WARNING | Low stock
```

**Ba dòng sự kiện trong file JUL**, thường là `logs/orders-service-0.log` nếu không có xung đột/rollover:

```text
FINE | Preparing order cache
INFO | Order accepted
WARNING | Low stock
```

Vì tham số `append=true`, file có thể còn các dòng từ lần chạy trước; bảng trên mô tả **một lần chạy**. FileHandler có thể thêm suffix khi có xung đột tên/khóa file và có pattern thế hệ `%g`. Đừng khẳng định tên file luôn giống nhau khi nhiều JVM tranh cùng thư mục.

**Điểm cần nhớ:**

- `Files.createDirectories(...)` chuẩn bị đường dẫn.
- `new FileHandler(pattern, limit, count, append)` đặt pattern, ngưỡng byte, số thế hệ và chế độ append.
- `setFormatter(...)` giúp file dạng text dễ đọc. Không đặt formatter, JUL FileHandler mặc định có thể tạo XML.
- `logger.setUseParentHandlers(false)` ngăn event lên handler root, tránh console trùng trong ví dụ.
- Logger ở FINE, file handler FINE, console INFO: **mức lọc logger và từng handler độc lập**.
- `close()` giải phóng file handle/khóa. Chỉ đóng các handler do chương trình sở hữu.

**Không tạo một FileHandler mới trong mỗi request**. Cần khởi tạo một lần, giữ tham chiếu và đóng khi ứng dụng shutdown. Trong ứng dụng đa luồng hoặc server có container, tháo/gắn handler dùng chung có thể tác động tới các request đang chạy; ví dụ chỉ minh họa trong JVM riêng.

## 10. Rotation và retention: không để mỗi service làm đầy ổ đĩa

Một file ứng dụng có thể tăng rất nhanh khi log DEBUG, request volume cao hoặc exception liên tục. Vì vậy cần tách:

- **Rotation (rollover):** khi đạt kích thước hoặc thời điểm quy định, file hoạt động được chuyển thành archive và một file mới được dùng.
- **Retention:** những archive được giữ bao lâu hoặc giới hạn tổng dung lượng/số lượng theo chính sách.
- **Compression:** nén file archive khi backend hỗ trợ.
- **Quota/monitoring:** phát cảnh báo trước khi filesystem hết chỗ.

| Chính sách | Ví dụ | Cần lưu ý |
| --- | --- | --- |
| Theo kích thước | Xoay quanh 10 MB | Một event lớn có thể làm vượt giới hạn trước rollover |
| Theo thời gian | Xoay mỗi ngày | Quan tâm múi giờ/lịch chạy |
| Theo kích thước và ngày | `%d{yyyy-MM-dd}-%i` | Số lượng archive trong một ngày |
| Giữ một số archive | `max="3"` theo cơ chế tương ứng | Không đồng nghĩa giữ đúng ba ngày |
| Giữ theo tuổi | Xóa file cũ hơn n ngày | Có thể cần chính sách Delete/retention riêng |
| Giới hạn tổng dung lượng | Tổng archive dưới một ngưỡng | Kiểm tra khi rollover và khi appender khởi tạo |

**Rotation không tự bảo đảm mọi thông tin đã được ghi bền vững.** Nếu JVM bị kill trong lúc buffer còn dữ liệu, filesystem đầy hoặc collector downstream lỗi, log có thể không tồn tại ở nơi bạn tìm. File logging thông thường cũng không thay thế transaction log/audit trail cần bảo đảm tính toàn vẹn và chống sửa đổi.

Khi chạy nhiều service chung một ổ đĩa, từng service có file riêng nhưng vẫn phải giám sát **dung lượng tổng**. Một appender DEBUG quá rộng có thể chiếm hết dung lượng và khiến service khác cũng không thể ghi log.

## 11. Nhiều JVM cùng ứng dụng: đừng ghi chung một file trên shared filesystem

Ví dụ hệ thống scale Orders thành hai JVM:

```text
Không khuyến nghị nếu không có cơ chế phối hợp đặc biệt:
Orders JVM A ─┐
              ├─> logs/orders-service.log
Orders JVM B ─┘
```

Thread-safety trong cùng JVM **không đảm bảo** hai tiến trình đồng thời ghi và rollover một file an toàn. Có thể gặp:

- Tranh khóa file hoặc bị tạo tên file khác ngoài dự tính.
- Dòng log xen kẽ khiến khó xác định instance phát event.
- Tiến trình này xoay/đổi tên trong lúc tiến trình kia đang ghi.
- Archive bị ghi đè, thu thập thiếu hoặc retention thực tế khác dự kiến.

Hai lựa chọn dễ vận hành hơn:

```text
Cách A: file theo instance
Orders JVM A ──> logs/orders-instance-a.log
Orders JVM B ──> logs/orders-instance-b.log

Cách B: stdout/stderr và collector
Orders JVM A ──> stdout ──┐
                          ├─> Collector (service=orders, instance=A/B)
Orders JVM B ──> stdout ──┘
```

Nếu dùng file theo instance, instance ID phải do hạ tầng cấp, được kiểm soát, tránh va chạm và không chứa ký tự đường dẫn nguy hiểm. Đừng lấy tên file từ request/user input hoặc một giá trị chưa được xác thực.

Trên Docker/Kubernetes, file cục bộ có thể nằm trên filesystem ngắn hạn, mất khi container bị thay thế. Nhiều nền tảng ưu tiên thu thập stdout/stderr và lưu tập trung; file theo ứng dụng khi ấy có thể được thay bằng **nhãn service/namespace/pod** của collector.

## 12. Quyền ghi, đường dẫn và bảo mật

Một lỗi đơn giản nhưng thường gặp là appender không thể tạo file vì **quyền truy cập filesystem (file permission)**.

### Relative path và absolute path

`logs/orders-service.log` là đường dẫn **tương đối theo working directory** của JVM. Nếu chạy bằng Maven ở thư mục dự án, đường dẫn thường xuất hiện dưới dự án. Nếu chạy bằng service manager từ thư mục khác, file có thể nằm nơi khác.

Trong triển khai Linux, có thể chọn đường dẫn tuyệt đối:

```text
/var/log/example/orders/orders-service.log
```

Đây là đường dẫn minh họa; ứng dụng không tự được quyền ghi vào bất cứ thư mục nào. Nên chuẩn bị thư mục, ownership, quyền ghi/đọc, quyền rename và quyền tạo archive bằng cấu hình triển khai, không tùy tiện cho ứng dụng chạy với đặc quyền root/administrator.

### Những việc nên kiểm tra

- Đường dẫn cuối cùng có nằm trong thư mục log cho phép không?
- Tiến trình có quyền tạo, ghi, rename và xóa file theo rotation không?
- File log có vô tình nằm trong thư mục được web server phục vụ công khai không?
- Có một ứng dụng khác dùng chung fileName/filePattern không?
- Tên file lấy từ cấu hình đáng tin hay đầu vào người dùng chưa kiểm soát?
- Đã đặt retention, quota và cơ chế giám sát đĩa chưa?
- Người được phép đọc log có thể thấy dữ liệu gì?

**File log có thể chứa thông tin nhạy cảm.** Exception message, SQL, đường dẫn nội bộ, correlation ID và dữ liệu do người dùng cung cấp có thể bị lưu lâu. Không ghi mật khẩu, token, API key, cookie xác thực, dữ liệu thẻ hay PII vào message và context. Mọi đích nhận log, gồm console, file và collector, đều cần chính sách quyền và thời hạn lưu.

## 13. Thêm request ID vào file, không tạo file riêng cho mỗi request

Một file theo ứng dụng thường chứa log của nhiều request đồng thời. Để tìm một request cụ thể, gắn `requestId` hoặc `traceId` vào các event.

Trong Log4j2, `ThreadContext` có thể được dùng:

```java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("requestId", "REQ-204");
try {
    LOG.info("Order processing started");
} finally {
    ThreadContext.remove("requestId");
}
```

Đây là **đoạn code minh họa**, cần đặt trong method của class có `LOG` và import phù hợp. Để hiển thị context, layout của file có thể dùng:

```text
%d{ISO8601} %-5level [%t] %logger requestId=%X{requestId} - %msg%n%ex
```

Trong hệ sinh thái SLF4J/Logback, khái niệm tương tự thường là **MDC**. Tuy nhiên việc đặt context không tự bảo đảm nó đi theo mọi thread của `CompletableFuture` hoặc thread pool: cần truyền/dọn context đúng vòng đời và tránh rò ID giữa request.

Gắn `traceId` trong log giúp tương quan sự kiện, **không có nghĩa hệ thống đã tự tạo distributed trace**. Với nhiều JVM, dùng service/instance ID ở metadata là cách xác định file/dòng thuộc node nào mà không tạo một file trên mỗi request.

## 14. Sự khác biệt giữa log theo ứng dụng và log theo loại sự kiện

Một ứng dụng có thể cần nhiều file với nhiệm vụ khác nhau:

```text
orders-service/
├── application.log        (INFO trở lên)
├── errors.log             (ERROR trở lên)
└── audit.log              (chỉ event audit hợp lệ)
```

Đây là **tách theo loại sự kiện bên trong một ứng dụng**, không phải thay cho file theo ứng dụng. Để làm đúng cần các appender/handler và filter riêng. Một log INFO của application có thể không xuất trong errors.log; một log ERROR có thể ở cả application.log và errors.log nếu thiết kế fan-out như vậy.

Đừng dựa vào việc hai file cùng chứa ERROR để kết luận chúng trùng sai. **Fan-out có chủ đích** khác với **cùng một event bị gửi hai lần vào chính một file** vì logger con và root cùng tham chiếu một appender.

Với audit, không chỉ cần tên file `audit.log`. Một audit trail đáng tin cậy có thể cần định nghĩa schema sự kiện, danh tính người thực hiện, kiểm soát sửa đổi, đồng bộ thời gian, retention và lưu trữ chống can thiệp. Appender thông thường không tự đáp ứng các yêu cầu đó.

## 15. Kiểm tra file log sau khi triển khai

Đừng chỉ thấy `LOG.info(...)` trong code rồi kết luận file logging đang hoạt động. Kiểm tra theo đúng đường sự kiện:

1. **API:** mã dùng JUL, SLF4J hay Log4j2?
2. **Backend:** runtime có provider/implementation tương ứng không?
3. **Tên logger:** class/package phát event có khớp cấu hình logger cho service đó?
4. **Level:** logger cho phép mức cần ghi không?
5. **Appender/handler:** có thật sự gắn file appender với logger đó không?
6. **Additivity:** record có bị gửi trùng hoặc mất đích do propagation không?
7. **Đường dẫn:** file thực tế được resolve từ working directory nào?
8. **Filesystem:** thư mục có tồn tại, có quyền ghi, đủ dung lượng và quyền xoay file không?
9. **Rotation:** file đang hoạt động và archive đúng pattern/chính sách không?
10. **Collector:** nếu có hệ thống tập trung, file đã được tail/ship và gắn nhãn đúng chưa?

Có thể thử một sự kiện `WARN` đặc trưng rồi xem file/appender status. Đừng bật toàn bộ TRACE trên production vô thời hạn khi chỉ muốn tìm một file log.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có `orders-service.log` | Config không nạp, sai path, thiếu quyền hoặc appender chưa khởi tạo | Xác minh classpath, status log, working directory và permission |
| Log của Billing xuất trong file Orders | Các service dùng chung đường dẫn hoặc logger routing sai | Tách fileName theo service/instance và kiểm tra AppenderRef |
| Không thấy DEBUG trong file | Logger hoặc AppenderRef/filter chặn DEBUG | Kiểm tra level tại cả logger lẫn appender |
| File có WARN nhưng console không có | Console mức cao hơn hoặc filter riêng | Kiểm tra AppenderRef Console |
| Một event xuất hai lần trong file | Additivity/đường AppenderRef trùng hoặc code log cùng lỗi nhiều lần | Chỉ giữ một đường đến appender hoặc sửa nơi log |
| File bị ghi đè sau restart | FileAppender append=false hoặc chính sách file không phù hợp | Dùng append/rolling có chủ đích |
| File tăng đến đầy đĩa | Không rotation, không retention, log quá chi tiết | Cấu hình rolling/retention, cảnh báo/quota |
| File của container mất sau deploy | Filesystem tạm thời hoặc chưa có collector | Dùng stdout/stderr hoặc volume/collector phù hợp |
| File bị phân tán thành nhiều tên | Nhiều JVM tranh file hoặc pattern `%u` của JUL xử lý xung đột | Tách theo instance, kiểm tra khóa và pipeline |
| Exception không có stack trace | Chỉ ghi `exception.getMessage()` hoặc layout thiếu Throwable | Truyền nguyên exception và kiểm tra formatter |
| File không theo tên class | File name do appender đặt, không phải tên class | Cấu hình đúng tên file theo service |
| Sửa `log4j2.xml` không thấy thay đổi | Dùng nhầm file/backend hoặc chưa reload | Xác nhận cấu hình thực tế trên runtime |
| File không thể rollover | Thiếu quyền tạo archive/rename, đĩa đầy hoặc pattern sai | Kiểm tra status log và filesystem |
| Hai JVM ghi chung file gây lỗi | Cạnh tranh ghi/xoay file | Tách per-instance hoặc chuyển sang collector |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** File log theo ứng dụng có bắt buộc mỗi class có một file riêng?  
**Đáp án:** Không. Nhiều logger theo class/package có thể dùng chung file của một ứng dụng.

**Câu 2.** Tại sao không nên để nhiều JVM độc lập cùng ghi `orders-service.log` trên shared filesystem?  
**Đáp án:** Có thể tranh khóa, ghi xen kẽ và lỗi rollover; nên tách file instance hoặc thu thập qua stdout.

**Câu 3.** Trong ví dụ Log4j2, bản ghi DEBUG đi đâu?  
**Đáp án:** Logger `demo.orders` cho phép DEBUG, appender OrdersFile nhận DEBUG, còn console chỉ INFO+ nên DEBUG chỉ vào file.

**Câu 4.** `append="true"` có bảo đảm giữ log vĩnh viễn?  
**Đáp án:** Không. Nó chỉ yêu cầu nối thêm thay vì ghi đè khi mở file; rotation/retention và các thao tác ngoài vẫn có thể chuyển/xóa dữ liệu.

**Câu 5.** `DefaultRolloverStrategy max="3"` có nghĩa giữ đúng ba ngày?  
**Đáp án:** Không. Đây là cấu hình của chiến lược rollover, không đồng nghĩa chính sách tuổi dữ liệu.

**Câu 6.** Trong JUL, thành phần nào ghi file và khi nào cần đóng?  
**Đáp án:** `FileHandler`; thành phần sở hữu cần đóng khi kết thúc vòng đời để giải phóng tài nguyên/khóa.

**Câu 7.** FileAppender Logback và RollingFile Log4j2 có dùng một file XML cấu hình chung được không?  
**Đáp án:** Không. Các backend khác nhau có class, schema và cách thiết lập khác nhau.

**Câu 8.** Vì sao file tương đối của service có thể xuất ở thư mục khác khi chạy qua service manager?  
**Đáp án:** Vì đường dẫn tương đối được resolve từ working directory của tiến trình.

**Câu 9.** Có nên tạo tên file dựa vào request ID do client gửi?  
**Đáp án:** Không phải lựa chọn mặc định; nên gắn ID đã kiểm soát vào trường log, tránh file explosion, path traversal và rủi ro riêng tư.

**Ghi nhớ:** **File log theo ứng dụng là đích lưu được quản lý bởi backend**, không phải một logger riêng cho từng class hay từng request. Hãy chọn file/đích theo service và instance, định tuyến log từ các class vào đó, rồi kiểm soát rotation, retention, permission, dữ liệu nhạy cảm và các quy tắc chạy nhiều JVM.
