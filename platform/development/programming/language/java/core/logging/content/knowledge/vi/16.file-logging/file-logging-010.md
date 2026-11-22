# Xử lý file đầy — File logging an toàn trong Java

## 1. File đầy trong logging là tình huống gì?

**File logging** là cách ứng dụng ghi các sự kiện log vào tệp thông qua **Handler/Appender**. Một tình huống quan trọng khi vận hành là **không thể tiếp tục ghi log vì không còn tài nguyên lưu trữ**, thường được gọi ngắn gọn là “file đầy”.

Nói chính xác hơn, cần phân biệt:

- **Tệp đạt giới hạn cấu hình:** ví dụ một rolling appender cho phép tối đa 10 MB mỗi tệp trước khi chuyển sang tệp tiếp theo. Đây là **điều kiện rotation**, chưa chắc ổ đĩa đã hết chỗ.
- **Filesystem hết dung lượng:** hệ điều hành có thể báo lỗi I/O như **ENOSPC** (*No space left on device*) khi ghi. Có thể file log hiện tại vẫn nhỏ nhưng phân vùng chứa nó đã đầy.
- **Hết inode hoặc quota:** filesystem không còn inode cho tệp mới, người dùng/container vượt quota hoặc hệ thống không đủ tài nguyên metadata; hành vi và thông báo lỗi phụ thuộc filesystem và hệ điều hành.
- **Hệ thống file chỉ đọc hoặc quyền ghi không phù hợp:** log không ghi được, nhưng nguyên nhân không phải hết dung lượng; ví dụ read-only filesystem, permission denied.
- **Giới hạn lưu trữ container/node:** một Pod hoặc container có thể chạm giới hạn ephemeral storage hay bị evict trước khi bạn thấy hết dung lượng toàn bộ ổ đĩa host.
- **Collector hoặc đích remote đầy:** có thể tác động đường truyền log/queue nhưng khác việc FileAppender ghi tệp cục bộ báo hết chỗ.

**Bài học tập trung vào việc ứng dụng Java xử lý đúng khi tệp log không thể ghi tiếp**, bao gồm phát hiện, giới hạn dung lượng, lựa chọn fallback, cảnh báo và cách bảo toàn hành vi nghiệp vụ.

Ví dụ một sự cố minh họa:

~~~text
ERROR component=file-logging event=log.write.failed reason=ENOSPC
WARN  component=observability event=log.sink.degraded action=fallback_stderr
~~~

Đây là **dòng minh họa**, không phải output mặc định của JUL hoặc Logback. Khi đích ghi file hỏng, chính sự kiện cảnh báo đó cũng có thể **không được ghi vào file**, nên cần đường phát tín hiệu độc lập.

## 2. Vì sao file log đầy có thể ảnh hưởng ứng dụng?

Một hệ thống ghi log liên tục có thể tăng dung lượng do:

1. **Không có rotation:** một file application.log tăng vô hạn.
2. **Rotation nhưng không retention:** file cũ được đổi tên mãi mà không xóa theo chính sách.
3. **DEBUG/TRACE bị bật diện rộng:** lượng event tăng đột biến.
4. **Stack trace và payload quá lớn:** một sự cố lặp lại tạo hàng nghìn bản ghi nhiều dòng.
5. **Retry không giới hạn:** cùng một lỗi ghi log hoặc lỗi mạng được ghi liên tục.
6. **Nhiều replica cùng ghi vào cùng phân vùng:** tổng dung lượng tăng nhanh hơn dự tính.
7. **Dữ liệu khác dùng chung filesystem:** database, file upload hoặc temp file chiếm không gian, dù app log nhỏ.
8. **Log đã bị xóa tên nhưng vẫn có tiến trình giữ file mở:** dung lượng thật chưa chắc được giải phóng.
9. **Giới hạn quota/inode:** phép ghi có thể hỏng dù thống kê dung lượng còn trống.
10. **Nén/xoay log thất bại:** có thể tạm cần thêm dung lượng cho file mới, bản nén và metadata.

Hậu quả có thể gồm:

- Mất log mới hoặc chỉ có log bị cắt một phần.
- Logger/Appender liên tục báo lỗi nội bộ, làm nhiễu stderr và monitoring.
- Thread ứng dụng chịu thêm thời gian do I/O chậm, retry hoặc lock.
- Các thành phần khác dùng chung volume cũng thất bại: ghi tệp tạm, cache, upload, đôi khi cả dữ liệu ứng dụng.
- Container bị restart hoặc Pod bị evict do giới hạn storage.
- Điều tra sự cố khó hơn vì **log quan trọng nhất lại biến mất lúc hệ thống bị áp lực**.

**Không được mặc định rằng một lỗi ghi log sẽ làm lỗi nghiệp vụ tự động được ném ra.** Nhiều logging backend cố ý xử lý lỗi I/O bên trong để tránh phá luồng ứng dụng; một số wrapper/hệ thống có chính sách khác. Phải biết hợp đồng của thư viện đang dùng.

## 3. Mục tiêu khi ứng phó file logging đầy

Có ba mục tiêu cần cân bằng:

| Mục tiêu | Ý nghĩa |
| --- | --- |
| **Quan sát được lỗi** | Có tín hiệu rằng logging đã suy giảm, ngay cả khi file không còn ghi được |
| **Ứng dụng hành xử đúng** | Không làm mất dữ liệu hoặc báo thành công sai chỉ vì logger hỏng |
| **Khôi phục có kiểm soát** | Giảm tốc độ ghi, dọn dung lượng đúng chính sách, điều chỉnh cấu hình và xác minh log chạy lại |

Hai tình huống có chính sách rất khác nhau:

**Log chẩn đoán thông thường:** lỗi ghi một dòng INFO có thể được xử lý theo **best effort**, giảm cấp/fallback sang console, phát metric/cảnh báo và giữ nghiệp vụ tiếp tục nếu an toàn.

