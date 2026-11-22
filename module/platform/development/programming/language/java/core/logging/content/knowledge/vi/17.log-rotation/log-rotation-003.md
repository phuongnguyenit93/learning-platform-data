# Rotation theo kích thước trong Java Logging

**Rotation theo kích thước** (*size-based log rotation*) là cơ chế **đóng hoặc chuyển file log hiện hành sang một file lưu trữ (archive) và mở file ghi tiếp** khi lượng dữ liệu của file đạt một ngưỡng được cấu hình. Mục tiêu là không để một file log duy nhất tăng mãi theo thời gian, đồng thời giữ lại một số lịch sử để chẩn đoán lỗi.

Ví dụ: ứng dụng đang ghi `app.log`, cấu hình ngưỡng khoảng 10 MB. Khi file đạt ngưỡng, hệ thống có thể đổi tên nó thành `app.1.log` và bắt đầu file `app.log` mới. Khi file mới tiếp tục đầy, các archive cũ có thể được dịch chỉ số, nén hoặc xóa theo **chính sách lưu giữ (retention)**.

**Điều cần nhớ:** *rotation* là hành động chuyển sang file mới; *retention* là quyết định giữ bao nhiêu file/bao lâu; *compression* là việc nén archive. Ba việc này liên quan nhưng **không đồng nghĩa**. Chỉ cấu hình một ngưỡng kích thước chưa chắc giúp hệ thống không bao giờ hết dung lượng.

## 1. Cơ chế hoạt động của size-based rotation

Sơ đồ khái niệm với một ứng dụng chỉ có một writer:

~~~text
Ứng dụng phát log event
           |
           v
Logger -> Handler / Appender
           |
           v
Kiểm tra lượng byte đang ghi
           |
        Có vượt ngưỡng?
        /           \
      Chưa          Có
       |             |
       v             v
Ghi vào file     Hoàn tất record /
hiện hành        chuyển file hiện hành
       |             |
       |             v
       |         Lưu dưới tên archive
       |             |
       |             v
       |         Mở file mới để ghi tiếp
       |             |
       +-------------+
                     |
                     v
                Ghi sự kiện
~~~

Hình vẽ trên minh họa logic tổng quát. **Thứ tự kiểm tra và rollover đối với một record nằm sát ngưỡng phụ thuộc implementation.** Một backend có thể ghi xong record rồi mới quyết định rotate, hoặc dự báo kích thước sự kiện tiếp theo. Không nên dựa vào ngưỡng `maxFileSize`/ `limit` như một giới hạn byte tuyệt đối cho mọi tình huống.

Các khái niệm:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Active file** | File đang được appender/handler ghi | `app.log` |
| **Archive** | File đã được chuyển khỏi trạng thái đang ghi | `app.1.log`, `app-2026-11-09.3.log.gz` |
| **Size threshold** | Mốc dung lượng dùng để kích hoạt rollover | `10MB` hoặc `10485760` byte |
| **Rollover/rotation** | Đóng/chuyển/gắn tên file cũ, chuẩn bị file mới | `app.log` → archive |
| **Generation/index** | Số thứ tự giúp phân biệt các archive | `0`, `1`, `2` hoặc token `%i` |
| **Retention** | Giới hạn archive được giữ theo số lượng, thời gian hay tổng dung lượng | Giữ 5 file; giữ 7 ngày |
| **Compression** | Nén file archive để giảm dung lượng | `.gz`, `.zip` |
| **Rotation error** | Lỗi ở bước rename, tạo file, nén hoặc xóa archive | Permission denied, disk full, file lock |

Một file archive thường là **lịch sử đã được ghi**, không phải file đang tiếp tục nhận message. Tuy nhiên tên và thứ tự generation thay đổi theo chính sách; không tự suy luận file có số lớn hơn luôn là mới hơn mà không đọc quy ước của backend.

## 2. Vì sao dùng rotation theo kích thước?

Một tiến trình Java phát log liên tục có thể tạo hàng gigabyte dữ liệu nếu chỉ append vào một file. Điều đó gây khó khăn cho:

- **Dung lượng ổ đĩa:** file tăng mãi có thể chiếm hết partition/volume.
- **Công cụ đọc log:** mở hoặc chuyển file rất lớn có thể chậm, khó tải và khó chia sẻ.
- **Collector:** một số hệ thống ingest hoặc sao chép hoạt động tốt hơn với file có kích thước vừa phải.
- **Vận hành:** archive tách nhỏ giúp lưu, nén, kiểm tra và xóa theo chính sách dễ hơn.
- **Tác động khi xảy ra lỗi:** một file quá lớn có thể khiến việc xử lý hoặc khôi phục sau sự cố tốn thời gian.

Tuy nhiên, rotation theo kích thước **không làm giảm số event do ứng dụng tạo ra**. Nó chỉ chia file thành các phần nhỏ. Nếu log INFO mỗi vòng lặp quá nhiều, vẫn cần sửa **log level, message volume, sampling hoặc thiết kế quan sát**. Không nên dùng rotation để che vấn đề spam log.

### Rotation khác truncation và xóa file

~~~text
Rotation:  app.log -> app.1.log, rồi tạo app.log mới
Truncate:  giữ tên app.log, xóa nội dung hiện có
Deletion:  loại bỏ hẳn archive cũ
~~~

`truncate` có thể làm mất lịch sử mà không tạo archive; xóa một file đang được tiến trình giữ mở cũng có thể không giải phóng dung lượng như mong đợi trên một số filesystem. Cần biết backend có cơ chế reopen/rename gì trước khi kết hợp với công cụ bên ngoài.

## 3. Kích thước được đo bằng byte, không phải số ký tự

Ngưỡng của JUL `FileHandler.limit` được mô tả theo **byte**, còn Logback cho phép viết giá trị `maxFileSize` kèm hậu tố như `KB`, `MB`, `GB`.

Một thông điệp ngắn không nhất thiết tạo file ngắn tương ứng vì dữ liệu ghi thực tế còn có:

