# Appender của Logback trong Java

## 1. Appender là gì?

Trong **Logback**, *appender* là thành phần **nhận log event rồi chuyển sự kiện tới một đích ghi hoặc một bước xử lý khác**. Đích có thể là console, file, một file có chính sách xoay vòng, kết nối mạng, hay một appender được bọc bởi cơ chế ghi bất đồng bộ. Nếu logger cho phép một sự kiện nhưng không có đường appender hoạt động phù hợp, người dùng vẫn có thể không thấy bản ghi ở nơi mong đợi.

Một cách hình dung:

~~~text
Mã Java dùng SLF4J Logger
       |
       v
Logger của Logback (mức log, TurboFilter, quan hệ cha-con)
       |
       v
Các appender gắn với logger / logger cha
       |
       +--> ConsoleAppender --> stdout / stderr
       |
       +--> FileAppender --> file log
       |
       +--> RollingFileAppender --> file đang ghi + archive
       |
       +--> AsyncAppender --> queue --> appender đích
~~~

Logback thường được dùng làm **backend cho SLF4J**. SLF4J cung cấp API `Logger.info(...)`, `Logger.warn(...)`, `Logger.error(...)`; Logback quyết định cách thực thi, format và chuyển các event sang appender.

**Phân biệt rõ ba vai trò:**

- **Logger:** nhận lời gọi, áp dụng mức log hiệu lực và một số quyết định lọc; logger có thể sở hữu danh sách appender và kế thừa đường phát sự kiện qua logger cha.
- **Appender:** quyết định **chuyển event đi đâu** và có thể áp dụng các bộ lọc riêng. Một logger có thể gắn nhiều appender; một appender có thể được nhiều logger tham chiếu.
- **Encoder/Layout:** xác định **event được biểu diễn thế nào** khi tới đích: dòng text, pattern với timestamp/thread/level hoặc dữ liệu được mã hóa theo định dạng khác. Appender quyết định đường ghi; encoder/layout quyết định nội dung xuất ở đường đó.

Ví dụ cùng một event `LOG.info("orderId={} status={}", id, status)` có thể được ghi ra console theo một pattern ngắn, đồng thời ghi vào file theo pattern chứa timestamp và tên thread. Đó là hai appender cùng nhận sự kiện, không phải hai lần mã nghiệp vụ gọi logger.

## 2. Appender ở đâu trong kiến trúc Logback?

### 2.1. Sự kiện đi từ logger tới appender

Với ứng dụng dùng SLF4J và backend Logback Classic:

1. Lệnh `LOG.info(...)` tạo yêu cầu ghi log qua SLF4J.
2. Logback xác định mức log có được bật tại logger tương ứng không. Một số bộ lọc tổng thể như `TurboFilter` có thể ảnh hưởng việc quyết định chấp nhận event.
3. Khi event được chấp nhận, Logback tạo/cung cấp `ILoggingEvent` chứa thông tin mức log, tên logger, message, arguments, dữ liệu thread, throwable và ngữ cảnh liên quan.
4. Event được chuyển tới các appender có hiệu lực của logger và, nếu cấu hình additivity cho phép, tới những appender gắn ở logger cha.
5. Mỗi appender có thể áp dụng filter rồi encode event và thực hiện thao tác ghi, hoặc chuyển tiếp sang worker/đích tiếp theo.

Đường đi chi tiết có thể thay đổi tùy phiên bản và loại appender. Không phải mọi appender đều format thành chuỗi text; appender bất đồng bộ có thể chỉ chuyển event qua hàng đợi tới appender khác.

### 2.2. Log level và appender filter là hai lớp khác nhau

Nếu root logger đặt `INFO`, các event DEBUG/TRACE từ logger kế thừa ngưỡng này thông thường bị loại ngay ở logger. Chúng không tới ConsoleAppender hay FileAppender để các appender xử lý tiếp.

Nếu logger đã chấp nhận event INFO nhưng một appender có `ThresholdFilter` chỉ cho phép WARN trở lên, **appender đó** không xuất INFO; một appender khác không có filter vẫn có thể xuất INFO. Điều này cho phép nhiều đích có chính sách khác nhau.

Ví dụ mục tiêu vận hành:

| Nguồn sự kiện | ConsoleAppender | FileAppender |
| --- | --- | --- |
| DEBUG (logger không cho phép) | Không tới appender | Không tới appender |
| INFO (logger cho phép) | Ghi | Không ghi nếu filter ở file yêu cầu WARN+ |
| WARN (logger cho phép) | Ghi | Ghi |
| ERROR (logger cho phép) | Ghi | Ghi |

