# Console appender — Ghi log ra console với Logback trong Java

## 1. Console appender là gì?

**Console appender** là thành phần của hệ thống logging có nhiệm vụ **ghi các sự kiện log ra luồng đầu ra của tiến trình**, thường là **stdout** hoặc **stderr**. Trong **Logback**, lớp dùng cho mục đích này là **ch.qos.logback.core.ConsoleAppender**.

Khi ứng dụng Java gọi **LOG.info(...)**, nó chưa trực tiếp in một dòng text. Sự kiện đi qua API logger, level, các bộ lọc và hệ thống appender; ConsoleAppender nhận sự kiện đủ điều kiện, dùng encoder để chuyển nó thành dữ liệu và ghi tới stream đã chọn.

Ví dụ thông điệp muốn nhìn thấy:

~~~text
INFO | event=service.started port=8080
WARN | event=dependency.slow durationMs=740
ERROR | event=payment.failed errorCode=TIMEOUT
~~~

Đây là **thông điệp minh họa**, không phải định dạng mặc định của Logback. Nội dung có được hiển thị và trông như thế nào phụ thuộc cấu hình.

Cần phân biệt:

- **Logger:** điểm phát log từ mã Java; ví dụ **org.slf4j.Logger**.
- **Appender:** nơi nhận event để xuất. ConsoleAppender là appender cho console; FileAppender là appender cho file.
- **Encoder/Layout:** định dạng event, chẳng hạn in level, tên logger, message, timestamp và stack trace.
- **Filter:** quy tắc chặn/cho phép một event được xuất.
- **Target:** stream mà ConsoleAppender ghi vào: **System.out** hoặc **System.err**.

**ConsoleAppender không phải System.out.println.** Println ghi trực tiếp ra stdout, không xét log level. LOG.debug(...) có thể bị logger loại khi level INFO, và còn có thể bị filter ở appender chặn.

## 2. Vị trí của ConsoleAppender trong pipeline Logback

~~~text
Mã ứng dụng: LOG.info("event=...")
                 |
                 v
           SLF4J Logger API
                 |
                 v
       Logback Logger / level
                 |
                 v
             Log event
                 |
         Cây logger và
           additivity
                 |
                 v
      ConsoleAppender + filter
                 |
                 v
       Encoder (pattern/charset)
                 |
           +-----+------+
           |            |
           v            v
       System.out    System.err
           |            |
           +-----+------+
                 |
                 v
    Terminal / container collector
~~~

Một Logger không nhất thiết có appender gắn trực tiếp. Nó có thể gửi sự kiện đến appender của logger cha hoặc **root logger** khi additivity cho phép.

| Thành phần | Câu hỏi cần kiểm tra |
| --- | --- |
| Logger/effective level | Lệnh gọi DEBUG, INFO, WARN, ERROR có được nhận hay không? |
| Additivity | Event có tới các appender gắn ở logger cha không? |
| Appender filter | Event đã qua logger có tiếp tục bị loại không? |
| Encoder | Dòng log dùng pattern, charset và cách biểu diễn exception nào? |
| Target | ConsoleAppender xuất stdout hay stderr? |
| Collector | Hạ tầng có thu thập, parse và giữ dòng log hay không? |

Sự kiện có thể bị chặn ở bất kỳ bước thích hợp nào. **Gọi LOG.error(...) không đảm bảo bản ghi đã tồn tại bền vững ở hệ thống thu thập từ xa.**

## 3. stdout và stderr khác nhau

Hai stream chuẩn của một tiến trình:

- **stdout:** thường chứa kết quả chính và các thông điệp thông thường.
- **stderr:** thường dành cho thông tin chẩn đoán và lỗi, tách biệt với kết quả chính.

**Logback ConsoleAppender** mặc định thường chọn **System.out** và cho phép đặt lại bằng thuộc tính target:

~~~xml
<target>System.out</target>
~~~

hoặc:

~~~xml
<target>System.err</target>
~~~

Hai đoạn trên chỉ là **mảnh XML bên trong appender**, chưa phải file logback.xml hoàn chỉnh.

Một CLI in JSON cho chương trình khác thường nên tránh trộn log vào stdout, vì có thể làm JSON output không hợp lệ. Nếu cần giữ stdout cho dữ liệu, có thể chọn stderr cho log chẩn đoán. Ngược lại, dịch vụ trong container thường cho hạ tầng thu cả stdout và stderr; lựa chọn cần theo chuẩn triển khai của hệ thống.

