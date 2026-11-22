# Xóa file log quá hạn trong Java — Chính sách retention sau Log rotation

## 1. Xóa file quá hạn là gì?

Trong hệ thống Java chạy liên tục, log được ghi ra console, file hoặc một hệ thống tập trung. Khi sử dụng **file logging**, dữ liệu sẽ tích lũy theo ngày, theo lượng truy cập hoặc theo kích thước. **Log rotation** là quá trình chuyển file đang ghi sang một file archive và tiếp tục ghi vào file mới; **retention/cleanup** là chính sách xác định các archive nào đã hết thời gian được phép lưu và có thể được xóa.

Ví dụ:

```text
logs/
  app.log                           <- file đang ghi
  archive/
    app-2026-10-01.log.gz           <- archive cũ
    app-2026-10-25.log.gz           <- archive còn mới
    app-2026-11-08.log.gz           <- archive hôm qua
```

Nếu vận hành quy định giữ archive trong khoảng 30 ngày, nhiệm vụ cleanup có thể xem xét archive quá tuổi; **không được mặc nhiên xóa `app.log` đang được ứng dụng ghi**. Nó cũng không được tự xóa tệp của module khác, file chưa được collector nhận hoặc bản ghi phải giữ lại để điều tra.

Hai hoạt động phải được phân biệt:

- **Rollover/rotation:** quyết định *khi nào tạo thế hệ log mới*; ví dụ khi file vượt 10 MB hoặc sang ngày mới.
- **Deletion/retention:** quyết định *archive nào không cần giữ nữa*; ví dụ file đủ 30 ngày tuổi, vượt số bản lưu hoặc vượt tổng dung lượng cho phép.

**Xóa file không thể được coi như thao tác vô hại.** Tệp đã xóa có thể chứa bằng chứng điều tra hoặc là bản sao duy nhất của một số event. Chính sách phải có phạm vi, điều kiện, chủ sở hữu và cách kiểm chứng rõ ràng.

## 2. Rotation, retention, backup và ingestion khác nhau như thế nào?

| Khái niệm | Mục tiêu | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Rotation** | Thay file đang ghi bằng thế hệ mới. | `app.log` được archive theo ngày. | Không mặc định có thời hạn xóa. |
| **Time retention** | Chọn archive theo tuổi hoặc kỳ lịch. | Giữ 30 kỳ archive ngày. | Khác với giữ đúng 30 × 24 giờ. |
| **Count retention** | Giới hạn số file/thế hệ archive. | Giữ tối đa 10 file thế hệ. | Một ngày có thể tạo nhiều file. |
| **Size retention** | Giới hạn dung lượng archive. | Tổng archive tối đa 5 GB. | Có thể loại file còn mới khi log tăng mạnh. |
| **Backup** | Tạo bản sao có thể phục hồi. | Lưu trên object storage có kiểm soát. | Rotation không tự tạo một backup độc lập. |
| **Log ingestion** | Thu và lưu event để truy vấn. | Shipper chuyển log tới kho tập trung. | Xóa quá sớm có thể làm mất log chưa được đọc. |

Một hệ thống có thể đặt đồng thời chính sách **30 kỳ lưu và tối đa 5 GB**. Nhưng nếu tổ chức **bắt buộc giữ tối thiểu 30 ngày**, việc đặt giới hạn dung lượng quá nhỏ có thể dẫn tới xung đột: file bị xóa trước kỳ hạn. Phải giải quyết ở thiết kế storage, ingestion hoặc chính sách đã được phê duyệt, không tùy ý xóa dữ liệu bắt buộc để giải phóng đĩa.

**Xóa local archive không đồng nghĩa xóa log ở mọi nơi.** Collector, search index, object storage, backup và filesystem snapshot có retention riêng. Ngược lại, nếu chưa có bản sao thứ hai, xóa local có thể khiến thông tin biến mất hoàn toàn.

## 3. Các điều kiện của một retention policy đúng

Trước khi bật xóa tự động, trả lời:

1. **Ai sở hữu archive?** Một appender, một service, scheduler hệ điều hành hay hệ quản lý log? Tránh nhiều owner cùng xóa một file.
2. **Thư mục được phép xóa là gì?** Ưu tiên tách `logs/app.log` đang ghi khỏi `logs/archive/`.
3. **Tên file được phép là gì?** Ví dụ chỉ `app-YYYY-MM-DD-i.log.gz`, không phải tất cả `*.log` trên volume.
4. **“Quá hạn” được đo như thế nào?** Từ last-modified time, thời điểm trong filename, thời điểm tạo archive hay một kỳ ngày/tháng?
5. **Ngưỡng biên xử lý ra sao?** Xóa khi *cũ hơn* 30 ngày hay *đủ 30 ngày tuổi trở lên*?
6. **Có yêu cầu giữ tối thiểu không?** Audit, security, hợp đồng khách hàng hoặc legal hold có thể cấm xóa dù vượt tuổi.
7. **Archive đã hoàn tất chưa?** Không chọn file đang nén, rename, upload hay vẫn được writer/shipper sử dụng.
8. **Khi nào job chạy?** Khi rollover, lúc startup hay theo lịch độc lập?
9. **Có dry-run không?** Phải xem được danh sách và số byte dự định xóa trước khi áp dụng lần đầu.
10. **Khi có lỗi thì làm gì?** Lỗi quyền, lock, disk, symlink, collector lag phải được báo, không tự coi là thành công.

