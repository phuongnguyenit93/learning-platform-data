# Rolling appender trong Java Logging

## 1. Rolling appender là gì?

**Rolling appender** là appender ghi log ra file nhưng có thêm cơ chế **rollover**: khi một điều kiện được thỏa, file đang ghi được chuyển thành bản lưu trữ (*archive*), một file mới bắt đầu nhận các log event tiếp theo. Nhờ đó ứng dụng tránh để một file duy nhất tăng liên tục, dễ phân loại log theo thời gian và có thể áp dụng chính sách lưu giữ phù hợp.

Trong các hệ thống Java phổ biến:

- **Logback** dùng `ch.qos.logback.core.rolling.RollingFileAppender` cùng *rolling policy*.
- **Apache Log4j 2** dùng plugin `RollingFile`, kết hợp *triggering policy* (khi nào xoay) và *rollover strategy* (xoay/lưu/xóa thế nào).
- **`java.util.logging` (JUL)** có `FileHandler` hỗ trợ file rotation theo dung lượng và số file, nhưng không gọi là `RollingFileAppender` và không dùng cùng cú pháp XML như Logback/Log4j2.

Rolling appender **không phải logger**, không quyết định mọi mức log theo cách riêng và cũng không tự thu thập log từ mọi dịch vụ. Mã ứng dụng gọi logger; backend xử lý level/filter, tạo log event, rồi appender nhận và ghi event theo đường dẫn được cấu hình.

Sơ đồ:

~~~text
Java code -> Logger -> filter/level -> Logging event
                                      |
                                      v
                             Rolling file appender
                                      |
               +----------------------+--------------------+
               |                                           |
         Active log file                           Triggering condition?
         logs/app.log                         time/size/startup/custom...
               |                                           |
               +----------------------+--------------------+
                                      |
                                      v
                           Rollover / archive
                       logs/archive/app-....log.gz
                                      |
                                      v
                        Retention / cleanup policy
~~~

Tùy cấu hình, rollover có thể đổi tên, chuyển file, nén archive hoặc chuyển tiếp ghi sang file mới. **Điều kiện rollover và điều kiện xóa archive là hai loại quy tắc khác nhau.**

## 2. Phân biệt active file, rollover, archive và retention

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Active file | File hiện tại mà appender đang ghi | `logs/app.log` |
| Trigger / triggering policy | Điều kiện khiến appender đánh giá cần xoay file | Đổi ngày, đạt 10 MB, khởi động JVM |
| Rollover | Thao tác kết thúc một chu kỳ ghi, tạo archive và mở/đổi file active | `app.log` được archive thành `app-2026-11-09.log.gz` |
| Archive file | File của chu kỳ đã kết thúc, có thể đã nén | `logs/archive/app-2026-11-09.0.log.gz` |
| Rolling policy / rollover strategy | Cách tổ chức tên, vị trí và hành vi xoay file | `TimeBasedRollingPolicy`, `DefaultRolloverStrategy` |
| Retention | Chính sách giữ và xóa những archive cũ | Giữ 7 ngày hoặc giới hạn tổng archive 1 GB |
| Compression | Nén archive để tiết kiệm dung lượng | Hậu tố `.gz` hoặc `.zip` |

Ví dụ mô tả: appender ghi dữ liệu vào `logs/app.log`. Sau khi đến kỳ rollover, dữ liệu của giai đoạn trước được chuyển thành archive `logs/archive/app-2026-11-09.log.gz`, còn `logs/app.log` tiếp tục nhận event mới.

**Không nên hiểu rollover là timer tự động xóa file vào đúng 00:00 trên mọi backend.** Nhiều cấu hình time-based đánh giá nhu cầu rollover khi một log event mới được ghi sau khi vượt ranh giới thời gian. Nếu ứng dụng không phát event trong nhiều giờ, archive có thể chỉ xuất hiện khi có bản ghi tiếp theo hoặc khi cơ chế khởi động/cleanup phù hợp chạy.

**Retention không đồng nghĩa với backup lâu dài.** Một archive có thể bị xóa đúng chính sách và không còn khả năng khôi phục. Nếu log bắt buộc giữ theo quy định, cần thiết kế nơi lưu bền vững/backup và quyền truy cập riêng, không chỉ dựa vào thư mục archive của appender.

## 3. Khi nào nên dùng rolling appender?

Rolling appender đặc biệt có giá trị khi ứng dụng **cần ghi file log tại máy/volume** trong thời gian dài:

1. **Server chạy liên tục:** log tăng mỗi ngày, cần file active dễ theo dõi nhưng archive có lịch sử theo ngày.
2. **Batch/job tạo nhiều event:** file một ngày có thể rất lớn, nên kết hợp điều kiện dung lượng và thời gian.
3. **Điều tra lỗi theo thời điểm:** tên archive chứa ngày hoặc kỳ giúp khoanh vùng nhanh.
4. **Quản trị dung lượng:** đặt giới hạn số kỳ lưu và tổng dung lượng archive, tránh file cũ tích tụ vô hạn.
5. **Chuyển log cho collector:** agent có thể đọc file active và archive nếu được thiết kế phù hợp với cách rotate.

