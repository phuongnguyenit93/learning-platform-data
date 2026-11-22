# Kiểm tra rotation của log file trong Java

## Mục tiêu học tập

**Kiểm tra rotation** là xác minh một hệ thống logging có **chuyển tệp đang ghi sang archive và tiếp tục ghi vào tệp mới đúng thời điểm, đúng tên, đúng số lượng và đúng chính sách lưu giữ** hay không. Kiểm tra có giá trị không chỉ vì thấy vài file được tạo: nó phải làm rõ tệp nào đang hoạt động, record có bị mất/trùng ngoài chủ đích, dữ liệu cũ được giữ hay xóa theo chính sách, và bộ thu thập log có còn đọc đúng nơi hay không.

Bài này thuộc nhóm **Log rotation** trong **Java Core Logging**, tập trung trực tiếp vào **“Kiểm tra rotation”**. Sau bài, bạn có thể:

- Xác định tiêu chí nghiệm thu cho **rotation theo kích thước** và **rotation theo thời gian**.
- Phân biệt **active file**, **archive**, **trigger**, **rolling policy**, **retention**, **compression** và **cleanup**.
- Tạo một bộ kiểm tra **Java 17 thuần JDK** với **java.util.logging.FileHandler**, dùng dữ liệu xác định được để kiểm tra thế hệ file, giới hạn số file, thứ tự record và mất lịch sử do retention.
- Thực hành **Java 17 + Logback Classic** với **RollingFileAppender** và **SizeAndTimeBasedRollingPolicy** để kiểm tra file hiện tại, archive, tính toàn vẹn và shutdown.
- Nhận biết vì sao **maxHistory không đồng nghĩa số lượng file tối đa**, vì sao archive có thể được dọn bất đồng bộ, và vì sao một file có thể vượt nhẹ ngưỡng dung lượng do ghi nguyên một record.
- Lập test matrix cho restart, concurrency, compression, permission, disk full, async logging, container và collector.
- Phân biệt **log bị mất đúng chính sách retention** với **log bị mất do lỗi pipeline**.

Các ví dụ sử dụng các ngưỡng cực nhỏ để rotation xảy ra nhanh. **Chỉ thực hành trong thư mục test hoặc tệp tạm; không áp dụng ngưỡng nhỏ đó cho production.**

## 1. Kiểm tra rotation thực chất là kiểm tra điều gì?

Một hệ thống ghi file log thường có một **active file** đang nhận các record mới. Khi đạt trigger, backend chuyển file đó thành archive hoặc đóng thế hệ hiện tại rồi mở thế hệ kế tiếp.

~~~mermaid
flowchart LR
    A["Ứng dụng phát event"] --> B["Appender / Handler"]
    B --> C["Active log file"]
    C --> D{"Đạt điều kiện rollover?"}
    D -->|Không| C
    D -->|Có| E["Archive / đổi generation"]
    E --> F["Mở active file tiếp theo"]
    F --> B
~~~

Tùy backend, vòng đời chi tiết có thể gồm rename, mở stream mới, nén archive và dọn lịch sử. Một số thao tác chạy bất đồng bộ. Sơ đồ là mô hình logic, không phải thứ tự thread của mọi implementation.

Có ít nhất **sáu điều kiện** phải kiểm tra:

1. **Trigger:** điều kiện kích hoạt đúng (số byte, ngày/giờ, hoặc cả hai).
2. **Continuity:** log mới tiếp tục đi vào file hợp lệ sau rollover.
3. **Naming:** active file và archive có tên/đường dẫn đúng quy tắc.
4. **Integrity:** các record được giữ lại không hỏng, không trùng và không thiếu ngoài chính sách cho phép.
5. **Retention:** file cũ bị giữ/xóa đúng số generation, số kỳ hoặc tổng dung lượng đã cấu hình.
6. **Operations:** file có quyền đọc/ghi, được collector tìm thấy, không làm nghẽn ứng dụng và không để lại tài nguyên sau shutdown.

**Có nhiều file không đủ để kết luận rotation PASS.** Có thể backend chỉ tạo file mới mỗi lần khởi động; cũng có thể có archive nhưng record gần nhất không được ghi sau khi chuyển. Cần có bằng chứng gắn với trigger và dữ liệu.

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| **Active file** | Tệp đang nhận log mới | Xem đường dẫn cấu hình và record mới nhất |
| **Archive / rolled file** | Tệp thuộc chu kỳ hoặc generation đã qua | Kiểm tra tên, timestamp, nội dung và quyền |
| **Triggering policy** | Điều kiện quyết định thời điểm rollover | Phát record vượt ngưỡng hoặc đi qua ranh giới thời gian |
| **Rolling policy** | Quyết định cách archive/đặt tên và tạo file mới | So khớp tên active/archive và vòng đời |
| **Size limit** | Ngưỡng kích thước tính theo byte hoặc đơn vị đã cấu hình | Đo byte thực của file, không chỉ số ký tự |
| **Time period** | Kỳ ngày/giờ/tháng theo pattern và timezone | Quan sát trước và sau ranh giới kỳ |
| **Generation/index** | Số định danh phiên bản file | Xem %g của JUL hoặc %i của Logback |
| **Retention** | Giới hạn lịch sử cần giữ | Phát sinh đủ kỳ/record rồi kiểm tra tệp bị xóa đúng chính sách |
| **Compression** | Nén archive thành .gz/.zip... | Xác minh giải nén được và dữ liệu còn đầy đủ |
| **Collector** | Thành phần đọc/gửi log đến backend tập trung | Xác nhận tiếp tục theo file mới và không nhảy sót archive |

**Rotation không phải retention.** Rotation chuyển từ file này sang file khác; retention quyết định dữ liệu cũ được giữ đến khi nào. Không nên gọi việc chủ đích xóa record cũ theo count/age là “rotation hỏng”, nếu chính sách đã quy định rõ giới hạn đó.

**Đếm file không đồng nghĩa đếm record.** Một record exception có thể in nhiều dòng stack trace, và một line có thể chứa ký tự đa byte trong UTF-8. Muốn QA đáng tin, hãy gắn sequence ID với mỗi **event**; khi quét file, phân biệt rõ định dạng một-line-per-event hay multiline.