Một chính sách an toàn có thể viết rõ:

> “Chỉ xóa archive có tên thuộc allowlist trong thư mục archive do service sở hữu, đã hoàn tất ghi và quá tuổi theo policy. Không xóa active log, symlink, file của ứng dụng khác, file thuộc legal hold hoặc file chưa đáp ứng điều kiện thu thập. Mỗi lần cleanup ghi nhận số file/byte và lỗi.”

**30 ngày trong các ví dụ chỉ là giả định học tập**, không phải thời hạn retention mặc định của Java hay một yêu cầu pháp lý chung.

## 4. Xác định “tuổi file”: mtime, ngày trên tên và kỳ archive

### 4.1. Tuổi theo thời điểm tuyệt đối

Nếu yêu cầu “cũ hơn 30 lần 24 giờ”, Java 17 có `Instant` và `Duration`:

```java
import java.time.Duration;
import java.time.Instant;

Instant cutoff = Instant.now().minus(Duration.ofDays(30));
```

So sánh `Files.getLastModifiedTime(path).toInstant()` với cutoff. Nếu dùng `modified.isBefore(cutoff)`, file **bằng đúng cutoff được giữ lại**. Nếu dùng `!modified.isAfter(cutoff)`, file **bằng cutoff cũng được chọn**. Chính sách phải quyết định trước.

Với thời điểm cố định `2026-11-09T00:00:00Z`, 30 × 24 giờ trước là `2026-10-10T00:00:00Z`:

| `mtime` của archive | So với cutoff | Kết quả với `isBefore` |
| --- | --- | --- |
| `2026-10-01T00:00:00Z` | Cũ hơn | Xóa nếu đúng phạm vi và đủ điều kiện. |
| `2026-10-10T00:00:00Z` | Bằng | Giữ lại. |
| `2026-10-25T00:00:00Z` | Mới hơn | Giữ lại. |

### 4.2. Tuổi theo kỳ ngày/tháng

Nếu một hệ thống tạo archive mỗi ngày theo pattern `%d{yyyy-MM-dd}`, cấu hình giữ 30 kỳ ngày là một cách giữ **các nhóm log theo ngày**, không luôn tương đương một ngưỡng chính xác 720 giờ.

Với rollover theo **tháng**, `maxHistory=6` của Logback có thể mang nghĩa sáu kỳ tháng. Không chuyển `maxHistory=30` thành “30 file” hay “30 ngày” nếu pattern không theo ngày hoặc có nhiều file trong một kỳ.

### 4.3. Không tin rằng filename bằng mtime

File tên `app-2026-10-01.log.gz` có thể được copy hoặc nén lại ngày 09/11, khiến last-modified time mang giá trị mới. Ngược lại, backup/restore cũng có thể giữ mtime cũ.

Do đó:

- **Lọc theo mtime:** phù hợp nếu mtime là nguồn tuổi chính thức; phải hiểu tác động của việc copy/nén.
- **Lọc theo ngày trong tên:** cần parser tên nghiêm ngặt, timezone/chu kỳ rõ ràng, tránh tin input tùy ý.
- **Lọc theo metadata của storage:** có thể hợp lý khi archive ở object storage với lifecycle chính thức.

Không tự động trộn các nguồn tuổi nếu chưa định nghĩa trường nào có thẩm quyền.

## 5. Ưu tiên để framework rolling quản lý file của chính nó

Trong ứng dụng dùng **Logback** hoặc **Log4j 2**, nên tận dụng rolling appender và retention policy khi chúng đáp ứng nhu cầu. Framework biết mẫu tên và thời điểm rollover của archive, thường giảm nguy cơ xóa nhầm so với một script quét cả thư mục.

Một thiết kế rõ ràng:

```text
Application Logger
       |
RollingFileAppender
       |
       +--> active: logs/app.log
       |
       +--> archives: logs/archive/app-<date>-<index>.log.gz
                              |
                         Retention policy
                              |
                     chỉ xóa archive phù hợp
```

**Phần xóa thường gắn với thời điểm rollover, không phải một đồng hồ độc lập.** Với nhiều cấu hình, rollover chỉ xảy ra khi có log event sau mốc thời gian. Một service không phát log cả tuần có thể chưa kích hoạt dọn archive dù có archive đã quá hạn; khi khởi động lại hoặc phát log mới, cơ chế mới có cơ hội thực hiện.

