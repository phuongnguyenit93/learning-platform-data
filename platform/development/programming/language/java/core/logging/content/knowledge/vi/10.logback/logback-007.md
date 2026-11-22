# logback-spring.xml trong Spring Boot: cấu hình Logback theo môi trường

**`logback-spring.xml`** là tên file cấu hình Logback mà **Spring Boot** có thể nạp và xử lý bằng cơ chế logging riêng. File này cho phép viết cấu hình Logback chuẩn (logger, appender, encoder, rolling file…) và sử dụng một số **phần mở rộng của Spring Boot** như `<springProfile>` để phân nhánh theo Spring profile và `<springProperty>` để đọc giá trị từ Spring `Environment`.

Tên file này không phải một khái niệm chung của Java Core hay một cú pháp mà Logback thuần tự hiểu. Nó dành cho ứng dụng có **Spring Boot + Logback** thích hợp trong runtime. Tài liệu dưới đây giải thích cách nạp file, cú pháp, ví dụ Java 17/Spring Boot và những lỗi cấu hình thường gặp, với nguyên tắc quan trọng: **cấu hình phải đúng backend, đúng thời điểm khởi tạo và đúng môi trường**.

## 1. `logback-spring.xml` dùng để làm gì?

Một ứng dụng thường phát log qua SLF4J:

```java
// Fragment trong lớp đã có SLF4J và một biến LOG.
LOG.info("event=order_received orderId={}", orderId);
```

Mã nghiệp vụ chỉ nói “phát một sự kiện ở mức INFO”. Các quyết định **in ra đâu, format thế nào, lưu bao lâu, mức DEBUG có bật hay không** được xử lý bởi logging backend, chẳng hạn Logback.

```text
Spring Boot bootstrap
      |
      | LoggingSystem nạp cấu hình log
      v
logback-spring.xml
      |
      +-- <springProperty> đọc Spring Environment
      +-- <springProfile> chọn đoạn cấu hình theo profile
      +-- <logger> / <root> đặt mức và phạm vi logger
      +-- <appender> chọn console, file, network...
      +-- <encoder> / <pattern> định dạng thông điệp
      |
      v
SLF4J Logger -> Logback -> appender -> console / file / collector
```

`logback-spring.xml` cấu hình **đường đi của log**, chứ không tạo logger cho từng class. Những lớp Java vẫn dùng `org.slf4j.LoggerFactory.getLogger(MyClass.class)` hoặc cách tương đương mà dự án đã chọn.

Các lợi ích thiết thực:

1. **Mức log theo môi trường:** bật `DEBUG` cho module khi phát triển, giới hạn `INFO` hoặc `WARN` khi vận hành.
2. **Điều chỉnh output:** console cho container, rolling file cho môi trường cần lưu file, hoặc encoder phù hợp với collector.
3. **Nhất quán theo ứng dụng:** cùng một cấu hình xử lý các logger sử dụng backend Logback, thay vì mỗi service tự tạo appender.
4. **Tận dụng Spring Environment:** tham chiếu các property như `spring.application.name`, tùy chọn với giá trị mặc định.
5. **Dễ kiểm tra:** đọc file có thể xác định vì sao `DEBUG` bị lọc, event bị in lặp hoặc ứng dụng không tạo file log.

## 2. `logback-spring.xml` khác `logback.xml` ra sao?

| Tiêu chí | `logback.xml` | `logback-spring.xml` |
| --- | --- | --- |
| Ai xử lý | Có thể được **Logback** tự tìm và nạp sớm | Được **Spring Boot LoggingSystem** nhận biết và xử lý khi Boot điều khiển logging |
| Vị trí thông dụng | Root của classpath | `src/main/resources/logback-spring.xml` → root của classpath sau khi đóng gói |
| Cú pháp Logback chuẩn | Có | Có |
| Mở rộng `<springProfile>`, `<springProperty>` | **Không dùng trực tiếp** trong chế độ Logback tự nạp sớm | Có khi Boot nạp đúng cách |
| Phù hợp với ứng dụng Spring Boot | Hợp lệ khi không cần Spring extensions | Thường ưu tiên khi cần Spring extensions hoặc muốn Boot kiểm soát khởi tạo |
| Dùng cho ứng dụng Java chỉ có Logback, không có Boot | Có | Không nên mặc định rằng Logback tự tìm và hiểu tên file này |