## 3. Tiêu chí nghiệm thu (acceptance criteria)

Trước khi chạy test, viết rõ **điều sẽ được coi là PASS** và **phạm vi mà test không thể chứng minh**.

| Test | Kích thích | Điều kiện PASS ví dụ |
| --- | --- | --- |
| Size trigger | Ghi đủ record để vượt ngưỡng | Có archive, file mới tiếp tục nhận record |
| No premature rollover | Ghi dưới ngưỡng | Chưa xuất archive mới ngoài dự kiến |
| Naming | Rollover nhiều lần | Tên generation/index và đường dẫn đúng |
| Data continuity | Ghi sequence ID liên tục | Record trong phạm vi retention không hỏng/trùng |
| Retention theo count | Vượt số generation của JUL | Không vượt count và record cũ nhất bị loại theo thiết kế |
| Retention theo thời gian | Tạo dữ liệu qua nhiều kỳ | Chỉ giữ kỳ đã quy định sau cleanup |
| Total archive size | Tạo nhiều archive vượt quota | Cleanup dần đạt tổng dung lượng theo hợp đồng backend |
| Restart | Tắt/mở lại process | Không ghi đè archive ngoài dự kiến và tiếp tục tên đúng |
| Invalid directory | Dùng path không có quyền trong môi trường test | Báo lỗi rõ, không âm thầm mất log |
| Async shutdown | Ghi burst rồi graceful stop | Queue được xả theo timeout và policy, không phát log sau stop |
| Collector | Theo dõi file trước/sau rollover | Không bị đứt tuyến đọc hoặc hiểu nhầm rename/truncate |
| Compression | Rollover sang .gz/.zip | File nén hoàn thành và giải nén/truy vấn được |

**Không dùng “filesize phải luôn nhỏ hơn hoặc bằng maxFileSize từng byte” làm assertion duy nhất.** Backend thường xuất một **record nguyên vẹn** rồi đánh giá rollover. Khi record cuối làm chạm hoặc vượt ngưỡng, file có thể lớn hơn mốc đã cấu hình. Điều quan trọng là quá trình rotate tiếp diễn và file không phát triển vô hạn do mất trigger.

Đối với rotation theo thời gian, **đến đúng 00:00 không nhất thiết file lập tức đổi nếu không có event mới**. Nhiều rolling implementation kiểm tra thời điểm tại lần append tiếp theo. QA cần phát thêm một event sau ranh giới kỳ và cho phép độ trễ/cleanup theo thiết kế.

## 4. Kỹ thuật tạo dữ liệu test có thể đối chiếu

Đừng ghi các message ngẫu nhiên hoặc chỉ in “hello”. Hãy tạo mỗi record có:

- **sequence ID duy nhất**, ví dụ seq=01, seq=02..., đủ để phát hiện thiếu/trùng.
- **payload kích thước xác định được**, để dễ kích hoạt size trigger.
- **tên event ổn định** và một formatter một-line-per-event trong bài kiểm tra.
- **charset rõ ràng** (UTF-8).
- **thư mục test tách biệt**, không tái sử dụng log production.
- **cơ chế đóng handler/appender** rồi mới đọc toàn bộ file, tránh nhìn snapshot dở dang.

Ví dụ hai record mẫu:

~~~text
seq=01 payload=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
seq=02 payload=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
~~~

Trong ví dụ trên, phần payload có 44 ký tự ASCII X. Nếu format là **seq=NN payload= + 44 X + \n**, mỗi record có **60 byte UTF-8** (15 byte phần đầu, 44 byte payload, 1 byte newline). Dùng ký tự ASCII tránh khác biệt giữa số ký tự và số byte. Nếu dùng emoji/tiếng Việt có dấu thì UTF-8 thường cần nhiều byte hơn; không thể coi 60 ký tự là 60 byte.

Nếu backend nén archive, **đếm event phải thực hiện sau khi giải nén**. Không so kích thước file .gz với size limit dành cho active file chưa nén.

## 5. Java 17 thuần JDK: kiểm thử JUL FileHandler rotation

JUL có **java.util.logging.FileHandler**, hỗ trợ giới hạn kích thước file và số thế hệ được giữ. Constructor minh họa:

~~~java
new FileHandler(pattern, 120, 3, false);
~~~

Ý nghĩa:
- **pattern:** nơi lưu và tên file, có thể chứa **%g** cho generation.
- **120:** số byte giới hạn xấp xỉ của mỗi file trong bộ rotating.
- **3:** số file output được quay vòng trong cơ chế count.
- **false:** không append dữ liệu cũ; phù hợp với thư mục test mới của bài.

Theo tài liệu Java SE 17, FileHandler **đóng/rotate file khi đạt giới hạn dung lượng** và đánh số generation **0, 1, 2...**. Mặc định nó dùng XMLFormatter nếu không thay, nên bài thực hành tự đặt Formatter một dòng để có kết quả ổn định.

### Chương trình RotationCheckDemo.java hoàn chỉnh

Tạo file **RotationCheckDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public class RotationCheckDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("rotation-check-");
        Logger logger = Logger.getLogger(RotationCheckDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                dir.resolve("service-%g.log").toString(), 120, 3, false);
        handler.setLevel(Level.INFO);
        handler.setEncoding("UTF-8");
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record) + "\n";
            }
        });
        logger.addHandler(handler);

        try {
            for (int seq = 1; seq <= 13; seq++) {
                logger.info(String.format(Locale.ROOT,
                        "seq=%02d payload=%s", seq, "X".repeat(44)));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<Path> logFiles;
        try (Stream<Path> paths = Files.list(dir)) {
            logFiles = paths
                    .filter(p -> p.getFileName().toString().endsWith(".log"))
                    .sorted()
                    .toList();
        }

        List<String> records = new ArrayList<>();
        for (Path path : logFiles) {
            records.addAll(Files.readAllLines(
                    path, StandardCharsets.UTF_8));
        }

        Set<String> ids = new HashSet<>();
        for (String record : records) {
            ids.add(record.substring(0, 6));
        }

        System.out.println("generated=13");
        System.out.println("logFiles=" + logFiles.size());
        System.out.println("rotationObserved=" + (logFiles.size() > 1));
        System.out.println("countLimitRespected=" + (logFiles.size() <= 3));
        System.out.println("retainedRecords=" + records.size());
        System.out.println("oldestEvicted=" + records.stream()
                .noneMatch(s -> s.startsWith("seq=01 ")));
        System.out.println("latestRetained=" + records.stream()
                .anyMatch(s -> s.startsWith("seq=13 ")));
        System.out.println("noDuplicateIds="
                + (records.size() == ids.size()));

        for (Path path : logFiles) {
            System.out.println(path.getFileName()
                    + " bytes=" + Files.size(path)
                    + " lines=" + Files.readAllLines(
                            path, StandardCharsets.UTF_8).size());
        }

        for (Path path : logFiles) {
            Files.delete(path);
        }
        Files.delete(dir);
    }
}
~~~