- Timestamp, level, tên logger, thread và thông tin context.
- Ký tự xuống dòng, dấu phân cách và encoding.
- Stack trace nhiều dòng khi có exception.
- Tên field, dấu ngoặc/quote khi xuất JSON.
- Header/footer của một số formatter/encoder.
- Sự khác biệt số byte của các ký tự Unicode trong UTF-8.

Ví dụ message `"Xin chào"` có nhiều ký tự tiếng Việt mã hóa thành nhiều byte trong UTF-8. **Không dùng `String.length()` để suy ra chính xác dung lượng file** sau khi đi qua formatter/encoder.

Ngoài ra, các mức ngưỡng size thường là **mốc kích hoạt gần đúng**. Một log event có stack trace rất dài có thể khiến file vượt mốc trước khi cơ chế rotate xử lý xong. Vì vậy nếu nơi nhận có giới hạn file cứng (chẳng hạn giới hạn upload), hãy kiểm thử với event lớn và có biện pháp **giới hạn kích thước bản ghi** ở nguồn phát.

### Ước tính lượng dữ liệu

Giả sử:

- Mỗi event sau encoding trung bình **500 byte**.
- Ứng dụng phát **200 event/giây**.
- Trung bình mỗi giây tạo khoảng **100.000 byte** (xấp xỉ 100 kB).
- Mỗi phút khoảng **6 MB** nếu lưu lượng ổn định.

Một file với ngưỡng **60 MB** có thể rollover sau khoảng mười phút trong điều kiện giả định trên; lưu lượng thực tế thay đổi theo loại event, giờ cao điểm và exception. Hãy đo từ hệ thống thật, không chỉ suy từ số request HTTP.

## 4. JUL: java.util.logging.FileHandler hỗ trợ rotation sẵn

Java Util Logging (JUL) có `java.util.logging.FileHandler` trong JDK. Bạn không cần cài Logback chỉ để xoay file theo dung lượng.

Một constructor quan trọng:

~~~java
FileHandler(String pattern, int limit, int count, boolean append)
~~~

Ý nghĩa:

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `pattern` | Mẫu đặt tên file | Có token đặc biệt `%g`, `%u`, `%t`, `%h` |
| `limit` | Ngưỡng xấp xỉ tối đa **byte trên một file** | `0` có nghĩa không giới hạn |
| `count` | Số file trong chu kỳ | Ít nhất 1; không phải số archive ngoài active |
| `append` | Có nối tiếp dữ liệu vào file hiện có khi mở hay không | `false` có thể làm mất nội dung cũ khi khởi tạo |

Ví dụ:

~~~java
FileHandler handler = new FileHandler(
        "/var/log/myapp/app-%g.log",
        10 * 1024 * 1024,
        5,
        true);
~~~

Đây là **đoạn minh họa trong một phương thức Java**. Nó giả định đã import `java.util.logging.FileHandler` và rằng thư mục `/var/log/myapp` tồn tại, tài khoản chạy JVM có quyền ghi. Kết quả không bảo đảm trên Windows nếu dùng đường dẫn Linux.

Với `limit` khoảng **10 MiB** và `count=5`, FileHandler dùng một **vòng file luân phiên** với generation thường từ 0 đến 4. **`count=5` nghĩa là năm file output trong vòng quay, không phải năm archive cộng thêm một active file.** Khi đã quay đủ, file cũ nhất trong vòng quay có thể bị ghi đè.

### Các token tên file của JUL

| Token | Ý nghĩa |
| --- | --- |
| `%g` | Generation number dùng cho rotation |
| `%u` | Số duy nhất để giảm xung đột khi file đang được sử dụng |
| `%t` | Thư mục tạm của hệ thống |
| `%h` | Thư mục home của người dùng |
| `%%` | Một ký tự phần trăm literal |

Nếu `count > 1` nhưng không có `%g` trong pattern, FileHandler có thể tự thêm generation vào tên file. Khi mở log từ nhiều tiến trình, `%u` giúp phân biệt file theo cơ chế lock của FileHandler; tài liệu JDK lưu ý tính tin cậy của cơ chế độc nhất này được bảo đảm chủ yếu cho **local filesystem**, không nên coi là một giải pháp khóa phân tán trên NFS.

**Đừng nhầm `%g`/ `%u` của JUL FileHandler với `%d`/`%i` của Logback.** Chúng thuộc hai hệ định dạng khác nhau.

### Vì sao append và restart quan trọng?

Nếu `append=false`, handler có thể khởi tạo bằng cách mở mới/truncate file hiện có theo cơ chế JUL, khiến dữ liệu của lần chạy trước không được giữ như dự kiến. `append=true` thích hợp khi cần nối tiếp file tồn tại, nhưng không thay thế retention hoặc chính sách xoay vòng.

Khi restart, cần kiểm tra:

- Dữ liệu của file active và archive có được giữ theo cấu hình không?
- Process mới có lấy được lock và mở file đúng pattern không?
- Đường dẫn có thay đổi theo `user.dir`, `%t` hoặc `%h` không?
- Quyền ghi có còn đúng sau khi logrotate/deploy tạo file mới không?

Đừng mặc định một restart sẽ tạo đúng cùng file `app.log`; token và quy tắc lock có thể khiến tên thay đổi.

## 5. Ví dụ Java 17+ chạy được: xoay file sau 300 byte

Ví dụ này dùng **JUL FileHandler**, tạo một thư mục tạm, phát nhiều bản ghi để kích hoạt rotation và kiểm tra kết quả. Mọi thao tác tệp nằm trong **thư mục tạm mới** của chương trình, không chạm file log production.