Đây là **mô hình cấu hình minh họa**, không phải chính sách mặc định bắt buộc của Logback.

### 2.3. Additivity quyết định có đi lên logger cha không

Một logger thường theo tên package/class, ví dụ `example.checkout.Service`. Theo mặc định, Logback có **additivity=true**: event đã được logger con chấp nhận có thể được gửi tới appender của logger đó **và** appender của logger cha, tới tận root.

Ví dụ:

~~~xml
<logger name="example.checkout" level="DEBUG">
    <appender-ref ref="FILE"/>
</logger>

<root level="INFO">
    <appender-ref ref="FILE"/>
</root>
~~~

Nếu cùng một `FILE` được tham chiếu ở logger con và root, một event từ `example.checkout.Service` có thể được appender đó nhận **hai lần**. Không nên coi đây là hai exception riêng; đó có thể là **log trùng do cấu hình**.

Một cách sửa nếu chỉ muốn log package này đi tới FILE và **không** tới các appender cha:

~~~xml
<logger name="example.checkout" level="DEBUG" additivity="false">
    <appender-ref ref="FILE"/>
</logger>
~~~

Đặt `additivity="false"` cắt đường chuyển event lên logger cha. Chỉ dùng khi đã gắn **đủ appender cần thiết** tại logger con; nếu đặt false nhưng quên appender thì có thể không còn đích ghi. Ngoài ra, ngưỡng root `INFO` **không tự lọc lại** một event DEBUG đã được logger con chấp nhận chỉ vì event đi qua appender gắn ở root; bộ lọc của từng appender vẫn có thể tác động.

## 3. Những appender thường gặp

| Appender | Chức năng chính | Khi nào hữu ích | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `ConsoleAppender` | Ghi ra `System.out` hoặc `System.err` | Ứng dụng CLI, container, development, hệ thống thu log stdout | Console/log driver vẫn có I/O và có thể nghẽn |
| `FileAppender` | Ghi nối tiếp vào một file | Ứng dụng cần file log cố định trên máy/volume | Cần quản lý kích thước, quyền truy cập, dung lượng đĩa |
| `RollingFileAppender` | Ghi file đang hoạt động và **rollover/archive** theo policy | Cần file log lâu dài có giới hạn và chính sách lưu giữ | Phải cấu hình đúng rolling/triggering policy và retention |
| `AsyncAppender` | Đưa event vào queue rồi chuyển cho appender đích | Muốn giảm phần thời gian ghi đồng bộ trên thread nghiệp vụ | Queue đầy, block/drop, shutdown và chi phí bộ nhớ |
| `SiftingAppender` | Phân luồng event tới appender động theo một khóa ngữ cảnh | Cần tách file theo tenant/job trong phạm vi được kiểm soát | Số appender/file động có thể tăng mạnh; lifecycle phức tạp |
| `SocketAppender` | Gửi log event qua mạng tới hệ thống nhận tương thích | Một số kiến trúc thu thập log tập trung | Phải xét tin cậy đường truyền, định dạng, kết nối và bảo mật |

Không phải mọi appender đều nằm cùng module hoặc có đầy đủ chức năng trong mọi phiên bản Logback. `ConsoleAppender`, `FileAppender` và `RollingFileAppender` thuộc Logback Core; `AsyncAppender` thường dùng trong Logback Classic với `ILoggingEvent`. Những loại appender chuyên biệt khác có thể phụ thuộc thêm module hoặc thư viện.

**Không nên chọn appender chỉ theo tên.** Chọn theo yêu cầu: cần log ra stdout cho collector của container, cần lưu file và rotate, cần giảm độ trễ, hay cần chuyển log đến hệ thống khác? Sau đó xác định chính sách mất log, lưu giữ và bảo vệ dữ liệu cho đích đó.

## 4. Cấu hình appender trong logback.xml

Cấu hình Logback phổ biến nằm trong `src/main/resources/logback.xml` và được đưa lên runtime classpath. Với cấu hình XML, các appender được khai báo bằng thẻ `<appender>`, đặt tên qua `name` và chỉ định class triển khai qua `class`. Logger hoặc root logger gắn appender qua `<appender-ref ref="..."/>`.

Ví dụ:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ở đây:

- `CONSOLE` là tên appender do dự án đặt; `ref="CONSOLE"` phải khớp chính xác.
- `ConsoleAppender` ghi về stdout trong cấu hình này.
- `<encoder>` với `PatternLayoutEncoder` mặc định theo Joran của Logback có pattern `%level %msg%n`: mức log, một khoảng trắng, message và newline.
- `<root level="INFO">` đặt ngưỡng ở root logger; những logger kế thừa mức này thường chỉ phát INFO/WARN/ERROR.
- Một appender **được định nghĩa nhưng không được tham chiếu** bởi đường logger liên quan có thể không nhận event mong đợi.

Pattern thường dùng khi điều tra:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
~~~

`%d` là thời điểm, `%-5level` là mức log có căn lề, `%thread` là thread, `%logger{36}` rút gọn tên logger, `%msg` là message và `%n` là newline. Pattern có thể thêm `%X{requestId}` nếu ứng dụng dùng MDC đúng cách.

**Appender và encoder không tự biến message thành JSON.** Muốn structured logging, phải dùng encoder/layout được hỗ trợ và cấu hình tương ứng. Chỉ đặt message dạng `key=value` vẫn có thể chỉ tạo một chuỗi text.

## 5. Ví dụ Java 17 chạy được: cùng event tới console và file

Ví dụ này dùng **SLF4J API 2.0.17** với **Logback Classic 1.5.18**, một cặp phiên bản minh họa tương thích để thực hành trên JDK 17. Đây **không phải khẳng định về phiên bản mới nhất**; dự án thật nên dùng dependency management và version đã được phê duyệt. Vì Logback là thư viện ngoài JDK, cần Maven/Gradle hoặc classpath phù hợp; riêng `javac` không có dependency sẽ không tìm thấy `org.slf4j.*`.

Tạo cấu trúc:

~~~text
logback-appender-demo/
  pom.xml
  src/main/java/example/AppenderDemo.java
  src/main/resources/logback.xml
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>logback-appender-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.AppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`slf4j-api` cung cấp API Logger, `logback-classic` cung cấp SLF4J provider và backend Logback. Maven tự kéo các dependency chuyển tiếp cần thiết của Logback; không cần khai báo một provider SLF4J khác cho ví dụ.

### 5.2. AppenderDemo.java

~~~java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(AppenderDemo.class);

    private AppenderDemo() {
    }

    public static void main(String[] args) {
        String orderId = "O-42";

        LOG.debug("step=validate orderId={}", orderId);
        LOG.info("operation=checkout orderId={} state={}",
                orderId, "started");
        LOG.warn("operation=checkout orderId={} event={}",
                orderId, "fallback");
        LOG.info("operation=checkout orderId={} state={}",
                orderId, "completed");
    }
}
~~~

Mã chủ yếu gọi SLF4J, không gọi trực tiếp `ConsoleAppender` hay `FileAppender`. Vì vậy thay đường ghi sau này chủ yếu là thay cấu hình backend, không cần sửa những lệnh log nghiệp vụ.

### 5.3. logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>target/appender-demo.log</file>
        <append>true</append>
        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Console và file ở đây là **hai đích riêng**. Appender `FILE` ghi tới `target/appender-demo.log` tính theo thư mục làm việc của tiến trình; khi chạy qua Maven ở thư mục dự án, `target` đã được tạo bởi bước build. `<append>true</append>` ghi nối vào file hiện có sau mỗi lần chạy, do đó nếu chạy lại, nội dung file tiếp tục tăng; không coi file luôn chỉ có ba dòng. Nếu muốn bắt đầu từ file mới cho một bài tập, xóa file thử nghiệm một cách chủ động trước khi chạy.

### 5.4. Chạy và kiểm tra output

Trong thư mục `logback-appender-demo`:

~~~bash
mvn -q compile exec:java
~~~

Phần log do **ứng dụng** xuất ra stdout với cấu hình trên là:

~~~text
INFO operation=checkout orderId=O-42 state=started
WARN operation=checkout orderId=O-42 event=fallback
INFO operation=checkout orderId=O-42 state=completed
~~~

Dòng DEBUG không xuất hiện vì root logger dùng ngưỡng INFO. File `target/appender-demo.log` cũng nhận ba dòng ứng dụng đó trong lần chạy đầu với file mới; các lần chạy sau sẽ nối thêm ba dòng. Tùy Maven, hệ điều hành hoặc môi trường khởi chạy có thể có thông báo riêng của công cụ ngoài ba dòng log minh họa.

Chỉ cần đổi `root level="INFO"` thành `DEBUG` và chạy lại, sự kiện `step=validate orderId=O-42` sẽ được cả hai appender nhận trước các dòng INFO/WARN, vì hai appender không có filter loại DEBUG riêng.