Chạy với **JDK 17+**:

~~~bash
javac RotationCheckDemo.java
java RotationCheckDemo
~~~

**Stdout đã được kiểm thử** trên JDK cho đúng bài thực hành này:

~~~text
generated=13
logFiles=3
rotationObserved=true
countLimitRespected=true
retainedRecords=5
oldestEvicted=true
latestRetained=true
noDuplicateIds=true
service-0.log bytes=60 lines=1
service-1.log bytes=120 lines=2
service-2.log bytes=120 lines=2
~~~

Ở đây mỗi record là 60 byte và **13 record = 780 byte được phát**. Nhưng hệ thống được cấu hình chỉ **3 file xấp xỉ 120 byte** mỗi file, nên không thể giữ toàn bộ 13 record. Kết quả **retainedRecords=5** và **oldestEvicted=true** là hệ quả có chủ đích của retention theo generation. File hiện hành ở thế hệ 0 chứa record mới nhất; các thế hệ 1, 2 chứa phần lịch sử gần nhất.

**Không diễn giải việc seq=01 không còn là lỗi**, vì số lượng file lưu lịch sử đã giới hạn. Test này chứng minh **rotation xảy ra**, **giữ số generation như cấu hình**, **record mới nhất còn**, và **không có sequence ID trùng trong dữ liệu còn được giữ**.

### Giải thích các điểm dễ nhầm

1. **Files.createTempDirectory** tạo mỗi lần chạy một directory riêng, tránh lẫn file cũ và hạn chế xung đột.
2. **service-%g.log** đưa generation vào filename. FileHandler còn hỗ trợ **%u** cho trường hợp cần giải quyết xung đột tên file.
3. **FileHandler(...,120,3,false)** là cấu hình dành riêng cho demo. Không dùng limit 120 byte trên hệ thống thật.
4. **Formatter** cố ý không đưa timestamp hoặc tên class vào message, giúp độ dài record xác định được.
5. **"\n"** được dùng cố định để byte count không phụ thuộc newline Windows/Linux.
6. **Locale.ROOT** giúp String.format dùng cách tạo số dễ lặp lại.
7. **handler.close()** xảy ra trước khi đọc file, giúp giải phóng stream/lock.
8. **Files.list** lấy file .log đã được tạo; không dùng nguyên danh sách file tạm làm log records.
9. **substring(0,6)** chỉ đúng vì demo biết định dạng **seq=NN**. Parser production cần xử lý message/stack trace có thể thay đổi, không cắt chuỗi theo độ dài cứng.
10. **Set ids** kiểm tra trùng trong số record còn được lưu. Điều này chưa chứng minh không có mất log ngoài retention nếu ta không biết tập ID nào được phép bị loại.

### Phép kiểm tra mạnh hơn: retention là một tập đuôi liên tục

Trong bài demo, ta biết 13 ID theo thứ tự 01..13. Nếu cấu hình chỉ giữ một **đuôi gần nhất** của sự kiện, một assertion mạnh hơn là:

~~~text
Retained IDs: 09, 10, 11, 12, 13
Missing IDs:  01..08 (đã vượt capacity được thiết kế)
Latest ID:    13
~~~

Đây là diễn giải của lần chạy đã kiểm thử. Với một hệ thống thực có nhiều producer, retry, filter và async logging, cần tính một **tập sự kiện đã được backend chấp nhận**, không áp đặt mọi số seq từ mã nghiệp vụ đều phải có mặt. Event có thể bị loại bởi level/filter hoặc đã bị retention theo chính sách.

### Nếu muốn test không mất record do retention

Tạo workload đủ nhỏ so với tổng capacity hoặc tăng count/limit trong **môi trường test** để toàn bộ 13 record được giữ. Khi đó bạn có thể so hai tập ID **expected/actual** mà không có sự xóa lịch sử chủ đích. Chỉ sau khi kiểm tra tính đầy đủ này mới chạy riêng kịch bản vượt capacity để kiểm tra retention.

## 6. Các loại rotation phải được kiểm thử khác nhau

### Rotation theo kích thước

Thường có ngưỡng như **1MB**, **100MB** hoặc giá trị cấu hình phù hợp. Quy trình:

1. Xác nhận không có archive mới khi workload vẫn dưới ngưỡng.
2. Ghi liên tục record có độ dài/charset kiểm soát đến khi rollover.
3. Phát thêm ít nhất một record **sau khi trigger**.
4. Xem file active và archive, xác nhận data continuity.
5. Không giả định kích thước từng file luôn bằng hoặc nhỏ hơn đúng ngưỡng byte vì cách backend ghi record nguyên vẹn và thời điểm đánh giá trigger.

Lỗi thường gặp là chỉ ghi tới vừa ngưỡng, thấy không có archive ngay lập tức, rồi kết luận sai. Cần xem backend đánh giá **trước khi ghi**, **sau khi ghi**, hay tại lần append kế tiếp.

### Rotation theo thời gian

Một ví dụ là file đổi theo **ngày UTC** hoặc theo **múi giờ được cấu hình**. Test cần kiểm tra:
- Ngày/giờ nào quyết định tên archive?
- Nếu tiến trình không có event sau ranh giới thời gian, rollover có chạy ngay không hay chờ event mới?
- Record ngay trước ranh giới thuộc kỳ cũ hay mới?
- Thay đổi timezone hoặc DST có gây tên file bất ngờ không?
- Sau restart trong cùng kỳ, file có tiếp tục đúng tên và không ghi đè ngoài dự kiến?
- Cleanup của kỳ cũ có chạy ngay hay theo lịch/tín hiệu rollover?