**Điểm quan trọng:** Spring Boot khởi tạo hệ thống logging khá sớm, trước khi toàn bộ `ApplicationContext` hoàn tất. Logback thuần có thể đọc `logback.xml` trước khi Boot sẵn sàng cung cấp các extension. Vì thế, đặt `<springProfile>` vào `logback.xml` thường gây lỗi parser; chuyển thành `logback-spring.xml` và để Boot nạp là cách được tài liệu Spring Boot khuyến nghị. Nếu cần file ở vị trí khác, có thể đặt property `logging.config` tới tài nguyên tương ứng.

**Không dùng cả hai file không kiểm soát:** Khi tồn tại nhiều cấu hình logging trong classpath, khó xác định file nào đang có hiệu lực và một file có thể được backend nạp trước Boot. Hãy giữ **một nguồn cấu hình chính có chủ đích** và kiểm tra quy tắc chọn file của phiên bản Boot đang dùng.

### File được đặt ở đâu?

Cấu trúc ứng dụng Maven phổ biến:

```text
my-app/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/Application.java
    └── resources/
        ├── application.properties
        └── logback-spring.xml
```

Trong cấu trúc này, Maven đưa file XML vào root classpath. Khi chạy executable JAR của Spring Boot, file nằm trong phần tài nguyên của ứng dụng.

Nếu chủ động dùng file ngoài classpath, cấu hình Boot có thể dùng:

```properties
logging.config=file:/opt/my-app/config/logback-spring.xml
```

Đây là **ví dụ đường dẫn**; file phải tồn tại và tiến trình có quyền đọc. Với file trong JAR, có thể chỉ định `classpath:logback-spring.xml`. Vì logging khởi tạo sớm, `logging.config` nên đến từ nguồn cấu hình được Boot đọc đủ sớm (property hệ thống, command-line hoặc `application.properties` thích hợp), không trông đợi `@PropertySource` được thêm muộn trong bean.

## 3. Cấu trúc Logback XML cơ bản

Một file `logback-spring.xml` có thể sử dụng các phần tử chuẩn:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Ý nghĩa:

- **`<configuration>`**: root của cấu hình Logback.
- **`<appender name="CONSOLE">`**: định nghĩa đích nhận event. `ConsoleAppender` thường ghi console; Logback còn có appender file, rolling file và các triển khai khác.
- **`<encoder>`** và `<pattern>`: mã hóa/định dạng event. `%d` là thời gian, `%level` là level, `%logger` là tên logger, `%msg` là message, `%n` là newline.
- **`<logger name="...">`**: điều chỉnh level cho category hoặc nhóm category.
- **`<root level="INFO">`**: đặt mức root logger. Các logger không có mức riêng thường kế thừa mức hiệu lực thích hợp theo phân cấp backend.
- **`<appender-ref>`**: gắn appender đã định nghĩa vào logger/root. Chỉ định nghĩa một appender thôi chưa bảo đảm event sẽ được gửi tới appender ấy.

Đoạn XML là **một cấu hình hợp lệ cho ứng dụng có Logback**, chưa phụ thuộc Spring extensions. Với file chứa đúng XML này, có thể dùng cả `logback.xml` nếu ứng dụng không cần `springProfile` và `springProperty`.

Lưu ý: logger con có thể truyền sự kiện lên logger cha theo cơ chế additivity của Logback. Nếu gắn cùng một đích tại cả hai tầng mà vẫn bật additivity, cùng một event có thể bị ghi **trùng** ở console hoặc file.

## 4. `<springProfile>`: cấu hình theo Spring profile

Phần mở rộng `springProfile` cho phép bật một đoạn cấu hình khi một biểu thức Spring profile phù hợp:

```xml
<springProfile name="dev">
    <logger name="com.example.logging" level="DEBUG"/>
</springProfile>

<springProfile name="!dev">
    <logger name="com.example.logging" level="INFO"/>
</springProfile>
```

Hai đoạn trên là **fragment cần đặt bên trong `<configuration>`** của `logback-spring.xml`. Khi profile `dev` được kích hoạt, logger thuộc `com.example.logging` được đặt mức `DEBUG`; khi `dev` không hoạt động, đặt mức `INFO`.