Tạo file **SizeRotationDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public final class SizeRotationDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("jul-size-rotation-");
        String pattern = dir.resolve("demo-%g.log").toString();
        Logger logger = Logger.getLogger("demo.rotation.SizeRotationDemo");
        logger.setUseParentHandlers(false);

        FileHandler handler = new FileHandler(pattern, 300, 3, false);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        try {
            for (int i = 0; i < 25; i++) {
                logger.info("event=processed seq=" + i
                        + " data=" + "x".repeat(70));
            }
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }

        List<Path> logs;
        try (Stream<Path> files = Files.list(dir)) {
            logs = files.filter(p -> p.getFileName().toString()
                            .matches("demo-[0-2]\\.log"))
                    .toList();
        }
        boolean latestFound = false;
        for (Path file : logs) {
            latestFound |= Files.readString(file).contains("seq=24 ");
        }

        System.out.println("rotated=" + (logs.size() > 1));
        System.out.println("withinCount=" + (logs.size() <= 3));
        System.out.println("latestPresent=" + latestFound);

        for (Path file : logs) {
            Files.deleteIfExists(file);
        }
        Files.deleteIfExists(dir);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SizeRotationDemo.java
java SizeRotationDemo
~~~

**Stdout đã được kiểm chứng trên JDK 17+:**

~~~text
rotated=true
withinCount=true
latestPresent=true
~~~

Giải thích:

1. `Files.createTempDirectory` tạo thư mục riêng giúp tránh va chạm tên hoặc phụ thuộc quyền ghi `/var/log`.
2. `new FileHandler(pattern, 300, 3, false)` yêu cầu giới hạn khoảng **300 byte trên một file**, với tối đa **ba file luân phiên**.
3. Formatter tạo một dòng văn bản cho mỗi record. Chuỗi `"x".repeat(70)` làm mỗi event đủ lớn để sau vài event sẽ chạm ngưỡng.
4. `logger.setUseParentHandlers(false)` ngăn bản ghi bị in thêm qua root console handler; điều này không ảnh hưởng cơ chế rotation của FileHandler.
5. `handler.close()` giải phóng file/lock trước khi đọc lại và xóa file thử nghiệm.
6. `rotated=true` chứng minh có nhiều hơn một generation; `withinCount=true` chứng minh số file phù hợp cấu hình `count=3`.
7. `latestPresent=true` kiểm tra bản ghi cuối `seq=24` vẫn nằm trong vòng file hiện hành/archives.

Chương trình **không khẳng định toàn bộ 25 event được giữ**. Vì chỉ có ba file và mỗi file nhỏ, các generation cũ nhất sẽ bị loại khi vòng quay lặp đủ nhiều. Đó là **retention hữu hạn có mất lịch sử cũ theo thiết kế**, không phải lỗi Java.

**Tại sao không in chính xác tên và kích thước từng file?** Thông tin này có thể thay đổi theo newline, formatter/encoding và thời điểm chuyển generation trên các hệ điều hành. Ví dụ xác nhận những bất biến quan trọng thay vì phụ thuộc tên/tổng byte tuyệt đối.

### Lưu ý về cleanup trong ví dụ

Đường dẫn tạm được tạo riêng; chương trình gỡ `FileHandler`, đóng nó và xóa các file sau kiểm thử. Nếu exception khác xảy ra trước bước cleanup, thư mục tạm có thể còn lại; đây là ví dụ học tập, không phải thư viện quản lý temp file theo mọi tình huống. Khi đưa vào hệ thống thật, quản lý vòng đời handler và quyền file trong tầng cấu hình logging.

## 6. Cấu hình JUL size rotation bằng logging.properties

Thay vì tạo `FileHandler` trong `main`, một ứng dụng có thể cấu hình bằng `logging.properties`:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.pattern = /var/log/myapp/app-%u-%g.log
java.util.logging.FileHandler.limit = 10485760
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.level = ALL
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

**Ý nghĩa:** một FileHandler với ngưỡng khoảng **10 MiB**, năm file xoay vòng, append khi mở lại và `SimpleFormatter` tạo text. Token `%u` giảm xung đột tên giữa các handler/process trên local disk; `%g` phân biệt generation.

Lệnh chạy ứng dụng đã biên dịch:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

`MyApplication` là **class ứng dụng giả định có `main()`**, không phải class được cung cấp trong bài. Đặt JVM property trước tên class hoặc `-jar`, và xác nhận đường dẫn file properties đúng với working directory.

Điều kiện để cấu hình hoạt động:

- Thư mục `/var/log/myapp` tồn tại và **process Java có quyền ghi/tạo/đổi tên**.
- Bộ cấu hình JUL thực sự được nạp, không bị một framework hoặc mã khởi tạo khác thay thế.
- Logger/handler level cho phép những sự kiện cần ghi.
- Volume còn dung lượng/quota; file lock không bị xung đột ngoài dự kiến.
- `limit > 0` nếu muốn size-based rotation; `limit=0` là **không giới hạn**.

### Cẩn thận với count=1

Nếu `count=1` và `limit` rất nhỏ, handler chỉ có một vị trí file trong vòng quay; khi rotate, nội dung cũ có thể bị mất mà không có archive lịch sử thực sự. Nếu mục tiêu là phục hồi sự cố vài giờ trước, cần chọn `count` và limit theo lưu lượng phát sinh log thực tế.

Ví dụ phép tính xấp xỉ: 5 file × 10 MiB ≈ **50 MiB vùng dữ liệu quay vòng**, chưa tính file lock, metadata, sai số bản ghi và hoạt động khác. **Không xem con số này là bảo đảm disk usage cứng** cho mọi sự cố, nhất là khi event rất dài hoặc có nhiều process.

## 7. Logback: RollingFileAppender và chính sách rollover

Với ứng dụng sử dụng SLF4J + Logback, `RollingFileAppender` là thành phần chuyên ghi file có rotation. Trong Logback có hai khái niệm:

- **RollingPolicy:** quy định xử lý khi rollover, tên file archive, nơi ghi tiếp, retention và nén.
- **TriggeringPolicy:** xác định **khi nào** phải rollover; trong một số policy, cùng đối tượng có thể đảm nhiệm cả hai trách nhiệm.

