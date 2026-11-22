# Nén file log trong Java Logging: GZIP, ZIP, rolling policy và vận hành

## 1. Nén file log là gì?

**Nén file log** (log file compression) là việc mã hóa dữ liệu của file log thành dạng ít tốn dung lượng lưu trữ hơn, thường bằng các thuật toán không mất dữ liệu (*lossless compression*). Trong hệ thống Java, thao tác này phổ biến nhất khi một file đang ghi được **rollover** thành **archive**, sau đó archive được nén thành `.gz`, `.zip` hoặc định dạng được framework hỗ trợ.

Ví dụ đường đi:

~~~text
Logger -> Rolling appender -> logs/app.log     (file đang ghi, plain text)
                                  |
                          Rollover khi đủ điều kiện
                                  |
                                  v
                         app.2026-11-09.log
                                  |
                              Compression
                                  |
                                  v
                    archive/app.2026-11-09.log.gz
                                  |
                       Retention / backup / collector
~~~

Tên file, thời điểm và bước xử lý là mô hình minh họa. Mỗi backend có thể thực hiện rename, nén, dọn file theo cách riêng.

**Điểm cốt lõi:** nén log và xoay log là **hai khái niệm khác nhau**.

- **Rollover / rotation:** kết thúc chu kỳ ghi vào một file, chuyển file cũ sang archive hoặc thế hệ khác, mở/chọn file tiếp tục ghi.
- **Compression:** giảm số byte dùng để lưu nội dung archive, thường được kích hoạt từ tên archive có hậu tố `.gz` hoặc `.zip`.
- **Retention / cleanup:** quy định archive nào được giữ và archive nào bị xóa khi quá tuổi, quá số kỳ hoặc quá tổng dung lượng.
- **Collection:** đưa log từ file, stdout hoặc archive tới hệ thống thu thập tập trung.

Một hệ thống có thể xoay file nhưng **không nén**; có thể nén archive rồi giữ **vô hạn** nếu chưa thiết lập retention; và có thể có retention nhưng vẫn cần đích sao lưu/thu thập riêng.

Trong Logback và Log4j2, cấu hình thông dụng là để **file active ở dạng text bình thường** cho appender ghi liên tục, còn file đã rollover mới mang hậu tố nén. Không nên hình dung rằng cứ đặt `.gz` vào tên archive là mọi byte trong `app.log` đang được stream qua gzip ngay lúc logger gọi `info(...)`.

## 2. Vì sao log có thể nén tốt?

Nhiều log text lặp lại các phần có cấu trúc: timestamp, tên logger, level, operation, field name, ký hiệu JSON, stack trace và template message. Thuật toán lossless có thể biểu diễn các mẫu lặp bằng ít byte hơn.

Ví dụ:

~~~text
2026-11-09T10:00:00Z INFO service=orders operation=checkout state=started id=O-1
2026-11-09T10:00:01Z INFO service=orders operation=checkout state=started id=O-2
2026-11-09T10:00:02Z INFO service=orders operation=checkout state=started id=O-3
~~~

Khi lưu nhiều dòng tương tự, các chuỗi `service=orders`, `operation=checkout` và `state=started` lặp lại, thường tạo cơ hội cho thuật toán nén.

Tuy nhiên **không có tỉ lệ nén cố định** cho mọi file. Tỉ lệ tùy thuộc nội dung, kích cỡ, entropy, encoding và thuật toán:

- Log text nhiều dòng tương tự thường dễ nén hơn chuỗi ngẫu nhiên.
- Log chứa dữ liệu mã hóa, ciphertext, định dạng đã nén, UUID ngẫu nhiên hoặc base64 của dữ liệu khó nén có thể giảm ít.
- Archive cực nhỏ có thể không tiết kiệm được dung lượng, thậm chí tăng nhẹ vì header/trailer của định dạng nén.
- Stack trace lặp thường có mẫu chung, nhưng việc giảm log trùng và chọn event hữu ích vẫn quan trọng hơn chỉ nén.

**GZIP/ZIP không phải mã hóa bảo mật.** Người có quyền đọc file nén thường có thể giải nén lấy nguyên nội dung, bao gồm token, dữ liệu cá nhân hay stack trace nhạy cảm. Compression không thay thế redaction, encryption, phân quyền hay retention.

## 3. GZIP và ZIP: chọn thế nào?

| Tiêu chí | GZIP (`.gz`) | ZIP (`.zip`) |
| --- | --- | --- |
| Cấu trúc cơ bản | Luồng dữ liệu nén, thường dùng cho một file log | Định dạng container có thể chứa một hoặc nhiều entry |
| Cách dùng thường gặp trong rolling | Archive như `app.2026-11-09.log.gz` | Archive như `app.2026-11-09.log.zip` |
| Thuật toán phổ biến | DEFLATE bên trong GZIP | ZIP có nhiều phương thức; DEFLATE thường được dùng |
| Đọc dữ liệu trong Java JDK | `GZIPInputStream` | `ZipInputStream`, `ZipFile` |
| Ghi dữ liệu trong Java JDK | `GZIPOutputStream` | `ZipOutputStream` |
| Khả năng tìm kiếm trực tiếp | Thường phải giải nén hoặc dùng công cụ có hỗ trợ gzip | Công cụ cần đọc entry trong ZIP |
| Phù hợp khi nào | Archive log một file, pipeline hỗ trợ `.gz` | Hệ thống sử dụng container ZIP hoặc công cụ nhận ZIP |