### ConsoleAppender và JUL ConsoleHandler khác nhau

| Tiêu chí | Logback ConsoleAppender | JUL ConsoleHandler |
| --- | --- | --- |
| Lớp | ch.qos.logback.core.ConsoleAppender | java.util.logging.ConsoleHandler |
| Thuộc hệ thống | Logback, thường qua SLF4J | java.util.logging của JDK |
| Stream mặc định | **System.out** | **System.err** |
| Định dạng | Encoder/Layout | Formatter |
| Mức thường gặp | TRACE, DEBUG, INFO, WARN, ERROR | FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE |
| Cấu hình điển hình | logback.xml | logging.properties hoặc code Java |

Không viết cấu hình của Logback rồi mong JUL đọc được; hai hệ có API và cách cấu hình khác nhau.

### Chuyển hướng output trong shell

Với bash, **>** chuyển stdout còn **2>** chuyển stderr:

~~~bash
java -jar app.jar > stdout.log
java -jar app.jar 2> stderr.log
java -jar app.jar > combined.log 2>&1
~~~

Các lệnh chỉ minh họa shell redirection; cần có file JAR thật. Chuyển hướng stream ra file **không phải FileAppender**: một bên do shell xử lý, bên còn lại do logging backend quản lý.

Nếu stdout và stderr cùng được thu rồi gộp lại, thứ tự quan sát giữa hai stream **không luôn phản ánh chính xác thứ tự phát event**. Khi cần điều tra, dùng timestamp có timezone và correlation ID.

## 4. File logback.xml cơ bản

Một cấu hình đầy đủ:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Cách đọc:

1. **name="CONSOLE"** đặt tên appender.
2. **class="...ConsoleAppender"** xác định loại appender.
3. **target=System.out** chọn stdout.
4. **encoder** chuyển log event thành nội dung ghi ra console.
5. **charset=UTF-8** hỗ trợ Unicode khi nơi nhận cũng dùng encoding tương thích.
6. **%level** là mức log, **%logger** là tên logger, **%msg** là message sau khi định dạng tham số, **%n** xuống dòng.
7. **root level=INFO** đặt mức mặc định của logger kế thừa.
8. **appender-ref** gắn CONSOLE vào root để các sự kiện được route tới appender.

Chỉ khai báo appender nhưng **không tham chiếu từ logger/root** sẽ không đảm bảo có output. **Tên name và ref phải khớp**. Trong ứng dụng thật, nên bổ sung timestamp, thread, request/trace ID và chính sách xuất Throwable phù hợp.

## 5. Dự án chạy được: Java 17 + Maven + Logback

Ví dụ này tạo một chương trình Java đơn giản phát bốn log event; chỉ ba event được in khi root ở INFO. Chương trình gọi **SLF4J API**, còn **ConsoleAppender** được chọn trong logback.xml. Không cần tự viết lớp appender.

### 5.1. Cấu trúc dự án

~~~text
console-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ConsoleAppenderDemo.java
        └── resources/
            └── logback.xml
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>console-appender-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                <configuration>
                    <mainClass>demo.ConsoleAppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các version ở đây là **phiên bản minh họa**, không phải khẳng định mới nhất. Maven giải quyết các dependency transitive của logback-classic như logback-core và SLF4J API. Dự án thật cần kiểm soát version và các bản vá bảo mật; tránh đưa nhiều SLF4J provider khác nhau vào cùng classpath.

### 5.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Với Maven, file dưới src/main/resources được đưa lên classpath khi chạy; Logback có thể nạp nó theo cơ chế cấu hình mặc định nếu không có framework/cấu hình khác ghi đè.

### 5.4. src/main/java/demo/ConsoleAppenderDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ConsoleAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ConsoleAppenderDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=cache.lookup result=miss");

        LOG.info("event=service.started port={}", 8080);

        LOG.warn("event=dependency.slow durationMs={}", 740);

        LOG.error("event=payment.failed errorCode={}", "TIMEOUT");
    }
}
~~~

Đây là **chương trình độc lập trong dự án Maven đã nêu**, không phải snippet thiếu class. Class được import là **org.slf4j.Logger** để mã không phụ thuộc API riêng của ConsoleAppender.

### 5.5. Biên dịch và chạy

Cần **JDK 17+**, Maven đã cài và dependency tải được hoặc có trong cache. Tại thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