Logback hỗ trợ các lựa chọn liên quan tới kích thước:

| Lựa chọn | Đặc điểm | Khuyến nghị sử dụng |
| --- | --- | --- |
| `SizeAndTimeBasedRollingPolicy` | Mỗi khoảng thời gian có các archive theo index `%i`, giới hạn kích thước `maxFileSize` | Khi cần chia file theo ngưỡng **và** quản lý lịch sử theo ngày/tháng |
| `TimeBasedRollingPolicy` | Archive theo khoảng thời gian và tùy chọn tổng dung lượng `totalSizeCap` | Khi chỉ cần giới hạn tổng archive, không bắt buộc giới hạn kích thước từng file |
| `FixedWindowRollingPolicy` + `SizeBasedTriggeringPolicy` | Rotation theo cửa sổ chỉ số cố định | Cấu hình legacy; Logback hiện khuyến cáo tránh do rename tốn kém |
| `FileAppender` thường | Append vào file không tự có rotation | Không phù hợp nếu cần giới hạn tăng trưởng file |

**Không chọn FixedWindow chỉ vì tên “size-based” nghe trực tiếp hơn.** Tài liệu Logback mới xem `FixedWindowRollingPolicy` là hướng cũ và không khuyến nghị; để người học dễ có retention theo ngày và dung lượng mỗi file, `SizeAndTimeBasedRollingPolicy` là ví dụ chính bên dưới.

### SizeAndTimeBasedRollingPolicy có gì đặc biệt?

Ví dụ pattern:

~~~text
archive/app-%d{yyyy-MM-dd}.%i.log
~~~

- **`%d{yyyy-MM-dd}`** đặt mốc khoảng thời gian; ở đây là theo ngày.
- **`%i`** là chỉ số file archive **trong một khoảng thời gian**; các số tăng khi có nhiều rollover do size trong cùng ngày.
- **Cả `%d` và `%i` đều bắt buộc** trong `fileNamePattern` cho size-and-time policy.
- **`maxFileSize`** là kích thước kích hoạt một rollover trước khi kết thúc khoảng thời gian hiện tại.
- **`maxHistory`** là số **khoảng thời gian** (như số ngày) giữ archive, **không phải số file tổng cộng**.
- **`totalSizeCap`** giới hạn tổng dung lượng **các archive** đã lưu, phối hợp với `maxHistory`; không nên coi nó là giới hạn tuyệt đối của active file và mọi file đang được mở.
- **`cleanHistoryOnStart`** có thể yêu cầu dọn archive cũ lúc start, hữu ích cho ứng dụng ít rollover.

Khi cùng ngày có 50 file archive, đặt `maxHistory=7` **không có nghĩa chỉ giữ 7 file**; nó mô tả tối đa 7 ngày lịch sử, rồi giới hạn tổng archive (nếu được cấu hình) được áp dụng thêm.

Ở một số bản Logback hiện đại, xử lý xóa archive diễn ra **bất đồng bộ** sau rollover. Không nên dùng thao tác kiểm tra ngay lập tức sau một event để khẳng định mọi file cũ đã bị xóa đúng lúc.

## 8. Ví dụ Logback 1.5.18: kích thước kết hợp thời gian

Ví dụ này dùng **Java 17+, Maven, Logback 1.5.18**. Trong cùng một ngày, mỗi khi log đạt khoảng **1 KB**, appender lưu archive có chỉ số `%i`; file hiện hành có tên `app.log`.

Cấu trúc:

~~~text
logback-size-demo/
├── pom.xml
└── src/main/
    ├── java/demo/LogbackSizeDemo.java
    └── resources/logback.xml
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>logback-size-demo</artifactId>
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

Phiên bản được dùng để **kiểm chứng ví dụ**, không phải cam kết là bản mới nhất. Maven sẽ giải quyết các dependency SLF4J cần thiết của Logback. Mã sử dụng API Logback trực tiếp để đóng context khi kiểm thử, nên cần `logback-classic` trên compile classpath.

### 8.2. LogbackSizeDemo.java

Tạo `src/main/java/demo/LogbackSizeDemo.java`:

~~~java
package demo;

import ch.qos.logback.classic.LoggerContext;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogbackSizeDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("logback-size-demo-");
        System.setProperty("LOG_DIR", dir.toString().replace('\\', '/'));

        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        Logger log = LoggerFactory.getLogger(LogbackSizeDemo.class);
        for (int i = 0; i < 90; i++) {
            log.info("event=processed seq={} data={}", i, "x".repeat(100));
        }
        context.stop();

        long archives = 0;
        Path archiveDir = dir.resolve("archive");
        if (Files.isDirectory(archiveDir)) {
            try (Stream<Path> paths = Files.list(archiveDir)) {
                archives = paths.filter(Files::isRegularFile).count();
            }
        }
        System.out.println("activeExists=" + Files.isRegularFile(dir.resolve("app.log")));
        System.out.println("archivesCreated=" + (archives > 0));
    }
}
~~~

Chương trình đặt JVM property `LOG_DIR` **trước lần gọi `LoggerFactory`**, để Logback đọc đúng thư mục tạm trong lúc khởi tạo. Đây là lý do class không có static field Logger khởi tạo sớm hơn `main()`.

Gọi `context.stop()` giúp backend đóng appender trước khi kiểm tra file, thích hợp cho chương trình kiểm thử ngắn. Trong một ứng dụng dài hạn, framework/backend thường quản lý shutdown. **Không gọi stop sau mỗi log event**.

### 8.3. logback.xml

Tạo `src/main/resources/logback.xml`:

~~~xml
<configuration>
  <appender name="ROLLING" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>${LOG_DIR}/app.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>${LOG_DIR}/archive/app-%d{yyyy-MM-dd}.%i.log</fileNamePattern>
      <maxFileSize>1KB</maxFileSize>
      <maxHistory>2</maxHistory>
      <totalSizeCap>10KB</totalSizeCap>
    </rollingPolicy>
    <encoder><pattern>%level | %msg%n</pattern></encoder>
  </appender>
  <root level="INFO"><appender-ref ref="ROLLING"/></root>