Các cách dùng được Spring Boot hỗ trợ có thể bao gồm:

- `name="dev"`: chỉ khi `dev` active.
- `name="!prod"`: khi `prod` không active.
- `name="dev | staging"`: khi ít nhất một trong hai profile active.
- `name="prod & eu"`: khi cả hai active. Trong XML attribute, ký tự `&` phải escape thành `&amp;`: `name="prod &amp; eu"`.

**Tên profile không phải tên file:** profile `dev` có thể được kích hoạt qua `--spring.profiles.active=dev`, `SPRING_PROFILES_ACTIVE` hoặc cấu hình application. Không nên hardcode nhiều `spring.profiles.active` trái ngược ở các nguồn mà không hiểu quy tắc ưu tiên cấu hình.

### `springProfile` không phải là level ở ứng dụng Java

Lời gọi `log.debug(...)` vẫn có trong mã nguồn ở mọi môi trường. Việc event có xuất hiện hay không phụ thuộc **level hiệu lực** của logger và filter/appender. Không viết `if (dev) log.debug(...)` chỉ để thay thế chính sách logging; profile và level trong config là cơ chế đúng hơn trong trường hợp chỉ thay đổi độ chi tiết.

## 5. `<springProperty>`: lấy giá trị từ Spring Environment

Khi muốn chèn tên ứng dụng vào log, file Boot có thể đọc `spring.application.name` từ `application.properties`:

```properties
spring.application.name=order-service
```

Trong `logback-spring.xml`:

```xml
<springProperty scope="context"
                name="serviceName"
                source="spring.application.name"
                defaultValue="unknown-service"/>

<appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level service=${serviceName} %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

Đây là **fragment**: cần đặt trong `<configuration>`, và appender phải được tham chiếu bởi root hoặc logger mới nhận event. Sau khi Boot nạp file, `springProperty` đặt một Logback property tên `serviceName`, dùng được trong `<pattern>`. Nếu Spring Environment không có key tương ứng, `defaultValue` đưa ra giá trị dự phòng.

Phân biệt:

| Cú pháp | Nguồn giá trị | Ý nghĩa |
| --- | --- | --- |
| `<springProperty source="spring.application.name" .../>` | Spring `Environment` | Lấy property do Boot quản lý để dùng trong Logback |
| `<property name="..." value="..."/>` | Cấu hình Logback | Khai báo property Logback trực tiếp |
| `${serviceName}` | Logback property đã được đặt | Tham chiếu giá trị bên trong cấu hình XML |
| `%X{requestId}` | MDC của event | Chèn request ID nếu ứng dụng/tracing đã đưa vào MDC |

Với `springProperty`, tên `source` phải dùng **cách viết kebab-case theo quy ước** của Spring Boot khi cần dấu nối, ví dụ `my.feature-name` thay vì tùy tiện dựa vào relaxed binding. Một `springProperty` không tự động lấy giá trị từ bean Spring được tạo muộn, và **không nên sử dụng nó để đưa secret vào log**.

Các giá trị về cơ sở dữ liệu, password, access token hoặc key bí mật có thể tồn tại trong Spring Environment nhưng **không được lấy ra in vào pattern**. `springProperty` là tiện ích cấu hình, không phải một giải pháp bảo mật.

## 6. Ví dụ có thể chạy: Spring Boot + Java 17 + `logback-spring.xml`

Ví dụ sử dụng **Spring Boot 3.5.16**, Java 17 và Maven. Đây là một phiên bản cụ thể để mô tả bài thực hành, không khẳng định là phiên bản mới nhất tại mọi thời điểm. Mã tạo một ứng dụng không có web server, chạy `CommandLineRunner` để phát log và kết thúc. Chỉ sử dụng `spring-boot-starter`, vốn mang các dependency logging thích hợp trong cấu hình starter thông thường.

Cấu trúc:

```text
logback-spring-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/LoggingConfigDemo.java
    └── resources/
        ├── application.properties
        └── logback-spring.xml
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>logback-spring-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Nhờ parent của Spring Boot quản lý dependency và plugin versions, ví dụ **không tự gắn thêm Logback hoặc SLF4J provider song song**. Nếu dự án của bạn thay `spring-boot-starter-logging` bằng Log4j 2, file `logback-spring.xml` sẽ không còn là nơi cấu hình backend mà bạn đang chạy.

