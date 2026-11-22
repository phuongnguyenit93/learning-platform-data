# Đồng bộ rotation trong Java logging

## 1. Đồng bộ rotation là gì?

**Log rotation (log rollover)** là quá trình chuyển tệp log đang ghi thành tệp lưu trữ và mở hoặc tiếp tục một tệp hiện hành, thường khi đạt ngưỡng dung lượng, qua mốc thời gian hoặc lúc khởi động. **Đồng bộ rotation** là bảo đảm các bên tham gia ghi log và luân chuyển tệp không cùng lúc thực hiện những bước xung đột khiến bản ghi bị mất, lặp, ghi nhầm tệp hoặc hỏng trạng thái.

Ví dụ, một dịch vụ Java dùng:

```text
logs/application.log          # tệp đang ghi
logs/application.log.1        # bản gần nhất đã rotate
logs/application.log.2        # bản cũ hơn
```

Nếu hai thread cùng thấy `application.log` đã đầy, cả hai đều cố đổi tên, kết quả có thể sai:

```text
Thread A: kiểm tra kích thước -> cần rotation
Thread B: kiểm tra kích thước -> cần rotation
Thread A: đổi application.log thành application.log.1
Thread B: đổi application.log thành application.log.1 (tệp cũ đã đổi tên)
Thread A: mở tệp application.log mới
Thread B: ghi bằng handle cũ hoặc mở tệp khác
```

Đây là **race condition**: kết quả phụ thuộc thứ tự xen kẽ của các thao tác. Vấn đề không chỉ là hai dòng log có thể xuất hiện khác thứ tự; còn là **quyết định rotate, thao tác với file và chuyển người ghi sang file mới phải phối hợp đúng**.

Một triển khai cần làm rõ **phạm vi đồng bộ**:

1. Nhiều thread trong **một tiến trình JVM**, dùng chung một logging manager.
2. Nhiều logger/appender hoặc nhiều logger context **trong cùng JVM**.
3. Hai hoặc nhiều **JVM/tiến trình độc lập** ghi vào cùng đường dẫn tệp.
4. Ứng dụng cùng một **công cụ rotate bên ngoài**, như `logrotate` trên Linux.
5. Nhiều container/pod dùng cùng **volume hoặc filesystem mạng**.
6. Một log shipper/collector đang đọc tệp trong lúc nó bị đổi tên, nén hoặc xóa.

**`synchronized` trong Java chỉ giải quyết việc phối hợp giữa các thread dùng cùng monitor trong một JVM.** Nó không tự bảo vệ tài nguyên trước JVM khác, công cụ `logrotate` hay tác nhân bên ngoài.

## 2. Những bất biến cần bảo vệ

Một quy trình rotation tốt nên có những tính chất sau, trong phạm vi bảo đảm được thiết kế:

| Bất biến | Ý nghĩa |
| --- | --- |
| **Một quyết định rollover cho một mốc** | Không có hai tác nhân cùng rotate một trạng thái tệp mà không nhận ra nhau |
| **Một thứ tự ghi rõ ràng trong phạm vi được bảo vệ** | Bản ghi được serialize hợp lệ và không bị chia xen ở các điểm nguy hiểm |
| **Không ghi tiếp vào tệp sai ngoài ý muốn** | Writer cần mở/rebind handle thích hợp khi tệp hiện hành được thay |
| **Tên archive không va chạm** | Không vô tình overwrite archive quan trọng bởi hai lần rotate đồng thời |
| **Retention không xóa dữ liệu đang được dùng** | Không nén/xóa archive mà writer hoặc collector còn phụ thuộc chưa xử lý |
| **Không xuất trùng ngoài ý muốn** | Một sự kiện không tự trở thành hai bản ghi chỉ do cấu hình appender/collector |
| **Lỗi được phát hiện và có chính sách** | Nếu rename, open, compress hoặc flush thất bại, không im lặng coi hệ thống an toàn |
| **Có giới hạn phạm vi cam kết** | Không tuyên bố “không mất log” khi chưa có cơ chế ghi bền và xác nhận đầy đủ |

Trong bài tập một JVM, có thể kiểm thử “12 sự kiện được lưu thành đúng 12 dòng khác nhau”. Trong hệ thống phân tán, một yêu cầu “không mất bất kỳ log nào kể cả khi crash” còn liên quan đến queue bền vững, flush/fsync, lưu trữ, xác nhận từ collector và chiến lược khôi phục; **mutex hay `synchronized` một mình không giải quyết được**.

### Rotation là một chuỗi thao tác có trạng thái

```text
Nhận sự kiện mới
      |
      v
Kiểm tra policy (size/time)
      |
      +--- chưa tới ngưỡng ----> ghi vào tệp hiện hành
      |
      +--- tới ngưỡng --------> giữ quyền điều phối rotation
                                  |
                                  v
                         flush/đóng hoặc đổi handle
                                  |
                                  v
                         archive/rename tệp cũ
                                  |
                                  v
                         mở/đặt tệp hiện hành mới
                                  |
                                  v
                         ghi sự kiện tiếp theo
                                  |
                                  v
                         cho các writer khác tiếp tục
```

Cách triển khai cụ thể phụ thuộc framework. Không nhất thiết mọi appender đều đóng file trước mọi thao tác hoặc thực hiện nén đồng bộ; một số có manager và tác vụ nén bất đồng bộ. Điều quan trọng là **những bước có thể xung đột phải được điều phối**, trong khi thao tác hậu xử lý có thể được tách nếu framework bảo đảm đủ an toàn.

## 3. Race condition thường thấy khi nhiều thread ghi

Giả sử mỗi thread kiểm tra dung lượng như sau:

```java
// Chỉ minh họa ý tưởng sai, không phải chương trình độc lập.
if (Files.size(logFile) >= limitBytes) {
    rotate(logFile);
}
append(logFile, message);
```

Đoạn code này có nhiều vấn đề:

- **Check-then-act race:** sau khi thread A đo dung lượng, thread B có thể đã ghi hoặc rotate.
- **Không đồng bộ đổi tên:** hai thread có thể cùng di chuyển tệp sang cùng tên archive.
- **Lệch trạng thái nội bộ:** bộ đếm số dòng, số byte, chỉ số archive có thể không khớp tệp thực.
- **Ghi khi tệp đang đổi:** file handle cũ vẫn trỏ đến đối tượng file cũ trên một số nền tảng; trên nền tảng khác, rename có thể bị từ chối vì file còn mở.
- **Vượt ngưỡng:** hai thread đồng thời kiểm tra trước khi append khiến kích thước tệp vượt xa mức dự kiến.
- **Mất thông tin lỗi:** nếu code chỉ log một exception khi rotate nhưng không có chiến lược phục hồi, hệ thống có thể tiếp tục ghi vào sai đích.

Trong Java, `volatile boolean rotating` **không đủ** để làm cả chuỗi kiểm tra–rotate–ghi trở thành thao tác nguyên tử. `volatile` cung cấp một số bảo đảm về visibility/order của biến, không tự tạo critical section cho nhiều thao tác file.

Sử dụng một **monitor chung**, `Lock` hoặc logging manager có đồng bộ nội bộ phù hợp là cách giải quyết trong **một tiến trình**. Trong thực tế, **không nên tự viết rolling logger mới nếu Log4j2/Logback đã có rolling appender phù hợp**.

## 4. Phạm vi một JVM: dùng chung manager thay vì mỗi logger tự rotate

Trong ứng dụng sử dụng logging framework:

```text
HTTP thread A ----\
HTTP thread B -----+--> Shared Rolling Appender/Manager --> active log file
Worker thread C --/
```

Một appender/manager chia sẻ có thể quyết định cách serialize các sự kiện và điều phối rollover theo thiết kế của thư viện. Điều này khác hẳn với việc ba thread tự viết ba đoạn mã `Files.move(...)` độc lập.

Các thực hành nên có:

1. Cấu hình appender **một lần khi khởi tạo**, sau đó để logger các lớp sử dụng.
2. Để framework quản lý policy, đổi tên tệp, buffer, tài nguyên mở và vòng đời đóng.
3. Không `new FileHandler`/`new RollingFileAppender` cho **mỗi request**.
4. Không để nhiều module tự chọn cùng `fileName` nhưng khác `filePattern` hoặc retention mà chưa hiểu khả năng chia sẻ manager.
5. Không dùng monitor trên một đối tượng ứng dụng bất kỳ rồi nghĩ mọi logger khác JVM đang dùng cùng monitor.
6. Xác định rõ lúc ứng dụng shutdown/rolling reconfigure, tránh hai đời appender cùng chủ động quản lý một đường dẫn.

Với Log4j2, tài liệu Rolling File Appenders nêu các appender cùng `fileName` (hoặc cùng `filePattern` khi không có `fileName`) **có thể chia sẻ `RollingFileManager`** trong phạm vi runtime quản lý thích hợp. Việc dùng cùng manager giúp tránh rollover lặp **trong phạm vi chia sẻ manager đó**, nhưng **không phải khóa phân tán cho nhiều JVM**.

Khi nhiều manager độc lập ghi cùng file, Log4j2 có thể tính kích thước không chính xác vì nó dựa vào dữ liệu mỗi manager đã ghi, không phải liên tục đo được toàn bộ phần ghi của những process khác. Đây là lý do không nên suy ra rằng hai JVM dùng cùng `filePattern` sẽ phối hợp rotation an toàn.

## 5. Ví dụ Java 17+ chạy được: đồng bộ rotate giữa hai thread

Để thấy nguyên tắc mà không phụ thuộc framework, chương trình sau minh họa **một writer chung**, có phương thức `synchronized append`. Writer giữ tệp hiện hành và hai bản archive; cứ **4 dòng** thì rotate. Hai thread cùng ghi **6 bản ghi** vào một writer. Ví dụ chủ ý rotate theo **số dòng** (dễ kiểm chứng), không dùng kích thước/timestamp.

**Giới hạn quan trọng:** đây là **mô hình giáo dục trong một JVM**, không phải rolling appender hoàn chỉnh hoặc giải pháp production. Nó mở/đóng file trên mỗi append cho đơn giản, không có xử lý mất điện, disk full, multi-process locking, nén, collector, async queue hoặc kiểm soát quyền truy cập.

Lưu toàn bộ mã vào **`SynchronizedRotationDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class SynchronizedRotationDemo {
    private static final int MAX_LINES = 4;

    private SynchronizedRotationDemo() {
    }

    private static final class RollingWriter {
        private final Path active;
        private int linesInActive;
        private int rollovers;

        private RollingWriter(Path active) {
            this.active = active;
        }

        synchronized void append(String record) throws IOException {
            if (linesInActive == MAX_LINES) {
                rotate();
            }

            Files.writeString(active, record + "\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
            linesInActive++;
        }

        private void rotate() throws IOException {
            Path first = active.resolveSibling("app.log.1");
            Path second = active.resolveSibling("app.log.2");

            Files.deleteIfExists(second);
            if (Files.exists(first)) {
                Files.move(first, second,
                        StandardCopyOption.REPLACE_EXISTING);
            }
            if (Files.exists(active)) {
                Files.move(active, first,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            linesInActive = 0;
            rollovers++;
        }

        synchronized int rollovers() {
            return rollovers;
        }
    }

    private static void writeSix(
            RollingWriter writer, String prefix) {
        for (int i = 1; i <= 6; i++) {
            try {
                writer.append(prefix + "-" + i);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("rotation-lab-");

        try {
            RollingWriter writer =
                    new RollingWriter(directory.resolve("app.log"));
            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<?> first =
                        pool.submit(() -> writeSix(writer, "A"));
                Future<?> second =
                        pool.submit(() -> writeSix(writer, "B"));

                first.get();
                second.get();
            } finally {
                pool.shutdownNow();
            }

            List<String> observed = new ArrayList<>();
            for (String name : List.of(
                    "app.log.2", "app.log.1", "app.log")) {
                observed.addAll(Files.readAllLines(
                        directory.resolve(name),
                        StandardCharsets.UTF_8));
            }

            Set<String> expected = new HashSet<>();
            for (int i = 1; i <= 6; i++) {
                expected.add("A-" + i);
                expected.add("B-" + i);
            }

            Set<String> distinct = new HashSet<>(observed);
            boolean verified =
                    observed.size() == 12
                    && distinct.equals(expected)
                    && writer.rollovers() == 2;

            System.out.println("records=" + observed.size());
            System.out.println("unique=" + distinct.size());
            System.out.println("rollovers=" + writer.rollovers());
            System.out.println("verified=" + verified);
        } finally {
            for (String name : List.of(
                    "app.log.2", "app.log.1", "app.log")) {
                Files.deleteIfExists(directory.resolve(name));
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac -encoding UTF-8 SynchronizedRotationDemo.java
java SynchronizedRotationDemo
```