Không phải môi trường nào cũng cần rolling file cục bộ. Trong **container/Kubernetes**, một mô hình phổ biến là ứng dụng ghi stdout/stderr bằng ConsoleAppender, còn runtime và agent chịu trách nhiệm thu thập/rotate tại hạ tầng. Chạy đồng thời cả rolling file trong container lẫn external log rotation khi không có phối hợp có thể làm đường log phức tạp và tăng chi phí.

## 4. RollingFileAppender của Logback: các thành phần chính

Logback Core cung cấp `RollingFileAppender`. Khi dùng Logback làm backend cho SLF4J, mã ứng dụng vẫn gọi các phương thức SLF4J `info(...)`, `warn(...)`, `error(...)`; XML quyết định file và cách rollover.

Ví dụ cấu hình Logback theo ngày:

~~~xml
<appender name="ROLLING"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/app.log</file>
    <append>true</append>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

Đây là **đoạn nằm trong `<configuration>`**, chưa đầy đủ vì cần tham chiếu appender trong `<root>` hoặc `<logger>`.

### 4.1. `<file>`: tên file active

`<file>logs/app.log</file>` chỉ đường dẫn mà ứng dụng đang ghi. Khi dùng đường dẫn tương đối, vị trí thực tế phụ thuộc working directory của tiến trình JVM. Trong một deployment khác, cùng đường dẫn tương đối có thể trỏ sang thư mục khác.

Có thể không đặt `<file>` ở một số cấu hình rolling phù hợp, để tên file hoạt động thay đổi theo pattern; nhưng nếu muốn một tên active ổn định cho agent đọc, khai báo file rõ ràng thường dễ vận hành.

### 4.2. `<fileNamePattern>`: tên archive

Pattern `app.%d{yyyy-MM-dd}.log.gz` tạo tên archive có thành phần ngày. Hậu tố `.gz` yêu cầu nén archive theo cơ chế Logback hỗ trợ. Ký hiệu `%d{...}` quyết định kỳ thời gian; `%d{yyyy-MM-dd}` thường là theo ngày, còn `%d{yyyy-MM-dd_HH}` có độ chi tiết theo giờ.

**Không nhầm pattern archive với pattern nội dung dòng log.** `fileNamePattern` đặt tên file; `<encoder><pattern>...` quyết định text được ghi trong file.

### 4.3. `<maxHistory>`: giữ bao nhiêu kỳ

`<maxHistory>7</maxHistory>` thường có nghĩa giữ các kỳ lịch sử tương ứng với đơn vị thời gian của pattern: với archive theo ngày là khoảng 7 kỳ ngày, với archive theo tháng là 7 kỳ tháng. Nó không đơn giản là số lượng **bảy file**: nếu có nhiều archive trong một ngày, vẫn có thể có nhiều file thuộc một kỳ.

### 4.4. `<totalSizeCap>`: giới hạn tổng archive

`<totalSizeCap>1GB</totalSizeCap>` đặt trần tổng kích thước archive chịu quản lý bởi rolling policy. Nó **không phải trần cứng áp cho mọi byte trên volume**: file active, file ngoài pattern, dữ liệu backup, file tạm và các file do hệ thống khác tạo có thể nằm ngoài phạm vi này.

Thông thường `maxHistory` cần được cấu hình để áp dụng `totalSizeCap` trong time-based policy. Cleanup gắn với chu kỳ rollover và các tùy chọn khởi động; **không nên hứa dung lượng sẽ luôn dưới trần tại mọi thời điểm**. Nếu ứng dụng ghi rất ít hoặc ngừng lâu, thời điểm dọn dẹp có thể khác kỳ vọng.

### 4.5. `<append>`, encoder và tham chiếu appender

`<append>true</append>` cho phép tiếp tục ghi vào file đang tồn tại thay vì tự động truncate khi khởi động. Encoder chuyển event thành byte: pattern có `%level`, `%logger`, `%msg`, `%n` hoặc `%X{requestId}` cho MDC. Nếu chưa gắn `ROLLING` vào logger/root bằng `<appender-ref ref="ROLLING"/>`, định nghĩa appender có thể không nhận log nào.

## 5. Ví dụ Java 17 chạy được: SLF4J + Logback + RollingFileAppender

Ví dụ sử dụng **JDK 17, Maven, SLF4J 2.0.17 và Logback Classic 1.5.18** để chạy một dự án nhỏ. Đây là cặp phiên bản minh họa tương thích để thực hành, **không phải khẳng định là phiên bản mới nhất**. Dự án thật nên dùng version/BOM đã được kiểm tra bảo mật và chính sách dependency của dự án.

Cấu trúc thư mục:

~~~text
rolling-log-demo/
  pom.xml
  src/main/java/example/RollingDemo.java
  src/main/resources/logback.xml
~~~