### 6.2. `application.properties`

```properties
spring.application.name=logging-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
```

Không đặt `spring.profiles.active` cố định trong file này để có thể chạy thử **có và không có profile `dev`** bằng tham số command line.

### 6.3. `logback-spring.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="unknown-service"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level service=${serviceName} %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <logger name="com.example.logging" level="DEBUG"/>
    </springProfile>

    <springProfile name="!dev">
        <logger name="com.example.logging" level="INFO"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là **toàn bộ file**, không phải fragment. `springProperty` đọc `spring.application.name`, cho ra `service=logging-demo` trong pattern. `springProfile` chọn level cho logger package `com.example.logging`. `root` giữ mức INFO và gắn một console appender duy nhất, tránh trùng log.

Cấu hình trên **không cần `scan="true"`** và không tự thêm file appender. Trong hệ thống production, cần cân nhắc timestamp có timezone, structured log, exception pattern, MDC và cơ chế thu thập phù hợp; pattern ngắn ở đây chủ yếu để dễ so sánh.

### 6.4. `LoggingConfigDemo.java`

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoggingConfigDemo implements CommandLineRunner {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingConfigDemo.class);

    public static void main(String[] args) {
        SpringApplication.run(LoggingConfigDemo.class, args);
    }

    @Override
    public void run(String... args) {
        LOG.debug("event=debug_probe requestId={}", "req-17");
        LOG.info("event=sample_ready requestId={}", "req-17");
        System.out.println("demoFinished=true");
    }
}
```

Java code chỉ dùng SLF4J API qua Spring Boot starter, không nhúng logic `if (dev)` vào các lời gọi logger. Thay đổi profile chỉ thay đổi cấu hình, không thay đổi class đã biên dịch.

### 6.5. Biên dịch và chạy

Trong thư mục `logback-spring-demo/`:

```bash
mvn -q package
java -jar target/logback-spring-demo-0.0.1-SNAPSHOT.jar
```

Lần chạy **không có `dev`** sẽ ghi log của chính ví dụ tương tự:

```text
10:15:30.125 INFO  service=logging-demo com.example.logging.LoggingConfigDemo - event=sample_ready requestId=req-17
demoFinished=true
```

Đây là **đoạn minh họa**: timestamp thực khác nhau, Spring Boot còn ghi các event khởi động khác, và console có thể gộp stdout với output của backend. Trong chính chương trình, lệnh `System.out.println` in **chính xác** một dòng `demoFinished=true`; việc đó không đồng nghĩa toàn bộ stdout chỉ có một dòng.

Chạy với profile `dev`:

```bash
java -jar target/logback-spring-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
```

Khi đó hai log do `CommandLineRunner` phát có dạng:

```text
10:15:30.125 DEBUG service=logging-demo com.example.logging.LoggingConfigDemo - event=debug_probe requestId=req-17
10:15:30.126 INFO  service=logging-demo com.example.logging.LoggingConfigDemo - event=sample_ready requestId=req-17
demoFinished=true
```

Đây cũng là **minh họa**; thời gian và thứ tự với các log khởi động của Spring Boot không cố định. Điểm cần kiểm tra là `DEBUG` chỉ được phép hiển thị khi profile `dev` kích hoạt, còn `INFO` và thông điệp `demoFinished=true` xuất hiện ở cả hai lượt chạy.

**Bước tự kiểm tra:** Bỏ hoặc đổi tên `src/main/resources/logback-spring.xml`, build lại rồi so sánh định dạng mặc định của Spring Boot. Khi dùng file riêng, pattern `service=logging-demo` sẽ thấy trong log do `CONSOLE` ghi. Nếu không thấy, kiểm tra tên file, vị trí classpath, backend thực tế và `logging.config`.

## 7. Dùng cấu hình mẫu của Spring Boot bằng `<include>`

Không phải lúc nào cũng cần tự viết toàn bộ pattern và appender. Spring Boot cung cấp các resource có thể include, ví dụ:

- `org/springframework/boot/logging/logback/defaults.xml`: một số conversion rule và pattern property mặc định.
- `org/springframework/boot/logging/logback/console-appender.xml`: định nghĩa console appender thông dụng.
- `org/springframework/boot/logging/logback/file-appender.xml`: định nghĩa file appender với chính sách được Boot cung cấp.
- Ở các nhánh Spring Boot hỗ trợ structured logging, còn có những include cho structured console/file appender; cần đối chiếu phiên bản Boot đang chạy.

Ví dụ **một cấu hình thay thế hoàn chỉnh** cho `logback-spring.xml`, không ghép với file ở mục 6:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Như vậy, Spring Boot có thể duy trì các quy ước pattern/console của chính framework. Không dùng cả file cấu hình thay thế và file ở mục 6 trong cùng một vị trí rồi giả định Spring Boot sẽ tự hợp nhất chúng. Nếu muốn tùy chỉnh riêng, chủ động chọn một chiến lược cấu hình rõ ràng.

**Lưu ý theo phiên bản:** Các include và thuộc tính được Boot cung cấp có thể thay đổi giữa những nhánh phiên bản; `base.xml` là resource tương thích đời cũ ở một số phiên bản nhưng không nên coi là nền tảng bắt buộc cho cấu hình mới. Kiểm tra tài liệu tương ứng với Spring Boot đang chạy.

## 8. Console, rolling file và môi trường triển khai

Console phù hợp với nhiều ứng dụng chạy trong container: hệ thống ngoài có thể thu stdout/stderr từ tiến trình. File log hữu ích nếu môi trường yêu cầu file cục bộ và có chính sách giữ/đẩy log phù hợp. Chọn đích ghi theo kiến trúc vận hành, **không phải chỉ vì file appender có thể được cấu hình**.

Nếu cần thêm rolling file trong một ứng dụng có Logback, đoạn **fragment** dưới đây có thể được đặt bên trong `<configuration>` rồi tham chiếu bằng `<appender-ref ref="FILE"/>` ở root hoặc logger phù hợp:

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>20MB</maxFileSize>
        <maxHistory>14</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

Giải thích:

- `<file>` chỉ đường dẫn file đang được ghi. Đường dẫn tương đối được giải theo thư mục làm việc của tiến trình.
- `SizeAndTimeBasedRollingPolicy` hỗ trợ rotation theo thời gian và kích thước; `%d` và `%i` là thành phần tên file archive.
- `maxHistory` giới hạn lịch sử theo số kỳ; `totalSizeCap` giới hạn tổng dung lượng lưu trữ archive theo chính sách.
- `<appender-ref>` phải gắn FILE vào logger/root phù hợp. Việc **chỉ khai báo appender** không tự tạo ra output khi chưa có event được chuyển tới nó.

**Không tự đưa file appender vào production mà bỏ qua** quyền ghi thư mục, filesystem read-only, quota, vòng đời container, retention, backup và chi phí lưu trữ. Nếu chỉ dùng file mà không dùng console, cần kiểm tra hệ thống thu thập còn lấy được log hay không.

Spring Boot cũng có các property như `logging.file.name` và một số tùy chỉnh rolling policy; tuy nhiên khi bạn đã tự định nghĩa đầy đủ file appender/rolling policy trong XML, **đừng mặc định** các property Spring Boot tự thay đổi appender đó. Phải nhìn rõ giá trị nào thực sự được tham chiếu trong XML.

## 9. Precedence giữa `application.properties` và Logback XML

Trong Spring Boot, có hai nơi thường được sử dụng để chọn level:

**Spring Environment:**

```properties
logging.level.root=INFO
logging.level.com.example.logging=DEBUG
```

**Logback XML:**

```xml
<logger name="com.example.logging" level="INFO"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
```

Đây là **hai cách cấu hình minh họa riêng biệt**. Khi dùng đồng thời, Spring Boot LoggingSystem có thể áp dụng cấu hình level lấy từ Environment trong quá trình khởi tạo, khiến level hiệu lực khác so với XML đã viết. Tránh tuyên bố “XML luôn thắng” hay “properties luôn thắng” cho mọi khía cạnh; cần kiểm tra cơ chế/phiên bản Boot và cấu hình thực tế.

Một cách phân chia trách nhiệm dễ bảo trì:

- Dùng `application.properties`/`application.yaml` cho các mức log đơn giản và thông tin cấu hình ứng dụng.
- Dùng `logback-spring.xml` khi cần pattern, appender, filter, rolling policy hoặc phần mở rộng theo profile.
- Không phân tán cùng một quy tắc level qua nhiều nơi nếu không có chủ đích.
- Chỉ dùng `logging.config` khi cần chỉ định file cấu hình ở vị trí khác hoặc quy ước dự án yêu cầu.

Các property kiểu `logging.file.name`, `logging.pattern.console` hoặc `logging.structured.format.console` có vai trò tùy thuộc cấu hình backend. Một custom `<encoder>` với pattern ghi cứng **không tự đọc mọi property tùy chỉnh** của Spring Boot nếu XML không tham chiếu chúng hoặc không dùng include phù hợp.

## 10. Kết hợp MDC, structured logging và exception

Để điều tra lỗi xuyên request, một pattern text có thể thêm MDC:

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} traceId=%X{traceId} %logger - %msg%n</pattern>
```