**Không đổi đồng hồ hệ thống production** để test thời gian. Trong test harness được kiểm soát, có thể dùng đồng hồ giả/cơ chế time injection mà backend hỗ trợ; nếu không, chạy tích hợp qua ranh giới thời gian thực hoặc sử dụng staging có chính sách phù hợp.

### Rotation kết hợp kích thước và thời gian

Trong Logback **SizeAndTimeBasedRollingPolicy**, pattern archive cần cả **%d** (kỳ thời gian) và **%i** (chỉ số file trong kỳ). Mỗi ngày có thể có nhiều archive khi vượt ngưỡng dung lượng; qua ngày mới, kỳ thời gian đổi. Vì vậy **maxHistory là số kỳ cần giữ**, không phải giới hạn số file archive tuyệt đối.

## 7. Logback: cấu hình kiểm tra kích thước và thời gian

Một ví dụ **logback.xml** cho Logback Classic:

~~~xml
<configuration>
  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/rolling/service.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>
        target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log
      </fileNamePattern>
      <maxFileSize>1KB</maxFileSize>
      <maxHistory>2</maxHistory>
      <totalSizeCap>10MB</totalSizeCap>
    </rollingPolicy>

    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

**Lưu ý XML whitespace:** nếu viết **fileNamePattern** xuống nhiều dòng như trên, XML chứa whitespace xuống dòng. Để tránh parser/backend hiểu sai tên file, nên **giữ nội dung fileNamePattern trên cùng một dòng** khi sử dụng thực tế:

~~~xml
<fileNamePattern>target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
~~~

Các thành phần:
- **file** là file active đang ghi.
- **fileNamePattern** là tên file archive; **%d** thể hiện kỳ ngày và **%i** chỉ số trong ngày.
- **maxFileSize=1KB** làm test rollover nhanh. Giá trị production cần tính theo tải và nhu cầu.
- **maxHistory=2** giới hạn số **kỳ thời gian** được giữ trong chính sách cleanup, **không phải chỉ giữ hai file .log**.
- **totalSizeCap=10MB** giới hạn tổng kích thước archive trong cơ chế cleanup khi dùng maxHistory; không phải size limit của active file.
- **encoder** là nơi định dạng nội dung log, khác với rolling fileNamePattern.
- **root INFO** và appender-ref bảo đảm event INFO tới ROLLING.

Phần cấu hình bên dưới trong ví dụ Maven sẽ sử dụng **fileNamePattern một dòng** để không gây nhầm đường dẫn. Khi dùng compression, pattern có thể kết thúc bằng **.gz** hoặc **.zip**, nhưng kiểm tra file phải tính đến quá trình nén bất đồng bộ.

**Ghi chú từ tài liệu chính thức Logback:** nếu mục tiêu chỉ là giới hạn **tổng dung lượng archive**, TimeBasedRollingPolicy cùng totalSizeCap thường đã đủ; không nên dùng SizeAndTimeBasedRollingPolicy chỉ vì nó nhiều tính năng hơn. Chỉ chọn policy kết hợp khi thực sự cần giới hạn từng file trong mỗi kỳ.

## 8. Java 17 + Maven: bài kiểm tra Logback có thể chạy

Để tránh phụ thuộc vào đúng ngày hiện tại, bài kiểm tra này dùng **30 event có sequence ID**, một payload đủ dài và một **RollingFileAppender**. Sau khi gọi **LoggerContext.stop()**, chương trình quét active file và archive, rồi so sánh số record và uniqueness. Mục tiêu là xác minh **rotation theo kích thước trong cùng một kỳ**; kiểm thử time boundary và retention qua nhiều ngày sẽ được trình bày riêng.

### Cấu trúc dự án

~~~text
logback-rotation-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LogbackRotationCheck.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>logback-rotation-check</artifactId>
  <version>1.0</version>

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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Các version được cố định để có bài học tái lập, **không có nghĩa đây là những phiên bản mới nhất**. Maven cần tải dependency hoặc có sẵn cache. Khi dùng trong dự án thật, tuân theo BOM/dependencyManagement và chính sách cập nhật/bảo mật.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/rolling/service.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
      <maxFileSize>1KB</maxFileSize>
      <maxHistory>2</maxHistory>
      <totalSizeCap>10MB</totalSizeCap>
    </rollingPolicy>

    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

Ví dụ này **không dùng compression** để chương trình có thể đọc trực tiếp tất cả file .log. Nếu chuyển fileNamePattern thành .gz, test reader phải giải nén; không quét và đọc compressed file như text thuần.

### File src/main/java/com/example/logging/LogbackRotationCheck.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LogbackRotationCheck {
    public static void main(String[] args) throws Exception {
        Logger logger = LoggerFactory.getLogger(LogbackRotationCheck.class);
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();

        try {
            for (int i = 1; i <= 30; i++) {
                logger.info("seq={} payload={}",
                        String.format("%02d", i), "X".repeat(180));
            }
        } finally {
            context.stop();
        }

        Path root = Path.of("target", "rolling");
        List<Path> files;
        try (Stream<Path> stream = Files.walk(root)) {
            files = stream.filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".log"))
                    .sorted()
                    .toList();
        }

        List<String> lines = new ArrayList<>();
        for (Path file : files) {
            lines.addAll(Files.readAllLines(
                    file, StandardCharsets.UTF_8));
        }

        Set<String> unique = new HashSet<>();
        for (String line : lines) {
            unique.add(line.substring(0, 6));
        }

        System.out.println("generated=30");
        System.out.println("activeFileExists="
                + Files.isRegularFile(root.resolve("service.log")));
        System.out.println("archiveObserved="
                + files.stream().anyMatch(p ->
                        p.getParent().getFileName()
                                .toString().equals("archive")));
        System.out.println("allRecordsPresent=" + (lines.size() == 30));
        System.out.println("noDuplicateIds="
                + (unique.size() == lines.size()));
        System.out.println("latestRetained=" + lines.stream()
                .anyMatch(s -> s.startsWith("seq=30 ")));
        System.out.println("contextStarted=" + context.isStarted());
    }
}
~~~

