# Status của Logback: theo dõi trạng thái nội bộ và lỗi cấu hình

**Status của Logback** là những thông báo chẩn đoán do chính Logback sinh ra khi tìm, đọc và áp dụng cấu hình, tạo appender, thiết lập encoder hoặc gặp lỗi lúc ghi log. Hệ thống này giúp trả lời câu hỏi: **“Bộ máy logging đang hoạt động ra sao, và vì sao log không xuất hiện ở nơi mong đợi?”**

Cần phân biệt ngay từ đầu:

- **Application log:** do mã ứng dụng gọi `org.slf4j.Logger.info(...)`, `warn(...)`, `error(...)`; nội dung mô tả nghiệp vụ, tác vụ hoặc lỗi của ứng dụng.
- **Internal status:** do các thành phần Logback sinh ra để báo việc đọc cấu hình, mở file, cấu hình appender, lỗi I/O và những vấn đề của chính hệ thống logging.

Status **không chỉ là một log event có level khác**. Nó được quản lý qua `StatusManager` và có thể được hiển thị qua `StatusListener` hoặc `StatusPrinter`. Nếu chính appender ghi log đang lỗi, hệ thống status giúp phát hiện vấn đề đó thay vì phụ thuộc hoàn toàn vào appender đã hỏng.

## 1. Vì sao Logback cần hệ thống status?

Giả sử ứng dụng cấu hình log ra `/var/log/demo/app.log`, nhưng không có quyền tạo file. Mã nghiệp vụ vẫn chạy:

~~~java
logger.info("event=job_completed jobId={}", jobId);
~~~

Đây là **đoạn mã minh họa bên trong một phương thức có logger SLF4J và jobId**. Lệnh gọi có thể hoàn tất mà file mong đợi vẫn không tồn tại: appender có thể không được start hoặc không ghi được.

Một thông báo nội bộ có thể mô tả lỗi cấu hình, đường dẫn hoặc lỗi I/O. Dựa vào status, người vận hành lần theo vấn đề từ nơi Logback đọc cấu hình đến đích ghi log.

Luồng khái niệm:

~~~text
            Logback khởi tạo / hoạt động
                        |
             Thành phần phát Status
                        |
                        v
                  StatusManager
                    /       \
                   /         \
           Lưu status      Phát tới listener
           trong context   (nếu đăng ký)
                |                |
                v                v
        Đọc qua Java API    stdout / stderr
        hoặc StatusPrinter2

Ứng dụng --SLF4J Logger--> Logback LoggerContext
                                |
                           Appender/filter
                                |
                         stdout/file/collector
~~~

Hai tuyến có chung một `LoggerContext` nhưng khác mục đích. Ví dụ status INFO nói “đã nhận diện một resource cấu hình” không đồng nghĩa ứng dụng có một sự kiện nghiệp vụ ở mức INFO.

Các trường hợp status đặc biệt hữu ích: file cấu hình không được chọn như dự kiến, XML sai, class appender không tải được, encoder không phù hợp, file log không có quyền ghi, rolling policy thất bại, hoặc một lỗi xuất hiện sau nhiều giờ chạy.

## 2. Các thành phần cơ bản

| Thành phần | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `Status` | Một sự kiện chẩn đoán nội bộ | Có level, message, nguồn phát và có thể chứa nguyên nhân |
| `InfoStatus` | Thông báo thông tin nội bộ | Không phải SLF4J application INFO |
| `WarnStatus` | Cảnh báo nội bộ | Có thể liên quan đến cấu hình hoặc vận hành |
| `ErrorStatus` | Lỗi nội bộ | Cần xem nguyên nhân và ảnh hưởng thực tế |
| `StatusManager` | Thu thập và giữ lịch sử status, phân phối tới listener | Đọc từ `LoggerContext.getStatusManager()` |
| `StatusListener` | Nhận status mới khi đã đăng ký | Không tự phát lại các status cũ |
| `OnConsoleStatusListener` | In status ra `System.out` | Có thể bật trong XML/JVM property |
| `OnErrorConsoleStatusListener` | In status ra `System.err` | Hữu ích khi tách luồng console |
| `NopStatusListener` | Không in status đến listener này | Không phù hợp để điều tra lỗi |
| `StatusPrinter2` | In những status đang được giữ | Thích hợp cho các bản Logback gần đây |
| `StatusPrinter` | API in status kiểu static ở tài liệu cũ | Deprecated ở các bản mới, cần xem version |