Đây là **fragment bên trong encoder**, không phải một file Logback hoàn chỉnh. `%X{requestId}` và `%X{traceId}` chỉ có dữ liệu nếu ứng dụng hoặc instrumentation đã điền MDC. `logback-spring.xml` không tự sinh request ID, không tự tạo distributed trace và không tự chuyển MDC qua mọi thread pool. Khi dùng async hoặc reactive, cần context propagation và cleanup đúng để không gán sai ID giữa các request.

Với exception:

```java
// Fragment trong ứng dụng có SLF4J; LOG và biến e đã được khai báo.
LOG.error("event=operation_failed requestId={}", requestId, e);
```

`Throwable` được chuyển đến backend để layout/encoder quyết định cách trình bày stack trace. Khi chỉnh custom pattern, cần kiểm tra stack trace thực sự được ghi; Logback có các conversion words cho exception và có thể tự thêm thông tin ngoại lệ trong một số cấu hình, nhưng không nên dựa vào điều đó nếu bạn đã cấu hình encoder/layout đặc thù.

**Structured logging:** Nếu collector cần mỗi event là một JSON object, nên dùng formatter/encoder có hỗ trợ JSON và escaping thay vì tự ghép message JSON bằng chuỗi. Các phiên bản Spring Boot mới có hỗ trợ structured logging riêng; cách bật và format phụ thuộc nhánh phiên bản. Đừng đặt `<pattern>` JSON nối chuỗi tự phát rồi cho rằng dữ liệu người dùng đã được escape đúng.