**Stdout chính xác do chương trình Java phát ra** với cấu hình logback.xml ở trên (không tính log riêng của Maven/môi trường):

~~~text
INFO | demo.ConsoleAppenderDemo | event=service.started port=8080
WARN | demo.ConsoleAppenderDemo | event=dependency.slow durationMs=740
ERROR | demo.ConsoleAppenderDemo | event=payment.failed errorCode=TIMEOUT
~~~

**Không có dòng DEBUG** vì effective level là INFO từ root. Các dòng kết thúc bằng newline; không có timestamp để kết quả không phụ thuộc đồng hồ.

### 5.6. Vì sao đúng ba dòng?

1. LoggerFactory lấy logger có tên **demo.ConsoleAppenderDemo**.
2. Logger không có level riêng, nên kế thừa ngưỡng **INFO**.
3. Sự kiện DEBUG thấp hơn INFO và bị loại.
4. INFO, WARN, ERROR đủ ngưỡng.
5. Logger chuyển event tới appender CONSOLE của root theo additivity thông thường.
6. Pattern xuất **%level | %logger | %msg%n**.
7. ConsoleAppender ghi **System.out**, vì vậy ba dòng thuộc stdout.
8. Các placeholder **{}** của SLF4J được thay bằng 8080, 740 và TIMEOUT tương ứng.

### 5.7. Bật DEBUG không cần sửa mã nguồn

Đổi cấu hình root:

~~~xml
<root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Chạy lại, **stdout của chương trình** có thêm dòng đầu:

~~~text
DEBUG | demo.ConsoleAppenderDemo | event=cache.lookup result=miss
INFO | demo.ConsoleAppenderDemo | event=service.started port=8080
WARN | demo.ConsoleAppenderDemo | event=dependency.slow durationMs=740
ERROR | demo.ConsoleAppenderDemo | event=payment.failed errorCode=TIMEOUT
~~~

Điều này cho thấy backend quyết định mức quan sát. Không nên sửa lời gọi LOG.debug thành LOG.info chỉ để buộc một dòng debug xuất ở production.

### 5.8. Chuyển target sang System.err

Thay target trong file XML:

~~~xml
<target>System.err</target>
~~~

Sau khi chạy lại với cấu hình khác giữ nguyên, nội dung ba dòng log vẫn như mục 5.5 nhưng được ghi vào **stderr**; **stdout của chương trình không có các dòng đó**. Nếu cần xác nhận, trong bash có thể chuyển hướng:

~~~bash
mvn -q compile exec:java > stdout.log 2> stderr.log
~~~

Các dòng log ứng dụng sẽ ở stderr.log. Nội dung riêng của Maven hoặc chẩn đoán runtime nếu có không thuộc output dự kiến của ví dụ.

## 6. Formatter/encoder: quyết định cách đọc log console

Với Logback, **PatternLayoutEncoder** thường được dùng để tạo dòng văn bản. Một số conversion word thông dụng:

| Ký hiệu | Kết quả |
| --- | --- |
| **%level** hoặc **%p** | INFO, WARN, ERROR, DEBUG... |
| **%logger** hoặc **%c** | Tên logger |
| **%logger{36}** | Tên logger dạng rút gọn |
| **%thread** hoặc **%t** | Tên thread |
| **%msg** / **%message** | Message sau khi gắn argument |
| **%n** | Xuống dòng |
| **%d{...}** | Thời gian với pattern cụ thể |
| **%X{requestId}** | Giá trị MDC requestId nếu có |
| **%ex** / **%throwable** | Thông tin ngoại lệ/stack trace theo converter |

Pattern phục vụ chẩn đoán có thể là:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n</pattern>
~~~

Đoạn trên chỉ là **phần tử pattern trong encoder**, không phải file XML độc lập. Timestamp phụ thuộc timezone/cấu hình thực tế: pattern dạng này **không tự bảo đảm UTC**.

Một hệ thống cần truy vấn trường như event, errorCode và durationMs có thể dùng **structured JSON encoder** tương ứng. Tự ghép JSON bằng String mà không escape dấu nháy/newline sẽ dễ tạo dữ liệu không hợp lệ. Chỉ có text key=value trong %msg cũng không tự biến mọi field thành trường được backend thu thập lập chỉ mục.

### Unicode và charset

Nếu message có tiếng Việt, nên đặt **UTF-8** trong encoder và kiểm tra charset tại nơi đọc/thu thập. Ví dụ:

~~~xml
<encoder>
    <charset>UTF-8</charset>
    <pattern>%level | %msg%n</pattern>
</encoder>
~~~

Không thể bảo đảm hiển thị đúng chỉ bằng phía appender khi terminal hoặc collector giải mã bằng bảng mã khác.

## 7. Appender filter: vì sao DEBUG/INFO không xuất?

Appender có thể thêm **ThresholdFilter** để chỉ nhận những event từ một mức trở lên.

Ví dụ ConsoleAppender chỉ nhận **WARN/ERROR**:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>
    <encoder>
        <pattern>%level | %msg%n</pattern>
    </encoder>
</appender>
~~~

Đây là mảnh appender để minh họa. Nếu logger đang DEBUG nhưng appender có ThresholdFilter WARN, các sự kiện DEBUG và INFO **vẫn không xuất**, vì đã bị appender chặn. Ngược lại, nâng độ chi tiết filter không khôi phục được event bị Logger loại từ trước.

| Logger effective level | Threshold của appender | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| INFO | Không có filter | Không | Có thể xuất | Có thể xuất | Có thể xuất |
| DEBUG | Không có filter | Có thể xuất | Có thể xuất | Có thể xuất | Có thể xuất |
| DEBUG | WARN | Không | Không | Có thể xuất | Có thể xuất |
| INFO | WARN | Không | Không | Có thể xuất | Có thể xuất |
| ERROR | INFO | Không | Không | Không | Có thể xuất |

“Có thể xuất” nghĩa là appender đã được gắn và không có filter khác chặn.

### Root INFO không nhất thiết loại DEBUG của logger con

Xét mảnh cấu hình:

~~~xml
<logger name="demo.order" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Nếu logger con demo.order.OrderService có effective level DEBUG và additivity=true, DEBUG của nó có thể tới appender ở root. **Root INFO không lọc lại event DEBUG đã được logger con chấp nhận**. Nếu muốn toàn bộ console chỉ có INFO trở lên, cần xem filter trên appender, không chỉ nhìn level root.

## 8. Additivity và bản ghi trùng

Khi **additivity=true** (hành vi mặc định thường gặp), event của logger con có thể được chuyển lên các ancestor để dùng appender của chúng.

Cấu hình dễ tạo log trùng:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%level | %msg%n</pattern>
    </encoder>
</appender>

<logger name="demo.order" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Vì CONSOLE được gắn ở cả demo.order và root, cùng một event có thể khiến appender được gọi hai lần. Điều này **không đủ để kết luận thao tác nghiệp vụ chạy hai lần**.

Cách sửa phổ biến là **chỉ gắn CONSOLE ở root**, còn logger con chỉ đặt level. Nếu thật sự cần một console riêng cho nhánh con, có thể cấu hình:

~~~xml
<logger name="demo.order"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="ORDER_CONSOLE"/>
</logger>
~~~

Ở đây **ORDER_CONSOLE phải được khai báo trước**. Khi additivity=false, event từ nhánh con không chuyển tiếp lên appender của ancestor theo tuyến đó. Nếu tắt additivity mà không có appender nào ở nhánh riêng, log có thể biến mất.

**Additivity khác với kế thừa level**: một logger có thể kế thừa INFO từ root nhưng vẫn ngắt tuyến appender; hoặc có level DEBUG riêng nhưng dùng appender ở root.

## 9. Chia INFO/WARN ra stdout, ERROR ra stderr

Một ConsoleAppender chỉ có **một target**. Nếu muốn phân luồng theo level, có thể tạo hai appender với filter không chồng lặp:

~~~xml
<configuration>
    <appender name="OUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="OUT"/>
        <appender-ref ref="ERR"/>
    </root>
</configuration>
~~~

Cơ chế:

- **OUT** loại đúng ERROR nhờ LevelFilter, các sự kiện INFO/WARN có thể được xuất qua stdout.
- **ERR** dùng ThresholdFilter ERROR nên không nhận INFO/WARN; ERROR được xuất qua stderr.
- **Root INFO** loại DEBUG từ các logger kế thừa INFO, trước khi event đi tới appender.
- Hai appender cùng tồn tại nhưng không cố ý nhân đôi ERROR.

Nếu **OUT không có LevelFilter**, một sự kiện ERROR có thể xuất cả stdout lẫn stderr. Cần kiểm chứng đường đi thực tế bằng cách chuyển hướng hai stream.