Muốn deadline cleanup chính xác ngay cả khi ứng dụng không chạy, cần giải pháp có lịch xử lý độc lập hoặc một storage lifecycle policy có hợp đồng phù hợp.

## 6. Logback: TimeBasedRollingPolicy, maxHistory và totalSizeCap

Logback hỗ trợ `RollingFileAppender` và `TimeBasedRollingPolicy`, cho phép xoay archive theo lịch và tự dọn các kỳ cũ.

Ví dụ file `logback.xml` của một ứng dụng có backend Logback hợp lệ:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>5GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Giải thích từng thành phần:

- `<file>logs/app.log</file>` là file **đang ghi**. Nó không phải archive quá hạn được lựa chọn để xóa theo lịch archive.
- `fileNamePattern` chứa `%d{yyyy-MM-dd}`, nghĩa là rollover theo **kỳ ngày** và archive có thể được nén nhờ hậu tố `.gz`.
- `maxHistory=30` quy định giữ **30 kỳ archive theo ngày**, không phải một phép đo chính xác tới mili-giây.
- `totalSizeCap=5GB` là giới hạn tổng dung lượng **archive** bổ sung; theo tài liệu Logback, để dùng totalSizeCap cần có maxHistory. Logback áp dụng maxHistory trước và totalSizeCap sau.
- `cleanHistoryOnStart=true` yêu cầu dọn lịch sử lúc appender start, hữu ích cho job ngắn hạn ít khi kích hoạt rollover. Mặc định thường là false.
- `<root>` tham chiếu appender `FILE` để chuyển sự kiện tới file. Nếu appender không được tham chiếu đúng, việc ghi log không hoạt động như mong đợi.

### Giới hạn quan trọng

**maxHistory không có nghĩa xóa đúng lúc sang ngày mới.** Cleanup thường chạy khi rollover, có thể bất đồng bộ; startup cleanup chỉ xuất hiện khi cấu hình bật. Một archive cũ có thể còn tồn tại trước lần xử lý kế tiếp.

Nếu yêu cầu giới hạn kích thước **mỗi file archive**, Logback có `SizeAndTimeBasedRollingPolicy` dùng cả `%d` và `%i` trong filename pattern. `totalSizeCap` không thay thế một giới hạn kích thước mỗi file; nó chỉ kiểm soát **tổng archive**.

**Lưu ý:** nếu yêu cầu giữ log tối thiểu 30 ngày, `totalSizeCap=5GB` có thể xóa archive chưa đủ 30 ngày khi dung lượng vượt cap. Đó là một lựa chọn chính sách phải được phê duyệt, không nên copy từ ví dụ mà không tính lượng log thực tế.

## 7. Log4j 2: Delete action, IfFileName và IfLastModified

Log4j 2 cung cấp `RollingFileAppender` với các rollover strategy; trong đó có **Delete action** để loại archive sau các đợt rollover. Muốn xóa file theo tuổi mà không ảnh hưởng file khác, nên kết hợp **basePath cụ thể + điều kiện tên file + điều kiện tuổi**.