### 5.1. Tạo pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>rolling-log-demo</artifactId>
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
                    <mainClass>example.RollingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`slf4j-api` là facade mà mã Java gọi. `logback-classic` cung cấp provider/implementation; Maven sẽ đưa các dependency chuyển tiếp cần thiết lên classpath. Không thêm một SLF4J provider khác như `slf4j-simple` vào ví dụ vì có thể gây nhiều provider cạnh tranh.

### 5.2. Tạo RollingDemo.java

~~~java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RollingDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(RollingDemo.class);

    private RollingDemo() {
    }

    public static void main(String[] args) {
        String jobId = "J-17";

        LOG.debug("jobId={} step=prepare", jobId);
        LOG.info("jobId={} phase=started", jobId);
        LOG.warn("jobId={} retry={} reason={}",
                jobId, 1, "temporary-unavailable");
        LOG.info("jobId={} phase=finished processed={}",
                jobId, 3);
    }
}
~~~

Chương trình không mở file bằng `FileOutputStream`, không gọi trực tiếp RollingFileAppender và không tự biết lịch rollover. Toàn bộ việc ghi file thuộc cấu hình Logback.

### 5.3. Tạo logback.xml

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

    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>target/logs/app.log</file>
        <append>true</append>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>target/logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
~~~

Đặt file ở `src/main/resources/logback.xml`. Khi chạy Maven từ thư mục gốc của dự án, `target` được tạo trong quá trình build và Logback có thể tạo các thư mục con cho file log theo đường dẫn được cấu hình. Trong môi trường khác cần kiểm tra working directory, quyền ghi và trạng thái khởi tạo appender.

**Hai appender nhận cùng log event**: CONSOLE xuất stdout, ROLLING ghi vào file. Không có dấu hiệu log trùng do mã gọi logger hai lần; đây là chủ đích gửi cùng sự kiện tới hai đích.

### 5.4. Biên dịch, chạy và đối chiếu output

Từ thư mục `rolling-log-demo`:

~~~bash
mvn -q compile exec:java
~~~

**Ba dòng log ứng dụng xuất ra stdout** với cấu hình trên:

~~~text
INFO jobId=J-17 phase=started
WARN jobId=J-17 retry=1 reason=temporary-unavailable
INFO jobId=J-17 phase=finished processed=3
~~~

Không có dòng DEBUG vì root level INFO. File active `target/logs/app.log` cũng chứa ba dòng tương ứng nếu mới chạy lần đầu trên file trống. Vì `append=true`, các lần chạy tiếp theo trong cùng chu kỳ có thể nối thêm dữ liệu; **không** khẳng định file luôn chỉ có ba dòng.

**Rollover chưa nhất thiết xảy ra trong bài demo ngắn.** TimeBasedRollingPolicy xoay theo ranh giới ngày của pattern, không xoay chỉ vì chương trình phát ba dòng. Để quan sát archive ngày, cần để ứng dụng chạy qua kỳ tiếp theo và phát event sau ranh giới, hoặc tạo bài test có điều kiện rút ngắn như pattern theo phút trong môi trường riêng; khi thay pattern, phải rà soát retention vì đơn vị của `maxHistory` cũng đổi.

Maven, môi trường chạy hoặc Logback status logger có thể in thêm thông báo công cụ; ba dòng ở trên là **phần log ứng dụng theo pattern đã cấu hình**, không phải cam kết stdout toàn tiến trình trong mọi môi trường.

### 5.5. Thay đổi cấu hình và dự đoán kết quả

- Đổi `<root level="INFO">` thành `DEBUG`: cả console và file có thêm dòng `DEBUG jobId=J-17 step=prepare`.
- Bỏ `<appender-ref ref="ROLLING"/>`: console vẫn có log, nhưng appender file không còn được root gọi.
- Giữ root INFO, thêm `ThresholdFilter` WARN vào ROLLING: console giữ ba dòng; file chỉ nhận dòng WARN, nhưng chỉ khi đã cấu hình filter đúng.
- Đổi pattern nội dung của ROLLING: file có timestamp/logger name khác console, nhưng logic nghiệp vụ không thay đổi.
- Đổi `append=true` thành `append=false` chỉ phục vụ thử nghiệm trong trường hợp hiểu rõ hậu quả; **không làm vậy một cách tùy tiện ở production** vì có thể ghi đè nội dung cũ khi khởi động.

## 6. Logback: kết hợp điều kiện thời gian và dung lượng

`TimeBasedRollingPolicy` thông thường dùng ngày/giờ để quyết định rollover. Nếu một file mỗi ngày có thể rất lớn, Logback có **`SizeAndTimeBasedRollingPolicy`** để xoay cả khi hết kỳ thời gian **hoặc** khi file trong kỳ hiện tại đạt ngưỡng dung lượng.

Thay đoạn `<rollingPolicy>` ở appender ROLLING bằng:

~~~xml
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>target/logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>10MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>100MB</totalSizeCap>
</rollingPolicy>
~~~

Trong pattern này:

- `%d{yyyy-MM-dd}` biểu thị kỳ ngày.
- `%i` đánh số nhiều archive trong cùng kỳ nếu log đủ lớn.
- `maxFileSize=10MB` là ngưỡng trigger theo kích thước file active.
- `maxHistory=7` giới hạn số kỳ lịch sử, **không phải đúng 7 file** vì có thể có nhiều chỉ số `%i` trong một ngày.
- `totalSizeCap=100MB` giới hạn tổng archive thuộc phạm vi policy, **không gồm mọi thứ đang nằm trên volume**.

**Cả `%d` lẫn `%i` là cần thiết** trong pattern của SizeAndTimeBasedRollingPolicy. Đừng chỉ thêm `<maxFileSize>10MB</maxFileSize>` vào TimeBasedRollingPolicy rồi kỳ vọng nó trở thành policy theo kích thước.

Một event đơn lẻ rất lớn hoặc cơ chế kích hoạt khi event mới được ghi có thể khiến kích thước thực tế vượt mốc kỳ vọng trong một khoảng ngắn. Vì vậy `maxFileSize` nên hiểu là **mốc kích hoạt rollover**, không phải kiểm tra an toàn đảm bảo tất cả file luôn nhỏ hơn 10MB tuyệt đối. Cần đặt cảnh báo dung lượng volume và giới hạn kích thước payload log riêng.

**Lưu ý thực hành:** TimeBasedRollingPolicy với `totalSizeCap` đã giải quyết nhu cầu giới hạn tổng archive theo kỳ. Tài liệu Logback khuyến nghị không dùng SizeAndTimeBasedRollingPolicy nếu không thật sự cần giới hạn dung lượng **mỗi file**, do rollover và đổi tên file có chi phí. Chọn policy đơn giản đủ đáp ứng yêu cầu thay vì mặc định bật mọi cơ chế.

### Nén archive

File pattern kết thúc bằng `.gz` cho phép Logback nén archive. Nén giảm byte lưu trữ nhưng cần thêm CPU và I/O, có thể làm tăng thời gian rollover. Nén **không có nghĩa file active đang được ghi trực tiếp theo định dạng gzip**; thường file active vẫn là file text bình thường, còn archive được nén khi rollover.

Không chỉ dựa vào nén để giải quyết log volume quá lớn: kiểm soát log level, độ dài message, retention và lượng event từ nguồn phát thường quan trọng hơn.

## 7. Log4j2: RollingFile, TriggeringPolicy và RolloverStrategy

Trong **Apache Log4j 2**, cấu hình appender rolling có cách tổ chức khác Logback. Log4j2 thường dùng:

- `<RollingFile>` để định nghĩa appender và đường dẫn file.
- `fileName` cho file active; `filePattern` cho archive.
- `<Policies>` gồm một hoặc nhiều *triggering policies*, ví dụ `TimeBasedTriggeringPolicy`, `SizeBasedTriggeringPolicy`, `OnStartupTriggeringPolicy`.
- `<DefaultRolloverStrategy>` hoặc chiến lược khác để xử lý archive, index và thao tác dọn dẹp.

Ví dụ `log4j2.xml` **minh họa trong dự án có log4j-api và log4j-core tương thích**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="target/logs/app.log"
                     filePattern="target/logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="10MB"/>
            </Policies>

            <DefaultRolloverStrategy max="20"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đây là một cấu hình ví dụ độc lập về XML, **không phải tệp `logback.xml`**. Không trộn thẻ `<rollingPolicy>` của Logback vào `log4j2.xml`.

Giải thích:

1. Khi kỳ ngày đổi hoặc kích thước file đạt ngưỡng, một triggering policy có thể yêu cầu rollover.
2. `%d` đặt thành phần ngày và `%i` cho phép nhiều archive trong một kỳ; thiếu `%i` khi có size triggering cùng time triggering có thể dẫn đến xung đột tên archive.
3. `DefaultRolloverStrategy max="20"` liên quan đến **cửa sổ chỉ số file archive** theo chiến lược đang dùng; **không tự có nghĩa “giữ 20 ngày”**.
4. Nếu cần xóa archive cũ theo tuổi, tổng dung lượng hoặc tên file, cấu hình thêm *Delete action* với điều kiện rõ ràng phù hợp với chiến lược, thay vì coi `max` là retention theo ngày.

Một ví dụ **đoạn mở rộng** bên trong `DefaultRolloverStrategy` nhằm xóa archive .gz có tuổi trên 7 ngày:

~~~xml
<DefaultRolloverStrategy max="20">
    <Delete basePath="target/logs/archive">
        <IfFileName glob="app.*.log.gz"/>
        <IfLastModified age="P7D"/>
    </Delete>
</DefaultRolloverStrategy>
~~~

Đoạn này chỉ áp dụng cho file khớp các điều kiện trong thư mục chỉ định, và được thực thi theo cơ chế rollover/cleanup của strategy. **Không áp dụng quy tắc xóa rộng vào một thư mục dùng chung chứa file nghiệp vụ khác.** Trong cấu hình thực tế cần test điều kiện matching, biến thiên tên archive, quyền xóa, timezone và chu kỳ kích hoạt trước khi tin vào kết quả.