**Log kiểm toán hoặc sự kiện phải lưu bền vững theo hợp đồng:** không được im lặng bỏ qua mất log nếu việc ghi là điều kiện bắt buộc để hoàn tất giao dịch. Cần cơ chế bền vững phù hợp như transactional outbox, event store hoặc kho audit đã được thiết kế; nếu không lưu được thì **từ chối hoặc dừng thao tác theo chính sách**. Một FileAppender thuần túy thường **không đủ** để tạo bảo đảm kiểm toán chặt chẽ.

Đừng dùng cùng một phương án “catch rồi bỏ qua” cho cả hai loại sự kiện.

## 4. Cơ chế khi ứng dụng Java ghi file

### 4.1. Với JUL

Một đường đi thường gặp:

~~~text
java.util.logging.Logger
            |
            v
       LogRecord
            |
            v
        FileHandler
       (level/filter)
            |
            v
         Formatter
            |
            v
       File system
~~~

**java.util.logging.FileHandler** là handler ghi log của JDK, hỗ trợ pattern tên tệp, giới hạn kích thước và số lượng tệp luân phiên. Khi việc ghi của handler gặp vấn đề, JUL có **ErrorManager** để báo lỗi nội bộ.

Điểm quan trọng: **không mặc định lệnh LOGGER.info(...) ném IOException ra cho code gọi nó**. Handler thường bắt và báo lỗi I/O theo cơ chế error reporting riêng. Việc phát log không tương đương một giao dịch ghi file mà ứng dụng có thể kiểm tra boolean thành công một cách trực tiếp.

### 4.2. Với SLF4J + Logback

~~~text
org.slf4j.Logger
        |
        v
Logback Classic Logger
        |
        v
RollingFileAppender / FileAppender
        |
        v
Encoder / OutputStream
        |
        v
File system
~~~

Logback có hệ thống **status** nội bộ để báo các sự cố của Appender và khởi tạo cấu hình. Một lời gọi logger.error(...) vẫn có thể không ném exception I/O lên code nghiệp vụ. Cần giám sát appender/status phù hợp với phiên bản Logback và hạ tầng triển khai.

**Logback ConsoleAppender** có thể ghi ra stdout/stderr độc lập với FileAppender. Nhưng gắn hai appender cùng root thường có nghĩa **cả hai cùng nhận các log bình thường**, không phải cơ chế tự động “chỉ chuyển sang console khi file đầy”. Nếu muốn failover theo điều kiện, cần thiết kế/kiểm thử rõ chứ không suy từ hai appender.

### 4.3. Appender lỗi không đồng nghĩa file hệ thống bị đầy

Ngoài dung lượng, có thể gặp:

- Permission denied do user hoặc mount permissions.
- No such file or directory vì thư mục log không tồn tại.
- File descriptor limit hoặc quá nhiều file đang mở.
- Read-only filesystem.
- Lock conflict hoặc trùng file pattern giữa nhiều tiến trình.
- Lỗi ổ đĩa hoặc thiết bị lưu trữ.
- Quota/inode exhaustion.

Chẩn đoán phải dựa trên **bằng chứng lỗi I/O và filesystem**, không tự quy mọi thất bại của FileHandler thành ENOSPC.

## 5. Rotation khác xử lý hết dung lượng thế nào?

**Log rotation** là cách chuyển từ một tệp log đang ghi sang tệp khác theo điều kiện, ví dụ kích thước hoặc thời gian. **Retention** quyết định giữ bản cũ bao lâu và tối đa bao nhiêu; **disk-capacity management** xử lý ngân sách lưu trữ tổng thể.

Ví dụ:

~~~text
app.log            (tệp đang ghi)
app.2026-11-09.0.log.gz
app.2026-11-09.1.log.gz
app.2026-11-08.0.log.gz
...
~~~

Nếu chỉ có rotation mà không dọn file cũ, lượng dung lượng vẫn tăng. Nếu chỉ giữ số file nhưng một file có thể quá lớn, toàn hệ thống vẫn có thể đầy. Cần kết hợp:

- Ngưỡng **maxFileSize** cho từng segment.
- **maxHistory** hoặc quy tắc tuổi file.
- **totalSizeCap** hoặc ngân sách archive tương ứng.
- Chính sách xóa/nén rõ ràng, kiểm tra quyền truy cập.
- Giám sát dung lượng filesystem/quota/inode và tốc độ tăng.
- Tránh nhiều ứng dụng đổ log vào cùng volume mà không chia ngân sách.

Ngay cả khi đã bật mọi cấu hình này, **không có lời bảo đảm tuyệt đối rằng filesystem sẽ không đầy**. File đang active, file tạm trong lúc nén, nguồn dữ liệu khác và thời điểm tác vụ cleanup đều ảnh hưởng.

## 6. Ví dụ cấu hình Logback RollingFileAppender có giới hạn

Đây là **một logback.xml minh họa cho Java dùng Logback Classic**, có file rotation theo thời gian và kích thước:

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Cách đọc và những hạn chế thiết yếu:

1. **RollingFileAppender** viết tệp active **logs/app.log** và sử dụng rolling policy cho archive.
2. **fileNamePattern** dùng ngày và chỉ số **%i** để đặt tên các segment đã xoay; **.gz** biểu diễn archive nén.
3. **maxFileSize=10MB** giới hạn kích thước mỗi segment trước khi rollover theo policy; không có nghĩa toàn bộ phân vùng chỉ cần 10 MB.
4. **maxHistory=7** trong chính sách daily thường giữ tối đa một số chu kỳ thời gian lịch sử, không phải đúng bảy file; một ngày có thể có nhiều segment.
5. **totalSizeCap=100MB** giới hạn tổng kích thước archive theo cách cleanup của policy; **không phải hard quota tức thời cho filesystem**, không bao gồm mọi file khác trên ổ đĩa.
6. **cleanHistoryOnStart=true** giúp cleanup theo chính sách khi khởi động; nó không thay thế việc bảo đảm luôn còn đủ dung lượng để ứng dụng chạy.
7. **logs và logs/archive** cần đường dẫn/permissions thích hợp; không giả định volume luôn writable ở mọi container.
8. **ConsoleAppender** được gắn song song: thông thường **mọi log đủ ngưỡng** đi cả file lẫn stderr. Nó tạo một kênh quan sát khác khi file lỗi, nhưng **không phải failover tự động chỉ bật lúc file đầy**.
9. Pattern thời gian minh họa có offset; nếu yêu cầu UTC tuyệt đối, cần cấu hình timezone ở formatter theo khả năng của phiên bản backend và kiểm chứng output.
10. Tham số, cách xử lý archive và khả năng nén cần được xác minh trên phiên bản Logback đang sử dụng.

Một hệ thống có nhiều replica có thể tạo nhiều volume/tệp, nên **100 MB trên một instance không phải ngân sách tổng cho toàn cluster**.

### Tại sao vẫn phải cảnh báo disk?

Khi filesystem cạn dung lượng, appender có thể không tạo được file mới hoặc không ghi được bản mới **trước khi cleanup hoàn tất**. Tình trạng đầy có thể phát sinh từ upload, cache hoặc file khác không thuộc danh sách archive; totalSizeCap không kiểm soát chúng.

Một số cấu hình rolling khác (time-based, fixed-window, external logrotate) có ngữ nghĩa khác nhau. Không kết hợp một cách mù quáng hai cơ chế rotation cùng kiểm soát một file active: có thể mất bản ghi hoặc tạo file/chỉ số sai.

## 7. Với JUL FileHandler: limit và count

JUL tích hợp trong JDK có khả năng rotation cơ bản. Ví dụ tệp logging.properties:

~~~properties
handlers = java.util.logging.FileHandler, java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.FileHandler.pattern = logs/jul-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.encoding = UTF-8
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Ở đây:

- **limit=1048576** là giới hạn kích thước tệp theo byte (xấp xỉ 1 MiB).
- **count=3** là số file trong nhóm luân phiên.
- **%g** là chỉ số thế hệ file.
- **append=true** yêu cầu nối thêm dữ liệu khi thích hợp, không biến FileHandler thành kho lưu trữ vô hạn.
- **ConsoleHandler của JUL mặc định ghi stderr**, khác với Logback ConsoleAppender thường mặc định stdout.
- Tên file thực tế có thể có hậu tố khác để tránh xung đột giữa các handler/tiến trình.
- Cần tạo thư mục **logs** và bảo đảm quyền ghi trước khi chạy, nếu filesystem không tự cung cấp các thư mục đó.

Cấu hình có cả hai handler **không đảm bảo file luôn ghi được hoặc tự chứng minh console sẽ giữ mọi bản ghi**, nhưng nó tạo một tuyến xuất khác và hỗ trợ chẩn đoán. Không dùng JUL FileHandler trong lúc mong đọc cấu hình logback.xml; hai backend khác nhau.

### FileHandler có thông báo IOException cho code nghiệp vụ không?

Thông thường API logging **không trả kết quả ghi thành công cho mỗi LOGGER.info(...)**. JUL có **ErrorManager** để nhận thông báo từ Handler. Vì vậy, nếu **bắt buộc phải biết bản ghi đã được lưu bền vững** trước khi giao dịch thành công, không nên dùng FileHandler thuần như cơ chế giao dịch.

Một lớp writer chuyên dụng có thể trả kết quả hoặc ném IOException, nhưng đó là **hợp đồng I/O của lớp writer**, khác với lời gọi Logger của framework.

## 8. Ví dụ Java 17 chạy được: mô phỏng hết dung lượng an toàn

Không cần và **không nên cố tình đổ dữ liệu đến khi đầy ổ đĩa thật** để kiểm thử bài học. Ta có thể **tiêm lỗi IOException** vào một output sink, như cách mock một filesystem hết chỗ.

Ví dụ dưới đây là **mô phỏng cơ chế ghi file**, không phải tái triển khai JUL FileHandler hay Logback FileAppender. Nó cho thấy cách một component có quyền kiểm soát I/O có thể:

1. Ghi bản ghi đầu tiên thành công.
2. Nhận IOException từ một sink giả lập có giới hạn byte.
3. Phát **một cảnh báo** ra stderr, không cố dùng lại sink hỏng vô hạn.
4. Chuyển các bản ghi chẩn đoán tiếp theo sang stderr theo chính sách best effort.
5. Cho người vận hành biết **không có bảo đảm mọi log đã được lưu**, và dữ liệu audit cần cơ chế riêng.