**Không đổi đuôi file thủ công để “nén”.** Đổi `app.log` thành `app.log.gz` bằng rename đơn thuần không tạo ra dữ liệu GZIP hợp lệ. Framework chỉ nén nếu **rolling policy/strategy thật sự có cơ chế compression** và hậu tố được công nhận.

Với Logback, `TimeBasedRollingPolicy` hỗ trợ tự động nén archive khi `fileNamePattern` kết thúc bằng `.gz` hoặc `.zip`. Các phiên bản hỗ trợ `.xz` có thể yêu cầu thư viện XZ phụ thuộc; không tự giả định dependency đó có sẵn. Với Log4j2, rolling file strategy nhận diện `.gz`, `.zip` và một số đuôi khác theo phiên bản/dependency; GZIP và ZIP là hai lựa chọn phổ biến, dễ triển khai nhất.

**Chọn theo cả hệ sinh thái:** log shipper có đọc archive gzip không? Retention quản lý file nào? Quy trình điều tra có phải giải nén rồi tìm kiếm không? Định dạng được hỗ trợ tốt từ lúc ghi tới lúc truy xuất quan trọng hơn việc một định dạng có thể nén nhỉnh hơn chút ít.

## 4. Chu kỳ sống của một file log có nén

Một chu kỳ điển hình:

1. **Mở active file:** appender ghi event dạng text/JSON vào `logs/app.log`; nó phải có quyền ghi và filesystem đủ dung lượng.
2. **Đánh giá trigger:** theo ngày/giờ, kích thước, startup hoặc điều kiện do policy hỗ trợ.
3. **Rollover:** backend chuyển active file sang tên archive hoặc một generation, rồi chuẩn bị file để nhận event tiếp theo.
4. **Compression:** dữ liệu archive được nén sang `.gz`/`.zip` theo strategy.
5. **Cleanup:** chính sách retention xóa các archive thuộc phạm vi quản lý khi đạt điều kiện.
6. **Collection/backup:** pipeline bên ngoài có thể tiếp nhận file active/archive, theo quy tắc riêng của agent.

Thứ tự triển khai chi tiết, thao tác nền và thời điểm hoàn thành khác nhau giữa framework/phiên bản. Đừng giả định `logger.info(...)` trả về là dấu hiệu rằng archive đã nén xong hoặc đã được backup.

### File active và archive khác nhau

~~~text
logs/app.log                                  <- đang được appender ghi
logs/archive/app.2026-11-08.log.gz            <- kỳ cũ, đã nén
logs/archive/app.2026-11-09.0.log.gz          <- kỳ cũ có index size
logs/archive/app.2026-11-09.1.log.gz
~~~

Tên trên minh họa một thư mục archive có thể có nhiều file theo cùng một ngày khi dùng size-and-time rotation. Với cấu hình theo ngày đơn thuần, thường không có chỉ số `%i`.

**Đừng nén trực tiếp một file mà JVM còn đang ghi** bằng một tiến trình độc lập không phối hợp. Nếu thao tác đọc/nén và thao tác ghi đồng thời, archive có thể thiếu dòng, chứa dữ liệu nửa chừng, bị nén trước khi flush hoặc bị log shipper theo dõi sai. Hãy để rolling appender sở hữu thời điểm chuyển file; nếu dùng công cụ ngoài, phải có cơ chế phối hợp và kiểm thử.

## 5. Logback: bật compression qua fileNamePattern

Trong Logback, `RollingFileAppender` ghi file active, còn `TimeBasedRollingPolicy` quyết định tên archive và chu kỳ rollover. Với **SLF4J + Logback**, mã Java vẫn gọi logger SLF4J thông thường; logic nén nằm trong `logback.xml`.

Ví dụ cấu hình hoàn chỉnh, archive theo ngày và nén GZIP:

~~~xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <append>true</append>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>512MB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
~~~

Đặt trong `src/main/resources/logback.xml` để có mặt trên classpath của ứng dụng dùng Logback. Đoạn cấu hình này yêu cầu dependencies SLF4J API và Logback backend tương thích; **JDK đơn thuần không có `RollingFileAppender`**.

Giải thích từng thuộc tính:

- `<file>logs/app.log</file>`: tên file active, thường vẫn ở dạng text/JSON chưa nén.
- `<fileNamePattern>...%d{yyyy-MM-dd}.log.gz</fileNamePattern>`: archive theo ngày và nén bằng gzip; `.gz` là tín hiệu compression được Logback hỗ trợ.
- `<maxHistory>7</maxHistory>`: lưu các **kỳ ngày** gần đây theo policy, không nhất thiết đúng bảy file trong mọi cấu hình.
- `<totalSizeCap>512MB</totalSizeCap>`: giới hạn tổng dung lượng archive theo phạm vi policy; thường yêu cầu maxHistory được thiết lập và không tính mọi file ngoài phạm vi (đặc biệt không tự giới hạn toàn bộ active file/volume).
- `<encoder>`: quyết định định dạng **nội dung log** trước khi nén, không phải tên archive.
- `<appender-ref ref="ROLLING"/>`: nối root logger tới appender; định nghĩa appender mà không tham chiếu có thể không ghi gì.