Ví dụ đầy đủ `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy>
                <Delete basePath="logs/archive"
                        maxDepth="1"
                        testMode="true">
                    <IfFileName glob="app-*.log.gz">
                        <IfLastModified age="P30D"/>
                    </IfFileName>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

**Đây là cấu hình đang ở chế độ xem trước, với `testMode="true"` nên không xóa thật.** Theo Log4j 2, Delete action ở test mode phát thông điệp qua Status Logger cho những file sẽ được chọn; người vận hành cần đối chiếu kết quả trước khi bật xóa.

Đọc cấu hình:

1. `fileName="logs/app.log"` là đường dẫn **active file**.
2. `filePattern="logs/archive/..."` đặt archive trong một thư mục riêng. `%d` chọn kỳ thời gian, `%i` phân biệt nhiều file trong cùng kỳ khi size trigger kích hoạt.
3. `TimeBasedTriggeringPolicy` và `SizeBasedTriggeringPolicy` quyết định lúc nào **rollover**, không phải trực tiếp lúc nào xóa.
4. `DefaultRolloverStrategy` chứa hành động thêm sau rollover.
5. `Delete basePath="logs/archive" maxDepth="1"` giới hạn phạm vi duyệt **một cấp** trong thư mục archive.
6. `IfFileName glob="app-*.log.gz"` chỉ cho phép những tên thuộc họ archive, không phải file tùy ý.
7. `IfLastModified age="P30D"` xét **last modification age** của file. Điều kiện tuổi được lồng trong điều kiện tên file, vì vậy cả hai đều cần phù hợp.
8. `testMode="true"` không thực hiện xóa; khi đã xác minh được tập file đúng và có phê duyệt mới chuyển sang chế độ xóa thật.

**Thời điểm thực hiện:** Delete action được thực hiện trong quá trình rollover. Nó không tự là cron job chạy mọi đêm. Nếu ứng dụng không phát log, một archive có thể đã cũ hơn ngưỡng nhưng vẫn còn trên disk trước lần rollover tiếp theo.

**An toàn với liên kết:** theo tài liệu Log4j 2, `followLinks` mặc định false, giảm nguy cơ đệ quy qua symbolic link ra ngoài basePath. Không bật `followLinks=true` khi chưa xác định chính xác quyền sở hữu các đường dẫn.

### IfLastModified khác maxHistory

- **Log4j 2 `IfLastModified age="P30D"`:** dựa trên tuổi mtime tại thời điểm action chạy, nhận file đã đủ tuổi quy định.
- **Logback `maxHistory=30`:** dựa trên các **kỳ archive** do rolling policy quản lý.
- **Java `Instant.isBefore(cutoff)`:** điều kiện nghiêm ngặt “cũ hơn cutoff”, không xóa file đúng bằng cutoff.

Không giả định hành vi ở **đúng ranh giới** trùng nhau giữa ba cơ chế. Nếu retention cần chính xác tới giây, cần định nghĩa phép so sánh, nguồn timestamp và timezone rõ ràng.

### Khi nào cần IfAll?

Log4j 2 hỗ trợ `IfAll` để yêu cầu nhiều path conditions đồng thời, bên cạnh cách lồng `IfLastModified` trong `IfFileName` như ví dụ. Cấu hình nhiều điều kiện phức tạp cần kiểm thử logic kết hợp; không tự suy ra tất cả điều kiện là OR hoặc AND trong mọi vị trí XML.

### Không dùng basePath quá rộng

Ví dụ thiếu an toàn:

```xml
<!-- Không dùng tùy tiện trong thư mục chứa nhiều loại file. -->
<Delete basePath="logs" maxDepth="99">
    <IfLastModified age="P30D"/>
