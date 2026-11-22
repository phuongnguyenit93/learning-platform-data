# Xoay tệp và giới hạn dung lượng với `java.util.logging.FileHandler`

`java.util.logging.FileHandler` ghi log ra tệp và hỗ trợ xoay vòng nhiều tệp theo giới hạn dung lượng. Khi tệp hiện tại đạt gần ngưỡng cấu hình, handler chuyển sang thế hệ tiếp theo; số thế hệ được giữ lại do `count` quyết định. Đây là cơ chế có sẵn trong JDK, phù hợp với ứng dụng cần log ra tệp mà không phải tự quản lý việc đổi tên và mở lại tệp.

Giới hạn của `FileHandler` là ngưỡng gần đúng cho từng tệp, không phải hard cap tuyệt đối cho tổng số byte. Record làm vượt ngưỡng có thể vẫn được ghi vào tệp hiện tại trước khi handler xoay vòng. Nếu yêu cầu là không đọc hoặc ghi vượt một số byte tuyệt đối, cần thêm cơ chế giới hạn ở tầng lưu trữ hoặc một handler có chính sách riêng.

## 1. Các thành phần của xoay vòng log

Xoay vòng log thường có bốn thành phần:

- **Pattern:** quy tắc tạo tên và vị trí tệp log.
- **Limit:** ngưỡng dung lượng tính theo byte cho mỗi tệp.
- **Count:** số thế hệ tệp được dùng trong chu kỳ xoay vòng.
- **Append:** có ghi nối vào các tệp đã tồn tại khi mở handler hay không.

Ví dụ cấu hình:

```java
FileHandler handler = new FileHandler(
    "logs/application-%g.log",
    1_048_576,
    5,
    true
);
```

Trong ví dụ này, mỗi tệp có ngưỡng xấp xỉ 1 MiB và handler dùng năm thế hệ. Pattern `%g` tạo tên như `application-0.log`, `application-1.log` ... `application-4.log`.

## 2. `limit` — giới hạn dung lượng mỗi tệp

Tham số `limit` của constructor `FileHandler(pattern, limit, count, append)` được tính bằng byte:

```java
int limit = 10 * 1024 * 1024; // khoảng 10 MiB
```

- `limit > 0`: handler xoay vòng khi lượng dữ liệu ghi vào tệp đạt ngưỡng.
- `limit == 0`: không áp dụng xoay vòng dựa trên dung lượng.
- Giá trị âm không hợp lệ.

Không nhầm byte với ký tự. Một ký tự Unicode có thể chiếm nhiều byte theo encoding; formatter cũng có thể thêm timestamp, level, tên logger, stack trace và newline. Vì vậy kích thước log thực tế phụ thuộc formatter và encoding.

### Vì sao tệp có thể lớn hơn `limit`?

`FileHandler` ghi log theo record. Record làm bộ đếm vượt ngưỡng có thể được ghi xong rồi handler mới xoay vòng. Ví dụ limit là 220 byte và record tiếp theo dài 35 byte, tệp có thể vượt ngưỡng bởi record đó trước khi chuyển sang generation tiếp theo.

Do đó, `limit` là giới hạn gần đúng cho từng tệp. Không dùng nó như cam kết rằng tệp không bao giờ vượt một kích thước tuyệt đối, và cũng không coi `limit * count` là hard cap tổng dung lượng.

## 3. `count` — số thế hệ được giữ

`count` xác định số tệp trong chu kỳ xoay vòng và phải ít nhất là 1.

Ví dụ `count = 3` với pattern `application-%g.log` tạo ba tên thế hệ:

```text
application-0.log
application-1.log
application-2.log
```

Khi handler cần xoay vòng sau thế hệ cuối, các thế hệ cũ được chuyển vòng để tái sử dụng số lượng tệp đã cấu hình; dữ liệu log cũ nhất sẽ bị thay thế theo chu kỳ. Vì vậy `count` quyết định độ dài lịch sử log được giữ tại chỗ.

Nếu chỉ cần một tệp, dùng `count = 1`. Nếu cần lưu lịch sử dài hơn, tăng `count` hoặc chuyển log cũ sang hệ thống lưu trữ/thu thập log riêng.

