# Đọc file log trong Java: xem, lọc, theo dõi và phân tích an toàn

Khi một ứng dụng Java ghi log ra file, bước tiếp theo trong điều tra sự cố là **đọc đúng file log**, hiểu cấu trúc bản ghi, lọc đúng sự kiện và biết liệu log có đang được cập nhật hay đã bị xoay vòng (**rotation**). Đọc file log không chỉ là mở một file văn bản: một request có thể tạo nhiều event, một exception có thể trải dài nhiều dòng, file có thể rất lớn, và log được nhìn thấy trong terminal chưa chắc là toàn bộ dữ liệu đã được lưu.

Chủ đề **“Đọc file log”** thuộc nhóm **File logging**. Bài này hướng dẫn cách tìm file, xem phần đầu/cuối, theo dõi log mới, tìm bằng level hoặc correlation ID, đọc bằng Java 17 với UTF-8 và bộ nhớ giới hạn, xử lý file đã nén, đọc multiline stack trace, đánh giá độ tin cậy và bảo vệ dữ liệu nhạy cảm.

**Mục tiêu sau bài học:** có thể đọc một file log nhỏ hoặc lớn, phân biệt **dòng vật lý** với **log event**, không bỏ qua file rotation, biết khi nào phải dùng parser/collector thay vì thao tác trên text, và tự chạy một chương trình Java 17 đọc log bằng `BufferedReader`.

## 1. Đọc file log là đọc thứ gì?

Một file text log điển hình có thể có nội dung:

```text
2026-11-09T10:00:00Z INFO  requestId=req-7 event=start
2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry
2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed
java.lang.IllegalStateException: upstream unavailable
    at com.example.PaymentClient.call(PaymentClient.java:42)
2026-11-09T10:00:03Z INFO  requestId=req-7 event=done
```

Đây là **dữ liệu minh họa**. Có **sáu dòng vật lý** nhưng **bốn event** theo quy ước format: dòng exception và stack frame thuộc event `ERROR`. Nếu đếm bằng `wc -l`, kết quả là số dòng được ngắt trong file, **không phải số sự kiện**.

Một event thường có:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Timestamp | Khi sự kiện xảy ra theo đồng hồ được ghi nhận | `2026-11-09T10:00:02Z` |
| Level | Độ nghiêm trọng của sự kiện | `INFO`, `WARN`, `ERROR` |
| Logger/category | Thành phần phát event | `com.example.PaymentClient` |
| Thread | Luồng phát log hoặc metadata liên quan | `http-worker-2` |
| Correlation ID | Nối những log của cùng hoạt động | `requestId=req-8` |
| Message | Thông điệp nghiệp vụ/kỹ thuật | `event=failed` |
| Throwable | Exception và stack trace (nếu có) | `IllegalStateException` |

**Không phải mọi file đều dùng format này.** JUL, Logback, Log4j 2, Spring Boot và các encoder JSON có kiểu đầu ra riêng. Cần xem **formatter/layout/encoder thực tế** trước khi viết lệnh tìm kiếm hoặc parser.

## 2. Tìm đúng file log trước khi đọc

Đầu tiên hãy xác định **ứng dụng có thật sự ghi file hay không**. Một service container có thể chỉ xuất log ra stdout/stderr để agent bên ngoài thu thập; khi đó sẽ không có `application.log` trong thư mục dự án.

Các vị trí thường gặp trong dự án hoặc môi trường:

- File tương đối: `logs/application.log` hoặc `logs/server.log`, tính từ **working directory của tiến trình**, không nhất thiết là thư mục chứa JAR.
- File tuyệt đối: ví dụ `/var/log/myapp/application.log` trên máy Unix-like.
- Đường dẫn được chỉ định qua cấu hình `logging.file.name`/`logging.file.path` của Spring Boot trong những trường hợp backend sử dụng các property đó.
- File appender do Logback/Log4j 2 cấu hình bằng `<file>` hay tương đương.
- JUL `FileHandler`, với tên file có thể chứa ký hiệu như `%h`, `%t`, `%g`, `%u` theo quy ước của Java.
- File được hệ thống/chạy service redirect từ stdout hoặc stderr, ví dụ `java -jar app.jar >out.log 2>err.log`.

**Đừng suy ra từ tên class:** `LoggerFactory.getLogger(MyService.class)` chỉ tạo/lấy logger theo category; nó **không quyết định** file nằm ở đâu. Cấu hình appender/handler và các tham số lúc khởi động mới quyết định nơi ghi.

Cách kiểm tra theo trình tự:

1. Tìm cấu hình thực sự được load khi ứng dụng khởi động.
2. Xác định **file appender/handler có được gắn với logger/root** và có chạy hay không.
3. Xác định đường dẫn thực tế, working directory, container volume/mount và quyền của tài khoản chạy tiến trình.
4. Xem có rolling policy, nén `.gz`, hậu tố ngày hoặc số thứ tự không.
5. Phân biệt file **đang ghi hiện tại** với **file lưu trữ đã rotation**; thông tin lỗi cũ có thể ở file archive.

Tìm thấy file đúng tên nhưng mốc thời gian quá cũ chưa chứng minh ứng dụng ngừng log: có thể mức log bị lọc, file hiện tại đã chuyển sang tên khác, hoặc ứng dụng chỉ còn ghi stdout/stderr.