### Lệnh chạy

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.LogbackRotationCheck"
~~~

Lệnh dùng Maven Exec Plugin để chạy một **JVM con** với classpath dự án, tránh lẫn backend logging của Maven. Chương trình đã được chạy thử với Logback Classic 1.5.18.

**Stdout của chương trình khi kiểm thử:**

~~~text
generated=30
activeFileExists=true
archiveObserved=true
allRecordsPresent=true
noDuplicateIds=true
latestRetained=true
contextStarted=false
~~~

Các dòng Maven riêng (nếu có) không thuộc output mẫu. Trên lần kiểm thử, hệ thống tạo ra **nhiều file archive cùng một active file**; fileCount quan sát là **5**. Không nên hardcode số lượng file archive như một hợp đồng chung vì nó còn phụ thuộc kích thước message, encoding, newline, phiên bản và thời điểm rollover.

### Ý nghĩa kết quả

- **activeFileExists=true:** file active còn tồn tại.
- **archiveObserved=true:** việc rollover đã xảy ra ít nhất một lần.
- **allRecordsPresent=true:** trong test cụ thể này, toàn bộ 30 event đều tìm thấy khi quét cả active và archive. Test sử dụng **maxHistory=2 kỳ** nhưng chỉ chạy trong một kỳ, không nhằm kiểm tra việc xóa lịch sử hai ngày.
- **noDuplicateIds=true:** không có ID trùng trong các dòng đã đọc.
- **latestRetained=true:** event cuối tiếp tục được ghi sau các lần rollover.
- **contextStarted=false:** Logback context đã dừng trước khi chương trình quét file.

**Cảnh báo về mức độ chứng minh:** chương trình dùng một thread tạo event và format một-line-per-event. Trong hệ thống thực, filter, AsyncAppender, lỗi I/O, nhiều thread/process hoặc multiline exception cần một thiết kế kiểm tra mạnh hơn. Đặc biệt, **lines.size()==30** chỉ phù hợp khi chưa có retention dự kiến xóa record hoặc khi test đã thiết kế cho mọi record đều phải còn.

## 9. Kiểm tra rotation theo thời gian và retention của Logback

**TimeBasedRollingPolicy** thường dùng một date pattern như:

~~~xml
<fileNamePattern>logs/app.%d{yyyy-MM-dd}.log</fileNamePattern>
~~~

Với size-and-time policy, thêm index:

~~~xml
<fileNamePattern>logs/app.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
~~~

Các điều kiện QA cần làm rõ:

1. **Kỳ rollover là ngày/giờ/tháng nào?** Pattern %d xác định nhịp dựa trên date pattern và timezone.
2. **Time boundary có cần event tiếp theo không?** Nếu đến nửa đêm nhưng không ai ghi log, file có thể chưa rotate. Kiểm tra bằng cách phát một record sau khi sang kỳ.
3. **Tên archive thuộc ngày nào?** Archive chứa dữ liệu của kỳ đã kết thúc, còn file active tiếp tục nhận record.
4. **MaxHistory là bao nhiêu kỳ?** Với daily pattern, maxHistory=2 về cơ bản giữ các kỳ lịch sử theo chính sách, không phải chỉ 2 archive nếu mỗi ngày có nhiều index.
5. **Cleanup chạy khi nào?** Logback thường dọn archive khi rollover; có thể thực hiện bất đồng bộ. Không kết luận FAIL chỉ vì tệp cũ còn vài mili-giây ngay sau trigger.
6. **TotalSizeCap có hiệu lực cùng maxHistory?** Logback yêu cầu đặt maxHistory khi dùng totalSizeCap; giới hạn lịch sử được áp dụng trước giới hạn tổng kích thước archive.
7. **Khởi động ngắn hạn không có rollover** thì cleanup có chạy không? Thuộc tính **cleanHistoryOnStart=true** có thể yêu cầu chạy dọn lịch sử khi appender bắt đầu nếu cần.
8. **DST/timezone và thay đổi clock** có ảnh hưởng như thế nào đến kỳ được đặt tên? Cần có chính sách thời gian nhất quán giữa log event và tên archive.

**Không thể kiểm thử retention hai ngày chỉ bằng một lượt ghi trong cùng ngày.** Bài Logback mục 8 xác nhận size rotation trong một kỳ; muốn nghiệm thu time-based retention phải tạo dữ liệu qua nhiều kỳ hợp lệ trong test harness hoặc môi trường staging thích hợp.

### Kiểm tra cleanup đúng cách

- Đưa vào một tập archive đại diện nhiều kỳ, trong **thư mục test**.
- Bảo đảm đúng rolling policy được nạp.
- Kích hoạt rollover hoặc cơ chế cleanup được hỗ trợ.
- Đợi các task dọn bất đồng bộ có điểm kết thúc hợp lệ trước khi chốt assertion.
- So sánh **các kỳ còn tồn tại**, **tổng dung lượng archive**, và **file active không bị xóa nhầm**.
- Không để QA xóa file production chỉ để minh họa retention.

Theo tài liệu Logback, **maxHistory** kiểm soát lịch sử archive, **totalSizeCap** thêm giới hạn tổng dung lượng archive và **cleanHistoryOnStart** có thể yêu cầu cleanup lúc startup. Khi file nén/rename bất đồng bộ, thời điểm quan sát phải tính đến trạng thái tạm.

## 10. Kiểm tra active file, archive naming và compression

Đường dẫn thực tế là phần quan trọng của QA. Với ví dụ Logback:

~~~text
target/rolling/
├── service.log
└── archive/
    ├── service.2026-11-09.0.log
    ├── service.2026-11-09.1.log
    └── service.2026-11-09.2.log
~~~

Đây là **ví dụ hình thức tên file**, không phải danh sách chính xác của mọi lần chạy hoặc mọi ngày. **service.log** là file đang nhận record; tên archive phụ thuộc ngày và index. Chỉ kiểm tra archive không có nghĩa đã xác nhận active file tiếp tục được ghi.

