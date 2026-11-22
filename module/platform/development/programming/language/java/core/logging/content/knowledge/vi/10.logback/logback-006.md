# logback.xml: Cấu hình Logback trong ứng dụng Java

## 1. logback.xml là gì?

**logback.xml** là tệp cấu hình XML tiêu chuẩn của **Logback**, một hệ thống logging được dùng phổ biến cùng **SLF4J** trong ứng dụng Java. Tệp này cho Logback biết **ghi những sự kiện nào, ghi theo định dạng gì và gửi đến đâu**: console, file, một appender bất đồng bộ hoặc những đích được cấu hình khác.

Ví dụ, cùng một ứng dụng có thể muốn:
- Giữ bản ghi từ **INFO** trở lên ở môi trường vận hành thông thường.
- Chỉ bật **DEBUG** cho package đang cần điều tra.
- In log ra **stdout** khi chạy trong container.
- Nếu dùng file, giới hạn dung lượng và xoay vòng file cũ.
- Gắn timestamp, tên thread, level, logger, request ID và exception.
- Tránh cùng một sự kiện bị ghi hai lần do cấu hình **additivity**.

Kiến trúc cơ bản:

~~~text
Mã Java
    |
    | org.slf4j.Logger.info/debug/error(...)
    v
SLF4J API
    |
    | provider tương thích
    v
Logback Classic: logger, level, filter, additivity
    |
    v
Logback Core: appender + encoder/layout
    |
    +--> ConsoleAppender --> stdout hoặc stderr
    +--> RollingFileAppender --> file đang ghi + file archive
    +--> AsyncAppender --> hàng đợi --> appender đích
~~~

**SLF4J là API**, còn **Logback Classic** là provider/backend triển khai. Nếu dự án chỉ có slf4j-api mà không có provider Logback phù hợp, việc đặt một file logback.xml trong classpath chưa đảm bảo file sẽ điều khiển log. Ngược lại, nếu ứng dụng đang dùng provider khác, phải cấu hình theo provider đó.

### Đặt file ở đâu?

Với Maven và Gradle, vị trí thông dụng là:

~~~text
src/main/resources/logback.xml
~~~

Sau khi đóng gói, file phải xuất hiện trong **runtime classpath**, thường ở gốc classpath hoặc bên trong JAR của ứng dụng. Đường dẫn này là đường dẫn **nguồn**; Logback đọc tài nguyên khi ứng dụng khởi tạo, không trực tiếp đọc thư mục source trong mọi cách triển khai.

Với unit test, có thể đặt cấu hình riêng ở:

~~~text
src/test/resources/logback-test.xml
~~~

Theo cơ chế tìm cấu hình mặc định của Logback, file **logback-test.xml** có thể được ưu tiên trước **logback.xml** khi cả hai cùng nằm trong classpath thử nghiệm. Vì vậy một bài test in DEBUG không có nghĩa chương trình chạy production cũng dùng DEBUG.

Có thể chỉ định cấu hình ngoài ứng dụng bằng system property của JVM:

~~~bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -jar myapp.jar
~~~

Đường dẫn chỉ mang tính minh họa. Property này thuộc Logback; nó **khác** với **-Djava.util.logging.config.file**, vốn dùng cho JUL. Với Spring Boot, còn có cơ chế **logging.config** và file **logback-spring.xml** được trình bày ở phần sau.

## 2. Cấu trúc cơ bản của logback.xml

Ví dụ đơn giản, chỉ ghi lên console:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ý nghĩa của từng phần:

| Thành phần | Công dụng |
| --- | --- |
| **configuration** | Phần tử gốc chứa cấu hình Logback |
| **appender** | Đích ghi log cụ thể: console, file, rolling file... |
| **name** | Tên định danh để Logger hoặc appender khác tham chiếu |
| **class** | Lớp triển khai Appender của Logback |
| **target** | Chọn **System.out** hoặc **System.err** cho ConsoleAppender |
| **encoder** | Chuyển sự kiện log thành văn bản/byte trước khi ghi |
| **pattern** | Mẫu hiển thị thời gian, level, logger và thông điệp |
| **root** | Logger gốc, nơi các logger con có thể thừa kế level và chuyển sự kiện tới appender |
| **appender-ref** | Kết nối root hoặc logger với appender đã được khai báo |

Khi root ở **INFO**, những lời gọi INFO, WARN và ERROR của logger kế thừa mức này được chấp nhận. DEBUG và TRACE bị chặn ở logger đó. Nếu một logger con đặt mức DEBUG riêng, bản ghi DEBUG của nó có thể đi tới appender của root theo cơ chế **additivity**. Mức INFO của root không được áp lại như một bộ lọc lần thứ hai cho bản ghi đã được logger con chấp nhận; tuy nhiên **bộ lọc của appender** vẫn có thể chặn.