Các lớp status chủ yếu thuộc package `ch.qos.logback.core.status`; `LoggerContext` thuộc `ch.qos.logback.classic`.

### Level của Status

Status thường có ba mức `Status.INFO`, `Status.WARN` và `Status.ERROR`.

| Status level | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| INFO | Một bước nội bộ diễn ra bình thường | Tìm thấy cấu hình, gắn appender |
| WARN | Điều kiện đáng chú ý | Thiết lập bất thường hoặc fallback |
| ERROR | Một lỗi nội bộ | Không khởi tạo được thành phần ghi log |

**Không dùng `Status.INFO` như tham số của `org.slf4j.Logger.info(...)`.** Các mức này là hằng số số nguyên trong API status, còn logging level thông thường thuộc SLF4J/Logback. Đặt root logger ở ERROR không có nghĩa toàn bộ status INFO tự động bị loại theo cùng cơ chế.

Status ERROR cần được điều tra, nhưng không phải lúc nào cũng đồng nghĩa toàn ứng dụng ngừng hoạt động: một appender lỗi có thể khiến log mất ở một đích, trong khi phần nghiệp vụ vẫn đang chạy.

## 3. Khi nào Logback sinh và in status?

Trong quá trình startup, Logback có thể:

1. Khởi tạo `LoggerContext` sau khi được chọn làm SLF4J provider.
2. Tìm tệp cấu hình thích hợp, chẳng hạn `logback-test.xml`, `logback.xml` hoặc một nguồn được chỉ định.
3. Đọc và phân tích cấu hình.
4. Tạo appender, encoder, filter, cấu hình level và gắn appender vào logger.
5. Tiếp tục ghi nhận các vấn đề nội bộ phát sinh khi appender hoạt động.

Logback lưu nhiều status vào `StatusManager`, **nhưng không nhất thiết in chúng ngay**. Khi cảnh báo hoặc lỗi xảy ra trong lúc parse cấu hình, Logback có cơ chế tự hiển thị status trên console để chẩn đoán. Hành vi này có những giới hạn:

- Nếu **không có warning/error**, status INFO vẫn có thể đã được lưu nhưng không được tự in.
- Khi **đã đăng ký một status listener**, việc tự in status do lỗi cấu hình có thể bị tắt để tránh trùng; listener trở thành kênh hiển thị dự kiến.
- **Không tìm thấy file cấu hình** không luôn được coi là lỗi để tự in, vì Logback có thể dùng fallback.
- Listener khai báo trong **XML sai cú pháp** có thể không được tạo, bởi parser chưa đọc được khai báo đó.

Vì vậy **console không có dòng status** chưa đủ kết luận không có thông tin chẩn đoán. Có thể chủ động bật listener hoặc in lịch sử đã lưu.

## 4. Bật status trong logback.xml

Cách rõ ràng nhất là đặt `statusListener` gần đầu cấu hình. Ví dụ tệp `src/main/resources/logback.xml`:

~~~xml
<configuration>
    <statusListener class="ch.qos.logback.core.status.OnConsoleStatusListener"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger{36} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

`OnConsoleStatusListener` xuất status mới qua **System.out**. Trong khi đó, log nghiệp vụ theo `CONSOLE` appender sẽ có định dạng `%level | %logger | %msg`. Nếu chỉ xem console, hai kiểu thông báo có thể xuất hiện xen nhau.

Một cú pháp ngắn là đặt thuộc tính `debug` ngay trên phần tử `configuration`:

~~~xml
<configuration debug="true">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%level | %logger{36} | %msg%n</pattern></encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
</configuration>
~~~

Trong Logback, `<configuration debug="true">` là cách bật kênh status console tương đương đăng ký listener thích hợp cho mục đích chẩn đoán.

**Đừng nhầm `debug="true"` trong configuration với `<root level="DEBUG">`.** Thiết lập đầu tiên điều khiển **thông tin nội bộ Logback**; thiết lập thứ hai điều khiển **mức log của ứng dụng**.

Nếu appender bị lỗi nhưng status listener đang hoạt động, bạn có thể thấy status ERROR dù câu lệnh `logger.error(...)` của ứng dụng không đi tới đích file đang hỏng.

## 5. Bật status sớm bằng JVM property

Khi nghi ngờ `logback.xml` không được tìm thấy hoặc XML quá lỗi để cài listener, hãy bật listener ở **JVM level**:

~~~bash
java -Dlogback.statusListenerClass=ch.qos.logback.core.status.OnConsoleStatusListener -jar app.jar
~~~

Đây là lệnh minh họa với `app.jar` của một ứng dụng có Logback. JVM property phải đứng trước `-jar`.

Logback còn hỗ trợ dạng ngắn:

~~~bash
java -Dlogback.statusListenerClass=STDOUT -jar app.jar
~~~

Có thể chọn lớp `ch.qos.logback.core.status.OnErrorConsoleStatusListener` để gửi status sang **System.err** thay vì **System.out**.

Một lựa chọn đặc biệt là:

~~~bash
java -Dlogback.statusListenerClass=ch.qos.logback.core.status.NopStatusListener -jar app.jar
~~~

`NopStatusListener` bỏ qua status chuyển tới nó, đồng thời việc cài một status listener có thể vô hiệu hóa cơ chế tự in lỗi cấu hình. **Không dùng lựa chọn này trong lúc đang điều tra lỗi**; nó khiến thông tin nội bộ khó thấy hơn.

JVM property được dùng để quan sát Logback sớm, **không tự sửa file cấu hình**, không bổ sung dependency thiếu và không thay đổi việc SLF4J chọn backend. Nếu runtime đang dùng Log4j 2 hoặc SLF4J NOP, property dành cho Logback không giúp quan sát status của backend khác.

## 6. Đọc status trong mã Java

Khi Logback đã được chọn làm SLF4J backend, có thể truy cập manager:

~~~java
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.core.status.Status;
import ch.qos.logback.core.status.StatusManager;
import org.slf4j.LoggerFactory;

// Đoạn minh họa nằm trong một phương thức của ứng dụng dùng Logback.
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
StatusManager manager = context.getStatusManager();

for (Status status : manager.getCopyOfStatusList()) {
    System.out.println(status.getLevel() + " " + status.getMessage());
}
~~~

Điều kiện quan trọng: `LoggerFactory.getILoggerFactory()` chỉ ép kiểu được sang `LoggerContext` nếu **backend thực sự là Logback**. Với provider khác, phép ép kiểu có thể gây `ClassCastException`.

`getCopyOfStatusList()` trả về bản sao của những status manager đang giữ. Trình quản lý mặc định giới hạn số thông báo được lưu, thường giữ phần đầu và phần gần đây để tránh tăng bộ nhớ vô hạn. **Không xem status manager là kho lưu trữ vĩnh viễn mọi sự cố.**

### In status với StatusPrinter2

Ở các bản Logback mới, có thể gọi:

~~~java
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.core.util.StatusPrinter2;
import org.slf4j.LoggerFactory;

// Đoạn minh họa, runtime phải dùng Logback.
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
new StatusPrinter2().print(context, 0);
~~~

Hàm in ra những status đang được giữ trong context, thường có timestamp, nguồn status và message. **Không có stdout cố định** vì số lượng status, thời điểm và cấu hình khác nhau giữa các lần chạy.