**Rollover theo thời gian thường cần log event mới sau ranh giới kỳ.** Một ứng dụng ngừng ghi nhiều giờ có thể chưa sinh archive ngay ở 00:00 theo đồng hồ. Chính sách cleanup cũng có thể thực thi ở thời điểm rollover hoặc khởi động theo tùy chọn, nên không bảo đảm archive biến mất chính xác giây đầu tiên nó đủ tuổi.

### 5.1. Đổi sang ZIP

Đối với policy hỗ trợ ZIP, đổi tên archive:

~~~xml
<fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.zip</fileNamePattern>
~~~

Khi Logback nhận diện đuôi `.zip` và policy hỗ trợ, nó tạo file archive nén dạng ZIP. Không nên giả định backend ZIP và GZIP có cùng chi phí CPU hoặc cấu trúc bên trong. Đo trên dữ liệu thực nếu lựa chọn ảnh hưởng vận hành.

### 5.2. Nén cùng rollover theo kích thước và thời gian

Một file mỗi ngày có thể quá lớn; sử dụng `SizeAndTimeBasedRollingPolicy`:

~~~xml
<!-- Thay riêng rollingPolicy trong appender ROLLING. -->
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>512MB</totalSizeCap>
</rollingPolicy>
~~~

Trong cấu hình này:

- `%d{yyyy-MM-dd}` phân biệt kỳ ngày.
- `%i` phân biệt **nhiều archive trong cùng kỳ** nếu một ngày ghi quá nhiều dữ liệu.
- `maxFileSize=20MB` là **điều kiện kích hoạt rollover trên file active**, không phải cam kết tất cả file trên disk đều nhỏ hơn 20MB mọi thời điểm.
- `maxHistory=7` tính theo kỳ thời gian, không có nghĩa tối đa bảy file: có thể có nhiều index một ngày.
- `totalSizeCap=512MB` chủ yếu quản lý tổng kích thước archive do policy kiểm soát, không giới hạn file active hay các file không thuộc pattern.

Không chỉ chèn `<maxFileSize>` vào `TimeBasedRollingPolicy` theo ngày thông thường rồi kỳ vọng policy tự kết hợp kích thước. Khi dùng `SizeAndTimeBasedRollingPolicy`, pattern phải chứa cả `%d` và `%i` phù hợp.

**Lưu ý hiệu năng:** mỗi lần rollover có thể phải rename, tạo directory, nén và xử lý archive. Nếu application ghi rất nhiều và file quá nhỏ, việc nén nhiều file nhỏ tốn tài nguyên và tạo áp lực lên log collector. Chọn ngưỡng hợp lý theo throughput và dung lượng thực tế.

## 6. Apache Log4j 2: RollingFile, Policies và Strategy

Log4j2 tổ chức rolling file bằng `RollingFile`, `Policies` và `RolloverStrategy`; cấu hình khác cú pháp Logback. Tên archive trong `filePattern` có thể kết thúc bằng `.gz` để yêu cầu framework nén file đã rollover.