**Không nhầm cấu hình Logback với cấu hình JUL:** Logback thường dùng TRACE, DEBUG, INFO, WARN, ERROR; JUL dùng FINE/FINER/FINEST, INFO, WARNING, SEVERE. Tên appender, XML và đường nạp file cũng khác.

## 3. Ví dụ Java 17 + Maven có thể chạy được

Ví dụ này chứng minh **logback.xml điều khiển mức log theo class**. Ứng dụng gồm một lớp main và một lớp giả lập thao tác thanh toán. Cả hai dùng **SLF4J API**, còn Logback định nghĩa nơi xuất và ngưỡng.

Mục tiêu đầu ra:
- Logger gốc ở **INFO**, nên DEBUG của lớp main bị ẩn.
- Logger **demo.PaymentService** ở **DEBUG**, nên DEBUG của lớp này xuất hiện.
- Appender xuất log ra stdout với pattern cố định để không phụ thuộc timestamp và thread.

### 3.1. Cấu trúc thư mục

~~~text
logback-xml-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          LogbackXmlDemo.java
      resources/
        logback.xml
~~~

### 3.2. pom.xml

Ví dụ sử dụng **Logback Classic 1.5.16** tương thích với dòng **SLF4J 2.x**. Phiên bản được cố định để minh họa một bộ dependency rõ ràng; khi dùng trong dự án thật, hãy theo bộ phiên bản đã được quản lý và kiểm thử của dự án.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>logback-xml-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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
~~~

**logback-classic** kéo theo các dependency cần thiết gồm **logback-core** và API SLF4J tương thích. Trong dự án lớn, có thể khai báo API trực tiếp và quản lý phiên bản bằng BOM/dependency management. Không nên thêm đồng thời một provider khác như **slf4j-simple** vào classpath demo vì chúng cạnh tranh vai trò backend.

### 3.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger{0} | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.PaymentService" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Chỉ có một appender CONSOLE** gắn với root. Logger PaymentService đặt mức DEBUG nhưng không có appender riêng; nó vẫn truyền sự kiện đã được chấp nhận tới appender của root vì **additivity mặc định là true**.

### 3.4. src/main/java/demo/LogbackXmlDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LogbackXmlDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LogbackXmlDemo.class);

    public static void main(String[] args) {
        LOG.debug("Startup diagnostic hidden");
        LOG.info("Application started");

        new PaymentService().charge("ORD-42");
    }
}

final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    void charge(String orderId) {
        LOG.debug("Gateway retry limit={}", 2);
        LOG.info("Payment accepted orderId={}", orderId);
    }
}
~~~

Đây là tệp Java hợp lệ: có đúng **một public class** tên LogbackXmlDemo trùng tên tệp; PaymentService là một lớp package-private trong cùng package **demo**. Cả hai dùng LoggerFactory.getLogger(Class) và SLF4J placeholder **{}**.

### 3.5. Biên dịch, chạy và giải thích kết quả

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.LogbackXmlDemo
~~~

**Stdout từ các sự kiện log của chương trình:**

~~~text
INFO | LogbackXmlDemo | Application started
DEBUG | PaymentService | Gateway retry limit=2
INFO | PaymentService | Payment accepted orderId=ORD-42
~~~

Phân tích:
1. **LOG.debug** của LogbackXmlDemo bị chặn vì logger này kế thừa root INFO.
2. **LOG.info** của LogbackXmlDemo xuất hiện.
3. **demo.PaymentService** có ngưỡng DEBUG riêng, nên cả DEBUG và INFO đều xuất hiện.
4. **%logger{0}** rút gọn tên logger để chỉ hiển thị phần tên class ở cuối, nên đầu ra không có tiền tố **demo.**.
5. **%level**, **%msg** và **%n** lần lượt in level, thông điệp và xuống dòng.
6. **System.out** được chọn có chủ đích. Logback ConsoleAppender có thể xuất sang stdout hoặc stderr tùy target; kết quả trên chỉ đúng với XML của ví dụ.

Maven có thể ghi thêm thông báo khi tải dependency hoặc khi có vấn đề cấu hình; chúng không phải các dòng log nghiệp vụ được định nghĩa trong ví dụ. Nếu kết quả khác, kiểm tra runtime classpath, provider, vị trí logback.xml và tên logger trước khi đổi code.

## 4. Root logger, named logger và kế thừa mức log

Có hai khái niệm quan trọng:

- **Root logger:** Logger gốc của hệ thống phân cấp Logback. Nó thường chứa mức mặc định và các appender dùng chung.
- **Named logger:** Logger có tên, thường từ **LoggerFactory.getLogger(MyClass.class)**. Tên thường theo package/class, chẳng hạn **com.example.payment.PaymentClient**.

Ví dụ:

~~~xml
<logger name="com.example" level="INFO"/>
<logger name="com.example.payment" level="DEBUG"/>
<logger name="com.example.payment.PaymentClient" level="TRACE"/>

<root level="WARN">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Giả sử CONSOLE đã được khai báo hợp lệ. Khi đó, các Logger có tên:
- **com.example.orders.OrderService** thường lấy mức hiệu lực từ **com.example = INFO**.
- **com.example.payment.InventoryCheck** lấy mức hiệu lực từ **com.example.payment = DEBUG** nếu không có cấu hình riêng phù hợp.
- **com.example.payment.PaymentClient** có ngưỡng **TRACE** theo cấu hình trực tiếp.
- Một logger ngoài nhánh **com.example** có thể kế thừa root **WARN**, trừ khi có cấu hình ở nhánh khác.

Đó là ví dụ về **kế thừa ngưỡng**. Khi một logger con phát sự kiện, Logback xét ngưỡng hiệu lực của chính logger nơi gọi; sau đó việc truyền đến các appender tổ tiên phụ thuộc additivity. Root không tự lọc lại mức logger con chỉ vì root có mức cao hơn. Nếu muốn hạn chế dữ liệu đi đến một appender cụ thể, đặt bộ lọc tại appender.

Để thay đổi production có kiểm soát, có thể chỉ bật DEBUG cho **com.example.payment.PaymentClient** thay vì bật DEBUG toàn bộ root.

### Mức log của Logback

Thứ tự mức thông dụng từ chi tiết tới nghiêm trọng:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

**OFF** là mức đặc biệt để tắt logger theo ngưỡng; **ALL** là mức đặc biệt cho phép mọi mức. Việc một bản ghi xuất hiện còn phụ thuộc Filter, appender, tình trạng provider và đích thu thập.

## 5. Additivity và lỗi log bị nhân đôi

**Additivity** xác định liệu sự kiện từ một named logger có được chuyển lên appender gắn với logger cha hay không. Theo mặc định, **additivity=true**.

Ví dụ dễ gây log trùng:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%level | %logger | %msg%n</pattern>
    </encoder>
</appender>

<logger name="com.example.payment" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Ở đây **cùng CONSOLE** được gắn vào logger **com.example.payment** và root. Vì logger con vẫn có additivity=true, sự kiện từ nhánh payment có thể được gửi tới **cùng appender hai lần**. Thời điểm root ghi thêm không có nghĩa hai exception khác nhau đã xảy ra.

Có hai hướng sửa, tùy mục tiêu:

**Cách A — Dùng appender chung ở root:** Chỉ khai báo mức riêng cho logger con, bỏ appender-ref ở logger con.

~~~xml
<logger name="com.example.payment" level="DEBUG"/>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

**Cách B — Cho logger con dùng tuyến appender riêng:** Gắn appender mong muốn vào logger con và đặt **additivity=false**.

~~~xml
<logger name="com.example.payment"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Cách B không chuyển sự kiện của logger payment đến appender thuộc logger cha. **Nếu đặt additivity=false nhưng không gắn appender nào thích hợp vào nhánh này, log có thể biến mất khỏi các đích mong đợi.** Khi cần payment ghi cả console và file, phải gắn đủ appender cho nó hoặc để kế thừa theo thiết kế phù hợp.

Không nên mặc định gắn một appender mới cho mỗi class. Trong phần lớn ứng dụng, khai báo appender ở root và chỉ cấu hình level theo package/class dễ bảo trì hơn.

## 6. Lọc thêm tại appender

Level ở Logger quyết định có tạo sự kiện hay không. Một **Filter của appender** tiếp tục quyết định sự kiện đó có được appender ghi không.

Ví dụ muốn console chỉ in từ WARN trở lên dù các logger khác có thể bật DEBUG:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>
    <encoder>
        <pattern>%level | %logger{36} | %msg%n</pattern>
    </encoder>
</appender>
~~~

**ThresholdFilter** cho phép các sự kiện có mức bằng hoặc nghiêm trọng hơn WARN đi qua appender này. Nếu Logger phát một bản ghi DEBUG hợp lệ, appender trên vẫn không in nó.

Nếu có hai appender, ví dụ CONSOLE nhận INFO+ và FILE nhận DEBUG+, mỗi appender có thể có bộ lọc riêng. Khi chẩn đoán không thấy log, phải kiểm tra:
1. Level hiệu lực của Logger.
2. Filter trên Logger (nếu có).
3. Additivity và đường truyền đến appender.
4. Level/filter của appender.
5. Encoder, quyền ghi, nơi xuất và collector đang nhận dữ liệu.

**Không nên dùng level ERROR thay cho một chính sách cảnh báo sự cố.** Có những lỗi tạm được retry thành công và không cần paging, trong khi một WARN lặp liên tục có thể phản ánh suy giảm đáng kể.