## 3. Đọc nhanh bằng lệnh trên Linux/macOS

Các lệnh này đọc **file có sẵn** (đã xác định đường dẫn và quyền đọc). Chúng minh họa thao tác shell, không phải Java code.

### Xem kích thước và thông tin file

```bash
ls -lh -- logs/application.log
```

`ls -lh` cho thấy kích thước theo đơn vị dễ đọc và thời gian sửa đổi trong kết quả liệt kê. Tùy hệ Unix, một số lệnh có lựa chọn `--` khác nhau; nếu dùng môi trường không hỗ trợ, xem hướng dẫn `ls` của hệ đó.

### Xem vài dòng đầu và cuối

```bash
head -n 20 logs/application.log
tail -n 100 logs/application.log
```

- `head`: những dòng đầu file (thường hữu ích khi xem log startup).
- `tail`: những dòng cuối file (thường hữu ích khi xem lỗi gần đây).
- `-n 100`: giới hạn **100 dòng vật lý**, không nhất thiết là 100 log event. Một stack trace dài có thể chiếm gần hết 100 dòng.

### Mở file để tìm và cuộn

```bash
less logs/application.log
```

Trong `less`, có thể tìm `/requestId=req-7` rồi nhấn Enter, nhấn `n` để tới kết quả tiếp theo, và `q` để thoát. `less` thường thích hợp hơn việc `cat` toàn bộ file nhiều GB ra terminal. Công cụ và phím tắt cụ thể phụ thuộc môi trường.

### Tìm theo chuỗi định danh

```bash
grep -n -F 'requestId=req-7' logs/application.log
```

- `-n` thêm **số dòng vật lý**.
- `-F` tìm chuỗi literal, tránh phải hiểu các dấu trong request ID như regex.
- Với pattern do người dùng cung cấp, nên cân nhắc thêm `--` hoặc cơ chế truyền pattern an toàn theo môi trường để không biến giá trị thành cờ/lệnh.

Tìm những dòng có chữ WARN hoặc ERROR bằng regex đơn giản:

```bash
grep -n -E ' WARN | ERROR ' logs/application.log
```

Đây là **phép tìm text**, không phải parser log tổng quát. Nó có thể khớp phần message của một event INFO có chứa chữ ERROR, hoặc bỏ sót format có dấu ngoặc, level khác. Với log production, nên dùng tiêu chuẩn format/structured fields.

### Lọc theo nhiều điều kiện

```bash
grep -F 'requestId=req-7' logs/application.log | grep -E ' WARN | ERROR '
```

Pipe này tìm trên **những dòng** chứa ID và level text; các dòng stack trace tiếp nối không chứa request ID có thể không xuất hiện. Khi điều tra exception, cần xem **vùng văn bản xung quanh** hoặc dùng collector đã ghép multiline.

Một cách xem ngữ cảnh xung quanh kết quả trên GNU grep:

```bash
grep -n -C 5 -F 'event=failed' logs/application.log
```

`-C 5` hiển thị năm dòng trước/sau mỗi kết quả. Nó giúp xem stack trace nhưng **không bảo đảm** toàn bộ exception rất dài được lấy đủ.

### Đếm dòng vật lý

```bash
wc -l logs/application.log
```

`wc -l` đếm ký tự xuống dòng LF theo ngữ nghĩa công cụ; nếu dòng cuối không kết thúc bằng newline, con số có thể khác số dòng `BufferedReader.readLine()` đọc được. Nó **không đếm đúng log event** khi có multiline stack trace hoặc message chứa newline.

## 4. Theo dõi file log đang cập nhật: `tail -f` và `tail -F`

Khi ứng dụng vẫn đang chạy, ta có thể muốn xem log mới xuất hiện theo thời gian thực gần đúng:

```bash
tail -n 50 -f logs/application.log
```

Lệnh hiển thị 50 dòng cuối rồi tiếp tục theo dõi nội dung được bổ sung. Dùng `Ctrl+C` để dừng. Nó chỉ hiển thị khi bytes mới **đã được tiến trình ghi/flush đến file mà công cụ đang theo dõi**; không bảo đảm event xuất hiện ngay lập tức lúc mã gọi logger.

### Tại sao `tail -f` có thể bỏ lỡ log sau rotation?

Có hai kiểu chuyển file thường gặp:

**Rename rồi tạo file mới:**

```text
logs/application.log   (file A)
        |
        | rotation
        v
logs/application.log.1 (file A, tên mới)
logs/application.log   (file B mới)
```

Một công cụ follow **file descriptor/inode cũ** có thể vẫn theo file A, trong khi ứng dụng đang ghi vào file B. Với GNU coreutils, `tail -F` theo dõi **tên đường dẫn** và thử mở lại sau khi file bị thay thế, nên thường phù hợp hơn khi log rotation kiểu rename:

```bash
tail -n 50 -F logs/application.log
```

`-F` không đồng nghĩa với “không bao giờ mất một byte”: còn phụ thuộc lịch kiểm tra file, thời điểm ứng dụng rotate, flush và việc các file bị thay quá nhanh. Tùy hệ điều hành/phiên bản `tail`, cách follow theo tên và hành vi khi file biến mất có thể khác; kiểm tra manual của hệ đang dùng.