Tạo tệp **FileFullLoggingDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class FileFullLoggingDemo {
    public static void main(String[] args) {
        QuotaOutputStream simulatedFile =
                new QuotaOutputStream(40);
        SafeFileSink sink = new SafeFileSink(simulatedFile);

        sink.log("INFO event=app.started");
        sink.log("WARN event=task.retry");
        sink.log("ERROR event=task.failed");

        System.out.println("SIMULATED_FILE:");
        System.out.print(simulatedFile.snapshot());
    }

    // Mô phỏng đích ghi file chỉ được chứa tối đa 40 byte.
    private static final class QuotaOutputStream extends OutputStream {
        private final ByteArrayOutputStream stored =
                new ByteArrayOutputStream();
        private final int capacity;

        QuotaOutputStream(int capacity) {
            this.capacity = capacity;
        }

        @Override
        public void write(int value) throws IOException {
            if (stored.size() >= capacity) {
                throw new IOException("SIMULATED_ENOSPC");
            }
            stored.write(value);
        }

        @Override
        public void write(byte[] source, int offset, int length)
                throws IOException {
            Objects.checkFromIndexSize(offset, length, source.length);

            // Mô phỏng nguyên bản ghi hoặc không ghi gì,
            // giúp output demo luôn xác định.
            if (length > capacity - stored.size()) {
                throw new IOException("SIMULATED_ENOSPC");
            }
            stored.write(source, offset, length);
        }

        String snapshot() {
            return stored.toString(StandardCharsets.UTF_8);
        }
    }

    private static final class SafeFileSink {
        private final OutputStream destination;
        private boolean degraded;

        SafeFileSink(OutputStream destination) {
            this.destination = destination;
        }

        void log(String message) {
            if (degraded) {
                System.err.println("FALLBACK | " + message);
                return;
            }

            byte[] record = (message + "\n")
                    .getBytes(StandardCharsets.UTF_8);

            try {
                destination.write(record);
                destination.flush();
            } catch (IOException failure) {
                degraded = true;
                System.err.println(
                        "ALERT | file-log-unavailable reason="
                        + failure.getMessage());
                System.err.println("FALLBACK | " + message);
            }
        }
    }
}
~~~

Chạy với **JDK 17 trở lên**, không cần Maven hoặc thư viện ngoài:

~~~bash
javac -encoding UTF-8 FileFullLoggingDemo.java
java FileFullLoggingDemo
~~~

**Stdout chính xác của chương trình Java:**

~~~text
SIMULATED_FILE:
INFO event=app.started
~~~

**Stderr chính xác của chương trình Java:**

~~~text
ALERT | file-log-unavailable reason=SIMULATED_ENOSPC
FALLBACK | WARN event=task.retry
FALLBACK | ERROR event=task.failed
~~~

Nếu terminal gộp stdout/stderr, các dòng có thể **xen kẽ theo cách khác** do hai stream độc lập. Vì vậy, phần trên mô tả **hai luồng riêng**, không cam kết thứ tự dòng khi terminal/IDE gộp chúng.

### Phân tích từng bước

- **QuotaOutputStream(40)** giữ tối đa 40 byte trong bộ nhớ; không ghi ra filesystem thật và **không có nguy cơ làm đầy ổ đĩa**.
- Bản ghi đầu tiên **INFO event=app.started** và newline vừa trong quota nên được lưu trong vùng nhớ mô phỏng file.
- Bản ghi thứ hai cần thêm byte vượt mức 40, nên sink giả lập ném **IOException("SIMULATED_ENOSPC")**.
- **SafeFileSink** chuyển trạng thái sang **degraded** sau lỗi đầu tiên, thông báo một lần và chuyển bản ghi thứ hai sang stderr.
- Bản ghi thứ ba không thử viết lại sink đã hỏng, mà đi thẳng stderr. Nhờ vậy không tạo vòng retry không giới hạn khi filesystem vẫn đầy.
- Cuối cùng chương trình in phần đã “lưu vào file giả lập” ra stdout để dễ quan sát.
- **ByteArrayOutputStream** và các message mẫu chỉ dùng ASCII, nên độ dài byte và output tái lập chính xác trên Java 17.

### Giới hạn cần hiểu để không áp dụng sai

1. **Đây là sink minh họa do ta kiểm soát trực tiếp IOException**. Trong Logback hoặc JUL, FileAppender/FileHandler có thể bắt và xử lý lỗi I/O nội bộ, không ném cho code gọi Logger.
2. **Ghi file thực tế không nhất thiết atomic theo dòng**. Một lần ghi có thể đã ghi một phần rồi mới lỗi; demo cố ý ghi toàn bộ hoặc không ghi để output xác định.
3. **degraded là trạng thái một chiều trong demo**. Ứng dụng thực cần quy trình phục hồi có kiểm soát, health/status và cảnh báo, không tự bỏ qua file mãi mãi sau lỗi thoáng qua.
4. **System.err cũng có thể không khả dụng** hoặc không được collector thu. Console fallback là một phương án best effort, không phải cam kết độ bền.
5. **Không dùng ví dụ làm kho audit**. Nếu hợp đồng yêu cầu lưu sự kiện bền vững, phải dùng cơ chế giao dịch chuyên dụng hoặc từ chối thao tác khi không thể đảm bảo.
6. **Ví dụ chỉ một thread**. Trong server đa luồng, việc chuyển trạng thái degraded, đóng/mở lại sink và quản lý thứ tự cần thread-safety rõ ràng.
7. **Dòng thông báo lỗi chỉ phát một lần** nhằm tránh log storm trong demo; production cần tăng metric, phát alert và có cơ chế phản hồi sự cố ngay cả khi không in lặp.

### Có nên dùng fallback stderr cho mọi loại log?

Không. Đối với **log chẩn đoán**, stderr/stdout là lựa chọn tự nhiên nếu hạ tầng thu stream. Đối với **sự kiện kiểm toán bắt buộc**, việc ghi stderr không đủ bảo đảm quyền kiểm soát, thứ tự và lưu trữ. Cần xác định rõ **chính sách sai hỏng** của từng loại thông tin trước khi áp dụng fallback.

## 9. Kiểm tra lỗi trong Linux trước khi dọn dung lượng

Khi có dấu hiệu disk full, hãy xác định **đúng filesystem và nguyên nhân**. Trên Linux, các lệnh chẩn đoán thông dụng:

~~~bash
# Dung lượng filesystem chứa thư mục log
df -h /var/log/myapp

# Kiểm tra inode của filesystem
df -i /var/log/myapp

# Ước lượng dung lượng thư mục log
du -sh /var/log/myapp

# Xem file lớn trong đúng thư mục, tránh quét toàn hệ thống vô cớ
du -ah /var/log/myapp | sort -h | tail -n 20