## 7. Ghi file và xoay vòng bằng RollingFileAppender

Khi vận hành trên máy chủ hoặc ứng dụng cần lưu log vào file, **RollingFileAppender** giúp tránh một file tăng dung lượng mãi mãi. Nó phối hợp với **rollingPolicy** để đổi sang archive dựa trên thời gian, kích thước hoặc cả hai.

Ví dụ **ghi file hiện tại** và xoay theo ngày *và* kích thước với **SizeAndTimeBasedRollingPolicy**:

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Ý nghĩa:

| Cấu hình | Công dụng |
| --- | --- |
| **file** | Tên file đang ghi (ví dụ logs/application.log) |
| **fileNamePattern** | Tên archive; **%d** là ngày, **%i** là chỉ số khi file cùng ngày vượt ngưỡng |
| **maxFileSize** | Ngưỡng kích thước cho một phần archive khi dùng chính sách kết hợp kích thước + thời gian |
| **maxHistory** | Số kỳ archive cũ cần giữ theo chính sách; ở mẫu này là 7 kỳ ngày |
| **totalSizeCap** | Giới hạn tổng dung lượng archive thuộc chính sách khi điều kiện dọn lịch sử được áp dụng |
| **.gz** | Archive được nén khi rollover |
| **%ex** | Chèn thông tin exception/stack trace khi sự kiện có Throwable |

**TimeBasedRollingPolicy** thuần khác với **SizeAndTimeBasedRollingPolicy**. Nếu dùng chính sách kết hợp kích thước + ngày, pattern phải có cả **%d** và **%i** để xác định từng archive trong ngày. Không chuyển maxFileSize vào một cấu hình policy không hỗ trợ rồi kỳ vọng nó hoạt động.

### Lưu ý khi chạy production

- Đảm bảo tiến trình có quyền ghi đúng thư mục. Nếu không tạo/ghi được file, Logback có thể báo lỗi nội bộ ở lúc khởi động.
- Quy định thời gian lưu theo nhu cầu điều tra, chi phí và yêu cầu bảo mật; các số 7 ngày, 10 MB, 1 GB trong ví dụ **không phải tiêu chuẩn bắt buộc**.
- Không để nhiều tiến trình JVM độc lập cùng ghi vào một file theo cấu hình thông thường nếu không có cơ chế phối hợp phù hợp; có thể gây cạnh tranh hoặc mất dữ liệu.
- Với container/Kubernetes, một cấu hình phổ biến là **ghi stdout/stderr** để nền tảng thu thập tập trung, thay vì cố quản lý file quay vòng bên trong container ngắn hạn.
- Không nhầm archive đã nén với hệ thống bảo quản log bất biến. Log audit, security và log có yêu cầu pháp lý cần thiết kế lưu trữ và kiểm soát riêng.

## 8. Thuộc tính (property) và biến môi trường

Hard-code đường dẫn log vào một file XML có thể khó khi chạy cùng ứng dụng ở Windows, Linux, container hoặc môi trường triển khai khác nhau. Logback hỗ trợ khai báo và tham chiếu property trong cấu hình.

Ví dụ:

~~~xml
<configuration>
    <property name="APP_NAME" value="checkout"/>
    <property name="LOG_DIR" value="logs"/>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>${LOG_DIR}/${APP_NAME}.log</file>
        <encoder>
            <pattern>${APP_NAME} | %level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Cú pháp **${NAME}** thay biến đã được khai báo. Logback cũng hỗ trợ nguồn property từ cấu hình, system properties hoặc environment theo cơ chế phân giải biến của nó. Chẳng hạn, có thể dùng giá trị mặc định khi một biến không tồn tại:

~~~xml
<file>${LOG_DIR:-logs}/application.log</file>
~~~

Cú pháp **:-** mang ý nghĩa fallback property. Trong ứng dụng thật, cần kiểm tra rõ **phạm vi** và **thứ tự ưu tiên** của các nguồn property, cũng như việc quyền ghi và thư mục đích có tồn tại/hợp lệ hay không.

Đừng đưa mật khẩu, token, khóa bí mật vào property chỉ để chúng xuất hiện trong pattern log. **Mục đích của property logging là linh hoạt cấu hình**, không phải phương thức lưu bí mật.

## 9. PatternLayout: hiểu những conversion word phổ biến

Trong Logback Classic, pattern thường là phần quan trọng nhất của encoder. Một mẫu production dễ đọc:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} trace=%X{traceId} - %msg%n%ex</pattern>
~~~

Ý nghĩa:

| Conversion word | Nội dung |
| --- | --- |
| **%d{...}** | Thời gian của sự kiện theo định dạng đã cho |
| **%thread** | Tên thread |
| **%level** hoặc **%p** | Log level |
| **%-5level** | Level căn trái trong độ rộng tối thiểu 5 ký tự |
| **%logger{36}** | Tên logger với quy tắc rút gọn để hạn chế độ rộng |
| **%logger{0}** | Phần tên cuối cùng, thường là tên class |
| **%msg** hoặc **%message** | Thông điệp đã được định dạng |
| **%n** | Ký tự xuống dòng phù hợp nền tảng |
| **%X{traceId}** | Giá trị trong **MDC** của khóa traceId nếu có |
| **%ex** | Thông tin exception nếu sự kiện giữ Throwable |

Nếu muốn thống nhất thời gian UTC, có thể chỉ rõ timezone trong mẫu ngày của Logback:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger - %msg%n</pattern>
~~~

Lưu ý **%msg** không tự đảm bảo message an toàn. Nếu chương trình đã nối token hoặc dữ liệu cá nhân vào message, pattern cũng sẽ in chúng. Việc xử lý dữ liệu nhạy cảm phải bắt đầu ngay tại điểm phát log hoặc trong pipeline redaction đã được thiết kế.

### MDC cho request/trace ID

MDC giúp gắn bối cảnh vào log mà không cần nhắc lại từng giá trị trong mọi câu message. Ví dụ SLF4J:

~~~java
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    MDC.remove("requestId");
}
~~~

Đây là đoạn minh họa đặt trong phương thức có **requestId** và **processRequest()**. Trong pattern Logback dùng **%X{requestId}** để hiển thị giá trị.

**MDC cần được quản lý theo vòng đời ngữ cảnh thực thi.** Thread pool có thể tái sử dụng thread; nếu không dọn MDC trong finally, request tiếp theo có thể mang ID của request trước. Trong các tác vụ bất đồng bộ, không mặc định context truyền giữa các thread; phải sử dụng cơ chế propagation được framework hỗ trợ. Không đưa bí mật hoặc payload nhạy cảm vào MDC.

## 10. Stack trace và exception trong logback.xml

Khi gọi SLF4J, ứng dụng nên truyền **Throwable**:

~~~java
try {
    saveOrder(orderId);
} catch (IOException e) {
    log.error("SAVE_FAILED orderId={}", orderId, e);
    throw e;
}
~~~

Đây là đoạn minh họa trong phương thức đã có biến, logger và hàm liên quan; không phải ví dụ độc lập. Tham số cuối **e** là Throwable và được SLF4J nhận diện theo overload phù hợp. Logback có thể dùng nó để ghi stack trace và cause chain.

Nếu chỉ viết:

~~~java
log.error("SAVE_FAILED: {}", e.getMessage());
~~~

Logger nhận một chuỗi thay cho Throwable; stack trace và các nguyên nhân lồng nhau không tự được đưa vào sự kiện log. Một số định dạng Logback tự bổ sung thông tin throwable khi pattern chưa chứa conversion word exception; có thể dùng **%ex** hoặc cấu hình tương đương để xác định rõ hơn.

**Không log cùng một exception ở nhiều tầng rồi ném tiếp ở mọi nơi**. Nếu Repository, Service, Controller đều ghi ERROR với cùng một stack trace, số dòng log tăng nhưng không có thêm nhiều bằng chứng. Hãy chọn nơi xử lý kết quả cuối hoặc nơi có ngữ cảnh độc đáo thực sự cần ghi. Nếu cần bổ sung cause khi chuyển exception, dùng constructor giữ nguyên nhân gốc.

## 11. AsyncAppender và chi phí của logging

Trong một số hệ thống, ghi log đồng bộ có thể làm request chờ I/O. **AsyncAppender** giúp tách phần ghi ra một thread xử lý hàng đợi.

Ví dụ appender bất đồng bộ bọc một FILE appender đã được định nghĩa:

~~~xml
<appender name="ASYNC_FILE"
          class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
~~~

Sau đó root có thể tham chiếu **ASYNC_FILE** thay vì tham chiếu FILE trực tiếp. Ví dụ này **không độc lập**: FILE phải là appender hợp lệ đã được khai báo trong cùng cấu hình.

Ý nghĩa các lựa chọn:
- **queueSize:** Dung lượng hàng đợi nội bộ.
- **discardingThreshold:** Ngưỡng liên quan đến chính sách loại bỏ sự kiện ít quan trọng khi hàng đợi thiếu chỗ; giá trị 0 làm mất cơ chế loại bỏ theo ngưỡng đó.
- **neverBlock=false:** Khi hàng đợi đầy, nhà sản xuất log có thể phải chờ thay vì luôn bỏ sự kiện.
- **appender-ref:** Appender thực sự thực hiện I/O cho các sự kiện đã lấy từ hàng đợi.