**Kiểm tra cấu hình:** nếu muốn giữ log ERROR/WARN trong file nhưng console nhận cả INFO, thêm filter ở appender FILE (mục 8). Việc thay filter của FILE sẽ không ảnh hưởng trực tiếp đến log của CONSOLE.

## 6. RollingFileAppender: file log có chính sách xoay vòng

`FileAppender` ghi liên tục vào một file, nên nếu ứng dụng chạy lâu mà không quản lý kích thước, file có thể trở nên rất lớn hoặc làm đầy volume. `RollingFileAppender` mở rộng cách ghi file bằng **rolling policy**; khi đến thời điểm/điều kiện rollover, file cũ có thể được chuyển vào archive và file đang ghi tiếp tục nhận sự kiện.

Một cấu hình phổ biến, xoay vòng theo ngày:

~~~xml
<!-- Đặt trong <configuration> để thay appender FILE của ví dụ. -->
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/appender-demo.log</file>
    <append>true</append>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>target/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>100MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

Cấu hình này dùng tên file active cố định và archive theo ngày. `fileNamePattern` có `%d{...}` để xác định đơn vị thời gian. `maxHistory=7` giữ giới hạn lịch sử theo kỳ ngày và `totalSizeCap=100MB` giúp giới hạn dung lượng archive theo cơ chế dọn dẹp của policy. **Các giới hạn không nhất thiết xóa file ngay tại khoảnh khắc vừa vượt ngưỡng**; cleanup thường gắn với rollover, và có tùy chọn cleanup khi khởi động tùy phiên bản/cấu hình. File active và các cơ chế backup bên ngoài cũng không nhất thiết nằm trong giới hạn archive này.

**Nếu cần vừa theo thời gian vừa theo kích thước**, Logback có `SizeAndTimeBasedRollingPolicy`. Ví dụ đoạn thay `rollingPolicy`:

~~~xml
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>target/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>10MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>100MB</totalSizeCap>
</rollingPolicy>
~~~

Ở chính sách kết hợp này, `%i` là chỉ số giúp đặt tên các archive trong cùng kỳ khi chạm giới hạn kích thước. **Đừng chỉ thêm `<maxFileSize>` vào TimeBasedRollingPolicy đơn thuần rồi kỳ vọng nó tự xoay theo kích thước**; phải dùng policy hỗ trợ đúng điều kiện. Các giá trị 10MB/7 ngày/100MB là ví dụ; chọn theo throughput, retention và dung lượng thực tế.

### Những điểm vận hành của rolling file

- Đảm bảo đường dẫn có quyền ghi và volume còn dung lượng.
- Không để nhiều tiến trình ghi chung một file một cách tùy tiện; đồng bộ file, chế độ prudent, locking và rollover giữa nhiều process là vấn đề cần thiết kế riêng.
- Nên tránh để công cụ rotate ngoài hệ thống và Logback đồng thời quản lý cùng file mà không có cơ chế phối hợp; đổi tên/truncate file có thể làm mất hoặc lặp dòng.
- Thử điều kiện rollover và retention trong môi trường thật, không chỉ kiểm tra rằng file active đã xuất hiện.
- File nén/archived log vẫn có thể chứa dữ liệu nhạy cảm, cần chính sách truy cập và xóa phù hợp.

## 7. AsyncAppender: tách một phần ghi log khỏi thread nghiệp vụ

`AsyncAppender` của Logback Classic là một **wrapper appender**: nó nhận `ILoggingEvent` và đưa vào hàng đợi, sau đó một worker chuyển sự kiện tới appender đích. Nó không tự quyết định file hay console cuối cùng; vẫn cần tham chiếu một appender thích hợp.

Ví dụ bọc FILE qua ASYNC:

~~~xml
<!-- FILE phải được định nghĩa trước và là appender đích hợp lệ. -->
<appender name="ASYNC"
          class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>512</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <includeCallerData>false</includeCallerData>
    <appender-ref ref="FILE"/>
</appender>
~~~

Trong cùng file cấu hình, thay root bằng:

~~~xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC"/>
</root>
~~~

Khi đó console ghi trực tiếp và FILE nhận event qua ASYNC. **Không đồng thời tham chiếu `FILE` trực tiếp và `ASYNC` (đang chuyển vào FILE) trên cùng đường log**, nếu không file có thể nhận mỗi sự kiện hai lần.

Các tùy chọn quan trọng:

| Thuộc tính | Ý nghĩa | Tác động cần hiểu |
| --- | --- | --- |
| `queueSize` | Số slot của hàng đợi | Queue lớn giữ nhiều event/bộ nhớ hơn, queue nhỏ dễ đầy sớm |
| `discardingThreshold` | Ngưỡng bắt đầu loại bớt event ít quan trọng khi queue gần đầy | Logback Classic có cơ chế discard những mức thấp như TRACE/DEBUG/INFO trong tình huống này |
| `neverBlock` | Quy tắc khi queue đầy | `false` thường cho phép chờ enqueue; `true` ưu tiên không block nhưng có thể bỏ event |
| `includeCallerData` | Có thu thập thông tin caller đầy đủ không | Bật có thể tốn thêm chi phí stack inspection |
| `maxFlushTime` | Giới hạn chờ worker flush khi dừng appender | Nếu chưa drain hết queue, có thể mất các event chưa ghi |

**Phân biệt hai chính sách:** `discardingThreshold=0` tắt việc bỏ sớm các mức ít quan trọng vì ngưỡng gần đầy, nhưng **không bảo đảm tuyệt đối không mất log** trong mọi trường hợp như crash/kill hoặc khi cấu hình bỏ event lúc đầy. `neverBlock=false` có thể khiến thread nghiệp vụ phải chờ nếu queue đầy. Đây là đánh đổi giữa độ trễ của ứng dụng và độ đầy đủ của bản ghi.

Async chuyển một phần encoding/I/O sang worker, nhưng **không làm tổng tài nguyên sử dụng bằng 0**. Theo dõi CPU, heap, GC, queue depth, throughput, p95/p99 latency, lượng event bị drop và thời gian shutdown. Không mặc định appender async trong bộ nhớ là giải pháp lưu trữ audit bền vững.

### Khi nào nên chọn async?

Cân nhắc khi ghi file hoặc network trên đường request gây độ trễ rõ rệt, khi có nhiều event cần batch/đệm, và ứng dụng đã xác định cách xử lý lúc collector chậm. Với một CLI nhỏ vài dòng INFO, appender đồng bộ đơn giản có thể đủ. Với sự kiện bắt buộc bảo toàn, cần kiểm chứng độ tin cậy end-to-end của đường thu thập.

## 8. Filter ở appender: mỗi đích một chính sách

Logback có các filter thực hiện các quyết định `DENY`, `NEUTRAL` hoặc `ACCEPT` tùy filter. Hai loại hay gặp trong Logback Classic:

### 8.1. ThresholdFilter: từ một mức trở lên

Ví dụ FILE chỉ nhận WARN và ERROR:

~~~xml
<appender name="FILE"
          class="ch.qos.logback.core.FileAppender">
    <file>target/warnings.log</file>

    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>

    <encoder>
        <pattern>%level %msg%n</pattern>
    </encoder>
</appender>
~~~

`ThresholdFilter` loại những event thấp hơn WARN, cho phép những event từ WARN trở lên đi tiếp qua appender. Trong khi đó CONSOLE có thể vẫn xuất INFO, nếu nó không gắn filter tương ứng.

### 8.2. LevelFilter: đúng một mức

Khi cần đích chỉ nhận **đúng ERROR**, có thể dùng:

~~~xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>ERROR</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
~~~

Đây là đoạn filter **phải đặt bên trong phần khai báo một appender**, không phải phần tử root độc lập. `LevelFilter` có hai lựa chọn theo match/mismatch; nó khác `ThresholdFilter` vốn dựa trên thứ tự mức.

**Logger level vẫn là điều kiện đầu tiên.** Nếu logger chặn DEBUG, không appender filter nào có thể “lấy lại” DEBUG đã bị loại. Nếu appender chặn INFO, tăng mức logger thành DEBUG chỉ khiến logger tạo thêm event; appender vẫn giữ chính sách riêng.

## 9. SiftingAppender và định tuyến động

`SiftingAppender` có thể tạo/chọn appender khác nhau dựa trên **giá trị discriminating key** của event, thường liên quan MDC. Chẳng hạn tách log theo `jobId` khi có số lượng job hữu hạn và có chính sách lifecycle/retention cụ thể.

Ý tưởng:

~~~text
MDC jobId=A -> SiftingAppender -> appender cho job A -> file A
MDC jobId=B -> SiftingAppender -> appender cho job B -> file B
~~~