</Delete>
```

Cấu hình đó có thể chọn cả file không phải archive của ứng dụng. Cách tốt hơn là basePath chuyên biệt và kết hợp allowlist tên + tuổi, cùng testMode/dry-run.

## 8. JUL FileHandler: count/limit không phải tuổi file

JDK cung cấp `java.util.logging.FileHandler` với giới hạn kích thước và số lượng thế hệ file:

```java
// Đoạn minh họa trong ứng dụng đã có logger và xử lý IOException.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "logs/app-%g.log", 1_000_000, 5, true);
handler.setFormatter(new java.util.logging.SimpleFormatter());
logger.addHandler(handler);
```

Trong đó:

- `%g` là chỉ số thế hệ khi rotate.
- `1_000_000` là giới hạn byte của file trong cơ chế xoay.
- `5` là số thế hệ, **không phải 5 ngày**.
- `true` là chế độ append theo API FileHandler.

**JUL FileHandler không có option trực tiếp kiểu maxAge=30d** để xóa archive theo tuổi như hai cơ chế trên. Nếu chỉ dùng JUL mà cần retention theo thời gian, phải chọn một logging backend khác hoặc thiết kế cleanup job riêng, có ranh giới rõ ràng và không xóa file đang được FileHandler mở.

Lưu ý file lock và hành vi khác nhau khi nhiều JVM cùng ghi; đừng thay FileHandler bằng một lịch xóa wildcard mà không đánh giá quyền sở hữu thế hệ file.

## 9. Khi nào nên dùng scheduler/job riêng?

Một job cleanup riêng có thể hợp lý khi:

- Service không phát log đủ thường xuyên để rollover-triggered cleanup chạy đúng hạn.
- Archive do nhiều component tạo nhưng có một storage policy thống nhất và có chủ sở hữu rõ.
- Cần phối hợp xác nhận collector đã đọc/upload một archive trước khi xóa local.
- Có trường hợp legal hold, storage tier hoặc retention đặc thù mà rolling policy không giải quyết.
- Dùng JUL hoặc một logger không có age retention built-in.

Nhưng job riêng cũng làm tăng rủi ro: cleanup có thể chạy giữa lúc nén, rename, upload, khi writer còn mở file, hoặc khi một appender khác cùng đang xóa.

Một thiết kế job có trách nhiệm nên có:

1. **Single ownership / lock/lease:** tránh nhiều instance dọn cùng một tập file.
2. **Directory isolation:** thư mục archive chỉ dành cho service, quyền hạn tối thiểu.
3. **Allowlist tên và loại file:** không nhận tên lấy trực tiếp từ request/user.
4. **Không follow symlink** và không đệ quy ngoài phạm vi đã duyệt.
5. **Một chính sách timestamp thống nhất**, cutoff và boundary được định nghĩa.
6. **Dry-run làm mặc định** trước khi bật xóa thật lần đầu.
7. **Điều kiện archive hoàn thành**: đã nén/rename/ship xong theo hợp đồng.
8. **Giới hạn mỗi batch**, số byte, timeout và retry hợp lý.
9. **Metrics và audit**: candidates/deleted/error, bytes và thời điểm chạy.
10. **Phục hồi/fail-safe**: khi không chắc chắn, bỏ qua file và phát cảnh báo thay vì xóa bừa.

**Không nên vừa bật delete trong rolling appender vừa chạy cron xóa các file đó** nếu chưa có phối hợp rõ ràng.

## 10. Ví dụ Java 17 độc lập: dry-run trước, xóa archive mô phỏng sau

Ví dụ chạy **chỉ trong một thư mục tạm do chương trình tự tạo**. Không cần thư viện bên thứ ba, không quét hoặc xóa log thật của máy. Chương trình tạo file giả với mtime biết trước, chỉ chọn archive đúng mẫu `app-YYYY-MM-DD.log.gz`, rồi chạy hai lượt:

- `DRY_RUN`: in quyết định nhưng không xóa.
- `APPLY`: xóa file đã quá hạn trong chính thư mục demo.

Để kết quả lặp lại chính xác, thời điểm được cố định tại `2026-11-09T00:00:00Z`; ngưỡng là 30 ngày trước. Các file có phần mở rộng `.gz` chỉ chứa text mẫu, **không phải file GZIP thật**: bài tập kiểm tra *quyết định lựa chọn file*, không phải cơ chế nén của appender.

### Tệp RetentionCleanupDemo.java

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class RetentionCleanupDemo {

    private static final Pattern ARCHIVE =
            Pattern.compile("app-\\d{4}-\\d{2}-\\d{2}\\.log\\.gz");

    private static final List<String> DEMO_NAMES = List.of(
            "app-2026-10-01.log.gz",
            "app-2026-10-10.log.gz",
            "app-2026-10-25.log.gz",
            "current.log",
            "notes.txt");

    private RetentionCleanupDemo() {
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("retention-demo-");

        try {
            create(directory, DEMO_NAMES.get(0),
                    "2026-10-01T00:00:00Z");
            create(directory, DEMO_NAMES.get(1),
                    "2026-10-10T00:00:00Z");
            create(directory, DEMO_NAMES.get(2),
                    "2026-10-25T00:00:00Z");
            create(directory, DEMO_NAMES.get(3),
                    "2026-09-01T00:00:00Z");
            create(directory, DEMO_NAMES.get(4),
                    "2026-09-01T00:00:00Z");

            Instant now = Instant.parse("2026-11-09T00:00:00Z");
            Instant cutoff = now.minus(Duration.ofDays(30));

            review(directory, cutoff, false);
            review(directory, cutoff, true);

            System.out.println("OLD_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(0))));
            System.out.println("RECENT_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(2))));
            System.out.println("ACTIVE_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(3))));
        } finally {
            for (String name : DEMO_NAMES) {
                Files.deleteIfExists(directory.resolve(name));
            }
            Files.deleteIfExists(directory);
        }
    }

    private static void create(Path directory, String name,
                               String isoTime) throws IOException {
        Path path = directory.resolve(name);
        Files.writeString(path, "sample", StandardCharsets.UTF_8);
        Files.setLastModifiedTime(path,
                FileTime.from(Instant.parse(isoTime)));
    }

    private static void review(Path directory, Instant cutoff,
                               boolean apply) throws IOException {
        String phase = apply ? "APPLY" : "DRY_RUN";

        try (Stream<Path> stream = Files.list(directory)) {
            for (Path file : stream.sorted(
                    Comparator.comparing(
                            p -> p.getFileName().toString())).toList()) {

                String name = file.getFileName().toString();

                if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
                        || !ARCHIVE.matcher(name).matches()) {
                    System.out.println(phase + " SKIP " + name);
                    continue;
                }

                Instant modified = Files.getLastModifiedTime(
                        file, LinkOption.NOFOLLOW_LINKS).toInstant();

                if (modified.isBefore(cutoff)) {
                    System.out.println(phase + " DELETE " + name);
                    if (apply) {
                        Files.delete(file);
                    }
                } else {
                    System.out.println(phase + " KEEP " + name);
                }
            }
        }
    }
}
```

### Biên dịch và chạy

Lưu đúng tên `RetentionCleanupDemo.java`. Tại thư mục chứa file, với JDK 17 trở lên:

```bash
javac -encoding UTF-8 RetentionCleanupDemo.java
java RetentionCleanupDemo
```

**Stdout chính xác theo code trên:**

```text
DRY_RUN DELETE app-2026-10-01.log.gz
DRY_RUN KEEP app-2026-10-10.log.gz
DRY_RUN KEEP app-2026-10-25.log.gz
DRY_RUN SKIP current.log
DRY_RUN SKIP notes.txt
APPLY DELETE app-2026-10-01.log.gz
APPLY KEEP app-2026-10-10.log.gz
APPLY KEEP app-2026-10-25.log.gz
APPLY SKIP current.log
APPLY SKIP notes.txt
OLD_EXISTS=false
RECENT_EXISTS=true
ACTIVE_EXISTS=true
```