**Bất đồng bộ không có nghĩa log chắc chắn không bị mất.** Tiến trình có thể bị kill trước khi queue được drain, đích ghi có thể gặp lỗi hoặc hệ thống có thể bị quá tải. Khi queue đầy, cách chọn giữa block và drop ảnh hưởng trực tiếp đến latency và độ tin cậy. Với audit hoặc thông tin cực kỳ quan trọng, phải thiết kế riêng đường ghi có bảo đảm phù hợp; không coi AsyncAppender mặc định như hàng đợi giao dịch bền vững.

Một chi phí khác thường bị bỏ qua: biểu thức được truyền vào Java vẫn phải đánh giá trước lời gọi logger. Ví dụ:

~~~java
log.debug("Diagnostics={}", buildLargeDiagnostics());
~~~

Hàm **buildLargeDiagnostics()** vẫn có thể chạy dù DEBUG đang tắt. Khi chi phí cao, cân nhắc:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Diagnostics={}", buildLargeDiagnostics());
}
~~~

Đây là các đoạn minh họa, yêu cầu logger và method đã tồn tại. Dùng placeholder **{}** là tốt cho việc trì hoãn format message, nhưng không tự trì hoãn mọi phép tính tạo đối số.

## 12. logback.xml và logback-spring.xml trong Spring Boot

Spring Boot thường tích hợp logging và hỗ trợ cấu hình mức bằng **application.properties** hoặc **application.yml**. Với Logback, một dự án Boot có thể dùng:

- **logback.xml:** Cú pháp Logback thông thường; Logback có thể nạp sớm theo cơ chế tự cấu hình.
- **logback-spring.xml:** Tên được Spring Boot nhận diện để hỗ trợ các phần mở rộng do Boot cung cấp, chẳng hạn **springProfile** và **springProperty** trong những điều kiện tương thích.

Ví dụ cấu hình chỉ phù hợp với **logback-spring.xml** khi được Spring Boot quản lý:

~~~xml
<configuration>
    <springProfile name="dev">
        <root level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <root level="INFO"/>
    </springProfile>
</configuration>
~~~

**Đây là đoạn minh họa về các phần tử Spring**, không phải file cấu hình hoàn chỉnh để dùng ngay: một ứng dụng cần khai báo appender theo nhu cầu và đảm bảo có nơi xuất log. **springProfile không phải thẻ chuẩn của Logback thuần**, vì thế không đưa nó vào **logback.xml** thông thường rồi kỳ vọng Logback tự hiểu.

Tương tự, Spring Boot có thể dùng:

~~~properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
~~~

Cấu hình nào thực sự có hiệu lực phụ thuộc cách dự án khởi động, version Spring Boot, các file logging và điểm áp dụng override. Không nên tùy tiện kết hợp nhiều cơ chế level ở các nơi khác nhau mà không biết thứ tự ưu tiên. Đặc biệt, tính năng scan/reload riêng của Logback có thể không hoạt động như kỳ vọng với những phần mở rộng Spring do Spring Boot diễn giải.

Trong ứng dụng Spring Boot sử dụng starter logging, backend Logback thường đã được đưa vào bởi dependency quản lý của framework. Kiểm tra cây dependency trước khi thêm một provider khác để tránh có nhiều provider SLF4J cùng tồn tại.

## 13. Nạp lại cấu hình khi đang chạy

Logback có khả năng theo dõi thay đổi tệp trong những cấu hình thích hợp. Ví dụ:

~~~xml
<configuration scan="true" scanPeriod="30 seconds">
    <!-- Cac appender, logger va root se duoc khai bao tai day. -->
</configuration>
~~~

Đây là **mẫu minh họa thuộc tính scan**, không phải file cấu hình production hoàn chỉnh. Khi file thực sự được hỗ trợ theo dõi và điều kiện reload đáp ứng, Logback có thể kiểm tra thay đổi định kỳ. Tuy nhiên, không mặc định việc sửa file nguồn trong repository sẽ khiến một JAR hoặc container đang chạy thay đổi cấu hình. Bản sao đã đóng gói, file mount, quyền ghi và cách khởi tạo backend đều ảnh hưởng.

Một thay đổi level trong production nên có:
1. Logger/package chính xác và mục đích điều tra rõ ràng.
2. Phạm vi instance/container cần áp dụng.
3. Thời hạn bật DEBUG/TRACE.
4. Kiểm tra volume, CPU, I/O và khả năng lộ dữ liệu.
5. Cách khôi phục baseline, kể cả sau restart/rollout.
6. Theo dõi dashboard và rule cảnh báo phụ thuộc mức log.

## 14. Những lỗi XML và cấu hình thường gặp

### 14.1. File không nằm trên runtime classpath

Đặt **logback.xml** trong thư mục bất kỳ mà không đưa vào resources sẽ khiến Logback không tìm thấy file như dự định. Kiểm tra artifact đã đóng gói và runtime classpath. Khi có file cấu hình được chỉ định qua property, bảo đảm đường dẫn đúng môi trường chạy.

