# Dự án thực hành: Thiết lập rotation cho log file trong Java 17

## 1. Mục tiêu của bài thực hành

Trong dự án này, bạn sẽ **thiết lập luân chuyển file log (log rotation)** cho một ứng dụng Java, tạo đủ log để buộc quá trình rollover diễn ra, rồi **tự kiểm chứng** tên file, số thế hệ, khả năng giữ log mới và giới hạn lưu trữ. Sau bản chạy tối thiểu bằng thư viện có sẵn của Java, bài học mở rộng cách đưa chính sách đó vào dịch vụ dùng Logback, phối hợp với log shipper và kiểm tra các rủi ro production.

Kết quả mong đợi không chỉ là “có file log” mà là có thể trả lời được:

1. **Khi nào file đang ghi được luân chuyển?** Theo kích thước, thời gian hoặc cả hai.
2. **File active và file cũ có tên gì?** Biết file nào chứa dữ liệu mới.
3. **Đã giới hạn số lượng/tuổi/dung lượng file chưa?** Rotation và retention là hai quyết định có liên quan nhưng khác nhau.
4. **Khi collector không hoạt động, log có bị xóa trước khi được đọc không?**
5. **Khi JVM restart hoặc nhiều instance cùng chạy, có ghi đè, mất hoặc nhân đôi log ngoài ý muốn không?**
6. **Khi disk đầy hoặc không có quyền ghi, hệ thống có tín hiệu lỗi quan sát được không?**

Bài lab chính dùng **JDK 17 trở lên**, `java.util.logging.FileHandler` và một file Java duy nhất; **không cần Maven, Spring hay dịch vụ bên ngoài**. Cấu hình Logback ở phần sau là **bước mở rộng** dành cho dự án thực có Logback; không áp dụng trực tiếp cho chương trình JUL thuần.

### Điều kiện hoàn thành

- [ ] Biên dịch và chạy được ví dụ Java 17.
- [ ] Có **ba** thế hệ file sau khi tạo đủ log để xoay nhiều lần.
- [ ] Sự kiện có sequence mới nhất vẫn hiện diện trong các file đang giữ.
- [ ] Những sự kiện cũ hơn giới hạn retention theo số file đã bị thay thế.
- [ ] Hiểu vì sao `count=3` không có nghĩa “file active + ba bản backup”.
- [ ] Có chính sách khi rotate, xóa/nén file và khi agent đọc file chậm.
- [ ] Có checklist kiểm thử restart, disk full, quyền file và collector outage.

## 2. Bối cảnh và kiến trúc lab

Giả sử có một service quản lý tồn kho ghi sự kiện chẩn đoán như sau:

~~~text
event=inventory_checked seq=001 outcome=OK
event=inventory_checked seq=002 outcome=OK
...
~~~

Nếu ghi vào một file mãi mãi, file có thể phình lớn và làm đầy filesystem. Ta muốn **file đang ghi được xoay khi vượt ngưỡng**, và chỉ giữ một số thế hệ gần nhất để dùng trong môi trường phát triển.

~~~text
Inventory service
      |
      v
JUL Logger
      |
      v
FileHandler
      |
      +--- app-0.log   (generation active theo JUL)
      +--- app-1.log   (thế hệ trước)
      +--- app-2.log   (thế hệ cũ hơn)
      |
      +--- file cũ hơn bị thay thế sau các lần rollover
~~~

Trong lab, mỗi lần chạy dùng một **thư mục tạm mới**, nhằm tránh xung đột với log đang có. Giá trị cấu hình được cố ý để nhỏ:

| Thuộc tính | Giá trị lab | Vì sao |
| --- | --- | --- |
| JDK | Java 17+ | Dùng API tiêu chuẩn, không cần dependency |
| Limit | 512 byte | Dễ kích hoạt rollover với vài chục dòng |
| Count | 3 | Dễ quan sát giới hạn ba thế hệ |
| Append | `false` | Không nối vào một chu kỳ file cũ từ lần chạy trước |
| Pattern | `app-%g.log` | Tạo tên theo generation number |
| Log generated | 100 event | Vượt xa tổng sức chứa ba file |
| Log level | `INFO` | Các sự kiện mô phỏng là thông tin thông thường |
| Encoding | UTF-8 | Tránh phụ thuộc charset mặc định |
| Output kiểm tra | Bốn dòng stdout | Không phụ thuộc đường dẫn tạm và timestamp |

**Không dùng cấu hình 512 byte và ba file cho production.** Đây là thông số phục vụ kiểm thử rollover; ứng dụng thật phải tính theo byte/s, độ trễ shipper, thời gian giữ và filesystem capacity.

## 3. Chuẩn bị môi trường