Có cách cấu hình Log4j2 không khai báo `fileName`, dùng `DirectWriteRolloverStrategy` để ghi trực tiếp theo tên archive; hành vi và việc xác định file active lúc đó khác với mô hình file active cố định ở ví dụ trên. Đừng suy luận một strategy áp dụng cho mọi RollingFile.

## 8. JUL FileHandler: cơ chế rotation tương đương nhưng API khác

JDK có sẵn `java.util.logging.FileHandler`. Nó hỗ trợ giới hạn kích thước và số file theo cấu hình, nhưng không dùng khái niệm `RollingFileAppender` của Logback.

Một ví dụ **chỉ sử dụng JDK 17** có thể chạy độc lập để hiểu sự khác biệt:

~~~java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class JulRotationDemo {
    private static final Logger LOG =
            Logger.getLogger(JulRotationDemo.class.getName());

    public static void main(String[] args) throws IOException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        // 1 MiB mỗi file, dùng tối đa 3 file trong bộ file rotation.
        try (FileHandler handler =
                new FileHandler("jul-demo-%g.log", 1_048_576, 3, true)) {
            handler.setLevel(Level.INFO);
            handler.setFormatter(new SimpleFormatter());
            LOG.addHandler(handler);

            for (int i = 0; i < 5; i++) {
                LOG.info("record=" + i);
            }
            handler.flush();
            LOG.removeHandler(handler);
        }

        System.out.println("emitted=5");
    }
}
~~~

**Lưu ý cú pháp:** đoạn mã trên minh họa ý tưởng dùng `FileHandler` trong một scope; `java.util.logging.FileHandler` kế thừa `Handler` có `close()` nhưng **không triển khai `AutoCloseable` trong tất cả phiên bản JDK**, vì vậy để giữ ví dụ tương thích chắc chắn, nên dùng cách `try/finally` thay vì dựa vào `try-with-resources`. Bản chạy độc lập thay thế, không phụ thuộc vào AutoCloseable, như sau:

~~~java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class JulRotationDemo {
    private static final Logger LOG =
            Logger.getLogger(JulRotationDemo.class.getName());

    public static void main(String[] args) throws IOException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler =
                new FileHandler("jul-demo-%g.log", 1_048_576, 3, true);
        try {
            handler.setLevel(Level.INFO);
            handler.setFormatter(new SimpleFormatter());
            LOG.addHandler(handler);

            for (int i = 0; i < 5; i++) {
                LOG.info("record=" + i);
            }
            handler.flush();
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.println("emitted=5");
    }
}
~~~

Lưu tên `JulRotationDemo.java` và chạy:

~~~bash
javac -encoding UTF-8 JulRotationDemo.java
java JulRotationDemo
~~~

**Stdout chính xác** của ví dụ này:

~~~text
emitted=5
~~~

Các dòng INFO được ghi vào file theo `SimpleFormatter`, không hiển thị trên stdout vì parent handlers đã bị tắt. Chỉ có năm bản ghi nhỏ nên có thể chưa đạt ngưỡng 1 MiB, và **không nhất thiết có rotation trong lần chạy này**. Muốn kiểm tra file theo generation `%g`, hãy dùng công cụ file explorer hoặc lệnh hệ điều hành để xem các file `jul-demo-0.log`, v.v. sau khi chạy trong một thư mục có quyền ghi.

Trong constructor `new FileHandler(pattern, limit, count, append)`:

- `pattern` là mẫu tên file, với `%g` là chỉ số generation.
- `limit` là ngưỡng dung lượng theo byte để bắt đầu rotation.
- `count` là số file của bộ rotation.
- `append` cho phép nối khi bắt đầu ghi theo khả năng và quy tắc của handler.

JUL rotation không có cú pháp `<maxHistory>` hay `<fileNamePattern>` tương đương trực tiếp với Logback. Đừng dán cấu hình Logback/Log4j2 vào hệ thống JUL.

## 9. Rolling appender và AsyncAppender: hai mục đích khác nhau

Rolling appender **quản lý file** và lịch lưu archive. Async appender/async logger **quản lý thời điểm và thread ghi** bằng cách đưa log event vào hàng đợi rồi chuyển tới appender đích.

Có thể kết hợp:

~~~text
Application thread -> AsyncAppender -> queue -> worker
                                              |
                                              v
                                     RollingFileAppender
                                              |
                                              v
                                  active file + archives
~~~

Việc kết hợp có thể làm giảm thời gian chờ I/O của request trong một số workload, nhưng không biến chi phí ghi/rotate/nén thành 0. Khi hàng đợi đầy, tùy framework và policy có thể block, bỏ log hoặc dùng đường xử lý khác; khi tiến trình bị kill trước khi flush, một số event có thể không tới file.

**Không gắn cả đường trực tiếp và đường async tới cùng một RollingFileAppender nếu không muốn ghi trùng.** Ví dụ root tham chiếu ROLLING và ASYNC, còn ASYNC cũng tham chiếu ROLLING, có thể làm cùng event được ghi hai lần.