Đây là sơ đồ khái niệm. SiftingAppender hữu ích khi việc chia đích giúp điều tra hoặc phân quyền, nhưng dễ tạo **rất nhiều appender và file** khi khóa có số lượng giá trị quá lớn hoặc do input người dùng kiểm soát. Không dùng raw request ID hay user input chưa kiểm soát trực tiếp làm tên file. Cần giới hạn số khóa, vòng đời appender, quyền ghi, độ an toàn đường dẫn và dọn dẹp.

Trong hệ thống nhiều tenant lớn, lựa chọn ghi **một luồng JSON có trường `tenantId` an toàn** rồi phân tách bằng collector có thể dễ vận hành hơn hàng nghìn file động. Quyết định phụ thuộc vào yêu cầu hệ thống.

## 10. Truyền log qua mạng và ứng dụng container

Không phải mọi hệ thống cần SocketAppender. Trong môi trường container, ứng dụng thường ghi console, để runtime/agent thu thập và chuyển tiếp log. Mô hình phổ biến:

~~~text
SLF4J -> Logback ConsoleAppender -> stdout/stderr
       -> container log driver/agent -> collector -> storage/search
~~~

Ưu điểm là ứng dụng tập trung vào phát sự kiện; pipeline bên ngoài chịu trách nhiệm vận chuyển/lưu trữ. Tuy vậy stdout **vẫn tiêu tốn I/O**, và driver/agent có thể gặp tình trạng backpressure hoặc mất event tùy cấu hình.

Nếu appender gửi trực tiếp qua socket, cần hiểu định dạng đầu nhận, thời gian retry, kết nối mạng, bảo mật đường truyền và cách xử lý khi collector không sẵn sàng. **Không khẳng định log đã bền vững chỉ vì `logger.info(...)` trả về thành công**; event có thể còn trong queue, buffer hoặc chưa được collector xác nhận.

Chọn đường ghi theo hạ tầng của ứng dụng, không bắt buộc tất cả backend phải trực tiếp gửi log sang mạng. Nếu yêu cầu lưu giữ có tính pháp lý/audit, cần cơ chế tin cậy được thiết kế riêng thay vì phụ thuộc duy nhất vào một queue appender thông thường.

## 11. Viết appender tùy biến: lúc nào và cần lưu ý gì?

Logback cung cấp các lớp nền như `AppenderBase<E>` và `UnsynchronizedAppenderBase<E>` trong `logback-core`. Trong trường hợp thật sự cần đích đặc biệt, ta có thể viết appender tùy biến, xử lý `ILoggingEvent` khi dùng Logback Classic.

Ví dụ **minh họa cơ chế**, không phải ứng dụng hoàn chỉnh:

~~~java
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

public final class CountingAppender
        extends AppenderBase<ILoggingEvent> {

    private long acceptedCount;

    @Override
    protected void append(ILoggingEvent event) {
        acceptedCount++;
        // Chỉ để mô tả: không ghi ra console, file hay network.
    }

    public long getAcceptedCount() {
        return acceptedCount;
    }
}
~~~

`AppenderBase` cung cấp cơ chế vòng đời/filter cơ bản và gọi phương thức `append(...)` do subclass triển khai khi appender đang ở trạng thái hoạt động. Mã trên chỉ chứng minh cách nhận sự kiện; **không dùng bộ đếm `long` không đồng bộ để thu thập số liệu trong môi trường đa thread**, và không dùng appender tự viết cho chức năng đã có sẵn mà chưa cân nhắc thread-safety, chi phí I/O, lifecycle và xử lý lỗi.

Khi cần metric cho số lượng log, dùng hệ thống metrics hoặc appender đã được kiểm chứng có thể phù hợp hơn. Đối với appender tùy biến thật, cần thiết kế `start()`/`stop()`, quản lý resource, xử lý exception, đóng luồng an toàn và không để việc ghi log nội bộ của chính appender tạo vòng lặp vô hạn.

## 12. MDC, formatter và an toàn dữ liệu trong appender

Appender nhận event đã có thông tin ngữ cảnh, nhưng **có hay không xuất ngữ cảnh ra log phụ thuộc encoder/layout**. Ví dụ Logback pattern:

~~~xml
<pattern>%d{HH:mm:ss.SSS} %-5level requestId=%X{requestId} %msg%n</pattern>
~~~

Nếu ứng dụng đặt MDC `requestId`, pattern có thể thêm giá trị đó vào từng dòng. Trong ứng dụng dùng thread pool, MDC thông thường có quan hệ với thread; mã ứng dụng cần dọn context khi kết thúc request và truyền context chủ động qua ranh giới bất đồng bộ theo cơ chế phù hợp.