Không ghi `Authorization`, cookie phiên, token, password hoặc payload cá nhân nhạy cảm vào message hay MDC. `springProperty` cũng không phải cách hợp lệ để đưa secret vào output.

## 11. Những lỗi phổ biến với `logback-spring.xml`

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| File XML không có tác dụng | Đặt sai tên hoặc sai `src/main/resources`; runtime dùng backend khác | Kiểm tra JAR/classpath, `logging.config`, provider/backend thực |
| `no applicable action for [springProfile]` | Extension bị nạp bởi Logback thuần hoặc scan lại cấu hình | Dùng `logback-spring.xml` do Boot nạp; tránh `scan="true"` với extensions |
| `no applicable action for [springProperty]` | File nạp sai thời điểm hoặc không được Boot xử lý | Kiểm tra cách nạp file và cơ chế scan |
| `serviceName_IS_UNDEFINED` hoặc property không đúng | Sai tên `source`, không có giá trị, phạm vi Logback property sai | Dùng kebab-case phù hợp, kiểm tra `spring.application.name`, `defaultValue` |
| Không thấy `DEBUG` trong `dev` | Profile chưa active, logger category không khớp, filter khác chặn | Kiểm tra active profiles, mức logger hiệu lực và appender |
| Log bị in hai lần | Hai appender console, additivity hoặc cấu hình chồng chéo | Kiểm tra đường đi logger → root → appender |
| File log không được tạo | FILE chưa được gắn, path không ghi được, appender lỗi khởi tạo | Kiểm tra `appender-ref`, đường dẫn/quyền và internal Logback status |
| Console có log nhưng collector không thấy | Collector đọc sai stream hoặc format không phù hợp | Kiểm tra stdout/stderr, pipeline, parser, việc thu thập trong container |
| Pattern không theo `logging.pattern.console` | Custom encoder có pattern riêng không tham chiếu property Boot | Chọn include của Boot hoặc chủ động nối property vào XML |
| `logging.level.*` khác mức dự kiến | Level được khai báo ở nhiều nơi hoặc profile khác đang active | Kiểm tra cấp cấu hình và hiệu lực runtime |
| Cấu hình scan gây lỗi sau khi sửa XML | Logback quét lại file nhưng extension Boot không có trong lần parse | Tắt scan, dùng cách reload được Boot/framework hỗ trợ |
| Dùng XML của Logback với Log4j 2 | Backend không hiểu cú pháp hoặc file bị bỏ qua | Dùng cấu hình của backend đang chạy, ví dụ `log4j2-spring.xml` nếu đã chuyển Log4j 2 |