Đối với log yêu cầu lưu giữ đáng tin, phải đánh giá độ bền end-to-end, shutdown, filesystem, crash và collector. RollingFileAppender trong một tiến trình không tự trở thành kho audit chống sửa đổi.

## 10. Ước lượng dung lượng và chọn chính sách

Tốc độ dữ liệu log phụ thuộc số event và byte đã encode:

~~~text
bytes/giây = event/giây × byte trung bình/event
bytes/ngày = bytes/giây × 86.400
~~~

Ví dụ dịch vụ tạo **200 event/s**, trung bình **500 byte/event**:

~~~text
200 × 500 = 100.000 byte/giây
100.000 × 86.400 = 8.640.000.000 byte/ngày
                  ≈ 8,64 GB/ngày (đơn vị thập phân)
~~~

Nếu file active được đặt ngưỡng khoảng 100 MB, dịch vụ có thể cần **nhiều lần rollover mỗi ngày**. Một chính sách chỉ xoay theo ngày có thể tạo ra một file gần 8,64 GB/ngày trước nén trong ví dụ lý tưởng này. Lúc đó cân nhắc `SizeAndTimeBasedRollingPolicy`, giảm log volume, thay đường thu thập hoặc phân bổ dung lượng phù hợp.

Các con số trên **không phải dự đoán chính xác dung lượng thực tế**, vì còn metadata, nén, biến động kích thước message, indexing, bản sao, output từ thư viện và các file khác. Mốc `maxFileSize` chỉ định điều kiện trigger, không thay việc đo dung lượng volume.

### Chọn retention theo yêu cầu

- Log INFO thông thường có thể có retention ngắn hơn log về lỗi nghiêm trọng hoặc sự kiện đối soát, nhưng chính sách cần do hệ thống quyết định.
- Nếu cần giữ nhiều tuần/tháng, cân nhắc archive/compression hoặc chuyển log vào storage thích hợp; đừng tin vào disk nhỏ của container/pod.
- Phân biệt **archive local phục vụ debug** với **backup hoặc lưu trữ đáp ứng compliance**.
- Theo dõi dung lượng volume, số file active/archive, tốc độ rollover, lỗi nén/xóa và lag của log collector.

## 11. Tình huống vận hành và những rủi ro thường gặp

### 11.1. Nhiều JVM ghi chung một file

Hai process cùng dùng `logs/app.log` có thể tranh chấp file, đánh giá kích thước sai, gặp xung đột đổi tên và làm archive bị thiếu/trùng. **Đừng mặc định rolling appender an toàn cho nhiều tiến trình trên cùng file**.

Logback có chế độ `prudent` cho một số trường hợp nhiều JVM ghi cùng file, nhưng chế độ này có ràng buộc: với TimeBasedRollingPolicy, không thể dùng đồng thời compression, và thuộc tính `<file>` phải để trống trong cấu hình prudent được hỗ trợ. Việc dùng prudent còn có thể giảm hiệu năng do đồng bộ file. Với nhiều instance/container, **mỗi instance ghi file riêng hoặc dùng console + collector** thường đơn giản hơn.

Log4j2 cũng có lưu ý rằng size-based rollover có thể tính sai nếu nhiều manager ghi chung file. Cần thiết kế file ownership rõ ràng và thử nghiệm trên filesystem thực tế.

### 11.2. Rollover và công cụ logrotate bên ngoài

Nếu Logback/Log4j2 tự đổi tên và nén file còn một công cụ khác đồng thời rotate/truncate cùng file, quá trình có thể mất dữ liệu hoặc tiếp tục ghi vào file descriptor cũ. Chọn **một bên chịu trách nhiệm chính** cho rotation, trừ khi có cơ chế tương tác được thiết kế và kiểm thử.

Nếu agent tail file, phải xác minh agent xử lý **rename, truncate, file inode, restart và archive compression** ra sao. Không chỉ nhìn thấy archive mới mà kết luận mọi dòng log đã được collector nhận.

### 11.3. Disk đầy hoặc không có quyền ghi

Lỗi tạo thư mục, file active, archive, nén hoặc xóa có thể khiến appender không khởi tạo hoặc ngừng ghi đúng. Kiểm tra status messages của backend lúc startup, quyền file/directory, free space, quota, filesystem mount, inode và quyền của container.

Ứng dụng có thể vẫn chạy business logic dù logging backend bị lỗi. Vì thế cần cảnh báo vận hành độc lập về file/collector và không xem “không có log ERROR” là bằng chứng không có lỗi.

### 11.4. File active lớn hơn trần archive

`totalSizeCap` ở Logback giới hạn tổng archive chịu quản lý, không tự hạn chế `app.log`. Nếu traffic tăng nhanh và ứng dụng chưa chạm thời điểm/điều kiện rollover, file active vẫn có thể lớn. Cần quan sát **dung lượng thực tế của cả thư mục**, đặt file size policy khi có yêu cầu giới hạn từng file và cấu hình cảnh báo volume.

### 11.5. Nén archive tốn CPU và có thể chậm