Dùng MDC giúp nối log của nhiều bước nhưng **không tự động tạo distributed trace**. Muốn theo dõi request xuyên dịch vụ, cần cơ chế tracing/truyền trace ID tương ứng. Một dòng ở mức TRACE và một event có `traceId` là hai ý niệm khác nhau.

Appender và encoder cũng **không tự bảo vệ bí mật**. Không ghi password, token, cookie hoặc payload chứa dữ liệu cá nhân không cần thiết. Nếu input người dùng chứa newline/ký tự điều khiển, dùng encoder có escaping đúng đích hoặc chuẩn hóa trường để tránh log forging. Log file/archive/collector cần được phân quyền và đặt retention tương ứng.

Nên chọn thông điệp giàu ngữ cảnh nhưng ngắn:

~~~text
operation=checkout requestId=req-12 orderId=O-42 outcome=success durationMs=28
~~~

Ví dụ này không ghi số thẻ, mật khẩu, địa chỉ hay toàn bộ request. Nó vẫn giúp tìm request và đo thời gian nếu trường được phát và xử lý nhất quán.

## 13. Xử lý sự cố: không thấy log, log trùng hoặc log bị mất

### Không thấy log

1. Kiểm tra SLF4J có **provider Logback** tương thích trên runtime classpath không; nếu thiếu provider, lời gọi có thể chuyển sang NOP hoặc triển khai khác.
2. Kiểm tra ngưỡng logger (`INFO`, `DEBUG`...), mức kế thừa và bộ lọc ở appender.
3. Kiểm tra appender đã được khai báo, có `name` đúng và **được tham chiếu** qua `appender-ref` ở đường logger tương ứng.
4. Xem đường đích, quyền ghi, dung lượng file, stderr/stdout và thư mục làm việc của tiến trình.
5. Kiểm tra lỗi parse XML/khởi tạo appender. Thông báo trạng thái khởi động của Logback hoặc `StatusPrinter` có thể giúp xác định appender không start hay file không mở được.
6. Nếu sử dụng AsyncAppender, quan sát queue/drop và shutdown. Có thể event chưa được ghi hoặc đã bị loại ở hàng đợi.

### Log trùng

- Kiểm tra cùng một appender được gắn ở logger con và root với additivity=true.
- Kiểm tra cùng đích file/console được kết nối qua **hai đường**: trực tiếp và thông qua AsyncAppender.
- Xem có nhiều handler hoặc bridge logging tạo tuyến lặp không. Các module bridge hai chiều có thể chuyển event qua nhiều framework không mong muốn.
- Kiểm tra code có log cùng exception ở nhiều tầng rồi rethrow liên tiếp không. Đây là log trùng do mã, khác với trùng do appender.

### Log thất lạc hoặc sai thứ tự

- Log có thể bị filter ở logger/appender, hoặc async queue loại bớt event khi tải lớn.
- Event trong queue/buffer có thể không kịp ghi khi tiến trình bị kill/crash.
- Nhiều thread và hệ thống tập trung có thể xử lý/truyền event không đồng thời. Không dùng thứ tự xuất hiện giữa các thread để khẳng định tuyệt đối thứ tự nhân quả.
- Với rolling file, cần kiểm tra rollover, retention và file active/archive khi tìm sự kiện cũ.
- Với output JSON, xác nhận encoder thực sự có trường cần tìm và có render Throwable đầy đủ nếu mục tiêu là điều tra exception.

## 14. Chọn appender theo mục tiêu vận hành

| Nhu cầu | Phương án thường phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Ứng dụng chạy trong container có log agent | ConsoleAppender -> stdout/stderr | Log driver/agent, routing, volume, backpressure |
| CLI/ứng dụng nhỏ | ConsoleAppender | Mức log, format, độ nhiễu |
| Server cần log file | RollingFileAppender | Rollover, maxHistory, totalSizeCap, dung lượng volume |
| Appender đồng bộ làm tăng p99 | AsyncAppender -> appender đích | queueSize, drop/block, shutdown, số event bị mất |
| Chỉ muốn WARN/ERROR ra một đích | ThresholdFilter ở appender đó | Logger vẫn phải chấp nhận WARN/ERROR |
| Tách log theo một khóa giới hạn | SiftingAppender | Cardinality, lifecycle, số lượng file, bảo mật |
| Thu thập tập trung qua mạng | Console + agent hoặc appender mạng phù hợp | Retry, encoding, tính tin cậy, TLS/quyền truy cập |