Trong nhiều tài liệu cũ, bạn sẽ gặp `StatusPrinter.print(context)`. Các bản Logback mới đánh dấu `StatusPrinter` là **deprecated**, thay bằng `StatusPrinter2`. Nếu dự án dùng version cũ không có API mới, hãy dùng API thực sự được phiên bản đó cung cấp.

### Listener đăng ký trễ không nhận lại status startup

Khi gọi:

~~~java
StatusManager manager = context.getStatusManager();
manager.add(myListener);
~~~

Listener chỉ nhận **các status phát sinh từ thời điểm được thêm trở đi**, không được tự động replay toàn bộ status trước đó. Nếu cần xem status startup, hãy sử dụng `getCopyOfStatusList()` hoặc status printer; nếu cần nhận status ngay trong giai đoạn khởi tạo, bật listener từ XML/JVM property.

## 7. Ví dụ chạy được Java 17+: StatusManager khác Logger

Ví dụ độc lập dưới đây dùng **Logback 1.5.18**, Java 17+ và Maven. Chương trình chủ động tạo **hai status thử nghiệm** `demo.status_probe_info` và `demo.status_probe_warn` để minh họa listener, rồi phát một application log thông thường. Hai status này **không phải báo cáo lỗi thật** của Logback.

Cấu trúc dự án:

~~~text
logback-status-demo/
├── pom.xml
└── src/main/
    ├── java/demo/StatusDemo.java
    └── resources/logback.xml
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logback-status-demo</artifactId>
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
          <version>3.5.1</version>
        </plugin>
      </plugins>
    </build>
</project>
~~~

`logback-classic` cung cấp backend và các dependency liên quan, bao gồm SLF4J API qua Maven dependency graph. Đối với thư viện dùng chung, thông thường chỉ cần facade SLF4J ở lớp nghiệp vụ; riêng ví dụ này sử dụng API Logback trực tiếp để khảo sát status.

### 7.2. StatusDemo.java

Tạo `src/main/java/demo/StatusDemo.java`:

~~~java
package demo;

import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.core.status.InfoStatus;
import ch.qos.logback.core.status.Status;
import ch.qos.logback.core.status.StatusListener;
import ch.qos.logback.core.status.StatusManager;
import ch.qos.logback.core.status.WarnStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class StatusDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(StatusDemo.class);

    public static void main(String[] args) {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        StatusManager manager = context.getStatusManager();

        StatusListener listener = status -> {
            if (status.getMessage().startsWith("demo.")) {
                System.out.println("listener=" +
                        levelName(status.getLevel()) +
                        " " + status.getMessage());
            }
        };
        manager.add(listener);

        manager.add(new InfoStatus("demo.status_probe_info", StatusDemo.class));
        manager.add(new WarnStatus("demo.status_probe_warn", StatusDemo.class));

        long stored = manager.getCopyOfStatusList().stream()
                .filter(s -> s.getMessage().startsWith("demo."))
                .count();
        System.out.println("stored=" + stored);

        LOG.info("event=application_ready");
        manager.remove(listener);
    }

    private static String levelName(int level) {
        return switch (level) {
            case Status.INFO -> "INFO";
            case Status.WARN -> "WARN";
            case Status.ERROR -> "ERROR";
            default -> "UNKNOWN";
        };
    }
}
~~~

`manager.add(listener)` đăng ký listener trước hai status mẫu. `new InfoStatus(...)` và `new WarnStatus(...)` là **API status**, không phải lời gọi logger ứng dụng. `getCopyOfStatusList()` đọc các status được lưu và lọc theo tiền tố riêng để không phụ thuộc số status startup. Sau đó `LOG.info(...)` ghi sự kiện ứng dụng bình thường qua Logback appender.

Chương trình gỡ listener ở cuối để minh họa việc quản lý vòng đời. Trong chương trình production, nếu listener tồn tại toàn thời gian chạy, cần quản lý đăng ký và shutdown có chủ đích.

### 7.3. logback.xml