### 14.2. Nhầm provider hoặc phiên bản

**logback.xml** có tác dụng khi provider Logback thực sự được dùng. Nếu classpath có nhiều provider SLF4J không tương thích, có thể phát cảnh báo và việc chọn backend không như mong muốn. Hãy chỉ giữ một provider phù hợp trong ứng dụng.

### 14.3. Appender được định nghĩa nhưng không được tham chiếu

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%msg%n</pattern>
    </encoder>
</appender>
~~~

Đây mới chỉ là **định nghĩa appender**. Nếu không có root hoặc logger gắn **appender-ref ref="CONSOLE"**, các sự kiện sẽ không tự động được gửi đến appender này vì nó tồn tại trong XML.

### 14.4. Sai tên appender-ref

~~~xml
<root level="INFO">
    <appender-ref ref="CONSOL"/>
</root>
~~~

Nếu appender thật có tên **CONSOLE**, tham chiếu **CONSOL** là sai. Logback có thể báo trạng thái cấu hình và không xuất log vào đích mong muốn.

### 14.5. Ghi trùng do additivity

Khi appender gắn cả logger con lẫn root và logger con vẫn additivity=true, một sự kiện có thể bị ghi hai lần. Chỉ giữ appender chung ở root hoặc cấu hình tuyến riêng với additivity=false và appender thích hợp.

### 14.6. Mức DEBUG không xuất hiện

Kiểm tra logger name có đúng class/package, có kế thừa từ root hay bị override, appender có ThresholdFilter không, cấu hình nào được nạp và liệu log có bị thu thập vào một đích khác.

### 14.7. Pattern sai hoặc không xử lý XML escaping

XML yêu cầu ký tự đặc biệt được escape đúng cách. Chẳng hạn **&** trong văn bản thuộc tính hoặc nội dung XML phù hợp phải được biểu diễn bằng **&amp;**; ký tự **<** trong text XML thường phải là **&lt;**. Nếu cú pháp XML sai, appender hoặc toàn bộ cấu hình có thể không khởi tạo như mong đợi.

### 14.8. Không có quyền ghi file hoặc volume đầy

RollingFileAppender không thể bù cho việc process không có quyền ghi, disk hết dung lượng hoặc nhiều instance tranh chấp cùng một file. Kiểm tra thông báo trạng thái và chỉ số hệ thống file.

### 14.9. Ghi stack trace, secret và payload quá mức

Ghi DEBUG hoặc TRACE toàn bộ production trong thời gian dài gây tốn tài nguyên và có thể lộ dữ liệu. Mức log thấp hơn không làm payload nhạy cảm trở nên an toàn. Bảo vệ dữ liệu tại điểm ghi log và ở pipeline lưu trữ.

## 15. Chẩn đoán khi không thấy log

Trình tự kiểm tra hợp lý:

1. **Logger có phát sự kiện không?** Kiểm tra đường chạy, nhánh code và mức gọi trong Java.
2. **Ứng dụng thật sự dùng Logback không?** Kiểm tra dependency/provider.
3. **Đúng logback.xml được nạp chưa?** Kiểm tra runtime classpath, logback-test.xml, override bằng system property và cơ chế logging của framework.
4. **Logger hiệu lực ở mức gì?** Kiểm tra root, package, class và tên logger chính xác.
5. **Appender có được gắn không?** Kiểm tra appender-ref và additivity.
6. **Appender có filter hoặc lỗi ghi không?** Xem ThresholdFilter, quyền file, thư mục, dung lượng và collector.
7. **Đích log nằm ở đâu?** Phân biệt stdout, stderr, file, container logs và hệ thống tập trung.
8. **Có exception hoặc lỗi parse XML không?** Xem trạng thái nội bộ Logback khi khởi tạo.

Trong môi trường điều tra, có thể dùng:

~~~xml
<configuration debug="true">
    <!-- Them appender, logger va root tu cau hinh thuc te. -->
</configuration>
~~~

Thuộc tính **debug=true** hỗ trợ nhìn trạng thái cấu hình nội bộ Logback; đoạn này chỉ minh họa phần mở đầu, không phải file độc lập. Khi đã xác định nguyên nhân, nên tắt chế độ chẩn đoán không cần thiết để tránh tăng log nội bộ.

## 16. Khi nào chọn ConsoleAppender, FileAppender, RollingFileAppender?

