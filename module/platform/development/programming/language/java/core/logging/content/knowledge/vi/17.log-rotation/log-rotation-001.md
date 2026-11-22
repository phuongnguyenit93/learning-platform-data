# Vì sao cần log rotation trong Java?

**Log rotation** (luân phiên tệp log) là cơ chế **đóng/chuyển một tệp log đang ghi sang một thế hệ lịch sử và tiếp tục ghi vào tệp mới** khi thỏa điều kiện, thường là đạt ngưỡng dung lượng hoặc bước sang kỳ thời gian. Thay vì để một tệp `application.log` tăng kích thước mãi mãi, hệ thống có thể tạo chuỗi như `application.log`, `application.1.log`, `application.2.log` hoặc các tệp có tên theo ngày.

**Mục tiêu chính:** kiểm soát sự phát triển của file log, giảm nguy cơ cạn dung lượng, giúp vận hành và thu gom log dễ hơn, đồng thời xây dựng chính sách lưu trữ có thể dự đoán. Tuy vậy, rotation **không đồng nghĩa** với retention, backup, nén, bảo đảm ghi bền hoặc giám sát: những phần đó cần được thiết kế riêng.

Bài này giải thích **vì sao cần rotation**, những tình huống không có rotation gây sự cố gì, thời điểm chọn luân phiên theo kích thước/thời gian, tác động đến Java Util Logging (JUL), Logback, Log4j2 và những lưu ý khi chạy trong container.

## 1. Nếu không rotation thì điều gì xảy ra?

Giả sử một dịch vụ Java ghi vào một tệp cố định:

```text
/var/log/myapp/application.log

Ngày đầu       150 MB
Sau một tuần   1.1 GB
Sau một tháng  4.5 GB
...            tăng tiếp theo lưu lượng
```

Đây là **số liệu minh họa**, không phải quy luật tốc độ tăng thực tế. Một hệ thống có nhiều request, lỗi lặp lại hoặc bật mức DEBUG có thể sinh dữ liệu nhanh hơn rất nhiều.

### 1.1. Đầy ổ đĩa có thể ảnh hưởng cả ứng dụng

Log thường cùng nằm trên filesystem chứa những thành phần khác của dịch vụ. Khi tệp tăng không giới hạn, có thể xảy ra:

- Không ghi tiếp được log, khiến thông tin điều tra sự cố bị thiếu đúng lúc cần nhất.
- Không tạo được file tạm, cache, checkpoint hoặc dữ liệu ứng dụng.
- Cơ sở dữ liệu, queue hoặc tiến trình khác cùng volume bị ảnh hưởng.
- Container hoặc node bị áp lực dung lượng và phải xử lý sự cố vận hành.
- Log appender/handler ghi file gặp lỗi; hành vi có thể khác theo logging framework và cấu hình.

**Rotation giảm nguy cơ một tệp đơn lẻ tăng vô hạn, nhưng không thể tự bảo đảm ổ đĩa không đầy.** Nếu tất cả các thế hệ file vẫn được giữ không giới hạn, hoặc nhiều ứng dụng ghi trên cùng ổ đĩa, tổng dung lượng vẫn có thể cạn. Cần kết hợp giới hạn lưu trữ, dọn file cũ, dung lượng dự phòng và cảnh báo.

### 1.2. Tệp quá lớn khó thao tác và phân tích

Một tệp hàng chục GB có thể gây bất tiện khi mở bằng editor, chuyển về máy để điều tra, sao lưu, truyền qua mạng hoặc đưa vào pipeline phân tích. Việc phân chia thành những tệp theo kích thước/ngày giúp:

- Xác định tập dữ liệu cần đọc khi biết khoảng thời gian xảy ra lỗi.
- Truyền hoặc lưu trữ từng phần thay vì một file khổng lồ.
- Nén các file đã đóng để giảm dung lượng lịch sử.
- Dọn lịch sử cũ theo chính sách mà không xóa toàn bộ file đang được ghi.
- Khoanh vùng lỗi hỏng/đọc file và thao tác sửa chữa.

Lưu ý: việc log được chia thành nhiều tệp **không tự tạo chỉ mục tìm kiếm**. Nếu cần truy vấn trên nhiều máy theo `traceId` hoặc timestamp, hệ thống log tập trung vẫn quan trọng.