Compression giúp tiết kiệm dung lượng nhưng cần CPU và thao tác file. Nhiều archive lớn cùng được nén hoặc upload có thể tạo tải đột biến, đặc biệt trên volume chậm. Theo dõi CPU, disk IO, p95/p99 latency và độ trễ của collector vào thời điểm rollover, không chỉ đo logging khi file chưa xoay.

### 11.6. Additivity và ghi trùng

Khi logger con và root cùng tham chiếu đến rolling appender với additivity mặc định, một event có thể đi vào appender hai lần. Nếu không chủ đích, rà soát điểm gắn `appender-ref` hoặc cấu hình `additivity="false"` ở logger phù hợp (và bảo đảm logger con vẫn có appender cần thiết).

Đây là vấn đề **định tuyến log**, không phải do rollover tự tạo thêm message.

### 11.7. Bảo mật và dữ liệu nhạy cảm

File active, archive và backup đều có thể chứa password, API token, cookie, dữ liệu thanh toán hoặc thông tin cá nhân nếu mã phát log không kiểm soát. Compression **không phải mã hóa**. Chọn các trường an toàn ngay tại nguồn, giới hạn quyền đọc, retention, mã hóa khi lưu/truyền nếu chính sách yêu cầu, và xử lý input chứa newline/ký tự điều khiển để hạn chế log forging.

Khi xóa archive, cần hiểu đây không tự đảm bảo mọi bản sao trên collector/backup cũng bị xóa. Chính sách bảo vệ dữ liệu phải bao phủ toàn pipeline.

## 12. Quy trình kiểm tra rolling appender trong dự án thật

1. **Kiểm tra backend thực tế:** mã đang dùng JUL, SLF4J+Logback hay Log4j2? Đúng file cấu hình `logback.xml`/`log4j2.xml` có được nạp không?
2. **Xác định file active:** resolved path, working directory, quyền ghi và owner của file.
3. **Xem điều kiện rollover:** time pattern có đúng đơn vị? Size policy có mốc phù hợp? Có cần event sau ranh giới để kích hoạt không?
4. **Xem tên archive:** pattern `%d`, `%i`, hậu tố nén, thư mục archive; thử nhiều lần rollover để phát hiện overwrite.
5. **Xem retention:** `maxHistory`/`totalSizeCap` hoặc strategy/Delete action có đúng phạm vi? Có khả năng xóa nhầm file ngoài ý muốn không?
6. **Đo dung lượng và tài nguyên:** bytes/s, disk free, số archive, CPU/nén, GC, p95/p99 latency và lag collector.
7. **Thử restart:** file active được append hay truncate? Archive còn đúng không? Tài nguyên có được flush/close ở shutdown không?
8. **Thử dưới tải:** tạo volume đủ để vượt size threshold, xem archive theo từng index, không chỉ kiểm tra ngày tháng.
9. **Thử lỗi filesystem:** disk đầy, permission denied, xóa archive không được; xem status logging, alert và hành vi ứng dụng.
10. **Thử nhiều instance/collector:** bảo đảm không ghi chung một file ngoài ý muốn và agent không bỏ event khi file được rename/nén.

Trong môi trường test, có thể hạ ngưỡng `maxFileSize` xuống kích thước nhỏ hợp lý và tạo log an toàn để rollover xuất hiện nhanh. **Không dùng thủ thuật phát log quá lớn trên production**, vì bản thân phép thử có thể làm đầy volume hoặc gây tải lớn cho collector.

## 13. So sánh Logback, Log4j2 và JUL

| Chủ đề | Logback | Log4j2 | JUL |
| --- | --- | --- | --- |
| Thành phần file rotation | `RollingFileAppender` | `RollingFile` / plugin liên quan | `FileHandler` |
| Cấu hình thời gian | `TimeBasedRollingPolicy` | `TimeBasedTriggeringPolicy` | Không có time-based rolling policy tương đương trực tiếp trong FileHandler |
| Cấu hình kích thước | `SizeAndTimeBasedRollingPolicy` khi kết hợp ngày + size | `SizeBasedTriggeringPolicy` kết hợp `Policies` | `limit` theo byte, `count` số file |
| Tên archive | `fileNamePattern` có `%d`/`%i` | `filePattern` có `%d`/`%i` | `pattern` với `%g` |
| Retention | `maxHistory` và `totalSizeCap` | RolloverStrategy, giới hạn chỉ số và Delete action | Quay vòng trong bộ file `count` |
| Nén | Dựa trên hậu tố archive, tùy policy | Dựa trên hậu tố archive, tùy strategy | Không có khả năng nén tương đương được tích hợp như hai framework |
| Cấu hình | `logback.xml` | `log4j2.xml` | `logging.properties` hoặc API handler |

Không hoán đổi nguyên xi những đoạn XML giữa Logback và Log4j2. Với JUL, log file rotation dùng cấu hình/constructor handler; không gọi phương thức SLF4J hoặc đặt plugin của Log4j2.