**Copy-truncate:** hệ thống copy file hiện có sang archive rồi truncate file đang ghi về 0. Cách này có thể gây khoảng thời gian ghi/đọc bị mất hoặc trùng trong một số tình huống; reader cần biết chính sách rotation thay vì suy đoán mọi file được rename.

**Quy tắc vận hành:** khi điều tra một khoảng thời gian chứa thời điểm rotate, cần xem cả file hiện tại **và các archive liên quan**, không chỉ `tail -f` file đang mở.

## 5. Đọc trên Windows PowerShell

Trên Windows, các thao tác tương đương có thể dùng PowerShell, với đường dẫn theo hệ thống:

### Xem 50 dòng cuối

```powershell
Get-Content -LiteralPath 'C:\logs\application.log' -Tail 50
```

### Xem dòng mới được bổ sung

```powershell
Get-Content -LiteralPath 'C:\logs\application.log' -Tail 50 -Wait
```

`-Wait` theo dõi nội dung đang được thêm. Hành vi khi file bị rename/truncate hoặc bị thay thế không nhất thiết giống `tail -F` của GNU; cần kiểm tra cơ chế rotation và phiên bản PowerShell.

### Tìm một request ID

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -SimpleMatch -Pattern 'requestId=req-7'
```

`Select-String` cho kết quả tìm kiếm theo dòng, thường kèm đường dẫn và số dòng. `-SimpleMatch` tìm literal, hữu ích cho ID có ký tự đặc biệt. Khi gặp log UTF-8 và ký tự tiếng Việt, cần lưu ý phiên bản Windows PowerShell/PowerShell 7 và cách công cụ nhận diện encoding.

### Xem metadata file

```powershell
Get-Item -LiteralPath 'C:\logs\application.log' |
    Select-Object FullName, Length, LastWriteTime
