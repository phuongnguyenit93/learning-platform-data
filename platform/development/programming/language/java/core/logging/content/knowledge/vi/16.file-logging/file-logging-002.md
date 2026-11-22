# Đường dẫn log trong Java File Logging

## Mục tiêu

**Đường dẫn log** là vị trí mà một file handler hoặc file appender dùng để tạo và ghi tệp log. Trong Java, cấu hình đúng đường dẫn là điều kiện quan trọng để ứng dụng ghi log ổn định khi chạy từ IDE, terminal, Windows Service, Linux server, Docker hoặc CI. Một đường dẫn hợp lệ trên máy lập trình viên có thể hoàn toàn sai khi deploy.

Bài thuộc nhóm **File logging** của **Java Core Logging**, tập trung vào **đường dẫn log**: cách hình thành, cấu hình, xử lý bằng Java 17, lỗi thường gặp và các yếu tố bảo mật/vận hành. Sau bài học, bạn sẽ:

- Phân biệt **relative path** và **absolute path**; xác định vai trò của **working directory**.
- Dùng **Path**, **Files** và **FileHandler** để tạo directory, ghi file, đóng handler và xác nhận nơi lưu.
- Phân biệt đường dẫn **file đang ghi** với pattern **rotation/archive**, cũng như pattern tên file với pattern nội dung log.
- Cấu hình path với JUL, Logback và nhận diện đặc điểm tương ứng trong Log4j 2.
- Tìm nguyên nhân file xuất hiện sai thư mục, không được tạo, không có quyền ghi, bị ghi đè hoặc mất sau redeploy.
- Nhận biết path traversal, symlink, quyền truy cập, retention và các giới hạn khi dùng logging file trong container.

## 1. Đường dẫn log là gì?

Ví dụ:

~~~text
my-service/
└── logs/
    └── application.log
~~~

**logs** là thư mục chứa; **application.log** là tên tệp; **logs/application.log** là đường dẫn file. Nội dung file có thể là:

~~~text
INFO event=request.completed requestId=req-12 status=200
~~~

Đây là ví dụ text đơn giản. Một **logging event** có thể chứa level, logger, timestamp, message, Throwable và metadata. **Đường dẫn không phải thuộc tính bắt buộc của message**: Logger phát sự kiện, còn **Handler/Appender** quyết định nơi xuất. Một hệ thống có thể đồng thời xuất log ra console và file.

~~~mermaid
flowchart LR
    A["Java Logger"] --> B["Level / Filter"]
    B --> C["FileHandler hoặc FileAppender"]
    C --> D["Filesystem path"]
    D --> E["Tệp log"]
~~~

Nếu không cấu hình file handler/appender, lời gọi **logger.info(...)** không tự tạo file chỉ vì logger có tên. Nếu một record bị level/filter loại, việc đã cấu hình file đúng cũng không bảo đảm có dòng log nào được ghi.

**Một đường dẫn tốt** phải giải thích được: nó nằm ở máy/container nào, là absolute hay relative, process có quyền mở file không, file có được giữ qua restart không, và collector có đọc được không.

## 2. Relative path và absolute path

**Relative path** là đường dẫn được hiểu dựa trên một thư mục nền, thường là working directory của tiến trình Java:

~~~text
logs/app.log
target/logs/app.log
../logs/app.log
~~~

**Absolute path** xác định vị trí từ gốc filesystem hoặc volume:

~~~text
/var/log/myapp/app.log
/srv/myapp/logs/app.log
C:\apps\myapp\logs\app.log
D:\service-logs\app.log
~~~

Các ví dụ trên thuộc các hệ điều hành khác nhau; không thể coi tất cả đều tồn tại hoặc có cùng cách biểu diễn trên một máy.

| Thuộc tính | Relative | Absolute |
| --- | --- | --- |
| Ví dụ | logs/app.log | /var/log/myapp/app.log |
| Phụ thuộc working directory | Có | Không theo cách của relative path |
| Dễ dùng trong project local | Thường có | Cần cấu hình theo máy |
| Có thể ghi sai chỗ khi đổi cách chạy | Dễ gặp | Ít hơn, nhưng vẫn có thể sai mount/volume |
| Portable giữa Windows/Linux | Có thể nếu dùng Path đúng | Thường phụ thuộc môi trường |
| Phù hợp deploy lâu dài | Cần kiểm soát working directory | Cần phân quyền và mount đúng |