Cần có JDK 17 trở lên và quyền tạo file trong thư mục tạm mặc định của hệ điều hành.

Kiểm tra:

~~~bash
java -version
javac -version
~~~

Trong một thư mục thực hành, tạo file:

~~~text
rotation-lab/
└── RotationLab.java
~~~

Các bước tạo/chạy trên macOS hoặc Linux:

~~~bash
mkdir rotation-lab
cd rotation-lab
# Tạo file RotationLab.java từ mã nguồn ở phần 4.
javac RotationLab.java
java RotationLab
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory rotation-lab
Set-Location rotation-lab
# Tạo file RotationLab.java từ mã nguồn ở phần 4.
javac RotationLab.java
java RotationLab
~~~

`javac` tạo bytecode `RotationLab.class` và các class phụ do compiler sinh ra. Chạy bằng `java RotationLab` sử dụng classpath hiện tại trong một dự án nhỏ không khai báo package. Nếu cấu hình môi trường có module/package hoặc chạy qua IDE, điều chỉnh đường dẫn theo dự án thực.

**Không cần quyền administrator/root.** Nếu thư mục tạm không cho phép tạo file, bài test phải thất bại có nguyên nhân rõ; không nên cấp quyền toàn filesystem chỉ để chạy lab.

## 4. Viết chương trình Java 17 thực sự xoay file