### 1.3. Tăng tính dự đoán cho vận hành

Khi biết cách rollover, số thế hệ lịch sử và tốc độ sinh log, nhóm vận hành có thể ước lượng dung lượng và xây dựng cảnh báo. Rotation giúp đặt quy tắc tương đối rõ:

- Mỗi file active có mục tiêu kích thước tối đa.
- Mỗi ngày/kỳ có nhóm file lịch sử riêng.
- File lịch sử có thể nén, chuyển đi hoặc xóa theo điều kiện.
- Có thể quan sát tốc độ log tăng bất thường.

Đây là **công cụ quản lý tài nguyên**, không phải cơ chế kiểm soát lỗi nghiệp vụ. Để giảm log quá ồn, vẫn cần chọn level hợp lý, sampling/rate limit ở nơi phù hợp và tránh ghi dữ liệu thừa.

## 2. Rotation, retention, compression, archiving khác nhau thế nào?

| Khái niệm | Câu hỏi | Ví dụ | Điều không tự đảm bảo |
| --- | --- | --- | --- |
| **Rotation / rollover** | Khi nào dừng ghi file hiện tại và bắt đầu file mới? | Mỗi 10 MiB hoặc mỗi ngày | Không quyết định lịch sử được giữ bao lâu nếu không có cleanup. |
| **Retention** | Bao lâu hoặc giữ bao nhiêu dung lượng dữ liệu cũ? | Giữ 7 ngày, giới hạn tổng file archive 1 GiB | Không tự bảo đảm các bản ghi đã được thu thập tập trung. |
| **Compression** | Làm nhỏ file lịch sử thế nào? | `.log.gz` cho file đã rollover | Không thay thế rotation, không bảo đảm mức nén cố định. |
| **Archiving** | Chuyển lịch sử đi đâu? | Object storage hoặc hệ thống lưu trữ dài hạn | Không tự xác minh toàn vẹn hay khả năng tìm kiếm. |
| **Backup** | Có bản sao khôi phục độc lập không? | Sao lưu theo chính sách hệ thống | Rotation không mặc nhiên tạo backup. |
| **Log shipping** | Ai đưa record tới nơi tập trung? | Agent đọc file hoặc stdout rồi đẩy tới collector | Không có bảo đảm exactly-once chỉ vì đã rotate. |

**Điểm mấu chốt:** rotation tạo ranh giới giữa file hiện tại và các file lịch sử. **Retention** mới quyết định file cũ bị xóa khi nào. Nếu chỉ cấu hình “mỗi ngày tạo một file mới” mà không giới hạn lịch sử, tổng dung lượng vẫn tăng theo thời gian.

Ví dụ:

```text
application.log              <- file đang ghi
application.2026-11-06.log.gz <- file lịch sử
application.2026-11-07.log.gz
application.2026-11-08.log.gz
```

Tên file là **ví dụ minh họa**, không phải pattern chung của tất cả backend. Tên file thực tế phụ thuộc cấu hình, timezone, kích thước, số lần rollover và chiến lược xử lý file.

## 3. Hai nhóm điều kiện rotation phổ biến

### 3.1. Rotation theo kích thước (size-based)

Một file mới được kích hoạt khi file đang ghi chạm hoặc vượt ngưỡng nhất định, ví dụ 10 MiB. Phù hợp với ứng dụng có tốc độ log biến động, đặc biệt khi xảy ra lỗi lặp nhiều lần.

**Ưu điểm:**

- Giới hạn tương đối kích thước mỗi file để thuận tiện đọc, truyền và nén.
- Tránh một file hoạt động tăng mãi trong thời gian tải đột biến.
- Dễ áp dụng cho hệ thống không cần tách log đúng theo ngày.

**Giới hạn:**

- Một record lớn có thể làm file vượt ngưỡng mục tiêu trước khi rollover.
- Khi log tăng đột biến, file quay rất nhanh; nếu số thế hệ ít thì log cũ bị thay thế sớm.
- File không nhất thiết phân chia theo thời gian một cách thuận tiện.
- “Giữ 5 file x 10 MiB” **không** có nghĩa giữ 5 ngày.

### 3.2. Rotation theo thời gian (time-based)