Ví dụ `src/main/resources/log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="20MB"/>
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

Cấu hình này yêu cầu Log4j2 API/Core tương thích; tự nó không biến thư viện JUL hoặc Logback thành Log4j2.

Ý nghĩa:

1. `fileName="logs/app.log"` xác định active file.
2. `filePattern="...%d{yyyy-MM-dd}.%i.log.gz"` xác định archive với ngày, index và gzip compression.
3. `TimeBasedTriggeringPolicy` xét ranh giới kỳ thời gian lấy từ pattern.
4. `SizeBasedTriggeringPolicy` xét kích thước file active để rollover khi đạt ngưỡng.
5. `DefaultRolloverStrategy max="20"` quản lý **cửa sổ chỉ số** archive theo chiến lược, **không đồng nghĩa giữ archive đúng 20 ngày**. Nếu cần dọn file quá tuổi, nên bổ sung Delete action có điều kiện thích hợp.

Ở Log4j2, sự nén archive được kích hoạt theo hậu tố được hỗ trợ của `filePattern`. Ngoài gzip còn có ZIP và các định dạng khác tùy phiên bản/dependency. Một số tùy chọn như `compressionLevel` có trong rollover strategy; dùng khi có nhu cầu đo chất lượng nén và chi phí CPU, không tự suy đoán rằng nén mạnh hơn luôn tốt hơn.

### 6.1. Dọn archive theo tuổi trong Log4j2

Ví dụ **đoạn thay thế** cho `DefaultRolloverStrategy max="20"` ở cấu hình trên:

~~~xml
<DefaultRolloverStrategy max="20">
    <Delete basePath="logs/archive">
        <IfFileName glob="app.*.log.gz"/>
        <IfLastModified age="P7D"/>
    </Delete>
</DefaultRolloverStrategy>
~~~

Đây là action dùng để xét **các file archive có tên phù hợp và đã quá thời gian quy định**, chạy theo cơ chế rollover/action của framework. Phải kiểm tra pattern/đường dẫn thật trước khi bật delete; không xóa cả thư mục dùng chung có những file ngoài phạm vi log.

- `P7D` là một khoảng thời gian theo định dạng duration được plugin chấp nhận, ở đây là bảy ngày.
- `IfFileName` giới hạn tên file cần xét.
- `IfLastModified` xét mốc thời gian file bị sửa gần nhất, không nhất thiết là thời điểm business event.
- Action cleanup không phải trình quét realtime đảm bảo xóa đúng thời điểm file vừa đủ bảy ngày.

Log4j2 có chiến lược **DirectWriteRolloverStrategy** khi không khai báo `fileName`: file active được viết trực tiếp theo `filePattern`. Đừng áp dụng mù quáng các suy luận về `logs/app.log` cố định sang mode đó; cần đọc cấu hình chiến lược thực tế.

### 6.2. Không dùng “đuôi .gz” để suy ra mọi thứ

Đuôi `.gz` trong `filePattern` bật compression nếu policy/strategy hỗ trợ và đã start thành công. Nó **không** tự quyết định:

- Sự kiện INFO/DEBUG nào sẽ được ghi (do logger level/filter quyết định).
- Tốc độ gửi sự kiện tới collector.
- File đã được flush/close xong trước khi JVM bị kill.
- Archive có được xóa sau bảy ngày hay không.
- File có được mã hóa hoặc ẩn dữ liệu nhạy cảm không.

Với vấn đề production, luôn kiểm tra trạng thái khởi tạo appender và hành vi rollover thực tế thay vì chỉ nhìn XML.

## 7. JUL FileHandler: có rotation nhưng không tự gzip

`java.util.logging.FileHandler` thuộc JDK có khả năng **rotation theo dung lượng và số thế hệ file** qua constructor, ví dụ:

~~~java
// Snippet nằm trong phương thức có xử lý IOException, không phải chương trình độc lập.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "logs/application-%g.log",
                1_048_576, 5, true);
~~~

Các tham số tương ứng là `pattern`, `limit`, `count` và `append`. Ký hiệu `%g` là số generation; `%u` có thể được dùng để tạo tên duy nhất trong trường hợp file bị khóa/xung đột.

**FileHandler của JUL không có tính năng nén GZIP tự động tương đương RollingFileAppender của Logback/Log4j2.** Nếu ứng dụng chỉ dùng JUL và cần compression, có thể:

- Chọn backend có rolling/compression phù hợp qua kiến trúc logging được duyệt.
- Để log rotation và compression cho công cụ ngoài, có cơ chế phối hợp file đã đóng.
- Tự xây quy trình archive nén file **đã được ngừng ghi**, kiểm tra dữ liệu và retention.

Đừng đổi đuôi tên file của JUL thành `.gz` rồi nghĩ nội dung sẽ được nén. FileHandler vẫn ghi theo formatter của nó, không tự chuyển thành GZIP stream chỉ vì tên file.

Với hệ thống có nhiều JVM, `FileHandler` có thể chọn tên duy nhất theo cơ chế locking, nhưng đó **không phải** cơ chế bảo đảm nhiều tiến trình cùng ghi/rotate/nén một file chung an toàn. Mỗi tiến trình nên có ownership file riêng hoặc dùng collector.

## 8. Ví dụ Java 17 chạy độc lập: nén archive GZIP và giải nén kiểm chứng

Để hiểu chính xác “nén file log” mà không cần thư viện ngoài, ví dụ này mô phỏng một lần rollover **khi không có logger/handler nào còn giữ file mở**:

1. Tạo file active chứa hai dòng log UTF-8.
2. Chuyển file active thành file archive chưa nén.
3. Nén archive thành file tạm bằng `GZIPOutputStream`.
4. Giải nén file tạm bằng `GZIPInputStream`, so sánh **byte-for-byte** với nội dung gốc.
5. Khi kiểm chứng thành công mới đổi tên file tạm thành `.gz`, xóa bản plain archive rồi tạo active file mới.
6. In báo cáo ngắn có kết quả dự đoán được.

Đây là **demo về cơ chế file**, không phải một logging appender production. Nó không triển khai đồng bộ với writer đang chạy, atomic rename trên mọi filesystem, retry khi lỗi nén hay retention. Những chức năng đó nên do backend đã kiểm chứng quản lý.

Tạo tệp **GzipLogRotationDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class GzipLogRotationDemo {
    private GzipLogRotationDemo() {
    }

    private static void gzip(Path source, Path destination) throws IOException {
        try (InputStream input = Files.newInputStream(source);
             GZIPOutputStream output = new GZIPOutputStream(
                     Files.newOutputStream(destination,
                             StandardOpenOption.CREATE,
                             StandardOpenOption.TRUNCATE_EXISTING))) {
            input.transferTo(output);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("target", "gzip-demo");
        Files.createDirectories(directory);

        Path active = directory.resolve("app.log");
        Path plainArchive = directory.resolve("app.1.log");
        Path temp = directory.resolve("app.1.log.gz.tmp");
        Path compressed = directory.resolve("app.1.log.gz");

        String initial = "INFO phase=start message=khởi-động\n"
                + "WARN phase=retry attempt=1\n";

        Files.writeString(active, initial, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);

        // Mô phỏng rollover khi file không còn được writer giữ mở.
        Files.move(active, plainArchive, StandardCopyOption.REPLACE_EXISTING);

        // Nén ra file tạm; chưa xóa archive gốc.
        gzip(plainArchive, temp);

        byte[] restored;
        try (GZIPInputStream input =
                     new GZIPInputStream(Files.newInputStream(temp))) {
            restored = input.readAllBytes();
        }

        boolean identical = Arrays.equals(
                initial.getBytes(StandardCharsets.UTF_8), restored);
        if (!identical) {
            throw new IOException("GZIP round-trip verification failed");
        }

        Files.move(temp, compressed, StandardCopyOption.REPLACE_EXISTING);
        Files.delete(plainArchive);

        Files.writeString(active, "INFO phase=running\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);

        System.out.println("archiveExists=" + Files.exists(compressed));
        System.out.println("plainArchiveRemoved=" + !Files.exists(plainArchive));
        System.out.println("roundTrip=" + identical);
        System.out.println("archivedLines="
                + new String(restored, StandardCharsets.UTF_8).lines().count());
        System.out.println("active=" + Files.readString(active,
                StandardCharsets.UTF_8).strip());
    }
}
~~~

Biên dịch và chạy tại thư mục làm việc có quyền ghi:

~~~bash
javac -encoding UTF-8 GzipLogRotationDemo.java
java GzipLogRotationDemo
~~~

**Stdout dự kiến khi chạy thành công:**

~~~text
archiveExists=true
plainArchiveRemoved=true
roundTrip=true
archivedLines=2
active=INFO phase=running
~~~

Giải thích từng kết quả:

- `archiveExists=true` vì `app.1.log.gz` đã được tạo và file tạm chuyển sang tên đích.
- `plainArchiveRemoved=true` vì bản plain archive chỉ bị xóa **sau khi** giải nén và đối chiếu byte thành công.
- `roundTrip=true` xác minh dữ liệu GZIP giải nén giống đúng mảng byte UTF-8 ban đầu, bao gồm dấu tiếng Việt và dấu xuống dòng.
- `archivedLines=2` vì file cũ có hai dòng log.
- `active=INFO phase=running` là nội dung file active mới, cho thấy archive cũ và file đang ghi là hai đối tượng khác nhau.

Các đường dẫn nằm dưới `target/gzip-demo` trong working directory. Demo ghi đè những tên file thử nghiệm này khi chạy lại; hãy dùng **thư mục test riêng**, không chạy tại một thư mục chứa log production trùng tên.

**Giới hạn quan trọng của demo:** `readAllBytes()` nạp cả file đã giải nén vào bộ nhớ để dễ so sánh. Cách này chỉ phù hợp với file test nhỏ. Với archive production hàng GB, dùng giải nén theo luồng và checksum/byte comparison có giới hạn bộ nhớ, hoặc tin cậy framework/verification pipeline đã được kiểm chứng. Việc thay file tạm bằng `Files.move(..., REPLACE_EXISTING)` cũng không bảo đảm nguyên tử trên mọi filesystem; production cần cơ chế xử lý crash và cleanup tốt hơn.

### 8.1. Điều kiện nén là không mất dữ liệu

Nén lossless đòi hỏi:

~~~text
decompress(compress(originalBytes)) == originalBytes
~~~

Nên so sánh **byte** chứ không chỉ số dòng, vì hai file có cùng số dòng vẫn có thể bị đổi ký tự hoặc mất vài byte. Trường hợp encoding (UTF-8), newline (LF/CRLF) và lỗi trong byte stream đều quan trọng.

GZIP có header/trailer và checksum để phát hiện nhiều dạng hỏng dữ liệu; nhưng CRC không phải cơ chế xác thực chống sửa đổi có chủ đích. Muốn bảo đảm tính toàn vẹn ở mức bảo mật, cần thiết kế checksum có xác thực/chữ ký hoặc lưu trữ có cơ chế kiểm soát phù hợp.

### 8.2. Đọc archive nén từ Java

Dùng `GZIPInputStream` theo hướng dẫn của JDK:

~~~java
// Snippet trong phương thức có throws IOException:
try (GZIPInputStream input =
         new GZIPInputStream(Files.newInputStream(archivePath))) {
    byte[] all = input.readAllBytes();
    // Chỉ dùng readAllBytes() khi biết file giải nén đủ nhỏ.
}
~~~

Không dùng `Files.readString(archivePath)` để đọc trực tiếp file `.gz` như text UTF-8; nó chứa byte nén, không phải chuỗi văn bản nguyên bản. Để đọc file lớn, ưu tiên `InputStream` theo luồng hoặc công cụ tìm kiếm/thu thập có hỗ trợ gzip.

## 9. Nén log không thay thế chính sách retention

Ba khái niệm thường bị trộn lẫn:

| Mục tiêu | Cơ chế | Ví dụ |
| --- | --- | --- |
| Giới hạn một chu kỳ file active | Time/size trigger | Xoay file theo ngày hoặc khi đạt 20 MB |
| Tiết kiệm archive trên disk | GZIP/ZIP compression | `.log.gz` |
| Giới hạn thời gian và dung lượng lưu | Retention/cleanup | Giữ 7 kỳ ngày hoặc tổng archive ≤ 512 MB |

Giả sử một hệ thống có log 12 GB/ngày trước nén; nếu archive sau nén còn khoảng 30% số byte ban đầu thì mỗi ngày vẫn khoảng 3,6 GB. Giữ bảy ngày là khoảng 25,2 GB archive, **chưa tính active file, tệp tạm nén, backup, metadata và các file khác**. Nén có thể giảm nhu cầu đĩa đáng kể nhưng không bao giờ thay thế giới hạn lưu giữ.

**Các giới hạn cleanup không nhất thiết có hiệu lực đúng tức thời.** Archive có thể cần chờ rollover hoặc một job cleanup; file đang ghi thường không nằm trong `totalSizeCap` của archive; nhiều instance/appender còn tạo nhiều tập archive riêng. Vì vậy đo **disk usage thật** chứ không lấy một thông số XML làm dung lượng toàn hệ thống.

Không tự xóa archive chỉ vì đã upload lên collector nếu chưa xác nhận collector nhận đủ và chính sách backup/retention cho phép. Ngược lại, đừng để cả máy chủ đầy log cũ vì tưởng compression tự quản lý tuổi file.

## 10. Ước lượng dung lượng nén và chọn ngưỡng

Để tính sơ bộ dung lượng log trước và sau nén:

~~~text
Bytes/ngày chưa nén
  = (event/giây) × (byte trung bình/event) × 86.400

Bytes/ngày sau nén
  ≈ Bytes/ngày chưa nén × (kích thước nén / kích thước gốc)
~~~

**Ví dụ giả định**, không phải một benchmark hay tỉ lệ nén phổ quát:

- 500 event/giây.
- 300 byte/event sau khi đã encode.
- Tỉ lệ `kích thước nén / kích thước gốc = 0,30` (giữ lại 30% số byte, giảm 70%).

Tính:

~~~text
500 × 300 = 150.000 byte/giây
150.000 × 86.400 = 12.960.000.000 byte/ngày
                 = 12,96 GB/ngày (GB thập phân)

12,96 × 0,30 = 3,888 GB archive/ngày
3,888 × 7   = 27,216 GB archive / 7 ngày
~~~

Con số này giả định throughput và tỉ lệ nén ổn định, chưa tính log khác, độ lớn file active, thời điểm rollover, filesystem và backup. Hãy đo trên **log đã được khử bí mật** từ workload thực tế để chọn policy.

### Chọn dung lượng file trước khi nén

- File active quá lớn: rollover hiếm, archive khó di chuyển/đọc và có rủi ro lấp đầy volume.
- File active quá nhỏ: rollover và compression liên tục, nhiều file nhỏ, overhead cao; pipeline thu thập phức tạp hơn.
- Archive quá nhiều: retention và file handle management trở nên tốn kém.
- Compression mức cao: có thể giảm thêm dung lượng nhưng tăng CPU và thời gian nén, tùy dữ liệu.

Đánh giá dưới tải với CPU, disk I/O, throughput, p95/p99 latency, GC/heap, thời gian rollover, compression duration, archive size và dung lượng disk trống. **Không có “kích thước 10 MB” đúng cho mọi ứng dụng**.

## 11. Nén file log và async logging là hai bài toán khác nhau

**AsyncAppender/async logger** có thể đẩy một phần công việc ghi log sang thread khác; **compression archive** là công việc xảy ra khi rollover, có thể được thực hiện theo cơ chế riêng của backend. Hai cơ chế có thể cùng tồn tại nhưng không phải một:

~~~text
Application threads
       |
       v
Async queue (nếu có)
       |
       v
RollingFileAppender / RollingFile
       |
       +--> active file
       |
       +--> rollover --> archive --> compression --> retention
~~~

Nếu queue đầy hoặc JVM bị kill trước khi event được ghi ra active file, việc có nén archive **không cứu được event chưa được lưu**. Nếu compression thất bại, async logging cũng không tự khắc phục archive đang lỗi.

Khi hệ thống có yêu cầu audit không được mất, phải xác định độ bền của toàn đường từ request tới storage; một in-memory queue hay appender file đơn lẻ có thể không đáp ứng yêu cầu đó.

## 12. Log compression trong container và hệ thống thu thập

Trong container hoặc nền tảng orchestration, cách phổ biến là ghi log vào stdout/stderr rồi để runtime và log agent quản lý rotation và collection:

~~~text
SLF4J / Log4j2 / JUL
       |
       v
Console appender / ConsoleHandler
       |
       v
stdout/stderr
       |
       v
Container runtime / log driver
       |
       v
Log agent / collector
       |
       v
Central storage / search / retention
~~~

Mô hình này tránh yêu cầu ứng dụng sở hữu file active/archive bên trong container. Nhưng **không phải mọi môi trường đều giống nhau**: log driver có thể giới hạn kích cỡ file, có chính sách rotation và retention riêng, trong khi một số agent không đọc archive nén tự động.

Nếu ứng dụng vẫn ghi rolling file trong volume:

- Kiểm tra agent có phát hiện file active sau rename/rollover không.
- Kiểm tra agent xử lý `.gz`/`.zip` ra sao: bỏ qua, đọc trực tiếp, hay chờ một job import archive?
- Không cho agent đọc **đồng thời** file active và archive đã nén theo cách sinh bản ghi trùng.
- Không nén/xóa archive trước khi hệ thống thu thập nhận đủ bản ghi.
- Theo dõi disk quota và số file trong volume, vì archive nén vẫn tiêu tốn dung lượng.

Không giả định `kubectl logs` hay lệnh xem console tự đọc những archive `.log.gz` mà ứng dụng đặt trên một volume tùy ý. Đó là hai luồng thu thập khác nhau.

## 13. An toàn, bảo mật và tính toàn vẹn

Compression là công cụ **tiết kiệm không gian**, không phải công cụ bảo mật.

1. **Không ghi bí mật từ đầu.** Không log mật khẩu, OTP, API key, token, cookie hoặc dữ liệu cá nhân không cần thiết; chúng vẫn tồn tại sau khi nén.
2. **Không coi `.gz` là encrypted.** Bất kỳ ai có quyền đọc archive nén thường có thể giải nén. Dùng filesystem ACL, mã hóa storage và kiểm soát quyền truy cập của collector khi cần.
3. **Giữ source khi compression chưa thành công.** Đừng xóa plain archive nếu lệnh nén thất bại hoặc output chưa được xác nhận. Nếu tự viết pipeline, dùng file tạm, kiểm tra, rồi mới chuyển tên/xóa nguồn một cách có kiểm soát.
4. **Chống race khi nén.** Không để writer còn mở file đang được sao chép/nén nếu không có cơ chế đồng bộ rõ.
5. **Đề phòng archive hỏng.** Thiết kế retry/quarantine/alert khi không giải nén được; đừng để lỗi compression làm thất lạc nguyên nhân sự cố vốn nằm trong log.
6. **Giới hạn dữ liệu giải nén.** Một archive nhỏ vẫn có thể giải nén thành dữ liệu rất lớn. Không dùng `readAllBytes()` với archive không tin cậy hoặc không biết dung lượng.
7. **Kiểm tra symlink/đường dẫn khi cleanup.** Tránh quét/xóa nhầm file ngoài thư mục archive, đặc biệt khi đường dẫn do input hoặc mount ảnh hưởng.
8. **Backup và retention:** việc xóa file `.gz` cục bộ không tự xóa các bản sao trên collector, backup hoặc object storage.
9. **Đừng dùng checksum GZIP như chữ ký bảo mật.** Nó giúp phát hiện hỏng dữ liệu ngẫu nhiên, không bảo vệ khỏi chỉnh sửa có chủ đích.
10. **Quan sát lỗi logging.** Ứng dụng có thể tiếp tục xử lý business logic dù file/appender không tạo được archive; cần cảnh báo độc lập về lỗi logging, disk và collector.

Nếu cần tuân thủ lưu giữ bắt buộc, thiết kế hệ thống audit/storage đáng tin cậy riêng, không dựa vào file `.gz` trên một node làm bằng chứng duy nhất.

## 14. Chẩn đoán các lỗi compression thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
| --- | --- | --- |
| File active vẫn là `app.log`, chưa có `.gz` | Chưa tới trigger rollover hoặc chưa có event sau ranh giới | Kiểm tra policy, time/size threshold, tạo event thử nghiệm an toàn |
| Archive tạo nhưng không nén | Pattern không có đuôi hỗ trợ hoặc policy/config không được load | Xem `fileNamePattern`/`filePattern` và status backend |
| Có file `.gz` nhưng giải nén lỗi | Chỉ rename đuôi, file bị ghi dở, nén thất bại hoặc archive hỏng | Kiểm tra magic/format, dùng GZIPInputStream hay công cụ gzip để thử |
| Disk đầy dù đã bật gzip | File active lớn, archive cũ chưa xóa, file tạm, backup hoặc tỉ lệ nén thấp | Đo dung lượng từng thư mục, xem retention và headroom khi nén |
| Không thấy archive đúng 00:00 | Rollover được đánh giá khi có event mới hoặc policy chưa chạy | Kiểm tra cách trigger hoạt động và thời điểm log kế tiếp |
| Archive bị xóa sớm | Retention quá chặt hoặc action xóa match quá rộng | Kiểm tra pattern, maxHistory, delete action và backup |
| Archive không được xóa | Retention thiếu/cleanup chưa chạy hoặc lỗi permission | Kiểm tra thời điểm rollover và thông báo status |
| Nén tốn CPU/độ trễ tăng | File lớn, compression nhiều instance cùng lúc, ngưỡng quá nhỏ | Đo CPU, IO, latency; điều chỉnh ngưỡng/lịch rollover |
| Collector thiếu log cũ | Agent không đọc gzip hoặc archive bị xóa quá sớm | Kiểm tra rotate/rename/compression với agent |
| Collector có log trùng | Đọc file active và archive cùng nội dung, hoặc nhiều appender | Kiểm tra source identity, offset và pipeline |
| Thiếu log trong archive | Writer chưa dừng, async queue chưa drain, kill/crash | Kiểm tra shutdown, flush, lock và tính bền vững |
| ZIP/GZIP rất ít giảm kích thước | Dữ liệu entropy cao hoặc archive quá nhỏ | Đo trên log thật, cân nhắc log volume và định dạng |
| GZIPInputStream báo lỗi | File hỏng, không đúng GZIP hoặc stream bị cắt | Giữ bản gốc nếu còn, quarantine và kiểm tra CRC/size |

### Checklist điều tra thực tế

1. Xác minh logger gọi vào **đúng backend** và đúng file cấu hình.
2. Xác minh **root/logger level, filter và appender-ref** không chặn log.
3. Kiểm tra active file path, quyền ghi, dung lượng trống và số inode/file descriptor.
4. Đọc pattern archive để phân biệt `%d`, `%i`, `.gz`/`.zip`.
5. Kiểm tra policy trigger theo ngày/size và hành vi tại restart.
6. Thử một rollover nhỏ trên môi trường test, không ép nén hàng GB ở production.
7. Đảm bảo archive thực sự giải nén được và giữ nguyên các bản ghi mong đợi.
8. Xem retention có đúng phạm vi xóa và có dọn file tạm thất bại không.
9. Thử hành vi khi collector chậm, file bị rename, archive bị nén/xóa.
10. Đo tài nguyên và lập alert về lỗi backend, disk free, compression duration, archive count và collector lag.

## 15. Bài tập tự kiểm tra

1. **Khái niệm:** giải thích khác nhau giữa rollover, compression và retention. Đặt `.gz` vào tên active file có tự làm writer nén log ngay không?
2. **GZIP và ZIP:** nêu một ưu điểm thực tế của GZIP đối với archive của một file và một tình huống ZIP phù hợp hơn. Vì sao đổi tên `app.log` thành `app.log.gz` không phải nén?
3. **Chạy Java 17:** tạo `GzipLogRotationDemo.java`, chạy với `javac` và `java`, kiểm tra `roundTrip=true` và nội dung file active. Nếu cố tình thay một byte trong archive nén, GZIPInputStream có thể báo lỗi gì?
4. **Logback:** thay `fileNamePattern` từ `.log` sang `.log.gz`; giải thích vai trò của `maxHistory` và `totalSizeCap` khi đã bật compression.
5. **Size + time:** viết pattern Logback có cả `%d` và `%i`, ngưỡng 20MB; giải thích vì sao có thể có nhiều archive trong cùng một ngày.
6. **Log4j2:** chỉ ra vai trò của `RollingFile`, `TimeBasedTriggeringPolicy`, `SizeBasedTriggeringPolicy` và `DefaultRolloverStrategy`. Tại sao `max="20"` không có nghĩa “giữ 20 ngày”?
7. **JUL:** vì sao `FileHandler` dù có `limit` và `count` vẫn không tự tạo `.gz`? Thiết kế một quy trình nén file đã đóng mà không làm mất log.
8. **Tính dung lượng:** với 1.000 event/s và 250 byte/event, hãy tính GB thô/ngày. Nếu nén còn 40% số byte, bảy ngày archive cần khoảng bao nhiêu GB trước backup?
9. **Collector:** trong một hệ thống file-based, nén archive ngay sau rollover có thể ảnh hưởng agent như thế nào? Làm sao kiểm tra không thiếu/trùng event?
10. **An toàn:** vì sao không được log token rồi dựa vào gzip để “bảo vệ”? Nêu chính sách phân quyền và retention cho archive.
11. **Hiệu năng:** so sánh chính sách xoay theo ngày với xoay theo 20MB khi lưu lượng thay đổi mạnh; chọn chỉ số để đo chi phí compression.
12. **Khôi phục lỗi:** nếu nén thất bại giữa chừng, thứ tự hợp lý giữa lưu file gốc, tạo file tạm, verify và cleanup là gì?

## 16. Tài liệu tham khảo chính thức

- Logback — Rolling File Appenders: https://logback.qos.ch/manual/appenders-rolling.html
- Apache Log4j 2 — Rolling File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Java SE 17 — GZIPOutputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html
- Java SE 17 — GZIPInputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html
- Java SE 17 — java.util.logging.FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

**Ghi nhớ:** nén file log trong Java thường là **nén archive sau rollover**, không phải gzip trực tiếp active file. Trong Logback, đuôi `.gz`/`.zip` của `fileNamePattern` kích hoạt compression khi policy hỗ trợ; trong Log4j2, `filePattern` và rollover strategy đảm nhiệm việc nén; JUL FileHandler có rotation nhưng không tự gzip. Luôn đi cùng **retention, kiểm tra dữ liệu, quyền truy cập, dung lượng disk, collector và xử lý lỗi compression** để tiết kiệm bộ nhớ lưu trữ mà không đánh đổi khả năng điều tra.