Tạo `src/main/resources/logback.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%level | %logger{30} | %msg%n</pattern></encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ví dụ không bật `statusListener` trong XML để output chỉ có các dòng do chương trình chủ động in. Nếu thêm listener toàn cục, có thể xuất hiện nhiều status thật về quá trình khởi tạo; đó là hành vi đúng khi đã bật quan sát toàn bộ.

### 7.4. Chạy và kiểm tra output

Từ thư mục chứa `pom.xml`, với Maven và JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StatusDemo
~~~

**Output chính xác đã được kiểm chứng**:

~~~text
listener=INFO demo.status_probe_info
listener=WARN demo.status_probe_warn
stored=2
INFO | demo.StatusDemo | event=application_ready
~~~

Giải thích:

- Hai dòng `listener=...` do **StatusListener** tự in ra `System.out`.
- `stored=2` xác nhận manager còn giữ đúng hai status có tiền tố `demo.`.
- Dòng `INFO | demo.StatusDemo | event=application_ready` đi qua **application Logger → Logback appender**, theo `logback.xml`.

Kết quả cho thấy rõ **status message và application log message là hai cơ chế riêng**, dù cùng chạy trong một ứng dụng có Logback.

## 8. Lưu ý khi dùng listener lâu dài

StatusListener giúp phát hiện lỗi xuất hiện **sau khi ứng dụng đã khởi tạo**, ví dụ file log không rotate được do hết dung lượng, đường dẫn không còn ghi được hoặc một appender báo lỗi I/O.

Một listener tự viết cần chú ý:

- Không gọi lại cùng hệ logging đang hỏng để “log lỗi của logging”; có thể tạo vòng lặp hoặc thêm nhiễu.
- Không chạy thao tác tốn kém, chặn lâu hoặc ném exception không kiểm soát ngay trong callback status.
- Chỉ đánh giá status WARN/ERROR cùng **ngữ cảnh** và tác động đến đích ghi; không coi mọi WARN tự động là lỗi nghiệp vụ.
- Listener được đăng ký sau startup chỉ thấy status mới; hãy đọc lịch sử đang lưu khi cần đối chiếu.
- Nếu cần gửi status tới hệ thống giám sát, thiết kế đường xử lý độc lập và giới hạn tần suất để tránh bão cảnh báo.

Một phương án thích hợp khi debug tại chỗ là dùng `OnConsoleStatusListener`; khi chạy lâu dài, có thể dùng giám sát riêng nếu nhu cầu vận hành đòi hỏi. Việc giữ console in toàn bộ status INFO ở production có thể làm log vận hành nhiễu.

## 9. Các tình huống lỗi thực tế

### 9.1. Không tìm thấy logback.xml

Ứng dụng không có file ở classpath đúng vị trí hoặc một file khác được ưu tiên. Logback có thể dùng fallback. Việc này **không nhất thiết tự in ERROR**, bởi không tìm thấy file không luôn bị coi là lỗi.

Kiểm tra artifact chạy cuối, resource classpath và các cấu hình được chỉ định khác. Dùng JVM status property hoặc `StatusPrinter2` để xem Logback đã tìm và nạp resource nào.

### 9.2. XML không hợp lệ

Nếu `logback.xml` có lỗi cú pháp, parser có thể không đi tới dòng `<statusListener>`. Khi đó bật listener qua system property từ ngoài file sẽ có ích. Xem thông báo lỗi có vị trí phần tử, tên class và nguyên nhân, sửa XML rồi kiểm tra lại sau khởi động.

### 9.3. FileAppender không ghi được

Một appender ghi file có thể báo status WARN/ERROR khi đường dẫn không hợp lệ, thiếu quyền ghi hoặc thất bại trong tác vụ rollover. Hãy kiểm tra **status của appender**, hệ thống file trong môi trường thực chạy (container/VM), và thử phát một application log sau khi sửa để xác nhận đích nhận.

Đừng giả định ứng dụng không báo exception là file đã ghi thành công: logging thường cố tránh làm gián đoạn nghiệp vụ ngay cả khi một đường xuất gặp sự cố.

### 9.4. Có nhiều cấu hình

Trong test, `logback-test.xml` có thể được dùng thay `logback.xml`; một cấu hình khai báo qua property hay framework có thể làm việc chọn file khác kỳ vọng. Status nội bộ thường giúp tìm nguồn cấu hình đang được áp dụng. Đừng sửa một file chỉ vì tên giống file Logback nếu runtime thực tế không đọc nó.

### 9.5. SLF4J dùng backend khác

Nếu runtime đang dùng Log4j 2, SLF4J Simple hoặc NOP, ép kiểu `LoggerFactory.getILoggerFactory()` sang `LoggerContext` thất bại. Kiểm tra runtime provider trước; cấu hình status của Logback chỉ phù hợp khi backend Logback thực sự đang có hiệu lực.

## 10. Phân biệt các tùy chọn cấu hình dễ nhầm

| Tùy chọn | Điều khiển | Không bảo đảm |
| --- | --- | --- |
| `<configuration debug="true">` | Hiển thị status nội bộ qua listener | Không tự bật application DEBUG |
| `<root level="DEBUG">` | Cho logger ứng dụng phát DEBUG nếu appender chấp nhận | Không tự in status nội bộ |
| `<statusListener class="...OnConsoleStatusListener"/>` | In status mới tới stdout | Không tự replay status trước đăng ký |
| `-Dlogback.statusListenerClass=STDOUT` | Bật listener từ JVM | Không sửa XML hay bổ sung backend |
| `StatusPrinter2.print(context, 0)` | In các status đã được manager giữ | Không là hệ lưu vĩnh viễn |
| `NopStatusListener` | Bỏ qua status gửi tới listener | Không phải cách chẩn đoán lỗi |

Ví dụ khi root INFO nhưng `configuration debug="true"`, bạn vẫn có thể thấy **status INFO của Logback**, còn `logger.debug("cache probe")` trong mã ứng dụng vẫn bị root level INFO loại.

Ngược lại, khi root DEBUG nhưng không bật status listener, các message DEBUG của ứng dụng có thể xuất, trong khi quá trình khởi tạo Logback vẫn không in đầy đủ status INFO.

## 11. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy `LOG.info` | Logger level, appender, filter hoặc backend sai | Xác định provider, kiểm tra status và đầu ra |
| Không thấy status dù app chạy | Không bật listener/in lịch sử và không có lỗi cấu hình cần tự in | Bật debug/statusListener hoặc `StatusPrinter2` |
| Listener trong XML không hoạt động | File không được nạp hoặc XML không parse được | Dùng JVM property, kiểm tra file đang nạp |
| Tăng root DEBUG mà vẫn không thấy status | Nhầm log level với status system | Dùng status listener/manager |
| Status INFO hiện nhưng log ứng dụng không ghi file | Appender file hỏng hoặc không được gắn đúng | Xem status WARN/ERROR, kiểm tra quyền ghi và routing |
| Listener đăng ký trong main không thấy status startup | Listener chỉ nhận status sau khi đăng ký | Đọc `getCopyOfStatusList()` |
| Thấy status trùng | Đăng ký listener lặp hoặc vừa in lịch sử vừa nghe live | Kiểm tra các kênh status output |
| `ClassCastException` tại LoggerContext | SLF4J đang chọn backend khác | Kiểm tra `LoggerFactory.getILoggerFactory()` |
| Console không lỗi nhưng log file mất | Cấu hình/đường file hoặc runtime I/O lỗi | Xem status, quyền volume, phát log thử |
| Cấu hình thiếu mà không báo ERROR | Fallback có thể được dùng | Bật status JVM và xem nguồn cấu hình |
| NopStatusListener làm mất cảnh báo | Listener chủ động bỏ qua status | Thay listener trong giai đoạn debug |

## 12. Quy trình điều tra theo từng bước

1. **Kiểm tra nhánh mã:** chắc chắn ứng dụng đã chạy tới lệnh logger.
2. **Xác định backend:** SLF4J đang dùng Logback, Log4j 2, Simple hay NOP?
3. **Bật status từ sớm:** khi nghi lỗi startup, dùng `-Dlogback.statusListenerClass=STDOUT`.
4. **Xác định nguồn cấu hình:** file nào được nạp, có fallback hay parse warning/error không?
5. **Kiểm tra appender:** appender có được tạo/start/gắn vào root/logger đúng không, có lỗi file hoặc rolling không?
6. **Kiểm tra level/filter:** root, logger theo package, filter appender có chặn message cần tìm không?
7. **Xác nhận đích thực tế:** stdout/stderr, file hoặc collector đang nhận bản ghi chưa?
8. **Giám sát lỗi runtime:** nếu lỗi xảy ra sau startup, dùng listener hoặc cơ chế giám sát phù hợp thay vì chỉ in status một lần.

Không kết luận “logging tốt” chỉ vì có status INFO hay “logging hỏng” chỉ vì không thấy status trên console. Cần đối chiếu status với việc gửi một log event thử và xác minh đích nhận.

## 13. Bài tập tự kiểm tra

Cho cấu hình:

~~~xml
<configuration debug="true">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%level | %msg%n</pattern></encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
</configuration>
~~~

Ứng dụng (đoạn minh họa với logger kiểu SLF4J) gọi:

~~~java
logger.debug("event=cache_probe");
logger.info("event=job_completed");
~~~

Hãy giải thích:

1. Tại sao có thể thấy nhiều status INFO lúc khởi tạo?
2. Tại sao dòng application DEBUG vẫn không được xuất?
3. Nếu XML sai cú pháp trước lúc Logback xử lý thuộc tính debug, nên bật status bằng cách nào?
4. Nếu `OnConsoleStatusListener` được thêm bằng mã trong `main()`, nó có nhận lại status đã xảy ra khi đọc cấu hình không?
5. Nếu ứng dụng ghi file thất bại, bạn cần xác minh những gì sau khi sửa quyền file?

**Đáp án gợi ý:**

1. `configuration debug="true"` bật quan sát status nội bộ của Logback.
2. Root logger ở INFO vẫn loại application DEBUG.
3. Dùng JVM property `-Dlogback.statusListenerClass=STDOUT` từ lúc khởi động.
4. Không tự động; đọc status đã lưu trong manager hoặc dùng status printer.
5. Kiểm tra status không còn lỗi **và** phát một application event mới, xác nhận file/đích thật nhận được bản ghi.

## 14. Thực hành an toàn và tài liệu tham khảo

Status có thể chứa đường dẫn file, tên cấu hình và chi tiết môi trường. **Không xuất status ra một endpoint công khai thiếu xác thực** trong hệ thống production. Khi debug, chọn kênh console thích hợp, quản lý quyền xem log và giảm verbosity sau khi hoàn tất.

Các ví dụ ở đây dựa trên Logback 1.5.18, Java 17+ và Maven. Ở phiên bản khác, hãy kiểm tra sự tồn tại của API `StatusPrinter2` hoặc cú pháp cấu hình mà dự án đang dùng. Khi một framework quản lý Logback (chẳng hạn Spring Boot), cần xét thêm thứ tự khởi tạo và cách framework chọn file cấu hình.

Tài liệu chính thức: [Logback Manual — Configuration và status messages](https://logback.qos.ch/manual/configuration.html).

**Ghi nhớ:** `StatusManager` lưu và phân phối **thông tin chẩn đoán nội bộ của Logback**; `StatusListener` nhận thông báo mới, còn `StatusPrinter2` giúp xem các thông báo đang lưu. Khi không thấy log, hãy kiểm tra **cả status system và tuyến application Logger → appender → đích ghi**, thay vì chỉ thay mức DEBUG/INFO.