File được luân phiên theo ngày, giờ hoặc kỳ được cấu hình. Ví dụ:

```text
logs/application-2026-11-07.log
logs/application-2026-11-08.log
logs/application-2026-11-09.log
```

Phù hợp khi nhóm vận hành thường tra cứu theo ngày và có chính sách giữ dữ liệu theo kỳ.

**Ưu điểm:** dễ phân loại theo thời gian, thuận tiện cho việc dọn file cũ hoặc gửi archive theo kỳ.

**Giới hạn:**

- Một ngày nhiều traffic có thể tạo file rất lớn nếu không có size cap.
- Thời điểm rollover trong nhiều backend được kiểm tra **khi có event log mới**, nên không chắc sẽ tạo một file mới đúng 00:00 khi ứng dụng hoàn toàn im lặng.
- Timezone ảnh hưởng tên và kỳ rollover; cần chọn timezone nhất quán.
- Nếu ứng dụng dừng nhiều ngày, không có nghĩa backend sẽ tạo đủ các file rỗng cho ngày không hoạt động.

### 3.3. Rotation kết hợp kích thước và thời gian

Kết hợp hai điều kiện thường có ích cho dịch vụ production: chia theo ngày **và** khi file một ngày vượt ngưỡng thì tăng chỉ số thứ tự.

```text
archive/app.2026-11-09.0.log.gz
archive/app.2026-11-09.1.log.gz
archive/app.2026-11-09.2.log.gz
archive/app.2026-11-10.0.log.gz
```

Trong đó ngày xác định kỳ, còn chỉ số giải quyết trường hợp một ngày sinh nhiều file. Cách ghi tên `%d` và `%i` có trong các backend như Logback/Log4j2; **JUL FileHandler không có cấu hình rotation theo ngày tích hợp tương đương các rolling policies này**.

## 4. Cách suy nghĩ về dung lượng và thời gian lưu

Để đặt giới hạn hợp lý, hãy bắt đầu từ **tốc độ sinh log**, không bắt đầu từ một con số mặc định.

Gọi:

- `V`: tổng byte log sinh trung bình mỗi ngày, bao gồm cả INFO, WARN, ERROR và khi bật chẩn đoán.
- `S`: kích thước mục tiêu của một file.
- `N`: số thế hệ file được giữ trong một chính sách chỉ giới hạn theo số file.
- `H`: thời gian lịch sử mong muốn.

Ước lượng đơn giản, nếu tốc độ ổn định và chưa tính nén/overhead:

```text
Số file/ngày ≈ V / S
Dung lượng nhóm N file ≈ N × S
Số ngày lịch sử xấp xỉ ≈ (N × S) / V
```

Ví dụ: ứng dụng sinh khoảng **100 MiB log/ngày**, mỗi file giới hạn **10 MiB**, chỉ giữ **5 file**. Dung lượng mục tiêu của nhóm file chỉ khoảng 50 MiB, tương đương **nửa ngày** ở tốc độ trung bình, không phải 5 ngày. Nếu gặp log storm, lịch sử thực tế ngắn hơn nữa.

Đây chỉ là **ước lượng để quy hoạch**: tệp có thể vượt nhẹ threshold theo record, các thế hệ file không luôn đầy, kích thước nén khác nhau, overhead của filesystem và tốc độ theo giờ không đồng đều.

Khi đặt chính sách cần xét thêm:

1. **Log storm:** error trong vòng lặp, retry thiếu giới hạn, DEBUG vô tình bật rộng có thể làm lượng log tăng gấp nhiều lần.
2. **Dung lượng của tất cả ứng dụng:** log của một JVM có giới hạn không có nghĩa ổ chung an toàn.
3. **Không gian dự phòng:** cho phép sự kiện đột biến, file chưa được ship hoặc thời gian collector bị gián đoạn.
4. **Lịch sử điều tra:** nếu thông thường phát hiện sự cố sau 48 giờ, giữ log cục bộ dưới 12 giờ có thể không đủ.
5. **Nhu cầu pháp lý/bảo mật:** chính sách lưu trữ có thể khác với thời gian cần để debug; dữ liệu không nên giữ vô hạn.
6. **Tốc độ dọn:** cleanup/retention có thể diễn ra khi rollover hoặc theo lịch, không phải luôn ngay lập tức.