**Stdout chính xác trong điều kiện đọc/ghi file thành công:**

```text
records=12
unique=12
rollovers=2
verified=true
```

**Stderr:** không có output từ chương trình khi không có lỗi.

### Vì sao kết quả xác định dù hai thread chạy không xác định thứ tự?

- Thread A tạo `A-1` đến `A-6`; thread B tạo `B-1` đến `B-6`.
- Thứ tự **xen kẽ giữa A và B không cố định** do scheduler của JVM, nhưng mỗi bản ghi vẫn được ghi **một lần** vì mỗi thread lặp đúng 6 lần.
- Hai thread chia sẻ **cùng một đối tượng `RollingWriter`**.
- Phương thức `synchronized append` giữ cùng monitor khi **kiểm tra ngưỡng, rotate và ghi**. Vì thế thread kia không thể vào `append` ở giữa chuỗi thao tác đó.
- Sau 4 bản ghi, sự kiện thứ 5 làm rollover lần một; sau 8 bản ghi, sự kiện thứ 9 làm rollover lần hai; cuối cùng có hai archive và tệp hiện hành.
- Chương trình đọc cả `app.log.2`, `app.log.1` và `app.log`, không quan tâm record nào nằm ở tệp nào.
- `Set` kiểm tra đủ 12 ID mong đợi. Kết hợp `observed.size() == 12` giúp phát hiện cả thiếu ID lẫn trùng dòng.
- `Future.get()` chờ hai tác vụ hoàn thành và sẽ báo lỗi nếu một tác vụ ném exception; việc kiểm đếm chỉ diễn ra sau đó.
- Tệp được đặt trong một **thư mục tạm riêng** và bị xóa sau khi kiểm chứng; chương trình không đụng tới log production của người học.

### Giới hạn của demo

`synchronized` chỉ bảo vệ monitor của **writer này trong JVM này**. Nếu tạo **hai RollingWriter khác nhau** trỏ cùng `app.log` thì mỗi đối tượng có lock riêng; chúng không được phối hợp. Nếu chạy **hai JVM**, `synchronized` của JVM A không liên quan tới JVM B.

Ngoài ra, các thao tác `delete/move/move` là nhiều bước riêng. `Files.move` không biến **cả chuỗi rotation** thành một giao dịch file-system nguyên tử. Nếu lỗi giữa chừng hoặc tiến trình crash, có thể còn trạng thái archive chưa hoàn chỉnh. Chương trình cũng không cố thực hiện `ATOMIC_MOVE` vì khả năng hỗ trợ và ngữ nghĩa khác theo filesystem. Trong production hãy dùng logging framework, cấu hình retention an toàn và đường lưu bền phù hợp.

## 6. Log4j2: RollingFileAppender và việc điều phối rollover

**Apache Log4j 2** có `RollingFileAppender` và `RollingRandomAccessFileAppender`. Chúng kết hợp:

- **Appender/manager**: giữ tài nguyên file và thực hiện ghi.
- **TriggeringPolicy**: quyết định **khi nào** cần rollover theo dung lượng/thời gian/khởi động.
- **RolloverStrategy**: quyết định **chuyển file như thế nào**, tên archive, số archive, nén và cleanup.
- **Layout**: định dạng từng LogEvent trước khi ghi.

Ví dụ file **`log4j2.xml`** ở `src/main/resources`, dùng một tệp hiện hành và file archive theo ngày/chỉ số:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="logs/application.log"
                     filePattern="logs/application-%d{yyyy-MM-dd}-%i.log.gz"
                     append="true">
            <PatternLayout charset="UTF-8"
                    pattern="%d{ISO8601} %-5p %c{1} - %m%n%ex"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="10 MB"/>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
            </Policies>
            <DefaultRolloverStrategy max="7"/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