| Nhu cầu | Lựa chọn thường phù hợp | Cân nhắc |
| --- | --- | --- |
| Chạy local để xem log trực tiếp | ConsoleAppender | Dễ đọc, đơn giản |
| Container hoặc Kubernetes có collector chuẩn | ConsoleAppender (stdout/stderr) | Thu thập tập trung và không phụ thuộc vòng đời file trong container |
| Ứng dụng chạy lâu trên máy chủ có chính sách file log | RollingFileAppender | Cần rotation, retention, quyền ghi, backup |
| Một tệp ngắn sống trong môi trường kiểm thử | FileAppender | Không phù hợp lưu vô hạn trên dịch vụ production |
| Cần giảm chờ I/O của luồng nghiệp vụ | AsyncAppender bọc appender thật | Có queue, backpressure, khả năng mất log khi crash |
| Có yêu cầu audit bền vững | Pipeline audit chuyên trách | Cần bảo đảm thu thập, bảo vệ và retention theo yêu cầu |

Đích nào tốt nhất phụ thuộc nền tảng triển khai. Trong container, ưu tiên một pipeline log thống nhất và gắn **service, environment, instance, traceId**, thay vì mỗi class tự tạo file riêng.

## 17. Checklist khi đưa logback.xml lên production

- **Classpath:** Có đúng một provider SLF4J tương thích và đúng file cấu hình được nạp.
- **Mức log:** Baseline phù hợp, thường INFO; DEBUG/TRACE chỉ mở theo nhu cầu điều tra.
- **Logger names:** Tên class/package đúng; các rule riêng không vô tình mất hiệu lực sau refactor.
- **Appender-ref:** Mọi appender cần dùng được gắn; không có log trùng do additivity.
- **Filter:** Ngưỡng logger và appender nhất quán với mục tiêu quan sát.
- **Pattern:** Có timestamp/múi giờ, level, logger, message, exception và correlation khi cần.
- **Bảo mật:** Không ghi password/token/private key/payload nhạy cảm; có redaction và quyền truy cập.
- **Chi phí:** Xem log volume, latency, CPU, storage, queue và giới hạn retention.
- **File rotation:** Dùng chính sách đúng, thử rollover và kiểm tra archive, maxHistory, totalSizeCap nếu ghi file.
- **Triển khai:** Có phương án reload/rollout, rollback cấu hình và kiểm tra log sau khi phát hành.
- **Quan sát sự cố:** Dùng metrics/trace kết hợp log; không coi mức ERROR là quy tắc paging duy nhất.

## 18. Câu hỏi tự kiểm tra

**1. logback.xml thuộc API SLF4J hay backend Logback?**  
Đó là file cấu hình của **backend Logback**; mã Java thường phát log qua SLF4J.

**2. Vì sao root INFO nhưng logger demo.PaymentService DEBUG vẫn ghi được DEBUG qua appender ở root?**  
Vì ngưỡng được kiểm tra tại logger phát sự kiện; sự kiện được chấp nhận chuyển đến appender của cha theo additivity. Appender có thể tiếp tục lọc riêng.

**3. Khi nào xuất hiện log trùng?**  
Khi cùng một appender được gắn ở logger con và tổ tiên, nhưng additivity vẫn cho truyền bản ghi lên trên; hoặc hệ thống có nhiều pipeline xuất cùng sự kiện.

**4. additivity=false có tự tạo appender riêng không?**  
Không. Nó ngăn chuyển lên appender của tổ tiên. Nếu logger không có appender thích hợp, log có thể mất khỏi đích mong muốn.

**5. Vì sao rolling file theo ngày và kích thước cần cả %d và %i?**  
Vì **SizeAndTimeBasedRollingPolicy** cần xác định kỳ thời gian và từng phần file trong kỳ khi vượt giới hạn kích thước.

**6. Cú pháp springProfile có chạy nguyên trạng trong logback.xml thuần không?**  
Không. Đó là mở rộng do Spring Boot xử lý, thường dùng trong **logback-spring.xml** khi ứng dụng Boot quản lý cấu hình.

**7. Muốn thấy stack trace phải làm gì?**  
Truyền Throwable vào API log, cấu hình encoder/layout để hiển thị thông tin exception phù hợp, đồng thời tránh ghi lặp nhiều tầng.

**8. Chỉ đặt logger DEBUG đã chắc log DEBUG hiển thị chưa?**  
Chưa. Cần kiểm tra appender, filter, additivity, provider, nơi nhận log và file cấu hình thực sự được nạp.

**9. logback.xml có tự bảo vệ secret trong message không?**  
Không. Phải loại bỏ hoặc che dữ liệu nhạy cảm ở code/pipeline và kiểm soát quyền truy cập.

**Ghi nhớ:** **logback.xml** là nơi tập trung cấu hình của Logback: root/named logger quyết định mức log, appender quyết định đích ghi, encoder quyết định định dạng, filter và additivity quyết định đường đi của sự kiện. Hiểu đúng các cơ chế này giúp ứng dụng Java ghi log đủ để điều tra, rõ nguồn phát và tránh log trùng hoặc tăng chi phí không kiểm soát.