Khi hai stream bị gộp bởi shell/container, **thứ tự dòng từ hai stream không được bảo đảm tuyệt đối**. Cân nhắc giữ toàn bộ log trong một stream theo chuẩn tổ chức nếu tính thứ tự và cách thu thập đòi hỏi như vậy.

## 10. ConsoleAppender, FileAppender và môi trường container

**ConsoleAppender** đẩy event vào stdout/stderr, còn **FileAppender/RollingFileAppender** do backend trực tiếp quản lý file. Chọn đích theo môi trường:

| Tiêu chí | ConsoleAppender | FileAppender / RollingFileAppender |
| --- | --- | --- |
| Nơi ghi | Stream của tiến trình | File được backend mở |
| Sử dụng thường gặp | CLI, service container hóa | Máy chủ cần file cục bộ |
| Rotation | Do shell/runtime/collector xử lý nếu có | Có thể cấu hình rotation ở RollingFileAppender |
| Retention | Hệ thống thu thập hoặc hạ tầng | Chính sách file và hạ tầng |
| Điểm cần chú ý | stdout bị nghẽn, collector chậm, stream trộn | Dung lượng ổ đĩa, quyền, file lock, rotation |
| Khả năng mất log | Có thể mất khi I/O hoặc collector lỗi | Có thể mất khi buffer/đĩa/tiến trình gặp lỗi |

**Ghi vào console không có nghĩa log sẽ được lưu trong một file**. Docker/Kubernetes hoặc cloud runtime có thể thu thập stdout/stderr, nhưng cần cấu hình collector, quyền truy cập, thời gian lưu và quota.

Một CLI muốn xuất dữ liệu máy đọc bằng stdout có thể chọn stderr cho log. Một server container có thể chọn stdout cho mọi level rồi dựa vào trường level trong log để phân loại. Không có một quy tắc phù hợp tuyệt đối cho mọi ứng dụng.

## 11. Hiệu năng, buffering và AsyncAppender

Console logging có chi phí: tạo message, định dạng, encoding, ghi stream và có thể đợi consumer của pipe hoặc collector. Việc ghi log quá nhiều trong vòng lặp hoặc ghi stack trace dài ở tần suất cao có thể làm tăng độ trễ.

Các yếu tố cần đo:

1. **Lưu lượng:** số event mỗi giây và kích thước trung bình.
2. **Level:** DEBUG/TRACE có thể làm lượng event tăng mạnh.
3. **Encoder:** pattern và JSON encoder có chi phí khác nhau.
4. **Đích:** terminal, file redirect hoặc container runtime có tốc độ ghi khác nhau.
5. **Buffer/flush:** flush thường xuyên có thể tốn I/O; giữ buffer lâu có rủi ro mất log khi process dừng bất ngờ.
6. **Thread:** nhiều luồng gửi event có thể tạo áp lực lên điểm xuất chung.

**Không thể khẳng định ConsoleAppender luôn chậm hơn FileAppender theo một tỷ lệ cố định.** Cần benchmark dưới tải và hạ tầng thực tế.

**AsyncAppender** có thể đưa event vào hàng đợi rồi để worker riêng ghi sang ConsoleAppender:

~~~text
Logger -> AsyncAppender -> Queue -> ConsoleAppender -> stdout
~~~

Nó có thể giảm thời gian chờ của thread nghiệp vụ trong một số trường hợp. Tuy nhiên, lúc hàng đợi đầy hoặc shutdown đột ngột, event có thể bị chặn, bỏ qua hoặc chưa flush xong theo cấu hình. Cần hiểu queue size, chính sách discard, timeout và shutdown; **async không bảo đảm log không mất**.

### Chú ý tính chi phí của đối số

Mảnh mã dùng SLF4J:

~~~java
LOG.debug("payload={}", expensiveSerialize(payload));
~~~

Dù DEBUG bị tắt, Java vẫn **đánh giá expensiveSerialize(payload)** trước lời gọi debug(...). Nếu việc tạo mô tả thực sự tốn kém:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

Các đoạn mã này **cần định nghĩa LOG, payload và phương thức** trong lớp thực; chúng không độc lập. Parameterized logging bằng **{}** giúp tránh một phần chi phí dựng chuỗi nhưng không trì hoãn mọi biểu thức đối số. Đừng đưa logic nghiệp vụ bắt buộc vào code chỉ chạy khi DEBUG được bật.