</configuration>
~~~

Trong cấu hình:

- `<file>` là active file: `app.log`.
- `fileNamePattern` đặt archive trong directory `archive`, có ngày và index.
- `maxFileSize=1KB` nhỏ **chỉ để kích hoạt rotation nhanh trong bài thử**; production cần chọn ngưỡng dựa workload.
- `maxHistory=2` nghĩa giữ lịch sử theo khoảng thời gian hai ngày (vì pattern dùng ngày), không phải hai file.
- `totalSizeCap=10KB` áp dụng tổng archive theo cơ chế cleanup của Logback; không phải hard limit tức thời của toàn bộ thư mục.
- Encoder `%level | %msg%n` xuất một event trên mỗi dòng.

### 8.4. Biên dịch và chạy

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.LogbackSizeDemo
~~~

**Stdout được kiểm chứng trong môi trường thử nghiệm:**

~~~text
activeExists=true
archivesCreated=true
~~~

Kết quả:

1. File `app.log` được tạo dưới một directory tạm.
2. Các bản ghi INFO đủ lớn để kích hoạt rotation trong cùng ngày.
3. Có ít nhất một file archive ở directory `archive`.
4. Chương trình không tuyên bố chính xác số lượng archive vì cleanup, thời gian và các phiên bản/cấu hình có thể làm thay đổi nó.
5. Ví dụ **giữ lại thư mục tạm để có thể tự kiểm tra các archive**; trong môi trường thử nghiệm, dọn nó khi đã xem xong. Nó không ghi vào file log production.

`SizeAndTimeBasedRollingPolicy` là **kết hợp cả hai cơ chế**. Nó có ngưỡng size để chia file nhiều lần trong ngày và mốc ngày để tổ chức retention; không phải một chính sách chỉ tính byte mà bỏ qua thời gian.

## 9. Vì sao FixedWindowRollingPolicy không phải lựa chọn mặc định mới?

Một số tài liệu đời cũ hướng dẫn:

~~~xml
<rollingPolicy class="ch.qos.logback.core.rolling.FixedWindowRollingPolicy">
  <fileNamePattern>app.%i.log.gz</fileNamePattern>
  <minIndex>1</minIndex>
  <maxIndex>5</maxIndex>
</rollingPolicy>
<triggeringPolicy class="ch.qos.logback.core.rolling.SizeBasedTriggeringPolicy">
  <maxFileSize>10MB</maxFileSize>
</triggeringPolicy>
~~~

Đây là **fragment cấu hình lịch sử**, không phải file XML hoàn chỉnh để copy vào dự án mới.

Cơ chế fixed window cần đổi tên nhiều file khi rotate để duy trì một dải chỉ số. Việc rename có thể chậm và gặp vấn đề trên một số filesystem, đặc biệt khi file đang được tiến trình khác giữ. Tài liệu Logback mới xem `FixedWindowRollingPolicy` là **deprecated** và **không khuyến cáo sử dụng cho cấu hình mới**.

Với nhu cầu thông thường, nên xét:

- `TimeBasedRollingPolicy` + retention/cap nếu chỉ cần dọn archive theo ngày/tổng dung lượng.
- `SizeAndTimeBasedRollingPolicy` nếu **mỗi file archive** cần chia ở ngưỡng kích thước rõ.

Nếu phải duy trì cấu hình fixed window cũ, kiểm tra version Logback, error/status messages và thử rollover trên filesystem thật trước khi nâng cấp; không kết hợp tùy tiện các policy không tương thích trong cùng appender.

## 10. Size rotation với Log4j 2 (so sánh ngắn)

Trong Log4j 2, một **RollingFile Appender** có thể kết hợp:

- **`SizeBasedTriggeringPolicy`** để kích hoạt rollover theo ngưỡng.
- **`filePattern`** để đặt tên archive.
- **Rollover strategy** để quản lý cách đặt chỉ số, nén và chính sách lưu.

Các thuật ngữ tương tự Logback nhưng là **API/configuration của Log4j 2**, không sao chép trực tiếp `SizeAndTimeBasedRollingPolicy` từ Logback sang `log4j2.xml`. Nếu runtime đang dùng Log4j 2, phải đọc cấu hình và tài liệu của đúng backend, không mong đợi `logback.xml` hoặc `logging.properties` có tác dụng.

Điểm chung: **ngưỡng kích thước kích hoạt rollover, strategy/policy quyết định archive và retention**, còn quyền file, volume và quá trình thu thập log quyết định vận hành có an toàn hay không.

## 11. Thiết kế retention đúng nhu cầu

Một ngưỡng nhỏ giúp file dễ đọc nhưng có thể tạo **rất nhiều archive**. Một ngưỡng lớn giảm số lần rollover nhưng file khó xử lý và có thể vượt giới hạn hệ thống thu thập.

Ví dụ hai cấu hình giả định:

| Tham số | Cấu hình A | Cấu hình B |
| --- | --- | --- |
| Ngưỡng mỗi file | 10 MiB | 100 MiB |
| Số event/giây trung bình | 100 | 100 |
| Giả định byte/event | 500 | 500 |
| Dữ liệu log/ngày | Khoảng 4,32 GB | Khoảng 4,32 GB |
| Số lần cần rotate/ngày (ước lượng) | ~412 | ~41 |
| Rủi ro chính | Nhiều file, chi phí rename/cleanup | File lớn, thời gian tải/đọc dài |

Các con số là ước lượng theo **100 × 500 × 86.400 = 4.320.000.000 byte/ngày**, không phản ánh workload cụ thể. Để thiết kế, còn phải xét giờ cao điểm, log exception dài, compression ratio và retention kỳ vọng.

### Đừng nhầm số file với thời gian lưu