**Lựa chọn hợp lý thường là:** rotation để chia và giới hạn file đang ghi; retention/archiving để quyết định vòng đời lịch sử; monitoring để phát hiện log tăng bất thường hoặc mất khả năng ghi.

## 5. Rotation có ngăn mất log không?

**Không.** Rotation là quản lý file, không phải bảo đảm độ bền. Vẫn có nguy cơ:

- File cũ bị thay thế trước khi log shipper đọc hết.
- Process chết đột ngột khi còn dữ liệu buffered hoặc queue async.
- Thiếu quyền, hết dung lượng hoặc lỗi I/O khiến appender không ghi tiếp.
- Collector đọc file đổi tên chưa đúng cách, dẫn tới bỏ sót hoặc nhập trùng record.
- Chính sách retention xóa file lịch sử quá sớm.
- Lỗi cấu hình khiến nhiều tiến trình dùng một tệp hoặc nhiều pipeline ghi trùng.

Trong hệ thống yêu cầu audit không được mất bản ghi, cần thiết kế lưu trữ có bảo đảm giao dịch/độ bền và cơ chế xác nhận riêng. `RollingFileAppender`, `FileHandler` hay công cụ `logrotate` thông thường không thay thế được audit trail bền vững.

### Rotation còn giúp hay cản trở điều tra lỗi?

Nếu không có rotation, file rất lớn, khó phân tích và dễ làm đầy đĩa. Nếu rotation quá mạnh, lịch sử cần thiết biến mất. Do đó phải chọn **ngưỡng file, số thế hệ/retention và nơi lưu dài hạn** theo thời gian cần điều tra sự cố thực tế.

## 6. Java Util Logging: FileHandler hỗ trợ rotation theo kích thước

Trong JDK, `java.util.logging.FileHandler` hỗ trợ cấu hình:

```java
new FileHandler(pattern, limit, count, append)
```

| Đối số | Ý nghĩa |
| --- | --- |
| `pattern` | Mẫu tên file. `%g` là số thế hệ, `%u` giúp tạo tên duy nhất khi cần tránh xung đột; `%h` là home, `%t` là thư mục temp. |
| `limit` | Giới hạn kích thước tệp theo **byte**; ngưỡng để rollover, không phải số dòng. |
| `count` | Số thế hệ file tối đa handler quản lý; phải là số dương. |
| `append` | `true` để nối tiếp file khi mở, `false` để tạo lại nội dung theo chế độ của handler. |

Ví dụ cấu hình **giới hạn xấp xỉ 1 MiB và giữ 3 thế hệ file**:

```java
// Đoạn minh họa, giả sử IOException được xử lý ở tầng gọi.
java.util.logging.FileHandler file =
        new java.util.logging.FileHandler(
                "app-%u.%g.log",
                1024 * 1024,
                3,
                true
        );
```

Khi file đạt ngưỡng, FileHandler chuyển sang thế hệ tiếp theo và có thể thay dữ liệu cũ nhất trong nhóm đã cấu hình. Với `%g`, tên file thể hiện chỉ số generation; với `%u`, tránh tranh chấp tên/khóa file khi có handler khác cùng pattern. Cơ chế tên/chốt file cụ thể vẫn nên kiểm tra theo JDK và filesystem sử dụng.

**Lưu ý quan trọng của JUL:**

- `limit=0` có nghĩa không áp dụng rotation theo giới hạn kích thước, vì vậy không nên hiểu `count=3` tự làm file chuyển mỗi ngày.
- Dùng `count` ít có thể khiến các record gần đây bị thay quá nhanh trong một đợt log storm.
- FileHandler mặc định có formatter/encoding và handler level theo cấu hình JUL; lựa chọn định dạng cần nhất quán với collector.
- Handler có thể dùng tệp khóa `.lck` và cần `close()` đúng lúc để giải phóng tài nguyên.
- `FileHandler` không có rolling policy theo ngày và cleanup theo độ tuổi linh hoạt như các backend có rolling policy chuyên dụng.
- Khi filesystem nằm trong container, file sẽ không tự được giữ sau khi container bị xóa nếu không có volume hoặc pipeline ship log.

### Cấu hình JUL qua logging.properties

Ví dụ tệp cấu hình, giả sử home directory có quyền ghi:

```properties
.level=INFO
handlers=java.util.logging.FileHandler

java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.pattern=%h/myapp-%u.%g.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
```

Trong dự án có class `com.example.Main` đã biên dịch, có thể khởi động bằng:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Đây là **mẫu nạp cấu hình cho ứng dụng JUL**, không phải lệnh chạy chương trình ở mục tiếp theo (vì chương trình demo cấu hình handler bằng code). Nếu backend thật là Logback/Log4j2, `logging.properties` của JUL không tự điều khiển các rolling appender của backend đó.

## 7. Java 17 chạy độc lập: tự tạo nhiều thế hệ file

Ví dụ sau tạo một **thư mục tạm duy nhất**, ghi nhiều bản ghi qua JUL `FileHandler` với giới hạn nhỏ để chắc chắn kích hoạt rotation, đóng handler, rồi liệt kê tên các tệp lịch sử. Chương trình in **chỉ tên file**, không in đường dẫn temp hay kích thước thay đổi theo máy. Không dùng thư viện ngoài JDK.

**Tệp `RotationDemo.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RotationDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("jul-rotation-");
        String pattern = directory.resolve("app.%g.log").toString();

        Logger logger = Logger.getLogger("demo.rotation");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        // 256 byte/file, 3 thế hệ, mở không append.
        FileHandler handler = new FileHandler(pattern, 256, 3, false);
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            for (int i = 1; i <= 60; i++) {
                logger.info(
                        "event=task.processed item=" + i
                        + " payload=xxxxxxxxxxxxxxxxxxxx"
                );
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<String> names;
        try (Stream<Path> files = Files.list(directory)) {
            names = files
                    .map(path -> path.getFileName().toString())
                    .filter(name -> name.endsWith(".log"))
                    .sorted()
                    .toList();
        }

        System.out.println("generationCount=" + names.size());
        for (String name : names) {
            System.out.println(name);
        }

        // Dọn toàn bộ thư mục tạm sau khi đã kiểm tra.
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path path : files.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }
}
```

**Biên dịch và chạy bằng JDK 17 trở lên:**

```bash
javac RotationDemo.java
java RotationDemo
```

**Standard output dự kiến khi chạy thành công trên filesystem bình thường:**

```text
generationCount=3
app.0.log
app.1.log
app.2.log
```

Vì sao kết quả này có ý nghĩa?

1. `Files.createTempDirectory` tạo một thư mục chưa chứa tệp log, giảm nguy cơ xung đột tên file.
2. Pattern `app.%g.log` đưa số thế hệ vào tên; với `count=3`, JUL quản lý tối đa ba thế hệ cho handler này.
3. Mỗi bản ghi có nhiều hơn vài chục byte; **60 event** vượt xa `limit=256` byte, nên rotation diễn ra nhiều lần và các tên `app.0.log`, `app.1.log`, `app.2.log` được tạo.
4. `logger.setLevel(Level.INFO)` và `handler.setLevel(Level.ALL)` đều cho phép INFO, còn `setUseParentHandlers(false)` tránh ghi trùng ra console do parent logger.
5. `handler.close()` đóng luồng và giải phóng khóa trước khi liệt kê/dọn tệp. Đếm file chỉ theo hậu tố `.log`, không tính file `.lck` nếu có ở giai đoạn handler còn mở.
6. Chương trình chỉ in tên file đã được sắp xếp; đường dẫn temp, thời gian và byte count có thể khác nhưng không ảnh hưởng dòng output dự kiến.
7. Sau khi quan sát, chương trình xóa các file và thư mục tạm. **Trong ứng dụng thật, không xóa file lịch sử ngay sau khi log**, mà áp dụng retention phù hợp và dùng handler có vòng đời dài.

**Giới hạn của demo:** mục tiêu là quan sát **số thế hệ file**, không phải chứng minh luôn giữ được 60 record. Thực tế, các record cũ nhất đã bị rollover và ghi đè vì chỉ có ba thế hệ nhỏ. Đây chính là lý do phải chọn retention/dung lượng phù hợp với nhu cầu điều tra.

## 8. Logback: rotation theo ngày và kích thước

Trong hệ sinh thái SLF4J + Logback, `RollingFileAppender` có thể dùng `SizeAndTimeBasedRollingPolicy`. Ví dụ **đoạn cấu hình** để đặt bên trong `<configuration>` của `logback.xml`:

```xml
<appender name="ROLLING"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

**Giải thích:**

- `file` là tệp hoạt động.
- `fileNamePattern` là tên các file đã rollover, có ngày `%d` và chỉ số `%i` để có nhiều file cùng ngày.
- `maxFileSize` là ngưỡng cho rollover theo dung lượng trong một kỳ.
- `maxHistory` giới hạn **số kỳ lịch sử** muốn giữ, không phải “số file đúng bằng bảy”.
- `totalSizeCap` giới hạn dung lượng lịch sử theo chính sách cleanup, **không phải quota cứng tức thời** của ổ đĩa.
- Encoder quyết định nội dung; rotation không thay đổi level/định dạng của một event.

Phải tham chiếu appender này trong root/logger nếu muốn nhận sự kiện:

```xml
<root level="INFO">
    <appender-ref ref="ROLLING"/>
</root>
```

Hai đoạn trên là **mẫu minh họa**, không phải một `logback.xml` độc lập. Cần kiểm tra thư mục, quyền ghi, phiên bản Logback và cấu hình tương thích. Không thể đem XML Logback áp dụng nguyên xi cho Log4j 2 hoặc JUL.

Khi app không phát log, việc dọn các file cũ có thể không diễn ra đúng thời gian lịch kỳ vọng vì cleanup gắn với vòng đời/rollover. Có thể có tùy chọn dọn lịch sử khi khởi động trong những phiên bản phù hợp, nhưng cần kiểm thử trước khi dùng production.

## 9. Log4j 2: RollingFileAppender

Trong Log4j 2 Core, có thể đặt những chính sách rollover trong `<RollingFile>`. Ví dụ **đoạn cấu hình** dùng trong `<Appenders>` của `log4j2.xml`:

```xml
<RollingFile name="ROLLING"
             fileName="logs/application.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout pattern="%d{ISO8601} %-5level %c - %m%ex%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1"/>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
    <DefaultRolloverStrategy max="7"/>