Nếu dùng **.gz/.zip**, cần kiểm tra:
- Tên file nén đúng policy, không sinh file tên kỳ sai.
- Archive có thể giải nén và số event phù hợp.
- File nén tạm hoặc thao tác nén còn chạy không? Không đọc ngay giữa lúc compression.
- Collector có theo dõi archive nén hoặc chỉ active file? Tránh phát hiện trùng/sót khi rename.
- Retention có tính các archive nén vào tổng dung lượng theo chính sách backend không?
- Không coi kích thước đã nén là kích thước byte dùng để trigger rollover của active file.

Một **collector theo dõi path tĩnh** có thể bị lỗi khi active file bị rename/truncate. QA phải đi theo chuỗi **trước rotation → ngay sau rotation → sau collector đã ingest** thay vì chỉ kiểm tra file trên ổ.

## 11. Đối chiếu record: đủ, không trùng và đúng thứ tự

Một chiến lược kiểm tra hiệu quả là gắn **sequence ID** hoặc event ID duy nhất cho mỗi record test.

Gọi:
- **E** là tập các event dự kiến được chấp nhận.
- **A** là tập event đọc được từ tất cả active file và archive thuộc phạm vi retention.
- **D** là tập event bị xóa có chủ đích theo retention được định nghĩa rõ.

Khi không có retention/drop/filter, kỳ vọng **A = E**; các ID là duy nhất và không bị corruption. Khi có retention, kỳ vọng phù hợp là **A = E \ D** theo điều kiện và thời điểm cleanup được thiết kế. Đây là mô hình logic, không phải công thức cho tất cả pipeline phức tạp.

Cần kiểm tra ít nhất:
- **Missing IDs:** event nào đáng lẽ còn mà không thấy?
- **Duplicate IDs:** có event xuất hai lần do additivity, retry hoặc collector không?
- **Ordering:** thứ tự có phù hợp trong một producer đơn luồng không? Với nhiều thread, không kỳ vọng global total order đơn giản.
- **Boundary IDs:** event cuối ở file cũ và đầu ở file mới có nối tiếp đúng không?
- **Encoding:** một record UTF-8 có bị cắt giữa ký tự hay không?
- **Malformed records:** một record có bị đứt giữa hai file không, hay một stack trace bị hiểu thành nhiều record?
- **Retained tail:** record mới nhất có còn sau rollover không?
- **End-to-end delivery:** nếu có collector, các event đã tới backend trung tâm chưa, không chỉ file local.

**Số lượng bản ghi không bằng số dòng văn bản trong mọi định dạng.** Nếu formatter ghi stack trace nhiều dòng, cần parser đúng ranh giới event hoặc log có cấu trúc để đếm chính xác.

Một kết quả **không có duplicate** không tự chứng minh **không bị missing**. Vì vậy nên kiểm cả số lượng, tập ID và điều kiện retention.

## 12. Kiểm tra thủ công bằng terminal

### Linux/macOS

Với một thư mục test có archive text không nén:

~~~bash
find target/rolling -type f -name '*.log' -print
find target/rolling -type f -name '*.log' -exec wc -c {} \;
find target/rolling -type f -name '*.log' -exec wc -l {} \;
grep -R 'seq=30 ' target/rolling
~~~

Lệnh trên liệt kê tên file, số byte, số dòng và tìm event cuối. Nó chỉ phù hợp khi format mỗi record một dòng và archive có đuôi .log không nén. Với .gz, phải giải nén đúng công cụ mới đọc nội dung.

**Đừng chỉ dùng tail -f lên một file rồi cho rằng vẫn theo dõi được log sau khi file bị đổi tên.** Hành vi theo dõi inode/path tùy tùy chọn và môi trường. Kiểm tra công cụ follow file và cấu hình collector mà ứng dụng thực sự dùng.

### Windows PowerShell

~~~powershell
Get-ChildItem -Path .\target\rolling -Recurse -File |
  Where-Object { $_.Extension -eq '.log' } |
  Select-Object FullName, Length, LastWriteTime

Get-ChildItem -Path .\target\rolling -Recurse -Filter '*.log' -File |
  ForEach-Object { Select-String -Path $_.FullName -Pattern 'seq=30 ' }
~~~

Hai ví dụ trên cho biết tệp nào tồn tại, dung lượng byte và nơi có event cuối. Nếu ứng dụng đang chạy, quá trình rename/rotation có thể thay đổi file ngay trong lúc lệnh liệt kê; để có snapshot xác định, **chạy test → graceful stop → kiểm tra**. Không coi ảnh chụp bất kỳ thời điểm nào trong quá trình ghi là kết quả cuối.

## 13. Concurrency và AsyncAppender

### Nhiều thread trong một JVM

Khi nhiều thread cùng phát log:
- Sequence ID toàn cục cần được gán thread-safe, ví dụ AtomicLong, nếu muốn dùng để kiểm tra trùng/thiếu.
- Logger/appender có thể xử lý event theo thứ tự khác với lúc chúng được tạo; không ép thứ tự timestamp tuyệt đối.
- Không đọc file đang rotate mà không có chính sách đồng bộ hoặc snapshot rõ ràng.
- Kiểm tra cả active file và archive; chỉ grep active file dễ khiến người đọc tưởng event cũ bị mất.

### Nhiều JVM/process cùng ghi một đường dẫn

Không mặc định hai tiến trình đồng thời ghi/rotate chung file là an toàn trên mọi backend hoặc filesystem. File lock, prudent mode, rename và retention có thể có hạn chế. Khi có nhiều instance, **tách đường dẫn theo instance** hoặc sử dụng stdout/stderr + collector theo kiến trúc được hỗ trợ. Nếu backend có cơ chế multi-process, phải kiểm thử chính chế độ đó thay vì suy diễn từ test một JVM.

### AsyncAppender

Nếu logger gửi event đến **AsyncAppender**, event có thể còn nằm trong queue lúc bạn đọc file. Bởi vậy:
1. Ngừng producer trước.
2. Chờ tác vụ nghiệp vụ kết thúc.
3. **Stop logging context** để worker xử lý queue còn lại theo chính sách/timeout.
4. Đọc file hoặc query backend sau điểm đồng bộ thích hợp.

Với Logback, những giá trị như **queueSize, discardingThreshold, neverBlock, maxFlushTime** có thể ảnh hưởng việc event bị bỏ, blocking hoặc xả queue khi shutdown. Không được lấy kết quả từ một appender đồng bộ rồi khẳng định pipeline async cũng bảo toàn mọi event.