## 4. Pattern đặt tên tệp

`FileHandler` hỗ trợ các thành phần đặc biệt trong pattern:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%t` | Thư mục tạm của hệ điều hành | `%t/app-%g.log` |
| `%h` | Thư mục home của người dùng hiện tại | `%h/logs/app-%g.log` |
| `%g` | Số thế hệ trong chu kỳ xoay vòng | `app-%g.log` |
| `%u` | Số duy nhất để tránh xung đột tên/lock | `app-%u-%g.log` |
| `%%` | Ký tự `%` theo nghĩa đen | `app-%%-log.txt` |

`%g` hữu ích khi `count > 1`. Nếu pattern không có `%g` mà count lớn hơn 1, FileHandler tự thêm số thế hệ vào tên tệp. `%u` giúp tránh xung đột khi nhiều handler hoặc tiến trình cùng dùng một pattern; FileHandler có cơ chế lock tệp để tránh ghi đồng thời vào cùng một file log.

Ví dụ đường dẫn tuyệt đối:

```java
String pattern = "%h/my-app/logs/application-%u-%g.log";
```

Đảm bảo thư mục cha tồn tại và tiến trình có quyền ghi. Pattern chỉ tạo tên tệp; không nên giả định rằng mọi thư mục trung gian đều tự được tạo.

## 5. `append` — ghi nối hay bắt đầu tệp mới

Tham số `append` điều khiển cách mở các tệp đã tồn tại:

- `true`: ghi nối vào tệp phù hợp nếu tệp đã tồn tại.
- `false`: mở tệp theo chế độ ghi mới, thay thế nội dung cũ theo cách mở của handler.

Trong môi trường production, chọn giá trị dựa trên chính sách lưu log sau khi khởi động lại. Nếu muốn giữ nội dung cũ khi ứng dụng restart, cân nhắc `append=true`; nếu mỗi lần chạy cần bộ log mới, dùng `append=false` và pattern có định danh phiên chạy hoặc thư mục riêng.

Không dùng cùng pattern cho nhiều ứng dụng không liên quan nếu chúng có thể tranh chấp file lock. Dùng `%u`, tên ứng dụng hoặc thư mục riêng để giảm xung đột.

## 6. Cấu hình bằng Java code

Ví dụ tạo logger và FileHandler:

```java
Logger logger = Logger.getLogger("com.example.service");
logger.setLevel(Level.INFO);
logger.setUseParentHandlers(false);