## 12. Exception, stack trace và MDC

Khi cần điều tra lỗi, nên truyền đối tượng Throwable:

~~~java
try {
    callPaymentService();
} catch (java.io.IOException ex) {
    LOG.error("event=payment.failed requestId={}", requestId, ex);
}
~~~

Đây là **mảnh minh họa**, cần LOG, requestId và method callPaymentService trong ngữ cảnh thật. Logback có thể nhận throwable để encoder/layout thể hiện stack trace và cause. Nhưng **không mặc định mọi pattern đều giữ toàn bộ Throwable**; phải kiểm tra converter/encoder và output thực tế.

Đừng chỉ log ex.getMessage() rồi bỏ mất nguyên nhân hoặc ghi cùng một exception ở mọi tầng. Nên xác định ranh giới chịu trách nhiệm log sau khi biết tác vụ đã thất bại.

### Request ID qua MDC

Với SLF4J MDC:

~~~java
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

Mảnh mã trên **không phải chương trình độc lập**; cần LOG đã có trong lớp. Trong encoder Logback có thể thêm:

~~~xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
~~~

Một dòng minh họa có thể là:

~~~text
INFO requestId=req-42 demo.OrderService - event=order.created outcome=success
~~~

Đây không phải output của chương trình ở mục 5. **MDC không tự động truyền qua mọi thread pool, CompletableFuture và async framework**. Cần propagate và dọn context đúng scope để không lẫn request ID giữa các công việc.

## 13. ANSI/màu sắc trên terminal

Khi phát triển cục bộ, có thể dùng pattern tô màu level:

~~~xml
<pattern>%highlight(%-5level) %logger - %msg%n</pattern>
~~~

Đây chỉ là **mảnh pattern minh họa**. Việc xử lý ANSI và màu tùy terminal, phiên bản backend hoặc cấu hình hỗ trợ (trên một số môi trường Windows có thể cần Jansi). Khi gửi log tới collector hay file, ký tự điều khiển màu có thể làm dữ liệu khó đọc/parse.

Không mặc định bật màu production. Nếu cần phân loại cảnh báo, nên xuất trường level rõ ràng để hệ thống thu thập lọc, thay vì dựa vào màu terminal.

## 14. Bảo mật và khả năng quan sát

Log console trong container, CI hoặc cloud platform có thể được thu thập, sao lưu và truy cập bởi nhiều hệ thống. Vì vậy:

- **Không ghi password, API key, access token, refresh token, cookie phiên, private key hoặc dữ liệu thẻ.**
- Không mặc định log toàn bộ request/response body, Authorization header hoặc object.toString().
- Với dữ liệu không tin cậy, dùng encoder có escaping để tránh newline/điều khiển ký tự tạo các dòng log giả.
- Chọn mã sự kiện, errorCode và requestId an toàn thay cho dữ liệu nhạy cảm; cân nhắc phân quyền và retention.
- Đừng coi một lời gọi LOG.info là chứng cứ giao dịch được ghi bền vững; logging có thể thất bại hoặc bị thu thập trễ.
- Metrics phù hợp với tỷ lệ lỗi/latency theo thời gian, còn log giúp phân tích một event cụ thể; tracing giúp theo luồng nhiều dịch vụ.
- Không cho requestId duy nhất thành metric label không giới hạn; nó thường phù hợp với log/trace.

Một console appender đơn giản vẫn cần quy tắc logging và quy trình quan sát để phát hiện vấn đề khi collector không nhận dữ liệu.

## 15. Những lỗi thường gặp

| Lỗi | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Có appender nhưng thiếu appender-ref | Không thấy log | Gắn appender vào logger hoặc root |
| ref sai tên | Không nối đúng đích | Đối chiếu name/ref |
| Root INFO nhưng mong DEBUG xuất | DEBUG bị loại | Cấu hình level đúng logger |
| Logger DEBUG nhưng appender ThresholdFilter WARN | Không có dòng DEBUG | Kiểm tra cả filter |
| Gắn cùng CONSOLE ở con và root | Một event xuất hai lần | Kiểm tra additivity và appender-ref |
| additivity=false không có appender riêng | Log biến mất | Gắn appender hoặc mở lại chuyển tiếp |
| Nhầm stdout của Logback với stderr của JUL | Redirect sai stream | Xác định backend và target |
| Gắn hai ConsoleAppender khác stream mà không lọc | ERROR có thể xuất trùng | Thiết kế filter không chồng lặp |
| Có nhiều SLF4J provider | Backend được chọn không như mong muốn | Dùng dependency tree và một provider |
| Dùng logback.xml với JUL thuần | Cấu hình bị bỏ qua | Sử dụng file của backend đúng |
| Charset không thống nhất | Tiếng Việt lỗi ký tự | Cấu hình UTF-8 ở đầu gửi và nơi nhận |
| Log quá dày đặc | Console/collector quá tải | Chọn level, sampling/metrics hợp lý |
| Bật ANSI khi lưu text tập trung | Ký tự màu lẫn vào log | Tắt màu hoặc xử lý escape |
| Log raw user input hoặc token | Lộ dữ liệu, log injection | Giảm trường, mask và escape |
| Không dọn MDC | RequestId của tác vụ cũ bị giữ | Dọn theo scope và propagate đúng |