```

Cấu hình này minh họa **một Logging Manager** nhận sự kiện từ những logger trong một ứng dụng, không yêu cầu người dùng tự khóa file ở từng nơi gọi `LOG.info`.

**Chú ý với filePattern**:

- `%d{yyyy-MM-dd}` đóng dấu mốc thời gian của archive, phù hợp khi dùng time policy.
- `%i` cho phép có **nhiều archive trong cùng một chu kỳ thời gian** khi size policy kích hoạt nhiều lần. Bỏ `%i` trong một cấu hình size+time có thể làm tên đích bị trùng và có nguy cơ ghi đè.
- `max="7"` là số chỉ số archive tối đa theo chiến lược phù hợp, **không tự đồng nghĩa “giữ đúng 7 ngày log”** khi mỗi ngày có thể nhiều archive. Chính sách thời hạn lưu theo ngày/dung lượng tổng cần được thiết kế riêng.
- `TimeBasedTriggeringPolicy` thường được đánh giá khi có LogEvent đi vào rolling path, không nên coi mọi trường hợp là có một timer bắt buộc đổi file chính xác lúc 00:00 khi không có log. `CronTriggeringPolicy` có cơ chế lịch khác và có thể đặt log gần ranh giới lịch vào file của chu kỳ kề.
- **Không bật đồng thời hai chính sách time-based khác nhau** mà không kiểm tra tài liệu; Log4j2 cảnh báo kết quả không xác định khi cùng dùng cả Cron và TimeBased policy.

### Đồng bộ trong Log4j2 có phạm vi

Tài liệu Apache nêu các appender cùng tên tệp hiện hành trong một môi trường chia sẻ `RollingFileManager` thích hợp có thể dùng cùng manager, giúp tránh rollover kép **trong phạm vi manager**. Nhưng không được suy ra rằng appender của **JVM khác** sẽ dùng manager đó.

Điểm cần phân biệt:

| Trường hợp | Mức phối hợp |
| --- | --- |
| Nhiều thread → **một** RollingFileAppender | Appender/manager điều phối việc ghi và rollover trong runtime của nó |
| Nhiều logger → cùng AppenderRef | Vẫn đi qua cùng appender; thường là cấu hình ưu tiên |
| Nhiều logger context trong JVM có thể chia sẻ manager | Có cơ chế chia sẻ `RollingFileManager` theo tài liệu và điều kiện tương thích cấu hình |
| Hai JVM riêng biệt dùng chung đường dẫn file | **Không** tự chia sẻ manager trong bộ nhớ; rủi ro va chạm rotation |
| Hai container cùng mount shared volume vào cùng tên file | Không có mutex phân tán mặc định; cần thay kiến trúc hoặc cơ chế phối hợp khác |

Log4j2 có tùy chọn `locking` trên một số file/rolling appender, nhưng **file locking không tự giải quyết mọi race của rollover**, đặc biệt khi có process khác, rename, archive retention và filesystem mạng. Ngữ nghĩa lock có thể là advisory theo hệ điều hành, nên phải kiểm chứng ứng dụng **cùng tuân thủ giao thức khóa**.

Một điểm đặc biệt: khi nhiều manager độc lập ghi cùng file, kích thước do mỗi manager theo dõi có thể không phản ánh đầy đủ những lần ghi của manager khác. Như vậy, ngay cả khi thao tác append thường xuyên “có vẻ hoạt động”, **ngưỡng size rollover** vẫn có thể bị quyết định sai.

Tài liệu: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html

## 7. Logback: RollingFileAppender và prudent mode

Trong **Logback** (thường dùng với SLF4J), `RollingFileAppender` kết hợp `RollingPolicy` và có thể thêm `TriggeringPolicy` tùy loại. Mã Java sử dụng `org.slf4j.Logger` không tự xác định file được rotate khi nào; phải xem provider và file cấu hình `logback.xml`.

Một mẫu cơ bản cho **một tiến trình quản lý một tệp**:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

Đây là **cấu hình Logback**, không phải Log4j2. `maxHistory` và `totalSizeCap` hỗ trợ chính sách lưu trữ; phải kiểm tra tính năng/phiên bản Logback thực tế, cách giới hạn tổng dung lượng và tác động khi cleanup chạy.

### Prudent mode và nhiều JVM

Logback có **prudent mode** nhằm hỗ trợ nhiều JVM ghi vào cùng tệp theo cơ chế phối hợp file access, nhưng tài liệu nêu rõ những **giới hạn quan trọng**:

1. `FixedWindowRollingPolicy` không được hỗ trợ trong prudent mode.
2. Trong prudent mode với `TimeBasedRollingPolicy`, **không cho phép nén archive**.
3. Thuộc tính `file` của RollingFileAppender phải **để trống/không chỉ định** vì nó không được phép cố định vào file đang hoạt động theo cách đó.

Ví dụ cấu hình tham khảo cho trường hợp cần prudent mode:

```xml
<configuration>
    <appender name="PRUDENT"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <prudent>true</prudent>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/shared.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="PRUDENT"/>
    </root>
</configuration>
```

**Không thêm `<file>logs/shared.log</file>` hoặc `.gz` vào fileNamePattern của prudent mode này.** Kể cả khi hệ thống hỗ trợ ghi có phối hợp, prudent mode **không biến một thư mục shared NFS/SMB thành kho log phân tán bền vững**, và việc dùng lock có thể làm giảm hiệu năng. Trong hầu hết hệ thống triển khai nhiều replica, **mỗi process ghi log riêng rồi thu qua agent** thường đơn giản và an toàn hơn.

Tài liệu: https://logback.qos.ch/manual/appenders-rolling.html

## 8. JUL FileHandler: giới hạn và tính duy nhất theo tiến trình

**`java.util.logging.FileHandler`** của JDK có thể ghi luân phiên các tệp theo giới hạn kích thước và số tệp. Ví dụ cấu hình thông qua code:

```java
import java.util.logging.FileHandler;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("example");
FileHandler file = new FileHandler(
        "logs/app.%u.%g.log", 1_000_000, 5, true);
logger.addHandler(file);
```

Đây là **đoạn minh họa trong một phương thức đã có thư mục `logs`**, không phải chương trình Java chạy độc lập.

Trong `FileHandler`:

- `limit`: ngưỡng byte cho một tệp theo cơ chế handler.
- `count`: số tệp generation trong vòng quay.
- `%g`: số generation dùng cho tên tệp.
- `%u`: số uniqueness có ích để giảm va chạm với handler/tiến trình khác.
- `append`: chọn có ghi tiếp phần hiện có hay không.
- Handler còn có formatter, level và vòng đời `close` riêng.

`%u` **không đồng nghĩa nhiều JVM cùng quản lý một archive chung**. Một cách an toàn phổ biến là cho các tiến trình dùng những file riêng hoặc để hạ tầng gom log sau đó.

Với JUL, `FileHandler` khác với `ConsoleHandler`; cái sau xuất stderr theo JDK mặc định, không tự tạo rotation trên disk. Đừng trộn file pattern của JUL như `%u`/`%g` với Log4j2 `%d`/`%i` hoặc Logback `%d`/`%i`: mỗi hệ thống có quy tắc cấu hình riêng.

Tài liệu JDK: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

## 9. Khi có nhiều JVM hoặc nhiều container: đừng dùng chung một active file

Tình huống nguy hiểm:

```text
JVM A ---\
          +---- /shared/logs/application.log
JVM B ---/
          |
          +---- cả A và B có rolling policy riêng