# Với quyền phù hợp, kiểm tra file đã unlink nhưng còn mở
sudo lsof +L1
~~~

**Đây là các lệnh chẩn đoán**, không phải lệnh cần chạy trong mọi môi trường. Thư mục phải tồn tại; quyền truy cập, tiện ích được cài và hệ điều hành có thể làm kết quả khác nhau.

### Đọc kết quả đúng

- **df -h** nói về **filesystem**, không phải kích thước của một file log riêng.
- **df -i** kiểm tra số inode, đặc biệt hữu ích khi có rất nhiều file nhỏ.
- **du** tính dung lượng theo các file mà công cụ thấy trong đường dẫn được quét; nó **có thể không bằng df** vì file đã unlink nhưng vẫn mở, filesystem metadata và các lý do khác.
- **lsof +L1** hữu ích để nhận diện file không còn tên nhưng tiến trình vẫn giữ mở; không phải mọi container đều có lsof hoặc đủ quyền xem toàn bộ tiến trình.
- **Quota** có thể chặn ghi dù df cho thấy còn không gian; cần công cụ quota/cgroup/volume phù hợp môi trường.
- **Permission denied** hoặc **read-only filesystem** phải được xử lý khác với ENOSPC; dọn dung lượng không sửa được quyền sai.

Khi môi trường là container, cần xác định **đường dẫn log nằm ở writable layer, volume gắn ngoài hay filesystem của node** trước khi xem df/du. Một thống kê từ bên trong container không luôn phản ánh mọi giới hạn lưu trữ do orchestrator đặt.

### Những thao tác dọn file cần tránh

**Không dùng rm -rf bừa bãi** đối với thư mục log production. Không xóa file audit có yêu cầu lưu trữ, log còn phục vụ điều tra hoặc dữ liệu nghiệp vụ chỉ để giải phóng vài GB.

**Không tự ý xóa một file log đang mở rồi nghĩ dung lượng sẽ giải phóng ngay**: trên hệ Unix, tiến trình có thể tiếp tục giữ file descriptor và các block chưa được giải phóng cho đến khi file thực sự được đóng. Cũng không nên cắt/truncate file đang ghi khi chưa hiểu policy, vì có thể mất dữ liệu, tạo khoảng trống bất thường hoặc phá kỳ vọng của appender.

Ưu tiên **quy trình rotate/retention đã được phê duyệt**, dọn archive đủ tuổi theo chính sách, và nếu cần đóng/mở lại handler thì làm qua lifecycle ứng dụng hoặc thao tác vận hành có kiểm soát.

## 10. Khắc phục khi filesystem thật sự hết chỗ

Một quy trình vận hành có thứ tự:

### Bước 1 — Xác nhận nguồn lỗi

Kiểm tra thông báo I/O, filesystem path, dung lượng, inode, quota và quyền. Phân biệt ENOSPC với read-only, permission, file lock hoặc storage backend lỗi.

### Bước 2 — Đánh giá tác động

Xác định dịch vụ có đang:

- Chỉ mất log chẩn đoán.
- Bị chậm vì appender I/O.
- Mất khả năng ghi dữ liệu ứng dụng cùng filesystem.
- Bị restart/evict bởi container runtime.
- Vi phạm yêu cầu kiểm toán hoặc điều kiện để tiếp tục giao dịch.

Nếu dữ liệu nghiệp vụ hoặc audit không thể bảo toàn, **không tiếp tục báo thành công sai**. Cô lập hoặc dừng công việc theo chính sách.

### Bước 3 — Bảo đảm kênh quan sát thay thế

Nếu an toàn và được triển khai, ưu tiên console appender hoặc metric/health signal không phụ thuộc đường dẫn file đang lỗi. Tránh gọi chính FileAppender hỏng để báo rằng FileAppender đã hỏng.

Không tạo vòng lỗi kiểu “ghi file thất bại → logger ghi lỗi này vào cùng file → thất bại → lặp vô hạn”. Dùng kênh báo lỗi nội bộ/status và giới hạn tần suất cảnh báo phù hợp.

### Bước 4 — Giảm áp lực ghi

Điều chỉnh mức DEBUG/TRACE, giới hạn sự kiện lặp, giảm payload và stack trace dư thừa, áp dụng sampling hợp lý. Đây là cách **giảm tốc độ tăng**, không tự giải quyết phần dung lượng đã đầy.

Đừng tắt toàn bộ ERROR hay xóa bằng chứng quan trọng chỉ để dashboard trông yên tĩnh.

### Bước 5 — Giải phóng hoặc tăng tài nguyên đúng chính sách

Kiểm tra các archive đã vượt retention và thực hiện cleanup đã được phép. Điều chỉnh volume/quota hoặc chuyển log sang đích phù hợp nếu cần. Với log đang mở, cần hiểu cơ chế rotation/reopen của backend.

Tránh sửa trực tiếp file runtime quản lý, hay xóa file nghi là log khi chưa xác nhận ứng dụng nào sở hữu nó.

### Bước 6 — Phục hồi khả năng ghi

Sau khi có đủ dung lượng, một handler/appender đã rơi vào trạng thái lỗi **không mặc nhiên tự khôi phục hoàn toàn**. Tùy phiên bản/backend, có thể cần cấu hình lại, mở lại file qua cơ chế ứng dụng hoặc restart có kiểm soát.

Nếu filesystem thực sự sửa xong nhưng backend không nhận log trở lại, phải kiểm tra nội bộ FileHandler/Appender thay vì cho rằng đĩa còn trống là xong.

### Bước 7 — Xác nhận từ đầu đến cuối

Tạo một **sự kiện kiểm tra không nhạy cảm** có event code riêng, xác minh nó đến đúng file/console, đúng định dạng và collector truy vấn được. Đồng thời quan sát disk usage, inode, số lỗi ghi file, tốc độ tăng archive, độ trễ và alert health.