**Kết thúc sạch không đảm bảo không mất log do sự cố.** SIGKILL, crash, mất điện, I/O lỗi và collector bị ngắt có thể làm thất lạc bản ghi ngoài phạm vi rotation. Cần tách test rotation với test độ bền/đảm bảo delivery.

## 14. Restart, rename và quyền truy cập

### Restart

Sau khi đã rotate vài lần:
1. Dừng context và process đúng cách.
2. Chụp danh sách file/size/event cuối.
3. Khởi động lại với cùng cấu hình.
4. Phát thêm record có ID mới.
5. Xác nhận active file tiếp tục ghi, tên archive không đè trái ý muốn, và retention vẫn đúng.

**Không dùng append=false trong production khi cần giữ lịch sử cũ** mà không biết hiệu ứng; với JUL, mode false trong demo chỉ để có dữ liệu test sạch. Trong Logback, tên/đường dẫn active và chỉ số archive phải được xác nhận theo policy thật.

### Lỗi quyền hoặc disk

Để kiểm thử lỗi an toàn, tạo **thư mục test không có quyền ghi**, volume read-only hoặc mô phỏng I/O failure trong môi trường chuyên dụng. Đừng tháo mount production hay làm đầy ổ thật để kiểm tra.

Một lỗi khi khởi tạo FileAppender hoặc FileHandler có thể khiến hệ thống không phát log như dự kiến. QA cần xem **status/error manager** của logging backend và quyết định ứng dụng phải fail-fast, cảnh báo hoặc fallback theo yêu cầu. Không tự động coi “ứng dụng vẫn chạy” là test rotation PASS.

### Đường dẫn archive

File active có thể ở **logs/app.log** nhưng archive ở **logs/archive/app.2026-11-09.log**. Nếu collector chỉ đọc một đường dẫn cũ không được cập nhật, log sau rollover có thể vắng mặt trong backend trung tâm dù đã được ghi đúng trên disk.

**Đừng thay đổi fileNamePattern hoặc file active trong lúc appender đang chạy** mà không dùng cơ chế reconfiguration chính thức. Race giữa rename và reader có thể làm việc kiểm thử trở nên không xác định.

## 15. Monitoring rotation trong môi trường vận hành

Sau khi test chức năng PASS, vẫn nên theo dõi những tín hiệu giúp phát hiện rotation hỏng về sau:

| Tín hiệu | Bất thường | Hành động gợi ý |
| --- | --- | --- |
| Kích thước file active | Tăng liên tục vượt mức thiết kế | Kiểm tra trigger/policy hoặc file không rotate |
| Số file archive | Không có archive dù đã vượt ngưỡng | Xác nhận đúng config/path và có event mới |
| Tổng dung lượng thư mục log | Tăng không giới hạn | Kiểm tra retention, totalSizeCap, cleanup |
| Tuổi của archive cũ nhất | Vượt thời gian giữ dự kiến | Xem maxHistory, cleanHistoryOnStart và lần rollover |
| Status/errors của appender | Permission, rename, compression, I/O fail | Xem quyền, disk và trạng thái sink |
| Không thấy sequence/event mới | Có thể file output bị ngắt | So logger level, appender và collector |
| Collector ingestion lag | Event local có nhưng backend trung tâm chưa có | Kiểm tra reader, rename/truncate, network và indexing |
| Queue async | Backlog/drop tăng trong burst/shutdown | Xem queueSize, discardingThreshold, maxFlushTime |
| File descriptor/lock | Leak sau restart/redeploy | Kiểm tra lifecycle, stop/close |

**Không giám sát bằng một con số thiếu ngữ cảnh.** Ví dụ archive count cao có thể hợp lệ trong ngày tải lớn với %i nhiều file; phải hiểu maxHistory là số kỳ, không phải số file. Ngược lại, không thấy archive có thể do ứng dụng không đủ lưu lượng để trigger, không nhất thiết lỗi.

Trên container/Kubernetes, cân nhắc ghi **stdout/stderr** để nền tảng/collector xử lý rotation thay cho ứng dụng, trừ khi có yêu cầu file logging. Khi platform quản lý file log, **test rotation ở đúng tầng sở hữu**; cấu hình RollingFileAppender không điều khiển rotation do container runtime thực hiện.

## 16. Các lỗi thường gặp và cách phân tích

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| Không có archive | Chưa vượt trigger hoặc không có event sau boundary | Tạo dữ liệu đủ kích thước, phát event sau thời gian |
| File active lớn hơn maxFileSize một chút | Backend ghi trọn event rồi mới rollover | Xem chu kỳ/file tiếp theo, không assert byte cứng sai thiết kế |
| Archive bị ghi đè ngoài ý muốn | Sai append/rotation config, reuse path khi restart | Test restart và inspect tên generation/index |
| Record cũ biến mất | Retention theo count/age/cap | So với chính sách trước khi kết luận mất log |
| Record mới nhất thiếu | Appender lỗi, chưa flush/stop, collector trễ | Dừng sạch và đọc cả active + archive |
| Có record trùng | Nhiều appender, additivity, bridge hoặc collector đọc lại | So event ID và toàn bộ pipeline |
| Một stack trace bị đếm nhiều lần | Multiline log | Parse theo event, không chỉ wc -l |
| MaxHistory=2 nhưng có hơn hai file | Hai kỳ có nhiều size-index files | Hiểu maxHistory là **kỳ**, không phải file count |
| Quá kỳ retention vẫn còn archive | Cleanup chạy lúc rollover/start hoặc bất đồng bộ | Test điều kiện cleanup và cho thời gian hoàn thành |
| File .gz chưa xuất hiện ngay | Compression chạy bất đồng bộ | Chờ completion hợp lệ rồi kiểm tra |
| Appender không start | XML sai, path không có quyền, class version khác | Kiểm tra Logback status và logback.xml |
| Lỗi vì thiếu %i | SizeAndTimeBasedRollingPolicy đòi %d và %i | Sửa fileNamePattern |
| JUL không thấy file name dự kiến | %g/%u hoặc file lock thay tên | Xem pattern và file output thực tế |
| Rotation PASS local nhưng FAIL trong container | Volume, working directory hoặc UID/GID khác | Kiểm tra filesystem/container và mount |
| Dashboard trống sau rollover | Collector không theo đổi tên/truncate | Kiểm tra tailing config và ingest lag |
| Rotation làm app chậm | I/O rename/compression/flush gây tải | Đo latency, điều chỉnh policy và lưu trữ |