Khi thay đổi cấu hình, thử đủ ba trường hợp: chạy bình thường, phát nhiều log dưới tải, và đích nhận log chậm/lỗi. Đánh giá **CPU, GC/heap, throughput, latency p95/p99, byte/s, queue depth và dropped events**. Không kết luận async hiệu quả chỉ vì thời gian gọi `LOG.info(...)` giảm: công việc ghi có thể đang dồn ở queue.

## 15. Những lỗi cấu hình phổ biến và cách phòng tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khai báo appender nhưng quên `appender-ref` | Logger không gửi event đến đích | Gắn appender ở logger/root đúng |
| Sai tên `ref` | Không tham chiếu được appender | Khớp chính xác `name` và `ref` |
| Đặt log level DEBUG ở logger nhưng appender filter WARN | Không thấy DEBUG ở đích đó | Xem cả logger level lẫn appender filter |
| Gắn cùng appender ở con và root | Một event có thể được ghi hai lần | Xem additivity, chỉ giữ đường mong muốn |
| Cùng FILE nhận trực tiếp và qua ASYNC | File trùng dòng | Chọn một đường tới cùng đích |
| Chỉ dùng FileAppender suốt thời gian dài | File tăng vô hạn | Dùng rolling/retention phù hợp |
| Cấu hình size rollover sai policy | Không rotate như kỳ vọng | Dùng SizeAndTimeBasedRollingPolicy khi cần cả thời gian và kích thước |
| Async queue quá nhỏ, discard không rõ ràng | Mất TRACE/DEBUG/INFO hoặc block request | Điều chỉnh chính sách dựa trên yêu cầu, đo drop/block |
| Bật includeCallerData cho mọi event | Tăng chi phí stack inspection | Bật khi thực sự cần và đo dưới tải |
| Chỉ dùng `%msg` mà muốn MDC/Throwable chi tiết | Log thiếu ngữ cảnh và lỗi | Cấu hình pattern/encoder tương ứng |
| Ghi raw user input/secret | Rò rỉ dữ liệu, log forging | Chọn trường an toàn, escape/limit, phân quyền |
| Hiểu appender async là lưu bền vững | Queue chưa ghi có thể mất khi crash | Thiết kế độ tin cậy end-to-end riêng |

## 16. Bài tập thực hành

1. **Console + file:** chạy ví dụ Maven ở mục 5. Giải thích vì sao có ba dòng log ứng dụng trên stdout và file, còn DEBUG không xuất. Chuyển root thành DEBUG và dự đoán số event được hai appender nhận.
2. **Additivity:** gắn `FILE` vào `logger name="example"` và root cùng lúc. Với additivity mặc định, dự đoán vì sao file có thể bị ghi trùng. Sửa bằng cách đặt lại điểm tham chiếu hoặc `additivity="false"` kèm appender cần thiết.
3. **Filter:** thêm `ThresholdFilter WARN` vào FILE nhưng giữ root INFO. Dự đoán console có bao nhiêu dòng và file có bao nhiêu dòng trong **một lần chạy với file mới**.
4. **Rolling:** thay FILE bằng RollingFileAppender, cấu hình archive theo ngày và `maxHistory`. Phân biệt chức năng của `file`, `fileNamePattern` và policy; nêu cách kiểm tra retention khi rollout.
5. **Async:** giả sử ứng dụng phát 10.000 log/s trong khi appender đích chỉ ghi được 8.000 log/s. Queue tăng trung bình bao nhiêu event/s nếu chưa bị chặn/loại? Thảo luận cách `neverBlock` và `discardingThreshold` ảnh hưởng khi backlog tăng.
6. **Bảo mật:** thiết kế pattern có `requestId` từ MDC mà không log token. Giải thích cách dọn MDC và vì sao encoder cần xử lý input có newline.
7. **Chẩn đoán:** ứng dụng có INFO trong mã nhưng file trống, console vẫn có INFO. Nêu thứ tự kiểm tra logger, filter appender, appender-ref, quyền file, cấu hình startup và async.

**Ghi nhớ:** Appender là thành phần quyết định **đường đi và đích xuất** của log event trong Logback. Logger quyết định mức sự kiện, appender có filter riêng, encoder/layout quyết định định dạng. Hiểu **appender-ref, additivity, File/RollingFile/Console/AsyncAppender, chính sách queue và retention** sẽ giúp ghi đúng đích, tránh log trùng hoặc mất log và quản lý chi phí logging hợp lý.