Nếu ứng dụng chạy từ **/srv/myapp**, relative path **logs/app.log** thường dẫn đến **/srv/myapp/logs/app.log**. Nếu một task runner lại chạy từ **/opt/runner**, cùng chuỗi trên có thể dẫn đến **/opt/runner/logs/app.log**. **Đường dẫn tương đối không mặc định tương đối với thư mục chứa JAR hoặc source file.**

Đường dẫn absolute rõ ràng hơn nhưng không tự giải quyết quyền truy cập. Ví dụ process chạy bằng user không có quyền ghi vào /var/log/myapp sẽ thất bại dù path hoàn toàn hợp lệ.

## 3. Working directory: vì sao IDE chạy được, server lại lỗi?

Khi gọi Java:

~~~java
// Minh họa, đặt trong một method Java.
java.nio.file.Path file =
        java.nio.file.Path.of("logs", "app.log");
System.out.println(file.toAbsolutePath().normalize());
~~~

Kết quả phụ thuộc **working directory của tiến trình JVM đang chạy**. Có thể kiểm tra bằng:

~~~java
// Minh họa.
System.out.println(System.getProperty("user.dir"));
System.out.println(java.nio.file.Path.of("")
        .toAbsolutePath().normalize());
~~~

Hai giá trị thường giúp chẩn đoán nơi JVM đang được khởi động. **user.dir** thường phản ánh thư mục làm việc lúc JVM khởi động. Đừng dùng **System.setProperty("user.dir", "...")** như một giải pháp đáng tin để thay đổi working directory giữa chừng: cách các thư viện/filesystem sử dụng property và current directory có thể khác nhau.

Những yếu tố có thể quyết định working directory:

1. Thư mục terminal khi chạy lệnh **java**.
2. Cài đặt **Working directory** trong IDE hoặc test runner.
3. WorkingDirectory của Linux systemd hoặc của Windows service wrapper.
4. **WORKDIR** trong Dockerfile hoặc workingDir của container.
5. Thư mục agent của CI job, Maven/Gradle task hoặc script khởi động.
6. Một process manager hoặc launcher tạo JVM con với working directory riêng.

**Cách sửa hợp lý** là xác định vị trí thực tế rồi cấu hình path rõ ràng, hoặc cố định working directory ở nơi triển khai. Không dựa vào giả định file sẽ nằm cạnh JAR.

## 4. Dùng java.nio.file.Path thay vì nối chuỗi

Trong Java 17, **Path** và **Files** cung cấp API để quản lý đường dẫn theo filesystem:

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| **Path.of("logs", "app.log")** | Biểu diễn đường dẫn | Không tự tạo file |
| **path.isAbsolute()** | Xác định có phải absolute không | Tùy filesystem |
| **path.toAbsolutePath()** | Chuyển sang biểu diễn absolute | File chưa tồn tại vẫn được |
| **path.normalize()** | Rút gọn các phần **.** và **..** ở mức cú pháp | Không kiểm tra symlink hoặc quyền |
| **path.resolve("app.log")** | Ghép tên file vào thư mục | Nếu phần được resolve là absolute, có thể thay base |
| **path.getParent()** | Lấy đường dẫn thư mục cha | Có thể trả null |
| **Files.createDirectories(dir)** | Tạo directory cùng các thư mục cha cần thiết | Có thể ném IOException |
| **Files.exists(path)** | Thử kiểm tra tồn tại | Không chứng minh có quyền ghi |
| **Files.isWritable(path)** | Thử kiểm tra quyền ghi | Có thể sai sau đó do race |
| **path.toRealPath()** | Lấy đường dẫn thực của đối tượng đã tồn tại | Có thể theo symlink tùy options |

Ví dụ:

~~~java
// Minh họa, dùng trong method có khai báo throws IOException.
java.nio.file.Path logDirectory =
        java.nio.file.Path.of("target", "logs")
                .toAbsolutePath().normalize();