FileHandler handler = new FileHandler(
    "logs/application-%g.log",
    1_048_576,
    5,
    true
);
handler.setLevel(Level.INFO);
handler.setFormatter(new SimpleFormatter());
logger.addHandler(handler);
```

`setUseParentHandlers(false)` ngăn record tiếp tục được chuyển lên handler của logger cha, nhờ đó tránh ghi trùng ra console nếu ứng dụng chỉ muốn dùng file handler này.

Level của logger và level của handler đều ảnh hưởng việc record có được ghi hay không. Đặt logger ở `INFO` và handler ở `INFO` cho phép record INFO trở lên đi qua cả hai tầng.

### Đóng handler đúng cách

`FileHandler` giữ file handle và lock trong thời gian hoạt động. Khi ứng dụng dừng hoặc thay cấu hình, cần gọi `close()` để flush, đóng tệp và giải phóng lock:

```java
logger.removeHandler(handler);
handler.close();
```

Nếu tạo handler trong một phương thức khởi tạo ứng dụng, giữ tham chiếu đến nó và đóng trong lifecycle shutdown. Không tạo handler mới cho từng log record.

## 7. Cấu hình bằng `logging.properties`

Ứng dụng có thể cấu hình `FileHandler` bằng file properties thay vì viết constructor trong code:

```properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.pattern=%h/my-app/logs/application-%g.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
```

Khởi động JVM với file cấu hình:

```bash
java -Djava.util.logging.config.file=logging.properties -jar application.jar
```

File cấu hình được LogManager đọc khi khởi tạo logging. Nếu ứng dụng tự gọi `LogManager.readConfiguration(...)`, cần thực hiện ở thời điểm khởi động thích hợp và tránh cấu hình lại sau khi các logger/handler đã được sử dụng mà không quản lý lifecycle.

`java.util.logging` thuộc module `java.logging` của JDK. Với runtime image được tạo tối giản bằng `jlink`, cần bảo đảm module này được đưa vào image.

## 8. Chương trình Java 17 hoàn chỉnh kiểm tra xoay vòng

Ví dụ sau ghi 18 record có kích thước cố định vào ba generation. Formatter một dòng giúp kích thước record dễ dự đoán; sau khi đóng handler, chương trình xác nhận có đúng ba tệp và mỗi tệp không vượt quá `limit` cộng kích thước một record. Điều kiện này phản ánh việc record vượt ngưỡng có thể được ghi trước khi xoay vòng.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;
import java.util.stream.Stream;

public class Main {
    private static final class OneLineFormatter extends SimpleFormatter {
        @Override
        public synchronized String format(LogRecord record) {
            return record.getMessage() + System.lineSeparator();
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Path.of(args[0]);
        Files.createDirectories(directory);

        final int limit = 220;
        final int count = 3;
        int maxRecordBytes = ("record-01-" + "x".repeat(24)
            + System.lineSeparator()).getBytes(StandardCharsets.UTF_8).length;

        Logger logger = Logger.getLogger("rotation-" + directory.getFileName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        FileHandler handler = new FileHandler(
            directory.resolve("app-%g.log").toString(),
            limit,
            count,
            false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        handler.setFormatter(new OneLineFormatter());
        logger.addHandler(handler);

        try {
            for (int i = 1; i <= 18; i++) {
                String sequence = (i < 10 ? "0" : "") + i;
                logger.info("record-" + sequence + "-" + "x".repeat(24));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        try (Stream<Path> files = Files.list(directory)) {
            List<Path> paths = files
                .filter(path -> path.getFileName().toString().endsWith(".log"))
                .sorted(Comparator.comparing(Path::toString))
                .toList();

            if (paths.size() != count) {
                throw new AssertionError(
                    "expected " + count + " generations, got " + paths.size());
            }

            boolean withinApproximateLimit = paths.stream()
                .allMatch(path -> {
                    try {
                        return Files.size(path) <= limit + maxRecordBytes;
                    } catch (java.io.IOException error) {
                        throw new java.io.UncheckedIOException(error);
                    }
                });
            if (!withinApproximateLimit) {
                throw new AssertionError("a file exceeded the limit plus one record");
            }

            System.out.println("generation count: " + paths.size());
            System.out.println(
                "all files within limit plus one record: " + withinApproximateLimit);
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main ./logs
```

Stdout chính xác:

```text
generation count: 3
all files within limit plus one record: true
```

Ví dụ ghi log vào thư mục `./logs`. Tên các tệp được tạo theo pattern `app-0.log`, `app-1.log` và `app-2.log`. Kích thước thực tế có thể khác theo hệ điều hành và cách ghi newline; chương trình kiểm tra theo ngưỡng cộng một record thay vì hard-code kích thước từng tệp.

## 9. Ước lượng dung lượng lưu trữ

Với `limit = L` và `count = N`, có thể ước lượng vùng lưu log khoảng `L × N`, cộng phần vượt ngưỡng do record. Đây chỉ là ước lượng, vì:

- Record cuối trước khi xoay vòng có thể làm tệp vượt `limit`.
- Formatter có thể tạo record rất dài, chẳng hạn stack trace hoặc payload nhiều dòng.
- Nhiều handler/ứng dụng có thể ghi vào các pattern hoặc thư mục khác nhau.
- Lock file và các tệp phụ trợ có thể tồn tại trong thời gian handler hoạt động.
- Tệp cũ có thể được giữ ở nơi khác bởi tiến trình thu thập log hoặc tác vụ backup.

Nếu hệ thống có yêu cầu dung lượng đĩa tối đa nghiêm ngặt, cần chính sách ở tầng lưu trữ: quota filesystem, log collector, tác vụ retention hoặc handler tùy chỉnh có kiểm soát kích thước record. Không dùng `limit × count` như giới hạn tuyệt đối.

## 10. Chọn chiến lược xoay vòng