</RollingFile>
```

Đoạn này cần được tham chiếu từ logger/root, ví dụ `<AppenderRef ref="ROLLING"/>`.

**Điểm cần phân biệt:**

- `TimeBasedTriggeringPolicy` và `SizeBasedTriggeringPolicy` là điều kiện rollover.
- `filePattern` xác định tên file lịch sử.
- `DefaultRolloverStrategy max="7"` liên quan số index/thế hệ mà strategy quản lý, **không tự có nghĩa lưu đúng 7 ngày**.
- Quản lý thời gian lưu, số lượng archive, tổng dung lượng hoặc xóa file theo tuổi cần kiểm tra các action/strategy phù hợp từng version.
- Một cấu hình rolling trong Log4j2 không tự kiểm soát các file do JUL hoặc Logback ghi ra ngoài cùng thư mục.

**Không trộn backend:** `logback.xml`, `log4j2.xml` và `logging.properties` là ba họ cấu hình khác nhau. Nếu code dùng SLF4J, cần xác định provider/backend thực tế trước khi chọn mẫu rolling. Nếu có nhiều provider SLF4J cạnh tranh, cấu hình rotation bạn viết có thể không hề được sử dụng.

## 10. Rotation ở bên trong ứng dụng hay bằng công cụ bên ngoài?

Có hai kiến trúc thường gặp:

**Rotation do logging framework quản lý:** JUL FileHandler, Logback RollingFileAppender, Log4j2 RollingFileAppender mở và quản lý tệp, rollover theo chính sách của backend.

**Rotation do hệ thống ngoài quản lý:** công cụ hệ điều hành hoặc agent thay đổi tên/cắt file theo lịch hoặc size, ví dụ Linux `logrotate`.

Bảng so sánh:

| Tiêu chí | Rotation trong Java backend | Rotation ngoài process |
| --- | --- | --- |
| Bộ phận quyết định rollover | Appender/handler và chính sách logging. | Tool/agent hệ điều hành, theo lịch hoặc ngưỡng. |
| Hành vi khi file đang mở | Backend có thể phối hợp đóng/đổi file theo lifecycle của nó. | Cần đảm bảo producer được thông báo/mở lại đúng, tùy phương thức rename/truncate. |
| Triển khai trên nhiều OS | Phụ thuộc backend, đường dẫn, quyền ghi. | Phụ thuộc công cụ OS/agent sẵn có. |
| Tích hợp theo package/service | Nằm trong cấu hình ứng dụng. | Thường do hạ tầng vận hành quản lý. |
| Dễ gây tương tác sai | Backend và tool ngoài cùng rotate một tệp nếu cấu hình chồng lấn. | Producer tiếp tục ghi vào file descriptor cũ hoặc mất byte khi copy/truncate. |

Đặc biệt trên Unix-like, một tiến trình có thể tiếp tục ghi vào inode đã được đổi tên nếu vẫn giữ file descriptor; do đó dùng `logrotate` bên ngoài không mặc nhiên khiến JVM chuyển sang file mới. Phương án `copytruncate` cũng có rủi ro mất/nhân đôi một số byte trong khoảng sao chép và truncate khi file đang tiếp tục ghi.

**Không để hai hệ thống cùng rotate một file nếu chưa có thiết kế rõ.** Tốt nhất xác định một bên sở hữu chính sách rollover và kiểm thử với chính thư viện/OS đang chạy. Nếu collector chỉ đọc stdout/stderr từ container, có thể hạ tầng container/platform đã quản lý rotation cho log runtime theo cách khác; app không nhất thiết cần `RollingFileAppender` riêng.

## 11. Java service chạy trong container hoặc Kubernetes

Một quy tắc vận hành phổ biến là ứng dụng **ghi console**, sau đó node runtime/agent/collector chịu trách nhiệm thu thập và quản lý các log tương ứng. Khi đó:

- Ứng dụng không nhất thiết tự dùng file rotation bằng Java.
- Vẫn phải theo dõi tốc độ sinh log và giới hạn dung lượng của node/container runtime.
- Nếu collector bị gián đoạn, cần hiểu khả năng đệm và điều kiện mất record.
- Retention dài hạn thường do backend log trung tâm quản lý.
- Log chứa thông tin nhạy cảm vẫn phải được kiểm soát từ ứng dụng.

Nếu ứng dụng **buộc phải ghi file bên trong container**:

- Cần volume phù hợp và quyền ghi.
- Cấu hình rotation/retention chủ động để tránh chiếm filesystem.
- Kiểm tra collector đọc file khi rename/rollover, theo dõi file identity và offset.
- Không để log history chỉ tồn tại trong filesystem tạm rồi kỳ vọng sau khi pod bị xóa vẫn còn.
- Đưa metadata `service`, `instance`, `environment`, `traceId` vào event/pipeline để phân biệt nhiều replica.

Rotation ở ứng dụng và retention ở log trung tâm là hai lớp quản lý khác nhau; một lớp không thay thế lớp kia.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ có một `app.log` mãi mãi | File tăng không giới hạn; dễ đầy disk và khó thao tác. | Áp dụng size/time rotation phù hợp và giám sát dung lượng. |
| Có rollover nhưng không cleanup | Hàng trăm file cũ tích tụ, tổng disk vẫn đầy. | Thiết lập retention, dung lượng tổng và quy trình dọn theo backend. |
| Giữ quá ít thế hệ | Lỗi chưa kịp điều tra đã bị ghi đè. | Dựa vào lưu lượng và thời gian cần giữ để chọn chính sách. |
| Hiểu `count=5` là “5 ngày” | Dữ liệu có thể mất sau vài phút nếu log storm. | Phân biệt giới hạn số file và thời gian lưu thực tế. |
| Chỉ rotate theo ngày khi log storm | Một file trong ngày có thể rất lớn. | Kết hợp size trigger và time trigger nếu phù hợp. |
| Dùng threshold size như giới hạn tuyệt đối | Event lớn có thể khiến file vượt một ít trước rollover. | Để dư headroom, giới hạn kích thước message và giám sát disk. |
| Chỉ dựa vào compression | File active và dữ liệu chưa nén vẫn tăng. | Rotation + cleanup; đo hiệu quả nén theo loại log thật. |
| Dùng `logrotate` bên ngoài đồng thời với rolling appender | Rename/truncate đụng nhau, đọc nhầm file, mất/nhân bản record. | Chọn một cơ chế sở hữu rollover và test phối hợp. |
| Đổi tên file khi JVM vẫn giữ descriptor | App tiếp tục ghi vào tệp đã rename trên một số hệ thống. | Dùng cơ chế mở lại file phù hợp với backend/OS. |
| Bỏ qua collector | File bị xóa trước khi được ship hoặc đọc trùng sau rollover. | Kiểm thử file tailing/offset, backlog và xóa file. |
| Không đóng handler/appender khi shutdown | Dữ liệu buffered/lock chưa được giải phóng. | Dùng lifecycle shutdown, flush/close phù hợp. |
| Ghi file local trong container rồi xem như backup | File có thể mất khi instance bị thay. | Volume, collector hoặc lưu trữ trung tâm theo yêu cầu. |
| Cho mọi request lỗi ghi stack trace rất dài | Tốc độ file tăng, quota/retention bị tiêu thụ nhanh. | Giảm log trùng, đặt level đúng, dùng metric và rate limit khi phù hợp. |
| Lưu log chứa token/payload bí mật | Rotation không ngăn rò rỉ dữ liệu trong mọi thế hệ file. | Mask/redact ở nguồn, phân quyền file, retention và audit truy cập. |

## 13. Checklist khi thiết kế rotation

Trước khi triển khai, hãy rà soát:

- [ ] Ứng dụng có **cần ghi file cục bộ** không, hay console + collector đã đủ?
- [ ] Tốc độ log trung bình, đỉnh và tình huống log storm đã được ước lượng?
- [ ] Ngưỡng size, chu kỳ thời gian và số thế hệ có phù hợp với nhu cầu điều tra?
- [ ] Retention có quy định **thời gian hoặc tổng dung lượng**, không chỉ số lần rollover?
- [ ] Nếu dùng file archive, có cần nén, chuyển đi, backup hoặc kiểm tra tính toàn vẹn?
- [ ] File active, file history, file tạm và log của các service khác có được tính vào ngân sách disk?
- [ ] Appender/handler đang chạy đúng backend và đúng cấu hình trên production?
- [ ] Có xác nhận hành vi khi restart, shutdown, lỗi I/O, đầy disk và quyền ghi sai?
- [ ] Agent/collector có đọc đúng file sau rename/rollover và không mất/trùng dữ liệu?
- [ ] Kịch bản nhiều instance cùng máy hoặc cùng volume đã được kiểm thử?
- [ ] Đã đặt cảnh báo khi dung lượng/log volume hoặc số lỗi ghi tăng bất thường?
- [ ] Dữ liệu nhạy cảm, retention theo chính sách và quyền truy cập các thế hệ file đã được xem xét?

## 14. Câu hỏi tự kiểm tra

1. Vì sao ghi mãi vào `application.log` có thể làm ảnh hưởng cả dịch vụ, không chỉ hoạt động logging?
2. Rotation khác retention, compression và backup ở điểm nào?
3. Nếu log tăng gấp mười trong một giờ, rotation theo size và theo ngày có tác động khác nhau thế nào?
4. Vì sao `count=3` trong JUL không có nghĩa là giữ log ba ngày?
5. Tại sao rotation vẫn có nguy cơ mất log nếu collector đọc chậm hoặc appender async chưa flush?
6. Vì sao hệ thống đã có console collector có thể **không cần** tự cấu hình file rolling trong Java?
7. Với hai hệ thống cùng quản lý một file (rolling appender + tool ngoài), sự cố nào có thể phát sinh?
8. Khi nào retention quá ngắn ảnh hưởng đến điều tra sau sự cố?
9. Vì sao cần theo dõi dung lượng **toàn ổ đĩa** dù một handler đã có giới hạn file?
10. Nếu ứng dụng ghi JSON log, việc đổi formatter có thay được rotation không?

**Kết luận:** Rotation cần thiết vì nó **ngăn một file log phát triển không kiểm soát, giảm rủi ro đầy ổ đĩa, giúp thao tác và tổ chức lịch sử thuận tiện hơn**. Nhưng rotation chỉ là một phần: muốn log thực sự hữu ích và an toàn, cần kết hợp **retention, monitoring, log shipping, quyền truy cập, vòng đời appender và chính sách dữ liệu nhạy cảm**.