### Giải thích từng kết quả

1. Cutoff là `2026-10-10T00:00:00Z` vì `Duration.ofDays(30)` tính 30 × 24 giờ.
2. Archive ngày 01/10 có `mtime` cũ hơn cutoff, nên ở lượt dry-run chỉ in `DELETE`; lượt apply mới thực sự gọi `Files.delete(file)`.
3. Archive ngày 10/10 có `mtime` **bằng** cutoff. `Instant.isBefore()` trả về false, vì vậy nó được giữ.
4. Archive ngày 25/10 mới hơn cutoff, cũng được giữ.
5. `current.log` có mtime rất cũ nhưng **không khớp pattern archive**. Nó vẫn được giữ.
6. `notes.txt` cũng không khớp pattern nên không bị xóa.
7. `Files.list(directory)` chỉ duyệt con trực tiếp; `Files.isRegularFile(..., NOFOLLOW_LINKS)` giúp loại symbol link.
8. `stream.sorted(...)` bảo đảm thứ tự output ổn định, không phụ thuộc cách filesystem liệt kê.
9. `finally` chỉ dọn các tên demo đã tạo và thư mục tạm do chương trình tự quản lý; không tác động đường dẫn production.

**Giới hạn an toàn:** đây là bài tập, không phải công cụ xóa production. Kiểm tra `isRegularFile` rồi gọi `delete` vẫn có *time-of-check to time-of-use race* nếu một tiến trình khác được phép đổi file/symlink trong lúc cleanup. Nó chưa có legal hold, xác nhận collector, lock/lease, phân quyền và audit xóa. Không chuyển `directory` thành đường dẫn hệ thống thật và chạy trực tiếp.

## 11. Tại sao không xóa file đang mở?

Một active log có thể đang được appender mở bằng file descriptor/handle. Xóa nó có hậu quả tùy hệ điều hành:

- Trên hệ POSIX, unlink tên file có thể thành công, nhưng process vẫn ghi qua descriptor cũ; dung lượng có thể chưa được trả lại cho tới khi descriptor đóng.
- Trên Windows, thao tác xóa có thể thất bại vì file đang mở/được lock tùy chế độ chia sẻ.
- Collector đang tail một file có thể mất dấu nếu file bị rename/xóa không theo thiết kế.

Vì vậy không xóa `app.log` đang ghi chỉ vì `mtime` trông cũ. File hiện tại nên được quản lý bằng rolling appender và được xác nhận chuyển sang archive hoàn chỉnh trước khi áp dụng retention.

Với file nén hoặc upload đang xử lý, cũng không nên chọn nó chỉ vì tên giống archive. Cần quy ước file tạm và tiêu chí “archive completed”.

## 12. logrotate, cron và container runtime

Trên Linux, `logrotate` là một công cụ ngoài Java hỗ trợ rotate/cleanup theo lịch. Trong một số hệ thống container, stdout/stderr do runtime hoặc log driver xoay vòng, trong khi ứng dụng không sở hữu file vật lý của stream đó.

Nếu dùng công cụ ngoài:

- Chọn **một owner rõ ràng**: rolling framework, logrotate hoặc lifecycle policy tại storage.
- Không để logrotate và Logback/Log4j 2 cùng rotate một file theo hai cách độc lập.
- Các khái niệm `daily`, `rotate N`, `maxage N` và `compress` của logrotate không có nghĩa giống thuộc tính `maxHistory` ở mọi framework.
- `copytruncate` có thể làm mất một khoảng nhỏ dòng log khi writer tiếp tục ghi giữa bước copy và truncate; phải đánh giá rủi ro.
- Với collector/file shipper theo inode/offset, xác nhận nó hiểu chính sách rename/rotation, không bỏ sót archive.
- Với log container, ưu tiên xử lý retention bằng nền tảng hoặc kho trung tâm phù hợp, không tự xóa các file mà JVM không sở hữu.

Không đề xuất lệnh xóa wildcard thiếu allowlist hoặc lệnh xóa trực tiếp trong `/var/log` khi chưa biết chính xác đường dẫn và chủ sở hữu.

## 13. Nếu xóa xong mà disk vẫn đầy

Một job có thể báo đã xóa nhiều file nhưng dung lượng volume chưa giảm như kỳ vọng. Nguyên nhân:

1. File đã unlink nhưng process vẫn giữ descriptor mở.
2. Log mới được tạo nhanh hơn tốc độ dọn.
3. File lớn nhất nằm ngoài archive directory và không khớp rule.
4. Filesystem snapshot, backup hoặc overlay layers còn giữ dữ liệu.
5. Xóa thất bại vì permission nhưng lỗi không được theo dõi.
6. Tác vụ Delete chưa chạy do chưa rollover, hoặc Logback startup cleanup chưa bật.
7. Mtime của archive đã được cập nhật khi nén/copy nên không vượt ngưỡng.
8. Collector chưa đọc kịp khiến job chủ động bỏ qua file, đúng chính sách an toàn.

Cần đo riêng: số file ứng viên, số file đã xóa thành công, số byte xóa, disk usage thực tế, open file descriptors và ingestion lag. Không xem việc “đã lên lịch delete” là bằng chứng giải phóng ổ đĩa.

## 14. Bảo mật, quyền riêng tư và tuân thủ

Log có thể chứa sự kiện bảo mật, thông tin vận hành hoặc dữ liệu cá nhân. Chính sách xóa phải đồng bộ với:

- Thời hạn giữ tối thiểu và tối đa do tổ chức/quy định liên quan áp dụng.
- Legal hold hoặc lệnh bảo toàn chứng cứ khi có điều tra.
- Quyền riêng tư: không giữ dữ liệu nhạy cảm lâu hơn nhu cầu hợp pháp.
- Backup, remote collector, object storage và các bản sao khác.
- Phân quyền read/delete, audit người hoặc tiến trình thực hiện cleanup.

**Không ghi password, OTP, access token, refresh token, session cookie hay private key vào log dù có retention.** Việc xóa sau một tháng không giúp dữ liệu an toàn trong tháng đang tồn tại.

Tác vụ cleanup nên ghi các thông tin vận hành cần thiết: policy version, tập file đã xóa, số byte, thời điểm và lỗi; **không copy toàn bộ nội dung file bị xóa** vào log cleanup. Nếu yêu cầu kiểm toán cao, log của cleanup cũng cần được ghi vào đích an toàn, tránh bị chính job vừa tạo xong xóa mất.

## 15. Kiểm thử chiến lược xóa file quá hạn

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| File archive quá tuổi, đúng allowlist | Được chọn theo policy. |
| File ở đúng cutoff | Hành vi phù hợp toán tử so sánh của implementation. |
| File archive còn mới | Không xóa. |
| File active dù rất cũ | Không xóa khi writer còn sở hữu. |
| File cùng thư mục nhưng tên khác | Không xóa. |
| Symlink trỏ ra ngoài archive | Không follow/không xóa đích. |
| File đang nén hoặc shipper đang đọc | Bị loại cho tới khi hoàn tất. |
| File có tên ngày cũ nhưng mtime mới | Kết quả đúng theo nguồn thời gian đã chọn. |
| Nhiều file/ngày | MaxHistory theo kỳ, count theo file được phân biệt. |
| Service không ghi log nhiều ngày | Xác định cleanup có cần startup/scheduler trigger không. |
| Disk đầy hoặc permission denied | Lỗi được đo; không báo hoàn tất giả. |
| Multi-instance cùng cleanup | Có một owner/lock/lease để tránh race. |
| Có legal hold | File được giữ dù đã quá hạn. |
| File bị xóa khi collector chưa ACK | Phát hiện và ngăn việc mất event quan trọng. |
| Job crash ở giữa | Lần chạy sau xử lý an toàn/idempotent. |
| Volume không giảm sau unlink | Kiểm tra descriptor đang mở, snapshot hoặc nguồn khác. |

Những metric hữu ích:

- `log_archive_files_total`: số archive hiện có.
- `log_archive_bytes_total`: tổng dung lượng archive.
- `log_cleanup_candidates_total`: số file đủ điều kiện theo policy.
- `log_cleanup_deleted_total`: số file xóa thành công.
- `log_cleanup_deleted_bytes_total`: tổng byte của file xóa thành công.
- `log_cleanup_errors_total`: lỗi delete/permission/đường dẫn.
- `log_archive_oldest_age_seconds`: độ tuổi archive cũ nhất.
- `log_collector_lag_seconds`: độ trễ của hệ thu thập.

Đây là **tên metric đề xuất để minh họa**, không phải tất cả đều được Java/Logback/Log4j 2 phát ra mặc định. Khi biểu diễn metric, tránh dùng đường dẫn đầy đủ hoặc ID sự kiện duy nhất làm metric label có cardinality cao.

## 16. Quy trình triển khai retention có thể kiểm toán