| Nhu cầu | Cấu hình gợi ý |
| --- | --- |
| Ứng dụng nhỏ, chỉ cần log gần nhất | `limit` vừa phải, `count=1` |
| Giữ lịch sử vài thế hệ | `limit` theo dung lượng record, `count` từ 3 đến 10 |
| Nhiều instance cùng host | Pattern có `%u` hoặc thư mục riêng theo instance |
| Giữ log qua lần restart | `append=true` và pattern ổn định |
| Mỗi lần chạy cần log mới | `append=false` và pattern có session/run identifier |
| Cần retention theo ngày | Dùng cơ chế rotation theo thời gian của hệ thống logging phù hợp; `FileHandler` chuẩn xoay theo dung lượng |
| Cần hard disk quota | Kết hợp quota/retention ở tầng lưu trữ hoặc handler có chính sách cứng |

`FileHandler` chuẩn xoay theo dung lượng, không có tham số xoay theo ngày. Nếu yêu cầu là xoay theo thời gian, cần scheduler hoặc logging framework hiện hành có rolling policy theo thời gian; không mô phỏng xoay ngày bằng cách thay đổi đồng hồ hoặc đổi tên file thủ công khi handler vẫn đang mở.

## 11. Các lỗi thường gặp

1. **Hiểu `limit` là hard cap.** Record làm vượt ngưỡng có thể vẫn được ghi; đây là giới hạn gần đúng cho mỗi tệp.
2. **Nhầm byte với ký tự.** Encoding và formatter quyết định số byte thực tế.
3. **Đặt `count` quá nhỏ.** Thế hệ cũ bị thay thế nhanh và lịch sử log ngắn.
4. **Quên `%g` khi cần tên generation rõ ràng.** Nếu count lớn hơn một, handler tự bổ sung generation khi pattern thiếu `%g`, nhưng pattern tường minh dễ vận hành hơn.
5. **Dùng pattern chung cho nhiều tiến trình.** Có thể xảy ra tranh chấp lock hoặc tạo hậu tố unique; dùng `%u` và thư mục riêng.
6. **Không đóng handler.** File handle và lock có thể tiếp tục được giữ, đồng thời dữ liệu cuối chưa được flush.
7. **Tạo FileHandler cho mỗi request.** Việc mở/đóng handler liên tục gây overhead và tranh chấp file; tạo handler theo lifecycle ứng dụng.
8. **Không kiểm tra quyền ghi hoặc thư mục.** Handler có thể ném IOException khi không mở được tệp.
9. **Ghi log trùng ở console và file.** Kiểm tra `useParentHandlers` và cấu hình handler của logger cha.
10. **Đặt logger level nhưng quên handler level.** Record có thể bị lọc ở một trong hai tầng.
11. **Dùng `append=false` mà không tính đến log cũ.** Các tệp generation phù hợp có thể bị ghi mới; chọn append theo retention policy.
12. **Coi `count × limit` là tổng dung lượng chính xác.** Record vượt ngưỡng và các tệp ngoài chu kỳ có thể làm tổng thực tế lớn hơn.
13. **Kỳ vọng FileHandler xoay theo ngày.** FileHandler chuẩn xoay theo dung lượng; xoay theo thời gian cần cơ chế khác.

## 12. Ghi nhớ

1. `java.util.logging.FileHandler` ghi log ra file và hỗ trợ xoay vòng theo dung lượng.
2. `limit` tính bằng byte và là ngưỡng gần đúng cho từng tệp; record vượt ngưỡng có thể được ghi trước khi xoay.
3. `count` là số thế hệ tệp trong chu kỳ; các thế hệ cũ được tái sử dụng khi xoay vòng.
4. `%g` biểu diễn generation; `%u` tránh xung đột tên/lock; `%t` là thư mục tạm; `%h` là home.
5. `append` quyết định có ghi nối vào file tồn tại khi mở handler hay không.
6. Có thể cấu hình qua constructor hoặc `logging.properties`.
7. Luôn đóng handler khi lifecycle kết thúc để flush và giải phóng file lock.
8. `limit × count` chỉ là ước lượng dung lượng, không phải hard cap tổng.
9. FileHandler chuẩn xoay theo dung lượng; yêu cầu xoay theo thời gian hoặc hard quota cần cơ chế bổ sung.