**Trình tự điều tra đề xuất:**

1. Xác nhận ứng dụng thực sự đang dùng **Spring Boot + Logback** và có provider tương thích.
2. Xác nhận file ở **đúng classpath** và `logging.config` không trỏ sang file khác.
3. Kiểm tra log khởi động để phát hiện XML parse error, appender thiếu hoặc property không tồn tại.
4. Kiểm tra Spring profile đang active trước khi kết luận `springProfile` sai.
5. Kiểm tra category logger, level, filter, additivity và appender-ref theo đúng nhánh.
6. So sánh một event `INFO` và một event `DEBUG` giữa hai profile; kiểm tra nội dung tại đích thực tế.
7. Nếu dùng file/collector, xác minh đường dẫn, quyền và pipeline lấy dữ liệu, không chỉ việc logger được gọi.

## 12. Quy tắc triển khai và checklist

Trước khi đưa `logback-spring.xml` vào dự án, kiểm tra:

- **Đúng backend:** runtime dùng Logback và có dependency/provider phù hợp; không cấu hình nhầm Log4j 2.
- **Đúng đường dẫn:** `src/main/resources/logback-spring.xml` hoặc file chỉ định qua `logging.config`; tránh nhiều file config cạnh tranh.
- **Đúng cơ chế Spring:** `springProfile` và `springProperty` chỉ được dùng trong cấu hình Boot thực sự nạp; không bật scan tự động của Logback cùng extensions.
- **Đúng phạm vi profile:** thử `dev`, `prod` và trường hợp không có profile; không để `DEBUG` chi tiết xuất hiện ngoài ý muốn.
- **Đúng logger và appender:** root/logger có `appender-ref`, additivity hợp lý, không phát log trùng.
- **Đúng định dạng:** timestamp có timezone rõ ràng ở môi trường vận hành, level, logger name, service, correlation ID và stack trace khi cần.
- **Đúng dữ liệu:** không có password, token, cookie phiên, PII không được phép; input không tin cậy được encode/escape.
- **Đúng lưu trữ:** rolling/retention, dung lượng, quyền ghi file hoặc collector được cấu hình và kiểm thử.
- **Đúng phối hợp cấu hình:** không vô tình ghi đè nhau giữa `application.properties`, `logging.level.*` và XML.
- **Đúng phiên bản:** các include, extension và key properties tương thích với phiên bản Spring Boot/Logback cụ thể.

**Ghi nhớ:** `logback-spring.xml` là **cấu hình Logback được Spring Boot điều khiển**, hữu ích nhất khi cần profile và property của Spring cùng các appender/encoder của Logback. Mã Java tiếp tục phát log qua SLF4J; Boot nạp cấu hình vào đúng thời điểm để chọn mức, format và đích ghi. Cấu hình tốt phải **đọc được, kiểm thử được ở từng môi trường và không làm lộ dữ liệu**.

## Tài liệu chính thức

- Spring Boot, *Logging (reference)*: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot, *Configure Logback for Logging*: https://docs.spring.io/spring-boot/how-to/logging.html
- Logback, *Configuration*: https://logback.qos.ch/manual/configuration.html