## 17. Checklist trước khi kết luận QA PASS

Chỉ đánh dấu PASS khi các điều kiện thích hợp với chính sách đang test được xác nhận:

- [ ] Đã xác định **backend thực tế** và file cấu hình có hiệu lực.
- [ ] Biết rõ **active file** và **archive fileNamePattern**.
- [ ] Đã phát dữ liệu với **sequence IDs** hoặc event IDs có thể đối chiếu.
- [ ] Test **dưới ngưỡng** và **vượt ngưỡng** kích thước, xem đúng trigger.
- [ ] Test **event đầu sau rollover** tiếp tục được ghi.
- [ ] Test time boundary bằng phương pháp an toàn, không sửa đồng hồ production.
- [ ] Không coi **maxHistory** là số file khi sử dụng rolling theo thời gian.
- [ ] Kiểm tra retention/totalSizeCap theo **kỳ**, sau cleanup hoàn tất.
- [ ] Quét **cả active và archive**, giải nén nếu cần.
- [ ] So được tập ID expected/actual trong phạm vi retention; xác định duplicate/missing.
- [ ] Kiểm tra startup/restart và shutdown, tránh đang còn async queue.
- [ ] Kiểm tra lỗi permission/disk trong **môi trường test**, không phá production.
- [ ] Kiểm tra path và collector sau rename/truncate, nhất là container.
- [ ] Có giới hạn storage và giám sát disk/retention.
- [ ] Đã ghi lại **policy, phiên bản backend, workload, ngày/giờ, timezone và kết quả thực tế** để người khác có thể tái hiện.

Checklist là công cụ tự đánh giá; không có nghĩa một bài thực hành nhỏ đã chứng minh toàn bộ tính đúng đắn của rotation trong production.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Thấy service-0.log, service-1.log, service-2.log; có chắc rotation đã hoạt động đúng không?

**Đáp án:** Chưa đủ. Phải kiểm trigger, dữ liệu sau rollover, tên file, retention và tập record còn được giữ. Nhiều file cũng có thể do nhiều lần startup hay process khác.

**Câu 2.** JUL FileHandler count=3 có nghĩa giữ tất cả event từng được ghi hay không?

**Đáp án:** Không. Nó quay vòng trên số file đã định. Khi vượt tổng capacity, các generation cũ sẽ bị thay và record cũ biến mất có chủ đích.

**Câu 3.** Vì sao bài JUL phát 13 event nhưng chỉ giữ 5 record?

**Đáp án:** Mỗi record 60 byte; limit 120 byte và count 3 nghĩa số generation hữu hạn, các event cũ bị thay khi rotate nhiều lần. Record mới nhất vẫn hiện diện.

**Câu 4.** Nếu maxHistory=2 trên daily SizeAndTimeBasedRollingPolicy thì tối đa hai file archive có đúng không?

**Đáp án:** Sai. MaxHistory giới hạn số **kỳ ngày**; trong mỗi ngày có thể nhiều archive chỉ số %i nếu kích thước vượt ngưỡng.

**Câu 5.** Ngay 00:00 mà chưa có archive mới, rotation time-based chắc chắn lỗi?

**Đáp án:** Không. Nhiều backend rollover khi phát event tiếp theo sau khi đổi kỳ; cần hiểu trigger thật và tạo sự kiện sau ranh giới.

**Câu 6.** Vì sao file có thể vượt nhẹ maxFileSize?

**Đáp án:** Backend có thể ghi nguyên event rồi mới kiểm trigger. Cần kiểm xem file tiếp theo được tạo đúng và không tăng không giới hạn.

**Câu 7.** Nếu có file nén .gz, có thể dùng Files.readAllLines trực tiếp và đếm record không?

**Đáp án:** Không. Phải giải nén và parse theo định dạng đã tạo. File nén cũng có thể đang được tạo bất đồng bộ.

**Câu 8.** Chạy AsyncAppender và nhìn file ngay khi vòng lặp logger.info kết thúc có đáng tin không?

**Đáp án:** Chưa. Event có thể còn trong queue. Phải có bước ngừng producer, drain/stop theo chính sách và điểm quan sát phù hợp.

**Câu 9.** Rotation đúng trên disk có chứng minh collector đã ingest mọi record không?

**Đáp án:** Không. Collector có thể gặp lỗi rename/truncate hoặc lag. Cần một bài kiểm tra end-to-end riêng.

**Câu 10.** Khi test retention có được xóa thư mục log production để xem backend tạo lại không?

**Đáp án:** Không. Dùng thư mục test/volume staging, dữ liệu giả và thao tác có kiểm soát; không gây mất chứng cứ vận hành.

## 19. Nguồn tham khảo kỹ thuật

- [Oracle Java SE 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): limit, count, append, naming %g/%u và cơ chế rotation.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): liệt kê, đọc và kiểm tra kích thước file.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): RollingFileAppender, TimeBasedRollingPolicy, SizeAndTimeBasedRollingPolicy, maxHistory, totalSizeCap và cleanup.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): cách nạp logback.xml, lifecycle và chẩn đoán cấu hình.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, discarding policy, backpressure và shutdown.

## Ghi nhớ

**Kiểm tra rotation là kiểm tra sự chuyển giao an toàn giữa các file cùng chính sách giữ lịch sử.** Hãy tạo record có ID và kích thước có thể dự đoán, kích thích trigger một cách kiểm soát, quét cả active/archive, so sánh tập ID và xác nhận event mới nhất còn. Luôn phân biệt dữ liệu bị loại **đúng retention** với dữ liệu mất do lỗi. Với time-based rotation, phải hiểu kỳ, timezone và thời điểm rollover; với AsyncAppender và collector, cần điểm đồng bộ và kiểm tra end-to-end riêng. **Rotation PASS không tự đồng nghĩa zero-loss hoặc durable delivery.**