**Không xác nhận đã phục hồi chỉ vì df hiển thị nhiều dung lượng trống hơn.** Phải có bằng chứng rằng **đường ghi log thực sự đã hoạt động lại**.

## 11. Hết dung lượng trong Docker và Kubernetes

File logging bên trong container có một số khác biệt:

| Nơi ghi | Rủi ro thường gặp | Hướng tiếp cận |
| --- | --- | --- |
| Writable layer trong container | Dữ liệu mất khi container bị xóa; có thể chịu giới hạn ephemeral storage | Ưu tiên stdout/stderr khi hạ tầng có collector |
| Volume gắn ngoài | Quota/full/permissions riêng; nhiều replica có thể tranh chấp | Quản lý dung lượng, rotation và quyền theo volume |
| Log stdout/stderr | Runtime/daemon/node vẫn phải lưu hoặc chuyển stream | Cấu hình logging driver, rotation và log collector |
| File chỉ tồn tại trong image/runtime | docker logs/kubectl logs không tự thấy file này | Cần xuất console hoặc sidecar/agent đọc file |
| Audit store riêng | Yêu cầu độ bền và phân quyền cao hơn log thường | Dùng cơ chế lưu sự kiện có hợp đồng phù hợp |

**Chuyển sang console logging không làm bài toán dung lượng biến mất**. Docker daemon hoặc kubelet vẫn có thể cần lưu log trên node trước khi collector ship đi. Đặt rotation/retention ở đúng tầng, kiểm tra quota và giám sát cả node.

Một số lệnh vận hành minh họa:

~~~bash
# Docker: kiểm tra logging driver trên daemon
docker info --format '{{.LoggingDriver}}'

# Container cụ thể: driver và lựa chọn log của container
docker inspect --format '{{json .HostConfig.LogConfig}}' my-java-app

# Kubernetes: xem sự kiện/điều kiện Pod khi nghi storage eviction
kubectl describe pod my-java-app -n demo

# Kubernetes: xem log container nếu còn khả dụng
kubectl logs my-java-app -n demo -c app --tail=100
~~~

Các tên **my-java-app**, **demo**, **app** chỉ là ví dụ; cần thay bằng tài nguyên thật. Lệnh kubectl logs chỉ cung cấp log từ container/runtime còn khả dụng, **không phải kho lịch sử vô hạn**. Với Kubernetes, eviction do ephemeral storage và dung lượng node có các ngưỡng/chính sách riêng, không phải mọi Pod hỏng đều do filesystem đầy.

### Vì sao không nên lưu mọi log trực tiếp vào cùng một persistent volume?

Một PV chung cho nhiều replica có thể gặp tranh chấp tên file, quyền truy cập và giới hạn I/O. Nếu bắt buộc dùng file, nên thiết kế đường dẫn và ownership rõ ràng theo instance, rolling policy tương thích, thu thập tập trung và phương án khôi phục. Với nhiều môi trường Kubernetes, console + collector là lựa chọn đơn giản hơn cho log chẩn đoán.

## 12. Giám sát sớm thay vì chờ ghi thất bại

Một chiến lược tốt phát hiện **nguy cơ đầy trước khi ENOSPC xảy ra**.

Các tín hiệu nên xem xét:

- **Filesystem available bytes** và tỷ lệ sử dụng theo volume/path quan trọng.
- **Available inodes** nếu filesystem dựa trên inode.
- **Quota hoặc ephemeral storage usage** theo container, Pod, namespace hoặc volume.
- **Tốc độ tăng dung lượng log** để ước tính thời gian chạm giới hạn.
- **Số lỗi ghi vào file/appender** theo thời gian.
- **Tuổi file cuối cùng được ghi thành công**, nếu có cách đo đáng tin.
- **Tình trạng log collector**: backlog, dropped events, parse errors, delivery latency.
- **Tần suất level ERROR, stack trace**, vì log storm có thể là nguyên nhân khiến dung lượng tăng nhanh.
- **Thời gian dọn archive và số archive còn lại**, để phát hiện retention không chạy.

Một cách nghĩ về cảnh báo:

~~~text
Nguy cơ = ít dung lượng còn lại + tốc độ ghi cao
          + không có đường fallback/collector tin cậy
~~~

Không đặt một ngưỡng cảnh báo cố định cho mọi filesystem. Ví dụ 80% có thể quá sớm với một volume được quản lý tốt, nhưng quá muộn với volume nhỏ đang tăng vài GB/phút. Nên đánh giá theo **bytes còn lại, tốc độ tiêu thụ và thời gian phản ứng của đội vận hành**.

### Vì sao không dùng chính file log làm kênh alert duy nhất?

Nếu file đầy, dòng log “Disk full” có thể không được lưu. Cần kênh quan sát có **failure domain khác**: metric, health check, hệ thống điều phối hoặc alert của storage platform. Không giả định cứ có ERROR là người trực sẽ thấy, nếu chính pipeline ghi log đang lỗi.

## 13. Ứng dụng có nên dừng khi không ghi log được?

Không có một câu trả lời đúng cho tất cả loại log.

| Loại sự kiện | Chính sách thường hợp lý |
| --- | --- |
| DEBUG/TRACE | Best effort: có thể drop có kiểm soát, tăng metric nếu cần |
| INFO vận hành | Best effort, có cảnh báo khi sink suy giảm |
| WARN/ERROR chẩn đoán | Ưu tiên kênh dự phòng độc lập và giữ bằng chứng |
| Audit có yêu cầu bền vững | Không coi fallback console là tương đương; dùng kho riêng hoặc từ chối thao tác nếu cần |
| Trạng thái nghiệp vụ quan trọng | Đảm bảo bằng transaction/storage có hợp đồng, không chỉ bằng Logger |