java.nio.file.Files.createDirectories(logDirectory);
java.nio.file.Path logFile = logDirectory.resolve("app.log");
~~~

**Path.of** chỉ tạo đối tượng Path. **Files.createDirectories** tạo directory, nhưng không tạo chính file app.log. **FileHandler/FileAppender** hoặc một API file output mới là thành phần mở hoặc tạo file khi ghi.

Với path cố định do code quyết định, cách dùng **resolve** phù hợp hơn ghép chuỗi **"target/" + name** vì dấu phân cách và quy tắc đường dẫn thuộc filesystem. Nếu path do user cung cấp, cần kiểm tra thêm vấn đề bảo mật ở mục 12.

## 5. Quyền ghi và thư mục cha

Đường dẫn có thể đúng cú pháp mà vẫn không ghi được khi:

- Thư mục cha không tồn tại và backend không tự tạo.
- Process không có quyền tạo directory/file.
- Mount là **read-only**, disk đầy, quota hết hoặc file descriptor bị giới hạn.
- Một thành phần path trỏ tới symlink hoặc file thay vì directory.
- Một process khác đang lock hoặc dùng cùng file.
- File bị thay đổi/xóa giữa lúc kiểm tra và mở.
- Filesystem/network share không khả dụng.
- Container chỉ mount một thư mục khác với path trong config.

**Tạo directory trước** là một giải pháp phù hợp khi ứng dụng sở hữu thư mục đó:

~~~java
// Minh họa.
java.nio.file.Path dir =
        java.nio.file.Path.of("target", "logs")
                .toAbsolutePath().normalize();
java.nio.file.Files.createDirectories(dir);
~~~

Tuy nhiên, trên máy production, thư mục như **/var/log/myapp** có thể phải được tạo bởi deploy/system administrator với ownership phù hợp. Không chạy ứng dụng dưới quyền root chỉ để làm cho log path ghi được.

**Files.isWritable** không bảo đảm thao tác mở file sau đó thành công, vì quyền và filesystem có thể thay đổi. Hãy xử lý IOException/đường báo lỗi của logging backend khi mở/ghi thật.

**Quyền đọc cũng quan trọng:** file log có thể chứa thông tin nghiệp vụ. Cấp quyền tối thiểu, không đưa token/password vào message hoặc tên file.

## 6. Ví dụ Java 17: tạo đúng đường dẫn, ghi log, đọc lại

Ví dụ độc lập này sử dụng **java.util.logging.FileHandler** của JDK, không cần Maven dependency. Chương trình:
1. Nhận thư mục log qua property **app.log.dir**, mặc định **target/logs**.
2. Tính absolute path và tạo directory.
3. Ghép file name **app.log**.
4. Ghi hai sự kiện, đóng Handler.
5. Đọc lại file UTF-8 và in kết quả ra stdout.