## 14. Những hiểu nhầm và lỗi phổ biến

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “Rolling nghĩa là tự xóa log cũ sau đúng 24 giờ” | Archive có thể vẫn tồn tại lâu hoặc dọn khi rollover | Cấu hình retention, kiểm tra thời điểm cleanup |
| “maxHistory=7 nghĩa là luôn có tối đa 7 file” | Một ngày có thể có nhiều file `%i` | Hiểu số kỳ thời gian và chính sách archive |
| “totalSizeCap giới hạn cả file active” | Volume vẫn đầy nếu active file quá lớn | Đo active + archive, dùng size trigger nếu cần |
| Chỉ dùng FileAppender trong ứng dụng chạy lâu | Một file không ngừng tăng | Dùng RollingFileAppender hoặc external collector |
| Thêm maxFileSize vào policy sai | Không xoay theo size như dự kiến | Dùng SizeAndTimeBasedRollingPolicy phù hợp |
| Thiếu `%i` khi kết hợp ngày và size | Có thể trùng tên archive trong cùng ngày | Dùng cả `%d` và `%i` |
| Coi `DefaultRolloverStrategy max` là số ngày retention | Không xóa đúng các file quá tuổi | Đặt Delete action/age nếu cần |
| Nén archive là mã hóa | Thông tin nhạy cảm vẫn đọc được | Bảo vệ dữ liệu và quyền truy cập riêng |
| Hai JVM ghi chung active file | Xung đột file/rollover | Mỗi instance một file hoặc collector chung |
| Dùng logrotate bên ngoài không phối hợp | Có thể mất/trùng log | Chọn một cơ chế rotate và test |
| Quên `appender-ref` | Logger không gửi event vào appender | Gắn đúng tên appender ở logger/root |
| Dùng cả direct và async tới một rolling appender | Một event ghi hai lần | Giữ một đường routing đúng chủ đích |
| Expect rollover trong demo có vài dòng | Chưa đạt trigger nên không có archive | Test điều kiện trigger thực tế |
| Chỉ kiểm tra app.log mà không xem archive | Tưởng log cũ đã mất | Kiểm tra directory, pattern và policy |
| Không giám sát đĩa/quota | Logger ngừng ghi nhưng ứng dụng có thể vẫn chạy | Quan sát trạng thái backend, disk, collector |

## 15. Bài tập thực hành

1. **Định nghĩa:** giải thích sự khác biệt giữa active file, archive, rollover và retention. Tại sao không được coi nén gzip là bảo vệ bí mật?
2. **Chạy Logback:** tạo ba tệp của ví dụ Maven ở mục 5 trên JDK 17. Dự đoán ba dòng stdout, nội dung file active trong lần chạy đầu và lý do chưa có archive ngay.
3. **Giữ file theo ngày:** đổi `fileNamePattern` thành mẫu theo giờ, ví dụ `%d{yyyy-MM-dd_HH}`. `maxHistory=7` bây giờ có ý nghĩa gì so với pattern theo ngày?
4. **Theo size:** dùng `SizeAndTimeBasedRollingPolicy` với `%d` và `%i`, ngưỡng nhỏ trong môi trường test. Quan sát tên archive thứ nhất/thứ hai cùng kỳ, rồi giải thích vì sao một kỳ không tương ứng đúng một file.
5. **Log4j2:** từ ví dụ `RollingFile`, thêm điều kiện `OnStartupTriggeringPolicy` vào `<Policies>` nếu cần. Giải thích tại sao `DefaultRolloverStrategy max="20"` không phải “giữ 20 ngày”.
6. **JUL:** chạy `JulRotationDemo.java`, tìm file `jul-demo-0.log` và giải thích vai trò `limit`, `count`, `%g`. Đổi limit nhỏ để quan sát generation.
7. **Tính dung lượng:** dịch vụ tạo 400 event/s, trung bình 250 byte/event. Tính GB/ngày trước nén và so sánh nguy cơ khi chỉ xoay theo ngày với khi có size threshold 100 MB.
8. **Sự cố:** file active có log nhưng archive không xuất hiện sau khi thay cấu hình. Nêu thứ tự kiểm tra trigger, pattern, quyền thư mục, appender-ref, startup status và event sau ranh giới thời gian.
9. **An toàn đa tiến trình:** hai JVM ghi cùng một file và cùng rotate. Nêu hai giải pháp thiết kế tránh xung đột; tại sao prudent mode không được xem là thay thế mọi cơ chế collector?
10. **Vận hành:** đề xuất các chỉ số/alert tối thiểu về dung lượng volume, số archive, lỗi nén/xóa, lag collector và độ trễ request trong giai đoạn rollover.

## 16. Nguồn tra cứu chính thức

- Logback Manual — Appenders, RollingFileAppender và Rolling Policies: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 — Rolling File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Java SE — `java.util.logging.FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

**Ghi nhớ:** rolling appender không chỉ đổi tên file. Nó quản lý **chu kỳ file active, điều kiện rollover, tên archive và retention**, đồng thời cần xét compression, hiệu năng, bảo mật và thu thập log. Trong Logback, phối hợp RollingFileAppender với đúng rolling policy; trong Log4j2, phối hợp RollingFile với triggering policy và rollover strategy; với JUL, dùng FileHandler theo cơ chế riêng.