```

Ngay cả khi cả hai JVM ghi được từng dòng, sự phối hợp **rotation** còn bao gồm:

- Cùng biết file nào là active và file nào là archive.
- Thống nhất thời điểm đổi tên tệp.
- Biết chỉ số archive nào đang được dùng.
- Không xóa archive mà JVM khác vẫn coi là active hoặc còn cần.
- Không tính kích thước dựa vào bộ đếm riêng không chứa byte từ JVM khác.
- Đảm bảo mọi process áp dụng cùng cơ chế file locking (nếu dùng).
- Hiểu filesystem mạng xử lý rename, cache, lock và crash thế nào.

**Khuyến nghị ưu tiên:** cho mỗi JVM/container có một active log độc lập, rồi để **agent/collector** hợp nhất sự kiện tại nơi thu thập.

```text
JVM A -> stdout hoặc app-A.log ----\
                                    +--> log collector --> search / retention
JVM B -> stdout hoặc app-B.log ----/
```

Mỗi process tự quản lý rotation của **tệp riêng** (hoặc không tự rotate nếu ghi stdout). Collector có thể gắn `service`, `instance_id`, `hostname`, `pod`, `trace_id` để người vận hành truy vấn tổng hợp mà không cần nhiều process chạm cùng một file.

Nếu tổ chức bắt buộc dùng một shared file, cần đánh giá cấu hình/phương thức được backend hỗ trợ (ví dụ một số trường hợp prudent mode của Logback), filesystem, quyền, lock, throughput và thử chịu lỗi. Đừng ngầm coi `Files.move(..., ATOMIC_MOVE)` cùng một `FileLock` là đủ để xây shared rolling logger cho production.

## 10. Rotation bởi ứng dụng so với `logrotate` bên ngoài

Trên Linux, `logrotate` thường được lên lịch qua cron/systemd để đổi tên, nén và dọn tệp. Nó **không biết** những lock trong một class Java nếu không có giao thức phối hợp.

Hai tình huống phổ biến:

### Đổi tên rồi tạo file mới

```text
Trước:
  application.log (ứng dụng đang mở file descriptor)

logrotate:
  rename application.log -> application.log.1
  create application.log mới

Ứng dụng:
  có thể vẫn giữ file descriptor trỏ đến file cũ
```

Trên hệ điều hành kiểu POSIX, đổi tên đường dẫn **không tự thay đổi đối tượng file mà descriptor đang mở trỏ tới**. Vì vậy ứng dụng có thể tiếp tục ghi vào file đã bị đổi tên cho đến khi nó đóng/mở lại descriptor. Trên một số môi trường khác, rename có thể bị cấm khi file vẫn mở.

Cách giải quyết cần **ứng dụng biết mở lại tệp một cách an toàn** sau tín hiệu/hook phù hợp, hoặc dùng rolling appender tự quản lý tệp. Không giả định mọi Java logging appender đều hỗ trợ nhận signal rồi reopen.

### `copytruncate`

`copytruncate` là cách `logrotate` sao chép file đang ghi sang archive rồi **truncate file hiện hành về rỗng**. Nó hữu ích với tiến trình không dễ yêu cầu reopen, nhưng có một **khoảng thời gian giữa copy và truncate** mà dữ liệu mới được ghi có thể **không nằm trong bản copy rồi bị cắt khỏi active file**.

Đây là **giới hạn được ghi rõ trong manual logrotate**, không phải lỗi riêng của Java. Ví dụ cấu hình:

```text
/var/log/my-service/application.log {
    size 10M
    rotate 7
    copytruncate
    compress
    missingok
    notifempty
}
```

Đoạn trên là **mẫu cấu hình logrotate**, không phải XML của Log4j2 hay Logback. Không đưa nó vào production mà chưa kiểm tra đường dẫn và chủ sở hữu file.

**`copytruncate` không bảo đảm không mất log**. Nó có thể làm dữ liệu biến mất ở cửa sổ copy–truncate dưới tải cao. Do đó khi ứng dụng Java đã sử dụng RollingFileAppender chính thức, thường nên để **framework chịu trách nhiệm rotation**, và không cho `logrotate` cùng lúc quản lý đúng tệp đó.

Tài liệu: https://man7.org/linux/man-pages/man8/logrotate.8.html

## 11. Cảnh báo khi dùng appender file thường với rotate bên ngoài

Theo tài liệu Log4j2, các **File Appender** thông thường không cung cấp cơ chế để ứng dụng ngoài ép reopen file đang mở. Nếu một công cụ ngoài đổi tên tệp, file descriptor của ứng dụng vẫn có thể trỏ vào file cũ. Vì vậy việc phối hợp với logrotate thường dẫn đến cách `copytruncate` có cửa sổ mất dữ liệu.

Điều này dẫn đến một quy tắc thực tế:

- Dùng `FileAppender` nếu có **lý do không cần appender tự rotation** và đường lưu phù hợp.
- Dùng `RollingFileAppender` nếu muốn **Log4j2 quản lý rollover và archive**.
- Dùng `ConsoleAppender` ghi stdout/stderr khi hạ tầng container đã đảm nhận thu và rotation ở tầng runtime.
- Nếu muốn logrotate bên ngoài quản lý, chọn một thiết kế được **ứng dụng và công cụ rotate hỗ trợ rõ**, không chỉ đặt cron và hy vọng file descriptor tự chuyển.

Tài liệu Log4j2: https://logging.apache.org/log4j/2.x/manual/appenders/file.html

## 12. Async logging và đồng bộ rotation

**Async logging** làm giảm thời gian một thread nghiệp vụ phải chờ thao tác ghi bằng cách đưa LogEvent vào queue rồi để một thread khác xử lý. Nhưng async không tự xóa vấn đề phối hợp tệp:

```text
Request threads
    |
    v
Async queue
    |
    v
Consumer / file manager
    |
    v
Rolling appender + rotation
    |
    v