Nếu nghiệp vụ vẫn có thể hoàn thành an toàn khi mất log chẩn đoán, việc dừng toàn hệ thống có thể gây sự cố lớn hơn. Ngược lại, nếu vận hành đòi hỏi ghi sự kiện bắt buộc trước khi trả thành công, **không được “fail open” một cách vô ý**.

Nên viết rõ trong tài liệu:

- Log loại nào là best effort?
- Khi log sink unavailable, thành phần có tiếp tục nhận request không?
- Bao nhiêu thời gian trước khi cảnh báo/escalate?
- Có fallback và cơ chế khôi phục nào?
- Ai phê duyệt việc bỏ qua hay dừng các thao tác audit?
- Kiểm thử đã mô phỏng chính xác failure domain chưa?

## 14. Xử lý lỗi mà không tạo vòng lặp hoặc che mất nguyên nhân

Khi file logging lỗi, một số cách xử lý tưởng hợp lý nhưng nguy hiểm:

**Sai — thử ghi thông báo lỗi qua cùng sink hỏng:**

~~~java
// Mã minh họa nguy hiểm: handleFailure lại dùng file logger lỗi.
try {
    writeLogFile(message);
} catch (java.io.IOException ex) {
    fileLogger.error("Write log failed", ex);
}
~~~

Đoạn trên là **mảnh minh họa**, không phải chương trình độc lập; các biến/hàm cần được định nghĩa ở lớp thực tế. Nếu fileLogger ghi vào chính file hỏng, thông báo có thể không đến đâu. Nếu lớp xử lý lỗi thực hiện retry vô hạn, có nguy cơ tạo log storm và mất CPU.

**Tốt hơn — báo trạng thái qua đường độc lập và rate limit:**

~~~text
FILE_SINK_FAILED
   |
   +--> đánh dấu degraded / tăng metric
   |
   +--> phát một thông báo trạng thái qua stderr hoặc kênh khác
   |
   +--> áp dụng chính sách fallback hoặc fail-stop đã xác định
   |
   +--> cảnh báo và phục hồi có kiểm soát
~~~

Một số backend có status reporting nội bộ khi appender lỗi; dùng API và phương pháp giám sát được backend hỗ trợ. **Không tự áp một lớp catch IOException quanh LOG.info và mong chắc chắn nhận được lỗi I/O của FileAppender.**

### Retry khi file còn đầy

Không retry ghi đồng bộ vô hạn bên trong thread xử lý request. Nếu muốn thử khôi phục, nên có **backoff, giới hạn số lần, circuit breaker/degraded state và cơ chế kiểm tra lại**. Nếu appender đã ngừng hoạt động, phải hiểu API lifecycle của backend; đừng đóng/mở FileHandler từ nhiều thread tùy tiện.

## 15. Bảo mật và retention khi giải phóng file

Khi ổ đĩa đầy, ưu tiên bảo toàn dữ liệu có giá trị pháp lý/điều tra:

- Không xóa archive đang trong thời gian retention bắt buộc.
- Không phát tán log chứa token hoặc dữ liệu cá nhân sang kênh console rộng hơn chỉ để có fallback.
- Không upload thủ công log nhạy cảm lên một dịch vụ bên ngoài chưa được phê duyệt.
- Nếu phải nén/chuyển archive, đảm bảo encryption, permission và integrity theo chính sách.
- Đừng mở quyền ghi 777 cho thư mục log để chữa permission error.
- Nếu log đã bị cắt/mất trong sự cố, nên ghi nhận **khoảng thời gian và phạm vi mất dữ liệu** ở hệ thống sự cố riêng; không giả lập lại các bản ghi như thể chúng đã được tạo.
- Giới hạn log payload, stack trace và thông tin nhạy cảm ngay cả khi vẫn còn dung lượng.

**Dọn dung lượng là thao tác vận hành có tác động dữ liệu**, không nên tự động xóa bất cứ file nào chỉ dựa trên đuôi .log mà không biết ownership và retention.

## 16. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý phù hợp |
| --- | --- | --- |
| Coi maxFileSize là giới hạn dung lượng toàn ổ đĩa | Vẫn bị ENOSPC dù rotation đang bật | Kết hợp retention, totalSizeCap và giám sát filesystem |
| Chỉ dùng rotation, không dọn archive | File cũ tăng vô hạn | Đặt lịch sử và ngân sách dung lượng |
| Chỉ xem df -h, bỏ qua inode/quota | Chẩn đoán sai nguyên nhân | Kiểm tra df -i và quota |
| Bắt IOException quanh LOG.info rồi cho rằng bắt lỗi FileAppender | Lỗi ghi bị backend xử lý nội bộ | Dùng status/error reporting của backend |
| Báo lỗi bằng cùng FileAppender đã hỏng | Không nhìn thấy cảnh báo | Kênh lỗi độc lập và health metric |
| Retry ghi file vô hạn | CPU/I/O cao, log storm | Giới hạn retry, degraded state, backoff |
| Xóa file đang mở và mong df giảm ngay | Block còn được giữ bởi file descriptor | Kiểm tra lsof và đóng/reopen có kiểm soát |
| Truncate bừa file active | Có thể mất dữ liệu và phá rotation | Dùng công cụ/policy đã được phê duyệt |
| Cấu hình hai appender rồi gọi là “automatic failover” | Log thường bị nhân đôi, failover không có điều kiện | Thiết kế tuyến xuất đúng, có test |
| Bật DEBUG quá rộng | Log tăng nhanh, đầy disk | Bật có chọn lọc và có thời hạn |
| File logging trong container nhưng không thu file | docker logs/kubectl logs trống | Console hoặc agent đọc file |
| File active đã đầy nhưng chỉ chờ archive cleanup | Vẫn mất log | Kiểm tra trạng thái sink, volume và khôi phục thực sự |
| File đầy chung với dữ liệu nghiệp vụ | Ghi business data cũng thất bại | Tách ngân sách/volume, cân nhắc fail-stop |
| Không ghi nhận mất log trong sự cố | Điều tra sai vì thiếu dữ liệu | Lưu nhận định/incident timeline độc lập |
| Dựa vào console fallback cho audit bắt buộc | Không đạt bảo đảm lưu trữ | Dùng event/audit store bền vững |

