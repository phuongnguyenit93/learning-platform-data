# Luân chuyển file log trong vận hành production Java

## 1. Luân chuyển file log là gì và vì sao cần?

**Luân chuyển file log (log rotation, rolling)** là quá trình chuyển file log đang ghi sang một thế hệ hoặc tên lưu trữ khác và bắt đầu ghi vào file mới theo một chính sách, thường dựa trên **dung lượng**, **thời gian** hoặc kết hợp hai điều kiện. Mục đích là kiểm soát kích thước file đang hoạt động, tránh để một file phình mãi, hỗ trợ thu thập, nén và quản lý vòng đời log trong production.

Ví dụ một ứng dụng ghi `application.log`; mỗi khi đạt ngưỡng, file được roll thành `application.2026-01-15.1.log.gz` và ứng dụng tiếp tục ghi file active mới. Cú pháp tên file, cách đánh số và thời điểm nén phụ thuộc vào công cụ cụ thể.

Một pipeline tổng quát:

~~~text
Java application
       |
       v
Logger -> Handler / Appender
                  |
                  v
            Active log file
                  |
            Rotation policy
               /      \
        Size/time     No trigger
            |             |
            v             v
       Roll old file   Keep appending
            |
            +--> Compress/archive/retention policy
            |
            +--> File shipper / collector
                   |
                   v
              Central log store
~~~

**Bốn việc không giống nhau:**

- **Rotation:** đóng/chuyển thế hệ file active và tiếp tục ghi file mới.
- **Retention:** quyết định giữ bao nhiêu file, bao lâu hoặc tối đa bao nhiêu dung lượng rồi xóa bản cũ.
- **Compression/archival:** nén hoặc chuyển file cũ sang kho khác; không đồng nghĩa đã có chính sách xóa.
- **Collection/shipping:** agent đọc log và gửi lên hệ thống tập trung; việc đọc đúng một file chưa chứng minh dữ liệu đã lưu bền ở đích.

**Điểm mấu chốt:** rotation giúp quản lý file, **không tự bảo đảm log không mất, không trùng, có đủ dữ liệu cho audit, hay không lộ thông tin cá nhân**. Phải đánh giá cả ứng dụng, filesystem, shipper và collector.

## 2. Những mô hình rotation phổ biến

| Chính sách | Khi nào roll? | Ưu điểm | Điều cần chú ý |
| --- | --- | --- | --- |
| **Size-based** | Khi file đạt/vượt ngưỡng dung lượng | Hạn chế file active quá lớn trong giờ cao điểm | Có thể roll rất nhiều lần trong một ngày |
| **Time-based** | Theo ngày, giờ hoặc chu kỳ | Dễ tổ chức log theo thời gian | Một file trong ngày có thể rất lớn |
| **Size + time** | Đến chu kỳ hoặc đạt ngưỡng trong chu kỳ | Kiểm soát kích thước và phân vùng theo ngày | Tên file cần ngày + chỉ số thế hệ |
| **Startup-based** | Khi ứng dụng khởi động theo policy riêng | Tách log của các lần chạy | Restart nhiều lần sinh nhiều file nhỏ |
| **External rotation** | Công cụ OS/agent tự đổi tên/copy file | Quản lý tập trung ngoài Java | Phải phối hợp file descriptor và khả năng reopen |
| **Container runtime rotation** | Runtime/kubelet xoay file stdout/stderr | Ứng dụng không cần tự mở file | Khác với rotation trong JVM; giữ và ship log vẫn cần policy |

Một số hệ thống kết hợp nhiều lớp. Ví dụ Java ghi stdout, container runtime xoay file stdout, shipper đọc các file runtime rồi collector lưu dài hạn. Cấu hình thêm một appender file trong Java có thể dẫn đến **hai bản sao** nếu shipper cũng thu cả stdout và file đó.

### Size-based khác giới hạn dung lượng tuyệt đối

Giả sử ngưỡng 10 MB. Một record dài có thể làm file vượt ngưỡng trước khi rollover được thực hiện. Chính sách size-based thường kích hoạt tại điểm ghi hoặc lần kiểm tra tiếp theo chứ **không nhất thiết bảo đảm từng file luôn nhỏ hơn đúng 10 MB từng byte**. Hệ thống vẫn cần giới hạn kích thước log event và bảo vệ ổ đĩa.

### Time-based không phải retention

Rolling mỗi ngày tạo các file ngày mới; **không có nghĩa file 30 ngày trước sẽ tự bị xóa**. Công cụ phải có `maxHistory`, số thế hệ, `totalSizeCap`, TTL hoặc retention policy riêng. Không nên dùng timestamp trên tên file như bằng chứng cho việc đã xóa đúng hạn.

## 3. Chọn chiến lược theo môi trường

Đặt các câu hỏi trước khi cấu hình:

1. Log đi ra **stdout/stderr**, file nội bộ, hay cả hai?
2. Chạy **một JVM** hay nhiều replica/container cùng ghi một đường dẫn?
3. Mục đích của file là **debug tại host**, nguồn cho log shipper, hay kho lưu chính thức?
4. Log trung bình và ở giờ cao điểm là bao nhiêu byte/giây hoặc GB/ngày?
5. Có giới hạn dung lượng filesystem, thời hạn giữ, quy định dữ liệu và SLO độ trễ thu thập không?
6. Khi file đang được ghi mà công cụ bên ngoài rename/truncate, writer sẽ phản ứng như thế nào?
7. Khi đích tập trung không nhận log, shipper có **persistent queue/checkpoint** để phục hồi không?
8. Những event cực kỳ quan trọng có cần một **audit/event store riêng** thay vì dựa vào file rotation thông thường không?

Một quy tắc vận hành thường hữu ích: trong container, **ghi structured log ra stdout/stderr và để nền tảng chịu trách nhiệm rotation/shipping** nếu hạ tầng đã được thiết kế, theo dõi và phân quyền đầy đủ. Với VM/bare metal cần file cục bộ, chọn **một thành phần sở hữu rotation** (logging backend hoặc công cụ OS được ứng dụng phối hợp). Không để hai công cụ độc lập cùng xoay một file active.

## 4. Java Util Logging (JUL): `FileHandler` có thể tự xoay theo dung lượng

JDK có `java.util.logging.FileHandler`. Một constructor quan trọng:

~~~java
FileHandler(String pattern, int limit, int count, boolean append)
~~~

Ý nghĩa:

- `pattern`: đường dẫn hoặc mẫu tên file.
- `limit`: ngưỡng kích thước theo **byte** mà handler dùng để kích hoạt rotation.
- `count`: số file trong chu kỳ rotation của handler, **bao gồm file active**, không phải “số backup cộng thêm file active”.
- `append`: có nối thêm vào file hiện có khi mở hay bắt đầu chu kỳ ghi mới, tùy cách handler mở file và trạng thái file.

Với `count=3`, một chu kỳ thông thường có tối đa ba thế hệ file, ví dụ `app-0.log`, `app-1.log`, `app-2.log`. Khi roll nhiều lần, các thế hệ cũ hơn sẽ bị thay thế. Tính chất này là **retention theo số file**, không phải retention theo số ngày.

### Các token tên file thường gặp của JUL

| Token | Ý nghĩa |
| --- | --- |
| `%g` | Generation number của file trong chu kỳ, thường 0 là thế hệ đang ghi |
| `%u` | Số unique được dùng để xử lý va chạm tên/lock giữa các `FileHandler` |
| `%t` | Thư mục tạm do Java xác định |
| `%h` | Home directory của người dùng |
| `%%` | Ký tự phần trăm `%` |

Ví dụ mẫu `logs/app-%g-%u.log` có thể tạo tên chứa generation và unique number. **`%u` không phải user ID hay số request.** Nếu nhiều JVM ghi vào cùng pattern, cơ chế lock/unique có thể tạo file khác nhau; không được xem nó là giải pháp hoàn chỉnh để chia sẻ một log file giữa nhiều process.

**JUL `FileHandler` có rotation dựa trên size**, nhưng không cung cấp một time-based rolling policy phong phú như các rolling appender chuyên dụng. Nếu cần xoay mỗi ngày/giờ kèm nén và xóa theo thời gian, có thể dùng backend hỗ trợ chính sách đó hoặc cấu hình hạ tầng chuyên trách, với việc chuyển file descriptor đúng cách.

## 5. Ví dụ Java 17 chạy độc lập: xoay ba thế hệ file

Chương trình sau dùng **JDK 17 thuần**, không cần dependency. Nó tạo một thư mục tạm riêng mỗi lần chạy, thiết lập `FileHandler` với giới hạn **512 byte/file**, tổng cộng **3 thế hệ**, rồi ghi 60 event giả. Số event này đủ để kích hoạt nhiều lần rotation.

Để output nhất quán và không ghi vào console qua logger cha, chương trình:

- Tắt `useParentHandlers`.
- Gắn một `FileHandler`, formatter đơn giản: mỗi event một dòng.
- Đóng handler trước khi đọc file để flush và giải phóng lock.
- Kiểm tra sự tồn tại của ba generation và số dòng được giữ.
- Chỉ in kết quả kiểm tra ra stdout, không in đường dẫn tạm ngẫu nhiên.