Với JUL `limit=10MiB,count=5`, lượng lịch sử chỉ phụ thuộc **dung lượng và tốc độ phát log**. Một đợt spam log có thể ghi đè toàn bộ năm file trong vài giây. Hệ thống không hề cam kết “giữ ba ngày” chỉ vì có năm file.

Với Logback `maxHistory=7` trong pattern theo ngày, đó là retention **theo ngày** của archive, nhưng nếu khối lượng log trong ngày tăng mạnh và `totalSizeCap` nhỏ, các archive cũ có thể bị dọn sớm hơn để đáp ứng cap.

Nếu có yêu cầu **audit** hoặc giữ log tối thiểu theo pháp luật, nên dùng một hệ thống lưu trữ/thu thập bền vững có chính sách độc lập. Rotation cục bộ không phải cơ chế audit bất biến.

### Compression có giúp không?

Đổi archive thành `.gz` có thể giảm dung lượng, nhất là log văn bản lặp nhiều. Nhưng:

- Tỷ lệ nén tùy nội dung, không phải 100% như nhau.
- Nén dùng CPU và I/O.
- Cần giữ đủ chỗ tạm trong lúc rollover/compression.
- Một số collector tail file nén khác file active; phải thiết kế rõ file nào được ingest.

Không giả định file archive nén nhỏ bằng một tỷ lệ cố định rồi dự toán storage quá sát giới hạn.

## 12. Quyền file và filesystem khi rotate

Một process ghi được vào `app.log` chưa chắc có quyền **rename, tạo archive, tạo file mới hoặc xóa archive cũ**. Trên filesystem POSIX:

- Append file hiện có: cần quyền ghi file và quyền đi qua các thư mục cha.
- Tạo file mới: cần quyền **write + execute** trên directory đích.
- Đổi tên/xóa file: thường cần quyền trên directory, còn phụ thuộc ACL/sticky bit/policy.
- Archive path thuộc directory khác: cần quyền thích hợp trên **cả nguồn và đích**.
- Nén: có thể cần thêm temporary space và quyền mở/ghi file nén.

Trên Windows, các quy tắc NTFS ACL và file-sharing handles có thể khiến rename/delete bị từ chối ngay cả khi ghi file hiện tại vẫn ổn. Trên NFS/SMB/volume mạng, semantics về lock, rename và nhất quán có thể khác local disk.

Không sửa lỗi bằng cách chạy JVM dưới **root/Administrator** hoặc dùng `chmod 777` cho cả thư mục log. Hãy xác định **user chạy service**, quyền thực tế và thao tác rollover đang thất bại, rồi cấp đúng quyền tối thiểu.

Các nguyên nhân không liên quan quyền file cũng cần kiểm tra:

- Hết dung lượng hoặc inode.
- Filesystem/mount **read-only**.
- Disk quota bị vượt.
- Log archive nằm trên một volume khác.
- Đường dẫn sai hoặc thiếu thư mục cha.
- File bị khóa bởi process khác.
- Cấu hình backend chưa được nạp hoặc appender không start.

## 13. Log rotation khi nhiều JVM/process cùng ghi

Rotation cục bộ an toàn nhất khi **một backend sở hữu một active file**. Nếu hai JVM ghi chung một file và đều tự rotate:

- Cả hai có thể thấy size vượt ngưỡng gần cùng lúc.
- Một process đổi tên file khi process kia vẫn giữ file descriptor.
- Dòng log có thể vào file cũ/đúng đường dẫn nhưng sai tên mong đợi.
- Archive bị ghi đè, thiếu hoặc không chứa đủ thứ tự như dự kiến.
- Cơ chế lock có thể thất bại hoặc không làm việc như local disk trên volume mạng.

**JUL `%u`** giúp phân biệt tên file giữa các FileHandler đồng thời trên local filesystem, nhưng không phải giao thức phối hợp rotation phân tán. Với Logback, **prudent mode** có các ràng buộc cụ thể và không nên mặc nhiên kết hợp với size-and-time/archive compression trong nhiều JVM mà chưa kiểm tra tài liệu hỗ trợ.

Các phương án thường an toàn hơn:

1. Mỗi process có **đường dẫn file riêng** chứa instance/pod ID khi policy cho phép.
2. Mỗi process ghi **stdout/stderr**, để host/container runtime/collector xử lý.
3. Dùng một dịch vụ thu thập log tập trung, mỗi process là một nguồn độc lập.
4. Khi bắt buộc cùng file, dùng cơ chế được backend và filesystem công bố hỗ trợ, kiểm thử contention và failover thực tế.

Không lấy một bài thử đơn tiến trình thành bằng chứng rotation an toàn trong cluster.

## 14. Docker, Kubernetes và logrotate ngoài ứng dụng

Trong container, nhiều ứng dụng Java không cần trực tiếp quản lý RollingFileAppender: có thể ghi **stdout/stderr** và giao cho container runtime/collector thực hiện rotation, retention, vận chuyển và giám sát.

Khi cần ghi vào file trong container:

- Chọn writable volume với UID/GID, ACL và dung lượng phù hợp.
- Không ghi vào image layer read-only.
- Thiết kế đường dẫn archive, giới hạn dung lượng và quyền nén/xóa.
- Không tạo nhiều process cùng rotate một active file ở shared mount.
- Xác nhận collector có tiếp tục tail file active sau rollover, không bỏ mất đoạn log giữa thao tác rename/reopen.

### Không để hai hệ thống cùng rotate một file nếu không phối hợp

Ví dụ ứng dụng Logback tự đổi tên `app.log`, còn công cụ `logrotate` của hệ điều hành cũng đổi tên/truncate file đó theo lịch. Hai cơ chế độc lập có thể:

- Đổi tên cùng file trong thời điểm cạnh tranh.
- Ghi vào descriptor của file đã bị rename hoặc xóa entry.
- Tạo file active mới với quyền khác, khiến JVM không mở được.
- Mất hoặc lặp dòng log trong khoảng **copytruncate**.