## 17. Checklist khi xử lý file log đầy

Có thể dùng checklist này trong tài liệu vận hành:

1. **Có bằng chứng ENOSPC không?** Lỗi nào, đường dẫn nào, vào lúc nào?
2. **Filesystem nào?** File active ở host/volume/overlay/container layer?
3. **Dung lượng còn bao nhiêu?** df -h, tốc độ tăng và các tác vụ khác cùng sử dụng.
4. **Inode/quota có vấn đề không?** df -i, quota hoặc ephemeral storage limit.
5. **Appender nào lỗi?** Logback FileAppender/RollingFileAppender, JUL FileHandler hay hệ thống khác?
6. **Log còn đổ ra đâu?** stdout/stderr, collector, metric, status listener?
7. **Có log bị mất hoặc cắt không?** Từ thời điểm nào, service/replica nào?
8. **Bài toán chỉ ảnh hưởng log hay cả dữ liệu nghiệp vụ?** Có cần tạm ngừng request?
9. **Rotation/retention chạy chưa?** Có archive cũ được phép dọn không?
10. **Có tệp đã unlink nhưng còn mở không?** Xử lý đúng process và thời điểm.
11. **Đã giảm log volume chưa?** Level, payload, stack trace lặp.
12. **Đã có dung lượng an toàn và sink hoạt động lại chưa?** Cần tạo event kiểm tra rồi readback ở đích thật.
13. **Alert/monitoring có nhìn thấy sự cố không?** Có đường giám sát độc lập với file log?
14. **Có cần điều chỉnh kiến trúc không?** Console + collector, quota riêng, archive ở object storage hoặc audit store bền vững?
15. **Đã cập nhật runbook và postmortem chưa?** Nguyên nhân gốc, dữ liệu mất, biện pháp phòng ngừa.

## 18. Tự kiểm tra kiến thức

**Câu 1.** RollingFileAppender đặt maxFileSize=10MB có bảo đảm filesystem không bao giờ đầy?

**Đáp án:** Không. Nó giới hạn segment theo policy, không phải tổng dung lượng cả filesystem. Cần retention, ngân sách archive và giám sát dung lượng thực tế.

**Câu 2.** Gọi LOGGER.info(...) rồi catch(IOException) bên ngoài có chắc nhận được lỗi FileHandler không?

**Đáp án:** Không. JUL/Logback thường xử lý lỗi I/O của Handler/Appender theo cơ chế nội bộ; cần xem ErrorManager/status của backend hoặc dùng một writer có hợp đồng trả lỗi riêng khi cần.

**Câu 3.** Vì sao một file log đã bị xóa nhưng dung lượng df không giảm?

**Đáp án:** Trên filesystem Unix, tiến trình có thể vẫn giữ file descriptor mở tới inode đã bị unlink. Cần kiểm tra và đóng/reopen đúng lifecycle, không xóa bừa file active.

**Câu 4.** Hết inode có phải luôn đồng nghĩa không còn byte trống?

**Đáp án:** Không. Có thể còn byte nhưng filesystem không tạo được file mới vì hết inode. Cần kiểm tra df -i và điều kiện thực tế.

**Câu 5.** Có thể dùng stderr fallback cho mọi sự kiện audit bắt buộc?

**Đáp án:** Không. Console best effort không đủ cam kết tính toàn vẹn, lưu bền vững và kiểm toán; cần cơ chế audit store phù hợp hoặc chính sách từ chối thao tác.

**Câu 6.** Vì sao không nên log lỗi ghi file vào chính FileAppender hỏng?

**Đáp án:** Dòng cảnh báo không thể đến file và có thể tạo lặp lỗi. Cần status channel/metric/console độc lập, có rate limit.

**Câu 7.** Nếu container dùng ConsoleAppender, có còn phải lo dung lượng không?

**Đáp án:** Có. Runtime/node có thể lưu log stream trước khi ship; cần rotation, quota và retention ở tầng hạ tầng.

**Câu 8.** totalSizeCap=100MB của rolling policy có phải hard quota trên tất cả file của ứng dụng không?

**Đáp án:** Không. Nó giới hạn archive theo cleanup policy, không điều khiển mọi file khác, file active hay nhu cầu tạm thời khi rotation/nén.

**Câu 9.** Vì sao ví dụ Java mô phỏng hết dung lượng bằng QuotaOutputStream thay vì tạo file thật rất lớn?

**Đáp án:** Để kiểm thử nhánh IOException và fallback xác định mà không làm đầy filesystem, gây hại cho môi trường học hoặc các dịch vụ khác.

**Câu 10.** Khi df -h cho thấy đã có dung lượng trống, có thể tuyên bố log đã phục hồi ngay không?

**Đáp án:** Chưa. Handler/Appender có thể ở trạng thái lỗi; cần kiểm tra lại bằng event không nhạy cảm và xác nhận bản ghi tới đúng file/collector.

**Ghi nhớ:** Khi file log đầy, vấn đề không chỉ là “xóa bớt file”. Cần **phân biệt rotation và ENOSPC**, hiểu **cách backend báo lỗi ghi**, giám sát **filesystem/quota/inode**, có **đường cảnh báo độc lập**, khôi phục theo retention an toàn và **không đánh đổi tính đúng đắn của nghiệp vụ/audit chỉ để log tiếp tục chạy**.