```

`Length` là **bytes**, không phải ký tự Java. Các lệnh trên không tự khôi phục log đã bị xóa/rotate hoặc log không bao giờ được appender ghi.

## 6. Encoding, newline và ký tự tiếng Việt

Trong Java, string là Unicode, nhưng file chứa **bytes**. Để đọc đúng tiếng Việt, bên ghi và bên đọc phải thống nhất **charset** (thường là UTF-8).

Những lỗi thường gặp:

- File thực tế được ghi UTF-8 nhưng công cụ đọc theo encoding khác → ký tự tiếng Việt bị lỗi.
- Log chứa `CRLF` (`\r\n`) nhưng parser chỉ hiểu LF trong một số trường hợp.
- File có UTF-8 BOM, hoặc pipeline thêm/bỏ BOM → token timestamp đầu tiên không khớp kỳ vọng.
- File đang được ghi dở, dòng cuối chưa có newline → công cụ đọc realtime có thể thấy **dòng chưa hoàn chỉnh**.
- Có ký tự điều khiển/ANSI màu từ console log được redirect → khi đọc bằng text có thể thấy mã escape hoặc hiển thị bất thường.

Trong chương trình Java, nên chỉ rõ UTF-8 thay vì phụ thuộc charset mặc định:

```java
// Fragment với java.nio.file.Files, Path, StandardCharsets.
try (java.io.BufferedReader reader =
        java.nio.file.Files.newBufferedReader(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý line ngay lúc đọc.
    }
}
```

Đây là **fragment**: `path` phải được khai báo và file tồn tại. `BufferedReader.readLine()` đọc đến LF, CR hoặc CRLF rồi trả chuỗi **không chứa ký tự xuống dòng**. Điều này thuận tiện để xử lý theo dòng nhưng không giữ nguyên cách file phân tách dòng; nếu cần bytes gốc, dùng API byte stream.

**Lưu ý tính đúng đắn:** nội dung đang được ghi có thể thay đổi giữa khi reader kiểm tra kích thước file và khi đọc. Đọc file live không tự tạo snapshot nhất quán. Nếu phân tích cần kết quả có thể tái lập, nên sử dụng bản copy/snapshot được tạo an toàn hoặc archive đã hoàn tất, có ghi nhận thời gian và phiên bản nguồn.

## 7. Ví dụ Java 17 độc lập: đọc file log theo luồng, lọc ID và đếm event mẫu

Ví dụ dùng **chỉ JDK 17+**, không cần Maven hay thư viện ngoài. Để chạy được trên máy bất kỳ mà không đụng vào log production, chương trình tạo một **thư mục tạm**, ghi nội dung log mẫu, đọc file đó, in kết quả và xóa tài nguyên tạm của chính nó sau khi kết thúc.

Mục tiêu ví dụ:

1. Mở file bằng `Files.newBufferedReader(..., UTF_8)`.
2. Đọc từng dòng bằng `readLine()`, không nạp toàn bộ file vào bộ nhớ.
3. Đếm dòng vật lý và **đếm event theo một quy ước header dành riêng cho file mẫu**.
4. Lọc những event có `requestId=req-7`.
5. Đóng reader bằng `try-with-resources`; không để handle file mở sau khi dùng.

Lưu **`ReadLogFileDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ReadLogFileDemo {
    private static boolean isEventHeader(String line) {
        // Chỉ đúng với file MẪU có prefix này.
        return line.startsWith("2026-11-09T");
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("read-log-demo-");
        Path logFile = directory.resolve("application.log");

        try {
            String sample = String.join("\n",
                    "2026-11-09T10:00:00Z INFO  requestId=req-7 event=start",
                    "2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry",
                    "2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed",
                    "    at com.example.Service.run(Service.java:42)",
                    "2026-11-09T10:00:03Z INFO  requestId=req-7 event=done"
            ) + "\n";

            Files.writeString(
                    logFile,
                    sample,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            int physicalLines = 0;
            int events = 0;
            int warnEvents = 0;
            int errorEvents = 0;

            try (BufferedReader reader =
                    Files.newBufferedReader(logFile, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    physicalLines++;

                    if (isEventHeader(line)) {
                        events++;
                        if (line.contains(" WARN ")) {
                            warnEvents++;
                        }
                        if (line.contains(" ERROR ")) {
                            errorEvents++;
                        }
                    }
                }
            }

            System.out.println("physicalLines=" + physicalLines);
            System.out.println("events=" + events);
            System.out.println("warnEvents=" + warnEvents);
            System.out.println("errorEvents=" + errorEvents);
            System.out.println("matching requestId=req-7:");

            try (BufferedReader reader =
                    Files.newBufferedReader(logFile, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (isEventHeader(line)
                            && line.contains("requestId=req-7")) {
                        System.out.println(line);
                    }
                }
            }
        } finally {
            Files.deleteIfExists(logFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReadLogFileDemo.java
java ReadLogFileDemo
```

**Stdout chính xác khi chương trình chạy thành công:**

```text
physicalLines=5
events=4
warnEvents=1
errorEvents=1
matching requestId=req-7:
2026-11-09T10:00:00Z INFO  requestId=req-7 event=start
2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry
2026-11-09T10:00:03Z INFO  requestId=req-7 event=done
```

**Stderr:** không có output do chương trình chủ động ghi khi chạy thành công. Nếu hệ thống từ chối tạo file tạm/ghi/xóa do quyền hoặc lỗi I/O, Java có thể phát exception với stack trace; đó không phải kết quả thành công mẫu.

Giải thích từng điểm:

- Dữ liệu mẫu có **năm dòng vật lý**: bốn header timestamp và một dòng `at com.example...` tiếp nối event ERROR. Vì vậy `physicalLines=5` nhưng `events=4`.
- `warnEvents=1`, `errorEvents=1` do chỉ có một header WARN và một header ERROR trong log mẫu.
- Ba dòng có `requestId=req-7` là ba **event khác nhau** của cùng request, không phải ba dòng ngẫu nhiên.
- `Files.createTempDirectory` tạo đường dẫn ngẫu nhiên và không in đường dẫn này, nên stdout có thể dự đoán. File trong thư mục tạm không đè bất kỳ log production nào.
- `StandardOpenOption.CREATE_NEW` yêu cầu file log tạm chưa tồn tại khi tạo; không vô tình ghi đè file có sẵn.
- `try-with-resources` đóng file reader ngay cả khi vòng lặp phát sinh lỗi. `finally` xóa file/thư mục **do chính demo tạo**; trong ứng dụng cần điều tra thực tế, **không xóa file nguồn** sau khi đọc.

**Giới hạn quan trọng:** `isEventHeader()` chỉ kiểm tra một prefix của mẫu. Đây **không phải parser production**: file có ngày khác, format timestamp khác, ký tự BOM, JSON, hoặc message chứa text trông như timestamp có thể làm số event sai. Muốn đếm event đáng tin, cần định nghĩa chuẩn format và parser theo từng loại log, hoặc phát structured logging ngay từ đầu.

### Đọc file log thật thay vì file mẫu

Với file đã tồn tại, cách mở tương tự:

```java
// Fragment trong method có quyền đọc file log.
Path path = Path.of("logs/application.log");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Phân tích mỗi dòng theo format thật, không xóa file nguồn.
    }
}
```

Đoạn này dùng các import ở ví dụ chính và giả định file `logs/application.log` có thật. Đường dẫn tương đối được giải theo **working directory**. Trong một ứng dụng chạy từ service manager hoặc container, đó không nhất thiết là thư mục source hay nơi đặt JAR.

## 8. Vì sao `BufferedReader` phù hợp với file lớn?

Một cách dễ viết nhưng có rủi ro với file hàng GB là:

```java
// Fragment chỉ nên dùng khi file nhỏ, kích thước đã biết.
var all = Files.readAllLines(path, StandardCharsets.UTF_8);
```

`Files.readAllLines` tạo một danh sách chứa toàn bộ dòng; file lớn có thể tiêu thụ rất nhiều heap và gây `OutOfMemoryError`. `Files.readString` cũng không phải lựa chọn phù hợp khi muốn đọc file log rất lớn vào một chuỗi.

Với `BufferedReader`, chương trình đọc **từng dòng**, giữ lượng dữ liệu hạn chế tại một thời điểm:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
```

Đây là **fragment**: `path` và `processLine` phải do ứng dụng cung cấp. Bộ nhớ theo số dòng đang giữ thường nhỏ hơn đọc hết file, nhưng **một dòng duy nhất cực dài vẫn có thể làm tốn bộ nhớ** vì `readLine()` phải dựng một `String` chứa dòng đó. Khi đầu vào có thể không tin cậy, cần chính sách giới hạn **bytes/ký tự cho mỗi record** hoặc parser streaming theo byte phù hợp.

### Dùng `Files.lines(...)` với Stream API

Java còn có:

```java
// Fragment: path là một Path hợp lệ; import java.util.stream.Stream.
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> line.contains(" ERROR ")).count();
    System.out.println("matchingPhysicalLines=" + count);
}
```

Lưu ý:

- `Files.lines` trả về `Stream<String>` có tài nguyên I/O nên **phải đóng**, thường qua `try-with-resources`.
- `filter` trên chuỗi đếm **dòng khớp**, không tự đếm log event.
- `Stream` hỗ trợ pipeline biểu đạt gọn, nhưng không phải giải pháp mặc định tối ưu cho mọi parser multiline có trạng thái.
- Với stream từ file, không nên sử dụng tùy tiện `parallel()` khi parser cần thứ tự, trạng thái hoặc ghép continuation.
- Nếu cần tái sử dụng dữ liệu sau khi stream đã được tiêu thụ, phải mở lại stream; stream không đọc lại tự động.

### Đọc N dòng cuối bằng Java, không tải cả file

Có thể giữ một hàng đợi tối đa N dòng khi quét file:

```java
// Fragment: imports java.util.ArrayDeque, java.util.Deque;
int limit = 100;
java.util.Deque<String> last = new java.util.ArrayDeque<>();

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (last.size() == limit) {
            last.removeFirst();
        }
        last.addLast(line);
    }
}
last.forEach(System.out::println);
```

Hàng đợi dùng bộ nhớ tỷ lệ với **100 dòng cuối** thay vì toàn bộ file, nhưng cách này vẫn **quét từ đầu đến cuối**, thời gian O(kích thước file). Nó không phải bản thay thế hiệu quả về I/O cho `tail` trên file hàng chục GB. Muốn đọc ngược từ cuối theo bytes/UTF-8, phải xử lý **ranh giới ký tự và newline**, không tùy tiện `RandomAccessFile.seek` rồi giải mã từ giữa một ký tự đa byte.

Trong đoạn minh họa này `limit=100` nên không có trường hợp hàng đợi bằng 0; nếu biến `limit` nhận input, cần validate là số dương.

## 9. Lọc log chính xác: level, request ID, thời gian và mã lỗi

Khi điều tra, một quy trình thường dùng là:

1. Xác định khoảng thời gian xảy ra lỗi, kèm timezone.
2. Tìm `requestId` hoặc `traceId` từ response/client hoặc alert, nếu hệ thống cung cấp.
3. Lọc đúng **service, file và thời gian** trước khi tìm chuỗi chi tiết.
4. Xem cả các event `INFO`/`WARN` trước lỗi và các `Caused by` trong stack trace.
5. Đối chiếu mã lỗi với metrics/tracing, không kết luận chỉ từ một dòng ERROR.

### Vì sao không chỉ tìm theo level?

Ví dụ:

```text
INFO  requestId=req-7 message="last error was recovered"
ERROR requestId=req-8 message="dependency timeout"
```

Lệnh tìm literal `ERROR` hoặc `error` có thể khớp chữ nằm trong **message** chứ không phải trường level. Nếu format biết rõ `level` nằm sau timestamp, có thể viết parser dành riêng cho format đó. Với log JSON, nên đọc trường `level` thay vì tìm text trên toàn dòng.

### Vì sao không chỉ tìm theo thời gian text?

Một file có thể ghi timestamp bằng UTC (`Z`), offset `+07:00`, múi giờ máy hoặc chỉ `HH:mm:ss`. So sánh chuỗi sẽ sai nếu các offset khác nhau hoặc format không có đủ ngày. Trong Java, nếu timestamp là ISO-8601 có offset, có thể parse bằng `java.time.OffsetDateTime.parse(...)` rồi so sánh **`Instant`**; với timestamp `Z`, `Instant.parse(...)` là lựa chọn đơn giản.

```java
// Fragment: chỉ đúng với timestamp ISO-8601 được cung cấp.
java.time.Instant first =
        java.time.Instant.parse("2026-11-09T10:00:00Z");
java.time.Instant second =
        java.time.Instant.parse("2026-11-09T10:00:02Z");

System.out.println(first.isBefore(second)); // true
```

Dòng cuối có kết quả `true` nếu chạy trong method với các import/tham chiếu trên. Tuy nhiên, **thứ tự timestamp không đủ để chứng minh thứ tự thực thi tuyệt đối giữa nhiều máy**: đồng hồ có thể lệch hoặc event có thể đến collector trễ. Correlation ID, sequence, span và cấu trúc causal mới giúp tái dựng luồng hệ thống đáng tin hơn.

### Cần giữ phần continuation của exception

Nếu một event ERROR có stack trace:

```text
2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed
java.lang.IllegalStateException: upstream unavailable
    at com.example.PaymentClient.call(PaymentClient.java:42)
    at com.example.OrderService.place(OrderService.java:17)
Caused by: java.net.SocketTimeoutException: timed out
    ...
```

thì chỉ in dòng chứa `ERROR` là **mất thông tin nguyên nhân**. Một parser multiline phải có quy tắc xác định **khi nào event mới bắt đầu**, lúc nào dòng tiếp tục thuộc event trước và xử lý exception nested. Nếu một message tự chứa dòng giả giống timestamp/level, parser dựa vào regex header có thể ghép sai; structured logging/collector đúng định dạng thường đáng tin hơn.

## 10. Đọc file log theo event thay vì theo dòng vật lý

Có ba phương án phổ biến:

| Kiểu file | Cách đọc phù hợp | Lưu ý |
| --- | --- | --- |
| Text, một event trên một dòng | Đọc từng dòng và parse header | Phải có quy ước escape newline trong message |
| Text, event có stack trace nhiều dòng | Parser multiline biết ranh giới event | Dễ sai nếu message chứa text giống header hoặc nhiều thread xen kẽ |
| JSON Lines/NDJSON, một JSON object mỗi dòng | Đọc từng dòng rồi parse thành object | Parser JSON chuẩn, kiểm tra schema và record size |

**Structured logging** giúp phân biệt rõ `timestamp`, `level`, `logger`, `requestId`, `message`, `exception`. Ví dụ một dòng JSON:

```json
{"timestamp":"2026-11-09T10:00:02Z","level":"ERROR","requestId":"req-8","errorCode":"UPSTREAM_TIMEOUT","message":"call failed","exception":"java.lang.IllegalStateException: upstream unavailable\n    at com.example.PaymentClient.call(...)"}
```

Đây là **một JSON object minh họa**, trong đó `\\n` là biểu diễn đã được escape ở giá trị chuỗi. Khi encoder thực sự xuất **compact JSON một dòng**, mỗi dòng vật lý có thể ánh xạ một event, dù giá trị `exception` chứa newline logic.

**Đừng tự parse JSON bằng `String.split(",")`**: dấu phẩy có thể xuất hiện trong chuỗi, JSON lồng nhau, giá trị escape và trường có thể thay đổi thứ tự. Sử dụng JSON parser như Jackson hoặc thư viện chính thức phù hợp phiên bản ứng dụng; đó là dependency ngoài JDK. Khi parse log từ bên ngoài, cần giới hạn kích thước, độ sâu dữ liệu, các loại field được phép xử lý và cách báo lỗi record hỏng.

Không mặc định tất cả file kết thúc `.json` đều là NDJSON: một file JSON có thể chứa **một array lớn**, một object được pretty-print qua nhiều dòng hoặc những record nối bằng delimiter khác. Phải biết contract của encoder/collector trước khi đọc.

## 11. File rotation: `.log.1`, timestamp và file `.gz`

Các hệ thống production thường xoay vòng file để tránh kích thước tăng mãi:

```text
logs/application.log
logs/application.log.1
logs/application.log.2.gz
logs/application.2026-11-08.log.gz
```

Tên file ở đây là ví dụ. Logback, Log4j 2, JUL `FileHandler`, logrotate hay container runtime có thể dùng quy tắc khác. Không suy đoán thứ tự chỉ theo tên file; hãy biết rolling policy thực tế.

Khi tìm một sự kiện cũ:

1. Xác định thời gian sự cố và timezone.
2. Xem file đang ghi hiện tại và danh sách archive.
3. Xem chính sách nén, max history, tổng dung lượng và khi file bị xóa.
4. Lựa chọn archive thuộc khoảng thời gian cần điều tra.
5. Nếu cần timeline toàn diện, đọc các archive theo thứ tự thời gian hợp lý và xử lý trường hợp record ở ranh giới rotation.
6. Đối chiếu dữ liệu ở central log storage nếu bản local đã bị rotation/retention.

### Đọc file gzip trên Unix-like

Với GNU gzip:

```bash
gzip -dc logs/application.log.2.gz | less
```

`gzip -dc` giải nén ra stdout **không tạo file giải nén mới**, rồi `less` cho phép xem. Tùy hệ, `zcat` hoặc `zgrep` cũng có thể sẵn nhưng cách đặt tên/option khác nhau.

Nếu muốn tìm request ID bên trong archive:

```bash
gzip -dc logs/application.log.2.gz | grep -n -F 'requestId=req-7'
```

**Bảo mật:** đọc/giải nén file từ nguồn không tin cậy cần cân nhắc kích thước sau giải nén; một file `.gz` rất nhỏ có thể giải nén thành khối lượng dữ liệu lớn. Không giải nén toàn bộ vào bộ nhớ để tìm một chuỗi.

### Đọc gzip bằng Java

```java
// Fragment: gzPath là Path trỏ tới file gzip có thật.
try (var input = new java.util.zip.GZIPInputStream(
            Files.newInputStream(gzPath));
     var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(
                    input, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng đã giải nén.
    }
}
```

Đây là **fragment**, không phải chương trình hoàn chỉnh; `gzPath`, `Files` và `StandardCharsets` cần được chuẩn bị tương ứng. `GZIPInputStream` chỉ phù hợp **file nén theo định dạng gzip**, không dùng cho ZIP archive chung. Dù dữ liệu được đọc theo luồng, cần kiểm soát giới hạn tổng bytes/dòng/record nếu nguồn không tin cậy.

## 12. Đọc log trong khi ứng dụng còn đang ghi

Đọc file live có nhiều tình huống đặc biệt:

**Dòng đang ghi dở:** Appender có thể viết nhiều lần trước khi newline được flush. Một reader đọc ngay lúc đó có thể thấy một phần record hoặc chưa thấy dữ liệu mới.

**Buffer:** Event đã được enqueue vào async logger nhưng chưa flush vào file. Không tìm thấy text lúc đó không có nghĩa ứng dụng chưa phát event.

**Rotation:** File bị rename/truncate hoặc nén. Reader giữ file descriptor cũ có thể không theo file mới; nếu cần đọc liên tục, phải xử lý reopen theo đường dẫn và tránh đọc trùng.

**Thay đổi file/encoding:** Một tiến trình hoặc agent khác ghi vào cùng file với encoding/format khác có thể làm parser lỗi. Chỉ nên có chủ thể sở hữu vòng đời file log theo thiết kế.

**Concurrent writers:** Nếu nhiều tiến trình cùng ghi text vào file không có đồng bộ/cơ chế file locking phù hợp, record có thể bị xen kẽ hoặc sai thứ tự. Không giả định việc mở file thành công nghĩa là có snapshot nhất quán.

**Ngày giờ và thứ tự:** Một hệ thống async có thể flush log không đúng thứ tự phát sinh; timestamp giữa nhiều node có thể lệch. Không sắp xếp một cách đơn giản rồi kết luận chính xác quan hệ nhân quả.

Để điều tra cần **tái lập chứng cứ**, sử dụng archive đã đóng hoặc snapshot có dấu thời gian/hash và giữ nguyên file nguồn; tránh chỉnh sửa trực tiếp file log. Công cụ đọc nên mở ở chế độ read-only.

### Có nên tự viết lệnh `tail -f` trong Java?

Có thể, nhưng đó là một **bài toán stateful** chứ không chỉ vòng lặp `readLine()`:

- Nhớ vị trí byte đã đọc, không cắt giữa UTF-8 multibyte.
- Xử lý partial line chờ đủ newline.
- Theo dõi file identity và tình huống rotate/recreate/truncate.
- Cân nhắc khi file biến mất, permission thay đổi, hoặc appender đổi đích.
- Có timeout/backoff, cơ chế dừng và không polling CPU quá cao.
- Quản lý offset/acknowledgment nếu sự kiện cần đưa qua collector đáng tin cậy.

`WatchService` của NIO có thể thông báo thay đổi trong **thư mục** trên một số hệ thống, nhưng không tự ghép event, không bảo đảm mỗi lần append có đúng một thông báo và không thay thế xử lý rotation. Nếu chỉ cần theo dõi lúc phát triển, `tail -f`, `tail -F` hoặc `Get-Content -Wait` đơn giản hơn; với production nên dùng log shipper/agent đã kiểm thử.

## 13. Quyền truy cập và bảo mật khi đọc file log

Log có thể chứa username, email, IP, session ID, query, exception message hoặc payload đã bị ghi sai. Việc **đọc file log** cũng là một thao tác với dữ liệu có thể nhạy cảm.

Những nguyên tắc cần áp dụng:

- **Chỉ đọc file bạn được cấp quyền.** Không vượt qua chính sách phân quyền để xem log của dịch vụ, tenant hoặc người dùng khác.
- **Không gửi file log thô lên nơi ngoài phạm vi cho phép** nếu chưa có chính sách xử lý PII/secret và cơ chế chia sẻ an toàn.
- **Không sao chép toàn bộ file lớn vào ticket/chat**; thay bằng đoạn cần điều tra đã được che dữ liệu phù hợp và kèm correlation ID.
- **Không chạy lệnh từ text log.** Stack trace, URL hay message trong log là dữ liệu, không phải chỉ dẫn thao tác hệ thống.
- **Không chọn đường dẫn tùy ý từ input người dùng** để đọc file server: đó là rủi ro path traversal/file disclosure. Nếu xây dựng giao diện đọc log, hãy dùng danh sách file cho phép, kiểm tra canonical path và symlink, phân quyền, giới hạn kích thước, rate limit.
- **Giữ lịch sử nguyên bản** nếu log được dùng làm bằng chứng kiểm toán; công cụ đọc/lọc cần tránh sửa file hoặc thay đổi retention ngoài quy trình.
- **Thận trọng với ANSI escape/control characters** từ đầu vào: khi in lại log vào terminal, các ký tự có thể điều khiển hiển thị. Dùng viewer/encoder bảo vệ thích hợp khi nguồn không tin cậy.

**Ghi chú:** Xóa/mask token trong bản log gửi ra ngoài không sửa được việc token đã có trong file gốc hoặc storage. Quy trình khắc phục rò rỉ cần có đánh giá bảo mật riêng (thu hồi secret, xử lý retention/access); đừng coi việc lọc trên terminal là đủ.

## 14. Những lỗi thường gặp khi đọc file log

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `NoSuchFileException` | Sai đường dẫn, working directory hoặc file đã rotate | Kiểm tra đường dẫn thực tế, container mount, file mới/archive |
| `AccessDeniedException` | Tiến trình đọc thiếu quyền | Kiểm tra chủ sở hữu/quyền truy cập theo chính sách |
| File tồn tại nhưng trống | Chưa phát event, level lọc, buffer chưa flush, appender chưa gắn | Kiểm tra logging config, level và pipeline |
| Chỉ thấy log rất cũ | Đang mở archive hoặc file cũ sau rotation | Xác định file đang được writer sử dụng |
| `tail -f` dừng thấy log sau rotate | Theo file cũ thay vì tên đường dẫn mới | Kiểm tra kiểu rotation, cân nhắc `tail -F` |
| Chữ tiếng Việt bị lỗi | Mismatch charset/BOM hoặc console encoding | Xác nhận encoding lúc ghi, đọc UTF-8 đúng |
| Đếm `ERROR` nhiều hơn số lỗi | Từ ERROR xuất hiện trong message/stack trace | Parse trường level, đếm event thay dòng |
| Không thấy toàn bộ exception | Đọc N dòng cuối hoặc chỉ grep header | Đọc continuation/stack trace hoặc dùng multiline parser |
| `OutOfMemoryError` khi đọc | `readAllLines`/ `readString` trên file quá lớn | Đọc streaming, giới hạn record, tránh giữ toàn bộ dữ liệu |
| Đọc file `.gz` ra ký tự lạ | Đang đọc bytes nén như text | Dùng gzip decoder trước rồi UTF-8 reader |
| Event bị trùng/gãy ở ranh giới | Rotation/copy-truncate hoặc nhiều writer | Kiểm tra rolling policy, file identity và collector |
| Không tìm thấy ID trong file | Log không có correlation ID, event ở file/service khác | Tìm theo trace/service/time range và cấu hình context |
| Timestamp sắp xếp không đúng | Các timezone khác nhau, clock skew, async flush | Parse Instant, đối chiếu trace/sequence |
| JSON parse lỗi | File không phải NDJSON hoặc record bị cắt | Kiểm tra schema, bytes/record, encoder và parser |
| `ReadLine` chỉ đọc một phần logic | Một event nhiều dòng bị chia thành các string | Ghép multiline hoặc dùng one-event-per-line JSON |
| Console có log nhưng file không có | Appender chỉ ra stdout/stderr | Kiểm tra đích cấu hình, không suy đoán luôn có file |

### Trình tự điều tra khi “mất log”

```text
Có chắc ứng dụng đã gọi logger?
          |
          v
Level/filter cho phép event?
          |
          v
File appender/handler được gắn và hoạt động?
          |
          v
Đường dẫn file đúng working directory/container?
          |
          v
File hiện tại hay archive đã rotation?
          |
          v
Đã flush; charset/format có đọc đúng?
          |
          v
Parser/filter có vô tình bỏ sự kiện?
          |
          v
Collector/storage có giữ record đó?
```

Đừng tăng retention của storage nếu event bị logger chặn ngay từ đầu. Đừng sửa parser nếu file chưa hề được appender ghi. Xác định **tầng đầu tiên làm event mất hoặc bị biến đổi** sẽ giảm thời gian điều tra.

## 15. Checklist thực hành

Trước khi kết luận đã đọc/điều tra file log đúng:

1. **Đúng nguồn:** file thuộc service, instance, môi trường và khoảng thời gian cần xem.
2. **Đúng đường dẫn:** đường dẫn tương đối/tuyệt đối, working directory, container mount rõ ràng.
3. **Đúng định dạng:** biết đây là text một dòng, text nhiều dòng hay JSON Lines.
4. **Đúng encoding:** dùng UTF-8 hoặc charset phù hợp; biết cách xử lý CRLF và BOM.
5. **Đúng đơn vị đếm:** phân biệt **dòng vật lý** và **event**, nhất là có exception.
6. **Đúng phạm vi thời gian:** timestamp parse đúng timezone, không suy từ đồng hồ máy đọc.
7. **Đúng correlation:** lọc theo requestId/traceId/errorCode và đọc cả các event trước/sau.
8. **Đúng rotation:** kiểm tra file hiện tại lẫn archive liên quan, cả `.gz` nếu có.
9. **Đúng tài nguyên:** file lớn dùng buffered/streaming, không tải toàn bộ vào heap; giới hạn record.
10. **Đúng độ tin cậy:** biết file live có thể thay đổi, event có thể flush trễ, reader có thể đang theo file cũ.
11. **Đúng bảo mật:** chỉ xem dữ liệu được phép, không tiết lộ secret/PII, không chạy text từ log.
12. **Đúng đối chiếu:** so sánh với trace, metric, response hoặc collector khi cần bằng chứng chính xác.
13. **Đúng kết quả:** một ví dụ Java 17 có thể mở file UTF-8, đọc từng dòng, đếm và lọc ID mà không sửa log production.

**Kết luận:** Đọc file log là kỹ năng kết hợp **định vị file, đọc hiệu quả, hiểu format và theo dõi vòng đời dữ liệu**. Lệnh `head`, `tail`, `grep`, `less` hoặc PowerShell giúp kiểm tra nhanh; `BufferedReader` và `Files.lines` cho phép viết công cụ Java; còn log rotation, multiline stack trace, structured JSON và quyền truy cập quyết định việc kết quả có đáng tin và an toàn hay không.

## Tài liệu tham khảo chính thức

- Oracle Java 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java 17 — `BufferedReader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Oracle Java 17 — `GZIPInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html
- GNU Coreutils — `tail`: https://www.gnu.org/software/coreutils/manual/html_node/tail-invocation.html
- Logback — Appenders: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 — Appenders: https://logging.apache.org/log4j/2.x/manual/appenders.html