1. **Khảo sát dữ liệu:** xác định nơi log được tạo, nơi lưu chính thức, archive local và các bản sao.
2. **Xác định policy đã phê duyệt:** tuổi/độ dài kỳ giữ, giới hạn tổng dung lượng, ngoại lệ và legal hold.
3. **Chọn owner:** rolling appender, cron/job hoặc storage lifecycle, tránh trùng quyết định.
4. **Tách thư mục:** active file và archive riêng, allowlist filename, quyền tối thiểu.
5. **Chọn cơ chế:** Logback `maxHistory/totalSizeCap`, Log4j 2 `Delete` và PathConditions, hoặc một job riêng khi có yêu cầu.
6. **Xác định khi nào cleanup chạy:** rollover, startup hay scheduler; kiểm tra trường hợp service ngủ dài ngày.
7. **Chạy dry-run/testMode:** ghi danh sách ứng viên, số lượng và byte; người có thẩm quyền kiểm tra.
8. **Test trên môi trường riêng:** boundary, symlink, permission, file đang ghi, collector lag, crash và restart.
9. **Bật xóa thật:** chỉ sau khi danh sách file đúng phạm vi và không vi phạm yêu cầu giữ.
10. **Quan sát:** đo file/byte thực xóa, lỗi, tuổi archive và dung lượng còn lại.
11. **Diễn tập phục hồi:** với log cần backup, xác minh bản lưu khác còn dùng được.
12. **Review định kỳ:** chính sách, pattern, version framework, lượng log và pháp lý có thể thay đổi.

**Đừng chỉ “thiết lập maxHistory rồi quên”.** Một retention policy hoàn tất khi có bằng chứng cleanup chạy đúng, không xóa nhầm và giữ được dữ liệu bắt buộc.

## 17. Các lỗi thường gặp

1. **Rotation tự dọn archive theo tuổi** dù chưa cấu hình retention.
2. **maxHistory=30 nghĩa là 30 file** dù pattern theo kỳ ngày.
3. **Giữ 10 file nghĩa là giữ 10 ngày** dù một ngày có hàng trăm file.
4. **Giả định mtime bằng ngày trong filename** sau khi copy, nén hoặc khôi phục.
5. **Dùng FileHandler count=5 làm age retention 5 ngày.**
6. **Tin rằng cleanup chạy lúc nửa đêm** dù chỉ gắn với rollover.
7. **Xóa mọi file *.log trong logs/** không có ownership/allowlist.
8. **Xóa active file** đang được appender mở.
9. **Bật followLinks và quét sâu** có thể vượt phạm vi archive.
10. **Không chạy testMode/dry-run** trước khi bật xóa thật.
11. **Xóa trước khi collector nhận** làm mất bản sao cuối cùng.
12. **Đồng thời chạy hai cleanup owners** không có phối hợp.
13. **Thấy disk chưa giảm rồi xóa thêm file** dù descriptor đang mở.
14. **Đặt tổng size cap thấp hơn mức tối thiểu cần giữ** nhưng không giải quyết xung đột yêu cầu.
15. **Dựa vào kiểm tra isRegularFile rồi delete như biện pháp chống race tuyệt đối.**
16. **Coi retention là cơ chế che giấu secret** thay vì redaction từ nguồn.

## 18. Checklist trước production

- [ ] Có policy được phê duyệt, xác định tuổi/kỳ và ranh giới xóa.
- [ ] Biết chủ sở hữu cleanup cho đúng archive directory.
- [ ] Active file được bảo vệ; archive nằm trong thư mục riêng.
- [ ] Tên file cho phép và nguồn thời gian được quy định chính xác.
- [ ] Cấu hình Logback/Log4j 2/JUL được chọn đúng framework và phiên bản.
- [ ] Phân biệt maxHistory, count/maxFiles và totalSizeCap.
- [ ] Biết cleanup được kích hoạt lúc rollover, startup hoặc theo lịch nào.
- [ ] Đã chạy dry-run/testMode và xác nhận danh sách file ứng viên.
- [ ] Không follow symlink ra ngoài, không xóa file đang xử lý.
- [ ] Đã kiểm tra legal hold và trạng thái collector/backup.
- [ ] Có metric/log lỗi, audit deletion và kiểm tra dung lượng sau cleanup.
- [ ] Đã test quyền ghi, disk đầy, restart, race, file đang mở và multi-instance.
- [ ] Có kế hoạch khôi phục cho dữ liệu bắt buộc.
- [ ] Không ghi token/password/PII không cần thiết vào log.
- [ ] Kiểm thử trên archive giả và xác nhận hành vi trên môi trường thực tế trước khi mở delete.

## Tài liệu tham khảo chính thức

- [Apache Log4j 2 — Rolling File Appenders và Delete Action](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Logback — RollingFileAppender, maxHistory, totalSizeCap](https://logback.qos.ch/manual/appenders-rolling.html)
- [Java 17 — Files, mtime và NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html)

**Ghi nhớ:** Xóa file quá hạn là một **chính sách lưu giữ có giới hạn về tuổi, tên file, đường dẫn và quyền**. Chọn đúng công cụ của logging backend khi có thể, chỉ xóa archive đã hoàn tất, không đụng active file, thử dry-run trước và đo kết quả thực tế; việc xóa local không đồng nghĩa mọi bản sao đã được xử lý.