File
```

Trong một thiết kế thông thường, một consumer/manager xử lý sự kiện theo đường ghi được điều phối, giúp hạn chế tác động tới thread request. Tuy nhiên:

- **Queue đầy** có thể khiến ứng dụng chặn, bỏ sự kiện hoặc chuyển hành vi khác theo cấu hình.
- **Crash trước flush/drain** có thể làm mất những sự kiện còn trong memory.
- **Thứ tự giữa nhiều thread** chỉ có ý nghĩa theo thứ tự queue chấp nhận sự kiện, không nhất thiết theo thời điểm nghiệp vụ từ xa.
- **Rotation lúc queue còn dữ liệu** phải do framework quản lý; không tự đổi tên tệp bên ngoài trong lúc async worker đang ghi.
- **Stop/shutdown** phải có cơ chế chờ/drain trong phạm vi thời gian và hợp đồng được cấu hình.
- **Đổi cấu hình nóng** có thể tạo appender mới; cần tránh hai đời appender cùng chủ động rotate một file.

**AsyncAppender không đồng nghĩa durable message queue.** Nếu yêu cầu tuân thủ hoặc audit không cho phép mất dữ liệu, cần một kênh lưu bền được thiết kế riêng, không chỉ tăng queue của appender.

## 13. Compression, archive cleanup và retention

Một rotation không chỉ tạo file mới. Thường có các tác vụ:

1. Chuyển file hiện hành thành archive (rename/move).
2. Nén archive, ví dụ `.gz`.
3. Cập nhật chỉ số/đường dẫn theo chính sách.
4. Xóa archive cũ theo số file, ngày hoặc dung lượng tổng.
5. Tiếp tục ghi file hiện hành.
6. Để agent/collector đọc những archive chưa ingest hết nếu pipeline yêu cầu.

Những bước hậu xử lý có thể chạy **bất đồng bộ**, nên tồn tại thêm tình huống cạnh tranh:

- Vừa rename archive thì lần rotation tiếp theo cũng muốn dùng cùng tên.
- Tiến trình nén đọc archive trong khi một writer khác vẫn đang ghi vào inode đó.
- Cleanup xóa file mà log shipper đang đọc chưa hoàn tất.
- Một file archive chưa có metadata cuối cùng nhưng collector đã phát hiện và ingest một phần.
- Retention quá ngắn làm collector chưa thu xong đã mất file.

Cần quy ước **tên archive không va chạm**, cho phép chỉ số tăng khi nhiều lần rotate cùng ngày, tách trách nhiệm archive của writer và hạ tầng đọc, kiểm tra cách log shipper xử lý rename/truncate.

Đừng mặc định `maxHistory=7` hoặc `max=7` đều mang ý nghĩa “7 ngày” ở mọi backend. Tên thuộc tính giống hoặc gần nhau không đồng nghĩa ngữ nghĩa tương đồng. Với time + size policy, một ngày có thể tạo nhiều file.

## 14. Rotation theo thời gian và đồng bộ đồng hồ

Rotation theo ngày/giờ có thêm vấn đề:

- **Timezone khác nhau:** hai máy có thể cắt ngày theo múi giờ khác nhau nếu cấu hình mặc định dựa vào hệ thống.
- **Đồng hồ được chỉnh (NTP/manual):** thay đổi giờ có thể làm policy nhìn thấy mốc không như dự kiến.
- **DST:** một ngày tại một số timezone có thể dài 23 hoặc 25 giờ; không nên suy diễn mọi ngày đều 24 giờ.
- **Thời gian của LogEvent khác thời gian file được rotate:** queue async và trễ xử lý có thể khiến sự kiện gần ranh giới nằm trong archive khác.
- **Cron policy:** một số cơ chế có timer và có thể rotate gần mốc định sẵn, nhưng LogEvent ranh giới có thể phân bố khác mong đợi.
- **TimeBased policy:** hoạt động theo mốc thời gian tính từ filePattern, nên cần kiểm tra hành vi khi không có log đi vào.
- **Nhiều replica khởi chạy ở mốc khác nhau:** một quy ước theo UTC và file riêng cho từng process dễ hiểu hơn cố tạo tên archive chung.

Cách giảm rủi ro:

1. Thống nhất timezone (nhiều hệ thống chọn UTC) ở chính sách logging.
2. Chọn timestamp có offset rõ trong bản ghi, độc lập tên file archive.
3. Dùng `filePattern` thể hiện chu kỳ và chỉ số khi cần nhiều file cùng chu kỳ.
4. Test tình huống trước/sau mốc rollover và lúc chạy lại chương trình sau downtime.
5. Không coi tên archive là bằng chứng chính xác tuyệt đối về thời gian từng sự kiện bên trong.

## 15. Rename, lock và atomicity của filesystem

Các thao tác liên quan:

| Cơ chế | Cung cấp gì | Không cung cấp gì |
| --- | --- | --- |
| `synchronized` | Mutual exclusion giữa thread dùng cùng monitor trong JVM | Không khóa JVM khác hoặc công cụ ngoài |
| `ReentrantLock` | Lock tường minh giữa thread cùng chia sẻ object lock | Không phải distributed lock |
| `FileChannel.lock()` | Khóa file ở mức OS theo API Java, trong phạm vi hệ thống hỗ trợ | Không tự phối hợp cả quyết định rollover, nhiều tên file và retention; có thể advisory |
| `Files.move(...)` | Chuyển tên/vị trí file theo filesystem | Không làm nhiều thao tác move/delete trở thành một transaction |
| `StandardCopyOption.ATOMIC_MOVE` | Yêu cầu move nguyên tử nếu provider/filesystem hỗ trợ | Không bảo đảm hỗ trợ mọi hệ thống hoặc atomic cho cả chuỗi rotate |
| `flush()` | Đẩy dữ liệu khỏi buffer ở tầng liên quan | Không tự xác nhận collector lưu bền, không luôn tương đương fsync |
| `FileChannel.force(...)` | Yêu cầu đồng bộ cập nhật file với thiết bị lưu trữ theo hợp đồng API | Không tự cung cấp exactly-once ở hệ thống log phân tán |

Với `ATOMIC_MOVE`, cần xử lý `AtomicMoveNotSupportedException` khi provider không hỗ trợ. Trên Windows, việc move file vẫn đang được tiến trình giữ mở có thể gặp hạn chế khác POSIX. Với NFS/SMB, cache, lock và semantics cần được thử trên hệ thống thực.

Ngay cả khi một thao tác rename riêng là atomic, tổng thể:

```text
delete archive.2
move archive.1 -> archive.2
move active -> archive.1
open new active
```

**không nguyên tử như một giao dịch**. Nếu crash giữa bước thứ 2 và 3, trạng thái archive có thể khác bình thường. Do đó việc khôi phục sau restart và logic xử lý lỗi cần có thiết kế thực tế.

## 16. Khi rotation lỗi: cần xử lý và giám sát gì?

Các nguồn lỗi phổ biến gồm:

| Lỗi / tình huống | Hệ quả có thể có | Cách kiểm tra |
| --- | --- | --- |
| Đĩa đầy hoặc quota hết | Ghi log/rotate thất bại | Disk usage, quota, trạng thái appender |
| Không có quyền rename/xóa | Rollover thất bại hoặc file giữ nguyên | Owner, permissions, filesystem |
| Archive trùng tên | File có thể bị overwrite hoặc rotate không thành công | `filePattern`, policy, nhiều writer |
| Hai process cùng rotate | Tên tệp/bộ đếm bị lệch | Có dùng chung active file không |
| File descriptor còn mở | Rename/reopen có thể không như kỳ vọng | Hệ điều hành, appender manager, công cụ ngoài |
| Nén archive bị lỗi | File lưu có thể chưa hoàn chỉnh | Status Logger, lỗi compression, tên archive |
| Agent thu log chậm | File bị dọn trước khi ingest xong | Retention so với backlog |
| JVM crash giữa các bước | Trạng thái archive chưa hoàn tất | Startup recovery, đối chiếu file |
| Queue async đầy hoặc chưa drain | Mất/trễ log dù policy đúng | Queue/drop metrics, shutdown |
| Clock/timezone bất nhất | Archive đổi theo chu kỳ khác dự kiến | Timezone, DST, policy, server time |

**Đừng gọi `LOG.error` để báo lỗi của chính appender hỏng mà không hiểu đường đi của Status Logger.** Khi hệ thống logging đã lỗi, việc dùng cùng appender để ghi một lỗi mới có thể không đến đích, thậm chí gây vòng lỗi. Cần có kênh giám sát/diagnostics bên ngoài như metrics, stdout/stderr được quản lý hoặc kiểm tra file/disk.

Trong Log4j2, `ignoreExceptions` quyết định ứng dụng có nhận một số exception từ appender hay không. Đặt `false` có thể khiến lỗi logging ảnh hưởng caller, nhưng **không biến logging thành cơ chế lưu trữ chắc chắn**. Khi dùng failover appender, điều kiện lan lỗi cần được cấu hình tương thích.

## 17. Kiểm thử đồng bộ rotation thế nào?

Một bài test đáng tin không chỉ kiểm tra file được đổi tên. Hãy kiểm tra **tính toàn vẹn dữ liệu trong phạm vi kỳ vọng**.

### Kiểm thử một JVM với nhiều thread

1. Tạo một thư mục thử nghiệm riêng, không dùng log production.
2. Có một writer/rolling appender chung, policy rollover rất nhỏ để kích hoạt nhiều lần.
3. Chạy nhiều thread, mỗi bản ghi mang một ID **duy nhất**: `threadId-sequence`.
4. Chờ mọi task hoàn thành và logging queue được drain nếu có.
5. Đọc **tất cả archive còn lại và file hiện hành**. Nếu retention đã xóa file, phải điều chỉnh chính sách test để vẫn giữ được toàn bộ sự kiện.
6. Đếm tổng số ID, số unique, số ID thiếu và số ID trùng.
7. Kiểm tra không có dòng bị cắt/xen và file vẫn parse được.
8. Tăng cường test nhiều lần với scheduler khác nhau để bắt race khó tái hiện.

Ví dụ phần 5 dùng `records=12`, `unique=12` và `verified=true`. Vì thứ tự interleaving không xác định, **không kiểm thử một thứ tự cố định giữa thread A và thread B**.

### Kiểm thử nhiều tiến trình

Nếu hệ thống bắt buộc nhiều JVM dùng chung file, chạy **hai tiến trình riêng** cùng lúc. Kiểm tra file lock, rename, kích thước file và archive count sau từng vòng. Không thay test này bằng test hai thread: chúng kiểm tra **phạm vi khóa khác nhau**.

### Kiểm thử va chạm với công cụ ngoài

Trong môi trường riêng, tạo log liên tục đồng thời chạy `logrotate` theo lịch nhanh. Kiểm tra bản ghi mất ở khoảng copy–truncate, file descriptor sau rename và dữ liệu có đi đúng file hay không. Không thực hiện test phá hoại trên tệp log production.

### Kiểm thử crash/khởi động lại

Dừng cưỡng bức tiến trình ở các thời điểm khác nhau gần rollover; khởi động lại và quan sát:

- Cấu hình có đọc được state/archive không?
- Có xóa nhầm archive cũ không?
- Có tiếp tục ghi mà tạo tên file trùng không?
- Những bản ghi chưa flush mất bao nhiêu?
- Collector có đọc trùng hoặc bỏ qua file sau rename không?

Một test thành công trong một JVM không đủ để chứng minh an toàn khi crash, distributed filesystem hay collector downtime.

## 18. Lỗi phổ biến cần tránh

**1. Tự rotate bằng `if (size > limit) move(...)` ở từng thread.** Đây là check-then-act race. Dùng shared manager hoặc critical section có phạm vi đúng.

**2. Cho rằng `volatile` thay được lock.** Visibility không tạo atomicity cho kiểm tra + rename + ghi.

**3. Dùng `synchronized` rồi suy ra nhiều JVM được bảo vệ.** Monitor chỉ nằm trong JVM và trên object cụ thể.

**4. Hai appender có cùng file nhưng khác policy/config.** Có thể xung đột manager, filePattern, retention; dùng cấu hình duy nhất và kiểm tra khả năng chia sẻ manager.

**5. Hai pod cùng ghi một active file trên shared volume.** Nên ưu tiên file/stream riêng cho từng instance hoặc pipeline thu tập trung.

**6. Dùng Log4j2 `RollingRandomAccessFile` như thể nó cho phép nhiều tiến trình mở chung không rủi ro.** Đặc tính truy cập/atomic append của nó khác RollingFile, cần đọc tài liệu triển khai.

**7. Đồng thời dùng framework rolling và logrotate trên cùng file.** Hai bên có thể tranh rename và archive. Chọn một chủ sở hữu rotation.

**8. Coi `copytruncate` không mất log.** Manual logrotate nêu rõ có cửa sổ có thể mất dữ liệu giữa copy và truncate.

**9. Coi file lock là giao thức distributed rotation.** Lock file không tự xử lý kiểm tra ngưỡng, archive index, rename và cleanup qua nhiều process.

**10. Đặt filePattern thiếu `%i` khi time+size có nhiều rollover cùng chu kỳ.** Tên archive có thể va chạm.

**11. Bật nén với Logback prudent mode mà không đọc giới hạn.** Prudent mode với TimeBasedRollingPolicy không hỗ trợ compression và có ràng buộc với trường file.

**12. Dùng retention ngắn hơn độ trễ collector.** Archive có thể bị dọn khi agent chưa ingest xong.

**13. Coi `max=7` của Log4j2 bằng `maxHistory=7` của Logback.** Khác backend và phạm vi ý nghĩa; kiểm tra chính sách thật.

**14. Quên queue async khi dừng hệ thống.** Những sự kiện chưa được drain có thể mất mặc dù rotation logic chính xác.

**15. Dựa vào timestamp archive làm thời điểm chính xác của mọi sự kiện.** Clock, timezone, async và mốc rollover có thể lệch.

**16. Kết luận “không mất log” chỉ vì test 12 dòng PASS.** Test demo chỉ chứng minh phạm vi hai thread, một tiến trình, hoạt động I/O bình thường.

## 19. Câu hỏi tự kiểm tra

1. **Đồng bộ rotation là gì?** Phối hợp kiểm tra policy, rename/archive, chuyển file đang ghi và ghi LogEvent để tránh race và trạng thái mâu thuẫn.
2. **Vì sao `volatile boolean rotating` chưa đủ?** Các thao tác kiểm tra–rotate–append vẫn không thành một critical section nguyên tử.
3. **`synchronized` giữa hai thread có bảo vệ một JVM khác không?** Không. Monitor riêng theo đối tượng/JVM.
4. **Vì sao nên có shared appender/manager?** Để thống nhất trạng thái tệp, policy và việc điều phối rollover trong phạm vi nó quản lý.
5. **Hai thread ghi 6 dòng mỗi thread, rotate mỗi 4 dòng, có bao nhiêu lần rollover trong ví dụ?** Hai lần; 12 dòng chia thành 3 lô 4 dòng.
6. **Vì sao chương trình kiểm `Set` ID thay vì so khớp thứ tự dòng?** Vì thứ tự xen kẽ giữa thread không xác định, còn tập ID mong đợi thì cố định.
7. **Log4j2 có `RollingFileManager` chung giữa các JVM độc lập không?** Không tự động; đó là cơ chế trong runtime có thể chia sẻ manager, không phải distributed lock.
8. **Vì sao nhiều manager ghi chung file khiến size rollover có thể sai?** Mỗi manager có thể theo dõi byte của riêng nó và không biết chính xác phần do manager khác ghi.
9. **Cần `%i` khi nào?** Khi có thể rotate nhiều lần trong cùng chu kỳ thời gian, như khi phối hợp time+size policy.
10. **`logrotate copytruncate` có mất dữ liệu không?** Có thể, do khoảng trống giữa copy và truncate được manual nêu.
11. **Rename tệp trên POSIX có tự đổi file descriptor appender đang mở sang đường dẫn mới không?** Không; descriptor tiếp tục trỏ đối tượng file trước rename.
12. **Logback prudent mode có cho phép nén archive không?** Không trong tổ hợp TimeBasedRollingPolicy prudent được tài liệu mô tả.
13. **ATOMIC_MOVE có làm cả chuỗi xóa/move/mở file thành transaction không?** Không. Nó chỉ là yêu cầu atomic cho một move khi được hỗ trợ.
14. **Dùng AsyncAppender có bảo đảm crash không mất sự kiện chưa flush không?** Không. Queue trong memory có thể mất.
15. **Nếu log shipper đọc archive chậm, điều gì cần kiểm tra?** Retention/cleanup, theo dõi rename, buffer và khả năng ingest còn kịp trước khi file bị xóa.
16. **Trong hệ thống nhiều container, cách tránh shared rotation đơn giản thường là gì?** Mỗi instance ghi stream/file riêng và thu tập trung qua agent.
17. **Ghi đủ số dòng khi không có lỗi I/O có bảo đảm không mất log trong mọi tình huống không?** Không. Cần thêm test crash, multi-process, collector và durability nếu có cam kết cao hơn.
18. **Có nên cùng dùng Log4j2 RollingFileAppender và logrotate trên một active file không?** Thường không; hãy xác định một bên chịu trách nhiệm rotation.

## 20. Nguồn tham khảo

- Apache Log4j 2, Rolling file appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Apache Log4j 2, File appenders và giới hạn reopen bên ngoài: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Logback, RollingFileAppender / prudent mode: https://logback.qos.ch/manual/appenders-rolling.html
- Linux manual `logrotate(8)`, `copytruncate`: https://man7.org/linux/man-pages/man8/logrotate.8.html
- Java 17, `FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Java 17, `Files.move`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

**Ghi nhớ:** đồng bộ rotation là bài toán **phối hợp nhiều bước có trạng thái**, không đơn giản là gọi `rename` dưới một khóa bất kỳ. Trong một JVM, dùng chung appender/manager hoặc critical section phù hợp. Giữa nhiều JVM hay công cụ ngoài, không coi `synchronized`, `FileLock` hay `ATOMIC_MOVE` đơn lẻ là lời giải toàn bộ. Ưu tiên mỗi instance có tệp/stream riêng, để logging framework quản lý rotation và collector thu tập trung; kiểm thử tính toàn vẹn, lỗi, crash và retention theo phạm vi bảo đảm được yêu cầu.