Tạo **`RotationLab.java`**, nội dung đầy đủ:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RotationLab {
    private static final int LIMIT_BYTES = 512;
    private static final int FILE_COUNT = 3;
    private static final int EVENTS = 100;

    public static void main(String[] args) throws Exception {
        // Thu muc rieng cho moi lan chay: tranh trung ten/ghi de.
        Path directory = Files.createTempDirectory("rotation-lab-");

        Logger logger = Logger.getLogger("lab.rotation.inventory");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        // %g la generation trong tap file cua FileHandler.
        String pattern = directory.resolve("app-%g.log").toString();
        FileHandler handler = new FileHandler(
                pattern, LIMIT_BYTES, FILE_COUNT, false);

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
                String message = String.format(
                        Locale.ROOT,
                        "event=inventory_checked seq=%03d outcome=OK",
                        i);
                logger.info(message);
            }
        } finally {
            // Dong file, flush buffer, giai phong file lock.
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        int found = 0;
        long retainedEvents = 0;
        boolean newestPresent = false;

        for (int gen = 0; gen < FILE_COUNT; gen++) {
            Path path = directory.resolve("app-" + gen + ".log");
            if (!Files.isRegularFile(path)) {
                continue;
            }

            found++;
            List<String> lines = Files.readAllLines(
                    path, StandardCharsets.UTF_8);
            retainedEvents += lines.size();

            for (String line : lines) {
                if (line.contains("seq=100")) {
                    newestPresent = true;
                }
            }
        }

        boolean oldEventsRemoved = retainedEvents < EVENTS;

        if (found != FILE_COUNT ||
                !oldEventsRemoved ||
                !newestPresent) {
            throw new IllegalStateException(
                    "Rotation verification failed");
        }

        System.out.println("generated=100");
        System.out.println("rotationFiles=3");
        System.out.println("oldEventsRemoved=true");
        System.out.println("newestEventPresent=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RotationLab.java
java RotationLab
~~~

**Stdout chính xác trong lần chạy thành công** với JDK 17+ và filesystem cho phép tạo/ghi/đổi tên file:

~~~text
generated=100
rotationFiles=3
oldEventsRemoved=true
newestEventPresent=true
~~~

**Stderr:** không có nội dung trong đường chạy thành công. Thư mục log được tạo trong thư mục tạm với một hậu tố ngẫu nhiên; chương trình **không in đường dẫn đó**, để stdout luôn cố định.

### Vì sao kết quả có thể xác định?

- 100 log event dài hơn tổng dung lượng của ba file 512 byte, nên đã có nhiều lần rollover.
- Pattern có token `%g`, vì vậy các file của lab thông thường mang tên `app-0.log`, `app-1.log`, `app-2.log`.
- Ba thế hệ gần nhất không thể chứa toàn bộ 100 event; biến `oldEventsRemoved` thành `true`.
- Event `seq=100` được phát cuối cùng, nên phải còn trong thế hệ được giữ lại nếu handler ghi thành công.
- Formatter không thêm timestamp hoặc tên thread ngẫu nhiên; stdout chỉ là báo cáo kiểm thử, không in tên thư mục.

Đây là **kiểm chứng cơ bản** cho vòng đời file trong lab. Nếu hệ thống đang dùng filesystem lạ, thư mục tạm không đủ quyền hoặc handler không thể ghi, chương trình có thể báo lỗi hoặc ném exception; khi đó không được coi là kết quả thành công.

### Giới hạn của chương trình

- Không có nén `.gz`, retention theo ngày hoặc collector.
- Chưa xác nhận mọi event được lưu lâu dài: bài lab cố ý chứng minh event cũ bị thay thế.
- FileHandler được tạo và ghi trong một JVM đơn tiến trình; chưa kiểm tra nhiều JVM cùng dùng một đường dẫn.
- Formatter đang dùng chuỗi `event=...`, không phải JSON. Khi production dùng NDJSON, cần JSON encoder đảm bảo escape và một event trên mỗi dòng.
- Vì không có code xử lý lỗi I/O ở `ErrorManager`, việc `logger.info()` không throw **không tự chứng minh** từng ghi file thành công; lab đọc lại file sau khi đóng handler.
- Mặc dù Java có thể giữ handle đến file, FileHandler chịu trách nhiệm đóng/mở trong chính cơ chế rotation của nó; việc một công cụ bên ngoài đổi tên file vẫn có thể gây vấn đề khác.

## 5. Đọc và giải thích các file sau rotation

Sau khi đóng `FileHandler`, bạn có thể tạm sửa lab để in `directory.toAbsolutePath()` trong **một lần chạy điều tra** nếu muốn biết đường dẫn chính xác. Không thêm lệnh in đó vào phiên bản dùng để so sánh stdout phía trên, vì đường dẫn thay đổi giữa các lần.

Hoặc thay `Files.createTempDirectory(...)` bằng một thư mục riêng trong dự án đã được cấp quyền, ví dụ `Path.of("lab-logs")` và `Files.createDirectories(directory)` khi muốn tự quan sát bằng trình duyệt file. Lưu ý phải **đổi tên hoặc xóa dữ liệu demo cũ có chủ đích** trước mỗi lần chạy; không được xóa thư mục log dùng chung với service thật.

Bảng ý nghĩa các thế hệ JUL:

| Đường dẫn | Ý nghĩa thông thường |
| --- | --- |
| `app-0.log` | Generation đang hoạt động/gần nhất |
| `app-1.log` | Generation trước đó |
| `app-2.log` | Generation cũ hơn còn được giữ |
| `app-3.log` | Không nằm trong chính sách `count=3` của lab |

Khi file active vượt ngưỡng, FileHandler có thể đổi thế hệ các file. File đã cũ hơn số thế hệ được cấu hình bị thay thế. Vì vậy:

- Không mong `app-2.log` luôn có ngày tạo cũ hơn chính xác bao nhiêu phút; rollover phụ thuộc tốc độ log.
- Không dùng `File.lastModified()` như bằng chứng duy nhất về thứ tự sự kiện giữa nhiều máy.
- Không coi `count=3` là **ba backup cộng active**. Nó là **tổng số thế hệ**.
- Không mong mọi file có kích thước **chính xác** 512 byte; record được ghi theo đợt, nên có thể vượt giới hạn tại thời điểm kích hoạt.
- Không dựa vào việc xem file active mà kết luận collector đã nhận đầy đủ.

Nếu muốn kiểm thử chi tiết hơn, hãy parse số sequence từ từng dòng, phân biệt file active và archive, xác minh chúng chỉ chứa chuỗi dạng cho phép; sau đó so các sequence với một nguồn dữ liệu kiểm thử độc lập để xác định phạm vi bị giữ/xóa. Tuy nhiên, **không kỳ vọng còn đủ cả 100 event**, vì retention trong lab cố ý thấp.

## 6. `FileHandler` thực sự kiểm soát tham số nào?

API JDK có constructor:

~~~java
FileHandler(String pattern, int limit, int count, boolean append)
~~~

Các giá trị chính:

| Tham số | Ý nghĩa và lưu ý |
| --- | --- |
| `pattern` | Mẫu tên file; có thể chứa token như `%g`, `%u` |
| `limit` | Ngưỡng kích thước **byte** dùng cho rotation, không phải số dòng |
| `count` | Tổng số file trong chu kỳ rotation của handler, gồm file active |
| `append` | Khi mở file, chọn nối vào file đang tồn tại hoặc bắt đầu lại theo policy |

Các token đặt tên thường gặp:

- `%g`: generation number của file đang nằm trong chu kỳ.
- `%u`: unique number giúp giải quyết một số va chạm tên/lock.
- `%t`: thư mục tạm của hệ điều hành/JVM.
- `%h`: home directory của tài khoản.
- `%%`: một ký tự `%` thực.

Ví dụ:

~~~text
logs/service-%g-%u.log
~~~

**`%u` không phải user ID, process ID hay request ID**, và không bảo đảm nhiều JVM chia sẻ an toàn cùng một file active. Số unique và lock behavior phụ thuộc môi trường; hãy cấp đường dẫn hoặc instance identity riêng cho từng process khi cần.

JUL `FileHandler` thích hợp để học **rotation theo size và số thế hệ**. Nó không cung cấp một time-based rolling policy phong phú như một số backend chuyên dụng. Nếu bài toán cần daily/hourly rollover, nén archive và xóa theo tuổi, nên dùng backend hoặc hạ tầng hỗ trợ cấu hình ấy và kiểm thử trên phiên bản thực.

### Cấu hình JUL bằng file properties (mở rộng)

Ngoài cách tạo `FileHandler` trực tiếp trong code, JUL có thể được cấu hình từ file `logging.properties`. Ví dụ phần cấu hình:

~~~properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.pattern=logs/app-%g.log
java.util.logging.FileHandler.limit=10485760
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
~~~

Trong một ứng dụng mà `LogManager` nạp file này ngay lúc JVM khởi động, có thể chạy với system property:

~~~bash
java -Djava.util.logging.config.file=logging.properties MainClass
~~~

**Đoạn này là công thức tích hợp**, không phải lệnh chạy trực tiếp cho `RotationLab.java` ở phần 4; chương trình lab **tự gắn FileHandler riêng** và tắt parent handlers, nên nó không sử dụng FileHandler từ root logger theo cách của ví dụ properties. Để dùng properties cho service thực, đặt class ứng dụng thay `MainClass`, đảm bảo thư mục `logs/` đã tồn tại và có quyền ghi.

Chỉ chọn **một đường cấu hình FileHandler cho cùng mục đích**. Nếu vừa dùng root FileHandler từ `logging.properties` vừa tự gắn handler tại một logger có parent enabled, event có thể bị ghi trùng hoặc phân tán sang nhiều file ngoài ý định.

## 7. Khi nào nên chuyển sang Logback rolling policy?

Nhiều dự án Java dùng SLF4J với Logback, thay vì JUL trực tiếp. Một cấu hình Logback theo thời gian kết hợp kích thước có thể có:

- File active ổn định, ví dụ `application.log`.
- Archive theo ngày và chỉ số khi vượt ngưỡng trong ngày.
- Nén `.gz` file cũ.
- Giới hạn số chu kỳ lịch sử và tổng dung lượng archive.

Đặt file dưới tên **`logback.xml`** trong classpath resource của một dự án **đã có Logback làm logging backend**:

~~~xml
<configuration>
  <property name="LOG_DIR" value="./logs"/>

  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>${LOG_DIR}/application.log</file>

    <rollingPolicy
      class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>${LOG_DIR}/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
      <maxFileSize>10MB</maxFileSize>
      <maxHistory>7</maxHistory>
      <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

**Lưu ý:** đây là cấu hình **mở rộng**, không phải file cần tạo để chạy `RotationLab.java`. Nó yêu cầu dependency/config tương thích với phiên bản Logback đang dùng. Dự án cần xác nhận XML được parser chấp nhận và thử rollover trên chính backend đó; Logback và JUL không tự thay thế cho nhau.

Ý nghĩa:

- `<file>`: đường dẫn file đang ghi.
- `fileNamePattern` có `%d` theo ngày và `%i` theo chỉ số trong cùng chu kỳ.
- `.gz`: yêu cầu nén file archive theo khả năng rolling policy.
- `maxFileSize=10MB`: ngưỡng rollover theo dung lượng trong cùng ngày.
- `maxHistory=7`: số **chu kỳ lịch sử** được giữ; khi pattern theo ngày, không được giải thích như “bảy file”.
- `totalSizeCap=1GB`: trần tổng dung lượng archive do cleanup policy quản lý; không phải giới hạn cứng cho toàn bộ filesystem.

Cấu hình thư mục `./logs` chỉ phù hợp khi deployment có filesystem tồn tại và quyền ghi. Trong production, dùng đường dẫn do đội vận hành cấp, bảo đảm thư mục được tạo/giám sát, và kiểm thử khi deploy trên container, VM hoặc shared storage.

**Nếu dùng structured JSON log**, cần encoder JSON phù hợp thay pattern text bên trên và kiểm thử NDJSON/escaping. **Đừng thay `%msg%n` bằng nối chuỗi JSON thủ công**: input chứa dấu nháy, newline hoặc backslash có thể phá cú pháp và log shipper.

## 8. Không trộn nhiều cơ chế rotation trên cùng file

Một service có thể chịu rotation ở nhiều tầng:

~~~text
Application -> stdout
                 |
                 v
        Container runtime logs
                 |
           runtime rotation
                 |
               shipper
                 |
              collector
~~~

hoặc:

~~~text
Application -> RollingFileAppender
                        |
                        v
                  application.log
                        |
                        v
                     shipper
                        |
                        v
                     collector
~~~

Nếu một ứng dụng đã để Logback xoay `application.log`, cấu hình thêm công cụ OS `logrotate` để rename/truncate **chính file đó** có thể xung đột. Hãy quyết định **một thành phần chịu trách nhiệm rotation file active**; nếu phải phối hợp các thành phần, cần một hợp đồng rõ về reopen, rename và checkpoint.

### Rename-create

Trên hệ thống kiểu POSIX, nếu công cụ ngoài đổi tên `application.log` thành `application.log.1` rồi tạo file `application.log` mới, **file descriptor mà JVM đang giữ vẫn có thể trỏ tới file cũ**. Khi ấy JVM tiếp tục ghi file archive và file active mới trống cho tới khi writer reopen đúng cách.

Không mặc định rằng mọi ứng dụng Java nhận `SIGHUP` sẽ tự mở lại log file; cần cơ chế được backend/framework hỗ trợ và kiểm thử.

### Copytruncate

Với `copytruncate`, công cụ bên ngoài sao chép file sang archive rồi truncate file active tại chỗ. Nó tránh yêu cầu reopen tức thì, nhưng có **race giữa sao chép và truncate**: các byte được viết trong khoảng đó có thể bị mất. Vì vậy `copytruncate` không phải giải pháp bảo toàn log tuyệt đối.

**Trong container:** nhiều hệ thống chọn ghi stdout/stderr và để runtime/node agent xoay log; ứng dụng không phải tự quản lý rolling file. Nhưng stdout ghi thành công **không chứng minh collector đã lưu**. Có thể mất log do runtime xoay/xóa trước khi shipper đọc kịp.

## 9. Rotation không phải retention, nén hay backup

Bốn khái niệm:

| Thành phần | Việc thực hiện | Chưa tự giải quyết |
| --- | --- | --- |
| Rotation | Chuyển từ file active sang thế hệ mới | Không bảo đảm log được lưu lâu |
| Retention | Giữ/xóa theo tuổi, số file hoặc dung lượng | Không chứng minh đã ship log |
| Compression | Giảm kích thước archive, ví dụ `.gz` | Không mã hóa nội dung |
| Archival/backup | Lưu sang vị trí khác | Cần chính sách vòng đời và quyền đọc riêng |

`FileHandler(count=3)` của lab thực hiện **rotation cùng giới hạn số thế hệ**, nhưng không có chính sách “xóa sau 30 ngày” hoặc nén. Logback có thêm các chính sách thời gian/dung lượng, nhưng cũng phải đo đạc và giám sát.

**Ước tính capacity trước khi đặt retention:** lấy byte/s hoặc GB/ngày của service, nhân số instance và khoảng lưu cần thiết. Thêm dung lượng cho active file, peak burst, compression tạm, file spool của shipper, metadata và headroom. Một archive cap không bao gồm mọi dữ liệu trên đĩa.

Ví dụ một instance phát log trung bình 20 MB/giờ; giữ local 24 giờ cần khoảng 480 MB **trước nén**, chưa tính peak và các file khác. Nếu collector có thể ngừng nhận dữ liệu trong 48 giờ, retention local 24 giờ **có nguy cơ xóa log trước khi gửi được**. Phải dựa vào SLO khôi phục/shipper backlog thực tế, không chỉ đặt count cho đẹp.

### Retention ở collector là chuyện khác

Xóa archive cục bộ sau bảy ngày **không xóa** bản sao tại central store, backup hoặc alert export. Ngược lại, giữ log ở central 30 ngày không giúp khôi phục file local nếu shipper chưa từng chuyển event. Quyền truy cập và data retention phải được đặt ở **mọi hop lưu trữ**.

## 10. Phối hợp với file shipper khi rollover

Trong production, một file agent thường theo dõi `application.log`, nhớ file identity/offset rồi chuyển event đến collector.

| Tình huống | Rủi ro | Cách kiểm tra |
| --- | --- | --- |
| File active bị rename | Shipper còn đọc file cũ hoặc bỏ sót phần cuối | Tail hết file cũ trước khi bỏ |
| File mới dùng lại tên active | Offset cũ áp vào file mới | Shipper phát hiện file mới theo identity |
| File bị truncate | Offset vượt EOF hoặc mất dữ liệu ở race | Test truncation/recovery |
| Archive nén ngay sau rollover | Agent chưa đọc hết file cũ | Chậm nén/xóa hoặc tăng khả năng ship |
| Rotation liên tục dưới peak | Thế hệ cũ mất trước khi agent bắt kịp | Tăng retention/spool hoặc nâng throughput |
| Agent restart sau khi đã đọc nhưng chưa ACK | Mất hoặc gửi trùng event | Kiểm tra checkpoint và delivery semantics |
| Glob thu cả active và archive | Một event có thể bị đọc hai lần | Thiết lập include/exclude, điều kiện file |
| JSON multiline | Một event bị tách thành nhiều record | Dùng NDJSON hoặc multiline parser đúng |

**Offset đã đọc không tự động bằng event đã được collector ACK.** Một số agent có persistent queue, một số chỉ có checkpoint cục bộ; độ tin cậy phải được đánh giá theo hợp đồng của agent thực, không dựa vào FileHandler.

**Rủi ro duplicate:** nếu agent đọc lại file sau rename/restart hoặc exporter retry khi ACK bị mất, cùng event có thể xuất hiện hai lần. Nếu cần dedupe, phát `eventId` ổn định và dùng quy tắc nhận phù hợp; “ghi một lần trong Java” không tự bảo đảm exactly-once tới collector.

### Một thử nghiệm end-to-end đơn giản

Trong môi trường test có agent/collector:

1. Ghi log event với một `eventId` giả duy nhất.
2. Tăng volume để bắt buộc xoay file.
3. Chờ agent xử lý với cơ chế quan sát có timeout, không dựa vào `sleep` cố định như bảo đảm.
4. Tìm `eventId` tại collector và so số lượng.
5. Restart agent sau khi file đã rename; kiểm tra event không mất ngoài chính sách.
6. Cho collector tạm ngừng nhận, kiểm tra queue/backlog và khả năng event cũ bị xóa.
7. Ghi nhận giới hạn: at-most-once, at-least-once, dedup hay best effort.

## 11. Những trường hợp lỗi cần thử

Một bản cấu hình hoạt động khi môi trường khỏe chưa đủ. Dự án phải thử cả các đường lỗi:

| Kiểm thử | Kỳ vọng và tiêu chí |
| --- | --- |
| Vượt size nhiều lần | Có rollover, số file không tăng vô hạn |
| Restart giữa chu kỳ | Append/overwrite đúng policy, không làm mất dữ liệu ngoài ý định |
| Thư mục không có quyền ghi | Có lỗi rõ hoặc status/metric từ backend, không giả định đã ghi |
| Disk full | Ứng dụng và logging backend có hành vi được định nghĩa |
| Hai JVM cùng ghi một đường dẫn | Không trộn dữ liệu/đua rename; nên tách file/instance |
| Chạy trong thread pool | Không corrupt log và không rò MDC/context nếu dùng |
| Vừa rollover vừa tail | Agent đọc đủ phần đuôi file trước khi xóa |
| Nén/archive quá sớm | Không xóa file khi shipper chưa đọc hết |
| Application bị kill cưỡng bức | Biết rủi ro mất buffer/unflushed log |
| Collector down nhiều giờ | Backlog/retention theo SLO, đo được drop count |
| Bật `DEBUG` ở traffic cao | Disk headroom và rolling policy vẫn chịu được |
| File/path có dấu Unicode hoặc không hợp lệ | Đường dẫn/charset được xử lý hoặc fail có kiểm soát |
| Message chứa newline | Khi dùng JSON, mỗi event vẫn parse được đúng NDJSON |
| Secret giả trong log message | Không xuất token/password ngoài allowlist |

### Gợi ý kiểm thử disk-full và quyền file an toàn

**Không cố làm đầy filesystem thật của máy production.** Dùng volume thử nghiệm có quota/giới hạn nhỏ hoặc filesystem sandbox riêng. Bắt đầu bằng mô phỏng quota, yêu cầu ghi quá giới hạn và quan sát error channel của logging backend. Trước khi dọn file, xác minh chính xác path lab để không xóa nhầm dữ liệu của service khác.

**Không sửa permission của thư mục dùng chung** để gây lỗi trong môi trường thật. Tạo thư mục test riêng; thay đổi quyền chỉ trong phạm vi được phép. Không dùng giải pháp “chmod 777” hoặc chạy service bằng root chỉ để FileHandler ghi được.

Với JUL, lỗi I/O ở handler có thể được chuyển tới `ErrorManager` hoặc cơ chế chẩn đoán của logging backend thay vì ném trực tiếp tới caller. Vì vậy phải kiểm tra **file thực, lỗi backend và metric/drop**, không chỉ assert `logger.info()` không throw.

## 12. Cách chọn chính sách cho production

Đừng sao chép `512 byte, count=3` của lab. Hãy lập chính sách triển khai:

| Trường | Câu hỏi khi cấu hình |
| --- | --- |
| `logSource` | stdout, file hay cả hai? có tạo duplicate không? |
| `rotationOwner` | JUL/Logback/Log4j2, logrotate hay container runtime? |
| `trigger` | size, time hoặc size+time? |
| `maxFileSize` | Dựa trên peak log rate và khả năng tail/ship? |
| `maxHistory` / `count` | Giữ trong bao nhiêu giờ/ngày hoặc bao nhiêu thế hệ? |
| `totalSizeCap` | Đã tính cả active, spool, compression và headroom chưa? |
| `compression` | Có tương thích tốc độ đọc file của agent không? |
| `privacy` | Log có PII/secret? quyền đọc và retention tại mọi đích? |
| `failureMode` | Khi disk full/collector down, block, drop hay fail closed? |
| `shutdown` | Có flush/drain trong thời gian cho phép? |
| `monitoring` | Disk free, archive size, rotate failure, shipper lag, drop count? |

### Một chính sách ví dụ, không phải mặc định

Với một service trên VM có file log riêng, có thể bắt đầu bằng **active file 10 MB**, archive size+time theo ngày, giữ **bảy chu kỳ lịch sử**, có tổng archive cap và agent gửi tới central store. Tuy nhiên, nếu tốc độ log lớn hoặc collector có thể mất kết nối lâu, thông số này có thể hoàn toàn không đủ. Phải kiểm tra dữ liệu vận hành, tăng headroom và phê duyệt retention.

Với container có pipeline stdout đầy đủ, có thể **không cần FileHandler**: dùng JSON encoder ra stdout, để runtime chịu trách nhiệm rotation và shipper chịu trách nhiệm buffer/retry. Vẫn phải kiểm chứng giới hạn file trên node và thời điểm agent đọc; “stdout là đủ” chỉ đúng khi toàn pipeline được cấu hình và vận hành phù hợp.

## 13. Security, privacy và file permissions

Rotation tạo thêm các bản sao: active file, archive, file nén, spool của shipper, central store và backup. Những bản này có thể giữ **thông tin nhạy cảm** ngay cả khi ứng dụng đã sửa code không log dữ liệu ấy nữa.

- Chỉ log dữ liệu theo allowlist: event code, severity, request/trace ID có kiểm soát, outcome, error code.
- Không ghi password, access token, cookie, OTP, raw payment details, DTO/body không cần thiết.
- Đặt quyền thư mục/file cho đúng service account và agent; hạn chế quyền đọc archive.
- Gzip chỉ **nén**, không mã hóa. Nếu cần bảo mật nội dung, dùng encryption phù hợp và quản lý khóa.
- Rotation và retention không xóa tự động bản sao ở collector/backup.
- Không log URL/query có token hoặc raw exception message có thể chứa PII.
- Khi test, dùng sentinel bí mật **giả**, không dùng credential thật.
- Không ghi file logs vào thư mục có thể được static web server phục vụ công khai.
- Với nhiều tenant, chỉ ghi tenant reference tối thiểu khi thật sự cần, tránh tách file theo ID user tùy tiện.

**Lưu ý về timestamp/ID:** một request ID không phải tên người dùng, nhưng vẫn có thể liên kết với cá nhân thông qua các log khác. Retention và phân quyền vẫn cần xét ngữ cảnh dữ liệu.

## 14. Checklist triển khai và bàn giao lab

### Kiểm tra code lab

- [ ] Có JDK 17+, file `RotationLab.java` biên dịch được bằng `javac`.
- [ ] Chạy thành công, stdout gồm đúng bốn dòng đã nêu.
- [ ] Có `app-0.log`, `app-1.log`, `app-2.log` dưới thư mục tạm của lần chạy.
- [ ] `seq=100` còn được giữ; số event trong file ít hơn 100 do policy count thấp.
- [ ] Handler được `flush()`, `close()` và tháo khỏi logger ở `finally`.
- [ ] Không dùng `System.out.println` để giả ghi log chính vào file.
- [ ] Không có dependency hoặc trình biên dịch ngoài JDK 17 cho lab chính.

### Kiểm tra cấu hình production

- [ ] Đã chọn một owner của rotation cho mỗi file active.
- [ ] Đã đo peak log rate, đủ disk free/headroom và dự tính retention.
- [ ] Appender/handler và shipper đã được kiểm thử cùng nhau khi rename/truncate/nén.
- [ ] File active/archive có quyền và thư mục đúng.
- [ ] Có cảnh báo disk full, lỗi rollover, shipper lag, queue backlog và drop.
- [ ] Không tạo vòng lặp thu cả stdout và file gây duplicate.
- [ ] Có kế hoạch restart, shutdown, log collector down và file shipper recovery.
- [ ] Có kiểm thử không ghi PII/token và kiểm soát việc đọc archive.
- [ ] Có retention riêng cho local log, central store, backup và audit log.
- [ ] Đã thử thay đổi config trên môi trường staging trước production.

## 15. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `count=3` được hiểu là 3 backup + active | Dự tính retention sai | Tổng file của JUL là 3 |
| `limit=512` được hiểu là 512 dòng | File quay khác kỳ vọng | Limit đo byte, không đo record |
| Chỉ tạo handler, không gắn vào logger | Không ghi được event mong muốn | `logger.addHandler(handler)` và level phù hợp |
| Vẫn bật parent handler trong lab | Log trùng ở console/file | Hiểu hierarchy và `setUseParentHandlers` |
| Không đóng handler | Lock chưa được giải phóng; output có thể chưa flush | `try/finally`, close trước khi đọc kiểm tra |
| Cho JUL và logrotate xoay cùng file | Race rename/truncate, file active trống | Một rotation owner và reopen policy |
| Dùng `copytruncate` rồi khẳng định không mất log | Có race làm mất byte | Chọn rolling phối hợp và kiểm thử |
| Chỉ đếm file, không kiểm tra log mới | Có thể rollover nhưng mất event cuối | Assert sequence/event ID gần nhất |
| Nén/xóa archive khi agent còn đang đọc | Collector thiếu phần đuôi file | Tối ưu shipper lag và thời gian giữ |
| Chạy nhiều JVM chung một file | Lock/rename race và dữ liệu lẫn | Tách đường dẫn theo instance |
| Giữ archive vô thời hạn | Đĩa đầy và tăng rủi ro dữ liệu | Retention + total cap + metric |
| Xem `.gz` là mã hóa | Log nhạy cảm bị đọc được | Kiểm soát quyền và encryption |
| Xem `logger.info()` không lỗi là đủ | Handler có thể báo lỗi ở kênh riêng | Kiểm chứng file/sink và backend errors |
| Đọc stdout và file vào cùng index | Nhân bản event | Xác định nguồn thu thập duy nhất |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao trong lab tạo 100 event nhưng cuối cùng không còn đủ cả 100 dòng?  
**Đáp:** Vì `FileHandler` giữ tối đa ba thế hệ theo `count=3`; những thế hệ cũ đã bị thay thế khi rollover nhiều lần.

**Câu 2.** `FileHandler(limit=512)` có nghĩa file luôn có kích thước không quá đúng 512 byte không?  
**Đáp:** Không. Rotation có thể xảy ra sau một record hoặc ở điểm kiểm tra cụ thể, nên có độ lệch so với ngưỡng.

**Câu 3.** Nếu cần xoay theo ngày và nén archive, có thể chỉ đổi `count` trong JUL không?  
**Đáp:** Không. Cần rolling policy/backend hoặc hạ tầng hỗ trợ thời gian/nén và kiểm thử tương thích.

**Câu 4.** Khi công cụ OS rename file active, JVM có tự ghi sang file mới không?  
**Đáp:** Không mặc định. File descriptor cũ có thể vẫn trỏ đến file đã đổi tên; cần reopen hoặc dùng rolling của chính backend.

**Câu 5.** `copytruncate` có loại bỏ hoàn toàn rủi ro mất log không?  
**Đáp:** Không. Có race giữa copy và truncate trong khi ứng dụng đang ghi.

**Câu 6.** Đủ ba file active/archive có chứng minh collector nhận đủ event không?  
**Đáp:** Không. Cần kiểm chứng agent, checkpoint, ACK, queue và dữ liệu ở đích nhận.

**Câu 7.** Vì sao nên kiểm tra quyền file và retention của archive, không chỉ file đang ghi?  
**Đáp:** Archive vẫn chứa dữ liệu nguyên gốc, có thể có PII/secret, và tồn tại thêm nhiều bản sao ở các chặng khác.

**Câu 8.** Trong container chỉ log stdout, Java có bắt buộc dùng `FileHandler` không?  
**Đáp:** Không. Rotation có thể do container runtime/node agent đảm nhiệm; vẫn cần cấu hình shipper và kiểm thử khi collector chậm.

**Tổng kết:** Thiết lập rotation đúng nghĩa là **cấu hình trigger + giới hạn file + vòng đời handler + khả năng chứng minh kết quả**. Lab Java 17 cho thấy rollover theo byte và retention theo số thế hệ. Khi triển khai production, cần xem cả quyền file, disk capacity, tương thích giữa writer và log shipper, chính sách xóa/nén, retry vận chuyển và yêu cầu bảo mật. Chỉ khi các lớp đó phối hợp tốt mới có một hệ thống file logging vận hành đáng tin.