Chọn **một chủ thể chính** chịu trách nhiệm rotation của file, hoặc một cách phối hợp được backend/OS hỗ trợ. Không coi `copytruncate` là không mất dữ liệu: nó có cửa sổ race giữa thao tác copy và truncate.

Với Kubernetes, nhu cầu bảo tồn log thường được giải quyết tốt hơn bằng **log shipping** và storage tập trung, không kỳ vọng archive nằm trong ephemeral Pod sẽ được giữ sau khi Pod bị thay thế.

## 15. Đặt size threshold và retention bao nhiêu?

Không có mốc “10 MB luôn đúng” hay “giữ ba file luôn đủ”. Quy trình ra quyết định thực tế:

1. **Đo dữ liệu:** tổng byte log/ngày, biến động theo giờ, event size trung bình và P99 kích thước event.
2. **Xác định mục tiêu:** cần lưu tại máy bao nhiêu phút/giờ để debug? Collector có giới hạn kích thước file không?
3. **Chọn file size:** đủ nhỏ để công cụ xử lý được, không nhỏ đến mức đổi tên/nén liên tục.
4. **Chọn retention:** số generation (JUL), số khoảng thời gian (Logback), tổng archive cap nếu có.
5. **Dự trữ dung lượng:** chừa không gian cho active file, archive, nén, file tạm và burst bất thường.
6. **Kiểm tra permission:** account chạy JVM tạo được file mới, rename archive và cleanup.
7. **Kiểm thử workload:** ghi đủ để vượt ngưỡng vài lần, restart và thử rolling nhiều lần.
8. **Giám sát thực tế:** metric dung lượng, lỗi appender, archive growth, file retention và collector ingestion.

### Bài tính đơn giản

Giả sử ứng dụng tạo **600 MiB log/ngày**. Nếu dùng JUL `limit=20MiB`, `count=10`, tổng cửa sổ lưu có kích thước xấp xỉ **200 MiB**, tương đương khoảng **8 giờ** ở tốc độ trung bình, *nếu log phân bố đều*. Trong giai đoạn lỗi nhiều sự kiện, cửa sổ này có thể rút xuống rất ngắn.

Nếu cần giữ log phục vụ sự cố ít nhất **ba ngày**, cấu hình JUL đó không đáp ứng dù có mười file. Hãy tăng khả năng lưu, thu thập ra storage tập trung hoặc chọn cơ chế retention theo thời gian phù hợp.

Tương tự, Logback `maxHistory=3` (với pattern ngày) không tự đảm bảo đủ dung lượng cho ba ngày nếu storage cap nhỏ hơn dữ liệu tạo ra; cần thiết kế **cả thời gian và dung lượng**.

## 16. Các lỗi rotation theo kích thước thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| File tăng mãi, không rotate | JUL `limit=0`, Logback dùng FileAppender thường, policy chưa được nạp | Kiểm tra active handler/appender và cấu hình runtime |
| Có rotation nhưng không còn log cũ | JUL `count` nhỏ, archive bị ghi đè; retention quá ngắn | Tăng capacity hoặc chuyển log tới kho tập trung |
| File vượt ngưỡng vài byte hoặc một event lớn | Ngưỡng là trigger xấp xỉ, event có kích thước lớn | Kiểm thử record cực dài; giới hạn event size |
| Log không xuất sau rollover | Không tạo được file mới, thiếu quyền hoặc đích sai | Kiểm tra status/handler error, quyền directory |
| Chỉ rotate khi có bản ghi mới | Trigger được kiểm tra khi phát log, không phải tác vụ đồng hồ liên tục | Phân biệt trigger theo event và lịch hệ thống |
| Appender báo thiếu `%i` | `SizeAndTimeBasedRollingPolicy` có pattern sai | Bổ sung cả `%d` và `%i` |
| Đặt `maxHistory=5` nhưng có hơn năm file | maxHistory tính **khoảng thời gian**, không phải file | Xem pattern ngày/tháng và giới hạn tổng archive |
| `totalSizeCap` không làm tổng thư mục dưới mức cap tuyệt đối | Cap chủ yếu áp dụng archive, active file và cleanup async còn tồn tại | Theo dõi tổng disk usage, đặt headroom |
| Archive không nén | Pattern không dùng đuôi compression hoặc config không hỗ trợ | Kiểm tra fileNamePattern/rolling policy |
| Đổi tên archive lỗi trên Windows | File được tiến trình khác giữ hoặc ACL/sharing mode | Kiểm tra process/file handles, chọn chính sách phù hợp |
| Log mất sau deploy/restart | `append=false`, path đổi, hoặc directory ephemeral | Kiểm tra append, persistent storage và log shipping |
| Log xuất hai lần | Nhiều handler/appender, additivity, bridge trùng | Lần theo một event qua pipeline |
| Cả Logback và logrotate cùng thao tác | Hai bộ rotation cạnh tranh | Chọn một chủ thể hoặc tích hợp reopen an toàn |
| Nhiều JVM ghi chung file, archive sai | Không có phối hợp locking/rename giữa process | Mỗi instance một file hoặc stdout/collector |
| Disk full dù đã rotate | Retention/cleanup thiếu, nhiều appender, archive ngoài phạm vi cap | Xem disk, quota, inode, retention thực tế |
| JUL %u làm xuất nhiều nhóm file | Có handler/process lock xung đột | Kiểm tra instance, lock và tên file, không xóa lock tùy tiện |

### Hệ thống không báo lỗi cho mã nghiệp vụ thì sao?

Logging backend có thể ghi lỗi vào **kênh nội bộ** mà không ném exception khi application code gọi `logger.info(...)`. Với Logback, xem **StatusManager/status listener** và startup diagnostics. Với JUL, xem **FileHandler ErrorManager** và stderr/config. Sau khi sửa lỗi, thử phát một event có ID kiểm thử rồi xác minh nó nằm trong active file hoặc archive thích hợp.

Đừng chỉ kiểm tra “không có exception” để kết luận rotation đang bảo toàn dữ liệu.