Tạo file **`FileRotationDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public class FileRotationDemo {
    private static final int FILE_LIMIT_BYTES = 512;
    private static final int FILE_COUNT = 3;
    private static final int EVENTS = 60;

    public static void main(String[] args) throws Exception {
        // Moi lan chay co thu muc rieng, khong ghi de log cu.
        Path directory = Files.createTempDirectory("jul-rotation-demo-");

        Logger logger = Logger.getLogger("demo.file.rotation");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        String pattern = directory.resolve("app-%g.log").toString();
        FileHandler handler = new FileHandler(
                pattern, FILE_LIMIT_BYTES, FILE_COUNT, false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        try {
            for (int i = 1; i <= EVENTS; i++) {
                String line = String.format(Locale.ROOT,
                        "seq=%03d event=cache_checked outcome=OK requestId=req-demo",
                        i);
                logger.info(line);
            }
        } finally {
            // Thao handler truoc khi doc file va giai phong lock.
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        int filesFound = 0;
        long retainedLines = 0;

        for (int generation = 0;
                generation < FILE_COUNT; generation++) {
            Path file = directory.resolve(
                    "app-" + generation + ".log");
            if (Files.isRegularFile(file)) {
                filesFound++;
                try (Stream<String> lines =
                        Files.lines(file, StandardCharsets.UTF_8)) {
                    retainedLines += lines.count();
                }
            }
        }

        System.out.println("eventsGenerated=" + EVENTS);
        System.out.println("rotationFiles=" + filesFound);
        System.out.println(
                "olderEventsRemoved=" + (retainedLines < EVENTS));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FileRotationDemo.java
java FileRotationDemo
~~~

**Stdout mong đợi chính xác** khi chạy thành công bằng JDK 17+ trên filesystem hỗ trợ tạo/ghi file bình thường, không xảy ra xung đột tên/lock:

~~~text
eventsGenerated=60
rotationFiles=3
olderEventsRemoved=true
~~~

**Stderr:** trống trong trường hợp thành công. Log không đi ra stdout/stderr, vì nó được gửi vào `FileHandler` riêng. Thư mục tạm của hệ điều hành sẽ chứa các file `app-0.log`, `app-1.log`, `app-2.log`; ví dụ cố ý không in đường dẫn vì nó thay đổi mỗi lần.

### Giải thích từng bước

1. `Files.createTempDirectory` tạo thư mục demo mới, không ghi đè file log của lần chạy trước.
2. `new FileHandler(pattern, 512, 3, false)` thiết lập kích hoạt rollover theo byte và ba file trong chu kỳ. `false` nghĩa không cố tình nối vào file cũ từ chu kỳ trước.
3. `handler.setEncoding("UTF-8")` chọn charset cho handler; message demo chỉ dùng ASCII để dễ tính.
4. Formatter trả một dòng cho mỗi record. Không in timestamp động để output test đơn giản; hệ thống production thường nên ghi timestamp UTC, severity, correlation ID và metadata được chuẩn hóa.
5. 60 event dài hơn khả năng giữ của ba file 512 byte; các file thế hệ cũ bị **thay thế khi roll**, nên `retainedLines < EVENTS`.
6. `finally` đóng handler và giải phóng lock trước khi đọc lại. Nếu một handler khác đang ghi cùng file, vòng đời của nó phải được quản lý riêng.
7. Tên file được tính qua `%g`. Với thư mục riêng của demo không có lock collision, các thế hệ thường là 0, 1 và 2.

**Lưu ý thực tế:** ngưỡng 512 byte và ba file chỉ để kích hoạt rotation dễ quan sát. Production phải chọn dựa trên lượng log, thời gian điều tra và dung lượng ổ đĩa; giới hạn theo byte không đồng nghĩa file không bao giờ vượt quá một ngưỡng tuyệt đối ở mọi thời điểm. Ví dụ **để lại file trong thư mục tạm** để người học có thể kiểm tra; muốn dọn chúng phải theo chính sách môi trường, không xóa nhầm file của tiến trình khác.

### Tại sao ví dụ chứng minh rotation nhưng không chứng minh lưu trữ đầy đủ?

Chương trình ghi 60 event, nhưng chỉ giữ lại những event nằm trong ba thế hệ mới nhất. `olderEventsRemoved=true` không phải bug của chương trình — đó là hậu quả có chủ đích của retention theo số file.

Với hệ thống cần điều tra lâu dài, phải **thu thập/ship log kịp thời trước khi file bị thay thế**, hoặc có một bước lưu trữ bền vững khác. Nếu collector down lâu hơn thời gian file cục bộ đủ dung lượng, một phần log có thể biến mất dù `FileHandler` đang hoạt động đúng.

## 6. Rotation theo thời gian và dung lượng với Logback

Khi dự án dùng **SLF4J + Logback** và cần rolling linh hoạt hơn, có thể dùng `RollingFileAppender`. Mẫu cấu hình sau là **minh họa dành cho môi trường Linux có thư mục `/var/log/example-app` được cấp quyền ghi**; cần có dependency Logback/backend phù hợp và thử trên phiên bản đang sử dụng, không phải cấu hình tự áp dụng cho JUL.

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/example-app/application.log</file>

        <rollingPolicy
          class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>
              /var/log/example-app/archive/app.%d{yyyy-MM-dd}.%i.log.gz
            </fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Ý nghĩa:

- `<file>` là tên **active file** mà appender ghi khi chưa rollover.
- `SizeAndTimeBasedRollingPolicy` dùng cả ngày và chỉ số `%i`; `maxFileSize` kích hoạt rollover khi đến ngưỡng trong cùng chu kỳ.
- `fileNamePattern` là mẫu tên **archive**; `.gz` cho biết có nén sau rollover theo policy.
- `maxHistory=14` thể hiện số chu kỳ lịch sử được giữ theo rolling policy; với `%d{yyyy-MM-dd}`, thông thường hiểu theo **chu kỳ ngày**, không có nghĩa “14 file”.
- `totalSizeCap` giới hạn tổng dung lượng archive theo khả năng và thời điểm cleanup của rolling policy, **không nên coi là quota đĩa cứng tuyệt đối**.
- `root` gắn một file appender; nếu thêm console appender, phải hiểu liệu shipper thu cả hai hay không.

**Lưu ý cấu hình XML:** khi triển khai thực, `fileNamePattern` nên được viết **trên một dòng không có khoảng trắng hoặc newline không mong muốn**, chẳng hạn:

~~~xml
<fileNamePattern>/var/log/example-app/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
~~~

Vì vậy, nếu copy cấu hình minh họa trên, hãy dùng phiên bản một dòng cho `fileNamePattern` để tránh giá trị chứa whitespace ngoài ý muốn. Các thông số khác cần đo dưới tải thật và xác minh quyền tạo thư mục.

### Logback không phải JUL

`java.util.logging.FileHandler` và Logback `RollingFileAppender` là **hai hệ thống backend khác nhau**. Chỉ thêm `logback.xml` vào một chương trình dùng JUL thuần không tự làm cho `FileHandler` chuyển sang chính sách Logback; cần định tuyến/bridge/framework phù hợp và có cấu hình được kiểm thử. Tránh tự kết luận thư viện nào cũng hỗ trợ cùng tên tham số và cùng ý nghĩa retention.

## 7. Log4j 2 và chính sách rolling

Với Log4j 2, mô hình thường có `RollingFile` appender và các triggering policy. Ví dụ minh họa cấu trúc cấu hình:

~~~xml
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="AppFile"
                     fileName="logs/application.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="14"/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="AppFile"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Quan trọng:** `DefaultRolloverStrategy max="14"` liên quan đến **giới hạn chỉ số rollover**, không có nghĩa “giữ chính xác 14 ngày”. Muốn kiểm soát retention theo tuổi, tổng dung lượng và số file ở nhiều ngày, cần các delete/retention policy phù hợp với phiên bản Log4j 2. Cần thử cả cách rollover, xóa file và nén sau khi cấu hình, không suy từ tên tham số.

Khi nhiều policy kích hoạt đồng thời, một event có thể nằm gần ranh giới thời gian/kích thước. Hãy kiểm thử việc đặt tên, số generation và dữ liệu ở hai phía điểm rollover. Không áp các ví dụ XML của hai backend cho nhau.

## 8. Công cụ rotation ngoài JVM: rename-create và copytruncate

Trên Linux/Unix, công cụ như `logrotate` có thể được dùng để đổi tên, nén và xóa log file. Tuy nhiên, file đang mở bởi JVM là một vấn đề phải hiểu kỹ.

### 8.1. Rename + create: cần writer reopen

~~~text
Truoc rotation:
  JVM FileHandler -> file descriptor -> /var/log/app.log

OS rename:
  /var/log/app.log -> /var/log/app.log.1
  create new /var/log/app.log

Neu JVM khong reopen:
  JVM van ghi vao descriptor cu (app.log.1)
  file app.log moi co the van trong
~~~

Trên hệ thống kiểu POSIX, việc **rename đường dẫn** không nhất thiết thay đổi file descriptor mà process đang giữ. Vì vậy JVM có thể tiếp tục ghi vào file đã bị đổi tên. Nếu công cụ ngoài xoay file, cần có **cơ chế reopen/reconfigure được hỗ trợ**, hoặc để backend Java tự quản lý rolling. Đừng cho rằng gửi `SIGHUP` đến mọi ứng dụng Java sẽ tự đóng/mở FileHandler — hành vi đó **không được JUL mặc định bảo đảm**.

### 8.2. Copytruncate: vẫn có race

`copytruncate` thường sao chép nội dung sang file archive rồi truncate file active ngay tại chỗ, không yêu cầu writer mở lại đường dẫn. Nhưng giữa bước **copy** và **truncate**, JVM vẫn có thể ghi thêm event. Những byte ở khoảng đó có nguy cơ **không có trong archive và bị mất khi truncate**, hoặc tạo tình huống trùng tùy shipper/cách xử lý. Vì vậy nó là đánh đổi về khả năng giữ descriptor, **không phải phương án bảo toàn log tuyệt đối**.

### 8.3. Chọn đúng một chủ sở hữu rollover

Không nên cấu hình cả Logback/Log4j rolling **và** `logrotate` tự đổi tên/truncate **cùng một file active** mà không có thiết kế rõ ràng. Hai lịch rollover không phối hợp có thể gây rename race, file bị lạc, ghi vào file archive, nén file đang được ghi hoặc shipper bỏ sót dữ liệu.

**Thực hành tốt:** chọn rotation do **logging backend** quản lý hoặc do **OS/runtime** quản lý, rồi đảm bảo writer/shipper tương thích. Nếu chương trình đã ghi stdout/stderr vào container runtime, đừng cố áp logrotate cho file stdout bên trong container như thể đó là cùng đối tượng file.

## 9. Container, Kubernetes và file log

Khi Java chạy trong container, thường khuyến nghị **ghi log vào stdout/stderr** và để container runtime/kubelet, node agent hoặc nền tảng logging quản lý file và rotation bên ngoài. Điều này giúp tránh buộc mọi container phải có persistent volume chỉ để ghi log chẩn đoán.

Tuy nhiên, cần hiểu các ranh giới:

- **stdout trong JVM** → stream của container → file log trên node/runtime → agent/shipper → collector là nhiều bước.
- Runtime/kubelet có thể có cấu hình giới hạn kích thước và số file; đây là **chính sách node/container**, không phải `FileHandler` trong Java.
- File bị xoay/xóa trước khi agent đọc xong có thể gây mất log.
- Một pod bị thay thế hoặc node mất khả năng lưu trước khi chuyển log có thể khiến dữ liệu tại node biến mất.
- Khi một ứng dụng vừa ghi stdout vừa ghi file riêng, agent cần biết nguồn nào được thu thập để tránh **duplicate event**.
- Sử dụng sidecar hoặc volume riêng có thể phù hợp cho một số yêu cầu, nhưng tăng trách nhiệm về dung lượng, lifecycle, retention và quyền truy cập.

Đừng nhầm **pod restart** với **daily rollover**. Một container mới có thể có file mới, trong khi collector vẫn liên kết chúng theo service/pod/request/trace ID; đây là vấn đề quan sát phân tán, không phải một chính sách generation của JVM.

## 10. File shipper phải hiểu rotation như thế nào?

Trong production, file log thường được một agent tail và gửi đi. Một agent đúng cần theo dõi không chỉ **tên đường dẫn**, mà còn file identity/offset/checkpoint theo khả năng của hệ điều hành và thiết kế agent.

Các trường hợp phải xử lý:

| Tình huống | Rủi ro | Yêu cầu kiểm thử |
| --- | --- | --- |
| File active được rename | Shipper có thể tiếp tục tail file cũ hoặc chuyển file mới sai lúc | Không mất phần cuối của file cũ |
| File mới xuất hiện cùng tên active | Checkpoint cũ có thể áp vào file mới sai | Nhận diện file mới và bắt đầu offset phù hợp |
| `copytruncate` làm file nhỏ lại | Offset cũ vượt EOF; dữ liệu trong race có thể mất | Nhận diện truncation, hiểu giới hạn của phương án |
| File archive bị nén ngay | Shipper chưa đọc hết bản gốc | Hoãn nén/giữ file đủ lâu, tránh xóa trước khi đọc |
| Restart agent | Chưa xác nhận đích nhận nhưng đã cập nhật offset | Phục hồi đúng; phân biệt mất và gửi trùng |
| Nhiều file tên gần giống | Glob có thể đọc cả active, archive và bản copy | Chỉ định path/include/exclude rõ |
| Rotation tốc độ cao | File cũ biến mất trước khi agent bắt kịp | Nâng ngưỡng retention/spool hoặc tăng năng lực ship |
| Định dạng multiline/JSON | Ranh giới event có thể bị tách | Parse/ghép đúng schema log |
| Windows file locking | Rename/delete file đang mở có thể bị chặn | Kiểm thử với JVM, shipper và OS thật |

**Checkpoint offset không đồng nghĩa event đã lưu ở collector.** Một số shipper đánh dấu đã đọc trước khi gửi xong; số khác có buffer bền vững hoặc acknowledgment sâu hơn. Cần đọc hợp đồng của agent và thử tình huống crash giữa đọc–gửi–ACK.

### Vì sao nén quá sớm nguy hiểm?

Sau khi rotation, người vận hành có thể muốn `gzip` file cũ ngay để tiết kiệm dung lượng. Nếu shipper vẫn đang đọc file cũ, việc đổi tên/nén/xóa quá sớm có thể khiến agent không hoàn tất phần còn lại. Hãy xác nhận hành vi tailer và chính sách **delay compression** hoặc khoảng đệm đủ dài theo tốc độ vận chuyển thực.

## 11. Tính toán dung lượng và retention

Một chính sách rotation nên được xây dựng từ lượng log thực tế, không chọn 10 MB/7 ngày theo thói quen. Một mô hình ước lượng thô:

~~~text
dungLuongThang = ingestBytesPerDay x soNgayGiu x soReplica
                 x heSoNen (neu archive nen)
                 + duPhong
~~~

Ví dụ bốn replica, mỗi replica tạo 200 MB log/ngày và giữ bảy ngày:

~~~text
200 MB/day x 4 replicas x 7 days = 5600 MB
~~~

Đó là **ước lượng trước nén**, chưa tính burst, chỉ mục/metadata, file active, checkpoint, spool của shipper, bản sao/backup và khoảng trống an toàn. Nếu log có biến động lớn, phải đo mức cao điểm và thêm headroom.

Cần kiểm soát đồng thời:

1. **Max active file size:** tránh một file quá lớn để tail, chuyển và kiểm tra.
2. **Max file count hoặc maxHistory:** giới hạn số thế hệ hoặc chu kỳ lịch sử.
3. **Total size cap:** tránh archive chiếm vô hạn ổ đĩa.
4. **Compression:** giảm dung lượng nhưng tốn CPU/I/O, có thể tạo file tạm.
5. **Backup/central retention:** chính sách ở nơi nhận độc lập với file local.
6. **Disk free threshold:** cảnh báo trước khi đĩa đầy, không đợi `ENOSPC`.
7. **Thời gian backlog của shipper:** file local phải tồn tại đủ lâu để agent gửi khi collector bị gián đoạn.

Một ngưỡng archive 1 GB không phải cam kết toàn bộ filesystem không vượt 1 GB: còn active file, log của service khác, spool và overhead của quá trình rollover/nén.

## 12. Concurrency, nhiều JVM và rotation race

### 12.1. Nhiều thread trong một JVM

Logging backend thường cung cấp các cơ chế đồng bộ/queue cần thiết cho một appender được dùng chung. Tuy nhiên, cấu hình sai nhiều handler vào cùng file có thể sinh ghi trùng, race và format bị đan xen. Nên dùng một đường cấu hình appender rõ ràng và kiểm thử khi có tải đồng thời.

### 12.2. Nhiều process hoặc nhiều replica

Không nên để nhiều JVM/container cùng ghi một file trên shared volume bằng cùng đường dẫn, rồi giả định `FileHandler` hoặc một rolling appender sẽ điều phối rollover an toàn giữa mọi process. Vấn đề gồm:

- Hai process cùng rename/delete/nén file.
- Writer còn giữ descriptor của generation cũ.
- File locking phụ thuộc filesystem/OS; network filesystem có thể có semantics khác.
- `%u` của JUL có thể tạo tên khác nhau khi xung đột, nhưng không biến cả hệ thống thành **multi-process rotation coordinator**.
- Nhiều replica khác nhau có thể có timestamp gần nhau; không thể suy ra thứ tự toàn hệ thống chỉ từ tên file.

Giải pháp thường là **mỗi process/replica có đường log riêng** hoặc ghi stdout rồi để agent/platform thu thập tập trung. Khi cần lưu dài hạn, dùng collector và schema có service, instance, request/trace ID phù hợp để tìm kiếm.

### 12.3. Async appender và shutdown

Với async logging, event có thể còn nằm trong queue khi rollover hoặc shutdown. Hệ thống cần cách drain/flush/close có giới hạn và rõ outcome. Nhưng **shutdown hook không cứu được log khi JVM bị kill cưỡng bức, host mất điện hoặc container hết grace period**.

Một ứng dụng Java gọi `handler.close()` đúng cách trong shutdown có thể giảm rủi ro mất dữ liệu khi thoát bình thường; không thay thế persistent queue, fsync, acknowledgment hoặc kiểm thử sự cố thực tế khi cần độ tin cậy cao.

## 13. Xử lý file đầy, lỗi quyền và các sự cố rotation

| Hiện tượng | Nguyên nhân khả dĩ | Việc cần kiểm tra |
| --- | --- | --- |
| File log tăng mãi không roll | Policy chưa gắn đúng appender; level/path sai | Xem active logger/backend, đường dẫn và trigger |
| Rotate xong vẫn ghi vào `.1` | JVM giữ descriptor cũ sau external rename | Có cơ chế reopen hay không |
| File mới trống sau logrotate | Writer chưa reopen; đang viết inode cũ | So sánh descriptor/inode và ứng dụng |
| Thiếu dòng quanh `copytruncate` | Race copy–truncate | Chuyển sang rolling được phối hợp, kiểm thử lại |
| Log có ít thế hệ hơn mong đợi | Chưa vượt ngưỡng, cleanup, tên file khác | Xem trigger, pattern, startup và quyền |
| Đĩa đầy dù có `maxHistory` | Active file, spool, file khác, archive chưa cleanup | Đo tổng filesystem, disk headroom |
| Không ghi được `.lck` / file | Directory permission, lock collision, disk full | Kiểm tra quyền, process/file handle |
| Appender ngừng ghi âm thầm | Backend có cơ chế báo lỗi riêng, không throw tới caller | Theo dõi internal status/error metrics |
| Dung lượng nén giảm ít | Loại dữ liệu log khó nén hoặc quá nhiều file nhỏ | Đo compression và chi phí CPU |
| Collector thiếu log sau rollover | Tailer offset/file identity sai; archive bị xóa sớm | Test shipper rename/truncate/restart |
| Một event bị lưu hai lần | Đọc cả stdout và file hoặc retry vận chuyển | Phân biệt duplicate producer, shipper, collector |
| Rotation dưới tải làm tăng latency | Nén/I/O/lock chạy trong hot path | Đo p95/p99 và cân nhắc async hoặc shipper |

**Lưu ý JUL:** nhiều lỗi ghi từ `Handler` có thể được báo qua `ErrorManager` hoặc kênh nội bộ thay vì ném exception trực tiếp tới code gọi `logger.info()`. Vì vậy đừng chỉ unit test “logger không throw” rồi kết luận không mất log. Cần quan sát error channel của backend và kiểm chứng file thực.

Khi file rotation gặp lỗi nghiêm trọng, đừng vô hiệu hóa quyền file hoặc cấp `0777` cho thư mục log như giải pháp nhanh. Cần sửa quyền theo nguyên tắc tối thiểu, đồng thời kiểm tra owner của file, thư mục archive và tài khoản chạy service.

## 14. Quyền riêng tư và bảo mật log đã luân chuyển

Rotation có thể tạo thêm **bản sao log ở nhiều trạng thái**: file active, archive nén, backup, file do shipper chuyển, kho tập trung và bản export của dashboard. File cũ vẫn có thể chứa token/PII dù ứng dụng đã sửa lời gọi logger.

Các biện pháp cần thiết:

- **Data minimization tại caller:** tránh log password, token, cookie, raw body, số định danh, thông tin thanh toán không cần thiết.
- **Quyền truy cập:** người ghi file, người đọc archive, agent và quản trị viên không nhất thiết có cùng quyền.
- **Mã hóa truyền/lưu:** khi policy yêu cầu, bảo vệ file/spool/backup và đường tới collector.
- **Retention theo loại log:** debug, security và audit có mục đích khác nhau; không chọn một retention vô hạn cho tất cả.
- **Xóa dữ liệu đúng phạm vi:** xóa file active/backup/central index theo chính sách; rotation cục bộ không tự xóa bản sao khác.
- **Quyền đối với file mới:** kiểm tra `umask`, ownership, group, quyền file khi rollover và khi logrotate `create` file.
- **Nén/archival:** archive nén vẫn chứa nguyên dữ liệu bên trong; không coi `.gz` là mã hóa.
- **Theo dõi truy cập/replay:** các hệ thống cần kiểm toán riêng phải có schema và độ tin cậy phù hợp hơn một rolling file tùy ý.

Đặc biệt, việc đặt mật khẩu hoặc access token vào **tên file log** là không phù hợp; tên file có thể xuất hiện trong process listing, monitor, backup và alert. Các tên dựa trên ngày/instance và nhóm ứng dụng là đủ cho phần lớn use case.

## 15. Kiểm thử rotation trước khi đưa vào production

### 15.1. Test ở cấp formatter/handler

- Sinh đủ số event để chắc chắn vượt ngưỡng (không chỉ phát ba dòng rồi giả định rotation).
- Đóng/flush đúng lifecycle trước khi kiểm tra kết quả.
- Đếm file được tạo, tên theo pattern và kích thước/line count.
- Xác nhận file mới nhất chứa event gần nhất theo chính sách backend.
- Kiểm tra event không bị cắt giữa dòng, log encoding đúng và message nhiều dòng không làm hỏng NDJSON nếu ứng dụng dùng JSON Lines.
- Kiểm tra sau nhiều vòng rollover, file cũ được thay thế/xóa theo retention.
- Đừng assert một kích thước byte tuyệt đối nếu backend cho phép lệch do ranh giới record.

### 15.2. Test tích hợp và fault injection

| Kịch bản | Kết quả cần đánh giá |
| --- | --- |
| Vượt size trong lúc nhiều thread ghi | Không có file hỏng/đan xen; throughput chấp nhận được |
| Qua nửa đêm/timezone boundary | Đặt tên đúng ngày, không mất record |
| Restart ứng dụng giữa chu kỳ | `append`/startup policy đúng; không overwrite ngoài ý muốn |
| Hai JVM cố ghi cùng tên | Cơ chế tách file/lock hoạt động hoặc fail rõ |
| Hết dung lượng đĩa | Phản ứng theo policy và có cảnh báo; không giấu lỗi |
| Directory không có quyền ghi | Backend báo lỗi có thể quan sát |
| Rotate trong lúc agent tail | Không mất phần cuối file cũ, không đọc trùng quá policy |
| Nén khi agent chưa đọc xong | Không xóa file trước khi hoàn tất |
| Collector mất kết nối nhiều giờ | Retention local đủ hoặc đo được số event mất |
| Crash đúng lúc rollover | Phục hồi file/offset đúng mức kỳ vọng |
| Container restart/node bị thay | Hiểu nơi log được lưu và mất ở đâu |
| Log chứa sentinel secret giả | Secret không xuất hiện ngoài kênh được phê duyệt |

**Kiểm tra end-to-end:** tạo event có ID giả, để hệ thống thực xoay file, kiểm tra agent/collector nhận được event đó. Phân biệt số event ở logger, file, shipper và nơi lưu cuối. Đừng tuyên bố “không mất log” chỉ vì trên đĩa hiện còn ba thế hệ.

### 15.3. Những chỉ số vận hành nên theo dõi

- Dung lượng đĩa trống và tốc độ tăng log (byte/s).
- Kích thước active file, số file archive, tổng dung lượng archive.
- Lần rollover gần nhất, lỗi rollover/nén/xóa archive.
- Số log event bị drop do queue/appender/collector.
- Độ trễ/backlog của file shipper và tuổi event cũ nhất chưa gửi.
- Tốc độ ghi log bất thường, spike khi bật `DEBUG`/`TRACE`.
- Số lần process restart, thời gian log không được ghi và các lỗi quyền/disk full.

Không dùng **địa chỉ request, event ID cá nhân hoặc tên file thay đổi theo mỗi request** làm metric label vì sẽ tạo cardinality rất cao. Dùng service, instance, reason code và outcome đã chuẩn hóa.

## 16. Những hiểu nhầm cần tránh

**“Có rotation là không thể đầy đĩa.”** Sai. Nhiều ứng dụng, file spool, file active, nén tạm hoặc archive chưa cleanup vẫn có thể chiếm toàn bộ filesystem.

**“`FileHandler(count=3)` giữ ba bản backup cộng file active.”** Sai. `count` là số thế hệ trong chu kỳ, thường **bao gồm file active**.

**“Logrotate rename file, JVM tự động ghi sang file mới.”** Không có bảo đảm. Phải kiểm tra reopen/file descriptor hoặc dùng backend rolling phối hợp.

**“Dùng `copytruncate` là không bao giờ mất log.”** Sai. Có race giữa copy và truncate.

**“Nén archive là đã mã hóa an toàn.”** Sai. Gzip chỉ nén, không bảo vệ bí mật.

**“File local đã roll/xóa thì log ở collector cũng hết.”** Sai. Central retention, backup và export là các chính sách khác.

**“Một dòng `logger.info` không throw nghĩa log đã ghi được.”** Không luôn đúng. Handler/backend có thể xử lý lỗi I/O riêng, queue có thể drop hoặc exporter chưa gửi thành công.

**“Cứ để mọi replica cùng ghi `/shared/app.log` cho dễ xem.”** Không an toàn mặc định. Multi-process rotation/locking trên shared volume cần cơ chế được thiết kế riêng.

**“Rotation dùng để đảm bảo audit không mất.”** Sai. Audit cần bổ sung quyền, integrity, durability, retention và các xác nhận phù hợp mục đích.

## 17. Checklist thực hành

- [ ] Quyết định rõ stdout/stderr hay file cục bộ là nguồn chính của log.
- [ ] Chỉ định một bên chịu trách nhiệm rotation ở mỗi file active.
- [ ] Chọn size/time/both phù hợp lượng log và peak load.
- [ ] Cấu hình dung lượng, số generation/chu kỳ lịch sử và total archive cap.
- [ ] Phân biệt rotation, compression, archival, retention và collection.
- [ ] Khi dùng JUL, hiểu `FileHandler(pattern, limit, count, append)` và token `%g`, `%u`.
- [ ] Khi dùng Logback/Log4j 2, kiểm tra policy đúng backend/phiên bản và tên file active/archive.
- [ ] Không dùng external rename mà thiếu reopen; hiểu rủi ro `copytruncate`.
- [ ] Kiểm thử ứng dụng nhiều thread/process, restart và log volume cao.
- [ ] Kiểm thử file shipper offset/checkpoint khi rename, truncate, nén, xóa.
- [ ] Giám sát disk free, file count, archive size, rotate failures, drop và shipper backlog.
- [ ] Phân quyền file và archive, bảo vệ PII, thiết lập retention cho mọi bản sao.
- [ ] Không phụ thuộc shutdown hook/rotation làm bảo đảm audit durability.

### Tự kiểm tra kiến thức

**Câu 1.** `FileHandler(pattern, 1024, 3, false)` có nghĩa giữ ba bản backup bên cạnh file active?  
**Đáp:** Không. `count=3` là ba file trong chu kỳ rotation, bao gồm file đang ghi.

**Câu 2.** Nếu JVM vẫn giữ descriptor sau khi `logrotate` rename, log sẽ đi đâu?  
**Đáp:** Trên filesystem kiểu POSIX, JVM có thể tiếp tục ghi vào file đã đổi tên cho đến khi reopen.

**Câu 3.** `copytruncate` có tuyệt đối tránh mất log không?  
**Đáp:** Không. Các record ghi giữa lúc copy và truncate có thể bị mất.

**Câu 4.** File đã nén `.gz` có an toàn như file được mã hóa không?  
**Đáp:** Không. Nén không cung cấp tính bí mật.

**Câu 5.** Trong container chỉ dùng stdout, Java có bắt buộc dùng `FileHandler` không?  
**Đáp:** Không. Nền tảng container/shipper có thể quản lý file bên ngoài JVM; ứng dụng vẫn cần schema và observability phù hợp.

**Câu 6.** Vì sao giữ file local ba ngày không chứng minh log ở central store cũng được giữ đúng ba ngày?  
**Đáp:** Vì mỗi hop có retention, backup và chính sách xóa riêng.

**Câu 7.** Đã đếm đúng ba file trong thư mục, có thể kết luận mọi event đến collector?  
**Đáp:** Không. Cần kiểm thử shipper, ACK/offset và dữ liệu ở nơi lưu cuối.

**Ghi nhớ:** Luân chuyển file là một phần của **vận hành logging**, giúp quản lý kích thước và vòng đời log. Trong Java, `FileHandler` hỗ trợ xoay theo byte và số thế hệ; Logback/Log4j 2 có rolling policy phong phú hơn. Nhưng hệ thống đáng tin còn cần phối hợp writer với OS/runtime và shipper, chính sách retention, quyền riêng tư, khả năng quan sát khi disk full, và kiểm thử end-to-end không mất hoặc nhân đôi dữ liệu ngoài mức chấp nhận được.