Tạo tệp **LogPathDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogPathDemo {
    private static final Logger LOG =
            Logger.getLogger(LogPathDemo.class.getName());

    public static void main(String[] args) throws Exception {
        String setting = System.getProperty("app.log.dir", "target/logs");
        Path logDirectory = Path.of(setting).toAbsolutePath().normalize();
        Files.createDirectories(logDirectory);
        Path logFile = logDirectory.resolve("app.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(logFile.toString(), false);
        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.info("event=job.started id=job-7");
            LOG.info("event=job.completed id=job-7 status=ok");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        List<String> lines =
                Files.readAllLines(logFile, StandardCharsets.UTF_8);
        System.out.println("logDirAbsolute=" + logDirectory.isAbsolute());
        System.out.println("fileInConfiguredDir="
                + logFile.getParent().equals(logDirectory));
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
~~~

### Chạy lần A: dùng thư mục mặc định

Tại thư mục chứa LogPathDemo.java:

~~~bash
javac LogPathDemo.java
java LogPathDemo
~~~

**Stdout chính xác khi file ghi thành công:**

~~~text
logDirAbsolute=true
fileInConfiguredDir=true
recordCount=2
INFO | event=job.started id=job-7
INFO | event=job.completed id=job-7 status=ok
~~~

Tệp được tạo ở **target/logs/app.log** tính từ working directory đang chạy, không phải mặc định ở nơi chứa thư viện Java. Output không in absolute path cụ thể để kết quả giống nhau trên Windows/Linux. **Console output của chương trình** ở đây là kết quả đọc file sau khi handler đã đóng; những lời gọi LOG.info ban đầu ghi vào file.

### Chạy lần B: thay đổi thư mục log

~~~bash
java -Dapp.log.dir=target/custom-logs LogPathDemo
~~~

**Stdout vẫn giống lần A**, nhưng file được ghi ở **target/custom-logs/app.log**. Tham số **-Dapp.log.dir=...** là system property tự định nghĩa của ví dụ, **không phải cấu hình đặc biệt mặc định của JUL**.

Trên Windows/PowerShell, nếu đường dẫn có khoảng trắng, đặt toàn bộ tham số trong nháy:

~~~powershell
java "-Dapp.log.dir=C:\Work Logs\MyApp" LogPathDemo
~~~

Một ví dụ đường dẫn tuyệt đối trên Linux:

~~~bash
java -Dapp.log.dir=/var/log/myapp LogPathDemo
~~~

Lệnh cuối chỉ thành công nếu ứng dụng có quyền tạo/ghi directory. Không hardcode đường dẫn này cho mọi môi trường.

### Giải thích

- **Path.of(setting).toAbsolutePath().normalize()** giải quyết đường dẫn và rút gọn cú pháp; không xử lý mọi rủi ro symlink.
- **Files.createDirectories** tạo các directory còn thiếu nếu được phép.
- **logDirectory.resolve("app.log")** tách cấu hình thư mục khỏi tên file.
- **FileHandler(..., false)** mở file với append=false để mỗi lần chạy không trộn log cũ. Với production cần lưu log, chọn append/rotation có chủ đích.
- **setEncoding("UTF-8")** và Formatter riêng giúp nội dung và output kiểm chứng rõ ràng; FileHandler mặc định thường dùng XMLFormatter nếu không cấu hình.
- **setUseParentHandlers(false)** tránh cùng record được gửi lên handler của logger cha; đã gắn FileHandler trực tiếp.
- **finally** đóng handler trước khi đọc file; giúp giải phóng stream và file lock trong phạm vi Handler.
- **recordCount=2** chỉ là kết quả của demo, không phải cam kết về log delivery/durability trong hệ thống phân tán.

Chương trình trên đã được biên dịch và chạy thử bằng JDK, với cả đường dẫn mặc định lẫn tùy chỉnh; cả hai trường hợp tạo file và đọc lại đúng hai record.

## 7. FileHandler của JUL: các ký hiệu trong pattern tên file

**FileHandler** của **java.util.logging** hỗ trợ pattern để tạo tên file và rotation. Các ký hiệu này **chỉ dùng cho tên file**, không phải formatter của nội dung record.

| Token | Ý nghĩa trong FileHandler pattern |
| --- | --- |
| **%h** | Home directory của user chạy JVM |
| **%t** | Thư mục tạm của hệ thống |
| **%g** | Số generation của file trong rotation |
| **%u** | Số unique để giải quyết xung đột tên file khi cần |
| **%%** | Ký tự **%** literal |

Ví dụ:

~~~java
// Minh họa; cần tạo sẵn directory con myapp với quyền phù hợp.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "%h/myapp/log-%u-%g.log",
                1024 * 1024,
                5,
                true);
~~~

Giải thích: giới hạn theo đơn vị byte mỗi file trong cơ chế rotation, **5 generation**, chế độ append=true, tên file dựa trên home directory và các token. File thực tế có thể có suffix theo generation/unique và trạng thái file lock; đừng dự đoán cứng đúng một file name.

**%h không phải token của Path.of thông thường.** Nó được FileHandler xử lý bên trong **pattern string**. Trong một biểu thức **Path.of("%h", "app.log")**, Java NIO không tự chuyển %h thành home directory.

Nếu sử dụng pattern chứa thư mục **%h/myapp**, phải bảo đảm thư mục myapp tồn tại và có quyền ghi. **Không giả định FileHandler luôn tạo tự động mọi directory cha.**

FileHandler có thể sử dụng lock file để điều phối quyền sở hữu file. Token **%u** không thay được chính sách quản lý nhiều tiến trình ghi chung một file; khi nhiều instance cùng ghi/rotate, nên xem lại kiến trúc để tránh xung đột.

## 8. Cấu hình JUL bằng logging.properties

Một ví dụ file **logging.properties** cho một ứng dụng khác dùng JUL và có directory myapp trong home user:

~~~properties
.level = INFO
handlers = java.util.logging.FileHandler

java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.pattern = %h/myapp/app-%u.%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

Khởi chạy ứng dụng đã biên dịch với lớp chính com.example.Main:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Đây là **lệnh minh họa cho một ứng dụng đã được cấu hình JUL**; không phải lệnh chạy LogPathDemo ở mục 6, vì demo tự tạo FileHandler từ code. **java.util.logging.config.file** chỉ tới file cấu hình JUL; bản thân đường dẫn logging.properties cũng có thể là relative và chịu ảnh hưởng working directory.

Trong properties:
- **FileHandler.pattern** chọn tên file.
- **limit/count** quy định rotation cơ bản.
- **append** quy định hành vi ghi nối khi mở file.
- **formatter** quy định nội dung log, không quyết định đường dẫn.
- **handlers** gắn file handler theo cấu hình root.

Các mức log và filter vẫn có thể loại sự kiện trước khi tới file. Đừng kết luận path sai chỉ vì không thấy dòng DEBUG/FINE, đặc biệt khi root hoặc FileHandler chỉ cho INFO trở lên.

## 9. Đường dẫn log trong Logback

Với **SLF4J + Logback**, log path thường nằm trong **logback.xml** và được quản lý bởi **FileAppender** hoặc **RollingFileAppender**, không phải JUL FileHandler.

Ví dụ file **src/main/resources/logback.xml**:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

**file** là đường dẫn file active. **logs/application.log** là relative path, thường được hiểu từ working directory của JVM. **PatternLayoutEncoder** quyết định cách trình bày message; pattern nội dung với **%d/%level/%msg** khác với pattern đặt tên file.

### Đổi thư mục theo môi trường

Logback cho phép substitution thuộc tính. Ví dụ cấu hình độc lập:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>${LOG_DIR:-logs}/application.log</file>
    <append>true</append>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%level | %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO"><appender-ref ref="FILE"/></root>
</configuration>
~~~

Cú pháp **${LOG_DIR:-logs}** dùng LOG_DIR nếu cấu hình cung cấp giá trị, hoặc **logs** làm fallback theo cơ chế property của Logback. Nguồn thuộc tính có thể là system property, environment variable hoặc scope cấu hình tương ứng. Với LOG_DIR tương đối, file vẫn phụ thuộc working directory; với LOG_DIR absolute, process vẫn cần quyền ghi và mount tồn tại.

**Không sao chép cú pháp substitution của Logback sang JUL properties hoặc Log4j 2 rồi cho rằng giống nhau.** Mỗi backend có cơ chế riêng.

### File active khác tên file đã rotate

RollingFileAppender thường có hai mục đích đường dẫn:

~~~xml
<appender name="ROLLING" class="ch.qos.logback.core.rolling.RollingFileAppender">
  <file>logs/application.log</file>
  <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.log</fileNamePattern>
    <maxHistory>7</maxHistory>
  </rollingPolicy>
  <encoder>
    <pattern>%level %msg%n</pattern>
  </encoder>
</appender>
~~~

Đây là **fragment** phải đặt trong configuration có logger/root appender-ref phù hợp. **file** chỉ file đang ghi, còn **fileNamePattern** quyết định tên archive theo rotation. **%d** trong fileNamePattern là token ngày của rolling policy; **%d** trong encoder pattern lại là timestamp của từng log record. Nếu đổi log directory, kiểm tra **cả file active và vị trí archive**.

## 10. Đường dẫn khi dùng Log4j 2 hoặc framework

**Log4j 2** cũng có FileAppender/RollingFileAppender nhưng dùng cấu hình khác Logback. Các tên thuộc tính hay gặp là **fileName** cho file active và **filePattern** cho archive ở RollingFile appender. Đừng đổi thư viện logging mà giữ nguyên mọi file XML cũ và kỳ vọng nơi ghi giống hệt.

Với **Spring Boot** hoặc framework khác, còn có property logging do framework hỗ trợ. Cần kiểm tra version, profile, config priority và backend thực sự đang được dùng. Một SLF4J facade không tự chọn nơi ghi; provider/backend và các file cấu hình cuối cùng quyết định.

Khi ứng dụng có nhiều cấu hình cùng tồn tại, hãy xác minh **cấu hình có hiệu lực trong JVM thật** trước khi sửa path. Ví dụ file logback.xml trong source chưa chắc được đóng gói lên classpath nếu build không đưa resources vào JAR.

## 11. Append, rotation và retention

Chọn đúng đường dẫn không đủ nếu file cứ tăng không giới hạn hoặc bị ghi đè mỗi lần khởi động.

| Lựa chọn | Tác dụng | Rủi ro/giới hạn |
| --- | --- | --- |
| **append=true** | Ghi thêm vào file hiện có | File tăng theo thời gian, cần retention |
| **append=false** | Mở lại theo chế độ không nối log cũ | Dễ ghi đè log cần giữ |
| Rotation theo kích thước | Giữ file active trong ngưỡng có kế hoạch | Phải kiểm soát số archive và tổng dung lượng |
| Rotation theo ngày | Chia archive theo thời gian | Phải làm rõ timezone, lịch dọn |
| File trên volume bền | Có thể giữ qua restart theo cấu hình storage | Vẫn cần backup/retention/permission |
| File trên filesystem tạm | Phù hợp bài test hoặc cache ngắn hạn | Có thể mất sau job/redeploy |

Nhiều tiến trình cùng dùng **logs/app.log** có thể dẫn tới lock, nội dung xen kẽ hoặc rotation xung đột. Không mặc định mọi backend đều ghi đồng thời an toàn trên mọi filesystem. Thường nên tách file theo instance hoặc dùng collector chung qua stdout/stderr.

Bên cạnh tên file, cần có **quy định ai được đọc log, lưu bao lâu và xóa theo chính sách nào**. Đường dẫn nằm trên volume bền nhưng không có rotation cũng có thể gây hết disk và làm service ngừng hoạt động.

## 12. Bảo mật: path traversal và symlink

Không để input từ request quyết định tùy ý tên file hoặc thư mục cho process ghi với quyền cao. Các chuỗi chứa **..**, absolute path, symlink hoặc token đặc biệt có thể thay đổi đích.

Một kiểm tra **cú pháp** cho file name nằm trong directory được chỉ định:

~~~java
// Đoạn minh họa: root do ứng dụng quản lý, userFileName là String.
java.nio.file.Path root =
        java.nio.file.Path.of("target", "trusted-logs")
                .toAbsolutePath().normalize();
java.nio.file.Path file =
        root.resolve(userFileName).normalize();

if (!file.startsWith(root) || file.equals(root)) {
    throw new IllegalArgumentException("Path outside log directory");
}
~~~

**Quan trọng:** Đây **chưa phải biện pháp bảo mật hoàn chỉnh**. normalize và startsWith ở mức Path không ngăn symlink bên trong root trỏ ra ngoài, cũng không ngăn một directory bị tráo giữa lúc kiểm tra và mở (TOCTOU). Với tình huống không tin cậy, cần allowlist tên file đơn giản, không theo symlink không tin cậy, thao tác an toàn với filesystem/permission và chính sách nghiệp vụ thích hợp.

Các rủi ro bổ sung:
- FileHandler có cú pháp pattern chứa **%**; không nên đưa raw input không tin cậy trực tiếp vào pattern.
- Tên file dài bất thường hoặc số lượng file lớn có thể gây cạn storage.
- Đường dẫn log hoặc message có thể lộ user name, thư mục nội bộ; không ghi secret trong path.
- File permission quá rộng cho phép người không có quyền đọc hoặc sửa log.

**Thiết kế đơn giản nhất:** admin/deployment quyết định directory; ứng dụng chọn tên file cố định được kiểm soát; chỉ các process cần thiết có quyền ghi/đọc.

## 13. Docker, Kubernetes và CI

### Container

Trong Docker hoặc Kubernetes, path như **/app/logs/app.log** là **đường dẫn bên trong filesystem của container**. Nó không tự tương đương file nằm trên host và không tự bền vững khi container được thay thế.

Đối với log vận hành thông thường, **stdout/stderr cùng collector của nền tảng** thường là lựa chọn dễ quản lý hơn. Nếu bắt buộc file logging:
1. Mount volume phù hợp tại directory log đã cấu hình.
2. Kiểm tra UID/GID và quyền ghi của container.
3. Kiểm tra collector/sidecar đọc chính xác đường dẫn được mount.
4. Cấu hình rolling/retention và giám sát disk usage.
5. Thử restart, redeploy và shutdown để hiểu dữ liệu nào được giữ.
6. Không gán quyền root tùy tiện chỉ để có thể tạo file.

Dockerfile **WORKDIR** hoặc workingDir của container cũng có thể làm relative path trỏ đến vị trí khác với local.

### CI/test runner

CI thường chạy trong workspace tạm, nên file như **target/logs/app.log** có thể biến mất sau job. Khi cần giữ log test, cấu hình tải lên dưới dạng CI artifact hoặc thu console output.

Khi các test chạy song song, tránh nhiều test mở cùng một file với append=false. Có thể tạo directory tạm riêng bằng **Files.createTempDirectory** và dọn sau khi handler đã đóng.

Đừng giả định đường dẫn production tồn tại trong CI; nên đưa log directory qua property/test configuration.

## 14. Chẩn đoán khi file log không xuất hiện

Một quy trình kiểm tra theo thứ tự:

1. **Xác định backend**: JUL FileHandler, Logback FileAppender hay Log4j 2. SLF4J API không tự quyết định file.
2. **Xác nhận cấu hình được nạp**: logback.xml, logging.properties, profile, tham số JVM và thứ tự override.
3. **Xem relative/absolute**: nếu relative, lấy working directory của JVM đang chạy.
4. **Phân biệt file và directory**: cấu hình có nhầm target/logs thay cho target/logs/app.log không?
5. **Thư mục cha có tồn tại không?** Backend có tạo hay deploy cần tạo trước?
6. **User chạy service có quyền mở file không?** Kiểm tra mount, filesystem, lock và quota.
7. **Logger có event hợp lệ không?** Level/filter có thể khiến file chưa ghi record nào.
8. **File đã rotate chưa?** Tìm file active, generation, archive và retention.
9. **Có nhiều process ghi cùng path không?** Xem xung đột tên/lock/rotation.
10. **File nằm trong container hay host?** Có volume mount và collector chưa?
11. **File có encoding/format khác không?** FileHandler có thể ghi XMLFormatter; không nên mở và nghĩ file bị lỗi vì không có text một dòng.
12. **Handler/Appender đã flush hoặc close chưa?** Async queue và buffer có thể chưa hoàn tất.
13. **Collector/backend tập trung có trễ không?** File tồn tại không có nghĩa dữ liệu đã được ingest/index.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| IDE có file, service không thấy | CWD khác | In absolute path hoặc quan sát property khi startup |
| Không thể tạo file | Parent không có/quyền thiếu | Files.createDirectories khi được phép, xem IOException |
| File xuất ở đường dẫn lạ | Relative path hoặc config override | Xác nhận config hiệu lực và working directory |
| File ghi đè sau restart | append=false | Đổi append/rolling policy nếu cần giữ lịch sử |
| Thấy app.0.log, app.1.log | FileHandler có rotation | Kiểm tra %g/count/limit |
| File biến mất sau deploy | Container ephemeral hoặc retention | Xem volume/collector/cleanup |
| Log không có khi chương trình vẫn chạy | Level/filter/provider | Kiểm tra Logger, Handler/Appender, backend |
| File đúng nhưng khó phân tích | Formatter hoặc encoding khác | Xem SimpleFormatter/XMLFormatter, UTF-8 |
| File bị lock | Process khác hoặc Handler chưa close | Kiểm tra file ownership và lifecycle |

**Không dùng chmod 777 hoặc chạy service quyền cao** như cách khắc phục mặc định. Những biện pháp đó có thể che nguyên nhân và gây rủi ro bảo mật.

## 15. Checklist kiểm thử file log path

Trước khi triển khai một đường dẫn mới, hãy thử:

- **Hai working directory khác nhau**, xác nhận relative path thay đổi đúng như dự kiến.
- **Một absolute path** được cấp quyền trong môi trường phù hợp.
- **Directory chưa tồn tại**, xem có được tạo hoặc báo lỗi rõ.
- **Không có quyền ghi**, xác nhận ứng dụng không im lặng che lỗi.
- **Hai lần restart**, kiểm tra append/rotation/retention.
- **File name có Unicode**, dùng charset và cơ chế đọc phù hợp.
- **Nhiều JVM/process**, xác nhận không ghi trùng/khóa file bất ngờ.
- **Shutdown và AsyncAppender**, kiểm tra buffer/queue theo hợp đồng backend.
- **Container restart**, xác nhận mount và log có thể thu thập lại.
- **Input không tin cậy**, thử tên chứa ../, absolute path và symlink trong môi trường test.
- **Disk gần đầy**, theo dõi quota, rotation và cách báo lỗi.
- **Collector**, xác nhận nguồn đọc đúng active path và archive policy.

Các bài kiểm tra cần dùng dữ liệu giả và thư mục test, không ghi đè hoặc gây quá tải file production.

## 16. Câu hỏi tự kiểm tra

**1. Nếu chạy cùng JAR ở hai working directory khác nhau, logs/app.log có nhất thiết cùng file không?**  
Không. Relative path thường dựa vào working directory của tiến trình, không dựa vào tên JAR.

**2. Path.of("logs", "app.log") có tự tạo file không?**  
Không. Nó chỉ biểu diễn đường dẫn; phải có API tạo/mở file. Directory cha cũng phải tồn tại hoặc được tạo phù hợp.

**3. Vì sao LogPathDemo dùng Files.createDirectories trước FileHandler?**  
Để tạo các directory còn thiếu nếu có quyền, giảm lỗi mở file do thiếu parent.

**4. %h của JUL FileHandler có tự hoạt động trong Path.of("%h", "app.log") không?**  
Không. %h là token trong pattern của FileHandler, không phải phép thay thế chung của Path.

**5. file và fileNamePattern của RollingFileAppender có cùng nhiệm vụ không?**  
Không. file thường là active log file; fileNamePattern chỉ tên archive trong chính sách rotation.

**6. normalize() có bảo đảm path không đi ra ngoài root qua symlink không?**  
Không. normalize xử lý cú pháp, không loại toàn bộ rủi ro symlink hoặc TOCTOU.

**7. Vì sao file ở /app/logs có thể mất sau container redeploy?**  
Vì filesystem bên trong container có thể là ephemeral nếu không có volume hoặc collector lưu log phù hợp.

**8. Vì sao append=false làm demo dễ kiểm thử nhưng có thể nguy hiểm trong production?**  
Vì demo cần file sạch và số dòng ổn định; production thường cần giữ dữ liệu và quản lý rotation.

**9. Files.isWritable trả true có đảm bảo FileHandler.open sẽ thành công không?**  
Không. File hoặc quyền có thể thay đổi, filesystem có thể lỗi hoặc bị lock.

**10. Có file log nghĩa là mọi record đã được collector lưu bền vững chưa?**  
Chưa. Vẫn còn buffer, flush, network, collector, rotation/retention và chính sách lưu riêng.

## 17. Tài liệu tham khảo

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): resolve, normalize, toAbsolutePath, toRealPath.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): Files.createDirectories, file access và I/O.
- [Java SE 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): cú pháp pattern %h/%t/%g/%u, limit, count, append.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): FileAppender, RollingFileAppender và fileNamePattern.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): cấu hình file và property substitution.

## Ghi nhớ

**Đường dẫn log phải được xác định theo runtime thật.** Luôn biết ứng dụng đang chạy ở đâu, path là relative hay absolute, file nằm trong container hay volume nào, ai có quyền ghi và chính sách rotation/retention là gì. Dùng **Path/Files** để xử lý directory an toàn, dùng **Handler/Appender** đúng backend để ghi, không để input không tin cậy tự chọn nơi lưu. Ghi được một file cũng không có nghĩa mọi log đã được lưu bền vững ở backend cuối cùng.