## 16. Checklist kiểm tra khi không thấy log console

1. **Backend:** ứng dụng có thật sự dùng Logback Classic không, hay JUL/Log4j 2?
2. **Provider:** SLF4J API có một provider tương thích không?
3. **Cấu hình:** logback.xml có trên classpath và được tải không?
4. **Logger name:** code dùng tên nào, effective level bao nhiêu?
5. **Appender:** được khai báo và tham chiếu đúng chưa?
6. **Additivity:** có bị tắt ở một cấp mà không có appender nhận không?
7. **Filter:** ThresholdFilter, LevelFilter hoặc TurboFilter chặn gì?
8. **Target:** System.out hay System.err? Terminal và redirect có đang xem đúng stream?
9. **Encoding:** charset ở encoder và ở terminal/collector có khớp không?
10. **Thu thập:** có buffer, drop, độ trễ hoặc retention khiến bản ghi không tìm thấy không?

Nếu log xuất trùng, kiểm tra **appender-ref và additivity** trước khi khẳng định nghiệp vụ chạy hai lần. Nếu lỗi không có stack trace, kiểm tra cách truyền Throwable và cấu hình encoder.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** ConsoleAppender của Logback mặc định hướng tới stdout hay stderr?

**Đáp án:** Thông thường **System.out**. Có thể đặt target System.err. JUL ConsoleHandler có mặc định khác là stderr.

**Câu 2.** Có ConsoleAppender trong logback.xml nhưng không có appender-ref. Có chắc log được in không?

**Đáp án:** Không. Phải có tuyến logger/root tham chiếu appender và event vượt qua level/filter.

**Câu 3.** Logger DEBUG và appender ThresholdFilter WARN có in DEBUG không?

**Đáp án:** Không. Appender loại các event thấp hơn WARN.

**Câu 4.** Root INFO và logger con DEBUG, appender ở root không có filter. DEBUG của con có thể được in không?

**Đáp án:** Có. Root không tự lọc lại event đã được logger con chấp nhận; additivity đưa event tới appender root.

**Câu 5.** Tại sao một event có thể in hai lần?

**Đáp án:** Cùng appender có thể được tham chiếu ở logger con và root khi additivity vẫn bật.

**Câu 6.** Muốn ERROR chỉ vào stderr, có đủ để tạo hai appender target khác nhau không?

**Đáp án:** Không. Phải thêm filter để tránh ERROR đi cả stdout và stderr.

**Câu 7.** ConsoleAppender có tự rotation file không?

**Đáp án:** Không. Nó ghi stream console; việc rotation do FileAppender/RollingFileAppender hoặc hạ tầng thu stream đảm nhiệm.

**Câu 8.** Tại sao LOG.debug("x={}", expensive(x)) vẫn có thể tốn CPU khi DEBUG tắt?

**Đáp án:** Java tính đối số expensive(x) trước lời gọi. Guard phép tính tốn kém nếu cần.

**Câu 9.** Có an toàn khi ghi token ở DEBUG vì production đang INFO?

**Đáp án:** Không. Level có thể thay đổi và log có thể được thu thập ở môi trường khác. Không ghi bí mật ở bất cứ level nào.

**Ghi nhớ:** **ConsoleAppender là đích xuất log ra stdout/stderr.** Để một event đến được console, cần nhìn toàn bộ đường đi: **Logger/effective level → additivity → appender/filter → encoder/charset → target → collector**. Cấu hình đơn giản, nhất quán và có kiểm chứng runtime thường tốt hơn một mạng lưới appender phức tạp không cần thiết.