## 17. Bài tập thực hành

### Bài 1 — Ý nghĩa của count

Cho JUL:

~~~java
new FileHandler("logs/app-%g.log", 1_048_576, 4, true);
~~~

**Câu hỏi:** cấu hình này bảo đảm giữ bốn archive cộng một file active hay bốn file tổng cộng? Nếu có quá nhiều log, chuyện gì xảy ra?

**Đáp án:** vòng FileHandler có **bốn file tổng cộng**. Khi xoay đủ, generation cũ bị thay thế; nó không bảo đảm retention theo số ngày.

### Bài 2 — File lớn hơn limit

FileHandler có `limit=1000` byte nhưng một event chứa stack trace dài hàng nghìn byte. **Câu hỏi:** có phải Java bắt buộc chẻ một exception thành nhiều file để mỗi file không vượt 1000 byte?

**Đáp án:** **Không.** Giới hạn là mốc kích hoạt rotation xấp xỉ; không phải bảo đảm tự cắt mỗi event lớn thành nhiều phần. Nên giới hạn event size và kiểm thử thực tế.

### Bài 3 — Logback maxHistory

Một `SizeAndTimeBasedRollingPolicy` có `fileNamePattern="app-%d{yyyy-MM-dd}.%i.log"`, `maxFileSize=5MB`, `maxHistory=7`.

**Câu hỏi:** có thể có 30 archive trong cùng một ngày không? Cấu hình có tự giữ đúng 7 file không?

**Đáp án:** **Có thể có nhiều file mỗi ngày** do index `%i`; `maxHistory=7` là giới hạn **7 khoảng ngày**, không phải 7 file. Dung lượng còn phụ thuộc `totalSizeCap` và cleanup.

### Bài 4 — Vì sao rotate bị lỗi nhưng append vẫn chạy?

Một process có quyền write lên file `app.log`, nhưng thiếu quyền tạo file mới trong directory. **Câu hỏi:** hành vi nào có thể xảy ra?

**Đáp án:** append file hiện tại có thể hoạt động; khi rotate, rename/create file active hoặc archive thất bại. Cần kiểm tra quyền directory, không chỉ file.

### Bài 5 — Hai JVM dùng cùng file

Hai instance cùng ghi và rotate `/data/app.log` trên shared volume. **Câu hỏi:** tại sao chỉ chọn một ngưỡng size giống nhau không đủ?

**Đáp án:** rotation có thao tác rename, file lock, reopen, cleanup và ghi đồng thời. Cần một cơ chế phối hợp được hỗ trợ, hoặc mỗi instance có file riêng/đưa log qua stdout và collector.

### Bài 6 — Chọn size theo lưu lượng

Một service sinh khoảng **1 MiB log mỗi phút** và dùng 6 file JUL với `limit=10MiB`. Nếu tốc độ không đổi, cửa sổ lịch sử trung bình là bao lâu?

**Đáp án:** khoảng **60 phút** vì tổng dung lượng gần `6 × 10MiB = 60MiB`. Đây là **ước lượng**, không phải retention có bảo đảm; peak log và dung lượng record ảnh hưởng.

## 18. Checklist triển khai size-based rotation

- [ ] Xác nhận **backend thực**: JUL, Logback, Log4j 2 hoặc hệ thống khác.
- [ ] Phân biệt **ngưỡng byte**, **điều kiện trigger** và **retention**.
- [ ] Với JUL, kiểm tra `limit`, `count`, `append`, `%g`/`%u`.
- [ ] Với Logback, dùng policy phù hợp và đúng `%d` + `%i` khi chọn size-and-time.
- [ ] Phân biệt `maxHistory` theo **period** và `totalSizeCap` theo dung lượng archive.
- [ ] Không hiểu size threshold là byte ceiling tuyệt đối trong mọi event.
- [ ] Giữ khoảng trống disk/quota cho active file, archive, compression và burst.
- [ ] Đảm bảo user JVM có quyền ghi **file và directory archive**, kể cả rename/delete.
- [ ] Không để hai JVM/appender độc lập rotate cùng một active file nếu không có hỗ trợ rõ.
- [ ] Không đồng thời dùng logrotate ngoài ứng dụng và rotation trong backend khi chưa có cơ chế phối hợp.
- [ ] Kiểm thử rollover thực, nhiều lần, cả restart, quyền file và collector tailing.
- [ ] Dùng event có ID kiểm thử để xác minh archive và active file; không chỉ xem startup success.
- [ ] Giám sát log-volume growth, lỗi rotation, archive cleanup và dung lượng còn lại.
- [ ] Với Docker/Kubernetes, ưu tiên stdout/stderr và logging pipeline của nền tảng nếu phù hợp.
- [ ] Nếu cần audit bền vững, dùng hệ thống lưu trữ chuyên dụng, không phụ thuộc vòng file cục bộ.

## 19. Tài liệu chính thức

- [JDK 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): constructor `limit/count/append`, token `%g/%u` và quy ước xoay file.
- [Logback — Rolling file appenders](https://logback.qos.ch/manual/appenders-rolling.html): `SizeAndTimeBasedRollingPolicy`, `maxFileSize`, `maxHistory`, `totalSizeCap` và cảnh báo về `FixedWindowRollingPolicy`.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): cách nạp `logback.xml`, status nội bộ và chẩn đoán cấu hình.

**Kết luận:** Rotation theo kích thước là cơ chế **giữ mỗi file log ở kích thước có thể quản lý và xoay sang file mới khi đạt ngưỡng**. JUL cung cấp `FileHandler(limit, count, append)`; Logback cung cấp `RollingFileAppender` và các rolling policy. Một thiết kế đúng phải xét **kích thước theo byte, retention, quyền tạo/rename, restart, nhiều tiến trình, collector và dung lượng thực tế**. Rotation giúp kiểm soát file; nó **không tự bảo đảm không mất log hoặc giữ lịch sử lâu dài**.